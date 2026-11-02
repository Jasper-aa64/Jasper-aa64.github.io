---
title: "LRU 缓存：哈希表加双向链表"
date: 2026-11-02
slug: "lru-cache"
description: "容量满了先淘汰最久没用的那个，get 和 put 都要 O(1)。哈希表能按 key 一步找到，却不记顺序；双向链表记着顺序、能一步挪动和删除，却没法按 key 找。把两者拼起来：哈希表里存链表节点的位置。用 std::list 写时靠 splice 挪节点，不用每次重新分配；不让用 std::list 时，带两个哨兵手写双向链表。最后看 Linux 页缓存、Redis、多线程缓存里的 LRU 都改成了什么样。"
summary: "LRU 要两样东西：按 key 一步找到，按使用先后排好队。哈希表给前一样，双向链表给后一样，哈希表的值存链表节点的位置把两者接上。命中时用 splice 把节点挪到头部，节点不动、位置不变，哈希表也不用改。"
toc: true
group: cpplinux
weight: 111
---

缓存放不下所有东西，满了就得扔掉一个。扔哪个？LRU（least recently used，最近最少使用）的回答是：扔最久没被用过的那个，赌的是刚用过的东西很快还会再用。面试里的标准题是 [LeetCode 146](https://leetcode.cn/problems/lru-cache/)：实现 `get(key)` 和 `put(key, value)`，容量固定，两个操作都要 O(1)。

## 1. 为什么是哈希表加双向链表

### 1.1 两个要求，各要一种结构 {#two-needs}

`get` 要按 key 一步找到值，这是哈希表的事；可哈希表里的元素没有先后，满了的时候说不出谁最久没用。要记住先后，就得有一个按使用时间排好的队：每用一次，把这个元素挪到队头，队尾自然就是最久没用的，淘汰时删队尾。这个队要支持“从中间拿出一个、插到队头”和“删掉队尾”都是 O(1)，数组做不到（中间删一个要挪后面所有元素），链表可以。

可链表按 key 找又要从头走一遍，O(n)。**所以两种结构拼起来用：哈希表里存的不是值，而是这个 key 在链表里那个节点的位置。** 按 key 查哈希表一步拿到节点，再在链表里把节点挪到头部，两步都是 O(1)。

<svg viewBox="0 0 760 296" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="左边是哈希表，每个 key 对应一个指向链表节点的位置；右边是双向链表，头部是最近用过的节点，尾部是最久没用、最先淘汰的节点，相邻节点之间有 next 和 prev 两个指针" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .lr0bg  { fill: #fbfaf7; }
    .lr0h   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .lr0n   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .lr0old { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .lr0ink { fill: #1c1b18; font-size: 13px; }
    .lr0mut { fill: #6b6558; font-size: 12px; }
    .lr0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .lr0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .lr0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0h { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0n { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0old { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0ink, :root:is([data-theme="dark"], [data-theme="black"]) .lr0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr0hd { fill: #a19caf; }
  </style>
  <defs><marker id="lr0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="lr0hd"/></marker></defs>
  <rect class="lr0bg" x="0" y="0" width="760" height="296" rx="10"/>
  <text class="lr0ttl" x="24" y="34">哈希表 pos_：key → 节点的位置</text>
  <text class="lr0ttl" x="400" y="34">双向链表 items_：按使用先后排队</text>
  <rect class="lr0h" x="24" y="60" width="220" height="40" rx="6"/>
  <text class="lr0ink" x="40" y="85">key 1  →  节点位置</text>
  <rect class="lr0h" x="24" y="130" width="220" height="40" rx="6"/>
  <text class="lr0ink" x="40" y="155">key 3  →  节点位置</text>
  <rect class="lr0h" x="24" y="200" width="220" height="40" rx="6"/>
  <text class="lr0ink" x="40" y="225">key 5  →  节点位置</text>
  <rect class="lr0n" x="400" y="60" width="180" height="40" rx="6"/>
  <text class="lr0ink" x="416" y="85">(key 1, value 10)</text>
  <rect class="lr0n" x="400" y="130" width="180" height="40" rx="6"/>
  <text class="lr0ink" x="416" y="155">(key 3, value 30)</text>
  <rect class="lr0old" x="400" y="200" width="180" height="40" rx="6"/>
  <text class="lr0ink" x="416" y="225">(key 5, value 50)</text>
  <path class="lr0ln" d="M244,80 L397,80" marker-end="url(#lr0a)"/>
  <path class="lr0ln" d="M244,150 L397,150" marker-end="url(#lr0a)"/>
  <path class="lr0ln" d="M244,220 L397,220" marker-end="url(#lr0a)"/>
  <path class="lr0ln" d="M460,100 L460,127" marker-end="url(#lr0a)"/>
  <path class="lr0ln" d="M520,130 L520,103" marker-end="url(#lr0a)"/>
  <path class="lr0ln" d="M460,170 L460,197" marker-end="url(#lr0a)"/>
  <path class="lr0ln" d="M520,200 L520,173" marker-end="url(#lr0a)"/>
  <text class="lr0mut" x="430" y="119">next</text>
  <text class="lr0mut" x="528" y="119">prev</text>
  <text class="lr0mut" x="596" y="85">头部：刚用过</text>
  <text class="lr0mut" x="596" y="219">尾部：最久没用，</text>
  <text class="lr0mut" x="596" y="235">满了先淘汰它</text>
  <text class="lr0mut" x="24" y="276">哈希表里本来没有顺序，这里排齐只是好画。每个节点里也存着 key：淘汰尾部时，要靠它去删哈希表里那一项。</text>
</svg>

### 1.2 为什么要双向：删一个节点要找它的前一个 {#why-doubly}

把节点挪到头部，第一步是把它从原来的位置摘下来，也就是让它前一个节点的 `next` 跳过它、指向它后一个。单向链表里，节点只知道后一个是谁，要找前一个只能从头走，O(n)；双向链表每个节点多存一个 `prev`，前一个一步就拿到。淘汰尾部也一样：删掉尾节点以后，新的尾是它的前一个。**多出来的这个 `prev` 指针，换来的是摘节点和删尾部都是 O(1)。**

节点里除了值还要存 key，原因在淘汰那一步：从链表尾拿到最久没用的节点后，还得把哈希表里对应的那一项删掉，而哈希表只能按 key 删。节点里不存 key，就不知道该删哪一项。

## 2. 用 std::list 写

### 2.1 代码 {#std-list}

```cpp
#include <list>
#include <unordered_map>
#include <utility>

class LRUCache {
public:
    explicit LRUCache(int capacity) : cap_(capacity) {}

    int get(int key) {
        auto it = pos_.find(key);                       // 只查一次哈希表
        if (it == pos_.end()) return -1;
        items_.splice(items_.begin(), items_, it->second);  // 节点挪到头部，不分配、不释放
        return it->second->second;                      // 迭代器还指着同一个节点
    }

    void put(int key, int value) {
        auto it = pos_.find(key);
        if (it != pos_.end()) {                         // 已有：改值，挪到头部
            it->second->second = value;
            items_.splice(items_.begin(), items_, it->second);
            return;
        }
        if (items_.size() == static_cast<size_t>(cap_)) {   // 满了：淘汰尾部
            pos_.erase(items_.back().first);            // 用节点里存的 key 删哈希表
            items_.pop_back();
        }
        items_.emplace_front(key, value);
        pos_[key] = items_.begin();
    }

private:
    int cap_;
    std::list<std::pair<int, int>> items_;              // 头部最近用过，尾部最久没用
    std::unordered_map<int, std::list<std::pair<int, int>>::iterator> pos_;
};
```

`std::list` 就是双向链表，`pos_` 里存的是指向链表节点的迭代器。`put` 分三种情况：key 已经在，改值、挪到头部；key 不在且满了，先删尾部再插；key 不在且没满，直接插到头部。

### 2.2 splice：挪节点而不是删了再插 {#splice}

把命中的节点挪到头部，直观的写法是 `erase` 掉它，再 `push_front` 一个新的，然后把新位置写回哈希表。这样每次命中都要释放一个节点、再分配一个节点（每个节点都是一次 `new`，见 [new 一次走到哪](/zh/ref/new-malloc-page-fault/)），哈希表也得再写一次。

`splice(pos, other, it)` 是把 `it` 指的那个节点从 `other` 里摘下来，接到 `pos` 前面。摘和接都只改几个 `prev`、`next` 指针，节点本身还是原来那块内存，所以**指向它的迭代器仍然有效，哈希表里存的位置一个字都不用改**。`get` 命中时只剩一次哈希查找加几次指针赋值。

<svg viewBox="0 0 760 250" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="get(5) 之前链表是 1、3、5，5 在尾部；splice 把节点 5 摘下来接到头部，之后链表是 5、1、3，节点 5 还是同一块内存，哈希表里的位置不用改" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .lr1bg  { fill: #fbfaf7; }
    .lr1n   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .lr1hit { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .lr1ink { fill: #1c1b18; font-size: 13px; }
    .lr1mut { fill: #6b6558; font-size: 12px; }
    .lr1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .lr1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .lr1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1n { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1hit { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1ink, :root:is([data-theme="dark"], [data-theme="black"]) .lr1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lr1hd { fill: #a19caf; }
  </style>
  <defs><marker id="lr1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="lr1hd"/></marker></defs>
  <rect class="lr1bg" x="0" y="0" width="760" height="250" rx="10"/>
  <text class="lr1ttl" x="24" y="34">get(5) 之前</text>
  <text class="lr1ttl" x="440" y="34">之后</text>
  <text class="lr1mut" x="24" y="60">头部</text>
  <rect class="lr1n" x="70" y="44" width="180" height="36" rx="6"/>
  <text class="lr1ink" x="86" y="67">(1, 10)</text>
  <rect class="lr1n" x="70" y="104" width="180" height="36" rx="6"/>
  <text class="lr1ink" x="86" y="127">(3, 30)</text>
  <text class="lr1mut" x="24" y="182">尾部</text>
  <rect class="lr1hit" x="70" y="164" width="180" height="36" rx="6"/>
  <text class="lr1ink" x="86" y="187">(5, 50)</text>
  <path class="lr1ln" d="M160,80 L160,101" marker-end="url(#lr1a)"/>
  <path class="lr1ln" d="M160,140 L160,161" marker-end="url(#lr1a)"/>
  <path class="lr1ln" d="M280,122 L400,122" marker-end="url(#lr1a)"/>
  <text class="lr1mut" x="296" y="112">splice 到头部</text>
  <text class="lr1mut" x="296" y="144">只改几个指针</text>
  <text class="lr1mut" x="440" y="60">头部</text>
  <rect class="lr1hit" x="486" y="44" width="180" height="36" rx="6"/>
  <text class="lr1ink" x="502" y="67">(5, 50)</text>
  <rect class="lr1n" x="486" y="104" width="180" height="36" rx="6"/>
  <text class="lr1ink" x="502" y="127">(1, 10)</text>
  <text class="lr1mut" x="440" y="182">尾部</text>
  <rect class="lr1n" x="486" y="164" width="180" height="36" rx="6"/>
  <text class="lr1ink" x="502" y="187">(3, 30)</text>
  <path class="lr1ln" d="M576,80 L576,101" marker-end="url(#lr1a)"/>
  <path class="lr1ln" d="M576,140 L576,161" marker-end="url(#lr1a)"/>
  <text class="lr1mut" x="24" y="230">绿色的节点 5 前后是同一块内存：哈希表里存的位置还指着它，不用改。下一个被淘汰的变成了 3。</text>
</svg>

### 2.3 两个细节 {#details}

`get` 里只调一次 `find`，拿到的迭代器接着用。先 `find` 判断有没有、再用 `pos_[key]` 取值，同一个 key 要哈希两次；`operator[]` 在 key 不存在时还会悄悄插入一项，用在查找上容易埋坑。

`items_.size()` 返回的是无符号的 `size_t`，直接和 `int` 的容量比较，编译器会给有符号、无符号比较的警告，所以这里转一下类型。容量是 0 时，这份代码会在空链表上 `back()`，LeetCode 保证容量至少是 1，自己用的时候要在构造时挡掉。

## 3. 不让用 std::list：自己写双向链表

### 3.1 两个哨兵节点 {#sentinels}

面试常加一句“不许用 `std::list`”，考的是手写链表的指针操作。最容易出错的是边界：插入第一个节点、删掉最后一个节点时，头指针、尾指针要单独处理。**办法是放两个不存数据的哨兵节点**，一个永远在最前，一个永远在最后，真正的节点都夹在中间。这样每个真节点都一定有前一个和后一个，摘节点、插到头部都只有一种写法，不用判断空。

```cpp
class LRUCache {
    struct Node { int key, val; Node* prev; Node* next; };
public:
    explicit LRUCache(int capacity) : cap_(capacity) {
        head_.next = &tail_; tail_.prev = &head_;       // 两个哨兵：链表永远不空
    }
    ~LRUCache() {
        for (Node* n = head_.next; n != &tail_;) { Node* nx = n->next; delete n; n = nx; }
    }
    LRUCache(const LRUCache&) = delete;                 // 节点归这个对象管，不能浅拷贝
    LRUCache& operator=(const LRUCache&) = delete;

    int get(int key) {
        auto it = pos_.find(key);
        if (it == pos_.end()) return -1;
        Node* n = it->second;
        unlink(n); push_front(n);
        return n->val;
    }
    void put(int key, int value) {
        auto it = pos_.find(key);
        if (it != pos_.end()) {
            Node* n = it->second;
            n->val = value; unlink(n); push_front(n);
            return;
        }
        if (static_cast<int>(pos_.size()) == cap_) {
            Node* lru = tail_.prev;                     // 尾哨兵前面那个就是最久没用的
            unlink(lru); pos_.erase(lru->key); delete lru;
        }
        Node* n = new Node{key, value, nullptr, nullptr};
        push_front(n);
        pos_[key] = n;
    }
private:
    static void unlink(Node* n) { n->prev->next = n->next; n->next->prev = n->prev; }
    void push_front(Node* n) {
        n->prev = &head_; n->next = head_.next;
        head_.next->prev = n; head_.next = n;
    }
    int cap_;
    Node head_{0, 0, nullptr, nullptr}, tail_{0, 0, nullptr, nullptr};
    std::unordered_map<int, Node*> pos_;
};
```

`unlink` 和 `push_front` 各两三行，有了哨兵就没有一个 `if`。`push_front` 里四句赋值的顺序有讲究：先设好新节点自己的 `prev`、`next`，再改两边邻居；要是先把 `head_.next` 改成 `n`，就找不到原来的第一个节点了。

两份代码在本机用 GCC 16.2 `-std=c++17 -O2 -Wall -Wextra` 编译、跑同一组用例（容量 2，依次 put、get、淘汰、更新），结果一致，没有警告。

### 3.2 节点归谁管 {#ownership}

节点是 `new` 出来的，哈希表里存的只是裸指针，释放的责任在 `LRUCache` 自己：淘汰时 `delete`，析构时把剩下的全删掉。正因为对象里管着一堆堆内存，默认的拷贝构造只会把指针复制一份，两个对象析构时会把同一批节点删两次，所以把拷贝删掉。想省掉手动 `delete`，可以让节点由 `std::unique_ptr` 持有，或者干脆预先分配一个节点数组、用下标代替指针。

## 4. 实际系统里的 LRU

### 4.1 Linux 页缓存：两条链表 {#page-cache}

[IO 地图](/maps/io-map.zh.html)里的页缓存满了也要淘汰页，但它不用严格的 LRU。严格 LRU 有一个弱点：把一个大文件从头读到尾一遍，读过的每一页都会依次排到队头，把真正常用的页全挤出去，可这些页以后再也不会用。所以内核把页分到两条链表上：第一次访问的页进“不活跃”链表，在那里又被访问一次才升到“活跃”链表；淘汰先从不活跃链表的尾部挑。只读一次的页在不活跃链表里就被淘汰了，碰不到活跃链表里的常用页。

### 4.2 Redis：抽样的近似 LRU {#redis}

Redis 设成 `allkeys-lru` 时，并没有把所有 key 串成一条链表：几千万个 key，每个多两个指针就是几百 MiB，每次访问还要改链表。它的做法是每个 key 只记一个最近访问的时间戳，要淘汰时随机抽几个 key（默认 5 个），扔掉其中最久没访问的。结果和严格 LRU 很接近，省掉了整条链表。

### 4.3 多线程：读也要上锁 {#threads}

普通的哈希表，多个线程同时读不用互斥。LRU 不一样：`get` 也要把节点挪到头部，读其实是一次写，所以每个操作都得拿锁，一把锁护住哈希表和链表。线程一多，所有人都排在这一把锁上。常见的办法是分片：按 key 的哈希值把缓存分成十几份，每份一个独立的 LRU、一把锁，不同分片的操作互不阻塞。LevelDB 的块缓存就是这样，分成 16 个分片。代价是 LRU 只在每个分片内部成立，整体上淘汰的不一定是全局最久没用的那个。
