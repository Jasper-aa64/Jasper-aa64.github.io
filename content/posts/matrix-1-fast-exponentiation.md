---
title: "Matrix #1: Matrix Fast Power — Linear Recurrence, DP Semirings & Kitamasa"
date: 2026-04-28T00:00:00+08:00
slug: "matrix-1-fast-exponentiation"
description: "Matrix multiplication and fast power; four patterns for encoding linear recurrences; four DP semirings (counting, boolean, min-plus, max-plus) with full templates; matrix + segment tree; Kitamasa algorithm."
summary: "Matrix fast power for linear recurrences (4 patterns), 4 semiring templates (count/bool/min-plus/max-plus), matrix+segment tree for range-add Fibonacci queries, Kitamasa O(k²logn) and NTT O(k log²k logn)."
categories: [Matrix]
tags: [math, matrix, fast-power, linear-recurrence, dp, segment-tree, kitamasa, semiring]
math: true
toc: true
---

# 1 Matrix Multiplication & Fast Power

## 1.1 Matrix Multiplication

For two $n\times n$ matrices $A=(a_{ij})$ and $B=(b_{ij})$, their product $C=AB$ satisfies:
$$c_{ij}=\sum_{k=1}^{n}a_{ik}b_{kj}$$

**Power definition:** $A^1=A$, $A^n=A^{n-1}\cdot A$.

## 1.2 Matrix Fast Power for Linear Recurrences

The key technique: encode a linear recurrence as a state vector multiplied by a **constant** transition matrix, then use fast exponentiation to reach $f(n)$ in $O(k^3\log n)$.

### Pattern 1: Basic $k$-order recurrence

$$f(n)=a_1 f(n-1)+a_2 f(n-2)+\cdots+a_k f(n-k)$$

$$\begin{pmatrix}f(n)\\f(n-1)\\\vdots\\f(n-k+1)\end{pmatrix}
=\begin{pmatrix}a_1&a_2&\cdots&a_{k-1}&a_k\\1&0&\cdots&0&0\\0&1&\cdots&0&0\\\vdots&&\ddots&&\vdots\\0&0&\cdots&1&0\end{pmatrix}
\begin{pmatrix}f(n-1)\\f(n-2)\\\vdots\\f(n-k)\end{pmatrix}$$

### Pattern 2: Recurrence with constant term

$$f(n)=a_1 f(n-1)+a_2 f(n-2)+C$$

$$\begin{pmatrix}f(n)\\f(n-1)\\1\end{pmatrix}
=\begin{pmatrix}a_1&a_2&C\\1&0&0\\0&0&1\end{pmatrix}
\begin{pmatrix}f(n-1)\\f(n-2)\\1\end{pmatrix}$$

### Pattern 3: Recurrence with polynomial forcing term

$$f(n)=a_1 f(n-1)+a_2 f(n-2)+c_2 n^2+c_1 n+c_0$$

Augment the state with $(n+1)^2$, $n+1$, $1$ and use $(n+1)^2=n^2+2n+1$:

$$\begin{pmatrix}f(n)\\f(n-1)\\(n+1)^2\\n+1\\1\end{pmatrix}
=\begin{pmatrix}a_1&a_2&c_2&c_1&c_0\\1&0&0&0&0\\0&0&1&2&1\\0&0&0&1&1\\0&0&0&0&1\end{pmatrix}
\begin{pmatrix}f(n-1)\\f(n-2)\\n^2\\n\\1\end{pmatrix}$$

### Pattern 4: Mutually dependent recurrences

$$f(n)=a_{11}f(n-1)+a_{12}g(n-1),\quad g(n)=a_{21}f(n-1)+a_{22}g(n-1)$$

$$\begin{pmatrix}f(n)\\g(n)\end{pmatrix}
=\begin{pmatrix}a_{11}&a_{12}\\a_{21}&a_{22}\end{pmatrix}
\begin{pmatrix}f(n-1)\\g(n-1)\end{pmatrix}$$

> **Summary of matrix fast power applications:**
> - **Linear recurrences** (the core use case)
> - **Matrix fast power requires a constant matrix** — the transition matrix must not change with $n$
> - **Directed graph path counting:** $(G^n)_{ij}$ = number of paths from $i$ to $j$ of exactly $n$ steps

### Example: CF 1117D — Valid 01 Strings

> Count length-$N$ binary strings where every maximal all-zero run has length divisible by $M$. $(1\leq N\leq10^{18},\ 2\leq M\leq100)$

**Observation:** valid strings are built from two operations — append a "1", or append a zero block of length exactly $M$.

$$f(n)=f(n-1)+f(n-M)\quad(f(0)=f(1)=\cdots=f(M-1)=1)$$

