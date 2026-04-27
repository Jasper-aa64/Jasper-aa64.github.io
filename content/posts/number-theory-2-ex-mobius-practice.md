---
title: "Number Theory #2-ex: Möbius Practice — LCM Sums, Divisor-Count, Omega Numbers"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-2-ex-mobius-practice"
description: "Worked examples applying Möbius techniques: SPOJ LCMSUM, Crash's Digital Table (two-layer blocking, O(n^3/4)), HDU 4944 FSF's Game (offline difference), SDOI2015 divisor-count sum, and CF 2176F Omega Numbers."
summary: "Practice problems for Möbius inversion: LCMSUM, two-variable lcm sum (O(n^3/4)), FSF's game with offline difference, divisor-count sum d(ij), Omega Numbers with Dirichlet suffix sum."
categories: [Number Theory]
tags: [math, number-theory, mobius-inversion, lcm, divisor-count, competitive-programming]
math: true
toc: true
---

(Continues from [Möbius Techniques](../number-theory-2-ex-mobius-techniques))

# 1 LCM Problems

## 1.1 SPOJ 5971 LCMSUM

> Compute (multiple test cases): $\displaystyle\sum_{i=1}^n\operatorname{lcm}(i,n)$
> $(1\leq T\leq3\times10^5,\;1\leq n\leq10^6)$

Rewrite with $\text{lcm}(i,n)=\tfrac{in}{\gcd(i,n)}$:
$$\sum_{i=1}^n\frac{in}{\gcd(i,n)}$$

Extract the $i=n$ term ($=n$) and pair the remaining terms $i$ and $n-i$ (noting $\gcd(i,n)=\gcd(n-i,n)$):

$$\frac{1}{2}\left(\sum_{i=1}^{n-1}\frac{in}{\gcd(i,n)}+\sum_{j=n-1}^1\frac{jn}{\gcd(j,n)}\right)+n=\frac{1}{2}\sum_{i=1}^{n-1}\frac{n^2}{\gcd(i,n)}+n=\frac{1}{2}\sum_{i=1}^n\frac{n^2}{\gcd(i,n)}+\frac{n}{2}$$

Apply Trick 3: substitute $d=\gcd(i,n)$, sum over divisors $d\mid n$, inner sum becomes $\varphi(n/d)$:

$$\frac{1}{2}\sum_{d\mid n}\frac{n^2}{d}\sum_{i=1}^{n/d}\left[\gcd\!\left(i,\tfrac{n}{d}\right)=1\right]+\frac{n}{2}=\frac{1}{2}\sum_{d\mid n}\frac{n^2}{d}\,\varphi\!\left(\frac{n}{d}\right)+\frac{n}{2}$$

Apply Trick 5 ($d\leftrightarrow n/d$):

$$\frac{1}{2}\sum_{d\mid n}n\cdot d\,\varphi(d)+\frac{n}{2}=\frac{n}{2}\!\left(\sum_{d\mid n}d\,\varphi(d)+1\right)$$

Let $g(n)=\sum_{d\mid n}d\,\varphi(d)$. Precompute:
1. Linear sieve for $\varphi$ in $O(n)$.
2. $h(d)=d\,\varphi(d)$ in $O(n)$.
3. Divisor convolution for $g$ in $O(n\log n)$.
4. Final answer for each query: $\tfrac{n}{2}(g(n)+1)$ in $O(1)$.

## 1.2 Luogu P1829 / BZOJ 2154 — Crash's Digital Table

> Compute (mod $20101009$): $\displaystyle\sum_{i=1}^n\sum_{j=1}^m\operatorname{lcm}(i,j)$
> $(1\leq n,m\leq10^7)$

Assume $n\leq m$. Rewrite $\text{lcm}(i,j)=ij/\gcd(i,j)$.

