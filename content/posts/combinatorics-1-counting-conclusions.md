---
title: "Combinatorics #0.1: 计数中常用的结论"
date: 2026-04-20
slug: "combinatorics-1-counting-conclusions"
description: "常见计数结论、Lucas 定理、不定方程解计数、平面分拆、DAG 路径计数、多项式平移、XOR 均匀性与若干竞赛常用结论。"
summary: "常见计数结论、Lucas 定理、不定方程解计数、平面分拆、DAG 路径计数、多项式平移、XOR 均匀性与若干竞赛常用结论。"
categories: [Combinatorics]
tags: [math, combinatorics, counting, lucas, partition, xor, graph]
math: true
toc: true
---

快速幂逆元模板：

```cpp
ll qp(ll a, ll e = M - 2) {
    ll r = 1;
    while (e) {
        if (e & 1) r = r * a % M;
        a = a * a % M;
        e >>= 1;
    }
    return r;
}
```

# 1 常用

1. 长度为 $n$ 的序列，非空子区间个数为：

$$
\frac{n(n+1)}{2}
$$

例如 $n = 3$ 时：

$$
\begin{align}
[1,1], [1,2], [1,3] \\
[2,2], [2,3] \\
[3,3]
\end{align}
$$

2. 若某个连通块大小为 $s$，其内部简单路径总数（包含单点路径）为：

$$
\binom{s}{2} + s = \frac{s(s-1)}{2} + s = \frac{s(s+1)}{2}
$$

3. 把长度为 $n$ 的序列切成若干连续段的方案数为：

$$
2^{n-1}
$$

因为相邻位置之间一共 $n-1$ 个缝，每个缝都可以选择“切”或“不切”。

4. $s$ 个点组成简单无向图（允许不连通）的方案数为：

$$
2^{\binom{s}{2}}
$$

因为任意两个点之间都可以独立选择“连边”或“不连边”。

# 2 Lucas 定理

对素数 $p$，有：

$$
\binom{n}{m} \bmod p =
\binom{\left\lfloor \frac{n}{p} \right\rfloor}{\left\lfloor \frac{m}{p} \right\rfloor}
\binom{n \bmod p}{m \bmod p}
\pmod p
$$

更准确的递推式通常写成：

$$
\binom{n}{m}\bmod p =
\binom{\left\lfloor \frac{n}{p} \right\rfloor}{\left\lfloor \frac{m}{p} \right\rfloor}
\cdot \binom{n \bmod p}{m \bmod p}
\pmod p
$$

## mod 2 的推论

$$
\binom{n}{i}\bmod 2 = 1
\iff i \subseteq n
$$

也就是：

- $\binom{n}{i}$ 为奇数，当且仅当 $i$ 的二进制 1 位都是 $n$ 的子集位。
- 这是很多按位计数题的核心工具。

# 3 不定方程解的数量

相关关键词：

- 无上界：经典插板法
- 上下界：容斥、DP、生成函数
- 对称上界：可进一步合并同类项

设要求解

$$
\sum_{j=1}^{n} x_j = S
$$

且每个变量满足下界 $l_j$、上界 $u_j$。

先做统一变换：

$$
y_j = x_j - l_j \ge 0
$$

则

$$
\sum_{j=1}^{n} y_j = S', \qquad
S' = S - \sum_{j=1}^{n} l_j
$$

同时新上界变为

$$
0 \le y_j \le u'_j,\qquad u'_j = u_j - l_j
$$

## 1) 直接容斥

$$
\# =
\sum_{I \subseteq \{1,\dots,n\}}
(-1)^{|I|}
\binom{S' - \sum_{j \in I}(u'_j + 1) + n - 1}{n - 1}
$$

当括号中为负数时该项视为 $0$。

复杂度：

$$
O(2^n)
$$

最直观，但当 $n$ 稍大时就不可用。

## 2) 对称上界：所有 $u'_j = k$

此时每个大小为 $i$ 的子集贡献相同，可合并成：

