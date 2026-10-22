---
title: "Low-Latency Trading — perf: How to Use It, What to Read"
date: 2026-10-22
slug: "low-latency-perf-profiling"
description: "perf answers two questions: which function and which instruction the time goes to, and whether the CPU is computing or waiting. Four commands, one job each: perf stat for the totals, record plus report for the hot function, annotate for the hot instruction, c2c for threads fighting over a cache line. Before starting, check permissions, the symbol table and the sampling event. IPC, cache-miss rate, branch-miss rate and hot-spot share each come with a reading line (from Intel's open-source intel-performance-skills). Then one real run on a virtual machine with no hardware counters: perf points at a single-accumulator sum, the samples land on the instruction after the add, and four accumulators make it 3.3 times faster."
summary: "stat for the totals, record and report to find the function holding 98% of the samples, annotate to see every sample land on the instruction after an add: a chain of adds, each waiting for the last, and splitting it four ways is 3.3 times faster. Without hardware counters, cpu-clock sampling still works; if the report shows only addresses, check the symbol table and the path the program runs from."
chapter: 2
categories: [Systems]
tags: [perf, profiling, linux, cpp, hft, low-latency]
toc: true
math: true
---

When a program is slow, don't guess. perf, the profiler that ships with the Linux kernel, answers two questions directly: which function and which instruction the time goes to, and whether the CPU is computing or waiting on data, branches or the kernel.

