---
title: "Condition Variable Thundering Herd"
num: 9
signal: "`futex_wake` and `try_to_wake_up` are hot; context switches grow with the threads woken per broadcast"
source: "skills/performance-patterns/patterns/cv-thundering-herd.md"
---

> - **Signal**: `futex_wake` and `try_to_wake_up` are hot; the context-switch rate grows with the number of threads each broadcast wakes; the CPU is busy but [IPC](/posts/low-latency-perf-profiling/#stat-ratios) collapses; `perf trace -e futex` shows lots of `FUTEX_WAKE val=INT_MAX`.
> - **How it differs from lock contention**: wait times in `perf lock stat` are normal; the hot symbols are on the wake-up path, not `native_queued_spin_lock_slowpath`.
> - **Cause**: `notify_all` wakes N threads, only one of which gets the mutex; the rest make a wasted futex round trip (wake, get scheduled, fail to lock, sleep again). With 160 threads one round is about $N \times 5\ \mu\text{s} \approx 800\ \mu\text{s}$; with 160 cores and only 40 jobs, about 75% of the wake-ups are wasted.
> - **Fix, chosen by the wake-up structure**:
>   - the dispatching thread knows how many jobs there are: wake only $\min(\text{threads}, \text{jobs})$ and stop once the jobs are taken;
>   - everyone must be woken: tree wake-up, first wake $K \approx \sqrt{N}$ helpers who wake the rest in parallel, cutting the time from $O(N)$ to about $O(\sqrt{N})$;
>   - only one can work at a time: relay with `notify_one`, notifying after releasing the mutex;
>   - the condition is just "how many units are left": switch to a semaphore and skip the lock fight after each wake-up.
> - **Not for**: barrier synchronization where every thread must proceed; use `std::barrier` or `std::latch`.
> - **Verify**: stress tests confirm no lost wake-ups and no thread asleep forever; futex WAKE counts and context switches drop. Cases cited in the documentation: precise wake-up 49–84% faster (OpenCV), tree wake-up 3 times faster (RocksDB).
> - **Mechanism**: what one sleep and wake-up of a thread costs is in [#16 1.1 Futex](/posts/spinlock-implementation/#11-futex-where-stdmutex-goes-when-the-lock-is-taken).
