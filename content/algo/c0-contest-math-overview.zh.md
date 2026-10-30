---
title: "C0：赛场上的数学"
date: 2026-10-30
slug: "c0-contest-math-overview"
description: "数论、组合计数、线性代数在赛场上怎么想：先看范围定复杂度，打表找规律，推式子靠五个动作（换枚举对象、交换求和顺序、把条件展开、贡献法、恰好与钦定互换）；每样工具讲它解决什么、什么信号该想到它、式子怎么推；最后从题面开始完整写三道题。附 13 道练习题。"
weight: 10
math: true
toc: true
---
比赛后半段的数学题，难点很少在定理本身：定理大多能背下来，卡住的地方是看不出这道题该用哪一个，或者看出来了却推不到能写代码的那一步。所以这篇不按定理排，按赛场上的动作排：先讲一道数学题拿到手怎么走（第 1 节），再分数论、组合计数、线性代数三块，每样东西都讲它解决什么、题面上什么信号该想到它、式子怎么推出来（第 2 到 4 节），最后从题面开始完整写三道题（第 5 节）。

## 1. 赛场上一道数学题怎么走

### 1.1 数据范围：先定能用的复杂度

数学题的数据范围比别的题更能说明做法，因为数学题的范围常常大到只有一两类算法能过。C++ 一秒大约 $10^8$ 次简单运算，按这个反推：

| 范围 | 能接受的复杂度 | 往哪想 |
|---|---|---|
| $n \le 10^{18}$ | $O(\log n)$，或 $O(k^3 \log n)$ | 快速幂、矩阵快速幂、线性递推、找规律后的闭式 |
| $n \le 10^{10}$ 到 $10^{11}$ | $O(n^{2/3})$、$O(\sqrt n)$ | 数论分块、杜教筛、min_25 |
| $n \le 10^7$ | $O(n)$ | 线性筛、阶乘表 |
| $n \le 10^5$ 到 $10^6$，式子里有卷积 | $O(n \log n)$ | NTT、多项式 |
| $n \le 5000$ | $O(n^2)$ | 组合数递推、计数 DP |
| $n \le 500$ | $O(n^3)$ | 高斯消元、行列式 |
| $n \le 20$ | $O(2^n n)$ | 子集容斥、状压 |

模数也是信号。$998244353 = 119 \cdot 2^{23} + 1$，它的乘法群里有 $2^{23}$ 阶的元素，NTT 正好要这个，所以**题目给 998244353 几乎是在提示要做卷积**；给 $10^9 + 7$ 只说明它是个质数，可以用费马小定理求逆元。模数不是质数，或者模数由输入给出，逆元就不一定存在，要换成 exgcd，必要时拆成质数幂再用 CRT 合并。模数是个小质数而 $n$ 比它大，阶乘里会出现因子 $p$，阶乘表直接失效，要用 Lucas。

### 1.2 打表：先让暴力替你看规律

推式子之前先写暴力，把小范围的答案打出来。打出来的表主要看三件事。第一，它是不是积性的：对互质的 $a, b$ 有没有 $f(ab) = f(a) f(b)$，是的话可以线性筛。第二，它是不是满足线性递推，是的话可以 BM 加快速求第 $n$ 项（4.3）。第三，它是不是某个认识的数列：$2^n$、$n!$、卡特兰数、斯特林数、斐波那契数。

暴力还有第二个用处：最后写出来的公式，在小数据上跟暴力比一遍再交。数学题错一个符号、差一个边界，样例往往还能过。**暴力程序先写，它既是找规律的工具，也是最后对拍的标准答案。** 队伍里别人在写别的题时，这一步只要五分钟。

### 1.3 推式子的五个动作

推式子看起来靠灵感，其实反复出现的动作只有五个。

**换枚举对象。** 直接枚举题目给的东西太慢时，换成枚举一个取值少的量。$\sum_{i \le n}\sum_{j \le n} f(\gcd(i, j))$ 里 $i, j$ 有 $n^2$ 对，但 $\gcd$ 只有 $n$ 种取值，改成枚举 $d = \gcd(i, j)$，再数有多少对的 $\gcd$ 恰好是 $d$。“所有子集的最大值之和”也一样：子集有 $2^n$ 个，改成枚举哪个元素是最大值。

**交换求和顺序。** 内层的求和条件依赖外层变量时，把两层倒过来，内层常常变成一个能直接写出来的数：

$$\sum_{i=1}^{n} \sum_{d \mid i} g(d) = \sum_{d=1}^{n} g(d) \cdot \#\{\, i \le n : d \mid i \,\} = \sum_{d=1}^{n} g(d) \left\lfloor \frac{n}{d} \right\rfloor$$

**把条件写成能展开的式子。** $[\gcd(i,j) = 1]$ 这种指示函数没法直接求和，但它等于 $\sum_{d \mid \gcd(i,j)} \mu(d)$，展开以后就能交换求和顺序（2.5）。“至少有一个坏条件成立”可以用容斥展开成交集的和（3.4）。

**贡献法。** 答案是“所有对象的某个量之和”，而这个量又是对象里各个零件的和时，把两层求和倒过来：对每个零件，数它出现在多少个对象里。期望的线性性是同一件事的概率版本（3.8）。

**恰好与至少互换，正难则反。** “恰好 $k$ 个”难数，“钦定 $k$ 个、其余不管”往往好数，两者之间差一个二项式反演（3.5）。“没有一个坏的”难数时，先数全部，再减去至少有一个坏的。

**几乎所有推导都是这五个动作的组合；卡住时把五个逐个试一遍，比盯着式子等灵感可靠。** 第 2 到 4 节的每个推导，都会标出用的是哪个动作。

### 1.4 取模的基本盘

数学题的答案几乎都要取模，下面这几样每场都要用，应该能闭眼写出来：

```cpp
const long long MOD = 1'000'000'007;

long long qpow(long long a, long long e, long long m = MOD) {
    long long r = 1 % m;
    a %= m;
    if (a < 0) a += m;
    for (; e > 0; e >>= 1, a = a * a % m)
        if (e & 1) r = r * a % m;
    return r;
}
long long inv(long long a) { return qpow(a, MOD - 2); }  // MOD 是质数才能这样求

struct Binom {
    vector<long long> f, fi;
    Binom(int n) : f(n + 1), fi(n + 1) {
        f[0] = 1;
        for (int i = 1; i <= n; i++) f[i] = f[i - 1] * i % MOD;
        fi[n] = inv(f[n]);
        for (int i = n; i > 0; i--) fi[i - 1] = fi[i] * i % MOD;
    }
    long long C(int n, int k) const {
        if (k < 0 || k > n) return 0;
        return f[n] * fi[k] % MOD * fi[n - k] % MOD;
    }
};
```

逆元用费马小定理：$p$ 是质数且 $p \nmid a$ 时 $a^{p-1} \equiv 1$，所以 $a^{-1} \equiv a^{p-2}$。阶乘的逆元只求一次快速幂，其余倒着推：因为 $\frac{1}{(i-1)!} = \frac{i}{i!}$，所以 `fi[i-1] = fi[i] * i`，整张表 $O(n)$。**除法一律换成乘逆元，减法之后加 MOD 再取模**，这两条漏掉任何一处，结果就会出负数或者错。

## 2. 数论

### 2.1 exgcd：解 $ax + by = c$

