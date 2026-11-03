---
title: "交易系统笔记 #20：用 TSC 测延迟"
date: 2026-11-02
slug: "tsc-latency-measurement"
description: "想知道一段代码花了多久，最直接的办法是在两头各读一次 TSC。可 TSC 数的是按固定频率走的时间，不是核心跑了多少周期；rdtsc 不等前面的指令做完，测短区间要加栅栏，栅栏又让测量本身变重；rdtscp 顺带告诉你读数时在哪个核，跨核比较读数靠的是各核 TSC 同步。热路径上只记 tick，换算和输出交给别的线程。"
summary: "TSC 读到的是什么、什么时候读到、在哪个核上读到，热路径上打点该怎么记，以及 tick 怎么换算成 ns：频率从哪来、怎么自己校准。"
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

早期的 CPU 上，TSC 跟着核心时钟走：降频时它变慢，进深度睡眠时它停下，这样的计数器没法拿来计时。现在的 CPU 都是 invariant TSC（不变的 TSC）：按一个固定频率走，不管核心在降频、睡眠还是 Turbo。这个频率通常接近 CPU 的标称频率，例如 3.593 GHz。Linux 下 `/proc/cpuinfo` 的 flags 里有 `constant_tsc` 和 `nonstop_tsc`，就说明是这种。

所以 **TSC 数的是时间，不是核心实际跑了多少个周期**。核心开着 Turbo 跑在 4.5 GHz、TSC 按 3.0 GHz 走时，100 个 TSC tick 是 33 ns，这段时间里核心实际跑了 150 个周期。想数核心周期，要用 perf 的 `cycles` 事件，它来自性能计数器，不是 TSC。

**频率变了，tick 怎么变**，要看这段时间由谁决定：

- **纯计算**：要跑多少个周期由指令和依赖决定，不随频率变。核心变快，花的时间就短，TSC 读到的 tick 跟着变少。例如 480 个周期：核心 2.4 GHz 时花 200 ns，按 3.6 GHz 走的 TSC 读到 720 tick；核心升到 3.6 GHz 时约 133 ns，读到 480 tick。
- **等内存**：时间由内存延迟决定，不随核心频率变。tick 基本不变，核心在这段时间里空转的周期反而变多。
- **所以 tick 变少不一定是代码变快了，也可能只是核心频率变高了**。比较两次测量，先把频率固定住（关掉省电和 Turbo，或者绑在不降频的核上）。

64 位按 3.6 GHz 加，要约 160 年才会回绕，不用担心溢出。同一颗 CPU 上的各个核从同一次复位开始计数，读数是同步的，Linux 开机时还会检查一遍，不同步就打出 `tsc: Marking TSC unstable`，改用别的时钟源。1.4 会用到这一点。

### 1.2 rdtsc：读一次 6–12 ns，AMD 上读数约 10 ns 才跳一次

- 测一段代码多快，最直接的办法是两头各读一次 TSC，再相减。
- 这个差可不可信，取决于两件事：读一次要多久，读数能分辨多短的时间。

1. **怎么读**

   - `rdtsc` 指令把 64 位读数分两半放：低 32 位在 EAX，高 32 位在 EDX。这是 32 位年代留下来的，那时一个寄存器装不下 64 位。

   ```cpp
   inline uint64_t rdtsc() noexcept {
       unsigned int lo, hi;
       __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
       return (uint64_t(hi) << 32) | lo;
   }
   ```

   - 自己写汇编时，`volatile` 不能漏。漏了，编译器会把它当成结果固定的计算，把两次读合成一次：实测 Clang 18 `-O2` 把“读两次相减”编成了返回 0。
   - **优先用编译器自带的 `__rdtsc()`**（头文件 `<x86intrin.h>`）：编出来是同一条指令，不会被合并。

2. **为什么不用 `clock_gettime`**

   - `clock_gettime` 在用户态（vDSO）里读的其实也是 TSC。
   - 但它每次多一次函数调用，还要用乘法和移位换算成纳秒，一次 20–30 ns。
   - `rdtsc` 只有读这一步，约 20–40 个周期，6–12 ns。
   - **所以热路径上只记 tick，换算留到事后。**

