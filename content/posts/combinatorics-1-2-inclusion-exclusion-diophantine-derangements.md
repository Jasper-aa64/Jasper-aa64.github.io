---
title: "Combinatorics #1.2: Inclusion-Exclusion, Bounded Diophantine Equations, and Derangements"
date: 2026-04-20
slug: "combinatorics-1-2-inclusion-exclusion-diophantine-derangements"
description: "Inclusion-exclusion in set and operator form, equal-count subproblems, bounded Diophantine counting, derangements, Stirling numbers, and selected contest problems."
summary: "Inclusion-exclusion in set and operator form, equal-count subproblems, bounded Diophantine counting, derangements, Stirling numbers, and selected contest problems."
categories: [Combinatorics]
tags: [math, combinatorics, inclusion-exclusion, derangements, diophantine, stirling, counting, NTT]
math: true
toc: true
---

# 1 Inclusion-Exclusion Basics

## Set form

**Two sets.** Let $S$ be finite and $A, B \subseteq S$:
$$|S \setminus (A \cup B)| = |S| - |A| - |B| + |A \cap B|$$

**Three sets.**
$$|S \setminus (A \cup B \cup C)| = |S| - |A| - |B| - |C| + |A \cap B| + |A \cap C| + |B \cap C| - |A \cap B \cap C|$$

**General form.**
$$\left|S \setminus \bigcup_{i=1}^{n} A_i\right| = \sum_{i=0}^{n}(-1)^i \sum_{1 \le j_1 < \cdots < j_i \le n} \left|\bigcap_{k=1}^{i} A_{j_k}\right|$$

## Operator form

Let $a_1, \dots, a_n$ be $n$ properties on a finite set $S$. Define:

- $N(a_i)$ = number of elements having property $a_i$. Special case: $N(1) = |S|$.
- $N(1 - a_i)$ = number of elements **not** having property $a_i$.
- $N(a_{i_1} a_{i_2} \cdots a_{i_k})$ = number of elements having **all** of $a_{i_1}, \dots, a_{i_k}$.
- Linearity: $N(a \pm b) = N(a) \pm N(b)$.

**Basic formula** (elements with none of the properties):
$$N\!\bigl((1-a_1)(1-a_2)\cdots(1-a_n)\bigr) = \sum_{i=0}^{n}(-1)^i \sum_{1 \le j_1 < \cdots < j_i \le n} N(a_{j_1} \cdots a_{j_i})$$

**Generalised formula** (first $x$ properties required, next $n$ forbidden):
$$N\!\bigl(a_1\cdots a_x(1-a_{x+1})\cdots(1-a_{x+n})\bigr) = \sum_{i=0}^{n}(-1)^i \sum_{x < j_1 < \cdots < j_i \le x+n} N(a_1\cdots a_x\, a_{j_1}\cdots a_{j_i})$$

> **[Example 1]** Count integers in $\{1, \dots, n\}$ that are multiples of 5 but neither multiples of 2 nor of 3.
>
> Set $a_1$: multiple of 2; $a_2$: multiple of 3; $a_3$: multiple of 5.
> $$N\!\bigl((1-a_1)(1-a_2)\,a_3\bigr) = N(a_3) - N(a_1 a_3) - N(a_2 a_3) + N(a_1 a_2 a_3)$$
> $$= \left\lfloor\frac{n}{5}\right\rfloor - \left\lfloor\frac{n}{10}\right\rfloor - \left\lfloor\frac{n}{15}\right\rfloor + \left\lfloor\frac{n}{30}\right\rfloor$$

> **[Example 2 — Nowcoder 19857]** $N$ couples ($2N$ people) in a circle, rotations equivalent, mirrors distinct. Count arrangements where no couple is adjacent.
>
> Let $A_i$: couple $i$ is adjacent. When $i$ pairs are forced adjacent, merge each into a block (2 internal orderings → $2^i$); the circle has $2N-i$ objects with $(2N-i-1)!$ circular arrangements:
> $$\boxed{\text{Ans} = \sum_{i=0}^{N}(-1)^i \binom{N}{i} 2^i (2N-i-1)!}$$

---

# 2 Examples

## 2.1 Euler's Totient

**Claim.** Let $n = p_1^{\alpha_1} \cdots p_k^{\alpha_k}$. Then $\varphi(n) = n\!\left(1 - \tfrac{1}{p_1}\right)\!\cdots\!\left(1 - \tfrac{1}{p_k}\right)$.

**Setup.** $S = \{1, \dots, n\}$, property $a_i$: "$x$ is a multiple of $p_i$." We want $\varphi(n) = N\!\bigl((1-a_1)\cdots(1-a_k)\bigr)$.

