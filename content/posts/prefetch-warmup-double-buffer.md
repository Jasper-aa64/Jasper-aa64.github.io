---
title: "Trading System Notes #14: Prefetching, Cache Warming, and Double Buffering"
date: 2026-10-15
slug: "prefetch-warmup-double-buffer"
description: "Much of the hot path's time goes to waiting for data. Software prefetch only helps where the hardware can't guess the address and you know it early; cache warming has to run on the core that does the work; a double buffer with an atomic index lets readers skip locks, but a fast writer corrupts the copy being read, measured at over 1500 torn reads in 2 seconds."
summary: "There are three ways to get data into cache ahead of time, each with a precondition: prefetching needs you to know the address before the hardware does, warming has to happen on the core that reads the data, and double buffering needs a guarantee that the writer never returns to a copy a reader hasn't finished."
chapter: 1
categories: [Systems]
tags: [cpp, prefetch, cache-warming, double-buffering, lock-free, hft, low-latency]
toc: true
math: true
light: true
---

Handling one market data message on the hot path spends a lot of time waiting for data: when the entry it needs isn't in cache, that's 70–120 ns, or 280–480 cycles at 4 GHz. This post covers three ways to get data there first, or keep it there, each with an easy-to-miss precondition. Software prefetch only helps where the hardware can't guess the address and you know it early. Warming has to run on the core that actually reads the data. A double buffer with an atomic index lets readers skip locks, but a writer that writes fast enough corrupts the copy a reader is in the middle of reading.

## 1. Software Prefetch: Addresses the Hardware Can't Guess but You Know Early

### 1.1 What the Hardware Already Prefetches

