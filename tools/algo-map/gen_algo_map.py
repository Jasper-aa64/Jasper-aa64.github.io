#!/usr/bin/env python3
"""Algorithm map for the algorithms hub (/algo/), entered from a small button on the reference page.

One data definition below generates four files:
  static/images/algo/algo-map.{zh,en}.svg   the static map shown on the hub page
  static/maps/algo-map.{zh,en}.html         the interactive map (click a box, step through a path)

The page shell (CSS, JS, text measuring) is shared with tools/arch-map/gen_arch_map.py.
To change the map, edit the node lists / TOURS and run from the repo root:
  python -X utf8 tools/algo-map/gen_algo_map.py
It prints a warning for every line of text that looks wider than its box.
"""
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('arch', os.path.join(HERE, '..', 'arch-map', 'gen_arch_map.py'))
arch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arch)
esc, text_w, tag_text = arch.esc, arch.text_w, arch.tag_text

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
W = 1600
FONT = arch.FONT
LANGS = ('zh', 'en')
WARNINGS = arch.WARNINGS


def post(slug):
    # The algorithm notes are English-only posts, so both languages link to the English page.
    return '/posts/' + slug + '/'


# ---------------------------------------------------------------- layout
X0 = 24                      # left edge of the bands
BAND_W = W - 2 * X0
GRID_W, GRID_GAP = 180, 12   # bands A and B: 8 columns
GRID_H, GRID_ROW_GAP = 76, 12
LANE_GAP = 16                # band C: three lanes, two columns each
LANE_W = (BAND_W - 2 * LANE_GAP) // 3
COL_W, COL_PAD = (LANE_W - 36) // 2, 12
C_H, C_GAP = 92, 26

Y_A = 124
Y_B = Y_A + 40 + 2 * GRID_H + GRID_ROW_GAP + 14 + 14
Y_C = Y_B + 40 + 2 * GRID_H + GRID_ROW_GAP + 14 + 14
Y_C_BOX = Y_C + 70
H_C = 70 + 6 * C_H + 5 * C_GAP + 16
H = Y_C + H_C + 64

NODES = {}


def grid_box(band_y, col, row):
    return (X0 + 12 + col * (GRID_W + GRID_GAP), band_y + 40 + row * (GRID_H + GRID_ROW_GAP), GRID_W, GRID_H)


def lane_box(lane, col, row):
    lx = X0 + lane * (LANE_W + LANE_GAP)
    return (lx + COL_PAD + col * (COL_W + COL_PAD), Y_C_BOX + row * (C_H + C_GAP), COL_W, C_H)


def node(nid, box, cls, zh, en, tags=()):
    """zh / en = (title, [lines], [panel sentences]); tags = [(label, slug)] shared by both languages."""
    t = [[(label, post(slug))] for label, slug in tags]
    NODES[nid] = dict(box=box, cls=cls,
                      zh=dict(title=zh[0], lines=zh[1], panel=zh[2], tags=t),
                      en=dict(title=en[0], lines=en[1], panel=en[2], tags=t))


