---
title: "IV：C++ 系统题目：UB、内存序、无锁哈希表、futex 锁、DAG 调度"
date: 2026-11-11
slug: "cpp-systems"
aliases: ["/interview/cpp-systems-five/"]
description: "C++ 系统方向的题目：未定义行为、严格别名和释放后使用；x86 上的内存序和同一条缓存行上的 ping-pong；无锁哈希表和基于纪元的回收；用 futex 实现互斥锁、把线程 id 缓存在 TLS 里；单线程 DAG 调度器和用线程池并行化。每道写题目和简短答法，知识点展开在对应的知识页。"
weight: 2
toc: true
math: true
---

这些题问的是同一件事的几个侧面：代码写出来以后，编译器、CPU、内核各自会对它做什么。每道写题目和简短答法，知识点的展开放在对应的知识页里，这里给链接。

## 1. UB、严格别名、释放后使用：为什么出错的地方离写错的地方很远 {#ub}

**题目**：解释 C++ 的未定义行为（UB）、严格别名（strict aliasing）和释放后使用（UAF），说明它们在实际代码里会引发什么问题。

> **三样东西是一回事：编译器假设它们不会发生**
>
> - **UB 是标准不规定结果的行为**：编译器按“程序里没有 UB”这个前提去优化，可以据此删代码、重排代码。
> - **所以同一份代码 `-O0` 下好好的，`-O2` 就坏了**：坏的地方往往不是写错的那一行，而是被编译器据此改写过的另一处。
> - **严格别名和释放后使用是 UB 里最常见的两类**：前一类让编译器不重读内存，后一类让指针指向别人的数据。

**展开见：[速查：未定义行为](/zh/ref/undefined-behavior/)**

