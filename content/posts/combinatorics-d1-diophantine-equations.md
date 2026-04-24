---
title: "Combinatorics D1: Diophantine Equations"
date: 2026-04-24
slug: "combinatorics-d1-diophantine-equations"
description: "Stars and bars, bounded Diophantine equations via inclusion-exclusion, prefix-sum DP, D&C NTT, equal-cap formula, and a full worked example on CF 2127F."
summary: "Stars and bars, bounded Diophantine equations via inclusion-exclusion, prefix-sum DP, D&C NTT, equal-cap formula, and a full worked example on CF 2127F."
categories: [Combinatorics]
tags: [math, combinatorics, diophantine, stars-and-bars, inclusion-exclusion, dp, ntt, hockey-stick]
math: true
toc: true
---

# 1 Stars and Bars (Unconstrained / Simple Bounds)

Count non-negative integer solutions of
$$x_1 + x_2 + \cdots + x_k = n, \quad x_i \ge 0.$$

**Model.** Represent the $n$ units as $n$ identical balls placed into $k$ labeled bins. Insert $k-1$ dividers to separate bins. Together the $n$ balls and $k-1$ dividers occupy $n+k-1$ slots; choosing which $k-1$ slots hold dividers determines the solution:
$$\boxed{\binom{n+k-1}{k-1}}$$

**Strictly positive** ($x_i \ge 1$): substitute $y_i = x_i - 1 \ge 0$, so $\sum y_i = n - k$. Requires $n \ge k$; formula:
$$\binom{n-1}{k-1}$$

**Lower bounds** ($x_i \ge a_i$): substitute $y_i = x_i - a_i \ge 0$, so $\sum y_i = n - \sum a_i$. Requires $n \ge \sum a_i$; formula:
$$\binom{n - \sum_{i=1}^k a_i + k - 1}{k-1}$$

**At most $n$** ($x_1 + \cdots + x_k \le n$, each $x_i \ge 0$):
- Add a slack variable $Z \ge 0$, so $x_1 + \cdots + x_k + Z = n$.
- Now $k+1$ variables summing to $n$:
$$\binom{n+k}{k}$$

---

# 2 Bounded Diophantine — Inclusion-Exclusion Formula

**Count** non-negative integer solutions of
$$x_1 + x_2 + \cdots + x_k = n, \quad l_i \le x_i \le r_i.$$

## 2.1 Setup

**Shift to zero lower-bounds.** Let $y_i = x_i - l_i \ge 0$, $U_i = r_i - l_i$, $N = n - \sum l_i$.

- If $N < 0$ or $N > \sum U_i$: answer is $0$.
- Otherwise count: $y_1 + \cdots + y_k = N$, $0 \le y_i \le U_i$.

## 2.2 Inclusion-Exclusion

Let $A_i$ be the "bad" event $y_i \ge U_i + 1$ (upper bound violated).

**Unconstrained count** ($y_i \ge 0$, no upper bound): $\binom{N+k-1}{k-1}$.

**Forced violation of subset $T$.** If every $i \in T$ satisfies $y_i \ge U_i + 1$, substitute $z_i = y_i - (U_i+1) \ge 0$. The new target sum is $N - \sum_{i\in T}(U_i+1)$. Count:
$$\binom{N - \sum_{i\in T}(U_i+1) + k - 1}{k-1}$$

where $M = N - \sum_{i\in T}(U_i+1)$; the term is $0$ when $M < 0$.

