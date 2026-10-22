---
title: "Shared Statistics Counter"
weight: 7
signal: "`lock add/inc/xadd` on the hot path with no retry loop; the same offset written by many CPUs in c2c"
source: "skills/performance-patterns/patterns/per-cpu-stats.md"
---

> - **Signal**: `lock add/inc/xadd` on the hot path, with no cmpxchg retry loop; [c2c](/posts/low-latency-perf-profiling/#c2c) shows the same offset written by many CPUs (true sharing); inconspicuous on 1 core, it shows up only with several.
> - **Cause**: every atomic add must own the cache line exclusively, so the line travels between cores, each time at close to memory latency (about 100–300 ns). Relaxed memory order does not help; the hardware still needs exclusive ownership.
> - **Fix, one of three in order of preference**:
>   - increments inside one function's loop, at no more than 2 hot spots: accumulate in a local variable and add it once with a relaxed atomic per batch or at function exit. A pure compute loop adds once at the end.
>   - increments spread over many places: bucket by CPU number. Use an array of 64-byte-aligned stats structs indexed by `sched_getcpu() & 63`; put all counters in the same struct so `sched_getcpu` is called once; sum the buckets when reading.
>   - a shared library that cannot easily own a global array: use `__thread` thread-local variables, flushed to the global on thread exit or periodically.
> - **Still contended after bucketing**: check whether flushes are too frequent, for example once per request, and lengthen the interval.
> - **Verify**: the total is only approximate at any moment, so confirm the business can live with that; `lock` instructions disappear from the hot path; HITM on that line drops in c2c.
> - **Mechanism**: where the cost of a write comes from is in [the MESI special, Part 5](/posts/low-latency-mesi-cache-coherence/#5-where-a-writes-cost-comes-from); sharding a counter per thread and merging afterwards is in [the MESI special, Part 6](/posts/low-latency-mesi-cache-coherence/#6-three-old-results-one-machine); the counter both cores write is in [#4 1.2](/posts/lock-free-queue-logger-micro-batching/#12-subtract-dont-count-the-counter-that-made-two-cores-fight).
