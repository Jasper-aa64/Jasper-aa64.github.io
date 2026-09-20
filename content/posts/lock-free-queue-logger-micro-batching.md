---
title: "Trading System Notes #4: Lock-Free Queues and Micro-Batching"
date: 2026-09-20
slug: "lock-free-queue-logger-micro-batching"
description: "How a single-producer single-consumer ring buffer avoids locks — the power-of-two mask, the two-step handoff, the memory order each side needs — and the traps that quietly bring contention back: a shared element counter, a full-check that reads the other core on every call, a log call that pushes one character per slot. Then a logger and a micro-batcher built on top, and what lock-free and wait-free actually promise."
summary: "A lock-free SPSC queue works because every shared variable has exactly one writer: each side updates only its own counter and merely reads the other's. The rest is keeping that property from being quietly undone — a shared element count both cores fight over (subtract two counters instead), a full-check that reads the other core on every call (cache the other side's cursor, which can only be wrong in the safe direction), a mirrored mapping that removes the wrap-around seam, and a logger that pushes one character per slot (thirty slots for one log line, five as text runs). It ends with the vocabulary that keeps lock-free claims honest: SPSC is wait-free only through a fail-fast interface, finite steps are not finite time, and a bounded queue must always choose between dropping and blocking."
categories: [Systems]
tags: [cpp, lock-free, wait-free, spsc, ring-buffer, atomics, logging, micro-batching, hft, low-latency]
toc: true
homepage: false
---

# Trading System Notes #4: Own Your Counter, Read Theirs — SPSC Queues, a Logger Built on One, and Micro-Batching

> **One-line thesis**: a lock-free single-producer single-consumer queue works because every shared variable has exactly one writer — each side updates only its own counter and merely reads the other's, so the two cores never fight over a write. Every optimization below shrinks the read traffic that remains; every trap below — a shared element count, a per-character log push, a queue that waits when full — quietly puts a cross-core cost or a cross-thread dependency back.

## What You're Actually Fighting

A hot thread that has to hand work to another thread — a log line, a market-data tick, an order event — can't reach for a mutex. Not because the lock instruction is slow (uncontended, it's cheap), but because of what a *contended* lock can turn into: the loser goes to sleep in the kernel, and when it wakes up is the scheduler's decision, not yours. If the thread holding the lock is a low-priority background worker, you've built a priority inversion onto your own critical path. What you're avoiding isn't a number of nanoseconds; it's a latency distribution with a long tail you don't control.

