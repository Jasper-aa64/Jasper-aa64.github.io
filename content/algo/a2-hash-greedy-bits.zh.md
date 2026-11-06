---
title: "A2（下）：哈希表、排序与贪心、位运算"
date: 2026-11-06
slug: "a2-hash-greedy-bits"
description: "三样各管一件事的工具：哈希表把“有没有、在哪、几次”降到平均 O(1)，用在两数之和、异位词分组、最长连续序列、前缀和计数上；排序把数据排成局部最优一眼可见的顺序，贪心靠交换论证说明对，用在区间调度、合并区间、跳跃游戏、加油站上，外加手写快排和归并数逆序对；位运算把小集合压进一个整数，lowbit、枚举子集、异或找只出现一次的数，以及优先级和移位的坑。附 10 道练习题。"
weight: 3
math: true
toc: true
---
这一半的三样东西各管一件事。**哈希表把“某个值有没有、在哪、出现几次”从扫一遍的 $O(n)$ 降到平均 $O(1)$；排序把数据排成局部最优一眼可见的顺序，贪心再一步步取；位运算把一个小集合压进一个整数，并、交、枚举子集都是一两条指令。**

## 1. 哈希表：查有没有、数几次，平均 O(1)

### 1.1 unordered_map 的用法和坑：`operator[]` 查不到会插入

1. **`unordered_map` 平均 $O(1)$，最坏 $O(n)$**
   - **平均 $O(1)$**：键先算出哈希值，落进一个桶里，桶里一般只有一两个元素，查一次只比较这几个。
   - **最坏 $O(n)$**：所有键都落进同一个桶时，查一次要把桶里的元素挨个比一遍。libstdc++ 的 `std::hash<int>` 就是整数原值，Codeforces 上有人专门造这种数据卡它。
   - **要按顺序遍历、找前驱后继，就用 `map`**：`map` 是红黑树，每样操作 $O(\log n)$。

2. **`operator[]` 查不到时会插入一个默认值**
   - **只想查有没有，用 `find` 或 `count`**：`if (m[x])` 会把 `x` 插进去，表越查越大，遍历时还会多出一堆值为 0 的键。C++20 起也可以用 `contains`。
   - **计数正好利用这一点**：`m[x]++` 查不到时先插入 0 再加 1，一行就是“出现次数加 1”。

3. **键是 `pair` 或结构体时，要自己写哈希**
   - **标准库没给 `pair` 提供哈希**：`unordered_map<pair<int, int>, int>` 直接编译不过。
   - **两个 32 位整数拼成一个 64 位整数再哈希**：

   ```cpp
   struct PairHash {
       size_t operator()(const pair<int, int>& p) const {
           unsigned long long k = (unsigned long long)(unsigned)p.first << 32 | (unsigned)p.second;
           return hash<unsigned long long>()(k);    // 两个 32 位拼成一个 64 位，不同的 pair 不会撞
       }
   };
   unordered_map<pair<int, int>, int, PairHash> mp;
   ```

   - **先转成 `unsigned` 再移位**：负数左移在 C++20 之前是未定义行为，转成无符号以后，高 32 位放 `first`、低 32 位放 `second`，两个不同的 `pair` 一定拼出不同的数。

4. **大概知道要放多少，就先 `reserve`**
   - **扩容会把所有元素重新放一遍**：元素数超过“桶数 × 负载因子”（默认 1）时，桶数大约翻倍，每个元素重新算哈希、换桶。
   - **`m.reserve(n)` 一次开够**：省掉中途的几次重新哈希。
   - **遍历顺序没有保证**：它和插入顺序无关，扩容后还会变，输出要按顺序就先排序。

> **什么时候想到哈希表**
>
> - **要反复问“某个值出现过没有、出现在哪、出现了几次”**：暴力每问一次扫一遍，哈希表每次平均 $O(1)$。
> - **要按某个特征把东西分组**：特征当键，同一组落进同一个桶，比如异位词排序后的字符串。
> - **不需要顺序**：要顺序、前驱后继、区间查询，就换 `map` 或 `set`。

### 1.2 两数之和：边扫边查“另一半见过没有”

