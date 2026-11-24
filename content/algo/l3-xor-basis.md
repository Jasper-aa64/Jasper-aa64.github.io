---
title: "L3: XOR Basis"
date: 2026-11-02
slug: "l3-xor-basis"
aliases: ["/algo/l2-xor-basis/"]
description: "XOR is addition over GF(2), so all subset XORs form a linear space, and an XOR basis is a basis of it with at most 60 numbers: insertion by highest bit, 2^r values each reached by 2^(n-r) subsets, greedy maximum, k-th smallest after reduction; prefix XORs, weighted greedy, range queries that keep the rightmost number; maximum XOR path written from scratch; two recent contest problems: CCPC Final 2025 L counts distinct range spans, 2026 ICPC Online II A finds the smallest common space. With 8 practice problems."
weight: 17
math: true
toc: true
---
Given $n$ numbers, pick any subset and XOR it together: what is the largest result? With $n = 50$ there are $2^{50}$ subsets, too many to enumerate. But the subset XORs repeat a lot. With three numbers $a$, $b$, $a \oplus b$, the values you can reach are exactly the ones you reach with $a$ and $b$ alone; the third number is redundant. Remove redundant numbers one at a time and at most 60 remain (each number has 60 bits), yet not a single reachable value is lost. What remains is an **XOR basis** (线性基). To say precisely what "redundant" means, and why at most 60 remain, we put XOR into linear algebra.

## Complexity at a Glance

$B = 60$ is the number of bits (one `long long`), $n$ the number of values, $q$ the number of queries. In 7.1 $a_i < 2^{32}$, so $B$ is 32 there.

| Operation | Complexity | See |
| --- | --- | --- |
| Insert a number / test whether it is representable | $O(B)$ | 2.1, 2.2 |
| Insert all $n$ numbers | $O(nB)$ | 2.1 |
| Max / min XOR | $O(B)$ | 4.1 |
| Reduce, `reduce()` | $O(B^2)$ | 4.2 |
| $k$-th smallest | $O(B)$, after one `reduce()` | 4.3 |
| Rank of prefix XORs (CF 1101G) | $O(nB)$ | 5.1 |
| Weighted selection | sort $O(n \log n)$ + inserts $O(nB)$ | 5.2 |
| Prefix basis (CF 1100F) | insert and query both $O(B)$; offline sorting gives $O(q \log q + (n + q) B)$ in total | 5.3 |
| Merge two bases | $O(B^2)$; a range query on a segment tree merges $O(\log n)$ nodes, $O(B^2 \log n)$ | 5.4 |
| Maximum XOR path | $O((n + m) B)$, $m$ the number of edges | 6 |
| Spirited Away | $O(32^2 n)$ | 7.1 |
| All Closed ($m \le 20$ is the bit width) | at most $m$ rounds, each $O(m \sum \lvert S_i \rvert + 2^m)$ | 7.2 |

The table in the appendix also lists the cost of every template function, and the matching incremental Gauss version.

## 1. XOR Is Addition Mod 2

### 1.1 A Number Is a Vector over GF(2)

Write a number below $2^{60}$ as 60 binary digits, each 0 or 1, and it becomes a 60-dimensional vector. XOR of two numbers adds digit by digit mod 2: $1 \oplus 1 = 0$ is exactly $1 + 1 \equiv 0 \pmod 2$. The field with two elements 0 and 1, where addition and multiplication are taken mod 2, is written **GF(2)** (also $\mathbb{F}_2$), so **XOR is vector addition over GF(2)**.

Over GF(2) the coefficients are only 0 and 1, so a linear combination $x_1 a_1 + x_2 a_2 + \cdots + x_n a_n$ ($x_i \in \{0, 1\}$) means "XOR together the numbers with $x_i = 1$". A subset XOR and a linear combination are the same thing, so a few notions carry over from linear algebra directly:

- **Span**: the set of all subset XORs, written $\operatorname{span}(a_1, \dots, a_n)$.
- **Linear independence**: no nonempty subset XORs to 0. When a statement says "no nonempty subset has XOR 0", it is asking for linear independence.
- **Basis and rank**: a linearly independent set of numbers that can XOR to every value in the space is a basis of the space; its size is the dimension of the space, also called the **rank** of the original numbers, written $r$. A 60-dimensional space holds at most 60 linearly independent numbers, so $r \le 60$.

