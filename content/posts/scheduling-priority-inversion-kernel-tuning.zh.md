---
title: "交易系统笔记 #19：调度策略、优先级反转与内核调优"
date: 2026-10-29
slug: "scheduling-priority-inversion-kernel-tuning"
description: "普通调度只保证份额，同一个核上的热线程可能要等对方一个几 ms 的时间片；实时优先级让它一就绪就跑，但会碰上 RT 限流、饿死内核线程和同核自旋死等。高优先级线程和低优先级线程共用一把锁时，中间的线程插进来会让等待没有上界，这是优先级反转，修法是优先级继承和优先级天花板，更彻底的是热线程不和低优先级线程共用锁。最后是内核抢占模式、PREEMPT_RT，以及从 BIOS 到 sysctl 的一张按层清单和 tuned。"
summary: "谁先跑、跑多久：调度类和时间片，实时优先级的三个坑，优先级反转的两种修法，PREEMPT_RT 为什么 HFT 常常不用，以及一台低延迟机器从 BIOS 到 sysctl 要动哪些开关。"
chapter: 1
categories: [Systems]
tags: [linux, scheduler, sched-fifo, priority-inversion, preempt-rt, kernel-tuning, tuned, hft, low-latency]
toc: true
math: true
light: true
---

行情线程绑在 3 号核上，另一个压缩日志的线程没绑核，也被调度到了 3 号核。两个都是默认的普通调度，日志线程一跑就是一个时间片，几 ms，行情线程只能等着。把行情线程改成实时优先级，它一就绪就能把日志线程挤下去。可它要是和一个低优先级线程共用一把锁，又可能被第三个线程间接卡住，这叫优先级反转。前两部分讲这两件事：调度器怎么决定谁先跑，以及优先级反转怎么治。后两部分讲机器本身：内核什么时候不能被抢占，以及从 BIOS 到 sysctl 要动哪些开关。

## 1. 调度策略：谁先跑、跑多久

### 1.1 调度类（scheduling class）：先比类，再比类内

Linux 的调度器每次挑下一个线程，按固定顺序问几个调度类：stop（内核自己做迁移等事情用）→ deadline（`SCHED_DEADLINE`）→ 实时（`SCHED_FIFO`、`SCHED_RR`）→ 普通（`SCHED_OTHER`、`SCHED_BATCH`、`SCHED_IDLE`）→ idle。前面的类里有可运行的线程，后面的类就轮不到。所以一个实时线程只要就绪，普通线程设得再“重要”也得让开。

普通类就是常说的 CFS（完全公平调度器，6.6 起换成了 EEVDF，思路一样）。每个线程累计一个按权重折算的运行时间（vruntime），调度器每次挑累计得最少的那个。nice 值从 −20 到 19，每差 1 级，权重约差 1.25 倍。它保证的是份额，不是先后：两个线程在同一个核上都想跑，就轮流跑，每次跑一个时间片，约 0.75–3 ms（核越多，默认值越大）。热线程恰好在对方的时间片开头醒来，就要等上一整片。把 nice 调高也只是多分一点份额，等的时间还是 ms 级。

实时类按优先级 1–99 严格排先后：高优先级的线程一就绪，立刻抢占正在跑的低优先级线程，从唤醒到跑起来是 µs 级，具体多久取决于内核那一刻能不能被抢占（第 3 部分）。`SCHED_FIFO` 抢到核以后一直跑，直到自己阻塞、主动让出，或者被更高优先级的线程抢走。`SCHED_RR` 一样，只是同一优先级的线程之间每 100 ms 轮一次。**普通类只保证份额，实时类保证一就绪就跑。**

`SCHED_DEADLINE` 按“每个周期要跑多少时间、截止时间在哪”排，最早截止的先跑（EDF），排在实时类前面。它适合周期性的任务，交易系统里少见。

### 1.2 设置：创建线程时就带上调度策略

最稳妥的做法是在创建线程时就把调度策略写进属性里：

```cpp
bool start_rt_thread(pthread_t& t, int prio) {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);  // 不写这句，下面两行被忽略
    pthread_attr_setschedpolicy(&attr, SCHED_FIFO);
    sched_param sp{};
    sp.sched_priority = prio;                                      // SCHED_FIFO 取 1–99
    pthread_attr_setschedparam(&attr, &sp);
    int err = pthread_create(&t, &attr, hot_loop, nullptr);
    pthread_attr_destroy(&attr);
    if (err != 0) {                                                // 返回值就是错误码，不设 errno
        std::fprintf(stderr, "pthread_create: %s\n", std::strerror(err));  // 没权限是 EPERM
        return false;
    }
    return true;
}
```

