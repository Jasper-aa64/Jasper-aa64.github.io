---
title: "Combinatorics #2-ex2: Cyclic Convolution"
date: 2026-04-25
slug: "combinatorics-2-ex2-cyclic-convolution"
description: "Cyclic convolution definition, FFT/NTT implementation for n=2^k, zero-padding, why n must be a power of two, and the fold-back technique for arbitrary n."
summary: "Cyclic convolution definition, FFT/NTT implementation for n=2^k, zero-padding, why n must be a power of two, and the fold-back technique for arbitrary n."
categories: [Combinatorics]
tags: [math, combinatorics, fft, ntt, convolution, cyclic, polynomial]
math: true
toc: true
---

# Cyclic Convolution

Given two sequences of length $n$ ($n=2^k$):

$$a=(a_0,a_1,\dots,a_{n-1}),\quad b=(b_0,b_1,\dots,b_{n-1})$$

Running FFT/NTT directly on length $n$ (without zero-padding) yields the **cyclic convolution**:

$$\boxed{c_i=\sum_{(j+k)\%n=i}a_j\cdot b_k}\qquad\text{equivalently}\qquad\boxed{c_i=\sum_{j=0}^{n-1}a_j\,b_{(i-j)\%n}}$$

**Contrast with linear convolution:** ordinary (linear) convolution takes $c_k=\sum_{i+j=k}a_i b_j$ with no modular reduction. Cyclic convolution wraps the indices around modulo $n$.

---

# 1 FFT $O(n\log n)$ Implementation (Radix-2, $n=2^k$)

```cpp
#include <bits/stdc++.h>
using namespace std;
using cd = complex<double>;
const double PI = acos(-1);

void fft(vector<cd>& a, bool invert) {
    int n = a.size();
    vector<int> rev(n);
    for (int i = 0; i < n; i++) {
        rev[i] = (rev[i>>1] >> 1) | ((i&1) * (n>>1));
        if (i < rev[i]) swap(a[i], a[rev[i]]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = 2 * PI / len * (invert ? -1 : 1);
        cd wlen(cos(ang), sin(ang));
        for (int i = 0; i < n; i += len) {
            cd w(1);
            for (int j = 0; j < len/2; j++) {
                cd u = a[i+j];
                cd v = a[i+j+len/2] * w;
                a[i+j]       = u + v;
                a[i+j+len/2] = u - v;
                w *= wlen;
            }
        }
    }
    if (invert) {
        for (cd& x : a) x /= n;
    }
}

// Cyclic convolution of length n = 2^k
vector<double> circularConvolutionFFT(const vector<double>& a,
                                      const vector<double>& b) {
    int n = a.size();  // assumes a.size() == b.size() == 2^k
    vector<cd> fa(a.begin(), a.end()),
                fb(b.begin(), b.end());
    fft(fa, false);  // no zero-padding: FFT on length n directly
    fft(fb, false);
    for (int i = 0; i < n; i++) fa[i] *= fb[i];
    fft(fa, true);
    vector<double> c(n);
    for (int i = 0; i < n; i++) c[i] = fa[i].real();
    return c;
}
```

**Why this gives cyclic convolution:**

1. `fft(..., false)` evaluates each sequence at the $n$-th roots of unity $\omega_n^0,\dots,\omega_n^{n-1}$.
2. Pointwise multiplication gives $\{C(\omega_n^i)\}$.
3. `fft(..., true)` (IFFT) recovers the coefficients $\{C_i\}$.
4. Because no zero-padding was added, the FFT implicitly wraps indices modulo $n$, producing the cyclic convolution.

---

# 2 Zero-Padding to the Next $2^k$

Radix-2 FFT requires $n=2^k$. If the input length is not a power of two, **zero-pad**:

```cpp
int L = /* original length */;
int N = 1;
while (N < L) N <<= 1;   // smallest 2^k >= L

vector<cd> fa(N), fb(N);
for (int i = 0; i < L; i++) { fa[i] = a[i]; fb[i] = b[i]; }
// fa[L..N-1] and fb[L..N-1] default to 0
```

For **linear convolution** (result length $L_a+L_b-1$), also ensure:

$$N\ge L_a+L_b-1$$

then round up to the next $2^k$.

---

# 3 Why $n$ Must Be a Power of Two

1. **Recursive splitting:** Radix-2 FFT splits a length-$n$ DFT into two length-$n/2$ sub-DFTs at every level. If $n$ is odd, you cannot split evenly.

