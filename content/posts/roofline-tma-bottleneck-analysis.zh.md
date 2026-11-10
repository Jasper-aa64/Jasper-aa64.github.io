---
title: "交易系统笔记 #23：roofline 和 TMA：瓶颈在算还是在搬，卡在流水线哪一段"
date: 2026-11-09
slug: "roofline-tma-bottleneck-analysis"
description: "perf 告诉你时间花在哪个函数、哪条指令上，不告诉你为什么。roofline 用峰值算力和峰值带宽两条屋顶框住性能：程序的计算强度决定它撞哪一面，离屋顶多远就是还能省多少；它假设内存请求能排满，看不到延迟。TMA 把每个周期的每个流水线槽位记到前端、后端、白做、有用四类之一，再一层层往下分，最后按那一类的精确事件采样，定位到代码行。交易系统的热路径大部分时间在空转，要在回放基准上测。"
summary: "两步找瓶颈：roofline 回答“受算力限制还是带宽限制、离上限多远”，TMA 回答“流水线卡在哪一段”，再按对应的事件采样找到代码。"
chapter: 2
categories: [Systems]
tags: [roofline, tma, topdown, perf, profiling, pmu, hft, low-latency]
toc: true
math: true
build:
  list: never
---

[perf 专题](/zh/posts/low-latency-perf-profiling/)能告诉你时间花在哪个函数、哪条指令上，可光知道“这个循环热”还不够：它是算得太多，还是数据来得太慢？是在等内存，还是分支老猜错？离硬件的上限还有多远，值不值得再抠？这一篇的两个方法分别回答这两层问题：roofline 先判断瓶颈在算还是在搬、离上限多远；TMA 再把“慢”拆到流水线的具体一段，最后落到代码行。

> **这篇的问题链：每解决一个，下一个就露出来**
> 1. **优化之前不知道上限在哪**：roofline 用峰值算力和峰值带宽画出两面屋顶（第 1 节）。
> 2. **roofline 只分得出“算”和“搬”，看不到延迟和流水线**：TMA 把每个流水线槽位记到四类之一，一层层往下分（2.1–2.3）。
> 3. **TMA 只说出了类别，不知道是哪行代码**：按这一类对应的精确事件采样（2.4）。
> 4. **交易系统的热路径大部分时间在空转，整个进程测出来全是轮询**：在回放基准上测处理函数（第 3 节）。

---

## 1. 程序离上限还有多远：roofline 用算力和带宽两面屋顶框住性能 {#roofline}

### 1.1 两个硬件上限：峰值算力和峰值带宽 {#peaks}

1. **峰值算力：每秒最多能做多少次浮点运算（FLOPS）**
   - **按执行单元数出来**：以一颗 4 核、最高 3.8 GHz、每核 2 个 FMA 单元、支持 AVX2 的笔记本 CPU 为例（Intel i5-8259U）。一条 256 位的 FMA 指令同时处理 8 个 `float`，每个做一次乘一次加，算 2 次运算：

     $$
     \text{峰值算力} = \underbrace{4}_{\text{物理核}} \times \underbrace{2}_{\text{FMA 单元}} \times \underbrace{8}_{\substack{\text{256 位里的} \\ \text{float 个数}}} \times \underbrace{2}_{\substack{\text{一次乘加} \\ \text{算 2 次}}} \times 3.8\ \text{GHz} \approx 486\ \text{GFLOPS}
     $$

   - **按物理核算，不按超线程算**：一个核上的两个超线程共用这 2 个 FMA 单元，不会多出算力。
   - **这是够不到的上界**：3.8 GHz 是单核睿频，所有核一起跑时频率更低；还要求每条指令都是 FMA、每周期两个单元都不空。
2. **峰值带宽：每秒最多能从内存搬多少字节**
   - **按内存条和通道数算**：同一台机器插 DDR4-2400、两个通道，每次传 64 位（8 B）：

     $$
     \text{峰值带宽} = \underbrace{2400\ \text{MT/s}}_{\text{每秒传输次数}} \times \underbrace{2}_{\text{通道}} \times \underbrace{8\ \text{B}}_{\text{每次 64 位}} = 38.4\ \text{GB/s}
     $$

   - **一个核自己吃不满**：单核能拿到的带宽受同时在路上的请求数限制（[内存延迟与带宽专题](/zh/posts/low-latency-memory-latency-bandwidth/) 1.3），要几个核一起读才接近这个数。