**Matrix model:** define the state vector $\mathbf{F}(n)=[f(n),f(n-1),\ldots,f(n-M+1)]^\top$, and the $M\times M$ transition matrix:
$$A=\begin{bmatrix}1&0&\cdots&0&1\\1&0&\cdots&0&0\\0&1&\cdots&0&0\\\vdots&&\ddots&&\vdots\\0&0&\cdots&1&0\end{bmatrix}$$

(First row encodes $f(n+1)=f(n)+f(n+1-M)$; remaining rows shift the state down.)

Initial vector: $\mathbf{F}(M-1)=[1,1,\ldots,1]^\top$.

Answer: $f(N)=(\mathbf{F}(N))_1=A^{N-(M-1)}\mathbf{F}(M-1)$ at index 0.

**Complexity:** $O(M^3\log N)$.

```cpp
int main(){
    ll n; int m;
    cin >> n >> m;
    if (n < m) { cout << 1 << '\n'; return 0; }
    if (n == m) { cout << 2 << '\n'; return 0; }

    Mat A; A.assign(m, vector<int>(m));
    A[0][0] = 1;
    A[0][m-1] = 1;
    for(int i = 1; i < m; i++) A[i][i-1] = 1;

    vector<int> F(m, 1);          // initial vector F(m-1) = [1,1,...,1]^T
    auto jm = mpow_vec(A, n-(m-1), F);
    cout << jm[0] << '\n';
    return 0;
}
```

---

# 2 Matrix Fast Power for DP — Four Semiring Types

## Type ①: Counting (standard ring, mod $M$)

**Semantics:** number of paths/arrangements.  
**Semiring:** $(\mathbb{Z}_M, +, \times, 0, 1)$

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int M = 1000000007;
using Mat = vector<vector<int>>;

Mat id(int n){
    Mat I(n, vector<int>(n, 0));
    for(int i = 0; i < n; i++) I[i][i] = 1;
    return I;
}

Mat mul(const Mat& A, const Mat& B){
    int n = (int)A.size();
    Mat C(n, vector<int>(n, 0));
    for(int i = 0; i < n; i++){
        for(int k = 0; k < n; k++){
            int aik = A[i][k];
            if(!aik) continue;
            ll t = aik;
            for(int j = 0; j < n; j++)
                C[i][j] = (C[i][j] + t * B[k][j]) % M;
        }
    }
    return C;
}

Mat mpow(Mat A, unsigned long long e){
    int n = (int)A.size();
    Mat R = id(n);
    while(e){
        if(e & 1ULL) R = mul(R, A);
        A = mul(A, A);
        e >>= 1ULL;
    }
    return R;
}

// compute A * x (matrix-vector)
vector<int> mul_vec(const Mat& A, const vector<int>& x){
    int n = (int)A.size();
    vector<int> y(n, 0);
    for(int i = 0; i < n; i++){
        long long s = 0;
        for(int j = 0; j < n; j++)
            if(A[i][j]) s = (s + 1LL * A[i][j] * x[j]) % M;
        y[i] = (int)s;
    }
    return y;
}

// compute A^e * x0  (O(n^2 log e), saves one dimension vs. full matrix power)
vector<int> mpow_vec(Mat A, unsigned long long e, vector<int> x){
    while(e){
        if(e & 1ULL) x = mul_vec(A, x);
        A = mul(A, A);
        e >>= 1ULL;
    }
    return x;
}
```

### Example: Nowcoder 17890 — Grid Coloring

> $m\times n$ grid; each cell is black (1) or white (0). Constraints: no two horizontally adjacent cells are both white; no two adjacent columns are both all-black. Count valid colourings. $(1\leq m\leq5,\ 1\leq n\leq10^{18})$

**Bitmask DP:** encode each column as an $m$-bit mask (bit=1 → black, bit=0 → white).

Constraint 1 (no two adjacent white cells in same row): for adjacent columns `st'` (prev) and `st` (curr), every row has at least one black cell → `(st | st') == ALL` where `ALL = (1<<m)-1`.

Constraint 2 (no two adjacent all-black columns): not (`st==ALL && st'==ALL`).

