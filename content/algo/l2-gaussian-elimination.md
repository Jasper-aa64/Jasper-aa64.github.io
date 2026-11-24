---
title: "L2: Gaussian Elimination"
date: 2026-11-24
slug: "l2-gaussian-elimination"
aliases: ["/algo/l3-gaussian-elimination/"]
description: "Gaussian elimination uses row operations that keep the solution set to bring a system into reduced row echelon form, then reads off no solution, a unique solution or free variables. Over the reals pick the largest pivot (P2455 classification, P3232 expectations with cycles); modulo a prime replace division by a modular inverse (P4783 matrix inverse, determinants); mod 2 addition and subtraction are XOR and a row is a bitset (POJ 1222 Lights Out, CF 1344F colors as GF(2) vectors); incremental elimination adds one equation at a time, and an XOR basis is a special case (2024 Kunming E, interactive). With a step-by-step animation and 6 practice problems."
weight: 16
math: true
toc: true
---
> The essence of Gaussian elimination: use row operations that keep the solution set to turn a system into a shape whose solution can be read at a glance.

Expectations with cycles, Lights Out, XOR constraints, matrix inverses and determinants all become linear systems, and all use one algorithm with different arithmetic. [L1](/algo/l1-linear-algebra/) explains where the facts about solutions come from (image and kernel); this post covers how to eliminate and where it shows up in problems: the elimination itself (section 1), which lines change for each field (sections 2 to 4), and the incremental version that adds one equation at a time (section 5). Each section ends with a problem.

## 1. What Elimination Does

### 1.1 Three Row Operations Keep the Solution Set

With $n$ equations in $m$ unknowns, write the **augmented matrix** with $n$ rows and $m + 1$ columns: the first $m$ columns are coefficients and the last is the right-hand side. Elimination uses only three **row operations**:

- swap two rows;
- multiply a row by a nonzero number;
- add a multiple of one row to another.

Each can be undone (swap back, multiply by the inverse, subtract back), and the undo is again a row operation. So a solution of the original system solves the new one and vice versa: **row operations do not change the solution set**. Columns cannot be moved freely, because each column is an unknown.

### 1.2 Eliminate Column by Column, Then Read the Result

Start from column 0 and keep a "current row" $r$ (initially 0):

1. among row $r$ and below, find a row with a nonzero entry in this column as the **pivot** and swap it to row $r$;
2. divide row $r$ by the pivot so the pivot becomes 1;
3. use row $r$ to clear this column in every other row;
4. record "the pivot of column $c$ is in row $r$", increase $r$, and move to the next column.

If step 1 finds no pivot, no row pins this unknown down: it is a **free variable** and can take any value. Then $r$ stays put and we go to the next column.

Clearing every other row in step 3 (above as well as below) is Gauss–Jordan elimination, and the result is the **reduced row echelon form**: each pivot column holds only the pivot's 1. No back-substitution is needed; the right-hand side of a pivot's row is the value of that unknown.

After elimination, every row from row $r$ down has all-zero coefficients. Read the result in this order:

1. some row has all-zero coefficients and a nonzero right-hand side, i.e. $0 = $ nonzero: **no solution**;
2. otherwise, with no free variable ($r = m$): a **unique solution**;
3. otherwise there are free variables and **the solution is not unique**: $p^{m - r}$ solutions mod $p$, $2^{m - r}$ mod 2, infinitely many over the reals.

**Check for no solution before free variables**: a system can have free variables and a contradictory row at the same time, and then the answer is no solution.

The animation below goes step by step through three systems: a unique solution, a free variable, and no solution. Each step marks the current column, the pivot and the row being cleared.

<iframe src="/maps/gauss-steps.en.html" title="Gaussian elimination, step by step" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:500px;overflow:hidden;margin:1.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/gauss-steps.en.html" target="_blank" rel="noopener">Open in a new window</a></p>

## 2. Reals: Pick the Pivot of Largest Absolute Value

### 2.1 A Tiny Pivot Magnifies the Error

Real numbers on a computer carry rounding error. With a tiny pivot, dividing by it in step 2 scales the row up enormously, and the errors of the other numbers grow with it.

Example: $10^{-20} x + y = 1$ and $x + y = 2$; the true solution is about $x = 1$, $y = 1$.

- With $10^{-20}$ from the first row as the pivot: subtract $10^{20}$ times the first row from the second, so $y$'s coefficient is $1 - 10^{20}$. A double has about 16 significant digits, so this becomes $-10^{20}$, and the right-hand side likewise becomes $-10^{20}$, giving $y = 1$. Back in the first row, $10^{-20} x = 1 - 1 = 0$, so $x = 0$: wrong.
- Swap first and use the 1 in the second row as the pivot: subtract $10^{-20}$ times the second row from the first; the coefficients and right-hand side barely change, giving $y = 1$, $x = 1$: right.

