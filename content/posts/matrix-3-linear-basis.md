---
title: "Matrix #3: Linear Basis (XOR Basis) & Simplex Method"
date: 2026-04-28T00:00:00+08:00
slug: "matrix-3-linear-basis"
description: "XOR linear basis over GF(2): construction, max/min XOR, k-th value, range basis; examples including median of XOR subsets, zero-XOR partitioning (CF 1101G), and XOR-divisibility counting; Simplex method for linear programming."
summary: "XOR linear basis: full template with kth, range basis, normalisation; Nowcoder median example; CF 1101G prefix-XOR rank; gym 104768 C XOR-divisibility; Simplex LP solver."
categories: [Matrix]
tags: [math, matrix, linear-basis, xor, gf2, simplex, linear-programming]
math: true
toc: true
---

(Continues from [Matrix #2](../matrix-2-gaussian-elimination))

# 1 Linear Basis (XOR Basis)

## 1.1 Basis of a Vector Space

The **maximal linearly independent set** of a vector space is called a basis.

## 1.2 XOR Linear Basis

A linear basis over $\mathbb{Z}_2^k$: a set $\{b_1,\ldots,b_r\}$ that is linearly independent over $\mathbb{Z}_2$ and spans the same achievable XOR values as the original set $S$.

**Applications:**
- Count distinct XOR values achievable by subsets of $S$
- Count subsets with XOR sum equal to a given value $T$
- Find maximum/minimum XOR achievable by any subset
- $k$-th smallest XOR value in the span

**Representation:** treat each integer as a $k$-bit binary vector; XOR corresponds to addition in $(\mathbb{Z}_2,+)$.

### 1.2.1 Definition and Construction

Given $S=\{a_1,\ldots,a_n\}$, the basis $\{b_1,\ldots,b_r\}$ satisfies:
- $\{b_i\}$ are linearly independent over $\mathbb{Z}_2$
- Every $a_j\in S$ can be written as $a_j=\bigoplus_{i\in I}b_i$

**Insertion algorithm** (high-bit first, analogous to Gaussian elimination):

```
for bit i from high to low:
    if bit i of x is 0: skip
    if b[i] == 0: place x as b[i], done
    else: x ^= b[i]
if x == 0: linearly dependent (zero = true)
```

Each insertion tries at most $B$ XOR steps. Total construction: $O(nB)$.

**Dimension and freedom:**
- $\mathrm{rank}$ = number of non-zero basis vectors.
- The basis spans exactly $2^{\mathrm{rank}}$ distinct XOR values.

### 1.2.2 Applications

**1. Count distinct XOR values and subset counts**

- Distinct achievable XOR sums: $2^{\mathrm{rank}}$
- Subsets with XOR $= T$ (let $f=n-r$):
  - $T$ not representable: answer $=0$
  - $T$ representable: answer $=2^f=2^{n-r}$
- Subsets with XOR $=0$ (including empty set): $2^f$; excluding empty set: $2^f-1$

**2. Maximum/minimum XOR**

- **Maximum:** maintain `res=0`; from high to low bit, XOR with any basis vector that increases the value.
- **Minimum non-zero XOR:** after normalisation, the smallest basis vector.

## 1.3 Complexity

| Operation | Complexity |
|-----------|-----------|
| Build from $n$ integers | $O(nB)$, $B$ = bit width |
| Insert/query single value | $O(B)$ |
| Max/min XOR | $O(B)$ |
| Count representable subsets | $O(B)$ |

## 1.4 Template

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

struct LB {
    static const int LOG = 60;   // covers up to ~1e18

    mutable ll b[LOG+1]{};       // b[i]: basis vector with highest bit at position i
    int rk = 0;                  // rank
    bool zero = false;           // true if some non-empty subset XORs to 0
    mutable bool dirty = false;

    void clear(){ memset(b,0,sizeof b); rk=0; zero=false; dirty=false; }

    // Insert x; returns true if rank increases
    bool ins(ll x){
        for(int i=LOG;i>=0;--i) if((x>>i)&1LL){
            if(!b[i]){ b[i]=x; ++rk; dirty=true; return true; }
            x^=b[i];
        }
        zero=true; return false;
    }

    int rank(){ int r=0; for(int i=0;i<LOG;++i) if(b[i]) ++r; return r; }

    // Normalise: clear lower bits of each basis vector (RREF lower half)
    // Required before kth_all / minelem
    void norm(){
        for(int i=0;i<=LOG;++i) if(b[i])
            for(int j=0;j<i;++j) if(b[j]&&((b[i]>>j)&1LL)) b[i]^=b[j];
    }

    // Check if x is representable
    bool can(ll x){
        for(int i=LOG;i>=0;--i) if((x>>i)&1LL){ if(!b[i]) return false; x^=b[i]; }
        return true;
    }

    // Maximum/minimum XOR with optional seed
    ll maxxor(ll seed=0) const {
        ll v=seed; for(int i=LOG;i>=0;--i) if(b[i]&&((v^b[i])>v)) v^=b[i]; return v;
    }
    ll minxor(ll seed) const {
        ll v=seed; for(int i=LOG;i>=0;--i) if(b[i]&&((v^b[i])<v)) v^=b[i]; return v;
    }

    // Minimum representable element (requires normalisation)
    ll minelem() const {
        ensure_norm(); if(rk==0||zero) return 0;
        for(int i=0;i<=LOG;++i) if(b[i]) return b[i]; return 0;
    }

    // Collect basis vectors from lowest to highest pivot (requires normalisation)
    vector<ll> low2high() const {
        ensure_norm(); vector<ll> v; v.reserve(rk);
        for(int i=0;i<=LOG;++i) if(b[i]) v.push_back(b[i]); return v;
    }

    // k-th smallest in the span including 0 (1-indexed); -1 on out-of-range
    ll kth_all(ll k) const {
        ensure_norm(); if(k<1) return -1;
        if(rk>=61) return -1;
        ull tot=1ULL<<rk; if((ull)k>tot) return -1;
        auto v=low2high(); ull mask=(ull)k-1; ll ans=0;
        for(int i=0;i<(int)v.size();++i){ if(mask&1ULL) ans^=v[i]; mask>>=1ULL; }
        return ans;
    }

    // k-th smallest among non-empty subsets (1-indexed)
    ll kth_nonempty(ll k) const { return kth_all(k+(!zero)); }

    // k-th largest (1-indexed, k=1 = maximum)
    ll kth_largest(ll k) const {
        if(rk>=61) return -1; ull tot=1ULL<<rk;
        if(k<1||(ull)k>tot) return -1; return kth_all((ll)(tot-(ull)k+1));
    }

    // Merge another basis
    void merge(const LB& o){ for(int i=0;i<=LOG;++i) if(o.b[i]) ins(o.b[i]); }

private:
    void ensure_norm() const {
        if(!dirty) return;
        for(int i=0;i<=LOG;++i) if(b[i])
            for(int j=0;j<i;++j) if(b[j]&&((b[i]>>j)&1LL)) b[i]^=b[j];
        dirty=false;
    }
} S;
```

### 1.4.1 Range XOR Basis

Supports: max XOR over any subarray $[l,r]$.

**Idea:** maintain a prefix basis where each basis vector also records its **position** (the latest index in the original array from which it was inserted). When answering $[l,r]$, only use basis vectors with position $\geq l$.

```cpp
template<int MAXN, int LOG=30>
struct RangeXorBasis {
    uint32_t bas[MAXN+1][LOG+1]{};
    int pos[MAXN+1][LOG+1]{};
    int n=0;

    void init(){ n=0; memset(bas[0],0,sizeof bas[0]); memset(pos[0],0,sizeof pos[0]); }

    void build(const vector<uint32_t>& a, int _n){ init(); for(int i=1;i<=_n;++i) push(a[i]); }

    void push(uint32_t x){
        ++n;
        memcpy(bas[n],bas[n-1],sizeof bas[n]); memcpy(pos[n],pos[n-1],sizeof pos[n]);
        int p=n;
        for(int k=LOG;k>=0;--k){
            if(((x>>k)&1U)==0) continue;
            if(!bas[n][k]){ bas[n][k]=x; pos[n][k]=p; break; }
            if(pos[n][k]<p){ swap(bas[n][k],x); swap(pos[n][k],p); }
            x^=bas[n][k];
        }
    }

    uint32_t maxxor(int l, int r, uint32_t seed=0) const {
        uint32_t v=seed;
        for(int k=LOG;k>=0;--k) if(pos[r][k]>=l) v=max(v,v^bas[r][k]);
        return v;
    }

    bool can(int l, int r, uint32_t x) const {
        for(int k=LOG;k>=0;--k){
            if(((x>>k)&1U)==0) continue;
            if(pos[r][k]<l) return false;
            x^=bas[r][k];
        }
        return true;
    }
};
```

## 1.5 Examples

### Median of XOR Subset Values (Nowcoder)

> Given array of length $N$, find the median of all $2^N-1$ non-empty subset XOR values ($N\leq10^5$, values $\leq10^9$).

**Conclusion:** build basis with rank $r$. The median is the **highest pivot basis vector** (after normalisation).

Equivalently: `kth_all(2^{r-1}+1)` in the "including-0" sorted sequence.

**Why:** Each of the $2^r$ distinct XOR values appears $2^{N-r}$ times in the full multiset (0 appears $2^{N-r}-1$ times for non-empty). Total $2^N-1$ is odd; the median position $2^{N-1}$ falls on the $2^{r-1}$-th distinct positive value:
$$\left\lceil\frac{2^{N-1}-(2^{N-r}-1)}{2^{N-r}}\right\rceil=\left\lceil 2^{r-1}-1+\frac{1}{2^{N-r}}\right\rceil=2^{r-1}$$

Including the offset from 0: rank `2^{r-1}+1` in the "with-0" sequence.

```cpp
int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int N; cin>>N;
    for(int i=0;i<N;++i){ long long x; cin>>x; S.ins(x); }
    if(S.rk==0){ cout<<0<<'\n'; return 0; }
    auto vec=S.low2high();   // ensure_norm() called inside
    cout<<vec.back()<<'\n';  // highest pivot = median
    return 0;
}
```

### CF 1101G — Zero XOR Subset-less

> Given $a_1,\ldots,a_n$, find the maximum number of contiguous segments such that no non-empty subset of segments XORs to 0. $(1\leq n\leq2\times10^5)$

**Setup:** Let $S(i)=a_1\oplus\cdots\oplus a_i$, $S(0)=0$. Segment $[l,r]$ has XOR $= S(r)\oplus S(l-1)$.

**Key reduction:** choosing a set of cut-points $J\ni\{0,n\}$ that divides the array into segments satisfies the condition iff:

> No non-empty even-sized subset of $J$ XORs to 0.

Since $S(0)=0$: adding/removing $S(0)$ maps even-sized subsets to odd-sized and vice versa. The condition is equivalent to: **$J\setminus\{0\}$ is linearly independent** in the XOR sense — i.e., no non-empty subset of $J\setminus\{0\}$ XORs to 0.

Therefore the maximum number of segments equals $\mathrm{rank}\{S(0),S(1),\ldots,S(n)\}$.

**Necessary condition:** $S(n)\neq0$ (the whole array must have non-zero XOR); otherwise output $-1$.

```cpp
#include <bits/stdc++.h>
using namespace std;

struct XorBasis {
    static const int LOG=31;   // a_i <= 1e9
    int b[LOG+1]{}, rnk=0;
    void insert(int x){
        for(int k=LOG;k>=0;--k){
            if(((x>>k)&1)==0) continue;
            if(!b[k]){ b[k]=x; ++rnk; return; }
            x^=b[k];
        }
    }
};

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n; cin>>n; vector<int> a(n+1);
    for(int i=1;i<=n;++i) cin>>a[i];
    vector<int> pref(n+1,0);
    for(int i=1;i<=n;++i) pref[i]=pref[i-1]^a[i];
    if(pref[n]==0){ cout<<-1<<'\n'; return 0; }
    XorBasis B;
    for(int i=0;i<=n;++i) B.insert(pref[i]);
    cout<<B.rnk<<'\n';
    return 0;
}
```

### CF Gym 104768 C — XOR Divisibility

> Given multiset, count non-empty subsets where every element divides the XOR sum. (Answer mod $998244353$)

**Step 1: only two possible XOR values**

All elements $\leq M=\max(S)$, so the XOR sum $g\lt2M$. Since $\mathrm{lcm}(S)\geq M$, we have $0\leq g\lt 2\mathrm{lcm}$. Thus:
$$g\in\{0,\,\mathrm{lcm}(S)\}$$

**Step 2: if $g\neq0$ then $\mathrm{lcm}=M$**

If $\mathrm{lcm}>M$ then $\mathrm{lcm}\geq2M>g$, contradiction. So $g=\mathrm{lcm}=M$.

**Step 3: count = A + B**

- **A (XOR = 0):** $2^{n-r}-1$ non-empty subsets, where $r$ = rank of the entire array's XOR basis.
- **B (XOR = M):** for each distinct value $M$ appearing in the array:
  - Let $D(M)=\{a_i:a_i\mid M\}$ with $m(M)=|D(M)|$ (with multiplicity).
  - Let $r(M)=\mathrm{rank}$ of the set of distinct divisors of $M$ that appear in the array.
  - Contribution: $2^{m(M)-r(M)}$ (each achievable XOR value in the span appears equally, and $M$ is achievable since $M\in D(M)$).

Build divisor lists: for each element $d$, iterate its multiples $M$ and add $d$ to $M$'s divisor list. Harmonic series, $O(n\log n)$.

Total complexity: $O(n\log n\cdot B)$ where $B=20$ bits suffices for values $\leq2\times10^5$.

```cpp
int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int T; cin>>T;
    const int MAXN=200000;
    static int pw2[MAXN+5]; pw2[0]=1;
    for(int i=1;i<=MAXN;++i){ pw2[i]=(pw2[i-1]<<1); if(pw2[i]>=P) pw2[i]-=P; }

    while(T--){
        int n; cin>>n; vector<int> a(n); int Mx=0;
        for(int i=0;i<n;++i){ cin>>a[i]; Mx=max(Mx,a[i]); }
        vector<int> cnt(Mx+1,0); for(int x:a) ++cnt[x];

        LB all; for(int x:a) all.ins(x);
        int r_all=all.rank();

        vector<int> vis; for(int v=1;v<=Mx;++v) if(cnt[v]) vis.push_back(v);

        // for each divisor d, collect its multiples M that appear in array
        vector<vector<int>> ds(Mx+1);
        for(int d:vis) for(int m=d;m<=Mx;m+=d) if(cnt[m]) ds[m].push_back(d);

        ll ans=0;
        ans=(pw2[n-r_all]-1+P)%P;   // part A

        for(int M:vis){
            int mcnt=0; for(int d:ds[M]) mcnt+=cnt[d];
            LB lb; for(int d:ds[M]) lb.ins(d);
            int rM=lb.rank();
            ans=(ans+pw2[mcnt-rM])%P;   // part B
        }
        cout<<ans%P<<'\n';
    }
    return 0;
}
```

---

# 2 Simplex Method for Linear Programming

**Problem:** maximise $c^\top x$ subject to $Ax\leq b$, $x\geq0$.

**Method:** iterate over vertices (basic feasible solutions) of the feasible polytope, improving the objective at each step.

**Handling unconstrained variables:** split $y=y^+-y^-$ with $y^+,y^-\geq0$.

**Complexity:** exponential worst case, near-polynomial in practice.

```cpp
#include <bits/stdc++.h>
using namespace std;
const double INF=1e18, EPS=1e-9;

