---
title: "冷路径没标注"
weight: 8
signal: "热函数里有只在罕见分支上调用的函数：报错、日志、断言、一次性初始化"
source: "skills/performance-patterns/patterns/cold-path-annotation.md"
---

> - **信号**：热函数里有只在罕见分支上调用的函数，比如报错和日志函数、断言、一次性初始化，或者写在 `if (ret < 0)`、`switch` 的 `default` 里的调用。
> - **冷的标准**：调用处的分支概率低于约 0.1%。
> - **原因**：冷代码按源码顺序夹在热代码中间，占指令缓存；编译器也没法生成“几乎不跳”的分支布局。
> - **修法**：在被调函数的**定义**上加 `[[gnu::cold]]`（老标准和 C 用 `__attribute__((cold))`），只加在声明上没用。冷函数里再调用的报错函数也要标，不会自动传下去。
> - **受益的是调用方**：冷函数本身不变快，热函数的指令变紧凑。
> - **验证**：
>   - 先确认分支真的冷：Intel 的 `branchprob.py` 用 PMU 事件量每个分支的实际跳转概率；没有负载可跑时，`gccbranchprob.py` 解析 GCC 的编译期静态估计（`-fdump-tree-profile_estimate-lineno`）；
>   - 再用 `-O2 -S` 看冷函数被挪到热函数的 `ret` 之后。
> - **原理**：[#7 3.2 冷热分离](/zh/posts/branch-prediction-branch-optimization/#32-冷热分离把罕见路径挪出去)。
