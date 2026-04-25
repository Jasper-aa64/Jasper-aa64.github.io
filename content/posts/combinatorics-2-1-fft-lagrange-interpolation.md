---
title: "Combinatorics #2.1: FFT and Lagrange Interpolation"
date: 2026-04-25
slug: "combinatorics-2-1-fft-lagrange-interpolation"
description: "Polynomial representations, FFT/DFT over complex numbers, Triple Sums, Fuzzy Search (difference convolution), FFT template, Lagrange interpolation (O(n²) and O(n) equidistant), sum of k-th powers, Assigning Prizes polynomial DP."
summary: "Polynomial representations, FFT/DFT over complex numbers, Triple Sums, Fuzzy Search (difference convolution), FFT template, Lagrange interpolation (O(n²) and O(n) equidistant), sum of k-th powers, Assigning Prizes polynomial DP."
categories: [Combinatorics]
tags: [math, combinatorics, fft, polynomial, lagrange, dp, convolution, generating-function]
math: true
toc: true
---

# 1 Two Representations of a Polynomial

> **[Two Representations]**
>
> **Coefficient form**: record the coefficients $a_n,\dots,a_0$:
>
> $$f(x)=a_nx^n+a_{n-1}x^{n-1}+\cdots+a_0$$
>
> **Point-value form**: choose $n+1$ distinct evaluation points $x_0,\dots,x_n$ and record:
>
> $$(x_0,f(x_0)),\;(x_1,f(x_1)),\;\dots,\;(x_n,f(x_n))$$
>
> **Equivalence:** any degree-$n$ polynomial is uniquely determined by its values at $n+1$ distinct points (e.g. three points determine a quadratic).

---

# 2 Why FFT Gives $O(n\log n)$ Multiplication

Convert to point-value form, multiply pointwise, then interpolate back:

$$
\underbrace{(\text{coefficients}\to\text{point values})}_{O(n\log n)}
\;+\;
\underbrace{(\text{pointwise multiplication})}_{O(n)}
\;+\;
\underbrace{(\text{point values}\to\text{coefficients})}_{O(n\log n)}
= O(n\log n)
$$

FFT/inverse FFT accelerates both the evaluation and interpolation steps to $O(n\log n)$.

## Prerequisites

> **[Prerequisites]**
>
> ### Complex exponential form
>
> $$a+bi=re^{i\theta},\qquad r=\sqrt{a^2+b^2},\qquad\tan\theta=\frac{b}{a}$$
>
> ### $n$-th roots of unity
>
> The roots of $x^n=1$ in $\mathbb{C}$ are:
>
> $$\omega_n^k=e^{i\frac{2k\pi}{n}},\qquad k=0,1,\dots,n-1$$
>
> Key identities:
>
> - $\omega_n^k=\omega_{2n}^{2k}$
> - $\omega_{2n}^{k+n}=-\omega_{2n}^k$

---

# 3 FFT Examples

## 3.1 Triple Sums