2. **Bit-reversal permutation:** the reordering step requires a fixed binary width for the indices (e.g. $n=16=2^4$ means all indices are 4-bit). The twiddle factors $\omega_n^i$ and $\omega_{n/2}^i$ align precisely, making the standard butterfly loop `for (len=2; len<=n; len*=2)` correct.

---

# 4 Cyclic Convolution via NTT ($n=2^k$)

When modular arithmetic is needed, use NTT instead of FFT:

```cpp
// Cyclic convolution: assumes a.size() == b.size() == N, N = 2^k
// Returns length-N result (a ⊛ b) modulo MOD
vector<ll> circularConvolutionNTT(vector<ll> a, vector<ll> b) {
    int N = a.size();
    ntt(a, false);
    ntt(b, false);
    for (int i = 0; i < N; i++) a[i] = a[i] * b[i] % MOD;
    ntt(a, true);
    return a;
}
```

Same idea as FFT: run NTT on exactly length $N$ (no zero-padding) to get the cyclic convolution modulo the NTT prime.

---

# 5 Cyclic Convolution for Arbitrary $n$ — Fold-Back Method

When $n$ is not a power of two, compute the **linear convolution** first, then fold the high-index terms back modulo $n$:

$$\boxed{c_i=(a*b)_{\text{lin}}[i]+(a*b)_{\text{lin}}[i+n],\quad 0\le i\lt n}$$

**Why it works:** The linear convolution of two length-$n$ arrays has indices $j+k\in[0,2n-2]$. The cyclic convolution wants $(j+k)\bmod n$. For each target index $i$:

- Terms with $j+k=i$ (already $\lt n$) contribute directly.
- Terms with $j+k=i+n$ (the "overflow") are exactly those that wrap around to $i$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

const int MOD = 998244353;
const int _g = 3;

ll modexp(ll a, ll e) { /* fast exponentiation, omitted */ }

void ntt(vector<ll>& a, bool invert) {
    int n = a.size();
    vector<int> rev(n);
    for (int i = 0; i < n; i++) {
        rev[i] = (rev[i>>1] >> 1) | ((i&1) * (n>>1));
        if (i < rev[i]) swap(a[i], a[rev[i]]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        ll wlen = modexp(_g, (MOD-1)/len * (invert ? -1 : 1) % (MOD-1));
        for (int i = 0; i < n; i += len) {
            ll w = 1;
            for (int j = 0; j < len/2; j++) {
                ll u = a[i+j];
                ll v = a[i+j+len/2] * w % MOD;
                a[i+j]       = u+v < MOD ? u+v : u+v-MOD;
                a[i+j+len/2] = u-v >= 0  ? u-v : u-v+MOD;
                w = w * wlen % MOD;
            }
        }
    }
    if (invert) {
        ll inv_n = modexp(n, MOD-2);
        for (ll& x : a) x = x * inv_n % MOD;
    }
}

// Cyclic convolution for arbitrary n via linear convolution + fold-back
vector<ll> circularConvolution(const vector<ll>& a, const vector<ll>& b) {
    int n = a.size();
    int need = 2*n - 1;           // linear convolution length
    int N = 1;
    while (N < need) N <<= 1;     // pad to next 2^k

    vector<ll> A(N), B(N);
    for (int i = 0; i < n; i++) { A[i] = a[i]; B[i] = b[i]; }

    ntt(A, false); ntt(B, false);
    for (int i = 0; i < N; i++) A[i] = A[i] * B[i] % MOD;
    ntt(A, true);  // A[0..need-1] holds the linear convolution

    // Fold back: add overflow terms to their residues
    vector<ll> c(n);
    for (int i = 0; i < n; i++) {
        ll v = A[i];
        if (i + n < need) v = (v + A[i + n]) % MOD;
        c[i] = v;
    }
    return c;
}

int main(){
    int n = 11;
    vector<ll> a(n), b(n);
    // read a[0..10], b[0..10]
    auto c = circularConvolution(a, b);
    for (int i = 0; i < n; i++) cout << c[i] << (i+1<n?' ':'\n');
}
```

**Summary of the fold-back technique:**

| Step | Action |
|---|---|
| 1 | Zero-pad $a,b$ from length $n$ to $N\ge2n-1$ |
| 2 | NTT → pointwise multiply → INTT → linear convolution in $A[0\ldots2n-2]$ |
| 3 | For each $i\in[0,n)$: $c[i]=A[i]+A[i+n]$ (if $i+n\lt2n-1$) |
