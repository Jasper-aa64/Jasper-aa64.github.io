---
title: "L3：线性基"
date: 2026-11-02
slug: "l3-xor-basis"
aliases: ["/algo/l2-xor-basis/"]
description: "异或是 GF(2) 上的加法，任选子集的异或和构成一个线性空间，线性基是它的一组至多 60 个数的基：按最高位插入、2^r 种值每种由 2^(n-r) 个子集得到、最大值贪心、规范化后第 k 小；前缀异或、带权贪心、区间询问留最靠右的数；从 0 写完最大 XOR 和路径；两道近年赛题：CCPC Final 2025 L 数不同的区间张成空间，2026 ICPC 网络赛第二场 A 求最小的公共空间。附 8 道练习题。"
weight: 17
math: true
toc: true
---
给 $n$ 个数，从中任选一些异或起来，最大能得到多少？$n = 50$ 时子集有 $2^{50}$ 个，枚举不动。可是这些子集的异或值里有大量重复：$a$、$b$、$a \oplus b$ 三个数，任选子集能得到的值和只用 $a$、$b$ 时一模一样，第三个数是多余的。把多余的数一个个去掉，剩下的数最多 60 个（每个数 60 位），能异或出的值却一个不少。剩下的这组数就是**线性基**。要说清楚“多余”是什么意思、为什么最多剩 60 个，需要把异或放进线性代数里看。

## 1. 线性基是什么

### 1.1 一个数是 GF(2) 上的向量

把一个小于 $2^{60}$ 的数写成 60 位二进制，每一位是 0 或 1，这个数就成了一个 60 维向量。两个数异或是逐位相加再模 2：$1 \oplus 1 = 0$ 正好是 $1 + 1 \equiv 0 \pmod 2$。只有 0、1 两个元素，加法和乘法都模 2 的域记作 **GF(2)**（也写 $\mathbb{F}_2$），所以**异或就是 GF(2) 上的向量加法**。

GF(2) 里系数只有 0 和 1，一个线性组合 $x_1 a_1 + x_2 a_2 + \cdots + x_n a_n$（$x_i \in \{0, 1\}$）就是“把 $x_i = 1$ 的那些数异或起来”。子集异或和与线性组合是同一件事，线性代数的几个概念可以直接搬过来：

- **张成的空间**：所有子集异或和组成的集合，记作 $\operatorname{span}(a_1, \dots, a_n)$。
- **线性无关**：没有一个非空子集的异或和等于 0。题面写“不存在异或和为 0 的非空子集”，说的就是线性无关。
- **基与秩**：一组线性无关、又能异或出空间里每个值的数叫这个空间的一组基；基里数的个数是空间的维数，也叫原来那组数的**秩**，记作 $r$。60 维空间里线性无关的数最多 60 个，所以 $r \le 60$。

这些概念在实数上是同一套，[L1 线性代数](/zh/algo/l1-linear-algebra/)讲了普通线性代数的模型，以及同一组 0/1 向量为什么在实数和 GF(2) 上秩不同。

开头说的“多余”就是“能被别的数异或出来”，去掉它不改变张成的空间；去到不能再去时，剩下的数线性无关，就是一组基。**换成基以后，能异或出的值不变，数的个数从 $n$ 降到 $r \le 60$**，后面所有问题都在这至多 60 个数上做。

### 1.2 按最高位存：插入就是一边插入一边消元

线性基用一个数组 `b[0..59]` 存，规定 **`b[i]` 要么是 0，要么是一个最高位恰好是第 $i$ 位的数**。插入 $x$ 时从高位往低位看：第 $i$ 位是 1 而 `b[i]` 空着，就把 $x$ 存进 `b[i]`；`b[i]` 已经有数，就令 $x \leftarrow x \oplus b_i$，把第 $i$ 位消成 0，继续看更低的位。

下面按位走一遍插入。默认插入 6、3、5、1：5 被消成 0，插入失败；其余三个各占一个主元位。可以换成自己的数。

<iframe src="/maps/xor-basis-insert.zh.html" title="线性基插入：分步看" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:545px;overflow:hidden;margin:1.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/xor-basis-insert.zh.html" target="_blank" rel="noopener">在新窗口打开</a></p>

插入过程中 $x$ 每次异或上的都是基里的数，所以任何时刻都有 $x_{\text{原}} = x_{\text{当前}} \oplus (\text{若干个 } b_i)$。插入有两种结局：

- $x$ 被消成 0：$x_{\text{原}}$ 等于若干个 $b_i$ 的异或，它已经在张成的空间里，`insert` 返回 `false`，基不变。
- $x$ 停在某个空位 `b[i]`：存进去的是 $x_{\text{原}}$ 异或上若干个已有的基，张成的空间和直接把 $x_{\text{原}}$ 放进去一样，秩加 1。

存下的数为什么线性无关：它们的最高位两两不同。任取其中一个非空子集异或，最高位最高的那个数在它的最高位上是 1，子集里别的数在这一位都是 0（它们的最高位更低），异或结果在这一位是 1，不可能是 0。

所以插完 $n$ 个数后，`b` 里的非零数是 $\operatorname{span}(a_1, \dots, a_n)$ 的一组基，个数就是秩 $r$。**一个数能不能被异或出来，就是对它走一遍插入的消元，看最后剩不剩 0**，这就是 `contains`。