So the goal isn't "fast", it's "bounded". A lock-free queue is the tool, and this post follows one from the ring buffer up to two things built on it — a logger and a micro-batching processor — and closes by asking what "lock-free" and "wait-free" actually promise. The surrounding hygiene is assumed: the hot thread is pinned and isolated ([post #1](/posts/cpu-affinity-core-isolation-numa/)), the memory it touches is locked and pre-faulted ([post #3](/posts/hot-path-memory-allocators/)), and the cache-line mechanics from [post #2](/posts/memory-ordering-false-sharing-dependency-chains/) are on hand — the release/acquire pairing and the price of a contended line show up on almost every line below.

---

## 1. The Ring: Two Counters and a Mask

A single-producer single-consumer (SPSC) queue is a fixed array of slots plus two counters. The producer owns `write_idx` — only it ever stores to it. The consumer owns `read_idx`. Each side *reads* the other's counter to learn whether there's room (producer) or data (consumer), but never writes it. That asymmetry is the whole design: with one writer per variable there is nothing to lock and nothing to retry.

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
    const size_t w = write_idx_.load(std::memory_order_relaxed);   // my own counter
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

Three details in there are worth slowing down for.

**The mask.** The counters only ever increase; a slot is `idx & mask_`, where `mask_ = capacity - 1`. That equals `idx % capacity` for every `idx` — but only when the capacity is a power of two, because then `capacity - 1` is a run of ones and the AND simply keeps the low bits. Since the capacity is a runtime value, the compiler can't turn `%` into a shift for you; the constructor rounds the requested size up to the next power of two (`round_up_pow2` is the usual bit-smearing helper) so the hot path gets a one-cycle AND instead of a hardware divide.

**Two steps, not one.** Instead of `push(const T&)`, the producer gets a pointer to the slot, constructs the element *in place*, and then publishes. The element is written once, straight into its final home; a `push(const T&)` would build it somewhere else and copy it in. Publishing is a separate step because it's the only moment the consumer is allowed to notice the element exists.

**Each side reads its own counter relaxed, the other's acquire, and publishes its own with release.** Only the owner ever writes a counter, so a `relaxed` read of your own is enough — a thread always sees its own earlier writes. The other side's counter is the one that carries information across cores. The producer's release store of `write_idx_` guarantees the slot's contents are visible to any consumer whose acquire load sees the new index; the consumer's release store of `read_idx_` guarantees it has finished reading a slot before a producer that observes that slot as free overwrites it. That's the release/acquire pairing from [post #2](/posts/memory-ordering-false-sharing-dependency-chains/) doing real work. On x86 a release store compiles to an ordinary `mov` — the ordering is free; on ARM it's a `stlr`, and it isn't.

One precedence trap, if you write the full-check with wrapped (masked) indices instead of monotonic counters: `(w + 1) & mask == r & mask` does *not* mean what it looks like. `==` binds tighter than `&`, so it parses as `(w + 1) & (mask == r) & mask`, and the "is it full?" test is almost always false — the producer cheerfully overwrites unread data. Parenthesize both masked operands, or use unwrapped counters and compare `w - r` against the capacity, as above.

---

## 2. Subtract, Don't Count: The Counter That Made Two Cores Fight

It's tempting to add a third field: an atomic element count, incremented by the producer on publish and decremented by the consumer on release, so that `size()` is a single load.

```cpp
std::atomic<size_t> count_{0};
// producer, after publishing:   count_.fetch_add(1, std::memory_order_release);
// consumer, after releasing:    count_.fetch_sub(1, std::memory_order_release);
```

That counter is the one variable *both* cores write. `fetch_add` and `fetch_sub` are read-modify-writes, and a read-modify-write needs the cache line in an exclusive state (Modified or Exclusive) — so every enqueue pulls the line away from the consumer and every dequeue pulls it back. It's the ownership ping-pong from [post #2](/posts/memory-ordering-false-sharing-dependency-chains/), with one difference worth noticing: this is *true* sharing, not false sharing. Padding the counter onto its own cache line can't help, because the two cores genuinely both want to modify the same variable.

The fix is to notice you already have the answer. The number of elements is `write_idx - read_idx`, and computing it takes two plain loads — and a load only needs the line in a shared state, with no ownership transfer:

```cpp
size_t size_approx() const {
  const size_t r = read_idx_.load(std::memory_order_acquire);    // the lagging counter first…
  const size_t w = write_idx_.load(std::memory_order_acquire);   // …then the leading one
  return w - r;
}
```

Two properties to keep. **It's a snapshot pair, not an instant.** The two loads happen at slightly different moments, so the result is approximate — fine for "roughly how backed up are we", wrong for a decision that needs an exact answer. Reading the lagging counter first makes it an over-estimate: it can never come out negative, but if both sides advance a long way between the two loads it can even read above the capacity, so clamp it if that matters. **The read order matters for an outside observer.** `w >= r` holds at every instant; reading `r` first guarantees the `w` you see is no older than that moment, so the difference can't come out negative. (The `acquire` on the first load is also what keeps the second load from being reordered ahead of it; with two `relaxed` loads the order would only be a suggestion.) Read them the other way around and a third thread — a monitoring loop, say — can pick up a `w` from before both sides moved and an `r` from after: `w - r` goes negative, which with unsigned counters wraps to an enormous number. (The producer or consumer calling `size_approx()` on itself can't hit this, because its own counter can't move in the middle of its own call. The rule exists for the public `size()` that any thread may call.)

---

## 3. Cache Their Cursor: A Stale Value That Can Only Err Safe

Look at what `try_claim()` does on every call: an acquire load of `read_idx_` — a counter the *consumer* writes. If the queue is nearly empty and nowhere near full, that read is wasted, but it isn't free: each time the consumer advances its counter, the producer's next read has to fetch the updated line across cores. The consumer's `try_peek()` has the mirror-image problem with `write_idx_`.

The fix is the locally cached copy that [post #2](/posts/memory-ordering-false-sharing-dependency-chains/) previewed for exactly this situation, now inside a real queue: the producer keeps a private `cached_read_idx_`, checks against *that*, and only when the cache says "full" pays for one real cross-core load, refreshes the cache, and checks again.

```cpp
alignas(64) std::atomic<size_t> write_idx_{0};
            size_t              cached_read_idx_ = 0;    // producer-private: rides on the producer's own line
alignas(64) std::atomic<size_t> read_idx_{0};
            size_t              cached_write_idx_ = 0;   // consumer-private

T* try_claim() {
  const size_t w = write_idx_.load(std::memory_order_relaxed);
  if (w - cached_read_idx_ == slots_.size()) {                       // looks full — the cache may be stale
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

**Why a stale cache is safe.** The consumer's counter only ever moves forward, so the producer's cached copy is always *at most* the real value — never ahead of it. Free space is computed from `capacity - (w - cached_read_idx_)`, so a stale cache can only *under*-estimate the room. It can say "full" when there's actually space — in which case the code refreshes and finds out — but it can never say "there's room" when there isn't. Every decision to *reject* a write is made on a fresh acquire load; the cache only decides whether it's worth paying for one yet. The consumer's cache is stale in the same safe direction: it may claim "empty" too early, never "data" when there's none.

There's a second, quieter win. When the consumer does refresh its cache, it typically learns that *many* elements have arrived, and can process all of them before touching the producer's line again. The cross-core read is paid once per burst rather than once per element.

---

## 4. Mirror the Addresses, Not the Data

A ring buffer of bytes — or of variable-length records — has an awkward moment: a write that starts near the end and runs past it. The usual handling splits it into two copies, one up to the physical end and one from the start, with a branch to decide when. There's a trick that removes the seam: map the *same physical memory* at two consecutive virtual addresses, so the buffer looks twice as long and the second half is a mirror of the first. A write that runs off the end of the first half just keeps going in the second, and lands exactly where the wrap-around would have put it. One `memcpy`, no branch.

It takes three steps, all Linux:

```cpp
void* base = mmap(nullptr, 2 * N, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);      // reserve addresses, nothing else
int   fd   = memfd_create("ring", 0);                                                  // an in-memory "file"…
ftruncate(fd, N);                                                                      // …N bytes long
mmap(base,                          N, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);   // first view
mmap(static_cast<char*>(base) + N,  N, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);   // second view: same pages
```

1. Reserve `2N` bytes of address space with `PROT_NONE` — it claims the addresses and nothing else.
2. Create an `N`-byte in-memory file with `memfd_create` and size it with `ftruncate`.
3. Map that file's descriptor over the first half and the second half of the reservation, both with `MAP_SHARED | MAP_FIXED`.

Both views are backed by the same pages, so `buf[i]` and `buf[i + N]` are one and the same byte.

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
║  consecutive addresses, so that a write which runs past the end  ║
║  of a ring buffer simply continues into the second copy instead  ║
║  of being split in two.                                          ║
║                                                                  ║
║  Main metaphor: a two-panel dissection diagram. Eight identical  ║
║  stone floor tiles, numbered 0 to 7, stand for the eight         ║
║  physical pages of the buffer.                                   ║
║                                                                  ║
║  Layout: side-by-side comparison (two-panel), left panel headed  ║
║  "ONE MAPPING", right panel headed "TWO MAPPINGS, SAME PAGES".   ║
║                                                                  ║
║  Objects and labels:                                             ║
║   - left panel: one row of eight tiles, numbered 0-7, with a     ║
║     heavy vertical boundary line at the right end of tile 7.     ║
║     A thick ruled arrow starts on tile 6, runs to the            ║
║     boundary and stops there; a second, separate arrow           ║
║     starts again over tile 0 — labeled "one write, cut in        ║
║     two: two copies"                                             ║
║   - right panel: a long unbroken row of sixteen tiles —          ║
║     tiles 0-7, then a second lighter, cross-hatched run of       ║
║     tiles 0-7 (the mirror). Thin dotted vertical lines drop      ║
║     from each of the sixteen tiles to a single row of eight      ║
║     physical tiles underneath, so each physical tile is          ║
║     joined to exactly two tiles above it. One single long        ║
║     ruled arrow starts on tile 6 and runs unbroken through       ║
║     the boundary across the first two mirrored tiles —           ║
║     labeled "one write, one copy"                                ║
║   - under the single row of eight physical tiles in the          ║
║     right panel: labeled "the same eight physical pages"         ║
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

![Two panels. Left: one row of eight numbered stone tiles ending at a wall, with a single write cut into two separate arrows. Right: the same eight tiles mapped twice back to back, dotted lines joining both copies to one row of eight physical pages, and one unbroken arrow crossing the boundary.](/images/lock-free-queue/mirror-the-addresses.png)

**Why the file descriptor?** You can't get this from two `MAP_ANONYMOUS` mappings: each anonymous mapping receives its own fresh, independent pages, and there is nothing for a second mapping to point at. To make two virtual ranges share pages you need a named object both can refer to — an fd here, or a System V shared-memory segment, which plays the same role.

**Everything happens at construction.** The reservation, the descriptor and both mappings are set up once; after that, every enqueue and dequeue is an ordinary memory access with no system call. It's the same move as [post #3](/posts/hot-path-memory-allocators/) — nothing happens for the first time on the hot path — and the pages deserve the same treatment: pre-fault them and lock them.

**What it costs, and when it doesn't apply.** `N` must be a multiple of the page size; a failure halfway through has to unwind cleanly (`munmap`, `close`); and the second view adds page-table entries and TLB pressure. And notice what the queue from section 1 *doesn't* need it for: with fixed-size slots, an element never straddles the end, so single-element writes never wrap mid-copy. The mirror pays off for byte streams, variable-length records, and bulk reads or writes of several elements at once — where the copy itself dominates and crossing the end is common.

---

## 5. The Logger: A Queue With a Reader Who Can Afford to Be Slow

Logging is the classic customer for this queue. The hot path wants to record something; the expensive parts — formatting, file I/O, the `write` syscall — should happen somewhere nobody is waiting. So the hot thread only fills a queue slot, and a dedicated background thread drains it.

The queue's slots have a fixed size, so what goes into one has to be a tagged union — a type tag plus room for the biggest thing you might log:

```cpp
enum class Tag : uint8_t { Char, Int, Long, Double, Text /* … */ };

struct LogElement {
  Tag tag;
  union {
    char c;  int i;  long l;  double d;  /* … the other numeric types … */
    char s[256];                          // the member that sets the price of every slot
  } u;
};   // 264 bytes on x86-64: the tag pads out to 8, then the 256-byte member
```

That `char s[256]` sets the size of every slot: an element holding a single `char` still occupies 264 bytes. A queue of 8 million of them is about 2 GiB — a deliberately large buffer, because the slow reader is going to fall behind during bursts.

The reader side is a loop that drains what's there, flushes the file, and sleeps:

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

The 10 ms sleep is a choice, not a requirement: this thread isn't latency-critical, so giving its core back beats spinning — at the price of log lines reaching the file up to ~10 ms late and a queue that has to absorb everything produced in that window. Two structural rules fall out of SPSC. **One logger instance serves exactly one producing thread** — a second producer would break the one-writer-per-counter contract, so give each thread its own logger or its own queue. And **shutdown order matters**: wait until the queue is drained, *then* stop the reader thread, then close the file. Stop the reader first and whatever was still queued is silently lost.

---

## 6. Thirty Slots for One Log Line

Here is a natural way to write the producer side: walk the format string, pushing each literal character as its own element and each `%` placeholder as a value element.

```cpp
template <typename T, typename... Rest>
void log(const char* fmt, const T& value, const Rest&... rest) {
  for (; *fmt; ++fmt) {
    if (*fmt == '%') { push(value); log(fmt + 1, rest...); return; }
    push(*fmt);                                  // one character = one 264-byte slot
  }
}
void log(const char* fmt) { for (; *fmt; ++fmt) push(*fmt); }   // no arguments left
```

Count what `log("Order Executed, id=%, price=%\n", id, price)` does: 19 characters of `Order Executed, id=`, one integer, 8 characters of `, price=`, one double, one newline — **30 pushes**, each a 264-byte element. That is 7,920 bytes, about 124 cache lines, written to record roughly 40 bytes of actual content.

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
    @media (prefers-color-scheme: dark) {
      .bg    { fill: #17161b; }
      .title { fill: #e9e7ef; }
      .row   { fill: #d7d3c8; }
      .lbl   { fill: #d7d3c8; }
      .cap   { fill: #a19caf; }
      .chr   { fill: #4a2f2c; stroke: #8f5a4c; }
      .val   { fill: #2b3038; stroke: #8391a0; }
      .txt   { fill: #33421f; stroke: #8fb257; }
      .brk   { stroke: #9a9384; }
    }
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

> Figure: both rows record the same log line. Nothing about the queue, the memory orders or the reader changed between them — only the unit of work per call did. Thirty publishes became five.

The cost shows up three ways:

- **The hot path pays per slot.** Thirty copies and thirty release stores per log call — and if the queue also maintains a shared element counter (section 2), thirty contended read-modify-writes on the line the consumer is fighting over.
- **It evicts the hot path's own data.** 7.7 KiB per call is a sizeable fraction of a typical 32–48 KB L1 data cache; a logging call that dirties a sixth to a quarter of L1 isn't free for the code that runs right after it.
- **The buffer is smaller than it looks.** 8 million slots at 30 slots per log line is room for about 280,000 log lines, not 8 million. A slow reader overflows it sooner, and "the queue is so big it never fills" loses most of its margin.

**The fix that changes nothing else: push text runs.** Instead of one slot per character, collect the literal text between placeholders and push it as a single `Text` element — at most 255 characters per slot, longer runs split across several. The example drops from 30 pushes to 5 (three text runs, two values) and from 7.7 KiB to about 1.3 KiB. Only the producer-side `log()` changes; the reader already knows how to write a text slot.

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

That's a sketch: `%%` escapes and argument-count errors are left out.

**Two bigger changes, and where each one stops working.**

*Push a pointer to the format string.* A string literal has static storage duration and can't be modified, so its address is valid for the whole run: the hot path can queue an 8-byte pointer plus the argument values, and the reader does the formatting. That changes the protocol, not just `log()`. The reader now has to parse the format string and fetch the right number of argument slots — and because the queue publishes one slot at a time, it can observe a record whose pointer has arrived but whose arguments haven't. You need to reserve several slots and publish them together, or move to variable-length records.

The trick works only because the pointee outlives the reader and never changes. Arguments don't have that property:

```cpp
void on_fill(const Fill& f) {
  std::string sym = f.symbol();
  logger.log("symbol=%\n", sym);     // suppose only sym's character pointer were queued…
}                                    // …sym is destroyed here; the reader arrives later, on another thread
```

The reader shows up after the queueing delay plus up to 10 ms of sleep — long after `sym` is gone, and a `c_str()` pointer or a stack buffer fails the same way. So arguments are *copied* into the queue, in the producer thread while it still owns them; only things that live for the whole run and never change can be passed by pointer.

*Parse the format string at compile time.* Take the previous idea to its end: everything static about a log statement — the format string, the argument types — is extracted at compile time and replaced by a small ID; at runtime only the ID and the raw argument values are recorded, and turning them into text is deferred to an offline step. That is how [NanoLog](https://github.com/PlatformLab/NanoLog) works; its README reports a median of roughly 7 ns per call (its own measurement, not one I've reproduced). [Quill](https://github.com/odygrd/quill) takes a different route: the hot thread encodes the arguments into its queue, a backend thread does the formatting and the I/O, and the queue can be bounded or unbounded, blocking or dropping when full, with counters for how often it dropped or blocked. Across all of these fixes the pattern is the same: the cost of a log call is *slots per call × cost per slot*, and every real fix shrinks the first factor instead of polishing the second.

---

## 7. Lock-Free Is a Promise About Progress, Not Speed

"Lock-free" gets used loosely. There is a ladder of guarantees, and where an operation sits depends on what happens when *other* threads are slow, suspended, or dead:

| Guarantee | What it promises | Typical shape |
|---|---|---|
| **Blocking** | Nothing: if another thread is descheduled, you can be held up indefinitely | A lock; a spin-wait on another thread's flag |
| **Obstruction-free** | You finish in bounded steps *if everyone else pauses*; under contention everyone can livelock | Mostly a stepping stone in the literature |
| **Lock-free** | The *system* always makes progress — some thread finishes in bounded steps — but a particular thread can lose forever | A CAS retry loop |
| **Wait-free** | *Every* thread finishes in a bounded number of its own steps, whatever the others do | A fixed sequence with no retry loop |

Lock-free promises that *someone* moves; wait-free promises that *everyone* does. So lock-free does not mean "never waits" — a thread stuck in a CAS loop is waiting; it's just that its waiting is always someone else's progress.

Where does the queue from section 1 sit?

| Operation | Why | Guarantee |
|---|---|---|
| `try_claim` + `publish` (producer; returns `nullptr` when full) | A fixed handful of loads and stores; no loop; finishing doesn't depend on the consumer | Wait-free |
| A producer that *spins* until a slot frees up | A loop whose exit condition is another thread's action | Blocking |
| `try_peek` + `release` (consumer; returns `nullptr` when empty) | Same shape as the producer side | Wait-free |
| `fetch_add` / `fetch_sub` on a shared counter | One atomic read-modify-write — on x86 a single `lock xadd`; on ARM without the LSE extension (before ARMv8.1) it compiles to a load-exclusive/store-exclusive retry loop | Wait-free on x86; degrades to lock-free on older ARM |

Four things follow from that.

**"SPSC is wait-free" is a statement about the interface, not the data structure.** The queue gets there by pushing the "full" and "empty" decisions out to the *caller*: the `try_` operations fail and return, and the caller chooses to drop, retry or block. The spin-until-space variant bakes the third choice in — and with it, the blocking. It also explains why dropping the shared counter from section 2 makes the claim cleaner: what's left on the hot path is loads and stores, with no dependence on how the hardware implements atomic read-modify-writes.

**"A crashed consumer can never hurt the producer" is only true while the queue has room.** The ring is bounded. When it fills, the producer has exactly two options — drop the item or wait — and "wait" puts the consumer's health back on your critical path. A bigger buffer moves the cliff further away; it doesn't remove it. That's why mature logging libraries expose the choice as configuration (Quill lets you pick queues that block or drop when full, and reports how often each happened), and why the number of slots each log call consumes in section 6 is a reliability question, not just a speed one.

**Finite steps are not finite time.** Wait-free bounds the number of steps *you* execute, no matter what the others do. It says nothing about the OS preempting you in the middle of them, a page fault, or a cache miss. Predictable latency is three layers stacked: the algorithm (operations that don't depend on other threads), the operating system (pinning, isolation, real-time priority — [post #1](/posts/cpu-affinity-core-isolation-numa/)), and memory and hardware (locked, pre-faulted pages — [post #3](/posts/hot-path-memory-allocators/); cache-line hygiene — [post #2](/posts/memory-ordering-false-sharing-dependency-chains/); no system calls on the hot path). Wait-free stops other threads from holding you up; the other two layers stop *you* from being held up.

**And wait-free is not automatically faster.** With little contention, a plain CAS-loop version usually succeeds on the first attempt and does less work than a construction carrying the machinery to guarantee a bound. What wait-free buys is the upper bound — worth having when the target is the tail (P99.9), not the mean. A multi-producer queue that claims slots with CAS is the textbook lock-free-but-not-wait-free shape, and often the right one.

---

## 8. Micro-Batching: The Backlog Picks the Batch Size

Batching amortizes per-message overhead — one wake-up, one downstream call for many messages — but every message that waits for a batch to fill pays for it in latency. A fixed batch size is wrong in both directions: too small under load, too slow when idle. The way out is to let the backlog choose:

| Backlog | Mode | Batch size |
|---|---|---|
| ≤ 10 | Not busy — optimize latency | 1 |
| ≤ 100 | Moderate | 100 |
| > 100 | Already behind — optimize throughput | 1000 |

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

The important line is the loop condition: `drain` takes **at most** `target` messages and stops the moment the queue is empty. It never waits for a batch to fill. So when there's no backlog, the batch is a single message and adds no latency at all; batches only grow when messages have *already* piled up — when they were going to wait anyway. The batch size follows the load without a timer.

**Where does `backlog` come from?** The tempting answer is a counter: `fetch_add(1)` on enqueue, `fetch_sub(batch_size)` after each batch. That's section 2's contended line again — and it isn't even exact. The counter is bumped *after* the enqueue, so a fast consumer can drain a message and decrement before the producer has counted it; with an unsigned counter the value wraps to an enormous number for a moment, and a read that lands in that window sees a huge backlog. Ask the queue instead. That has a cost, and it shows up in the type system: a generic batcher that only knows `enqueue` and `dequeue` can't see the queue's counters, so the queue type has to promise an O(1) approximate size:

```cpp
template <typename Q, typename Msg>
concept BatchSource = requires(Q q, Msg& m) {
  { q.try_pop(m) }   -> std::convertible_to<bool>;
  { q.size_approx() } -> std::convertible_to<size_t>;
};
```

An approximate snapshot is enough — it only selects one of three tiers, and being off by a few messages changes nothing. Not counting yourself isn't free; you pay for it with a stronger requirement on the queue.

---

## Recap

1. **One writer per variable is the whole design.** Each side stores only its own counter and reads the other's, with `relaxed` for its own, `acquire` for theirs and `release` to publish. Nothing to lock, nothing to retry.
2. **A shared element counter re-creates the fight you removed.** Both cores read-modify-write one line, and no padding fixes true sharing. Subtract the two counters instead — reading the lagging one first — and accept an approximate snapshot.
3. **A cached copy of the other side's cursor can only be wrong in the safe direction.** The counters only move forward, so a stale cache can claim "full" or "empty" too early but never the reverse; the cross-core read is paid only when the cache runs out, and once per burst rather than once per element.
4. **Double mapping mirrors the addresses, not the data.** Same pages at two consecutive addresses turn a split copy into one — worth it for byte streams and bulk copies, not for fixed-size slots — and it's all done at construction.
5. **A log call costs slots per call × cost per slot.** Pushing text runs cuts thirty slots to five with no protocol change; pointers and compile-time parsing cut it further but change the protocol, and a pointer is only safe for something that outlives the reader and never changes — the format string, not the arguments.
6. **Lock-free, wait-free and predictable are three different claims.** SPSC is wait-free only through a fail-fast interface; the spin-until-space variant is blocking. Finite steps are not finite time — the OS and memory layers still have to do their part.
7. **A bounded queue always has to choose between dropping and blocking.** "The consumer can't hurt the producer" holds only while there's room, which makes slots-per-call a reliability number.
8. **Micro-batching adapts by taking what's there.** The backlog picks a tier, the drain never waits to fill a batch, and the backlog itself comes from the queue rather than from a counter — at the price of a stronger interface requirement on the queue type.
