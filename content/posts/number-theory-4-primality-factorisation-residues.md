---
title: "Number Theory #4: Primality, Factorisation & Residues (Miller-Rabin, Pollard Rho, Tonelli-Shanks)"
date: 2026-04-28T00:00:00+08:00
slug: "number-theory-4-primality-factorisation-residues"
description: "Miller-Rabin deterministic primality test for 64-bit integers; Pollard Rho integer factorisation; Tonelli-Shanks square roots mod p; cubic roots via extension field; N-th residues over composite modulus via CRT."
summary: "Miller-Rabin primality test, Pollard Rho factorisation, Tonelli-Shanks for quadratic residues, cubic residues via F_p[t]/(t^3-a), quartic residues by double square root, and general k-th residues via primitive root + BSGS, plus N-th residues mod composite."
categories: [Number Theory]
tags: [math, number-theory, miller-rabin, pollard-rho, quadratic-residue, tonelli-shanks, crt]
math: true
toc: true
---

# 1 Miller-Rabin Primality Test

The Miller-Rabin implementation is included in the Pollard Rho template below.

**Deterministic for 64-bit integers** using witnesses $\{2,3,5,7,11,13,17,19,23\}$ — no false positives for $n\lt 3.3\times10^{24}$.

# 2 Pollard Rho Factorisation

> **Template problem: Luogu P4718.**
> Given $n$, determine if it is prime (output `Prime`) or output its largest prime factor.

The template below uses:
- Miller-Rabin with the nine deterministic witnesses.
- Pollard Rho with Brent's cycle detection and batched GCD (every 127 steps and at every power-of-2 cycle length).

```cpp
using i64 = long long;

i64 mul(i64 a, i64 b, i64 m) {
    return static_cast<__int128>(a) * b % m;
}
i64 power(i64 a, i64 b, i64 m) {
    i64 res = 1 % m;
    for (; b; b >>= 1, a = mul(a, a, m))
        if (b & 1) res = mul(res, a, m);
    return res;
}

bool isprime(i64 n) {
    if (n < 2) return false;
    static constexpr int A[] = {2, 3, 5, 7, 11, 13, 17, 19, 23};
    int s = __builtin_ctzll(n - 1);
    i64 d = (n - 1) >> s;
    for (auto a : A) {
        if (a == n) return true;
        i64 x = power(a, d, n);
        if (x == 1 || x == n - 1) continue;
        bool ok = false;
        for (int i = 0; i < s - 1; ++i) {
            x = mul(x, x, n);
            if (x == n - 1) { ok = true; break; }
        }
        if (!ok) return false;
    }
    return true;
}

std::vector<i64> factorize(i64 n) {
    std::vector<i64> p;
    std::function<void(i64)> f = [&](i64 n) {
        if (n <= 10000) {
            for (int i = 2; i * i <= n; ++i)
                for (; n % i == 0; n /= i) p.push_back(i);
            if (n > 1) p.push_back(n);
            return;
        }
        if (isprime(n)) { p.push_back(n); return; }
        auto g = [&](i64 x) { return (mul(x, x, n) + 1) % n; };
        i64 x0 = 2;
        while (true) {
            i64 x = x0, y = x0, d = 1;
            i64 pw = 1, lam = 0, v = 1;
            while (d == 1) {
                y = g(y);
                ++lam;
                v = mul(v, std::abs(x - y), n);
                if (lam % 127 == 0) { d = std::gcd(v, n); v = 1; }
                if (pw == lam) {
                    x = y; pw *= 2; lam = 0;
                    d = std::gcd(v, n); v = 1;
                }
            }
            if (d != n) { f(d); f(n / d); return; }
            ++x0;
        }
    };
    f(n);
    std::sort(p.begin(), p.end());
    return p;
}
```

Alternative (simpler) version using `rand()`:

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

ll gcd(ll a, ll b){ while(b){ ll t=b; b=a%b; a=t; } return a; }

// Miller-Rabin primality test
bool is_prime(ll n, int iter = 5) {
    if (n < 2) return false;
    if (n == 2 || n == 3) return true;
    if (n % 2 == 0) return false;
    ll d = n - 1; int s = 0;
    while (d % 2 == 0) { d /= 2; s++; }
    for (int i = 0; i < iter; i++) {
        ll a = rand() % (n - 2) + 2;
        ll x = 1, base = a, exp = d;
        while (exp > 0) {
            if (exp % 2 == 1) x = (__int128)x * base % n;
            base = (__int128)base * base % n;
            exp /= 2;
        }
        if (x == 1 || x == n - 1) continue;
        bool ok = false;
        for (int r = 1; r < s; r++) {
            x = (__int128)x * x % n;
            if (x == n - 1) { ok = true; break; }
        }
        if (!ok) return false;
    }
    return true;
}