So over the reals, **pick the row with the largest absolute value in the column as the pivot** (partial pivoting), and test "is it zero" with $|x| < \varepsilon$, never `== 0`.

#### Cost

$O(n \cdot m \cdot w)$: $n$ rows, $m$ columns eliminated, $w$ columns per row ($w = m + 1$ with one right-hand side); $O(n^3)$ for a square system, and $n$ around 500 is the limit. Each column sweeps every row of the matrix.

#### Template (reals)

```cpp
#include <bits/stdc++.h>
using namespace std;

const double EPS = 1e-8;

// Gauss-Jordan over the reals: a has n rows; eliminate the first m columns, the columns after them (the RHS, possibly several) follow along
// returns -1: no solution; otherwise the rank r: r == m is a unique solution, r < m has free variables
// where[c]: the row holding the pivot of unknown c, -1 for a free variable; when solvable x_c = a[where[c]][m], free variables 0
int gauss(vector<vector<double>>& a, int m, vector<int>& where) {
    int n = a.size(), w = n ? a[0].size() : 0, r = 0;
    where.assign(m, -1);
    for (int c = 0; c < m && r < n; c++) {
        int p = r;
        for (int i = r; i < n; i++)
            if (fabs(a[i][c]) > fabs(a[p][c])) p = i;    // pivot with the largest absolute value
        if (fabs(a[p][c]) < EPS) continue;               // no pivot in this column: x_c is free, r stays
        swap(a[p], a[r]);
        for (int j = w - 1; j >= c; j--) a[r][j] /= a[r][c];
        for (int i = 0; i < n; i++)
            if (i != r && fabs(a[i][c]) > EPS)
                for (int j = w - 1; j >= c; j--) a[i][j] -= a[i][c] * a[r][j];
        where[c] = r++;
    }
    for (int i = r; i < n; i++)
        for (int j = m; j < w; j++)
            if (fabs(a[i][j]) > EPS) return -1;          // 0 = nonzero: check for no solution before free variables
    return r;
}
```

Check the return value for $-1$ (no solution) first, then whether the rank is $m$ (unique solution). This is the reading order of 1.2: a system can have free variables and a contradictory row at the same time, and then the answer is no solution.

### 2.2 Example: Luogu P2455, Telling No Solution from Infinitely Many

