---
title: "L3: XOR Basis"
date: 2026-11-02
slug: "l3-xor-basis"
aliases: ["/algo/l2-xor-basis/"]
description: "XOR is addition over GF(2), so all subset XORs form a linear space, and an XOR basis is a basis of it with at most 60 numbers: insertion by highest bit, 2^r values each reached by 2^(n-r) subsets, greedy maximum, k-th smallest after reduction; prefix XORs, weighted greedy, range queries that keep the rightmost number; the maximum XOR path as a worked example; two recent contest problems: CCPC Final 2025 L counts distinct range spans, 2026 ICPC Online II A finds the smallest common space. With 8 practice problems."
weight: 17
math: true
toc: true
---
Given $n$ numbers, pick any subset and XOR it together: what is the largest result?

- **There are too many subsets to enumerate**: with $n = 50$ there are $2^{50}$.
- **The subset XORs repeat a lot**: $a$, $b$, $a \oplus b$ reach exactly the values $a$ and $b$ alone reach, so the third number is redundant.
- **Dropping redundant numbers leaves at most 60**: each number has 60 bits, the remaining numbers reach every value the originals did, and this set is an **XOR basis**. Saying what "redundant" means and why at most 60 remain takes linear algebra.

<style>.chroma .line.hl{background:rgba(56,139,253,.15)}</style>

## 1. What an XOR Basis Is

### 1.1 A Number Is a Vector over GF(2)

**Read a number as a 0/1 vector: XOR is vector addition and a subset XOR is a linear combination.**

1. **XOR is vector addition mod 2**
   - **A number is a 60-dimensional 0/1 vector**: write a number below $2^{60}$ in 60 binary digits, one coordinate per bit.
   - **XOR adds bit by bit mod 2**: $1 \oplus 1 = 0$ is exactly $1 + 1 \equiv 0 \pmod 2$. The field with only 0 and 1 and arithmetic mod 2 is **GF(2)** (also $\mathbb{F}_2$).
2. **A subset XOR is a linear combination with coefficients 0 or 1**
   - **$x_1 a_1 + \cdots + x_n a_n$ ($x_i \in \{0, 1\}$) is the XOR of the numbers with $x_i = 1$**: so the notions of linear algebra carry over directly.
     - **Span**: the set of all subset XORs, written $\operatorname{span}(a_1, \dots, a_n)$.
     - **Linear independence**: no nonempty subset XORs to 0. A statement saying "no nonempty subset has XOR 0" means exactly this.
     - **Basis and rank**: an independent set that reaches every value of the space is a basis; its size is the rank $r$, and $r \le 60$ in a 60-dimensional space.
   - **The same notions over the reals are in L1**: [L1 Linear Algebra](/algo/l1-linear-algebra/) covers the general model and why the same 0/1 vectors can have different ranks over the reals and over GF(2).
3. **The XOR basis is what remains after dropping redundant numbers**
   - **"Redundant" means reachable from the others**: dropping it keeps the span; when nothing more can be dropped, the rest is independent, a basis.
   - **With the basis, $n$ numbers shrink to $r \le 60$**: the reachable values stay the same, and every later question works on these at most 60 numbers.

### 1.2 Stored by Highest Bit: Insertion Eliminates as It Goes

**`b[i]` only holds a number whose highest bit is $i$; insertion goes from high bits down, clearing the 1s of $x$ with the basis, stores $x$ at the first empty slot, and a result of 0 means $x$ was already reachable.**

1. **How it is stored and inserted**
   - **`b[i]` is either 0 or a number whose highest bit is exactly $i$**: 60 slots in all.
   - **Inserting $x$ scans from bit 59 down**: if bit $i$ is 1 and `b[i]` is empty, store $x$ in `b[i]`; if `b[i]` is occupied, set $x \leftarrow x \oplus b_i$ to clear that bit and keep going lower.
   - **Example**: the animation below inserts 6, 3, 5, 1 bit by bit. 5 is cleared to 0 and fails; the other three each take a slot. You can try your own numbers.

<iframe src="/maps/xor-basis-insert.en.html" title="XOR basis insertion, step by step" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:545px;overflow:hidden;margin:1.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/xor-basis-insert.en.html" target="_blank" rel="noopener">Open in a new window</a></p>

2. **A failed insertion means the number is reachable**
   - **Every step XORs in a basis number**: so $x_{\text{orig}} = x_{\text{now}} \oplus (\text{some } b_i)$ at all times. Ending at 0 means $x_{\text{orig}}$ is an XOR of basis numbers and the basis stays the same; stopping at an empty slot stores a number with the same span contribution as $x_{\text{orig}}$, and the rank grows by 1.
   - **This is `contains`**: to test whether a number is reachable, run the same elimination on it and see whether 0 remains.
3. **The stored numbers are always independent**
   - **Their highest bits are pairwise different**: in any nonempty subset, the number with the highest top bit has a 1 there and the others have 0, so the XOR cannot be 0. After inserting, the nonzero entries of `b` are a basis, and their count is the rank $r$.
4. **Insertion is Gaussian elimination mod 2, one row at a time**
   - **So an XOR basis can insert online**: write the $n$ numbers as an $n \times 60$ 0/1 matrix; `b[i]` is the row with pivot in column $i$, and "clear bit $i$ with `b[i]`" is a row operation. Gaussian elimination takes the whole matrix and sweeps column by column; the XOR basis eliminates each number as it arrives.
   - **`b` is in row echelon form**: ordered by decreasing $i$ it is row echelon form, and the reduction of 1.4 turns it into reduced row echelon form.

### 1.3 Counting: $2^r$ Values, $2^{n-r}$ Subsets Each

**$n$ numbers have $2^n$ subsets; their XORs take only $2^r$ distinct values, and every value is reached by exactly $2^{n-r}$ subsets.**

1. **Walk through $a = (6, 3, 5)$ first**
   - **The rank after insertion is 2**: in binary `110`, `011`, `101`. 6 goes into `b[2]`, 3 into `b[1]`; 5 XORs with 6 to get `011`, then with 3 to get 0, so its insertion fails. So $r = 2$ and $n - r = 1$.
   - **The 8 subsets give only 4 values**: grouped by XOR as follows.
     - **XOR 0**: $\{\}$, $\{6, 3, 5\}$.
     - **XOR 3**: $\{3\}$, $\{6, 5\}$.
     - **XOR 5**: $\{5\}$, $\{6, 3\}$.
     - **XOR 6**: $\{6\}$, $\{3, 5\}$.
   - **Every value gets exactly 2 subsets**: 4 values is $2^r$, 2 each is $2^{n-r}$, and no value gets more than another.
2. **Why there are exactly $2^r$ distinct values**
   - **Each choice from the basis gives a different value**: each of the $r$ basis numbers is chosen or not, $2^r$ choices. If two choices gave the same value, XORing them would make a nonempty subset reach 0, contradicting independence. The basis also reaches every value in the space, so there are exactly $2^r$.
   - **Example**: the basis is 6 and 3, and its four choices give 0, 6, 3, 5.
3. **Why every value gets exactly $2^{n-r}$ subsets**
   - **The failed numbers are chosen freely, and the basis completes the rest in one way**: to reach $v$, the $n - r$ numbers whose insertion failed can be chosen any way, $2^{n-r}$ ways; after each, the basis has exactly one choice that makes up the rest, because representation in a basis is unique. So every $v$ is reached by $2^{n-r}$ subsets, whatever $v$ is.
   - **Example**: the failed number is 5. To reach 6: without 5, take 6, giving $\{6\}$; with 5, 3 is still missing, so take 3, giving $\{3, 5\}$.
4. **How problems use this result**
   - **Counting subsets with XOR $t$**: $2^{n-r}$ if $t$ is reachable (`contains(t)`), otherwise 0. Code in 2.2.
   - **Counting nonempty subsets with XOR 0**: 0 is always reachable, by $2^{n-r}$ subsets; removing the empty set leaves $2^{n-r} - 1$.
   - **Sorting the XORs of all $2^n$ subsets**: with repeats, view them as $2^r$ distinct values, each repeated $2^{n-r}$ times in a row. See the end of 2.5.

### 1.4 Reduction: Each Pivot Bit in One Number, and Values Sort Like the Choice in Binary

> The essence of reduction: it rewrites the basis into the standard form unique to its space, so the $k$-th smallest reads straight off the binary digits and two spaces can be compared by comparing their bases.

