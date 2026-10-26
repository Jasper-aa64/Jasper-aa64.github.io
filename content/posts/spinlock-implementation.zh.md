---
title: "交易系统笔记 #16：自旋锁"
date: 2026-10-21
slug: "spinlock-implementation"
description: "锁只持几十到一两百 ns 时，std::mutex 抢不到锁就进内核睡（futex），一睡一醒要几 µs。自旋锁不睡，但只在持锁的线程一直在跑时才划算。最简单的 CAS 循环每试一次都要独占锁所在的缓存行，等锁的核把行抢来抢去，持锁的核放锁也要排队；先读后抢（TTAS）让等的核各读各的副本；循环里加 PAUSE，锁放开那一刻不用冲刷流水线；放锁时一群核同时冲，用指数退避错开。第 2 部分：票据锁按先来后到排队，MCS 锁让每个核盯自己的那条行，放锁只惊动下一个；读写锁读得短时不比互斥锁快；umonitor / umwait 和 WFE 让等的核停下来，等那条行被写了再醒。"
summary: "自旋锁快不快，看等锁的核在干什么：每次都读改写，就把锁所在的行抢来抢去；先读后抢、循环里加 PAUSE、抢输了退一步，等的时候才几乎不打扰持锁的核。"
chapter: 1
categories: [Systems]
tags: [cpp, spinlock, atomics, futex, mesi, pause, ticket-lock, mcs-lock, rwlock, umwait, hft, low-latency]
toc: true
math: true
---

改订单簿的一档、拷一份行情快照，这类代码要加锁保护，叫临界区（`lock()` 和 `unlock()` 之间的那一段），持锁时间只有几十到一两百 ns。用 `std::mutex` 护着临界区，没抢到锁的线程会被挂起，锁放开后再被叫醒，一睡一醒要几 µs，是持锁时间的 10 倍到上百倍。自旋锁（spinlock）的办法是不睡：抢不到就留在原地反复看，锁一放开立刻接手。

“反复看”怎么看，决定了这把锁快不快。看的方式不对，等锁的核会把锁所在的那条缓存行抢来抢去，连正拿着锁的核都被拖慢；锁放开时，它们又一窝蜂同时去抢。把这些问题一个个去掉，就是一把能用的自旋锁。不过动手之前要先弄清楚，睡到底贵在哪里，什么时候转比睡划算。

## 1. 自旋锁怎么写：从 CAS 循环到 TTAS 和 PAUSE

### 1.1 futex：std::mutex 抢不到锁就去睡

`std::mutex` 在 Linux 上的做法，可以用一个原子整数写出来。它有三个状态：0 是没锁，1 是锁着、没人等，2 是锁着、可能有人在睡。

```cpp
#include <atomic>

class SleepingMutex {  // 0 = 没锁，1 = 锁着、没人等，2 = 锁着、可能有人在睡
public:
    void lock() {
        int c = 0;
        if (state_.compare_exchange_strong(c, 1, std::memory_order_acquire)) return;  // 快路径：一次 CAS
        if (c != 2) c = state_.exchange(2, std::memory_order_acquire);
        while (c != 0) {
            state_.wait(2, std::memory_order_relaxed);  // 还是 2 就进内核睡（Linux 上是 futex）
            c = state_.exchange(2, std::memory_order_acquire);
        }
    }
    void unlock() {
        if (state_.exchange(0, std::memory_order_release) == 2)
            state_.notify_one();  // 可能有人在睡，才进内核叫醒一个
    }

private:
    std::atomic<int> state_{0};
};
```

