---
title: "Number Theory #4: Min_25 Sieve and Du Jiao Sieve"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-4-min25-du-jiao-sieve"
description: "Min_25 sieve for prefix sums of multiplicative functions in O(n^{3/4}/log n); Du Jiao sieve for μ and φ prefix sums in O(n^{2/3}) via convolution identities; worked examples including P3768 and 51Nod LCM/GCD sums."
summary: "Min_25 sieve: theory, two complete examples, Lagrange interpolation for power sums. Du Jiao sieve: template, P3768, GCD sum, LCM sum."
categories: [Number Theory]
tags: [math, number-theory, min25-sieve, du-jiao-sieve, multiplicative-functions, prefix-sum]
math: true
toc: true
---

# 1 Min_25 Sieve

## 1.1 Problem

Compute the prefix sum $\sum_{i=1}^n f(i)$ of a multiplicative function $f$.

## 1.2 Algorithm Overview

> **Checklist before starting:**
> 1. Verify $f$ is multiplicative.
> 2. $h(x)=\sum_{\substack{2\leq p\leq x\\p\text{ prime}}}f(p)$ — fast prime-sum query (computed by Min_25 first phase).
> 3. Initialise: the "pre-sieve" raw prefix sums over two channels. If $f(p)$ is a polynomial of degree $\leq4$ use closed-form formulas; otherwise use Lagrange interpolation.
> 4. Implement $f(p^e)$ (usually a closed form).

### Lagrange interpolation for power sums

$F_k(n)=\sum_{i=1}^n i^k\pmod{M}$: preprocess once per $k$, then answer in $O(k)$.

```cpp
// F_k(n) = sum_{i=1}^n i^k  (mod M)
// First call for a given k: O(k) preprocessing; subsequent calls: O(k)
inline ll qp(ll a, ll e){ ll r=1%M; a%=M; while(e){ if(e&1) r=r*a%M; a=a*a%M; e>>=1; } return r; }

ll sum_pow(ll n, int k){
    if(n <= 0) return 0;

    static int cached_k = -1, d = 0;
    static vector<ll> y, fact, ifac;

    if (k != cached_k){
        cached_k = k;
        d = k + 2;                      // d = k+2 nodes suffice
        y.assign(d+1, 0);               // y[i] = prefix sum of i^k
        for (int i=1; i<=d; ++i) y[i] = (y[i-1] + qp(i, k)) % M;

        fact.assign(d+1, 1);
        for (int i=1; i<=d; ++i) fact[i] = fact[i-1] * i % M;
        ifac.assign(d+1, 1);
        ifac[d] = qp(fact[d], M-2);
        for (int i=d; i>=1; --i) ifac[i-1] = ifac[i] * i % M;
    }

    if (n <= d) return y[(int)n];

    ll nm = n % M;
    vector<ll> pre(d+2, 1), suf(d+3, 1);
    for (int i=1; i<=d; ++i)  pre[i] = pre[i-1] * ((nm - i + M) % M) % M;
    for (int i=d; i>=1; --i)  suf[i] = suf[i+1] * ((nm - i + M) % M) % M;

    ll ans = 0;
    for (int i=1; i<=d; ++i){
        ll num     = pre[i-1] * suf[i+1] % M;              // product without (n-i)
        ll den_inv = ifac[i-1] * ifac[d-i] % M;
        ll term    = y[i] * num % M * den_inv % M;
        if ( (d - i) & 1 ) term = (M - term) % M;          // sign (-1)^{d-i}
        ans += term; ans %= M;
    }
    return ans;
}

// Usage: compute separate passes for each needed exponent k
// Pass 1: all s5 values
for (int i = 1; i <= s; ++i) s5[i] = sum_pow(d[i], 5);
// Pass 2: all s6 values
for (int i = 1; i <= s; ++i) s6[i] = sum_pow(d[i], 6);
```

## 1.3 Min_25 Core: Computing $h(x)$

The key observation is that all queried arguments of $h$ are of the form $i=\lfloor n/m\rfloor$.