# ---------------------------------------------------------------- band A: interview core (write it, fast and right)
A = [
    ('a_cx', 0, 0, ('复杂度 · STL', ['看数据范围定复杂度', '容器的复杂度要背熟'],
                    ['先看数据范围：n 到 1e5 要 O(n log n)，1e6 要 O(n)，20 以内可以指数。',
                     '面试和比赛的第一步都是这一步；vector、map、priority_queue、unordered_map 的复杂度要背熟。']),
     ('Complexity · STL', ['Limits pick the bound', 'Know container costs'],
      ['Read the limits first: n up to 1e5 needs O(n log n), 1e6 needs O(n), around 20 allows exponential.',
       'This is the first step in interviews and contests alike; know the costs of vector, map, priority_queue and unordered_map.'])),
    ('a_bs', 1, 0, ('二分', ['有序里找边界', '答案单调就二分答案'],
                    ['答案单调（能做到 x，就能做到比 x 更松的）就二分答案，把求最优变成判定可行。',
                     '固定用一种写法（左闭右开），边界才不会错。']),
     ('Binary search', ['Boundaries in sorted data', 'Search on the answer'],
      ['If feasibility is monotone in the answer, binary-search the answer and turn optimisation into a yes/no check.',
       'Stick to one style (half-open) so the boundaries never go wrong.'])),
    ('a_tp', 2, 0, ('双指针 · 滑窗', ['两端都只往右走', '总共 O(n)'],
                    ['区间合法与否随右端点单调时，左端点也只会往右走，总共 O(n)。',
                     '最长无重复子串、和至少为 k 的最短子数组都是这一类。']),
     ('Two pointers', ['Both ends only move right', 'O(n) in total'],
      ['When validity is monotone in the right end, the left end only moves right as well: O(n) in total.',
       'Longest substring without repeats and shortest subarray with sum at least k are this pattern.'])),
    ('a_ps', 3, 0, ('前缀和 · 差分', ['区间和 O(1)', '区间加 O(1)'],
                    ['区间和用前缀和，区间加用差分，二维同理。',
                     '“和为 k 的子数组有几个”用前缀和加哈希表。']),
     ('Prefix sums', ['O(1) range sum', 'O(1) range add'],
      ['Prefix sums give range sums, difference arrays give range adds, in 2D as well.',
       '"How many subarrays sum to k" is prefix sums plus a hash map.'])),
    ('a_st', 4, 0, ('栈 · 单调栈', ['下一个更大的数', '单调队列：滑窗最值'],
                    ['单调栈求每个数左右第一个更大或更小的数，单调队列求滑窗最值，都是均摊 O(n)。',
                     '括号匹配、表达式求值用普通栈。']),
     ('Monotonic stack', ['Next greater element', 'Deque: window max'],
      ['A monotonic stack finds the nearest greater or smaller element on each side; a monotonic deque gives sliding-window maxima; both amortised O(n).',
       'Bracket matching and expression evaluation use a plain stack.'])),
    ('a_hp', 5, 0, ('堆 · 哈希表', ['Top-K；动态取最值', '查有没有、数几次'],
                    ['动态取最值用堆，Top-K 用大小为 K 的堆；查有没有、数出现几次用哈希表。',
                     'HFT 面试常拿这两个问行情去重、订单簿最优价。']),
     ('Heap · hash map', ['Top-K, running max', 'Membership and counts'],
      ['A heap gives the running min or max, a size-K heap gives top-K; a hash map answers membership and counts.',
       'HFT interviews use these for de-duplicating market data and best bid/ask.'])),
    ('a_gr', 6, 0, ('排序 · 贪心', ['排序后取局部最优', '交换论证说明对'],
                    ['贪心一般先排序，再用交换论证说明“换一下不会更好”。区间调度、合并区间是高频题。',
                     '快排和归并要能手写，归并顺带求逆序对。']),
     ('Sorting · greedy', ['Sort, then pick locally', 'Prove by exchange'],
      ['Greedy usually starts with a sort, and an exchange argument shows that swapping never helps. Interval scheduling and merging intervals come up a lot.',
       'Be able to write quicksort and merge sort by hand; merge sort also counts inversions.'])),
    ('a_bit', 7, 0, ('位运算', ['lowbit；枚举子集', '异或的性质'],
                     ['x & -x 取最低位的 1；枚举 m 的子集：for (s = m; s; s = (s - 1) & m)。',
                      '异或自反，找只出现一次的数。这些是状压 DP 的基础。']),
     ('Bit tricks', ['lowbit, subset loops', 'XOR identities'],
      ['x & -x isolates the lowest set bit; loop over the subsets of m with s = (s - 1) & m.',
       'XOR cancels itself, which finds the element that appears once. Bitmask DP builds on these.'])),
    ('a_srch', 0, 1, ('搜索 · 回溯', ['BFS：最少步数', 'DFS：枚举 + 剪枝'],
                      ['无权图最短路用 BFS；排列、组合、子集用 DFS 回溯，剪枝决定能不能过。',
                       '网格题、岛屿数量是高频题。']),
     ('Search', ['BFS: fewest steps', 'DFS: enumerate + prune'],
      ['BFS gives shortest paths on unweighted graphs; DFS with backtracking enumerates permutations, combinations and subsets, and pruning decides whether it passes.',
       'Grid problems and counting islands come up a lot.'])),
    ('a_tree', 1, 1, ('树', ['遍历 · 直径 · LCA', '递归返回值的设计'],
                      ['二叉树的前、中、后序和层序遍历要能不用递归写出来；树的直径两遍 DFS；LCA 用倍增。',
                       '面试里的树题，难点大多在递归函数返回什么。']),
     ('Trees', ['Traversal, diameter, LCA', 'Design the return value'],
      ['Write pre-, in-, post-order and level-order traversals without recursion too; the diameter takes two DFS passes; LCA uses binary lifting.',
       'Most interview tree problems come down to what the recursive function returns.'])),
    ('a_graph', 2, 1, ('图 · 最短路', ['Dijkstra · 拓扑排序', '有负权：Bellman-Ford'],
                       ['非负权用 Dijkstra（堆优化 O(m log n)），有负权用 Bellman-Ford；有向无环图先拓扑排序再 DP。',
                        '课程表、任务依赖就是拓扑排序。']),
     ('Shortest paths', ['Dijkstra, topological sort', 'Negative: Bellman-Ford'],
      ['Dijkstra with a heap for non-negative weights (O(m log n)), Bellman-Ford with negative ones; on a DAG, sort topologically and then DP.',
       'Course schedules and task dependencies are topological sorts.'])),
    ('a_dsu', 3, 1, ('并查集', ['动态加边问连通', 'Kruskal 最小生成树'],
                     ['路径压缩加按秩合并，每次操作几乎是常数。',
                      '动态加边问两点是否连通、Kruskal 求最小生成树都用它。']),
     ('Union-find', ['Online connectivity', "Kruskal's MST"],
      ['With path compression and union by rank, each operation is almost constant time.',
       "Use it for connectivity as edges are added, and for Kruskal's minimum spanning tree."])),
    ('a_dp1', 4, 1, ('DP：线性 · 背包', ['先定状态的含义', '再写转移和边界'],
                     ['先定状态的含义，再写转移和边界。',
                      '最长上升子序列、编辑距离、01 背包和完全背包是必会的模板，背包要会压成一维。']),
     ('DP: linear, knapsack', ['Define the state first', 'Then transitions, bases'],
      ['Fix what a state means first, then the transitions and the base cases.',
       'LIS, edit distance, 0/1 and unbounded knapsack are must-know templates; compress knapsack to one dimension.'])),
    ('a_dp2', 5, 1, ('DP：区间 · 树 · 状压', ['按长度、子树、集合', '状压：n 到 20 左右'],
                     ['区间 DP 按长度从小到大算；树形 DP 在 DFS 回溯时合并子树；状压 DP 用一个整数表示集合，n 到 20 左右。']),
     ('DP: tree, bitmask', ['Interval, subtree, set', 'Bitmask: n up to ~20'],
      ['Interval DP goes by increasing length; tree DP merges subtrees on the way back up the DFS; bitmask DP encodes a set as an integer, for n up to about 20.'])),
    ('a_str', 6, 1, ('字符串', ['KMP · 哈希 · Trie', '01-Trie：最大异或'],
                     ['KMP 求前缀函数做匹配；字符串哈希 O(1) 比较两个子串；Trie 存前缀，按位存的 01-Trie 求最大异或。']),
     ('Strings', ['KMP, hashing, trie', '0/1 trie: max XOR'],
      ['KMP matches with the prefix function; string hashing compares substrings in O(1); a trie stores prefixes, and a bitwise 0/1 trie finds the maximum XOR.'])),
    ('a_design', 7, 1, ('设计题', ['LRU · 订单簿 · 限流', '考数据结构选型'],
                        ['HFT 面试常考：LRU（哈希表 + 双向链表，O(1)）、订单簿（按价格有序的表，每一档一个队列）、滑动窗口限流。',
                         '考的是选什么数据结构、每个操作多少复杂度。']),
     ('Design', ['LRU, order book, limiter', 'Choosing the structure'],
      ['Common in HFT interviews: an LRU cache (hash map + doubly linked list, O(1)), an order book (a price-ordered map with a queue per level), a sliding-window rate limiter.',
       'What is tested is which structure you pick and the cost of each operation.'])),
]
for nid, col, row, zh, en in A:
    node(nid, grid_box(Y_A, col, row), 'hot', zh, en)

