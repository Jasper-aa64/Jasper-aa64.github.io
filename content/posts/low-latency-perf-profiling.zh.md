---
title: "低时延交易 —— perf：怎么用、看哪些指标"
date: 2026-10-22
slug: "low-latency-perf-profiling"
description: "perf 回答两个问题：时间花在哪个函数、哪条指令上，CPU 是在算还是在等。四个命令各管一件事：perf stat 出总账，record 加 report 找热函数，annotate 找热指令，c2c 查多线程抢缓存行。开工前查权限、符号表和采样事件；IPC、缓存缺失率、分支失败率、热点占比各有一条判读线（出自 Intel 开源的 intel-performance-skills）。最后在一台拿不到硬件计数器的虚拟机上真跑一遍：perf 指到一个单累加器求和，样本落在加法的下一条指令上，拆成四个累加器后快了 3.3 倍。"
summary: "先用 stat 看总账，再用 record 和 report 找到占 98% 样本的函数，最后用 annotate 看到样本全落在加法后面一条指令上：那是一条一环扣一环的加法链，拆成四路就快了 3.3 倍。拿不到硬件计数器时，cpu-clock 采样照样能用；报告里只剩地址，先查符号表和程序所在的路径。"
chapter: 2
categories: [Systems]
tags: [perf, profiling, linux, cpp, hft, low-latency]
toc: true
math: true
---

程序慢，先别猜。perf 是 Linux 内核自带的性能分析工具，能直接回答两个问题：时间花在哪个函数、哪条指令上；CPU 是在算，还是在等数据、等分支、等内核。

