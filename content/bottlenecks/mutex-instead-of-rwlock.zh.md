---
title: "该用读写锁的地方用了 mutex"
weight: 10
signal: "mutex 护着读多写少的数据（读超过约 75%）；`perf lock stat` 里等待时间远大于持有时间"
source: "skills/performance-patterns/patterns/mutex-to-rwlock.md"
---

> - **信号**：mutex 护着查找、读状态，写只在罕见分支，读占比超过约 75%；内核 mutex 的 `osq_lock` 热；pthread mutex 的内核态占比随核数涨；`perf lock stat` 里等待时间远大于持有时间。
> - **原因**：mutex 让只读的获取也独占缓存行，N 个读者完全串行。
> - **修法**：读路径用读锁，写路径用写锁。读到一半发现要插入时，先放读锁再拿写锁，拿到后必须再查一次，因为中间可能有别的线程已经插入了。
> - **内核里**：`rwlock_t` 是自旋锁，持锁时不能睡；可能睡眠的临界区用 `rw_semaphore`。
> - **不适用**：写 > 50%；临界区只有几条指令；写对时间敏感（有的实现会让读者一直饿着写者，可以设写优先）。
> - **原文附带的实测**（单 socket 32 核，纯读）：
>   - mutex 从 1 线程的 1.64 Mops/s 降到 32 线程的 1.06；
>   - 读写锁 16 线程到 18.2 Mops/s（16.8 倍），32 线程回落到 15.47，因为读者计数本身在抢一个缓存行；
>   - 32 线程时有 1% 写还快 2.7 倍，5% 写快 1.7 倍；
>   - mutex 每秒约 104 万次上下文切换，读写锁 3 秒里一共 225 次；
>   - perf record 自身开销：1 线程 1.1%，32 线程 5.5%。
> - **原理**：拿锁是一次读改写，要独占缓存行，见 [MESI 专题第 5 节](/zh/posts/low-latency-mesi-cache-coherence/#5-一次写的钱花在哪)；抢不到的线程进内核睡，见 [#16 1.1 futex](/zh/posts/spinlock-implementation/#11-futexstdmutex-抢不到锁就去睡)。
