---
title: "False Sharing"
num: 6
signal: "A line above 5% Tot Hitm in c2c, with different offsets written by different threads"
source: "skills/performance-patterns/patterns/false-sharing.md"
---

> - **Signal**: a line above 5% Tot Hitm in [c2c](/posts/low-latency-perf-profiling/#c2c), with different offsets in it written by different threads; inconspicuous on 1 core, it shows up only with several; mostly HITMs within one socket.
> - **Cause**: the cache line (usually 64 bytes) is the smallest unit of coherence. When thread A writes field X, thread B's copy of the whole line is invalidated and has to be read again from L3 or memory.
> - **Fix in three steps**:
>   - first pad generously to push the fighting fields onto different lines. This step only proves the diagnosis; don't worry about space yet;
>   - re-measure with c2c: it only counts if that line's HITM drops below 1% and throughput comes up. If it doesn't drop, the diagnosis was wrong: either it is true sharing, or other fields are involved;
>   - then reorder by access pattern: fields each thread writes often get a line each, fields many threads only read can share a line, rarely touched fields fill the gaps.
> - **The thorough fix**: move thread-private fields into a per-thread struct.
> - **Verify**: compare c2c before and after; guard the struct size with `_Static_assert`.
> - **Mechanism**: [#2 Part 2, False Sharing](/posts/memory-ordering-false-sharing-dependency-chains/#2-false-sharing-when-correctness-was-never-the-question); how the line's state goes back and forth when two cores each write their own variable is in [the MESI special, Part 6](/posts/low-latency-mesi-cache-coherence/#6-three-old-results-one-machine); `alignas(64)`, which gives an object whole lines of its own, is in [#6 1.3](/posts/alignment-layout-cache-dram-geometry/#13-alignas-asking-for-more-alignment).