# ---------------------------------------------------------------- band B: quick pass (know what it solves)
B = [
    ('b_seg', 0, 0, ('树状数组 · 线段树', ['区间查、区间改', '都是 O(log n)'],
                     ['单点改、区间查用树状数组；区间改、区间查，或者要维护复杂信息，用线段树加懒标记。',
                      '题里有“多次修改 + 多次区间询问”就想到它。']),
     ('Segment trees', ['Fenwick and segment tree', 'Range ops in O(log n)'],
      ['Point update with range query: Fenwick tree; range update with range query, or richer information: segment tree with lazy tags.',
       'Think of it whenever a problem mixes many updates with many range queries.'])),
    ('b_bst', 1, 0, ('平衡树 · pb_ds', ['动态第 k 小、排名', '比赛优先用库'],
                     ['要动态求第 k 小、求排名，用 pb_ds 的 tree 或手写 Treap。比赛里优先用库。']),
     ('Balanced BST', ['k-th element, rank', 'Prefer pb_ds in contests'],
      ['For a dynamic k-th smallest or rank, use the pb_ds tree or a hand-written treap; prefer the library in contests.'])),
    ('b_tree', 2, 0, ('树上进阶', ['树剖 · 换根 · 点分治', '路径改查、全根统计'],
                      ['路径上修改、查询用树链剖分套线段树；每个点都当一次根算答案用换根 DP；统计满足条件的路径用点分治。']),
     ('Advanced trees', ['HLD, rerooting, centroid', 'Path ops, every root'],
      ['Path updates and queries: heavy-light decomposition over a segment tree; an answer for every root: rerooting DP; counting paths: centroid decomposition.'])),
    ('b_conn', 3, 0, ('连通性', ['Tarjan · 缩点', '2-SAT：二选一约束'],
                      ['有向图的强连通分量缩成 DAG 再 DP；无向图求割点和桥；一堆“二选一”约束是 2-SAT。']),
     ('Connectivity', ['Tarjan, condensation', '2-SAT: pick-one rules'],
      ['Condense strongly connected components into a DAG and DP on it; find cut vertices and bridges; a set of either-or constraints is 2-SAT.'])),
    ('b_flow', 4, 0, ('网络流 · 二分图', ['最大流 · 匹配 · 费用流', '难在建图'],
                      ['分配、匹配、最小割都能建模成网络流，Dinic 写熟一份板子。难点在建图，不在算法本身。']),
     ('Flows · matching', ['Max flow, min-cost flow', 'Modelling is the hard part'],
      ['Assignment, matching and min-cut problems become flow networks; keep one Dinic template ready. The hard part is building the graph.'])),
    ('b_str', 5, 0, ('字符串进阶', ['AC 自动机 · SAM', 'Manacher：回文'],
                     ['多模式串匹配用 AC 自动机；子串计数、本质不同子串用后缀自动机；最长回文用 Manacher。']),
     ('Advanced strings', ['Aho-Corasick, SAM', 'Manacher: palindromes'],
      ['Many patterns at once: Aho-Corasick; counting distinct substrings: the suffix automaton; longest palindromes: Manacher.'])),
    ('b_geo', 6, 0, ('计算几何', ['叉积 · 凸包', '半平面交 · 精度'],
                     ['一切从叉积判方向开始：凸包、旋转卡壳、半平面交。精度问题用 eps，能用整数就用整数。']),
     ('Geometry', ['Cross product, hull', 'Half-planes, precision'],
      ['Everything starts from the cross product: convex hull, rotating calipers, half-plane intersection. Use eps, or integers when possible.'])),
    ('b_game', 7, 0, ('博弈', ['Nim · SG 函数', '先打表找规律'],
                      ['公平组合游戏：Nim 看各堆的异或和；几个独立游戏合起来，SG 值是各自 SG 值的异或。先打表找规律。']),
     ('Games', ['Nim, Sprague-Grundy', 'Brute force for a pattern'],
      ['Impartial games: Nim is decided by the XOR of the piles; a sum of independent games has the XOR of their Grundy values. Tabulate small cases first.'])),
    ('b_dc', 0, 1, ('分治', ['CDQ · 整体二分', '离线降一维'],
                    ['三维偏序用 CDQ 分治降掉一维；很多询问各自要二分时，整体二分把它们一起二分。']),
     ('Divide and conquer', ['CDQ, parallel bin. search', 'Offline, drop a dimension'],
      ['CDQ divide and conquer removes one dimension from 3D dominance counting; parallel binary search answers many binary searches together.'])),
    ('b_off', 1, 1, ('离线技巧', ['莫队 · 扫描线', '询问能重排就离线'],
                     ['询问可以重排就离线做：区间询问按块排序用莫队；二维数点、矩形面积并用扫描线加树状数组。']),
     ('Offline tricks', ["Mo's algorithm, sweep", 'Reorder the queries'],
      ["If queries can be reordered, go offline: Mo's algorithm for range queries, a sweep line with a Fenwick tree for 2D counting and rectangle union."])),
    ('b_lichao', 2, 1, ('李超树 · 笛卡尔树', ['斜率优化 DP', '区间最值变成树'],
                        ['斜率优化 DP 的通用解法是李超线段树（动态加直线、求某点最值）；笛卡尔树把区间最值问题变成树上问题。']),
     ('Li Chao · Cartesian', ['Convex hull trick DP', 'Range min as a tree'],
      ['A Li Chao tree (insert lines, query the max at a point) is the general tool for convex-hull-trick DP; a Cartesian tree turns range-min problems into tree problems.'])),
    ('b_rand', 3, 1, ('对拍 · 随机化', ['暴力对拍查错', '随机哈希防卡'],
                      ['写完难题先写暴力程序对拍，比肉眼查错快得多；随机哈希、随机打乱防止被构造的数据卡掉。']),
     ('Stress testing', ['Check against brute force', 'Randomised hashing'],
      ['After a hard problem, stress-test it against a brute force; it beats reading the code. Random hashing and shuffling defeat adversarial tests.'])),
]
for nid, col, row, zh, en in B:
    node(nid, grid_box(Y_B, col, row), 'cold', zh, en)

# ---------------------------------------------------------------- band C: the contest focus (math)
NT1, NT11, NT2, NT2X, NT3, NT4P, NT4S, NT0 = ('NT #1 GCD · CRT', 'number-theory-1-elementary'), \
    ('NT #1.1 floor blocks', 'number-theory-1-1-divisibility-blocking'), \
    ('NT #2 multiplicative', 'number-theory-2-multiplicative-functions'), \
    ('NT #2-ex Möbius', 'number-theory-2-ex-mobius-techniques'), \
    ('NT #3 sieve → Möbius', 'number-theory-3-sieve-mobius-inclusion-exclusion'), \
    ('NT #4 Miller-Rabin · rho', 'number-theory-4-primality-factorisation-residues'), \
    ('NT #4 Min_25 · Du', 'number-theory-4-min25-du-jiao-sieve'), \
    ('NT #0 common formulae', 'number-theory-0-common-formulae')
C11, C0, C12, C21, C22, C31, C32 = ('C #1.1 binomials', 'combinatorics-1-1-permutations-combinations'), \
    ('C #0 formulae', 'combinatorics-0-common-formulae-conclusions'), \
    ('C #1.2 inclusion-exclusion', 'combinatorics-1-2-inclusion-exclusion-diophantine-derangements'), \
    ('C #2.1 FFT', 'combinatorics-2-1-fft-lagrange-interpolation'), \
    ('C #2.2 roots · NTT', 'combinatorics-2-2-primitive-roots-ntt'), \
    ('C #3.1 OGF', 'combinatorics-3-1-ordinary-generating-functions'), \
    ('C #3.2 power series', 'combinatorics-3-2-more-operations-on-formal-power-series')
M1, M2, M3, M4 = ('M #1 fast power · Kitamasa', 'matrix-1-fast-exponentiation'), \
    ('M #2 Gaussian elimination', 'matrix-2-gaussian-elimination'), \
    ('M #3 linear basis', 'matrix-3-linear-basis'), ('M #4 problems', 'matrix-4-problems')

