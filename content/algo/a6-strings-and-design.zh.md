---
title: "A6：字符串与设计题"
date: 2026-11-06
slug: "a6-strings-and-design"
description: "字符串和设计题：KMP 的前缀函数让匹配失败时文本指针不回头，字符串哈希把子串变成一个数、O(1) 比较（双模数，别用自然溢出），Trie 合并公共前缀，01-Trie 贪心求最大异或；设计题先定接口再选结构：LRU 用哈希表加双向链表，订单簿用有序价位加每档一条 FIFO 队列加订单号索引，做到 O(1) 撤单，限流器在固定窗口、滑动窗口、令牌桶之间取舍。附 9 道练习题。"
weight: 7
math: true
toc: true
---
这一轮分两块：

- **字符串题难在比较子串很贵**：两个长 $m$ 的子串逐个字符比要 $O(m)$，放进循环就是 $O(nm)$。KMP、字符串哈希、Trie 各用一种办法把这一步变便宜。
- **设计题考的是选数据结构**：题目给出几个操作，要选出让每个操作都够快的组合，并说清每个操作的复杂度。订单簿是 HFT 面试里最常见的一道。

## 1. 字符串：把比较子串变便宜

### 1.1 KMP：匹配失败时，模式往回跳，文本不回头

[LC 28 找出字符串中第一个匹配项的下标](https://leetcode.cn/problems/find-the-index-of-the-first-occurrence-in-a-string/)：给文本 `haystack` 和模式 `needle`，返回模式第一次出现的下标，没有就返回 −1。两个串长度都不超过 $10^4$，只有小写字母。

1. **朴素匹配慢在失败后从头再来**
   - **朴素做法对每个起点逐个字符比**：失败就把起点右移一格，模式从头再比，最坏 $O(nm)$，比如在 `aaa…a` 里找 `aa…ab`。
   - **浪费在已经比过的信息上**：失败前已经对上了模式的前 $k$ 个字符，文本里这一段的内容就是已知的，不该再比一遍。

2. **前缀函数：每个位置上最长的相等真前缀和真后缀**
   - **定义**：$\pi[i]$ 是 `s[0..i]` 这一段里，既是前缀又是后缀的最长子串的长度，不算整段本身。
   - **例子**：`s = "aabaaab"` 时，$\pi$ = `0 1 0 1 2 2 3`。最后一位是 3，因为整段的前 3 个字符 `aab` 和后 3 个字符 `aab` 相同。
   - **它回答的问题**：模式已经对上了前 $k$ 个字符，下一个字符对不上时，模式最多还能保住前 $\pi[k-1]$ 个。这一段既是模式的前缀，又是文本里刚比过那段的后缀，不用再比。

   ```cpp
   std::vector<int> prefix_function(const std::string& s) {
       int n = s.size();
       std::vector<int> pi(n, 0);
       for (int i = 1; i < n; i++) {
           int k = pi[i - 1];                            // 先试上一个位置的最长相等前后缀
           while (k > 0 && s[i] != s[k]) k = pi[k - 1];  // 接不上，就退到次长的那个
           if (s[i] == s[k]) k++;
           pi[i] = k;
       }
       return pi;
   }
   ```

   - **求前缀函数也是在自己身上做匹配**：位置 $i$ 先试着接在 $\pi[i-1]$ 后面；接不上就退到 $\pi[k-1]$，也就是次长的相等前后缀，直到接上或者退到 0。

3. **KMP：失败时 `k = pi[k - 1]`，文本的下标从不回头**

   ```cpp
   int strStr(const std::string& text, const std::string& pat) {
       int m = pat.size();
       std::vector<int> pi = prefix_function(pat);
       int k = 0;                                        // text 的当前位置已经对上了 pat 的前 k 个字符
       for (int i = 0; i < (int)text.size(); i++) {
           while (k > 0 && text[i] != pat[k]) k = pi[k - 1];
           if (text[i] == pat[k]) k++;
           if (k == m) return i - m + 1;                 // 要找全部出现位置：记下来，再 k = pi[k - 1] 接着找
       }
       return -1;
   }
   ```

   - **`k` 是唯一的状态**：文本的当前位置已经对上了模式的前 `k` 个字符。
   - **对不上就让 `k = pi[k - 1]`**：相当于把模式右移到下一个可能对上的位置，文本的 `i` 不动。
   - **`k == m` 就是找到了**：要找所有出现位置，就记下来，再让 `k = pi[k - 1]` 接着找。

4. **复杂度是 $O(n + m)$：`k` 涨得慢，退得再多也有限**
   - **`k` 每一步最多加 1**：整个过程加起来最多加 $n$ 次。
   - **while 每执行一次，`k` 至少减 1**：`k` 不会小于 0，所以 while 的总次数不超过加的总次数，也是 $O(n)$。求前缀函数同理是 $O(m)$。

5. **前缀函数还能求最短周期：LC 459 重复的子字符串**
   - **题意**：判断一个字符串能不能由它的某个子串重复多次构成，$n \le 10^4$。
   - **结论**：设 $p = n - \pi[n-1]$，串能由子串重复构成，当且仅当 $p < n$ 并且 $p$ 整除 $n$。

   ```cpp
   bool repeatedSubstringPattern(const std::string& s) {
       int n = s.size();
       int p = n - prefix_function(s)[n - 1];            // 最短周期
       return p < n && n % p == 0;
   }
   ```

   - **为什么 $p$ 是最短周期**：最长相等前后缀长 $n - p$，意思是 `s[i] == s[i + p]` 对所有能比的 $i$ 都成立，所以 $p$ 是串的周期，而且是最短的。
   - **为什么还要 $p$ 整除 $n$**：$p$ 整除 $n$ 时，串就是前 $p$ 个字符重复 $n / p$ 次。反过来，串要是由长 $d$ 的块重复构成，$d$ 也是周期，由周期引理，最短周期 $p$ 一定整除 $d$，所以也整除 $n$。

> **认出 KMP**
>
> - **在长文本里找一个模式串的出现位置或次数**：KMP，$O(n + m)$。
> - **问字符串的周期、最短循环节，或者“最长的既是前缀又是后缀的子串”**：直接看前缀函数，最后一个问题的答案就是 $\pi[n-1]$。
> - **C++ 的 `std::string::find` 不保证线性**：常见实现是逐个起点比，最坏 $O(nm)$，数据专门构造过时会超时。

### 1.2 字符串哈希：子串变成一个数，O(1) 比较

1. **多项式哈希：把串看成一个 $B$ 进制数**
   - **定义**：长 $m$ 的串 $s$，哈希是 $h(s) = \left(\sum_{i=0}^{m-1} s_i B^{\,m-1-i}\right) \bmod M$。
   - **前缀哈希按位递推**：$H_0 = 0$，$H_{i+1} = H_i \cdot B + s_i$。
   - **任意子串的哈希 O(1) 算出**：

   $$h(s[l, r)) = H_r - H_l \cdot B^{\,r-l} \pmod M$$

   - **这和前缀和求区间和是同一个想法**：只是前面那一段要先乘上 $B^{\,r-l}$，把位数对齐了再减。

   ```cpp
   struct StrHash {
       static constexpr uint64_t M1 = 1000000007, M2 = 998244353, B = 131;
       std::vector<uint64_t> h1, h2, p1, p2;             // h[i] = s 前 i 个字符的哈希，p[i] = B^i
       explicit StrHash(const std::string& s)
           : h1(s.size() + 1), h2(s.size() + 1), p1(s.size() + 1), p2(s.size() + 1) {
           p1[0] = p2[0] = 1;
           for (size_t i = 0; i < s.size(); i++) {
               uint64_t c = (unsigned char)s[i];
               h1[i + 1] = (h1[i] * B + c) % M1;
               h2[i + 1] = (h2[i] * B + c) % M2;
               p1[i + 1] = p1[i] * B % M1;
               p2[i + 1] = p2[i] * B % M2;
           }
       }
       uint64_t get(int l, int r) const {                // 子串 s[l, r) 的哈希，两个模数拼成一个 64 位数
           uint64_t a = (h1[r] + M1 - h1[l] * p1[r - l] % M1) % M1;
           uint64_t b = (h2[r] + M2 - h2[l] * p2[r - l] % M2) % M2;
           return a << 32 | b;
       }
   };
   ```

   - **哈希相等不等于串相等**：不同的串可能撞到同一个值。只用一个模数 $M$ 时，两个不同的随机串撞上的概率约 $1/M$，比较的次数一多就不可忽略。
   - **两个模数一起用，撞上要两边同时撞**：概率约 $1/(M_1 M_2) \approx 10^{-18}$。两个 30 位的值拼成一个 64 位数，正好能直接放进哈希表。
   - **`h1[l] * p1[r - l]` 不会溢出**：两个数都小于 $2^{30}$，乘积小于 $2^{60}$。

2. **别用 `unsigned long long` 自然溢出**
   - **自然溢出就是模 $2^{64}$**：写起来省事，乘加完不用取模。
   - **它能被专门构造的数据卡掉**：Thue–Morse 串（从 `a` 开始，每次把整串的 `a`、`b` 互换后接在后面）长 2048 时，和它互换后的串，在任何奇数底数下模 $2^{64}$ 的哈希都相等。实测 3 到 1999 的全部 999 个奇数底数，一个不落都撞上了；偶数底数更糟，乘几次高位就移出去了。
   - **用大质数取模，底数在启动时随机选**：对方不知道底数，就没法事先构造冲突。上面的代码为了对拍用了固定的 131，比赛和线上要换成随机数。

3. **最长重复子串（LC 1044）：二分长度，哈希判重**
   - **题意**：找出 `s` 里出现至少两次（可以重叠）的最长子串，没有就返回空串。$n \le 3 \times 10^4$，只有小写字母。
   - **长度有单调性**：长 $L$ 的子串有重复，长 $L - 1$ 的一定也有（取它的前 $L - 1$ 个字符），所以能二分长度，用 A1 第 2 节“找第一个为真”的写法。
   - **判一个长度只要 $O(n)$**：把所有长 $L$ 的子串的哈希放进哈希表，插入时发现已经在里面，就是有重复。

   ```cpp
   std::string longestDupSubstring(const std::string& s) {
       int n = s.size();
       StrHash h(s);
       auto find = [&](int L) -> int {                   // 长 L 的子串有没有出现两次：有就返回一个起点
           std::unordered_set<uint64_t> seen;
           for (int i = 0; i + L <= n; i++)
               if (!seen.insert(h.get(i, i + L)).second) return i;
           return -1;
       };
       int lo = 0, hi = n;                               // 长 lo 有重复（长 0 算有），长 hi 没有
       while (hi - lo > 1) {
           int mid = (lo + hi) / 2;
           if (find(mid) != -1) lo = mid; else hi = mid;
       }
       return lo == 0 ? "" : s.substr(find(lo), lo);
   }
   ```

   - **复杂度是 $O(n \log n)$**：二分 $\log n$ 轮，每轮 $O(n)$。
   - **哈希表比的只是哈希值**：真要稳妥，哈希撞上时再比一次原串。双模数下误判的概率可以忽略，这里没比。
   - **例子**：`"banana"` 返回 `"ana"`，它在下标 1 和 3 各出现一次，两次重叠；`"abcd"` 返回空串。

> **认出字符串哈希**
>
> - **要反复判断两个子串是否相等**：前缀哈希预处理 $O(n)$，之后每次 $O(1)$。
> - **求“最长的满足某性质的子串”，而且性质随长度单调**：二分长度，每个长度用哈希判断。
> - **只比较一两次**：直接比字符，不值得为它做预处理。

### 1.3 Trie：公共前缀合在一起存

[LC 208 实现 Trie（前缀树）](https://leetcode.cn/problems/implement-trie-prefix-tree/)：实现 `insert`（插入一个单词）、`search`（这个单词插入过没有）、`startsWith`（有没有插入过的单词以它开头）。单词和前缀长度不超过 2000，只有小写字母，调用总数不超过 $3 \times 10^4$。

1. **Trie 把公共前缀合在一起存，查一个串只和它自己的长度有关**
   - **每条边是一个字符**：从根往下走一条路径，就拼出一个前缀；单词在哪个节点结束，就在那里打一个结束标记。
   - **查一个长 $m$ 的串只要 $O(m)$**：和存了多少个单词无关。
   - **`search` 和 `startsWith` 只差最后一步**：两者都沿着串往下走；`startsWith` 走得通就行，`search` 还要求终点有结束标记。

   ```cpp
   class Trie {
       struct Node {
           int next[26];
           bool end = false;                             // 有没有单词在这里结束
           Node() { std::fill(next, next + 26, -1); }
       };
       std::vector<Node> nodes_{1};                      // 节点放在数组里，0 号是根
       int walk(const std::string& w) const {            // 沿着 w 往下走，走不下去返回 -1
           int u = 0;
           for (char c : w) {
               u = nodes_[u].next[c - 'a'];
               if (u == -1) return -1;
           }
           return u;
       }
   public:
       void insert(const std::string& w) {
           int u = 0;
           for (char c : w) {
               int d = c - 'a';
               if (nodes_[u].next[d] == -1) {
                   nodes_[u].next[d] = nodes_.size();    // 先记下新节点的下标
                   nodes_.emplace_back();                // 再扩容：扩容会让指向旧元素的引用失效
               }
               u = nodes_[u].next[d];
           }
           nodes_[u].end = true;
       }
       bool search(const std::string& w) const { int u = walk(w); return u != -1 && nodes_[u].end; }
       bool startsWith(const std::string& p) const { return walk(p) != -1; }
   };
   ```

   - **节点放在 `vector` 里，用下标互相连**：比每个节点 `new` 一次少很多次分配，内存也是连续的。
   - **坑：`vector` 扩容会让引用失效**：要是写成 `int& v = nodes_[u].next[d]; if (v == -1) { nodes_.emplace_back(); v = nodes_.size() - 1; }`，`emplace_back` 扩容以后，`v` 指向的旧内存已经释放，再写它就是未定义行为。先写下标、再扩容，或者全程只用下标。
   - **空间是节点数乘 26 个整数**：单词多、字符集大时很占内存，可以把 `next` 换成 `unordered_map` 或者排好序的小数组，查找慢一点。

2. **01-Trie：按二进制位存数，贪心求最大异或（LC 421）**
   - **题意**：[LC 421](https://leetcode.cn/problems/maximum-xor-of-two-numbers-in-an-array/) 在数组里选两个数，求它们异或的最大值。$n \le 2 \times 10^5$，每个数在 $[0, 2^{31})$ 里。
   - **把每个数按位从高到低插进一棵二叉 Trie**：每个节点只有两个孩子，0 和 1。
   - **查询时每一位都尽量走和自己相反的那边**：某一位异或得 1，比它下面所有低位全是 1 还大，所以从高到低能取 1 就取 1，这个贪心是对的。

   ```cpp
   int findMaximumXOR(const std::vector<int>& nums) {
       std::vector<std::array<int, 2>> ch(1, {-1, -1});  // 01-Trie：每个节点两个孩子
       int best = 0;
       for (int x : nums) {
           int u = 0;
           for (int b = 30; b >= 0; b--) {               // 从最高位往下插入 x
               int d = x >> b & 1;
               if (ch[u][d] == -1) { ch[u][d] = ch.size(); ch.push_back({-1, -1}); }
               u = ch[u][d];
           }
           u = 0;
           int cur = 0;
           for (int b = 30; b >= 0; b--) {               // 每一位尽量走和 x 相反的那边
               int d = x >> b & 1;
               if (ch[u][d ^ 1] != -1) { cur |= 1 << b; u = ch[u][d ^ 1]; }
               else u = ch[u][d];
           }
           best = std::max(best, cur);
       }
       return best;
   }
   ```

   - **复杂度是 $O(31 n)$**：每个数插入和查询各走 31 层。
   - **先插入再查询，路径一定存在**：至少有 `x` 自己那条，不用判空；和自己异或得 0，不影响最大值。
   - **`ch[u][d] = ch.size()` 在 `push_back` 之前**：这一行先算右边、再写左边，写完才扩容，没有引用失效的问题。

> **认出 Trie**
>
> - **在一组单词上反复问前缀**：自动补全、按前缀计数，或者单词搜索 II（LC 212），在网格上 DFS 时沿着 Trie 走，走不下去就剪枝。
> - **问“选两个数，异或最大”**：01-Trie，每一位贪心。
> - **只问整个单词在不在**：`unordered_set` 就够了，不用 Trie。

## 2. 设计题：每个操作要什么能力，就选什么结构

设计题给出一组操作，要求每个操作都够快。**答题的主线是先列出每个操作需要什么能力，再挑一组能同时提供这些能力的数据结构**，最后用复杂度说明每个操作确实够快。

> **面试时设计题怎么答**
>
> - **先问需求和规模**：有哪些操作、各自多频繁、数据量多大、要不要线程安全。订单簿要问一个标的上同时挂多少单、价格范围多大、撤单占多少比例。
> - **再定接口**：把函数签名写出来，输入、输出和失败时返回什么都说清楚。
> - **然后选数据结构，给出每个操作的复杂度**：每个操作说一句“它需要什么能力，所以用什么结构”。
> - **最后谈边界和并发**：容量满了怎么办、撤一个不存在的单返回什么、时间戳倒退怎么办；多线程时是加一把锁、按键分片，还是改成单线程处理、别的线程通过队列把请求交给它。

### 2.1 LRU 缓存：哈希表定位，双向链表排新旧

[LC 146 LRU 缓存](https://leetcode.cn/problems/lru-cache/)：实现一个容量固定的缓存，`get(key)` 返回值（没有返回 −1），`put(key, value)` 插入或更新；满了以后再插入新键，要淘汰最久没被用过的那一项。`get` 和 `put` 都要平均 $O(1)$。容量不超过 3000，调用不超过 $2 \times 10^5$ 次。

1. **两个需求要两个结构：按键查找，按最近使用的时间排序**
   - **按键 $O(1)$ 查找**：哈希表。
   - **$O(1)$ 把一项挪到“最新”、$O(1)$ 删掉“最旧”**：双向链表，最近用过的放在表头，最久没用的就在表尾。
   - **哈希表里存的是链表节点的位置**：查到键，就直接拿到链表里的那个节点，不用在链表里找。

   ```cpp
   class LRUCache {
       int cap_;
       std::list<std::pair<int, int>> items_;            // (key, value)，最近用过的在最前
       std::unordered_map<int, std::list<std::pair<int, int>>::iterator> pos_;  // key → 它在链表里的位置
   public:
       explicit LRUCache(int capacity) : cap_(capacity) {}
       int get(int key) {
           auto f = pos_.find(key);
           if (f == pos_.end()) return -1;
           items_.splice(items_.begin(), items_, f->second);  // 挪到最前，不拷贝，迭代器不失效
           return f->second->second;
       }
       void put(int key, int value) {
           auto f = pos_.find(key);
           if (f != pos_.end()) {
               f->second->second = value;
               items_.splice(items_.begin(), items_, f->second);
               return;
           }
           if ((int)items_.size() == cap_) {
               pos_.erase(items_.back().first);          // 淘汰最久没用的：链表尾
               items_.pop_back();
           }
           items_.emplace_front(key, value);
           pos_[key] = items_.begin();
       }
   };
   ```

2. **`splice` 让“挪到最前”不拷贝，位置也不失效**
   - **`items_.splice(items_.begin(), items_, it)` 只改几个指针**：把 `it` 指的节点摘下来接到表头，$O(1)$。
   - **`std::list` 的迭代器在 `splice` 以后仍然有效**：哈希表里存的位置不用更新。
   - **淘汰时先删哈希表里的项，再删链表尾**：顺序反过来的话，`items_.back()` 已经没了，拿不到它的键。
   - **复杂度**：`get` 和 `put` 都是平均 $O(1)$，空间 $O(\text{容量})$。
   - **例子**：容量 2，依次 `put(1,1)`、`put(2,2)`、`get(1)` 得 1、`put(3,3)` 淘汰键 2、`get(2)` 得 −1、`put(4,4)` 淘汰键 1，之后 `get(1)`、`get(3)`、`get(4)` 分别得 −1、3、4。

3. **追问时常问的几点**
   - **链表节点里必须存键**：淘汰表尾时，要靠这个键去哈希表里删对应的项。
   - **`put` 一个已有的键也算“用过”**：要更新值并挪到最前，不触发淘汰。
   - **多线程时读写锁帮不上忙**：`get` 也会改链表，读也是写，一把互斥锁护住整个结构最简单；要提高并发，就按键分片，每片一把锁、一个独立的 LRU。
   - **LFU（LC 460）按使用次数淘汰**：同样次数里淘汰最久没用的。做法是一张“次数 → 一条 LRU 链表”的哈希表，再记住当前的最小次数，每个操作仍然是 $O(1)$。

> **认出 LRU 这一类**
>
> - **要 $O(1)$ 查找，又要 $O(1)$ 调整顺序**：哈希表加双向链表，哈希表里存链表的迭代器。
> - **顺序按时间排**（最近用过、先来后到）：链表就够；**顺序按大小排**：换成 `map` 或堆。

### 2.2 订单簿：价格优先、时间优先

题目：实现一个标的的限价订单簿。

- **`add(order)`**：来一笔限价单，先和对手方能成交的挂单撮合，没成交完的部分挂进簿里，返回成交列表。
- **`cancel(id)`**：撤掉一笔还挂着的单，单不存在就返回 false。
- **撮合规则是价格优先、时间优先**：买单先和最低的卖价成交，卖单先和最高的买价成交；同一价位上先来的先成交；成交价取挂单的价格。

1. **三个需求，三个结构**
   - **随时找到最优价，价位之间要有序**：`std::map<价格, 价位>`，`begin()` 就是最优价。
   - **同一价位里先来的先成交**：每个价位一条 FIFO 队列，新单接在队尾，成交从队头开始。
   - **按订单号直接找到这笔单**：`unordered_map<订单号, 位置>`，撤单时不用扫队列。
   - **买方要价格从高到低，卖方要从低到高**：买方的键存成 `-price`，两边就能用同一种 `map`，位置也能用同一种迭代器存。

   ```cpp
   struct Order { int64_t id; bool buy; int64_t price; int64_t qty; };
   struct Fill  { int64_t taker, maker, price, qty; };   // 主动方、被动方、成交价、成交量

   class OrderBook {
       using Queue = std::list<Order>;                   // 一个价位上的订单，按到达顺序
       using Book  = std::map<int64_t, Queue>;           // 键 → 价位；begin() 是最优价
       Book bids_, asks_;                                // 买方的键是 -price，卖方的键是 price
       struct Loc { Book* book; Book::iterator level; Queue::iterator it; };
       std::unordered_map<int64_t, Loc> index_;          // 订单号 → 它在哪个价位、队列里哪个位置
       static int64_t key(bool buy, int64_t price) { return buy ? -price : price; }
   public:
       std::vector<Fill> add(Order o) {
           std::vector<Fill> fills;
           Book& opp = o.buy ? asks_ : bids_;
           while (o.qty > 0 && !opp.empty()) {
               auto level = opp.begin();                 // 对手方的最优价位
               Queue& q = level->second;
               Order& m = q.front();                     // 这一价位里最早到的
               if (o.buy ? m.price > o.price : m.price < o.price) break;  // 价格对不上，停
               int64_t x = std::min(o.qty, m.qty);
               fills.push_back({o.id, m.id, m.price, x});  // 按挂单的价格成交
               o.qty -= x;
               m.qty -= x;
               if (m.qty == 0) { index_.erase(m.id); q.pop_front(); }
               if (q.empty()) opp.erase(level);
           }
           if (o.qty > 0) {                              // 没成交完的部分挂在自己这一方
               Book& own = o.buy ? bids_ : asks_;
               auto level = own.try_emplace(key(o.buy, o.price)).first;
               level->second.push_back(o);
               index_[o.id] = {&own, level, std::prev(level->second.end())};
           }
           return fills;
       }
       bool cancel(int64_t id) {
           auto f = index_.find(id);
           if (f == index_.end()) return false;          // 已经成交完或撤过了
           Loc loc = f->second;
           loc.level->second.erase(loc.it);
           if (loc.level->second.empty()) loc.book->erase(loc.level);
           index_.erase(f);
           return true;
       }
   };
   ```

2. **撮合从对手方的最优价位、最早的那一笔开始吃**
   - **价格对不上就停**：买单遇到比自己限价高的卖价，或者卖单遇到比自己限价低的买价，就不能再成交了。
   - **每次成交量取两笔里小的那个**：被吃完的挂单出队，并从索引里删掉；价位空了，就从 `map` 里删掉。
   - **成交价取挂单的价格**：挂单先到，价格是它报的，后来的主动方接受这个价格。
   - **剩下的部分挂进自己这一方**：`try_emplace` 找到或者新建这个价位，接到队尾，再记下位置。
   - **例子**：卖方挂着 101 元 5 股（1 号）、100 元 3 股（2 号）、100 元 4 股（3 号），来一笔 101 元买 9 股（4 号）。先吃 100 元的价位，2 号成交 3 股、3 号成交 4 股；再吃 101 元的价位，1 号成交 2 股。4 号全部成交，1 号剩 3 股继续挂着。

3. **撤单 $O(1)$：索引里存好价位和队列里的位置**
   - **索引里存三样东西**：属于哪一方的 `map`、价位的迭代器、队列里的迭代器。`std::map` 和 `std::list` 的迭代器在别的元素增删时都不失效，所以可以一直存着。
   - **撤单就是在队列里删一个节点**：价位空了再删价位，按迭代器删都是 $O(1)$。
   - **撤一个已经成交完的单返回 false**：成交完的单在撮合时已经从索引里删掉了。

4. **复杂度：撮合按成交笔数算，撤单和看最优价都是 $O(1)$**
   - **撮合的代价和吃掉的笔数成正比**：每吃一笔都是常数次操作，只有新建一个价位时要在 `map` 里找一次，$O(\log P)$。

   | 操作 | 复杂度 | 说明 |
   |---|---|---|
   | `add`，不成交，挂进簿里 | $O(\log P)$ | $P$ 是价位数，`try_emplace` 要在 `map` 里找这个价位 |
   | `add`，成交 $k$ 笔 | $O(k + \log P)$ | 每吃一笔 $O(1)$，按迭代器删掉一个空价位是均摊 $O(1)$ |
   | `cancel` | 平均 $O(1)$ | 哈希表定位，链表删节点 |
   | 看最优价 | $O(1)$ | `begin()` |

5. **真实系统常把 `map` 换成按价格下标的数组**
   - **价格都落在最小变动单位（tick）的网格上**：A 股是 0.01 元，价格可以换成整数个 tick。
   - **一天里价格的范围有限**：A 股有涨跌停，能出现的价位就那么多个，开一个数组，下标是（价格 − 跌停价）÷ tick。
   - **数组版每一步都是 $O(1)$，访存也连续**：找价位直接按下标，不用在红黑树里一层层追指针；最优价用一个变量记着，价位被吃空时往外扫到下一个非空的价位，价位密集时扫得很短。
   - **`std::list` 每个节点都要分配一次内存**：真实系统用预先分配好的订单池，加侵入式链表（前后指针直接放在订单结构体里），热路径上不调 `malloc`。
   - **价格范围没有上限的品种才用 `map`**：或者用数组覆盖最优价附近的价位，`map` 兜底远处的价位。

> **订单簿追问时常问的几点**
>
> - **为什么不用堆存价位**：堆只能 $O(1)$ 看最优价，删中间的价位要懒删除，也没法按顺序遍历前 10 档去发行情。
> - **改单怎么处理**：多数交易所的规则是改价或者加量都算撤掉重新排队，失去时间优先；只减量一般保留原来的位置。A 股没有改单，只能撤单重报。
> - **市价单怎么撮合**：当作价格无穷大（买）或 0（卖）的限价单去吃，吃不完的部分不挂，直接撤掉。

### 2.3 限流器：固定窗口、滑动窗口、令牌桶

题目：实现 `bool allow(t)`，时刻 `t` 来一个请求，决定放不放行，限制“每 $W$ 时间最多 `limit` 次”。交易系统里最常见的用处是给报单限速：交易所和券商对报单速率有上限，超了会被拒单。

1. **固定窗口：时间切成格子，每格计数**

   ```cpp
   class FixedWindowLimiter {                            // 时间切成长 W 的格子，每格最多 limit 次
       int64_t W_, limit_, window_ = INT64_MIN, count_ = 0;
   public:
       FixedWindowLimiter(int64_t W, int64_t limit) : W_(W), limit_(limit) {}
       bool allow(int64_t t) {
           int64_t w = t / W_;                           // t 落在第几个格子
           if (w != window_) { window_ = w; count_ = 0; }  // 进了新格子，计数清零
           if (count_ == limit_) return false;
           ++count_;
           return true;
       }
   };
   ```

   - **每个请求 $O(1)$，只存两个数**：当前是第几个格子，这个格子放行了几次。
   - **毛病是格子边界上能放行 2 倍**：限制“每 1000 ms 最多 5 次”，999 ms 来 5 次、1000 ms 再来 5 次，两批各在自己的格子里，全部放行，2 ms 里放行了 10 次。实测正是 10 次，下面的滑动窗口只放行 5 次。

2. **滑动窗口：记下窗口里每次放行的时间**

   ```cpp
   class SlidingWindowLimiter {                          // 任何长 W 的时间段 (t - W, t] 里最多 limit 次
       int64_t W_;
       size_t limit_;
       std::deque<int64_t> times_;                       // 窗口里放行过的时间戳
   public:
       SlidingWindowLimiter(int64_t W, size_t limit) : W_(W), limit_(limit) {}
       bool allow(int64_t t) {
           while (!times_.empty() && times_.front() <= t - W_) times_.pop_front();  // 滑出窗口的扔掉
           if (times_.size() == limit_) return false;
           times_.push_back(t);
           return true;
       }
   };
   ```

   - **任何一段长 $W$ 的时间里都不超过 `limit` 次**：没有边界问题。
   - **每个请求均摊 $O(1)$，但要存 `limit` 个时间戳**：限得宽的时候（比如每秒 10 万次），内存不小。
   - **折中的做法是滑动窗口计数**：只存当前格子和上一个格子的计数，按上一格在窗口里还占多少比例加权估算，内存 $O(1)$，代价是结果近似。

3. **令牌桶：按时间补令牌，允许一阵突发**

   ```cpp
   class TokenBucket {                                   // 桶里最多 cap 个令牌，每过 1 个时间单位补 rate 个
       int64_t cap_, rate_, tokens_, last_;
   public:
       TokenBucket(int64_t cap, int64_t rate, int64_t t0) : cap_(cap), rate_(rate), tokens_(cap), last_(t0) {}
       bool allow(int64_t t) {
           tokens_ = std::min(cap_, tokens_ + (t - last_) * rate_);  // 用到时才按经过的时间一次补齐
           last_ = t;
           if (tokens_ == 0) return false;
           --tokens_;
           return true;
       }
   };
   ```

   - **请求来了拿走一个令牌，拿不到就拒绝**：桶里最多 `cap` 个，每过一个时间单位补 `rate` 个。
   - **不用定时器补令牌**：请求来的时候，按距上次经过的时间一次补齐，和每个时间单位补一次的结果一样。
   - **长期平均速率是 `rate`，短时间最多连着放行 `cap` 个**：适合“平均不超过多少，但允许偶尔来一阵”的需求。
   - **坑：空闲很久以后 `(t - last_) * rate_` 可能溢出**：可以先把时间差截到 `cap_ / rate_ + 1`。速率不是整数时，把时间单位取细（纳秒），或者改成“每 `interval` 纳秒补一个令牌”。

> **三种限流怎么选**
>
> - **只要大致限住，实现最简单**：固定窗口，接受边界上的 2 倍。
> - **要求任何一段时间都不超限**：滑动窗口，比如对外承诺的报单速率。
> - **只限平均速率，允许突发**：令牌桶。

## 练习

每题后面一句话提示练的是哪一节。订单簿和限流器没有对应的 OJ 题，照 2.2、2.3 自己写一遍，再拿一个暴力版本（所有挂单放一个数组、每次线性找最优）对拍。

**必做**

1. [LeetCode 28 找出字符串中第一个匹配项的下标](https://leetcode.cn/problems/find-the-index-of-the-first-occurrence-in-a-string/)：1.1 的前缀函数和 KMP。
2. [LeetCode 1044 最长重复子串](https://leetcode.cn/problems/longest-duplicate-substring/)：二分长度，双模数哈希判重。
3. [LeetCode 208 实现 Trie（前缀树）](https://leetcode.cn/problems/implement-trie-prefix-tree/)：节点放数组，注意扩容。
4. [LeetCode 421 数组中两个数的最大异或值](https://leetcode.cn/problems/maximum-xor-of-two-numbers-in-an-array/)：01-Trie，每一位贪心。
5. [LeetCode 146 LRU 缓存](https://leetcode.cn/problems/lru-cache/)：哈希表存链表迭代器，`splice`。

**选做**

6. [LeetCode 459 重复的子字符串](https://leetcode.cn/problems/repeated-substring-pattern/)：前缀函数求最短周期。
7. [LeetCode 1392 最长快乐前缀](https://leetcode.cn/problems/longest-happy-prefix/)：答案就是 $\pi[n-1]$。
8. [LeetCode 212 单词搜索 II](https://leetcode.cn/problems/word-search-ii/)：网格 DFS 沿着 Trie 剪枝。
9. [LeetCode 460 LFU 缓存](https://leetcode.cn/problems/lfu-cache/)：次数到 LRU 链表的哈希表，记住最小次数。

## 和地图上其他格子的连接

- 字符串哈希和 A1 的前缀和是同一个想法，二分长度用的也是 A1 第 2 节的模板。
- 01-Trie 和 L2 的线性基都在处理异或：01-Trie 回答“和某一个数异或最大是多少”，线性基回答“任选一组数，异或最大是多少”。
- KMP 的前缀函数在 B3 的字符串进阶里推广成 AC 自动机：在 Trie 上给每个节点配一个失配指针，一遍扫文本就能匹配一整组模式串。
- 订单簿用逐笔委托和逐笔成交重建时，做的就是 2.2 的 `add` 和 `cancel`。