**Intersection count.** For any $\{i_1, \dots, i_t\} \subseteq \{1, \dots, k\}$, multiples of $p_{i_1}\cdots p_{i_t}$ in $S$:
$$N(a_{i_1}\cdots a_{i_t}) = \frac{n}{p_{i_1}\cdots p_{i_t}}$$

**Apply inclusion-exclusion.**
$$\varphi(n) = \sum_{t=0}^{k}(-1)^t \sum_{1 \le i_1 < \cdots < i_t \le k} \frac{n}{p_{i_1}\cdots p_{i_t}} = n\left[1 - \sum_i \frac{1}{p_i} + \sum_{i<j}\frac{1}{p_i p_j} - \cdots\right]$$

**Recognise the bracket** as a product expansion:
$$\boxed{\prod_{i=1}^{k}\!\left(1 - \frac{1}{p_i}\right) = \sum_{S \subseteq \{1,\dots,k\}}(-1)^{|S|} \cdot \frac{1}{\prod_{i \in S} p_i}}$$

Hence $\boxed{\varphi(n) = n\prod_{i=1}^{k}\!\left(1 - \tfrac{1}{p_i}\right)}$.

---

# 3 Equal-Count Subproblems

The raw inclusion-exclusion sum runs over all $2^n$ subsets $T \subseteq [n]$:
$$N\!\left(\prod_{i=1}^n(1-A_i)\right) = \sum_{T \subseteq [n]}(-1)^{|T|} N\!\left(\prod_{i \in T} A_i\right)$$

**Key observation.** If $N(A_{i_1}\cdots A_{i_k})$ depends only on $k$ — the same value for every choice of $k$ indices — then all $\binom{n}{k}$ subsets of size $k$ contribute identically, and the $2^n$-term sum collapses to $n+1$ terms:
$$N\!\left(\prod_{i=1}^n(1-A_i)\right) = \sum_{k=0}^{n}(-1)^k \binom{n}{k} \cdot N(A_1 A_2 \cdots A_k)$$

> **[Example 1 — Surjections]**
>
> $m$ labeled objects into $n$ labeled people; everyone gets at least one.
>
> **Setup.** $|S| = n^m$. Property $a_i$: person $i$ gets nothing.
>
> **Intersection count.** Fix any $t$ people empty: each object has $n-t$ choices, so $N(a_{j_1}\cdots a_{j_t}) = (n-t)^m$. Depends only on $t$. ✓
>
> $$\boxed{\sum_{t=0}^{n}(-1)^t \binom{n}{t}(n-t)^m}$$
>
> Equals $n!\, S_2(m, n)$. Exactly $r$ people receive objects: $\binom{n}{r} r!\, S_2(m, r)$.

> **[Example 2 — No pair adjacent, linear]**
>
> $2n$ elements $a_1,\dots,a_n$ and $b_1,\dots,b_n$. Count permutations where no pair $(a_i, b_i)$ is adjacent.
>
> **Intersection count.** Force any $k$ pairs adjacent: merge into blocks ($2^k$ internal orderings), leaving $2n-k$ objects: $N(A_{i_1}\cdots A_{i_k}) = 2^k(2n-k)!$ Depends only on $k$. ✓
>
> $$\boxed{\sum_{k=0}^{n}(-1)^k \binom{n}{k} 2^k (2n-k)!}$$

---

# 4 Bounded Linear Diophantine Equations

Count integer solutions of $x_1 + \cdots + x_k = n$, $l_i \le x_i \le r_i$.

## 4.1 Inclusion-exclusion formula

Shift: $y_i = x_i - l_i$, $U_i = r_i - l_i$, $N = n - \sum l_i$. If $N < 0$ or $N > \sum U_i$, answer is 0. Otherwise count $\sum y_i = N$, $0 \le y_i \le U_i$.

Let $A_i$: $y_i \ge U_i + 1$. For subset $T$, let $M = N - \sum_{i \in T}(U_i+1)$; the term is 0 when $M < 0$.