Transition matrix $A$ of size $2^m\times2^m$:
$$A[\text{st}][\text{st}'] = 1 \iff (\text{st}\mid\text{st}')==\text{ALL} \;\text{ and }\; \neg(\text{st}=\text{st}'=\text{ALL})$$

*(Visual: the matrix rows are indexed by current column mask st, columns by previous mask st'. Entry is 1 iff both constraints hold.)*

**Complexity:** $O((2^m)^3\log n)$.

```cpp
void solve() {
    int m; unsigned long long n;
    cin >> m >> n;
    int S = 1 << m, ALL = S - 1;
    Mat A; A.assign(S, vector<int>(S));
    for(int stp = 0; stp < S; ++stp)
        for(int st = 0; st < S; ++st)
            if(((st | stp) == ALL) && !(st == ALL && stp == ALL))
                A[st][stp] = 1;
    vector<int> x0(S, 1);
    auto jm = mpow_vec(A, n-1, x0);
    ll ans = 0;
    for(int i = 0; i < S; i++){ ans += jm[i]; ans %= M; }
    cout << ans << endl;
}
```

### Example: LeetCode — Number of ZigZag Arrays II

> Array of length $n$, elements in $[l,r]$; adjacent elements unequal; no three consecutive elements strictly increasing or decreasing. Count valid arrays mod $10^9+7$. ($3\leq n\leq10^9$, $1\leq l\lt r\leq75$)

**Reduction:** shift values to $\{1,\ldots,K\}$ with $K=r-l+1$ (only length matters). Valid arrays are one of two alternating patterns: up-down or down-up.

With $t=n-1$ steps, define two $K\times K$ matrices:
$$U_{i,j}=[i>j]\quad(\text{go up: current }\gt\text{ previous})$$
$$D_{i,j}=[i\lt j]\quad(\text{go down: current }\lt\text{ previous})$$

For the "up-start" pattern:
- $t$ even: operator $(DU)^{t/2}$
- $t$ odd: operator $U\cdot(DU)^{\lfloor t/2\rfloor}$

For the "down-start" pattern: swap $U$ and $D$.

Apply each operator to the all-ones initial vector $x_0$, sum all components.

**Complexity:** $O(K^3\log n)$ where $K\leq75$.

## Type ②: Boolean Reachability (OR-AND semiring)

**Semantics:** does there exist a path/sequence of length exactly $n$?  
**Semiring:** $(\{0,1\},\lor,\land,0,1)$

**Note:** computing $A^k$ with standard integer arithmetic and thresholding at $>0$ gives reachability too — but the boolean version avoids overflow.

**Useful identity:** $\leq k$ step reachability via $(I\lor A)^k = I\lor A\lor A^2\lor\cdots\lor A^k$ (OR is idempotent, so boolean fast power works directly).

### Up to 64 states — bitmask encoding, $O(n^3/64)$

```cpp
using ull = unsigned long long;
struct BMat {
    int n;
    vector<ull> r;   // r[i] is a bitmask: bit j = A[i][j]
    BMat(): n(0) {}
    explicit BMat(int n_): n(n_), r(n_, 0ULL) {}
};

BMat bid(int n){
    assert(n <= 64);
    BMat I(n);
    for(int i = 0; i < n; i++) I.r[i] |= (1ULL << i);
    return I;
}

// C = A (*) B  (boolean: C[i][j] = OR_k (A[i][k] AND B[k][j]))
// O(n^3 / 64) via 64-bit AND
BMat bmul(const BMat& A, const BMat& B){
    assert(A.n == B.n);
    int n = A.n;
    BMat C(n);
    vector<ull> col(n, 0ULL);
    for(int j = 0; j < n; j++){
        ull m = 0ULL;
        for(int k = 0; k < n; k++)
            if((B.r[k] >> j) & 1ULL) m |= (1ULL << k);
        col[j] = m;
    }
    for(int i = 0; i < n; i++){
        const ull ai = A.r[i];
        if(!ai) continue;
        for(int j = 0; j < n; j++)
            if(ai & col[j]) C.r[i] |= (1ULL << j);
    }
    return C;
}

BMat bmpow(BMat A, ull e){
    BMat R = bid(A.n);
    while(e){ if(e & 1ULL) R = bmul(R, A); A = bmul(A, A); e >>= 1ULL; }
    return R;
}

ull bmul_vec(const BMat& A, ull x){
    int n = A.n; ull y = 0ULL;
    for(int i = 0; i < n; i++)
        if(A.r[i] & x) y |= (1ULL << i);
    return y;
}

ull bmpow_vec(BMat A, ull e, ull x){
    while(e){ if(e & 1ULL) x = bmul_vec(A, x); A = bmul(A, A); e >>= 1ULL; }
    return x;
}

void bset(BMat& A, int i, int j){ A.r[i] |= (1ULL << j); }
bool bget(const BMat& A, int i, int j){ return (A.r[i] >> j) & 1ULL; }
```

### Arbitrary $n$ — blocked bitmask, $O(n^3/64)$

```cpp
using ull = unsigned long long;
struct BM {
    int n, b;           // b = ceil(n/64) blocks
    ull mask;           // valid bits in the last block
    vector<vector<ull>> a;  // a[i][t]: block t of row i

    BM(): n(0), b(0), mask(0) {}
    explicit BM(int n_): n(n_) {
        b = (n + 63) >> 6;
        a.assign(n, vector<ull>(b, 0ULL));
        int r = n & 63;
        mask = (b == 0 ? 0ULL : (r ? ((1ULL<<r)-1ULL) : ~0ULL));
    }
    static BM id(int n){
        BM I(n);
        for(int i = 0; i < n; ++i) I.a[i][i>>6] |= (1ULL << (i & 63));
        if(I.b) for(int i = 0; i < n; ++i) I.a[i].back() &= I.mask;
        return I;
    }
    inline void set(int i, int j){ a[i][j>>6] |= (1ULL << (j & 63)); }
    inline bool get(int i, int j) const { return (a[i][j>>6] >> (j & 63)) & 1; }
};

BM bmul(const BM& A, const BM& B){
    int n = A.n, b = A.b;
    BM C(n);
    for(int i = 0; i < n; ++i){
        auto &row = C.a[i];
        for(int t = 0; t < b; ++t){
            ull w = A.a[i][t];
            while(w){
                int bit = __builtin_ctzll(w);
                int k = (t<<6) + bit;
                if(k < n) for(int u = 0; u < b; ++u) row[u] |= B.a[k][u];
                w &= w - 1;
            }
        }
        if(b) row[b-1] &= C.mask;
    }
    return C;
}

BM bmpow(BM A, unsigned long long e){
    BM R = BM::id(A.n);
    while(e){ if(e & 1ULL) R = bmul(R, A); A = bmul(A, A); e >>= 1ULL; }
    return R;
}

// y = A * x  (column-vector semantics: predecessors of x in one step)
std::vector<ull> bmul_vec(const BM& A, const std::vector<ull>& x){
    int n = A.n, b = A.b;
    std::vector<ull> y(b, 0ULL);
    for(int i = 0; i < n; ++i){
        bool hit = false;
        for(int t = 0; t < b; ++t) if(A.a[i][t] & x[t]){ hit = true; break; }
        if(hit) y[i>>6] |= (1ULL << (i & 63));
    }
    if(b) y[b-1] &= A.mask;
    return y;
}

std::vector<ull> bmpow_vec(BM A, unsigned long long e, std::vector<ull> x){
    while(e){ if(e & 1ULL) x = bmul_vec(A, x); A = bmul(A, A); e >>= 1ULL; }
    return x;
}

// forward step: y = x * A  (expand from source set outward)
std::vector<ull> bmul_vec_forward(const BM& A, const std::vector<ull>& x){
    int b = A.b, n = A.n;
    std::vector<ull> y(b, 0ULL);
    for(int i = 0; i < n; ++i)
        if((x[i>>6] >> (i & 63)) & 1ULL)
            for(int u = 0; u < b; ++u) y[u] |= A.a[i][u];
    if(b) y[b-1] &= A.mask;
    return y;
}
```

## Type ③: Shortest Cost (min-plus semiring)

**Semantics:** minimum total cost of exactly $n$ steps.  
**Semiring:** $(\mathbb{L}\cup\{\infty\},\min,+,\infty,0)$

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
using Mat = vector<vector<ll>>;
const ll INF = (1LL<<60);

Mat minplus_mul(const Mat& A, const Mat& B){
    int n = (int)A.size();
    Mat C(n, vector<ll>(n, INF));
    for(int i = 0; i < n; i++)
        for(int k = 0; k < n; k++) if(A[i][k] < INF){
            ll aik = A[i][k];
            for(int j = 0; j < n; j++) if(B[k][j] < INF)
                C[i][j] = min(C[i][j], aik + B[k][j]);
        }
    return C;
}

Mat minplus_pow(Mat A, unsigned long long e){
    int n = (int)A.size();
    Mat R(n, vector<ll>(n, INF));
    for(int i = 0; i < n; i++) R[i][i] = 0;  // identity: diagonal 0, rest INF
    while(e){
        if(e & 1ULL) R = minplus_mul(R, A);
        A = minplus_mul(A, A);
        e >>= 1ULL;
    }
    return R;
}

// A^n * v  (O(n^2 log n), faster than full matrix power for vector queries)
vector<ll> minplus_pow_vec(Mat A, unsigned long long e, vector<ll> v){
    int n = (int)A.size();
    auto apply = [&](const Mat& M, const vector<ll>& x){
        vector<ll> y(n, INF);
        for(int i = 0; i < n; i++)
            for(int k = 0; k < n; k++) if(M[i][k] < INF && x[k] < INF)
                y[i] = min(y[i], M[i][k] + x[k]);
        return y;
    };
    while(e){
        if(e & 1ULL) v = apply(A, v);
        A = minplus_mul(A, A);
        e >>= 1ULL;
    }
    return v;
}
```

## Type ④: Maximum Reward (max-plus semiring)

**Semantics:** maximum total reward of exactly $n$ steps.  
**Semiring:** $(\mathbb{L}\cup\{-\infty\},\max,+,-\infty,0)$

```cpp
using Mat = vector<vector<ll>>;
const ll NINF = -(1LL<<60);

Mat maxplus_mul(const Mat& A, const Mat& B){
    int n = (int)A.size();
    Mat C(n, vector<ll>(n, NINF));
    for(int i = 0; i < n; i++)
        for(int k = 0; k < n; k++) if(A[i][k] > NINF){
            ll aik = A[i][k];
            for(int j = 0; j < n; j++) if(B[k][j] > NINF)
                C[i][j] = max(C[i][j], aik + B[k][j]);
        }
    return C;
}

Mat maxplus_pow(Mat A, unsigned long long e){
    int n = (int)A.size();
    Mat R(n, vector<ll>(n, NINF));
    for(int i = 0; i < n; i++) R[i][i] = 0;  // identity: diagonal 0, rest -INF
    while(e){
        if(e & 1ULL) R = maxplus_mul(R, A);
        A = maxplus_mul(A, A);
        e >>= 1ULL;
    }
    return R;
}

vector<ll> maxplus_pow_vec(Mat A, unsigned long long e, vector<ll> v){
    int n = (int)A.size();
    auto apply = [&](const Mat& M, const vector<ll>& x){
        vector<ll> y(n, NINF);
        for(int i = 0; i < n; i++)
            for(int k = 0; k < n; k++) if(M[i][k] > NINF && x[k] > NINF)
                y[i] = max(y[i], M[i][k] + x[k]);
        return y;
    };
    while(e){
        if(e & 1ULL) v = apply(A, v);
        A = maxplus_mul(A, A);
        e >>= 1ULL;
    }
    return v;
}
```

---

# 3 Matrix + Data Structures

## 3.1 Fibonacci Segment Tree (CF 719E — Sasha and Array)

> Array $a_1,\ldots,a_n$, $m$ queries:
> - Range add $x$ to $a[l..r]$
> - Query $\sum_{i=l}^r F(a_i)\bmod(10^9+7)$ where $F$ is the Fibonacci function.
>
> $(1\leq n,m\leq10^5,\ 1\leq a_i,x\leq10^9)$

**Key insight:** define the Fibonacci transition matrix $T=\begin{pmatrix}1&1\\1&0\end{pmatrix}$ with $T^k=\begin{pmatrix}F_{k+1}&F_k\\F_k&F_{k-1}\end{pmatrix}$.

Represent each $a_i$ as the $2\times2$ matrix $T^{a_i}$. Adding $x$ to $a_i$ means right-multiplying by $T^x$, which is the **same matrix for all positions in the range**.

**Segment tree with matrix lazy tags:**
- **Node value** `sum`: sum of all $T^{a_i}$ in the range (matrix addition, element-wise).
- **Lazy tag** `tag`: pending right-multiplication matrix (identity initially).
- **push_down:** $\sum T^{a_i+x} = \sum T^{a_i} \cdot T^x$, so multiply both `sum` and `tag` of children on the right.
- **push_up:** `sum = left.sum + right.sum` (element-wise matrix addition).
- **Answer:** query returns the sum matrix; answer is `sum.a[1][0]` (= $\sum F_{a_i}$).

**Complexity:** $O(m\log n\cdot2^3\log x)$ since each `T^x` costs $O(4\log x)$.

```cpp
#include<bits/stdc++.h>
#define int long long
#define endl '\n'
using namespace std;
const int N = 2e5 + 10;
const int MOD = 1e9+7;
const int SZ = 2;   // matrix dimension

struct Mat {
    int a[SZ][SZ];
    Mat(){ for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++) a[i][j]=0; }
    void clear(){ for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++) a[i][j]=0; }
    void init(){ clear(); for(int i=0;i<SZ;i++) a[i][i]=1; }
    Mat operator+(const Mat& dx) const {
        Mat ls;
        for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++)
            ls.a[i][j] = (a[i][j]+dx.a[i][j])%MOD;
        return ls;
    }
    Mat operator*(const Mat& dx) const {
        Mat ls;
        for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++){
            long long s=0;
            for(int k=0;k<SZ;k++){
                s += (a[i][k]*dx.a[k][j])%MOD;
                if(s>=(1ll<<62)) s%=MOD;
            }
            ls.a[i][j]=(int)(s%MOD);
        }
        return ls;
    }
    Mat mpow(long long e) const {
        Mat ls; ls.init(); Mat di=*this;
        while(e){ if(e&1) ls=ls*di; e>>=1; di=di*di; }
        return ls;
    }
} tree[N<<2], lazy[N<<2];

