---
title: "Combinatorics #0: Common Formulae & Conclusions"
date: 2026-04-20
categories: [Combinatorics]
tags: [math, combinatorics, floor-sum, xor, fibonacci, perfect-squares]
math: true
---

# 1 Geometric Series Sum

First term $a_1$, common ratio $q$, sum of first $n$ terms $S_n$:
- $q = 1$: $S_n = n a_1$
- $q \neq 1$: $S_n = \dfrac{a_1(1 - q^n)}{1 - q}$

---

# 2 Floor Sum Algorithm (Euclidean-like 类欧几里得)

## Basic form — $O(\log \max\{a,b,m\})$

$$\sum_{i=0}^{n-1}\left\lfloor\frac{a \cdot i+b}{m}\right\rfloor, \quad n,m,a,b > 0$$

```cpp
LL F(LL n, LL m, LL a, LL b) {
    if (a == 0) return n * (b / m);
    if (b >= m) return n * (b / m) + F(n, a, b % m, m);
    if (a >= m) return (n - 1) * n / 2 * (a / m) + F(n, a % m, b, m);
    return F((a * n + b) / m, m, (a * n + b) % m, a);
}
```

## General form — allows negative $a, b$;  requires $n \geq 0, m > 0$

```cpp
ll F_all(ll n, ll m, ll a, ll b) {
    auto floordiv = [&](ll x, ll m) {
        if (x >= 0) return x / m;
        return -( (-x + m - 1) / m );
    };
    ll ans = 0;
    if (a < 0 || a >= m) { ll q = floordiv(a, m); ans += q * n * (n - 1) / 2; a -= q * m; }
    if (b < 0 || b >= m) { ll q = floordiv(b, m); ans += q * n; b -= q * m; }
    // now 0 <= a, b < m — use non-negative version
    while (true) {
        if (a >= m) { ans += (n - 1) * n / 2 * (a / m); a %= m; }
        if (b >= m) { ans += n * (b / m); b %= m; }
        ll y_max = a * n + b;
        if (y_max < m) break;
        n = y_max / m; b = y_max % m; swap(a, m);
    }
    return ans;
}
```

## 2.1 Template problem — [Luogu P5170](https://www.luogu.com.cn/problem/P5170)

Given $n, a, b, c$, compute $\sum_{i=0}^{n} \lfloor\frac{ai+b}{c}\rfloor$, $\sum_{i=0}^{n} \lfloor\frac{ai+b}{c}\rfloor^2$, $\sum_{i=0}^{n} i\lfloor\frac{ai+b}{c}\rfloor$ mod $998244353$.

**Universal Euclidean algorithm:**

```cpp
#include <iostream>
template <typename T> T pow(T a, int b) {
    T res; for (; b; b >>= 1) { if (b & 1) res = res * a; a = a * a; } return res;
}
template <typename T> T euclid(int a, int b, int c, int n, T U, T R) {
    if (b >= c) return pow(U, b / c) * euclid(a, b % c, c, n, U, R);
    if (a >= c) return euclid(a % c, b, c, n, U, pow(U, a / c) * R);
    auto m = ((long long)a * n + b) / c;
    if (!m) return pow(R, n);
    return pow(R, (c - b - 1) / a) * U *
           euclid(c, (c - b - 1) % a, a, m - 1, R, U) *
           pow(R, n - (c * m - b - 1) / a);
}
constexpr int M = 998244353;
struct Info {
    long long x, y, s, t, u;
    Info() : x(0), y(0), s(0), t(0), u(0) {}
    Info operator*(const Info& rhs) const {
        Info res;
        res.x = (x + rhs.x) % M;
        res.y = (y + rhs.y) % M;
        res.s = (s + rhs.s + rhs.x * y) % M;
        auto tmp = (rhs.x * (rhs.x + 1) / 2 + x * rhs.x) % M;
        res.t = (t + rhs.t + x * rhs.s + tmp * y) % M;
        res.u = (u + rhs.u + 2 * y * rhs.s + rhs.x * y % M * y) % M;
        return res;
    }
};
void solve(int a, int b, int c, int n) {
    Info U, R; U.y = 1; R.x = 1;
    auto res = euclid(a, b, c, n, U, R);
    std::cout << (res.s + b / c) % M << ' ' << (res.u + (long long)(b/c)*(b/c)) % M << ' ' << res.t << '\n';
}
int main() {
    int t; std::cin >> t;
    for (; t; --t) { int a, b, c, n; std::cin >> n >> a >> b >> c; solve(a, b, c, n); }
}
```