// Pollard's Rho: returns a non-trivial factor of n
ll pollards_rho(ll n) {
    if (n % 2 == 0) return 2;
    srand(time(0));
    ll x = rand() % (n - 2) + 2, y = x;
    ll c = rand() % (n - 1) + 1, d = 1;
    auto f = [&](ll val){ return (__int128(val) * val + c) % n; };
    while (d == 1) {
        x = f(x); y = f(f(y));
        d = gcd(abs(x - y), n);
        if (d == n) return pollards_rho(n);  // restart on failure
    }
    return d;
}

// Fully factorize n into primes
void factorize(ll n, vector<ll> &factors) {
    if (n == 1) return;
    if (is_prime(n)) { factors.push_back(n); return; }
    ll factor = pollards_rho(n);
    factorize(factor, factors);
    factorize(n / factor, factors);
}

int main() {
    ll n = 8051;
    vector<ll> factors;
    factorize(n, factors);
    sort(factors.begin(), factors.end());
    for (auto f : factors) cout << f << " ";
    cout << endl;
}
```

# 3 Quadratic Residues

Solve $x^2\equiv N\pmod{p}$, where $p$ is an odd prime.

- If $N=0$: unique solution $x=0$.
- **Legendre symbol** $\left(\frac{N}{p}\right)=N^{(p-1)/2}\bmod p$: equals $1$ if $N$ is a QR, $p-1$ if not, $0$ if $p\mid N$.
- If $p\equiv3\pmod{4}$: $x=N^{(p+1)/4}\bmod p$ (direct formula).
- Otherwise use **Tonelli-Shanks**.

**Complete library** (quadratic, cubic, quartic, $k$-th residues, $N$-th residue mod composite):

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
using u128 = unsigned __int128;

ll gcd(ll a, int b){ return b ? gcd(b, a%b) : a; }
ll mod(ll x, ll p){ x%=p; if(x<0) x+=p; return x; }
ll mul(ll a, ll b, ll p){ return (ll)((u128)(a%p+p)%p * (u128)(b%p+p)%p % (u128)p); }

ll qp(ll a, ll e, ll p){
    ll r=1%p; a=mod(a,p);
    while(e){ if(e&1) r=mul(r,a,p); a=mul(a,a,p); e>>=1; }
    return r;
}

ll exgcd(ll a, ll b, ll &x, ll &y){
    if(!b){ x=1; y=0; return a; }
    ll x1, y1; ll g=exgcd(b, a%b, x1, y1);
    x=y1; y=x1-(a/b)*y1; return g;
}

ll invmod(ll a, ll m){   // modular inverse (requires gcd(a,m)=1)
    a=mod(a,m); ll x,y; ll g=exgcd(a,m,x,y);
    if(g!=1) throw runtime_error("invmod: gcd!=1");
    return mod(x,m);
}

// Legendre symbol (a|p), p odd prime
ll legendre(ll a, ll p){ return qp(mod(a,p), (p-1)>>1, p); }

vector<ll> factor_unique(ll n){
    vector<ll> f;
    for(ll d=2; d*d<=n; d+=(d==2?1:2)){
        if(n%d==0){ f.push_back(d); while(n%d==0) n/=d; }
    }
    if(n>1) f.push_back(n);
    return f;
}

ll primitive_root(ll p){   // primitive root mod p (p odd prime)
    if(p==2) return 1;
    ll phi=p-1; auto fac=factor_unique(phi);
    for(ll g=2;;++g){
        bool ok=true;
        for(ll q:fac) if(qp(g,phi/q,p)==1){ ok=false; break; }
        if(ok) return g;
    }
}

ll bsgs(ll g, ll a, ll p){   // solve g^x ≡ a (mod p), O(sqrt p)
    g=mod(g,p); a=mod(a,p);
    if(a==1%p) return 0;
    const ll m=(ll)floor(sqrt((long double)(p-1)))+1;
    unordered_map<ll,ll> mp; mp.reserve(m*2);
    ll e=1;
    for(ll j=0;j<m;++j){ if(!mp.count(e)) mp[e]=j; e=mul(e,g,p); }
    ll ginvm=qp(invmod(g,p),m,p);
    ll cur=a;
    for(ll i=0;i<=m;++i){
        auto it=mp.find(cur);
        if(it!=mp.end()) return i*m+it->second;
        cur=mul(cur,ginvm,p);
    }
    return -1;
}

// Tonelli-Shanks: solve x^2 ≡ a (mod p)
vector<ll> sqrt_mod(ll a, ll p){
    a=mod(a,p);
    if(a==0) return {0};
    ll ls=legendre(a,p);
    if(ls==0) return {0};
    if(ls==p-1) return {};   // not a quadratic residue
    if(p%4==3){
        ll x=qp(a,(p+1)/4,p); ll y=mod(p-x,p);
        if(x==y) return {x};
        return (x<y)?vector<ll>{x,y}:vector<ll>{y,x};
    }
    // write p-1 = q * 2^s with q odd
    ll q=p-1, s=0; while((q&1)==0){ q>>=1; ++s; }
    ll z=2; while(legendre(z,p)!=p-1) ++z;  // find a non-residue
    ll c=qp(z,q,p);
    ll x=qp(a,(q+1)/2,p);
    ll t=qp(a,q,p);
    ll m=s;
    while(t!=1){
        ll t2=t; ll i=0;
        while(t2!=1){ t2=mul(t2,t2,p); ++i; if(i==m) return {}; }
        ll b=qp(c,1LL<<(m-i-1),p);
        x=mul(x,b,p); t=mul(t,mul(b,b,p),p); c=mul(b,b,p); m=i;
    }
    ll y=mod(p-x,p);
    if(x==y) return {x};
    return (x<y)?vector<ll>{x,y}:vector<ll>{y,x};
}

vector<ll> quad_root(ll a, ll p){ return sqrt_mod(a,p); }
```