Prefetching means issuing the request before the data is actually used, so the cache line is already there when it's needed. The CPU does this on its own all the time. Hardware prefetchers watch the addresses of cache misses: when they see accesses walking forward through memory, or stepping by a fixed stride, they fetch the next few lines ahead, and they also pull in adjacent lines. Out-of-order execution helps too: later independent loads don't wait for earlier ones to finish and can be issued early ([Ref 2.3](/ref/cpu-memory/#in-flight)). So scanning an array in order, or stepping by a fixed stride, needs no hand-written prefetch, which is why hand-written prefetches show no gain in most tests.

Hardware prefetching has two blind spots. First, it usually doesn't cross a 4 KiB page: the next page's physical address isn't necessarily adjacent, so it doesn't know where to fetch. Second, accesses whose addresses are computed from data have no pattern for it to learn: a hash table bucket is computed from the key, the address in `a[idx[i]]` needs `idx[i]` read first, and the next node of a linked list needs the current node read first. Papers describe all sorts of prefetchers that try to learn these patterns; common CPUs mostly ship the stride-based and region-based kinds.

### 1.2 `__builtin_prefetch`: Which Instruction Each Argument Maps To

GCC and Clang issue a prefetch with `__builtin_prefetch(addr, rw, locality)`: `rw` is 0 (prefetch for reading) or 1 (prefetch for writing), and `locality` from 3 down to 0 says how often the data will be reused and how close to the core it should go. The measured x86 instructions are:

| Code | Instruction | Meaning |
|---|---|---|
| `__builtin_prefetch(p, 0, 3)` | `prefetcht0` | Into all cache levels, including L1 |
| `__builtin_prefetch(p, 0, 2)` | `prefetcht1` | Into L2 and beyond |
| `__builtin_prefetch(p, 0, 1)` | `prefetcht2` | Into L3 and beyond |
| `__builtin_prefetch(p, 0, 0)` | `prefetchnta` | Non-temporal: used once, keep cache pollution low |
| `__builtin_prefetch(p, 1, 3)` | `prefetchw` | Prefetch for writing, taking ownership early; falls back to `prefetcht0` when `-march` lacks it |

A prefetch is only a hint: an invalid address doesn't fault, and later instructions don't wait for it. But like an ordinary miss it occupies an LFB (line fill buffer) entry, and the lines it brings in evict others.

### 1.3 When It Helps: A Batch of Independent Accesses with Computed Addresses

The typical case is a batch of order IDs, each looked up in a hash table. The address of each lookup is computed from the order ID, so the hardware can't guess it; but the whole batch of IDs is already in hand, so which slot the lookup D steps later will read can be computed now. So while handling element `i`, issue a prefetch for element `i + D`:

```cpp
struct Slot { uint64_t key; uint64_t value; };

inline size_t slot_of(uint64_t id, int bits) { return (id * 0x9E3779B97F4A7C15ull) >> (64 - bits); }

uint64_t lookup_batch(const Slot* slots, int bits, const uint64_t* ids, int n) {
    constexpr int D = 8;                                         // prefetch distance: 8 lookups ahead
    uint64_t sum = 0;
    for (int i = 0; i < n; ++i) {
        if (i + D < n)
            __builtin_prefetch(&slots[slot_of(ids[i + D], bits)]);   // the slot read D lookups later
        sum += slots[slot_of(ids[i], bits)].value;                 // the slot read now
    }
    return sum;
}
```

These lookups are independent, and out-of-order execution could already issue several at once, but how far ahead it can look is limited by the ROB size and the number of instructions per lookup: with more work per lookup, the window can't reach the later lookups. Prefetching takes "issue the request early" out of the window and lets up to $D$ misses be in flight at once. If 8 lookups all go to memory, waiting for them one after another takes $8 \times 90 = 720$ ns; with all of them in flight, the total is close to a single memory latency. $D$ has to be large enough that the time after the prefetch is issued covers one memory latency:

$$D \approx \frac{\text{memory latency}}{\text{time per iteration}}$$

With a memory latency of about 90 ns and about 10 ns per iteration, $D$ should be around 9. Too small, and the data hasn't arrived when it's used; too large, and fetched lines get evicted before they're used.

Conversely, prefetching 8 elements ahead while scanning an `int` array in order is 32 bytes ahead, most likely in the same cache line, which the hardware fetched long ago; it only adds instructions.

For pointer chasing such as a linked list, prefetching can't help a single chain: the next node's address isn't known until the current node arrives, so the request can't be issued early ([#10, section 2](/posts/pointer-memory-access/)). What you can do is walk several independent chains at once so several misses are in flight, or replace the chain with an array.

## 2. Cache Warming: Keeping the Hot Path's Data and Instructions in Cache

### 2.1 Why It Goes Cold

A trading hot path doesn't run continuously: market data comes in bursts, and orders go out only occasionally. In the gaps, other code runs, logging, statistics, other strategies, and its data and instructions push the hot path's cache lines out of L1 and L2, and wipe the history stored in the branch predictor. When the next message arrives, the hot path's entries have to come from L3 or even memory, its instructions have to be fetched again and its branches relearned, so the first one is often especially slow.

### 2.2 Data Warming and Instruction Warming (Dry Runs)

Warming means pulling these back in during idle time. Data warming reads the data the hot path will use, periodically; one element per cache line is enough, with `volatile` so the compiler doesn't delete reads nobody uses. Instruction warming goes further: run the whole path with fake market data, from receiving the message, computing the signal and risk checks to building the order, stopping just before the order is sent. This is called a **dry run**. It touches exactly the data, instructions and branches the real path touches, which is more complete than reading data alone, and it warms the address translations in the TLB as well.

### 2.3 It Has to Run on the Core Doing the Work

L1 and L2 are private to each core ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)). Reading the data from another thread warms the L1 and L2 of that thread's core; when the working core reads it, the line is either in L3 or in another core's cache and has to be moved over, about 20–100 ns ([Ref 2.1](/ref/cpu-memory/#latency)). So warming belongs on the hot thread itself, for example in the busy-poll loop that receives market data: when no message has arrived for a while, warm a small piece.

Two more points. Warming should only read, not write: a write takes the line exclusive and invalidates every other core's copy. And each warming step should be small, a few cache lines, then go back to check for new messages, so a real message never waits behind a long warm-up.

## 3. Double Buffer with an Atomic Index: Readers Don't Lock

### 3.1 How It Works

Data like parameter tables or instrument definitions is updated occasionally by a control thread and read constantly by the trading thread. With a lock, the trading thread has to wait whenever the control thread is holding it to write. Double buffering keeps two copies: the writer writes the new data into the copy nobody is reading, then changes an atomic index to point at the new copy; the reader first reads the index, then reads the copy it points to:

```cpp
template<typename T>
class DoubleBuffer {
public:
    DoubleBuffer(size_t size) : currentIndex(0) {
        buffers[0] = std::vector<T>(size);
        buffers[1] = std::vector<T>(size);
    }
    void update(const std::vector<T>& newData) {
        size_t nextIndex = 1 - currentIndex.load(std::memory_order_relaxed);
        std::copy(newData.begin(), newData.end(), buffers[nextIndex].begin());
        std::atomic_thread_fence(std::memory_order_release);   // data fully written before the index changes
        currentIndex.store(nextIndex, std::memory_order_relaxed);
    }
    std::vector<T> read() const {
        size_t index = currentIndex.load(std::memory_order_relaxed);
        std::atomic_thread_fence(std::memory_order_acquire);   // read the data only after reading the index
        return buffers[index];
    }
private:
    std::vector<T> buffers[2];
    std::atomic<size_t> currentIndex;
};
```

The two fences pair up: the writer's release fence ensures all the data is written before the index changes, and the reader's acquire fence ensures that once it sees the new index, the data it reads is the fully written copy ([#2](/posts/memory-ordering-false-sharing-dependency-chains/) covers acquire / release).

### 3.2 A Fast Writer Writes into the Copy Being Read

This design assumes the writer won't come back to a copy before the reader has finished reading it. Nothing guarantees that. The reader sees index 0 and starts copying `buffers[0]`; meanwhile the writer updates once, writing `buffers[1]` and changing the index to 1, then immediately updates again, and the next copy is `buffers[0]`, the one being copied. What the reader gets is half old data and half new.

Measured: the writer updates nonstop, filling the whole array (4096 `int`s) with one value each time; the reader reads a copy each time and checks that every element is equal. In 2 seconds it read about 1.3 million times, and 1551–1933 of those reads contained a mix of old and new values, in each of 3 runs.

To use this structure, you have to guarantee that before the writer returns to a copy, everyone reading that copy has finished. Common ways:

- **Version number** (seqlock): before writing, bump the version to an odd number, and after writing bump it to even; the reader reads the version before and after reading the data, and retries if it's odd or has changed. Good for small data such as a top-of-book snapshot.
- **Triple buffer**: add a spare buffer. The writer always writes the spare, then swaps it with "the latest" in one atomic exchange; when the reader wants to read, it also swaps the one it holds for the latest in one atomic exchange. The writer can never touch the reader's copy; the price is that the reader only gets the latest data and intermediate updates may be skipped, which fits "I only want the latest quote, the latest parameters".
- **Reclaim after readers leave**: each update writes a fresh copy and swaps a pointer, and the old copy is reclaimed only after every reader has left it, the RCU approach.

Also, `read()` returns a `std::vector` by value, which allocates and copies the whole thing on every read; on the hot path, read in place instead of copying.

### 3.3 Warming on the Wrong Core

Double buffers like this often come with a "dry-run warm-up": after each `update`, read both copies once per cache line. But `update` runs on the writer's thread, so by 2.3 it warms the writer's core, and the trading thread's core gets nothing. The standby copy will be overwritten by the next update anyway, so warming it only helps the writer. If you want to warm, do it in the trading thread's own idle time.
