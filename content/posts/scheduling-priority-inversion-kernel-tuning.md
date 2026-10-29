---
title: "Trading System Notes #19: Scheduling Policies, Priority Inversion and Kernel Tuning"
date: 2026-10-29
slug: "scheduling-priority-inversion-kernel-tuning"
description: "Normal scheduling only guarantees a share, so a hot thread on a shared core can wait out a time slice of several ms; a real-time priority makes it run as soon as it is ready, but brings RT throttling, starved kernel threads and same-core spin deadlocks. When a high-priority and a low-priority thread share a lock, a thread in between can make the wait unbounded: that is priority inversion, fixed by priority inheritance or priority ceilings, and more thoroughly by never sharing locks with low-priority threads. Then kernel preemption modes, PREEMPT_RT, a layer-by-layer checklist from BIOS to sysctl, and tuned."
summary: "Who runs first and for how long: scheduling classes and time slices, three traps of real-time priorities, two fixes for priority inversion, why HFT often skips PREEMPT_RT, and which knobs a low-latency box turns from BIOS to sysctl."
chapter: 1
categories: [Systems]
tags: [linux, scheduler, sched-fifo, priority-inversion, preempt-rt, kernel-tuning, tuned, hft, low-latency]
toc: true
math: true
light: true
---

The market-data thread is pinned to core 3. A log-compression thread that is not pinned also lands on core 3. Both use the default normal scheduling, so once the log thread starts it runs for a whole time slice, several ms, and the market-data thread just waits. Give the market-data thread a real-time priority and it pushes the log thread off as soon as it is ready. But if it shares a lock with a low-priority thread, a third thread can still hold it up indirectly. That is priority inversion. The first two parts cover these two things: how the scheduler decides who runs first, and how to cure priority inversion. The last two cover the machine itself: when the kernel cannot be preempted, and which knobs to turn from BIOS to sysctl.

## 1. Scheduling Policies: Who Runs First, and for How Long

### 1.1 Scheduling Classes: Compare the Class First, Then Within It

Each time the Linux scheduler picks the next thread, it asks the scheduling classes in a fixed order: stop (used by the kernel for migration and similar jobs) → deadline (`SCHED_DEADLINE`) → real-time (`SCHED_FIFO`, `SCHED_RR`) → normal (`SCHED_OTHER`, `SCHED_BATCH`, `SCHED_IDLE`) → idle. While an earlier class has a runnable thread, the later classes get nothing. So once a real-time thread is ready, a normal thread has to step aside no matter how "important" it is set to be.

The normal class is the familiar CFS (Completely Fair Scheduler; since 6.6 replaced by EEVDF, same idea). Each thread accumulates a weighted run time (vruntime), and the scheduler always picks the one that has accumulated the least. Nice values run from −20 to 19, and each step changes the weight by about 1.25×. What it guarantees is a share, not an order: two threads that both want the same core take turns, each running one time slice, about 0.75–3 ms (the default grows with the core count). If the hot thread wakes just as the other one starts its slice, it waits a whole slice. Raising its nice value only buys a larger share; the wait is still in milliseconds.

The real-time class orders threads strictly by priority 1–99: when a higher-priority thread becomes ready, it immediately preempts the lower-priority thread that is running. Wake-to-run takes microseconds, and exactly how long depends on whether the kernel can be preempted at that moment (Part 3). A `SCHED_FIFO` thread that gets the core keeps it until it blocks, yields, or is preempted by a higher priority. `SCHED_RR` is the same, except that threads of equal priority rotate every 100 ms. **The normal class only guarantees a share; the real-time class guarantees running as soon as you are ready.**

`SCHED_DEADLINE` orders tasks by "how much run time per period, and when is the deadline", earliest deadline first (EDF), and sits ahead of the real-time class. It suits periodic tasks and is rare in trading systems.

### 1.2 Setting It: Bake the Policy In When the Thread Is Created

The safest way is to put the policy into the attributes when creating the thread:

```cpp
bool start_rt_thread(pthread_t& t, int prio) {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);  // without this, the next two lines are ignored
    pthread_attr_setschedpolicy(&attr, SCHED_FIFO);
    sched_param sp{};
    sp.sched_priority = prio;                                      // SCHED_FIFO takes 1–99
    pthread_attr_setschedparam(&attr, &sp);
    int err = pthread_create(&t, &attr, hot_loop, nullptr);
    pthread_attr_destroy(&attr);
    if (err != 0) {                                                // the return value is the error code; errno is not set
        std::fprintf(stderr, "pthread_create: %s\n", std::strerror(err));  // no permission gives EPERM
        return false;
    }
    return true;
}
```

