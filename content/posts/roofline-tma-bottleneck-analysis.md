---
title: "Trading System Notes #23: Roofline and TMA: Computing or Moving Data, and Where the Pipeline Stalls"
date: 2026-11-09
lastmod: 2026-11-10
slug: "roofline-tma-bottleneck-analysis"
description: "perf tells you which function and which instruction the time goes to, not why. Roofline boxes performance in with two roofs, peak compute and peak bandwidth: a program's arithmetic intensity decides which roof it hits, and its distance from the roof is how much is left to gain; it assumes memory requests keep the bus full, so it cannot see latency. TMA charges every pipeline slot of every cycle to one of four categories (front end, back end, wasted, useful), splits each one level by level, and ends by sampling that category's precise event down to a line of code. A trading system's hot path spends most of its time spinning, so measure it on a replay benchmark."
summary: "Finding a bottleneck in two steps: roofline answers \"bound by compute or by bandwidth, and how far from the limit\", TMA answers \"where in the pipeline it stalls\", and sampling the matching event finds the code."
chapter: 2
categories: [Systems]
tags: [roofline, tma, topdown, perf, profiling, pmu, hft, low-latency]
toc: true
math: true
build:
  list: never
---

The [perf special](/posts/low-latency-perf-profiling/) tells you which function and which instruction the time goes to, but knowing "this loop is hot" is not enough. Is it computing too much, or is the data arriving too slowly? Is it waiting on memory, or is a branch guessed wrong over and over? How far is it from what the hardware can do, and is it worth squeezing further? The two methods in this post answer those two layers of question: roofline first decides whether the bottleneck is computing or moving data and how far from the limit it is; TMA then pins "slow" to a specific stage of the pipeline, and finally to a line of code.

> **This post's chain of problems: each fix exposes the next**
> 1. **Before optimizing, you don't know where the limit is**: roofline draws two roofs from peak compute and peak bandwidth (Part 1).
> 2. **Roofline only tells "computing" from "moving data"; it can't see latency or the pipeline**: TMA charges every pipeline slot to one of four categories and splits them level by level (2.1–2.3).
> 3. **TMA names a category, not a line of code**: sample the precise event that matches the category (2.4).
> 4. **A trading system's hot path spends most of its time spinning, so measuring the whole process measures polling**: measure the handler on a replay benchmark (Part 3).

---

## 1. How Far a Program Is from Its Limit: Roofline Boxes Performance In with Two Roofs, Compute and Bandwidth {#roofline}

### 1.1 Two Hardware Limits: Peak Compute and Peak Bandwidth {#peaks}

1. **Peak compute: the most floating-point operations per second (FLOPS)**
   - **It follows from the execution units**: take a laptop CPU with 4 cores, up to 3.8 GHz, 2 FMA units per core and AVX2 (Intel i5-8259U). One 256-bit FMA instruction handles 8 `float`s at once, each getting one multiply and one add, which counts as 2 operations:

     $$
     \text{peak compute} = \underbrace{4}_{\text{physical cores}} \times \underbrace{2}_{\text{FMA units}} \times \underbrace{8}_{\substack{\text{floats in} \\ \text{256 bits}}} \times \underbrace{2}_{\substack{\text{a multiply-add} \\ \text{counts as 2}}} \times 3.8\ \text{GHz} \approx 486\ \text{GFLOPS}
     $$

   - **Count physical cores, not hyperthreads**: the two hyperthreads on a core share its 2 FMA units, so they add no compute.
   - **It is an upper bound you never reach**: 3.8 GHz is the single-core turbo, and the clock is lower with every core busy; it also requires every instruction to be an FMA and both units to be busy every cycle.
2. **Peak bandwidth: the most bytes per second that can come from memory**
   - **It follows from the DIMMs and the channel count**: the same machine has DDR4-2400 in two channels, each transfer 64 bits (8 B) wide:

     $$
     \text{peak bandwidth} = \underbrace{2400\ \text{MT/s}}_{\text{transfers per second}} \times \underbrace{2}_{\text{channels}} \times \underbrace{8\ \text{B}}_{\text{64 bits each}} = 38.4\ \text{GB/s}
     $$

   - **One core can't saturate it on its own**: the bandwidth a single core gets is limited by how many requests it can have in flight ([memory latency and bandwidth special](/posts/low-latency-memory-latency-bandwidth/) 1.3); it takes several cores reading together to get close to this number.

