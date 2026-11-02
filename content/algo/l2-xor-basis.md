---
title: "L2: XOR Basis"
date: 2026-11-02
slug: "l2-xor-basis"
description: "XOR is addition over GF(2), so all subset XORs form a linear space, and an XOR basis is a basis of it with at most 60 numbers: insertion by highest bit, 2^r values each reached by 2^(n-r) subsets, greedy maximum, k-th smallest after reduction; prefix XORs, weighted greedy, range queries that keep the rightmost number; maximum XOR path written from scratch. With 8 practice problems."
weight: 16
math: true
toc: true
---
Given $n$ numbers, pick any subset and XOR it together: what is the largest result? With $n = 50$ there are $2^{50}$ subsets, too many to enumerate. But the subset XORs repeat a lot. With three numbers $a$, $b$, $a \oplus b$, the values you can reach are exactly the ones you reach with $a$ and $b$ alone; the third number is redundant. Remove redundant numbers one at a time and at most 60 remain (each number has 60 bits), yet not a single reachable value is lost. What remains is an **XOR basis** (线性基). To say precisely what "redundant" means, and why at most 60 remain, we put XOR into linear algebra.

## 1. XOR Is Addition Mod 2

### 1.1 A Number Is a Vector over GF(2)

Write a number below $2^{60}$ as 60 binary digits, each 0 or 1, and it becomes a 60-dimensional vector. XOR of two numbers adds digit by digit mod 2: $1 \oplus 1 = 0$ is exactly $1 + 1 \equiv 0 \pmod 2$. The field with two elements 0 and 1, where addition and multiplication are taken mod 2, is written **GF(2)** (also $\mathbb{F}_2$), so **XOR is vector addition over GF(2)**.

Over GF(2) the coefficients are only 0 and 1, so a linear combination $x_1 a_1 + x_2 a_2 + \cdots + x_n a_n$ ($x_i \in \{0, 1\}$) means "XOR together the numbers with $x_i = 1$". A subset XOR and a linear combination are the same thing, so a few notions carry over from linear algebra directly:

- **Span**: the set of all subset XORs, written $\operatorname{span}(a_1, \dots, a_n)$.
- **Linear independence**: no nonempty subset XORs to 0. When a statement says "no nonempty subset has XOR 0", it is asking for linear independence.
- **Basis and rank**: a linearly independent set of numbers that can XOR to every value in the space is a basis of the space; its size is the dimension of the space, also called the **rank** of the original numbers, written $r$. A 60-dimensional space holds at most 60 linearly independent numbers, so $r \le 60$.

The "redundant" number from the opening is one that the others can XOR to; removing it leaves the span unchanged. When nothing more can be removed, the remaining numbers are linearly independent, i.e. a basis. **After switching to the basis, the reachable values are the same, while the count of numbers drops from $n$ to $r \le 60$**; every problem below is solved on those at most 60 numbers.

### 1.2 The Precondition: The Set Must Be Closed under XOR

Replacing the numbers by a basis only works when the problem wants all values reachable by "any subset". That set is closed under XOR: XOR two subset XORs together and you get the XOR of the symmetric difference of the two subsets, again a subset XOR. Once the problem restricts which subsets may be chosen, closure can break.

Take $a = (1, 2, 4)$ and forbid choosing two neighbours. The legal choices are nothing, any single number, or the first and the third, with XORs $0, 1, 2, 4, 5$; the maximum is 5. Insert these values into a basis and ask for the maximum, and you get $1 \oplus 2 \oplus 4 = 7$, which needs all three numbers and breaks the rule. The basis treated XORs between legal values as reachable: $1 \oplus 2 = 3$ corresponds to choosing the first and the second, which is itself illegal. **First make sure the wanted values form a set closed under XOR (any subset, one path plus any cycles, and so on), and only then use a basis; with a restriction on the choice, find a way to remove the restriction, and if you cannot, switch to search or DP.**

## 2. Insertion: Eliminating as You Insert

### 2.1 Stored by Highest Bit

The basis is an array `b[0..59]` with one rule: **`b[i]` is either 0 or a number whose highest bit is exactly bit $i$**. To insert $x$, scan from the high bits down: if bit $i$ is 1 and `b[i]` is empty, store $x$ in `b[i]`; if `b[i]` is taken, set $x \leftarrow x \oplus b_i$, which clears bit $i$, and continue with the lower bits.

