---
title: "Trading System Notes #3: Memory Pools and Allocators"
date: 2026-09-17
slug: "hot-path-memory-allocators"
description: "Why malloc/free's real problem is variance, not speed — and four increasingly general ways to guarantee nothing on the hot path is happening for the first time: an O(1) free-list pool, locked and pre-faulted pages, a bump-allocating arena behind a custom STL allocator, and std::pmr's runtime alternative to all three. Closes with a reference object pool that folds the first two techniques into one class."
summary: "Every technique in this post does the same thing at a different layer: move an uncertain, kernel-involving operation off the hot path and force it to happen once, upfront, before it can ambush a single request. An object pool replaces malloc's variable-cost search with an always-O(1) free list. mlockall and careful mallopt tuning stop the kernel from quietly taking pages back — and pre-faulting closes the one gap mlock alone leaves open. A hand-rolled arena allocator makes the STL itself cooperate with a custom allocator backed by bump-pointer memory. std::pmr solves the same STL-cooperation problem the standard library's way — trading compile-time speed for runtime flexibility."
categories: [Systems]
tags: [cpp, memory-pool, allocator, mlock, tlb-shootdown, pmr, hft, low-latency, stl]
toc: true
homepage: false
---

# Trading System Notes #3: Nothing Happens for the First Time on the Hot Path — Object Pools, Locked Pages, and Polymorphic Allocators

> **One-line thesis**: every technique below does the same thing at a different layer — take an operation whose cost depends on state you don't control (a lock, a syscall, a page fault, a virtual dispatch) and force it to happen once, at startup, so the hot path is never the one discovering it for the first time.

## What You're Actually Fighting

`malloc`/`free` are not slow. Call one a thousand times in a tight loop and the average cost looks perfectly fine. The problem HFT code has with them isn't the mean — it's the **tail**, and the tail is state-dependent: glibc's allocator hands out per-thread arenas to avoid lock contention, but once thread count exceeds arena count, two threads start fighting over the same arena's lock; a request the current arena can't satisfy might mean a fresh `brk`/`mmap` call into the kernel; freed memory gets sorted into size-class bins that have to be walked and possibly coalesced, and how long that walk takes depends on the fragmentation history of everything that happened on that heap before. None of these costs are fixed. All of them depend on "what has this process been doing so far" — which is exactly the kind of question a hot path cannot afford to ask.

Everything in this post is a variation on the same fix: figure out which operation has this property — cost depends on first-touch, or contention, or fragmentation, none of it knowable in advance — and **move it to a point in the program's lifetime where you don't care how long it takes.** Usually that point is startup. Section 1 moves the allocation itself. Section 2 moves the kernel's decision about whether your pages are allowed to leave RAM, and — less obviously — the kernel's decision about whether they're backed by physical memory *at all*. Sections 3 and 4 generalize the same move so it works for arbitrary STL containers, not just a single hand-rolled type, and disagree with each other about where the resulting flexibility should be paid for: at compile time, or at run time.

---

## 1. The Object Pool: Trading a Search for a Pointer

The fix for "I don't want to call malloc on the hot path" is almost embarrassingly direct: allocate everything you will ever need once, at startup, and hand pieces of that pre-allocated block out and back on demand. That's an object pool — a fixed number of instances of one type `T`, held in memory the program already owns.

### The naive version has the same disease in miniature

```cpp
struct ObjectBlock {
  T object_;
  bool is_free_ = true;
};
std::vector<ObjectBlock> store_;
size_t next_free_index_ = 0;
```

`allocate()` placement-constructs into `store_[next_free_index_]`, marks it taken, and then calls `updateNextFreeIndex()` to find the *next* free slot for next time — by scanning forward from the current position, wrapping around at the end. In an access pattern close to FIFO, the very next slot is usually free and the scan stops almost immediately. But nothing guarantees that pattern. Hold objects out of order, release them out of order, and the scan can walk the entire pool before finding a hole — **worst case O(n), and the worst case is exactly as unpredictable as the fragmentation-dependent cost this pool was supposed to replace.** The kernel round-trip got eliminated; a smaller, same-shaped problem grew back inside the pool.