In most problems $f(p)$ is a low-degree polynomial in $p$: $f(p)=\sum_t a_t p^t$. Each term $p^t$ is handled independently, so it suffices to solve the case $f(p)=p^t$.

**Goal:** for all $i=\lfloor n/m\rfloor$, compute $h(i)=\sum_{\substack{p\leq i\\p\text{ prime}}}p^t$.

**Idea:** simulate the Sieve of Eratosthenes, but instead of sieving primality, sieve a *weighted sum* $x^t$.

Define:
$$h'_{i,j}=\sum_{1\leq x\leq j}\bigl[x\text{ is 1, prime, or has no prime factor }\leq p_i\bigr]\cdot x^t$$

Intuitively: starting from all integers $1..j$, successively remove those whose smallest prime factor is $p_1,p_2,\ldots,p_i$. After all removals, only 1 and the primes remain.

**Transition:**

$$\boxed{\begin{aligned}
j\geq p_i^2:\quad &h'_{i,j}=h'_{i-1,j}-p_i^t\Bigl(h'_{i-1,\lfloor j/p_i\rfloor}-h'_{i-1,p_i-1}\Bigr)\\
j\lt p_i^2:\quad &h'_{i,j}=h'_{i-1,j}
\end{aligned}}$$

**Derivation:** going from $h'_{i-1}$ to $h'_{i}$, subtract the weights of numbers **first hit** by $p_i$. These are $y=p_i x$ where $x$ has no prime factor $\lt p_i$. Since $y\leq j\iff x\leq\lfloor j/p_i\rfloor$, and the sieve starts at $p_i^2$ (smaller $y$ would already be prime or handled earlier):

$$\text{removed weight}=\sum_{\substack{x\leq\lfloor j/p_i\rfloor\\x\text{ no factor }\lt p_i}}(p_i x)^t
=p_i^t\underbrace{\Bigl(h'_{i-1,\lfloor j/p_i\rfloor}-h'_{i-1,p_i-1}\Bigr)}_{\text{weight of }x\in[p_i,\lfloor j/p_i\rfloor]\text{ surviving sieve}}$$

When $j\lt p_i^2$ there is nothing to remove, so $h'_{i,j}=h'_{i-1,j}$.

**Why only the $\lfloor n/k\rfloor$ points?**

Min_25 maintains $h'$ only at the $s\approx2\sqrt{n}$ distinct values:
$$d[1..s]=\bigl(1,2,\ldots,m,\;\lfloor n/m\rfloor,\ldots,\lfloor n/2\rfloor,\lfloor n/1\rfloor\bigr),\quad m=\lfloor\sqrt{n}\rfloor$$

- Small half: $1,\ldots,m$ (covers all values $\leq m$).
- Large half: $\lfloor n/1\rfloor,\lfloor n/2\rfloor,\ldots,\lfloor n/m\rfloor$ (covers all large distinct floor values, strictly decreasing).
- When $n$ is a perfect square, $m$ appears in both halves — subtract 1: $s=2m-(m^2=n)$.

**O(1) index mapping:**
$$\text{id}(x)=\begin{cases}x,&x\leq m\\s-\lfloor n/x\rfloor+1,&x>m\end{cases}$$

**Complexity:** $O(n^{3/4}/\log n)$ time, $O(\sqrt{n})$ space.

**Code alignment** (two channels $k=0$ and $k=1$):
```cpp
// initialisation
g[i][0] = d[i] - 1;                         // sum_{x=2}^{d[i]} 1
g[i][1] = d[i]*(d[i]+1)/2 - 1;              // sum_{x=2}^{d[i]} x

// sieve step
g[j][k] -= (g[id(d[j]/p[i])][k] - g[id(p[i-1])][k]) * (k==0 ? 1 : p[i]);
```
After sieving, `g[*][0]` = $\pi(d[*])$ and `g[*][1]` = $\sum_{p\leq d[*]}p$.

## 1.4 DFS to compute $g(n,m)$