1. **Why reduce**
   - **The $k$-th smallest needs the order of all $2^r$ values, and the raw `b` does not show it**: 1s that high basis numbers carry in lower bits disturb the comparison of the lower bits.
2. **What reduction does**
   - **Each pivot bit appears only in its own number**: the highest bit $i$ of a nonzero `b[i]` is its **pivot bit**. If `b[i]` has a 1 at a lower pivot bit $j$, XOR in `b[j]` to clear it. Code in 2.4.
3. **After reduction, values sort like the choice written in binary**
   - **The bits of the result at the pivot positions are the choice itself**: number the basis by pivot from low to high as $c_0, \dots, c_{r-1}$, with $c_t$'s pivot at $p_t$. Every other basis number has 0 at bit $p_t$, so bit $p_t$ of the result says whether $c_t$ was chosen.
   - **Comparing two choices depends only on the highest index where they differ**: call it $t$. Bits above $p_t$ depend only on indices above $t$, chosen the same on both sides; at bit $p_t$ the side that chose $c_t$ has a 1. So writing a choice as the binary number $\sum_{t \text{ chosen}} 2^t$, results sort the same way: the $k$-th smallest (0-based) chooses basis numbers by the binary digits of $k$.
   - **Example**: the figure below is a 4-bit example; the top shows `b` before and after reduction, the bottom the value chosen by each $k = 0, \dots, 7$.

<a href="/images/algo/xor-basis-rref-kth.en.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-rref-kth.en.svg" alt="Reduction and k-th smallest: on the left b[3]=1101, b[2]=0111, b[0]=0001, with extra 1s in pivot columns in red; after b[2]^=b[0], b[3]^=b[2], b[3]^=b[0] the right side is 1010, 0110, 0001 and pivot columns 3, 2, 0 each hold one 1. Below, k from 0 to 7 picks c0=b[0], c1=b[2], c2=b[3] by its bits, giving 0, 1, 6, 7, 10, 11, 12, 13: the value bits at the pivots equal the bits of k, so values increase with k." style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

4. **The reduced basis is determined by the space alone**
   - **Two spaces are equal exactly when their reduced bases are equal**: the proof and its use are in point 2 of the idea in 5.1.

### 1.5 The Precondition: The Set Must Be Closed under XOR

**An XOR basis answers "all values reachable by any subset"; to use it, the set the problem asks about must be closed under XOR.**

1. **XORs of arbitrary subsets are closed under XOR**
   - **XORing two subset XORs gives the XOR of their symmetric difference**: still a subset XOR, so the basis can stand in for the original numbers.
2. **A restriction on which subsets are allowed often breaks closure**
   - **Example**: $a = (1, 2, 4)$, no two adjacent numbers may both be chosen. The allowed XORs are $0, 1, 2, 4, 5$, so the maximum is 5; inserting into a basis and taking the maximum gives $1 \oplus 2 \oplus 4 = 7$, which needs all three numbers and breaks the rule. The mistake is counting XORs of allowed values as reachable.
   - **Check closure first, then use a basis**: any subset, or one path plus any cycles, is fine; with a restriction, first try to remove it, and otherwise switch to search or DP.

## 2. What an XOR Basis Can Do

**An XOR basis answers five kinds of questions about "XOR any subset": whether a value is reachable, how many, maximum and minimum, ranking, and merging.** Below, $n$ is the number of inserted values and $r$ the rank.

1. **Whether a number is reachable**
   - **Run the elimination of insertion on it; it is reachable when 0 remains**: `contains`, $O(60)$. Insertion is also $O(60)$, and inserting all $n$ numbers is $O(60 n)$. See 2.1.
2. **Counting**
   - **Only the rank is needed**: there are $2^r$ distinct values (including 0); subsets with XOR $t$ number $2^{n-r}$ if $t$ is reachable, else 0; nonempty subsets with XOR 0 number $2^{n-r} - 1$. See 2.2.
3. **Maximum and minimum of $s$ XOR any subset**
   - **Greedy from the high bits down**: whenever a bit can become 1, XOR in the basis number for it (`max_xor`); the minimum is the reverse (`min_xor`). Both $O(60)$. See 2.3.
4. **The $k$-th smallest, or the rank of a value**
   - **Reduce, then choose basis numbers by the binary digits of $k$**: call `reduce()` once after inserting, $O(60^2)$; or keep the basis reduced while inserting with `insert_reduced`, $O(60)$ each. Then `kth` and `index` cost $O(60)$ each. See 2.4 and 2.5.
5. **Merging two bases**
   - **Insert the numbers of one into the other**: `merge`, $O(60^2)$. Kept on the nodes of a segment tree or a binary-lifting table, this assembles the basis of any range or tree path. See 2.6.

Three variations, segment XORs, weights, and only numbers inside a range, are in section 3. The template with every function together is in the appendix.

### 2.1 Insert and Test Whether a Value Is Reachable

**Insertion and the test both sweep from high bits down; why it works is in 1.2.**

#### Cost

`insert` and `contains` are both $O(60)$: going down from bit 59, each bit does at most one XOR. Inserting all $n$ numbers costs $O(60 n)$.

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

- **`insert` returns whether it succeeded**: success means the rank grew by 1; `false` means $x$ was already reachable and the basis is unchanged.
- **`contains` runs the same elimination without storing**: hitting an empty slot it needs means the number cannot be cleared, so it returns `false`.

### 2.2 Counting

**The number of values depends only on the rank; counting subsets needs a reachability test first. Why: see 1.3.**

#### Cost

The number of values and the number of zero subsets are $O(1)$, using only the rank; the number of subsets with XOR $t$ needs `contains(t)` first, $O(60)$.

```cpp
// after inserting n numbers. n - r can be large; when the answer is taken modulo something, replace 1LL << with fast power
long long kinds(const XorBasis& lb) { return 1LL << lb.r; }               // distinct XOR values, 0 included
long long ways(const XorBasis& lb, int n, long long t) {                  // subsets with XOR t, the empty set included
    return lb.contains(t) ? 1LL << (n - lb.r) : 0;
}
```

- **`kinds` is $2^r$**: including the 0 of the empty set.
- **`ways` first checks whether $t$ is reachable**: if so the answer is $2^{n-r}$, otherwise 0. Nonempty subsets with XOR 0 are `ways(lb, n, 0) - 1`, removing the empty set.
- **Take the modulus when $n - r$ is large**: when the answer is modulo something, replace `1LL <<` with fast power.

### 2.3 Maximum XOR: Greedy from the High Bits Down

**Going from high bits down, XOR in the basis number whenever that bit can become 1; the result is the maximum.**

1. **Why the greedy works**
   - **Comparison starts at the high bits, and no step disturbs the bits already fixed**: with the current result $v$, going down from $i = 59$, if bit $i$ of $v$ is 0 and `b[i]` is nonzero, XOR in `b[i]`. Its highest bit is $i$, so higher bits are untouched; the later `b[j]` ($j < i$) all have 0 at bit $i$, so this bit is never changed back.
   - **In code this is `v = max(v, v ^ b[i])`**: when bit $i$ is 0 the XOR makes $v$ larger, when it is 1 smaller.
2. **The starting value and the minimum**
   - **The start need not be 0**: "the maximum of $s$ XOR any subset" starts the greedy from $v = s$, which the path problem of section 4 needs.
   - **The minimum is the reverse**: XOR whenever it makes $v$ smaller.

#### Cost

`max_xor` and `min_xor` are both $O(60)$, one look per bit.

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

- **Both are member functions of `XorBasis`**: when `b[i]` is 0 the XOR leaves $v$ unchanged, so no special case is needed.
- **With $s = 0$ the minimum is always 0**: that comes from the empty set; for the minimum over nonempty subsets, see the end of 2.5.

### 2.4 Reduction

**From low bits to high, use the lower pivots to clear each number's 1s at the other pivot bits; what it is for is in 1.4. The basis can also stay reduced during insertion, so it never needs fixing afterwards.**

#### Cost

`reduce()` is $O(60^2)$: two nested loops of at most 60 each. `insert_reduced` costs $O(60)$ per number, the same order as `insert`.

```cpp
    void reduce() {                              // reduction: each pivot bit stays in its own number
        for (int i = 0; i < B; i++)
            for (int j = i - 1; j >= 0; j--)
                if (b[j] && (b[i] >> j & 1)) b[i] ^= b[j];
    }
```

- **`i` goes upward**: when `b[i]` is processed, every lower `b[j]` is already reduced and has no pivot bit other than bit $j$, so XORing it in only clears bit $j$ of `b[i]` and never turns another pivot bit back to 1.
- **The result is still a basis of the same space**: XORing in basis numbers keeps the span and the highest bit of `b[i]`, so the rule of 1.2 still holds.

