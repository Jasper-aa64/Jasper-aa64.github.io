---
title: "IV. 因子开发和因子计算优化"
date: 2026-11-19T00:00:00+08:00
slug: "cv-factor"
aliases: ["/interview/cv-internship/"]
description: "简历实习第 3、4 条的专页。第 1 节因子开发：研究侧整列批量算的原型改成逐条增量的 on_tick，再逐值对拍、补单元测试。第 2 节因子计算优化：逐条调用的路径上常做的 8 类改法，每类改之前、改之后。第 3 节两个手写模板：OFI（一个入口）和 60 秒 VWAP（写入口、upd、读入口）。第 4 节两份带测试的完整代码。"
weight: 4
toc: true
math: true
---

这一页是简历实习第 3、4 条的专页。代码都是为了讲清楚做法重写的简化版，名字和结构不是原工程的。行情接入和行情优化（第 1、2 条）见[行情接入和 SPMC 广播环](/zh/interview/md-feed-spmc/)，回测框架和回测优化（第 5、6 条）见[因子回测框架](/zh/interview/backtest-framework/)。

## 1. 因子开发：把整列批量算的原型改成逐条增量算，再逐值对上 {#factor-dev}

> **简历原文**
>
> 将研究侧的因子落地为 C++ 生产实现，按逐 tick 增量计算（on_tick）编写；以研究原型或旧系统结果逐值对拍保证研究与生产一致，无参考结果时以单元测试覆盖边界情况；上线前完成计时、优化与回归验证

