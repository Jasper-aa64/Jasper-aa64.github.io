---
title: "交易系统笔记 #6:内存对齐、布局与缓存和 DRAM 的几何"
date: 2026-10-04
slug: "alignment-layout-cache-dram-geometry"
description: "为什么热路径上的每个内存决定,最后都归结为一次访问碰哪几条缓存行、这些行住在哪:对齐与填充,alignas 写在类型上和变量上的区别,堆上的过对齐与两档分配器,AoS 与 SoA,用去规范化打断依赖链;再往下进到硬件——L1 的组和关键步长、在 M1 上实测的 2 的幂步长、DRAM 行缓冲、刷新和多通道均衡。"
summary: "访问从来不按字节付钱,按缓存行付;地址决定了碰哪几条行、这些行争哪个缓存组、住在哪个 DRAM 通道和 bank。对齐让一个值不跨行;填充让数组保持对齐;alignas 用空间换隔离,#pragma pack 为了对上外部格式放弃对齐。布局决定一次访问碰几条行——AoS 还是 SoA,去规范化还是连查三次。再往下,地址的几位选定 L1 的组(于是相差 4 KiB 的数据不管缓存多空都在抢 8 个格子)、DRAM 的行缓冲(命中 14 ns,冲突 41 ns)和通道(步长互质才均衡)。按列遍历慢是五层叠加,行缓冲只是最后一层。"
categories: [Systems]
tags: [cpp, alignment, cache, memory-layout, false-sharing, dram, numa, hft, low-latency]
toc: true
homepage: false
---

# 交易系统笔记 #6:地址决定邻居 —— 内存对齐、布局与缓存和 DRAM 的几何

> **一句话**:内存从来不按字节付钱。每次访问都按整条缓存行付,而地址决定了碰哪几条行、这些行在缓存里争哪个组、在 DRAM 里住哪个通道、bank 和行。对齐和布局管前一半;你平时不会去想的那几位地址,管后一半。

## 真正要对付的是什么

下面这张图,是这个系列里所有事情发生的地方。一次 load 先让 TLB 翻译地址,再依次问 L1D、L2、全核共享的 L3,最后经内存控制器到内存条。数据永远按整条 64 字节缓存行搬。

<a href="/images/memory-geometry/hardware-map.zh.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/hardware-map.zh.svg" alt="硬件地图:从流水线和 store buffer,经 L1、L2、L3、内存控制器到内存条,附访问延迟量级表和一个地址的各段" loading="lazy" decoding="async"></a>

这篇从上往下走。前半部分是你能直接控制的:一个值从哪开始、结构体怎么填充、记录怎么摆——用"一次访问碰几条行"来衡量。后半部分进到框的内部:L1 怎么决定一条行能放在哪,为什么某些步长能让几乎空着的缓存不停地踢人,以及一次 DRAM 访问离开芯片之后到底做了什么。

---

## 1. 对齐让一个值待在一条行里

一个值**按 N 对齐**,是说它的地址是 N 的整数倍;`alignof(T)` 就是类型 T 要求的那个 N。x86-64 上基本类型按自己的大小对齐:`int` 是 4,`double` 和指针是 8。

CPU 在乎它,原因是缓存行。行的起点都是 64 的倍数,而 **64 是 8 的倍数**,所以按 8 对齐的 `double` 在一条行里只可能从偏移 0、8……56 开始,最后一个正好撑满。它不可能横跨两条行。落在偏移 60 的 `double`,前 4 字节在这条行,后 4 字节在下一条。

横跨有两类后果,轻重差得很远:

- **变慢。** 一次 load 拆成两次缓存访问(叫**行分裂**),两条行要是在不同的页里,还要多翻译一次。x86 不报错,只是悄悄变慢——所以在 x86 上很难发现对齐问题。
- **原子操作严重得多。** 带 `lock` 前缀的读改写之所以不可分割,是因为核在指令做完之前一直独占它那条行([MESI 缓存一致性](/zh/posts/low-latency-mesi-cache-coherence/))。跨两条行做不到,CPU 只能退化成锁总线——**split lock**,贵得多,还会拖累别的核;Linux 从 5.7 起能检测并报告它。