To stay reduced during insertion, `insert` needs two extra steps:

```cpp
    bool insert_reduced(long long x) {           // basis must be reduced before; stays reduced; true if inserted
        for (int i = B - 1; i >= 0; i--)
            if ((x >> i & 1) && b[i]) x ^= b[i]; // clear every existing pivot bit of x, all the way down to bit 0
        if (!x) return false;                    // reduced to 0: already reachable
        int t = 63 - __builtin_clzll(x);         // the highest remaining bit is the new pivot
        for (int i = t + 1; i < B; i++)
            if (b[i] >> t & 1) b[i] ^= x;        // clear bit t in the higher basis numbers
        b[t] = x;
        r++;
        return true;
    }
```

- **Step one eliminates $x$ all the way down**: `insert` stops at the first empty slot, so $x$ may still have 1s at lower pivot bits; here elimination runs to bit 0. The basis is reduced, so XORing `b[i]` flips only bit $i$ among the pivot bits; afterwards $x$ is 0 at every pivot bit, and its highest remaining bit $t$ is a new pivot.
- **Step two clears bit $t$ in the old basis**: each higher basis number with a 1 at bit $t$ gets $x$ XORed in. $x$ is 0 at the other pivot bits, so none of them turns back to 1; lower basis numbers have their highest bit below $t$, so bit $t$ is already 0.
- **The basis must be reduced beforehand**: insert only with `insert_reduced`, or after some plain `insert` calls run `reduce()` once and continue. It is incremental Gauss's `add` (appendix) written for an XOR basis.
- **Need the reduced basis only once at the end: `insert` plus one `reduce()`; need it after every insertion: `insert_reduced`**: in 5.1, for example, the reduced basis is hashed after every insertion; a `reduce()` each time costs $O(60^2)$, `insert_reduced` only $O(60)$.

### 2.5 The $k$-th Smallest and the Rank of a Value

**The subsets of the original array XOR to $2^r$ distinct values (including 0 from the empty set). Sort them: after reduction, the $k$-th ($k$ from 0) is obtained by choosing basis numbers by the binary digits of $k$; conversely, reading a value's bits at the pivot positions gives its rank. Why: see 1.4.**

#### Cost

`kth` and `index` are both $O(60)$; the `reduce()` before them is needed only once, $O(60^2)$, and not at all if every insertion used `insert_reduced`.

```cpp
    long long kth(unsigned long long k) const {  // basis must be reduced; k from 0, the 0-th is 0
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;                       // k >= 2^r: no such value
    }
    unsigned long long index(long long x) const {  // basis must be reduced; rank of a reachable x among the values (0-based)
        unsigned long long k = 0;
        for (int i = 0, t = 0; i < B; i++)
            if (b[i]) { if (x >> i & 1) k |= 1ULL << t; t++; }
        return k;
    }
```

- **`kth` counts $k$ from 0, and the 0-th value is 0**: when $k \ge 2^r$ there is none and it returns $-1$.
- **`index` is `kth` backwards**: for a reachable value, its bits at the pivot positions, read together, are its 0-based rank.

When a statement asks for the "$k$-th smallest", first decide what it ranks: distinct values, or the XORs of all subsets (a value reached by several subsets is listed that many times). The two give different answers.

1. **`kth` ranks distinct values**
   - **`kth` counts choices from the basis, not subsets of the original array, so repeats never arise**: the $2^r$ choices from the basis match the $2^r$ distinct values one to one (1.3), so each value has one choice and is ranked once; the numbers whose insertion failed are never chosen, so the repeats they cause never appear.
   - **Example**: $a = \{6, 3, 5\}$, the basis is 6 and 3, $r = 2$. The 8 subsets XOR to 0, 6, 3, 5, 5, 3, 6, 0; the distinct values in order are 0, 3, 5, 6, which are `kth(0)` to `kth(3)`.
2. **The problem wants distinct values: use `kth` directly; only whether 0 counts differs**
   - **With $k$ from 1 and nonempty subsets only, whether $r = n$ decides whether 0 counts**: when $r < n$ some insertion failed, and that number together with the basis numbers expressing it XORs to 0, so 0 counts and the answer is `kth(k - 1)`; when $r = n$ only the empty set gives 0, so skip it and answer `kth(k)`. This is the most common mistake in these problems.
   - **Example**: in $\{6, 3, 5\}$, $r = 2 < 3$ and $6 \oplus 3 \oplus 5 = 0$, so the 1st smallest is `kth(0)` = 0 and the 2nd is `kth(1)` = 3; for $\{6, 3\}$, $r = n = 2$, only the empty set gives 0, so the 1st smallest is `kth(1)` = 3.
3. **The problem keeps repeats: each value is listed $2^{n-r}$ times in a row**
   - **Sorted, the XORs of all $2^n$ subsets are the $2^r$ distinct values, each repeated $2^{n-r}$ times (1.3)**: the $k$-th ($k$ from 1) falls in run $\lfloor (k - 1) / 2^{n-r} \rfloor$ counting from 0, so the answer is `kth((k - 1) >> (n - r))`. Without the empty set, the missing entry is one 0 at the very front, so use $k + 1$ in place of $k$.
   - **Example**: $\{6, 3, 5\}$ sorted is 0, 0, 3, 3, 5, 5, 6, 6, each value $2^{3-2} = 2$ times; the 5th is `kth(4 >> 1)` = `kth(2)` = 5.
4. **The minimum over nonempty subsets**
   - **It is 0 when $r < n$, otherwise `kth(1)`**: the reduced basis number with the lowest pivot bit.

### 2.6 Merging Two Bases

**Insert the nonzero numbers of one basis into the other one by one to get the basis of both sets together.**

#### Cost

`merge` is $O(60^2)$: the other basis has at most 60 nonzero numbers, each inserted in $O(60)$.

```cpp
    void merge(const XorBasis& o) {              // absorb another basis, O(60^2); call reduce() again before kth
        for (int i = 0; i < B; i++)
            if (o.b[i]) insert(o.b[i]);
    }
```

- **On the nodes of a segment tree or a binary-lifting table, this assembles the basis of any range or tree path**: a range query on a segment tree merges $O(\log n)$ nodes, $O(60^2 \log n)$.
- **An XOR basis does not support deletion**: for problems with deletions, go offline to "the time interval each number exists" and use segment-tree divide and conquer.

## 3. Three Common Variations

**Section 2 answers "given some numbers, choose any subset". Contest problems often change one thing: the numbers to insert must be computed first, each number carries a weight, or only numbers inside a range may be used. Each subsection below covers one.**

1. **The numbers inserted are not the originals but segment XORs (3.1)**
   - **Switch to prefix XORs and insert those**: a segment's XOR is the XOR of two prefix XORs, so "these segments are independent" is the same as "the matching prefix XORs are independent".
   - **Example**: CF 1101G, cut the array into as many segments as possible so that no nonempty choice of segments XORs to 0.
2. **Each number has a weight; choose an independent set with the largest total weight (3.2)**
   - **Insert by decreasing weight and take the ones that go in**: the same greedy as Kruskal for minimum spanning trees.
   - **Example**: Luogu P4570 Elements, each ore has a number and a magic value; the chosen numbers must not XOR to 0, and the total magic is maximized.
3. **Only numbers inside $[l, r]$ may be used, over many queries (3.3)**
   - **Each pivot bit keeps the rightmost number, and a query uses only basis numbers at positions $\ge l$**: this is the greedy of 3.2 with position as the weight, called the prefix basis.
   - **Example**: CF 1100F, many queries for the maximum subset XOR inside a range.

### 3.1 The Numbers in the Basis Are Segment XORs: CF 1101G