**Inclusion-exclusion over all subsets:**
$$\boxed{\#\ =\ \sum_{T \subseteq [k]} (-1)^{|T|} \binom{N - \sum_{i\in T}(U_i+1) + k-1}{k-1}}$$
Direct evaluation: $O(k \cdot 2^k)$.

---

# 3 Prefix-Sum DP — $O(kN)$

Define $dp[i][s]$ = number of ways to make sum $s$ using the first $i$ variables $y_1, \dots, y_i$ (each in $[0, U_i]$).

**Base:** $dp[0][0] = 1$.

**Transition.** $y_i$ contributes any value in $[0, U_i]$, so:
$$dp[i][s] = \sum_{v=0}^{\min(s,U_i)} dp[i-1][s-v] = \mathrm{pref}[s] - \mathrm{pref}[s - U_i - 1]$$

where $\mathrm{pref}[t] = \sum_{u=0}^{t} dp[i-1][u]$ and $\mathrm{pref}[-1] = 0$.

Rolling arrays reduce space to $O(N)$.

**Answer:** $dp[k][N]$ (mod $10^9+7$).

> If $N$ itself exceeds available memory or time budget, this DP is not applicable — use the NTT method instead.

```cpp
#include <bits/stdc++.h>
using namespace std;
const int MOD = 1000000007;
inline int add(int a,int b){ a+=b; if(a>=MOD) a-=MOD; return a; }

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int k; long long n; cin>>k>>n;
    vector<long long> L(k),R(k);
    for(int i=0;i<k;++i) cin>>L[i]>>R[i];

    long long sumL=0,sumU=0;
    vector<long long> U64(k);
    for(int i=0;i<k;++i){
        sumL+=L[i];
        long long ui=R[i]-L[i];
        if(ui<0){ cout<<0<<"\n"; return 0; }
        U64[i]=ui; sumU+=ui;
    }
    long long N64=n-sumL;
    if(N64<0||N64>sumU){ cout<<0<<"\n"; return 0; }
    int N=(int)N64;

    // clamp each U_i to N — anything larger never affects the DP
    vector<int> U(k);
    for(int i=0;i<k;++i) U[i]=(int)min(U64[i],N64);

    vector<int> prev(N+1,0),cur(N+1,0),pref(N+1,0);
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
    cout<<prev[N]<<"\n";   // answer mod 10^9+7
}
```

---

# 4 Divide-and-Conquer NTT — Generating Function Method

Each variable $y_i \in [0, U_i]$ corresponds to the generating polynomial
$$P_i(x) = 1 + x + x^2 + \cdots + x^{U_i}.$$

The answer is $[x^N]\displaystyle\prod_{i=1}^k P_i(x)$.

**Strategy.** Merge the $k$ polynomials with divide-and-conquer; at each merge truncate to degree $N$ to avoid unnecessary growth.

**Complexity.** Each merge node $v$ performs one convolution of cost $O(d_v \log d_v)$ where $d_v$ is the effective polynomial length at that node (capped at $N+1$). Total cost:
$$O\!\left(\sum_{\text{merge node }v} d_v \log d_v\right)$$
Since every truncation keeps $d_v \le N+1$, in the common case where polynomial lengths grow gradually across levels this is approximately $O(N \log N \log k)$. In the worst case (e.g. all $k$ polynomials already of length $\Theta(N)$ at the leaves) it can reach $O(kN \log N)$.

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MOD = 998244353;
const int G   = 3;

long long pw(long long a, long long b, long long mod = MOD) {
    long long r = 1; a %= mod;
    for (; b > 0; b >>= 1) { if (b & 1) r = r * a % mod; a = a * a % mod; }
    return r;
}

void ntt(vector<int>& a, bool inv) {
    int n = a.size();
    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) swap(a[i], a[j]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        long long w = inv ? pw(G, MOD - 1 - (MOD - 1) / len)
                         : pw(G, (MOD - 1) / len);
        for (int i = 0; i < n; i += len) {
            long long wn = 1;
            for (int j = 0; j < len / 2; ++j) {
                int u = a[i + j], v = (long long)a[i + j + len/2] * wn % MOD;
                a[i + j]          = u + v >= MOD ? u + v - MOD : u + v;
                a[i + j + len/2]  = u - v <    0 ? u - v + MOD : u - v;
                wn = wn * w % MOD;
            }
        }
    }
    if (inv) {
        long long inv_n = pw(n, MOD - 2);
        for (auto& x : a) x = (long long)x * inv_n % MOD;
    }
}

// multiply A and B, keep only coefficients [0..lim]
vector<int> conv_trunc(vector<int> A, vector<int> B, int lim) {
    if (A.empty() || B.empty()) return {};
    if ((int)A.size() > lim + 1) A.resize(lim + 1);
    if ((int)B.size() > lim + 1) B.resize(lim + 1);
    int need = (int)A.size() + (int)B.size() - 1;
    int n = 1; while (n < need) n <<= 1;
    A.resize(n); B.resize(n);
    ntt(A, false); ntt(B, false);
    for (int i = 0; i < n; ++i) A[i] = (long long)A[i] * B[i] % MOD;
    ntt(A, true);
    A.resize(min(need, lim + 1));
    return A;
}

