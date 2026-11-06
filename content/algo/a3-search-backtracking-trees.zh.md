---
title: "A3：搜索与回溯、树"
date: 2026-11-06
slug: "a3-search-backtracking-trees"
description: "BFS 按层往外扩，第一次到达就是最少步数，网格题入队时就标记，多源 BFS 把所有起点放在第 0 层；回溯在一棵选择树上做 DFS，每一步选、递归、撤销，排序后剪枝、从 start 往后选去重；二叉树的遍历看访问自己的时机，递归函数交给父节点的只能是一条链，答案在当前节点把两边拼起来；验证 BST 靠祖先定下的区间，最近公共祖先看 p、q 是否分在两边；一般的树用倍增求 LCA，边权非负时两次搜索求直径。附 9 道练习题。"
weight: 4
math: true
toc: true
---
这一轮的东西都是“把所有可能走一遍”，区别在走的顺序和每一步带回什么：

- **BFS 按步数一层一层往外扩**：第一次到达某个点时走的步数，就是到它的最少步数。
- **回溯按 DFS 的顺序枚举所有方案**：每一步选一个、递归下去、回来时撤销，适合要列出全部方案、规模又不大的题。
- **树上的题多数是一次递归**：难点在递归函数该返回什么，以及答案在哪一步算。

## 1. BFS：按层往外扩，第一次到达就是最少步数

### 1.1 BFS 为什么能求最少步数：队列让点按步数从小到大出队

1. **队列里的点，步数从队头到队尾不减，而且最多差 1**
   - **起点是第 0 层**：它出队时，把一步能到的点放进队列，这些点是第 1 层。
   - **第 1 层的点全部出队以后，才轮到第 2 层**：第 1 层的点放进来的都是第 2 层，排在所有第 1 层的点后面。
   - **所以一个点第一次被放进队列时，它的步数就是最少步数**：更少步数能到的点都更早出队，要是能更早到它，它早就被放进来了。

2. **入队时就标记访问，不要等出队时才标记**
   - **出队时才标记，同一个点会被放进队列好几次**：它还没出队时，别的邻居又把它放进来一遍。网格里一个点有 4 个邻居，队列会膨胀好几倍，最坏超时或超内存。
   - **入队时标记，每个点只进队一次**：总共 $O(V + E)$，网格上就是 $O(mn)$。

> **什么时候想到 BFS**
>
> - **问“最少几步”“最短要多久”，每一步的代价都一样**：BFS。
> - **每一步的代价不一样**：换成 A4 的 Dijkstra。
> - **代价只有 0 和 1 两种**：用双端队列，代价 0 的放队头，代价 1 的放队尾（0-1 BFS）。
> - **只问连通、数块数，不问步数**：BFS 和 DFS 都行，DFS 写起来更短，但网格大时递归可能爆栈。

### 1.2 网格 BFS：岛屿数量