[CF 1101G (Zero XOR Subset)-less](https://codeforces.com/problemset/problem/1101/G), time limit 2 s

1. **Statement**

   Given an array $a_1, \dots, a_n$, cut it into as many segments as possible: each element lies in exactly one segment, each segment has at least one element, and there is no nonempty set of segments whose numbers all XOR to 0. Print the maximum number of segments, or $-1$ if no valid division exists.

   - **Input**: the first line holds $n$ ($1 \le n \le 2 \cdot 10^5$); the second holds $n$ integers $a_i$ ($0 \le a_i \le 10^9$).
   - **Output**: the maximum number of segments, or $-1$.

   **Sample 1 input**

   ```text
   4
   5 5 7 2
   ```

   **Sample 1 output**

   ```text
   2
   ```

   **Sample 2 input**

   ```text
   3
   1 2 3
   ```

   **Sample 2 output**

   ```text
   -1
   ```

   **Sample 3 input**

   ```text
   3
   3 1 10
   ```

   **Sample 3 output**

   ```text
   3
   ```

   The statement's note: sample 1 can be cut as $[5, 5, 7], [2]$; no cut into 3 segments works, for example in $[5], [5, 7], [2]$ the segments $[5, 7]$ and $[2]$ XOR to 0. Sample 2 has no valid division. In sample 3 every number is its own segment.
2. **Idea**
   1. **A segment's XOR is the XOR of two prefix XORs**: let $S_i = a_1 \oplus \cdots \oplus a_i$, $S_0 = 0$, and the cut points be $0 = c_0 < c_1 < \cdots < c_k = n$; the $j$-th segment XORs to $S_{c_j} \oplus S_{c_{j-1}}$. "No set of segments XORs to 0" means these $k$ segment values are independent.
   2. **The segment values are independent exactly when the prefix XORs at the cuts, $S_{c_1}, \dots, S_{c_k}$, are**: a segment value is the XOR of two neighbouring $S$, and conversely $S_{c_j}$ is the XOR of the first $j$ segments. Each group of $k$ numbers expresses the other, so they span the same space, and one group is independent exactly when the other is. The problem becomes: choose as many independent numbers as possible from $S_1, \dots, S_n$, and $S_n$ must be chosen (the last cut is always $n$).
   3. **The answer is the rank of $S_1, \dots, S_n$, with no solution when $S_n = 0$**: if $S_n = 0$ it alone XORs to 0, so print $-1$. Otherwise insert $S_n$ first and then the other prefix XORs, giving a basis that contains $S_n$, of size equal to the rank $r$; the $k$ values $S$ of any valid division are independent, so $k \le r$. So insert every prefix XOR into the basis, and the answer is the rank.

      For instance, in sample 1 the prefix XORs are $5, 0, 7, 5$ with rank 2; choosing $S_3 = 7$ and $S_4 = 5$ gives the division $[5, 5, 7], [2]$.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // the appendix's XorBasis: only the members used here, copy the implementation from the appendix
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]: the number whose highest bit is exactly i, 0 if none
       int r = 0;                              // rank
       bool insert(long long x);               // true if inserted (rank grows by 1)
   };

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int n;
       cin >> n;
       XorBasis lb;
       long long s = 0;                         // prefix XOR S_i
       for (int i = 0; i < n; i++) {
           long long a;
           cin >> a;
           s ^= a;
           lb.insert(s);
       }
       cout << (s == 0 ? -1 : lb.r) << '\n';    // S_n = 0: no solution; otherwise the rank of the prefix XORs
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: $n$ insertions, $O(60 n)$.
   - **Check $S_n = 0$ first**: however large the rank of the other prefix XORs, $S_n = 0$ means no solution, because all segments together XOR to 0.

### 3.2 Each Number Has a Weight, Insert by Decreasing Weight: Luogu P4570

[Luogu P4570 [BJWC2011] 元素 (Element)](https://www.luogu.com.cn/problem/P4570), time limit 1 s

1. **Statement**

   There are $N$ kinds of ore; kind $i$ has an element number $\mathit{Number}_i$ and a magic value $\mathit{Magic}_i$. Choose some ores to forge a staff, at most one piece of each kind. If the chosen ores contain a nonempty subset whose element numbers XOR to 0, "magic cancellation" happens and no staff can be made. The staff's magic is the sum of the chosen ores' magic values; find the largest magic a staff can have.

   - **Input**: the first line holds $N$ ($1 \le N \le 1000$); each of the next $N$ lines holds two positive integers $\mathit{Number}_i$ and $\mathit{Magic}_i$ ($1 \le \mathit{Number}_i \le 10^{18}$, $1 \le \mathit{Magic}_i \le 10^4$).
   - **Output**: one integer, the largest magic.

   **Sample 1 input**

   ```text
   3
   1 10
   2 20
   3 30
   ```

   **Sample 1 output**

   ```text
   50
   ```

   The statement's note: using all three kinds gives $1 \oplus 2 \oplus 3 = 0$, so the magic cancels; the best choice is the last two kinds, $20 + 30 = 50$.
2. **Idea**
   1. **No cancellation means the chosen element numbers are independent**: "no nonempty subset XORs to 0" is exactly the definition of independence (1.1). The task becomes: pick an independent set from $N$ numbers with the largest total weight (magic value).
   2. **Insert by decreasing weight and keep each number whose insertion succeeds**: a successful insertion means the number is independent of those already kept, so the kept numbers are always an independent set. In the sample, insert 3, 2, 1 in the order of magic 30, 20, 10: 3 and 2 succeed, 1 = 3 ⊕ 2 fails, and the answer is $30 + 20 = 50$.
   3. **The greedy's $t$-th number is never lighter than the $t$-th of any independent set**: sort both by decreasing weight, the greedy as $g_1, \dots, g_r$ and any independent set as $o_1, \dots, o_m$, $m \le r$. Suppose $w(o_t) > w(g_t)$: $o_1, \dots, o_t$ are independent and span $t$ dimensions while $g_1, \dots, g_{t-1}$ span only $t - 1$, so some $o_j$ ($j \le t$) is not expressible by $g_1, \dots, g_{t-1}$. It is heavier than $g_t$, so the greedy handled it before inserting $g_t$, when the basis held only $g$'s heavier than it; its insertion should have succeeded, a contradiction. Never lighter term by term means the largest total. Section 3.3 reuses this with position as the weight.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // the appendix's XorBasis: only the members used here, copy the implementation from the appendix
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]: the number whose highest bit is exactly i, 0 if none
       int r = 0;                              // rank
       bool insert(long long x);               // true if inserted (rank grows by 1)
   };

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int n;
       cin >> n;
       vector<pair<long long, long long>> items(n);   // (element number, magic value)
       for (auto& [x, w] : items) cin >> x >> w;
       sort(items.begin(), items.end(),
            [](const auto& p, const auto& q) { return p.second > q.second; });
       XorBasis lb;
       long long sum = 0;
       for (auto [x, w] : items)
           if (lb.insert(x)) sum += w;                // success: independent of those kept
       cout << sum << '\n';
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: sorting is $O(N \log N)$ and the inserts $O(60 N)$.
   - **Sort by weight before inserting**: inserting in input order puts 1 and 2 in first, 3 then fails, and the sample gives only $10 + 20 = 30$.
   - **Element numbers reach $10^{18}$**: use `long long`; $10^{18} < 2^{60}$, so the appendix's 60-bit basis suffices.

### 3.3 Only Numbers Inside a Range May Be Used: The Prefix Basis, Each Pivot Bit Keeps the Rightmost Number

**Insert from left to right, letting each pivot bit keep the rightmost number; a query $[l, r]$ uses only the basis numbers at positions $\ge l$.**

1. **Example: CF 1100F**
   - **Task**: an array and many queries asking for the maximum subset XOR inside $[l, r]$. Rebuilding a basis per query costs $O(60 \cdot \text{length})$, too slow.
   - **How this differs from 3.1**: in 3.1 the numbers put into the basis are themselves segment XORs; here they are still single $a_i$, and the range only limits which of them may be used.
2. **The method: insertion with swaps, called the prefix basis**
   - **Next to each `b[i]` keep a position `pos[i]`**: when inserting the $p$-th number, if the `b[i]` met has a smaller position than $p$, swap them; the newcomer stays in `b[i]`, and the old number carries its position further down.
   - **After inserting the $r$-th number, answer the queries with right end $r$**: run the greedy using only the `b[i]` with `pos[i]` $\ge l$; sort the queries by $r$ offline and keep a single basis.

#### Cost

Each insertion and each query is $O(60)$; with the queries sorted by $r$ offline, the total is $O(q \log q + 60 (n + q))$.

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

- **Using only positions $\ge l$ is right because this is the greedy of 3.2 with position as the weight**: inserting by decreasing position $a_r, a_{r-1}, \dots$, once $a_l$ is in the basis already expresses all of $a_l, \dots, a_r$; numbers further left only fill empty dimensions, so the part with position $\ge l$ spans exactly $a_l, \dots, a_r$.
- **Insertion with swaps maintains this greedy online**: the newcomer has the largest position and should be chosen first; the number pushed down until it vanishes is the leftmost one in a dependent set.
- **Example**: the figure below shows the basis after each insertion of the array $5, 6, 3, 4$, and the query $[3, 4]$ at right end 4.