Define $g(n,m)=\sum_{\substack{2\leq x\leq n\\P^-(x)>m}}f(x)$, where $P^-(x)$ is the smallest prime factor of $x$. Then $\text{Ans}=f(1)+g(n,0)$.

$$g(n,m)=\underbrace{\sum_{\substack{m\lt p\leq n\\p\text{ prime}}}f(p)}_{h(n)-h(m)}+\sum_{\substack{m\lt p\leq n\\p\text{ prime}}}\sum_{\substack{e\geq1\\p^e\leq n}}f(p^e)\bigl([e>1]+g(\lfloor n/p^e\rfloor,p)\bigr)$$

Once $h$ is available (from the first phase), this DFS runs in $O(n^{3/4}/\log n)$.

## 1.5 Example: LOJ #6053 — A Simple Function

$$f(1)=1,\quad f(p^c)=p\oplus c,\quad f(ab)=f(a)f(b)\ (\gcd(a,b)=1). \quad\text{Compute }\sum_{i=1}^n f(i).$$

For odd primes $p$: $f(p)=p\oplus1=p-1$. For $p=2$: $f(2)=2\oplus1=3$.

$$h(x)=\sum_{p\leq x}(p\oplus1)=\underbrace{\Bigl(\sum_{p\leq x}p\Bigr)}_{S_1(x)}-\pi(x)+2$$

Run Min_25 with two channels ($t=0$ for $\pi$, $t=1$ for $\sum p$), combine as $h(i)=(s_1(i)-s_0(i)+2)\bmod M$.

```cpp
#include <bits/stdc++.h>
#define N 300005
#define M 1000000007
typedef long long ll;
using namespace std;
constexpr int qp(ll a,ll x=M-2){int res=1;for(;x;x>>=1,a=a*a%M)(x&1)&&(res=a*res%M);return res;}

struct min25 {
    bool vis[N];
    ll n, d[N], g[N][2], h[N];
    int m, s, cnt, p[N];

    int id(ll x){ return x <= m ? x : s - n/x + 1; }

    ll calc(ll nn) {
        int i, j, k;
        m = (int)sqrt(n = nn);
        s = 2*m - (1ll*m*m == n);
        cnt = 0;
        memset(vis, 0, (m+1)*sizeof(bool));

        // linear sieve: primes up to m
        for (i = 2; i <= m; ++i) {
            if (!vis[i]) p[++cnt] = i;
            for (j = 1; j <= cnt && 1ll*p[j]*i <= m; ++j) {
                vis[p[j]*i] = 1;
                if (i % p[j] == 0) break;
            }
        }
        p[0] = 1;  // sentinel for id(p[i-1]) when i=1

        // collect all distinct floor(n/i) values
        for (i = 1; i <= m; ++i) d[i] = i;
        for (i = 1; i <= m; ++i) d[s-i+1] = n/i;

        // initialise: sum_{x=2}^{d[i]} 1  and  sum_{x=2}^{d[i]} x
        for (i = 1; i <= s; ++i) {
            g[i][0] = (d[i] - 1) % M;
            g[i][1] = (d[i]%M) * ((d[i]+1)%M) % M * ((M+1)/2) % M - 1;
        }

        // Min_25 sieve (first phase): remove composites
        for (i = 1; i <= cnt; ++i)
            for (j = s; d[j] >= 1ll*p[i]*p[i]; --j)
                for (k = 0; k < 2; ++k)
                    (g[j][k] -= (g[id(d[j]/p[i])][k] - g[id(p[i-1])][k]) * (k==0 ? 1 : p[i]) % M) %= M;

        // combine into h[i] = S_1(d[i]) - pi(d[i]) + 2  (for d[i] >= 2)
        for (i = 1; i <= s; ++i) {
            h[i] = (g[i][1] - g[i][0] + (d[i] >= 2 ? 2 : 0)) % M;
            if (h[i] < 0) h[i] += M;
        }

        return (S(n, 0) + 1) % M;  // f(1)=1
    }

    // S(n, j) = g(n, p_j): DFS over smallest prime factor > p_j
    ll S(ll n, int j) {
        ll ans = (h[id(n)] - h[id(p[j])] + M) % M;
        if (n <= p[j]) return 0;

        for (int k = j+1; k <= cnt && 1ll*p[k]*p[k] <= n; ++k) {
            ll ml = p[k];
            for (int e = 1; ; ++e, ml *= p[k]) {
                // f(p^e) = p xor e
                ll add = (ll)(p[k]^e) * ((e>1) + S(n/ml, k) % M) % M;
                ans += add; ans %= M;
                if (ml > n/p[k]) break;
            }
        }
        return ans;
    }
} A;

int main() {
    ll n;
    if (scanf("%lld", &n) != 1) return 0;
    printf("%lld\n", A.calc(n));
    return 0;
}
```

