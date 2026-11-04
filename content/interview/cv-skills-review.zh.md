---
title: "IV：简历技能行，容易被问到的"
date: 2026-11-04T00:00:00+08:00
slug: "cv-skills-review"
description: "简历“专业技能”里写了“熟悉”的每一行，面试官最可能顺着问的几题：C++ 语言、CPU 体系结构、低延迟优化、Linux 调优、并发、系统编程、性能剖析与测量。每题写答到哪一层，链到本站讲过的页面。"
weight: 4
toc: true
math: true
---

- **简历上写了“熟悉”，面试官就会顺着往下问**：这一页按简历“专业技能”的顺序，每一行挑出最可能被问到的几题，不求全。
- **标 ★ 的先过**：量化私募的 C++ 岗最常问语言、容器、智能指针和并发基础；体系结构和低延迟优化是简历的重点，被问到要能落到数字和自己做过的事上。没标 ★ 的扫一眼，能说出一两句就行。
- **复习的方法是先盖住“答到哪一层”自己答**：答不上，或者只能说出结论、说不出原因，就点开“本站”那一列的页面回看。
- **复习顺序是知识点 → 实习 → 项目 1**：这一页是第一步；实习各条和项目 1 的追问另外过。

## 1. C++：STL、智能指针、模板、RAII、移动语义、CRTP、RVO {#cpp}

- **这一行几乎一定会问**：C++ 岗的一面通常从这里开始，问的是“底层怎么实现”，不是“怎么用”。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| ★ `vector` 扩容 | 容量满了就申请一块更大的内存（libstdc++ 是 2 倍，MSVC 是 1.5 倍），把元素搬过去，释放旧的，所以 `push_back` 均摊 O(1)。搬完以后旧的迭代器、指针、引用全部失效。元素的移动构造是 `noexcept` 才用移动，否则用拷贝，为的是扩容中途抛异常时原数组还完好。知道大小就先 `reserve` | [STL 容器](/zh/ref/stl-containers/) |
| ★ `map` 和 `unordered_map` | `map` 是红黑树，有序，查找 O(log n)；`unordered_map` 是哈希表，桶数组加链表节点，平均 O(1)，最坏 O(n)。元素数超过“桶数 × 负载因子（默认 1）”就 rehash，所有元素重新分桶，迭代器失效，但指向元素的指针和引用不失效。热路径上按代码查找，能用数组下标就别用哈希表 | [STL 容器](/zh/ref/stl-containers/)、[三种有序结构](/zh/ref/skiplist-rbtree-bplustree/) |
| ★ `shared_ptr` 怎么实现 | 对象指针加一个控制块，控制块里有强引用计数、弱引用计数和删除器。计数用原子操作增减，所以线程安全的是计数本身，不是指向的对象。`make_shared` 把对象和控制块一次分配。两个对象互相持有 `shared_ptr` 会循环引用、永远不释放，其中一边改成 `weak_ptr` | [shared_ptr](/zh/ref/shared-ptr/)、[unique_ptr 和 weak_ptr](/zh/ref/unique-ptr-weak-ptr/) |
| ★ `unique_ptr` 的开销 | 独占所有权，只能移动不能拷贝。用默认删除器时和裸指针一样大，解引用也一样快，所以没有理由用裸指针管理所有权 | [unique_ptr 和 weak_ptr](/zh/ref/unique-ptr-weak-ptr/) |
| ★ 移动语义和 `std::move` | 右值引用绑定“马上要死的对象”，移动构造把它的资源（比如堆上的缓冲区）直接拿过来、把源置空，省掉一次深拷贝。`std::move` 本身什么都不移动，只是 `static_cast` 成右值引用，让重载选中移动版本。完美转发是万能引用加 `std::forward`，保持实参原来的左值或右值身份 | [移动语义](/zh/ref/move-semantics/) |
| ★ RAII | 资源在构造函数里获取、在析构函数里释放。抛异常时栈展开会调用已构造对象的析构函数，所以资源不会泄漏，`lock_guard` 就是这样保证锁一定被释放。析构函数不要抛异常 | [构造、拷贝、析构和 RAII](/zh/ref/special-members-raii/) |
| ★ 虚函数怎么实现 | 每个有虚函数的对象开头有一个 vptr，指向它所属类的 vtable；同一个虚函数在父类和每个子类的表里都在同一格，所以调用时编译器只要“读 vptr → 读第几格 → 跳过去”。贵的地方主要不是这次间接跳转，而是编译器不知道调的是谁，没法内联。基类的析构函数要写成 virtual | [虚函数](/zh/ref/virtual-functions/)、[对象布局](/zh/ref/object-layout/) |
| ★ CRTP 为什么能替代虚函数（简历上写了） | 子类把自己当模板参数传给基类，基类里 `static_cast<Derived*>(this)` 去调，编译期就知道调的是谁，能内联，对象里也没有 vptr。代价是 `Base<A>` 和 `Base<B>` 是两个不相关的类型，放不进同一个容器 | [CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/) |
| RVO 和 NRVO | C++17 起，返回一个纯右值（`return T(...)`）保证直接构造在调用方的位置上，不拷贝也不移动。返回具名局部变量（NRVO）编译器通常会做，但不保证。`return std::move(x);` 反而会挡住 NRVO | [返回值优化](/zh/posts/rvo-pure-functions/) |
| 模板 | 每种模板实参实例化一份代码，代价是编译时间和代码体积；特化和偏特化给特定类型换实现；约束模板参数从 SFINAE 到 C++20 的 concepts | 待补 |