struct Simplex {
    int n,m; vector<int> B,N; vector<vector<double>> D;

    Simplex(vector<vector<double>>& A, vector<double>& b, vector<double>& c)
        :n(c.size()),m(b.size()),B(m),N(n+1),D(m+2,vector<double>(n+2)){
        for(int i=0;i<m;i++) for(int j=0;j<n;j++) D[i][j]=A[i][j];
        for(int i=0;i<m;i++){ B[i]=n+i; D[i][n]=-1; D[i][n+1]=b[i]; }
        for(int j=0;j<n;j++){ N[j]=j; D[m][j]=-c[j]; }
        N[n]=-1; D[m+1][n]=1;
    }

    void Pivot(int r,int s){
        double inv=1.0/D[r][s];
        for(int i=0;i<m+2;i++) if(i!=r)
            for(int j=0;j<n+2;j++) if(j!=s)
                D[i][j]-=D[r][j]*D[i][s]*inv;
        for(int j=0;j<n+2;j++) if(j!=s) D[r][j]*=inv;
        for(int i=0;i<m+2;i++) if(i!=r) D[i][s]*=-inv;
        D[r][s]=inv; swap(B[r],N[s]);
    }

    bool Simplex1(int phase){
        int x=(phase==1?m+1:m);
        while(true){
            int s=-1;
            for(int j=0;j<=n;j++){
                if(phase==2&&N[j]==-1) continue;
                if(s==-1||D[x][j]<D[x][s]-EPS||(abs(D[x][j]-D[x][s])<EPS&&N[j]<N[s])) s=j;
            }
            if(D[x][s]>-EPS) return true;
            int r=-1;
            for(int i=0;i<m;i++) if(D[i][s]>EPS){
                double val=D[i][n+1]/D[i][s];
                if(r==-1||val<D[r][n+1]/D[r][s]-EPS||
                   (abs(val-D[r][n+1]/D[r][s])<EPS&&B[i]<B[r])) r=i;
            }
            if(r==-1) return false;
            Pivot(r,s);
        }
    }