## 1.6 Example: Luogu P5325 — Min_25 Template

$$f(p^k)=p^k(p^k-1),\quad\text{compute }\sum_{i=1}^n f(i)\pmod{10^9+7}.$$

$$h(x)=\sum_{p\leq x}p(p-1)=\Bigl(\sum_{p\leq x}p^2\Bigr)-\Bigl(\sum_{p\leq x}p\Bigr)$$

Requires two channels: $t=2$ (sum of $p^2$) and $t=1$ (sum of $p$).

Initialise: $g[i][0]=\sum_{x=2}^{d[i]}x^2-1$ (use closed form $\frac{n(n+1)(2n+1)}{6}-1$), $g[i][1]=\sum_{x=2}^{d[i]}x-1$.

Sieve step for $k=0$ (channel for $p^2$): multiply by $p[i]^2$ instead of $p[i]$.

> **Common pitfall:** multiplications of two `int` values produce `int` overflow. Always cast to `ll` or use `(ll)p[i]*p[i]%M`.

```cpp
#include <bits/stdc++.h>
#define N 300005
#define M 1000000007
typedef long long ll;
using namespace std;
constexpr int qp(ll a,ll x=M-2){int res=1;for(;x;x>>=1,a=a*a%M)(x&1)&&(res=a*res%M);return res;}

struct min25 {
    bool vis[N];
    ll n, d[N], g[N][2], h[N];
    int m, s, cnt, p[N];

    int id(ll x){ return x <= m ? x : s - n/x + 1; }

    ll calc(ll nn) {
        int i, j, k;
        m = (int)sqrt(n = nn);
        s = 2*m - (1ll*m*m == n);
        cnt = 0;
        memset(vis, 0, (m+1)*sizeof(bool));
        for (i = 2; i <= m; ++i) {
            if (!vis[i]) p[++cnt] = i;
            for (j = 1; j <= cnt && 1ll*p[j]*i <= m; ++j) {
                vis[p[j]*i] = 1;
                if (i % p[j] == 0) break;
            }
        }
        p[0] = 1;
        for (i = 1; i <= m; ++i) d[i] = i;
        for (i = 1; i <= m; ++i) d[s-i+1] = n/i;

        for (i = 1; i <= s; ++i) {
            int inv6 = qp(6);
            ll s2 = (d[i]%M) * ((d[i]+1)%M) % M * ((2*d[i]+1)%M) % M * inv6 % M;
            g[i][0] = (s2 - 1 + M) % M;           // sum of x^2 for x=2..d[i]
            g[i][1] = (d[i]%M) * ((d[i]+1)%M) % M * ((M+1)/2) % M - 1;  // sum of x
        }

        for (i = 1; i <= cnt; ++i)
            for (j = s; d[j] >= 1ll*p[i]*p[i]; --j)
                for (k = 0; k < 2; ++k)
                    (g[j][k] -= (g[id(d[j]/p[i])][k] - g[id(p[i-1])][k])
                        * (k==0 ? (ll)p[i]*p[i]%M : p[i]) % M) %= M;  // cast: avoid int overflow

        for (i = 1; i <= s; ++i) {
            h[i] = (g[i][0] - g[i][1] + M) % M;   // sum p^2 - sum p = sum p(p-1)
            if (h[i] < 0) h[i] += M;
        }

        return (S(n, 0) + 1) % M;
    }

    ll S(ll n, int j) {
        ll ans = (h[id(n)] - h[id(p[j])]) % M;
        if (ans < 0) ans += M;
        if (n <= p[j]) return 0;

        for (int k = j+1; k <= cnt && 1ll*p[k]*p[k] <= n; ++k) {
            ll ml = p[k];
            for (int e = 1; ; ++e, ml *= p[k]) {
                // f(p^e) = p^e * (p^e - 1); use __int128 to avoid ll overflow
                ll add = ((__int128_t)ml * (ml-1) % M) * ((S(n/ml, k) + (e>1)) % M) % M;
                ans += add; ans %= M;
                if (ml > n/p[k]) break;
            }
        }
        return ans;
    }
} A;

int main() {
    ll n;
    if (scanf("%lld", &n) != 1) return 0;
    printf("%lld\n", A.calc(n));
    return 0;
}
```