C = [
    # lane 0: number theory
    ('c_pow', 0, 0, 0, 'data', [NT1], ('快速幂 · gcd · exgcd', ['所有模运算的起点'],
                                     ['快速幂 O(log n)；扩展欧几里得解 ax + by = gcd(a, b)，用来求逆元、解线性同余方程。',
                                      '赛场上要能一分钟写出来。']),
     ('Fast power · gcd · exgcd', ['Where modular work starts'],
      ['Fast power is O(log n); extended Euclid solves ax + by = gcd(a, b), which gives inverses and solves linear congruences.',
       'Be able to write them in a minute.'])),
    ('c_inv', 0, 0, 1, 'data', [NT1], ('逆元 · CRT · 欧拉定理', ['模意义除法；合并同余'],
                                     ['模数是质数用费马小定理求逆元，不是就用 exgcd；1 到 n 的逆元能线性求出。',
                                      '中国剩余定理合并几个同余式（模数不互质用扩展 CRT）；扩展欧拉定理把很大的指数降下来。']),
     ('Inverses · CRT · Euler', ['Division mod p; merging'],
      ["Mod a prime, Fermat's little theorem gives the inverse; otherwise exgcd. All inverses of 1..n come out in linear time.",
       "CRT merges congruences (generalised CRT when moduli share factors); the extended Euler theorem reduces huge exponents."])),
    ('c_sieve', 0, 0, 2, 'data', [NT3], ('筛法', ['线性筛顺带筛积性函数'],
                                       ['线性筛 O(n) 求出质数，同时筛出 φ、μ、约数个数这些积性函数。n 到 1e7 都靠它预处理。']),
     ('Sieves', ['Linear sieve, plus φ, μ, d'],
      ['The linear sieve finds primes in O(n) and computes multiplicative functions such as φ, μ and the divisor count on the way; it covers precomputation up to about 1e7.'])),
    ('c_mult', 0, 0, 3, 'data', [NT2], ('积性函数 · 狄利克雷卷积', ['φ、μ、d、σ 之间的关系'],
                                      ['狄利克雷卷积把这些函数连成一张网：μ * 1 = ε，φ * 1 = id，1 * 1 = d。推式子时靠这些恒等式换元。']),
     ('Multiplicative · Dirichlet', ['How φ, μ, d, σ relate'],
      ['Dirichlet convolution ties these functions together: μ * 1 = ε, φ * 1 = id, 1 * 1 = d. Derivations substitute with these identities.'])),
    ('c_mob', 0, 0, 4, 'data', [NT2X, NT11], ('莫比乌斯反演 · 数论分块', ['∑ gcd 类式子的标准路线'],
                                            ['看到 ∑∑[gcd(i, j) = 1] 或 ∑ gcd(i, j)，用 [n = 1] = ∑_{d | n} μ(d) 换掉条件，再交换求和顺序。',
                                             '剩下的 ⌊n / d⌋ 只有 O(√n) 种取值，按块算。它本质上是在约数上做容斥（组合计数那一列）。']),
     ('Möbius · floor blocks', ['The route for sums over gcd'],
      ['For ∑∑[gcd(i, j) = 1] or ∑ gcd(i, j), replace the condition with [n = 1] = ∑_{d | n} μ(d) and swap the order of summation.',
       'What remains, ⌊n / d⌋, takes only O(√n) values, so sum block by block. It is inclusion-exclusion over divisors (see the counting lane).'])),
    ('c_dujiao', 0, 0, 5, 'data', [NT4S], ('杜教筛 · min_25', ['n 到 1e10 的前缀和'],
                                         ['线性筛只够到 1e7。n 再大，杜教筛用狄利克雷卷积把积性函数前缀和递归下去，O(n^{2/3})；min_25 处理在质数处好算的积性函数。']),
     ("Du's sieve · Min_25", ['Prefix sums up to 1e10'],
      ["A linear sieve stops around 1e7. Beyond that, Du's sieve recurses on prefix sums through a Dirichlet convolution in O(n^{2/3}); Min_25 handles multiplicative functions that are easy at primes."])),
    ('c_root', 0, 1, 1, 'sync', [C22], ('原根 · BSGS', ['离散对数；NTT 的模数'],
                                      ['原根把乘法变成指数上的加法；BSGS 在 O(√p) 内解 a^x ≡ b (mod p)。',
                                       '998244353 的原根 3 就是 NTT 用的那个。']),
     ('Primitive roots · BSGS', ['Discrete log; NTT moduli'],
      ['A primitive root turns multiplication into addition of exponents; baby-step giant-step solves a^x ≡ b (mod p) in O(√p).',
       'The primitive root 3 of 998244353 is the one NTT uses.'])),
    ('c_mr', 0, 1, 2, 'sync', [NT4P], ('Miller-Rabin · rho', ['1e18 级的判素和分解'],
                                     ['1e18 级别的数判素用 Miller-Rabin（固定 7 个底就是确定性的），分解用 Pollard rho。乘法要用 __int128 防溢出。']),
     ('Miller-Rabin · rho', ['Primality, factoring to 1e18'],
      ['Miller-Rabin tests numbers up to 1e18 (a fixed set of 7 bases makes it deterministic) and Pollard rho factors them; use __int128 for the products.'])),
    ('c_qr', 0, 1, 3, 'sync', [NT4P], ('二次剩余 · Lucas', ['模 p 开方；大组合数取模'],
                                     ['Cipolla 解 x² ≡ a (mod p)；Lucas 定理算 n 很大、p 不大的组合数取模，扩展 Lucas 处理合数模。']),
     ('Square roots · Lucas', ['√ mod p; big binomials'],
      ["Cipolla solves x² ≡ a (mod p); Lucas's theorem computes binomials mod a small prime when n is huge, and the generalised version handles composite moduli."])),
    ('c_ntfact', 0, 1, 4, 'sync', [NT0], ('常用结论', ['勒让德公式；约数个数上界'],
                                        ['n! 里质因子 p 的次数用勒让德公式；1e9 以内的数约数最多 1344 个，1e18 以内约 1e5 个，决定能不能枚举约数。']),
     ('Handy facts', ["Legendre's formula; divisors"],
      ["Legendre's formula gives the power of p in n!; numbers below 1e9 have at most 1344 divisors and below 1e18 about 1e5, which decides whether enumerating divisors is feasible."])),
    # lane 1: counting
    ('c_cnt', 1, 0, 0, 'data', [C11, C0], ('排列组合 · 组合数取模', ['预处理阶乘和逆阶乘'],
                                         ['预处理 n! 和它的逆元，组合数 O(1)。先修：逆元（数论那一列）。',
                                          '插板法、多重集排列、错位排列这些模型要能一眼认出来。']),
     ('Binomials mod p', ['Precompute factorials'],
      ['Precompute n! and its inverse for O(1) binomials. Needs: inverses (number theory lane).',
       'Recognise stars and bars, multiset permutations and derangements at a glance.'])),
    ('c_ie', 1, 0, 1, 'data', [C12], ('容斥 · 错排 · 不定方程', ['“至少”和“恰好”互相换'],
                                    ['限制很多的计数：先算不管限制的，再按违反了哪些限制加加减减。',
                                     '有上界的不定方程解数、错排都是容斥的模板题。']),
     ('Inclusion-exclusion', ['Trade "at least" for "exactly"'],
      ['For counts with many restrictions, count without them and add or subtract by the set of restrictions violated.',
       'Bounded solutions of linear equations and derangements are the template problems.'])),
    ('c_binv', 1, 0, 2, 'data', [], ('二项式反演 · min-max 反演', ['恰好 k 个 ↔ 至少 k 个'],
                                    ['容斥的代数形式：已知 g(k) = ∑ C(i, k) f(i)，就能反过来解出 f。',
                                     'min-max 反演用来求“所有东西都出现一次的期望时间”。']),
     ('Binomial inversion', ['Exactly k ↔ at least k'],
      ['The algebraic form of inclusion-exclusion: from g(k) = ∑ C(i, k) f(i) you can solve back for f.',
       'Min-max inversion gives the expected time until everything has appeared.'])),
    ('c_gf', 1, 0, 3, 'data', [C31], ('生成函数', ['OGF 管组合；EGF 管排列'],
                                     ['把计数序列装进幂级数：几类物品各选若干个，就是几个生成函数相乘。',
                                      '无标号用普通生成函数，有标号（排列）用指数生成函数。']),
     ('Generating functions', ['OGF: choose; EGF: arrange'],
      ['Put a counting sequence into a power series: choosing from several kinds of items multiplies their generating functions.',
       'Unlabelled objects use ordinary generating functions; labelled ones (arrangements) use exponential ones.'])),
    ('c_ntt', 1, 0, 4, 'data', [C21, C22], ('FFT · NTT', ['O(n log n) 的卷积'],
                                          ['两个多项式相乘从 O(n²) 降到 O(n log n)。模 998244353 用 NTT，不丢精度；任意模数用三模 NTT 或拆系数 FFT。',
                                           '先修：原根（数论那一列）。']),
     ('FFT · NTT', ['Convolution in O(n log n)'],
      ['Polynomial multiplication drops from O(n²) to O(n log n). Mod 998244353 use NTT, which is exact; for arbitrary moduli use three-modulus NTT or split FFT.',
       'Needs: primitive roots (number theory lane).'])),
    ('c_poly', 1, 0, 5, 'data', [C32], ('多项式全家桶', ['求逆 · ln · exp · 分治 NTT'],
                                       ['有了 NTT，生成函数的除法、对数、指数都是 O(n log n)。比赛直接用板子；要会的是把题目化成“求某个生成函数的第 n 项”。']),
     ('Polynomial toolkit', ['Inverse, ln, exp, D&C NTT'],
      ['With NTT, division, logarithm and exponential of power series are all O(n log n). Use templates in contests; the skill is reducing the problem to "the n-th coefficient of some generating function".'])),
    ('c_model', 1, 1, 0, 'sync', [], ('球盒 · 斯特林 · 卡特兰', ['经典分配模型'],
                                     ['球和盒子有没有区别、盒子能不能空，十二种情况各对应一个公式（组合数、斯特林数、分拆数）。',
                                      '卡特兰数对应括号序列、出栈序列、二叉树个数。']),
     ('Balls into boxes', ['Stirling, Catalan, partitions'],
      ['Whether balls and boxes are distinguishable and whether boxes may be empty gives twelve cases, each with its formula (binomials, Stirling numbers, partitions).',
       'Catalan numbers count bracket sequences, stack orders and binary trees.'])),
    ('c_polya', 1, 1, 1, 'sync', [], ('Polya · Burnside', ['旋转、翻转下的不同方案'],
                                     ['旋转或翻转后相同的染色算一种时，用 Burnside：对每个置换数不动点，再取平均。项链计数是模板。']),
     ('Pólya · Burnside', ['Counting up to symmetry'],
      ['When colourings equal under rotation or reflection count once, Burnside averages the fixed points over the group. Necklace counting is the template.'])),
    ('c_prob', 1, 1, 2, 'sync', [], ('概率 · 期望 DP', ['期望的线性性；倒推'],
                                    ['期望能拆成各部分期望之和（线性性）；期望 DP 一般从终点往回推。分数结果用逆元取模输出。']),
     ('Probability · expectation', ['Linearity; work backwards'],
      ['Split an expectation into a sum by linearity; expectation DP usually runs backwards from the end. Fractions are printed modulo p with inverses.'])),
    ('c_fwt', 1, 1, 3, 'sync', [], ('FWT · 子集卷积 · SOS', ['按位与 / 或 / 异或的卷积'],
                                   ['下标做位运算的卷积用 FWT；对所有子集求和（高维前缀和）用 SOS DP，O(n·2^n)。']),
     ('FWT · SOS', ['AND / OR / XOR convolutions'],
      ['Convolutions where indices combine by a bitwise operation use FWT; sums over all subsets (high-dimensional prefix sums) use SOS DP in O(n·2^n).'])),
    # lane 2: linear algebra
    ('c_mpow', 2, 0, 0, 'data', [M1], ('矩阵乘法 · 快速幂', ['O(k³ log n) 算线性递推'],
                                     ['n 到 1e18、每一项只依赖前 k 项的递推（斐波那契、只看前几项的计数 DP），写成 k × k 矩阵做快速幂。']),
     ('Matrix fast power', ['Recurrences in O(k³ log n)'],
      ['A recurrence where each term depends on the previous k (Fibonacci, counting DPs with a short memory) becomes a k × k matrix raised to the n-th power, for n up to 1e18.'])),
    ('c_semi', 2, 0, 1, 'data', [M1], ('DP 半环', ['(min, +) 矩阵：恰好走 k 步'],
                                     ['把乘法换成加法、加法换成取 min，矩阵快速幂就能算“恰好走 k 步的最短路”；布尔矩阵算可达性。']),
     ('DP semirings', ['(min, +): exactly k steps'],
      ['Swap multiplication for addition and addition for min, and matrix power computes shortest walks of exactly k steps; boolean matrices give reachability.'])),
    ('c_gauss', 2, 0, 2, 'data', [M2], ('高斯消元', ['实数 · 模 p · 异或方程组'],
                                      ['O(n³) 解线性方程组；模 p 时除法换成乘逆元；异或方程组用 bitset 加速。',
                                       '要会判无解、数自由元：方案数 = p 的自由元个数次方。']),
     ('Gaussian elimination', ['Reals, mod p, and XOR'],
      ['Solves linear systems in O(n³); mod p, division becomes multiplication by an inverse; XOR systems speed up with bitset.',
       'Detect inconsistency and count free variables: the number of solutions is p to that power.'])),
    ('c_det', 2, 0, 3, 'data', [], ('行列式', ['消成上三角；任意模数辗转相除'],
                                   ['行列式 = 消成上三角以后对角线的乘积。模数不是质数时，两行之间做辗转相除来消元。']),
     ('Determinants', ['Triangularise; Euclid for any mod'],
      ['The determinant is the product of the diagonal after elimination to triangular form; for a composite modulus, eliminate with a Euclid-style exchange between rows.'])),
    ('c_mtt', 2, 0, 4, 'data', [], ('矩阵树定理 · LGV', ['生成树计数；不相交路径'],
                                   ['生成树个数 = 拉普拉斯矩阵去掉一行一列后的行列式；LGV 引理把不相交路径组的计数变成一个行列式。']),
     ('Matrix-tree · LGV', ['Spanning trees; disjoint paths'],
      ['The number of spanning trees is a cofactor of the Laplacian; the LGV lemma turns counting non-intersecting path systems into a determinant.'])),
    ('c_bm', 2, 1, 0, 'sync', [M1], ('BM · 特征多项式', ['从前几项求递推；Kitamasa'],
                                    ['不知道递推式时用 Berlekamp-Massey 从前 2k 项求出来；k 大时用特征多项式（Kitamasa）把 O(k³ log n) 降到 O(k² log n)，再配 NTT 更快。']),
     ('BM · Kitamasa', ['Recover the recurrence'],
      ['When the recurrence is unknown, Berlekamp-Massey recovers it from the first 2k terms; for large k, the characteristic polynomial (Kitamasa) cuts O(k³ log n) to O(k² log n), and NTT goes further.'])),
    ('c_mprob', 2, 1, 1, 'sync', [M4], ('矩阵题型', ['线段树的节点存矩阵'],
                                      ['区间加、区间求斐波那契和：线段树每个节点存一个矩阵，懒标记也是矩阵。']),
     ('Matrix problems', ['Matrices in segment trees'],
      ['Range add with range Fibonacci sums: each segment-tree node stores a matrix, and so does the lazy tag.'])),
    ('c_basis', 2, 1, 2, 'sync', [M3], ('线性基', ['最大异或；第 k 小异或'],
                                      ['一组数所有子集的异或和构成一个线性空间，线性基是它的一组基（至多 64 个数）：求最大异或、能否异或出 x、第 k 小。']),
     ('Linear basis', ['Max XOR, k-th XOR'],
      ['The XORs of all subsets form a vector space; a linear basis (at most 64 numbers) answers the maximum XOR, whether x is reachable, and the k-th smallest.'])),
]
for nid, lane, col, row, cls, tags, zh, en in C:
    node(nid, lane_box(lane, col, row), cls, zh, en, tags)