> **[Example — SPOJ TSUM: Triple Sums](https://vjudge.net/problem/SPOJ-TSUM)**
>
> Given a sequence $s_1,s_2,\dots,s_n$, count for every value $v$ the number of triples $(i,j,k)$ with $s_i+s_j+s_k=v$ and $i\lt j\lt k$.
>
> - $1\le n\le4\times10^4$, $|s_i|\le2\times10^4$, $v\in[-6\times10^4,6\times10^4]$
>
> Define $S(x)=\sum x^{s_i}$. Then $S(x)^3$ counts all unordered triples. With $S_2(x)=\sum x^{2s_i}$ and $S_3(x)=\sum x^{3s_i}$, inclusion-exclusion gives:
>
> $$\text{valid triples}=\frac{1}{6}\left(S(x)^3-3S_2(x)S(x)+2S_3(x)\right)$$
>
> Implementation: use FFT for $S^3$ and $S_2\cdot S$; shift indices if $s_i$ can be negative.

## 3.2 Fuzzy Search (difference convolution)

> **[Example — CF 528D: Fuzzy Search](https://codeforces.com/contest/528/problem/D)**
>
> Given text $S$ (length $n$), pattern $T$ (length $m$), and tolerance $k$, count alignments $i$ where for every position $j$ in $T$ there exists $p$ with $|(i+j-1)-p|\le k$ and $S[p]=T[j]$.
>
> $(1\le|T|\le|S|\le200000,\ 0\le k\le200000)$. When $k=0$ this is exact matching.
>
> For each character $c\in\{\mathrm{A},\mathrm{C},\mathrm{G},\mathrm{T}\}$:
>
> 1. **Expand** all occurrences of $c$ in $S$ by radius $k$ via a difference array: $A_c[x]=1$ iff some $S[p]=c$ with $|x-p|\le k$.
> 2. **Indicator** array $B_c[j]=\mathbf{1}[T[j]=c]$.
> 3. **Reverse $B_c$ and convolve**: $C_c=A_c * B_c^{\mathrm{rev}}$. Then $C_c[i+m-1]$ counts matching positions for character $c$ at alignment $i$.
> 4. **Sum over characters**: alignment $i$ is valid iff $\sum_c C_c[i+m-1]=m$.
>
> Complexity: $O(n\log n)$.

```cpp
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, m, k;
    string S, T; cin >> n >> m >> k;
    cin >> S >> T;

    auto solve_for_char = [&](char ch) {
        vector<int> A(n, 0), diff(n + 1, 0);
        for (int p = 0; p < n; ++p) if (S[p] == ch) {
            int L = max(0, p - k);
            int R = min(n - 1, p + k);
            diff[L] += 1;
            diff[R + 1] -= 1;
        }
        for (int i = 0, cur = 0; i < n; ++i) {
            cur += diff[i];
            A[i] = (cur > 0) ? 1 : 0;
        }
        vector<int> B(m, 0);
        for (int j = 0; j < m; ++j) B[j] = (T[j] == ch);
        reverse(B.begin(), B.end());
        return multiply(A, B);
    };

    vector<ll> acc(n + m - 1, 0);
    for (char c : string("ACGT")) {
        auto conv = solve_for_char(c);
        for (int i = 0; i < (int)conv.size(); ++i) acc[i] += conv[i];
    }

    int ans = 0;
    for (int i = 0; i + m <= n; ++i)
        if (acc[m - 1 + i] == m) ans++;
    cout << ans << '\n';
    return 0;
}
```

---

# 4 FFT Template

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

using cd = complex<double>;
const double PI = acos(-1);

void fft(vector<cd>& a, bool invert) {
    int n = a.size();
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j |= bit;
        if (i < j) swap(a[i], a[j]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = 2 * PI / len * (invert ? -1 : 1);
        cd wlen(cos(ang), sin(ang));
        for (int i = 0; i < n; i += len) {
            cd w(1);
            for (int j = 0; j < len / 2; j++) {
                cd u = a[i + j];
                cd v = a[i + j + len / 2] * w;
                a[i + j] = u + v;
                a[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
    if (invert) {
        for (cd& x : a) x /= n;
    }
}

vector<ll> convolution(const vector<ll>& A, const vector<ll>& B) {
    int n = 1;
    while (n < (int)A.size() + (int)B.size()) n <<= 1;
    vector<cd> fa(A.begin(), A.end()), fb(B.begin(), B.end());
    fa.resize(n); fb.resize(n);
    fft(fa, false); fft(fb, false);
    for (int i = 0; i < n; i++) fa[i] *= fb[i];
    fft(fa, true);
    vector<ll> res(n);
    for (int i = 0; i < n; i++) res[i] = (ll)(fa[i].real() + 0.5);
    return res;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m;
    cin >> n >> m;
    vector<ll> A(n), B(m);
    for (auto& x : A) cin >> x;
    for (auto& x : B) cin >> x;
    auto C = convolution(A, B);
    for (int i = 0; i < n + m - 1; i++)
        cout << C[i] << (i + 1 == n + m - 1 ? '\n' : ' ');
    return 0;
}
```

---

# 5 Lagrange Interpolation

> **[Lagrange Interpolation]**
>
> Given $n$ points $(x_i,y_i)$, $1\le i\le n$, with $x_i$ pairwise distinct, the unique polynomial of degree $\le n-1$ through them is:
>
> $$f(x)=\sum_{i=1}^{n}y_i\prod_{j\ne i}\frac{x-x_j}{x_i-x_j}$$
>
> There is a direct analogy with CRT.

| Variant | Complexity |
|---|---|
| Full reconstruction (all queries) | $O(n^2)$ preprocess + $O(n)$ per query |
| Single-point query (arbitrary nodes) | $O(n^2)$ |
| Single-point query ($x_i=i$, equidistant) | $O(n)$ |

## 5.1 Generic $O(n^2)$: multi-query

Preprocess weights $w[i]=1/\prod_{j\ne i}(x_i-x_j)$ in $O(n^2)$, then each query is $O(n)$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

ll modinv(ll a) { return qp(a, mod - 2); }

int main(){
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m;
    cin >> n >> m >> mod;
    vector<ll> x(n), y(n);
    for (int i = 0; i < n; ++i) cin >> x[i] >> y[i];

    vector<ll> w(n, 1);
    for (int i = 0; i < n; ++i) {
        ll prod = 1;
        for (int j = 0; j < n; ++j) if (j != i)
            prod = prod * ((x[i] - x[j] + mod) % mod) % mod;
        w[i] = modinv(prod);
    }

    while (m--) {
        ll v; cin >> v;
        bool hit = false;
        for (int i = 0; i < n; ++i) {
            if (v == x[i]) { cout << y[i] << "\n"; hit = true; break; }
        }
        if (hit) continue;
        ll num = 0, den = 0;
        for (int i = 0; i < n; ++i) {
            ll inv = modinv((v - x[i] + mod) % mod);
            ll t = w[i] * inv % mod;
            num = (num + t * y[i]) % mod;
            den = (den + t) % mod;
        }
        cout << num * modinv(den) % mod << "\n";
    }
    return 0;
}
```

## 5.2 Generic $O(n^2)$: single-point query

```cpp
ll lagrange_nn(const vector<ll>& x, const vector<ll>& y, ll v) {
    int n = x.size();
    ll ans = 0;
    for (int i = 0; i < n; ++i) {
        ll num = 1, den = 1;
        for (int j = 0; j < n; ++j) if (j != i) {
            num = num * ((v - x[j]) % mod + mod) % mod;
            den = den * ((x[i] - x[j]) % mod + mod) % mod;
        }
        ans = (ans + y[i] * num % mod * modinv(den)) % mod;
    }
    return (ans + mod) % mod;
}
```

## 5.3 $O(n)$ single-point query with equidistant nodes $x_i=i$

```cpp
ll lagrange_linear(const vector<ll>& y, ll v) {
    int n = y.size();

    vector<ll> pref(n+1), suf(n+1);
    vector<ll> fac(n+1), ifac(n+1);
    {
        fac[0] = 1;
        for (int i = 1; i <= n; ++i) fac[i] = fac[i-1] * i % mod;
        ifac[n] = modinv(fac[n]);
        for (int i = n; i > 0; --i) ifac[i-1] = ifac[i] * i % mod;
    }

    pref[0] = 1;
    for (int i = 0; i < n; ++i) pref[i+1] = pref[i] * ((v - i) % mod + mod) % mod;
    suf[n] = 1;
    for (int i = n-1; i >= 0; --i) suf[i] = suf[i+1] * ((v - i) % mod + mod) % mod;

    ll ans = 0;
    for (int i = 0; i < n; ++i) {
        ll num = pref[i] * suf[i+1] % mod;
        ll den = ifac[i] * ifac[n-1-i] % mod;
        if ((n-1-i) & 1) den = (mod - den) % mod;
        ans = (ans + y[i] * num % mod * den) % mod;
    }
    return (ans + mod) % mod;
}
```

### Equally spaced nodes $a+ih$

If nodes are $a,a+h,\dots,a+dh$, normalize $v$ to the $0..d$ grid:

```cpp
ll lagrange_equidistant(vector<ll>& y, ll a, ll h, ll v) {
    int d = (int)y.size() - 1;
    if (h > 0 && v >= a) {
        ll t = (v - a);
        if (t % h == 0) {
            ll idx = t / h;
            if (0 <= idx && idx <= d) return y[(int)idx];
        }
    }
    ll k = (((v % mod - a % mod + mod) % mod) * inv(h)) % mod;
    return lagrange_uniform_0_to_d(y, k);
}
```

---

# 6 Example: Sum of $k$-th Powers

> **[Example — CF 622F: The Sum of the $k$-th Powers](https://codeforces.com/contest/622/problem/F)**
>
> Compute $\displaystyle\sum_{i=1}^n i^k$ where $1\le n\le10^9$, $0\le k\le10^6$, modulo $10^9+7$.
>
> The function $f(n)=\sum_{i=1}^n i^k$ is a polynomial of degree $k+1$ in $n$.
>
> **Proof** (Stirling numbers + falling factorials):
>
> $$f(n)=\sum_{j=0}^k S_2(k,j)\sum_{i=1}^n i^{\underline{j}}=\sum_{j=0}^k S_2(k,j)\cdot\frac{(n+1)^{\underline{j+1}}}{j+1}$$
>
> The coefficients $S_2(k,j)$ are independent of $n$, so this is degree $k+1$.
>
> **Telescoping:** from $(x+1)^{\underline{j+1}}-x^{\underline{j+1}}=(j+1)x^{\underline{j}}$ we get $\Delta\!\left(\frac{x^{\underline{j+1}}}{j+1}\right)=x^{\underline{j}}$, hence $\sum_{i=0}^n i^{\underline{j}}=\frac{(n+1)^{\underline{j+1}}}{j+1}$.
>
> **Algorithm:** evaluate $f$ at $k+2$ small points, then use $O(n)$ Lagrange interpolation to get $f(n)$.

---

# 7 Example: Assigning Prizes

> **[Example — ACM-ICPC Brazil 2021–22 Subregional A: Assigning Prizes]**
>
> Given $p_1,\dots,p_n$ and $R$, count sequences $a_1,\dots,a_n$ with $p_i\le a_i\le R$ and $a_1\ge a_2\ge\cdots\ge a_n$. Answer modulo $10^9+7$. $(1\le n\le5000,\ 1\le R,\ p_i\le10^9)$
>
> Define $f(i,x)=$ number of valid completions with $a_i=x$:
>
> $$f(i,x)=\sum_{j=p_{i+1}}^x f(i+1,j),\qquad f(n,x)=1$$
>
> Brute-force fails ($R$ up to $10^9$). Key: $f(i,x)$ is a degree-$(n-i)$ polynomial in $x$. Store $n-i+1$ point-values instead. Maintain $S(i,x)=\sum_{j=1}^x f(i,j)$ (degree $+1$, discrete integral):
>
> $$f(i,x)=S(i+1,x)-S(i+1,p_{i+1}-1)$$
>
> $S(i+1,p_{i+1}-1)$ is evaluated by $O(n)$ Lagrange. Overall $O(n^2)$. Final answer: $f(0,R)$.

```cpp
ll lagrange_linear(const vector<ll>& y, ll v) { /* see §5.3 */ }

int add(int a, int b){ a+=b; if(a>=MOD) a-=MOD; return a; }
int sub(int a, int b){ a-=b; if(a<0) a+=MOD; return a; }

int main(){
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    init(5e4 + 2);

    int n, R;
    cin >> n >> R;
    vector<int> p(n + 1);
    for (int i = 1; i <= n; i++) cin >> p[i];
    for (int i = n - 1; i >= 1; i--) p[i] = max(p[i], p[i + 1]);

    if (R < p[1]) { cout << 0 << '\n'; return 0; }

    vector<ll> f_next(1, 1);
    for (int i = n - 1; i >= 0; i--) {
        int deg = int(f_next.size()) - 1;

        vector<ll> S(deg + 1);
        S[0] = f_next[0];
        for (int j = 1; j <= deg; j++) S[j] = add(S[j-1], f_next[j]);

        int f_ext = lagrange_linear(f_next, deg + 1);
        vector<ll> f_curr(deg + 2);
        for (int j = 0; j <= deg; j++) f_curr[j] = S[j];
        f_curr[deg + 1] = add(S[deg], f_ext);

        ll v = p[i + 1] - 1;
        int subVal = 0;
        if (v >= 0) subVal = lagrange_linear(f_curr, v);
        for (int j = 0; j <= deg + 1; j++) f_curr[j] = sub(f_curr[j], subVal);

        f_next.swap(f_curr);
    }
    cout << lagrange_linear(f_next, R) << endl;
    return 0;
}
```

## How to spot a polynomial structure

> **[How to recognise polynomial structure]**
>
> - If DP contains $F(x)=\sum_{t\le x}G(t)$, think **discrete integral**: if $G$ is degree $d$, then $F$ is degree $d+1$.
> - Base layer constant/linear/low-degree + each prefix-sum layer → degree increases by 1.
> - If $x$ only appears as an upper/lower bound (not in $x\cdot f(x)$ interactions), the sequence is often polynomial.
> - If $x$ ranges to $10^9$ but depth $n$ is small, Lagrange interpolation is usually the key.
>
> **Code correspondence:** maintain polynomial values at equally spaced nodes $x=0,1,\dots$; prefix sums = discrete integration (degree $+1$); subtract $S(p_{i+1}-1)$ as a single Lagrange query; final answer from one Lagrange query at $R$. Total $O(n^2)$.

## When does a recurrence give a polynomial closed form?

> **[When is a recurrence's closed form a polynomial?]**
>
> Three equivalent criteria (satisfy any one):
>
> 1. **Difference criterion:** $\Delta^k a_n\equiv0$ $\Rightarrow$ $a_n$ is degree $\le k-1$.
> 2. **Characteristic-root criterion:** only root $1$ with multiplicity $k$, no $r\ne1$ $\Rightarrow$ every solution is degree $\le k-1$.
> 3. **Generating-function criterion:** $A(x)=R(x)/(1-x)^k$ with $\deg R\lt k$ $\Rightarrow$ $a_n$ is degree $\le k-1$.
>
> With non-homogeneous polynomial right-hand side of degree $s$: solution is degree $\le s+k$ (if homogeneous part has only root 1). Any root $r\ne1$ introduces $r^n$ — **not** a pure polynomial.
>
> Examples:
> - $a_{n+1}-a_n=c$ → linear
> - $a_{n+2}-2a_{n+1}+a_n=0$ → linear
> - $a_{n+1}=a_n+n^2$ → cubic
> - $a_{n+1}=2a_n+n$ → contains $2^n$, **not** polynomial