裴蜀定理说，$ax + by = c$ 有整数解当且仅当 $\gcd(a, b) \mid c$。扩展欧几里得在求 $\gcd$ 的同时给出 $ax + by = \gcd(a,b)$ 的一组解。递归到 $(b, a \bmod b)$ 时已经有 $b x' + (a \bmod b) y' = g$，把 $a \bmod b = a - \lfloor a/b \rfloor b$ 代进去，整理成 $a$ 和 $b$ 的系数：

$$a y' + b \left( x' - \left\lfloor \frac{a}{b} \right\rfloor y' \right) = g$$

所以 $x = y'$，$y = x' - \lfloor a/b \rfloor y'$。代码里递归时把 `x, y` 交换着传进去，回来只要修正 `y`：

```cpp
// 返回 g = gcd(a, b)，并求出 a*x + b*y = g 的一组解
long long exgcd(long long a, long long b, long long& x, long long& y) {
    if (b == 0) { x = 1; y = 0; return a; }
    long long g = exgcd(b, a % b, y, x);
    y -= a / b * x;
    return g;
}
```

有了一组特解 $(x_0, y_0)$，$ax + by = c$ 的全部解是 $x = x_0 \cdot \frac{c}{g} + k \cdot \frac{b}{g}$（$y$ 跟着变）。同余方程 $ax \equiv c \pmod m$ 就是 $ax + my = c$，最小非负解是把 $x$ 对 $m/g$ 取模再调成非负。**同余方程、不定方程、模数不是质数时的逆元，都是 exgcd 这一个函数**，逆元存在的条件就是 $\gcd(a, m) = 1$。

### 2.2 同余方程组：两两合并

给一组 $x \equiv r_i \pmod{m_i}$ 求 $x$。经典 CRT 公式要求模数两两互质，比赛里更常用的是两两合并，不要求互质。合并 $x \equiv r_1 \pmod{m_1}$ 和 $x \equiv r_2 \pmod{m_2}$：第一个方程说 $x = r_1 + m_1 t$，代进第二个得到 $m_1 t \equiv r_2 - r_1 \pmod{m_2}$，这是一个关于 $t$ 的同余方程。设 $g = \gcd(m_1, m_2)$，$g \nmid (r_2 - r_1)$ 就无解；否则 exgcd 给出 $m_1 p + m_2 q = g$，即 $m_1 p \equiv g \pmod{m_2}$，于是 $t = \frac{r_2 - r_1}{g} p$ 满足方程，$t$ 只需对 $m_2 / g$ 取模。合并后的模数是 $\operatorname{lcm}(m_1, m_2)$：

```cpp
// 合并 x ≡ r1 (mod m1) 和 x ≡ r2 (mod m2)，结果写回 r1、m1；无解返回 false
bool crt_merge(long long& r1, long long& m1, long long r2, long long m2) {
    long long p, q;
    long long g = exgcd(m1, m2, p, q);
    if ((r2 - r1) % g != 0) return false;
    long long t = (__int128)((r2 - r1) / g) * p % (m2 / g);
    long long l = m1 / g * m2;
    r1 = (long long)((((__int128)t * m1 + r1) % l + l) % l);
    m1 = l;
    return true;
}
```

中间乘积可能到 $10^{36}$ 量级，所以用 `__int128`。**两两合并的写法不要求模数互质，比背 CRT 公式更通用**，一组方程从左到右合并一遍即可。

### 2.3 欧拉定理与降幂：指数太大怎么办

$\gcd(a, m) = 1$ 时 $a^{\varphi(m)} \equiv 1 \pmod m$，费马小定理是 $m$ 为质数的特例。指数 $b$ 很大（比如本身是个幂，或者是一个大数的十进制串）时，可以把指数对 $\varphi(m)$ 取模。不互质时有扩展欧拉定理：

$$a^b \equiv a^{\, b \bmod \varphi(m) + \varphi(m)} \pmod m, \quad b \ge \varphi(m)$$

它不要求 $a$ 和 $m$ 互质，代价是指数要保留一个 $+\varphi(m)$，所以需要知道 $b$ 是否 $\ge \varphi(m)$。指数塔 $a_1^{a_2^{a_3^{\cdots}}} \bmod m$ 就是递归地用它：外层模 $m$，指数那一层模 $\varphi(m)$，再里一层模 $\varphi(\varphi(m))$。$\varphi$ 每用两次至少减半，**所以指数塔沿 $\varphi$ 链往下递归，链长只有 $O(\log m)$**，到模数为 1 就停。

### 2.4 线性筛：一次求出所有积性函数值

积性函数指对互质的 $a, b$ 有 $f(ab) = f(a) f(b)$ 的函数，比如欧拉函数 $\varphi$、莫比乌斯函数 $\mu$、因子个数 $d$。积性函数由它在质数幂上的值决定，所以只要知道 $f(p^k)$，筛的时候就能把所有 $f(n)$ 填出来。

线性筛让每个合数 $x$ 只被筛一次：用它的最小质因子 $p$ 和 $i = x / p$ 去筛。外层枚举 $i$，内层从小到大枚举质数 $p$，筛掉 $i \cdot p$；一旦 $p \mid i$ 就停，因为再往后的质数 $p' > p$ 已经不是 $i \cdot p'$ 的最小质因子了（$p$ 比它小，而且整除 $i \cdot p'$），留给以后的 $i$ 去筛。停下来的那一刻也正好区分了两种情况：$p \nmid i$ 时 $i$ 和 $p$ 互质，直接相乘；$p \mid i$ 时 $p$ 在 $i \cdot p$ 里的次数至少是 2，按质数幂的规则算：

```cpp
// 线性筛：每个合数只被它的最小质因子筛一次，顺便求出 φ 和 μ
struct Sieve {
    vector<int> primes, phi, mu;
    vector<bool> comp;
    Sieve(int n) : phi(n + 1), mu(n + 1), comp(n + 1) {
        phi[1] = mu[1] = 1;
        for (int i = 2; i <= n; i++) {
            if (!comp[i]) { primes.push_back(i); phi[i] = i - 1; mu[i] = -1; }
            for (int p : primes) {
                if ((long long)i * p > n) break;
                comp[i * p] = true;
                if (i % p == 0) {            // p 是 i 的最小质因子，i*p 里 p 的次数 ≥ 2
                    phi[i * p] = phi[i] * p;
                    mu[i * p] = 0;
                    break;
                }
                phi[i * p] = phi[i] * (p - 1);  // i 和 p 互质
                mu[i * p] = -mu[i];
            }
        }
    }
};
```

**线性筛的关键在那个 `break`：它保证每个合数只被最小质因子筛一次，于是总共 $O(n)$，而且筛到 $i \cdot p$ 时正好知道 $p$ 和 $i$ 是否互质。** 要筛别的积性函数，只要把两个分支换成那个函数的规则；$f(p^k)$ 不能从 $f(p^{k-1})$ 一步推出时，另开一个数组记 $i$ 里最小质因子那一部分的幂。

### 2.5 狄利克雷卷积与莫比乌斯反演

两个数论函数的狄利克雷卷积是 $(f * g)(n) = \sum_{d \mid n} f(d)\, g(n/d)$。记 $\mathbf{1}(n) = 1$，$\mathrm{id}(n) = n$，$\varepsilon(n) = [n = 1]$（卷积的单位元），常用的关系有四条：

