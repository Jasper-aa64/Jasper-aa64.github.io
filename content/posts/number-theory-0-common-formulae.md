---
title: "Number Theory #0: Common Formulae — Legendre's Formula & Divisor Convolutions"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-0-common-formulae"
description: "Legendre's formula for prime exponents in n!, divisor/multiple convolution templates, and offline difference for batch computation of H(n)=Σf(d)g(⌊n/d⌋)."
summary: "Legendre's formula, divisor and multiple convolutions in O(n log n), offline-difference batch processing for H(n)=Σf(d)g(⌊n/d⌋)."
categories: [Number Theory]
tags: [math, number-theory, convolution, divisor, legendre, offline-difference, sieve]
math: true
toc: true
---

# 1 Legendre's Formula — Prime Exponent in $n!$

For a positive integer $n$ and prime $p$, the exponent $\nu_p(n!)$ of $p$ in $n!$ is:

$$\nu_p(n!) = \sum_{i=1}^{\infty} \left\lfloor \frac{n}{p^i} \right\rfloor = \frac{n - S_p(n)}{p - 1}$$

where $S_p(n)$ is the sum of the digits of $n$ in base $p$.

```cpp
int multiplicity_factorial(int n, int p) {
    int count = 0;
    do { n /= p; count += n; } while (n);
    return count;
}
```

---

# 2 Divisor Convolution

> **[Technique — Divisor Convolution]**
>
> Given arrays $f$ and $g$, compute $h$ in $O(n\log n)$:
>
> $$h(n) = \sum_{d\mid n} f(d)\cdot g(n/d) \quad\text{or}\quad h(d) = \sum_{d\mid d'} f(d'/d)\cdot g(d')$$

```cpp
// divisor form (enumeration of factors)
for (int d = 1; d <= n; d++)
    for (int j = 1; j <= n/d; j++)
        h[d*j] += (ll)f[d] * g[j] % M, h[d*j] %= M;

// divisor form — multiply-by-enumerator
for (int d = 1; d <= N; ++d)
    for (int m = d; m <= N; m += d)
        h[m] += (i128)f[d] * g[m/d] % M, h[m] %= M;

// multiple form
for (int d = 1; d <= Amax; d++)
    for (int j = d; j <= Amax; j += d)
        h[d] += (ll)f[j/d] * g[j] % M, h[d] %= M;
```

## 2.1 Offline Difference — Batch $H(1..N)$

> **[Technique — Batch $H(n)=\sum_{d=1}^n f(d)\,g(\lfloor n/d\rfloor)$]**
>
>揃 Single-point:分 block in $O(\sqrt{n})$.
>
> **Batch** $O(N\log N)$: for each $d$ and $k$, on $n\in[dk,d(k+1)-1]$ the quotient $\lfloor n/d\rfloor = k$ is constant.
>
> ```cpp
> diff[d*k]       += f(d)*g(k)
> diff[d*(k+1)]   -= f(d)*g(k)   // if d*(k+1) ≤ N
> ```
>
> Then prefix-sum $H[n] = \sum \text{diff}[..n]$.