<a href="/images/algo/xor-basis-prefix.en.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-prefix.en.svg" alt="Prefix XOR basis: array 101, 110, 011, 100. After a1: b[2]=101@1. After a2: 110@2 swaps out 101@1, which reduces to 011 and goes to b[1]. After a3: 011@3 swaps out 011@1, which reduces to 0 and is dropped. After a4: 100@4 takes b[2], 110@2 is pushed down, reduces to 001 and goes to b[0]. Query [3,4] uses only 100@4 and 011@3, max XOR 111=7." style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

## 4. Example: Maximum XOR Path

[Luogu P4151](https://www.luogu.com.cn/problem/P4151), WC2011, time limit 1 s

1. **Statement**

   A connected undirected graph with non-negative edge weights, vertices numbered 1 to $N$. Find a path from vertex 1 to vertex $N$ whose edge-weight XOR is maximum. The path may revisit vertices and edges, and an edge is XORed in as many times as it appears.

   - **Input**: the first line holds $N, M$, the numbers of vertices and edges. Each of the next $M$ lines holds $S_i, T_i, D_i$: an undirected edge of weight $D_i$ between $S_i$ and $T_i$. There may be multi-edges or self-loops. $N \le 50000$, $M \le 100000$, $D_i \le 10^{18}$.
   - **Output**: one integer, the maximum XOR.

   **Input**

   ```text
   5 7
   1 2 2
   1 3 2
   2 4 1
   2 5 1
   4 5 3
   5 3 4
   4 3 2
   ```

   **Output**

   ```text
   6
   ```

   The statement's note: the path $1 \to 2 \to 4 \to 3 \to 5 \to 2 \to 4 \to 5$ has XOR $2 \oplus 1 \oplus 2 \oplus 4 \oplus 1 \oplus 1 \oplus 3 = 6$; the shorter path $1 \to 3 \to 5$ also gives $2 \oplus 4 = 6$.
2. **Idea**
   1. **The XORs of all paths are one fixed path $P$ XOR any cycle**:

      $$\{\text{XORs of all paths from 1 to } N\} = \{\, P \oplus C \mid C \text{ is a cycle XOR} \,\}$$

      Paths may backtrack, and an edge used twice cancels: going along $P$ and back along another path $Q$ is a cycle $C$, so the XOR of $Q$ is $P \oplus C$. Conversely, walk from 1 onto $C$, go around, come back the same way to 1, then follow $P$; the back-and-forth part cancels, giving $P \oplus C$.
   2. **Cycle XORs form a space, so the answer is `max_xor(P)`**: two cycles joined are still a cycle, the connecting back-and-forth part cancelling, so cycle XORs are closed under XOR (1.5) and a basis applies; the answer is the maximum XOR starting from $P$ (2.3). What is left is a basis of the cycle space.
   3. **A basis of the cycle space: build a spanning tree and insert $d_u \oplus d_v \oplus w$ for every edge**: $d_u$ is the XOR along tree edges from 1 to $u$, given by one BFS from 1. Every step $u \to v$ (weight $w$) of a cycle splits as

      $$w = d_u \oplus d_v \oplus \underbrace{(d_u \oplus d_v \oplus w)}_{0 \text{ on tree edges}}$$

      Writing out every step of a cycle and XORing them all, the $d$ parts cancel in pairs and only the bracketed terms remain; conversely each $d_u \oplus d_v \oplus w$ is itself a cycle. So inserting this term for every edge gives a basis of the cycle space. Take $P$ to be the tree path, which is $d_N$.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // the appendix's XorBasis: only the members used here, copy the implementation from the appendix
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]: the number whose highest bit is exactly i, 0 if none
       int r = 0;                              // rank
       bool insert(long long x);               // true if inserted (rank grows by 1)
       long long max_xor(long long v = 0) const;   // max of v XOR any subset
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

3. **Cost and pitfalls**
   - **Cost**: BFS is $O(n + m)$ and each edge is inserted once at $O(60)$, $O((n + m) \cdot 60)$ in total.
   - **Tree edges, self-loops and multi-edges need no special case**: a tree edge inserts 0, and a self-loop or multi-edge inserts its own cycle.
   - **Small weights give a ready-made brute force**: with all weights below 16, the state "which vertex, which current XOR" has only $16 n$ values; BFS from $(1, 0)$ and take the largest XOR at vertex $N$ to cross-check the program.

## 5. Two Recent Contest Problems

### 5.1 CCPC Final 2025 L (Spirited Away): Counting Distinct Range Spans