### 1.2 程序的计算强度决定撞哪一面屋顶 {#intensity}

1. **程序这一侧也有两个量：计算量和访存量**
   - **计算强度**（arithmetic intensity）：每搬 1 个字节做几次运算，单位 FLOP/B。
   - **例子**：`float` 求和每读 4 B 做 1 次加法，强度 0.25；点积每读 8 B（`a[i]`、`b[i]` 各一个）做一次乘一次加，也是 0.25。
2. **能达到的性能是两面屋顶里低的那一面**

   $$
   P \;=\; \min\big(\,P_{\text{peak}},\;\; I \times B_{\text{peak}}\,\big)
   $$

   - **$I$ 小的时候**：$I \times B_{\text{peak}}$ 更小，性能被带宽卡住（memory-bound），落在斜坡上。上面的求和最多 $0.25 \times 38.4 \approx 9.6$ GFLOPS，只有峰值算力的 2%。
   - **$I$ 大的时候**：性能被算力卡住（compute-bound），落在平顶上。
   - **拐点**（ridge point）：两面屋顶相交处，$I^* = P_{\text{peak}} / B_{\text{peak}} = 486 / 38.4 \approx 12.7$ FLOP/B。强度低于它，先撞带宽；高于它，先撞算力。
3. **把程序实测的性能点上去，离屋顶的距离就是还能省多少**

<svg viewBox="0 0 760 420" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="roofline 图，横轴是计算强度（每字节多少次浮点运算，对数刻度，0.01 到 100），纵轴是性能（GFLOPS，对数刻度，0.1 到 1000）。实线是内存带宽屋顶 38.4 GB/s 的斜坡，在 12.7 FLOP/B 处和 486 GFLOPS 的算力平顶相交。虚线是数据在 L1 里时更陡、更高的斜坡，在 0.5 FLOP/B 处碰到平顶。float 求和的强度是 0.25：数据在内存里时最多约 9.6 GFLOPS，正好落在实线斜坡上；一个累加器的标量版每 4 个周期做一次加法，约 1 GFLOPS，远在屋顶下面，向量化、多累加器、多核把它往上推，推到斜坡就停。分块矩阵乘强度几十，落在平顶下面，受算力限制。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
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
  <text class="rfink" x="400" y="406" text-anchor="middle">计算强度（FLOP/字节，对数刻度）</text>
  <text class="rfmut" x="72" y="364" text-anchor="end">0.1</text>
  <text class="rfmut" x="72" y="289" text-anchor="end">1</text>
  <text class="rfmut" x="72" y="214" text-anchor="end">10</text>
  <text class="rfmut" x="72" y="139" text-anchor="end">100</text>
  <text class="rfmut" x="72" y="64" text-anchor="end">1000</text>
  <text class="rfink" x="24" y="210" text-anchor="middle" transform="rotate(-90 24 210)">性能（GFLOPS，对数刻度）</text>
  <path class="rfl1" d="M80 210.9L351.8 83.5"/>
  <path class="rfmem" d="M80 316.2L576.4 83.5"/>
  <path class="rfcpu" d="M351.8 83.5H720"/>
  <path class="rfrdg" d="M576.4 83.5V360"/>
  <text class="rfink" x="720" y="74" text-anchor="end">算力屋顶 486 GFLOPS</text>
  <text class="rfred" x="330" y="236" transform="rotate(-25.1 330 236)">内存带宽屋顶 38.4 GB/s</text>
  <text class="rfred" x="120" y="180" transform="rotate(-25.1 120 180)">数据在 L1 里：更高的斜坡</text>
  <text class="rfmut" x="584" y="352">拐点 12.7 FLOP/B</text>
  <path class="rfarr" d="M303.7 280V222"/>
  <path class="rfah" d="M303.7 216l-5 9h10z"/>
  <circle class="rfpt2" cx="303.7" cy="286.6" r="5"/>
  <circle class="rfpt" cx="303.7" cy="211.3" r="5.5"/>
  <text class="rfgrn" x="314" y="290">一个累加器的标量求和：约 1 GFLOPS</text>
  <text class="rfgrn" x="314" y="256">向量化、多累加器、多核：往上推</text>
  <text class="rfgrn" x="252" y="200" text-anchor="end">数据在内存里：顶多 9.6</text>
  <circle class="rfpt" cx="636.3" cy="99.2" r="5.5"/>
  <text class="rfgrn" x="628" y="122" text-anchor="middle">分块矩阵乘：受算力限制</text>
