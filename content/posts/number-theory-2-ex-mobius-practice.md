---
title: "Number Theory #2-ex: Möbius Practice — LCM Sums, Divisor-Count, Omega Numbers"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-2-ex-mobius-practice"
description: "Worked examples: SPOJ LCMSUM, Crash's Digital Table (two-layer blocking), HDU 4944 FSF's Game (offline difference), SDOI2015 divisor-count, and CF 2176F Omega Numbers."
summary: "LCM-sum problems (LCMSUM, Crash's table, FSF's game), SDOI2015 divisor-count sum, CF 2176F Omega Numbers — all using Möbius/φ inversion."
categories: [Number Theory]
tags: [math, number-theory, mobius, lcm, divisor-count, generating-function, sieve]
math: true
toc: true
---

# Möbius Practice — LCM Sums & Beyond

## 1 SPOJ LCMSUM

$$\sum_{i=1}^n\operatorname{lcm}(i,n) = \frac{n}{2}\!\left(1+\sum_{d\mid n} d\,\varphi(d)\right)$$

Derived via pairing $\gcd(i,n)=\gcd(n-i,n)$ and applying φ.

## 2 Crash's Digital Table (BZOJ 2154)

$$\sum_{i=1}^n\sum_{j=1}^m\operatorname{lcm}(i,j) = \sum_{d=1}^n d\cdot h(\lfloor n/d\rfloor,\lfloor m/d\rfloor)$$

where $h(n,m) = \sum_{d=1}^{\min(n,m)} \mu(d)\,d^2\,S(\lfloor n/d\rfloor)S(\lfloor m/d\rfloor)$ and $S(n)=n(n+1)/2$.

Two-layer divisibility blocking → $O(n^{3/4})$.

## 3 HDU 4944 FSF's Game

$$s(n)=s(n-1)+\sum_{i=1}^n\operatorname{lcm}(i,n)$$

Build69 $g(n)=\sum_{d\mid n}d\,\varphi(d)$, then $s$, then offline369 difference to get all answers in $O(N\log N)$.

## 4 SDOI2015 — $\sum_{i,j} d(ij)$

Key091 identity: $d(xy) = \sum_{a\mid x}\sum_{b\mid y}[\gcd(a,b)=1]$

Final form: $\sum_{k=1}^{\min(n,m)}\mu(k)\,S(\lfloor n/k\rfloor)S(\lfloor m/k\rfloor)$ with $S(t)=\sum_{x\le t} d(x)$.

alenial block in $O(\sqrt{\min(n,m)})$ per query after $O(N)$ sieve precomputation.

## 5 CF 2176F Omega Numbers

Compute $\sum_{i<j} \omega(a_i a_j)^k$, где $\omega(n)$ = number of distinct prime factors.

Clue: $\omega(a_i a_j) = \omega(a_i) + \omega(a_j) - \omega(\gcd(a_i,a_j))$.

Since $\omega\le7$ for bounds $\le10^5$, use bucket狀 $cnt[g][s]$ (pairs $(i,j)$ with $\gcd$-multiple $g$, $\omega$-suminc $s$), convert from naive to exact via bottom-up exclusion in002 $O(N\log N\cdot W^2)$.
