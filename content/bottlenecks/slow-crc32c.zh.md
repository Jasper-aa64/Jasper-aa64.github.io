---
title: "CRC32C 写得慢"
weight: 12
signal: "annotate 上 `crc32b/l/q` 占大头；只有一个 `_mm_crc32_u64` 累加器，或逐字节查表"
source: "skills/performance-patterns/patterns/fast-crc32c.md"
---

> - **信号**：[annotate](/zh/posts/low-latency-perf-profiling/#annotate-scan) 上 `crc32b/l/q` 占大头；只有一个 `_mm_crc32_u64` 累加器；逐字节查表的实现。函数名里带 crc32c 就值得查。
> - **原因**：`_mm_crc32_u64` 延迟约 3 周期，一次只算 8 字节，单累加器上限约 2.5 GB/s/GHz。
> - **修法**：用 corsix fast-crc32 的 fusion 算法。向量路径（VPCLMULQDQ）和标量 crc32 指令走不同的执行端口，两条流同时跑；向量路径再用多个独立累加器。
> - **现成三版**，运行时按 CPU 自动选：
>   - AVX-512 + VPCLMULQDQ（Ice Lake、AMD Zen 4 以后），64–97 GB/s；
>   - SSE4.2 + PCLMULQDQ，15–25 GB/s；
>   - 纯 C，1–3 GB/s。
> - **单核对比**（文档里的表）：Sapphire Rapids 上朴素标量约 23 GB/s，Chromium 的 AVX-512 版 65 GB/s，fusion 97 GB/s。
> - **写新代码**：要用 CRC32C 就直接用现成的，不要自己写。
> - **验证**：空缓冲区、种子 0 结果是 0；`crc32c(0, "123456789", 9) == 0xE3069283`。
> - **原理**：单累加器的上限由指令延迟决定，拆成几条独立的链才能把执行单元用满，见 [#2 3.5 把打断依赖链变成一个公式](/zh/posts/memory-ordering-false-sharing-dependency-chains/#35-把打断依赖链变成一个公式)。
