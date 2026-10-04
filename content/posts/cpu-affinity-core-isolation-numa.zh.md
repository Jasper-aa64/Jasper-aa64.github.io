---
title: "交易系统笔记 #1:CPU 隔离与 NUMA"
date: 2026-09-09
slug: "cpu-affinity-core-isolation-numa"
description: "怎么在一台多核服务器上清出一个 CPU 核,让一个热线程独占它:为什么要这么做,isolcpus / nohz_full / rcu_nocbs 各自压掉哪一类噪声,怎么冻结超线程和频率,以及 NUMA 的 first-touch 陷阱。"
summary: "低延迟系统的敌人是抖动,不是平均值。目标是让热线程成为它那个核上唯一会运行的东西:绑核消掉迁移代价,隔离参数一层层赶走时钟中断、RCU 和设备中断,关超线程、锁频率去掉核自身的波动,share-nothing 让 NUMA 问题根本不出现。"
categories: [Systems]
tags: [linux, low-latency, cpu-affinity, numa, isolcpus, nohz-full, hft, jitter, c-states]
toc: true
homepage: false
---

想象行情剧烈波动的那 100 微秒。你的策略线程被抢占了一次,或者它的 L1/L2 被别的任务冲掉了一次,这一下就是 30 微秒。你的订单进交易所撮合队列时排在了所有人后面,成交价差了一个 tick——这就是逆向选择在吃你的利润。在延迟敏感的交易系统里,敌人**不是平均延迟,而是尾延迟和抖动**:平均 2 微秒、偶尔冲到 50 微秒,不如稳稳的 5 微秒。

所以这篇里的所有手段只服务一个目标:**让热线程成为它那个物理核上唯一会运行的东西,并且一直保持下去。** 第 1 部分把别人从这个核上清走——绑核和隔离;第 2 部分处理核自己给你使绊子——超线程、C-state 和频率;第 3 部分转向内存,因为在多路服务器上,不是所有内存都一样近。

---

## 1. 绑核与隔离:把核清出来

### 1.1 线程为什么会被挪走,挪一次要付什么

Linux 调度器(CFS,6.6 起是 EEVDF)默认会为了负载均衡在核之间迁移线程:它看到 3 号核空着、8 号核上有两个可运行任务,就挪一个到 3 号核。从"所有核公平使用"的角度看这没错;对你的热线程来说,这一次迁移就是灾难。

为什么是灾难:**L1、L2 和 TLB 都是每个物理核私有的。** 你的线程在 7 号核上跑了一阵,订单簿的热数据、策略代码的指令、地址翻译条目,全都在 7 号核的缓存里。调度器把它挪到 12 号核,而 12 号核的 L1/L2 里一样都没有。于是接下来几万条指令,每次访存都是缺失:从 L3 拿(约 40 个周期)或者从内存拿(约 200–300 个周期)。实测下来,一次迁移换来的是**几十微秒的退化窗口**,这段时间线程主要在重新暖缓存,真正的活只能干平时的几分之一。如果迁移还跨了插槽,情况更糟——数据变成了"远端内存",此后每次访问都要多付约 50%,而且是永久的(第 3 部分)。

绑核(affinity)就是告诉调度器:**这个线程只在这个核上跑,别的地方都不行。** 它把迁移代价直接降到零。

但要看清楚:**绑核只解决"线程被挪走",不解决"核上还有别人"。** 你把线程钉在 3 号核,3 号核的周期性时钟中断、软中断、内核线程、其他用户进程照样都在,照样按时抢占你。绑核是**必要但不充分**的,后面还得有一整套隔离。

![迁移的代价:每个核私有的缓存不会跟着线程走](/images/cpu-affinity/migration-cost.jpg)

### 1.2 隔离:一层一层赶走噪声

想象一台没做任何配置的机器上的 3 号核,数一数它每秒被打断多少次:你的热线程想跑,别的用户线程可能被调度上来,内核线程(`kworker`、`ksoftirqd`)有活要干,1000 Hz 的周期时钟中断雷打不动,网卡每收一个包就是一次硬中断,硬中断又会触发软中断,RCU 的回调也需要一个核来执行。

