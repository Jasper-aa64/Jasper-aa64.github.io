---
title: "Trading System Notes #20: Measuring Latency with the TSC"
date: 2026-11-02
slug: "tsc-latency-measurement"
description: "The most direct way to time a piece of code is to read the TSC at both ends. But the TSC counts time at a fixed rate, not the cycles the core actually ran; rdtsc does not wait for earlier instructions to finish, so short regions need fences, and fences make the measurement itself heavier; rdtscp also tells you which core you read on, and comparing readings across cores relies on the cores' TSCs being synchronized. On the hot path, record ticks only and leave conversion and output to another thread."
summary: "What a TSC reading means, when it is taken, which core it is taken on, and how to record timestamps on the hot path."
chapter: 1
categories: [Systems]
tags: [cpp, tsc, rdtsc, rdtscp, latency, measurement, hft, low-latency]
toc: true
math: true
---

To find out how long it takes from receiving a market-data update to sending an order, the most direct way is to read the time at both ends and subtract. One `clock_gettime` call costs about 20–30 ns, yet a piece of code on a trading hot path is often only a few hundred ns, so the timing itself takes a tenth of it. That is why low-latency systems usually read the CPU's TSC directly: one instruction, about 10 ns. Reading a hardware counter directly means answering three questions yourself: what the number stands for, whether it is read where you wrote the read, and how to turn it into nanoseconds. Part 1 covers the first two and which core a reading comes from; conversion is left to Part 2.

## 1. Reading the TSC: What You Read, and When

### 1.1 TSC (Time Stamp Counter): a Fixed-Rate Counter in Every Core

The TSC is a 64-bit counter in every logical core, cleared at power-on and counting up from then on. It has no box of its own on the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a>; it is just a register in the core.

On early CPUs the TSC followed the core clock: it slowed down when the core slowed down and stopped in deep sleep, which made it useless for timing. Today's CPUs have an invariant TSC: it runs at a fixed rate whether the core is throttled, asleep or in Turbo. The rate is usually close to the CPU's nominal frequency; on the machine used in this post it is 3.593 GHz. On Linux, `constant_tsc` and `nonstop_tsc` among the flags in `/proc/cpuinfo` mean you have this kind.

So **the TSC counts time, not the cycles the core actually ran**. With the core in Turbo at 4.5 GHz and the TSC running at 3.0 GHz, 100 TSC ticks are 33 ns, during which the core ran 150 cycles. To count core cycles, use perf's `cycles` event, which comes from the performance counters, not the TSC.

Counting at 3.6 GHz, 64 bits take about 160 years to wrap, so overflow is not a concern. The cores of one CPU start counting from the same reset, so their readings are synchronized; Linux also checks at boot, and if they are not, it prints `tsc: Marking TSC unstable` and switches to another clock source. 1.4 relies on this.

### 1.2 rdtsc: 6–12 ns per Read, and the Reading Only Jumps About Every 10 ns

The TSC is read with the `rdtsc` instruction. It dates from the 32-bit era, when one register couldn't hold 64 bits, so the result comes in two halves: the low 32 bits in EAX, the high 32 bits in EDX, joined to form the reading:

```cpp
inline uint64_t rdtsc() noexcept {
    unsigned int lo, hi;
    __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
    return (uint64_t(hi) << 32) | lo;
}
```

When you write the assembly yourself, don't drop `volatile`. Without it the compiler treats the asm as a computation with no inputs and a fixed result, so two reads can be merged into one: measured, Clang 18 `-O2` compiles "read twice and subtract" to returning 0. The compiler's own `__rdtsc()` (header `<x86intrin.h>`) compiles to the same instruction and is never merged, so prefer it.

Why not just call `clock_gettime`? In user space (the vDSO) it also reads the TSC, but each call adds a function call and a multiply-and-shift to convert to nanoseconds, about 20–30 ns in total. `rdtsc` is only the read, about 20–40 cycles, 6–12 ns. **So on the hot path, record ticks only and convert later.**

How short an interval the reading can resolve depends on how it actually advances. By frequency, one tick is 1 / 3.593 GHz ≈ 0.28 ns. But on the AMD machine used here, the reading doesn't go up by 1 every 0.28 ns; it jumps about every 10 ns, by 36 each time (36 × 0.28 ≈ 10 ns). Read twice within the same 10 ns and the second read is only 1 higher: that 1 is there so readings never repeat, not because 0.28 ns really passed.

That has two consequences. First, you can't measure `rdtsc` itself precisely on this machine: two back-to-back reads differ by 36 almost every time, exactly one jump, so all you can see is that a read takes at most about 10 ns. Second, **a single measurement shorter than 10–20 ns mostly reads quantization error**: a 5 ns piece of code may show a difference of 1 or of 36, depending on whether a jump fell in between. To measure code that short, run it many times and divide the total, or measure many times and look at the distribution.

### 1.3 Out-of-Order Execution: rdtsc Doesn't Wait for Earlier Instructions

Two reads and a subtraction are not enough, because the CPU executes out of order (the "Rename + ROB" box on the hardware map). `rdtsc` does not wait for the instructions before it to finish, and instructions after it may start executing before it. So in this:

```cpp
uint64_t t0 = __rdtsc();
int r = parse(msg);        // the code being measured
uint64_t t1 = __rdtsc();
```

both edges are fuzzy: the first few instructions of `parse` may start before `t0` is read, and when `t1` is read the last few may not have finished. When the measured code is only tens of ns, the measured number can come out shorter than the real one.

