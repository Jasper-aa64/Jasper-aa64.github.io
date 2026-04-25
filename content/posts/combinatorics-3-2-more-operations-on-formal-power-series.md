---
title: "Combinatorics #3.2: More Operations on Formal Power Series"
date: 2026-04-25
slug: "combinatorics-3-2-more-operations-on-formal-power-series"
description: "Newton iteration for polynomial inverse and square root, derivative/integral/composition of formal power series, logarithm and exponential of series, and worked examples including CF438E and a bad-modulus complete-knapsack generating function."
summary: "Newton iteration for polynomial inverse and square root, derivative/integral/composition of formal power series, logarithm and exponential of series, and worked examples including CF438E and a bad-modulus complete-knapsack generating function."
categories: [Combinatorics]
tags: [math, combinatorics, generating-function, formal-power-series, ntt, newton, polynomial, exp, logarithm]
math: true
toc: true
---

# 1 More Operations on Formal Power Series

In the world of formal power series, we only care about algebraic operations on coefficients. Numerical convergence is irrelevant here.

**Formal power series vs. analytic power series**

- A formal power series is fundamentally a sequence.
- An analytic power series is fundamentally a limit object.
- By substitution, a formal power series can be turned into an ordinary power series.
- Over $\mathbb{C}$, one can prove that formal power series and power series with positive radius of convergence obey the same rules for the "usual" operations.

> The "usual" operations are: addition, subtraction, multiplication, differentiation, integration, and composition.

Some standard sequence transforms are:

$$
\begin{aligned}
c\cdot F(x)              &\longrightarrow \text{scale the sequence}\\
x\cdot F(x)              &\longrightarrow \text{shift right and pad with 0}\\
\frac{F(x)-f(0)}{x}      &\longrightarrow \text{shift left}\\
F_1(x)\pm F_2(x)         &\longrightarrow \text{termwise sum / difference}
\end{aligned}
$$

---

# 2 Newton Iteration: $O(n\log n)$ Inverse and Square Root

## 2.1 The general idea

Given a polynomial $g(x)$, we want a formal power series $f(x)$ satisfying

$$
g(f(x))=0.
$$

Here $f(x)$ is a formal power series, $g(x)$ is a polynomial, and $g\circ f$ is again a formal power series.

### Generic framework

1. **Initialization**

   When $n=1$, only the constant term matters:

   $$
   g(a_0)=0.
   $$

2. **Induction hypothesis**

   Suppose we already know the first $n$ coefficients:

   $$
   f_0(x)=a_0+a_1x+\cdots+a_{n-1}x^{n-1}\pmod{x^n}.
   $$

