---
title: "已知算法"
num: 14
signal: "函数名是 cosine、hamming、jaccard 一类"
source: "skills/performance-patterns/references/known-algorithms.md"
---

> - **信号**：函数名是 cosine、hamming、jaccard 一类就触发，按指令集给出向量化做法。
> - **余弦相似度**：一次遍历同时算 $a \cdot b$、$a \cdot a$、$b \cdot b$ 三路，每路 4 个独立累加器（AVX2 下共 12 个 ymm）。输入已归一化就退化成点积；分母小于 $\varepsilon$ 返回 0。
> - **Hamming 距离**：XOR 后数 1。POPCNT 基线 8 字节一块、4 个累加器，约 4–6 GB/s；AVX2 用 Harley-Seal 位切片计数，约 20–30 GB/s；AVX-512 VPOPCNTDQ 约 40–60 GB/s。不要手写 popcount。
> - **Jaccard 距离**：同一遍里同时算 AND 和 OR 的 popcount。两边各自的 popcount 已知时，用 $|A \cup B| = |A| + |B| - |A \cap B|$ 省掉 OR，工作量减半。两个全零向量按约定返回相似度 1。
> - **共同点**：三种都要处理不满一组的尾巴；结尾的除法和开方占比可以忽略，不用优化。
> - **原理**：点积怎么用向量指令和累加器写，见 [#15 3.2 AVX2 + FMA 点积](/zh/posts/simd-vectorization-intrinsics/#32-例子avx2--fma-点积)。
