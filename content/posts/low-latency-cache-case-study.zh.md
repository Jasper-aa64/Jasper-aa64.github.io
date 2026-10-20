---
title: "低时延交易 —— 缓存案例：一次行情重算 64 个期权"
date: 2026-10-20
slug: "low-latency-cache-case-study"
description: "CppCon 2026 的一场演讲，把一段期权重算代码的中位数从 510 ns 压到 329 ns，浮点运算一条没少。顺着它走四步：两趟循环让一批期权的缺失同时在路上，批多大要按 LFB 的 16 个槽位、按行来算；算这一批之前先预取下一批，换成普通读或 NTA 反而更慢；用 clflushopt 交出只读一次的事件行，只在缓存挤满时才值；拆到两个核以后，跨核读一条行约 30 ns：别读回自己刚写、对面正盯着的那条行，结果行先用 clwb 写回，让 L3 直接回答。"
summary: "一条行情要碰 140 条缓存行，时间大多花在等它们。四步改的都不是计算，是数据什么时候到、到哪一层、在谁手里：让缺失同时在路上，提前要下一批，交出读一次就没用的行，跨核交接时少读一次，把要给对面读的行先放进 L3。"
chapter: 1
categories: [Systems]
tags: [cpp, cache, mlp, prefetch, clflushopt, clwb, mesi, hft, low-latency]
toc: true
math: true
homepage: false
---

一条行情进来，要把这只股票挂着的 64 个期权重算一遍：每个期权的价格跟着标的挪一点，再算一个 alpha，越过阈值的记下来。每个期权只有 25 次浮点运算，这段代码的中位数却要 510 ns，p90 超过 1 µs，CPU 大部分时间在等数据。