Apply Trick 3 ($d=\gcd$):
$$\sum_{d=1}^n d\sum_{i=1}^{\lfloor n/d\rfloor}\sum_{j=1}^{\lfloor m/d\rfloor}[\gcd(i,j)=1]\cdot i\cdot j$$

Define:
$$h(n,m)=\sum_{i=1}^n\sum_{j=1}^m[\gcd(i,j)=1]\cdot i\cdot j$$

so the answer is $\displaystyle\sum_{d=1}^n d\cdot h\!\left(\lfloor n/d\rfloor,\lfloor m/d\rfloor\right)$.

Expand $[\gcd(i,j)=1]$ with Trick 2, then apply Trick 1:
$$h(n,m)=\sum_{d=1}^{\min(n,m)}\mu(d)\sum_{i=1}^n[d\mid i]\cdot i\cdot\sum_{j=1}^m[d\mid j]\cdot j
=\sum_{d=1}^{\min(n,m)}\mu(d)\,d^2\,S\!\left(\Bigl\lfloor\frac{n}{d}\Bigr\rfloor\right)S\!\left(\Bigl\lfloor\frac{m}{d}\Bigr\rfloor\right)$$

where $S(n)=\sum_{i=1}^n i=\tfrac{n(n+1)}{2}$ (computed in $O(1)$).

$h(n,m)$ is evaluated with divisibility blocking in $O(\sqrt{\min(n,m)})$.

**Complexity:** outer blocking over $d$ takes $O(\sqrt{n})$ steps; each step calls $h$ costing $O(\sqrt{n/d})$; combined $O(n^{3/4})$.

```cpp
#include <bits/stdc++.h>
using namespace std;

#define el '\n'
typedef long long LL;
constexpr int N = 1e7 + 10, md = 20101009;

int T, n, m;
int primes[N], cnt, mu[N];
bool vis[N];

void seive(){} // linear sieve to fill mu[]

LL sum[N], a[N];

void prepare(){
    seive();
    for(int i = 1; i < N; i++){
        LL tmp = 1LL * i * i % md * mu[i] % md;
        sum[i] = (sum[i-1] + tmp) % md;   // prefix sum of i^2 * mu[i]
    }
}

LL R(LL n){ return (1 + n) * n / 2 % md; }

int g(int n, int d){ return n / (n / d); }  // right endpoint of divisibility block

LL h(int n, int m){
    LL res = 0;
    int sn = min(n, m);
    for(int l = 1, r; l <= sn; l = r + 1){
        r = min(g(n, l), g(m, l));
        LL tmp = (sum[r] - sum[l-1]) * R(n/l) % md * R(m/l) % md;
        res = (res + tmp) % md;
    }
    return res;
}

LL cal(int n, int m){
    LL res = 0;
    int sn = min(n, m);
    for(int l = 1, r; l <= sn; l = r + 1){
        r = min(g(n, l), g(m, l));
        LL tmp = (R(r) - R(l-1)) % md * h(n/l, m/l);
        res = (res + tmp) % md;
    }
    if(res < 0) res += md;
    return res;
}

int main(){
    prepare();
    cin >> n >> m;
    cout << cal(n, m) << el;
}
```

## 1.3 HDU 4944 — FSF's Game

> Compute (mod $2^{32}$, multiple test cases $T\leq5\times10^5$):
> $$\sum_{i=1}^n\sum_{j=i}^n\sum_{\substack{d\mid i\\d\mid j}}\frac{ij}{\gcd(i/d,\,j/d)},\quad 1\leq n\leq5\times10^5$$

### Solution

Use $\gcd(i/d,j/d)=\gcd(i,j)/d$, so each term $\frac{ij}{\gcd(i/d,j/d)}=\frac{ij\cdot d}{\gcd(i,j)}=\text{lcm}(i,j)\cdot d$.

The sum becomes:
$$\sum_{i=1}^n\sum_{j=i}^n\sum_{\substack{d\mid i\\d\mid j}}\text{lcm}(i,j)\cdot d$$