$$\boxed{\# = \sum_{T \subseteq [k]} (-1)^{|T|} \binom{N - \sum_{i \in T}(U_i+1) + k-1}{k-1}}$$

Direct evaluation: $O(k \cdot 2^k)$.

## 4.2 Prefix-sum DP: $O(kN)$

$dp[i][s]$ = ways to make sum $s$ with first $i$ variables. With prefix sums $\text{pref}[t] = \sum_{u=0}^{t} dp[i-1][u]$:
$$dp[i][s] = \text{pref}[s] - \text{pref}[s - U_i - 1]$$

Answer is $dp[k][N]$ (mod $10^9+7$). If $N$ is too large for memory, use the NTT method.

```cpp
#include <bits/stdc++.h>
using namespace std;
const int MOD = 1000000007;
inline int add(int a, int b) { a += b; if (a >= MOD) a -= MOD; return a; }

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int k; long long n; cin >> k >> n;
    vector<long long> L(k), R(k);
    for (int i = 0; i < k; ++i) cin >> L[i] >> R[i];

    long long sumL = 0, sumU = 0;
    vector<long long> U64(k);
    for (int i = 0; i < k; ++i) {
        sumL += L[i];
        long long ui = R[i] - L[i];
        if (ui < 0) { cout << 0 << "\n"; return 0; }
        U64[i] = ui; sumU += ui;
    }
    long long N64 = n - sumL;
    if (N64 < 0 || N64 > sumU) { cout << 0 << "\n"; return 0; }
    int N = (int)N64;

    // clamp each U_i to N — anything larger never affects the DP
    vector<int> U(k);
    for (int i = 0; i < k; ++i) U[i] = (int)min(U64[i], N64);

    vector<int> prev(N+1, 0), cur(N+1, 0), pref(N+1, 0);
    prev[0] = 1; int reach = 0;
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
        for (int s = reach+1; s <= N; ++s) cur[s] = 0;
        swap(prev, cur);
    }
    cout << prev[N] << "\n";   // answer mod 10^9+7
}
```

## 4.3 Divide-and-conquer NTT — generating function method

Each variable $y_i \in [0, U_i]$ corresponds to $P_i(x) = 1 + x + \cdots + x^{U_i}$. Answer $= [x^N]\prod P_i(x)$.

Merge the $k$ polynomials with divide-and-conquer, truncating to degree $N$ at each step. Cost per node $v$: $O(d_v \log d_v)$ where $d_v \le N+1$. In the common case this is approximately $O(N \log N \log k)$; worst case $O(kN \log N)$.

Answer is mod $998244353$.

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MOD = 998244353, G = 3;

long long pw(long long a, long long b, long long mod = MOD) {
    long long r = 1; a %= mod;
    for (; b > 0; b >>= 1) { if (b & 1) r = r*a%mod; a = a*a%mod; }
    return r;
}

void ntt(vector<int>& a, bool inv) {
    int n = a.size();
    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) swap(a[i], a[j]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        long long w = inv ? pw(G, MOD-1-(MOD-1)/len) : pw(G, (MOD-1)/len);
        for (int i = 0; i < n; i += len) {
            long long wn = 1;
            for (int j = 0; j < len/2; ++j) {
                int u = a[i+j], v = (long long)a[i+j+len/2]*wn%MOD;
                a[i+j]       = u+v >= MOD ? u+v-MOD : u+v;
                a[i+j+len/2] = u-v <    0 ? u-v+MOD : u-v;
                wn = wn*w%MOD;
            }
        }
    }
    if (inv) { long long iv = pw(n, MOD-2); for (auto& x : a) x = (long long)x*iv%MOD; }
}

vector<int> conv_trunc(vector<int> A, vector<int> B, int lim) {
    if (A.empty() || B.empty()) return {};
    if ((int)A.size() > lim+1) A.resize(lim+1);
    if ((int)B.size() > lim+1) B.resize(lim+1);
    int need = (int)A.size()+(int)B.size()-1;
    int n = 1; while (n < need) n <<= 1;
    A.resize(n); B.resize(n);
    ntt(A, false); ntt(B, false);
    for (int i = 0; i < n; ++i) A[i] = (long long)A[i]*B[i]%MOD;
    ntt(A, true);
    A.resize(min(need, lim+1));
    return A;
}