[QOJ / Universal Cup 3727 L](https://contest.ucup.ac/contest/3727/problem/18012), time limit 4 s

1. **Statement**

   You are given a sequence of non-negative integers $a_1, \dots, a_n$. For a range $[l, r]$, XOR together any subset of $a_l, \dots, a_r$ (the empty subset gives 0); the set of all possible results is $B(l, r)$. Over all $1 \le l \le r \le n$, how many distinct sets $B(l, r)$ are there?

   - **Input**: the first line holds $T$, the number of test cases. Each test case has $n$ ($1 \le n \le 10^5$) on one line and $n$ integers $a_i$ ($0 \le a_i < 2^{32}$) on the next. The sum of $n$ over all test cases is at most $10^5$.
   - **Output**: for each test case, one line with the number of distinct sets $B(l, r)$.

   **Input**

   ```text {hl_lines=["2-3","6-7","10-11"]}
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
   ```

   **Output**

   ```text {hl_lines=[1,3,5]}
   4
   10
   12
   36
   46
   ```

   In the first test case $a = (1, 2, 3)$: $B(1, 1) = \{0, 1\}$, $B(2, 2) = \{0, 2\}$, $B(3, 3) = \{0, 3\}$, and the other three ranges all give $\{0, 1, 2, 3\}$, so the answer is 4.
2. **Idea**
   1. **Only $O(32 n)$ ranges are really different**: fix the right end $r$ and move the left end left; the space only grows, each change adds one dimension, so it changes at most 32 times. The change points are the positions in the prefix basis of 3.3: after inserting $a_r$, list the basis by `pos` decreasing as $v_1, \dots, v_k$ with positions $p_1 > p_2 > \cdots > p_k$, and set $p_{k+1} = 0$; then

      $$B(l, r) = \operatorname{span}(v_1, \dots, v_j), \qquad p_{j+1} < l \le p_j .$$

      This restates 3.3: "the part with position $\ge l$ spans exactly $a_l, \dots, a_r$". So for each $r$ only these at most 32 spaces need to be enumerated.
   2. **Two spaces are equal exactly when their reduced bases are**: the highest bit of every nonzero value in the space is a pivot bit, so the set of pivot bits is determined by the space; after reduction the basis number at pivot $p$ is the value of the space whose only 1 among the pivot bits is at $p$, and by 1.4 there is exactly one, so it is determined by the space too. Hash the reduced basis to a 64-bit number; counting distinct hashes counts distinct spaces.
   3. **The hash of a basis is the sum of `mix` over its numbers**: $h(S) = \sum_{x \in S} \operatorname{mix}(x) \bmod 2^{64}$, skipping positions where `b[i]` is 0.

      **The same basis gives the same value**: `mix` is a fixed function, and a sum does not depend on order.

      **Two different bases almost never collide**: treat $\operatorname{mix}(x)$ as an independent, uniform random 64-bit number assigned to each $x$. For $S \ne T$, $h(S) - h(T)$ is a $\pm 1$ sum of the $\operatorname{mix}$ values over the symmetric difference; with all other terms fixed, the remaining one must hit one specific value, probability $2^{-64}$. With about $3.2 \times 10^6$ hashes, about $5 \times 10^{12}$ pairs, the chance of any collision is about $3 \times 10^{-7}$.

      **Why `mix` first**: the argument needs the values to be independent and close to random. Raw basis numbers are not; they are linearly related by construction. For example, the space $\{0, 1, 2, 3\}$ has reduced basis $\{1, 2\}$ and the space $\{0, 3\}$ has $\{3\}$; the spaces differ, yet both raw sums are 3 and both XORs are 3.

      **The essence of why `mix` scrambles: it alternates xorshifts with multiplication by odd constants, two operations that do not distribute over each other, so additive or XOR relations among the inputs do not survive to the outputs.** An xorshift `x ^= x >> k` is linear for XOR and multiplying by an odd number is linear for addition mod $2^{64}$, but neither is linear for both; after two rounds, $x \oplus y = z$ or $x + y = z$ implies no simple relation among $\operatorname{mix}(x)$, $\operatorname{mix}(y)$, $\operatorname{mix}(z)$. The right shift folds high bits into low ones, and the multiplication carries only upward, spreading low bits into high ones; after two rounds every output bit depends on every input bit, and flipping one input bit flips about half the output bits (avalanche). Every step is invertible (an odd multiplier is invertible mod $2^{64}$, and so is an xorshift), so `mix` is a bijection: distinct numbers stay distinct, and a collision can only come from the summation.
   4. **Keep the basis reduced while inserting**: calling `reduce()` and rehashing after every insertion costs $O(32^3)$ per right endpoint $r$, too slow. Use 2.4's `insert_reduced` and stay reduced during insertion instead, $O(60)$ per number. The hash is computed as in item 3 and recomputed after each insertion, also $O(60)$. The code uses the appendix's `PrefixBasis` to get the at most 32 basis numbers of each right endpoint, then inserts them into a fresh `XorBasis` by position, largest first.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // the appendix's PrefixBasis (3.3): only the members used here, copy the implementation from the appendix
   struct PrefixBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]: the rightmost number whose pivot is bit i
       int pos[B] = {};                        // position of b[i] (from 1)
       void insert(long long x, int p);        // insert the p-th number
   };

   // the appendix's XorBasis: same
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]: the number whose highest bit is exactly i, 0 if none
       int r = 0;                              // rank
       bool insert_reduced(long long x);       // insert and keep the basis reduced; it must be reduced before
   };

   uint64_t mix(uint64_t x) {                    // splitmix64: scramble a number into 64 random-looking bits
       x += 0x9e3779b97f4a7c15ULL;
       x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
       x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
       return x ^ (x >> 31);
   }

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int T;
       cin >> T;
       while (T--) {
           int n;
           cin >> n;
           PrefixBasis pb;
           vector<uint64_t> hs;                  // hash of the space for each (r, j)
           for (int r = 1; r <= n; r++) {
               long long x;
               cin >> x;
               pb.insert(x, r);
               vector<pair<int, long long>> v;   // (position, basis number), by position descending
               for (int i = 0; i < PrefixBasis::B; i++)
                   if (pb.b[i]) v.push_back({pb.pos[i], pb.b[i]});
               sort(v.rbegin(), v.rend());
               if (v.empty() || v[0].first < r) hs.push_back(0);   // a_r = 0: B(r, r) = {0}
               XorBasis c;                       // reduced basis, filled one by one in position order
               for (auto [q, y] : v) {
                   c.insert_reduced(y);
                   uint64_t h = 0;
                   for (int i = 0; i < XorBasis::B; i++)
                       if (c.b[i]) h += mix(c.b[i]);
                   hs.push_back(h);              // B(l, r) for l in (next position, q]
               }
           }
           sort(hs.begin(), hs.end());
           cout << unique(hs.begin(), hs.end()) - hs.begin() << '\n';
       }
   }
   ```

   5. **Incremental Gauss throughout works too**: an XOR basis is a special case of incremental Gauss (appendix), so both parts can be swapped. `PrefixGauss` replaces `PrefixBasis` and gives each right endpoint's at most 32 equations with their positions; `IncGauss` replaces `insert_reduced`: add them by position, largest first, hashing after each. `PrefixGauss` keeps only row echelon form, so one space can be stored as different rows; passing them through `IncGauss`, which always stays in RREF, makes the result depend only on the space. Column $i$ holds bit $i$ of the number, and `MV` is 64.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   const int MV = 64;                               // 1024 in the appendix; 32 columns here, so 64 is enough (MV must exceed the column count)

   // the appendix's IncGauss: only the members used here, copy the implementation from the appendix
   struct IncGauss {
       int n;                                       // number of columns
       vector<bitset<MV>> row;                      // always in RREF
       IncGauss(int n);
       int add(bitset<MV> v, int b);                // 1: independent, rank grows; 0: implied by the rows; -1: contradiction
   };

   // the appendix's PrefixGauss: same
   struct PrefixGauss {
       int n;
       vector<bitset<MV>> row;                      // row[c]: the rightmost equation whose first 1 is in column c
       vector<int> pos;                             // position of row[c] (from 1), 0 if empty
       PrefixGauss(int n);
       void add(bitset<MV> v, int b, int p);        // add the p-th equation
   };

   uint64_t mix(uint64_t x) {                       // splitmix64: scramble a number into 64 random-looking bits
       x += 0x9e3779b97f4a7c15ULL;
       x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
       x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
       return x ^ (x >> 31);
   }

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int T;
       cin >> T;
       while (T--) {
           int n;
           cin >> n;
           PrefixGauss pg(32);                      // 32 columns: column i holds bit i of the number
           vector<uint64_t> hs;
           for (int r = 1; r <= n; r++) {
               unsigned long long x;
               cin >> x;
               pg.add(bitset<MV>(x), 0, r);         // right-hand side always 0, only the left side matters
               vector<pair<int, int>> v;            // (position, column), by position descending
               for (int c = 0; c < 32; c++)
                   if (pg.pos[c]) v.push_back({pg.pos[c], c});
               sort(v.rbegin(), v.rend());
               if (v.empty() || v[0].first < r) hs.push_back(0);   // a_r = 0: B(r, r) = {0}
               IncGauss g(32);
               for (auto [q, c] : v) {
                   g.add(pg.row[c], 0);
                   uint64_t h = 0;
                   for (auto& w : g.row) h += mix(w.to_ullong());
                   hs.push_back(h);                 // B(l, r) for l in (next position, q]
               }
           }
           sort(hs.begin(), hs.end());
           cout << unique(hs.begin(), hs.end()) - hs.begin() << '\n';
       }
   }
   ```

3. **Cost and pitfalls**
   - **Cost of the XOR basis version**: each insertion is $O(60)$ (both the insertion and the rehash scan 60 bits) and each right end inserts at most 32 numbers, $O(60 \cdot 32 \cdot n)$ in total, about $2 \times 10^8$ simple operations at $n = 10^5$, well within the 4-second limit.
   - **Cost of the incremental Gauss version**: with `MV` = 64 a bitset row is one word; `pg.add` scans at most 32 columns, `g.add` walks at most 32 rows, and the rehash covers 32 rows, all $O(32)$, $O(32^2 n)$ in total. With the appendix's `MV` = 1024 each XOR touches 16 words, 16 times slower, which may exceed the limit.
   - **Do not call `pg.at(l)` for every left end**: `at` builds a fresh `IncGauss` each time, $O(32^3)$ per right endpoint, the same problem as calling `reduce()` every time; add the equations one by one by position, largest first, and hash after each.
   - **When $a_r = 0$, count $\{0\}$ separately**: $a_r$ cannot be inserted, so $p_1 < r$, and the ranges with left end in $(p_1, r]$ give $\{0\}$, which the formula above does not cover.
   - **Hash collisions are negligible**: the chance is about $3 \times 10^{-7}$; see item 3 of the idea.

### 5.2 2026 ICPC Online Contest II A (All Closed): What Every Solution Must Contain

