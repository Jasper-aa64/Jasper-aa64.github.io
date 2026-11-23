---
title: "C0: Mathematics in Contests"
date: 2026-10-30
slug: "c0-contest-math-overview"
description: "How to think about number theory, counting and linear algebra in a contest: read the limits to fix the complexity, print small cases to find the pattern, and derive with five recurring moves (change what you enumerate, swap the order of summation, expand the condition, count contributions, trade exactly for at-least). Each tool comes with what it solves, the signal that points to it and how its formula is derived; three problems are then solved from the statement up. 13 practice problems at the end."
weight: 10
math: true
toc: true
---
In the mathematics problems of the second half of a contest, the hard part is rarely the theorem itself. Most theorems can be memorised; what goes wrong is not seeing which one a problem needs, or seeing it and failing to derive a form that can be coded. So this post is ordered by what you do in a contest rather than by theorem: first how to approach a mathematics problem at all (section 1), then number theory, counting and linear algebra, with each tool described by what it solves, which signal in the statement points to it and how its formula is derived (sections 2 to 4), and finally three problems written from the statement up (section 5).

## 1. How to approach a mathematics problem

### 1.1 Limits: fix the complexity first

Limits say more about the method in mathematics problems than anywhere else, because they are often so large that only one or two kinds of algorithm survive. C++ does about $10^8$ simple operations per second, which gives:

| Limit | Acceptable complexity | Where to look |
|---|---|---|
| $n \le 10^{18}$ | $O(\log n)$, or $O(k^3 \log n)$ | fast power, matrix power, linear recurrences, a closed form found from a pattern |
| $n \le 10^{10}$ to $10^{11}$ | $O(n^{2/3})$, $O(\sqrt n)$ | division blocks, Du's sieve, min_25 |
| $n \le 10^7$ | $O(n)$ | linear sieve, factorial tables |
| $n \le 10^5$ to $10^6$ with a convolution | $O(n \log n)$ | NTT, polynomials |
| $n \le 5000$ | $O(n^2)$ | binomial recurrences, counting DP |
| $n \le 500$ | $O(n^3)$ | Gaussian elimination, determinants |
| $n \le 20$ | $O(2^n n)$ | inclusion-exclusion over subsets, bitmask DP |

The modulus says less than the limits do. 998244353 is now the default modulus in many contests, so seeing it does not mean a convolution is coming; it matters in the other direction: $998244353 = 119 \cdot 2^{23} + 1$, so its multiplicative group has an element of order $2^{23}$, and when the derivation produces a convolution, NTT works directly. With a modulus like $10^9 + 7$ and a convolution in the formula, NTT does not apply directly, and you switch to three-modulus NTT or split-coefficient FFT. **Whether to convolve is decided by the derived formula, not by the modulus.** Both moduli are prime, so inverses come from Fermat's little theorem. If the modulus is not prime, or is given in the input, inverses may not exist and you switch to exgcd, splitting into prime powers and merging with CRT if needed. If the modulus is a small prime and $n$ exceeds it, factorials contain $p$, the factorial table breaks, and Lucas takes over.

### 1.2 Print a table: let brute force find the pattern

Before deriving anything, write a brute force and print the answers for small inputs. Look at the table for three things. First, is it multiplicative, $f(ab) = f(a) f(b)$ for coprime $a, b$? Then a linear sieve computes it. Second, does it satisfy a linear recurrence? Then BM plus fast evaluation of the $n$-th term works (4.3). Third, is it a sequence you know: $2^n$, $n!$, Catalan, Stirling, Fibonacci?

The brute force has a second job: compare the final formula against it on small inputs before submitting. A wrong sign or an off-by-one boundary in a mathematics problem often still passes the samples. **Write the brute force first: it finds the pattern, and later it is the reference answer for checking.** While a teammate is busy with another problem, this takes five minutes.

### 1.3 Five moves for deriving formulas

Deriving formulas looks like inspiration, but the same five moves keep coming back.

**Change what you enumerate.** When enumerating what the statement gives is too slow, enumerate a quantity with fewer values. $\sum_{i \le n}\sum_{j \le n} f(\gcd(i, j))$ has $n^2$ pairs but only $n$ possible gcds, so enumerate $d = \gcd(i, j)$ and count the pairs whose gcd is exactly $d$. "The sum of the maximum over all subsets" is the same: there are $2^n$ subsets, so enumerate which element is the maximum instead.

**Swap the order of summation.** When the inner condition depends on the outer variable, turning the sums around often makes the inner sum a number you can write down:

$$\sum_{i=1}^{n} \sum_{d \mid i} g(d) = \sum_{d=1}^{n} g(d) \cdot \#\{\, i \le n : d \mid i \,\} = \sum_{d=1}^{n} g(d) \left\lfloor \frac{n}{d} \right\rfloor$$

**Write the condition as something that expands.** An indicator like $[\gcd(i,j) = 1]$ cannot be summed directly, but it equals $\sum_{d \mid \gcd(i,j)} \mu(d)$, and once expanded the order of summation can be swapped (2.5). "At least one bad condition holds" expands into a sum over intersections by inclusion-exclusion (3.4).

**Count contributions.** When the answer is a sum over objects of a quantity that is itself a sum over the parts of each object, turn the two sums around: for each part, count how many objects it appears in. Linearity of expectation is the probabilistic version of the same move (3.8).

**Trade exactly for at-least; count the complement.** "Exactly $k$" is often hard while "these $k$ chosen, the rest arbitrary" is easy, and binomial inversion converts between them (3.5). When "none is bad" is hard, count everything and subtract the objects with at least one bad.

**Almost every derivation is a combination of these five moves; when stuck, trying them one by one is more reliable than staring at the formula.** Every derivation in sections 2 to 4 names the move it uses.

### 1.4 Modular basics

Almost every answer is taken modulo something, and these pieces are needed in every contest, so they should come out without thinking:

```cpp
const long long MOD = 1'000'000'007;

long long qpow(long long a, long long e, long long m = MOD) {
    long long r = 1 % m;
    a %= m;
    if (a < 0) a += m;
    for (; e > 0; e >>= 1, a = a * a % m)
        if (e & 1) r = r * a % m;
    return r;
}
long long inv(long long a) { return qpow(a, MOD - 2); }  // only valid when MOD is prime

struct Binom {
    vector<long long> f, fi;
    Binom(int n) : f(n + 1), fi(n + 1) {
        f[0] = 1;
        for (int i = 1; i <= n; i++) f[i] = f[i - 1] * i % MOD;
        fi[n] = inv(f[n]);
        for (int i = n; i > 0; i--) fi[i - 1] = fi[i] * i % MOD;
    }
    long long C(int n, int k) const {
        if (k < 0 || k > n) return 0;
        return f[n] * fi[k] % MOD * fi[n - k] % MOD;
    }
};
```

The inverse uses Fermat's little theorem: for prime $p$ with $p \nmid a$, $a^{p-1} \equiv 1$, so $a^{-1} \equiv a^{p-2}$. The inverse factorials need only one fast power; the rest go backwards, because $\frac{1}{(i-1)!} = \frac{i}{i!}$ gives `fi[i-1] = fi[i] * i`, so the whole table is $O(n)$. **Replace every division by multiplication with an inverse, and add MOD after every subtraction before reducing**; missing either once gives negative or wrong results.

