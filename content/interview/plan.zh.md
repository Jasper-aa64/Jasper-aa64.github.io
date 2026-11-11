---
title: "IV：本周计划：C++ 架构方向，11-11 到 11-16"
date: 2026-11-11
lastmod: 2026-11-11
slug: "plan"
description: "这一周要过的东西：每天的手撕、知识页、口述，每一项都链到本站对应的页面；下面是手撕清单和设计题清单。"
weight: -1
toc: true
---

这一页是这一周的清单。每天三块：手撕、知识、口述，每一项都给本站的链接，做完一项就打勾。

> **方针：每天三块，先手撕，再知识，最后口述**
>
> - **手撕限时 15–20 分钟**：开写前先用 30 秒说设计；超时就看参考，第二天从空白再写一遍。写完打印 `bad = 0` 才算对。
> - **知识页每页 8–10 分钟**：看完关掉页面，出声说 1 分钟：是什么、底下怎么实现、代价是什么。说不下去的地方再翻回去。
> - **口述要说出声**：录一遍听，超时就删。
> - **时间不够时**：先保手撕，再保口述，知识页可以挪到第二天。

## 1. 今天：11-11 周三 {#wed}

**手撕**（编号是学习仓库 `算法/手撕/` 里的骨架）：

- ⬜ `09` 时间窗口 VWAP 和平均每笔成交量，从空白写。讲法见[因子计算 3.4](https://jasper-aa64.github.io/zh/ref/factor-computation/#vwap)。
- ⬜ `10` 两个队列实现栈、两个栈实现队列，从空白写。
- ⬜ `02` 滚动最大值（单调队列），重写。
- ⬜ LC 739 每日温度（单调栈）。

**知识：C++ 语言 8 页 + 内存 3 页**，按这个顺序：

| | 页 | 先看它的理由 |
|---|---|---|
| ⬜ | [智能指针](https://jasper-aa64.github.io/zh/ref/smart-pointers/) | 周六手撕简版 `shared_ptr` |
| ⬜ | [左值、右值和移动语义](https://jasper-aa64.github.io/zh/ref/move-semantics/) | 周六手撕 String 类要写移动构造 |
| ⬜ | [构造、拷贝、析构和 RAII](https://jasper-aa64.github.io/zh/ref/special-members-raii/) | 和移动语义连着看 |
| ⬜ | [函数调用栈帧](https://jasper-aa64.github.io/zh/ref/stack-frame/) | 栈和堆各放什么、为什么栈快 |
| ⬜ | [new 一次走到哪](https://jasper-aa64.github.io/zh/ref/new-malloc-page-fault/) | 热路径上为什么不分配内存 |
| ⬜ | [虚函数](https://jasper-aa64.github.io/zh/ref/virtual-functions/) | 和 [CRTP 静态多态](https://jasper-aa64.github.io/zh/posts/crtp-static-polymorphism/)对比着讲 |
| ⬜ | [对象布局](https://jasper-aa64.github.io/zh/ref/object-layout/) | vptr 放在哪、填充怎么算 |
| ⬜ | [lambda 和 std::function](https://jasper-aa64.github.io/zh/ref/lambda-function/) | 线程池的 `submit` 用到类型擦除 |
| ⬜ | [模板](https://jasper-aa64.github.io/zh/ref/templates/) | |
| ⬜ | [const、constexpr、consteval、constinit](https://jasper-aa64.github.io/zh/ref/const-constexpr/) | 周六的 C++17/20 接着它 |
| ⬜ | [四种 cast](https://jasper-aa64.github.io/zh/ref/cpp-casts/) | 最短，放最后 |

**口述**：

- ⬜ 讲一个因子，对着[因子计算第 1 节](https://jasper-aa64.github.io/zh/ref/factor-computation/#factors)的代码核一遍，说到 90 秒以内，录一遍。
- ⬜ 自我介绍。

## 2. 11-12 周四：并发、进程和文件 {#thu}

**手撕**：

- ⬜ `11` 线程池：任务队列、条件变量、退出时等任务做完。
- ⬜ `12` 阻塞队列：一把互斥锁加两个条件变量。
- ⬜ `07` SPSC 环形队列，重写。

**知识**：

- ⬜ [线程同步](https://jasper-aa64.github.io/zh/ref/thread-sync/)
- ⬜ [线程池和 future](https://jasper-aa64.github.io/zh/ref/thread-pool-future/)
- ⬜ [用户态和内核态](https://jasper-aa64.github.io/zh/ref/user-kernel-mode/)
- ⬜ [进程和线程](https://jasper-aa64.github.io/zh/ref/process-thread-fork/)
- ⬜ [进程间通信](https://jasper-aa64.github.io/zh/ref/ipc/)
- ⬜ [文件 IO](https://jasper-aa64.github.io/zh/ref/file-io/)
- ⬜ 博客 [#2 内存序与缓存行](https://jasper-aa64.github.io/zh/posts/memory-ordering-false-sharing-dependency-chains/)、[#16 自旋锁](https://jasper-aa64.github.io/zh/posts/spinlock-implementation/) 过一遍

**口述**：[C++ 系统五题](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/)的第 1、2、4 道。

- ⬜ [第 1 道：UB、严格别名、释放后使用](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/#ub)
- ⬜ [第 2 道：x86 内存序和 ping-pong](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/#memory-order)
- ⬜ [第 4 道：futex 锁和 TLS 里的 tid](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/#futex)

## 3. 11-13 周五：网络 {#fri}

**手撕**：

- ⬜ `08` LRU，重写。
- ⬜ LC 215 第 K 大（堆）、LC 23 合并 K 个有序链表。
- ⬜ epoll 主循环默写。

**知识**：

- ⬜ [epoll](https://jasper-aa64.github.io/zh/ref/epoll-internals/)
- ⬜ [TCP 三次握手、四次挥手和 TIME_WAIT](https://jasper-aa64.github.io/zh/ref/tcp-states/)
- ⬜ [TCP 怎么做到可靠](https://jasper-aa64.github.io/zh/ref/tcp-reliability/)
- ⬜ [socket 编程](https://jasper-aa64.github.io/zh/ref/socket-programming/)
- ⬜ [HTTP 和 HTTPS](https://jasper-aa64.github.io/zh/ref/http-basics/)
- ⬜ 低延迟网络：为什么关 Nagle、内核旁路是什么、行情为什么用 UDP 组播（周五前补好，链接放这里）

**口述**：TCP 握手和挥手、epoll 的两种触发方式、Reactor，各 1 分钟。

## 4. 11-14 周六：C++17/20 和设计题 {#sat}

**手撕**：

- ⬜ `13` 简版 `shared_ptr`、`unique_ptr`（骨架周六前放好）。
- ⬜ `14` String 类：构造、拷贝、移动、析构（骨架周六前放好）。
- ⬜ LC 207 课程表，然后 `15` DAG 调度器，讲法见[五题第 5 道](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/#dag)。

**知识**：

- ⬜ C++17/20 新特性一页（周六前补好，链接放这里）。
- ⬜ [交易系统架构地图](https://jasper-aa64.github.io/zh/ref/trading-architecture/)：下单、风控那几部分各说 1 分钟。

**口述**：

- ⬜ [第 3 道：无锁哈希表和 epoch 回收](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/#lockfree-map)
- ⬜ [第 5 道：DAG 调度器](https://jasper-aa64.github.io/zh/interview/cpp-systems-five/#dag)
- ⬜ 三道设计题各 2 分钟，见第 7 节。

## 5. 11-15 周日：整场模拟 {#sun}

- ⬜ 60 分钟整场模拟：自我介绍、项目深挖、基础问答、一道 20 分钟限时手撕、反问。
- ⬜ 模拟里卡住的题，当天回填到对应的页。
- ⬜ 为什么选这个方向、反问 3 个问题。

## 6. 11-16 周一上午：只复习，不学新的 {#mon}

- ⬜ 最不稳的 2 道手撕从空白重写。
- ⬜ 自我介绍、讲一个因子、AI 工程化那题各说一遍。
- ⬜ 13:30 试麦克风和共享屏幕。

## 7. 清单：手撕和设计题 {#lists}

**手撕**（`bad = 0` 才打勾）：

| 类别 | 题目 | 编号 |
|---|---|---|
| 流式窗口 | 时间窗口 VWAP 和平均每笔成交量 | `09` |
| 流式窗口 | 滚动均值方差、滚动最大值（单调队列） | `01`、`02` |
| 基础数据结构 | 两个队列实现栈、两个栈实现队列 | `10` |
| 基础数据结构 | 单调栈（LC 739）、堆（LC 215、LC 23）、LRU | `08` |
| 基础算法 | 二分左右边界（LC 34）、滑动窗口（LC 3）、反转链表、二叉树层序、快排、归并 | LeetCode |
| 系统类 | 线程池、阻塞队列、SPSC 环形队列 | `11`、`12`、`07` |
| 系统类 | 简版 `shared_ptr`、`unique_ptr`；String 类 | `13`、`14` |
| 设计类 | DAG 调度器：先拓扑排序，再讲怎么并行 | `15` |

**设计题**（每道按“结论 → 取舍 → 做过的相邻的事”说 2 分钟，答法周六前补好）：

- ⬜ 单机回测怎么改成分布式。
- ⬜ 全链路监控怎么搭，怎么快速定位性能瓶颈。
- ⬜ 实时风控放在链路的哪里。