These notions are the same ones as over the reals; [L1 Linear Algebra](/algo/l1-linear-algebra/) sets up the model in ordinary linear algebra and shows why the same 0/1 vectors can have different ranks over the reals and over GF(2).

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

The animation below walks through insertion bit by bit. It starts with 6, 3, 5, 1: 5 is cleared to 0 and fails, and the other three each take a pivot bit. You can type your own numbers.

<iframe src="/maps/xor-basis-insert.en.html" title="XOR basis insertion, step by step" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:545px;overflow:hidden;margin:1.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/xor-basis-insert.en.html" target="_blank" rel="noopener">Open in a new window</a></p>

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

The figure below ties 4.2 and 4.3 together on a 4-bit example: the top shows `b` before and after reduction, the bottom shows the value chosen by each $k = 0, \dots, 7$.

<a href="/images/algo/xor-basis-rref-kth.en.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-rref-kth.en.svg" alt="Reduction and k-th smallest: on the left b[3]=1101, b[2]=0111, b[0]=0001, with extra 1s in pivot columns in red; after b[2]^=b[0], b[3]^=b[2], b[3]^=b[0] the right side is 1010, 0110, 0001 and pivot columns 3, 2, 0 each hold one 1. Below, k from 0 to 7 picks c0=b[0], c1=b[2], c2=b[3] by its bits, giving 0, 1, 6, 7, 10, 11, 12, 13: the value bits at the pivots equal the bits of k, so values increase with k." style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

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

### 5.3 Range Queries: The Prefix Basis, Each Pivot Bit Keeps the Rightmost Number

Example (CF 1100F): an array and many queries asking for the maximum subset XOR inside $[l, r]$. Rebuilding a basis per query costs $O(60 \cdot \text{length})$, too slow.

The technique is called the **prefix basis**: insert from left to right and keep a position `pos[i]` next to each `b[i]`. When inserting the $p$-th number, if the `b[i]` it meets has a position smaller than $p$, swap them: the newcomer stays in `b[i]` and the old number carries its position further down to the lower bits. The basis after inserting the $r$-th number answers every query with right end $r$: run the greedy using only the `b[i]` with `pos[i]` $\ge l$.

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

The figure below shows the basis after each insertion of the array $5, 6, 3, 4$, and the query $[3, 4]$ at right end 4:

<a href="/images/algo/xor-basis-prefix.en.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-prefix.en.svg" alt="Prefix XOR basis: array 101, 110, 011, 100. After a1: b[2]=101@1. After a2: 110@2 swaps out 101@1, which reduces to 011 and goes to b[1]. After a3: 011@3 swaps out 011@1, which reduces to 0 and is dropped. After a4: 100@4 takes b[2], 110@2 is pushed down, reduces to 001 and goes to b[0]. Query [3,4] uses only 100@4 and 011@3, max XOR 111=7." style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

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

## 7. Two Recent Contest Problems

### 7.1 CCPC Final 2025 L (Spirited Away): Counting Distinct Range Spans