## 2. Number theory

### 2.1 exgcd: solving $ax + by = c$

Bézout's identity says $ax + by = c$ has integer solutions exactly when $\gcd(a, b) \mid c$. The extended Euclidean algorithm computes the gcd and, along the way, one solution of $ax + by = \gcd(a,b)$. When the recursion on $(b, a \bmod b)$ returns, we have $b x' + (a \bmod b) y' = g$; substitute $a \bmod b = a - \lfloor a/b \rfloor b$ and collect the coefficients of $a$ and $b$:

$$a y' + b \left( x' - \left\lfloor \frac{a}{b} \right\rfloor y' \right) = g$$

So $x = y'$ and $y = x' - \lfloor a/b \rfloor y'$. Passing `x, y` swapped into the recursion leaves only `y` to fix afterwards:

```cpp
// returns g = gcd(a, b) and one solution of a*x + b*y = g
long long exgcd(long long a, long long b, long long& x, long long& y) {
    if (b == 0) { x = 1; y = 0; return a; }
    long long g = exgcd(b, a % b, y, x);
    y -= a / b * x;
    return g;
}
```

Given one solution $(x_0, y_0)$, all solutions of $ax + by = c$ are $x = x_0 \cdot \frac{c}{g} + k \cdot \frac{b}{g}$ (with $y$ following). The congruence $ax \equiv c \pmod m$ is just $ax + my = c$, and the smallest non-negative solution comes from reducing $x$ modulo $m/g$. **Congruences, Diophantine equations and inverses modulo a non-prime are all this one function**, and the inverse exists exactly when $\gcd(a, m) = 1$.

### 2.2 Systems of congruences: merge two at a time

Given $x \equiv r_i \pmod{m_i}$, find $x$. The classic CRT formula needs pairwise coprime moduli; in contests, merging two equations at a time is more common because it needs no such condition. To merge $x \equiv r_1 \pmod{m_1}$ with $x \equiv r_2 \pmod{m_2}$: the first says $x = r_1 + m_1 t$, and substituting into the second gives $m_1 t \equiv r_2 - r_1 \pmod{m_2}$, a congruence in $t$. With $g = \gcd(m_1, m_2)$, there is no solution if $g \nmid (r_2 - r_1)$; otherwise exgcd gives $m_1 p + m_2 q = g$, i.e. $m_1 p \equiv g \pmod{m_2}$, so $t = \frac{r_2 - r_1}{g} p$ works, and $t$ only matters modulo $m_2 / g$. The merged modulus is $\operatorname{lcm}(m_1, m_2)$:

```cpp
// merge x ≡ r1 (mod m1) and x ≡ r2 (mod m2) into r1, m1; false if there is no solution
bool crt_merge(long long& r1, long long& m1, long long r2, long long m2) {
    long long p, q;
    long long g = exgcd(m1, m2, p, q);
    if ((r2 - r1) % g != 0) return false;
    long long t = (__int128)((r2 - r1) / g) * p % (m2 / g);
    long long l = m1 / g * m2;
    r1 = (long long)((((__int128)t * m1 + r1) % l + l) % l);
    m1 = l;
    return true;
}
```

Intermediate products can reach about $10^{36}$, hence `__int128`. **Merging pairwise needs no coprimality, which makes it more general than the CRT formula**; a whole system is merged left to right.

### 2.3 Euler's theorem and reducing exponents

For $\gcd(a, m) = 1$, $a^{\varphi(m)} \equiv 1 \pmod m$, with Fermat's little theorem as the prime case. When the exponent $b$ is huge (itself a power, or a long decimal string), it can be reduced modulo $\varphi(m)$. Without coprimality there is the extended form:

$$a^b \equiv a^{\, b \bmod \varphi(m) + \varphi(m)} \pmod m, \quad b \ge \varphi(m)$$

It drops the coprimality requirement at the cost of keeping a $+\varphi(m)$ in the exponent, so you must know whether $b \ge \varphi(m)$. A power tower $a_1^{a_2^{a_3^{\cdots}}} \bmod m$ applies this recursively: the outer level modulo $m$, the exponent modulo $\varphi(m)$, the next level modulo $\varphi(\varphi(m))$. Applying $\varphi$ twice at least halves the number, **so the recursion follows the $\varphi$ chain, which has length $O(\log m)$**, and stops when the modulus reaches 1.

### 2.4 Linear sieve: every value of a multiplicative function at once

A multiplicative function satisfies $f(ab) = f(a) f(b)$ for coprime $a, b$: Euler's $\varphi$, Möbius $\mu$, the divisor count $d$. It is determined by its values on prime powers, so knowing $f(p^k)$ is enough to fill in every $f(n)$ while sieving.

The linear sieve crosses each composite $x$ out exactly once, using its smallest prime factor $p$ and $i = x / p$. The outer loop runs over $i$, the inner loop over primes $p$ in increasing order, crossing out $i \cdot p$; it stops as soon as $p \mid i$, because for any later prime $p' > p$, $p'$ is no longer the smallest prime factor of $i \cdot p'$ ($p$ is smaller and divides it), so that number is left for a later $i$. The moment of stopping also separates the two cases: if $p \nmid i$, then $i$ and $p$ are coprime and the values multiply; if $p \mid i$, then $p$ appears in $i \cdot p$ at least twice and the prime-power rule applies:

```cpp
// linear sieve: each composite is crossed out once, by its smallest prime factor; computes φ and μ
struct Sieve {
    vector<int> primes, phi, mu;
    vector<bool> comp;
    Sieve(int n) : phi(n + 1), mu(n + 1), comp(n + 1) {
        phi[1] = mu[1] = 1;
        for (int i = 2; i <= n; i++) {
            if (!comp[i]) { primes.push_back(i); phi[i] = i - 1; mu[i] = -1; }
            for (int p : primes) {
                if ((long long)i * p > n) break;
                comp[i * p] = true;
                if (i % p == 0) {            // p is i's smallest prime factor; p appears ≥ 2 times in i*p
                    phi[i * p] = phi[i] * p;
                    mu[i * p] = 0;
                    break;
                }
                phi[i * p] = phi[i] * (p - 1);  // i and p are coprime
                mu[i * p] = -mu[i];
            }
        }
    }
};
```

**The whole point of the linear sieve is that `break`: it makes each composite crossed out once, by its smallest prime factor, so the total is $O(n)$, and at $i \cdot p$ it tells you whether $p$ and $i$ are coprime.** To sieve another multiplicative function, replace the two branches with its rules; when $f(p^k)$ does not follow from $f(p^{k-1})$ in one step, keep another array with the power of the smallest prime in $i$.

### 2.5 Dirichlet convolution and Möbius inversion

The Dirichlet convolution of two arithmetic functions is $(f * g)(n) = \sum_{d \mid n} f(d)\, g(n/d)$. With $\mathbf{1}(n) = 1$, $\mathrm{id}(n) = n$ and $\varepsilon(n) = [n = 1]$ (the identity of convolution), four relations come up all the time:

