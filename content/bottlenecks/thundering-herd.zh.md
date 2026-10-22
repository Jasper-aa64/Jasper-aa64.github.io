---
title: "条件变量惊群"
weight: 9
signal: "`futex_wake`、`try_to_wake_up` 热；上下文切换率随每次广播叫醒的线程数涨"
source: "skills/performance-patterns/patterns/cv-thundering-herd.md"
---

> - **信号**：`futex_wake`、`try_to_wake_up` 热；上下文切换率随每次广播叫醒的线程数涨；CPU 很忙但 [IPC](/zh/posts/low-latency-perf-profiling/#stat-ratios) 崩；`perf trace -e futex` 里大量 `FUTEX_WAKE val=INT_MAX`。
> - **和锁竞争的区别**：`perf lock stat` 的等待时间正常；热符号是唤醒路径，不是 `native_queued_spin_lock_slowpath`。
> - **原因**：`notify_all` 叫醒 N 个线程，只有一个能拿到 mutex，其余白跑一趟 futex（唤醒、调度、拿锁失败、再睡）。160 个线程时一轮约 $N \times 5\ \mu\text{s} \approx 800\ \mu\text{s}$；160 核只有 40 个活时，约 75% 的唤醒是白费的。
> - **修法按唤醒结构选**：
>   - 派活的线程知道有几个活：只叫醒 $\min(\text{线程数}, \text{活数})$ 个，活被领完就停；
>   - 必须叫醒全部：树形唤醒，先叫醒 $K \approx \sqrt{N}$ 个帮手，大家并行往下叫，耗时从 $O(N)$ 降到约 $O(\sqrt{N})$；
>   - 一次只有一个能干活：`notify_one` 接力，在释放 mutex 之后再通知；
>   - 条件只是“还剩几个单位”：换成信号量，省掉每次唤醒后的抢锁。
> - **不适用**：所有线程都要往下走的屏障同步，改用 `std::barrier`、`std::latch`。
> - **验证**：压测确认不丢唤醒、没有线程永远睡着；futex WAKE 次数和上下文切换下降。文档引的案例：精确唤醒快 49–84%（OpenCV），树形唤醒快 3 倍（RocksDB）。
> - **原理**：线程睡下、再被叫醒一次要付什么，见 [#16 1.1 futex](/zh/posts/spinlock-implementation/#11-futexstdmutex-抢不到锁就去睡)。