int a[N];

inline Mat baseT(){   // Fibonacci transition matrix
    Mat t;
    t.a[0][0]=1; t.a[0][1]=1;
    t.a[1][0]=1; t.a[1][1]=0;
    return t;
}

void pushdown(int dq){
    lazy[dq<<1]    = lazy[dq<<1]    * lazy[dq];
    lazy[dq<<1|1]  = lazy[dq<<1|1]  * lazy[dq];
    tree[dq<<1]    = tree[dq<<1]    * lazy[dq];
    tree[dq<<1|1]  = tree[dq<<1|1]  * lazy[dq];
    lazy[dq].init();
}
void pushup(int dq){ tree[dq]=tree[dq<<1]+tree[dq<<1|1]; }
void build(int l,int r,int dq){
    lazy[dq].init();
    if(l==r){ Mat T=baseT(); tree[dq]=T.mpow(a[l]); return; }
    int m=(l+r)>>1;
    build(l,m,dq<<1); build(m+1,r,dq<<1|1); pushup(dq);
}
void add(int l,int r,int ml,int mr,int dq,const Mat& zhi){
    if(ml<=l && r<=mr){ lazy[dq]=lazy[dq]*zhi; tree[dq]=tree[dq]*zhi; return; }
    pushdown(dq); int m=(l+r)>>1;
    if(ml<=m) add(l,m,ml,mr,dq<<1,zhi);
    if(mr>m)  add(m+1,r,ml,mr,dq<<1|1,zhi);
    pushup(dq);
}
Mat query(int l,int r,int ml,int mr,int dq){
    if(ml<=l && r<=mr) return tree[dq];
    pushdown(dq); int m=(l+r)>>1; Mat ls;
    if(ml<=m) ls=ls+query(l,m,ml,mr,dq<<1);
    if(mr>m)  ls=ls+query(m+1,r,ml,mr,dq<<1|1);
    return ls;
}
void solve(){
    int n,m; cin>>n>>m;
    for(int i=1;i<=n;i++) cin>>a[i];
    build(1,n,1);
    int sz,l,r; long long v; Mat T=baseT();
    while(m--){
        cin>>sz;
        if(sz==1){ cin>>l>>r>>v; Mat M=T.mpow(v); add(1,n,l,r,1,M); }
        else{ cin>>l>>r; Mat ans=query(1,n,l,r,1); cout<<(ans.a[1][0]%MOD+MOD)%MOD<<endl; }
    }
}
signed main(){ ios::sync_with_stdio(false); cin.tie(0); cout.tie(0); solve(); return 0; }
```

## 3.2 Range-Add, Range sin-Sum — Luogu P6327 (Floating Point)

> Array $a[]$, operations: range add $v$; query $\sum_{i=l}^r\sin(a_i)$. ($n,m\leq2\times10^5$)

**Key identity:** $\sin(a+v)=\sin a\cos v+\cos a\sin v$ and $\cos(a+v)=-\sin a\sin v+\cos a\cos v$.

Store each node as the $2\times2$ rotation matrix:
$$\begin{pmatrix}\cos a_i&-\sin a_i\\\sin a_i&\cos a_i\end{pmatrix}$$

Adding $v$ to $a_i$ is right-multiplication by the rotation matrix $R(v)=\begin{pmatrix}\cos v&-\sin v\\\sin v&\cos v\end{pmatrix}$.

The segment tree stores matrix sums; the answer to a range-sin query is `ans.a[1][0]` (sum of $\sin$ components). The push-down and push-up are identical in structure to the Fibonacci case but with floating-point matrices.

```cpp
#include<bits/stdc++.h>
#define int long long
#define endl '\n'
using namespace std;
const int N = 2e5 + 10;
const int SZ = 2;

