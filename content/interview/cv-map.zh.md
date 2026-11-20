---
title: "IV. CV map"
date: 2026-11-18T00:00:00+08:00
slug: "cv-map"
description: "简历的专业技能、实习经历、项目 1 三块原文，每一句都能点：点进去是这一句的讲法、背后的知识点，或者能跑的完整代码。"
weight: -2
toc: true
---

这一页是简历原文，只留**专业技能、实习经历、项目 1** 三块，**每一句都能点**：

- **技能行**：每个词点进去是讲它的博客；行末的“问答”是这一行最可能被问的题（[技能行](/zh/interview/cv-skills-review/)）。
- **实习、项目**：每一句点进去是这一句的讲法；行末的“代码”是能跑的完整代码，没有“代码”的那几句是做法和数字，点进去看怎么讲。

## 1. 专业技能 {#skills}

**C++**：熟练掌握 C++，熟悉 [STL](/zh/ref/stl-containers/)、[智能指针](/zh/ref/smart-pointers/)、[模板](/zh/ref/templates/)、[RAII](/zh/ref/special-members-raii/) 与[移动语义](/zh/ref/move-semantics/)，熟悉 [CRTP 静态多态](/zh/posts/crtp-static-polymorphism/)。　→ [问答](/zh/interview/cv-skills-review/#cpp)

**CPU 架构**：熟悉 CPU 体系结构对延迟的影响：[缓存层次与缓存行](/zh/ref/cpu-memory/)、[MESI 缓存一致性](/zh/posts/low-latency-mesi-cache-coherence/)、[store buffer](/zh/posts/memory-ordering-false-sharing-dependency-chains/#store-buffer)、[乱序执行（ROB）](/zh/ref/cpu-memory/)、[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/)、[内存级并行（LFB）](/zh/posts/low-latency-memory-latency-bandwidth/)、[分支预测](/zh/posts/branch-prediction-branch-optimization/)、[TLB 与大页](/zh/posts/low-latency-context-switch-page-table-tlb/)、[NUMA 访存](/zh/posts/cpu-affinity-core-isolation-numa/)。　→ [问答](/zh/interview/cv-skills-review/#cpu)

**低延迟优化**：熟悉[缓存友好的数据布局](/zh/posts/alignment-layout-cache-dram-geometry/)、[伪共享规避](/zh/posts/memory-ordering-false-sharing-dependency-chains/#false-sharing)、[内存池与 arena 分配器](/zh/posts/hot-path-memory-allocators/)、[缓存预取与预热](/zh/posts/prefetch-warmup-double-buffer/)、[SIMD 向量化](/zh/posts/simd-vectorization-intrinsics/)、[分支优化](/zh/posts/branch-prediction-branch-optimization/)、[循环优化与指令级并行](/zh/posts/loop-optimization/)、[强度削弱与定点数运算](/zh/posts/strength-reduction-arithmetic/)。　→ [问答](/zh/interview/cv-skills-review/#optimization)

**Linux 调优**：熟悉 [CPU 绑核与核心隔离](/zh/posts/cpu-affinity-core-isolation-numa/)、[中断亲和](/zh/posts/cpu-affinity-core-isolation-numa/)、[实时调度策略与优先级](/zh/posts/scheduling-priority-inversion-kernel-tuning/#sched-classes)、[大页内存](/zh/posts/scheduling-priority-inversion-kernel-tuning/)。　→ [问答](/zh/interview/cv-skills-review/#linux-tuning)

**并发编程**：熟悉[多线程与并发编程](/zh/ref/thread-sync/)，掌握 [std::atomic 与内存序](/zh/posts/memory-ordering-false-sharing-dependency-chains/#release-acquire)、[互斥锁、条件变量](/zh/ref/thread-sync/)、[线程池](/zh/ref/thread-pool-future/)；理解 [lock-free / wait-free 的进度保证](/zh/posts/wait-free-sticky-counter/)，了解 [SPSC 无锁队列](/zh/posts/lock-free-queue-logger-micro-batching/#spsc)、[SPMC 广播队列](/zh/interview/md-feed-spmc/)、[自旋锁（TTAS、票据锁、MCS）](/zh/posts/spinlock-implementation/)、[共享内存通信](/zh/ref/ipc/)与 [micro-batching](/zh/posts/lock-free-queue-logger-micro-batching/#micro-batching)。　→ [问答](/zh/interview/cv-skills-review/#concurrency)

**系统编程**：熟悉 Linux 系统编程（[进程与 IPC](/zh/ref/ipc/)、[epoll](/zh/ref/epoll-internals/)、[mmap](/zh/interview/md-feed-spmc/#shm)、[虚拟内存与缺页](/zh/ref/new-malloc-page-fault/)）；了解 [TCP/IP](/zh/ref/tcp-states/)、[HTTP](/zh/ref/http-basics/)、[WebSocket](/zh/interview/cv-projects/#av-wss)。　→ [问答](/zh/interview/cv-skills-review/#system)

**性能分析**：熟练使用 [perf](/zh/posts/low-latency-perf-profiling/)、火焰图做性能剖析与[汇编级分析](/zh/interview/cv-projects/#triage-perf-three)，掌握[基于 TSC 的延迟测量](/zh/posts/tsc-latency-measurement/)与[分位数统计](/zh/posts/trading-system-latency-metrics/)；使用 [ASan/UBSan](/zh/ref/sanitizers/)、GTest 保障正确性；熟悉 CMake、vcpkg、Git。　→ [问答](/zh/interview/cv-skills-review/#tools)

**AI Native**：深度使用 Claude Code、Codex 等 AI 编程工具[完成工程开发与性能优化](/zh/interview/cv-projects/#skill-why)，能[编写 Agent skill 约束 Agent 的工作流程](/zh/interview/cv-projects/#skill-what)；具备 MCP Server 框架完整落地经验，了解大模型底层原理、RAG。

> **没有链接的词，本站还没有单独讲**：火焰图、GTest、CMake、vcpkg、Git、MCP Server、RAG。被问到按做过的事答。

## 2. 实习经历 {#internship}

在 Linux 上开发和优化量化交易的低延迟 C++ 系统，负责[行情接入](/zh/interview/md-feed-spmc/#md-feed)与[因子开发](/zh/interview/cv-factor/#factor-dev)，并优化[行情链路](/zh/interview/md-feed-spmc/#md-opt)、[因子计算](/zh/interview/cv-factor/#factor-opt)与[因子回测](/zh/interview/backtest-framework/)的性能。

### 2.1 行情接入 {#md-feed}

[接入两家行情源并转换为统一结构落盘](/zh/interview/md-feed-spmc/#usage)，[回调线程经 SPMC 广播队列向落盘进程交付数据](/zh/interview/md-feed-spmc/#ring)；[基于真实行情校验价格、委托类型、成交金额等字段](/zh/interview/md-feed-spmc/#md-verify)，[经整日 4.5 亿条行情回放验证](/zh/interview/md-feed-spmc/#md-replay)，[支持断线自动续传](/zh/interview/md-feed-spmc/#md-reconnect)。

→ 代码：[环](/zh/interview/md-feed-spmc/#ring)、[放进共享内存](/zh/interview/md-feed-spmc/#shm)、[回调和落盘线程](/zh/interview/md-feed-spmc/#usage)；完整程序 [SPMC 专页 3.1](/zh/interview/md-feed-spmc/#hw-md-feed)

### 2.2 行情优化 {#md-opt}

[SPMC 广播队列的读写计数按缓存行隔离、消除伪共享，高频读取场景下写入延迟中位数降低约 40%](/zh/interview/md-feed-spmc/#false-sharing)；[启动时预触内存页消除首轮缺页](/zh/interview/md-feed-spmc/#prefault)，[去掉回调中对共享时间字段的跨核读取](/zh/interview/md-feed-spmc/#clock)，[单包处理延迟中位数降低约 17%、P99 降低约 57%](/zh/interview/md-feed-spmc/#opt-measure)。

→ 代码：[伪共享改之前 / 改之后](/zh/interview/md-feed-spmc/#false-sharing)、[预触](/zh/interview/md-feed-spmc/#prefault)、[读时钟](/zh/interview/md-feed-spmc/#clock)；完整程序 [SPMC 专页 3.2](/zh/interview/md-feed-spmc/#hw-md-opt)

### 2.3 因子开发 {#factor-dev}

[将研究侧的因子落地为 C++ 生产实现，按逐 tick 增量计算（on_tick）编写](/zh/interview/cv-factor/#factor-ontick)；[以研究原型或旧系统结果逐值对拍保证研究与生产一致](/zh/interview/cv-factor/#factor-diff)，[无参考结果时以单元测试覆盖边界情况](/zh/interview/cv-factor/#factor-unit)；[上线前完成计时、优化与回归验证](/zh/interview/cv-factor/#factor-release)。

→ 代码：[增量滚动标准差](/zh/interview/cv-factor/#factor-ontick)；完整程序 [因子专页 4.1](/zh/interview/cv-factor/#hw-factor-dev)（增量算法、按 key 对拍、边界单元测试）

### 2.4 因子计算优化 {#factor-opt}

针对逐 tick 调用的 CPU 密集计算路径做日常调优：[多个因子共用的中间量每条行情只算一次](/zh/interview/cv-factor/#opt-shared)；[滚动窗口统计由每次重算改为增量更新](/zh/interview/cv-factor/#opt-rolling)；[用下标计算或哈希替代线性查找](/zh/interview/cv-factor/#opt-index)；[将依赖数据的分支改为无分支写法](/zh/interview/cv-factor/#opt-branchless)；[精简行情数据布局](/zh/interview/cv-factor/#opt-layout)；[拆分串行累加的依赖链](/zh/interview/cv-factor/#opt-dep-chain)；用 [CRTP](/zh/posts/crtp-static-polymorphism/) [替代虚函数调用，消除间接跳转并让编译器能够内联](/zh/interview/cv-factor/#opt-crtp)；[消除热循环里的内存分配与拷贝](/zh/interview/cv-factor/#opt-alloc)。

→ 代码：每一类的改之前 / 改之后都在点进去的那一节；完整程序 [因子专页 4.2](/zh/interview/cv-factor/#hw-factor-opt)（每一类都比对输出）

### 2.5 因子回测框架 {#backtest-flow}

[回测框架按交易日回放历史行情](/zh/interview/backtest-framework/#steps)（[每个交易日约 650 万条、2,000 余只股票](/zh/interview/backtest-framework/#data)）。[为其搭建性能验证流程](/zh/interview/backtest-framework/#backtest-flow)：[每次改动先比对输出、确认结果不变](/zh/interview/backtest-framework/#flow-output)，[再与原版配对计时](/zh/interview/backtest-framework/#flow-paired)。

→ 代码：[框架一天 4 步](/zh/interview/backtest-framework/#steps)、[装载](/zh/interview/backtest-framework/#load)、[回放和写结果](/zh/interview/backtest-framework/#replay)、[框架完整程序](/zh/interview/backtest-framework/#full)；验证流程 [回测专页第 4 节](/zh/interview/backtest-framework/#backtest-flow)

### 2.6 因子回测优化 {#backtest-opt}

[去掉每个交易日重复执行的初始化，运行耗时降低约 22%](/zh/interview/backtest-framework/#opt-init)；[再用 perf 剖析定位到行情装载的开销](/zh/interview/backtest-framework/#opt-load)：[每个交易日为每只股票按固定 6000 条预分配行情数组，一天约 17.5 GB，时间大量耗在缺页与内存分配上](/zh/interview/backtest-framework/#opt-load)；[改为按实际条数分配、行情结构体精简一半以上、bar 时间轴与字符串改为共享，行情记录用 arena 统一分配、跨交易日复用](/zh/interview/backtest-framework/#opt-load)，[耗时在此基础上再降约 44%](/zh/interview/backtest-framework/#opt-load)。

→ 代码：[改之前的定长数组](/zh/interview/backtest-framework/#load)、[改之后的 `Tick`、`StockDay`、`Arena`](/zh/interview/backtest-framework/#data)；完整程序 [回测专页 7.1](/zh/interview/backtest-framework/#hw-backtest-opt)

## 3. 项目 1：C++ 性能自动优化 Agent Skill {#project}

[针对 coding agent 自动优化中“改快但改错”“提速实为测量噪声”“过早停止”三类问题](/zh/interview/cv-projects/#skill-three-failures)，[设计性能优化流程并封装为 Agent skill](/zh/interview/cv-projects/#skill-what)，[由 Agent 按流程自主完成剖析、改写、验证与决策，全程留痕、结果可复现](/zh/interview/cv-projects/#skill-why)。

### 3.1 分诊与 perf 剖析 {#triage}

[先比较墙钟与 CPU 时间等低成本指标](/zh/interview/cv-projects/#triage-two-clocks)，[判断瓶颈属于 CPU 热点、等待与 I/O、锁竞争还是多核扩展，再选剖析手段](/zh/interview/cv-projects/#triage-four-classes)；[CPU 热点用 perf 逐层深入：perf stat 看整体指标，perf report 找热点函数，perf annotate 看热点汇编](/zh/interview/cv-projects/#triage-perf-three)；[跨核争用用 perf c2c 定位到具体缓存行](/zh/interview/cv-projects/#triage-c2c)。

→ 命令和输出：[perf 专题](/zh/posts/low-latency-perf-profiling/)

### 3.2 按信号渐进式披露性能瓶颈修复方法 {#signals}

[Agent 以剖析结果或源码中的信号（如某缓存行跨核争用严重、热点循环为单一累加器串行累加）匹配对应的性能瓶颈](/zh/interview/cv-projects/#signals-index)，[命中后才加载其成因、修复方法与验证方法](/zh/interview/cv-projects/#signals-card)；[按需加载控制上下文占用](/zh/interview/cv-projects/#signals-why)，[新增一类性能瓶颈只需新增一条信号索引](/zh/interview/cv-projects/#signals-add)。

→ 信号表：[性能瓶颈速查](/zh/ref/bottlenecks/)

### 3.3 正确性与性能验证 {#verify}

[每个改动单独验证](/zh/interview/cv-projects/#verify-one-change)：[先比对输出，与原版不一致即否决](/zh/interview/cv-projects/#verify-correctness)；[再测速度，每轮让新旧版本紧挨着各跑一次、先后顺序随机，逐轮对比，避免机器频率、温度等随时间漂移偏向某一方](/zh/interview/cv-projects/#verify-paired)，[多轮结果稳定更快才采纳](/zh/interview/cv-projects/#verify-confirm)。

→ 流程：[回测专页第 4 节](/zh/interview/backtest-framework/#backtest-flow)

### 3.4 缓存性能瓶颈案例 {#case}

[公开 C++ 低延迟案例（期权定价，单条行情访问上百条缓存行，性能瓶颈在访存延迟与长依赖链）](/zh/interview/cv-projects/#case-what)，[Agent 按流程优化](/zh/interview/cv-projects/#case-diagnose)，采用[双核分担](/zh/interview/cv-projects/#case-split)、[软件预取](/zh/interview/cv-projects/#case-prefetch)、[SIMD 向量化](/zh/interview/cv-projects/#case-simd)，[P50 延迟降低约 67%](/zh/interview/cv-projects/#case-honest)。

→ 代码：[缓存案例博客](/zh/posts/low-latency-cache-case-study/)里的 8 段，[1.1 数据布局](/zh/posts/low-latency-cache-case-study/#11-数据怎么摆期权的地址在股票记录里)、[1.2 基线](/zh/posts/low-latency-cache-case-study/#12-基线一个期权一个期权地取数计算)、[2.2 两趟](/zh/posts/low-latency-cache-case-study/#22-两趟先把一批的行都要过来再集中算)、[3.2 预取](/zh/posts/low-latency-cache-case-study/#32-什么时候要第一趟之后第二趟之前)、[4.2 clflushopt](/zh/posts/low-latency-cache-case-study/#42-clflush-与-clflushopt一个串行一个能并行)、[5.1 两个核 40 / 24](/zh/posts/low-latency-cache-case-study/#51-怎么拆主核留-40-个辅核拿-24-个)、[5.2 读回刚写的行](/zh/posts/low-latency-cache-case-study/#52-读回自己刚写的行对面一读副本就没了)、[6.2 SIMD](/zh/posts/low-latency-cache-case-study/#simd-code)；四个版本的完整程序 [第 12 节](/zh/interview/cv-projects/#handwrite)

### 3.5 项目 1 按 STAR 讲 {#project-star}

> **S（背景）**：让 coding agent 自己优化 C++ 代码，最常见三种坏结果：改快了但结果错了；把测量噪声当成提速；拿到一点收益就停（[1.1](/zh/interview/cv-projects/#skill-three-failures)）。
>
> **T（任务）**：设计一套性能优化流程，封装成 Agent skill，让 Agent 按流程自己完成剖析、改写、验证和决策，每一步留痕、结果能复现。再拿一个公开的 C++ 低延迟案例把流程走通。
>
> **A（做法）**：
>
> 1. **分诊**：先比墙钟和 CPU 时间，分成 CPU 热点、等待与 I/O、锁竞争、多核扩展四类，再选工具。CPU 热点用 `perf stat`、`perf report`、`perf annotate` 一层层往下，跨核争用用 `perf c2c` 定位到缓存行（[第 2 节](/zh/interview/cv-projects/#skill-triage)）。
> 2. **按信号加载修法**：每类瓶颈一张卡片，索引里只写“看到什么算命中”。命中了才加载成因、修法和验证方法，省上下文，加一类瓶颈只加一张卡片（[第 3 节](/zh/interview/cv-projects/#skill-signals)）。
> 3. **三道关**：先比输出，不一致直接否决；再配对计时，新旧紧挨着跑、顺序随机，先跑 A/A 看噪声，筛选和确认用不同的数据；停的条件开跑前写好（[第 4 节](/zh/interview/cv-projects/#skill-verify)）。
> 4. **用在案例上**：一条行情重算 64 个期权，要碰 140 条缓存行，判断是卡在等内存加上长依赖链。Agent 按流程依次落地：分批取数让缺失重叠，软件预取下一批，拆给两个核（40 / 24），4 个期权一组用 AVX2 算（[第 5 节](/zh/interview/cv-projects/#skill-case)）。
>
> **R（结果）**：案例的 P50 延迟降低约 67%，在测试机（虚拟机）上测的，只说百分比。每个改动都过了比输出和配对计时，记录完整、能复现。代码是 Agent 改的，流程、判据和否决是我做的。有几条规则是知道答案以后补的，所以它证明的是流程能走通，要证明能推广，还得拿 Agent 没见过的代码盲测（[5.7](/zh/interview/cv-projects/#case-honest)）。

## 4. CV 上没写、讨论过的知识点 {#extra}

简历上没有、准备时聊到的知识点，从 11-20 起记在这里，一条一句话加链接。

| 知识点 | 一句话 | 看哪里 |
|---|---|---|
| MPMC 队列（rte_ring） | 生产者用 CAS 抢 `prod_head_`，各写各的槽，写完按抢到的顺序推进 `prod_tail_`；消费者一边对称，用 `cons_head_`、`cons_tail_`。 | [#18 线程安全队列 2.1](/zh/posts/thread-safe-queue/#21-rte_ring先抢位置再按抢的顺序发布) |
| Disruptor | 生产者可以一个也可以多个（多个时 `fetch_add` 抢号、每一格标圈数，生产者之间不互相等），特点在消费者一侧：每个消费者都读全部（广播），生产者等最慢的那个，不覆盖。 | [#18 线程安全队列 2.2](/zh/posts/thread-safe-queue/#22-disruptor每一格自己标写好了)、[2.3](/zh/posts/thread-safe-queue/#23-背压和等待策略满了等最慢的消费者空了怎么等) |
| CPU 调度（通用） | 只做两个决定：什么时候换下当前线程（看抢占），换谁上（调度策略）。策略在“平均等得最短”（SJF）和“谁都很快轮到”（RR）之间取舍，MLFQ 不预知长短也能近似 SJF。 | [#19 调度 1.1](/zh/posts/scheduling-priority-inversion-kernel-tuning/#how-scheduling)，Linux 的做法见 [1.2](/zh/posts/scheduling-priority-inversion-kernel-tuning/#sched-classes) |
| SIMD 追问：多个线程写相似度矩阵，怎么避免数据竞争 | 按输出切：输入只读，每个线程只写自己的那几行，没有两个线程写同一个元素，也不用锁。 | [#15 SIMD 第 4 节](/zh/posts/simd-vectorization-intrinsics/#parallel-matrix) |
| SIMD 追问：AoS 改成 SoA 为什么可能更快 | 循环只用一个字段时，SoA 只搬这个字段，缓存和带宽不浪费。同一字段连续存放，一条向量 load 就装满，AoS 要洗牌。 | [#15 SIMD 2.3](/zh/posts/simd-vectorization-intrinsics/#layout) |
| SIMD 追问：数据布局和 SIMD 有什么关系 | 一条向量 load 只能读一段连续地址，要同时算的数挨着放，一条指令才装得满。 | [#15 SIMD 2.3](/zh/posts/simd-vectorization-intrinsics/#layout) |
| SIMD 追问：手写 intrinsics 还是靠编译器 | 先靠编译器，看报告和汇编确认它做了。它做不到的热点才手写，缓存案例里手写了 AVX2。 | [#15 SIMD 3.1](/zh/posts/simd-vectorization-intrinsics/#31-什么时候值得)、[缓存案例的 SIMD](/zh/posts/low-latency-cache-case-study/#simd-code) |
| SIMD 追问：编译器什么时候才能自动向量化 | 它能证明“一排同时算”和“一个一个算”结果一样的时候：指针不重叠，没有跨迭代依赖，数据连续，归约允许重排。 | [#15 SIMD 2.2](/zh/posts/simd-vectorization-intrinsics/#22-挡住向量化的几种情况) |
