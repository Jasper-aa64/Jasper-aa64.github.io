---
title: "Number Theory #1: Elementary Number Theory — GCD, LCM, Euler, CRT"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-1-elementary"
description: "GCD/LCM properties and subarray difference identity; Bézout's theorem and Frobenius; Euler's theorem, Fermat's little theorem, modular inverse; power-tower reduction via φ-chain; congruence systems and CRT; Legendre's formula for n!."
summary: "GCD/LCM properties, Bézout/Frobenius, Euler's theorem with power-tower reduction and φ-chain technique, congruence system merging via exGCD, CRT, and n! prime factorisation via Legendre's formula."
categories: [Number Theory]
tags: [math, number-theory, gcd, lcm, euler, crt, congruence, legendre]
math: true
toc: true
---

# 1 GCD & LCM

## 1.1 GCD Properties

$$\begin{aligned}
&\bullet\;\gcd(a,b)=\gcd(b,a) &&\bullet\;\gcd(a,0)=a\\
&\bullet\;\gcd(a,b)=\gcd(-a,b) &&\bullet\;\gcd(a,ka)=a\\
&\bullet\;\gcd(a,b)=\gcd(|a|,|b|) &&\bullet\;\gcd(an,bn)=n\gcd(a,b)\\
&\bullet\;\text{if }d\mid a\text{ and }d\mid b\text{, then }d\mid\gcd(a,b) &&\bullet\;\gcd(a,b)=\gcd(a,ka+b)
\end{aligned}$$

The last identity implies $\gcd(x,y)=\gcd(x,y-x)$.

Also: $d\mid\gcd(i,j)\;\Rightarrow\;d\mid i\text{ and }d\mid j$.

### 1.1.2 Subarray GCD — Difference Identity

For any interval $[l,r]$ with minimum position $m$:
$$\gcd(a_l,\ldots,a_r)=\gcd\!\bigl(a_m,\;|a_l-a_{l+1}|,\;|a_{l+1}-a_{l+2}|,\;\ldots,\;|a_{r-1}-a_r|\bigr).$$

## 1.2 LCM Properties

- If $a\mid m$ and $b\mid m$, then $\operatorname{lcm}(a,b)\mid m$ (generalises to arrays).
- $\operatorname{lcm}(ma,mb)=m\cdot\operatorname{lcm}(a,b)$.

**LCM of $1\ldots n$:** consider the prime factorisation.
$$\operatorname{lcm}(1,\ldots,n)=\prod_{p\in\mathcal{P}}p^{\lfloor\log_p n\rfloor},\quad\mathcal{P}=\{\text{primes}\leq n\}.$$

```cpp
// enumerate primes, accumulate highest prime power ≤ n
ll lc = 1;
for(int p = 2; p <= n; p++){
    if(!is_prime[p]) continue;
    ll e = p;
    while(e * p <= n) e *= p;   // highest power of p not exceeding n
    lc = lc * e % MOD;
}
cout << lc << "\n";
```

## 1.3 Useful Identity and CF 2183

> **Identity:**
> $$\frac{1}{\operatorname{lcm}(a_i,a_{i+1})}=\frac{\gcd(a_i,a_{i+1})}{a_i a_{i+1}}$$
> When $a_i\lt a_{i+1}$: $\gcd(a_i,a_{i+1})\leq a_{i+1}-a_i$.

**Codeforces 2183 solution** (bounding a cyclic lcm-sum by 1):

$$\begin{aligned}
&\sum_{i}\frac{1}{\operatorname{lcm}(a_i,a_{i+1})}
=\sum_i\frac{\gcd(a_i,a_{i+1})}{a_ia_{i+1}}\\
&\leq\frac{a_2-a_1}{a_1a_2}+\frac{a_3-a_2}{a_2a_3}+\cdots+\frac{a_n-a_{n-1}}{a_{n-1}a_n}+\frac{a_1}{a_1a_n}\\
&=\Bigl(\frac{1}{a_1}-\frac{1}{a_2}\Bigr)+\Bigl(\frac{1}{a_2}-\frac{1}{a_3}\Bigr)+\cdots+\Bigl(\frac{1}{a_{n-1}}-\frac{1}{a_n}\Bigr)+\frac{1}{a_n}\\
&=\frac{1}{a_1}\;\leq\;1.
\end{aligned}$$

---

# 2 Extended GCD (exGCD)