**Wrapper + driver:**

```cpp
void sol() {
    int N, p;
    cin >> N >> p;
    auto v2 = solve_quadratic(N, p);   // x^2 ≡ N mod p
    if (!v2.empty()) {
        for (auto i : v2) cout << i << ' ';
        cout << '\n';
    } else {
        cout << "Hola!" << endl;
    }
}
signed main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int T; cin >> T;
    while(T--) sol();
}
```

# 4 Cubic Residues

Solve $x^3\equiv a\pmod{p}$, $p$ odd prime.

- If $p\equiv2\pmod{3}$: the map $x\mapsto x^3$ is a bijection on $\mathbb{F}_p^*$, so the unique solution is $x=a^{(2p-1)/3}\bmod p$.
- If $p\equiv1\pmod{3}$: use an **extension-field method** in $\mathbb{F}_p[t]/(t^3-a)$.

**Extension field $\mathbb{F}_p[t]/(t^3-a)$:** elements are degree-$\lt3$ polynomials; multiplication reduces modulo $t^3=a$.

```cpp
/* Extension field F_p[t]/(t^3 - a) */
struct S3 { ll s[3]; S3(){s[0]=s[1]=s[2]=0;} S3(ll a0,ll a1,ll a2){s[0]=a0;s[1]=a1;s[2]=a2;} };
static ll S3_A;  // t^3 = S3_A in the extension

inline S3 mul(const S3& A, const S3& B, ll p){
    ll k[3]={0,0,0};
    for(int i=0;i<3;i++) for(int j=0;j<3;j++){
        if(i+j<3)   k[i+j]=(k[i+j]+((__int128)A.s[i]*B.s[j])%p)%p;
        else k[i+j-3]=(k[i+j-3]+((__int128)A.s[i]*B.s[j]%p)*(S3_A%p))%p;
    }
    return S3(k[0]%p,k[1]%p,k[2]%p);
}
inline S3 qp(S3 a, ll e, ll p){   // fast exponentiation in extension field
    S3 r(1,0,0);
    while(e){ if(e&1) r=mul(r,a,p); a=mul(a,a,p); e>>=1; }
    return r;
}
inline S3 rand_S3(ll p){ return S3(rand()%p, rand()%p, rand()%p); }

vector<ll> cubic_root(ll a, ll p){
    a=mod(a,p);
    if(a==0) return {0};
    if(p<=3){
        vector<ll> v;
        for(int x=0;x<p;x++) if((ll)x*x%p*x%p==a) v.push_back(x);
        return v;
    }
    if(p%3==2){   // unique root via fast exponentiation
        ll x=qp(a,(2*p-1)/3,p);
        if(qp(x,3,p)==a) return {x};
        return {};
    }
    // p % 3 == 1: extension field method
    if(qp(a,(p-1)/3,p)!=1) return {};   // not a cubic residue

    // primitive cube root of unity: ω = (-1 + sqrt(-3)) / 2
    auto rt=sqrt_mod(mod(p-3,p),p);   // sqrt(-3) mod p
    if(rt.empty()) return {};
    ll inv2=invmod(2,p);
    ll w=mod((rt[0]-1)*inv2,p);   // one primitive cube root of unity

    S3_A=a;
    ll x=-1;
    // randomly find u such that v = u^{(p-1)/3} is a pure t-term
    while(true){
        S3 u=rand_S3(p);
        S3 v=qp(u,(p-1)/3,p);
        if(v.s[1] && v.s[0]==0 && v.s[2]==0){
            x=invmod(v.s[1],p); break;
        }
    }
    vector<ll> res={x,mul(x,w,p),mul(mul(x,w,p),w,p)};
    sort(res.begin(),res.end());
    res.erase(unique(res.begin(),res.end()),res.end());
    return res;
}
```

