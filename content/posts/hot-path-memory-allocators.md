---
title: "Trading System Notes #3: Memory Pools and Allocators"
date: 2026-09-17
lastmod: 2026-11-10
slug: "hot-path-memory-allocators"
description: "Why malloc/free's real problem is variance, not speed — and four increasingly general ways to guarantee nothing on the hot path happens for the first time: an O(1) free-list object pool, a bump-pointer arena behind a custom STL allocator, std::pmr as the runtime version of the same idea, and the layer underneath all three: pre-faulted, locked pages that glibc is not allowed to hand back to the kernel. With reference implementations of the pool and the arena, and the lock-free free stack and ABA of a pool shared by several threads."
summary: "Every technique in this post does the same thing at a different layer: move an uncertain, kernel-involving operation off the hot path and force it to happen once, upfront, before it can ambush a single request. An object pool replaces malloc's variable-cost search with an always-O(1) free list. mlockall and careful mallopt tuning stop the kernel from quietly taking pages back — and pre-faulting closes the one gap mlock alone leaves open. A hand-rolled arena allocator makes the STL itself cooperate with a custom allocator backed by bump-pointer memory. std::pmr solves the same STL-cooperation problem the standard library's way — trading compile-time speed for runtime flexibility."
chapter: 1
categories: [Systems]
tags: [cpp, memory-pool, allocator, mlock, tlb-shootdown, pmr, hft, low-latency, stl]
toc: true
homepage: false
---

`malloc` and `free` are not slow. Call them a thousand times in a tight loop and the average looks perfectly fine. The problem HFT code has with them isn't the mean — it's the **tail**, and the tail depends on state you don't control. glibc hands out per-thread arenas to avoid lock contention, but once there are more threads than arenas, two threads fight over one arena's lock. A request the current arena can't satisfy may mean a fresh `brk` or `mmap` call into the kernel. Freed memory goes into size-class bins that have to be walked and possibly coalesced, and how long that takes depends on the fragmentation history of everything the heap has seen. None of these costs is fixed; all of them depend on "what has this process been doing so far" — exactly the question a hot path can't afford to ask.

> **Why the hot path doesn't use malloc: fast when it's fast, a hundred times slower when it isn't**
> malloc looks in cheap places first and expensive ones later, and which layer it reaches depends on what this process has allocated and freed before ([where one new goes](/zh/ref/new-malloc-page-fault/), Chinese only for now):
> 1. **tcache hit**: the thread's own small list, touched by no other thread, no lock, about 10–20 ns.
> 2. **The arena's free lists**: take the arena's lock, maybe split or coalesce neighbouring free chunks, tens of ns to one or two hundred ns; with many threads, they also fight over the lock.
> 3. **brk / mmap into the kernel**: not enough free chunks at hand, one system call of a few hundred ns to 1 µs.
> 4. **First write to the new pages**: in step 3 the kernel only recorded a range of addresses; each 4 KiB page faults on its first write, about 0.5–2 µs each; the first pass over a large new block costs tens of µs to ms.
>
> - **On average it isn't slow**: most calls stop at layer 1.
> - **The P99 spikes come from layers 3 and 4**: there is no way to know in advance which call will fall that far.
> - **free can push the next call back to layer 3**: glibc releases large blocks straight back to the kernel with `munmap`, so the next request goes into the kernel again.
> - **Pools and arenas move layers 2–4 to startup**: take everything at once at startup, write the whole block once to fault every page in, and lock it.
> - **Hot-path allocation is then equally fast every time**: all that is left is moving a list head or a pointer.

> **Signs it's time for an object pool or an arena**
> - **The median is fine, P99 has spikes**: at the moments of the spikes perf shows page faults (`page-faults`) or `brk`/`mmap` system calls, so the hot path is asking the kernel for memory.
> - **The hot path keeps doing new and delete on objects of the same size**: orders or messages, for example; use an object pool (Part 1), O(1) to take and to return.
> - **A batch of objects lives and dies together**: one trading day's market data, the temporary data of one request; use an arena (Part 2), allocate forward only and free the whole block at the end.
> - **Several threads allocate at once, and malloc's lock shows up in perf**: one pool per thread, or the lock-free free stack of Part 5; read the box in 5.1 first to decide whether you really need to share one pool.

Everything in this post is a variation on one fix: find the operation whose cost depends on first touch, contention or fragmentation, and **move it to a point in the program's life where you don't care how long it takes** — usually startup. Parts 1 to 3 move the allocation itself: an object pool handles one type allocated and freed one at a time, an arena handles a batch of objects used up and thrown away together, and `std::pmr` trades the compile-time type for runtime flexibility. Part 4 goes one layer down, to the memory underneath all three allocators: its pages must be faulted in and locked at startup, and nothing in the process may hand pages back to the kernel. Parts 1 and 2 each end with a reference implementation you can use as is; Part 5 covers the lock-free version for several threads allocating from one pool, and ABA.