隔离就是把这些噪声源一层一层关掉。每一层对应一类具体的噪声:

**`isolcpus=3`(内核启动参数)**——把 3 号核从调度器的通用池里拿出来。调度器不再主动往上面放任务,被唤醒的任务默认也不会落到那里。历史上它还会把这个核移出调度域,不参与负载均衡。

这里有一个**几乎人人都会踩的误解**:`isolcpus` 不是一堵权限墙。它**不会阻止你把线程显式绑到这个核上**,它只让*自动的、默认的*调度行为绕开这个核。标准用法恰恰是:用 `isolcpus` 清出 3–7 号核(没有东西会自动落上去),再由你的程序用 affinity API 按名字把热线程一个个放上去——一个线程一个核,独占。所以:`isolcpus=2-7` 之后,`taskset -c 4 ./app` 还能在 4 号核上跑吗?**能**——本来就该这么用。

**`nohz_full=3`(内核启动参数)**——关掉周期时钟中断。平时内核每秒要用时钟中断敲每个核 100 到 1000 次,做时间片统计和各种记账。`nohz_full` 让这个核在**只有一个可运行任务时**停掉这个 tick。

重点是**只有一个**。你一旦在这个核上放第二个可运行线程,内核没法用一个 tick 给两个线程记账,tick 立刻就回来了。所以 `nohz_full` 和"一个线程独占一个核"是焊在一起的。

**`rcu_nocbs=3`(内核启动参数)**——RCU 是内核里大量使用的同步机制,它的回收阶段有回调要在某个核上执行。`rcu_nocbs` 把 3 号核的回调交给其他核上专门的 `rcuop/N` 线程。`nohz_full` 会自动把它覆盖的核加进 `rcu_nocbs`,所以两者通常一起出现。

**`irqaffinity=0,1`(内核启动参数)+ `/proc/irq/N/smp_affinity`**——设备中断默认送到哪些核。把默认掩码设成只有 0、1 号核,再对具体的 IRQ 精细绑定,网卡收包的中断就落在打杂的核上,而不是你的热核上。(中断绑定值得单独写一篇。)

**还有一类东西关不掉,只能饿死它们。** 名字里带核号的 per-CPU 内核线程——`ksoftirqd/3`、`kworker/3`、`migration/3`——是每个核固有的,`isolcpus` 删不掉。但它们只在有活的时候才醒:`ksoftirqd/3` 处理 3 号核上的软中断,你把网卡中断引走之后,3 号核不再产生网络软中断,它就一直睡着;`kworker/3` 处理派到 3 号核的工作项,你把 RCU 回调和中断都挪走之后,派给它的活趋近于零,它也不会醒。**思路不是"杀掉线程",而是"断掉它的活源,让它永远睡着"。**

在这种布局里,所有没被隔离的核(通常是 0 号,有时加上 1 号)叫**打杂核**(housekeeping core)。系统的噪声并没有消失,你只是**把它们全部赶到了打杂核上**,换来热核上的绝对安静。

**最后还剩一点消不掉的残余。** 就算上面全配好,`nohz_full` 核上仍然有大约 1 Hz 的残余时钟中断;和你共享地址空间的其他线程改了地址空间(`munmap`/`mprotect`),你会收到 TLB shootdown 的核间中断(IPI);偶尔还有调度 IPI;有 NMI watchdog(用 `nmi_watchdog=0` 关掉);还有 SMI——固件层面的系统管理中断,操作系统完全看不见,每次几十到几百微秒,只能在 BIOS 里处理。这些残余的大小和频率,就是你用 `cyclictest` / `oslat` 测出来的"地板"。

### 1.3 四种机制,"隔离强度"到底指什么

`isolcpus` 是**内核级**的启动参数,隔离**强**(真的把核从调度池里拿走)。代价是静态的——改它要重启。

`cpuset`(cgroup 的一个子系统)也是内核级、强隔离,但是**动态的**:运行时就能划出一组 CPU 加内存节点,把进程移进移出。它有一个 `isolcpus` 没有的能力——**连内存节点也能划**,在 NUMA 场景下很有用。内核文档现在更推荐 `cpuset` + `nohz_full`,但生产上 `isolcpus` 仍然用得很多,因为它简单、可靠、启动就生效。