## 2.1 Bézout's Theorem

- $ax+by=c$ has integer solutions iff $\gcd(a,b)\mid c$.
- Generalisation: $\sum_{i=1}^n a_ix_i=b$ has integer solutions iff $\gcd(a_i)\mid b$.
- $\gcd(a,b)$ is the smallest positive integer representable as $ax+by$.

**Frobenius coin problem** (two denominations, $\gcd(a,b)=1$):  
Largest non-representable value $= ab-a-b$.

---

# 3 Euler's Theorem

## 3.1 Statements

### Euler's Theorem

If $\gcd(a,m)=1$:
$$a^{\varphi(m)}\equiv1\pmod{m}$$

### Fermat's Little Theorem

For prime $p$ with $p\nmid a$:
$$a^{p-1}\equiv1\pmod{p}$$

(Special case of Euler: $\varphi(p)=p-1$.)

### Modular Inverse

1. When $\gcd(a,m)=1$: $a^{-1}\equiv a^{\varphi(m)-1}\pmod{m}$.
2. When $p$ is prime and $0\lt a\lt p$: $a^{-1}\equiv a^{p-2}\pmod{p}$.

## 3.2 Power-Tower Reduction (Euler Totient Descent)

$$a^b\equiv\begin{cases}a^{b\bmod\varphi(m)},&\gcd(a,m)=1\\a^b,&b\lt\varphi(m)\\a^{b\bmod\varphi(m)+\varphi(m)},&b\geq\varphi(m)\end{cases}\pmod{m}$$

### 3.2.1 General Method: φ-Chain + Lifted Modulus

**Scenario:** the modulus may vary, the base may not be coprime to the modulus, and the exponent may be small — we need a safe, uniform approach.

1. **Build the φ-chain from top to bottom:** start with the outer modulus $p$, the next layer uses $\varphi(p)$, then $\varphi(\varphi(p))$, down to 1. When $\gcd(a,p)=1$, we only need $b\bmod\varphi(p)$.

2. **Lifted modulus (preserve "large exponent" information):** returning only $b\bmod\varphi(p)$ is wrong when the base and modulus are not coprime or when the exponent is small. Instead return:
$$\operatorname{Mod}(x,m)=\begin{cases}x,&x\lt m\\x\bmod m+m,&x\geq m\end{cases}$$
The "+m" flag signals to the upper layer that the exponent is "large", preventing incorrect collapse.

3. **Recursive implementation:** `dfs(pos, mod, r)` — stop at the leaf or when `mod == 1`; compute the upper-layer exponent modulo $\varphi(\text{mod})$ first, then exponentiate.

### 3.2.2 Example A — Nowcoder NC17190: Range-Add + Power Tower mod p

> Support: range add on array $a[]$; query $a[l]^{a[l+1]^{\cdots^{a[r]}}}\bmod p$.

- Use a **BIT with difference encoding** to support range-add and point-query: `query(i)` returns the current `a[i]`.
- For queries, run **φ-chain + lifted-modulus DFS**. This handles:
  - Different modulus each query.
  - Base possibly not coprime to modulus.
  - Exponent possibly too small.

```cpp
#include <bits/stdc++.h>
#define pb push_back
using namespace std;
const int N = 5e5 + 5, maxn = 2e7 + 5;
typedef long long ll;
ll bit[N]; int n;
vector<int> prime; bool vis[maxn]; int phi[maxn];

void read(int &x) {
    x = 0; int f = 1; char ch = getchar();
    while (!isdigit(ch)) { if (ch == '-') f = -1; ch = getchar(); }
    while (isdigit(ch)) { x = (x << 3) + (x << 1) + ch - '0'; ch = getchar(); }
    x *= f;
}

void init() {
    phi[1] = 1;
    for (int i = 2; i < maxn; i++) {
        if (!vis[i]) { prime.pb(i); phi[i] = i - 1; }
        for (int j = 0; j < (int)prime.size() && i * prime[j] < maxn; j++) {
            vis[i * prime[j]] = 1;
            if (i % prime[j] == 0) { phi[i * prime[j]] = phi[i] * prime[j]; break; }
            else phi[i * prime[j]] = phi[i] * phi[prime[j]];
        }
    }
}

void update(int p, ll val) { while (p <= n) { bit[p] += val; p += (p & -p); } }
ll query(int p) { ll res = 0; while (p > 0) { res += bit[p]; p -= (p & -p); } return res; }
void range_update(int l, int r, ll val) { update(l, val); update(r + 1, -val); }

ll Mod(ll x, ll y) { return x >= y ? (x % y + y) : x; }
ll power(ll a, ll b, ll p) {
    ll res = 1; a = Mod(a, p);
    while (b) { if (b & 1) res = Mod(res * a, p); a = Mod(a * a, p); b >>= 1; }
    return res;
}

ll dfs(int v, int p, int r) {
    ll tn = query(v);
    if (v == r || p == 1) return Mod(tn, 1LL * p);
    ll res = dfs(v + 1, phi[p], r);   // keep original value (lifted)
    return power(tn, res, 1LL * p);
}

int main() {
    init();
    int m, a, op, l, r, x, p;
    read(n); read(m);
    for (int i = 1; i <= n; i++) { read(a); range_update(i, i, a); }
    while (m--) {
        read(op); read(l); read(r);
        if (op == 1) { read(x); range_update(l, r, 1LL * x); }
        else { read(p); printf("%lld\n", dfs(l, p, r) % p); }
    }
    return 0;
}
```