## 2.2 Example — [2025 ICPC Wuhan A. Planting Trees](https://qoj.ac/contest/2609/problem/14719)

**Problem:** Two plants start at heights $x, y$. Each day they grow by $f$ and $g$ respectively, then height is taken mod $m$.  
Count days where the first plant is shorter ($L_t < R_t$).

$$L_t = (x + ft) \bmod m, \quad R_t = (y + gt) \bmod m, \quad \text{Ans} = \sum_{t=0}^{n-1} [L_t < R_t]$$

**Key trick — convert $[u < v]$ to a floor sum:**

For any $0 \leq u, v < m$:

$$[u < v] = 1 + \left\lfloor\frac{(v-1) - u}{m}\right\rfloor \tag{1}$$

*Proof:* $(v-1)-u \in [-m, m-1]$. If $u < v$: value $\in [0, m-1)$, floor = 0, RHS = 1. If $u \geq v$: value $\in [-m,-1]$, floor = $-1$, RHS = 0. ✓

Apply (1) with $u = L_t,\ v = R_t$:

$$[L_t < R_t] = 1 + \left\lfloor\frac{R_t - 1 - L_t}{m}\right\rfloor \tag{2}$$

Expand $L_t, R_t$ by **writing mod as "original minus $m\lfloor\cdot\rfloor$":**

$$L_t = ft + x - m\left\lfloor\frac{ft+x}{m}\right\rfloor, \qquad R_t = gt + y - m\left\lfloor\frac{gt+y}{m}\right\rfloor$$

Substitute into the numerator of (2):

$$R_t - 1 - L_t = (g-f)t + (y-x-1) - m\left(\left\lfloor\frac{gt+y}{m}\right\rfloor - \left\lfloor\frac{ft+x}{m}\right\rfloor\right)$$

Divide by $m$ and take floor (the $m\lfloor\cdot\rfloor/m$ terms are already integers, so they pass through the floor unchanged):

$$\left\lfloor\frac{R_t-1-L_t}{m}\right\rfloor = \left\lfloor\frac{(g-f)t+(y-x-1)}{m}\right\rfloor - \left\lfloor\frac{gt+y}{m}\right\rfloor + \left\lfloor\frac{ft+x}{m}\right\rfloor$$

So (2) becomes:

$$[L_t < R_t] = 1 + \left\lfloor\frac{(g-f)t+(y-x-1)}{m}\right\rfloor - \left\lfloor\frac{gt+y}{m}\right\rfloor + \left\lfloor\frac{ft+x}{m}\right\rfloor \tag{3}$$

Sum (3) over $t = 0,\dots,n-1$, letting $F(n,m,a,b) = \sum_{t=0}^{n-1}\left\lfloor\frac{at+b}{m}\right\rfloor$:

$$\boxed{\text{Ans} = n + F(n,m,g-f,\,y-x-1) - F(n,m,g,\,y) + F(n,m,f,\,x)}$$

```cpp
void solve() {
    ll f, x, g, y, n, M; cin >> f >> x >> g >> y >> n >> M;
    ll ans = n + F_all(n, M, g-f, y-x-1) - F_all(n, M, g, y) + F_all(n, M, f, x);
    cout << ans << "\n";
}
```

---

# 3 XOR Kingdom

## 3.1 XOR ↔ Addition

$$x + y = (x \oplus y) + 2 \cdot (x \mathbin{\&} y)$$

- **XOR** = addition without carry
- **AND** = exactly which bits carry

## 3.2 Basic Properties