struct Mat {
    double a[SZ][SZ];
    Mat(){ for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++) a[i][j]=0; }
    void init(){ for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++) a[i][j]=(i==j)?1:0; }
    Mat operator+(const Mat& dx){ Mat ls; for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++) ls.a[i][j]=a[i][j]+dx.a[i][j]; return ls; }
    Mat operator*(const Mat& dx){ Mat ls; for(int i=0;i<SZ;i++) for(int j=0;j<SZ;j++) for(int k=0;k<SZ;k++) ls.a[i][j]+=a[i][k]*dx.a[k][j]; return ls; }
    Mat mpow(long long e) const { Mat ls; ls.init(); Mat di=*this; while(e){ if(e&1) ls=ls*di; e>>=1; di=di*di; } return ls; }
} tree[N<<2], lazy[N<<2];

int a[N];
void pushdown(int dq){ lazy[dq<<1]=lazy[dq<<1]*lazy[dq]; lazy[dq<<1|1]=lazy[dq<<1|1]*lazy[dq]; tree[dq<<1]=tree[dq<<1]*lazy[dq]; tree[dq<<1|1]=tree[dq<<1|1]*lazy[dq]; lazy[dq].init(); }
void pushup(int dq){ tree[dq]=tree[dq<<1]+tree[dq<<1|1]; }
void build(int l,int r,int dq){
    lazy[dq].init();
    if(l==r){ tree[dq].a[0][0]=cos(a[l]); tree[dq].a[0][1]=-sin(a[l]); tree[dq].a[1][0]=sin(a[l]); tree[dq].a[1][1]=cos(a[l]); return; }
    int ed=l+r>>1; build(l,ed,dq<<1); build(ed+1,r,dq<<1|1); pushup(dq);
}
void add(int l,int r,int ml,int mr,int dq,Mat zhi){
    if(ml<=l&&r<=mr){ lazy[dq]=lazy[dq]*zhi; tree[dq]=tree[dq]*zhi; return; }
    pushdown(dq); int ed=l+r>>1;
    if(ml<=ed) add(l,ed,ml,mr,dq<<1,zhi);
    if(mr>ed)  add(ed+1,r,ml,mr,dq<<1|1,zhi);
    pushup(dq);
}
Mat query(int l,int r,int ml,int mr,int dq){
    if(ml<=l&&r<=mr) return tree[dq];
    pushdown(dq); int ed=l+r>>1; Mat ls;
    if(ml<=ed) ls=ls+query(l,ed,ml,mr,dq<<1);
    if(mr>ed)  ls=ls+query(ed+1,r,ml,mr,dq<<1|1);
    return ls;
}
void solve(){
    int n; cin>>n;
    for(int i=1;i<=n;i++) cin>>a[i];
    build(1,n,1);
    int m; cin>>m; int sz,l,r,v;
    while(m--){
        cin>>sz;
        if(sz==1){ cin>>l>>r>>v; Mat ls; ls.a[0][0]=cos(v); ls.a[0][1]=-sin(v); ls.a[1][0]=sin(v); ls.a[1][1]=cos(v); add(1,n,l,r,1,ls); }
        else{ cin>>l>>r; auto ans=query(1,n,l,r,1); cout<<ans.a[1][0]<<endl; }
    }
}
signed main(){ ios::sync_with_stdio(false); cin.tie(0); cout.tie(0); cout<<fixed<<setprecision(6); solve(); return 0; }
```

> **Matrix + data structure pattern:**
> - Expand the maintained values from scalars to matrices.
> - push_down: $\sum\vec{F}(a_i+x)=M^x\sum\vec{F}(a_i)$ — the same constant matrix applies to the whole sum.
> - push_up: simple matrix (or vector) addition.
>
> When a lazy tag's push_down is hard to implement, consider whether extending to matrices unlocks it.

---

# 4 Kitamasa — Faster Linear Recurrence

Compute $a_n$ for $a_n=c_1a_{n-1}+\cdots+c_ka_{n-k}$ in $O(k^2\log n)$ time and $O(k)$ space — better than matrix exponentiation's $O(k^3\log n)$ for large $k$.

## Algorithm

Represent the answer as a linear combination of initial values: $a_n=\sum_{i=0}^{k-1}r_i a_i$.

The coefficient vector $r(x)\bmod P(x)$ (where $P(x)=x^k-c_1x^{k-1}-\cdots-c_k$ is the characteristic polynomial) is maintained via polynomial fast power modulo $P(x)$.

## Implementation — $O(k^2\log n)$

```cpp
#include <bits/stdc++.h>
using namespace std;
using i64 = long long;
using i128 = __int128_t;

