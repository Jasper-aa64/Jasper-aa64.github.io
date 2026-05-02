---
title: "Number Theory #3.1: Sieve Problems — Coin System DP via Sieve"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-3-1-sieve-problems"
description: "A sieve-style DP for a coin-system problem where every later denomination is a multiple of a previous one."
summary: "Greedy optimality for divisibility-chain coin systems, DP over the maximum denomination, and a sieve-style transition by adding one larger coin."
categories: [Number Theory]
tags: [math, number-theory, sieve, dp, coin-system, greedy]
math: true
toc: true
---

# Problem

> **[Example — Nowcoder 19895: Sieve + DP]**
>
> We want to design a sequence of coin denominations
>
> $$
> x_1,x_2,x_3,\ldots
> $$
>
> satisfying the following rules:
>
> - $x_1=1$.
> - The denominations form a divisibility chain: for every $a\lt b$, $x_b$ is a positive integer multiple of $x_a$. Equivalently, each newly appended denomination must be a multiple of the current largest denomination.
>
> For example, $1,5,125,250$ is a valid coin system, while $1,5,100,125$ is not.
>
> Given $N$ item prices
>
> $$
> w_1,w_2,\ldots,w_N,
> $$
>
> choose a valid coin system that minimizes the total number of coins needed to buy all items. No change is allowed.

This is a number-theory-flavored DP problem because the legal transitions between denominations are exactly divisibility transitions. Once the current largest denomination is $i$, the next denomination can be any multiple $i\cdot j$.

# 1 Key Property: Greedy Is Optimal

For a coin system where every new denomination is built as a multiple of the previous largest denomination, greedy payment is optimal.

That is, to pay an amount $A$, always use the largest coin not exceeding the remaining amount, then repeat.

The reason is the divisibility constraint. If a larger coin has value $M=i\cdot j$, then one $M$-coin can replace exactly $j$ coins of value $i$. Using the larger coin is never worse than using those smaller coins:

$$
j\text{ coins of value }i
\quad\Longrightarrow\quad
1\text{ coin of value }i\cdot j.
$$

So if the largest denomination is fixed, the best way to pay each price is determined by greedy decomposition.

# 2 DP State

Let

$$
f[i]
=
\text{minimum total number of coins needed when the largest denomination is exactly }i.
$$

The largest denomination matters because once it is fixed at $i$, the next coin we add must be a multiple of $i$:

$$
M=i\cdot j,\qquad j\ge 2.
$$

This gives the optimal substructure.

Suppose an optimal coin system ends with maximum denomination $M$. The denomination right before $M$ must be some $i$ with

$$
i\mid M.
$$

After removing $M$, the remaining denominations are still valid. Moreover, that remaining prefix must be optimal among all systems whose maximum denomination is $i$; otherwise we could replace it by a better prefix and improve the whole system.

Therefore, every optimal system ending at $M$ can be seen as:

1. take an optimal system ending at some divisor $i$;
2. add one new denomination $M=i\cdot j$.

This is why the transition enumerates multiples, just like a sieve.

# 3 Transition: How Much Does One New Coin Save?

Assume we already have the best system whose maximum coin is $i$. Now add a larger coin

$$
M=i\cdot j,\qquad j\ge 2.
$$

For one price $w_k$, before adding $M$, greedy decomposition may contain several $i$-coins. After adding $M$, every group of $j$ such $i$-coins can be replaced by one $M$-coin.

For this one item, the number of replaceable groups is

$$
\left\lfloor \frac{w_k}{i\cdot j}\right\rfloor.
$$

Each replacement changes

$$
j\text{ small coins}
\quad\to\quad
1\text{ large coin},
$$

so it saves $j-1$ coins.

Thus, for this one item, the number of coins saved is

$$
(j-1)\left\lfloor \frac{w_k}{i\cdot j}\right\rfloor.
$$

Summing over all items, adding the coin $M=i\cdot j$ saves

$$
\text{save}
=
(j-1)
\sum_{k=1}^{N}
\left\lfloor \frac{w_k}{i\cdot j}\right\rfloor.
$$

So the DP transition is

$$
f[i\cdot j]
=
\min\left(
f[i\cdot j],
f[i]-\text{save}
\right).
$$

