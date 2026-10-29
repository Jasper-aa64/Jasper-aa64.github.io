---
title: "A1: Complexity, Binary Search, Two Pointers, Prefix Sums"
date: 2026-10-29
slug: "a1-complexity-binary-search-two-pointers-prefix-sums"
description: "Four basics on arrays: read the limits to pick the complexity, and the STL interface traps; one binary search template (first true) and binary search on the answer, which turns optimisation into a check; two pointers work when validity survives shrinking the window; prefix sums turn subarray sums into a difference of two numbers, difference arrays turn range adds into two point updates. Eight practice problems."
weight: 1
math: true
toc: true
---

All four topics in this round answer queries on an array, and all of them bring brute-force $O(n^2)$ down. Two properties make that possible: monotonicity (binary search, two pointers) and accumulated quantities that can be subtracted (prefix sums, difference arrays). Complexity comes first because it decides which direction to think in.

## 1. Complexity: read the limits first

### 1.1 From the limits to the complexity

C++ does roughly $10^8$ simple operations (additions, comparisons, array accesses) per second. Once the problem states the bound on $n$, the acceptable complexity is mostly fixed:

| Bound on $n$ | Acceptable complexity | Typical approach |
|---|---|---|
| around $20$ | $O(2^n \cdot n)$ | Subset enumeration, bitmask DP |
| $500$ | $O(n^3)$ | Interval DP, Floyd |
| $5000$ | $O(n^2)$ | Double-loop DP |
| $2 \times 10^5$ | $O(n \log n)$ | Sorting, binary search, heaps, segment trees |
| $10^7$ | $O(n)$ | Two pointers, prefix sums, linear sieve |
| $10^{18}$ | $O(\log n)$ or $O(\sqrt n)$ | Fast power, binary search on the answer, floor blocks |

With $n$ up to $2 \times 10^5$, $O(n^2)$ is $4 \times 10^{10}$ operations and certainly too slow, so think of sorting, binary search or two pointers. **Look at $n$ first: it nearly tells you which family of algorithms to use.** Interviews work the same way: when the interviewer states the input size, that is a hint about the complexity.

### 1.2 What STL containers cost

| Operation | Complexity | Trap |
|---|---|---|
| `vector::push_back` | Amortised $O(1)$ | Growth moves everything; `reserve` when the size is known |
| `sort` | $O(n \log n)$ | The comparator must be a strict "less than"; `<=` gives wrong results or even out-of-bounds crashes |
| `map` / `set` operations | $O(\log n)$ | Red-black tree, larger constant than a hash table |
| `unordered_map` operations | Average $O(1)$, worst $O(n)$ | On Codeforces people build colliding inputs; use a custom hash |
| `priority_queue` `push` / `pop` | $O(\log n)$ | Max-heap by default |
| `lower_bound` on a `vector` | $O(\log n)$ | |
| `std::lower_bound` on a `set` | $O(n)$ | `set` iterators are not random access; call the member `s.lower_bound(x)` |

**Many time-limit failures are not a wrong algorithm but a wrong interface.** Besides the `set` row, two more are common: `memset` of a $10^6$ array in every test case, which costs $T \times 10^6$ over $T$ cases; and heavy I/O without unsynchronising. For large input, start with `ios::sync_with_stdio(false); cin.tie(nullptr);` and end lines with `'\n'`, not `endl` (which flushes every time).

## 2. Binary search: a boundary on a monotone predicate

### 2.1 One template: the first position that is true

Binary search does not need a sorted array; it needs a monotone predicate: `pred(i)` is false on a prefix and true from some position on, and we want the first true position. Finding the first element $\ge t$ in a sorted array is just the case `pred(i) = a[i] >= t`.

```cpp
// First position in [lo, hi) where pred is true; hi if there is none
template <class Pred>
long long first_true(long long lo, long long hi, Pred pred) {
    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2;
        if (pred(mid)) hi = mid;
        else lo = mid + 1;
    }
    return lo;
}
```

Why it is correct: the loop keeps two facts, everything left of `lo` is false, and `hi` and everything right of it are true (`hi` starts outside the range and counts as true). If `mid` is true, the first true is at `mid` or to its left, so `hi = mid`; if false, it is to the right, so `lo = mid + 1`. The range shrinks every step, and when `lo == hi` that position has only falses on its left and is itself true. If everything is false it returns the initial `hi`, meaning "none". `mid` is computed as `lo + (hi - lo) / 2` so that `lo + hi` cannot overflow.

**Memorise only this form (half-open, first true) and rewrite every other question into it:**

- First $\ge t$: `pred = a[i] >= t`, which is `lower_bound`;
- First $> t$: `pred = a[i] > t`, which is `upper_bound`;
- Last $\le t$: the first $> t$ minus one;
- How many times $t$ occurs: `upper_bound` minus `lower_bound`.

