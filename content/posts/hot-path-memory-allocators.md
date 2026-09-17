---
title: "Trading System Notes #3: Nothing Happens for the First Time on the Hot Path — Object Pools, Locked Pages, and Polymorphic Allocators"
date: 2026-09-17
slug: "hot-path-memory-allocators"
description: "Why malloc/free's real problem is variance, not speed — and four increasingly general ways to guarantee nothing on the hot path is happening for the first time: an O(1) free-list pool, locked and pre-faulted pages, a bump-allocating arena behind a custom STL allocator (plus a real memory-corruption bug found in the reference implementation), and std::pmr's runtime alternative to all three. Closes with a reference object pool that folds the first two techniques into one class."
summary: "Every technique in this post does the same thing at a different layer: move an uncertain, kernel-involving operation off the hot path and force it to happen once, upfront, before it can ambush a single request. An object pool replaces malloc's variable-cost search with an always-O(1) free list. mlockall and careful mallopt tuning stop the kernel from quietly taking pages back — and pre-faulting closes the one gap mlock alone leaves open. A hand-rolled arena allocator makes the STL itself cooperate, at the cost of a real bug this post walks through in detail: a memory-layout mismatch between two functions that silently corrupts a neighboring block's metadata, invisible in the shipped demo. std::pmr solves the same STL-cooperation problem the standard library's way — trading compile-time speed for runtime flexibility."
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

<!--
╔══════════════════════════════════════════════════════════════════╗
║  🖼  ILLUSTRATION  ——  Nothing happens for the first time         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Academic graphite pencil illustration on clean white paper.     ║
║  16:9. Precise technical linework, careful cross-hatching for    ║
║  shading and depth. Monochrome graphite only — no color, no      ║
║  watercolor, no graph-paper grid. Scientific-journal /           ║
║  textbook figure. NOT cartoon, NOT colorful.                     ║
║                                                                  ║
║  Topic: four different techniques for making sure nothing on a   ║
║  latency-critical path is ever being decided, allocated, or      ║
║  faulted in for the first time — each one prepared in advance.   ║
║                                                                  ║
║  Main metaphor: a classical stone colonnade / arcade with four   ║
║  plinths standing between the columns, each plinth holding one   ║
║  precisely rendered mechanical object, left to right in a row.   ║
║                                                                  ║
║  Layout: arcade / colonnade of four objects in sequence,         ║
║  left to right, matched visual weight.                           ║
║                                                                  ║
║  Objects and labels:                                             ║
║   - plinth 1: a wooden pegboard with a short chain of numbered   ║
║     pegs linked in sequence, one peg drawn slightly raised as    ║
║     "next" — labeled "OBJECT POOL" / "free list, always O(1)"    ║
║   - plinth 2: a heavy iron strongbox bolted to the stone floor   ║
║     with a padlock and a taut chain — labeled "LOCKED PAGES" /   ║
║     "mlock + pre-faulted"                                        ║
║   - plinth 3: a large paper scroll unrolled across two wooden    ║
║     spindles, a drafting pen resting partway along the sheet —   ║
║     labeled "ARENA" / "bump pointer, one scroll at a time"       ║
║   - plinth 4: a rotating brass selector dial wired by a thin     ║
║     cable to a small unmarked junction box beside it — labeled   ║
║     "POLYMORPHIC RESOURCE" / "chosen at runtime"                 ║
║   - thin ruled banner spanning above all four plinths:           ║
║     "prepared before the hot path ever runs"                     ║
║                                                                  ║
║  Title (top, large): "Nothing Happens for the First Time on      ║
║  the Hot Path"                                                   ║
║  Subtitle: "Four ways to make sure the work was already done"    ║
║  Footer caption: "Prepared, Not Fast."                            ║
║                                                                  ║
║  All text in English. No Chinese characters. No color fills.     ║
║  No gradients. Monochrome graphite only.                         ║
╚══════════════════════════════════════════════════════════════════╝
-->

![Four plinths in a stone colonnade, each holding a mechanical object representing a different allocator technique, under the banner "prepared before the hot path ever runs"](/images/hot-path-allocators/four-allocators.png)

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

Closing that hole takes three separate `mallopt` calls, each blocking a different path back to the kernel:

