---
title: "IV：量化 C++ 开发、infra 题目和知识点"
date: 2026-11-02
slug: "quant-infra-cpp"
description: "一组量化方向 C++ 开发、交易系统开发、infra 岗的面试题：问答题按 C++、工具链、并发与体系结构、操作系统、性能测量五块整理，手撕题写思路和追问，每条标出本站哪里讲过。"
weight: 1
toc: true
---

这组题来自一位第一次面量化方向的同学，岗位是 C++ 开发、交易系统开发和 infra，面的是几家传统量化私募和一家币圈量化。它的特点很集中：**几乎不问项目，问答从 C++ 一路问到 CPU 和内核，手撕题没有一道是常见的算法题，全是并发和内存管理。** 所以准备的重点不是刷题，而是把“这行代码在机器上发生了什么”讲清楚。

下面每道题写三样东西：考的是什么，答到哪一层算到位，本站哪里讲过。“待补”表示本站还没有对应的页面。

## 1. 问答题

### 1.1 C++ 语言：标准规定了什么，编译器借此做了什么 {#cpp}

这一块问得很杂，从未定义行为（UB）到 C++26 的提案都有。它们背后是同一个问题：**标准把某件事定为 UB，编译器就假设它永远不发生，并据此删代码、重排代码。** 能把这一层讲出来，比背 UB 清单有用。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| 常见的 UB | 有符号整数溢出、数组越界、空指针解引用、读未初始化的变量、数据竞争、违反严格别名。编译器假设它们不发生：比如 `x + 1 > x` 直接折成 `true`，循环变量是 `int` 时不再考虑溢出，可以放心展开和向量化 | 待补，散见[类型双关](/zh/posts/type-punning-calls-compiler-hints/) |
| 严格别名 | 两个不同类型的指针（`char`、`unsigned char`、`std::byte` 除外）被认为不指向同一个对象，所以编译器写完一个以后不必重读另一个。用 `float*` 去读 `int` 的内存是 UB，开 `-O2` 后结果可能和 `-O0` 不同；合法的写法是 `memcpy` 或 `std::bit_cast`，编出来通常只有一条 `mov` | [四种 cast](/zh/ref/cpp-casts/)、[类型双关](/zh/posts/type-punning-calls-compiler-hints/) |
| UAF（释放后使用） | 对象释放后还通过旧指针访问。那块内存可能已经分给了别人，表现随机，往往在很远的地方才出错。查：AddressSanitizer；防：用 `unique_ptr`、`shared_ptr` 把所有权写进类型，观察者用 `weak_ptr::lock()` | [智能指针](/zh/ref/smart-pointers/) |
| 副作用和求值顺序 | `i = i++ + 1` 这类在 C++17 以前是 UB。C++17 规定了 `=` 右边先算、`<<` 和 `>>` 从左到右、`a[b]` 先算 `a`；但函数的几个实参之间的顺序仍然不定，只是不再交错 | 待补 |
| 小端和字节序 | x86 和 ARM（默认）都是小端：低字节放低地址。网络字节序是大端，收发时用 `htons` / `ntohl` 转。判断本机：C++20 的 `std::endian::native` | [socket 编程](/zh/ref/socket-programming/) |
| 模板 | 两阶段名字查找、特化和偏特化、变参模板、SFINAE 到 concepts；每种实参实例化一份代码，代价是编译时间和体积 | 待补 |
| CRTP | 子类把自己当模板参数传给基类，基类 `static_cast` 回子类调用，编译期绑定、能内联、没有 vptr；代价是 `Base<A>` 和 `Base<B>` 放不进同一个容器 | [CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/) |
| `thread_local` 怎么实现 | Linux x86-64 上每个线程的 TLS 块地址放在 `fs` 段寄存器里，变量按 `%fs:偏移` 访问。主程序和启动时就加载的 `.so` 用静态 TLS，一条指令；`dlopen` 进来的 `.so` 偏移启动时不知道，要调 `__tls_get_addr` 查。Windows 是 `gs` 指向的 TEB 里的 TLS 槽，ARM64 用 `TPIDR_EL0` 寄存器 | [线程同步](/zh/ref/thread-sync/) |
| C++26 的 `std::hive` | 分块存储的无序容器：元素地址一旦确定就不再移动，删除只在原位留空并记下跳过的长度，插入优先复用空位，遍历时跳过空位。适合频繁增删、又要长期持有指针的对象集合，前身是 `plf::colony` | 待补 |
| C++26 的静态反射 | P2996：`^^T` 得到一个编译期的反射值（`std::meta::info`），可以遍历类的成员、取名字和类型，再用 `[: ... :]` 把它拼回代码里。最直接的用途是自动生成序列化、枚举转字符串，不用再写宏 | 待补 |

