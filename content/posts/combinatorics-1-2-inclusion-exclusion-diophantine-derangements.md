---
title: "Combinatorics #1.2: Inclusion-Exclusion, Bounded Diophantine Equations, and Derangements"
date: 2026-04-20
slug: "combinatorics-1-2-inclusion-exclusion-diophantine-derangements"
description: "A compact note on inclusion-exclusion, bounded integer solutions, equal-cap upper bounds, and classical derangement formulas."
summary: "A compact note on inclusion-exclusion, bounded integer solutions, equal-cap upper bounds, and classical derangement formulas."
categories: [Combinatorics]
tags: [math, combinatorics, inclusion-exclusion, derangements, stars-and-bars, counting]
math: true
toc: true
---

This note collects a few standard counting templates that repeatedly appear in contest problems:

- inclusion-exclusion in set form
- onto-function and adjacency-avoidance counting
- bounded linear Diophantine equations
- derangements and fixed-point counting

# 1 Inclusion-Exclusion Basics

## Two sets

Let $S$ be a finite set and let $A, B \subseteq S$. Then

$$
\left|S \setminus (A \cup B)\right|
= |S| - |A| - |B| + |A \cap B|
$$

Equivalently,

$$
|A \cup B| = |A| + |B| - |A \cap B|
$$

## Three sets

For three subsets $A, B, C \subseteq S$,

$$
\left|S \setminus (A \cup B \cup C)\right|
= |S| - |A| - |B| - |C|
+ |A \cap B| + |A \cap C| + |B \cap C|
- |A \cap B \cap C|
$$

## General form

For subsets $A_1,\dots,A_n \subseteq S$,

$$
\left|S \setminus \bigcup_{i=1}^{n} A_i\right|
=
\sum_{T \subseteq [n]} (-1)^{|T|}
\left|\bigcap_{i \in T} A_i\right|
$$

where $[n] = \{1,2,\dots,n\}$, and the empty-intersection term is interpreted as $|S|$.

This is often the cleanest way to count objects with a list of forbidden properties.

# 2 Classic Inclusion-Exclusion Examples

## Euler's totient formula

Let

$$
n = p_1^{\alpha_1} p_2^{\alpha_2}\cdots p_k^{\alpha_k}
$$

be the prime factorization of $n$. Then

$$
\varphi(n)
=
n \prod_{i=1}^{k}\left(1 - \frac{1}{p_i}\right)
$$

Reason:

- let $S = \{1,2,\dots,n\}$
- let $A_i$ be the set of multiples of $p_i$ inside $S$
- then $\varphi(n)$ counts elements of $S$ outside $\bigcup A_i$

For any index set $T$,

$$
\left|\bigcap_{i \in T} A_i\right|
=
\frac{n}{\prod_{i \in T} p_i}
$$

because every $p_i$ divides $n$. Inclusion-exclusion then expands exactly into the product formula.

## Surjections: every person gets at least one item

Suppose $m$ labeled objects are distributed to $n$ labeled people, and every person must receive at least one object.

Let $A_i$ be the event that person $i$ receives nothing. The total number of unrestricted assignments is $n^m$, and if a fixed set of $t$ people are empty-handed, then each object has only $n-t$ choices. Therefore

$$
\#\text{onto assignments}
=
\sum_{t=0}^{n} (-1)^t \binom{n}{t}(n-t)^m
$$

This is also

$$
n!\,S_2(m,n)
$$

where $S_2(m,n)$ is the Stirling number of the second kind.

## No paired elements are adjacent

Given $2n$ distinct elements

$$
a_1,\dots,a_n,\quad b_1,\dots,b_n
$$

count permutations in which no pair $(a_i,b_i)$ is adjacent.

Let $A_i$ be the event that $a_i$ and $b_i$ are adjacent. If a fixed set of $k$ pairs are forced to be adjacent:

- each pair becomes one block
- each block has $2$ internal orders
- total number of objects becomes $2n-k$

So

$$
\left|A_{i_1}\cap\cdots\cap A_{i_k}\right|
=
2^k (2n-k)!
$$

and the final answer is

$$
\boxed{
\sum_{k=0}^{n} (-1)^k \binom{n}{k} 2^k (2n-k)!
}
$$

# 3 Bounded Linear Diophantine Equations

We want to count integer solutions of

$$
x_1+x_2+\cdots+x_k=n,\qquad l_i \le x_i \le r_i
$$

## Step 1: remove lower bounds

Set

$$
y_i = x_i - l_i,\qquad U_i = r_i - l_i,\qquad N = n - \sum_{i=1}^{k} l_i
$$

Then the problem becomes

$$
y_1+y_2+\cdots+y_k=N,\qquad 0 \le y_i \le U_i
$$

If $N < 0$ or $N > \sum U_i$, the answer is $0$.

## Inclusion-exclusion formula

Let $A_i$ be the event that $y_i \ge U_i+1$. Then

$$
\# =
\sum_{T \subseteq [k]} (-1)^{|T|}
\binom{N-\sum_{i \in T}(U_i+1)+k-1}{k-1}
$$

with the usual convention that illegal binomial parameters contribute $0$.

Equivalently, in the original variables:

$$
\# =
\sum_{T \subseteq [k]} (-1)^{|T|}
\binom{
n-\sum_{i=1}^{k} l_i - \sum_{i \in T}(r_i-l_i+1)+k-1
}{k-1}
$$

