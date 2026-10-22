---
title: "串行累加"
num: 1
signal: "annotate 上一条 `vaddss`/`vfmadd`（或它的下一条）占大头；IPC ≪ 1，缓存缺失却很低"
source: "skills/performance-patterns/patterns/parallel-accumulator.md"
---

> - **信号**：[annotate](/zh/posts/low-latency-perf-profiling/#annotate-scan) 上一条 `vaddss`/`vfmadd` 占大头（样本常记在它的下一条指令上，要往前看一条）；[IPC](/zh/posts/low-latency-perf-profiling/#stat-ratios) ≪ 1，缓存缺失却很低，这个组合是关键。
> - **原因**：每次 `+=` 都要等上一次的结果，速度卡在浮点加的延迟（4–5 周期）上，而不是吞吐（约 0.5 周期），差 8–10 倍。
> - **修法**：拆成多个独立累加器。纯 C 拆 4 个约快 4 倍；SSE2 向量累加快 4–8 倍；AVX2 向量加 4 个累加器快 8–15 倍。
> - **累加器个数**：$\text{延迟} \div \text{吞吐} = 4 \div 0.5 = 8$。一般 4 个够，紧循环用 8 个。
> - **尾巴**：不满一组的尾巴也要用多累加器，否则小输入又退回串行。
> - **前提**：运算满足结合律（加、乘、min、max）。结果会差一个舍入误差；要求逐位一致就不能用。
> - **验证**：输出在舍入误差内一致，IPC 至少翻倍。
> - **原理**：[#9 循环优化 3.2](/zh/posts/loop-optimization/#32-浮点求和编译器不敢换顺序要多个累加器)；累加器个数的公式见 [#2 3.5](/zh/posts/memory-ordering-false-sharing-dependency-chains/#35-把打断依赖链变成一个公式)；编译器替不替你拆，见[内存延迟与带宽 1.5.1](/zh/posts/low-latency-memory-latency-bandwidth/#151-向量化simd与多个累加器谁来做)；实测见 [perf 专题 4.6](/zh/posts/low-latency-perf-profiling/#demo-fix)。