3. **读数是一级一级跳的**

   - 按频率算，一个 tick 是 1 / 3.593 GHz ≈ 0.28 ns。
   - 但在 AMD Zen 系列（Ryzen、EPYC）上实测，读数约每 10 ns 才跳一次，一次加 36（36 × 0.28 ≈ 10 ns）。Intel 上一般看不到这种固定台阶，连读几次的差各不相同。手上的机器是哪种，连读几次就知道。
   - 同一个 10 ns 里再读，只比上一次多 1。这个 1 只是为了让读数不重复，不代表真过了 0.28 ns。
   - **台阶是计数器自己的更新方式，和 `rdtsc` 读得快慢无关**：就算读一次不花时间，读到的也是台阶。3.593 GHz ÷ 36 ≈ 100 MHz，看起来读数是跟着一个约 100 MHz 的参考时钟、每拍补 36（从数字推出来的，没有查到文档）。
   - **为什么不每个 tick 跳一次**：
     - **要求**：TSC 在所有核上要一样快、读数对得上，核降频、睡眠时也不能停（1.1）。
     - **核自己的时钟靠不住**：它会变频，睡眠时会停。
     - **另起一个 3.6 GHz 的时钟也不划算**：每个核都要一直开着它，费电，各核之间还要对齐到 0.28 ns。
     - **实际做法**：TSC 跟着一个慢、但一直开着的参考时钟走，每来一拍加一个固定的数（这里是 36），一次补够这一拍的 tick。
     - **Intel 也是这个思路**：手册在 CPUID 的 `0x15` 叶里写明“TSC 频率 = 晶振频率 × 一个比值”。Intel 读出来看不到台阶，说明它在两拍之间做了细分，怎么细分没有公开。
   - **能不能更细**：单次读 TSC，分辨率就是一跳，这是硬件定的，软件改不了。要更细只有两条路：
     - **不看单次**：重复跑再除，或者多次取平均（下面第 4 块），分辨的是平均值。
     - **不用 TSC，改数核心周期**：用性能计数器（PMU）的“核没停的周期”事件，`rdpmc` 读，每个周期加 1。代价是要内核先开好计数器、允许用户态读，虚拟机里常常拿不到；而且它数的是周期，不是时间，核一变频就换算不成纳秒（1.1）。测几个周期的指令延迟，用的就是这条路。

   <a href="/images/tsc-latency-measurement/rdtsc-steps.zh.svg" target="_blank" rel="noopener"><img src="/images/tsc-latency-measurement/rdtsc-steps.zh.svg" alt="横轴是真实时间 0–40 ns，纵轴是 rdtsc 读数。理想情况读数每 0.28 ns 加 1，是一条斜线；实际是台阶，约每 10 ns 跳一次、一次加 36。情况 A：一段 5 ns 的代码落在一个台阶里，两次读数是 1036 和 1037，差 1，换算成 0.28 ns，少算。情况 B：同样 5 ns，中间碰上一次跳变，读数 1072 和 1108，差 36，换算成 10 ns，多算。" loading="lazy" decoding="async"></a>

