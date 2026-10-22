---
title: "Mutex Where a Reader-Writer Lock Belongs"
weight: 10
signal: "A mutex guards mostly-read data (reads above about 75%); in `perf lock stat` the wait time far exceeds the hold time"
source: "skills/performance-patterns/patterns/mutex-to-rwlock.md"
---

> - **Signal**: a mutex guards lookups and state reads, writes happen only on rare branches, and reads are above about 75%; the kernel mutex's `osq_lock` is hot; the kernel-time share of a pthread mutex grows with the core count; in `perf lock stat` the wait time far exceeds the hold time.
> - **Cause**: a mutex makes even a read-only acquisition own the cache line exclusively, so N readers are fully serialized.
> - **Fix**: take a read lock on read paths and a write lock on write paths. A reader that finds it must insert releases the read lock, takes the write lock, and must look again once it has it, because another thread may have inserted in between.
> - **In the kernel**: `rwlock_t` is a spinlock and must not sleep while held; use `rw_semaphore` for critical sections that may sleep.
> - **Not for**: writes > 50%; critical sections of only a few instructions; time-sensitive writes (some implementations let readers starve writers forever; writer preference can be set).
> - **Measurements included in the original** (one socket, 32 cores, pure reads):
>   - the mutex falls from 1.64 Mops/s with 1 thread to 1.06 with 32;
>   - the reader-writer lock reaches 18.2 Mops/s with 16 threads (16.8 times) and falls back to 15.47 with 32, because the reader count itself fights over one cache line;
>   - with 32 threads it is still 2.7 times faster with 1% writes, and 1.7 times faster with 5%;
>   - the mutex makes about 1.04 million context switches per second; the reader-writer lock made 225 in 3 seconds in total;
>   - perf record's own overhead: 1.1% with 1 thread, 5.5% with 32.
> - **Mechanism**: taking a lock is a read-modify-write that must own the cache line, see [the MESI special, Part 5](/posts/low-latency-mesi-cache-coherence/#5-where-a-writes-cost-comes-from); a thread that cannot get it sleeps in the kernel, see [#16 1.1 Futex](/posts/spinlock-implementation/#11-futex-where-stdmutex-goes-when-the-lock-is-taken).
