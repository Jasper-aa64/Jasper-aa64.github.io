---
title: "数值数组用 std::sort"
weight: 13
signal: "对 float、double 或整数数组调 `std::sort`、`nth_element`、`partial_sort`、`qsort`"
source: "skills/performance-patterns/patterns/simd-sort.md"
---

> - **适用**：float、double、int32/uint32/int64/uint64 数组上的 `std::sort`、`nth_element`、`partial_sort`、数值比较的 `qsort`、手写快排。字符串、指针、没有数值键的对象不适用。
> - **原因**：introsort 一次比较一个元素，每次比较都是一个分支，没有数据并行。
> - **修法**：换 x86-simd-sort（NumPy、PyTorch、OpenJDK 在用）。快排的划分用 AVX-512 压缩指令向量化，小子数组用 SIMD 排序网络。AVX-512 上快 3–8 倍，AVX2 上 2–4 倍，运行时自动选。
> - **坑**：
>   - 不稳定，`stable_sort` 没有替代；
>   - 浮点数组可能有 NaN 时必须传 `hasnan=true`，否则行为未定义；
>   - `qsort` 会把所有 NaN 统一成 quiet NaN；`argsort` 遇到 NaN 静默退回 `std::sort`，没有加速；
>   - 要求 C++17。
> - **验证**：拷一份用 `std::sort` 排，逐个比对。
