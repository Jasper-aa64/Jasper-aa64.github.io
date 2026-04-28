---
title: "Number Theory #3: From Eratosthenes to Möbius Inclusion-Exclusion"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-3-sieve-mobius-inclusion-exclusion"
description: "Computing μ via Eratosthenes sieving; the three-function framework (multiples count g, exact count f, coprime count h); Möbius inclusion-exclusion conclusions with worked examples and CF 803F full solution."
summary: "Eratosthenes sieve for μ; g/f/h framework; Conclusions 1 and 2 with derivations and tables; GCD table intuition; CF 803F Coprime Subsequences with bottom-up and Möbius approaches."
categories: [Number Theory]
tags: [math, number-theory, mobius, sieve, inclusion-exclusion, coprime]
math: true
toc: true
---

(Continues from [Number Theory #2](../number-theory-2-multiplicative-functions))

# Overview

> **Three functions over set $S=\{1,\ldots,n\}$:**
> - $g(x)$ = number of elements in $S$ divisible by $x$ (the "multiples count").
> - $f(x)$ = number of elements in $S$ equal to $x$ exactly (the "exact count").
> - $h(x)$ = number of elements in $S$ coprime to $x$ (the "coprime count").
>
> **Key result:** if $g(x)$ can be evaluated in $O(1)$, then all values $f(x)$ and $h(x)$ for $1\leq x\leq n$ can be computed in $O(n\log\log n)$ time.

# 1 Computing $\mu$ via Eratosthenes Sieve

The Möbius function can be computed with a simple sieve without needing the linear sieve:

```cpp
mu[1] = 1;
for (int i = 1; i <= MAXN; ++i) {
    for (int j = i + i; j <= MAXN; j += i) {
        mu[j] -= mu[i];
    }
}
```

This works because the Möbius inversion identity $\sum_{d\mid n}\mu(d)=[n=1]$ directly gives the recurrence: $\mu(n)=-\sum_{d\mid n,d\lt n}\mu(d)$.

> **When to prefer Eratosthenes over linear sieve for μ:**
> The linear sieve requires the function being computed to be multiplicative. Eratosthenes-style sieving works for any function defined via divisor-sum recurrences, including cases that are not strictly multiplicative.

---

# 2 Core Framework: Conclusions 1 and 2

## Conclusion 1 (Multiple Form)

$$\boxed{f(x)=\sum_{i=1}^{\lfloor n/x\rfloor}g(i\cdot x)\cdot\mu(i)}$$

**Derivation:** the Möbius inversion multiple form. If $g(x)=\sum_{i=1}^{\lfloor n/x\rfloor}f(i\cdot x)$ (the multiples transform), then by Möbius inversion $f$ is recovered as above.

## Conclusion 2 (Coprime Count via Divisor Sum)

$$\boxed{h(n)=\sum_{d\mid n}g(d)\cdot\mu(d)}$$

**Intuition** (example with $n=6$, $S=\{1,\ldots,10\}$):

$h(6)$ = count of elements in $\{1,\ldots,10\}$ coprime to 6.
By inclusion-exclusion over prime factors of 6 ($p=2$ and $p=3$):
$$h(6)=g(1)-g(2)-g(3)+g(6)=10-5-3+1=3\qquad(\text{elements: }1,5,7)$$

The divisors of 6 are $1,2,3,6$ with $\mu$ values $1,-1,-1,1$ — exactly matching the inclusion-exclusion signs.

**Big picture:**
$$\underbrace{\text{exact count }f}_{\text{hard}}\xrightarrow{\text{Möbius transform}}\underbrace{\text{multiples count }g}_{\text{easy}}\xrightarrow{\text{inversion}}\underbrace{\text{exact answer}}_{\text{recover }f}$$

---

# 3 Worked Table: Computing $f(1) = \text{cnt}(1)$ with $N=10$

We want: how many times does 1 appear in $S=\{1,\ldots,10\}$? (Answer is obviously 1.)

Using Conclusion 1: $f(1)=\sum_{i=1}^{10}g(i)\cdot\mu(i)$ where $g(i)=\lfloor10/i\rfloor$.

| $i$ | $\mu(i)$ | $g(i)=\lfloor10/i\rfloor$ | $\mu(i)\cdot g(i)$ |
|----:|--------:|-------------------------:|------------------:|
| 1   | 1       | 10                       | 10                |
| 2   | −1      | 5                        | −5                |
| 3   | −1      | 3                        | −3                |
| 4   | 0       | 2                        | 0                 |
| 5   | −1      | 2                        | −2                |
| 6   | 1       | 1                        | 1                 |
| 7   | −1      | 1                        | −1                |
| 8   | 0       | 1                        | 0                 |
| 9   | 0       | 1                        | 0                 |
| 10  | 1       | 1                        | 1                 |

$$f(1)=10-5-3+0-2+1-1+0+0+1=1\quad\checkmark$$

---

# 4 GCD Table Intuition for $g(x)=\lfloor n/x\rfloor\lfloor m/x\rfloor$

**Question:** for $i\in[1,n]$, $j\in[1,m]$, let $g(x)$ = number of pairs with $x\mid\gcd(i,j)$. How many such pairs are there?

The pairs with $x\mid\gcd(i,j)$ are exactly those where $x\mid i$ and $x\mid j$. There are $\lfloor n/x\rfloor$ choices for $i$ and $\lfloor m/x\rfloor$ choices for $j$, so:
$$g(x)=\left\lfloor\frac{n}{x}\right\rfloor\cdot\left\lfloor\frac{m}{x}\right\rfloor$$

**GCD table for $i,j\in[1,10]$** (scan visually to verify $g(x)=\lfloor10/x\rfloor^2$):

|     | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|----:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---:|
| **1** | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| **2** | 1 | 2 | 1 | 2 | 1 | 2 | 1 | 2 | 1 | 2 |
| **3** | 1 | 1 | 3 | 1 | 1 | 3 | 1 | 1 | 3 | 1 |
| **4** | 1 | 2 | 1 | 4 | 1 | 2 | 1 | 4 | 1 | 2 |
| **5** | 1 | 1 | 1 | 1 | 5 | 1 | 1 | 1 | 1 | 5 |
| **6** | 1 | 2 | 3 | 2 | 1 | 6 | 1 | 2 | 3 | 2 |
| **7** | 1 | 1 | 1 | 1 | 1 | 1 | 7 | 1 | 1 | 1 |
| **8** | 1 | 2 | 1 | 4 | 1 | 2 | 1 | 8 | 1 | 2 |
| **9** | 1 | 1 | 3 | 1 | 1 | 3 | 1 | 1 | 9 | 1 |
| **10** | 1 | 2 | 1 | 2 | 5 | 2 | 1 | 2 | 1 | 10 |

---

# 5 Conclusion 2 via Eratosthenes

The formula $h(n)=\sum_{d\mid n}g(d)\mu(d)$ can also be computed sieve-style:

```cpp
mu[1] = 1;
for (int i = 1; i < MAXN; ++i)
    for (int j = i + i; j < MAXN; j += i)
        mu[j] -= mu[i];

// compute h[j] = sum_{d|j} g[d] * mu[d]
for (int i = 1; i <= n; ++i)
    for (int j = i; j <= n; j += i)
        h[j] += mu[i] * g[i];
```

**Special case** ($S=\{n!\}$, singleton):
- $g(x)=1$ for all $x$ (since $n!$ is divisible by every $x\leq n$).
- $h(x)=\sum_{d\mid x}\mu(d)=[x=1]$ — only 1 is coprime to $n!$, as expected.

---

# 6 Example: CF 803F — Coprime Subsequences

> Given array $a_1,\ldots,a_n$, count non-empty subsets whose GCD equals 1.

**Setup:**
- $f(x)$ = number of non-empty subsets with $\gcd=x$ exactly.
- $g(x)$ = number of non-empty subsets with $x\mid\gcd$ (GCD is a multiple of $x$) = $2^{\text{cnt}[x]}-1$, where $\text{cnt}[x]$ = count of $a_i$ divisible by $x$.

We want $f(1)$. By Conclusion 1:
$$f(1)=\sum_{d=1}^{\max}\mu(d)\,g(d)=\sum_{d=1}^{\max}\mu(d)\,(2^{\text{cnt}[d]}-1)$$

**Computing $\text{cnt}[x]$** (count of $a_i$ divisible by $x$):
1. Build frequency array $\text{freq}[v]$ = count of $v$ in $a[]$.
2. For each $x$, sum $\text{freq}[x]+\text{freq}[2x]+\text{freq}[3x]+\cdots$ — harmonic series, $O(M\log M)$.

**Two equivalent implementations:**

**Approach 1 — bottom-up exclusion** (equivalent to Möbius but computed top-down from multiples):
Start with $f[x]=2^{\text{cnt}[x]}-1$ for all $x$. Then for $x$ from $M$ down to 1, subtract $f[j]$ for each multiple $j=2x,3x,\ldots$ of $x$. At the end $f[x]$ = count of subsets with GCD exactly $x$.

**Approach 2 — direct Möbius:**
$$\text{Ans}=\sum_{d=1}^M\mu(d)\,(2^{\text{cnt}[d]}-1)$$

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int MOD = 1e9 + 7;

int add(int a, int b){ a += b; if(a >= MOD) a -= MOD; return a; }
int sub(int a, int b){ a -= b; if(a < 0) a += MOD; return a; }
int mul(ll a, ll b){ return int(a * b % MOD); }

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n; cin >> n;
    vector<int> a(n);
    int m = 0;
    for(int i = 0; i < n; i++){ cin >> a[i]; m = max(m, a[i]); }

    // precompute pow2[k] = 2^k % MOD
    vector<int> pow2(n+1, 1);
    for(int i = 1; i <= n; i++) pow2[i] = add(pow2[i-1], pow2[i-1]);

    // cnt[x] = number of a[i] divisible by x
    vector<int> cnt(m+1, 0);
    for(int v : a) cnt[v]++;
    for(int i = 1; i <= m; i++)
        for(int j = i*2; j <= m; j += i)
            cnt[i] += cnt[j];

    // Approach 1: bottom-up exclusion
    vector<int> f(m+1, 0);
    for(int i = m; i >= 1; i--){
        f[i] = sub(pow2[cnt[i]], 1);   // subsets with all elements divisible by i
        for(int j = i*2; j <= m; j += i)
            f[i] = sub(f[i], f[j]);     // subtract those with GCD = multiple of i
    }
    cout << f[1] << "\n";

    /* Approach 2: direct Möbius inversion
    vector<int> f(m+1, 0);
    for(int i = 1; i <= m; i++) f[i] = sub(pow2[cnt[i]], 1);
    int ans = 0;
    for(int i = 1; i <= m; i++){
        ans = (ans + (ll)mu[i] * f[i] % MOD + MOD) % MOD;
    }
    cout << ans << "\n";
    */
    return 0;
}
```