# ---------------------------------------------------------------- lines: learn first → learn next
CHAINS = [['c_pow', 'c_inv', 'c_sieve', 'c_mult', 'c_mob', 'c_dujiao'],
          ['c_cnt', 'c_ie', 'c_binv', 'c_gf', 'c_ntt', 'c_poly'],
          ['c_mpow', 'c_semi', 'c_gauss', 'c_det', 'c_mtt']]
SIDE = [('c_inv', 'c_root'), ('c_cnt', 'c_model'), ('c_mpow', 'c_bm'), ('c_gauss', 'c_basis')]


def edges():
    out = []
    for chain in CHAINS:
        for a, b in zip(chain, chain[1:]):
            ax, ay, aw, ah = NODES[a]['box']
            bx, by, bw, bh = NODES[b]['box']
            cx = ax + 40
            out.append(('e_%s_%s' % (a, b), 'M%d,%d L%d,%d' % (cx, ay + ah, cx, by - 2), 'line'))
    for a, b in SIDE:
        ax, ay, aw, ah = NODES[a]['box']
        bx, by, bw, bh = NODES[b]['box']
        y = ay + 30
        out.append(('e_%s_%s' % (a, b), 'M%d,%d L%d,%d' % (ax + aw, y, bx - 2, y), 'line'))
    return out