$$
\sum_{i=0}^{\lfloor S'/(k+1)\rfloor}
(-1)^i
\binom{n}{i}
\binom{S' - i(k+1) + n - 1}{n - 1}
$$

复杂度约为：

$$
O\!\left(\frac{S'}{k+1}\right)
$$

再加上组合数预处理开销。

## 3) 一般上下界：推荐生成函数 / 截断卷积

答案就是多项式系数：

$$
[x^{S'}]\prod_{j=1}^{n}(1+x+\cdots+x^{u'_j})
$$

### A. 逐变量前缀和 DP

初始：

```cpp
dp[0] = 1;
```

转移时，对每个变量构造前缀和：

$$
\text{pref}[s] = \sum_{t=0}^{s} dp[t]
$$

则有：

$$
\text{new\_dp}[s] =
\text{pref}[s] -
\bigl(s-u'_j-1\ge 0 ? \text{pref}[s-u'_j-1] : 0\bigr)
$$

复杂度：

$$
O(nS')
$$

实现简单、常数小，是竞赛里最常用的版本。

### B. 分子 / 分母拆分

利用恒等式：

$$
1+x+\cdots+x^{u'_j} = \frac{1-x^{u'_j+1}}{1-x}
$$

所以

$$
\prod_j (1+x+\cdots+x^{u'_j}) =
\frac{\prod_j(1-x^{w_j})}{(1-x)^n},
\qquad w_j = u'_j+1
$$

定义

$$
\prod_j(1-x^{w_j}) = \sum_{t\ge 0} a_t x^t
$$

则

$$
[x^{S'}]\prod_j(1+x+\cdots+x^{u'_j}) =
\sum_{t=0}^{S'} a_t \binom{S'-t+n-1}{n-1}
$$

先反向 0/1 背包求 $a_t$：

```cpp
a[0] = 1;
for each w_j:
    for t = S'..w_j:
        a[t] -= a[t - w_j];
```

再做组合数加权求和。

完整代码：

```cpp
#include <bits/stdc++.h>
using namespace std;
using int64 = long long;
const int MOD = 1000000007;

int64 qp(int64 a, int64 e) {
    int64 r = 1;
    while (e) {
        if (e & 1) r = (r * a) % MOD;
        a = (a * a) % MOD;
        e >>= 1;
    }
    return r;
}

int64 invmod(int64 x) {
    return qp((x % MOD + MOD) % MOD, MOD - 2);
}

int64 comb_mod(int N, int K, const vector<int64>& fact, const vector<int64>& invfact) {
    if (K < 0 || K > N) return 0;
    return fact[N] * invfact[K] % MOD * invfact[N - K] % MOD;
}

int64 count_solutions_mod(int S, const vector<int>& l, const vector<int>& u) {
    int n = (int)l.size();
    for (int i = 0; i < n; ++i) if (u[i] < l[i]) return 0;

    long long suml = 0;
    for (int x : l) suml += x;
    long long S1 = (long long)S - suml;
    if (S1 < 0) return 0;

    vector<int> w(n);
    for (int i = 0; i < n; ++i) w[i] = u[i] - l[i] + 1;

    vector<int64> a(S1 + 1);
    a[0] = 1;
    for (int j = 0; j < n; ++j) {
        int wj = w[j];
        if (wj <= 0) continue;
        for (int t = (int)S1; t >= wj; --t) {
            a[t] = (a[t] - a[t - wj]) % MOD;
        }
    }
    for (auto& v : a) if (v < 0) v += MOD;

    int Nmax = (int)(S1 + n - 1);
    vector<int64> fact(Nmax + 1), invfact(Nmax + 1);
    fact[0] = 1;
    for (int i = 1; i <= Nmax; ++i) fact[i] = fact[i - 1] * i % MOD;
    invfact[Nmax] = invmod(fact[Nmax]);
    for (int i = Nmax; i >= 1; --i) invfact[i - 1] = invfact[i] * i % MOD;

    int64 total = 0;
    for (int t = 0; t <= S1; ++t) {
        if (a[t] == 0) continue;
        int N = (int)(S1 - t + n - 1);
        int K = n - 1;
        int64 c = comb_mod(N, K, fact, invfact);
        total = (total + a[t] * c) % MOD;
    }
    if (total < 0) total += MOD;
    return total;
}

int main() {
    int S = 10;
    vector<int> l = {0, 1, 0};
    vector<int> u = {5, 4, 6};
    cout << count_solutions_mod(S, l, u) << "\n";
    return 0;
}
```

# 4 分拆计数（平面分拆）

例题模型：`Monotonic Matrix`

题意等价于求满足以下条件的矩阵个数：

- $A_{i,j}\in\{0,1,2\}$
- 行方向单调
- 列方向单调

## 4.1 普通分拆

整数分拆（integer partition）是把一个正整数拆成若干个非增正整数之和，例如：

$$
5 = 3+2 = 2+2+1 = 5
$$

通常可用 Ferrers 图表示。

## 4.2 平面分拆

平面分拆是分拆的二维推广：一个矩阵 $(a_{i,j})$ 满足

$$
a_{i,j} \ge a_{i,j+1},\qquad
a_{i,j} \ge a_{i+1,j},\qquad
a_{i,j}\ge 0
$$

也就是行列都非增。可以把 $a_{i,j}$ 看成该位置堆叠的小立方体高度，于是平面分拆对应一个三维堆积模型。

## 4.3 盒子里的平面分拆

若限制：

- 行数 $\le n$
- 列数 $\le m$
- 高度 $\le k$

那么就得到“装在 $n\times m\times k$ 盒子里的平面分拆”。

## 4.4 MacMahon 盒子公式

装在 $a\times b\times c$ 盒子里的平面分拆个数为：

$$
\prod_{i=1}^{a}\prod_{j=1}^{b}\prod_{k=1}^{c}
\frac{i+j+k-1}{i+j+k-2}
$$

## 4.5 对应原题

题目要求 $A_{i,j}\in\{0,1,2\}$ 且行列单调不减。

如果把数值看作高度，那么这正好对应装在一个 $n\times m\times 2$ 盒子里的平面分拆。

因此答案就是：

$$ \prod_{i=1}^{n}\prod_{j=1}^{m}\prod_{k=1}^{2}\frac{i+j+k-1}{i+j+k-2} = \prod_{i=1}^{n}\prod_{j=1}^{m}\frac{i+j+1}{i+j-1} $$

进一步可化简为封闭式：

$f(n,m) = \frac{\binom{n+m}{n}\binom{n+m+1}{n}}{n+1} = \frac{\binom{n+m}{m}\binom{n+m+1}{m}}{m+1}$。

# 5 $u\to v$ 路径数量怎么求

这里区分两个概念：

- `walk`：允许重复顶点
- `simple path`：不允许重复顶点

一些关键结论：

- 若图中存在从 $u$ 到 $v$ 的可达环，那么 `walk` 的数量可能是无限。
- 一般有向图上计数 simple paths 是 `#P-complete`，通常没有多项式做法。
- 但在 DAG 上，simple paths 数量可以用拓扑 DP 在线性时间内求出。

## 5.1 图是 DAG 时

复杂度：

$$
O(n+m)
$$

代码：

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

ll count_paths_in_dag(int n, const vector<vector<int>>& g, int s, int t, ll MOD) {
    vector<int> indeg(n, 0);
    for (int u = 0; u < n; ++u)
        for (int v : g[u]) indeg[v]++;

    queue<int> q;
    for (int i = 0; i < n; ++i)
        if (indeg[i] == 0) q.push(i);

    vector<int> topo;
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        topo.push_back(u);
        for (int v : g[u])
            if (--indeg[v] == 0) q.push(v);
    }

    vector<ll> dp(n, 0);
    dp[s] = 1 % MOD;

    for (int u : topo) {
        if (dp[u] == 0) continue;
        for (int v : g[u]) {
            dp[v] += dp[u];
            if (dp[v] >= MOD) dp[v] -= MOD;
        }
    }
    return dp[t];
}
```

## 5.2 一般有向图：先 SCC 压缩

做法：

1. 用 Tarjan / Kosaraju 找 SCC。
2. 构造压缩后的 condensation DAG。
3. 判断从 `comp(u)` 到 `comp(v)` 的路径上是否经过“有环 SCC”。
4. 若路径上无环成分，则在压缩 DAG 上做 DP。

如果路径上存在有环 SCC：

- 若计数 `walk`，通常意味着答案无限。
- 若计数 `simple path`，问题通常已经回到困难问题。

# 6 多项式平移 / 连续点值平移

## 6.1 模素数意义下二项式前缀和

问题：

$$
\sum_{i=0}^{m}\binom{n}{i}\bmod 998244353,
\qquad
0\le m\le n\le 9\times 10^8
$$

这类题可用多项式平移 / 连续点值平移做到：

$$
O(\sqrt m \log m)
$$

参考：<https://oi-wiki.org/math/poly/shift/>

代码如下：

```cpp
#include <bits/stdc++.h>
using namespace std;

const int P = 998244353;

namespace ModInt {
    inline int add(int x, int y) { return x + y >= P ? x + y - P : x + y; }
    inline int sub(int x, int y) { return x < y ? x - y + P : x - y; }
    inline int mul(int x, int y) { return 1ll * x * y % P; }
    inline int Pow(int x, int y) {
        int r = 1;
        for (; y; y >>= 1, x = mul(x, x)) if (y & 1) r = mul(r, x);
        return r;
    }
    inline int inv(int x) { return Pow(x, P - 2); }
}
using namespace ModInt;

namespace POLY {
    using Poly = vector<int>;

    Poly G[19];
    void Prework() {
        for (int k = 0; k < 19; ++k) {
            G[k] = Poly(1 << k, 1);
            const int x = Pow(3, P >> k + 1);
            for (int i = 1; i < (int)G[k].size(); ++i) G[k][i] = mul(G[k][i - 1], x);
        }
    }

    int r[1 << 22], l;
    void Getlen(int n) {
        l = 1;
        while (l < n) l <<= 1;
        for (int i = 1; i < l; ++i) {
            r[i] = r[i >> 1] >> 1;
            if (i & 1) r[i] |= (l >> 1);
        }
    }

    void Dft(Poly& F, int tp) {
        F.resize(l);
        for (int i = 0; i < l; ++i) if (i < r[i]) swap(F[i], F[r[i]]);
        for (int i = 1, o = 0; i < l; i <<= 1, ++o) {
            for (int j = 0; j < l; j += (i << 1)) {
                for (int k = 0; k < i; ++k) {
                    int x = F[j + k], y = mul(G[o][k], F[i + j + k]);
                    F[j + k] = add(x, y);
                    F[i + j + k] = sub(x, y);
                }
            }
        }
        if (tp == -1) {
            reverse(F.begin() + 1, F.end());
            const int x = inv(l);
            for (int i = 0; i < l; ++i) F[i] = mul(F[i], x);
        }
    }

    Poly operator*(Poly x, Poly y) {
        int tx = x.size(), ty = y.size();
        if (tx <= 50 && ty <= 50) {
            Poly ret(tx + ty - 1);
            for (int i = 0; i < tx; ++i) {
                for (int j = 0; j < ty; ++j) {
                    ret[i + j] = (ret[i + j] + 1ll * x[i] * y[j]) % P;
                }
            }
            return ret;
        }
        Getlen(tx + ty);
        Dft(x, 1);
        Dft(y, 1);
        for (int i = 0; i < l; ++i) x[i] = mul(x[i], y[i]);
        Dft(x, -1);
        x.resize(tx + ty - 1);
        return x;
    }
}
using namespace POLY;

const int N = 1e5 + 10;

int fac[N], ifac[N];
void init(int n) {
    fac[0] = 1;
    for (int i = 1; i <= n; ++i) fac[i] = mul(fac[i - 1], i);
    ifac[n] = inv(fac[n]);
    for (int i = n; i; --i) ifac[i - 1] = mul(ifac[i], i);
}

Poly Inv(const Poly& F) {
    int n = F.size();
    Poly mut(n + 1, 1), G(n);
    for (int i = 0; i < n; ++i) mut[i + 1] = mul(mut[i], F[i]);
    int x = inv(mut[n]);
    for (int i = n - 1, t = 1; ~i; t = mul(t, F[i]), --i) {
        G[i] = mul(mul(mut[i], t), x);
    }
    return G;
}

Poly Inter(Poly F, int c) {
    int n = F.size() - 1;
    for (int i = 0; i <= n; ++i) {
        F[i] = mul(F[i], mul(ifac[i], ifac[n - i]));
        if ((n - i) & 1) F[i] = P - F[i];
    }
    Poly G(2 * n + 1);
    for (int i = 0; i <= 2 * n; ++i) {
        G[i] = i - n + c;
        if (G[i] < 0) G[i] += P;
    }
    G = Inv(G);

    F = F * G;
    int t = 1;
    for (int i = 0; i <= n; ++i) t = mul(t, sub(c, i));
    for (int i = 0; i <= n; ++i) {
        F[i] = mul(F[i + n], t);
        t = mul(t, mul(c + i + 1, G[i]));
    }
    F.resize(n + 1);
    return F;
}

int n, m;
void solve() {
    cin >> n >> m;

    if (n == 1) {
        cout << m + 1 << endl;
        return;
    }

    int B = sqrt(m);
    while (B * (B + 1) > m) B--;

    int ans = 0, r = m - B * (B + 1), t = 1;
    for (int i = 0; i <= r; ++i) {
        if (i) t = mul(t, n - i + 1);
        ans = add(ans, mul(ifac[i], t));
    }
    t = mul(t, ifac[r]);

    auto merge = [&](Poly& F, Poly G) {
        for (auto x : G) F.push_back(x);
    };
    Poly F{r + 1, r + B + 1}, G{n - r, n - r - B}, H{n - r, n - r - B};
    int inv_B = inv(B);
    for (int k = __lg(B) - 1; ~k; --k) {
        int d(B >> k);
        merge(F, Inter(F, (d >> 1) + 1));
        merge(G, Inter(G, (d >> 1) + 1));
        merge(H, Inter(H, (d >> 1) + 1));
        Poly F0 = Inter(F, mul(d >> 1, inv_B));
        Poly G0 = Inter(G, mul(d >> 1, inv_B));
        Poly H0 = Inter(H, mul(d >> 1, inv_B));
        for (int i = 0; i < (int)F.size(); ++i) {
            H[i] = add(mul(G[i], H0[i]), mul(H[i], F0[i]));
            F[i] = mul(F[i], F0[i]);
            G[i] = mul(G[i], G0[i]);
        }
        if (d & 1) {
            for (int i = 0; i < (int)F.size(); ++i) {
                H[i] = add(mul(G[i], n - r - i * B - d + 1), mul(H[i], r + i * B + d));
                G[i] = mul(G[i], n - r - i * B - d + 1);
                F[i] = mul(F[i], r + i * B + d);
            }
        } else {
            F.pop_back();
            G.pop_back();
            H.pop_back();
        }
    }

    F = Inv(F);
    for (int i = 0; i < (int)F.size(); t = mul(t, mul(F[i], G[i])), ++i) {
        ans = add(ans, mul(mul(F[i], H[i]), t));
    }
    cout << ans << endl;
}

int main() {
    init(100000);
    Prework();

    int T;
    cin >> T;
    while (T--) solve();
}
```

# 7 XOR 的均匀性结论

把数看成向量空间 $\mathbb{F}_2^m$ 中的元素。若 $X_1,\dots,X_t$ 独立且均匀分布在 $\{0,\dots,2^m-1\}$ 上，令 $k = 2^m$，则

$$
S = X_1 \oplus \cdots \oplus X_t
$$

在整个空间上仍然均匀分布。也就是说，对任意 $y$ 都有：

$$
\Pr[S = y] = \frac{1}{k}
$$

对应的计数版结论：

满足

$$
x_1 \oplus \cdots \oplus x_t = y
$$

的 $t$ 元组一共有

$$
k^{t-1}
$$

个。因为前 $t-1$ 个可以任取，最后一个被唯一确定。

# 8 一些竞赛中的常见结论

## 8.1 中位数聚段：把相同值的 $k$ 个出现挪成一段的最小相邻交换数

设某个值在原数组中的下标（0-based）为：

$$
p_0 < p_1 < \cdots < p_{k-1}
$$

令

$$
q_i = p_i - i
$$

取 $q$ 的中位数 $m = \mathrm{median}(q_0,\dots,q_{k-1})$，则把这 $k$ 个元素挪到一段所需的最小相邻交换次数为：

$$
\sum_{i=0}^{k-1} |q_i - m|
$$

最优目标段为：

$$
[t, t+k-1], \qquad t = m
$$

证明非常直接：

$$
\sum_{i=0}^{k-1} |p_i - (t+i)| =
\sum_{i=0}^{k-1} |(p_i-i)-t|
$$

这是一个对 $t$ 的 L1 最优化问题，因此最优解由中位数给出。

典型应用：

- 只有两种数，把同类元素聚在一起
- 统计若干相同颜色聚成块的最少交换次数

## 8.2 多种颜色都要各自聚成连续块：子集 DP / SOS DP

题意模型：

- 给定长度 $n$ 的颜色序列
- 颜色种类数 $\le 20$
- 允许相邻交换，代价为交换次数
- 要求每种颜色最终都变成一段连续块
- 块的相对顺序任意

### 关键结论

若最终块顺序为 $\pi=[T_1,\dots,T_k]$，定义

$$
\mathrm{cnt}[i][j] = \text{原串中 “i 在 j 前” 的对数}
$$

则该顺序的最小相邻交换次数为：

$$
\boxed{
\mathrm{cost}(\pi) =
\sum_{1 \le s < t \le k}\mathrm{cnt}[\pi_t][\pi_s]
}
$$

原因是：每一对“后块元素站在前块元素前面”的逆序对，至少要被交换一次，而一次相邻交换最多修正一对。

### 子集 DP 形式

令：

$$
h[S] = \text{把集合 } S \text{ 内颜色排到左侧的最小代价}
$$

把最后放到最右端的颜色记为 $c \in S$，则新增代价为：

$$
W^{(c)}[S\setminus\{c\}] =
\sum_{i\in S\setminus\{c\}} \mathrm{cnt}[c][i]
$$

于是：

$$
h[S] =
\min_{c\in S}
\left(
h[S\setminus\{c\}] + W^{(c)}[S\setminus\{c\}]
\right)
$$

复杂度：

$$
O(nk + k2^k)
$$

代码：

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;
    vector<int> a(n);
    for (int i = 0; i < n; ++i) cin >> a[i];

    vector<int> id(21, -1);
    int k = 0;
    for (int x : a) if (id[x] == -1) id[x] = k++;
    for (int& x : a) x = id[x];

    if (k <= 1) {
        cout << 0 << "\n";
        return 0;
    }

    vector<vector<ll>> cnt(k, vector<ll>(k, 0));
    vector<ll> seen(k, 0);
    for (int x : a) {
        for (int y = 0; y < k; ++y) if (y != x) {
            cnt[y][x] += seen[y];
        }
        seen[x]++;
    }

    int N = 1 << k;
    vector<vector<ll>> add(k, vector<ll>(N, 0));
    for (int c = 0; c < k; ++c) {
        for (int S = 1; S < N; ++S) {
            int i = __builtin_ctz(S);
            add[c][S] = add[c][S ^ (1 << i)] + cnt[c][i];
        }
    }

    const ll INF = (1LL << 62);
    vector<ll> dp(N, INF);
    dp[0] = 0;
    for (int S = 1; S < N; ++S) {
        for (int c = 0; c < k; ++c) if ((S >> c) & 1) {
            int T = S ^ (1 << c);
            dp[S] = min(dp[S], dp[T] + add[c][T]);
        }
    }

    cout << dp[N - 1] << "\n";
    return 0;
}
```