### 2.2 Binary search on the answer: from "find the minimum" to "is this enough"

Many problems ask for "the smallest $x$ such that ... is possible". If being able to do it with $x$ implies being able to do it with anything larger, then `pred(x) = possible with x` is false then true, and the first true is the answer. **Binary search on the answer turns optimisation into a feasibility check, and the check is usually much easier to write.**

Example: there are $n$ piles of bananas, you eat $k$ per hour and must finish within $h$ hours; find the smallest $k$. Faster always finishes too, so the predicate is monotone. At speed $k$ a pile of $p$ takes $\lceil p / k \rceil$ hours, and the total must not exceed $h$:

```cpp
int min_speed(const vector<int>& piles, long long h) {
    auto ok = [&](long long k) {
        long long hours = 0;
        for (int p : piles) hours += (p + k - 1) / k;   // ceiling division
        return hours <= h;
    };
    return first_true(1, *max_element(piles.begin(), piles.end()) + 1, ok);
}
```

Eating as fast as the largest pile always finishes, so the upper bound is that plus one. The cost is $O(n \log V)$, with $V$ the largest pile.

The signals: the problem asks for "the smallest possible maximum", "the largest possible minimum" or "the least amount needed", and checking a given answer is easy.

On real numbers, do not stop on an epsilon; run a fixed 100 iterations. Each one halves the interval, so 100 is far more precision than needed, and floating-point error can never cause an endless loop.

## 3. Two pointers and sliding windows

### 3.1 When the left end only moves right

Enumerating all subarrays is $O(n^2)$. Two pointers get $O(n)$ when the left end of a valid window never moves back as the right end advances. The left end then takes at most $n$ steps in total, and each element enters and leaves the window once.

That monotonicity comes from validity surviving a shrink. Take "no repeated character in the window": if a window has no repeats, neither does any smaller window inside it. So when extending the right end creates a repeat, move the left end right until it is gone; when the right end moves on, the left end never needs to go back, because going back makes a larger window, which can only be less valid. **To decide whether two pointers apply, ask whether validity survives shrinking the window: if it does, the left end only moves right.**

### 3.2 Two shapes: longest valid, shortest valid

For the longest valid window: extend the right end by one, shrink the left end while invalid, then record the answer.

```cpp
// Longest substring without repeated characters
int longest_unique(const string& s) {
    int cnt[256] = {}, best = 0, l = 0;
    for (int r = 0; r < (int)s.size(); r++) {
        cnt[(unsigned char)s[r]]++;
        while (cnt[(unsigned char)s[r]] > 1) cnt[(unsigned char)s[l++]]--;
        best = max(best, r - l + 1);
    }
    return best;
}
```

For the shortest valid window: extend the right end by one, and while still valid, record the answer and shrink the left end.

```cpp
// Shortest subarray with sum at least target, all elements positive
int min_len(int target, const vector<int>& a) {
    int n = a.size(), best = INT_MAX, l = 0;
    long long sum = 0;
    for (int r = 0; r < n; r++) {
        sum += a[r];
        while (sum >= target) {
            best = min(best, r - l + 1);
            sum -= a[l++];
        }
    }
    return best == INT_MAX ? 0 : best;
}
```

The second one relies on all elements being positive: then a larger window has a larger sum, "sum $\ge$ target" survives extending and may be lost by shrinking, and the left end only moves right. **With negative numbers the window sum is no longer monotone in the window, and two pointers give wrong answers**; that case needs prefix sums with a monotonic deque (round A2).

### 3.3 The other kind: closing in from both ends of a sorted array

