---
title: "Number Theory #2: Multiplicative Functions, Möbius Inversion & Dirichlet Convolution"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-2-multiplicative-functions"
description: "Multiplicative functions and linear sieve; Möbius function and inversion in divisor and multiple forms; Dirichlet convolution; Du Jiao sieve for prefix sums of μ and φ; generalized Möbius inversion on posets."
summary: "Multiplicative functions, single-point and linear-sieve evaluation; Möbius function, both forms of Möbius inversion with full derivations and examples; Dirichlet convolution, key identities, Du Jiao sieve; generalized Möbius inversion on posets."
categories: [Number Theory]
tags: [math, number-theory, multiplicative-functions, mobius-inversion, dirichlet-convolution, du-jiao-sieve, linear-sieve]
math: true
toc: true
---

(Continues from [Number Theory #1](../number-theory-1-elementary))

# 1 Multiplicative Functions

## 1.1 Definition

A function $f$ is **multiplicative** if:
$$f(p) \cdot f(q) = f(p \cdot q), \quad \gcd(p,q)=1$$

Functions that are multiplicative:
$$\begin{cases}f(n)=n\\f(n)=[n=1]\\\sigma_k(n)=\sum_{d\mid n}d^k\end{cases}$$

For $\sigma_k(n)=\sum_{d\mid n}d^k$, consider the cases $k=0$ (divisor count $\tau$) and $k=1$ (divisor sum $\sigma$).

> **Proposition.** If $f(n)$ and $g(n)$ are both multiplicative, then $h(n)=f(n)g(n)$ is also multiplicative.

## 1.2 Computing Multiplicative Functions

### Single-point evaluation

If $f$ is multiplicative and $n=p_1^{\alpha_1}p_2^{\alpha_2}\cdots p_k^{\alpha_k}$, then:
$$f(n)=f(p_1^{\alpha_1})\,f(p_2^{\alpha_2})\cdots f(p_k^{\alpha_k}).$$

Decompose $n$ into prime-power factors, evaluate $f(p^k)$ for each, and multiply.

**Complexity:** $O\!\left(\sqrt{n}\cdot\text{cost of }f(p,k)\right)$, which is $O(\sqrt{n})$ when $f(p,k)$ is $O(1)$.

```cpp
ll get_f(ll n) {
    ll ans = 1;
    for (int i = 2; i <= n / i; i++) {
        int cnt = 0;
        while (n % i == 0) cnt++, n /= i;  // count exponent of prime i
        ans *= f(i, cnt);                   // f(p, k) represents f(p^k)
    }
    if (n > 1) ans *= f(n, 1);              // handle the last prime factor > 1
    return ans;
}
```

### Linear sieve for $f(1)\ldots f(n)$

Let **cnt[n]** be the exponent of the smallest prime factor of $n$.  
The key sub-problem is implementing **calc\_f(p, k)** $= f(p^k)$.

```cpp
namespace Prime {
    vector<int> spf; vector<int> p;
    vector<int> mu; vector<int> f; vector<int> cnt;
    void initp(int n) {
        spf.resize(n + 1, 0);
        f.resize(n + 1, 0);
        cnt.resize(n + 1, 0);
        f[1] = 1;                                                              // base case
        for (int i = 2; i <= n; ++i) {
            if (!spf[i]) {
                spf[i] = i;
                p.push_back(i);
                f[i] = calc_f(i, 1);
                cnt[i] = 1;                                                    // i is prime: exponent = 1
            }
            for (int j = 0; j < (int)p.size() && p[j] <= spf[i] && i*p[j] <= n; ++j) {
                int x = i * p[j];
                spf[x] = p[j];
                if (i % p[j] == 0) {
                    cnt[x] = cnt[i] + 1;
                    f[x] = f[i] / calc_f(p[j], cnt[i]) * calc_f(p[j], cnt[i]+1); // p[j] | i: extend exponent
                    break;
                }
                cnt[x] = 1;
                f[x] = f[i] * calc_f(p[j], 1);                                // p[j] ∤ i: new prime factor
            }
        }
    }
}
```

### Example: Nowcoder 23047

$$\text{Compute }\bigoplus_{i=1}^{N}\!\left(i^{N}\bmod(10^{9}+7)\right),\quad 1\leq N\leq 1.3\times10^{7}$$

The map $i\mapsto i^N\bmod(10^9+7)$ is multiplicative. Adapt the linear sieve directly.

### Example: Codeforces 757E

$$\begin{align}
&f_0(n):\text{ number of ordered pairs }(p,q)\text{ with }p\cdot q=n,\ \gcd(p,q)=1\\
&f_{r+1}(n)=\sum_{u\cdot v=n}\frac{f_r(u)+f_r(v)}{2}\\
&\text{Q queries, each asks }f_r(n)\bmod(10^9+7)\quad(1\leq q\leq10^6,\ 0\leq r\leq10^6,\ 1\leq n\leq10^6)
\end{align}$$

**Key observations.**

For $n=p_1^{\alpha_1}\cdots p_k^{\alpha_k}$, a pair $(p,q)$ with $pq=n$ and $\gcd(p,q)=1$ means every prime $p_i$ goes entirely to $p$ or $q$. There are $2^k=2^{\omega(n)}$ such pairs, so $f_0(n)=2^{\omega(n)}$.

Multiplicativity of $f_0$: for $\gcd(p,q)=1$,
$$f_0(pq)=2^{\omega(p)+\omega(q)}=2^{\omega(p)}\cdot2^{\omega(q)}=f_0(p)\cdot f_0(q).$$

The recurrence simplifies by divisor symmetry:
$$f_{r+1}(n)=\sum_{d\mid n}\frac{f_r(d)+f_r(n/d)}{2}=\sum_{d\mid n}f_r(d).$$

> **Tip.** General statement: if $f$ is multiplicative then $g(n)=\sum_{d\mid n}f(d)$ is multiplicative. (See Dirichlet convolution below.)

By induction all $f_x$ are multiplicative, and:
$$f_r(p^\alpha)=\sum_{i=0}^{\alpha}f_{r-1}(p^i).$$

Starting from $f_0(p^\alpha)=2$ for $\alpha\geq1$ and $f_0(1)=1$, we get $f_1(p^\alpha)=1+2\alpha$.

**Crucial property:** $f_r(p^\alpha)$ depends only on $r$ and $\alpha$, not on $p$.

Precompute table $f[r][\alpha]$ for $0\leq r\leq r_{\max}$, $0\leq\alpha\leq20$:
$$f[r][\alpha]=f[r][\alpha-1]+f[r-1][\alpha]\quad(\text{prefix sum over }\alpha\text{ per layer})$$

Each query $(r,n)$: factor $n$, return $\prod_i f[r][e_i]$ in $O(\log n)$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int MOD = 1000000007;

int main(){
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int q;
    cin >> q;
    vector<pair<int,int>> qs(q);
    int max_r = 0;
    for(int i = 0; i < q; i++){
        cin >> qs[i].first >> qs[i].second;
        max_r = max(max_r, qs[i].first);
    }

    // 1) precompute smallest prime factor
    const int N = 1000000;
    vector<int> spf(N+1);
    spf[1] = 1;
    for(int i = 2; i <= N; i++) if(spf[i] == 0){
        for(int j = i; j <= N; j += i) if(spf[j] == 0)
            spf[j] = i;
    }

    // 2) precompute f_r(p^α) for 0 ≤ r ≤ max_r, 0 ≤ α ≤ 20
    const int MAXA = 20;
    vector<array<int,MAXA+1>> f(max_r+1);
    f[0][0] = 1;
    for(int a = 1; a <= MAXA; a++) f[0][a] = 2;  // f_0(p^α) = 2 for α > 0
    for(int r = 1; r <= max_r; r++){
        f[r][0] = 1;  // f_r(1) = 1
        for(int a = 1; a <= MAXA; a++)
            f[r][a] = (f[r][a-1] + f[r-1][a]) % MOD;
    }

    // 3) answer each query: factor n, multiply f[r][exponent]
    for(auto &qr : qs){
        int r = qr.first, n = qr.second;
        ll ans = 1;
        while(n > 1){
            int p = spf[n], c = 0;
            while(n % p == 0){ n /= p; c++; }
            ans = ans * f[r][c] % MOD;
        }
        cout << ans << '\n';
    }
    return 0;
}
```

---

# 2 Möbius Inversion

## 2.1 Motivation

> **Example.** Compute $\displaystyle\sum_{i=1}^n\gcd(i,n)$.
>
> $$\begin{aligned}
> \sum_{i=1}^n\gcd(i,n)
> &=\sum_{d\mid n}d\cdot\sum_{i=1}^n[\gcd(i,n)=d]\\
> &=\sum_{d\mid n}d\cdot\sum_{i=1}^{\lfloor n/d\rfloor}\!\left[\gcd\!\left(i,\Bigl\lfloor\tfrac{n}{d}\Bigr\rfloor\right)=1\right]\\
> &=\sum_{d\mid n}d\cdot\varphi\!\left(\Bigl\lfloor\tfrac{n}{d}\Bigr\rfloor\right)
> \end{aligned}$$

## 2.2 Möbius Function & Inversion — Divisor Form

> **Möbius function** $\mu(n)$:
> $$\mu(n)=\begin{cases}1,&n=1\\0,&n\text{ has a squared prime factor}\\(-1)^k,&n\text{ is a product of }k\text{ distinct primes}\end{cases}$$
>
> **Key property:** $\displaystyle\sum_{d\mid n}\mu(d)=[n=1]$
>
> **Möbius inversion — two equivalent forms:**
>
> 1. **Divisor form:** If $\displaystyle F(n)=\sum_{d\mid n}f(d)$ (i.e.\ $F=f*1$), then:
> $$\boxed{f(n)=\sum_{d\mid n}\mu(d)\,F\!\left(\frac{n}{d}\right)}$$
> Equivalently, $f=F*\mu$.
>
> 2. **Multiple form:** If $\displaystyle F(n)=\sum_{n\mid m}f(m)$, then:
> $$\boxed{f(n)=\sum_{n\mid m}\mu\!\left(\frac{m}{n}\right)F(m)}$$

**Remark on "inversion" in algebra:** inversion means finding the inverse. For a function it recovers the preimage; for a matrix it finds the inverse matrix. Möbius inversion recovers $f$ from $F$.

### 2.2.1 Intuition I: Unrolling the divisor sum

Given $F(n)=\sum_{d\mid n}g(d)$, recover $g$ step by step:

```
F(1) = g(1)                       =>  g(1) = F(1)
F(2) = g(1)+g(2)                  =>  g(2) = F(2)-F(1)
F(3) = g(1)+g(3)                  =>  g(3) = F(3)-F(1)
F(4) = g(1)+g(2)+g(4)             =>  g(4) = F(4)-F(2)
F(5) = g(1)+g(5)                  =>  g(5) = F(5)-F(1)
F(6) = g(1)+g(2)+g(3)+g(6)        =>  g(6) = F(6)-F(3)-F(2)+F(1)
F(7) = g(1)+g(7)                  =>  g(7) = F(7)-F(1)
F(8) = g(1)+g(2)+g(4)+g(8)        =>  g(8) = F(8)-F(4)-F(2)+F(1)
```

Expanding recursively (replacing each $g(d)$ with its $F$-expansion), only $F$ values remain. The coefficient of each $F(n/d)$ turns out to be exactly $\mu(d)$:
$$g(n)=\sum_{d\mid n}\mu(d)\,F\!\left(\frac{n}{d}\right)$$

This is the **Möbius inversion formula**.

### 2.2.2 Intuition II: Inclusion-exclusion over prime factors

$$\begin{aligned}
&\bullet\quad n=p^k\ (\text{single prime power}):\ \text{square-free divisors are }1\text{ and }p,\\
&\quad\quad g(p^k)=F(p^k)-F(p^{k-1}).\\[4pt]
&\bullet\quad n=pq\ (\text{two distinct primes}):\ \text{square-free divisors are }1,p,q,pq,\\
&\quad\quad g(pq)=F(pq)-F(q)-F(p)+F(1).\\[4pt]
&\bullet\quad\text{General: }n=p_1^{\alpha_1}\cdots p_k^{\alpha_k}.\\
&\quad\text{Each square-free divisor }d\text{ corresponds to a subset }S\subseteq\{p_1,\ldots,p_k\},\\
&\quad d=\prod_{p_i\in S}p_i,\quad\mu(d)=(-1)^{|S|},\\
&\quad g(n)=\sum_{S\subseteq\{1,\ldots,k\}}(-1)^{|S|}F\!\left(\frac{n}{\prod_{i\in S}p_i}\right).
\end{aligned}$$

This is multi-dimensional inclusion-exclusion along the divisor tree.

### Example: Necklace counting

**Problem:** A ring of $n$ elements each drawn from $\{1,\ldots,r\}$; two rings are equal if one can be rotated to match the other. Count distinct rings.

Without the rotation equivalence the total count is $r^n$.

Let $f(d)$ = number of rings with minimal period exactly $d$. The minimal period always divides $n$.

Each such ring contributes $d$ distinct linear representations (one per rotation within the period):
$$r^n=\sum_{d\mid n}d\cdot f(d)$$

*(Visual justification: the cyclic group $\mathbb{Z}_n$ acts on the $r^n$ sequences. A sequence with minimal period $d$ has orbit size $d$, so the $f(d)$ distinct rings of that period account for $d\cdot f(d)$ sequences. Summing over all $d\mid n$ recovers $r^n$.)*

By Möbius inversion:
$$n\cdot f(n)=\sum_{d\mid n}\mu\!\left(\frac{n}{d}\right)r^d$$
$$f(n)=\frac{1}{n}\sum_{d\mid n}\mu\!\left(\frac{n}{d}\right)r^d$$
$$\text{Answer}=\sum_{d\mid n}f(d)$$

**Why "first unconstrained, then classify by orbit size"?** For symmetry-reduction problems (remove rotations), the two standard tools are Burnside's lemma and the orbit-stabilizer theorem. Here we use the latter: orbit size of a sequence with minimal period $d$ is exactly $d$, giving the identity above.

*(Second visual: the orbit-stabilizer theorem $|\text{orbit}|\times|\text{stabilizer}|=|\text{group}|$ applied to $\mathbb{Z}_n$ acting on period-$d$ sequences, confirming orbit size $= d$.)*

## 2.3 Möbius Inversion — Multiple Form

Let $f,g:\mathbb{N}\to\mathbb{R}$ with both vanishing for $n>N$. Then:
$$\boxed{f(n)=\sum_{\substack{n\mid m\\m\leq N}}g(m)}\;\Longleftrightarrow\;\boxed{g(n)=\sum_{\substack{n\mid m\\m\leq N}}\mu\!\left(\frac{m}{n}\right)f(m)}$$

### Example: Nowcoder 14648

$$\text{Given sequences }a,b\text{ of length }n,\text{ count ordered pairs }(x,y)\text{ with }\gcd(x,y)=1\text{ and }a_{b_x}=b_{a_y}.$$
$$(1\leq n\leq10^5,\quad 1\leq a_i,b_i\leq n)$$

**Trick for** $\sum_{x,y}[c_x=d_y]$:
```cpp
for(x=1;x<=n;x++) cnt[c[x]]++;
for(y=1;y<=n;y++) ans+=cnt[d[y]];
```

Applying this to $a_{b_x}=b_{a_y}$ without the GCD constraint:
```cpp
for(x=1;x<=n;x++) cnt[a[b[x]]]++;
for(y=1;y<=n;y++) ans+=cnt[b[a[y]]];
```

With $\gcd(x,y)=1$:
$$\text{Ans}=\sum_{\substack{1\leq x,y\leq n}}[a_{b_x}=b_{a_y}]\cdot[\gcd(x,y)=1]$$

**Branch 1 — via multiple form:**

$$f(d)=\sum_{\substack{1\leq x,y\leq n}}[a_{b_x}=b_{a_y}]\cdot[\gcd(x,y)=d]$$
$$g(d)=\sum_{d\mid d'}f(d')=\sum_{\substack{1\leq x,y\leq n\\d\mid x,\;d\mid y}}[a_{b_x}=b_{a_y}]$$
$$\text{Ans}=f(1)=\sum_{d=1}^n\mu(d)\,g(d)$$

$g(d)$ computed in $O(n/d)$; total $O(n\log n)$.

**Branch 2 — via divisor form (grouping identity):**

$$\text{Ans}=\sum_{d=1}^n\mu(d)\!\sum_{\substack{d\mid x,\,d\mid y}}[a_{b_x}=b_{a_y}]
=\sum_{d=1}^n\mu(d)\sum_{t=1}^n\left(\sum_{d\mid x}[a_{b_x}=t]\right)\!\left(\sum_{d\mid y}[b_{a_y}=t]\right)$$

```cpp
void sol() {
    int n; cin>>n;
    vector<int> a(n+1), b(n+1);
    for(int i=1;i<=n;i++) cin>>a[i];
    for(int i=1;i<=n;i++) cin>>b[i];
    ll ans = 0;
    vector<ll> g(n+1);                        // must be ll
    for(int d=1;d<=n;d++){
        unordered_map<int,int> cnt;            // see warning below — plain vector would be O(n^2)
        for(int x=d;x<=n;x+=d) cnt[a[b[x]]]++;
        for(int y=d;y<=n;y+=d) g[d]+=cnt[b[a[y]]];
    }
    for(int i=1;i<=n;i++) ans += (ll)mu[i]*g[i];
    cout<<ans<<endl;
}
```

> **Warning.** Reinitialising `vector<int> cnt(n+1)` each round degrades to $O(n^2)$. Two alternatives:
> 1. Use `unordered_map` (if still TLE, use option 2).
> 2. Fixed array + **touch-and-clear** (only zero out entries you actually wrote):

```cpp
vector<int> cnt(n+1, 0), touched;
touched.reserve(n);
auto touch_inc = [&](int v){
    if (cnt[v] == 0) touched.push_back(v);
    ++cnt[v];
};
auto clear_touched = [&](){
    for (int v : touched) cnt[v] = 0;
    touched.clear();
};
```

Full solution using a timestamp array (avoids clearing entirely):

```cpp
// grouping identity + timestamp array
void sol(){
    int n; cin>>n;
    vector<int> a(n+1), b(n+1);
    for(int i=1;i<=n;i++) cin>>a[i]; for(int i=1;i<=n;i++) cin>>b[i];
    // precompute C[x] = a[b[x]], D[y] = b[a[y]]
    vector<int> C(n+1), D(n+1);
    for(int x=1;x<=n;x++) C[x] = a[b[x]];
    for(int y=1;y<=n;y++) D[y] = b[a[y]];

    ll ans = 0;
    vector<ll> g(n+1, 0);
    vector<int> cnt(n+1, 0), vis(n+1, 0);
    int tick = 0;

    for(int d=1; d<=n; d++){
        ++tick;                              // new iteration of d: increment timestamp
        for(int x=d; x<=n; x+=d){
            int t = C[x];
            if(vis[t] != tick){ vis[t] = tick; cnt[t] = 0; }
            ++cnt[t];
        }
        long long cur = 0;
        for(int y=d; y<=n; y+=d){
            int t = D[y];
            if(vis[t] == tick) cur += cnt[t];
        }
        g[d] = cur;                          // g(d) = #{(x,y): d|x, d|y, C_x=D_y}
    }
    for(int d=1; d<=n; d++) ans += (ll)mu[d]*g[d];
    cout << ans << '\n';
}
```

### Example: AtCoder abc162 E

$$\text{Compute }\sum_{A_1=1}^K\sum_{A_2=1}^K\cdots\sum_{A_N=1}^K\gcd(A_1,\ldots,A_N)\pmod{10^9+7}\quad(K,N\leq10^5)$$

Let $f(d)=\#\{(A_1,\ldots,A_N):\gcd=d\}$ and $g(d)=\sum_{d\mid d'}f(d')=\lfloor K/d\rfloor^N$.

$$\text{Ans}=\sum_{d=1}^K d\cdot f(d)$$

**Via multiple form:**
$$f(d)=\sum_{d\mid d'}\mu\!\left(\frac{d'}{d}\right)g(d')$$
$$\text{Ans}=\sum_{d=1}^K d\cdot\sum_{d\mid d'}\mu\!\left(\frac{d'}{d}\right)g(d')=\sum_{d'=1}^K g(d')\underbrace{\sum_{d\mid d'}d\cdot\mu\!\left(\frac{d'}{d}\right)}_{=\varphi(d')}=\sum_{m=1}^K\Bigl\lfloor\tfrac{K}{m}\Bigr\rfloor^N\varphi(m)$$

**Via divisor form (same result):**
$$\text{Ans}=\sum_{n=1}^K n\sum_{d\mid n}\mu(d)\,g\!\left(\tfrac{n}{d}\right)
=\sum_{d=1}^K\mu(d)\sum_{m=1}^{\lfloor K/d\rfloor}dm\cdot g(m)
=\sum_{m=1}^K g(m)\underbrace{\sum_{d\mid m}d\,\mu\!\left(\tfrac{m}{d}\right)}_{=\varphi(m)}$$

```cpp
void sol() {
    ll N, K; cin>>N>>K;
    ll ans = 0;
    for(ll d_ = 1; d_ <= K; d_++){
        ll add = (ll)qp(K/d_, N) * phi[d_] % M;
        ans += add; ans %= M;
    }
    cout<<ans;
}
```

### Example: LCMS — AtCoder AGC038 C

$$\text{Given }A_1,\ldots,A_N,\text{ compute }\sum_{i\lt j}\mathrm{lcm}(A_i,A_j).\quad(N\leq2\times10^5,\ A_i\leq10^6)$$

**Reduction:** $\displaystyle\sum_{i,j}\mathrm{lcm}(A_i,A_j)=2\cdot\text{Ans}+\sum_i A_i$, so compute:
$$\text{Ans}'=\sum_{i,j}\mathrm{lcm}(A_i,A_j)=\sum_{i,j}\frac{A_iA_j}{\gcd(A_i,A_j)}=\sum_{d=1}^L\frac{1}{d}\underbrace{\sum_{i,j}A_iA_j\cdot[\gcd(A_i,A_j)=d]}_{f(d)}$$

Let $g(d)=\sum_{d\mid d'}f(d')=\Bigl(\sum_{i:d\mid A_i}A_i\Bigr)^2$.

By Möbius inversion (multiple form):
$$f(d)=\sum_{d\mid d'}\mu\!\left(\frac{d'}{d}\right)g(d')$$

Let $h(d')=\sum_{i:d'\mid A_i}A_i$ (multiple sum over $A$, computable in $O(L\log L)$). Then $g(d)=h(d)^2$.

**$O(N\log N)$ Dirichlet convolution** — given arrays $f,g$, compute full array $h$:

$$h(n)=\sum_{d\mid n}f(d)\cdot g\!\left(\frac{n}{d}\right)\implies O(N\log N)$$
$$h(d)=\sum_{d\mid d'}f\!\left(\frac{d'}{d}\right)\cdot g(d')\implies O(A\log A),\;A=\text{value range}$$

```cpp
// divisor form
for(int d = 1; d <= n; d++){
    for(int j = 1; j <= n/d; j++){
        h[d*j] += (ll)f[d]*g[j]%M; h[d*j] %= M;
    }
}
// equivalent, slightly better constant
int N = Amax;
vector<ll> h(N+1), f(N+1), g(N+1);
for(int d = 1; d <= N; ++d){
    for(int m = d; m <= N; m += d){  // enumerate multiples m of d
        h[m] += (i128)f[d] * g[m/d] % M;  h[m] %= M;
    }
}

// multiple form
vector<int> h(Amax+1, 0);
for(int d = 1; d <= Amax; d++){
    for(int j = d; j <= Amax; j += d){
        h[d] += (ll)f[j/d]*g[j]%M; h[d] %= M;
    }
}
```

Full solution:

```cpp
void sol() {
    // 1) linear sieve for mu[] and inv[]
    init(1e6+10); initp(1e6+10);

    int n; cin>>n;
    vector<int> A(n);
    for(auto &x : A) cin>>x;

    // 2) count[x] and V[x] = x * count[x] % MOD
    vector<int> cnt(1e6+1);
    for(auto &x : A) cnt[x]++;
    vector<int> V(1e6+1);
    for(int i=1; i<=1e6; i++) V[i] = (ll)i * cnt[i] % M;

    // 3) jm[d] = sum_{d|x} V[x]  (multiple sum)
    vector<int> jm(1e6+10);
    for(int d=1; d<=1e6; d++){
        for(int j=d; j<=1e6; j+=d){
            jm[d] += V[j]; jm[d] %= M;
        }
    }
    // 4) g[d] = jm[d]^2 % MOD
    vector<int> g(1e6+1, 0);
    for(int d=1; d<=1e6; d++) g[d] = (ll)jm[d] * jm[d] % M;

    // 5) h[d] = sum_{d|d'} mu[d'/d] * g[d']  (Dirichlet convolution)
    vector<int> h(1e6+10);
    for(int d=1; d<=1e6; d++){
        for(int j=d; j<=1e6; j+=d){
            h[d] += (ll)mu[j/d]*g[j]%M; h[d] %= M;
        }
    }
    // 6) Ans' = sum_d h[d]*inv[d];  ans = (Ans' - sumA) * inv2
    int T = 0;
    for(int d=1; d<=1e6; d++){
        T += (ll)h[d]*inv[d]%M; T %= M;
    }
    ll sumA = 0;
    for(int x : A) sumA = (sumA + x) % M;
    ll INV2 = (M + 1) / 2;
    int ans = (T - sumA + M) % M * INV2 % M;
    cout << ans << '\n';
}
```

---

# 3 Dirichlet Convolution

## 3.1 Definition

For $f,g:\mathbb{N}\to\mathbb{R}$, the **Dirichlet convolution** is:
$$(f*g)(n)=\sum_{d\mid n}f(d)\,g\!\left(\frac{n}{d}\right)$$

## 3.2 Properties

If $f(n)$ and $g(n)$ are multiplicative, then $h(n)=(f*g)(n)$ is also multiplicative.

## 3.3 Key Identities

$$f=g*1\;\Leftrightarrow\; g=f*\mu$$

> **Standard identities:**
> $$\begin{align}
> &\bullet\ \varepsilon=\mu*1\\
> &\bullet\ \mathrm{id}=\varphi*1\\
> &\bullet\ \varphi=\mu*\mathrm{id}
> \end{align}$$

## 3.4 Du Jiao Sieve

### 3.4.1 Core recursive formula and derivation

**Goal:** compute $M(n)=\sum_{i=1}^n\mu(i)$ for large $n$ (up to $10^{11}$) quickly.

> $$M(n)=1-\sum_{i=2}^n M\!\left(\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor\right)$$

**Derivation (algebraic):**

$$\begin{align}
1&=\sum_{i=1}^n\varepsilon(i)=\sum_{i=1}^n(\mu*1)(i)=\sum_{i=1}^n\sum_{d\mid i}\mu(d)\\
&=\underbrace{\sum_{d=1}^n\mu(d)\sum_{i=1}^n[d\mid i]}_{\text{swap order}}=\sum_{d=1}^n\mu(d)\Bigl\lfloor\tfrac{n}{d}\Bigr\rfloor=\sum_{d=1}^n\mu(d)\sum_{i=1}^{\lfloor n/d\rfloor}1\\
\text{(swap again)}&=\sum_{i=1}^n\sum_{d=1}^{\lfloor n/i\rfloor}\mu(d)=\sum_{i=1}^n M\!\left(\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor\right)
\end{align}$$

*(Visual: a triangular grid where row $i$ has $\lfloor n/i\rfloor$ entries each equal to $\mu(j)$ for $j=1,\ldots,\lfloor n/i\rfloor$. Reading by rows yields $\sum_i M(\lfloor n/i\rfloor)$; identifying the first row as $M(n)$ and subtracting the remaining rows gives the recursion.)*

Therefore:
$$M(n)=\sum_{i=1}^n M\!\left(\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor\right)-\sum_{i=2}^n M\!\left(\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor\right)=1-\sum_{i=2}^n M\!\left(\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor\right)$$

> $\lfloor n/i\rfloor$ takes only $O(\sqrt{n})$ distinct values. Enumerate with divisibility blocking:
> ```cpp
> for(l=1; l<=n; l=r+1) {
>     r = n/(n/l);
>     // process block [l, r] with quotient n/l
> }
> ```

### 3.4.2 Du Jiao Sieve for large $n$ — $O(n^{2/3})$

We want:
$$S_\mu(n)=\sum_{i\leq n}\mu(i),\qquad S_\varphi(n)=\sum_{i\leq n}\varphi(i).$$

Convolution identities:
$$\sum_{i\leq n}\mu(i)\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor=1,\qquad\sum_{i\leq n}\varphi(i)\Bigl\lfloor\tfrac{n}{i}\Bigr\rfloor=\frac{n(n+1)}{2}$$

Merge terms with the same quotient $t=\lfloor n/l\rfloor$ (divisibility blocking) to turn the sum into a recursion over $S(\lfloor n/k\rfloor)$.

**Template: [Luogu P4213 Du Jiao Sieve](https://www.luogu.com.cn/problem/P4213)** — $O(n^{2/3})$

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

namespace Prime {
    vector<int> spf; vector<int> prime;
    vector<int> mu; vector<int> phi;
    void initp(int n) {
        spf.resize(n + 1, 0);
        mu.resize(n + 1, 0);
        phi.resize(n + 1, 0);
        mu[1] = 1; phi[1] = 1;                                            // base case
        for (int i = 2; i <= n; ++i) {
            if (!spf[i]) {
                spf[i] = i; prime.push_back(i);
                mu[i] = -1;  phi[i] = i - 1;                              // i is prime
            }
            for(int j=0; j<(int)prime.size()&&prime[j]<=spf[i]&&i*prime[j]<=n; ++j){
                int x = i * prime[j];
                spf[x] = prime[j];
                if (i % prime[j] == 0) {
                    mu[x] = 0;  phi[x] = phi[i] * prime[j];               // prime[j]^2 | x
                    break;
                } else {
                    mu[x] = -mu[i];  phi[x] = phi[i] * (prime[j] - 1);   // new prime factor
                }
            }
        }
    }
}
using namespace Prime;

const int MAXN = 5000000;
vector<ll> sumMu, sumPhi;
unordered_map<ll,ll> cacheMu, cachePhi;

ll getMu(ll n){
    if (n <= MAXN) return sumMu[n];        // small n: direct table lookup
    if (cacheMu.count(n)) return cacheMu[n];
    ll ans = 1;                            // Möbius convolution identity
    for (ll l=2,r; l<=n; l=r+1){
        ll t = n/l; r = n/t;
        ans -= (r-l+1) * getMu(t);
    }
    return cacheMu[n] = ans;
}

ll getPhi(ll n){
    if (n <= MAXN) return sumPhi[n];       // small n: direct table lookup
    if (cachePhi.count(n)) return cachePhi[n];
    ll ans = n*(n+1)/2;                    // Euler phi convolution identity
    for (ll l=2,r; l<=n; l=r+1){
        ll t = n/l; r = n/t;
        ans -= (r-l+1) * getPhi(t);
    }
    return cachePhi[n] = ans;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    Prime::initp(MAXN);
    sumMu.resize(MAXN+1);  sumPhi.resize(MAXN+1);
    sumMu[0] = 0;  sumPhi[0] = 0;
    for (int i=1; i<=MAXN; ++i){
        sumMu[i]  = sumMu[i-1]  + mu[i];
        sumPhi[i] = sumPhi[i-1] + phi[i];
    }
    cacheMu.reserve(1<<20);  cachePhi.reserve(1<<20);

    int q; cin>>q;
    while(q--){
        ll n; cin>>n;
        cout << getPhi(n) << " " << getMu(n) << "\n";
    }
    return 0;
}
```

> **Why does removing `if (n <= MAXN) return sumPhi[n]` cause TLE?**
> This line is the foundation of the memoization. The recursion generates many sub-problems $\text{getPhi}(t)$ where most $t\leq\text{MAXN}$ (with $\text{MAXN}\approx n^{2/3}$). `cachePhi` only stores values *above* MAXN; for small $t$ there is no cache, so the same small $t$ is recomputed from scratch in every branch. **The small-range lookup table is the core reason Du Jiao sieve is fast.**

### Example: 2021 Ladder Tournament L3-030 "Poor Simple Problem"

A random sequence $A$ is generated by repeatedly drawing from $[1,n]$ uniformly until $\gcd(A_1,\ldots,A_k)=1$. Given $n$, compute the expected length $E$ modulo prime $p$.

$$(1\leq n\leq10^{11},\quad n\lt p\leq10^{12})$$

The termination condition "$\nexists\, w>1$ dividing all elements" is equivalent to $\gcd(A_1,\ldots,A_k)=1$.

$$E=\sum_{k=1}^\infty k\cdot P(\text{length}=k)=\sum_{k=1}^\infty k\cdot P(\gcd(A_1,\ldots,A_{k-1})>1)\cdot P(\gcd=1\mid\gcd(\ldots,A_{k-1})>1)$$

Let $f(k)=\sum_{d=1}^n\mu(d)\bigl\lfloor n/d\bigr\rfloor^k$.

$$X=P(\gcd(A_1,\ldots,A_{k-1})>1)=\frac{n^{k-1}-f(k-1)}{n^{k-1}}$$

$$Y=P(\gcd=1\mid\gcd(\ldots,A_{k-1})>1)=\frac{f(k)-f(k-1)\cdot n}{n^k-f(k-1)\cdot n}$$

The case $k=1$ is handled separately: $P(\text{length}=1)=P(A_1=1)=\tfrac{1}{n}$.

$$E=\sum_{k=2}^\infty k\cdot\left(\frac{f(k)}{n^k}-\frac{f(k-1)}{n^{k-1}}\right)+\frac{1}{n}$$

Substituting $f$ and computing $S(r)=\sum_{k=2}^\infty kr^k-\sum_{j=1}^\infty(j+1)r^j$ using the standard geometric-series identities:
$$\sum_{k=1}^\infty kr^k=\frac{r}{(1-r)^2},\qquad\sum_{k=1}^\infty r^k=\frac{r}{1-r}\quad(|r|\lt1)$$

$$A=\frac{r}{(1-r)^2}-r,\qquad B=\frac{r}{(1-r)^2}+\frac{r}{1-r}$$

$$S(r)=A-B=1-r-\frac{1}{1-r}\tag{1}$$

When $d=1$, $r=1$: by definition $S(1)=\sum_{k=2}^\infty k(1-1)=0$.

Substituting back and simplifying using $\sum_{d\leq n}\mu(d)=M(n)$ and $\sum_{d\leq n}\mu(d)\lfloor n/d\rfloor=1$:

$$\boxed{E=M(n)-n\sum_{d=2}^n\frac{\mu(d)}{n-\lfloor n/d\rfloor}}$$

*(The $d=1$ term has zero denominator but cancels completely in the derivation.)*

Compute $\displaystyle\sum_{d=2}^n\frac{\mu(d)}{n-\lfloor n/d\rfloor}$ via divisibility blocking: for a block $[L,R]$ with constant quotient $t=\lfloor n/L\rfloor$, the denominator $n-t$ is constant and the block contributes:
$$\frac{\sum_{d=L}^R\mu(d)}{n-t}=\frac{M(R)-M(L-1)}{n-t}$$

Each $M(x)$ is evaluated by Du Jiao sieve.

> **Note:** $n$ and $p$ can both exceed $2^{62}$; all multiplications need `__int128`. The `qp` function must also use `__int128` arithmetic.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
using i128 = __int128_t;
ll M;
constexpr ll qp(ll a, ll x = M-2){
    ll res=1; for(;x;x>>=1,a=(i128)a*a%M) (x&1)&&(res=(i128)a*res%M); return res;
}

namespace Prime { /* linear sieve for mu, same as above */ }
using namespace Prime;

const int MAXN = 5000000;
vector<ll> sumMu;
unordered_map<ll,ll> cacheMu;

ll getMu(ll n){
    if (n <= MAXN) return sumMu[n];
    if (cacheMu.count(n)) return cacheMu[n];
    ll ans = 1;
    for (ll l=2,r; l<=n; l=r+1){
        ll t = n/l; r = n/t;
        ans -= (r-l+1) * getMu(t);
    }
    return cacheMu[n] = ans;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    Prime::initp(MAXN);
    sumMu.resize(MAXN+1); sumMu[0] = 0;
    for (int i=1; i<=MAXN; ++i) sumMu[i] = sumMu[i-1] + mu[i];
    cacheMu.reserve(1<<20);

    ll n, p; cin>>n>>p; M = p;
    ll ans = getMu(n);
    for(ll l=2,r; l<=n; l=r+1) {
        ll t = n/l; r = n/t;
        ll deltaM = (getMu(r) - getMu(l-1)) % M;
        ll sub = (i128)n * deltaM % M * qp(n-t) % M;
        ans = (ans - sub + M) % M;
        if(ans < 0) ans += M;
    }
    if(ans < 0) ans += M;
    cout << ans << '\n';
    return 0;
}
```

---

# 4 Generalized Möbius Inversion

> **Theorem.** Let $(X,\leq)$ be a locally finite partially ordered set and $f,g:X\to\mathbb{R}$. Then:
> $$f(x)=\sum_{y\leq x}g(y)\;\Longleftrightarrow\;g(x)=\sum_{y\leq x}\mu(y,x)\,f(y)$$
> where $\mu(x,y)$ is defined recursively:
> $$\mu(x,y)=\begin{cases}1,&x=y\\-\displaystyle\sum_{x\leq z\lt y}\mu(x,z),&x\lt y\end{cases}$$

$$\begin{align}
&\bullet\ \text{Möbius inversion can be derived from inclusion-exclusion.}\\
&\bullet\ \text{Inclusion-exclusion is subset inversion.}\\
&\bullet\ \text{Möbius inversion, inclusion-exclusion, and prefix sums are all special cases of generalized Möbius inversion.}\\
&\bullet\ \text{Generalized Möbius inversion requires only a locally finite poset.}
\end{align}$$

*(Diagram: the three classical settings — total order, divisibility, subset lattice — depicted as special posets, all unified under the same framework.)*

**Three classical special cases:**

### 1. Total order $1\leq2\leq3\leq\cdots\leq n$ → prefix sums

$$\mu(y,y)=1,\quad\mu(y,y+1)=-1,\quad\mu(y,x)=0\;(x\geq y+2)$$

Substituting into the inversion formula:
$$f(x)=\sum_{y\leq x}\mu(y,x)\,g(y)=g(x)-g(x-1)$$

This is the discrete derivative — the inverse of the prefix sum.

### 2. Divisibility order → standard Möbius inversion

$$\mu(d,n)=\mu\!\left(\frac{n}{d}\right)$$

### 3. Subset inclusion → inclusion-exclusion

$$g(S)=\sum_{T\subseteq S}f(T)\;\Longleftrightarrow\; f(S)=\sum_{T\subseteq S}(-1)^{|S|-|T|}g(T)$$
$$g(T)=\sum_{T\subseteq S}f(S)\;\Longleftrightarrow\; f(T)=\sum_{T\subseteq S}(-1)^{|S|-|T|}g(S)$$

The Möbius function on the Boolean lattice (subset poset) is:
$$\mu(T,S)=\begin{cases}(-1)^{|S|-|T|},&T\subseteq S\\0,&\text{otherwise}\end{cases}$$

Equivalently $\mu(T,S)=(-1)^{|S\setminus T|}$ for $T\subseteq S$.

*(Diagram: Boolean lattice $B_3$ on $\{a,b,c\}$, $\zeta$-transform (subset sum) going bottom-up, Möbius inversion (inclusion-exclusion with alternating signs) going top-down.)*

**Practical note:** For most posets, $\mu(y,x)$ is hard to compute. The three cases above cover essentially all competitive-programming applications.

*At least generalized Möbius inversion provides a unified and elegant framework.*

---

# 5 Other Inversions: Min-Max, Binomial, …

**Common theme:** when a problem is hard to attack directly, transform it into an equivalent form.

### Min-Max conversion

$$\max(a,b)=a+b-\min(a,b)\quad\Rightarrow\quad\text{reduce }\max\text{ problems to }\min$$

Or via absolute value:
$$\max(a,b)=\frac{a+b+|a-b|}{2},\qquad\min(a,b)=\frac{a+b-|a-b|}{2}$$
