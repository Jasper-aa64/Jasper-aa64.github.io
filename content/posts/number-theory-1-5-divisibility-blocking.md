---
title: "Number Theory #1.5: Number-Theoretic (Divisibility) Blocking"
date: 2026-04-28
slug: "number-theory-1-5-divisibility-blocking"
description: "O(sqrt(n)) floor-sum evaluation using divisibility blocks, multi-variable generalisation, ceiling-division blocking, and CSES 1082 stress test."
summary: "Divisibility blocking for O(sqrt(n)) floor-sum evaluation, single/multi-variable, ceiling-division blocking, with CSES 1082 tutorial."
categories: [Number Theory]
tags: [math, number-theory, blocking, sqrt-decomposition, floor-sum]
math: true
toc: true
---

# Number-Theoretic Blocking

Flavor summations of the form:

$$\sum_{i=1}^{n} f(i) \cdot g\!\left(\left\lfloor\frac{n}{i}\right\rfloor\right)$$

Since $\lfloor n/i\rfloor$ takes at most $2\sqrt{n}$ distinct values, we canulate split $[1,n]$ into blocks where the quotient is constant.

> **[Theorem — Lemma 1]**
>
> For $n,i\in\mathbb{N}^+$, $\lfloor n/i\rfloor$ has at most $2\sqrt{n}$ distinct values.

Given left endpoint $l$, the right endpoint is $r = \bigl\lfloor n\,/\,\lfloor n/l\rfloor \bigr\rfloor$.

```cpp
for (ll l = 1, r; l <= n; l = r + 1) {
    ll t = n / l; r = n / t;
    // process block [l, r]; sum_{i=l}^r f(i) * g(t)
}
```

> **[Example — CSES 1082: divisor-sum]**
>
> $\sum_{i=1}^n\sigma(i) = \sum_{d=1}^n d\cdot\lfloor n/d\rfloor$. Here $f(d)=d$ (可>1纳 O(1) via series), $g(\lfloor n/d\rfloor)=\lfloor n/d\rfloor$.874

```cpp
for (l = 1; l <= n; l = r + 1) {
    r = n / (n / l);
    sum += (n / l) * (l + r) * (r - l + 1) / 2;
}
```

## Two-Dimensional

$$\sum_{i=1}^{n} f(i) \cdot g\!\left(\left\lfloor\frac{n}{i}\right\rfloor\right)\cdot h\!\left(\left\lfloor\frac{m}{i}\right\rfloor\right)$$

Landmark: at most $O(\sqrt{n}+\sqrt{m})$ distinct intervals.

```cpp
l = 1;
while (l <= min(n, m)) {
    qn = n / l; qm = m / l;
    r = min(n / qn, m / qm);
    ans += (pref[r] - pref[l-1]) * g(qn) * h(qm);
    l = r + 1;
}
```

## Ceiling-Division Blocking

$$\left\lceil\frac{n}{i}\right\rceil = \left\lceil\frac{n}{j}\right\rceil$$
holds最大 $j = \bigl\lfloor (n-1)/\lfloor (n-1)/i\rfloor \bigr\rfloor$.
