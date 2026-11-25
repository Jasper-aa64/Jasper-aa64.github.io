---
title: "L3：线性基"
date: 2026-11-02
slug: "l3-xor-basis"
aliases: ["/algo/l2-xor-basis/"]
description: "异或是 GF(2) 上的加法，任选子集的异或和构成一个线性空间，线性基是它的一组至多 60 个数的基：按最高位插入、2^r 种值每种由 2^(n-r) 个子集得到、最大值贪心、规范化后第 k 小；前缀异或、带权贪心、区间询问留最靠右的数；例题最大 XOR 和路径；两道近年赛题：CCPC Final 2025 L 数不同的区间张成空间，2026 ICPC 网络赛第二场 A 求最小的公共空间。附 8 道练习题。"
weight: 17
math: true
toc: true
---
给 $n$ 个数，从中任选一些异或起来，最大能得到多少？

- **子集太多，枚举不动**：$n = 50$ 时子集有 $2^{50}$ 个。
- **异或值里有大量重复**：$a$、$b$、$a \oplus b$ 三个数能异或出的值，和只用 $a$、$b$ 时一样，第三个数是多余的。
- **去掉多余的数，最多剩 60 个**：每个数 60 位，剩下的数能异或出的值一个不少，这组数就是**线性基**。要说清“多余”是什么、为什么最多剩 60 个，得把异或放进线性代数里看。

<style>.chroma .line.hl{background:rgba(56,139,253,.15)}</style>

## 1. 线性基是什么

### 1.1 一个数是 GF(2) 上的向量

**把数看成 0/1 向量，异或就是向量加法，子集异或和就是线性组合。**

1. **异或就是模 2 的向量加法**
   - **一个数是一个 60 维的 0/1 向量**：小于 $2^{60}$ 的数写成 60 位二进制，每一位是一个分量。
   - **两个数异或是逐位相加再模 2**：$1 \oplus 1 = 0$ 正好是 $1 + 1 \equiv 0 \pmod 2$。只有 0、1 两个元素、加法乘法都模 2 的域叫 **GF(2)**（也写 $\mathbb{F}_2$）。
2. **子集异或和就是系数只取 0、1 的线性组合**
   - **线性组合 $x_1 a_1 + \cdots + x_n a_n$（$x_i \in \{0, 1\}$）就是把 $x_i = 1$ 的数异或起来**：所以线性代数的概念可以直接搬过来。
     - **张成的空间**：所有子集异或和组成的集合，记作 $\operatorname{span}(a_1, \dots, a_n)$。
     - **线性无关**：没有一个非空子集的异或和等于 0。题面写“不存在异或和为 0 的非空子集”，说的就是它。
     - **基与秩**：线性无关、又能异或出空间里每个值的一组数叫基，基里数的个数叫秩，记作 $r$；60 维空间里 $r \le 60$。
   - **实数上是同一套概念**：[L1 线性代数](/zh/algo/l1-linear-algebra/)讲了一般的模型，以及同一组 0/1 向量为什么在实数和 GF(2) 上秩不同。
3. **线性基就是去掉多余的数后剩下的那组**
   - **“多余”就是能被别的数异或出来**：去掉它不改变张成的空间；去到不能再去时，剩下的数线性无关，就是一组基。
   - **换成基以后，数的个数从 $n$ 降到 $r \le 60$**：能异或出的值不变，后面所有问题都在这至多 60 个数上做。

### 1.2 按最高位存：插入就是一边插入一边消元

**`b[i]` 只放最高位是第 $i$ 位的数；插入时从高位往低位，用已有的基消掉 $x$ 的 1，停在空位就存下，消成 0 就说明 $x$ 已经能被异或出来。**

1. **怎么存、怎么插**
   - **`b[i]` 要么是 0，要么是最高位恰好为第 $i$ 位的数**：一共 60 个位置。
   - **插入 $x$ 时从第 59 位往下看**：第 $i$ 位是 1 而 `b[i]` 空着，就把 $x$ 存进 `b[i]`；`b[i]` 有数，就令 $x \leftarrow x \oplus b_i$，把这一位消成 0，继续看更低的位。
   - **例子**：下面的动画按位走一遍插入 6、3、5、1。5 被消成 0，插入失败；其余三个各占一个位置。可以换成自己的数。

<iframe src="/maps/xor-basis-insert.zh.html" title="线性基插入：分步看" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:545px;overflow:hidden;margin:1.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/xor-basis-insert.zh.html" target="_blank" rel="noopener">在新窗口打开</a></p>

2. **插入失败，说明它能被异或出来**
   - **$x$ 每一步异或的都是基里的数**：所以始终有 $x_{\text{原}} = x_{\text{当前}} \oplus (\text{若干个 } b_i)$。消成 0，说明 $x_{\text{原}}$ 等于若干个基的异或，基不变；停在空位，存进去的数和 $x_{\text{原}}$ 张成的空间一样，秩加 1。
   - **这就是 `contains`**：判断一个数能不能异或出来，对它走一遍同样的消元，看最后剩不剩 0。
3. **存下的数一定线性无关**
   - **它们的最高位两两不同**：任取一个非空子集异或，最高位最高的那个数在这一位是 1，别的数在这一位都是 0，结果不可能是 0。所以插完后 `b` 里的非零数就是一组基，个数就是秩 $r$。
4. **插入就是模 2 的高斯消元，只是来一行消一行**
   - **线性基能在线插入**：把 $n$ 个数排成 $n$ 行 60 列的 0/1 矩阵，`b[i]` 是主元在第 $i$ 列的行，“用 `b[i]` 消掉第 $i$ 位”是一次行变换。高斯消元拿到整个矩阵再逐列消，线性基来一个消一个。
   - **`b` 是行阶梯形**：按 $i$ 从大到小排就是行阶梯形，1.4 的规范化再把它整理成简化行阶梯形。

### 1.3 计数：$2^r$ 种值，每种 $2^{n-r}$ 个子集

**$n$ 个数任选子集，共 $2^n$ 种选法，异或出来只有 $2^r$ 种不同的值，而且每种值都恰好由 $2^{n-r}$ 种选法得到。**

1. **用 $a = (6, 3, 5)$ 先看一遍**
   - **插入后秩是 2**：二进制是 `110`、`011`、`101`。6 存进 `b[2]`，3 存进 `b[1]`；5 异或 6 得 `011`，再异或 3 得 0，插入失败。所以 $r = 2$，$n - r = 1$。
   - **8 个子集只异或出 4 种值**：按异或值分组如下。
     - **得 0**：$\{\}$、$\{6, 3, 5\}$。
     - **得 3**：$\{3\}$、$\{6, 5\}$。
     - **得 5**：$\{5\}$、$\{6, 3\}$。
     - **得 6**：$\{6\}$、$\{3, 5\}$。
   - **每种值恰好 2 个子集**：4 种就是 $2^r$，每种 2 个就是 $2^{n-r}$，没有哪个值多、哪个值少。
2. **不同的值为什么正好 $2^r$ 种**
   - **基的每种选法给出一个不同的值**：基里 $r$ 个数各选或不选，共 $2^r$ 种选法。两种选法要是给出同一个值，把它们异或起来就是一个非空子集异或出 0，和线性无关矛盾。基又能凑出空间里的每个值，所以正好 $2^r$ 种。
   - **例子**：基是 6 和 3，四种选法给出 0、6、3、5。
3. **每种值为什么恰好 $2^{n-r}$ 个子集**
   - **插入失败的数随便选，剩下的由基唯一补齐**：要凑出 $v$，插入失败的 $n - r$ 个数怎么选都行，共 $2^{n-r}$ 种；每种选完，还差的部分基恰好有一种选法补上，因为基的表示唯一。所以凑出每个 $v$ 的子集都是 $2^{n-r}$ 个，和 $v$ 是哪个值无关。
   - **例子**：失败的数是 5。凑 6 时，不选 5 就选 6，得 $\{6\}$；选 5 就还差 3，再选 3，得 $\{3, 5\}$。
4. **做题时怎么用这个结论**
   - **数异或和等于 $t$ 的子集**：$t$ 能异或出来（`contains(t)`）就是 $2^{n-r}$ 个，否则 0 个。代码见 2.2。
   - **数异或和为 0 的非空子集**：0 一定能得到，有 $2^{n-r}$ 个子集，去掉空集是 $2^{n-r} - 1$ 个。
   - **把全部 $2^n$ 个子集的异或和排序**：不去重时看成 $2^r$ 种不同的值，每种连续重复 $2^{n-r}$ 次。见 2.5 末尾。

### 1.4 规范化：每个主元位只留在一个数里，值的大小顺序就是选法的二进制

> 规范化的本质：把线性基整理成它所在空间唯一的标准形，于是第 $k$ 小能按二进制位直接读出，两个空间是否相同也能直接比基。

1. **为什么要规范化**
   - **第 $k$ 小要排出全部 $2^r$ 个值的顺序，原样的 `b` 看不出来**：高位的基在低位上带着 1，会干扰低位的比较。
2. **规范化做什么**
   - **让每个主元位只出现在自己那个数里**：非零 `b[i]` 的最高位 $i$ 叫**主元位**。`b[i]` 在某个更低的主元位 $j$ 上是 1，就异或上 `b[j]` 把它消掉。代码见 2.4。
