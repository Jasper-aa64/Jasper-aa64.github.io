---
title: "IV. 因子回测框架：一天怎么跑"
date: 2026-11-18T00:00:00+08:00
slug: "backtest-framework"
description: "简历实习第 5、6 条的专页，补 fir 里没答上的“回测系统怎么搭的”：按交易日一天一天跑，每天 4 步，读行情文件、按股票装进 arena 切出的数组、逐条喂给和实盘同一份的因子、每个 bar 收盘写一行结果。分两部分：代码（第 5 条，框架一天怎么跑）和优化（第 6 条的两轮，以及第 4 条因子侧的改法），最后是常问的题。"
weight: 3
toc: true
---

这一页补 fir 里没答上的那题：**回测系统怎么搭的**。框架原本就有，我做的是简历上第 5 条的验证流程和第 6 条的两轮优化。为了讲清楚，这里把框架重写成一个能跑的简化版，名字不是原工程的；这一页分两部分：[第 2 节](#code)是代码，框架一天怎么跑；[第 3 节](#opt)是优化，每一处都对到第 2 节的代码。验证流程（比输出、配对计时）在[第 4 节](#backtest-flow)。

**回放、回算、回测，三个词**（[因子生产 2 节](/zh/ref/factor-production/#replay)）：

- **回放**：把录下来的行情按原来的顺序重喂一遍，用来对账、复现问题。
- **回算**：在历史行情上把因子值批量算出来，存成文件。
- **回测**：拿因子值模拟交易、算收益。

简历上叫“回测框架”。按这三个词分，**我负责的是回算这一段**：用历史行情把因子按实盘的方式重算一遍，每只股票每个 bar 写一行因子值。拿这些值去模拟交易、撮合、算收益是下游的事，不是我负责的。

## 1. 概览 {#pitch}

> 1. **我负责的是因子回算这一段，框架原本就有，按交易日一天一天跑，每天 4 步**：读当天的行情文件；按股票装进各自的数组；一只股票从头走到尾，逐条喂给因子的 `on_tick`，因子和实盘是同一份代码；每个 bar 收盘取一次因子值，写成结果文件。
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
    for (size_t i = 0; i < stocks.size(); ++i) {     // ① 一只股票一只股票地走
        const StockDay& s = stocks[i];                //    它今天的快照
        Factors& f = state[i];                        //    它跨交易日保留的因子状态
        const Tick* last = nullptr;                   //    最后一条喂过的快照
        int k = 0;                                    //    下一条要喂的快照
        for (size_t b = 0; b < bars.size(); ++b) {    // ② 沿 4801 个收盘点往后走
            while (k < s.tick_count && s.ticks[k].time <= bars[b]) {   // ③ 收盘点之前的快照逐条喂 on_tick
                f.on_tick(s.ticks[k]);
                last = &s.ticks[k++];
            }
            if (!last) continue;                // ④ 今天还没来过行情：这个 bar 不输出
            f.on_bar(*last);                    //    收盘：这个 bar 没有新行情就沿用上一条
            std::fprintf(out, "%s,%s,%s,%.6g,%.6g\n", date, time_str[b].c_str(),   // ⑤ 写一行
                         s.code.c_str(), f.spread.value(), f.vol.value());
            ++rows;
        }
    }
    return rows;
}
```

- **bar 怎么切**：时间不晚于收盘点的行情都归这个 bar，所以 9:30:00 整那一条归第一个 bar。这类约定和研究侧对不上，结果就对不上（[因子专页 1.1](/zh/interview/cv-factor/#factor-ontick)）。
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
struct RollingVol {                            // 过去 N 个 bar 收益率的标准差（因子专页 1.1）
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
- **`std::max(s, 0.0)` 不是多余的**：行情停下以后收益率一直是 0，窗口方差应该正好是 0，舍入会让 `s` 落到 −1e−17 这样的数，直接开方得到 NaN。自测第三天只给了半天行情，就是这样测出来的；[因子专页 4.1](/zh/interview/cv-factor/#hw-factor-dev) 的写法也带这一句。
- **`Factors` 这里是手写的组合**：上线的因子在编译期拼好，用 CRTP 的 `FactorSet`（[因子专页 2.7](/zh/interview/cv-factor/#opt-crtp)）。

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
struct RollingVol {                            // 过去 N 个 bar 收益率的标准差（因子专页 1.1）
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
    for (size_t i = 0; i < stocks.size(); ++i) {     // ① 一只股票一只股票地走
        const StockDay& s = stocks[i];                //    它今天的快照
        Factors& f = state[i];                        //    它跨交易日保留的因子状态
        const Tick* last = nullptr;                   //    最后一条喂过的快照
        int k = 0;                                    //    下一条要喂的快照
        for (size_t b = 0; b < bars.size(); ++b) {    // ② 沿 4801 个收盘点往后走
            while (k < s.tick_count && s.ticks[k].time <= bars[b]) {   // ③ 收盘点之前的快照逐条喂 on_tick
                f.on_tick(s.ticks[k]);
                last = &s.ticks[k++];
            }
            if (!last) continue;                // ④ 今天还没来过行情：这个 bar 不输出
            f.on_bar(*last);                    //    收盘：这个 bar 没有新行情就沿用上一条
            std::fprintf(out, "%s,%s,%s,%.6g,%.6g\n", date, time_str[b].c_str(),   // ⑤ 写一行
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
- **每个改动都先比输出、再配对计时**：流程见[第 4 节](#backtest-flow)。

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
- **`perf record -g` 带调用栈采样**：内核的缺页处理占了一块，调用栈落在每天给每只股票新建对象的地方。
- **测试机是虚拟机，拿不到硬件计数器**：采样用的是软件时钟事件，能看时间花在哪个函数，看不了缓存缺失；缺页次数是软件事件，`perf stat -e page-faults` 能数。

```bash
# 1. 用带符号的优化构建（-O2 -g），采样才能对回函数名
cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo .. && make

# 2. 每秒采 99 次，同时记调用栈
perf record -F 99 -g -- ./backtest --config day.yaml

# 3. 看时间花在哪些函数上、是谁调过来的
perf report --stdio
```

- **`-g` 记调用栈**：只看到“内核的缺页处理占了一块”没有用，要知道是哪段用户代码触发的。调用栈显示它们落在每天给每只股票新建对象的地方。
- **测试机是虚拟机，拿不到硬件计数器**：采样用的是软件时钟事件，能看时间花在哪个函数，看不了缓存缺失这类硬件指标。缺页次数是软件事件，`perf stat -e page-faults` 能数。


perf 的四个命令见 [perf 专题](/zh/posts/low-latency-perf-profiling/)。

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
- **每碰到一个新页就缺页一次**：构造时 6000 个槽都被初始化，4 KB 的页全被碰一遍。
- **为什么这会慢**：`new` 这么大的块，分配器直接向内核要一段地址，这时还没有物理内存；每碰到一个新的 4 KB 页就缺页一次，陷入内核、找一个物理页、清零、建映射，一次 1 µs 到几微秒，一天几百万次。这一天结束 `delete`，第二天从头再来一遍。
- **所以问题不是算得慢，是碰的内存太多**：开销有 3 种，缺页和清零、分配和释放、每条行情太大搬的字节多。下面 5 处改动各砍掉其中一种或几种。

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

**试过没用的：预取**：

- **装载大多是写**：写先进 store buffer，不用等。
- **大头是缺页**：预取碰到没映射的页直接丢掉，不会替你缺页。
- **唯一要等的读，布局改好以后也不用等了**：原来每只股票的计数器之间隔着几 MB 的定长数组，改完以后挨得很近，所以收益是 0。

**22% 和 44% 不能连起来算**：

- **两轮的基线不同**：72 → 56 秒；61.7 → 34.5 秒。分开讲两个数，不报总数。

### 3.3 因子侧的优化：改的是第 ③ 步每条都调的 `on_tick` {#factor-opt}

- **8 类改法改的都是第 ③ 步的回调**：每条行情调一次的 `on_tick`、每个 bar 调一次的 `on_bar`，在回测里也拿这个循环量。
- **改前改后的代码在因子专页**：见[因子专页第 2 节](/zh/interview/cv-factor/#factor-opt)，这里只对到这一页的代码。

> **本质：动手之前先算上限**。

- **算因子只占一次运行的一成左右**：装数据（第 ② 步，3.2 改的地方）才是大头。
- **单个改法的收益常常落在测量波动里**：一个改法就算把这一段全省掉，整次运行也快不到一成。
- **所以每个改法都单独验证**：先比输出，再配对计时（[因子专页 2.9](/zh/interview/cv-factor/#opt-measure)）。

| 改法 | 对到这一页的哪里 |
|---|---|
| 共用的中间量每条只算一次（[2.1](/zh/interview/cv-factor/#opt-shared)） | 这一页只有两个因子，各自读盘口；因子多了以后，中间价、价差这类每个因子都要的量，由 `Factors::on_tick` 每条算一次再传下去。同一个因子有几档参数（前 1、3、5、10 档）时，一个循环算完，路过时记下各档的值。 |
| 滚动窗口改成增量（[2.2](/zh/interview/cv-factor/#opt-rolling)） | `RollingVol::on_bar` 已经是增量写法：进一个、出一个，每次 $O(1)$，不重算整个窗口。 |
| 直接算下标，不查找（[2.3](/zh/interview/cv-factor/#opt-index)） | 这一页的回放用 `k`、`b` 两个下标同步往前走，没有查找；4.3 改的是因子内部按时间找 bar 下标的地方。 |
| 无分支（[2.4](/zh/interview/cv-factor/#opt-branchless)） | `on_tick` 里由数据决定走向的判断，比如这一档有没有挂单。 |
| 精简布局（[2.5](/zh/interview/cv-factor/#opt-layout)） | 和第二轮装载优化是同一处改动：`Tick` 从约 850 字节减到约 370 字节（[3.2 ②](#opt-load)）。装载时要写的字节少了，回放时每条要读的缓存行也少了。 |
| 拆依赖链（[2.6](/zh/interview/cv-factor/#opt-dep-chain)） | 跨档累加这类串行求和。求和顺序变了，末位会变，对拍按容差。 |
| CRTP（[2.7](/zh/interview/cv-factor/#opt-crtp)） | 这一页的 `Factors` 是手写组合；上线的因子用 `FactorSet` 在编译期拼好，`on_tick` 能一路内联。 |
| 消掉热循环里的分配和拷贝（[2.8](/zh/interview/cv-factor/#opt-alloc)） | `on_tick` 里的临时容器提到外面，`reserve` 一次，每条只 `clear`。 |

### 3.4 因子侧实际量过的三个 {#factor-measured}

| 改法 | 量出来 | 结论 |
|---|---|---|
| 几档参数共用一遍行情 | 输出一致，配对计时更快 | 收了 |
| 找 bar 改成哈希表 | 输出一致，配对计时更慢 | 拒了。行情按时间来，从上次的位置往后找，多半一两步就到；哈希多了一次哈希计算和一次不连续的访存。bar 是等距的，应该直接算下标 |
| 补空 bar 改成一遍线性 | 单看快了一点，多轮配对后差值的区间跨过 0 | 判为噪声，没有收 |

- **改哪一段就量哪一段**：程序日志里有分阶段计时，改动有没有起作用看“算因子”那一段，值不值得收再看整次运行（[4.4](#flow-phase)）。
- **被问“简历上这 8 类各快了多少”**：这 8 类是逐条调用路径上日常做的改法，在回测框架里单独量过的是上面三个；哈希那次量出来更慢，没有收，正好说明每个改法都是先量再收。

## 4. 验证流程：先比输出，再配对计时 {#backtest-flow}

> **验证流程的本质：先证明结果没变，再用配对计时抵消机器的漂移**。

- **简历第 5 条做的就是这个**：框架原本就有，我给它搭的是验证流程，第 3 节的优化都按这个流程收。

### 4.1 同一个程序跑几次就差好几秒：性能结论只认配对计时 {#flow-noise}

一开始在本地机器上试改法。同一个基线连跑 3 次，耗时是 103.2、103.2、107.3 秒，自己和自己就差 4 秒；几个改法的中位数从快 1.9 秒到慢 2.8 秒不等，和噪声分不开。

所以定了两条规矩：

- **本地只改代码，性能结论只认 Linux 测试机上跑出来的**。
- **每个改动过两关**：先比输出，再配对计时。

### 4.2 第一关：比输出 {#flow-output}

每次运行以后，把新版本的输出文件和原版的逐个比 md5。不一致就直接否决，不看它快了多少。

```bash
for f in out_old/*.parquet; do
    a=$(md5sum < "$f")
    b=$(md5sum < "out_new/$(basename "$f")")
    [ "$a" = "$b" ] || { echo "MISMATCH $f"; exit 1; }
done
```

**这道门自己也要验**：故意做一个错的版本（比如跳过某只股票的前 100 行），确认它会被抓到。抓不到错的门等于没有门。

### 4.3 第二关：新旧紧挨着各跑一次，顺序随机 {#flow-paired}

机器的状态一直在变：CPU 频率、温度、虚拟机上别的租户。先把旧版跑 8 次、再把新版跑 8 次，中间机器的状态变了，这个变化就全算到了新版头上。

配对的做法是每一轮让新旧版本紧挨着各跑一次，哪个先跑随机定，只看同一轮里两个的差。慢慢发生的变化对同一轮的两次影响差不多，一减就抵消了。

```python
import random, statistics, subprocess, time

def run(binary):
    t0 = time.perf_counter()
    subprocess.run([binary, "--config", "day.yaml"], check=True)
    return time.perf_counter() - t0

run(OLD); run(NEW)                       # 各预热一次，丢掉

diffs = []
for _ in range(8):
    order = [OLD, NEW]
    random.shuffle(order)                # 谁先跑随机定
    t = {b: run(b) for b in order}
    check_md5()                          # 每次运行都过第一关
    diffs.append(t[NEW] - t[OLD])        # 只看同一轮里的差

print("配对差的中位数", statistics.median(diffs))
print("新版更快的轮数", sum(d < 0 for d in diffs), "/", len(diffs))
```

- **先跑 A/A**：拿同一个程序当新旧两边跑一遍。两边一模一样，配对差的波动就是噪声的大小。它回答“多大的差才算数”。
- **看方向是否一致**：8 轮全部是新版更快，如果新旧其实没差别，出现这种结果的概率是 $2 / 2^8 \approx 0.8\%$（两边都算）。3 轮全对的概率是 25%，说明不了什么，所以轮数要够。
- **判据事先写死**：比如“配对差的中位数为负，而且区间不跨过 0”。事先写死，就不会看到结果以后再找理由收下。

### 4.4 改哪一段就量哪一段 {#flow-phase}

程序日志里有分阶段的计时：读文件、装数据、算因子、写结果。“这个改动有没有起作用”在被改的那一段看，“值不值得收”再看整次运行。只看整次运行，改动落在占比很小的那一段时，零点几秒的变化分辨不出来。

> **讲的时候按这个顺序**
>
> 1. **为什么要先搭流程**：同一个程序跑几次就差几秒，比改进还大，分不出谁快。
> 2. **两关**：先比输出，不一致直接否决；再配对计时。
> 3. **配对计时**：新旧紧挨着各跑一次、顺序随机，只看每一对的差，机器的漂移就抵消了；先跑 A/A 看噪声多大；判据事先写死。
> 4. **框架不是我写的**：我做的是验证流程，以及按这个流程做的优化。

## 5. 常问的问题 {#classic}

每题先说结论，一到三句。

| 问 | 答 |
|---|---|
| 回测系统怎么搭的 | 我负责的是因子回算这一段：把历史行情按交易日回放，用和实盘同一份因子代码，算出每只股票每个 bar 的因子值。每天 4 步：读行情文件，按股票装进各自的数组，逐条喂给 `on_tick`，每个 bar 收盘写一行结果。框架原本就有，我做了两件事：先搭验证流程，再按这个流程优化装载。撮合、收益评估在下游，不是我这段。 |
| 回测和回算有什么区别 | 回算只算因子值，看的是历史上这个因子长什么样。回测还要拿信号模拟下单、撮合，算收益和风险。我这段的产出是回测和研究的输入。 |
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
| 你在里面做了什么 | 先搭验证流程：每个改动先比输出，再配对计时（[第 4 节](#backtest-flow)）。再按这个流程优化：第一轮去掉每天重复的初始化，约 22%（[3.1](#opt-init)）；第二轮按实际条数分配、结构体减半、字符串共享、arena、跨天复用，约 44%（[3.2](#opt-load)）。 |

## 6. 对着代码问的细节 {#details}

| 问 | 答 |
|---|---|
| `load_day` 为什么要数两遍 | 先知道每只股票今天几条，才能从 arena 给它切连续的一段；不数就只能按上限预留。 |
| 扫两遍，第二遍缓存不是凉了吗 | 两遍都不热：一天约 2.4 GB，远大于 L3，哪一遍都是从内存顺序流过去，靠硬件预取。第一遍只读每行的 `stock`，一行 368 字节只碰 1 条缓存行，流量约是第二遍的几分之一。这个比例是估算，没单独量过。 |
| 能不能只扫一遍 | 能，两种：计数并进第 1 步读文件那一遍，读文件本来就要过每一行，计数不再多扫。或者每只股票在 arena 里按上限（4801 条）留虚拟地址，不碰就不占物理页，一遍直接写，代价是每只股票末尾最多浪费不到一页。 |
| arena 为什么多要一半 | 每天条数不一样，刚好够的话第二天多一点就得整块换，复用就没发生。多要的一半只是虚拟地址，没写过的页不占物理内存。 |
| 不清零就复用，安全吗 | 安全：装载时每条的每个字段都写一遍，回放只读到 `tick_count` 为止，上一天留在后面的旧数据读不到。 |
| 为什么 `Tick` 要平凡可析构 | arena 整块丢、整块覆盖，不会挨个调析构；`Tick` 里有 `string` 就会漏。所以 `string` 挪进 `StockDay`，再用 `static_assert` 钉住。 |
| `ticks[k].time <= bars[b]` 为什么是小于等于 | 收盘点那一刻的行情归这个 bar，9:30:00 整那一条就落在第一个 bar 里。改成小于，那一条会挪到下一个 bar，结果就和研究侧对不上。 |
| 空 bar 为什么沿用上一条 | 这个 bar 没有新行情，价格还是上一条的；`on_bar` 照样调，收益率按 0 算，窗口照样往前走。 |
| `state` 为什么放在交易日循环外面 | 因子状态要跨天保留；放进循环里，每天开盘的前 20 个 bar 都是 NaN。 |
| `fprintf` 一天调 1000 万次，慢吗 | 慢，装载优化完以后它就是大头。可以把整行先拼进一块缓冲、攒够一批再写，或者直接写二进制。 |
| 因子为什么不用虚函数基类 | `Factors` 里直接放具体类型，调哪个函数编译时就定了，编译器能内联。每条行情都要调，虚调用每次多一次间接跳转，还挡住内联。 |
| `RollingVol` 为什么不直接存平方和 | 平方和减均值的平方，是两个大数相减，会丢精度。这里用 Welford：窗口没满时逐个加，满了以后用新进、旧出两个值一步更新均值和 `s`。 |
| 第二天第一个 bar 的收益率是什么 | `prev_mid` 也跨天保留，所以算的是隔夜收益，比 3 秒收益大得多，会把接下来 20 个 bar 的波动率抬高。要不要算进去看研究侧的定义，不要就在每天开盘前把 `prev_mid` 设回 NaN。 |
| 下午为什么从 13:00:03 开始 | 每个 bar 管（上一个收盘点，这个收盘点]。下午第一个 bar 是 13:00:03，13:00:00 开盘那条快照归它。从 13:00:00 开始，就会多出一个只装开盘那一刻的 bar。 |
| `Spread` 为什么除以 `last` | 价差换成比例，不同价位的股票才能比。`last` 为 0（开盘前还没成交）会得到 inf，真代码要先判。 |
| `mmap` 的返回值没检查 | 简化版省掉了，真代码要判 `MAP_FAILED`。`take` 放不下会返回空，`load_day` 没判，是因为 `reset` 按总字节数要，`Tick` 360 字节、8 字节对齐，各段之间没有对齐空隙，一定放得下。 |
| arena 为什么用 `mmap`，不用 `malloc` | 一块几 GB，按页对齐，`munmap` 马上还给系统。`malloc` 这么大的块内部也走 `mmap`，直接调更清楚，还能加 `MAP_HUGETLB` 或 `madvise` 换大页。 |
| 自测第一天为什么是 14399 行，不是 3 × 4801 | 有的股票开盘头几个 bar 还没来过行情，`last` 是空，这几个 bar 不输出。第三天只有一半行情，但后面的 bar 沿用最后一条照样输出，所以是满的 14403。 |
| 能不能多线程 | 能按股票分：每只股票的 `Factors` 和那段 `ticks` 互不相干，分给几个线程各跑一批，只有输出要合并。也可以按交易日分（第 5 节）。 |
| `assert` 在 `-O2` 下还检查吗 | 检查。`-O2` 不定义 `NDEBUG`，加 `-DNDEBUG` 才会去掉。 |

## 7. 手写练习：arena {#handwrite}

这一节只练一份：第 3.2 节的 arena。先出声说 30 秒思路，再从空白写，打印“全部测试通过！”才算写对。

### 7.1 回测优化：按实际条数从 arena 切，跨交易日复用 {#hw-backtest-opt}

- **开写前说**：一天的行情同生同死，用一块 arena；每天开头 `reset(今天总条数)`，够用就偏移归零、原地覆盖，不够才换块，换的时候多要一半；每只股票 `take(实际条数)`；`Tick` 必须平凡可析构。
- **写的时候注意**：Linux 上用 `mmap`，其他平台用 `malloc` 代替；测试钉住了[3.2 节](#opt-load)“⑤ 第一版没复用上”那个坑：扩容规则是“刚好够”时，第二天多 2.6% 就要换块，复用没有发生。

<details>
<summary><strong>参考代码</strong>（138 行，先自己写，写完或卡住再展开）</summary>

```cpp
// 实习 6：回测装数据。改之前：每天每只股票 new 一个定长 6000 条的对象；改之后：按实际条数从 arena 切、跨交易日复用
// 规模缩小了（300 只股票），结构和页面一致；重点是 TickArena 和“不够时多要一半”的扩容规则
// 编译：g++ -std=c++17 -O2 -Wall -Wextra i6_backtest_opt.cpp -o bt_opt && ./bt_opt
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>
#include <type_traits>
#include <vector>
#ifdef __linux__
#include <sys/mman.h>
#endif

// ---- 改之前：照着行情源定义的大结构，每只股票一个定长对象 ----
struct TickOld {
    std::string code, exchange;            // 每条两个 string：装一行就向分配器要两次
    int64_t time; double pre_close, last, open, high, low, upper, lower;
    double others[40];                     // 装载时没人写、因子也不读的几十个字段
    double bid_px[10], ask_px[10]; int64_t bid_vol[10], ask_vol[10];
};
struct Bar { int32_t time; };
struct StockDayOld {
    TickOld ticks[6000];                   // 不管今天几条，都是 6000 个槽，构造时全碰一遍
    Bar     bars[4801];                    // 每只股票一份自己的 bar 时间轴
    int     tick_count = 0;
};

// ---- 改之后：只留被写、被读的字段；没有需要析构的成员 ----
struct Tick {
    int64_t time; double pre_close, last; int64_t volume; double amount;
    double bid_px[10], ask_px[10]; int64_t bid_vol[10], ask_vol[10];
};
static_assert(std::is_trivially_destructible_v<Tick>, "没有析构要跑，才能整块丢");

class TickArena {
    Tick*  base_ = nullptr;
    size_t cap_ = 0, used_ = 0;            // 单位是条
    double grow_;
public:
    int    remaps = 0;                     // 换了几次块（测试用）
    explicit TickArena(double grow = 1.5) : grow_(grow) {}
    ~TickArena() { release(); }
    void reset(size_t need) {              // 每个交易日开头调一次，need 是今天的总条数
        if (need > cap_) {                 // 不够才换块，换的时候多要一些
            release();
            cap_ = size_t(double(need) * grow_);
#ifdef __linux__
            void* p = mmap(nullptr, cap_ * sizeof(Tick), PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            assert(p != MAP_FAILED);
            base_ = static_cast<Tick*>(p);
#else
            base_ = static_cast<Tick*>(std::malloc(cap_ * sizeof(Tick)));
#endif
            ++remaps;
        }
        used_ = 0;                         // 够用：偏移归零，原地覆盖着写（上一天的页已经映射好，不再缺页）
    }
    Tick* take(size_t n) { assert(used_ + n <= cap_); Tick* p = base_ + used_; used_ += n; return p; }
private:
    void release() {
        if (!base_) return;
#ifdef __linux__
        munmap(base_, cap_ * sizeof(Tick));
#else
        std::free(base_);
#endif
        base_ = nullptr;
    }
};

struct StockDay {
    std::string code, exchange;            // 是股票的属性，存一份，行情记录里不放
    Tick* ticks = nullptr;
    int   tick_count = 0;
};

// 装一条：每个字段都无条件写，所以复用 arena 不用清零
void load_tick(Tick& t, int i) {
    t.time = i * 3; t.pre_close = 10; t.last = 10 + i % 7 * 0.01; t.volume = i; t.amount = i * 10.0;
    for (int k = 0; k < 10; ++k) { t.bid_px[k] = t.last - k * 0.01; t.ask_px[k] = t.last + k * 0.01; t.bid_vol[k] = t.ask_vol[k] = 100; }
}

int main() {
    std::printf("一条行情：改之前 %zu 字节，改之后 %zu 字节；一只股票的旧对象 %.1f MB\n",
                sizeof(TickOld), sizeof(Tick), sizeof(StockDayOld) / 1048576.0);

    // 两天的行数：第二天比第一天多 2.6%
    const int kStocks = 300;
    std::vector<std::vector<int>> rows(2, std::vector<int>(kStocks));
    for (int s = 0; s < kStocks; ++s) { rows[0][s] = 2000 + s * 5; rows[1][s] = int(rows[0][s] * 1.026); }

    // 改之前：每天每只 new 一个，当天结束 delete
    auto t0 = std::chrono::steady_clock::now();
    double check_old = 0;
    for (int d = 0; d < 2; ++d) {
        std::vector<std::unique_ptr<StockDayOld>> stocks;
        for (int s = 0; s < kStocks; ++s) {
            stocks.emplace_back(new StockDayOld());
            for (int i = 0; i < rows[d][s]; ++i) { stocks[s]->ticks[i].code = "600000"; stocks[s]->ticks[i].last = 10 + i % 7 * 0.01; }
            stocks[s]->tick_count = rows[d][s];
            check_old += stocks[s]->ticks[rows[d][s] - 1].last;
        }
    }
    double ms_old = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();

    // 改之后：先数出今天总条数，arena 一次 reset，每只股票顺着切一段
    auto run_new = [&](TickArena& arena, double& check) {
        std::vector<StockDay> stocks(kStocks);
        for (auto& s : stocks) { s.code = "600000"; s.exchange = "SH"; }
        for (int d = 0; d < 2; ++d) {
            size_t total = 0; for (int s = 0; s < kStocks; ++s) total += rows[d][s];
            arena.reset(total);
            for (int s = 0; s < kStocks; ++s) {
                stocks[s].ticks = arena.take(rows[d][s]);
                stocks[s].tick_count = rows[d][s];
                for (int i = 0; i < rows[d][s]; ++i) load_tick(stocks[s].ticks[i], i);
                check += stocks[s].ticks[rows[d][s] - 1].last;   // 只读到 tick_count 为止
            }
        }
    };
    t0 = std::chrono::steady_clock::now();
    TickArena arena(1.5); double check_new = 0;
    run_new(arena, check_new);
    double ms_new = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    assert(std::abs(check_old - check_new) < 1e-6);                 // 两版装出来的数据一样

    // 第一版的扩容规则“刚好够”：第二天多 2.6% 就得换块，复用没发生
    TickArena exact(1.0); double dummy = 0;
    run_new(exact, dummy);
    std::printf("改之前 %.0f ms，改之后 %.0f ms\n", ms_old, ms_new);
    std::printf("两天里换块次数：刚好够 %d 次，多要一半 %d 次\n", exact.remaps, arena.remaps);
    assert(exact.remaps == 2 && arena.remaps == 1);
    std::printf("全部测试通过！\n");
}
```

</details>