## 1.7 Variants: $\pi(n)$ and $\sum_{p\leq n}p$

After the first phase (sieve), before the DFS:
- **$\pi(n)$:** return `(g[id(n)][0] % M + M) % M`.
- **$\sum_{p\leq n}p$:** return `(g[id(n)][1] % M + M) % M`.

### Example: count $x\in[2,N]$ with $\text{spf}(x)=K$

$(2\leq N,K\leq10^9)$

**Transform:** set $m=\lfloor N/K\rfloor$. The condition $\text{spf}(x)=K$ with $x=Km$ is equivalent to $\text{spf}(m)\geq K$. So we count integers in $[1,m]$ with all prime factors $\geq K$ — exactly the Legendre $\phi$ function:
$$\phi(m,\pi(K-1))=1+g(m,p_{\pi(K-1)})$$

**Special cases:**
1. $K>N$: answer 0.
2. $K$ not prime: answer 0.
3. $K^2>N$: answer 1 (only $x=K$).
4. $K-1>\sqrt{m}$: all composites $\leq m$ have a prime factor $\leq\sqrt{m}\lt K-1$, so $g(m,p_{\pi(K-1)})=\pi(m)-\pi(K-1)$; answer $=\pi(m)-\pi(K-1)+1$.

```cpp
// pi(x) from sieved prime table
int pi(int x){ return (int)(upper_bound(p+1, p+cnt+1, x) - p) - 1; }
```

For case 4, the sieve must extend at least to $K-1$: `int limit = max(m, K-1)`.

---

# 2 Du Jiao Sieve

## 2.1 Overview

**Goal:** compute prefix sums $S(n)=\sum_{i=1}^n f(i)$ of a multiplicative function $f$ for large $n$.

**Core idea:** find two easy-to-sum multiplicative functions $g$ and $h$ with $h=f*g$, then use:

> $$S(n)=\sum_{i=1}^n h(i)-\sum_{d=2}^n g(d)\,S\!\left(\Bigl\lfloor\frac{n}{d}\Bigr\rfloor\right)$$

**Convolution–swap identity:**
$$\sum_{i\leq n}f(i)\Bigl\lfloor\frac{n}{i}\Bigr\rfloor=\sum_{m\leq n}(f*1)(m)$$

## 2.2 Template: $S_\mu(n)$ and $S_\varphi(n)$

Key identities:
$$\sum_{i\leq n}\mu(i)\Bigl\lfloor\frac{n}{i}\Bigr\rfloor=1,\qquad
\sum_{i\leq n}\varphi(i)\Bigl\lfloor\frac{n}{i}\Bigr\rfloor=\frac{n(n+1)}{2}$$

Convolution identities used: $\varepsilon=\mu*1$, $\mathrm{id}=\varphi*1$, $\varphi=\mu*\mathrm{id}$.

`MAXN` threshold: empirically $n^{2/3}$, default $5\times10^6$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