`taskset`(进程级命令)和 `pthread_setaffinity_np` / `sched_setaffinity`(线程级 API)提供的是**弱**隔离,"弱"的准确意思是:它们只约束"**这个**进程/线程只能在这些核上跑",**不阻止别的线程也跑到这些核上**。真正的隔离得先由 `isolcpus` 或 `cpuset` 把核清出来。

`sched_setaffinity` 和 `pthread_setaffinity_np` 的区别:前者是原始系统调用,用 TID 指定线程(传 `0` 表示自己);后者是 glibc 的封装,内部调用前者,用 `pthread_t` 句柄指定线程。`_np` 后缀是 "non-portable"(glibc 扩展,不是 POSIX)。

### 1.4 一个"绑核并启动线程"的封装里的四个坑

常见的"绑核再开线程"封装,删减后是这样:

```cpp
inline auto setThreadCore(int core_id) noexcept {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(core_id, &cpuset);
    return (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) == 0);
}

template<typename T, typename... A>
inline auto createAndStartThread(int core_id, const std::string &name, T &&func, A &&... args) noexcept {
    auto t = new std::thread([&]() {
        if (core_id >= 0 && !setThreadCore(core_id)) { /* 打印错误;exit(EXIT_FAILURE) */ }
        std::forward<T>(func)((std::forward<A>(args))...);
    });
    std::this_thread::sleep_for(1s);   // 赌"affinity 已生效 + 线程已经迁过去"
    return t;
}
```

`setThreadCore` 没问题:`cpu_set_t` 是一个位掩码,`CPU_ZERO`/`CPU_SET` 是操作它的宏,对 `pthread_self()` 调用就是"把自己钉到 core_id 上",`noexcept` 加 `bool` 返回是热路径风格。问题出在外层:

**坑 1——悬空引用。** lambda 用 `[&]` 按引用捕获了 `core_id`、`name` 和 `args...`,而它可能在 `createAndStartThread` 返回之后才开始执行。那时栈帧已经没了,每个引用都悬空。修法是按值捕获,或者把参数打包进 `std::tuple`、用 `std::apply` 展开。

**坑 2——`sleep_for(1s)` 只是把竞态盖住了。** 它掩盖的竞态是:主线程 `return t` 时,子线程的 `func` 可能已经在跑,**但 `setThreadCore` 还没生效**。正确的修法是握手:`std::latch ready{1}`,子线程设完 affinity 后 `count_down`,主线程返回前 `wait`。顺带一提,睡整整一秒也白白拖慢了启动。

**坑 3——`new std::thread` 出来的裸指针从不 delete。** 而且它返回一个仍然 `joinable` 的线程指针,却没约定由谁来 `join`/`detach`;一个到析构时还 joinable 的 `std::thread` 会直接调用 `std::terminate`。

**坑 4——第一次迁移还是发生了。** 线程出生时跑在*创建者*的核上,到入口才迁去目标核,第一次迁移的冷缓存照样要付。彻底的修法是 `pthread_attr_setaffinity_np`,让线程**一出生就在目标核上**。

### 1.5 布局上的一条规矩:别用 0 号核

0 号核是 Linux 的启动 CPU,天然是各种打杂活动的集散地:RCU 的宽限期内核线程、默认工作队列、一些迁不走的 IRQ、NMI watchdog、计时、`kworker`。就算别的核全 `isolcpus` 了,这些也还集中在 0 号核上(有时溢到 1 号)。所以标准布局是:**打杂活动限制在 0(和 1)号核,热线程放在别处**;双路机器上,热核还要放在**网卡所在的那个 NUMA 节点**上。选核之前先用 `lscpu -e=CPU,CORE,SOCKET` 把映射关系看清楚。

---

## 2. 超线程与频率:核自己给你使绊子

第 1 部分讲的是把**别人**赶出你的核。这一部分不一样:**核本身**有几个特性,就算整个核都归你,也会让你的延迟抖动。

