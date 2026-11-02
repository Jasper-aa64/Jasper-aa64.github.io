---
title: "交易系统笔记 #20：用 TSC 测延迟"
date: 2026-11-02
slug: "tsc-latency-measurement"
description: "想知道一段代码花了多久，最直接的办法是在两头各读一次 TSC。可 TSC 数的是按固定频率走的时间，不是核心跑了多少周期；rdtsc 不等前面的指令做完，测短区间要加栅栏，栅栏又让测量本身变重；rdtscp 顺带告诉你读数时在哪个核，跨核比较读数靠的是各核 TSC 同步。热路径上只记 tick，换算和输出交给别的线程。"
summary: "TSC 读到的是什么、什么时候读到、在哪个核上读到，以及在热路径上打点该怎么记。"
chapter: 1
categories: [Systems]
tags: [cpp, tsc, rdtsc, rdtscp, latency, measurement, hft, low-latency]
toc: true
math: true
---

想知道从收到一条行情到发出订单花了多久，最直接的办法是在两头各读一次时间，再相减。`clock_gettime` 读一次约 20–30 ns，可交易系统热路径上一段代码常常只有几百 ns，计时本身就占了一成。所以低延迟系统通常直接读 CPU 里的 TSC：一条指令，约 10 ns。直接读硬件计数器，就要自己回答三个问题：读到的数代表什么，它是不是在你写的那个位置读的，以及这个数怎么换算成纳秒。第 1 部分讲前两个和读数时在哪个核上，换算留到第 2 部分。

## 1. 读 TSC：读到的是什么，什么时候读到

### 1.1 TSC（time stamp counter）：每个核里一个按固定频率走的计数器

TSC 是每个逻辑核里的一个 64 位计数器，开机时清零，之后一直往上加。它在<a href="/maps/hardware-map.zh.html" target="_blank" rel="noopener">硬件地图</a>上没有单独的框，就是核里的一个寄存器。

早期的 CPU 上，TSC 跟着核心时钟走：降频时它变慢，进深度睡眠时它停下，这样的计数器没法拿来计时。现在的 CPU 都是 invariant TSC（不变的 TSC）：按一个固定频率走，不管核心在降频、睡眠还是 Turbo。这个频率通常接近 CPU 的标称频率，例如本文用的这台机器是 3.593 GHz。Linux 下 `/proc/cpuinfo` 的 flags 里有 `constant_tsc` 和 `nonstop_tsc`，就说明是这种。

所以 **TSC 数的是时间，不是核心实际跑了多少个周期**。核心开着 Turbo 跑在 4.5 GHz、TSC 按 3.0 GHz 走时，100 个 TSC tick 是 33 ns，这段时间里核心实际跑了 150 个周期。想数核心周期，要用 perf 的 `cycles` 事件，它来自性能计数器，不是 TSC。

64 位按 3.6 GHz 加，要约 160 年才会回绕，不用担心溢出。同一颗 CPU 上的各个核从同一次复位开始计数，读数是同步的，Linux 开机时还会检查一遍，不同步就打出 `tsc: Marking TSC unstable`，改用别的时钟源。1.4 会用到这一点。

### 1.2 rdtsc：读一次约 10 ns，但读数不一定一个 tick 一个 tick 地走

读 TSC 的指令是 `rdtsc`，它把低 32 位放进 EAX、高 32 位放进 EDX，拼起来就是 64 位读数：

```cpp
inline uint64_t rdtsc() noexcept {
    unsigned int lo, hi;
    __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
    return (uint64_t(hi) << 32) | lo;
}
```

编译器自带的 `__rdtsc()`（头文件 `<x86intrin.h>`）做的是同一件事，编译器还知道它改了哪些寄存器，优先用它。

一次 `rdtsc` 大约 20–40 个周期，6–12 ns。`clock_gettime` 在用户态（vDSO）里其实也是读 TSC，只是多了一次函数调用和换算成纳秒的乘法、移位，所以要 20–30 ns。直接读 TSC 省下的就是这两样，换算挪到事后去做。

读数的精度却不一定是一个 tick（这台机器上约 0.28 ns）。在本文这台 AMD 机器上连续读，读数大约每 10 ns 才真正跳一次，一次加 36；同一个 10 ns 窗口里再读，只比上一次多 1，保证读数不重复。连读两次 `rdtsc` 的差几乎总是 36，也就是正好一跳，所以只能说读一次不超过约 10 ns。**比 10–20 ns 还短的单次测量，读出来的主要是量化误差**，要测短代码，就重复跑很多次再看分布。

### 1.3 乱序执行：rdtsc 不等前面的指令做完

只读两次相减还不够，因为 CPU 是乱序执行的（硬件地图上“重命名 + ROB”那一格）。`rdtsc` 不会等它前面的指令做完才读，它后面的指令也可能在它之前就开始执行。于是下面这段：

```cpp
uint64_t t0 = __rdtsc();
int r = parse(msg);        // 被测的代码
uint64_t t1 = __rdtsc();
```

两头的边界都是模糊的：`parse` 的前几条指令可能在读 `t0` 之前就开始了，读 `t1` 时 `parse` 的最后几条可能还没做完。被测代码只有几十 ns 时，量出来的数可能比真实的还短。

修法是用栅栏把边界钉住。`lfence` 的意思是：等它前面的指令都做完，它后面的指令才能开始。`rdtscp` 是 `rdtsc` 的变体，会等前面的指令都执行完、前面的读都完成才读，但不拦后面的指令。于是开始和结束各写成这样：

