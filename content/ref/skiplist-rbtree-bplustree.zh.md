---
title: "跳表、红黑树、B+ 树：三种有序结构各用在哪"
date: 2026-11-02
slug: "skiplist-rbtree-bplustree"
description: "哈希表查得快，但不记顺序；要按 key 排序遍历、做范围查询，就得用有序结构。红黑树用五条颜色规则把树高压在 2 log n 以内，插入删除只要常数次旋转，std::map、Linux 调度器、epoll 都用它；跳表在有序链表上随机长出索引层，期望 O(log n)，实现简单、范围查询自然，Redis 的有序集合和 LevelDB 的内存表用它；B+ 树把一个节点做成一个磁盘页，几百上千个分叉让树只有 3 到 4 层，数据全在串起来的叶子里，MySQL InnoDB 的索引就是它。附一个对着 std::set 测过的跳表实现。"
summary: "三者都是 O(log n) 的有序结构，差别在每一步的代价落在哪：红黑树和跳表在内存里，一步是一次指针跳转，比的是实现难度和改动范围；B+ 树在磁盘上，一步是一次读页，所以要把树做得又宽又矮。"
toc: true
math: true
group: cpplinux
weight: 124
---

哈希表按 key 查是平均 O(1)，代价是 key 在里面的位置和大小顺序无关。要按 key 从小到大遍历，要找“第一个不小于 x 的”，要查 `[lo, hi]` 之间的全部，哈希表只能全扫一遍。有序结构把 key 按顺序组织起来，查找、插入、删除都是 O(log n)，范围查询是“找到起点再往后走”，O(log n + k)。最基本的有序结构是二叉搜索树，下面三种都是它的问题的不同解法。

## 1. 红黑树

### 1.1 二叉搜索树会退化：按顺序插入就成了链表 {#bst-degenerate}

二叉搜索树里，每个节点左边的 key 都比它小、右边的都比它大，查找从根往下每一步排除一半，步数等于树高。树高要是 $\log_2 n$，查找就是 O(log n)；可树长成什么样取决于插入顺序，按 1、2、3、…… 的顺序插，每个新节点都挂在上一个的右边，树退化成一条链，查找变成 O(n)。

所以要“平衡”：插入、删除以后调整一下，让树高一直保持在 O(log n)。AVL 树要求每个节点左右子树高度差不超过 1，最矮，查找最快，但条件太严，插入删除时调整得多。**红黑树放宽了条件，只保证最长路径不超过最短路径的 2 倍**，换来每次修改只需要很少的调整。

### 1.2 五条规则：颜色是用来数路径长度的 {#rb-rules}

红黑树满足五条规则：

1. 每个节点要么红、要么黑；
2. 根是黑的；
3. 叶子（空指针 NIL，看作一个黑节点）是黑的；
4. 红节点的两个孩子都是黑的，也就是不能有两个红节点连着；
5. 从任意一个节点出发，到它下面每个 NIL 的路径上，黑节点的个数都相同，这个数叫这个节点的黑高。

真正起作用的是第 4、5 条：第 5 条说所有路径上黑节点一样多，第 4 条说红节点只能夹在黑节点之间，所以最长的路径是红黑交替，最短的路径全是黑节点，前者最多是后者的 2 倍。

### 1.3 树高不超过 2 log(n+1) {#rb-height}

把上面的直觉写成证明。先用归纳法证：黑高为 $bh$ 的子树里，至少有 $2^{bh} - 1$ 个真正的节点（不算 NIL）。黑高为 0 的子树就是 NIL，0 个节点，成立；一个节点的两个孩子，黑高至少是它的黑高减 1，所以它的子树至少有 $2 \times (2^{bh-1} - 1) + 1 = 2^{bh} - 1$ 个节点。

再用第 4 条：从根到 NIL 的任意一条路径上，至少一半的节点是黑的，所以根的黑高至少是树高 $h$ 的一半。两条合起来：

$$
n \;\ge\; 2^{\,h/2} - 1
\quad\Longrightarrow\quad
h \;\le\; 2\log_2(n+1)
$$

**100 万个节点的红黑树，树高最多 40 层**，查找最多 40 次比较。完全平衡的话是 20 层，红黑树用最多 2 倍的高度，换来修改时的调整很便宜。

### 1.4 插入：先涂红，再靠变色和旋转修 {#rb-insert}

新节点总是涂成红色挂到叶子位置，这样任何路径上的黑节点个数都没变，第 5 条自动成立，唯一可能被破坏的是第 4 条：它的父节点也是红的。修复看叔叔节点（父节点的兄弟）的颜色：