### The fix: don't search, maintain

```cpp
T* objects_;
std::size_t* free_list_;
std::size_t next_free_index_;                    // head of the free list
static constexpr std::size_t kInvalidIndex = -1;  // list terminator
```

`free_list_` is a linked list of free slots — but implemented as **array indices instead of pointers**. `free_list_[i]` doesn't record whether slot `i` is free; it records *which slot comes next in the free list, if `i` is currently the head*. `next_free_index_` is that head. `allocate()` takes whatever slot `next_free_index_` currently points to and moves the head to `free_list_[that slot]` — one read, one write, no scan. `deallocate()` pushes the freed slot back onto the head the same way. Both operations are **exactly the same handful of instructions every single time**, because the free list is maintained incrementally on every call — by the time you call `allocate()`, "what's the next free slot" is already sitting in a variable, not something you go looking for.

That's worth being precise about, because it's a common mislabel: this is **not an intrusive linked list**. An intrusive list stores its `next` pointer *inside the payload type itself* — the object doubles as its own node. Here, `free_list_` is a completely separate array running in parallel with `objects_`; a `T` has no idea it's linked into anything. The genuinely intrusive version of this pool would `union` the "next free index" into the same memory a not-yet-constructed `T` would otherwise occupy, saving the second array at the cost of a less obvious ownership story — a real memory-vs-simplicity tradeoff the reference implementation opted out of.

One layout detail worth keeping: `ObjectBlock` packs `T` and `is_free_` into a single struct rather than two parallel arrays. A single `allocate()` call touches both fields together, so keeping them adjacent means one cache-line fetch does the job instead of two independent ones landing on unrelated lines.

---

## 2. Locked Isn't Enough: The mmap Trap and the TLB Shootdown Tax

The pool solves "don't ask the allocator for memory on the hot path." It does nothing about a second, easy-to-miss failure mode: the memory you already have can still be taken away from you, or can still cost you a surprise the first time you touch it.

### mlockall alone has a hole in it

`mlockall(MCL_CURRENT | MCL_FUTURE)` tells the kernel: every page this process currently holds, and every page it will ever hold, stays resident — never swapped out. That sounds complete. It isn't, because of one detail: **`munmap` doesn't unlock a page, it tears down the entire mapping the lock was attached to.** glibc routes any allocation above `M_MMAP_THRESHOLD` (128 KB by default) through `mmap` instead of the heap, and `free()`-ing that memory calls `munmap` on it immediately — silently discarding whatever `mlockall` had guaranteed, the moment that allocation is released.

<!--
╔══════════════════════════════════════════════════════════════════╗
║  🖼  ILLUSTRATION  ——  Torn down, not unlocked                    ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Academic graphite pencil illustration on clean white paper.     ║
║  16:9. Precise technical linework, careful cross-hatching for    ║
║  shading and depth. Monochrome graphite only — no color, no      ║
║  watercolor, no graph-paper grid. Scientific-journal /           ║
║  textbook figure. NOT cartoon, NOT colorful.                     ║
║                                                                  ║
║  Topic: munmap does not undo a lock on a page — it removes the   ║
║  entire mapping the lock was attached to, so the lock has        ║
║  nothing left to hold.                                           ║
║                                                                  ║
║  Main metaphor: a two-panel dissection diagram, left and right,  ║
║  of the exact same stone plinth.                                 ║
║                                                                  ║
║  Layout: side-by-side comparison (two-panel), left labeled       ║
║  "BEFORE", right labeled "AFTER".                                ║
║                                                                  ║
║  Objects and labels:                                             ║
║   - left panel: a heavy iron strongbox sitting on the plinth,    ║
║     wrapped tight in a chain with a closed padlock — labeled     ║
║     "mlock() — page resident, chain drawn taut"                  ║
║   - right panel: the exact same plinth, now bare — the strongbox ║
║     itself is gone entirely, but the same chain and padlock      ║
║     still hang in mid-air in the box's old outline, closed and   ║
║     intact, holding nothing — labeled "munmap() — the box is     ║
║     gone. The lock never opened; there is simply nothing left    ║
║     for it to hold."                                             ║
║   - a faint dotted outline on the right plinth marking exactly   ║
║     where the strongbox used to sit                              ║
║                                                                  ║
║  Title (top, large): "Torn Down, Not Unlocked"                   ║
║  Subtitle: "munmap doesn't undo a lock — it removes what the     ║
║  lock was attached to"                                           ║
║  Footer caption: "Torn Down, Not Unlocked."                      ║
║                                                                  ║
║  All text in English. No Chinese characters. No color fills.     ║
║  No gradients. Monochrome graphite only.                         ║
╚══════════════════════════════════════════════════════════════════╝
-->