$$\mu * \mathbf{1} = \varepsilon, \qquad \varphi * \mathbf{1} = \mathrm{id}, \qquad \mu * \mathrm{id} = \varphi, \qquad \mathbf{1} * \mathbf{1} = d$$

第一条展开就是 $\sum_{d \mid n} \mu(d) = [n = 1]$，第二条是 $\sum_{d \mid n} \varphi(d) = n$。莫比乌斯反演是第一条的推论：若 $F = f * \mathbf{1}$，两边卷 $\mu$ 得 $f = F * \mu$。

赛场上真正用到的是前两条的展开形式。$[\gcd(i,j) = 1] = \sum_{d \mid \gcd(i,j)} \mu(d)$ 把一个条件拆成因子上的和，$\gcd(i,j) = \sum_{d \mid \gcd(i,j)} \varphi(d)$ 把一个值拆成因子上的和；拆完以后 $d \mid \gcd(i,j)$ 等价于 $d \mid i$ 且 $d \mid j$，就能交换求和顺序。**反演在赛场上的用法几乎只有一个：把 $[\gcd = 1]$ 或 $\gcd$ 本身拆成因子求和，然后交换求和顺序。** 2.7 的三道式子都是这样推的。

### 2.6 数论分块：$\lfloor n/i \rfloor$ 只有 $O(\sqrt n)$ 种取值

$i \le \sqrt n$ 时 $i$ 本身只有 $\sqrt n$ 个；$i > \sqrt n$ 时 $\lfloor n/i \rfloor < \sqrt n$，取值也不超过 $\sqrt n$ 个。所以 $\lfloor n/i \rfloor$ 总共不超过 $2\sqrt n$ 种取值，而且相同的值连成一段。从段的左端 $l$ 出发，商是 $q = \lfloor n/l \rfloor$，商仍为 $q$ 的最大的 $i$ 是 $\lfloor n/q \rfloor$，这就是段的右端。两个变量 $n, m$ 同时出现时，右端取两者的较小值：

```cpp
// Σ_{d=1}^{min(n,m)} f(d)·⌊n/d⌋·⌊m/d⌋，pre 是 f 的前缀和（pre[0] = 0）
long long block_sum(long long n, long long m, const vector<long long>& pre) {
    long long res = 0;
    for (long long l = 1, r; l <= min(n, m); l = r + 1) {
        r = min(n / (n / l), m / (m / l));
        res += (pre[r] - pre[l - 1]) * (n / l) * (m / l);
    }
    return res;
}
```

**只要式子化成 $\lfloor n/d \rfloor$ 乘一个能求前缀和的函数，就能 $O(\sqrt n)$ 算完**；多组询问时前缀和预处理一次，每组只付分块的代价。

### 2.7 范式：gcd 求和的三道式子

这一类题是数论里出现最多的，三道式子用同一个骨架。

第一道，数互质的对：$\sum_{i=1}^{n} \sum_{j=1}^{m} [\gcd(i,j) = 1]$。用 $\mu$ 把条件拆开，再交换求和顺序，$d \mid i$ 的 $i$ 有 $\lfloor n/d \rfloor$ 个：

$$\sum_{i=1}^{n} \sum_{j=1}^{m} \sum_{d \mid i,\, d \mid j} \mu(d) = \sum_{d=1}^{\min(n,m)} \mu(d) \left\lfloor \frac{n}{d} \right\rfloor \left\lfloor \frac{m}{d} \right\rfloor$$

第二道，$\gcd$ 求和：$\sum_{i,j} \gcd(i,j)$。用 $\varphi * \mathbf{1} = \mathrm{id}$ 把值拆开，同样交换，得到 $\sum_{d} \varphi(d) \lfloor n/d \rfloor \lfloor m/d \rfloor$。第 5.1 节从题面开始完整写这一道。

第三道，$\gcd$ 是质数的对：$\sum_{p} \sum_{i,j} [\gcd(i,j) = p]$。先换枚举对象：$\gcd(i,j) = p$ 等价于 $i = pi'$，$j = pj'$ 且 $\gcd(i', j') = 1$，于是内层变成第一道，上限换成 $n/p$、$m/p$：

$$\sum_{p} \sum_{d} \mu(d) \left\lfloor \frac{n}{pd} \right\rfloor \left\lfloor \frac{m}{pd} \right\rfloor$$

这时外层对每个质数做一次分块，太慢。关键一步是令 $T = pd$，改成枚举 $T$，因为 $\lfloor n/T \rfloor$ 只跟 $T$ 有关：

$$\sum_{T=1}^{\min(n,m)} \left\lfloor \frac{n}{T} \right\rfloor \left\lfloor \frac{m}{T} \right\rfloor \underbrace{\sum_{p \mid T,\ p \text{ 质数}} \mu\!\left(\frac{T}{p}\right)}_{g(T)}$$

$g(T)$ 跟询问无关，预处理时对每个质数 $p$ 枚举它的倍数加一遍，总共 $O(n \log \log n)$，再做前缀和，每组询问就是一次分块。

**三道式子同一个骨架：把条件或值拆成因子求和，交换顺序，合并成 $\sum_T g(T) \lfloor n/T \rfloor \lfloor m/T \rfloor$，预处理 $g$ 的前缀和再分块。** 把乘积 $pd$ 换成新变量 $T$ 这一步最容易想不到，它的作用是让 $\lfloor n/\cdot \rfloor$ 只依赖一个变量。$\operatorname{lcm}$ 求和也走这条路：$\operatorname{lcm}(i,j) = \frac{ij}{\gcd(i,j)}$，先枚举 $\gcd$，剩下的互质条件再用 $\mu$ 拆，会出现两层分块。

### 2.8 $n$ 到 $10^{10}$ 以上：杜教筛

$n$ 大到线性筛筛不完时，要直接求积性函数的前缀和 $S(n) = \sum_{i \le n} f(i)$。杜教筛的想法是找一个辅助函数 $g$，使 $h = f * g$ 和 $g$ 的前缀和都能直接写出来。对 $h$ 的前缀和交换求和顺序：

$$\sum_{i=1}^{n} h(i) = \sum_{i=1}^{n} \sum_{d \mid i} g(d)\, f\!\left(\frac{i}{d}\right) = \sum_{d=1}^{n} g(d)\, S\!\left(\left\lfloor \frac{n}{d} \right\rfloor\right)$$

把 $d = 1$ 那一项单独拿出来，就得到 $S(n)$ 的递推：

$$g(1)\, S(n) = \sum_{i=1}^{n} h(i) - \sum_{d=2}^{n} g(d)\, S\!\left(\left\lfloor \frac{n}{d} \right\rfloor\right)$$

右边的和可以分块，用到的 $S$ 只在 $\lfloor n/d \rfloor$ 这 $O(\sqrt n)$ 个点上，记忆化下来；再用线性筛把 $n^{2/3}$ 以内的 $S$ 预先算好，总复杂度 $O(n^{2/3})$。求 $\sum \varphi$ 取 $g = \mathbf{1}$，$h = \mathrm{id}$，于是 $S(n) = \frac{n(n+1)}{2} - \sum_{d \ge 2} S(\lfloor n/d \rfloor)$；求 $\sum \mu$ 取 $g = \mathbf{1}$，$h = \varepsilon$，于是 $S(n) = 1 - \sum_{d \ge 2} S(\lfloor n/d \rfloor)$。**杜教筛的全部技巧在于找 $g$：让 $f * g$ 和 $g$ 的前缀和都能直接写出来。**