$$\mu * \mathbf{1} = \varepsilon, \qquad \varphi * \mathbf{1} = \mathrm{id}, \qquad \mu * \mathrm{id} = \varphi, \qquad \mathbf{1} * \mathbf{1} = d$$

Written out, the first is $\sum_{d \mid n} \mu(d) = [n = 1]$ and the second is $\sum_{d \mid n} \varphi(d) = n$. Möbius inversion is a corollary of the first: if $F = f * \mathbf{1}$, convolving both sides with $\mu$ gives $f = F * \mu$.

What contests actually use is the expanded form of the first two. $[\gcd(i,j) = 1] = \sum_{d \mid \gcd(i,j)} \mu(d)$ splits a condition into a sum over divisors, and $\gcd(i,j) = \sum_{d \mid \gcd(i,j)} \varphi(d)$ splits a value the same way; afterwards $d \mid \gcd(i,j)$ means $d \mid i$ and $d \mid j$, and the order of summation can be swapped. **In contests inversion has essentially one use: split $[\gcd = 1]$ or the gcd itself into a sum over divisors, then swap the order of summation.** All three formulas in 2.7 are derived this way.

### 2.6 Division blocks: $\lfloor n/i \rfloor$ takes only $O(\sqrt n)$ values

For $i \le \sqrt n$ there are only $\sqrt n$ values of $i$; for $i > \sqrt n$, $\lfloor n/i \rfloor < \sqrt n$, so again at most $\sqrt n$ values. In total $\lfloor n/i \rfloor$ takes at most $2\sqrt n$ values, and equal values form contiguous runs. A run starting at $l$ has quotient $q = \lfloor n/l \rfloor$, and the largest $i$ with the same quotient is $\lfloor n/q \rfloor$, the end of the run. With two variables $n, m$, the run ends at the smaller of the two:

```cpp
// Σ_{d=1}^{min(n,m)} f(d)·⌊n/d⌋·⌊m/d⌋, where pre is the prefix sum of f (pre[0] = 0)
long long block_sum(long long n, long long m, const vector<long long>& pre) {
    long long res = 0;
    for (long long l = 1, r; l <= min(n, m); l = r + 1) {
        r = min(n / (n / l), m / (m / l));
        res += (pre[r] - pre[l - 1]) * (n / l) * (m / l);
    }
    return res;
}
```

**Once a formula becomes $\lfloor n/d \rfloor$ times a function with computable prefix sums, it takes $O(\sqrt n)$**; with many queries, the prefix sums are computed once and each query pays only for the blocks.

### 2.7 The pattern: three gcd sums

This family is the most common in number theory, and all three formulas share one skeleton.

First, count coprime pairs: $\sum_{i=1}^{n} \sum_{j=1}^{m} [\gcd(i,j) = 1]$. Split the condition with $\mu$, swap the sums, and note that $\lfloor n/d \rfloor$ values of $i$ are divisible by $d$:

$$\sum_{i=1}^{n} \sum_{j=1}^{m} \sum_{d \mid i,\, d \mid j} \mu(d) = \sum_{d=1}^{\min(n,m)} \mu(d) \left\lfloor \frac{n}{d} \right\rfloor \left\lfloor \frac{m}{d} \right\rfloor$$

Second, sum the gcd: $\sum_{i,j} \gcd(i,j)$. Split the value with $\varphi * \mathbf{1} = \mathrm{id}$, swap the same way, and get $\sum_{d} \varphi(d) \lfloor n/d \rfloor \lfloor m/d \rfloor$. Section 5.1 solves this one from the statement up.

Third, count pairs whose gcd is prime: $\sum_{p} \sum_{i,j} [\gcd(i,j) = p]$. First change what you enumerate: $\gcd(i,j) = p$ means $i = pi'$, $j = pj'$ with $\gcd(i', j') = 1$, so the inner part is the first formula with limits $n/p$ and $m/p$:

$$\sum_{p} \sum_{d} \mu(d) \left\lfloor \frac{n}{pd} \right\rfloor \left\lfloor \frac{m}{pd} \right\rfloor$$

One division-block pass per prime is too slow. The key step is to set $T = pd$ and enumerate $T$ instead, because $\lfloor n/T \rfloor$ depends on $T$ alone:

$$\sum_{T=1}^{\min(n,m)} \left\lfloor \frac{n}{T} \right\rfloor \left\lfloor \frac{m}{T} \right\rfloor \underbrace{\sum_{p \mid T,\ p \text{ prime}} \mu\!\left(\frac{T}{p}\right)}_{g(T)}$$

$g(T)$ does not depend on the query. Precompute it by running over the multiples of each prime $p$, $O(n \log \log n)$ in total, take prefix sums, and each query is one block pass.

**The three formulas share one skeleton: split the condition or the value into a sum over divisors, swap the order, merge into $\sum_T g(T) \lfloor n/T \rfloor \lfloor m/T \rfloor$, then precompute prefix sums of $g$ and use blocks.** Replacing the product $pd$ by a new variable $T$ is the step people miss; its purpose is to make $\lfloor n/\cdot \rfloor$ depend on one variable. Sums of lcm go the same way: $\operatorname{lcm}(i,j) = \frac{ij}{\gcd(i,j)}$, enumerate the gcd first, split the remaining coprimality with $\mu$, and two nested block passes appear.

### 2.8 $n$ beyond $10^{10}$: Du's sieve

When $n$ is too large for a linear sieve, the prefix sum $S(n) = \sum_{i \le n} f(i)$ of a multiplicative function must be computed directly. Du's sieve finds a helper $g$ such that both $h = f * g$ and $g$ have prefix sums you can write down. Swapping the order of summation in the prefix sum of $h$:

$$\sum_{i=1}^{n} h(i) = \sum_{i=1}^{n} \sum_{d \mid i} g(d)\, f\!\left(\frac{i}{d}\right) = \sum_{d=1}^{n} g(d)\, S\!\left(\left\lfloor \frac{n}{d} \right\rfloor\right)$$

Taking the $d = 1$ term out gives a recursion for $S(n)$:

$$g(1)\, S(n) = \sum_{i=1}^{n} h(i) - \sum_{d=2}^{n} g(d)\, S\!\left(\left\lfloor \frac{n}{d} \right\rfloor\right)$$

The sum on the right goes in blocks and only needs $S$ at the $O(\sqrt n)$ points $\lfloor n/d \rfloor$, which are memoised; with $S$ precomputed up to $n^{2/3}$ by a linear sieve, the total is $O(n^{2/3})$. For $\sum \varphi$ take $g = \mathbf{1}$, $h = \mathrm{id}$, so $S(n) = \frac{n(n+1)}{2} - \sum_{d \ge 2} S(\lfloor n/d \rfloor)$; for $\sum \mu$ take $g = \mathbf{1}$, $h = \varepsilon$, so $S(n) = 1 - \sum_{d \ge 2} S(\lfloor n/d \rfloor)$. **All the skill in Du's sieve is choosing $g$ so that the prefix sums of $f * g$ and $g$ can be written down.**