---

## 1. The Object Pool: Allocate a Batch of Slots for One Type Up Front, Take One When Needed, Return It When Done {#pool}

**Object pool**: at startup, allocate a fixed number of slots for one type `T` at once; on the hot path, allocating means taking a free slot and freeing means putting it back, with no call to `malloc`. It is used for objects like orders and market-data messages, whose number has an upper bound and which are created and destroyed over and over.

### 1.1 Scanning for a Free Slot: The Worst Case Walks the Whole Pool {#scan-pool}

The key is the step "find the next free slot": **it has to be the same few instructions every time, regardless of how the pool has been used before.** The most direct version gives each slot a "free or not" flag and, after each allocation, scans forward to find the next free slot for next time.

```cpp
struct ObjectBlock {
  T    object_;
  bool is_free_ = true;
};
std::vector<ObjectBlock> store_;
std::size_t next_free_index_ = 0;   // the slot the next allocation uses

T* allocate() {
  ObjectBlock& b = store_[next_free_index_];
  b.is_free_ = false;               // placement-construct into b.object_, omitted
  // find a free slot for next time: scan forward, wrap to the start at the end (pool-full handling omitted)
  std::size_t i = next_free_index_;
  do {
    i = (i + 1) % store_.size();
  } while (!store_[i].is_free_ && i != next_free_index_);
  next_free_index_ = i;
  return &b.object_;
}
```

How far it scans depends on how the free slots are spread over the pool:

- **Objects are freed in the order they were allocated** (first in, first out): the slot right after the current position is free, and the scan stops after one step.
- **Objects are held for different lengths of time**: free slots are scattered over the pool, and one scan can walk most of it, O(n) in the worst case.

**How long the scan takes depends on how the pool has been used before**, which is the same disease as `malloc`: the cost depends on history, and the tail latency can't be predicted. The system call into the kernel is gone; the uncertainty is not.

### 1.2 Free List: The Next Free Slot Is Always Kept at the List Head {#free-list}

The fix is not to search: chain all free slots into a list, allocate from the head, and free back onto the head. "Which slot is free next" is always sitting in `head_`, ready to use.

```cpp
T*           objects_;     // capacity slots, pointing at memory with no objects constructed yet
std::size_t* free_list_;   // free_list_[i]: while slot i is free, the slot after it in the list
std::size_t  head_;        // the first free slot; kInvalid means the pool is used up
static constexpr std::size_t kInvalid = static_cast<std::size_t>(-1);

T* allocate() {
  if (head_ == kInvalid) return nullptr;
  std::size_t i = head_;
  head_ = free_list_[i];                // move the head to the next free slot
  return ::new (&objects_[i]) T();
}

void deallocate(T* p) {
  std::size_t i = static_cast<std::size_t>(p - objects_);
  p->~T();
  free_list_[i] = head_;                // put this slot at the front of the list
  head_ = i;
}
```

The list is chained with array indices, not pointers: `free_list_[i]` holds the index of the next free slot. A walk through it with 4 slots:

| Operation | Taken or returned | `head_` | Free list |
|---|---|---|---|
| Startup | | 0 | 0 → 1 → 2 → 3 |
| `allocate()` | slot 0 | 1 | 1 → 2 → 3 |
| `allocate()` | slot 1 | 2 | 2 → 3 |
| `deallocate(slot 0)` | slot 0 | 0 | 0 → 2 → 3 |
| `allocate()` | slot 0 | 2 | 2 → 3 |

**Allocation and freeing are each one read and one write, independent of how many free slots there are and where they are.** The list is last in, first out, which brings a side benefit: the slot returned most recently is the first to be handed out again, and it is most likely still in cache.

### 1.3 Where the Next Free Index Lives: a Separate Array, the Same Slot, or the Object's Own Memory {#free-link-layout}

In 1.2, `free_list_` is a separate array alongside `objects_`, and `T` has no idea it is linked into a list; this is called **non-intrusive**. The index can live elsewhere too, and each of the three layouts has a cost:

| Where the index lives | Cache lines one allocation touches | Extra memory | Cost |
|---|---|---|---|
| A separate array (1.2) | Two: `free_list_[i]` and `objects_[i]` are not together | 8 bytes per slot | One more chance of a cache miss per allocation |
| In the same slot as the object (1.4) | One when `T` is small | 8 bytes per slot | None |
| The object's own memory, i.e. **intrusive** (`union`) | One | 0 | Requires `sizeof(T) ≥ 8`; an object written after it was freed (use-after-free) corrupts the list directly, which is very hard to track down |

Intrusive works because **a free slot holds no object**: that memory is idle anyway, so it can hold the index of the "next free slot"; on allocation the index is read out first, and then `T` is constructed at the same address, overwriting it.