min_25 筛解决同样的问题，适用于 $f(p)$ 是关于 $p$ 的低次多项式、$f(p^k)$ 好算的积性函数，它先求出所有 $\lfloor n/i \rfloor$ 处的质数和，再按最小质因子递归补上合数，复杂度约 $O(n^{3/4} / \log n)$。

### 2.9 其余数论工具：认出信号就行

下面这些在赛场上是拿板子用的，要记住的是题面上什么信号对应它、复杂度多少：

| 题面信号 | 工具 | 代价 |
|---|---|---|
| 求 $a^x \equiv b \pmod p$ 里的 $x$ | BSGS（大步小步） | $O(\sqrt p)$ |
| 判断 $10^{18}$ 量级的数是不是质数，或者分解它 | Miller-Rabin + Pollard rho | 约 $O(n^{1/4})$ |
| 求 $x^2 \equiv a \pmod p$ | 二次剩余（Cipolla） | $O(\log p)$ |
| NTT 需要的单位根、离散对数、$x^k \equiv a$ | 原根 | 从小往大试，通常很快找到 |
| $\binom{n}{m} \bmod p$，$p$ 小而 $n$ 大 | Lucas | $O(p + \log_p n)$ |
| $n!$ 里因子 $p$ 的个数 | Legendre：$\sum_{k \ge 1} \lfloor n/p^k \rfloor$ | $O(\log_p n)$ |

## 3. 组合计数

### 3.1 组合数取模：先看 $n$ 和模数

同一个 $\binom{n}{k} \bmod p$，按 $n$ 和模数的不同有四种算法。$n \le 5000$ 时用杨辉三角 $\binom{n}{k} = \binom{n-1}{k-1} + \binom{n-1}{k}$ 递推，只用加法，任何模数都行。模数是大于 $n$ 的质数时用 1.4 的阶乘表，预处理 $O(n)$，每次 $O(1)$。模数是小质数 $p$ 而 $n \ge p$ 时，阶乘里含 $p$ 没有逆元，用 Lucas 定理 $\binom{n}{m} \equiv \binom{n \bmod p}{m \bmod p} \binom{\lfloor n/p \rfloor}{\lfloor m/p \rfloor}$ 把 $n$ 按 $p$ 进制拆开。模数是合数时拆成质数幂分别算，再用 2.2 合并，这种题少见。**模数是大质数时组合数就是查三张表，其余情况先看模数再选做法。**

### 3.2 计数的基本动作：插板、双射、贡献

插板法数的是 $x_1 + \dots + x_k = n$ 的非负整数解：把 $n$ 个球排成一排，插 $k - 1$ 块板分成 $k$ 段，球和板一共 $n + k - 1$ 个位置，选哪些位置放板，所以是 $\binom{n+k-1}{k-1}$。要求 $x_i \ge 1$ 时先给每个变量发一个，变成 $\binom{n-1}{k-1}$；有别的下界也是先发掉。上界不能这样处理，要用 3.4 的容斥。

双射是把要数的东西一一对应到好数的东西。卡特兰数是最典型的例子：从 $(0,0)$ 出发，走 $n$ 步向上、$n$ 步向下，任何时候不低于 0 的路径有多少条。全部路径有 $\binom{2n}{n}$ 条，坏的路径是某一刻碰到了 $-1$。把坏路径第一次碰到 $-1$ 之前的部分上下翻转，起点变成 $(0, -2)$，终点不变，这是坏路径和“从 $-2$ 走到 $0$ 的路径”之间的一一对应，后者有 $n+1$ 步向上，有 $\binom{2n}{n+1}$ 条。所以

$$C_n = \binom{2n}{n} - \binom{2n}{n+1}$$

括号序列、出栈序列、二叉树形态都能对应到这种路径。下界从 0 换成别的数、或者上下步数不相等时，同一个翻转照样能用。

贡献法本质上是交换求和顺序。例子：所有子集的最大值之和。把数组从小到大排好，$a_i$（下标从 0 开始）是最大值的子集，就是从比它小的 $i$ 个数里随便选，有 $2^i$ 个，答案是 $\sum_i a_i 2^i$。所有子数组的和之和也一样：$a_i$ 出现在左端 $\le i$、右端 $\ge i$ 的 $(i+1)(n-i)$ 个子数组里。**一个对象很难整体数时，换个角度：数每个零件出现在多少个对象里。**

### 3.3 球盒模型：$n$ 个球放进 $k$ 个盒子

分配问题按“球有没有区别、盒子有没有区别、盒子有什么限制”分成十二种，下面这张表要能当场推出来。$S(n,k)$ 是第二类斯特林数（$n$ 个有区别的元素分成 $k$ 个无序非空集合），$p(n,k)$ 是把 $n$ 分成恰好 $k$ 个正整数之和（不计顺序）的方案数，$k^{\underline{n}} = k(k-1)\cdots(k-n+1)$。

| 球 | 盒 | 盒子随意 | 每盒至少一个 | 每盒至多一个 |
|---|---|---|---|---|
| 有区别 | 有区别 | $k^n$ | $k!\, S(n,k)$ | $k^{\underline{n}}$ |
| 有区别 | 无区别 | $\sum_{i=0}^{k} S(n,i)$ | $S(n,k)$ | $[n \le k]$ |
| 无区别 | 有区别 | $\binom{n+k-1}{k-1}$ | $\binom{n-1}{k-1}$ | $\binom{k}{n}$ |
| 无区别 | 无区别 | $\sum_{i=0}^{k} p(n,i)$ | $p(n,k)$ | $[n \le k]$ |

两个递推都从一个具体元素的去向推出来。$S(n,k)$ 看第 $n$ 个元素：它自己单独一组，剩下的分成 $k-1$ 组；或者加入前 $n-1$ 个元素分好的 $k$ 组之一，有 $k$ 种选法。$p(n,k)$ 看有没有大小为 1 的部分：有的话拿掉一个 1；没有的话每部分都减 1，还是 $k$ 部分，总和少了 $k$：

$$S(n,k) = S(n-1,k-1) + k\, S(n-1,k), \qquad p(n,k) = p(n-1,k-1) + p(n-k,k)$$

**表里每一格都能从“最后一个球去哪”或“有没有大小为 1 的部分”推出来，不必死记。** 第一类斯特林数 $s(n,k)$ 数的是 $n$ 个元素排成 $k$ 个环的方案（有 $k$ 个环的排列），递推的想法一样：第 $n$ 个元素自成一环，或者插到前面某个元素后面，有 $n-1$ 种位置，$s(n,k) = s(n-1,k-1) + (n-1)\, s(n-1,k)$。

### 3.4 容斥：数“一个坏条件都不满足”

有 $n$ 个坏事件 $A_1, \dots, A_n$，要数一个都不发生的对象：

$$\Big| \overline{A_1} \cap \dots \cap \overline{A_n} \Big| = \sum_{S \subseteq \{1..n\}} (-1)^{|S|} \Big| \bigcap_{i \in S} A_i \Big|$$

一个恰好落在 $t \ge 1$ 个坏事件里的对象，在右边被算了 $\sum_{j} (-1)^j \binom{t}{j} = 0$ 次，所以只剩没有坏事件的对象。能用容斥的前提是“几个坏事件同时发生”好数。坏事件对称时，交集大小只跟 $|S|$ 有关，$2^n$ 个子集合成 $n+1$ 项：$\sum_{i} (-1)^i \binom{n}{i} N(i)$。

