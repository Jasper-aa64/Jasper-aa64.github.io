---
title: "共享统计计数器"
weight: 7
signal: "热路径上有 `lock add/inc/xadd`、没有重试循环；c2c 上同一偏移被很多 CPU 写"
source: "skills/performance-patterns/patterns/per-cpu-stats.md"
---

> - **信号**：热路径上有 `lock add/inc/xadd`，没有 cmpxchg 重试循环；[c2c](/zh/posts/low-latency-perf-profiling/#c2c) 显示同一偏移被很多 CPU 写（真共享）；1 核不显眼，多核才冒出来。
> - **原因**：每次原子加都要独占缓存行，这一行在核之间来回传，每次接近内存延迟（约 100–300 ns）。改用 relaxed 内存序也没用，硬件照样要独占。
> - **修法按优先级三选一**：
>   - 自增在一个函数的循环里、热点不超过 2 处：本地变量攒一批，到批量或函数退出时用 relaxed 原子加一次。纯计算循环直接在末尾加一次。
>   - 自增散在多处：按 CPU 号分桶。64 字节对齐的统计结构体数组，下标用 `sched_getcpu() & 63`；所有计数器放进同一个结构体，只调一次 `sched_getcpu`；读的时候把各桶加起来。
>   - 共享库不方便持有全局数组：用 `__thread` 线程局部变量，线程退出或定期刷到全局。
> - **已经分桶了还在抢**：查是不是刷新太频繁，比如每个请求刷一次，拉长间隔。
> - **验证**：总数在任意时刻只是近似值，要确认业务能接受；`lock` 指令从热路径消失；c2c 上该行 HITM 下降。
> - **原理**：一次写的价钱从哪来，见 [MESI 专题第 5 节](/zh/posts/low-latency-mesi-cache-coherence/#5-一次写的钱花在哪)；计数器按线程分片、事后合并，见 [MESI 专题第 6 节](/zh/posts/low-latency-mesi-cache-coherence/#6-三个旧结论同一台机器)；两个核都写的那个计数器，见 [#4 1.2](/zh/posts/lock-free-queue-logger-micro-batching/#12-相减别计数那个让两个核打起来的计数器)。