### 1.2 The Program's Arithmetic Intensity Decides Which Roof It Hits {#intensity}

1. **The program has two quantities too: work and traffic**
   - **Arithmetic intensity**: how many operations are done per byte moved, in FLOP/B.
   - **Examples**: a `float` sum does 1 add per 4 B read, an intensity of 0.25; a dot product does one multiply and one add per 8 B read (one `a[i]` and one `b[i]`), also 0.25.
2. **The performance you can reach is the lower of the two roofs**

   $$
   P \;=\; \min\big(\,P_{\text{peak}},\;\; I \times B_{\text{peak}}\,\big)
   $$

   - **When $I$ is small**: $I \times B_{\text{peak}}$ is smaller, and performance is capped by bandwidth (memory-bound): the point sits on the slope. The sum above reaches at most $0.25 \times 38.4 \approx 9.6$ GFLOPS, 2% of peak compute.
   - **When $I$ is large**: performance is capped by compute (compute-bound): the point sits under the flat roof.
   - **The ridge point**: where the two roofs meet, $I^* = P_{\text{peak}} / B_{\text{peak}} = 486 / 38.4 \approx 12.7$ FLOP/B. Below it you hit bandwidth first; above it, compute.
3. **Plot the program's measured performance, and its distance from the roof is how much is left to gain**

