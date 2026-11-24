---
title: "L2：高斯消元"
date: 2026-11-24
slug: "l2-gaussian-elimination"
aliases: ["/algo/l3-gaussian-elimination/"]
description: "高斯消元用不改变解集的行变换把方程组化成简化行阶梯形，再读出无解、唯一解或自由元。实数下选绝对值最大的主元（P2455 分类、P3232 期望有环）；模质数下除法换成乘逆元（P4783 矩阵求逆、行列式）；模 2 下加减都是异或，一行存成 bitset（POJ 1222 开关灯、CF 1344F 颜色看成 GF(2) 向量）；增量高斯一条一条加方程，线性基是它的特例（2024 昆明 E 交互题）。附分步动画和 6 道练习。"
weight: 16
math: true
toc: true
---
> 高斯消元的本质：用不改变解集的行变换，把方程组化成一眼能读出解的形状。

期望有环、开关灯、异或约束、矩阵求逆、行列式，列出来都是线性方程组，用的是同一个算法，只是加减乘除的规则不同。[L1](/zh/algo/l1-linear-algebra/) 讲了解方程的结论从哪来（像和核），这一篇讲怎么消、在哪些题里用：消元本身（第 1 节）、三种数域各改哪几行（第 2 到 4 节）、一条一条加方程的增量版本（第 5 节）。每一节后面跟一道例题。

## 1. 消元在做什么

### 1.1 三种行变换不改变解集

$n$ 个方程、$m$ 个未知数，写成 $n$ 行 $m + 1$ 列的**增广矩阵**：前 $m$ 列是系数，最后一列是右端。消元只用三种**行变换**：

- 交换两行；
- 一行乘一个非零数；
- 一行加上另一行的若干倍。

每种都能撤回：换回来、乘倒数、减回去，撤回的操作也是行变换。所以原方程组的解满足变换后的方程组，反过来也成立，**行变换前后两组方程同解**。列不能随便动，因为一列对应一个未知数。

### 1.2 一列一列消，消完读结果

从第 0 列开始，维护“当前行” $r$（一开始是 0）：

1. 在第 $r$ 行及以下找这一列非零的一行作**主元**，换到第 $r$ 行；
2. 把第 $r$ 行除以主元，主元变成 1；
3. 用第 $r$ 行把其余所有行这一列消成 0；
4. 记下“第 $c$ 列的主元在第 $r$ 行”，$r$ 加 1，处理下一列。

第 1 步找不到主元，说明这个未知数没有被任何一行“管住”，它是**自由元**，可以任取。这时 $r$ 不动，直接看下一列。

上下都消（第 3 步消“其余所有行”，不只是下面的行）的写法叫高斯–约当消元，消完是**简化行阶梯形**：每个主元列只有主元那一个 1。这样不用回代，主元所在行的右端就是那个未知数的值。

消完从第 $r$ 行往下全是系数全 0 的行，读结果按这个顺序：

1. 某一行系数全 0、右端不是 0，写出来是 $0 = $ 非零，**无解**；
2. 否则，没有自由元（$r = m$）就是**唯一解**；
3. 否则有自由元，**解不唯一**。模 $p$ 下解的个数是 $p^{m - r}$，模 2 下是 $2^{m - r}$；实数下有无穷多个。

**先查无解，再查自由元**：一个方程组可以同时有自由元和矛盾的行，这时答案是无解。

下面的动画分步走一遍，有三组方程：唯一解、有自由元、无解。每一步标出当前列、主元和被消的行。

<iframe src="/maps/gauss-steps.zh.html" title="高斯消元：分步看" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:500px;overflow:hidden;margin:1.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/gauss-steps.zh.html" target="_blank" rel="noopener">在新窗口打开</a></p>

## 2. 实数：选绝对值最大的主元

### 2.1 主元太小，误差会被放大

实数在计算机里有舍入误差。主元很小时，第 2 步除以它会把这一行放大很多倍，别的数的误差也跟着放大。

例：$10^{-20} x + y = 1$，$x + y = 2$，真解约是 $x = 1$、$y = 1$。

- 用第一行的 $10^{-20}$ 作主元：第二行减去第一行的 $10^{20}$ 倍，$y$ 的系数是 $1 - 10^{20}$，double 只有约 16 位有效数字，这里算出来就是 $-10^{20}$，右端也一样只剩 $-10^{20}$，得 $y = 1$；代回第一行，$10^{-20} x = 1 - 1 = 0$，$x = 0$，错了。
- 先交换，用第二行的 1 作主元：第一行减去第二行的 $10^{-20}$ 倍，系数和右端都几乎不变，得 $y = 1$、$x = 1$，对了。

所以实数消元**每列都选绝对值最大的那一行作主元**（列主元），判断“是不是 0”用 $|x| < \varepsilon$，不能用 `== 0`。

#### 复杂度