"按自己的大小对齐就不跨行",只对**大小是 2 的幂、且不超过 64** 的值成立。一个 12 字节、`alignof` 为 4 的结构体,可能从偏移 56 或 60 开始而横跨——16 个可能的起点里有 2 个(枚举)。把它改成 `alignas(16)`(同时补到 16 字节),4 个可能的起点一个都不跨。

---

## 2. 填充是为了数组

编译器摆结构体的成员,规则三条:

1. 成员按声明顺序摆,每个放在第一个是它自己对齐倍数的偏移上,中间的空隙是**填充**字节;
2. 结构体的对齐 = 成员里最大的对齐;
3. `sizeof` 向上补到这个对齐的倍数(**尾部填充**)。

```cpp
struct DefaultAlignedStruct {
    char a;      // 偏移 0,之后 3 字节填充
    int b;       // 偏移 4
    double c;    // 偏移 8
};               // sizeof 16,alignof 8
static_assert(sizeof(DefaultAlignedStruct) == 16 && alignof(DefaultAlignedStruct) == 8);
```

第 3 条是因为数组:`T arr[N]` 的第 *i* 个元素在 `基址 + i × sizeof(T)`。`sizeof` 如果不是 `alignof` 的倍数,第 0 个对齐了,第 1 个就错位了。

成员顺序会改变大小:

```cpp
struct Bad  { char a; double b; char c; int d; };   // 0、8、16、20 → sizeof 24(11 字节填充)
struct Good { double b; int d; char a; char c; };   // 0、8、12、13 → sizeof 16
static_assert(sizeof(Bad) == 24 && sizeof(Good) == 16);
```

按对齐从大到小排,填充最少。放进数组差别是实打实的:一条 64 字节的行能放 2.7 个前者、正好 4 个后者,扫一遍少碰三分之一的行。不过省字节只是一半——热字段也该放在一起(第 7 节),两个目标冲突时,少碰行优先。

---

## 3. `alignas` 写在类型上,还是变量上

`alignas(N)` 要求比默认更高的对齐,写在**哪里**很要紧:

```cpp
struct alignas(32) AlignasType { int data[5]; };    // 数据 20 字节
static_assert(sizeof(AlignasType) == 32 && alignof(AlignasType) == 32);

alignas(64) char buffer[100];                       // 这个变量从一条行的起点开始
static_assert(sizeof(buffer) == 100 && alignof(decltype(buffer)) == 1);
```

- **写在类型上**:每个对象都从 32 的倍数开始,而且按第 3 条,`sizeof` 被补到 32。
- **写在变量上**:只改变这个变量的地址,它的类型和 `sizeof` 都不变。

