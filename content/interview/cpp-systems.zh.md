---
title: "IV：C++ 系统题目：UB、内存序、无锁哈希表、futex 锁、DAG 调度"
date: 2026-11-11
slug: "cpp-systems"
aliases: ["/interview/cpp-systems-five/"]
description: "C++ 系统方向的题目：未定义行为、严格别名和释放后使用；x86 上的内存序和同一条缓存行上的 ping-pong；无锁哈希表和基于纪元的回收；用 futex 实现互斥锁、把线程 id 缓存在 TLS 里；单线程 DAG 调度器和用线程池并行化。每道写题目和简短答法，知识点展开在对应的知识页。"
weight: 2
toc: true
math: true
---

这些题问的是同一件事的几个侧面：代码写出来以后，编译器、CPU、内核各自会对它做什么。每道写题目和简短答法，知识点的展开放在对应的知识页里，这里给链接。

## 1. UB、严格别名、释放后使用：为什么出错的地方离写错的地方很远 {#ub}

**题目**：解释 C++ 的未定义行为（UB）、严格别名（strict aliasing）和释放后使用（UAF），说明它们在实际代码里会引发什么问题。

> **三样东西是一回事：编译器假设它们不会发生**
>
> - **UB 是标准不规定结果的行为**：编译器按“程序里没有 UB”这个前提去优化，可以据此删代码、重排代码。
> - **所以同一份代码 `-O0` 下好好的，`-O2` 就坏了**：坏的地方往往不是写错的那一行，而是被编译器据此改写过的另一处。
> - **严格别名和释放后使用是 UB 里最常见的两类**：前一类让编译器不重读内存，后一类让指针指向别人的数据。

**展开见速查[未定义行为](/zh/ref/undefined-behavior/)**：UB 的三个例子（第 2 节）、严格别名和 `memcpy`（第 3 节）、释放后使用的三种常见形式和对象池里的版本号（第 4 节）、怎么用 sanitizer 查（第 5 节）。

## 2. x86 上的内存序和 ping-pong：硬件只重排“先写后读”，慢的是缓存行在核之间来回搬 {#memory-order}

**题目**：解释内存序（memory order）在 x86 上的表现，并结合 MESI 说明同一条缓存行上的 ping-pong。

> **x86 只会把“先写后读”乱序，慢的是缓存行在核之间来回搬**
>
> - **x86 是 TSO**：写先进 store buffer，后面读另一个地址的指令可以先完成，所以只有“先写后读”会乱。`acquire`、`release` 在 x86 上都是普通的 `mov`；`seq_cst` 的写编成 `xchg`，等 store buffer 排空，才管得住它。
> - **写一条缓存行之前要先独占它**：两个核轮流写，这条行就在两个核的缓存之间来回搬，每次 20–100 ns。伪共享改布局隔开，真共享只能让每个核大多数时候只写自己的行。