属性默认是 `PTHREAD_INHERIT_SCHED`：新线程继承创建者的调度策略，属性里写的策略和优先级会被**悄悄忽略**，不报错。所以第一行 `PTHREAD_EXPLICIT_SCHED` 不能省。另一种写法是先创建、再用 `pthread_setschedparam` 改，但两步之间线程已经按普通调度跑了一段，热线程的初始化可能就落在这段里。

pthread 系列函数出错时直接返回错误码，不设 `errno`，所以要用 `strerror(err)`，用 `perror` 打出来的是不相干的旧值。最常见的错是 `EPERM`：设实时优先级要有 `CAP_SYS_NICE`，或者放开 `RLIMIT_RTPRIO`（`ulimit -r`，或在 `/etc/security/limits.conf` 里配 `rtprio`）。

`std::thread` 没有调度接口，要拿底层句柄改：

```cpp
void set_fifo(std::thread& t, int prio) {
    sched_param sp{};
    sp.sched_priority = prio;
    if (int err = pthread_setschedparam(t.native_handle(), SCHED_FIFO, &sp); err != 0)
        std::fprintf(stderr, "pthread_setschedparam: %s\n", std::strerror(err));
}
```

命令行上用 `chrt`：`chrt -f 80 ./app` 以 `SCHED_FIFO` 80 启动程序；`chrt -f -p 80 <tid>` 改一个已有的线程，`-p` 后面给线程号就只改那一个线程；加 `-a` 改这个进程的所有线程；`chrt -p <pid>` 只看不改。`ps -eLo tid,cls,rtprio,comm` 能列出每个线程的调度类和优先级。

### 1.3 RT 限流（RT throttling）：每秒被停 50 ms

内核默认 `kernel.sched_rt_period_us = 1000000`、`kernel.sched_rt_runtime_us = 950000`：每 1 s 里，实时任务最多跑 950 ms，剩下的 50 ms 留给普通任务，防止一个写错的实时线程把机器锁死。忙轮询的 `SCHED_FIFO` 线程正好把核占满，于是每秒被强停一次，一次约 50 ms，`dmesg` 里会出现 `sched: RT throttling activated`。对行情线程来说，这就是每秒一次 50 ms 的空窗。

较新的内核（6.12 起）改用 fair server：给普通任务预留每秒最多 50 ms，只有这个核上真有普通任务在等时才让出。另一种修法是把 `sched_rt_runtime_us` 设成 −1，彻底关掉限流。**关掉限流以后，写错的实时线程真能把这个核锁死**，所以要配合隔离，让这个核上本来就没有别的任务。

### 1.4 饿死内核线程：同一个核上的 ksoftirqd 和 kworker

每个核上都有自己的内核线程：`ksoftirqd/N` 处理这个核上的软中断，`kworker/N` 做派给这个核的工作。它们大多是普通优先级。一个 `SCHED_FIFO` 线程在核 N 上忙轮询，它们就永远轮不到：发到这个核的网络软中断一直堆着，别的核上等这个核完成某项工作的线程也跟着卡住。优先级 99 还和 `migration/N`、watchdog 这类内核线程同级，连它们也会被挡住。