### 2.1 超线程:一个物理核装成两个

超线程(Intel 的叫法,通称 SMT)让一个物理核表现为两个逻辑核。操作系统看到 `CPU 0` 和 `CPU 48`,但它们是**同一个物理核**上的两套寄存器状态。一条流水线停下来等内存时,核可以切去执行另一套状态的指令来填空——对吞吐有好处,通常多 15%–30%。

但这两个逻辑核**共享几乎所有真正要紧的东西**:执行单元(ALU、FPU)、L1、L2、store buffer、TLB、分支预测器。于是:你把热线程钉在 `CPU 0`,以为自己独占了一个核;结果另一个任务被调度到 `CPU 48`,它跑 AVX、占着浮点单元让你干等,它的访存还冲掉你们共用的 L1,你的热数据只能重新加载。"我独占这个核"的前提被兄弟线程打破了。

看看开没开、谁和谁是兄弟:

```bash
lscpu -e                                                          # 看 CORE 列,数字相同的就是兄弟
cat /sys/devices/system/cpu/cpu0/topology/thread_siblings_list    # 直接列出 CPU0 的兄弟
cat /sys/devices/system/cpu/smt/active                            # 1 = SMT 开着
```

怎么关:最彻底的是在 BIOS 里全局关掉超线程,或者内核命令行加 `nosmt`。不想全局关,就一个一个把兄弟下线:

```bash
echo 0 > /sys/devices/system/cpu/cpu48/online   # CPU48 消失,CPU0 独占整个物理核
```

验证方法是前后各跑一次 `cyclictest`,比较最大值和尖刺次数。

### 2.2 C-state:核在打盹,叫醒它要时间

C-state 是 CPU 的**空闲省电状态**。C0 是在干活;C1 / C1E 是浅度停顿;C3、C6 是深度睡眠——越深越省电,但**醒来越慢**。C6 会清空 L1 和 L2、降低核电压,从 C6 回到 C0 大约要 30 到 100 微秒。

如果你的线程节奏是"处理一个行情包,然后短暂空闲",核可能在空闲时滑进 C6;下一个包到达时,前 30–100 微秒全花在叫醒核上。这是一个很阴险的尾延迟来源,因为它只在空闲之后才出现。

三种修法,从粗到细:

1. **`idle=poll`(内核启动参数)**——最粗暴:核空闲时不进任何 C-state,原地轮询。延迟最低,但功耗和发热拉满。
2. **限制最深的 C-state**——`processor.max_cstate=1` + `intel_idle.max_cstate=1`,或者运行时逐个状态 `echo 1 > /sys/devices/system/cpu/cpuN/cpuidle/stateX/disable`。允许浅睡,禁止深睡。
3. **`/dev/cpu_dma_latency`(PM QoS)**——打开这个设备文件,写入一个 32 位整数 `0`,**并且一直不关这个文件描述符**。这等于告诉内核"全系统能容忍的唤醒延迟是 0 微秒",内核就让核远离深度 C-state。关掉 fd,约束就解除。这是在程序里就能做的选项,比启动参数灵活。

### 2.3 P-state:核会变速,那就把它焊死

P-state 管的是**频率和电压**。有两样东西在动:

**一是调频策略(governor)。** 默认的 `powersave` 会随负载逐步升频——你的线程突然忙起来时,它不会一下跳到满速,而是"看到负载上来,升一档,再看,再升一档",你的前几个包就在这个爬坡过程中低频运行。换成 `performance`,频率就焊在最高的非睿频频率上。

**二是睿频(Turbo)。** "散热和功耗有余量时,跑到额定频率以上。"问题在于它让**频率变成了一个变量**:取决于有几个核在忙、机箱有多热、你的指令流里有没有 AVX-512(重度 AVX 会触发降频)。频率一变,每段代码的执行时间都跟着变——这就是抖动。HFT 的做法通常是**关掉睿频,让核跑在固定的基础频率上**——牺牲峰值速度,换每一次执行时间都一样。