把 $n$ 个数排成一个 $n$ 行 60 列的 0/1 矩阵，插入做的就是模 2 的高斯消元：每个 `b[i]` 是一行主元在第 $i$ 列的行，“用 `b[i]` 消掉 $x$ 的第 $i$ 位”是一次行变换。区别在顺序。高斯消元拿到整个矩阵再逐列消；**线性基来一行消一行，所以能在线插入**。`b` 按 $i$ 从大到小排是行阶梯形，第 1.4 节的规范化再把它整理成简化行阶梯形。

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
   - **基的 $2^r$ 种选法给出 $2^r$ 个结果**：基里 $r$ 个数各选或不选。
   - **这些结果两两不同**：假如两种不同的选法结果相同，两个结果异或得 0，这正是两种选法的对称差的异或和；对称差非空，和线性无关矛盾。
   - **空间里的每个值都能由基得到**：所以不同的值正好 $2^r$ 种，包括空集给的 0。
   - **例子**：基是 6 和 3，四种选法给出 0、6、3、5。
3. **每种值为什么恰好 $2^{n-r}$ 个子集**
   - **平均数还不能说明每种一样多**：$2^n$ 个子集分到 $2^r$ 种值上，平均每种 $2^{n-r}$ 个，还要说明分得均匀。
   - **把 $n$ 个数分成成功和失败两部分**：插入成功的 $r$ 个原数组成一组基（每个都不能被之前成功的数表示，所以线性无关）；插入失败的 $n - r$ 个数，每个都能被这组基异或出来。
   - **失败的部分可以随便选**：要异或出某个能得到的值 $v$，先在失败的 $n - r$ 个数里任选，共 $2^{n-r}$ 种选法，这部分的异或和记为 $u$。
   - **成功的部分只有一种补法**：还差的 $v \oplus u$ 也在空间里，而基的表示唯一，所以恰好有 1 种选法凑出它。
   - **异或出 $v$ 的子集和失败部分的选法一一对应**：所以正好 $2^{n-r}$ 个，和 $v$ 是哪个值无关。
   - **例子**：失败的数是 5。要得到 6 时，不选 5，基里选 6，得 $\{6\}$；选 5，还差 $6 \oplus 5 = 3$，基里选 3，得 $\{3, 5\}$。
   - **线性代数里这是秩-零化度定理**：把选法写成 $x \in \{0, 1\}^n$，异或和 $f(x) = x_1 a_1 \oplus \cdots \oplus x_n a_n$ 是线性映射，像的维数是 $r$，核（异或出 0 的选法）的维数就是 $n - r$；异或出 $v$ 的选法是核整体平移一下，和核一样大。
4. **做题时怎么用这个结论**
   - **数异或和等于 $t$ 的子集**：$t$ 能异或出来（`contains(t)`）就是 $2^{n-r}$ 个，否则 0 个。代码见 2.2。
   - **数异或和为 0 的非空子集**：0 一定能得到，有 $2^{n-r}$ 个子集，去掉空集是 $2^{n-r} - 1$ 个。
   - **把全部 $2^n$ 个子集的异或和排序**：不去重时看成 $2^r$ 种不同的值，每种连续重复 $2^{n-r}$ 次。见 2.5 末尾。

### 1.4 规范化：每个主元位只留在一个数里，值的大小顺序就是选法的二进制

> 规范化的本质：把线性基整理成它所在空间唯一的标准形，于是第 $k$ 小能按二进制位直接读出，两个空间是否相同也能直接比基。

最大值只关心每一位尽量是 1。第 $k$ 小要的是全部 $2^r$ 个值的排序，`b` 现在的样子还看不出顺序：高位的基在低位上的 1 会干扰低位的比较。所以先整理一下。把每个非零 `b[i]` 的最高位 $i$ 叫**主元位**，**规范化**就是让每个主元位只出现在自己那个数里：`b[i]` 在某个更低的主元位 $j$ 上是 1，就异或上 `b[j]` 把它消掉。

规范化之后，把 $r$ 个基按主元位从低到高编号为 $c_0, c_1, \dots, c_{r-1}$，$c_t$ 的主元位记作 $p_t$。任取一种选法，结果在第 $p_t$ 位上就是“$c_t$ 选了没有”，因为别的基在这一位都是 0。

比较两种不同选法的结果。设 $t$ 是两者选得不一样的编号里最大的那个。高于 $p_t$ 的位只受编号大于 $t$ 的基影响（编号不超过 $t$ 的基，最高位不超过 $p_t$），这些基两边选得一样，所以高于 $p_t$ 的位全相同；第 $p_t$ 位上，选了 $c_t$ 的那边是 1，另一边是 0。所以**把选法写成二进制数 $\sum_{t \text{ 被选}} 2^t$，结果的大小顺序和这个二进制数的大小顺序一致**：从小到大第 $k$ 个值（$k$ 从 0 数，第 0 个是 0），就是按 $k$ 的二进制位去选基。

下图用一个 4 位的例子把规范化和第 $k$ 小连起来：上面是规范化前后的 `b`，下面是 $k = 0, \dots, 7$ 选出的值。