下面的输出都是在一台虚拟机上真跑出来的。这台机器拿不到硬件计数器，所以和周期数有关的指标（IPC、缓存缺失、分支失败、c2c）只给命令和判读线，没有实测输出。第 4 部分的每个数字都能在[原始输出](https://github.com/Jasper-aa64/trading-system-notes-study/tree/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B)里找到。

## 1. perf 能回答什么：四个命令各管一件事 {#commands}

perf 常用的就是四个命令，从粗到细：

- **`perf stat`：几秒钟出总账**。跑一遍程序，报耗时、上下文切换、缺页；有硬件计数器时还有周期数、指令数、缓存和分支的缺失次数，用来判断 CPU 是在算还是在等（3.1）。
- **`perf record` + `perf report`：哪个函数热**。record 每隔一小段时间记下程序正在执行的指令地址，一次记录叫一个样本；report 按函数汇总，谁占的样本多，时间就花在谁身上（3.2、4.4）。
- **`perf annotate`：哪条指令热**。把一个函数的样本摊到它的每条汇编指令上（4.5）。
- **`perf c2c`：多线程抢同一条缓存行**。找出被几个核来回抢的缓存行，以及抢的是行里哪个位置（3.3）。

一般先跑 stat，再 record 和 report，最后对热函数用 annotate。拿不准从哪下手，就先跑 stat：它最快，常常就够回答问题了，Intel 的 linux-perf skill 也是这么建议的。多核扩展不上去（线程加倍、吞吐不涨）是另一类问题：用 1 个线程和 N 个线程各 record 一次，比两次的热点排名，名次跳上来的函数再用 c2c 查（3.4）。

## 2. 开工前：权限、符号表和采样事件 {#before}

这三样不对，perf 要么报权限错误，要么报告里只剩一串地址，要么在虚拟机上什么都采不到。

### 2.1 perf_event_paranoid：普通用户能看多少 {#paranoid}

`/proc/sys/kernel/perf_event_paranoid` 是内核给 perf 设的门槛，数越大，没有特权的用户能看的越少（perf_event_open(2) 手册页）：

- `2`：只能测用户态，Linux 4.6 起的默认值；
- `1`：用户态和内核态都能测，4.6 以前的默认值；
- `0`：还能看按 CPU 采的数据，但拿不到原始的 tracepoint 样本；
- `-1`：不限制。

这道门槛只管没有特权的用户。root（有 `CAP_SYS_ADMIN`，或者较新内核上的 `CAP_PERFMON`）不受它限制（内核文档 `Documentation/admin-guide/sysctl/kernel.rst` 的 perf_event_paranoid 一节）。第 4 部分那台机器上是 2，但是用 root 运行，所以没有被挡。调低它要 root 权限，而且对整台机器生效，共用的机器上先问管理员。

### 2.2 符号表和调试信息：报告里为什么只剩一串地址 {#symbols}

report 里的函数名来自二进制里的符号表。看到的是一串十六进制地址，说明 perf 没读到符号表。常见原因有两个，第 4 部分的实测里还碰上了第三个：

- **二进制被 strip 了**。strip 会删掉符号表。同一个演示程序，strip 之前 report 里是 `sum_serial`，strip 之后成了这样：

  ```text
    98.03%  perf_demo.strip  perf_demo.stripped  [.] 0x0000000000000a14
     0.26%  perf_demo.strip  perf_demo.stripped  [.] 0x00000000000009ed
  ```

  分析时用没 strip 的那份。

- **`-g` 管的是源码行，不是函数名**。`-g` 往二进制里加调试信息，annotate 能在汇编上面印出对应的源码行，靠的就是它（见 4.5 的输出）。函数名不靠 `-g`：同一个程序不加 `-g` 编译，只要没 strip，report 里照样有名字：

  ```text
    98.52%  perf_demo_nog  perf_demo_nog      [.] sum_serial
     1.02%  perf_demo_nog  perf_demo_nog      [.] refresh
     0.09%  perf_demo_nog  perf_demo_nog      [.] main
  ```

- **程序放在 `/tmp/perf-` 开头的路径下**。perf 支持 JIT（just-in-time，即时编译）程序：JIT 把它生成的代码的符号写进文本文件 `/tmp/perf-<进程号>.map`，perf 照着解析（perf 文档 `tools/perf/Documentation/jit-interface.txt`）。6.11 之前的 perf 只比前缀，凡是路径以 `/tmp/perf-` 开头的文件都当成这种符号文件来读，二进制当然读不出来（Linux 源码 `tools/perf/util/symbol.c`，v3.10 第 774 行、v6.10 第 1802 行；提交 b0979f008f13 改成只认 `/tmp/perf-<数字>.map`，从 v6.11 起）。第一次实测时我把程序放在 `/tmp/perf-demo-20261022/` 下，没 strip 的二进制在 report 里也全是地址，`perf report -vv` 把它的符号来源标成 `j`，也就是 JIT。换成 `/tmp/demo-perf-20261022/` 就正常了，两次的输出都在[原始输出](https://github.com/Jasper-aa64/trading-system-notes-study/tree/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B/first-run)里。

调用栈是另一回事。`perf record -g` 默认顺着帧指针往回找调用者，编译器省掉帧指针时调用栈会乱，这时改用 `--call-graph dwarf`（perf-record(1) 的 `--call-graph` 一节）。所以第 4 部分编译时加了 `-fno-omit-frame-pointer`。即便这样，4.4 的调用链还是少了一层，原因在那一节。

### 2.3 cpu-clock 和 cycles：按时间采样，还是按硬件计数 {#events}

采样要有个触发条件，常用的是这两个：

- **`cpu-clock` 是软件事件**。由内核里每个 CPU 一个的高精度定时器按时间触发（perf_event_open(2) 对 `PERF_COUNT_SW_CPU_CLOCK` 的说明），不需要硬件支持，虚拟机上也能用。第 4 部分 record 用的是默认频率，每秒 4000 次。
- **`cycles` 是硬件事件**。由 CPU 里的 PMU（performance monitoring unit，性能监控单元）计数。IPC、缓存缺失、分支失败和 c2c 都要用 PMU；精确采样也要它，Intel 上叫 PEBS，AMD 上叫 IBS（perf-list(1)）。
- **虚拟机常常不给 PMU**。这时 `cycles` 拿不到，`cpu-clock` 照样能采。所以先探测再用（4.2）。

## 3. 指标和判读线：数到多少该往哪查 {#thresholds}

这一节的线都出自 Intel 开源的 [intel-performance-skills](https://github.com/intel/intel-performance-skills)（`skills/linux-perf`，提交 3e33aec，MIT 许可）。它们是经验线：越过了，说明值得往那个方向查，不说明一定是那个问题。除了内核态占比和热点占比，这一节的指标都要硬件计数器。第 4 部分的虚拟机拿不到（4.2），所以这里只有命令和判读线，没有实测输出。

### 3.1 perf stat 的四个比例：CPU 在算还是在等 {#stat-ratios}

```bash
perf stat -e cycles,instructions,cache-references,cache-misses,branches,branch-misses -- ./prog
```

$$\text{IPC} = \frac{\text{instructions}}{\text{cycles}}$$

$$\text{缓存缺失率} = \frac{\text{cache-misses}}{\text{cache-references}}$$

$$\text{分支失败率} = \frac{\text{branch-misses}}{\text{branches}}$$

单看一个数（`references/flow-a.md`）：

> - IPC（instructions per cycle，每周期执行的指令数）< 1：CPU 多数时间在等；> 3：算得很满。
> - 缓存缺失率 > 3–5%：偏内存瓶颈。
> - 分支失败率 > 3–5%：偏分支。
> - 内核态时间占 task-clock 的 30% 以上：偏系统调用或 I/O。

几个数合起来判：

> - IPC < 1 且缓存缺失率 > 3%：内存瓶颈，看数据布局、分块、预取（见[内存延迟与带宽专题](/zh/posts/low-latency-memory-latency-bandwidth/)）。
> - IPC < 1 且分支失败率 > 3%：分支问题，消掉分支、改用条件传送（`cmov`）、加预测提示（见 [#7 分支预测](/zh/posts/branch-prediction-branch-optimization/)）。
> - 内核态 > 30%：减少系统调用，批量或异步做 I/O。
> - IPC ≥ 3 且缺失率低：CPU 已经用得很充分，瓶颈在别处。
> - 都不明显：转到 record 和 report。

内核态占比不要硬件计数器：单跑一次 perf stat（不加 `-r`），输出末尾有 `seconds user` 和 `seconds sys` 两行，4.2 的输出里就有。

### 3.2 perf report：热点占多少，下一步做什么 {#report-lines}

`references/flow-b.md` 里的线：

> - 某个函数占 ≥ 20% 的样本：必须进 annotate 看汇编。原文写的是必须，不是可以看。
> - 每个函数都 < 5%：没有单点热点，去看并行和算法。
> - malloc、free、new、delete 占大头：考虑对象池或 arena（见 [#3 内存池与分配器](/zh/posts/hot-path-memory-allocators/)）。
> - 排第一的是内核符号（标 `[k]`）且 > 40%：系统调用或 I/O，用 `strace -c` 数系统调用。
> - 很多小的内核函数（`copy_to_user`、`mutex_lock`）：锁竞争或系统调用开销。
> - 自旋锁、CAS 的包装函数显眼：进 annotate 看是不是 `lock cmpxchg` 扎堆，改法见 [#16 自旋锁](/zh/posts/spinlock-implementation/)（{{% bottleneck-ref "tas-spinlock" %}}）。

annotate 里看什么，Intel 另有一份扫描清单（`references/building-blocks.md`）。和第 4 部分直接相关的是“串行累加”：单条浮点指令占函数样本的 40% 以上，再满足 IPC < 0.5、缓存缺失率 < 2%、源和目的是同一个寄存器这三条中的一条。套这条规则时要留意样本的偏移，见 4.5。

### 3.3 perf c2c：多线程抢同一条缓存行 {#c2c}

```bash
perf c2c record -- ./prog
perf c2c report --stdio
```

- **HITM（hit modified）是什么**。一次读命中了另一个核缓存里改过、还没写回的行（内核头文件 `include/uapi/linux/perf_event.h` 的 `PERF_MEM_SNOOP_HITM`）。这条行得从那个核搬过来，一次 20–100 ns（[速查 2.6](/zh/ref/cpu-memory/#cross-core)，原理见 [MESI 专题](/zh/posts/low-latency-mesi-cache-coherence/)）。c2c 按 HITM 的次数排出争得最凶的缓存行（perf-c2c(1)）。
> - **先看哪些行**。默认只看 Tot Hitm（这一行的 HITM 占全部 HITM 的比例）> 5% 的行（`SKILL.md`）。
> - **真共享还是伪共享**。同一个偏移被多个线程写，是真共享：大家在改同一份数据。同一行里不同偏移被不同线程写，是伪共享：数据本来互不相干，只是挤在了一条缓存行里（`references/flow-c.md`；伪共享见 [#2 内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/)、{{% bottleneck-ref "false-sharing" %}}）。
- **要硬件支持**。Intel 上 c2c 用的是 load latency 和精确 store 两类采样事件（默认是 `cpu/mem-loads,ldlat=30/P` 和 `cpu/mem-stores/P`），AMD 上用 IBS（perf-c2c(1)）。第 4 部分的虚拟机拿不到。

### 3.4 多核扩展不上去：比较 1 核和 N 核的热点排名 {#scaling}

`references/flow-d.md` 的做法：

> - 先确认程序真在用多线程：`ldd ./prog` 看有没有链 libpthread、libgomp、libtbb、libomp，再分别在 1、N/2、N 个核上测吞吐。
> - 1 核和 N 核各 record 一次，比两次的前 15 名函数。满足任一条就算“跳上来”：
>   - 名次升了 3 位以上；
>   - 占比翻倍以上；
>   - 占比涨了 3 个百分点以上；
>   - 1 核时不在前 15，N 核时 ≥ 2%。
> - 对跳上来的函数做 c2c，按结果分五类：
>   - 伪共享：把字段垫开（{{% bottleneck-ref "false-sharing" %}}）；
>   - TAS 自旋：改成先读后抢（见 [#16 自旋锁](/zh/posts/spinlock-implementation/)、{{% bottleneck-ref "tas-spinlock" %}}）；
>   - 统计计数器被多个核写：按 CPU 分桶（{{% bottleneck-ref "shared-counter" %}}）；
>   - 真的在共享数据：原子操作、RCU、更细的锁；
>   - 没有 c2c 信号：回到 report 看计算和分支。
> - 改完重新采样：修掉一个瓶颈，会露出下一个。

排名比较用 cpu-clock 就能做，c2c 那一步要硬件计数器。

### 3.5 annotate 扫描：一个热函数的汇编按 7 条查 {#annotate-scan}

report 指到一个热函数以后，用 annotate 看它的汇编。Intel 把要查的东西列成 7 条（`references/building-blocks.md`），每条后面是对应的[瓶颈卡片](/zh/ref/bottlenecks/)：

> 1. **没向量化**：热指令全是标量浮点（`vaddsd`、`vmulsd` 等），没有一条打包指令，标量占函数样本 > 50%。先找挡住向量化的原因，再加宽（{{% bottleneck-ref "narrow-vector" %}}）。
> 2. **向量太窄**：CPU 支持 AVX2/AVX-512，热路径的打包指令还用 xmm（或 AVX-512 机器上用 ymm），占 > 20%（{{% bottleneck-ref "narrow-vector" %}}）。
> 3. **串行累加**：单条浮点指令占 > 40%，再加上 IPC < 0.5、缺失率 < 2%、源和目的是同一个寄存器这三条中的任一条。样本常记在慢指令的下一条上（skid），照字面数浮点指令会漏：4.5 的实测里，样本 100% 落在 `addss` 后面那条整数 `add` 上，要往前看一条（{{% bottleneck-ref "serial-accumulator" %}}）。
> 4. **水平归约**：乘法后 3–5 条指令内跟着 `shufps`/`addss`/`unpckhps`，合计 > 10%。这是编译器生成的水平归约，按多累加器改写处理（{{% bottleneck-ref "serial-accumulator" %}}）。
> 5. **TAS 自旋**：循环里的 `lock cmpxchg`/`lock xchg` 占 > 10%（{{% bottleneck-ref "tas-spinlock" %}}）。
> 6. **内存压力**：读内存指令合计 > 30%，没有分量相当的计算。没有现成修法，提示去看局部性、缩小工作集、预取；perf stat 的缺失率也高才可信。这一条没有对应的卡片，原理见[内存延迟与带宽专题](/zh/posts/low-latency-memory-latency-bandwidth/)。
> 7. **原子计数器**：`lock add/inc/xadd/sub` 占 > 10%。结果后面紧跟条件跳转，其实是用加法实现的锁，按 TAS 处理（{{% bottleneck-ref "tas-spinlock" %}}）；结果没人用，是统计计数器，按 CPU 分桶（{{% bottleneck-ref "shared-counter" %}}）。

## 4. 真跑一遍：一台没有硬件计数器的虚拟机 {#demo}

结论先说：perf 指到 `sum_serial` 占了 98% 的样本，这些样本全落在它的加法后面一条指令上，那是一条一环扣一环的加法链。拆成四个累加器以后，结果在舍入误差内一致，平均耗时从 0.545 s 降到 0.164 s。这些数只代表这台机器、这组参数。

### 4.1 机器和程序 {#demo-setup}

- 机器：一台拿不到硬件计数器的 x86-64 虚拟机。
- 内核 `3.10.0-1160.119.1.el7.x86_64`；perf `3.10.0-1160.119.1.el7.x86_64.debug`，版本号跟着内核包走。
- 编译器 GCC 12.2.0，参数 `-O2 -g -fno-omit-frame-pointer`。
- 用 root 运行，`perf_event_paranoid` 是 2。

演示程序要有一个明显的热点和一个对照用的冷函数。热点是只用一个累加器的求和：每次加法都要等上一次的结果，浮点加法要 3–5 个周期才出结果（[速查 2.1](/zh/ref/cpu-memory/#latency)），所以只能一个接一个地加。冷函数每轮改写 256 个价格，模拟新行情进来，也让每一轮的和都得重算。4096 个 float 一共 16 KiB，放得进 L1D（一级数据缓存），求和不用等内存。

```cpp
#include <cstdio>
#include <cstring>
#include <vector>

// 冷函数：每轮改写 256 个价格，模拟新行情进来
__attribute__((noinline)) void refresh(float* px, int n, int round) {
    const int start = (round * 256) & (n - 1);  // n 是 2 的幂
    for (int j = 0; j < 256; ++j)
        px[start + j] = 100.0f + 0.01f * static_cast<float>((round + j) & 255);
}

// 热点：只有一个累加器，每次加法都要等上一次加完
__attribute__((noinline)) float sum_serial(const float* a, int n) {
    float s = 0.0f;
    for (int i = 0; i < n; ++i) s += a[i];
    return s;
}

// 修法：四个累加器，四条加法链互不等待
__attribute__((noinline)) float sum_4acc(const float* a, int n) {
    float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, s3 = 0.0f;
    int i = 0;
    for (; i + 4 <= n; i += 4) {
        s0 += a[i];
        s1 += a[i + 1];
        s2 += a[i + 2];
        s3 += a[i + 3];
    }
    for (; i < n; ++i) s0 += a[i];
    return (s0 + s1) + (s2 + s3);
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "1";
    const int n = 4096;  // 16 KiB，放得进 L1D
    const int rounds = 100000;
    std::vector<float> px(n);
    for (int i = 0; i < n; ++i) px[i] = 100.0f + 0.01f * static_cast<float>(i & 255);

    if (std::strcmp(mode, "check") == 0) {  // 同一份数据：两种求和，加一个 double 参考值
        double ref = 0.0;
        for (float x : px) ref += x;
        std::printf("sum_serial = %.4f\nsum_4acc   = %.4f\ndouble ref = %.4f\n",
                    sum_serial(px.data(), n), sum_4acc(px.data(), n), ref);
        return 0;
    }
    const bool fixed = mode[0] == '4';
    double total = 0.0;
    for (int r = 0; r < rounds; ++r) {
        refresh(px.data(), n, r);
        total += fixed ? sum_4acc(px.data(), n) : sum_serial(px.data(), n);
    }
    std::printf("%s: total = %.6e\n", fixed ? "sum_4acc" : "sum_serial", total);
}
```

有三种跑法：`./perf_demo 1` 用单累加器，`./perf_demo 4` 用四个累加器，`./perf_demo check` 在同一份数据上算两种和，再算一个 double 的参考值。所有命令写在一个[脚本](https://github.com/Jasper-aa64/trading-system-notes-study/blob/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B/run.sh)里依次跑完；脚本把每条命令的输出存进文件，下文的命令省掉了这些重定向。

### 4.2 先探测：硬件计数器拿得到吗 {#demo-probe}

```bash
perf stat -e cycles,instructions -- /bin/true
echo "exit code: $?"
```

```text
 Performance counter stats for '/bin/true':

   <not supported>      cycles
   <not supported>      instructions

       0.002029639 seconds time elapsed

       0.000000000 seconds user
       0.002424000 seconds sys


exit code: 0
```

- 两个硬件事件都是 `<not supported>`，perf 的退出码却是 0。脚本要是只看退出码，会以为测到了，所以要逐行检查输出。
- 打印出 0 也要当成拿不到：程序真跑了，周期数和指令数不可能是 0。
- 末尾的 `seconds user` 和 `seconds sys` 只在单跑一次时才有，加 `-r` 时没有。内核态占比就从这两行算（3.1）。

所以下面只能用软件事件：耗时、上下文切换、缺页，加上 cpu-clock 采样。

### 4.3 perf stat -r 10：总账和波动 {#demo-stat}

```bash
perf stat -r 10 ./perf_demo 1
```

```text
 Performance counter stats for './perf_demo 1' (10 runs):

            544.05 msec task-clock                #    0.999 CPUs utilized            ( +-  1.38% )
                 0      context-switches          #    0.001 K/sec                    ( +- 55.28% )
                 0      cpu-migrations            #    0.001 K/sec                    ( +- 40.82% )
               376      page-faults               #    0.691 K/sec                    ( +-  0.03% )
   <not supported>      cycles
   <not supported>      instructions
   <not supported>      branches
   <not supported>      branch-misses

           0.54486 +- 0.00755 seconds time elapsed  ( +-  1.39% )
```

- **单线程，一直在跑**。task-clock 544.05 ms，`0.999 CPUs utilized`：从头到尾占着一个核。上下文切换和 CPU 迁移平均都不到 1 次（perf 按整数打印，所以显示 0）。
- **缺页 376 次，10 次几乎一样**（±0.03%）。
- **硬件事件全是 `<not supported>`**，和 4.2 的探测一致。
- **耗时 0.54486 s ± 0.00755 s**。± 后面不是单次运行之间的波动，是 10 次平均值的标准误：perf 源码（`tools/perf/util/stat.c` 的 `stddev_stats()`）算的是

  $$\text{标准误} = \sqrt{\frac{s^2}{n}}$$

  $s^2$ 是 10 次耗时的样本方差，$n = 10$。单次运行之间的差别要再乘 $\sqrt{10} \approx 3.2$，约 ±4.4%。跑 10 次是为了比较两个版本：差别要明显大于这个波动才算数（4.6）。

### 4.4 perf record 和 perf report：哪个函数热 {#demo-report}

```bash
perf record -e cpu-clock -g -o perf.serial.data ./perf_demo 1
perf report --stdio -i perf.serial.data
```

```text
sum_serial: total = 4.148225e+10
[ perf record: Woken up 1 times to write data ]
[ perf record: Captured and wrote 0.175 MB perf.serial.data (2346 samples) ]
```

report 的开头（往下还有内核和动态链接器的几十行，都在 0.3% 以下）：

```text
# Samples: 2K of event 'cpu-clock'
# Event count (approx.): 586500000
#
# Children      Self  Command    Shared Object      Symbol
# ........  ........  .........  .................  .................................
#
    99.19%     0.00%  perf_demo  libc-2.17.so       [.] __libc_start_main
            |
            ---__libc_start_main
               |
               |--98.12%--sum_serial
               |
                --0.90%--refresh

    98.12%    98.04%  perf_demo  perf_demo          [.] sum_serial
            |
             --98.04%--__libc_start_main
                       sum_serial

     0.90%     0.90%  perf_demo  perf_demo          [.] refresh
            |
            ---__libc_start_main
               refresh

     0.26%     0.00%  perf_demo  [kernel.kallsyms]  [k] page_fault
```

- **样本数和频率**。record 一共记了 2346 个样本。cpu-clock 的 Event count 单位是纳秒：586,500,000 ns ÷ 2346 = 250 µs 一个，也就是默认的每秒 4000 次。
- **Self 和 Children**（perf 文档 `tools/perf/Documentation/callchain-overhead-calculation.txt`）。Self 是样本直接落在这个函数里的比例；Children 再加上它调用的函数。`__libc_start_main` 的 Self 是 0、Children 是 99.19%：它自己不干活，时间全花在它调用的函数里。所有 Self 加起来是 100%，Children 加起来会超过 100%。
- **该看哪个函数**。`sum_serial` 的 Self 是 98.04%，过了“≥ 20% 必须看汇编”那条线，下一步是 annotate（4.5）。`refresh` 只有 0.90%，在 5% 以下，是冷函数，不用管。
- **用户态还是内核态**。`[.]` 是用户态，`[k]` 是内核态。内核里最多的是 `page_fault`，只有 0.26%。

调用链里少了 `main`。明明是 `main` 调的 `sum_serial`，链上却是 `__libc_start_main` 直接到 `sum_serial`。原因是 `sum_serial` 不调用别的函数，是叶子函数，GCC 12 没给它建栈帧：加了 `-fno-omit-frame-pointer`，它开头也没有 `push %rbp`（4.5 的汇编）。按帧指针回溯，从它往上一跳就越过了 `main`。换成按 DWARF 回溯（`perf record -e cpu-clock --call-graph dwarf`），`main` 就回来了：

```text
    99.04%     0.00%  perf_demo  perf_demo            [.] _start
            |
            ---_start
               __libc_start_main
               main
               |
               |--97.93%--sum_serial
               |
                --1.12%--refresh
```

这台机器上按 DWARF 回溯时，report 开头会多打几行 `BFD: Dwarf Error: ... only handles version 2, 3 and 4`：GCC 12 默认生成 DWARF 5 格式的调试信息，机器上的老 binutils 读不了。这几行不影响调用链，上面就是同一次的输出。

### 4.5 perf annotate：哪条指令热 {#demo-annotate}

```bash
perf annotate --stdio -i perf.serial.data sum_serial
```

截取函数本身那一段：

```text
 Percent |	Source code & Disassembly of perf_demo for cpu-clock (2300 samples, percent: local period)
----------------------------------------------------------------------------------------------------------
         :            __attribute__((noinline)) float sum_serial(const float* a, int n) {
         :                float s = 0.0f;
         :                for (int i = 0; i < n; ++i) s += a[i];
    0.00 :   400a00:       test   %esi,%esi
    0.00 :   400a02:       jle    400a20 <sum_serial(float const*, int)+0x20>
    0.00 :   400a04:       movslq %esi,%rsi
         :                float s = 0.0f;
    0.00 :   400a07:       pxor   %xmm0,%xmm0
    0.00 :   400a0b:       lea    (%rdi,%rsi,4),%rax
    0.00 :   400a0f:       nop
         :                for (int i = 0; i < n; ++i) s += a[i];
    0.00 :   400a10:       addss  (%rdi),%xmm0
  100.00 :   400a14:       add    $0x4,%rdi
    0.00 :   400a18:       cmp    %rax,%rdi
    0.00 :   400a1b:       jne    400a10 <sum_serial(float const*, int)+0x10>
    0.00 :   400a1d:       ret
    0.00 :   400a1e:       xchg   %ax,%ax
         :                float s = 0.0f;
    0.00 :   400a20:       pxor   %xmm0,%xmm0
         :                return s;
         :            }
    0.00 :   400a24:       ret
```

- **样本记在加法的下一条上**。这个函数的 2300 个样本，100% 记在 `add $0x4,%rdi` 上。真正要等的是它前面那条 `addss (%rdi),%xmm0`：`s += a[i]` 编出来就是它，每次都要用上一次算出的 `%xmm0`。
- **这叫 skid**。不用精确采样时，记下的指令地址可以往后偏（perf_event_open(2) 里 `precise_ip` 为 0 的说明）。这里偏了一条：循环卡在等 `addss` 出结果，样本记在它后面。精确采样要硬件计数器，这台机器用不了。所以读 annotate 时，热点可能在标出来的那条，也可能在它前面一条。
- **照字面套规则会漏**。3.2 里“串行累加”那条要单条浮点指令占 40% 以上，这里 100% 记在整数指令 `add` 上，套规则查不出来。往前看一条才对得上。
- **源码行从 `-g` 来**。汇编上面印的 `for (int i = 0; i < n; ++i) s += a[i];` 是调试信息给的；不加 `-g` 编译，同样的位置只有汇编（[原始输出](https://github.com/Jasper-aa64/trading-system-notes-study/tree/main/02-%E5%B8%B8%E8%A7%81%E6%80%A7%E8%83%BD%E7%93%B6%E9%A2%88%E4%B8%8E%E4%BC%98%E5%8C%96%E6%96%B9%E5%90%91/00-%E8%A1%A5-perf-%E5%AE%9E%E6%B5%8B)里的 `extra/annotate_nog.txt`）。

慢的原因在源码里就能看出来：只有一个累加器，每次加法都要等上一次的结果。解决办法是拆成几条互不相干的加法链。

### 4.6 拆成四个累加器：先核结果，再比耗时 {#demo-fix}

`sum_4acc` 把数轮流分给四个累加器，四条加法链互不等待，最后再合起来（代码在 4.1）。加法的顺序变了，浮点结果会差一点，所以先核结果：

```bash
./perf_demo check
```

```text
sum_serial = 414822.4688
sum_4acc   = 414822.3750
double ref = 414822.4000
```

414822 在 $2^{18}$ 和 $2^{19}$ 之间，float 的尾数有 23 位，所以这个量级上相邻两个 float 相差 $2^{18-23} = 2^{-5} = 0.03125$。单累加器比参考值多 0.0688，约 2 个间隔；四累加器少 0.025，不到 1 个间隔。两种和都在舍入误差之内，差别来自加法的顺序：浮点加法不满足结合律。

再跑 10 次：

```bash
perf stat -r 10 ./perf_demo 4
```

```text
 Performance counter stats for './perf_demo 4' (10 runs):

            163.27 msec task-clock                #    0.995 CPUs utilized            ( +-  5.71% )
                 0      context-switches          #    0.003 K/sec                    ( +- 33.33% )
                 0      cpu-migrations            #    0.002 K/sec                    ( +- 50.92% )
               376      page-faults               #    0.002 M/sec                    ( +-  0.03% )
   <not supported>      cycles
   <not supported>      instructions
   <not supported>      branches
   <not supported>      branch-misses

           0.16404 +- 0.00933 seconds time elapsed  ( +-  5.69% )
```

| 版本 | 平均耗时 | 标准误 |
|---|---|---|
| 单累加器 | 0.54486 s | 0.00755 s（1.39%） |
| 四累加器 | 0.16404 s | 0.00933 s（5.69%） |

- **快了约 3.3 倍**（0.54486 ÷ 0.16404 ≈ 3.32）。两个均值差 0.38 s，是标准误的 40 倍以上，远大于波动。
- **相对波动变大，绝对值差不多**。标准误从 1.39% 涨到 5.69%，绝对值却都在 10 ms 以内（7.55 ms 和 9.33 ms）。程序变快了，同样大小的波动占比就大。
- **编译器把四个累加器装进了一个寄存器**。GCC 12 在 `-O2` 下把四个累加器放进一个 xmm 寄存器的四格，循环里只剩一条 `addps`，一次加 4 个数（objdump 的输出）：

  ```text
  400a53:	movups (%rdi,%rcx,1),%xmm0
  400a57:	addps  %xmm0,%xmm1
  ```

  加法链还是一条，但每一环加 4 个数。

再 record 一次：

```text
# Children      Self  Command    Shared Object        Symbol
# ........  ........  .........  ...................  .......................................
#
    97.64%     0.00%  perf_demo  libc-2.17.so         [.] __libc_start_main
    93.17%    93.17%  perf_demo  perf_demo            [.] sum_4acc
     4.10%     4.10%  perf_demo  perf_demo            [.] refresh
```

`refresh` 的代码没动，占比从 0.90% 涨到 4.10%：总时间短了，没改的部分占比就上来了，不过还在 5% 以下。`sum_4acc` 仍然过了 20% 的线，照规矩还要再 annotate 一次。原始输出里的 `out/annotate_4acc.txt` 显示，73.87% 的样本记在 `addps` 后面的 `cmp` 上，热点还是这条加法链。

## 应用 {#in-practice}

4.6 把一个累加器拆成四个，就是“{{% bottleneck-ref "serial-accumulator" "plain" %}}”这张卡片的一次实测。卡片写了在 perf 里看到什么、怎么改、怎么验证；修法那一条的加速倍数是原文的数字，这台虚拟机上测到的是 4.6 的约 3.3 倍。

{{% bottleneck "serial-accumulator" %}}