# 5 Quartic Residues

> Quartic residues can be solved as nested square roots.

Solve $x^4\equiv a\pmod{p}$ by two applications of `sqrt_mod`:

```cpp
vector<ll> quartic_root(ll a, ll p){
    a=mod(a,p); if(a==0) return {0};
    vector<ll> res; res.reserve(4);
    auto ys=quad_root(a,p);
    for(ll y:ys){ auto xs=quad_root(y,p); for(ll x:xs) res.push_back(x); }
    sort(res.begin(),res.end());
    res.erase(unique(res.begin(),res.end()),res.end());
    vector<ll> ok;
    for(ll x:res) if(qp(x,4,p)==a) ok.push_back(x);
    return ok;
}
```

# 6 General $k$-th Residues (odd prime modulus)

Via primitive root and BSGS: convert $x^k\equiv a$ to a linear congruence in the discrete-log domain.

Let $g$ be a primitive root mod $p$, $a=g^t$ (find $t$ via BSGS), and $x=g^y$. Then $ky\equiv t\pmod{p-1}$.

Let $d=\gcd(k,p-1)$. The equation has solutions iff $d\mid t$; if so, there are $d$ solutions.

```cpp
vector<ll> kth_root(ll a, ll k, ll p){
    if(k<=0) return {};
    a=mod(a,p); if(a==0) return {0};
    ll g=primitive_root(p);
    ll t=bsgs(g,a,p); if(t<0) return {};
    ll m=p-1;
    ll d=gcd((ll)k,m);
    if(t%d) return {};
    ll k_=k/d, t_=t/d, m_=m/d;
    ll invk=invmod(k_,m_);
    ll y0=((__int128)invk*t_)%m_;
    vector<ll> ans; ans.reserve(d);
    for(ll i=0;i<d;++i){
        ll y=(y0+i*m_)%m;
        ll x=qp(g,y,p);
        if(qp(x,k,p)==a) ans.push_back(x);
    }
    sort(ans.begin(),ans.end());
    ans.erase(unique(ans.begin(),ans.end()),ans.end());
    return ans;
}
```

**Unified interface:**

```cpp
// Complexity notes:
// solve_quadratic: O(log p) for p≡3(mod4); O((log p)^2) Tonelli-Shanks otherwise
// solve_cubic:     O(log p) for p≡2(mod3); O(log p) expected via extension field
// solve_quartic:   two Tonelli-Shanks calls, O((log p)^2)
// solve_kth:       primitive root + BSGS, O(sqrt(p) + log p)

vector<ll> solve_quadratic(ll a, ll p){ return quad_root(a,p); }
vector<ll> solve_cubic(ll a, ll p){ return cubic_root(a,p); }
vector<ll> solve_quartic(ll a, ll p){ return quartic_root(a,p); }
vector<ll> solve_kth(ll a, ll k, ll p){
    if(k==2) return solve_quadratic(a,p);
    if(k==3) return solve_cubic(a,p);
    if(k==4) return solve_quartic(a,p);
    return kth_root(a,k,p);
}
```

# 7 $N$-th Residues mod Composite — Luogu P5668