```cpp
struct XorBasis {
    static const int B = 60;          // all values are below 2^60 (10^18 < 2^60)
    long long b[B] = {};              // b[i]: the number whose highest bit is exactly i, or 0
    int r = 0;                        // rank

    bool insert(long long x) {        // true if inserted (rank grows by 1)
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; r++; return true; }
            x ^= b[i];
        }
        return false;                 // x was reduced to 0: it is already reachable
    }

    bool contains(long long x) const {
        for (int i = B - 1; i >= 0; i--)
            if (x >> i & 1) {
                if (!b[i]) return false;
                x ^= b[i];
            }
        return true;
    }
};
```

One insertion does at most 60 XORs, so inserting all $n$ numbers costs $O(60 n)$.

### 2.2 A Failed Insertion Means the Number Is Reachable

During insertion $x$ is only ever XORed with numbers already in the basis, so at every moment $x_{\text{orig}} = x_{\text{now}} \oplus (\text{some } b_i)$. Insertion ends in one of two ways:

- $x$ is reduced to 0: $x_{\text{orig}}$ equals the XOR of some $b_i$, so it is already in the span; `insert` returns `false` and the basis is unchanged.
- $x$ stops at an empty slot `b[i]`: what is stored is $x_{\text{orig}}$ XOR some existing basis numbers, which spans the same space as storing $x_{\text{orig}}$ itself, and the rank grows by 1.

Why the stored numbers are linearly independent: their highest bits are pairwise different. Take any nonempty subset of them and XOR it. The number with the highest top bit has a 1 in that bit, and every other number in the subset has a 0 there (their top bits are lower), so the XOR has a 1 in that bit and cannot be 0.

So after inserting all $n$ numbers, the nonzero entries of `b` are a basis of $\operatorname{span}(a_1, \dots, a_n)$, and their count is the rank $r$. **Whether a number is reachable is decided by running the elimination of an insertion on it and checking whether 0 is left**; that is `contains`.

### 2.3 Relation to Gaussian Elimination

Stack the $n$ numbers into an $n \times 60$ 0/1 matrix, and insertion is Gaussian elimination mod 2: each `b[i]` is a row with its pivot in column $i$, and "clear bit $i$ of $x$ with `b[i]`" is a row operation. The difference is the order. Gaussian elimination takes the whole matrix and clears column by column; **a basis clears one row as it arrives, so it supports online insertion**. Sorted by $i$ from high to low, `b` is in row echelon form; the reduction in Section 4.2 turns it into reduced row echelon form.

## 3. Counting: $2^r$ Values, $2^{n-r}$ Subsets Each

### 3.1 There Are $2^r$ Distinct XOR Values

Each of the $r$ basis numbers is either chosen or not, giving $2^r$ XOR values, and they are pairwise distinct. If two different choices gave the same value, XORing the two results would give 0, and that is the XOR of the symmetric difference of the two choices; the symmetric difference is nonempty, contradicting independence. The basis also reaches every value in the space, so **any-subset XORs take exactly $2^r$ distinct values, including the 0 of the empty set**.

### 3.2 Every Value Is Reached by $2^{n-r}$ Subsets

$n$ numbers have $2^n$ subsets, spread over $2^r$ distinct values, so on average each value gets $2^{n-r}$ of them. In fact every value gets exactly that many.

The $r$ original numbers whose insertion succeeded form a basis (each cannot be expressed by the successes before it, so they are independent; every failed number can be expressed by them). To reach a value $v$: choose any subset of the $n - r$ failed numbers, with XOR $u$; the successful basis has exactly one choice reaching $v \oplus u$ (representation in a basis is unique, see 3.1), and together they give $v$. The failed numbers can be chosen freely and each choice has exactly one completion, $2^{n-r}$ in total.

In linear-algebra terms: write a choice as $x \in \{0, 1\}^n$; the XOR $f(x) = x_1 a_1 \oplus \cdots \oplus x_n a_n$ is a linear map whose image has dimension $r$, so by rank–nullity the kernel (choices reaching 0) has dimension $n - r$; the choices reaching $v$ are a shifted copy of the kernel, the same size.