Apply Trick 1 (set $i=i'd$, $j=j'd$, outer loop over $d$):
$$\sum_{d=1}^n d^2\sum_{i=1}^{\lfloor n/d\rfloor}\sum_{j=i}^{\lfloor n/d\rfloor}\text{lcm}(i,j)$$

Let $s(n)=\sum_{i=1}^n\sum_{j=i}^n\text{lcm}(i,j)$. The answer is $\displaystyle\sum_{d=1}^n d^2\cdot s\!\left(\lfloor n/d\rfloor\right)$.

**Approach 1 (TLE):** compute $s$ via the relation $s(n)=\frac{\sum_{i,j}\text{lcm}(i,j)+\sum_i i}{2}$ using the LCMSUM formula. Each $s(\lfloor n/d\rfloor)$ costs $O(n)$; with $O(\sqrt{n})$ outer steps and $T$ test cases: $O(Tn\sqrt{n})\approx3\times10^8$ — too slow.

**Approach 2 (offline difference):**

Use the incremental identity from LCMSUM:
$$s(n)-s(n-1)=\sum_{i=1}^n\text{lcm}(i,n)=\frac{n}{2}\Bigl(1+\sum_{d\mid n}d\,\varphi(d)\Bigr)$$

Precompute:
1. Linear sieve for $\varphi$ in $O(N)$.
2. $h(d)=d\,\varphi(d)$; divisor convolution to get $g(n)=\sum_{d\mid n}d\,\varphi(d)$ in $O(N\log N)$.
3. $s(n)=\sum_{t=1}^n\frac{t}{2}(1+g(t))$ by prefix sum in $O(N)$.

For $\text{Ans}(n)=\sum_{d=1}^n d^2\cdot s(\lfloor n/d\rfloor)$, note that for $n\in[dk,\,d(k+1)-1]$ the quotient $\lfloor n/d\rfloor=k$ is constant, contributing $d^2\cdot s(k)$ to every $n$ in that range.

**Offline difference:** build `ans[]` such that for each $(d,k)$:
```cpp
ans[d*k]     += d^2 * s(k)
ans[d*(k+1)] -= d^2 * s(k)   // if d*(k+1) <= N
```
Then prefix-sum `ans[]` to get all $\text{Ans}(1..N)$. Each query is $O(1)$.

**Complexity:** $O(N\log N)$ precomputation; works for $N=5\times10^5$.

> **General technique:** to compute $H(n)=\sum_{d=1}^n f(d)\,g(\lfloor n/d\rfloor)$ for all $n=1..N$ simultaneously:
>
> For each $d$ and $k=1..\lfloor N/d\rfloor$, when $n\in[dk,\,d(k+1)-1]$ the value $\lfloor n/d\rfloor=k$ is constant and adds $f(d)g(k)$ to every $n$ in the block. Use a difference array:
> ```
> diff[d*k]       += f(d)*g(k)
> diff[d*(k+1)]   -= f(d)*g(k)   // if d*(k+1) <= N
> ```
> Final prefix sum gives $H[n]$.