namespace Prime {
    vector<int> spf, prime, mu, phi;
    void initp(int n) {
        spf.resize(n+1, 0); mu.resize(n+1, 0); phi.resize(n+1, 0);
        mu[1] = 1; phi[1] = 1;                                            // base
        for (int i = 2; i <= n; ++i) {
            if (!spf[i]) { spf[i]=i; prime.push_back(i); mu[i]=-1; phi[i]=i-1; } // prime
            for (int j=0; j<(int)prime.size()&&prime[j]<=spf[i]&&i*prime[j]<=n; ++j) {
                int x = i * prime[j]; spf[x] = prime[j];
                if (i % prime[j] == 0) { mu[x]=0; phi[x]=phi[i]*prime[j]; break; }   // p^2 | x
                else                   { mu[x]=-mu[i]; phi[x]=phi[i]*(prime[j]-1); }  // new prime
            }
        }
    }
} using namespace Prime;

const int MAXN = 5000000;
vector<ll> sumMu, sumPhi;
unordered_map<ll,ll> cacheMu, cachePhi;

ll getMu(ll n){
    if (n <= MAXN) return sumMu[n];        // small n: table lookup
    if (cacheMu.count(n)) return cacheMu[n];
    ll ans = 1;
    for (ll l=2,r; l<=n; l=r+1){ ll t=n/l; r=n/t; ans -= (r-l+1)*getMu(t); }
    return cacheMu[n] = ans;
}

ll getPhi(ll n){
    if (n <= MAXN) return sumPhi[n];       // small n: table lookup
    if (cachePhi.count(n)) return cachePhi[n];
    ll ans = n*(n+1)/2;
    for (ll l=2,r; l<=n; l=r+1){ ll t=n/l; r=n/t; ans -= (r-l+1)*getPhi(t); }
    return cachePhi[n] = ans;
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    Prime::initp(MAXN);
    sumMu.resize(MAXN+1); sumPhi.resize(MAXN+1);
    sumMu[0]=0; sumPhi[0]=0;
    for (int i=1; i<=MAXN; ++i){ sumMu[i]=sumMu[i-1]+mu[i]; sumPhi[i]=sumPhi[i-1]+phi[i]; }
    cacheMu.reserve(1<<20); cachePhi.reserve(1<<20);
    int q; cin>>q;
    while(q--){ ll n; cin>>n; cout<<getPhi(n)<<" "<<getMu(n)<<"\n"; }
    return 0;
}
```

## 2.3 Useful Identities

$$\sum_{i=1}^n i=\frac{n(n+1)}{2},\quad
\sum_{i=1}^n i^2=\frac{n(n+1)(2n+1)}{6},\quad
\sum_{i=1}^n i^3=\left(\frac{n(n+1)}{2}\right)^2$$

$$\Bigl(\sum_{i=1}^n a_i\Bigr)^2=\sum_{i=1}^n a_i^2+2\sum_{1\leq i\lt j\leq n}a_ia_j$$

$$\sum_{k=0}^n\binom{n}{k}=2^n,\quad
\sum_{k=0}^n k\binom{n}{k}=n\cdot2^{n-1},\quad
\sum_{k=r}^n\binom{k}{r}=\binom{n+1}{r+1}\ (\text{hockey stick})$$

## 2.4 Example: Luogu P3768 — Simple Math Problem

$$\text{Compute }\sum_{i=1}^n\sum_{j=1}^n ij\,\gcd(i,j)\pmod{p}$$

**Derivation:** use $\gcd(i,j)=\sum_{d\mid\gcd(i,j)}\varphi(d)$, swap sums, substitute $i=id$, $j=jd$:

$$\sum_{d=1}^n\varphi(d)\cdot d^2\sum_{i=1}^{\lfloor n/d\rfloor}\sum_{j=1}^{\lfloor n/d\rfloor}ij
=\sum_{d=1}^n\varphi(d)\cdot d^2\left(\sum_{i=1}^{\lfloor n/d\rfloor}i\right)^2$$

Let $F(n)=\sum_{d=1}^n\varphi(d)d^2$. Then:
$$\text{Ans}=\sum_{d=1}^n F(\lfloor n/d\rfloor)\cdot\left(\sum_{i=1}^{\lfloor n/d\rfloor}i\right)^2$$

To compute $F$ via Du Jiao sieve, choose $f=\varphi\cdot\mathrm{id}^2$ and $g=\mathrm{id}^2$:
$$(f*g)(n)=\sum_{d\mid n}\varphi(d)d^2\cdot(n/d)^2=n^2\sum_{d\mid n}\varphi(d)=n^3$$

So $\sum_{i\leq n}(f*g)(i)=\sum_{i\leq n}i^3=\frac{n^2(n+1)^2}{4}$ and $\sum_{i\leq n}g(i)=\sum_{i\leq n}i^2=\frac{n(n+1)(2n+1)}{6}$.

Both computable in $O(1)$. Du Jiao sieve gives $F(n)$ in $O(n^{2/3})$.

> **Performance tip:** precompute `inv6 = qp(6)` once. Calling `qp(6)` inside every `sumg(n)` evaluation causes many redundant exponentiations.

```cpp
const int MAXN = 5000000;
vector<ll> sumf, sumPhi;
unordered_map<ll,ll> cachef;
ll inv6;