The min_25 sieve solves the same problem for multiplicative functions where $f(p)$ is a low-degree polynomial in $p$ and $f(p^k)$ is easy: it first computes prime sums at every $\lfloor n/i \rfloor$, then adds the composites recursively by smallest prime factor, in roughly $O(n^{3/4} / \log n)$.

### 2.9 Other number theory tools: recognise the signal

These are used from a template in contests; what to remember is the signal and the cost:

| Signal in the statement | Tool | Cost |
|---|---|---|
| find $x$ with $a^x \equiv b \pmod p$ | BSGS (baby-step giant-step) | $O(\sqrt p)$ |
| test or factor a number around $10^{18}$ | Miller-Rabin + Pollard rho | about $O(n^{1/4})$ |
| solve $x^2 \equiv a \pmod p$ | quadratic residues (Cipolla) | $O(\log p)$ |
| roots of unity for NTT, discrete logarithms, $x^k \equiv a$ | primitive roots | try small candidates; usually found fast |
| $\binom{n}{m} \bmod p$ with small $p$ and large $n$ | Lucas | $O(p + \log_p n)$ |
| the exponent of $p$ in $n!$ | Legendre: $\sum_{k \ge 1} \lfloor n/p^k \rfloor$ | $O(\log_p n)$ |

## 3. Counting

### 3.1 Binomials modulo something: look at $n$ and the modulus

The same $\binom{n}{k} \bmod p$ has four algorithms depending on $n$ and the modulus. For $n \le 5000$, Pascal's rule $\binom{n}{k} = \binom{n-1}{k-1} + \binom{n-1}{k}$ uses only additions and works for any modulus. For a prime modulus larger than $n$, use the factorial tables of 1.4: $O(n)$ precomputation, $O(1)$ per query. For a small prime $p$ with $n \ge p$, factorials contain $p$ and have no inverse, so Lucas's theorem $\binom{n}{m} \equiv \binom{n \bmod p}{m \bmod p} \binom{\lfloor n/p \rfloor}{\lfloor m/p \rfloor}$ splits $n$ into base-$p$ digits. For a composite modulus, compute modulo each prime power and merge with 2.2; such problems are rare. **With a large prime modulus a binomial is three table lookups; otherwise look at the modulus before choosing.**

### 3.2 Basic counting moves: stars and bars, bijections, contributions

Stars and bars counts non-negative integer solutions of $x_1 + \dots + x_k = n$: put $n$ balls in a row and insert $k - 1$ bars to cut it into $k$ pieces; balls and bars take $n + k - 1$ positions, choose which hold bars, so $\binom{n+k-1}{k-1}$. With $x_i \ge 1$, hand each variable one ball first, giving $\binom{n-1}{k-1}$; other lower bounds are handed out the same way. Upper bounds cannot be handled like this and need the inclusion-exclusion of 3.4.

A bijection maps the things to count one-to-one onto things that are easy to count. Catalan numbers are the standard example: paths from $(0,0)$ with $n$ up-steps and $n$ down-steps that never go below 0. There are $\binom{2n}{n}$ paths in all, and a bad path touches $-1$ at some point. Reflect the part of a bad path before its first touch of $-1$: the start moves to $(0, -2)$ and the end stays, which matches bad paths one-to-one with paths from $-2$ to $0$; those have $n+1$ up-steps, so there are $\binom{2n}{n+1}$ of them. Hence

$$C_n = \binom{2n}{n} - \binom{2n}{n+1}$$

Bracket sequences, stack-permutation sequences and binary tree shapes all map onto such paths. The same reflection still works when the floor is not 0 or the numbers of up- and down-steps differ.

Counting contributions is, at bottom, swapping the order of summation. Example: the sum of the maximum over all subsets. Sort the array ascending; the subsets whose maximum is $a_i$ (0-indexed) are any choice from the $i$ smaller elements, $2^i$ of them, so the answer is $\sum_i a_i 2^i$. The sum of all subarray sums works the same way: $a_i$ lies in the $(i+1)(n-i)$ subarrays with left end $\le i$ and right end $\ge i$. **When an object is hard to count as a whole, change the angle: count how many objects each part appears in.**

### 3.3 Balls into boxes: $n$ balls, $k$ boxes

Distribution problems split into twelve cases by whether balls are distinguishable, whether boxes are, and what each box allows; this table should be derivable on the spot. $S(n,k)$ is the Stirling number of the second kind ($n$ distinguishable elements into $k$ unordered non-empty sets), $p(n,k)$ the number of ways to write $n$ as a sum of exactly $k$ positive integers ignoring order, and $k^{\underline{n}} = k(k-1)\cdots(k-n+1)$.

| Balls | Boxes | Any | At least one each | At most one each |
|---|---|---|---|---|
| distinct | distinct | $k^n$ | $k!\, S(n,k)$ | $k^{\underline{n}}$ |
| distinct | identical | $\sum_{i=0}^{k} S(n,i)$ | $S(n,k)$ | $[n \le k]$ |
| identical | distinct | $\binom{n+k-1}{k-1}$ | $\binom{n-1}{k-1}$ | $\binom{k}{n}$ |
| identical | identical | $\sum_{i=0}^{k} p(n,i)$ | $p(n,k)$ | $[n \le k]$ |

Both recurrences come from following one specific element. For $S(n,k)$ follow element $n$: it is a group on its own and the rest form $k-1$ groups, or it joins one of the $k$ groups formed by the first $n-1$ elements, in $k$ ways. For $p(n,k)$ ask whether some part equals 1: if so, remove one 1; if not, subtract 1 from each part, still $k$ parts, with total smaller by $k$:

$$S(n,k) = S(n-1,k-1) + k\, S(n-1,k), \qquad p(n,k) = p(n-1,k-1) + p(n-k,k)$$

**Every cell of the table follows from "where does the last ball go" or "is there a part of size 1", so nothing needs memorising.** Stirling numbers of the first kind $s(n,k)$ count arrangements of $n$ elements into $k$ cycles (permutations with $k$ cycles) by the same idea: element $n$ forms its own cycle, or is inserted after one of the earlier elements in $n-1$ ways, so $s(n,k) = s(n-1,k-1) + (n-1)\, s(n-1,k)$.

### 3.4 Inclusion-exclusion: counting objects that avoid every bad condition

With bad events $A_1, \dots, A_n$, the objects where none happens number

$$\Big| \overline{A_1} \cap \dots \cap \overline{A_n} \Big| = \sum_{S \subseteq \{1..n\}} (-1)^{|S|} \Big| \bigcap_{i \in S} A_i \Big|$$

An object lying in exactly $t \ge 1$ bad events is counted $\sum_{j} (-1)^j \binom{t}{j} = 0$ times on the right, so only objects with no bad event remain. The precondition is that "several bad events at once" is easy to count. When the bad events are symmetric, the size of an intersection depends only on $|S|$, and $2^n$ subsets collapse into $n+1$ terms: $\sum_{i} (-1)^i \binom{n}{i} N(i)$.