```cpp
#include <bits/stdc++.h>
using namespace std;
typedef long long LL;
constexpr int N = 5e5 + 10;

int T, n;
int primes[N], cnt;
bool vis[N];
LL phi[N];

void seive(){
    phi[1] = 1;
    for(int i = 2; i < N; i++){
        if(!vis[i]){
            primes[cnt++] = i;
            phi[i] = i - 1;
        }
        for(int j = 0; j < cnt && 1LL * primes[j] * i < N; j++){
            LL t = primes[j] * i;
            vis[t] = true;
            if(i % primes[j] == 0){
                phi[t] = phi[i] * primes[j];
                break;
            }
            phi[t] = phi[i] * (primes[j] - 1);
        }
    }
}

LL h[N], g[N], s[N], ans[N];

void init(){
    seive();
    for(int d = 1; d < N; d++) h[d] = d * phi[d];
    for(int d = 1; d < N; d++)
        for(int n = d; n < N; n += d)
            g[n] += h[d];                        // g[n] = sum_{d|n} d*phi[d]
    for(int n = 1; n < N; n++)
        s[n] = s[n-1] + (g[n] + 1) * n / 2;     // s[n] = sum_{t=1}^n lcm-row sum
    for(int d = 1; d < N; d++){
        for(int i = 1; 1LL * i * d < N; i++){
            LL tmp = 1LL * d * d * s[i];
            ans[d*i] += tmp;
            if(d * (i+1) < N) ans[d*(i+1)] -= tmp;
        }
    }
    for(int i = 1; i < N; i++) ans[i] += ans[i-1];  // prefix sum to get Ans(n)
}

int main(){
    init();
    cin >> T;
    for(int t = 1; t <= T; t++){
        cin >> n;
        cout << "Case #" << t << ": " << (unsigned)ans[n] << '\n';
    }
}
```

---

# 2 Classical Example

## 2.1 SDOI2015 — Sum of Divisor Counts

> Compute (multiple test cases):
> $$\sum_{i=1}^n\sum_{j=1}^m d(i\cdot j)\quad(1\leq n,m,T\leq5\times10^4)$$
> where $d(n)=\sum_{d\mid n}1$ is the number-of-divisors function.

**Key identity.** For any positive integers $x,y$:
$$d(xy)=\sum_{a\mid x}\sum_{b\mid y}[\gcd(a,b)=1]$$

*(Proof sketch: each divisor of $xy$ corresponds to distributing prime-power exponents between $x$ and $y$; the coprimality condition ensures no prime is counted in both $a$ and $b$.)*

**Möbius inversion to remove the GCD condition:**
$$\begin{align}
d(xy)&=\sum_{a\mid x}\sum_{b\mid y}\sum_{k\mid\gcd(a,b)}\mu(k)\\
&=\sum_{k=1}^{\min(x,y)}\mu(k)\sum_{\substack{a\mid x\\k\mid a}}1\;\sum_{\substack{b\mid y\\k\mid b}}1\\
&=\sum_{\substack{k\mid x\\k\mid y}}\mu(k)\,d\!\left(\frac{x}{k}\right)d\!\left(\frac{y}{k}\right)
\end{align}$$

Substitute into the double sum and swap:
$$\sum_{i\leq n}\sum_{j\leq m}d(ij)
=\sum_{k=1}^{\min(n,m)}\mu(k)\Bigl(\sum_{\substack{i\leq n\\k\mid i}}d(i/k)\Bigr)\Bigl(\sum_{\substack{j\leq m\\k\mid j}}d(j/k)\Bigr)
=\boxed{\sum_{k=1}^{\min(n,m)}\mu(k)\,S\!\left(\Bigl\lfloor\frac{n}{k}\Bigr\rfloor\right)S\!\left(\Bigl\lfloor\frac{m}{k}\Bigr\rfloor\right)}$$

where $S(t)=\sum_{x=1}^t d(x)$.

**Precomputation** (all in $O(N)$, $N=5\times10^4$):
- Linear sieve for $\mu$ and prefix sums $\text{preMu}$.
- Divisor count $d$ as a multiplicative function via linear sieve ($\text{calc\_f}(p,k)=k+1$).
- Prefix sums $S$.

**Query:** divisibility blocking over $k$; each block $[l,r]$ with constant $\lfloor n/k\rfloor,\lfloor m/k\rfloor$ contributes $(\text{preMu}[r]-\text{preMu}[l-1])\cdot S(n/l)\cdot S(m/l)$.

**Complexity:** $O(N)$ preprocessing, $O(\sqrt{\min(n,m)})$ per query.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int N = 50000;

int p[N], pcnt;
bool vis[N+1];
int mu[N+1], preMu[N+1];
int d[N+1], cnt[N+1];   // cnt[n] = exponent of smallest prime factor of n
ll S[N+1];

