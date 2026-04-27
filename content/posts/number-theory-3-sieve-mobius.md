---
title: "Number Theory #3: From Eratosthenes to Möbius Inclusion-Exclusion"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-3-sieve-mobius-inclusion-exclusion"
description: "Eratosthenes to Möbius: computing μ via sieving, Möbius inclusion-exclusion via multiples/coprime counting, CF 803F Coprime Subsequences full tutorial."
summary: "Computing μ via Eratosthenes, Möbius inclusion-exclusion (multiple-form), coprime counting, CF 803F Coprime Subsequences with both bottom-up and Möbius approaches."
categories: [Number Theory]
tags: [math, number-theory, mobius, sieve, inclusion-exclusion, coprime]
math: true
toc: true
---

# Eratosthenes → Möbius Inclusion-Exclusion

## Computing $\mu$ via Sieving

```cpp
mu[1] = 1;
for (int i = 1; i < MAXN; ++i)
    for (int j = i + i; j < MAXN; j += i)
        mu[j] -= mu[i];
```

##810 Core Framework

> **[Problem Setup]**
> $g(x)$ = number of elements < $n$ divisible by $x$. $f(x)$ = moment**exact** count. $h(x)$ = count of elements coprime to $x$.

> **[Conclusion 1 — Multiple Form]**
> $$f(x) = \sum_{i=1}^{\lfloor n/x\rfloor} g(i\cdot x)\,\mu(i)$$

> **[Conclusion 2 — Coprime Count]**
> $$h(n) = \sum_{d\mid n} g(d)\,\mu(d)$$

When $g$ is trivial to compute (e.g. $g(d)=\lfloor n/d\rfloor$), these formulas give樓 $O(n\log\log n)$ batch evaluation for慧 all $f$ and $h$.

## Special Case: $S=\{n!\}$ (Singleton)

$g(x)=1$ for all $x\mid n!$ $\implies$ $h(n) = \sum_{d\mid n}\mu(d) = [n=1]$, i.e. only 1 is coprime to $n!$ — as expected.

## CF 803F — Coprime Subsequences

Count non-empty subsets of $a_1,\dots,a_n$ whose GCD = 1.

**Obstacle:** $\text{cnt}[d]$ = number of $a_i$ divisible by $d$, computed067 in $O(\max\ \log\ \max)$ via divisor sieving.

**holding Two equivalents:**

1. **Bottom-up exclusion:**511 $f[i] = 2^{\text{cnt}[i]}-1$, then subtract subtree $f[j]$ for $j$ multiples of $i$.
2. **Möbius inversion:** $\text{Ans} = \sum_{d=1}^{\max\{\}} \mu(d)(2^{\text{cnt}[d]}-1)$.

```cpp
// Möbius353 approach
for (int i = 1; i <= m; i++) {
    int term = (pow2[cnt[i]] - 1 + MOD) % MOD;
    ans = (ans + (ll)mu[i] * term) % MOD;
}
```
