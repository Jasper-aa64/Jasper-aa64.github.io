---
title: "CPU and Memory: Map, Numbers, Estimates"
description: "Which boxes one memory access passes through, how big and how fast each box is, and how to combine those numbers to estimate the memory time of a piece of code."
date: 2026-10-08
lastmod: 2026-10-08
slug: "cpu-memory"
weight: 10
toc: true
---

This page is a map to keep open, not a post. It has three parts, in the order "where → how big and how fast → how to combine":

1. [Map](#map): which boxes a read or a write passes through, and which post covers each box.
2. [Numbers](#numbers): latency, bandwidth and capacity for each box, how many requests can be in flight, and how fast the CPU itself wants data. Every number says where it comes from.
3. [Estimates](#estimate): one formula that strings the numbers of Part 2 together, to tell whether code is slow because it moves too much or because each move is slow.

When a later post covers a new hardware layer or measures a new number, it goes here.

## 1. Map: The Boxes One Access Passes Through {#map}

<a href="/images/ref/hardware-map.en.svg" target="_blank" rel="noopener"><img src="/images/ref/hardware-map.en.svg" alt="Hardware map from the pipeline and store buffer through L1, L2, L3, the memory controller and DIMMs, with a latency table and the fields of one address" loading="lazy" decoding="async"></a>

Blue text says where something is covered: #N is Trading System Notes #N, MESI is the topic post, and "Ref N.N" is a section of this page. Click the image for the full-size version.

### 1.1 One Load, Step by Step {#load}

1. The **TLB** translates the virtual address into a physical one; meanwhile **L1D** has already picked the set from address bits 6–11 (the address fields at the bottom of the map).
2. An L1D hit ends here, in about 1 ns. On a miss, L1D first takes an entry in its **fill buffer** to record "this line has been requested and hasn't come back yet", then asks the core's own **L2**, then the **L3** shared by all cores. The fill buffer has only a dozen or so entries, which caps how many misses one core can have outstanding on its own ([2.3](#in-flight)).
3. If L3 misses too, the **memory controller** takes over and picks a channel, bank and row from the address: about 14 ns on a row-buffer hit, 28–41 ns otherwise; with the queueing and transfers along the way, one memory access takes about 70–120 ns ([2.1](#latency)).
4. What comes back is always a whole **64-byte cache line**, which is placed in each cache level on the way up.

### 1.2 A Store Takes Two More Steps {#store}

A store first goes into the **store buffer**, so later instructions don't wait for it. Before it can be written into L1D, the core needs exclusive ownership of the line: every copy in another core has to be invalidated (**MESI**), and each of those cores queues the invalidation in its **invalidate queue** first. If the line isn't in the cache, the whole line has to be read in before it can be modified (RFO, read for ownership), so a store miss also moves a whole line from memory.

### 1.3 Which Post Covers Which Box {#posts}

| Box | Post |
|---|---|
| Cores, SMT, NUMA, interrupts on a core | [#1 CPU Isolation and NUMA](/posts/cpu-affinity-core-isolation-numa/) |
| Pipeline and dependency chains, registers, store buffer, invalidate queue, cache lines and false sharing | [#2 Memory Ordering and Cache Lines](/posts/memory-ordering-false-sharing-dependency-chains/) |
| Cache coherence | [MESI](/posts/low-latency-mesi-cache-coherence/) |
| Locking memory, TLB shootdowns | [#3 Memory Pools and Allocators](/posts/hot-path-memory-allocators/) |
| Several cores reading and writing one line | [#4 Lock-Free Queues](/posts/lock-free-queue-logger-micro-batching/) · [#5 SPMC Broadcast Ring](/posts/spmc-shared-memory-broadcast-ring/) |
| Page faults | [#5 SPMC Broadcast Ring](/posts/spmc-shared-memory-broadcast-ring/) |
| Alignment, layout, set associativity, inside a DIMM, refresh, channels | [#6 Alignment, Layout, and Geometry](/posts/alignment-layout-cache-dram-geometry/) |
| The roads between the boxes: latency, bandwidth, fill buffers | Parts 2 and 3 of this page |

## 2. Numbers: How Big and How Fast Each Box Is {#numbers}

These are magnitudes, not a spec sheet. Every row says where its number comes from:

- **Measured**: measured on my own machines (Ryzen 5 5600GT on Windows, or an M1 MacBook Air), in the post named;
- **Public data**: the public database from Chips and Cheese ([bandwidth](https://jsmemtest.chipsandcheese.com/bwdata), [latency](https://jsmemtest.chipsandcheese.com/latencydata)); the chips are listed in [2.7](#chips);
- **Derived**: calculated from other numbers;
- **Typical**: a typical value from specs or references, not measured.

Cycles and nanoseconds are converted at about 4 GHz: 1 ns ≈ 4 cycles.

### 2.1 Latency: How Long One Access Waits {#latency}

| One… | About | Source |
|---|---|---|
| Register read | 0–1 cycles | Typical |
| L1D hit | ~1 ns (4–5 cycles) | Public data: 0.7–1.4 ns |
| L2 hit | ~2.5–5 ns (12–16 cycles) | Public data: 2.4–5.5 ns |
| L3 hit | ~10–15 ns on desktops, ~20–25 ns on servers | Public data |
| Uncontended atomic read-modify-write (`lock add`, CAS, line in your own L1) | ~10–20 cycles | Typical |
| Line sitting in another core's cache | Tens of ns; shorter within one core complex, longer across CCDs or sockets | Typical |
| Local memory | ~75–90 ns on desktops, ~85–120 ns on servers, ~105 ns on M1 | Public data (random reads over 1 GiB) |
| …of which TLB misses | ~10–30 ns: with huge pages, Zen 3 89 → 79 ns, Zen 4 84 → 73 ns, Ice Lake server 117 → 85 ns | Public data |
| Remote NUMA memory | Local plus tens of ns | Typical |
| Running into a DRAM refresh | A few hundred ns more; about 4.5% of random accesses | Typical + derived ([2.5](#dram)) |
| First write to a page (page fault) | ~1.5 µs | Measured (5600GT on Windows, [#5](/posts/spmc-shared-memory-broadcast-ring/)) |
| Simplest system call | ~0.1–0.5 µs, depending on the kernel and its vulnerability mitigations | Typical |
| Thread switch | ~1–5 µs, plus the cost of a cold cache afterwards | Typical |
| NVMe SSD 4 KiB read | 10–100 µs | Typical |

From L1 to memory, each level is 3–10× slower than the one above, about 100× in total. The microsecond rows are outside the cache hierarchy altogether, where the operating system is doing work for you: one page fault costs as much as 1,500 L1 hits.

### 2.2 Bandwidth: How Much Arrives per Second {#bandwidth}

| Data in | One core, sequential reads | Whole chip | Source |
|---|---|---|---|
| L1D | ~150–420 GB/s | Cores × one core | Public data |
| L2 | ~85–210 GB/s | Cores × one core | Public data |
| L3 | ~100–150 GB/s on desktops, ~35 GB/s on servers | Hundreds of GB/s to over 1 TB/s | Public data |
| Memory | ~35–57 GB/s on desktops, ~16 GB/s on servers, ~45–57 GB/s on M1 | 50–100 GB/s on dual-channel desktops; hundreds of GB/s on 8–12-channel servers | Public data + derived |
| PCIe 4.0 ×16 | — | ~32 GB/s each way | Typical |
| NVMe SSD | — | 3–7 GB/s | Typical |

Two things to notice:

- **Latency spans 100×, bandwidth only 10×.** From L1 to memory, one core's bandwidth drops from hundreds of GB/s to tens. The two columns aren't two ways of writing one quantity; what sits between them is how many requests are in flight ([2.3](#in-flight)).
- **How much of the chip one core gets depends on the platform.** On a Zen 3 desktop one core reads 35 GB/s and all cores 51 GB/s, so a single core gets about 70%. On an Ice Lake server one core reads 16.6 GB/s and 10 cores 124 GB/s, so a single core gets just over a tenth. On an M1, one big core gets nearly all of it. A server core sits farther from memory (higher latency) and has more channels behind it (a higher peak), and both push that ratio down. When you see a single-core bandwidth figure, first ask whether it's a desktop or a server.

### 2.3 How Many Can Be in Flight {#in-flight}

One core's bandwidth = requests in flight × 64 B ÷ latency (Little's law). The structures that limit "in flight":

| Structure | Size | What it limits | Source |
|---|---|---|---|
| ROB (reorder buffer) | 200–600 entries: Skylake 224, Zen 3 256, Golden Cove 512, M1 ~630 | How far ahead out-of-order execution can look for independent loads to issue early | Typical |
| L1D fill buffer | A dozen or so (Intel generations ~10–16) | How many misses one core's own loads can have outstanding | Typical |
| L2 outstanding-request queue | A few dozen | Where the L2 prefetcher's extra requests wait, without using fill buffers | Typical |
| Store buffer | ~50–110 entries: Skylake 56, Zen 3 64, Golden Cove 114 | Stores park here instead of waiting for the cache | Typical |

Same core, same memory, and only the number in flight changes: bandwidth moves by two orders of magnitude (derived, at 80 ns and 64 B per line):

| Access pattern | In flight | One core's bandwidth |
|---|---|---|
| Linked list: the next address waits for this read | 1 | 64 B ÷ 80 ns ≈ 0.8 GB/s |
| Independent addresses the prefetcher can't help with (random, or a stride that crosses a page every time: prefetchers don't cross 4 KiB pages) | The dozen or so fill buffers | ~10–13 GB/s |
| Sequential reads, prefetchers at full speed | ~40–45 (back-calculated: 35 GB/s × 80 ns ≈ 2.8 KB) | ~35 GB/s (Zen 3, public data) |

The 40-odd requests in the last row are far more than a dozen fill buffers. The extra ones are the L2 prefetcher's, waiting in its own queue on your behalf.

### 2.4 How Fast the CPU Wants Data {#appetite}

Whether memory bandwidth is the bottleneck also depends on the other side: if data arrived for free, how many bytes per second would the loop consume? One core at about 4 GHz (derived):

| Loop | Per cycle | Per second | Compared with memory |
|---|---|---|---|
| `float` sum, one accumulator, no `-ffast-math` | 4 B every 3–4 cycles: each add waits for the previous one | ~4–5 GB/s | Below one core's memory bandwidth: stuck on the add chain, not on memory |
| `int` sum, one accumulator, not vectorized | 4 B | 16 GB/s | Only memory barely keeps up with it |
| Vectorized, several accumulators (two 32 B loads per cycle) | 64 B | ~256 GB/s | Bandwidth-bound as soon as data leaves L1 |
| The L1 load ports' limit (2–3 loads per cycle, 32–64 B each) | 64–128 B | 250–500 GB/s | — |
| Dozens of operations per element | Well under 1 B | — | Almost always compute-bound |

"How fast is the CPU" isn't one number: the same sum, written differently, ranges from 4 GB/s to 250 GB/s, a 60× spread. Bandwidth is the bottleneck only when the loop eats faster than memory delivers.

### 2.5 Inside the DIMMs: Channels, Row Buffers, Refresh {#dram}

| Quantity | Number | Source |
|---|---|---|
| One channel's peak | Transfer rate × 8 B: DDR4-3200 → 25.6 GB/s, DDR5-6000 → 48 GB/s (a DDR5 DIMM is two 32-bit subchannels, still 8 B together) | Derived |
| The chip's peak | Channels × one channel: 51–96 GB/s on dual-channel desktops; hundreds of GB/s on 8–12-channel servers | Derived |
| What you actually get | All cores reading: from just over 70% to nearly 90% of peak (Zen 4 73 / 96 GB/s, Zen 3 51 / 57.6 GB/s) | Public data |
| Row buffer | ~14 ns on a hit to the open row, ~28 ns with no row open, ~41 ns on a row conflict (DDR4-3200 CL22) | Typical |
| Refresh | Every ~7.8 µs, blocking a few hundred ns each time (~350 ns for 8 Gb DDR4); about 4.5% of random accesses run into one | Typical + derived |
| Loaded latency | The fuller the bandwidth, the slower each access; near the limit it can exceed twice the idle latency | Typical |

### 2.6 A Line Bouncing Between Cores {#cross-core}

One producer writes into a ring nonstop while readers on other cores busy-poll the same blocks (measured: 5600GT on Windows, a 512 KiB ring, [#5](/posts/spmc-shared-memory-broadcast-ring/)):

| Readers | 0 | 1 | 2 | 5 |
|---|---|---|---|---|
| Producer, per write | 2.8 ns | 18.5 ns | 24.0 ns | 28.0 ns |

With no readers, the line stays in the producer's own L1. With one reader, every block has to invalidate the reader's copy before it can be written ([MESI](/posts/low-latency-mesi-cache-coherence/)), and each write gets more than six times more expensive. That's throughput, with the store buffer absorbing part of the wait; a single cross-core round trip by itself is tens of nanoseconds.

### 2.7 A Few Specific Chips {#chips}

Public data from Chips and Cheese. My 5600GT is also Zen 3, so its numbers should be close to the first column (not measured).

| | Zen 3 desktop<br>Ryzen 9 5950X, dual-channel DDR4-3600 | Ice Lake server<br>Xeon 8370C, cloud VM | Apple M1<br>LPDDR4X-4266 |
|---|---|---|---|
| L1D latency | 0.8 ns | 1.4 ns | 0.9 ns |
| L2 latency | 2.4 ns | 4.0 ns | 5.5 ns |
| L3 latency (at 8 MiB) | 10.7 ns | 23.1 ns | — (no L3; a 12 MiB L2 shared by the four big cores) |
| Memory latency (random reads over 1 GiB) | 91 ns | 117 ns | 106 ns |
| One core reading L1 | 311 GB/s | 240 GB/s | 150 GB/s |
| One core reading L2 | 158 GB/s | 157 GB/s | 86 GB/s |
| One core reading L3 | 122 GB/s | 34 GB/s | — |
| One core reading memory | 35 GB/s | 16.6 GB/s | 57 GB/s |
| All cores reading memory | 51 GB/s (peak 57.6) | 124 GB/s (10 cores) | ~60 GB/s (peak 68) |

## 3. Estimates: Lines to Move × Time per Line {#estimate}

None of the numbers in Part 2 explains slow code on its own. Strung together they make one formula:

> **Total time ≈ lines to move × time each line costs on average**

```
lines to move   ← Q1 bytes used per line?     Q2 does a line survive until reuse?
time per line   ← Q3 which level serves it?   Q4 how many in flight at once?

lines per second = min( in flight ÷ latency ,  peak bandwidth ÷ 64 B )
                        └ one core hits this ┘  └ takes many cores ┘
```

Then take the smaller of that and the demand side ([2.4](#appetite)):

> **Actual speed = min(how fast the CPU wants data, useful bytes per line × lines per second)**

### 3.1 Four Questions {#four-questions}

- **Q1: how many bytes of each line are used (spatial locality).** Reading `int`s one after another, one 64 B line feeds 16 of them; with a stride of 64 B or more, each line feeds just 4 B, so the same useful data takes 16 times as many lines. "Wasted bandwidth" is about this question only, and has nothing to do with whether the bus is full. A 64 B stride is already the worst case; larger strides aren't worse on this count.
- **Q2: does a fetched line survive until it's needed again (temporal locality).** It fails to survive for exactly three reasons: a **cold miss** (first touch, which nobody avoids), a **capacity miss** (more reused lines than the level holds), and a **conflict miss** (addresses crowding into one set, the critical stride in [#6](/posts/alignment-layout-cache-dram-geometry/)). Padding fixes only conflicts; capacity takes blocking, which means working on one cache-sized chunk at a time.
- **Q3: which level supplies it.** That sets the latency and the peak bandwidth; numbers in [2.1](#latency) and [2.2](#bandwidth).
- **Q4: how many can be in flight at once.** If the next address waits for this read (linked lists, trees, hash chains), there is one, and every line pays a full latency. If addresses are computed, out-of-order execution issues later loads early, up to a full fill buffer. If the walk is sequential, the prefetcher keeps another batch outstanding for you ([2.3](#in-flight)). That's what "the pipeline hides latency" means: latency doesn't get shorter; many waits overlap.

### 3.2 Five Examples {#examples}

All estimated with the Zen 3 desktop numbers (derived, not measured):

1. **Sequential sum over a big array, vectorized.** Q1: every line is fully used. Q4: prefetchers at full speed, about 35 GB/s for one core, while the CPU wants about 256 GB/s. The smaller one wins: about 35 GB/s, bound by memory bandwidth. With four cores scanning, they hit the chip's ~51 GB/s together and each gets only about 13 GB/s.
2. **The same sum with `float` and one accumulator.** The CPU only wants about 4 GB/s, less than memory delivers. Data in L1 or in memory runs at nearly the same speed; going faster means breaking the dependency chain (several accumulators, [#2](/posts/memory-ordering-false-sharing-dependency-chains/)), and faster memory does nothing.
3. **Walking a linked list scattered over the heap.** Q4 is 1: each node pays a full memory latency, about 90 ns, so a million nodes take about 90 ms. The road is wide, and 0.7 GB/s of it is used. The only fixes are keeping nodes next to each other (an array, a pool) or keeping them in cache.
4. **One table lookup on the hot path that goes to memory.** About 90 ns: 360 cycles at 4 GHz, the time of ninety L1 hits. A hot path touches only a few lines per market-data message, so bytes are tiny; what hurts is a dependent miss like this one (Q3, Q4), not bandwidth.
5. **Another process on the same machine scanning memory hard (a backtest, a market-data replay).** It fills the chip's bandwidth, the memory controller queues up, and every miss on the hot path gets slower (loaded latency, [2.5](#dram)). Pinning cores isolates compute; it doesn't isolate this road.

### 3.3 Easy to Mix Up {#pitfalls}

- **A full fill buffer means maximum overlap, not "falling back to serial".** With N entries in flight, miss N+1 waits for the oldest one to return and free its slot, so the steady state keeps N in flight and each line costs latency ÷ N. Only dependency chains are truly serial. So bandwidth and latency aren't either-or: one core's bandwidth *is* in-flight × 64 B ÷ latency, and when latency grows (DRAM row conflicts, TLB misses), the same N moves fewer lines per second.
- **"5 ns per line" is throughput, not latency.** 80 ns ÷ 16 = 5 ns is an average; every line still takes the full 80 ns.
- **"Bandwidth-bound" has two ceilings.** One core hits in-flight ÷ latency first; the chip's peak takes several cores pushing together. Before saying "the bus is saturated", ask how many cores.
- **Padding fixes conflicts, not capacity.** One extra cache line per row sends addresses a critical stride apart to different sets; but if more lines need to be reused than the level holds (one column of 2048 rows is 2048 lines, 128 KiB, against 32 KiB of L1D), padding can't make them fit, and blocking can.

For any claim about memory access, first ask which of the four questions it answers; when one paragraph mixes several, take them apart.
