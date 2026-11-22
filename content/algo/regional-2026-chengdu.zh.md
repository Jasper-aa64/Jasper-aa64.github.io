---
title: "2026 ICPC 成都站：金牌线以内的 6 题"
date: 2026-11-22T00:00:00+08:00
slug: "regional-2026-chengdu"
description: "2026 ICPC 成都站金牌线以内的 6 题：D 两边伤害倍率相同，化成一个累计量；M 记录位置可以事后挪到 r 最大的地方；K 二分答案，可行集合只记两端；I 用 DFS 进出时刻（括号序）把一棵森林编进 [1, 2n]；C 两个约束之间的一段化成“从 1..ℓ 选 c 个不同的数凑和”；E 凸包扇形三角剖分定位，再处理落在对角线上的退化情况。每题给题意、思路、代码、复杂度和坑。"
weight: 21
math: true
toc: true
---

2026 ICPC 成都站 10 月 25 日比，319 支正式队，铜线 3 题、银线 5 题、金线 6 题。下面是金线以内的 6 题，按过题队数从多到少排：D、M、K 是签到，I、C 是银牌题，E 是金牌题。其余各站的分档题表见 [区域赛真题](/zh/algo/regionals/#chengdu-2026)。

题面在 [QOJ #4607](https://qoj.ac/contest/4607) 和 [Gym 106799](https://codeforces.com/gym/106799)。每题按“题意和范围 → 思路 → 代码 → 复杂度和坑”写。代码都用官方样例跑过，并和暴力解随机对拍过；C 和 E 还在最大规模的随机数据上跑过，都在时限内。

## 签到：D、M、K

### D Duel of Wrath：两边的伤害倍率总相同 {#d}

[QOJ #23595](https://qoj.ac/problem/23595)

1. **题意和范围**
   - **两人每回合同时出手**：A 每回合对 B 造成 $a$ 的若干倍伤害，B 对 A 造成 $b$ 的同样倍数。倍数由游戏决定：两人都正常是 1 倍，恰好一人进入 Wrath 是 2 倍，两人都进入 Wrath 是 4 倍。
   - **A 赢的条件**：B 死而 A 活着；同一回合两人都死不算赢。问不管游戏怎么选倍数，A 是不是一定赢。
   - **范围**：$a, b, h_A, h_B \le 10^{18}$，$T \le 10^5$ 组。
2. **思路**
   - **一个回合里两边的倍数一样**：A 打出 $m \cdot a$ 时，B 打出的正好是 $m \cdot b$。所以只要记“到目前为止的倍数之和” $S$：B 受到 $S \cdot a$，A 受到 $S \cdot b$。游戏每回合给 $S$ 加上 1、2 或 4。
   - **B 还活着当且仅当 $S \cdot a < h_B$**：也就是 $S \le s$，其中 $s = \lfloor (h_B - 1) / a \rfloor$。
   - **最坏情况是先把 $S$ 一点点加到 $s$，最后一回合加 4**：战斗在 $S$ 第一次超过 $s$ 时结束，结束时的 $S$ 最大是 $s + 4$。游戏可以每回合加 1 走到恰好 $s$，再一次加 4 做到这个最大值。这一刻 A 受到 $(s + 4) \cdot b$。
   - **A 必胜当且仅当 $h_A > (s + 4) \cdot b$**：结束前的 $S \le s$，A 受的伤害更小，不会提前死。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   int main() {
       int T;
       scanf("%d", &T);
       while (T--) {
           long long a, b, ha, hb;
           scanf("%lld %lld %lld %lld", &a, &b, &ha, &hb);
           __int128 s = (hb - 1) / a;                 // B 还活着时 S 最大是 s
           puts((__int128)ha > (s + 4) * b ? "YES" : "NO");
       }
   }
   ```

3. **复杂度和坑**
   - **复杂度**：每组 $O(1)$。
   - **乘法会溢出**：$(s + 4) \cdot b$ 最大约 $10^{36}$，要用 `__int128`。
   - **同归于尽不算赢**：比较用严格大于。

> **看到“对手任意选、问是否一定赢”时**
>
> - **先找对两边一样的量**：本题两人的伤害倍率总相同，整局就只剩一个累计量 $S$，对手的选择变成“$S$ 每步加 1、2、4”。
> - **再找对手的最坏一步**：结束前把伤害攒到最大、最后一步加到最多。

### M Minimum Records：记录位置可以事后挪 {#m}

[QOJ #23604](https://qoj.ac/problem/23604)

1. **题意和范围**
   - **从每个区间 $[l_i, r_i]$ 里选一个数 $a_i$**：如果 $a_i$ 严格大于前面所有数，位置 $i$ 就是一个“记录”，第一个位置一定是记录。
   - **求记录个数的最小值**：$n \le 10^6$，总和 $\le 10^6$，$-10^9 \le l_i \le r_i \le 10^9$。
2. **思路**
   - **当前最大值越大越好**：后面的位置想不成为记录，只要能选一个不超过当前最大值的数，最大值大只会更容易。
   - **能不当记录就不当**：如果 $l_i \le M$（$M$ 是当前最大值），选 $a_i = l_i$，它不是记录。
   - **必须多一个记录时，让它落在 $r$ 最大的位置**：$l_i > M$ 时，按现在的选法 $i$ 必须成为记录，记录数加 1。可这个记录不一定要放在 $i$：前面某个位置 $j$ 如果 $r_j \ge l_i$，可以回头把 $a_j$ 改成 $r_j$，让 $j$ 成为记录，$i$ 就不用了。反正多一个记录，就挑 $r$ 最大的位置，让新的最大值尽量大。
   - **所以只要记 $R$ = 目前见过的 $r$ 的最大值**：遇到 $l_i > M$，记录数加 1，$M$ 更新为 $R$（含 $r_i$）。
   - **为什么回头改是合法的**：被选中的 $j$ 满足 $r_j = R \ge l_i > M$，它确实大于之前的最大值；$j$ 和 $i$ 之间原来不是记录的位置，最大值变大以后仍然不是。
   - **例子**：区间 $[1,1], [1,100], [20,20], [30,30]$。走到第 3 个时 $20 > M = 1$，记录数变成 2，$M = R = 100$（相当于让第 2 个位置取 100 当记录），第 4 个不再是记录，答案 2。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   int main() {
       int T;
       scanf("%d", &T);
       while (T--) {
           int n;
           scanf("%d", &n);
           long long M = LLONG_MIN, R = LLONG_MIN;   // M：当前最大值；R：见过的 r 的最大值
           int cnt = 0;
           for (int i = 0; i < n; i++) {
               long long l, r;
               scanf("%lld %lld", &l, &r);
               R = max(R, r);
               if (l > M) cnt++, M = R;              // 必须多一个记录，让它落在 r 最大的位置
           }
           printf("%d\n", cnt);
       }
   }
   ```

3. **复杂度和坑**
   - **复杂度**：$O(n)$。输入有 $2 \times 10^6$ 个数，用 `scanf` 或关同步的 `cin`。
   - **第一个位置不用特判**：$M$ 初值取负无穷，第一个位置自然记成记录，$M$ 取 $r_1$。
   - **只往前看会错**：如果只在 $i$ 自己身上加记录（$M = r_i$），样例 1 会得到 3。

> **看到“贪心选了以后后面才发现不够好”时**
>
> - **把决定推迟**：先不定 $a_j$ 取多少，只记“需要时它最多能取到多少”，等后面真的需要时再回头定。本题记的就是 $R$。

### K Keep Your Distance：二分答案，可行集合只记两端 {#k}

[QOJ #23602](https://qoj.ac/problem/23602)

1. **题意和范围**
   - **给有序的 $a_1 \le \dots \le a_n$ 和间距要求 $l_2, \dots, l_n$**：选整数 $b_i$，相邻两个满足 $\lvert b_i - b_{i-1} \rvert \ge l_i$。
   - **最小化最大误差**：求 $\max_i \lvert a_i - b_i \rvert$ 的最小值。$n \le 10^5$，$a_i, l_i \le 10^9$。
2. **思路**
   - **答案有单调性，二分最大误差 $d$**：$d$ 越大，每个 $b_i$ 能选的范围 $[a_i - d, a_i + d]$ 越宽，能满足的一定还能满足。判定“误差 $d$ 行不行”，找第一个行的 $d$。
   - **判定时维护 $b_i$ 的可行取值集合 $S_i$**：$S_1 = [a_1 - d, a_1 + d]$。$x$ 在 $S_i$ 里，要求 $x \in [L_i, R_i]$（$L_i = a_i - d$，$R_i = a_i + d$），并且 $S_{i-1}$ 里有某个 $y$ 离 $x$ 至少 $l_i$。
   - **只和 $S_{i-1}$ 的两端有关**：存在这样的 $y$，当且仅当 $\min S_{i-1} \le x - l_i$ 或 $\max S_{i-1} \ge x + l_i$。所以
     $$S_i = [L_i,\ \min(R_i, mx - l_i)] \ \cup\ [\max(L_i, mn + l_i),\ R_i],$$
     其中 $mn$、$mx$ 是 $S_{i-1}$ 的两端。
   - **$S_i$ 可能断成两段，但不影响**：下一步只用它的最小值和最大值，中间缺一块没关系。哪一步两段都空，$d$ 就不行。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;
   int n;
   vector<ll> a, l;
   bool ok(ll d) {
       ll mn = a[0] - d, mx = a[0] + d;               // S_1 = [L_1, R_1]
       for (int i = 1; i < n; i++) {
           ll L = a[i] - d, R = a[i] + d;
           ll nmn = LLONG_MAX, nmx = LLONG_MIN;
           if (L <= min(R, mx - l[i])) nmn = min(nmn, L), nmx = max(nmx, min(R, mx - l[i]));  // 左边那段
           if (max(L, mn + l[i]) <= R) nmn = min(nmn, max(L, mn + l[i])), nmx = max(nmx, R);  // 右边那段
           if (nmn > nmx) return false;
           mn = nmn, mx = nmx;
       }
       return true;
   }
   int main() {
       int T;
       scanf("%d", &T);
       while (T--) {
           scanf("%d", &n);
           a.assign(n, 0), l.assign(n, 0);
           for (auto &x : a) scanf("%lld", &x);
           for (int i = 1; i < n; i++) scanf("%lld", &l[i]);
           ll lo = 0, hi = 2e9;                        // 第一个为真
           while (lo < hi) {
               ll mid = (lo + hi) / 2;
               if (ok(mid)) hi = mid; else lo = mid + 1;
           }
           printf("%lld\n", lo);
       }
   }
   ```

3. **复杂度和坑**
   - **复杂度**：$O(n \log w)$，$w$ 是二分的上界。
   - **上界取多少**：$d = 10^9$ 时让 $b$ 交替取 $a_i - d$ 和 $a_i + d$，相邻两个至少差 $2d - 10^9 = 10^9 \ge l_i$，一定可行。代码里取 $2 \times 10^9$ 留余量，全程用 `long long`。
   - **想成“$b_i$ 的可行范围是一个区间”会错**：两段之间可能有缺口，可行集合不是区间；好在转移只用两端，不需要存整个集合。

> **看到“最小化最大值”时**
>
> - **先想二分答案**：把“最小化”变成“给定上限，判断行不行”。
> - **判定里只留转移用得上的信息**：本题可行集合可能断开，但下一步只看最小值和最大值，状态就是两个数。

## 银牌：I、C

### I Invisible Edges：用 DFS 的进出时刻编码一片森林 {#i}

[QOJ #23600](https://qoj.ac/problem/23600)

1. **题意和范围**
   - **程序运行两遍**：第一遍拿到一片森林（$n$ 个点，$m < n$ 条边），给每个点写一个 $[1, 2n]$ 里的数 $a_u$。之后点被任意重新编号，第二遍只拿到新编号下每个点上的数，要还原出所有边（用新编号）。
   - **范围**：$n \le 2 \times 10^5$，总和 $\le 2 \times 10^5$。
2. **思路**
   - **值域是 $2n$，提示用括号序**：DFS 一片森林，进入一个点记一次时刻、离开一个点也记一次，一共正好 $2n$ 个时刻。
   - **每个点只存它的进入时刻**：$a_u$ = 进入 $u$ 时的时刻。没有点存的时刻，就是某个点的离开时刻。重新编号不改变点上的数，所以第二遍仍然知道每个时刻发生了什么。
   - **第二遍按时刻重放 DFS**：时刻 $t$ 从 1 走到 $2n$。如果有点 $v$ 的数是 $t$，说明这时进入 $v$：栈顶就是 $v$ 的父亲，记下这条边，再把 $v$ 压栈；如果没有，说明这时栈顶的点离开，弹栈。
   - **为什么栈顶就是父亲**：DFS 进入 $v$ 时，栈里正好是从根到 $v$ 的父亲那条路径。森林里一棵树走完，栈就空了，下一棵树的根进来时栈是空的，不会接错边。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   int main() {
       char role[8];
       int T;
       scanf("%s %d", role, &T);
       while (T--) {
           int n;
           if (role[0] == 'c') {                       // 第一遍：按 DFS 进入时刻编号
               int m;
               scanf("%d %d", &n, &m);
               vector<vector<int>> adj(n + 1);
               for (int i = 0; i < m; i++) {
                   int u, v;
                   scanf("%d %d", &u, &v);
                   adj[u].push_back(v), adj[v].push_back(u);
               }
               vector<int> a(n + 1, 0), it(n + 1, 0), par(n + 1, 0);
               int t = 0;
               for (int s = 1; s <= n; s++) {
                   if (a[s]) continue;
                   vector<int> st = {s};
                   a[s] = ++t;                         // 进入 s：时刻 +1
                   while (!st.empty()) {
                       int u = st.back();
                       if (it[u] < (int)adj[u].size()) {
                           int v = adj[u][it[u]++];
                           if (v == par[u]) continue;
                           par[v] = u, a[v] = ++t, st.push_back(v);
                       } else {
                           ++t, st.pop_back();         // 离开 u：时刻也 +1，但不记
                       }
                   }
               }
               for (int i = 1; i <= n; i++) printf("%d%c", a[i], " \n"[i == n]);
           } else {                                    // 第二遍：按时刻重放 DFS
               scanf("%d", &n);
               vector<int> who(2 * n + 1, 0);
               for (int i = 1; i <= n; i++) {
                   int b;
                   scanf("%d", &b);
                   who[b] = i;
               }
               vector<int> st;
               vector<pair<int, int>> e;
               for (int t = 1; t <= 2 * n; t++) {
                   if (who[t]) {                       // 有点在 t 进入：它是栈顶的儿子
                       if (!st.empty()) e.push_back({st.back(), who[t]});
                       st.push_back(who[t]);
                   } else if (!st.empty()) {
                       st.pop_back();                  // 没人进入：栈顶离开
                   }
               }
               printf("%d\n", (int)e.size());
               for (auto [u, v] : e) printf("%d %d\n", u, v);
           }
       }
   }
   ```

3. **复杂度和坑**
   - **复杂度**：两遍都是 $O(n)$。
   - **离开时刻也要计数**：只给进入计时的话值域只有 $n$，第二遍分不清什么时候该弹栈。
   - **DFS 写成显式栈**：一条链有 $2 \times 10^5$ 个点，递归可能爆栈。`it[u]` 记 $u$ 的邻接表走到哪了。
   - **森林要从每个没访问过的点各起一次 DFS**：时刻在树之间连续计数，不要清零。

> **看到“值域给 $2n$、要把一棵树编进点权”时**
>
> - **先想括号序 / 欧拉序**：DFS 每个点进一次、出一次，正好 $2n$ 个时刻，进入时刻存在点上，离开时刻用“空着的时刻”表示。

### C Counting Arrays：一段化成“从 1..ℓ 选几个不同的数凑和” {#c}

[QOJ #23594](https://qoj.ac/problem/23594)

1. **题意和范围**
   - **数组从 0 开始，每步加 0 或加 1**：$a_1 = 0$，$a_{i+1} - a_i \in \{0, 1\}$。不加约束时有 $2^{n-1}$ 个。
   - **给 $m$ 个前缀和约束** $s_{p_j} = v_j$，求满足全部约束的数组个数，模 998244353。
   - **范围**：$n \le 100$，但 $T \le 10^4$ 组，$n$ 的总和没有限制；$v_j \le 10^9$。
2. **思路**
   - **相邻两个约束之间单独算**：设上一个约束在位置 $L$、下一个在 $R$，段长 $\ell = R - L$。这一段内的和 $a_{L+1} + \dots + a_R = v_R - v_L$ 是已知的。
   - **把这段写成“起点 + 增量”**：设 $a_L = x$，段内第 $k$ 个数是 $x + c_k$，$c_k$ 是这一段前 $k$ 步里“加 1”的次数。段内和等于 $\ell x + \sum_{k=1}^{\ell} c_k$。
   - **$\sum c_k$ 是一组不同的数之和**：段内第 $t$ 步加了 1，它会让后面的 $c_t, c_{t+1}, \dots, c_\ell$ 都多 1，一共贡献 $\ell - t + 1$。各步的贡献互不相同、取值在 $1..\ell$，所以
     $$\sum_{k=1}^{\ell} c_k = \text{从 } \{1, 2, \dots, \ell\} \text{ 里选出的那几个数之和},$$
     选了几个数，就是这一段加了几次 1，也就是 $a_R - a_L = c$。
   - **预处理 $g[\ell][c][w]$**：从 $1..\ell$ 里选 $c$ 个不同的数、和为 $w$ 的方案数。按“选不选 $\ell$”做 0/1 背包：
     $$g[\ell][c][w] = g[\ell-1][c][w] + g[\ell-1][c-1][w-\ell].$$
   - **在约束位置上做 DP**：状态是约束位置上的值 $x$。从 $a_L = x$ 走到 $a_R = x + c$ 的方案数是 $g[\ell][c][(v_R - v_L) - \ell x]$。
   - **两头**：位置 1 当成一个约束 $s_1 = 0$、$a_1 = 0$；如果题目给了 $p = 1$，要求 $v = 0$。最后一个约束之后的位置没有限制，乘 $2^{\,n - p_{\text{last}}}$。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;
   const int MOD = 998244353, N = 100;
   // g[l][c][w]：从 1..l 里选 c 个不同的数，和为 w 的方案数
   vector<vector<int>> g[N + 1];
   int G(int l, int c, ll w) {
       if (c < 0 || c > l || w < 0 || w >= (ll)g[l][c].size()) return 0;
       return g[l][c][w];
   }
   int main() {
       g[0] = {{1}};
       for (int l = 1; l <= N; l++) {
           g[l].resize(l + 1);
           for (int c = 0; c <= l; c++) {
               int top = c * (2 * l - c + 1) / 2;      // 选最大的 c 个数的和
               g[l][c].assign(top + 1, 0);
               for (int w = 0; w <= top; w++) {
                   ll v = G(l - 1, c, w) + G(l - 1, c - 1, w - l);   // 不选 l / 选 l
                   g[l][c][w] = v % MOD;
               }
           }
       }
       int T;
       scanf("%d", &T);
       while (T--) {
           int n, m;
           scanf("%d %d", &n, &m);
           vector<ll> dp(n, 0);                        // dp[x]：上一个约束位置上 a = x 的方案数
           dp[0] = 1;
           int lastp = 1;
           ll lastv = 0;
           bool bad = false;
           for (int j = 0; j < m; j++) {
               int p;
               ll v;
               scanf("%d %lld", &p, &v);
               if (bad) continue;
               if (p == 1) { if (v != 0) bad = true; continue; }
               int len = p - lastp;
               ll need = v - lastv;                    // a_{L+1} + ... + a_R
               vector<ll> nd(n, 0);
               for (int x = 0; x < n; x++) {
                   if (!dp[x]) continue;
                   ll w = need - (ll)len * x;          // 去掉每项都有的 x
                   if (w < 0) continue;
                   for (int c = 0; c <= len && x + c < n; c++)
                       nd[x + c] = (nd[x + c] + dp[x] * G(len, c, w)) % MOD;
               }
               dp = nd, lastp = p, lastv = v;
           }
           ll ans = 0;
           if (!bad) {
               ll pw = 1;
               for (int i = 0; i < n - lastp; i++) pw = pw * 2 % MOD;   // 最后一个约束之后随便走
               for (int x = 0; x < n; x++) ans = (ans + dp[x]) % MOD;
               ans = ans * pw % MOD;
           }
           printf("%lld\n", ans);
       }
   }
   ```

3. **复杂度和坑**
   - **预处理**：$g$ 一共约 $1.3 \times 10^7$ 项（对每个 $\ell$、$c$，$w$ 最多到 $\ell c$），时间和空间都只做一次，约 50 MB。
   - **每组 $O(n^2)$**：每段对每个 $x$ 枚举 $c \le \ell$，各段 $\ell$ 加起来不超过 $n$。$10^4$ 组 $n = 100$ 也只有约 $10^8$ 次运算。
   - **不要每组重算 $g$**：$n$ 的总和没限制，每组 $O(n^4)$ 会超时。和输入无关的表放在读入之前算一次。
   - **$v$ 可以很大**：$w$ 超出表的范围或为负就是 0 种，`G` 里统一判掉。

> **看到“$n$ 很小，但组数很多、$n$ 的总和不限”时**
>
> - **把和输入无关的部分预处理**：本题 $g$ 只依赖段长，算一次全组共用，每组只剩 $O(n^2)$ 的 DP。
>
> **看到“0/1 步长、给前缀和”时**
>
> - **把和拆成“每一步的贡献”**：第 $t$ 步加 1 贡献 $\ell - t + 1$，前缀和约束就变成“选几个不同的数凑一个和”的背包。

## 金牌：E

### E Enclose the Point：凸包扇形定位，再处理落在对角线上的情况 {#e}

[QOJ #23596](https://qoj.ac/problem/23596)

1. **题意和范围**
   - **给 $n$ 个不同的点，$q$ 次询问一个点 $P$**：用其中一些点当顶点围一个简单多边形，把 $P$ 严格围在内部，顶点数最少。没有就输出 -1。
   - **范围**：$n, q \le 10^5$（总和），坐标绝对值 $\le 10^9$。
2. **答案只有 -1、3、4 三种**
   - **-1**：$P$ 不严格在所有点的凸包内部。用这些点围的多边形都在凸包里，$P$ 在凸包外或边界上就围不住；反过来，$P$ 严格在凸包内部时，凸包本身就是一个合法的多边形。
   - **3**：有三个点围成的三角形严格包含 $P$。
   - **4**：$P$ 严格在凸包内，但所有点都在经过 $P$ 的两条直线上。这时任何三角形都有两个顶点在同一条直线上，而这条直线经过 $P$：$P$ 要么落在这条边上，要么在三角形外，所以没有三角形。四条射线上各取一个点围成的四边形能严格包住 $P$。
   - **其余情况都能找到三角形**：下面的构造过程就是证明，它在每种情况下都给出一个三角形，除了上面“两条直线”的情况。
3. **思路：以凸包的一个顶点为扇心，二分定位**
   - **求凸包，去掉共线的点**：逆时针得到 $h_0, h_1, \dots, h_{m-1}$。凸包退化成线段（$m < 3$）时答案都是 -1。
   - **从 $h_0$ 连到其他顶点，把凸包切成扇形三角形** $h_0 h_i h_{i+1}$：二分出 $P$ 落在哪个扇区，再判断 $P$ 是否严格在凸包内部（在 $h_0h_1$ 左侧、$h_0h_{m-1}$ 右侧、$h_ih_{i+1}$ 左侧）。
   - **$P$ 严格在三角形 $h_0 h_i h_{i+1}$ 内**：答案 3，就是这个三角形。
   - **$P$ 落在对角线 $h_0 h_i$ 上**（记 $A = h_0$，$X = h_i$）：取 $X$ 在凸包上的两个邻居 $F = h_{i-1}$、$D = h_{i+1}$。线段 $AX$ 一定穿过线段 $FD$，交点记作 $Y$。
     - **$P$ 在 $A$ 和 $Y$ 之间**：$P$ 严格在三角形 $AFD$ 内。
     - **$P$ 在 $Y$ 和 $X$ 之间**：$P$ 严格在三角形 $XFD$ 内。
     - **$P$ 恰好是交点 $Y$**：$P$ 同时在直线 $AX$ 和 $FD$ 上，四个点都用不上，要找第五个不在这两条直线上的点 $E$。
   - **找 $E$**：凸包顶点里任意三个不共线，所以直线 $AX$ 上只有 $A$、$X$ 两个顶点，$FD$ 上只有 $F$、$D$。凸包有 5 个以上顶点时，随便取另一个顶点就是 $E$。凸包只有 4 个顶点时，这种交点只有一个（两条对角线的交点），扫一遍所有点找 $E$，整组只扫一次；找不到，就是“所有点在两条直线上”，答案 4，输出凸包的四个顶点。
   - **有了 $E$ 怎么取三角形**：两条直线把平面分成四块，$E$ 在其中一块里。在 $A$、$X$ 中取和 $E$ 隔着直线 $FD$ 的那个，在 $F$、$D$ 中取和 $E$ 隔着直线 $AX$ 的那个，这两个点和 $E$ 围成的三角形严格包含 $P$：从 $P$ 看出去，三个方向两两之间的夹角都小于 180°。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;
   typedef long long ll;
   typedef __int128 LL;
   struct P { ll x, y; int id; };
   P operator-(P a, P b) { return {a.x - b.x, a.y - b.y, 0}; }
   LL cross(P a, P b) { return (LL)a.x * b.y - (LL)a.y * b.x; }
   int sgn(LL v) { return (v > 0) - (v < 0); }
   int side(P a, P b, P q) { return sgn(cross(b - a, q - a)); }   // q 在有向直线 ab 的左 1、右 -1、线上 0

   int main() {
       int T;
       scanf("%d", &T);
       while (T--) {
           int n, q;
           scanf("%d %d", &n, &q);
           vector<P> p(n);
           for (int i = 0; i < n; i++) scanf("%lld %lld", &p[i].x, &p[i].y), p[i].id = i + 1;

           // 1. 凸包（Andrew，去掉共线点，逆时针）
           vector<P> s = p;
           sort(s.begin(), s.end(), [](P a, P b) { return a.x != b.x ? a.x < b.x : a.y < b.y; });
           vector<P> h(2 * n);
           int k = 0;
           for (int i = 0; i < n; i++) {
               while (k >= 2 && side(h[k - 2], h[k - 1], s[i]) <= 0) k--;
               h[k++] = s[i];
           }
           for (int i = n - 2, t = k + 1; i >= 0; i--) {
               while (k >= t && side(h[k - 2], h[k - 1], s[i]) <= 0) k--;
               h[k++] = s[i];
           }
           h.resize(max(1, k - 1));
           int m = h.size();

           // 凸包是四边形时，“对角线交点”这种情况要找一个不在两条对角线上的点，整组只算一次
           int extra = -2;                              // -2 没算过，-1 没有，否则是下标
           auto findExtra = [&]() {
               if (extra != -2) return extra;
               extra = -1;
               for (auto &c : p)
                   if (side(h[0], h[2], c) != 0 && side(h[1], h[3], c) != 0) { extra = c.id - 1; break; }
               return extra;
           };

           while (q--) {
               P Q;
               scanf("%lld %lld", &Q.x, &Q.y);
               // 2. 不严格在凸包内部就无解
               bool in = m >= 3 && side(h[0], h[1], Q) > 0 && side(h[0], h[m - 1], Q) < 0;
               int i = 1;
               if (in) {                                // 以 h[0] 为扇心二分：最后一个 side(h0, h_i, Q) >= 0 的 i
                   int lo = 1, hi = m - 2;
                   while (lo < hi) {
                       int mid = (lo + hi + 1) / 2;
                       if (side(h[0], h[mid], Q) >= 0) lo = mid; else hi = mid - 1;
                   }
                   i = lo;
                   in = side(h[i], h[i + 1], Q) > 0;
               }
               if (!in) { puts("-1"); continue; }
               // 3. 严格落在扇形三角形 h0 h_i h_{i+1} 里
               if (side(h[0], h[i], Q) != 0) {
                   printf("3\n%d %d %d\n", h[0].id, h[i].id, h[i + 1].id);
                   continue;
               }
               // 4. 落在对角线 A X 上：看 Q 在 F D 的哪一侧
               P A = h[0], X = h[i], F = h[i - 1], D = h[i + 1];
               int sq = side(F, D, Q), sa = side(F, D, A);
               if (sq == sa) { printf("3\n%d %d %d\n", A.id, F.id, D.id); continue; }
               if (sq != 0) { printf("3\n%d %d %d\n", X.id, F.id, D.id); continue; }
               // 5. Q 恰是 AX 与 FD 的交点：找第三条线上的点 E
               int e = -1;
               if (m >= 5) e = h[i + 2 <= m - 1 ? i + 2 : i - 2].id - 1;   // 凸包上另一个顶点，不在两条线上
               else e = findExtra();
               if (e < 0) { printf("4\n%d %d %d %d\n", A.id, F.id, X.id, D.id); continue; }
               P E = p[e];
               P u = side(F, D, E) == side(F, D, A) ? X : A;   // 和 E 隔着 FD 的那个
               P v = side(A, X, E) == side(A, X, F) ? D : F;   // 和 E 隔着 AX 的那个
               printf("3\n%d %d %d\n", E.id, u.id, v.id);
           }
       }
   }
   ```

   - **第 1 步**：Andrew 单调链求凸包，`<= 0` 把共线的点一起弹掉，凸包顶点任意三个不共线，后面“直线上只有两个顶点”才成立。
   - **第 2 步**：二分找最后一个“$P$ 在 $h_0h_i$ 左侧或线上”的 $i$，$P$ 就在扇区 $h_0h_ih_{i+1}$ 里；再看它是否严格在凸包边 $h_ih_{i+1}$ 的左侧。
   - **第 3–5 步**：对应上面的三种情况：严格在扇形三角形里、在对角线上但不在交点、恰在交点。

4. **复杂度和坑**
   - **复杂度**：每组凸包 $O(n \log n)$，每次询问 $O(\log n)$，四边形凸包时最多再扫一次 $O(n)$。
   - **凸包要去掉共线点**：留着共线点，扇区可能退化成面积为 0 的三角形，对角线也可能和凸包边重合。
   - **$P$ 在凸包边界上是 -1**：严格在内部才行，判断全部用严格不等号。
   - **叉积的范围**：坐标差到 $2 \times 10^9$，乘积到 $4 \times 10^{18}$，相减可能到 $8 \times 10^{18}$，贴着 `long long` 的上限，代码里用 `__int128` 算。
   - **输入点可能和 $P$ 重合**：这样的点在两条直线上，不会被选成 $E$，也不会是凸包顶点（$P$ 严格在内部）。

> **看到“几何构造、问最少几个点”时**
>
> - **先把答案的可能值缩小**：本题证明了只有 -1、3、4，问题就变成“什么时候 3 做不到”。
> - **一般位置先解决，退化情况单独列**：扇形三角剖分处理一般情况，再一条条处理“落在对角线上”“恰在交点上”“所有点在两条线上”。退化情况要和暴力对拍，手推很容易漏。