The fix is to pin the edges with fences. `lfence` means: the instructions after it may not start until all the instructions before it have finished. `rdtscp` is a variant of `rdtsc` that waits for all earlier instructions to execute and all earlier loads to complete before reading, but does not hold back later instructions. So the start and end look like this:

```cpp
inline uint64_t tsc_begin() {      // start mark: read only after earlier instructions finish
    _mm_lfence();
    uint64_t t = __rdtsc();
    _mm_lfence();                  // later instructions may not start early
    return t;
}

inline uint64_t tsc_end() {        // end mark: rdtscp waits for earlier instructions before reading
    unsigned aux;
    uint64_t t = __rdtscp(&aux);
    _mm_lfence();                  // later instructions may not start early
    return t;
}
```

This behavior of `lfence` is defined by Intel. On AMD, `lfence` only waits like this once the operating system turns on a switch, which recent Linux and Windows do by default; on older systems AMD recommends `mfence`. If you also need earlier stores to be visible to other cores, the sequence Intel's manual gives is `mfence; lfence; rdtsc`.

Fences have a cost. On this machine, the difference between two fenced reads goes from one jump to two, about 20 ns; and the fences stop the measured code from overlapping with the code around it, so what you measure is no longer exactly how it normally runs. **Fences make the edges accurate, at the cost of a heavier measurement and code that no longer overlaps with its neighbors.** So use fences for short code of tens of ns (microbenchmarks); for marks on a production hot path, which measure whole spans of several µs where an edge error of ten-odd ns is acceptable, a plain `rdtsc` is the usual choice.

The compiler moves code too. If nothing uses the result of the measured code, the compiler may delete it entirely, or move computations that don't touch memory outside the reads. In a microbenchmark, make sure the result is used, for example by writing it to a `volatile` variable.

### 1.4 rdtscp and Cores: Knowing Which Core You Read On

Besides the TSC, `rdtscp` also reads a register called `IA32_TSC_AUX` into ECX, which is the `aux` in the code above. Linux sets this register on each core to "NUMA node × 4096 + core number", and `getcpu` in the vDSO relies on it. If the two reads at start and end give different `aux` values, the thread was moved to another core in between: the span includes a migration ([#1](/posts/cpu-affinity-core-isolation-numa/) 1.1), and the two cores' readings may not line up exactly, so throw the sample away or mark it separately. A hot thread pinned to one core as in #1 never hits this.

There is a more common case of comparing readings across cores: a producer on core 2 stamps a message as it writes it into a queue, the consumer on core 4 stamps it again when it takes it out, and the difference is how long the message sat in the queue. This works because of what 1.1 said: the cores of one machine have synchronized TSCs. In a virtual machine, the hypervisor may add an offset to the TSC, or skew it when a virtual CPU moves to another physical core, and then subtracting across cores is no longer reliable. The TSCs of two machines have nothing to do with each other and cannot be subtracted at all.

To check that a machine supports all this, look at CPUID: bit 27 of EDX in leaf `0x80000001` is `rdtscp`, and bit 8 of EDX in leaf `0x80000007` is invariant TSC. On Linux, `grep -o 'rdtscp\|constant_tsc\|nonstop_tsc' /proc/cpuinfo` is easier.

### 1.5 Marks on the Hot Path: Record Ticks, Leave Conversion and Output to Another Thread

A mark adds time to the hot path itself: about 10 ns to read the TSC, plus a memory write or an enqueue to record it. So the hot path does only those two steps, storing the difference in ticks into a preallocated array, or handing it to the asynchronous logger of [#4](/posts/lock-free-queue-logger-micro-batching/), with conversion, formatting and file writes done on another thread. A common way to write it is a pair of macros:

```cpp
#define START_MEASURE(TAG) const auto TAG = Common::rdtsc()

#define END_MEASURE(TAG, LOGGER)                                                  \
    do {                                                                          \
        const auto end = Common::rdtsc();                                         \
        LOGGER.log("% RDTSC " #TAG " %\n", Common::getCurrentTimeStr(&time_str_), \
                   (end - TAG));                                                  \
    } while (false)
```

`LOGGER.log` only puts its arguments into a lock-free queue, and the logger thread formats them later. The `end - TAG` in the log is a tick count, not nanoseconds. Every mark adds tens of ns to the hot path, so in production mark only a few key points, or sample.

A span measured with the TSC suits a piece of code within one thread. But a trade goes from the market-data thread to the strategy thread to the order thread, often across processes, from receiving the update to sending the order. To know how long each leg took, every stage records an **absolute timestamp**, and afterwards the records of each stage are joined per order. This kind of record is called tick-to-trade (TTT), commonly written as:

```cpp
#define TTT_MEASURE(TAG, LOGGER)                                                  \
    do {                                                                          \
        const auto TAG = Common::getCurrentNanos();                               \
        LOGGER.log("% TTT " #TAG " %\n", Common::getCurrentTimeStr(&time_str_), TAG); \
    } while (false)
```

`getCurrentNanos()` returns nanoseconds since 1970, i.e. the system clock. Several processes on one machine could in fact share the TSC, but to line up with timestamps in exchange reports or records on another machine, you need the system clock that every machine has synchronized (via PTP). **Use the TSC for spans within one thread, and a shared absolute clock to build timelines across components and machines.**

A single measurement means little: the same code takes 300 ns one time and 2 µs the next when it hits a cache miss. What matters is the distribution over many measurements: the median, the 99th percentile, the maximum. That is the subject of the next item, measuring trading-system performance.