Three common examples. Surjections, $n$ distinct balls into $k$ distinct boxes with none empty: the bad event is "box $j$ is empty"; forcing $i$ boxes empty leaves $(k-i)^n$ ways, so the count is $\sum_i (-1)^i \binom{k}{i} (k-i)^n$, which also equals the table's $k!\, S(n,k)$. Derangements, no $i$ in position $i$: force $i$ positions fixed, permute the rest freely, $D_n = \sum_i (-1)^i \binom{n}{i} (n-i)!$. Stars and bars with upper bounds $x_j \le c_j$: the bad event is $x_j \ge c_j + 1$; for a chosen set of bad variables, raise their lower bounds to $c_j + 1$ and apply stars and bars. **Inclusion-exclusion needs intersections of bad events to be easy to count; under symmetry one binomial collapses $2^n$ subsets into $n+1$ terms.**

### 3.5 Binomial inversion: trading exactly for chosen

Let $f(k)$ count objects with exactly $k$ good properties, and $g(k)$ be the "choose $k$ properties to hold, ignore the rest" count: for each $k$-set of properties, count the objects satisfying those, and add up. An object with exactly $i$ properties is counted in $g(k)$ once for each $k$-subset of its $i$ properties, so

$$g(k) = \sum_{i \ge k} \binom{i}{k} f(i) \quad \Longleftrightarrow \quad f(k) = \sum_{i \ge k} (-1)^{i-k} \binom{i}{k} g(i)$$

The inverse formula can be checked by substituting the left side; the inner sum is $\sum_j (-1)^j \binom{t}{j} = [t = 0]$. Example: permutations with exactly $k$ fixed points. Choosing $i$ positions to be fixed, then permuting the rest freely, gives $g(i) = \binom{n}{i} (n-i)!$; substituting gives $f(k)$, and $k = 0$ is the derangement formula of the previous section.

```cpp
// permutations with exactly k fixed points: g(i) = C(n,i)·(n-i)!, then invert
long long exact_fixed(int n, int k, const Binom& B) {
    long long res = 0;
    for (int i = k; i <= n; i++) {
        long long g = B.C(n, i) * B.f[n - i] % MOD;
        long long term = B.C(i, k) * g % MOD;
        res += (i - k) % 2 ? MOD - term : term;
    }
    return res % MOD;
}
```

The other common form trades "at most" for "exactly": $g(k) = \sum_{i \le k} \binom{k}{i} f(i)$ is equivalent to $f(k) = \sum_{i \le k} (-1)^{k-i} \binom{k}{i} g(i)$. The colouring problem of 5.2 uses this form. **When "exactly $k$" is hard, count "these $k$ chosen, the rest arbitrary" and invert; that $g$ is usually a binomial times an unconstrained free part.**

Min-max inversion applies the same idea to maxima and minima: $\max(S) = \sum_{\varnothing \ne T \subseteq S} (-1)^{|T|+1} \min(T)$, and it still holds under expectation. It is for problems where the expected time until all events happen (a maximum) is hard but the expected time until the first one happens (a minimum) is easy, such as the expected number of steps to collect every card when each step yields card $i$ with probability $p_i$.

### 3.6 Generating functions: "how many of each kind" becomes polynomial multiplication

An ordinary generating function (OGF) writes $a_0, a_1, \dots$ as $\sum a_n x^n$. Its use: with several kinds of items, where the number taken of kind $i$ must lie in a set $A_i$, the number of ways to take $n$ items in total is the coefficient of $x^n$ in $\prod_i \big( \sum_{a \in A_i} x^a \big)$, because expanding the product picks one term from each factor and the exponents add up to the total. The usual closed forms:

$$\frac{1}{1-x} = \sum_{n \ge 0} x^n, \qquad \frac{1}{(1-x)^k} = \sum_{n \ge 0} \binom{n+k-1}{k-1} x^n, \qquad 1 + x + \dots + x^c = \frac{1 - x^{c+1}}{1-x}$$

The second one is stars and bars. Stars and bars with upper bounds becomes $\prod_j \frac{1 - x^{c_j+1}}{1-x}$, and expanding the numerator gives one term per subset in the inclusion-exclusion of 3.4: the two derivations meet here. Recurrences can be solved the same way: the Fibonacci generating function satisfies $F = x + xF + x^2 F$, so $F = \frac{x}{1 - x - x^2}$, and partial fractions give the closed form.

An exponential generating function (EGF) is $\sum a_n \frac{x^n}{n!}$ and is for labelled objects. Multiplying two EGFs gives coefficients $\sum_i \binom{n}{i} a_i b_{n-i}$, and the extra $\binom{n}{i}$ is exactly "which $i$ of the $n$ labels go to the first part". So $e^x$ is "one set", $\frac{(e^x - 1)^k}{k!}$ splits into $k$ non-empty unordered sets with coefficients $S(n,k)$, and derangements have EGF $\frac{e^{-x}}{1-x}$. **When joining two objects requires deciding how labels are split between them, use an EGF; when it does not, use an OGF.** A generating function is only bookkeeping; with many terms, the multiplication is done by the NTT of 3.7.

### 3.7 Convolutions and polynomials: NTT is the calculator for generating functions

$c_k = \sum_{i+j=k} a_i b_j$ is polynomial multiplication: $O(n^2)$ directly, $O(n \log n)$ with FFT or NTT. NTT works modulo 998244353 with primitive root 3 and has no floating-point error, so it is the first choice in contests. On top of multiplication sits a set of polynomial templates (inverse, logarithm, exponential, square root), all Newton iteration over multiplication in $O(n \log n)$; divide-and-conquer NTT handles self-convolving recurrences like $f_n = \sum_{i=0}^{n-1} f_i g_{n-i}$ in $O(n \log^2 n)$.

Two related tools belong here. Lagrange interpolation: when the answer is known to be a polynomial of degree $k$ in $n$ (for example $\sum_{i \le n} i^k$ has degree $k+1$), compute $k+2$ values by brute force and interpolate any $n$, in $O(k)$ at consecutive points. FWT computes bitwise convolutions $c_k = \sum_{i \oplus j = k} a_i b_j$ (with $\oplus$ being xor, or, or and) in $O(n \log n)$; summing over all subsets is SOS DP, $O(2^n n)$. **When a problem multiplies many polynomials, or asks for the $n$-th coefficient of a product, that is the signal for NTT.**

### 3.8 Probability and expectation

Linearity of expectation, $E[X + Y] = E[X] + E[Y]$, needs no independence, and it is the most used tool in expectation problems: split the quantity into a sum of indicators, and each indicator's expectation is the probability of its event. The number of fixed points of a random permutation splits into "is position $i$ fixed", each with probability $\frac{1}{n}$, so the expectation is 1 without ever finding the distribution. Coupon collector: with $j$ kinds collected, the wait for a new one is geometric with success rate $\frac{n-j}{n}$ and mean $\frac{n}{n-j}$, so the total is $\sum_j \frac{n}{n-j} = n H_n$.