Problem ([Luogu P2455](https://www.luogu.com.cn/problem/P2455), SDOI2006): a linear system in $n \le 50$ unknowns with integer coefficients. Print each $x_i$ with 2 decimals if the solution is unique, $-1$ if there is no solution, and $0$ if there are infinitely many.

This is exactly the reading step of 1.2, and the trap is the order: when a column has no pivot, **do not declare "infinitely many" right away**. Finish the elimination and check for $0 = $ nonzero rows first. For example, $x + y = 1$ and $x + y = 2$: after column 1 the second row becomes $0 = 1$; column 2 has no pivot, so $y$ looks free, but the answer is $-1$.

```cpp
#include <bits/stdc++.h>
using namespace std;

// uses gauss from 2.1 (reals)

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<vector<double>> a(n, vector<double>(n + 1));   // augmented matrix, column n is the right-hand side
    for (auto& row : a)
        for (auto& v : row) cin >> v;

    vector<int> where;
    int r = gauss(a, n, where);
    if (r < 0) { cout << -1 << '\n'; return 0; }
    if (r < n) { cout << 0 << '\n'; return 0; }

    cout << fixed << setprecision(2);
    for (int c = 0; c < n; c++)
        cout << 'x' << c + 1 << '=' << (fabs(a[where[c]][n]) < 0.005 ? 0.0 : a[where[c]][n]) << '\n';
}
```

`a[i][c]` changes inside the inner loop, so `j` runs from right to left and column `c` is updated last; every earlier update still sees the old value. Values with tiny absolute value are printed as 0, avoiding `-0.00`. Cost $O(n^3)$ with $n \le 50$.

### 2.3 Example: Luogu P3232, an Expectation with Cycles

Problem ([Luogu P3232](https://www.luogu.com.cn/problem/P3232), HNOI2013): a connected undirected graph with $n \le 500$ vertices and $m \le 125000$ edges. Start at vertex 1; each step takes a uniformly random incident edge; stop at vertex $n$. The score is the sum of the numbers of the edges walked (counted each time). Number the edges $1 \dots m$ to minimise the expected score, and print it with 3 decimals.

**First, how many times each edge is walked in expectation.** There are too many edges for one equation each, so set up equations on vertices. Let $f_u$ be the expected number of visits to $u$ before reaching $n$ ($u \ne n$). Each visit to $v$ moves to a given neighbour with probability $1 / \deg v$, so

$$
f_u = [u = 1] + \sum_{v \sim u,\ v \ne n} \frac{f_v}{\deg v}.
$$

The first term is the start at vertex 1; when $v = n$ the walk has stopped and does not leave again. $u$ depends on its neighbours and they depend on $u$: there is a cycle, so the values cannot be pushed through in order, and the $n - 1$ equations have to be solved together.

Edge $(u, v)$ is walked $\dfrac{f_u}{\deg u} + \dfrac{f_v}{\deg v}$ times in expectation (leaving $u$ along it plus leaving $v$ along it), dropping the term whose endpoint is $n$.

**Then assign numbers.** The expected score is $\sum_e (\text{number}_e \times \text{expected count}_e)$. By the rearrangement inequality, pairing large with small minimises the sum, so the most-walked edge gets number 1, and so on.

```cpp
#include <bits/stdc++.h>
using namespace std;

// uses gauss from 2.1 (reals)

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, m;
    cin >> n >> m;
    vector<int> eu(m), ev(m), deg(n + 1, 0);
    vector<vector<int>> g(n + 1);
    for (int i = 0; i < m; i++) {
        cin >> eu[i] >> ev[i];
        deg[eu[i]]++, deg[ev[i]]++;
        g[eu[i]].push_back(ev[i]);
        g[ev[i]].push_back(eu[i]);
    }

    // unknowns f_1..f_{n-1}: expected visits to u before reaching n
    // f_u - sum_{v ~ u, v != n} f_v / deg_v = [u == 1]
    int k = n - 1;
    vector<vector<double>> a(k, vector<double>(k + 1, 0));
    for (int u = 1; u < n; u++) {
        a[u - 1][u - 1] += 1;
        for (int v : g[u])
            if (v != n) a[u - 1][v - 1] -= 1.0 / deg[v];
        a[u - 1][k] = (u == 1);
    }
    vector<int> where;
    gauss(a, k, where);                                    // unique solution: every column has a pivot, where[c] == c

    // expected uses of edge (u, v): chosen when leaving u, plus when leaving v; nothing leaves n
    vector<double> e(m);
    for (int i = 0; i < m; i++)
        e[i] = (eu[i] != n ? a[eu[i] - 1][k] / deg[eu[i]] : 0) + (ev[i] != n ? a[ev[i] - 1][k] / deg[ev[i]] : 0);
    sort(e.rbegin(), e.rend());                            // the more an edge is used, the smaller its number
    double ans = 0;
    for (int i = 0; i < m; i++) ans += e[i] * (i + 1);
    cout << fixed << setprecision(3) << ans << '\n';
}
```

Here the solution is always unique (the expected visit counts from vertex 1 are determined), so the code skips the checks for no solution and free variables. Cost: eliminating over $n - 1$ vertices is $O(n^3)$, about $1.25 \times 10^8$ at $n = 500$; sorting the $m$ edges adds $O(m \log m)$.

## 3. Modulo a Prime: Replace Division by an Inverse

### 3.1 Only Two Changes

Modulo a prime $p$ numbers are exact, with no rounding, and the elimination is the same apart from two changes:

- any **nonzero** entry can be the pivot; there is no need for the largest;
- dividing by the pivot becomes **multiplying by its inverse** (fast power $a^{p-2}$).

Every nonzero number has an inverse modulo a prime, so step 2 always works. When the modulus is not prime, a nonzero pivot may have no inverse, and the elimination has to run a Euclid-style subtraction between two rows instead; see practice problem 6.

#### Cost

$O(n \cdot m \cdot w + r \log p)$: the elimination is the same as over the reals, plus one inverse per pivot (fast power, $O(\log p)$), where $r$ is the rank. For a square system that is $O(n^3 + n \log p)$.

#### Template (mod a prime)

```cpp
#include <bits/stdc++.h>
using namespace std;
using ll = long long;

const ll P = 1e9 + 7;

ll qp(ll a, ll e) {
    ll r = 1;
    for (a %= P; e; e >>= 1, a = a * a % P)
        if (e & 1) r = r * a % P;
    return r;
}

// Gauss-Jordan mod a prime P: a has n rows; eliminate the first m columns, the columns after them (the RHS, possibly several) follow along
// return value and where as in the real version: -1 for no solution, otherwise the rank
int gauss(vector<vector<ll>>& a, int m, vector<int>& where) {
    int n = a.size(), w = n ? a[0].size() : 0, r = 0;
    where.assign(m, -1);
    for (int c = 0; c < m && r < n; c++) {
        int p = r;
        while (p < n && a[p][c] == 0) p++;               // mod p any nonzero entry can be the pivot
        if (p == n) continue;
        swap(a[p], a[r]);
        ll iv = qp(a[r][c], P - 2);                      // multiply by the inverse instead of dividing
        for (int j = c; j < w; j++) a[r][j] = a[r][j] * iv % P;
        for (int i = 0; i < n; i++)
            if (i != r && a[i][c]) {
                ll f = a[i][c];
                for (int j = c; j < w; j++) a[i][j] = (a[i][j] - f * a[r][j] % P + P) % P;
            }
        where[c] = r++;
    }
    for (int i = r; i < n; i++)
        for (int j = m; j < w; j++)
            if (a[i][j]) return -1;
    return r;
}
```

### 3.2 Example: Luogu P4783, Matrix Inverse

Problem ([Luogu P4783](https://www.luogu.com.cn/problem/P4783)): invert an $N \times N$ matrix modulo $10^9 + 7$ with $N \le 400$, or print `No Solution` if it is singular.

Put $A$ and the identity $I$ side by side as $[A \mid I]$ and eliminate the whole $n \times 2n$ matrix until the left half is $I$; the right half is then $A^{-1}$.

Why: each row operation is a left multiplication by an invertible matrix, so the whole sequence is a left multiplication by some matrix $E$. The left half going from $A$ to $I$ means $EA = I$, so $E = A^{-1}$; the right half goes from $I$ to $EI = E$, which is exactly $A^{-1}$. If some column of the left half has no pivot, $A$ does not have full rank and is not invertible.

```cpp
#include <bits/stdc++.h>
using namespace std;
// uses gauss from 3.1 (mod a prime; P and qp come with it)

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<vector<ll>> a(n, vector<ll>(2 * n, 0));       // [A | I]
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) cin >> a[i][j];
        a[i][n + i] = 1;
    }
    vector<int> where;
    if (gauss(a, n, where) != n) { cout << "No Solution\n"; return 0; }   // the left half cannot become I
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) cout << a[i][n + j] << " \n"[j == n - 1];
}
```

Eliminating the $n \times 2n$ matrix takes about $2 n^3$ multiplications, about $1.3 \times 10^8$ at $n = 400$.

### 3.3 Determinant: Clear Only Below, Multiply the Diagonal

How the three row operations affect the determinant: swapping two rows flips the sign; multiplying a row by $k$ multiplies it by $k$; adding a multiple of another row leaves it unchanged. So use only the third operation (plus swaps) to reach an upper triangle; the determinant is the product of the diagonal, with one sign flip per swap. No need to scale pivots to 1 or to clear rows above. The mod-prime code, the matrix-tree theorem and the LGV lemma are in [C0 section 4.6](/algo/c0-contest-math-overview/). Clearing only below takes about $n^3 / 3$ multiplications, plus the inverses, $O(n^3 + n \log p)$ in total.

## 4. Mod 2: Addition and Subtraction Are XOR

### 4.1 Store Each Row as a Bitset

GF(2) has only 0 and 1 with $1 + 1 = 0$, so addition and subtraction are both XOR; the pivot is always 1, so there is no division. Step 3, "subtract a multiple of row $r$ from row $i$", has only one case left: if row $i$ has a 1 in this column, XOR the whole of row $r$ into it.

#### Cost

$O(n \cdot m \cdot (m + 1) / 64)$, $O(n^3 / 64)$ for a square system, fast enough for $n$ up to 2000. With each row in a `bitset`, XOR-ing a whole row handles 64 bits at once, which saves a factor of 64 over the real version.

#### Template (mod 2)

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MV = 2000;                             // MV = max variables, the max number of unknowns; a bitset length must be fixed at compile time

// Gauss-Jordan mod 2: each row is a bitset, bits 0..m-1 are coefficients, bit m is the RHS
// return value and where as in the real version: -1 for no solution, otherwise the rank; when solvable x_c = a[where[c]][m]
int gauss(vector<bitset<MV + 1>>& a, int m, vector<int>& where) {
    int n = a.size(), r = 0;
    where.assign(m, -1);
    for (int c = 0; c < m && r < n; c++) {
        int p = r;
        while (p < n && !a[p][c]) p++;
        if (p == n) continue;
        swap(a[p], a[r]);
        for (int i = 0; i < n; i++)
            if (i != r && a[i][c]) a[i] ^= a[r];         // XOR the whole row, 64 bits at a time
        where[c] = r++;
    }
    for (int i = r; i < n; i++)
        if (a[i][m]) return -1;                          // 0 = 1
    return r;
}
```

### 4.2 Example: POJ 1222, Lights Out

Problem ([POJ 1222](http://poj.org/problem?id=1222) EXTENDED LIGHTS OUT): a 5 by 6 grid of lights, each with a switch; pressing it flips that light and its up, down, left and right neighbours. Given which lights are on, find which switches to press to turn everything off, printed as a 5 by 6 table of 0/1. A solution is guaranteed.

**Why this is a system mod 2.** The order of presses does not matter (flips commute) and pressing twice cancels, so each switch is just pressed or not: $x \in \{0, 1\}$. A light ends up off exactly when the number of times it is flipped has the same parity as its initial state:

$$
x_{\text{self}} \oplus x_{\text{up}} \oplus x_{\text{down}} \oplus x_{\text{left}} \oplus x_{\text{right}} = \text{initial state}.
$$

30 lights give 30 equations in 30 unknowns, one per switch. Column $c$ of the coefficient matrix $A$ is "which lights switch $c$ flips", row $r$ is "which switches flip light $r$", and both are plus shapes.

<a href="/images/algo/lights-out-matrix.en.svg" target="_blank" rel="noopener"><img src="/images/algo/lights-out-matrix.en.svg" alt="The Lights Out coefficient matrix: left, pressing switch (2,3) flips the 5 lights in a plus, which is column 9 of A; middle, light (1,1) is flipped by only 3 switches, giving x(1,1) ⊕ x(1,2) ⊕ x(2,1) = initial state, which is row 1 of A; right, the whole 30×30 A with rows as lights and columns as switches, its 1s along a few diagonals, with column 9 and row 1 marked." style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

```cpp
#include <bits/stdc++.h>
using namespace std;

// uses gauss from 4.1 (mod 2)

const int R = 5, C = 6, V = R * C;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int T;
    cin >> T;
    for (int t = 1; t <= T; t++) {
        // equation r: number of flips of light r ≡ its initial state (mod 2)
        // column c: which lights switch c flips; column V is the right-hand side
        vector<bitset<MV + 1>> a(V);
        for (int i = 0; i < R; i++)
            for (int j = 0; j < C; j++) {
                int s;
                cin >> s;
                a[i * C + j][V] = s;
            }
        int dx[5] = {0, 1, -1, 0, 0}, dy[5] = {0, 0, 0, 1, -1};
        for (int i = 0; i < R; i++)
            for (int j = 0; j < C; j++)
                for (int d = 0; d < 5; d++) {
                    int x = i + dx[d], y = j + dy[d];
                    if (x >= 0 && x < R && y >= 0 && y < C) a[x * C + y][i * C + j] = 1;
                }

        vector<int> where;
        gauss(a, V, where);                                // the statement guarantees a solution: full rank

        cout << "PUZZLE #" << t << '\n';
        for (int i = 0; i < R; i++)
            for (int j = 0; j < C; j++)
                cout << (where[i * C + j] == -1 ? 0 : (int)a[where[i * C + j]][V]) << " \n"[j == C - 1];
    }
}
```

The statement says every initial state can be turned off; for a square matrix that is the same as full rank, so the solution is unique and the code does not check for no solution. Other sizes (5 by 5, say) need not be full rank: with free variables there are $2^{\text{free}}$ solutions, and some initial states have none.

### 4.3 Example: CF 1344F Piet's Palette, Colors as Vectors

Problem ([CF 1344F](https://codeforces.com/problemset/problem/1344/F)): a palette has $n \le 1000$ cells, each red R, yellow Y, blue B or empty. Mixing a sequence: look at the first two colors; equal ones are both removed, different ones are replaced by the missing third color; one color left is the result, nothing left is white W. There are $k \le 1000$ operations in order: `mix` mixes some cells in a given order and reports the result; `RY`, `RB`, `YB` swap two colors in some cells. Find any initial palette, or report that none exists.

All the difficulty is in the model; once it is set up, it is the elimination of 4.1.

**Mixing is XOR.** Encode W, R, Y, B as the GF(2) vectors $(0, 0)$, $(1, 0)$, $(0, 1)$, $(1, 1)$. Against the rule: two equal colors XOR to $(0, 0)$, "both removed"; R XOR Y is $(1, 1)$, i.e. B, "replaced by the missing color", and the other two pairs work the same; an empty cell is $(0, 0)$ and has no effect. XOR is commutative and associative, so **the result of a mix is the XOR of the cells' color vectors**, independent of order; the given order is never used.

**A swap is multiplication by a matrix.** Swapping R and Y exchanges $(1, 0)$ and $(0, 1)$ and fixes $(1, 1)$; this is a linear map on GF(2)$^2$ with matrix $\begin{pmatrix}0&1\\1&0\end{pmatrix}$. Likewise RB is $\begin{pmatrix}1&0\\1&1\end{pmatrix}$ and YB is $\begin{pmatrix}1&1\\0&1\end{pmatrix}$.

**Keep a running matrix per cell.** Cell $j$'s initial color is an unknown vector $x_j$ and its current color is $T_j x_j$, with $T_j$ starting as the identity and left-multiplied by the swap matrix at each swap. A `mix` then tells us

$$
\bigoplus_{j \in S} T_j x_j = \text{result color},
$$

which splits into two equations mod 2, one per component. There are $2n \le 2000$ unknowns and $2k \le 2000$ equations, about $2000^3 / 64 \approx 1.3 \times 10^8$ bit operations with bitsets. Free variables can be set to 0; any solution is accepted.

```cpp
#include <bits/stdc++.h>
using namespace std;

// uses gauss from 4.1 (mod 2)

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, k;
    cin >> n >> k;
    // a color is a vector in GF(2)^2: W = 00, R = (1,0), Y = (0,1), B = (1,1); mixing is XOR
    // color of cell j now = T_j * x_j, x_j = (x_{2j}, x_{2j+1}) is the initial color, T_j starts as I
    vector<array<int, 4>> T(n, {1, 0, 0, 1});            // {t00, t01, t10, t11}
    vector<bitset<MV + 1>> eq;
    int V = 2 * n;
    for (int t = 0; t < k; t++) {
        string op;
        int m;
        cin >> op >> m;
        vector<int> id(m);
        for (auto& j : id) cin >> j, j--;
        if (op == "mix") {
            char ch;
            cin >> ch;
            bitset<MV + 1> e0, e1;               // one equation for each bit of the result color
            for (int j : id) {
                e0[2 * j] = T[j][0], e0[2 * j + 1] = T[j][1];
                e1[2 * j] = T[j][2], e1[2 * j + 1] = T[j][3];
            }
            e0[V] = (ch == 'R' || ch == 'B');
            e1[V] = (ch == 'Y' || ch == 'B');
            eq.push_back(e0), eq.push_back(e1);
        } else {
            // swapping two colors is an invertible linear map M on GF(2)^2, T_j <- M * T_j
            array<int, 4> M = op == "RY" ? array<int, 4>{0, 1, 1, 0}
                            : op == "RB" ? array<int, 4>{1, 0, 1, 1}
                                         : array<int, 4>{1, 1, 0, 1};
            for (int j : id) {
                auto& A = T[j];
                A = {(M[0] & A[0]) ^ (M[1] & A[2]), (M[0] & A[1]) ^ (M[1] & A[3]),
                     (M[2] & A[0]) ^ (M[3] & A[2]), (M[2] & A[1]) ^ (M[3] & A[3])};
            }
        }
    }

    vector<int> where;
    if (gauss(eq, V, where) < 0) { cout << "NO\n"; return 0; }

    string s(n, '.');
    for (int j = 0; j < n; j++) {
        int b0 = where[2 * j] == -1 ? 0 : eq[where[2 * j]][V];          // free variables set to 0
        int b1 = where[2 * j + 1] == -1 ? 0 : eq[where[2 * j + 1]][V];
        s[j] = ".RYB"[b0 | b1 << 1];
    }
    cout << "YES\n" << s << '\n';
}
```

### 4.4 Counting Solutions Is the XOR Basis Count

When the mod-2 system $Ax = b$ is solvable it has $2^{m - r}$ solutions: one particular solution XOR any element of the kernel (the "translate" of [L1 section 4.5](/algo/l1-linear-algebra/)). "Each value is reached by $2^{n-r}$ subsets" in [L3 section 3.2](/algo/l3-xor-basis/) is the same statement: take the $n$ numbers as the $n$ columns of $A$, the choice of numbers is $x$, and the numbers whose insertion fails are the free variables.

## 5. Incremental Elimination: One Equation at a Time

### 5.1 Eliminate Each Equation as It Arrives

Some problems feed equations one by one: you want the first moment all unknowns are determined, or you need to pick an independent set out of many candidate equations. Re-eliminating each time is too slow; instead keep a reduced row echelon form and eliminate each new equation as it comes:

1. use each existing row to clear the new equation's coefficient in that row's pivot column (the right-hand side changes along);
2. if all coefficients are now 0: a zero right-hand side means the equation follows from the existing ones, return 0; a nonzero one is a contradiction, return $-1$;
3. otherwise take its first nonzero column as a new pivot, use it to clear that column in the existing rows to keep "one 1 per pivot column", append it, and return 1.

#### Cost

| Operation | Cost |
| --- | --- |
| `eliminate`, `add`, `implied` | $O(r \cdot \text{MV} / 64)$ |
| `rank` | $O(1)$ |
| `solve` | $O(r + \text{MV} / 64)$ |
| `kernel` | $O((n - r)(r + \text{MV} / 64))$ |
| `merge` | $O(r' \cdot r \cdot \text{MV} / 64)$, $r'$ the other side's rank |

$r$ is the current rank, $n$ the number of unknowns, and $\text{MV} / 64$ the number of machine words in one bitset row, so XOR-ing a whole row costs that many integer XORs. Adding $k$ equations one after another costs $O(k \cdot r \cdot \text{MV} / 64)$ in total. Mod $p$ a row is a `vector<long long>`, XOR becomes subtracting a multiple, and step 3 first multiplies the new row by the inverse of its pivot; adding one equation costs $O(r \cdot n + \log p)$.

#### Template (mod 2)

Unknown $j$ is bit $j$ of the bitset; `MV` just has to exceed the number of unknowns. The right-hand side is an `int`, so several systems with the same coefficients can pack their right-hand sides bit by bit and be eliminated together; 5.2 does 30 at once.

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MV = 1024;                             // MV = max variables, the max number of unknowns; a bitset length must be fixed at compile time

// incremental Gauss (mod 2): add equations one at a time, always in RREF
struct IncGauss {
    int n;                                       // number of unknowns
    vector<bitset<MV>> row;
    vector<int> rhs, piv;                        // right-hand side and pivot column of each row; several RHS bits can be packed and XORed together
    bool bad = false;                            // a contradiction has appeared
    IncGauss(int n) : n(n) {}

    void eliminate(bitset<MV>& v, int& b) const {        // clear v on every pivot column using the rows; the RHS follows
        for (int i = 0; i < (int)row.size(); i++)
            if (v[piv[i]]) v ^= row[i], b ^= rhs[i];
    }
    int add(bitset<MV> v, int b) {               // 1: independent, rank grows; 0: implied by the rows; -1: contradiction
        eliminate(v, b);
        int p = v._Find_first();
        if (p >= n) { if (b) bad = true; return b ? -1 : 0; }
        for (int i = 0; i < (int)row.size(); i++)
            if (row[i][p]) row[i] ^= v, rhs[i] ^= b;  // clear the new pivot column in the old rows
        row.push_back(v), rhs.push_back(b), piv.push_back(p);
        return 1;
    }
    int rank() const { return row.size(); }
    int implied(bitset<MV> v) const {            // is the left side v implied? return its RHS if so, else -1
        int b = 0;
        eliminate(v, b);
        return v.none() ? b : -1;
    }
    bitset<MV> solve() const {                   // one solution when !bad: free variables 0, each pivot equals its RHS
        bitset<MV> x;
        for (int i = 0; i < (int)row.size(); i++) x[piv[i]] = rhs[i];
        return x;
    }
    vector<bitset<MV>> kernel() const {          // basis of the homogeneous solution space, n - rank() vectors
        vector<int> isp(n, -1);
        for (int i = 0; i < (int)row.size(); i++) isp[piv[i]] = i;
        vector<bitset<MV>> ks;
        for (int f = 0; f < n; f++) {
            if (isp[f] >= 0) continue;
            bitset<MV> x;
            x[f] = 1;                            // this free variable 1, the others 0
            for (int i = 0; i < (int)row.size(); i++)
                if (row[i][f]) x[piv[i]] = 1;
            ks.push_back(x);
        }
        return ks;
    }
    void merge(const IncGauss& o) {              // add the other side's equations one by one
        for (int i = 0; i < (int)o.row.size(); i++) add(o.row[i], o.rhs[i]);
    }
};
```

If `bad` is true the system has no solution. Otherwise it has $2^{n - r}$ solutions: `solve()` gives one, and XOR-ing in any subset of the vectors from `kernel()` gives the rest, the picture of [L1 section 4.5](/algo/l1-linear-algebra/): all solutions are the null space shifted by one solution.

The XOR basis is this template with at most 60 columns and no right-hand side; a side-by-side comparison, and the operations the XOR basis is usually used for such as the $k$-th smallest, are in the appendix of [L3 XOR Basis](/algo/l3-xor-basis/).

### 5.2 Example: 2024 ICPC Kunming E Extracting Weights, Picking Independent Queries

Problem ([2024 ICPC Kunming Regional E](https://codeforces.com/gym/105588/problem/E), interactive): a tree with $n \le 250$ vertices has unknown weights $w_i < 2^{30}$, with $w_1 = 0$ known. Given $k$, you may ask at most $n$ times for "the XOR of the weights of all vertices on the path from $u$ to $v$", answered only if the path has exactly $k$ edges. All questions are sent at once and answered together. First decide whether at most $n$ queries can determine every weight: if not, print `NO`; otherwise print `YES`, ask, and finally print $w_2, \dots, w_n$.

**Each query is an equation.** The unknowns are $w_1, \dots, w_n$. The answer to $(u, v)$ is the XOR of the weights on the path, so the coefficients are the 0/1 vector "is the vertex on the path". $w$ has 30 bits, but the systems for the 30 bits share the same coefficients, so the right-hand side is one `int` and XOR handles all 30 systems at once.

**Whether it is possible is a question of rank.** The equations of all paths with $k$ edges, plus $w_1 = 0$, must have rank $n$ to pin down every weight. Picking $n$ independent ones among them is exactly the template of 5.1: enumerate every pair at distance $k$ and keep it when it raises the rank.

**Insert $w_1 = 0$ first.** It is an equation too and costs no query. With it inserted first, the queries only need to fill the other $n - 1$ dimensions, so at most $n - 1$ are asked. If you pick $n - 1$ queries first and add it at the end, those $n - 1$ might already imply $w_1 = 0$; then it does not go in, the rank stops at $n - 1$, and you answer `NO` although a different or one more query would have been enough.

**Eliminate twice.** The first pass does not know the answers and picks queries by coefficients only; after the answers arrive, insert the same equations again with right-hand sides. In the full-rank reduced row echelon form each row has only its pivot's 1, so the right-hand side is that vertex's weight.

```cpp
#include <bits/stdc++.h>
using namespace std;

// uses IncGauss from 5.1

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, k;
    cin >> n >> k;
    vector<vector<int>> g(n + 1);
    for (int i = 1; i < n; i++) {
        int x, y;
        cin >> x >> y;
        g[x].push_back(y), g[y].push_back(x);
    }
    vector<int> par(n + 1, 0), dep(n + 1, 0), ord{1};
    for (int i = 0; i < (int)ord.size(); i++)
        for (int v : g[ord[i]])
            if (v != par[ord[i]]) par[v] = ord[i], dep[v] = dep[ord[i]] + 1, ord.push_back(v);

    auto path = [&](int u, int v) {             // vertices on the path u..v, bit i-1 is vertex i
        bitset<MV> s;
        while (u != v) {
            if (dep[u] < dep[v]) swap(u, v);
            s[u - 1] = 1, u = par[u];
        }
        s[u - 1] = 1;
        return s;
    };
    auto dist = [&](int u, int v) {
        int d = 0;
        while (u != v) {
            if (dep[u] < dep[v]) swap(u, v);
            u = par[u], d++;
        }
        return d;
    };

    IncGauss G(n);
    bitset<MV> e1;
    e1[0] = 1;
    G.add(e1, 0);                                // w_1 = 0 is an equation too, eliminated with the queries
    vector<pair<int, int>> ask;
    for (int u = 1; u <= n && G.rank() < n; u++)
        for (int v = u + 1; v <= n && G.rank() < n; v++)
            if (dist(u, v) == k && G.add(path(u, v), 0) == 1) ask.push_back({u, v});

    if (G.rank() < n) { cout << "NO" << endl; return 0; }
    cout << "YES" << endl;
    cout << "? " << ask.size();
    for (auto [u, v] : ask) cout << ' ' << u << ' ' << v;
    cout << endl;

    IncGauss S(n);                               // eliminate again with the answers
    S.add(e1, 0);
    for (auto [u, v] : ask) {
        int x;
        cin >> x;
        S.add(path(u, v), x);
    }
    vector<int> w(n);
    for (int i = 0; i < n; i++) w[S.piv[i]] = S.rhs[i];   // full-rank reduced form: each row is just its pivot
    cout << '!';
    for (int i = 1; i < n; i++) cout << ' ' << w[i];
    cout << endl;
}
```

Enumerating pairs is $O(n^2)$, each pair costs $O(n)$ for the distance and the path, and each incremental insertion $O(n \cdot n / 64)$, about $O(n^3)$ in total. Interactive problems need a flush after each output, hence `endl` in the code.

## Practice

Each problem lists the section it uses.

**Required**

1. [Luogu P3389 Gaussian elimination (template)](https://www.luogu.com.cn/problem/P3389): 2.2, unique solution only.
2. [Luogu P4035 Sphere generator](https://www.luogu.com.cn/problem/P4035): sphere equations are quadratic; subtract neighbouring pairs to cancel the quadratic terms and get a linear system. Section 2.
3. [Luogu P2973 Driving Out the Piggies](https://www.luogu.com.cn/problem/P2973): an expectation with cycles, equations on vertices as in 2.3.
4. [Luogu P2447 Alien centipedes](https://www.luogu.com.cn/problem/P2447): mod 2, and also print how many equations are needed before everything is determined. Sections 4 and 5.

**Optional**

5. [Luogu P3164 Harmonious matrix](https://www.luogu.com.cn/problem/P3164): the same model as Lights Out but a nonzero solution is required, so set free variables to 1. 4.2.
6. [Luogu P4111 Little Z's rooms](https://www.luogu.com.cn/problem/P4111): a determinant by the matrix-tree theorem modulo $10^9$, which is not prime, so there are no inverses; eliminate by Euclid-style subtraction between two rows. 3.1, 3.3.

## Connections to Other Posts

- [L1 Linear Algebra](/algo/l1-linear-algebra/): section 3 "finding a basis is elimination", section 6 the structure of solutions (image and kernel), section 4.4 mod-2 elimination and the XOR basis as rows and columns of one matrix.
- [L3 XOR Basis](/algo/l3-xor-basis/): insertion is the incremental Gauss of 5.1 with at most 60 columns (its appendix compares the two), and the count in 3.2 is 4.4.
- [C0 Contest Math Overview](/algo/c0-contest-math-overview/): 4.4 lists the three kinds of statements that turn into linear systems, and 4.6 has the determinant template and counting uses.
- The template collection [Matrix #2: Gaussian Elimination](/posts/matrix-2-gaussian-elimination/): full templates for solving, determinants, inverses and rank over the reals, mod $p$ and mod 2, and the incremental version mod $p$.