> **Where to put the index: by default, in the same slot**
>
> - **The usual case**: in the same slot as the object (the layout in 1.4); one allocation touches only one cache line, and the code stays clear.
> - **Many slots, tight memory, and `T` is at least 8 bytes**: go intrusive and save 8 bytes per slot.
> - **The objects must be packed as one `T` array** (for example, to walk all objects in array order): only a separate array works.


### 1.4 Reference Implementation: An Object Pool You Can Use As Is {#ref-pool}

The pool below puts the free list together with the startup treatment of Part 4 (4.1 pre-faulting, 4.2 page locking):

- **At startup it takes all its memory at once, locks it and faults it in**: `aligned_alloc` allocates `capacity` slots in one go, `mlock` locks them, `memset` writes every page once (4.1, 4.2).
- **Free slots are chained into one list, and allocation and freeing only touch the head**: `free_head_` is the index of the first free slot, and each free slot's `next_free` records the next one. Allocation takes the head off; freeing puts the slot back at the head (1.2).
- **The "next free slot" lives in the same slot as the object**: the second layout in the table of 1.3. `next_free` is inside `Slot`, so reading `next_free` and then constructing `T` touch the same slot, usually the same cache line.

```cpp
template <typename T>
class ObjectPool {
  struct Slot {
    alignas(T) unsigned char storage[sizeof(T)];  // T lives here once constructed
    std::size_t next_free;                        // while free: index of the next free slot
  };
  static constexpr std::size_t kInvalid = static_cast<std::size_t>(-1);

  Slot* slots_;
  std::size_t capacity_;
  std::size_t free_head_;                         // index of the first free slot

 public:
  explicit ObjectPool(std::size_t capacity)
      : capacity_(capacity), free_head_(capacity ? 0 : kInvalid) {
    std::size_t bytes = sizeof(Slot) * capacity_;
    slots_ = static_cast<Slot*>(std::aligned_alloc(alignof(Slot), bytes));
    if (!slots_) throw std::bad_alloc{};
    if (mlock(slots_, bytes) != 0) {
      // no CAP_IPC_LOCK or over RLIMIT_MEMLOCK: log it; the memset below still faults every page in
    }
    std::memset(slots_, 0, bytes);
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
    if (free_head_ == kInvalid) return nullptr;   // pool used up: no exception on the hot path
    Slot& slot = slots_[free_head_];
    free_head_ = slot.next_free;                  // take the head off
    return ::new (slot.storage) T(std::forward<Args>(args)...);
  }

  void deallocate(T* obj) {
    obj->~T();
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));
    slot->next_free = free_head_;                 // put it back at the head
    free_head_ = static_cast<std::size_t>(slot - slots_);
  }
};
```

**When the pool is used up, `allocate` returns `nullptr` instead of throwing**: on the hot path the caller decides whether to take a slow path or drop the message. `std::aligned_alloc` requires the byte count to be a multiple of the alignment; `sizeof(Slot)` is always a multiple of `alignof(Slot)`, so that holds here automatically.

---

## 2. The Arena: A Batch of Objects Used Up and Thrown Away Together, Allocation Down to One Addition {#arena}

An object pool hands out one type `T`, allocated and returned one at a time. The hot path has another pattern too: handling one tick needs a batch of temporary objects of different sizes and types, such as the buffers of a few `std::vector`s and `std::string`s, all thrown away once the tick is done. Giving every kind of object its own pool is not practical; the arena is made for this case.

### 2.1 A Batch of Objects That Live and Die Together: A Pointer That Only Moves Forward, Reclaimed Only by Rewinding the Whole Block {#bump}

1. **The arena tracks only one number: how many bytes of the block are already used (`used`)**
   - **Allocation in three steps**: round `used` up to the requested alignment; check whether `used + size` still fits in `capacity`; if it does, move `used` past this block and return the old position.
   - **No search**: the next free position is always wherever the pointer is now; there is nothing to look for.
   - **Even cheaper than Part 1's free list**: not even a list head to change, just one addition.
   - **When a block fills up**: move on to the next pre-reserved block the same way.
2. **The price is that one allocation can't be freed on its own**
   - **Why**: the arena doesn't record where each allocation starts and ends, so there is nothing to look up even if you wanted to return one.
   - **There is only one way to reclaim**: `reset()`, which rewinds `used` to 0 and reuses the whole block from the start.
3. **So choose by object lifetime**
   - **A batch of objects that live and die together** (all temporary objects allocated during one tick): use an arena.
   - **Staggered lifetimes**: still use Part 1's pool.

### 2.2 STL Containers Go to the Global Heap by Default: Wrap the Arena as an Allocator Whose deallocate Deliberately Does Nothing {#stl-allocator}