EDGES = edges()

TEXT = {
    'zh': dict(
        title='算法地图：面试要写的、快速过的、赛场主攻的',
        legend=['绿框 = 面试常考，要能写对写快；灰框 = 快速过，知道它解决什么、什么时候想到它；蓝框 = 主攻的主线，按箭头从上往下学；黄框 = 主攻的支线，主线学到箭头那一格时挂上去。',
                '蓝字 = 站内已有的笔记（英文）：NT = Number Theory，C = Combinatorics，M = Matrix。框之间跨列的先修关系写在点开后的说明里。'],
        r_a='面试常考：要能写对、写快（HFT / 互联网面试和比赛签到题）',
        r_b='快速过：知道它解决什么、复杂度多少、什么时候想到它',
        r_c='赛场主攻：数学。要能推式子，赛场上说得出思路',
        lanes=['数论', '组合计数', '线性代数（矩阵）'],
        footer=['图跟着学习进度更新：讲过的框补上对应的文章。']),
    'en': dict(
        title='Algorithm map: what to write in interviews, what to skim, what to master for contests',
        legend=['Green = interview core, write it right and fast; grey = skim, know what it solves and when to reach for it; blue = main line of the contest focus, top to bottom; yellow = side branch, picked up when the main line reaches its arrow.',
                'Blue labels = notes already on this site: NT = Number Theory, C = Combinatorics, M = Matrix. Prerequisites across lanes are in the box details.'],
        r_a='Interview core: write it right and fast (HFT / tech interviews, easy contest problems)',
        r_b='Skim: what it solves, what it costs, when to reach for it',
        r_c='Contest focus: mathematics. Derive the formula and state the idea under contest pressure',
        lanes=['Number theory', 'Counting', 'Linear algebra (matrices)'],
        footer=['The map grows with the study: boxes gain links to posts as they are covered.']),
}

UI = {
    'zh': dict(page_title='算法地图', lead='点一个框看它解决什么、什么时候想到它；选一条路线，一步一步看先学什么。蓝字可以直接点开对应的笔记。',
               other_lang=['English', 'algo-map.en.html'], static=['静态图', '/images/algo/algo-map.zh.svg'],
               ref=['算法', '/zh/algo/'], prev='上一步', next='下一步', exit='退出',
               step='第 {i} / {n} 步', panel_empty='点图里的任意一个框。', zoom=['看原尺寸', '适应宽度'], panel_links='站内笔记'),
    'en': dict(page_title='Algorithm Map', lead='Click a box to see what it solves and when to reach for it. Pick a route to step through what to learn first. Blue labels open the notes.',
               other_lang=['中文', 'algo-map.zh.html'], static=['Static image', '/images/algo/algo-map.en.svg'],
               ref=['Algorithms', '/algo/'], prev='Back', next='Next', exit='Exit',
               step='Step {i} of {n}', panel_empty='Click any box in the map.', zoom=['Actual size', 'Fit width'], panel_links='Notes on this site'),
}