3. **Newton update**

   Modulo $x^{2n}$, define

   $$
   f_1(x)=f_0(x)-\frac{g(f_0(x))}{g'(f_0(x))}\pmod{x^{2n}}.
   $$

   Then $f_1$ is correct up to the first $2n$ terms.

Each iteration doubles the valid length, so after $\log n$ rounds we get the answer modulo $x^n$.
The dominant cost is several polynomial multiplications, hence $O(n\log n)$ with NTT.

## 2.2 Polynomial inverse

Given a polynomial $f(x)$ with $f(0)\neq 0$, compute $g(x)$ such that

$$
f(x)g(x)\equiv 1 \pmod{x^n}.
$$

Newton iteration:

$$
g_{k+1}(x)=g_k(x)\bigl(2-f(x)g_k(x)\bigr)\pmod{x^{2^k}}.
$$

Start from

$$
g_0(x)=f(0)^{-1}.
$$

## 2.3 Polynomial square root

Assume first that $f(0)$ has a square root modulo the base modulus. In the common simplified setting, we take $f(0)=1$.

We want

$$
g(x)^2\equiv f(x)\pmod{x^n}.
$$

Newton iteration:

$$
g_{k+1}(x)=\frac12\left(g_k(x)+\frac{f(x)}{g_k(x)}\right)\pmod{x^{2^k}}.
$$

The inverse $\frac{1}{g_k(x)}$ is computed by the inverse algorithm above.

## 2.4 NTT + Newton template

Complexity: $O(n\log n)$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int MOD = 998244353, G = 3;

// NTT utilities omitted ...

// keep only the first m coefficients of a polynomial
void trim(vector<ll>& a, int m){
    if((int)a.size() > m) a.resize(m);
}

// polynomial inverse: f^{-1} mod x^n
vector<ll> poly_inv(const vector<ll>& f, int n){
    vector<ll> g(1, qp(f[0])); // g(0) = f(0)^{-1}
    for(int m = 1; m < n; m <<= 1){
        // extend precision to 2m terms
        vector<ll> f_cut(f.begin(), f.begin() + min((int)f.size(), 2 * m));
        auto tmp = multiply(multiply(g, g), f_cut);
        g.resize(2 * m);
        for(int i = 0; i < 2 * m; i++){
            // g_{k+1} = g * (2 - f * g)
            ll v = (2 * g[i] % MOD - tmp[i] + MOD) % MOD;
            g[i] = v;
        }
    }
    trim(g, n);
    return g;
}

// polynomial square root mod x^n, assuming f[0] is a quadratic residue
vector<ll> poly_sqrt(const vector<ll>& f, int n){
    vector<ll> g(1, 1); // initial guess h0 = 1 or sqrt(f[0]); simplified to 1 here
    ll c0 = f[0];
    g[0] = 1; // here we assume f[0] = 1

    for(int m = 1; m < n; m <<= 1){
        // h_{k+1} = (h + f / h) * inv2
        vector<ll> g_inv = poly_inv(g, 2 * m);
        vector<ll> t = multiply(f, g_inv);
        t.resize(2 * m);
        g.resize(2 * m);
        ll inv2 = (MOD + 1) / 2;
        for(int i = 0; i < 2 * m; i++){
            g[i] = (g[i] + t[i]) * inv2 % MOD;
        }
    }
    trim(g, n);
    return g;
}

int main(){
    int n = 8;           // compute up to x^8
    vector<ll> f = {1, 2, 3};

    auto invf = poly_inv(f, n);
    for(auto v : invf) cout << " " << v;
    cout << "\n";

    // requires f[0] = 1 and a square root modulo MOD
    auto sq = poly_sqrt(f, n);
    for(auto v : sq) cout << " " << v;
    cout << "\n";
    return 0;
}
```

## 2.5 Example: [The Child and Binary Tree](https://codeforces.com/contest/438/problem/E)

Given a set $\{c_1,c_2,\dots,c_n\}$, every node in a rooted binary tree must have a weight from this set.

The total weight of a rooted binary tree is the sum of the weights of all its nodes.
For each $s=1,2,\dots,m$, count the number of different rooted binary trees of total weight $s$, modulo $998244353$.
Left and right subtrees are distinguishable.

$$
1\le n,m,c_i\le 10^5.
$$

### Method 1

Let

$$
f_s=\text{the number of valid binary trees with total weight exactly }s,
\qquad
C(x)=\sum_{i=1}^{n}x^{c_i},
\qquad
F(x)=\sum_{s\ge 0}f_sx^s.
$$

For a nonempty tree, if the root weight is $c\in C$ and the left / right subtrees have total weights $a,b$, then

$$
a+b+c=s,
\qquad
\#\{\text{such trees}\}=\sum_{c\in C}\sum_{a+b=s-c}f_af_b.
$$

Including the empty tree ($f_0=1$), we get

$$
F(x)=1+C(x)F(x)^2.
$$

So

$$
C(x)F(x)^2-F(x)+1=0,
$$

and therefore

$$
F(x)=\frac{1\pm\sqrt{1-4C(x)}}{2C(x)}.
$$

To match the regular expansion with $F(0)=1$, it is more convenient to rewrite this as

$$
F(x)=\frac{2}{1+\sqrt{1-4C(x)}}.
$$

Now the denominator has constant term $1+1=2$, which is invertible modulo $998244353$.

**Algorithm**

1. Let
   $$
   A(x)=1-4C(x),\qquad S(x)=\sqrt{A(x)}\quad (S(0)=1).
   $$
2. Compute $S(x)$ by Newton iteration.
3. Let
   $$
   N(x)=1+S(x),\qquad F(x)=2\cdot N(x)^{-1}.
   $$
4. Again compute the inverse by Newton iteration.

Complexity:

$$
O(m\log m).
$$

```cpp
int main(){
    ios::sync_with_stdio(false);
    cin.tie(NULL);

    int n, m;
    cin >> n >> m;
    vector<int> C(m + 1);
    for(int i = 0; i < n; i++){
        int c; cin >> c;
        if(c <= m) C[c] = (C[c] + 1) % MOD;
    }

    // build A(x) = 1 - 4 * C(x)
    vector<int> A(m + 1);
    A[0] = 1;
    for(int i = 1; i <= m; i++){
        A[i] = (MOD - (long long)4 * C[i] % MOD) % MOD;
    }

    // compute S = sqrt(A)
    auto S = poly_sqrt(A, m + 1);
    // compute N = 1 + S
    vector<int> N(m + 1);
    for(int i = 0; i <= m; i++){
        N[i] = S[i];
    }
    N[0] = (N[0] + 1) % MOD;
    // compute N^{-1}
    auto Nin = poly_inv(N, m + 1);
    // F(x) = 2 * N^{-1}
    for(int i = 0; i <= m; i++){
        Nin[i] = (int)((long long)Nin[i] * 2 % MOD);
    }

    for(int s = 1; s <= m; s++){
        cout << Nin[s] << "\n";
    }
    return 0;
}
```

We can also compute

$$
\frac{1\pm\sqrt{1-4C(x)}}{2C(x)}
$$

directly, but then the denominator has zero constant term and cannot be inverted as a polynomial.

### Why do we choose the "$-$" branch?

The generating function

$$
F(x)=\sum_{s\ge 0}f_sx^s
$$

must satisfy $F(0)=f_0=1$.

Since all weights satisfy $c_i\ge 1$, we have

$$
C(x)=\sum_i x^{c_i}
\Rightarrow
C(0)=0,
\qquad
A(x):=1-4C(x)\Rightarrow A(0)=1.
$$

We choose the regular square-root branch with $\sqrt{A(0)}=1$.
Now consider

$$
F(x)=\frac{1\pm\sqrt{1-4C(x)}}{2C(x)}.
$$

As $x\to 0$:

- with the "$+$" branch, the numerator tends to $2$ and the denominator tends to $0$, so it diverges;
- with the "$-$" branch, both numerator and denominator tend to $0$, so it is a $0/0$ form.

Using

$$
(1-\sqrt{1-4C})(1+\sqrt{1-4C})=4C,
$$

we get

$$
\frac{1-\sqrt{1-4C}}{2C}=\frac{2}{1+\sqrt{1-4C}}.
$$

The denominator on the right has constant term $2$, hence it is invertible, and the resulting series has constant term $1$.

So **only the "$-$" branch** gives the unique regular solution.

### Direct computation of $\displaystyle F=\frac{1-\sqrt{1-4C}}{2C}$

Let

$$
u=\min\{i\ge 1:[x^i]C(x)\neq 0\},
$$

the minimum allowed weight.
Then

$$
C(x)=x^uD(x),
$$

with

$$
D(0)=[x^u]C(x)\neq 0.
$$

Also,

$$
1-\sqrt{1-4C(x)}=2C(x)\cdot H(x)=2x^uD(x)\cdot H(x),
$$

where $H(0)\neq 0$.
So numerator and denominator contain exactly the same factor $x^u$.

Shift both of them right by $u$:

$$
\widetilde U(x)=\frac{U(x)}{x^u},
\qquad
\widetilde J(x)=\frac{J(x)}{x^u},
$$

where

$$
U(x)=1-\sqrt{1-4C(x)},
\qquad
J(x)=2C(x).
$$

Then

$$
F(x)=\frac{\widetilde U(x)}{\widetilde J(x)}.
$$

Now $\widetilde J(0)=2D(0)\neq 0$, so polynomial inversion becomes legal.

```cpp
int main(){
    ios::sync_with_stdio(false); cin.tie(NULL);

    int n, m;
    cin >> n >> m;
    vector<int> C(m + 1);
    for(int i = 0; i < n; i++){
        int c; cin >> c;
        if(c <= m) C[c] = (C[c] + 1) % M;
    }

    // build A(x) = 1 - 4 * C(x)
    vector<int> A(m + 1);
    A[0] = 1;
    for(int i = 1; i <= m; i++) A[i] = (M - (ll)4 * C[i] % M) % M;

    int u = -1; bool first = true;
    for(int i = 0; i < m + 1; i++){
        if(first && C[i]){ first = false; u = i; }
    }
    if (u == -1) {
        for (int s = 1; s <= m; s++) cout << 0 << "\n";
        return 0;
    }

    auto S = poly_sqrt(A, m + 1 + u);
    // compute N = 1 - S
    vector<int> N(m + 1 + u);
    for(int i = 0; i <= m + u; i++){ N[i] = -S[i]; N[i] += M; N[i] %= M; }
    N[0] = (N[0] + 1) % M;

    vector<int> twoC(m + u + 1);
    for(int i = 0; i < m + 1; i++){
        twoC[i] = (ll)2 * C[i] % M;
    }
    vector<int> den(twoC.begin() + u, twoC.begin() + u + (m + 1));
    auto den_inv = poly_inv(den, m + 1);
    vector<int> num(N.begin() + u, N.begin() + u + (m + 1));
    auto ans = multiply(num, den_inv);

    for(int s = 1; s <= m; s++){
        cout << ans[s] << "\n";
    }
    return 0;
}
```

### Method 2

Apply Newton iteration directly to

$$
G(F)=C(x)F(x)^2-F(x)+1=0.
$$

The key point is that every update uses **polynomial convolution**, not pointwise multiplication, and "$+1$" / "$-1$" only affect coefficient $0$.

Core facts:

1. Newton formula:
   $$
   F_{k+1}=F_k-\frac{G(F_k)}{G'(F_k)},
   \qquad
   G(F)=CF^2-F+1,
   \qquad
   G'(F)=2CF-1.
   $$

2. Polynomial operations:

   - Multiplication and inversion are done with NTT in $O(m\log m)$.
   - To compute $U=G(F)$ and $V=G'(F)$ we need:
     - $F^2$: one convolution;
     - $C\cdot F^2$ and $C\cdot F$: two more convolutions.
   - When adding or subtracting constants, only coefficient $0$ is adjusted.

Thus we can compute

$$
F(x)=\sum_{s\ge 0}f_sx^s,
\qquad
1+C(x)F(x)^2-F(x)=0,
$$

and finally output $\{f_s\}_{s=1}^{m}$.

```cpp
vector<int> solve_newton(const vector<int> &C, int m) {
    vector<int> F(1, 1);   // initial value: F(x) = 1
    for (int L = 1; L <= m; L <<= 1) {
        int Len = min(2 * L, m + 1);
        auto F2 = multiply_capped(F, F, Len);
        auto CF2 = multiply_capped(C, F2, Len);
        auto CF  = multiply_capped(C, F, Len);

        vector<int> U(Len), V(Len); // U = G(F), V = G'(F)
        for (int i = 0; i < Len; i++) {
            ll u = CF2[i] - (i < (int)F.size() ? F[i] : 0);
            if (i == 0) u += 1;
            u %= M;
            U[i] = int(u);

            ll v = 2LL * CF[i];
            if (i == 0) v -= 1;
            v %= M;
            if (v < 0) v += M;
            V[i] = int(v);
        }

        auto W = poly_inv(V, Len);
        auto UW = multiply_capped(U, W, Len);
        F.resize(Len);
        for (int i = 0; i < Len; i++) {
            F[i] -= UW[i];
            if (F[i] < 0) F[i] += M;
        }
    }
    F.resize(m + 1);
    return F;
}

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);

    int n, m;
    cin >> n >> m;
    vector<int> C(m + 1, 0);
    for (int i = 0, c; i < n; i++) {
        cin >> c;
        if (c <= m) C[c] = 1;
    }

    auto F = solve_newton(C, m);
    for (int s = 1; s <= m; s++) cout << F[s] << "\n";
    return 0;
}
```

### Method 3

CDQ divide and conquer. Omitted here.

## 2.6 Example: [Convolution](https://ac.nowcoder.com/acm/contest/5857/B)

Define the generating function

$$
F(x)=\sum_{i=1}^{\infty}f_ix^i,
$$

where

$$
f_i=af_{i-1}+bf_{i-2}\quad (i\ge 2),
\qquad
f_0=0,\quad f_1=1.
$$

We need the coefficient of degree $n$ in

$$
\sum_{i=1}^{\infty}F(x)^i \pmod{998244353}.
$$

with

$$
1\le n\le 2\times 10^6,
\qquad
0\le a,b\lt 998244353.
$$

Method 1: polynomial inverse.

Method 2: omitted.

---

# 3 Derivative, Integral, and Composition

## 3.1 Derivative

The derivative of

$$
f(x)=a_0+a_1x+a_2x^2+\cdots
$$

is

$$
f'(x)=a_1+2a_2x+\cdots+(n+1)a_{n+1}x^n+\cdots.
$$

Interpretation:

$$
\begin{aligned}
F'(x) &\longrightarrow \text{multiply by the exponent and shift left},\\
(c)' &= 0,\\
(x^n)' &= nx^{n-1}.
\end{aligned}
$$

## 3.2 Integral

The integral is

$$
\int f(x)\,dx
=a_0x+\frac{a_1}{2}x^2+\cdots+\frac{a_{n-1}}{n}x^n+\cdots.
$$

Interpretation:

$$
\int f(x)\,dx
\longrightarrow
\text{shift right and divide by the exponent}.
$$

## 3.3 Composition

Suppose

$$
f(x)=a_1x+\cdots+a_nx^n+\cdots,
\qquad
g(x)=b_0+b_1x+\cdots+b_nx^n+\cdots.
$$

Then $g\circ f$ is the formal power series

$$
c_0+c_1x+\cdots+c_nx^n+\cdots,
$$

where

$$
c_0=b_0,
\qquad
c_n=\sum_{k=1}^{n}b_k\sum_{i_1+i_2+\cdots+i_k=n}a_{i_1}a_{i_2}\cdots a_{i_k}.
$$

We prefer $f(x)$ to have zero constant term to stay in the formal setting cleanly.

Composition + differentiation gives the chain rule:

$$
(g(f(x)))'=g'(f(x))\cdot f'(x),
$$

equivalently

$$
(g\circ f)'=(g'\circ f)\cdot f'.
$$

---

# 4 $\ln$ and $\exp$

## 4.1 Two key forms

$$
\exp(x)=\sum_{n\ge 0}\frac{x^n}{n!},
\qquad
\ln(1+x)=\sum_{n\ge 1}\frac{(-1)^{n+1}}{n}x^n.
$$

If

$$
[x^0]f(x)=0,
$$

then we may define

$$
\exp(f(x))
\qquad\text{and}\qquad
\ln(1+f(x)).
$$

For $\exp$, all coefficients of the exponential generating function are $1$:

$$
\exp(x)=1+x+\frac{x^2}{2!}+\cdots=\sum_{n\ge 0}\frac{x^n}{n!}.
$$

For $\ln$, we cannot define $\ln(0)$, so the standard object is $\ln(1+x)$.
More generally, $\ln(f(x))$ is valid if

$$
[x^0]f(x)=1.
$$

Also,

$$
g(x)=\exp(f(x))
\Longleftrightarrow
f(x)=\ln(g(x)).
$$

## 4.2 Computing $\ln(f(x))$ in $O(n\log n)$

This requires

$$
[x^0]f(x)=1.
$$

The key observation is

$$
(\ln(f(x)))'=f'(x)\cdot \frac{1}{f(x)}.
$$

Here:

- $f'(x)$ costs $O(n)$;
- $\frac{1}{f(x)}$ costs $O(n\log n)$.

So

$$
\ln(f(x))=\int f'(x)\frac{1}{f(x)}\,dx,
$$

and the total complexity is $O(n\log n)$.

## 4.3 Computing $\exp(f(x))$ in $O(n\log n)$

This requires

$$
[x^0]f(x)=0.
$$

Suppose

$$
g(x)=\exp(f(x)).
$$

Then

$$
\ln(g(x))-f(x)=0.
$$

Construct

$$
h(x,f)=\ln(x)-f.
$$

Using Newton iteration, if $g_0(x)$ is already correct modulo $x^n$, then

$$
g(x)\equiv g_0(x)\bigl(1-\ln(g_0(x))+f(x)\bigr)\pmod{x^{2n}}.
$$

## 4.4 Example: [Nowcoder Practice Contest 24 F — Tricycle](https://ac.nowcoder.com/acm/contest/157/F)

The volume bound is $5\times 10^4$, while each item type has up to $10^5$ copies, so we can safely treat it as a complete knapsack.

For an item of volume $v_i$, the ordinary generating function is

$$
1+x^{v_i}+x^{2v_i}+\cdots=\frac{1}{1-x^{v_i}}.
$$

Thus the total generating function is

$$
F(x)=\prod_{i=1}^{n}\frac{1}{1-x^{v_i}}
=\sum_{k=0}^{\infty}a_kx^k,
$$

and we want $a_1,a_2,\dots,a_m$ modulo $19260817$.

Use logarithm first:

$$
\ln(1+x)=x-\frac{x^2}{2}+\frac{x^3}{3}-\frac{x^4}{4}+\cdots
$$

$$
-\ln(1-x)=x+\frac{x^2}{2}+\frac{x^3}{3}+\cdots
$$

Then

$$
\begin{aligned}
g(x)=\ln F(x)
&=\sum_{i=1}^{n}\bigl[-\ln(1-x^{v_i})\bigr] \\
&=\sum_{i=1}^{n}\sum_{j=1}^{\infty}\frac{x^{jv_i}}{j} \\
&=\sum_{k=1}^{m}\sum_{j=1}\frac{x^{kj}}{j}\cdot \#\,[v_i=k].
\end{aligned}
$$

This takes $O(m\log m)$ if we only keep terms up to degree $m$.

Then

$$
F(x)=\exp(g(x))=\sum_{k=0}^{m}a_kx^k.
$$

This polynomial exponential can be computed in $O(m\log m)$ using CDQ divide and conquer + fast polynomial multiplication.

Since $19260817$ is a bad modulus for ordinary NTT, use either:

1. multi-mod NTT + CRT;
2. FFT + splitting.

The following implementation uses three-mod NTT + CRT.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

// Three NTT moduli + CRT
static const int M1 = 998244353, G1 = 3;
static const int M2 = 1004535809, G2 = 3;
static const int M3 = 469762049,  G3 = 3;

template<int mod, int G>
struct NTT {
    vector<int> rev, roots{0,1};
    static ll mod_pow(ll a, ll e) {
        ll r = 1;
        while (e) {
            if (e & 1) r = r * a % mod;
            a = a * a % mod;
            e >>= 1;
        }
        return r;
    }
    void dft(vector<int>& a) {
        int n = a.size();
        if ((int)rev.size() != n) {
            rev.assign(n, 0);
            for (int i = 1; i < n; i++)
                rev[i] = (rev[i>>1] >> 1) | ((i & 1) * (n >> 1));
        }
        for (int i = 0; i < n; i++) if (i < rev[i]) swap(a[i], a[rev[i]]);
        if ((int)roots.size() < n) {
            int k = __builtin_ctz(roots.size());
            roots.resize(n);
            while ((1 << k) < n) {
                ll e = mod_pow(G, (mod - 1) >> (k + 1));
                for (int i = 1 << (k - 1); i < (1 << k); ++i) {
                    roots[2 * i]     = roots[i];
                    roots[2 * i + 1] = (ll)roots[i] * e % mod;
                }
                ++k;
            }
        }
        for (int len = 1; len < n; len <<= 1) {
            for (int i = 0; i < n; i += len << 1) {
                for (int j = 0; j < len; ++j) {
                    int u = a[i + j];
                    int v = (ll)a[i + j + len] * roots[len + j] % mod;
                    a[i + j]       = u + v < mod ? u + v : u + v - mod;
                    a[i + j + len] = u - v >= 0 ? u - v : u - v + mod;
                }
            }
        }
    }
    void idft(vector<int>& a) {
        int n = a.size();
        reverse(a.begin() + 1, a.end());
        dft(a);
        ll inv_n = mod_pow(n, mod - 2);
        for (int i = 0; i < n; i++) a[i] = a[i] * inv_n % mod;
    }
    vector<int> conv(vector<int> a, vector<int> b) {
        int need = a.size() + b.size() - 1;
        int n = 1; while (n < need) n <<= 1;
        a.resize(n); b.resize(n);
        dft(a); dft(b);
        for (int i = 0; i < n; i++) a[i] = (ll)a[i] * b[i] % mod;
        idft(a);
        a.resize(need);
        return a;
    }
};
using NTT1 = NTT<M1, G1>;
using NTT2 = NTT<M2, G2>;
using NTT3 = NTT<M3, G3>;

// CRT merge of the three NTT outputs
vector<int> multiply(const vector<int>& A, const vector<int>& B, int mod) {
    NTT1 n1; NTT2 n2; NTT3 n3;
    auto c1 = n1.conv(A, B);
    auto c2 = n2.conv(A, B);
    auto c3 = n3.conv(A, B);
    int n = c1.size();
    vector<int> C(n);
    ll inv12 = NTT2::mod_pow(M1, M2 - 2);
    ll inv123 = NTT3::mod_pow((ll)M1 * M2 % M3, M3 - 2);
    ll m12 = (ll)M1 * M2;
    for (int i = 0; i < n; i++) {
        ll x1 = c1[i];
        ll x2 = (c2[i] - x1) % M2 * inv12 % M2;
        if (x2 < 0) x2 += M2;
        ll x3 = (c3[i] - (x1 + x2 * M1) % M3) % M3 * inv123 % M3;
        if (x3 < 0) x3 += M3;
        ll x = x1 + x2 * M1 + x3 * m12;
        C[i] = x % mod;
    }
    return C;
}

const int M = 19260817;

int main(){
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m;
    cin >> n >> m;
    const int M = 19260817;
    vector<int> freq(m + 1); // frequency of each volume
    for (int i = 0; i < n; i++){
        int v; cin >> v;
        if (v <= m) freq[v]++;
    }

    // preprocess modular inverses
    vector<int> inv(m + 1);
    inv[1] = 1;
    for (int i = 2; i <= m; i++) inv[i] = (M - (ll)(M / i) * inv[M % i] % M) % M;

    // compute g[k] = sum_{d | k} freq[d] * inv[k / d]
    vector<int> g(m + 1);
    for (int d = 1; d <= m; d++) if (freq[d]){
        for (int k = d; k <= m; k += d){
            int j = k / d;
            g[k] = (g[k] + (ll)freq[d] * inv[j]) % M;
        }
    }

    // ----- CDQ divide and conquer for f = exp(g) -----
    vector<int> f(m + 1);
    vector<int> gp(m);
    for (int i = 0; i < m; i++) gp[i] = (ll)(i + 1) * g[i + 1] % M;

    function<void(int,int)> cdq = [&](int l, int r){
        if (l == r) {
            if (l == 0) f[0] = 1;
            return;
        }
        int mid = (l + r) >> 1;
        cdq(l, mid);
        int len1 = mid - l + 1;
        int len2 = r - l;
        vector<int> A(len1), B(len2);
        for (int i = 0; i < len1; i++) A[i] = f[l + i];
        for (int i = 0; i < len2; i++) B[i] = gp[i];
        auto C = multiply(A, B, M);
        for (int k = mid + 1; k <= r; k++){
            ll t = C[k - 1 - l];
            f[k] = (f[k] + t * inv[k]) % M;
        }
        cdq(mid + 1, r);
    };
    cdq(0, m);
    // -----------------------------------------------

    ll ans = 0;
    for (int k = 1; k <= m; k++) ans = (ans + f[k]) % M;
    cout << ans << "\n";
    return 0;
}
```