三个常见的例子。满射，$n$ 个有区别的球放进 $k$ 个有区别的盒子且不空：坏事件是“第 $j$ 个盒子空”，钦定 $i$ 个盒子空，其余随意，有 $(k-i)^n$ 种，所以满射数是 $\sum_i (-1)^i \binom{k}{i} (k-i)^n$，它也等于表里的 $k!\, S(n,k)$。错排，没有一个 $i$ 在第 $i$ 位：钦定 $i$ 个位置不动，其余随便排，$D_n = \sum_i (-1)^i \binom{n}{i} (n-i)!$。带上界的插板，$x_j \le c_j$：坏事件是 $x_j \ge c_j + 1$，钦定一组坏变量，就先把它们的下界抬到 $c_j + 1$ 再插板。**容斥的前提是“坏事件的交”好数；对称时一个组合数就把 $2^n$ 个子集压成 $n+1$ 项。**

### 3.5 二项式反演：恰好与钦定互换

设 $f(k)$ 是恰好有 $k$ 个好性质的对象数，$g(k)$ 是“钦定 $k$ 个性质成立、其余不管”的计数：对每个大小为 $k$ 的性质集合，数满足这些性质的对象，再加起来。一个恰好有 $i$ 个性质的对象，在 $g(k)$ 里被它那 $i$ 个性质中的每个 $k$ 元子集各算一次，所以

$$g(k) = \sum_{i \ge k} \binom{i}{k} f(i) \quad \Longleftrightarrow \quad f(k) = \sum_{i \ge k} (-1)^{i-k} \binom{i}{k} g(i)$$

右边的反演式可以把左边代进去验证，内层是 $\sum_j (-1)^j \binom{t}{j} = [t = 0]$。例子：恰好 $k$ 个不动点的排列。钦定 $i$ 个位置不动，先选是哪 $i$ 个，剩下的随便排，$g(i) = \binom{n}{i} (n-i)!$，代进反演式就得到 $f(k)$；$k = 0$ 时就是上一节的错排公式。

```cpp
// 恰好 k 个不动点的排列数：g(i) = C(n,i)·(n-i)!，再反演
long long exact_fixed(int n, int k, const Binom& B) {
    long long res = 0;
    for (int i = k; i <= n; i++) {
        long long g = B.C(n, i) * B.f[n - i] % MOD;
        long long term = B.C(i, k) * g % MOD;
        res += (i - k) % 2 ? MOD - term : term;
    }
    return res % MOD;
}
```

另一种常用形式是“至多”与“恰好”：$g(k) = \sum_{i \le k} \binom{k}{i} f(i)$ 等价于 $f(k) = \sum_{i \le k} (-1)^{k-i} \binom{k}{i} g(i)$。5.2 节的染色题用的就是这一种。**“恰好 $k$ 个”难数时，先数“钦定 $k$ 个、其余随意”，再反演回来；钦定的那个 $g$ 通常是一个组合数乘一个不受限的自由部分。**

min-max 反演是同一类想法用在最大最小值上：$\max(S) = \sum_{\varnothing \ne T \subseteq S} (-1)^{|T|+1} \min(T)$，两边取期望仍成立。它的用处是“所有事件都发生的期望时间”（最大值）难求、“最早一个发生的期望时间”（最小值）好求的题，比如每步以概率 $p_i$ 拿到第 $i$ 种卡，集齐的期望步数。

### 3.6 生成函数：把“每类选几个”变成多项式乘法

普通生成函数（OGF）把数列 $a_0, a_1, \dots$ 写成 $\sum a_n x^n$。它的用处是：有若干类物品，第 $i$ 类可以选的个数在集合 $A_i$ 里，问总共选 $n$ 个的方案数，答案就是 $\prod_i \big( \sum_{a \in A_i} x^a \big)$ 里 $x^n$ 的系数，因为展开乘积时从每个括号里挑一项，指数相加正好是总个数。常用的封闭形式：

$$\frac{1}{1-x} = \sum_{n \ge 0} x^n, \qquad \frac{1}{(1-x)^k} = \sum_{n \ge 0} \binom{n+k-1}{k-1} x^n, \qquad 1 + x + \dots + x^c = \frac{1 - x^{c+1}}{1-x}$$

第二条就是插板法。带上界的插板写成生成函数是 $\prod_j \frac{1 - x^{c_j+1}}{1-x}$，把分子展开，每一项对应 3.4 里容斥的一个子集，两种推法在这里会合。递推也能这样解：斐波那契的生成函数满足 $F = x + xF + x^2 F$，所以 $F = \frac{x}{1 - x - x^2}$，拆成部分分式就得到通项。

指数生成函数（EGF）写成 $\sum a_n \frac{x^n}{n!}$，用于有标号的对象。两个 EGF 相乘，系数是 $\sum_i \binom{n}{i} a_i b_{n-i}$，多出来的 $\binom{n}{i}$ 正是“$n$ 个标号里哪 $i$ 个分给第一部分”。所以 $e^x$ 是“一个集合”，$\frac{(e^x - 1)^k}{k!}$ 是分成 $k$ 个非空无序集合，系数就是 $S(n,k)$；错排的 EGF 是 $\frac{e^{-x}}{1-x}$。**拼接两个对象时，要决定标号怎么分给两边就用 EGF，不用决定就用 OGF。** 生成函数本身只是记账方式，项数一多就要用 3.7 的 NTT 去乘。

### 3.7 卷积与多项式：NTT 是生成函数的计算器

$c_k = \sum_{i+j=k} a_i b_j$ 就是两个多项式相乘，直接算 $O(n^2)$，FFT 和 NTT 做到 $O(n \log n)$。NTT 在模 998244353 下做，原根是 3，没有浮点误差，比赛里优先用它。在乘法之上还有一套多项式板子：求逆、对数、指数、开根，都是用牛顿迭代套在乘法上，$O(n \log n)$；分治 NTT 处理 $f_n = \sum_{i=0}^{n-1} f_i g_{n-i}$ 这种自己卷自己的递推，$O(n \log^2 n)$。

两样相关的工具也在这里。拉格朗日插值：答案已知是 $n$ 的 $k$ 次多项式（比如 $\sum_{i \le n} i^k$ 是 $k+1$ 次），就暴力算出 $k+2$ 个点，插值求任意 $n$，连续点处 $O(k)$。FWT 做的是按位运算的卷积 $c_k = \sum_{i \oplus j = k} a_i b_j$（$\oplus$ 可以是异或、或、与），$O(n \log n)$；对所有子集求和用 SOS DP，$O(2^n n)$。**题目要把很多多项式乘起来，或者答案是某个乘积的第 $n$ 项系数，就是 NTT 的信号。**

### 3.8 概率与期望

期望的线性性 $E[X + Y] = E[X] + E[Y]$ 不要求独立，这是期望题最常用的工具：把要求的量拆成一堆指示变量的和，每个指示变量的期望就是它那件事发生的概率。随机排列的不动点个数，拆成“第 $i$ 位是不是不动点”，每个概率 $\frac{1}{n}$，加起来期望是 1，不需要先求分布。集卡问题：已经集了 $j$ 种时，下一种新卡要等的步数是成功率 $\frac{n-j}{n}$ 的几何分布，期望 $\frac{n}{n-j}$，总期望是 $\sum_j \frac{n}{n-j} = n H_n$。

