---
title: "Combinatorics #1.2: Inclusion-Exclusion, Bounded Diophantine Equations, and Derangements"
date: 2026-04-20
slug: "combinatorics-1-2-inclusion-exclusion-diophantine-derangements"
description: "Inclusion-exclusion in set and operator form, bounded Diophantine counting with prefix-sum DP and divide-and-conquer NTT, derangement formulas, and Stirling numbers."
summary: "Inclusion-exclusion in set and operator form, bounded Diophantine counting with prefix-sum DP and divide-and-conquer NTT, derangement formulas, and Stirling numbers."
categories: [Combinatorics]
tags: [math, combinatorics, inclusion-exclusion, derangements, diophantine, stirling, counting, NTT]
math: true
toc: true
---

This note collects the standard counting templates that appear most often in contest problems:

- inclusion-exclusion in both set form and operator form
- onto-function and adjacency-avoidance counting
- bounded linear Diophantine equations (inclusion-exclusion, prefix-sum DP, divide-and-conquer NTT, equal-cap formula)
- derangements and fixed-point counting
- Stirling numbers of the second kind

# 1 Inclusion-Exclusion Basics

## Set form

**Two sets.** Let $S$ be a finite set and $A, B \subseteq S$. Then

$$|S \setminus (A \cup B)| = |S| - |A| - |B| + |A \cap B|$$

**Three sets.** For $A, B, C \subseteq S$,

$$|S \setminus (A \cup B \cup C)| = |S| - |A| - |B| - |C| + |A \cap B| + |A \cap C| + |B \cap C| - |A \cap B \cap C|$$

**General form.** For subsets $A_1, \dots, A_n \subseteq S$,

$$\left|S \setminus \bigcup_{i=1}^{n} A_i\right| = \sum_{T \subseteq [n]} (-1)^{|T|} \left|\bigcap_{i \in T} A_i\right|$$

where the empty-intersection term equals $|S|$.

## Operator form

Let $A_i$ denote a "bad property," and $N(A_{i_1} A_{i_2} \cdots)$ the number of elements with all listed properties. Then

$$N\!\left(\prod_{i=1}^{n}(1 - A_i)\right) = \sum_{T \subseteq [n]} (-1)^{|T|} N\!\left(\prod_{i \in T} A_i\right)$$

This algebraic form is convenient for deriving formulas: expand the product, collect signs, identify $N(\cdots)$ for each intersection.

# 2 Classic Examples

## 2.1 Euler's totient

Let $n = p_1^{\alpha_1} \cdots p_k^{\alpha_k}$. Then

$$\varphi(n) = n \prod_{i=1}^{k}\left(1 - \frac{1}{p_i}\right)$$

Set $S = \{1, \dots, n\}$ and $A_i = \{x \in S : p_i \mid x\}$. For any index set $T$,

$$\left|\bigcap_{i \in T} A_i\right| = \frac{n}{\prod_{i \in T} p_i}$$

because every $p_i$ divides $n$. Inclusion-exclusion expands directly into the product formula.

## 2.2 Couples in a circular arrangement

**Problem.** $2N$ people ($N$ couples) are arranged in a circle. Two arrangements are the same if one is a rotation of the other (mirror flips are distinct). Count arrangements where no couple is adjacent.

Let $A_i$ = couple $i$ is adjacent. If $i$ couples are forced adjacent, each becomes a block (2 internal orderings), and the circle has $2N - i$ objects with $(2N - i - 1)!$ circular arrangements.

$$\boxed{\text{Ans} = \sum_{i=0}^{N} (-1)^i \binom{N}{i} 2^i (2N - i - 1)!}$$

## 2.3 Surjections: every person gets at least one item

Distribute $m$ labeled objects among $n$ labeled people, every person receiving at least one. Let $A_i$ = person $i$ gets nothing. Then $|S| = n^m$ and forcing $t$ people empty leaves each object $(n-t)$ choices, giving

$$\boxed{\sum_{t=0}^{n} (-1)^t \binom{n}{t} (n-t)^m}$$

This equals $n!\, S_2(m, n)$ where $S_2$ is the Stirling number of the second kind.