When it does not split, define states and write equations. Expectation DP usually sets $E[s]$ to the expected remaining steps from state $s$ to the end and works backwards from the end, whose value is known (0), since each state's value is determined by its successors. When the states form cycles there is no DP order, so write one equation per state and solve them with the Gaussian elimination of 4.4. When a probability is required modulo $p$, the fraction $\frac{a}{b}$ becomes $a \cdot b^{-1}$. **In expectation problems look for linearity first: split the total into indicators and ask only for each one's probability; if it does not split, define states and write equations.**

### 3.9 Other counting tools: recognise the signal

| Signal in the statement | Tool |
|---|---|
| configurations equal up to rotation or reflection count once | Burnside / Pólya: $\frac{1}{\lvert G \rvert} \sum_{g \in G} k^{c(g)}$, where $c(g)$ is the number of cycles of $g$ |
| labelled unrooted trees, possibly with given degrees | Prüfer sequences: $n^{n-2}$ in total; $\frac{(n-2)!}{\prod (d_i - 1)!}$ with degrees $d_i$ |
| convolutions over bitwise xor, or, and of indices | FWT |
| for every set, the sum over its subsets | SOS DP |
| counting spanning trees, counting non-intersecting path systems | matrix-tree theorem, LGV (see 4.6) |

## 4. Linear algebra

### 4.1 Matrix power: the $10^{18}$-th term of a linear recurrence

If each state vector comes linearly from the previous one, $v_{i+1} = M v_i$ with $M$ independent of $i$, then $v_n = M^{n-1} v_1$, and computing $M^{n-1}$ by fast power costs $O(k^3 \log n)$, where $k$ is the vector length:

```cpp
using Mat = vector<vector<long long>>;

Mat mul(const Mat& A, const Mat& B) {
    int n = A.size(), K = B.size(), m = B[0].size();
    Mat C(n, vector<long long>(m, 0));
    for (int i = 0; i < n; i++)
        for (int k = 0; k < K; k++) {
            if (!A[i][k]) continue;
            for (int j = 0; j < m; j++) C[i][j] = (C[i][j] + A[i][k] * B[k][j]) % MOD;
        }
    return C;
}
Mat mpow(Mat A, long long e) {
    int n = A.size();
    Mat R(n, vector<long long>(n, 0));
    for (int i = 0; i < n; i++) R[i][i] = 1;
    for (; e > 0; e >>= 1, A = mul(A, A))
        if (e & 1) R = mul(R, A);
    return R;
}
```

**The hard part of matrix power is not the power but the state: everything the next step's formula uses must be in the vector.** A constant in the recurrence needs a 1 in the vector; an index $i$ needs $i$ and 1, since $i + 1 = i + 1 \cdot 1$; a prefix sum needs $S_i$, with $a_{i+1}$ in $S_{i+1} = S_i + a_{i+1}$ expanded by the recurrence. Section 5.3 works one through.

The same tool has two other common uses. In the $k$-th power of a graph's adjacency matrix $A$, $(A^k)_{uv}$ counts walks of length exactly $k$ from $u$ to $v$, because each multiplication by $A$ adds one edge. A DP with fixed transitions over a huge length, such as strings of length $n$ that avoid a pattern (states are positions in the KMP automaton), becomes a matrix the same way.

### 4.2 A different addition and multiplication: (min, +) matrices

Fast power of matrices $C_{ij} = \sum_k A_{ik} B_{kj}$ uses only two properties: multiplication is associative, and it distributes over addition. Replacing "add" by $\min$ and "multiply" by $+$ keeps both, so $C_{ij} = \min_k (A_{ik} + B_{kj})$ can be powered too. With $A$ the edge-weight matrix, its $k$-th power gives shortest walks using exactly $k$ edges; (max, +) works the same way. **As long as the new "add" and "multiply" are associative and distributive, fast power still holds.** Such matrices in a segment tree also handle DP under updates (dynamic DP).

### 4.3 When the matrix is hard to write: tables plus BM

If the answer comes from some $k$-dimensional fixed linear transition, the sequence satisfies a linear recurrence of order at most $k$ even if you never write the matrix: by Cayley-Hamilton, $M$ satisfies its own characteristic polynomial, and multiplying by the initial vector turns that into a recurrence for $a_n$. The Berlekamp-Massey algorithm finds the shortest linear recurrence from the first $2k$ terms in $O(k^2)$; with a recurrence of order $k$, the $n$-th term is $x^n$ modulo the characteristic polynomial, in $O(k^2 \log n)$ (faster with NTT).

In a contest: run a brute-force DP for the first few hundred terms, hand them to BM, then compute the $n$-th term. The precondition is that the underlying process really is a fixed linear transition; to be safe, predict a few extra brute-force terms with the recurrence and submit only if they match. **Anything produced by a fixed linear transition satisfies a linear recurrence: a few hundred brute-force terms through BM beat deriving the matrix by hand.**

### 4.4 Gaussian elimination over three fields

Gaussian elimination goes column by column: find a non-zero pivot row in the current column, swap it up, and use it to clear that column in the other rows. Over the reals pick the pivot of largest absolute value to limit error; modulo a prime, division becomes multiplication by an inverse; modulo 2, each row is a bitset and elimination is xor, $O(n^3 / 64)$. Then read the result: a row saying $0 = $ non-zero means no solution; as many pivots as unknowns means a unique solution; otherwise there are free variables, each can take any value, and the number of solutions is $p^{\text{free}}$ ($2^{\text{free}}$ modulo 2).

Three kinds of signals lead to linear systems. Expected values of random walks on graphs with cycles: $E_u = 1 + \frac{1}{\deg u} \sum_{v \sim u} E_v$, with $E = 0$ at the target, $n$ equations in $n$ unknowns. Light-switch problems: each switch toggles some lights, whether it is pressed an odd number of times is a 0/1 unknown, and each light's final state is an equation modulo 2. And xor constraints of all kinds. **Expectations with cycles, light switches and xor constraints all turn into linear systems, and the number of solutions is read off the free variables.**

### 4.5 Linear basis: a basis under xor

Treat each number as a vector over GF(2); a linear basis is a basis of the space they span, built by eliminating from the highest bit on insertion:

```cpp
struct XorBasis {
    unsigned long long b[64] = {};
    int rank = 0;
    bool insert(unsigned long long x) {
        for (int i = 63; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; rank++; return true; }
            x ^= b[i];
        }
        return false;              // x is already an xor of basis elements
    }
    unsigned long long max_xor() const {
        unsigned long long r = 0;
        for (int i = 63; i >= 0; i--) r = max(r, r ^ b[i]);
        return r;
    }
};
```

Say $n$ numbers give rank $r$. Exactly $2^r$ distinct xor values are reachable; each reachable value comes from $2^{n-r}$ subsets (take any subset of the $n - r$ numbers whose insertion failed and fix it up with the basis); the maximum xor is greedy from the high bit down. **A linear basis is Gaussian elimination modulo 2 done while inserting; think of it first for any "xor of a subset" problem.** Path-xor problems end up here too: the xor values of all paths between two vertices are the xor of any one path combined with some set of cycles, so insert the cycle xor of each non-tree edge into a basis. Range xor problems first become prefix xors.

### 4.6 Determinants and counting: matrix-tree, LGV

