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

On early CPUs the TSC followed the core clock: it slowed down when the core slowed down and stopped in deep sleep, which made it useless for timing. Today's CPUs have an invariant TSC: it runs at a fixed rate whether the core is throttled, asleep or in Turbo. The rate is usually close to the CPU's nominal frequency, for example 3.593 GHz. On Linux, `constant_tsc` and `nonstop_tsc` among the flags in `/proc/cpuinfo` mean you have this kind.

So **the TSC counts time, not the cycles the core actually ran**. With the core in Turbo at 4.5 GHz and the TSC running at 3.0 GHz, 100 TSC ticks are 33 ns, during which the core ran 150 cycles. To count core cycles, use perf's `cycles` event, which comes from the performance counters, not the TSC.

Counting at 3.6 GHz, 64 bits take about 160 years to wrap, so overflow is not a concern. The cores of one CPU start counting from the same reset, so their readings are synchronized; Linux also checks at boot, and if they are not, it prints `tsc: Marking TSC unstable` and switches to another clock source. 1.4 relies on this.

### 1.2 rdtsc: 6–12 ns per Read, and on AMD the Reading Only Jumps About Every 10 ns

- The most direct way to time code is to read the TSC at both ends and subtract.
- Whether that difference can be trusted depends on two things: how long one read takes, and how short an interval the reading can resolve.

**1. How to read it**

- `rdtsc` returns the 64-bit reading in two halves: the low 32 bits in EAX, the high 32 bits in EDX. It dates from the 32-bit era, when one register couldn't hold 64 bits.

```cpp
inline uint64_t rdtsc() noexcept {
    unsigned int lo, hi;
    __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
    return (uint64_t(hi) << 32) | lo;
}
```

- When writing the assembly yourself, don't drop `volatile`. Without it the compiler treats the asm as a computation with a fixed result and can merge two reads into one: measured, Clang 18 `-O2` compiles "read twice and subtract" to returning 0.
- **Prefer the compiler's own `__rdtsc()`** (header `<x86intrin.h>`): same instruction, never merged.

**2. Why not `clock_gettime`**

- In user space (the vDSO), `clock_gettime` also reads the TSC.
- But each call adds a function call and a multiply-and-shift to convert to nanoseconds: 20–30 ns per call.
- `rdtsc` is only the read: about 20–40 cycles, 6–12 ns.
- **So on the hot path, record ticks only and convert later.**

**3. The reading moves in steps**

- By frequency, one tick is 1 / 3.593 GHz ≈ 0.28 ns.
- But measured on AMD Zen parts (Ryzen, EPYC), the reading jumps only about every 10 ns, by 36 each time (36 × 0.28 ≈ 10 ns). Intel parts usually show no fixed step; back-to-back differences vary. A few back-to-back reads tell you which kind your machine is.
- Read again within the same 10 ns and you get only 1 more. That 1 is there so readings never repeat, not because 0.28 ns really passed.
- **The staircase is how the counter itself updates, unrelated to how fast `rdtsc` reads**: even if a read took no time, you'd see the same steps. 3.593 GHz ÷ 36 ≈ 100 MHz, so the reading appears to follow a roughly 100 MHz reference clock, adding 36 per tick (inferred from the numbers, not from documentation).

<a href="/images/tsc-latency-measurement/rdtsc-steps.en.svg" target="_blank" rel="noopener"><img src="/images/tsc-latency-measurement/rdtsc-steps.en.svg" alt="Horizontal axis: real time 0–40 ns; vertical axis: rdtsc reading. Ideally the reading rises by 1 every 0.28 ns, a straight line; in reality it is a staircase, jumping by 36 about every 10 ns. Case A: 5 ns of code falls inside one step, readings 1036 and 1037, difference 1, converted to 0.28 ns: too short. Case B: the same 5 ns spans a jump, readings 1072 and 1108, difference 36, converted to 10 ns: too long." loading="lazy" decoding="async"></a>

**4. What it does to measurements**

