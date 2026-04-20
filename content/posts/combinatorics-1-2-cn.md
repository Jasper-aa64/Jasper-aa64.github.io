---
title: "Combinatorics #1.2：容斥原理、不定方程、错排"
date: 2026-04-20
slug: "combinatorics-1-2-cn"
description: "容斥原理的集合与算子形式、有上下界不定方程计数（前缀和DP与分治NTT）、错排公式与第二类斯特林数。"
summary: "容斥原理的集合与算子形式、有上下界不定方程计数（前缀和DP与分治NTT）、错排公式与第二类斯特林数。"
categories: [Combinatorics]
tags: [数学, 组合数学, 容斥原理, 错排, 不定方程, 斯特林数, 计数, NTT, 生成函数]
math: true
toc: true
---

# 1 基础

**定理（容斥原理，两个子集）**  
设 $S$ 是有限集，$A,B\subseteq S$，则

$$|S \setminus (A\cup B)| = |S| - |A| - |B| + |A\cap B|$$

**定理（容斥原理，三个子集）**  
设 $A,B,C\subseteq S$，则

$$|S \setminus (A\cup B\cup C)| = |S| - |A| - |B| - |C| + |A\cap B| + |A\cap C| + |B\cap C| - |A\cap B\cap C|$$

**定理（容斥原理，一般形式）**  
设 $A_1,A_2,\dots,A_n\subseteq S$，则

$$\left|S \setminus \bigcup_{i=1}^{n} A_i\right| = \sum_{i=0}^{n} (-1)^i \sum_{1\le j_1<\cdots<j_i\le n} \left|\bigcap_{k=1}^{i} A_{j_k}\right|$$

**算子形式**  
设 $A_i$ 为一种"坏性质"，$N(A_{i_1}\cdots A_{i_k})$ 为同时具备这些性质的元素个数，则

$$N\!\left(\prod_{i=1}^{n}(1-A_i)\right) = \sum_{T\subseteq[n]}(-1)^{|T|}\, N\!\left(\prod_{i\in T}A_i\right)$$

算子形式便于推导：将乘积展开后，对每一个交项 $N(\cdots)$ 做计数即可。

# 2 例题

## 2.1 Euler 函数

**命题：** $n=p_1^{\alpha_1}\cdots p_k^{\alpha_k}$，则

$$\varphi(n)=n\prod_{i=1}^{k}\left(1-\frac{1}{p_i}\right)$$

**证明：** 令 $S=\{1,\dots,n\}$，$A_i=\{x\in S\mid p_i\mid x\}$。对任意 $T\subseteq\{1,\dots,k\}$，

$$\left|\bigcap_{i\in T}A_i\right|=\frac{n}{\prod_{i\in T}p_i}$$

（因为每个 $p_i$ 均整除 $n$）。将容斥展开后，恰好得到乘积公式。

---

**例题（Nowcoder 19857）**

$N$ 对情侣共 $2N$ 人围成一个环，要求任意一对情侣不相邻。两方案若能通过旋转互相得到则视为相同（不考虑镜像翻转），求方案数。

设事件 $A_i$：第 $i$ 对情侣相邻。固定选中 $i$ 对相邻时：
- 把每对合并为一个块，内部有 2 种次序，贡献 $2^i$；
- 环上共 $2N-i$ 个物体，圆排列数为 $(2N-i-1)!$。

$$\boxed{\text{Ans}=\sum_{i=0}^{N}(-1)^i\binom{N}{i}2^i(2N-i-1)!}$$

---

## 2.2 满射：每个人至少得到一件物品

$m$ 件有标号物品分给 $n$ 个有标号的人，每人至少得到一件，求方案数。

令 $A_i$：第 $i$ 个人空手。$|S|=n^m$；若固定 $t$ 个人空手，则每件物品有 $n-t$ 个去向：

$$\boxed{\sum_{t=0}^{n}(-1)^t\binom{n}{t}(n-t)^m}$$

等价写法（Stirling 数）：$n!\,S_2(m,n)$，即先将 $m$ 件物品分成 $n$ 个非空无标号组，再给组贴标签。

