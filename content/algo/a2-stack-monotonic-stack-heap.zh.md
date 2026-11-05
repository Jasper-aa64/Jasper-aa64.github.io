---
title: "A2（上）：栈、单调栈、堆"
date: 2026-11-05
slug: "a2-stack-monotonic-stack-heap"
description: "三样维护候选的结构：栈取最近一个还没配对的；单调栈把以后永远用不上的候选提前扔掉，一遍求出每个元素左右第一个更大或更小的，再拿这对边界算最大矩形、做贡献计数；单调队列求滑窗最值；堆随时取最值，用来做 Top K、多路归并、两个堆维护中位数，删不了中间的元素时用懒删除。附 9 道练习题。"
weight: 2
math: true
toc: true
---
这一轮的三样东西都在维护一组候选，每一步取出最该处理的那一个。**栈按到达顺序取最近的；单调栈在栈的基础上，把以后永远用不上的候选提前扔掉；堆按大小取最大或最小的。** 栈和单调栈每个元素只进出一次，总共 $O(n)$；堆的插入和取出是 $O(\log n)$。哈希表、排序与贪心、位运算放在 A2 的下半。

## 1. 栈：要找的总是最近一个还没配对的

### 1.1 括号匹配：右括号只和最近的左括号配

[LC 20](https://leetcode.cn/problems/valid-parentheses/)：一个字符串里只有 `()[]{}`，问括号是不是都正确配对。

一个右括号该和谁配？**和它左边最近的、还没配上的左括号。** 从左往右扫，左括号压栈；遇到右括号，栈顶就是“最近的、还没配上的”那个，类型对得上就弹掉，对不上就是错的。扫完栈里还剩左括号，也是错的。

```cpp
bool isValid(string s) {
    string st;                              // 当栈用
    for (char c : s) {
        if (c == '(' || c == '[' || c == '{') { st.push_back(c); continue; }
        char need = c == ')' ? '(' : c == ']' ? '[' : '{';
        if (st.empty() || st.back() != need) return false;
        st.pop_back();
    }
    return st.empty();                      // 还有左括号没配上
}
```

> **什么时候想到栈**
>
> - **问题里有“和最近一个还没处理完的东西配对或抵消”**：括号和标签的嵌套、撤销操作、表达式求值、路径化简（`..` 抵消上一层目录）。
> - **递归改成循环**：递归本身就是系统栈，手写一个栈能模拟它，DFS 的非递归写法就是这样来的。

## 2. 单调栈：每个元素左右第一个比它大（小）的

### 2.1 栈里只留还没找到答案的元素，它们自然是单调的

[LC 739 每日温度](https://leetcode.cn/problems/daily-temperatures/)：给每天的温度，对每一天求要再等几天才会更热，之后都不会更热就填 0。$n \le 10^5$。

暴力是对每天往后扫，最坏 $O(n^2)$，会超时。换个方向想：从左往右扫，**把还没等到更热那天的日子放在栈里**。新来一天 $i$，栈顶那天如果比 $i$ 冷，$i$ 就是它等的那天，记下答案、弹掉；一直弹到栈顶不比 $i$ 冷为止，再把 $i$ 压进去。

**为什么 $i$ 一定是被弹掉那天 $j$ 之后第一个更热的？** $j$ 和 $i$ 之间的每一天都是在 $j$ 之后进栈的。它们当中要是有一天比 $j$ 热，进栈时就已经把 $j$ 弹掉了，轮不到 $i$。

**这个栈从底到顶温度不增**：一个比栈顶热的日子进栈前，会先把比它冷的都弹掉。所以叫单调栈，单调是这个做法的结果，不用专门去维护。

```cpp
vector<int> dailyTemperatures(vector<int>& t) {
    int n = t.size();
    vector<int> ans(n, 0);                  // 没被弹掉的，答案就是 0
    vector<int> st;                         // 存下标
    for (int i = 0; i < n; i++) {
        while (!st.empty() && t[st.back()] < t[i]) {
            ans[st.back()] = i - st.back(); // i 是它之后第一个更热的
            st.pop_back();
        }
        st.push_back(i);
    }
    return ans;
}
```

拿样例 `[73, 74, 75, 71, 69, 72, 76, 73]` 走一遍，栈里写成“温度（下标）”：

| $i$ | 温度 | 弹掉的（答案） | 栈，底 → 顶 |
|---|---|---|---|
| 0 | 73 | | 73(0) |
| 1 | 74 | 73(0)：1 | 74(1) |
| 2 | 75 | 74(1)：1 | 75(2) |
| 3 | 71 | | 75(2) 71(3) |
| 4 | 69 | | 75(2) 71(3) 69(4) |
| 5 | 72 | 69(4)：1，71(3)：2 | 75(2) 72(5) |
| 6 | 76 | 72(5)：1，75(2)：4 | 76(6) |
| 7 | 73 | | 76(6) 73(7) |

最后栈里剩下的 76、73 之后都没有更热的，答案是 0。结果 `1 1 4 2 1 1 0 0`。

**复杂度是 $O(n)$，虽然里面套了一个 while。** 每个下标进栈一次，出栈最多一次，所以 while 的循环体在整个过程里加起来最多执行 $n$ 次。

### 2.2 同一遍拿到两个方向的答案，只差比较符号

被弹掉的元素拿到的是**右边**的答案。另一个方向也在同一遍里：**$i$ 弹完以后，栈顶就是 $i$ 左边离它最近的、没被弹条件弹掉的那个**，也就是左边的答案。改一下弹栈条件，就得到四种组合：

| 弹栈条件 | 被弹的 $j$ 得到 | 弹完后的栈顶是 $i$ 的 |
|---|---|---|
| `a[top] < a[i]` | 右边第一个 $>$ 它的 | 左边最近的 $\ge$ 它的 |
| `a[top] <= a[i]` | 右边第一个 $\ge$ 它的 | 左边最近的 $>$ 它的 |
| `a[top] > a[i]` | 右边第一个 $<$ 它的 | 左边最近的 $\le$ 它的 |
| `a[top] >= a[i]` | 右边第一个 $\le$ 它的 | 左边最近的 $<$ 它的 |

规律是**右边那一侧的符号就是弹栈条件反过来看，左边那一侧和右边恰好一个带等号、一个不带**。四种都和暴力对拍过。

> **比较符号怎么选：先想清楚相等的元素算不算**
>
> - **数组里没有重复值**：四种随便用，结果一样。
> - **有重复值，题目问的是“严格更大”**：右边用 `<` 弹（第一行）。
> - **要拿左右边界去数子数组**（2.4）：一边带等号、一边不带，否则几个相等的最小值会把同一个子数组数两遍。

### 2.3 以每根柱子为最矮的那根：柱状图里的最大矩形

[LC 84](https://leetcode.cn/problems/largest-rectangle-in-histogram/)：给一排宽为 1 的柱子的高度，求能勾勒出的最大矩形面积。$n \le 10^5$。

枚举左右端点是 $O(n^2)$。换个角度：**矩形的高一定等于它覆盖的柱子里最矮那根的高**。于是对每根柱子 $j$，算“以它为最矮的那根”时矩形最宽能有多宽：向左、向右各延伸到第一根比它矮的柱子为止。设这两根的下标是 $L$ 和 $R$，面积就是

$$h_j \times (R - L - 1)$$

两边的边界正好是 2.2 表里最后一行：用 `>=` 弹栈，$j$ 被 $i$ 弹掉时，$i$ 是右边第一根不高于它的，弹掉以后的栈顶是左边第一根比它矮的。

```cpp
int largestRectangleArea(vector<int>& h) {
    h.push_back(0);                         // 哨兵：最后把栈里的柱子全弹出来
    vector<int> st;
    long long best = 0;
    for (int i = 0; i < (int)h.size(); i++) {
        while (!st.empty() && h[st.back()] >= h[i]) {
            long long height = h[st.back()]; st.pop_back();
            int left = st.empty() ? -1 : st.back();   // 左边第一根更矮的，没有就是 -1
            best = max(best, height * (i - left - 1));
        }
        st.push_back(i);
    }
    h.pop_back();
    return best;
}
```

**相等的柱子会少算宽度，但不影响答案。** 用 `>=` 弹，两根一样高的，前一根被后一根弹掉，右边界停在后一根上，宽度算短了。可这一段等高柱子里最靠右的那根，左边界会越过它们，右边界停在真正更矮的柱子上，宽度是对的。比如 `[2, 5, 2]`：下标 0 被下标 2 弹掉时只算出宽 2，下标 2 被哨兵弹掉时算出宽 3，面积 6。

**哨兵 0 比所有高度都矮**，扫到它时栈里剩下的柱子都会被弹出来结算，不用在循环外再写一遍。

### 2.4 同一对边界拿来计数：所有子数组最小值之和

[LC 907](https://leetcode.cn/problems/sum-of-subarray-minimums/)：求所有连续子数组的最小值之和，对 $10^9 + 7$ 取模。$n \le 3 \times 10^4$。

子数组有 $O(n^2)$ 个，一个个枚举太慢。**反过来对每个元素算：它是多少个子数组的最小值。** 设 $a_j$ 左边第一个比它小的在 $L$，右边第一个不大于它的在 $R$。左端点在 $(L, j]$ 里、右端点在 $[j, R)$ 里的子数组，最小值都是 $a_j$，一共 $(j - L)(R - j)$ 个，所以

$$\text{答案} = \sum_j a_j \cdot (j - L_j) \cdot (R_j - j)$$

```cpp
int sumSubarrayMins(vector<int>& a) {
    const long long MOD = 1e9 + 7;
    a.push_back(0);                         // 哨兵，同 2.3
    vector<int> st;
    long long ans = 0;
    for (int i = 0; i < (int)a.size(); i++) {
        while (!st.empty() && a[st.back()] >= a[i]) {
            int j = st.back(); st.pop_back();
            int left = st.empty() ? -1 : st.back();
            ans = (ans + (long long)a[j] * (j - left) % MOD * (i - j)) % MOD;
        }
        st.push_back(i);
    }
    a.pop_back();
    return ans;
}
```

**为什么一边带等号、一边不带。** 拿 `[1, 1]` 来说，子数组 `[1, 1]` 有两个相等的最小值。左边找“严格更小”、右边找“不大于”，就是把每个子数组算在它最靠右的那个最小值头上：下标 0 的右边界停在下标 1，只数到 `[1]` 自己；下标 1 的左边界越过下标 0，数到 `[1]` 和 `[1, 1]`。合计 3，正确。两边都找“严格更小”，`[1, 1]` 会被两个下标各数一次。

> **认出贡献法**
>
> - **问“所有子数组的最小值（或最大值）之和”**：不枚举子数组，对每个元素算它是多少个子数组的最值，用单调栈求左右边界。
> - **问“以某个元素为瓶颈时最大能多大”**：像 2.3 那样，对每个元素求它能向两边延伸多远。

### 2.5 单调队列：滑动窗口里的最大值

[LC 239](https://leetcode.cn/problems/sliding-window-maximum/)：一个长 $k$ 的窗口从左滑到右，输出每个位置窗口里的最大值。$n \le 10^5$。

窗口每滑一步，右边进一个、左边出一个。左边也要出元素，栈只能从一头进出，所以换成双端队列。**扔候选的理由和单调栈一样**：下标 $m < i$ 而且 $a_m \le a_i$，$m$ 会比 $i$ 先离开窗口，又不比 $i$ 大，以后永远当不了最大值，现在就可以扔掉。这样队列从头到尾是递减的，**队头就是当前窗口的最大值**，队头的下标滑出窗口时从队头弹掉。

```cpp
vector<int> maxSlidingWindow(vector<int>& a, int k) {
    deque<int> dq;                          // 存下标，对应的值从队头到队尾递减
    vector<int> ans;
    for (int i = 0; i < (int)a.size(); i++) {
        while (!dq.empty() && a[dq.back()] <= a[i]) dq.pop_back();   // 以后当不了最大值
        dq.push_back(i);
        if (dq.front() <= i - k) dq.pop_front();                     // 队头滑出了窗口
        if (i >= k - 1) ans.push_back(a[dq.front()]);
    }
    return ans;
}
```

每个下标进出队列各一次，$O(n)$。队尾弹的是“没用了”的，队头弹的是“过期了”的，两件事分开。

**单调队列也能放在前缀和上用**：有负数时求“和至少为 $k$ 的最短子数组”（[LC 862](https://leetcode.cn/problems/shortest-subarray-with-sum-at-least-k/)），滑动窗口用不了。对前缀和 $S$ 维护一个递增的单调队列：扫到 $r$ 时，队头 $l$ 只要满足 $S_r - S_l \ge k$ 就记一次答案并弹掉，因为之后的右端点再用它，子数组只会更长；队尾不小于 $S_r$ 的也弹掉，因为它们比 $r$ 早、前缀和又不比 $S_r$ 小，当左端点永远不如 $r$。

## 3. 堆：随时取出最大（最小）的那个

### 3.1 priority_queue 默认是大根堆，比较器的方向是反的

C++ 的 `priority_queue` 是一个二叉堆。`push` 和 `pop` 是 $O(\log n)$，`top` 是 $O(1)$，用一个已有的 `vector` 直接构造是 $O(n)$。

```cpp
priority_queue<int> mx;                                  // 大根堆，top 是最大的
priority_queue<int, vector<int>, greater<int>> mn;       // 小根堆，top 是最小的

auto cmp = [](const Node& a, const Node& b) { return a.val > b.val; };
priority_queue<Node, vector<Node>, decltype(cmp)> pq(cmp);   // 按 val 的小根堆
```

**比较器的含义和 `sort` 一样：`cmp(a, b)` 为真表示 a 排在 b 前面。但堆顶是排在最后的那个。** 所以默认的 `less` 给出大根堆，想要小根堆就写 `greater`，或者在自定义比较器里写 `>`。面试时写反了是最常见的错，写完拿两个数在脑子里过一遍。

### 3.2 Top K：只留 k 个的小根堆

[LC 215](https://leetcode.cn/problems/kth-largest-element-in-an-array/)：求数组里第 $k$ 大的数。

**用一个小根堆保存目前见过的最大的 $k$ 个数**，堆顶是这 $k$ 个里最小的，也就是第 $k$ 大。新来一个数先放进去，堆里超过 $k$ 个就把堆顶踢掉：被踢的数比 $k$ 个数都小，不可能再进前 $k$。

```cpp
int findKthLargest(vector<int>& a, int k) {
    priority_queue<int, vector<int>, greater<int>> pq;
    for (int x : a) {
        pq.push(x);
        if ((int)pq.size() > k) pq.pop();   // 踢掉 k+1 个里最小的
    }
    return pq.top();
}
```

时间 $O(n \log k)$，内存只要 $O(k)$。**数据是一条一条流进来的也能用**，比如行情流里实时维护成交额前 $k$ 的股票，不用把所有数据存下来。题目要 $O(n)$ 的话用 `nth_element`（快速选择，平均 $O(n)$），但它要求整个数组都在内存里。

### 3.3 多路归并：把 k 个有序序列合成一个

[LC 23](https://leetcode.cn/problems/merge-k-sorted-lists/)：合并 $k$ 个升序链表。

合成后的下一个元素，一定是这 $k$ 个链表当前表头里最小的那个。**堆里放每个链表的当前表头**，每次取出最小的接到结果后面，再把它的下一个节点放进堆里。

```cpp
ListNode* mergeKLists(vector<ListNode*>& lists) {
    auto cmp = [](ListNode* a, ListNode* b) { return a->val > b->val; };   // > 给出小根堆
    priority_queue<ListNode*, vector<ListNode*>, decltype(cmp)> pq(cmp);
    for (ListNode* p : lists) if (p) pq.push(p);
    ListNode dummy, *tail = &dummy;
    while (!pq.empty()) {
        ListNode* p = pq.top(); pq.pop();
        tail->next = p; tail = p;
        if (p->next) pq.push(p->next);
    }
    return dummy.next;
}
```

总共 $N$ 个节点，堆里最多 $k$ 个，时间 $O(N \log k)$。**几个交易所或几个通道的行情各自按时间有序，按时间戳合成一路，就是这道题。**

### 3.4 两个堆维护中位数

[LC 295](https://leetcode.cn/problems/find-median-from-data-stream/)：数一个一个加进来，随时要能回答当前的中位数。

把数分成较小的一半和较大的一半：**较小的一半放大根堆 `lo`，较大的一半放小根堆 `hi`**，中位数就在两个堆顶上。要一直保持两条：

- **`lo` 里每个数都不大于 `hi` 里每个数**：新数先进 `lo`，再把 `lo` 的堆顶挪到 `hi`。挪过去的是 `lo` 里最大的，顺序就不会乱。
- **`lo` 和 `hi` 一样多，或者 `lo` 多一个**：挪完以后 `hi` 多了，就把 `hi` 的堆顶挪回 `lo`。

```cpp
class MedianFinder {
    priority_queue<int> lo;                              // 较小的一半，大根堆
    priority_queue<int, vector<int>, greater<int>> hi;   // 较大的一半，小根堆
public:
    void addNum(int x) {
        lo.push(x);
        hi.push(lo.top()); lo.pop();
        if (hi.size() > lo.size()) { lo.push(hi.top()); hi.pop(); }
    }
    double findMedian() {
        return lo.size() > hi.size() ? lo.top() : (lo.top() + (double)hi.top()) / 2;
    }
};
```

加一个数 $O(\log n)$，查中位数 $O(1)$。

### 3.5 堆删不了中间的元素：懒删除

`priority_queue` 只能删堆顶。要删任意一个元素，比如订单簿里有人撤单，**可以先记一笔“这个值该删了”，等它浮到堆顶时再真正弹掉**：

```cpp
struct LazyMaxHeap {
    priority_queue<int> pq;
    unordered_map<int, int> dead;           // 值 → 还欠着没删的个数
    void push(int x) { pq.push(x); }
    void erase(int x) { dead[x]++; }        // 只记账，不动堆
    int top() {
        while (dead[pq.top()] > 0) { dead[pq.top()]--; pq.pop(); }   // 堆顶是该删的就真删
        return pq.top();
    }
};
```

每个元素最多被真正弹出一次，均摊下来还是 $O(\log n)$。代价是该删的元素在堆里多待一阵，堆可能比实际的元素多。

> **堆、懒删除还是 multiset**
>
> - **只取最值、只删最值**：用堆，常数最小。
> - **偶尔要删中间的元素，只关心最值**：堆加懒删除。
> - **要删任意元素，还要按顺序遍历、找前驱后继**：用 `std::multiset` 或 `std::map`（红黑树），每样操作 $O(\log n)$，常数比堆大。订单簿按价格存，一般就用 `map`。

## 练习

每题后面一句话提示练的是哪一节。

**必做**

1. [LeetCode 739 每日温度](https://leetcode.cn/problems/daily-temperatures/)：2.1 的单调栈模板。
2. [LeetCode 84 柱状图中最大的矩形](https://leetcode.cn/problems/largest-rectangle-in-histogram/)：以每根柱子为最矮，求左右边界，加哨兵。
3. [LeetCode 239 滑动窗口最大值](https://leetcode.cn/problems/sliding-window-maximum/)：单调队列，队尾扔没用的，队头扔过期的。
4. [LeetCode 23 合并 K 个升序链表](https://leetcode.cn/problems/merge-k-sorted-lists/)：多路归并，比较器方向别写反。
5. [LeetCode 295 数据流的中位数](https://leetcode.cn/problems/find-median-from-data-stream/)：两个堆，保持两条不变式。

**选做**

6. [LeetCode 20 有效的括号](https://leetcode.cn/problems/valid-parentheses/)：普通栈。
7. [LeetCode 907 子数组的最小值之和](https://leetcode.cn/problems/sum-of-subarray-minimums/)：贡献法，一边带等号、一边不带。
8. [LeetCode 215 数组中的第 K 个最大元素](https://leetcode.cn/problems/kth-largest-element-in-an-array/)：大小为 $k$ 的小根堆，或 `nth_element`。
9. [LeetCode 862 和至少为 K 的最短子数组](https://leetcode.cn/problems/shortest-subarray-with-sum-at-least-k/)：前缀和上的单调队列，有负数。

## 和地图上其他格子的连接

- 2.3 的“对每个元素求它能向两边延伸多远”，在 B3 的笛卡尔树里会变成一棵树：每个元素的左右边界就是它在树上管辖的区间。
- 堆是 A4 里 Dijkstra 的核心：每次取出当前距离最小的点，过期的条目用的就是 3.5 的懒删除。