// a_n = c1*a_{n-1} + ... + ck*a_{n-k}
// init = [a0, a1, ..., a_{k-1}], coef = [c1, c2, ..., ck]
i64 kitamasa(vector<i64> init, vector<i64> coef, long long n, i64 mod){
    int k = (int)coef.size();
    if(n < (int)init.size()){ i64 x=init[(int)n]%mod; if(x<0) x+=mod; return x; }
    for(auto &x:init){ x%=mod; if(x<0) x+=mod; }
    for(auto &x:coef){ x%=mod; if(x<0) x+=mod; }
    if(k==0) return 0;
    if(k==1){
        i64 base=coef[0], pw=1%mod; long long e=n;
        while(e){ if(e&1) pw=(i64)((i128)pw*base%mod); e>>=1; if(e) base=(i64)((i128)base*base%mod); }
        return (i64)((i128)init[0]*pw%mod);
    }
    auto mul = [&](vector<i64> A, vector<i64> B){
        vector<i64> C(k);
        for(int t=0;t<k;++t){
            i64 v=A[t];
            if(v){ for(int j=0;j<k;++j) C[j]=(C[j]+(i64)((i128)v*B[j]%mod))%mod; }
            i64 bk=B[k-1];
            for(int i=k-1;i>0;--i) B[i]=(B[i-1]+(i64)((i128)bk*coef[i]%mod))%mod;
            B[0]=(i64)((i128)bk*coef[0]%mod);
        }
        return C;
    };
    vector<i64> resC(k,0), cur(k,0);
    resC[0]=1%mod; cur[1]=1%mod;   // resC=1 (constant), cur=x
    long long e=n;
    while(e){ if(e&1) resC=mul(cur,resC); e>>=1; if(e) cur=mul(cur,cur); }
    i128 acc=0;
    for(int i=0;i<k;++i) acc=(acc+(i128)resC[i]*init[i])%mod;
    i64 ans=(i64)acc%mod; if(ans<0) ans+=mod;
    return ans;
}

