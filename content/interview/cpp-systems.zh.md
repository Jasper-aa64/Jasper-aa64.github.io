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

> **两个问题，一个管对不对，一个管快不快**
>
> - **内存序管的是正确性**：一个核写的值，另一个核什么时候看得到、按什么顺序看到。
> - **ping-pong 管的是性能**：两个核轮流写同一条缓存行，这条行就在两个核的缓存之间来回搬。
> - **两件事背后是同一套硬件**：每个核私有的缓存、64 字节的缓存行、store buffer、MESI。

**展开见 [#2 内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/)**：

- **内存序**：x86 只允许“先写后读”这一种乱序，以及两个线程各自先写再读的例子（[1.3](/zh/posts/memory-ordering-false-sharing-dependency-chains/#four-reorderings)）；每种内存序在 x86 和 ARM 上编成什么、贵在哪（[1.6](/zh/posts/memory-ordering-false-sharing-dependency-chains/#cost)）。
- **ping-pong**：缓存行为什么来回搬（[2.1](/zh/posts/memory-ordering-false-sharing-dependency-chains/#cache-line-unit)）；伪共享和真共享各自怎么修、怎么用 `perf c2c` 分辨（[2.5](/zh/posts/memory-ordering-false-sharing-dependency-chains/#ping-pong)）。

## 3. 无锁哈希表和 epoch 回收：表不难写，难的是旧节点什么时候能释放 {#lockfree-map}

**题目**：设计并实现一个无锁哈希表，说明怎么用基于纪元的回收（epoch-based reclamation，和 RCU 是同一个思路）做平滑回收。

> **先把形状定下来：难做的部分尽量不做**
>
> - **固定容量、不扩容**：扩容是无锁哈希表里最难的部分。键的个数有上限（比如合约 id）时，直接按上限开够。
> - **开放寻址、线性探测**：槽连续放在一个数组里，探测时访问的是相邻的内存。
> - **键一旦写进槽就不再改，删除只把值指针换成空**：探测链不会断，找键这一步也不需要任何保护。代价是删掉的键仍然占着槽，所以键的总数不能超过容量。
> - **值不就地改**：更新时分配一个新节点，一次原子交换把指针换过去。读者要么看到旧节点、要么看到新节点，不会看到改了一半的。
> - **剩下的问题只有一个**：换下来的旧节点可能还有读者正在读，什么时候能释放。这就是 epoch 回收要解决的。

### 3.1 表：键用 CAS 占槽，值用指针原子交换 {#map}

```cpp
#include <atomic>
#include <cstdint>
#include <utility>
#include <vector>

struct Node {
    uint64_t val;
    explicit Node(uint64_t v) : val(v) {}
};

class Ebr;   // 回收器，定义在 3.2

// 固定容量、开放寻址的无锁哈希表：键是非 0 的 64 位整数，值是指向节点的指针
class LockFreeMap {
public:
    LockFreeMap(size_t cap_pow2, Ebr& ebr) : slots_(cap_pow2), mask_(cap_pow2 - 1), ebr_(ebr) {}

    // 插入或更新；表满了返回 false
    bool put(int tid, uint64_t key, uint64_t val) {
        Slot* s = find_slot(key, true);
        if (!s) return false;
        // 1. 不就地改：分配一个新节点，一次原子交换把指针换过去
        Node* old = s->node.exchange(new Node(val), std::memory_order_seq_cst);
        // 2. 换下来的旧节点可能还有读者在读，交给 Ebr
        if (old) ebr_.retire(tid, old);
        return true;
    }

    // 删除：只把值指针换成空；键留在槽里，探测链不会断
    void erase(int tid, uint64_t key) {
        Slot* s = find_slot(key, false);
        if (!s) return;
        Node* old = s->node.exchange(nullptr, std::memory_order_seq_cst);
        if (old) ebr_.retire(tid, old);
    }

    bool get(int tid, uint64_t key, uint64_t& out) {
        // 1. 进临界区：从这里到 leave，读到的节点都不会被释放
        ebr_.enter(tid);
        Slot* s = find_slot(key, false);
        Node* n = s ? s->node.load(std::memory_order_seq_cst) : nullptr;
        if (n) out = n->val;
        // 2. 值已经拷出来了，离开以后不再碰 n
        ebr_.leave(tid);
        return n != nullptr;
    }

private:
    struct Slot {
        std::atomic<uint64_t> key{0};        // 0 表示空槽
        std::atomic<Node*> node{nullptr};
    };

    // 线性探测。键一旦写进槽就不再改，所以找键这一步不需要保护
    Slot* find_slot(uint64_t key, bool claim) {
        size_t i = (key * 0x9E3779B97F4A7C15ull) >> 32 & mask_;
        for (size_t n = 0; n <= mask_; ++n, i = (i + 1) & mask_) {
            uint64_t cur = slots_[i].key.load(std::memory_order_acquire);
            if (cur == key) return &slots_[i];
            if (cur != 0) continue;
            // 1. 碰到空槽：查找到此为止；插入就用 CAS 把它占下来
            if (!claim) return nullptr;
            if (slots_[i].key.compare_exchange_strong(cur, key, std::memory_order_acq_rel)) return &slots_[i];
            // 2. CAS 失败说明别人刚占了这个槽；占的正好是同一个键就用它，否则接着往后找
            if (cur == key) return &slots_[i];
        }
        return nullptr;
    }

    std::vector<Slot> slots_;
    size_t mask_;
    Ebr& ebr_;
};
```

- **两个线程同时插入同一个键**：只有一个 CAS 成功，失败的那个看到槽里已经是这个键，直接用它。两个线程随后各自交换值指针，后换的留下，先换的那个节点被当成旧节点交给回收。
- **读路径没有锁，也不写共享的缓存行**（读者自己的那条公告除外，见 3.2），所以多个读者之间不会互相拖慢。

### 3.2 回收：旧节点等所有读者都离开它那一代，再释放 {#ebr}

- **全局有一个纪元号**。读者进临界区时公告“我在第 e 代”，离开时标成不在。
- **写者把节点摘下来以后不马上释放**：记下摘的时候是第几代，放进自己的待释放列表。
- **纪元怎么前进**：所有在临界区里的线程都已经公告了当前这一代，纪元才能加 1。
- **为什么是多 2 才能释放**：节点在第 r 代被摘下。可能还拿着它的读者，都是摘之前进来的，公告的代数不超过 r。这样的读者只要还在，纪元最多前进到它的代数加 1，也就是不超过 r + 1。所以纪元到了 r + 2，这些读者一定都已经离开。

```cpp
// 基于纪元的回收：读者进临界区时公告自己所在的纪元，旧节点等所有读者都离开那个纪元才释放
class Ebr {
public:
    static constexpr int kMaxThreads = 64;
    static constexpr uint64_t kIdle = ~0ull;   // 不在临界区里

    // 读者进入：公告“我在第 e 代”
    void enter(int tid) {
        // 1. 公告（写）之后才去读共享指针（读）：先写后读正是 x86 会重排的那一种，所以用 seq_cst
        rec_[tid].epoch.store(global_.load(std::memory_order_seq_cst), std::memory_order_seq_cst);
    }
    // 读者离开：之后不再碰临界区里拿到的任何指针
    void leave(int tid) { rec_[tid].epoch.store(kIdle, std::memory_order_release); }

    // 写者：n 已经从表里摘下来，新来的读者拿不到它；记下摘的时候是第几代
    void retire(int tid, Node* n) {
        auto& limbo = rec_[tid].limbo;
        limbo.push_back({global_.load(std::memory_order_seq_cst), n});
        // 1. 攒够一批再处理，释放不是每次写都做
        if (limbo.size() < 64) return;
        try_advance();
        // 2. 纪元比节点的那一代多了 2，摘它之前进来的读者都已经离开，可以释放
        uint64_t g = global_.load(std::memory_order_seq_cst);
        size_t keep = 0;
        for (auto& [e, p] : limbo) {
            if (e + 2 <= g) delete p;
            else limbo[keep++] = {e, p};
        }
        limbo.resize(keep);
    }

private:
    // 所有在临界区里的线程都已经公告了当前这一代，纪元才能加 1
    void try_advance() {
        uint64_t g = global_.load(std::memory_order_seq_cst);
        for (auto& r : rec_) {
            uint64_t e = r.epoch.load(std::memory_order_seq_cst);
            if (e != kIdle && e != g) return;   // 有读者还停在旧的一代，这次不推进
        }
        global_.compare_exchange_strong(g, g + 1, std::memory_order_seq_cst);
    }

    struct alignas(64) Rec {
        std::atomic<uint64_t> epoch{kIdle};
        std::vector<std::pair<uint64_t, Node*>> limbo;   // 这个线程摘下来、还没释放的节点
    };
    Rec rec_[kMaxThreads];
    std::atomic<uint64_t> global_{0};
};
```

- **“平滑”指的是什么**：读路径上没有释放；写路径上攒够一批才处理一次；没有任何一步要让所有线程停下来等。要更平滑，可以把待释放列表交给后台线程去放。
- **公告要用 `seq_cst`**：读者先写自己的公告、再读共享指针，正是 x86 会重排的“先写后读”（[#2 1.3](/zh/posts/memory-ordering-false-sharing-dependency-chains/#four-reorderings)）。重排以后，写者扫描时看不到这个读者，读者却已经拿到了旧节点。
- **线程编号**：代码里由调用方传 `tid`，实际用的时候每个线程第一次进来时登记一个，存在 `thread_local` 里。

### 3.3 取舍：一个读者卡住，内存就一直涨 {#ebr-tradeoff}

- **epoch 回收的弱点**：只要有一个读者停在临界区里不出来（被调度走了、死循环了），纪元就推进不了，所有线程的待释放列表都只进不出。
- **hazard pointer 是另一种方案**：读者公告的不是“我在第几代”，而是“我正在用这个指针”。一个读者卡住只拖住它公告的那几个节点，待释放的内存有上限。代价是每读一个节点都要多一次公告的写，而且同样是先写后读，要一道全屏障。
- **RCU 是同一个思想在内核里的做法**：读端几乎不花钱；写端等一个宽限期，确认每个 CPU 都经过了一次不在读端临界区的时刻，再释放。纪元前进两次，相当于一个宽限期。
- **交易系统里常见的做法是绕开它**：
  - **按合约分片，每个线程只碰自己那一片**：表根本不共享，也就没有回收问题（[交易系统架构 3.2](/zh/ref/trading-architecture/#shard)）。
  - **节点从固定大小的池里取，用完还回池里，永远不还给系统**：读到的最多是被复用的槽，配上版本号就能发现（1.3）。
  - **热线程都绑在隔离核上、一直在跑**：读者不会被调度走，纪元推得动，epoch 回收的弱点碰不到。

### 3.4 另外两种做法：按哈希低位分片加锁，回收交给后台线程 {#shard-lock}

**按哈希低位分片加锁：不追求无锁，把一把大锁拆成很多把小锁**

- **怎么拆**：开 $2^k$ 个分片，每个分片是一张普通哈希表加一把锁。键算出哈希 $h$ 后，用低 $k$ 位 `h & (2^k - 1)` 选分片，只锁这一片。
- **为什么够用**：两个线程只有落到同一片时才会互相等，分片数取线程数的几倍，撞上的概率就很低。读多写少时，每片用读写锁或者 seqlock，读者几乎不等。
- **一个容易踩的地方**：分片用了哈希的低位，分片里面选桶就不能再用同样的低位，否则一个分片里的键低位全相同，只落在几个桶里。分片里改用高位，或者用 $h \gg k$ 再取模。
- **代价**：拿锁要一次原子操作，抢同一片时要排队；读者也拿锁（互斥锁或读写锁）时没有回收问题，删掉的节点在锁里直接释放，因为拿到锁之后不会有人还在读它；读者用 seqlock 不拿锁时，又回到要延迟释放。

**回收交给后台线程：热路径上只入队，不释放**

- **做法**：写线程把换下来的旧节点连同当时的纪元，放进一个队列（每个写线程一条 SPSC 队列就够），立刻返回。后台线程不断从队列里取，等到纪元前进两次、确认没有读者还拿着它，再 `delete`。
- **为什么更平滑**：3.2 里的 `retire` 攒满 64 个会在写线程上做一次批量释放，这一下的耗时落在热路径上。挪到后台线程以后，写线程每次只多一次入队，延迟稳定。
- **代价**：多一个线程、多一条队列；后台线程如果跟不上，队列会涨，所以要监控队列长度。内核的 RCU 也是这样做的：`call_rcu` 只登记回调，宽限期过了由后台处理。

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