int calc_f(int p, int k){ return k + 1; }  // d(p^k) = k+1

void sieveAll() {
    mu[1] = 1; d[1] = 1;
    for (int i = 2; i <= N; ++i) {
        if (!vis[i]) {
            p[pcnt++] = i;
            mu[i] = -1;
            d[i] = 2;    // d(p^1) = 2
            cnt[i] = 1;
        }
        for (int j = 0; j < pcnt && 1LL*p[j]*i <= N; ++j) {
            int x = p[j] * i;
            vis[x] = true;
            if (i % p[j] == 0) {
                mu[x] = 0;
                cnt[x] = cnt[i] + 1;
                d[x] = d[i] / calc_f(p[j], cnt[i]) * calc_f(p[j], cnt[i]+1);
                break;
            }
            mu[x] = -mu[i];
            cnt[x] = 1;
            d[x] = d[i] * calc_f(p[j], 1);
        }
    }
    for (int i = 1; i <= N; ++i) {
        preMu[i] = preMu[i-1] + mu[i];
        S[i] = S[i-1] + d[i];
    }
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    sieveAll();
    int T; cin >> T;
    while (T--) {
        int n, m; cin >> n >> m;
        int L = min(n, m);
        ll ans = 0;
        for (int l = 1, r; l <= L; l = r + 1) {
            int vn = n / l, vm = m / l;
            r = min(n / vn, m / vm);
            ans += 1LL * (preMu[r] - preMu[l-1]) * S[vn] * S[vm];
        }
        cout << ans << '\n';
    }
    return 0;
}
```

---

# 3 Other Problems

## 3.1 2025 ICPC Network Round B — Creating Chaos (identity proof)

**Approach:** always keep $k$ consecutive elements.

**Key identity:**
$$\gcd(x,n)=\sum_{\substack{d\mid x\\d\mid n}}\varphi(d)$$

**Proof:** from $\sum_{d\mid m}\varphi(d)=m$, substitute $m=\gcd(x,n)$.

$$\begin{aligned}
F(S)&=\sum_{1\leq i\lt j\leq m}\gcd(|a_i-a_j|,n)
=\sum_{1\leq i\lt j\leq m}\sum_{d\mid n}\varphi(d)\,[d\mid(a_i-a_j)]\\
&=\sum_{d\mid n}\varphi(d)\sum_{i=1}^{n-k-1}\sum_{j=i+1}^{n-k}[(a_i-a_j)\bmod d=0]
\end{aligned}$$

Since keeping $n-k$ consecutive elements always minimises $\sum_{i\lt j}[(a_i-a_j)\bmod d=0]$ for every $d$, it minimises $F(S)$.

## 3.2 CF 2176F — Omega Numbers

> Compute:
> $$f(a,k)=\sum_{i\lt j}\omega(a_i\cdot a_j)^k$$
> where $\omega(n)$ = number of distinct prime factors of $n$.

### Key identity

$$\omega(a_i\cdot a_j)=\omega(a_i)+\omega(a_j)-\omega(\gcd(a_i,a_j))$$

So:
$$f(a,k)=\sum_{i\lt j}\bigl(\omega(a_i)+\omega(a_j)-\omega(\gcd(a_i,a_j))\bigr)^k$$

### Algorithm

**Step 1.** Sieve $\omega(x)$ for $1\leq x\leq N$ (each prime contributes 1 to all its multiples).

**Step 2.** Build `naive[g][s]` = number of ordered pairs $(i,j)$ with $g\mid a_i$, $g\mid a_j$, and $\omega(a_i)+\omega(a_j)=s$.

For each $g$: collect the bucket `cnt[w]` = count of elements divisible by $g$ with $\omega=w$; then convolve to get the ordered-pair counts; subtract diagonal ($i=j$) and divide by 2 to get unordered pairs.

**Step 3.** Convert `naive` to `exact` (GCD exactly $g$) via reverse Möbius (sweep $g$ from $N$ down to $1$):
$$\text{cnt}[g][s]=\text{naive}[g][s]-\sum_{k=2,3,\ldots}\text{cnt}[kg][s]$$

**Step 4.** Answer:
$$\text{Answer}=\sum_{g=1}^N\sum_s\text{cnt}[g][s]\cdot(s-\omega(g))^k$$

**Complexity:** $O(N\log N\cdot W^2)$ where $W\leq7$ ($\omega\leq7$ for $n\leq10^6$).

```cpp
const int M = 998244353;
int omega[maxn];