拆不开时设状态写方程。期望 DP 一般设 $E[s]$ 为从状态 $s$ 走到终点还要的期望步数，从终点往回推，因为终点的值已知（为 0），每个状态的值由它的后继决定。状态之间有环时，DP 的顺序排不出来，就把每个状态的方程都列出来，用 4.4 的高斯消元解。答案要求模 $p$ 的概率时，分数 $\frac{a}{b}$ 写成 $a \cdot b^{-1}$。**期望题先找线性性：把总量拆成指示变量，每个只问它发生的概率；拆不开再设状态写方程。**

### 3.9 其余计数工具：认出信号就行

| 题面信号 | 工具 |
|---|---|
| 旋转、翻转后相同算一种 | Burnside / Pólya：$\frac{1}{\lvert G \rvert} \sum_{g \in G} k^{c(g)}$，$c(g)$ 是置换 $g$ 的环数 |
| 有标号无根树计数，或者给定每个点的度数 | Prüfer 序列：共 $n^{n-2}$ 棵；度数为 $d_i$ 时 $\frac{(n-2)!}{\prod (d_i - 1)!}$ |
| 下标按位异或、或、与的卷积 | FWT |
| 对每个集合求它所有子集的和 | SOS DP |
| 生成树计数、不相交路径组计数 | 矩阵树定理、LGV（见 4.6） |

## 4. 线性代数

### 4.1 矩阵快速幂：线性递推的第 $10^{18}$ 项

如果每一步的状态向量都由上一步线性得到，$v_{i+1} = M v_i$，且 $M$ 不随 $i$ 变，那么 $v_n = M^{n-1} v_1$，用快速幂算 $M^{n-1}$ 只要 $O(k^3 \log n)$，$k$ 是向量的长度：

```cpp
using Mat = vector<vector<long long>>;

Mat mul(const Mat& A, const Mat& B) {
    int n = A.size(), K = B.size(), m = B[0].size();
    Mat C(n, vector<long long>(m, 0));
    for (int i = 0; i < n; i++)
        for (int k = 0; k < K; k++) {
            if (!A[i][k]) continue;
            for (int j = 0; j < m; j++) C[i][j] = (C[i][j] + A[i][k] * B[k][j]) % MOD;
        }
    return C;
}
Mat mpow(Mat A, long long e) {
    int n = A.size();
    Mat R(n, vector<long long>(n, 0));
    for (int i = 0; i < n; i++) R[i][i] = 1;
    for (; e > 0; e >>= 1, A = mul(A, A))
        if (e & 1) R = mul(R, A);
    return R;
}
```

**矩阵快速幂的难点不在快速幂，在状态：下一步公式里用到的每样东西都得在向量里。** 递推里有常数，就在向量里放一个 1；有下标 $i$，就放 $i$ 和 1，因为 $i + 1 = i + 1 \cdot 1$；要求前缀和，就放 $S_i$，并把 $S_{i+1} = S_i + a_{i+1}$ 里的 $a_{i+1}$ 按递推式展开。5.3 节完整做一道。

同一个工具还有两种常见用法。图的邻接矩阵 $A$ 的 $k$ 次幂里，$(A^k)_{uv}$ 是从 $u$ 到 $v$ 长度恰好为 $k$ 的路径数，因为每乘一次 $A$ 就多走一条边。转移固定、长度很大的 DP，比如长度为 $n$ 且不含某个模式串的字符串个数（状态是 KMP 自动机上的位置），转移写成矩阵也一样。

### 4.2 换一套加法和乘法：(min, +) 矩阵

矩阵乘法 $C_{ij} = \sum_k A_{ik} B_{kj}$ 能做快速幂，只用到两条性质：乘法满足结合律，乘法对加法有分配律。把“加”换成 $\min$、“乘”换成 $+$，这两条仍然成立，于是 $C_{ij} = \min_k (A_{ik} + B_{kj})$ 也能快速幂。$A$ 是边权矩阵时，它的 $k$ 次幂给出恰好走 $k$ 条边的最短路。(max, +) 同理。**只要新的“加”和“乘”满足结合律和分配律，快速幂就照样成立。** 这种矩阵放进线段树，还能处理带修改的 DP（动态 DP）。

### 4.3 写不出矩阵时：打表加 BM

如果答案是某个 $k$ 维固定线性转移跑出来的，即使不知道矩阵长什么样，数列也满足一个阶数不超过 $k$ 的线性递推：由 Cayley-Hamilton 定理，$M$ 满足自己的特征多项式，乘上初始向量就是 $a_n$ 的递推关系。Berlekamp-Massey 算法从前 $2k$ 项求出最短的线性递推，$O(k^2)$；有了 $k$ 阶递推，第 $n$ 项是 $x^n$ 对特征多项式取模，$O(k^2 \log n)$（用 NTT 可以更快）。

赛场上的用法是：暴力 DP 跑出前几百项，交给 BM 得到递推，再求第 $n$ 项。前提是背后的过程确实是固定的线性转移；保险起见，用求出的递推去预测几项暴力多算出来的值，对上了再交。**只要答案是某个固定线性转移跑出来的，它就满足线性递推：暴力跑出前几百项交给 BM，比手推矩阵快。**

### 4.4 高斯消元：三种数域

高斯消元逐列处理：在当前列找一个非零的主元行，换上来，用它把其余行这一列消成 0。实数域上选绝对值最大的主元，减小误差；模质数下除法换成乘逆元；模 2 下每行存成 bitset，消元就是异或，$O(n^3 / 64)$。消完看结果：出现 $0 = $ 非零的行就无解；主元个数等于未知数个数就唯一解；否则有自由元，每个自由元可以任取，解的个数是 $p^{\text{自由元数}}$（模 2 时是 $2^{\text{自由元数}}$）。

题面上有三类信号会落到线性方程组上。图上随机游走的期望，状态之间有环：$E_u = 1 + \frac{1}{\deg u} \sum_{v \sim u} E_v$，终点 $E = 0$，$n$ 个方程 $n$ 个未知数。开关灯一类的题：按一个开关改变若干灯，每个开关按奇数次还是偶数次是一个 0/1 未知数，每盏灯的最终状态是一个模 2 方程。还有各种异或约束。**期望有环、开关灯、异或约束，这三类题列出来都是线性方程组，解的个数看自由元。**

### 4.5 线性基：异或下的一组基

把每个数看成 GF(2) 上的向量，线性基是这组向量张成空间的一组基，插入时按最高位逐位消：

```cpp
struct XorBasis {
    unsigned long long b[64] = {};
    int rank = 0;
    bool insert(unsigned long long x) {
        for (int i = 63; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; rank++; return true; }
            x ^= b[i];
        }
        return false;              // x 能被已有的基异或出来
    }
    unsigned long long max_xor() const {
        unsigned long long r = 0;
        for (int i = 63; i >= 0; i--) r = max(r, r ^ b[i]);
        return r;
    }
};
```

设 $n$ 个数插完后秩为 $r$。能异或出的不同值正好 $2^r$ 个；每个能得到的值，由 $2^{n-r}$ 个子集得到（那 $n - r$ 个插入失败的数随便选，都能用基补回来）；最大异或值从高位往低位贪心。**线性基就是一边插入一边做的模 2 高斯消元，所有“子集异或”的问题都先想它。** 路径异或的题也会落到这里：图上两点间所有路径的异或值，等于任意一条路径的异或值再异或上若干个环，把每条非树边围成的环的异或值插进线性基即可。区间异或先转成前缀异或。

