---
title: "A4：图：最短路、拓扑排序、并查集"
date: 2026-11-06
slug: "a4-graphs-shortest-path-topo-dsu"
description: "图上的三类面试题：按边权和规模选最短路（BFS、0-1 BFS、Dijkstra 加懒删除、Bellman-Ford 判负环和限制边数、Floyd）；拓扑排序用入度或三色 DFS 排出先后、判环，再在 DAG 上按拓扑序 DP；并查集用路径压缩和按大小合并，数连通块、找成环的边、做 Kruskal 最小生成树。附 9 道练习题。"
weight: 5
math: true
toc: true
---
这一轮讲图上最常考的三类问题，先把图存下来，再按问题选算法：

- **最短路先看边权，再看规模**：边权都是 1 用 BFS，非负用 Dijkstra，有负权用 Bellman-Ford，任意两点之间用 Floyd。
- **拓扑排序处理有向图里的先后依赖**：排出一个合法的顺序，顺带判断依赖有没有环，再在无环图上按这个顺序做 DP。
- **并查集处理无向图里的连通**：边一条条加进来，随时回答两个点连没连通，每次操作近似 $O(1)$。

## 1. 存图：邻接表还是邻接矩阵

### 1.1 邻接表存每个点的出边，邻接矩阵存任意两点之间

1. **两种存法存的东西不一样**
   - **邻接表存每个点的出边**：`g[u]` 里是从 $u$ 出发的所有边 $(v, w)$，空间 $O(n + m)$，遍历一个点的出边只花它的度数那么多时间。
   - **邻接矩阵存任意两点之间的边**：`w[u][v]` 是 $u$ 到 $v$ 的边权，空间 $O(n^2)$，查一条边 $O(1)$。
   - **邻接表这样建**：

   ```cpp
   vector<vector<pair<int,int>>> g(n);          // g[u]：u 的所有出边 (v, w)
   for (auto& e : edges) {
       g[e[0]].push_back({e[1], e[2]});
       // 无向图再加反方向：g[e[1]].push_back({e[0], e[2]});
   }
   ```

   - **无向图的每条边要存两次**：$u \to v$ 和 $v \to u$ 各一条，邻接表里的边数按 $2m$ 算。

> **邻接表还是邻接矩阵**
>
> - **$n$ 到 $10^5$、边稀疏**：用邻接表。$10^5$ 个点的矩阵有 $10^{10}$ 个格子，开不下。
> - **$n$ 在 500 以内，或者要 $O(1)$ 查两点之间的边**（比如 2.5 的 Floyd）：用邻接矩阵。有重边时矩阵里只留最小的那条。

## 2. 最短路：先看边权，再看规模

### 2.1 BFS：边权都是 1 时，先到的就是最短

1. **BFS 按距离一层一层往外扩**
   - **队列里的距离从队头到队尾不减**：起点距离 0 先出队，它的邻居都是 1；1 的点出完，才轮到 2 的点。
   - **一个点第一次被访问时的距离就是最短距离**：比它近的点都已经出过队，要是有更短的路，它早就被那条路上的点访问了。

   ```cpp
   vector<int> bfs(int n, const vector<vector<int>>& g, int s) {
       vector<int> dist(n, -1);                 // -1 表示还没到过
       queue<int> q;
       dist[s] = 0; q.push(s);
       while (!q.empty()) {
           int u = q.front(); q.pop();
           for (int v : g[u])
               if (dist[v] == -1) { dist[v] = dist[u] + 1; q.push(v); }
       }
       return dist;
   }
   ```

   - **复杂度 $O(n + m)$**：每个点进队一次，每条边看一次。
   - **网格题就是这张图**：每个格子是一个点，上下左右是边，“最少几步走到”就是 BFS。

