---
title: "A1：复杂度、二分、双指针、前缀和"
date: 2026-10-29
slug: "a1-complexity-binary-search-two-pointers-prefix-sums"
description: "数组上的四样基本功：先看数据范围定复杂度，STL 接口的坑；二分只背一种写法（找第一个为真），二分答案把求最优变成判定；双指针看窗口合法在缩小时能不能保持；前缀和把子数组和变成两数之差，差分把区间加变成改两个点。附 8 道练习题。"
weight: 1
math: true
toc: true
---
这一轮的四样东西都在数组上做查询，目标都是把暴力的 $O(n^2)$ 降下来。降得下来，靠的是两种性质：一种是单调性（二分、双指针），一种是能相减的累计量（前缀和、差分）。复杂度放在最前面，因为它决定一道题该往哪个方向想。

## 1. 复杂度：先看数据范围

### 1.1 数据范围反推复杂度

C++ 一秒大约能做 $10^8$ 次简单操作（加法、比较、数组访问）。题目给出 $n$ 的上限，能接受的复杂度也就基本定了：

| $n$ 的上限 | 能接受的复杂度 | 常见做法 |
|---|---|---|
| $20$ 左右 | $O(2^n \cdot n)$ | 枚举子集、状压 DP |
| $500$ | $O(n^3)$ | 区间 DP、Floyd |
| $5000$ | $O(n^2)$ | 二重循环的 DP |
| $2 \times 10^5$ | $O(n \log n)$ | 排序、二分、堆、线段树 |
| $10^7$ | $O(n)$ | 双指针、前缀和、线性筛 |
| $10^{18}$ | $O(\log n)$ 或 $O(\sqrt n)$ | 快速幂、二分答案、数论分块 |

比如 $n$ 到 $2 \times 10^5$，$O(n^2)$ 是 $4 \times 10^{10}$ 次，必然超时，就要往排序、二分、双指针上想。**拿到题先看 $n$：它几乎直接告诉你该用哪一类算法。** 面试也一样，面试官报出数据规模，就是在提示复杂度。

### 1.2 STL 容器的代价

| 操作 | 复杂度 | 坑 |
|---|---|---|
| `vector::push_back` | 均摊 $O(1)$ | 扩容时整体搬家；知道大小就先 `reserve` |
| `sort` | $O(n \log n)$ | 比较函数必须是严格的“小于”，写成 `<=` 会出错，甚至越界崩溃 |
| `map` / `set` 的增删查 | $O(\log n)$ | 红黑树，常数比哈希表大 |
| `unordered_map` 的增删查 | 平均 $O(1)$，最坏 $O(n)$ | Codeforces 上有人专门构造冲突数据，要换自定义哈希 |
| `priority_queue` 的 `push` / `pop` | $O(\log n)$ | 默认是大根堆 |
| `lower_bound` 用在 `vector` 上 | $O(\log n)$ | |
| `std::lower_bound` 用在 `set` 上 | $O(n)$ | `set` 的迭代器不能随机访问，要用成员函数 `s.lower_bound(x)` |

**很多超时不是算法想错了，而是用错了接口。** 除了表里 `set` 那一条，还有两个常见的：多组数据时每组都 `memset` 一个 $10^6$ 的数组，$T$ 组就是 $T \times 10^6$；输入输出量大时没关同步。读写量大的题开头加 `ios::sync_with_stdio(false); cin.tie(nullptr);`，换行用 `'\n'`，不用 `endl`（`endl` 每次都刷新缓冲区）。

## 2. 二分：在单调的判定上找边界

### 2.1 一个模板：找第一个为真的位置

二分的前提不是“数组有序”，而是判定单调：有一个判定 `pred(i)`，前面一段全为假，从某个位置起全为真，要找的是第一个为真的位置。在有序数组里找第一个 $\ge t$ 的数，只是 `pred(i) = a[i] >= t` 这一种情况。

```cpp
// 在 [lo, hi) 里找第一个让 pred 为真的位置；全为假时返回 hi
template <class Pred>
long long first_true(long long lo, long long hi, Pred pred) {
    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2;
        if (pred(mid)) hi = mid;
        else lo = mid + 1;
    }
    return lo;
}
```

它为什么对：循环里一直保持两件事，`lo` 左边全为假，`hi` 和它右边全为真（`hi` 一开始在区间外，当它为真）。`mid` 为真，第一个真在 `mid` 或它左边，于是 `hi = mid`；`mid` 为假，第一个真在 `mid` 右边，于是 `lo = mid + 1`。区间每次都缩小，缩到 `lo == hi` 时，这个位置左边全假、它自己为真，正是要找的。全为假时返回 `hi` 的初值，表示“没有”。`mid` 写成 `lo + (hi - lo) / 2`，是为了防止 `lo + hi` 溢出。

**只背这一种写法（左闭右开，找第一个真），别的问法都改写成它：**

- 第一个 $\ge t$：`pred = a[i] >= t`，就是 `lower_bound`；
- 第一个 $> t$：`pred = a[i] > t`，就是 `upper_bound`；
- 最后一个 $\le t$：第一个 $> t$ 的位置减 1；
- $t$ 出现几次：`upper_bound` 减 `lower_bound`。