Problem ([QOJ / Universal Cup 3727 L](https://contest.ucup.ac/contest/3727/problem/18012), 4 s): you are given a sequence of non-negative integers $a_1, \dots, a_n$. For a range $[l, r]$, XOR together any subset of $a_l, \dots, a_r$ (the empty subset gives 0); the set of all possible results is $B(l, r)$, the span of $a_l, \dots, a_r$. Over all $1 \le l \le r \le n$, how many distinct sets $B(l, r)$ are there?

**Input**: the first line holds $T$, the number of test cases. Each test case has $n$ ($1 \le n \le 10^5$) on one line and $n$ integers $a_i$ ($0 \le a_i < 2^{32}$) on the next. The sum of $n$ over all test cases is at most $10^5$.

**Output**: for each test case, one line with the number of distinct sets $B(l, r)$.

**Sample**

```text
Input
5
3
1 2 3
4
10 12 17 33
6
1 0 9 8 7 3
8
9012 91829 9819 78 237 862 7672 2
10
0 1 2 4 8 16 32 64 128 256

Output
4
10
12
36
46
```

In the first test case $a = (1, 2, 3)$: $B(1, 1) = \{0, 1\}$, $B(2, 2) = \{0, 2\}$, $B(3, 3) = \{0, 3\}$, and the other three ranges all give $\{0, 1, 2, 3\}$, so the answer is 4.

#### 7.1.1 Only $O(32 n)$ Ranges Are Really Different

There are $O(n^2)$ ranges, so first shrink that to something enumerable. Fix the right end $r$. As the left end $l$ moves left the space only grows, each change adds one dimension, so it changes at most 32 times. The change points are exactly the positions in the prefix basis of 5.3: sort the basis after inserting $a_r$ by `pos` from high to low as $v_1, \dots, v_k$, with positions $p_1 > p_2 > \cdots > p_k$, and set $p_{k+1} = 0$; then

$$
B(l, r) = \operatorname{span}(v_1, \dots, v_j), \qquad p_{j+1} < l \le p_j .
$$

This is the sentence of 5.3, "the part with position $\ge l$ spans exactly $a_l, \dots, a_r$", said another way. In addition, when $a_r = 0$, $l = r$ gives $\{0\}$ (then $p_1 < r$). **With the right end fixed, the left end passes at most 32 change points, so all ranges together produce only $O(32 n)$ spaces.**

#### 7.1.2 Two Spaces Are Equal Exactly When Their Reduced Bases Are

One space has many bases, so comparing bases directly does not work; we need a form determined by the space alone. The reduced basis is one. The highest bit of every nonzero element of the space is a pivot bit (same reason as the independence proof in 2.2: the highest bit of any combination is the highest pivot bit among the basis numbers used), so the set of pivot bits is determined by the space. Now take the basis number $c_p$ on pivot bit $p$: after reduction it is the element of the space whose pivot bits contain only bit $p$, and 4.3 says an element of the space is determined uniquely by its values on the pivot bits, so there is only one such element. Therefore **the reduced basis is determined by the space, and two spaces are equal exactly when their reduced bases are equal**. Hash the reduced basis into a 64-bit number and count the distinct hashes at the end.

#### 7.1.3 Keeping the Basis Reduced While Inserting

For each $r$, insert $v_1, v_2, \dots$ in that order into an empty basis and record the hash of the current space after each insertion. Calling `reduce()` from 4.2 after every insertion and hashing everything costs $O(32^2)$ each time, $O(32^3)$ per $r$, too slow. Instead keep the basis reduced during insertion: first clear all pivot bits of the new number $y$ with the existing basis, so the highest remaining bit $t$ of $y$ is a new pivot bit; then XOR $y$ into every existing basis number that has a 1 in bit $t$. Each insertion is then $O(32)$. The hash is the sum of the scrambled basis numbers, so changing one basis number subtracts the old term and adds the new one. In total $O(32^2 n)$, about $10^8$ simple operations for $n = 10^5$.

```cpp
#include <bits/stdc++.h>
using namespace std;
using u32 = uint32_t;
using u64 = uint64_t;

u64 mix(u64 x) {                          // splitmix64: scramble a number into 64 random-looking bits
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

int main() {
    int T;
    scanf("%d", &T);
    while (T--) {
        int n;
        scanf("%d", &n);
        u32 b[32] = {};                   // the prefix basis of 5.3
        int pos[32] = {};
        vector<u64> hs;                   // hash of the space for each (r, j)
        for (int r = 1; r <= n; r++) {
            u32 x;
            scanf("%u", &x);
            int p = r;
            for (int i = 31; i >= 0; i--) {
                if (!(x >> i & 1)) continue;
                if (!b[i]) { b[i] = x; pos[i] = p; break; }
                if (pos[i] < p) { swap(b[i], x); swap(pos[i], p); }
                x ^= b[i];
            }
            vector<pair<int, u32>> v;     // (position, basis number), by position from high to low
            for (int i = 0; i < 32; i++)
                if (b[i]) v.push_back({pos[i], b[i]});
            sort(v.rbegin(), v.rend());
            if (v.empty() || v[0].first < r) hs.push_back(0);   // a_r = 0: B(r, r) = {0}
            u32 c[32] = {};               // reduced basis, filled one number at a time
            u64 h = 0;
            for (auto [q, y] : v) {
                for (int i = 31; i >= 0; i--)
                    if ((y >> i & 1) && c[i]) y ^= c[i];          // clear the existing pivot bits of y
                int t = 31 - __builtin_clz(y);                    // the new pivot bit
                for (int i = t + 1; i < 32; i++)
                    if (c[i] >> t & 1) { h -= mix(c[i]); c[i] ^= y; h += mix(c[i]); }
                c[t] = y;
                h += mix(y);
                hs.push_back(h);          // B(l, r) for l in (next position, q]
            }
        }
        sort(hs.begin(), hs.end());
        printf("%d\n", (int)(unique(hs.begin(), hs.end()) - hs.begin()));
    }
}
```

Among $O(32 n)$ 64-bit hashes the chance of a collision is about $(3 \times 10^6)^2 / 2^{65}$, negligible.

### 7.2 2026 ICPC Online Contest II A (All Closed): What Every Solution Must Contain

Problem ([QOJ 4113](https://qoj.ac/contest/4113)): there are $n$ nonempty sets $S_1, \dots, S_n$ with elements in $[0, 2^m)$, $m \le 20$. One operation picks a number $x$ and adds it to all sets at once. Using as few operations as possible, make every set closed under XOR, and output the numbers added.

#### 7.2.1 From "Fewest Operations" to "Smallest Space"

Let the added numbers form a set $T$, so set $i$ ends up as $S_i \cup T$. A nonempty set closed under XOR contains $a \oplus a = 0$ and is closed under addition, so it is a space. Look at the part common to all final sets:

$$
K = \bigcap_{i} (S_i \cup T) = I \cup T, \qquad I = \bigcap_i S_i .
$$

An intersection of spaces is a space, so $K$ is a space containing $I$, and the final sets can be written as $S_i \cup K$. $T$ never needs numbers from $I$ (they are already in every set), so $|T| = |K| - |I|$, and **fewest operations means smallest $K$: find the smallest space $K \supseteq I$ such that every $S_i \cup K$ is a space; the answer is $K \setminus I$.**

#### 7.2.2 Every Added Number Is Forced

Start from $K = \operatorname{span}(I)$: every valid $K$ contains $I$ and is a space, so it contains $\operatorname{span}(I)$. If some $S_i \cup K$ is not closed, there is a number $x$ in $\operatorname{span}(S_i \cup K)$ that is in neither $S_i$ nor $K$. Take any valid solution $K^*$ containing the current $K$: $S_i \cup K^*$ is a space containing $S_i \cup K$, so it contains $x$; $x$ is not in $S_i$, so it must be in $K^*$. Hence every valid solution contains $x$; set $K \leftarrow \operatorname{span}(K \cup \{x\})$, which is still contained in every valid solution.

Each added $x$ raises the rank of $K$ by 1, so after at most $m$ steps every $S_i \cup K$ is closed. At that point $K$ itself is valid and is contained in every valid solution, so it is the smallest one, which also makes the answer unique. **To find the smallest valid solution, start from what every valid solution must contain and keep adding until it is valid; where you stop is the smallest solution.**

#### 7.2.3 Testing Closure by Counting Elements

$S_i \cup K \subseteq \operatorname{span}(S_i \cup K)$, and the latter has exactly $2^r$ elements (3.1), where $r$ is the rank of $S_i \cup K$. So

$$
S_i \cup K \text{ closed} \iff \lvert S_i \rvert + \lvert K \rvert - \lvert S_i \cap K \rvert = 2^r .
$$

When it is not closed, list $\operatorname{span}(S_i \cup K)$ (at most $2^m$ elements) and find a number in neither $S_i$ nor $K$: that is the $x$ to add. Checking all sets in one round costs $O(m \sum \lvert S_i \rvert)$, there are at most $m$ rounds, plus $O(2^m)$ for the listing in each round.

```cpp
#include <bits/stdc++.h>
using namespace std;

int n, m;

bool insert(vector<int>& b, int x) {      // insertion of 2.1, b has m slots
    for (int i = m - 1; i >= 0; i--) {
        if (!(x >> i & 1)) continue;
        if (!b[i]) { b[i] = x; return true; }
        x ^= b[i];
    }
    return false;
}

vector<int> expand(const vector<int>& b) { // list every element of span(b)
    vector<int> all = {0};
    for (int i = 0; i < m; i++)
        if (b[i]) {
            int sz = all.size();
            for (int j = 0; j < sz; j++) all.push_back(all[j] ^ b[i]);
        }
    return all;
}

int main() {
    scanf("%d %d", &n, &m);
    vector<vector<int>> s(n);
    vector<int> cnt(1 << m, 0);            // cnt[x]: how many sets contain x
    for (auto& si : s) {
        int k;
        scanf("%d", &k);
        si.resize(k);
        for (int& x : si) { scanf("%d", &x); cnt[x]++; }
    }
    vector<int> kb(m, 0);                  // basis of K, starting from span(I)
    for (int x = 0; x < (1 << m); x++)
        if (cnt[x] == n) insert(kb, x);
    vector<char> inK(1 << m), inS(1 << m);
    while (true) {
        vector<int> K = expand(kb);
        fill(inK.begin(), inK.end(), 0);
        for (int x : K) inK[x] = 1;
        int forced = -1;                   // a new number every valid solution must contain
        for (int i = 0; i < n && forced < 0; i++) {
            vector<int> b = kb;
            int common = 0;                // |S_i ∩ K|
            for (int x : s[i]) { insert(b, x); common += inK[x]; }
            int r = 0;
            for (int i2 = 0; i2 < m; i2++) r += b[i2] != 0;
            long long uni = (long long)s[i].size() + K.size() - common;   // |S_i ∪ K|
            if (uni == (1LL << r)) continue;                              // already closed
            for (int x : s[i]) inS[x] = 1;
            for (int x : expand(b))
                if (!inK[x] && !inS[x]) { forced = x; break; }
            for (int x : s[i]) inS[x] = 0;
        }
        if (forced < 0) break;
        insert(kb, forced);
    }
    vector<int> ans;                       // K \ I
    for (int x : expand(kb))
        if (cnt[x] < n) ans.push_back(x);
    sort(ans.begin(), ans.end());
    printf("%d\n", (int)ans.size());
    for (int x : ans) printf("%d ", x);
    printf("\n");
}
```

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

- The elimination of 2.3 is Gaussian elimination mod 2, and insertion is a special case of incremental elimination in [L2 Gaussian Elimination](/algo/l2-gaussian-elimination/) section 5.2. The number of solutions of an XOR system ($2^{\text{free variables}}$) is the same number as the $2^{n-r}$ of 3.2: the free variables are exactly the numbers whose insertion failed.
- The 0/1 trie of A6 also finds a maximum XOR, but of "$x$ with one number of the set": only a single number may be chosen; a basis answers "any subset". A statement that says "pick two numbers" wants a trie; one that says "pick some numbers" wants a basis.
- The greedy of 5.2 is greedy on a matroid, the same structure as Kruskal's minimum spanning tree (acyclic edge sets in place of independent sets).

## Appendix: XOR Basis and Incremental Gauss Templates

The two templates side by side. An XOR basis is incremental Gauss written for "at most 60 columns, no right-hand side", so almost every operation has a counterpart on both sides; right-hand sides, contradictions and solution vectors exist only in incremental Gauss. Both templates were checked against brute-force enumeration.

| Task | XOR basis `XorBasis` | Incremental Gauss `IncGauss` |
| --- | --- | --- |
| Add a number / an equation | `insert`, old rows untouched, $O(60)$ | `add`, clears old rows, always RREF, $O(r \cdot \text{MX} / 64)$ |
| Can it be represented | `contains`, $O(60)$ | `implied`, which also gives the implied RHS, $O(r \cdot \text{MX} / 64)$ |
| Rank | `r`, $O(1)$ | `rank()`, $O(1)$ |
| Reduced form | `reduce()`, called when needed, $O(60^2)$ | always reduced, no extra work |
| Max / min XOR | `max_xor` / `min_xor`, $O(60)$ | `max_xor` / `min_xor`, $O(r \cdot \text{MX} / 64)$ |
| $k$-th smallest / rank of a value | `kth` / `index`, $O(60)$, after one `reduce()` | `kth` $O(r \log r + r \cdot \text{MX} / 64)$ / `index` $O(r \log r)$, no reduction needed |
| Merge | `merge`, $O(60^2)$ | `merge`, adding the other side's $r'$ rows one by one, $O(r' \cdot r \cdot \text{MX} / 64)$ |
| Range queries | `PrefixBasis`: insert, `max_xor` and `at` are all $O(60)$ | `PrefixGauss`: `add`, `implied`, `max_xor` $O(n \cdot \text{MX} / 64)$, `bad` $O(1)$, `rank` $O(n)$, `at` $O(n \cdot r \cdot \text{MX} / 64)$ |
| Right-hand side and contradictions | none | `add` returns $-1$, `bad` remembers it |
| One solution / all solutions | none | `solve()` $O(r + \text{MX} / 64)$ / `kernel()` $O((n - r)(r + \text{MX} / 64))$ |
| Columns | at most 60 | at most `MX`, thousands are fine |

Here $r$ is the current rank and $n$ the number of unknowns; `MX / 64` is the number of machine words in one bitset row, so one bitset XOR costs that many integer XORs. The XOR basis's 60 is just "rank at most 60, one word per row", so both columns follow the same formula: with $\text{MX} = 64$, incremental Gauss's $O(r \cdot \text{MX}/64)$ is $O(r)$ with $r \le 60$.

### XOR Basis

```cpp
#include <bits/stdc++.h>
using namespace std;

// XOR basis: values below 2^60; b[i] is 0 or a number whose highest bit is exactly i
struct XorBasis {
    static const int B = 60;
    long long b[B] = {};
    int r = 0;                                   // rank; 2^r reachable values, each from 2^(n-r) subsets after n insertions

    bool insert(long long x) {                   // true if the rank grows; false means x was already reachable
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; r++; return true; }
            x ^= b[i];
        }
        return false;
    }
    bool contains(long long x) const {           // is x reachable
        for (int i = B - 1; i >= 0; i--)
            if (x >> i & 1) {
                if (!b[i]) return false;
                x ^= b[i];
            }
        return true;
    }
    long long max_xor(long long v = 0) const {   // max of v XOR any subset
        for (int i = B - 1; i >= 0; i--) v = max(v, v ^ b[i]);
        return v;
    }
    long long min_xor(long long v) const {       // min of v XOR any subset
        for (int i = B - 1; i >= 0; i--) v = min(v, v ^ b[i]);
        return v;
    }
    void reduce() {                              // reduce: each pivot bit stays only in its own number
        for (int i = 0; i < B; i++)
            for (int j = i - 1; j >= 0; j--)
                if (b[j] && (b[i] >> j & 1)) b[i] ^= b[j];
    }
    long long kth(unsigned long long k) const {  // reduce() first; k-th smallest (0-based, the 0th is 0), -1 if none
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;
    }
    unsigned long long index(long long x) const {  // reduce() first; rank of a reachable x among the values (0-based)
        unsigned long long k = 0;
        for (int i = 0, t = 0; i < B; i++)
            if (b[i]) { if (x >> i & 1) k |= 1ULL << t; t++; }
        return k;
    }
    void merge(const XorBasis& o) {              // absorb another basis, O(60^2); call reduce() again before kth
        for (int i = 0; i < B; i++)
            if (o.b[i]) insert(o.b[i]);
    }
};

// prefix basis (explained in 5.3): insert left to right, each pivot bit keeps the rightmost number
struct PrefixBasis {
    static const int B = 60;
    long long b[B] = {};
    int pos[B] = {};                             // position of b[i] (1-based)

    void insert(long long x, int p) {            // insert the p-th number
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; pos[i] = p; return; }
            if (pos[i] < p) { swap(b[i], x); swap(pos[i], p); }
            x ^= b[i];
        }
    }
    long long max_xor(int l) const {             // max XOR over [l, current right end]
        long long v = 0;
        for (int i = B - 1; i >= 0; i--)
            if (pos[i] >= l) v = max(v, v ^ b[i]);
        return v;
    }
    XorBasis at(int l) const {                   // a basis of [l, current right end]; all XorBasis operations apply
        XorBasis s;
        for (int i = 0; i < B; i++)
            if (b[i] && pos[i] >= l) s.b[i] = b[i], s.r++;
        return s;
    }
};
```

`kth` counts $k$ from 0 and includes 0; whether the statement's "$k$-th smallest" counts 0 depends on whether $r = n$, as at the end of 4.3.

### Incremental Gauss (mod 2)

The interface first; the implementations follow.

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MX = 1024;                             // max number of columns (unknowns)

// incremental Gauss (mod 2): add equations one at a time, always in RREF
struct IncGauss {
    int n;                                       // number of unknowns
    vector<bitset<MX>> row;
    vector<int> rhs, piv;                        // right-hand side and pivot column of each row; several RHS bits can be packed and XORed together
    bool bad = false;                            // a contradiction has appeared
    IncGauss(int n) : n(n) {}

    // solving equations
    void eliminate(bitset<MX>& v, int& b) const;   // clear v on every pivot column using the rows; the RHS follows
    int add(bitset<MX> v, int b);                // 1: independent, rank grows; 0: implied by the rows; -1: contradiction
    int rank() const { return row.size(); }
    int implied(bitset<MX> v) const;             // is the left side v implied? return its RHS if so, else -1
    bitset<MX> solve() const;                    // one solution when !bad: free variables 0, each pivot equals its RHS
    vector<bitset<MX>> kernel() const;           // basis of the homogeneous solution space, n - rank() vectors
    void merge(const IncGauss& o);               // add the other side's equations one by one

    // counterparts of the XOR basis operations: left sides only (row space), RHS ignored; column 0 is the most significant bit
    bitset<MX> max_xor(bitset<MX> v) const;      // max of v XOR any rows
    bitset<MX> min_xor(bitset<MX> v) const;      // min of v XOR any rows
    bitset<MX> kth(unsigned long long k) const;  // k-th smallest in the row space (0-based, the 0th is all zeros); needs k < 2^rank()
    unsigned long long index(const bitset<MX>& x) const;  // rank of x among the row space when x is in it (0-based)
    vector<int> low_to_high() const;             // row ids ordered by pivot from low bit to high bit (pivot column descending)
};

// prefix incremental Gauss (mod 2): equations come left to right, each pivot column keeps the rightmost one; the RHS is column n and is eliminated too
struct PrefixGauss {
    int n;
    vector<bitset<MX>> row;                      // row[c]: the equation whose first 1 is in column c; the row for c = n is 0 = 1
    vector<int> pos;                             // position of row[c] (1-based), 0 if empty
    PrefixGauss(int n) : n(n), row(n + 1), pos(n + 1, 0) {}

    void add(bitset<MX> v, int b, int p);        // add the p-th equation; needs MX > n
    bool bad(int l) const { return pos[n] >= l; }  // are equations l..current contradictory (l is 1-based)
    int rank(int l) const;                       // rank of equations l..current
    int implied(bitset<MX> v, int l) const;      // using only equations l..current: the implied RHS, or -1 if not implied
    bitset<MX> max_xor(bitset<MX> v, int l) const;  // max of v XOR left sides of equations l..current
    IncGauss at(int l) const;                    // equations l..current as an IncGauss
};
```

Unknown $j$ is bit $j$ of the bitset. When `bad` is true the system has no solution and `solve()` and `kernel()` mean nothing; otherwise there are $2^{n - \text{rank}}$ solutions, which is [L1 linear algebra](/algo/l1-linear-algebra/) section 4.5's picture: all solutions are the null space translated by one solution.

The functions that mirror the XOR basis look only at left sides and read each row as an $n$-bit number with **column 0 as the most significant bit**. The pivot is the first 1 in a row, so "earlier pivot, larger number" is the same as the basis's "higher top bit, larger number". To match integers, put bit $W - 1 - j$ of an integer $x$ into column $j$ ($W$ is the bit width). The rows are always in RREF, so `kth` needs no `reduce()` first.

`PrefixGauss` is the swap insertion of 5.3 with bitset rows and the first 1 as the pivot; the RHS is column $n$ and is eliminated too, so the row `0 = 1` keeps the rightmost position $q$, and equations $l$ through the current one contradict each other exactly when $l \le q$, which is all `bad(l)` checks. It keeps only an echelon form without clearing old rows, so `max_xor` scans the columns front to back greedily.

#### Implementation: Solving Equations

```cpp
void IncGauss::eliminate(bitset<MX>& v, int& b) const {
    for (int i = 0; i < (int)row.size(); i++)
        if (v[piv[i]]) v ^= row[i], b ^= rhs[i];
}

int IncGauss::add(bitset<MX> v, int b) {
    eliminate(v, b);
    int p = v._Find_first();
    if (p >= n) { if (b) bad = true; return b ? -1 : 0; }
    for (int i = 0; i < (int)row.size(); i++)
        if (row[i][p]) row[i] ^= v, rhs[i] ^= b;     // clear the new pivot column in the old rows
    row.push_back(v), rhs.push_back(b), piv.push_back(p);
    return 1;
}

int IncGauss::implied(bitset<MX> v) const {
    int b = 0;
    eliminate(v, b);
    return v.none() ? b : -1;
}

bitset<MX> IncGauss::solve() const {
    bitset<MX> x;
    for (int i = 0; i < (int)row.size(); i++) x[piv[i]] = rhs[i];
    return x;
}

vector<bitset<MX>> IncGauss::kernel() const {    // all solutions = solve() XOR any subset of these
    vector<int> isp(n, -1);
    for (int i = 0; i < (int)row.size(); i++) isp[piv[i]] = i;
    vector<bitset<MX>> ks;
    for (int f = 0; f < n; f++) {
        if (isp[f] >= 0) continue;
        bitset<MX> x;
        x[f] = 1;                                // this free variable 1, the others 0
        for (int i = 0; i < (int)row.size(); i++)
            if (row[i][f]) x[piv[i]] = 1;
        ks.push_back(x);
    }
    return ks;
}

void IncGauss::merge(const IncGauss& o) {
    for (int i = 0; i < (int)o.row.size(); i++) add(o.row[i], o.rhs[i]);
}
```

#### Implementation: Counterparts of the XOR Basis Operations

```cpp
// in RREF each pivot column is 1 only in its own row, so the result on a pivot column says whether that row was chosen,
// and two choices first differ on some pivot column: the greedy only decides 0 or 1 on each pivot column
bitset<MX> IncGauss::max_xor(bitset<MX> v) const {
    for (int i = 0; i < (int)row.size(); i++)
        if (!v[piv[i]]) v ^= row[i];
    return v;
}

bitset<MX> IncGauss::min_xor(bitset<MX> v) const {
    for (int i = 0; i < (int)row.size(); i++)
        if (v[piv[i]]) v ^= row[i];
    return v;
}

vector<int> IncGauss::low_to_high() const {
    vector<int> id(row.size());
    iota(id.begin(), id.end(), 0);
    sort(id.begin(), id.end(), [&](int a, int b) { return piv[a] > piv[b]; });
    return id;
}

bitset<MX> IncGauss::kth(unsigned long long k) const {   // bit t of k: whether to take the row of the t-th pivot counted from the low end
    bitset<MX> v;
    vector<int> id = low_to_high();
    for (int t = 0; t < (int)id.size() && t < 64; t++)
        if (k >> t & 1) v ^= row[id[t]];
    return v;
}

unsigned long long IncGauss::index(const bitset<MX>& x) const {
    unsigned long long k = 0;
    vector<int> id = low_to_high();
    for (int t = 0; t < (int)id.size() && t < 64; t++)
        if (x[piv[id[t]]]) k |= 1ULL << t;
    return k;
}
```

#### Implementation: Prefix Incremental Gauss

```cpp
void PrefixGauss::add(bitset<MX> v, int b, int p) {
    v[n] = b;
    while (v.any()) {
        int c = v._Find_first();
        if (!pos[c]) { row[c] = v; pos[c] = p; return; }
        if (pos[c] < p) { swap(row[c], v); swap(pos[c], p); }
        v ^= row[c];
    }
}

int PrefixGauss::rank(int l) const {
    int r = 0;
    for (int c = 0; c < n; c++) r += pos[c] >= l;
    return r;
}

int PrefixGauss::implied(bitset<MX> v, int l) const {
    v[n] = 0;
    for (int c = v._Find_first(); c < n; c = v._Find_next(c)) {
        if (pos[c] < l) return -1;
        v ^= row[c];
    }
    return v[n];
}

bitset<MX> PrefixGauss::max_xor(bitset<MX> v, int l) const {   // echelon form: row[c] only touches columns c and later, so greedy from the high end
    for (int c = 0; c < n; c++)
        if (pos[c] >= l && !v[c]) v ^= row[c];
    v[n] = 0;                                    // column n is the RHS, drop it
    return v;
}

IncGauss PrefixGauss::at(int l) const {
    IncGauss g(n);
    for (int c = 0; c <= n; c++)
        if (pos[c] >= l) {
            bitset<MX> w = row[c];
            int b = w[n];
            w[n] = 0;
            g.add(w, b);
        }
    return g;
}
```

**Which one: if the problem asks what XORs of subsets of some numbers can give, use the XOR basis; if it asks to solve equations, detect contradictions, or has more than 60 unknowns, use incremental Gauss.**