vector<int> dc(vector<vector<int>>& polys, int l, int r, int N) {
    if (r-l == 1) return polys[l];
    int m = (l+r) >> 1;
    return conv_trunc(dc(polys, l, m, N), dc(polys, m, r, N), N);
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int k; long long n; cin >> k >> n;
    vector<long long> L(k), R(k);
    for (int i = 0; i < k; ++i) cin >> L[i] >> R[i];

    long long sumL = 0, sumU = 0;
    vector<long long> U64(k);
    for (int i = 0; i < k; ++i) {
        sumL += L[i];
        long long ui = R[i]-L[i];
        if (ui < 0) { cout << 0 << "\n"; return 0; }
        U64[i] = ui; sumU += ui;
    }
    long long N64 = n-sumL;
    if (N64 < 0 || N64 > sumU) { cout << 0 << "\n"; return 0; }
    int N = (int)N64;

    vector<vector<int>> polys(k);
    for (int i = 0; i < k; ++i) {
        int len = (int)min(U64[i], (long long)N)+1;
        polys[i].assign(len, 1);  // P_i(x) = 1 + x + ... + x^{min(U_i,N)}
    }
    auto res = dc(polys, 0, k, N);
    cout << (N < (int)res.size() ? res[N] : 0) << "\n";  // answer mod 998244353
}
```

## 4.4 Equal-cap case: $O\!\left(\min\!\left(n, \lfloor S/(k+1) \rfloor\right)\right)$

$n$ variables each in $[0, k]$, sum $= S$. By symmetry, inclusion-exclusion collapses to:

$$\boxed{g(n,S,k) = \sum_{i=0}^{\min(n,\lfloor S/(k+1)\rfloor)}(-1)^i \binom{n}{i} \binom{S-i(k+1)+n-1}{n-1}}$$

Terms with $S - i(k+1) < 0$ vanish. If $k \ge S$, the upper bound is never active: answer $= \binom{S+n-1}{n-1}$. If $S < 0$ or $S > nk$, answer is 0.

---

# 5 Derangements

A derangement is a permutation $p$ of $\{1,\dots,n\}$ with $p_i \ne i$ for all $i$. Count: $D(n)$.

## 5.1 Recurrence

$$D(0) = 1,\quad D(1) = 0,\quad D(n) = (n-1)\bigl(D(n-1)+D(n-2)\bigr)\quad(n \ge 2)$$

```cpp
D[0] = 1; D[1] = 0;
for (int i = 2; i <= MAXN; ++i)
    D[i] = 1LL*(i-1)*(D[i-1]+D[i-2])%MOD;