/*** usage
int main(){
    // Fibonacci: a_n = a_{n-1} + a_{n-2},  a_0=0, a_1=1
    vector<i64> init={0,1}, coef={1,1};
    i64 mod=1000000007LL;
    cout << kitamasa(init, coef, 50, mod) << "\n";  // F_50
}
***/
```

## NTT-based version — $O(k\log^2 k\cdot\log n)$

Uses polynomial modular reduction ($x^n\bmod P(x)$) via NTT:

```cpp
// prerequisite: qp, ntt, multiply, polyInv are implemented

void trim(vector<int>& a){ while(!a.empty()&&a.back()==0) a.pop_back(); }

vector<int> polyInv(const vector<int>& f, int m){
    vector<int> g(1, qp(f[0]));  // g0 = 1/f[0]
    int len=1;
    while(len<m){
        int need=min(len<<1,m);
        vector<int> fcut(min((int)f.size(),need));
        for(int i=0;i<(int)fcut.size();++i) fcut[i]=f[i];
        auto fg=multiply(fcut,g); fg.resize(need);
        vector<int> t(need);
        t[0]=(2-(fg.size()?fg[0]:0))%M; if(t[0]<0) t[0]+=M;
        for(int i=1;i<need;++i){ int v=(i<(int)fg.size()?fg[i]:0); t[i]=v?(M-v):0; }
        auto gnew=multiply(g,t); gnew.resize(need); g.swap(gnew); len=need;
    }
    g.resize(m); return g;
}