![Before and after: a locked strongbox on a plinth, then the same plinth with the box gone entirely — only the still-closed chain and padlock hang in mid-air where it used to sit](/images/hot-path-allocators/torn-down-not-unlocked.jpg)

Closing that hole takes three separate `mallopt` calls, each blocking a different path back to the kernel:

- **`M_MMAP_MAX = 0`** — forbid the mmap path entirely. Every allocation, regardless of size, goes through the heap; `free()` becomes pure bookkeeping and never calls `munmap`.
- **`M_TRIM_THRESHOLD = -1`** — the same idea applied to the heap itself. By default, glibc shrinks the heap back toward the OS via `sbrk` once enough contiguous free space accumulates at the top; this disables that, so a large chunk of freed space at the top of the heap is never handed back.
- **`M_ARENA_MAX = 1`** — a different axis: multiple worker arenas are themselves backed by additional `mmap`-obtained regions. Forcing a single arena (allocation only happens at startup anyway, so the concurrency benefit of multiple arenas is moot here) removes those extra mmap sources up front.

### The tax that isolcpus can't hide you from

Any page-table change — `munmap`, `mprotect`, or the kernel's own transparent-huge-page background compaction — forces a **TLB shootdown**: the core making the change doesn't know which other cores have cached the now-stale translation, so it broadcasts an inter-processor interrupt (IPI) to every core that has recently run the same process's address space. Each one has to stop, trap into the kernel, invalidate the affected TLB entry, and resume — microsecond-scale, and it scales with how many cores share that address space.

The sharp, easy-to-get-wrong point: **`isolcpus` does not protect against this.** `isolcpus` operates at the scheduler layer — it controls whether the scheduler will place *tasks* on a given core. A TLB shootdown is a hardware interrupt, delivered based on which cores are recorded in the kernel's `mm_cpumask` for that address space — a completely different mechanism that the scheduler has no say over. A perfectly isolated, pinned hot-core thread can still get interrupted mid-flight by a *cold* thread in the same process calling `munmap` or `mprotect`, because both threads share the same `mm_struct`, and the shootdown targets the address space, not the scheduling class. This is the deeper reason THP and automatic NUMA balancing get disabled on tuned systems, beyond "unpredictable latency from background compaction" — both routinely rewrite page tables, and every rewrite is a shootdown that reaches cores the scheduler was told never to touch.

---

## 3. An Arena Behind the STL: A Pointer That Only Moves Forward

The object pool only ever hands out one type, `T`. Real hot-path code wants to use `std::vector`, `std::string`, ordinary STL containers — without those containers ever touching the global heap. That means writing something that satisfies the C++ allocator interface, backed by memory the program already owns.

### The allocator: a pointer that only ever moves forward

```cpp
struct MemoryBlock {
  size_t used, capacity;
  bool is_active;
  // ...
};
```