- **`M_MMAP_MAX = 0`** — forbid the mmap path entirely. Every allocation, regardless of size, goes through the heap; `free()` becomes pure bookkeeping and never calls `munmap`.
- **`M_TRIM_THRESHOLD = -1`** — the same idea applied to the heap itself. By default, glibc shrinks the heap back toward the OS via `sbrk` once enough contiguous free space accumulates at the top; this disables that, so a large chunk of freed space at the top of the heap is never handed back.
- **`M_ARENA_MAX = 1`** — a different axis: multiple worker arenas are themselves backed by additional `mmap`-obtained regions. Forcing a single arena (allocation only happens at startup anyway, so the concurrency benefit of multiple arenas is moot here) removes those extra mmap sources up front.

### The tax that isolcpus can't hide you from

Any page-table change — `munmap`, `mprotect`, or the kernel's own transparent-huge-page background compaction — forces a **TLB shootdown**: the core making the change doesn't know which other cores have cached the now-stale translation, so it broadcasts an inter-processor interrupt (IPI) to every core that has recently run the same process's address space. Each one has to stop, trap into the kernel, invalidate the affected TLB entry, and resume — microsecond-scale, and it scales with how many cores share that address space.

The sharp, easy-to-get-wrong point: **`isolcpus` does not protect against this.** `isolcpus` operates at the scheduler layer — it controls whether the scheduler will place *tasks* on a given core. A TLB shootdown is a hardware interrupt, delivered based on which cores are recorded in the kernel's `mm_cpumask` for that address space — a completely different mechanism that the scheduler has no say over. A perfectly isolated, pinned hot-core thread can still get interrupted mid-flight by a *cold* thread in the same process calling `munmap` or `mprotect`, because both threads share the same `mm_struct`, and the shootdown targets the address space, not the scheduling class. This is the deeper reason THP and automatic NUMA balancing get disabled on tuned systems, beyond "unpredictable latency from background compaction" — both routinely rewrite page tables, and every rewrite is a shootdown that reaches cores the scheduler was told never to touch.

---

## 3. An Arena Behind the STL — and a Bug Hiding in Plain Sight

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

### The bug

The reference implementation this section is based on has a genuine memory-corruption bug, and it's worth tracing through carefully because nothing about running its own demo reveals it.

The constructor sizes the backing buffer as `(header_size + block_size) * num_blocks` — a size calculation that implicitly assumes each block's header sits immediately before its own data, back to back: `header0, data0, header1, data1, …`. But the code that actually *addresses* each block, `arena_mem_.blocks[i]`, is a plain array subscript on a `MemoryBlock*` — and C++ array indexing advances by `sizeof(MemoryBlock)` per step, i.e. by `header_size` alone, never by `header_size + block_size`. That means the headers are actually laid out packed together at the very front of the buffer, one right after another — a different, incompatible picture from the one the size calculation assumed.

`MemoryBlock::data()` then computes its own block's data address as `this + 1` — "one header-width past myself." Under the packed-headers layout that `blocks[i]` actually produces, that expression lands **exactly on the next block's header**. Concretely, with an illustrative `header_size = 64` and 4 blocks:

| block `i` | address of `blocks[i]` (packed) | `data()` = `this + 1` |
|---|---|---|
| 0 | 0 | **64 — exactly `blocks[1]`'s address** |
| 1 | 64 | **128 — exactly `blocks[2]`'s address** |
| 2 | 128 | **192 — exactly `blocks[3]`'s address** |

Writing "into block 0's data region" is, in reality, writing into block 1's `used`/`capacity`/`is_active` fields. Block 1's writes land on block 2's header, and so on down the chain.