def chain_steps(chain, zh, en):
    steps = [([chain[0]], zh[0], en[0])]
    for i, (a, b) in enumerate(zip(chain, chain[1:])):
        steps.append((['e_%s_%s' % (a, b), b], zh[i + 1], en[i + 1]))
    return steps


TOURS = [
    ('interview', '面试刷题路线', 'Interview route', [
        (['a_cx'], '先练“看数据范围定复杂度”，再把 STL 容器的复杂度背熟。后面每道题都从这一步开始。',
         'Start with "read the limits, pick the complexity", and learn the costs of the STL containers. Every problem starts here.'),
        (['a_bs', 'a_tp', 'a_ps'], '数组上的三件套：二分、双指针、前缀和。面试题一大半是它们的组合。',
         'The array trio: binary search, two pointers, prefix sums. Most interview problems combine them.'),
        (['a_st', 'a_hp', 'a_gr', 'a_bit'], '栈、堆、哈希表、排序贪心、位运算：选对容器，复杂度就对了。',
         'Stacks, heaps, hash maps, sorting and greedy, bit tricks: pick the right container and the complexity follows.'),
        (['a_srch', 'a_tree', 'a_graph', 'a_dsu'], '搜索、树、图、并查集：递归和 BFS 写熟，树题想清楚递归返回什么。',
         'Search, trees, graphs, union-find: make recursion and BFS automatic, and decide what a recursive call returns.'),
        (['a_dp1', 'a_dp2'], 'DP：每道题先写下“状态是什么意思”，转移自然就出来了。',
         'DP: write down what a state means before anything else; the transition follows.'),
        (['a_str', 'a_design'], '字符串和设计题收尾。HFT 面试常落在设计题：LRU、订单簿、限流。',
         'Finish with strings and design. HFT interviews often end on design: LRU, order book, rate limiter.'),
    ]),
    ('nt', '数论主线', 'Number theory line', chain_steps(CHAINS[0], [
        '从快速幂、gcd、exgcd 开始：后面每一格都要用。',
        '逆元和 CRT：模意义下怎么做除法、怎么合并同余。旁边的原根接在这里。',
        '线性筛：O(n) 筛质数，顺带筛积性函数。',
        '积性函数和狄利克雷卷积：推式子用的那几个恒等式。',
        '莫比乌斯反演加数论分块：赛场上 ∑ gcd 类题目的标准路线，这一格要能当场推。',
        'n 到 1e10：杜教筛和 min_25。'], [
        'Start with fast power, gcd and exgcd: every later box uses them.',
        'Inverses and CRT: division and merging congruences mod m. Primitive roots hang off here.',
        'The linear sieve: primes in O(n), multiplicative functions on the way.',
        'Multiplicative functions and Dirichlet convolution: the identities used in derivations.',
        'Möbius inversion with floor blocks: the standard contest route for sums over gcd; derive it on the spot.',
        "n up to 1e10: Du's sieve and Min_25."])),
    ('comb', '组合计数主线', 'Counting line', chain_steps(CHAINS[1], [
        '组合数取模：预处理阶乘和逆阶乘。经典模型（球盒、卡特兰）接在这里。',
        '容斥：限制多的计数，按违反了哪些限制加减。',
        '二项式反演：“恰好 k 个”和“至少 k 个”互相换。',
        '生成函数：把“各选若干个凑总数”变成多项式相乘。',
        'NTT：让多项式乘法变成 O(n log n)。',
        '多项式全家桶：求逆、ln、exp。要练的是把题化成“求第 n 项系数”。'], [
        'Binomials mod p: precompute factorials and inverse factorials. Classic models (balls into boxes, Catalan) hang off here.',
        'Inclusion-exclusion: add and subtract by the set of violated restrictions.',
        'Binomial inversion: trade "exactly k" for "at least k".',
        'Generating functions: "pick some of each to reach a total" becomes a product of polynomials.',
        'NTT makes that product O(n log n).',
        'The polynomial toolkit: inverse, ln, exp. The skill is reducing to "the n-th coefficient".'])),
    ('la', '线性代数主线', 'Linear algebra line', chain_steps(CHAINS[2], [
        '矩阵快速幂：n 到 1e18 的线性递推。递推式不知道时用旁边的 BM。',
        'DP 半环：把 (+, ×) 换成 (min, +)，算恰好走 k 步的最短路。',
        '高斯消元：实数、模 p、异或三种。异或方程组接到旁边的线性基。',
        '行列式：消成上三角。',
        '矩阵树定理和 LGV：计数题里的行列式。'], [
        'Matrix fast power: linear recurrences for n up to 1e18. If the recurrence is unknown, BM recovers it.',
        'DP semirings: swap (+, ×) for (min, +) to get shortest walks of exactly k steps.',
        'Gaussian elimination over reals, mod p and XOR; XOR systems lead to the linear basis.',
        'Determinants: eliminate to triangular form.',
        'Matrix-tree theorem and LGV: determinants in counting problems.'])),
    ('signals', '赛场上怎么想到', 'Contest signals', [
        (['c_mob', 'c_dujiao'], '式子里有 ∑ gcd 或 [gcd = 1]：莫比乌斯反演换掉条件，数论分块求和；n 到 1e10 再上杜教筛。',
         'A sum over gcd or a [gcd = 1] condition: Möbius inversion removes it, floor blocks sum it; for n up to 1e10 add Du\'s sieve.'),
        (['c_ie', 'c_binv'], '计数带“每一个都不能……”的限制：容斥；问“恰好 k 个”：先算“至少 k 个”，再二项式反演。',
         'Counting with "none of them may...": inclusion-exclusion; "exactly k": count "at least k", then invert.'),
        (['c_gf', 'c_ntt', 'c_poly'], '“若干种物品各选几个、凑出总和 n”，n 到 1e5：生成函数相乘，用 NTT。',
         '"Choose some of each kind to total n", with n up to 1e5: multiply generating functions with NTT.'),
        (['c_mpow', 'c_bm'], 'n 到 1e18、每项只依赖前几项：矩阵快速幂；递推式不知道就用 BM 求。',
         'n up to 1e18 and each term depends on a few before it: matrix fast power; unknown recurrence: BM.'),
        (['c_gauss', 'c_basis'], '一组开关、异或、模 2 的方程：高斯消元或线性基。',
         'Switches, XOR, equations mod 2: Gaussian elimination or a linear basis.'),
    ]),
]

SVG_STYLE = arch.SVG_STYLE + '''
      .lane-t { font-size: 15px; font-weight: 700; fill: #0550ae; }'''