## 2. CPU 体系结构：缓存、MESI、store buffer、ROB、LFB、分支预测、TLB、NUMA {#cpu}

- **这一行写得最长，被问到就要能落到数字**：先在[硬件地图](/zh/ref/cpu-memory/)上说清它在哪一层，再给量级，再连到自己做过的优化。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| ★ 各级缓存的延迟 | L1D 约 1 ns（4–5 周期），L2 约 3–5 ns，L3 约 10–30 ns，内存约 70–120 ns；L1、L2 每核私有，L3 全核共享。缓存行 64 B，一次至少搬一整行 | [CPU 与内存](/zh/ref/cpu-memory/) |
| ★ 伪共享（简历：环形缓冲区计数按缓存行隔离） | 两个线程写的变量不同，但在同一条缓存行上。每次写都要先拿到这条行的独占权，行就在两个核之间来回搬，一次跨核约 20–100 ns。用 `alignas(64)` 把它们隔到不同的行。实习里环形缓冲区的读写计数就是这样隔开的，写入延迟中位数降了约 40% | [#2 内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/) |
| ★ MESI | 每条行在每个核里有四种状态：M（改过、只有我有）、E（没改、只有我有）、S（多个核都有）、I（无效）。写之前必须拿到独占：别的核的副本先作废，回了 ACK 才能写。读一条在别人那里是 M 的行，由那个核直接转发过来 | [MESI](/zh/posts/low-latency-mesi-cache-coherence/) |
| store buffer 和 StoreLoad 重排 | store 先进 store buffer，流水线不等独占权就往下走，等的是队首那条 store。所以“先写 A、再读 B”可能让别的核看到读在写前面，这是 x86 唯一允许的重排。`seq_cst` 的 store 在 x86 上编成 `xchg`，就是为了堵住它 | [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) |
| 乱序执行和 ROB | 指令按依赖关系乱序执行，按程序顺序退休；ROB 有几百项。一条读内存的 load 卡在队首时，后面的指令把 ROB 填满就只能停下 | [CPU 与内存](/zh/ref/cpu-memory/)、[缓存案例](/zh/posts/low-latency-cache-case-study/) |
| LFB 和内存级并行 | 每个核约 10–16 个 LFB，同时在路上的 L1 缺失最多这么多。单核带宽 ≈ 在途数 × 64 B ÷ 延迟，所以单核读内存到不了整机带宽 | [内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/) |
| ★ 分支预测 | 一条分支要十几个周期后才知道往哪走，CPU 只能先猜。猜对几乎不花钱，猜错要把之后的活全部扔掉，约 15–20 个周期。数据有规律就猜得准，随机就只能猜对一半，经典例子是数组排序后同一个循环快好几倍 | [#7 分支预测](/zh/posts/branch-prediction-branch-optimization/) |
| TLB 和大页 | TLB 缓存虚拟地址到物理地址的翻译，每个核一份，L1 dTLB 64–96 项，二级 1500–3000 项，每项管一页。4 KiB 的页一共只盖几 MiB；2 MiB 的大页一项盖 512 倍。没命中要走页表，多 15–30 ns | [上下文切换、页表与 TLB](/zh/posts/low-latency-context-switch-page-table-tlb/)、[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/) |
| NUMA | 多插槽的机器，每个插槽有自己的内存，读另一个插槽的内存更慢、带宽更低。物理页在第一次写的时候落在写它的那个节点上（first touch），所以内存要在绑好核的线程里初始化，或者用 `numactl --membind` 指定 | [#1 CPU 隔离与 NUMA](/zh/posts/cpu-affinity-core-isolation-numa/) |

## 3. 低延迟优化方法 {#optimization}

- **每一条都能挂到实习里做过的事**：答完原理，接一句“我在哪里用过、效果多少”。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| ★ 热路径为什么不能 `malloc` | `malloc` 的耗时不确定：可能要抢锁、找合适的空闲块，还可能调 `brk` / `mmap` 进内核，第一次碰到新页还会缺页。内存池启动时一次分好固定大小的块，用 free list 管理，分配和释放都是 O(1)；arena 只往后顺序分配，到时候整体释放。实习里回测按交易日复用同一块内存，耗时降了约 44% | [#3 内存池与分配器](/zh/posts/hot-path-memory-allocators/)、[new 一次走到哪](/zh/ref/new-malloc-page-fault/) |
| ★ 依赖链和多累加器（简历：拆分串行累加的依赖链） | 只用一个累加器时，每次加法都要等上一次的结果，被加法的延迟（约 4 周期）卡住，CPU 的两个加法单元大半时间空着。拆成 4–8 个累加器各加各的，最后再合起来，吞吐就上去了。代价是浮点加法的顺序变了，末位会变，和研究侧对拍时要按容差比（[Python 与 C++](/zh/interview/python-cpp-consistency/) 1.1） | [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) |
| ★ 无分支写法（简历上写了） | 把依赖数据、猜不准的 `if` 改成 `cmov`、掩码或查表，不用猜就不会猜错。分支本来就猜得准时反而可能更慢：分支猜对了可以提前往下跑，`cmov` 必须等条件算出来 | [#7](/zh/posts/branch-prediction-branch-optimization/) |
| ★ 数据布局 | 按访问模式摆数据：热字段放在一起、冷字段挪出去，一次处理只碰少数几条缓存行；按字段批量扫描时用 SoA（每个字段一个数组）比 AoS 更省带宽，也更好向量化 | [#6 内存对齐与布局](/zh/posts/alignment-layout-cache-dram-geometry/) |
| 预取和预热 | 软件预取（`__builtin_prefetch`）提前几百 ns 把下一批数据要过来，提前太多会把还要用的行挤掉。预热是启动时把内存页都碰一遍、把热路径空跑几遍，让缺页、缓存和分支预测器都先热起来；实习里启动时预触内存页，消掉了首轮的缺页 | [#14 预取、预热与双缓冲](/zh/posts/prefetch-warmup-double-buffer/) |
| SIMD | 一条指令同时算 4 个（AVX2）或 8 个（AVX-512）double。编译器自动向量化要求循环之间没有依赖、指针不会互相别名、内存连续；浮点求和要放开结合律才会被向量化，这又会改末位 | [#15 SIMD](/zh/posts/simd-vectorization-intrinsics/) |
| 强度削弱和定点数 | 把除法换成乘以倒数或移位，把乘法换成加法；价格用放大后的整数存，既快，又不会有浮点取整的问题 | [#12 强度削弱](/zh/posts/strength-reduction-arithmetic/) |

## 4. Linux 低延迟调优：绑核、隔离、中断亲和、实时调度、大页 {#linux-tuning}

- **QD 岗问得少，能说清每个手段解决什么就够**：重点是“为什么要这样做”，命令记个名字就行。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| 绑核和核心隔离 | 绑核（`pthread_setaffinity_np`、`taskset`）让线程不被挪到别的核，否则换核后 L1、L2 和 TLB 都是冷的。`isolcpus` 让调度器不往这些核上放别的任务，`nohz_full` 再去掉时钟中断 | [#1](/zh/posts/cpu-affinity-core-isolation-numa/) |
| 中断亲和 | 网卡中断默认可能落在热线程的核上，打断它；改 `/proc/irq/N/smp_affinity` 把中断挪到别的核 | [#1](/zh/posts/cpu-affinity-core-isolation-numa/) |
| 实时调度和优先级反转 | `SCHED_FIFO` 的线程不会被普通线程抢占。优先级反转：低优先级线程拿着锁，被中优先级线程抢走 CPU，高优先级线程等锁一直等下去；办法是优先级继承锁 | [#19 调度与优先级反转](/zh/posts/scheduling-priority-inversion-kernel-tuning/) |
| 大页 | 用 hugetlbfs 预留大页，或者开透明大页（THP），减少 TLB 缺失。THP 的 `khugepaged` 会在后台合并页、改页表，可能带来抖动，低延迟场景常关掉 | [#19](/zh/posts/scheduling-priority-inversion-kernel-tuning/)、[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/) |

## 5. 多线程与并发 {#concurrency}

- **基础题一定会问，无锁那几个是加分项**：互斥锁、条件变量、原子变量和内存序要答到“为什么这样写才对”。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| ★ 内存序：relaxed、acquire、release、seq_cst | relaxed 只保证这一个变量的读写是原子的，不管前后顺序。release 写配上 acquire 读：读到这个值的线程，能看到写方在 release 之前写的所有东西，这就是“发布数据”的标准写法。seq_cst 再加一条所有线程看到同一个全局顺序。x86 上 acquire 和 release 都是普通的 `mov`，只有 seq_cst 的 store 要 `xchg` | [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) |
| ★ 条件变量为什么要配锁和 while | 等待方在锁里检查条件，`wait` 原子地“放锁并睡下”，否则检查完、睡下之前的通知会丢。醒来要在 `while` 里重新检查条件，因为可能是虚假唤醒，也可能被别的线程抢先拿走了数据 | [线程同步](/zh/ref/thread-sync/) |
| ★ 死锁和怎么避免 | 四个条件：互斥、持有并等待、不可抢占、循环等待。实际最常用的办法是破坏循环等待：所有线程按同一顺序加锁，或者用 `std::scoped_lock` 一次锁住多把 | [线程同步](/zh/ref/thread-sync/) |
| ★ 线程池 | 一个任务队列加几个工作线程，队列用互斥锁加条件变量保护；提交任务时用 `packaged_task` 包一层，调用方拿 `future` 等结果 | [线程池和 future](/zh/ref/thread-pool-future/) |
| lock-free 和 wait-free | lock-free 保证总有某个线程在前进，但某个线程可能一直 CAS 失败重试；wait-free 保证每个线程的步数都有上界。SPSC 环满了就返回失败的接口是 wait-free，满了就空转等的是阻塞式 | [#17 wait-free](/zh/posts/wait-free-sticky-counter/) |
| SPSC 无锁队列 | 生产者只写 tail、消费者只写 head，各自用 release 发布、用 acquire 读对方，不需要 CAS。容量取 2 的幂，下标用 `& (N-1)` 代替取模；head 和 tail 放在不同的缓存行，再各自缓存一份对方的下标，少读对方的行 | [#4 无锁队列](/zh/posts/lock-free-queue-logger-micro-batching/)、[#18 线程安全队列](/zh/posts/thread-safe-queue/) |
| 自旋锁：TTAS、票据锁、MCS | TTAS 先用普通读等锁看起来空闲了再 CAS，等待时不反复抢独占权；票据锁按取号顺序拿锁，公平；MCS 每个等待者在自己的节点上自旋，锁释放时只惊动下一个 | [#16 自旋锁](/zh/posts/spinlock-implementation/) |

## 6. Linux 系统编程：进程与 IPC、epoll、mmap、虚拟内存与缺页 {#system}

- **进程线程和缺页最常被问**：网络那半句（TCP/IP、HTTP、WebSocket）简历上写的是“了解”，过一遍下面链的几页 ref 就够。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| ★ 进程和线程的区别 | 进程是资源的容器：地址空间、fd 表、信号处理函数；线程是在容器里跑的执行流：寄存器、栈、TLS。线程切换和进程切换的直接开销差不多，都在 1 到几 µs；差别在切换以后，同一进程的线程还能接着用 TLB 和缓存 | [进程和线程](/zh/ref/process-thread-fork/) |
| ★ `fork` 和写时复制 | `fork` 只复制页表，父子进程共用物理页，页标成只读；谁先写，谁触发缺页，内核这时才复制那一页。多线程程序 `fork` 后子进程里只剩调 `fork` 的那个线程 | [进程和线程](/zh/ref/process-thread-fork/) |
| ★ 虚拟内存和缺页（简历：启动时预触内存页） | `new` → `malloc` → `brk` / `mmap` 拿到的只是一段虚拟地址，第一次访问才缺页、分配物理页，每次几百 ns 到几 µs。所以实习里启动时先把内存全碰一遍，热路径上就不再缺页 | [new 一次走到哪](/zh/ref/new-malloc-page-fault/) |
| IPC 有哪几种 | 管道、消息队列、共享内存、信号、socket。共享内存最快，数据不用经过内核拷贝，但同步要自己做 | [进程间通信](/zh/ref/ipc/) |
| `mmap` | 把文件或匿名内存映射进地址空间；读文件时少一次从内核缓冲区到用户缓冲区的拷贝，按页懒加载 | [new 一次走到哪](/zh/ref/new-malloc-page-fault/)、[文件 IO](/zh/ref/file-io/) |
| epoll | 用红黑树存要监听的 fd，就绪的 fd 由内核回调挂到就绪链表上，`epoll_wait` 只取这个链表，不像 `select` 那样每次扫一遍所有 fd。水平触发只要还有数据就一直通知，边缘触发只在状态变化时通知一次，要一次读到 `EAGAIN` | [epoll](/zh/ref/epoll-internals/) |
| 网络（简历写的是“了解”） | 三次握手、四次挥手、TIME_WAIT；TCP 怎么做到可靠；一次 HTTP 请求的全过程 | [TCP 状态](/zh/ref/tcp-states/)、[TCP 可靠传输](/zh/ref/tcp-reliability/)、[HTTP](/zh/ref/http-basics/)、[socket 编程](/zh/ref/socket-programming/) |

## 7. 工具：perf、火焰图、TSC 测量、分位数、ASan/UBSan {#tools}

- **这一行和实习、项目 1 都连着**：答工具怎么用时，顺手讲一次自己用它找到了什么。

| 题目 | 答到哪一层 | 本站 |
|---|---|---|
| ★ perf 怎么用 | 先 `perf stat` 看整体：IPC、缓存缺失、分支预测失败；再 `perf record -g` 加 `perf report` 找热点函数；最后 `perf annotate` 看热点落在哪几条指令上。火焰图横向宽度是采样占比，不是时间先后。实习里用它找到日志后台线程空转，调整轮询间隔后 CPU 占用降了 31% | [perf 专题](/zh/posts/low-latency-perf-profiling/) |
| ★ 怎么测一段代码的延迟 | 用 `rdtsc` / `rdtscp` 读 TSC，现代 x86 的 TSC 恒定频率、各核同步；前后要加栅栏，防止被测的指令被乱序挪到计时外面；换算成 ns 要用校准过的频率；空测一次计时本身的开销再减掉 | [#20 用 TSC 测延迟](/zh/posts/tsc-latency-measurement/) |
| ★ 为什么报分位数不报平均 | 延迟分布是长尾的，平均值会被少数尖刺拉高，也可能把它们藏起来；报 P50、P99、P99.9，尖刺在哪个分位上一目了然。实习里单包处理延迟就是按中位数和 P99 报的 | [#21 交易系统性能衡量](/zh/posts/trading-system-latency-metrics/) |
| ASan 和 UBSan | ASan 查越界、释放后使用、重复释放，程序会慢约 2 倍；UBSan 查有符号溢出、空指针、未对齐访问这类未定义行为。只在测试构建里开 | [IV：量化 C++ 题目](/zh/interview/quant-infra-cpp/) |
| 编译选项会不会改结果 | `-O2` 换 `-O3` 一般不改浮点结果；`-march=native` 打开 FMA 会改末位；`-ffast-math` 会删掉 NaN 判断、重排求和，因子代码里不能开 | [Python 与 C++](/zh/interview/python-cpp-consistency/) 第 5 节 |