ll sumg(ll n){
    return ((ll)(n%M)*((n+1)%M)%M*((2*n+1)%M)%M*inv6)%M;
}

ll getf(ll n){
    if (n <= MAXN) return sumf[n];
    if (cachef.count(n)) return cachef[n];
    ll s1 = (ll)(n%M)*((n+1)%M)%M*((M+1)/2)%M;
    ll ans = s1*s1%M;
    for (ll l=2,r; l<=n; l=r+1){
        ll t=n/l; r=n/t;
        ans -= (ll)(sumg(r)-sumg(l-1)+M)%M * getf(t) % M;
        ans = (ans%M+M)%M;
    }
    return cachef[n] = ans;
}

signed main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    ll n; cin>>M>>n;
    inv6 = qp(6);
    Prime::initp(MAXN);
    sumf.resize(MAXN+1); sumPhi.resize(MAXN+1);
    sumf[0]=0; sumPhi[0]=0;
    for (int i=1; i<=MAXN; ++i){
        sumPhi[i]=(sumPhi[i-1]+phi[i])%M;
        sumf[i]=(sumf[i-1]+(ll)phi[i]*i%M*i%M)%M;
    }
    cachef.reserve(1<<20);
    ll ans=0;
    for (ll l=1,r; l<=n; l=r+1){
        ll v=n/l; r=n/v;
        ll dF=(getf(r)-getf(l-1)+M)%M;
        ll vv=v%M;
        ll S=vv*((v+1)%M)%M*qp(2)%M;
        ans=(ans+dF*S%M*S)%M;
    }
    if(ans<0) ans+=M;
    cout<<ans<<'\n';
    return 0;
}
```

## 2.5 $\varphi$ Prefix Sum with Modular Arithmetic

When $n$ is in the `ll` range and the modulus $M$ is variable, overflow is the main hazard:

```cpp
int M = 1e9+7;
int qp(ll a,ll x=M-2){int res=1;for(;x;x>>=1,a=a*a%M)(x&1)&&(res=a*res%M);return res;}

const int MAXN = 2000000;
vector<ll> sumf;
unordered_map<ll,ll> cachef;

inline ll sumH(ll n){
    n %= M;
    return (n * ((n+1)%M) % M) * qp(2) % M;
}
inline ll norm(ll x){ x%=M; if(x<0) x+=M; return x; }

ll getf(ll n){
    if (n <= MAXN) return sumf[n];
    auto it = cachef.find(n); if (it != cachef.end()) return it->second;
    ll ans = sumH(n);   // G(n) = sum_{k<=n} k  — use sumH to avoid ll*ll overflow
    for (ll l=2,r; l<=n; l=r+1){
        ll t=n/l; r=n/t;
        ll cnt=(r-l+1)%M;
        ans=norm(ans-cnt*getf(t)%M);
    }
    return cachef[n]=ans;
}