### 3.2.3 Example B — "2023 Power Tower mod 2023": When the Shortcut Works

**Goal:** $2^{3^{4^{\cdots^{2023}}}}\bmod 2023$.

Key observations:
- $2023=7\cdot17^2$, $\varphi(2023)=1632$, $\gcd(2,2023)=1$ — so only the exponent mod 1632 matters.
- The tower **contains 1632 itself as a layer**. Since $1632^{(\text{positive})} \equiv 0\pmod{1632}$, that layer collapses immediately.
- From that layer downward, parity and $\bmod16$ control of lower-order factors propagate correctly within the same mod-1632 iteration.

```cpp
b = 2023;
for (int i = 2022; i >= 3; --i)
    b = qpow(i, b, 1632);        // iterate from top, always mod φ(2023)
ans = qpow(2, b /* or b%1632+1632 */, 2023);
```

**Conclusion:** this "always reduce mod $\varphi(p)$" shortcut works here because the tower contains $\varphi(p)$ as a layer and the outermost base is coprime to $p$. It is a **special-case shortcut, not a general rule**.

## 3.3 Euler's Totient Function $\varphi$

$\varphi(n)$ = count of integers in $[1,n]$ coprime to $n$. $\varphi(1)=1$.

$$\varphi(n)=n\!\left(1-\frac{1}{p_1}\right)\!\left(1-\frac{1}{p_2}\right)\cdots\left(1-\frac{1}{p_k}\right)$$

**Single-value computation in $O(\sqrt{n})$:**

```cpp
int euler_phi(int n) {
    int m = (int)sqrt(n + 0.5);
    int ans = n;
    for (int i = 2; i <= m; i++)
        if (n % i == 0) {
            ans = ans / i * (i - 1);   // divide first to avoid overflow
            while (n % i == 0) n /= i;
        }
    if (n > 1) ans = ans / n * (n - 1);   // last prime factor > sqrt(n)
    return ans;
}
```

---

# 4 Congruence Systems

## 4.1 Residue Classes mod m

The integers mod $m$ partition $\mathbb{Z}$ into $m$ equivalence classes $\{0,1,\ldots,m-1\}$. The congruence relation $a\equiv b\pmod{m}$ is equivalent to $m\mid(a-b)$.

## 4.2 Merging Two Congruences via exGCD

**Problem:** given $x\equiv r\pmod{m_1}$ and $x\equiv b\pmod{m_2}$, find $x\pmod{\operatorname{lcm}(m_1,m_2)}$.

> Note: $(m_1,m_2)$ denotes GCD, $[m_1,m_2]$ denotes LCM.

**Merging procedure** (using exGCD):
1. Solve $m_1 t\equiv(b-r)\pmod{m_2}$ for $t$.
2. Solvable iff $g=\gcd(m_1,m_2)\mid(b-r)$; otherwise no solution.
3. Reduce to $(m_1/g)\cdot t\equiv(b-r)/g\pmod{m_2/g}$; multiply by the inverse of $m_1/g$ mod $m_2/g$.
4. New solution: $x\leftarrow r+m_1 t_0$, new modulus: $\operatorname{lcm}(m_1,m_2)$.

**Recursively merge all $k$ equations in $O(k\log m)$.** Final answer: $x\equiv x_0\pmod{[m_1,m_2,\ldots,m_k]}$.