> Given $n,m,k$, find all $x\in[0,m-1]$ with $x^n\equiv k\pmod{m}$. Output count and solutions in ascending order.

**Strategy:** factorise $m=\prod p_i^{q_i}$, solve $x^n\equiv k\pmod{p_i^{q_i}}$ for each prime power, then combine via CRT.

**Solving $x^n\equiv k\pmod{p^q}$:**

- Handle $v_p(k)$ (the $p$-adic valuation of $k$): need $v_p(x)=v_p(k)/n$, so $n\mid v_p(k)$.
- Reduce to a unit-group equation in $(\mathbb{Z}/p^r\mathbb{Z})^*$ where $r=q-v_p(k)$.
- For odd $p$: the unit group is cyclic of order $\phi(p^r)=p^{r-1}(p-1)$; use primitive root + BSGS.
- For $p=2$: the unit group is $\mathbb{Z}/2\times\mathbb{Z}/2^{r-2}$ for $r\geq3$, generated by $-1$ and $5$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;
using i128 = __int128_t;

ll gcdll(ll a, ll b){ return b ? gcdll(b, a%b) : (a>=0?a:-a); }

ll qp(ll a, ll e, ll m){
    ll r=1; a%=m;
    while(e){ if(e&1) r=(i128)r*a%m; a=(i128)a*a%m; e>>=1; }
    return r;
}
ll ecgcd(ll a, ll b, ll &x, ll &y){
    if(!a){ x=0; y=1; return b; }
    ll x1,y1; ll g=ecgcd(b%a,a,x1,y1);
    x=y1-(b/a)*x1; y=x1; return g;
}
ll inv(ll a, ll m){
    ll x,y; ll g=ecgcd((a%m+m)%m,m,x,y);
    if(g!=1) return -1;
    return (x%m+m)%m;
}
map<ll,int> factor(ll m){   // prime factorisation (m <= 1e9)
    map<ll,int> f;
    for(ll i=2; i*i<=m; ++i){
        if(m%i==0){ int c=0; while(m%i==0){m/=i;++c;} f[i]=c; }
    }
    if(m>1) f[m]=1;
    return f;
}

ll bsgs(ll g, ll h, ll mod){
    if(h>=mod) return -1;
    if(g%mod==0) return (h==0?1:-1);
    if(h==1) return 0;
    ll s=(ll)sqrtl(mod)+1;
    unordered_map<ll,ll> tab; tab.reserve(s<<1); tab.max_load_factor(0.7f);
    ll cur=1;
    for(ll j=0;j<s;++j){ if(!tab.count(cur)) tab.emplace(cur,j); cur=(i128)cur*g%mod; }
    ll gs=cur, inv_gs=inv(gs,mod);
    if(inv_gs==-1) return -1;
    ll t=h%mod;
    for(ll i=0;i<s;++i){
        auto it=tab.find(t);
        if(it!=tab.end()) return i*s+it->second;
        t=(i128)t*inv_gs%mod;
    }
    return -1;
}

ll primitive_root(ll p){
    if(p==2) return 1;
    ll phi=p-1; auto fac=factor(phi);
    for(ll g=2;g<p;++g){
        bool ok=true;
        for(auto &kv:fac) if(qp(g,phi/kv.first,p)==1){ok=false;break;}
        if(ok) return g;
    }
    return -1;
}

vector<ll> ANS;
void crt_dfs(int idx, ll x, ll mod_now, vector<ll>& mods, vector<vector<ll>>& sols){
    if(idx==(int)mods.size()){ ANS.push_back(x); return; }
    ll m2=mods[idx];
    for(ll y:sols[idx]){
        ll M=mod_now*m2;
        ll inv_m=inv(mod_now%m2,m2);
        ll t=((y-x)%m2+m2)%m2;
        ll nxt=(x+(i128)mod_now*((i128)t*inv_m%m2))%M;
        crt_dfs(idx+1,(nxt+M)%M,M,mods,sols);
    }
}