1. **题目：数网格里有几块相连的陆地**
   - **题意**：[LC 200 岛屿数量](https://leetcode.cn/problems/number-of-islands/)，`'1'` 是陆地、`'0'` 是水，上下左右相连的陆地算一个岛，问有几个岛。$m, n \le 300$。
   - **思路**：扫每个格子，碰到一块还没访问过的陆地，岛数加 1，从它开始 BFS，把整块岛都标记掉。

2. **从每块没访问过的陆地出发，把整块淹掉**

   ```cpp
   int numIslands(vector<vector<char>>& g) {
       int m = g.size(), n = g[0].size(), cnt = 0;
       int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
       for (int i = 0; i < m; i++)
           for (int j = 0; j < n; j++) {
               if (g[i][j] != '1') continue;
               cnt++;                                      // 碰到一块没淹过的陆地：新岛
               queue<pair<int,int>> q;
               q.push({i, j}); g[i][j] = '0';              // 入队时就标记
               while (!q.empty()) {
                   auto [x, y] = q.front(); q.pop();
                   for (int d = 0; d < 4; d++) {
                       int nx = x + dx[d], ny = y + dy[d];
                       if (nx < 0 || nx >= m || ny < 0 || ny >= n || g[nx][ny] != '1') continue;
                       g[nx][ny] = '0';
                       q.push({nx, ny});
                   }
               }
           }
       return cnt;
   }
   ```

   - **`dx`、`dy` 两个数组列出四个方向**：一个 for 循环走完上下左右，不用写四遍。
   - **把陆地改成 `'0'` 就是标记访问**：省掉一个 `visited` 数组。题目不许改输入时，另开一个 `vector<vector<bool>>`。
   - **越界判断写在最前面**：`||` 是短路的，越界时不会再去读 `g[nx][ny]`。

3. **复杂度和坑**
   - **时间 $O(mn)$**：每个格子最多入队一次，每次看 4 个邻居。
   - **出队时才改成 `'0'` 会重复入队**：见 1.1 的第 2 块。

### 1.3 多源 BFS：腐烂的橘子

1. **题目：所有橘子都烂掉要几分钟**
   - **题意**：[LC 994 腐烂的橘子](https://leetcode.cn/problems/rotting-oranges/)，`2` 是烂橘子、`1` 是新鲜橘子、`0` 是空格。每过一分钟，烂橘子上下左右的新鲜橘子都会烂掉。问最少几分钟后没有新鲜橘子，做不到就返回 −1。$m, n \le 10$。
   - **从每个烂橘子各做一次 BFS 是错的**：每个格子要的是离它最近的那个烂橘子，分开做还得再取最小值，又慢又容易写错。

2. **把所有烂橘子一起放进队列，当成第 0 层**
   - **这等于加了一个虚拟的总起点**：它一步连到所有烂橘子，之后就是普通的 BFS，每个格子的层数就是它离最近的烂橘子有几步。
   - **一层就是一分钟**：每轮先记下队列当前的长度 `sz`，只处理这 `sz` 个点，它们是同一分钟烂的。

   ```cpp
   int orangesRotting(vector<vector<int>>& g) {
       int m = g.size(), n = g[0].size(), fresh = 0;
       queue<pair<int,int>> q;
       for (int i = 0; i < m; i++)
           for (int j = 0; j < n; j++) {
               if (g[i][j] == 2) q.push({i, j});          // 所有烂橘子一起当起点
               else if (g[i][j] == 1) fresh++;
           }
       int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
       int minutes = 0;
       while (!q.empty() && fresh > 0) {
           int sz = q.size();                             // 这一层是同一分钟烂的
           while (sz--) {
               auto [x, y] = q.front(); q.pop();
               for (int d = 0; d < 4; d++) {
                   int nx = x + dx[d], ny = y + dy[d];
                   if (nx < 0 || nx >= m || ny < 0 || ny >= n || g[nx][ny] != 1) continue;
                   g[nx][ny] = 2; fresh--;
                   q.push({nx, ny});
               }
           }
           minutes++;
       }
       return fresh == 0 ? minutes : -1;
   }
   ```

   - **循环条件带上 `fresh > 0`**：最后一批橘子烂掉以后就停，不会多算一分钟。
   - **一开始就没有新鲜橘子，答案是 0**：比如 `[[0, 2]]`，循环一次都不进。
   - **样例**：`[[2,1,1],[1,1,0],[0,1,1]]` 是 4，`[[2,1,1],[0,1,1],[1,0,1]]` 是 −1（左下角那个永远烂不到）。

3. **复杂度**
   - **时间 $O(mn)$**：和单源 BFS 一样，每个格子入队一次。

> **认出多源 BFS**
>
> - **问“每个点离最近的某类点有多远”**：把那一类点全部当第 0 层，一次 BFS 求完。
> - **几样东西同时往外扩散**：火、病毒、烂橘子，同一时刻的扩散就是同一层。

## 2. 回溯：选、递归、撤销

### 2.1 回溯的骨架：在一棵选择树上做 DFS

1. **每一步做三件事：选一个、递归下去、回来撤销**
   - **选**：把这一步的选择放进当前路径 `path`，并更新相关标记（比如 `used[i] = true`）。
   - **递归**：带着这条路径去做下一步的选择。
   - **撤销**：递归回来以后，把刚才放进去的拿出来、标记改回去，再去试这一步的下一个选择。

2. **撤销不能省，因为整个搜索只用一份 `path`**
   - **`path` 是所有分支共用的**：不撤销的话，上一个分支留下的东西会带进下一个分支，方案就错了。
   - **也可以每层拷一份 `path` 传下去**：不用撤销，但每层都多一次拷贝，慢，面试时一般写共享加撤销的版本。

3. **复杂度看选择树有多少个叶子**
   - **估法**：叶子数乘以每个叶子的代价（通常是把路径拷进答案的 $O(n)$）。
   - **子集**：$2^n$ 个叶子，$O(2^n \cdot n)$，$n$ 到 20 左右还能跑。
   - **排列**：$n!$ 个叶子，$O(n! \cdot n)$，$n$ 到 10 左右。

> **什么时候想到回溯**
>
> - **要列出所有方案**（所有子集、所有排列、所有合法组合）：答案本身就有指数多个，只能回溯。
> - **只问方案数或最优值，而且 $n$ 不大**：先写回溯，再看有没有重复的子问题，有就加记忆化，变成 A5 的 DP。
> - **数据范围到 $10^5$ 这个量级**：不是回溯，换别的思路。

### 2.2 子集：每个元素选或不选

1. **题目：列出一个数组的所有子集**
   - **题意**：[LC 78 子集](https://leetcode.cn/problems/subsets/)，`nums` 里的元素互不相同，$n \le 10$，返回所有子集。
   - **选择树**：第 $i$ 层决定 `nums[i]` 选不选，每个叶子是一个子集，一共 $2^n$ 个。

2. **对每个元素先走“不选”，再走“选”**

   ```cpp
   vector<vector<int>> subsets(vector<int>& nums) {
       vector<vector<int>> ans;
       vector<int> path;
       function<void(int)> dfs = [&](int i) {
           if (i == (int)nums.size()) { ans.push_back(path); return; }
           dfs(i + 1);                                    // 不选 nums[i]
           path.push_back(nums[i]);                       // 选
           dfs(i + 1);                                    // 递归
           path.pop_back();                               // 撤销
       };
       dfs(0);
       return ans;
   }
   ```

   - **走到 `i == n` 才收集答案**：这时每个元素都决定过了，`path` 就是一个完整的子集。
   - **`function<void(int)>` 让 lambda 能递归调用自己**：普通 lambda 在定义时还看不到自己的名字。

### 2.3 全排列：每个位置选一个还没用过的

1. **题目：列出一个数组的所有排列**
   - **题意**：[LC 46 全排列](https://leetcode.cn/problems/permutations/)，`nums` 里的元素互不相同，$n \le 6$。
   - **选择树**：第 $k$ 层决定第 $k$ 个位置放谁，候选是所有还没用过的数。

2. **用 `used` 记哪些数已经放进路径**

   ```cpp
   vector<vector<int>> permute(vector<int>& nums) {
       int n = nums.size();
       vector<vector<int>> ans;
       vector<int> path;
       vector<bool> used(n, false);
       function<void()> dfs = [&]() {
           if ((int)path.size() == n) { ans.push_back(path); return; }
           for (int i = 0; i < n; i++) {
               if (used[i]) continue;
               used[i] = true; path.push_back(nums[i]);   // 选
               dfs();                                     // 递归
               path.pop_back(); used[i] = false;          // 撤销
           }
       };
       dfs();
       return ans;
   }
   ```

   - **子集和排列的区别在每层的候选**：子集每层只决定一个元素，排列每层要在所有没用过的数里挑一个。
   - **撤销要成对**：`path` 弹出，`used` 也要改回 `false`，漏一个就少方案。

### 2.4 组合总和：排序后剪枝，从 start 往后选

1. **题目：从候选数里凑出目标和，同一个数可以重复用**
   - **题意**：[LC 39 组合总和](https://leetcode.cn/problems/combination-sum/)，`candidates` 互不相同、都是正数，返回所有和为 `target` 的组合，组合之间不能重复（`[2, 3]` 和 `[3, 2]` 算同一个）。
   - **样例**：`[2, 3, 6, 7]`，`target = 7`，答案是 `[2, 2, 3]` 和 `[7]`。

2. **从 `start` 往后选去掉重复，排过序就能提前停**

   ```cpp
   vector<vector<int>> combinationSum(vector<int>& c, int target) {
       sort(c.begin(), c.end());
       vector<vector<int>> ans;
       vector<int> path;
       function<void(int, int)> dfs = [&](int start, int left) {
           if (left == 0) { ans.push_back(path); return; }
           for (int i = start; i < (int)c.size(); i++) {
               if (c[i] > left) break;                    // 排过序：后面的更大，都不用试
               path.push_back(c[i]);
               dfs(i, left - c[i]);                       // 传 i 不传 i + 1：同一个数可以再选
               path.pop_back();
           }
       };
       dfs(0, target);
       return ans;
   }
   ```

   - **只从 `start` 往后选，路径里的数就是不减的**：`[3, 2]` 这种顺序根本不会生成，每个组合只按一种顺序出现一次。
   - **递归传 `i` 而不是 `i + 1`**：下一步还能选同一个数，这就是“可以重复用”。
   - **`break` 是剪枝**：`c[i]` 已经超过剩下要凑的数，后面的更大，整段都不用试。不排序就只能 `continue`，一个个试完。

3. **变形：候选数有重复、每个只能用一次**
   - **题意**：[LC 40 组合总和 II](https://leetcode.cn/problems/combination-sum-ii/)，比如 `[1, 1, 2]` 凑 3，`[1, 2]` 只能算一次。
   - **改两处**：递归传 `i + 1`，每个数只用一次；同一层里跳过和前一个相同的值。

   ```cpp
   for (int i = start; i < (int)c.size(); i++) {
       if (c[i] > left) break;
       if (i > start && c[i] == c[i - 1]) continue;   // 同一层不选同样的值
       path.push_back(c[i]);
       dfs(i + 1, left - c[i]);                       // 每个数只能用一次：传 i + 1
       path.pop_back();
   }
   ```

   - **`i > start` 管的是“同一层”**：同一层选第一个 1 和选第二个 1，后面能走出的方案完全一样，只留第一个。不同层可以选两个 1（`[1, 1, ...]`），所以不能写成 `i > 0`。

> **回溯怎么去重、怎么剪枝**
>
> - **组合不讲顺序**：从 `start` 往后选，路径里的下标递增，每个组合只出现一次。
> - **候选里有重复值**：先排序，同一层跳过和前一个相同的值（`i > start && c[i] == c[i - 1]`）。
> - **剪枝**：先排序，凑不上的时候 `break`，后面的更大，不用再试。

### 2.5 N 皇后：用三个数组 O(1) 判断冲突

1. **题目：在 n × n 的棋盘上放 n 个互不攻击的皇后**
   - **题意**：[LC 51 N 皇后](https://leetcode.cn/problems/n-queens/)，列出所有放法；只问放法数的是 LC 52。$n \le 9$。
   - **每行恰好放一个**：所以按行回溯，第 $r$ 层决定第 $r$ 行的皇后放在哪一列。

2. **同列、同一条对角线，用三个布尔数组记**
   - **同列**：`col[c]`。
   - **主对角线（左上到右下）上 $r - c$ 相同**：加上 $n$ 变成非负下标，`d2[r - c + n]`。
   - **副对角线（右上到左下）上 $r + c$ 相同**：`d1[r + c]`。

   ```cpp
   int totalNQueens(int n) {
       vector<bool> col(n), d1(2 * n), d2(2 * n);
       int cnt = 0;
       function<void(int)> dfs = [&](int r) {             // 第 r 行放在哪一列
           if (r == n) { cnt++; return; }
           for (int c = 0; c < n; c++) {
               if (col[c] || d1[r + c] || d2[r - c + n]) continue;
               col[c] = d1[r + c] = d2[r - c + n] = true;
               dfs(r + 1);
               col[c] = d1[r + c] = d2[r - c + n] = false;
           }
       };
       dfs(0);
       return cnt;
   }
   ```

   - **$n = 1$ 到 $8$ 的放法数是 1、0、0、2、10、4、40、92**：和这份代码跑出来的一样。
   - **要输出棋盘时**：再开一个 `vector<string>`，放皇后时把那一格改成 `'Q'`，撤销时改回 `'.'`。

## 3. 二叉树：遍历和“递归返回什么”

### 3.1 遍历：前中后序看访问自己的时机，层序用队列

1. **前序、中序、后序只差“访问自己”放在哪**
   - **前序**：先访问自己，再左子树、右子树。
   - **中序**：先左子树，再自己，再右子树。二叉搜索树（BST）的中序是从小到大的。
   - **后序**：先左右子树，最后自己。要用到子树结果的题（3.2）都是后序。

   ```cpp
   void inorderRec(TreeNode* root, vector<int>& out) {
       if (!root) return;
       inorderRec(root->left, out);
       out.push_back(root->val);                          // 挪到第一行是前序，挪到最后是后序
       inorderRec(root->right, out);
   }
   ```

2. **迭代的中序：一路向左压栈，弹出来访问，再转去右子树**

   ```cpp
   vector<int> inorderIter(TreeNode* root) {
       vector<int> out;
       stack<TreeNode*> st;
       TreeNode* cur = root;
       while (cur || !st.empty()) {
           while (cur) { st.push(cur); cur = cur->left; }   // 一路向左压栈
           cur = st.top(); st.pop();
           out.push_back(cur->val);                         // 左子树走完了，访问自己
           cur = cur->right;                                // 再去右子树
       }
       return out;
   }
   ```

   - **栈里存的是“左子树还没走完、自己还没访问”的节点**：一路向左时把它们压进去，弹出来时左子树刚好走完。
   - **什么时候要写迭代版**：树可能退化成一条很长的链（几十万层）时，递归会爆栈；面试也常直接要求“不用递归”。

3. **层序：队列里每次正好是一整层**
   - **题意**：[LC 102 二叉树的层序遍历](https://leetcode.cn/problems/binary-tree-level-order-traversal/)，按层从上到下、每层从左到右输出。
   - **和 1.3 一样先记下 `sz`**：一轮只处理这 `sz` 个点，就是一整层。

   ```cpp
   vector<vector<int>> levelOrder(TreeNode* root) {
       vector<vector<int>> ans;
       if (!root) return ans;
       queue<TreeNode*> q;
       q.push(root);
       while (!q.empty()) {
           int sz = q.size();                               // 队里现在正好是一整层
           ans.push_back({});
           while (sz--) {
               TreeNode* x = q.front(); q.pop();
               ans.back().push_back(x->val);
               if (x->left) q.push(x->left);
               if (x->right) q.push(x->right);
           }
       }
       return ans;
   }
   ```

### 3.2 递归返回值：交给父节点的只能是一条链

1. **最大深度：返回子树的高度，父节点取两边较大的加 1**

   ```cpp
   int maxDepth(TreeNode* root) {
       if (!root) return 0;
       return 1 + max(maxDepth(root->left), maxDepth(root->right));
   }
   ```

   - **空树返回 0 是边界**：叶子的两边都是 0，返回 1。

2. **二叉树的直径：返回单侧深度，在当前节点把两边拼起来**
   - **题意**：[LC 543 二叉树的直径](https://leetcode.cn/problems/diameter-of-binary-tree/)，任意两个节点之间最长路径的边数，这条路径不一定经过根。
   - **每条路径都有一个最高点**：路径从最高点往下分成左右两段。所以对每个节点 $x$，算“以 $x$ 为最高点的最长路径” $= l + r$，$l$、$r$ 是左右子树往下最长链的节点数，取所有节点里的最大值。
   - **父节点要的却只是一条链**：路径经过 $x$ 往上走到父节点，就只能带上左右其中一侧。所以函数返回 $1 + \max(l, r)$，两边拼起来的 $l + r$ 记进全局变量 `best`。

   ```cpp
   int diameterOfBinaryTree(TreeNode* root) {
       int best = 0;
       function<int(TreeNode*)> depth = [&](TreeNode* x) -> int {   // 返回：从 x 往下最长链有几个节点
           if (!x) return 0;
           int l = depth(x->left), r = depth(x->right);
           best = max(best, l + r);                         // 经过 x 的最长路径有 l + r 条边
           return 1 + max(l, r);                            // 交给父节点的只能是一侧
       };
       depth(root);
       return best;
   }
   ```

   - **样例**：`[1, 2, 3, 4, 5]`（2 的两个孩子是 4、5），答案 3，路径是 4 → 2 → 1 → 3。

3. **二叉树中的最大路径和：同一个骨架，负的一侧不要**
   - **题意**：[LC 124 二叉树中的最大路径和](https://leetcode.cn/problems/binary-tree-maximum-path-sum/)，节点值可以是负数，路径至少有一个节点，求路径上节点值之和的最大值。
   - **一侧的链和是负的，就不如不接**：所以取 $\max(0, \text{gain})$。
   - **`best` 的初值要是 `INT_MIN`**：全是负数时，答案是最大的那个负数，初值写 0 就错了。

   ```cpp
   int maxPathSum(TreeNode* root) {
       int best = INT_MIN;
       function<int(TreeNode*)> gain = [&](TreeNode* x) -> int {   // 返回：从 x 往下走一条链的最大和
           if (!x) return 0;
           int l = max(0, gain(x->left));                   // 是负的就不要这一侧
           int r = max(0, gain(x->right));
           best = max(best, x->val + l + r);                // 以 x 为最高点的路径
           return x->val + max(l, r);
       };
       gain(root);
       return best;
   }
   ```

   - **样例**：`[-10, 9, 20, null, null, 15, 7]`，答案 42，路径是 15 → 20 → 7。

> **树上递归该返回什么**
>
> - **返回值是父节点能接着用的那部分**：往上走只能带一条链，所以返回单侧的最优（深度、链和）。
> - **答案在当前节点算**：把左右两边的返回值拼起来，更新全局的 `best`。
> - **一道题要的东西父节点用不上**：就是这个模式，返回值和答案分开。

### 3.3 验证二叉搜索树：每个节点要落在祖先定下的区间里

1. **题目：判断一棵树是不是 BST**
   - **题意**：[LC 98 验证二叉搜索树](https://leetcode.cn/problems/validate-binary-search-tree/)，要求左子树所有节点都小于根，右子树所有节点都大于根，每棵子树也是这样。节点值是 `int` 范围。
   - **只和左右孩子比是错的**：`[5, 4, 6, null, null, 3, 7]` 里，3 是 6 的左孩子，比 6 小，局部看没问题；但它在 5 的右子树里，比 5 小，不合法。

2. **递归时把允许的区间传下去**
   - **往左走，上界变成当前节点的值；往右走，下界变成当前节点的值**：每个节点都必须落在一路上祖先定下的开区间里。

   ```cpp
   bool isValidBST(TreeNode* root) {
       function<bool(TreeNode*, long long, long long)> ok = [&](TreeNode* x, long long lo, long long hi) {
           if (!x) return true;
           if (x->val <= lo || x->val >= hi) return false;  // 必须落在祖先们定下的开区间里
           return ok(x->left, lo, x->val) && ok(x->right, x->val, hi);
       };
       return ok(root, LLONG_MIN, LLONG_MAX);
   }
   ```

   - **区间端点用 `long long`**：节点值可能就是 `INT_MIN` 或 `INT_MAX`，用 `int` 当初始边界会把它误判成越界。
   - **另一种写法是中序遍历，检查是否严格递增**：BST 的中序是从小到大的，等价。

### 3.4 最近公共祖先：p、q 分在两边的那个节点

1. **题目：求两个节点在二叉树里的最近公共祖先**
   - **题意**：[LC 236 二叉树的最近公共祖先](https://leetcode.cn/problems/lowest-common-ancestor-of-a-binary-tree/)，`p`、`q` 都在树里，一个节点也可以是它自己的祖先。
   - **最近公共祖先（LCA）**：同时是 `p` 和 `q` 的祖先、又离它们最近的那个节点。

2. **函数返回“这棵子树里找到的 p 或 q”**

   ```cpp
   TreeNode* lowestCommonAncestor(TreeNode* root, TreeNode* p, TreeNode* q) {
       if (!root || root == p || root == q) return root;
       TreeNode* l = lowestCommonAncestor(root->left, p, q);
       TreeNode* r = lowestCommonAncestor(root->right, p, q);
       if (l && r) return root;                             // p、q 分在两边：就是 root
       return l ? l : r;                                    // 都在一边：答案在那一边
   }
   ```

   - **左右都找到了**：`p`、`q` 分在 `root` 两侧，`root` 就是 LCA。
   - **只有一边找到**：那一边返回的要么已经是 LCA，要么是 `p`、`q` 里先碰到的那一个，原样往上交，由上层去判断。
   - **碰到 `p` 或 `q` 就直接返回，不再往下找**：另一个要是在它下面，它就是 LCA；要是不在，上层会从另一边找到。
   - **复杂度 $O(n)$**：每次查询都要走一遍整棵树。查询很多时，用 4.1 的倍增。

## 4. 一般的树：倍增求 LCA、直径

### 4.1 倍增求 LCA：每个点记下往上跳 2 的 k 次方步到哪

1. **题目：一棵树、很多次询问两个点的 LCA**
   - **题意**：[洛谷 P3379【模板】最近公共祖先（LCA）](https://www.luogu.com.cn/problem/P3379)，$n, m \le 5 \times 10^5$，$m$ 次询问。
   - **一次询问 $O(n)$ 会超时**：$5 \times 10^5$ 次询问乘 $5 \times 10^5$ 个点，要把每次询问降到 $O(\log n)$。

2. **预处理：`up[k][v]` 是 v 往上跳 $2^k$ 步到的点**
   - **$k = 0$ 是父亲**：BFS 一遍求出每个点的父亲和深度。
   - **跳 $2^k$ 步等于连跳两次 $2^{k-1}$ 步**：$\text{up}[k][v] = \text{up}[k-1][\text{up}[k-1][v]]$。
   - **预处理 $O(n \log n)$**：$\log n$ 层，每层 $n$ 个点。$n = 5 \times 10^5$ 时 20 层，`int` 共约 40 MB。

3. **询问：先抬到同样深，再一起往上跳**

   ```cpp
   struct LCA {
       int LOG;
       vector<vector<int>> up;     // up[k][v]：v 往上跳 2^k 步到的点，跳过根就停在根
       vector<int> dep;
       LCA(int n, const vector<vector<int>>& adj, int root) {
           LOG = 1; while ((1 << LOG) < n) LOG++;
           up.assign(LOG, vector<int>(n, root));
           dep.assign(n, 0);
           vector<int> order{root}; vector<bool> seen(n); seen[root] = true;   // BFS 求父亲和深度，深树不爆栈
           for (size_t i = 0; i < order.size(); i++) {
               int v = order[i];
               for (int w : adj[v]) if (!seen[w]) {
                   seen[w] = true; dep[w] = dep[v] + 1; up[0][w] = v; order.push_back(w);
               }
           }
           for (int k = 1; k < LOG; k++)
               for (int v = 0; v < n; v++) up[k][v] = up[k - 1][up[k - 1][v]];   // 跳 2^k = 连跳两次 2^(k-1)
       }
       int query(int a, int b) const {
           if (dep[a] < dep[b]) swap(a, b);
           for (int k = LOG - 1; k >= 0; k--)               // 先把 a 抬到和 b 一样深
               if (dep[a] - (1 << k) >= dep[b]) a = up[k][a];
           if (a == b) return a;
           for (int k = LOG - 1; k >= 0; k--)               // 一起往上跳：跳完还不相等才跳
               if (up[k][a] != up[k][b]) { a = up[k][a]; b = up[k][b]; }
           return up[0][a];
       }
   };
   ```

   - **抬到同样深，就是把深度差拆成二进制**：从大到小试每个 $2^k$，不会跳过头就跳。
   - **抬完相等，说明 b 就是 a 的祖先**：直接返回。
   - **一起跳时，“跳完还不相等才跳”**：这样 `a`、`b` 最后停在 LCA 正下方的两个点上，再往上一步就是 LCA。要是写成“相等就跳”，可能跳到 LCA 上面的某个公共祖先。
   - **根的父亲设成根自己**：跳过头的都停在根上，不会越界。
   - **询问 $O(\log n)$**：两个循环各 $\log n$ 次。
   - **P3379 的编号从 1 开始，根是输入给的 $s$**：读入时减 1，或者把数组开到 $n + 1$。

### 4.2 树的直径：从任意点找最远点，再从它找最远点

1. **题目：求树上距离最远的两个点之间的距离**
   - **直径**：树上所有两点之间路径长度的最大值，边上可以有权。
   - **做法**：从任意点 $s$ 出发找最远的点 $a$，再从 $a$ 出发找最远的点 $b$，$a$ 到 $b$ 的距离就是直径。两次遍历，$O(n)$。

   ```cpp
   pair<int, long long> farthest(int s, const vector<vector<pair<int,int>>>& adj) {
       int n = adj.size();
       vector<long long> dist(n, 0);
       vector<bool> seen(n, false);
       vector<int> st{s}; seen[s] = true;                   // 树上两点路径唯一，怎么遍历都行
       while (!st.empty()) {
           int v = st.back(); st.pop_back();
           for (auto [w, c] : adj[v])
               if (!seen[w]) { seen[w] = true; dist[w] = dist[v] + c; st.push_back(w); }
       }
       int far = max_element(dist.begin(), dist.end()) - dist.begin();
       return {far, dist[far]};
   }
   long long treeDiameter(const vector<vector<pair<int,int>>>& adj) {
       int a = farthest(0, adj).first;                      // 第一次：从任意点找最远点 a
       return farthest(a, adj).second;                      // 第二次：从 a 出发的最远距离就是直径
   }
   ```

   - **树上两点之间只有一条路径**：所以用栈、用队列遍历都一样，第一次走到就是真正的距离。

2. **为什么对：从任意点出发的最远点，一定是某条直径的端点**
   - **设定**：以 $s$ 为根，把到 $s$ 的距离看成深度 $\text{dep}$，$a$ 是最深的点。设 $u$–$v$ 是一条直径，长度 $D$，它的最高点（$u$、$v$ 的 LCA）是 $t$。
   - **$u$、$v$ 里至少有一个点，和 $a$ 的 LCA 不比 $t$ 低**：$a$ 不在 $t$ 的子树里时，它和 $u$、$v$ 的 LCA 都是 $t$ 的祖先；$a$ 在 $t$ 的子树里时，$u$、$v$ 分在 $t$ 下面的不同分支（或者 $t$ 就是其中一个），$a$ 至少和其中一个在 $t$ 处分开。记这个点是 $x$，另一个是 $y$，$x$ 和 $a$ 的 LCA 是 $c$。
   - **边权非负，越往上越浅**：$c$ 不比 $t$ 低，所以 $\text{dep}(c) \le \text{dep}(t)$。$a$ 是最深的，所以 $\text{dep}(a) \ge \text{dep}(y)$。于是

   $$d(a, x) = \text{dep}(a) + \text{dep}(x) - 2\,\text{dep}(c) \ \ge\ \text{dep}(y) + \text{dep}(x) - 2\,\text{dep}(t) = D$$

   - **结论**：从 $a$ 出发有一条不短于直径的路径，$a$ 就是某条直径的端点，第二次从 $a$ 找到的最远距离就是直径。

3. **有负边权时这个做法是错的**
   - **反例**：一条链 $A$–$B$–$C$–$D$，边权依次是 1、−10、5。真正的直径是 $C$–$D$，长 5。从 $A$ 出发，最远的是 $B$（距离 1）；再从 $B$ 出发，最远的是 $A$，算出来是 1。
   - **出错在证明的第三步**：有负边时，往上走不一定变浅，$\text{dep}(c) \le \text{dep}(t)$ 不成立。
   - **改用 3.2 的树形 DP**：每个点返回往下最长链（负的就取 0），在当前点把最长的两条拼起来，边权正负都对。

> **树的直径用哪种做法**
>
> - **边权非负、只要长度或端点**：两次遍历，代码最短，还能顺手拿到两个端点。
> - **有负边权，或者要在 DP 里顺带算别的**：树形 DP，每个点返回往下最长链，在当前点拼两条。

## 练习

每题后面一句话提示练的是哪一节。

**必做**

1. [LeetCode 994 腐烂的橘子](https://leetcode.cn/problems/rotting-oranges/)：多源 BFS，一层是一分钟。
2. [LeetCode 46 全排列](https://leetcode.cn/problems/permutations/)：回溯的选、递归、撤销，`used` 要成对改回去。
3. [LeetCode 39 组合总和](https://leetcode.cn/problems/combination-sum/)：从 `start` 往后选去重，排序后 `break` 剪枝。
4. [LeetCode 543 二叉树的直径](https://leetcode.cn/problems/diameter-of-binary-tree/)：返回单侧深度，在当前节点拼两边。
5. [LeetCode 236 二叉树的最近公共祖先](https://leetcode.cn/problems/lowest-common-ancestor-of-a-binary-tree/)：返回子树里找到的 `p` 或 `q`。

**选做**

6. [LeetCode 124 二叉树中的最大路径和](https://leetcode.cn/problems/binary-tree-maximum-path-sum/)：同 543 的骨架，负的一侧不要，`best` 初值是 `INT_MIN`。
7. [LeetCode 98 验证二叉搜索树](https://leetcode.cn/problems/validate-binary-search-tree/)：把区间传下去，边界用 `long long`。
8. [LeetCode 51 N 皇后](https://leetcode.cn/problems/n-queens/)：按行回溯，三个数组判冲突。
9. [洛谷 P3379【模板】最近公共祖先（LCA）](https://www.luogu.com.cn/problem/P3379)：倍增，注意 1 开始编号和给定的根。

## 和地图上其他格子的连接

- **BFS 的“每一步代价相同”一放开，就是 A4 的 Dijkstra**：代价只有 0 和 1 时，用双端队列的 0-1 BFS 就够。
- **回溯里有重复的子问题，加上记忆化就是 A5 的 DP**：$n$ 到 20 左右、要在所有排列里找最优（比如旅行商问题），换成 A5 的状压 DP。
- **3.2 的“返回一条链、在当前节点拼两边”，就是 A5 树形 DP 的雏形**：树形 DP 只是把返回值从一个数换成几个状态。
- **倍增不只用来求 LCA**：B2 的树链剖分也能求 LCA，还能支持路径上的修改和查询。