2. **边权只有 0 和 1：0-1 BFS**
   - **用双端队列，边权 0 的插队头，边权 1 的排队尾**：这样队列里的距离仍然从头到尾不减，而且最多只有两种值。

   ```cpp
   vector<int> bfs01(int n, const vector<vector<pair<int,int>>>& g, int s) {
       vector<int> dist(n, INT_MAX);
       deque<int> dq;
       dist[s] = 0; dq.push_back(s);
       while (!dq.empty()) {
           int u = dq.front(); dq.pop_front();
           for (auto [v, w] : g[u]) {
               if (dist[u] + w < dist[v]) {
                   dist[v] = dist[u] + w;
                   if (w == 0) dq.push_front(v); else dq.push_back(v);   // 边权 0 插队头，边权 1 排队尾
               }
           }
       }
       return dist;
   }
   ```

   - **一个点可能被更新两次**：先经一条 1 边进了队尾，后来又经一条 0 边变短、插到队头，所以判断条件是“变短了才更新”，不是“没访问过”。
   - **复杂度 $O(n + m)$**，比 Dijkstra 少一个 $\log$。

### 2.2 Dijkstra：非负权，每次定下离起点最近的那个点

1. **题目：信号从 $k$ 传到所有节点要多久**
   - **题意**：[LC 743 网络延迟时间](https://leetcode.cn/problems/network-delay-time/)，$n$ 个节点编号 1 到 $n$，`times[i] = (u, v, w)` 是一条有向边，信号走过它要 $w$。从 $k$ 发出信号，问所有节点都收到要多久，有收不到的返回 −1。$n \le 100$，边数 $\le 6000$，$0 \le w \le 100$。
   - **答案是从 $k$ 出发的最短距离里最大的那个**：所有节点都收到，要等最远的那个收到。

2. **堆里距离最小的点，它的距离已经是最终值**
   - **为什么能定下来**：设堆顶是 $u$，距离 $d$。别的任何一条到 $u$ 的路，都要先经过一个还在堆里、距离不小于 $d$ 的点，再走几条非负的边，不可能比 $d$ 短。
   - **定下以后用它松弛出边**：对每条 $u \to v$，`dist[u] + w < dist[v]` 就更新 `dist[v]`，把 $(dist[v], v)$ 压进堆。

   ```cpp
   int networkDelayTime(vector<vector<int>>& times, int n, int k) {
       vector<vector<pair<int,int>>> g(n + 1);              // 节点从 1 编号
       for (auto& e : times) g[e[0]].push_back({e[1], e[2]});
       const int INF = INT_MAX;
       vector<int> dist(n + 1, INF);
       priority_queue<pair<int,int>, vector<pair<int,int>>, greater<>> pq;   // (距离, 点)，小根堆
       dist[k] = 0; pq.push({0, k});
       while (!pq.empty()) {
           auto [d, u] = pq.top(); pq.pop();
           if (d > dist[u]) continue;                       // 过期条目：u 早被更短的距离定下了
           for (auto [v, w] : g[u])
               if (dist[u] + w < dist[v]) { dist[v] = dist[u] + w; pq.push({dist[v], v}); }
       }
       int ans = *max_element(dist.begin() + 1, dist.end());
       return ans == INF ? -1 : ans;
   }
   ```

   - **同一个点会在堆里留下好几条**：它每变短一次就压一条，堆删不了旧的那条。
   - **取出时距离比 `dist[u]` 大，就是过期的，跳过**：这就是 [A2 上 3.5](/zh/algo/a2-stack-monotonic-stack-heap/#35-堆删不了中间的元素懒删除) 的懒删除。
   - **复杂度 $O(m \log m)$**：每条边最多压一次堆。$m \le n^2$，所以 $\log m$ 和 $\log n$ 是同一个量级。
   - **`dist[u] + w` 不会溢出**：从堆里取出的点距离都是有限的，`INF` 只出现在比较的右边。
   - **节点从 1 编号**：数组开 $n + 1$，求最大值时从下标 1 开始，否则下标 0 的 `INF` 会被当成答案。

3. **有负权时，Dijkstra 的论证就不成立**
   - **一个点定下以后还可能变短**：“先经过堆里更远的点，再走非负边”这一步用到了边权非负。
   - **例子**：边 $0 \to 1$ 权 2、$1 \to 3$ 权 1、$0 \to 2$ 权 3、$2 \to 1$ 权 −2。真实的最短距离是 $d_1 = 1$、$d_3 = 2$。用访问标记的写法先定下 $d_1 = 2$，算出 $d_3 = 3$，之后 $2 \to 1$ 让 $d_1$ 变短，可 1 已经处理过，$d_3$ 就错了。
   - **上面这种不加标记、变短就重新压堆的写法**：结果是对的，但一个点会被反复处理，最坏是指数级。**有负权就换 Bellman-Ford。**

### 2.3 Bellman-Ford：有负权，就把每条边松弛 n − 1 轮

1. **最短路最多有 $n - 1$ 条边，所以松弛 $n - 1$ 轮就够**
   - **没有负环时，最短路不会重复经过一个点**：重复经过就有环，环的权不为负，去掉它不会变长。所以最短路最多 $n$ 个点、$n - 1$ 条边。
   - **第 $i$ 轮松弛完，边数不超过 $i$ 的路径里最短的那条都已经算出来了**：每一轮把所有边都松弛一遍，路径就能多延伸一条边。
   - **复杂度 $O(nm)$**：$n - 1$ 轮，每轮看 $m$ 条边。某一轮什么都没变，就可以提前停。

2. **第 $n$ 轮还能变短，说明从起点走得到一个负环**
   - **负环上转一圈就短一截**：最短路没有下限，松弛永远停不下来。

   ```cpp
   struct Edge { int u, v; long long w; };

   bool bellmanFord(int n, const vector<Edge>& edges, int s, vector<long long>& dist) {
       const long long INF = LLONG_MAX / 4;
       dist.assign(n, INF);
       dist[s] = 0;
       for (int i = 0; i < n - 1; i++) {                    // 最短路最多 n-1 条边
           bool changed = false;
           for (auto& e : edges)
               if (dist[e.u] != INF && dist[e.u] + e.w < dist[e.v]) { dist[e.v] = dist[e.u] + e.w; changed = true; }
           if (!changed) break;                             // 这一轮没变，后面也不会变
       }
       for (auto& e : edges)                                // 第 n 轮还能变短：从 s 走得到一个负环
           if (dist[e.u] != INF && dist[e.u] + e.w < dist[e.v]) return false;
       return true;
   }
   ```

   - **`dist[e.u] != INF` 不能省**：有负权时，`INF` 加一个负数会比 `INF` 小，一个走不到的点会被当成走得到。
   - **它只能发现从 $s$ 走得到的负环**：要判整张图有没有负环，加一个虚拟起点，向每个点连一条权 0 的边。

3. **SPFA 是 Bellman-Ford 的队列版**
   - **只拿上一轮变短了的点去松弛**：别的点的出边这一轮不会带来新结果，用一个队列装变短的点。
   - **平均比 Bellman-Ford 快很多，最坏还是 $O(nm)$**：可以专门构造数据卡它，非负权的题别用它代替 Dijkstra。

### 2.4 限制边数的最短路：每一轮只用上一轮的结果

1. **题目：最多中转 $k$ 次的最便宜航线**
   - **题意**：[LC 787 K 站中转内最便宜的航班](https://leetcode.cn/problems/cheapest-flights-within-k-stops/)，$n$ 个城市（$n \le 100$），`flights[i] = (from, to, price)`，求从 `src` 到 `dst`、最多经过 $k$ 站中转的最便宜价格，没有就返回 −1。
   - **最多中转 $k$ 次，就是最多走 $k + 1$ 条边**：Bellman-Ford 第 $i$ 轮以后，`dist` 正好是“边数不超过 $i$”的最便宜价格，跑 $k + 1$ 轮就是答案。

2. **每一轮都要拿上一轮的拷贝去松弛**

   ```cpp
   int findCheapestPrice(int n, vector<vector<int>>& flights, int src, int dst, int k) {
       const int INF = 1e9;
       vector<int> dist(n, INF);
       dist[src] = 0;
       for (int round = 0; round <= k; round++) {           // 最多 k 次中转 = 最多 k+1 条边
           vector<int> prev = dist;                         // 这一轮只用上一轮的结果
           for (auto& f : flights) {
               int u = f[0], v = f[1], w = f[2];
               if (prev[u] != INF && prev[u] + w < dist[v]) dist[v] = prev[u] + w;
           }
       }
       return dist[dst] == INF ? -1 : dist[dst];
   }
   ```

   - **不拷贝，一轮就可能走好几条边**：同一轮里 `dist[u]` 刚被更新，又被拿去更新 `dist[v]`，边数限制就破了。
   - **例子**：航班 $0 \to 1$ 价 100、$1 \to 2$ 价 100、$0 \to 2$ 价 500，$k = 0$，答案是直飞的 500。不拷贝时，按这个顺序处理，同一轮里先得到 $d_1 = 100$，再用它得到 $d_2 = 200$，答案就错成了 200。
   - **复杂度 $O(k \cdot m)$**。
   - **Dijkstra 不能直接做这道题**：最便宜的路不一定边数少，状态里要多记一维“用了几条边”。

### 2.5 Floyd：任意两点之间，O(n³)

1. **一个点一个点地加进来当中转站**
   - **状态**：只允许经过前 $k$ 个点中转时，$i$ 到 $j$ 的最短距离。
   - **加入第 $k$ 个点**：要么不经过它，要么经过它一次，$d_{ij} = \min(d_{ij},\ d_{ik} + d_{kj})$。第一维可以滚动掉，直接在一个矩阵上改。

   ```cpp
   vector<vector<long long>> floyd(int n, const vector<Edge>& edges) {
       const long long INF = LLONG_MAX / 4;
       vector<vector<long long>> d(n, vector<long long>(n, INF));
       for (int i = 0; i < n; i++) d[i][i] = 0;
       for (auto& e : edges) d[e.u][e.v] = min(d[e.u][e.v], e.w);
       for (int k = 0; k < n; k++)                          // k 必须在最外层
           for (int i = 0; i < n; i++)
               for (int j = 0; j < n; j++)
                   if (d[i][k] < INF && d[k][j] < INF) d[i][j] = min(d[i][j], d[i][k] + d[k][j]);
       return d;
   }
   ```

   - **$k$ 必须在最外层**：第 $k$ 轮要用到“只经过前 $k - 1$ 个点”时的全部结果，$k$ 放到里面，用到的是还没算完的值。
   - **$n$ 到 500 左右**：$500^3 \approx 10^8$，正好是一秒的量。
   - **负权也能用**：算完以后有 $d_{ii} < 0$，就说明 $i$ 在一个负环上。

> **最短路用哪种**
>
> - **边权都是 1**：BFS，$O(n + m)$。
> - **边权只有 0 和 1**：0-1 BFS，$O(n + m)$。
> - **非负权、一个起点**：Dijkstra 堆优化，$O(m \log m)$。
> - **有负权，或者限制边数，或者要判负环**：Bellman-Ford，$O(nm)$。
> - **要任意两点之间的距离，$n$ 在 500 以内**：Floyd，$O(n^3)$。

## 3. 拓扑排序：有向图里，先做没有前置的

### 3.1 Kahn：入度为 0 的先出队

1. **题目：课程有先修要求，能不能学完、按什么顺序学**
   - **题意**：[LC 207 课程表](https://leetcode.cn/problems/course-schedule/) 和 [LC 210 课程表 II](https://leetcode.cn/problems/course-schedule-ii/)，`numCourses` 门课（$\le 2000$），`prerequisites[i] = [a, b]` 表示学 $a$ 之前要先学 $b$。207 问能不能学完，210 要给出一种顺序，学不完返回空数组。
   - **把先修关系画成有向图**：$b \to a$，先修的指向后修的。学完所有课的顺序，就是这张图的一个拓扑序。

2. **入度就是“还有几门先修没学”**
   - **入度为 0 的课现在就能学**：把它们都放进队列。
   - **学完一门，它指向的课入度减 1**：减到 0 的，先修都学完了，入队。

   ```cpp
   vector<int> findOrder(int n, vector<vector<int>>& prerequisites) {
       vector<vector<int>> g(n);
       vector<int> indeg(n, 0);
       for (auto& p : prerequisites) { g[p[1]].push_back(p[0]); indeg[p[0]]++; }   // 先修 p[1] 指向课 p[0]
       queue<int> q;
       for (int i = 0; i < n; i++) if (indeg[i] == 0) q.push(i);
       vector<int> order;
       while (!q.empty()) {
           int u = q.front(); q.pop();
           order.push_back(u);
           for (int v : g[u]) if (--indeg[v] == 0) q.push(v);
       }
       if ((int)order.size() < n) return {};                // 有环：环上的点入度永远减不到 0
       return order;
   }
   ```

   - **出队的点数少于 $n$，就是有环**：环上每个点都在等环上的前一个点，入度永远减不到 0，一个都出不了队。
   - **例子**：4 门课，`[[1,0],[2,0],[3,1],[3,2]]`，输出 `0 1 2 3`。
   - **复杂度 $O(n + m)$**。
   - **边的方向别写反**：写成 $a \to b$，排出来的是倒序。207 只问能不能学完，看不出错；210 要顺序，就错了。

### 3.2 DFS 三色：碰到还在递归栈上的点，就是环

1. **每个点有三种状态**
   - **0：没访问过。**
   - **1：在当前的递归栈上**，也就是从它出发的 DFS 还没结束。
   - **2：已经处理完**，从它出发走得到的点都看过了。

   ```cpp
   bool canFinish(int n, vector<vector<int>>& prerequisites) {
       vector<vector<int>> g(n);
       for (auto& p : prerequisites) g[p[1]].push_back(p[0]);
       vector<int> color(n, 0);                             // 0 没访问，1 在递归栈上，2 已完成
       function<bool(int)> dfs = [&](int u) {               // 返回 true 表示找到了环
           color[u] = 1;
           for (int v : g[u]) {
               if (color[v] == 1) return true;              // 碰到栈上的点：回边，有环
               if (color[v] == 0 && dfs(v)) return true;
           }
           color[u] = 2;
           return false;
       };
       for (int i = 0; i < n; i++)
           if (color[i] == 0 && dfs(i)) return false;
       return true;
   }
   ```

   - **碰到颜色 1 的点就是环**：它还在栈上，说明从它出发又走回了它自己。
   - **碰到颜色 2 的点不是环**：只是两条路汇到了同一个点。只用“访问过、没访问过”两种状态，会把 $0 \to 1$、$0 \to 2$、$1 \to 2$ 这种汇合误判成环。
   - **点变成 2 的顺序倒过来，就是一个拓扑序**：一个点处理完时，它能走到的点都已经处理完了。
   - **递归深度可能到 $n$**：$n$ 到 $10^5$ 级时可能栈溢出，那时用 Kahn。

### 3.3 DAG 上的 DP：按拓扑序算，用到的都已经算完

1. **有向无环图（DAG）上的最长路**
   - **状态**：$f_v$ 是以 $v$ 结尾的最长路，$f_v = \max_{u \to v} (f_u + w_{uv})$。
   - **按拓扑序算就对**：$u$ 出队时，所有指向 $u$ 的边都已经处理过，$f_u$ 已经是终值，可以拿去更新后面的点。

   ```cpp
   long long dagLongestPath(int n, const vector<Edge>& edges) {   // 边权和最大的路径
       vector<vector<pair<int,long long>>> g(n);
       vector<int> indeg(n, 0);
       for (auto& e : edges) { g[e.u].push_back({e.v, e.w}); indeg[e.v]++; }
       vector<long long> f(n, 0);                           // f[v]：以 v 结尾的最长路
       queue<int> q;
       for (int i = 0; i < n; i++) if (indeg[i] == 0) q.push(i);
       long long best = 0;
       while (!q.empty()) {
           int u = q.front(); q.pop();
           best = max(best, f[u]);
           for (auto [v, w] : g[u]) {
               f[v] = max(f[v], f[u] + w);                  // u 出队时 f[u] 已经是终值
               if (--indeg[v] == 0) q.push(v);
           }
       }
       return best;
   }
   ```

   - **复杂度 $O(n + m)$**。
   - **一般图上的最长路是难题**，有环就能一直绕；**DAG 上没有环，按拓扑序一遍就算完**。最短路、路径条数也一样，负权也不要紧。

> **什么时候想到拓扑排序**
>
> - **题目里有先后依赖**：课程先修、任务调度、编译顺序，要排出一个合法的顺序，或者判断依赖有没有环。
> - **在有向无环图上求最长路、最短路、方案数**：按拓扑序做 DP，每个点算的时候，它依赖的点都已经算完。

## 4. 并查集：动态地合并集合，问两个点连没连通

### 4.1 路径压缩加按大小合并：每次操作近似 O(1)

1. **每个集合是一棵树，根代表这个集合**
   - **`parent[x]` 指向 $x$ 的父亲**：根的父亲是它自己。
   - **`find(x)` 一路往上走到根**：两个点的根相同，就在同一个集合里。
   - **`unite(a, b)` 把一棵树的根挂到另一棵的根下面**：两个集合就合成了一个。

2. **两个优化一起用，均摊每次 $O(\alpha(n))$**

   ```cpp
   struct DSU {
       vector<int> parent, sz;
       DSU(int n) : parent(n), sz(n, 1) { iota(parent.begin(), parent.end(), 0); }
       int find(int x) {
           while (parent[x] != x) {
               parent[x] = parent[parent[x]];               // 路径减半：顺手把 x 挂到祖父上
               x = parent[x];
           }
           return x;
       }
       bool unite(int a, int b) {                           // 已经在一个集合里返回 false
           a = find(a); b = find(b);
           if (a == b) return false;
           if (sz[a] < sz[b]) swap(a, b);                   // 小的挂到大的下面
           parent[b] = a; sz[a] += sz[b];
           return true;
       }
   };
   ```

   - **路径压缩让下次走得短**：`find` 时把路过的点往上挂。这里用的是路径减半，每走一步把当前点挂到祖父上，不用递归。
   - **按大小合并让树不长高**：小树挂到大树下面，一个点每往下沉一层，它所在的集合至少大一倍，所以树高不超过 $\log n$。
   - **两个一起用，均摊每次 $O(\alpha(n))$**：$\alpha$ 是反阿克曼函数，$n$ 在任何能想到的范围里 $\alpha(n) \le 4$，当成常数。
   - **`unite` 要先找到两个根再连**：直接写 `parent[a] = b`，$a$ 不是根时，等于把它从原来的树上拆下来，原来那棵树就断了。

### 4.2 数连通块：每成功合并一次，块数减 1

1. **题目：有几个省份**
   - **题意**：[LC 547 省份数量](https://leetcode.cn/problems/number-of-provinces/)，$n$ 个城市（$n \le 200$），`isConnected[i][j] = 1` 表示两城直接相连，相连的城市属于同一个省，问有几个省，也就是有几个连通块。
   - **一开始每个城市各是一块，每成功合并一次，块数减 1。**

   ```cpp
   int findCircleNum(vector<vector<int>>& isConnected) {
       int n = isConnected.size(), groups = n;
       DSU d(n);
       for (int i = 0; i < n; i++)
           for (int j = i + 1; j < n; j++)
               if (isConnected[i][j] && d.unite(i, j)) groups--;   // 每合并一次少一个集合
       return groups;
   }
   ```

   - **复杂度 $O(n^2 \alpha(n))$**：输入本身就是 $n^2$ 的矩阵。
   - **这道题用 BFS 或 DFS 数连通块也行**：并查集的长处在边是一条条来的、中途就要回答的时候。

### 4.3 找成环的边：两端已经连通的那一条

1. **题目：树上多了一条边，删哪条**
   - **题意**：[LC 684 冗余连接](https://leetcode.cn/problems/redundant-connection/)，一棵 $n$ 个点的树（$n \le 1000$）多加了一条边，返回一条删掉以后剩下的是树的边；有多个答案时，返回输入里最后出现的那条。
   - **按输入顺序加边，第一条两端已经连通的边就是答案。**

   ```cpp
   vector<int> findRedundantConnection(vector<vector<int>>& edges) {
       DSU d(edges.size() + 1);                             // 点从 1 编号
       for (auto& e : edges)
           if (!d.unite(e[0], e[1])) return e;              // 两端早已连通，这条边成环
       return {};
   }
   ```

   - **为什么正好是“最后出现的那条”**：图里只有一个环，能删的只有环上的边。按顺序加边时，环上的边里只有最后加进来的那条，加的时候两端已经被环上别的边连通了，它就是环上在输入里最靠后的那条。
   - **复杂度 $O(n \alpha(n))$**。

### 4.4 Kruskal 最小生成树：边按权排序，不成环就要

1. **题目：连通所有点的最小总边权**
   - **题意**：[洛谷 P3366【模板】最小生成树](https://www.luogu.com.cn/problem/P3366)，无向图 $n \le 5000$ 个点、$m \le 2 \times 10^5$ 条边，求最小生成树的边权和，不连通就输出 `orz`。
   - **做法**：边按权从小到大看，两端不连通就选它，连通了就跳过（选了会成环）。

   ```cpp
   long long kruskal(int n, vector<Edge> edges, bool& connected) {
       sort(edges.begin(), edges.end(), [](const Edge& a, const Edge& b) { return a.w < b.w; });
       DSU d(n);
       long long total = 0; int used = 0;
       for (auto& e : edges)
           if (d.unite(e.u, e.v)) { total += e.w; used++; }
       connected = (used == n - 1);                         // 选够 n-1 条才连通
       return total;
   }
   ```

   - **为什么贪心是对的（交换论证）**：设当前选的边 $e$ 一端在已经连好的块 $A$ 里，一端在 $A$ 外。所有一端在 $A$ 里、一端在 $A$ 外的边里，$e$ 是最轻的：更轻的这种边已经看过，看的时候两端不连通，早就被选了，$A$ 就不会还是现在这样。如果某棵最小生成树不含 $e$，把 $e$ 加进去会成一个环。这个环从 $A$ 里出去又回来，一定还有另一条一端在 $A$ 里、一端在 $A$ 外的边 $e'$，$w_{e'} \ge w_e$。用 $e$ 换掉 $e'$，还是一棵生成树，总权不会变大。
   - **复杂度 $O(m \log m)$**：排序为主，并查集部分近似 $O(m)$。
   - **选够 $n - 1$ 条边才连通**：少于 $n - 1$ 条就输出 `orz`。

> **什么时候想到并查集**
>
> - **边一条条加进来，随时问两个点连没连通、一共有几块**：用并查集，每次近似 $O(1)$。
> - **判断无向图里加一条边会不会成环**：两端已经连通就会成环，Kruskal 靠的就是这一条。
> - **只能合并，不能拆开**：要删边时，离线倒过来做，把删边变成加边。
> - **点和点之间有数量关系**（比如“$a$ 比 $b$ 大 3”、两个点奇偶相同还是相反）：用带权并查集，每个点再记它到父亲的权，`find` 时沿路累加。

## 练习

每题后面一句话提示练的是哪一节。

**必做**

1. [LeetCode 743 网络延迟时间](https://leetcode.cn/problems/network-delay-time/)：2.2 的 Dijkstra 加懒删除。
2. [LeetCode 787 K 站中转内最便宜的航班](https://leetcode.cn/problems/cheapest-flights-within-k-stops/)：限制边数的 Bellman-Ford，每轮用上一轮的拷贝。
3. [LeetCode 207 课程表](https://leetcode.cn/problems/course-schedule/)：Kahn 或三色 DFS 判环。
4. [LeetCode 684 冗余连接](https://leetcode.cn/problems/redundant-connection/)：并查集，两端已经连通的那条边。
5. [洛谷 P3366【模板】最小生成树](https://www.luogu.com.cn/problem/P3366)：Kruskal，边排序加并查集。

**选做**

6. [LeetCode 210 课程表 II](https://leetcode.cn/problems/course-schedule-ii/)：输出拓扑序，边的方向别写反。
7. [LeetCode 547 省份数量](https://leetcode.cn/problems/number-of-provinces/)：数连通块。
8. [LeetCode 1091 二进制矩阵中的最短路径](https://leetcode.cn/problems/shortest-path-in-binary-matrix/)：网格上的 BFS，8 个方向。
9. [LeetCode 399 除法求值](https://leetcode.cn/problems/evaluate-division/)：带权并查集，每个点记它和父亲的比值。

## 和地图上其他格子的连接

- **Dijkstra 的过期条目用的是堆的懒删除**：见 [A2 上 3.5](/zh/algo/a2-stack-monotonic-stack-heap/#35-堆删不了中间的元素懒删除)。
- **DP 的状态之间本来就是一张 DAG**：A5 的每种 DP，都是按某个拓扑序去算 3.3 那样的转移。
- **树是没有环的连通图**：A3 的树上问题（遍历、直径、LCA），都是图上问题去掉环以后的简化。
