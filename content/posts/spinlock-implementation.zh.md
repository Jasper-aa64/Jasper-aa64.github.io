---
title: "交易系统笔记 #16：自旋锁"
date: 2026-10-21
slug: "spinlock-implementation"
description: "临界区（加锁保护的那段代码）跑一遍只要几十 ns 时，std::mutex 抢不到锁就进内核睡（futex），一睡一醒要几 µs。自旋锁不睡，但只在持锁的线程一直在跑时才划算。最简单的 CAS 循环每试一次都要独占锁所在的缓存行，等锁的核把行抢来抢去，持锁的核放锁也要排队；先读后抢（TTAS）让等的核各读各的副本；循环里加 PAUSE，锁放开那一刻不用冲刷流水线；放锁时一群核同时冲，用指数退避错开。"
summary: "自旋锁快不快，看等锁的核在干什么：每次都读改写，就把锁所在的行抢来抢去；先读后抢、循环里加 PAUSE、抢输了退一步，等的时候才几乎不打扰持锁的核。"
chapter: 1
categories: [Systems]
tags: [cpp, spinlock, atomics, futex, mesi, pause, hft, low-latency]
toc: true
math: true
---

改订单簿的一档、拷一份行情快照，这类代码要加锁保护，叫临界区（`lock()` 和 `unlock()` 之间的那一段），跑一遍只要几十 ns：改一档是找到那一档、加上数量，十来条指令；拷一份 10 档快照是复制 5 条缓存行左右；数据都在本核缓存里时，各要几 ns 到十几 ns，再加上加锁、放锁各一次原子操作（各约 2–6 ns）。有别的线程也在抢时，锁所在的缓存行、刚被别的核改过的数据行，都要先从别的核那里搬过来，每条约 20–100 ns，跑一遍会涨到一两百 ns。用 `std::mutex` 护着它，没抢到锁的线程会被挂起，锁放开后再被叫醒，一睡一醒要几 µs，是临界区本身的 10 倍到上百倍。自旋锁（spinlock）的办法是不睡：抢不到就留在原地反复看，锁一放开立刻接手。

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

这一来一回要付两次系统调用（各约 0.1–0.5 µs），外加等的线程切出去、再切回来两次线程切换（各约 1–5 µs，还要算上缓存被别的线程冲掉的代价）。等的那个核要是已经进了省电状态，叫醒它还要更久（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 的 2.2）。合起来，从放锁到等的线程真正跑起来，约 2–10 µs。可临界区跑一遍只要几十 ns，也就是说，锁几十 ns 后就放开了，睡下去的线程却要再过几 µs 才能接手，晚了 10 倍到上百倍。不睡，原地盯着锁，锁一放开就能接手，这就是自旋锁存在的理由。

### 1.2 自旋的前提：持锁的线程一直在跑

转比睡划算，是因为锁很快就会放开。这要两个条件：持锁的线程一直在跑，临界区很短。有一条不成立，自旋就成了白烧 CPU。

第一条坏在调度上。持锁的线程要是被换下 CPU（时间片用完、被别的线程抢占、等 I/O），锁就跟着它一起停住，等的核只能干转，一转就是一个时间片，毫秒级，比睡一次贵得多。更糟的是等的线程和持锁的线程挤在同一个核上：等的一方占着核在转，持锁的一方排不上，锁就放不开，直到时间片用完。所以用户态的自旋锁总和绑核一起用：每个会碰这把锁的线程各绑一个隔离出来的核（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 的 1.2），操作系统就没有理由把持锁的线程换下去。

第二条坏在临界区里做了慢事。写日志、`malloc`、系统调用、查数据库、等网络，这些要么几 µs 起步，要么可能阻塞，持锁时间跟着变长、变得没法预测，等的核就一直陪着转。锁里只放改数据的那几行：要查的、要算的先在锁外做完，进锁只写结果。

两条做不到，就用会睡的 `std::mutex`，或者折中：先转一小会儿，还拿不到再睡。glibc 的自适应互斥锁（`PTHREAD_MUTEX_ADAPTIVE_NP`）就是这样做的，不过 `std::mutex` 默认不是这种类型。

### 1.3 最简单的自旋锁：一个原子变量，循环 CAS

不睡，就是把 `SleepingMutex` 里“进内核睡”那一步换成“再试一次”：

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

`compare_exchange_weak(expected, 1, …)` 的意思是：`locked_` 等于 `expected`（0）就改成 1，返回 true；不等就把 `locked_` 的当前值写进 `expected`，返回 false。所以失败以后 `expected` 变成了 1，下一轮之前要改回 0。`weak` 允许偶尔“明明相等也报失败”，ARM 上用一对独占读写实现时会这样。外面本来就有循环，用 `weak` 就够了；只判断一次、失败就走的地方才用 `strong`。

