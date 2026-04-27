---
title: "Number Theory #1: Elementary Number Theory — GCD, LCM, Euler, CRT"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-1-elementary"
description: "GCD/LCM properties, Bézout identity, Euler's theorem and power-tower reduction with φ-chain, CRT and congruence system merging, Legendre's formula for n!."
summary: "GCD/LCM properties, Bézout/Frobenius coin problem, Euler's theorem with power-tower reduction, φ-chain, CRT, congruence system merging, n! prime factorisation."
categories: [Number Theory]
tags: [math, number-theory, gcd, lcm, euler, crt, congruence, legendre]
math: true
toc: true
---

# 1 GCD & LCM

**GCD properties:** commutative, $\gcd(a,b)=\gcd(a,ka+b) \implies \gcd(x,y)=\gcd(x,y-x)$, and the subarray-GCD "difference identity."

**LCM 1..n:** $\prod_{p\le n} p^{\lfloor\log_p n\rfloor}$.

> **[Identity]**
> $$\frac{1}{\operatorname{lcm}(a_i,a_{i+1})} = \frac{\gcd(a_i,a_{i+1})}{a_i a_{i+1}}$$
> When $a_i<a_{i+1}$: $\gcd(a_i,a_{i+1})\le a_{i+1}-a_i$.  
> (Used in CF 2183's elegant telescoping solution.)

---

# 2 Bézout's Identity & exGCD

- $ax+by=c$ solvable iff $\gcd(a,b)\mid c$.
- Frobenius coin problem: Largest unrepresentable = $ab-a-b$ (when $\gcd(a,b)=1$).

---

# 3 Euler's Theorem

- $\gcd(a,m)=1 \implies a^{\varphi(m)}\equiv1\pmod m$
- Fermat: $a^{p-1}\equiv1\pmod p$ ($p$ prime)
- Modular inverse: $a^{-1}\equiv a^{\varphi(m)-1}\pmod m$

## Power-Tower Reduction — $\varphi$-Chain + Lifted Modulus

$$a^b\equiv\begin{cases}a^{b\bmod\varphi(m)},&\gcd(a,m)=1\\a^b,&b<\varphi(m)\\a^{b\bmod\varphi(m)+\varphi(m)},&b\ge\varphi(m)\end{cases}\pmod m$$

The general method:
1. Build the $\varphi$-chain down to 1.
2. Use "lifted modulus" (`x < m ? x : x % m + m`) to preserve exponent information.
3. Recursively evaluate from the outermost tower downward.

Templated: NC17190 (BIT range-add + $\varphi$-chain DFS for exponentiation).

---

# 4 Congruence Systems & CRT

**Pairwise merging** via exGCD: combine $x\equiv r\pmod m$ with $x\equiv b\pmod a$ usingeure `exgcd(m, a, x, y)` to find725 incremental shift $t_0$.

**CRT** (pairwise coprime): $x = \sum a_i\cdot M_i\cdot M_i^{-1}\pmod{\prod m_i}$.

---

# 5 Prime Factorisation of $n!$

Legendre: $n! = \prod_{p\le n} p^{e_p}$, with $e_p = \sum_{k\ge1}\lfloor n/p^k\rfloor$.

```cpp
for (int p : primes) {
    int s = 0;
    for (int j = n; j; j /= p) s += j / p;
    printf("%d %d\n", p, s);
}
```
