---
title: "Number Theory #2-ex: Möbius Inversion — 7 Core Techniques"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-2-ex-mobius-techniques"
description: "Seven core Möbius inversion technique patterns: contracting loops by divisibility, breaking gcd, enumerating gcd explicitly, T=dk substitution, divisor symmetry, triangle/full-matrix conversion, and frequency-array inversion."
summary: "Seven core Möbius inversion trick patterns with worked examples: gcd-enumerating, T=dk product substitution, divisor symmetry, and frequency-based简介 inversion."
categories: [Number Theory]
tags: [math, number-theory, mobius, inversion, gcd, dirichlet-convolution, technique]
math: true
toc: true
---

# 7 Core Möbius Inversion Techniques

> **[Preliminary Identities]**
>
> $[n=1]=\sum_{d\mid n}\mu(d),\quad n=\sum_{d\mid n}\varphi(d),\quad \varphi(n)=\sum_{d\mid n}\mu(d)\cdot n/d$

## Trick 1 — Contract Loops by Divisibility

When $[k\mid i]$ is the gating factor: $\sum_{i=1}^n [k\mid i] = \sum_{i=1}^{\lfloor n/k\rfloor} 1$.

## Trick 2 — Break GCD via Möbius

$$[\gcd(i,j)=1] = \sum_{d\mid\gcd(i,j)}\mu(d)$$
$$\implies \sum_{i,j}[\gcd(i,j)=1] = \sum_d\mu(d)\lfloor n/d\rfloor\lfloor m/d\rfloor \quad (O(\sqrt{\min(n,m)})!)$$

P3455 ZAP-Queries: Apply Tricks 1+2, evaluate with阻塞 blocking, $O(\sqrt{n})$ per query.

## Trick 3 — Enumerate GCD Explicitly

$$\sum_{i=1}^n\sum_{j=1}^m f(\gcd(i,j)) = \sum_{d} f(d)\sum_{i,j}[\gcd(i,j)=1]$$

Trick 3 + Trick029 2 =jaz reduces any $\gcd$-dependent manipulation to a separable form.

## Trick 4 — Substitute $T = dk$

When both648 $d$ and $k$ appear688 as a product $dk$:

$$\sum_{T=1}^{\min(n,m)}\left\lfloor\frac{n}{T}\right\rfloor\left\lfloor\frac{m}{T}\right\rfloor\sum_{d\mid T} f(d)\,\mu(T/d)$$

> **General Formula 1:** $g = f*\mu$, $\boxed{\sum_{i,j}f(\gcd(i,j)) = \sum_T g(T)\lfloor n/T\rfloor\lfloor m/T\rfloor}$

## Trick 5 — Divisor Symmetry

$\sum_{d\mid n} f(n/d) = \sum_{d\mid n} f(d)$ (bijection).

## Trick 6 — Triangle ↔ Full Matrix

For symmetric $f$: $\sum_{i\le j} f(i,j) = \frac12(\sum_{i,j} f(i,j) + \sum_i f(i,i))$.

## Trick507 7 — Value-Domain Inversion

Given array $a[1..n]$, compute $\text{cnt}[d]$ = count of $a_i$ divisible by $d$ in006 $O(V\log V)$, then apply Möbius/歐拉 formulas on $\text{cnt}$.