- You can't measure `rdtsc` itself precisely: two back-to-back reads differ by 36 almost every time, exactly one jump, so all you can see is that a read takes at most about 10 ns.
- Any single measurement can come out only two ways: the interval crossed n jumps, or n + 1 (cases A and B in the figure). So **a single measurement is off by at most one jump, about 10 ns, no matter how long the code runs**. How many jumps you cross depends on where the start lands within a step, which is random, so over many runs the over- and under-counts cancel and the mean has no bias.
- What matters is how much of the measured time those 10 ns are: timing 1 µs of code, a single reading is off by at most 1%; 100 ns, by at most 10%, so one reading cannot tell 100 ns from 105 ns, and only averaging or repetition can (the two ways below); 5 ns, the error is bigger than the code itself. **So don't read single samples of code around 100 ns, and a single measurement shorter than 10–20 ns mostly reads quantization error.**
- On an Intel part without steps, a single reading is not much better: without fences, out-of-order execution moves the read earlier or later by ten-odd cycles, and with fences each read gets heavier (1.3), so the edges carry about 10 ns of uncertainty anyway. **About 10 ns is the resolution of a single timestamp pair, not just an AMD quirk**; production marks time whole spans of hundreds of ns to several µs, where this is a few percent.
- The reading also includes the reads themselves: with nothing between two reads, the difference is still about 36. That part is roughly fixed, so measure an empty region first and subtract the floor.
- Two ways to measure short code:
  - Run it 1000 times between the two reads and divide by 1000. The error is still one jump, but per run it shrinks to about 0.01 ns.
  - Measure many times and take the **mean, not the median**. Where the start falls within a step is random, so 5 ns of code crosses a jump half the time, and the average comes out at (1 + 36) / 2 = 18.5 ticks ≈ 5.2 ns, close to the truth. The median gets pulled to one of the two outcomes: 3 ns of code crosses a jump only 30% of the time, so the median is 1 tick, read as 0.28 ns.
- **This is how benchmarks report differences like 52.6 ns vs 52.5 ns: the first way above.** The tool (Google Benchmark, say) loops the code hundreds of thousands to millions of times and divides the total by the count, so one jump of error shrinks to around a hundred-thousandth of a ns per run. What limits the result then is run-to-run variation (frequency, caches, code alignment), not timer resolution; whether a 0.1 ns difference is real takes several runs and a check that the intervals don't overlap.
- Save medians and percentiles such as p99 for intervals much longer than a jump, such as a full processing path of hundreds of ns to a few µs, where quantization is a few percent.
- Errors from out-of-order execution are a separate matter; see 1.3.

### 1.3 Out-of-Order Execution: rdtsc Doesn't Wait for Earlier Instructions

**1. Why the edges are fuzzy**
- **Out-of-order execution**: the CPU does not finish instructions one by one in program order (the "Rename + ROB" box on the hardware map). `rdtsc` reads without waiting for the instructions before it to finish, and instructions after it may start before it.
- With just two reads and a subtraction, look at this:

```cpp
uint64_t t0 = __rdtsc();
int r = parse(msg);        // the code being measured
uint64_t t1 = __rdtsc();
```

- **Start**: the first few instructions of `parse` may begin before `t0` is read.
- **End**: when `t1` is read, the last few instructions of `parse` may not have finished.
- **Result**: both edges move inward, so when the measured code is only tens of ns, the measurement comes out shorter than the real one.

**2. The fix: pin the edges with fences**
- **`lfence`**: the instructions after it may not start until all the instructions before it have finished.
- **`rdtscp`**: a variant of `rdtsc` that waits for all earlier instructions to execute and all earlier loads to complete before reading, but does not hold back later instructions.
- The start and end marks look like this:

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

- **Start mark**: the first `lfence` lets the earlier code finish; the second keeps the measured code from starting before the read.
- **End mark**: `rdtscp` waits for the measured code to finish before reading; the `lfence` after it keeps later code from starting early.

**3. Intel vs. AMD**
- **Intel**: this behavior of `lfence` is defined in the manual.
- **AMD**: `lfence` only waits like this once the operating system turns on a switch. Recent Linux and Windows do so by default; on older systems AMD recommends `mfence`.
- **If earlier stores must also be visible to other cores**: the sequence Intel's manual gives is `mfence; lfence; rdtsc`.

**4. What fences cost, and when to use them**
- **Extra overhead**: measured on an empty interval, the difference between two fenced reads goes from one jump to two, about 20 ns, one jump more than without fences.
- **No more overlap**: fences stop the measured code from overlapping with the code around it, so what you measure is no longer exactly how it normally runs.
- **Fences make the edges accurate, at the cost of a heavier measurement and code that no longer overlaps with its neighbors.**
- **Which to use**:
  - **Microbenchmarks**: for code of tens of ns, the edge error is as large as the code itself, so use fences.
  - **Production hot path**: marks there measure whole spans of several µs, where an edge error of ten-odd ns is acceptable, so a plain `rdtsc` is the usual choice.

**5. The compiler moves code too**
- **Deleted entirely**: if nothing uses the result of the measured code, the compiler may remove it.
- **Moved outside**: computations that don't touch memory may be moved outside the two reads.
- **Fix**: make sure the result is used, for example by writing it to a `volatile` variable.

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