// D&C: product of polys[l..r), coefficients truncated to degree N
vector<int> dc(vector<vector<int>>& polys, int l, int r, int N) {
    if (r - l == 1) return polys[l];
    int m = (l + r) >> 1;
    return conv_trunc(dc(polys, l, m, N), dc(polys, m, r, N), N);
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int k; long long n; cin >> k >> n;
    vector<long long> L(k), R(k);
    for (int i = 0; i < k; ++i) cin >> L[i] >> R[i];

    long long sumL = 0, sumU = 0;
    vector<long long> U64(k);
    for (int i = 0; i < k; ++i) {
        sumL += L[i];
        long long ui = R[i] - L[i];
        if (ui < 0) { cout << 0 << "\n"; return 0; }
        U64[i] = ui; sumU += ui;
    }
    long long N64 = n - sumL;
    if (N64 < 0 || N64 > sumU) { cout << 0 << "\n"; return 0; }
    int N = (int)N64;

    // P_i(x) = 1 + x + ... + x^{min(U_i, N)}  (higher terms never contribute)
    vector<vector<int>> polys(k);
    for (int i = 0; i < k; ++i) {
        int len = (int)min(U64[i], (long long)N) + 1;
        polys[i].assign(len, 1);
    }

    auto res = dc(polys, 0, k, N);
    cout << (N < (int)res.size() ? res[N] : 0) << "\n";  // answer mod 998244353
    return 0;
}
```

---

# 5 Equal-Cap Case

$n$ variables each in $[0, k]$, sum $= S$.

Let $A_j$: variable $j$ exceeds $k$ (i.e. $y_j \ge k+1$). By symmetry every size-$i$ intersection has the same count, so:

$$\boxed{g(n,S,k)=\sum_{i=0}^{\min\!\left(n,\,\lfloor S/(k+1)\rfloor\right)}(-1)^i\binom{n}{i}\binom{S-i(k+1)+n-1}{n-1}}$$

The upper limit is $\min\!\bigl(n,\lfloor S/(k+1)\rfloor\bigr)$: at most $n$ variables can violate the bound, and terms with $S-i(k+1)<0$ vanish. Complexity:
$$O\!\left(\min\!\left(n,\left\lfloor\frac{S}{k+1}\right\rfloor\right)\right)$$

**Special case.** If $k \ge S$, no upper bound is ever tight: answer $= \dbinom{S+n-1}{n-1}$.

**Boundary.** If $S < 0$ or $S > nk$, the answer is $0$.

---

# 6 Example — [CF 2127F](https://codeforces.com/contest/2127/problem/F)

> Combinatorics + Inclusion-Exclusion + Hockey-Stick Identity

## 6.1 Linearise the Sum

After substituting the sum variable, both $A(M)$ and $B(M)$ below reduce to sums of the form
$$\mathrm{Cnt}(k,\,y,\,M)=\#\bigl\{k\text{ variables in }[0,M]\text{ summing to }y\bigr\}$$
weighted by $y$ (or shifted versions thereof). Concretely:

- Let $k_1=n-2$, window $[L_A,U_A]=[\max(0,S-(M-1)),\,\min(S,k_1 M)]$,
$$A(M)=\sum_{y=L_A}^{U_A}(y+M-S)\cdot\mathrm{Cnt}(k_1,y,M).$$
- Let $k_2=n-3$, window $[L_B,U_B]=[\max(0,S-2M+1),\,\min(S-M,k_2 M)]$,
$$B(M)=\sum_{y=L_B}^{U_B}(y+2M-S)\cdot\mathrm{Cnt}(k_2,y,M).$$

## 6.2 Problem Statement

Given integers $n$ and $m$. A **snake array** $a_1,\dots,a_n$ satisfies:
1. $0\le a_i\le m$;
2. $\sum a_i = m$;
3. $a_n = \max(a_1,\dots,a_n)$.

Define function $f(a)$ as follows (pseudocode): starting at $\mathrm{pos}=1$, if $a_{\mathrm{pos}}\lt a_n$ jump to the first position to the right with a strictly larger value and add the difference to the answer; otherwise increment $\mathrm{pos}$. Compute the sum of $f(a)$ over all snake arrays, modulo $10^9+7$.

## 6.3 Algorithm

### 6.3.1 Simplify $f(a)$

Let $M=a_n$. Tracing through the process: whenever we are at some position $i$ with $a_i \lt M$, we keep jumping to the "next greater" until we reach $a_n$, accumulating $M - a_i$.

Which positions $i$ serve as "segment heads"? Exactly those satisfying:
- $i=1$ and $a_1 \lt M$, or
- $i\ge 2$, $a_{i-1}=M$, and $a_i \lt M$.

This gives the clean formula:
$$f(a)=\sum_{i=1}^{n-1}(M-a_i)\cdot\bigl[a_i\lt M\;\wedge\;(i=1\text{ or }a_{i-1}=M)\bigr].$$

### 6.3.2 Enumerate the Maximum $M$

The snake-array conditions are equivalent to: fix $M\in[0,m]$ as the maximum, let the first $n-1$ entries satisfy $0\le a_i\le M$ and $\sum_{i=1}^{n-1}a_i = S:=m-M$, and set $a_n=M$.

For fixed $M$, linearity lets us split the contribution into two types:

- **Position $i=1$:**
$$A(M)=\sum_{x=0}^{M-1}(M-x)\cdot\#\bigl\{(a_2,\dots,a_{n-1})\in[0,M]^{n-2}:\textstyle\sum a=S-x\bigr\}.$$
- **Position $i\ge2$** (requires $a_{i-1}=M$):
$$B(M)=\sum_{x=0}^{M-1}(M-x)\cdot\#\bigl\{n-3\text{ variables in }[0,M]:\textstyle\sum a=S-M-x\bigr\}.$$

By symmetry every $i\in\{2,\dots,n-1\}$ contributes equally, so the total contribution from these positions is $(n-2)\cdot B(M)$.

The answer is therefore:
$$\mathrm{Ans}=\sum_{M=0}^{m}\bigl(A(M)+(n-2)\,B(M)\bigr).$$

### 6.3.3 Count $t$ Ordered Integers in $[0,k]$ Summing to $S$

**1. Unconstrained (stars and bars).** If $x_i\ge0$ with no upper bound, the count is $\binom{S+t-1}{t-1}$.

**2. Remove the upper bound by inclusion-exclusion.**
$$\#\text{valid}=\sum_{j=0}^{t}(-1)^j\binom{t}{j}\cdot\#\bigl\{\text{solutions with the chosen }j\text{ variables}\ge k+1\bigr\}.$$
Subtract $k+1$ from each chosen variable; the remaining $t$ variables are non-negative with total $S-j(k+1)$. This gives the standard formula:

$$\boxed{\mathrm{Cnt}(t,S,k)=\begin{cases}\displaystyle\sum_{j=0}^{\min(t,\,\lfloor S/(k+1)\rfloor)}(-1)^j\binom{t}{j}\binom{S-j(k+1)+t-1}{t-1}, & t\ge1,\\[6pt]1 & (t=0\text{ and }S=0),\\[4pt]0 & (t=0\text{ and }S\ne0).\end{cases}}$$

Binomial terms with a negative lower index are treated as 0. For each evaluation the upper limit on $j$ is $\lfloor S/(k+1)\rfloor$, so the cost per call is $O(S/k)$.

Expanding $\mathrm{Cnt}$ and substituting into $A(M)$:
$$A(M)=\sum_{x=0}^{M-1}(M-x)\sum_{j\ge0}(-1)^j\binom{k}{j}\binom{S-x-j(M+1)+r}{r}.$$

---

**Why the naive triple loop is too slow.**

- Outer loop: $M=0,\dots,m$.
- Middle loop (per $M$): $x=0,\dots,\min(M-1,S)$ — roughly $O(M)$ iterations.
- Inner loop (per $(M,x)$): inclusion-exclusion over $j=0,\dots,\lfloor(S-x)/(M+1)\rfloor$.

For fixed $M$, the middle × inner work is approximately $O\!\left(M\cdot\frac{S}{M+1}\right)$. When $S\approx m$ this is $O(m)$ per $M$, making the total $O(m^2)$ — too slow for $m\le2\cdot10^5$.

## 6.4 Interchange the Summations

Because both sums are finite (the inner $j$-sum terminates when $S-x-j(M+1)\lt0$), we may swap the order of summation:
$$A(M)=\sum_{j\ge0}(-1)^j\binom{k}{j}\sum_{x=0}^{M-1}(M-x)\binom{S-x-j(M+1)+r}{r}.$$
(Apply the same transformation to $B(M)$, replacing $k$ with $n-3$ and $S$ with $S-M$.)

## 6.5 Substitute Variables — Convert to an Interval Sum over $t$

Fix $j$ and write the inner sum as:
$$I_j:=\sum_{x=0}^{M-1}(M-x)\binom{S-x-j(M+1)+r}{r}.$$

Substitute $t := S-j(M+1)-x$, i.e. $x = S-j(M+1)-t$. As $x$ runs from $0$ to $M-1$, $t$ runs from $S-j(M+1)$ down to $S-j(M+1)-M+1$. Truncating to the non-negative part:
$$a:=\max\bigl(0,\;S-j(M+1)-(M-1)\bigr),\qquad b:=S-j(M+1).$$
If $b\lt0$ the term is 0 (use this as an early-exit condition when increasing $j$).

After substitution, $M-x = (M-S+j(M+1))+t$, so:
$$I_j=\sum_{t=a}^{b}\bigl((M-S)+j(M+1)+t\bigr)\binom{t+r}{r}.$$

Splitting the constant from the $t$-term:
$$I_j=\bigl(M-S+j(M+1)\bigr)\underbrace{\sum_{t=a}^{b}\binom{t+r}{r}}_{T_0(a,b)}+\underbrace{\sum_{t=a}^{b}t\binom{t+r}{r}}_{T_1(a,b)}.$$

## 6.6 Evaluate $T_0$ and $T_1$ via Hockey Stick

Let $r=k-1$.

**$T_0$** (Hockey Stick):
$$T_0(a,b)=\sum_{t=a}^{b}\binom{t+r}{r}=\binom{b+r+1}{r+1}-\binom{a+r}{r+1}.$$
($T_0=0$ if $a>b$; the second term vanishes when $a=0$.)

**$T_1$** — use the identity $t\binom{t+r}{r}=(r+1)\binom{t+r}{r+1}$:
$$T_1(a,b)=\sum_{t=a}^{b}t\binom{t+r}{r}=(r+1)\sum_{t=a}^{b}\binom{t+r}{r+1}=(r+1)\!\left(\binom{b+r+1}{r+2}-\binom{a+r}{r+2}\right).$$

Therefore:
$$I_j=\bigl(M-S+j(M+1)\bigr)\,T_0(a,b)+T_1(a,b),$$
and substituting back:
$$A(M)=\sum_{j\ge0}(-1)^j\binom{k}{j}\Bigl(\bigl(M-S+j(M+1)\bigr)T_0(a,b)+T_1(a,b)\Bigr).$$
Each $T_0,T_1$ is a difference of two binomial coefficients — $O(1)$ per term.

## 6.7 Same Treatment for $B(M)$

Apply the identical steps to
$$B(M)=\sum_{x=0}^{M-1}(M-x)\cdot\mathrm{Cnt}(k',\,S-M-x,\,M),\qquad k'=n-3,$$
using $S\leftarrow S-M$ throughout. The only change is the constant factor in $M-x$: it becomes $(2M-S)+j(M+1)$.

## 6.8 Key Takeaways

- **Linearise complex processes into "segment-head" contributions** — reduces a complicated traversal to a simple weighted sum.
- **Swap summation order** when both sums are finite — turns a triple loop into $O(1)$ per $(M,j)$ pair after precomputing binomials.
- **Hockey Stick + the identity $t\binom{t+r}{r}=(r+1)\binom{t+r}{r+1}$** — closes interval sums of the form $\sum t^{\le1}\binom{t+r}{r}$ in $O(1)$.

```cpp
#include <bits/stdc++.h>
using namespace std;