</svg>

   - **点在斜坡下面**：受带宽限制，要么少搬字节，要么让同样的字节多算几次（提高强度，点往右移）。
   - **点在平顶下面**：受算力限制，再提高强度也没用，要把执行单元用满（向量化、FMA、多个累加器）。
   - **点离屋顶很远**：两个上限都没碰到，问题在别处（1.5）。图里一个累加器的标量求和就是这样：每 4 个周期才做一次加法（加法延迟），约 1 GFLOPS，比带宽屋顶低一个数量级。

### 1.3 屋顶按层分：数据在哪一层，就用哪一层的带宽 {#hierarchical}

1. **斜坡不止一条：每一层缓存都有自己的带宽**
   - **L1 的带宽比内存高一个数量级以上**：图里的虚线就是数据全在 L1 里时的斜坡，0.5 FLOP/B 就碰到平顶了。
   - **同一个求和，数组装得进 L1 和装不进，落在不同的斜坡上**：数组每掉出一层缓存，性能就换到更低的那条斜坡，这就是“数组越大越慢”的台阶（[内存延迟与带宽专题](/zh/posts/low-latency-memory-latency-bandwidth/) 1.5）。
2. **计算强度也分层算：分母是从那一层搬的字节**
   - **分块**（blocking）不减少运算，减少的是从内存搬的字节：一块数据装进缓存后被重复用很多次，对内存来说强度变高了，点往右移，离开斜坡。
   - **矩阵乘就是这样从斜坡挪到平顶的**：不分块时每个数从内存读很多遍，强度很低；分块以后每个数读一遍、用几十次。

### 1.4 落在斜坡下就少搬字节，落在平顶下就把执行单元用满 {#what-to-do}

1. **受带宽限制（memory-bound）：少搬字节、少开数据流**
   - **只读要的字段**：结构体数组换成按字段分开的数组（SoA），换窄类型（`double` → `float`、`int64` → `int32`）。
   - **几遍合成一遍**：几个因子在同一遍扫描里一起算，数据只从内存读一次。
   - **分块**：让一块数据在缓存里被多用几次（1.3）。
   - **多个核一起读**：一个核吃不满内存带宽（1.1）。
   - **全市场逐笔数据跑因子就在这一类**：每读几十字节的一条记录只做几次运算，强度远低于 1。具体做法见[交易系统架构第 8 部分](/zh/ref/trading-architecture/)的“顺序扫的数据”那个框。