- [第 2 节：编译器怎么利用 UB，四个实测例子](/zh/ref/undefined-behavior/#examples)
- [第 3 节：严格别名和 `memcpy`](/zh/ref/undefined-behavior/#strict-aliasing)
- [第 4 节：释放后使用的常见写法和对象池里的版本号](/zh/ref/undefined-behavior/#uaf)
- [第 5 节：怎么用 sanitizer 和编译选项查](/zh/ref/undefined-behavior/#detect)

## 2. x86 上的内存序和 ping-pong：硬件只重排“先写后读”，慢的是缓存行在核之间来回搬 {#memory-order}

**题目**：解释内存序（memory order）在 x86 上的表现，并结合 MESI 说明同一条缓存行上的 ping-pong。

> **x86 只会把“先写后读”乱序，慢的是缓存行在核之间来回搬**
>
> - **x86 是 TSO**：写先进 store buffer，后面读另一个地址的指令可以先完成，所以只有“先写后读”会乱。`acquire`、`release` 在 x86 上都是普通的 `mov`；`seq_cst` 的写编成 `xchg`，等 store buffer 排空，才管得住它。
> - **写一条缓存行之前要先独占它**：两个核轮流写，这条行就在两个核的缓存之间来回搬，每次 20–100 ns。伪共享改布局隔开，真共享只能让每个核大多数时候只写自己的行。

**展开见：[#2 第 3 节案例：x86 上的内存序和 ping-pong](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case)**

- [3.1 x86 上的内存序：只有“先写后读”会乱](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-x86)
- [3.2 ping-pong：来回搬的代价和两种](/zh/posts/memory-ordering-false-sharing-dependency-chains/#ping-pong)
- [3.3 全局计数器：每个线程各记一份](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-counter)
- [3.4 SPSC 队列的下标：缓存一份对方的](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-spsc)
- [3.5 自旋锁：先读后抢](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-spinlock)
- [3.6 用 `perf c2c` 分辨伪共享和真共享](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-c2c)

## 3. 无锁哈希表和 epoch 回收：表不难写，难的是旧节点什么时候能释放 {#lockfree-map}

**题目**：设计并实现一个无锁哈希表，说明怎么用基于纪元的回收（epoch-based reclamation，和 RCU 是同一个思路）做平滑回收。

> **表用固定容量加开放寻址，难的是旧节点什么时候能释放**
>
> - **先说前提**：键的个数有上限（合约 id 这类），所以表定成固定容量；没有上限时再说扩容怎么做（新表、逐格搬、旧表走同一套回收）。
> - **表**：键用 CAS 占槽，写进去就不再改，删除只把值指针换成空；更新时分配新节点，一次原子交换换上去，读者要么看到旧的、要么看到新的。
> - **回收用 epoch**：读者进出临界区时公告自己在第几代，写者把旧节点按摘下时的代数挂起；全局纪元比它多 2，摘之前进来的读者都已经离开，才释放。弱点是一个读者卡在临界区里，内存就一直涨。
> - **不追求无锁时**：按哈希低位分片，每片一把锁；释放交给后台线程，写线程只入队。

**展开见：[#3 第 6 节案例：无锁哈希表](/zh/posts/hot-path-memory-allocators/#case-lockfree-map)**

- [6.1 表：固定容量、开放寻址，键只占槽不腾槽，值整个换指针](/zh/posts/hot-path-memory-allocators/#case-map)
- [6.2 卡在哪：旧节点换下来的那一刻，可能还有读者拿着它](/zh/posts/hot-path-memory-allocators/#case-problem)
- [6.3 epoch 回收：为什么纪元多 2 才能释放](/zh/posts/hot-path-memory-allocators/#case-ebr)
- [6.4 取舍：读者卡住内存就涨，hazard pointer 和 RCU](/zh/posts/hot-path-memory-allocators/#case-ebr-tradeoff)
- [6.5 分片加锁和后台回收](/zh/posts/hot-path-memory-allocators/#case-shard-lock)
- [6.6 键的个数没有上限时：扩容、腾槽、小的值直接放进槽里](/zh/posts/hot-path-memory-allocators/#case-map-full)

## 4. futex 互斥锁和 TLS 里的线程 id：没人抢时不进内核，抢不到才睡 {#futex}

**题目**：用 `futex_wait_private` 实现一个互斥锁，并说明怎么实现放在 TLS 里的线程 id（tid）。

> **锁的状态放在用户态的一个原子变量里，解锁时看旧值决定要不要进内核叫人**
>
> - **futex 是内核提供的“在一个地址上睡下、叫醒”**：`FUTEX_WAIT` 带一个期望值，值已经变了就不睡，所以不会漏掉叫醒。
> - **锁用三个状态**：0 没锁，1 锁住没人等，2 锁住可能有人等。加锁先 CAS 0 → 1，没人抢就不进内核；抢不到把状态换成 2 再睡，醒来仍然换成 2。解锁换成 0，旧值是 2 才调 `FUTEX_WAKE`。
> - **tid**：`gettid` 是一次系统调用，每个线程第一次取了存进 `thread_local` 变量，之后只是一条 `mov`；`fork` 以后要清掉。

**展开见：[#16 第 3 节案例：用 futex 写一把互斥锁](/zh/posts/spinlock-implementation/#case-futex)**

- [3.1 futex 给了什么：检查和睡下是一步](/zh/posts/spinlock-implementation/#case-futex-api)
- [3.2 两个状态的锁：每次解锁都要进内核](/zh/posts/spinlock-implementation/#case-futex-two)
- [3.3 三个状态：解锁时看旧值，就知道要不要叫人](/zh/posts/spinlock-implementation/#case-futex-three)
- [3.4 线程 id：每个线程只取一次，存在 TLS 里](/zh/posts/spinlock-implementation/#case-tid)

## 5. DAG 调度器：单线程按拓扑序跑，并行靠原子的入度计数 {#dag}

**题目**：实现一个单线程的 DAG 调度器，并说明怎么用线程池把它并行化。

> **单线程按入度排；并行时“减 1”和“是不是我减到了 0”必须是同一步**
>
> - **单线程**：每个节点记还在等几个前驱，等到 0 的进就绪队列；跑完一个，后继各减 1。$O(V + E)$，有环时排出来的节点不足 $n$ 个。
> - **并行**：计数换成原子变量，`fetch_sub` 返回旧值 1 的那个线程提交后继，每个节点正好提交一次；另用一个计数加条件变量，等全部节点跑完。
> - **取舍**：节点太小，调度的开销盖过计算；图是固定的，就预先分层，整层并行地跑。

**展开见：[线程池和 future 第 4 节案例：DAG 调度器](/zh/ref/thread-pool-future/#case-dag)**

- [4.1 单线程：等到 0 的就能跑](/zh/ref/thread-pool-future/#case-dag-serial)
- [4.2 并行卡在哪：几个前驱可能同时跑完](/zh/ref/thread-pool-future/#case-dag-problem)
- [4.3 并行：谁把后继的计数减到 0，谁提交它](/zh/ref/thread-pool-future/#case-dag-parallel)
- [4.4 取舍：节点太小，调度的开销就盖过计算](/zh/ref/thread-pool-future/#case-dag-tradeoff)