3. **规范化之后，值的大小顺序就是选法的二进制顺序**
   - **结果在主元位上的比特就是选法**：把基按主元位从低到高编号为 $c_0, \dots, c_{r-1}$，$c_t$ 的主元位是 $p_t$。别的基在第 $p_t$ 位都是 0，所以结果的第 $p_t$ 位就是“$c_t$ 选了没有”。
   - **两种选法比大小，只看选得不一样的最高编号**：设这个编号是 $t$。高于 $p_t$ 的位只受编号大于 $t$ 的基影响，两边一样；第 $p_t$ 位上，选了 $c_t$ 的一边是 1。所以把选法写成二进制数 $\sum_{t \text{ 被选}} 2^t$，结果的大小顺序和它一致：第 $k$ 小（$k$ 从 0 数）就是按 $k$ 的二进制位选基。
   - **例子**：下图是一个 4 位的例子，上面是规范化前后的 `b`，下面是 $k = 0, \dots, 7$ 选出的值。

<a href="/images/algo/xor-basis-rref-kth.zh.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-rref-kth.zh.svg" alt="规范化和第 k 小：左边 b[3]=1101、b[2]=0111、b[0]=0001，主元列里多出来的 1 标红；经过 b[2]^=b[0]、b[3]^=b[2]、b[3]^=b[0] 三步，右边变成 1010、0110、0001，主元列 3、2、0 各只剩一个 1。下面 k 从 0 到 7，按 k 的二进制选 c0=b[0]、c1=b[2]、c2=b[3]，得到 0、1、6、7、10、11、12、13，值在主元位上的比特就是 k 的比特，所以按 k 递增。" style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

4. **规范化后的基由空间唯一决定**
   - **两个空间相同，当且仅当规范化后的基相同**：证明和用法见 5.1 的思路第 2 点。

### 1.5 前提：要的集合对异或封闭

**线性基回答的是“任选子集”能异或出的全部值，要用它，题目要的集合必须对异或封闭。**

1. **任选子集的异或值对异或封闭**
   - **两个子集的异或和再异或，等于两个子集的对称差的异或和**：仍是某个子集的异或和，所以可以用基代替原来的数。
2. **带选取限制时往往不封闭，不能直接用**
   - **例子**：$a = (1, 2, 4)$，规定不能选相邻的两个。合法选法的异或和是 $0, 1, 2, 4, 5$，最大是 5；插进线性基求最大，会得到 $1 \oplus 2 \oplus 4 = 7$，可 7 要三个数全选，违反限制。错在把合法值之间的异或也当成了能取到的值。
   - **先确认集合封闭，再用线性基**：任选子集、一条路径加任意环这类可以用；带选取限制的，先想办法把限制拆掉，拆不掉就换搜索或 DP。

## 2. 线性基能做什么

**线性基能回答“任选子集异或”的五类问题：能不能异或出来、有几个、最大最小、排第几、合并。** 下文 $n$ 是插入过的数的个数，$r$ 是秩。

1. **判断一个数能不能异或出来**
   - **对它走一遍插入的消元，最后剩 0 就能**：`contains`，$O(60)$。插入也是 $O(60)$，$n$ 个数全插完 $O(60 n)$。见 2.1。
2. **数个数**
   - **只用到秩**：不同的值有 $2^r$ 种（含 0）；异或和等于 $t$ 的子集，$t$ 能异或出来时有 $2^{n-r}$ 个，否则 0 个；异或和为 0 的非空子集有 $2^{n-r} - 1$ 个。见 2.2。
3. **求 $s$ 异或上任意子集的最大、最小值**
   - **从高位往低位贪心**：这一位能变成 1 就异或上对应的基（`max_xor`），最小值反过来（`min_xor`），都是 $O(60)$。见 2.3。
4. **求第 $k$ 小，或者一个值排第几**
   - **先规范化，再按 $k$ 的二进制位选基**：插完调一次 `reduce()`，$O(60^2)$；或者插入时就用 `insert_reduced` 保持规范，每次 $O(60)$。之后 `kth`、`index` 每次 $O(60)$。见 2.4、2.5。
5. **合并两组基**
   - **把一组的数逐个插进另一组**：`merge`，$O(60^2)$。放在线段树、倍增表的节点上，就能拼出区间、树上路径的基。见 2.6。

段的异或、带权、只许用区间里的数，这三种变形在第 3 节。全部函数合在一起的板子在文末附录。

### 2.1 插入和判断能否异或出来

**插入和判断都是从高位往低位消一遍，原理见 1.2。**

#### 复杂度

`insert` 和 `contains` 都是 $O(60)$：从第 59 位往下，每位最多异或一次。$n$ 个数全插完是 $O(60 n)$。

```cpp
struct XorBasis {
    static const int B = 60;          // 值都小于 2^60（10^18 < 2^60）
    long long b[B] = {};              // b[i]：最高位恰好是 i 的那个数，没有就是 0
    int r = 0;                        // 秩

    bool insert(long long x) {        // 插入成功（秩加 1）返回 true
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; r++; return true; }
            x ^= b[i];
        }
        return false;                 // x 被消成 0：它已经能被异或出来
    }

    bool contains(long long x) const {
        for (int i = B - 1; i >= 0; i--)
            if (x >> i & 1) {
                if (!b[i]) return false;
                x ^= b[i];
            }
        return true;
    }
};
```

- **`insert` 返回是否插入成功**：成功说明秩加 1；返回 `false` 说明 $x$ 已经能被异或出来，基不变。
- **`contains` 和 `insert` 走同一遍消元，只是不存**：碰到需要的位置空着，就说明消不掉，返回 `false`。

### 2.2 计数

**种类数只看秩，个数要先判断能不能异或出来，原理见 1.3。**

#### 复杂度

种类数和为 0 的子集数是 $O(1)$，只用到秩；等于 $t$ 的子集数要先 `contains(t)`，$O(60)$。

```cpp
// 插过 n 个数之后。n - r 可能很大，题目要取模时把 1LL << 换成快速幂
long long kinds(const XorBasis& lb) { return 1LL << lb.r; }               // 不同异或值的个数，含 0
long long ways(const XorBasis& lb, int n, long long t) {                  // 异或和等于 t 的子集个数，含空集
    return lb.contains(t) ? 1LL << (n - lb.r) : 0;
}
```

- **`kinds` 是 $2^r$**：包括空集给的 0。
- **`ways` 先判断 $t$ 能不能异或出来**：能就是 $2^{n-r}$，否则 0。异或和为 0 的非空子集是 `ways(lb, n, 0) - 1`，减掉空集。
- **$n - r$ 大时要取模**：题目要取模时，把 `1LL <<` 换成快速幂。

### 2.3 最大异或：从高位往低位贪心

**从高位往低位，这一位能变成 1 就异或上对应的基，最后得到的就是最大值。**

1. **为什么贪心对**
   - **比大小先比高位，而每一步都不影响已经定好的高位**：设当前结果为 $v$，从 $i = 59$ 往下，$v$ 的第 $i$ 位是 0 而 `b[i]` 非零，就异或上 `b[i]`。`b[i]` 的最高位是 $i$，不碰更高的位；后面用到的 `b[j]`（$j < i$）在第 $i$ 位都是 0，也不会把这一位改回去。
   - **写成代码是 `v = max(v, v ^ b[i])`**：第 $i$ 位是 0 时异或后变大，是 1 时变小。
2. **起点和最小值**
   - **起点可以不是 0**：“$s$ 异或上任意子集的最大值”从 $v = s$ 开始贪心，第 4 节的路径题就要用到。
   - **最小值反过来**：异或后变小就异或。

#### 复杂度

`max_xor` 和 `min_xor` 都是 $O(60)$，每一位看一次。

```cpp
    long long max_xor(long long v = 0) const {   // v 异或上任意子集的最大值
        for (int i = B - 1; i >= 0; i--) v = max(v, v ^ b[i]);
        return v;
    }
    long long min_xor(long long v) const {       // v 异或上任意子集的最小值
        for (int i = B - 1; i >= 0; i--) v = min(v, v ^ b[i]);
        return v;
    }
```

- **两个都是 `XorBasis` 的成员函数**：`b[i]` 为 0 时异或不改变 $v$，不用特判。
- **$s = 0$ 时最小值总是 0**：那是空集给的；题目要非空子集的最小值，见 2.5 末尾。

### 2.4 规范化

**从低位到高位，用更低的主元把每个数在别的主元位上的 1 消掉，作用见 1.4。也可以插入时就保持规范化，一直不用补。**

#### 复杂度

`reduce()` 是 $O(60^2)$：两重循环，各至多 60 次。`insert_reduced` 每插一个数 $O(60)$，和 `insert` 同阶。

```cpp
    void reduce() {                              // 规范化：主元位只留在自己那个数里
        for (int i = 0; i < B; i++)
            for (int j = i - 1; j >= 0; j--)
                if (b[j] && (b[i] >> j & 1)) b[i] ^= b[j];
    }
```

