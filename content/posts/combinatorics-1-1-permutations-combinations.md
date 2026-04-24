---
title: "Combinatorics #1.1: Permutations and Combinations"
date: 2026-04-24
slug: "combinatorics-1-1-permutations-combinations"
description: "Hockey Stick identity, addition/multiplication principles, binomial identities, example problems: bitonic sequences, multiset permutations, multi-layer coloring DP, CCPC Subpermutation."
summary: "Hockey Stick identity, addition/multiplication principles, binomial identities, example problems: bitonic sequences, multiset permutations, multi-layer coloring DP, CCPC Subpermutation."
categories: [Combinatorics]
tags: [math, combinatorics, permutation, combination, hockey-stick, dp, ntt]
math: true
toc: true
---

Main methods for counting problems:
1. Direct formulas
2. Dynamic programming
3. Inclusion-exclusion
4. Generating functions
5. Pólya's theorem
6. Transform via "inversion"

# 1 Hockey Stick Identity

**Identity A (basic):**
$$\sum_{i=r}^{n}\binom{i}{r}=\binom{n+1}{r+1}$$
Meaning: sum from index $i=r$ up to $n$, where the bottom index equals the upper index.
**Example:** $\displaystyle\sum_{k=2}^{n-1}\binom{k}{2}=\binom{n}{3}$

**Identity B (bounded version):**
$$\sum_{i=a}^{b}\binom{i}{r}=\binom{b+1}{r+1}-\binom{a}{r+1}$$
Meaning: index runs from any $a$ to $b$, not necessarily starting at $r$.
**Example:** $\displaystyle\sum_{k=2}^{n-1}\binom{k}{2}=\binom{n}{3}-\binom{2}{3}=\binom{n}{3}$

Note: out-of-range binomials like $\binom{2}{3}$ are treated as $0$.

---

# 2 Addition Principle

> **Example — Addition Principle + Hockey Stick**
>
> Let $n > 1$ be a positive integer. Count ordered triples $(x,y,z)$ of positive integers with $x+y+z \le n$.
>
> ---
>
> Let $S = x+y+z$. Since $x,y,z \ge 1$, we have $3 \le S \le n$.
>
> **Step 1 — Fix $S$.** The equation $x+y+z=S$ with $x,y,z\ge1$ has
> $$\binom{S-1}{2}$$
> positive integer solutions.
>
> **Step 2 — Sum over all $S$ (Hockey Stick).**
> $$\sum_{S=3}^{n}\binom{S-1}{2}=\sum_{k=2}^{n-1}\binom{k}{2}=\binom{n}{3}$$
>
> Enumerating over $S$ then summing is the **addition principle**. Answer: $\dbinom{n}{3}=\dfrac{n(n-1)(n-2)}{6}$.

---

# 3 Multiplication Principle

**Divisor count theorem.**

If $N = p_1^{r_1}p_2^{r_2}\cdots p_k^{r_k}$, its positive divisors are $\{p_1^{b_1}\cdots p_k^{b_k} : 0\le b_i\le r_i\}$. Each exponent $b_i$ is chosen independently, so:
$$\tau(N)=\prod_{i=1}^{k}(r_i+1)$$

---

# 4 Useful Binomial Identities

$$\binom{n}{m}=\binom{n-1}{m-1}+\binom{n-1}{m}$$
$$\binom{n}{m}=\frac{n}{m}\binom{n-1}{m-1}$$
$$\binom{n}{m}=\frac{n-m+1}{m}\binom{n}{m-1}$$

---

# 5 Integer Solutions of Diophantine Equations

Stars-and-bars basics ($x_i\ge0$, $x_i\ge1$, lower bounds, $\le n$) and bounded ranges (inclusion-exclusion, prefix-sum DP, D&C NTT) — see the dedicated note on Diophantine equations.

---

# 6 Examples

## 6.1 Three Independent Groups — Solve Separately, Then Multiply