An arena allocates from a pre-reserved block by tracking one number: how many bytes of this block are already spoken for. `allocate(size)` rounds the current write position up to the requested alignment, checks whether `used + size` still fits in `capacity`, and if so simply advances `used` and returns the old position — no search, because there's nothing to search: the "next free position" is always exactly wherever the pointer currently sits. When a block fills up, the arena activates the next pre-reserved block the same way. This is strictly cheaper than section 1's free list — not even a linked-list pointer swap, just an add — and the price is that there is no way to free a single allocation out of the middle. Nothing records where any individual allocation started or ended, so there's nothing to look up even if you wanted to release one. The only reset operation is global: rewind every block's `used` back to zero and start over. That's the right tradeoff for a batch of objects with identical lifetimes — everything allocated while processing one tick, thrown away together once the tick is done — and the wrong one for objects with staggered lifetimes, which still belong in section 1's pool.

### Pre-faulting: closing the gap mlock leaves at first touch

The arena's backing memory is obtained once, at construction, with `posix_memalign` and `mlock()` — this time locking just the arena's own region, a more surgical complement to section 2's process-wide `mlockall`. But a freshly obtained virtual address range isn't backed by physical memory yet: Linux maps pages lazily, and the actual physical page only gets assigned on the **first write**, via a page fault that traps into the kernel. `mlock` guarantees a page won't be evicted once it's backed — it says nothing about whether the mapping has been established yet. The constructor closes that gap with one line: `memset(raw_memory, 0, total_size)`, touching every page once, at startup, so every fault that was ever going to happen already has. By the time the hot path runs, every page in the arena is not just locked, but *already mapped* — nothing left to discover for the first time.

The allocator that adapts this arena to the STL interface (`allocate`/`deallocate`/`construct`/`destroy`/`rebind`) is mostly boilerplate worth knowing exists rather than dwelling on — with one exception: `deallocate()` is a deliberate no-op, for the same reason `reset()` is the only way to reclaim memory. Construction and destruction of individual objects still happen normally through `construct`/`destroy`; only the *memory* side of the contract is neutered.

---

## 4. std::pmr: The Same Answer, Paid for at Runtime

Section 3's custom allocator has a sharp edge nothing in the type system warns you about: `std::vector<int>` and `std::vector<int, LowLatencyAllocator<int>>` are unrelated types. The allocator is a template parameter — part of the container's type, not a runtime setting — so a function written to take `std::vector<int>&` will reject the arena-backed version outright, and every function that needs to accept either has to be templated on the allocator too.

`std::pmr` (C++17) solves the same "let the STL use my allocation strategy" problem the opposite way: move the choice of strategy out of the type and into a runtime pointer. `std::pmr::memory_resource` is an abstract base class — `do_allocate`, `do_deallocate`, `do_is_equal` — and any concrete allocation strategy is expressed by subclassing it. Every `std::pmr` container uses the single, uniform `std::pmr::polymorphic_allocator<T>`, which holds nothing but a `memory_resource*`; because that pointer's concrete target isn't part of the type, `std::pmr::vector<int>` is always the same type regardless of which resource backs a given instance — free to pass around, assign, return, no template gymnastics required. The price is paid on every allocation: a virtual call through that pointer, dispatched at runtime, instead of section 3's version, where the concrete allocator type is known at compile time and can be inlined away entirely. It's the same static-vs-dynamic-polymorphism tradeoff C++ programmers already navigate with virtual functions vs. templates, applied here to memory itself.

The standard library ships a few resources that map directly onto what's already been covered:

- **`monotonic_buffer_resource`** is section 3's arena, standardized: allocate forward only, release everything together, no individual reclamation. It even accepts an initial caller-supplied buffer (a stack `std::array`, say) with a fallback resource for overflow — the standard-library version of the `allow_fallback_` parameter.
- **`unsynchronized_pool_resource`** is closer to section 1's pool, generalized to many object sizes instead of one fixed type, managed as size-class "slabs."
- **`synchronized_pool_resource`** is the thread-safe version of the above — and the name says exactly what that costs: a lock, the same class of contention this entire post exists to avoid.

### The lifetime trap the standard itself warns about