内存序管的是临界区里的读写不能跑到锁外面去（[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 的 1.5）。`lock()` 成功的那次 CAS 用 acquire：临界区里的读写不能提到拿锁之前，这样才看得到上一个持锁者写的东西。`unlock()` 的写用 release：临界区里的读写不能拖到放锁之后。两者配成一对，上一个持锁者在临界区里写的，下一个持锁者一定看得到。失败的那几次 CAS 什么也没拿到，用 relaxed 就行。拿锁时不需要 release，它管的是拿锁之前的读写，和临界区无关。

用 `exchange` 写更短：`while (locked_.exchange(1, std::memory_order_acquire)) {}`，把 1 写进去、返回旧值，旧值是 0 就说明锁是自己拿到的。这就是测试并设置（test-and-set，TAS）。两种写法每试一次都是一次读改写（read-modify-write，RMW），毛病也一样。

### 1.4 读改写抢行：等的核每试一次都要把行抢过来

`locked_` 住在一条缓存行里。在<a href="/maps/hardware-map.zh.html" target="_blank" rel="noopener">硬件地图</a>上，这条行可以在好几个核的 L1D 里各有一份副本，规矩是右边 MESI 那个框写的：谁要写，先让别人的副本作废（[MESI 专题](/zh/posts/low-latency-mesi-cache-coherence/)）。

读改写是一种写。x86 上 CAS 编成 `lock cmpxchg`，不管比较成不成功，它都要先把这条行拿到本核、独占（MESI 的 M 或 E），比较失败时把原值写回去。ARM 上换成 `casal` 这类指令，同样是对这一条行的读改写。所以 3 个核在等锁时，每个核每转一圈都要把行从别的核那里抢过来一次，每抢一次约 20–100 ns（[速查 2.6](/zh/ref/cpu-memory/#cross-core)）。这条行就在等锁的核之间来回搬，一刻不停。

搬行本身只是浪费，坏的是它挡住了持锁的核。持锁的核放锁时要写 `locked_`，同样得先把行抢回来，它得排在等锁的核那一串读改写后面：锁早该放了，放锁的那次写却迟迟落不下去。被保护的数据要是和 `locked_` 在同一条行里，临界区每改一次数据也要抢一次，临界区本身都被拖长。后一个问题好治，给锁单独一条行就行（`alignas(64)`，[#6](/zh/posts/alignment-layout-cache-dram-geometry/)）；前一个问题要改的是等的方式。

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

`while (locked_.load(...))` 这个循环只有两三条指令：读、比较、跳回去。乱序执行的核不会等一圈做完再开始下一圈，它按分支预测（[#7](/zh/posts/branch-prediction-branch-optimization/)）一直往下猜“还要再转”，把后面几十圈的读都先发出去。ROB 里于是排着一长串对 `locked_` 的读，都还没退休（retire，按程序顺序确认结果）。

锁放开的那一刻，这一串读出了问题。x86 规定读和读之间不能乱序，程序里靠后的读不能比靠前的读看到更旧的值。可这些读是提前发出去的，不少早就读到了旧值 `true`。这时持锁核的失效请求进来，这个核没法再保证它们守着这条规矩，只好把从那里开始的指令全部扔掉、重新执行。这叫内存序冲刷（memory ordering machine clear），和分支猜错一样要冲刷整条流水线，也是几十个周期，偏偏落在锁刚放开、最该快的时候。循环出口本身还是一次分支猜错，一共付两次。在硬件地图上，这件事横跨两个框：失效请求顺着灰色虚线进 invalidate queue，撞上 ROB 里还没退休的那一串读。

`pause` 指令就是为这种循环准备的。它让下一圈晚一点开始，流水线里同时只有一两次读，锁放开时没有一长串要扔，这次冲刷就省掉了。它还有两个好处：转得慢了，核的功耗降下来；这个核开着超线程（SMT）的话，兄弟线程能用上执行资源（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 的 2.1）。

一条 `pause` 停多久，各代差很多，约 10–150 个周期：Intel 从 Skylake 起，从约 10 个周期拉长到约 140 个周期。所以“转 1000 次就去睡”这种按次数定的预算，换一颗 CPU 时间可能差 10 倍，要限时就按时间算。ARM 上没有 `pause`：`yield` 是给多线程核的提示，在很多核上等于空操作，有的库改用 `isb` 拖一小段时间；真要在等的时候省电，就用 `wfe` 让核睡到这条行被别人写。可移植的写法是包一个小函数：

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

TTAS 让持锁期间安静了，放锁那一刻还是乱的。锁放开后，3 个等的核都读到 `false`，几乎同时回到第一行去 `exchange`。只有第一个成功，另外 2 个失败，可每次 `exchange` 都要把行抢到自己那里，失败的也一样。等的核越多，这一阵读改写越长；新主人的临界区要是很短，它放锁的那次写就得排在这一串后面。所以每次交接的时间大约随等锁的核数 $N$ 线性增长：

$$t_{\text{交接}} \approx N \times t_{\text{搬行}}, \qquad t_{\text{搬行}} \approx 20\text{–}100\ \text{ns}$$

4 个核在等，一次交接就是约 80–400 ns，比临界区本身还长。

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

每输一次，下次多歇一倍（指数退避），各个核回来的时间就错开了，同时冲的少了。实际的实现还会给歇的长度加一点随机，免得几个核步调一致，又撞在一起。代价是锁放开时可能大家都在歇，锁空在那里没人拿。上限也要按时间想：64 次 `pause`，在 `pause` 约 10 个周期的机器上约 0.2 µs，在约 140 个周期的机器上约 3 µs，差了十几倍。

等的核一多，退避也只是缓解。根本的办法是让每个等的核在自己的那条行上转、按先来后到一个一个交接，放锁时只惊动下一个，排队锁（票据锁、MCS 锁）就是这么做的。不过在交易系统里，一把锁经常有好几个核在抢，本身就说明设计该改了：改成只有一个线程写，别的线程把要改的东西通过队列交给它（[#4](/zh/posts/lock-free-queue-logger-micro-batching/)、[#5](/zh/posts/spmc-shared-memory-broadcast-ring/)），比把锁写得再好都管用。

## 应用 {#in-practice}

1.3 到 1.5 节的读改写抢行和 TTAS，在实际优化里对应“{{% bottleneck-ref "tas-spinlock" "plain" %}}”这张卡片；1.1 节讲的线程睡下、再被叫醒的代价，是“{{% bottleneck-ref "thundering-herd" "plain" %}}”这张卡片的原理。两张卡片都写了在 perf 里看到什么、怎么改、怎么验证。

{{% bottleneck "tas-spinlock" %}}

{{% bottleneck "thundering-herd" %}}
