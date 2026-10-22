---
title: "TAS 自旋锁"
num: 5
signal: "annotate 上 `lock cmpxchg` 在紧循环里扎堆；线程越多吞吐越低"
source: "skills/performance-patterns/patterns/ttas.md"
---

> - **信号**：[annotate](/zh/posts/low-latency-perf-profiling/#annotate-scan) 上 `lock cmpxchg` 在紧循环里扎堆；[perf report](/zh/posts/low-latency-perf-profiling/#report-lines) 里 spin_lock、cas 一类函数显眼；线程越多吞吐越低，不只是不涨。
> - **原因**：TAS（test-and-set）锁每次都直接读改写。`cmpxchg` 失败也要独占缓存行，所有等待者和持锁者抢同一行，竞争时总线流量是 $O(N^2)$。和锁放在同一行的数据也跟着被抢。
> - **修法**：先普通读，读到锁空闲再 CAS（TTAS，test-and-test-and-set）。等待时缓存行处于共享态，流量降到 $O(N)$。
> - **生产写法**：先试一次 CAS，失败再进读循环，没有竞争时不多花一次读。
> - **锁和数据同行**：把锁垫到单独一行。
> - **验证**：`lock cmpxchg` 的样本密度下降；1/2/4/8 线程的吞吐曲线不再往下走；[c2c](/zh/posts/low-latency-perf-profiling/#c2c) 上锁所在行的 HITM 下降。
> - **原理**：等的核每试一次都要把行抢过来，见 [#16 1.4](/zh/posts/spinlock-implementation/#14-读改写抢行等的核每试一次都要把行抢过来)；先读后抢见 [#16 1.5 TTAS](/zh/posts/spinlock-implementation/#15-ttas先读看着空了再抢)；最简单的 CAS 循环见 [#16 1.3](/zh/posts/spinlock-implementation/#13-最简单的自旋锁一个原子变量循环-cas)。
