---
title: "Combinatorics: Order Theory — Chromatic Polynomials, Chordal Graphs, Order Polynomials, Dilworth & Hall"
date: 2026-04-26
slug: "combinatorics-order-theory"
description: "Chromatic polynomial, chordal/interval graphs, PEO product formula, order polynomials (chain/antichain/tree/DAG/divisor lattice), MacMahon formula, Dilworth, Mirsky, Hall's marriage theorem, Erdős–Szekeres, missile interception."
summary: "Chromatic polynomial, chordal/interval graphs, PEO product formula, order polynomials (chain/antichain/tree/DAG/divisor lattice), MacMahon formula, Dilworth, Mirsky, Hall's marriage theorem, Erdős–Szekeres, missile interception."
categories: [Combinatorics]
tags: [math, combinatorics, graph, chromatic-polynomial, chordal-graph, poset, order-theory, dilworth, hall, dp]
math: true
toc: true
---

# 1 Chromatic Polynomial

> **[Theorem — Chromatic Polynomial]**
>
> The number of proper $k$-colorings of graph $G$ (adjacent vertices receive different colors) is a polynomial in $k$, called the **chromatic polynomial** $P_G(k)$.
>
> Closed forms for common graphs:
>
> | Graph | $P_G(k)$ |
> |---|---|
> | Complete graph $K_n$ | $k(k-1)(k-2)\cdots(k-n+1)$ |
> | Tree $T_n$ | $k(k-1)^{n-1}$ |
> | Cycle $C_n$ | $(k-1)^n+(-1)^n(k-1)$ |
>
> General graphs obey the **deletion-contraction recurrence** (NP-hard to evaluate in general):
>
> $$P_G(k)=P_{G-e}(k)-P_{G/e}(k)$$
>
> where $G-e$ deletes edge $e$ and $G/e$ contracts it (merges its endpoints).

**Clique:** a set of vertices that are pairwise adjacent.

---

# 2 Example — Colorful Segments 2 (Chordal & Interval Graphs)