**Every reachable value is reached by exactly $2^{n-r}$ subsets; the number of nonempty subsets with XOR 0 is $2^{n-r} - 1$.** When a problem asks about "the XORs of all $2^n$ subsets, sorted", first view it as $2^r$ distinct values, each repeated $2^{n-r}$ times.

## 4. Maximum and $k$-th Smallest

### 4.1 Maximum XOR: Greedy from the High Bits Down

Numbers are compared by their highest bit first, so to make the result as large as possible, make the highest bit 1 if possible. Let the current result be $v$ and go from $i = 59$ down: if bit $i$ of $v$ is 0 and `b[i]` is nonzero, XOR `b[i]` in. This step does not touch higher bits, because the highest bit of `b[i]` is $i$; and bit $i$ is never changed back later, because every later `b[j]` ($j < i$) has a 0 in bit $i$. **Taking the bits from high to low and turning each one into 1 whenever possible gives the maximum.** In code this is `v = max(v, v ^ b[i])`: when bit $i$ is 0 the XOR makes $v$ larger, when it is 1 the XOR makes it smaller.

The start need not be 0. For "the maximum of $s$ XOR any subset", start the greedy at $v = s$; the path problem in Section 6 needs this. The minimum is the mirror image: XOR whenever it makes $v$ smaller, which gives the minimum of $s$ XOR any subset.

```cpp
    long long max_xor(long long v = 0) const {   // max of v XOR any subset
        for (int i = B - 1; i >= 0; i--) v = max(v, v ^ b[i]);
        return v;
    }
    long long min_xor(long long v) const {       // min of v XOR any subset
        for (int i = B - 1; i >= 0; i--) v = min(v, v ^ b[i]);
        return v;
    }
```

These are member functions of `XorBasis`; when `b[i]` is 0 the XOR leaves $v$ unchanged, so no special case is needed. With $s = 0$ the minimum is always 0 (the empty set); for "the minimum over nonempty subsets", see the end of 4.3.

### 4.2 Reduction: Each Pivot Bit Lives in One Number Only

The maximum only cares about making each bit 1 when possible. The $k$-th smallest needs the full order of all $2^r$ values, and `b` as it stands does not show that order: ones that a higher basis number has in lower bits interfere with the comparison of those lower bits. So tidy it first. Call the highest bit $i$ of each nonzero `b[i]` a **pivot bit**. **Reduction** makes every pivot bit appear only in its own number: whenever `b[i]` has a 1 in a lower pivot bit $j$, XOR `b[j]` in to clear it.

```cpp
    void reduce() {                              // reduction: each pivot bit stays in its own number
        for (int i = 0; i < B; i++)
            for (int j = i - 1; j >= 0; j--)
                if (b[j] && (b[i] >> j & 1)) b[i] ^= b[j];
    }
```

`i` goes upward, so when `b[i]` is processed all lower `b[j]` are already reduced and contain no pivot bit other than bit $j$; XORing one in only clears bit $j$ of `b[i]` and cannot turn another pivot bit back to 1. XORing in basis numbers changes neither the span nor the highest bit of `b[i]`, so after reduction we still have a basis of the same space that still obeys the rule of 2.1. The cost is $O(60^2)$.

### 4.3 $k$-th Smallest: The Binary Digits of $k$ Are the Choice

After reduction, number the $r$ basis elements by pivot bit from low to high as $c_0, c_1, \dots, c_{r-1}$, and write $p_t$ for the pivot bit of $c_t$. For any choice, bit $p_t$ of the result is exactly "was $c_t$ chosen", because every other basis number has a 0 there.

Compare the results of two different choices. Let $t$ be the largest index on which they differ. Bits above $p_t$ are affected only by basis numbers with index above $t$ (those with index at most $t$ have top bit at most $p_t$), and both sides choose those identically, so all bits above $p_t$ agree; in bit $p_t$, the side that chose $c_t$ has a 1 and the other a 0. Therefore **writing a choice as the binary number $\sum_{t \text{ chosen}} 2^t$, the order of results matches the order of these binary numbers**: the $k$-th value from the smallest ($k$ counted from 0, value 0 being the 0-th) is obtained by choosing basis numbers according to the binary digits of $k$.

```cpp
    long long kth(unsigned long long k) const {  // call reduce() first; k from 0, the 0-th is 0
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;                       // k >= 2^r: no such value
    }
```

A statement's "$k$-th smallest" ($k$ counted from 1) usually comes in one of two flavours, and both differ only in how 0 and repeated values count:

- **Nonempty subsets, distinct values**: whether 0 is reachable by a nonempty subset depends on whether some insertion failed. When $r < n$ it is (choose a failed number together with the basis numbers that express it), so the distinct values of nonempty subsets are the same as with the empty set, and the answer is `kth(k - 1)`; when $r = n$ it is not, 0 must be skipped, and the answer is `kth(k)`. **Whether $r$ equals $n$ decides whether 0 counts, and this is where these problems most often go wrong.**
- **All $2^n$ subsets, with repetition**: every value repeats $2^{n-r}$ times (3.2), so the $k$-th is the distinct value with 0-based index $\lfloor (k - 1) / 2^{n-r} \rfloor$.

The minimum over nonempty subsets follows: 0 when $r < n$, otherwise `kth(1)`, the reduced basis number with the lowest pivot bit.

## 5. Common Variations in Problems

The first four sections all answer "given some numbers, choose any subset". Contest problems rarely ask that directly; more often they translate some other structure into this question, or add one more requirement on top of it.

### 5.1 XOR of Ranges: Switch to Prefix XORs

Example (CF 1101G): cut an array into as many segments as possible so that no choice of one or more segments has XOR 0.

Let the prefix XOR be $S_i = a_1 \oplus \cdots \oplus a_i$ with $S_0 = 0$. With cut points $0 = c_0 < c_1 < \cdots < c_k = n$, segment $j$ has XOR $S_{c_j} \oplus S_{c_{j-1}}$, and the condition is that these $k$ segment values are linearly independent. Segment values and prefix values express each other: $S_{c_j}$ is the XOR of the first $j$ segments. Two sets of $k$ numbers that express each other span the same space, and $k$ numbers are independent exactly when they span $k$ dimensions, so

$$
\text{segment values independent} \iff S_{c_1}, S_{c_2}, \dots, S_{c_k} \text{ independent}.
$$

The problem becomes: pick as many linearly independent numbers from $S_1, \dots, S_n$ as possible, and $S_n$ must be among them. If $S_n = 0$ there is no solution; otherwise $\{S_n\}$ alone is independent and extends to a basis of $S_1, \dots, S_n$, so the answer is the rank of these $n$ prefix XORs. **Write the XOR of a segment or range as the XOR of two prefix XORs, then look at the linear relations among the prefix XORs.**

### 5.2 Weighted Choice: Insert by Decreasing Weight

Each number carries a nonnegative weight, and we want a linearly independent set with maximum total weight. Sort by weight from high to low, insert in that order, and take every number whose insertion succeeds.

Why the greedy is right. Let the greedy picks, sorted by weight, be $g_1, \dots, g_r$ with nonincreasing weights; take any linearly independent set, also sorted, $o_1, \dots, o_m$. First, $m \le r$: the greedy picks are a basis of all the numbers, and no independent set exceeds the rank. Next we show $w(g_t) \ge w(o_t)$ for every $t$; summing gives optimality. Suppose $w(o_t) > w(g_t)$ for some $t$. $o_1, \dots, o_t$ are $t$ independent numbers, while $g_1, \dots, g_{t-1}$ span only $t - 1$ dimensions, so some $o_j$ ($j \le t$) cannot be expressed by $g_1, \dots, g_{t-1}$. Its weight is $w(o_j) \ge w(o_t) > w(g_t)$, so the greedy processed it before $g_t$; at that time all picks so far were among $g_1, \dots, g_{t-1}$ and could not express $o_j$, so $o_j$ should have been inserted and become some $g_s$ ($s < t$), contradicting that $g_1, \dots, g_{t-1}$ cannot express it.

```cpp
// items: (number, weight), weights nonnegative. Returns the max total weight of an independent set
long long max_weight(vector<pair<long long, long long>> items) {
    sort(items.begin(), items.end(),
         [](const auto& p, const auto& q) { return p.second > q.second; });
    XorBasis lb;
    long long sum = 0;
    for (auto [x, w] : items)
        if (lb.insert(x)) sum += w;
    return sum;
}
```

**Independent sets have the exchange property (a smaller one can always borrow a number from a larger one to grow), so inserting greedily by decreasing weight is optimal.** The next section reuses this with position as the weight.

### 5.3 Range Queries: Each Pivot Bit Keeps the Rightmost Number

