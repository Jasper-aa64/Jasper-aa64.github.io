---
title: "Test-and-Set Spinlock"
num: 5
signal: "`lock cmpxchg` piles up in a tight loop in annotate; throughput drops as threads are added"
source: "skills/performance-patterns/patterns/ttas.md"
---

> - **Signal**: `lock cmpxchg` piles up in a tight loop in [annotate](/posts/low-latency-perf-profiling/#annotate-scan); spin_lock, cas and similar functions stand out in [perf report](/posts/low-latency-perf-profiling/#report-lines); throughput falls as threads are added, not merely stops growing.
> - **Cause**: a TAS (test-and-set) lock does a read-modify-write on every attempt. Even a failed `cmpxchg` must own the cache line exclusively, so every waiter and the holder fight over one line, and under contention the bus traffic is $O(N^2)$. Data sharing the lock's line gets dragged along.
> - **Fix**: read normally first and CAS only once the lock looks free (TTAS, test-and-test-and-set). While waiting, the line stays in the shared state and the traffic drops to $O(N)$.
> - **Production form**: try one CAS first and enter the read loop only if it fails, so the uncontended case pays no extra read.
> - **Lock and data on one line**: pad the lock onto a line of its own.
> - **Verify**: the sample density on `lock cmpxchg` drops; the throughput curve over 1/2/4/8 threads no longer falls; HITM on the lock's line drops in [c2c](/posts/low-latency-perf-profiling/#c2c).
> - **Mechanism**: every attempt by a waiting core takes the line, see [#16 1.4](/posts/spinlock-implementation/#14-rmws-steal-the-line-every-attempt-takes-it-exclusive); reading before grabbing is [#16 1.5 TTAS](/posts/spinlock-implementation/#15-ttas-read-first-grab-only-when-it-looks-free); the simplest CAS loop is [#16 1.3](/posts/spinlock-implementation/#13-the-simplest-spinlock-one-atomic-and-a-cas-loop).