// Solve x^n ≡ k (mod p^q), return all solutions in [0, p^q)
vector<ll> solve_pq(ll n, ll k, ll p, int q){
    ll pq=1; for(int i=0;i<q;++i) pq*=p;
    k%=pq;

    if(k==0){   // x ≡ 0 (mod p^ceil(q/n))
        vector<ll> r;
        if(n==0) return r;
        ll e=(q+n-1)/n;
        if(e>q){ r.push_back(0); return r; }
        ll pe=1; for(int i=0;i<e;++i) pe*=p;
        ll cnt=pq/pe; r.reserve(cnt);
        for(ll i=0;i<cnt;++i) r.push_back(i*pe);
        return r;
    }

    // compute v_p(k)
    ll v=0, tk=k;
    while(tk%p==0){ tk/=p; ++v; }
    if(v%n) return {};

    ll a=v/n;
    ll kp=k; for(int i=0;i<v;++i) kp/=p;
    ll r=q-v, pr=1; for(int i=0;i<r;++i) pr*=p;

    vector<ll> ys;
    if(r>0){
        if(p==2){
            if(r==1){ if(kp&1) ys.push_back(1); }
            else if(r==2){
                if(n&1){ if(kp%4==1) ys.push_back(1); if(kp%4==3) ys.push_back(3); }
                else{ if(kp%4==1){ ys.push_back(1); ys.push_back(3); } }
            } else {  // r >= 3: unit group C2 × C_{2^{r-2}}, generators -1 and 5
                ll lam=1; for(int i=0;i<r-2;++i) lam<<=1;
                ll n2=n%lam; if(!n2) n2=lam;
                int ac=(kp%4==1?0:1);
                ll c2=(ac==0?kp%pr:(pr-kp)%pr);
                ll bc=bsgs(5,c2,pr); if(bc==-1) return {};
                vector<ll> As, Bs;
                if(n&1) As.push_back(ac);
                else if(ac==0){ As.push_back(0); As.push_back(1); }
                ll g=gcdll(n2,lam);
                if(bc%g==0){
                    ll b0=(i128)(bc/g)*inv(n2/g,lam/g)%(lam/g);
                    for(ll i=0;i<g;++i) Bs.push_back(b0+i*(lam/g));
                }
                for(ll A:As) for(ll B:Bs){
                    ll y=qp(5,B,pr);
                    if(A) y=(pr-y)%pr;
                    ys.push_back(y);
                }
            }
        } else {  // odd prime p: cyclic unit group, find primitive root of p^r
            ll phi=pr/p*(p-1), nphi=n%phi; if(!nphi) nphi=phi;
            ll g=primitive_root(p);
            if(r>1 && qp(g,p-1,p*p)==1) g+=p;  // lift to p^r if needed
            ll b=bsgs(g,kp%pr,pr); if(b==-1) return {};
            ll d=gcdll(nphi,phi); if(b%d) return {};
            ll a0=(i128)(b/d)*inv(nphi/d,phi/d)%(phi/d);
            for(ll i=0;i<d;++i) ys.push_back(qp(g,a0+i*(phi/d),pr));
        }
    } else {
        ys.push_back(0);
    }

    // reconstruct x = p^a * y, with free-variable block
    vector<ll> ret;
    if(ys.empty()) return ret;
    ll pa=1; for(int i=0;i<a;++i) pa*=p;
    ll step=1; for(int i=0;i<q-v+a;++i) step*=p;   // p^{q-v+a}
    ll cnt=1;  for(int i=0;i<v-a;++i) cnt*=p;       // p^{v-a}
    ret.reserve((size_t)ys.size()*cnt);
    for(ll y:ys){
        ll x0=(i128)pa*(y%pq)%pq;
        for(ll i=0;i<cnt;++i) ret.push_back((x0+(i128)i*step)%pq);
    }
    return ret;
}

void sol(){
    ll n, m, k; cin>>n>>m>>k;
    if(m==1){ cout<<1<<'\n'<<0<<'\n'; return; }
    auto fac=factor(m);
    vector<ll> mods; vector<vector<ll>> all;
    for(auto &kv:fac){
        ll p=kv.first; int q=kv.second;
        ll pq=1; for(int i=0;i<q;++i) pq*=p;
        mods.push_back(pq);
        auto v=solve_pq(n,k,p,q);
        if(v.empty()){ cout<<0<<'\n'; return; }
        all.push_back(move(v));
    }
    ANS.clear();
    crt_dfs(0,0,1,mods,all);
    sort(ANS.begin(),ANS.end());
    cout<<ANS.size()<<'\n';
    for(size_t i=0;i<ANS.size();++i){ if(i) cout<<' '; cout<<ANS[i]; }
    if(!ANS.empty()) cout<<'\n';
}

int main(){
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int T; cin>>T;
    while(T--) sol();
    return 0;
}
```