<a href="/images/algo/xor-basis-rref-kth.zh.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-rref-kth.zh.svg" alt="规范化和第 k 小：左边 b[3]=1101、b[2]=0111、b[0]=0001，主元列里多出来的 1 标红；经过 b[2]^=b[0]、b[3]^=b[2]、b[3]^=b[0] 三步，右边变成 1010、0110、0001，主元列 3、2、0 各只剩一个 1。下面 k 从 0 到 7，按 k 的二进制选 c0=b[0]、c1=b[2]、c2=b[3]，得到 0、1、6、7、10、11、12、13，值在主元位上的比特就是 k 的比特，所以按 k 递增。" style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

### 1.5 前提：要的集合对异或封闭

用基代替原来的数，前提是题目要的就是“任选子集”能异或出的全部值。这个集合对异或封闭：两个子集的异或和再异或，等于两个子集的对称差的异或和，仍是某个子集的异或和。题目一旦限制了能选哪些子集，封闭性就可能没了。

比如 $a = (1, 2, 4)$，规定不能选相邻的两个。合法的选法是不选、只选一个、选第 1 和第 3 个，异或和为 $0, 1, 2, 4, 5$，最大是 5。把这些值插进线性基再求最大，会得到 $1 \oplus 2 \oplus 4 = 7$，可 7 要三个数全选，违反了限制。错在线性基把合法值之间的异或也当成了能取到的值：$1 \oplus 2 = 3$ 对应的选法“第 1 和第 2 个”本身不合法。**先确认要的值构成一个对异或封闭的集合（任选子集、一条路径加任意环这类），再用线性基；带选取限制的，先想办法把限制拆掉，拆不掉就换搜索或 DP。**

## 2. 线性基能做什么

线性基回答的都是“从这些数里任选子集异或起来”的问题。下面先把能做的事分成几类讲清楚，每一条说问的是什么、怎么做、多快、在哪一小节；后面每小节先给复杂度，再给代码。为什么能这样做，见第 1 节。下文 $n$ 是插入过的数的个数，$r$ 是秩。

1. **判断一个数能不能异或出来。** 对它走一遍插入的消元，最后剩 0 就能（`contains`），$O(60)$。插入本身也是 $O(60)$，$n$ 个数全插完 $O(60 n)$。见 2.1。
2. **数个数。** 这一类只用到秩，见 2.2：
   - 能异或出多少种不同的值：$2^r$ 种，包括空集给的 0。
   - 异或和等于 $t$ 的子集有几个：$t$ 能异或出来时是 $2^{n-r}$ 个，否则 0 个。要先 `contains(t)`，$O(60)$。
   - 异或和为 0 的非空子集有几个：$2^{n-r} - 1$ 个，减掉的是空集。
3. **求最大、最小。** “$s$ 异或上任意子集”的最大值，从高位往低位贪心，这一位能变成 1 就异或上对应的基（`max_xor`）；最小值反过来（`min_xor`）。都是 $O(60)$，见 2.3。只要非空子集的最小值时，0 算不算要看 $r$ 是否等于 $n$，见 2.5 末尾。
4. **排第几。** 第 $k$ 小、或者一个值是第几小：先规范化一次（`reduce()`，$O(60^2)$，见 2.4），之后按 $k$ 的二进制位选基就是第 $k$ 小（`kth`），反过来读主元位就是排名（`index`），每次 $O(60)$。见 2.5。
5. **合并。** 把一组基的每个数插进另一组（`merge`），$O(60^2)$。放在线段树、倍增表的节点上，就能拼出任意区间、树上路径的基。见 2.6。

区间、带权、区间询问这些变形在第 3 节。全部函数合在一起的板子在文末附录。

### 2.1 插入和判断能否异或出来

插入怎么做、为什么插入失败就说明能异或出来，见 1.2。

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

### 2.2 计数

能异或出的不同值有 $2^r$ 个（含空集给的 0）；异或和等于 $t$ 的子集，$t$ 能异或出来时有 $2^{n-r}$ 个，否则没有；异或和为 0 的非空子集有 $2^{n-r} - 1$ 个。为什么是这些数，见 1.3。

#### 复杂度

种类数和为 0 的子集数是 $O(1)$，只用到秩；等于 $t$ 的子集数要先 `contains(t)`，$O(60)$。

```cpp
// 插过 n 个数之后。n - r 可能很大，题目要取模时把 1LL << 换成快速幂
long long kinds(const XorBasis& lb) { return 1LL << lb.r; }               // 不同异或值的个数，含 0
long long ways(const XorBasis& lb, int n, long long t) {                  // 异或和等于 t 的子集个数，含空集
    return lb.contains(t) ? 1LL << (n - lb.r) : 0;
}
```

“异或和为 0 的非空子集”是 `ways(lb, n, 0) - 1`，减掉的是空集。

### 2.3 最大异或：从高位往低位贪心

比较两个数先比最高位，所以要让结果最大，先让最高位尽量是 1。设当前结果为 $v$，从 $i = 59$ 往下：$v$ 的第 $i$ 位是 0 而 `b[i]` 非零，就异或上 `b[i]`。这一步不碰更高的位，因为 `b[i]` 的最高位就是 $i$；之后也不会把第 $i$ 位改回去，因为后面用到的 `b[j]`（$j < i$）在第 $i$ 位都是 0。**高位优先、每一位能变成 1 就变成 1，最后得到的就是最大值。** 写成代码是 `v = max(v, v ^ b[i])`：第 $i$ 位是 0 时异或后变大，是 1 时变小。