最常见的取值是 64:对象从行首开始,如果大小又是整数条行,它就**独占**这几条行,邻居的写不会和它抢——这是修伪共享([#2](/posts/memory-ordering-false-sharing-dependency-chains/),英文)的办法,也是 MESI"单写者"规则在硬件上的落地。写在类型上的 `alignas(64)` 会自动把大小补成 64 的倍数(`struct alignas(64) { char x[100]; }` 是 128);写在成员上只挪起点:

```cpp
struct Two   { alignas(64) char a[100]; char b; };              // b 在偏移 100,和 a 的最后一截共用一条行
struct Three { alignas(64) char a[100]; alignas(64) char b; };  // b 在偏移 128,独占一条行
static_assert(offsetof(Two, b) == 100 && offsetof(Three, b) == 128);
```

`std::hardware_destructive_interference_size`(C++17,`<new>`)是"行大小"的可移植写法(标准库提供时)。代价明摆着:`alignas(64)` 把一个 4 字节的计数器撑成 64 字节——用空间买隔离。

---

## 4. 堆上的过对齐

`malloc` 和普通 `new` 只保证"最大基本类型"的对齐——x86-64 上是 16。要更多,得换接口。

**`std::aligned_alloc(alignment, size)`** 要求 `size` 是 `alignment` 的整数倍,否则分配失败、返回空指针。先向上取整:300 字节、64 对齐,就要 320。

```cpp
#include <cstdlib>

void* make_buffer() {
    const size_t alignment = 64, requested = 300;
    size_t size = (requested + alignment - 1) / alignment * alignment;   // 320
    return std::aligned_alloc(alignment, size);                          // 用 std::free 释放
}
```

**过对齐的 `new`**(C++17)在**类型**本身过对齐时自动生效,`delete` 也会配上对应的释放函数。坑在于只在调用处传对齐:

```cpp
struct Plain { float v[4]; };                              // 类型自己只要求 4
auto* p = new (std::align_val_t{128}) Plain();             // 带对齐的分配……
delete p;                                                  // ……普通的释放:不配对,未定义行为
```

`delete` 看的是类型,没看到特别的对齐,就调普通的 `operator delete`。分配和释放不是一对;在 MinGW 上它直接崩,堆损坏(`0xC0000374`)。要么把对齐写进类型,要么两边都手动配对:`p->~Plain(); ::operator delete(p, std::align_val_t{128});`。

**两档分配器。** 一个生产用的 STL 分配器在这些之上做了这样的事:

```cpp
#include <cstdlib>
#include <cstring>
#include <new>
#include <sys/mman.h>

void* allocate_bytes(size_t num_bytes) {
    void* ptr = nullptr;
    if (num_bytes <= (1 << 14)) {                        // 不超过 16 KiB:按缓存行对齐
        const size_t a = 64;
        size_t sz = (num_bytes + a - 1) & ~(a - 1);
        if ((ptr = std::aligned_alloc(a, sz))) std::memset(ptr, 0, sz);
    } else {                                             // 更大:按 2 MiB 对齐
        const size_t a = 1 << 21;
        size_t sz = (num_bytes + a - 1) & ~(a - 1);
        if ((ptr = std::aligned_alloc(a, sz))) {
#if defined(__linux__)
            madvise(ptr, sz, MADV_HUGEPAGE);             // 必须在第一次碰这块内存之前
#endif
            std::memset(ptr, 0, sz);
        }
    }
    if (!ptr) throw std::bad_alloc();
    return ptr;
}
```

- 小请求从行首开始、占整数条行,两次分配永远不共用一条行。
- 大请求对齐到 **2 MiB——x86-64 大页的大小**:透明大页只能把"按 2 MiB 对齐、长 2 MiB"的区间映射成一个大页。
- **`madvise` 在 `memset` 前面**,因为页在第一次被碰时才分配,内核就在那一刻看有没有"想要大页"的标记。先清零,拿到的就是 4 KiB 小页,只能等后台的 `khugepaged` 以后合并——那是不可预测的停顿。`memset` 还顺便把每一页的首次缺页(在 [#5](/zh/posts/spmc-shared-memory-broadcast-ring/) 实测约 1.5 µs 一页)提前付清,不留给热路径。
- 取整掩码 `(n + a - 1) & ~(a - 1)` 只因为 `a` 是 2 的幂才成立;换成 `a = 48`,在 0 到 100,000 之间有 66,672 个值和除法版结果不同。

两笔代价要说出来。超过 16 KiB 的请求一律取整到 2 MiB,一个 20 KiB 的容器要占、要清 2 MiB——适合少量大数组,不适合大量中等容器。THP 加 `madvise` 还依赖系统开关;HFT 部署更常见的是预留显式大页(`MAP_HUGETLB`)、关掉 THP,因为显式更确定。

---

## 5. `#pragma pack` 描述的是外面的世界

```cpp
#pragma pack(push, 1)
struct PackedStruct { char a; int b; double c; };   // 偏移 0、1、5;sizeof 13,alignof 1
#pragma pack(pop)
static_assert(sizeof(PackedStruct) == 13);
```

压紧把第 1 节全反过来:`b` 和 `c` 落在不对齐的地址上,数组元素一路漂移、跨过行边界,指向 `c` 的指针是不对齐的 `double*`(解引用是未定义行为),在这种字段上做原子操作还可能撞上 split lock。取这些地址时编译器不会警告。它的用途是对上外部的字节布局——网络协议、文件格式——不是省内存;用之前先 `memcpy` 到对齐的局部变量里(固定大小的 `memcpy` 会被编译成一条普通 load)。

---

## 6. 数行数,不数字节:AoS 还是 SoA

下面所有布局问题都是同一个问题:**这次访问要碰几条缓存行?**

```cpp
struct Point1 { float x, y, z; };
Point1 points1[1000];                                  // 结构体数组(AoS)

struct Point2 { float x[1000], y[1000], z[1000]; };
Point2 points2;                                        // 数组结构体(SoA)
```

只对 x 求和:AoS 每条行都拖着用不上的 y、z——12,000 字节,**188 条行**。SoA 读一个连续的 4,000 字节数组——**63 条行**。三倍差距就是"每条行里有用的字节只占三分之一"。反过来(同一个点的 x、y、z 一起用),AoS 赢:一条行对三个相隔 4,000 字节的数组。**一个元素的所有成员一起用 → AoS;扫一遍只用部分成员 → SoA。**

两点要小心。12 字节不是 2 的幂,所以 AoS 里每 16 个元素有 2 个跨行(第 1 节);SoA 的 `float` 数组一个都不跨。而且这个例子只有 12 KB,放得进 L1,第一遍之后行数差就不再影响耗时。差距在工作集远大于缓存、或者向量化时才显现——SoA 连续的 float 一条 load 就能装满一个 SIMD 寄存器。

可以用**代理视图**在 SoA 存储上保留 AoS 风格的写法:`operator[]` 返回一个只装"存储指针 + 下标"的小对象,它的访问函数转发到各个数组:

```cpp
#include <cstddef>
#include <vector>

class ParticleSoA;
struct ParticleRef {                                   // 一个"虚拟元素":存储 + 下标
    ParticleSoA* storage;
    size_t index;
    float& x() const;
    float& vx() const;
};

class ParticleSoA {
    std::vector<float> x_, vx_;
    friend struct ParticleRef;
public:
    explicit ParticleSoA(size_t n) : x_(n), vx_(n) {}
    size_t size() const { return x_.size(); }
    ParticleRef operator[](size_t i) { return {this, i}; }
    std::vector<float>& x_array()  { return x_; }      // 热循环直接拿底层数组
    std::vector<float>& vx_array() { return vx_; }
};

inline float& ParticleRef::x()  const { return storage->x_[index]; }
inline float& ParticleRef::vx() const { return storage->vx_[index]; }

void step(ParticleSoA& p) {
    p[0].x() = 10.0f;                                  // 写起来像 AoS
    auto& x = p.x_array(); auto& vx = p.vx_array();
    for (size_t i = 0; i < p.size(); ++i) x[i] += vx[i];   // 跑起来是 SoA
}
```

调用方拿到可读的 AoS 写法;真正在意性能的循环直接走连续数组,SoA 的缓存和 SIMD 收益正是从这里来的。

---

## 7. 用去规范化打断依赖链

规范化的写法,检查一笔订单的风控上限:

```cpp
#include <cstdint>
#include <unordered_map>

struct RiskProfile { uint32_t max_order_size; double max_position_value; };
struct Client      { uint32_t client_id; uint32_t risk_profile_id; };
struct Order       { uint64_t order_id; uint32_t client_id; uint32_t quantity; double price; };

std::unordered_map<uint32_t, RiskProfile> risk_profiles;
std::unordered_map<uint32_t, Client>      clients;
std::unordered_map<uint64_t, Order>       orders;

bool check_risk_normalized(uint64_t order_id) {
    const auto& order  = orders.at(order_id);                      // 缺失 #1
    const auto& client = clients.at(order.client_id);              // 缺失 #2:要等 #1 的结果
    const auto& risk   = risk_profiles.at(client.risk_profile_id); // 缺失 #3:要等 #2 的结果
    return order.quantity <= risk.max_order_size;
}
```

它比"三次缺失"更糟。每次查找的 key 都来自上一次查找读到的数据,乱序执行没法把它们叠起来:**延迟是相加的**。这就是 *pointer chasing*。而且每次 `unordered_map::at` 本身就是先读桶、再读节点。

去规范化把检查要用的字段直接拷进订单:

```cpp
struct EnrichedOrder {
    uint64_t order_id;
    uint32_t quantity;
    double   price;
    uint32_t client_id;
    uint32_t max_order_size;        // 从风控参数拷来
    double   max_position_value;    // 从风控参数拷来
};                                  // 40 字节,原来是 24
std::unordered_map<uint64_t, EnrichedOrder> enriched_orders;

bool check_risk_denormalized(uint64_t order_id) {
    const auto& o = enriched_orders.at(order_id);   // 只查一次
    return o.quantity <= o.max_order_size;
}
```

账单在写的时候来。风控参数一改,要么立刻改掉所有副本——写放大,改到一半还有一致性问题;要么已有订单保留创建时的值(快照语义)。所以判断标准不是"参数改得频不频繁",而是**"副本要不要立刻同步?"** 要立刻同步、订单又多,去规范化就把成本从读搬到了写;能接受快照语义,它通常划算。

---

## 8. `alignas(64)` 是隔离,`alignas(32)` 是打包

```cpp
struct alignas(64) OptimalOrder {
    uint64_t price;        // 最热
    uint32_t quantity;
    uint32_t orderId;
    uint64_t timestamp;    // 较少访问
    char symbol[8];        // 最冷
};                         // 字段共 32 字节;因为 alignas(64),sizeof 是 64
static_assert(sizeof(OptimalOrder) == 64);
```

数据 32 字节,但类型上的 `alignas(64)` 把 `sizeof` 补到了 64。按想要的效果选:

- **一条行放两个、都不跨行:`alignas(32)`。** 不写 `alignas` 时 `alignof` 只有 8,结果取决于数组首地址——落在偏移 16(`malloc` 只保证这么多),每两个就有一个跨行。适合单线程顺序扫和多线程只读。
- **一条行放一个:`alignas(64)`。** 适合不同线程各**写**各的订单;伪共享要有写才会发生,只读共享没有害处。代价是每条行一半是填充。

"按访问频率排字段"只对**大于一条行**的结构体有意义:整条行是一起搬的,32 字节结构体里怎么排都一样。大结构体里,把热字段放在第一条行;冷字段很多时,干脆拆到另一个结构体里(热冷拆分)。

字符串也是同一笔账。内联 `char Name[32]` 的记录是 36 字节——每 16 个有 8 个跨行,扫下标时还得拖着名字。换成 `const char*` 是 16 字节,扫起来紧凑,但读名字要去别处做一次依赖访存。代码也是数据:互相调用的函数应该在指令缓存里挨着放,热路径超过 L1I 时,编译器和链接器用冷热分段、PGO 和 BOLT 来做这件事。

---

## 9. L1D 内部:64 组 × 8 路

现在进到框里面。L1D 不允许任何一条行随便放。

<a href="/images/memory-geometry/l1d-sets.zh.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/l1d-sets.zh.svg" alt="L1D 是一个 64 行 × 8 格的柜子:地址拆成 tag、组号和行内偏移;组号选中一行,8 个 tag 并行比较" loading="lazy" decoding="async"></a>

32 KiB 的 L1D、64 字节一行,能放 512 条行。让一条行随便放(全相联),每次访问都要比 512 个 tag——1 纳秒内做不完。每条行只能放固定一格(直接映射),两条恰好分到同一格的热行就会永远互相踢。折中是**组相联**:512 格排成 **64 组 × 8 路**。地址拆成三段:

- **行内偏移**,bit 0–5:64 字节行里的第几个字节;
- **组号**,bit 6–11:64 组里的哪一组——算出来的,不用找;
- **tag**,bit 12 以上:和这一组 8 路里的 tag 同时比较。

拿地址 10000 = 二进制 `10 011100 010000`:偏移 16,组 28,tag 2。加 4096:`11 011100 010000`——**还是组 28**,tag 变成 3。所以地址相差 4096 整数倍的数据,永远在抢同一组的 8 个格子,第 9 个进来就要踢人,**哪怕另外 63 组全空着**。这个距离叫**关键步长**:缓存大小 ÷ 路数 = 32 KiB ÷ 8 = 4 KiB。这样产生的缺失叫*冲突缺失*,和"装不下"的容量缺失是两回事。同样算,L2(512 KiB、8 路)有 1024 组、关键步长 64 KiB;L3 通常把高位哈希后再选组和切片,规律没这么干净。

为什么恰好 4 KiB?L1 在 TLB 还在翻译地址的**同时**就开始选组(虚拟地址索引、物理地址标记,VIPT)。这要求组号的那几位翻译前后不变,也就是落在页内偏移里。4 KiB 页的页内偏移是 12 位:6 位给字节、6 位给组。所以"组数 × 行大小"被卡在 4 KiB,L1 想做大只能加路数:32 KiB = 4 KiB × 8。苹果 M1 用 16 KiB 页、128 KiB 的 L1D——16 KiB × 8,同一个约束。

---

## 10. 2 的幂步长把一个组挤爆

要认出的模式是:**一起用的数据,地址两两相差关键步长的整数倍,就全挤进同一个组。** 常见的有两种样子。

### 10.1 按列走矩阵

```cpp
int m[64][1024];             // 每行正好 4096 字节
long long sum = 0;
for (int j = 0; j < 1024; ++j)
    for (int i = 0; i < 64; ++i)
        sum += m[i][j];      // 每一步:+4096 字节
```

第 0 列拉进 64 条行——才 4 KiB,L1 有 32 KiB——而每条行里还装着第 1–15 列,接下来十五列本该全命中。可这 64 条行全在**一个组**里,只有 8 路,只留得住最后 8 条,于是几乎每次都缺失。

改法:**按整条行填充**——`int m[64][1040]`(每行 4160 字节)让每一行往后挪一个组,64 行正好铺满 64 组;只填一个 `int`(`[64][1025]`)每行只挪 4 字节,连续 16 行还在同一组,每组 16 条超过 8 路,而且行首也不再按行对齐。或者**分块**:一次处理 8 × 16 的一块,在行被踢出去之前用完它的 16 个 int。或者干脆按行走。

在苹果 M1 MacBook Air 上实测(Apple clang 21,`-O2`,7 次取最快,高 QoS、未绑核)。M1 的参数和 x86 不同——128 KiB 的 L1D、128 字节的行、**关键步长 16 KiB**(8 路按公开规格假定)——所以测试扫一遍行宽,对照组每行多填一条 128 字节的行:

| 行宽(相邻两行地址差) | 按列 ns/次 | 同行宽 + 128 B 填充 | 按行 |
|---|---|---|---|
| 1 KiB | 0.25 | 0.18 | 0.05 |
| 2 KiB | 0.27 | 0.18 | 0.05 |
| 4 KiB | 0.40 | 0.19 | 0.05 |
| 8 KiB | 0.62 | 0.21 | 0.07 |
| **16 KiB**(M1 的关键步长) | **0.81** | 0.20 | 0.06 |
| 32 KiB | 0.78 | 0.20 | 0.06 |

填充那一列是平的:组被打散,行一直留在 L1 里。不填充的随步长变慢,**到 16 KiB 封顶**——4 KiB 时 64 行落进 4 个组(32 格),8 KiB 时 2 个组,16 KiB 起只剩 1 个组 8 格——正是关键步长预言的位置;32 KiB 不更慢,因为已经是"同一组"了。

**为什么只慢 4 倍,不是 20 倍?** 这些数是**吞吐**(总时间 ÷ 次数),不是延迟。每个地址都是算出来的、不依赖读到的值,所以很多缺失能同时在路上;L2 命中约 5 ns,0.81 ns 一次相当于大约六个重叠。而且最大的矩阵 2 MiB,在 M1 的 12 MiB L2 里,被踢出 L1 的行只掉到 L2。换成**有依赖**的读——下一个地址来自上一次读到的值,比如哈希冲突链、订单簿的树——缺失不能重叠,组冲突就暴露完整的延迟。HFT 热路径上的查找多半是后一种。

### 10.2 几个按页对齐的数组一起扫

```cpp
float* a[10];                          // 十个各自单独分配的大数组
for (size_t i = 0; i < n; ++i)
    out[i] = a[0][i] + a[1][i] + a[2][i] + a[3][i] + a[4][i]
           + a[5][i] + a[6][i] + a[7][i] + a[8][i] + a[9][i];
```

大块分配的起点在页内的偏移往往相同(glibc 遇到大请求直接向内核要页,返回"页起点 + 固定头")。于是下标 *i* 处的十个元素 bit 6–11 完全相同——十条行抢 8 路。而且循环轮流访问的行比格子多,"踢最久没用的"规则踢掉的恰好是下一步要用的:每次都缺失。*i* 往后走也没用,十个数组一起挪。

改法是让第 *k* 个数组多错开 *k* 条行:

```cpp
#include <cstdlib>

constexpr int kArrays = 10;
constexpr size_t kLine = 64;
void*  raw[kArrays];
float* arr[kArrays];

void allocate(size_t bytes) {
    for (int k = 0; k < kArrays; ++k) {
        raw[k] = std::aligned_alloc(4096, bytes + 4096);                            // 多要一页
        arr[k] = reinterpret_cast<float*>(static_cast<char*>(raw[k]) + k * kLine);  // 错开 k 条行
    }
}
void release() { for (int k = 0; k < kArrays; ++k) std::free(raw[k]); }             // 用原始指针释放
```

在 M1 上编译运行:十个起点对 4096 取模依次是 0、64……576,组 0 到 9 各占一个。

名字相近的 **L1 bank 冲突**——同一个周期两条 load 落进同一个内部 bank——是端口争用,不是容量问题,而且高度依赖微架构(老的 Intel 核如 Sandy Bridge 明显,新核大多没有)。

---

## 11. 内存条里面:通道、rank、bank、行缓冲

L3 缺失之后,请求交给 CPU 芯片上的内存控制器,再由它去内存条。

<a href="/images/memory-geometry/dram-geometry.zh.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/dram-geometry.zh.svg" alt="内存条内部:内存控制器连两个通道;一个 rank 是 8 颗并排的芯片;每颗芯片 16 个 bank;一个 bank 是一张行表加一个行缓冲,行命中约 14 ns、行空约 28 ns、行冲突约 41 ns" loading="lazy" decoding="async"></a>

**最小单元:bank 和行缓冲。** DRAM 的一个格子只是一个很小的电容加一个开关,电荷太少,单独读不出来。所以一个 **bank**——一张几万行、每行约 1 KiB(一颗芯片里)的表——读的时候先**打开一整行**:把这一行所有格子接到一排放大器上,放大并锁存。锁存住的那一行就是**行缓冲**。要的字节再按列号从里面取。一个 bank 只有一个行缓冲,所以只能开着一行;要读同一个 bank 的另一行,得先把当前这行关掉(预充电)。

**三种情况。** DDR4-3200 CL22 上,开行、读列、关行三个动作各约 22 个时钟 × 0.625 ns ≈ 14 ns:

- **行命中**:那一行已经开着 → 只读列,**约 14 ns**;
- **行空**:这个 bank 没开任何行 → 开行 + 读列,**约 28 ns**;
- **行冲突**:开着的是同一个 bank 的另一行 → 关行 + 开行 + 读列,**约 41 ns**。

再加上控制器排队、片上互连、一路下来的缓存查找,一次完整的 DRAM 访问通常 80–100 ns。

**往上数。** 一个通道 64 位宽;一颗常见的芯片一次出 8 位,所以 **8 颗并排组成一个 rank**,一起响应——一条 64 字节的行是 8 拍 × 8 字节,每颗芯片出 8 字节,大家打开同一个行号、同一个列号。每颗芯片有 16 个 bank(DDR4),各自独立开行,所以内存条能同时处理好几个请求。同一通道上的几个 rank 共用那组线,轮流传。**通道**是互相独立的几组线:带宽 ≈ 通道数 × 单通道带宽,单次访问并不会变快。

**拆地址。** 和 L1 的组号完全一个思路:控制器把物理地址拆成通道、rank、bank、行、列几段。低位给列,所以连续地址落在同一个已开的行里;通道和 bank 的位夹在中间,通常还做哈希。具体映射因平台而异,很少公开。

**按列遍历为什么慢——五层一起吃亏。** `int matrix[31250][2048]`(每行 8 KiB,共 256 MB),往下走一列,每步地址 +8,192 字节:

1. **每条行只用了 1/16**:每步一条新的 64 字节行,只读其中 4 字节。
2. **剩下的等不到被用**:另外 15 个 int 属于后面 15 列,要 31,250 步之后才轮到。一列碰过的行共 2 MB,比 L1、L2 都大,而 8 KiB 步长又让整列在 L1 里挤进一个组、在 L2 里只占 8 个组。
3. **每一步都换一个页**:一列 31,250 个页,TLB 只有一两千项——几乎每次都要查页表。
4. **预取器帮不上**:硬件预取器一般不跨 4 KiB 页。
5. **DRAM 行冲突**:相邻两次访问差 8 KiB,往往落在同一个 bank 的不同行——每次约 41 ns,而不是 14 ns。

按行走把五条全反过来:开一次 DRAM 行服务很多条缓存行,每条行全用上,预取器提前跑,TLB 每 1,024 个 int 才换一次页。行缓冲只是最底下那一层。改法和前面一样:换遍历顺序(或先转置),或者分块。

---

## 12. 刷新:关不掉的尾延迟

DRAM 的电容会漏电,控制器必须定期把每一行读出来再写回。64 ms 内刷完所有行、分 8,192 批,就是大约每 **7.8 µs** 一次刷新命令(tREFI);刷新期间这个 rank 有几百 ns 不能访问(tRFC,8 Gb 的 DDR4 芯片约 350 ns)。350 ÷ 7,800 ≈ **4.5%**:一次随机的 DRAM 访问大约有这么大的概率多等最多几百 ns(按全 bank 刷新估算)。平均值上看不出来,出现在 **P99 和 P99.9** 里。

软件关不掉它。让热数据集留在缓存里,热路径根本不去 DRAM;用支持细粒度刷新或按 bank 刷新的内存,缩短每次阻塞;尾延迟测量里看到周期约 7.8 µs 的毛刺,要想到刷新。

---

## 13. 多通道均衡:让行数互质

通道要同时忙起来,带宽才叠加。控制器把连续地址轮流分到各个通道上(交织)。用最简单的模型,粒度 64 字节:`通道号 = (地址 ÷ 64) mod N`。

4 个通道,一个数组里每个对象 256 字节(4 条行),热路径只读每个对象的**第一条行**:第 *i* 个对象的第一条行是第 4*i* 条,4*i* mod 4 = 0。**所有热行都在通道 0**,另外三个闲着。把对象补到 5 条行(320 字节):5*i* mod 4 依次是 0、1、2、3——四个通道轮着来。

规则:**对象按缓存行取整成 L 条行,让 L 和通道数 N 互质**——2 或 4 个通道时就是让行数为奇数。3 通道天然均衡,因为 2 的幂条行和 3 总是互质。两点现实:真实的控制器大多会把地址高位做异或哈希,恰恰为了打散这类规律,所以先确认平台的映射、再测,别急着手工填充;而且只有受带宽限制的负载才需要操心——留在缓存里的热数据根本到不了通道。

---

## 小结

1. **访问按行付钱。** 对齐让一个值待在一条行里(64 是所有不超过 64 的 2 的幂的倍数);填充让数组保持对齐;成员顺序改变 `sizeof`。
2. **`alignas` 用空间买隔离;`#pragma pack` 为了对上外部格式放弃对齐。** 写在类型上的 `alignas(64)` 还会补齐 `sizeof`,写在成员上只挪起点。堆上要 `aligned_alloc` 加取整后的大小,`new`/`delete` 按同一个对齐配对,要大页就在第一次碰之前 `madvise`。
3. **布局就是数行数。** 扫部分字段用 SoA,整体使用用 AoS;去规范化打断依赖链,判断标准是副本要不要立刻同步;每线程各写一个用 `alignas(64)`,一行放两个用 `alignas(32)`。
4. **地址选定 L1 的组。** 64 组 × 8 路让相差 4 KiB 的地址不管缓存多空都抢 8 个格子;按整条行填充、按整条行错开数组,或者分块。M1 上关键步长 16 KiB 的实测:0.20 → 0.81 ns/次——这是吞吐,有依赖的读会暴露多得多的代价。
5. **DRAM 是行、bank 和通道。** 行命中约 14 ns、行冲突约 41 ns;按列遍历在五层上吃亏;刷新带来软件消除不了的 P99 尾巴;热步长和通道数互质,通道才均衡。