<svg viewBox="0 0 760 420" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Roofline chart. The x axis is arithmetic intensity (floating-point operations per byte, log scale, 0.01 to 100), the y axis is performance (GFLOPS, log scale, 0.1 to 1000). The solid line is the slope of the 38.4 GB/s memory-bandwidth roof, which meets the 486 GFLOPS compute roof at 12.7 FLOP/B. The dashed line is the steeper, higher slope for data in L1, which reaches the flat roof at 0.5 FLOP/B. A float sum has intensity 0.25: with the data in memory it reaches at most about 9.6 GFLOPS, right on the solid slope; the scalar version with one accumulator does one add every 4 cycles, about 1 GFLOPS, far below the roof, and vectorizing, more accumulators and more cores push it up until it stops at the slope. A blocked matrix multiply has an intensity of tens and sits under the flat roof, bound by compute." style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif">
  <style>
    .rfbg   { fill: #fbfaf7; }
    .rfax   { stroke: #4a463d; stroke-width: 1.3; fill: none; }
    .rfgrid { stroke: #e4dfd3; stroke-width: 1; fill: none; }
    .rfmem  { stroke: #c15b3f; stroke-width: 2.4; fill: none; }
    .rfl1   { stroke: #c15b3f; stroke-width: 1.6; fill: none; stroke-dasharray: 6 4; }
    .rfcpu  { stroke: #4a463d; stroke-width: 2.4; fill: none; }
    .rfrdg  { stroke: #6b6558; stroke-width: 1; fill: none; stroke-dasharray: 3 3; }
    .rfpt   { fill: #6f8f3f; stroke: #3f5a1f; stroke-width: 1.2; }
    .rfpt2  { fill: #ffffff; stroke: #6f8f3f; stroke-width: 1.6; }
    .rfarr  { stroke: #6f8f3f; stroke-width: 1.6; fill: none; }
    .rfah   { fill: #6f8f3f; }
    .rfink  { fill: #1c1b18; font-size: 12px; }
    .rfsm   { fill: #1c1b18; font-size: 11.5px; }
    .rfmut  { fill: #6b6558; font-size: 11px; }
    .rfred  { fill: #c15b3f; font-size: 12px; }
    .rfgrn  { fill: #3f5a1f; font-size: 11.5px; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfbg { fill: #17161b; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfax { stroke: #c9c4b8; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfgrid { stroke: #2c2b33; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfmem { stroke: #e0896f; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfl1 { stroke: #e0896f; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfcpu { stroke: #d8d3c6; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfrdg { stroke: #8a8578; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfpt { fill: #8fb257; stroke: #b9d68a; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfpt2 { fill: #17161b; stroke: #8fb257; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfarr { stroke: #8fb257; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfah { fill: #8fb257; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfink { fill: #e8e4da; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfsm { fill: #e8e4da; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfmut { fill: #a39d90; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfred { fill: #e0896f; }
  :root:is([data-theme="dark"], [data-theme="black"]) .rfgrn { fill: #b9d68a; }
  </style>
  <rect class="rfbg" x="0" y="0" width="760" height="420" rx="10"/>
  <path class="rfgrid" d="M240 60V360M400 60V360M560 60V360M720 60V360M80 285H720M80 210H720M80 135H720M80 60H720"/>
  <path class="rfax" d="M80 60V360H720"/>
  <text class="rfmut" x="80" y="384" text-anchor="middle">0.01</text>
  <text class="rfmut" x="240" y="384" text-anchor="middle">0.1</text>
  <text class="rfmut" x="400" y="384" text-anchor="middle">1</text>
  <text class="rfmut" x="560" y="384" text-anchor="middle">10</text>
  <text class="rfmut" x="720" y="384" text-anchor="middle">100</text>
  <text class="rfink" x="400" y="406" text-anchor="middle">Arithmetic intensity (FLOP/byte, log scale)</text>
  <text class="rfmut" x="72" y="364" text-anchor="end">0.1</text>
  <text class="rfmut" x="72" y="289" text-anchor="end">1</text>
  <text class="rfmut" x="72" y="214" text-anchor="end">10</text>
  <text class="rfmut" x="72" y="139" text-anchor="end">100</text>
  <text class="rfmut" x="72" y="64" text-anchor="end">1000</text>
  <text class="rfink" x="24" y="210" text-anchor="middle" transform="rotate(-90 24 210)">Performance (GFLOPS, log scale)</text>
  <path class="rfl1" d="M80 210.9L351.8 83.5"/>
  <path class="rfmem" d="M80 316.2L576.4 83.5"/>
  <path class="rfcpu" d="M351.8 83.5H720"/>
  <path class="rfrdg" d="M576.4 83.5V360"/>
  <text class="rfink" x="720" y="74" text-anchor="end">Compute roof 486 GFLOPS</text>
  <text class="rfred" x="330" y="236" transform="rotate(-25.1 330 236)">Memory bandwidth roof 38.4 GB/s</text>
  <text class="rfred" x="120" y="180" transform="rotate(-25.1 120 180)">Data in L1: a higher slope</text>
  <text class="rfmut" x="584" y="352">Ridge 12.7 FLOP/B</text>
  <path class="rfarr" d="M303.7 280V222"/>
  <path class="rfah" d="M303.7 216l-5 9h10z"/>
  <circle class="rfpt2" cx="303.7" cy="286.6" r="5"/>
  <circle class="rfpt" cx="303.7" cy="211.3" r="5.5"/>
  <text class="rfgrn" x="314" y="290">Scalar sum, one accumulator: ~1 GFLOPS</text>
  <text class="rfgrn" x="314" y="256">SIMD, accumulators, cores: push up</text>
  <text class="rfgrn" x="252" y="200" text-anchor="end">Data in DRAM: ≤ 9.6</text>
  <circle class="rfpt" cx="636.3" cy="99.2" r="5.5"/>
  <text class="rfgrn" x="628" y="122" text-anchor="middle">Blocked matmul: compute-bound</text>
</svg>

   - **A point under the slope**: bound by bandwidth. Either move fewer bytes, or do more work on the same bytes (raise the intensity, which moves the point right).
   - **A point under the flat roof**: bound by compute. Raising the intensity won't help; keep the execution units full (vectorization, FMA, multiple accumulators).
   - **A point far below both roofs**: it touches neither limit, and the problem is elsewhere (1.5). The scalar sum with one accumulator in the chart is such a case: it does one add every 4 cycles (the add latency), about 1 GFLOPS, an order of magnitude below the bandwidth roof.

### 1.3 Roofs per Level: Data in a Given Level Gets That Level's Bandwidth {#hierarchical}

1. **There is more than one slope: every cache level has its own bandwidth**
   - **L1 bandwidth is more than an order of magnitude above memory's**: the dashed line in the chart is the slope with all data in L1, which reaches the flat roof at 0.5 FLOP/B.
   - **The same sum lands on different slopes depending on whether the array fits in L1**: every time the array falls out of a cache level, performance drops to the next lower slope; these are the "bigger array, slower" steps ([memory latency and bandwidth special](/posts/low-latency-memory-latency-bandwidth/) 1.5).
2. **Intensity is per level too: the denominator is the bytes moved from that level**
   - **Blocking** doesn't reduce the work, it reduces the bytes moved from memory: once a block of data is in cache it is reused many times, so the intensity seen by memory goes up, and the point moves right, off the slope.
   - **That is how matrix multiply moves from the slope to the flat roof**: without blocking each number is read from memory many times, and the intensity is low; with blocking each number is read once and used tens of times.

### 1.4 Under the Slope, Move Fewer Bytes; Under the Flat Roof, Keep the Units Full {#what-to-do}

1. **Bandwidth-bound (memory-bound): move fewer bytes, open fewer data streams**
   - **Read only the fields you need**: turn an array of structs into one array per field (SoA), use narrower types (`double` → `float`, `int64` → `int32`).
   - **Merge several passes into one**: compute several factors in the same scan, so the data is read from memory once.
   - **Blocking**: let a block of data be used several times while it is in cache (1.3).
   - **Read with several cores**: one core can't saturate memory bandwidth (1.1).
   - **Computing factors over whole-market tick data falls in this class**: each record of a few tens of bytes gets only a few operations, an intensity far below 1. The concrete steps are in the "sequentially scanned data" box of [trading architecture Part 8](/zh/ref/trading-architecture/#batch) (Chinese only for now).
2. **Compute-bound: keep the execution units full**
   - **Vectorize**: one instruction handles 8 `float`s ([#15](/posts/simd-vectorization-intrinsics/)).
   - **Break dependency chains**: multiple accumulators, so several operations are in the execution units at once ([#9](/posts/loop-optimization/)).
   - **Use cheaper operations**: multiply by a reciprocal instead of dividing, shift instead of multiplying by a constant ([#12](/posts/strength-reduction-arithmetic/)).
   - **Do less work**: update incrementally instead of recomputing the whole window every time.

### 1.5 What Roofline Can't See: Latency and Dependencies {#roofline-limits}

1. **The slope assumes memory requests keep the pipe full**
   - **The bandwidth roof is reached only with many requests in flight at once**: $\text{bandwidth} = \text{requests in flight} \times 64\ \text{B} \div \text{latency}$ (Little's law).
   - **Pointer chasing has only one request in flight**: linked lists, `std::map`, multi-level lookups each wait for the previous step's load, and run one or two orders of magnitude below the slope. On the chart such a program sits far below the roof, but the cause is neither compute nor bandwidth; it is latency.
2. **The flat roof assumes the execution units are busy**
   - **Dependency chains, branch mispredictions and instruction-cache misses all leave the point below both roofs**: roofline tells you only "still far from the limit", not where it is stuck.
3. **Most of an HFT hot path is exactly this case**
   - **Each market-data message touches only a few cache lines and does little arithmetic**: bandwidth and compute are nowhere near full, and the latency goes into cache misses and dependencies ([cache case study special](/posts/low-latency-cache-case-study/)).
   - **So roofline suits batch computation better**: backtests, factor computation, market-data replay; the hot path needs the next part's TMA to break it down.

## 2. Where the Pipeline Stalls: TMA Charges Every Slot to One of Four Categories {#tma}

### 2.1 The Unit of Account Is the Pipeline Slot: 4–6 per Cycle, and a Slot Has Only Four Fates {#slots}

1. **A pipeline slot is one place for the front end to hand a µop to the back end**
   - **µop (micro-op)**: one of the one-to-several internal operations the CPU splits an x86 instruction into.
   - **How many per cycle**: it depends on the microarchitecture; older Intel cores take 4, newer ones 5–6. The total number of slots over a stretch of time = width × cycles.
2. **TMA (Top-down Microarchitecture Analysis) books every slot by asking just two questions**
   - **Did this slot issue a µop?** If not, either the front end didn't deliver one (**Frontend Bound**) or the back end was full and couldn't take it (**Backend Bound**).
   - **Did the issued µop finally retire?** If so, it was useful work (**Retiring**); if not, it was work done after a wrong branch guess and flushed (**Bad Speculation**).
   - **The four categories add up to exactly 100%**: every slot falls into exactly one, so the four ratios can be compared directly, and you look at the largest first.

<svg viewBox="0 0 760 330" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="TMA classification tree. At the top are the pipeline slots, 4 to 6 per cycle. The first question is whether the slot issued a micro-op: if not, it splits into the front end delivering nothing (Frontend Bound) and the back end unable to accept (Backend Bound); if so, the next question is whether it retired: not retired is wasted work (Bad Speculation), retired is useful (Retiring). Second level: Frontend Bound splits into fetch latency (instruction-cache and iTLB misses) and fetch bandwidth (decode can't keep up); Backend Bound splits into Memory Bound (waiting for data, further split into L1, L2, L3, DRAM and stores) and Core Bound (divider, execution ports, dependency chains); Bad Speculation splits into branch mispredicts and machine clears (memory-ordering conflicts, self-modifying code); Retiring splits into light and heavy operations (microcode)." style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif">
  <style>
    .tmbg   { fill: #fbfaf7; }
    .tmtop  { fill: #eef1f4; stroke: #9aa6b2; stroke-width: 1.3; }
    .tmno   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .tmyes  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .tmsub  { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.2; }
    .tmln   { stroke: #6b6558; stroke-width: 1.3; fill: none; }
    .tmink  { fill: #1c1b18; font-size: 12px; }
    .tmhd   { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .tmsm   { fill: #1c1b18; font-size: 11.5px; }
    .tmmut  { fill: #6b6558; font-size: 11.5px; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmbg { fill: #17161b; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmtop { fill: #23262c; stroke: #5a6470; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmno { fill: #4a2f2c; stroke: #8f5a4c; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmyes { fill: #33421f; stroke: #8fb257; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmsub { fill: #201f26; stroke: #3a3945; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmln { stroke: #a39d90; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmink { fill: #e8e4da; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmhd { fill: #e8e4da; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmsm { fill: #e8e4da; }
  :root:is([data-theme="dark"], [data-theme="black"]) .tmmut { fill: #a39d90; }
  </style>
  <rect class="tmbg" x="0" y="0" width="760" height="330" rx="10"/>
  <rect class="tmtop" x="230" y="14" width="300" height="38" rx="6"/>
  <text class="tmhd" x="380" y="38" text-anchor="middle">Pipeline slots: 4–6 per cycle</text>
  <path class="tmln" d="M380 52V66M197 66H563M197 66V80M563 66V80"/>
  <text class="tmmut" x="197" y="98" text-anchor="middle">No µop issued</text>
  <text class="tmmut" x="563" y="98" text-anchor="middle">Issued: did it retire?</text>
  <path class="tmln" d="M197 104V112M106 112H289M106 112V124M289 112V124M563 104V112M472 112H655M472 112V124M655 112V124"/>
  <rect class="tmno" x="24" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="106" y="144" text-anchor="middle">Frontend Bound</text>
  <text class="tmsm" x="106" y="162" text-anchor="middle">front end sent nothing</text>
  <rect class="tmno" x="207" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="289" y="144" text-anchor="middle">Backend Bound</text>
  <text class="tmsm" x="289" y="162" text-anchor="middle">back end can't accept</text>
  <rect class="tmno" x="390" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="472" y="144" text-anchor="middle">Bad Speculation</text>
  <text class="tmsm" x="472" y="162" text-anchor="middle">not retired: flushed</text>
  <rect class="tmyes" x="573" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="655" y="144" text-anchor="middle">Retiring</text>
  <text class="tmsm" x="655" y="162" text-anchor="middle">retired: useful work</text>
  <path class="tmln" d="M106 172V190M289 172V190M472 172V190M655 172V190"/>
  <rect class="tmsub" x="24" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="34" y="212">Fetch latency:</text>
  <text class="tmsm" x="34" y="230">I-cache, iTLB misses,</text>
  <text class="tmsm" x="34" y="248">refetch after jumps</text>
  <text class="tmink" x="34" y="276">Fetch bandwidth:</text>
  <text class="tmsm" x="34" y="294">decode can't keep up</text>
  <rect class="tmsub" x="207" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="217" y="212">Memory Bound: waiting</text>
  <text class="tmsm" x="217" y="230">for data; split into L1,</text>
  <text class="tmsm" x="217" y="248">L2, L3, DRAM, Store</text>
  <text class="tmink" x="217" y="276">Core Bound:</text>
  <text class="tmsm" x="217" y="294">divider, ports, chains</text>
  <rect class="tmsub" x="390" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="400" y="212">Branch mispredicts:</text>
  <text class="tmsm" x="400" y="230">wrong direction/target</text>
  <text class="tmink" x="400" y="258">Machine Clear:</text>
  <text class="tmsm" x="400" y="276">memory-order conflict,</text>
  <text class="tmsm" x="400" y="294">self-modifying code</text>
  <rect class="tmsub" x="573" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="583" y="212">Light ops:</text>
  <text class="tmsm" x="583" y="230">one µop per instruction</text>
  <text class="tmink" x="583" y="258">Heavy ops:</text>
  <text class="tmsm" x="583" y="276">microcode sequences,</text>
  <text class="tmsm" x="583" y="294">very long instructions</text>
</svg>

### 2.2 Drilling Down: Each Category Splits into Two or Three, Level by Level, Down to the Hardware {#drill-down}

1. **The first level only gives the direction; the second level tells you what to change**

   | Level 2 | What it means | Common causes and where to look |
   |---|---|---|
   | Memory Bound | The back end is waiting for data | Working set too large, random access, false sharing ([cache case study special](/posts/low-latency-cache-case-study/), [#6](/posts/alignment-layout-cache-dram-geometry/)) |
   | Core Bound | The data is there, but the execution units are too few or stuck behind a dependency chain | Serial accumulation, division, scalar code ([#9](/posts/loop-optimization/), [#12](/posts/strength-reduction-arithmetic/)) |
   | Branch mispredicts | A wrong guess empties the pipeline and starts over | Data-dependent branches ([#7](/posts/branch-prediction-branch-optimization/)) |
   | Machine Clear | No branch was guessed wrong, yet the CPU cleared the pipeline | Another core wrote a line you just read (memory-ordering conflict), false sharing ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)) |
   | Fetch latency | The instructions aren't in cache, or there are too many jumps | Hot-path code too large, cold code mixed in ([#7](/posts/branch-prediction-branch-optimization/) Part 3) |
   | Fetch bandwidth | The instructions are there, but decode can't deliver them fast enough | Rarely the main cause; usually very long instructions or alignment |
   | Heavy operations | One instruction is split into many µops | Microcoded instructions, some string instructions, division |

2. **High Retiring doesn't mean there's nothing to do**
   - **It only says the slots weren't wasted**: if the work itself is unnecessary (scalar code, repeated computation), Retiring is high too. Then go back to roofline and ask whether to vectorize or do less work.
3. **At each level, drill only into the largest category**
   - **If Backend Bound is largest at level 1, look only at its Memory Bound and Core Bound**; only if Memory Bound is large do you look at which cache level. Leave the other branches alone for now.

### 2.3 How to Measure: perf stat's Topdown Metric Groups {#measure}

1. **On Intel machines**
   - **Level 1**: `perf stat -M TopdownL1 -- ./bench` prints the four ratios directly.
   - **Level 2**: `perf stat -M TopdownL2 -- ./bench`.
   - **Deeper levels**: use `toplev` from pmu-tools, for example `toplev -l3 ./bench`, which marks the largest category at each level.
2. **On AMD machines**
   - **Zen 4 and later have similar metric groups**: `perf stat -M PipelineL1`, `PipelineL2`. The category names differ somewhat from Intel's; the idea is the same.
3. **You need hardware counters**
   - **Every TMA ratio is computed from hardware events**: many virtual machines don't pass the counters through to the guest, and then `-M` reports it as unsupported (the machine in the [perf special](/posts/low-latency-perf-profiling/) 4.2 is one).

### 2.4 Once You Know the Category, Find the Code: Sample That Category's Precise Event {#locate}

1. **The problem: TMA tells you "Memory Bound is 60%", not which line**
2. **The fix: sample with the event that matches the category, and the samples land on the offending instruction**

   | Category | Sampling event (Intel names) |
   |---|---|
   | Branch mispredicts | `br_misp_retired.all_branches` |
   | Memory Bound | `mem_load_retired.l3_miss` (or `l1_miss`, `l2_miss`, depending on which level the third level points at) |
   | Fetch latency | `frontend_retired.l2_miss`, `frontend_retired.itlb_miss` |
   | Machine Clear (false sharing) | Use `perf c2c` instead ([perf special](/posts/low-latency-perf-profiling/) 3.3) |
   | Core Bound | Plain `cycles` sampling, then look for dependency chains and divisions in `perf annotate` |

   - **The command**: `perf record -e br_misp_retired.all_branches:pp -- ./bench`, then `perf report` and `perf annotate`.
   - **`:pp` asks for precise sampling**: an ordinary sample records an instruction address that slides a few instructions late (skid), so the sample lands after the offending instruction; `:pp` makes Intel's PEBS hardware record that instruction's own address.
   - **Then fix it from the bottleneck cards**: each card says what you see in perf, how to change it and how to verify (the In Practice section).

### 2.5 Two Preconditions: No Gross Problem in the Code, No Interference from the Environment {#preconditions}

1. **Fix the obvious problems before using TMA**
   - **Examples**: an $O(n^2)$ algorithm, a debug build with optimization off, logging inside the hot loop. TMA's ratios still come out, but they lead you into microarchitectural detail while the real problem is a level above.
2. **The measurement environment has to be stable**
   - **Pinned cores, fixed frequency, nothing else running on the machine**: otherwise other processes' cache pollution and frequency drops are counted into the ratios ([#1](/posts/cpu-affinity-core-isolation-numa/), [#19](/posts/scheduling-priority-inversion-kernel-tuning/)).
   - **Run long enough**: the counters are multiplexed (several groups of events take turns), and ratios from a short run jitter.

## 3. Using It on a Trading System: The Hot Path Spends Most of Its Time Spinning {#in-trading}

1. **The problem: running TMA on the whole trading process measures almost nothing but polling**
   - **A market-data thread spends nearly all its time busy-polling**: an idle loop runs very smoothly and Retiring is high, so the few microseconds of real message handling are drowned out.
2. **The fix: take the handler out on its own and measure it on a replay benchmark**
   - **Replay recorded market data**: a loop calls the handler back to back, and only that stretch is measured, so roofline and TMA both measure the real handling logic.
   - **Or count only during handling**: `perf stat --control` lets the program itself turn counting on when handling starts and off when it ends.
3. **Each method covers one kind of code**
   - **Batch computation (factors, backtests, replay)**: roofline first, to see whether it's bound by bandwidth or compute and how far from the roof.
   - **The hot path**: on roofline it is far from both roofs (1.5), so go straight to TMA; it is usually Memory Bound (cache misses) or branch mispredicts.
4. **The whole procedure**
   - **perf finds the hot function** → **roofline decides computing or moving data** → **TMA finds the pipeline category** → **sampling the matching event finds the line** → **fix it from the bottleneck card, then measure the distribution again** ([#21](/posts/trading-system-latency-metrics/) 1.2).

## In Practice {#in-practice}

How TMA's second level maps to the [bottleneck cards](/ref/bottlenecks/):

| TMA level 2 | Cards to check first |
|---|---|
| Core Bound | {{% bottleneck-ref "serial-accumulator" %}}, {{% bottleneck-ref "narrow-vector" %}}, {{% bottleneck-ref "missing-restrict" %}} |
| Memory Bound | {{% bottleneck-ref "false-sharing" %}}, {{% bottleneck-ref "shared-counter" %}} |
| Branch mispredicts | {{% bottleneck-ref "unpredictable-branch" %}} |
| Fetch latency | {{% bottleneck-ref "cold-path" %}} |
| Locks and atomics within Backend Bound | {{% bottleneck-ref "tas-spinlock" %}} |