起点不一定是 0。“$s$ 异或上任意子集的最大值”，从 $v = s$ 开始贪心即可，第 4 节图上的路径就要用到。最小值反过来，异或后变小就异或，得到 $s$ 异或上任意子集的最小值。

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

这两个是 `XorBasis` 的成员函数，`b[i]` 为 0 时异或不改变 $v$，不用特判。$s = 0$ 时最小值总是 0（空集），题目要“非空子集的最小值”，见 2.5 末尾。

### 2.4 规范化

为什么要规范化、规范化后是什么样子，见 1.4。

#### 复杂度

`reduce()` 是 $O(60^2)$：两重循环，各至多 60 次。

```cpp
    void reduce() {                              // 规范化：主元位只留在自己那个数里
        for (int i = 0; i < B; i++)
            for (int j = i - 1; j >= 0; j--)
                if (b[j] && (b[i] >> j & 1)) b[i] ^= b[j];
    }
```

`i` 从小到大处理，轮到 `b[i]` 时更低的 `b[j]` 都已经规范好，除了第 $j$ 位不含别的主元位，异或它只会清掉 `b[i]` 的第 $j$ 位，不会把别的主元位翻回 1。异或上基里的数不改变张成的空间，也不改变 `b[i]` 的最高位，所以规范化后仍是同一个空间的一组基，仍满足 1.2 的规定。

### 2.5 第 $k$ 小和求排名

为什么按 $k$ 的二进制选基就是第 $k$ 小，见 1.4。`index` 反过来：一个能异或出来的值，在主元位上的比特拼起来就是它从 0 数的排名。

#### 复杂度

`kth` 和 `index` 都是 $O(60)$；前面的 `reduce()` 只需要做一次，$O(60^2)$。

```cpp
    long long kth(unsigned long long k) const {  // 先 reduce()；k 从 0 数，第 0 个是 0
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;                       // k ≥ 2^r：不存在
    }
    unsigned long long index(long long x) const {  // 先 reduce()；x 能被异或出来时，它是第几小（从 0 数）
        unsigned long long k = 0;
        for (int i = 0, t = 0; i < B; i++)
            if (b[i]) { if (x >> i & 1) k |= 1ULL << t; t++; }
        return k;
    }
```

题面里的“第 $k$ 小”（$k$ 从 1 数）常有两种算法，差别都在 0 和重复值上：

- **只算非空子集、去重**：0 能不能由非空子集得到，看有没有插入失败的数。$r < n$ 时能（失败的数和表示它的那些基一起选），这时非空子集的不同值和含空集时一样，答案是 `kth(k - 1)`；$r = n$ 时不能，要跳过 0，答案是 `kth(k)`。**$r$ 是否等于 $n$ 决定 0 算不算，这是这类题最常错的地方。**
- **按全部 $2^n$ 个子集算、不去重**：每个值重复 $2^{n-r}$ 次（1.3），第 $k$ 个就是不同值里从 0 数的第 $\lfloor (k - 1) / 2^{n-r} \rfloor$ 个。

非空子集的最小值也由此得到：$r < n$ 时是 0，否则是 `kth(1)`，也就是规范化后主元位最低的那个基。

### 2.6 合并两组基

#### 复杂度

`merge` 是 $O(60^2)$：另一组至多 60 个非零数，每个插入 $O(60)$。

```cpp
    void merge(const XorBasis& o) {              // 把另一组基并进来，O(60^2)；之后要第 k 小得重新 reduce()
        for (int i = 0; i < B; i++)
            if (o.b[i]) insert(o.b[i]);
    }
```

“一段里所有数的线性基”可以放在线段树、倍增表的节点上，靠合并拼出任意区间或树上路径的基；线段树上一次区间询问合并 $O(\log n)$ 个节点，$O(60^2 \log n)$。线性基不支持删除；要删的题，离线成“每个数在哪段时间里存在”，再做线段树分治。

## 3. 题目里常见的变形

前两节回答的都是“给一堆数，任选子集”。比赛题很少直接这样问，常见的是把别的结构翻译成这个问题，或者在它上面加一层要求。

### 3.1 区间的异或：先换成前缀异或

例（CF 1101G）：把数组切成尽量多段，要求任选若干段（至少一段），它们的异或和都不为 0。

设前缀异或 $S_i = a_1 \oplus \cdots \oplus a_i$，$S_0 = 0$。切点 $0 = c_0 < c_1 < \cdots < c_k = n$ 时，第 $j$ 段的异或是 $S_{c_j} \oplus S_{c_{j-1}}$，条件是这 $k$ 个段值线性无关。段值和前缀值可以互相表示：$S_{c_j}$ 等于前 $j$ 段的异或。两组各 $k$ 个数互相能表示，就张成同一个空间；$k$ 个数线性无关，等价于它们张成 $k$ 维，所以

$$
\text{段值线性无关} \iff S_{c_1}, S_{c_2}, \dots, S_{c_k} \text{ 线性无关}.
$$

问题变成从 $S_1, \dots, S_n$ 里选尽量多的线性无关的数，而且必须选上 $S_n$。$S_n = 0$ 时无解；否则 $\{S_n\}$ 本身线性无关，能扩充成 $S_1, \dots, S_n$ 的一组基，答案就是这 $n$ 个前缀异或的秩，全部插一遍是 $O(60 n)$。**段和区间的异或先写成两个前缀异或的异或，再看前缀异或这组数的线性关系。**