`std::pmr::vector` looks exactly like an ordinary value type — return one by value and it seems as safe as returning any other `std::vector`. It isn't, and the reason is specific: a `polymorphic_allocator` only *points at* its `memory_resource`; it never owns it. If that resource is a local variable, returning the vector does nothing to extend the resource's lifetime:

```cpp
auto create_vec() -> std::pmr::vector<int> {
  auto resource = PrintingResource{};           // local, destroyed at scope exit
  auto vec = std::pmr::vector<int>{&resource};  // vec stores only &resource
  return vec;                                   // resource is destroyed here
}
auto vec = create_vec();
vec.emplace_back(1);  // undefined behavior
```

`vec` itself moves out cleanly — no deep copy, nothing about the return looks wrong. The danger is invisible at the call site precisely because `std::pmr::vector<int>` advertises the same value semantics as `std::vector<int>` without actually owning the thing its correctness depends on. The rule this forces is unglamorous but absolute: a `memory_resource`'s lifetime must outlive every container built on it — which usually means it has to live in a strictly outer scope, never inside the function that merely constructs and returns the container.

---

## 5. Putting It Together: Two Reference Implementations

Two shapes from the sections above are worth keeping as complete, reusable references: a fixed-type pool for objects with independent lifetimes, and an arena for a batch of objects that all get thrown away together. `std::pmr` isn't a third — it solves a type-compatibility problem, not a performance one, and paying a virtual call on every allocation makes it a worse default than either of these for something that's actually meant to sit on a hot path. Reach for it only when the flexibility is worth that specific cost.