### 1.2 工具链：符号怎么找到，优化能跨多远 {#toolchain}

工具链的问题围绕两件事：链接器怎么把各个目标文件里的符号对上，优化能不能跨过编译单元的边界。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| 编译的几个阶段 | 预处理、编译（前端出 IR，中端优化，后端出汇编）、汇编、链接 | [从源码到进程](/zh/ref/cpp-linux/#build) |
| 链接做了什么 | 符号解析：每个未定义的符号找到唯一定义；重定位：把地址填进引用它的地方。静态库按需取 `.o`，所以命令行上的顺序有影响；动态库的符号在加载时由 `ld.so` 解析 | [从源码到进程](/zh/ref/cpp-linux/#build) |
| ODR（单一定义规则） | 普通函数和变量全程序只能有一个定义；`inline` 函数和模板可以出现在多个编译单元里，但每份必须完全相同。不同的话是 UB，链接器随便挑一份，**不报错** | [从源码到进程](/zh/ref/cpp-linux/#build) |
| PIC（地址无关代码） | 代码不依赖自己被加载到哪：模块内部用 RIP 相对寻址；访问别的模块的数据经过 GOT（一张地址表），调别的模块的函数经过 PLT，第一次调用时才解析。`.so` 必须是 PIC；主程序编成 PIE，才能享受地址随机化 | [从源码到进程](/zh/ref/cpp-linux/#build) |
| 链接期内联（LTO） | `-flto` 时目标文件里存的不是机器码，而是中间表示（GCC 的 GIMPLE、LLVM 的 bitcode）。链接时把所有 IR 合起来，再做一遍跨文件的内联和优化，最后才生成机器码。ThinLTO 只合并摘要、分模块并行，编译快很多 | 待补 |
| 常用优化参数 | `-O2` / `-O3`、`-march=native`（用上本机指令集，但二进制换台机器可能跑不了）、`-flto`、PGO（`-fprofile-generate` 跑一遍再 `-fprofile-use`）、`-fno-plt`；`-ffast-math` 会改变浮点结果 | 待补 |
| LLVM 后端有哪些阶段 | 中端在 IR 上做内联、SROA、GVN、LICM、循环向量化等；后端依次是指令选择（SelectionDAG 或 GlobalISel）、指令调度、寄存器分配、插入函数序言和尾声、窥孔优化，最后发射机器码 | 待补 |

### 1.3 并发和体系结构：每个说法都要落到硬件 {#concurrency}

这是问得最多的一块。区别于一般后端面试的地方在于，**每个并发问题都要讲到指令、缓存行和周期数**，只说“加锁”“用原子变量”不够。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| memory order 在 x86 上怎么表现 | x86 是 TSO：只有“先写后读”会被重排（写先进 store buffer，后面的读可能先完成）。所以 acquire 读、release 写编出来就是普通 `mov`，只有 `seq_cst` 写要用 `xchg`（或 `mov` 加 `mfence`）。但编译器的重排照样要靠 `atomic` 的内存序来约束；ARM 的硬件重排更多，屏障是真指令 | [内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/) |
| MESI 和同一缓存行上的 ping-pong | 两个核轮流写同一条 64 字节的缓存行，每次写都要让对方的副本失效、把行搬过来，一次几十到上百 ns。两个变量只是碰巧在同一行也一样（伪共享），解法是 `alignas(64)` 分开 | [MESI 缓存一致性](/zh/posts/low-latency-mesi-cache-coherence/) |
| 无锁容器 | CAS 循环；ABA 问题；节点什么时候能安全释放 | [无锁队列](/zh/posts/lock-free-queue-logger-micro-batching/)、[线程安全队列](/zh/posts/thread-safe-queue/) |
| lock-free 和 wait-free | lock-free：任何时刻总有一个线程在前进，但某个线程可能一直 CAS 失败；wait-free：每个线程都在有限步内完成，比如用 `fetch_add` 而不是 CAS 循环 | [wait-free](/zh/posts/wait-free-sticky-counter/) |
| 流水线停顿 | 分支预测失败一次约 15–20 个周期；缓存未命中按层级从几 ns 到上百 ns；长的数据依赖链让乱序执行无事可做 | [分支预测](/zh/posts/branch-prediction-branch-optimization/)、[硬件地图](/zh/ref/cpu-memory/) |

### 1.4 操作系统：用户态和内核态之间的代价 {#os}

操作系统的题几乎都在问同一笔账：**进一次内核、拷一次数据、缺一次页、错过一次 TLB 各要多少，以及怎么绕开。**

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| 零拷贝 | 普通的 `read` 再 `write` 要在内核和用户缓冲区之间拷两次；`sendfile` / `splice` 让数据只在内核里走，`mmap` 让用户态直接看页缓存 | [IO 总图](/zh/ref/cpp-linux/#io)、[进程间通信](/zh/ref/ipc/) |
| NUMA | 多路服务器上每个 CPU 插槽有自己的内存，访问对面插槽的内存更慢。做法：线程绑核，内存在本节点分配（`numactl`，或者先 first-touch） | [CPU 隔离与 NUMA](/zh/posts/cpu-affinity-core-isolation-numa/) |
| mmap 和大页 | 4 KiB 的页太多，TLB 装不下就要查页表。2 MiB 大页让一条 TLB 项覆盖 512 倍的范围。hugetlbfs 是预留的大页、必须显式申请，THP 是内核自动合并、可能带来不可控的停顿 | [new 一次走到哪](/zh/ref/new-malloc-page-fault/)、[内存池与分配器](/zh/posts/hot-path-memory-allocators/) |
| 页表 | x86-64 四级页表，每次地址翻译先查 TLB，未命中再由硬件逐级查表；页不在内存时触发缺页，由内核补上 | [进程地图](/zh/ref/cpp-linux/#map)、[硬件地图](/zh/ref/cpu-memory/) |
| 协程怎么实现 | 有栈协程：每个协程一块自己的栈，切换就是保存、恢复寄存器和栈指针（`ucontext`、boost.context）。C++20 是无栈协程：编译器把函数改写成状态机，局部变量放进堆上的协程帧，`co_await` 处保存状态并返回调用方 | 待补 |
| 一次系统调用的过程 | glibc 把调用号放进 `rax`、参数放进寄存器，执行 `syscall` 指令；CPU 切到内核态、换到内核栈，内核保存寄存器、按调用号查表调用实现，最后 `sysret` 回来。`clock_gettime` 这类走 vDSO，根本不进内核 | 待补 |
| OS 怎么管理 RSS | RSS 是进程实际占着的物理页。`malloc` 只拿到虚拟地址，第一次写才缺页分配物理页；内存紧张时内核按活跃、不活跃两个 LRU 链表回收页缓存和匿名页（换出到 swap），cgroup 可以限住上限。`free` 不一定把内存还给内核 | [new 一次走到哪](/zh/ref/new-malloc-page-fault/)、[LRU 缓存](/zh/ref/lru-cache/) |
| io_uring | 用户态和内核共享两个环：提交队列和完成队列。一次可以批量提交很多请求，只进一次内核；开 SQPOLL 后由内核线程轮询提交队列，连这一次也省了 | 待补 |

### 1.5 性能测量和线程池 {#perf}

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| perf | `perf stat` 看总体计数（IPC、缓存未命中、分支预测失败），`perf record` 加 `perf report` 找热点 | [perf](/zh/posts/low-latency-perf-profiling/) |
| 怎么严肃地做微基准 | 预热（缓存、分支预测器、TLB 都要先热起来，CPU 频率也要升上去）；调频策略设成 `performance`、关睿频；绑核并隔离；用大页排除 TLB 抖动；跑很多次看分布（中位数和 p99），不只看平均；防止编译器把被测代码优化掉 | [用 TSC 测延迟](/zh/posts/tsc-latency-measurement/)、[调度与内核调参](/zh/posts/scheduling-priority-inversion-kernel-tuning/) |
| 线程池的 work stealing | 每个线程一个双端队列，自己从一端放、从同一端取（后进先出，缓存热）；自己空了就从别人队列的另一端偷。共享的只有偷的那一端，竞争比一个全局队列小得多。经典实现是 Chase-Lev 双端队列 | 待补，基础线程池见[线程池和 future](/zh/ref/thread-pool-future/) |

## 2. 手撕题

### 2.1 对象池：多线程分配，单线程回收 {#object-pool}

题目要求像 pmr 的 `synchronized_pool_resource` 那样：存储是一串大小翻倍的块（`list<T[N]>`，下一块是 `2N`），空闲槽用一个无锁的侵入式 LIFO 栈管理。

**为什么这样设计。** 块只追加、不搬家，已经分出去的对象地址一直有效；大小翻倍，扩容次数是对数级。空闲槽本身没在用，正好拿它的前 8 个字节存“下一个空闲槽”的指针，这就是侵入式：栈不需要额外的节点。

**分配**是从栈顶弹出：读 `head` 和 `head->next`，CAS 把 `head` 换成 `next`。**回收**只有一个线程，把槽压回栈顶。栈空时要扩容，这是慢路径，用一把互斥锁保护就够了，快路径仍然无锁。

追问几乎一定是 **ABA**：CAS 只比较值，`head` 从 X 变成别的、又变回 X，CAS 看不出来。线程 A 读到 `head = X`、`next = Y` 后被换下，别的线程拿走 X 和 Y、又把 X 还回来，A 回来 CAS 成功，栈顶却成了正被别人用着的 Y。解法是给 `head` 带一个版本号，每次修改加 1，CAS 同时比较下标和版本号（32 位下标加 32 位版本号打包进 64 位，或用 16 字节的 CAS）。内存序：弹出的 CAS 用 acquire，压入用 release，保证拿到槽的线程看得到上一个使用者写完的内容。

本站：[内存池与分配器](/zh/posts/hot-path-memory-allocators/)第 1 节讲池和空闲链表，[第 5 节](/zh/posts/hot-path-memory-allocators/#aba) 有 ABA 的时刻表和无锁版本的完整代码。

### 2.2 优化 SPSC 场景下的移动平均 {#sma}

一个线程推价格，一个线程算最近 N 个价格的简单移动平均（SMA）。原实现用 mutex 加条件变量传数据，`std::deque` 存窗口，`std::map` 按品种查，每条消息 `new` / `delete`。逐项换：

- **队列**：只有一个生产者和一个消费者，换成无锁环形队列。生产者只写尾、消费者只写头，两个下标放在不同缓存行上，用 acquire / release 同步，不需要锁也不需要进内核睡眠。见[无锁队列](/zh/posts/lock-free-queue-logger-micro-batching/)。
- **窗口**：定长的环形缓冲区，加上一个运行中的总和，新价格进来加上它、减去被挤出的那个，每次 O(1)。浮点数一直加减会累积误差，可以定期重算一次，或者价格用整数（最小变动单位）表示。
- **查找**：`std::map` 是红黑树，每次查找都要跟着指针走好几层；换成哈希表，品种数固定时直接用数组按编号索引更好。
- **分配**：换成 pmr 的内存池或启动时预分配，热路径上不再调 `malloc`。见[内存池与分配器](/zh/posts/hot-path-memory-allocators/)。
- **向量化**：窗口重算这类循环可以用 `#pragma clang loop vectorize(enable)` 提示，前提是数据连续、对齐、指针之间不重叠。见 [SIMD 向量化](/zh/posts/simd-vectorization-intrinsics/)。

追问是“你怎么证明快了”，答案就是 1.5 节的微基准方法。

### 2.3 无锁哈希表 {#lockfree-hashmap}

这道是币圈量化问的。思路是**分片加 RCU**：按哈希值的低几位分成若干片，每片单独处理，写和写之间的冲突被分散开；读的路径完全不加锁。

写者修改时不就地改，而是复制一份、改好，再用一次原子写把指针换过去。难点在于旧版本什么时候能释放：可能还有读者正拿着它。epoch（或 RCU）的办法是，读者进入时登记“我在第 e 代”，离开时注销；写者把旧版本挂上“第 e 代退休”的标签，等所有读者都离开了第 e 代，才真正释放。

追问是**回收怎么做才平滑**：不在写者线程里当场释放，而是把退休的对象放进队列，由后台线程批量释放，写路径上就没有长停顿。代价是某个读者迟迟不退出，会拖住整代的回收，内存会涨。另一种方案是 hazard pointer：读者登记的是具体指针，回收更精确，但每次读都要多一次写和一次内存屏障。

本站：待补。

### 2.4 并行化一个 DAG 调度器 {#dag}

给一个单线程的 DAG 调度器和一个线程池，要求并行化。基础是拓扑排序：**入度为 0 的节点都已就绪，可以一起提交给线程池。** 每个节点执行完，把它所有后继的入度原子减 1（`fetch_sub`），减到 0 的那个线程负责提交这个后继。最后用一个完成计数（或 `std::latch`）通知所有节点都已跑完。

两种提交方式的差别在关键路径：按层批量提交写起来简单，但同一层里最慢的节点会拖住下一层；完成一个就立刻提交它的后继，关键路径更短。节点很小的时候，调度本身的开销会超过计算，要把小节点合并。

本站：基础线程池见[线程池和 future](/zh/ref/thread-pool-future/)，DAG 调度待补。

### 2.5 用 futex 实现 mutex {#futex-mutex}

这道追问最深。面试者的写法是两状态：锁字里存持有者的线程 id，空闲时是一个特殊值；加锁 CAS，失败先自旋一定次数，再 `futex_wait` 睡；解锁写回空闲值、`futex_wake`。它能用，但有一个问题：**解锁时不知道有没有人在等，只能每次都调 `futex_wake`**，而那是一次系统调用。

标准做法是三个状态（Drepper《Futexes Are Tricky》）：0 是没锁，1 是锁住且没人等，2 是锁住且可能有人等。

```cpp
#include <atomic>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <unistd.h>

static void futex_wait(std::atomic<int>* a, int val) {
    syscall(SYS_futex, reinterpret_cast<int*>(a), FUTEX_WAIT_PRIVATE, val, nullptr, nullptr, 0);
}
static void futex_wake(std::atomic<int>* a, int n) {
    syscall(SYS_futex, reinterpret_cast<int*>(a), FUTEX_WAKE_PRIVATE, n, nullptr, nullptr, 0);
}

class Mutex {
    std::atomic<int> s_{0};   // 0 没锁，1 锁住没人等，2 锁住可能有人等
public:
    void lock() {
        int c = 0;
        if (s_.compare_exchange_strong(c, 1, std::memory_order_acquire)) return;   // 快路径
        if (c != 2) c = s_.exchange(2, std::memory_order_acquire);
        while (c != 0) {
            futex_wait(&s_, 2);                          // 值仍是 2 才睡
            c = s_.exchange(2, std::memory_order_acquire);
        }
    }
    void unlock() {
        if (s_.fetch_sub(1, std::memory_order_release) != 1) {   // 原来是 2：可能有人在等
            s_.store(0, std::memory_order_release);
            futex_wake(&s_, 1);
        }
    }
};
```

没人抢的时候，加锁一次 CAS、解锁一次 `fetch_sub`，都不进内核。醒来的线程把状态设成 2 而不是 1，因为它不知道身后还有没有别人在等，宁可多唤醒一次也不能漏。要加自旋，就放在 `exchange(2)` 之前，循环里只读不写，读到 0 再 CAS。

**内存序怎么分析**：拿到锁的那次 CAS 或 `exchange` 用 acquire，释放锁的写用 release，这一对保证临界区里的读写不会越过加锁和解锁。futex 系统调用本身不承担 C++ 意义上的同步，同步全靠这个原子变量。`futex_wait` 在内核里会再检查一次“值是不是还是 2”，不是就立刻返回。这正是“先检查再睡”，防的是检查和睡下之间的那次唤醒被漏掉（[epoll](/zh/ref/epoll-internals/) 里的等待队列是同一个道理）。

**锁字里存线程 id 有什么用**：能检查“解锁的是不是持有者”、支持递归锁和死锁诊断。Linux 的优先级继承锁（`FUTEX_LOCK_PI`）就要求锁字存持有者的 tid，再用一个最高位标记有人在等，内核据此把持有者的优先级临时提高。

**公平性**：`futex_wake` 唤醒一个线程，但它醒来之前，刚到的线程可能直接 CAS 成功插了队。这样吞吐高，等着的线程却可能一直抢不到。要公平，可以用 ticket lock（按号排队），或者解锁时把锁直接交给被唤醒的线程；排队锁 MCS 让每个等待者在自己的缓存行上自旋，核多的时候也不会集体抢同一行。glibc 的 mutex 默认不保证公平。

本站：[自旋锁](/zh/posts/spinlock-implementation/)讲了 CAS、自旋和退避，[线程同步](/zh/ref/thread-sync/)讲了 mutex 的快路径和进内核睡。

## 3. 还没写的

按这组题，本站还缺这些：UB 和求值顺序的专题、模板和元编程、C++26 的 `std::hive` 和静态反射、LTO 和 LLVM 的优化阶段、协程的实现、一次系统调用的完整路径、io_uring、work stealing 线程池、无锁栈和 ABA、epoch 和 RCU 回收、DAG 调度器。**最值得先补的是无锁栈加 ABA 和 epoch 回收**：对象池和无锁哈希表两道手撕题都建在它们上面。futex 锁的代码已经在 2.5 节，单独成页时再补上测试。
