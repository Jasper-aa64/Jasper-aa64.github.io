---
title: "Matrix #4: Matrix Problems — Fibonacci Subarray Sums, Gaussian Elimination & Expected Value"
date: 2026-04-28T00:00:00+08:00
slug: "matrix-4-problems"
description: "Fibonacci squared sums over all sub-arrays via segment tree with 4-tuple (prod, pre, suf, sum); expected number of random swaps to sort a permutation via cycle-decomposition state space and Gaussian elimination."
summary: "Hard matrix problems: Fibonacci squared subarray sum with segment-tree 4-tuple and companion matrix; cycle-decomposition partition state space for random-swap sorting, first-step analysis, and Gaussian elimination."
categories: [Matrix]
tags: [math, matrix, segment-tree, gaussian-elimination, expected-value, permutation, dp]
math: true
toc: true
---

(Continues from [Matrix #1](../matrix-1-fast-exponentiation))

# 1 Fibonacci Squared Subarray Sum

> **Problem.** Given $a_1,\ldots,a_n$. Define:
> $$f(S)=\sum_{T\subseteq S}\bigl(\mathrm{fib}(\textstyle\sum_{x\in T}x)\bigr)^2$$
> where $\mathrm{fib}(0)=0,\ \mathrm{fib}(1)=1,\ \mathrm{fib}(n)=\mathrm{fib}(n-1)+\mathrm{fib}(n-2)$.
>
> Support:
> 1. Point update $a_p\leftarrow v$.
> 2. Query $\sum_{S=[a_i,\ldots,a_j]}f(S)$ over all contiguous subarrays $[i,j]\subseteq[l,r]$.
>
> $(n,q\leq10^5,\ a_i\leq10^5)$, answer mod $998244353$.

## Setup

Define the companion matrix $B=\begin{pmatrix}2&2&-1\\1&0&0\\0&1&0\end{pmatrix}$ so that $B^k$ encodes $(\mathrm{fib}(k)^2,\ \ldots)$. For each position $a_i$, let $M_i=I+B^{a_i}$ (a $3\times3$ matrix).

The key identity for combining adjacent intervals:
$$\text{given left interval }L\text{ and right interval }R,$$
$$\text{prod}_{LR}=\text{prod}_L\cdot\text{prod}_R$$
$$\text{pre}_{LR}=\text{pre}_L+\text{prod}_L\cdot\text{pre}_R$$
$$\text{suf}_{LR}=\text{suf}_R+\text{suf}_L\cdot\text{prod}_R$$
$$\text{sum}_{LR}=\text{sum}_L+\text{sum}_R+\text{suf}_L\cdot\text{pre}_R$$

Each segment-tree node stores the 4-tuple $(\text{prod},\text{pre},\text{suf},\text{sum})$ — all $3\times3$ matrices. The final answer for a query is `result.sum * v` at index `[0][0]`, where $v=[0,1,1]^\top$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
const int MOD = 998244353;

struct Mat {
    int a[3][3];
    Mat(bool ident=false){
        for(int i=0;i<3;i++) for(int j=0;j<3;j++) a[i][j]=(ident&&i==j)?1:0;
    }
};
inline int addm(int x,int y){ int z=x+y; if(z>=MOD) z-=MOD; return z; }
inline int mulm(ll x,ll y){ return (int)(x*y%MOD); }

Mat operator+(const Mat& A,const Mat& B){
    Mat C;
    for(int i=0;i<3;i++) for(int j=0;j<3;j++) C.a[i][j]=addm(A.a[i][j],B.a[i][j]);
    return C;
}
Mat operator*(const Mat& A,const Mat& B){
    Mat C;
    for(int i=0;i<3;i++) for(int k=0;k<3;k++) if(A.a[i][k])
        for(int j=0;j<3;j++) C.a[i][j]=addm(C.a[i][j],mulm(A.a[i][k],B.a[k][j]));
    return C;
}
Mat mpow(Mat A,int e){
    Mat R(true);
    while(e){ if(e&1) R=A*R; A=A*A; e>>=1; }
    return R;
}

struct Node { int l,r; Mat prod,pre,suf,sum; };
const int N=100000+5;
int n,q,a[N];

Mat B,I(true),G;   // companion matrix, identity, initial column vector

Node seg[N<<2];

inline void pull(Node& rt,const Node& L,const Node& R){
    rt.prod=L.prod*R.prod;
    rt.pre =L.pre +(L.prod*R.pre);
    rt.suf =R.suf +(L.suf *R.prod);
    rt.sum =L.sum + R.sum+(L.suf*R.pre);
}
inline void build(int u,int l,int r){
    seg[u].l=l; seg[u].r=r;
    if(l==r){
        Mat M=I+mpow(B,a[l]);    // leaf: I + B^{a_l}
        seg[u].prod=seg[u].pre=seg[u].suf=seg[u].sum=M;
        return;
    }
    int m=(l+r)>>1;
    build(u<<1,l,m); build(u<<1|1,m+1,r);
    pull(seg[u],seg[u<<1],seg[u<<1|1]);
}
inline void modify(int u,int p,int val){
    if(seg[u].l==seg[u].r){
        Mat M=I+mpow(B,val);
        seg[u].prod=seg[u].pre=seg[u].suf=seg[u].sum=M;
        return;
    }
    int m=(seg[u].l+seg[u].r)>>1;
    if(p<=m) modify(u<<1,p,val); else modify(u<<1|1,p,val);
    pull(seg[u],seg[u<<1],seg[u<<1|1]);
}
Node query(int u,int L,int R){
    if(L<=seg[u].l&&seg[u].r<=R) return seg[u];
    int m=(seg[u].l+seg[u].r)>>1;
    if(R<=m) return query(u<<1,L,R);
    if(L>m)  return query(u<<1|1,L,R);
    Node left=query(u<<1,L,R), right=query(u<<1|1,L,R);
    Node res; pull(res,left,right); return res;
}

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    // companion matrix B: [2 2 -1; 1 0 0; 0 1 0]
    B=Mat();
    B.a[0][0]=2; B.a[0][1]=2; B.a[0][2]=MOD-1;
    B.a[1][0]=1; B.a[2][1]=1;
    // initial vector G = [0,1,1]^T stored as a 3x1 "matrix"
    G=Mat(); G.a[1][0]=1; G.a[2][0]=1;

    cin>>n>>q;
    for(int i=1;i<=n;i++) cin>>a[i];
    build(1,1,n);

    while(q--){
        int op; cin>>op;
        if(op==1){ int p,v; cin>>p>>v; a[p]=v; modify(1,p,v); }
        else{
            int l,r; cin>>l>>r;
            Node res=query(1,l,r);
            Mat ans=res.sum*G;
            cout<<ans.a[0][0]<<'\n';
        }
    }
    return 0;
}
```

---

# 2 Gaussian Elimination — Expected Random-Swap Sort

## 2.1 Problem — CodeChef CHEFONM

> A permutation of $n$ elements. Each step: uniformly pick an unordered pair $\{i,j\}$ and swap them. Find the expected number of steps to sort the permutation (reach the identity). Output for all initial cycle types.

**Total pairs:** $T=\binom{n}{2}$.

## 2.2 State Space: Cycle-Type Partition

A permutation's cycle structure is fully described by the multiset of cycle lengths (the "cycle type"). For example, a permutation of 6 elements might be in state $[3,2,1]$.

The number of distinct cycle types for $n$ elements equals $p(n)$ (partition function), which is small for small $n$ — this is why the approach is feasible.

## 2.3 One-Step Transitions

**A) Split: swap within the same cycle of length $L$**

Swapping two elements at "distance" $j$ (chord length $j$ in the cycle, $1\leq j\leq L-1$) splits the cycle into lengths $j$ and $L-j$.

Number of such unordered pairs in an $L$-cycle:
- $j\neq L/2$: exactly $L$ pairs.
- $j=L/2$ (only when $L$ even): exactly $L/2$ pairs.

For simplicity in implementation: iterate $j$ from 1 to $L-1$; for each $j$, add probability $\frac{L}{2T}$ to the transition splitting into $\{j, L-j\}$. This automatically accounts for the double-counting when $j=L-j$.

**B) Merge: swap across two different cycles of lengths $a$ and $b$**

The number of cross-pairs is $a\cdot b$, so the merging probability is $\frac{ab}{T}$.

## 2.4 Linear System via First-Step Analysis

Let $E[S]$ = expected steps to reach all-ones partition from state $S$.

$$E[S_{\text{ok}}]=0,\qquad E[S]=1+\sum_{S'}p(S\to S')\,E[S']$$

Rearranging: $E[S]-\sum_{S'}p(S\to S')\,E[S']=1$.

In matrix form: $(I-Q)\mathbf{e}=\mathbf{1}$ where $Q_{S,S'}=p(S\to S')$. Solve by Gaussian elimination.

> **When to use Gaussian elimination vs. DP:**
> - **DAG (no cycles):** DP along reverse topological order, $O(V+E)$. Equivalently, back-substitution on a triangular system.
> - **Cyclic graph:** states depend on each other in a cycle (e.g. partition $[2,1]\leftrightarrow[3]$ can transition both ways). Must solve the full linear system $(I-Q)\mathbf{e}=\mathbf{1}$, $O(K^3)$ Gaussian elimination.
> - **Hybrid:** find SCCs, compress to a DAG; solve each SCC's small system separately, propagate along DAG. Complexity: $\sum_iO(k_i^3)+O(E)$.
>
> **Rule of thumb:** topological order when possible; linear equations only when cycles are unavoidable (and the state space is small enough after compression).

## 2.5 Implementation

```cpp
#include <bits/stdc++.h>
constexpr int N = 10;
vector<double> anss[N + 1];

vector<double> gauss(vector<vector<double>> a, vector<double> b) {
    int n = a.size();
    for (int i = 0; i < n; ++i) {
        double x = a[i][i];
        for (int j = i; j < n; ++j) a[i][j] /= x;
        b[i] /= x;
        for (int j = 0; j < n; ++j) {
            if (i == j) continue;
            x = a[j][i];
            for (int k = i; k < n; ++k) a[j][k] -= a[i][k] * x;
            b[j] -= b[i] * x;
        }
    }
    return b;
}

int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    cout << fixed << setprecision(7);

    vector<vector<int>> partitions[N + 1];
    for (int n = 1; n <= N; ++n) {
        vector<int> partition;
        // DFS generates partitions in ascending order
        function<void(int,int)> dfs = [&](int rest, int last){
            if (rest == 0){ partitions[n].push_back(partition); return; }
            for (int i = 1; i <= last && i <= rest; ++i){
                partition.push_back(i); dfs(rest-i, i); partition.pop_back();
            }
        };
        dfs(n, n);

        int cnt = partitions[n].size();
        vector<vector<double>> a(cnt, vector<double>(cnt));
        vector<double> b(cnt);
        a[0][0] = 1;   // terminal state: E = 0  →  A[0][0]=1, b[0]=0

        for (int x = 1; x < cnt; ++x) {
            partition = partitions[n][x];
            a[x][x] += 1;   // diagonal: coefficient of E[S]
            b[x] += 1;      // RHS constant
            int T = n * (n - 1) / 2;

            // A) split: swap within a cycle of length partition[i]
            for (int i = 0; i < (int)partition.size(); ++i) {
                for (int j = 1; j < partition[i]; ++j) {
                    double prob = partition[i] * 0.5 / T;
                    auto newP(partition);
                    newP.erase(newP.begin() + i);
                    newP.push_back(j);
                    newP.push_back(partition[i] - j);
                    sort(newP.begin(), newP.end(), greater<>());
                    int idx = lower_bound(partitions[n].begin(), partitions[n].end(), newP)
                              - partitions[n].begin();
                    a[x][idx] -= prob;
                }
            }
            // B) merge: swap across two different cycles
            for (int i = 0; i < (int)partition.size(); ++i) {
                for (int j = 0; j < i; ++j) {
                    double prob = partition[i] * partition[j] * 1.0 / T;
                    auto newP(partition);
                    newP.erase(newP.begin() + i);
                    newP.erase(newP.begin() + j);
                    newP.push_back(partition[i] + partition[j]);
                    sort(newP.begin(), newP.end(), greater<>());
                    int idx = lower_bound(partitions[n].begin(), partitions[n].end(), newP)
                              - partitions[n].begin();
                    a[x][idx] -= prob;
                }
            }
        }
        anss[n] = gauss(a, b);
    }

    int t; cin >> t;
    while (t--) {
        int n; cin >> n;
        vector<int> a(n);
        for (int i = 0; i < n; ++i){ cin >> a[i]; --a[i]; }
        // find cycle type of the input permutation
        vector<bool> vis(n);
        vector<int> partition;
        for (int i = 0; i < n; ++i) {
            if (vis[i]) continue;
            int len = 0;
            for (int j = i; !vis[j]; j = a[j], ++len) vis[j] = true;
            partition.push_back(len);
        }
        sort(partition.begin(), partition.end(), greater<>());
        int idx = lower_bound(partitions[n].begin(), partitions[n].end(), partition)
                  - partitions[n].begin();
        cout << anss[n][idx] << "\n";
    }
    return 0;
}
```