## 2.4 No paired elements are adjacent (linear)

$2n$ elements $a_1, \dots, a_n, b_1, \dots, b_n$. Count permutations where no pair $(a_i, b_i)$ is adjacent. Forcing $k$ pairs adjacent merges each into a block (2 internal orders), leaving $2n - k$ objects.

$$|A_{i_1} \cap \cdots \cap A_{i_k}| = 2^k (2n - k)!$$

$$\boxed{\sum_{k=0}^{n} (-1)^k \binom{n}{k} 2^k (2n - k)!}$$

# 3 Bounded Linear Diophantine Equations

Count integer solutions of

$$x_1 + x_2 + \cdots + x_k = n, \qquad l_i \le x_i \le r_i$$

## 3.1 Inclusion-exclusion formula

**Step 1: remove lower bounds.** Set $y_i = x_i - l_i$, $U_i = r_i - l_i$, $N = n - \sum l_i$. The problem becomes $\sum y_i = N$, $0 \le y_i \le U_i$. If $N < 0$ or $N > \sum U_i$, answer is $0$.

**Step 2: apply inclusion-exclusion.** Let $A_i$ = $y_i \ge U_i + 1$.

$$\# = \sum_{T \subseteq [k]} (-1)^{|T|} \binom{N - \sum_{i \in T}(U_i + 1) + k - 1}{k - 1}$$

In the original variables:

$$\# = \sum_{T \subseteq [k]} (-1)^{|T|} \binom{n - \sum_{i=1}^{k} l_i - \sum_{i \in T}(r_i - l_i + 1) + k - 1}{k - 1}$$

Direct subset enumeration costs $O(k \cdot 2^k)$.

## 3.2 Prefix-sum DP: $O(kN)$

Let $dp[i][s]$ = number of ways to use the first $i$ variables to reach sum $s$. Naively:

$$dp[i][s] = \sum_{x=0}^{\min(U_i, s)} dp[i-1][s-x]$$

With prefix sums $\text{pref}[t] = \sum_{u=0}^{t} dp[i-1][u]$, this becomes $O(1)$ per state:

$$dp[i][s] = \text{pref}[s] - \text{pref}[s - U_i - 1]$$

(with $\text{pref}[-1] = 0$). Total complexity: $O(kN)$, space $O(N)$ with rolling arrays.

```cpp
#include <bits/stdc++.h>
using namespace std;
const int MOD = 1000000007;
inline int add(int a, int b) { a += b; if (a >= MOD) a -= MOD; return a; }

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int k; long long n;
    cin >> k >> n;
    vector<long long> L(k), R(k);
    for (int i = 0; i < k; ++i) cin >> L[i] >> R[i];

    long long sumL = 0, sumU = 0;
    vector<int> U(k);
    for (int i = 0; i < k; ++i) {
        sumL += L[i];
        long long ui = R[i] - L[i];
        if (ui < 0) { cout << 0 << "\n"; return 0; }
        U[i] = (int)ui; sumU += ui;
    }
    long long N64 = n - sumL;
    if (N64 < 0 || N64 > sumU) { cout << 0 << "\n"; return 0; }
    int N = (int)N64;

    vector<int> prev(N + 1, 0), cur(N + 1, 0), pref(N + 1, 0);
    prev[0] = 1;
    int reach = 0;
    for (int i = 0; i < k; ++i) {
        reach = min(N, reach + U[i]);
        int run = 0;
        for (int s = 0; s <= reach; ++s) { run = add(run, prev[s]); pref[s] = run; }
        for (int s = 0; s <= reach; ++s) {
            int left = s - U[i] - 1;
            int val = pref[s];
            if (left >= 0) { val -= pref[left]; if (val < 0) val += MOD; }
            cur[s] = val;
        }
        for (int s = reach + 1; s <= N; ++s) cur[s] = 0;
        swap(prev, cur);
    }
    cout << prev[N] << "\n";
    return 0;
}
```

## 3.3 Divide-and-conquer NTT: $O(N \log N \log k)$