### 4.6 行列式与计数：矩阵树定理、LGV

模质数的行列式用高斯消元算：消成上三角，对角线乘起来，每交换一次行变一次号，$O(n^3)$：

```cpp
long long det(Mat a) {             // 模质数 MOD 下的行列式，元素要在 [0, MOD)
    int n = a.size();
    long long res = 1;
    for (int c = 0; c < n; c++) {
        int piv = -1;
        for (int r = c; r < n; r++)
            if (a[r][c]) { piv = r; break; }
        if (piv < 0) return 0;
        if (piv != c) { swap(a[piv], a[c]); res = MOD - res; }
        res = res * a[c][c] % MOD;
        long long iv = inv(a[c][c]);
        for (int r = c + 1; r < n; r++) {
            long long f = a[r][c] * iv % MOD;
            if (!f) continue;
            for (int j = c; j < n; j++) a[r][j] = (a[r][j] - f * a[c][j] % MOD + MOD) % MOD;
        }
    }
    return res;
}
```

矩阵树定理：无向图（可以有重边）的拉普拉斯矩阵 $L = D - A$，$D$ 是度数对角阵，$A$ 是邻接矩阵（重边计重数），删掉任意一行和同号的一列，剩下的行列式就是生成树个数。有向图数以 $r$ 为根的外向树，用入度矩阵减邻接矩阵，删掉第 $r$ 行第 $r$ 列。

LGV 引理：DAG 上有起点 $a_1..a_k$、终点 $b_1..b_k$，$e(a_i, b_j)$ 是两点间的路径数，那么行列式 $\det[e(a_i, b_j)]$ 等于所有两两不相交的路径组按配对方式的符号求和。网格图上起点和终点都按顺序排好时，不相交的路径组只可能是 $a_i \to b_i$，行列式就直接是方案数。**生成树计数、不相交路径计数这两类看起来是图论的题，答案都是一个行列式。**

## 5. 从 0 写三道题

三道题各对应一块，每道都按赛场的顺序走：看范围定复杂度，推式子，写代码，跟暴力对拍。

### 5.1 数论：gcd 求和

**题面。** $T$ 组询问，每组给 $n, m$，求 $\sum_{i=1}^{n} \sum_{j=1}^{m} \gcd(i, j)$。$T \le 1000$，$n, m \le 10^7$。

**看范围。** 每组 $O(nm)$ 不用想，每组 $O(n)$ 也要 $10^{10}$，所以每组只能 $O(\sqrt n)$ 左右，目标是化成 2.6 的 $\sum_d f(d) \lfloor n/d \rfloor \lfloor m/d \rfloor$，$f$ 的前缀和预处理到 $10^7$。

**推。** 用 $\varphi * \mathbf{1} = \mathrm{id}$ 把 $\gcd$ 拆成因子求和，再交换求和顺序：

$$\sum_{i=1}^{n} \sum_{j=1}^{m} \sum_{d \mid \gcd(i,j)} \varphi(d) = \sum_{d=1}^{\min(n,m)} \varphi(d) \left\lfloor \frac{n}{d} \right\rfloor \left\lfloor \frac{m}{d} \right\rfloor$$

不记得 $\varphi * \mathbf{1} = \mathrm{id}$ 也能推到同一个地方：换枚举对象，枚举 $\gcd = d$，个数用 2.7 第一道的结论，得到 $\sum_d d \sum_k \mu(k) \lfloor \frac{n}{dk} \rfloor \lfloor \frac{m}{dk} \rfloor$；令 $T = dk$，内层是 $\sum_{d \mid T} d\, \mu(T/d) = (\mathrm{id} * \mu)(T) = \varphi(T)$。两条路在同一个式子会合，说明式子大概率没推错。

**复杂度与空间。** 线性筛 $O(N)$，$N = 10^7$；每组询问不超过 $2(\sqrt n + \sqrt m)$ 段，1000 组约 $10^7$ 次。答案最大约 $10^{15}$，`long long` 够，不用取模。前缀和数组 $10^7$ 个 `long long` 占 80 MB，所以筛的时候直接把 $\varphi$ 写进这个数组，筛完再原地做前缀和，不另开 `phi`：

```cpp
#include <bits/stdc++.h>
using namespace std;

const int N = 10'000'000;

long long block_sum(long long n, long long m, const vector<long long>& pre) {
    long long res = 0;
    for (long long l = 1, r; l <= min(n, m); l = r + 1) {
        r = min(n / (n / l), m / (m / l));
        res += (pre[r] - pre[l - 1]) * (n / l) * (m / l);
    }
    return res;
}

int main() {
    // 线性筛求 φ，筛完再原地改成前缀和，省一个数组
    vector<long long> pre(N + 1);
    vector<int> primes;
    vector<bool> comp(N + 1);
    pre[1] = 1;
    for (int i = 2; i <= N; i++) {
        if (!comp[i]) { primes.push_back(i); pre[i] = i - 1; }
        for (int p : primes) {
            if ((long long)i * p > N) break;
            comp[i * p] = true;
            if (i % p == 0) { pre[i * p] = pre[i] * p; break; }
            pre[i * p] = pre[i] * (p - 1);
        }
    }
    for (int i = 1; i <= N; i++) pre[i] += pre[i - 1];

    int T;
    scanf("%d", &T);
    while (T--) {
        long long n, m;
        scanf("%lld %lld", &n, &m);
        printf("%lld\n", block_sum(n, m, pre));
    }
}
```

**对拍。** 30 组 $n, m \le 60$ 跟二重循环比，全对；$n = m = 10^7$ 输出 1004297420038032，在 `long long` 范围内。

### 5.2 组合：恰好用上 $m$ 种颜色

**题面。** $n$ 个格子排成一行，有 $k$ 种颜色，每格涂一种，相邻格子颜色不同，并且恰好用到其中 $m$ 种颜色（这 $m$ 种每种至少出现一次，其余颜色不出现）。求方案数模 $10^9+7$。$n \le 10^9$，$m \le k \le 10^6$。

**看范围。** $n$ 到 $10^9$，不能按格子 DP，$n$ 只能出现在快速幂的指数里；$k$ 到 $10^6$，可以接受 $O(k \log n)$。

**推。** 先选出用哪 $m$ 种颜色，$\binom{k}{m}$ 种；剩下的问题是用这 $m$ 种颜色、每种都用上、相邻不同，记为 $f(m)$。“每种都用上”是“恰好”，难数；放宽成“只用某 $j$ 种颜色里的、不要求用全”就好数：第一格 $j$ 种选法，之后每格只要跟前一格不同，各 $j - 1$ 种，

$$g(j) = j\,(j-1)^{n-1}$$

一个“只用这 $j$ 种”的方案，实际用到的颜色恰好是其中某 $i$ 种，所以 $g(j) = \sum_{i \le j} \binom{j}{i} f(i)$。这是 3.5 的“至多 ↔ 恰好”，反演得

$$f(m) = \sum_{j=1}^{m} (-1)^{m-j} \binom{m}{j}\, j\,(j-1)^{n-1}, \qquad \text{答案} = \binom{k}{m} f(m)$$

检查边界：$n = 1$ 时 $(j-1)^0 = 1$，$f(m) = \sum_j (-1)^{m-j} \binom{m}{j} j$，$m = 1$ 时为 1，$m \ge 2$ 时为 0，跟“一格只能用一种颜色”一致。