This is exact, but direct subset enumeration costs $O(k2^k)$.

## Prefix-sum DP: $O(kN)$

Define $dp[i][s]$ as the number of ways to use the first $i$ variables to obtain sum $s$. Then

$$
dp[i][s] = \sum_{x=0}^{\min(U_i,s)} dp[i-1][s-x]
$$

Let

$$
\text{pref}[t] = \sum_{u=0}^{t} dp[i-1][u]
$$

Then the transition becomes

$$
dp[i][s]
=
\text{pref}[s]
- \bigl(s-U_i-1 \ge 0 ? \text{pref}[s-U_i-1] : 0\bigr)
$$

so every state is updated in $O(1)$ after prefix sums.

Reference implementation:

```cpp
#include <bits/stdc++.h>
using namespace std;
const int MOD = 1000000007;

inline int add(int a, int b) {
    a += b;
    if (a >= MOD) a -= MOD;
    return a;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int k;
    long long n;
    cin >> k >> n;

    vector<long long> L(k), R(k);
    for (int i = 0; i < k; ++i) cin >> L[i] >> R[i];

    long long sumL = 0, sumU = 0;
    vector<int> U(k);
    for (int i = 0; i < k; ++i) {
        sumL += L[i];
        long long ui = R[i] - L[i];
        if (ui < 0) {
            cout << 0 << "\n";
            return 0;
        }
        U[i] = (int)ui;
        sumU += ui;
    }

    long long N64 = n - sumL;
    if (N64 < 0 || N64 > sumU) {
        cout << 0 << "\n";
        return 0;
    }
    int N = (int)N64;

    vector<int> prev(N + 1, 0), cur(N + 1, 0), pref(N + 1, 0);
    prev[0] = 1;
    int reach = 0;

    for (int i = 0; i < k; ++i) {
        reach = min(N, reach + U[i]);
        int run = 0;
        for (int s = 0; s <= reach; ++s) {
            run = add(run, prev[s]);
            pref[s] = run;
        }
        for (int s = 0; s <= reach; ++s) {
            int left = s - U[i] - 1;
            int val = pref[s];
            if (left >= 0) {
                val -= pref[left];
                if (val < 0) val += MOD;
            }
            cur[s] = val;
        }
        for (int s = reach + 1; s <= N; ++s) cur[s] = 0;
        swap(prev, cur);
    }

    cout << prev[N] << "\n";
    return 0;
}
```

## Equal-cap case: all upper bounds are the same

If every variable satisfies

$$
0 \le x_i \le k
$$

and

$$
x_1+\cdots+x_n=S
$$

then inclusion-exclusion gives

$$
g(n,S,k)
=
\sum_{i=0}^{\lfloor S/(k+1)\rfloor}
(-1)^i
\binom{n}{i}
\binom{S-i(k+1)+n-1}{n-1}
$$

The number of summands is only $O(S/(k+1))$, so this version is often quoted as an $O(S/k)$ counting formula.

# 4 Derangements

A derangement is a permutation $p$ of $\{1,2,\dots,n\}$ such that

$$
p_i \ne i \qquad \text{for all } i
$$

Denote the number of derangements by $D(n)$.

## Recurrence

$$
D(0)=1,\qquad D(1)=0,\qquad
D(n)=(n-1)\bigl(D(n-1)+D(n-2)\bigr)\quad (n\ge2)
$$

## Inclusion-exclusion formula

Let $A_i$ be the event that position $i$ is fixed. Then

$$
D(n)
=
\left|S \setminus \bigcup_{i=1}^{n} A_i\right|
=
\sum_{k=0}^{n} (-1)^k \binom{n}{k}(n-k)!
$$

Equivalently,

$$
\boxed{
D(n)=n!\sum_{k=0}^{n}\frac{(-1)^k}{k!}
}
$$

Hence

$$
\frac{D(n)}{n!} \to \frac{1}{e}
$$

as $n \to \infty$.

## Exponential generating function

A permutation is a set of disjoint cycles. The EGF of all cycles is

$$
\text{CYC}(x)=\sum_{k\ge1}\frac{x^k}{k}=-\ln(1-x)
$$

If we forbid $1$-cycles, we get

$$
\text{CYC}_{\ge2}(x)=-\ln(1-x)-x
$$

Thus the EGF of derangements is

$$
\boxed{
H(x)=\exp(\text{CYC}_{\ge2}(x))
= \frac{e^{-x}}{1-x}
}
$$

Expanding this EGF again yields

$$
\frac{D(n)}{n!} = \sum_{k=0}^{n}\frac{(-1)^k}{k!}
$$

which is the same inclusion-exclusion formula in generating-function form.

## Exactly $k$ fixed points

If a permutation of $[n]$ has exactly $k$ fixed points:

1. choose which $k$ positions are fixed
2. derange the remaining $n-k$ positions

So the answer is

$$
\boxed{
\binom{n}{k} D(n-k)
}
$$

or explicitly,

$$
\binom{n}{k}
\sum_{i=0}^{n-k}(-1)^i\binom{n-k}{i}(n-k-i)!
$$

## Linear-time recurrence code

```cpp
D[0] = 1;
D[1] = 0;
for (int i = 2; i <= MAXN; ++i) {
    D[i] = 1LL * (i - 1) * (D[i - 1] + D[i - 2]);
}
```