Template (POJ 2891, arbitrary moduli):

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

__int128 exgcd(__int128 a, __int128 b, __int128 &x, __int128 &y) {
    if (b == 0) { x = 1; y = 0; return a; }
    __int128 x1, y1;
    __int128 g = exgcd(b, a % b, x1, y1);
    x = y1; y = x1 - (a / b) * y1;
    return g;
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int k;
    while (cin >> k) {
        vector<pair<ll,ll>> eq(k);
        for (int i = 0; i < k; i++) cin >> eq[i].first >> eq[i].second;  // modulus ai, remainder ri

        __int128 r = 0, m = 1;
        bool ok = true;
        for (auto &[a0, r0] : eq) {
            __int128 a = a0, b = r0;
            __int128 x, y;
            __int128 g = exgcd(m, a, x, y);
            if ((b - r) % g != 0) { ok = false; break; }
            __int128 lcm = m / g * a;
            __int128 tgt = (b - r) / g;
            __int128 mod = a / g;
            __int128 t0 = ((x % mod) * (tgt % mod)) % mod;
            r = r + m * t0;
            r = (r % lcm + lcm) % lcm;
            m = lcm;
        }
        if (!ok) cout << -1 << "\n";
        else cout << (ll)r << "\n";
    }
    return 0;
}
```

## 4.3 CRT — Constructive Solution (Pairwise Coprime Moduli)

When $m_1,m_2,\ldots,m_n$ are pairwise coprime, the unique solution mod $M=\prod m_i$ is:
$$x=\sum_{i=1}^n a_i\cdot M_i\cdot(M_i^{-1}\bmod m_i)\pmod{M},\quad M_i=M/m_i.$$

```cpp
ll CRT(const vector<int> &a, const vector<int> &m) {
    int n = a.size();
    ll M = 1;
    for (int i = 0; i < n; ++i) M *= m[i];   // product of all moduli
    ll ans = 0;
    for (int i = 0; i < n; ++i) {
        ll mi = m[i], Mi = M / mi;
        int x, y;
        if (exgcd(mi, Mi, x, y) != 1) return -1;
        ans = (ans + Mi * y % M * a[i]) % M;
    }
    return (ans + M) % M;   // return value in [0, M)
}
```

---

# 5 Prime Factorisation of $n!$

**Legendre's formula:** the exponent of prime $p$ in $n!$ is
$$e_p=\sum_{k\geq1}\left\lfloor\frac{n}{p^k}\right\rfloor.$$

Each term $\lfloor n/p^k\rfloor$ counts multiples of $p^k$ in $[1,n]$, each contributing one additional factor of $p$.

**Implementation 1** (Sieve of Eratosthenes + Legendre):

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    long long n; if (!(cin >> n)) return 0;
    int N = (int)n;
    vector<char> is_prime(N+1, true);
    vector<int> primes;
    if (N >= 2) {
        is_prime[0] = is_prime[1] = false;
        for (int i = 2; i <= N; i++) {
            if (is_prime[i]) {
                primes.push_back(i);
                if ((long long)i * i <= N)
                    for (int j = i * i; j <= N; j += i) is_prime[j] = false;
            }
        }
    }
    bool first = true;
    for (int p : primes) {
        long long cnt = 0, pk = p;
        while (pk <= n) {
            cnt += n / pk;
            if (pk > n / p) break;   // prevent overflow
            pk *= p;
        }
        if (!first) cout << ' ';
        cout << p << '^' << cnt;
        first = false;
    }
    cout << '\n';
    return 0;
}
```

**Implementation 2** (Linear sieve + Legendre, cleaner):

```cpp
#include <iostream>
using namespace std;
const int N = 1000010;
int primes[N], cnt;
bool st[N];
void init(int n) {
    for (int i = 2; i <= n; i++) {
        if (!st[i]) primes[cnt++] = i;
        for (int j = 0; primes[j] * i <= n; j++) {
            st[i * primes[j]] = true;
            if (i % primes[j] == 0) break;
        }
    }
}
int main() {
    int n; cin >> n;
    init(n);
    for (int i = 0; i < cnt; i++) {
        int p = primes[i], s = 0;
        for (int j = n; j; j /= p) s += j / p;   // Legendre's formula
        printf("%d %d\n", p, s);
    }
    return 0;
}
```