[Codeforces Gym 105385 Problem C](https://codeforces.com/gym/105385/problem/C)

Given $n$ segments on the number line, assign each a color from $k$ options so that same-colored segments do not intersect. Count the ways. $n\le5\times10^5,\ k\le10^9$.

## 2.1 Graph Model

One vertex per segment; connect $v_i$ and $v_j$ if their segments intersect. "Same-colored segments do not intersect" = proper $k$-coloring of this graph = $P_G(k)$.

Since each segment is an interval, this is an **interval graph** — a special case of a **chordal graph**.

## 2.2 PEO + Product Formula for Chordal Graphs

> **[Theorem — Chromatic Polynomial of Chordal Graphs]**
>
> Every chordal graph has a **perfect elimination ordering (PEO)** $v_1,\dots,v_n$: for each $v_i$, the neighbours that appear *before* it in the ordering form a clique.
>
> Let $s_i = |\text{earlier neighbours of }v_i|$. Then:
>
> $$P_G(k)=\prod_{i=1}^n(k-s_i)$$
>
> **Proof:** Color in order $v_1,\dots,v_n$. The earlier neighbours of $v_i$ form a clique, so they all have distinct colors, occupying $s_i$ colors. The number of valid colors for $v_i$ is $k-s_i$. Multiply over all vertices.

## 2.3 PEO for Interval Graphs: Sort by Right Endpoint

Sort segments by right endpoint $r$ (ascending). This gives a valid PEO.

**Why:** For the $i$-th segment $I_i$ (right endpoint $R_i$), every "later" neighbour (index $j>i$ and intersecting $I_i$) contains the point $R_i$ — so they pairwise intersect, forming a clique. ✓

$s_i$ = number of segments with right endpoint $\ge R_i$ and left endpoint $\le R_i$, minus $I_i$ itself. Compute with a two-pointer sweep:

```cpp
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int T; cin >> T;
    while (T--) {
        int n; ll k;
        cin >> n >> k;
        vector<Seg> a(n);
        for (int i = 0; i < n; ++i) cin >> a[i].l >> a[i].r;

        // sort by right endpoint → PEO order
        vector<int> ordR(n);
        iota(ordR.begin(), ordR.end(), 0);
        sort(ordR.begin(), ordR.end(), [&](int i, int j){ return a[i].r < a[j].r; });

        vector<ll> R(n);
        for (int pos = 0; pos < n; ++pos) R[pos] = a[ordR[pos]].r;

        // also sort by left endpoint for sweep
        vector<pair<ll,int>> arr(n);
        for (int pos = 0; pos < n; ++pos) arr[pos] = {a[ordR[pos]].l, pos};
        sort(arr.begin(), arr.end());

        int p = 0; ll ans = 1, K = k % P;
        for (int pos = 0; pos < n; ++pos) {
            ll curR = R[pos];
            while (p < n && arr[p].first <= curR) ++p;
            int s = p - (pos + 1);
            ans = ans * ((K - s + P) % P) % P;
        }
        cout << ans << '\n';
    }
    return 0;
}
```

---

# 3 Order Polynomials

Count **order-preserving maps** $f:P\to\{1,\dots,k\}$ on a finite poset $P$:

- **Weakly monotone** ($x\preceq y\Rightarrow f(x)\le f(y)$): counted by the **order polynomial** $\Omega_P(k)$.
- **Strictly monotone** ($x\prec y\Rightarrow f(x)\lt f(y)$): counted by $\bar\Omega_P(k)$.

Both are polynomials in $k$.

## 3.1 Antichain

$n$ pairwise incomparable elements — no constraints:

$$\Omega_P(k)=\bar\Omega_P(k)=k^n$$

## 3.2 Chain

Chain $x_1\prec x_2\prec\cdots\prec x_n$:

| Type | Count | Analogy |
|---|---|---|
| Weakly monotone ($\le$) | $\binom{n+k-1}{n}$ | multiset selection / stars-and-bars |
| Strictly monotone ($\lt$) | $\binom{k}{n}$ | ordinary combination |

## 3.3 Disjoint Union

If $P=P_1\sqcup\cdots\sqcup P_m$ (components pairwise incomparable):

$$\Omega_P(k)=\prod_{i=1}^m\Omega_{P_i}(k),\qquad\bar\Omega_P(k)=\prod_{i=1}^m\bar\Omega_{P_i}(k)$$

## 3.4 Tree Posets

**Monotone coloring** (child color $\ge$ parent): DP with $dp_v(c)=$ ways to color subtree of $v$ with $f(v)=c$:

$$dp_v(c)=\prod_{u\in\text{children}(v)}\left(\sum_{t=c}^k dp_u(t)\right),\qquad\Omega_P(k)=\sum_{c=1}^k dp_{\text{root}}(c)$$

**Linear extensions** (strict bijection $f:V\to\{1,\dots,n\}$, parent $\lt$ child):

$$\#\text{linear extensions}=\frac{n!}{\prod_v|\text{subtree}(v)|}$$

## 3.5 DAG Posets (Bitmask DP, $n\le20$)

> **[Algorithm — Order Polynomial on a DAG]**
>
> Count $\Omega_P(k)$ by the **order ideal** correspondence: each order-preserving $f$ corresponds to a chain $\varnothing=I_0\subseteq I_1\subseteq\cdots\subseteq I_k=P$ where each $I_t$ is downward-closed (an order ideal).
>
> **Steps:**
>
> 1. Enumerate all order ideals via bitmask (if $v\in I$ then all ancestors of $v$ are in $I$).
> 2. Run length-$k$ DP on the ideal lattice: $dp_{t+1}[I]=\sum_{J\subseteq I}dp_t[J]$.
> 3. Start $dp_0[\varnothing]=1$; answer is $dp_k[P]$.

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m; long long K;
    cin >> n >> m >> K;

    vector<vector<int>> g(n);
    for (int i = 0; i < m; ++i) {
        int u, v; cin >> u >> v; --u; --v;
        g[u].push_back(v);
    }

    // precompute ancestor bitmask for each node
    vector<int> preMask(n, 0);
    for (int s = 0; s < n; ++s) {
        vector<int> st = {s};
        vector<char> vis(n, 0); vis[s] = 1;
        while (!st.empty()) {
            int x = st.back(); st.pop_back();
            for (int y : g[x]) if (!vis[y]) { vis[y] = 1; st.push_back(y); }
        }
        for (int y = 0; y < n; ++y)
            if (vis[y] && y != s) preMask[y] |= (1 << s);
    }

    int fullMask = (1 << n) - 1;

    // enumerate all order ideals (downward-closed subsets)
    vector<int> ideals; vector<int> idOf(1 << n, -1);
    for (int S = 0; S < (1 << n); ++S) {
        bool ok = true;
        for (int v = 0; v < n && ok; ++v)
            if ((S >> v & 1) && (preMask[v] & ~S)) ok = false;
        if (ok) { idOf[S] = ideals.size(); ideals.push_back(S); }
    }

    int J = ideals.size();
    int idEmpty = idOf[0], idFull = idOf[fullMask];

    // precompute subset relations: preds[i] = all j with ideals[j] ⊆ ideals[i]
    vector<vector<int>> preds(J);
    for (int i = 0; i < J; ++i)
        for (int j = 0; j < J; ++j)
            if ((ideals[j] & ideals[i]) == ideals[j]) preds[i].push_back(j);

    // length-K DP over ideal lattice
    vector<long long> dp(J, 0), ndp(J, 0);
    dp[idEmpty] = 1;
    for (long long t = 0; t < K; ++t) {
        fill(ndp.begin(), ndp.end(), 0);
        for (int i = 0; i < J; ++i) {
            long long s = 0;
            for (int j : preds[i]) s += dp[j];
            ndp[i] = s;
        }
        dp.swap(ndp);
    }
    cout << dp[idFull] << "\n";
    return 0;
}
```

## 3.6 Divisor Lattice and MacMahon's Formula

For $N=p_1^{e_1}\cdots p_r^{e_r}$, the divisor poset $P_N$ ($d_1\preceq d_2\iff d_1\mid d_2$) is isomorphic to the grid poset $\prod_i\{0,\dots,e_i\}$ (coordinatewise order).

Counting weakly monotone maps $f:P_N\to[k]$:

| Case | Formula | Notes |
|---|---|---|
| $r=1$ (chain) | $\binom{k+e_1}{e_1}$ | standard stars-and-bars |
| $r=2$ (grid) | MacMahon box formula | plane partitions in $(e_1+1)\times(e_2+1)\times k$ box |
| $r\ge3$ | no simple product | determinantal / symmetric-function methods |

**MacMahon box formula** ($r=2$):

$$\Omega_{P_N}(k)=\prod_{i=1}^{e_1+1}\prod_{j=1}^{e_2+1}\prod_{t=1}^{k}\frac{i+j+t-1}{i+j+t-2}$$

---

# 4 Fundamental Theorems

A **chain** is a totally ordered subset; an **antichain** is a subset with no two elements comparable.

## 4.1 Dilworth's Theorem

> **[Theorem — Dilworth]**
>
> In a finite poset $S$:
>
> $$\text{width}\ w = \text{size of largest antichain} = \text{minimum number of chains covering }S$$

## 4.2 Mirsky's Theorem

> **[Theorem — Mirsky]**
>
> In a finite poset $S$:
>
> $$\text{height}\ h = \text{length of longest chain} = \text{minimum number of antichains covering }S$$

> **Hasse diagram view:**
>
> - Dilworth: width = min vertical paths (chains) to partition vertices
> - Mirsky: height = min horizontal layers (antichains) to partition vertices
>
> They are perfectly dual: reversing the poset swaps chains ↔ antichains.

## 4.3 Hall's Marriage Theorem

> **[Theorem — Hall's Marriage Theorem]**
>
> A family $\mathcal{A}=\{A_1,\dots,A_n\}$ admits a system of distinct representatives ($a_i\in A_i$, all distinct) **if and only if** for every $I\subseteq\{1,\dots,n\}$:
>
> $$\left|\bigcup_{i\in I}A_i\right|\ge|I|$$
>
> **Bipartite version:** in a bipartite graph with left vertices $X$ and right vertices $Y$, a matching covering all of $X$ exists iff $|N(S)|\ge|S|$ for all $S\subseteq X$.

### The Four Theorems — One Family

All four express the same idea: "size of the largest structure = size of the smallest decomposition":

| Theorem | Setting | Equality |
|---|---|---|
| Hall | bipartite graph | matching exists ↔ Hall's condition |
| König | bipartite graph | max matching = min vertex cover |
| Dilworth | poset | max antichain = min chain cover |
| Mirsky | poset | max chain = min antichain cover |

## 4.4 Erdős–Szekeres Theorem

> **[Theorem — Erdős–Szekeres]**
>
> Any sequence of $rs+1$ real numbers contains a non-decreasing subsequence of length $\ge r+1$ or a non-increasing subsequence of length $\ge s+1$.

> **[Proof — via Dilworth's Theorem]**
>
> Define a poset on $\{(i,a_i)\}_{i=1}^n$ by $(i,a_i)\preceq(j,a_j)\iff i\le j\wedge a_i\le a_j$.
>
> If the width (largest antichain) is $\le s$, Dilworth gives at most $s$ chains covering all $n\ge rs+1$ points. If every chain has length $\le r$, then $n\le rs$ — contradiction. So some chain has length $\ge r+1$, giving a non-decreasing subsequence of that length.

---

# 5 Example — Missile Interception (Luogu P1020 / NOIP1999)

Given heights $h_1,\dots,h_n$. One interception system covers a **non-increasing subsequence**.

- **Q1:** Maximum missiles one system intercepts = length of longest non-increasing subsequence (LNIS).
- **Q2:** Minimum systems to cover all missiles.

> **[Solution via Dilworth]**
>
> Define poset $\{(i,h_i)\}$ with $(i,h_i)\preceq(j,h_j)\iff i\le j\wedge h_i\ge h_j$.
>
> - A chain = a non-increasing subsequence (one system's interceptions).
> - An antichain = a strictly increasing subsequence (each pair conflicts — no system can cover both).
>
> By Dilworth: **minimum chain cover = width = maximum antichain = LIS length**.
>
> - Q1: longest chain = LNIS, computed by running LIS on the negated sequence.
> - Q2: minimum chains = LIS of the original sequence.
>
> Both in $O(n\log n)$ via binary search (patience sorting).