    // Returns optimal value; -INF = infeasible, +INF = unbounded
    double Solve(vector<double>& x){
        int r=0; for(int i=1;i<m;i++) if(D[i][n+1]<D[r][n+1]) r=i;
        if(D[r][n+1]<-EPS){
            Pivot(r,n); if(!Simplex1(1)||D[m+1][n+1]<-EPS) return -INF;
            if(abs(D[m+1][n+1])>EPS) return -INF;
            if(find(B.begin(),B.end(),-1)!=B.end()){
                int rr=find(B.begin(),B.end(),-1)-B.begin();
                int ss=0; while(ss<=n&&abs(D[rr][ss])<EPS) ss++; Pivot(rr,ss);
            }
        }
        if(!Simplex1(2)) return INF;
        x.assign(n,0); for(int i=0;i<m;i++) if(B[i]<n) x[B[i]]=D[i][n+1];
        return D[m][n+1];
    }
};

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int m,n; cin>>m>>n;
    vector<vector<double>> A(m,vector<double>(n));
    vector<double> b(m),c(n);
    for(int i=0;i<m;i++) for(int j=0;j<n;j++) cin>>A[i][j];
    for(int i=0;i<m;i++) cin>>b[i];
    for(int j=0;j<n;j++) cin>>c[j];
    Simplex solver(A,b,c); vector<double> x;
    double val=solver.Solve(x);
    if(val==-INF) cout<<"No solution\n";
    else if(val==INF) cout<<"Unbounded\n";
    else{
        cout<<fixed<<setprecision(9)<<val<<"\n";
        for(double xi:x) cout<<xi<<" "; cout<<"\n";
    }
    return 0;
}
```

> **Input format:** `m n` (constraints, variables), then $m\times n$ matrix $A$, then vector $b$, then vector $c$.