$O(n \cdot m \cdot w)$：$n$ 行、消 $m$ 列、每行 $w$ 列（一个右端时 $w = m + 1$），方阵就是 $O(n^3)$，$n = 500$ 左右是上限。每处理一列，要把整个矩阵的每一行都消一遍。

#### 模板（实数）

```cpp
#include <bits/stdc++.h>
using namespace std;

const double EPS = 1e-8;

// 高斯–约当消元（实数）：a 有 n 行，消前 m 列，后面的列是右端（可以不止一列），跟着一起变
// 返回 -1：无解；否则返回秩 r，r == m 是唯一解，r < m 有自由元
// where[c]：第 c 个未知数的主元在哪一行，-1 表示自由元；有解时 x_c = a[where[c]][m]，自由元取 0
int gauss(vector<vector<double>>& a, int m, vector<int>& where) {
    int n = a.size(), w = n ? a[0].size() : 0, r = 0;
    where.assign(m, -1);
    for (int c = 0; c < m && r < n; c++) {
        int p = r;
        for (int i = r; i < n; i++)
            if (fabs(a[i][c]) > fabs(a[p][c])) p = i;    // 选绝对值最大的主元
        if (fabs(a[p][c]) < EPS) continue;               // 这一列没有主元：x_c 是自由元，r 不动
        swap(a[p], a[r]);
        for (int j = w - 1; j >= c; j--) a[r][j] /= a[r][c];
        for (int i = 0; i < n; i++)
            if (i != r && fabs(a[i][c]) > EPS)
                for (int j = w - 1; j >= c; j--) a[i][j] -= a[i][c] * a[r][j];
        where[c] = r++;
    }
    for (int i = r; i < n; i++)
        for (int j = m; j < w; j++)
            if (fabs(a[i][j]) > EPS) return -1;          // 0 = 非零：先查无解，再看自由元
    return r;
}
```

返回值先看是不是 $-1$（无解），再看秩是不是 $m$（唯一解）。这是 1.2 读结果的顺序：一个方程组可以同时有自由元和矛盾的行，这时答案是无解。

### 2.2 例：洛谷 P2455 线性方程组，区分无解和无穷多解