```

## 5.2 Inclusion-exclusion

$$D(n) = \sum_{k=0}^{n}(-1)^k \binom{n}{k}(n-k)! = \boxed{n!\sum_{k=0}^{n}\frac{(-1)^k}{k!}}$$

$D(n)/n! \to 1/e$ as $n \to \infty$.

## 5.3 EGF

Forbid 1-cycles: $\text{CYC}_{\ge2}(x) = -\ln(1-x) - x$.

$$\boxed{H(x) = \exp(\text{CYC}_{\ge2}(x)) = \frac{e^{-x}}{1-x}}$$

## 5.4 Binomial inversion

$$D(n) = \sum_{i=0}^{n}(-1)^{n-i}\binom{n}{i}i!$$

## 5.5 Exactly $k$ fixed points

**Problem.** Count permutations of $\{1,\dots,n\}$ with exactly $k$ positions satisfying $p_i = i$.

**Step 1 — choose the fixed positions:** $\binom{n}{k}$ ways.

**Step 2 — derange the remaining $n-k$ positions.** From the $n-k$ remaining, "accidentally" fix $i$ more:
$$N\!\Bigl(\prod_j(1-A_j)\Bigr) = \sum_{i=0}^{n-k}(-1)^i\binom{n-k}{i}(n-(k+i))!$$

**Combining:**
$$\binom{n}{k}\sum_{i=0}^{n-k}(-1)^i\binom{n-k}{i}(n-(k+i))!$$

The inner sum is exactly $D_{n-k}$, so:

$$\boxed{\binom{n}{k}\,D_{n-k}}$$

---

# 6 Stirling Numbers of the Second Kind — Preview

$S_2(n,k)$ (also $\begin{Bmatrix}n\\\\k\end{Bmatrix}$): $n$ distinct balls into $k$ indistinguishable non-empty boxes.

**Recurrence.**
$$S_2(n,k) = \underbrace{S_2(n-1,k-1)}_{\text{ball }n\text{ opens a new box}} + \underbrace{k\cdot S_2(n-1,k)}_{\text{ball }n\text{ joins an existing box}}$$

**Closed form.**
$$S_2(n,k) = \frac{1}{k!}\sum_{i=0}^{k}(-1)^i\binom{k}{i}(k-i)^n$$

**Falling factorial expansion.**
$$x^n = \sum_{k=0}^{n}S_2(n,k)\,x^{\underline{k}}, \qquad x^{\underline{k}} = x(x-1)\cdots(x-k+1) = \frac{x!}{(x-k)!}$$

**Surjections** into $k$ labeled boxes: $k!\,S_2(n,k)$.

---

# 7 Selected Problems

## 7.1 Nowcoder 16513 — integers coprime to a prime set

Given a set $A = \{a_1,\dots,a_k\}$ of primes ($k \le 20$, $a_i \le 100$), count integers in $[L,R]$ not divisible by any $a_i$. ($L, R \le 10^{18}$)

**Reduction.** Count on $[1,X]$ and subtract: Answer $= F(R) - F(L-1)$.

**Key fact.** Multiples of $d$ in $[L, R]$:
$$\left\lfloor\frac{R}{d}\right\rfloor - \left\lfloor\frac{L-1}{d}\right\rfloor$$
This is the standard $[L,R] \to [1,R]$ minus $[1,L-1]$ trick.

**Inclusion-exclusion** over subsets $S \subseteq A$:
$$F(X) = \sum_{S \subseteq A}(-1)^{|S|}\left\lfloor\frac{X}{\prod_{a \in S}a}\right\rfloor$$

Since all $a_i$ are prime, $\prod_{a \in S}a = \text{lcm}(S)$. Prune when product $> X$. Complexity: $O(2^k)$.

## 7.2 CF 547C — Mike and Foam (dynamic coprime pairs)

$n$ beer glasses with heights $a_1,\dots,a_n$. Counter starts empty. $q$ operations: each places a glass on or removes one from the counter. After each operation output the number of pairs $(i,j)$ ($i < j$) on the counter with $\gcd(a_i, a_j) = 1$.

($1 \le n, q \le 2\times10^5$; $1 \le a_i \le 5\times10^5$)

**Problem restatement.** Maintain multiset $S$; after each insert/delete of $v$, count how many $y \in S$ satisfy $\gcd(y, v) = 1$. Direct loop is $O(|S|\log v)$ — too slow.

### Key data structure

Maintain $\text{cnt}[d]$ = elements in $S$ divisible by $d$, and running answer $\text{ans}$.

For any $v$ with distinct prime factors $p_1,\dots,p_m$, the number of elements in $S$ coprime to $v$ is:
$$\Delta = \sum_{T \subseteq \{p_1,\dots,p_m\}}(-1)^{|T|}\,\text{cnt}\!\left[\prod_{i \in T}p_i\right] = \sum_{d \mid v}\mu(d)\,\text{cnt}[d]$$

(only squarefree $d$ matter; $\mu(d) = (-1)^{|T|}$ for squarefree $d$).

### Insert vs Delete — order matters

**Insert $v$:** compute $\Delta$ with current $\text{cnt}$, then `ans += Δ`, then `cnt[d]++` for all squarefree divisors $d$ of $v$.

**Delete $v$:** `cnt[d]--` first (remove $v$), then compute $\Delta$, then `ans -= Δ`.

This ensures $v$ is never counted against itself.

### Complexity

$O(2^{\omega(v)})$ per op; $\omega(v) \le 7$ for $v \le 5\times10^5$, so at most 128 entries touched per op. Sieve Möbius in $O(V\log\log V)$.

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MAXV = 500001;
int mu[MAXV], cnt[MAXV];

void sieve() {
    vector<int> primes;
    vector<bool> composite(MAXV, false);
    mu[1] = 1;
    for (int i = 2; i < MAXV; ++i) {
        if (!composite[i]) { primes.push_back(i); mu[i] = -1; }
        for (int p : primes) {
            if ((long long)i*p >= MAXV) break;
            composite[i*p] = true;
            if (i % p == 0) { mu[i*p] = 0; break; }
            mu[i*p] = -mu[i];
        }
    }
}

vector<int> sqfree_divs(int v) {
    vector<int> ps;
    for (int p = 2; (long long)p*p <= v; ++p)
        if (v % p == 0) { ps.push_back(p); while (v % p == 0) v /= p; }
    if (v > 1) ps.push_back(v);
    int m = ps.size();
    vector<int> divs; divs.reserve(1 << m);
    for (int mask = 0; mask < (1 << m); ++mask) {
        int d = 1;
        for (int i = 0; i < m; ++i) if (mask >> i & 1) d *= ps[i];
        divs.push_back(d);
    }
    return divs;
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    sieve();
    int n; cin >> n;
    vector<int> a(n+1);
    for (int i = 1; i <= n; ++i) cin >> a[i];

    int q; cin >> q;
    vector<bool> on(n+1, false);
    long long ans = 0;
    while (q--) {
        int idx; cin >> idx;
        int v = a[idx];
        auto divs = sqfree_divs(v);
        if (!on[idx]) {                          // insert
            for (int d : divs) ans += mu[d]*cnt[d];
            for (int d : divs) cnt[d]++;
        } else {                                 // delete
            for (int d : divs) cnt[d]--;
            for (int d : divs) ans -= mu[d]*cnt[d];
        }
        on[idx] = !on[idx];
        cout << ans << "\n";
    }
}
```
