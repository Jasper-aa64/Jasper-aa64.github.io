---
title: "Number Theory #3.1: Sieve Problems — Coin System DP via Sieve"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-3-1-sieve-problems"
description: "A sieve-style dynamic programming problem on coin systems whose denominations form a divisibility chain, including the greedy optimality proof, transition derivation, and full implementation."
summary: "Sieve + DP for a coin-system problem: greedy optimality under divisibility-chain denominations, optimal substructure, transition by saved coin count, and full code."
categories: [Number Theory]
tags: [math, number-theory, sieve, dp, coin-system, greedy]
math: true
toc: true
---

# Sieve-Method Problems

> **[Example — Nowcoder 19895: Sieve + DP]**
>
> We need to create a sequence of coin denominations. Suppose the denominations are $x_1,x_2,x_3,\ldots$. Then $x_1$ must be $1$, and each later denomination must be a positive integer multiple of an earlier one: $x_b$ is a multiple of $x_a$ for $b>a$.
>
> For example, $1,5,125,250$ is valid, while $1,5,100,125$ is not.
>
> Given prices $w_1,w_2,\ldots,w_N$ of $N$ items, choose a valid coin system that minimizes the total number of coins needed to buy all items. No change is allowed.

# 1 Key Property

For this kind of system, where each later denomination is a multiple of an earlier denomination, there is an important property:

> **Greedy is optimal.** To pay an amount $A$, always use the largest current denomination not exceeding $A$, then the next largest, and so on.
>
> **Reason.** A larger denomination can always replace several smaller denominations because of the divisibility condition. Using one large coin is never worse than using the corresponding group of smaller coins.

Therefore, if the maximum denomination is fixed at $M$, then for each price $a_k$, the optimal number of coins is obtained by greedy decomposition under this coin system.

# 2 State Design and Optimal Substructure

Let

$$
f[i] := \text{minimum total number of coins needed when the maximum denomination is exactly } i.
$$

Why does this have optimal substructure?

If an optimal sequence ends with maximum denomination $M$, then its previous denomination must be some $i$ with $i\mid M$. Removing $M$ leaves a valid coin system whose maximum denomination is $i$. That prefix must itself be optimal for the subproblem with maximum denomination $i$; otherwise replacing it by a better prefix would improve the whole solution, which is a contradiction.

Thus, any optimal sequence ending at $M$ can be viewed as taking an optimal sequence ending at some $i$ and then adding one new denomination

$$
M=i\cdot j.
$$

This is the basis of the transition from $f[i]$ to $f[M]$.

# 3 Deriving the Transition: How Much Does One New Coin Save?

Suppose we already have an optimal solution whose maximum denomination is $i$, and we want to add a larger denomination

$$
M=i\cdot j,\qquad j\ge 2.
$$

After adding $M$, what changes?

- For any price $a_k$, under the old system with maximum denomination $i$, the greedy decomposition contains some number of $i$-coins.
- After adding $M=i\cdot j$, every group of $j$ coins of denomination $i$ can be replaced by one coin of denomination $M$.
- Each such replacement reduces the coin count by $j-1$.

For one item with price $a_k$, the number of such replaceable groups is

$$
\left\lfloor\frac{a_k}{i\cdot j}\right\rfloor.
$$

So this item saves

$$
(j-1)\left\lfloor\frac{a_k}{i\cdot j}\right\rfloor
$$

coins. Summing over all items, the total saving from adding $M=i\cdot j$ is

$$
\text{cnt}=(j-1)\sum_{k=1}^{N}\left\lfloor\frac{a_k}{i\cdot j}\right\rfloor.
$$

Therefore:

$$
f[i\cdot j]
=
\min\left(
    f[i\cdot j],
    f[i]-\text{cnt}
\right).
$$

**Intuition.** Start from the question "how can adding a larger denomination reduce the number of coins?" The only possible improvement is packing several adjacent smaller coins into one larger coin. The replacement rate is fixed: $j$ coins become $1$ coin, so each replacement saves $j-1$ coins. The number of replacements for price $a_k$ is exactly $\lfloor a_k/(i\cdot j)\rfloor$.

# 4 Initialization and Answer

- With only the $1$-coin, buying item $a_k$ needs $a_k$ coins, so

$$
f[1]=\sum_{k=1}^{N}a_k.
$$

- Denominations larger than $\max a_k$ are useless because no change is allowed.
- The final answer is

$$
\min_{1\le i\le \max A} f[i].
$$

The complexity is

$$
O(\max A\log \max A),
$$

from the harmonic-series style enumeration of multiples.

```cpp
#include <iostream>
#include <algorithm>
#include <cstring>
using namespace std;

const int N = 1e5 + 10;

int f[N], w[N];

int main() {
    memset(f, 0x3f, sizeof f);
    f[1] = 0;

    int n, max_price = -1;
    cin >> n;

    for (int i = 1; i <= n; i++) {
        cin >> w[i];
        f[1] += w[i];
        max_price = max(max_price, w[i]);
    }

    for (int i = 1; i <= max_price; i++) {
        for (int j = 2; i * j <= max_price; j++) {
            int cnt = 0;
            for (int k = 1; k <= n; k++) {
                cnt += w[k] / (i * j);
            }
            cnt = cnt * (j - 1);
            f[i * j] = min(f[i * j], f[i] - cnt);
        }
    }

    int res = 1e9 + 10;
    for (int i = 1; i <= max_price; i++) {
        res = min(res, f[i]);
    }

    cout << res << endl;
    return 0;
}
```
