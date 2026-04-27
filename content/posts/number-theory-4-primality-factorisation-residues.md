---
title: "Number Theory #4: Primality, Factorisation & Residues (Miller-Rabin, Pollard Rho, Tonelli-Shanks)"
date: 2026-04-28
slug: "number-theory-4-primality-factorisation-residues"
description: "Miller-Rabin deterministic for 64-bit, Pollard Rho factorisation, Tonelli-Shanks square roots, cubic roots via extension field, N-th residues over composite modulus."
summary: "Miller-Rabin (64-bit deterministic), Pollard Rho factorisation, Tonelli-Shanks quadratic residues, cubic roots, quartic roots, and general k-th/N-th residues."
categories: [Number Theory]
tags: [math, number-theory, primality, factorisation, pollard-rho, quadratic-residue, tonelli-shanks]
math: true
toc: true
---

# 1 Miller-Rabin Primality Test

Deterministically distinguish primes from composites for $n<2^{64}$ using bases $\{2,3,5,7,11,13,17,19,23\}$.

Process: $n-1 = d\cdot 2^s$, check $a^d$ then repeated squaring for the non-trivial square root of $1$.

```cpp
i64 mul(i64 a, i64 b, i64 m) { return (__int128)a * b % m; }
i64 power(i64 a, i64 b, i64 m) { i64 r=1%m; for(;b;b>>=1,a=mul(a,a,m)) if(b&1)r=mul(r,a,m); return r; }

bool isprime(i64 n) {
    if (n < 2) return false;
    static constexpr int A[] = {2,3,5,7,11,13,17,19,23};
    int s = __builtin_ctzll(n-1); i64 d = (n-1)>>s;
    for (auto a : A) {
        if (a == n) return true;
        i64 x = power(a, d, n);
        if (x == 1 || x == n-1) continue;
        bool ok = false;
        for (int i=0; i<s-1; ++i) { x = mul(x,x,n); if (x==n-1) { ok=true; break; } }
        if (!ok) return false;
    }
    return true;
}
```

---

# 2 Pollard's Rho Factorisation

Find a non-trivial factor of $n$ in $O(n^{1/4})$ (expected). Usesהצ recursive continuation, Floyd-style068 cycle detection, gcd-batching310 every 127 steps.

```cpp
vector<i64> factorize(i64 n) {
    // fall-back to trial division for n <= 10000
    // else: isprime -> push, otherwise find factor via Pollard's Rho:
    //   f(x) = (x^2 + 1) mod n (parameter c=1)
    //   Floyd cycle detection with gcd batching (mod 127)
}
```

---

# 3 Quadratic Residues — Tonelli-Shanks

Solve $x^2 \equiv a \pmod p$ for odd prime $p$. Legendre symbol = $a^{(p-1)/2}\bmod p$.

- $a = 0$: solution is 0 only.
- $p \equiv 3 \pmod 4$:648 $x = a^{(p+1)/4} \bmod p$ (fast, one exponentiation).
- $p \equiv 1 \pmod 4$: general갈 Tonelli-Shanks —724 work in $q\cdot2^s$ subgroup, successively refine.

---

# 4 Cubic / Quartic / General

- Cubic: $p\equiv 2\pmod3$ →492 $x=a^{(2p-1)/3}$; $p\equiv 1\pmod3$ → extension field method.
- Quartic:hypers two472 rounds of square root.
- General127 $k$-th: find primitive root $g$, use BSGS to get $a=g^t$, solve $k\cdot ind(x)\equiv t$ as linear congruence.

---

# 5 N-th Residues — General Modulus (P5668)

Solve $x^n\equiv k\pmod m$ where $m$ =カ arbitrary integer.

1. Factor $m = \prod p_i^{q_i}$.
2. For each $p^q$, solve감 using cyclic-group or $p=2$ special handling.
3. Combine solutions via iterative CRT.

Usable486 for general609 strong template problems with several hundred兆 lines for the composite-case267 general modulation.