> **[Example — CF 869C](https://codeforces.com/contest/869/problem/C)**
>
> Three types of islands coloured red, blue, and purple with counts $a, b, c$. Undirected bridges of length 1 may be built between any two distinct islands. For any two same-coloured islands: they must not be directly connected, and must not reach each other in 2 steps via one intermediate island. Count valid bridge configurations mod $998244353$.
>
> ---
>
> Partition into groups A (red, size $a$), B (blue, size $b$), C (purple, size $c$). Analyse the constraints:
>
> 1. **No bridge within a same-coloured group** (direct distance 1 forbidden).
> 2. **Between two different-coloured groups, the bridges form a matching.** For example, between A and B: if a B-island were connected to two A-islands, those two A-islands would be at distance 2 — a violation. So A-B bridges form a matching; same for A-C and B-C.
>
> The three matchings are independent, so the total count is their product:
> $$|\mathrm{matchings}(K_{a,b})|\times|\mathrm{matchings}(K_{a,c})|\times|\mathrm{matchings}(K_{b,c})|\pmod{998244353}$$

> **Fact — Matchings in complete bipartite graph $K_{n,m}$:**
> $$\sum_{k=0}^{\min(n,m)}\binom{n}{k}\binom{m}{k}k!$$
> Choose $k$ edges: pick $k$ vertices from each side ($\binom{n}{k}\binom{m}{k}$), then bijectively match them ($k!$).

## 6.2 Enumerate $k$ + Binomials

> **[Example — CF 300C](https://codeforces.com/contest/300/problem/C)**
>
> Given two distinct digits $a, b$ ($1\le a<b\le9$), call a positive integer *good* if all its digits are drawn from $\{a,b\}$, and *super-good* if additionally its digit-sum is also good. Count $n$-digit super-good integers mod $10^9+7$. ($1\le n\le10^6$)
>
> ---
>
> Enumerate $k$ = number of $a$-digits ($0\le k\le n$), so $n-k$ digits are $b$. The digit-sum is $S = ka+(n-k)b$. If $S$ is good, this $k$ contributes $\binom{n}{k}$ super-good integers:
>
> ```cpp
> long long ans = 0;
> for (int k = 0; k <= n; k++) {
>     int S = k * a + (n - k) * b;
>     if (good(S)) ans = (ans + C(n, k)) % MOD;
> }
> cout << ans << "\n";
> ```

---

# 7 Examples

## 7.1 Bitonic Sequence with One Repeated Element

> **[Example — CF 1312 D](https://codeforces.com/contest/1312/problem/D)**
>
> Count sequences of length $n$ mod $998244353$ satisfying:
> - Every element is an integer in $[1, m]$.
> - There is **exactly one** pair of equal elements.
> - There exists an index $i$ such that $a_j < a_{j+1}$ for all $j < i$ and $a_j > a_{j+1}$ for all $j \ge i$ (the sequence is **bitonic**: strictly increasing then strictly decreasing).
>
> ($2 \le n \le m \le 2\cdot10^5$)

$$\boxed{\mathrm{Ans}=\binom{m}{n-1}\cdot(n-2)\cdot2^{n-3}}$$

## 7.2 Multiset Permutation + No Leading Zero

> **[Example — CF 991 E](https://codeforces.com/contest/991/problem/E)**
>
> Given a positive integer $n$ (no leading zeros), count positive integers $m$ (no leading zeros) such that:
> - The set of digits appearing in $n$ and in $m$ is identical.
> - Each digit $a$ ($0 \le a \le 9$) appears in $m$ **no more times** than it appears in $n$.
>
> ($1 \le n \le 10^{18}$)

Enumerate a usage vector $\mathbf{c}=(c_0,\ldots,c_9)$ where
$$1\le c_d\le\mathrm{cnt}_d\;(\mathrm{cnt}_d>0),\quad c_d=0\;(\mathrm{cnt}_d=0),\quad L=\sum c_d.$$

**Total:** multiset permutation count $M=\dfrac{L!}{\prod c_d!}$.

**Illegal** (leading zero): fix the first digit as 0, distribute the remaining $L-1$ positions:
$$M_0=\frac{(L-1)!}{(c_0-1)!\prod_{d>0}c_d!}=M\cdot\frac{c_0}{L}$$

Contribution of this $\mathbf{c}$:
$$\mathrm{contrib}(\mathbf{c})=M-M_0=M\cdot\frac{L-c_0}{L}$$

Answer $= \displaystyle\sum_{\mathbf{c}}\mathrm{contrib}(\mathbf{c})$.

With $|n|\le19$ and at most 10 digit types, the number of $\mathbf{c}$-states is $\prod_{d:\mathrm{cnt}_d>0}\mathrm{cnt}_d$, which is feasible.

> **Two approaches for counting illegal (leading-zero) arrangements:**
>
> - **Route A:** Fix the first position as 0 and count directly — used above.
> - **Route B:** Symmetry / proportion argument. Treat all $M$ permutations as equally likely. Since each permutation contains exactly $c_0$ zeros among $L$ positions, the probability of a leading zero is $c_0/L$, giving $M_0 = M\cdot c_0/L$. The same argument gives the count of permutations starting with any specific digit $x$ as $M\cdot c_x/L$.

---

# 8 Multi-Layer Coloring DP

> **[Example — CF 140 E](https://codeforces.com/contest/140/problem/E)**
>
> A New Year tree has $n$ layers of lights; layer $i$ has $l_i$ lights. Requirements:
> - Adjacent lights **within** each layer have different colors.
> - Adjacent layers use **different color sets**.
>
> There are $m$ types of colored lights. Count valid decorating schemes mod $p$.
>
> ($1 \le n,m \le 10^6$, $1 \le l_i \le 5000$, $L = \sum_{i=1}^n l_i \le 10^7$, $2 \le p \le 10^9$)

## 8.1 Within One Layer: Exactly $k$ Colours, No Two Adjacent the Same

Erase colour names — treat $k$ colours as abstract labels $1,\ldots,k$ (renaming = same arrangement). Define:
$$a[s][k]=\#\{\text{sequences of length }s\text{ using exactly }k\text{ distinct colours, no two adjacent equal}\}\quad(\text{colours unlabelled})$$

**Recurrence** (same structure as Stirling numbers of the 2nd kind, but with adjacency constraint):
$$a[s][k]=a[s-1][k-1]+(k-1)\cdot a[s-1][k]$$

- Position $s$ uses a **new** colour → $a[s-1][k-1]$
- Position $s$ reuses an existing colour but not the one at position $s-1$ → $k-1$ choices

**Base:** $a[1][1]=1$; all other $a[1][k]=0$.

Precompute up to $s\le5000$: $\Theta(s^2)$ transitions.

## 8.2 Restore Concrete Colour Names

$a[s][k]$ uses abstract labels. To map to $m$ real colours, choose which $k$ concrete colours to use and assign them:
$$A_m^k=m(m-1)\cdots(m-k+1)$$
(equivalently $\binom{m}{k}\cdot k!$).

If the colour set is already fixed (e.g. "same set as the previous layer"), only $k$ colours are usable, giving $A_k^k=k!$.

**Arrangements for one layer of length $s$ using exactly $k$ specific concrete colours:**
$$A_m^k\cdot a[s][k]$$

## 8.3 Inter-Layer DP: Track Only the Colour-Count per Layer

Define:
$$d_i[k]=\text{ways for layers }1,\ldots,i\text{ to all be valid, with layer }i\text{ using exactly }k\text{ colours}$$

Let $S_{i-1}=\sum_{t\ge1}d_{i-1}[t]$ = total valid ways for the first $i-1$ layers.

**Ignoring** the "colour set must differ from previous layer" constraint:
$$\mathrm{naive}_i[k]=S_{i-1}\cdot A_m^k\cdot a[l_i][k]$$

**Subtract** the invalid part — layer $i$'s colour set is **identical** to layer $i-1$'s. This only applies when layer $i-1$ also used exactly $k$ colours (count: $d_{i-1}[k]$). For each such case, layer $i$'s filling count is $k!\cdot a[l_i][k]$:

$$\boxed{d_i[k]=a[l_i][k]\cdot\Bigl(A_m^k\cdot S_{i-1}-k!\cdot d_{i-1}[k]\Bigr)}$$

First layer ($i=1$, no previous layer):
$$d_1[k]=A_m^k\cdot a[l_1][k]$$

**Answer:** $\displaystyle\sum_{k\ge1}d_n[k]\bmod p$

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n; long long m, p;
    cin >> n >> m >> p;
    vector<int> L(n);
    int smax = 0;
    for (int i = 0; i < n; ++i) { cin >> L[i]; smax = max(smax, L[i]); }

    // precompute A_m^k (falling factorial) and k!
    vector<int> Pm(smax + 1, 0), fact(smax + 1, 0);
    Pm[0] = 1 % p;
    for (int k = 1; k <= smax; ++k) {
        long long term = (m - (k - 1)) % p; if (term < 0) term += p;
        Pm[k] = (int)((1LL * Pm[k-1] * term) % p);
    }
    fact[0] = 1 % p;
    for (int k = 1; k <= smax; ++k)
        fact[k] = (int)((1LL * fact[k-1] * k) % p);

    // precompute a[s][k] (lower-triangular)
    vector<vector<int>> a(smax + 1);
    for (int s = 0; s <= smax; ++s) a[s].assign(s + 1, 0);
    if (smax >= 1) a[1][1] = 1 % p;
    for (int s = 2; s <= smax; ++s)
        for (int k = 1; k <= s; ++k) {
            long long v1 = a[s-1][k-1];
            long long v2 = (k <= s-1) ? 1LL * a[s-1][k] * (k - 1) : 0;
            a[s][k] = (int)((v1 + v2) % p);
        }

    // inter-layer DP
    vector<int> prev(smax + 1, 0), cur(smax + 1, 0);
    { // layer 1
        int s = L[0];
        for (int k = 1; k <= s; ++k)
            cur[k] = (int)(1LL * a[s][k] * Pm[k] % p);
        swap(prev, cur);
        fill(cur.begin(), cur.end(), 0);
    }
    for (int i = 2; i <= n; ++i) {
        int s = L[i-1];
        long long Sprev = 0;
        for (int k = 1; k < (int)prev.size(); ++k) {
            Sprev += prev[k]; if (Sprev >= p) Sprev -= p;
        }
        for (int k = 1; k <= s; ++k) {
            long long allSets = 1LL * Pm[k] * Sprev % p;
            long long sameSet = 1LL * fact[k] * prev[k] % p;
            long long coef = allSets - sameSet; if (coef < 0) coef += p;
            cur[k] = (int)(1LL * a[s][k] * coef % p);
        }
        swap(prev, cur);
        fill(cur.begin(), cur.end(), 0);
    }
    long long ans = 0;
    for (int k = 1; k <= smax; ++k) { ans += prev[k]; if (ans >= p) ans -= p; }
    cout << (ans % p) << '\n';
}
```

---

# 9 CCPC 2021 Online — Subpermutation

> **[Example — HDU 7133](https://vjudge.net/problem/HDU-7133)**
>
> List all $n$-element permutations in lexicographic order as one infinite sequence. Count how many contiguous substrings of this sequence equal some $m$-element permutation of $\{1,\ldots,m\}$. Output the answer mod $10^9+7$, $T$ test cases.
>
> ($T\le10^5$, $1\le m\le n\le10^6$)

> **How does `next_permutation` work in $O(n)$?**
>
> Given permutation $a_1\ldots a_n$ in lexicographic order:
> 1. Scan right-to-left for the last ascent: the largest $k$ with $a_k < a_{k+1}$. If none exists, this is the final permutation.
> 2. In the suffix $a_{k+1}\ldots a_n$, find the rightmost element $a_l$ just greater than $a_k$. Swap $a_k \leftrightarrow a_l$.
> 3. Reverse the suffix $a_{k+1}\ldots a_n$ (making it ascending).
>
> Example: $123645 \to$ last ascent at position of $4$ (since $4<5$), suffix $45$, swap $\to 123654$, reverse suffix $\to 123654$.

**Case 1 — $m$-permutation lies entirely within one $n$-permutation.**

- There are $m!$ permutations of $\{1,\ldots,m\}$.
- Treating the block as a unit, it plus the remaining $n-m$ elements gives $(n-m+1)!$ arrangements.
- Total: $m!\cdot(n-m+1)!$

**Case 2 — $m$-permutation straddles two consecutive $n$-permutations.**

Let $A=\{p_1,\ldots,p_{k-1},p_k,p_{k+1},\ldots,p_j,\ldots,p_n\}$ where $p_k<p_{k+1}$, suffix $[k+1,n]$ is descending, and $p_j$ is the rightmost element in that suffix greater than $p_k$. The next permutation is:

$$B=\{p_1,\ldots,p_{k-1},p_j,p_n,p_{n-1},\ldots,p_{j+1},p_k,p_{j-1},\ldots,p_{k+1}\}$$

Let the $m$-permutation start at position $i$; classify by $k$:

**(i) $i\le k$, $i+m-1>n$:**
- Arrangements of the $[n-m,n]$ portion: $(n-m)!$
- Arrangements of the $m$ values: $m!$ minus those where $[i,n]$ is fully descending, i.e. $\binom{m}{n-i+1}(m-n+i-1)!$

Count: $(n-m)!\bigl[m!-\binom{m}{n-i+1}(m-n+i-1)!\bigr]$ ... ①

**(ii) $i>k$, $n<i+m-1<j+n$:**
- (It can be shown $i+m-1\ge j$ is impossible: the $m$-permutation excludes $p_k$, and $p_j>p_k$ so $p_j$ cannot be in it either.)
- Among $(n-m)!$ arrangements of $[n-m,n]$, all but 1 have an ascent: $(n-m)!-1$ valid.
- The $m$ values in $B$ contribute: $\binom{m}{n-i+1}(m-n+i-1)!$

Count: $\bigl[(n-m)!-1\bigr]\binom{m}{n-i+1}(m-n+i-1)!$ ... ②

**Combining ① + ② and summing over $i=n-m+2$ to $n$:**
$$\text{Answer}=\sum_{i=n-m+2}^{n}\left[(n-m)!\cdot m!-\frac{m!}{(n-i+1)!}\right]$$

Substitute $j=n-i+1$:
$$=\sum_{j=1}^{m-1}\left[(n-m)!\cdot m!-\frac{m!}{j!}\right]$$

Precompute factorials and prefix sums to answer each query in $O(1)$.