没人争的时候（指 `lock()` 时状态是 0，持锁期间也没有别的线程来抢，状态不会变成 2），`lock()` 只做一次 CAS（compare-and-swap，比较并交换：值等于 0 才改成 1），`unlock()` 只做一次 `exchange`，把 1 改回 0。两次都在用户态，各约 2–6 ns（[速查 2.1](/zh/ref/cpu-memory/#latency)），这时它和自旋锁一样便宜。

抢不到时才分岔。`lock()` 先把状态改成 2，意思是“有线程在等这把锁，放锁时得叫醒它”，然后这个线程自己调 `wait` 去睡。C++20 的 `atomic::wait` 在 Linux 上落到 futex（fast userspace mutex）系统调用：内核核对这个整数还是 2，就把线程挂到这个地址的等待队列上，切去跑别的线程。放锁的一方从 `exchange` 拿到的旧值是 2，就用 `notify_one`（还是 futex）叫醒一个。被叫醒的线程要等调度器把它放回某个核，才能接着执行 `exchange` 去抢。`std::mutex` 底下的 glibc 互斥锁用的也是这三个状态。

这一来一回要付两次系统调用（各约 0.1–0.5 µs），外加等的线程切出去、再切回来两次线程切换（各约 1–5 µs，还要算上缓存被别的线程冲掉的代价）。等的那个核要是已经进了省电状态，叫醒它还要更久（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 的 2.2）。合起来，从放锁到等的线程真正跑起来，约 2–10 µs。可持锁时间只有几十到一两百 ns，也就是说，锁很快就放开了，睡下去的线程却要再过几 µs 才能接手，晚了 10 倍到上百倍。不睡，原地盯着锁，锁一放开就能接手，这就是自旋锁存在的理由。

几十到一两百 ns 是这么来的：一个线程拿到锁、跑完临界区、再放锁，拆开看：

| 持锁时做的事 | 实际干了什么 | 没人抢时（数据在本核缓存里） | 有人抢时（行要从别的核搬过来） |
|---|---|---|---|
| 加锁 | 一次 CAS | 约 2–6 ns | 约 20–100 ns：锁所在的行刚被上一个持锁的核写过 |
| 改订单簿的一档 | 按价格找到那一档，加上数量，写回去，十来条指令 | 几 ns 到十几 ns | 约 20–200 ns：这一档所在的一两条行刚被别的核改过 |
| 拷一份 10 档快照 | 买卖各 10 档，每档价格、数量各 8 B，共 320 B，约 5 条缓存行 | 十几 ns | 几十到一两百 ns：5 条行可以同时去取 |
| 放锁 | 一次 `exchange` | 约 2–6 ns | 约 20–100 ns：等锁的核手里有这条行的副本，要先作废 |

改一档和拷快照一次只做一件，再加上加锁、放锁，持锁时间在没人抢时是几十 ns，有人抢时是一两百 ns。

### 1.2 自旋的前提：持锁的线程一直在跑

转比睡划算，是因为锁很快就会放开。这要两个条件：持锁的线程一直在跑，持锁时间很短。有一条不成立，锁就迟迟放不开。

第一条坏在调度上。持锁的线程要是被换下 CPU（时间片用完、被别的线程抢占、等 I/O），锁就跟着它一起停住，等的核只能干转，一转就是一个时间片，毫秒级，比睡一次贵得多。更糟的是等的线程和持锁的线程挤在同一个核上：等的一方占着核在转，持锁的一方排不上，锁就放不开，直到时间片用完。所以用户态的自旋锁总和绑核一起用：每个会碰这把锁的线程各绑一个隔离出来的核（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 的 1.2），操作系统就没有理由把持锁的线程换下去。

第二条坏在临界区里做了慢事。写日志、`malloc`、系统调用、查数据库、等网络，这些要么几 µs 起步，要么可能阻塞。等的线程绑在自己的隔离核上时，干转本身不浪费什么，那个核本来也没有别的活。坏处落在等的线程身上：它往往是热路径上的线程（比如要读订单簿去下单的那个），持锁的一方慢几 µs，它就晚几 µs，而且慢多久没法预测，尾延迟跟着拉长。这笔账转和睡都要付，换成 `std::mutex` 也省不掉。慢事里要是有会阻塞的（系统调用、缺页、等网络），持锁的线程还会被换下 CPU，第一条也跟着坏了。所以锁里只放改数据的那几行：要查的、要算的先在锁外做完，进锁只写结果。

两条做不到，就用会睡的 `std::mutex`，或者折中：先转一小会儿，还拿不到再睡。glibc 的自适应互斥锁（`PTHREAD_MUTEX_ADAPTIVE_NP`）就是这样做的，不过 `std::mutex` 默认不是这种类型。

### 1.3 最简单的自旋锁：一个原子变量，循环 CAS

自旋锁就是一个整数 `locked_`：0 是锁空着，1 是有人拿着。`lock()` 要亲手把它从 0 改成 1，改成了就是自己拿到了锁，可以进临界区；改不成说明别人拿着。`unlock()` 把它写回 0，下一个线程才改得成。不睡，就是把 `SleepingMutex` 里“进内核睡”那一步换成“再试一次”：

```cpp
#include <atomic>

class CasSpinLock {
public:
    void lock() {
        int expected = 0;
        while (!locked_.compare_exchange_weak(expected, 1, std::memory_order_acquire,
                                              std::memory_order_relaxed)) {
            expected = 0;  // 失败时 expected 被改成了当前值 1，改回 0 再试
        }
    }
    void unlock() { locked_.store(0, std::memory_order_release); }

private:
    std::atomic<int> locked_{0};
};
```

`compare_exchange_weak(expected, 1, …)` 的意思是：`locked_` 等于 `expected`（0）就改成 1，返回 true；不等就把 `locked_` 的当前值写进 `expected`，返回 false。所以失败以后 `expected` 变成了 1，下一轮之前要改回 0。不改回去，下一轮问的就成了“等于 1 就改成 1”：锁明明被别人拿着，这次 CAS 却会成功，两个线程同时进了临界区。CAS 这么设计，是因为它最常见的用法是“读出旧值、算出新值、写回去”：失败说明别人刚改过，要拿最新的值重算。失败时顺手把当前值交回来，就省掉一次单独的读，硬件本来也已经读到了它（x86 的 `lock cmpxchg` 失败时把当前值放进 EAX 寄存器，ARM 的独占读先读出了它）。比如把一个原子数翻倍：`int old = x.load(); while (!x.compare_exchange_weak(old, old * 2)) {}`，失败后 `old` 已经是最新值，直接重算：比如 `x` 是 5，读出 `old = 5` 以后别的线程把 `x` 改成了 7，这次 CAS 失败，`old` 被改成 7，下一轮把 7 改成 14。锁的用法正好相反，期望值永远是 0，所以每轮都要改回去。`weak` 允许偶尔“明明相等也报失败”，ARM 上用一对独占读写实现时会这样：CAS 拆成独占读、独占写两条指令，两条之间要是来了中断，或者别的核碰了这条行，独占写就失败，哪怕值没变。x86 的 `lock cmpxchg` 是一条指令，不会这样，`weak` 和 `strong` 编出来一样。`strong` 在 ARM 上要在里面再包一层循环，把这种失败挡掉。外面本来就有循环，用 `weak` 就够了；只判断一次、失败就走的地方才用 `strong`。

`compare_exchange_weak` 后面那两个内存序参数，第一个用在 CAS 成功时，第二个用在失败时。内存序管的是临界区里的读写不能跑到锁外面去（[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 的 1.5）。`lock()` 成功的那次 CAS 用 acquire：临界区里的读写不能提到拿锁之前，这样才看得到上一个持锁者写的东西。`unlock()` 的写用 release：临界区里的读写不能拖到放锁之后。两者配成一对，上一个持锁者在临界区里写的，下一个持锁者一定看得到。失败的那几次 CAS 什么也没拿到，用 relaxed 就行。拿锁时不需要 release，它管的是拿锁之前的读写，和临界区无关。

用 `exchange` 写更短：`while (locked_.exchange(1, std::memory_order_acquire)) {}`，把 1 写进去、返回旧值，旧值是 0 就说明锁是自己拿到的。这就是测试并设置（test-and-set，TAS）。两种写法每试一次都是一次读改写（read-modify-write，RMW），毛病也一样。

### 1.4 读改写抢行：等的核每试一次都要把行抢过来

`locked_` 住在一条缓存行里。在<a href="/maps/hardware-map.zh.html" target="_blank" rel="noopener">硬件地图</a>上，这条行可以在好几个核的 L1D 里各有一份副本，规矩是右边 MESI 那个框写的：谁要写，先让别人的副本作废（[MESI 专题](/zh/posts/low-latency-mesi-cache-coherence/)）。

读改写是一种写。x86 上 CAS 编成 `lock cmpxchg`，不管比较成不成功，它都要先把这条行拿到本核、独占（MESI 的 M 或 E），比较失败时把原值写回去。ARM 上换成 `casal` 这类指令，同样是对这一条行的读改写。所以 3 个核在等锁时，每个核每转一圈都要把行从别的核那里抢过来一次，每抢一次约 20–100 ns（[速查 2.6](/zh/ref/cpu-memory/#cross-core)）。这条行就在等锁的核之间来回搬，一刻不停。

搬行本身只是浪费，坏的是它挡住了持锁的核。持锁的核放锁时要写 `locked_`，同样得先把行抢回来，它得排在等锁的核那一串读改写后面：锁早该放了，放锁的那次写却迟迟落不下去。被保护的数据要是和 `locked_` 在同一条行里，临界区每改一次数据也要抢一次，持锁时间都被拖长。后一个问题好治，给锁单独一条行就行（`alignas(64)`，[#6](/zh/posts/alignment-layout-cache-dram-geometry/)）；前一个问题要改的是等的方式。

### 1.5 TTAS：先读，看着空了再抢

等的核其实只需要知道锁放了没有，读就够了；看到放了，才值得去抢。这就是先测试、再测试并设置（test-and-test-and-set，TTAS）：

```cpp
#include <atomic>
#include <immintrin.h>  // _mm_pause，见 1.6

class TtasSpinLock {
public:
    void lock() {
        for (;;) {
            if (!locked_.exchange(true, std::memory_order_acquire)) return;  // 先抢一次：没人争时只有这一次读改写
            while (locked_.load(std::memory_order_relaxed)) _mm_pause();    // 抢不到就只读，看着空了再回去抢
        }
    }
    void unlock() { locked_.store(false, std::memory_order_release); }

private:
    alignas(64) std::atomic<bool> locked_{false};  // 独占一条缓存行
};
```

变化在循环里的第二行：抢不到以后，等的核只做普通的读。读不需要独占，3 个等锁的核各拿一份共享副本（MESI 的 S），每次读都在自己的 L1D 里命中，约 1 ns，没有一条消息跑出核外。持锁的核不受打扰，临界区里也没人来抢行。

锁放开时，持锁的核写 `locked_`，发一轮失效请求，把 3 份副本作废。等的核下一次读不命中，各自把行重新读回来，看到 `false`，才回到第一行去 `exchange`。读改写只在“看起来空了”时才做；没人争的时候，第一行一次就成功，和 `CasSpinLock` 一样快。

循环里的读用 relaxed 就够。它只用来判断“值得去抢了”，真正拿锁靠的是 `exchange` 的 acquire。

### 1.6 PAUSE：别让流水线排满对这条行的读

`while (locked_.load(...))` 这个循环只有两三条指令：读、比较、跳回去。空转着等锁，锁放开的那一刻，等锁的核要冲刷一次流水线，经过是这样的：

1. **提前读**。乱序执行的核不会等一圈做完再开始下一圈，它按分支预测（[#7](/zh/posts/branch-prediction-branch-optimization/)）一直猜“还要再转”，把后面几十圈的读都先发出去。这些读都拿到了旧值 `true`，在 ROB 里排队等退休（retire，按程序顺序确认结果）。读到的值要等退休才算数。
2. **放锁**。持锁的核写 `locked_ = false`，失效请求送到等锁的核，作废它 L1 里的这条行。这时 ROB 里那一串读已经拿到了值，却都还没退休。
3. **对账**。x86 承诺读和读按程序顺序生效：靠后的读不能比靠前的读看到更旧的值。提前读是在赌：从拿到值到退休这段时间里，这条行没人改。赌赢了，提前拿到的值和按顺序读到的一样。现在行恰好在这段时间里被改了，这些值就不一定是按顺序读该看到的。逐条核对太贵，硬件不去核对：只要有拿到了值、还没退休的读，它读过的行被作废，就按违规处理。
4. **冲刷**。从最早那条受影响的读开始，后面的指令全部扔掉、重新执行。这叫内存序冲刷（memory ordering machine clear），和分支猜错一样要清空整条流水线，几十个周期，偏偏落在锁刚放开、最该快的时候。重新执行的读拿到 `false`，循环该退出了，可分支预测一直猜“还要再转”，出口这里又猜错一次，再冲一次。

在硬件地图上，这件事横跨两个框：失效请求顺着灰色虚线进 invalidate queue，撞上 ROB 里还没退休的那一串读。

<a href="/images/spinlock-implementation/pause-rob.zh.svg" target="_blank" rel="noopener"><img src="/images/spinlock-implementation/pause-rob.zh.svg" alt="锁放开那一刻，等锁的核的 ROB 里有什么。上半是空循环：ROB 里第 1 圈的读已退休，第 2 到第 10 圈的读都提前读到了旧值 true、还没退休；核 0 放锁的失效请求一来，这 9 次读全部扔掉重来（内存序冲刷），退出循环时又一次分支猜错。下半是加 pause：第 1 圈的读已退休，后面是一条停约 140 个周期的 pause，第 2 圈的读还没发出，失效请求来时没东西要扔，只剩一次分支猜错。底下说明代价：最多晚约 140 个周期（约 35 ns）发现锁空了。" loading="lazy" decoding="async"></a>

`pause` 指令就是为这种循环准备的。它让核停约 140 个周期（约 35 ns）再往下走，下一圈的读停完才发出。一圈里那次读命中 L1，几个周期就退休了，所以失效请求进来时，流水线里多半没有拿到了值、还没退休的读，第 3 步没东西要对，第 4 步的冲刷就省了，只剩出口那一次分支猜错。代价是发现锁空了会晚一点：锁可能在 `pause` 中途放开，要等它停完才去读，最多晚一次 `pause`，约 35 ns。它还有两个好处：转得慢了，核的功耗降下来；这个核开着超线程（SMT）的话，兄弟线程能用上执行资源（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 的 2.1）。

一条 `pause` 约 140 个周期，是现在交易服务器（Skylake 以后的至强）上的数，平时就按它估。这个数不是写死的：Skylake 之前的 Intel 上只有十来个周期，同一段代码换台机器，一次 `pause` 能差 10 倍。所以“转 1000 次就去睡”这种按次数定的预算靠不住，要限时就按时间算。ARM 上没有 `pause`：`yield` 是给多线程核的提示，在很多核上等于空操作，有的库改用 `isb` 拖一小段时间；真要在等的时候省电，就用 `wfe` 让核睡到这条行被别人写。可移植的写法是包一个小函数：

```cpp
#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
inline void cpu_relax() { _mm_pause(); }
#elif defined(__aarch64__)
inline void cpu_relax() { asm volatile("yield" ::: "memory"); }
#else
inline void cpu_relax() {}
#endif
```

别拿 `std::this_thread::yield()` 代替它。它在 Linux 上是 `sched_yield` 系统调用，每次约 0.1–0.5 µs；核上有别的线程能跑时，它还会把核让出去，等于自己把自己换下了 CPU。

### 1.7 放锁的一刻：等的核一起冲

TTAS 让持锁期间安静了，放锁那一刻还是乱的。锁放开后，3 个等的核都读到 `false`，几乎同时回到第一行去 `exchange`。只有第一个成功，另外 2 个失败，可每次 `exchange` 都要把行抢到自己那里，失败的也一样。等的核越多，这一阵读改写越长；新主人的持锁时间要是很短，它放锁的那次写就得排在这一串后面。所以每次交接的时间大约随等锁的核数 $N$ 线性增长：

$$t_{\text{交接}} \approx N \times t_{\text{搬行}}, \qquad t_{\text{搬行}} \approx 20\text{–}100\ \text{ns}$$

4 个核在等，一次交接就是约 80–400 ns，比一次持锁本身还长。

一个办法是抢输了先退一步：

```cpp
#include <algorithm>
#include <atomic>

class BackoffSpinLock {
public:
    void lock() {
        for (int backoff = 1;; backoff = std::min(backoff * 2, kMaxBackoff)) {
            if (!locked_.exchange(true, std::memory_order_acquire)) return;
            for (int i = 0; i < backoff; ++i) cpu_relax();  // 抢输了：先歇一会儿，再去看（cpu_relax 见 1.6）
            while (locked_.load(std::memory_order_relaxed)) cpu_relax();
        }
    }
    void unlock() { locked_.store(false, std::memory_order_release); }

private:
    static constexpr int kMaxBackoff = 64;
    alignas(64) std::atomic<bool> locked_{false};
};
```

每输一次，下次多歇一倍（指数退避），各个核回来的时间就错开了，同时冲的少了。歇着多半不添延迟：输了，说明锁刚被别的核拿走，它要持锁一整段；后面要是还有别的核在等，自己轮到之前本来就要等好几段。歇的时间不超过这段反正要等的时间，自己并不更晚，只是少挤了一次抢行。输得越多，说明抢的核越多、前面要等得越久，歇的就该越长，所以翻倍。实际的实现还会给歇的长度加一点随机，免得几个核步调一致，又撞在一起。歇过了头才真添延迟：锁放开时自己还在歇，锁空在那里没人拿，或者被后来的核拿走。只有一两个核在抢时，前面本来没几段要等，退避省下的抢行少，添的延迟却实打实，上限要设得小。上限也要按时间想：64 次 `pause` 约 3 µs，换到 `pause` 只有十来个周期的老机器上只剩约 0.2 µs。退避还让锁更偏心：输得多的核歇得久，下次更难赢；刚来的核从歇 1 次开始，反应最快。运气差的核可能一直输下去，这叫饿死（starvation）。上限保证它每隔一段总会回来抢，但不保证抢得到。

等的核一多，退避也只是缓解。根本的办法是排队：按先来后到一个一个交接（票据锁，2.1），再让每个等的核在自己的那条行上转，放锁时只惊动下一个（MCS 锁，2.2）。不过在交易系统里，一把锁经常有好几个核在抢，本身就说明设计该改了：改成只有一个线程写，别的线程把要改的东西通过队列交给它（[#4](/zh/posts/lock-free-queue-logger-micro-batching/)、[#5](/zh/posts/spmc-shared-memory-broadcast-ring/)），比把锁写得再好都管用。

## 2. 很多核一起等：票据锁、MCS 锁、读写锁和地址监控等待

### 2.1 票据锁（ticket lock）：取号排队

1.7 留下两个问题：放锁时等的核一起冲，交接时间随等的核数线性增长；谁抢到全凭运气，运气差的核会饿死。两个问题出在同一处：锁只有“空”和“占”两种状态，放锁时所有等的核看到的是同一件事“空了”，只能一起去抢。票据锁让每个等的核等的是不同的事：

```cpp
class TicketSpinLock {
public:
    void lock() {
        unsigned my = next_.fetch_add(1, std::memory_order_relaxed);  // 取号
        while (serving_.load(std::memory_order_acquire) != my) cpu_relax();  // 等叫到自己
    }
    void unlock() {
        // 只有持锁的线程会改 serving_，读出来加 1 再写回去就行，不用读改写
        serving_.store(serving_.load(std::memory_order_relaxed) + 1, std::memory_order_release);
    }

private:
    alignas(64) std::atomic<unsigned> next_{0};     // 取号机：每来一个线程加 1
    alignas(64) std::atomic<unsigned> serving_{0};  // 叫号屏：等的线程都在读它
};
```

像银行叫号。来一个线程，先在 `next_` 上 `fetch_add` 取一个号：这是一次读改写，返回加之前的值，所以每个线程拿到的号都不同。然后它盯着 `serving_`，等叫到自己的号。放锁就是把 `serving_` 加 1，叫下一个号。`serving_` 只有持锁的线程会改，没人和它抢，读出来加 1 再写回去就行，x86 上是一条普通的 `mov`；用 `fetch_add` 也对，但那是一次带 `lock` 前缀的读改写，多花约 2–6 ns。`next_` 和 `serving_` 各占一条行：放在一起的话，每来一个线程取号，`fetch_add` 都要把这条行独占过去，正在读 `serving_` 的核手里的副本跟着作废，持锁期间也不得安静。

放锁时，所有等的核还是都要重读 `serving_`：这条行被写了，它们的副本都作废，各自再读一次，N 个核就是 N 次读不命中。但读到新值以后，只有号对上的那一个核出循环，别的核接着读、接着等，没有人去抢。1.7 的 TTAS 放锁后是一串读改写，每次都要把行独占过去，新主人放锁也得排在后面；这里只剩一串读，读的核各拿一份共享副本，不用把行抢走。号是先来先拿的，所以严格先来后到，没有人会饿死。

剩下的代价在那 N 次读：叫到号的核也在里面，它的读不一定先被满足，最坏要等前面 N−1 次读走完，所以交接仍然随 N 变长，只是每一步从读改写换成了读。等的核知道自己前面还有几个人（`my - serving_`），可以按人数歇：前面有 5 个人，就先歇约 5 段持锁时间再来看，这叫按比例退避（proportional backoff），比 1.7 的指数退避准。

票据锁的软肋在先来后到本身：轮到的那个线程必须马上接手。它要是被换下了 CPU（没绑核、被抢占），锁明明空着，后面所有人都得等它回来，一等就是一个调度周期，ms 级。TTAS 不排队，锁空了谁都能拿，反而不怕这个。所以排队锁把 1.2 的前提收得更紧：不光持锁的线程，等锁的线程也得一直在跑。

### 2.2 MCS 锁：每个核在自己的那条行上等

票据锁放锁时 N 个核都要重读，是因为大家盯的是同一条行。要让放锁只惊动下一个，就得让每个等的核盯不同的行：每个核带一个自己的节点，排成链表，各自盯自己节点里的一个标志，前一任放锁时只写下一个节点的标志。这就是 MCS 锁，名字取自两位作者 Mellor-Crummey 和 Scott：

```cpp
class McsSpinLock {
public:
    struct alignas(64) Node {  // 每个等锁的线程带一个，各占一条缓存行
        std::atomic<Node*> next{nullptr};
        std::atomic<bool> granted{false};  // 前一任交接时写 true
    };

    void lock(Node* me) {
        me->next.store(nullptr, std::memory_order_relaxed);
        me->granted.store(false, std::memory_order_relaxed);
        Node* prev = tail_.exchange(me, std::memory_order_acq_rel);  // 排到队尾，拿到原来的队尾
        if (prev == nullptr) return;                                 // 队是空的：直接拿到锁
        prev->next.store(me, std::memory_order_release);             // 挂到前一个后面
        while (!me->granted.load(std::memory_order_acquire)) cpu_relax();  // 只盯自己的节点
    }

    void unlock(Node* me) {
        Node* next = me->next.load(std::memory_order_acquire);
        if (next == nullptr) {
            Node* expected = me;
            if (tail_.compare_exchange_strong(expected, nullptr, std::memory_order_release,
                                              std::memory_order_relaxed))
                return;  // 后面确实没人：队清空
            // 有人已经排到队尾、还没来得及挂上来：等它挂好
            while ((next = me->next.load(std::memory_order_acquire)) == nullptr) cpu_relax();
        }
        next->granted.store(true, std::memory_order_release);  // 只叫醒下一个
    }

private:
    alignas(64) std::atomic<Node*> tail_{nullptr};
};
```

`lock()` 先把自己的节点清干净，再用 `tail_.exchange(me)` 一步把自己设成队尾，同时拿回原来的队尾 `prev`。`prev` 是空的，说明没人拿着锁，直接返回；不是空的，就把自己挂到 `prev->next` 上，然后只盯自己的 `granted`。

`unlock()` 要看后面有没有人。`next` 不为空，就把它的 `granted` 写成 `true`，交接完成。`next` 为空有两种可能：真的没人在等；或者有人已经做完 `exchange` 排到了队尾，还没来得及执行 `prev->next.store(me)` 挂上来。这两种情况光看 `next` 分不清，所以用 CAS 试着把队尾从自己改回空：成功说明队尾还是自己，后面确实没人；失败说明队尾已经换成了别人，那个线程马上就会挂上来，等它挂好再交接。这里不能直接把 `tail_` 写成空，那样就把刚排进来的线程丢了，它永远等不到有人写它的 `granted`。

好处在放锁那一下。每个等的核只在第一次读自己的 `granted` 时取一次行，之后一直命中自己的 L1，持锁期间这几条行上没有任何流量。放锁写的是下一个节点的那条行，只有下一个核手里有它的副本，失效只发给这一个核，它重读一次就拿到 `true`。交接永远是一次搬行（约 20–100 ns），等的核再多也不变。这里的链表也不会像平常那样处处不命中：平常遍历链表要从头一个一个追指针，每一步都得等上一步的读回来；MCS 从不遍历，每个线程只碰自己的节点，再各碰一次前一个和后一个的节点，不命中只发生在交接那几次搬行上，次数固定。节点要各占一条行（`alignas(64)`），否则两个核的节点挤在一条行上，写一个节点会把另一个核的副本也作废，又回到大家盯同一条行。

内存序要配对，理由各不相同：

- `tail_.exchange` 用 `acq_rel`。队是空的那条路上，线程直接拿到锁，没有经过 `granted`，只能靠这次 `exchange` 的 acquire 接上一任放锁时那次 CAS 的 release，才看得到上一任在临界区里的写。release 那一半是因为它把节点交了出去，后来的线程会拿着这个指针往节点的 `next` 里写，节点的初始化要先于这些写。
- `prev->next.store` 用 release，`unlock()` 里读 `next` 用 acquire。前一任拿到我的指针后要往我的 `granted` 里写 `true`，我在 `lock()` 开头把 `granted` 清成 `false` 的那次写必须先发生，不然我的 `false` 可能盖掉前一任的 `true`，我就永远等下去。
- 交接时 `granted` 的 release 写和 acquire 读，就是 1.3 的配对：临界区里的写跟着锁交给下一任。

代价有三处。接口要多传一个节点，节点要活到 `unlock()` 为止，通常放在调用方的栈上，`lock` 和 `unlock` 在同一个作用域里。没人争时，`lock()` 是一次 `exchange`，和 TTAS 一样，`unlock()` 却要一次读加一次 CAS，比 TTAS 放锁的一次普通写多一次读改写。它和票据锁一样是排队锁，轮到的线程被换下 CPU，整条队都卡住。Linux 内核的自旋锁（qspinlock）把两头的好处拼在了一起：没人争时只改一个 4 字节的字，有人排队才用 MCS 节点，节点每个核预先备好，调用方不用传。

### 2.3 三种锁放在一起比

| | TTAS + 退避 | 票据锁 | MCS 锁 |
|---|---|---|---|
| 放锁时惊动几个核 | N 个：都重读，再一串读改写 | N 个：都重读，只有 1 个出来 | 1 个 |
| 一次交接 | 约 N × 20–100 ns | 1 轮失效 + 最多 N 次读 | 约 20–100 ns，和 N 无关 |
| 先来后到 | 不保证，会饿死 | 保证 | 保证 |
| 没人争时 | 加锁 1 次 `exchange`，放锁 1 次普通写 | 加锁 1 次 `fetch_add` + 1 次读，放锁 1 次普通写 | 加锁 1 次 `exchange`，放锁 1 次读 + 1 次 CAS |
| 等的线程被换下 CPU | 别的核照样能拿 | 轮到它时整条队卡住 | 同票据锁 |

2–4 个绑了核的线程偶尔抢一下，TTAS 加退避就够：没人争时最便宜，也不怕谁被换下。很多核长时间抢同一把锁，MCS 交接最稳。不过 1.7 结尾那句仍然成立：交易系统的热路径上，好几个核抢一把锁本身就该改设计，改成只有一个线程写，别的线程通过队列把要改的东西交给它。

### 2.4 读写锁：读的一方一起进，但都要改同一个计数

行情快照这类数据，读的线程多，写的线程只有一个，偶尔写一次。互斥锁让读的一方也一个一个进，可读和读之间并不冲突。读写锁（`std::shared_mutex`）分两种拿法：读的一方用 `lock_shared()`，好几个可以同时在里面；写的一方用 `lock()`，要等里面一个读的都没有，进去以后别人都进不来。最简单的写法是用一个整数记状态：

```cpp
class RwSpinLock {  // state_：-1 = 写的一方拿着，0 = 空，n > 0 = n 个读的一方在里面
public:
    void lock_shared() {
        for (;;) {
            int n = state_.load(std::memory_order_relaxed);
            if (n >= 0 && state_.compare_exchange_weak(n, n + 1, std::memory_order_acquire,
                                                       std::memory_order_relaxed))
                return;
            cpu_relax();
        }
    }
    void unlock_shared() { state_.fetch_sub(1, std::memory_order_release); }

    void lock() {
        for (;;) {
            int expected = 0;
            if (state_.load(std::memory_order_relaxed) == 0 &&
                state_.compare_exchange_weak(expected, -1, std::memory_order_acquire,
                                             std::memory_order_relaxed))
                return;
            cpu_relax();
        }
    }
    void unlock() { state_.store(0, std::memory_order_release); }

private:
    alignas(64) std::atomic<int> state_{0};
};
```

读的一方进来时，只要状态不是 −1（没有写的一方在里面），就用 CAS 加 1，出去时减 1；写的一方要把状态从 0 改成 −1，出去时写回 0。

它比互斥锁好，要两个条件同时满足：读的一方在锁里待得久（µs 级，比如遍历一整张表），读远多于写。这时几个读的一方的临界区真能叠在一起跑。

读得短时它不比互斥锁快，因为读的一方也在写。`lock_shared()` 和 `unlock_shared()` 都是对 `state_` 的读改写，每次都要把这条行独占过去。4 个核各读一档盘口，临界区约 20 ns，可每读一次要搬两次行（约 2 × 20–100 ns），行在 4 个核之间来回搬，读的一方其实一个接一个地排在这条行上，和互斥锁一样串行，状态更复杂，还更慢。1.4 讲的“等的核把锁所在的行抢来抢去”，在读写锁上连已经拿到锁的读的一方都躲不开。

写得多时它也不行。上面这份写法偏向读的一方：只要一直有读的一方进进出出，状态就到不了 0，写的一方一直进不去，饿死的是写的一方。偏向写的一方的写法反过来：有写的一方在等，新来的读的一方就不让进，读的一方要排队。glibc 的 `pthread_rwlock`（Linux 上 `std::shared_mutex` 底下就是它）默认偏向读的一方。写多时，读写锁只是一把记账更贵的互斥锁。

读多写少、又读得短，交易系统里的办法是让读的一方完全不写：版本号（seqlock）和双数组（[#14](/zh/posts/prefetch-warmup-double-buffer/)）。读的一方只读一个版本号或下标，对不上就重读，写的一方从不等读的一方。代价是只能有一个写的一方，读的一方偶尔要重读。

### 2.5 地址监控等待：`umonitor` / `umwait`、`WFE`

到这里有两种等法。自旋加 `pause`，核一直在跑，耗电，开着超线程时还占着兄弟线程的执行资源；futex 进内核睡，核让出来了，可从放锁到真正醒来要 2–10 µs。地址监控等待在两者之间：告诉硬件“盯着这条行，有人写它就叫醒我”，然后核进轻度睡眠。叫醒靠的就是缓存一致性：别的核要写这条行，先得发失效请求把这个核的副本作废，失效请求一到，硬件顺带把核叫醒。不用系统调用，也不用一直转。在[硬件地图](/zh/ref/cpu-memory/)上，这件事发生在核和 L1D 之间。

x86 上这是 WAITPKG 扩展里的指令，Intel 从 Tremont、Alder Lake、Sapphire Rapids 起才有，用之前要查 CPUID；AMD 上对应的是 `monitorx` / `mwaitx`。

```cpp
#include <atomic>
#include <cstdint>
#include <immintrin.h>  // 编译加 -mwaitpkg；运行前先用 CPUID 确认这颗 CPU 支持 WAITPKG
#include <x86intrin.h>  // __rdtsc

inline void wait_until_set(std::atomic<uint32_t>& flag) {
    while (flag.load(std::memory_order_acquire) == 0) {
        _umonitor(&flag);                                      // 1. 登记要盯的这条行
        if (flag.load(std::memory_order_acquire) != 0) break;  // 2. 登记完再看一次
        _umwait(1, __rdtsc() + 100000);  // 3. 进 C0.1 等：这条行被写、到点、来中断都会醒
    }
}

inline void signal(std::atomic<uint32_t>& flag) {
    flag.store(1, std::memory_order_release);  // 普通的写就行
}
```

`_umonitor(addr)` 登记 `addr` 所在的那条行。`_umwait(ctrl, deadline)` 让核停下来，直到这条行被写、TSC（时间戳计数器）走到 `deadline`、来了中断，或者到了操作系统设的上限（Linux 默认约 10 万个 TSC 周期，几十 µs），才醒。`ctrl` 选睡多深：1 是 C0.1，醒得快；0 是 C0.2，更省电，醒得慢一些。两种都还在 C0 里，没进 C1、C6 这些要停时钟的状态，所以醒来比从内核叫醒快得多，又比 `pause` 转着慢一点。醒了不代表条件成立，也可能是到点或者来了中断，所以外面要套循环再看一次。

三步的顺序不能换：先登记，再看一次，最后睡。要是先看、再登记，在“看到是 0”和“登记”之间别人把它写成了 1，这次写发生在登记之前，硬件不会因此叫醒，核要一直睡到 `deadline`。登记完再看一次，写要是发生在登记之前，第 2 步就能看到；发生在登记之后，第 3 步会被它叫醒。`deadline` 是一个绝对的 TSC 值，不是时长，要写成 `__rdtsc() + 等多久`；写 0 等于一个早就过去的时刻，`umwait` 马上返回，循环就成了空转。

ARM 上对应的是 `WFE`（wait for event）。先用独占读 `ldaxr` 读这个地址，硬件会记住这条行（独占监视器，exclusive monitor）；然后 `WFE` 睡下。别的核写这条行，监视器被清掉，这本身就算一个事件，核被叫醒，写的一方不用再发 `SEV`。Linux 在 ARM64 上等一个变量变值（`smp_cond_load_acquire`）就是这么写的。`WFE` 也可能无故醒来，同样要在循环里再看。

交易系统里，热路径上绑核的线程还是 `pause` 转着等，几十 ns 都不想多付。`umwait` 适合不在热路径上、又不想睡进内核的等待，比如日志线程等队列来数据：核省下来，开着超线程时兄弟线程能用上整个核。它也能和排队锁配：MCS 的每个等锁的核本来就只盯自己的那条行，`umonitor` 这条行再 `umwait`，前一任交接的那次写正好把它叫醒。很多交易机在 BIOS 里关掉了深的 C-state，C0.1、C0.2 不受影响；操作系统也可以单独关掉 C0.2（`IA32_UMWAIT_CONTROL`），那时 `ctrl = 0` 也只进 C0.1。

## 应用 {#in-practice}

1.3 到 1.5 节的读改写抢行和 TTAS，在实际优化里对应“{{% bottleneck-ref "tas-spinlock" "plain" %}}”这张卡片；1.1 节讲的线程睡下、再被叫醒的代价，是“{{% bottleneck-ref "thundering-herd" "plain" %}}”这张卡片的原理。两张卡片都写了在 perf 里看到什么、怎么改、怎么验证。

{{% bottleneck "tas-spinlock" %}}

{{% bottleneck "thundering-herd" %}}