推广：恰好有 $r$ 个人得到物品的方案数为 $\displaystyle\binom{n}{r}r!\,S_2(m,r)$。

---

**例题（无序分组）**

$2n$ 个元素 $a_1,\dots,a_n,b_1,\dots,b_n$ 的全排列中，无任意一对 $(a_i,b_i)$ 相邻，求排列数。

固定 $k$ 对必须相邻时，每对合并为一块（2 种内部次序），总块数 $2n-k$，排列数 $(2n-k)!$，故

$$N(A_{i_1}\cdots A_{i_k})=2^k(2n-k)!$$

$$\boxed{\sum_{k=0}^{n}(-1)^k\binom{n}{k}2^k(2n-k)!}$$

## 2.3 不定方程的解数量（含上下界，容斥式）

求整数解数：

$$x_1+x_2+\cdots+x_k=n,\qquad l_i\le x_i\le r_i$$

**去下界：** 令 $y_i=x_i-l_i$，$U_i=r_i-l_i$，$N=n-\sum l_i$，化为 $\sum y_i=N$，$0\le y_i\le U_i$。若 $N<0$ 或 $N>\sum U_i$，答案为 0。

**容斥：** 令 $A_i$：$y_i\ge U_i+1$（超上界）。

$$\boxed{\#=\sum_{T\subseteq[k]}(-1)^{|T|}\binom{N-\sum_{i\in T}(U_i+1)+(k-1)}{k-1}}$$

等价原变量形式：

$$\#=\sum_{T\subseteq[k]}(-1)^{|T|}\binom{n-\sum_{i=1}^k l_i-\sum_{i\in T}(r_i-l_i+1)+(k-1)}{k-1}$$

直接枚举子集复杂度 $O(k2^k)$，每项 $O(1)$（需预处理组合数）。

## 2.4 前缀和优化 DP $O(kN)$

设 $dp[i][s]$ 为"用前 $i$ 个变量凑出和 $s$ 的方案数"，初值 $dp[0][0]=1$。朴素转移：

$$dp[i][s]=\sum_{x=0}^{\min(U_i,s)}dp[i-1][s-x]$$

令 $\text{pref}[t]=\sum_{u=0}^{t}dp[i-1][u]$，则

$$dp[i][s]=\text{pref}[s]-\text{pref}[s-U_i-1]$$

（约定 $\text{pref}[-1]=0$），每个状态 $O(1)$，总复杂度 $O(kN)$，滚动数组空间 $O(N)$。

```cpp
#include <bits/stdc++.h>
using namespace std;
const int MOD = 1000000007;
inline int add(int a,int b){ a+=b; if(a>=MOD) a-=MOD; return a; }

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int k; long long n; cin>>k>>n;
    vector<long long> L(k), R(k);
    for(int i=0;i<k;++i) cin>>L[i]>>R[i];

    long long sumL=0, sumU=0; vector<int> U(k);
    for(int i=0;i<k;++i){
        sumL+=L[i]; long long ui=R[i]-L[i];
        if(ui<0){ cout<<0<<"\n"; return 0; }
        U[i]=(int)ui; sumU+=ui;
    }
    long long N64=n-sumL;
    if(N64<0||N64>sumU){ cout<<0<<"\n"; return 0; }
    int N=(int)N64;

    vector<int> prev(N+1,0), cur(N+1,0), pref(N+1,0);
    prev[0]=1; int reach=0;
    for(int i=0;i<k;++i){
        reach=min(N,reach+U[i]);
        int run=0;
        for(int s=0;s<=reach;++s){ run=add(run,prev[s]); pref[s]=run; }
        for(int s=0;s<=reach;++s){
            int left=s-U[i]-1;
            int val=pref[s];
            if(left>=0){ val-=pref[left]; if(val<0) val+=MOD; }
            cur[s]=val;
        }
        for(int s=reach+1;s<=N;++s) cur[s]=0;
        swap(prev,cur);
    }
    cout<<prev[N]<<"\n";
    return 0;
}
```

## 2.5 分治 NTT $O(N\log N\log k)$

每个变量 $y_i\in[0,U_i]$ 对应多项式 $P_i(x)=1+x+\cdots+x^{U_i}$，答案即

$$[x^N]\prod_{i=1}^{k}P_i(x)$$

将 $k$ 个多项式做分治合并，每次卷积后截断到 $x^N$，时间 $O(N\log N)$；树高 $\log k$，总复杂度 $O(N\log N\log k)$。

```cpp
// 截断卷积：只保留到 x^lim
vector<int> conv_trunc(vector<int> A, vector<int> B, int lim){
    if(A.empty()||B.empty()) return {};
    if((int)A.size()>lim+1) A.resize(lim+1);
    if((int)B.size()>lim+1) B.resize(lim+1);
    int need=(int)A.size()+(int)B.size()-1;
    int n=1; while(n<need) n<<=1;
    A.resize(n); B.resize(n);
    ntt(A,false); ntt(B,false);
    for(int i=0;i<n;++i) A[i]=(int)(1LL*A[i]*B[i]%M);
    ntt(A,true);
    A.resize(min(need,lim+1));
    return A;
}

vector<int> multiply_range(vector<vector<int>>& polys, int l, int r, int N){
    if(r-l==1) return polys[l];
    int m=(l+r)>>1;
    auto L=multiply_range(polys,l,m,N);
    auto R=multiply_range(polys,m,r,N);
    return conv_trunc(L,R,N);
}
```

## 2.6 等上界情形 $O(S/k)$

$n$ 个变量各在 $[0,k]$ 内，之和为 $S$，求方案数。

无上界时答案为 $\binom{S+n-1}{n-1}$（隔板法）。设 $i$ 个变量违反上界（即 $>k$），对其做变量替换 $y=x-(k+1)\ge0$，总和变为 $S-i(k+1)$：

$$g(n,S,k)=\sum_{i=0}^{\lfloor S/(k+1)\rfloor}(-1)^i\binom{n}{i}\binom{S-i(k+1)+n-1}{n-1}$$

当 $i>\lfloor S/(k+1)\rfloor$ 时，$S-i(k+1)<0$ 使组合数为 0，故求和项数约为 $S/(k+1)$，即 $O(S/k)$。

若 $k\ge S$，上界无效，直接返回 $\binom{S+n-1}{n-1}$。

# 3 错排

$p$ 是 $\{1,2,\dots,n\}$ 的排列，且 $\forall i,\ p_i\ne i$，记满足条件的排列数为 $D(n)$。

## 3.1 递推式

$$D(0)=1,\quad D(1)=0,\quad D(n)=(n-1)\bigl(D(n-1)+D(n-2)\bigr)\quad(n\ge2)$$

```cpp
D[0]=1; D[1]=0;
for(int i=2;i<=MAXN;++i)
    D[i]=1LL*(i-1)*(D[i-1]+D[i-2])%MOD;
```

## 3.2 容斥公式

令 $A_i$：位置 $i$ 被自己占据（$p_i=i$）。$|S|=n!$，固定 $k$ 个位置后剩余 $(n-k)!$ 种排列：

$$D(n)=\left|S\setminus\bigcup_{i=1}^{n}A_i\right|=\sum_{k=0}^{n}(-1)^k\binom{n}{k}(n-k)!$$

$$\boxed{D(n)=n!\sum_{k=0}^{n}\frac{(-1)^k}{k!}},\qquad \frac{D(n)}{n!}\xrightarrow{n\to\infty}\frac{1}{e}$$

## 3.3 指数型生成函数

置换 = 若干置换环（圆排列）的无标号集合。环长 $k$ 的圆排列数 $(k-1)!$，在 EGF 中贡献 $\frac{(k-1)!}{k!}x^k=\frac{x^k}{k}$，故

$$\text{CYC}(x)=\sum_{k\ge1}\frac{x^k}{k}=-\ln(1-x)$$

错排禁止 1-环：

$$\text{CYC}_{\ge2}(x)=-\ln(1-x)-x$$

$$\boxed{H(x)=\exp\bigl(\text{CYC}_{\ge2}(x)\bigr)=\frac{e^{-x}}{1-x}}$$

展开后提取 $[x^n]$ 即得容斥公式。

## 3.4 二项式反演

设 $f_n$：恰有 0 个不动点的排列数（即 $D(n)$），$g_n=n!$（至多 $n$ 个不动点）。由二项式反演：

$$f_n=\sum_{i=0}^{n}\binom{n}{i}(-1)^{n-i}i!$$

与容斥结果一致，$O(n)$。

## 3.5 恰好有 $k$ 个不动点

1. 选出哪 $k$ 个位置固定：$\binom{n}{k}$ 种。
2. 在剩余 $n-k$ 个位置上做错排：$D(n-k)$ 种。

$$\boxed{\binom{n}{k}D(n-k)}$$

展开即

$$\binom{n}{k}\sum_{i=0}^{n-k}(-1)^i\binom{n-k}{i}(n-k-i)!$$

# 4 第二类斯特林数 $S_2(n,k)$

将 $n$ 个有标号球放入 $k$ 个**无标号**非空盒子的方案数，记作 $S_2(n,k)$ 或 $\left\{\begin{smallmatrix}n\\k\end{smallmatrix}\right\}$。

**递推关系：**

$$S_2(n,k)=k\cdot S_2(n-1,k)+S_2(n-1,k-1)$$

（第 $n$ 个球放入已有 $k$ 个盒之一，或独自开一个新盒）

**通项公式：**

$$S_2(n,k)=\frac{1}{k!}\sum_{i=0}^{k}(-1)^i\binom{k}{i}(k-i)^n$$

**重要公式（下降幂展开）：**

$$x^n=\sum_{k=0}^{n}S_2(n,k)\,x^{\underline{k}},\qquad x^{\underline{k}}=x(x-1)\cdots(x-k+1)$$

与满射的联系：将 $n$ 件物品放入 $k$ 个**有标号**非空盒子的方案数为 $k!\,S_2(n,k)$。

# 5 例题

## 5.1 区间内与素数集合互质的整数个数

**题意（Nowcoder 16513）：** 给定只含素数的集合 $A=\{a_1,\dots,a_k\}$（$k\le20$），统计 $[L,R]$ 内不被任何 $a_i$ 整除的正整数个数。

令

$$F(X)=\#\{1\le n\le X:\forall a\in A,\ a\nmid n\}$$

由容斥：

$$F(X)=\sum_{S\subseteq A}(-1)^{|S|}\left\lfloor\frac{X}{\prod_{a\in S}a}\right\rfloor$$

答案为 $F(R)-F(L-1)$，复杂度 $O(2^k)$（乘积超过 $X$ 时剪枝）。

> **补充：** 区间 $[L,R]$ 内 $d$ 的倍数个数
> $$\left\lfloor\frac{R}{d}\right\rfloor-\left\lfloor\frac{L-1}{d}\right\rfloor$$
> 是"$[L,R]$ 问题 → $(R)-(L-1)$ → $[1,n]$ 问题"的经典套路。

## 5.2 动态互质对计数

**题意（CF 547C）：** 动态维护一个集合 $S$（插入/删除），每次操作后输出 $S$ 中满足 $\gcd(a_i,a_j)=1$ 的对数。

**法一（容斥）：** 维护 $\text{cnt}[d]$：$S$ 中被 $d$ 整除的元素个数。插入值 $v$（质因子集合 $\{p_1,\dots,p_m\}$）时，与现有元素互质的数目为

$$\sum_{S\subseteq\{p_1,\dots,p_m\}}(-1)^{|S|}\text{cnt}\!\left[\prod_{p\in S}p\right]$$

更新 $\text{cnt}[d]$ 对所有 $2^m$ 个无平方因子因数。删除时先更新 $\text{cnt}$ 再算差量。

**法二（Möbius 反演）：**

$$\sum_{y\in S}\mathbf{1}[\gcd(v,y)=1]=\sum_{d\mid v}\mu(d)\cdot\text{cnt}[d]$$

两种方法每次操作均为 $O(2^{\omega(v)})$，$v\le5\times10^5$ 时 $\omega(v)\le7$。