4. **对测量的影响**

   - 量不准 `rdtsc` 自己：连读两次的差几乎总是 36，正好一跳，只能看出读一次不超过约 10 ns。
   - 任何一次测量，读数差都只有两种可能：区间里碰上了 n 次跳变，或者 n + 1 次（见上图的情况 A、B）。所以**单次测量最多差一跳，约 10 ns，和被测代码多长无关**。碰上几次跳变取决于起点落在台阶的哪个位置，这是随机的，多测几次取平均，多算和少算会互相抵掉，平均值没有偏差。
   - 要看的是这 10 ns 占被测时间多少：测 1 µs 的代码，单次最多差 1%；测 100 ns，单次最多差 10%，比如分不出 100 ns 和 105 ns，要比这种差别只能靠多次平均或重复跑（见下面两种办法）；测 5 ns，误差比代码本身还大。**所以 100 ns 上下的代码不看单次读数，比 10–20 ns 还短的单次测量，读出来的主要是量化误差。**
   - 换到没有台阶的 Intel 上，单次也好不了多少：不加栅栏时乱序会让读数提前或推后十几个周期，加了栅栏读一次又更重（1.3），边界本来就有约 10 ns 的不确定。**所以约 10 ns 是单次打点的分辨率，不只是 AMD 的问题**；线上打点测的是几百 ns 到几 µs 的整段，这点误差只占几个百分点。
   - 读数里还多了读指令自己：两次读之间什么都不放，差也有约 36。这部分大致固定，测之前先空测一次，把这个底数减掉。
   - 测短代码，有两种办法：
     - 让代码在两次读之间重复跑 1000 次，再除以 1000。误差还是一跳，但摊到每次只剩约 0.01 ns。
     - 测很多次，取**平均值，不取中位数**。起点落在一级台阶的哪个位置是随机的，5 ns 的代码有一半的次数碰上跳变，平均下来 (1 + 36) / 2 = 18.5 tick ≈ 5.2 ns，接近真实值。中位数会被其中一种结果带偏：3 ns 的代码只有 30% 的次数碰上跳变，中位数是 1 tick，读成 0.28 ns。
   - **基准测试报出的 52.6 ns、52.5 ns 这种小数点后的差别，就是靠第一种办法来的**：工具（例如 Google Benchmark）把代码循环跑几十万到上百万次，总时间除以次数，一跳的误差摊到每次只剩十万分之一 ns 左右。这时结果准不准，取决于每轮之间的波动（频率、缓存、代码对齐），不再取决于计时分辨率；0.1 ns 的差别是不是真的，要多跑几轮，看区间是否重叠。
   - 中位数、p99 这类分位数，留给比一跳长得多的区间，比如一次完整的处理要几百 ns 到几 µs，这时量化误差只占几个百分点。
   - 乱序执行带来的误差是另一回事，见 1.3。

### 1.3 乱序执行：rdtsc 不等前面的指令做完

1. **边界为什么模糊**
   - **乱序执行**：CPU 不按代码顺序一条条做完（硬件地图上“重命名 + ROB”那一格）。`rdtsc` 不等它前面的指令做完就读，它后面的指令也可能比它先开始。
   - 只读两次相减，看这段：

   ```cpp
   uint64_t t0 = __rdtsc();
   int r = parse(msg);        // 被测的代码
   uint64_t t1 = __rdtsc();
   ```

   - **开头**：`parse` 的前几条指令可能在读 `t0` 之前就开始了。
   - **结尾**：读 `t1` 时，`parse` 的最后几条可能还没做完。
   - **结果**：两头都往里缩，被测代码只有几十 ns 时，量出来的数比真实的短。

2. **修法：用栅栏把边界钉住**
   - **`lfence`**：等它前面的指令都做完，它后面的指令才能开始。
   - **`rdtscp`**：`rdtsc` 的变体，等前面的指令都执行完、前面的读都完成才读，但不拦后面的指令。
   - 开始和结束各写成这样：

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

   - **开始打点**：第一道 `lfence` 让前面的代码先做完，第二道不让被测代码在读数之前开始。
   - **结束打点**：`rdtscp` 等被测代码做完才读，后面的 `lfence` 不让后面的代码提前开始。
   - **`rdtscp` 只管前面一头**：它等前面的指令做完才读，但不拦后面的指令，后面的代码可能在它读数之前就开始执行。所以它后面还要一道 `lfence`。
   - **后面这道什么时候要紧**：连续打点时，一次读数既是上一段的终点，又是下一段的起点（`t0`、`t1`、`t2` 依次读），两头都得钉住。只测一段、后面不再测时，它影响很小，但加上不吃亏，所以统一这样写。
   - **开始打点也能用 `rdtscp`**：把开头的 `lfence` + `rdtsc` 换成一条 `rdtscp`，效果一样，都是等前面的指令做完再读，后面那道 `lfence` 照样要。好处是顺便拿到 `aux`，可以查迁移（1.4 的代码就是这么写的）。

3. **Intel 和 AMD 的差别**
   - **Intel**：`lfence` 的这个效果是手册规定的。
   - **AMD**：要操作系统打开一个开关，`lfence` 才会这样等。较新的 Linux 和 Windows 默认都打开了，老系统上 AMD 建议用 `mfence`。
   - **还要前面的写对别的核可见**：Intel 手册给的写法是 `mfence; lfence; rdtsc`。