A determinant modulo a prime comes from Gaussian elimination: reduce to upper triangular form, multiply the diagonal, flip the sign at each row swap, $O(n^3)$:

```cpp
long long det(Mat a) {             // determinant modulo the prime MOD; entries must be in [0, MOD)
    int n = a.size();
    long long res = 1;
    for (int c = 0; c < n; c++) {
        int piv = -1;
        for (int r = c; r < n; r++)
            if (a[r][c]) { piv = r; break; }
        if (piv < 0) return 0;
        if (piv != c) { swap(a[piv], a[c]); res = MOD - res; }
        res = res * a[c][c] % MOD;
        long long iv = inv(a[c][c]);
        for (int r = c + 1; r < n; r++) {
            long long f = a[r][c] * iv % MOD;
            if (!f) continue;
            for (int j = c; j < n; j++) a[r][j] = (a[r][j] - f * a[c][j] % MOD + MOD) % MOD;
        }
    }
    return res;
}
```

Matrix-tree theorem: for an undirected graph (multiple edges allowed), form the Laplacian $L = D - A$, with $D$ the diagonal degree matrix and $A$ the adjacency matrix (multiple edges counted with multiplicity); delete any one row and the same column, and the determinant of what remains is the number of spanning trees. For out-trees rooted at $r$ in a directed graph, use the in-degree matrix minus the adjacency matrix and delete row and column $r$.

LGV lemma: in a DAG with sources $a_1..a_k$, sinks $b_1..b_k$ and $e(a_i, b_j)$ the number of paths between them, $\det[e(a_i, b_j)]$ equals the signed sum, by pairing, of all systems of pairwise vertex-disjoint paths. On a grid where sources and sinks are both in order, disjoint systems can only pair $a_i \to b_i$, and the determinant is the count itself. **Counting spanning trees and counting non-intersecting paths look like graph theory, but both answers are a determinant.**

## 5. Three problems from scratch

One problem per lane, each in contest order: read the limits for the complexity, derive the formula, write the code, check against brute force.

### 5.1 Number theory: summing gcds

**Statement.** $T$ queries, each giving $n, m$; compute $\sum_{i=1}^{n} \sum_{j=1}^{m} \gcd(i, j)$. $T \le 1000$, $n, m \le 10^7$.

**Limits.** $O(nm)$ per query is out, and even $O(n)$ per query is $10^{10}$, so each query gets about $O(\sqrt n)$. The target is the form $\sum_d f(d) \lfloor n/d \rfloor \lfloor m/d \rfloor$ of 2.6, with prefix sums of $f$ precomputed up to $10^7$.

**Derivation.** Split the gcd into a sum over divisors with $\varphi * \mathbf{1} = \mathrm{id}$ and swap the sums:

$$\sum_{i=1}^{n} \sum_{j=1}^{m} \sum_{d \mid \gcd(i,j)} \varphi(d) = \sum_{d=1}^{\min(n,m)} \varphi(d) \left\lfloor \frac{n}{d} \right\rfloor \left\lfloor \frac{m}{d} \right\rfloor$$

Without remembering $\varphi * \mathbf{1} = \mathrm{id}$ you reach the same place: change what you enumerate, enumerate $\gcd = d$, count pairs with the first formula of 2.7, and get $\sum_d d \sum_k \mu(k) \lfloor \frac{n}{dk} \rfloor \lfloor \frac{m}{dk} \rfloor$; with $T = dk$ the inner part is $\sum_{d \mid T} d\, \mu(T/d) = (\mathrm{id} * \mu)(T) = \varphi(T)$. Two routes meeting at the same formula is good evidence that it is right.

**Time and memory.** Linear sieve $O(N)$ with $N = 10^7$; each query has at most $2(\sqrt n + \sqrt m)$ blocks, about $10^7$ steps for 1000 queries. The answer is at most about $10^{15}$, which fits in `long long` without a modulus. The prefix array of $10^7$ `long long` values takes 80 MB, so the sieve writes $\varphi$ straight into it and turns it into prefix sums in place, with no separate `phi`:

```cpp
#include <bits/stdc++.h>
using namespace std;

const int N = 10'000'000;

long long block_sum(long long n, long long m, const vector<long long>& pre) {
    long long res = 0;
    for (long long l = 1, r; l <= min(n, m); l = r + 1) {
        r = min(n / (n / l), m / (m / l));
        res += (pre[r] - pre[l - 1]) * (n / l) * (m / l);
    }
    return res;
}

int main() {
    // linear sieve for φ, then prefix sums in place to save an array
    vector<long long> pre(N + 1);
    vector<int> primes;
    vector<bool> comp(N + 1);
    pre[1] = 1;
    for (int i = 2; i <= N; i++) {
        if (!comp[i]) { primes.push_back(i); pre[i] = i - 1; }
        for (int p : primes) {
            if ((long long)i * p > N) break;
            comp[i * p] = true;
            if (i % p == 0) { pre[i * p] = pre[i] * p; break; }
            pre[i * p] = pre[i] * (p - 1);
        }
    }
    for (int i = 1; i <= N; i++) pre[i] += pre[i - 1];

    int T;
    scanf("%d", &T);
    while (T--) {
        long long n, m;
        scanf("%lld %lld", &n, &m);
        printf("%lld\n", block_sum(n, m, pre));
    }
}
```

**Check.** 30 queries with $n, m \le 60$ against a double loop, all correct; $n = m = 10^7$ prints 1004297420038032, within `long long`.

### 5.2 Counting: using exactly $m$ colours

**Statement.** $n$ cells in a row, $k$ colours; paint each cell so that adjacent cells differ and exactly $m$ of the colours are used (each of those $m$ at least once, no other colour). Count the ways modulo $10^9+7$. $n \le 10^9$, $m \le k \le 10^6$.

**Limits.** With $n$ up to $10^9$ there is no DP over cells; $n$ can only appear in the exponent of a fast power. $k$ up to $10^6$ allows $O(k \log n)$.

**Derivation.** First choose which $m$ colours, $\binom{k}{m}$ ways; what remains is to use these $m$ colours, all of them, with adjacent cells different: call it $f(m)$. "All of them" is an "exactly", which is hard; relaxing to "only colours from some $j$, not necessarily all" is easy: $j$ choices for the first cell, then $j - 1$ for each next cell, since it only has to differ from its predecessor:

$$g(j) = j\,(j-1)^{n-1}$$

A painting that uses only these $j$ colours actually uses exactly some $i$ of them, so $g(j) = \sum_{i \le j} \binom{j}{i} f(i)$. This is the "at most ↔ exactly" form of 3.5, and inverting gives

$$f(m) = \sum_{j=1}^{m} (-1)^{m-j} \binom{m}{j}\, j\,(j-1)^{n-1}, \qquad \text{answer} = \binom{k}{m} f(m)$$

Check a boundary: for $n = 1$, $(j-1)^0 = 1$ and $f(m) = \sum_j (-1)^{m-j} \binom{m}{j} j$, which is 1 for $m = 1$ and 0 for $m \ge 2$, matching "one cell uses one colour".

