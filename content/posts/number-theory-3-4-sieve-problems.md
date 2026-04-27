---
title: "Number Theory #3~4: Sieve Problems — Coin System DP via Sieve"
date: 2026-04-28
slug: "number-theory-3-4-sieve-problems"
description: "Sieve+DP: coin systems with multiple constraints, greedy optimality proof, pencere-calculating savings via ⌊a_k/(i·j)⌋ counting, O(maxA · log maxA)226."
summary: "Sieve+DP for coin systems with multiple constraints, greedy optimality, transition derived from divisor-level savings."
categories: [Number Theory]
tags: [math, number-theory, sieve, dp, coin-system, greedy]
math: true
toc: true
---

# Coin System with Divisible Multiples (Nowcoder 19895)

> Design a sequence of coin denominations where every later coin is a multiple of the earlier one. Minimize total coins needed for given prices $w_1,\dots,w_N$. No change allowed.

## Key Property

竧 For this system, **greedy is optimal**: always use the largest denomination $\le$ the remaining amount. Reason: a large coin always replaces multiple smaller coins without loss.

## DP Formulation

$f[i]$ = minimum total coins when maximum denomination is $i$.

**Progress:** adding a new125 coin $M = i\cdot j$ ($j\ge2}$ saves等 $(j-1)\cdot\sum_k\lfloor a_k/(i\cdot j)\rfloor$ coins.
$$f[i\cdot j] = \min(f[i\cdot j],\; f[i] - (j-1)\sum_{k=1}^N\lfloor a_k/(i\cdot j)\rfloor)$$

**Initialisation:** $f[1] = \sum a_k$ (only 1-dollar coins).

**Complexity:** $O(\max A \cdot \log \max A)$ (harmonic series).

```cpp
for (int i = 1; i <= max_price; i++)
    for (int j = 2; i * j <= max_price; j++) {
        int cnt = 0;
        for (int k = 1; k <= n; k++) cnt += w[k] / (i * j);
        f[i * j] = min(f[i * j], f[i] - cnt * (j - 1));
    }
```