题（[洛谷 P2455](https://www.luogu.com.cn/problem/P2455)，SDOI2006）：$n \le 50$ 元一次方程组，系数是整数。唯一解就输出每个 $x_i$，保留 2 位小数；无解输出 $-1$；有无穷多解输出 $0$。

这题就是 1.2 的读结果，难点在顺序：某一列没有主元时**不能马上判“无穷多解”**，要接着消完，再先查 $0 = $ 非零的行。比如 $x + y = 1$、$x + y = 2$：第 1 列消完，第二行变成 $0 = 1$；第 2 列找不到主元，$y$ 看上去是自由元，但答案是 $-1$。

```cpp
#include <bits/stdc++.h>
using namespace std;

// 套 2.1 的 gauss（实数）

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<vector<double>> a(n, vector<double>(n + 1));   // 增广矩阵，第 n 列是右端
    for (auto& row : a)
        for (auto& v : row) cin >> v;

    vector<int> where;
    int r = gauss(a, n, where);
    if (r < 0) { cout << -1 << '\n'; return 0; }
    if (r < n) { cout << 0 << '\n'; return 0; }

    cout << fixed << setprecision(2);
    for (int c = 0; c < n; c++)
        cout << 'x' << c + 1 << '=' << (fabs(a[where[c]][n]) < 0.005 ? 0.0 : a[where[c]][n]) << '\n';
}
```

`a[i][c]` 在内层循环里会被改，所以 `j` 从右往左扫，第 `c` 列最后改，前面用到的都是旧值。输出前把绝对值很小的数当成 0，避免打印出 `-0.00`。复杂度 $O(n^3)$，$n \le 50$。

### 2.3 例：洛谷 P3232 游走，期望里有环

题（[洛谷 P3232](https://www.luogu.com.cn/problem/P3232)，HNOI2013）：无向连通图 $n \le 500$ 个点、$m \le 125000$ 条边。从 1 号点出发，每步等概率走一条相邻的边，走到 $n$ 号点停下，得分是走过的边的编号之和（走几次加几次）。给边编号 $1 \sim m$，使期望得分最小，输出最小值，保留 3 位小数。

**先算每条边期望被走几次。** 边太多，不能对边列方程，先对点列。设 $f_u$ 是到达 $n$ 之前经过点 $u$ 的期望次数（$u \ne n$）。每次经过 $v$，下一步走向某个邻居的概率是 $1 / \deg v$，所以

$$
f_u = [u = 1] + \sum_{v \sim u,\ v \ne n} \frac{f_v}{\deg v}.
$$

第一项是出发时就在 1 号点；$v = n$ 时已经停下，不会再出发。$u$ 的期望次数依赖邻居，邻居又依赖 $u$，有环，不能按顺序推，只能列 $n - 1$ 个方程一起解。

边 $(u, v)$ 被走的期望次数是从 $u$ 出发选中它加上从 $v$ 出发选中它：$\dfrac{f_u}{\deg u} + \dfrac{f_v}{\deg v}$，端点是 $n$ 的那一项不算。

**再分配编号。** 期望得分 $= \sum_e (\text{编号}_e \times \text{期望次数}_e)$。排序不等式：大的配小的乘积和最小，所以走得最多的边给编号 1，依次往下。

```cpp
#include <bits/stdc++.h>
using namespace std;

// 套 2.1 的 gauss（实数）

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, m;
    cin >> n >> m;
    vector<int> eu(m), ev(m), deg(n + 1, 0);
    vector<vector<int>> g(n + 1);
    for (int i = 0; i < m; i++) {
        cin >> eu[i] >> ev[i];
        deg[eu[i]]++, deg[ev[i]]++;
        g[eu[i]].push_back(ev[i]);
        g[ev[i]].push_back(eu[i]);
    }

    // 未知数 f_1..f_{n-1}：到达 n 之前经过点 u 的期望次数
    // f_u - sum_{v ~ u, v != n} f_v / deg_v = [u == 1]
    int k = n - 1;
    vector<vector<double>> a(k, vector<double>(k + 1, 0));
    for (int u = 1; u < n; u++) {
        a[u - 1][u - 1] += 1;
        for (int v : g[u])
            if (v != n) a[u - 1][v - 1] -= 1.0 / deg[v];
        a[u - 1][k] = (u == 1);
    }
    vector<int> where;
    gauss(a, k, where);                                    // 解唯一，每列都有主元，where[c] == c

    // 边 (u, v) 被走的期望次数：从 u 出发选中它，加上从 v 出发选中它；到了 n 就停
    vector<double> e(m);
    for (int i = 0; i < m; i++)
        e[i] = (eu[i] != n ? a[eu[i] - 1][k] / deg[eu[i]] : 0) + (ev[i] != n ? a[ev[i] - 1][k] / deg[ev[i]] : 0);
    sort(e.rbegin(), e.rend());                            // 走得越多的边，编号越小
    double ans = 0;
    for (int i = 0; i < m; i++) ans += e[i] * (i + 1);
    cout << fixed << setprecision(3) << ans << '\n';
}
```

这题解一定唯一（从 1 出发每个点的期望次数是确定的），代码里省掉了无解和自由元的判断。复杂度：对 $n - 1$ 个点消元 $O(n^3)$，$n = 500$ 约 $1.25 \times 10^8$；再给 $m$ 条边排序 $O(m \log m)$。

## 3. 模质数：除法换成乘逆元

### 3.1 只改两处

模质数 $p$ 下数是精确的，没有误差，消元框架完全一样，只改两处：

- 找主元时**只要非零就行**，不用选最大；
- 除以主元换成**乘它的逆元**（快速幂求 $a^{p-2}$）。

非零的数在模质数下都有逆元，所以第 2 步总能做。模数不是质数时，非零的主元可能没有逆元，要换成两行之间辗转相除的消法，见练习 6。

#### 复杂度

$O(n \cdot m \cdot w + r \log p)$：消元部分和实数一样，另外每个主元求一次逆元（快速幂 $O(\log p)$），$r$ 是秩。方阵就是 $O(n^3 + n \log p)$。

#### 模板（模质数）

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

const ll P = 1e9 + 7;

ll qp(ll a, ll e) {
    ll r = 1;
    for (a %= P; e; e >>= 1, a = a * a % P)
        if (e & 1) r = r * a % P;
    return r;
}

// 高斯–约当消元（模质数 P）：a 有 n 行，消前 m 列，后面的列是右端（可以不止一列），跟着一起变
// 返回值和 where 的含义同实数版：-1 无解，否则返回秩
int gauss(vector<vector<ll>>& a, int m, vector<int>& where) {
    int n = a.size(), w = n ? a[0].size() : 0, r = 0;
    where.assign(m, -1);
    for (int c = 0; c < m && r < n; c++) {
        int p = r;
        while (p < n && a[p][c] == 0) p++;               // 模 p 下只要非零就能当主元
        if (p == n) continue;
        swap(a[p], a[r]);
        ll iv = qp(a[r][c], P - 2);                      // 除以主元换成乘逆元
        for (int j = c; j < w; j++) a[r][j] = a[r][j] * iv % P;
        for (int i = 0; i < n; i++)
            if (i != r && a[i][c]) {
                ll f = a[i][c];
                for (int j = c; j < w; j++) a[i][j] = (a[i][j] - f * a[r][j] % P + P) % P;
            }
        where[c] = r++;
    }
    for (int i = r; i < n; i++)
        for (int j = m; j < w; j++)
            if (a[i][j]) return -1;
    return r;
}
```

### 3.2 例：洛谷 P4783 矩阵求逆

题（[洛谷 P4783](https://www.luogu.com.cn/problem/P4783)）：$N \le 400$ 的方阵，求它模 $10^9 + 7$ 的逆矩阵；不可逆输出 `No Solution`。

把 $A$ 和单位阵 $I$ 并排写成 $[A \mid I]$，对整个 $n \times 2n$ 矩阵做消元，把左半边消成 $I$，右半边就是 $A^{-1}$。

为什么：每个行变换都等于左乘一个可逆矩阵，一串行变换合起来是左乘某个矩阵 $E$。左半边从 $A$ 变成 $I$，说明 $EA = I$，所以 $E = A^{-1}$；右半边从 $I$ 变成 $EI = E$，正好是 $A^{-1}$。左半边某一列找不到主元，$A$ 的秩不满，不可逆。

```cpp
#include <bits/stdc++.h>
using namespace std;
// 套 3.1 的 gauss（模质数，P 和 qp 也在里面）

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<vector<ll>> a(n, vector<ll>(2 * n, 0));       // [A | I]
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) cin >> a[i][j];
        a[i][n + i] = 1;
    }
    vector<int> where;
    if (gauss(a, n, where) != n) { cout << "No Solution\n"; return 0; }   // 左半边消不成 I
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) cout << a[i][n + j] << " \n"[j == n - 1];
}
```

对 $n \times 2n$ 的矩阵消元，约 $2 n^3$ 次乘法，$n = 400$ 时约 $1.3 \times 10^8$。

### 3.3 行列式：只消下面，乘对角线

三种行变换对行列式的影响：交换两行变号；一行乘 $k$，行列式乘 $k$；一行加上另一行的倍数，行列式不变。所以只用第三种变换（再加交换）把矩阵消成上三角，行列式就是对角线乘积，每交换一次变一次号。这时不用把主元除成 1，也不用消上面的行。模质数的代码和矩阵树定理、LGV 引理在 [C0 第 4.6 节](/zh/algo/c0-contest-math-overview/)。只消下面约 $n^3 / 3$ 次乘法，加上求逆元，共 $O(n^3 + n \log p)$。

## 4. 模 2：加减都是异或

### 4.1 一行存成 bitset

GF(2) 上只有 0 和 1，$1 + 1 = 0$，加法和减法都是异或；主元一定是 1，不用除。消元的第 3 步“第 $i$ 行减去第 $r$ 行的若干倍”只剩一种情况：第 $i$ 行这一列是 1，就整行异或上第 $r$ 行。

#### 复杂度

$O(n \cdot m \cdot (m + 1) / 64)$，方阵就是 $O(n^3 / 64)$，$n$ 到 2000 也能跑。把一行存成 `bitset`，一整行的异或一次处理 64 位，所以比实数版少一个 64 的因子。

#### 模板（模 2）

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MV = 2000;                             // MV = max variables，未知数个数的上限；bitset 的长度要在编译时定下，所以是常量

// 高斯–约当消元（模 2）：每行是一个 bitset，前 m 位是系数，第 m 位是右端
// 返回值和 where 的含义同实数版：-1 无解，否则返回秩；有解时 x_c = a[where[c]][m]
int gauss(vector<bitset<MV + 1>>& a, int m, vector<int>& where) {
    int n = a.size(), r = 0;
    where.assign(m, -1);
    for (int c = 0; c < m && r < n; c++) {
        int p = r;
        while (p < n && !a[p][c]) p++;
        if (p == n) continue;
        swap(a[p], a[r]);
        for (int i = 0; i < n; i++)
            if (i != r && a[i][c]) a[i] ^= a[r];         // 整行异或，bitset 一次处理 64 位
        where[c] = r++;
    }
    for (int i = r; i < n; i++)
        if (a[i][m]) return -1;                          // 0 = 1
    return r;
}
```