Example (CF 1100F): an array and many queries asking for the maximum subset XOR inside $[l, r]$. Rebuilding a basis per query costs $O(60 \cdot \text{length})$, too slow.

Insert from left to right and keep a position `pos[i]` next to each `b[i]`. When inserting the $p$-th number, if the `b[i]` it meets has a position smaller than $p$, swap them: the newcomer stays in `b[i]` and the old number carries its position further down to the lower bits. The basis after inserting the $r$-th number answers every query with right end $r$: run the greedy using only the `b[i]` with `pos[i]` $\ge l$.

```cpp
struct PrefixBasis {
    static const int B = 60;
    long long b[B] = {};
    int pos[B] = {};                   // position (from 1) remembered for b[i]; further right is better

    void insert(long long x, int p) {
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; pos[i] = p; return; }
            if (pos[i] < p) { swap(b[i], x); swap(pos[i], p); }
            x ^= b[i];
        }
    }

    long long max_xor(int l) const {   // only basis numbers at positions >= l: range [l, current right end]
        long long v = 0;
        for (int i = B - 1; i >= 0; i--)
            if (pos[i] >= l) v = max(v, v ^ b[i]);
        return v;
    }
};
```

Why keeping only `pos[i]` $\ge l$ is right: this is the greedy of 5.2 with position as the weight. Insert by decreasing position, $a_r, a_{r-1}, \dots$; once $a_l$ is in, the basis can already express every number in $a_l, \dots, a_r$, and numbers further left only fill dimensions that are still empty, never pushing out what is there. So in the basis built greedily from right to left, the part with position $\ge l$ spans exactly $a_l, \dots, a_r$. The swapping insertion maintains this greedy result online: the newcomer has the largest position and should be chosen first, so whenever it meets an older number it pushes that one down, and the number pushed all the way to 0 is the leftmost of a linearly dependent group. **Each pivot bit keeps the rightmost number, and a query $[l, r]$ uses only the part with position $\ge l$.** Sort the queries by $r$ offline and keep a single basis; each query costs $O(60)$.

### 5.4 Merging Two Bases

To merge two bases, insert every nonzero number of one into the other, $O(60^2)$. "The basis of all numbers in a block" can sit on nodes of a segment tree or a binary-lifting table, and merging assembles the basis of any range or tree path. A basis does not support deletion; for problems with deletions, turn them offline into "the time interval during which each number exists" and use segment-tree divide and conquer over time.

## 6. Writing One from Scratch: Maximum XOR Path

Problem (Luogu P4151, WC2011): a connected undirected graph with $n \le 5 \times 10^4$ vertices and $m \le 10^5$ edges, weights up to $10^{18}$, possibly with multi-edges and self-loops. Find a path from 1 to $n$ whose edge-weight XOR is maximum; the path may revisit vertices and edges, and a repeated edge counts in the XOR as many times as it is used.

### 6.1 What Set Do the Path XORs Form

Before a basis can help, check whether the wanted set is "one value XOR a space". The path may go back and forth, and an edge used twice cancels out. Let $P$ be a fixed path from 1 to $n$ and $Q$ any other. Going out along $P$ and back along $Q$ is a closed walk $C$, so the XOR of $Q$ equals $P \oplus C$. Conversely, for any closed walk $C$, start at vertex 1, walk to $C$, go around it once, walk back to 1 the same way, then follow $P$; the out-and-back part cancels and the XOR is $P \oplus C$. So

$$
\{\text{XORs of all paths from 1 to } n\} = \{\, P \oplus C \mid C \text{ is the XOR of a closed walk} \,\},
$$

and closed-walk XORs are closed under XOR (two closed walks joined are again a closed walk, the connecting part cancels), so they form a space. **The answer is `max_xor(P)`; all that is left is a basis of the closed-walk space.**

### 6.2 A Basis of the Cycle Space: One Cycle per Edge

Run a BFS (or DFS) from 1 to get a spanning tree, and let $d_u$ be the XOR along tree edges from 1 to $u$. For each step $u \to v$ of a closed walk (weight $w$), write

$$
w = d_u \oplus d_v \oplus \underbrace{(d_u \oplus d_v \oplus w)}_{0 \text{ on tree edges}}.
$$