<svg viewBox="0 0 760 420" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="MemoryBlock::data() computes this plus one, which lands exactly on the next block's header instead of this block's own data region, silently corrupting neighboring metadata">
  <style>
    .bg    { fill: #fbfaf7; }
    .panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .ink   { fill: #1c1b18; }
    .muted { fill: #6b6558; }
    .hdr   { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .data  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .hit   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.8; }
    .arrow { stroke: #8a8474; stroke-width: 2; fill: none; marker-end: url(#ah); }
    .bad   { stroke: #c15b3f; stroke-width: 2.2; fill: none; marker-end: url(#ah2); }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .lbl   { fill: #3a372f; font-size: 11px; }
    .cap   { fill: #6b6558; font-size: 10.5px; }
    .gap   { fill: #c15b3f; font-size: 11px; font-weight: 700; }
    @media (prefers-color-scheme: dark) {
      .bg    { fill: #17161b; }
      .panel { fill: #201f26; stroke: #3a3945; }
      .ink   { fill: #e9e7ef; }
      .muted { fill: #a19caf; }
      .hdr   { fill: #2a2933; stroke: #47454f; }
      .data  { fill: #23262c; stroke: #3f4650; }
      .hit   { fill: #4a2f2c; stroke: #8f5a4c; }
      .arrow { stroke: #9a9384; }
      .bad   { stroke: #e0795b; }
      .title { fill: #e9e7ef; }
      .lbl   { fill: #d7d3c8; }
      .cap   { fill: #a19caf; }
      .gap   { fill: #e0795b; }
    }
  </style>
  <defs>
    <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="760" height="420" rx="10"/>
  <text class="title" x="24" y="30">this + 1 lands on the next block's header, not this block's own data</text>

  <text class="muted" x="24" y="58" font-size="12" font-weight="700">What blocks[i] indexing actually builds (header_size = 64, illustrative)</text>
  <rect class="hdr" x="24"  y="70" width="64" height="46" rx="4"/>
  <rect class="hdr" x="88"  y="70" width="64" height="46" rx="4"/>
  <rect class="hdr" x="152" y="70" width="64" height="46" rx="4"/>
  <rect class="hdr" x="216" y="70" width="64" height="46" rx="4"/>
  <rect class="data" x="280" y="70" width="456" height="46" rx="4"/>
  <text class="lbl" x="38"  y="98">H0</text>
  <text class="lbl" x="102" y="98">H1</text>
  <text class="lbl" x="166" y="98">H2</text>
  <text class="lbl" x="230" y="98">H3</text>
  <text class="cap" x="292" y="98">data_start — never actually addressed per block</text>
  <text class="cap" x="18" y="130" font-size="10" text-anchor="middle">0</text>
  <text class="cap" x="88" y="130" font-size="10" text-anchor="middle">64</text>
  <text class="cap" x="152" y="130" font-size="10" text-anchor="middle">128</text>
  <text class="cap" x="216" y="130" font-size="10" text-anchor="middle">192</text>
  <text class="cap" x="280" y="130" font-size="10" text-anchor="middle">256</text>

  <text class="muted" x="24" y="168" font-size="12" font-weight="700">What MemoryBlock::data() actually returns: this + 1 (one header-width past self)</text>

  <rect class="hit" x="24"  y="182" width="64" height="46" rx="4"/>
  <rect class="hit" x="88"  y="182" width="64" height="46" rx="4"/>
  <rect class="hit" x="152" y="182" width="64" height="46" rx="4"/>
  <rect class="hdr" x="216" y="182" width="64" height="46" rx="4"/>
  <text class="lbl" x="30"  y="210" font-size="10">H0.data()</text>
  <text class="lbl" x="94"  y="210" font-size="10">H1.data()</text>
  <text class="lbl" x="158" y="210" font-size="10">H2.data()</text>

  <path class="bad" d="M56 182 C 56 150, 120 150, 120 116"/>
  <path class="bad" d="M120 182 C 120 150, 184 150, 184 116"/>
  <path class="bad" d="M184 182 C 184 150, 248 150, 248 116"/>

  <text class="gap" x="24" y="250">block[0].data() returns H1's own address —</text>
  <text class="gap" x="24" y="268">writing "into block 0" overwrites H1's used / capacity / is_active.</text>

  <rect class="panel" x="24" y="292" width="712" height="108" rx="8"/>
  <text class="title" x="40" y="316" font-size="12.5">Why the shipped demo never catches it</text>
  <text class="cap" x="40" y="338" font-size="11">total_memory_size was computed as if header and data were interleaved per block —</text>
  <text class="cap" x="40" y="354" font-size="11">but blocks[i] indexing and data_start both assume every header is packed up front.</text>
  <text class="cap" x="40" y="370" font-size="11" font-weight="700">data() matches neither model. The demo's own allocations are too small to ever roll</text>
  <text class="cap" x="40" y="386" font-size="11" font-weight="700">over to a second block, so the corrupted header gets written — but never read.</text>
</svg>

> Figure: the size calculation, the array indexing, and `data()` each encode a different, mutually inconsistent picture of the same buffer. Only the middle one (packed headers) matches what the compiler actually generates for `blocks[i]`, and `data()` was never updated to agree with it. A demo that allocates a handful of ints and short strings never forces a second block into use, so the corrupted header sits there, unread and undetected — a passing demo run is evidence about the inputs you tried, not about the code.

The fix doesn't need a new idea, just using one that was already computed and quietly ignored: `data_start` is calculated correctly at construction time and never referenced again anywhere else in the class. Give each block a `data_ptr` field, set once, at the same point every other per-block field is initialized:

```cpp
char* data_ptr;
char* data() { return data_ptr; }   // no more per-call this+1 guesswork

// in the per-block initialization loop:
block->data_ptr = arena_mem_.data_start + i * block_size;
```

Each block's real address is computed once, at startup — matching this post's opening thesis exactly, just applied one layer deeper than mlock or pre-faulting: the *address arithmetic itself* is now a fixed fact established before the hot path runs, not something recomputed (incorrectly) on every call.

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

## 5. Putting It Together: A Reference Object Pool

Sections 1 and 2 compose cleanly into one self-contained thing worth actually keeping around: a fixed-type pool with O(1) alloc/dealloc, backed by memory that's pre-allocated, pre-faulted, and locked before the hot path ever runs. One refinement beyond either version in section 1: instead of a separate `free_list_` array, the "next free slot" index lives *inside* the same slot as `T`, so a single allocation touches one cache line instead of two unrelated arrays.

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

What each earlier section contributed, concretely: the `next_free`-inside-`Slot` layout and the head-pointer swap are section 1's free list; `aligned_alloc` + `mlock` + the eager `memset` are section 2's "never let the kernel take it back, and never fault on first touch"; the missing piece from section 3's bug — one function's address math disagreeing with another's — has no equivalent failure mode here, because `Slot` is one struct with one layout, not a separately-computed header region and data region that have to agree with each other.

This pool is *not* what sections 3 and 4 are for, on purpose. It hands out exactly one type, individually, with independent lifetimes — reach for the arena (section 3) or `std::pmr` (section 4) instead when the actual need is "let arbitrary STL containers avoid the heap" or "release a whole batch of unrelated allocations at once." Forcing all four techniques into a single class would trade away the property that makes each one fast in its own situation.

---

## Recap

1. **The problem was never speed — it's variance.** Every cost this post removes (a lock, a syscall, a page fault, a virtual dispatch) is fine on average; what's intolerable is not knowing, per request, how long it will take.
2. **An index-based free list is O(1) because it's maintained on every call, not searched on demand** — and it is not an intrusive list; the `next` pointer lives in a parallel array, not inside `T` itself.
3. **`mlockall` alone has a hole: `munmap` tears down the whole mapping, lock included.** `M_MMAP_MAX`, `M_TRIM_THRESHOLD`, and `M_ARENA_MAX` each close a different path back to the kernel.
4. **`isolcpus` protects scheduling, not TLB shootdowns.** A cold thread in the same process can still interrupt a perfectly isolated hot core, because the shootdown targets the address space (`mm_cpumask`), not the scheduling class.
5. **An arena is strictly cheaper than a free list — pure pointer advance, no list maintenance — at the cost of only supporting bulk release.** Pre-faulting with `memset` closes the one gap `mlock` alone leaves: the first write to a fresh page.
6. **A demo passing tells you about the inputs you tried, not about the code.** The reference arena's `data()` computes the wrong address for every block but one, silently corrupting neighboring headers — invisible because the shipped demo never allocates enough to roll over to a second block.
7. **`std::pmr` trades section 3's compile-time speed for a uniform, runtime-flexible type** — the same virtual-vs-template tradeoff C++ already has elsewhere, applied to allocation. Its sharpest edge: a `polymorphic_allocator` only points at its resource, so returning a `pmr::vector` built on a local resource is a dangling pointer wearing a value type's clothes.
8. **Sections 1 and 2 compose into one reusable pool; sections 3 and 4 solve a different problem and don't merge in.** Co-locating the free-list link with `T` turns two cache-line touches into one — the kind of refinement that falls out naturally once the underlying mechanism is actually understood, not copied.

---

*The knowledge skeleton for this post — the two object-pool implementations, the mallopt/mlockall tuning, the TLB shootdown mechanism, the pinned-arena allocator, and std::pmr — comes from a close reading of [`zzxscodes/trading-system-notes`](https://github.com/zzxscodes/trading-system-notes). The memory-corruption bug in section 3, its trace-through, and its fix are not from that source; they turned up during that close reading and are original to this post.*