Zooming out, every section above is really the same question asked again at a different layer: *where does this storage actually come from, and who's managing it?*
<svg viewBox="0 0 640 1180" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="From malloc/free's unpredictable latency, through Object Pool's v1 linear scan being superseded by v2's free list, through allocator-environment tuning, to the Arena's bump pointer, to the STL allocator and std::pmr — ending at memory strategy decoupled from container type" style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif">
  <style>
    .bg  { fill: #fbfaf7; }
    .ink { fill: #1c1b18; }
    .muted { fill: #6b6558; }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .boxN  { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .boxGone { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; stroke-dasharray: 4 3; opacity: 0.8; }
    .boxGo   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 2; }
    .edge     { stroke: #b3ab98; stroke-width: 1.6; fill: none; marker-end: url(#ahN2); }
    .edgeGone { stroke: #b3ab98; stroke-width: 1.4; fill: none; stroke-dasharray: 4 3; opacity: 0.75; marker-end: url(#ahN2); }
    .edgeGo   { stroke: #6f8f3f; stroke-width: 2; fill: none; marker-end: url(#ahGo2); }
    @media (prefers-color-scheme: dark) {
      .bg  { fill: #17161b; }
      .ink { fill: #e9e7ef; }
      .muted { fill: #a19caf; }
      .title { fill: #e9e7ef; }
      .boxN  { fill: #201f26; stroke: #3a3945; }
      .boxGone { fill: #2a2933; stroke: #47454f; }
      .boxGo   { fill: #33421f; stroke: #8fb257; }
      .edge     { stroke: #55525f; }
      .edgeGone { stroke: #55525f; }
      .edgeGo   { stroke: #8fb257; }
    }
  </style>
  <defs>
    <marker id="ahN2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ahGo2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#6f8f3f"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="640" height="1180" rx="10"/>
  <text class="title" x="20" y="26">Pool to pmr: the same question — where storage comes from —</text>
  <text class="title" x="20" y="42">answered five different ways</text>
  <rect class="boxN" x="180" y="56" width="280" height="56" rx="8"/>
  <text class="ink" x="320" y="80" font-size="14" font-weight="700" text-anchor="middle">malloc / free</text>
  <text class="muted" x="320" y="98" font-size="11" text-anchor="middle">unpredictable, variable latency</text>
  <path class="edge" d="M320,112 L320,154"/>
  <rect class="boxN" x="190" y="156" width="260" height="50" rx="8"/>
  <text class="ink" x="320" y="180" font-size="14" font-weight="700" text-anchor="middle">Object Pool</text>
  <text class="muted" x="320" y="197" font-size="11" text-anchor="middle">§1</text>
  <path class="edgeGone" d="M300,206 L170,246"/>
  <path class="edgeGo" d="M340,206 L470,246"/>
  <rect class="boxGone" x="40" y="248" width="240" height="64" rx="8"/>
  <text class="muted" x="160" y="272" font-size="12.5" font-weight="700" text-anchor="middle">v1 · linear scan</text>
  <text class="muted" x="160" y="290" font-size="10.5" text-anchor="middle">O(N) · superseded by v2</text>
  <rect class="boxGo" x="360" y="248" width="240" height="64" rx="8"/>
  <text class="ink" x="480" y="272" font-size="12.5" font-weight="700" text-anchor="middle">v2 · explicit free list</text>
  <text class="ink" x="480" y="290" font-size="10.5" text-anchor="middle">O(N) → O(1)</text>
  <path class="edgeGo" d="M460,312 L340,354"/>
  <rect class="boxN" x="170" y="356" width="300" height="64" rx="8"/>
  <text class="ink" x="320" y="380" font-size="14" font-weight="700" text-anchor="middle">intrusive free list</text>
  <text class="muted" x="320" y="398" font-size="10.5" text-anchor="middle">next lives inside T, no extra node</text>
  <path class="edge" d="M320,420 L320,450"/>
  <rect class="boxN" x="160" y="452" width="320" height="50" rx="8"/>
  <text class="ink" x="320" y="476" font-size="13.5" font-weight="700" text-anchor="middle">tightening allocator control</text>
  <text class="muted" x="320" y="493" font-size="11" text-anchor="middle">§2</text>
  <path class="edge" d="M300,502 L160,542"/>
  <path class="edge" d="M340,502 L480,542"/>
  <rect class="boxN" x="40" y="544" width="240" height="64" rx="8"/>
  <text class="ink" x="160" y="568" font-size="12.5" font-weight="700" text-anchor="middle">glibc tuning</text>
  <text class="muted" x="160" y="586" font-size="10" text-anchor="middle">M_MMAP_MAX=0 · M_TRIM_THRESHOLD=-1</text>
  <rect class="boxN" x="360" y="544" width="240" height="64" rx="8"/>
  <text class="ink" x="480" y="568" font-size="12.5" font-weight="700" text-anchor="middle">mlockall</text>
  <text class="muted" x="480" y="586" font-size="10" text-anchor="middle">locked into RAM · swappiness=0</text>
  <path class="edge" d="M180,608 L300,650"/>
  <path class="edge" d="M460,608 L340,650"/>
  <rect class="boxN" x="170" y="652" width="300" height="50" rx="8"/>
  <text class="ink" x="320" y="682" font-size="13.5" font-weight="700" text-anchor="middle">a stable memory environment</text>
  <path class="edge" d="M320,702 L320,738"/>
  <rect class="boxN" x="190" y="740" width="260" height="50" rx="8"/>
  <text class="ink" x="320" y="764" font-size="14" font-weight="700" text-anchor="middle">Arena Allocator</text>
  <text class="muted" x="320" y="781" font-size="11" text-anchor="middle">§3 · bump-pointer arena</text>
  <path class="edge" d="M320,790 L320,826"/>
  <rect class="boxN" x="170" y="828" width="300" height="56" rx="8"/>
  <text class="ink" x="320" y="852" font-size="14" font-weight="700" text-anchor="middle">bump pointer</text>
  <text class="muted" x="320" y="870" font-size="10.5" text-anchor="middle">only ever moves forward · O(1) alloc</text>
  <path class="edge" d="M320,884 L320,920"/>
  <rect class="boxN" x="150" y="922" width="340" height="50" rx="8"/>
  <text class="ink" x="320" y="946" font-size="13.5" font-weight="700" text-anchor="middle">STL Allocator</text>
  <text class="muted" x="320" y="963" font-size="10" text-anchor="middle">custom allocator · compile-time polymorphism</text>
  <path class="edge" d="M320,972 L320,1008"/>
  <rect class="boxN" x="190" y="1010" width="260" height="56" rx="8"/>
  <text class="ink" x="320" y="1034" font-size="14" font-weight="700" text-anchor="middle">std::pmr</text>
  <text class="muted" x="320" y="1052" font-size="10.5" text-anchor="middle">§4 · run-time polymorphism</text>
  <path class="edgeGo" d="M320,1066 L320,1100"/>
  <rect class="boxGo" x="90" y="1102" width="460" height="64" rx="8"/>
  <text class="ink" x="320" y="1126" font-size="14" font-weight="700" text-anchor="middle">memory strategy decoupled from container type</text>
  <text class="ink" x="320" y="1144" font-size="10.5" text-anchor="middle">"where memory comes from" and "how it's managed" are independent</text>
</svg>

### A Reference Object Pool

Sections 1 and 2 compose cleanly into one self-contained thing: a fixed-type pool with O(1) alloc/dealloc, backed by memory that's pre-allocated, pre-faulted, and locked before the hot path ever runs. One refinement beyond either version in section 1: instead of a separate `free_list_` array, the "next free slot" index lives *inside* the same slot as `T`, so a single allocation touches one cache line instead of two unrelated arrays.

```cpp
template <typename T>
class ObjectPool {
  struct Slot {
    alignas(T) unsigned char storage[sizeof(T)];  // T lives here once constructed
    std::size_t next_free;                        // free-list link, co-located with T
  };
  static constexpr std::size_t kInvalid = static_cast<std::size_t>(-1);

  Slot* slots_;
  std::size_t capacity_;
  std::size_t free_head_ = 0;

 public:
  explicit ObjectPool(std::size_t capacity) : capacity_(capacity) {
    std::size_t bytes = sizeof(Slot) * capacity_;
    slots_ = static_cast<Slot*>(std::aligned_alloc(alignof(Slot), bytes));
    if (!slots_) throw std::bad_alloc{};

    mlock(slots_, bytes);            // never swapped out (check the return value in production —
    std::memset(slots_, 0, bytes);   // needs CAP_IPC_LOCK / RLIMIT_MEMLOCK); memset pre-faults every page now

    for (std::size_t i = 0; i < capacity_; ++i)
      slots_[i].next_free = (i + 1 < capacity_) ? i + 1 : kInvalid;
  }

  ~ObjectPool() {
    munlock(slots_, sizeof(Slot) * capacity_);
    std::free(slots_);
  }

  ObjectPool(const ObjectPool&) = delete;
  ObjectPool& operator=(const ObjectPool&) = delete;

  template <typename... Args>
  T* allocate(Args&&... args) {
    if (free_head_ == kInvalid) return nullptr;      // pool exhausted — no exception on the hot path
    Slot& slot = slots_[free_head_];
    free_head_ = slot.next_free;                     // O(1): the next slot was already known
    return ::new (slot.storage) T(std::forward<Args>(args)...);
  }

  void deallocate(T* obj) {
    obj->~T();
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));
    std::size_t index = slot - slots_;
    slot->next_free = free_head_;                    // push back onto the free-list head
    free_head_ = index;
  }
};
```

What each piece contributed, concretely: the `next_free`-inside-`Slot` layout and the head-pointer swap are section 1's free list; `aligned_alloc` + `mlock` + the eager `memset` are section 2's "never let the kernel take it back, and never fault on first touch."

### A Reference Arena

The pool above hands out one type, individually, with independent lifetimes. An arena is for the opposite shape: a batch of allocations — possibly different sizes, possibly different types — that all get released together. Same startup treatment as the pool (one allocation, `mlock`, `memset` to pre-fault), but the allocation logic itself is simpler still: no free list to maintain at all, just a running offset.

```cpp
class Arena {
  unsigned char* base_;
  std::size_t capacity_;
  std::size_t used_ = 0;
  bool allow_malloc_fallback_;

 public:
  explicit Arena(std::size_t capacity, bool allow_malloc_fallback = false)
      : capacity_(capacity), allow_malloc_fallback_(allow_malloc_fallback) {
    base_ = static_cast<unsigned char*>(
        std::aligned_alloc(alignof(std::max_align_t), capacity_));
    if (!base_) throw std::bad_alloc{};

    mlock(base_, capacity_);           // same locking + pre-faulting as the pool
    std::memset(base_, 0, capacity_);  // (check mlock's return value in production)
  }

  ~Arena() {
    munlock(base_, capacity_);
    std::free(base_);
  }

  Arena(const Arena&) = delete;
  Arena& operator=(const Arena&) = delete;

  void* allocate(std::size_t size, std::size_t alignment = alignof(std::max_align_t)) {
    std::size_t aligned_used = (used_ + alignment - 1) & ~(alignment - 1);
    if (aligned_used + size > capacity_) {
      return allow_malloc_fallback_ ? std::malloc(size) : nullptr;  // arena exhausted
    }
    void* ptr = base_ + aligned_used;
    used_ = aligned_used + size;
    return ptr;
  }

  void reset() noexcept { used_ = 0; }  // the only way to reclaim — bulk, not per-allocation
};
```

`allocate()` is the whole bump-allocator idea in four lines: round the current offset up to the requested alignment, check it still fits, advance the offset, return the old one. No search, no list to maintain — the "next free position" is always just `used_`. `reset()` is the only reclaim path, matching the arena's whole premise: it doesn't track individual allocations, so it can't release one. One deliberate simplification versus section 3's multi-block design: a single fixed-capacity buffer rather than a chain of pre-reserved blocks — simpler to get right, at the cost of a hard capacity ceiling instead of the ability to keep growing. `allow_malloc_fallback_` is the same escape hatch section 3's arena had for exactly that ceiling.

Pick the pool when objects have independent lifetimes and get freed one at a time. Pick the arena when a whole batch — everything touched while handling one tick, one order, one request — shares a single lifetime and gets thrown away as a unit.

---

## Recap

1. **The problem was never speed — it's variance.** Every cost this post removes (a lock, a syscall, a page fault, a virtual dispatch) is fine on average; what's intolerable is not knowing, per request, how long it will take.
2. **An index-based free list is O(1) because it's maintained on every call, not searched on demand** — and it is not an intrusive list; the `next` pointer lives in a parallel array, not inside `T` itself.
3. **`mlockall` alone has a hole: `munmap` tears down the whole mapping, lock included.** `M_MMAP_MAX`, `M_TRIM_THRESHOLD`, and `M_ARENA_MAX` each close a different path back to the kernel.
4. **`isolcpus` protects scheduling, not TLB shootdowns.** A cold thread in the same process can still interrupt a perfectly isolated hot core, because the shootdown targets the address space (`mm_cpumask`), not the scheduling class.
5. **An arena is strictly cheaper than a free list — pure pointer advance, no list maintenance — at the cost of only supporting bulk release.** Pre-faulting with `memset` closes the one gap `mlock` alone leaves: the first write to a fresh page.
6. **`std::pmr` trades section 3's compile-time speed for a uniform, runtime-flexible type** — the same virtual-vs-template tradeoff C++ already has elsewhere, applied to allocation. Its sharpest edge: a `polymorphic_allocator` only points at its resource, so returning a `pmr::vector` built on a local resource is a dangling pointer wearing a value type's clothes.
7. **Two reference shapes cover the practical cases: a pool for independent lifetimes, an arena for a batch released together.** Co-locating the free-list link with `T` turns two cache-line touches into one; the arena drops list maintenance entirely — just a running offset. `std::pmr`'s per-allocation virtual dispatch is why it isn't a third reference implementation here.
