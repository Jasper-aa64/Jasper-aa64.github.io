---
title: "Combinatorics #2-ex1: Difference (Correlation) Convolution"
date: 2026-04-25
slug: "combinatorics-2-ex1-difference-convolution"
description: "Cross-correlation via ordinary convolution: reverse-A and reverse-B extraction methods, derivation, and Ring Trick II (cyclic shift score maximisation via difference convolution)."
summary: "Cross-correlation via ordinary convolution: reverse-A and reverse-B extraction methods, derivation, and Ring Trick II (cyclic shift score maximisation via difference convolution)."
categories: [Combinatorics]
tags: [math, combinatorics, fft, ntt, convolution, correlation, polynomial]
math: true
toc: true
---

# Difference Convolution

> **[Technique — Difference Convolution: Result Extraction]**
>
> The **difference convolution** (cross-correlation) of two arrays $A$ and $B$ is:
>
> $$c_k=\sum_{i=k}^{R}a_i\,b_{i-k}\quad(k=0\ldots R)$$
>
> Equivalently: $c_k=\sum_{j=0}^{R-k}a_{k+j}\,b_j$, where $R$ is the largest index used.
>
> FFT/NTT computes $c_k=\sum_{i+j=k}a_i b_j$ (index sum). The trick is to **reverse one array** to convert the index-difference structure into index-sum structure.

## Two Extraction Methods

### Method 1: Reverse $A$

- Form $A^{\text{rev}}_t=a_{R-t}$, compute $D=A^{\text{rev}}*B$ (ordinary convolution, length $2R+1$).
- Extract: $\boxed{c_k=D_{R-k}}\quad(k=0\ldots R)$

### Method 2: Reverse $B$

- Form $B^{\text{rev}}_t=b_{R-t}$, compute $D=A*B^{\text{rev}}$.
- Extract: $\boxed{c_k=D_{R+k}}\quad(k=0\ldots R)$

Memory aid:

| | Convolution | Read position |
|---|---|---|
| Reverse $A$ | $A^{\text{rev}}*B$ | Left of centre: $D_{R-k}$ |
| Reverse $B$ | $A*B^{\text{rev}}$ | Right of centre: $D_{R+k}$ |

⚠️ The convolution length must be $\ge2R+1$ (pad to the next power of two for NTT). Only read the $k=0\ldots R$ slice.

## Derivation

**Reverse A:** $D=A^{\text{rev}}*B$ gives

$$D_s=\sum_t a_{R-t}\,b_{s-t}=\sum_i a_i\,b_{s-R+i}$$

Setting $s=R-k$:

$$D_{R-k}=\sum_{i\ge k}a_i\,b_{i-k}=c_k\quad\checkmark$$

**Reverse B:** Setting $s=R+k$ gives $D_{R+k}=c_k$.

---

# 1 Example — Ring Trick II

**Problem K, Ring Trick II** — regional problem

## 1.1 Problem Statement

- Given a length-$n$ sequence $a_1,\dots,a_n$ with $a_i\in[0,m)$.
- Choose any integer $k$ and apply a Caesar shift: $a_i\leftarrow(a_i+k)\bmod m$.
- For non-negative integer $x$, define its **hole count** $H(x)$ as the sum of holes in its decimal digits:
  - Digits 0, 4, 6, 9 each contribute 1 hole
  - Digit 8 contributes 2 holes
  - All other digits contribute 0
  
  Example: $H(8504)=4$; the sequence $[8,8,10,0]$ has hole sum $2+2+1+1=6$.

- **Goal:** choose $k$ to maximise $S(k)=\sum_{i=1}^n H\bigl((a_i+k)\bmod m\bigr)$. Output $\max_k S(k)$.

Constraints: $1\le n,m\le2\times10^5$.

## 1.2 Model

Define:

$$f[x]=|\{i:a_i=x\}|\quad\text{(frequency)},\qquad h[x]=H(x)\quad\text{(hole count)}$$

for $x=0,\dots,m-1$. Then:

$$S(k)=\sum_{x=0}^{m-1}f[x]\;h[(x+k)\bmod m]$$

This is a **cyclic cross-correlation**: the value at shift $k$ is the dot product of $f$ with a cyclically shifted version of $h$.

## 1.3 Implementation

Key observations:
- **Reverse** $f$ to get $A$: the cyclic cross-correlation becomes a convolution.
- **Double** $h$ to length $2m$: the linear convolution naturally covers the modular wraparound (every cyclic shift appears in the linear result).
- Extract the length-$m$ segment from position $m-1$ leftwards.

With $R=m-1$, the reverse-A formula gives $c_k=D_{m-1-k}$:

```cpp
vector<int> A(m);
for (int i = 0; i < m; i++) A[i] = freq[i];

vector<int> B(2 * m);
for (int i = 0; i < 2 * m; i++) B[i] = h[i % m];

reverse(A.begin(), A.end());
vector<int> C = multiply(A, B);   // ordinary NTT convolution

ll ans = 0;
for (int k = 0; k < m; k++) ans = max<ll>(ans, C[m - 1 - k]);
cout << ans << "\n";
```

**Why doubling $h$ works:** After reversing $A$, the ordinary linear convolution at position $R-k=m-1-k$ captures $\sum_x f[x]\cdot h[(x+k)\bmod m]$ exactly when $h$ has been extended to cover the wraparound. Repeating $h$ once is sufficient since the maximum index accessed is $(m-1)+(m-1)=2m-2$.