**手写练习**：这一条带测试的完整代码在 [4.1 节](#hw-factor-dev)。

### 1.1 研究侧一次拿到整列数据，生产上一次只来一条：改成 on_tick 增量 {#factor-ontick}

研究原型用 pandas，手里是一整天的数据，一行代码对整列算：

```python
ret = mid.pct_change()
factor = ret.rolling(20).std()        # 过去 20 个 bar 收益率的标准差
```

生产上行情是一条一条来的，每来一条只能更新一次状态，算出当前这一个值。同一个因子写成 `on_tick`：

```cpp
class RollingVol {
    static constexpr int N = 20;
    std::array<double, N> buf_{};       // 环形数组，存窗口里的 N 个值
    int    n_ = 0, pos_ = 0;
    double mean_ = 0, s_ = 0;           // s_ 是窗口内 (x - mean)² 的和
    double prev_mid_ = NaN;

public:
    void on_bar(double mid) {           // 每个 bar 收盘时调一次
        double x = mid / prev_mid_ - 1; // 第一个 bar 没有前值，得到 NaN
        prev_mid_ = mid;
        if (std::isnan(x)) return;

        if (n_ < N) {                   // 窗口没满：往里加
            buf_[pos_] = x; ++n_;
            double d = x - mean_;
            mean_ += d / n_;
            s_    += d * (x - mean_);
        } else {                        // 窗口满了：进一个，出一个
            double old = buf_[pos_];
            buf_[pos_] = x;
            double new_mean = mean_ + (x - old) / N;
            s_   += (x - old) * (x - new_mean + old - mean_);
            mean_ = new_mean;
        }
        pos_ = (pos_ + 1) % N;
    }
    double value() const {              // 窗口没满输出 NaN；除以 N - 1
        return n_ < N ? NaN : std::sqrt(s_ / (N - 1));
    }
};
```

**pandas 一行里藏着的约定，C++ 里每一条都要写明**：

- **窗口没满时输出什么**：`rolling(20)` 前 19 个是 NaN，C++ 要一样。
- **除以 N 还是 N − 1**：pandas 的 `std` 默认 `ddof=1`，除以 N − 1；numpy 默认除以 N。
- **NaN 怎么处理**：跳过，还是让它进窗口。
- **bar 怎么切**：9:30:00 整那一条归哪个 bar，午休前后怎么接，一个 bar 里有几条行情取哪一条，整段没有行情的空 bar 怎么补。

这些有歧义的地方先找研究员问清，再写。

### 1.2 两边是两套算法，必须证明结果一样：逐值对拍 {#factor-diff}

研究原型整段批量算，C++ 每来一条更新一次，算法本身就不同。所以要拿同一天的数据两边各跑一遍，逐个值比。

```python
# 按 key 对齐，不按行的顺序比
key = ["date", "time", "code", "factor_id"]
m = ref.merge(out, on=key, how="outer", suffixes=("_ref", "_out"), indicator=True)

extra = m[m["_merge"] != "both"]                       # 1. 多出来或少掉的行
d = (m["value_out"] - m["value_ref"]).abs()
bad = m[d > 1e-9 + 1e-6 * m["value_ref"].abs()]        # 2. 值超过容差的行
```

- **按 key 比，不按行序**：两边输出的顺序可以不同，key 是日期、时间、股票、因子编号。
- **“对上”的标准是容差**：绝对误差和相对误差各设一个门槛。增量算法的运算顺序和批量的不同，编译器还可能把乘加合成一条 FMA 指令，浮点结果的末几位会不一样，要求逐位一致做不到。
- **迁移旧系统的因子时可以要求更严**：算法没换、运算顺序也照搬时，可以要求输出文件逐字节一致。

**对不上时，先看差的形状，它指向原因在哪一层**：

| 差的形状 | 原因多半在哪 |
|---|---|
| 整行多了或少了 | 数据过滤或展开，比如某只股票该不该出现 |
| 个别值差在末几位 | 运算顺序或 FMA，按容差就过 |
| 集中在某个时间段 | 时间边界：9:30:00 整、午休前后、一个 bar 里有几条 |
| 集中在某几只股票 | 数据本身：某档价格是 0，涨跌停时一边的盘口是空的 |

**一个例子**：迁移旧系统的 4 个因子，第一次对拍多出近 10000 行。按股票一分，全来自 2 只股票：它们那天只有价、量、额全是 0 的占位行情，被展开成了全天的 bar。读数据时去掉这种股票以后，全部一致。

### 1.3 没有参考结果：手算小例子，用单元测试覆盖边界 {#factor-unit}

新因子没有旧系统的结果可比时，自己构造几条行情、手算出答案，写成单元测试。重点放在边界上：

- 9:30:00 整的那一条；
- 午休前最后一条和午休后第一条；
- 一个 bar 里有好几条行情；
- 整段没有行情的空 bar；
- 某一档的价格是 0；
- 一天的条数超过上限。

### 1.4 上线前：计时、优化、回归 {#factor-release}

- **计时**：用整天的回放，测每条行情的平均耗时和尾部耗时，看有没有超出预算。
- **优化**：超了就按[第 2 节](#factor-opt)的办法改。
- **回归**：固定几个交易日，新版本的输出和上一版逐值一致。有变化，必须能说出是哪个改动造成的、为什么该变。

> **讲的时候按这个顺序**
>
> 1. **改成逐条增量**：研究侧整列 `rolling`，生产上每来一条只更新一次状态。
> 2. **把隐含的约定写明**：窗口没满出什么、除以 N 还是 N − 1、NaN 怎么办、bar 怎么切，不清楚的找研究员确认。
> 3. **逐值对拍**：按 key 对齐，按容差比；举“多出近 10000 行，来自 2 只全是 0 的占位股票”的例子。
> 4. **没有参考时**：手算小例子，单元测试覆盖边界。
> 5. **因子用的是快照**：十档盘口，3 秒一条。

## 2. 因子计算优化：逐条调用的路径上常做的 8 类改法 {#factor-opt}

> **简历原文**
>
> 针对逐 tick 调用的 CPU 密集计算路径做日常调优：多个因子共用的中间量每条行情只算一次；滚动窗口统计由每次重算改为增量更新；用下标计算或哈希替代线性查找；将依赖数据的分支改为无分支写法；精简行情数据布局；拆分串行累加的依赖链；用 CRTP 替代虚函数调用，消除间接跳转并让编译器能够内联；消除热循环里的内存分配与拷贝

**手写练习**：这一条带测试的完整代码在 [4.2 节](#hw-factor-opt)。

`on_tick` 每条行情调一次，一天几百万次。下面每一类先写改之前，再写改之后。

### 2.1 每个因子各算一遍相同的中间量：每条行情只算一次 {#opt-shared}

```cpp
// 改之前：每个因子自己算 bar 下标、中间价
void FactorA::on_tick(const Tick& t) { int bar = bar_index(t.time); double mid = (t.bid_px[0] + t.ask_px[0]) / 2; /*...*/ }
void FactorB::on_tick(const Tick& t) { int bar = bar_index(t.time); double mid = (t.bid_px[0] + t.ask_px[0]) / 2; /*...*/ }

// 改之后：框架每条行情算一次，传给所有因子
struct TickCtx { int bar; double mid; double spread; };

void Engine::on_tick(const Tick& t) {
    TickCtx c{ bar_index(t.time),
               (t.bid_px[0] + t.ask_px[0]) / 2,
               t.ask_px[0] - t.bid_px[0] };
    for (auto& f : factors_) f.on_tick(t, c);
}
```

同一个因子有几档参数时也是这个思路。比如要前 1、3、5、10 档的买量之和，不用 4 个循环各加一遍，一个循环加到第 10 档，路过第 1、3、5 档时把当时的和记下来：

```cpp
double acc = 0;
for (int lv = 0; lv < 10; ++lv) {
    acc += t.bid_vol[lv];
    if (lv == 0) out[0] = acc;
    if (lv == 2) out[1] = acc;
    if (lv == 4) out[2] = acc;
}
out[3] = acc;
```

### 2.2 滚动窗口每次从头算：进一个、出一个 {#opt-rolling}

过去 N 个 bar 的和、均值、方差，每次从头算是 $O(N)$，增量更新是 $O(1)$。

```cpp
// 改之前：每个 bar 把窗口里的 N 个值重新加一遍
double sum = 0;
for (int i = 0; i < N; ++i) sum += window[i];

// 改之后：进一个加，出一个减
sum += x_new - x_old;
```

- **和、均值**：进一个加，出一个减。
- **方差**：用 3.1 里那种更新均值和离差平方和的写法（Welford），比“平方和减去和的平方”稳，后者两个大数相减会丢精度。
- **最大值、最小值**：用单调队列，队列里只留“还有可能成为最大值”的元素，摊下来每次 $O(1)$。
- **代价**：浮点误差会随着加减累积。对拍按容差比，必要时每隔一段整窗重算一次。

### 2.3 每条行情线性找自己属于哪个 bar：直接算下标 {#opt-index}

bar 是 3 秒等距的，一条行情属于第几个 bar 可以直接算出来，不用找：

```cpp
// 改之前：在 bar 的时间数组里一个个比
int bar_index(int64_t t) {
    for (int i = 0; i < n_bars; ++i)
        if (bar_time[i] >= t) return i;
    return n_bars;
}

// 改之后：按距开盘的秒数除以 3，午休单独处理
int bar_index(int sec_of_day) {
    constexpr int kOpen = 9 * 3600 + 30 * 60;      // 09:30:00
    constexpr int kNoon = 11 * 3600 + 30 * 60;     // 11:30:00
    constexpr int kPm   = 13 * 3600;               // 13:00:00
    if (sec_of_day <= kNoon) return (sec_of_day - kOpen) / 3;
    return 2400 + (sec_of_day - kPm) / 3;          // 上午 2 小时是 2400 个 bar
}
```

午休前后两个端点归哪个 bar，要和研究侧的切法一致，这正是 3.1 里要问清的约定。

**哈希不一定比线性查找快**：这里试过把查找换成哈希表，输出一致，量出来反而慢了。原因是行情按时间来，从上次的位置往后找，多半一两步就到；哈希多了一次哈希计算和一次不连续的访存。所以这个改法没有收，等距的数据直接算下标才是对的方向。

### 2.4 走向由数据决定的分支：改成无分支 {#opt-branchless}

分支预测器靠历史规律猜。“这一档有没有挂单”“这笔是买还是卖”这类判断由数据决定，没有规律，猜错一次要十几个周期。

```cpp
// 改之前：这一档有没有价，看数据
if (t.bid_px[i] > 0) px = t.bid_px[i];
else                 px = last_px;

// 改之后：写成条件表达式，编译器通常编成条件传送（cmov），没有跳转
double px = t.bid_px[i] > 0 ? t.bid_px[i] : last_px;

// 能用算术消掉的直接消掉：没有挂单时量是 0，乘出来也是 0
sum += t.bid_px[i] * t.bid_vol[i];
```

另一类是由参数决定、整个循环里都不变的分支，把它提到循环外面，循环体里就没有判断了。

**无分支不总是更快**：条件传送要把两边的值都算出来，分支本来就好猜时，原来的写法更快。改之前先看这个分支是不是真的猜不准（[分支预测](/zh/posts/branch-prediction-branch-optimization/)）。

### 2.5 一条行情很大，因子只读其中几十字节：精简布局 {#opt-layout}

一条行情记录近 1 KB，因子每条只读其中一小部分。逐条扫的时候，CPU 搬进缓存的大部分字节是用不到的字段。把不用的字段删掉、常读的字段放在一起，每条行情要读的缓存行就从十几条降到几条。具体做法在 6.4。

### 2.6 一个累加器串着加，每次都等上一次：拆成几个累加器 {#opt-dep-chain}

```cpp
// 改之前：每次加法都要等上一次的结果，一次浮点加 4 个周期左右
double s = 0;
for (int i = 0; i < n; ++i) s += x[i];

// 改之后：4 个累加器互不依赖，CPU 可以同时算
double s0 = 0, s1 = 0, s2 = 0, s3 = 0;
int i = 0;
for (; i + 4 <= n; i += 4) {
    s0 += x[i];     s1 += x[i + 1];
    s2 += x[i + 2]; s3 += x[i + 3];
}
double s = (s0 + s1) + (s2 + s3);
for (; i < n; ++i) s += x[i];
```

- **为什么编译器不自己做**：浮点加法不满足结合律，换了求和顺序结果的末位会变。不开 `-ffast-math`，编译器不能擅自改顺序。
- **代价**：末位会变，对拍要按容差比。动这类计算之前，先定好对比的标准。

依赖链的原理见 [#2 内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/)和[循环优化与指令级并行](/zh/posts/loop-optimization/)。

### 2.7 每条行情一次虚调用，编译器没法内联：CRTP {#opt-crtp}

```cpp
// 改之前：通过基类指针调，运行时才知道调的是谁
struct IFactor {
    virtual void on_tick(const Tick& t) = 0;
    virtual ~IFactor() = default;
};
for (IFactor* f : factors) f->on_tick(t);        // 读 vptr，读虚表，间接跳转

// 改之后：派生类把自己当模板参数传给基类，编译期就知道调的是谁
template <class D>
struct FactorBase {
    void on_tick(const Tick& t) { static_cast<D*>(this)->on_tick_impl(t); }
};
struct Spread : FactorBase<Spread> {
    void on_tick_impl(const Tick& t) { /*...*/ }
};

// 一组因子在编译期拼好
template <class... Fs>
struct FactorSet {
    std::tuple<Fs...> fs;
    void on_tick(const Tick& t) {
        std::apply([&](auto&... f) { (f.on_tick(t), ...); }, fs);
    }
};
```

- **省的主要不是那次间接跳转**：虚调用预测对的时候只有几个周期。代价大的是编译器不知道调的是谁，没法内联，也就没法把几个因子对同一个字段的读取合并、没法向量化。
- **代价**：类型在编译期定死，不能按配置在运行时换；`FactorBase<A>` 和 `FactorBase<B>` 是两个不相关的类型，放不进同一个容器；每种类型实例化一份代码。
- **什么时候换成 CRTP，看两条**：类型是不是部署时就定了；调用是不是每条行情都要过。两条都满足才换。研究阶段读了配置才知道要算哪些因子，就用虚函数，把虚调用提到循环外面。

细节见 [CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/)。

### 2.8 热循环里的分配和拷贝：提到外面，复用 {#opt-alloc}

```cpp
// 改之前：每条行情构造、析构一个临时容器，每次都走分配器
for (const Tick& t : ticks) {
    std::vector<double> tmp;
    fill(tmp, t);
    use(tmp);
}

// 改之后：容器提到循环外，先留够容量，每次只清空
std::vector<double> tmp;
tmp.reserve(64);
for (const Tick& t : ticks) {
    tmp.clear();                 // 只把长度归零，不释放内存
    fill(tmp, t);
    use(tmp);
}
```

同一类的还有：按值传的大对象改成按引用传；每行都重新拼的字符串改成提前算好一次。

### 2.9 每个改法先量再收 {#opt-measure}

- **先算上限**：这一段占整次运行的多少，全省掉最多快多少。在回测框架里，算因子只占一次运行的一小部分，装数据才是大头（[回测框架专页 3.2](/zh/interview/backtest-framework/#opt-load)），所以计算一侧单个改法的收益常常落在测量波动里。
- **先比输出，再配对计时**：流程见[回测框架专页第 4 节](/zh/interview/backtest-framework/#backtest-flow)。
- **量过以后没有收的也有**：4.3 的哈希，输出一致但更慢，拒了；有一个把补空 bar 改成一遍线性的改法，单看快了一点，多轮配对后差值的区间跨过 0，判成噪声，没有收。

> **讲的时候按这个顺序**
>
> 1. **先说这是逐条调用路径上日常做的几类**，再挑两三个展开，不要 8 个都讲。
> 2. **首选滚动窗口**：每次重算 $O(N)$ 改成进一个、出一个 $O(1)$，能手写。
> 3. **再讲 CRTP**：省的主要是内联，不是那次跳转；类型部署时就定、每条都调，才换。
> 4. **主动说代价**：改运算顺序末位会变，对拍按容差；每个改法先量再收，哈希那次量出来更慢就没收。

## 3. 两个因子模板：一个入口，还是两个入口 {#templates}

手写因子题按这两种写法来。两个例子不是实习上线的因子，是从[因子计算速查](/zh/ref/factor-computation/)里挑的：一个每张快照出值，一个按时刻采样。

### 3.1 OFI：每张快照出一个值，一个入口 {#tpl-ofi}

> **OFI 的本质：相邻两张快照比买一、卖一，算出这一张的委托流不平衡 e，再对最近 N 个 e 求和**。

- **买方**：买一价上移、不变、下移，分别取整档新增、量差、整档减少。
- **卖方方向相反**：卖一价下移是抢着卖，取整档新增；e = eb − ea。
- **窗口和用环形数组维护**：进一个加、出一个减，每次 O(1)。
- **只有一个入口**：每张快照都要一个值，写入口直接返回因子值，不另写读入口。

原文和推导见[因子计算速查 1.2](/zh/ref/factor-computation/#ofi)。

```cpp
// Snapshot 里 bid_px[0]、bid_qty[0] 是买一价、买一量，ask 同理；价格是放大过的整数
struct Ofi {
  static constexpr int N = 64;  // 窗口张数，取 2 的幂
  int64_t ring[N] = {};         // 最近 N 个 e
  int64_t sum = 0;              // ring 里 N 个 e 的和
  int64_t count = 0;            // 一共算出过几个 e
  bool has_prev = false;
  // 上一张的买一价、买一量、卖一价、卖一量
  int64_t pb = 0, qb = 0, pa = 0, qa = 0;
  // 窗口还没攒满 N 个 e 时返回空，对应 pandas rolling(N) 开头的 NaN
  std::optional<int64_t> on_snapshot(const Snapshot& s) {
    int64_t b = s.bid_px[0], vb = s.bid_qty[0];
    int64_t a = s.ask_px[0], va = s.ask_qty[0];
    // 1. 第一张没有上一张，只存下来，不能拿 0 当上一张
    if (!has_prev) {
      has_prev = true;
      pb = b; qb = vb; pa = a; qa = va;
      return std::nullopt;
    }
    // 2. 买方：价上移整档算新增，价不变看量差，价下移整档算减少
    int64_t eb = b > pb ? vb : (b == pb ? vb - qb : -qb);
    // 3. 卖方镜像：价下移整档算新增卖压
    int64_t ea = a < pa ? va : (a == pa ? va - qa : -qa);
    int64_t e = eb - ea;
    // 4. 进一个加、出一个减；没满时被覆盖的格子是 0，减了也不影响
    //    下标用按位与回绕，所以 N 要是 2 的幂
    int64_t& slot = ring[count & (N - 1)];
    sum += e - slot;
    slot = e;
    ++count;
    // 5. 存下这一张，下一张和它比
    pb = b; qb = vb; pa = a; qa = va;
    if (count < N) return std::nullopt;
    return sum;
  }
};
```

```cpp
// 用法：每只股票一个 Ofi，每来一张快照喂一次；窗口没满返回 nullopt
std::vector<Ofi> ofi(n_stocks);
void on_snapshot(int stock, const Snapshot& s) {
  if (auto v = ofi[stock].on_snapshot(s)) signal(stock, *v);
}
```

**为什么返回 `optional`：整数因子需要一个“没有值”的表示**。

- **0 是合法的值**：买卖压力抵消时和就是 0，整数又没有 NaN。
- **窗口没满返回 `nullopt`**：对应 pandas `rolling(N)` 开头的 NaN；浮点因子可以直接返回 NaN。
- **不用哨兵值 `INT64_MIN`**：调用方忘了判断，它会被当成真的值；`optional` 把“可能没有值”写进了返回类型。

### 3.2 60 秒 VWAP：按时刻采样，写入口、`upd`、读入口 {#tpl-vwap}

> **按时刻采样的本质：写入和读取拆成两个入口，读之前先把状态推进到时刻 T**。

- **成交来了只改状态**：`on_trade` 入队，两个和各加一次。
- **要值时先 `upd(T)`**：剔掉过期的成交。换成别的窗口因子，只改 `upd` 的内容。
- **为什么必须拆开**：一段时间没有成交时，过期的数据只能在读的时候靠 `upd` 剔掉。
- **窗口空时返回 `nullopt`**：VWAP 是 0/0，返回 0 会被当成价格 0；要和 pandas 对拍时可以改成返回 NaN。

原文见[因子计算速查 3.4](/zh/ref/factor-computation/#vwap)。

```cpp
struct Trade { int64_t t, px, qty; };  // t 毫秒；px 放大过的整数
struct Window60s {
  static constexpr int64_t W = 60'000;
  std::deque<Trade> q;            // 窗口里的成交，队头最旧
  int64_t sum_pq = 0, sum_q = 0;  // 整数累加，加进去再减出来一位不差
  // 1. 写入口：入队，两个和各加一次
  void on_trade(const Trade& x) {
    q.push_back(x);
    sum_pq += x.px * x.qty;
    sum_q += x.qty;
  }
  // 2. upd：把状态推进到时刻 T。这里是剔除过期的：窗口左开右闭，
  // 正好 60 秒前的那一笔也要出去，所以是 <=
  void upd(int64_t T) {
    while (!q.empty() && q.front().t <= T - W) {
      sum_pq -= q.front().px * q.front().qty;
      sum_q -= q.front().qty;
      q.pop_front();
    }
  }
  // 3. 读入口：先 upd，再判空，再算
  std::optional<double> vwap(int64_t T) {
    upd(T);
    if (q.empty()) return std::nullopt;
    return double(sum_pq) / double(sum_q);
  }
  std::optional<double> avg_qty(int64_t T) {
    upd(T);
    if (q.empty()) return std::nullopt;
    return double(sum_q) / double(q.size());
  }
};
```

```cpp
// 用法：成交来了只调 on_trade；到采样时刻 T 调 vwap(T)，它自己先 upd(T) 再算
Window60s w;  // 每只股票一个
void on_trade(const Trade& x) { w.on_trade(x); }
void on_timer(int64_t T) {  // 比如每 3 秒一次
  auto v = w.vwap(T);
  out(T, v ? *v : NaN);  // 窗口里没有成交，写 NaN
}
```

## 4. 手写练习：两份能跑的完整代码 {#handwrite}

> **怎么练**
>
> 1. **先说**：不展开代码，按“开写前说”出声说一遍设计，30 秒以内。
> 2. **再写**：从空白写，编译、运行，打印“全部测试通过！”才算写对；对不上再展开参考代码。
> 3. **第二天重写**：能边写边说出每一行为什么这样写，比写得快更重要。
>
> 参考代码只用标准库，g++ 15 加 `-Wall -Wextra` 零警告，编译命令在每份代码的开头。进度记在[本周计划第 3 节](/zh/interview/plan/#handwrite)。

### 4.1 因子开发：增量滚动标准差、按 key 对拍、边界单元测试 {#hw-factor-dev}

- **开写前说**：窗口没满时 Welford 加一个，满了进一个、出一个；参考答案是整窗重算；对拍按 key 对齐、按绝对加相对容差比；对拍的门自己也要用故意做错的数据验一遍。
- **写的时候注意**：除以 N − 1；窗口没满输出 NaN；第一个 bar 没有收益率；价格不变时离差平方和可能因为舍入变成极小的负数，开根号前取 `max(0, ·)`，[第 1.1 节](#factor-ontick)的片段没写这一句。

<details>
<summary><strong>参考代码</strong>（128 行，先自己写，写完或卡住再展开）</summary>

```cpp
// 实习 3：因子开发。研究侧 rolling(20).std() 改成 on_bar 增量；按 key 对齐、按容差逐值对拍；单元测试覆盖边界
// 编译：g++ -std=c++17 -O2 -Wall -Wextra i3_factor_dev.cpp -o factor_dev && ./factor_dev
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <limits>
#include <map>
#include <random>
#include <string>
#include <tuple>
#include <vector>

constexpr double NaN = std::numeric_limits<double>::quiet_NaN();

// ---- 生产版：每个 bar 收盘调一次，O(1) 更新 ----
// 对应 pandas：ret = mid.pct_change(); factor = ret.rolling(N).std()   （ddof = 1，窗口没满是 NaN）
template <int N>
class RollingVol {
    std::array<double, N> buf_{};
    int    n_ = 0, pos_ = 0;
    double mean_ = 0, s_ = 0;          // s_ = 窗口内 Σ(x − mean)²
    double prev_mid_ = NaN;
public:
    void on_bar(double mid) {
        double x = mid / prev_mid_ - 1;    // 第一个 bar 没有前值，得到 NaN
        prev_mid_ = mid;
        if (std::isnan(x)) return;
        if (n_ < N) {                      // 窗口没满：Welford 加一个
            buf_[pos_] = x; ++n_;
            double d = x - mean_;
            mean_ += d / n_;
            s_    += d * (x - mean_);
        } else {                           // 窗口满了：进一个、出一个
            double old = buf_[pos_];
            buf_[pos_] = x;
            double new_mean = mean_ + (x - old) / N;
            s_   += (x - old) * (x - new_mean + old - mean_);
            mean_ = new_mean;
        }
        pos_ = (pos_ + 1) % N;
    }
    double value() const { return n_ < N ? NaN : std::sqrt(std::max(0.0, s_) / (N - 1)); }
};

// ---- 研究版（参考答案）：拿到整列，每个位置把窗口从头算一遍 ----
std::vector<double> rolling_std_ref(const std::vector<double>& mid, int N) {
    std::vector<double> ret(mid.size(), NaN), out(mid.size(), NaN);
    for (size_t i = 1; i < mid.size(); ++i) ret[i] = mid[i] / mid[i - 1] - 1;
    for (size_t i = N; i < mid.size(); ++i) {          // ret[0] 是 NaN，所以第一个满窗在 i = N
        double m = 0, s = 0;
        for (size_t j = i + 1 - N; j <= i; ++j) m += ret[j];
        m /= N;
        for (size_t j = i + 1 - N; j <= i; ++j) s += (ret[j] - m) * (ret[j] - m);
        out[i] = std::sqrt(s / (N - 1));
    }
    return out;
}

// ---- 3 秒 bar 的下标：按距开盘的秒数除以 3，午休单独处理（端点归属要和研究侧一致）----
int bar_index(int sec_of_day) {
    constexpr int kOpen = 9 * 3600 + 30 * 60, kNoon = 11 * 3600 + 30 * 60, kPm = 13 * 3600;
    if (sec_of_day <= kNoon) return (sec_of_day - kOpen) / 3;
    return 2400 + (sec_of_day - kPm) / 3;               // 上午 2 小时 = 2400 个 bar
}

// ---- 对拍：按 key 对齐，不按行序；容差 = 绝对 + 相对 ----
using Key = std::tuple<int, std::string>;               // (bar, code)
struct DiffReport { int missing = 0, extra = 0, bad = 0; };
DiffReport compare(const std::map<Key, double>& ref, const std::map<Key, double>& out,
                   double atol = 1e-12, double rtol = 1e-9) {
    DiffReport r;
    for (auto& [k, v] : ref) {
        auto it = out.find(k);
        if (it == out.end()) { ++r.missing; continue; }
        bool both_nan = std::isnan(v) && std::isnan(it->second);
        if (!both_nan && !(std::fabs(it->second - v) <= atol + rtol * std::fabs(v))) ++r.bad;
    }
    for (auto& [k, v] : out) if (!ref.count(k)) ++r.extra;
    return r;
}

int main() {
    // 1. 对拍：同一天的数据两边各算一遍
    std::mt19937 rng(42);
    std::normal_distribution<double> step(0, 0.002);
    std::vector<double> mid{10.0};
    for (int i = 1; i < 4800; ++i) mid.push_back(mid.back() * (1 + step(rng)));

    auto ref_vals = rolling_std_ref(mid, 20);
    RollingVol<20> f;
    std::map<Key, double> ref, out;
    for (size_t i = 0; i < mid.size(); ++i) {
        f.on_bar(mid[i]);
        out[{int(i), "600000"}] = f.value();
        ref[{int(i), "600000"}] = ref_vals[i];
    }
    auto r = compare(ref, out);
    std::printf("对拍：缺 %d 行，多 %d 行，超容差 %d 个\n", r.missing, r.extra, r.bad);
    assert(r.missing == 0 && r.extra == 0 && r.bad == 0);

    // 对拍的门自己也要验：故意做错一个，必须被抓到
    out[{100, "600000"}] += 1e-6;
    out[{9999, "000001"}] = 0;
    r = compare(ref, out);
    assert(r.bad == 1 && r.extra == 1);

    // 2. 单元测试：手算的小例子和边界
    RollingVol<3> g;
    g.on_bar(100); assert(std::isnan(g.value()));          // 第一个 bar 没有收益率
    g.on_bar(101); g.on_bar(102); assert(std::isnan(g.value()));   // 只有 2 个收益率，窗口没满
    g.on_bar(103);                                          // 收益率 1%、0.990…%、0.980…%
    double r1 = 0.01, r2 = 102.0 / 101 - 1, r3 = 103.0 / 102 - 1, m = (r1 + r2 + r3) / 3;
    double expect = std::sqrt(((r1 - m) * (r1 - m) + (r2 - m) * (r2 - m) + (r3 - m) * (r3 - m)) / 2);
    assert(std::fabs(g.value() - expect) < 1e-15);
    RollingVol<3> flat;                                     // 价格不变：方差是 0，不能因为舍入变成负数开根号
    for (int i = 0; i < 10; ++i) flat.on_bar(10.0);
    assert(flat.value() == 0.0);

    assert(bar_index(9 * 3600 + 30 * 60) == 0);             // 09:30:00 整
    assert(bar_index(9 * 3600 + 30 * 60 + 2) == 0);         // 09:30:02 还在第 0 个
    assert(bar_index(9 * 3600 + 30 * 60 + 3) == 1);
    assert(bar_index(11 * 3600 + 30 * 60) == 2400);         // 11:30:00 整：这里归到上午的末尾
    assert(bar_index(13 * 3600) == 2400);                   // 13:00:00 接着往下数
    assert(bar_index(15 * 3600) == 4800);
    std::printf("全部测试通过！\n");
}
```

</details>

### 4.2 因子计算优化：每一类“改之前 / 改之后”，输出一致才算 {#hw-factor-opt}

- **开写前说**：每一类改法两版都写，跑同一份数据，输出一致才算数；改了求和顺序的按容差比。
- **写的时候注意**：重点手写两个。一个是单调队列求滚动最大值：队列里只留还可能成为最大值的，值单调递减。另一个是 CRTP 的 `FactorSet`：折叠表达式依次调每个因子。其余几类看一遍，能说出改之前慢在哪就够。

<details>
<summary><strong>参考代码</strong>（141 行，先自己写，写完或卡住再展开）</summary>

```cpp
// 实习 4：因子计算优化。每一类都写“改之前 / 改之后”，并检查两版输出一致（改了运算顺序的按容差）
// 编译：g++ -std=c++17 -O2 -Wall -Wextra i4_factor_opt.cpp -o factor_opt && ./factor_opt
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <deque>
#include <memory>
#include <random>
#include <tuple>
#include <vector>

struct Tick { int sec; double bid_px[10], ask_px[10]; double bid_vol[10]; double last; };

// ---- 4.1 同一个量的几档参数：一次循环，路过时记下 ----
void depth_before(const Tick& t, double out[4]) {
    const int lv[4] = {1, 3, 5, 10};
    for (int k = 0; k < 4; ++k) { out[k] = 0; for (int i = 0; i < lv[k]; ++i) out[k] += t.bid_vol[i]; }
}
void depth_after(const Tick& t, double out[4]) {
    double acc = 0;
    for (int i = 0; i < 10; ++i) {
        acc += t.bid_vol[i];
        if (i == 0) out[0] = acc;
        if (i == 2) out[1] = acc;
        if (i == 4) out[2] = acc;
    }
    out[3] = acc;
}

// ---- 4.2 滚动窗口：和用“进一个加、出一个减”；最大值用单调队列 ----
class RollingMax {                       // 队列里只留“还可能成为最大值”的下标，值单调递减
    std::deque<std::pair<long, double>> q_;
    long i_ = 0; int n_;
public:
    explicit RollingMax(int n) : n_(n) {}
    double push(double x) {
        while (!q_.empty() && q_.back().second <= x) q_.pop_back();   // 比 x 小的以后不可能是最大
        q_.emplace_back(i_, x);
        if (q_.front().first <= i_ - n_) q_.pop_front();             // 滑出窗口
        ++i_;
        return q_.front().second;
    }
};

// ---- 4.3 找 bar：线性找 → 直接算下标 ----
std::vector<int> g_bar_end;              // 每个 bar 的结束秒（含），线性查找用
int bar_linear(int sec) {
    for (size_t i = 0; i < g_bar_end.size(); ++i) if (g_bar_end[i] >= sec) return int(i);
    return int(g_bar_end.size());
}
int bar_direct(int sec) {
    constexpr int kOpen = 9 * 3600 + 30 * 60, kNoon = 11 * 3600 + 30 * 60, kPm = 13 * 3600;
    if (sec <= kNoon) return (sec - kOpen) / 3;
    return 2400 + (sec - kPm) / 3;                       // 上午 2 小时 = 2400 个 bar
}

// ---- 4.4 由数据决定的分支 → 条件表达式 / 算术 ----
double pick_before(const Tick& t, int i, double last) { if (t.bid_px[i] > 0) return t.bid_px[i]; else return last; }
double pick_after (const Tick& t, int i, double last) { return t.bid_px[i] > 0 ? t.bid_px[i] : last; }   // 通常编成 cmov

// ---- 4.6 一个累加器串着加 → 4 个累加器 ----
double sum_before(const double* x, int n) { double s = 0; for (int i = 0; i < n; ++i) s += x[i]; return s; }
double sum_after(const double* x, int n) {
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0; int i = 0;
    for (; i + 4 <= n; i += 4) { s0 += x[i]; s1 += x[i + 1]; s2 += x[i + 2]; s3 += x[i + 3]; }
    double s = (s0 + s1) + (s2 + s3);
    for (; i < n; ++i) s += x[i];
    return s;
}

// ---- 4.7 虚函数 → CRTP，一组因子在编译期拼好 ----
struct IFactor { virtual void on_tick(const Tick& t) = 0; virtual double value() const = 0; virtual ~IFactor() = default; };
struct SpreadV : IFactor { double v = 0; void on_tick(const Tick& t) override { v += t.ask_px[0] - t.bid_px[0]; } double value() const override { return v; } };
struct MidV    : IFactor { double v = 0; void on_tick(const Tick& t) override { v += (t.ask_px[0] + t.bid_px[0]) / 2; } double value() const override { return v; } };

template <class D> struct FactorBase { void on_tick(const Tick& t) { static_cast<D*>(this)->on_tick_impl(t); } };
struct Spread : FactorBase<Spread> { double v = 0; void on_tick_impl(const Tick& t) { v += t.ask_px[0] - t.bid_px[0]; } };
struct Mid    : FactorBase<Mid>    { double v = 0; void on_tick_impl(const Tick& t) { v += (t.ask_px[0] + t.bid_px[0]) / 2; } };
template <class... Fs> struct FactorSet {
    std::tuple<Fs...> fs;
    void on_tick(const Tick& t) { std::apply([&](auto&... f) { (f.on_tick(t), ...); }, fs); }
};

// ---- 4.8 热循环里的分配 → 提到外面、复用 ----
void fill(std::vector<double>& v, const Tick& t) { for (int i = 0; i < 10; ++i) v.push_back(t.bid_px[i] * t.bid_vol[i]); }
double alloc_before(const std::vector<Tick>& ts) {
    double s = 0;
    for (auto& t : ts) { std::vector<double> tmp; fill(tmp, t); s += tmp[3]; }
    return s;
}
double alloc_after(const std::vector<Tick>& ts) {
    double s = 0; std::vector<double> tmp; tmp.reserve(16);
    for (auto& t : ts) { tmp.clear(); fill(tmp, t); s += tmp[3]; }   // clear 只把长度归零，不释放
    return s;
}

int main() {
    std::mt19937 rng(7);
    std::uniform_real_distribution<double> px(9.5, 10.5), vol(0, 1000);
    std::vector<Tick> ticks(20000);
    for (auto& t : ticks) {
        for (int i = 0; i < 10; ++i) { t.bid_px[i] = (rng() % 5 == 0) ? 0 : px(rng); t.ask_px[i] = t.bid_px[i] + 0.01; t.bid_vol[i] = vol(rng); }
        t.last = px(rng);
    }

    for (auto& t : ticks) { double a[4], b[4]; depth_before(t, a); depth_after(t, b); for (int k = 0; k < 4; ++k) assert(a[k] == b[k]); }

    // 滚动和 + 滚动最大值，对暴力
    const int N = 20; double run = 0; RollingMax rm(N); std::vector<double> xs;
    for (auto& t : ticks) {
        double x = t.last; xs.push_back(x);
        run += x; if (xs.size() > N) run -= xs[xs.size() - 1 - N];
        double mx = rm.push(x);
        size_t lo = xs.size() > N ? xs.size() - N : 0;
        double brute_sum = 0, brute_max = -1e300;
        for (size_t j = lo; j < xs.size(); ++j) { brute_sum += xs[j]; brute_max = std::max(brute_max, xs[j]); }
        assert(std::fabs(run - brute_sum) < 1e-9 && mx == brute_max);
    }

    // bar：两种写法对全天每一秒结果一样
    for (int b = 0; b < 2400; ++b) g_bar_end.push_back(9 * 3600 + 30 * 60 + 3 * b + 2);
    for (int b = 0; b < 2400; ++b) g_bar_end.push_back(13 * 3600 + 3 * b + 2);
    for (int s = 9 * 3600 + 30 * 60; s <= 11 * 3600 + 30 * 60; ++s) assert(bar_linear(s) == bar_direct(s));
    for (int s = 13 * 3600; s < 15 * 3600; ++s) assert(bar_linear(s) == bar_direct(s));

    for (auto& t : ticks) for (int i = 0; i < 10; ++i) assert(pick_before(t, i, t.last) == pick_after(t, i, t.last));

    std::vector<double> big(1'000'003); for (auto& v : big) v = px(rng);
    double s1 = sum_before(big.data(), int(big.size())), s2 = sum_after(big.data(), int(big.size()));
    assert(std::fabs(s1 - s2) <= 1e-9 * std::fabs(s1));      // 换了求和顺序，末位会变：按容差比
    std::printf("串行和 %.17g，4 路和 %.17g（末位不同是正常的）\n", s1, s2);

    std::vector<std::unique_ptr<IFactor>> virt; virt.emplace_back(new SpreadV); virt.emplace_back(new MidV);
    FactorSet<Spread, Mid> crtp;
    for (auto& t : ticks) { for (auto& f : virt) f->on_tick(t); crtp.on_tick(t); }
    assert(virt[0]->value() == std::get<0>(crtp.fs).v && virt[1]->value() == std::get<1>(crtp.fs).v);

    assert(alloc_before(ticks) == alloc_after(ticks));
    std::printf("全部测试通过！\n");
}
```

</details>
