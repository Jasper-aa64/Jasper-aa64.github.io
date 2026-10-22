---
title: "Missing restrict"
num: 4
signal: "An overlap check (pointer subtract, compare, jump) before the loop; the same loop compiled into vector and scalar versions"
source: "skills/performance-patterns/patterns/missing-restrict.md"
---

> - **Applies to**: C only.
> - **Signal**: an overlap check of pointer subtractions, compares and jumps before the loop; the same loop compiled into a vector and a scalar version; or a simple loop with no dependencies and no branches that was not vectorized at all.
> - **Cause**: the compiler cannot assume the output pointer does not overlap the inputs, so it either adds a run-time check (10–20 instructions plus two copies of the loop) or gives up on vectorizing.
> - **Fix**: write read-only inputs as `const float * restrict` and the output as `float * restrict`. C++ has no standard restrict, only GCC/Clang's `__restrict__`.
> - **Trap**: restrict is a promise to the compiler. If a caller really passes overlapping pointers, that is undefined behavior, not just slower code. Parameters meant to be processed in place must not get it.
> - **Verify**: compare `gcc -O2 -S` output before and after; the check is gone. If tests fail after adding it, a caller is passing overlapping pointers: remove restrict and fix the caller.
> - **Mechanism**: [#10 Part 1, __restrict](/posts/pointer-memory-access/#1-__restrict-promising-the-compiler-two-pointers-dont-overlap): why two pointers may point at the same memory is in [1.1](/posts/pointer-memory-access/#11-aliasing-two-pointers-may-point-at-the-same-memory); the compiler checking at run time itself is in [1.2](/posts/pointer-memory-access/#12--o3-the-compiler-checks-at-run-time-itself).