[QOJ 20236](https://qoj.ac/contest/4113/problem/20236), 2026 ICPC Online Contest II A, time limit 1 s

1. **Statement**

   You are given $n$ sets $S_1, \dots, S_n$, each holding distinct integers in $[0, 2^m)$. One operation picks an integer $x$ ($0 \le x < 2^m$) and inserts it into every set (where it is not already present). A set $S$ is XOR-closed if $x \oplus y \in S$ for all $x, y \in S$. Find the minimum number of operations that makes every $S_i$ XOR-closed, and give one way to do it.

   - **Input**: the first line holds $n$ ($1 \le n \le 2 \cdot 10^5$) and $m$ ($1 \le m \le 20$); the $i$-th of the next $n$ lines holds $c_i$ ($c_i \ge 1$) followed by $c_i$ distinct integers $a_{i,1}, \dots, a_{i,c_i}$ ($0 \le a_{i,j} < 2^m$), the elements of $S_i$; $\sum c_i \le 10^6$.
   - **Output**: the minimum number of operations $k$ on the first line, and on the second the $k$ chosen values of $x$ in order; any optimal solution is accepted.

   **Sample 1 input**

   ```text
   3 3
   1 1
   3 0 1 7
   6 1 2 3 4 5 7
   ```

   **Sample 1 output**

   ```text
   3
   0 7 6
   ```

   **Sample 2 input**

   ```text
   1 4
   4 11 5 14 0
   ```

   **Sample 2 output**

   ```text
   0
   ```

   The statement's note: after the operations in sample 1, $S_1$ and $S_2$ become $\{0, 1, 6, 7\}$ and $S_3$ becomes $\{0, 1, \dots, 7\}$; fewer than 3 operations cannot work. In sample 2 the only set is already closed, so no operation is needed.
2. **Idea**
   1. **From "fewest operations" to "smallest space"**: a nonempty set closed under XOR contains $a \oplus a = 0$, so it is a space. Let the added numbers form $T$; the common part of all final sets

      $$K = \bigcap_{i} (S_i \cup T) = I \cup T, \qquad I = \bigcap_i S_i$$

      is an intersection of spaces, hence a space, and the final sets can be written $S_i \cup K$. $T$ need not contain numbers of $I$, which are already in every set, so $|T| = |K| - |I|$. Fewest operations therefore means the smallest space $K \supseteq I$ such that every $S_i \cup K$ is a space; the answer is $K \setminus I$.
   2. **Every added number is forced**: start from $K = \operatorname{span}(I)$. When some $S_i \cup K$ is not closed, take an $x$ in $\operatorname{span}(S_i \cup K)$ but in neither $S_i$ nor $K$. For any valid solution $K^*$ containing the current $K$, $S_i \cup K^*$ is a space containing $S_i \cup K$, so it contains $x$; since $x \notin S_i$, $x \in K^*$. Set $K \leftarrow \operatorname{span}(K \cup \{x\})$: it is still contained in every valid solution, and its rank grows by 1. Within $m$ steps every set is closed; then $K$ is valid and contained in every valid solution, so it is the smallest, and the answer is unique.
   3. **Closure is tested by counting elements**: $S_i \cup K$ always lies inside the space it spans, which has exactly $2^r$ elements (1.3), $r$ being the rank of $S_i \cup K$; equal sizes mean the two are the same set:

      $$S_i \cup K \text{ closed} \iff \lvert S_i \rvert + \lvert K \rvert - \lvert S_i \cap K \rvert = 2^r .$$

      When it is not closed, list $\operatorname{span}(S_i \cup K)$, at most $2^m$ elements, and any one in neither $S_i$ nor $K$ is the $x$ to add.

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   int n, m;

   // the appendix's XorBasis: only the members used here, copy the implementation from the appendix
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]: the number whose highest bit is exactly i, 0 if none
       int r = 0;                              // rank
       bool insert(long long x);               // true if inserted (rank grows by 1)
   };

   vector<int> expand(const XorBasis& lb) { // list every element of span(b)
       vector<int> all = {0};
       for (int i = 0; i < XorBasis::B; i++)
           if (lb.b[i]) {
               int sz = all.size();
               for (int j = 0; j < sz; j++) all.push_back(all[j] ^ lb.b[i]);
           }
       return all;
   }

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       cin >> n >> m;
       vector<vector<int>> s(n);
       vector<int> cnt(1 << m, 0);            // cnt[x]: how many sets contain x
       for (auto& si : s) {
           int k;
           cin >> k;
           si.resize(k);
           for (int& x : si) { cin >> x; cnt[x]++; }
       }
       XorBasis kb;                           // basis of K, starting from span(I)
       for (int x = 0; x < (1 << m); x++)
           if (cnt[x] == n) kb.insert(x);
       vector<char> inK(1 << m), inS(1 << m);
       while (true) {
           vector<int> K = expand(kb);
           fill(inK.begin(), inK.end(), 0);
           for (int x : K) inK[x] = 1;
           int forced = -1;                   // a new number every valid solution must contain
           for (int i = 0; i < n && forced < 0; i++) {
               XorBasis b = kb;
               int common = 0;                // |S_i ∩ K|
               for (int x : s[i]) { b.insert(x); common += inK[x]; }
               int r = b.r;
               long long uni = (long long)s[i].size() + K.size() - common;   // |S_i ∪ K|
               if (uni == (1LL << r)) continue;                              // already closed
               for (int x : s[i]) inS[x] = 1;
               for (int x : expand(b))
                   if (!inK[x] && !inS[x]) { forced = x; break; }
               for (int x : s[i]) inS[x] = 0;
           }
           if (forced < 0) break;
           kb.insert(forced);
       }
       vector<int> ans;                       // K \ I
       for (int x : expand(kb))
           if (cnt[x] < n) ans.push_back(x);
       sort(ans.begin(), ans.end());
       cout << ans.size() << '\n';
       for (int x : ans) cout << x << ' ';
       cout << '\n';
   }
   ```

3. **Cost and pitfalls**
   - **Cost**: at most $m$ rounds; checking all sets in one round is $O(m \sum \lvert S_i \rvert)$, plus $O(2^m)$ for the listing.
   - **To find the smallest valid solution, start from what every valid solution must contain**: keep adding forced numbers until the solution is valid; where it stops is the smallest.

## Practice

Each problem lists the section it uses.

**Core**

1. [Luogu P3857 彩灯](https://www.luogu.com.cn/problem/P3857): 2.2.
2. [Luogu P4570 元素](https://www.luogu.com.cn/problem/P4570): 3.2.
3. [LOJ 114 k 大异或和](https://loj.ac/p/114): 2.5; watch whether 0 counts.
4. [Luogu P4869 albus就是要第一个出场](https://www.luogu.com.cn/problem/P4869): rank of a given value, 2.5 in reverse, times the repetition count of 1.3.
5. [CF 845G Shortest Path Problem?](https://codeforces.com/problemset/problem/845/G): Section 4, asking for the minimum.
6. [CF 1100F Ivan and Burgers](https://codeforces.com/problemset/problem/1100/F): 3.3.

**Optional**

7. [CF 959F Mahmoud and Ehab and yet another xor task](https://codeforces.com/problemset/problem/959/F): the number of subsets of the first $l$ numbers with XOR $x$, 2.2 plus offline processing.
8. [Luogu P3292 幸运数字](https://www.luogu.com.cn/problem/P3292): maximum XOR on a tree path, 2.6 plus binary lifting.

## Connections to Other Boxes on the Map

- The elimination of 1.2 is Gaussian elimination mod 2, and insertion is a special case of incremental elimination in [L2 Gaussian Elimination](/algo/l2-gaussian-elimination/) section 6.1. The number of solutions of an XOR system ($2^{\text{free variables}}$) is the same number as the $2^{n-r}$ of 1.3: the free variables are exactly the numbers whose insertion failed.
- The 0/1 trie of A6 also finds a maximum XOR, but of "$x$ with one number of the set": only a single number may be chosen; a basis answers "any subset". A statement that says "pick two numbers" wants a trie; one that says "pick some numbers" wants a basis.
- The greedy of 3.2 is greedy on a matroid, the same structure as Kruskal's minimum spanning tree (acyclic edge sets in place of independent sets).

## Appendix: XOR Basis and Incremental Gauss Templates

The two templates side by side. An XOR basis is incremental Gauss written for "at most 60 columns, no right-hand side", so almost every operation has a counterpart on both sides; right-hand sides, contradictions and solution vectors exist only in incremental Gauss. Both templates were checked against brute-force enumeration.

**How the two templates differ**

| | XOR basis `XorBasis` | Incremental Gauss `IncGauss` |
| --- | --- | --- |
| A row is | a number, no right-hand side | an equation: coefficient bitset + right-hand side |
| Stored by | `b[i]` is the row whose pivot is bit $i$ | each row remembers its pivot column `piv` |
| Reduced to 0 | insertion fails: the number is reachable | check the right-hand side: 0 means implied by the rows (returns 0), nonzero means contradiction (returns $-1$, `bad` remembers it) |
| Columns | at most 60 | at most `MV`, thousands are fine |

**Operations and costs**

| Task | `XorBasis` | `IncGauss` |
| --- | --- | --- |
| Insert, not keeping the basis reduced | `insert`, $O(60)$ | none |
| Insert, keeping it reduced | `insert_reduced`, $O(60)$ | `add`, $O(r w)$ |
| Reduce afterwards | `reduce()`, $O(60^2)$ | not needed |
| Can it be represented | `contains`, $O(60)$ | `implied`, which also gives the implied RHS, $O(r w)$ |
| Rank | `r`, $O(1)$ | `rank()`, $O(1)$ |
| Max / min XOR | `max_xor` / `min_xor`, $O(60)$ | `max_xor` / `min_xor`, $O(r w)$ |
| $k$-th smallest | `kth`, basis must be reduced, $O(60)$ | `kth`, $O(r \log r + r w)$ |
| Rank of a value | `index`, basis must be reduced, $O(60)$ | `index`, $O(r \log r)$ |
| Merge | `merge`, $O(60^2)$ | `merge`, $O(r' r w)$ |
| One solution | none | `solve()`, $O(r + w)$ |
| All solutions | none | `kernel()`, $O((n - r)(r + w))$ |

**Range queries**

| Task | `PrefixBasis` | `PrefixGauss` |
| --- | --- | --- |
| Add the $p$-th item | `insert`, $O(60)$ | `add`, $O(n w)$ |
| Max XOR of a range | `max_xor`, $O(60)$ | `max_xor`, $O(n w)$ |
| Implied by a range | none | `implied`, $O(n w)$ |
| Is a range contradictory | none | `bad`, $O(1)$ |
| Rank of a range | none | `rank`, $O(n)$ |
| Extract a range's basis | `at`, $O(60)$ | `at`, $O(n r w)$ |

In the costs, $r$ is the current rank, $r'$ the other side's rank, $n$ the number of unknowns, and $w = \text{MV} / 64$ the number of machine words in one bitset row, so one bitset XOR is $w$ integer XORs. An XOR basis row is a single word ($w = 1$) and its rank is at most 60: put $w = 1$ and $r = 60$ into the incremental Gauss column and you get the XOR basis column. Each operation costs the same order on both sides; the difference is only how many columns fit.

So "can this number be reached by XOR" and "is this equation redundant" are the same question; a right-hand side adds the third outcome, contradiction.

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
    bool insert_reduced(long long x) {           // basis must be reduced before; stays reduced; true if inserted
        for (int i = B - 1; i >= 0; i--)
            if ((x >> i & 1) && b[i]) x ^= b[i]; // clear every existing pivot bit of x, all the way down to bit 0
        if (!x) return false;                    // reduced to 0: already reachable
        int t = 63 - __builtin_clzll(x);         // the highest remaining bit is the new pivot
        for (int i = t + 1; i < B; i++)
            if (b[i] >> t & 1) b[i] ^= x;        // clear bit t in the higher basis numbers
        b[t] = x;
        r++;
        return true;
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
    long long kth(unsigned long long k) const {  // basis must be reduced; k-th smallest (0-based, the 0th is 0), -1 if none
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;
    }
    unsigned long long index(long long x) const {  // basis must be reduced; rank of a reachable x among the values (0-based)
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

// prefix basis (explained in 3.3): insert left to right, each pivot bit keeps the rightmost number
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

`kth` counts $k$ from 0 and includes 0; whether the statement's "$k$-th smallest" counts 0 depends on whether $r = n$, as at the end of 2.5.

### Incremental Gauss (mod 2)

The equation-solving functions are the template of [L2 section 6.1](/algo/l2-gaussian-elimination/), implemented right inside the struct; their costs are in the table at the start of this appendix. The operations that mirror the XOR basis (including `PrefixGauss::max_xor`) are only declared in the struct and implemented afterwards.

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

    // solving equations
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

    // counterparts of the XOR basis operations: left sides only (row space), RHS ignored; column 0 is the most significant bit
    bitset<MV> max_xor(bitset<MV> v) const;      // max of v XOR any rows
    bitset<MV> min_xor(bitset<MV> v) const;      // min of v XOR any rows
    bitset<MV> kth(unsigned long long k) const;  // k-th smallest in the row space (0-based, the 0th is all zeros); needs k < 2^rank()
    unsigned long long index(const bitset<MV>& x) const;        // rank of x among the row space when x is in it (0-based)
    vector<int> low_to_high() const;             // row ids ordered by pivot from low bit to high bit (pivot column descending)
};

// prefix incremental Gauss (mod 2): equations come left to right, each pivot column keeps the rightmost one; the RHS is column n and is eliminated too
struct PrefixGauss {
    int n;
    vector<bitset<MV>> row;                      // row[c]: the equation whose first 1 is in column c; the row for c = n is 0 = 1
    vector<int> pos;                             // position of row[c] (1-based), 0 if empty
    PrefixGauss(int n) : n(n), row(n + 1), pos(n + 1, 0) {}

    void add(bitset<MV> v, int b, int p) {       // add the p-th equation; needs MV > n
        v[n] = b;
        while (v.any()) {
            int c = v._Find_first();
            if (!pos[c]) { row[c] = v; pos[c] = p; return; }
            if (pos[c] < p) { swap(row[c], v); swap(pos[c], p); }
            v ^= row[c];
        }
    }
    bool bad(int l) const { return pos[n] >= l; }  // are equations l..current contradictory (l is 1-based)
    int rank(int l) const {                      // rank of equations l..current
        int r = 0;
        for (int c = 0; c < n; c++) r += pos[c] >= l;
        return r;
    }
    int implied(bitset<MV> v, int l) const {     // using only equations l..current: the implied RHS, or -1 if not implied
        v[n] = 0;
        for (int c = v._Find_first(); c < n; c = v._Find_next(c)) {
            if (pos[c] < l) return -1;
            v ^= row[c];
        }
        return v[n];
    }
    bitset<MV> max_xor(bitset<MV> v, int l) const;              // max of v XOR left sides of equations l..current
    IncGauss at(int l) const {                   // equations l..current as an IncGauss
        IncGauss g(n);
        for (int c = 0; c <= n; c++)
            if (pos[c] >= l) {
                bitset<MV> w = row[c];
                int b = w[n];
                w[n] = 0;
                g.add(w, b);
            }
        return g;
    }
};
```