```cpp
inline uint64_t tsc_begin() {      // 开始打点：等前面的指令做完再读
    _mm_lfence();
    uint64_t t = __rdtsc();
    _mm_lfence();                  // 后面的指令不许提前开始
    return t;
}

inline uint64_t tsc_end() {        // 结束打点：rdtscp 等前面的指令做完才读
    unsigned aux;
    uint64_t t = __rdtscp(&aux);
    _mm_lfence();                  // 后面的指令不许提前开始
    return t;
}
```

`lfence` 的这个效果是 Intel 规定的。AMD 上，要操作系统打开一个开关，`lfence` 才会这样等，较新的 Linux 和 Windows 默认都打开了；老系统上 AMD 建议用 `mfence`。如果还要求前面的写都已经对别的核可见，Intel 手册给的写法是 `mfence; lfence; rdtsc`。

栅栏是有代价的。这台机器上，带栅栏的两次读数之差从 1 跳变成 2 跳，约 20 ns；而且栅栏挡住了被测代码和前后代码的重叠，测到的已经不完全是平时跑的样子。**栅栏让边界准了，代价是测量本身更重，被测代码也不再和前后重叠。**所以测几十 ns 的短代码（微基准）时加栅栏；在线上热路径里打点，测的是几 µs 的整段，十几 ns 的边界误差可以接受，通常就用不带栅栏的 `rdtsc`。

编译器也会挪代码。被测代码的结果如果没人用，编译器可能把整段删掉，或者把不依赖内存的计算挪到读数外面。微基准里要让结果被用到，比如写进一个 `volatile` 变量。

### 1.4 rdtscp 和跨核：读数的同时知道自己在哪个核

`rdtscp` 除了读 TSC，还把一个叫 `IA32_TSC_AUX` 的寄存器读进 ECX，就是上面代码里的 `aux`。Linux 把每个核的这个寄存器设成“NUMA 节点号 × 4096 + 核号”，vDSO 里的 `getcpu` 也是靠它。开始和结束两次读到的 `aux` 不一样，就说明线程中途被挪到了别的核：这段时间里含一次迁移（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 1.1），两个核的读数也未必完全对得上，这个样本应该扔掉或单独标出来。热线程按 #1 绑死在一个核上，就不会出现这种情况。

跨核比较读数还有一种更常见的场景：生产者在 2 号核往队列里写消息时打一个时间戳，消费者在 4 号核取出时再打一个，相减得到消息在队列里待了多久。这能成立，靠的是 1.1 说的同一台机器上各核 TSC 同步。虚拟机里，虚拟机监控程序可能给 TSC 加偏移，或者在虚拟 CPU 挪到别的物理核时出偏差，这时跨核相减就不可靠了。两台机器之间的 TSC 更是毫无关系，没法相减。

要确认一台机器支持这些，看 CPUID：`0x80000001` 的 EDX 第 27 位是 `rdtscp`，`0x80000007` 的 EDX 第 8 位是 invariant TSC。Linux 上直接 `grep -o 'rdtscp\|constant_tsc\|nonstop_tsc' /proc/cpuinfo` 更方便。

### 1.5 热路径打点：先记 tick，换算和输出交给别的线程

打点本身会给热路径加时间：读一次 TSC 约 10 ns，记下来又要一次写内存或者入队。所以热路径上只做这两步，把差值以 tick 为单位存进预先分配好的数组，或者交给 [#4](/zh/posts/lock-free-queue-logger-micro-batching/) 的异步日志，换算、格式化、写文件都在别的线程上做。一种常见的写法是两个宏：

```cpp
#define START_MEASURE(TAG) const auto TAG = Common::rdtsc()

#define END_MEASURE(TAG, LOGGER)                                                  \
    do {                                                                          \
        const auto end = Common::rdtsc();                                         \
        LOGGER.log("% RDTSC " #TAG " %\n", Common::getCurrentTimeStr(&time_str_), \
                   (end - TAG));                                                  \
    } while (false)
```

`LOGGER.log` 只是把参数放进一个无锁队列，日志线程再去格式化。日志里记的 `end - TAG` 是 tick 数，不是纳秒。每加一个打点，热路径就多几十 ns，所以线上只在关键的几处打，或者按比例抽样。

区间用 TSC 测，适合同一个线程里的一段代码。可一笔交易从收到行情到发出订单，要经过行情线程、策略线程、下单线程，常常还跨进程，想知道每一段各花了多久，就要在每个环节记一个**绝对时间戳**，事后按订单把各环节的记录拼起来。这种记录叫 tick-to-trade（TTT），常见的写法是：

```cpp
#define TTT_MEASURE(TAG, LOGGER)                                                  \
    do {                                                                          \
        const auto TAG = Common::getCurrentNanos();                               \
        LOGGER.log("% TTT " #TAG " %\n", Common::getCurrentTimeStr(&time_str_), TAG); \
    } while (false)
```

`getCurrentNanos()` 返回的是从 1970 年起的纳秒数，也就是系统时钟。同一台机器上的几个进程其实也能共用 TSC，但要和交易所回报里的时间、另一台机器上的记录对上，就得用各机器都对过时的系统时钟（用 PTP 同步）。**同一个线程里的区间用 TSC，跨组件、跨机器拼时间线用统一的绝对时钟。**

单次测量的数字意义不大：同一段代码，这一次 300 ns，下一次碰上缓存未命中就是 2 µs。要看的是很多次测量的分布：中位数、99 分位、最大值。这是下一节交易系统性能衡量的内容。
