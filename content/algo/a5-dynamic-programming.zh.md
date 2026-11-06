---
title: "A5：动态规划：线性、背包、区间、树形、状压"
date: 2026-11-06
slug: "a5-dynamic-programming"
description: "动态规划先写清楚状态的含义，再写转移、边界、计算顺序和答案在哪；从记忆化搜索改成递推。线性 DP（打家劫舍、最长递增子序列和 tails 数组、最长公共子序列、编辑距离、买卖股票的状态机）、背包（0-1 倒序、完全背包正序、零钱兑换的最少个数和组合数、分割等和子集）、区间 DP（按长度从小到大，戳气球枚举最后一个）、树形 DP（每个节点返回选和不选两个值）、状压 DP（n 在 20 以内，dp[mask][i]）。附 9 道练习题。"
weight: 6
math: true
toc: true
---
动态规划（DP）解的是“一个大问题能拆成同样形状的小问题，而且小问题会被反复用到”的题：

- **状态是一个小问题的名字**：比如“前 $i$ 间房子能偷到的最大值”，写下来就是 $f_i$。
- **转移是大问题怎么由小问题拼出来**：比如 $f_i$ 由 $f_{i-1}$ 和 $f_{i-2}$ 算出。
- **每个状态只算一次**：算过的存下来，后面直接取，这是 DP 比暴力搜索快的全部原因。

**DP 题难在定状态，不在写代码**：状态的含义一旦写清楚，转移、边界、计算顺序基本都是顺着推出来的。下面每道题都先写状态的含义。

## 1. 怎么想 DP：先写清楚状态的含义

### 1.1 从记忆化搜索到递推：同一个子问题只算一次