- **`i` 从小到大处理**：轮到 `b[i]` 时，更低的 `b[j]` 都已经规范好，除了第 $j$ 位不含别的主元位，异或它只会清掉 `b[i]` 的第 $j$ 位，不会把别的主元位翻回 1。
- **规范化后还是同一个空间的基**：异或上基里的数不改变张成的空间，也不改变 `b[i]` 的最高位，仍满足 1.2 的规定。

插入时就保持规范化，要在 `insert` 上补两步：

```cpp
    bool insert_reduced(long long x) {           // 插之前要是规范的，插完仍是规范的；成功返回 true
        for (int i = B - 1; i >= 0; i--)
            if ((x >> i & 1) && b[i]) x ^= b[i]; // 消掉 x 上所有已有的主元位，一直消到第 0 位
        if (!x) return false;                    // 消成 0：已经能被异或出来
        int t = 63 - __builtin_clzll(x);         // 剩下的最高位是新主元位
        for (int i = t + 1; i < B; i++)
            if (b[i] >> t & 1) b[i] ^= x;        // 更高的基里第 t 位清成 0
        b[t] = x;
        r++;
        return true;
    }
```

- **第一步把 $x$ 消到底**：`insert` 碰到第一个空位就停，$x$ 更低的主元位上可能还有 1；这里一直消到第 0 位。基是规范的，异或 `b[i]` 在主元位里只翻第 $i$ 位，所以消完 $x$ 在所有主元位上都是 0，剩下的最高位 $t$ 一定是新主元位。
- **第二步清掉旧基的第 $t$ 位**：更高的基第 $t$ 位是 1 的，异或上 $x$。$x$ 在别的主元位上都是 0，不会把它们翻回 1；更低的基最高位比 $t$ 低，第 $t$ 位本来就是 0。
- **前提是插之前已经规范**：一直只用 `insert_reduced` 插；或者先用 `insert` 插过一些，调一次 `reduce()` 再接着用。它就是增量高斯 `add`（附录）的线性基写法。
- **只在最后用一次规范化的基，用 `insert` 加一次 `reduce()`；插入过程中每插一个就要用，用 `insert_reduced`**：比如 5.1 每插一个数就要哈希一次规范化的基，每次都 `reduce()` 是 $O(60^2)$，`insert_reduced` 只要 $O(60)$。

### 2.5 第 $k$ 小和求排名

**原数组的子集能异或出 $2^r$ 个不同的值（含空集给的 0），把它们从小到大排好：规范化之后，第 $k$ 个（$k$ 从 0 数）就是按 $k$ 的二进制位选基；反过来，读出一个值在主元位上的比特就是它的排名。原理见 1.4。**

#### 复杂度

`kth` 和 `index` 都是 $O(60)$；前面的 `reduce()` 只需要做一次，$O(60^2)$，一直用 `insert_reduced` 插的就不用做。

```cpp
    long long kth(unsigned long long k) const {  // 基要是规范的；k 从 0 数，第 0 个是 0
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;                       // k ≥ 2^r：不存在
    }
    unsigned long long index(long long x) const {  // 基要是规范的；x 能被异或出来时，它是第几小（从 0 数）
        unsigned long long k = 0;
        for (int i = 0, t = 0; i < B; i++)
            if (b[i]) { if (x >> i & 1) k |= 1ULL << t; t++; }
        return k;
    }
```

- **`kth` 的 $k$ 从 0 数，第 0 个是 0**：$k \ge 2^r$ 时不存在，返回 $-1$。
- **`index` 是 `kth` 反过来**：一个能异或出来的值，在主元位上的比特拼起来就是它从 0 数的排名。

题面说“第 $k$ 小”，先分清它排的是去重后的值，还是全部子集的异或值（同一个值出现几次就排几次），两种的答案不一样。

1. **`kth` 排的是去重后的值**
   - **`kth` 数的是基的选法，不是原数组的子集，所以天然去重**：基的 $2^r$ 种选法和 $2^r$ 个不同的值一一对应（1.3），每个值只对应一种选法，也就只排一次；插入失败的数不参与选，它们带来的重复根本不会出现。
   - **例子**：$a = \{6, 3, 5\}$，基是 6 和 3，$r = 2$。8 个子集的异或值是 0、6、3、5、5、3、6、0，去重后从小到大是 0、3、5、6，就是 `kth(0)` 到 `kth(3)`。
2. **题目要去重：直接用 `kth`，只差 0 算不算**
   - **题面 $k$ 从 1 数，只算非空子集时，$r$ 是否等于 $n$ 决定 0 算不算**：$r < n$ 时有插入失败的数，它和表示它的那些基一起选就异或出 0，所以 0 算，答案是 `kth(k - 1)`；$r = n$ 时 0 只能由空集得到，要跳过，答案是 `kth(k)`。这是这类题最常错的地方。
   - **例子**：$\{6, 3, 5\}$ 里 $r = 2 < 3$，$6 \oplus 3 \oplus 5 = 0$，第 1 小是 `kth(0)` = 0，第 2 小是 `kth(1)` = 3；换成 $\{6, 3\}$，$r = n = 2$，0 只有空集给得出，第 1 小是 `kth(1)` = 3。
3. **题目不去重：每个值连着排 $2^{n-r}$ 遍**
   - **全部 $2^n$ 个子集的异或值排好序，是 $2^r$ 个不同值各重复 $2^{n-r}$ 遍（1.3）**：第 $k$ 个（$k$ 从 1 数）落在从 0 数的第 $\lfloor (k - 1) / 2^{n-r} \rfloor$ 段，答案是 `kth((k - 1) >> (n - r))`。不算空集时，少掉的是排在最前的一个 0，把 $k$ 换成 $k + 1$ 再套。
   - **例子**：$\{6, 3, 5\}$ 排好是 0、0、3、3、5、5、6、6，每个值 $2^{3-2} = 2$ 遍；第 5 个是 `kth(4 >> 1)` = `kth(2)` = 5。
4. **非空子集的最小值**
   - **$r < n$ 时是 0，否则是 `kth(1)`**：也就是规范化后主元位最低的那个基。

### 2.6 合并两组基

**把一组的非零数逐个插进另一组，就得到两组数合在一起的基。**

#### 复杂度

`merge` 是 $O(60^2)$：另一组至多 60 个非零数，每个插入 $O(60)$。

```cpp
    void merge(const XorBasis& o) {              // 把另一组基并进来，O(60^2)；之后要第 k 小得重新 reduce()
        for (int i = 0; i < B; i++)
            if (o.b[i]) insert(o.b[i]);
    }
```

- **放在线段树、倍增表的节点上，能拼出任意区间、树上路径的基**：线段树上一次区间询问合并 $O(\log n)$ 个节点，$O(60^2 \log n)$。
- **线性基不支持删除**：要删的题，离线成“每个数在哪段时间里存在”，再做线段树分治。

## 3. 三种常见变形

**第 2 节的问题是“给一堆数，任选子集”。比赛题常在上面改一处：插进基的数要先算出来、每个数带权、或者只许用一个区间里的数。下面三小节各讲一种。**

1. **插进基的不是原数，而是一段的异或（3.1）**
   - **先换成前缀异或再插**：一段的异或是两个前缀异或的异或，所以“这些段线性无关”等价于“对应的前缀异或线性无关”。
   - **例子**：CF 1101G，把数组切成尽量多段，任选几段异或起来都不为 0。
2. **每个数带一个权，要挑一组线性无关的数让权和最大（3.2）**
   - **按权从大到小插，插进去的就选上**：和最小生成树的 Kruskal 是同一个贪心。
   - **例子**：洛谷 P4570 元素，每块矿石有编号和魔力，选出的编号不能异或出 0，求魔力和最大。
3. **只许用区间 $[l, r]$ 里的数，有很多次询问（3.3）**
   - **每个主元位留位置最靠右的数，询问时只用位置 $\ge l$ 的基**：这是 3.2 的贪心把权换成位置，叫前缀线性基。
   - **例子**：CF 1100F，多次询问区间里任选子集的最大异或。

### 3.1 插进基的数是一段的异或：CF 1101G