The default attribute is `PTHREAD_INHERIT_SCHED`: the new thread inherits the creator's policy, and the policy and priority written into the attributes are **silently ignored**, with no error. So the `PTHREAD_EXPLICIT_SCHED` line cannot be left out. The alternative is to create the thread first and change it with `pthread_setschedparam`, but between the two steps the thread already runs for a while under normal scheduling, and the hot thread's initialization may fall into that window.

The pthread functions return the error code directly and do not set `errno`, so use `strerror(err)`; `perror` would print some unrelated old value. The most common error is `EPERM`: setting a real-time priority needs `CAP_SYS_NICE`, or a raised `RLIMIT_RTPRIO` (`ulimit -r`, or `rtprio` in `/etc/security/limits.conf`).

`std::thread` has no scheduling interface, so change it through the native handle:

```cpp
void set_fifo(std::thread& t, int prio) {
    sched_param sp{};
    sp.sched_priority = prio;
    if (int err = pthread_setschedparam(t.native_handle(), SCHED_FIFO, &sp); err != 0)
        std::fprintf(stderr, "pthread_setschedparam: %s\n", std::strerror(err));
}
```

On the command line use `chrt`: `chrt -f 80 ./app` starts a program at `SCHED_FIFO` 80; `chrt -f -p 80 <tid>` changes an existing thread, and given a thread ID after `-p` it changes only that thread; add `-a` to change every thread of the process; `chrt -p <pid>` only shows. `ps -eLo tid,cls,rtprio,comm` lists each thread's class and priority.

### 1.3 RT Throttling: Stopped for 50 ms Every Second

By default the kernel sets `kernel.sched_rt_period_us = 1000000` and `kernel.sched_rt_runtime_us = 950000`: in every 1 s, real-time tasks may run at most 950 ms, and the remaining 50 ms is kept for normal tasks, so that a buggy real-time thread cannot lock up the machine. A busy-polling `SCHED_FIFO` thread fills the core completely, so it is forcibly stopped once a second for about 50 ms, and `dmesg` shows `sched: RT throttling activated`. For a market-data thread that is a 50 ms blackout every second.

Newer kernels (6.12 on) use a fair server instead: up to 50 ms per second is reserved for normal tasks, and it is only handed over when a normal task is actually waiting on that core. The other fix is to set `sched_rt_runtime_us` to −1 and turn throttling off entirely. **With throttling off, a buggy real-time thread really can lock up the core**, so pair it with isolation, so that nothing else lives on that core in the first place.

### 1.4 Starving Kernel Threads: ksoftirqd and kworker on the Same Core

Every core has its own kernel threads: `ksoftirqd/N` handles that core's softirqs, `kworker/N` does work queued to that core. Most of them run at normal priority. When a `SCHED_FIFO` thread busy-polls on core N, they never get a turn: network softirqs sent to that core pile up, and threads on other cores that wait for this core to finish some work get stuck too. Priority 99 also ties with kernel threads like `migration/N` and the watchdog, so even those are blocked.