vector<int> polyMod(vector<int> A, const vector<int>& P, const vector<int>& inv_revP){
    int k=(int)P.size()-1; trim(A);
    if((int)A.size()<=k){ A.resize(k); return A; }
    int n=(int)A.size()-1, m=n-k+1;
    vector<int> rA(m); for(int i=0;i<m;++i) rA[i]=A[n-i];
    vector<int> inv(m); for(int i=0;i<m;++i) inv[i]=inv_revP[i];
    auto qrev_full=multiply(rA,inv); qrev_full.resize(m);
    vector<int> Q(m); for(int i=0;i<m;++i) Q[i]=qrev_full[m-1-i];
    auto QP=multiply(Q,P);
    vector<int> R(max((int)A.size(),(int)QP.size()));
    for(int i=0;i<(int)A.size();++i) R[i]=(R[i]+A[i])%M;
    for(int i=0;i<(int)QP.size();++i){ R[i]=(R[i]-QP[i])%M; if(R[i]<0) R[i]+=M; }
    R.resize(k); return R;
}

vector<int> pow_x_modP_ntt(long long n, const vector<int>& P, const vector<int>& inv_revP){
    int k=(int)P.size()-1;
    vector<int> res(1,1), base={0,1};
    base=polyMod(base,P,inv_revP);
    while(n){
        if(n&1){ res=multiply(res,base); res=polyMod(res,P,inv_revP); }
        n>>=1;
        if(n){ base=multiply(base,base); base=polyMod(base,P,inv_revP); }
    }
    res.resize(k); return res;
}

// main interface: a_n = c1 a_{n-1} + ... + ck a_{n-k}
// init=[a0..a_{k-1}], coef=[c1..ck]
int kitamasa_ntt(const vector<int>& init, const vector<int>& coef, long long n){
    int k=(int)coef.size();
    if(n<(long long)init.size()) return (init[(int)n]%M+M)%M;
    vector<int> P(k+1,0); P[k]=1;
    for(int i=0;i<k;++i){ int ci=coef[i]%M; if(ci<0) ci+=M; P[k-1-i]=(M-ci)%M; }
    vector<int> revP(k+1); for(int i=0;i<=k;++i) revP[i]=P[k-i];
    auto inv_revP=polyInv(revP,k);
    auto R=pow_x_modP_ntt(n,P,inv_revP);
    long long ans=0;
    for(int i=0;i<k;++i){ long long a=(i<(int)init.size()?init[i]:0); if(a<0) a+=M; ans=(ans+a*1ll*R[i])%M; }
    return (int)ans;
}

/*** usage
int main(){
    vector<int> init={0,1}, coef={1,1};
    ll n; cin>>n;
    cout << kitamasa_ntt(init, coef, n) << "\n";
}
***/
```