[CF 1101G (Zero XOR Subset)-less](https://codeforces.com/problemset/problem/1101/G)，时限 2 秒

1. **题面**

   给一个数组 $a_1, \dots, a_n$，把它切成尽量多的段：每个元素恰好在一段里，每段至少一个元素，并且不存在若干段（至少一段），把它们里面的数全部异或起来等于 0。输出最多能切成几段；没有合法的切法输出 $-1$。

   - **输入**：第一行 $n$（$1 \le n \le 2 \cdot 10^5$），第二行 $n$ 个整数 $a_i$（$0 \le a_i \le 10^9$）。
   - **输出**：最多的段数，或者 $-1$。

   **样例 1 输入**

   ```text
   4
   5 5 7 2
   ```

   **样例 1 输出**

   ```text
   2
   ```

   **样例 2 输入**

   ```text
   3
   1 2 3
   ```

   **样例 2 输出**

   ```text
   -1
   ```

   **样例 3 输入**

   ```text
   3
   3 1 10
   ```

   **样例 3 输出**

   ```text
   3
   ```

   题面的样例说明：样例 1 切成 $[5, 5, 7], [2]$ 合法；切成 3 段都不行，比如 $[5], [5, 7], [2]$ 里，$[5, 7]$ 和 $[2]$ 异或起来是 0。样例 2 没有合法的切法。样例 3 每个数单独一段。
2. **思路**
   1. **一段的异或写成两个前缀异或的异或**：设 $S_i = a_1 \oplus \cdots \oplus a_i$，$S_0 = 0$，切点是 $0 = c_0 < c_1 < \cdots < c_k = n$，那么第 $j$ 段的异或是 $S_{c_j} \oplus S_{c_{j-1}}$。“不存在若干段异或为 0”就是这 $k$ 个段值线性无关。
   2. **段值线性无关，等价于切点处的前缀异或 $S_{c_1}, \dots, S_{c_k}$ 线性无关**：段值是相邻两个 $S$ 的异或，反过来 $S_{c_j}$ 是前 $j$ 段的异或。两组各 $k$ 个数互相能表示，张成同一个空间，所以一组线性无关，另一组也线性无关。问题就变成：从 $S_1, \dots, S_n$ 里挑尽量多个线性无关的，并且必须挑 $S_n$（最后一个切点总是 $n$）。
   3. **答案是 $S_1, \dots, S_n$ 的秩，$S_n = 0$ 时无解**：$S_n = 0$ 时它自己就异或出 0，输出 $-1$。否则先插 $S_n$，再插其余的前缀异或，得到一组包含 $S_n$ 的基，大小就是秩 $r$；任何合法切法的 $k$ 个 $S$ 线性无关，$k \le r$。所以把所有前缀异或插进线性基，答案就是秩。

      比如样例 1 的前缀异或是 $5, 0, 7, 5$，秩是 2，挑 $S_3 = 7$ 和 $S_4 = 5$，对应切法 $[5, 5, 7], [2]$。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // 附录的 XorBasis：这里只列用到的成员，实现照抄附录
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]：最高位恰好是 i 的那个数，没有就是 0
       int r = 0;                              // 秩
       bool insert(long long x);               // 插入成功（秩加 1）返回 true
   };

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int n;
       cin >> n;
       XorBasis lb;
       long long s = 0;                         // 前缀异或 S_i
       for (int i = 0; i < n; i++) {
           long long a;
           cin >> a;
           s ^= a;
           lb.insert(s);
       }
       cout << (s == 0 ? -1 : lb.r) << '\n';    // S_n = 0 无解，否则是前缀异或的秩
   }
   ```

3. **复杂度和坑**
   - **复杂度**：$n$ 次插入，$O(60 n)$。
   - **先判 $S_n = 0$**：哪怕别的前缀异或的秩很大，$S_n = 0$ 也是无解，因为所有段合起来异或就是 0。

### 3.2 每个数带权，按权从大到小插：洛谷 P4570

[洛谷 P4570 [BJWC2011] 元素](https://www.luogu.com.cn/problem/P4570)，时限 1 秒

1. **题面**

   有 $N$ 种矿石，第 $i$ 种有元素序号 $\mathit{Number}_i$ 和魔力值 $\mathit{Magic}_i$。从中选一些矿石炼一根法杖，每种最多用一块。如果选中的矿石里存在一个非空子集，它们的元素序号异或起来为 0，就会发生“魔法抵消”，炼不出法杖。法杖的魔力是选中矿石的魔力值之和，求能炼出的法杖的最大魔力。

   - **输入**：第一行 $N$（$1 \le N \le 1000$），接下来 $N$ 行每行两个正整数 $\mathit{Number}_i$、$\mathit{Magic}_i$（$1 \le \mathit{Number}_i \le 10^{18}$，$1 \le \mathit{Magic}_i \le 10^4$）。
   - **输出**：一个整数，最大魔力值。

   **样例 1 输入**

   ```text
   3
   1 10
   2 20
   3 30
   ```

   **样例 1 输出**

   ```text
   50
   ```

   题面的样例说明：三种都用时 $1 \oplus 2 \oplus 3 = 0$，会发生魔法抵消；最优是选后两种，$20 + 30 = 50$。
2. **思路**
   1. **不会魔法抵消，就是选出的元素序号线性无关**：“没有非空子集异或为 0”正是线性无关的定义（1.1）。问题变成：从 $N$ 个数里挑一组线性无关的，让它们的权（魔力值）之和最大。
   2. **按权从大到小插进线性基，插入成功的就选上**：插入成功说明它和已经选上的数线性无关，选出的始终是一组线性无关的数。比如样例按魔力 30、20、10 依次插 3、2、1：3 和 2 成功，1 = 3 ⊕ 2 失败，答案 $30 + 20 = 50$。
   3. **贪心选出的第 $t$ 个，不比任何一组线性无关的数的第 $t$ 个轻**：两组都按权从大到小排，贪心的是 $g_1, \dots, g_r$，任取的一组是 $o_1, \dots, o_m$，$m \le r$。假如 $w(o_t) > w(g_t)$：$o_1, \dots, o_t$ 线性无关，张成 $t$ 维，而 $g_1, \dots, g_{t-1}$ 只张成 $t - 1$ 维，所以有某个 $o_j$（$j \le t$）不能被 $g_1, \dots, g_{t-1}$ 表示。它比 $g_t$ 重，贪心在插 $g_t$ 之前处理过它，那时基里只有比它重的 $g$，插它应该成功，矛盾。逐项都不轻，加起来就是最大。3.3 会再用这个结论，把权换成位置。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // 附录的 XorBasis：这里只列用到的成员，实现照抄附录
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]：最高位恰好是 i 的那个数，没有就是 0
       int r = 0;                              // 秩
       bool insert(long long x);               // 插入成功（秩加 1）返回 true
   };

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int n;
       cin >> n;
       vector<pair<long long, long long>> items(n);   // (元素序号, 魔力值)
       for (auto& [x, w] : items) cin >> x >> w;
       sort(items.begin(), items.end(),
            [](const auto& p, const auto& q) { return p.second > q.second; });
       XorBasis lb;
       long long sum = 0;
       for (auto [x, w] : items)
           if (lb.insert(x)) sum += w;                // 插入成功：和已选的线性无关
       cout << sum << '\n';
   }
   ```

3. **复杂度和坑**
   - **复杂度**：排序 $O(N \log N)$，插入 $O(60 N)$。
   - **要先按权排序再插**：按输入顺序插，样例会先插进 1 和 2，3 插入失败，只得到 $10 + 20 = 30$。
   - **元素序号到 $10^{18}$**：用 `long long`，$10^{18} < 2^{60}$，附录的线性基开 60 位够用。

### 3.3 只许用区间里的数：前缀线性基，每个主元位留最靠右的

**从左往右插入，每个主元位留位置最靠右的数；询问 $[l, r]$ 时只用位置 $\ge l$ 的那部分基。**

1. **例：CF 1100F**
   - **题意**：一个数组，多次询问区间 $[l, r]$ 里任选子集的最大异或。每次询问重建一遍基要 $O(60 \cdot \text{区间长})$，太慢。
   - **和 3.1 的区别**：3.1 插进基的数本身是一段的异或；这里插的还是单个 $a_i$，区间限制的是哪些数能用。
2. **做法：交换插入，这叫前缀线性基**
   - **`b[i]` 旁边多记一个位置 `pos[i]`**：插入第 $p$ 个数时，碰到的 `b[i]` 位置比 $p$ 小就交换，新来的留在 `b[i]`，旧的带着它的位置继续往低位消。
   - **插完第 $r$ 个数，回答右端点为 $r$ 的询问**：只用 `pos[i]` $\ge l$ 的那些 `b[i]` 贪心；询问按 $r$ 离线排序，只维护一份基。

#### 复杂度

插入和每次询问都是 $O(60)$；询问按 $r$ 离线排序，总共 $O(q \log q + 60 (n + q))$。

```cpp
struct PrefixBasis {
    static const int B = 60;
    long long b[B] = {};
    int pos[B] = {};                   // b[i] 记着的位置（从 1 数），越靠右越好

    void insert(long long x, int p) {
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; pos[i] = p; return; }
            if (pos[i] < p) { swap(b[i], x); swap(pos[i], p); }
            x ^= b[i];
        }
    }

    long long max_xor(int l) const {   // 只用位置 >= l 的基：区间 [l, 当前右端点]
        long long v = 0;
        for (int i = B - 1; i >= 0; i--)
            if (pos[i] >= l) v = max(v, v ^ b[i]);
        return v;
    }
};
```

- **只用位置 $\ge l$ 的基就对，因为这是 3.2 的贪心，权值取位置**：按位置从大到小插 $a_r, a_{r-1}, \dots$，插完 $a_l$ 时基已经能表示 $a_l, \dots, a_r$；再往左插的数只填还空着的维度，所以位置 $\ge l$ 的部分正好张成 $a_l, \dots, a_r$。
- **交换插入是在线维护这个贪心**：新来的数位置最大，应该最先被选；被挤到消成 0 的，是一组线性相关的数里最靠左的那个。
- **例子**：下图是数组 $5, 6, 3, 4$ 依次插入时每一步的基，以及右端点为 4 时的询问 $[3, 4]$。

<a href="/images/algo/xor-basis-prefix.zh.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-prefix.zh.svg" alt="区间线性基：数组 101、110、011、100。插完 a1：b[2]=101@1。插完 a2：110@2 换下 101@1，101 往下消成 011 存进 b[1]。插完 a3：011@3 换下 011@1，旧的消成 0 丢掉。插完 a4：100@4 进 b[2]，110@2 被挤下去，消成 001 存进 b[0]。询问 [3,4] 只用位置不小于 3 的 100@4 和 011@3，最大异或 111=7。" style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