Unknown $j$ is bit $j$ of the bitset. When `bad` is true the system has no solution and `solve()` and `kernel()` mean nothing; otherwise there are $2^{n - \text{rank}}$ solutions, which is [L1 linear algebra](/algo/l1-linear-algebra/) section 4.5's picture: all solutions are the null space translated by one solution.

The functions that mirror the XOR basis look only at left sides and read each row as an $n$-bit number with **column 0 as the most significant bit**. The pivot is the first 1 in a row, so "earlier pivot, larger number" is the same as the basis's "higher top bit, larger number". To match integers, put bit $W - 1 - j$ of an integer $x$ into column $j$ ($W$ is the bit width). The rows are always in RREF, so `kth` needs no `reduce()` first.

`PrefixGauss` is the swap insertion of 3.3 with bitset rows and the first 1 as the pivot; the RHS is column $n$ and is eliminated too, so the row `0 = 1` keeps the rightmost position $q$, and equations $l$ through the current one contradict each other exactly when $l \le q$, which is all `bad(l)` checks. It keeps only an echelon form without clearing old rows, so `max_xor` scans the columns front to back greedily.

#### Implementation: Counterparts of the XOR Basis Operations

```cpp
// in RREF each pivot column is 1 only in its own row, so the result on a pivot column says whether that row was chosen,
// and two choices first differ on some pivot column: the greedy only decides 0 or 1 on each pivot column
bitset<MV> IncGauss::max_xor(bitset<MV> v) const {
    for (int i = 0; i < (int)row.size(); i++)
        if (!v[piv[i]]) v ^= row[i];
    return v;
}

bitset<MV> IncGauss::min_xor(bitset<MV> v) const {
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

bitset<MV> IncGauss::kth(unsigned long long k) const {        // bit t of k: whether to take the row of the t-th pivot counted from the low end
    bitset<MV> v;
    vector<int> id = low_to_high();
    for (int t = 0; t < (int)id.size() && t < 64; t++)
        if (k >> t & 1) v ^= row[id[t]];
    return v;
}

unsigned long long IncGauss::index(const bitset<MV>& x) const {
    unsigned long long k = 0;
    vector<int> id = low_to_high();
    for (int t = 0; t < (int)id.size() && t < 64; t++)
        if (x[piv[id[t]]]) k |= 1ULL << t;
    return k;
}

bitset<MV> PrefixGauss::max_xor(bitset<MV> v, int l) const {              // echelon form: row[c] only touches columns c and later, so greedy from the high end
    for (int c = 0; c < n; c++)
        if (pos[c] >= l && !v[c]) v ^= row[c];
    v[n] = 0;                                    // column n is the RHS, drop it
    return v;
}
```

**Which one: if the problem asks what XORs of subsets of some numbers can give, use the XOR basis; if it asks to solve equations, detect contradictions, or has more than 60 unknowns, use incremental Gauss.**