1. Commutative & associative: `a^b = b^a`, `(a^b)^c = a^(b^c)` — bits are independent.
2. Identity & self-inverse: `a^0 = a`, `a^a = 0`.
3. ⭐ Invertible: if `a^b = c` then `a = b^c`.
4. Each bit is $\bmod 2$ addition (no carry).
5. **Prefix XOR of $1..n$** has period 4:

| $n \bmod 4$ | `1^2^...^n` |
|---|---|
| 0 | `n` |
| 1 | `1` |
| 2 | `n+1` |
| 3 | `0` |

## 3.3 Common Conclusions

1. **Subarray XOR via prefix XOR**  
   Let `pref[i] = a[1]^...^a[i]`. Then XOR of `a[l..r]` = `pref[r] ^ pref[l-1]`.
   - **Count subarrays with XOR = K:** prefix XOR + hashmap.
   ```cpp
   ll countXorSubarrays(vector<int>& a, int K) {
       unordered_map<int,int> cnt; cnt[0] = 1;
       int pref = 0; ll ans = 0;
       for (int x : a) { pref ^= x; ans += cnt[pref ^ K]; cnt[pref]++; }
       return ans;
   }
   ```

2. **Subset XOR and linear algebra**  
   Each number is a bit-vector; XOR is vector addition over $GF(2)$. → **Linear basis.**

3. **Maximum XOR pair / maximum subset XOR**
   - Max `ai ^ aj`: 01-Trie, greedy from highest bit. $O(n \log A)$.
   - Max XOR of subset / linear combination: linear basis, greedy from high bit.

4. **Count pairs with XOR < K**  
   01-Trie with subtree sizes; for each prefix query how many stored prefixes $p$ satisfy `(pref[i]^p) < K`. $O(n \log A)$.

5. **XOR convolution**  
   FWT in $O(N \log N)$ on frequency vectors of size $N = 2^m$.

6. **Bit divide-and-conquer**  
   For counting/minimisation, split on highest bit, recurse, count cross contributions.

### 3.3.1 Trie Templates

**Max XOR pair:**
```cpp
struct Trie { int ch[2]; Trie(){ ch[0]=ch[1]=-1; } };
vector<Trie> T;
void insert(int x) {
    int p = 0;
    for (int b = 30; b >= 0; --b) {
        int bit = (x >> b) & 1;
        if (T[p].ch[bit] == -1) { T[p].ch[bit] = T.size(); T.emplace_back(); }
        p = T[p].ch[bit];
    }
}
int queryMaxXor(int x) {
    int p = 0, res = 0;
    for (int b = 30; b >= 0; --b) {
        int bit = (x >> b) & 1, want = bit ^ 1;
        if (T[p].ch[want] != -1) { res |= (1 << b); p = T[p].ch[want]; }
        else p = T[p].ch[bit];
    }
    return res;
}
```

**Count XOR pairs < K:** maintain subtree size `sz` at each Trie node; at each bit, if taking the "same" branch keeps XOR smaller, add the whole opposite subtree count.

## 3.4 Linear Basis Merge

- Classic application: $k$-th minimum XOR value (use basis + greedy / divide-and-conquer + count).

---

# 4 Fibonacci

## Sum formula

$$S(n) = \sum_{i=1}^{n} F_i = F_{n+2} - 1$$

*Proof:* $F_k = F_{k+2} - F_{k+1}$; telescoping sum from $k=1$ to $n$ gives $F_{n+2} - F_2 = F_{n+2} - 1$.

## 4.1 Fast Doubling — $O(\log n)$

Given $a = F_k$, $b = F_{k+1}$:

$$F_{2k} = a(2b - a), \qquad F_{2k+1} = a^2 + b^2$$

```cpp
pair<long long,long long> fib_pair(long long n, long long mod) {
    if (n == 0) return {0, 1};
    auto [a, b] = fib_pair(n >> 1, mod);
    long long c = (__int128)a * ((2*b - a % mod + mod) % mod) % mod;
    long long d = ((__int128)a*a + (__int128)b*b) % mod;
    return (n & 1) ? make_pair(d, (c + d) % mod) : make_pair(c, d);
}

// Usage: sum F(1)+...+F(n) = F(n+2) - 1
long long fibSum(long long n, long long MOD) {
    auto [f, _] = fib_pair(n + 2, MOD);
    return (f - 1 + MOD) % MOD;
}
```