2. **受算力限制（compute-bound）：把执行单元用满**
   - **向量化**：一条指令处理 8 个 `float`（[#15](/zh/posts/simd-vectorization-intrinsics/)）。
   - **拆依赖链**：多个累加器，让几次运算同时在执行单元里（[#9](/zh/posts/loop-optimization/)）。
   - **换便宜的运算**：除法换乘倒数、乘常数换移位（[#12](/zh/posts/strength-reduction-arithmetic/)）。
   - **少做运算**：增量更新代替每次重算整个窗口。

### 1.5 roofline 看不到的：延迟和依赖 {#roofline-limits}

1. **斜坡假设内存请求能排满**
   - **带宽屋顶要靠很多请求同时在路上才达得到**：$\text{带宽} = \text{在路上的请求数} \times 64\ \text{B} \div \text{延迟}$（Little 定律）。
   - **pointer chasing 只有一个请求在路上**：链表、`std::map`、多级查表，每一步都要等上一步读回来，性能比斜坡低一两个数量级。这种程序在图上离屋顶很远，可原因既不是算力也不是带宽，是延迟。
2. **平顶假设执行单元都忙**
   - **依赖链、分支预测失败、指令缓存缺失，都会让点停在两面屋顶下面**：roofline 只告诉你“离上限还远”，不告诉你卡在哪。
3. **HFT 的热路径大多就是这种情况**
   - **每条行情只碰几条缓存行，运算也很少**：带宽和算力都远没用满，延迟全花在缓存缺失和依赖上（[缓存案例专题](/zh/posts/low-latency-cache-case-study/)）。
   - **所以 roofline 更适合批量计算**：回测、因子计算、行情回放；热路径要用下一节的 TMA 往下拆。

## 2. 卡在流水线哪一段：TMA 把每个槽位记到四类之一 {#tma}

### 2.1 记账单位是流水线槽位：每周期 4–6 个，一个槽只有四种结局 {#slots}

1. **槽位（pipeline slot）是前端往后端送 µop 的名额**
   - **µop（微操作）**：CPU 把一条 x86 指令拆成的一到几个内部操作。
   - **每周期最多送几个**：看微架构，较老的 Intel 核 4 个，新一点的 5–6 个。一段时间的总槽位数 = 宽度 × 周期数。
2. **TMA（Top-down Microarchitecture Analysis）给每个槽位记一笔账，只问两个问题**
   - **这个槽位送出 µop 了吗**：没送出，要么是前端没送来（**Frontend Bound**），要么是后端满了接不住（**Backend Bound**）。
   - **送出的 µop 最后提交了吗**：提交了就是有用的工作（**Retiring**）；没提交，就是猜错分支以后白做、被冲掉了（**Bad Speculation**）。
   - **四类加起来正好 100%**：每个槽位只落进一类，所以四个比例可以直接比，哪一类最大就先查哪一类。

<svg viewBox="0 0 760 330" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="TMA 的分类树。最上面是流水线槽位，每周期 4 到 6 个。第一个问题是这个槽送出微操作了吗：没送出，分成前端没送来（Frontend Bound）和后端接不住（Backend Bound）；送出了，再问最后提交了吗：没提交是白做（Bad Speculation），提交了是有用（Retiring）。第二层：Frontend Bound 分取指延迟（指令缓存、iTLB 缺失）和取指带宽（解码跟不上）；Backend Bound 分 Memory Bound（等数据，再分 L1、L2、L3、DRAM、存储）和 Core Bound（除法器、执行端口、依赖链）；Bad Speculation 分分支预测失败和 Machine Clear（内存序冲突、自修改代码）；Retiring 分轻操作和重操作（微码）。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
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
  <text class="tmhd" x="380" y="38" text-anchor="middle">流水线槽位：每周期 4–6 个</text>
  <path class="tmln" d="M380 52V66M197 66H563M197 66V80M563 66V80"/>
  <text class="tmmut" x="197" y="98" text-anchor="middle">没送出 µop</text>
  <text class="tmmut" x="563" y="98" text-anchor="middle">送出了：最后提交了吗？</text>
  <path class="tmln" d="M197 104V112M106 112H289M106 112V124M289 112V124M563 104V112M472 112H655M472 112V124M655 112V124"/>
  <rect class="tmno" x="24" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="106" y="144" text-anchor="middle">Frontend Bound</text>
  <text class="tmsm" x="106" y="162" text-anchor="middle">前端没送来</text>
  <rect class="tmno" x="207" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="289" y="144" text-anchor="middle">Backend Bound</text>
  <text class="tmsm" x="289" y="162" text-anchor="middle">后端满了接不住</text>
  <rect class="tmno" x="390" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="472" y="144" text-anchor="middle">Bad Speculation</text>
  <text class="tmsm" x="472" y="162" text-anchor="middle">没提交：白做、被冲掉</text>
  <rect class="tmyes" x="573" y="124" width="165" height="48" rx="6"/>
  <text class="tmhd" x="655" y="144" text-anchor="middle">Retiring</text>
  <text class="tmsm" x="655" y="162" text-anchor="middle">提交了：有用的工作</text>
  <path class="tmln" d="M106 172V190M289 172V190M472 172V190M655 172V190"/>
  <rect class="tmsub" x="24" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="34" y="212">取指延迟：</text>
  <text class="tmsm" x="34" y="230">指令缓存、iTLB 缺失，</text>
  <text class="tmsm" x="34" y="248">跳转后重新取指</text>
  <text class="tmink" x="34" y="276">取指带宽：</text>
  <text class="tmsm" x="34" y="294">解码跟不上</text>
  <rect class="tmsub" x="207" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="217" y="212">Memory Bound：等数据</text>
  <text class="tmsm" x="217" y="230">再分 L1、L2、L3、</text>
  <text class="tmsm" x="217" y="248">DRAM、Store Bound</text>
  <text class="tmink" x="217" y="276">Core Bound：</text>
  <text class="tmsm" x="217" y="294">除法器、端口、依赖链</text>
  <rect class="tmsub" x="390" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="400" y="212">分支预测失败：</text>
  <text class="tmsm" x="400" y="230">猜错方向或目标</text>
  <text class="tmink" x="400" y="258">Machine Clear：</text>
  <text class="tmsm" x="400" y="276">内存序冲突、</text>
  <text class="tmsm" x="400" y="294">自修改代码</text>
  <rect class="tmsub" x="573" y="190" width="165" height="120" rx="6"/>
  <text class="tmink" x="583" y="212">轻操作：</text>
  <text class="tmsm" x="583" y="230">一条指令一个 µop</text>
  <text class="tmink" x="583" y="258">重操作：</text>
  <text class="tmsm" x="583" y="276">微码序列、</text>
  <text class="tmsm" x="583" y="294">很长的指令</text>
</svg>

### 2.2 往下钻：每一类再分两三类，一层层分到具体硬件 {#drill-down}

1. **第一层只说大方向，要看第二层才知道该改什么**

   | 第二层 | 什么意思 | 常见原因和去哪看 |
   |---|---|---|
   | Memory Bound | 后端在等数据 | 工作集太大、随机访问、伪共享（[缓存案例专题](/zh/posts/low-latency-cache-case-study/)、[#6](/zh/posts/alignment-layout-cache-dram-geometry/)） |
   | Core Bound | 数据到了，执行单元不够用或者被依赖链卡住 | 串行累加、除法、标量代码（[#9](/zh/posts/loop-optimization/)、[#12](/zh/posts/strength-reduction-arithmetic/)） |
   | 分支预测失败 | 猜错以后清空流水线重来 | 数据相关的分支（[#7](/zh/posts/branch-prediction-branch-optimization/)） |
   | Machine Clear | 不是分支猜错，CPU 也把流水线清了 | 别的核改了你刚读过的行（内存序冲突）、伪共享（[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/)） |
   | 取指延迟 | 指令没在缓存里，或者跳转太多 | 热路径代码太大、冷代码混在里面（[#7](/zh/posts/branch-prediction-branch-optimization/) 第 3 节） |
   | 取指带宽 | 指令都在，解码送不过来 | 很少是主因，多是很长的指令或者对齐问题 |
   | 重操作 | 一条指令被拆成很多 µop | 微码指令、某些字符串指令、除法 |

2. **Retiring 高不等于没事可做**
   - **它只说明槽位没浪费**：如果做的本来就是多余的工作（标量代码、重复计算），Retiring 也会很高。这时要回到 roofline，看是不是该向量化、少做运算。
3. **每一层只往最大的那一类钻**
   - **第一层 Backend Bound 最大，就只看它下面的 Memory Bound 和 Core Bound**；Memory Bound 再大，才看是哪一层缓存。其他分支先不管。

### 2.3 怎么测：perf stat 的 topdown 指标组 {#measure}

1. **Intel 的机器**
   - **第一层**：`perf stat -M TopdownL1 -- ./bench`，四个比例直接打出来。
   - **第二层**：`perf stat -M TopdownL2 -- ./bench`。
   - **更深几层**：用 pmu-tools 里的 `toplev`，例如 `toplev -l3 ./bench`，它会把每一层最大的那一类标出来。
2. **AMD 的机器**
   - **Zen 4 起有类似的指标组**：`perf stat -M PipelineL1`、`PipelineL2`，分类的名字和 Intel 不完全一样，思路相同。
3. **要有硬件计数器**
   - **TMA 的每个比例都是从硬件事件算出来的**：很多虚拟机不把计数器交给客户机，这时 `-M` 会报不支持（[perf 专题](/zh/posts/low-latency-perf-profiling/) 4.2 那台机器就是这样）。

### 2.4 知道类别以后定位到代码：按这一类的精确事件采样 {#locate}

1. **痛点：TMA 只告诉你“Memory Bound 占 60%”，不告诉你是哪一行**
2. **解决：用和这一类对应的事件采样，样本就落在惹事的指令上**

   | 类别 | 采样事件（Intel 的名字） |
   |---|---|
   | 分支预测失败 | `br_misp_retired.all_branches` |
   | Memory Bound | `mem_load_retired.l3_miss`（或 `l1_miss`、`l2_miss`，看第三层是哪一层） |
   | 取指延迟 | `frontend_retired.l2_miss`、`frontend_retired.itlb_miss` |
   | Machine Clear（伪共享） | 改用 `perf c2c`（[perf 专题](/zh/posts/low-latency-perf-profiling/) 3.3） |
   | Core Bound | 普通的 `cycles` 采样，再在 `perf annotate` 里看依赖链和除法 |

   - **命令**：`perf record -e br_misp_retired.all_branches:pp -- ./bench`，再 `perf report`、`perf annotate`。
   - **`:pp` 要精确采样**：普通采样记下的指令地址会往后滑几条（skid），样本落在惹事指令后面；`:pp` 让 Intel 用 PEBS 硬件直接记下那条指令的地址。
   - **然后对着瓶颈卡片改**：每张卡片写了在 perf 里看到什么、怎么改、怎么验证（应用一节）。

### 2.5 两条前提：代码没有明显的大问题，测量环境不干扰 {#preconditions}

1. **先把明显的问题修掉再用 TMA**
   - **例子**：算法是 $O(n^2)$、调试版本没开优化、热循环里在打日志。这时 TMA 的比例照样能算出来，但它会把你引到微架构的细节上，而真正的问题在上一层。
2. **测量环境要稳**
   - **绑核、固定频率、机器上没有别的负载**：否则别的进程的缓存污染、降频都会算进比例里（[#1](/zh/posts/cpu-affinity-core-isolation-numa/)、[#19](/zh/posts/scheduling-priority-inversion-kernel-tuning/)）。
   - **跑得够久**：计数器是复用的（几组事件轮流计数），跑得太短比例会抖。

## 3. 用在交易系统上：热路径大部分时间在空转 {#in-trading}

1. **痛点：对整个交易进程跑 TMA，测到的几乎全是轮询**
   - **行情线程绝大部分时间在忙轮询**：一个空转的循环跑得很顺，Retiring 很高，真正处理行情的那几微秒被淹没了。
2. **解决：把处理函数单独拿出来，在回放基准上测**
   - **用录下来的行情回放**：一个循环连续调用处理函数，只测这一段，roofline 和 TMA 测的都是真正的处理逻辑。
   - **或者只在处理期间计数**：`perf stat --control` 让程序自己在处理开始时打开计数、结束时关掉。
3. **两个方法各管一类代码**
   - **批量计算（因子、回测、回放）**：先上 roofline，看是受带宽还是受算力限制，离屋顶多远。
   - **热路径**：roofline 上离屋顶都远（1.5），直接用 TMA，多半是 Memory Bound（缓存缺失）或者分支预测失败。
4. **整个流程**
   - **perf 找到热函数** → **roofline 判断算还是搬** → **TMA 找到流水线哪一类** → **按对应事件采样找到代码行** → **按瓶颈卡片改，改完再测分布**（[#21](/zh/posts/trading-system-latency-metrics/) 1.2）。

## 应用 {#in-practice}

TMA 的第二层和[瓶颈卡片](/zh/ref/bottlenecks/)的对应关系：

| TMA 第二层 | 先看哪几张卡片 |
|---|---|
| Core Bound | {{% bottleneck-ref "serial-accumulator" %}}、{{% bottleneck-ref "narrow-vector" %}}、{{% bottleneck-ref "missing-restrict" %}} |
| Memory Bound | {{% bottleneck-ref "false-sharing" %}}、{{% bottleneck-ref "shared-counter" %}} |
| 分支预测失败 | {{% bottleneck-ref "unpredictable-branch" %}} |
| 取指延迟 | {{% bottleneck-ref "cold-path" %}} |
| Backend Bound 里的锁和原子操作 | {{% bottleneck-ref "tas-spinlock" %}} |