## 4. 例题：最大 XOR 和路径

[洛谷 P4151](https://www.luogu.com.cn/problem/P4151)，WC2011，时限 1 秒

1. **题面**

   边权为非负整数的无向连通图，节点编号 1 到 $N$。求一条从 1 号点到 $N$ 号点的路径，使路径上边权的异或和最大。路径可以重复经过点和边，一条边出现几次，它的权值就异或几次。

   - **输入**：第一行 $N, M$，点数和边数。接下来 $M$ 行，每行 $S_i, T_i, D_i$，表示 $S_i$ 和 $T_i$ 之间有一条权值为 $D_i$ 的无向边。可能有重边或自环。$N \le 50000$，$M \le 100000$，$D_i \le 10^{18}$。
   - **输出**：一个整数，最大的异或和。

   **输入**

   ```text
   5 7
   1 2 2
   1 3 2
   2 4 1
   2 5 1
   4 5 3
   5 3 4
   4 3 2
   ```

   **输出**

   ```text
   6
   ```

   题面的样例说明：路径 $1 \to 2 \to 4 \to 3 \to 5 \to 2 \to 4 \to 5$ 的异或和是 $2 \oplus 1 \oplus 2 \oplus 4 \oplus 1 \oplus 1 \oplus 3 = 6$；边数更少的路径 $1 \to 3 \to 5$ 也是 $2 \oplus 4 = 6$。
2. **思路**
   1. **所有路径的异或值，是一条固定路径 $P$ 异或上任意一个回路**：

      $$\{\text{所有 1 到 } N \text{ 路径的异或值}\} = \{\, P \oplus C \mid C \text{ 是回路的异或值} \,\}$$

      路径可以走回头路，一条边走两次等于没走：沿 $P$ 去、沿另一条路径 $Q$ 原路回，是一条回路 $C$，所以 $Q$ 的异或值是 $P \oplus C$。反过来，从 1 走到 $C$ 上绕一圈、原路回到 1，再走 $P$，来回的那段抵消，得到 $P \oplus C$。
   2. **回路的异或值是一个空间，所以答案是 `max_xor(P)`**：两条回路接起来还是回路，中间来回的一段抵消，所以回路的异或值对异或封闭（1.5），能用线性基，答案就是从 $P$ 出发的最大异或（2.3）。剩下的是求回路空间的一组基。
   3. **回路空间的基：做一棵生成树，每条边插一个 $d_u \oplus d_v \oplus w$**：$d_u$ 是从 1 沿树边走到 $u$ 的异或和，从 1 做一遍 BFS 得到。回路上的每一步 $u \to v$（边权 $w$）都拆成

      $$w = d_u \oplus d_v \oplus \underbrace{(d_u \oplus d_v \oplus w)}_{\text{树边上是 } 0}$$

      沿回路把每一步写开再全部异或，$d$ 的部分首尾相接、两两抵消，只剩括号里那项；反过来，每个 $d_u \oplus d_v \oplus w$ 本身就是一个回路。所以把每条边的这一项插进线性基，就得到回路空间的基。$P$ 取树上的路径，就是 $d_N$。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // 附录的 XorBasis：这里只列用到的成员，实现照抄附录
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]：最高位恰好是 i 的那个数，没有就是 0
       int r = 0;                              // 秩
       bool insert(long long x);               // 插入成功（秩加 1）返回 true
       long long max_xor(long long v = 0) const;   // v 异或上任意子集的最大值
   };

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int n, m;
       cin >> n >> m;
       vector<int> eu(m), ev(m);
       vector<long long> ew(m);
       vector<vector<pair<int, long long>>> g(n + 1);
       for (int i = 0; i < m; i++) {
           cin >> eu[i] >> ev[i] >> ew[i];
           g[eu[i]].push_back({ev[i], ew[i]});
           g[ev[i]].push_back({eu[i], ew[i]});
       }
       vector<long long> d(n + 1, -1);       // 从 1 沿生成树到 u 的异或和，-1 表示还没到过
       d[1] = 0;
       queue<int> q;
       q.push(1);
       while (!q.empty()) {
           int u = q.front();
           q.pop();
           for (auto [v, w] : g[u])
               if (d[v] < 0) { d[v] = d[u] ^ w; q.push(v); }
       }
       XorBasis lb;
       for (int i = 0; i < m; i++) lb.insert(d[eu[i]] ^ d[ev[i]] ^ ew[i]);   // 树边插进去是 0
       cout << lb.max_xor(d[n]) << '\n';
   }
   ```

3. **复杂度和坑**
   - **复杂度**：BFS $O(n + m)$，每条边插一次 $O(60)$，总共 $O((n + m) \cdot 60)$。
   - **树边、自环、重边都不用特判**：树边插进去是 0，自环和重边插进去就是它们自己的环。
   - **小边权下有现成的暴力**：边权都小于 16 时，状态“当前在哪个点、当前异或值是多少”只有 $16 n$ 种，从 $(1, 0)$ 出发 BFS，落在点 $N$ 上的异或值取最大，可以拿来和程序对拍。

## 5. 两道近年的赛题

### 5.1 CCPC Final 2025 L（Spirited Away）：数不同的区间张成空间

[QOJ / Universal Cup 3727 L](https://contest.ucup.ac/contest/3727/problem/18012)，时限 4 秒

1. **题面**

   给一个非负整数序列 $a_1, \dots, a_n$。对区间 $[l, r]$，从 $a_l, \dots, a_r$ 里任选若干个异或起来（可以一个都不选，结果是 0），所有可能的结果组成集合 $B(l, r)$。对所有 $1 \le l \le r \le n$，问一共有多少个不同的集合 $B(l, r)$。

   - **输入**：第一行 $T$，表示数据组数。每组第一行 $n$（$1 \le n \le 10^5$），第二行 $n$ 个整数 $a_i$（$0 \le a_i < 2^{32}$）。所有组的 $n$ 之和不超过 $10^5$。
   - **输出**：每组一行，不同集合 $B(l, r)$ 的个数。

   **输入**

   ```text {hl_lines=["2-3","6-7","10-11"]}
   5
   3
   1 2 3
   4
   10 12 17 33
   6
   1 0 9 8 7 3
   8
   9012 91829 9819 78 237 862 7672 2
   10
   0 1 2 4 8 16 32 64 128 256
   ```

   **输出**

   ```text {hl_lines=[1,3,5]}
   4
   10
   12
   36
   46
   ```

   第一组 $a = (1, 2, 3)$：$B(1, 1) = \{0, 1\}$，$B(2, 2) = \{0, 2\}$，$B(3, 3) = \{0, 3\}$，其余三个区间都是 $\{0, 1, 2, 3\}$，所以答案是 4。
2. **思路**
   1. **不同的区间只有 $O(32 n)$ 种**：固定右端点 $r$，左端点往左走，空间只会变大，每变一次维数加 1，所以至多变 32 次。变化点就是 3.3 前缀线性基里的位置：插完 $a_r$ 后把基按 `pos` 从大到小排成 $v_1, \dots, v_k$，位置 $p_1 > p_2 > \cdots > p_k$，记 $p_{k+1} = 0$，那么

      $$B(l, r) = \operatorname{span}(v_1, \dots, v_j), \qquad p_{j+1} < l \le p_j .$$

      这是 3.3 那句“位置 $\ge l$ 的部分正好张成 $a_l, \dots, a_r$”换了个说法。所以只要对每个 $r$ 枚举这至多 32 个空间。
   2. **两个空间相同，当且仅当规范化后的基相同**：空间里每个非零数的最高位都是主元位，所以主元位的集合由空间决定；规范化后主元位 $p$ 上的基，是空间里“主元位中只有第 $p$ 位是 1”的那个数，按 1.4 这样的数只有一个，也由空间决定。于是把规范化后的基哈希成一个 64 位数，数不同的哈希值就是数不同的空间。
   3. **一边插入一边保持规范化**：每插一个数就 `reduce()` 再整体哈希，每个右端点 $r$ 要 $O(32^3)$，太慢。改用 2.4 的 `insert_reduced`，插入时就保持规范化，每插一个数 $O(60)$。哈希取各个基打散之后的和，插完一个数重新加一遍，也是 $O(60)$。代码套附录的 `PrefixBasis` 求每个右端点的至多 32 个基，再把它们按位置从大到小插进一个新的 `XorBasis`。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   // 附录的 PrefixBasis（3.3）：这里只列用到的成员，实现照抄附录
   struct PrefixBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]：主元在第 i 位、位置最靠右的那个数
       int pos[B] = {};                        // b[i] 的位置（从 1 数）
       void insert(long long x, int p);        // 插入第 p 个数
   };

   // 附录的 XorBasis：同上
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]：最高位恰好是 i 的那个数，没有就是 0
       int r = 0;                              // 秩
       bool insert_reduced(long long x);       // 插入并保持规范化，插之前要是规范的
   };

   uint64_t mix(uint64_t x) {                    // splitmix64：把一个数打散成随机的 64 位
       x += 0x9e3779b97f4a7c15ULL;
       x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
       x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
       return x ^ (x >> 31);
   }

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       int T;
       cin >> T;
       while (T--) {
           int n;
           cin >> n;
           PrefixBasis pb;
           vector<uint64_t> hs;                  // 每个 (r, j) 对应空间的哈希
           for (int r = 1; r <= n; r++) {
               long long x;
               cin >> x;
               pb.insert(x, r);
               vector<pair<int, long long>> v;   // (位置, 基)，按位置从大到小
               for (int i = 0; i < PrefixBasis::B; i++)
                   if (pb.b[i]) v.push_back({pb.pos[i], pb.b[i]});
               sort(v.rbegin(), v.rend());
               if (v.empty() || v[0].first < r) hs.push_back(0);   // a_r = 0：B(r, r) = {0}
               XorBasis c;                       // 规范化的基，按位置从大到小一个一个插
               for (auto [q, y] : v) {
                   c.insert_reduced(y);
                   uint64_t h = 0;
                   for (int i = 0; i < XorBasis::B; i++)
                       if (c.b[i]) h += mix(c.b[i]);
                   hs.push_back(h);              // l 落在 (下一个位置, q] 时的 B(l, r)
               }
           }
           sort(hs.begin(), hs.end());
           cout << unique(hs.begin(), hs.end()) - hs.begin() << '\n';
       }
   }
   ```