constexpr int qp(ll a, ll x = M-2){
    int res=1; for(;x;x>>=1,a=a*a%M)(x&1)&&(res=a*res%M); return res;
}

void sieve() {
    fill(omega, omega + maxn, 0);
    for (int i = 2; i < maxn; i++) {
        if (omega[i] == 0) {           // i is prime
            for (int j = i; j < maxn; j += i)
                omega[j]++;
        }
    }
}

void solve() {
    int n; long long k;
    cin >> n >> k;

    vector<int> freq(n+10);
    for (int i = 0; i < n; i++) { int val; cin >> val; freq[val]++; }

    vector exact(n+10, vector<int>(2*8));

    for (int g = 1; g <= n; g++) {
        vector<ll> cnt(8);
        for (int j = g; j <= n; j += g) cnt[omega[j]] += freq[j];

        // naive: all ordered pairs among multiples of g
        for (int w1 = 0; w1 < 8; w1++)
            for (int w2 = 0; w2 < 8; w2++)
                exact[g][w1+w2] = (exact[g][w1+w2] + cnt[w1]*cnt[w2] % M) % M;

        // remove diagonal (i == j)
        for (int w = 0; w < 8; w++)
            exact[g][w+w] = (exact[g][w+w] - cnt[w] + M) % M;

        ll inv2 = (M + 1) / 2;
        for (int s = 0; s < 2*8; s++)
            exact[g][s] = exact[g][s] * inv2 % M;
    }

    // exact: subtract multiples (reverse Möbius)
    for (int g = n; g >= 1; g--)
        for (int j = 2*g; j <= n; j += g)
            for (int s = 0; s < 2*8; s++)
                exact[g][s] = (exact[g][s] - exact[j][s] + M) % M;

    ll ans = 0;
    for (int g = 1; g <= n; g++)
        for (int s = 0; s < 2*8; s++){
            int val = s - omega[g];
            ans = (ans + (ll)exact[g][s] * qp(val, k)) % M;
        }
    cout << ans << "\n";
}

signed main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int T = 1;
    sieve();
    cin >> T;
    while(T--) solve();
    return 0;
}
```

### Alternative: Dirichlet suffix sum + subset inversion

View each $a_i$ as its set of distinct prime factors $S_i$ with $|S_i|=\omega_i\leq6$. The sum becomes $\sum_{i\lt j}|S_i\cup S_j|^k$.

For each $i$ and target $t$, count $j$ with $|S_i\cup S_j|=t$. Decompose by $|S_j|$ and $S_j\cap S_i$: define $g_{siz,S}=\#\{j:|S_j|=siz,\,S_j\cap S_i=S\}$.

Compute $f_{siz,S}=\sum_{|S_j|=siz}[S\subseteq S_j]$ via a Dirichlet suffix sum over prime indices (harmonic-series or Eratosthenes-style sweep). Then by superset Möbius inversion:
$$g_{siz,S}=\sum_{S\subseteq T}(-1)^{|T|-|S|}f_{siz,T}$$

Enumerate subsets explicitly. Subtract self-pairs, accumulate $i$'s contribution, divide by 2.

**Complexity:** $O(n\cdot3^\omega\cdot\omega)$, $\omega\leq6$.