4. **栅栏的代价与取舍**
   - **额外开销**：实测空测时，带栅栏的两次读数之差从 1 跳变成 2 跳，约 20 ns，比不带栅栏多一跳。
   - **挡住重叠**：栅栏让被测代码不能和前后的代码重叠执行，测到的已经不完全是平时跑的样子。
   - **栅栏让边界准了，代价是测量本身更重，被测代码也不再和前后重叠**。
   - **怎么选**：
     - **微基准**：测几十 ns 的短代码，边界误差和代码本身一样大，加栅栏。
     - **线上热路径**：测的是几 µs 的整段，十几 ns 的边界误差可以接受，通常用不带栅栏的 `rdtsc`。

5. **编译器也会挪代码**
   - **整段删掉**：被测代码的结果没人用，编译器可能把它删了。
   - **挪到外面**：不依赖内存的计算，可能被挪到两次读数之外。
   - **修法**：让结果被用到，比如写进一个 `volatile` 变量。

### 1.4 rdtscp 和跨核：读数的同时知道自己在哪个核

1. **`aux`：顺便读出在哪个核**
   - **读了什么**：`rdtscp` 除了读 TSC，还把 `IA32_TSC_AUX` 寄存器读进 ECX，就是上面代码里的 `aux`。
   - **里面是什么**：Linux 把每个核的这个寄存器设成“NUMA 节点号 × 4096 + 核号”，vDSO 里的 `getcpu` 也是靠它。拆开就是：

   ```cpp
   unsigned core = aux & 0xfff;   // 低 12 位：核号
   unsigned node = aux >> 12;     // 其余位：NUMA 节点号
   ```