### 3.2 带权选数：按权从大到小插

每个数带一个非负权值，要选出一组线性无关的数使权值和最大。做法是按权值从大到小排序，依次插入，插入成功的就选上。

为什么贪心对。设贪心选出的数按权值排成 $g_1, \dots, g_r$，权值不增；任取一组线性无关的数，也按权值排成 $o_1, \dots, o_m$。先有 $m \le r$：贪心选出的数是全部数的一组基，任何线性无关组都不超过秩。再证每个 $t$ 都有 $w(g_t) \ge w(o_t)$，加起来就得到贪心最优。假设某个 $t$ 上 $w(o_t) > w(g_t)$。$o_1, \dots, o_t$ 是 $t$ 个线性无关的数，$g_1, \dots, g_{t-1}$ 只张成 $t - 1$ 维，所以其中某个 $o_j$（$j \le t$）不能被 $g_1, \dots, g_{t-1}$ 表示。它的权值 $w(o_j) \ge w(o_t) > w(g_t)$，贪心在 $g_t$ 之前就处理过它；当时已选的数都在 $g_1, \dots, g_{t-1}$ 里，表示不出 $o_j$，那 $o_j$ 应该插入成功、成为某个 $g_s$（$s < t$），和“不能被 $g_1, \dots, g_{t-1}$ 表示”矛盾。

#### 复杂度

排序 $O(n \log n)$，插入 $O(60 n)$。

```cpp
// items：(数, 权值)，权值非负。返回线性无关组的最大权值和
long long max_weight(vector<pair<long long, long long>> items) {
    sort(items.begin(), items.end(),
         [](const auto& p, const auto& q) { return p.second > q.second; });
    XorBasis lb;
    long long sum = 0;
    for (auto [x, w] : items)
        if (lb.insert(x)) sum += w;
    return sum;
}
```

**线性无关组有交换性质（小的一组总能从大的一组里借一个数扩充），所以按权从大到小贪心插入就是最优。** 这个结论下一节还会用到，权值换成位置。

### 3.3 区间询问：前缀线性基，每个主元位留最靠右的

例（CF 1100F）：一个数组，多次询问区间 $[l, r]$ 里任选子集的最大异或。每次询问重建一遍基要 $O(60 \cdot \text{区间长})$，太慢。

做法叫**前缀线性基**：从左往右插入，`b[i]` 旁边多记一个位置 `pos[i]`。插入第 $p$ 个数时，碰到的 `b[i]` 位置比 $p$ 小，就把两者交换：新来的留在 `b[i]`，旧的带着它的位置继续往低位消。插完第 $r$ 个数时的这份基，回答所有右端点为 $r$ 的询问：只用 `pos[i]` $\ge l$ 的那些 `b[i]` 贪心。

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

为什么只留 `pos[i]` $\ge l$ 的就对：这是 3.2 的贪心，权值取位置。按位置从大到小插 $a_r, a_{r-1}, \dots$，插完 $a_l$ 时，基已经能表示 $a_l, \dots, a_r$ 里的每个数；再往左插的数，只会填还空着的维度，不会挤掉已有的。所以“按位置从右往左贪心”得到的基里，位置 $\ge l$ 的那部分正好张成 $a_l, \dots, a_r$。交换插入是在线维护这个贪心的结果：新来的数位置最大，应该最先被选，碰到位置更小的就把它往下挤，被挤到消成 0 的是一组线性相关的数里最靠左的那个。**每个主元位留最靠右的数，询问 $[l, r]$ 只用位置 $\ge l$ 的部分。** 询问按 $r$ 离线排序，只维护一份基。

下图是数组 $5, 6, 3, 4$ 依次插入时每一步的基，以及右端点为 4 时的询问 $[3, 4]$：

<a href="/images/algo/xor-basis-prefix.zh.svg" target="_blank" rel="noopener"><img src="/images/algo/xor-basis-prefix.zh.svg" alt="区间线性基：数组 101、110、011、100。插完 a1：b[2]=101@1。插完 a2：110@2 换下 101@1，101 往下消成 011 存进 b[1]。插完 a3：011@3 换下 011@1，旧的消成 0 丢掉。插完 a4：100@4 进 b[2]，110@2 被挤下去，消成 001 存进 b[0]。询问 [3,4] 只用位置不小于 3 的 100@4 和 011@3，最大异或 111=7。" style="display:block;width:100%;max-width:1000px;margin:1em auto"></a>

## 4. 从 0 写一道题：最大 XOR 和路径

题（洛谷 P4151，WC2011）：无向连通图，$n \le 5 \times 10^4$ 个点，$m \le 10^5$ 条边，边权不超过 $10^{18}$，可能有重边和自环。求一条从 1 到 $n$ 的路径，使经过的边权异或和最大；路径可以重复经过点和边，重复经过的边重复计入异或。

### 4.1 所有路径的异或值是什么集合