### 2.2 二分答案：把“求最小”变成“判断行不行”

很多题问“最小的 $x$，使得……能做到”。如果能做到 $x$ 就一定能做到比 $x$ 大的值，那么 `pred(x) = x 能做到` 就是前面全假、后面全真，第一个真就是答案。**二分答案把求最优变成判定可行，而判定通常比直接求最优好写得多。**

例子：有 $n$ 堆香蕉，每小时吃 $k$ 根，要在 $h$ 小时内吃完，求最小的 $k$。速度越快越吃得完，判定是单调的。速度为 $k$ 时，一堆 $p$ 根要 $\lceil p / k \rceil$ 小时，加起来不超过 $h$ 就行：

```cpp
int min_speed(const vector<int>& piles, long long h) {
    auto ok = [&](long long k) {
        long long hours = 0;
        for (int p : piles) hours += (p + k - 1) / k;   // 上取整
        return hours <= h;
    };
    return first_true(1, *max_element(piles.begin(), piles.end()) + 1, ok);
}
```

速度取最大的一堆就一定吃得完，所以上界是它加 1。复杂度 $O(n \log V)$，$V$ 是最大的一堆。

认出二分答案的信号：题目问“最大值最小是多少”“最小值最大是多少”“最少需要多少”，而且给定一个答案，验证它行不行很容易。

小数上的二分不用 eps 判断结束，固定循环 100 次：每次区间减半，100 次以后精度远超需要，也不会因为浮点误差死循环。

## 3. 双指针与滑动窗口

### 3.1 什么时候左端点只往右走

枚举所有子数组是 $O(n^2)$。双指针能做到 $O(n)$，前提是：右端点往右走时，合法窗口的左端点不会往左退。这样左端点总共只走 $n$ 步，每个元素进窗口一次、出窗口一次。

这个单调性来自窗口合法性在缩小时能保持。以“窗口里没有重复字符”为例：一个窗口没有重复，它里面更小的窗口也没有。所以右端点往右扩出了重复，只需把左端点往右挪到重复消失为止；之后右端点再往右，左端点也不用回头，因为回头得到的窗口更大，只会更不合法。**判断能不能用双指针，就看窗口合法这件事在缩小时能不能保持：能保持，左端点就只往右走。**

### 3.2 两种写法：最长合法、最短合法

求最长的合法窗口：右端点每扩一格，不合法就缩左端点，缩到合法再记答案。

```cpp
// 最长的无重复字符子串
int longest_unique(const string& s) {
    int cnt[256] = {}, best = 0, l = 0;
    for (int r = 0; r < (int)s.size(); r++) {
        cnt[(unsigned char)s[r]]++;
        while (cnt[(unsigned char)s[r]] > 1) cnt[(unsigned char)s[l++]]--;
        best = max(best, r - l + 1);
    }
    return best;
}
```

求最短的合法窗口：右端点每扩一格，只要还合法，就记答案、缩左端点。

```cpp
// 和至少为 target 的最短子数组，元素都为正
int min_len(int target, const vector<int>& a) {
    int n = a.size(), best = INT_MAX, l = 0;
    long long sum = 0;
    for (int r = 0; r < n; r++) {
        sum += a[r];
        while (sum >= target) {
            best = min(best, r - l + 1);
            sum -= a[l++];
        }
    }
    return best == INT_MAX ? 0 : best;
}
```

第二段依赖元素全为正：这样窗口越大和越大，“和 $\ge$ target”在扩大时保持、在缩小时可能失去，左端点才只往右走。**数组里有负数时，窗口和不再随窗口单调，双指针会给出错的答案**，要换成前缀和加单调队列（A2 讲）。

### 3.3 另一种双指针：有序数组两头往中间夹

在有序数组里找两个数，和为 $t$：左指针在头、右指针在尾，和小了左指针右移，和大了右指针左移。这样不会漏掉答案：和大于 $t$ 时，`a[r]` 跟剩下的任何 `a[l']`（$l' \ge l$）相加只会更大，所以 `r` 可以直接扔掉；和小了同理扔掉 `l`。三数之和就是枚举第一个数，再对剩下的部分做一次两头夹，$O(n^2)$。

## 4. 前缀和与差分

### 4.1 前缀和：区间和变成两个数相减

令 $S_0 = 0$，$S_i = a_0 + a_1 + \dots + a_{i-1}$，那么区间 $[l, r)$ 的和就是 $S_r - S_l$。预处理 $O(n)$，之后每次询问 $O(1)$。$S$ 比原数组多开一位、区间用左闭右开，$l = 0$ 时就不用特判。

前缀和更大的用处，是把“子数组和”换成“两个前缀之差”，子数组问题于是变成“在前缀数组里找一对 $l < r$”的问题。以“和为 $k$ 的子数组有几个”为例：要数满足 $S_r - S_l = k$ 的对，从左往右扫 $r$，每到一个 $r$，就问前面有几个 $S_l = S_r - k$，用哈希表记每个前缀和出现的次数：

