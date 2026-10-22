---
title: "性能瓶颈：信号、原因、修法"
description: "常见的性能瓶颈各一张卡片：在 perf 里看到什么、为什么慢、怎么改、怎么确认改对了，再链到站内讲这个机制的文章。后两节是写新代码时一开始就避开的坑，以及让程序在不同 CPU 上自动选指令集。"
date: 2026-10-22
lastmod: 2026-10-22
slug: "bottlenecks"
weight: 30
toc: true
math: true
---

<!-- 卡片的源文件在 content/bottlenecks/：中文 <id>.zh.md，英文 <id>.md，文件名就是 id，也是下面的锚点。第 1、2 节由短代码 bottleneck-lookup、bottleneck-cards 从这些文件自动汇总；文章末尾用短代码 bottleneck 按 id 嵌入同一份卡片。加一种瓶颈只需新增这两个文件。 -->

用 [perf](/zh/posts/low-latency-perf-profiling/) 找到热点以后，下一步是认出它是哪种瓶颈、照什么办法改。这一页把常见的瓶颈各写成一张卡片：信号是在 perf 里或源码里看到什么，原因是为什么慢，修法是怎么改，验证是怎么确认改对了，原理链到站内讲这个机制的文章。

这些内容属于 Intel 开源的 performance-patterns（[intel/intel-performance-skills](https://github.com/intel/intel-performance-skills)，提交 3e33aec，MIT 许可）。卡片里的阈值和加速倍数都是原文写的，没有在自己的机器上复测；串行累加除外，[perf 专题 4.6](/zh/posts/low-latency-perf-profiling/#demo-fix) 实测过。

## 1. 从信号找瓶颈：查找表 {#lookup}

perf 给出一个现象，先在这张表里找它对应哪张卡片。左边是在 perf 的输出或源码里看到的东西，右边链到卡片。

{{% bottleneck-lookup "看到什么" "对应的瓶颈" %}}

## 2. 瓶颈卡片：信号、原因、修法、验证 {#cards}

每张卡片的标题是编号加瓶颈名，锚点是它的英文 id。编号按收录先后发，发出后不再改，新收的取下一个号，排在最后；讲到某种瓶颈原理的文章，末尾也嵌着同一张卡片。

{{% bottleneck-cards %}}

## 3. 写新代码：一开始就避开这些坑 {#new-code}

从零写新代码时，照下面的清单写，第 2 节那些瓶颈一开始就避开。每条后面是对应的卡片。

- **指针**：互不重叠的指针参数加 `restrict`（C），只读输入加 `const`（{{% bottleneck-ref "missing-restrict" %}}）。
- **求和这类浮点归约**：热循环里不用单个累加器；在函数说明里写明，求和顺序变了，结果会差一个舍入误差（{{% bottleneck-ref "serial-accumulator" %}}）。
- **SIMD**：
  - 用目标机器支持的最宽寄存器（{{% bottleneck-ref "narrow-vector" %}}）；
  - 用过 ymm 或 zmm0–15 的函数，出口加 `vzeroupper`（{{% bottleneck-ref "missing-vzeroupper" %}}）；
  - 处理长度不是向量宽度整数倍的尾巴；
  - 内联汇编标注 `/* CPUID: <特性> */`，改了标志位要把 `"cc"` 加进 clobber。
- **几个 SIMD 版本**：同一个函数写了几个版本，在运行时按 CPU 选（第 4 节），不要用编译期的 `#ifdef` 写死。
- **多线程**：
  - 每线程的数据按 64 字节对齐垫开（{{% bottleneck-ref "false-sharing" %}}）；
  - 计数器每 CPU 或每线程一份，不用全局原子量（{{% bottleneck-ref "shared-counter" %}}）；
  - 自旋锁先读再 CAS（{{% bottleneck-ref "tas-spinlock" %}}）。
- **罕见路径**：报错和罕见路径的函数标 `[[gnu::cold]]`（{{% bottleneck-ref "cold-path" %}}）。
- **有现成的不重写**：CRC32C 用现成实现（{{% bottleneck-ref "slow-crc32c" %}}）；已知算法照表写（{{% bottleneck-ref "known-algorithms" %}}）；数值排序用 x86-simd-sort（{{% bottleneck-ref "std-sort-numeric" %}}）。

## 4. 让程序在不同 CPU 上自动选指令集 {#isa-dispatch}

同一个函数准备几个版本，比如 SSE2、AVX2、AVX-512 各一个，程序运行时查 CPU 支持哪些指令，挑最快的那个。这样同一个二进制在老机器上能跑，在新机器上也能用上宽向量。有两种做法：

- **让编译器生成（`target_clones`）**：适合编译器能自动向量化的普通循环。在函数上加这个属性，列出要生成的几档（比如 AVX-512、AVX2），编译器生成几个版本，程序加载时按 CPU 挑一个。
  - 最后一档写 `"default"` 兜底；各档写特性名，GCC 在这个属性里不认 `x86-64-v3` 这类级别名；
  - 函数必须非 static，还要加 `noinline`：处处被内联掉，就不会生成挑版本的代码，自动选择悄悄失效；
  - 它不会把手写的 `_mm256_*` 升级成 `_mm512_*`。
- **自己写选择逻辑（`__builtin_cpu_supports`）**：适合手写的 intrinsics 和汇编。拿不准就用这个，逻辑写在明面上，能审。
  - 第一次调用时按 `x86-64-v4`、`v3`、`v2` 从高到低查，把选中的版本存进一个 static 函数指针；之后每次调用只多一次间接跳转。几个线程同时第一次调用也没事，写进去的是同一个值；
  - 每个版本的定义上加 `__attribute__((target("avx2,fma")))` 这类属性：整个文件按较低的 `-march` 编译时，靠它编译器才会给这个函数生成高一档的指令。
- **检查条件要覆盖全部指令集**：少写一个，就会在通过检查却缺这个特性的 CPU 上报非法指令。每次加宽、改写之后都要重新核。
- **别的平台**：
  - Clang 两种做法都一样能用；
  - MSVC 用 `IsProcessorFeaturePresent()` 查特性；
  - ARM/AArch64 用 `getauxval(AT_HWCAP)` 查特性，没有 `target_clones` 的对应做法；
  - 共享库优先自己写选择逻辑，编译器生成的那种在有的链接器上有初始化顺序问题。

站内的例子见 [#15 3.3](/zh/posts/simd-vectorization-intrinsics/#33-对齐指令集检测vzeroupper)：用 `__attribute__((target("avx2,fma")))` 只给一个函数开 AVX2，启动时检测一次 CPU，支持才走这条路。
