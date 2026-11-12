---
title: "手撕：8 道增量计算和数据结构"
date: 2026-11-09
slug: "handwrite-8"
description: "面试现场手写的 8 道题：前 5 道是因子的增量算法，滚动均值方差（Welford）、滚动最大值（单调队列）、滚动中位数（两个 multiset）、截面排名（同值取平均）、EMA（adjust 两种），结果都要和 pandas 逐值相同；后 3 道是 C++ 岗常见的订单簿、SPSC 环形队列、LRU。每道附参考代码，都和暴力解随机对拍过。"
weight: 8
math: true
toc: true
---
这 8 道是面试里最可能让当场写的题，分两组：

- **前 5 道是因子的增量算法**：研究侧用 pandas 一次算一整列；实盘里行情一条一条来，每来一条只能花 $O(1)$ 或 $O(\log n)$ 更新，结果还要和 pandas 逐值相同。所以每道都先说清楚它对齐 pandas 的哪个写法，对不上的常见原因见 [因子生产第 4 节](/zh/ref/factor-production/#consistency)。
- **后 3 道是 C++ 岗常见的手写题**：订单簿、SPSC 环形队列、LRU。

> **写完怎么判对：和暴力解随机对拍**
>
> - **暴力解直接按定义算**：每一步把整个窗口重新扫一遍，慢，但一眼能看出是对的。
> - **随机数据取小值域**：值只在 0–9 里取，相等的值会大量出现，等号边界上的错才会暴露出来。
> - **浮点比较带容差**：增量更新和重新计算的求和顺序不同，最后几位会差一点（[因子生产 4.3.1](/zh/ref/factor-production/#sum-order)）。
> - **跑几千组，不一致的个数为 0 才算对**：下面每道的参考代码都这样对拍过。

## 1. 因子的增量算法

### 1.1 滚动均值和方差：Welford，先出后进

1. **题目：长度为 n 的窗口，每进一条，输出窗口的均值和方差**
   - **对齐 `x.rolling(n).mean()` 和 `.var()`**：方差默认 `ddof=1`，分母是 $n-1$（[因子生产 4.4.2](/zh/ref/factor-production/#ddof)）；窗口没满时输出 NaN（[因子生产 4.4.3](/zh/ref/factor-production/#rolling)）。

2. **不用“平方和减和的平方”：两个大数相减，有效数字会被吃掉**
   - **这个公式是** $\text{var} = \dfrac{\sum x^2 - (\sum x)^2 / n}{n-1}$。
   - **价格在 100 附近、只差几分钱时**：两项都约是 $10^4 n$，差却只有 $10^{-4} n$ 的量级，double 的 16 位有效数字被吃掉 8 位，严重时算出负方差。
   - **Welford 改成维护均值 $\bar{x}$ 和偏差平方和 $M_2 = \sum (x - \bar{x})^2$**：每一步只加减小量，不会出现大数相减。

3. **进一个、出一个，各自 $O(1)$**
   - **进来 $x$，个数变成 $k$**：$\delta = x - \bar{x}_{\text{旧}}$，$\bar{x}_{\text{新}} = \bar{x}_{\text{旧}} + \delta / k$，$M_2 \mathrel{+}= \delta \, (x - \bar{x}_{\text{新}})$。
   - **出去 $y$，个数变成 $k$**：$\delta = y - \bar{x}_{\text{旧}}$，$\bar{x}_{\text{新}} = \bar{x}_{\text{旧}} - \delta / k$，$M_2 \mathrel{-}= \delta \, (y - \bar{x}_{\text{新}})$。
   - **两条都是一次用旧均值、一次用新均值**：这样乘出来的正好是 $M_2$ 的精确变化量。

   ```cpp
   struct RollingMeanVar {
       int n;
       deque<double> win;
       double mean = 0, m2 = 0;                 // m2 = 窗口内 (x - mean)^2 之和
       explicit RollingMeanVar(int n_) : n(n_) {}
       void push(double x) {
           if ((int)win.size() == n) {          // 先把最老的移出去
               double y = win.front(); win.pop_front();
               int k = win.size();
               if (k == 0) { mean = 0; m2 = 0; }
               else {
                   double d = y - mean;         // 旧均值
                   mean -= d / k;
                   m2 -= d * (y - mean);        // 新均值
               }
           }
           win.push_back(x);
           int k = win.size();
           double d = x - mean;
           mean += d / k;
           m2 += d * (x - mean);
       }
       bool ready() const { return (int)win.size() == n; }   // 没满时外面输出 NaN
       double get_mean() const { return mean; }
       double get_var() const { return m2 / (n - 1); }       // ddof = 1
   };
   ```

   - **先出后进**：反过来做，窗口里会短暂多出一个元素，个数 $k$ 就错了。
   - **$n = 1$ 时样本方差没有定义**：分母是 0，pandas 也给 NaN。

### 1.2 滚动最大值：单调队列

1. **题目：长度为 n 的窗口，每进一条，输出窗口的最大值**
   - **对齐 `x.rolling(n, min_periods=1).max()`**：从第一条就开始输出，窗口没满时取已有的那些。
   - **和 [LC 239](/zh/algo/a2-stack-monotonic-stack-heap/#25-单调队列滑动窗口里的最大值) 是同一道题**，只是改成一条一条来。

2. **队列里只留以后还可能当最大值的元素，值从队头到队尾递减**

   ```cpp
   struct RollingMax {
       int n;
       long long idx = 0;                       // 下一条的下标
       deque<pair<long long, double>> q;        // (下标, 值)
       explicit RollingMax(int n_) : n(n_) {}
       void push(double x) {
           while (!q.empty() && q.back().second <= x) q.pop_back();   // 队尾：以后当不了最大
           q.push_back({idx, x});
           while (q.front().first <= idx - n) q.pop_front();           // 队头：滑出窗口
           ++idx;
       }
       double get_max() const { return q.front().second; }
   };
   ```

   - **队尾扔掉不比 $x$ 大的**：它们比 $x$ 先离开窗口，又不比 $x$ 大，以后永远当不了最大值。相等的也扔，留新的那个，它活得更久。
   - **队列存下标**：要靠下标判断是不是滑出了窗口。
   - **摊下来每条 $O(1)$**：每个元素进队一次、出队最多一次。

### 1.3 滚动中位数：两个 multiset

1. **题目：长度为 n 的窗口，每进一条，输出窗口的中位数**
   - **对齐 `x.rolling(n, min_periods=1).median()`**：偶数个时取中间两个的平均。

2. **数据流的中位数用两个堆，窗口版要删过期元素，堆删不了中间的**
   - **[LC 295](/zh/algo/a2-stack-monotonic-stack-heap/#34-两个堆维护中位数) 只加不删**：大根堆装小的一半，小根堆装大的一半。
   - **窗口版每步要删一个任意位置的元素**：换成两个 `multiset`，每样操作 $O(\log n)$；也可以继续用堆，加[懒删除](/zh/algo/a2-stack-monotonic-stack-heap/#35-堆删不了中间的元素懒删除)。

3. **保持两条不变式：`lo` 的最大不超过 `hi` 的最小；`lo` 和 `hi` 一样多，或者多 1 个**

   ```cpp
   struct RollingMedian {
       int n;
       deque<double> win;
       multiset<double> lo, hi;                 // lo 装小的一半，hi 装大的一半
       explicit RollingMedian(int n_) : n(n_) {}
       void rebalance() {
           if (lo.size() > hi.size() + 1) { auto it = prev(lo.end()); hi.insert(*it); lo.erase(it); }
           else if (hi.size() > lo.size()) { auto it = hi.begin(); lo.insert(*it); hi.erase(it); }
       }
       void push(double x) {
           if ((int)win.size() == n) {
               double y = win.front(); win.pop_front();
               auto it = lo.find(y);            // 只删一个
               if (it != lo.end()) lo.erase(it); else hi.erase(hi.find(y));
               rebalance();
           }
           win.push_back(x);
           if (lo.empty() || x <= *prev(lo.end())) lo.insert(x); else hi.insert(x);
           rebalance();
       }
       double get_median() const {
           if (lo.size() > hi.size()) return *prev(lo.end());
           return (*prev(lo.end()) + *hi.begin()) / 2;
       }
   };
   ```

   - **删除要写 `erase(find(y))`**：`erase(y)` 会把所有等于 $y$ 的都删掉，窗口里有重复值时就少了。
   - **先在 `lo` 里找，找不到再去 `hi`**：同一个值可能两边都有，删哪边都对，删完 `rebalance` 会把个数补平。
   - **每步一次删除、一次插入、最多两次挪动**：$O(\log n)$。

### 1.4 截面排名：同值取平均名次

1. **题目：同一时刻几千只股票的因子值，求每只的排名**
   - **对齐 `s.rank()` 和 `s.rank(pct=True)`**：同值取平均名次（`method='average'`）；NaN 不参与排名，结果保持 NaN；`pct=True` 时除以有效个数（[因子生产 4.6.1](/zh/ref/factor-production/#rank)）。

2. **按值排序下标，一组相同的值一起给名次**

   ```cpp
   vector<double> cs_rank(const vector<double>& v, bool pct) {
       int n = v.size();
       vector<double> out(n, NAN);
       vector<int> idx;
       for (int i = 0; i < n; ++i) if (!isnan(v[i])) idx.push_back(i);   // NaN 不参与
       sort(idx.begin(), idx.end(), [&](int a, int b) { return v[a] < v[b]; });
       int m = idx.size();
       for (int i = 0; i < m;) {
           int j = i;
           while (j < m && v[idx[j]] == v[idx[i]]) ++j;   // [i, j) 是一组相同的值
           double r = (i + 1 + j) / 2.0;                  // 名次 i+1 .. j 的平均
           for (int k = i; k < j; ++k) out[idx[k]] = pct ? r / m : r;
           i = j;
       }
       return out;
   }
   ```

   - **NaN 必须在排序前剔掉**：NaN 和谁比都是 false，放进 `sort` 会破坏比较器要求的严格弱序，结果不可预测。
   - **名次从 1 开始**：一组占名次 $i+1$ 到 $j$，平均是 $(i+1+j)/2$。
   - **`pct` 除以有效个数 $m$，不是总数 $n$**。
   - **复杂度**：排序 $O(m \log m)$。

### 1.5 EMA：adjust 的两种写法

1. **题目：对齐 `x.ewm(alpha=a, adjust=...).mean()`，每进一条输出一个值**
   - **`adjust=False` 是递推**：$y_0 = x_0$，$y_t = (1-\alpha)\, y_{t-1} + \alpha\, x_t$。
   - **`adjust=True` 是对全部历史加权平均**（[因子生产 4.4.4](/zh/ref/factor-production/#ewm)）：
     $$y_t = \frac{\sum_{i=0}^{t} (1-\alpha)^i\, x_{t-i}}{\sum_{i=0}^{t} (1-\alpha)^i}$$

2. **`adjust=True` 也能 $O(1)$：分子、分母各自递推**
   - **新来一条，旧的权重都乘一次 $1-\alpha$，新的一条权重是 1**：所以 $\text{num}_t = x_t + (1-\alpha)\,\text{num}_{t-1}$，分母同理是 $\text{den}_t = 1 + (1-\alpha)\,\text{den}_{t-1}$。

   ```cpp
   struct EmaNoAdjust {
       double a, y = 0;
       bool started = false;
       explicit EmaNoAdjust(double a_) : a(a_) {}
       double push(double x) {
           if (!started) { y = x; started = true; }
           else y = (1 - a) * y + a * x;
           return y;
       }
   };

   struct EmaAdjust {
       double a, num = 0, den = 0;
       explicit EmaAdjust(double a_) : a(a_) {}
       double push(double x) {
           num = x + (1 - a) * num;
           den = 1 + (1 - a) * den;
           return num / den;
       }
   };
   ```

   - **两种写法开头几条不同，越往后越接近**：分母收敛到 $1/\alpha$ 以后，`adjust=True` 就和递推一样了。
   - **对不上时看差值的样子**：开头差得大、后面慢慢收敛，多半是两边的 `adjust` 不一样。

## 2. C++ 岗常见的手写题

### 2.1 订单簿：每个价位的总量，按委托号扣

1. **题目：用逐笔维护每个价位上挂着的总量，随时取买一、卖一**
   - **逐笔委托是 `add`**：按委托号记下方向、价格、数量，加到那个价位上。
   - **撤单和成交都是 `reduce`**：按委托号找到那笔委托，从它的价位上扣掉；成交时买卖两边各扣一次。

2. **价位用有序的 `map`，委托用哈希表**

   ```cpp
   struct Book {
       struct Order { bool is_bid; int px; long long qty; };
       unordered_map<long long, Order> orders;      // 委托号 -> 委托
       map<int, long long, greater<int>> bids;      // 价格从高到低，begin() 是买一
       map<int, long long> asks;                    // 价格从低到高，begin() 是卖一
       void add(long long id, bool is_bid, int px, long long qty) {
           orders[id] = {is_bid, px, qty};
           if (is_bid) bids[px] += qty; else asks[px] += qty;
       }
       void reduce(long long id, long long qty) {     // 撤单、成交
           auto it = orders.find(id);
           if (it == orders.end()) return;
           Order& o = it->second;
           if (o.is_bid) { if ((bids[o.px] -= qty) == 0) bids.erase(o.px); }
           else          { if ((asks[o.px] -= qty) == 0) asks.erase(o.px); }
           if ((o.qty -= qty) == 0) orders.erase(it);
       }
       int best_bid() const { return bids.empty() ? -1 : bids.begin()->first; }
       int best_ask() const { return asks.empty() ? -1 : asks.begin()->first; }
       long long qty_at(bool is_bid, int px) const {
           if (is_bid) { auto it = bids.find(px); return it == bids.end() ? 0 : it->second; }
           auto it = asks.find(px);
           return it == asks.end() ? 0 : it->second;
       }
   };
   ```

   - **价位扣到 0 必须删掉**：不删的话 `begin()` 还停在这个空价位上，买一、卖一就错了。
   - **价格用整数**：按最小变动单位存（比如“分”），浮点价格当 `map` 的键，会因为 0.1 + 0.2 这类误差多出一个价位。
   - **复杂度**：`add`、`reduce` 是 $O(\log P)$，$P$ 是价位数；买一、卖一 $O(1)$。
   - **这里只维护每档总量**：要按时间优先撮合，每档要挂一条委托队列，见 [A6 2.2](/zh/algo/a6-strings-and-design/#22-订单簿价格优先时间优先)。实盘里价格集中在买一卖一附近，价位常改成按最小变动单位下标的数组，取买一卖一不再查树。

### 2.2 SPSC 环形队列：一个写、一个读，不加锁

1. **题目：一个线程写、一个线程读的定长队列，`try_push` 满了返回 false，`try_pop` 空了返回 false**
   - **完整的讲解在 [无锁队列 1.2](/zh/posts/lock-free-queue-logger-micro-batching/#spsc-ring)**，这里是手写时要写出来的最短版本。

2. **两个下标只增不减，靠掩码落到槽位上**

   ```cpp
   template <class T, size_t N>                     // N 必须是 2 的幂
   struct Spsc {
       static_assert((N & (N - 1)) == 0);
       T buf[N];
       alignas(128) atomic<size_t> head{0};         // 读者改：下一个要读的位置
       alignas(128) atomic<size_t> tail{0};         // 写者改：下一个要写的位置
       bool try_push(const T& v) {
           size_t t = tail.load(memory_order_relaxed);                   // 自己改的，relaxed 就够
           if (t - head.load(memory_order_acquire) == N) return false;   // 满
           buf[t & (N - 1)] = v;
           tail.store(t + 1, memory_order_release);                      // 先写数据，再发布
           return true;
       }
       bool try_pop(T& v) {
           size_t h = head.load(memory_order_relaxed);
           if (h == tail.load(memory_order_acquire)) return false;       // 空
           v = buf[h & (N - 1)];
           head.store(h + 1, memory_order_release);                      // 读完了，槽位还给写者
           return true;
       }
   };
   ```

   - **容量取 2 的幂**：`& (N - 1)` 代替 `% N`，省一次除法。
   - **元素个数是 `tail - head`**：下标只增不减，无符号数回绕时相减照样对，不用另设计数器。
   - **写者先写数据，再 release 发布 `tail`；读者 acquire 读到 `tail`，再读数据**：这一对保证读者看到新下标时，数据一定已经写好了。`head` 反过来同理，保证写者覆盖槽位时，读者已经读完。
   - **`head` 和 `tail` 隔 128 B**：两个线程各写一个，放在同一条缓存行里就是伪共享；只隔 64 B，L2 的相邻行预取也会把两条行一起拉过来（[速查 2.6](/zh/ref/cpu-memory/#cross-core)）。
   - **测法**：两个线程推 1000 万条，读者检查顺序不乱、一条不丢。

### 2.3 LRU 缓存：哈希表定位，链表排新旧

1. **题目：[LC 146](https://leetcode.cn/problems/lru-cache/)，`get` 和 `put` 都要 $O(1)$，满了淘汰最久没用过的**
   - **完整的讲解在 [A6 2.1](/zh/algo/a6-strings-and-design/#21-lru-缓存哈希表定位双向链表排新旧)**，这里是最短版本。

   ```cpp
   struct LRU {
       int cap;
       list<pair<int, int>> lst;                                // (key, value)，头是最新
       unordered_map<int, list<pair<int, int>>::iterator> pos;
       explicit LRU(int c) : cap(c) {}
       int get(int key) {
           auto it = pos.find(key);
           if (it == pos.end()) return -1;
           lst.splice(lst.begin(), lst, it->second);            // 挪到头
           return it->second->second;
       }
       void put(int key, int value) {
           auto it = pos.find(key);
           if (it != pos.end()) {
               it->second->second = value;
               lst.splice(lst.begin(), lst, it->second);
               return;
           }
           if ((int)lst.size() == cap) { pos.erase(lst.back().first); lst.pop_back(); }
           lst.push_front({key, value});
           pos[key] = lst.begin();
       }
   };
   ```

   - **`splice` 只改指针，不拷贝节点**：哈希表里存的迭代器不会失效。
   - **链表里要存 key**：淘汰链表尾时，要拿它的 key 去哈希表里删。
   - **更新已有的 key 也算一次使用**：要挪到头。

## 练习：8 道 LeetCode

挑的是面试最常见、又和 QD 的活沾边的。讲解都在对应的文章里。

| 题 | 套路 | 讲解 |
|---|---|---|
| [LC 23 合并 K 个升序链表](https://leetcode.cn/problems/merge-k-sorted-lists/) | 小根堆多路归并，等于多路行情按时间戳合并 | [A2（上）练习 4](/zh/algo/a2-stack-monotonic-stack-heap/#练习-4lc-23-合并-k-个升序链表小根堆多路归并) |
| [LC 215 数组中的第 K 个最大元素](https://leetcode.cn/problems/kth-largest-element-in-an-array/) | 只留 k 个的小根堆，$O(n \log k)$，流式也能用 | [A2（上）3.2](/zh/algo/a2-stack-monotonic-stack-heap/#32-top-k只留-k-个的小根堆) |
| [LC 560 和为 K 的子数组](https://leetcode.cn/problems/subarray-sum-equals-k/) | 前缀和加哈希表 | [A2（下）1.5](/zh/algo/a2-hash-greedy-bits/#15-和为-k-的子数组前缀和加哈希表) |
| [LC 56 合并区间](https://leetcode.cn/problems/merge-intervals/) | 按左端点排序，接得上就延长 | [A2（下）2.4](/zh/algo/a2-hash-greedy-bits/#24-合并区间按左端点排序接得上就延长) |
| [LC 34 在排序数组中查找元素的第一个和最后一个位置](https://leetcode.cn/problems/find-first-and-last-position-of-element-in-sorted-array/) | 两个“第一个为真” | [A1 练习 1](/zh/algo/a1-complexity-binary-search-two-pointers-prefix-sums/#练习-1lc-34-两个边界都用第一个为真) |
| [LC 3 无重复字符的最长子串](https://leetcode.cn/problems/longest-substring-without-repeating-characters/) | 滑动窗口，最长合法窗口 | [A1 3.2](/zh/algo/a1-complexity-binary-search-two-pointers-prefix-sums/#32-两种写法最长合法最短合法) |
| [LC 300 最长递增子序列](https://leetcode.cn/problems/longest-increasing-subsequence/) | 贪心加二分，$O(n \log n)$ | [A5 2.1](/zh/algo/a5-dynamic-programming/#21-最长递增子序列以第-i-个结尾或者每个长度的最小结尾) |
| [LC 207 课程表](https://leetcode.cn/problems/course-schedule/) | 拓扑排序，入度为 0 的先出 | [A4 3.1](/zh/algo/a4-graphs-shortest-path-topo-dsu/#31-kahn入度为-0-的先出队) |
