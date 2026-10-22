---
title: "伪共享"
weight: 6
signal: "c2c 某行 Tot Hitm > 5%，同一行里不同偏移被不同线程写"
source: "skills/performance-patterns/patterns/false-sharing.md"
---

> - **信号**：[c2c](/zh/posts/low-latency-perf-profiling/#c2c) 某行 Tot Hitm > 5%，同一行里不同偏移被不同线程写；1 核时不显眼，多核才冒出来；以同一 socket 内的 HITM 为主。
> - **原因**：缓存行（通常 64 字节）是一致性的最小单位。A 线程写字段 X，B 线程那份整行也失效，要重新从 L3 或内存读。
> - **修法分三步**：
>   - 先多垫 padding，把打架的字段推到不同的行。这一步只为证明诊断对，先不管省空间；
>   - 用 c2c 复测，该行 HITM 降到 1% 以下、吞吐上来才算对。降不下来说明诊断错了：要么是真共享，要么还有别的字段卷进来；
>   - 再按访问模式重排：每个线程常写的字段各占一行，多线程只读的字段可以共用一行，很少碰的字段填空位。
> - **更彻底的做法**：把线程私有的字段挪进每线程一份的结构体。
> - **验证**：c2c 前后对比；用 `_Static_assert` 守住结构体大小。
> - **原理**：[#2 第 2 节 伪共享](/zh/posts/memory-ordering-false-sharing-dependency-chains/#2-伪共享这里从来就不是正确性问题)；两个核各写自己的变量时，这条行的状态怎么来回变，见 [MESI 专题第 6 节](/zh/posts/low-latency-mesi-cache-coherence/#6-三个旧结论同一台机器)；让对象独占整条行的 `alignas(64)` 见 [#6 1.3](/zh/posts/alignment-layout-cache-dram-geometry/#13-alignas主动把对齐调大)。