Each variable $y_i \in [0, U_i]$ corresponds to the polynomial $P_i(x) = 1 + x + \cdots + x^{U_i}$. The answer is the coefficient of $x^N$ in $\prod_{i=1}^{k} P_i(x)$.

Merge the $k$ polynomials with divide-and-conquer, truncating to degree $N$ at each step. Each level does $O(N \log N)$ work via NTT, and there are $\log k$ levels.

```cpp
// Truncated convolution: C = (A * B) kept to degree lim
vector<int> conv_trunc(vector<int> A, vector<int> B, int lim) {
    if (A.empty() || B.empty()) return {};
    if ((int)A.size() > lim + 1) A.resize(lim + 1);
    if ((int)B.size() > lim + 1) B.resize(lim + 1);
    int need = (int)A.size() + (int)B.size() - 1;
    int n = 1; while (n < need) n <<= 1;
    A.resize(n); B.resize(n);
    ntt(A, false); ntt(B, false);
    for (int i = 0; i < n; ++i) A[i] = (int)(1LL * A[i] * B[i] % MOD);
    ntt(A, true);
    A.resize(min(need, lim + 1));
    return A;
}

// Divide-and-conquer merge of polys[l..r)
vector<int> multiply_range(vector<vector<int>>& polys, int l, int r, int N) {
    if (r - l == 1) return polys[l];
    int m = (l + r) >> 1;
    auto L = multiply_range(polys, l, m, N);
    auto R = multiply_range(polys, m, r, N);
    return conv_trunc(L, R, N);
}
```

Build each $P_i$ as `vector<int>(min(U[i],N)+1, 1)` and call `multiply_range`. Extract `prod[N]`.

## 3.4 Equal-cap case: all upper bounds are $k$, complexity $O(S/k)$

Count ordered non-negative integer solutions of $x_1 + \cdots + x_n = S$ with each $x_j \le k$.

Without upper bounds the answer is $\binom{S + n - 1}{n - 1}$ (stars and bars). Applying inclusion-exclusion on the $i$ variables that exceed $k$:

$$g(n, S, k) = \sum_{i=0}^{\lfloor S/(k+1) \rfloor} (-1)^i \binom{n}{i} \binom{S - i(k+1) + n - 1}{n - 1}$$

The sum has only $\lfloor S/(k+1) \rfloor + 1$ terms because $\binom{S-i(k+1)+n-1}{n-1} = 0$ once $S - i(k+1) < 0$. This gives $O(S/k)$ time.

If $k \ge S$ no variable can exceed $S$, so the upper bound is vacuous and the answer is simply $\binom{S+n-1}{n-1}$.

# 4 Derangements

A derangement is a permutation $p$ of $\{1, \dots, n\}$ with $p_i \ne i$ for all $i$. Denote the count by $D(n)$.

## 4.1 Recurrence

$$D(0) = 1, \quad D(1) = 0, \quad D(n) = (n-1)\bigl(D(n-1) + D(n-2)\bigr) \quad (n \ge 2)$$

```cpp
D[0] = 1; D[1] = 0;
for (int i = 2; i <= MAXN; ++i)
    D[i] = 1LL * (i - 1) * (D[i - 1] + D[i - 2]) % MOD;
```

## 4.2 Inclusion-exclusion formula

Let $A_i$ = position $i$ is fixed. Then

$$D(n) = \left|S \setminus \bigcup_{i=1}^{n} A_i\right| = \sum_{k=0}^{n} (-1)^k \binom{n}{k}(n-k)!$$

$$\boxed{D(n) = n! \sum_{k=0}^{n} \frac{(-1)^k}{k!}}$$

As $n \to \infty$, $D(n)/n! \to 1/e$.

## 4.3 Exponential generating function

Every permutation is a set of disjoint cycles. The EGF of all cycles is

$$\text{CYC}(x) = \sum_{k \ge 1} \frac{x^k}{k} = -\ln(1 - x)$$

Forbidding 1-cycles:

$$\text{CYC}_{\ge 2}(x) = -\ln(1 - x) - x$$

The EGF of derangements is

