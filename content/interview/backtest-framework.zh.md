---
title: "IV：因子回测框架：一天怎么跑"
date: 2026-11-18T00:00:00+08:00
slug: "backtest-framework"
description: "简历实习第 5、6 条的专页，补 fir 里没答上的“回测系统怎么搭的”：按交易日一天一天跑，每天 4 步，读行情文件、按股票装进 arena 切出的数组、逐条喂给和实盘同一份的因子、每个 bar 收盘写一行结果。每段代码标出它对应第 6 条的哪一处优化，最后是一分钟讲法和常问的题。"
weight: 3
toc: true
---

这一页补 fir 里没答上的那题：**回测系统怎么搭的**。框架原本就有，我做的是简历上第 5 条的验证流程和第 6 条的两轮优化。为了讲清楚，这里把框架重写成一个能跑的简化版，名字不是原工程的；验证流程和两轮优化的细节在[实习拆解页第 5、6 节](/zh/interview/cv-internship/#backtest-flow)，这一页只讲框架本身长什么样。

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

## 2. 整体：一天 4 步 {#steps}

| 步 | 代码里是 | 做什么 | 对应的优化 |
|---|---|---|---|
| ① 读行情文件 | `read_day` | 当天的快照按时间排好，一行是“哪只股票 + 一条快照” | — |
| ② 装进每只股票的数组 | `load_day`（[4 节](#load)） | 先数每只股票今天几条，从 arena 切一段，再按行写进去 | [6.4 ①③④⑤](/zh/interview/cv-internship/#bt-five)、[6.1 ③](/zh/interview/cv-internship/#bt-init) |
| ③ 逐条回放 | `replay_and_write` 的内层循环（[5 节](#replay)） | 一只股票走到底，bar 收盘点之前的行情都喂 `on_tick` | 因子侧的改法见[实习拆解页 4 节](/zh/interview/cv-internship/#factor-opt) |
| ④ 写结果 | `replay_and_write` 里的 `fprintf` | 每个 bar 收盘写一行：日期、时间、代码、因子值 | [6.1 ②](/zh/interview/cv-internship/#bt-init) |

主循环就这几行：

```cpp
const auto bars = build_bar_timeline();          // bar 时间轴：建一次，所有股票、所有交易日共用
std::vector<std::string> time_str;               // 时间字符串：4801 个，只格式化一次
for (int64_t t : bars) time_str.push_back(format_time(t));
std::vector<Factors> state(n_stocks);            // 每只股票的因子状态，跨交易日保留
TickArena arena;                                 // 一块 arena，跨交易日复用

for (const auto& date : dates) {                 // 按交易日一天一天跑
    auto file = read_day(date);                  // ① 读行情文件
    load_day(file, stocks, arena);               // ② 装进每只股票的数组
    replay_and_write(date, stocks, state, bars, time_str, out);   // ③ 逐条回放，④ 写结果
}
```

- **为什么按交易日切**：天和天之间只有因子状态要接上（滚动窗口），行情可以一天一换。一天的数据一起来、一起走，正好放进一块 arena；要并行的话，也是按日期分片（[实习拆解页 6.4 ④](/zh/interview/cv-internship/#bt-five)、[回测平台 4 节](/zh/ref/backtest-platform/#split)）。
- **为什么先装进每只股票的数组，再回放**：因子是每只股票自己的时间序列，状态按股票存。一只股票连着从头走到尾，它的因子状态一直在缓存里；按文件顺序读一行喂一行，就是每条都换一只股票。

## 3. 数据：一条行情、一只股票、一块 arena {#data}

```cpp
// 一条行情：3 秒快照，精简后约 370 字节
struct Tick {
    int64_t time;                 // 当天的毫秒数，比如 9:30:00 是 34200000
    double  pre_close, last;
    int64_t volume;
    double  amount;
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

// 一天的行情记录放进一块 arena，跨交易日复用
class TickArena {
    Tick*  base_ = nullptr;
    size_t cap_ = 0, used_ = 0;                          // 单位是条
public:
    void reset(size_t need) {                            // 每个交易日开头调一次
        if (need > cap_) {                               // 不够才换块，换的时候多要一半
            if (base_) munmap(base_, cap_ * sizeof(Tick));
            cap_  = need + need / 2;
            base_ = static_cast<Tick*>(mmap(nullptr, cap_ * sizeof(Tick),
                        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
        }
        used_ = 0;                                       // 够用：偏移归零，原地覆盖着写
    }
    Tick* take(size_t n) { Tick* p = base_ + used_; used_ += n; return p; }
};
```

- **`Tick` 原来约 850 字节**：照着行情源的结构定义，大半字段没人读；只留被写、被读的字段，剩约 370 字节（[6.4 ②](/zh/interview/cv-internship/#bt-five)）。
- **`StockDay` 原来是定长数组**：`Tick ticks[6000]` 加一份自己的 bar 时间轴，每只股票约 7.6 MB，每天 `new` 一遍，一天约 17.5 GB（[6.3](/zh/interview/cv-internship/#bt-account)）。现在只放一个指针，指向 arena 里按实际条数切的一段。
- **代码和交易所原来在每条 `Tick` 里**：两个 `std::string`，一天 1300 万个小块；挪进 `StockDay` 以后，`Tick` 才没有要析构的成员，`static_assert` 钉住（[6.4 ③](/zh/interview/cv-internship/#bt-five)）。
- **一天多大**：650 万条 × 约 370 字节，约 2.4 GB。第一天按 1.5 倍要，之后条数不超过它就原地覆盖，不再缺页（[6.4 ⑤](/zh/interview/cv-internship/#bt-five)）。

## 4. 第 1、2 步：读文件，装进每只股票的数组 {#load}

```cpp
void load_day(const std::vector<Row>& file, std::vector<StockDay>& stocks, TickArena& arena) {
    std::vector<int> rows_today(stocks.size(), 0);
    for (const Row& r : file) ++rows_today[r.stock];          // 第一遍：每只股票今天几条
    arena.reset(file.size());                                 // 一天一块，够用就原地覆盖
    for (size_t i = 0; i < stocks.size(); ++i) {
        stocks[i].ticks = arena.take(rows_today[i]);          // 按实际条数切一段
        stocks[i].tick_count = 0;
    }
    for (const Row& r : file) {                               // 第二遍：按行写进去
        StockDay& s = stocks[r.stock];
        s.ticks[s.tick_count++] = r.tick;                     // 文件按时间排好，装进来已经有序
    }
}
```

- **为什么数两遍**：先知道每只股票今天几条，才能从 arena 里给它切连续的一段；不数就只能按上限预留，又回到 6000 条定长。
- **为什么不排序**：行情文件本来就按时间排，按行写进去，每只股票的数组自然有序。原来每只股票装完还要再排一次，第一轮优化把它去掉了（[6.1 ③](/zh/interview/cv-internship/#bt-init)）。
- **读文件这一步不是重点**：格式是厂商定的，这里把读出来的行当成一个数组 `file`。

改之前装载是这样的（[6.3](/zh/interview/cv-internship/#bt-account)）：

```cpp
struct StockDayOld {
    TickOld ticks[6000];      // 定长：不管今天几条，都是 6000 个槽，每个约 850 字节
    Bar     bars[4801];       // 每只股票一份自己的 bar 时间轴
    int     tick_count = 0;
};
for (auto& code : codes) stocks[code] = new StockDayOld();   // 每个交易日开头 new，这一天结束 delete
```

## 5. 第 3、4 步：逐条喂因子，每个 bar 写一行 {#replay}

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
- **结果写多少**：2000 多只 × 4801 个 bar，一天约 1000 万行。装载优化完以后，写结果成了新的大头（[6.5](/zh/interview/cv-internship/#bt-result)）。
- **时间字符串只格式化一次**：4801 个时间点，每只股票写出来的字符串都一样，原来每一行都格式化一次；第一轮优化改成一张表，按 bar 下标取（[6.1 ②](/zh/interview/cv-internship/#bt-init)）。

## 6. 因子：和实盘同一份代码 {#factors}

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

## 7. 完整程序和自测 {#full}

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

// ---- 一条行情：3 秒快照，精简后约 370 字节 ----
struct Tick {
    int64_t time;                 // 当天的毫秒数，比如 9:30:00 是 34200000
    double  pre_close, last;
    int64_t volume;
    double  amount;
    double  bid_px[10], ask_px[10];
    int64_t bid_vol[10], ask_vol[10];
};
static_assert(std::is_trivially_destructible_v<Tick>);   // 没有析构要跑，arena 才能整块丢

// ---- 行情文件里的一行：哪只股票 + 这条快照；文件按时间排好 ----
struct Row { int stock; Tick tick; };                    // stock 是读文件时把代码换成的编号

// ---- 一天的行情记录放进一块 arena，跨交易日复用 ----
class TickArena {
    Tick*  base_ = nullptr;
    size_t cap_ = 0, used_ = 0;                          // 单位是条
public:
    void reset(size_t need) {                            // 每个交易日开头调一次
        if (need > cap_) {                               // 不够才换块，换的时候多要一半
            if (base_) munmap(base_, cap_ * sizeof(Tick));
            cap_  = need + need / 2;
            base_ = static_cast<Tick*>(mmap(nullptr, cap_ * sizeof(Tick),
                        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
        }
        used_ = 0;                                       // 够用：偏移归零，原地覆盖着写
    }
    Tick* take(size_t n) { Tick* p = base_ + used_; used_ += n; return p; }
    const Tick* base() const { return base_; }
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
void load_day(const std::vector<Row>& file, std::vector<StockDay>& stocks, TickArena& arena) {
    std::vector<int> rows_today(stocks.size(), 0);
    for (const Row& r : file) ++rows_today[r.stock];          // 第一遍：每只股票今天几条
    arena.reset(file.size());                                 // 一天一块，够用就原地覆盖
    for (size_t i = 0; i < stocks.size(); ++i) {
        stocks[i].ticks = arena.take(rows_today[i]);          // 按实际条数切一段
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

    TickArena arena;
    std::FILE* out = std::fopen("factors.csv", "w");
    const char* dates[] = {"20260105", "20260106", "20260107"};
    const Tick* first_base = nullptr;
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

## 8. 常问的问题 {#classic}

每题先说结论，一到三句。

| 问 | 答 |
|---|---|
| 回测系统怎么搭的 | 按交易日一天一天跑，每天 4 步：读行情文件，按股票装进各自的数组，逐条喂给因子的 `on_tick`（和实盘同一份代码），每个 bar 收盘写一行结果。框架原本就有，我做了两件事：搭验证流程，再按这个流程优化装载。 |
| 是中心化的还是各自搭的 | 框架原本就有，我在它上面做验证和优化；它前面的数据怎么存、后面的结果怎么评估，不是我负责的。 |
| 650 万条是什么 | 3 秒快照，不是逐笔；2000 多只股票，每只一天最多约 4800 个快照，平均两三千条。 |
| 一天的数据放在哪 | 读进内存：一块 arena，约 2.4 GB，按股票切成一段一段；跨交易日复用这一块。 |
| 怎么做到回测和实盘同一份代码 | 因子只认 `on_tick` / `on_bar` / `value` 这几个接口，不知道行情从哪来：实盘是行情来一条调一次，回测是循环里调。 |
| 为什么要先装进数组再回放 | 因子是每只股票自己的时间序列，状态按股票存；一只股票连着走完，状态一直在缓存里。按文件顺序喂，每条都换一只股票。 |
| 跨天的状态怎么办 | 因子状态在所有交易日之外建一次，第二天接着用，滚动窗口能接上前一天。 |
| 一年的数据怎么跑快 | 按交易日分片给多个核、多台机器；每片要先把开盘前的因子状态算好（预热），这是分片唯一要接上的东西。 |
| 你在里面做了什么 | 先搭验证流程：每个改动先比输出，再配对计时（[5 节](/zh/interview/cv-internship/#backtest-flow)）。再按这个流程优化：第一轮去掉每天重复的初始化，约 22%；第二轮按实际条数分配、结构体减半、字符串共享、arena、跨天复用，约 44%（[6 节](/zh/interview/cv-internship/#backtest-opt)）。 |

## 9. 对着代码问的细节 {#details}

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