能用线性基之前，先看要的集合是不是“某个值异或上一个空间”。路径可以走回头路，一条边走两次等于没走。设 $P$ 是一条固定的从 1 到 $n$ 的路径，$Q$ 是任意另一条。沿 $P$ 去、沿 $Q$ 原路回，是一条回路 $C$，所以 $Q$ 的异或值等于 $P \oplus C$。反过来，任取一条回路 $C$，从 $P$ 的起点 1 出发走到 $C$ 上、绕一圈、原路回到 1，再走 $P$，来回的那段抵消，得到的路径异或值是 $P \oplus C$。所以

$$
\{\text{所有 1 到 } n \text{ 路径的异或值}\} = \{\, P \oplus C \mid C \text{ 是回路的异或值} \,\},
$$

回路的异或值对异或封闭（两条回路接起来还是回路，中间来回的一段抵消），是一个空间。**答案就是 `max_xor(P)`，问题只剩下怎么求出回路空间的一组基。**

### 4.2 回路空间的基：每条边一个环

从 1 出发做一遍 BFS（或 DFS），得到一棵生成树，记 $d_u$ 为从 1 沿树边走到 $u$ 的异或和。对回路上的每一步 $u \to v$（边权 $w$），写成

$$
w = d_u \oplus d_v \oplus \underbrace{(d_u \oplus d_v \oplus w)}_{\text{树边上是 } 0}.
$$

沿一条回路把每一步都这样写开再全部异或起来，$d$ 的部分首尾相接、两两抵消，只剩括号里那项，而它只在非树边上非零。所以任何回路的异或值都是若干个 $d_u \oplus d_v \oplus w$ 的异或；反过来，每个 $d_u \oplus d_v \oplus w$ 本身就是一个回路（树上从 $u$ 到 $v$，再走这条边回来）。**把每条边的 $d_u \oplus d_v \oplus w$ 都插进线性基，就得到回路空间的基**：树边插进去是 0，不影响；自环和重边不用特判。

答案是从 $d_n$ 出发的最大异或（$d_n$ 就是树上的那条路径 $P$），复杂度 $O((n + m) \cdot 60)$。

### 4.3 完整程序

```cpp
#include <bits/stdc++.h>
using namespace std;

// 套附录的 XorBasis（用到 insert 和 max_xor）

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

写完先和暴力对拍。边权取小于 16 的值时，“当前在哪个点、当前异或值是多少”这个状态只有 $16 n$ 种，从 $(1, 0)$ 出发 BFS 出所有能到的状态，落在点 $n$ 上的那些异或值就是全部路径的异或值，取最大和程序比。**能重复走的路径题，状态（点，异或值）在小边权下是有限的，这是现成的暴力。**

## 5. 两道近年的赛题

### 5.1 CCPC Final 2025 L（Spirited Away）：数不同的区间张成空间

题（[QOJ / Universal Cup 3727 L](https://contest.ucup.ac/contest/3727/problem/18012)，时限 4 秒）：给一个非负整数序列 $a_1, \dots, a_n$。对区间 $[l, r]$，从 $a_l, \dots, a_r$ 里任选若干个异或起来（可以一个都不选，结果是 0），所有可能的结果组成集合 $B(l, r)$，也就是 $a_l, \dots, a_r$ 张成的空间。对所有 $1 \le l \le r \le n$，问一共有多少个不同的集合 $B(l, r)$。

**输入**：第一行一个整数 $T$，表示数据组数。每组第一行一个整数 $n$（$1 \le n \le 10^5$），第二行 $n$ 个整数 $a_i$（$0 \le a_i < 2^{32}$）。所有组的 $n$ 之和不超过 $10^5$。

**输出**：每组输出一行，表示不同集合 $B(l, r)$ 的个数。

**样例**

```text
输入
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

输出
4
10
12
36
46
```

第一组 $a = (1, 2, 3)$：$B(1, 1) = \{0, 1\}$，$B(2, 2) = \{0, 2\}$，$B(3, 3) = \{0, 3\}$，其余三个区间都是 $\{0, 1, 2, 3\}$，所以答案是 4。

#### 5.1.1 不同的区间只有 $O(32 n)$ 种

区间有 $O(n^2)$ 个，先要缩到能枚举的量。固定右端点 $r$，左端点 $l$ 往左走时空间只会变大，每变一次维数加 1，所以最多变 32 次。变化点就是 3.3 前缀线性基里的那些位置：把插完 $a_r$ 后的基按 `pos` 从大到小排成 $v_1, \dots, v_k$，位置为 $p_1 > p_2 > \cdots > p_k$，记 $p_{k+1} = 0$，那么

$$
B(l, r) = \operatorname{span}(v_1, \dots, v_j), \qquad p_{j+1} < l \le p_j .
$$

这是 3.3 那句“位置 $\ge l$ 的部分正好张成 $a_l, \dots, a_r$”换了个说法。另外 $a_r = 0$ 时 $l = r$ 给出 $\{0\}$（这时 $p_1 < r$）。**固定右端点，左端点往左只经过至多 32 个跳变点，所有区间的空间加起来只有 $O(32 n)$ 个。**

#### 5.1.2 两个空间相同，当且仅当规范化后的基相同

同一个空间有很多组基，直接比基不行，得找一个只由空间决定的写法。规范化后的基就是。空间里每个非零数的最高位都是主元位（理由和 1.2 的线性无关证明一样：任何组合的最高位，就是参与组合的基里最高的那个主元位），所以主元位的集合由空间决定。再看主元位 $p$ 上的那个基 $c_p$：规范化之后，它是空间里“主元位中只有第 $p$ 位是 1”的数，而 1.4 说空间里的数由它在主元位上的取值唯一决定，这样的数只有一个。所以 **规范化后的基由空间唯一决定，两个空间相同当且仅当规范化后的基相同**。把规范化的基哈希成一个 64 位数，最后数有多少种不同的哈希值。

#### 5.1.3 一边插入一边保持规范化

对每个 $r$，按 $v_1, v_2, \dots$ 的顺序往一个空的基里插，每插一个记下当前空间的哈希。如果每次插完都调用 2.4 的 `reduce()` 再整体哈希，一次是 $O(32^2)$，每个 $r$ 要 $O(32^3)$，太慢。改成插入时就保持规范化：先用已有的基把新数 $y$ 的主元位全部消掉，$y$ 剩下的最高位 $t$ 是一个新主元位；再把已有的基里第 $t$ 位是 1 的都异或上 $y$。这样每插一个是 $O(32)$。哈希取各个基打散之后的和，改动一个基就减去旧的、加上新的。总复杂度 $O(32^2 n)$，$n = 10^5$ 时约 $10^8$ 次简单操作。

```cpp
#include <bits/stdc++.h>
using namespace std;
using u32 = uint32_t;
using u64 = uint64_t;