This is the core idea: adding a larger denomination is useful only because it packs several smaller coins into one coin. The packing ratio is fixed by divisibility, and the number of packs is counted by floor division.

# 4 Initialization and Answer

If the only coin is $1$, then buying an item with price $w_k$ needs exactly $w_k$ coins. Therefore,

$$
f[1]=\sum_{k=1}^{N}w_k.
$$

There is no need to consider denominations larger than

$$
\max w_k,
$$

because no item can use such a coin when no change is allowed.

The answer is

$$
\min_{1\le i\le \max w_k} f[i].
$$

# 5 Why This Is a Sieve-Style DP

The transition has the form

$$
i \to i\cdot j.
$$

So for every possible current maximum denomination $i$, we enumerate all larger denominations that are multiples of $i$:

```cpp
for (int i = 1; i <= max_price; i++) {
    for (int j = 2; i * j <= max_price; j++) {
        // transition from i to i * j
    }
}
```

This is the same enumeration pattern as a divisor/multiple sieve.

The number of pairs $(i,j)$ with $i\cdot j\le V$ is

$$
\sum_{i=1}^{V}\left\lfloor\frac{V}{i}\right\rfloor
=
O(V\log V),
$$

where $V=\max w_k$.

The direct implementation below recomputes

$$
\sum_k \left\lfloor\frac{w_k}{i\cdot j}\right\rfloor
$$

inside the transition, so its running time is

$$
O(NV\log V).
$$

If needed, this term can be precomputed by frequency counting:

$$
g[t]=\sum_{k=1}^{N}\left\lfloor\frac{w_k}{t}\right\rfloor.
$$

Then the DP itself becomes $O(V\log V)$.

# 6 Implementation

This is the direct version corresponding to the derivation above.

```cpp
#include <iostream>
#include <algorithm>
#include <cstring>
using namespace std;

const int N = 1e5 + 10;

int f[N], w[N];

int main() {
    memset(f, 0x3f, sizeof f);

    int n, max_price = -1;
    cin >> n;

    f[1] = 0;
    for (int i = 1; i <= n; i++) {
        cin >> w[i];
        f[1] += w[i];
        max_price = max(max_price, w[i]);
    }

    for (int i = 1; i <= max_price; i++) {
        for (int j = 2; i * j <= max_price; j++) {
            int save = 0;

            for (int k = 1; k <= n; k++) {
                save += w[k] / (i * j);
            }

            save *= (j - 1);
            f[i * j] = min(f[i * j], f[i] - save);
        }
    }

    int ans = 1e9 + 10;
    for (int i = 1; i <= max_price; i++) {
        ans = min(ans, f[i]);
    }

    cout << ans << endl;
    return 0;
}
```

# 7 Optimized Counting Variant

The expensive part of the direct code is the loop over all prices for every transition:

```cpp
for (int k = 1; k <= n; k++) {
    save += w[k] / (i * j);
}
```

Since the transition only needs the value

$$
\sum_k \left\lfloor\frac{w_k}{t}\right\rfloor,
$$

where $t=i\cdot j$, we can precompute it for every $t$.

Let $\text{freq}[x]$ be the number of items with price $x$. Then

$$
g[t]
=
\sum_{x=1}^{V}\text{freq}[x]\left\lfloor\frac{x}{t}\right\rfloor.
$$

Use a prefix count array and group prices by the value of $\lfloor x/t\rfloor$:

```cpp
vector<int> freq(max_price + 1), pref(max_price + 1), g(max_price + 1);

for (int i = 1; i <= n; i++) {
    freq[w[i]]++;
}

for (int x = 1; x <= max_price; x++) {
    pref[x] = pref[x - 1] + freq[x];
}

for (int t = 1; t <= max_price; t++) {
    for (int q = 1, l = t; l <= max_price; q++, l += t) {
        int r = min(max_price, l + t - 1);
        int cnt = pref[r] - pref[l - 1];
        g[t] += q * cnt;
    }
}
```

Then the transition becomes:

```cpp
int t = i * j;
int save = (j - 1) * g[t];
f[t] = min(f[t], f[i] - save);
```

The important point is not the implementation detail, but the modeling step:

the effect of adding denomination $i\cdot j$ depends only on how many complete blocks of size $i\cdot j$ appear across all item prices.