**展开见 [#2 第 3 节案例](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case)**：3.1 x86 上的内存序，3.2 ping-pong 的来回和两种，3.3–3.5 真共享的三个修法（计数器、队列下标、自旋锁），3.6 用 `perf c2c` 分辨。

## 3. 无锁哈希表和 epoch 回收：表不难写，难的是旧节点什么时候能释放 {#lockfree-map}

**题目**：设计并实现一个无锁哈希表，说明怎么用基于纪元的回收（epoch-based reclamation，和 RCU 是同一个思路）做平滑回收。

> **表用固定容量加开放寻址，难的是旧节点什么时候能释放**
>
> - **表**：键用 CAS 占槽，写进去就不再改，删除只把值指针换成空；更新时分配新节点，一次原子交换换上去，读者要么看到旧的、要么看到新的。
> - **回收用 epoch**：读者进出临界区时公告自己在第几代，写者把旧节点按摘下时的代数挂起；全局纪元比它多 2，摘之前进来的读者都已经离开，才释放。弱点是一个读者卡在临界区里，内存就一直涨。
> - **不追求无锁时**：按哈希低位分片，每片一把锁；释放交给后台线程，写线程只入队。

**展开见 [#3 第 6 节案例](/zh/posts/hot-path-memory-allocators/#case-lockfree-map)**：6.1 表的代码，6.2 epoch 回收的代码和“为什么多 2 才能释放”，6.3 读者卡住时的取舍以及 hazard pointer、RCU，6.4 分片加锁和后台回收。

## 4. futex 互斥锁和 TLS 里的线程 id：没人抢时不进内核，抢不到才睡 {#futex}

**题目**：用 `futex_wait_private` 实现一个互斥锁，并说明怎么实现放在 TLS 里的线程 id（tid）。

### 4.1 锁：三个状态，解锁时才知道要不要叫人 {#futex-mutex}

- **futex 是什么**：内核提供的“在一个地址上睡下、在一个地址上叫醒”。`FUTEX_WAIT(addr, val)` 的意思是：如果 `*addr` 还等于 `val`，就睡；否则立刻返回。检查和睡下在内核里是一步，中间不会漏掉一次叫醒。
- **锁的状态放在用户态的一个原子变量里**：0 是没锁，1 是锁住且没人等，2 是锁住且可能有人等。

```cpp
#include <atomic>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <unistd.h>

class FutexMutex {
    std::atomic<int> state_{0};   // 0 没锁，1 锁住没人等，2 锁住可能有人等

public:
    void lock() {
        // 1. 快路径：没人持有，0 → 1，一次 CAS 就拿到锁，不进内核
        int c = 0;
        if (state_.compare_exchange_strong(c, 1, std::memory_order_acquire)) return;
        // 2. 没抢到：把状态改成 2，告诉解锁的人“有人在等”
        //    exchange 返回 0，说明锁正好被放开，这一下就拿到了
        if (c != 2) c = state_.exchange(2, std::memory_order_acquire);
        while (c != 0) {
            // 3. 状态还是 2 才睡；已经变了就立刻返回，再抢一次
            syscall(SYS_futex, &state_, FUTEX_WAIT_PRIVATE, 2, nullptr, nullptr, 0);
            // 4. 醒来再抢。不知道后面还有没有人在等，所以设成 2，不是 1
            c = state_.exchange(2, std::memory_order_acquire);
        }
    }

    void unlock() {
        // 5. 旧值是 2 才可能有人在睡，叫醒一个；旧值是 1 就不进内核
        if (state_.exchange(0, std::memory_order_release) == 2)
            syscall(SYS_futex, &state_, FUTEX_WAKE_PRIVATE, 1, nullptr, nullptr, 0);
    }
};
```

- **为什么要分 1 和 2**：只有“锁住”一种状态的话，解锁时不知道有没有人在等，只能每次都去叫，每次解锁都是一次系统调用，约 50–150 ns。分开以后，没人抢时加锁、解锁各是一次原子操作。
- **醒来以后设成 2 是保守的做法**：最多让下一次解锁多叫一次，换来的是不会漏掉还在睡的线程。
- **`_PRIVATE` 的意思**：这个 futex 只在本进程里用。内核直接拿“地址空间加虚拟地址”当键，不用去查这一页对应的物理页。
- **内存序**：拿到锁的那次 CAS 或 `exchange` 用 `acquire`，放锁的写用 `release`，临界区里的读写就不会越过加锁和解锁。同步全靠这个原子变量，futex 系统调用本身只负责睡和叫醒。
- **可以先自旋一小会儿再睡**：临界区很短时，转几十圈就能等到锁，比睡下再被叫醒快得多。自旋放在第 2 步之前，循环里只读不写，读到 0 再 CAS。

公平性、锁里存持有者的 tid 有什么用，见 [IV：量化 C++ 开发 2.5](/zh/interview/quant-infra-cpp/#futex-mutex)；自旋和退避见 [#16 自旋锁](/zh/posts/spinlock-implementation/)。

### 4.2 tid：`gettid` 是一次系统调用，所以每个线程只取一次 {#tid}

```cpp
#include <sys/syscall.h>
#include <unistd.h>

inline pid_t current_tid() {
    // 1. 每个线程各有一份 t_tid；第一次调用时取一次，之后直接读
    thread_local pid_t t_tid = 0;
    if (__builtin_expect(t_tid == 0, 0)) t_tid = static_cast<pid_t>(syscall(SYS_gettid));
    return t_tid;
}
```

- **为什么要缓存**：打日志、记录锁的持有者，每次都要线程 id。一次系统调用约 50–150 ns，读一个 `thread_local` 变量是一条 `mov`。
- **`thread_local` 怎么实现**：Linux x86-64 上，每个线程的 TLS 块地址放在 `fs` 段寄存器里，变量按 `%fs:偏移` 访问。主程序和启动时就加载的动态库，偏移在加载时就定了，一条指令；`dlopen` 进来的动态库要调 `__tls_get_addr` 去查，可以用 `-ftls-model=initial-exec` 换回一条指令（[线程同步](/zh/ref/thread-sync/)）。
- **`fork` 之后要清掉**：子进程里这个线程的 tid 变了，缓存的却是从父进程拷过来的旧值。在 `pthread_atfork` 的子进程回调里把它置 0。
- **和锁的关系**：优先级继承锁（`FUTEX_LOCK_PI`）要求锁字里存持有者的 tid，内核靠它找到持有者，临时提高它的优先级（[#19 优先级反转](/zh/posts/scheduling-priority-inversion-kernel-tuning/)）。每次加锁都要写 tid，所以 tid 必须读得便宜。

## 5. DAG 调度器：单线程按拓扑序跑，并行靠原子的入度计数 {#dag}

**题目**：实现一个单线程的 DAG 调度器，并说明怎么用线程池把它并行化。

### 5.1 单线程：入度为 0 的先跑，跑完把后继的入度减 1 {#dag-serial}

```cpp
#include <queue>
#include <vector>

struct Graph {
    int n = 0;
    std::vector<std::vector<int>> succ;   // succ[v]：v 跑完以后才能跑的节点
    std::vector<int> indeg;          // indeg[v]：v 还要等几个前驱
    explicit Graph(int n) : n(n), succ(n), indeg(n, 0) {}
    void add_edge(int u, int v) { succ[u].push_back(v); ++indeg[v]; }
};

// 单线程：返回一个拓扑序；有环返回空
std::vector<int> topo_order(const Graph& g) {
    // 1. 入度拷一份来减，入度为 0 的先进就绪队列
    std::vector<int> indeg = g.indeg, order;
    std::queue<int> ready;
    for (int v = 0; v < g.n; ++v)
        if (indeg[v] == 0) ready.push(v);
    // 2. 取一个就绪的排进去，它的后继入度各减 1，减到 0 的就绪
    while (!ready.empty()) {
        int v = ready.front(); ready.pop();
        order.push_back(v);
        for (int s : g.succ[v])
            if (--indeg[s] == 0) ready.push(s);
    }
    // 3. 环上的节点入度永远减不到 0，所以排出来的不足 n 个
    if ((int)order.size() != g.n) order.clear();
    return order;
}
```

- **复杂度是 $O(V + E)$**：每个节点进出队列各一次，每条边只看一次。
- **图不变、每来一条行情都要跑一遍**：拓扑序只算一次存下来，之后按这个顺序执行，不用每次重新排。

### 5.2 并行：谁把后继的计数减到 0，谁提交它 {#dag-parallel}

线程池用最基本的那种，`submit` 收一个 `void()` 的任务（[线程池和 future 第 3 节](/zh/ref/thread-pool-future/)）。

```cpp
// 并行跑一遍无环图：每个节点调一次 fn(v)，并且在它所有前驱的 fn 返回之后
class DagRun {
public:
    DagRun(const Graph& g, ThreadPool& pool, std::function<void(int)> fn)
        : g_(g), pool_(pool), fn_(std::move(fn)), pending_(g.n), remaining_(g.n) {}

    void run() {
        if (g_.n == 0) return;
        // 1. 每个节点还要等几个前驱，放进原子计数
        for (int v = 0; v < g_.n; ++v) pending_[v].store(g_.indeg[v]);
        // 2. 入度为 0 的直接提交
        for (int v = 0; v < g_.n; ++v)
            if (g_.indeg[v] == 0) pool_.submit([this, v] { exec(v); });
        // 3. 等全部节点跑完
        std::unique_lock<std::mutex> lk(m_);
        cv_.wait(lk, [this] { return done_; });
    }

private:
    void exec(int v) {
        fn_(v);
        // 1. 后继的计数各减 1；fetch_sub 返回旧值，旧值是 1 说明是我把它减到了 0，由我提交
        //    两个前驱同时跑完也只有一个线程看到 1，所以每个节点正好提交一次
        for (int s : g_.succ[v])
            if (pending_[s].fetch_sub(1, std::memory_order_acq_rel) == 1)
                pool_.submit([this, s] { exec(s); });
        // 2. 我是最后一个跑完的，叫醒 run()；done_ 在锁里改，通知才不会丢
        if (remaining_.fetch_sub(1, std::memory_order_acq_rel) == 1) {
            std::lock_guard<std::mutex> lk(m_);
            done_ = true;
            cv_.notify_all();
        }
    }

    const Graph& g_;
    ThreadPool& pool_;
    std::function<void(int)> fn_;
    std::vector<std::atomic<int>> pending_;
    std::atomic<int> remaining_;
    std::mutex m_;
    std::condition_variable cv_;
    bool done_ = false;
};
```

- **每个节点正好提交一次**：一个节点有几个前驱同时跑完，它们各自做一次 `fetch_sub`，只有一个线程拿到旧值 1。
- **前驱的输出，后继一定看得到**：前驱在 `fn_` 里写输出，再 `fetch_sub`；提交后继的线程是做了最后一次 `fetch_sub` 的那个。`acq_rel` 让这几次 `fetch_sub` 之前的写，对后面执行这个后继的线程都可见。
- **等待结束要用锁里的标志**：最后一个节点跑完，在锁里置 `done_` 再通知。只通知、不置标志，`run()` 要是还没睡下，这次通知就丢了。

### 5.3 取舍：节点太小，调度的开销就盖过计算 {#dag-tradeoff}

- **一次入队加出队约 100 ns–1 µs**，还可能叫醒一个睡着的线程。节点里只有几十纳秒的计算时，并行反而更慢。只有一个后继的链要合并成一个任务。
- **就绪的后继自己留一个接着跑，其余的再提交**：数据还在当前核的缓存里，也少一次入队。
- **所有线程共用一个队列，会一起抢队头那把锁**：改成每个线程一个双端队列，自己从一头取放，没活干的线程从别人的另一头偷（work stealing）。
- **加速比有上限**：设全部节点的工作量是 $T_1$，最长的那条依赖链是 $T_\infty$，$p$ 个线程的耗时 $T_p \ge \max(T_1 / p,\ T_\infty)$。最长的链占了大头时，加再多线程也没用。
- **某个节点失败**：它下游的节点都不能跑了，但“还剩几个没完成”的计数要照样扣掉，否则等待的线程永远等不到结束。
- **图是固定的，就不要动态调度**：预先把节点按层分好，同一层的节点互不依赖，整层并行地跑，层和层之间汇合一次。因子计算就是这种图：中间量被几个上层因子共用，图在开盘前就定了。这样写更简单，延迟也更稳定；代价是同一层里最慢的节点会拖住下一层。