u64 mix(u64 x) {                          // splitmix64：把一个数打散成随机的 64 位
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

int main() {
    int T;
    scanf("%d", &T);
    while (T--) {
        int n;
        scanf("%d", &n);
        u32 b[32] = {};                   // 3.3 的前缀线性基
        int pos[32] = {};
        vector<u64> hs;                   // 每个 (r, j) 对应空间的哈希
        for (int r = 1; r <= n; r++) {
            u32 x;
            scanf("%u", &x);
            int p = r;
            for (int i = 31; i >= 0; i--) {
                if (!(x >> i & 1)) continue;
                if (!b[i]) { b[i] = x; pos[i] = p; break; }
                if (pos[i] < p) { swap(b[i], x); swap(pos[i], p); }
                x ^= b[i];
            }
            vector<pair<int, u32>> v;     // (位置, 基)，按位置从大到小
            for (int i = 0; i < 32; i++)
                if (b[i]) v.push_back({pos[i], b[i]});
            sort(v.rbegin(), v.rend());
            if (v.empty() || v[0].first < r) hs.push_back(0);   // a_r = 0：B(r, r) = {0}
            u32 c[32] = {};               // 规范化的基，一个一个往里插
            u64 h = 0;
            for (auto [q, y] : v) {
                for (int i = 31; i >= 0; i--)
                    if ((y >> i & 1) && c[i]) y ^= c[i];          // 消掉 y 上已有的主元位
                int t = 31 - __builtin_clz(y);                    // 新的主元位
                for (int i = t + 1; i < 32; i++)
                    if (c[i] >> t & 1) { h -= mix(c[i]); c[i] ^= y; h += mix(c[i]); }
                c[t] = y;
                h += mix(y);
                hs.push_back(h);          // l 落在 (下一个位置, q] 时的 B(l, r)
            }
        }
        sort(hs.begin(), hs.end());
        printf("%d\n", (int)(unique(hs.begin(), hs.end()) - hs.begin()));
    }
}
```

$O(32 n)$ 个 64 位哈希值里出现碰撞的概率约是 $(3 \times 10^6)^2 / 2^{65}$，可以忽略。

### 5.2 2026 ICPC 网络赛第二场 A（All Closed）：所有解都必须包含的数

题（[QOJ 4113](https://qoj.ac/contest/4113)）：有 $n$ 个非空集合 $S_1, \dots, S_n$，元素都在 $[0, 2^m)$ 里，$m \le 20$。一次操作选一个数 $x$，把它同时加进所有集合。用最少的操作让每个集合都对异或封闭，输出要加的那些数。

#### 5.2.1 把“最少操作”换成“最小的空间”

设加进去的数组成集合 $T$，最后第 $i$ 个集合是 $S_i \cup T$。一个非空集合对异或封闭，就包含 $a \oplus a = 0$，又对加法封闭，所以它就是一个空间。看所有最终集合的公共部分：

$$
K = \bigcap_{i} (S_i \cup T) = I \cup T, \qquad I = \bigcap_i S_i .
$$

若干个空间的交还是空间，所以 $K$ 是一个包含 $I$ 的空间，并且最终集合可以写成 $S_i \cup K$。$T$ 里不必放 $I$ 中的数（它们本来就在每个集合里），所以 $|T| = |K| - |I|$，**操作最少等价于 $K$ 最小：求最小的空间 $K \supseteq I$，使每个 $S_i \cup K$ 都是空间，答案是 $K \setminus I$。**

#### 5.2.2 每一步加的数都是逼出来的

从 $K = \operatorname{span}(I)$ 开始，任何合法的 $K$ 都包含 $I$、又是空间，所以都包含 $\operatorname{span}(I)$。如果某个 $S_i \cup K$ 不封闭，就有一个数 $x$ 落在 $\operatorname{span}(S_i \cup K)$ 里，却既不在 $S_i$ 也不在 $K$ 里。任取一个包含当前 $K$ 的合法解 $K^*$：$S_i \cup K^*$ 是空间，又包含 $S_i \cup K$，所以包含 $x$；$x$ 不在 $S_i$ 里，只能在 $K^*$ 里。于是每个合法解都包含 $x$，令 $K \leftarrow \operatorname{span}(K \cup \{x\})$，它仍然被每个合法解包含。

每加一个 $x$，$K$ 的秩加 1，至多 $m$ 次后所有 $S_i \cup K$ 都封闭。这时 $K$ 本身合法，又包含于每个合法解，所以它就是最小的那个，答案也因此唯一。**求最小的合法解，可以从“每个合法解都必须包含什么”出发，一直加到合法为止，停下时得到的就是最小解。**

#### 5.2.3 判断封闭：数元素个数

$S_i \cup K \subseteq \operatorname{span}(S_i \cup K)$，而后者正好有 $2^r$ 个元素（1.3），$r$ 是 $S_i \cup K$ 的秩。所以

$$
S_i \cup K \text{ 封闭} \iff \lvert S_i \rvert + \lvert K \rvert - \lvert S_i \cap K \rvert = 2^r .
$$

不封闭时，把 $\operatorname{span}(S_i \cup K)$ 列出来（至多 $2^m$ 个），找一个既不在 $S_i$ 也不在 $K$ 里的数，就是要加的 $x$。每轮检查所有集合是 $O(m \sum \lvert S_i \rvert)$，至多 $m$ 轮，再加上每轮 $O(2^m)$ 的列举。

```cpp
#include <bits/stdc++.h>
using namespace std;

int n, m;

// 套附录的 XorBasis

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
    scanf("%d %d", &n, &m);
    vector<vector<int>> s(n);
    vector<int> cnt(1 << m, 0);            // cnt[x]：x 在几个集合里
    for (auto& si : s) {
        int k;
        scanf("%d", &k);
        si.resize(k);
        for (int& x : si) { scanf("%d", &x); cnt[x]++; }
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
    printf("%d\n", (int)ans.size());
    for (int x : ans) printf("%d ", x);
    printf("\n");
}
```

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

| 要做的事 | 线性基 `XorBasis` | 增量高斯 `IncGauss` |
| --- | --- | --- |
| 一行是什么 | 一个数，没有右端 | 一条方程：系数 bitset + 右端 |
| 按什么存 | `b[i]` 就是主元在第 $i$ 位的那一行 | 每行记它的主元列 `piv` |
| 加一个数 / 一条方程 | `insert`，不清旧行，$O(60)$ | `add`，清旧行，始终是简化行阶梯形，$O(r \cdot \text{MV} / 64)$ |
| 能否表示出来 | `contains`，$O(60)$ | `implied`，还给出推出的右端，$O(r \cdot \text{MV} / 64)$ |
| 秩 | `r`，$O(1)$ | `rank()`，$O(1)$ |
| 规范化 | `reduce()`，要用时再调，$O(60^2)$ | 一直是规范的，不用额外做 |
| 最大 / 最小异或 | `max_xor` / `min_xor`，$O(60)$ | `max_xor` / `min_xor`，$O(r \cdot \text{MV} / 64)$ |
| 第 $k$ 小 / 求排名 | `kth` / `index`，$O(60)$，之前要 `reduce()` 一次 | `kth` $O(r \log r + r \cdot \text{MV} / 64)$ / `index` $O(r \log r)$，不用先规范化 |
| 合并 | `merge`，$O(60^2)$ | `merge`，另一组的 $r'$ 行逐条 `add`，$O(r' \cdot r \cdot \text{MV} / 64)$ |
| 区间询问 | `PrefixBasis`：插入、`max_xor`、`at` 都是 $O(60)$ | `PrefixGauss`：`add`、`implied`、`max_xor` $O(n \cdot \text{MV} / 64)$，`bad` $O(1)$，`rank` $O(n)$，`at` $O(n \cdot r \cdot \text{MV} / 64)$ |
| 消成 0 时 | 插入失败，这个数能被异或出来 | 看右端：是 0 就能由已有方程推出（返回 0），非 0 就矛盾（返回 $-1$，`bad` 记下） |
| 一组解 / 全部解 | 没有 | `solve()` $O(r + \text{MV} / 64)$ / `kernel()` $O((n - r)(r + \text{MV} / 64))$ |
| 列数 | 不超过 60 | 不超过 `MV`，几千也行 |

表里 $r$ 是当前的秩，$n$ 是未知数个数；`MV / 64` 是一行 bitset 占的机器字数，一次 bitset 异或就是这么多次整数异或。线性基的 60 也可以看成“秩不超过 60、一行一个字”，所以两边的复杂度是同一个式子：$\text{MV} = 64$ 时，增量高斯的 $O(r \cdot \text{MV}/64)$ 就是 $O(r)$，而 $r \le 60$。

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
    long long kth(unsigned long long k) const {  // 先 reduce()；第 k 小（k 从 0 数，第 0 个是 0），不存在返回 -1
        long long v = 0;
        for (int i = 0; i < B; i++)
            if (b[i]) { if (k & 1) v ^= b[i]; k >>= 1; }
        return k ? -1 : v;
    }
    unsigned long long index(long long x) const {  // 先 reduce()；x 能被异或出来时，它是第几小（从 0 数）
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