## 4.2 Number of digits of $F_n$

$$\text{digits}(F_n) = \left\lfloor n \log_{10} \varphi - \tfrac{1}{2}\log_{10} 5 \right\rfloor + 1$$

```cpp
long long fib_digits(long long n, double base = 10.0) {
    if (n <= 1) return 1;
    const double phi = (1.0 + sqrt(5.0)) / 2.0;
    return (long long)floor(n * log(phi)/log(base) - log(sqrt(5.0))/log(base)) + 1;
}
```

## 4.3 Closed form (Binet's formula)

$$F_n = \frac{1}{\sqrt{5}}\left[\left(\frac{1+\sqrt{5}}{2}\right)^n - \left(\frac{1-\sqrt{5}}{2}\right)^n\right]$$

---

# 5 Perfect Squares

## 5.1 Fast detection

For integer $x \geq 0$:
1. **Modular pruning** (eliminates most non-squares instantly):
   - $x \bmod 4 \in \{0,1\}$
   - $x \bmod 8 \in \{0,1,4\}$
   - $x \bmod 16 \in \{0,1,4,9\}$ (stronger)
   - $x \bmod 3 \in \{0,1\}$
   - Last decimal digit $\in \{0,1,4,5,6,9\}$
2. Integer square root: `r = (ll)sqrt(x)`, check `r*r == x` (also try `r±1` for float precision).

## 5.2 "Two elements sum to a perfect square"

### 5.2.1 Does any pair $(a_i + a_j)$ form a perfect square?

Let `Amax` = max value, `Smax = 2*Amax`.

1. Precompute all squares up to `Smax`: `sq = {0, 1, 4, 9, ..., ⌊√Smax⌋²}`
2. Maintain count table `cnt` of values seen so far.
3. For each `x = a[i]`: check `for t in sq: if cnt[t - x] > 0`.

Complexity: $O(n \sqrt{S_{\max}})$.

### 5.2.2 Count all such pairs

Same as above — accumulate `cnt[t - x]` instead of just checking existence. Scan left-to-right so each unordered pair is counted once.

### 5.2.3 Small value range — frequency array

If `Amax` is small (e.g. $\leq 2 \times 10^5$): use frequency array `freq[v]`. For each square `t`, enumerate `v`, pair `u = t - v`, add `freq[v]*freq[u]`. Handle `v == u` with $\binom{\text{freq}[v]}{2}$.

Complexity: $O(\sqrt{S_{\max}} \cdot A_{\max})$, small constant.

## 5.3 "Consecutive integers summing to a perfect square"

Find $l..r$ such that $l + (l+1) + \cdots + r = \dfrac{(l+r)(r-l+1)}{2} = k^2$.

With length $m = r - l + 1$: sum $= \dfrac{m(2l + m - 1)}{2}$, which becomes a number-theory equation.

**Algorithms:**
1. **Two pointers / sliding window** (when all values positive): expand right if `sum < target`, shrink left if `sum > target`. When target isn't fixed, check if `sum` is a perfect square at each step.
2. **Enumerate square root**: if sum's upper bound is $M$, enumerate $k$, set $S = k^2$, solve for $m$ or $l$.

## 5.4 "Prefix difference is a perfect square" — general template

Many problems reduce to: $\text{prefix}[j] - \text{prefix}[i]$ is a perfect square.

- Enumerate right endpoint $j$; maintain hashmap `cnt[prefix[i]]`.
- Precompute square set `sq` (up to max possible interval sum).
- For each $j$, add:

$$\sum_{t \in \text{sq}} \texttt{cnt}[\text{prefix}[j] - t]$$

Complexity: $O(n \sqrt{\text{MaxSum}})$. Very stable pattern.