using i64 = long long;
const int MOD = 1'000'000'007;

i64 qp(i64 a, i64 e = MOD - 2) {
    i64 r = 1;
    while (e) {
        if (e & 1) r = r * a % MOD;
        a = a * a % MOD; e >>= 1;
    }
    return r;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int T; cin >> T;
    vector<pair<int,int>> qs(T);
    int maxn = 0, maxm = 0;
    for (int t = 0; t < T; ++t) {
        int n, m; cin >> n >> m;
        qs[t] = {n, m};
        maxn = max(maxn, n);
        maxm = max(maxm, m);
    }
    int LIM = maxn + maxm + 5;
    vector<i64> fac(LIM + 1), ifac(LIM + 1);
    fac[0] = 1;
    for (int i = 1; i <= LIM; ++i) fac[i] = fac[i-1] * i % MOD;
    ifac[LIM] = qp(fac[LIM]);
    for (int i = LIM; i >= 1; --i) ifac[i-1] = ifac[i] * i % MOD;

    auto C = [&](i64 n, i64 k) -> i64 {
        if (n < 0 || k < 0 || k > n) return 0;
        if (n > LIM) return 0;
        return fac[n] * ifac[k] % MOD * ifac[n-k] % MOD;
    };

    // Returns (sum0, sum1) = ( sum Cnt(k,y;M), sum y*Cnt(k,y;M) ) for y in [L..U]
    // where Cnt(k,y;M) = #{k variables in [0,M] summing to y}
    auto windowed = [&](int k, int M, i64 L, i64 U) -> pair<i64,i64> {
        if (L > U || M < 0) return {0, 0};
        if (k == 0) {
            i64 s0 = (0 >= L && 0 <= U) ? 1 : 0;
            return {s0, 0};
        }
        i64 sum0 = 0, sum1 = 0;
        int r = k - 1;
        if (U < 0) return {0, 0};
        i64 jmax = U / (M + 1);
        for (i64 j = 0; j <= jmax; ++j) {
            i64 a = L - j * (M + 1);
            i64 b = U - j * (M + 1);
            if (b < 0) break;
            if (a < 0) a = 0;
            if (a > b) continue;
            // T0 = C(b+r+1, r+1) - C(a-1+r+1, r+1)
            i64 s0 = (C(b + r + 1, r + 1) - C(a - 1 + r + 1, r + 1)) % MOD;
            if (s0 < 0) s0 += MOD;
            // T1 = (r+1) * (C(b+r+1, r+2) - C(a-1+r+1, r+2))
            i64 s1t = (i64)(r + 1) * ((C(b + r + 1, r + 2) - C(a - 1 + r + 1, r + 2)) % MOD) % MOD;
            if (s1t < 0) s1t += MOD;
            i64 coef = C(k, j);
            if (j & 1) coef = (MOD - coef) % MOD;
            // y = t + j*(M+1), so sum1 gets s1t + j*(M+1)*s0
            i64 part = (s1t + (j % MOD) * ((M + 1) % MOD) % MOD * s0) % MOD;
            sum0 = (sum0 + coef * s0) % MOD;
            sum1 = (sum1 + coef * part) % MOD;
        }
        return {sum0, sum1};
    };

    for (auto [n, m] : qs) {
        i64 ans = 0;
        for (int M = 0; M <= m; ++M) {
            int S = m - M;

            // A(M): k1 = n-2, window [max(0,S-(M-1)) .. min(S, k1*M)]
            i64 A = 0;
            int k1 = n - 2;
            if (M > 0) {
                i64 LA = max(0, S - (M - 1));
                i64 UA = (k1 >= 1) ? min<i64>(S, 1LL * k1 * M) : min<i64>(S, 0);
                auto [s0A, s1A] = windowed(k1, M, LA, UA);
                A = (s1A + ((M - S + 0LL) % MOD + MOD) % MOD * s0A) % MOD;
            }

            // B(M): k2 = n-3, window [max(0,S-2M+1) .. min(S-M, k2*M)]
            i64 B = 0;
            int k2 = n - 3;
            if (M > 0 && k2 >= 0) {
                i64 LB = max(0, S - 2 * M + 1);
                i64 UB = (k2 >= 1) ? min<i64>(S - M, 1LL * k2 * M) : min<i64>(S - M, 0);
                if (LB <= UB) {
                    auto [s0B, s1B] = windowed(k2, M, LB, UB);
                    B = (s1B + ((2LL * M - S) % MOD + MOD) % MOD * s0B) % MOD;
                }
            }
            ans = (ans + A + ((n - 2 + 0LL) % MOD) * B) % MOD;
        }
        cout << ans % MOD << "\n";
    }
    return 0;
}
```