1. **Pain point: hot-path code wants ordinary `std::vector`s and `std::string`s**, but by default they get memory from the global heap, i.e. from `malloc`.
2. **Fix: wrap the arena in a class that satisfies the C++ allocator interface** and pass it to the container as a template argument; all of the container's memory then comes from the arena.
   - **The interface is mostly boilerplate**: `allocate`, `deallocate`, `construct`, `destroy`, `rebind`; knowing it exists is enough.
   - **The one thing to watch is that `deallocate()` is a no-op**: an arena can't return one block anyway; reclaiming only happens through `reset()`.
   - **Objects are still destroyed normally**: `destroy` still calls the destructor; only the "give the memory back" half is disabled.

### 2.3 Reference Implementation: An Arena You Can Use As Is {#ref-arena}

The startup treatment is the same as the pool in 1.4 (Part 4); the allocation logic is simpler, with no free list to maintain, just an offset `used_` that moves forward.

```cpp
class Arena {
  unsigned char* base_;
  std::size_t capacity_;
  std::size_t used_ = 0;

 public:
  explicit Arena(std::size_t capacity) : capacity_(capacity) {
    base_ = static_cast<unsigned char*>(std::aligned_alloc(64, capacity_));  // capacity must be a multiple of 64
    if (!base_) throw std::bad_alloc{};
    if (mlock(base_, capacity_) != 0) {
      // as above: log it
    }
    std::memset(base_, 0, capacity_);
  }

  ~Arena() {
    munlock(base_, capacity_);
    std::free(base_);
  }

  Arena(const Arena&) = delete;
  Arena& operator=(const Arena&) = delete;

  // alignment must be a power of two and no more than 64
  void* allocate(std::size_t size, std::size_t alignment = alignof(std::max_align_t)) {
    std::size_t start = (used_ + alignment - 1) & ~(alignment - 1);  // round up to the alignment
    if (start + size > capacity_) return nullptr;                    // doesn't fit
    used_ = start + size;                                            // move forward
    return base_ + start;
  }

  void reset() noexcept { used_ = 0; }
};
```

- **`allocate` is the three steps of 2.1**: `base_` is 64-byte aligned, so an aligned offset gives an aligned address, which is also why `alignment` can't exceed 64.
- **`reset()` doesn't call destructors**: objects placed in it are either trivially destructible, or the caller destroys them before `reset()`.
- **Only one fixed-size buffer**: easier to get right than the multi-block design of 2.1, at the cost of a hard capacity limit; when it's used up, it returns `nullptr`.

---

## 3. std::pmr: Once the Allocator Is in the Type, Functions Reject the Container; pmr Moves It to Run Time {#pmr}

### 3.1 The Allocator Is Part of the Type: Change the Allocator and Functions Reject It; pmr Turns It Into a Runtime Pointer {#allocator-in-type}

1. **Pain point: Part 2's allocator is a template parameter of the container**
   - **`std::vector<int>` and `std::vector<int, LowLatencyAllocator<int>>` are two unrelated types**.
   - **Consequence**: a function written to take `std::vector<int>&` rejects the arena version; to accept both, every function has to be templated on the allocator.
2. **Fix: `std::pmr` (C++17) moves "which allocation strategy" out of the type and into a runtime pointer**
   - **`std::pmr::memory_resource` is an abstract base class**: a concrete allocation strategy subclasses it and implements `do_allocate`, `do_deallocate` and `do_is_equal`.
   - **Every pmr container uses the same `polymorphic_allocator<T>`**: it holds nothing but a `memory_resource*`.
   - **So `std::pmr::vector<int>` is the same type whichever resource backs it**: pass it, assign it, return it freely.
