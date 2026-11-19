---
title: "IV：因子回测框架：一天怎么跑"
date: 2026-11-18T00:00:00+08:00
slug: "backtest-framework"
description: "简历实习第 5、6 条的专页，补 fir 里没答上的“回测系统怎么搭的”：按交易日一天一天跑，每天 4 步，读行情文件、按股票装进 arena 切出的数组、逐条喂给和实盘同一份的因子、每个 bar 收盘写一行结果。分两部分：代码（第 5 条，框架一天怎么跑）和优化（第 6 条的两轮，以及第 4 条因子侧的改法），最后是常问的题。"
weight: 3
toc: true
---

这一页补 fir 里没答上的那题：**回测系统怎么搭的**。框架原本就有，我做的是简历上第 5 条的验证流程和第 6 条的两轮优化。为了讲清楚，这里把框架重写成一个能跑的简化版，名字不是原工程的；这一页分两部分：[第 2 节](#code)是代码，框架一天怎么跑；[第 3 节](#opt)是优化，每一处都对到第 2 节的代码。验证流程（比输出、配对计时）在[实习拆解页第 5 节](/zh/interview/cv-internship/#backtest-flow)。

> **回放、回算、回测，三个词**（[因子生产 2 节](/zh/ref/factor-production/#replay)）
>
> - **回放**：把录下来的行情按原来的顺序重喂一遍，用来对账、复现问题。
> - **回算**：在历史行情上把因子值批量算出来，存成文件。
> - **回测**：拿因子值模拟交易、算收益。
>
> 简历上叫“回测框架”。按这三个词分，**它做的是回算**：用历史行情把因子按实盘的方式重算一遍，每只股票每个 bar 写一行因子值。拿这些值去模拟交易、算收益是研究那边的事，不是我负责的。

## 1. 一分钟讲法 {#pitch}

> 1. **框架原本就有，按交易日一天一天跑，每天 4 步**：读当天的行情文件；按股票装进各自的数组；一只股票从头走到尾，逐条喂给因子的 `on_tick`，因子和实盘是同一份代码；每个 bar 收盘取一次因子值，写成结果文件。
> 2. **一天约 650 万条 3 秒快照、2000 多只股票**。因子的状态按股票存、跨天保留，滚动窗口能接上前一天。
> 3. **我做了两件事**：先给它搭验证流程，每个改动先比输出，再配对计时；再按这个流程优化，第一轮去掉每天重复的初始化，约 22%；第二轮改行情的装载，约 44%。

## 2. 代码：框架一天怎么跑 {#code}

简历第 5 条。这一节的代码都是优化以后的样子；改之前是什么样、改了什么，在[第 3 节](#opt)。

### 2.1 整体：一天 4 步 {#steps}

| 步 | 代码里是 | 做什么 | 对应的优化 |
|---|---|---|---|
| ① 读行情文件 | `read_day` | 当天的快照按时间排好，一行是“哪只股票 + 一条快照” | — |
| ② 装进每只股票的数组 | `load_day`（[2.3](#load)） | 先数每只股票今天几条，从 arena 切一段，再按行写进去 | 第二轮全部 5 处（[3.2](#opt-load)）；第一轮去掉排序（[3.1](#opt-init)） |
| ③ 逐条回放 | `replay_and_write` 的内层循环（[2.4](#replay)） | 一只股票走到底，bar 收盘点之前的行情都喂 `on_tick` | 因子侧的改法（[3.3](#factor-opt)） |
| ④ 写结果 | `replay_and_write` 里的 `fprintf` | 每个 bar 收盘写一行：日期、时间、代码、因子值 | 第一轮：时间字符串只格式化一次（[3.1](#opt-init)） |

主循环就这几行：

```cpp
const auto bars = build_bar_timeline();          // bar 时间轴：建一次，所有股票、所有交易日共用
std::vector<std::string> time_str;               // 时间字符串：4801 个，只格式化一次
for (int64_t t : bars) time_str.push_back(format_time(t));
std::vector<Factors> state(n_stocks);            // 每只股票的因子状态，跨交易日保留
Arena arena;                                     // 一块 arena，跨交易日复用

for (const auto& date : dates) {                 // 按交易日一天一天跑
    auto file = read_day(date);                  // ① 读行情文件
    load_day(file, stocks, arena);               // ② 装进每只股票的数组
    replay_and_write(date, stocks, state, bars, time_str, out);   // ③ 逐条回放，④ 写结果
}
```

- **为什么按天用一块 arena：一天的行情一起生、一起死，并且一天能整块放进内存（约 2.4 GB）。** 不能切得更小，是因为行情文件按时间排，读完一整天才凑得齐任何一只股票的数组。天和天之间只有因子状态要接上（滚动窗口），行情可以一天一换；要并行的话，也是按日期分片（[3.2 ④](#opt-load)、[回测平台 4 节](/zh/ref/backtest-platform/#split)）。
- **为什么先装进每只股票的数组，再回放**：因子是每只股票自己的时间序列，状态按股票存。一只股票连着从头走到尾，它的因子状态一直在缓存里；按文件顺序读一行喂一行，就是每条都换一只股票。

### 2.2 数据：一条行情、一只股票、一块 arena {#data}

```cpp
// 一条行情：3 秒快照。这里的简化版 360 字节（原工程约 370），怎么从约 850 字节减下来的见 3.2 ②
struct Tick {
    int64_t time;                 // 当天的毫秒数，比如 9:30:00 是 34200000
    double  pre_close, last;      // 昨收价、最新价
    int64_t volume;               // 成交总量
    double  amount;               // 成交总金额
    double  bid_px[10], ask_px[10];
    int64_t bid_vol[10], ask_vol[10];
};
static_assert(std::is_trivially_destructible_v<Tick>);   // 没有析构要跑，arena 才能整块丢

// 行情文件里的一行：哪只股票 + 这条快照；文件按时间排好
struct Row { int stock; Tick tick; };                    // stock 是读文件时把代码换成的编号

// 每只股票一天的对象：只放代码、指针和条数
struct StockDay {
    std::string code, exchange;   // 这只股票的属性，存一份，行情记录里不放
    Tick* ticks = nullptr;        // arena 里切给它的那一段
    int   tick_count = 0;
};

// 一天的行情记录放进一块 arena，跨交易日复用；按字节记账，什么类型都能切
class Arena {
    char*  base_ = nullptr;
    size_t cap_ = 0, used_ = 0;                          // 单位是字节
public:
    void reset(size_t need) {                            // 每个交易日开头调一次，need 是今天要用的总字节数
        if (need > cap_) {                               // 不够才换块，换的时候多要一半
            if (base_) munmap(base_, cap_);
            cap_  = need + need / 2;
            base_ = static_cast<char*>(mmap(nullptr, cap_,
                        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
        }
        used_ = 0;                                       // 够用：偏移归零，原地覆盖着写
    }
    template <class T>
    T* take(size_t n) {                                  // 切 n 个 T；放不下返回空
        static_assert(std::is_trivially_destructible_v<T>);   // 没有析构要跑，才能整块丢
        // 偏移向上取整到 alignof(T)（一定是 2 的幂）；base_ 来自 mmap、页对齐，偏移对齐了指针就对齐
        size_t start = (used_ + alignof(T) - 1) & ~(alignof(T) - 1);
        if (start + n * sizeof(T) > cap_) return nullptr;
        used_ = start + n * sizeof(T);
        return reinterpret_cast<T*>(base_ + start);
    }
};

// 用法：arena.reset(今天总条数 * sizeof(Tick));  Tick* p = arena.take<Tick>(n);
```

- **`Tick` 只有标量和定长数组**：没有要析构的成员，`static_assert` 钉住，arena 才能整块丢、整块覆盖。
- **`StockDay` 只放这只股票的属性和一个指针**：代码、交易所存一份；行情在 arena 里，按实际条数切一段给它。
- **一天多大**：650 万条 × 约 370 字节，约 2.4 GB，放进一块 arena，跨交易日复用。
- **`Arena` 按字节记账，`take<T>` 切之前先对齐**：现在只放 `Tick`，每段都是 `sizeof(Tick)` 的整数倍，取整那一行实际不改变偏移；留着它，以后同一块里混放别的结构也不用改 arena。
- **这三个结构都是第二轮优化以后的样子**：`Tick` 原来约 850 字节、带两个 `string`，`StockDay` 原来是 6000 条的定长数组，改了什么见 [3.2](#opt-load)。

### 2.3 第 1、2 步：读文件，装进每只股票的数组 {#load}

```cpp
void load_day(const std::vector<Row>& file, std::vector<StockDay>& stocks, Arena& arena) {
    std::vector<int> rows_today(stocks.size(), 0);
    for (const Row& r : file) ++rows_today[r.stock];          // 第一遍：每只股票今天几条
    arena.reset(file.size() * sizeof(Tick));                  // 一天一块，够用就原地覆盖
    for (size_t i = 0; i < stocks.size(); ++i) {
        stocks[i].ticks = arena.take<Tick>(rows_today[i]);    // 按实际条数切一段
        stocks[i].tick_count = 0;
    }
    for (const Row& r : file) {                               // 第二遍：按行写进去
        StockDay& s = stocks[r.stock];
        s.ticks[s.tick_count++] = r.tick;                     // 文件按时间排好，装进来已经有序
    }
}
```

- **为什么数两遍**：先知道每只股票今天几条，才能从 arena 里给它切连续的一段；不数就只能按上限预留，又回到 6000 条定长。
- **为什么不排序**：行情文件本来就按时间排，按行写进去，每只股票的数组自然有序。原来每只股票装完还要再排一次，第一轮优化把它去掉了（[3.1](#opt-init)）。
- **读文件这一步不是重点**：格式是厂商定的，这里把读出来的行当成一个数组 `file`。

### 2.4 第 3、4 步：逐条喂因子，每个 bar 写一行 {#replay}

先是 bar 时间轴：3 秒一个收盘点，所有股票、所有交易日共用一份。

```cpp
std::vector<int64_t> build_bar_timeline() {
    std::vector<int64_t> bars;
    for (int64_t t = 34200000; t <= 41400000; t += 3000) bars.push_back(t);   // 9:30:00 – 11:30:00
    for (int64_t t = 46803000; t <= 54000000; t += 3000) bars.push_back(t);   // 13:00:03 – 15:00:00
    return bars;                                                              // 2401 + 2400 = 4801 个
}
```

然后一只股票从头走到尾：

```cpp
size_t replay_and_write(const char* date, const std::vector<StockDay>& stocks,
                        std::vector<Factors>& state, const std::vector<int64_t>& bars,
                        const std::vector<std::string>& time_str, std::FILE* out) {
    size_t rows = 0;
    for (size_t i = 0; i < stocks.size(); ++i) {
        const StockDay& s = stocks[i];
        Factors& f = state[i];
        const Tick* last = nullptr;
        int k = 0;
        for (size_t b = 0; b < bars.size(); ++b) {
            while (k < s.tick_count && s.ticks[k].time <= bars[b]) {   // 收盘点之前的都归这个 bar
                f.on_tick(s.ticks[k]);
                last = &s.ticks[k++];
            }
            if (!last) continue;                // 今天还没来过行情：这个 bar 不输出
            f.on_bar(*last);                    // 这个 bar 里没有新行情：沿用上一条
            std::fprintf(out, "%s,%s,%s,%.6g,%.6g\n", date, time_str[b].c_str(),
                         s.code.c_str(), f.spread.value(), f.vol.value());
            ++rows;
        }
    }
    return rows;
}
```

- **bar 怎么切**：时间不晚于收盘点的行情都归这个 bar，所以 9:30:00 整那一条归第一个 bar。这类约定和研究侧对不上，结果就对不上（[实习拆解页 3.1](/zh/interview/cv-internship/#factor-ontick)）。
- **空 bar 怎么补**：这个 bar 里没有新行情，就拿上一条行情收盘；开盘以后还没来过行情的 bar 不输出。
- **结果写多少**：2000 多只 × 4801 个 bar，一天约 1000 万行。装载优化完以后，写结果成了新的大头（[3.2](#opt-load)）。
- **时间字符串只格式化一次**：4801 个时间点，每只股票写出来的字符串都一样，原来每一行都格式化一次；第一轮优化改成一张表，按 bar 下标取（[3.1](#opt-init)）。

### 2.5 因子：和实盘同一份代码 {#factors}

```cpp
struct Spread {                                // 盘口价差占最新价的比例
    double v = NaN;
    void   on_tick(const Tick& t) { v = (t.ask_px[0] - t.bid_px[0]) / t.last; }
    void   on_bar(const Tick&) {}
    double value() const { return v; }
};
template <int N>
struct RollingVol {                            // 过去 N 个 bar 收益率的标准差（实习拆解页 3.1）
    std::array<double, N> buf{};
    int    n = 0, pos = 0;
    double mean = 0, s = 0, prev_mid = NaN;
    void on_tick(const Tick&) {}
    void on_bar(const Tick& t) {               // 每个 bar 收盘调一次
        double mid = (t.bid_px[0] + t.ask_px[0]) / 2;
        double x = mid / prev_mid - 1;
        prev_mid = mid;
        if (std::isnan(x)) return;
        if (n < N) {
            buf[pos] = x; ++n;
            double d = x - mean; mean += d / n; s += d * (x - mean);
        } else {
            double old = buf[pos]; buf[pos] = x;
            double nm = mean + (x - old) / N;
            s += (x - old) * (x - nm + old - mean); mean = nm;
        }
        pos = (pos + 1) % N;
    }
    double value() const {                     // 舍入会让 s 变成极小的负数，开方前截到 0
        return n < N ? NaN : std::sqrt(std::max(s, 0.0) / (N - 1));
    }
};
struct Factors {                               // 一只股票的全部因子状态，跨交易日保留
    Spread         spread;
    RollingVol<20> vol;
    void on_tick(const Tick& t) { spread.on_tick(t); vol.on_tick(t); }
    void on_bar(const Tick& t)  { spread.on_bar(t);  vol.on_bar(t); }
};
```

- **和实盘同一份代码，靠的是接口**：因子只认 `on_tick`、`on_bar`、`value`，不知道行情从哪来。实盘是行情来一条调一次，回测是上面那个循环调。
- **状态跨天保留**：`state` 在所有交易日之外建一次，第二天开盘时 20 个 bar 的窗口里还是前一天的收益率，和实盘连续跑的结果一样。
- **`std::max(s, 0.0)` 不是多余的**：行情停下以后收益率一直是 0，窗口方差应该正好是 0，舍入会让 `s` 落到 −1e−17 这样的数，直接开方得到 NaN。自测第三天只给了半天行情，就是这样测出来的；[实习拆解页 7.3](/zh/interview/cv-internship/#hw-factor-dev) 的写法也带这一句。
- **`Factors` 这里是手写的组合**：上线的因子在编译期拼好，用 CRTP 的 `FactorSet`（[实习拆解页 4.7](/zh/interview/cv-internship/#opt-crtp)）。

### 2.6 完整程序和自测 {#full}

自测造了 3 只股票、3 个交易日（第三天只有半天行情），检查 4 件事：每一行都装进去了；每只股票的数组按时间有序；第二、三天 arena 原地复用、没有换块；跨天保留的窗口是满的。

```
20260105：5201 条行情，写了 14399 行结果
20260106：5200 条行情，写了 14400 行结果
20260107：2601 条行情，写了 14403 行结果
全部测试通过！
```

<details>
<summary>展开完整代码（Linux 上 <code>g++ -std=c++17 -O2 -Wall -Wextra backtest_day.cpp -o bt && ./bt</code>）</summary>

```cpp
// 因子回测框架的骨架：按交易日回放，每天 4 步。为讲清楚重写的简化版，名字不是原工程的。
// 编译：g++ -std=c++17 -O2 -Wall -Wextra backtest_day.cpp -o bt && ./bt
#include <sys/mman.h>
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <string>
#include <type_traits>
#include <vector>

constexpr double NaN = std::numeric_limits<double>::quiet_NaN();

// ---- 一条行情：3 秒快照，这里的简化版 360 字节 ----
struct Tick {
    int64_t time;                 // 当天的毫秒数，比如 9:30:00 是 34200000
    double  pre_close, last;      // 昨收价、最新价
    int64_t volume;               // 成交总量
    double  amount;               // 成交总金额
    double  bid_px[10], ask_px[10];
    int64_t bid_vol[10], ask_vol[10];
};
static_assert(std::is_trivially_destructible_v<Tick>);   // 没有析构要跑，arena 才能整块丢

// ---- 行情文件里的一行：哪只股票 + 这条快照；文件按时间排好 ----
struct Row { int stock; Tick tick; };                    // stock 是读文件时把代码换成的编号

// ---- 一天的行情记录放进一块 arena，跨交易日复用；按字节记账，什么类型都能切 ----
class Arena {
    char*  base_ = nullptr;
    size_t cap_ = 0, used_ = 0;                          // 单位是字节
public:
    void reset(size_t need) {                            // 每个交易日开头调一次，need 是总字节数
        if (need > cap_) {                               // 不够才换块，换的时候多要一半
            if (base_) munmap(base_, cap_);
            cap_  = need + need / 2;
            base_ = static_cast<char*>(mmap(nullptr, cap_,
                        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
        }
        used_ = 0;                                       // 够用：偏移归零，原地覆盖着写
    }
    template <class T>
    T* take(size_t n) {                                  // 切 n 个 T；放不下返回空
        static_assert(std::is_trivially_destructible_v<T>);
        size_t start = (used_ + alignof(T) - 1) & ~(alignof(T) - 1);   // 偏移对齐到 alignof(T)
        if (start + n * sizeof(T) > cap_) return nullptr;
        used_ = start + n * sizeof(T);
        return reinterpret_cast<T*>(base_ + start);
    }
    const char* base() const { return base_; }
};

// ---- 每只股票一天的对象：只放代码、指针和条数 ----
struct StockDay {
    std::string code, exchange;   // 这只股票的属性，存一份，行情记录里不放
    Tick* ticks = nullptr;        // arena 里切给它的那一段
    int   tick_count = 0;
};

// ---- 因子：和实盘是同一份代码，只认 on_tick / on_bar / value，不知道行情从哪来 ----
struct Spread {                                // 盘口价差占最新价的比例
    double v = NaN;
    void   on_tick(const Tick& t) { v = (t.ask_px[0] - t.bid_px[0]) / t.last; }
    void   on_bar(const Tick&) {}
    double value() const { return v; }
};
template <int N>
struct RollingVol {                            // 过去 N 个 bar 收益率的标准差（实习拆解页 3.1）
    std::array<double, N> buf{};
    int    n = 0, pos = 0;
    double mean = 0, s = 0, prev_mid = NaN;
    void on_tick(const Tick&) {}
    void on_bar(const Tick& t) {               // 每个 bar 收盘调一次
        double mid = (t.bid_px[0] + t.ask_px[0]) / 2;
        double x = mid / prev_mid - 1;
        prev_mid = mid;
        if (std::isnan(x)) return;
        if (n < N) {
            buf[pos] = x; ++n;
            double d = x - mean; mean += d / n; s += d * (x - mean);
        } else {
            double old = buf[pos]; buf[pos] = x;
            double nm = mean + (x - old) / N;
            s += (x - old) * (x - nm + old - mean); mean = nm;
        }
        pos = (pos + 1) % N;
    }
    double value() const {                     // 舍入会让 s 变成极小的负数，开方前截到 0
        return n < N ? NaN : std::sqrt(std::max(s, 0.0) / (N - 1));
    }
};
struct Factors {                               // 一只股票的全部因子状态，跨交易日保留
    Spread         spread;
    RollingVol<20> vol;
    void on_tick(const Tick& t) { spread.on_tick(t); vol.on_tick(t); }
    void on_bar(const Tick& t)  { spread.on_bar(t);  vol.on_bar(t); }
};

// ---- bar 时间轴：3 秒一个收盘点，所有股票、所有交易日共用一份 ----
std::vector<int64_t> build_bar_timeline() {
    std::vector<int64_t> bars;
    for (int64_t t = 34200000; t <= 41400000; t += 3000) bars.push_back(t);   // 9:30:00 – 11:30:00
    for (int64_t t = 46803000; t <= 54000000; t += 3000) bars.push_back(t);   // 13:00:03 – 15:00:00
    return bars;                                                              // 2401 + 2400 = 4801 个
}
std::string format_time(int64_t ms) {
    char buf[16];
    int s = int(ms / 1000);
    std::snprintf(buf, sizeof buf, "%02d:%02d:%02d", s / 3600, s / 60 % 60, s % 60);
    return buf;
}

// ---- 第 1、2 步：读一天的行情，装进每只股票的数组 ----
void load_day(const std::vector<Row>& file, std::vector<StockDay>& stocks, Arena& arena) {
    std::vector<int> rows_today(stocks.size(), 0);
    for (const Row& r : file) ++rows_today[r.stock];          // 第一遍：每只股票今天几条
    arena.reset(file.size() * sizeof(Tick));                  // 一天一块，够用就原地覆盖
    for (size_t i = 0; i < stocks.size(); ++i) {
        stocks[i].ticks = arena.take<Tick>(rows_today[i]);    // 按实际条数切一段
        stocks[i].tick_count = 0;
    }
    for (const Row& r : file) {                               // 第二遍：按行写进去
        StockDay& s = stocks[r.stock];
        s.ticks[s.tick_count++] = r.tick;                     // 文件按时间排好，装进来已经有序
    }
}

// ---- 第 3、4 步：一只股票从头走到尾，逐条喂 on_tick；每个 bar 收盘写一行结果 ----
size_t replay_and_write(const char* date, const std::vector<StockDay>& stocks,
                        std::vector<Factors>& state, const std::vector<int64_t>& bars,
                        const std::vector<std::string>& time_str, std::FILE* out) {
    size_t rows = 0;
    for (size_t i = 0; i < stocks.size(); ++i) {
        const StockDay& s = stocks[i];
        Factors& f = state[i];
        const Tick* last = nullptr;
        int k = 0;
        for (size_t b = 0; b < bars.size(); ++b) {
            while (k < s.tick_count && s.ticks[k].time <= bars[b]) {   // 收盘点之前的都归这个 bar
                f.on_tick(s.ticks[k]);
                last = &s.ticks[k++];
            }
            if (!last) continue;                // 今天还没来过行情：这个 bar 不输出
            f.on_bar(*last);                    // 这个 bar 里没有新行情：沿用上一条
            std::fprintf(out, "%s,%s,%s,%.6g,%.6g\n", date, time_str[b].c_str(),
                         s.code.c_str(), f.spread.value(), f.vol.value());
            ++rows;
        }
    }
    return rows;
}

// ---- 自测用：造一天的行情文件 ----
std::vector<Row> make_day(int day, int n_stocks) {
    std::vector<Row> rows;
    const auto bars = build_bar_timeline();
    for (size_t b = 0; b < bars.size(); ++b)
        for (int s = 0; s < n_stocks; ++s) {
            if ((b + s + day) % (s + 2) != 0) continue;       // 每只股票活跃程度不同
            Tick t{};
            t.time = bars[b] - 1000;
            t.last = 10 + s + 0.01 * ((b * 7 + day) % 13);
            t.bid_px[0] = t.last - 0.01;
            t.ask_px[0] = t.last + 0.01 * (1 + s);
            rows.push_back({s, t});
        }
    return rows;
}

int main() {
    const int n_stocks = 3;
    std::vector<StockDay> stocks(n_stocks);
    const char* codes[] = {"600000", "000001", "300750"};
    for (int i = 0; i < n_stocks; ++i) { stocks[i].code = codes[i]; stocks[i].exchange = i ? "SZ" : "SH"; }
    std::vector<Factors> state(n_stocks);              // 因子状态跨交易日保留

    const auto bars = build_bar_timeline();            // 建一次，每天都用
    std::vector<std::string> time_str;                 // 时间字符串也只格式化一次
    for (int64_t t : bars) time_str.push_back(format_time(t));
    assert(bars.size() == 4801 && time_str.front() == "09:30:00" && time_str.back() == "15:00:00");

    Arena arena;
    std::FILE* out = std::fopen("factors.csv", "w");
    const char* dates[] = {"20260105", "20260106", "20260107"};
    const char* first_base = nullptr;
    for (int d = 0; d < 3; ++d) {                      // 按交易日一天一天跑
        auto file = make_day(d, n_stocks);             // 第 1 步：读行情文件（这里是造的）
        if (d == 2) file.resize(file.size() / 2);      // 第三天条数少一半
        load_day(file, stocks, arena);                 // 第 2 步
        if (d == 0) first_base = arena.base();
        assert(arena.base() == first_base);            // 第二、三天原地复用，没有换块

        size_t total = 0;
        for (auto& s : stocks) {
            total += s.tick_count;
            for (int k = 1; k < s.tick_count; ++k) assert(s.ticks[k - 1].time <= s.ticks[k].time);
        }
        assert(total == file.size());                  // 每一行都装进去了，没有多也没有少

        size_t rows = replay_and_write(dates[d], stocks, state, bars, time_str, out);   // 第 3、4 步
        assert(rows > 0 && rows <= bars.size() * n_stocks);
        std::printf("%s：%zu 条行情，写了 %zu 行结果\n", dates[d], file.size(), rows);
    }
    std::fclose(out);
    assert(!std::isnan(state[0].vol.value()));         // 跨天保留的窗口已经满了
    std::printf("全部测试通过！\n");
}
```

</details>

## 3. 优化 {#opt}

- **简历第 6 条分两轮**：隔了几个月，各有各的基线。第一轮去掉每天重复的初始化（约 22%），第二轮改行情的装载（约 44%）。
- **第 4 条因子计算优化改的是因子代码**：放在 3.3、3.4。
- **每个改动都先比输出、再配对计时**：流程见[实习拆解页 5 节](/zh/interview/cv-internship/#backtest-flow)。

### 3.1 第一轮：每天重复做的 3 件事，改成只做一次或不做，约 22% {#opt-init}

> **本质：结果和交易日、股票都无关的计算，每天、每只股票重算了一遍**。

- 改成在循环外算一次。

| 改之前 | 改之后 | 在第 2 节的哪里 |
|---|---|---|
| 每只股票各自生成 4801 个 bar 时间点 | 一天生成一次，每只股票拷一份 | 主循环前的 `build_bar_timeline()`（[2.1](#steps)） |
| 输出的每一行都格式化一次时间字符串 | 4801 个字符串格式化一次，存成表，按 bar 下标取 | `time_str`（[2.1](#steps)、[2.4](#replay)） |
| 每只股票装完再按时间排一次序 | 去掉；文件本来按时间排，按行写进去就有序 | `load_day` 第二遍（[2.3](#load)） |

- **输出完全不变**：一次运行约 72 秒降到约 56 秒。
- **第 2 节的简化版是第二轮以后的样子**：那里 bar 时间轴全程只有一份、所有股票共用，是第二轮 ① 的做法。

### 3.2 第二轮：行情装载，约 44% {#opt-load}

> **本质：装载碰的内存太多，时间耗在缺页和分配器上**。

- **前三处让碰的内存变少**：①②③ 少碰页、少分配。
- **后两处让内存复用**：④⑤ 一天一块 arena，跨天复用。

**怎么找到的**：

- **阶段计时只能说“装数据慢”**：说不出这一段里面是什么慢。
- **`perf record -g` 带调用栈采样**：内核的缺页处理占了一块，调用栈落在每天给每只股票新建对象的地方（[实习拆解页 6.2](/zh/interview/cv-internship/#bt-perf)）。

**改之前**：

```cpp
struct TickOld {                       // 约 850 字节，照着行情源的结构定义
    std::string code, exchange;        // 每条行情都带股票代码和交易所
    double open, high, low, upper_limit, lower_limit /*, 还有几十个 */;
    double bid_px[10], ask_px[10];
    int64_t bid_vol[10], ask_vol[10];
    // ...
};
struct StockDayOld {
    TickOld ticks[6000];      // 定长：不管今天几条，都是 6000 个槽
    Bar     bars[4801];       // 每只股票一份自己的 bar 时间轴
    int     tick_count = 0;
};
for (auto& code : codes) stocks[code] = new StockDayOld();   // 每个交易日开头 new，这一天结束 delete
```

- **每天构造约 17.5 GB**：一个 `StockDayOld` 约 7.6 MB，2300 多只，每天 `new` 一遍。
- **用到的不到一半**：平均每只一天只有 2700 多条。
- **每碰到一个新页就缺页一次**：构造时 6000 个槽都被初始化，4 KB 的页全被碰一遍（[实习拆解页 6.3](/zh/interview/cv-internship/#bt-account)）。

**5 处改动**：

| 改动 | 改之前 → 改之后 | 在第 2 节的哪里 | 砍掉的开销 | 少了多少 |
|---|---|---|---|---|
| ① 按实际条数分配，bar 时间轴共用 | 每只 6000 个槽、各一份时间轴 → 先数今天几条，按这个数要；时间轴全局一份 | `load_day` 第一遍、`arena.take<Tick>(rows_today[i])` | 缺页：没用到的槽不再被碰 | 12.3 秒 |
| ② `Tick` 瘦身 | 约 850 字节 → 约 370 字节 | `struct Tick`（[2.2](#data)） | 缺页，以及算因子时读的缓存行 | 6.3 秒 |
| ③ 字符串挪出去共享 | 每条 `Tick` 带 `code`、`exchange` → 挪进 `StockDay`，每只股票一份 | `struct StockDay` 的两个 `string` | 1300 万个小块的分配和释放 | 4.9 秒 |
| ④ arena 统一分配 | 每只股票一块 → 一天一块，按股票切 | `Arena::take` | 逐条析构、逐块释放 | 1.3 秒 |
| ⑤ arena 跨交易日复用 | 每天 `new` / `delete` → 偏移归零，原地覆盖 | `Arena::reset` | 第二天的缺页和还内存 | 1.7 秒 |

**② `Tick` 怎么瘦的**：

- **只留装载时会写、因子会读的字段**：开高低、涨跌停，和那几十个用不到的字段直接删。
- **留下的按字段算**：

| 字段 | 大小 |
|---|---|
| `time`、`pre_close`、`last`、`volume`、`amount` | 5 × 8 = 40 字节 |
| 买卖 10 档的价和量：`bid_px`、`ask_px`、`bid_vol`、`ask_vol` | 4 × 10 × 8 = 320 字节 |
| 合计 | 这一页的简化版 360 字节；原工程约 370 字节 |

- **这里主要靠删字段**：精简结构体一般有 4 种办法，删字段、换小类型、调字段顺序减少对齐填充、把每行重复的内容挪出去共享；这里用的是第 1 种，再加 ③ 把字符串挪出去。
- **装载时要写的页少了**：每条少写约 480 字节。
- **回放时要读的缓存行少了**：每条从约 14 条（850 / 64）降到约 6 条（370 / 64）。

**③ 挪出去的两个 `string`，就是 `StockDay` 里那两个**：

- **代码、交易所是股票的属性**：不是每条行情的属性，每只股票存一份就够。
- **省下分配和释放**：装载时每行少两次分配，换天时不用逐个释放 1300 万个小块。
- **`Tick` 因此不需要析构**：里面只剩标量和定长数组，成了平凡可析构的类型，④ 的 arena 才能整块丢，用 `static_assert(std::is_trivially_destructible_v<Tick>)` 钉住。

**⑤ 第一版没复用上**：

- **原因在扩容规则**：原来是“不够才换，换成刚好够的大小”，第二天行数比第一天多 2.6%，每天都整块换新的。
- **由缺页次数对不上查出来**：预期少约 57 万次缺页，实测只少 6 万次。
- **改成不够时要 1.5 倍**：之后实测少了 57 万次，和预期对上。

**第二轮的结果**：

- **整次运行约 61.7 秒降到约 34.5 秒**：约 44%，输出 md5 不变。
- **缺页从 970 多万次降到 310 多万次**。
- **省在装数据和两天交界**：写结果那一段没动，成了新的大头。

**试过没用的：预取**（[实习拆解页 6.6](/zh/interview/cv-internship/#bt-prefetch)）：

- **装载大多是写**：写先进 store buffer，不用等。
- **大头是缺页**：预取碰到没映射的页直接丢掉，布局改好以后收益是 0。

**22% 和 44% 不能连起来算**：

- **两轮的基线不同**：72 → 56 秒；61.7 → 34.5 秒。分开讲两个数，不报总数。

### 3.3 因子侧的优化：改的是第 ③ 步每条都调的 `on_tick` {#factor-opt}

- **8 类改法改的都是第 ③ 步的回调**：每条行情调一次的 `on_tick`、每个 bar 调一次的 `on_bar`，在回测里也拿这个循环量。
- **改前改后的代码在实习拆解页**：见[实习拆解页 4 节](/zh/interview/cv-internship/#factor-opt)，这里只对到这一页的代码。

> **本质：动手之前先算上限**。

- **算因子只占一次运行的一成左右**：装数据（第 ② 步，3.2 改的地方）才是大头。
- **单个改法的收益常常落在测量波动里**：一个改法就算把这一段全省掉，整次运行也快不到一成。
- **所以每个改法都单独验证**：先比输出，再配对计时（[实习拆解页 4.9](/zh/interview/cv-internship/#opt-measure)）。

| 改法 | 对到这一页的哪里 |
|---|---|
| 共用的中间量每条只算一次（[4.1](/zh/interview/cv-internship/#opt-shared)） | 这一页只有两个因子，各自读盘口；因子多了以后，中间价、价差这类每个因子都要的量，由 `Factors::on_tick` 每条算一次再传下去。同一个因子有几档参数（前 1、3、5、10 档）时，一个循环算完，路过时记下各档的值。 |
| 滚动窗口改成增量（[4.2](/zh/interview/cv-internship/#opt-rolling)） | `RollingVol::on_bar` 已经是增量写法：进一个、出一个，每次 $O(1)$，不重算整个窗口。 |
| 直接算下标，不查找（[4.3](/zh/interview/cv-internship/#opt-index)） | 这一页的回放用 `k`、`b` 两个下标同步往前走，没有查找；4.3 改的是因子内部按时间找 bar 下标的地方。 |
| 无分支（[4.4](/zh/interview/cv-internship/#opt-branchless)） | `on_tick` 里由数据决定走向的判断，比如这一档有没有挂单。 |
| 精简布局（[4.5](/zh/interview/cv-internship/#opt-layout)） | 和第二轮装载优化是同一处改动：`Tick` 从约 850 字节减到约 370 字节（[3.2 ②](#opt-load)）。装载时要写的字节少了，回放时每条要读的缓存行也少了。 |
| 拆依赖链（[4.6](/zh/interview/cv-internship/#opt-dep-chain)） | 跨档累加这类串行求和。求和顺序变了，末位会变，对拍按容差。 |
| CRTP（[4.7](/zh/interview/cv-internship/#opt-crtp)） | 这一页的 `Factors` 是手写组合；上线的因子用 `FactorSet` 在编译期拼好，`on_tick` 能一路内联。 |
| 消掉热循环里的分配和拷贝（[4.8](/zh/interview/cv-internship/#opt-alloc)） | `on_tick` 里的临时容器提到外面，`reserve` 一次，每条只 `clear`。 |

### 3.4 因子侧实际量过的三个 {#factor-measured}

| 改法 | 量出来 | 结论 |
|---|---|---|
| 几档参数共用一遍行情 | 输出一致，配对计时更快 | 收了 |
| 找 bar 改成哈希表 | 输出一致，配对计时更慢 | 拒了。行情按时间来，从上次的位置往后找，多半一两步就到；哈希多了一次哈希计算和一次不连续的访存。bar 是等距的，应该直接算下标 |
| 补空 bar 改成一遍线性 | 单看快了一点，多轮配对后差值的区间跨过 0 | 判为噪声，没有收 |

- **改哪一段就量哪一段**：程序日志里有分阶段计时，改动有没有起作用看“算因子”那一段，值不值得收再看整次运行（[实习拆解页 5.5](/zh/interview/cv-internship/#flow-phase)）。
- **被问“简历上这 8 类各快了多少”**：这 8 类是逐条调用路径上日常做的改法，在回测框架里单独量过的是上面三个；哈希那次量出来更慢，没有收，正好说明每个改法都是先量再收。

## 4. 常问的问题 {#classic}

每题先说结论，一到三句。

| 问 | 答 |
|---|---|
| 回测系统怎么搭的 | 按交易日一天一天跑，每天 4 步：读行情文件，按股票装进各自的数组，逐条喂给因子的 `on_tick`（和实盘同一份代码），每个 bar 收盘写一行结果。框架原本就有，我做了两件事：搭验证流程，再按这个流程优化装载。 |
| 是中心化的还是各自搭的 | 框架原本就有，我在它上面做验证和优化；它前面的数据怎么存、后面的结果怎么评估，不是我负责的。 |
| 650 万条是什么 | 3 秒快照，不是逐笔；2000 多只股票，每只一天最多约 4800 个快照，平均两三千条。 |
| 这么多数据放在哪：数据库，还是加载到内存 | 历史行情按交易日存成行情文件；回测时按天全部加载：每个交易日把当天所有股票的快照一次读进内存，回放完这一天再换下一天，不是把全部历史一次装进去。 |
| 一天在内存里多大 | 约 650 万条 × 370 字节，约 2.4 GB，放在一块 arena 里，按股票切成一段一段，跨交易日复用。一年两百多个交易日就是几百 GB，装不下，所以按天切。 |
| 怎么做到回测和实盘同一份代码 | 因子只认 `on_tick` / `on_bar` / `value` 这几个接口，不知道行情从哪来：实盘是行情来一条调一次，回测是循环里调。 |
| 为什么要先装进数组再回放 | 因子是每只股票自己的时间序列，状态按股票存；一只股票连着走完，状态一直在缓存里。按文件顺序喂，每条都换一只股票。 |
| arena 为什么按天，不按更短的时间 | **一天的行情一起生、一起死，并且一天能整块放进内存。** 切得更小也省不出什么：按天复用以后缺页已经没了；真要切小是内存不够的时候，比如换成逐笔数据。 |
| 跨天的状态怎么办 | 因子状态在所有交易日之外建一次，第二天接着用，滚动窗口能接上前一天。 |
| 一年的数据怎么跑快 | 按交易日分片给多个核、多台机器；每片要先把开盘前的因子状态算好（预热），这是分片唯一要接上的东西。 |
| 因子计算优化在回测里快了多少 | 算因子只占一次运行的一成左右，单个改法的收益常常落在测量波动里。单独量过三个：几档共用一遍行情，收了；找 bar 改成哈希，输出一致但更慢，拒了；补空 bar 改成一遍线性，区间跨过 0，判为噪声（[3.4](#factor-measured)）。 |
| 你在里面做了什么 | 先搭验证流程：每个改动先比输出，再配对计时（[实习拆解页 5 节](/zh/interview/cv-internship/#backtest-flow)）。再按这个流程优化：第一轮去掉每天重复的初始化，约 22%（[3.1](#opt-init)）；第二轮按实际条数分配、结构体减半、字符串共享、arena、跨天复用，约 44%（[3.2](#opt-load)）。 |

## 5. 对着代码问的细节 {#details}

| 问 | 答 |
|---|---|
| `load_day` 为什么要数两遍 | 先知道每只股票今天几条，才能从 arena 给它切连续的一段；不数就只能按上限预留。 |
| arena 为什么多要一半 | 每天条数不一样，刚好够的话第二天多一点就得整块换，复用就没发生。多要的一半只是虚拟地址，没写过的页不占物理内存。 |
| 不清零就复用，安全吗 | 安全：装载时每条的每个字段都写一遍，回放只读到 `tick_count` 为止，上一天留在后面的旧数据读不到。 |
| 为什么 `Tick` 要平凡可析构 | arena 整块丢、整块覆盖，不会挨个调析构；`Tick` 里有 `string` 就会漏。所以 `string` 挪进 `StockDay`，再用 `static_assert` 钉住。 |
| `ticks[k].time <= bars[b]` 为什么是小于等于 | 收盘点那一刻的行情归这个 bar，9:30:00 整那一条就落在第一个 bar 里。改成小于，那一条会挪到下一个 bar，结果就和研究侧对不上。 |
| 空 bar 为什么沿用上一条 | 这个 bar 没有新行情，价格还是上一条的；`on_bar` 照样调，收益率按 0 算，窗口照样往前走。 |
| `state` 为什么放在交易日循环外面 | 因子状态要跨天保留；放进循环里，每天开盘的前 20 个 bar 都是 NaN。 |
| `fprintf` 一天调 1000 万次，慢吗 | 慢，装载优化完以后它就是大头。可以把整行先拼进一块缓冲、攒够一批再写，或者直接写二进制。 |