```cpp
long long count_sum_k(const vector<int>& a, long long k) {
    unordered_map<long long, long long> seen{{0, 1}};   // S_0 = 0 先放进去
    long long s = 0, ans = 0;
    for (int x : a) {
        s += x;
        if (auto it = seen.find(s - k); it != seen.end()) ans += it->second;
        seen[s]++;
    }
    return ans;
}
```

`seen` 一开始放一个 0，对应从开头开始的子数组。这里数组可以有负数，因为整个做法没有用到单调性。**有负数就用前缀和加哈希表，全为正才能用滑动窗口，这是两者的分界线。**

二维前缀和：$S_{i,j}$ 是左上角 $i$ 行 $j$ 列那块矩形的和。按容斥，

$$S_{i+1,j+1} = S_{i,j+1} + S_{i+1,j} - S_{i,j} + a_{i,j}$$

行 $[r_1, r_2)$、列 $[c_1, c_2)$ 的子矩形和是

$$S_{r_2,c_2} - S_{r_1,c_2} - S_{r_2,c_1} + S_{r_1,c_1}$$

```cpp
struct Prefix2D {
    vector<vector<long long>> S;
    Prefix2D(const vector<vector<int>>& a) {
        int n = a.size(), m = a[0].size();
        S.assign(n + 1, vector<long long>(m + 1, 0));
        for (int i = 0; i < n; i++)
            for (int j = 0; j < m; j++)
                S[i + 1][j + 1] = S[i][j + 1] + S[i + 1][j] - S[i][j] + a[i][j];
    }
    long long sum(int r1, int c1, int r2, int c2) const {   // 行 [r1, r2)、列 [c1, c2)
        return S[r2][c2] - S[r1][c2] - S[r2][c1] + S[r1][c1];
    }
};
```

### 4.2 差分：区间加变成改两个点

差分是前缀和的反操作：$d_i = a_i - a_{i-1}$（$a_{-1}$ 当作 0）。给 $[l, r)$ 里每个数都加 $v$，相邻两数的差只在两处变了：$d_l$ 多了 $v$，$d_r$ 少了 $v$。所有区间加做完，对 $d$ 求一遍前缀和，就还原出 $a$。$q$ 次区间加因此从 $O(nq)$ 降到 $O(n + q)$。

```cpp
// 每个操作 {l, r, v}：给 [l, r) 加 v
vector<long long> apply_adds(int n, const vector<array<int, 3>>& ops) {
    vector<long long> d(n + 1, 0);
    for (auto [l, r, v] : ops) {
        d[l] += v;
        d[r] -= v;
    }
    vector<long long> a(n);
    long long run = 0;
    for (int i = 0; i < n; i++) a[i] = run += d[i];
    return a;
}
```

**前缀和与差分互为逆运算：一个把点累成区间，一个把区间拆回点。** 所以选哪个看操作：区间加、最后才查，用差分；数组不变、反复查区间和，用前缀和；修改和查询穿插着来，两者都不够，要上树状数组或线段树（B1）。

二维差分同理：给一个子矩形加 $v$，改四个角，左上 $+v$、右上外侧 $-v$、左下外侧 $-v$、右下外侧 $+v$，最后做一遍二维前缀和还原。

## 练习

判对错交给 OJ。每题后面一句话提示练的是哪一节。

**必做**

1. [LeetCode 34 在排序数组中查找元素的第一个和最后一个位置](https://leetcode.cn/problems/find-first-and-last-position-of-element-in-sorted-array/)：2.1 的模板，两个边界都用“第一个为真”写。
2. [LeetCode 1011 在 D 天内送达包裹的能力](https://leetcode.cn/problems/capacity-to-ship-packages-within-d-days/)：二分答案，想清楚上下界。
3. [LeetCode 1004 最大连续 1 的个数 III](https://leetcode.cn/problems/max-consecutive-ones-iii/)：最长合法窗口，先说清楚“合法”是什么。
4. [LeetCode 974 和可被 K 整除的子数组](https://leetcode.cn/problems/subarray-sums-divisible-by-k/)：前缀和加计数，注意负数取模。
5. [LeetCode 1094 拼车](https://leetcode.cn/problems/car-pooling/)：差分。

**选做**

6. [LeetCode 410 分割数组的最大值](https://leetcode.cn/problems/split-array-largest-sum/)：“最大值最小”。
7. [LeetCode 76 最小覆盖子串](https://leetcode.cn/problems/minimum-window-substring/)：最短合法窗口，难在 $O(1)$ 判断窗口是否合法。
8. [洛谷 P3397 地毯](https://www.luogu.com.cn/problem/P3397)：二维差分。

## 和地图上其他格子的连接

- 前缀和与差分是“离散微积分”最简单的一对，地图上组合计数那一列会用到更一般的形式。
- 二分答案在数论那列还会出现：$n$ 到 $10^{18}$ 时，很多“最小的 $x$”只能二分。
- 有负数的“最短子数组和 $\ge k$”留到 A2 的单调队列。