Expand every step of a closed walk this way and XOR them all: the $d$ terms chain end to end and cancel in pairs, leaving only the bracketed terms, which are nonzero only on non-tree edges. So the XOR of any closed walk is an XOR of some values $d_u \oplus d_v \oplus w$; conversely each $d_u \oplus d_v \oplus w$ is itself a closed walk (tree path from $u$ to $v$, then this edge back). **Inserting $d_u \oplus d_v \oplus w$ for every edge gives a basis of the cycle space**: tree edges insert 0, which does nothing, and self-loops and multi-edges need no special case.

The answer is the maximum XOR starting from $d_n$ ($d_n$ is the tree path $P$), in $O((n + m) \cdot 60)$.

### 6.3 The Full Program

```cpp
#include <bits/stdc++.h>
using namespace std;

struct XorBasis {
    static const int B = 60;
    long long b[B] = {};
    void insert(long long x) {
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; return; }
            x ^= b[i];
        }
    }
    long long max_xor(long long v) const {
        for (int i = B - 1; i >= 0; i--) v = max(v, v ^ b[i]);
        return v;
    }
};

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, m;
    cin >> n >> m;
    vector<int> eu(m), ev(m);
    vector<long long> ew(m);
    vector<vector<pair<int, long long>>> g(n + 1);
    for (int i = 0; i < m; i++) {
        cin >> eu[i] >> ev[i] >> ew[i];
        g[eu[i]].push_back({ev[i], ew[i]});
        g[ev[i]].push_back({eu[i], ew[i]});
    }
    vector<long long> d(n + 1, -1);       // XOR along the spanning tree from 1 to u; -1 means not reached yet
    d[1] = 0;
    queue<int> q;
    q.push(1);
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        for (auto [v, w] : g[u])
            if (d[v] < 0) { d[v] = d[u] ^ w; q.push(v); }
    }
    XorBasis lb;
    for (int i = 0; i < m; i++) lb.insert(d[eu[i]] ^ d[ev[i]] ^ ew[i]);   // tree edges insert 0
    cout << lb.max_xor(d[n]) << '\n';
}
```

Once it is written, compare it against brute force. With weights below 16, the state "which vertex, which current XOR" has only $16 n$ possibilities; BFS from $(1, 0)$ over all reachable states, and the XORs of states at vertex $n$ are exactly the XORs of all paths; take the maximum and compare. **For path problems that allow revisits, the state (vertex, XOR) is finite under small weights, which is a ready-made brute force.**

## Practice

Each problem lists the section it uses.

**Core**

1. [Luogu P3857 彩灯](https://www.luogu.com.cn/problem/P3857): 3.1.
2. [Luogu P4570 元素](https://www.luogu.com.cn/problem/P4570): 5.2.
3. [LOJ 114 k 大异或和](https://loj.ac/p/114): 4.3; watch whether 0 counts.
4. [Luogu P4869 albus就是要第一个出场](https://www.luogu.com.cn/problem/P4869): rank of a given value, 4.3 in reverse, times the repetition count of 3.2.
5. [CF 845G Shortest Path Problem?](https://codeforces.com/problemset/problem/845/G): Section 6, asking for the minimum.
6. [CF 1100F Ivan and Burgers](https://codeforces.com/problemset/problem/1100/F): 5.3.

**Optional**

7. [CF 959F Mahmoud and Ehab and yet another xor task](https://codeforces.com/problemset/problem/959/F): the number of subsets of the first $l$ numbers with XOR $x$, 3.2 plus offline processing.
8. [Luogu P3292 幸运数字](https://www.luogu.com.cn/problem/P3292): maximum XOR on a tree path, 5.4 plus binary lifting.

## Connections to Other Boxes on the Map

- The elimination of 2.3 is Gaussian elimination mod 2. When Gaussian elimination comes later, the number of solutions of an XOR system ($2^{\text{free variables}}$) is the same number as the $2^{n-r}$ of 3.2: the free variables are exactly the numbers whose insertion failed.
- The 0/1 trie of A6 also finds a maximum XOR, but of "$x$ with one number of the set": only a single number may be chosen; a basis answers "any subset". A statement that says "pick two numbers" wants a trie; one that says "pick some numbers" wants a basis.
- The greedy of 5.2 is greedy on a matroid, the same structure as Kruskal's minimum spanning tree (acyclic edge sets in place of independent sets).