All the output below comes from real runs on a virtual machine. That machine has no hardware counters, so the cycle-based metrics (IPC, cache misses, branch misses, c2c) come with commands and reading lines but no measured output. Every number in Part 4 can be found in the [raw output](https://github.com/Jasper-aa64/trading-system-notes-study/tree/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B).

## 1. What perf Answers: Four Commands, One Job Each {#commands}

Day to day, perf comes down to four commands, from coarse to fine:

- **`perf stat`: the totals, in seconds**. Run the program once and get elapsed time, context switches and page faults; with hardware counters, also cycles, instructions, and cache and branch misses, which tell you whether the CPU is computing or waiting (3.1).
- **`perf record` + `perf report`: which function is hot**. record notes the address of the instruction the program is executing every so often, one sample each time; report adds the samples up by function, and the function with the most samples is where the time goes (3.2, 4.4).
- **`perf annotate`: which instruction is hot**. It spreads one function's samples over its assembly instructions (4.5).
- **`perf c2c`: threads fighting over one cache line**. It finds the lines that bounce between cores, and which part of the line is being fought over (3.3).

The usual order is stat first, then record and report, then annotate on the hot function. If you don't know where to start, run stat: it is the fastest and often answers the question on its own, which is also what Intel's linux-perf skill recommends. Poor multi-core scaling (twice the threads, no more throughput) is a different problem: record once with 1 thread and once with N threads, compare the hot-spot rankings, and run c2c on the functions that jumped up (3.4).

## 2. Before Starting: Permissions, Symbols and the Sampling Event {#before}

Get any of these three wrong and perf either refuses with a permission error, shows a report full of bare addresses, or samples nothing at all on a virtual machine.

### 2.1 perf_event_paranoid: How Much an Ordinary User May See {#paranoid}

`/proc/sys/kernel/perf_event_paranoid` is the bar the kernel sets for perf; the higher the number, the less an unprivileged user may see (the perf_event_open(2) man page):

- `2`: user-space measurements only, the default since Linux 4.6;
- `1`: both user and kernel measurements, the default before 4.6;
- `0`: also per-CPU data, but no raw tracepoint samples;
- `-1`: no restrictions.

The bar applies only to unprivileged users. root (`CAP_SYS_ADMIN`, or `CAP_PERFMON` on newer kernels) is not held back by it (kernel documentation, the perf_event_paranoid section of `Documentation/admin-guide/sysctl/kernel.rst`). The machine in Part 4 is at 2, but the runs were done as root, so nothing was blocked. Lowering it needs root and affects the whole machine; on a shared machine, ask the administrator first.

### 2.2 Symbols and Debug Info: Why the Report Shows Only Addresses {#symbols}

The function names in a report come from the binary's symbol table. A string of hex addresses means perf did not read the symbol table. There are two common causes, and the run in Part 4 hit a third:

- **The binary was stripped**. strip deletes the symbol table. The same demo program shows `sum_serial` before strip and this after it:

  ```text
    98.03%  perf_demo.strip  perf_demo.stripped  [.] 0x0000000000000a14
     0.26%  perf_demo.strip  perf_demo.stripped  [.] 0x00000000000009ed
  ```

  Profile the unstripped copy.

- **`-g` is about source lines, not function names**. `-g` adds debug info, which is what lets annotate print the matching source line above the assembly (see the output in 4.5). Function names do not depend on it: build the same program without `-g`, and as long as it is not stripped, the report still has names:

  ```text
    98.52%  perf_demo_nog  perf_demo_nog      [.] sum_serial
     1.02%  perf_demo_nog  perf_demo_nog      [.] refresh
     0.09%  perf_demo_nog  perf_demo_nog      [.] main
  ```

- **The program sits under a path starting with `/tmp/perf-`**. perf supports JIT (just-in-time compiled) code: the JIT writes symbols for the code it generates into a text file `/tmp/perf-<pid>.map`, and perf resolves addresses from it (perf documentation, `tools/perf/Documentation/jit-interface.txt`). perf before 6.11 compares only the prefix: any file whose path starts with `/tmp/perf-` is read as such a symbol file, and a binary cannot be read that way (Linux source `tools/perf/util/symbol.c`, line 774 in v3.10 and line 1802 in v6.10; commit b0979f008f13 changed it to accept only `/tmp/perf-<number>.map`, from v6.11). In my first run the program sat in `/tmp/perf-demo-20261022/`, and even the unstripped binary showed nothing but addresses; `perf report -vv` marked its symbol source as `j`, for JIT. Moving to `/tmp/demo-perf-20261022/` fixed it; the output of both runs is in the [raw output](https://github.com/Jasper-aa64/trading-system-notes-study/tree/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B/first-run).

Call stacks are a separate matter. `perf record -g` walks back to the callers through frame pointers by default, and when the compiler omits frame pointers the call graph comes out wrong; use `--call-graph dwarf` then (the `--call-graph` section of perf-record(1)). That is why Part 4 builds with `-fno-omit-frame-pointer`. Even so, the call chain in 4.4 misses one level; that section explains why.

### 2.3 cpu-clock and cycles: Sampling by Time or by Hardware Count {#events}

Sampling needs a trigger, and these two are the usual ones:

- **`cpu-clock` is a software event**. It fires on time, driven by the kernel's high-resolution per-CPU timer (perf_event_open(2), `PERF_COUNT_SW_CPU_CLOCK`), needs no hardware support and works on a virtual machine. The record runs in Part 4 use the default rate, 4000 samples per second.
- **`cycles` is a hardware event**. It is counted by the PMU (performance monitoring unit) in the CPU. IPC, cache misses, branch misses and c2c all need the PMU, and so does precise sampling, called PEBS on Intel and IBS on AMD (perf-list(1)).
- **Virtual machines often don't expose the PMU**. Then `cycles` is unavailable while `cpu-clock` still works. So probe before relying on it (4.2).

## 3. Metrics and Reading Lines: What Number Points Where {#thresholds}

The lines in this part come from Intel's open-source [intel-performance-skills](https://github.com/intel/intel-performance-skills) (`skills/linux-perf`, commit 3e33aec, MIT license). They are rules of thumb: crossing one says it is worth looking in that direction, not that the problem is certainly there. Except for the kernel-time share and the hot-spot share, every metric here needs hardware counters. The virtual machine in Part 4 has none (4.2), so this part has commands and reading lines but no measured output.

### 3.1 The Four perf stat Ratios: Computing or Waiting {#stat-ratios}

```bash
perf stat -e cycles,instructions,cache-references,cache-misses,branches,branch-misses -- ./prog
```

$$\text{IPC} = \frac{\text{instructions}}{\text{cycles}}$$

$$\text{cache-miss rate} = \frac{\text{cache-misses}}{\text{cache-references}}$$

$$\text{branch-miss rate} = \frac{\text{branch-misses}}{\text{branches}}$$

One number at a time (`references/flow-a.md`):

> - IPC (instructions per cycle) < 1: the CPU spends most of its time waiting; > 3: it is computing at full tilt.
> - Cache-miss rate > 3–5%: leaning memory-bound.
> - Branch-miss rate > 3–5%: leaning branch-bound.
> - Kernel time above 30% of task-clock: leaning on system calls or I/O.

Several numbers together:

> - IPC < 1 and cache-miss rate > 3%: memory-bound; look at data layout, blocking, prefetching (see the [memory latency and bandwidth special](/posts/low-latency-memory-latency-bandwidth/)).
> - IPC < 1 and branch-miss rate > 3%: branch-bound; remove branches, use conditional moves (`cmov`), add prediction hints (see [#7 Branch Prediction](/posts/branch-prediction-branch-optimization/)).
> - Kernel time > 30%: make fewer system calls, batch I/O or make it asynchronous.
> - IPC ≥ 3 and low miss rates: the CPU is already well used; the bottleneck is elsewhere.
> - Nothing stands out: move on to record and report.

The kernel-time share needs no hardware counters: run perf stat once (without `-r`) and the output ends with two lines, `seconds user` and `seconds sys`; the output in 4.2 has them.

### 3.2 perf report: How Big the Hot Spot Is, What to Do Next {#report-lines}

The lines in `references/flow-b.md`:

> - One function holds ≥ 20% of the samples: you must go into annotate and read the assembly. The original says must, not may.
> - Every function is below 5%: no single hot spot; look at parallelism and algorithms.
> - malloc, free, new, delete dominate: consider an object pool or an arena (see [#3 Memory Pools and Allocators](/posts/hot-path-memory-allocators/)).
> - The top entry is a kernel symbol (marked `[k]`) above 40%: system calls or I/O; count the system calls with `strace -c`.
> - Many small kernel functions (`copy_to_user`, `mutex_lock`): lock contention or system-call overhead.
> - Spinlock or CAS wrapper functions stand out: check in annotate whether `lock cmpxchg` piles up; the fix is in [#16 Spinlocks](/posts/spinlock-implementation/) ({{% bottleneck-ref "tas-spinlock" %}}).

For what to look for in annotate, Intel has a separate scan list (`references/building-blocks.md`). The entry that matters for Part 4 is the serial accumulator: one floating-point instruction holds more than 40% of the function's samples, plus one of three conditions: IPC < 0.5, cache-miss rate < 2%, or the same register as source and destination. When applying it, mind where the samples land; see 4.5.

### 3.3 perf c2c: Threads Fighting over One Cache Line {#c2c}

```bash
perf c2c record -- ./prog
perf c2c report --stdio
```

- **What HITM (hit modified) is**. A load that hits a line another core's cache has modified and not yet written back (`PERF_MEM_SNOOP_HITM` in the kernel header `include/uapi/linux/perf_event.h`). The line has to be moved over from that core, 20–100 ns each time ([Reference 2.6](/ref/cpu-memory/#cross-core); how it works is in the [MESI special](/posts/low-latency-mesi-cache-coherence/)). c2c ranks cache lines by their HITM counts to find the most contended ones (perf-c2c(1)).
> - **Which lines to look at first**. By default only lines with Tot Hitm (this line's share of all HITMs) above 5% (`SKILL.md`).
> - **True or false sharing**. The same offset written by several threads is true sharing: everyone is changing the same data. Different offsets in one line written by different threads is false sharing: the data has nothing to do with each other and just happens to share a cache line (`references/flow-c.md`; false sharing is covered in [#2 Memory Ordering and Cache Lines](/posts/memory-ordering-false-sharing-dependency-chains/), {{% bottleneck-ref "false-sharing" %}}).
- **It needs hardware support**. On Intel, c2c uses load-latency and precise-store sampling events (by default `cpu/mem-loads,ldlat=30/P` and `cpu/mem-stores/P`); on AMD it uses IBS (perf-c2c(1)). The virtual machine in Part 4 has neither.

### 3.4 Poor Multi-Core Scaling: Compare the 1-Core and N-Core Hot-Spot Rankings {#scaling}

The method in `references/flow-d.md`:

> - First confirm the program really uses threads: `ldd ./prog` to see whether it links libpthread, libgomp, libtbb or libomp, then measure throughput on 1, N/2 and N cores.
> - Record once on 1 core and once on N cores and compare the top 15 functions of each. A function has jumped up if any of these holds:
>   - it rose 3 or more places;
>   - its share at least doubled;
>   - its share grew by 3 or more percentage points;
>   - it was outside the top 15 on 1 core and is at ≥ 2% on N cores.
> - Run c2c on the functions that jumped and sort the results into five kinds:
>   - false sharing: pad the fields apart ({{% bottleneck-ref "false-sharing" %}});
>   - TAS spinning: read before you grab (see [#16 Spinlocks](/posts/spinlock-implementation/), {{% bottleneck-ref "tas-spinlock" %}});
>   - a statistics counter written by many cores: one bucket per CPU ({{% bottleneck-ref "shared-counter" %}});
>   - genuinely shared data: atomics, RCU, finer-grained locks;
>   - no c2c signal: back to report to look at computation and branches.
> - Re-profile after each fix: removing one bottleneck exposes the next.

The ranking comparison works with cpu-clock alone; the c2c step needs hardware counters.

### 3.5 Annotate Scan: Seven Checks on a Hot Function's Assembly {#annotate-scan}

Once report points at a hot function, annotate shows its assembly. Intel lists seven things to check (`references/building-blocks.md`), each followed here by the matching [bottleneck card](/ref/bottlenecks/):

> 1. **No vectorization**: the hot instructions are all scalar floating point (`vaddsd`, `vmulsd` and the like), not one packed instruction, and scalar holds > 50% of the function's samples. Find what blocks vectorization first, then widen ({{% bottleneck-ref "narrow-vector" %}}).
> 2. **Vectors too narrow**: the CPU supports AVX2/AVX-512, but the hot path's packed instructions still use xmm (or ymm on an AVX-512 machine), at > 20% ({{% bottleneck-ref "narrow-vector" %}}).
> 3. **Serial accumulator**: one floating-point instruction holds > 40%, plus any one of three: IPC < 0.5, miss rate < 2%, or the same register as source and destination. Samples often land on the instruction after the slow one (skid), so counting floating-point instructions literally misses it: in the run in 4.5, 100% of the samples sit on the integer `add` after `addss`; look one instruction back ({{% bottleneck-ref "serial-accumulator" %}}).
> 4. **Horizontal reduction**: `shufps`/`addss`/`unpckhps` within 3–5 instructions after a multiply, > 10% combined. This is a horizontal reduction the compiler generated; rewrite it with multiple accumulators ({{% bottleneck-ref "serial-accumulator" %}}).
> 5. **TAS spinning**: `lock cmpxchg`/`lock xchg` in a loop at > 10% ({{% bottleneck-ref "tas-spinlock" %}}).
> 6. **Memory pressure**: loads > 30% combined, with no comparable computation. There is no ready fix; it points at locality, a smaller working set and prefetching, and is only credible if perf stat's miss rate is high too. This one has no matching card; the mechanism is in the [memory latency and bandwidth special](/posts/low-latency-memory-latency-bandwidth/).
> 7. **Atomic counter**: `lock add/inc/xadd/sub` at > 10%. If a conditional jump follows the result, it is really a lock built from an add; treat it as TAS ({{% bottleneck-ref "tas-spinlock" %}}). If nobody uses the result, it is a statistics counter; bucket it per CPU ({{% bottleneck-ref "shared-counter" %}}).

## 4. One Real Run: A Virtual Machine with No Hardware Counters {#demo}

The result first: perf points at `sum_serial`, holding 98% of the samples, and those samples all land on the instruction after its add: a chain of adds, each waiting for the last. With four accumulators the result agrees within rounding error and the mean time drops from 0.545 s to 0.164 s. These numbers describe this machine with these settings only.

### 4.1 Machine and Program {#demo-setup}

- Machine: an x86-64 virtual machine with no access to hardware counters.
- Kernel `3.10.0-1160.119.1.el7.x86_64`; perf `3.10.0-1160.119.1.el7.x86_64.debug`, whose version follows the kernel package.
- Compiler GCC 12.2.0, flags `-O2 -g -fno-omit-frame-pointer`.
- Run as root, with `perf_event_paranoid` at 2.

The demo program needs one obvious hot spot and one cold function for contrast. The hot spot is a sum with a single accumulator: every add waits for the result of the one before, and a floating-point add takes 3–5 cycles to produce its result ([Reference 2.1](/ref/cpu-memory/#latency)), so the adds can only happen one after another. The cold function rewrites 256 prices per round, standing in for new market data and making every round's sum need recomputing. 4096 floats are 16 KiB, which fits in L1D (the level-1 data cache), so the sum never waits for memory.

```cpp
#include <cstdio>
#include <cstring>
#include <vector>

// Cold function: rewrites 256 prices per round, like new market data arriving
__attribute__((noinline)) void refresh(float* px, int n, int round) {
    const int start = (round * 256) & (n - 1);  // n is a power of 2
    for (int j = 0; j < 256; ++j)
        px[start + j] = 100.0f + 0.01f * static_cast<float>((round + j) & 255);
}

// Hot spot: a single accumulator, every add waits for the previous one
__attribute__((noinline)) float sum_serial(const float* a, int n) {
    float s = 0.0f;
    for (int i = 0; i < n; ++i) s += a[i];
    return s;
}

// Fix: four accumulators, four chains of adds that don't wait for each other
__attribute__((noinline)) float sum_4acc(const float* a, int n) {
    float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, s3 = 0.0f;
    int i = 0;
    for (; i + 4 <= n; i += 4) {
        s0 += a[i];
        s1 += a[i + 1];
        s2 += a[i + 2];
        s3 += a[i + 3];
    }
    for (; i < n; ++i) s0 += a[i];
    return (s0 + s1) + (s2 + s3);
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "1";
    const int n = 4096;  // 16 KiB, fits in L1D
    const int rounds = 100000;
    std::vector<float> px(n);
    for (int i = 0; i < n; ++i) px[i] = 100.0f + 0.01f * static_cast<float>(i & 255);

    if (std::strcmp(mode, "check") == 0) {  // Same data: both sums, plus a double reference
        double ref = 0.0;
        for (float x : px) ref += x;
        std::printf("sum_serial = %.4f\nsum_4acc   = %.4f\ndouble ref = %.4f\n",
                    sum_serial(px.data(), n), sum_4acc(px.data(), n), ref);
        return 0;
    }
    const bool fixed = mode[0] == '4';
    double total = 0.0;
    for (int r = 0; r < rounds; ++r) {
        refresh(px.data(), n, r);
        total += fixed ? sum_4acc(px.data(), n) : sum_serial(px.data(), n);
    }
    std::printf("%s: total = %.6e\n", fixed ? "sum_4acc" : "sum_serial", total);
}
```

There are three ways to run it: `./perf_demo 1` uses one accumulator, `./perf_demo 4` uses four, and `./perf_demo check` computes both sums on the same data plus a double reference. All the commands run in order from one [script](https://github.com/Jasper-aa64/trading-system-notes-study/blob/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B/run.sh); the script saves each command's output to a file, and the commands below leave out those redirections.

### 4.2 Probe First: Are Hardware Counters Available? {#demo-probe}

```bash
perf stat -e cycles,instructions -- /bin/true
echo "exit code: $?"
```

```text
 Performance counter stats for '/bin/true':

   <not supported>      cycles
   <not supported>      instructions

       0.002029639 seconds time elapsed

       0.000000000 seconds user
       0.002424000 seconds sys


exit code: 0
```

- Both hardware events are `<not supported>`, yet perf exits with 0. A script that checks only the exit code would think it measured something, so check the output line by line.
- A printed 0 also counts as unavailable: a program that actually ran cannot take 0 cycles or 0 instructions.
- The `seconds user` and `seconds sys` lines at the end appear only for a single run, not with `-r`. The kernel-time share comes from these two lines (3.1).

So everything below uses software events only: elapsed time, context switches, page faults, plus cpu-clock sampling.

### 4.3 perf stat -r 10: Totals and Noise {#demo-stat}

```bash
perf stat -r 10 ./perf_demo 1
```

```text
 Performance counter stats for './perf_demo 1' (10 runs):

            544.05 msec task-clock                #    0.999 CPUs utilized            ( +-  1.38% )
                 0      context-switches          #    0.001 K/sec                    ( +- 55.28% )
                 0      cpu-migrations            #    0.001 K/sec                    ( +- 40.82% )
               376      page-faults               #    0.691 K/sec                    ( +-  0.03% )
   <not supported>      cycles
   <not supported>      instructions
   <not supported>      branches
   <not supported>      branch-misses

           0.54486 +- 0.00755 seconds time elapsed  ( +-  1.39% )
```

- **Single-threaded, running the whole time**. task-clock is 544.05 ms at `0.999 CPUs utilized`: one core busy from start to finish. Context switches and CPU migrations average less than one each (perf prints whole numbers, hence the 0).
- **376 page faults, nearly identical across the 10 runs** (±0.03%).
- **Every hardware event is `<not supported>`**, matching the probe in 4.2.
- **Elapsed time 0.54486 s ± 0.00755 s**. The number after ± is not the spread between single runs but the standard error of the 10-run mean: perf's source (`stddev_stats()` in `tools/perf/util/stat.c`) computes

  $$\text{standard error} = \sqrt{\frac{s^2}{n}}$$

  where $s^2$ is the sample variance of the 10 times and $n = 10$. The spread between single runs is $\sqrt{10} \approx 3.2$ times larger, about ±4.4%. The point of 10 runs is comparing two versions: a difference only counts if it is clearly larger than this noise (4.6).

### 4.4 perf record and perf report: Which Function Is Hot {#demo-report}

```bash
perf record -e cpu-clock -g -o perf.serial.data ./perf_demo 1
perf report --stdio -i perf.serial.data
```

```text
sum_serial: total = 4.148225e+10
[ perf record: Woken up 1 times to write data ]
[ perf record: Captured and wrote 0.175 MB perf.serial.data (2346 samples) ]
```

The top of the report (a few dozen more lines follow for the kernel and the dynamic linker, all below 0.3%):

```text
# Samples: 2K of event 'cpu-clock'
# Event count (approx.): 586500000
#
# Children      Self  Command    Shared Object      Symbol
# ........  ........  .........  .................  .................................
#
    99.19%     0.00%  perf_demo  libc-2.17.so       [.] __libc_start_main
            |
            ---__libc_start_main
               |
               |--98.12%--sum_serial
               |
                --0.90%--refresh

    98.12%    98.04%  perf_demo  perf_demo          [.] sum_serial
            |
             --98.04%--__libc_start_main
                       sum_serial

     0.90%     0.90%  perf_demo  perf_demo          [.] refresh
            |
            ---__libc_start_main
               refresh

     0.26%     0.00%  perf_demo  [kernel.kallsyms]  [k] page_fault
```

- **Sample count and rate**. record took 2346 samples. For cpu-clock the Event count is in nanoseconds: 586,500,000 ns ÷ 2346 = 250 µs per sample, the default 4000 per second.
- **Self and Children** (perf documentation, `tools/perf/Documentation/callchain-overhead-calculation.txt`). Self is the share of samples that land directly in the function; Children adds the functions it calls. `__libc_start_main` has Self 0 and Children 99.19%: it does no work itself, and all the time goes to what it calls. The Self column adds up to 100%; the Children column adds up to more.
- **Which function to look at**. `sum_serial` has Self 98.04%, past the "≥ 20% must read the assembly" line, so the next step is annotate (4.5). `refresh` has only 0.90%, below 5%: a cold function, leave it alone.
- **User or kernel**. `[.]` is user space, `[k]` is the kernel. The biggest kernel entry is `page_fault`, at only 0.26%.

The call chain is missing `main`. `main` is what calls `sum_serial`, yet the chain goes straight from `__libc_start_main` to `sum_serial`. The reason is that `sum_serial` calls nothing else, which makes it a leaf function, and GCC 12 built no stack frame for it: despite `-fno-omit-frame-pointer`, it does not start with `push %rbp` (see the assembly in 4.5). Walking frame pointers, the first step up from it skips past `main`. Walk with DWARF instead (`perf record -e cpu-clock --call-graph dwarf`) and `main` is back:

```text
    99.04%     0.00%  perf_demo  perf_demo            [.] _start
            |
            ---_start
               __libc_start_main
               main
               |
               |--97.93%--sum_serial
               |
                --1.12%--refresh
```

On this machine a DWARF walk makes report print a few `BFD: Dwarf Error: ... only handles version 2, 3 and 4` lines at the top: GCC 12 emits DWARF 5 debug info by default, and the machine's old binutils cannot read it. The lines don't affect the call chain; the output above is from that same run.

### 4.5 perf annotate: Which Instruction Is Hot {#demo-annotate}

```bash
perf annotate --stdio -i perf.serial.data sum_serial
```

The part covering the function itself:

```text
 Percent |	Source code & Disassembly of perf_demo for cpu-clock (2300 samples, percent: local period)
----------------------------------------------------------------------------------------------------------
         :            __attribute__((noinline)) float sum_serial(const float* a, int n) {
         :                float s = 0.0f;
         :                for (int i = 0; i < n; ++i) s += a[i];
    0.00 :   400a00:       test   %esi,%esi
    0.00 :   400a02:       jle    400a20 <sum_serial(float const*, int)+0x20>
    0.00 :   400a04:       movslq %esi,%rsi
         :                float s = 0.0f;
    0.00 :   400a07:       pxor   %xmm0,%xmm0
    0.00 :   400a0b:       lea    (%rdi,%rsi,4),%rax
    0.00 :   400a0f:       nop
         :                for (int i = 0; i < n; ++i) s += a[i];
    0.00 :   400a10:       addss  (%rdi),%xmm0
  100.00 :   400a14:       add    $0x4,%rdi
    0.00 :   400a18:       cmp    %rax,%rdi
    0.00 :   400a1b:       jne    400a10 <sum_serial(float const*, int)+0x10>
    0.00 :   400a1d:       ret
    0.00 :   400a1e:       xchg   %ax,%ax
         :                float s = 0.0f;
    0.00 :   400a20:       pxor   %xmm0,%xmm0
         :                return s;
         :            }
    0.00 :   400a24:       ret
```

- **The samples land on the instruction after the add**. All 2300 of this function's samples, 100%, are on `add $0x4,%rdi`. The instruction actually being waited on is the one before it, `addss (%rdi),%xmm0`: that is what `s += a[i]` compiles to, and each one needs the `%xmm0` the previous one produced.
- **This is called skid**. Without precise sampling, the recorded instruction address may land later than the instruction responsible (the description of `precise_ip` 0 in perf_event_open(2)). Here it is off by one: the loop is stuck waiting for `addss`, and the sample is recorded on the instruction after it. Precise sampling needs hardware counters, which this machine lacks. So when reading annotate, the hot spot is either the marked instruction or the one before it.
- **Applying the rule literally misses it**. The serial-accumulator entry in 3.2 wants one floating-point instruction above 40%, but here 100% sits on the integer instruction `add`, so the rule finds nothing. Looking one instruction back makes it match.
- **The source lines come from `-g`**. The `for (int i = 0; i < n; ++i) s += a[i];` printed above the assembly comes from the debug info; built without `-g`, the same spot shows assembly only (`extra/annotate_nog.txt` in the [raw output](https://github.com/Jasper-aa64/trading-system-notes-study/tree/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B)).

The cause of the slowness is visible in the source: a single accumulator, so every add waits for the one before. The fix is to split it into several independent chains of adds.

### 4.6 Four Accumulators: Check the Result, Then Compare Times {#demo-fix}

`sum_4acc` hands the numbers to four accumulators in turn, so the four chains of adds don't wait for each other, and combines them at the end (the code is in 4.1). The order of the adds has changed, so the floating-point result shifts slightly; check it first:

```bash
./perf_demo check
```

```text
sum_serial = 414822.4688
sum_4acc   = 414822.3750
double ref = 414822.4000
```

414822 lies between $2^{18}$ and $2^{19}$, and a float has 23 fraction bits, so adjacent floats at this magnitude are $2^{18-23} = 2^{-5} = 0.03125$ apart. The single accumulator is 0.0688 above the reference, about 2 steps; the four accumulators are 0.025 below, less than 1 step. Both sums are within rounding error, and the difference comes from the order of the adds: floating-point addition is not associative.

Then 10 more runs:

```bash
perf stat -r 10 ./perf_demo 4
```

```text
 Performance counter stats for './perf_demo 4' (10 runs):

            163.27 msec task-clock                #    0.995 CPUs utilized            ( +-  5.71% )
                 0      context-switches          #    0.003 K/sec                    ( +- 33.33% )
                 0      cpu-migrations            #    0.002 K/sec                    ( +- 50.92% )
               376      page-faults               #    0.002 M/sec                    ( +-  0.03% )
   <not supported>      cycles
   <not supported>      instructions
   <not supported>      branches
   <not supported>      branch-misses

           0.16404 +- 0.00933 seconds time elapsed  ( +-  5.69% )
```

| Version | Mean time | Std. error |
|---|---|---|
| 1 accumulator | 0.54486 s | 0.00755 s (1.39%) |
| 4 accumulators | 0.16404 s | 0.00933 s (5.69%) |

- **About 3.3 times faster** (0.54486 ÷ 0.16404 ≈ 3.32). The two means differ by 0.38 s, more than 40 times either standard error, far beyond the noise.
- **Larger relative noise, similar absolute noise**. The standard error grows from 1.39% to 5.69%, but both stay under 10 ms in absolute terms (7.55 ms and 9.33 ms). The program got faster, so the same amount of noise is a bigger share.
- **The compiler put the four accumulators in one register**. At `-O2`, GCC 12 packs the four accumulators into the four lanes of one xmm register, leaving a single `addps` in the loop that adds 4 numbers at a time (objdump output):

  ```text
  400a53:	movups (%rdi,%rcx,1),%xmm0
  400a57:	addps  %xmm0,%xmm1
  ```

  It is still one chain of adds, but every link adds 4 numbers.

One more record:

```text
# Children      Self  Command    Shared Object        Symbol
# ........  ........  .........  ...................  .......................................
#
    97.64%     0.00%  perf_demo  libc-2.17.so         [.] __libc_start_main
    93.17%    93.17%  perf_demo  perf_demo            [.] sum_4acc
     4.10%     4.10%  perf_demo  perf_demo            [.] refresh
```

The code of `refresh` didn't change, yet its share rose from 0.90% to 4.10%: the total got shorter, so the unchanged part takes a bigger share, though still below 5%. `sum_4acc` is still past the 20% line, so by the rules it gets another annotate. In the raw output, `out/annotate_4acc.txt` shows 73.87% of the samples on the `cmp` after `addps`: the hot spot is still this chain of adds.

## In Practice {#in-practice}

Splitting one accumulator into four in 4.6 is one measured case of the {{% bottleneck-ref "serial-accumulator" "plain" %}} card below. The card lists what perf shows, how to fix it and how to verify the fix; the speedups in its fix line are the original's numbers, while this virtual machine measured the roughly 3.3 times of 4.6.

{{% bottleneck "serial-accumulator" %}}