$$\boxed{H(x) = \exp\!\bigl(\text{CYC}_{\ge 2}(x)\bigr) = \frac{e^{-x}}{1 - x}}$$

Expanding $H(x) = e^{-x} \cdot \frac{1}{1-x}$ and extracting $[x^n]$ recovers the inclusion-exclusion formula.

## 4.4 Binomial inversion

Let $f_n$ = derangements of $[n]$ (exactly 0 fixed points), $g_n = n!$ (all permutations = at most all fixed). By binomial inversion:

$$f_n = \sum_{i=0}^{n} \binom{n}{i} (-1)^{n-i} i! = \sum_{i=0}^{n} (-1)^{n-i} \frac{n!}{(n-i)!}$$

This agrees with the inclusion-exclusion formula above and is another $O(n)$ computation.

## 4.5 Exactly $k$ fixed points

Choose which $k$ positions are fixed ($\binom{n}{k}$ ways), then derange the remaining $n - k$:

$$\boxed{\binom{n}{k} D(n - k)}$$

# 5 Stirling Numbers of the Second Kind

$S_2(n, k)$ (also written $\left\{\begin{smallmatrix}n\\k\end{smallmatrix}\right\}$) counts ways to partition $n$ labeled objects into $k$ non-empty, unlabeled groups.

**Recurrence:**

$$S_2(n, k) = k \cdot S_2(n-1, k) + S_2(n-1, k-1)$$

(the $n$-th object either joins one of the existing $k$ groups, or starts a new group of its own).

**Explicit formula:**

$$S_2(n, k) = \frac{1}{k!} \sum_{i=0}^{k} (-1)^i \binom{k}{i} (k - i)^n$$

**Connection to surjections:** distributing $n$ labeled objects into $k$ labeled non-empty boxes gives $k!\, S_2(n, k)$.

**Falling factorial expansion:**

$$x^n = \sum_{k=0}^{n} S_2(n, k)\, x^{\underline{k}}$$

where $x^{\underline{k}} = x(x-1)(x-2)\cdots(x-k+1)$ is the $k$-th falling factorial of $x$.

# 6 Selected Problems

## 6.1 Integers in $[L, R]$ coprime to a prime set

**Problem (Nowcoder 16513).** Given a set $A = \{a_1, \dots, a_k\}$ of primes, count integers in $[L, R]$ not divisible by any $a_i$.

Define $F(X) = \#\{1 \le n \le X : \forall a \in A,\ a \nmid n\}$. By inclusion-exclusion over subsets $S \subseteq A$:

$$F(X) = \sum_{S \subseteq A} (-1)^{|S|} \left\lfloor \frac{X}{\prod_{a \in S} a} \right\rfloor$$

Answer: $F(R) - F(L - 1)$. Complexity: $O(2^k)$ per query (prune when $\prod > X$).

## 6.2 Dynamic coprime pair counting

**Problem (CF 547C).** Maintain a multiset $S$ under insertions and deletions. After each operation, output the number of pairs $(i, j)$ with $i < j$ and $\gcd(a_i, a_j) = 1$.

**Method 1 — Inclusion-exclusion.** Maintain $\text{cnt}[d]$ = number of elements in $S$ divisible by $d$. When inserting value $v$ with prime factorization $\{p_1, \dots, p_m\}$, the number of existing elements coprime to $v$ is

$$\sum_{S \subseteq \{p_1,\dots,p_m\}} (-1)^{|S|} \text{cnt}\!\left[\prod_{p \in S} p\right]$$

Update $\text{cnt}[d]$ for all $2^m$ squarefree divisors of $v$ after computing the delta. Deletion is symmetric: update $\text{cnt}$ first, then compute the delta.

**Method 2 — Möbius inversion.**

$$\sum_{y \in S} \mathbf{1}[\gcd(v, y) = 1] = \sum_{d \mid v} \mu(d) \cdot \#\{y \in S : d \mid y\} = \sum_{d \mid v} \mu(d)\, \text{cnt}[d]$$

Both methods run in $O(2^{\omega(v)})$ per query where $\omega(v) \le 7$ for $v \le 5 \times 10^5$.