CppCon 2026 上，高频交易公司 Graviton Research Capital 的 Sanchit Gupta 拿这段代码讲了一场（[视频](https://youtu.be/FDjXUP6Am1M)、[幻灯片](https://github.com/CppCon/CppCon2026/blob/main/Presentations/The_Latency_Slippage.pdf)、[代码](https://github.com/0xsanchit/CacheLatency)；我是从[知乎上的一篇介绍](https://zhuanlan.zhihu.com/p/2095095452555391143)看到的）。他分四步把中位数压到 329 ns，p90 压到 550 ns。浮点运算一条没少，改的是数据什么时候到、到哪一层、那时在哪个核手里。

每一步用到的机制，博客里大多单独讲过：MLP（memory-level parallelism，内存级并行）和 LFB（line fill buffer，行填充缓冲）、软件预取、MESI。放进同一段代码里，能看到它们各值多少，也能看到它们在抢同一样东西：每个核只有 16 个 LFB，批处理、预取、`clflushopt` 都要占。下面的数字都是演讲那台机器上测的：i9-14900KS，核心 5.9 GHz，只开 4 个大核、关掉超线程，程序跑在隔离的核上；周期数按 3.19 GHz 的 TSC（time stamp counter，时间戳计数器）计。

## 1. 一次事件的账：140 条缓存行，大半从 L3 来

### 1.1 数据怎么摆：期权的地址在股票记录里

写行情的线程在另一个核上，每 5 µs 往一个 8 MiB 的环形缓冲区里写一条 192 B 的事件，正好 3 条缓存行。处理行情的线程绑在一个隔离的核上，每条事件读一次就不再碰。

事件里写着是哪只股票。股票表有 8,192 条记录，每条 576 B，也就是 9 条行：最新价，加上 64 个（期权编号，delta）。期权表有 524,288 条记录，每条 128 B，分成两条行：一条放价格，一条放算 alpha 要用的状态，两条都要读。

这里有一跳依赖：期权的地址是从股票记录里读出来的，股票记录没到之前，哪个期权都没法要。股票记录一到，64 个期权之间就互不相干了，谁先算都行。后面几步都绕着这两点转。

<a href="/images/cache-case-study/event-walk.zh.svg" target="_blank" rel="noopener"><img src="/images/cache-case-study/event-walk.zh.svg" alt="一次事件碰到的缓存行：写者在另一个核上，每 5 µs 往 8 MiB 的环形缓冲区写一条 192 B 的事件（3 行），处理线程读一次；事件里的股票编号指向股票记录（576 B，9 行：最新价和 64 个期权编号、delta）；期权的地址要从股票记录里读出来，这是一跳依赖；64 个期权记录各 128 B（2 行：价格一行、alpha 的状态一行），共 128 行，散在 52 万条记录里；alpha 越过阈值的期权编号记进结果。底部的条：3 + 9 + 128 = 140 行，期权占 128 行。" loading="lazy" decoding="async"></a>

写成代码：

```cpp
#include <cstdint>

constexpr int    K = 64;                          // 一只股票挂着的期权数
constexpr double kThreshold = 0.5;                // alpha 超过它就记下来

struct Holding { uint32_t option; float delta; };   // 期权编号，对这只股票的 delta

struct alignas(64) Event {                        // 192 B = 3 行
    uint64_t seq;
    uint32_t stock;
    double   px;
    char     book[168];
};
struct alignas(64) Stock {                        // 8 + 512 B，补齐到 576 B = 9 行
    double  last_px;
    Holding holds[K];
};
struct alignas(64) Option {                       // 128 B = 2 行
    double curr_px, actual_px, aux[6];            // 第 1 行：价格
    double ema, alpha, state[6];                  // 第 2 行：alpha 要用的状态
};

// 一串前后依赖的浮点运算（演讲里是 25 次），两条行都要读
inline double alpha_of(double px, double ref, double aux, double& ema) {
    ema = 0.9 * ema + 0.1 * px;
    double x = (px - ref) / (aux + 1.0), a = x;
    for (int i = 0; i < 10; ++i) a = a * x + 0.01 * i;
    return a + 0.01 * (px - ema);
}
```

### 1.2 基线：一个期权一个期权地取数、计算

处理一条事件：查股票记录，算出这次价格挪了多少（`move`），再挨个更新 64 个期权。循环单独写成 `price_span`，第 5 节拆到两个核时，两边各跑一段。

```cpp
// 一段 holdings 逐个重算：越过阈值的期权编号写进 hits，返回个数
int price_span(const Holding* h, int count, double move, Option* options, uint32_t* hits) {
    int n = 0;
    for (int j = 0; j < count; ++j) {
        Option& o = options[h[j].option];            // 地址从股票记录里读出来
        o.curr_px += move * h[j].delta;
        o.alpha = alpha_of(o.curr_px, o.actual_px, o.aux[0] + o.aux[4], o.ema);
        if (o.alpha > kThreshold) hits[n++] = h[j].option;
    }
    return n;
}

int on_tick(Event& ev, Stock* stocks, Option* options, uint32_t* hits) {
    Stock& st = stocks[ev.stock];                    // 9 行
    const double move = ev.px - st.last_px;
    st.last_px = ev.px;
    return price_span(st.holds, K, move, options, hits);
}
```

外面还有一层循环：自旋读环形缓冲区的序号（acquire 读），等到下一条事件就调 `on_tick`。演讲测的是每条事件的处理时间：中位数 510 ns，p90 1,012 ns，每条事件 8,142 条指令。

### 1.3 时间花在哪：130 次缺失，只重叠了一部分

一次事件要碰的行：

$$
\underbrace{3}_{\text{事件}} + \underbrace{9}_{\text{股票记录}} + \underbrace{64 \times 2}_{\text{期权}} = 140\ \text{条行}
$$

140 条里 128 条是期权，散在 52 万条记录里。跑 20 万条事件，实际碰到的表有 42.7 MiB，再加上不停流过的 8 MiB 环形缓冲区，一共 50.7 MiB，而 L3 只有 36 MiB：表不可能全留在缓存里，环形缓冲区流过时还在把它们往外挤。

基线每条事件的读平均落在这几层：

| 层 | 每条事件 | 这台机器上一次要多久 |
|---|---|---|
| L1 | 222 次 | 0.85 ns |
| L2 | 19 次 | 2.7 ns |
| L3 | 104 次 | 12.3 ns |
| 内存 | 7 次 | 88 ns |

L1 以外的 130 次缺失，大多落在 L3。假如一次只等一个：

$$
104 \times 12.3\ \text{ns} + 7 \times 88\ \text{ns} \approx 1.9\ \mu\text{s}
$$

比实测的 510 ns 长得多，说明乱序执行已经让一部分缺失重叠起来了。可每个核同时能挂 16 个缺失，64 个期权又互不依赖，按说能重叠得多得多。

## 2. 批处理：让一批期权的缺失同时在路上

### 2.1 为什么只重叠了一部分：计算占住了乱序窗口

乱序执行能提前发出的读，限于它看得到的那段指令：取进来、还没退休的指令都在 ROB（reorder buffer，重排序缓冲）里，读要先进了 ROB 才发得出去（[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/) 1.3.2）。基线的循环里，两个期权的读之间隔着一整个期权的计算。那串前后依赖的浮点运算要等数据到了才能开始，等的时候就占着 ROB 的位置；占上几个期权，ROB 就满了，再往后那些期权的读还没被取进来，也就发不出去。

所以同时有几个缺失在路上，是写代码的顺序定的。64 个期权的更新互不依赖，顺序可以改。

### 2.2 两趟：先把一批的行都要过来，再集中算

```cpp
#include <algorithm>

// 一批 D 个：第一趟只取数，第二趟集中算
template <int D>
int price_span_batched(const Holding* h, int count, double move, Option* options, uint32_t* hits) {
    int n = 0;
    for (int b = 0; b < count; b += D) {
        const int m = std::min(D, count - b);
        Option* o[D];
        double px[D], ref[D], arg[D], ema[D];
        for (int k = 0; k < m; ++k) {                 // 第一趟：两条行都碰到，读进小数组
            o[k]   = &options[h[b + k].option];
            px[k]  = o[k]->curr_px + move * h[b + k].delta;
            ref[k] = o[k]->actual_px;
            arg[k] = o[k]->aux[0] + o[k]->aux[4];
            ema[k] = o[k]->ema;
        }
        for (int k = 0; k < m; ++k) {                 // 第二趟：算 alpha，写回
            o[k]->curr_px = px[k];
            o[k]->alpha = alpha_of(px[k], ref[k], arg[k], ema[k]);
            o[k]->ema = ema[k];
            if (o[k]->alpha > kThreshold) hits[n++] = h[b + k].option;
        }
    }
    return n;
}
```

第一趟只取数：算地址，把两条行里要用的字段读进几个小数组。相邻两个期权的读之间只隔几条指令，一批 D 个期权的 2D 条行几乎同时发出去。第二趟再算 alpha、写回。

D = 4 和基线比（每条事件）：

| | 基线 | D = 4 |
|---|---|---|
| 中位数 | 510 ns | 469 ns（−8%） |
| p90 | 1,012 ns | 776 ns（−23%） |
| L3 命中 | 103.7 次 | 104.0 次 |
| 指令数 | 8,142 | 9,191（+13%） |
| 每周期退休的指令（IPC） | 1.98 | 2.47（+25%） |

L3 命中一次没少：批处理不消除缺失，只是不再一个一个地等。多出来的 1,049 条指令是小数组和第二趟循环的开销，可同样的活挤进了更短的时间里。p90 比中位数降得多：慢的事件多半是缺失更多的那些，重叠省下的也更多。

### 2.3 一批多大：LFB 要按行算

一次缺失从发出到行回来，要占一个 LFB。演讲用 lemire 的 [testingmlp](https://github.com/lemire/testingmlp) 测过这台机器：同时有至少 16 个缺失在路上的周期占 29.7%，有 17 个的周期一次也没有，所以每个核是 16 个。

每个期权 2 条行，一批 D 个就是 2D 个缺失。D 从 1 扫到 64：

<a href="/images/cache-case-study/batch-sweep.zh.svg" target="_blank" rel="noopener"><img src="/images/cache-case-study/batch-sweep.zh.svg" alt="批大小 D 扫描（同一次运行，每条事件，ns）：D = 1 中位数 590、p90 961；D = 2 为 525、856；D = 4 为 474、776；D = 8 为 525、801；D = 16 为 545、791；D = 64 为 580、741。每批同时在路上的行数是 2D：2、4、8、16、32、128，LFB 只有 16 个。中位数在 D = 4 最低，p90 在 D = 64 最低；D = 64 时 LFB 满着的周期每条事件 1,001 个，D = 1 和 4 时只有 35、36。" loading="lazy" decoding="async"></a>

D = 4（8 条行）中位数最低。D = 8 已经是 16 条行，占满全部 LFB，可股票记录、事件和硬件预取器也要用 LFB，中位数回到 525 ns。D = 64 把整个事件的 128 条行一口气要完才开始算，LFB 满着、新请求进不去的周期每条事件 1,001 个（D = 1 和 4 时只有 35、36），中位数退到 580 ns。可它的 p90 是这次扫描里最好的 741 ns：中位数和尾部的最优点不在同一个 D 上，演讲按中位数选了 D = 4。

批处理以后，一批的 2D 条行一起在路上了，可第二趟算的时候没有新的请求发出去：算和等还是轮流来，每一批开头都要等这一批的行回来。下一批要哪些期权，股票记录里早就写着，完全可以在算这一批之前就要。

## 3. 软件预取：算这一批时，下一批已经在路上

### 3.1 预取不是 load：不占 ROB，但占 LFB

第一趟本来就是在要数据，那为什么不把下一批的第一趟也提前做了？因为普通的读有目标寄存器，数据不回来它就不能退休，后面的指令全堵在 ROB 里，正是 2.1 节的问题。软件预取（`_mm_prefetch`）没有目标寄存器，没有指令等它，发出去就能退休，不占着 ROB。

但它和普通缺失一样要占一个 LFB，直到行回来，用的还是那 16 个。第二个参数是提示：`_MM_HINT_T0` 取进包括 L1 在内的各级缓存，T1、T2 只取进外面几层，NTA 表示数据只用一次、尽量别占缓存（对应的指令和 GCC 写法见 [#14](/zh/posts/prefetch-warmup-double-buffer/) 1.2）。ARM 上对应的是 `prfm` 指令，GCC 的 `__builtin_prefetch` 两边都能编。

### 3.2 什么时候要：第一趟之后、第二趟之前

下一批的期权编号就在股票记录里，这时股票记录早就在 L1 了，地址现成。把下面几行插到两趟之间（`#include <immintrin.h>`）：

```cpp
        for (int k = b + D; k < std::min(b + 2 * D, count); ++k) {   // 下一批的两条行先要着
            const char* p = reinterpret_cast<const char*>(&options[h[k].option]);
            _mm_prefetch(p,      _MM_HINT_T0);
            _mm_prefetch(p + 64, _MM_HINT_T0);
        }
```

每个期权两条行都要，因为第一趟两条都读。第一批不用专门预热：它自己的第一趟就是在并行地取数，从第二批起预取才开始赚。这一批的计算够长，下一批的行在这段时间里回得来。

D = 4 时，中位数 469 → 414 ns（−12%），p90 776 → 710 ns。

提前量就是一批，D 个期权。演讲另外扫了一次：D = 4 中位数最好（394 ns），D = 16 的 p90 最好（645 ns）。D = 2 太近，一批的计算盖不住一次缺失，每条事件有 172 次读撞上还在路上的预取（D = 4 时 17 次）。D = 64 一批就是整个事件，没有下一批可要。

### 3.3 换成普通读、换成 NTA：都更慢

同样在 D = 16 的批处理上、同样的提前量，只换预取那两行的写法（每条事件）：

| 写法 | 中位数 | p90 | 等 L1 缺失的周期 |
|---|---|---|---|
| 不预取（只批处理） | 520 ns | 776 ns | 1,074 |
| `_MM_HINT_T0` | 505 ns | 655 ns | 292 |
| 换成普通读 | 550 ns | 831 ns | — |
| `_MM_HINT_NTA` | 856 ns | 1,012 ns | 1,995 |

换成普通读，行也提前要了，却比不预取还慢：每条读都要等数据回来才能退休，又把 ROB 堵上了。NTA 慢了 65%：它告诉硬件这些行用完就可以扔，可这些期权下一条事件还要用。九成的行情落在同一批 1,024 只股票上，它们的期权一共

$$
1024 \times 64 \times 128\ \text{B} = 8\ \text{MiB}
$$

装不进 2 MiB 的 L2，装得进 36 MiB 的 L3。T0 让它们留在 L3 里，NTA 偏偏把下一条事件要用的这些行先扔了。

预取管的是下一步要哪条行。新的行进缓存，就得有旧的行出去，出去哪一条由替换策略决定，而替换策略不知道哪些行已经没用了。

## 4. 交出死数据：clflushopt

### 4.1 读一次就死的行：照样占着三级缓存

每条事件的 3 条行（一条头、两条盘口）读完就没用了，环形缓冲区转完 8 MiB 一圈之前，没人再碰它们。可它们和别的行一样，在 L1、L2、L3 里各占一个位置，而且这个位置是挤掉别的行换来的，挤掉的可能正是下一条事件要用的期权。替换策略一般是伪 LRU（近似“最久没用的先换出”），这 3 条行刚刚用过，反而最不会被换出去。

硬件不知道它们已经死了，程序知道。

### 4.2 clflush 与 clflushopt：一个串行，一个能并行

`clflush` 把一条行从所有层级里作废，脏的先写回内存。它和前后的读写严格保序，连着发几条就一条一条地等。`clflushopt` 作废得一样彻底，但不保序，几条可以同时在路上，走的也是 LFB。ARM 上对应的是 `dc civac`（按地址写回并作废）。

把三条事件行在处理完以后交出去：

```cpp
int on_tick(Event& ev, Stock* stocks, Option* options, uint32_t* hits) {
    Stock& st = stocks[ev.stock];
    const double move = ev.px - st.last_px;
    st.last_px = ev.px;
    const int n = price_span_batched<4>(st.holds, K, move, options, hits);
    char* e = reinterpret_cast<char*>(&ev);          // 这条事件不会再有人读
    _mm_clflushopt(e);
    _mm_clflushopt(e + 64);
    _mm_clflushopt(e + 128);
    return n;
}
```

GCC 编译要加 `-mclflushopt`（第 5 节的 `clwb` 要加 `-mclwb`），或者用支持它们的 `-march`。

结果：中位数 414 → 409 ns（−1.2%），p90 710 → 705 ns。每条事件多了 6 条指令（三条 `clflushopt` 和算地址），L1 命中多了 2.2 次，等 L1 缺失的周期 634 → 495（−22%）。中位数几乎没动，等缺失的时间却少了五分之一。

### 4.3 只在缓存挤满时才值

演讲另外做了一个小实验：每条事件读 4 条只用一次的流式行，再查一次每条事件都要用的热表；几组只差一条语句（不交出、`clflushopt`、`clflush`），热表的大小分两档：大到受挤压，或者小到没压力。

| | 不交出 | `clflushopt` |
|---|---|---|
| 热表受挤压 | 106.4 ns | 92.6 ns（−13%） |
| 没有压力 | 83.2 ns | 86.4 ns（+4%） |

受挤压时，L3 缺失从每条事件 4.13 次降到 3.69 次。没有压力时，没有值得保护的行，交出就是纯开销。LFB 忙的时间从 0.8% 涨到 4.0%：这些 `clflushopt` 经过 LFB，并行地做。换成 `clflush`，不管有没有压力都要 807 个周期，它是一条一条串行做的。

一个核上能做的到这里差不多了：510 → 409 ns。剩下的时间主要是 64 个期权本身的计算和还要等的缺失。64 个期权互不相干，自然想到分给两个核算。可两个核一交换数据，就有了一种新的缺失：要的行在另一个核手里。

## 5. 拆到两个核：跨核读一条行约 30 ns

### 5.1 怎么拆：主核留 40 个，辅核拿 24 个

能拆的是 64 个期权的更新。不能拆的是前面那一段：轮询环形缓冲区、查股票、算 `move`，前后依赖，什么也预取不了。所以主核留下这一段和较大的一份（40 个），后 24 个交给辅核。交接时把期权编号、delta 和 `move` 一起给过去，辅核就不用再读股票记录，省掉的正是那一跳依赖。辅核要等主核交接以后才能开始，给它少一点，它才能在主核算完自己那份之前算完。

```cpp
#include <atomic>

constexpr int kAux = 24;                              // 交给辅核的期权数，主核留 40 个

struct alignas(64) Req {                              // 主核 → 辅核
    std::atomic<uint64_t> seq{0};
    double  move;
    Holding give[kAux];
};
struct alignas(64) Res {                              // 辅核 → 主核
    std::atomic<uint64_t> seq{0};
    int      n;
    uint32_t hit[kAux];
};

// 主核：查股票、算 move，交出后 24 个，自己算前 40 个，再收辅核的结果
int main_tick(Event& ev, Stock* stocks, Option* options, uint32_t* hits,
              Req& req, const Res& res, uint64_t seq) {
    Stock& st = stocks[ev.stock];
    const double move = ev.px - st.last_px;
    st.last_px = ev.px;
    for (int j = 0; j < kAux; ++j) req.give[j] = st.holds[K - kAux + j];
    req.move = move;
    req.seq.store(seq, std::memory_order_release);
    int n = price_span_batched<4>(st.holds, K - kAux, req.move, options, hits);
    while (res.seq.load(std::memory_order_acquire) != seq) {}
    for (int i = 0; i < res.n; ++i) hits[n++] = res.hit[i];
    return n;
}

// 辅核：等到这一轮的请求，算交过来的 24 个，结果写进 res
void aux_tick(const Req& req, Res& res, Option* options, uint64_t seq) {
    while (req.seq.load(std::memory_order_acquire) != seq) {}
    uint32_t hit[kAux];
    const int n = price_span_batched<4>(req.give, kAux, req.move, options, hit);
    for (int i = 0; i < n; ++i) res.hit[i] = hit[i];
    res.n = n;
    res.seq.store(seq, std::memory_order_release);
}
```

两个核用 release 写、acquire 读交接（[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/)）：主核写好 `req` 再发布序号，辅核看到序号再读；结果反过来走一遍。

结果：中位数 409 → 364 ns（−11%），p90 705 → 575 ns（−18%）。主核自己那段 365 ns，辅核那段 298 ns，主核仍然最后一个算完，事件的时间由它定。

交接本身也要花时间：`req` 和 `res` 都是一个核写、另一个核读，每条行都要从一个核走到另一个核。下图标出了主核在哪两处要等对面：

<a href="/images/cache-case-study/two-core-handoff.zh.svg" target="_blank" rel="noopener"><img src="/images/cache-case-study/two-core-handoff.zh.svg" alt="拆到两个核：主核（CPU 1）轮询环形缓冲区、查股票、算 move，写 req 并发布序号，算自己的 40 个，等 res 的序号，收结果；辅核（CPU 2）自旋读 req 的序号，算交过来的 24 个，写 res 并发布序号，再 clwb。主核两处要等对面：一，算自己那 40 个时读回 req.move，可辅核刚读过这条行，副本被拿走了，要回辅核拿，约 28 ns，改成用主核自己的 move；二，读 res，那是辅核刚写的脏行，要去辅核那里拿，约 30 ns，辅核先 clwb 写回，L3 直接回答，约 12 ns。" loading="lazy" decoding="async"></a>

第一处是主核自己的一次读，看上去完全免费。

### 5.2 读回自己刚写的行：对面一读，副本就没了

主核交接完，算自己那 40 个时传的是 `req.move`，也就是刚刚写进交接内存的那个值。看上去是一次 L1 命中，自己刚写的，还能不在 L1 里？

可辅核正在自旋读 `req.seq`，它和 `move` 在同一条行上。主核写完，这条行在主核那里是 Modified；辅核一读，这条行基本就被拿走了，没给主核留副本。主核再读 `req.move`，要去辅核那里拿回来。

演讲为此单独测了一条行在两个核之间的代价：核 1 先把行弄成干净的或脏的，核 2 读一次或者不碰，核 1 再碰一次并计时，测 4,096 轮。

| 情形 | 核 1 再碰一次 |
|---|---|
| 核 2 没碰过，核 1 读 | 0.8 ns |
| 行是干净的，核 2 读过，核 1 读 | 1.0 ns，E 变 S，核 1 的副本还在 |
| 行是脏的，核 2 读过，核 1 读 | 28 ns，是前者的 34 倍 |
| 核 2 读过，核 1 写 | 54 ns，没人读过时只要 2.8 ns |

整个实验 L3 缺失是 0，这些时间全是一致性协议的开销，不是容量不够。写比读还贵：核 2 手里有副本，核 1 要先让它作废、等它回话，才能写（[MESI 缓存一致性](/zh/posts/low-latency-mesi-cache-coherence/)第 5 节）。

改法就是少一个 load、少一条指令：主核用自己手里的 `move`。

```diff
-    int n = price_span_batched<4>(st.holds, K - kAux, req.move, options, hits);
+    int n = price_span_batched<4>(st.holds, K - kAux, move, options, hits);
```

中位数 364 → 344 ns（−5.5%），p90 575 → 555 ns，每条事件的跨核转发 0.96 → 0.82 次。[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 的伪共享是同一回事：一条行上有别的核在读写的变量，你对这条行的每次访问都可能要过一次核。这里那个变量是 `seq`，而 `move` 本来就在主核手里。

### 5.3 L3 什么时候能直接回答：一个核独占着，就得先去问它

反方向是主核读辅核写好的结果 `res`。读一条别的核碰过的行要多久，要看这条行这时在哪、是什么状态。演讲的第二个实验：核 2 把行写脏或者只读一下，再扫一遍自己的数组，把这条行挤到 L1、L2、L3 或者内存；然后核 1 读它一次并计时。

| 行在哪、什么状态 | 核 1 读一次 |
|---|---|
| 干净，在核 2 的 L1 | 29 ns |
| 干净，在核 2 的 L1 到 L3 之间 | 25–29 ns |
| 干净，两个别的核都有（共享） | 13 ns，L3 直接回答 |
| 干净，连 L3 也被挤掉 | 99 ns，从内存来 |
| 脏，还在核 2 的 L1 或 L2 | 28–30 ns，和干净的一样 |
| 脏，被挤出核 2 的 L2 | 95 ns，从内存来 |
| 实验本身（栅栏加一次 L1 命中） | 0.8 ns |

能看出两件事。第一，只要一条行可能还在某一个别的核手里，哪怕它是干净的，L3 也不能自己回答：那个核独占着它（E），可以不打招呼就改成 M，L3 不知道它改没改，只能先去问。两个核都拿着（S）就不一样了，谁要写都得先通知别人，L3 手里那份一定是最新的，13 ns 直接给。

第二，同样被挤出核 2 的 L2，干净的行留在了 L3（29 ns，L3 命中），脏的行没进 L3，直接写回了内存（95 ns，每次读 0.96 次 L3 缺失，也没有哪个核拿着它）。Intel 客户端芯片的 L3 既不包含 L2，也不和 L2 互斥：L2 换出一条行时 L3 留不留，是没有公开的启发式规则，这台机器上表现为干净的留、脏的不留。

结果行 `res` 正好是贵的那种：辅核刚写完，脏的，还在辅核的 L1 里，主核读它得去问辅核。要是辅核写完就把它写回、让 L3 有一份干净的，主核就不用去问了。

### 5.4 clwb：写完先写回，L3 就能直接回答

`clwb` 和 `clflushopt` 是一个模子：都不保序，几条可以同时经过 LFB 在路上，要等它们做完就加一道栅栏。区别在留下什么：`clflushopt` 把行扔掉，`clwb` 把脏数据写回、行还留着（Intel 手册说留不留是给硬件的提示，这台机器上留了）。所以只读一次的事件行适合交出去，马上要被别的核读的行适合写回。ARM 上最接近的是 `dc cvac`（按地址写回，不作废）。

单独测一条行，核 2 写过或读过，核 1 读：

| 核 2 对这条行做过什么 | 不处理 | 核 2 先 `clwb` |
|---|---|---|
| 写过（脏） | 30 ns | 12 ns（−60%），L3 直接回答 |
| 只读过（干净） | 28 ns | 26 ns，没什么可写回，还得去问核 2 |

脏行写回以后，读它和两个核共享时一样快；干净的行没有脏数据可写，`clwb` 什么也没改变。

放进交接：辅核发布结果以后，把 `res` 的每条行都 `clwb` 一遍。

```cpp
    res.seq.store(seq, std::memory_order_release);
    for (std::size_t i = 0; i < sizeof(Res); i += 64)    // 发布以后，把结果的每条行写回（行还留着）
        _mm_clwb(reinterpret_cast<char*>(&res) + i);
    _mm_mfence();                                         // 等这些写回做完
```

主核每条事件的跨核转发 0.87 → 0.34 次，普通的 L3 命中 2.53 → 3.07 次：结果在 L3 里等主核，而不是在辅核的 L1 里。主核等辅核结果的那一段从 111 ns 降到 97 ns；辅核的计算一点没少，少的只是主核的等待。中位数 344 → 329 ns，p90 555 → 550 ns。

演讲只推了辅核到主核这一个方向。主核交出去的 `req` 行，辅核读它时同样要去主核那里拿，也可以写完就 `clwb`；只是主核在关键路径上，多出来的这几条指令要算进事件的时间里，值不值得要测了才知道。