3. **The price is paid on every allocation**
   - **Every allocation makes a virtual call through that pointer**; Part 2's allocator type is known at compile time and can be inlined away entirely.
   - **This is the trade-off between static and dynamic polymorphism** ([#8](/posts/crtp-static-polymorphism/)), applied this time to memory.

### 3.2 The Standard Library's Own Resources, Matching Parts 1 and 2 {#std-resources}

- **`monotonic_buffer_resource` is Part 2's arena, standardized**: allocate forward only, free everything together, no individual reclaiming. At construction you can give it a buffer the caller prepared, such as a `std::array` on the stack.
  - **When the buffer runs out it goes to its upstream resource, and the default upstream is `new`**: a silent `malloc` on the hot path.
  - **Set the upstream to `std::pmr::null_memory_resource()`**: running out then throws `std::bad_alloc`, so a capacity that's too small shows up right away.
- **`unsynchronized_pool_resource` is closer to Part 1's pool**: generalized to many object sizes, with one group of slots per size class.
- **`synchronized_pool_resource` is its thread-safe version**: at the cost of a lock, exactly the kind of contention this post is trying to avoid.

### 3.3 A Resource Is Only Pointed To, Never Owned: If It Dies First, the Container Dangles {#lifetime}

1. **Pain point: `std::pmr::vector` looks like an ordinary value type, so returning one by value seems safe**
   - **But `polymorphic_allocator` only points at its resource and doesn't own it**: if the resource is a local variable, returning the vector doesn't make the resource live any longer.

   ```cpp
   auto create_vec() -> std::pmr::vector<int> {
     auto resource = PrintingResource{};           // local, destroyed at scope exit
     auto vec = std::pmr::vector<int>{&resource};  // vec stores only &resource
     return vec;                                   // resource is destroyed here
   }
   auto vec = create_vec();
   vec.emplace_back(1);  // undefined behavior
   ```

   - **Nothing looks wrong at the return**: `vec` itself moves out fine, with no deep copy; but the resource it points at is gone, and adding elements afterwards is undefined behavior.
2. **Rule: a resource must outlive every container built on it**
   - **Put it in an outer scope**: never inside the function that constructs and returns the container.

### 3.4 Object Pool, Arena or std::pmr: Look at How the Objects Are Freed {#which}

> **Choose by how the objects are freed**
>
> 1. **Objects allocated and freed one at a time, of one fixed type**: use an object pool. Allocation and freeing only touch the head of the free list, O(1).
> 2. **A batch of objects used up and thrown away together** (all the temporary objects touched while handling one tick or one order): use an arena. Allocation is one addition; nothing can be freed on its own; `reset()` the whole thing when done.
> 3. **The same container type has to switch between different memory sources**: use `std::pmr`. It solves type compatibility, not performance; every allocation pays one more virtual call, so on the hot path it is worse than the other two.

---

## 4. The Page Layer: With a Big Block of Memory in Hand, Why Does the Hot Path Still Enter the Kernel When It Uses It {#keep-memory}

The allocators of the first three parts all take one big block of memory at startup: the pool's slot array, the arena's blocks, the buffer behind a pmr resource. Hot-path allocation only moves pointers inside that block and never goes to `malloc`. **But having the block in hand doesn't yet mean the hot path stays out of the kernel when it uses it**: when the pages of that block actually arrive, and whether they get taken away, is up to the kernel, whichever allocator you use. Four pain points below show up one after another; each fix exposes the next.

> **Four pain points, one after another**
> - **All you get is addresses, and the first write to every page faults**: write the whole block once at startup (4.1).
> - **Faulted-in pages can be swapped out when memory is tight**: lock them with `mlock` or `mlockall` (4.2).
> - **glibc tears down the mappings of locked pages by itself and hands them back to the kernel, and the lock goes with them**: three `mallopt` calls close glibc's three ways of giving memory back (4.3).
> - **Tearing down mappings and changing page tables interrupts hot cores with inter-processor interrupts**: once the process is running, its address space is read-only (4.4).
>
> The first two cover the pool's or arena's own block; the last two cover the whole process, including memory that third-party libraries and cold threads get through glibc.

### 4.1 All You Get Is Addresses: The First Write to Every Page Faults, So Write the Whole Block Once at Startup {#prefault}

**Pain point**: when `aligned_alloc`, `posix_memalign` or `mmap` returns, the kernel has only recorded a range of virtual addresses, with no physical memory behind it yet. Linux maps pages lazily: each 4 KiB page traps into the kernel with a page fault on its first access, which allocates a physical page, about 0.5–2 µs each time. The first slot the pool hands out and the first page the arena advances into will both fault on the hot path.

**Fix**: add one line, `memset(raw_memory, 0, total_size)`, to the constructor, writing every page once at startup so all the faults are paid then; if the memory comes from `mmap`, you can also pass `MAP_POPULATE` and have the kernel fault the pages in at mapping time. **By the time the hot path runs, every page in the pool and the arena is already mapped, and nothing has to happen for the first time**. The pool in 1.4 and the arena in 2.3 both do this.

### 4.2 Faulted-In Pages Can Be Swapped Out: mlock Locks One Block, mlockall Locks the Whole Process {#mlockall}

**Pain point**: faulting the pages in doesn't guarantee they stay. When memory is tight, the kernel swaps pages that haven't been touched for a while out to disk; when the hot path touches one again, it is read back from disk, at the ms level.

**Fix**: lock the pages.

- **`mlock(addr, len)` locks one block**: the pool or arena calls it once on its own block at construction, so the pages in the range stay resident and are never swapped out; on success it also faults those pages in.
- **`mlockall(MCL_CURRENT | MCL_FUTURE)` locks the whole process**: all pages mapped now are locked; `MCL_FUTURE` makes pages mapped later get faulted in and locked in one go at mapping time.
- **Page locking often fails, and when it fails, not a single page is locked or faulted in**: without `CAP_IPC_LOCK`, the total you can lock is limited by `RLIMIT_MEMLOCK` (a common default is 8 MB; older kernels allow only 64 KB). So check the return value at startup, and do the `memset` of 4.1 anyway: the pages aren't locked, but at least the first-touch faults are already paid.

### 4.3 Locked Pages Can Be Handed Back to the Kernel by glibc: Three mallopt Calls, Each Closing One Path {#mallopt}

**Pain point**: `mlockall` doesn't stop glibc from handing pages back to the kernel by itself. A lock goes with its mapping: `munmap` doesn't unlock a page, it tears down the whole mapping, and the lock goes with it. glibc does exactly that: allocations above `M_MMAP_THRESHOLD` (128 KB by default) get their own `mmap`, and `free` calls `munmap` on them immediately. The next request is another pair of system calls plus page faults (under `MCL_FUTURE`, new pages are faulted in all at once inside `mmap`). The pool's and arena's own blocks are never `free`d, but other code in the process still goes through glibc: third-party libraries, STL containers with the default allocator, cold threads for logging and monitoring.

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

**Fix**: glibc has three ways to give memory back to the kernel; three `mallopt` calls close one each:

| Setting | Path it closes | Effect |
|---|---|---|
| `M_MMAP_MAX = 0` | Large allocations get their own `mmap`, `munmap`ed on `free` | Every allocation goes through the heap; `free` is pure bookkeeping inside the heap |
| `M_TRIM_THRESHOLD = -1` | When a large chunk at the top of the heap is free, shrink the heap and give it back to the kernel | The heap only grows, never shrinks |
| `M_ARENA_MAX = 1` | Each new arena `mmap`s its own memory | Only the main arena is used; allocation happens only at startup, so the reduced lock contention of multiple arenas doesn't matter |

> **At startup, set mallopt first, then lock the pages**
>
> ```cpp
> mallopt(M_MMAP_MAX, 0);
> mallopt(M_TRIM_THRESHOLD, -1);
> mallopt(M_ARENA_MAX, 1);
> mlockall(MCL_CURRENT | MCL_FUTURE);   // needs CAP_IPC_LOCK, or a large enough RLIMIT_MEMLOCK
> ```
>
> - **Call `mallopt` before the first large allocation**: blocks already `mmap`ed are not affected.
> - **`mlockall` can fail**: without the permission or enough quota it returns an error and locks nothing, so check the return value at startup; the fallback is the pre-faulting of 4.1.

### 4.4 Tearing Down Mappings Interrupts Hot Cores: TLB Shootdowns, So Keep the Address Space Read-Only Once the Process Runs {#shootdown}

**Pain point**: each core's TLB caches translations from virtual to physical addresses. After one core removes a mapping (`munmap`) or tightens its permissions (`mprotect`), the stale translations in other cores' TLBs must be invalidated, and the hardware doesn't sync them by itself: **the only way is to send an inter-processor interrupt (IPI) to every core currently running this process and have each clear its own**. Each interrupted core traps into the kernel, clears the TLB entries and comes back; this is a **TLB shootdown**, a few microseconds each time.

**`isolcpus` doesn't stop it.** `isolcpus` controls which cores the scheduler puts threads on; a shootdown IPI is delivered by "which cores are running this process's address space", which has nothing to do with scheduling. However well the hot thread is isolated and pinned, a cold thread in the same process `free`ing a large block still interrupts the hot core once.

**Fix**: closing glibc's `munmap` in 4.3 saves the system call and the page faults, and saves the shootdown too. **Once the hot-path process is running, don't change its address space again**: transparent huge pages' background compaction and automatic NUMA balancing also change page tables and have to be turned off as well. The full list of triggers and how to turn them off is in [the TLB special, 3.3](/posts/low-latency-context-switch-page-table-tlb/#triggers).

---

## 5. Several Threads Sharing One Pool: The List Head Must Be Taken and Put Back Lock-Free, and Guarded Against ABA {#aba}

The pools and arenas of the first four parts are all used from one thread. This part first explains why several threads end up needing to share one pool, and when they actually don't, then how the list head becomes a lock-free stack when the pool is shared, and the ABA problem peculiar to lock-free stacks.

### 5.1 Why Share: An Object Is Often Allocated on One Thread and Freed on Another {#why-shared}

1. **The most common need is returning across threads**
   - **Typical case**: the market-data thread takes a `Message` from the pool, fills it in and hands it to the strategy thread through an SPSC ring; when the strategy thread is done with it, it has to give it back.
   - **One pool per thread breaks here**: the strategy thread can only return it to its own pool. The market-data thread's pool only ever gives out and soon runs dry; the strategy thread's pool only ever takes in and keeps growing.
2. **Second, saving memory**
   - **If every thread keeps its own peak capacity, the total is that times the number of threads**: pool memory also has to be locked and pre-faulted (Part 4), so keeping too much is expensive.
   - **With one shared pool, the system-wide peak is enough**: the threads' peaks usually don't come at the same time.
3. **Once shared, the pool of 1.4 used as is goes wrong**
   - **Two threads reading `free_head_` at the same time get the same slot**: the same memory goes to two users.
   - **A `mutex` fixes it, but brings the jitter back**: even with no contention, each lock costs one atomic read-modify-write; under contention, the thread that loses the lock goes to sleep, and waking it takes a few to tens of µs, landing right in the tail latency ([#1](/posts/cpu-affinity-core-isolation-numa/) 3.4).

> **First decide whether to share the pool**
> - **Allocation and freeing on the same thread**: one pool per thread, the single-threaded version of 1.4, not even an atomic operation.
> - **Returned across threads, but only between one pair of threads in a fixed direction**: send the used object (or its index) back through an SPSC ring to the thread that allocated it, which puts it back into the pool itself. The pool stays single-threaded; this is common in HFT.
> - **Several threads all allocate and all free**: share one pool and turn the list head into a lock-free stack (5.2).
> - **Many threads and frequent allocation**: use two levels. Each thread first uses its own small cache, and only when that is empty or full does it take from or return to the shared pool in batches. glibc's tcache and tcmalloc both follow this idea.

### 5.2 Make the List Head an Atomic and Take and Put Back With CAS: That's a Lock-Free Free Stack {#lock-free-stack}

1. **Allocate (pop)**: read `head` and its `next`, then CAS `head` from the value read to `next`. If another thread changed `head` in the meantime, the CAS fails; read again and retry.
2. **Free (push)**: point the returned slot's `next` at the current `head`, then CAS `head` to this slot.
3. **Why it's called a stack**: the free list is only entered and left at its head, last in, first out, so it is a lock-free stack. With no lock, nobody goes to sleep; a thread whose CAS fails just tries once more.

### 5.3 ABA: CAS Only Compares Values, So It Can't See That head Changed and Changed Back {#aba-problem}

**This stack has a classic trap called ABA: CAS only compares values, and can't see that the value changed in between and then changed back**. The name describes `head` going from A to B and back to A. Below, X, Y and Z are three free slots, and the stack starts as X → Y → Z:

| Moment | Thread A (allocating) | Other threads | Free stack |
|---|---|---|---|
| 1 | Reads `head = X`, `X.next = Y`, and is switched out before its CAS | | X → Y → Z |
| 2 | | Thread B allocates twice, taking X and Y | Z |
| 3 | | Some thread returns X | X → Z |
| 4 | CAS: `head` is still X, so it succeeds and sets `head` to Y | | Y → Z, but Y is in use by B |

After moment 4, the next allocation hands Y out again, so one slot goes to two users at the same time; and X, just returned, falls off the stack and can never be handed out again.

### 5.4 The Fix: Give the List Head a Version Number and Compare It Along With the Index in the CAS {#tagged-head}

**The fix is to give `head` a version number that goes up by 1 on every change, and have the CAS compare the index and the version together**. At moment 1, thread A reads (X, version 5); moments 2 and 3 make three changes in all, so `head` becomes (X, version 8). A compares against (X, 5), they're not equal, the CAS fails, and A reads again and retries.

Slots are named by 32-bit indices, so an index and a 32-bit version fit exactly into one `uint64_t`, and an ordinary 64-bit CAS can compare both. A list of pointers would need a 16-byte CAS (`cmpxchg16b` on x86-64), or squeezing the version into the 16 unused high bits of a 64-bit pointer. The version wraps around, but that would require thread A to miss exactly $2^{32}$ changes while it is switched out, which doesn't happen in practice.

Read the code in three segments: how the slots and the list head are laid out, taking a slot, returning a slot.

**Segment 1: the slots and the list head, with an index and a version packed into one 64-bit number**

```cpp
template <typename T>
class ConcurrentPool {
  struct Slot {
    alignas(T) unsigned char storage[sizeof(T)];  // the object is constructed here; first member, so object address = slot address
    std::atomic<std::uint32_t> next;              // while free: index of the next free slot
  };
  static constexpr std::uint32_t kNil = UINT32_MAX;   // end of the list; when the stack is empty, the top is this
  static std::uint64_t pack(std::uint32_t ver, std::uint32_t idx) {
    return (std::uint64_t(ver) << 32) | idx;      // high 32 bits: version, low 32 bits: index
  }

  Slot* slots_;                                   // allocation, mlock, memset and list setup as in 1.4
  std::atomic<std::uint64_t> head_;               // (version, index of the top), initially pack(0, 0)
```

- **Indices instead of pointers, so that the index fits into 64 bits together with the version**: one ordinary 64-bit CAS (`lock cmpxchg` on x86) compares both at once.
- **`next` has bytes of its own, and it is atomic**: when another thread reads it, this slot may be in use by someone, for the reason given in 5.5.

**Segment 2: `allocate`, taking a slot off the top of the stack**

```cpp
 public:
  template <typename... Args>
  T* allocate(Args&&... args) {
    std::uint64_t old = head_.load(std::memory_order_acquire);              // ① read the top: version + index
    for (;;) {
      std::uint32_t idx = static_cast<std::uint32_t>(old);                  // ② the low 32 bits are the top's index
      if (idx == kNil) return nullptr;                                      //    the pool is used up
      std::uint32_t next = slots_[idx].next.load(std::memory_order_relaxed);   // ③ the slot under the top; may be stale
      std::uint64_t desired = pack(static_cast<std::uint32_t>(old >> 32) + 1, next);  // ④ new top: version + 1, index becomes next
      if (head_.compare_exchange_weak(old, desired,                         // ⑤ only if head_ still equals old, set it to desired
                                      std::memory_order_acquire,            //    success
                                      std::memory_order_acquire))           //    failure: old now holds the latest value, back to ②
        return ::new (slots_[idx].storage) T(std::forward<Args>(args)...);  // ⑥ the slot is mine; construct the object in place
    }
  }
```

- **A stale `next` read at ③ does no harm**: if another thread touched `head_` between ① and ⑤, the version has changed, ⑤ is certain to fail, and the stale `next` is thrown away with it.
- **⑤ compares all 64 bits**: even if the top's index has come back to X, the version won't match. The CAS at moment 4 in the table of 5.3 fails right here.
- **On failure `old` already holds the latest value**: so the loop doesn't need another `load` and starts again from ②. The `weak` version occasionally fails for no reason; since it's in a loop anyway, one more try handles it.
- **Only the thread whose CAS succeeds reaches ⑥**: the slot is already off the stack and belongs to it alone, and only then is the object constructed.

**Segment 3: `deallocate`, pushing a slot back on top of the stack**

```cpp
  void deallocate(T* obj) {
    obj->~T();                                                              // ① destroy first
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));   // ② object address → slot address
    std::uint32_t idx = static_cast<std::uint32_t>(slot - slots_);          //    slot address → index
    std::uint64_t old = head_.load(std::memory_order_relaxed);
    for (;;) {
      slot->next.store(static_cast<std::uint32_t>(old), std::memory_order_relaxed);  // ③ my next = the current top
      std::uint64_t desired = pack(static_cast<std::uint32_t>(old >> 32) + 1, idx);  // ④ new top: version + 1, index becomes mine
      if (head_.compare_exchange_weak(old, desired,                         // ⑤ push only if the top hasn't changed
                                      std::memory_order_release,            //    success: publish the destruction and next together
                                      std::memory_order_relaxed))           //    failure: back to ③, next re-pointed at the new top
        return;
    }
  }
};
```

- **③ rewrites `next` on every round**: a failed CAS means the top changed, so `next` must point at the new top before trying again.
- **Pushed back on top, last in, first out**: the slot just returned is the first to go out next time, and it is most likely still in cache.
- **The version goes up by 1 on push too**: strictly, bumping it only on pop is enough to stop ABA, because for a slot to be taken by someone and returned, there must be a pop in between; bumping on every change keeps the rule simpler.

A stress test built with GCC 16.2: 8 threads sharing a 64-slot pool, each allocating and freeing 200,000 times; no slot was ever handed to two threads at once, and all 64 slots were back at the end.

### 5.5 Memory Ordering: acquire for Allocation, release for Freeing {#pool-ordering}


- **The load and the CAS in allocation both use acquire**: the thread that gets a slot has to see what the previous user wrote into it before freeing it, and the `next` written when it was freed. On failure, the CAS reads the latest `head` back into `old`, and the next round goes on to read its `next`, so the failure path needs acquire too.
- **The CAS in freeing uses release**: the writes into this slot and the `next` just written are published, together with this CAS, to the next thread that gets the slot.

`next` is kept separate, as a `std::atomic` that shares no bytes with `storage`, because when thread A reads `X.next` at moment 1, X may already have been taken by another thread that is constructing an object in `storage`. With the two kept apart, that read is not a data race; the stale value it reads is thrown away with the failed CAS.

### 5.6 Slots Are Never Returned to the System: That Removes the Hardest Problem of Lock-Free Stacks, Reclamation {#no-reclaim}

An ordinary lock-free stack `delete`s a node after popping it, while another thread may still hold its address and be about to read `next`, i.e. read memory that has already been freed; solving that takes a reclamation scheme such as hazard pointers or epochs. **The slots of a pool are always there, so the worst you can read is a stale `next`**, and that value is thrown away with the failed CAS.
