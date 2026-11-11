---
title: "IV：本周计划：C++ 架构方向，11-11 到 11-16"
date: 2026-11-11
lastmod: 2026-11-11
slug: "plan"
description: "这一周要补的东西，按缺口大小排：JD 写明要的、同类岗位实际考过的、自己最弱的先补；每一项看完马上写或马上说。"
weight: -1
toc: true
---

这一页是这一周的清单。排法和找性能热点一样：先补最大的缺口，小缺口留到最后，时间不够就砍掉。

> **怎么排、怎么补**
>
> - **缺口大小 = JD 写没写 × 同类岗位考没考过 × 自己有多弱**：三样都占的排最前；只在通用题单里出现、没有出处的，不进手撕，最多口述。
> - **看完马上用**：要写的，看完对应那一节就从空白写，写完打印 `bad = 0`；要说的，看完就关掉页面出声说。不先把知识点全看完再回头用。
> - **手撕限时 15–20 分钟**：开写前先用 30 秒说设计；超时就看参考，第二天从空白再写一遍。
> - **做完一项打勾**：没出处的项发现了就删。

## 1. 缺口排序：从大到小 {#gaps}

| # | 缺口 | 为什么排这里 | 看什么 → 马上做什么 | 哪天 | 状态 |
|---|---|---|---|---|---|
| 1 | 无锁哈希表和 epoch 回收 | AG 面经里实际考过；JD 写了多线程并发 | [系统题目第 3 节](https://jasper-aa64.github.io/zh/interview/cpp-systems/#lockfree-map) → 从空白写 `18`；再说 [3.4 分片加锁和后台回收](https://jasper-aa64.github.io/zh/interview/cpp-systems/#shard-lock) | 周三 | ⬜ |
| 2 | 低延迟网络和加密交易所接入 | JD 写了网络编程；AG 做加密货币高频，行情和下单走 WebSocket 加 TLS；之前没准备 | 网络补充页（周四上午前放好）→ 默写 epoll 主循环；说清关 Nagle、内核旁路、UDP 组播、WebSocket/TLS/JSON 各自的延迟在哪 | 周四 | ⬜ |
| 3 | 三道设计题：分布式回测、全链路监控、实时风控和资金管理 | JD 职责前三条原文；之前没准备 | 答法（周四晚前放好）→ 每道按“结论 → 取舍 → 做过的相邻的事”说 2 分钟 | 周五 | ⬜ |
| 4 | 线程池、阻塞队列 | JD 写了多线程并发；同一篇面经问到 work stealing 线程池 | [线程池和 future](https://jasper-aa64.github.io/zh/ref/thread-pool-future/) → 写 `11`；[线程安全队列 #18](https://jasper-aa64.github.io/zh/posts/thread-safe-queue/) → 写 `12` | 周四 | ⬜ |
| 5 | 对象池、无锁侵入式栈 | 同类岗位面经里实际考过 | 骨架带讲解（周五前放好）→ 写 `14` 对象池、`17` 无锁栈（ABA） | 周五、周六 | ⬜ |
| 6 | C++17/20 | JD 原文“熟悉 C++17/20”；没系统看过 | 一页（周五前放好）→ 每个特性说一句解决什么问题 | 周六 | ⬜ |
| 7 | 性能定位和 benchmark | JD 写了“快速定位性能瓶颈”；同类面经追问过怎么做可信的 benchmark | [perf 专题](https://jasper-aa64.github.io/zh/posts/low-latency-perf-profiling/)、[TSC 延迟测量 #20](https://jasper-aa64.github.io/zh/posts/tsc-latency-measurement/) → 说一遍 SPSC 下移动均值那道优化题：换什么、怎么证明变快了 | 周六 | ⬜ |
| 8 | 基础算法写得慢 | JD 写了数据结构与算法；上一场限时题超时 | 每天晚上 1–2 道：`09`、`10`、`02`、LC 739、LC 215、LC 23 | 每天晚上 | ⬜ |
| 9 | C++ 语言和内存基础 | 页面都写过，属于小缺口 | 每页 1 分钟口述，说不顺的才翻页，见第 3 节 | 碎片时间、周一上午 | ⬜ |

**不进手撕的**：String 类、简版智能指针。没有找到这一类岗位考过的出处，只口述：五个特殊成员各做什么、移动构造为什么要 `noexcept`、`shared_ptr` 的控制块和线程安全。

## 2. 每天 {#days}

| 日期 | 先做（大缺口） | 晚上 | 口述 |
|---|---|---|---|
| **11-11 周三** | #1 无锁哈希表：看第 3 节 → 写 `18` | `09`、`10` | 讲一个因子，90 秒以内；自我介绍 |
| **11-12 周四** | #2 网络：看补充页 → 默写 epoll 主循环；#4 写 `11`、`12` | `02`、LC 739 | 网络那几个点各 1 分钟 |
| **11-13 周五** | #3 三道设计题各说 2 分钟；#5 写 `14` 对象池 | LC 215、LC 23 | 系统题目第 1、2 道 |
| **11-14 周六** | #5 写 `17` 无锁栈；#6 C++17/20；#7 benchmark 那道优化题 | 最不稳的一道重写 | 系统题目第 4、5 道 |
| **11-15 周日** | 60 分钟整场模拟：自我介绍、项目、基础问答、20 分钟限时手撕、反问 | 卡住的题回填 | 为什么选这个方向，反问 3 个 |
| **11-16 周一上午** | 最不稳的 2 道从空白重写；第 3 节说不顺的页 | — | 13:30 试麦克风和共享屏幕；14:00 开始 |

## 3. 小缺口：C++ 基础页，每页 1 分钟口述 {#basics}

说得顺就跳过，说不顺才翻页。

- ✅ [智能指针](https://jasper-aa64.github.io/zh/ref/smart-pointers/)
- ⬜ [左值、右值和移动语义](https://jasper-aa64.github.io/zh/ref/move-semantics/)
- ⬜ [构造、拷贝、析构和 RAII](https://jasper-aa64.github.io/zh/ref/special-members-raii/)
- ⬜ [函数调用栈帧](https://jasper-aa64.github.io/zh/ref/stack-frame/)
- ⬜ [new 一次走到哪](https://jasper-aa64.github.io/zh/ref/new-malloc-page-fault/)
- ⬜ [虚函数](https://jasper-aa64.github.io/zh/ref/virtual-functions/)，和 [CRTP 静态多态](https://jasper-aa64.github.io/zh/posts/crtp-static-polymorphism/)对比着说
- ⬜ [对象布局](https://jasper-aa64.github.io/zh/ref/object-layout/)
- ⬜ [lambda 和 std::function](https://jasper-aa64.github.io/zh/ref/lambda-function/)
- ⬜ [模板](https://jasper-aa64.github.io/zh/ref/templates/)
- ⬜ [const、constexpr、consteval、constinit](https://jasper-aa64.github.io/zh/ref/const-constexpr/)
- ⬜ [四种 cast](https://jasper-aa64.github.io/zh/ref/cpp-casts/)
- ⬜ [未定义行为：UB、严格别名、释放后使用](https://jasper-aa64.github.io/zh/ref/undefined-behavior/)
- ⬜ [ASan 和 TSan](https://jasper-aa64.github.io/zh/ref/sanitizers/)
- ⬜ 并发和系统：[线程同步](https://jasper-aa64.github.io/zh/ref/thread-sync/)、[用户态和内核态](https://jasper-aa64.github.io/zh/ref/user-kernel-mode/)、[进程和线程](https://jasper-aa64.github.io/zh/ref/process-thread-fork/)、[进程间通信](https://jasper-aa64.github.io/zh/ref/ipc/)、[文件 IO](https://jasper-aa64.github.io/zh/ref/file-io/)
- ⬜ 网络基础：[epoll](https://jasper-aa64.github.io/zh/ref/epoll-internals/)、[TCP 状态](https://jasper-aa64.github.io/zh/ref/tcp-states/)、[TCP 可靠性](https://jasper-aa64.github.io/zh/ref/tcp-reliability/)、[socket 编程](https://jasper-aa64.github.io/zh/ref/socket-programming/)