### 4.2 例：POJ 1222 开关灯

题（[POJ 1222](http://poj.org/problem?id=1222) EXTENDED LIGHTS OUT）：5 行 6 列的灯，每个位置有一个开关，按一下会翻转它自己和上下左右的灯。给出初始哪些灯亮，求按哪些开关能让所有灯熄灭，输出一个 5×6 的 0/1 表。数据保证有解。

**为什么是模 2 的方程组。** 按开关的顺序无所谓（翻转可以交换），按两次等于没按，所以每个开关只需要决定按或不按，设成 $x \in \{0, 1\}$。一盏灯最后熄灭，当且仅当它被翻转的次数和它一开始亮不亮奇偶相同：

$$
x_{\text{自己}} \oplus x_{\text{上}} \oplus x_{\text{下}} \oplus x_{\text{左}} \oplus x_{\text{右}} = \text{初始状态}.
$$

30 盏灯 30 个方程，30 个开关 30 个未知数。系数矩阵 $A$ 的第 $c$ 列是“按开关 $c$ 翻转哪些灯”，第 $r$ 行是“哪些开关会翻转灯 $r$”，两者都是十字形。

<a href="/images/algo/lights-out-matrix.zh.svg" target="_blank" rel="noopener"><img src="/images/algo/lights-out-matrix.zh.svg" alt="开关灯的系数矩阵：左图按开关 (2,3) 翻转十字形的 5 盏灯，是 A 的第 9 列；中图灯 (1,1) 只被 3 个开关翻转，方程是 x(1,1) ⊕ x(1,2) ⊕ x(2,1) = 初始状态，是 A 的第 1 行；右图是整个 30×30 的 A，行是灯、列是开关，1 沿着几条对角线分布，标出了第 9 列和第 1 行。" style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

```cpp
#include <bits/stdc++.h>
using namespace std;

// 套 4.1 的 gauss（模 2）

const int R = 5, C = 6, V = R * C;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int T;
    cin >> T;
    for (int t = 1; t <= T; t++) {
        // 第 r 行方程：灯 r 被翻转的次数之和 ≡ 它一开始亮不亮 (mod 2)
        // 第 c 列：按开关 c 会翻转哪些灯；第 V 列是右端
        vector<bitset<MV + 1>> a(V);
        for (int i = 0; i < R; i++)
            for (int j = 0; j < C; j++) {
                int s;
                cin >> s;
                a[i * C + j][V] = s;
            }
        int dx[5] = {0, 1, -1, 0, 0}, dy[5] = {0, 0, 0, 1, -1};
        for (int i = 0; i < R; i++)
            for (int j = 0; j < C; j++)
                for (int d = 0; d < 5; d++) {
                    int x = i + dx[d], y = j + dy[d];
                    if (x >= 0 && x < R && y >= 0 && y < C) a[x * C + y][i * C + j] = 1;
                }

        vector<int> where;
        gauss(a, V, where);                                // 题目保证有解，满秩

        cout << "PUZZLE #" << t << '\n';
        for (int i = 0; i < R; i++)
            for (int j = 0; j < C; j++)
                cout << (where[i * C + j] == -1 ? 0 : (int)a[where[i * C + j]][V]) << " \n"[j == C - 1];
    }
}
```

题面说任何初始状态都能全部熄灭，对方阵来说这等价于满秩，所以解唯一，代码里没有判无解。换成别的尺寸（比如 5×5）就不一定满秩了：有自由元时解有 $2^{\text{自由元数}}$ 个，有的初始状态无解。

### 4.3 例：CF 1344F Piet's Palette，把颜色看成向量

题（[CF 1344F](https://codeforces.com/problemset/problem/1344/F)）：调色盘有 $n \le 1000$ 个格子，每格是红 R、黄 Y、蓝 B 之一或者空。混色规则：一串颜色，每次看前两个，相同就都删掉，不同就换成缺的那一种，最后剩一个就是结果，什么都不剩是白 W。依次给出 $k \le 1000$ 个操作：`mix` 按给定顺序混若干格子并告诉你结果；`RY`、`RB`、`YB` 把若干格子里的两种颜色互换。求一种初始的调色盘，或者判断不可能。

这题的难点全在建模，建好之后就是 4.1 的消元。

**混色就是异或。** 把 W、R、Y、B 编成 GF(2) 上的二维向量 $(0, 0)$、$(1, 0)$、$(0, 1)$、$(1, 1)$。对照规则：相同的两种颜色异或得 $(0, 0)$，就是“都删掉”；R 和 Y 异或得 $(1, 1)$ 即 B，正是“换成缺的那一种”，另外两对也一样；空格是 $(0, 0)$，不影响。异或满足交换律、结合律，所以**混色的结果就是这些格子颜色向量的异或和**，和顺序无关，题目给的顺序用不上。

**互换就是乘一个矩阵。** RY 互换把 $(1, 0)$ 和 $(0, 1)$ 交换，$(1, 1)$ 不变，这是 GF(2)$^2$ 上的线性变换，矩阵是 $\begin{pmatrix}0&1\\1&0\end{pmatrix}$；同样 RB 是 $\begin{pmatrix}1&0\\1&1\end{pmatrix}$，YB 是 $\begin{pmatrix}1&1\\0&1\end{pmatrix}$。

**每格记一个累计矩阵。** 格子 $j$ 的初始颜色是未知向量 $x_j$，现在的颜色是 $T_j x_j$，$T_j$ 一开始是单位阵，每被互换一次就左乘对应的矩阵。一次 `mix` 告诉我们

$$
\bigoplus_{j \in S} T_j x_j = \text{结果颜色},
$$

按两个分量拆开就是两条模 2 方程。未知数 $2n \le 2000$ 个，方程 $2k \le 2000$ 条，bitset 消元约 $2000^3 / 64 \approx 1.3 \times 10^8$ 次位运算。有自由元时随便取 0，任意一组解都行。

```cpp
#include <bits/stdc++.h>
using namespace std;

// 套 4.1 的 gauss（模 2）

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, k;
    cin >> n >> k;
    // 颜色 = GF(2)^2 的向量：W = 00，R = (1,0)，Y = (0,1)，B = (1,1)；混色就是异或
    // 格子 j 现在的颜色 = T_j * x_j，x_j = (x_{2j}, x_{2j+1}) 是初始颜色，T_j 一开始是单位阵
    vector<array<int, 4>> T(n, {1, 0, 0, 1});            // {t00, t01, t10, t11}
    vector<bitset<MV + 1>> eq;
    int V = 2 * n;
    for (int t = 0; t < k; t++) {
        string op;
        int m;
        cin >> op >> m;
        vector<int> id(m);
        for (auto& j : id) cin >> j, j--;
        if (op == "mix") {
            char ch;
            cin >> ch;
            bitset<MV + 1> e0, e1;               // 结果颜色的第 0 位、第 1 位各一个方程
            for (int j : id) {
                e0[2 * j] = T[j][0], e0[2 * j + 1] = T[j][1];
                e1[2 * j] = T[j][2], e1[2 * j + 1] = T[j][3];
            }
            e0[V] = (ch == 'R' || ch == 'B');
            e1[V] = (ch == 'Y' || ch == 'B');
            eq.push_back(e0), eq.push_back(e1);
        } else {
            // 交换两种颜色是 GF(2)^2 上的可逆线性变换 M，T_j <- M * T_j
            array<int, 4> M = op == "RY" ? array<int, 4>{0, 1, 1, 0}
                            : op == "RB" ? array<int, 4>{1, 0, 1, 1}
                                         : array<int, 4>{1, 1, 0, 1};
            for (int j : id) {
                auto& A = T[j];
                A = {(M[0] & A[0]) ^ (M[1] & A[2]), (M[0] & A[1]) ^ (M[1] & A[3]),
                     (M[2] & A[0]) ^ (M[3] & A[2]), (M[2] & A[1]) ^ (M[3] & A[3])};
            }
        }
    }

    vector<int> where;
    if (gauss(eq, V, where) < 0) { cout << "NO\n"; return 0; }

    string s(n, '.');
    for (int j = 0; j < n; j++) {
        int b0 = where[2 * j] == -1 ? 0 : eq[where[2 * j]][V];          // 自由元取 0
        int b1 = where[2 * j + 1] == -1 ? 0 : eq[where[2 * j + 1]][V];
        s[j] = ".RYB"[b0 | b1 << 1];
    }
    cout << "YES\n" << s << '\n';
}
```

### 4.4 解的个数和线性基的计数是同一件事

模 2 方程组 $Ax = b$ 有解时，解有 $2^{m - r}$ 个：特解异或上核里的任意一个元素（[L1 第 4.5 节](/zh/algo/l1-linear-algebra/)的“平移”）。[L3 第 3.2 节](/zh/algo/l3-xor-basis/)的“每个值由 $2^{n-r}$ 个子集得到”是同一个结论：把 $n$ 个数当作 $A$ 的 $n$ 列，选哪些数就是 $x$，插入失败的数对应自由元。

## 5. 增量高斯：一条一条加方程

### 5.1 每来一条方程就消

有的题方程是一条一条来的：要知道“加到第几条时第一次能确定全部未知数”，或者要从很多候选方程里挑出线性无关的一组。每次重新消一遍太慢，可以一直维护一个简化行阶梯形，来一条消一条：

1. 用已有的每一行，把新方程在那一行主元列上的系数消成 0（右端跟着一起变）；
2. 消完系数全 0：右端是 0，说明新方程能由已有方程推出，返回 0；右端非 0，矛盾，返回 $-1$；
3. 否则取它第一个非零的列作新主元，再用它把已有各行这一列清成 0，保持“每个主元列只有一个 1”，然后加进来，返回 1。

#### 复杂度

| 操作 | 复杂度 |
| --- | --- |
| `eliminate`、`add`、`implied` | $O(r \cdot \text{MV} / 64)$ |
| `rank` | $O(1)$ |
| `solve` | $O(r + \text{MV} / 64)$ |
| `kernel` | $O((n - r)(r + \text{MV} / 64))$ |
| `merge` | $O(r' \cdot r \cdot \text{MV} / 64)$，$r'$ 是另一组的秩 |

$r$ 是当前的秩，$n$ 是未知数个数，$\text{MV} / 64$ 是一行 bitset 占的机器字数，一次整行异或就是这么多次整数异或。依次加 $k$ 条方程，总共 $O(k \cdot r \cdot \text{MV} / 64)$。模 $p$ 下一行是 `vector<long long>`，异或换成减去若干倍，第 3 步先把新行乘主元的逆元，加一条是 $O(r \cdot n + \log p)$。

#### 模板（模 2）

第 $j$ 个未知数对应 bitset 的第 $j$ 位，`MV` 开到比未知数个数大就行。右端是一个 `int`，几组系数相同的方程组可以把右端按位打包一起消，5.2 就是 30 组一起消。

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MV = 1024;                             // MV = max variables，未知数个数的上限；bitset 的长度要在编译时定下，所以是常量

// 增量高斯（模 2）：一条一条加方程，始终保持简化行阶梯形
struct IncGauss {
    int n;                                       // 未知数个数
    vector<bitset<MV>> row;
    vector<int> rhs, piv;                        // 每行的右端、主元列；右端可以把若干位打包一起异或
    bool bad = false;                            // 出现过矛盾
    IncGauss(int n) : n(n) {}

    void eliminate(bitset<MV>& v, int& b) const {        // 用已有各行把 v 在主元列上的 1 消掉，右端跟着变
        for (int i = 0; i < (int)row.size(); i++)
            if (v[piv[i]]) v ^= row[i], b ^= rhs[i];
    }
    int add(bitset<MV> v, int b) {               // 1：独立，秩加 1；0：能由已有方程推出；-1：矛盾
        eliminate(v, b);
        int p = v._Find_first();
        if (p >= n) { if (b) bad = true; return b ? -1 : 0; }
        for (int i = 0; i < (int)row.size(); i++)
            if (row[i][p]) row[i] ^= v, rhs[i] ^= b;  // 新主元列在旧行里清成 0
        row.push_back(v), rhs.push_back(b), piv.push_back(p);
        return 1;
    }
    int rank() const { return row.size(); }
    int implied(bitset<MV> v) const {            // 左边为 v 的方程能否推出：能就返回右端，不能返回 -1
        int b = 0;
        eliminate(v, b);
        return v.none() ? b : -1;
    }
    bitset<MV> solve() const {                   // !bad 时的一组解：自由元取 0，主元等于右端
        bitset<MV> x;
        for (int i = 0; i < (int)row.size(); i++) x[piv[i]] = rhs[i];
        return x;
    }
    vector<bitset<MV>> kernel() const {          // 齐次方程组解空间的基，n - rank() 个
        vector<int> isp(n, -1);
        for (int i = 0; i < (int)row.size(); i++) isp[piv[i]] = i;
        vector<bitset<MV>> ks;
        for (int f = 0; f < n; f++) {
            if (isp[f] >= 0) continue;
            bitset<MV> x;
            x[f] = 1;                            // 这个自由元取 1，其余自由元取 0
            for (int i = 0; i < (int)row.size(); i++)
                if (row[i][f]) x[piv[i]] = 1;
            ks.push_back(x);
        }
        return ks;
    }
    void merge(const IncGauss& o) {              // 把另一组的方程逐条加进来
        for (int i = 0; i < (int)o.row.size(); i++) add(o.row[i], o.rhs[i]);
    }
};
```

`bad` 为真时方程组无解。否则解有 $2^{n - r}$ 个：`solve()` 给出一个，再异或上 `kernel()` 里任意几个向量，就是 [L1 第 4.5 节](/zh/algo/l1-linear-algebra/)说的“全部解是零空间整体平移一个解”。

线性基是这份模板在列数不超过 60、没有右端时的写法；两者逐项对照，以及第 $k$ 小这类线性基常用的操作，在 [L3 线性基](/zh/algo/l3-xor-basis/)的附录。

### 5.2 例：2024 ICPC 昆明 E Extracting Weights，挑出独立的询问

题（[2024 ICPC 昆明区域赛 E](https://codeforces.com/gym/105588/problem/E)，交互）：一棵 $n \le 250$ 个点的树，点有未知权值 $w_i < 2^{30}$，已知 $w_1 = 0$。给定 $k$，你可以问至多 $n$ 次“从 $u$ 到 $v$ 的简单路径上所有点权的异或和”，但只有路径恰好 $k$ 条边时才回答。所有询问必须一次性发出，再一起收回答。先判断能不能用至多 $n$ 次询问确定所有权值：不能就输出 `NO`；能就输出 `YES`，发出询问，最后输出 $w_2, \dots, w_n$。

**每次询问是一条方程。** 未知数是 $w_1, \dots, w_n$。询问 $(u, v)$ 的回答是路径上的点的权值异或和，系数就是“点在不在路径上”的 0/1 向量。$w$ 有 30 位，但每一位的方程组系数都一样，右端用一个 `int` 存，异或时 30 个方程组一起做。

**能不能确定，看秩。** 所有 $k$ 条边的路径对应的方程，加上 $w_1 = 0$，秩为 $n$ 才能唯一确定全部权值。从中挑出 $n$ 条线性无关的方程，就是 5.1 的模板：枚举所有距离为 $k$ 的点对，能让秩加 1 的就留下。

**$w_1 = 0$ 要先放进去。** 它也是一条方程，不占询问次数。先插它，询问只需要补齐剩下的 $n - 1$ 维，最多问 $n - 1$ 次。如果先挑 $n - 1$ 条询问、最后再加它，这 $n - 1$ 条的组合可能恰好推出 $w_1 = 0$，它就加不进去，秩停在 $n - 1$；其实换一条询问或多问一条就够，却误判成 `NO`。

**两遍消元。** 第一遍不知道回答，只看系数挑询问；拿到回答后，带着右端把同样的方程再加一遍，满秩的简化行阶梯形每行只剩主元那一个 1，右端就是那个点的权值。

```cpp
#include <bits/stdc++.h>
using namespace std;

// 套 5.1 的 IncGauss

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, k;
    cin >> n >> k;
    vector<vector<int>> g(n + 1);
    for (int i = 1; i < n; i++) {
        int x, y;
        cin >> x >> y;
        g[x].push_back(y), g[y].push_back(x);
    }
    vector<int> par(n + 1, 0), dep(n + 1, 0), ord{1};
    for (int i = 0; i < (int)ord.size(); i++)
        for (int v : g[ord[i]])
            if (v != par[ord[i]]) par[v] = ord[i], dep[v] = dep[ord[i]] + 1, ord.push_back(v);

    auto path = [&](int u, int v) {             // u 到 v 路径上的点，第 i-1 位表示点 i
        bitset<MV> s;
        while (u != v) {
            if (dep[u] < dep[v]) swap(u, v);
            s[u - 1] = 1, u = par[u];
        }
        s[u - 1] = 1;
        return s;
    };
    auto dist = [&](int u, int v) {
        int d = 0;
        while (u != v) {
            if (dep[u] < dep[v]) swap(u, v);
            u = par[u], d++;
        }
        return d;
    };

    IncGauss G(n);
    bitset<MV> e1;
    e1[0] = 1;
    G.add(e1, 0);                                // w_1 = 0 也是一条方程，和询问一起消
    vector<pair<int, int>> ask;
    for (int u = 1; u <= n && G.rank() < n; u++)
        for (int v = u + 1; v <= n && G.rank() < n; v++)
            if (dist(u, v) == k && G.add(path(u, v), 0) == 1) ask.push_back({u, v});

    if (G.rank() < n) { cout << "NO" << endl; return 0; }
    cout << "YES" << endl;
    cout << "? " << ask.size();
    for (auto [u, v] : ask) cout << ' ' << u << ' ' << v;
    cout << endl;

    IncGauss S(n);                               // 带上回答，再消一遍
    S.add(e1, 0);
    for (auto [u, v] : ask) {
        int x;
        cin >> x;
        S.add(path(u, v), x);
    }
    vector<int> w(n);
    for (int i = 0; i < n; i++) w[S.piv[i]] = S.rhs[i];   // 满秩的简化行阶梯形：每行只剩主元
    cout << '!';
    for (int i = 1; i < n; i++) cout << ' ' << w[i];
    cout << endl;
}
```

枚举点对 $O(n^2)$，每对求距离和路径 $O(n)$，增量消元每次 $O(n \cdot n / 64)$，总共约 $O(n^3)$。交互题每次输出后都要刷新，代码里用 `endl`。

## 练习

每题后面写的是用到哪一节。

**必做**

1. [洛谷 P3389 【模板】高斯消元法](https://www.luogu.com.cn/problem/P3389)：2.2，只判唯一解。
2. [洛谷 P4035 球形空间产生器](https://www.luogu.com.cn/problem/P4035)：球面方程是二次的，相邻两个相减，二次项消掉，变成线性方程组。第 2 节。
3. [洛谷 P2973 Driving Out the Piggies](https://www.luogu.com.cn/problem/P2973)：期望有环，和 2.3 一样对点列方程。
4. [洛谷 P2447 外星千足虫](https://www.luogu.com.cn/problem/P2447)：模 2，还要输出最早用到第几条方程就能确定，第 4、5 节。

**选做**

5. [洛谷 P3164 和谐矩阵](https://www.luogu.com.cn/problem/P3164)：和开关灯同一个模型，但要非零解，自由元取 1。4.2。
6. [洛谷 P4111 小 Z 的房间](https://www.luogu.com.cn/problem/P4111)：矩阵树定理求行列式，模数 $10^9$ 不是质数，没有逆元，两行之间辗转相除消元。3.1、3.3。

## 和其他文章的连接

- [L1 线性代数](/zh/algo/l1-linear-algebra/)：第 3 节“求基就是消元”，第 6 节解的结构（像和核），第 4.4 节模 2 消元和线性基是同一个矩阵的行和列。
- [L3 线性基](/zh/algo/l3-xor-basis/)：插入是 5.1 增量高斯在列数不超过 60 时的特例（两者对照在它的附录），3.2 的计数就是 4.4。
- [C0 赛场数学总览](/zh/algo/c0-contest-math-overview/)：4.4 列出了落到线性方程组的三类题面信号，4.6 是行列式的模板和计数用法。
- 英文模板合集 [Matrix #2: Gaussian Elimination](/posts/matrix-2-gaussian-elimination/)：实数、模 $p$、模 2 的求解、行列式、求逆、求秩全套模板，以及模 $p$ 的增量版本。
