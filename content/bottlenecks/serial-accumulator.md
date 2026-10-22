---
title: "Serial Accumulator"
num: 1
signal: "One `vaddss`/`vfmadd` (or the instruction after it) dominates annotate; IPC ≪ 1 while cache misses stay low"
source: "skills/performance-patterns/patterns/parallel-accumulator.md"
---

> - **Signal**: one `vaddss`/`vfmadd` dominates [annotate](/posts/low-latency-perf-profiling/#annotate-scan) (samples often land on the instruction after it, so look one back); [IPC](/posts/low-latency-perf-profiling/#stat-ratios) ≪ 1 while cache misses stay low. That combination is the key.
> - **Cause**: every `+=` waits for the previous result, so the speed is set by the latency of a floating-point add (4–5 cycles) rather than its throughput (about 0.5 cycles), a gap of 8–10 times.
> - **Fix**: split into several independent accumulators. Four in plain C is about 4 times faster; SSE2 vector accumulation 4–8 times; AVX2 vectors with 4 accumulators 8–15 times.
> - **How many accumulators**: $\text{latency} \div \text{throughput} = 4 \div 0.5 = 8$. Four is usually enough; tight loops use 8.
> - **The tail**: the leftover elements that don't fill a group need multiple accumulators too, or small inputs fall back to serial.
> - **Precondition**: the operation must be associative (add, multiply, min, max). The result shifts by a rounding error; if it must match bit for bit, this fix is out.
> - **Verify**: the output agrees within rounding error, and IPC at least doubles.
> - **Mechanism**: [#9 Loop Optimization 3.2](/posts/loop-optimization/#32-floating-point-sums-the-compiler-wont-reorder-so-use-several-accumulators); the accumulator-count formula is in [#2 3.5](/posts/memory-ordering-false-sharing-dependency-chains/#35-turning-break-the-dependency-chain-into-a-formula); whether the compiler splits it for you is in [Memory Latency and Bandwidth 1.5.1](/posts/low-latency-memory-latency-bandwidth/#151-vectorization-simd-and-multiple-accumulators-who-does-it); measured in [the perf special, 4.6](/posts/low-latency-perf-profiling/#demo-fix).