[LC 1](https://leetcode.cn/problems/two-sum/)：在数组里找两个下标，对应的数加起来等于 `target`，保证恰好有一个解。$n \le 10^4$。

1. **对每个数，要找的另一半就是 `target - x`**
   - **暴力是两重循环**：$O(n^2)$。
   - **把见过的数存进哈希表**：扫到 `nums[i]`，查 `target - nums[i]` 见过没有，见过就是答案。

   ```cpp
   vector<int> twoSum(vector<int>& nums, int target) {
       unordered_map<int, int> pos;                 // 值 → 下标
       for (int i = 0; i < (int)nums.size(); i++) {
           auto it = pos.find(target - nums[i]);    // 先查再插：不会和自己配对
           if (it != pos.end()) return {it->second, i};
           pos[nums[i]] = i;
       }
       return {};
   }
   ```

   - **先查再插**：`target = 6`、`nums[i] = 3` 时，表里还没有这个 3，就不会把它和自己配成一对。

2. **时间 $O(n)$，空间 $O(n)$**
   - **数组有序时换成两头夹的双指针**：空间降到 $O(1)$（A1 的 3.3）。

### 1.3 字母异位词分组：排好序的字符串当键

[LC 49](https://leetcode.cn/problems/group-anagrams/)：把一组字符串按“字母相同、顺序不同”分组。最多 $10^4$ 个字符串，每个长度不超过 100，只有小写字母。

1. **异位词排好序以后完全相同**
   - **排好序的字符串当键**：`"eat"`、`"tea"`、`"ate"` 都变成 `"aet"`，落进同一组。

   ```cpp
   vector<vector<string>> groupAnagrams(vector<string>& strs) {
       unordered_map<string, vector<string>> groups;
       for (const string& s : strs) {
           string key = s;
           sort(key.begin(), key.end());            // 异位词排序后相同
           groups[key].push_back(s);
       }
       vector<vector<string>> ans;
       for (auto& [k, v] : groups) ans.push_back(std::move(v));
       return ans;
   }
   ```

2. **时间 $O(n \cdot L \log L)$，$L$ 是字符串长度**
   - **键也可以是 26 个字母各出现几次**：把计数拼成一个字符串当键，不用排序，$O(n \cdot L)$，字符串长时更快。

### 1.4 最长连续序列：只从一段的起点往后数

[LC 128](https://leetcode.cn/problems/longest-consecutive-sequence/)：一个无序整数数组，求数值连续（如 1、2、3、4）的最长序列有多长，要求 $O(n)$。$n \le 10^5$。

1. **只从一段的起点开始往后数**
   - **排序能做，但是 $O(n \log n)$**：题目要 $O(n)$。
   - **全部放进哈希集合**：对每个 `x`，`x - 1` 不在集合里，`x` 才是一段的起点，从它往后数 `x + 1`、`x + 2` 在不在。
   - **`x - 1` 在集合里就跳过**：这一段会被它的起点数到。

   ```cpp
   int longestConsecutive(vector<int>& nums) {
       unordered_set<int> st(nums.begin(), nums.end());
       int best = 0;
       for (int x : st) {
           if (st.count(x - 1)) continue;           // 不是一段的起点，跳过
           int y = x;
           while (st.count(y + 1)) y++;
           best = max(best, y - x + 1);
       }
       return best;
   }
   ```

2. **每个数只被往后数到一次，所以是 $O(n)$**
   - **while 只在起点上跑**：每个数只属于一段，只会被这一段的起点数到一次。
   - **遍历集合，不遍历原数组**：原数组里同一个起点重复出现 $n/2$ 次时，每次都把整段数一遍，又退回 $O(n^2)$。

### 1.5 和为 K 的子数组：前缀和加哈希表

[LC 560](https://leetcode.cn/problems/subarray-sum-equals-k/)：数一数和等于 `k` 的连续子数组有几个，元素可以是负数。$n \le 2 \times 10^4$。

1. **子数组的和是两个前缀和之差**
   - **设 $S_i$ 是前 $i$ 个数的和**：子数组 $(l, r]$ 的和是 $S_r - S_l$，它等于 $k$ 当且仅当 $S_l = S_r - k$。
   - **扫到 $r$ 时查表**：前面有几个前缀和等于 $S_r - k$，就有几个以 $r$ 结尾的子数组。
   - **`cnt[0] = 1` 不能漏**：它是空前缀 $S_0 = 0$，对应从开头开始的子数组。

   ```cpp
   int subarraySum(vector<int>& nums, int k) {
       unordered_map<int, int> cnt;                 // 前缀和的值 → 出现次数
       cnt[0] = 1;                                  // 空前缀
       int s = 0, ans = 0;
       for (int x : nums) {
           s += x;
           auto it = cnt.find(s - k);
           if (it != cnt.end()) ans += it->second;
           cnt[s]++;
       }
       return ans;
   }
   ```

2. **时间 $O(n)$，空间 $O(n)$**
   - **有负数，滑动窗口用不了**：窗口和不再随窗口变大而变大（A1 的 4.1）。
   - **和 LC 974 的区别在键的范围**：974 找的是余数相同，余数只有 $k$ 种，开一个数组计数；这里找的是具体的值，值的范围很大，只能用哈希表。

## 2. 排序与贪心：排好序，每步取当前最好的

### 2.1 比较器：必须是严格弱序，写 `<=` 会出错

1. **`sort` 的比较器回答的是“a 是否必须排在 b 前面”**
   - **两个元素相等时必须返回 false**：`cmp(a, a)` 一定要是 false，这是严格弱序的第一条。
   - **写成 `<=` 会出错**：`cmp(a, a)` 变成 true。libstdc++ 的 `std::sort` 内层循环靠比较器给出的边界停下，相等的元素一多，下标会越过数组末尾去读写，常见的表现是段错误。
   - **多个关键字用 `tie` 比**：`return tie(a.x, a.y) < tie(b.x, b.y);` 先比 `x`，相等再比 `y`，不容易写错。

2. **要保持相等元素原来的顺序，用 `stable_sort`**
   - **`sort` 不保证稳定**：相等的元素排完以后先后可能变。
   - **`stable_sort` 保证稳定**：同样 $O(n \log n)$，要多用一块和数组一样大的内存。

### 2.2 贪心为什么对：交换论证

1. **贪心每一步取当前看起来最好的，不回头**
   - **难的是证明它对**：每一步的局部最优，不一定拼得出整体最优。
   - **证明的常用办法是交换论证**：拿一个最优解，在它和贪心解第一处不同的地方，把最优解的选择换成贪心的选择。
   - **只要换完不变差、仍然合法**：最优解就能一步步换成贪心解，贪心解也就是最优的。2.3 是一个完整的例子。

> **什么时候想到贪心**
>
> - **问最多、最少，而且这一步怎么选，不会限制后面还能怎么选**：或者限制能用一个量概括，比如“目前最远能到哪”“油箱里还剩多少”。
> - **排好序以后答案有明显的结构**：按结束时间、按开始时间、按单位价值。
> - **想不出交换论证，或者能举出反例，就换 DP**：硬币面额是 1、3、4 时凑 6，贪心先拿 4，得到 4 + 1 + 1 三枚；最优是 3 + 3 两枚。

### 2.3 区间调度：按右端点排序，能放就放

[LC 435](https://leetcode.cn/problems/non-overlapping-intervals/)：最少删掉几个区间，剩下的就互不重叠。只在端点相碰（如 `[1, 2]` 和 `[2, 3]`）不算重叠。$n \le 10^5$。

1. **删得最少，就是留得最多**
   - **答案 = $n$ − 最多能留下几个互不重叠的区间**。

2. **按右端点从小到大排，和上一个留下的不重叠就留下**

   ```cpp
   int eraseOverlapIntervals(vector<vector<int>>& iv) {
       sort(iv.begin(), iv.end(), [](const vector<int>& a, const vector<int>& b) {
           return a[1] < b[1];                      // 按右端点从小到大
       });
       int kept = 0, end = INT_MIN;
       for (auto& v : iv) {
           if (v[0] >= end) { kept++; end = v[1]; } // 和上一个留下的不重叠，留下
       }
       return (int)iv.size() - kept;
   }
   ```

   - **`end` 是上一个留下的区间的右端点**：新区间的左端点不小于它，就不重叠。

3. **为什么按右端点：它给后面留的空间最多**
   - **交换论证**：设某个最优解的第一个区间是 $A$，右端点最小的区间是 $B$。把 $A$ 换成 $B$，$B$ 结束得不比 $A$ 晚，后面的区间照样和它不重叠，个数不变，所以留下 $B$ 不会吃亏。
   - **按左端点排是错的**：`[1, 10]`、`[2, 3]`、`[4, 5]` 按左端点先拿 `[1, 10]`，后两个都放不下，只留 1 个；按右端点留下 `[2, 3]`、`[4, 5]` 两个。
   - **时间 $O(n \log n)$**：排序占大头，扫一遍是 $O(n)$。

### 2.4 合并区间：按左端点排序，接得上就延长

[LC 56](https://leetcode.cn/problems/merge-intervals/)：把有重叠的区间合并，输出合并后的区间。端点相碰也要合并。$n \le 10^4$。

1. **按左端点排好以后，能合并的区间一定挨着**
   - **接得上就延长**：当前区间的左端点不超过结果里最后一个区间的右端点，就把它并进去。
   - **接不上就另起一段**。

   ```cpp
   vector<vector<int>> merge(vector<vector<int>>& iv) {
       sort(iv.begin(), iv.end());                  // 按左端点
       vector<vector<int>> ans;
       for (auto& v : iv) {
           if (!ans.empty() && v[0] <= ans.back()[1])
               ans.back()[1] = max(ans.back()[1], v[1]);   // 接上了：延长
           else
               ans.push_back(v);
       }
       return ans;
   }
   ```

2. **延长时右端点要取较大的那个**
   - **例子**：`[1, 10]` 后面来了 `[2, 3]`，合并后还是 `[1, 10]`，直接改成 3 就错了。
   - **时间 $O(n \log n)$**。

> **区间题按哪一端排序**
>
> - **选出最多互不重叠的区间、最少用几支箭射爆所有气球（[LC 452](https://leetcode.cn/problems/minimum-number-of-arrows-to-burst-balloons/)）**：按右端点。
> - **合并区间、插入区间、求总共覆盖多长**：按左端点。
> - **同一时刻最多有几个区间重叠（会议室问题）**：把每个区间拆成“开始 +1、结束 −1”两个事件，排序后扫一遍，或者用 A1 的差分。

### 2.5 跳跃游戏：只记“目前最远能到哪”

[LC 55](https://leetcode.cn/problems/jump-game/)：`a[i]` 是在下标 `i` 最多能往前跳几格，问能不能从下标 0 跳到最后一个下标。[LC 45](https://leetcode.cn/problems/jump-game-ii/)：保证能到，问最少跳几次。$n \le 10^4$。

1. **LC 55：从左往右维护目前最远能到的下标**
   - **能到 `i`，就能到 `i` 之前的所有下标**：所以“能到哪些下标”只用一个数 `reach` 概括。
   - **`i` 超过 `reach`，就到不了**。

   ```cpp
   bool canJump(vector<int>& a) {
       int reach = 0;                               // 目前能到的最远下标
       for (int i = 0; i < (int)a.size(); i++) {
           if (i > reach) return false;             // i 到不了
           reach = max(reach, i + a[i]);
       }
       return true;
   }
   ```

2. **LC 45：按“跳几次能到”把下标分层**
   - **跳 0 次能到的只有下标 0**：跳 $k$ 次能到的下标是一段连续的区间，下一层的右端是这一层里每个点能跳到的最远处。
   - **走完这一层的区间，就必须再跳一次**：`curEnd` 是这一层的右端，`farthest` 是下一层的右端。
   - **这就是一层一层的 BFS**（A3），只是每层是一个区间，不用队列。

   ```cpp
   int jump(vector<int>& a) {
       int steps = 0, curEnd = 0, farthest = 0;     // curEnd：当前步数能到的最远处
       for (int i = 0; i + 1 < (int)a.size(); i++) {
           farthest = max(farthest, i + a[i]);
           if (i == curEnd) { steps++; curEnd = farthest; }   // 这一步的范围走完了，必须再跳一次
       }
       return steps;
   }
   ```

   - **循环只到倒数第二个下标**：站在最后一个下标上就不用再跳了。写成 `i < n` 的话，最后一个下标恰好是某层右端时，会多算一跳。
   - **两题都是时间 $O(n)$、空间 $O(1)$**。

### 2.6 加油站：油箱一变负，起点就挪到下一站

[LC 134](https://leetcode.cn/problems/gas-station/)：环形路上有 $n$ 个加油站，在站 `i` 加 `gas[i]` 升油，开到下一站耗 `cost[i]` 升，油箱起初是空的。问从哪一站出发能绕一圈，没有就返回 −1，有解时答案唯一。$n \le 10^5$。

1. **总油量够不够，决定有没有解**
   - **总油量小于总消耗，从哪出发都跑不完**：返回 −1。
   - **总油量不小于总消耗，一定有解**：下一块找出起点。

2. **从 `start` 出发开到 `i` 时油箱变负，`start` 到 `i` 之间都不能当起点**
   - **从中间某站 `j` 出发，到 `j` 时油箱是 0**：而从 `start` 出发到 `j` 时油箱不小于 0（否则早就变负了），从 `j` 开到 `i` 的油量变化一样，起始油还更少，也一定会变负。
   - **所以起点直接挪到 `i + 1`，油箱清零重来**：一遍扫完，$O(n)$。

   ```cpp
   int canCompleteCircuit(vector<int>& gas, vector<int>& cost) {
       int total = 0, tank = 0, start = 0;
       for (int i = 0; i < (int)gas.size(); i++) {
           total += gas[i] - cost[i];
           tank += gas[i] - cost[i];
           if (tank < 0) { start = i + 1; tank = 0; }   // 从 start 到 i 都不能当起点
       }
       return total < 0 ? -1 : start;
   }
   ```

### 2.7 手写快排和归并：归并顺带数逆序对

1. **快排：随机选基准，两头往中间换**

   ```cpp
   void quickSort(vector<int>& a, int l, int r) {   // 排 [l, r]
       if (l >= r) return;
       int pivot = a[l + rand() % (r - l + 1)];     // 随机选基准
       int i = l, j = r;
       while (i <= j) {
           while (a[i] < pivot) i++;
           while (a[j] > pivot) j--;
           if (i <= j) swap(a[i++], a[j--]);
       }
       quickSort(a, l, j);
       quickSort(a, i, r);
   }
   ```

   - **基准要随机选**：固定选第一个的话，有序数组上每次只分出一个元素，退化成 $O(n^2)$。
   - **遇到等于基准的元素，两边都停下来交换**：内层用严格的 `<` 和 `>`，数组全是同一个数时，`i` 和 `j` 每步都停、都交换，最后在中间相遇，照样对半分。
   - **递归 `[l, j]` 和 `[i, r]`**：循环结束时 `j < i`，两者之间夹着的元素都等于基准，已经在最终位置上。
   - **平均 $O(n \log n)$，最坏 $O(n^2)$，原地排序，不稳定。**

2. **归并：拆成两半各自排好，再合并**

   ```cpp
   long long mergeSort(vector<int>& a, vector<int>& tmp, int l, int r) {  // 排 [l, r)，返回逆序对数
       if (r - l <= 1) return 0;
       int m = (l + r) / 2;
       long long inv = mergeSort(a, tmp, l, m) + mergeSort(a, tmp, m, r);
       int i = l, j = m, k = l;
       while (i < m && j < r) {
           if (a[i] <= a[j]) tmp[k++] = a[i++];
           else { inv += m - i; tmp[k++] = a[j++]; }   // a[i..m) 都比 a[j] 大
       }
       while (i < m) tmp[k++] = a[i++];
       while (j < r) tmp[k++] = a[j++];
       copy(tmp.begin() + l, tmp.begin() + r, a.begin() + l);
       return inv;
   }
   ```

   - **合并时顺带数逆序对**：左半的 `a[i]` 大于右半的 `a[j]` 时，左半已经排好序，`a[i..m)` 都比 `a[j]` 大，一次加上 `m - i`。
   - **相等时先取左边（`<=`）**：保证稳定，也不会把相等的两个数算成逆序对。
   - **时间 $O(n \log n)$，稳定，要 $O(n)$ 的额外内存。**

> **用 `std::sort`、`stable_sort`，还是手写**
>
> - **只要排好序**：用 `std::sort`，它是内省排序，以快排为主，递归太深就换堆排序，最坏也是 $O(n \log n)$。
> - **要稳定**：用 `stable_sort`，底下是归并。
> - **面试要手写**：快排写随机基准、两边遇到相等都停；要数逆序对、给链表排序（[LC 148](https://leetcode.cn/problems/sort-list/)），写归并。

## 3. 位运算：把一个小集合压进一个整数

### 3.1 常用操作：lowbit、去掉最低位的 1、popcount

| 写法 | 结果 | 例子：$x = 12 = 1100_2$ |
|---|---|---|
| `x & -x` | 只留最低位的 1（lowbit） | $0100_2 = 4$ |
| `x & (x - 1)` | 去掉最低位的 1 | $1000_2 = 8$ |
| `__builtin_popcount(x)` | 1 的个数 | 2 |
| `__builtin_ctz(x)` | 末尾有几个 0（`x` 不能是 0） | 2 |
| `x >> k & 1` | 第 $k$ 位是几 | $k = 2$ 时是 1 |
| `x \| 1 << k`、`x & ~(1 << k)`、`x ^ 1 << k` | 第 $k$ 位置 1、清 0、翻转 | |

1. **`x & -x` 只留最低位的 1，靠的是补码**
   - **`-x` 等于 `~x + 1`**：`x` 最低位的 1 右边全是 0，取反后变成全 1，加 1 一路进位，正好进到这一位；这一位左边的位都和 `x` 相反，一与就全没了，只剩这一位。
   - **树状数组就靠它跳**（B1）。

2. **`x & (x - 1)` 去掉最低位的 1**
   - **`x - 1` 把最低位的 1 变成 0，右边的 0 全变成 1**：和 `x` 一与，这一段全清零，更高的位不变。
   - **例子：判断 2 的幂**：`x > 0 && (x & (x - 1)) == 0`，2 的幂只有一个 1，去掉就是 0。
   - **数 1 的个数**：反复去掉最低位的 1，循环几次就有几个 1；平时直接用 `__builtin_popcount`，64 位用 `__builtin_popcountll`，C++20 起有 `std::popcount`。

### 3.2 用整数表示集合：枚举子集

1. **$n$ 个元素的每个子集，对应 0 到 $2^n - 1$ 里的一个整数**
   - **第 $i$ 位是 1，表示选了第 $i$ 个元素**。
   - **集合运算都是一条指令**：并是 `a | b`，交是 `a & b`，差是 `a & ~b`，`s` 是 `m` 的子集当且仅当 `(s & m) == s`。
   - **`for (int s = 0; s < (1 << n); s++)` 枚举全部子集**：$n$ 到 20 左右还行，约 $10^6$ 个。

2. **枚举 `m` 的所有子集：`s = (s - 1) & m`**

   ```cpp
   for (int s = m; s; s = (s - 1) & m) {
       // s 依次是 m 的每个非空子集，从大到小
   }
   ```

   - **为什么能一个不漏**：`s - 1` 把 `s` 最低位的 1 变成 0、右边全变成 1，再和 `m` 一与，只留下 `m` 里有的位，正好是 `m` 的子集里比 `s` 小的下一个。
   - **例子**：$m = 1011_2$ 依次得到 $1011_2$、$1010_2$、$1001_2$、$1000_2$、$0011_2$、$0010_2$、$0001_2$，共 7 个。
   - **空集不在里面**：`s` 变成 0 循环就停了，要空集就单独处理。
   - **对每个 `m` 都枚举一遍子集，总共是 $3^n$**：每个元素有三种状态（不在 `m` 里、在 `m` 里不在 `s` 里、在 `s` 里），状压 DP 里常见，$n$ 到 15 左右。

### 3.3 异或：成对的抵消，找只出现一次的数

1. **异或的三条性质让顺序无所谓**
   - **$x \oplus x = 0$，$x \oplus 0 = x$**：同一个数异或两次就消掉了。
   - **满足交换律和结合律**：一串数怎么排、怎么分组异或，结果都一样。

2. **LC 136：其余每个数都出现两次，找只出现一次的那个**
   - **全部异或起来**：成对的抵消成 0，剩下的就是答案。时间 $O(n)$，额外空间 $O(1)$。

   ```cpp
   int singleNumber(vector<int>& a) {
       int x = 0;
       for (int v : a) x ^= v;                      // 成对的抵消成 0
       return x;
   }
   ```

3. **LC 260：有两个数只出现一次，记作 $p$、$q$**
   - **全部异或得到 $p \oplus q$**：$p \ne q$，所以它不是 0。
   - **取它最低位的 1**：$p$ 和 $q$ 在这一位上一个是 0、一个是 1。
   - **按这一位把所有数分成两组**：成对的数落在同一组里抵消，$p$ 和 $q$ 各落一组，两组分别异或，各剩一个。

   ```cpp
   vector<int> singleNumberIII(vector<int>& a) {
       unsigned x = 0;
       for (int v : a) x ^= v;                      // x = p ^ q，p != q，所以 x != 0
       unsigned low = x & -x;                       // p 和 q 在这一位上不同
       int p = 0, q = 0;
       for (int v : a) {
           if (v & low) p ^= v; else q ^= v;        // 按这一位分两组，各剩一个
       }
       return {p, q};
   }
   ```

   - **lowbit 要用 `unsigned` 算**：$p \oplus q$ 恰好只有最高位是 1 时，它作为 `int` 是 `INT_MIN`，`-x` 溢出，是未定义行为。

> **什么时候想到位运算**
>
> - **$n$ 不超过 20 左右，要枚举子集，或者状态是“哪些已经用过了”**：用整数表示集合，这就是状压（A5）。
> - **要 $O(1)$ 额外空间找出现奇数次的数**：异或。
> - **要判断 2 的幂、数 1 的个数、找最低位的 1**：用 3.1 那几招。

### 3.4 位运算的坑：优先级、移位溢出、有符号右移

1. **`&`、`|`、`^` 的优先级比 `==` 低**
   - **`x & 1 == 0` 实际算的是 `x & (1 == 0)`**：结果永远是 0，要写成 `(x & 1) == 0`。
   - **`<<` 比 `+`、`-` 低**：`1 << n - 1` 是 `1 << (n - 1)`，拿不准就加括号。

2. **`1 << 31` 会溢出，`1 << 40` 不会自动变成 64 位**
   - **字面量 `1` 是 `int`**：`1 << 31` 移进了符号位，C++20 之前是未定义行为（C++20 起结果是 `INT_MIN`）；移 32 位及以上永远是未定义行为。
   - **要 64 位就写 `1LL << k`**：左边的类型决定结果的类型，和赋给谁无关。

3. **负数右移补的是符号位**
   - **`-8 >> 1` 是 −4**：主流编译器对有符号数做算术右移，C++20 起标准也这样规定。
   - **右移和除法在负数上不一样**：`-1 >> 1` 是 −1（向下取整），`-1 / 2` 是 0（向 0 取整），不能互换。
   - **把整数当位集合用时，用 `unsigned`**：右移补 0，也不会碰到符号位的溢出。

## 练习

每题后面一句话提示练的是哪一节。

**必做**

1. [LeetCode 560 和为 K 的子数组](https://leetcode.cn/problems/subarray-sum-equals-k/)：1.5，前缀和加哈希表，`cnt[0] = 1`。
2. [LeetCode 128 最长连续序列](https://leetcode.cn/problems/longest-consecutive-sequence/)：1.4，只从起点往后数，遍历集合。
3. [LeetCode 435 无重叠区间](https://leetcode.cn/problems/non-overlapping-intervals/)：2.3，按右端点排序，说得出交换论证。
4. [LeetCode 56 合并区间](https://leetcode.cn/problems/merge-intervals/)：2.4，按左端点排序，延长时取较大的。
5. [LeetCode 45 跳跃游戏 II](https://leetcode.cn/problems/jump-game-ii/)：2.5，按层走，循环到倒数第二个。

**选做**

6. [LeetCode 49 字母异位词分组](https://leetcode.cn/problems/group-anagrams/)：1.3，排好序的字符串当键。
7. [LeetCode 134 加油站](https://leetcode.cn/problems/gas-station/)：2.6，油箱一变负，起点挪到下一站。
8. [LeetCode 260 只出现一次的数字 III](https://leetcode.cn/problems/single-number-iii/)：3.3，按最低位的 1 分组。
9. [LeetCode 78 子集](https://leetcode.cn/problems/subsets/)：3.2，0 到 $2^n - 1$ 每个整数就是一个子集。
10. [LeetCode 148 排序链表](https://leetcode.cn/problems/sort-list/)：2.7，链表上写归并。

## 和地图上其他格子的连接

- 1.5 的“前缀和加哈希表”，A6 的字符串哈希还会再用：把子串变成一个数，放进哈希表里比较。
- 2.5 的按层走，就是 A3 的 BFS 每层是一段连续下标时的样子。
- 3.2 的枚举子集是 A5 状压 DP 的基础；3.1 的 lowbit 是 B1 树状数组的基础。
- 交换论证在 L2 线性基的带权贪心里也会用到：证明“按权从大到小插入”拿到的就是最优的那组。