```bash
cpupower frequency-set -g performance
cpupower frequency-set -d 3.5GHz -u 3.5GHz               # 下限 = 上限,频率钉死
echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo   # 关掉睿频
```

超线程、C-state、P-state 有一个共同点:它们都是**为平均效率 / 省电 / 峰值吞吐设计的,而这些目标和"每次执行时间都一样"相冲突**。热核一律同样处理——**冻结在全功率状态**:关掉兄弟线程,禁止深睡,锁死频率。你故意放弃核的一部分能力和全部弹性,换来它绝对可预测。

---

## 3. NUMA:内存并不一样近

前两部分把 CPU 这边收拾干净了。这一部分换个维度:**内存**。在多路服务器上,"访问内存"要多久,取决于你访问的是**哪一块**内存。

### 3.1 两个插槽,一条 UPI

双路服务器物理上是两颗 CPU,每颗直接连着一部分内存条。CPU 0 访问"连在自己身上"的内存是**本地访问**,约 90 ns。CPU 0 访问"连在 CPU 1 上"的内存,要把请求经过 CPU 之间的互连(Intel 叫 UPI,AMD 叫 Infinity Fabric)送到 CPU 1,由 CPU 1 的内存控制器取出来再送回——这是**远端访问**,约 140 ns。

`numactl --hardware` 能看到这一点:它打印一个 `node distances` 矩阵,本地是 `10`,远端是 `21`,比值 2.1 大致就是延迟的倍数。

关键是:这个附加代价**不是偶尔的尖刺,而是每一次远端访问都要交的税。** 如果你的热线程跑在 CPU 0 上,它的订单簿数据却不小心分配在了节点 1,那么它这辈子每碰一次订单簿都慢 50 ns。这不是抖动,而是整个分布的**基线平移**——和 C-state 唤醒那种离散的、"只在空闲后才出现"的尖刺,完全是两种形状。