That is why real-time priorities are usually 50–80, not 99, and why the core should have no other work to begin with: NIC interrupts moved away, unbound workqueues moved away (Part 4). That is the isolation of [#1](/posts/cpu-affinity-core-isolation-numa/) 1.2.

### 1.5 Spinning on the Same Core: the Lock Holder Never Gets the CPU

[#16](/posts/spinlock-implementation/) 1.2 said that spinning assumes the lock holder keeps running. A real-time priority breaks that assumption completely: thread H, `SCHED_FIFO`, spins on core 3 waiting for a lock; the holder L is also on core 3, at a lower priority. H never yields, so L never gets the core, the lock is never released, and H spins until RT throttling stops it. **On one core, a high-priority thread spinning on a lock held by a low-priority thread waits forever.** The fix is to keep the two sides of a spinlock on separate cores, or to switch to a lock that sleeps (the priority-inheritance lock of 2.2).

### 1.6 Do You Still Need a Real-Time Priority on an Isolated Core?

When the hot thread owns an isolated core, it is alone there and shares nothing; with `nohz_full` even the timer tick stops, and normal scheduling will not be preempted by anyone. What a real-time priority guards against here is whatever occasionally slips in: a thread nobody pinned, a kernel thread woken on that core. With a moderate real-time priority, a normal thread that slips in cannot take the core, at the cost of guarding against all three traps of 1.3–1.5. **A real-time priority decides who runs first on a shared core; on a core you already own, it is insurance.** Two setups are common: an isolated core with normal scheduling, relying on isolation to keep everyone out; or an isolated core with a moderate real-time priority and throttling turned off, for one more layer of insurance.

## 2. Priority Inversion: a High-Priority Thread Stuck Behind One in the Middle

### 2.1 Priority Inversion: a Thread in the Middle Cuts In

Three threads on one core: low-priority L holds lock `m`; high-priority H wakes, needs `m`, and blocks; then medium-priority M wakes. It does not need the lock, but it outranks L, so it takes the core. Now H waits for L to release the lock, and L waits for M to give up the core. H waits in total:

$$
T_H = \underbrace{t_L}_{\substack{\text{rest of L's} \\ \text{critical section}}} + \underbrace{\textstyle\sum t_M}_{\substack{\text{every medium-priority} \\ \text{thread that cuts in}}}
$$

The first term is unavoidable: a lock means waiting for the holder to finish, and a short critical section keeps it short. The second term has no bound: however long M runs, and however many Ms arrive, H waits that long; H has effectively been queued behind M, and the priorities are inverted. **The thing to cure is not "high waits for low" but a thread in the middle cutting in and making the wait unbounded.**

The best-known case is Mars Pathfinder in 1997: after landing, the system kept resetting. A high-priority bus-management task was waiting on a lock held by a low-priority meteorological-data task, while a medium-priority communications task held the CPU for a long time. The bus task missed its deadline, the watchdog decided the system had hung, and reset it. Engineers on the ground turned on the priority-inheritance option of that mutex, and the problem went away.

### 2.2 Priority Inheritance (PI): Whoever Blocks H Is Raised to H's Priority

Priority inheritance works like this: while H is blocked on lock `m`, the holder L is temporarily raised to H's priority. M now ranks below L and cannot take the core; L finishes its critical section, releases the lock, drops back to its own priority, and H gets the lock. If L is itself waiting on another lock `m2`, the holder K of `m2` is raised as well, and so on down the chain. H then only waits for the critical sections along the chain; the second term is gone.

A POSIX mutex turns it on through an attribute:

```cpp
void init_pi_mutex(pthread_mutex_t& m) {
    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_INHERIT);
    pthread_mutex_init(&m, &a);
    pthread_mutexattr_destroy(&a);
}
```

`std::mutex` has no such option; to use it you have to use `pthread_mutex_t` directly.

On Linux it is cheap. A PI lock sits on a PI futex: with no contention, locking is a single CAS that writes your thread ID into the lock word and, like an ordinary futex lock ([#16](/posts/spinlock-implementation/) 1.1), stays out of the kernel; only on contention does it enter the kernel (`FUTEX_LOCK_PI`), where the kernel finds the holder from the thread ID in the lock word and raises it. **Priority inheritance only costs anything when there is actual contention.**

It also has a blind spot: it needs a definite owner to raise. When H waits on a condition variable, a semaphore, or the readers of a reader-writer lock, it waits for "someone to signal", and there is no definite owner, so priority inheritance cannot help. If H waits on a condition variable for L to produce data and M cuts in and takes L's core, H is still held up. Proxy execution in newer kernels aims to cover this case too, and is being merged piece by piece.

### 2.3 Priority Ceiling (PP, Priority Protect): Raised to the Top the Moment You Lock

A priority ceiling gives each lock a preset ceiling priority, the highest among all threads that will ever use the lock. Whoever takes the lock is immediately raised to the ceiling, whether or not anyone is waiting, and drops back on release. The moment L takes the lock it is as high as H, so M cannot take its core from the start: the inversion is blocked before it happens. And because the holder already outranks every other user of the lock, none of them can preempt it, no chain of waiting forms, and H is held up by at most one critical section.

```cpp
void init_pp_mutex(pthread_mutex_t& m, int ceiling) {
    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_PROTECT);
    pthread_mutexattr_setprioceiling(&a, ceiling);                 // highest priority among all threads that use this lock
    pthread_mutex_init(&m, &a);
    pthread_mutexattr_destroy(&a);
}
```

The cost is on every lock: each lock and unlock changes the priority, which glibc has to enter the kernel for, so even an uncontended lock goes from one CAS (about 20 ns) to two system calls (about 0.2–2 µs). And you must know every user's priority in advance; a thread above the ceiling that tries to take the lock fails.

| | Priority inheritance (PI) | Priority ceiling (PP) |
|---|---|---|
| When it raises | Only once someone waits | As soon as the lock is taken |
| Cost with no contention | Same as a plain lock, one CAS | Every lock and unlock changes priority, entering the kernel |
| What you must know in advance | Nothing | The highest priority among all users |
| Chains of waiting | Possible, raised one by one | Blocked by at most one critical section |

**Little contention and an open set of users: use priority inheritance. A fixed set of users and a worst-case wait that must be bounded (hard real-time): use a priority ceiling.**

### 2.4 The Low-Latency Choice: Hot Threads Don't Share Locks with Low-Priority Threads

Priority inheritance and ceilings only shrink H's wait to one critical section. A hot thread does not want to wait even that long: the thread inside the critical section can take a page fault or an interrupt, so that section is not always short. So the usual hot-path practice is to share no lock at all. Data the hot thread hands off goes through an SPSC ring ([#4](/posts/lock-free-queue-logger-micro-batching/), [#18](/posts/thread-safe-queue/)); a ring has no owner, and the producer writes and moves on. Data the hot thread reads that changes rarely and is read often, like configuration, uses a double buffer with an atomic index ([#14](/posts/prefetch-warmup-double-buffer/) Part 3) or a seqlock, so the reader takes no lock. Only low-frequency shared state off the hot path uses locks, and then a priority-inheritance lock is the safety net. **The most thorough fix is to structure the system so a high-priority thread never has to wait for a low-priority one.**

## 3. The Kernel Must Be Preemptible Too: Preemption Modes and PREEMPT_RT

### 3.1 Non-Preemptible Windows: Nobody Takes the Core While the Kernel Holds a Spinlock

A real-time thread wakes and wants the core, but the thread on that core may be inside the kernel at that moment: holding a spinlock, with interrupts disabled, or running softirqs. These regions cannot be preempted, so the real-time thread waits until it leaves them, and the "run as soon as ready" of Part 1 is discounted here.

A normal kernel picks its preemption mode with the boot parameter `preempt=`, which only works if the kernel has `CONFIG_PREEMPT_DYNAMIC`:

- `none`: kernel code switches threads only at a few points such as returning to user space; best throughput, longest waits;
- `voluntary`: the kernel has explicit points where it may yield;
- `full`: kernel code can be preempted anywhere except while holding a spinlock or with interrupts off;
- `lazy` (6.13 on): preemption of normal tasks is deferred to the next timer tick, real-time tasks still preempt immediately.

Even with `full`, the spinlock and interrupts-off regions remain. On a busy machine, a real-time thread on a normal kernel can take hundreds of µs or even several ms from wake-up to running in the worst case.

### 3.2 PREEMPT_RT: Shrinking the Non-Preemptible Windows to the Minimum

PREEMPT_RT takes the remaining windows apart, with three main changes:

- **Spinlocks become sleeping locks**: most kernel `spinlock_t` locks become rt_mutex-based locks whose holder can be preempted, with priority inheritance built in; only `raw_spinlock_t` still really spins.
- **Interrupt handlers run in threads**: hard-interrupt handlers run in kernel threads (`irq/N-name`, `SCHED_FIFO` 50 by default), so a hot thread at 80 is not interrupted by their processing; the hardware entry into the interrupt remains, but it is short. A normal kernel booted with `threadirqs` gets this one too.
- **Softirqs run in threads as well**, and `printk` was rewritten so it no longer disables preemption for long.

It was merged into mainline in 6.12; before that you needed a distribution's `-rt` kernel. The worst-case wake-up latency drops to about 10–100 µs, at the cost of more context switches, heavier locks, and a few percent to over 10% less throughput.

### 3.3 HFT Often Skips the Real-Time Kernel

A real-time kernel lowers the worst-case time "from being woken to running". But an HFT hot thread is never woken: it busy-polls on an isolated core, makes no system calls on the hot path, and with kernel bypass its packets do not even go through the kernel network stack. The kernel is not on its path, so a real-time kernel does little for it and makes the kernel paths it does use slower. A real-time kernel pays off where the design relies on wake-ups: blocking queues, timers, interrupt-driven I/O, or many threads sharing a few cores (industrial control, audio processing). **A real-time kernel bounds the time from wake-up to running; a hot thread that never sleeps never pays it.**

## 4. Kernel and BIOS Tuning: a Layer-by-Layer Checklist

[#1](/posts/cpu-affinity-core-isolation-numa/) covered isolated cores, SMT, C-states and P-states, and [#3](/posts/hot-path-memory-allocators/) covered `mlockall` and TLB shootdowns. The remaining knobs are listed below by layer, each with what it changes, what it buys, and what it costs. The common idea is the one from #1: any mechanism designed for average efficiency, power saving or peak throughput can make a particular run slower, so turn it off on hot cores where you can; and turn off unused subsystems, which removes paths that can interrupt a hot core.

### 4.1 BIOS and Power: Turn Off Mechanisms Built for Averages and Peaks

- **C-states, P-states, SMT**: mechanisms and trade-offs in #1 Part 2. Turn them off in the BIOS too: on some platforms the hardware does its own frequency control (such as Intel's HWP), and changing only the OS side does not stop it.
- **Turbo**: a trade-off. Off, the frequency is fixed and every run takes the same time; on, a single core can be about 10%–30% faster, but the frequency moves with the number of active cores and the temperature. Turn it off for determinism; some teams keep Turbo and control the active core count and cooling instead.
- **Server BIOS performance presets**: usually called the power profile; choosing "performance" or "low latency" sets the items above together with uncore frequency and memory power saving.
- **HPET**: it does not normally send interrupts; what matters is the clock source. The kernel normally uses the TSC, and `clock_gettime` reads it in user space in about 20–30 ns; once the TSC is judged unreliable, the kernel falls back to HPET, and every read goes out to the chipset, about 0.5–1.5 µs. Check that `cat /sys/devices/system/clocksource/clocksource0/current_clocksource` says `tsc`.
- **VT-x / AMD-V**: turn it off if you run no virtual machines; it falls under "turn off whatever you don't use".

The OS-side commands: `cpupower frequency-set -g performance` pins the governor at the highest frequency; under Intel's `intel_pstate` driver, turning Turbo off is `echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo` (**writing 1 is what turns it off**), and under `acpi-cpufreq` it is `echo 0 > /sys/devices/system/cpu/cpufreq/boost`; to limit C-states, open `/dev/cpu_dma_latency`, write 0, and keep it open (#1 2.2).

### 4.2 Boot Parameters: a Few Beyond Isolation

- **`isolcpus`, `nohz_full`, `rcu_nocbs`, `irqaffinity`**: see #1 1.2.
- **`preempt=`**: see 3.1.
- **`threadirqs`**: runs interrupt handlers in kernel threads (`irq/N-name`), so they can be pinned and prioritized; the cost is one extra thread switch per interrupt.
- **`nowatchdog`, `nmi_watchdog=0`**: the soft-lockup detector thread wakes every few seconds, and the NMI watchdog uses a performance counter to fire NMIs periodically. Turning them off removes two kinds of interruption, at the cost of nobody reporting a real kernel hang.
- **`tsc=reliable`**: skips the kernel's periodic checks of the TSC (the clocksource watchdog compares it against another clock), so one jittery check cannot mark the TSC unreliable and fall back to HPET. The cost is that a real TSC problem goes unnoticed; on newer CPUs the TSC runs at a constant rate and is synchronized across cores, so the risk is small.
- **`mitigations=off`**: turns off the mitigations for CPU vulnerabilities such as Spectre and Meltdown. Their cost is mostly on entering and leaving the kernel: switching page tables on every system call (KPTI), clearing buffers before returning to user space, guarding indirect branches; each system call costs about 0.1–0.5 µs more. A hot path that stays out of the kernel is barely affected; **the cost is security**, so use it only on dedicated machines that run no outside code.
- **`transparent_hugepage=never`**: turns off transparent huge pages. The background thread `khugepaged` merges pages at times you don't control, and merging changes page tables, which triggers TLB shootdowns (#3 2.2).
- **`audit=0`, `ipv6.disable=1`, `mce=off`**: turn off unused subsystems. `mce=off` turns off hardware error reporting; only do it on test machines.

### 4.3 sysctl: Network

- **`net.core.busy_read`, `net.core.busy_poll`** (in µs): when a socket read finds no data, poll the NIC queue in the kernel for up to this long instead of sleeping until an interrupt. It saves the "interrupt → softirq → wake the thread" stretch, about 5–20 µs, at the cost of holding the CPU while polling. More on this with kernel bypass.
- **`net.core.netdev_max_backlog`**: the length of the per-core queue from the driver to the protocol stack. A burst that fills it drops packets (the second column of `/proc/net/softnet_stat` grows); raise it to avoid drops.
- **`net.core.somaxconn`**: the cap on `listen`'s accept queue, which matters for servers accepting many connections; trading clients have few, long-lived connections, so it matters little.
- **Turning off Nagle**: there is no global sysctl; each socket sets `setsockopt(TCP_NODELAY)` itself. `net.ipv4.tcp_low_latency` has done nothing since 4.14.
- **BBR, `tcp_fastopen`**: BBR is a congestion-control algorithm that affects throughput and queuing over long-distance links; fast open saves one round trip when connecting. Trading connections stay inside the data center and stay up once established, so both matter little.

### 4.4 sysctl: Memory

- **`vm.swappiness` and `mlockall`**: a lower swappiness only makes the kernel swap less; under memory pressure it still swaps. What actually keeps hot data from being swapped out is `mlockall(MCL_CURRENT | MCL_FUTURE)`, whose loophole is in #3 Part 2. The process needs `CAP_IPC_LOCK` or a large enough `RLIMIT_MEMLOCK`.
- **`vm.dirty_ratio`, `vm.dirty_background_ratio`**: the share of memory in dirty pages at which background writeback starts, and at which writing threads are made to wait. Lower values write in small, frequent batches instead of piling up several GB and writing at once, so a logging thread does not stall for hundreds of ms in `write()`; the cost is more disk writes.
- **`vm.zone_reclaim_mode=0`, `kernel.numa_balancing=0`**: when the local node runs out of memory, use remote memory directly instead of reclaiming local pages first; and do not let the kernel migrate pages automatically, since migration changes page tables and also triggers TLB shootdowns. NUMA is in #1 Part 3.
- **Turning off KSM**: KSM scans in the background and merges pages with identical contents, mostly for virtual machines; merging and splitting both change page tables.

### 4.5 Interrupts and Background Work

- **Stop irqbalance and bind NIC interrupts to housekeeping cores**: see #1 1.2. If irqbalance keeps running, it undoes your manual bindings.
- **`echo 0-1 > /sys/devices/virtual/workqueue/cpumask`**: unbound kernel workqueues run only on housekeeping cores 0 and 1. Work bound to a specific core is not affected.
- **Interrupt coalescing, `ethtool -C eth0 rx-usecs N`**: the NIC waits for N µs or a number of packets before raising an interrupt. Fewer interrupts save CPU, but each packet can wait up to N µs longer. `rx-usecs 100` is a throughput setting; for a low-latency market-data NIC set it to 0 and turn adaptive off, or use busy polling instead.

### 4.6 tuned: Saving the Checklist as a Configuration

Typing these knobs one by one, it is easy to miss one after a reboot, or to have another tool set it back. tuned is a background service that applies a configuration file (a profile) covering sysctl, sysfs, the frequency governor, `/dev/cpu_dma_latency` and boot parameters, and keeps them applied. The common ones:

- **`latency-performance`**: performance governor, C-states limited through `/dev/cpu_dma_latency`, performance-leaning energy settings, less swapping;
- **`network-latency`**: on top of that, turns off transparent huge pages and automatic NUMA balancing and turns on `busy_read` and `busy_poll`;
- **`cpu-partitioning`**: write `isolated_cores=2-7` in `/etc/tuned/cpu-partitioning-variables.conf`, and it generates the `isolcpus`, `nohz_full` and `rcu_nocbs` boot parameters and moves kernel threads and interrupts to the housekeeping cores.

Your own profile can say `include=network-latency` and add a few lines of its own, and the whole machine's tuning becomes a text file you can keep in git and diff. `tuned-adm active` shows which profile is in use, and `tuned-adm verify` checks whether any setting has been changed. Note that tuned, hand-written sysctl files and tools like irqbalance overwrite each other, so keep exactly one source. **Tuning should be reproducible: write it into a tuned profile instead of typing it one knob at a time.**
