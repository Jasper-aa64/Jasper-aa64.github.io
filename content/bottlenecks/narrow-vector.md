---
title: "Vectors Too Narrow"
weight: 2
signal: "The hot loop is scalar floating point; or xmm on an AVX2 machine, ymm on an AVX-512 machine"
source: "skills/performance-patterns/patterns/simd-upconversion.md"
---

> - **Signal**: the hot loop is scalar floating point; or it uses xmm on a machine with AVX2; or ymm on a machine with AVX-512 (checks 1 and 2 of the [annotate scan](/posts/low-latency-perf-profiling/#annotate-scan)).
> - **Cause**: the vector unit issues one instruction per cycle whatever the register width. Each doubling of width roughly doubles throughput; scalar to zmm is at most 8 times faster.
> - **Rule out three cases first**:
>   - A loop already limited by memory bandwidth gains far less than 2 times from widening. It only counts as compute-bound if IPC is near or above 1 with few misses.
>   - With a serial accumulator, switch to multiple accumulators first ([Serial Accumulator](/ref/bottlenecks/#serial-accumulator)); widening alone does nothing.
>   - The ymm-to-zmm step: many Intel CPUs lower their clock when running zmm, cancelling part or all of the gain. Check the sustained clock with turbostat before and after; if it drops a lot and the workload is not compute-heavy, compare against the AVX2 version.
> - **Fix** (when intrinsics or assembly already exist): a ten-step "zipper" rewrite:
>   - copy the original loop as the narrow fallback;
>   - unroll the original loop once and give the second half another set of registers;
>   - move the second half's instructions one by one directly under their counterparts in the first half;
>   - merge adjacent pairs of integer adds into one, pairs of narrow vector operations into one wide operation, and adjacent multiplies and adds into FMA;
>   - handle loop invariants and accumulators, and finally update the clobber list and the CPUID comment;
>   - if any step cannot be done (an illegal swap, registers that cannot be merged), abandon the whole rewrite.
> - **The tail**: AVX-512 can use a mask register for one masked operation instead of a scalar tail.
> - **No hand-written intrinsics**, the compiler just emitted xmm: use `target_clones` to have the compiler build several versions (see [picking the instruction set at run time](/ref/bottlenecks/#isa-dispatch)).
> - **Verify**:
>   - floating-point results may differ by 1 ULP (unit in the last place; reordering and FMA both change rounding), and bit-exact reference values must be regenerated with the new code;
>   - check signed and unsigned semantics in integer loops;
>   - the CPUID guard covers every newly used instruction set;
>   - wide registers appear in annotate.
> - **Mechanism**: how wide the registers are, and why only 128 bits without an instruction-set flag, is in [#15 Part 1](/posts/simd-vectorization-intrinsics/#1-how-wide-the-registers-are-without-an-instruction-set-flag-only-128-bits); what blocks vectorization is in [#15 2.2](/posts/simd-vectorization-intrinsics/#22-what-blocks-vectorization).