<svg viewBox="0 0 760 470" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="双路服务器上的核隔离与 NUMA 布局:打杂核吸收噪声,热核只跑一个线程,设备中断引到打杂核,跨插槽访存要付 UPI 的代价" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .bg    { fill: #fbfaf7; }
    .panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .ink   { fill: #1c1b18; }
    .muted { fill: #6b6558; }
    .core       { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .coreHouse  { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .coreHot    { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 2; }
    .coreLabel  { fill: #3a372f; font-size: 11px; }
    .dram  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .nic   { fill: #e7e2f0; stroke: #9a8cc0; stroke-width: 1.2; }
    .upi   { stroke: #8a8474; stroke-width: 2.5; }
    .irq   { stroke: #c15b3f; stroke-width: 1.8; fill: none; marker-end: url(#ahzh); }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .cap   { fill: #6b6558; font-size: 10.5px; }
    @media (prefers-color-scheme: dark) {
      .bg    { fill: #17161b; }
      .panel { fill: #201f26; stroke: #3a3945; }
      .ink   { fill: #e9e7ef; }
      .muted { fill: #a19caf; }
      .core       { fill: #2a2933; stroke: #47454f; }
      .coreHouse  { fill: #4a2f2c; stroke: #8f5a4c; }
      .coreHot    { fill: #33421f; stroke: #8fb257; }
      .coreLabel  { fill: #d7d3c8; }
      .dram  { fill: #23262c; stroke: #3f4650; }
      .nic   { fill: #2e2940; stroke: #6a5c95; }
      .upi   { stroke: #9a9384; }
      .irq   { stroke: #e0795b; }
      .title { fill: #e9e7ef; }
      .cap   { fill: #a19caf; }
    }
  </style>
  <defs>
    <marker id="ahzh" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="760" height="470" rx="10"/>
  <text class="title" x="24" y="30">一台双路服务器:噪声赶到打杂核,热核清净</text>
  <rect class="panel" x="24" y="48" width="330" height="196" rx="8"/>
  <text class="muted" x="40" y="70" font-size="12" font-weight="700">插槽 0 · NUMA 节点 0</text>
  <rect class="coreHouse" x="40"  y="82" width="70" height="42" rx="5"/>
  <text class="coreLabel" x="49" y="99">核 0</text><text class="cap" x="49" y="115">打杂</text>
  <rect class="coreHouse" x="118" y="82" width="70" height="42" rx="5"/>
  <text class="coreLabel" x="127" y="99">核 1</text><text class="cap" x="127" y="115">打杂</text>
  <rect class="core" x="196" y="82" width="66" height="42" rx="5"/>
  <text class="coreLabel" x="205" y="99">核 2</text>
  <rect class="coreHot" x="270" y="82" width="76" height="42" rx="5"/>
  <text class="coreLabel" x="279" y="99" font-weight="700">核 3</text><text class="cap" x="279" y="115">热线程</text>
  <rect class="core" x="40"  y="132" width="66" height="38" rx="5"/><text class="coreLabel" x="49" y="155">核 4</text>
  <rect class="core" x="114" y="132" width="66" height="38" rx="5"/><text class="coreLabel" x="123" y="155">核 5</text>
  <rect class="core" x="188" y="132" width="66" height="38" rx="5"/><text class="coreLabel" x="197" y="155">核 6</text>
  <rect class="core" x="262" y="132" width="84" height="38" rx="5"/><text class="coreLabel" x="271" y="155">核 7</text>
  <rect class="dram" x="40" y="182" width="306" height="46" rx="6"/>
  <text class="ink" x="52" y="201" font-size="11.5" font-weight="700">本地内存(节点 0)</text>
  <text class="cap" x="52" y="218">核 3 &#8594; 这里 &#8776; 90 ns(本地)</text>
  <rect class="panel" x="406" y="48" width="330" height="196" rx="8"/>
  <text class="muted" x="422" y="70" font-size="12" font-weight="700">插槽 1 · NUMA 节点 1</text>
  <rect class="core" x="422" y="82" width="66" height="42" rx="5"/><text class="coreLabel" x="431" y="99">核 8</text>
  <rect class="core" x="496" y="82" width="66" height="42" rx="5"/><text class="coreLabel" x="505" y="99">核 9</text>
  <rect class="core" x="570" y="82" width="70" height="42" rx="5"/><text class="coreLabel" x="579" y="99">核 10</text>
  <rect class="core" x="648" y="82" width="72" height="42" rx="5"/><text class="coreLabel" x="657" y="99">核 11</text>
  <rect class="core" x="422" y="132" width="66" height="38" rx="5"/><text class="coreLabel" x="431" y="155">核 12</text>
  <rect class="core" x="496" y="132" width="66" height="38" rx="5"/><text class="coreLabel" x="505" y="155">核 13</text>
  <rect class="core" x="570" y="132" width="70" height="38" rx="5"/><text class="coreLabel" x="579" y="155">核 14</text>
  <rect class="core" x="648" y="132" width="72" height="38" rx="5"/><text class="coreLabel" x="657" y="155">核 15</text>
  <rect class="dram" x="422" y="182" width="306" height="46" rx="6"/>
  <text class="ink" x="434" y="201" font-size="11.5" font-weight="700">内存(节点 1)</text>
  <text class="cap" x="434" y="218">核 3 &#8594; 这里 &#8776; 140 ns(经 UPI)</text>
  <line class="upi" x1="354" y1="146" x2="406" y2="146"/>
  <text class="muted" x="360" y="138" font-size="10.5" font-weight="700">UPI</text>
  <rect class="nic" x="24" y="300" width="150" height="60" rx="8"/>
  <text class="ink" x="40" y="324" font-size="12" font-weight="700">网卡</text>
  <text class="cap" x="40" y="342">PCIe 挂在插槽 0</text>
  <text class="cap" x="40" y="356">&#8594; 热核放在节点 0</text>
  <path class="irq" d="M120 300 C 120 260, 90 180, 75 128"/>
  <path class="irq" d="M150 300 C 175 250, 165 180, 153 128"/>
  <text class="cap" x="118" y="286" fill="#c15b3f">硬中断 &#8594; 打杂核</text>
  <rect class="panel" x="250" y="286" width="486" height="152" rx="8"/>
  <text class="title" x="266" y="310" font-size="12.5">核 3 上真正在跑什么</text>
  <text class="cap" x="266" y="332" font-size="11">isolcpus=3    调度器不往这里放任何东西(显式绑核照样可以)</text>
  <text class="cap" x="266" y="350" font-size="11">nohz_full=3   只剩一个可运行任务 &#8594; 1000 Hz 的 tick 停掉</text>
  <text class="cap" x="266" y="368" font-size="11">rcu_nocbs=3   RCU 回调交给其他核上的 rcuop 线程</text>
  <text class="cap" x="266" y="386" font-size="11">irqaffinity    设备中断落在 0/1 号核,不在这里</text>
  <text class="cap" x="266" y="404" font-size="11">绑核 + attr   线程一出生就在核 3 &#8212; 连第一次迁移都省了</text>
  <text class="cap" x="266" y="424" font-size="11" font-weight="700">剩下的:约 1 Hz 残余 tick、偶尔的 IPI、SMI &#8212; 这就是地板</text>
</svg>

> 图:打杂核(0/1)吸收设备中断和内核杂活;核 3 用三个启动参数清出来,再把热线程绑上去;访问节点 1 的内存要过 UPI,每次约多 50 ns。

### 3.2 first-touch:页跟着第一个写它的核走,不跟着 `malloc` 走

这是 NUMA 里最反直觉、也最容易弄错的一点。

你 `malloc(1GB)` 时,Linux **并没有真的给你 1 GB 物理内存**——它只是在你的地址空间里预留了一段虚拟地址。物理页要等你第一次**写**这一页时才分配(由缺页触发)。而内核分配时的默认策略是 **first-touch**:物理页放在**执行第一次写的那个核**所在的 NUMA 节点上。

后果是:你在主线程里 `malloc` 一大块,顺手 `memset` 清零,这一整块就落在了**主线程当时所在的节点**上。然后你把工作线程绑到另一个节点的核上去用它——每次访问都是远端。正确的模式是**谁用谁初始化**:分配完先别碰,让最终要用它的工作线程在自己的核上做第一次写。

### 3.3 membind、preferred、interleave

`numactl` 和 `libnuma` 提供三种内存绑定策略,区别在于"节点不够用了怎么办":

- **`--membind=0`(严格绑定)**——只从节点 0 分配,**节点 0 满了就失败 / OOM,哪怕节点 1 还有大把空闲。** 更糟的是,真正 OOM 之前,内核会先让 `kswapd` 拼命回收节点 0,而这个回收本身就是一阵抖动。所以严格绑定时,你得自己盯着目标节点的空闲内存、对称地扩容——**不要**一遇到问题就放宽成 `--preferred`,那等于扔掉了 NUMA 本地性的保证。
- **`--preferred=0`(软偏好)**——优先节点 0,不够就退到别的节点。不会 OOM,但失去了"数据一定在本地"的保证。
- **`--interleave=all`(交错)**——页按轮转分到各个节点。它不是为延迟设计的,是为**带宽**:一个要扫大量内存的分析任务,可以把带宽压力摊到所有内存控制器上。不适合 HFT 热路径。

`libnuma` 的接口是 `numa_alloc_onnode()`、`numa_run_on_node()`、`numa_set_localalloc()`;底层系统调用是 `mbind(2)`、`set_mempolicy(2)`、`move_pages(2)`。诊断用 `numastat -p <pid>`,看每个节点分配了多少、`numa_miss` / `numa_foreign` 有没有在涨。

### 3.4 最好的 NUMA 修法,是根本不出现这个问题

上面讲的都是事后补救——数据已经共享了、已经跨线程了。真正的低延迟系统,首选是让 NUMA 问题**不存在**:

- 热路径**单线程 + 绑核**,数据私有——没有共享,就没有跨节点的问题。
- 需要多个工作线程时,走 **share-nothing**:每个线程有自己的一份状态,绑在自己节点的核上,用自己节点的内存,线程之间只通过消息传递(无锁队列)交换必要的东西。
- 这样每个线程做的都是本地访问,NUMA 距离矩阵里那个 `21`,你永远碰不到。
