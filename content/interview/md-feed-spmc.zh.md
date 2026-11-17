---
title: "IV：行情接入和 SPMC 广播环"
date: 2026-11-17T00:00:00+08:00
slug: "md-feed-spmc"
description: "简历第一条“行情接入”专页，带上第二条里消伪共享那一项：按配置接一家行情，回调线程是唯一的生产者，把统一结构写进共享内存里每格带戳的广播环，落盘线程批量读。先是一分钟讲法和完整代码，再是两类追问：常问的知识点，和对着代码一行一行问的细节。"
weight: 3
toc: true
math: true
---

这一页只讲简历第一条“行情接入”。讲法、代码、追问用的是同一版环：**每格带一个序号戳，一个生产者，读者自己记进度**，和 [SPMC 广播环](/zh/posts/spmc-shared-memory-broadcast-ring/)第 1、2 节是同一个结构。代码是为了讲清楚重写的简化版，名字不是原工程的。

## 1. 一分钟讲法 {#pitch}

> **开口这么说**
>
> 1. **按配置接一家行情的 SDK，Level-2 的快照、逐笔委托、逐笔成交每一路一个环**：这一路的回调线程把厂商的结构转成统一结构，直接写进共享内存里的广播环。每个环只有这一路的回调在写，是唯一的生产者。
> 2. **环的大小取 2 的幂，下标用 `& (N − 1)`，每格带一个序号戳**：写就是三步，取下一格、原地填、最后用 release 盖戳，不等任何读者。
> 3. **每个读者自己记“下一条要第几条”，不放进共享区**：acquire 读格子里的戳，算 `int(戳 − 我要的)`，小于 0 是还没写到，等于 0 是正好，大于 0 是被套圈。
> 4. **落盘线程睡几毫秒醒一次**：读到没有为止，批量写文件。代价是读者落后满一圈会被覆盖。
> 5. **是在原来的代码上改的**：顺手消了一处伪共享，回调线程的写下标和写线程的读下标原来挤在同一条缓存行，写下标用 `alignas(128)` 独占一块，读下标挪进读者自己的对象（[2.4 节](#false-sharing)）。

**两家行情怎么接：启动时读配置决定接哪一家**。每一路只有一个回调线程在写它的环，所以单生产者成立；换一家只改配置，环、落盘线程、文件格式一行不用动。

## 2. 代码 {#code}

### 2.1 环：一个生产者，读者各记各的 {#ring}

```cpp
#include <atomic>
#include <cstdint>

template <class T, uint32_t CNT>
class SPMCQueue {
    static_assert(CNT && !(CNT & (CNT - 1)), "CNT 必须是 2 的幂");
    static_assert(std::atomic<uint32_t>::is_always_lock_free, "跨进程用的原子量必须是 lock-free 的");
public:
    struct Reader {
        T* read() {
            auto& blk = q->blks[next_idx & (CNT - 1)];
            uint32_t new_idx = blk.idx.load(std::memory_order_acquire);
            if (int(new_idx - next_idx) < 0) return nullptr;   // 还没写到
            next_idx = new_idx + 1;                             // 正好，或被套圈后跳到这一条
            return &blk.data;
        }
        T* readLast() {                                         // 读到没有为止，只留最新一条
            T* ret = nullptr;
            while (T* cur = read()) ret = cur;
            return ret;
        }
        SPMCQueue* q = nullptr;
        uint32_t next_idx;                                      // 读者私有，不在共享内存里
    };

    Reader getReader() {                                        // 从下一条开始，不回放
        Reader r;
        r.q = this;
        r.next_idx = write_idx + 1;
        return r;
    }

    template <class Fill>
    void write(Fill fill) {                                     // 只有一个线程调
        auto& blk = blks[++write_idx & (CNT - 1)];              // ① 下一格
        fill(blk.data);                                         // ② 原地填
        blk.idx.store(write_idx, std::memory_order_release);  // ③ 最后盖戳
    }

private:
    struct alignas(64) Block {
        std::atomic<uint32_t> idx{0};                           // 这一格装的是第几条
        T data;
    } blks[CNT];
    alignas(128) uint32_t write_idx = 0;                        // 只有生产者写
};
```

- **写端只有三步，从不读读者的任何东西**：没有“满了”，写满一圈就覆盖最老的一格。所以生产者从不等待，有几个读者、读者多慢都不影响它。
- **发布信号是每一格自己的戳，不是一个所有人都读的共享下标**：读者之间没有任何可写的共享状态，多一个读者，写端一步不变。
- **测过**：`CNT = 8`，读者要第 2 条时生产者已经写到第 21 条，`read()` 拿到第 18 条（差值 16，正好两圈）；`CNT = 65536`，生产者写 200 万条、领先不到一圈，读者逐条核序号，不丢、不乱。

### 2.2 放进共享内存：四个调用 {#shm}

```cpp
// 伪码：按名字打开一块共享内存（没有就创建）→ 设成队列那么大（新内存全是 0）
//       → 映射进本进程的地址空间（可读写、MAP_SHARED 让别的进程看得到）→ 关掉 fd，映射还在
// mmap 六个参数：地址（nullptr 让内核挑）、长度、权限、共享方式、fd、偏移
template <class Q> Q* shmmap(const char* name) {
    int fd = shm_open(name, O_CREAT | O_RDWR, 0666);                          // ① 按名字打开，没有就创建
    if (fd == -1) return nullptr;
    if (ftruncate(fd, sizeof(Q))) { close(fd); return nullptr; }              // ② 设成队列那么大，新内存全是 0
    Q* ret = (Q*)mmap(nullptr, sizeof(Q), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);  // ③ 映射进来
    close(fd);                                                                 // ④ 关掉 fd，映射还在
    return ret == MAP_FAILED ? nullptr : ret;
}
```

**全 0 就是空队列**：没有人跑构造函数，`idx = 0`、`write_idx = 0` 正好是初始状态，`ftruncate` 保证新扩出来的部分是 0。

**`mmap` 和共享内存要知道的几点**：

| 问 | 开口这么说 |
|---|---|
| `mmap` 做的是什么 | 把一个文件或共享内存对象映射进进程的地址空间：内核在页表里建好映射，之后读写就是普通的 load / store，不再有系统调用。 |
| 两个进程为什么能共享 | 各自映射同一个名字，两边的页表项指向同一批物理页。虚拟地址可以不一样，所以里面不能放指针。 |
| `MAP_SHARED` 和 `MAP_PRIVATE` | `MAP_SHARED` 写进去，别的进程看得到；`MAP_PRIVATE` 是写时复制，改的只是自己的副本，广播环就失效了。 |
| 物理内存什么时候分配 | 按需：每一页第一次碰到才缺页、才分配。所以开盘前要把每页写一遍，只读不行，只读会映射到共享的零页。 |
| 它放在哪、活多久 | Linux 上在 `/dev/shm` 下，是 tmpfs，在内存里，不落盘。`close(fd)`、`munmap` 都不删它，要 `shm_unlink` 或重启；接入进程崩了，数据还在，读者照样能读。 |
| 能开多大 | `/dev/shm` 默认最多是物理内存的一半，环开得大要先看这个上限；`ftruncate` 设多大，能映射的就是多大。 |
| 还有哪些共享内存的方式 | System V 的 `shmget` / `shmat` 是老接口，用整数 key；`MAP_SHARED` 加 `MAP_ANONYMOUS` 没有名字，只有 `fork` 出来的父子进程能共享。要按名字、随时挂新的读者进程，就用 `shm_open`。 |
| 大页有什么用 | 环有几十 MB 到几 GB，按 4 KB 一页要占很多 TLB 项，遍历时 TLB 缺失多；换成 2 MB 的大页（在 hugetlbfs 挂载点上建文件再映射）能少很多。 |
| 原子量能跨进程用吗 | lock-free 的能，原子指令作用在物理内存上，两个进程映射的是同一块；不是 lock-free 的不行，它内部的锁在进程里。 |
| 会不会被换出 | 内存紧张时页可能被换到磁盘，再碰就是一次很慢的缺页；可以用 `mlock` 锁在内存里。 |

### 2.3 每一路一个回调、一个环，落盘线程挨个读 {#usage}

SDK 按数据类型分路推送，每一路注册一个回调：快照一个，逐笔委托一个，逐笔成交一个。**每个回调只写自己那一路的环**，所以每个环都只有一个写者。

```cpp
// 每一路一个环：接入进程和每个读者进程都按名字拿到同一组环
auto* snap_q  = shmmap<SPMCQueue<Snapshot, 1 << 19>>("/md_snapshot");  // 快照
auto* order_q = shmmap<SPMCQueue<Order,    1 << 22>>("/md_order");     // 逐笔委托
auto* trade_q = shmmap<SPMCQueue<Trade,    1 << 22>>("/md_trade");     // 逐笔成交

// 快照回调：厂商的快照结构 → 统一的 Snapshot
//   伪码：write 交出环里的下一格 → 逐字段转换填进去（代码定长拷贝，时间换成毫秒，
//         价格 ÷ 10000 转成元，十档价、量逐档转换）→ write 盖戳
void on_snapshot(const VendorSnap* in) {
    snap_q->write([&](Snapshot& out) {           // out 就是环里的那一格，直接填
        copy_code(out.code, in->code);
        out.time_ms = in->t;
        out.last    = in->last_px / 10000.0;     // 这家的价格是放大 10000 倍的整数
        for (int i = 0; i < 10; ++i) {
            out.bid_px[i]  = in->bid_px[i] / 10000.0;
            out.bid_vol[i] = in->bid_vol[i];
        }
    });
}

// 逐笔委托回调：厂商的委托结构 → 统一的 Order
//   伪码：代码、委托序号（成交回查委托时用）、价、量、方向逐字段转换；
//         委托类型深圳的 0 / 1 / U → 限价 / 市价 / 本方最优
void on_order(const VendorOrder* in) {
    order_q->write([&](Order& out) {
        copy_code(out.code, in->code);
        out.order_no = in->order_no;
        out.price    = in->price / 10000.0;
        out.qty      = in->qty;
        out.side     = in->side;
        out.type     = to_order_type(in->ord_type);
    });
}

// 逐笔成交回调：厂商的成交结构 → 统一的 Trade
//   伪码：代码、价、量、买卖双方的委托序号逐字段转换；深圳的撤单也在这一路，价格是 0 就标成撤单
void on_trade(const VendorTrade* in) {
    trade_q->write([&](Trade& out) {
        copy_code(out.code, in->code);
        out.price    = in->price / 10000.0;
        out.qty      = in->qty;
        out.bid_no   = in->bid_order_no;
        out.ask_no   = in->ask_order_no;
        out.canceled = (in->price == 0);
    });
}

// 落盘线程
//   伪码：每一路建一个读者（在接入开始写之前建好）；循环：每个环都 read() 到 nullptr，
//         拿到一条就格式化进这一路的缓冲、不留指针 → 一批写一次文件 → 睡几毫秒
void disk_loop() {
    auto rs = snap_q->getReader();
    auto ro = order_q->getReader();
    auto rt = trade_q->getReader();
    for (;;) {
        while (Snapshot* s = rs.read()) append_line(snap_buf,  *s);
        while (Order*    o = ro.read()) append_line(order_buf, *o);
        while (Trade*    t = rt.read()) append_line(trade_buf, *t);
        flush_all();
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
}
```

- **回调里做的就是结构体转换**：厂商的结构和统一结构字段名、单位、枚举都不一样，所以是逐字段转换，不能整块 `memcpy`，也不能 `reinterpret_cast` 过去。
- **转换直接写进环里的格子**：`write` 把那一格的引用交给 lambda，填完才盖戳，所以统一结构不用先在栈上构造一份再拷进去。
- **上海不一样**：委托、撤单、成交在同一路里推，按业务序号排，所以是一个回调、一个环，格子里带一个字段区分是哪一类。
- **逐笔的环开得比快照大**：逐笔一天几亿条，快照一天几百万条，落盘线程每次醒来，逐笔积压得多。

### 2.4 在原来的代码上消伪共享：写序号和读游标分开 {#false-sharing}

这是简历第二条“行情优化”的第一项，在原来那份环的代码上改的。

**原来的布局**：落盘线程的读游标放在队列里，紧挨着写序号。两个变量逻辑上毫无关系，可在同一条缓存行上：回调线程每写一条改 `write_idx`，落盘线程每读一条改 `disk_next`，哪个核要写，都得先把整条行独占过来，另一个核的副本就作废了。这条行每条行情都在两个核之间搬一趟。

```cpp
// 改之前：读游标放在队列里，和写序号挨着，同一条缓存行
template <class T, uint32_t CNT>
struct OldQueue {
    Block<T> blks[CNT];
    uint32_t write_idx = 0;                    // 回调线程每条都写
    std::atomic<uint32_t> disk_next{1};        // 落盘线程每读一条都写
};
```

**改法**：写序号独占一个 128 字节的块；读游标挪出队列，放进读者自己的 `Reader`，也独占一块。再用 `static_assert` 把布局钉死。

```cpp
// 改之后
template <class T, uint32_t CNT>
struct NewQueue {
    Block<T> blks[CNT];
    alignas(128) uint32_t write_idx = 0;       // 只有回调线程写，这一块里没有别人

    struct alignas(128) Reader {               // 读者私有，也独占一块
        NewQueue* q;
        uint32_t next_idx;
        T* read();
    };
};

// 把布局钉死：以后有人在 write_idx 后面加成员，编译就报错
using NQ = NewQueue<Snapshot, 1 << 16>;
static_assert(offsetof(NQ, write_idx) % 128 == 0, "写序号要从 128 字节边界开始");
static_assert(sizeof(NQ) - offsetof(NQ, write_idx) == 128, "写序号后面不能再挤别的成员");
static_assert(sizeof(NQ::Reader) == 128, "读游标独占一块");
```

- **为什么读游标挪出去，而不是在队列里也 `alignas(128)`**：游标只有这个读者自己用，放进共享区没有任何好处；挪到读者自己的对象里，加读者就是多建一个 `Reader`，队列的布局一点不用动。
- **为什么是 128，不是 64**：Intel 的相邻行预取会把同一个 128 字节块里的两条行成对取进来，只隔 64 还可能被顺带拉走。
- **布局检查先在老代码上跑红**：老布局里 `write_idx` 后面紧跟着 `disk_next`，“后面不能再挤别的成员”那一条一定过不了。确认检查会失败，再改代码让它通过。

**对照实验**：同一个程序里新旧两种布局交替跑 7 轮，读者在另一个核上全速读，看生产者每写一条花多久。我的 Windows 机器上，改之前约 17 ns，改之后约 3 ns。这是读者全速紧跟的极端情况；按落盘线程实际的节奏，差得少得多，这也是简历上说“高频读取场景下”的原因。

<details>
<summary><strong>完整的对照程序</strong>（能直接编译运行）</summary>

```cpp
// 伪共享对照：老布局（写序号和读游标挨着）vs 新布局（写序号独占 128 字节，读游标在读者自己的对象里）
// 编译：g++ -std=c++17 -O2 -Wall -Wextra -pthread fs.cpp -o fs && ./fs
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <thread>
#include <vector>

struct Snapshot { uint64_t seq; double last; double bid_px[5]; };

template <class T>
struct alignas(64) Block { std::atomic<uint32_t> idx{0}; T data; };

// ---- 改之前：读游标放在队列里，和写序号挨着，同一条缓存行 ----
template <class T, uint32_t CNT>
struct OldQueue {
    Block<T> blks[CNT];
    uint32_t write_idx = 0;                    // 回调线程每条都写
    std::atomic<uint32_t> disk_next{1};        // 落盘线程每读一条都写

    template <class Fill> void write(Fill fill) {
        auto& blk = blks[++write_idx & (CNT - 1)];
        fill(blk.data);
        blk.idx.store(write_idx, std::memory_order_release);
    }
    T* read() {                                // 只有一个读者：落盘线程
        auto& blk = blks[disk_next & (CNT - 1)];
        uint32_t s = blk.idx.load(std::memory_order_acquire);
        if (int(s - disk_next) < 0) return nullptr;
        disk_next.store(s + 1, std::memory_order_relaxed);   // 写的是共享的那条行
        return &blk.data;
    }
};

// ---- 改之后：写序号独占一个 128 字节的块；读游标挪进读者自己的 Reader ----
template <class T, uint32_t CNT>
struct NewQueue {
    Block<T> blks[CNT];
    alignas(128) uint32_t write_idx = 0;       // 只有回调线程写，这一块里没有别人

    struct alignas(128) Reader {               // 读者私有，也独占一块
        NewQueue* q;
        uint32_t next_idx;
        T* read() {
            auto& blk = q->blks[next_idx & (CNT - 1)];
            uint32_t s = blk.idx.load(std::memory_order_acquire);
            if (int(s - next_idx) < 0) return nullptr;
            next_idx = s + 1;
            return &blk.data;
        }
    };
    Reader getReader() { return Reader{this, write_idx + 1}; }

    template <class Fill> void write(Fill fill) {
        auto& blk = blks[++write_idx & (CNT - 1)];
        fill(blk.data);
        blk.idx.store(write_idx, std::memory_order_release);
    }
};

// 把布局钉死：以后有人在 write_idx 后面加成员，编译就报错
using NQ = NewQueue<Snapshot, 1 << 16>;
static_assert(offsetof(NQ, write_idx) % 128 == 0, "写序号要从 128 字节边界开始");
static_assert(sizeof(NQ) - offsetof(NQ, write_idx) == 128, "写序号后面不能再挤别的成员");
static_assert(sizeof(NQ::Reader) == 128, "读游标独占一块");
// 老布局一定过不了上面那条“后面不能再挤”：
using OQ = OldQueue<Snapshot, 1 << 16>;
static_assert(offsetof(OQ, disk_next) - offsetof(OQ, write_idx) < 64, "改之前：两个在同一条行里");

constexpr uint32_t kN = 20'000'000;

// 生产者写 kN 条，读者在另一个核上一直读；返回生产者每写一条的平均 ns
template <class MakeReader, class Q>
double run(Q& q, MakeReader make_reader) {
    std::atomic<bool> stop{false};
    auto reader = make_reader();
    std::thread rd([&] {
        uint64_t sum = 0;
        while (!stop.load(std::memory_order_relaxed))
            while (Snapshot* s = reader.read()) sum += s->seq;
        if (sum == 42) std::puts("");          // 不让编译器把读删掉
    });
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    auto t0 = std::chrono::steady_clock::now();
    for (uint32_t i = 1; i <= kN; ++i)
        q.write([&](Snapshot& s) { s.seq = i; s.last = i * 0.01; });
    auto t1 = std::chrono::steady_clock::now();
    stop = true;
    rd.join();
    return std::chrono::duration<double, std::nano>(t1 - t0).count() / kN;
}

struct OldReader { OQ* q; Snapshot* read() { return q->read(); } };

int main() {
    std::vector<double> olds, news;
    for (int round = 0; round < 7; ++round) {            // 新旧交替跑，取中位数
        auto o = std::make_unique<OQ>();
        olds.push_back(run(*o, [&] { return OldReader{o.get()}; }));
        auto n = std::make_unique<NQ>();
        news.push_back(run(*n, [&] { return n->getReader(); }));
    }
    std::sort(olds.begin(), olds.end());
    std::sort(news.begin(), news.end());
    std::printf("每写一条：改之前 %.1f ns，改之后 %.1f ns（7 轮中位数）\n", olds[3], news[3]);
}
```

</details>

## 3. 常问的知识点 {#classic}

每题先说结论，一到三句。

| 问 | 开口这么说 |
|---|---|
| 为什么用共享内存，每个进程自己订阅不行吗 | 行情源有频控和连接数限制，只接一次、解码一次，几个进程都能读，看到的还是同一份；共享内存映射好之后读写就是普通的 load / store，socket 每条都要进内核、拷贝。 |
| Level-2 不只有快照，逐笔放哪 | 每一路一个环，各有自己的统一结构：快照一个；深圳逐笔委托、逐笔成交分两路推，各一个；上海委托、撤单、成交在同一路里，按业务序号排，一个。每个环只有这一路的回调在写，都是单生产者。整日回放的 4.5 亿条，大头是逐笔。 |
| 为什么是广播环，不是几个 SPSC | 生产者不能被慢读者拖住，加读者生产者不用改；代价是慢读者会被覆盖。读者各要一部分、或者丢了必须当场知道，才用按读者分开的 SPSC。 |
| 什么能放进共享内存 | 定长、可平凡拷贝、不含指针的数据；`vector`、`string`、有虚函数的都不行，同一块内存在两个进程里地址不同，指针到了另一边就是错的。 |
| 读写进度靠什么 | 写者一个只增的序号，写进每一格的戳里；每个读者自己记下一条要读的号；两个一减就知道写没写到。 |
| 没写过的格子怎么不被读到 | 没写过的格子戳是 0，读者要的号从 1 起，差值是负的，判成“还没写到”。 |
| 跨进程下标怎么传 | 不用传：戳就在共享内存的格子里，是 lock-free 的 32 位原子量，两个进程映射同一块物理内存，看到的是同一个变量。 |
| 内存序 | 写者先写数据，再 release 存戳；读者 acquire 读戳，读到新值就一定看得到数据。x86 上这两个都是普通 `mov`，只拦编译器重排；ARM 上会多出屏障。 |
| 为什么大小取 2 的幂 | 下标用 `x & (N − 1)` 代替取模，一条与指令；而且 2³² 是 N 的整数倍，序号回绕成 0 时格子位置还是连着的。 |
| 被套圈怎么办 | 戳比我要的大，说明中间丢了，这一版直接跳到这一条；丢了几条就是那个差值，在 `Reader` 里累加一下就看得见。 |
| 撕裂读是什么，怎么防 | 读者读到一半，生产者绕一圈回来重写同一格，读到一半旧一半新。防法是生产者先把戳作废成 0、再写数据、最后盖新号，读者复制完再读一次戳，变了就丢。 |
| 伪共享 | 不同核写的变量在同一条缓存行，互相把对方的行打失效；`alignas` 分开，我用 128，因为相邻行预取会成对拉两行。 |
| 怎么确认是伪共享 | 先看布局，是不是同一行、不同核在写；再做只改对齐的对照实验；物理机上用 `perf c2c` 看 HITM。 |
| 读者会不会拖慢生产者 | 不会让它等，但每条消息要在两个核之间走两趟：写时作废读者的副本，读时把行取回来。平时感觉不到，全速写、读者紧跟时每条会变贵。 |

## 4. 对着代码问的细节 {#details}

这一类问题没有标准说法，**答得出来的前提是自己写过、跑过**。每题对着 2.1 节的某一行。

### 4.1 写端 {#details-write}

| 问 | 开口这么说 |
|---|---|
| `++write_idx` 为什么是先加，序号为什么从 1 开始 | 新内存全是 0，戳 0 的意思是“没写过”。序号从 1 开始，没写过的格子永远比读者要的小；要是从 0 开始，读者要第 0 条，看到空格子的戳也是 0，会把没写的格子当数据读走。 |
| `write_idx` 为什么不是原子量 | 只有生产者一个线程写它，读者不看它（只有 `getReader()` 建读者时读一次），读者看的是格子里的戳。 |
| 第 ③ 步改成 `relaxed` 会怎样 | 读者可能先看到新戳、后看到数据，拿到一条没填完的。x86 上硬件不会把两次写重排，大概率测不出来，但编译器可以把数据的写挪到戳后面；ARM 上硬件也会重排。 |
| `write` 为什么收一个 lambda，不收 `const T&` | 原地填格子，省一次拷贝：回调里直接把厂商结构转进环里，不先在栈上构造一份再拷进去。 |
| 两家同时接，能不能两个回调线程写同一个环 | 不能：`++write_idx` 不是原子的，两个线程会拿到同一个号、写同一格。要同时接就各写各的环；非要一个环，得改成 `fetch_add` 占号、按序号顺序发布，那是另一种结构。 |
| `Block` 为什么 `alignas(64)` | 相邻两格不共用缓存行，生产者写第 i 格时不会把读者正在读的第 i − 1 格的行拽走。 |
| 一格多大，整个环多大 | 一格 = 4 字节戳加数据，向上补到 64 的倍数；整个环 = 一格 × `CNT`。比如数据 88 字节，一格 128 字节，`CNT = 2¹⁹` 时 64 MiB。说你们自己的数之前先算好。 |
| `write_idx` 为什么 `alignas(128)` | 生产者每条都写它，不能和读者常读的格子挤在一行；128 是因为相邻行预取会成对拉两行。 |

### 4.2 读端 {#details-read}

| 问 | 开口这么说 |
|---|---|
| 为什么写 `int(new_idx − next_idx) < 0`，不写 `new_idx < next_idx` | 戳是 32 位，会回绕。无符号相减再当有符号看，只要两者差不到 2³¹，回绕前后大小都对；直接比较，回绕后的新戳 1 会被判成比 `0xFFFFFFFE` 小，误判成没写到。 |
| 差值大于 0 时，跳过了几条 | 正好是那个差值，而且一定是 `CNT` 的整数倍：读者看的那一格，戳只可能是 `next_idx` 加减若干个 `CNT`。 |
| `next_idx` 为什么不放共享内存 | 只有这个读者自己读写，放进共享区既没人用，还会和别人挤缓存行。读者从不往队列里写，读者之间就没有竞争。 |
| 两个线程能不能共用一个 `Reader` | 不能，`next_idx` 只属于一个读者，共用会互相把对方的进度改掉；每个线程自己 `getReader()`。 |
| `read()` 返回指针，有什么风险 | 指针指向共享的那一格，生产者绕回来会重写它。所以落盘线程拿到就马上格式化进自己的缓冲，不留着指针。 |
| `readLast()` 给谁用 | 只要最新值的读者，比如监控、看板：一口气读到没有，中间的跳过。 |

### 4.3 共享内存和启动顺序 {#details-shm}

| 问 | 开口这么说 |
|---|---|
| 没有构造函数运行，环怎么初始化 | 靠全 0：`ftruncate` 扩出来的内存全是 0，戳 0、`write_idx` 0 就是空队列。 |
| 戳为什么直接声明成 `std::atomic`，放进共享内存行不行 | 行，前提是 lock-free：`atomic<uint32_t>` 就是 4 个字节，全 0 就是值 0，不需要谁跑构造函数，所以加了一句 `static_assert(is_always_lock_free)`。也有写法是声明成普通 `uint32_t`、用的时候强转成 atomic 指针，严格说是未定义行为；C++20 要这样做，该用 `std::atomic_ref`。 |
| 读者进程后启动，`getReader()` 读 `write_idx` 有什么问题 | 这是非原子读，生产者同时在写，严格说是数据竞争。x86 上对齐的 32 位读不会读出半个值，最多拿到一个稍旧的号，从前几条开始读；要严格，就把 `write_idx` 改成原子量、读者用 `relaxed` 读。 |
| 落盘进程崩了重启，会丢数据吗 | 会：`getReader()` 从下一条开始，崩掉那几秒全丢。要续读，就把 `next_idx` 存到进程外面，重启后从它接着读，落后不到一圈就一条不丢。 |
| 每天重建队列，老读者还在跑会怎样 | 新戳从 1 开始，老读者的游标是几百万，差值一直是负的，`read()` 一直返回空，看起来像没行情，实际是卡住。重建队列时一起重启读者。 |
| 开盘第一圈为什么慢 | 共享内存按页分配，每一页第一次写才缺页；启动时在绑好核的线程上把每页写一遍，只读不行，只读会映射到共享的零页。 |

### 4.4 落盘线程和数字 {#details-numbers}

| 问 | 开口这么说 |
|---|---|
| 睡多久、环多大才不会被套圈 | 两个数比一下：每次睡的时间乘行情速率，远小于 `CNT` 就行。读者完全停住能撑 `CNT ÷ 速率` 秒，比如每秒 5 万条、`CNT = 2¹⁹`，约 10 秒。 |
| 为什么落盘要批量 | 一次写文件是一次系统调用，攒一批写一次，开销摊到每条上就很小。 |
| 怎么知道整日回放没被套圈 | 读者里累加差值大于 0 时跳过的条数，跑完是 0；落盘条数等于写入条数。 |
| 生产者会不会因为落盘慢而变慢 | 不会，生产者从不看读者；落盘慢的后果是落后、最终被套圈，代价在读者那一侧。 |

### 4.5 伪共享那一处 {#details-false-sharing}

| 问 | 开口这么说 |
|---|---|
| 原来是哪两个变量在同一行 | 回调线程的写序号 `write_idx`，和落盘线程的读游标；读游标原来放在队列里，紧挨着写序号。 |
| 只读的变量和写的变量在一行，算不算伪共享 | 算，只要有一个核在写：读的那个核每次都要把行重新取回来，写的那个核每次都要先作废对方的副本。 |
| 为什么不把读游标也放在队列里、加 `alignas(128)` 就完了 | 也能消掉伪共享，但游标只有读者自己用，放共享区没有好处；放进 `Reader`，加读者不用改队列的布局。 |
| `static_assert` 钉的是什么 | 写序号从 128 字节边界开始，而且它后面不再有别的成员；读者对象正好 128 字节。以后谁加成员挤进这一块，编译就报错。 |
| 怎么证明是伪共享、改了有效 | 先看布局，两个变量在同一行、被不同的核写；再做对照，只改布局、别的不动，新旧交替跑多轮比中位数。物理机上可以用 `perf c2c` 看这条行的 HITM。 |
| 40% 和你实验里差好几倍，哪个对 | 都对，条件不一样：读者全速紧跟时差好几倍；简历的 40% 是按“高频读取”的节奏测的；落盘线程实际几毫秒醒一次，每条平均只省几纳秒。 |