所以实时优先级一般给 50–80，不给 99，而且要让这个核上本来就没有别的活：网卡中断绑走、不绑核的工作队列挪走（第 4 部分），这就是 [#1](/zh/posts/cpu-affinity-core-isolation-numa/) 1.2 讲的隔离。

### 1.5 同核自旋：持锁的线程永远上不了核

[#16](/zh/posts/spinlock-implementation/) 1.2 说过，自旋的前提是持锁的线程一直在跑。实时优先级会把这个前提彻底打破：`SCHED_FIFO` 的线程 H 在 3 号核上自旋等锁，持锁的线程 L 也在 3 号核上，优先级更低。H 不让出，L 就上不了核，锁也就永远不放，H 一直转到被 RT 限流停下为止。**同一个核上，高优先级线程自旋等低优先级线程持有的锁，就是死等。**修法是让自旋锁的两边各占一个核，或者换成会睡的锁（2.2 的优先级继承锁）。

### 1.6 隔离核上还要不要实时优先级

热线程独占一个隔离核时，核上本来就只有它，不需要和谁分份额，`nohz_full` 下连时钟中断都停了，普通调度也不会被别的线程抢。实时优先级在这里防的是偶尔混进来的东西：某个没绑核的线程、一个被唤醒到这里的内核线程。给热线程一个中等的实时优先级，混进来的普通线程就抢不走它，代价是 1.3–1.5 这三个坑都要防。**实时优先级解决的是共用核时谁先跑；核已经独占时，它是一层保险。**常见的做法有两种：隔离核加普通调度，靠隔离保证没人来；或者隔离核加中等实时优先级，再关掉限流，多一层保险。

## 2. 优先级反转：高优先级线程被中间的线程卡住

### 2.1 优先级反转（priority inversion）：中间的线程插进来

三个线程在同一个核上：低优先级的 L 拿着锁 `m`；高优先级的 H 醒来，也要 `m`，只能阻塞；这时中优先级的 M 醒来，它不需要锁，但优先级比 L 高，于是抢走了核。现在 H 在等 L 放锁，L 在等 M 让出核。H 一共要等：

$$
T_H = \underbrace{t_L}_{\substack{\text{L 剩下的} \\ \text{临界区}}} + \underbrace{\textstyle\sum t_M}_{\substack{\text{所有插进来的} \\ \text{中优先级线程}}}
$$

第一项躲不掉：锁本来就要等持有者做完，临界区短，这一段也短。第二项没有上界：M 跑多久、来几个 M，H 就等多久，H 实际上排到了 M 后面，优先级倒过来了。**要治的不是“高优先级等低优先级”，而是中间的线程插进来，让等待没有上界。**

最有名的例子是 1997 年的火星探路者号：着陆后系统反复重启。高优先级的总线管理任务在等一把锁，锁被低优先级的气象数据任务拿着，中优先级的通信任务又长时间占着 CPU。总线任务超时，看门狗认为系统卡死，于是重启。地面把那把互斥锁的优先级继承选项打开，问题就消失了。

### 2.2 优先级继承（PI，priority inheritance）：谁挡着 H，谁就临时升到 H

优先级继承的做法是：H 阻塞在锁 `m` 上时，把 `m` 的持有者 L 的优先级临时提到 H 的优先级。M 比 L 低了，抢不走核，L 跑完临界区、放锁，优先级降回原值，H 拿到锁。如果 L 自己也在等另一把锁 `m2`，`m2` 的持有者 K 同样被提升，沿着这条链一路往下传。这样 H 只用等链上各段临界区，第二项没了。

POSIX 互斥锁通过属性打开它：

```cpp
void init_pi_mutex(pthread_mutex_t& m) {
    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_INHERIT);
    pthread_mutex_init(&m, &a);
    pthread_mutexattr_destroy(&a);
}
```

`std::mutex` 没有这个选项，要用的话只能直接用 `pthread_mutex_t`。

在 Linux 上它的代价很小。PI 锁底下是 PI futex：没人抢时，加锁就是一次 CAS，把自己的线程号写进锁字，和普通的 futex 锁（[#16](/zh/posts/spinlock-implementation/) 1.1）一样不进内核；只有抢不到时才进内核（`FUTEX_LOCK_PI`），内核按锁字里的线程号找到持有者，再提升它。**优先级继承只在真的发生争抢时才花钱。**

它也有覆盖不到的地方：要有一个确定的持有者可以提升。H 等条件变量、信号量，或者等读写锁的读者时，等的是“有人来通知”，没有一个确定的持有者，优先级继承就帮不上忙。比如 H 在条件变量上等 L 生产数据，M 插进来抢了 L 的核，H 照样被拖住。新内核里的 proxy execution 想把这种情况也管起来，还在逐步合入。

### 2.3 优先级天花板（PP，priority protect）：一拿锁就升到最高

优先级天花板给每把锁预设一个天花板优先级，取所有会用这把锁的线程里最高的那个。谁拿到这把锁，谁的优先级就立刻提到天花板，有没有人在等都一样；放锁时再降回去。L 一拿锁就和 H 一样高，M 从一开始就抢不走它，反转在发生之前就被挡住了。而且持有者已经是这把锁的使用者里最高的，别的使用者都抢不走它，不会形成一串等待，H 最多被挡一段临界区。

```cpp
void init_pp_mutex(pthread_mutex_t& m, int ceiling) {
    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_PROTECT);
    pthread_mutexattr_setprioceiling(&a, ceiling);                 // 所有会用这把锁的线程里最高的优先级
    pthread_mutex_init(&m, &a);
    pthread_mutexattr_destroy(&a);
}
```

代价在每一次加锁上：每次加锁、放锁都要改优先级，glibc 要为此进内核，没人抢的一次加锁也从一次 CAS（约 20 ns）变成两次系统调用（约 0.2–2 µs）。而且要事先知道所有使用者的优先级，比天花板还高的线程来拿锁会失败。

| | 优先级继承（PI） | 优先级天花板（PP） |
|---|---|---|
| 什么时候提升 | 有人等了才提升 | 一拿锁就提升 |
| 没人抢时的代价 | 和普通锁一样，一次 CAS | 每次加锁、放锁都要改优先级，要进内核 |
| 要事先知道什么 | 不用 | 所有使用者里最高的优先级 |
| 等待链 | 可能是一串，逐个提升 | 最多被挡一段临界区 |

**争抢少、使用者不固定，用优先级继承；使用者固定、最坏等待时间必须有上界（硬实时），用优先级天花板。**

### 2.4 低延迟系统的选法：热线程不和低优先级线程共用锁

优先级继承和天花板都只是把 H 的等待压到一段临界区。热线程连一段临界区也不想等：临界区里的线程也可能缺页、被中断，那一段并不总是短的。所以热路径上常见的做法是根本不共用锁。热线程要交出去的数据走 SPSC 环（[#4](/zh/posts/lock-free-queue-logger-micro-batching/)、[#18](/zh/posts/thread-safe-queue/)），环没有持有者，生产者写完就走；热线程要读的配置这类“偶尔改、经常读”的数据，用双数组加原子索引（[#14](/zh/posts/prefetch-warmup-double-buffer/) 第 3 部分）或 seqlock，读的一方不拿锁。只有低频、不在热路径上的共享状态才用锁，这时用优先级继承锁兜底。**最彻底的办法是让高优先级线程在结构上就不用等低优先级线程。**

## 3. 内核也要能被抢占：preempt 模式与 PREEMPT_RT

### 3.1 不可抢占的窗口：内核拿着自旋锁时谁也抢不走

实时线程醒来要抢核，可核上的线程这时可能正在内核里：拿着自旋锁、关着中断，或者在跑软中断。这些区域不能被抢占，实时线程只能等它走出来，第 1 部分说的“一就绪就跑”在这里打了折扣。

普通内核用启动参数 `preempt=` 选抢占模式，要内核开了 `CONFIG_PREEMPT_DYNAMIC` 才认：

- `none`：内核代码只在返回用户态等少数地方切换线程，吞吐最好，等待最长；
- `voluntary`：内核里显式插了一些可以让出的点；
- `full`：除了拿着自旋锁、关着中断的区域，内核代码随时可以被抢占；
- `lazy`（6.13 起）：普通任务的抢占推迟到下一个时钟中断，实时任务照旧立刻抢占。

就算是 `full`，拿自旋锁和关中断的区域也还在。忙的机器上，普通内核里实时线程从唤醒到跑起来，最坏能到几百 µs 甚至几 ms。

### 3.2 PREEMPT_RT：把不可抢占的窗口缩到最短

PREEMPT_RT 把剩下的这些窗口也拆掉，主要改了三处：

- **自旋锁换成会睡的锁**：内核里大部分 `spinlock_t` 改成基于 rt_mutex 的锁，持有者可以被抢占，锁本身带优先级继承；只有 `raw_spinlock_t` 还真的自旋。
- **中断处理放进线程**：硬中断的处理函数在内核线程（`irq/N-名字`，默认 `SCHED_FIFO` 50）里跑，优先级 80 的热线程不会被它们的处理过程打断，硬件进中断的那一下还在，但很短。普通内核加启动参数 `threadirqs` 也能做到这一条。
- **软中断也放进线程**，`printk` 也改成了不会长时间关抢占的写法。

它在 6.12 合入主线，之前要用发行版的 `-rt` 内核。效果是最坏的唤醒延迟降到约 10–100 µs，代价是上下文切换更多、锁更重，吞吐下降几个百分点到 10% 以上。

### 3.3 HFT 常常不用实时内核

实时内核压低的是“从被唤醒到跑起来”的最坏时间。可 HFT 的热线程不等唤醒：它在隔离核上忙轮询，热路径上不做系统调用，用了内核旁路以后，连收包都不经过内核网络栈。内核不在它的路径上，实时内核就帮不上什么忙，反而让它确实要用的那些内核路径变慢了。设计里依赖唤醒的场景才值得上实时内核：阻塞队列、定时器、靠中断驱动的 I/O，或者很多线程共用几个核（工业控制、音频处理）。**实时内核压的是被唤醒到跑起来的最坏时间；热线程不睡，这段时间就不存在。**

## 4. 内核与 BIOS 调优：一张按层的清单

[#1](/zh/posts/cpu-affinity-core-isolation-numa/) 讲了隔离核、超线程、C-state 和 P-state，[#3](/zh/posts/hot-path-memory-allocators/) 讲了 `mlockall` 和 TLB shootdown。剩下的开关按层排在下面，每一个都写它动的是什么、换来什么、代价是什么。共同的思路和 #1 一样：凡是为平均效率、省电、峰值吞吐设计的机制，都可能让某一次执行变慢，热核上能关就关；用不到的子系统也关，少一条可能打断热核的路径。

### 4.1 BIOS 和电源：关掉为平均和峰值设计的机制

- **C-state、P-state、超线程**：原理和取舍见 #1 第 2 部分。BIOS 里也要关，一些平台的调频由硬件自己做（如 Intel 的 HWP），只改操作系统一侧管不住。
- **Turbo**：有取舍。关掉以后频率固定，每次执行时间一样；开着时单核能快约 10%–30%，但频率随活跃核数和温度变。追求确定性就关，也有团队留着 Turbo，同时把活跃核数和散热控制住。
- **服务器 BIOS 的性能预设**：一般叫 power profile，选“性能”或“低延迟”，会把上面几项连同 uncore 频率、内存省电一起设好。
- **HPET**：它平时不发中断，要紧的是时钟源。内核正常用 TSC 当时钟源，`clock_gettime` 在用户态读 TSC，约 20–30 ns；TSC 一旦被判成不可靠，内核退回 HPET，每次读都要访问芯片组，约 0.5–1.5 µs。用 `cat /sys/devices/system/clocksource/clocksource0/current_clocksource` 确认是 `tsc`。
- **VT-x / AMD-V**：不跑虚拟机就关，属于“用不到的都关”。

操作系统一侧对应的命令：`cpupower frequency-set -g performance` 把调频策略定在最高频；Intel 的 `intel_pstate` 驱动下关 Turbo 是 `echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo`（**写 1 才是关**），`acpi-cpufreq` 驱动下是 `echo 0 > /sys/devices/system/cpu/cpufreq/boost`；限制 C-state 可以打开 `/dev/cpu_dma_latency`、写入 0 并一直开着（#1 2.2）。

### 4.2 启动参数：隔离之外的几个

- **`isolcpus`、`nohz_full`、`rcu_nocbs`、`irqaffinity`**：见 #1 1.2。
- **`preempt=`**：见 3.1。
- **`threadirqs`**：把中断处理函数放进内核线程（`irq/N-名字`），这样它们可以绑核、排优先级；代价是每次中断多一次线程切换。
- **`nowatchdog`、`nmi_watchdog=0`**：soft lockup 检测线程每几秒醒一次，NMI watchdog 用一个性能计数器周期性地发 NMI。关掉少两类打断，代价是内核真卡死时没人报。
- **`tsc=reliable`**：跳过内核对 TSC 的定期核对（时钟源看门狗拿别的时钟比），也就不会因为一次核对的抖动把 TSC 判成不可靠、退回 HPET。代价是 TSC 真有问题时也发现不了，较新的 CPU 上 TSC 频率恒定、跨核同步，风险小。
- **`mitigations=off`**：关掉 Spectre、Meltdown 这类 CPU 漏洞的缓解措施。缓解的开销主要在进出内核：每次系统调用切换页表（KPTI）、返回用户态前清空缓冲区、间接跳转加防护，每次系统调用多约 0.1–0.5 µs。热路径不进内核时几乎不受影响，**代价是安全**，只用在专用、不跑外来代码的机器上。
- **`transparent_hugepage=never`**：关掉透明大页。后台线程 `khugepaged` 合并页的时机不受控制，合并时还要改页表，触发 TLB shootdown（#3 2.2）。
- **`audit=0`、`ipv6.disable=1`、`mce=off`**：关掉用不到的子系统。`mce=off` 关的是硬件错误上报，只在测试机上关。

### 4.3 sysctl：网络

- **`net.core.busy_read`、`net.core.busy_poll`**（单位 µs）：socket 读不到数据时，先在内核里轮询网卡队列最多这么久，而不是立刻睡下等中断。省掉“中断 → 软中断 → 唤醒线程”这一段，约 5–20 µs，代价是轮询期间占着 CPU。讲内核旁路时会接着说。
- **`net.core.netdev_max_backlog`**：每个核上驱动交给协议栈的队列长度。突发流量把队列打满就丢包（`/proc/net/softnet_stat` 第 2 列在涨），调大可以防丢。
- **`net.core.somaxconn`**：`listen` 的全连接队列上限，影响要接很多连接的服务端；交易客户端连接少、连得久，影响小。
- **关 Nagle**：没有全局的 sysctl，要每个 socket 自己设 `setsockopt(TCP_NODELAY)`。`net.ipv4.tcp_low_latency` 从 4.14 起已经不起作用。
- **BBR、`tcp_fastopen`**：BBR 是拥塞控制算法，影响长距离链路的吞吐和排队；fast open 在建连时省一个往返。交易连接在机房内、建好后长期不断，这两项影响都小。

### 4.4 sysctl：内存

- **`vm.swappiness` 和 `mlockall`**：swappiness 调小只是让内核少换出，内存压力大时照样会换。真正保证热数据不被换出的是 `mlockall(MCL_CURRENT | MCL_FUTURE)`，它的漏洞见 #3 第 2 部分。进程要有 `CAP_IPC_LOCK`，或者足够大的 `RLIMIT_MEMLOCK`。
- **`vm.dirty_ratio`、`vm.dirty_background_ratio`**：脏页占到内存的多少比例时开始后台写回、多少时让写的线程停下来等。调小以后小批量常写，不会一次攒几 GB 再写，写日志的线程就不会在 `write()` 里卡上几百 ms；代价是写盘次数多。
- **`vm.zone_reclaim_mode=0`、`kernel.numa_balancing=0`**：本节点内存不够时直接用远端的，不先回收本地的页；不让内核自动搬页，搬页要改页表，同样会触发 TLB shootdown。NUMA 见 #1 第 3 部分。
- **关 KSM**：KSM 在后台扫描、合并内容相同的页，主要服务虚拟机，合并和拆分都要改页表。

### 4.5 中断和后台工作

- **停掉 irqbalance，把网卡中断绑到打杂核**：见 #1 1.2。irqbalance 不停，手动绑的中断会被它改回去。
- **`echo 0-1 > /sys/devices/virtual/workqueue/cpumask`**：不绑核的内核工作队列只在 0、1 号打杂核上跑。绑在某个核上的工作不受它管。
- **中断合并 `ethtool -C eth0 rx-usecs N`**：网卡攒够 N µs 或若干个包，才发一次中断。中断少了，CPU 也省了，但每个包最多多等 N µs。`rx-usecs 100` 是为吞吐配的，行情网卡要低延迟，就设成 0 并关掉 adaptive，或者干脆用 busy poll。

### 4.6 tuned：把清单存成一份配置

上面这些开关一条条手敲，重启以后很容易漏一条，或者被别的工具改回去。tuned 是一个后台服务，按配置文件（profile）统一设置 sysctl、sysfs、调频策略、`/dev/cpu_dma_latency` 和启动参数，并一直维持着。常用的几个：

- **`latency-performance`**：调频策略定在 performance，通过 `/dev/cpu_dma_latency` 限制 C-state，偏向性能的能耗设置，少换页；
- **`network-latency`**：在它之上关掉透明大页和 NUMA 自动平衡，打开 `busy_read`、`busy_poll`；
- **`cpu-partitioning`**：在 `/etc/tuned/cpu-partitioning-variables.conf` 里写 `isolated_cores=2-7`，它生成 `isolcpus`、`nohz_full`、`rcu_nocbs` 这些启动参数，并把内核线程和中断挪到打杂核上。

自己的配置可以写成 `include=network-latency`，再加上自己的几行，整台机器的调优就成了一个能放进 git、能 diff 的文本文件。`tuned-adm active` 看当前用的是哪个，`tuned-adm verify` 检查设置有没有被改掉。要注意的是 tuned、手写的 sysctl 和 irqbalance 这类工具会互相覆盖，只能留一个来源。**调优的结果要能重现：写进 tuned 配置，而不是一条条手敲。**
