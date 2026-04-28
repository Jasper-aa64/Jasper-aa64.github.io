---
title: "Matrix #2: Gaussian Elimination — Real, Mod, Mod-2, Incremental"
date: 2026-04-28T00:00:00+08:00
slug: "matrix-2-gaussian-elimination"
description: "Gaussian elimination templates for linear systems, determinant, inverse, and rank over reals, modular arithmetic, and GF(2); incremental RREF maintenance; examples including Lights Out, Piet's Palette, and ICPC tree XOR queries."
summary: "Gauss elimination: real/mod/mod-2 templates (solve, det, inv, rank); incremental online RREF; Extended Lights Out, CF 1344F abstract GF(2) modelling, 2024 ICPC Kunming interactive tree queries."
categories: [Matrix]
tags: [math, matrix, gaussian-elimination, linear-algebra, gf2, bitset, interactive]
math: true
toc: true
---

(Continues from [Matrix #1](../matrix-1-fast-exponentiation))

# 1 Applications of Gaussian Elimination

## 1.1 Solving a Linear System $Ax = b$

$$\begin{pmatrix}a_{11}&a_{12}&\cdots&a_{1n}\\a_{21}&a_{22}&\cdots&a_{2n}\\\vdots&\vdots&&\vdots\\a_{n1}&a_{n2}&\cdots&a_{nn}\end{pmatrix}
\begin{pmatrix}x_1\\x_2\\\vdots\\x_n\end{pmatrix}
=\begin{pmatrix}b_1\\b_2\\\vdots\\b_n\end{pmatrix}$$

## 1.2 Computing the Determinant

Row-reduce to upper-triangular form, accumulate diagonal entries; track sign flips from row swaps.

```cpp
struct DET {
    int a[3005][3005], n;
    int run() {
        if(!n) return 1;
        int x, y, z, k, res = 1;
        for(x = 1; x <= n; ++x) {
            for(y = x; y <= n && !a[y][x]; ++y);
            if(y > n) return 0;
            if(y > x) {
                for(k = 1; k <= n; ++k) swap(a[x][k], a[y][k]);
                res && (res = M - res);   // flip sign (mod M)
            }
            k = qp(a[x][x]);
            res = 1ll * res * a[x][x] % M;
            for(z = 1; z <= n; ++z) a[x][z] = 1ll * a[x][z] * k % M;
            for(y = 1; y <= n; ++y) if(x != y) {
                k = a[y][x];
                for(z = 1; z <= n; ++z) del(a[y][z], a[x][z], k);
            }
        }
        for(x = 1; x <= n; ++x) res = 1ll * res * a[x][x] % M;
        return res;
    }
} det;
```

## 1.3 Computing the Inverse Matrix

**Idea:** form the augmented matrix $[A\mid I]$ and row-reduce the left half to $I$; the right half becomes $A^{-1}$.

## 1.4 Templates

**Complexity:** $O(n\cdot m\cdot\min(n,m))$, typically $O(n^3)$.

### 1.4.1 Real-valued (double precision)

Tip: replace `double` with `long double` if higher precision is needed.

```cpp
const double EPS = 1e-12;

// Solve Ax=b; returns solution vector, or {} if singular / non-unique
vector<double> gauss(vector<vector<double>> a, vector<double> b) {
    int n = a.size();
    for(int i = 0; i < n; i++) {
        int r = i;
        for(int k = i; k < n; k++) if(fabs(a[k][i]) > fabs(a[r][i])) r = k;
        if(fabs(a[r][i]) < EPS) return {};
        if(r != i) { swap(a[r], a[i]); swap(b[r], b[i]); }
        double inv = 1.0 / a[i][i];
        for(int j = i; j < n; j++) a[i][j] *= inv; b[i] *= inv;
        for(int j = 0; j < n; j++) if(j != i) {
            double x = a[j][i]; if(fabs(x) < EPS) continue;
            for(int k = i; k < n; k++) a[j][k] -= x * a[i][k];
            b[j] -= x * b[i];
        }
    }
    return b;
}

// Determinant
double det(vector<vector<double>> a) {
    int n = a.size(); double d = 1; int s = 1;
    for(int i = 0; i < n; i++) {
        int r = i;
        for(int k = i; k < n; k++) if(fabs(a[k][i]) > fabs(a[r][i])) r = k;
        if(fabs(a[r][i]) < EPS) return 0;
        if(r != i) { swap(a[r], a[i]); s = -s; }
        d *= a[i][i];
        double inv = 1.0 / a[i][i];
        for(int j = i+1; j < n; j++) {
            double f = a[j][i] * inv; if(fabs(f) < EPS) continue;
            for(int k = i; k < n; k++) a[j][k] -= f * a[i][k];
        }
    }
    return s == -1 ? -d : d;
}

// Inverse matrix; returns {} if singular
vector<vector<double>> inv(vector<vector<double>> a) {
    int n = a.size();
    vector<vector<double>> I(n, vector<double>(n)); for(int i = 0; i < n; i++) I[i][i] = 1;
    for(int c = 0; c < n; c++) {
        int r = c;
        for(int k = c; k < n; k++) if(fabs(a[k][c]) > fabs(a[r][c])) r = k;
        if(fabs(a[r][c]) < EPS) return {};
        if(r != c) { swap(a[r], a[c]); swap(I[r], I[c]); }
        double invp = 1.0 / a[c][c];
        for(int j = 0; j < n; j++) { a[c][j] *= invp; I[c][j] *= invp; }
        for(int i = 0; i < n; i++) if(i != c) {
            double f = a[i][c]; if(fabs(f) < EPS) continue;
            for(int j = 0; j < n; j++) { a[i][j] -= f*a[c][j]; I[i][j] -= f*I[c][j]; }
        }
    }
    return I;
}

// Rank of an n×m matrix
int rank(vector<vector<double>> a) {
    int n = a.size(); if(!n) return 0;
    int m = a[0].size(), r = 0;
    for(int c = 0; c < m && r < n; c++) {
        int p = r;
        for(int i = r; i < n; i++) if(fabs(a[i][c]) > fabs(a[p][c])) p = i;
        if(fabs(a[p][c]) < EPS) continue;
        if(p != r) swap(a[p], a[r]);
        for(int i = r+1; i < n; i++) {
            double f = a[i][c] / a[r][c]; if(fabs(f) < EPS) continue;
            for(int j = c; j < m; j++) a[i][j] -= f * a[r][j];
        }
        r++;
    }
    return r;
}
```

### 1.4.2 Modular arithmetic

> Tip: when $p$ is prime, use fast-exponentiation for the modular inverse (more efficient).

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int P = 998244353;

ll qp(ll a, ll e=P-2){ ll r=1; for(a%=P;e;e>>=1){ if(e&1) r=r*a%P; a=a*a%P; } return r; }

// O(n^3): n×n system; returns unique solution or {} on singular/multiple solutions
vector<int> gauss_mod(vector<vector<int>> a, vector<int> b) {
    int n = a.size();
    for(int i = 0; i < n; i++) {
        int r = i;
        while(r < n && a[r][i] == 0) ++r;
        if(r == n) return {};   // all-zero column: singular or multiple solutions
        if(r != i) { swap(a[r], a[i]); swap(b[r], b[i]); }
        int inv = qp(a[i][i]);
        for(int j = i; j < n; j++) a[i][j] = 1ll*a[i][j]*inv%P;
        b[i] = 1ll*b[i]*inv%P;
        for(int j = 0; j < n; j++) if(j != i) {
            int x = a[j][i]; if(!x) continue;
            for(int k = i; k < n; k++) {
                a[j][k] = (a[j][k] - 1ll*x*a[i][k])%P;
                if(a[j][k] < 0) a[j][k] += P;
            }
            b[j] = (b[j] - 1ll*x*b[i])%P;
            if(b[j] < 0) b[j] += P;
        }
    }
    return b;
}

// Determinant (n×n), O(n^3)
int det_mod(vector<vector<int>> a) {
    int n = a.size(); ll det = 1; int sgn = 1;
    for(int i = 0; i < n; i++) {
        int r = i; while(r < n && a[r][i] == 0) ++r;
        if(r == n) return 0;
        if(r != i) { swap(a[r], a[i]); sgn *= -1; }
        det = det * a[i][i] % P;
        ll inv = qp(a[i][i]);
        for(int j = i+1; j < n; j++) {
            ll f = 1ll*a[j][i]*inv%P; if(!f) continue;
            for(int k = i; k < n; k++) {
                a[j][k] = (a[j][k] - f*a[i][k])%P;
                if(a[j][k] < 0) a[j][k] += P;
            }
        }
    }
    if(sgn == -1) det = (P - det)%P;
    return (int)det;
}

// Inverse matrix (n×n), O(n^3); returns {} if singular
vector<vector<int>> inv_mod(vector<vector<int>> a) {
    int n = a.size();
    vector<vector<int>> inv(n, vector<int>(n, 0));
    for(int i = 0; i < n; i++) inv[i][i] = 1;
    for(int c = 0; c < n; c++) {
        int r = c; while(r < n && a[r][c] == 0) ++r;
        if(r == n) return {};
        if(r != c) { swap(a[r], a[c]); swap(inv[r], inv[c]); }
        int ic = qp(a[c][c]);
        for(int j = 0; j < n; j++) { a[c][j]=1ll*a[c][j]*ic%P; inv[c][j]=1ll*inv[c][j]*ic%P; }
        for(int i = 0; i < n; i++) if(i != c) {
            int f = a[i][c]; if(!f) continue;
            for(int j = 0; j < n; j++) {
                a[i][j]  = (a[i][j]  - 1ll*f*a[c][j])%P;  if(a[i][j]<0)  a[i][j]+=P;
                inv[i][j]= (inv[i][j]- 1ll*f*inv[c][j])%P; if(inv[i][j]<0) inv[i][j]+=P;
            }
        }
    }
    return inv;
}

// Rank of an n×m matrix, O(n^3)
int rank_mod(vector<vector<int>> a) {
    int n = (int)a.size(); if(!n) return 0;
    int m = (int)a[0].size(), r = 0;
    for(int c = 0; c < m && r < n; ++c) {
        int p = r; while(p < n && a[p][c] == 0) ++p;
        if(p == n) continue;
        if(p != r) swap(a[p], a[r]);
        int inv = qp(a[r][c]);
        for(int i = r+1; i < n; ++i) {
            if(a[i][c] == 0) continue;
            ll f = 1ll*a[i][c]*inv%P;
            for(int j = c; j < m; ++j) {
                a[i][j] = (a[i][j] - f*a[r][j])%P;
                if(a[i][j] < 0) a[i][j] += P;
            }
        }
        ++r;
    }
    return r;
}
```

### 1.4.3 Mod-2 (GF(2)) with bitset

**Complexity:** $O(n^3/W)$ where $W=64$ (machine word width) using `bitset` rows.

Augmented matrix format: each row is a `bitset<MAXM>` where columns $0\ldots m-1$ are the coefficient matrix and column $m$ is the RHS.

```cpp
const int MAXM = 2005;   // must satisfy MAXM >= m+1

// Solve Ax=b over GF(2), A is n×m, augmented column at index m
// Returns unique solution as 0/1 vector, or {} on no-solution/multiple solutions
vector<int> gauss_xor(vector<bitset<MAXM>> a, int n, int m) {
    vector<int> where(m, -1);
    int row = 0;
    for(int col = 0; col < m && row < n; ++col) {
        int sel = -1;
        for(int i = row; i < n; ++i) if(a[i][col]) { sel = i; break; }
        if(sel == -1) continue;
        if(sel != row) swap(a[sel], a[row]);
        where[col] = row;
        for(int i = 0; i < n; ++i) if(i != row && a[i][col]) a[i] ^= a[row];
        ++row;
    }
    // check for contradiction: row of 0...0 | 1
    for(int i = 0; i < n; ++i) {
        bool all0 = true;
        for(int j = 0; j < m; ++j) if(a[i][j]) { all0 = false; break; }
        if(all0 && a[i][m]) return {};
    }
    // check for free variables -> multiple solutions
    for(int j = 0; j < m; ++j) if(where[j] == -1) return {};
    vector<int> x(m, 0);
    for(int j = 0; j < m; ++j) x[j] = a[where[j]][m];
    return x;
}
```

### Example: Extended Lights Out — POJ 1222

> A $5\times6$ grid of switches and lights. Pressing switch $(i,j)$ toggles that light and its four neighbours. Given initial state, find a configuration that turns all lights off (or report impossible).

**Modelling:** each switch $x_{ij}\in\mathbb{Z}_2$ appears in a linear equation for each affected light:
$$a_{ij}\oplus x_{ij}\oplus x_{i-1,j}\oplus x_{i,j-1}\oplus x_{i+1,j}\oplus x_{i,j+1}=0$$

30 lights give 30 equations in 30 unknowns over GF(2). Solve with mod-2 Gauss, $O(n^3/W)$ with $n=30$.

```cpp
#include <bits/stdc++.h>
using namespace std;
const int MAXM = 40;

vector<int> gauss_xor(vector<bitset<MAXM>> a, int n, int m) {
    vector<int> where(m, -1);
    int row = 0;
    for(int col = 0; col < m && row < n; ++col) {
        int sel = -1;
        for(int i = row; i < n; ++i) if(a[i][col]) { sel = i; break; }
        if(sel == -1) continue;
        if(sel != row) swap(a[sel], a[row]);
        where[col] = row;
        for(int i = 0; i < n; ++i) if(i != row && a[i][col]) a[i] ^= a[row];
        ++row;
    }
    for(int i = 0; i < n; ++i) {
        bool all0 = true;
        for(int j = 0; j < m; ++j) if(a[i][j]) { all0 = false; break; }
        if(all0 && a[i][m]) return {};
    }
    for(int j = 0; j < m; ++j) if(where[j] == -1) return {};
    vector<int> x(m, 0);
    for(int j = 0; j < m; ++j) x[j] = a[where[j]][m];
    return x;
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int tt; cin >> tt; int cnt = 0;
    while(tt--) {
        cout << "PUZZLE #" << ++cnt << endl;
        const int N=5, M=6, V=N*M;
        int b[N][M];
        for(int i=0;i<N;i++) for(int j=0;j<M;j++) cin>>b[i][j];
        vector<bitset<MAXM>> A(V);
        int dx[5]={0,0,0,1,-1}, dy[5]={0,1,-1,0,0};
        for(int i=0;i<N;i++) for(int j=0;j<M;j++) {
            int r=i*M+j;
            for(int d=0;d<5;d++) {
                int x=i+dx[d], y=j+dy[d];
                if(x>=0&&x<N&&y>=0&&y<M) A[r].flip(x*M+y);
            }
            if(b[i][j]) A[r].flip(V);
        }
        auto res = gauss_xor(A, V, V);
        if(res.empty()) { cout<<"IMPOSSIBLE\n"; continue; }
        for(int i=0;i<N;i++) for(int j=0;j<M;j++)
            cout<<res[i*M+j]<<(j+1<M?' ':'\n');
    }
    return 0;
}
```

### Example: CF 1344F — Piet's Palette

> Operations on a palette of $n$ slots: `RY/RB/YB` swap colour pairs; `mix` returns the XOR sum of selected slots. Given operation log and mix results, recover the initial palette or output NO.

**Key observation:** the four colours `{W, R, Y, B}` map to $\mathbb{Z}_2^2$ as `W=(0,0), R=(1,0), Y=(0,1), B=(1,1)`. Under this encoding, "mix" is bitwise XOR and all three swap operations are invertible $2\times2$ linear maps over $\mathbb{Z}_2$:

$$M_{RY}=\begin{pmatrix}0&1\\1&0\end{pmatrix},\quad
M_{RB}=\begin{pmatrix}1&0\\1&1\end{pmatrix},\quad
M_{YB}=\begin{pmatrix}1&1\\0&1\end{pmatrix}$$

Track a per-slot cumulative transform $T_j$ (initially $I$). Each `RY/RB/YB` on subset $S$ updates $T_j\leftarrow M\cdot T_j$ for $j\in S$.

Each `mix` on subset $S$ with result colour $c=(b_0,b_1)$ produces two linear equations over GF(2):
$$\bigoplus_{j\in S}(T_j\cdot x_j)=b,\qquad\text{i.e.}\quad\sum_{j\in S}\text{row}_0(T_j)\cdot x_j=b_0,\quad\sum_{j\in S}\text{row}_1(T_j)\cdot x_j=b_1$$

where $x_j\in\mathbb{Z}_2^2$ are the unknown initial colours. Collect all equations ($\leq2k$), solve with bitset Gauss ($V=2n$ unknowns).

**Complexity:** $O(V^3/64)\approx O(n^3/64)$, sufficient for $n\leq1000$.

```cpp
#include <bits/stdc++.h>
using namespace std;

static const int MAXN = 1000;
static const int MAXV = MAXN * 2;

struct Mat { bool a[2][2]; Mat(){ a[0][0]=a[1][1]=1; a[0][1]=a[1][0]=0; } };

pair<bool,vector<int>> gauss(int E, int V, vector<bitset<MAXV+1>>& eqs) {
    vector<int> where(V, -1); int r = 0;
    for(int c = 0; c < V && r < E; c++) {
        int sel = r; while(sel<E && !eqs[sel][c]) sel++;
        if(sel==E) continue;
        swap(eqs[sel], eqs[r]); where[c]=r;
        for(int i=0;i<E;i++) if(i!=r && eqs[i][c]) eqs[i]^=eqs[r];
        r++;
    }
    for(int i=r;i<E;i++) if(eqs[i][V]) return {false,{}};
    vector<int> x(V,0);
    for(int i=0;i<V;i++) if(where[i]!=-1) x[i]=eqs[where[i]][V];
    return {true,x};
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, k; cin>>n>>k;
    const int V=2*n;
    Mat M_RY, M_RB, M_YB;
    M_RY.a[0][0]=0; M_RY.a[0][1]=1; M_RY.a[1][0]=1; M_RY.a[1][1]=0;
    M_RB.a[0][0]=1; M_RB.a[0][1]=0; M_RB.a[1][0]=1; M_RB.a[1][1]=1;
    M_YB.a[0][0]=1; M_YB.a[0][1]=1; M_YB.a[1][0]=0; M_YB.a[1][1]=1;
    static Mat T[MAXN];   // cumulative transforms, initially identity
    vector<bitset<MAXV+1>> eqs;

    for(int _=0;_<k;_++) {
        string op; int m; cin>>op>>m;
        vector<int> idx(m); for(int i=0;i<m;i++){ cin>>idx[i]; --idx[i]; }
        if(op=="mix") {
            char rc; cin>>rc;
            int val=(rc=='R'?1:rc=='Y'?2:rc=='B'?3:0);
            int b0=val&1, b1=(val>>1)&1;
            bitset<MAXV+1> r0, r1;
            for(int j:idx) {
                if(T[j].a[0][0]) r0.flip(2*j);
                if(T[j].a[0][1]) r0.flip(2*j+1);
                if(T[j].a[1][0]) r1.flip(2*j);
                if(T[j].a[1][1]) r1.flip(2*j+1);
            }
            r0[V]=b0; r1[V]=b1;
            eqs.push_back(r0); eqs.push_back(r1);
        } else {
            Mat& M=(op=="RY"?M_RY:op=="RB"?M_RB:M_YB);
            for(int j:idx) {
                Mat old=T[j], nw;
                for(int a=0;a<2;a++) for(int b=0;b<2;b++) {
                    bool v=0;
                    for(int t=0;t<2;t++) v^=(M.a[a][t]&old.a[t][b]);
                    nw.a[a][b]=v;
                }
                T[j]=nw;
            }
        }
    }
    auto [ok,sol]=gauss((int)eqs.size(),V,eqs);
    if(!ok){cout<<"NO\n";return 0;}
    cout<<"YES\n";
    string ans(n,'.');
    for(int i=0;i<n;i++){
        int v=sol[2*i]+(sol[2*i+1]<<1);
        if(v==1) ans[i]='R'; else if(v==2) ans[i]='Y'; else if(v==3) ans[i]='B';
    }
    cout<<ans<<"\n";
    return 0;
}
```

---

# 2 Incremental Gaussian Elimination

Maintain a Gaussian basis in **RREF form online**: insert equations one at a time and immediately reduce.

Each `add_row` call:
1. Reduce the new row against all existing pivot columns.
2. If the row becomes all-zero: check the RHS — zero means **linearly dependent** (return 0), nonzero means **contradiction** (return −1).
3. Otherwise find the new pivot, update existing rows to zero out that column, and append.

## 2.1 Modular (mod $p$)

**Complexity:** `add_row` is $O(n\cdot\mathrm{rank})$ worst-case $O(n^2)$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int P = 998244353;

int qp(int a, ll e=P-2){ a%=P; if(a<0) a+=P; int r=(P==1?0:1%P);
    while(e){if(e&1) r=(int)(1LL*r*a%P); a=(int)(1LL*a*a%P); e>>=1;} return r; }
int invm(int a){ a%=P; if(a<0) a+=P; return qp(a,P-2); }

struct IncGauss {
    int n, rnk = 0;
    vector<vector<int>> row;   // basis rows (maintained in RREF)
    vector<int> rhs;           // right-hand sides
    vector<int> pc;            // pc[rid] = pivot column of row rid
    vector<int> who;           // who[col] = row index with that pivot; -1 = free
    bool bad = false;

    IncGauss(int n_=0): n(n_), who(n, -1) {}
    void reset(int n_){ n=n_; row.clear(); rhs.clear(); pc.clear(); who.assign(n,-1); rnk=0; bad=false; }

    // Insert row a·x=b (a,b already in [0,P))
    // Returns: 1 = independent; 0 = dependent; -1 = contradiction
    int add_row(vector<int> a, int b) {
        if(bad) return -1;
        for(int c=0;c<n;c++) {
            int r=who[c]; if(r==-1) continue;
            int k=a[c]; if(k==0) continue;
            for(int j=0;j<n;j++){ a[j]-=(int)(1LL*k*row[r][j]%P); if(a[j]<0) a[j]+=P; }
            int pb=(int)(1LL*k*rhs[r]%P); b-=pb; if(b<0) b+=P;
        }
        int p=-1; for(int j=0;j<n;j++) if(a[j]!=0){ p=j; break; }
        if(p==-1){ if(b==0) return 0; bad=true; return -1; }
        int iv=invm(a[p]);
        for(int j=0;j<n;j++) a[j]=(int)(1LL*a[j]*iv%P);
        b=(int)(1LL*b*iv%P);
        for(int r=0;r<rnk;r++) {
            int k=row[r][p]; if(k==0) continue;
            for(int j=0;j<n;j++){ int prod=(int)(1LL*k*a[j]%P); row[r][j]-=prod; if(row[r][j]<0) row[r][j]+=P; }
            int pb=(int)(1LL*k*b%P); rhs[r]-=pb; if(rhs[r]<0) rhs[r]+=P;
        }
        row.push_back(move(a)); rhs.push_back(b); pc.push_back(p); who[p]=rnk; rnk++;
        return 1;
    }

    bool solve_unique(vector<int>& x) const {
        if(bad || rnk!=n) return false;
        x.assign(n,0); for(int r=0;r<rnk;r++) x[pc[r]]=rhs[r]; return true;
    }
    bool get_one_solution(vector<int>& x) const {
        if(bad) return false;
        x.assign(n,0); for(int r=0;r<rnk;r++) x[pc[r]]=rhs[r]; return true;
    }
    int rank() const { return rnk; }
};
```

## 2.2 Mod-2 with bitset

**Complexity:** `add_row_bitset` is $O(\mathrm{rank}\cdot n/64)$.

```cpp
#include <bits/stdc++.h>
using namespace std;
#define MAXN 4096

struct IncGauss2 {
    int n, rnk = 0;
    vector<bitset<MAXN>> R;   // basis rows (RREF)
    vector<int> B;            // right-hand sides (0/1)
    vector<int> pc;           // pc[row] = pivot column
    vector<int> who;          // who[col] = row with that pivot; -1 = free
    bool bad = false;

    IncGauss2(int n_=0): n(n_), who(n_,-1) {}
    void reset(int n_){ n=n_; R.clear(); B.clear(); pc.clear(); who.assign(n,-1); rnk=0; bad=false; }

    // Returns: 1 independent; 0 dependent; -1 contradiction
    int add_row_bitset(bitset<MAXN> v, int b) {
        if(bad) return -1;
        for(int c=0;c<n;c++){ int r=who[c]; if(r==-1) continue; if(v[c]){ v^=R[r]; b^=B[r]; } }
        int p=-1; for(int j=0;j<n;j++) if(v[j]){ p=j; break; }
        if(p==-1){ if(b==0) return 0; bad=true; return -1; }
        for(int r=0;r<rnk;r++) if(R[r][p]){ R[r]^=v; B[r]^=b; }
        R.push_back(move(v)); B.push_back(b&1); pc.push_back(p); who[p]=rnk; rnk++;
        return 1;
    }
    // Sparse interface: ones = list of column indices set to 1
    int add_row_sparse(const vector<int>& ones, int b) {
        if(bad) return -1;
        bitset<MAXN> v; for(int c:ones) if(0<=c&&c<n) v.set(c);
        return add_row_bitset(v, b&1);
    }
    // Dense interface
    int add_row(const vector<int>& a, int b) {
        if(bad) return -1;
        bitset<MAXN> v; for(int j=0;j<n;j++) if(a[j]&1) v.set(j);
        return add_row_bitset(v, b&1);
    }

    bool get_one_solution(vector<int>& x) const {
        if(bad) return false; x.assign(n,0); for(int r=0;r<rnk;r++) x[pc[r]]=B[r]; return true;
    }
    bool solve_unique(vector<int>& x) const {
        if(bad||rnk!=n) return false; x.assign(n,0); for(int r=0;r<rnk;r++) x[pc[r]]=B[r]; return true;
    }
    int rank() const { return rnk; }
    int nullity() const { return n-rnk; }
    bool is_bad() const { return bad; }

    // Convenience: fix x[idx] = val
    int add_eq_assign_idx(int idx, int val){ return add_row_sparse({idx}, val&1); }
    // 2D index: fix x[i*m+j] = val
    int add_eq_assign_2d(int i, int j, int m, int val){ return add_eq_assign_idx(i*m+j, val&1); }
};
```

### Example: 2024 ICPC Kunming E — Tree XOR Queries (Interactive)

> Tree of $n$ nodes with unknown weights $w_i$ ($w_1=0$ known). You may query: "XOR of all weights on the path between $u$ and $v$ whose distance equals $k$." Find all weights. ($n,k\leq250$)

**Strategy:** enumerate all pairs $(u,v)$ with $\mathrm{dist}(u,v)=k$; each query gives a linear equation $\bigoplus_{i\in\mathrm{path}(u,v)}w_i = \text{answer}$.

Insert the constraint $w_1=0$ directly. Then greedily insert path equations until the system has rank $n$ (i.e. $n-1$ independent queries found, plus the $w_1=0$ constraint).

**Key:** insert $w_1=0$ as a proper equation into the incremental basis; do not treat it separately, because $w_1$ may be deducible from path equations (which would already fix it).

**Complexity:** $O(n^3/64)$ total for incremental Gauss.

```cpp
#include <bits/stdc++.h>
using namespace std;
static const int MAXN = 260;
static const int LOG  = 9;   // 2^8 = 256 > 250

struct IncGauss2 {  // same as above, using MAXN
    int n, rnk=0;
    vector<bitset<MAXN>> R; vector<uint32_t> B;
    vector<int> pc, who; bool bad=false;
    IncGauss2(int n_=0): n(n_), who(n,-1) {}
    void reset(int n_){ n=n_; R.clear(); B.clear(); pc.clear(); who.assign(n,-1); rnk=0; bad=false; }
    int add_row(bitset<MAXN> v, int b){
        if(bad) return -1;
        for(int c=0;c<n;c++){ int r=who[c]; if(r==-1) continue; if(v[c]){ v^=R[r]; b^=B[r]; } }
        int p=-1; for(int j=0;j<n;j++) if(v[j]){ p=j; break; }
        if(p==-1){ if(b==0u) return 0; bad=true; return -1; }
        for(int r=0;r<rnk;r++) if(R[r][p]){ R[r]^=v; B[r]^=b; }
        R.push_back(move(v)); B.push_back(b); pc.push_back(p); who[p]=rnk; rnk++;
        return 1;
    }
    bool solve_unique(vector<uint32_t>& x) const {
        if(bad||rnk!=n) return false; x.assign(n,0u); for(int r=0;r<rnk;r++) x[pc[r]]=B[r]; return true;
    }
    int rank() const { return rnk; }
};

int n, K;
vector<int> g[MAXN];
int up[LOG][MAXN], dep[MAXN];

void dfs(int u,int p){ for(int v:g[u]) if(v!=p){ dep[v]=dep[u]+1; up[0][v]=u; dfs(v,u); } }
void build_lca(){ for(int j=1;j<LOG;j++) for(int i=1;i<=n;i++) up[j][i]=up[j-1][up[j-1][i]]; }
int lca(int a,int b){
    if(dep[a]<dep[b]) swap(a,b);
    int d=dep[a]-dep[b]; for(int j=0;j<LOG;j++) if((d>>j)&1) a=up[j][a];
    if(a==b) return a;
    for(int j=LOG-1;j>=0;j--) if(up[j][a]!=up[j][b]){ a=up[j][a]; b=up[j][b]; }
    return up[0][a];
}
int dist2(int u,int v){ int w=lca(u,v); return dep[u]+dep[v]-2*dep[w]; }
bitset<MAXN> path_bits(int u,int v){
    bitset<MAXN> bs; int w=lca(u,v); bs.set(w-1);
    for(int x=u;x!=w;x=up[0][x]) bs.set(x-1);
    for(int x=v;x!=w;x=up[0][x]) bs.set(x-1);
    return bs;
}

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    cin>>n>>K;
    for(int i=1;i<=n;i++) g[i].clear();
    for(int i=1;i<n;i++){ int x,y; cin>>x>>y; g[x].push_back(y); g[y].push_back(x); }
    dep[1]=0; dfs(1,0); build_lca();

    IncGauss2 IG1(n); vector<pair<int,int>> ask;
    { bitset<MAXN> e1; e1.reset(); e1.set(0); IG1.add_row(e1,0); }  // w1=0

    for(int u=1;u<=n;++u) for(int v=u+1;v<=n;++v){
        if(dist2(u,v)!=K) continue;
        auto bs=path_bits(u,v);
        if(IG1.add_row(bs,0)==1) ask.push_back({u,v});
    }
    if((int)ask.size()<n-1){ cout<<"NO\n"<<flush; return 0; }

    cout<<"YES\n";
    cout<<"? "<<ask.size(); for(auto [u,v]:ask) cout<<' '<<u<<' '<<v;
    cout<<'\n'<<flush;

    vector<uint32_t> val(ask.size());
    for(int i=0;i<(int)ask.size();++i){ uint32_t x; cin>>x; val[i]=x; }

    IncGauss2 sol(n);
    { bitset<MAXN> e1; e1.reset(); e1.set(0); sol.add_row(e1,0); }
    for(int i=0;i<(int)ask.size();++i){ auto [u,v]=ask[i]; sol.add_row(path_bits(u,v),val[i]); }

    vector<uint32_t> W; sol.solve_unique(W);
    cout<<"! ";
    for(int i=2;i<=n;++i) cout<<W[i-1]<<(i==n?'\n':' ');
    cout<<flush;
    return 0;
}
```