int main() {
    ll n; cin>>n;
    Prime::initp(MAXN);
    sumf.assign(MAXN+1, 0);
    for (int i=1; i<=MAXN; ++i) sumf[i]=(sumf[i-1]+(ll)phi[i])%M;
    cachef.reserve(1<<19);
    cout<<getf(n)<<'\n';
}
```

## 2.6 Sum of GCDs — 51Nod 1237

$$\sum_{i=1}^n\sum_{j=1}^n\gcd(i,j)=\sum_{d=1}^n\varphi(d)\Bigl\lfloor\frac{n}{d}\Bigr\rfloor^2$$

Apply divisibility blocking; compute $F(n)=\sum_{d\leq n}\varphi(d)$ via Du Jiao sieve.

> **Pitfall:** $t=\lfloor n/l\rfloor$ is `ll`, and $t^2$ overflows `ll`. Use `__int128` multiplication.

```cpp
ll ans = 0;
for (ll l=1,r; l<=n; l=r+1){
    ll t=n/l; r=n/t;
    ans += (__int128)(getf(r)-getf(l-1)+M)%M * t%M * t%M; ans%=M;
}
```

## 2.7 Sum of LCMs — 51Nod 1237 (variant)

$$\sum_{i=1}^n\sum_{j=1}^n\text{lcm}(i,j),\quad 1\leq n\leq10^{10}$$

**Useful identity:**
$$\sum_{i=1}^n i\cdot[\gcd(n,i)=1]=\frac{\varphi(n)\cdot n+[n=1]}{2}$$

**Derivation:**
$$\sum_{i,j}\text{lcm}(i,j)=\sum_{d=1}^n d\sum_{i=1}^{\lfloor n/d\rfloor}\sum_{j=1}^{\lfloor n/d\rfloor}ij\cdot[\gcd(i,j)=1]$$

By symmetry and the identity above, the inner double sum equals $\sum_{i=1}^{\lfloor n/d\rfloor}\varphi(i)\cdot i^2$.

Let $F(n)=\sum_{i=1}^n\varphi(i)\cdot i^2$. Then:
$$\text{Ans}=\sum_{d=1}^n d\cdot F\!\left(\Bigl\lfloor\frac{n}{d}\Bigr\rfloor\right)$$

$F$ uses the same Du Jiao sieve as P3768 (same $f=\varphi\cdot\mathrm{id}^2$).

$$F(n)=\frac{n^2(n+1)^2}{4}-\sum_{i=2}^n i^2\,F\!\left(\Bigl\lfloor\frac{n}{i}\Bigr\rfloor\right)$$

Final answer with one layer of divisibility blocking over $d$, total $O(n^{2/3})$.

```cpp
ll s1(ll n){ return ((ll)(n%M)*((n+1)%M)%M*qp(2))%M; }

signed main() {
    ll n; cin>>n;
    inv6 = qp(6);
    initp(MAXN);
    sumf.resize(MAXN+1); sumf[0]=0;
    for (int i=1; i<=MAXN; ++i) sumf[i]=(sumf[i-1]+(ll)phi[i]*i%M*i%M)%M;
    cachef.reserve(1<<20);
    ll ans=0;
    for (ll l=1,r; l<=n; l=r+1){
        ll t=n/l; r=n/t;
        ll dd=(s1(r)-s1(l-1)+M)%M;
        ans=(ans+(ll)dd*getf(t)%M)%M;
    }
    if(ans<0) ans+=M;
    cout<<ans<<'\n';
    return 0;
}
```

### Alternative derivation (Möbius approach)

$$\text{Ans}=\sum_{d=1}^n d\sum_{k=1}^{\lfloor n/d\rfloor}\mu(k)\Bigl(k\cdot S\!\Bigl(\Bigl\lfloor\frac{n}{kd}\Bigr\rfloor\Bigr)\Bigr)^2$$

Let $F(m)=\sum_{k=1}^m\mu(k)\Bigl(k\,S\!\bigl(\lfloor m/k\rfloor\bigr)\Bigr)^2$, then $\text{Ans}=\sum_{d=1}^n d\cdot F(\lfloor n/d\rfloor)$.
