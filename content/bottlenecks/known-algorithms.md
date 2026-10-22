---
title: "Known Algorithms"
num: 14
signal: "Functions named cosine, hamming, jaccard and the like"
source: "skills/performance-patterns/references/known-algorithms.md"
---

> - **Signal**: a function named cosine, hamming, jaccard or similar triggers it, with a vectorized recipe per instruction set.
> - **Cosine similarity**: compute $a \cdot b$, $a \cdot a$ and $b \cdot b$ in one pass, each with 4 independent accumulators (12 ymm in total with AVX2). With normalized inputs it reduces to a dot product; a denominator below $\varepsilon$ returns 0.
> - **Hamming distance**: XOR, then count the ones. The POPCNT baseline takes 8-byte chunks with 4 accumulators, about 4–6 GB/s; AVX2 uses Harley-Seal bit-sliced counting, about 20–30 GB/s; AVX-512 VPOPCNTDQ about 40–60 GB/s. Don't hand-write popcount.
> - **Jaccard distance**: compute the popcounts of AND and OR in the same pass. When both sides' popcounts are known, $|A \cup B| = |A| + |B| - |A \cap B|$ removes the OR and halves the work. Two all-zero vectors return similarity 1 by convention.
> - **In common**: all three must handle the tail that doesn't fill a group; the final division and square root are negligible and need no tuning.
> - **Mechanism**: how to write a dot product with vector instructions and accumulators is in [#15 3.2 An AVX2 + FMA Dot Product](/posts/simd-vectorization-intrinsics/#32-example-an-avx2--fma-dot-product).
