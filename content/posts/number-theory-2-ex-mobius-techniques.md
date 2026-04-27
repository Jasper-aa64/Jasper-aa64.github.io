---
title: "Number Theory #2-ex: Möbius Techniques"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-2-ex-mobius-techniques"
description: "Seven core Möbius-inversion manipulation techniques: loop shortening, gcd-to-divisor conversion, reduction to coprimality indicator, Dirichlet convolution substitution, divisor symmetry, triangle-to-full-matrix, and value-domain inversion."
summary: "Seven core techniques for Möbius inversion problems: loop shortening, gcd indicator expansion, coprimality reduction, Dirichlet convolution via T=dk, divisor symmetry, diagonal symmetry, and value-domain cnt[] tricks."
categories: [Number Theory]
tags: [math, number-theory, mobius-inversion, dirichlet-convolution, techniques]
math: true
toc: true
---

(Continues from [Number Theory #2](../number-theory-2-multiplicative-functions))

## 0.1 Basic Identities

> $$\bullet\;[n=1]=\sum_{d\mid n}\mu(d)$$
> $$\bullet\;n=\sum_{d\mid n}\varphi(d)\;\implies\;\varphi(n)=\sum_{d\mid n}\mu(d)\cdot\frac{n}{d}$$
> $$\bullet\;\sigma(n)=\sum_{d\mid n}d$$

**Indicator / sieve identities**
- **Coprimality indicator:** $\displaystyle[\gcd(x,n)=1]=\sum_{d\mid\gcd(x,n)}\mu(d)$
- **Congruence indicator:** $[x\equiv y\pmod{d}]=[d\mid(x-y)]$

**Classical divisor sums**
- $\displaystyle\sum_{d\mid n}\varphi(d)=n$
- $\displaystyle\sum_{d\mid n}\mu(d)=[n=1]$
- $\displaystyle\sum_{d\mid n}\tau(d)=\sum_{d\mid n}\tau(n/d)\quad(\tau=1*1,\ \tau\text{ is the divisor-count function})$
- $\sigma=\mathrm{id}*\mathbf{1},\quad\tau=\mathbf{1}*\mathbf{1},\quad\varphi=\mu*\mathrm{id}$

**GCD variants**
- $\displaystyle\gcd(a,b)=\sum_{d\mid\gcd(a,b)}\varphi(d)$
- $\displaystyle\sum_{d\mid n}\mu(d)\Bigl\lfloor\frac{m}{d}\Bigr\rfloor$ = "count of $x\in[1,m]$ coprime to $n$" (inclusion-exclusion over prime factors of $n$)
- $\displaystyle d(xy)=\sum_{a\mid x}\sum_{b\mid y}[\gcd(a,b)=1]$

**GCD-layered substitution (very common)**
$$\sum_{k=1}^{n}f\!\bigl(\gcd(k,n)\bigr)=\sum_{d\mid n}f(d)\,\varphi\!\left(\frac{n}{d}\right)$$
(Group $k$ by $\gcd(k,n)=d$.)

---

# 1 Trick 1 — Loop Shortening via Divisibility

> When iterating $i=1,\ldots,n$, if the expression is non-zero only when $k\mid i$, shorten the loop:
> $$\sum_{i=1}^{n}[k\mid i]=\sum_{i=1}^{\lfloor n/k\rfloor}1=\Bigl\lfloor\frac{n}{k}\Bigr\rfloor$$

**Example:** $\displaystyle\sum_{i=1}^n\sum_{j=1}^m[\gcd(i,j)=k]$

Substitute $i=i'k$, $j=j'k$; the condition $\gcd(i,j)=k$ becomes $\gcd(i',j')=1$:
$$\sum_{i=1}^n\sum_{j=1}^m[\gcd(i,j)=k]=\sum_{i'=1}^{\lfloor n/k\rfloor}\sum_{j'=1}^{\lfloor m/k\rfloor}[\gcd(i',j')=1]$$

**Key point:** non-zero entries appear only every $k$ steps in both loops, so the range shrinks by factor $k$.

---

# 2 Trick 2 — Convert GCD-Divisors to Individual Divisors

$$[\gcd(x,y)=1]=\sum_{d\mid\gcd(x,y)}\mu(d)=\sum_{\substack{d\mid x\\d\mid y}}\mu(d)=\sum_{d=1}^{n}\mu(d)\cdot[d\mid x]\cdot[d\mid y]$$

> **Core idea:** $\gcd(i,j)$ varies with $i,j$ so its divisors are hard to enumerate directly. Use $d\mid\gcd(i,j)\iff d\mid i\text{ and }d\mid j$ to decouple the two indices.

**Example:** $\displaystyle\sum_{i=1}^n\sum_{j=1}^m[\gcd(i,j)=1]$

$$\begin{align}
\sum_{i=1}^n\sum_{j=1}^m[\gcd(i,j)=1]
&=\sum_{i=1}^n\sum_{j=1}^m\sum_{d\mid\gcd(i,j)}\mu(d)\\
&=\sum_{d=1}^{\min(n,m)}\mu(d)\sum_{i=1}^n[d\mid i]\sum_{j=1}^m[d\mid j]\\
&=\sum_{d=1}^{\min(n,m)}\mu(d)\Bigl\lfloor\frac{n}{d}\Bigr\rfloor\Bigl\lfloor\frac{m}{d}\Bigr\rfloor
\end{align}$$

The last sum is evaluated in $O\!\left(\sqrt{\min(n,m)}\right)$ via divisibility blocking.

### Example 1: Luogu P3455 [POI2007] ZAP-Queries

$$\text{Compute }\sum_{i=1}^n\sum_{j=1}^m[\gcd(i,j)=k],\quad 1\leq T,n,m,k\leq5\times10^4$$

- Trick 1: reduce to $\sum_{i=1}^{\lfloor n/k\rfloor}\sum_{j=1}^{\lfloor m/k\rfloor}[\gcd(i,j)=1]$.
- Trick 2: $=\displaystyle\sum_{d=1}^{\min(\lfloor n/k\rfloor,\lfloor m/k\rfloor)}\mu(d)\Bigl\lfloor\frac{\lfloor n/k\rfloor}{d}\Bigr\rfloor\Bigl\lfloor\frac{\lfloor m/k\rfloor}{d}\Bigr\rfloor$.

> **Supplementary identity:** $\displaystyle\Bigl\lfloor\frac{\lfloor n/k\rfloor}{d}\Bigr\rfloor=\Bigl\lfloor\frac{n}{kd}\Bigr\rfloor$. The two forms are equivalent; the right-hand form is cleaner in derivations, the left-hand form is more natural in code.

```cpp
int main(){
    long long t;
    read(t);
    get_mu(50000);
    while(t--){
        static long long a, b, d;
        read(a); read(b); read(d);
        static long long max_rep, ans;
        max_rep = min(a, b); ans = 0;
        for(long long l=1, r; l<=max_rep; l=r+1){
            r = min(a/(a/l), b/(b/l));
            ans += (a/(l*d)) * (b/(l*d)) * (sum[r] - sum[l-1]);
        }
        printf("%lld\n", ans);
    }
    return 0;
}
```

### Example 2: Luogu P2522 [HAOI2011] Problem b

$$\text{Compute }\sum_{i=x}^n\sum_{j=y}^m[\gcd(i,j)=k],\quad 1\leq T,x,y,n,m,k\leq5\times10^4$$

Reduce to four $(1,\cdot)$-based queries via 2D prefix-sum inclusion-exclusion:
$$\sum_{i=x}^n\sum_{j=y}^m[\gcd(i,j)=k]
=\sum_{1..n;1..m}-\sum_{1..x-1;1..m}-\sum_{1..n;1..y-1}+\sum_{1..x-1;1..y-1}$$

---

# 3 Trick 3 — Reduce a General $f(\gcd)$ Sum to $[\gcd=1]$ Form

> Replace the inner expression $f(\gcd(i,j))$ by $f(d)\cdot[\gcd(i',j')=1]$ by factoring out $d=\gcd(i,j)$.

The most common Möbius pattern: $\displaystyle\sum_{i=1}^n\sum_{j=1}^mf(\gcd(i,j))$.

Set $d=\gcd(i,j)$, $i=i'd$, $j=j'd$; then $\gcd(i',j')=1$ (otherwise $d$ is not maximal).

Add an outer loop over $d$ and shrink the inner ranges (Trick 1):
$$\begin{align}
\sum_{i=1}^n\sum_{j=1}^mf(\gcd(i,j))
&=\sum_{d=1}^{\min(n,m)}\sum_{i'=1}^{\lfloor n/d\rfloor}\sum_{j'=1}^{\lfloor m/d\rfloor}f(\gcd(i'd,j'd))\cdot[\gcd(i',j')=1]\\
&=\sum_{d=1}^{n}\sum_{i=1}^{\lfloor n/d\rfloor}\sum_{j=1}^{\lfloor m/d\rfloor}f(d)\cdot[\gcd(i,j)=1]
\end{align}$$

---

# 4 Trick 4 — Substitute $T=dk$ to Identify a Dirichlet Convolution

> When outer loop is $d$ and inner variable is $k$, and only their product $T=dk$ appears in floor expressions, swap to outer loop over $T$ and enumerate divisors $d\mid T$.

Starting from Trick 3:
$$S=\sum_{d=1}^n f(d)\sum_{i=1}^{\lfloor n/d\rfloor}\sum_{j=1}^{\lfloor m/d\rfloor}[\gcd(i,j)=1]$$

**Step 1.** Expand $[\gcd(i,j)=1]$ with Möbius, swap summation order:
$$S=\sum_{d=1}^n f(d)\sum_{k=1}^{\min(\lfloor n/d\rfloor,\lfloor m/d\rfloor)}\mu(k)
\sum_{i=1}^{\lfloor n/d\rfloor}[k\mid i]\;\sum_{j=1}^{\lfloor m/d\rfloor}[k\mid j]$$

**Step 2.** Replace divisibility counts:
$$\sum_{i=1}^{\lfloor n/d\rfloor}[k\mid i]=\Bigl\lfloor\frac{n}{dk}\Bigr\rfloor,\qquad
\sum_{j=1}^{\lfloor m/d\rfloor}[k\mid j]=\Bigl\lfloor\frac{m}{dk}\Bigr\rfloor$$

$$S=\sum_{d=1}^n f(d)\sum_{k=1}^{\min(\lfloor n/d\rfloor,\lfloor m/d\rfloor)}\mu(k)\Bigl\lfloor\frac{n}{dk}\Bigr\rfloor\Bigl\lfloor\frac{m}{dk}\Bigr\rfloor$$

**Step 3.** Set $T=dk$. For fixed $T$, all pairs $(d,k)$ with $dk=T$ correspond to divisors $d\mid T$ with $k=T/d$. Since $dk\leq\min(n,m)$, we have $T\leq\min(n,m)$:
$$S=\sum_{T=1}^{\min(n,m)}\Bigl\lfloor\frac{n}{T}\Bigr\rfloor\Bigl\lfloor\frac{m}{T}\Bigr\rfloor\sum_{d\mid T}f(d)\,\mu\!\left(\frac{T}{d}\right)$$

**Step 4.** Recognise the Dirichlet convolution $g=f*\mu$:
$$g(T)=\sum_{d\mid T}f(d)\,\mu\!\left(\frac{T}{d}\right)$$

$$\boxed{S=\sum_{T=1}^{\min(n,m)}g(T)\Bigl\lfloor\frac{n}{T}\Bigr\rfloor\Bigl\lfloor\frac{m}{T}\Bigr\rfloor}$$

> **General Formula 1.** Combining Tricks 3 and 4:
> $$\sum_{i=1}^n\sum_{j=1}^m f(\gcd(i,j))=\sum_{T=1}^{n}g(T)\Bigl\lfloor\frac{n}{T}\Bigr\rfloor\Bigl\lfloor\frac{m}{T}\Bigr\rfloor,\quad g=f*\mu$$
> **Limitation:** the inner expression must depend only on $\gcd(i,j)$ (a univariate function). This formula does not generalise to expressions involving $i$ or $j$ independently.

### 4.1 Example: ZAP-Queries via General Formula 1

With $f(x)=[x=k]$:
$$g(T)=\sum_{d\mid T}[d=k]\,\mu\!\left(\frac{T}{d}\right)=[k\mid T]\,\mu\!\left(\frac{T}{k}\right)$$

Apply Trick 1 (set $T=ik$):
$$\sum_{i=1}^{\min(\lfloor n/k\rfloor,\lfloor m/k\rfloor)}\mu(i)\Bigl\lfloor\frac{n}{ik}\Bigr\rfloor\Bigl\lfloor\frac{m}{ik}\Bigr\rfloor$$

Evaluate with divisibility blocking.

---

# 5 Trick 5 — Divisor Symmetry: $d\leftrightarrow n/d$

> When $d$ runs over all divisors of $n$, $d$ and $n/d$ are in bijection.

Example:
$$\frac{1}{2}\sum_{d\mid n}\frac{n^2}{d}\,\varphi\!\left(\frac{n}{d}\right)+\frac{n}{2}
=\frac{1}{2}\sum_{d\mid n}n\cdot d\,\varphi(d)+\frac{n}{2}$$

(Replace $d\to n/d$ throughout the divisor sum.)

---

# 6 Trick 6 — Diagonal Symmetry: Upper Triangle vs Full Matrix

> **When $f(i,j)=f(j,i)$, convert between the full double sum and the upper-triangle sum.**

## 6.1 Upper-triangle and lower-triangle

$$\sum_{i=1}^n\sum_{j=i}^n f(i,j)=\sum_{j=1}^n\sum_{i=1}^j f(i,j)$$

Both sides sum the upper-triangle region (including the diagonal); only the summation order differs.

## 6.2 Upper-triangle sum and full-matrix sum

$$\sum_{i=1}^n\sum_{j=i}^n f(i,j)
=\frac{\displaystyle\sum_{i=1}^n\sum_{j=1}^n f(i,j)+\sum_{i=1}^n f(i,i)}{2}$$

"Upper triangle including diagonal" = (full matrix + diagonal) / 2.

Equivalently:
$$\sum_{i=1}^n\sum_{j=1}^n f(i,j)=2\sum_{i=1}^n\sum_{j=i}^n f(i,j)-\sum_{i=1}^n f(i,i)$$

---

# 7 Trick 7 — Value-Domain Möbius with $\mathrm{cnt}[\,]$

> **Overview:** standard Möbius problems operate on $1,2,\ldots,n$. When the input is an array $a[1\cdots n]$ and summation involves number-theoretic functions of array values, introduce:
> - $w[y]$ = number of times value $y$ appears in $a[\cdot]$
> - $\mathrm{cnt}[d]$ = number of elements in $a[\cdot]$ divisible by $d$

**Example.** Given $a[1\cdots n]$ with $1\leq a_i\leq n$, compute:
$$\sum_{i=1}^n\sum_{j=1}^n\bigl(\gcd(a[i],a[j])+[\gcd(a[i],a[j])\neq1]\bigr)$$

Split into two parts:
$$\underbrace{\sum_{i,j}\gcd(a[i],a[j])}_{P_1}+\underbrace{\sum_{i,j}[\gcd(a[i],a[j])\neq1]}_{P_2}$$

**Computing $P_2$ (non-coprime pairs):**

Expand $[\gcd=1]=\sum_{d\mid\gcd}\mu(d)$, decouple with Trick 2:
$$\sum_{i,j}[\gcd(a[i],a[j])=1]=\sum_{d=1}^V\mu(d)\Bigl(\sum_i[d\mid a[i]]\Bigr)^2=\sum_{d=1}^V\mu(d)\,\mathrm{cnt}^2(d)$$

$$P_2=n^2-\sum_{d=1}^V\mu(d)\,\mathrm{cnt}^2(d)$$

**Computing $P_1$ (sum of GCDs):**

Use Euler inversion $\mathrm{id}=\varphi*\mathbf{1}$, i.e.\ $\gcd(a,b)=\sum_{d\mid\gcd(a,b)}\varphi(d)$, then Trick 2:
$$P_1=\sum_{i,j}\gcd(a[i],a[j])=\sum_{d=1}^V\varphi(d)\,\mathrm{cnt}^2(d)$$

**Final answer:**
$$\text{Answer}=n^2+\sum_{d=1}^V\bigl(\varphi(d)-\mu(d)\bigr)\,\mathrm{cnt}^2(d)$$

**Computing $\mathrm{cnt}[d]$:** build $w[y]$ (frequency array), then for each $d$ accumulate $w[d]+w[2d]+\cdots$ — harmonic-series cost $O(V\log V)$.

**Complexity:** $O(V\log V)$ overall, $V=\max\{a_i\}$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int N = 100000 + 10;   // set to max(a[i]) + 5 as needed
const int P = 998244353;

int n, v;
int a[N], w[N];

bool st[N];
int primes[N], tot;
int mu[N]; ll phi[N];
ll cnt[N];
vector<int> g[N];  // g[x][0] = smallest prime factor of x

// sieve + phi + mu
void get_primes(int nmax) {
    phi[1] = 1;
    for (int i = 1; i <= nmax; i++) mu[i] = 1;
    for (int i = 2; i <= nmax; i++) {
        if (!st[i]) {
            primes[tot++] = i;
            mu[i] = -1;
            phi[i] = i - 1;
            for (int j = i + i; j <= nmax; j += i) {
                st[j] = true;
                g[j].push_back(i);
                if ((j / i) % i == 0) mu[j] = 0;
                else if (mu[j] != 0) mu[j] = -mu[j];
            }
        } else {
            int p = g[i][0];        // smallest prime factor of i
            int now = i / p;
            if (now % p == 0) phi[i] = 1LL * p * phi[now];
            else              phi[i] = 1LL * (p - 1) * phi[now];
        }
    }
}

// cnt[d] = number of elements in a[] divisible by d
void get_cnt() {
    for (int i = 1; i <= n; i++) w[a[i]]++;
    cnt[1] = n;
    for (int d = 2; d <= v; d++) {
        for (int j = d; j <= v; j += d) {
            cnt[d] += w[j];   // no modular reduction: cnt[d] <= n
        }
    }
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    cin >> n;
    v = 0;
    for (int i = 1; i <= n; i++) {
        cin >> a[i];
        v = max(v, a[i]);
    }

    get_primes(v);
    get_cnt();

    ll ans = 1LL * n * n % P;
    for (int d = 1; d <= v; d++) {
        ll term = (((phi[d] - mu[d]) % P) + P) % P;
        ll cd   = cnt[d] % P;
        ans = (ans + term * cd % P * cd) % P;
    }
    cout << ans << '\n';
    return 0;
}
```