2. **用它查迁移：两头的 `aux` 不一样就扔掉**
   - **怎么查**：开始和结束都用 `rdtscp`，比两次读到的 `aux`。1.3 的 `tsc_begin` 用的是 `rdtsc`，读不到 `aux`，要查迁移时开始那次也换成 `rdtscp`：

   ```cpp
   unsigned a0, a1;
   uint64_t t0 = __rdtscp(&a0);   // 开始：rdtscp 自己等前面做完
   _mm_lfence();                  // 被测代码不许提前开始
   int r = parse(msg);
   uint64_t t1 = __rdtscp(&a1);   // 结束
   _mm_lfence();
   bool migrated = (a0 != a1);    // 中途换过核
   ```

   - **不一样说明什么**：线程中途被挪到了别的核，这段时间里含一次迁移（[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 1.1），两个核的读数也未必完全对得上。
   - **怎么处理**：这个样本扔掉，或者单独标出来。
   - **热线程**：按 #1 绑死在一个核上，就不会出现这种情况。

3. **跨核相减：同一台机器上可以**
   - **场景**：生产者在 2 号核往队列里写消息时打一个时间戳，消费者在 4 号核取出时再打一个，相减得到消息在队列里待了多久。
   - **为什么能减**：靠 1.1 说的同一台机器上各核的 TSC 是同步的。
   - **要留意**：同步也不是分毫不差。排队时间很短时，差值可能是很小的负数。这说明排队时间短到在同步误差以内，不是程序出错。

4. **不能相减的情况：同步这个前提不成立**
   - **前提**：跨核相减成立，全靠各核的 TSC 同步（1.1）。下面几种情况，这个前提不成立。
   - **这台机器上 TSC 本身没同步**：固件（BIOS）写过 TSC，或者多路服务器的几个插槽没对齐。Linux 开机检查出来会打出 `tsc: Marking TSC unstable`（1.1），`dmesg` 里能看到，这时跨核相减就不能信。
   - **虚拟机**：虚拟机监控程序可能给 TSC 加偏移，或者在虚拟 CPU 挪到别的物理核时出偏差，跨核相减就不可靠了。
   - **两台机器**：根本不是同一套计数器，谈不上同步，没法相减。要跨机器对时间，用 PTP 对过时的系统时钟（1.5 第 4 块）。

5. **确认机器支持**
   - **CPUID**：`0x80000001` 的 EDX 第 27 位是 `rdtscp`，`0x80000007` 的 EDX 第 8 位是 invariant TSC。
   - **Linux 上更方便**：直接看 `/proc/cpuinfo` 里有没有这三个标志。

   ```bash
   grep -o 'rdtscp\|constant_tsc\|nonstop_tsc' /proc/cpuinfo | sort -u
   ```

### 1.5 热路径打点：先记 tick，换算和输出交给别的线程

1. **打点本身也花时间**
   - **花在哪**：读一次 TSC 约 10 ns，记下来又要一次写内存或者入队。
   - **热路径上只做这两步**：把差值以 tick 为单位存进预先分配好的数组，或者交给 [#4](/zh/posts/lock-free-queue-logger-micro-batching/) 的异步日志。
   - **其余的挪走**：换算成纳秒、格式化、写文件，都在别的线程上做。

2. **常见写法：一对宏**

   ```cpp
   #define START_MEASURE(TAG) const auto TAG = Common::rdtsc()

   #define END_MEASURE(TAG, LOGGER)                       \
       do {                                               \
           const auto end = Common::rdtsc();              \
           LOGGER.log("RDTSC " #TAG " %\n", (end - TAG)); \
       } while (false)
   ```

   - **`START_MEASURE`**：读一次 TSC，存进一个以 `TAG` 命名的局部变量。
   - **`END_MEASURE`**：再读一次，把差值交给日志。
   - **`LOGGER.log`**：只把参数放进一个无锁队列，日志线程再去格式化。
   - **单位**：日志里记的 `end - TAG` 是 tick 数，不是纳秒。
   - **别在这里拼时间字符串**：在 `END_MEASURE` 里顺手调一个“取当前时间字符串”的函数，等于把格式化又放回了热路径。要记时间，就记原始的数，交给日志线程去转。
   - **代价**：每加一个打点，热路径就多几十 ns。所以线上只在关键的几处打，或者按比例抽样。

3. **跨线程、跨机器：记绝对时间戳**
   - **TSC 区间管不到的**：它适合同一个线程里的一段代码。一笔交易从收到行情到发出订单，要经过行情线程、策略线程、下单线程，常常还跨进程。
   - **做法**：每个环节记一个**绝对时间戳**，事后按订单把各环节的记录拼起来，就知道每一段各花了多久。这种记录叫 tick-to-trade（TTT）：

   ```cpp
   #define TTT_MEASURE(TAG, LOGGER)                    \
       do {                                            \
           const auto TAG = Common::getCurrentNanos(); \
           LOGGER.log("TTT " #TAG " %\n", TAG);        \
       } while (false)
   ```

   - **`getCurrentNanos()`**：返回从 1970 年起的纳秒数，也就是系统时钟。

4. **TSC 还是系统时钟**
   - **同一台机器的几个进程**：其实也能共用 TSC，各核的 TSC 是同步的（1.1）。
   - **要和交易所回报、别的机器对上**：TSC 对不上，得用各机器都对过时的系统时钟（用 PTP 同步）。
   - **同一个线程里的区间用 TSC，跨组件、跨机器拼时间线用统一的绝对时钟**。

5. **看分布，不看单次**
   - **单次意义不大**：同一段代码，这一次 300 ns，下一次碰上缓存未命中就是 2 µs。
   - **要看的**：很多次测量的分布，也就是中位数、99 分位、最大值。这是下一节交易系统性能衡量的内容。

## 2. 换算和校准：tick 怎么变成 ns

- 第 1 部分记下的都是 tick。要变成 ns，得知道 TSC 一秒走多少个 tick，也就是 TSC 频率。
- 这个数错了，每个时间都按同一个比例错，而且看不出来。所以先讲换算本身，再讲频率从哪来、怎么自己量、量完放在哪。

### 2.1 换算：tick 除以 TSC 频率

1. **式子**

   $$t_{\text{ns}} = \frac{\Delta \text{tick}}{f_{\text{TSC}}} \times 10^9$$

   - **只缺一个数**：读数差 $\Delta \text{tick}$ 已经有了，缺的是 TSC 频率 $f_{\text{TSC}}$。
   - **频率错多少，时间就错多少**：按 3.0 GHz 算、实际是 3.593 GHz，每个时间都多算约 20%（3.593 ÷ 3.0 ≈ 1.198）。这种错不会报错，数看起来照样合理。
   - **在哪算**：热路径只记 tick（1.5），换算在日志线程里做，或者事后做。

2. **整数先乘后除会溢出**
   - **常见写法**：`ticks * 1000000000ULL / freq`，先乘 $10^9$ 再除，保住精度。
   - **溢出点**：乘出来的数要放进 64 位，所以 $\Delta \text{tick}$ 最多约 $1.8 \times 10^{10}$（$2^{64} \div 10^9$）。按 3.6 GHz 算，区间超过约 5 秒就溢出，结果变成一个小得离谱的数，也不报错。
   - **改法**：用 double 算，double 有 15–16 位有效数字，ns 级够用；或者先算好 `ns_per_tick = 1e9 / freq`，换算时乘一次。

### 2.2 频率从哪来：先查，查不到再量

1. **内核开机时量过一遍**
   - **怎么看**：`dmesg | grep -i tsc`，会有一行 `tsc: Refined TSC clocksource calibration: … MHz`，或者 `tsc: Detected … MHz processor`。
   - **怎么来的**：开机时内核拿别的时钟（HPET、PIT 这类）对着 TSC 量了一段。
   - **怎么用**：部署时读一次，写进配置。

2. **Intel：CPUID 0x15**
   - **给的是什么**：晶振频率（ECX）和一个比值（EBX ÷ EAX）。TSC 频率 = 晶振频率 × 比值，就是 1.2 第 3 块说的“慢晶振加每拍补固定数”。
   - **可能查不到**：有的型号 ECX 是 0，不报晶振频率；虚拟机里整个叶子可能都是 0（实测云上一台 Intel 虚拟机，0x15、0x16 都返回 0）。

   ```cpp
   uint64_t freq_from_cpuid_15() {
       unsigned eax, ebx, ecx, edx;
       if (!__get_cpuid(0x15, &eax, &ebx, &ecx, &edx)) return 0;   // 没有这个叶子（多数 AMD）
       if (eax == 0 || ebx == 0 || ecx == 0) return 0;              // 没报比值或晶振频率（虚拟机里常见）
       return uint64_t(ecx) * ebx / eax;
   }
   ```

   - **`__get_cpuid`**：先查这个叶子存不存在，不存在返回 0，不会读到垃圾。
   - **查不到就返回 0**：让调用方知道要换别的办法，不要退回一个写死的默认值。

3. **别用 CPUID 0x16**
   - **它是什么**：处理器的标称基础频率（MHz），是给人看的，Intel 没保证它等于 TSC 频率。
   - **AMD 上没有**：AMD 没有定义这个叶子，查不到。
   - **后果**：拿它当 TSC 频率、查不到再退回 3.0 GHz 的默认值，在 3.593 GHz 的机器上，每个时间都多算约 20%。

4. **都拿不到就自己量**：对着 `steady_clock` 校准，见 2.3。

### 2.3 自己校准：对着 steady_clock 量一段

1. **做法**
   - **两头各记一对**：开始时记下 TSC 读数和 `steady_clock` 时间，等一段时间 $T$，结束时再记一对。
   - **算频率**：

   $$f_{\text{TSC}} = \frac{\text{tick}_1 - \text{tick}_0}{t_1 - t_0}$$

2. **误差从哪来：两头的配对误差**
   - **配对误差**：TSC 和 `steady_clock` 不是同一瞬间读的，中间隔着一次 `now()`（20–30 ns，1.2），偶尔还会被打断。记作 $\delta$。
   - **摊到基线上**：两头各有一个 $\delta$，频率的相对误差大约是

   $$\frac{\Delta f}{f} \approx \frac{\delta_0 + \delta_1}{T}$$

   - **例子**：两头合计 60 ns，基线 100 ms，相对误差 $60 \div 10^8 = 6 \times 10^{-7}$，也就是 0.6 ppm。拿这个频率换算一段 1 ms 的区间，只差 0.6 ns。
   - **所以基线越长越准**。100 ms 级的基线，误差已经远小于 1.2 的一跳（约 10 ns）。

3. **把配对误差压小：两次 TSC 夹一次 now()**

   ```cpp
   tsc_arr[0] = rdtsc();
   for (int i = 0; i < try_times; ++i) {          // try_times = 5
       ns_arr[i] = std::chrono::steady_clock::now();
       tsc_arr[i + 1] = rdtsc();
   }

   auto min_tsc_diff = tsc_arr[1] - tsc_arr[0];
   auto ave_tsc = average(tsc_arr[0], tsc_arr[1]);
   auto ns = ns_arr[0];
   for (int i = 1; i < try_times; ++i) {
       auto tsc_diff = tsc_arr[i + 1] - tsc_arr[i];
       if (tsc_diff < min_tsc_diff) {               // 找夹得最紧的一组
           min_tsc_diff = tsc_diff;
           ave_tsc = average(tsc_arr[i], tsc_arr[i + 1]);
           ns = ns_arr[i];
       }
   }
   return {ave_tsc, ns};
   ```

   - **夹住**：`now()` 读到的那一刻，一定落在它前后两次 `rdtsc` 之间。取两次读数的中点当作配对的 TSC，误差不超过夹缝的一半。
   - **连夹 5 次、取最紧的**：夹缝最小的那次，说明中间没被中断或调度打断。
   - **夹缝多宽**：一次 `now()` 加一次 `rdtsc`，最紧的约 30–40 ns，所以中点误差不到 20 ns。

4. **对着哪个时钟量**
   - **`steady_clock`**：单调，不会往回跳（Linux 上是 `CLOCK_MONOTONIC`）。
   - **`system_clock` 会跳**：NTP 校时、有人改系统时间，它会整段往前或往后跳。校准的那 100 ms 里跳一下，频率就错了。
   - **`high_resolution_clock` 别用**：在 libstdc++（GCC 默认的标准库）里它就是 `system_clock`（实测 `std::is_same` 为真），在 libc++ 里又是 `steady_clock`。同一行代码，换个标准库意思就变了。
   - **还要更干净**：NTP 也会微调 `steady_clock` 走的快慢，只调快慢、不跳。要连这个也避开，用 `clock_gettime(CLOCK_MONOTONIC_RAW, …)`。

### 2.4 两种计时器：校准放在什么时候

1. **TSCTimer：第一次取结果时才校准**
   - **启动时记一对**：`base_point` 是静态变量，程序启动时就用 2.3 的夹法记下一对（TSC，`steady_clock`）。
   - **第一次 `get()` 再记一对**：两对一减，算出 `cycle_to_ns_scale`（每个 tick 多少 ns），存进一个原子变量，之后不再算。

   ```cpp
   static void calibrate() {
       auto [end_tsc, end_time] = TimerHelper::get_tsc_ns_pair();
       auto& [begin_tsc, begin_time] = TimerHelper::base_point;
       std::chrono::nanoseconds duration = end_time - begin_time;
       auto scale = static_cast<double>(duration.count()) / static_cast<double>(end_tsc - begin_tsc);
       double expected = 0.;
       cycle_to_ns_scale.compare_exchange_strong(expected, scale, std::memory_order_relaxed);
   }
   ```

   - **`compare_exchange_strong`**：几个线程同时第一次 `get()`，只有第一个写进去的算数，其余的用它的结果。
   - **好处**：`start` / `end` 只读 TSC，不碰别的时钟；基线是“程序启动到第一次 `get()`”，通常很长，误差很小。
   - **代价**：第一次 `get()` 要做 5 次 `now()`，约 100–150 ns，落在热路径上就是一次尖刺。程序刚启动就调 `get()`，基线又太短。
   - **怎么用**：启动阶段等一会儿（比如 100 ms 以上），主动调一次 `get()`，把校准做在热路径之外。

2. **TSCTimer：一次读数同时结束一段、开始下一段**

   ```cpp
   timer.start(1);
   some_work(20);
   timer.start(0, timer.stop, 1);   // 一次读数：开始区间 0，同时结束区间 1
   some_work(30);
   timer.end(0);
   ```

   - **累计**：每个区间一个槽，`end` 时做 `cycles_arr_[i] += tsc - last_tsc_arr_[i]`，同一个区间测多次会加在一起。
   - **一次读数切换**：就是 1.3 说的连续打点，一个读数既是区间 1 的终点，又是区间 0 的起点。少读一次，两段之间也没有缝。
   - **没加栅栏**：`start` / `end` 里只有 `rdtsc` 或 `rdtscp`，适合 ms 级的长区间；测几十 ns 的代码，要按 1.3 加 `lfence`。

3. **HardwareTimer：构造时就校准好**
   - **构造时做完**：先用 CPUID 查有没有 TSC、`rdtscp`、invariant TSC，再校准 5 次、每次 100 ms，取中位数。构造一次要 0.5 秒以上，所以只能放在启动阶段。
   - **每次校准查迁移**：两头都用 `rdtscp`，`aux` 不一样就重来（1.4）。
   - **取中位数**：5 次里有一两次被打断，中位数不受影响。
   - **单次校准可以这样写**：

   ```cpp
   // 对着 steady_clock 量 baseline，返回 TSC 频率（Hz）；连续 max_retry 次都换过核就返回 0
   double calibrate(std::chrono::milliseconds baseline, int max_retry = 5) {
       using clock = std::chrono::steady_clock;
       for (int attempt = 0; attempt < max_retry; ++attempt) {
           unsigned a0, a1;
           auto c0 = clock::now();
           uint64_t t0 = __rdtscp(&a0);
           std::this_thread::sleep_for(baseline);
           uint64_t t1 = __rdtscp(&a1);
           auto c1 = clock::now();
           if (a0 != a1) continue;                          // 中途换过核：这次不算，重来
           double ns = std::chrono::duration<double, std::nano>(c1 - c0).count();
           return double(t1 - t0) * 1e9 / ns;               // double 算，不会溢出
       }
       return 0;                                            // 一直在换核：先绑核再校准
   }
   ```

   - **对着 `steady_clock`**：理由见 2.3 第 4 块。
   - **用 double 算**：避开 2.1 的整数溢出。
   - **重来要有上限**：线程没绑核、机器又忙时，可能一直被挪，没有上限的重来就会一直转。超过几次就返回 0，让调用方先绑核（[#1](/zh/posts/cpu-affinity-core-isolation-numa/)）再校准。
   - **查不到频率就报错**：按 2.2，不要退回写死的默认值。

4. **两种怎么选**
   - **TSCTimer**：校准晚、开销小，适合嵌在程序里随时测几段。
   - **HardwareTimer**：启动时付 0.5 秒，换来能检查的校准结果（查迁移、取中位数），适合先确认机器和频率再开工。
   - **两种都把校准放在热路径之外，热路径上只读 TSC**。

### 2.5 虚拟机里的 TSC

1. **读数被改过**
   - **偏移**：虚拟机监控程序给每台虚拟机的 TSC 加一个偏移，让它看起来从虚拟机开机时算起。
   - **缩放**：虚拟机迁到 TSC 频率不同的物理机上，读数要按比例缩放。CPU 支持 TSC scaling 时由硬件做；不支持时只能把 `rdtsc` 拦下来模拟，一次读要进出虚拟机，慢到 µs 级。

2. **频率不好拿**
   - **CPUID 可能全是 0**：0x15、0x16 都查不到（2.2）。
   - **内核知道**：虚拟机里的内核从虚拟机监控程序拿到频率，`dmesg` 里照样有 `tsc: Detected … MHz`。
   - **所以在虚拟机里**：先看内核的值，再按 2.3 自己量一遍核对。

3. **时钟源可能被换掉**
   - **怎么看**：`cat /sys/devices/system/clocksource/clocksource0/current_clocksource`，虚拟机里常见 `tsc` 或 `kvm-clock`。
   - **被判不可靠时**：内核退回 HPET 这类时钟源，`clock_gettime` 每次都要访问芯片组，从 20–30 ns 涨到约 0.5–1.5 µs（[#19](/zh/posts/scheduling-priority-inversion-kernel-tuning/) 4.1）。
   - **`tsc=reliable`**：让内核跳过对 TSC 的核对，不会因为一次抖动就把它判掉（#19 4.2）。确定 TSC 没问题时才加。
   - **对校准的影响**：`rdtsc` 照样能读，变的是 `steady_clock`：对照的时钟每次读要 µs 级，配对误差跟着变大，基线要相应拉长。
