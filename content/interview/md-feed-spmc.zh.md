---
title: "IV. 行情接入和 SPMC 广播环"
date: 2026-11-17T00:00:00+08:00
slug: "md-feed-spmc"
description: "简历实习前两条的专页，第 3 节是两份带测试的完整代码。第 1 部分行情接入：按配置接一家行情，回调线程是唯一的生产者，把统一结构写进共享内存里每格带戳的广播环，另一个进程的落盘线程批量读。第 2 部分行情优化：伪共享、预触内存页、回调自己读时钟。每部分都是概览、代码、常问的知识点、对着代码问的细节。"
weight: 3
toc: true
math: true
---

这一页讲简历实习经历的前两条：**第 1 部分是行情接入，第 2 部分是行情优化**。两部分用的是同一版环：**每格带一个序号戳，一个生产者，读者自己记进度**，和 [SPMC 广播环](/zh/posts/spmc-shared-memory-broadcast-ring/)第 1、2 节是同一个结构。代码是为了讲清楚重写的简化版，名字不是原工程的。

## 1. 行情接入：回调写环，落盘进程批量读 {#md-feed}

### 1.1 概览 {#pitch}

> 1. **按配置接一家行情的 SDK，Level-2 的快照、逐笔委托、逐笔成交每一路一个环**：这一路的回调线程把厂商的结构转成统一结构，直接写进共享内存里的广播环。每个环只有这一路的回调在写，是唯一的生产者。
> 2. **环的大小取 2 的幂，下标用 `& (N − 1)`，每格带一个序号戳**：写就是三步，取下一格、原地填、最后用 release 盖戳，不等任何读者。
> 3. **每个读者自己记“下一条要第几条”，不放进共享区**：acquire 读格子里的戳，算 `int(戳 − 我要的)`，小于 0 是还没写到，等于 0 是正好，大于 0 是被套圈。
> 4. **落盘是另一个进程，按名字映射同一组环，里面的落盘线程睡几毫秒醒一次**：读到没有为止，批量写文件。代价是读者落后满一圈会被覆盖。
> 5. **是在原来的代码上改的**：顺手消了一处伪共享，回调线程的写下标和落盘线程的读下标原来挤在共享内存的同一条缓存行，读者在另一个进程里照样是伪共享，写下标用 `alignas(128)` 独占一块，读下标挪进读者自己的对象（[2.2 节](#false-sharing)）。

**两家行情怎么接：启动时读配置决定接哪一家**。每一路只有一个回调线程在写它的环，所以单生产者成立；换一家只改配置，环、落盘线程、文件格式一行不用动。

### 1.2 环：一个生产者，读者各记各的 {#ring}

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

### 1.3 放进共享内存：四个调用 {#shm}

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

| 问 | 答 |
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

### 1.4 每一路一个回调、一个环，落盘进程挨个读 {#usage}

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

// 落盘进程里的落盘线程（另一个进程，按名字拿到同一组环）
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

### 1.5 架构：接入进程写，落盘进程读，都放在网卡那个插槽上 {#arch}

- **接入进程**：每一路一个回调线程，是这一路环的唯一生产者，绑在网卡所在 NUMA 节点的一个核上。
- **落盘进程**：另一个进程，按名字 `shm_open` 同一组环，里面的落盘线程是读者，绑在同一节点的另一个核上，批量写文件。
- **为什么分成两个进程**：落盘慢、落盘进程崩了重启，都不碍着接入。要再加读者进程，按名字挂上来、自己建 `Reader`，接入进程一行不改。
- **共享内存的页**：接入进程在回调核上先把环写一遍，物理页落在本节点（2.3 节）。落盘进程启动时也把环碰一遍，补上自己那份页表项。

这一层常被追问的硬件问题：

| 问 | 答 |
|---|---|
| 伪共享是什么和什么之间的 | 核和核之间。每个核有自己的 L1、L2，一条缓存行可以在几个核里各有一份副本。两个不同的变量落在同一行、至少一方在写，写的那个核要先作废别的核的副本，别的核再访问就得把整行要回来。只读不写不会有，大家都是 Shared。 |
| 读者在另一个进程里，还有伪共享吗 | 有。缓存一致性只看物理地址：两个进程映射同一块共享内存，页表项指向同一批物理页，同一条缓存行就是同一条。核上跑的是同一进程的两个线程，还是两个进程，MESI 的行为一样。 |
| 两个进程要在同一颗 CPU 上才有伪共享吗 | 核不一样才有。同一个物理核（分时轮流跑，或者超线程的两个兄弟）共用 L1，行不用搬，没有伪共享。同插槽的不同核，换手一次约 20–100 ns。跨插槽也有，换手要过 UPI，约 150–300 ns，慢 3–5 倍（[速查 2.1](/zh/ref/cpu-memory/#latency)）。所以接入和落盘都放在网卡那个插槽，伪共享还是得靠布局消。 |
| 跨插槽是不是不共享 L3 了 | 对，每个插槽一块 L3。内存还是同一个地址空间，物理上分两半挂在两个插槽上，读对面那一半要过互连。一致性靠归属插槽：一条行的物理地址落在哪个插槽的内存上，那个插槽就记着哪些插槽有它的副本（目录或 snoop filter），要写时通过互连去作废对面的副本。 |
| `mmap` 进来的共享内存，第一次访问时发生了什么 | `mmap` 返回时内核只记了一段虚拟地址，页表项是空的。第一次访问：dTLB 没命中，走页表，走到最后一级发现项是空的，CPU 在这个核上抛缺页异常。内核找到或分配物理页、填页表项，再重新执行这条指令。之后和普通内存一样走 TLB 和缓存，内核不参与。 |
| 缺页是中断吗 | 是异常，不是中断：由当前这条指令引起，在同一个核上同步处理。网卡中断才是设备发来的、异步的。共享内存在 `/dev/shm`，页在内存里，只有不读盘的轻缺页，微秒级；要从盘里读的重缺页还得加 10–100 µs。 |
| 两个进程都会缺页吗 | 都会，页表是每个进程一份。接入进程第一次写某一页，内核分物理页、填它的页表项。落盘进程第一次碰这一页，物理页已经有了，只补自己的页表项，也是一次轻缺页。所以两边启动时都要把环碰一遍。 |

### 1.6 接入时核过的三件事：字段口径、整日回放、断线续传 {#md-verify}

#### 1.6.1 厂商给的字段不能直接信：拿真实行情逐字段核 {#md-fields}

接入最费时间的是弄清每个字段到底是什么口径。核出来的几处：

| 字段 | 核出来的差异 | 怎么处理 |
|---|---|---|
| 上海逐笔的顺序 | 委托、撤单、成交在同一路里，要按统一的业务序号排 | 一开始用错了序号字段，换成业务序号 |
| 撤单在哪一路 | 深圳的撤单在成交那一路里，价格是 0；上海的在委托那一路里 | 按市场分开处理 |
| 深圳委托类型 | 取值是 0、1、U，对应限价、市价、本方最优 | 整天核下来只有这 3 种，按这 3 种转换 |
| 上海成交金额 | 行情源给的是整数元，成交量不是 100 股的整数倍时丢了角和分 | 改成价格 × 成交量自己算，复核到分一致 |

沪深 Level-2 的三类数据和两市的差别见 [A 股市场](/zh/ref/a-share-market/)。

#### 1.6.2 整日回放 4.5 亿条：看条数、内存、有没有被套圈 {#md-replay}

把一整天的真实行情按原样回放一遍，约 4.5 亿条。看 3 样：

- **条数对得上**：发出去多少条，文件里就有多少行。
- **内存稳定不涨**：没有泄漏，环是定长的。
- **落盘线程没被套圈**：序号连续，没有回退和重复。

**第一次回放统计出 100 多处序号回退和重复**，看着像程序的 bug。查下来是统计脚本处理每行的速度比落盘线程还慢，它把落盘线程拖住了，环被套圈。统计换成快的写法重跑，问题消失。结论是测量工具不能比被测的东西慢。

#### 1.6.3 断线续传：能力是 SDK 的，我做的是验证和补漏 {#md-reconnect}

- **重连和断点续传由 SDK 提供**：断线后 SDK 自己重连，从断点接着推，程序不用退出。
- **验证**：人为断开网络几十秒再恢复，核对断线前后的行不丢、不重。
- **补漏**：首次连接偶尔遇到网络错误，原来直接失败，改成隔几秒重试。

### 1.7 常问的知识点 {#classic}

每题先说结论，一到三句。

| 问 | 答 |
|---|---|
| SPMC 是你写的吧，怎么做的 | 是我写的，在原来的代码上改的。每格带一个序号戳，生产者原地填完再盖戳，不等读者；读者自己记要第几条，看戳一比就知道能不能读。改的时候还同时关注到并解决了伪共享的问题。 |
| 为什么用共享内存，每个进程自己订阅不行吗 | 行情源有**频控和连接数限制**：行情网关限制一个账号能开几条连接、订阅频率多高，没法每个进程各自连一条。所以只接一次、解码一次，几个进程都能读，看到的还是同一份。<br>共享内存映射好之后读写就是普通的 load / store，socket 每条都要进内核、拷贝。 |
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
| 读者会不会拖慢生产者 | 不会让它等，但每条消息要在两个核之间走两趟：写时作废读者的副本，读时把行取回来。平时感觉不到，全速写、读者紧跟时每条会变贵。 |

### 1.8 对着代码问的细节 {#details}

这一类问题没有标准说法，**答得出来的前提是自己写过、跑过**。每题对着 1.2 节的某一行。

#### 1.8.1 写端 {#details-write}

| 问 | 答 |
|---|---|
| `++write_idx` 为什么是先加，序号为什么从 1 开始 | 新内存全是 0，戳 0 的意思是“没写过”。序号从 1 开始，没写过的格子永远比读者要的小；要是从 0 开始，读者要第 0 条，看到空格子的戳也是 0，会把没写的格子当数据读走。 |
| `write_idx` 为什么不是原子量 | 只有生产者一个线程写它，读者不看它（只有 `getReader()` 建读者时读一次），读者看的是格子里的戳。 |
| 第 ③ 步改成 `relaxed` 会怎样 | 读者可能先看到新戳、后看到数据，拿到一条没填完的。x86 上硬件不会把两次写重排，大概率测不出来，但编译器可以把数据的写挪到戳后面；ARM 上硬件也会重排。 |
| `write` 为什么收一个 lambda，不收 `const T&` | 原地填格子，省一次拷贝：回调里直接把厂商结构转进环里，不先在栈上构造一份再拷进去。 |
| 两家同时接，能不能两个回调线程写同一个环 | 不能：`++write_idx` 不是原子的，两个线程会拿到同一个号、写同一格。要同时接就各写各的环；非要一个环，得改成 `fetch_add` 占号、按序号顺序发布，那是另一种结构。 |
| `Block` 为什么 `alignas(64)` | 相邻两格不共用缓存行，生产者写第 i 格时不会把读者正在读的第 i − 1 格的行拽走。 |
| 一格多大，整个环多大 | 一格 = 4 字节戳加数据，向上补到 64 的倍数；整个环 = 一格 × `CNT`。比如数据 88 字节，一格 128 字节，`CNT = 2¹⁹` 时 64 MiB。说你们自己的数之前先算好。 |
| `write_idx` 为什么 `alignas(128)` | 生产者每条都写它，不能和读者常读的格子挤在一行；128 是因为相邻行预取会成对拉两行。 |

#### 1.8.2 读端 {#details-read}

| 问 | 答 |
|---|---|
| 为什么写 `int(new_idx − next_idx) < 0`，不写 `new_idx < next_idx` | 戳是 32 位，会回绕。无符号相减再当有符号看，只要两者差不到 2³¹，回绕前后大小都对；直接比较，回绕后的新戳 1 会被判成比 `0xFFFFFFFE` 小，误判成没写到。 |
| 差值大于 0 时，跳过了几条 | 正好是那个差值，而且一定是 `CNT` 的整数倍：读者看的那一格，戳只可能是 `next_idx` 加减若干个 `CNT`。 |
| `next_idx` 为什么不放共享内存 | 只有这个读者自己读写，放进共享区既没人用，还会和别人挤缓存行。读者从不往队列里写，读者之间就没有竞争。 |
| 两个线程能不能共用一个 `Reader` | 不能，`next_idx` 只属于一个读者，共用会互相把对方的进度改掉；每个线程自己 `getReader()`。 |
| `read()` 返回指针，有什么风险 | 指针指向共享的那一格，生产者绕回来会重写它。所以落盘线程拿到就马上格式化进自己的缓冲，不留着指针。 |
| `readLast()` 给谁用 | 只要最新值的读者，比如监控、看板：一口气读到没有，中间的跳过。 |

#### 1.8.3 共享内存和启动顺序 {#details-shm}

| 问 | 答 |
|---|---|
| 没有构造函数运行，环怎么初始化 | 靠全 0：`ftruncate` 扩出来的内存全是 0，戳 0、`write_idx` 0 就是空队列。 |
| 戳为什么直接声明成 `std::atomic`，放进共享内存行不行 | 行，前提是 lock-free：`atomic<uint32_t>` 就是 4 个字节，全 0 就是值 0，不需要谁跑构造函数，所以加了一句 `static_assert(is_always_lock_free)`。也有写法是声明成普通 `uint32_t`、用的时候强转成 atomic 指针，严格说是未定义行为；C++20 要这样做，该用 `std::atomic_ref`。 |
| 读者进程后启动，`getReader()` 读 `write_idx` 有什么问题 | 这是非原子读，生产者同时在写，严格说是数据竞争。x86 上对齐的 32 位读不会读出半个值，最多拿到一个稍旧的号，从前几条开始读；要严格，就把 `write_idx` 改成原子量、读者用 `relaxed` 读。 |
| 落盘进程崩了重启，会丢数据吗 | 会：`getReader()` 从下一条开始，崩掉那几秒全丢。要续读，就把 `next_idx` 存到进程外面，重启后从它接着读，落后不到一圈就一条不丢。 |
| 每天重建队列，老读者还在跑会怎样 | 新戳从 1 开始，老读者的游标是几百万，差值一直是负的，`read()` 一直返回空，看起来像没行情，实际是卡住。重建队列时一起重启读者。 |
| 开盘第一圈为什么慢 | 共享内存按页分配，每一页第一次写才缺页；启动时在绑好核的线程上把每页写一遍，只读不行，只读会映射到共享的零页。 |

#### 1.8.4 落盘线程和数字 {#details-numbers}

| 问 | 答 |
|---|---|
| 睡多久、环多大才不会被套圈 | 两个数比一下：每次睡的时间乘行情速率，远小于 `CNT` 就行。读者完全停住能撑 `CNT ÷ 速率` 秒，比如每秒 5 万条、`CNT = 2¹⁹`，约 10 秒。 |
| 为什么落盘要批量 | 一次写文件是一次系统调用，攒一批写一次，开销摊到每条上就很小。 |
| 怎么知道整日回放没被套圈 | 读者里累加差值大于 0 时跳过的条数，跑完是 0；落盘条数等于写入条数。 |
| 生产者会不会因为落盘慢而变慢 | 不会，生产者从不看读者；落盘慢的后果是落后、最终被套圈，代价在读者那一侧。 |

## 2. 行情优化：伪共享、预触内存页、回调自己读时钟 {#md-opt}

> **简历原文**
>
> SPMC 广播队列的读写计数按缓存行隔离、消除伪共享，高频读取场景下写入延迟中位数降低约 40%；启动时预触内存页消除首轮缺页，去掉回调中对共享时间字段的跨核读取，单包处理延迟中位数降低约 17%、P99 降低约 57%

### 2.1 概览 {#opt-pitch}

> 1. **伪共享**：回调线程的写序号和落盘线程的读游标原来在同一条缓存行，两边每条都写；写序号用 `alignas(128)` 独占一块，读游标挪进读者自己的对象，再用 `static_assert` 钉死布局。40% 只在读得很密时成立，这一点主动说。
> 2. **预触**：第一圈写的全是新内存，缺页挤在开盘最忙的时候；启动时在绑好核的线程上每页写一个字节，P99 降约 57%。
> 3. **读时钟**：回调原来读时间线程刷新的共享字段，每条一次跨核搬行；改成回调自己 `clock_gettime`，走 vDSO 不进内核，中位数降约 17%。
> 4. **为什么两个数差这么多**：预触去掉的是偶发的大开销，降尾部；读时钟去掉的是每条都有的小开销，降中位数。

### 2.2 在原来的代码上消伪共享：写序号和读游标分开 {#false-sharing}

这是第一项，在原来那份环的代码上改的。

**原来的布局**：落盘线程的读游标放在共享内存的队列里，紧挨着写序号。落盘线程在另一个进程里，但两个进程映射的是同一批物理页，同一条缓存行就是同一条，伪共享照样发生（[1.5 节](#arch)）。两个变量逻辑上毫无关系，可在同一条缓存行上：回调线程每写一条改 `write_idx`，落盘线程每读一条改 `disk_next`，哪个核要写，都得先把整条行独占过来，另一个核的副本就作废了。这条行每条行情都在两个核之间搬一趟。

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

**对照实验**：同一个程序里新旧两种布局交替跑 7 轮，读者在另一个核上全速读，看生产者每写一条花多久。程序里用两个线程模拟，硬件上和两个进程一样。我的 Windows 机器上，改之前约 17 ns，改之后约 3 ns。这是读者全速紧跟的极端情况；按落盘线程实际的节奏，差得少得多，这也是简历上说“高频读取场景下”的原因。

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

### 2.3 第一圈的缺页挤在开盘：启动时预触内存页 {#prefault}

**缺页**：大块内存刚分配时，内核只记下“这段地址归你”，不马上给物理页。第一次写到某个 4 KB 的页，CPU 陷入内核，内核找一个物理页、清零、建好映射再返回，一次 1 µs 到几微秒；正常处理一包只要零点几微秒。环有几百万格，第一圈写的每一页都是新的，正好落在开盘那几分钟。

```cpp
// 伪码：在绑到回调核的线程上，SDK 开始回调之前，对环的每一页写一个字节
void prefault(void* p, size_t bytes) {
    auto* c = static_cast<volatile char*>(p);
    for (size_t off = 0; off < bytes; off += 4096)
        c[off] = 0;                      // 必须写：逼内核现在就分配
}
```

- **必须写，不能只读**：读一个没碰过的页，内核映射的是全局共享的零页，物理内存还是没分配，等于没做。
- **在已经绑到回调核的线程上做**：Linux 默认把物理页分在第一次写它的线程所在的 NUMA 节点，在回调核上预触，页就落在回调线程本地。
- **`volatile` 是为了不让编译器把这些写删掉**：写进去的值之后没人读，编译器有权当成无用的写优化掉。
- **代价**：启动慢约 1 秒，内存一启动就占满整个环。峰值内存不变，环转过一圈本来也会全部占上。

**结果**：回放期间回调线程的缺页从 14000 多次降到 200 多次，P99 降约 57%，中位数不变。

### 2.4 每条行情跨核读一次时间：回调自己读时钟 {#clock}

> **本质：把每条行情一次跨核的缓存行传输，换成本核上读一次 TSC**。

1. **原来**
   - **时间线程**：在另一个核上不停把当前时间写进一个共享字段 `now_`。
   - **回调**：每来一条行情，读一次 `now_`，填进接收时间。
2. **问题在哪：每次读都是一次缓存行传输**
   - **这条行几乎总在写者的核上**：时间线程一直在写，行在它的 L1 里，是修改（M）状态。
   - **回调每读一次都不命中**：要把这条行从时间线程的核传过来，几十 ns，每条行情一次。
   - **还是数据竞争**：一个线程写、另一个线程读，中间没有任何同步。
3. **改了什么：回调自己读时钟，不碰共享字段**
   - **`clock_gettime` 走 vDSO**：内核把读时钟的代码和数据映射进每个进程。时钟源是 TSC 时，在用户态读本核的 TSC 再换算，不进内核，约 20 ns。
   - **没有共享数据了**：时间只放在局部变量里，跨核传输和数据竞争一起消失。
   - **前提是时钟源是 TSC**：不是的话每次都是系统调用，所以启动日志里记下时钟源和读一次的耗时。

```cpp
// 改之前：读另一个核不停改写的字段
out.recv_time = g_time_thread->now_;           // 每条一次跨核传输

// 改之后：回调自己读时钟，只用局部变量
timespec ts;
clock_gettime(CLOCK_REALTIME, &ts);            // 走 vDSO，不进内核
out.recv_time = to_recv_format(ts);
```

**结果**：单包处理延迟的中位数降约 17%，P99 不变。

### 2.5 两个数怎么来的：打点、配对、事先写死的判据 {#opt-measure}

| 改动 | 省的是什么 | 中位数 | P99 |
|---|---|---|---|
| 预触内存页 | 缺页只在第一次碰到某一页时发生，是偶发的大开销 | 不变 | 降约 57% |
| 回调自己读时钟 | 每条都少一次跨核读，是每条都有的小开销 | 降约 17% | 不变 |

- **打点**：每包在回调入口和发布完成各取一次时间，差值写进预先分配好的数组；热路径不做 I/O，跑完离线取分位数。
- **比较**：新旧两个程序用同一份回放，配对交替跑；先拿同一个程序当两边各跑几对，确认两边没有系统差。
- **判据事先写死**：中位数和 P99 都不许变差。试过写环前预取下一格，P99 变好、中位数慢了几纳秒，按判据没有留。
- **数字只说百分比**：测试机是虚拟机，绝对值偏高；量级是每包零点几微秒。

### 2.6 常问的知识点 {#opt-classic}

| 问 | 答 |
|---|---|
| 伪共享是什么 | 不同核写的变量在同一条缓存行，一个核一写，另一个核手里整条行就作废，下次访问要重新搬过来；`alignas` 分开就好。 |
| 为什么隔 128，不是 64 | Intel 的相邻行预取会把同一个 128 字节块里的两条行成对取进来，只隔 64 还可能被顺带拉走。 |
| 怎么确认是伪共享 | 先看布局，是不是同一行、不同核在写；再做只改对齐的对照实验；物理机上用 `perf c2c` 看 HITM。 |
| 缺页是什么，为什么集中在开盘 | 内存第一次写到某一页才真正分配，每次要陷入内核、清零、建映射；环第一圈写的全是新页，第一圈正好是开盘。 |
| 预触为什么要写，只读不行吗 | 只读会映射到全局共享的零页，物理页还是没分配；第一次写才真正分配。 |
| 为什么在绑好核的线程上预触 | 物理页默认分在第一次写它的线程所在的 NUMA 节点上，这样页就在回调线程本地。 |
| `clock_gettime` 为什么快 | 走 vDSO：读时钟的代码和数据映射进了进程，时钟源是 TSC 时在用户态读完，不进内核，一次 20 ns 左右。 |
| 读别的线程刷新的时间字段有什么问题 | 一是每条一次跨核搬行，几十纳秒；二是一个写、一个读、没有同步，严格说是数据竞争。 |
| 为什么一个降中位数、一个降 P99 | 中位数反映每条都走的正常路径，尾部反映偶发的大开销；读时钟每条都省一点，预触只去掉偶发的缺页。两个数不能互推。 |
| 延迟怎么测才不被测量本身干扰 | 热路径上只往预分配的数组里写差值，不打日志、不分配；跑完离线排序取分位数。 |

### 2.7 对着代码问的细节 {#details-false-sharing}

| 问 | 答 |
|---|---|
| 原来是哪两个变量在同一行 | 回调线程的写序号 `write_idx`，和落盘线程的读游标；读游标原来放在队列里，紧挨着写序号。 |
| 只读的变量和写的变量在一行，算不算伪共享 | 算，只要有一个核在写：读的那个核每次都要把行重新取回来，写的那个核每次都要先作废对方的副本。 |
| 为什么不把读游标也放在队列里、加 `alignas(128)` 就完了 | 也能消掉伪共享，但游标只有读者自己用，放共享区没有好处；放进 `Reader`，加读者不用改队列的布局。 |
| `static_assert` 钉的是什么 | 写序号从 128 字节边界开始，而且它后面不再有别的成员；读者对象正好 128 字节。以后谁加成员挤进这一块，编译就报错。 |
| 怎么证明是伪共享、改了有效 | 先看布局，两个变量在同一行、被不同的核写；再做对照，只改布局、别的不动，新旧交替跑多轮比中位数。物理机上可以用 `perf c2c` 看这条行的 HITM。 |
| 40% 和你实验里差好几倍，哪个对 | 都对，条件不一样：读者全速紧跟时差好几倍；简历的 40% 是按“高频读取”的节奏测的；落盘线程实际几毫秒醒一次，每条平均只省几纳秒。 |
| `prefault` 里为什么用 `volatile char*` | 写进去的 0 之后没人读，不加 `volatile`，编译器可以把整个循环当成无用的写删掉。 |
| 每 4096 字节写一次，用了大页还这样吗 | 步长按页大小走：2 MB 大页每 2 MB 写一次就够，而且大页本身缺页次数就少得多。 |
| 打点为什么用预分配的数组，不用 `vector::push_back` | `push_back` 扩容时会分配、拷贝，正好落在热路径上；预先开好，热路径只写一个数。 |
| 分位数为什么用 `nth_element` | 只要第 k 小的那个数，`nth_element` 平均线性时间，不用整个排序。 |

## 3. 手写练习：两份能跑的完整代码 {#handwrite}

前面的代码是片段，这一节补成带测试的完整程序：3.1 对第 1 部分，3.2 对第 2 部分。先按“开写前说”出声说 30 秒，再从空白写，打印“全部测试通过！”才算写对。参考代码只用标准库，厂商 SDK 用假的代替，编译命令在每份代码的开头。

### 3.1 行情接入：按配置接一家 → 统一结构 → 广播环 → 落盘线程 {#hw-md-feed}

- **开写前说**：启动时按配置接一家，回调线程是唯一的生产者，只做转换和写环；写就是取下一格、原地填、release 盖戳；落盘线程自己记 `next_idx`，醒来读到没有为止，一次减法分三种情况。
- **写的时候注意**：序号从 1 开始，全 0 的格子才不会被读成数据；比较写成 `int(戳 − next_idx) < 0`，回绕时也对；读者在生产者开始写之前建好；测试核四样：条数、序号连续、单位换算、没被套圈，再用一个小环测套圈时跳过的条数。
- **每一行会被怎么问**：见 [1.7](#classic)、[1.8 节](#details)。

<details>
<summary><strong>参考代码</strong>（153 行，先自己写，写完或卡住再展开）</summary>

```cpp
// 实习 1：行情接入。按配置接一家 → 回调线程转成统一结构 → 写进每格带戳的 SPMC 广播环 → 落盘线程批量读
// 要点：回调线程是唯一的生产者，只做转换和写环；写 = 下一格、原地填、release 盖戳；读者自记 next_idx，一次减法三种情况
// 编译：g++ -std=c++17 -O2 -Wall -Wextra -pthread i1_md_feed.cpp -o md_feed && ./md_feed
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <thread>

// ---- 统一结构：哪一家转换后都是它 ----
struct Snapshot {
    char     code[8];
    int64_t  time_ms;
    double   last;
    double   bid_px[10];
    int64_t  bid_vol[10];
    uint32_t seq;          // 这一家的第几条（测试用）
};

// ---- 两家厂商各自的结构（字段名、单位都不一样）----
struct VendorASnap { char code[8]; int64_t t; int64_t last_px; int64_t bid_px[10]; int64_t bid_vol[10]; };  // 价格放大 10000 倍
struct VendorBSnap { char symbol[8]; int64_t ts; double price; double bids[10]; int32_t lots[10]; };       // 量是手，1 手 = 100 股

// ---- SPMC 广播环：一个生产者，每格带戳，读者各记各的 ----
template <class T, uint32_t CNT>
class SPMCQueue {
    static_assert(CNT && !(CNT & (CNT - 1)), "CNT 必须是 2 的幂");
public:
    struct Reader {
        T* read() {
            auto& blk = q->blks[next_idx & (CNT - 1)];
            uint32_t new_idx = blk.idx.load(std::memory_order_acquire);
            int d = int(new_idx - next_idx);
            if (d < 0) return nullptr;              // 还没写到
            skipped += uint32_t(d);                 // 大于 0：被套圈，跳过了 d 条
            next_idx = new_idx + 1;
            return &blk.data;
        }
        SPMCQueue* q = nullptr;
        uint32_t next_idx = 0;                      // 读者私有，不在共享区
        uint64_t skipped = 0;
    };

    Reader getReader() { Reader r; r.q = this; r.next_idx = write_idx + 1; return r; }

    template <class Fill>
    void write(Fill fill) {                         // 只有一个线程调
        auto& blk = blks[++write_idx & (CNT - 1)];  // ① 下一格，序号从 1 开始
        fill(blk.data);                             // ② 原地填
        blk.idx.store(write_idx, std::memory_order_release);  // ③ 最后盖戳
    }

private:
    struct alignas(64) Block { std::atomic<uint32_t> idx{0}; T data; } blks[CNT];
    alignas(128) uint32_t write_idx = 0;
};

// ---- 两家的转换：回调里只做这个，然后写环 ----
template <class Q>
void on_vendor_a(Q& q, const VendorASnap& in, uint32_t seq) {
    q.write([&](Snapshot& out) {
        std::memcpy(out.code, in.code, 8);
        out.time_ms = in.t;
        out.last = in.last_px / 10000.0;
        for (int i = 0; i < 10; ++i) {
            out.bid_px[i]  = in.bid_px[i] / 10000.0;
            out.bid_vol[i] = in.bid_vol[i];
        }
        out.seq = seq;
    });
}
template <class Q>
void on_vendor_b(Q& q, const VendorBSnap& in, uint32_t seq) {
    q.write([&](Snapshot& out) {
        std::memcpy(out.code, in.symbol, 8);
        out.time_ms = in.ts;
        out.last = in.price;
        for (int i = 0; i < 10; ++i) {
            out.bid_px[i]  = in.bids[i];
            out.bid_vol[i] = int64_t(in.lots[i]) * 100;   // 手 → 股
        }
        out.seq = seq;
    });
}

enum class Vendor { A, B };                        // 启动时读配置决定接哪一家

// 跑一家：回调线程写 n 条，落盘线程每 200 µs 醒一次批量读，边读边核
void run(Vendor vendor, uint32_t n) {
    auto q = std::make_unique<SPMCQueue<Snapshot, 1 << 16>>();   // 真实工程里是 shm_open + mmap，全 0 就是空队列
    auto r = q->getReader();                       // 读者在生产者开始写之前建好
    std::atomic<bool> done{false};
    uint64_t lines = 0, bad = 0;

    std::thread disk([&] {
        for (;;) {
            bool fin = done.load(std::memory_order_acquire);
            while (Snapshot* s = r.read()) {       // 读到没有为止
                if (s->seq != lines) ++bad;        // 不丢、不乱
                double expect = 10.0 + (s->seq % 100) * 0.01;
                if (s->last < expect - 1e-9 || s->last > expect + 1e-9) ++bad;   // 价格换算
                if (s->bid_vol[0] != 500) ++bad;                                  // 量的换算
                ++lines;
            }
            if (fin) break;
            std::this_thread::sleep_for(std::chrono::microseconds(200));
        }
    });

    std::thread sdk([&] {                          // SDK 的回调线程：唯一的生产者
        for (uint32_t i = 0; i < n; ++i) {
            if (vendor == Vendor::A) {
                VendorASnap in{};
                std::memcpy(in.code, "600000\0", 8);
                in.t = i; in.last_px = 100000 + (i % 100) * 100;      // 10.00 + 0.01·k
                for (int k = 0; k < 10; ++k) { in.bid_px[k] = in.last_px - k * 100; in.bid_vol[k] = 500; }
                on_vendor_a(*q, in, i);
            } else {
                VendorBSnap in{};
                std::memcpy(in.symbol, "000001\0", 8);
                in.ts = i; in.price = 10.0 + (i % 100) * 0.01;
                for (int k = 0; k < 10; ++k) { in.bids[k] = in.price - k * 0.01; in.lots[k] = 5; }
                on_vendor_b(*q, in, i);
            }
        }
        done.store(true, std::memory_order_release);
    });

    sdk.join(); disk.join();
    std::printf("%s：写 %u 条，落盘 %llu 条，出错 %llu，被套圈跳过 %llu\n", vendor == Vendor::A ? "A" : "B",
                n, (unsigned long long)lines, (unsigned long long)bad, (unsigned long long)r.skipped);
    assert(lines == n && bad == 0 && r.skipped == 0);
}

int main() {
    run(Vendor::A, 200000);
    run(Vendor::B, 200000);

    // 套圈：CNT = 8，读者要第 2 条时生产者已经写到第 21 条
    SPMCQueue<int, 8> small;
    auto r = small.getReader();
    small.write([](int& x) { x = 1; });
    assert(*r.read() == 1 && r.read() == nullptr); // 读完第 1 条，第 2 条还没写到
    for (int i = 2; i <= 21; ++i) small.write([&](int& x) { x = i; });
    int* p = r.read();                              // 要第 2 条，那一格先后装过 2、10、18
    assert(*p == 18 && r.skipped == 16);            // 跳过 16 条，正好两圈
    std::printf("套圈：要第 2 条拿到第 %d 条，跳过 %llu 条\n", *p, (unsigned long long)r.skipped);
    std::printf("全部测试通过！\n");
}
```

</details>

### 3.2 行情优化：读写计数隔离、预触、读时钟、打点 {#hw-md-opt}

- **开写前说**：写序号独占一个 128 字节的块，读游标挪进读者自己的对象，用 `static_assert` 钉死布局；启动时在绑好核的线程上每页写一个字节；回调自己 `clock_gettime`；延迟打点进预分配的数组，跑完离线取分位数。
- **写的时候注意**：预触必须写、不能只读；分位数用 `nth_element`，不用整个排序。
- **我机器上的一次输出**（Windows）：两个计数在同一条缓存行约 440 ms，隔开约 40 ms。这个数字因机器而异。

<details>
<summary><strong>参考代码</strong>（121 行，先自己写，写完或卡住再展开）</summary>

```cpp
// 实习 2：行情优化。① 写序号和读游标按 128 字节隔离并钉死布局 ② 启动时预触内存页 ③ 回调自己读时钟 ④ 打点和分位数
// 编译：g++ -std=c++17 -O2 -Wall -Wextra -pthread i2_md_opt.cpp -o md_opt && ./md_opt
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <memory>
#include <thread>
#include <vector>
#ifdef __linux__
#include <sched.h>
#endif

struct Snapshot { int64_t recv_ns; double last; double bid_px[10]; int64_t bid_vol[10]; };
// ---- ① 伪共享：回调线程每条都写的写序号、落盘线程每读一条都写的读游标，各占一个 128 字节的块 ----
// 改之前：两个挨着，落在同一条缓存行，两个核每条都要把这一行抢过来
struct TailBefore {
    uint32_t write_idx;                    // 回调线程每条都写
    uint32_t disk_next;                    // 落盘线程每读一条都写
};
// 改之后：写序号在队列里独占一块；读游标挪进读者自己的对象，也独占一块
struct alignas(128) WriteIdx { uint32_t v = 0; };
struct alignas(128) Reader   { uint32_t next_idx = 0; };
template <class T, uint32_t CNT>
struct QueueLayout {
    struct alignas(64) Block { std::atomic<uint32_t> idx{0}; T data; } blks[CNT];
    WriteIdx write_idx;
};
using Q = QueueLayout<Snapshot, 1024>;
// 把布局钉死：以后有人增删成员，编译就报错
static_assert(sizeof(WriteIdx) == 128 && alignof(WriteIdx) == 128, "写序号要独占 128 字节");
static_assert(sizeof(Reader) == 128 && alignof(Reader) == 128, "读游标要独占 128 字节");
static_assert(offsetof(Q, write_idx) % 128 == 0, "写序号要从块边界开始");
static_assert(sizeof(Q) - offsetof(Q, write_idx) == 128, "写序号后面不能再挤别的成员");
static_assert(offsetof(TailBefore, disk_next) < 64, "改之前：两个在同一条缓存行");

// ---- ② 预触：每页写一个字节，逼内核现在就分配；要在绑到回调核的线程上调 ----
void pin_to_core(int core) {
#ifdef __linux__
    cpu_set_t set; CPU_ZERO(&set); CPU_SET(core, &set);
    sched_setaffinity(0, sizeof(set), &set);     // 绑核后再写，页落在这个核的 NUMA 节点
#else
    (void)core;
#endif
}
void prefault(void* p, size_t bytes, size_t page = 4096) {
    auto* c = static_cast<volatile char*>(p);
    for (size_t off = 0; off < bytes; off += page) c[off] = 0;   // 必须写：只读会映射到共享零页
}

// ---- ③ 读时钟：回调自己读，走 vDSO 不进内核；不再读别的核不停改写的共享字段 ----
inline int64_t now_ns() {
#if defined(CLOCK_REALTIME)
    timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return int64_t(ts.tv_sec) * 1'000'000'000 + ts.tv_nsec;
#else
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
#endif
}

// ---- ④ 打点：热路径只往预分配数组里写差值，跑完离线取分位数 ----
class LatencyRecorder {
    std::vector<int64_t> samples_;
    size_t n_ = 0;
public:
    explicit LatencyRecorder(size_t cap) : samples_(cap) {}   // 预先分配，热路径不分配
    void add(int64_t ns) { if (n_ < samples_.size()) samples_[n_++] = ns; }
    int64_t percentile(double p) {                           // 离线算，p 取 0–100
        assert(n_ > 0);
        size_t k = std::min(n_ - 1, size_t(p / 100.0 * double(n_)));
        std::nth_element(samples_.begin(), samples_.begin() + k, samples_.begin() + n_);
        return samples_[k];
    }
};

// ---- 演示：两个线程各写各的计数（像写序号和读游标），同一条行 vs 隔开 ----
template <class Pair>
double race_ms(Pair& p, uint64_t iters) {
    auto t0 = std::chrono::steady_clock::now();
    std::thread a([&] { for (uint64_t i = 0; i < iters; ++i) p.x.fetch_add(1, std::memory_order_relaxed); });
    std::thread b([&] { for (uint64_t i = 0; i < iters; ++i) p.y.fetch_add(1, std::memory_order_relaxed); });
    a.join(); b.join();
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
}
struct SameLine  { std::atomic<uint64_t> x{0}; std::atomic<uint64_t> y{0}; };
struct Separated { alignas(128) std::atomic<uint64_t> x{0}; alignas(128) std::atomic<uint64_t> y{0}; };

int main() {
    // 预触：一个 64 MB 的环，启动时每页写一个字节
    pin_to_core(0);
    size_t bytes = 64u << 20;
    std::unique_ptr<char[]> ring(new char[bytes]);
    auto t0 = std::chrono::steady_clock::now();
    prefault(ring.get(), bytes);
    double pre_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    std::printf("预触 64 MB 用了 %.1f ms（启动时付一次，开盘时不再缺页）\n", pre_ms);

    // 打点 + 分位数：分位数本身要算对
    LatencyRecorder rec(1000);
    for (int i = 1; i <= 1000; ++i) rec.add(i);
    assert(rec.percentile(50) == 501 && rec.percentile(99) == 991);

    // 用打点量一次“读时钟”的开销
    LatencyRecorder clk(100000);
    for (int i = 0; i < 100000; ++i) { int64_t a = now_ns(); int64_t b = now_ns(); clk.add(b - a); }
    std::printf("读一次时钟：P50 %lld ns，P99 %lld ns\n",
                (long long)clk.percentile(50), (long long)clk.percentile(99));

    // 伪共享演示（数字因机器而异，只看相对大小）
    SameLine s; Separated d;
    double t_same = race_ms(s, 20'000'000), t_sep = race_ms(d, 20'000'000);
    std::printf("两个计数同一条缓存行 %.0f ms，隔开 128 字节 %.0f ms\n", t_same, t_sep);
    assert(s.x == 20'000'000 && d.y == 20'000'000);
    std::printf("全部测试通过！\n");
}
```

</details>