- 叔叔是红的：把父亲和叔叔涂黑、祖父涂红。祖父那一层往下每条路径上的黑节点数没变，但祖父变红后可能和它的父亲连成两个红，于是把祖父当成新插入的节点，往上继续检查，最坏一直走到根，O(log n) 次变色。
- 叔叔是黑的：变色解决不了，要旋转。新节点、父亲、祖父排成一条直线时旋转一次，拐了个弯时先转一次把它掰直、再转一次，然后变色，修复到此结束。

旋转是在保持 key 顺序不变的前提下，把一边的节点挪到另一边：

<svg viewBox="0 0 760 286" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="左旋 x：x 的右孩子 y 升上来做子树的根，x 降为 y 的左孩子，y 原来的左子树 b 改挂到 x 的右边；右旋 y 是它的逆操作；中序遍历都是 a x b y c" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sk0bg  { fill: #fbfaf7; }
    .sk0nd  { fill: #eef1f4; stroke: #6b6558; stroke-width: 1.4; }
    .sk0sub { fill: #f3efe6; stroke: #b9b2a3; stroke-width: 1.2; }
    .sk0hot { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.4; }
    .sk0ink { fill: #1c1b18; font-size: 14px; }
    .sk0mut { fill: #6b6558; font-size: 12px; }
    .sk0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sk0hl  { stroke: #c98a76; stroke-width: 2.2; fill: none; }
    .sk0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0nd { fill: #23262c; stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0sub { fill: #26241f; stroke: #5d574b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0hot { fill: #4a2f2c; stroke: #c98a76; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk0hd { fill: #a19caf; }
  </style>
  <defs><marker id="sk0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sk0hd"/></marker></defs>
  <rect class="sk0bg" x="0" y="0" width="760" height="286" rx="10"/>
  <path class="sk0ln" d="M158,76 L126,110"/>
  <path class="sk0ln" d="M184,74 L226,111"/>
  <path class="sk0hl" d="M228,141 L204,180"/>
  <path class="sk0ln" d="M252,141 L276,180"/>
  <circle class="sk0nd" cx="170" cy="60" r="20"/>
  <text class="sk0ink" x="170" y="65" text-anchor="middle">x</text>
  <circle class="sk0nd" cx="240" cy="125" r="20"/>
  <text class="sk0ink" x="240" y="130" text-anchor="middle">y</text>
  <rect class="sk0sub" x="98" y="110" width="44" height="30" rx="6"/>
  <text class="sk0ink" x="120" y="130" text-anchor="middle">a</text>
  <rect class="sk0hot" x="178" y="180" width="44" height="30" rx="6"/>
  <text class="sk0ink" x="200" y="200" text-anchor="middle">b</text>
  <rect class="sk0sub" x="258" y="180" width="44" height="30" rx="6"/>
  <text class="sk0ink" x="280" y="200" text-anchor="middle">c</text>
  <path class="sk0ln" d="M330,92 L428,92" marker-end="url(#sk0a)"/>
  <text class="sk0mut" x="379" y="82" text-anchor="middle">左旋 x</text>
  <path class="sk0ln" d="M428,122 L330,122" marker-end="url(#sk0a)"/>
  <text class="sk0mut" x="379" y="142" text-anchor="middle">右旋 y</text>
  <path class="sk0ln" d="M578,76 L532,110"/>
  <path class="sk0ln" d="M604,74 L648,110"/>
  <path class="sk0ln" d="M510,141 L476,180"/>
  <path class="sk0hl" d="M530,143 L548,180"/>
  <circle class="sk0nd" cx="590" cy="60" r="20"/>
  <text class="sk0ink" x="590" y="65" text-anchor="middle">y</text>
  <circle class="sk0nd" cx="520" cy="125" r="20"/>
  <text class="sk0ink" x="520" y="130" text-anchor="middle">x</text>
  <rect class="sk0sub" x="638" y="110" width="44" height="30" rx="6"/>
  <text class="sk0ink" x="660" y="130" text-anchor="middle">c</text>
  <rect class="sk0sub" x="448" y="180" width="44" height="30" rx="6"/>
  <text class="sk0ink" x="470" y="200" text-anchor="middle">a</text>
  <rect class="sk0hot" x="528" y="180" width="44" height="30" rx="6"/>
  <text class="sk0ink" x="550" y="200" text-anchor="middle">b</text>
  <text class="sk0mut" x="24" y="244">b 的 key 在 x 和 y 之间，所以它从 y 的左边改挂到 x 的右边，中序遍历仍是 a x b y c，顺序不变。</text>
  <text class="sk0mut" x="24" y="264">只改几个指针，O(1)：c 上移一层，a 下移一层。右边偏高时左旋一次，两边就拉平了。</text>
</svg>

**一次插入最多旋转 2 次，一次删除最多 3 次**，其余的修复都是变色；AVL 树删除时最坏要沿路径旋转 O(log n) 次，还要更新每个节点记的高度。旋转要改指针、动结构，变色只是改一个位，所以写多的场景红黑树更合适；读多写少、要的是最矮的树，AVL 稍快一点。删除的情况分得更细（删掉一个黑节点会让一条路径少一个黑节点，要从兄弟那边借），但思路一样：先变色，不行再旋转。

### 1.5 用在哪：std::map、Linux 调度器、epoll {#rb-uses}

C++ 的 `std::map`、`std::set` 在 libstdc++、libc++、MSVC 里都是红黑树（见 [STL 容器](/zh/ref/stl-containers/#map)）。libstdc++ 的树头是一个哨兵节点，它的父指针指向根，左右指针分别指向最小和最大的节点，所以 `begin()` 是 O(1)；迭代器 `++` 就是找中序后继：有右子树就去右子树的最左边，否则往上找第一个“自己在它左边”的祖先，均摊 O(1)。

Linux 内核在 `lib/rbtree.c` 里有一份通用的红黑树，用得很多：CFS 调度器把可运行的任务按已跑过的虚拟时间（vruntime）排在一棵红黑树里，最左边的节点单独缓存着，挑下一个要跑的任务是 O(1)，任务入队出队是 O(log n)；6.6 版起换成 EEVDF 调度器，排队用的仍是红黑树。[epoll](/zh/ref/epoll-internals/) 把登记的 fd 放在红黑树里，`epoll_ctl` 增删改是 O(log n)。Java 8 的 `HashMap` 在一个桶里的元素超过 8 个（且桶数组不小于 64）时，把这个桶的链表换成红黑树，让哈希冲突严重时最坏也只是 O(log n)。

## 2. 跳表

### 2.1 有序链表加索引层 {#skiplist-idea}

有序链表插入删除只改指针，但查找只能从头一个个走，O(n)。给它加一层“快车道”：每隔一个节点抽一个出来，串成上面一层链表；再从这一层每隔一个抽一个，串成更上面一层。查找从最高层开始往右走，下一个比目标大就下降一层，每层最多走两步，一共 $\log_2 n$ 层，O(log n)，就是在链表上做二分查找。

<svg viewBox="0 0 760 270" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="4 层的跳表，最底层 L0 有 1、3、5、7、9、12、15、18、21 共 9 个节点；L1 有 3、7、12、21；L2 有 7、21；L3 只有 21；查找 15 的路径是 head 的 L3 下降到 L2，走到 7，下降到 L1，走到 12，下降到 L0，下一个就是 15" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sk1bg  { fill: #fbfaf7; }
    .sk1nd  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .sk1hd2 { fill: #f3efe6; stroke: #b9b2a3; stroke-width: 1.2; }
    .sk1tg  { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.5; }
    .sk1ink { fill: #1c1b18; font-size: 12.5px; }
    .sk1mut { fill: #6b6558; font-size: 12px; }
    .sk1ln  { stroke: #b9c2cc; stroke-width: 1.2; fill: none; }
    .sk1hl  { stroke: #c98a76; stroke-width: 2.2; fill: none; }
    .sk1hd  { fill: #b9c2cc; }
    .sk1hh  { fill: #c98a76; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1nd { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1hd2 { fill: #26241f; stroke: #5d574b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1tg { fill: #4a2f2c; stroke: #c98a76; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1ln { stroke: #4a515c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk1hd { fill: #4a515c; }
  </style>
  <defs>
    <marker id="sk1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sk1hd"/></marker>
    <marker id="sk1b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sk1hh"/></marker>
  </defs>
  <rect class="sk1bg" x="0" y="0" width="760" height="270" rx="10"/>
  <text class="sk1mut" x="20" y="64">L3</text>
  <text class="sk1mut" x="20" y="104">L2</text>
  <text class="sk1mut" x="20" y="144">L1</text>
  <text class="sk1mut" x="20" y="184">L0</text>
  <text class="sk1mut" x="70" y="36" text-anchor="middle">head</text>
  <rect class="sk1hd2" x="48" y="47" width="44" height="26" rx="4"/>
  <rect class="sk1hd2" x="48" y="87" width="44" height="26" rx="4"/>
  <rect class="sk1hd2" x="48" y="127" width="44" height="26" rx="4"/>
  <rect class="sk1hd2" x="48" y="167" width="44" height="26" rx="4"/>
  <path class="sk1ln" d="M92,60 L666,60" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M362,100 L666,100" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M92,140 L176,140" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M222,140 L316,140" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M502,140 L666,140" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M92,180 L106,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M152,180 L176,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M222,180 L246,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M292,180 L316,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M362,180 L386,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M432,180 L456,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M572,180 L596,180" marker-end="url(#sk1a)"/>
  <path class="sk1ln" d="M642,180 L666,180" marker-end="url(#sk1a)"/>
  <path class="sk1hl" d="M70,73 L70,85" marker-end="url(#sk1b)"/>
  <path class="sk1hl" d="M92,100 L316,100" marker-end="url(#sk1b)"/>
  <path class="sk1hl" d="M340,113 L340,125" marker-end="url(#sk1b)"/>
  <path class="sk1hl" d="M362,140 L456,140" marker-end="url(#sk1b)"/>
  <path class="sk1hl" d="M480,153 L480,165" marker-end="url(#sk1b)"/>
  <path class="sk1hl" d="M502,180 L526,180" marker-end="url(#sk1b)"/>
  <rect class="sk1nd" x="108" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="130" y="185" text-anchor="middle">1</text>
  <rect class="sk1nd" x="178" y="127" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="200" y="145" text-anchor="middle">3</text>
  <rect class="sk1nd" x="178" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="200" y="185" text-anchor="middle">3</text>
  <rect class="sk1nd" x="248" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="270" y="185" text-anchor="middle">5</text>
  <rect class="sk1nd" x="318" y="87" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="340" y="105" text-anchor="middle">7</text>
  <rect class="sk1nd" x="318" y="127" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="340" y="145" text-anchor="middle">7</text>
  <rect class="sk1nd" x="318" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="340" y="185" text-anchor="middle">7</text>
  <rect class="sk1nd" x="388" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="410" y="185" text-anchor="middle">9</text>
  <rect class="sk1nd" x="458" y="127" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="480" y="145" text-anchor="middle">12</text>
  <rect class="sk1nd" x="458" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="480" y="185" text-anchor="middle">12</text>
  <rect class="sk1tg" x="528" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="550" y="185" text-anchor="middle">15</text>
  <rect class="sk1nd" x="598" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="620" y="185" text-anchor="middle">18</text>
  <rect class="sk1nd" x="668" y="47" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="690" y="65" text-anchor="middle">21</text>
  <rect class="sk1nd" x="668" y="87" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="690" y="105" text-anchor="middle">21</text>
  <rect class="sk1nd" x="668" y="127" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="690" y="145" text-anchor="middle">21</text>
  <rect class="sk1nd" x="668" y="167" width="44" height="26" rx="4"/>
  <text class="sk1ink" x="690" y="185" text-anchor="middle">21</text>
  <text class="sk1mut" x="24" y="226">查 15（红色路径）：每层往右走，直到下一个比 15 大就下降一层，head → 7 → 12 → 15。</text>
  <text class="sk1mut" x="24" y="248">一个 key 在各层的方块是同一个节点，节点里存着它在每一层的 next 指针。</text>
</svg>

### 2.2 随机层数：抛硬币决定节点有几层 {#random-level}

严格的“每隔一个抽一个”在插入一个节点以后就乱了，要维持它得重排整条索引。跳表的办法是不维持：新节点插入时抛硬币，正面就多长一层，直到抛出反面，所以节点至少有 1 层的概率是 1，至少有 2 层的概率是 1/2，至少有 $k$ 层的概率是 $1/2^{k-1}$。**索引不是排出来的，是按概率长出来的**，平均下来每一层的节点数是下一层的一半，和严格版本一样。

对 100 万个 key 实测，每层的节点数是：

```text
level 0: 1000000
level 1: 499709
level 2: 250168
level 3: 124861
level 4: 62426
level 5: 31250
```

最高层是 21，$\log_2 10^6 \approx 20$。查找时每一层往右走的期望步数是常数（概率为 $p$ 时是 $1/p$），层数期望是 $\log_{1/p} n$，所以查找、插入、删除的期望都是 O(log n)。最坏情况是所有节点都只抛出 1 层，退化成链表，但这个概率小到可以不考虑；而且它和输入的顺序无关，不像普通二叉搜索树按顺序插入就必然退化。

每个节点平均有 $1/(1-p)$ 个 next 指针：$p = 1/2$ 时是 2 个，和二叉树的左右孩子一样多；Redis 取 $p = 1/4$，平均约 1.33 个，用多走几步换更少的内存，最多 32 层。

### 2.3 代码 {#skiplist-code}

每个节点存一个 `next` 数组，`next[i]` 是它在第 `i` 层的下一个节点。查找、插入、删除都先做同一件事：从最高层往下，记下每一层上最后一个比目标小的节点，存进 `prev`。插入时这些就是新节点在各层的前驱，每一层做一次普通的链表插入；删除时把它们的 `next` 越过被删的节点。

```cpp
#include <cassert>
#include <cstdio>
#include <random>
#include <set>
#include <vector>

class SkipList {
    static constexpr int kMaxLevel = 32;
    struct Node {
        int key;
        std::vector<Node*> next;                       // next[i]：第 i 层的下一个节点
        Node(int k, int lv) : key(k), next(lv, nullptr) {}
    };
    Node head_{0, kMaxLevel};                          // 头节点：每一层都有，不存数据
    int level_ = 1;                                    // 当前最高层数
    std::mt19937 rng_{42};

    int random_level() {                               // 抛硬币：每多一层的概率是 1/2
        int lv = 1;
        while (lv < kMaxLevel && (rng_() & 1)) ++lv;
        return lv;
    }
    // 每一层上最后一个 key < target 的节点，存进 prev
    void find_prev(int target, Node* prev[]) {
        Node* x = &head_;
        for (int i = level_ - 1; i >= 0; --i) {
            while (x->next[i] && x->next[i]->key < target) x = x->next[i];
            prev[i] = x;
        }
    }
public:
    ~SkipList() {
        for (Node* x = head_.next[0]; x;) { Node* n = x->next[0]; delete x; x = n; }
    }
    bool contains(int key) {
        Node* prev[kMaxLevel];
        find_prev(key, prev);
        Node* x = prev[0]->next[0];
        return x && x->key == key;
    }
    bool insert(int key) {
        Node* prev[kMaxLevel];
        find_prev(key, prev);
        if (prev[0]->next[0] && prev[0]->next[0]->key == key) return false;
        int lv = random_level();
        for (int i = level_; i < lv; ++i) prev[i] = &head_;   // 新长出来的层，前驱是头节点
        if (lv > level_) level_ = lv;
        Node* n = new Node(key, lv);
        for (int i = 0; i < lv; ++i) {                 // 每一层都是一次普通的链表插入
            n->next[i] = prev[i]->next[i];
            prev[i]->next[i] = n;
        }
        return true;
    }
    bool erase(int key) {
        Node* prev[kMaxLevel];
        find_prev(key, prev);
        Node* x = prev[0]->next[0];
        if (!x || x->key != key) return false;
        for (int i = 0; i < (int)x->next.size(); ++i) prev[i]->next[i] = x->next[i];
        delete x;
        while (level_ > 1 && !head_.next[level_ - 1]) --level_;
        return true;
    }
    // 范围查询 [lo, hi]：先找到 lo，再沿最底层往后走
    std::vector<int> range(int lo, int hi) {
        Node* prev[kMaxLevel];
        find_prev(lo, prev);
        std::vector<int> out;
        for (Node* x = prev[0]->next[0]; x && x->key <= hi; x = x->next[0]) out.push_back(x->key);
        return out;
    }
    int level() const { return level_; }
    std::size_t count(int lv) const {                  // 第 lv 层上有几个节点
        std::size_t c = 0;
        for (const Node* x = head_.next[lv]; x; x = x->next[lv]) ++c;
        return c;
    }
};

int main() {
    SkipList s; std::set<int> ref; std::mt19937 g(7);
    for (int i = 0; i < 200000; ++i) {
        int k = g() % 50000, op = g() % 3;
        if (op == 0) assert(s.insert(k) == ref.insert(k).second);
        else if (op == 1) assert(s.erase(k) == (ref.erase(k) == 1));
        else assert(s.contains(k) == (ref.count(k) == 1));
    }
    auto r = s.range(100, 200);
    std::vector<int> want(ref.lower_bound(100), ref.upper_bound(200));
    assert(r == want);
    std::printf("ok: %zu keys, top level %d\n", ref.size(), s.level());
    SkipList t; for (int i = 0; i < 1000000; ++i) t.insert(i);
    std::printf("1e6 keys: top level %d\n", t.level());
    for (int lv = 0; lv < 6; ++lv) std::printf("level %d: %zu\n", lv, t.count(lv));
}
```

`main` 随机做 20 万次插入、删除、查找，每一步都和 `std::set` 的结果对比，最后再对比一次范围查询；GCC 16.2 `-O2` 下全部通过，输出 `ok: 23221 keys, top level 18`，上一节每层的节点数也是这个程序打出来的。和红黑树比，这里没有任何“修复”步骤：插入删除只碰目标位置前后的指针。

### 2.4 Redis 的有序集合为什么用跳表 {#redis-zset}

Redis 的有序集合（zset）里每个成员带一个分数，要支持按成员查分数、按分数排名、按分数或排名取一段。它用两个结构：一个哈希表从成员查分数，O(1)；一个按（分数，成员）排序的跳表，管顺序。元素少时（默认不超过 128 个、每个不超过 64 字节）两者都不用，直接存成一块紧凑的连续内存（listpack，早期叫 ziplist），挨个扫也很快。

选跳表而不是平衡树，理由有三条。**一是范围操作就是“找到起点、沿最底层往后走”**，`ZRANGEBYSCORE` 这类命令正好是这个形状；平衡树要靠中序后继一步步往上往下找。二是实现简单，没有旋转的分情况讨论，好写好调，Redis 在上面加功能也容易：每个节点的每一层多记一个跨度（span，这一步跨过了多少个节点），沿查找路径把跨度加起来就是排名，`ZRANK` 也是 O(log n)；最底层再加一个后退指针，就能倒着遍历。三是内存可调，$p$ 取 1/4 以后平均指针数比平衡树还少。

跳表还有一个 Redis 用不上的好处：并发友好。插入只改目标位置前后的几个指针，而且可以从最底层往上一层层地挂，每一层用一次 CAS（比较并交换）就能完成，不需要像平衡树旋转那样同时改一片节点。Java 的 `ConcurrentSkipListMap` 就是无锁跳表；LevelDB、RocksDB 写入时先进内存里的一张有序表（memtable），用的也是跳表，读的线程不用加锁。Redis 执行命令是单线程的，这一条不是它选跳表的原因。

## 3. B+ 树

### 3.1 一次读一页：磁盘上比的是读几次 {#disk-page}

数据库的数据在磁盘上。读内存一次约 100 ns，SSD 随机读一次约 $10\sim100\ \mu s$，机械硬盘约 $5\sim10$ ms，比内存慢 3 到 5 个数量级。而且磁盘按块读，读 1 个字节和读 16 KB 的代价几乎一样。所以在磁盘上，一次查找的代价约等于要读几个页，也就是树有几层。

一棵存 1000 万行的平衡二叉树有 24 层左右，查一行要 24 次随机读；红黑树最坏还要再翻倍。**解决办法是让每个节点就是一个页，一个页里塞几百上千个 key，分出几百上千个叉**，树就只有 3 到 4 层。这就是 B 树一族的思路。

### 3.2 结构：数据全在叶子里，叶子串成链表 {#bplus-structure}

B+ 树的内部节点只放 key 和指向子节点的指针，用来指路；真正的数据只放在叶子节点里，所有叶子在同一层，按 key 的顺序用指针串成链表（InnoDB 里是双向链表）。

<svg viewBox="0 0 760 276" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="两层的 B+ 树：根节点有 key 30 和 60，三个指针分别指向三个叶子；叶子 5 10 20、30 40 50、60 70 80 每个 key 下面带着整行数据，叶子之间双向相连；范围查询 10 到 50 从根走到第一个叶子，再沿链表读到第二个叶子" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sk2bg  { fill: #fbfaf7; }
    .sk2in  { fill: #f3efe6; stroke: #b9b2a3; stroke-width: 1.3; }
    .sk2key { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .sk2hit { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .sk2row { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.1; }
    .sk2ink { fill: #1c1b18; font-size: 13px; }
    .sk2mut { fill: #6b6558; font-size: 12px; }
    .sk2sm  { fill: #4f6b2a; font-size: 11px; }
    .sk2ln  { stroke: #6b6558; stroke-width: 1.3; fill: none; }
    .sk2hl  { stroke: #c98a76; stroke-width: 2.2; fill: none; }
    .sk2hd  { fill: #6b6558; }
    .sk2hh  { fill: #c98a76; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2in { fill: #26241f; stroke: #5d574b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2key { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2hit { fill: #4a2f2c; stroke: #c98a76; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2row { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2sm { fill: #b9d68a; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sk2hd { fill: #a19caf; }
  </style>
  <defs>
    <marker id="sk2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="sk2hd"/></marker>
    <marker id="sk2b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sk2hh"/></marker>
  </defs>
  <rect class="sk2bg" x="0" y="0" width="760" height="276" rx="10"/>
  <rect class="sk2in" x="300" y="30" width="160" height="32" rx="4"/>
  <path class="sk2ln" d="M330,30 L330,62 M380,30 L380,62 M430,30 L430,62"/>
  <text class="sk2ink" x="355" y="51" text-anchor="middle">30</text>
  <text class="sk2ink" x="405" y="51" text-anchor="middle">60</text>
  <text class="sk2mut" x="478" y="44">内部节点：只放 key 和子页指针，</text>
  <text class="sk2mut" x="478" y="62">一个 16 KB 的页能放 1000 多个</text>
  <path class="sk2hl" d="M315,62 L160,126" marker-end="url(#sk2b)"/>
  <path class="sk2ln" d="M380,62 L380,126" marker-end="url(#sk2a)"/>
  <path class="sk2ln" d="M445,62 L600,126" marker-end="url(#sk2a)"/>
  <rect class="sk2key" x="80" y="130" width="50" height="28"/>
  <text class="sk2ink" x="105" y="149" text-anchor="middle">5</text>
  <rect class="sk2hit" x="130" y="130" width="50" height="28"/>
  <text class="sk2ink" x="155" y="149" text-anchor="middle">10</text>
  <rect class="sk2hit" x="180" y="130" width="50" height="28"/>
  <text class="sk2ink" x="205" y="149" text-anchor="middle">20</text>
  <rect class="sk2hit" x="305" y="130" width="50" height="28"/>
  <text class="sk2ink" x="330" y="149" text-anchor="middle">30</text>
  <rect class="sk2hit" x="355" y="130" width="50" height="28"/>
  <text class="sk2ink" x="380" y="149" text-anchor="middle">40</text>
  <rect class="sk2hit" x="405" y="130" width="50" height="28"/>
  <text class="sk2ink" x="430" y="149" text-anchor="middle">50</text>
  <rect class="sk2key" x="530" y="130" width="50" height="28"/>
  <text class="sk2ink" x="555" y="149" text-anchor="middle">60</text>
  <rect class="sk2key" x="580" y="130" width="50" height="28"/>
  <text class="sk2ink" x="605" y="149" text-anchor="middle">70</text>
  <rect class="sk2key" x="630" y="130" width="50" height="28"/>
  <text class="sk2ink" x="655" y="149" text-anchor="middle">80</text>
  <rect class="sk2row" x="80" y="160" width="50" height="22"/>
  <text class="sk2sm" x="105" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="130" y="160" width="50" height="22"/>
  <text class="sk2sm" x="155" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="180" y="160" width="50" height="22"/>
  <text class="sk2sm" x="205" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="305" y="160" width="50" height="22"/>
  <text class="sk2sm" x="330" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="355" y="160" width="50" height="22"/>
  <text class="sk2sm" x="380" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="405" y="160" width="50" height="22"/>
  <text class="sk2sm" x="430" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="530" y="160" width="50" height="22"/>
  <text class="sk2sm" x="555" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="580" y="160" width="50" height="22"/>
  <text class="sk2sm" x="605" y="175" text-anchor="middle">整行</text>
  <rect class="sk2row" x="630" y="160" width="50" height="22"/>
  <text class="sk2sm" x="655" y="175" text-anchor="middle">整行</text>
  <path class="sk2hl" d="M233,150 L301,150" marker-end="url(#sk2b)"/>
  <path class="sk2ln" d="M233,138 L301,138" marker-start="url(#sk2a)"/>
  <path class="sk2ln" d="M459,150 L526,150" marker-end="url(#sk2a)"/>
  <path class="sk2ln" d="M459,138 L526,138" marker-start="url(#sk2a)"/>
  <text class="sk2mut" x="24" y="216">叶子：key 和整行数据（InnoDB 的主键索引），按 key 的顺序双向串起来。</text>
  <text class="sk2mut" x="24" y="236">查 id 在 10 到 50 之间的行（红色）：从根走到 10 所在的叶子，再沿链表往右读，读到 50 为止。</text>
  <text class="sk2mut" x="24" y="256">不管查哪个 key，都要走到叶子，每次查找读的页数一样多。</text>
</svg>

### 3.3 高度：3 层装得下 2000 多万行 {#bplus-height}

InnoDB 的页是 16 KB。主键是 8 字节的 `BIGINT` 时，内部节点里一项是 8 字节的 key 加 6 字节的页指针，约 14 字节，一页放得下约 $16384 / 14 \approx 1170$ 项，也就是 1170 个分叉。叶子存整行，一行 1 KB 的话一页放 16 行左右。于是：

$$
\underbrace{1170}_{\text{根的分叉}} \times \underbrace{1170}_{\text{第二层的分叉}} \times \underbrace{16}_{\text{每个叶子的行数}} \;\approx\; 2190 \text{ 万行}
$$

3 层的 B+ 树就存得下 2000 多万行，查一行读 3 个页。根节点和第二层被访问得最频繁，通常一直留在内存的缓冲池里，真正去磁盘读的往往只有叶子那 1 次。

### 3.4 B 树和 B+ 树的区别 {#b-vs-bplus}

B 树的每个节点都存数据，key 在哪一层找到就在哪一层返回。B+ 树把数据全挪到叶子，带来三点不同。**第一，内部节点不存数据，一页能放的 key 更多，分叉更多，树更矮**，读的页更少。第二，每次查找都走到叶子，读的页数一样多，性能稳定；B 树运气好在根就找到了，运气差要到最底层。第三，范围查询：B+ 树找到起点后沿叶子链表顺序读；B 树的数据散在各层，要做中序遍历，在不同层的节点之间来回跳，每一跳都可能是一次随机读。

### 3.5 InnoDB 为什么用 B+ 树 {#innodb}

和其他结构比一遍，理由就清楚了。哈希索引等值查询是 O(1)，但做不了范围查询、`ORDER BY` 和最左前缀匹配，而这些是 SQL 的日常；InnoDB 只在内存里对热点页自动建一层自适应哈希索引作补充。红黑树、AVL 树这类二叉树太高，每层一次磁盘读，1000 万行要 24 次以上；而且一个节点只占几十字节，却要占一整个页去读。B 树的问题是上一节那三点。

InnoDB 的表本身就是一棵按主键组织的 B+ 树，叶子里放整行，叫聚簇索引。其他的二级索引也是 B+ 树，但叶子里放的是主键值，查到以后还要拿主键回聚簇索引再查一次，叫回表；要查的列都在二级索引里时不用回表，叫覆盖索引。

插入时叶子页满了就要分裂：分配一个新页，挪一半数据过去，再在父节点里加一项，父节点满了继续往上分裂。主键用自增 ID 时，新行总是追加在最右边的叶子，页按顺序填满，几乎没有中间分裂；用随机的 UUID 当主键，新行随机落在各个叶子中间，频繁分裂，页只填一半左右，空间和缓存都浪费。

## 4. 对比 {#compare}

| | 红黑树 | 跳表 | B+ 树 |
|---|---|---|---|
| 查找 | 最坏 O(log n)，树高 ≤ $2\log_2(n+1)$ | 期望 O(log n) | $O(\log_m n)$ 次读页，$m$ 是分叉数，几百上千 |
| 范围查询 | 找到起点后逐个找中序后继 | 找到起点后沿最底层走 | 找到起点后沿叶子链表读 |
| 插入、删除的调整 | 变色加最多 2 到 3 次旋转 | 只改前后的指针，不调整 | 页满分裂、过空合并 |
| 每个元素的额外开销 | 3 个指针加 1 位颜色 | 平均 $1/(1-p)$ 个指针 | 内部节点的一项，摊到每行很少 |
| 实现难度 | 高，插入删除分很多情况 | 低 | 高，还要处理页的管理和持久化 |
| 用在哪 | `std::map`、Linux 调度器、epoll、Java `HashMap` 的桶 | Redis 有序集合、LevelDB 和 RocksDB 的内存表、Java `ConcurrentSkipListMap` | MySQL InnoDB 等关系数据库的索引、很多文件系统的目录和区段索引 |

三者渐近复杂度一样，选哪个看一步的代价落在哪。红黑树和跳表在内存里，一步是一次指针跳转，选的是确定的最坏界（红黑树）还是简单和并发友好（跳表）。B+ 树在磁盘上，一步是一次读页，所以宁可在一个节点里多比较几百次，也要少走一层。

这个道理到内存里也成立，只是“页”换成了缓存行：红黑树每走一步都是一次可能未命中缓存的指针跳转（见[硬件地图](/zh/ref/cpu-memory/)），而一个节点放十几个 key 的内存 B 树，一次未命中能排除更多候选，所以像 Abseil 的 `btree_map` 这样的有序容器，在 key 很多时常常比 `std::map` 快，也更省内存。
