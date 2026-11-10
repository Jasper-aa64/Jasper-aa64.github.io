---
title: "Trading System Notes #4: Lock-Free Queues and Micro-Batching"
date: 2026-09-20
lastmod: 2026-11-10
slug: "lock-free-queue-logger-micro-batching"
description: "How a single-producer single-consumer ring buffer avoids locks — the power-of-two mask, the two-step handoff, the memory order each side needs — and the traps that quietly bring contention back: a shared element counter, a full-check that reads the other core on every call. Then a logger and micro-batching built on top, and what lock-free and wait-free actually promise."
summary: "A lock-free SPSC queue works because every shared variable has exactly one writer: each side writes only its own index and merely reads the other's. The rest is keeping that property from being quietly undone: compute the element count by subtracting the two indices instead of keeping a shared counter, cache the other side's index and refresh it only when the queue looks full or empty, and push log lines as text runs, not one character per slot. SPSC is wait-free only through a fail-fast interface, and a bounded queue must always choose between dropping and blocking when it fills."
chapter: 1
categories: [Systems]
tags: [cpp, lock-free, wait-free, spsc, ring-buffer, atomics, logging, micro-batching, hft, low-latency]
toc: true
math: true
homepage: false
---

A hot thread has to hand work to another thread: a log line, a market-data tick, an order event. A locked queue adds only a few tens of nanoseconds on average, but it brings a long latency tail you don't control, so the hot path uses a lock-free queue (1.1 first says when the switch is worth it). The whole design rests on one rule: **every shared variable has exactly one writer**. Each side writes only its own index and only reads the other's, so the two cores never fight over a write. The surrounding hygiene is assumed below: the hot thread is pinned and isolated ([#1](/posts/cpu-affinity-core-isolation-numa/)), the memory it touches is locked and pre-faulted ([#3](/posts/hot-path-memory-allocators/)), and release/acquire and the price of a cache line are covered in [#2](/posts/memory-ordering-false-sharing-dependency-chains/).

---

## 1. The SPSC Ring: How Two Hot Threads Hand Off Data Without a Lock {#spsc}

### 1.1 When to Use It: A Locked Queue Isn't Slow on Average but in the Tail, and a Lock-Free Ring Makes You Manage the Waiting {#when-spsc}

1. **The pain: a queue built from one mutex and two condition variables ([#18](/posts/thread-safe-queue/) Part 1) carries three uncontrolled costs on a hot path**
   - **A thread that loses the lock goes to sleep**: it sleeps on a futex and is woken later. From the notify to actually running takes several to tens of µs, and when it wakes is the scheduler's decision.
   - **When the consumer is asleep, the producer has to wake it**: `notify_one` then enters the kernel, so the hot thread pays a system call on the other side's behalf.
   - **When the lock holder is switched out, the hot thread waits with it**: if the holder is a low-priority background thread, that is priority inversion ([#19](/posts/scheduling-priority-inversion-kernel-tuning/) Part 2).
   - **So what you're avoiding isn't the few tens of ns added on average; it's a long latency tail you don't control.**
2. **The fix: a lock-free SPSC ring in which each side writes only its own index** (1.2)
   - **There is no lock to fight over**: nobody goes to sleep, nobody has to wake anybody, and the hot path never enters the kernel.
   - **Full and empty both return immediately**: every operation has a bounded number of steps. The goal isn't "fast", it's "bounded".
3. **The cost: you manage the waiting yourself, and the shape is fixed**
   - **When it's empty there is no condition variable to sleep on**: the consumer either keeps checking (busy polling) and occupies a whole core, or takes what's there in batches every so often and adds that interval to the latency.
   - **Exactly one writer and one reader**: add a second writer and "each index has one writer" no longer holds.
   - **Fixed capacity**: when it's full you have to choose between dropping and blocking (Part 4).

> **Decide first whether to switch to a lock-free ring**
> - **The consumer is idle most of the time and the producer isn't on a hot path** (reconciliation, admin commands, monitoring reports): use a blocking queue with a lock. It saves CPU, it's easy to get right, and a wake-up of a few µs is affordable.
> - **Both ends are hot threads pinned to isolated cores** (market data → strategy, strategy → gateway): use a lock-free SPSC ring, with the consumer busy-polling and the threads pinned ([#1](/posts/cpu-affinity-core-isolation-numa/)).
> - **Only the producer is hot and the consumer is in no hurry** (logging, writing to disk): still use a lock-free ring. The hot thread only fills slots and never enters the kernel; the consumer takes what's there in batches every so often (Parts 3 and 5) and doesn't need a core of its own.
> - **Several producers feed one consumer**: give each producer its own SPSC ring and let the consumer check them in turn, or use a multi-producer lock-free ring ([#18](/posts/thread-safe-queue/) Part 2).

### 1.2 Two Counters and a Mask {#spsc-ring}

A single-producer single-consumer (SPSC) queue is a fixed array of slots plus two indices that only ever increase. The producer owns `write_idx`: only it ever stores to it. The consumer owns `read_idx`. Each side reads the other's index, the producer to learn whether there is room and the consumer to learn whether there is data, but never writes it. With one writer per variable there is nothing to lock and nothing to retry.

```cpp
template <typename T>
class SpscQueue {
  std::vector<T> slots_;                       // capacity is a power of two
  size_t         mask_;                        // capacity - 1

  alignas(64) std::atomic<size_t> write_idx_{0};   // stored to only by the producer
  alignas(64) std::atomic<size_t> read_idx_{0};    // stored to only by the consumer

 public:
  explicit SpscQueue(size_t n) : slots_(round_up_pow2(n)), mask_(slots_.size() - 1) {}

  // ---- producer ----
  T* try_claim() {                             // step 1: where do I write?  nullptr = full
    const size_t w = write_idx_.load(std::memory_order_relaxed);   // my own index
    const size_t r = read_idx_.load(std::memory_order_acquire);    // theirs
    if (w - r == slots_.size()) return nullptr;
    return &slots_[w & mask_];
  }
  void publish() {                             // step 2: make the element visible
    write_idx_.store(write_idx_.load(std::memory_order_relaxed) + 1,
                     std::memory_order_release);
  }

  // ---- consumer ----
  T* try_peek() {                              // nullptr = empty
    const size_t r = read_idx_.load(std::memory_order_relaxed);    // mine
    const size_t w = write_idx_.load(std::memory_order_acquire);   // theirs
    if (r == w) return nullptr;
    return &slots_[r & mask_];
  }
  void release() {                             // done reading: hand the slot back
    read_idx_.store(read_idx_.load(std::memory_order_relaxed) + 1,
                    std::memory_order_release);
  }
};
```

The code makes three design choices:

- **A slot's position is `idx & mask_`, so the capacity is a power of two**: with a power-of-two capacity, `mask_ = capacity - 1` is a run of low ones, and `idx & mask_` equals `idx % capacity`. The capacity is only known at run time, so the compiler can't turn `%` into a bit operation for you; the constructor rounds the capacity up to a power of two, and the hot path gets one AND instead of a divide. The indices only increase, so the full-check `w - r == capacity` never has to worry about wrapping.
- **The producer works in two steps: get a pointer to the slot, then publish**: `try_claim` returns the slot's address and the element is constructed in place, written once. A `push(const T&)` would build it somewhere else and copy it in. Publishing is a separate step because it's the only moment the consumer is allowed to see the element.
- **Read your own index relaxed, the other's acquire, and write your own with release**: only you ever write your own index, and a thread always sees its own earlier writes, so relaxed is enough. The other side's index is what carries information across cores. The producer release-stores `write_idx_`, so a consumer whose acquire load sees the new index also sees the slot's contents; the consumer release-stores `read_idx_`, so when the producer sees a slot as free, the consumer has certainly finished reading it. On x86 these release stores compile to ordinary `mov`s; on ARM they are `stlr`.

If you write the full-check with masked indices instead of increasing ones, watch the operator precedence: in `(w + 1) & mask == r & mask`, `==` binds tighter than `&`, so it parses as `((w + 1) & (mask == r)) & mask`. That is almost always false, and the producer overwrites unread data. Either parenthesize both sides, or subtract unwrapped indices as above.

### 1.3 Subtract, Don't Count: The Counter That Made Two Cores Fight {#size-from-indices}

It's tempting to add an atomic element count, incremented by the producer after publishing and decremented by the consumer after releasing, so that `size()` is a single load:

```cpp
std::atomic<size_t> count_{0};
// producer, after publishing:   count_.fetch_add(1, std::memory_order_release);
// consumer, after releasing:    count_.fetch_sub(1, std::memory_order_release);
```

**Both cores write this counter, which is exactly what breaks "one writer per variable".** `fetch_add` and `fetch_sub` are read-modify-writes and need exclusive ownership of the line, so every enqueue pulls the line away from the consumer and every dequeue pulls it back. This is true sharing, not false sharing: the two cores really do modify the same variable, and padding it onto its own cache line doesn't help.

The element count is already there: it is `write_idx - read_idx`. Computing it takes two loads, and a load only needs the line in a shared state, with no ownership transfer:

```cpp
size_t size_approx() const {
  const size_t r = read_idx_.load(std::memory_order_acquire);    // the lagging index first…
  const size_t w = write_idx_.load(std::memory_order_acquire);   // …then the leading one
  return w - r;
}
```

Two things to keep in mind when using it:

- **The result is approximate**: the two loads happen at slightly different moments, so together they don't describe one instant. That's fine for "roughly how backed up are we", wrong for a decision that needs an exact answer. Both sides can move between the two loads, so the result can even exceed the capacity; clamp it if that matters.
- **Read `r` first, then `w`**: `w >= r` holds at every instant and `w` only increases, so the `w` you read second is no smaller than `w` was when you read `r`, and the difference can't go negative. Read them the other way around and an outside thread (a monitoring loop, say) can pick up a `w` from before both sides moved and an `r` from after: `w - r` goes negative, which for unsigned values is an enormous number. The first load is acquire so the second can't be reordered ahead of it. The producer or consumer calling it on itself can't hit this, because its own index can't move in the middle of its own call; the rule is for a `size()` that any thread may call.

---

## 2. Optimizing the SPSC Ring: Fewer Cross-Core Reads of the Other Side's Index, No Split Copy at the Wrap {#optimize}

### 2.1 Cache Their Cursor: A Stale Value That Can Only Err Safe {#cached-index}

> **What this section solves: every enqueue and dequeue reads the other side's index across cores**
>
> - **The pain: checking full and empty reads the index the other side writes, every time**: the producer's `try_claim()` acquire-loads `read_idx_` on every call, and the consumer's `try_peek()` loads `write_idx_`.
> - **That read is mostly wasted, and it isn't cheap**: while the queue is far from full and far from empty, the new value doesn't change the decision. But every time the other side advances its index, that line has been modified on the other core, and reading it again means fetching it across cores, tens of ns to over a hundred each time.
> - **The fix: decide using a local copy**: only when the copy says "full" or "empty" do you actually read the other side's index and refresh the copy.
> - **The effect: one cross-core read per batch instead of one per element.**
> - **A stale copy is still safe**: the other side's index only moves forward, so a stale copy only makes the decision more conservative (details below).

Concretely, each side keeps a local copy of the other side's index and checks against it; only when the copy says "full" or "empty" does it read the real index once, refresh the copy, and check again:

```cpp
alignas(64) std::atomic<size_t> write_idx_{0};
            size_t              cached_read_idx_ = 0;    // producer-private: on the same line as the producer's own index
alignas(64) std::atomic<size_t> read_idx_{0};
            size_t              cached_write_idx_ = 0;   // consumer-private

T* try_claim() {
  const size_t w = write_idx_.load(std::memory_order_relaxed);
  if (w - cached_read_idx_ == slots_.size()) {                       // looks full — the copy may be stale
    cached_read_idx_ = read_idx_.load(std::memory_order_acquire);    // pay for one cross-core read
    if (w - cached_read_idx_ == slots_.size()) return nullptr;       // really full
  }
  return &slots_[w & mask_];
}

T* try_peek() {
  const size_t r = read_idx_.load(std::memory_order_relaxed);
  if (r == cached_write_idx_) {                                      // looks empty — refresh
    cached_write_idx_ = write_idx_.load(std::memory_order_acquire);
    if (r == cached_write_idx_) return nullptr;                      // really empty
  }
  return &slots_[r & mask_];
}
```

**A stale copy only makes the decision conservative; it never makes it wrong.** The consumer's index only moves forward, so the producer's copy is always at most the real value, and the free space computed from it can only be too small. It can say "full" when there is actually room, in which case the code refreshes and finds out; it can never say "there's room" when there isn't. The consumer's copy is stale in the same safe direction: it may say "empty" too early, never "data" when there is none.

There is a second win. When the consumer does refresh, it usually finds that many elements have arrived, and it can process all of them before touching the producer's line again. **The cross-core read goes from once per element to once per batch.**

### 2.2 Mirror the Addresses, Not the Data {#mirror-mapping}

A ring buffer of bytes, or of variable-length records, has an awkward moment: a write that starts near the end runs past it. The usual handling splits it into two copies, one up to the end and one from the start, plus a branch to decide when to split.

There is a way to remove the seam: **map the same physical memory at two adjacent virtual address ranges**, so the buffer looks twice as long and the second half is a mirror of the first. A write that runs past the end of the first half just continues into the second half and lands exactly where the wrap-around would have put it: one `memcpy`, no branch. On Linux it takes three steps:

```cpp
void* base = mmap(nullptr, 2 * N, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);      // reserve 2N of addresses, nothing else
int   fd   = memfd_create("ring", 0);                                                  // an in-memory "file"…
ftruncate(fd, N);                                                                      // …N bytes long
mmap(base,                          N, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);   // first view
mmap(static_cast<char*>(base) + N,  N, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);   // second view: same pages
```

1. Reserve `2N` bytes of address space with `PROT_NONE`: it claims the addresses and no memory.
2. Create an in-memory file with `memfd_create` and size it to `N` bytes with `ftruncate`.
3. Map that file over the first half and over the second half, both with `MAP_SHARED | MAP_FIXED`.

Both views are backed by the same physical pages, so `buf[i]` and `buf[i + N]` are the same byte.

**The wrap-around doesn't disappear; only the starting offset wraps.** The indices are still folded back into `[0, N)` with a mask, so `N` is a power of two (at least the page size, which makes it a multiple of the page size as well). A write is never longer than the free space, and the free space is never more than `N`, so the end stays within `2N` and never runs past the second view; the part that runs past the end of the first view lands in the mirror, which is the start of the ring after the wrap:

```cpp
bool write(const char* src, size_t len) {
  size_t h = head_.load(std::memory_order_relaxed);
  size_t t = tail_.load(std::memory_order_acquire);
  if (len > N - (h - t)) return false;               // not enough free space
  std::memcpy(buf_ + (h & (N - 1)), src, len);       // start in [0, N), len ≤ N, end ≤ 2N
  head_.store(h + len, std::memory_order_release);
  return true;
}
```

The read side is the same: read `len` bytes from `buf_ + (t & (N - 1))` in one go, whether or not they cross the end.

<!--
╔══════════════════════════════════════════════════════════════════╗
║  🖼  ILLUSTRATION  ——  Mirror the Addresses, Not the Data         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Academic graphite pencil illustration on clean white paper.     ║
║  16:9. Style: precise technical linework, careful                ║
║  cross-hatching for shading and depth, monochrome graphite only  ║
║  — no color, no watercolor, no graph-paper grid. Scientific      ║
║  journal or engineering textbook style. NOT cartoon. NOT         ║
║  colorful. Precise and academic.                                 ║
║                                                                  ║
║  Topic: mapping the same physical memory pages at two            ║
║  consecutive address ranges, so that a write which runs past     ║
║  the end of a ring buffer simply continues into the second       ║
║  range and lands on the first pages again, instead of being      ║
║  split in two.                                                   ║
║                                                                  ║
║  Main metaphor: a two-panel dissection diagram. Eight identical  ║
║  stone floor tiles, numbered 0 to 7, stand for the eight         ║
║  physical pages.                                                 ║
║                                                                  ║
║  Layout: side-by-side comparison (two-panel), left panel headed  ║
║  "ONE MAPPING", right panel headed "TWO MAPPINGS, SAME PAGES".   ║
║                                                                  ║
║  Objects and labels:                                             ║
║   - left panel: one row of eight tiles, numbered 0-7, with a     ║
║     heavy vertical wall at the right end of tile 7. A thick      ║
║     ruled arrow starts on tile 6, runs to the wall and stops;    ║
║     a second, separate arrow starts again over tile 0 —          ║
║     labeled "one write, cut in two: two copies"                  ║
║   - right panel: THREE horizontal rows of eight tiles, stacked   ║
║     one above the other, each row numbered 0-7 from left to      ║
║     right. All three rows have the same width and are exactly    ║
║     aligned, so tile k of every row sits directly above tile     ║
║     k of the next row.                                           ║
║       * top row: lightly cross-hatched tiles — labeled           ║
║         "first view"                                             ║
║       * middle row: heavy solid stone tiles — labeled            ║
║         "the physical pages"                                     ║
║       * bottom row: lightly cross-hatched tiles — labeled        ║
║         "second view"                                            ║
║     Straight VERTICAL dotted lines join each tile to the tile    ║
║     with the SAME number directly above or below it (0 to 0,     ║
║     1 to 1, ... 7 to 7). No diagonal lines, no crossing lines,   ║
║     no line ever joins two different numbers.                    ║
║     One thick ruled arrow starts on tile 6 of the top row and    ║
║     runs to the right end of that row; a second thick ruled      ║
║     arrow of the same style runs over tiles 0 and 1 of the       ║
║     bottom row; a small curved dotted hook joins the end of      ║
║     the first arrow to the start of the second — together        ║
║     labeled "one write, one copy"                                ║
║                                                                  ║
║  Title (top, large): "Mirror the Addresses, Not the Data"        ║
║  Subtitle: "The same pages mapped twice, back to back — a write  ║
║  that crosses the end never has to split"                        ║
║  Footer caption: "Mirror the Addresses, Not the Data."           ║
║                                                                  ║
║  All text in English. No Chinese characters. No color fills. No  ║
║  gradients. Monochrome graphite only.                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
-->

![Two panels. Left: one row of eight numbered stone tiles ending at a wall, with a single write cut into two separate arrows. Right: three aligned rows of the same eight numbered tiles (first view, physical pages, second view) joined by vertical dotted lines between matching numbers, and one write that runs off the end of the first view and continues across the first two tiles of the second view.](/images/lock-free-queue/mirror-the-addresses.jpg)

- **It needs a file descriptor; two anonymous mappings can't do it**: each `MAP_ANONYMOUS` mapping gets its own fresh pages, and there is nothing for the second mapping to point at. For two address ranges to share pages you need an object both can refer to: an fd here, or a System V shared-memory segment.
- **Everything happens at construction**: the reservation, the fd and both mappings are done once, and after that every enqueue and dequeue is an ordinary memory access with no system call. As in [#3](/posts/hot-path-memory-allocators/), these pages should also be pre-faulted and locked.
- **What it costs, and where it applies**: `N` must be a multiple of the page size; a failure halfway through has to `munmap` and `close` what was already done; the second view adds page-table entries and TLB pressure. The queue in 1.2 doesn't need it: its slots have a fixed size, so an element never straddles the end. It suits byte streams, variable-length records, and reads or writes of several elements at once, where the copy itself dominates and crossing the end is common.

---

## 3. A Logger Built on the Queue

### 3.1 The Hot Thread Only Fills Slots; a Background Thread Writes the File {#logger}

Logging is the classic customer for this queue. Formatting, file I/O and the `write` system call are all slow and belong where nobody is waiting: the hot thread only fills queue slots with what it wants to record, and one background thread drains the queue and writes the file.

The queue's slots have a fixed size, so a slot holds a tagged union with room for the biggest thing you might log:

```cpp
enum class Tag : uint8_t { Char, Int, Long, Double, Text /* … */ };

struct LogElement {
  Tag tag;
  union {
    char c;  int i;  long l;  double d;  /* … the other numeric types … */
    char s[256];                          // the member that sets the size of every slot
  } u;
};   // 264 bytes on x86-64: the tag pads out to 8, then the 256-byte member
```

**`char s[256]` sets the size of every slot**: an element holding a single `char` still occupies 264 bytes. 8 million slots is about 2 GiB, deliberately large, because the background thread is slow and will fall behind during bursts.

The background thread is a loop that drains, flushes the file, and sleeps:

```cpp
while (running_) {
  while (LogElement* e = queue_.try_peek()) {
    write_to_file(*e);                  // switch on e->tag
    queue_.release();
  }
  file_.flush();
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
}
```

The 10 ms sleep is a choice: this thread isn't latency-sensitive, so giving its core back beats spinning, at the price of log lines reaching the file up to 10 ms late and a queue that has to hold everything produced in that window. SPSC adds two rules:

- **One logger serves exactly one producing thread**: a second producer would break "one writer per index", so give each thread its own logger or its own queue.
- **On shutdown, drain the queue first, then stop the background thread, then close the file**: stop the background thread first and whatever was still queued is silently lost.

### 3.2 Push Text Runs: Five Slots for One Log Line {#text-runs}

The producer's `log()` walks the format string and splits one log line into several elements pushed into the queue. **The unit pushed is a text run, not a character**: the literal text between two `%` placeholders is collected into one `Text` element, and each placeholder pushes one value. `log("Order Executed, id=%, price=%\n", id, price)` makes 5 pushes in total: three text runs and two values.

<svg viewBox="0 0 760 274" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The same log line pushed two ways: per character it occupies thirty 264-byte queue slots, about 7.7 KiB; as three text runs plus two values it occupies five slots, about 1.3 KiB" style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif">
  <style>
    .bg    { fill: #fbfaf7; }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .row   { fill: #3a372f; font-size: 12px; font-weight: 700; }
    .lbl   { fill: #3a372f; font-size: 11.5px; }
    .cap   { fill: #6b6558; font-size: 11px; }
    .chr   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .val   { fill: #eef1f4; stroke: #9fb0c0; stroke-width: 1.2; }
    .txt   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.4; }
    .brk   { fill: none; stroke: #8a8474; stroke-width: 1.4; }
      :root:is([data-theme="dark"], [data-theme="black"]) .bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .title { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .row { fill: #d7d3c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .lbl { fill: #d7d3c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cap { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .chr { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .val { fill: #2b3038; stroke: #8391a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .txt { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .brk { stroke: #9a9384; }
  </style>
  <rect class="bg" x="0" y="0" width="760" height="274" rx="10"/>
  <text class="title" x="24" y="30">One log line, pushed two ways — every square is one 264-byte queue slot</text>
  <text class="row" x="24" y="58">Per-character push</text>
  <rect class="chr" x="24.0" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="47.7" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="71.4" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="95.1" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="118.8" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="142.5" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="166.2" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="189.9" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="213.6" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="237.3" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="261.0" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="284.7" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="308.4" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="332.1" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="355.8" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="379.5" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="403.2" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="426.9" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="450.6" y="68" width="21" height="26" rx="3"/>
  <rect class="val" x="474.3" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="498.0" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="521.7" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="545.4" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="569.1" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="592.8" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="616.5" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="640.2" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="663.9" y="68" width="21" height="26" rx="3"/>
  <rect class="val" x="687.6" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="711.3" y="68" width="21" height="26" rx="3"/>
  <path class="brk" d="M24.0,107 L24.0,112 L732.3,112 L732.3,107"/>
  <text class="lbl" x="24" y="132">30 slots × 264 B ≈ 7.7 KiB written — about 40 bytes of it is actual text and values</text>
  <text class="row" x="24" y="166">Text-run push</text>
  <rect class="txt" x="24.0" y="176" width="21" height="26" rx="3"/>
  <rect class="val" x="47.7" y="176" width="21" height="26" rx="3"/>
  <rect class="txt" x="71.4" y="176" width="21" height="26" rx="3"/>
  <rect class="val" x="95.1" y="176" width="21" height="26" rx="3"/>
  <rect class="txt" x="118.8" y="176" width="21" height="26" rx="3"/>
  <path class="brk" d="M24.0,215 L24.0,220 L139.8,220 L139.8,215"/>
  <text class="lbl" x="24" y="240">5 slots × 264 B ≈ 1.3 KiB — the same content in one sixth of the bytes</text>
  <text class="cap" x="156.5" y="193">text run · id · text run · price · text run</text>
  <rect class="chr" x="24" y="254" width="12" height="12" rx="2"/>
  <text class="cap" x="42" y="264">one character</text>
  <rect class="val" x="152" y="254" width="12" height="12" rx="2"/>
  <text class="cap" x="170" y="264">one value (int, double, …)</text>
  <rect class="txt" x="342" y="254" width="12" height="12" rx="2"/>
  <text class="cap" x="360" y="264">one text run (up to 255 characters)</text>
</svg>

> Figure: both rows record the same log line. The queue, the memory orders and the background thread are unchanged; only the unit pushed per call changed: thirty publishes became five.

**The unit has to be large because every slot costs 264 bytes however little it holds** (3.1), so the number of slots is the cost. The same log line, pushed both ways:

| Unit pushed | Slots per line | Written per call | Lines that fit in 8 million slots |
|---|---|---|---|
| One slot per character | 30 | about 7.7 KiB, 124 cache lines | about 270,000 |
| One slot per text run | 5 | about 1.3 KiB | about 1.6 million |

- **The hot path pays per slot**: each slot is one copy and one release store, so 30 slots is 30 of each.
- **The more you write, the dirtier L1 gets**: an L1 data cache is typically 32–48 KB. A call that writes 7.7 KiB dirties a sixth to a quarter of it, and the code that runs right after has to read its own data back in; 1.3 KiB is only 3%–4%.
- **The buffer holds 6 times as many lines**: with the same 8 million slots, a queue pushed in text runs is much less likely to fill while the background thread lags for a while.

A text run longer than 255 characters is split across several slots. Only the producer-side `log()` changes; the background thread already knows how to write a `Text` slot:

```cpp
LogElement* claim() {                       // the policy point: what happens when the queue is full?
  LogElement* s;
  while ((s = queue_.try_claim()) == nullptr) { /* spin here — or count a drop and abandon the record */ }
  return s;
}

void push_text(const char* p, size_t n) {
  while (n > 0) {
    const size_t k = std::min<size_t>(n, 255);         // leave room for the terminating NUL
    LogElement* slot = claim();
    slot->tag = Tag::Text;
    std::memcpy(slot->u.s, p, k);
    slot->u.s[k] = '\0';
    queue_.publish();
    p += k;  n -= k;
  }
}

template <typename T, typename... Rest>
void log(const char* fmt, const T& value, const Rest&... rest) {
  const char* run = fmt;                                // start of the current text run
  for (; *fmt; ++fmt) {
    if (*fmt == '%') {
      push_text(run, static_cast<size_t>(fmt - run));   // everything before the placeholder, in one go
      push(value);
      log(fmt + 1, rest...);
      return;
    }
  }
}
void log(const char* fmt) { push_text(fmt, std::strlen(fmt)); }
```

This is a sketch: `%%` escapes and argument-count errors are left out.

### 3.3 Going Further: Push Only a Pointer to the Format String, or Parse It at Compile Time {#log-formats}

Two bigger changes, both cutting the number of slots each call pushes even further:

- **Push only a pointer to the format string and let the background thread format**: a string literal has static storage duration and can't be modified, so its address is valid for the whole run, and the hot path only needs to push an 8-byte pointer plus the argument values. This changes the protocol: the background thread has to parse the format string and fetch the right number of argument slots, and because the queue publishes one slot at a time, it can see the pointer arrive before the arguments. So you either reserve several slots and publish them together, or move to variable-length records.
- **Parse the format string at compile time**: everything static about a log statement (the format string, the argument types) is replaced at compile time by a small ID; at run time only the ID and the raw argument values are recorded, and turning them into text is left to an offline step. That is how [NanoLog](https://github.com/PlatformLab/NanoLog) works; its README reports a median of roughly 7 ns per call (its own measurement, not reproduced here). [Quill](https://github.com/odygrd/quill) takes another route: the hot thread encodes the arguments into its own queue, a backend thread does the formatting and the I/O, blocking or dropping when the queue is full is configurable, and it counts how often each happened.

**Passing by pointer only works for things that live for the whole run and never change**, and arguments don't have that property:

```cpp
void on_fill(const Fill& f) {
  std::string sym = f.symbol();
  logger.log("symbol=%\n", sym);     // suppose only sym's character pointer were queued…
}                                    // …sym is destroyed here; the background thread reads it later
```

The background thread can take over ten milliseconds to get there, long after `sym` is destroyed and the memory behind its `c_str()` pointer is invalid. So arguments are copied into the queue in the producer thread, while it still owns them.

**These changes are really one idea**: the cost of a `log` call is the number of slots each call pushes times the cost per slot, and every change that actually works shrinks the first factor instead of polishing the second.

---

## 4. Lock-Free Is a Promise About Progress, Not Speed

### 4.1 A Ladder of Guarantees {#progress-guarantees}

"Lock-free" gets used loosely. Ranked by what happens when other threads are slow, suspended or dead, there are four levels of progress guarantee, from weakest to strongest:

| Guarantee | What it promises | Typical shape |
|---|---|---|
| Blocking | Nothing: if another thread is descheduled, you can be held up indefinitely | A lock; a spin-wait on another thread's flag |
| Obstruction-free | You finish in bounded steps if everyone else pauses; under contention you can livelock | Mostly found in the literature |
| Lock-free | The system always makes progress: some thread finishes in bounded steps, but a particular thread can lose forever | A CAS retry loop |
| Wait-free | Every thread finishes in a bounded number of its own steps, whatever the others do | A fixed sequence with no retry loop |

**Lock-free promises that someone moves; wait-free promises that everyone does.** So lock-free does not mean "never waits": a thread stuck in a CAS loop is waiting; it's just that every failed retry means someone else succeeded.

### 4.2 Where the SPSC Queue Sits {#spsc-progress}

| Operation | Why | Guarantee |
|---|---|---|
| `try_claim` + `publish` (returns `nullptr` when full) | A fixed handful of loads and stores, no loop; finishing doesn't depend on the consumer | Wait-free |
| A producer that spins until a slot frees up | Whether the loop exits depends on another thread | Blocking |
| `try_peek` + `release` (returns `nullptr` when empty) | Same shape as the producer side | Wait-free |
| `fetch_add` / `fetch_sub` on a shared counter | A single `lock xadd` on x86; on ARM without the LSE extension (before ARMv8.1) it compiles to a load-exclusive/store-exclusive retry loop | Wait-free on x86, lock-free on older ARM |

Four things follow:

- **"SPSC is wait-free" is a statement about the interface, not the data structure**: it gets there by pushing the full and empty decisions to the caller. The `try_` operations fail and return, and the caller chooses to drop, retry or block. The spin-until-space version bakes "block" in. With the shared counter from 1.3 gone, the hot path is left with plain loads and stores, so the claim no longer depends on how the hardware implements atomic read-modify-writes.
- **"A crashed consumer can't hurt the producer" is only true while the queue has room**: the ring is bounded. Once it fills, the producer can only drop the item or wait, and waiting puts the consumer's health back on your critical path. A bigger buffer is further from full, but the moment it fills always comes. That's why mature logging libraries make "block or drop when full" a configuration option, and why the number of slots per call in 3.2 is a reliability question, not just a speed one.
- **Finite steps are not finite time**: wait-free bounds the number of steps you execute; it can't stop the OS from preempting you midway, a page fault, or a cache miss. Predictable latency takes three layers together: an algorithm that doesn't depend on other threads; an OS layer with pinning, isolation and real-time priority ([#1](/posts/cpu-affinity-core-isolation-numa/)); and a memory and hardware layer with pre-faulted, locked pages ([#3](/posts/hot-path-memory-allocators/)), cache-line care ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)) and no system calls on the hot path.
- **Wait-free is not automatically faster**: with little contention, a plain CAS loop usually succeeds on the first try and does less work than an implementation carrying the machinery to guarantee a bound. What wait-free buys is the upper bound, worth it when the target is a tail like P99.9. A multi-producer queue that claims slots with CAS is the textbook "lock-free but not wait-free" shape, and often the right choice.

---

## 5. Micro-Batching: The Backlog Picks the Batch Size

### 5.1 Take What's There, Never Wait to Fill {#micro-batching}

Every time the consumer processes, however many messages it handles, it pays a **fixed cost**, mostly one call downstream: one `write` system call for the logging thread, one `send` for a gateway. That costs several hundred ns to a few µs, while processing one message (copying, formatting) often takes only tens of ns. The lock-free queue itself never puts the consumer to sleep: `try_pop` returns immediately when there's nothing, and whether to spin or sleep for a while is the consumer's own choice. If it sleeps 10 ms and wakes like the logging thread in 3.1, the context switch on waking is also a fixed cost paid once per batch.

**Processing one message at a time is slow because of this fixed cost: every message pays all of it, and that caps the consumer's throughput.** With a fixed cost $F$, a per-message cost $v$, and $b$ messages per batch:

$$\text{cost per message} = \frac{F}{b} + v$$

For example, with $F = 1\ \mu s$ and $v = 50\ ns$: one message per batch costs 1.05 µs each, at most about 950,000 messages per second; 100 per batch costs 60 ns each, about 16 million per second. **When messages arrive faster than the consumer's ceiling, the backlog keeps growing, and once the ring is full the hot path's `push` starts failing.** That is what batching fixes: spread $F$ over a batch, and the ceiling approaches $1/v$.

The cost of batching is at the other end: **every message that waits for a batch to fill pays for it in latency.** So a fixed batch size is wrong in both directions: too small, and under load $F$ isn't spread thin enough and the consumer falls behind; too large and waiting to fill, and when it's quiet a message waits for later messages before it's processed. **The way out is to let the current backlog decide how many this batch takes:**

> **Batch size: chosen by the backlog**
>
> 1. **Backlog of 10 or fewer**: not busy, favor latency, one message per batch.
> 2. **Backlog of 11–100**: moderate, at most 100 per batch.
> 3. **Backlog over 100**: already behind, favor throughput, at most 1000 per batch.

```cpp
size_t pick_batch(size_t backlog) {
  if (backlog <= 10)  return 1;
  if (backlog <= 100) return 100;
  return 1000;
}

size_t drain(Queue& q, std::vector<Msg>& out, size_t target) {
  size_t n = 0;
  Msg m;
  while (n < target && q.try_pop(m)) { out.push_back(m); ++n; }   // never waits for a full batch
  return n;
}
```

The key is the loop condition: `drain` takes **at most** `target` messages and stops the moment the queue is empty; it never waits to fill. With no backlog, a batch is a single message and adds no latency at all; batches only grow when messages have already piled up, and those messages were going to wait anyway. The batch size follows the load without a timer.

> **Decide first whether to batch by backlog**
>
> - **Each downstream call has a fixed cost and accepts several messages at once** (a log `write`/`writev`, writing to disk, sending metrics, several messages in one `send`): worth it. The more $F$ exceeds $v$, the more throughput batching buys.
> - **The load comes in bursts** (a flood at the open or on news, quiet the rest of the time): the best fit. When it's quiet, one message per batch adds no latency; when the flood arrives, batches grow by themselves and the consumer isn't overwhelmed.
> - **The fixed cost is already small, or the downstream only takes one message at a time**: there's no $F$ to spread, and batching saves little.
> - **Only the latest message matters** (a strategy reading market data, where old quotes are already stale): don't work through the backlog one by one; coalesce it so each instrument keeps only its latest update, and skip the old ones.
> - **Each message has a hard latency limit**: messages late in a batch wait for the ones before them. With 1000 per batch at 50 ns each, the last one waits about 50 µs longer. Set the maximum batch from that limit.

### 5.2 Read the Backlog from the Queue, Not a Counter {#backlog}

The tempting answer is a counter for the backlog: `fetch_add(1)` on enqueue, `fetch_sub(batch_size)` after each batch. That's the counter both cores fight over from 1.3 again, and it isn't even exact: the count is bumped after the enqueue, so a fast consumer can take the message and decrement before the producer has incremented. For an unsigned counter the value briefly becomes an enormous number, and a read that lands in that moment sees a huge backlog.

So ask the queue directly. The cost shows up in the type: a generic batcher only knows `try_pop` and can't see the queue's indices, so it requires the queue type to provide an O(1) approximate size:

```cpp
template <typename Q, typename Msg>
concept BatchSource = requires(Q q, Msg& m) {
  { q.try_pop(m) }   -> std::convertible_to<bool>;
  { q.size_approx() } -> std::convertible_to<size_t>;
};
```

An approximate value is enough: it only picks one of three tiers, and being off by a few messages doesn't change the result.

## In Practice {#in-practice}

The counter that made two cores fight in 1.3 matches the {{% bottleneck-ref "shared-counter" "plain" %}} card below: what perf shows, how to fix it, how to verify the fix.

{{% bottleneck "shared-counter" %}}
