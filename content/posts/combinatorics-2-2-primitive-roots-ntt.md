---
title: "Combinatorics #2.2: Primitive Roots, Discrete Logarithm, NTT, Divide-and-Conquer NTT"
date: 2026-04-25
slug: "combinatorics-2-2-primitive-roots-ntt"
description: "Order and primitive roots (Euler's theorem, BSGS, exBSGS), discrete index as logarithm analogue, SGU 261 Discrete Roots, NTT theory and templates, divide-and-conquer NTT (product tree), Wannafly D team selection, Nowcoder 50F generating functions."
summary: "Order and primitive roots (Euler's theorem, BSGS, exBSGS), discrete index as logarithm analogue, SGU 261 Discrete Roots, NTT theory and templates, divide-and-conquer NTT (product tree), Wannafly D team selection, Nowcoder 50F generating functions."
categories: [Combinatorics]
tags: [math, combinatorics, ntt, primitive-root, bsgs, discrete-log, divide-and-conquer, generating-function, fft]
math: true
toc: true
---

# 1 Order and Primitive Roots

> **[Theorem — Euler's Theorem]**
>
> If positive integers $m,a$ satisfy $\gcd(a,m)=1$, then $a^{\varphi(m)}\equiv1\pmod{m}$.
>
> - The sequence $a^1,a^2,a^3,\dots$ is periodic modulo $m$ with period dividing $\varphi(m)$.
> - This need not be the shortest period. For example, $2^1,2^2,2^3,\dots\pmod7$ gives $2,4,1,2,4,\dots$, which has period 3, not $\varphi(7)=6$.

> **[Definition — Order]**
>
> Let $\gcd(a,m)=1$. The **order** of $a$ modulo $m$ is the smallest positive integer $n$ with $a^n\equiv1\pmod{m}$, denoted $\delta_m(a)$.

> **[Definition — Primitive Root]**
>
> If $\delta_m(a)=\varphi(m)$, then $a$ is a **primitive root** modulo $m$.
>
> For example, 3 is a primitive root modulo 7: $\delta_7(3)=\varphi(7)=6$.

# 2 Properties of the Order

$$
\begin{split}&\text{Assume}\ \gcd(a,m)=1,\ \delta=\delta_m(a).\ \text{Then:}\\ &\quad\bullet\ a^0,a^1,\dots,a^{\delta-1}\ \text{are pairwise distinct modulo}\ m\\ &\quad\bullet\ a^\gamma\equiv a^{\gamma'}\pmod{m}\iff\gamma\equiv\gamma'\pmod{\delta}\\ &\quad\bullet\ \delta\mid\varphi(m)\end{split}
$$

# 3 Existence and Testing of Primitive Roots

> **[Theorem — Existence of Primitive Roots]**
>
> A primitive root exists modulo $m$ if and only if $m\in\{2,4,p^a,2p^a\}$ for some odd prime $p$.

```cpp
#include <bits/stdc++.h>
using namespace std; using i64 = long long;

bool isPrimePower(i64 x){
    if (x < 2) return false;
    for (i64 p = 2; p * p <= x; ++p){
        if (x % p == 0){
            while (x % p == 0) x /= p;
            return x == 1;
        }
    }
    return true;
}

bool hasPrimitiveRoot(i64 n){
    if (n < 2) return false;
    if (n == 2 || n == 4) return true;
    if (n & 1) return isPrimePower(n);
    if (n % 4 == 0) return false;
    return isPrimePower(n / 2);
}

int main(){
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    for (i64 n; cin >> n; )
        cout << (hasPrimitiveRoot(n) ? "YES\n" : "NO\n");
}
```

> **[Theorem — Characterization of Primitive Roots]**
>
> Let $m>1$ and $\gcd(g,m)=1$. Then $g$ is a primitive root modulo $m$ if and only if for every prime factor $q_i$ of $\varphi(m)$:
>
> $$g^{\varphi(m)/q_i}\not\equiv 1\pmod{m}$$
>
> **Intuition:** If the exponent cannot be reduced by removing any single prime factor, the order must already equal $\varphi(m)$.

> **[Example — Luogu P6091: Primitive Root]**
>
> Given $n$, find all primitive roots of $n$. With output parameter $d$: if there are $c$ primitive roots $g_1\lt g_2\lt\cdots\lt g_c$, output $g_d,g_{2d},\ldots,g_{\lfloor c/d\rfloor d}$.

```cpp
#include<bits/stdc++.h>
using namespace std;

const int N = 1000000 + 7;
int pr[N], ph[N], fc[9], u[11], v[11];
bool f[N], b[N], p[N], q[N];

void init(int n) {
    b[2] = b[4] = ph[1] = 1;
    int t = 0;
    for (int i = 2; i <= n; ++i) {
        if (!f[i]) { pr[++t] = i; ph[i] = i - 1; }
        for (int j = 1, k; j <= t && (k = i * pr[j]) <= n; ++j) {
            f[k] = true;
            if (i % pr[j] == 0) { ph[k] = ph[i] * pr[j]; break; }
            ph[k] = ph[i] * ph[pr[j]];
        }
    }
    for (int i = 2; i <= t; ++i) {
        for (long long x = pr[i]; x <= n; x *= pr[i]) b[x] = true;
        for (long long x = 2LL * pr[i]; x <= n; x *= pr[i]) b[x] = true;
    }
}

int qp(int a, int b, int p) {
    int r = 1;
    while (b) { if (b & 1) r = int(1LL*r*a%p); a = int(1LL*a*a%p); b >>= 1; }
    return r;
}

int main() {
    int T, n = 0, m, d;
    scanf("%d", &T);
    for (int i = 1; i <= T; ++i) { scanf("%d %d", &u[i], &v[i]); n = max(n, u[i]); }
    init(n);

    for (int o = 1; o <= T; ++o) {
        n = u[o]; d = v[o];
        if (!b[n]) { puts("0\n"); continue; }

        m = ph[n];
        int tmp = m, t = 0;
        for (int i = 1; pr[i]*pr[i] <= tmp; ++i)
            if (tmp % pr[i] == 0) {
                fc[++t] = pr[i];
                while (tmp % pr[i] == 0) tmp /= pr[i];
                for (int k = pr[i]; k <= m; k += pr[i]) p[k] = true;
            }
        if (tmp > 1) { fc[++t] = tmp; for (int k = tmp; k <= m; k += tmp) p[k] = true; }

        int g;
        for (g = 1; ; ++g) {
            while (qp(g, m, n) != 1) ++g;
            int i; for (i = 1; i <= t; ++i) if (qp(g, m/fc[i], n) == 1) break;
            if (i > t) break;
        }

        int cnt = 0;
        for (int k = 1, cur = 1; k <= m; ++k) {
            cur = int(1LL * cur * g % n);
            if (!p[k]) { q[cur] = true; ++cnt; } else { p[k] = false; }
        }
        printf("%d\n", cnt);
        for (int i = 1, seen = 0; i < n; ++i)
            if (q[i]) { q[i] = false; if (++seen == d) { printf("%d ", i); seen = 0; } }
        puts("");
    }
    return 0;
}
```

# 4 Discrete Index (Discrete Logarithm)

> **[Definition — Discrete Index]**
>
> For prime $p$ with primitive root $g$: the elements $g^0,g^1,\dots,g^{p-2}$ are a permutation of $1,\dots,p-1$ modulo $p$. If $g^c\equiv x\pmod{p}$, then $c$ is the **discrete index** of $x$: $\operatorname{ind}_g(x)=c$.
>
> The index mimics the real logarithm: it converts multiplication into addition modulo $p-1$.
>
> **Computing the index:** Baby-Step Giant-Step **(BSGS)** — solve $a^x\equiv b\pmod m$ for the smallest non-negative $x$.
>
> - Standard BSGS requires $\gcd(a,m)=1$.
> - General case: use **exBSGS**.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

ll qp(ll a,ll e,ll m){ __int128 A=(a%m+m)%m,r=1; while(e){ if(e&1) r=r*A%m; A=A*A%m; e>>=1;} return (ll)r; }

ll exgcd(ll a, ll b, ll &x, ll &y) {
    if (!b) { x = 1; y = 0; return a >= 0 ? a : -a; }
    ll x1, y1; ll g = exgcd(b, a % b, x1, y1);
    x = y1; y = x1 - (a / b) * y1; return g;
}

ll modinv(ll a, ll mod) {
    ll x, y; ll g = exgcd(a, mod, x, y);
    if (g != 1) return -1;
    x %= mod; if (x < 0) x += mod; return x;
}

ll bsgs(ll a,ll b,ll m){
    a%=m; b%=m; if(m==1||b==1%m) return 0;
    ll n=(ll)ceil(sqrt((long double)m));
    vector<pair<ll,ll>> bs; bs.reserve(n);
    ll cur=1%m; for(ll j=0;j<n;j++){ bs.push_back({cur,j}); cur=(ll)((__int128)cur*a%m); }
    sort(bs.begin(),bs.end());
    vector<pair<ll,ll>> baby; baby.reserve(bs.size());
    for(auto &p:bs) if(baby.empty()||baby.back().first!=p.first) baby.push_back(p);
    ll inv_an=modinv(qp(a,n,m),m); if(inv_an==-1) return -1;
    cur=b%m;
    for(ll i=0;i<=n;i++){
        auto it=lower_bound(baby.begin(),baby.end(),make_pair(cur,(ll)-1));
        if(it!=baby.end()&&it->first==cur) return i*n+it->second;
        cur=(ll)((__int128)cur*inv_an%m);
    }
    return -1;
}

ll exbsgs(ll a,ll b,ll m){
    if(m==1) return 0;
    a=(a%m+m)%m; b=(b%m+m)%m; if(b==1%m) return 0;
    if(a%m==0) return b==0?1:-1;
    ll cnt=0,t=1%m;
    while(true){
        ll g=gcd(a,m); if(g==1) break; if(b%g) return -1;
        m/=g; b/=g; t=(ll)((__int128)t*(a/g)%m); cnt++; if(t==b) return cnt;
    }
    ll inv_t=modinv(t%m,m); if(inv_t==-1) return -1;
    ll rhs=(ll)((__int128)b*inv_t%m);
    ll res=bsgs(a%m,rhs,m); return res==-1?-1:res+cnt;
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    ll a, b, m;
    while (cin >> a >> b >> m) {
        ll x = exbsgs(a, b, m);
        if (x == -1) cout << "no solution\n";
        else cout << x << "\n";
    }
    return 0;
}
```

> **[Key Fact ⭐ — The modulus shifts from P to φ(P)]**
>
> When $P$ is prime, $\operatorname{ord}(g)=P-1=\varphi(P)$. The discrete logarithm map $\operatorname{ind}_g(g^t)=t\pmod{P-1}$ converts multiplication in $\mathbb{F}_P^*$ into addition in $\mathbb{Z}_{P-1}$.
>
> **Why:** The primitive root $g$ satisfies $g^{P-1}\equiv1$ and $g^n\equiv1\iff(P-1)\mid n$. This is the exact point where multiplicative congruence becomes additive congruence modulo the order.

> **[Example — SGU 261: Discrete Roots](https://vjudge.net/problem/SGU-261)**
>
> Find all roots of $x^K\equiv A\pmod{P}$, where $P,K$ are both prime. $(2\le P\le10^9,\ 2\le K\le10^5,\ 0\le A\lt P)$
>
> **Idea:** in the reals, $x^K=A\Rightarrow x=A^{1/K}$. With discrete logarithms, replace $\ln$ with ind (modulus shifts from $P$ to $P-1$):
>
> $$K\cdot\operatorname{ind}(x)\equiv\operatorname{ind}(A)\pmod{P-1}$$
>
> **Algorithm:**
>
> 1. **$A=0$:** the only root is $x=0$ (since $P$ is prime).
> 2. **$A\ne0$:** write $x=g^t$, $A=g^b$. The equation becomes $Kt\equiv b\pmod{P-1}$.
> 3. **Linear congruence:** let $d=\gcd(K,P-1)$. Solvable iff $d\mid b$. The base solution is $t_0\equiv b_1K_1^{-1}\pmod{M_1}$. There are $d$ roots: $x_i=g^{t_0+iM_1}\bmod P$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long; using i128 = __int128_t;

// (qp, exgcd, modinv, factorize_distinct, primitive_root, bsgs defined above)

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    ll P, K, A; cin >> P >> K >> A;

    if (A == 0) { cout << 1 << "\n0\n"; return 0; }

    ll g = primitive_root(P);
    ll indA = bsgs(g, A, P);
    if (indA == -1) { cout << 0 << "\n"; return 0; }

    ll mod = P - 1;
    ll d = gcd(K, mod);
    if (indA % d != 0) { cout << 0 << "\n"; return 0; }

    ll K1 = K/d, M1 = mod/d, indA1 = indA/d;
    ll x, y; exgcd(K1, M1, x, y);
    x = (x%mod + mod)%mod;
    ll base_t = (i128)indA1 * x % M1;

    set<ll> roots;
    for (ll i = 0; i < d; ++i) {
        ll t = (base_t + i * M1) % (P - 1);
        roots.insert(qp(g, t, P));
    }
    cout << roots.size() << "\n";
    for (auto r : roots) cout << r << ' ';
    cout << "\n";
    return 0;
}
```

---

# 5 Number Theoretic Transform (NTT)

Replace the complex roots of unity $\omega_n$ with modular primitive roots. The DFT/IDFT derivation still holds over $\mathbb{Z}_p$ instead of $\mathbb{C}$.

- **Advantages:** fast; exact (integer arithmetic, no floating-point error)
- **Limitation:** the modulus must be a prime of the form $p=r\cdot2^t+1$

Common NTT-friendly primes (all have primitive root $g=3$):

| Prime | Factored form | Max array size |
|---|---|---|
| 998244353 | $119\cdot2^{23}+1$ | $\sim8\times10^6$ |
| 1004535809 | $479\cdot2^{21}+1$ | $>10^9$ (as value) |
| 65537 | $2^{16}+1$ | $65536$ |

## 5.1 Template

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int M = 998244353;
const int _g = 3;

int qp(int a, ll e=M-2) {
    int r = 1;
    while (e) { if (e & 1) r = (ll)r*a%M; a = (ll)a*a%M; e >>= 1; }
    return r;
}

void ntt(vector<int>& a, int invert) {
    int n = a.size();
    vector<int> rev(n);
    for (int i = 0; i < n; ++i) {
        rev[i] = (rev[i>>1] >> 1) | ((i&1) * (n>>1));
        if (i < rev[i]) swap(a[i], a[rev[i]]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        int wn = qp(_g, (M-1)/len);
        if (invert) wn = qp(wn);
        for (int i = 0; i < n; i += len) {
            ll w = 1;
            for (int j = 0; j < len/2; ++j) {
                int u = a[i+j], v = (ll)a[i+j+len/2]*w%M;
                a[i+j] = u+v < M ? u+v : u+v-M;
                a[i+j+len/2] = u-v >= 0 ? u-v : u-v+M;
                w = w*wn%M;
            }
        }
    }
    if (invert) { int inv_n = qp(n); for (int &x : a) x = (ll)x*inv_n%M; }
}

vector<int> multiply(vector<int> a, vector<int> b) {
    int sz = 1;
    while (sz < (int)a.size() + (int)b.size() - 1) sz <<= 1;
    a.resize(sz); b.resize(sz);
    ntt(a, 0); ntt(b, 0);
    for (int i = 0; i < sz; ++i) a[i] = (ll)a[i]*b[i]%M;
    ntt(a, 1);
    return a;
}
```

## 5.2 Faster version (precomputed roots)

```cpp
const int M = 998244353; const int _g = 3;

int qp(int a, ll e=M-2) {
    int r = 1;
    while (e) { if (e & 1) r = (ll)r*a%M; a = (ll)a*a%M; e >>= 1; }
    return r;
}

void ntt(vector<int> &a, bool inv) {
    int n = a.size();
    if (n == 1) return;
    int L = __builtin_ctz(n);
    vector<int> rev(n); rev[0] = 0;
    for (int i = 1; i < n; i++) rev[i] = (rev[i>>1]>>1) | ((i&1)<<(L-1));
    for (int i = 0; i < n; i++) if (i < rev[i]) swap(a[i], a[rev[i]]);

    static vector<int> roots{0, 1};
    if ((int)roots.size() < n) {
        int k = __builtin_ctz(roots.size());
        roots.resize(n);
        while ((1 << k) < n) {
            int e = qp(_g, (M-1) >> (k+1));
            for (int i = 1<<(k-1); i < (1<<k); i++) {
                roots[2*i] = roots[i];
                roots[2*i+1] = (ll)roots[i]*e%M;
            }
            k++;
        }
    }
    for (int len = 1; len < n; len <<= 1)
        for (int i = 0; i < n; i += len<<1)
            for (int j = 0; j < len; j++) {
                int u = a[i+j], v = (ll)a[i+j+len]*roots[len+j]%M;
                a[i+j] = u+v<M?u+v:u+v-M;
                a[i+j+len] = u-v>=0?u-v:u-v+M;
            }
    if (inv) {
        reverse(a.begin()+1, a.end());
        int inv_n = qp(n);
        for (int &x : a) x = (ll)x*inv_n%M;
    }
}

vector<int> multiply(vector<int> a, vector<int> b) {
    int sz = (int)a.size()+(int)b.size()-1, n = 1;
    while (n < sz) n <<= 1;
    a.resize(n); b.resize(n);
    ntt(a, false); ntt(b, false);
    for (int i = 0; i < n; i++) a[i] = (ll)a[i]*b[i]%M;
    ntt(a, true); a.resize(sz);
    return a;
}
```

---

# 6 Divide-and-Conquer FFT / NTT

> **[Problem 1: Product of linear factors]**
>
> Compute $f(x)=\prod_{i=1}^n(x-a_i)\bmod 998244353$, $n\le10^5$.
>
> The naïve $O(n^2)$ approach multiplies one factor at a time. Correct approach: **Divide-and-Conquer NTT (Product Tree)**
>
> 1. **Build a segment tree:** leaf $[i,i]$ holds $(x-a_i)$; internal node $[l,r]$ holds the product of its children.
> 2. **Merge children** with NTT polynomial multiplication at cost $O(d\log d)$.
> 3. **Complexity:** tree height $O(\log n)$, total degree per level $O(n)$ → $O(n\log^2 n)$ overall.

```cpp
#include <bits/stdc++.h>
using namespace std;
const int P=998244353;

// (ntt, multiply omitted)

vector<int> build(int l, int r, const vector<int>& A){
    if(l==r) return { (-A[l]+P)%P, 1 };
    int m=(l+r)>>1;
    return multiply(build(l,m,A), build(m+1,r,A));
}

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n; cin>>n;
    vector<int> A(n);
    for(int i=0;i<n;i++) cin>>A[i];
    auto F = build(0,n-1,A);
    for(int i=0;i<=n;i++) cout<<F[i]<<(i==n?'\n':' ');
}
```

> **[Problem 2: General product of polynomials]**
>
> Compute $f(x)=\prod_{i=1}^n f_i(x)\bmod 998244353$, $\sum\deg(f_i)\le10^5$.
>
> Multiplying sequentially gives $O(n^2\log n)$ — worse than brute force.
>
> - **Approach 1:** Divide-and-conquer NTT, $O(n\log^2 n)$.
> - **Approach 2:** Huffman-style NTT — always merge the two lowest-degree polynomials, same complexity.

**Divide-and-conquer version:**

```cpp
vector<int> build(int l, int r, const vector<vector<int>>& F) {
    if (l == r) return F[l];
    int m = (l+r)>>1;
    return multiply(build(l,m,F), build(m+1,r,F));
}
```

**Huffman version:**

```cpp
struct Cmp {
    bool operator()(const vector<int>& a, const vector<int>& b) const {
        return a.size() > b.size();
    }
};
priority_queue<vector<int>, vector<vector<int>>, Cmp> pq;
// ... push all f_i into pq, then:
while (pq.size() > 1) {
    auto A = move(pq.top()); pq.pop();
    auto B = move(pq.top()); pq.pop();
    pq.push(multiply(A, B));
}
```

> **[Example — Wannafly Contest 20 D: Choosing Teammates](https://ac.nowcoder.com/acm/contest/133/D)**
>
> $m$ groups, group $i$ has $s_i$ people. Choose exactly $k$ people with at least 1 from each group. Count ways modulo 998244353. People are distinguishable. $(m\le k\le\sum s_i=n\le10^5)$
>
> **Stars-and-bars vs. distinguishable:** In stars-and-bars, identical balls give $\binom{k+m-1}{m-1}$. Here people are distinct, so group $i$ generates:
>
> $$F_i(x)=(1+x)^{s_i}-1\qquad\text{(subtract the "pick nobody" constant)}$$
>
> Answer: $[x^k]\prod_i F_i(x)$. Brute-force DP is $O(nk)\approx10^{10}$ — infeasible. Use **divide-and-conquer NTT** in $O(n\log n\cdot\log m)$.

```cpp
vector<int> build(int l, int r) {
    if (l == r) return polys[l];
    int m = (l + r) >> 1;
    return multiply_capped(build(l,m), build(m+1,r), K);
}
```

> **[Example — Nowcoder Practice 50 F](https://ac.nowcoder.com/acm/contest/1080/F)**
>
> $n$ matches; match $i$ has $a_i$ Protoss and $b_i$ Zerg units. Each match you choose Protoss or Zerg:
>
> - Choosing Zerg: $2^{b_i}-1$ deployment options, contributes 0 to Protoss count.
> - Choosing Protoss: $\binom{a_i}{t}$ ways to deploy $t\in[1,a_i]$ units, contributing $t$ to Protoss count.
>
> Match $i$ generating function: $G_i(x)=(1+x)^{a_i}+2^{b_i}-2$
>
> Compute $F(x)=\prod_i G_i(x)$ and output all coefficients modulo 998244353.

```cpp
// build G_i for each match, then divide-and-conquer NTT:
vector<vector<int>> G(n);
for (int i = 0; i < n; i++) {
    G[i].assign(a[i]+1, 0);
    int z = (qp(2, b[i]) - 1 + MOD) % MOD;
    G[i][0] = z;
    for (int t = 1; t <= a[i]; t++) G[i][t] = C(a[i], t);
}

function<vector<int>(int,int)> solve = [&](int l, int r) -> vector<int> {
    if (l == r) return G[l];
    int m = (l+r)>>1;
    return multiply(solve(l,m), solve(m+1,r));
};

auto F = solve(0, n-1);
F.resize(S+1);
for (int i = 0; i <= S; i++) cout << F[i] << ' ';
```
