---
title: "漏 vzeroupper"
weight: 3
signal: "AVX 函数之后第一条 SSE 指令的周期数极高；AVX 转 SSE 的辅助事件非零"
source: "skills/performance-patterns/patterns/missing-vzeroupper.md"
---

> - **信号**：`other_assists.avx_to_sse` 非零；AVX 函数之后第一条 SSE 指令的周期数极高；冷启动、还没跑过 AVX 代码时没有这个开销。
> - **原因**：写过 ymm 或 zmm0–15，寄存器上半部就是“脏”的。之后第一条老式 SSE 指令要保存、恢复整个寄存器状态，有的微架构要几百周期。`vzeroupper` 约 1 周期就能清掉。
> - **修法**：
>   - intrinsics 代码在每个可能走到 SSE 的出口前加 `_mm256_zeroupper()`：return 前、调 SSE 函数前、回调前；
>   - 内联汇编末尾加 `vzeroupper`，并把 ymm0–15 全部加进 clobber 列表，因为它会清掉所有寄存器的上半部。
> - **不需要的情况**：只用 zmm16–31，或只用 xmm。用 `target("avx2")`、`target_clones` 的函数由编译器自动插入。
> - **验证**：`other_assists.avx_to_sse` 归零。没归零就 `objdump -d` 搜 ymm/zmm，找别的漏点。
> - **原理**：[#15 3.3 对齐、指令集检测、vzeroupper](/zh/posts/simd-vectorization-intrinsics/#33-对齐指令集检测vzeroupper)。
