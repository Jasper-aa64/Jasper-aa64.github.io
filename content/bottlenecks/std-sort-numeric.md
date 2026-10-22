---
title: "std::sort on Numeric Arrays"
num: 13
signal: "`std::sort`, `nth_element`, `partial_sort` or `qsort` on arrays of float, double or integers"
source: "skills/performance-patterns/patterns/simd-sort.md"
---

> - **Applies to**: `std::sort`, `nth_element`, `partial_sort`, `qsort` with a numeric comparison, and hand-written quicksort on arrays of float, double, int32/uint32/int64/uint64. Not strings, pointers, or objects without a numeric key.
> - **Cause**: introsort compares one element at a time, every comparison is a branch, and there is no data parallelism.
> - **Fix**: switch to x86-simd-sort (used by NumPy, PyTorch, OpenJDK). The quicksort partition is vectorized with AVX-512 compress instructions, and small subarrays use SIMD sorting networks. 3–8 times faster with AVX-512, 2–4 times with AVX2, picked at run time.
> - **Traps**:
>   - it is not stable, and there is no replacement for `stable_sort`;
>   - float arrays that may contain NaN must pass `hasnan=true`, otherwise the behavior is undefined;
>   - `qsort` turns every NaN into a quiet NaN; `argsort` silently falls back to `std::sort` on NaN, with no speedup;
>   - it needs C++17.
> - **Verify**: sort a copy with `std::sort` and compare element by element.