def svg(lang, interactive):
    T = TEXT[lang]
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="%s">' % (W, H, W, H, FONT),
         '  <defs>',
         '    <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
         '      <path d="M0,0 L10,5 L0,10 z" fill="#555"/>',
         '    </marker>',
         '    <style>' + SVG_STYLE + '\n    </style>',
         '  </defs>',
         '  <rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H),
         '  <text x="20" y="38" class="h" style="font-size:23px">%s</text>' % esc(T['title'])]
    for i, line in enumerate(T['legend']):
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (64 + 20 * i, esc(line)))
        arch.check('legend', line, 12, W - 40)

    band_h = 40 + 2 * GRID_H + GRID_ROW_GAP + 14
    o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="#f4fbf5" stroke="#4ac26b" stroke-dasharray="6 4"/>' % (X0, Y_A, BAND_W, band_h))
    o.append('  <text x="%d" y="%d" class="lane-h" style="fill:#1a7f37">%s</text>' % (X0 + 12, Y_A + 26, esc(T['r_a'])))
    o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="#ffffff" stroke="#8c959f" stroke-dasharray="6 4"/>' % (X0, Y_B, BAND_W, band_h))
    o.append('  <text x="%d" y="%d" class="lane-h" style="fill:#57606a">%s</text>' % (X0 + 12, Y_B + 26, esc(T['r_b'])))
    o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="10" class="sock"/>' % (X0, Y_C, BAND_W, H_C))
    o.append('  <text x="%d" y="%d" class="h">%s</text>' % (X0 + 12, Y_C + 28, esc(T['r_c'])))
    for i, name in enumerate(T['lanes']):
        lx = X0 + i * (LANE_W + LANE_GAP)
        if i:
            o.append('  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#d0d7de" stroke-width="1"/>' % (lx - LANE_GAP // 2, Y_C + 44, lx - LANE_GAP // 2, Y_C + H_C - 12))
        o.append('  <text x="%d" y="%d" class="lane-t">%s</text>' % (lx + COL_PAD, Y_C + 58, esc(name)))

    for nid, n in NODES.items():
        x, y, w, h = n['box']
        d = n[lang]
        if interactive:
            o.append('  <g id="%s" class="node" tabindex="0" role="button" aria-label="%s">' % (nid, esc(d['title'])))
        else:
            o.append('  <g id="%s">' % nid)
        o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="6" class="%s"/>' % (x, y, w, h, n['cls']))
        yy = y + 24
        o.append('  <text x="%d" y="%d" class="t">%s</text>' % (x + 12, yy, esc(d['title'])))
        arch.check('%s/%s title' % (lang, nid), d['title'], 15, w - 24, True)
        for line in d['lines']:
            yy += 18
            o.append('  <text x="%d" y="%d" class="s">%s</text>' % (x + 12, yy, esc(line)))
            arch.check('%s/%s' % (lang, nid), line, 12, w - 24)
        for segs in d['tags']:
            yy += 18
            o.append('  ' + tag_text(x + 12, yy, segs))
            arch.check('%s/%s tag' % (lang, nid), ''.join(t for t, _ in segs), 12, w - 24)
        if yy + 10 > y + h:
            WARNINGS.append('%s/%s: text runs to y=%d, box ends at y=%d' % (lang, nid, yy + 10, y + h))
        o.append('  </g>')

    for eid, path, kind in EDGES:
        o.append('  <path d="%s" class="%s edge" id="%s" marker-end="url(#arr)"/>' % (path, kind, eid))
    for i, line in enumerate(T['footer']):
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (H - 26 + 20 * i, esc(line)))
    o.append('</svg>')
    return '\n'.join(o)


def page(lang):
    u = UI[lang]
    data = {'nodes': {}, 'ui': dict(u)}
    for nid, n in NODES.items():
        d = n[lang]
        data['nodes'][nid] = {'title': d['title'], 'lines': d['panel'], 'tags': [[list(seg) for seg in segs] for segs in d['tags']]}
    data['ui']['tours'] = {}
    ids = set(NODES) | {e[0] for e in EDGES}
    for key, zh, en, steps in TOURS:
        out = []
        for idlist, czh, cen in steps:
            for i in idlist:
                if i not in ids:
                    WARNINGS.append('tour %s refers to unknown id %s' % (key, i))
            out.append([idlist, czh if lang == 'zh' else cen])
        data['ui']['tours'][key] = [zh if lang == 'zh' else en, out]
    buttons = ''.join('<button type="button" data-k="%s" aria-pressed="false">%s</button>' % (k, esc(zh if lang == 'zh' else en))
                      for k, zh, en, _ in TOURS)
    js_data = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    css = arch.PAGE_CSS.replace('.map.full svg { width: 1600px;', '.map.full svg { width: %dpx;' % W)
    return '\n'.join([
        '<!doctype html>',
        '<html lang="%s">' % ('zh-CN' if lang == 'zh' else 'en'),
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>%s</title>' % esc(u['page_title']),
        '<link rel="icon" href="/images/logo.svg?v=20261008-rounded-brain-1">',
        '<style>' + css + '</style>',
        '</head>',
        '<body>',
        '<header>',
        '<h1>%s</h1>' % esc(u['page_title']),
        '<p class="lead">%s</p>' % esc(u['lead']),
        '<nav><a href="%s">%s</a><a href="%s">%s</a><a href="%s">%s</a></nav>' % (
            u['other_lang'][1], esc(u['other_lang'][0]), u['ref'][1], esc(u['ref'][0]), u['static'][1], esc(u['static'][0])),
        '</header>',
        '<div class="tours">%s<button type="button" class="zoom" aria-pressed="false">%s</button></div>' % (buttons, esc(u['zoom'][0])),
        '<div class="layout">',
        '<div class="map">',
        svg(lang, True),
        '</div>',
        '<aside class="side">',
        '<div class="card stepbar" id="stepbar"><div class="count"></div><div class="cap"></div><div class="btns">'
        '<button type="button" class="prev">%s</button><button type="button" class="next">%s</button><button type="button" class="exit">%s</button></div></div>' % (
            esc(u['prev']), esc(u['next']), esc(u['exit'])),
        '<div class="card" id="panel"><p>%s</p></div>' % esc(u['panel_empty']),
        '</aside>',
        '</div>',
        '<script>',
        'const DATA = %s;' % js_data,
        arch.PAGE_JS.strip('\n'),
        '</script>',
        '</body>',
        '</html>',
    ])


def main():
    del WARNINGS[:]  # drop anything the arch-map module produced on import
    for lang in LANGS:
        arch.write('static/images/algo/algo-map.%s.svg' % lang, svg(lang, False))
        arch.write('static/maps/algo-map.%s.html' % lang, page(lang))
    for w in sorted(set(WARNINGS)):
        print('WARN', w)


if __name__ == '__main__':
    main()