**Complexity.** Factorial table $O(k)$; $m$ terms with one fast power each, $O(m \log n)$.

```cpp
#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1'000'000'007;

long long qpow(long long a, long long e, long long m = MOD) {
    long long r = 1 % m;
    a %= m;
    if (a < 0) a += m;
    for (; e > 0; e >>= 1, a = a * a % m)
        if (e & 1) r = r * a % m;
    return r;
}
long long inv(long long a) { return qpow(a, MOD - 2); }

struct Binom {
    vector<long long> f, fi;
    Binom(int n) : f(n + 1), fi(n + 1) {
        f[0] = 1;
        for (int i = 1; i <= n; i++) f[i] = f[i - 1] * i % MOD;
        fi[n] = inv(f[n]);
        for (int i = n; i > 0; i--) fi[i - 1] = fi[i] * i % MOD;
    }
    long long C(int n, int k) const {
        if (k < 0 || k > n) return 0;
        return f[n] * fi[k] % MOD * fi[n - k] % MOD;
    }
};

// length n, adjacent cells differ, all m colours used
long long exact_colors(long long n, int m, const Binom& B) {
    long long res = 0;
    for (int j = 1; j <= m; j++) {
        long long term = B.C(m, j) * j % MOD * qpow(j - 1, n - 1) % MOD;
        res += (m - j) % 2 ? MOD - term : term;
    }
    return res % MOD;
}

int main() {
    long long n;
    int k, m;
    scanf("%lld %d %d", &n, &k, &m);
    Binom B(k);
    printf("%lld\n", B.C(k, m) * exact_colors(n, m, B) % MOD);
}
```

**Check.** Every $(n, k, m)$ with $n \le 5$, $k \le 4$ against enumerating all paintings, all correct.

### 5.3 Linear algebra: summing a recurrence with an index term

**Statement.** $a_1 = a_2 = 1$, $a_i = a_{i-1} + a_{i-2} + i$ for $i \ge 3$. Compute $S_n = \sum_{i=1}^{n} a_i \bmod 10^9+7$ for $n \le 10^{18}$.

**Limits.** $10^{18}$ allows only $O(\log n)$, and the recurrence is linear, so matrix power.

**Derivation.** To design the state, ask what the formula for step $i \to i+1$ uses. $a_{i+1} = a_i + a_{i-1} + (i+1)$ uses $a_i$, $a_{i-1}$ and $i+1$; the next $i+2 = (i+1) + 1$ uses the constant 1; $S_{i+1} = S_i + a_{i+1} = S_i + a_i + a_{i-1} + (i+1)$ uses $S_i$. So the state is $(a_i, a_{i-1}, i+1, 1, S_i)$, and the transition is written row by row:

$$\begin{pmatrix} a_{i+1} \\ a_i \\ i+2 \\ 1 \\ S_{i+1} \end{pmatrix} = \begin{pmatrix} 1 & 1 & 1 & 0 & 0 \\ 1 & 0 & 0 & 0 & 0 \\ 0 & 0 & 1 & 1 & 0 \\ 0 & 0 & 0 & 1 & 0 \\ 1 & 1 & 1 & 0 & 1 \end{pmatrix} \begin{pmatrix} a_i \\ a_{i-1} \\ i+1 \\ 1 \\ S_i \end{pmatrix}$$

Start from $(1, 1, 3, 1, 2)$ at $i = 2$ and multiply $n - 2$ times to reach term $n$; $n = 1$ is handled separately.

**Complexity.** $5^3 \times 60 \approx 7500$ multiplications.

```cpp
#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1'000'000'007;
using Mat = vector<vector<long long>>;

Mat mul(const Mat& A, const Mat& B) {
    int n = A.size(), K = B.size(), m = B[0].size();
    Mat C(n, vector<long long>(m, 0));
    for (int i = 0; i < n; i++)
        for (int k = 0; k < K; k++) {
            if (!A[i][k]) continue;
            for (int j = 0; j < m; j++) C[i][j] = (C[i][j] + A[i][k] * B[k][j]) % MOD;
        }
    return C;
}
Mat mpow(Mat A, long long e) {
    int n = A.size();
    Mat R(n, vector<long long>(n, 0));
    for (int i = 0; i < n; i++) R[i][i] = 1;
    for (; e > 0; e >>= 1, A = mul(A, A))
        if (e & 1) R = mul(R, A);
    return R;
}

int main() {
    long long n;
    scanf("%lld", &n);
    if (n == 1) { puts("1"); return 0; }
    // state (a_i, a_{i-1}, i+1, 1, S_i), from i = 2 to i = n
    Mat M = {{1, 1, 1, 0, 0},
             {1, 0, 0, 0, 0},
             {0, 0, 1, 1, 0},
             {0, 0, 0, 1, 0},
             {1, 1, 1, 0, 1}};
    Mat v = {{1}, {1}, {3}, {1}, {2}};
    printf("%lld\n", mul(mpow(M, n - 2), v)[4][0]);
}
```

**Check.** $n < 60$ against the direct recurrence, all correct. This problem also works without deriving the matrix: feed the first few dozen brute-force terms to BM and it returns a recurrence of order 5, matching the length of the state vector.

## Practice

For each problem, settle three things first: what complexity the limits imply, which moves of section 1.3 it uses, and what formula it reduces to.

Number theory:
- [Luogu P1082 同余方程](https://www.luogu.com.cn/problem/P1082): an inverse via exgcd.
- [Luogu P4777 EXCRT](https://www.luogu.com.cn/problem/P4777): pairwise merging with non-coprime moduli; watch for overflow.
- [Luogu P2257 YY的GCD](https://www.luogu.com.cn/problem/P2257): the third formula of 2.7; how to precompute $g(T)$.
- [Luogu P1829 Crash的数字表格](https://www.luogu.com.cn/problem/P1829): summing lcm, two nested block passes.
- [Luogu P4213 杜教筛](https://www.luogu.com.cn/problem/P4213): $\sum \varphi$ and $\sum \mu$ up to $2^{31}$.

Counting:
- [Luogu P1641 生成字符串](https://www.luogu.com.cn/problem/P1641): reflection with unequal numbers of up- and down-steps.
- [Luogu P1450 硬币购物](https://www.luogu.com.cn/problem/P1450): upper bounds by inclusion-exclusion, $2^4$ subsets for four coins.
- [Luogu P4859 已经没有什么好害怕的了](https://www.luogu.com.cn/problem/P4859): chosen ↔ exactly, with $g$ from a DP.
- [Luogu P4451 整数的lqp拆分](https://www.luogu.com.cn/problem/P4451): a closed form from a generating function.

Linear algebra:
- [Luogu P2886 Cow Relays](https://www.luogu.com.cn/problem/P2886): (min, +) matrix power.
- [Luogu P3232 游走](https://www.luogu.com.cn/problem/P3232): expectation equations, Gaussian elimination, then a greedy step.
- [Luogu P4570 元素](https://www.luogu.com.cn/problem/P4570): linear basis plus greedy.
- [Luogu P4111 小 Z 的房间](https://www.luogu.com.cn/problem/P4111): matrix-tree theorem with a non-prime modulus.