3. **复杂度和坑**
   - **复杂度**：每插一个数 $O(60)$（插入和重算哈希都扫一遍 60 位），每个右端点至多插 32 个，总共 $O(60 \cdot 32 \cdot n)$，$n = 10^5$ 时约 $2 \times 10^8$ 次简单操作，时限 4 秒够用。
   - **$a_r = 0$ 时要单独算 $\{0\}$**：这时 $a_r$ 插不进去，$p_1 < r$，左端点在 $(p_1, r]$ 的区间给出 $\{0\}$，上面的式子没有覆盖。
   - **哈希碰撞可以忽略**：$O(32 n)$ 个 64 位哈希值里出现碰撞的概率约是 $(3 \times 10^6)^2 / 2^{65}$。

### 5.2 2026 ICPC 网络赛第二场 A（All Closed）：所有解都必须包含的数

[QOJ 20236](https://qoj.ac/contest/4113/problem/20236)，2026 ICPC 网络赛第二场 A，时限 1 秒

1. **题面**

   给 $n$ 个集合 $S_1, \dots, S_n$，每个集合里是互不相同的整数，都在 $[0, 2^m)$ 里。一次操作选一个整数 $x$（$0 \le x < 2^m$），把它加进每个集合（已经有的就不加）。集合 $S$ 叫异或封闭，是指对任意 $x, y \in S$ 都有 $x \oplus y \in S$。求让所有 $S_i$ 都异或封闭的最少操作次数，并给出一种做法。

   - **输入**：第一行 $n$（$1 \le n \le 2 \cdot 10^5$）和 $m$（$1 \le m \le 20$）；接下来第 $i$ 行先是 $c_i$（$c_i \ge 1$），再是 $c_i$ 个互不相同的整数 $a_{i,1}, \dots, a_{i,c_i}$（$0 \le a_{i,j} < 2^m$），表示 $S_i$；保证 $\sum c_i \le 10^6$。
   - **输出**：第一行最少操作次数 $k$，第二行 $k$ 个整数，依次是每次选的 $x$；有多种最优解时输出任意一种。

   **样例 1 输入**

   ```text
   3 3
   1 1
   3 0 1 7
   6 1 2 3 4 5 7
   ```

   **样例 1 输出**

   ```text
   3
   0 7 6
   ```

   **样例 2 输入**

   ```text
   1 4
   4 11 5 14 0
   ```

   **样例 2 输出**

   ```text
   0
   ```

   题面的样例说明：样例 1 操作之后 $S_1, S_2$ 变成 $\{0, 1, 6, 7\}$，$S_3$ 变成 $\{0, 1, \dots, 7\}$，少于 3 次做不到。样例 2 唯一的集合本来就封闭，不用操作。
2. **思路**
   1. **把“最少操作”换成“最小的空间”**：对异或封闭的非空集合包含 $a \oplus a = 0$，所以就是空间。设加进去的数组成集合 $T$，所有最终集合的公共部分

      $$K = \bigcap_{i} (S_i \cup T) = I \cup T, \qquad I = \bigcap_i S_i$$

      是若干个空间的交，也是空间，最终集合可以写成 $S_i \cup K$。$T$ 里不必放 $I$ 中的数，它们本来就在每个集合里，所以 $|T| = |K| - |I|$。于是操作最少就是求最小的空间 $K \supseteq I$，使每个 $S_i \cup K$ 都是空间，答案是 $K \setminus I$。
   2. **每一步加的数都是逼出来的**：从 $K = \operatorname{span}(I)$ 开始。某个 $S_i \cup K$ 不封闭时，取一个在 $\operatorname{span}(S_i \cup K)$ 里、却既不在 $S_i$ 也不在 $K$ 里的 $x$。任取一个包含当前 $K$ 的合法解 $K^*$，$S_i \cup K^*$ 是空间，又包含 $S_i \cup K$，所以包含 $x$；$x$ 不在 $S_i$ 里，只能在 $K^*$ 里。令 $K \leftarrow \operatorname{span}(K \cup \{x\})$，它仍被每个合法解包含，秩加 1。至多 $m$ 步后所有集合都封闭，这时 $K$ 合法，又被每个合法解包含，所以是最小解，答案也唯一。
   3. **判断封闭只要数元素个数**：$S_i \cup K$ 总在它张成的空间里，那个空间正好有 $2^r$ 个元素（1.3），$r$ 是 $S_i \cup K$ 的秩，个数相等就说明两者是同一个集合：

      $$S_i \cup K \text{ 封闭} \iff \lvert S_i \rvert + \lvert K \rvert - \lvert S_i \cap K \rvert = 2^r .$$

      不封闭时把 $\operatorname{span}(S_i \cup K)$ 列出来，至多 $2^m$ 个，找一个既不在 $S_i$ 也不在 $K$ 里的数，就是要加的 $x$。

   ```cpp
   #include <bits/stdc++.h>
   using namespace std;

   int n, m;

   // 附录的 XorBasis：这里只列用到的成员，实现照抄附录
   struct XorBasis {
       static const int B = 60;
       long long b[B] = {};                    // b[i]：最高位恰好是 i 的那个数，没有就是 0
       int r = 0;                              // 秩
       bool insert(long long x);               // 插入成功（秩加 1）返回 true
   };

   vector<int> expand(const XorBasis& lb) { // 列出 span(b) 的全部元素
       vector<int> all = {0};
       for (int i = 0; i < XorBasis::B; i++)
           if (lb.b[i]) {
               int sz = all.size();
               for (int j = 0; j < sz; j++) all.push_back(all[j] ^ lb.b[i]);
           }
       return all;
   }

   int main() {
       ios::sync_with_stdio(false);
       cin.tie(nullptr);
       cin >> n >> m;
       vector<vector<int>> s(n);
       vector<int> cnt(1 << m, 0);            // cnt[x]：x 在几个集合里
       for (auto& si : s) {
           int k;
           cin >> k;
           si.resize(k);
           for (int& x : si) { cin >> x; cnt[x]++; }
       }
       XorBasis kb;                           // K 的基，从 span(I) 开始
       for (int x = 0; x < (1 << m); x++)
           if (cnt[x] == n) kb.insert(x);
       vector<char> inK(1 << m), inS(1 << m);
       while (true) {
           vector<int> K = expand(kb);
           fill(inK.begin(), inK.end(), 0);
           for (int x : K) inK[x] = 1;
           int forced = -1;                   // 每个合法解都必须包含的新数
           for (int i = 0; i < n && forced < 0; i++) {
               XorBasis b = kb;
               int common = 0;                // |S_i ∩ K|
               for (int x : s[i]) { b.insert(x); common += inK[x]; }
               int r = b.r;
               long long uni = (long long)s[i].size() + K.size() - common;   // |S_i ∪ K|
               if (uni == (1LL << r)) continue;                              // 已经封闭
               for (int x : s[i]) inS[x] = 1;
               for (int x : expand(b))
                   if (!inK[x] && !inS[x]) { forced = x; break; }
               for (int x : s[i]) inS[x] = 0;
           }
           if (forced < 0) break;
           kb.insert(forced);
       }
       vector<int> ans;                       // K \ I
       for (int x : expand(kb))
           if (cnt[x] < n) ans.push_back(x);
       sort(ans.begin(), ans.end());
       cout << ans.size() << '\n';
       for (int x : ans) cout << x << ' ';
       cout << '\n';
   }
   ```

3. **复杂度和坑**
   - **复杂度**：至多 $m$ 轮，每轮检查所有集合是 $O(m \sum \lvert S_i \rvert)$，再加 $O(2^m)$ 的列举。
   - **求最小的合法解，从“每个合法解都必须包含什么”出发**：一直加必须包含的数，加到合法为止，停下时就是最小解。

## 练习

每题后面写的是用到哪一节。

**必做**

1. [洛谷 P3857 彩灯](https://www.luogu.com.cn/problem/P3857)：2.2。
2. [洛谷 P4570 元素](https://www.luogu.com.cn/problem/P4570)：3.2。
3. [LOJ 114 k 大异或和](https://loj.ac/p/114)：2.5，注意 0 算不算。
4. [洛谷 P4869 albus就是要第一个出场](https://www.luogu.com.cn/problem/P4869)：给值求排名，是 2.5 反过来，再乘上 1.3 的重复次数。
5. [CF 845G Shortest Path Problem?](https://codeforces.com/problemset/problem/845/G)：第 4 节，求最小值。
6. [CF 1100F Ivan and Burgers](https://codeforces.com/problemset/problem/1100/F)：3.3。

**选做**

7. [CF 959F Mahmoud and Ehab and yet another xor task](https://codeforces.com/problemset/problem/959/F)：前 $l$ 个数里异或和为 $x$ 的子集个数，2.2 加离线。
8. [洛谷 P3292 幸运数字](https://www.luogu.com.cn/problem/P3292)：树上路径的最大异或，2.6 加树上倍增。

## 和地图上其他格子的连接

- 1.2 的消元就是模 2 的高斯消元，插入是 [L2 高斯消元](/zh/algo/l2-gaussian-elimination/)第 6.1 节增量高斯的特例；异或方程组的解数（$2^{\text{自由元数}}$）和 1.3 的 $2^{n-r}$ 是同一个数：自由元就是插入失败的那些数。
- A6 的 01-Trie 也求最大异或，它求的是“$x$ 和集合里某一个数异或的最大值”，集合里的数只能选一个；线性基求的是任选子集。题面说“选两个数”用 Trie，说“选若干个数”用线性基。
- 3.2 的贪心是拟阵上的贪心，最小生成树的 Kruskal 是同一个结构（图的无环边集代替线性无关组）。

## 附：线性基和增量高斯的板子

两份板子放在一起对照。线性基是增量高斯在“列数不超过 60、没有右端”时的写法，所以每个操作基本都能在两边找到对应；右端、矛盾、解向量只有增量高斯有。两份都和暴力枚举对拍过。

**两份板子的区别**

| | 线性基 `XorBasis` | 增量高斯 `IncGauss` |
| --- | --- | --- |
| 一行是什么 | 一个数，没有右端 | 一条方程：系数 bitset + 右端 |
| 按什么存 | `b[i]` 就是主元在第 $i$ 位的那一行 | 每行记它的主元列 `piv` |
| 消成 0 时 | 插入失败，这个数能被异或出来 | 看右端：是 0 就能由已有方程推出（返回 0），非 0 就矛盾（返回 $-1$，`bad` 记下） |
| 列数 | 不超过 60 | 不超过 `MV`，几千也行 |

**操作和复杂度**

| 要做的事 | `XorBasis` | `IncGauss` | 线性基复杂度 | 增量高斯复杂度 |
| --- | --- | --- | --- | --- |
| 插入，不管规范化 | `insert` | 没有 | $O(60)$ | — |
| 插入，保持规范化 | `insert_reduced` | `add` | $O(60)$ | $O(r w)$ |
| 事后规范化 | `reduce()` | 不需要 | $O(60^2)$ | — |
| 能否表示出来 | `contains` | `implied`，还给出推出的右端 | $O(60)$ | $O(r w)$ |
| 秩 | `r` | `rank()` | $O(1)$ | $O(1)$ |
| 最大 / 最小异或 | `max_xor` / `min_xor` | `max_xor` / `min_xor` | $O(60)$ | $O(r w)$ |
| 第 $k$ 小 | `kth`，基要是规范的 | `kth` | $O(60)$ | $O(r \log r + r w)$ |
| 求排名 | `index`，基要是规范的 | `index` | $O(60)$ | $O(r \log r)$ |
| 合并 | `merge` | `merge` | $O(60^2)$ | $O(r' r w)$ |
| 一组解 | 没有 | `solve()` | — | $O(r + w)$ |
| 全部解 | 没有 | `kernel()` | — | $O((n - r)(r + w))$ |

**区间询问**

| 要做的事 | `PrefixBasis` | `PrefixGauss` | 线性基复杂度 | 增量高斯复杂度 |
| --- | --- | --- | --- | --- |
| 加入第 $p$ 个 | `insert` | `add` | $O(60)$ | $O(n w)$ |
| 区间最大异或 | `max_xor` | `max_xor` | $O(60)$ | $O(n w)$ |
| 区间能否推出 | 没有 | `implied` | — | $O(n w)$ |
| 区间是否矛盾 | 没有 | `bad` | — | $O(1)$ |
| 区间的秩 | 没有 | `rank` | — | $O(n)$ |
| 取出区间的基 | `at` | `at` | $O(60)$ | $O(n r w)$ |

复杂度里 $r$ 是当前的秩，$r'$ 是另一组的秩，$n$ 是未知数个数，$w = \text{MV} / 64$ 是一行 bitset 占的机器字数，一次 bitset 异或就是 $w$ 次整数异或。线性基一行就是一个字（$w = 1$），秩不超过 60：把增量高斯那列的 $w$ 换成 1、$r$ 换成 60，就是线性基那列。同一个操作两边同阶，差别只在列数能开多大。

所以“这个数能不能被异或出来”和“这条方程是不是多余的”是同一个问题；带上右端，就多了“矛盾”这一种结局。

### 线性基

```cpp
#include <bits/stdc++.h>
using namespace std;

// 线性基：值小于 2^60，b[i] 要么是 0，要么是最高位恰好为 i 的数
struct XorBasis {
    static const int B = 60;
    long long b[B] = {};
    int r = 0;                                   // 秩；能异或出 2^r 个值，插过 n 个数时每个值有 2^(n-r) 种选法

    bool insert(long long x) {                   // 成功（秩加 1）返回 true，失败说明 x 已能被异或出来
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; r++; return true; }
            x ^= b[i];
        }
        return false;
    }
    bool insert_reduced(long long x) {           // 插之前要是规范的，插完仍是规范的；成功返回 true
        for (int i = B - 1; i >= 0; i--)
            if ((x >> i & 1) && b[i]) x ^= b[i]; // 消掉 x 上所有已有的主元位，一直消到第 0 位
        if (!x) return false;                    // 消成 0：已经能被异或出来
        int t = 63 - __builtin_clzll(x);         // 剩下的最高位是新主元位
        for (int i = t + 1; i < B; i++)
            if (b[i] >> t & 1) b[i] ^= x;        // 更高的基里第 t 位清成 0
        b[t] = x;
        r++;
        return true;
    }
    bool contains(long long x) const {           // x 能否被异或出来
        for (int i = B - 1; i >= 0; i--)
            if (x >> i & 1) {
                if (!b[i]) return false;
                x ^= b[i];
            }
        return true;
    }
    long long max_xor(long long v = 0) const {   // v 异或上任意子集的最大值
        for (int i = B - 1; i >= 0; i--) v = max(v, v ^ b[i]);
        return v;
    }
    long long min_xor(long long v) const {       // v 异或上任意子集的最小值
        for (int i = B - 1; i >= 0; i--) v = min(v, v ^ b[i]);
        return v;
    }
    void reduce() {                              // 规范化：每个主元位只留在自己那个数里
        for (int i = 0; i < B; i++)
            for (int j = i - 1; j >= 0; j--)
                if (b[j] && (b[i] >> j & 1)) b[i] ^= b[j];
    }
    long long kth(unsigned long long k) const {  // 基要是规范的；第 k 小（k 从 0 数，第 0 个是 0），不存在返回 -1
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;
    }
    unsigned long long index(long long x) const {  // 基要是规范的；x 能被异或出来时，它是第几小（从 0 数）
        unsigned long long k = 0;
        for (int i = 0, t = 0; i < B; i++)
            if (b[i]) { if (x >> i & 1) k |= 1ULL << t; t++; }
        return k;
    }
    void merge(const XorBasis& o) {              // 把另一组基并进来，O(60^2)；之后要第 k 小得重新 reduce()
        for (int i = 0; i < B; i++)
            if (o.b[i]) insert(o.b[i]);
    }
};

// 前缀线性基（讲解见 3.3）：从左往右插，每个主元位留位置最靠右的数
struct PrefixBasis {
    static const int B = 60;
    long long b[B] = {};
    int pos[B] = {};                             // b[i] 的位置（从 1 数）

    void insert(long long x, int p) {            // 插入第 p 个数
        for (int i = B - 1; i >= 0; i--) {
            if (!(x >> i & 1)) continue;
            if (!b[i]) { b[i] = x; pos[i] = p; return; }
            if (pos[i] < p) { swap(b[i], x); swap(pos[i], p); }
            x ^= b[i];
        }
    }
    long long max_xor(int l) const {             // 区间 [l, 当前右端点] 的最大异或
        long long v = 0;
        for (int i = B - 1; i >= 0; i--)
            if (pos[i] >= l) v = max(v, v ^ b[i]);
        return v;
    }
    XorBasis at(int l) const {                   // 区间 [l, 当前右端点] 的一组基，可以接着用上面的全部操作
        XorBasis s;
        for (int i = 0; i < B; i++)
            if (b[i] && pos[i] >= l) s.b[i] = b[i], s.r++;
        return s;
    }
};
```

`kth` 的 $k$ 从 0 数，包含 0；题面的“第 $k$ 小”0 算不算，按 2.5 末尾看 $r$ 是否等于 $n$。

### 增量高斯（模 2）

解方程的几个函数和 [L2 第 6.1 节](/zh/algo/l2-gaussian-elimination/)的模板相同，实现直接写在结构体里，复杂度见附录开头的表；和线性基对应的操作（包括 `PrefixGauss::max_xor`）只在结构体里声明，实现放在后面。

```cpp
#include <bits/stdc++.h>
using namespace std;

const int MV = 1024;                             // MV = max variables，未知数个数的上限；bitset 的长度要在编译时定下，所以是常量

// 增量高斯（模 2）：一条一条加方程，始终保持简化行阶梯形
struct IncGauss {
    int n;                                       // 未知数个数
    vector<bitset<MV>> row;
    vector<int> rhs, piv;                        // 每行的右端、主元列；右端可以把若干位打包一起异或
    bool bad = false;                            // 出现过矛盾
    IncGauss(int n) : n(n) {}

    // 解方程
    void eliminate(bitset<MV>& v, int& b) const {        // 用已有各行把 v 在主元列上的 1 消掉，右端跟着变
        for (int i = 0; i < (int)row.size(); i++)
            if (v[piv[i]]) v ^= row[i], b ^= rhs[i];
    }
    int add(bitset<MV> v, int b) {               // 1：独立，秩加 1；0：能由已有方程推出；-1：矛盾
        eliminate(v, b);
        int p = v._Find_first();
        if (p >= n) { if (b) bad = true; return b ? -1 : 0; }
        for (int i = 0; i < (int)row.size(); i++)
            if (row[i][p]) row[i] ^= v, rhs[i] ^= b;  // 新主元列在旧行里清成 0
        row.push_back(v), rhs.push_back(b), piv.push_back(p);
        return 1;
    }
    int rank() const { return row.size(); }
    int implied(bitset<MV> v) const {            // 左边为 v 的方程能否推出：能就返回右端，不能返回 -1
        int b = 0;
        eliminate(v, b);
        return v.none() ? b : -1;
    }
    bitset<MV> solve() const {                   // !bad 时的一组解：自由元取 0，主元等于右端
        bitset<MV> x;
        for (int i = 0; i < (int)row.size(); i++) x[piv[i]] = rhs[i];
        return x;
    }
    vector<bitset<MV>> kernel() const {          // 齐次方程组解空间的基，n - rank() 个
        vector<int> isp(n, -1);
        for (int i = 0; i < (int)row.size(); i++) isp[piv[i]] = i;
        vector<bitset<MV>> ks;
        for (int f = 0; f < n; f++) {
            if (isp[f] >= 0) continue;
            bitset<MV> x;
            x[f] = 1;                            // 这个自由元取 1，其余自由元取 0
            for (int i = 0; i < (int)row.size(); i++)
                if (row[i][f]) x[piv[i]] = 1;
            ks.push_back(x);
        }
        return ks;
    }
    void merge(const IncGauss& o) {              // 把另一组的方程逐条加进来
        for (int i = 0; i < (int)o.row.size(); i++) add(o.row[i], o.rhs[i]);
    }

    // 和线性基对应的操作：只看左边（行空间），不管右端；比大小时第 0 列是最高位
    bitset<MV> max_xor(bitset<MV> v) const;      // v 异或上任意几行的最大值
    bitset<MV> min_xor(bitset<MV> v) const;      // v 异或上任意几行的最小值
    bitset<MV> kth(unsigned long long k) const;  // 行空间里第 k 小（从 0 数，第 0 个是全 0），要求 k < 2^rank()
    unsigned long long index(const bitset<MV>& x) const;        // x 在行空间里时，它是第几小（从 0 数）
    vector<int> low_to_high() const;             // 行号按主元从低位到高位排（主元列从大到小）
};

// 前缀增量高斯（模 2）：方程从左往右加，每个主元列留位置最靠右的那条；右端当作第 n 列一起消
struct PrefixGauss {
    int n;
    vector<bitset<MV>> row;                      // row[c]：第一个 1 在第 c 列的方程，c = n 那行是 0 = 1
    vector<int> pos;                             // row[c] 的位置（从 1 数），0 表示空
    PrefixGauss(int n) : n(n), row(n + 1), pos(n + 1, 0) {}

    void add(bitset<MV> v, int b, int p) {       // 加入第 p 条方程，要求 MV > n
        v[n] = b;
        while (v.any()) {
            int c = v._Find_first();
            if (!pos[c]) { row[c] = v; pos[c] = p; return; }
            if (pos[c] < p) { swap(row[c], v); swap(pos[c], p); }
            v ^= row[c];
        }
    }
    bool bad(int l) const { return pos[n] >= l; }  // 第 l 条到当前这条方程是否矛盾（l 从 1 数）
    int rank(int l) const {                      // 第 l 条到当前这条方程的秩
        int r = 0;
        for (int c = 0; c < n; c++) r += pos[c] >= l;
        return r;
    }
    int implied(bitset<MV> v, int l) const {     // 只用第 l 条到当前这条：能推出就返回右端，不能返回 -1
        v[n] = 0;
        for (int c = v._Find_first(); c < n; c = v._Find_next(c)) {
            if (pos[c] < l) return -1;
            v ^= row[c];
        }
        return v[n];
    }
    bitset<MV> max_xor(bitset<MV> v, int l) const;              // 只用第 l 条到当前这条的左边，v 异或上它们的最大值
    IncGauss at(int l) const {                   // 第 l 条到当前这条方程，交给 IncGauss
        IncGauss g(n);
        for (int c = 0; c <= n; c++)
            if (pos[c] >= l) {
                bitset<MV> w = row[c];
                int b = w[n];
                w[n] = 0;
                g.add(w, b);
            }
        return g;
    }
};
```

第 $j$ 个未知数对应 bitset 的第 $j$ 位。`bad` 为真时方程组无解，`solve()` 和 `kernel()` 没有意义；否则解有 $2^{n - \text{rank}}$ 个，就是 [L1 线性代数](/zh/algo/l1-linear-algebra/) 4.5 节的图景：全部解是零空间整体平移一个解。

和线性基对应的那几个函数只看左边，把每一行当成一个 $n$ 位的数，**第 0 列是最高位**。主元是一行里最靠前的 1，所以“主元越靠前，数越大”，和线性基里“最高位越高，数越大”是同一回事。要和整数对上，就把整数 $x$ 的第 $W - 1 - j$ 位放进第 $j$ 列（$W$ 是位数）。简化行阶梯形一直保持着，所以 `kth` 前面不用 `reduce()`。

`PrefixGauss` 就是 3.3 的交换插入，只是一行换成 bitset、主元取最靠前的那个 1；右端当作第 $n$ 列一起消，消出来的 `0 = 1` 那行留的是最靠右的位置 $q$，第 $l$ 条到当前这条矛盾当且仅当 $l \le q$，所以 `bad(l)` 比一下就行。它只保持行阶梯形，不清旧行，所以 `max_xor` 要按列从前往后贪心。

#### 实现：和线性基对应的操作

```cpp
// 简化行阶梯形里每个主元列只有自己那行是 1，所以结果在主元列上的值就是“那行选没选”，
// 而两种选法的结果第一次不同一定落在某个主元列上：贪心只要决定每个主元列是 0 还是 1
bitset<MV> IncGauss::max_xor(bitset<MV> v) const {
    for (int i = 0; i < (int)row.size(); i++)
        if (!v[piv[i]]) v ^= row[i];
    return v;
}

bitset<MV> IncGauss::min_xor(bitset<MV> v) const {
    for (int i = 0; i < (int)row.size(); i++)
        if (v[piv[i]]) v ^= row[i];
    return v;
}

vector<int> IncGauss::low_to_high() const {
    vector<int> id(row.size());
    iota(id.begin(), id.end(), 0);
    sort(id.begin(), id.end(), [&](int a, int b) { return piv[a] > piv[b]; });
    return id;
}

bitset<MV> IncGauss::kth(unsigned long long k) const {        // k 的第 t 位：选不选从低位数第 t 个主元的那行
    bitset<MV> v;
    vector<int> id = low_to_high();
    for (int t = 0; t < (int)id.size() && t < 64; t++)
        if (k >> t & 1) v ^= row[id[t]];
    return v;
}

unsigned long long IncGauss::index(const bitset<MV>& x) const {
    unsigned long long k = 0;
    vector<int> id = low_to_high();
    for (int t = 0; t < (int)id.size() && t < 64; t++)
        if (x[piv[id[t]]]) k |= 1ULL << t;
    return k;
}

bitset<MV> PrefixGauss::max_xor(bitset<MV> v, int l) const {              // 行阶梯形：row[c] 只改第 c 列及以后，从高位往低位贪心
    for (int c = 0; c < n; c++)
        if (pos[c] >= l && !v[c]) v ^= row[c];
    v[n] = 0;                                    // 第 n 列是右端，不算
    return v;
}
```

**选哪份：题目问一组数的子集异或能得到什么，用线性基；题目要解方程、判矛盾，或者未知数超过 60 个，用增量高斯。**
