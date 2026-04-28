---
title: "Number Theory #1.5: Divisibility Blocking (Floor-Division Decomposition)"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-1-5-divisibility-blocking"
description: "O(sqrt n) evaluation of floor-division sums by blocking; single-variable, two-variable, and multi-variable cases; ceiling-division variant; CSES 1082 example."
summary: "Divisibility blocking for O(sqrt n) floor-sum evaluation: lemma, single-variable loop, O(1) interval sum requirements, two-variable min-trick, multi-variable pseudocode, and ceiling-division blocking."
categories: [Number Theory]
tags: [math, number-theory, blocking, sqrt-decomposition, floor-sum]
math: true
toc: true
---

# Divisibility Blocking (Number-Theoretic Blocking)

## Problem Setting

Evaluate sums of the form:
$$\sum_{i=1}^{n}\underbrace{f(i)}_{O(1)}\cdot g\!\left(\left\lfloor\frac{n}{i}\right\rfloor\right)$$

If $f(i)$'s prefix sum is computable in $O(1)$, the whole sum can be evaluated in $O(\sqrt{n})$.

## Lemma 1

> For $n,i\in\mathbb{N}^+$, $\lfloor n/i\rfloor$ takes at most $2\sqrt{n}$ distinct values.

We enumerate $k=\lfloor n/i\rfloor$ and for each $k$ compute:
$$\sum_{k}\;g(k)\cdot\underbrace{\bigl(f(l)+\cdots+f(r)\bigr)}_{\text{need }O(1)\text{ interval sum}}$$

## Core Loop

The key observation: given left endpoint $l$, the right endpoint of the block where $\lfloor n/i\rfloor$ is constant equals:
$$r=\left\lfloor\frac{n}{\lfloor n/l\rfloor}\right\rfloor$$

```cpp
for (ll l = 1, r; l <= n; l = r + 1) {
    ll t = n / l;   // constant value of floor(n/i) in this block
    r = n / t;      // right endpoint of the block
    // process block [l, r] with quotient t
}
```

## O(1) Interval Sum Requirement

In each block $[l,r]$, we need $\sum_{i=l}^r f(i)$ in $O(1)$. If we compute $f(i)$ one by one, the loop runs $r-l+1$ times per block and the total reverts to $O(n)$.

Two correct approaches:
- **Closed-form formula** (e.g. $f(i)=1$, $f(i)=i$, $f(i)=i^2$, …)
- **Prefix-sum array** — only valid when $O(n)$ preprocessing is acceptable; it does **not** break the $O(\sqrt{n})$ query time but does require $O(n)$ memory and preprocessing.

> Storing a prefix-sum array of size $n$ is fine for most problems, but the preprocessing cost is $O(n)$, not $O(\sqrt{n})$.

## Example: CSES 1082 — Sum of All Divisors

$$\sum_{i=1}^n\sigma(i)=\sum_{i=1}^n\sum_{d\mid i}d=\sum_{d=1}^n d\cdot\left\lfloor\frac{n}{d}\right\rfloor$$

Here $f(d)=d$ and $g(\lfloor n/d\rfloor)=\lfloor n/d\rfloor$. The sum of $f$ over $[l,r]$ is an arithmetic series: $\sum_{d=l}^r d=\frac{(l+r)(r-l+1)}{2}$, computable in $O(1)$.

```cpp
#include <iostream>
using namespace std;
int main() {
    long long n; cin >> n;
    long long sum = 0, l, r;
    for (l = 1; l <= n; l = r + 1) {
        r = n / (n / l);
        long long k = n / l;                 // constant quotient in this block
        sum += k * (l + r) * (r - l + 1) / 2;  // closed-form interval sum
    }
    cout << sum;
}
```

---

# Two-Variable Blocking

$$\sum_{i=1}^{n}f(i)\cdot g\!\left(\left\lfloor\frac{n}{i}\right\rfloor\right)\cdot h\!\left(\left\lfloor\frac{m}{i}\right\rfloor\right)$$

$\lfloor n/i\rfloor$ has $O(\sqrt{n})$ distinct values; $\lfloor m/i\rfloor$ has $O(\sqrt{m})$ distinct values. We need a block where **both** are simultaneously constant.

**Algorithm:**
1. Start with $l=1$.
2. Compute $q_n=\lfloor n/l\rfloor$, $q_m=\lfloor m/l\rfloor$.
3. Compute right endpoints $r_1=\lfloor n/q_n\rfloor$, $r_2=\lfloor m/q_m\rfloor$.
4. Take $r=\min(r_1,r_2)$: within $[l,r]$, both quotients are constant.
5. Add block contribution: $\text{ans}\mathrel{+}=\bigl(\sum_{i=l}^r f(i)\bigr)\cdot g(q_n)\cdot h(q_m)$.
6. Set $l=r+1$.

**Termination:** stop when $l>\min(n,m)$ (beyond that, at least one quotient is 0).

**Complexity:** $O(\sqrt{n}+\sqrt{m})$ blocks total (each step advances to the next distinct value of at least one variable).

```cpp
l = 1;
while (l <= min(n, m)) {
    ll qn = n / l, qm = m / l;
    ll r = min(n / qn, m / qm);
    ans += (prefixF[r] - prefixF[l-1]) * g(qn) * h(qm);
    l = r + 1;
}
```

---

# Multi-Variable Blocking

$$\sum_{i=1}^{N}F\!\left(i,\;\left\lfloor\frac{n_1}{i}\right\rfloor,\;\left\lfloor\frac{n_2}{i}\right\rfloor,\;\ldots,\;\left\lfloor\frac{n_k}{i}\right\rfloor\right)$$

Each floor function is piecewise constant with $O(\sqrt{n_j})$ breakpoints. The joint block where all $k$ quotients are simultaneously constant is found by taking $r=\min_j\lfloor n_j/\lfloor n_j/l\rfloor\rfloor$.

```cpp
l = 1;
while (l <= min(n1, n2, ..., nk)) {
    for (j = 1..k) {
        t[j] = n[j] / l;          // current quotient for variable j
        r[j] = n[j] / t[j];       // right endpoint for variable j alone
    }
    r = min(r[1], r[2], ..., r[k]);
    ans += block_contribution([l, r], t[1], t[2], ..., t[k]);
    l = r + 1;
}
```

**Complexity:** each step advances past the closest breakpoint of any variable; total steps $\leq\sum_{j=1}^k O(\sqrt{n_j})$. With $O(1)$ block contribution: total $O\!\bigl(\sqrt{n_1}+\cdots+\sqrt{n_k}\bigr)$.

---

# Ceiling-Division Blocking

For $\lceil n/i\rceil$, the block right endpoint differs slightly from the floor case.

The block where $\lceil n/i\rceil=\lceil n/j\rceil$ for all $j\in[i,n]$ has its right endpoint at:
$$r=\left\lfloor\frac{n-1}{\lfloor(n-1)/i\rfloor}\right\rfloor$$

That is, substitute $n\to n-1$ in the floor-division right-endpoint formula.