To find two numbers summing to $t$ in a sorted array, start one pointer at each end: if the sum is too small move the left one right, if too large move the right one left. Nothing is missed: when the sum exceeds $t$, `a[r]` plus any remaining `a[l']` ($l' \ge l$) is even larger, so `r` can be discarded; symmetrically for `l`. Three-sum is one loop over the first number plus this squeeze on the rest, $O(n^2)$.

## 4. Prefix sums and difference arrays

### 4.1 Prefix sums: a range sum is one subtraction

Let $S_0 = 0$ and $S_i = a_0 + a_1 + \dots + a_{i-1}$; the sum of $[l, r)$ is $S_r - S_l$. Preprocessing is $O(n)$, each query $O(1)$. Making $S$ one longer and using half-open ranges removes the special case $l = 0$.

The bigger use is turning "subarray sum" into "difference of two prefixes", so a subarray problem becomes "find a pair $l < r$ in the prefix array". To count subarrays with sum $k$, count pairs with $S_r - S_l = k$: scan $r$ from left to right and ask how many earlier prefixes equal $S_r - k$, keeping counts in a hash map:

```cpp
long long count_sum_k(const vector<int>& a, long long k) {
    unordered_map<long long, long long> seen{{0, 1}};   // S_0 = 0 goes in first
    long long s = 0, ans = 0;
    for (int x : a) {
        s += x;
        if (auto it = seen.find(s - k); it != seen.end()) ans += it->second;
        seen[s]++;
    }
    return ans;
}
```

The initial 0 in `seen` accounts for subarrays starting at the beginning. Negative numbers are fine here, because nothing relies on monotonicity. **With negatives, use prefix sums and a hash map; only with all-positive values does a sliding window work. That is the line between the two.**

2D prefix sums: $S_{i,j}$ is the sum of the top-left $i \times j$ rectangle. By inclusion-exclusion,

$$S_{i+1,j+1} = S_{i,j+1} + S_{i+1,j} - S_{i,j} + a_{i,j}$$

and the sum over rows $[r_1, r_2)$ and columns $[c_1, c_2)$ is

$$S_{r_2,c_2} - S_{r_1,c_2} - S_{r_2,c_1} + S_{r_1,c_1}$$

```cpp
struct Prefix2D {
    vector<vector<long long>> S;
    Prefix2D(const vector<vector<int>>& a) {
        int n = a.size(), m = a[0].size();
        S.assign(n + 1, vector<long long>(m + 1, 0));
        for (int i = 0; i < n; i++)
            for (int j = 0; j < m; j++)
                S[i + 1][j + 1] = S[i][j + 1] + S[i + 1][j] - S[i][j] + a[i][j];
    }
    long long sum(int r1, int c1, int r2, int c2) const {   // rows [r1, r2), columns [c1, c2)
        return S[r2][c2] - S[r1][c2] - S[r2][c1] + S[r1][c1];
    }
};
```

### 4.2 Difference arrays: a range add is two point updates

The difference array undoes the prefix sum: $d_i = a_i - a_{i-1}$ (with $a_{-1} = 0$). Adding $v$ to every element of $[l, r)$ changes only two differences: $d_l$ grows by $v$ and $d_r$ shrinks by $v$. After all the adds, one prefix sum over $d$ rebuilds $a$, so $q$ range adds cost $O(n + q)$ instead of $O(nq)$.

```cpp
// Each op {l, r, v}: add v to [l, r)
vector<long long> apply_adds(int n, const vector<array<int, 3>>& ops) {
    vector<long long> d(n + 1, 0);
    for (auto [l, r, v] : ops) {
        d[l] += v;
        d[r] -= v;
    }
    vector<long long> a(n);
    long long run = 0;
    for (int i = 0; i < n; i++) a[i] = run += d[i];
    return a;
}
```

**Prefix sums and difference arrays are inverses: one accumulates points into ranges, the other splits ranges back into points.** So the operations decide: range adds with queries only at the end, use differences; a fixed array with many range-sum queries, use prefix sums; updates and queries interleaved, neither is enough and you need a Fenwick or segment tree (round B1).

2D differences work the same way: to add $v$ to a sub-rectangle, change four corners: $+v$ at the top left, $-v$ just right of the top right, $-v$ just below the bottom left, $+v$ just beyond the bottom right; one 2D prefix sum rebuilds the grid.

## Practice

The online judge decides right or wrong. Each problem has a one-line note on which section it practises.

**Core**

1. [LeetCode 34 Find First and Last Position of Element in Sorted Array](https://leetcode.com/problems/find-first-and-last-position-of-element-in-sorted-array/): the 2.1 template; write both boundaries as "first true".
2. [LeetCode 1011 Capacity To Ship Packages Within D Days](https://leetcode.com/problems/capacity-to-ship-packages-within-d-days/): binary search on the answer; get the bounds right.
3. [LeetCode 1004 Max Consecutive Ones III](https://leetcode.com/problems/max-consecutive-ones-iii/): longest valid window; first say what "valid" means.
4. [LeetCode 974 Subarray Sums Divisible by K](https://leetcode.com/problems/subarray-sums-divisible-by-k/): prefix sums with counting; watch negative remainders.
5. [LeetCode 1094 Car Pooling](https://leetcode.com/problems/car-pooling/): difference array.

**Optional**

6. [LeetCode 410 Split Array Largest Sum](https://leetcode.com/problems/split-array-largest-sum/): "smallest possible maximum".
7. [LeetCode 76 Minimum Window Substring](https://leetcode.com/problems/minimum-window-substring/): shortest valid window; the hard part is checking validity in $O(1)$.
8. [Luogu P3397 地毯 (Carpets)](https://www.luogu.com.cn/problem/P3397): 2D difference array.

## Links to other boxes on the map

- Prefix sums and differences are the simplest pair of "discrete calculus"; the counting lane uses more general forms.
- Binary search on the answer returns in the number theory lane: with $n$ up to $10^{18}$, many "smallest $x$" questions can only be binary-searched.
- The shortest subarray with sum $\ge k$ and negative numbers waits for the monotonic deque in A2.