**复杂度。** 阶乘表 $O(k)$，求和 $m$ 项、每项一次快速幂，$O(m \log n)$。

```cpp
#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1'000'000'007;

long long qpow(long long a, long long e, long long m = MOD) {
    long long r = 1 % m;
    a %= m;
    if (a < 0) a += m;
    for (; e > 0; e >>= 1, a = a * a % m)
        if (e & 1) r = r * a % m;
    return r;
}
long long inv(long long a) { return qpow(a, MOD - 2); }

struct Binom {
    vector<long long> f, fi;
    Binom(int n) : f(n + 1), fi(n + 1) {
        f[0] = 1;
        for (int i = 1; i <= n; i++) f[i] = f[i - 1] * i % MOD;
        fi[n] = inv(f[n]);
        for (int i = n; i > 0; i--) fi[i - 1] = fi[i] * i % MOD;
    }
    long long C(int n, int k) const {
        if (k < 0 || k > n) return 0;
        return f[n] * fi[k] % MOD * fi[n - k] % MOD;
    }
};

// 恰好用上 m 种颜色（m 种都出现）、相邻不同、长度 n
long long exact_colors(long long n, int m, const Binom& B) {
    long long res = 0;
    for (int j = 1; j <= m; j++) {
        long long term = B.C(m, j) * j % MOD * qpow(j - 1, n - 1) % MOD;
        res += (m - j) % 2 ? MOD - term : term;
    }
    return res % MOD;
}

int main() {
    long long n;
    int k, m;
    scanf("%lld %d %d", &n, &k, &m);
    Binom B(k);
    printf("%lld\n", B.C(k, m) * exact_colors(n, m, B) % MOD);
}
```

**对拍。** $n \le 5$、$k \le 4$ 的所有 $(n, k, m)$ 跟枚举全部染色比，全对。

### 5.3 线性代数：带下标的递推求和

**题面。** $a_1 = a_2 = 1$，$a_i = a_{i-1} + a_{i-2} + i$（$i \ge 3$）。求 $S_n = \sum_{i=1}^{n} a_i \bmod 10^9+7$，$n \le 10^{18}$。

**看范围。** $10^{18}$ 只能 $O(\log n)$，递推是线性的，走矩阵快速幂。

**推。** 设计状态时问一句：从第 $i$ 项走到第 $i+1$ 项，公式里要用到什么。$a_{i+1} = a_i + a_{i-1} + (i+1)$ 要用 $a_i$、$a_{i-1}$、$i+1$；下一步的 $i+2 = (i+1) + 1$ 要用常数 1；$S_{i+1} = S_i + a_{i+1} = S_i + a_i + a_{i-1} + (i+1)$ 要用 $S_i$。于是状态取 $(a_i, a_{i-1}, i+1, 1, S_i)$，逐行写出转移：

$$\begin{pmatrix} a_{i+1} \\ a_i \\ i+2 \\ 1 \\ S_{i+1} \end{pmatrix} = \begin{pmatrix} 1 & 1 & 1 & 0 & 0 \\ 1 & 0 & 0 & 0 & 0 \\ 0 & 0 & 1 & 1 & 0 \\ 0 & 0 & 0 & 1 & 0 \\ 1 & 1 & 1 & 0 & 1 \end{pmatrix} \begin{pmatrix} a_i \\ a_{i-1} \\ i+1 \\ 1 \\ S_i \end{pmatrix}$$

从 $i = 2$ 的 $(1, 1, 3, 1, 2)$ 出发，乘 $n - 2$ 次到第 $n$ 项，$n = 1$ 单独处理。

**复杂度。** $5^3 \times 60 \approx 7500$ 次乘法。

```cpp
#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1'000'000'007;
using Mat = vector<vector<long long>>;

Mat mul(const Mat& A, const Mat& B) {
    int n = A.size(), K = B.size(), m = B[0].size();
    Mat C(n, vector<long long>(m, 0));
    for (int i = 0; i < n; i++)
        for (int k = 0; k < K; k++) {
            if (!A[i][k]) continue;
            for (int j = 0; j < m; j++) C[i][j] = (C[i][j] + A[i][k] * B[k][j]) % MOD;
        }
    return C;
}
Mat mpow(Mat A, long long e) {
    int n = A.size();
    Mat R(n, vector<long long>(n, 0));
    for (int i = 0; i < n; i++) R[i][i] = 1;
    for (; e > 0; e >>= 1, A = mul(A, A))
        if (e & 1) R = mul(R, A);
    return R;
}

int main() {
    long long n;
    scanf("%lld", &n);
    if (n == 1) { puts("1"); return 0; }
    // 状态 (a_i, a_{i-1}, i+1, 1, S_i)，从 i = 2 走到 i = n
    Mat M = {{1, 1, 1, 0, 0},
             {1, 0, 0, 0, 0},
             {0, 0, 1, 1, 0},
             {0, 0, 0, 1, 0},
             {1, 1, 1, 0, 1}};
    Mat v = {{1}, {1}, {3}, {1}, {2}};
    printf("%lld\n", mul(mpow(M, n - 2), v)[4][0]);
}
```

**对拍。** $n < 60$ 跟直接递推比，全对。这道题也可以不推矩阵：暴力算出前几十项交给 BM，会得到一个 5 阶递推，跟状态向量的长度一致。

## 练习

每道题先想清楚三件事：范围说明了什么复杂度，用的是第 1.3 节哪几个动作，最后化成了什么式子。

数论：
- [洛谷 P1082 同余方程](https://www.luogu.com.cn/problem/P1082)：exgcd 求逆元。
- [洛谷 P4777 扩展中国剩余定理](https://www.luogu.com.cn/problem/P4777)：模数不互质的两两合并，注意溢出。
- [洛谷 P2257 YY的GCD](https://www.luogu.com.cn/problem/P2257)：2.7 第三道，$g(T)$ 怎么预处理。
- [洛谷 P1829 Crash的数字表格](https://www.luogu.com.cn/problem/P1829)：$\operatorname{lcm}$ 求和，两层分块。
- [洛谷 P4213 杜教筛](https://www.luogu.com.cn/problem/P4213)：$\sum \varphi$ 和 $\sum \mu$，$n$ 到 $2^{31}$。

组合计数：
- [洛谷 P1641 生成字符串](https://www.luogu.com.cn/problem/P1641)：反射法，上下步数不相等。
- [洛谷 P1450 硬币购物](https://www.luogu.com.cn/problem/P1450)：上界用容斥，四种硬币 $2^4$ 个子集。
- [洛谷 P4859 已经没有什么好害怕的了](https://www.luogu.com.cn/problem/P4859)：钦定 ↔ 恰好，$g$ 要配一个 DP。
- [洛谷 P4451 整数的lqp拆分](https://www.luogu.com.cn/problem/P4451)：生成函数求闭式。

线性代数：
- [洛谷 P2886 Cow Relays](https://www.luogu.com.cn/problem/P2886)：(min, +) 矩阵快速幂。
- [洛谷 P3232 游走](https://www.luogu.com.cn/problem/P3232)：期望列方程、高斯消元，再加一步贪心。
- [洛谷 P4570 元素](https://www.luogu.com.cn/problem/P4570)：线性基加贪心。
- [洛谷 P4111 小 Z 的房间](https://www.luogu.com.cn/problem/P4111)：矩阵树定理，模数不是质数。