1. **题目：不能偷相邻的两间房，最多偷多少**
   - **题意**：[LC 198 打家劫舍](https://leetcode.cn/problems/house-robber/)，一排房子各有一笔钱 $a_i$，相邻的两间不能都偷，求最多能偷多少。$n \le 100$。
   - **暴力是枚举每间偷不偷**：$2^n$ 种，$n = 100$ 时算不完。

2. **先写成递归：看最后一间偷不偷**
   - **状态**：$f_i$ 表示前 $i$ 间房子能偷到的最大值。
   - **最后一间不偷**：前 $i - 1$ 间随意，就是 $f_{i-1}$。
   - **最后一间偷**：第 $i - 1$ 间就不能偷，前 $i - 2$ 间随意，就是 $f_{i-2} + a_i$。

   $$f_i = \max(f_{i-1},\ f_{i-2} + a_i), \qquad f_0 = 0,\ f_{-1} = 0$$

   - **直接递归会重复算**：$f_5$ 要 $f_4$ 和 $f_3$，$f_4$ 又要 $f_3$，$f_3$ 被算两遍，越往下重复得越多，总共是指数级。

3. **加一个备忘录：算过的直接拿，就是记忆化搜索**

   ```cpp
   vector<int> A_, memo_;
   int go(int i) {                                // 前 i 间房子能偷到的最大值
       if (i <= 0) return 0;
       if (memo_[i] != -1) return memo_[i];       // 算过就直接拿
       return memo_[i] = max(go(i - 1),           // 第 i 间不偷
                             go(i - 2) + A_[i - 1]);  // 第 i 间偷：第 i-1 间就不能偷
   }
   ```

   - **每个 $i$ 只真正算一次**：一共 $n$ 个状态，每个 $O(1)$，总共 $O(n)$。
   - **记忆化搜索的好处是不用想计算顺序**：递归自己会先去算它依赖的状态。

4. **把递归倒过来，从小到大填表，就是递推**

   ```cpp
   int robArr(vector<int>& a) {
       int n = a.size();
       vector<int> f(n + 1, 0);                   // f[i]：前 i 间房子能偷到的最大值
       for (int i = 1; i <= n; i++)
           f[i] = max(f[i - 1], (i >= 2 ? f[i - 2] : 0) + a[i - 1]);
       return f[n];
   }
   ```

   - **计算顺序要保证用到的状态已经算好**：$f_i$ 只用到 $f_{i-1}$ 和 $f_{i-2}$，所以 $i$ 从小到大填。
   - **递推没有递归的函数调用开销，也不怕递归太深爆栈**：$n$ 到 $10^5$ 以上时，记忆化搜索的递归深度可能超过栈的大小。

5. **只用到前两个状态，就只存两个变量**

   ```cpp
   int rob(vector<int>& a) {                      // LC 198
       int take = 0, skip = 0;                    // 到上一间为止：上一间偷了 / 没偷的最大值
       for (int x : a) {
           int nt = skip + x;                     // 这一间偷：上一间必须没偷
           int ns = max(take, skip);              // 这一间不偷：上一间随意
           take = nt, skip = ns;
       }
       return max(take, skip);
   }
   ```

   - **这是另一种状态的写法**：按“这一间偷没偷”分成两个状态，转移里直接写出“偷了的下一间不能偷”，和上面的 $f_i$ 等价。
   - **空间从 $O(n)$ 降到 $O(1)$**：叫滚动数组，前提是转移只用到最近的几个状态。

> **写 DP 的五步**
>
> - **第 1 步，写清楚状态的含义**：用一句话说 $f_i$ 或 $f_{i,j}$ 是什么，包括下标从 0 还是 1 开始、“前 $i$ 个”还是“以第 $i$ 个结尾”。
> - **第 2 步，写转移**：看最后一步有几种做法（最后一间偷不偷、最后一个字符怎么处理、最后一件物品选不选），每种做法对应一个更小的状态。
> - **第 3 步，写边界**：最小的状态直接给值，比如 $f_0 = 0$；求最小值时，凑不出来的状态设成无穷大。
> - **第 4 步，定计算顺序**：每个状态用到的状态都要先算好，一般是下标从小到大，区间 DP 按长度从小到大。
> - **第 5 步，找答案在哪**：是 $f_n$，还是所有 $f_i$ 里最大的那个，还是最后几个状态取最值。

## 2. 线性 DP：状态是“前 i 个”或“以第 i 个结尾”

### 2.1 最长递增子序列：以第 i 个结尾，或者每个长度的最小结尾

1. **题目：最长的严格递增子序列有多长**
   - **题意**：[LC 300](https://leetcode.cn/problems/longest-increasing-subsequence/)，给一个整数数组，求最长严格递增子序列的长度。子序列可以不连续，但顺序不变。$n \le 2500$。
   - **例子**：`[10, 9, 2, 5, 3, 7, 101, 18]` 的答案是 4，比如 `[2, 3, 7, 101]`。

2. **$O(n^2)$ 写法：状态是“以第 $i$ 个结尾”**
   - **状态**：$f_i$ 表示以 $a_i$ 结尾的最长严格递增子序列的长度。
   - **转移**：$a_i$ 前面接的是哪个数？枚举所有 $j < i$ 且 $a_j < a_i$，接在以 $a_j$ 结尾的那条后面。

   $$f_i = 1 + \max_{j < i,\ a_j < a_i} f_j$$

   ```cpp
   int lengthOfLIS_n2(vector<int>& a) {           // LC 300，O(n^2)
       int n = a.size(), best = 0;
       vector<int> f(n, 1);                       // f[i]：以 a[i] 结尾的最长严格递增子序列长度
       for (int i = 0; i < n; i++) {
           for (int j = 0; j < i; j++)
               if (a[j] < a[i]) f[i] = max(f[i], f[j] + 1);
           best = max(best, f[i]);
       }
       return best;
   }
   ```

   - **没有这样的 $j$ 时 $f_i = 1$**：$a_i$ 自己单独成一条。
   - **为什么要“以第 $i$ 个结尾”**：接下一个数时要和上一个数比大小，状态里必须知道最后一个数是谁。“前 $i$ 个里最长的”不知道结尾，转移写不出来。
   - **答案不是 $f_{n-1}$，而是所有 $f_i$ 的最大值**：最长的那条不一定以最后一个数结尾。

3. **$O(n \log n)$ 写法：每个长度只留最小的结尾**
   - **状态换了一种**：`tails[k]` 表示所有长度为 $k + 1$ 的递增子序列里，最小的那个结尾。
   - **结尾越小越好**：同样长度的两条，结尾小的那条后面能接的数更多，结尾大的那条可以扔掉。
   - **`tails` 一定是严格递增的**：长度为 $k + 1$ 的那条，去掉最后一个数就是一条长度为 $k$ 的，它的结尾更小，所以 `tails[k-1] < tails[k]`。
   - **新来一个 $x$，二分找第一个 $\ge x$ 的位置**：找不到说明 $x$ 比所有结尾都大，能接出一条更长的，放到末尾；找到了就用 $x$ 替换它，那个长度的最小结尾变小了。

   ```cpp
   int lengthOfLIS(vector<int>& a) {              // LC 300，O(n log n)
       vector<int> tails;                         // tails[k]：长度为 k+1 的递增子序列里，最小的结尾
       for (int x : a) {
           auto it = lower_bound(tails.begin(), tails.end(), x);   // 第一个 >= x 的位置
           if (it == tails.end()) tails.push_back(x);              // 比所有结尾都大：接出更长的
           else *it = x;                                           // 否则让这个长度的结尾变小
       }
       return tails.size();
   }
   ```

   - **答案是 `tails` 的长度，但 `tails` 本身不一定是一条真的子序列**：例子里最后 `tails = [2, 3, 7, 18]`，碰巧是一条；输入 `[3, 4, 1]` 时 `tails = [1, 4]`，1 在 4 后面，不是子序列，长度 2 却是对的。
   - **严格递增用 `lower_bound`，不下降用 `upper_bound`**：相等的数在严格递增里不能接，要替换掉同样大的那个结尾；不下降时可以接，要找第一个 $> x$ 的。

### 2.2 最长公共子序列：两个串各取一个前缀

1. **题目：两个字符串最长的公共子序列**
   - **题意**：[LC 1143](https://leetcode.cn/problems/longest-common-subsequence/)，求两个字符串最长公共子序列的长度。长度都 $\le 1000$。
   - **例子**：`"abcde"` 和 `"ace"` 的答案是 3。

2. **状态：两个串各取一个前缀**
   - **状态**：$f_{i,j}$ 表示 $a$ 的前 $i$ 个字符和 $b$ 的前 $j$ 个字符的最长公共子序列长度。
   - **看两个前缀的最后一个字符**：相等就一起用上；不相等，至少有一个用不上，扔掉其中一个，取较大的。

   $$f_{i,j} = \begin{cases} f_{i-1,j-1} + 1 & a_i = b_j \\ \max(f_{i-1,j},\ f_{i,j-1}) & a_i \ne b_j \end{cases}$$

   ```cpp
   int longestCommonSubsequence(string a, string b) {   // LC 1143
       int n = a.size(), m = b.size();
       vector<vector<int>> f(n + 1, vector<int>(m + 1, 0));   // f[i][j]：a 前 i 个、b 前 j 个的 LCS
       for (int i = 1; i <= n; i++)
           for (int j = 1; j <= m; j++)
               f[i][j] = a[i - 1] == b[j - 1] ? f[i - 1][j - 1] + 1
                                              : max(f[i - 1][j], f[i][j - 1]);
       return f[n][m];
   }
   ```

   - **下标从 1 开始，第 0 行、第 0 列就是空串的边界**：空串和谁的公共子序列都是 0，不用单独处理。
   - **复杂度**：时间、空间都是 $O(nm)$。只要长度时可以只留两行。

### 2.3 编辑距离：最后一步是哪种操作

1. **题目：把一个串改成另一个串最少要几步**
   - **题意**：[LC 72](https://leetcode.cn/problems/edit-distance/)，每步可以插入、删除或替换一个字符，求把 $a$ 变成 $b$ 的最少步数。长度都 $\le 500$。
   - **例子**：`"horse"` 变成 `"ros"` 要 3 步。

2. **状态和 LCS 一样取两个前缀，转移看最后一步做了什么**
   - **状态**：$f_{i,j}$ 表示把 $a$ 的前 $i$ 个字符变成 $b$ 的前 $j$ 个字符的最少步数。
   - **最后一个字符相等**：不用动它，$f_{i,j} = f_{i-1,j-1}$。
   - **不相等时有三种最后一步**：把 $a_i$ 替换成 $b_j$，来自 $f_{i-1,j-1}$；删掉 $a_i$，来自 $f_{i-1,j}$；在末尾插入 $b_j$，来自 $f_{i,j-1}$。

   $$f_{i,j} = \begin{cases} f_{i-1,j-1} & a_i = b_j \\ 1 + \min(f_{i-1,j-1},\ f_{i-1,j},\ f_{i,j-1}) & a_i \ne b_j \end{cases}$$

   ```cpp
   int minDistance(string a, string b) {          // LC 72
       int n = a.size(), m = b.size();
       vector<vector<int>> f(n + 1, vector<int>(m + 1));      // f[i][j]：a 前 i 个变成 b 前 j 个的最少操作
       for (int i = 0; i <= n; i++) f[i][0] = i;              // 删光
       for (int j = 0; j <= m; j++) f[0][j] = j;              // 全插入
       for (int i = 1; i <= n; i++)
           for (int j = 1; j <= m; j++) {
               if (a[i - 1] == b[j - 1]) f[i][j] = f[i - 1][j - 1];
               else f[i][j] = 1 + min({f[i - 1][j - 1],       // 替换
                                       f[i - 1][j],           // 删掉 a[i-1]
                                       f[i][j - 1]});         // 插入 b[j-1]
           }
       return f[n][m];
   }
   ```

   - **边界和 LCS 不同，要单独写**：前 $i$ 个变成空串要删 $i$ 次，空串变成前 $j$ 个要插 $j$ 次。
   - **两个串的题，状态几乎总是“各取一个前缀”**：LCS、编辑距离、通配符匹配、正则匹配都是这个形状，区别只在最后一个字符怎么处理。

### 2.4 买卖股票：每天结束时处在哪个状态

1. **题目：带冷冻期的股票买卖，最多赚多少**
   - **题意**：[LC 309](https://leetcode.cn/problems/best-time-to-buy-and-sell-stock-with-cooldown/)，给每天的股价，可以买卖多次，但手里最多一股；卖出的第二天不能买（冷冻期）。$n \le 5000$。
   - **例子**：`[1, 2, 3, 0, 2]` 的答案是 3：第 1 天买、第 2 天卖、第 3 天冷冻、第 4 天买、第 5 天卖。

2. **把“手里有没有股票、能不能买”写成状态机**
   - **状态**：每天结束时处在三种状态之一。`hold` 是手里有一股；`sold` 是今天刚卖掉；`rest` 是空仓、明天可以买。每个状态存“到今天为止、处在这个状态时的最大利润”。
   - **转移就是状态机的边**：
     - **`hold`**：昨天就持有，今天不动；或者昨天是 `rest`，今天买。
     - **`sold`**：昨天持有，今天卖。
     - **`rest`**：昨天就是 `rest`；或者昨天刚卖，今天冷冻期结束。

   $$\begin{aligned} \text{hold}' &= \max(\text{hold},\ \text{rest} - p) \\ \text{sold}' &= \text{hold} + p \\ \text{rest}' &= \max(\text{rest},\ \text{sold}) \end{aligned}$$

   ```cpp
   int maxProfitCooldown(vector<int>& p) {        // LC 309
       int hold = INT_MIN / 2, sold = INT_MIN / 2, rest = 0;  // 当天结束时：持有 / 今天刚卖 / 空仓且可买
       for (int x : p) {
           int nh = max(hold, rest - x);          // 继续持有，或今天买（只能从可买状态买）
           int ns = hold + x;                     // 今天卖
           int nr = max(rest, sold);              // 继续空仓，或昨天卖的冷冻期结束
           hold = nh, sold = ns, rest = nr;
       }
       return max(sold, rest);
   }
   ```

   - **冷冻期落在“只能从 `rest` 买”这一条上**：`sold` 不能直接转到 `hold`，必须先过一天变成 `rest`。
   - **开始时不可能持有，初值设成很小的负数**：用 `INT_MIN / 2` 而不是 `INT_MIN`，因为 `hold + x` 会溢出。
   - **三个新值要用旧值算**：先算出 `nh`、`ns`、`nr` 再一起赋值，不然 `sold` 会用到今天刚更新的 `hold`。

3. **其他几道股票题只是状态机的边不同**
   - **[LC 122](https://leetcode.cn/problems/best-time-to-buy-and-sell-stock-ii/) 不限次数、没有冷冻期**：只要 `hold` 和 `cash` 两个状态，卖了当天就能再买。
   - **[LC 121](https://leetcode.cn/problems/best-time-to-buy-and-sell-stock/) 只能买卖一次**：买入那条边只能从“还没交易过”的状态出发，等价于维护到今天为止的最低价。
   - **限 $k$ 次交易**：状态里加一维“已经买了几次”，$\text{hold}_k$ 和 $\text{cash}_k$。
   - **有手续费**：卖出那条边减去手续费。

> **认出线性 DP**
>
> - **问“最长 / 最大 / 方案数”，而且答案和顺序有关**：子序列、子数组、一排房子、一串天数，状态通常是“前 $i$ 个”或“以第 $i$ 个结尾”。
> - **转移要知道最后一个元素是谁**：用“以第 $i$ 个结尾”，答案取所有状态的最值。
> - **两个串比较**：状态是“各取一个前缀”，$f_{i,j}$，看两个最后字符。
> - **每一步有几种身份可切换**（持有 / 空仓、偷了 / 没偷）：画状态机，每个状态一个变量，边就是转移。

## 3. 背包：每件物品选还是不选

### 3.1 0-1 背包：一维数组为什么要倒序

1. **题目：容量有限，每件最多拿一次，价值最大是多少**
   - **题意**：$m$ 件物品，第 $i$ 件重 $w_i$、价值 $v_i$，背包容量 $W$，每件最多拿一次，求最大总价值。
   - **状态**：$f_{i,c}$ 表示只考虑前 $i$ 件、容量为 $c$ 时的最大价值。
   - **转移看第 $i$ 件拿不拿**：不拿就是 $f_{i-1,c}$；拿就是 $f_{i-1,c-w_i} + v_i$。

   $$f_{i,c} = \max(f_{i-1,c},\ f_{i-1,c-w_i} + v_i)$$

2. **压成一维时，容量要从大到小遍历**

   ```cpp
   int knap01(vector<int>& w, vector<int>& v, int W) {
       vector<int> f(W + 1, 0);                   // f[c]：容量 c 时的最大价值
       for (size_t i = 0; i < w.size(); i++)
           for (int c = W; c >= w[i]; c--)        // 倒序：f[c - w[i]] 还是上一件物品时的值
               f[c] = max(f[c], f[c - w[i]] + v[i]);
       return f[W];
   }
   ```

   - **一维数组里同时住着两行**：更新第 $i$ 件时，已经更新过的位置是 $f_{i,\cdot}$，还没更新的位置是 $f_{i-1,\cdot}$。
   - **转移要的是上一行的 $f_{i-1,c-w_i}$**：$c - w_i$ 比 $c$ 小，倒序遍历时它还没被这一轮改过，拿到的正是上一行的值。
   - **正序会让同一件物品被拿多次**：正序时 $f_{c-w_i}$ 已经是这一轮的值，可能已经拿过第 $i$ 件，再拿一次就成了完全背包。

### 3.2 完全背包：正序，同一件可以再拿

1. **每件物品可以拿任意多次，只把循环方向改成正序**

   ```cpp
   int knapComplete(vector<int>& w, vector<int>& v, int W) {
       vector<int> f(W + 1, 0);
       for (size_t i = 0; i < w.size(); i++)
           for (int c = w[i]; c <= W; c++)        // 正序：f[c - w[i]] 可能已经用过这件，正好表示可以再拿
               f[c] = max(f[c], f[c - w[i]] + v[i]);
       return f[W];
   }
   ```

   - **转移变成用这一行的值**：$f_{i,c} = \max(f_{i-1,c},\ f_{i,c-w_i} + v_i)$。拿了一件第 $i$ 件以后，剩下的容量里还可以接着拿第 $i$ 件。
   - **0-1 和完全背包只差循环方向，这一点面试最常问**：倒序每件最多一次，正序每件不限次数。

### 3.3 零钱兑换：最少个数和组合数，循环顺序不同

1. **题目：凑出一个金额最少要几枚硬币**
   - **题意**：[LC 322](https://leetcode.cn/problems/coin-change/)，每种面值的硬币不限数量，求凑出 `amount` 的最少硬币数，凑不出返回 -1。`amount` $\le 10^4$。
   - **状态**：$f_a$ 表示凑出金额 $a$ 的最少硬币数。
   - **转移看最后一枚是哪种面值**：$f_a = 1 + \min_{c \le a} f_{a-c}$。

   ```cpp
   int coinChange(vector<int>& coins, int amount) {   // LC 322
       const int INF = INT_MAX / 2;
       vector<int> f(amount + 1, INF);            // f[a]：凑出 a 的最少硬币数
       f[0] = 0;
       for (int a = 1; a <= amount; a++)
           for (int c : coins)
               if (c <= a) f[a] = min(f[a], f[a - c] + 1);
       return f[amount] >= INF ? -1 : f[amount];
   }
   ```

   - **凑不出的金额设成无穷大**：用 `INT_MAX / 2`，`f[a - c] + 1` 不会溢出。
   - **这里两层循环谁在外面都行**：求的是最少个数，同一组硬币按什么顺序数都不影响最小值。

2. **题目：凑出一个金额有多少种组合**
   - **题意**：[LC 518 零钱兑换 II](https://leetcode.cn/problems/coin-change-ii/)，求凑出 `amount` 的组合数，`1 + 2` 和 `2 + 1` 算同一种。
   - **状态**：$f_a$ 表示凑出金额 $a$ 的组合数，$f_0 = 1$（什么都不拿是一种）。

   ```cpp
   int change(int amount, vector<int>& coins) {   // LC 518
       vector<unsigned long long> f(amount + 1, 0);   // f[a]：凑出 a 的组合数
       f[0] = 1;
       for (int c : coins)                        // 先枚举硬币：每种组合只按硬币顺序数一次
           for (int a = c; a <= amount; a++)
               f[a] += f[a - c];
       return (int)f[amount];
   }
   ```

   - **外层枚举硬币，数出来的是组合数**：处理第 $k$ 种硬币时，$f$ 里只有前 $k - 1$ 种硬币组成的方案。每种组合都是按硬币的先后顺序一种一种加进来的，只会被数一次。
   - **外层枚举金额，数出来的是排列数**：每个金额都会把所有面值试一遍作为“最后一枚”，`1 + 2` 和 `2 + 1` 的最后一枚不同，被数成两种。
   - **例子**：`amount = 5`、`coins = [1, 2, 5]`，外层枚举硬币得 4，外层枚举金额得 9。

### 3.4 分割等和子集：能不能凑出总和的一半

1. **题目：数组能不能分成和相等的两份**
   - **题意**：[LC 416](https://leetcode.cn/problems/partition-equal-subset-sum/)，每个数是正整数，问能不能分成两个子集，和相等。$n \le 200$，每个数 $\le 100$。
   - **换成背包**：总和是奇数就不行；是偶数时，问的就是能不能选出一些数，和恰好是总和的一半。每个数只能用一次，是 0-1 背包。

   ```cpp
   bool canPartition(vector<int>& a) {            // LC 416
       int s = accumulate(a.begin(), a.end(), 0);
       if (s % 2) return false;
       int t = s / 2;
       vector<char> f(t + 1, 0);                  // f[c]：能不能选出和恰好为 c 的子集
       f[0] = 1;
       for (int x : a)
           for (int c = t; c >= x; c--)           // 每个数只能用一次：倒序
               f[c] = f[c] || f[c - x];
       return f[t];
   }
   ```

   - **状态从“最大价值”换成“能不能恰好凑出”**：转移的 $\max$ 换成“或”，形状和 0-1 背包一样。
   - **复杂度**：$O(n \cdot t)$，$t$ 最大 $10^4$，一共 $2 \times 10^6$ 次。

> **认出背包**
>
> - **有一组物品，每件选或不选，受一个总量限制**（容量、金额、和）：0-1 背包，一维倒序。
> - **每件可以选任意多次**：完全背包，一维正序。
> - **问“恰好凑出”**：状态是“能不能”或“几种”，$f_0 = 1$；问“不超过”，$f$ 全初始化成 0。
> - **数方案时先想清楚顺序算不算不同**：算同一种是组合，外层物品；算不同是排列，外层金额。

## 4. 区间 DP：按区间长度从小到大算

### 4.1 最长回文子序列：看区间两端相不相等

1. **题目：一个字符串里最长的回文子序列**
   - **题意**：[LC 516](https://leetcode.cn/problems/longest-palindromic-subsequence/)，求最长回文子序列的长度。长度 $\le 1000$。
   - **例子**：`"bbbab"` 的答案是 4（`"bbbb"`）。

2. **状态是一个区间，转移看两端**
   - **状态**：$f_{l,r}$ 表示 $s_l \dots s_r$ 里最长回文子序列的长度。
   - **两端相等**：两端都能用上，夹住里面的，$f_{l,r} = f_{l+1,r-1} + 2$。
   - **两端不相等**：至少有一端用不上，$f_{l,r} = \max(f_{l+1,r},\ f_{l,r-1})$。

   ```cpp
   int longestPalindromeSubseq(string s) {        // LC 516
       int n = s.size();
       vector<vector<int>> f(n, vector<int>(n, 0));   // f[l][r]：s[l..r] 里最长回文子序列
       for (int i = 0; i < n; i++) f[i][i] = 1;
       for (int len = 2; len <= n; len++)         // 按长度从小到大：用到的都是更短的区间
           for (int l = 0; l + len - 1 < n; l++) {
               int r = l + len - 1;
               if (s[l] == s[r]) f[l][r] = (len == 2 ? 0 : f[l + 1][r - 1]) + 2;
               else f[l][r] = max(f[l + 1][r], f[l][r - 1]);
           }
       return n ? f[0][n - 1] : 0;
   }
   ```

   - **计算顺序按长度，不按 $l$ 从小到大**：$f_{l,r}$ 用到的 $f_{l+1,r}$ 的左端点更大。$l$ 从小到大算时它还没算好；按长度算时，更短的区间都已经算完了。
   - **长度为 2 时里面是空区间**：两端相等就是 2，单独处理。

### 4.2 戳气球：枚举最后一个戳的

1. **题目：戳破所有气球，得分最多是多少**
   - **题意**：[LC 312](https://leetcode.cn/problems/burst-balloons/)，戳破第 $k$ 个气球得 $a_{\text{左邻}} \times a_k \times a_{\text{右邻}}$ 分，左右邻是当时还没破的气球，两头外面当成 1。$n \le 300$。
   - **例子**：`[3, 1, 5, 8]` 的答案是 167。

2. **枚举区间里最后一个戳的，而不是第一个**
   - **枚举第一个戳的不行**：戳掉一个以后，它左右两边变成了邻居，两个子问题互相影响，拆不开。
   - **枚举最后一个戳的就拆开了**：设 $k$ 是开区间 $(l, r)$ 里最后一个戳的，戳它时 $(l, r)$ 里只剩它自己，左右邻正好是 $a_l$ 和 $a_r$；在它之前，$(l, k)$ 和 $(k, r)$ 两边各戳各的，互不影响。
   - **状态**：$f_{l,r}$ 表示把开区间 $(l, r)$ 里的气球全戳完的最大得分，两头补上 1。

   $$f_{l,r} = \max_{l < k < r} \left( f_{l,k} + f_{k,r} + a_l \cdot a_k \cdot a_r \right)$$

   ```cpp
   int maxCoins(vector<int>& nums) {              // LC 312
       vector<int> a{1};
       for (int x : nums) a.push_back(x);
       a.push_back(1);
       int n = a.size();
       vector<vector<int>> f(n, vector<int>(n, 0));   // f[l][r]：开区间 (l, r) 里的气球全戳完的最大得分
       for (int len = 2; len < n; len++)
           for (int l = 0; l + len < n; l++) {
               int r = l + len;
               for (int k = l + 1; k < r; k++)    // k 是 (l, r) 里最后一个戳的
                   f[l][r] = max(f[l][r], f[l][k] + f[k][r] + a[l] * a[k] * a[r]);
           }
       return f[0][n - 1];
   }
   ```

   - **复杂度**：$O(n^3)$，$n = 300$ 时约 $4.5 \times 10^6$ 次。
   - **区间 DP 的关键是找一个“切点”，让两边的子问题互不影响**：这道题的切点是最后一个戳的，石子合并是最后一次合并的位置。

> **认出区间 DP**
>
> - **问题在一段区间上，答案由更短的区间拼出来**：回文、括号、合并石子、戳气球。
> - **数据范围 $n$ 在 500 以内**：状态 $O(n^2)$，转移枚举切点 $O(n)$，总共 $O(n^3)$。
> - **计算顺序按长度从小到大**：保证用到的区间都更短。
> - **找不到能把区间拆开的切点时，换成“最后一步”去想**：最后一个戳的、最后一次合并。

## 5. 树形 DP：每个节点向上返回几种情况

### 5.1 打家劫舍 III：每个节点返回选和不选两个值

1. **题目：房子排成一棵二叉树，父子不能都偷**
   - **题意**：[LC 337](https://leetcode.cn/problems/house-robber-iii/)，每个节点有一笔钱，直接相连的父子两个节点不能都偷，求最多能偷多少。节点数 $\le 10^4$。

2. **状态挂在节点上，按选不选分成两个**
   - **状态**：对每个节点 $t$，算两个值。$\text{sel}_t$ 是偷 $t$ 时、$t$ 这棵子树能偷到的最大值；$\text{no}_t$ 是不偷 $t$ 时的最大值。
   - **偷 $t$**：两个孩子都不能偷。
   - **不偷 $t$**：每个孩子偷不偷都行，各自取较大的。

   $$\text{sel}_t = v_t + \text{no}_L + \text{no}_R, \qquad \text{no}_t = \max(\text{sel}_L, \text{no}_L) + \max(\text{sel}_R, \text{no}_R)$$

   ```cpp
   pair<int, int> dfs337(TreeNode* t) {           // {选 t 时子树最大值, 不选 t 时子树最大值}
       if (!t) return {0, 0};
       auto [ls, ln] = dfs337(t->left);
       auto [rs, rn] = dfs337(t->right);
       int sel = t->val + ln + rn;                // 选 t：两个孩子都不能选
       int no = max(ls, ln) + max(rs, rn);        // 不选 t：每个孩子各取较大的
       return {sel, no};
   }
   int robIII(TreeNode* root) { auto [s, n] = dfs337(root); return max(s, n); }
   ```

   - **计算顺序是后序遍历**：先算完两个孩子，再算自己，递归天然就是这个顺序。
   - **只返回一个值会出错**：父节点要知道“孩子没偷时最多多少”，只返回“孩子子树的最大值”不够，所以每个节点返回一对。
   - **复杂度**：每个节点算一次，$O(n)$。

> **认出树形 DP**
>
> - **问题在一棵树上，每个节点的答案由它的孩子拼出来**：独立集（父子不能同选）、树的直径、子树大小、选若干节点的最值。
> - **父节点需要知道孩子处在哪种情况**：每个节点返回几个值，一个值对应一种情况（选 / 不选，染哪种颜色）。
> - **写法固定是后序 DFS**：先递归孩子，再合并。

## 6. 状压 DP：用一个整数表示选了哪些

### 6.1 旅行商：走过哪些点、现在停在哪

1. **题目：每个点恰好经过一次的最短回路**
   - **题意**：$n$ 个点，两两之间有距离 $d_{i,j}$，从 0 出发，每个点恰好经过一次再回到 0，求最短总长。$n \le 16$ 左右。
   - **暴力是枚举访问顺序**：$(n - 1)!$ 种，$n = 16$ 时约 $1.3 \times 10^{12}$，算不完。

2. **状态只记“走过哪些点”和“停在哪”，不记走的顺序**
   - **状态**：$f_{\text{mask},i}$ 表示走过的点集合是 $\text{mask}$、现在停在 $i$ 的最短路长。$\text{mask}$ 是一个整数，第 $j$ 位是 1 表示点 $j$ 走过了。
   - **为什么能扔掉顺序**：以后怎么走，只取决于还剩哪些点没走、现在在哪，和之前按什么顺序走无关。顺序不同、集合和终点相同的路，只留最短的那条。
   - **转移**：从 $i$ 走到一个还没走过的点 $j$。

   $$f_{\text{mask} \cup \{j\},\, j} = \min\left(f_{\text{mask} \cup \{j\},\, j},\ f_{\text{mask},i} + d_{i,j}\right), \qquad j \notin \text{mask}$$

   ```cpp
   int tsp(const vector<vector<int>>& d) {        // 从 0 出发，每个点恰好经过一次，回到 0 的最短环
       int n = d.size();
       const int INF = INT_MAX / 2;
       vector<vector<int>> f(1 << n, vector<int>(n, INF));  // f[mask][i]：走过 mask 里的点、停在 i 的最短路
       f[1][0] = 0;
       for (int mask = 1; mask < (1 << n); mask++)
           for (int i = 0; i < n; i++) {
               if (f[mask][i] >= INF || !(mask >> i & 1)) continue;
               for (int j = 0; j < n; j++) {
                   if (mask >> j & 1) continue;   // j 已经走过
                   int nm = mask | 1 << j;
                   f[nm][j] = min(f[nm][j], f[mask][i] + d[i][j]);
               }
           }
       int best = INF;
       for (int i = 0; i < n; i++) best = min(best, f[(1 << n) - 1][i] + d[i][0]);
       return best;
   }
   ```

   - **计算顺序是 $\text{mask}$ 从小到大**：转移只会往 $\text{mask}$ 里加点，新的 $\text{mask}$ 一定比旧的大。
   - **位运算的三个动作**：`mask >> j & 1` 看第 $j$ 位，`mask | 1 << j` 把第 $j$ 位置 1，`(1 << n) - 1` 是全集。
   - **复杂度**：状态 $2^n \cdot n$ 个，每个枚举 $n$ 个下一站，共 $O(2^n n^2)$。$n = 16$ 时约 $1.7 \times 10^7$；$n = 20$ 时约 $4 \times 10^8$，内存也要 $2^{20} \times 20$ 个整数，约 80 MB，已经到边上。

3. **[LC 847](https://leetcode.cn/problems/shortest-path-visiting-all-nodes/) 是同一个状态，换成 BFS**
   - **题意**：无向图，边长都是 1，可以从任意点出发、重复经过点和边，求访问所有点的最短路。$n \le 12$。
   - **状态还是（走过的集合，现在在哪）**：边长都是 1，所以在这个状态空间上做 BFS，第一次走到全集时的步数就是答案。

> **认出状压 DP**
>
> - **$n$ 很小，在 20 以内**：$2^{20} \approx 10^6$，一个集合能用一个整数存下来。
> - **问题要求“每个都用一次”“分配给每个人”“覆盖所有”**：旅行商、任务分配、选若干个互不冲突的。
> - **暴力是枚举排列 $n!$**：状压把它降到 $2^n$ 乘一个多项式，靠的是“只记集合、不记顺序”。

## 练习

每题后面一句话提示练的是哪一节。

**必做**

1. [LeetCode 300 最长递增子序列](https://leetcode.cn/problems/longest-increasing-subsequence/)：两种写法都写，说清 `tails` 的含义。
2. [LeetCode 72 编辑距离](https://leetcode.cn/problems/edit-distance/)：两个前缀，最后一步三种操作，边界单独写。
3. [LeetCode 518 零钱兑换 II](https://leetcode.cn/problems/coin-change-ii/)：完全背包数组合，外层枚举硬币。
4. [LeetCode 416 分割等和子集](https://leetcode.cn/problems/partition-equal-subset-sum/)：换成 0-1 背包，一维倒序。
5. [LeetCode 309 买卖股票的最佳时机含冷冻期](https://leetcode.cn/problems/best-time-to-buy-and-sell-stock-with-cooldown/)：三个状态的状态机。

**选做**

6. [LeetCode 1143 最长公共子序列](https://leetcode.cn/problems/longest-common-subsequence/)：两个串各取前缀的模板。
7. [LeetCode 516 最长回文子序列](https://leetcode.cn/problems/longest-palindromic-subsequence/)：区间 DP，按长度从小到大。
8. [LeetCode 337 打家劫舍 III](https://leetcode.cn/problems/house-robber-iii/)：树形 DP，每个节点返回一对值。
9. [LeetCode 847 访问所有节点的最短路径](https://leetcode.cn/problems/shortest-path-visiting-all-nodes/)：状压状态加 BFS。

## 和地图上其他格子的连接

- 6.1 的 `mask >> j & 1`、`mask | 1 << j` 是 A2 下半位运算的用法，枚举子集也在那里。
- 0-1 背包的“选或不选”和 A3 回溯的“选或不选”是同一棵搜索树：回溯把每条路都走一遍，DP 把相同状态的路合并成一个。
- 有向无环图上的最长路、路径条数是图上的 DP，计算顺序就是 A4 的拓扑序。
- 2.1 的 `tails` 用的是 A1 的二分，找“第一个 $\ge x$ 的位置”。
