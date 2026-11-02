---
title: "对象布局：对齐、填充、vptr 和 vtable"
date: 2026-11-02
slug: "object-layout"
description: "一个 C++ 对象在内存里就是一段连续的字节。成员要落在自己的对齐上，编译器就在中间和末尾补填充，所以 sizeof 往往比成员加起来大，调一下顺序就能变小；空类占 1 字节，做基类或标了 [[no_unique_address]] 可以不占。有虚函数的类，每个对象开头多一个 vptr，指向这个类唯一的一张 vtable，表里除了函数地址还有 offset_to_top 和 typeinfo。多继承时对象里有两个 vptr，转成第二个基类的指针，数值会加 16，第二张表里放的是先调整 this 再跳过去的 thunk。最后讲怎么用 sizeof、-fdump-lang-class、pahole 和 gdb 亲眼看到这些。"
summary: "对象的大小 = 成员 + 为对齐补的填充，按从大到小排成员填充最少；空类做基类可以不占空间。有虚函数时对象只多一个 8 字节的 vptr，函数再多也只是表变长；vtable 每个类一张，放在重定位后变只读的 .data.rel.ro。多继承时第二个基类子对象有自己的 vptr，转换指针要加偏移，经它调用的虚函数要先过一个调整 this 的 thunk。"
toc: true
group: cpplinux
weight: 104
aliases: ["/posts/object-layout/"]
---

`sizeof` 一个结构体，结果常常比成员大小加起来要大；一个什么成员都没有的空类，`sizeof` 是 1；一个类加了虚函数，每个对象就大了 8 字节；多继承时把派生类指针转成第二个基类的指针，指针的数值会变。这几件事背后是同一个问题：编译器怎么把一个对象摆进一段连续的字节里。这篇把它们一个个画在字节格子上，数字都按 x86-64 Linux 上的 Itanium C++ ABI（GCC 和 Clang 都用它），用 GCC 16 编译实测。

## 1. 对齐和填充：sizeof 为什么比成员加起来大

### 1.1 对齐（alignment）：一个类型的地址必须是几的倍数

内存按 64 字节一条缓存行搬进 CPU（[硬件地图：一次读怎么走](/zh/ref/cpu-memory/#load)）。一个 8 字节的 `int64_t` 如果放在 8 的倍数地址上，它一定整个落在同一条行里，一次就读完；要是放在地址 60，就会跨两条行，一次读要碰两条，x86 上能跑但更慢，一些老的 ARM 和别的架构上直接出错，原子操作跨行在 x86 上也会变得极慢。所以 ABI 给每个类型规定了对齐：它的地址必须是这个数的倍数。基本类型的对齐就是自己的大小，`char` 是 1，`int32_t` 是 4，`int64_t`、`double`、指针是 8，用 `alignof(T)` 可以查到。结构体的对齐取成员里最大的那个。

编译器摆成员时有两条硬规矩：成员按声明顺序排，每个成员的偏移必须是它对齐的倍数。

```cpp
struct Bad {
    char    a;   // 偏移 0
    int64_t b;   // 要 8 的倍数：偏移 8，中间空 7 字节
    char    c;   // 偏移 16
    int32_t d;   // 要 4 的倍数：偏移 20，中间空 3 字节
};
static_assert(sizeof(Bad) == 24 && alignof(Bad) == 8);
static_assert(offsetof(Bad, b) == 8 && offsetof(Bad, d) == 20);
```

成员一共 1 + 8 + 1 + 4 = 14 字节，`sizeof` 却是 24。中间空出来的 7 字节和 3 字节叫填充（padding），里面什么都没有，只是为了让 `b` 和 `d` 落在自己的对齐上。**sizeof 是成员加填充，填充是对齐规则逼出来的。**

### 1.2 末尾填充：为了数组里下一个也对齐

填充不只出现在成员之间，结构体末尾也会补：

```cpp
struct Tail { int64_t b; char c; };   // 8 + 1 = 9，sizeof 却是 16
```

原因在数组。`Tail arr[2]` 里，`arr[1]` 紧跟在 `arr[0]` 后面，地址是 `arr + sizeof(Tail)`。要是 `sizeof` 是 9，`arr[1].b` 就落在 9 的位置，不再是 8 的倍数了。所以编译器把大小向上补到对齐的整数倍，**sizeof 一定是 alignof 的整数倍**，数组里每一个元素才都对齐。

### 1.3 调整顺序：从大到小排，填充最少

填充多少取决于成员的顺序。把 `Bad` 的成员按对齐从大到小重排：

```cpp
struct Good {
    int64_t b;   // 0
    int32_t d;   // 8
    char    a;   // 12
    char    c;   // 13，末尾补 2 字节到 16
};
static_assert(sizeof(Good) == 16);
```

大的在前，后面每个成员的偏移自然就是它对齐的倍数，只剩末尾一点填充。同样四个成员，从 24 字节变成 16 字节。放在一条 64 字节的缓存行上看差别更直观：

<svg viewBox="0 0 760 248" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="同一条 64 字节缓存行：Bad 每个 24 字节，a 后面空 7 字节、c 后面空 3 字节，一条行放下两个多，第三个跨到下一条行；Good 每个 16 字节，只在末尾空 2 字节，一条行正好放 4 个" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ol0bg  { fill: #fbfaf7; }
    .ol0m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.2; }
    .ol0p   { fill: #e4e1da; stroke: #b3ad9f; stroke-width: 1.2; }
    .ol0gh  { fill: #f1efe9; stroke: #cfc9bc; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .ol0ink { fill: #1c1b18; font-size: 12.5px; }
    .ol0mut { fill: #6b6558; font-size: 11.5px; }
    .ol0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .ol0mono{ font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .ol0ln  { stroke: #8c8577; stroke-width: 1.2; fill: none; }
    .ol0edge{ stroke: #b4532f; stroke-width: 1.6; fill: none; stroke-dasharray: 5 4; }
    .ol0red { fill: #b4532f; font-size: 11.5px; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0m { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0p { fill: #2e2c28; stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0gh { fill: #201f1d; stroke: #4a463f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0ink, :root:is([data-theme="dark"], [data-theme="black"]) .ol0ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0ln { stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0edge { stroke: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol0red { fill: #f0a07a; }
  </style>
  <rect class="ol0bg" x="0" y="0" width="760" height="248" rx="10"/>
  <text class="ol0ttl" x="24" y="28">一条 64 字节的缓存行，能放几个</text>
  <text class="ol0mut" x="80" y="52" text-anchor="middle">0</text>
  <text class="ol0mut" x="160" y="52" text-anchor="middle">8</text>
  <text class="ol0mut" x="240" y="52" text-anchor="middle">16</text>
  <text class="ol0mut" x="320" y="52" text-anchor="middle">24</text>
  <text class="ol0mut" x="400" y="52" text-anchor="middle">32</text>
  <text class="ol0mut" x="480" y="52" text-anchor="middle">40</text>
  <text class="ol0mut" x="560" y="52" text-anchor="middle">48</text>
  <text class="ol0mut" x="640" y="52" text-anchor="middle">56</text>
  <text class="ol0mut" x="720" y="52" text-anchor="middle">64</text>
  <text class="ol0ink ol0mono" x="24" y="86">Bad</text>
  <rect class="ol0m" x="80" y="62" width="10" height="38"/>
  <rect class="ol0p" x="90" y="62" width="70" height="38"/>
  <rect class="ol0m" x="160" y="62" width="80" height="38"/>
  <rect class="ol0m" x="240" y="62" width="10" height="38"/>
  <rect class="ol0p" x="250" y="62" width="30" height="38"/>
  <rect class="ol0m" x="280" y="62" width="40" height="38"/>
  <rect class="ol0gh" x="320" y="62" width="240" height="38"/>
  <rect class="ol0gh" x="560" y="62" width="160" height="38"/>
  <text class="ol0ink ol0mono" x="85" y="86" text-anchor="middle">a</text>
  <text class="ol0mut" x="125" y="86" text-anchor="middle">填充 7</text>
  <text class="ol0ink ol0mono" x="200" y="86" text-anchor="middle">b</text>
  <text class="ol0ink ol0mono" x="245" y="86" text-anchor="middle">c</text>
  <text class="ol0ink ol0mono" x="300" y="86" text-anchor="middle">d</text>
  <text class="ol0mut" x="440" y="86" text-anchor="middle">Bad[1]</text>
  <text class="ol0mut" x="640" y="86" text-anchor="middle">Bad[2] 的前 16 字节</text>
  <text class="ol0ink ol0mono" x="24" y="152">Good</text>
  <rect class="ol0m" x="80" y="128" width="80" height="38"/>
  <rect class="ol0m" x="160" y="128" width="40" height="38"/>
  <rect class="ol0m" x="200" y="128" width="10" height="38"/>
  <rect class="ol0m" x="210" y="128" width="10" height="38"/>
  <rect class="ol0p" x="220" y="128" width="20" height="38"/>
  <rect class="ol0gh" x="240" y="128" width="160" height="38"/>
  <rect class="ol0gh" x="400" y="128" width="160" height="38"/>
  <rect class="ol0gh" x="560" y="128" width="160" height="38"/>
  <text class="ol0ink ol0mono" x="120" y="152" text-anchor="middle">b</text>
  <text class="ol0ink ol0mono" x="180" y="152" text-anchor="middle">d</text>
  <text class="ol0ink ol0mono" x="205" y="152" text-anchor="middle">a</text>
  <text class="ol0ink ol0mono" x="215" y="152" text-anchor="middle">c</text>
  <text class="ol0mut" x="320" y="152" text-anchor="middle">Good[1]</text>
  <text class="ol0mut" x="480" y="152" text-anchor="middle">Good[2]</text>
  <text class="ol0mut" x="640" y="152" text-anchor="middle">Good[3]</text>
  <path class="ol0edge" d="M720,58 L720,172"/>
  <text class="ol0red" x="728" y="86">跨行</text>
  <rect class="ol0m" x="80" y="190" width="14" height="14"/>
  <text class="ol0mut" x="100" y="202">成员</text>
  <rect class="ol0p" x="150" y="190" width="14" height="14"/>
  <text class="ol0mut" x="170" y="202">填充</text>
  <rect class="ol0gh" x="220" y="190" width="14" height="14"/>
  <text class="ol0mut" x="240" y="202">数组里后面的元素</text>
  <text class="ol0ink" x="80" y="232">Bad 一条行放 2 个多，第 3 个跨到下一条行；Good 正好放 4 个，一个都不跨。</text>
</svg>

一百万个元素的数组，`Bad` 占 24 MB，`Good` 占 16 MB，从头扫一遍要搬的缓存行也少三分之一。所以定义结构体时，**按对齐从大到小排成员，是不花任何代价的省空间办法**。

但大小不是唯一要考虑的。经常一起读写的成员放在一起，读一个时另一个已经跟着进了缓存；反过来，两个线程各写各的成员，如果它们挤在同一条行里，这条行会在两个核之间来回搬（[缓存行乒乓](/zh/ref/cpu-memory/#cross-core)），这时要故意加填充把它们隔开，`alignas(64)` 就是干这个的：

```cpp
struct Counter { alignas(64) int64_t n; };   // 每个 Counter 独占一条行
static_assert(sizeof(Counter) == 64);
```

还有一个方向相反的工具：`#pragma pack(1)` 或 `__attribute__((packed))` 去掉所有填充，`Bad` 会变成 14 字节。代价是 `b` 落在偏移 1，不再对齐，编译器访问它要生成能处理不对齐的代码，取 `&p.b` 当普通的 `int64_t*` 用也不安全。它只适合描述网络包头、文件格式这类字节排布由外部规定的数据。

### 1.4 空类：sizeof 是 1，做基类时可以是 0

一个没有任何成员的类，`sizeof` 是 1，不是 0。C++ 要求两个不同的对象地址不同：`Empty a, b;` 里 `&a != &b`，`Empty arr[10]` 里每个元素地址都不一样。大小是 0 就做不到，所以编译器给它 1 个字节，里面什么都不存。

这 1 字节放进别的结构体里，还会带出填充：

```cpp
struct Empty {};
struct WithEmpty { Empty e; int x; };        // e 占 1，补 3，x 在 4：共 8
struct EboBase : Empty { int x; };           // 4
struct NUA { [[no_unique_address]] Empty e; int x; };   // 4（C++20）
static_assert(sizeof(Empty) == 1 && sizeof(WithEmpty) == 8);
static_assert(sizeof(EboBase) == 4 && sizeof(NUA) == 4);
```

空类当基类时，编译器可以让它和派生类的第一个成员共用地址，不占空间，这叫空基类优化（empty base optimization，EBO）。C++20 的 `[[no_unique_address]]` 把同样的待遇给了成员：标了它的空成员可以不占空间。**空类单独存在要占 1 字节，嵌进别人里面可以占 0。**

标准库到处在用这一点。`std::unique_ptr<int, Del>` 带一个没有成员的删除器，大小仍然是 8，和裸指针一样，删除器没有多占一个字节；容器里存的分配器也一样。MSVC 不认 `[[no_unique_address]]`，要写 `[[msvc::no_unique_address]]`，跨平台的代码要注意。

## 2. 带虚函数的对象：多出一个 vptr

### 2.1 vptr：对象开头的 8 字节

虚函数调用怎么找到函数、要付哪些代价，[虚函数](/zh/ref/virtual-functions/)那篇讲过：每个对象开头藏一个 vptr，指向自己那个类的 vtable，调用时读 vptr、再从表里读函数地址、跳过去。这里只看它在对象里占了哪：

```cpp
struct V {
    virtual ~V() = default;
    virtual void f() {}
    int a;   // 偏移 8
    int b;   // 偏移 12
};
struct V1 { virtual void f() {} int a; };   // 8 + 4，末尾补 4：16
static_assert(sizeof(V) == 16 && sizeof(V1) == 16);
```

vptr 是一个指针，占 8 字节、要 8 对齐，编译器把它放在偏移 0，成员接在后面。`V1` 只有一个 `int`，也是 16 字节，因为对齐变成了 8，末尾要补齐。虚函数的地址都在表里，表每个类只有一张，所以**对象里只多一个指针，虚函数再多也只是表变长**。

### 2.2 vtable 里有什么：offset_to_top、typeinfo、函数地址

`g++ -fdump-lang-class -c v.cpp` 会把每个类的布局和 vtable 写进一个 `.class` 文件，`V` 的那一段是：

```text
Vtable for V
V::_ZTV1V: 5 entries
0     (int (*)(...))0
8     (int (*)(...))(& _ZTI1V)
16    (int (*)(...))V::~V
24    (int (*)(...))V::~V
32    (int (*)(...))V::f

Class V
   size=16 align=8
V (0x...) 0
    vptr=((& V::_ZTV1V) + 16)
```

最后一行说明 vptr 不指向表头，而是指向偏移 16，也就是第一个函数那一格。这一格叫地址点（address point），虚函数按声明顺序从这里往后排，调用时用"vptr + 8 × 序号"取地址。地址点前面还有两格：

- **vptr[-1]：typeinfo 指针**，指向这个类的 `type_info` 对象。`typeid(*p)` 和 `dynamic_cast` 都要先通过它知道对象的实际类型。
- **vptr[-2]：offset_to_top**，这个 vptr 离整个对象开头有多远。单继承时永远是 0，到多继承才用得上（3.3）。

析构函数占了两格，因为它有两个版本：完整析构（GCC 符号里的 `D1`）只析构对象、不释放内存，用在栈上的对象和成员上；带 delete 的析构（`D0`）先调 `D1`，再调 `operator delete` 释放内存。`delete p` 时 `p` 可能是基类指针，要释放多大的内存、调谁的 `operator delete`，只有实际类型知道，所以"析构 + 释放"整个都要走虚调用，就得在表里单独占一格。

<svg viewBox="0 0 760 284" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="对象 v 有 16 字节：偏移 0 是 vptr，8 是 a，12 是 b。vptr 指向 V 的 vtable 里第一个函数那一格；这一格往前依次是 typeinfo 指针和 offset_to_top，往后是两个析构函数和 f。vtable 在 .data.rel.ro 里，typeinfo 指向 typeinfo for V，函数地址指向代码段" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ol1bg  { fill: #fbfaf7; }
    .ol1vp  { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .ol1m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .ol1tb  { fill: #fdf8ec; stroke: #c9a85c; stroke-width: 1.3; }
    .ol1hd  { fill: #f1ece0; stroke: #c9a85c; stroke-width: 1.3; }
    .ol1bx  { fill: #eaf2fb; stroke: #7aa2cf; stroke-width: 1.3; }
    .ol1ink { fill: #1c1b18; font-size: 12.5px; }
    .ol1mut { fill: #6b6558; font-size: 11.5px; }
    .ol1ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .ol1mono{ font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .ol1hl  { stroke: #b4532f; stroke-width: 1.6; fill: none; }
    .ol1ln  { stroke: #6b6558; stroke-width: 1.3; fill: none; }
    .ol1hdr { fill: #b4532f; }
    .ol1hdg { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1vp { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1m { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1tb { fill: #2b2617; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1hd { fill: #24211a; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1bx { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1ink, :root:is([data-theme="dark"], [data-theme="black"]) .ol1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1hl { stroke: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1hdr { fill: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol1hdg { fill: #a19caf; }
  </style>
  <defs>
    <marker id="ol1r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ol1hdr"/></marker>
    <marker id="ol1g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ol1hdg"/></marker>
  </defs>
  <rect class="ol1bg" x="0" y="0" width="760" height="284" rx="10"/>
  <text class="ol1ttl" x="30" y="34">对象 v（栈上或堆上）</text>
  <rect class="ol1vp" x="30" y="50" width="200" height="34"/>
  <text class="ol1mut ol1mono" x="40" y="72">+0</text>
  <text class="ol1ink ol1mono" x="80" y="72">vptr</text>
  <rect class="ol1m" x="30" y="84" width="100" height="34"/>
  <rect class="ol1m" x="130" y="84" width="100" height="34"/>
  <text class="ol1mut ol1mono" x="40" y="106">+8</text>
  <text class="ol1ink ol1mono" x="80" y="106">a</text>
  <text class="ol1mut ol1mono" x="140" y="106">+12</text>
  <text class="ol1ink ol1mono" x="180" y="106">b</text>
  <text class="ol1mut" x="30" y="140">sizeof(V) = 16</text>
  <text class="ol1ttl" x="300" y="34">V 的 vtable（.data.rel.ro）</text>
  <rect class="ol1hd" x="300" y="50" width="240" height="30"/>
  <rect class="ol1hd" x="300" y="80" width="240" height="30"/>
  <rect class="ol1tb" x="300" y="110" width="240" height="30"/>
  <rect class="ol1tb" x="300" y="140" width="240" height="30"/>
  <rect class="ol1tb" x="300" y="170" width="240" height="30"/>
  <text class="ol1mut ol1mono" x="310" y="70">−16</text>
  <text class="ol1ink" x="350" y="70">offset_to_top = 0</text>
  <text class="ol1mut ol1mono" x="310" y="100">−8</text>
  <text class="ol1ink" x="350" y="100">typeinfo 指针</text>
  <text class="ol1mut ol1mono" x="310" y="130">0</text>
  <text class="ol1ink" x="350" y="130">~V()，完整析构 D1</text>
  <text class="ol1mut ol1mono" x="310" y="160">+8</text>
  <text class="ol1ink" x="350" y="160">~V()，带 delete 的 D0</text>
  <text class="ol1mut ol1mono" x="310" y="190">+16</text>
  <text class="ol1ink" x="350" y="190">f()</text>
  <path class="ol1hl" d="M230,67 L262,67 L262,125 L297,125" marker-end="url(#ol1r)"/>
  <rect class="ol1bx" x="566" y="50" width="184" height="50" rx="6"/>
  <text class="ol1ink" x="578" y="72">typeinfo for V</text>
  <text class="ol1mut" x="578" y="90">typeid、dynamic_cast 用</text>
  <rect class="ol1bx" x="566" y="120" width="184" height="80" rx="6"/>
  <text class="ol1ink" x="578" y="142">代码段 .text</text>
  <text class="ol1mut ol1mono" x="578" y="162">V::~V（两个版本）</text>
  <text class="ol1mut ol1mono" x="578" y="182">V::f</text>
  <path class="ol1ln" d="M540,95 L552,95 L552,75 L563,75" marker-end="url(#ol1g)"/>
  <path class="ol1ln" d="M540,125 L563,135" marker-end="url(#ol1g)"/>
  <path class="ol1ln" d="M540,155 L563,158" marker-end="url(#ol1g)"/>
  <path class="ol1ln" d="M540,185 L563,180" marker-end="url(#ol1g)"/>
  <text class="ol1ink" x="30" y="236">vptr 指向第一个函数那一格，往前两格是 offset_to_top 和 typeinfo，往后是虚函数，按声明顺序排。</text>
  <text class="ol1ink" x="30" y="260">一个类只有一张表，所有 V 对象的 vptr 都指向同一处；对象里只多这 8 字节。</text>
</svg>

vtable 放在哪个段也有讲究。表里存的是函数的绝对地址，而程序默认编成位置无关（PIE），`.so` 更是装到哪都行，这些地址要等装载时才知道，得由动态链接器在启动时填进去。所以 vtable 不能直接放在只读的 `.rodata`，而是放在 `.data.rel.ro`：装载时可写，动态链接器把地址填好以后，再用 `mprotect` 改成只读，这一步叫 RELRO（relocation read-only）。[进程地图的段表](/zh/ref/cpp-linux/#segments)里 `.rodata` 那一行写的"重定位后的 vtable"，指的就是它。**vtable 运行时是只读的，改不了；能被改的是对象里的 vptr**，堆溢出把 vptr 覆盖成假表的地址，下一次虚调用就会跳到攻击者想去的地方，这是经典的利用手法。

### 2.3 vptr 什么时候写进去：构造函数一层一层改

vptr 由构造函数写进对象，而且不是一次写好。构造一个 `Derived` 时，先跑 `Base` 的构造函数，它一开头把 vptr 设成 `Base` 的表；`Base` 的构造跑完，轮到 `Derived` 的构造函数，再把 vptr 改成 `Derived` 的表。所以在 `Base` 的构造函数里调虚函数，调到的是 `Base` 的版本：

```cpp
struct Base {
    Base() { hello(); }                          // 这时 vptr 指向 Base 的表
    virtual void hello() { std::puts("Base::hello"); }
    virtual ~Base() = default;
};
struct Derived : Base {
    std::string name = "Derived";
    void hello() override { std::puts(name.c_str()); }
};

int main() { Derived d; d.hello(); }   // 输出 Base::hello，再输出 Derived
```

这是故意的：`Base` 构造时，`Derived` 的成员 `name` 还没构造，要是这时调到 `Derived::hello`，它读的就是一个还不存在的 `std::string`。析构反过来走：`~Derived` 跑完，vptr 被改回 `Base` 的表，再跑 `~Base`，`~Base` 里调虚函数同样只到 `Base` 那一层。**对象在构造和析构的过程中，类型是一层一层变的，vptr 跟着变。**

面试常问的两个"为什么"都从这里来。构造函数不能是虚函数：虚调用要先读对象里的 vptr，而构造之前对象还不存在、vptr 还没写，况且构造时你本来就写明了要造哪个类型，不需要按实际类型分派。基类的析构函数要是虚的：`Base* p = new Derived; delete p;` 时，析构不是虚的，就只会调 `~Base`，`Derived` 的成员没析构，`operator delete` 拿到的大小也是 `Base` 的，结果是未定义行为。

## 3. 继承：基类子对象怎么摆

### 3.1 单继承：基类在前，派生类接着往后排

派生类对象里包着一个完整的基类对象，叫基类子对象，它放在偏移 0，派生类自己的成员接在后面。基类有 vptr 时，派生类直接用这个 vptr，不再另加，它的表也是在基类那张表的基础上改：覆盖了的函数换成自己的地址，新增的虚函数接在后面。所以 `Derived*` 和 `Base*` 指向同一个对象时，**单继承下两个指针的数值一样，转换不用任何指令**。

```cpp
struct V1 { virtual void f() {} int a; };   // 16：vptr 8，a 4，末尾空 4
struct VD : V1 { int c; };                  // 还是 16：c 在偏移 12
static_assert(sizeof(VD) == 16);
```

`VD` 多了一个成员，大小却没变：`c` 被塞进了 `V1` 末尾那 4 字节填充里。`V1` 有虚函数，不是 C++03 意义上的 POD，Itanium ABI 允许派生类复用这种基类末尾的填充。这也说明不能对基类子对象整体 `memcpy` 一个 `sizeof(V1)` 的大小，那会把 `c` 一起覆盖掉。

### 3.2 多继承：两个基类子对象，两个 vptr

两个基类都有虚函数时，派生类对象里就有两个基类子对象，各带一个 vptr：

```cpp
struct BaseA { virtual ~BaseA() = default; virtual void FuncB() {} int a; int b; };
struct BaseB { virtual ~BaseB() = default; virtual void FuncC() {} int a; int b; };
struct Derive : BaseA, BaseB {
    void FuncB() override {}
    void FuncC() override {}
    int c;
};
static_assert(sizeof(BaseA) == 16 && sizeof(Derive) == 40);
```

`BaseA` 子对象在偏移 0，和 `Derive` 共用开头的 vptr；`BaseB` 子对象在偏移 16，带着自己的 vptr；`c` 在 32，末尾补 4 字节到 40。`BaseB` 的成员函数编译时只认识 `BaseB` 的布局：vptr 在偏移 0，`a` 在 8。要让它们能处理 `Derive` 里的那一份，传给它们的指针就必须指向偏移 16。所以把 `Derive*` 转成 `BaseB*`，编译器会生成一条加法：

```asm
_Z2upP6Derive:                  # BaseB* up(Derive* d) { return d; }
        xorl    %edx, %edx
        leaq    16(%rdi), %rax  # d + 16
        testq   %rdi, %rdi
        cmove   %rdx, %rax      # d 是空指针就还返回空指针
        ret
```

空指针转换后必须还是空指针，所以有一次判断；引用不可能为空，转引用就只有那条 `leaq`。**多继承时，同一个对象转成不同基类的指针，数值不一样。** 用 `static_cast` 或隐式转换，编译器知道该加多少；绕过它，比如先转成 `void*` 再转成 `BaseB*`，或者用 `reinterpret_cast`，就没人加这 16，拿到的是一个指错位置的指针。

### 3.3 this 调整：第二张表里放的是 thunk

`BaseB* p = &d; p->FuncC();` 时，调用处只知道 `p` 是个 `BaseB*`，于是读 `p` 指向的那个 vptr，也就是偏移 16 的第二个 vptr，从它指的表里取 `FuncC`。可 `Derive::FuncC` 编译时假定 `this` 指向 `Derive` 的开头，读 `c` 用的是 `this + 32`，现在传进来的 `this` 却多了 16。所以第二张表里放的不是 `Derive::FuncC` 本身，而是一小段先把 `this` 改回来的代码，叫 thunk：

```text
Vtable for Derive
Derive::_ZTV6Derive: 11 entries
0     (int (*)(...))0
8     (int (*)(...))(& _ZTI6Derive)
16    (int (*)(...))Derive::~Derive
24    (int (*)(...))Derive::~Derive
32    (int (*)(...))Derive::FuncB
40    (int (*)(...))Derive::FuncC
48    (int (*)(...))-16
56    (int (*)(...))(& _ZTI6Derive)
64    (int (*)(...))Derive::_ZThn16_N6DeriveD1Ev
72    (int (*)(...))Derive::_ZThn16_N6DeriveD0Ev
80    (int (*)(...))Derive::_ZThn16_N6Derive5FuncCEv
```

```asm
_ZThn16_N6Derive5FuncCEv:       # non-virtual thunk to Derive::FuncC()
        subq    $16, %rdi       # this 从 BaseB 子对象退回 Derive 开头
        jmp     .LTHUNK0        # 跳到 Derive::FuncC 的函数体

_ZThn16_N6DeriveD0Ev:           # non-virtual thunk to Derive::~Derive()，D0 版
        subq    $16, %rdi
        movl    $40, %esi       # 按整个 Derive 的大小
        jmp     _ZdlPvm         # operator delete(void*, size_t)
```

`Derive` 的 vtable 其实是一个数组分成两段：前半段给 `BaseA` 子对象和 `Derive` 自己用，后半段给 `BaseB` 子对象用，两个 vptr 各指向一段的地址点。第二段的 offset_to_top 是 −16：从 `BaseB` 子对象往前 16 字节才是整个对象的开头，`dynamic_cast<void*>(p)` 和 `typeid(*p)` 就靠这一格找回完整的对象。

<svg viewBox="0 0 760 372" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Derive 对象 40 字节：偏移 0 到 16 是 BaseA 子对象（vptr、a、b），16 到 32 是 BaseB 子对象（自己的 vptr、a、b），32 是 c，最后补 4 字节。Derive* 和 BaseA* 指向偏移 0，BaseB* 指向偏移 16。第一个 vptr 指向 vtable 前半段，函数直接是 Derive 的实现；第二个 vptr 指向后半段，offset_to_top 是 −16，函数都是先把 this 减 16 再跳过去的 thunk" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ol2bg  { fill: #fbfaf7; }
    .ol2vp  { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .ol2m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .ol2own { fill: #eaf2fb; stroke: #7aa2cf; stroke-width: 1.3; }
    .ol2p   { fill: #e4e1da; stroke: #b3ad9f; stroke-width: 1.3; }
    .ol2tb  { fill: #fdf8ec; stroke: #c9a85c; stroke-width: 1.2; }
    .ol2hd  { fill: #f1ece0; stroke: #c9a85c; stroke-width: 1.2; }
    .ol2ink { fill: #1c1b18; font-size: 12.5px; }
    .ol2mut { fill: #6b6558; font-size: 11.5px; }
    .ol2ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .ol2red { fill: #b4532f; font-size: 12px; font-weight: 700; }
    .ol2mono{ font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .ol2hl  { stroke: #b4532f; stroke-width: 1.6; fill: none; }
    .ol2hdr { fill: #b4532f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2vp { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2m { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2own { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2p { fill: #2e2c28; stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2tb { fill: #2b2617; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2hd { fill: #24211a; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2ink, :root:is([data-theme="dark"], [data-theme="black"]) .ol2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2red { fill: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2hl { stroke: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ol2hdr { fill: #f0a07a; }
  </style>
  <defs>
    <marker id="ol2r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ol2hdr"/></marker>
  </defs>
  <rect class="ol2bg" x="0" y="0" width="760" height="372" rx="10"/>
  <text class="ol2red" x="140" y="30">Derive*、BaseA* 指这里 ↓</text>
  <text class="ol2red" x="332" y="30">BaseB* 指这里（+16）↓</text>
  <text class="ol2ttl ol2mono" x="24" y="94">Derive d</text>
  <rect class="ol2vp" x="140" y="66" width="96" height="44"/>
  <rect class="ol2m" x="236" y="66" width="48" height="44"/>
  <rect class="ol2m" x="284" y="66" width="48" height="44"/>
  <rect class="ol2vp" x="332" y="66" width="96" height="44"/>
  <rect class="ol2m" x="428" y="66" width="48" height="44"/>
  <rect class="ol2m" x="476" y="66" width="48" height="44"/>
  <rect class="ol2own" x="524" y="66" width="48" height="44"/>
  <rect class="ol2p" x="572" y="66" width="48" height="44"/>
  <text class="ol2ink ol2mono" x="188" y="93" text-anchor="middle">vptr</text>
  <text class="ol2ink ol2mono" x="260" y="93" text-anchor="middle">a</text>
  <text class="ol2ink ol2mono" x="308" y="93" text-anchor="middle">b</text>
  <text class="ol2ink ol2mono" x="380" y="93" text-anchor="middle">vptr</text>
  <text class="ol2ink ol2mono" x="452" y="93" text-anchor="middle">a</text>
  <text class="ol2ink ol2mono" x="500" y="93" text-anchor="middle">b</text>
  <text class="ol2ink ol2mono" x="548" y="93" text-anchor="middle">c</text>
  <text class="ol2mut" x="596" y="93" text-anchor="middle">填充</text>
  <text class="ol2mut ol2mono" x="140" y="126" text-anchor="middle">0</text>
  <text class="ol2mut ol2mono" x="236" y="126" text-anchor="middle">8</text>
  <text class="ol2mut ol2mono" x="332" y="126" text-anchor="middle">16</text>
  <text class="ol2mut ol2mono" x="428" y="126" text-anchor="middle">24</text>
  <text class="ol2mut ol2mono" x="524" y="126" text-anchor="middle">32</text>
  <text class="ol2mut ol2mono" x="620" y="126" text-anchor="middle">40</text>
  <text class="ol2mut" x="260" y="148" text-anchor="middle">BaseA 子对象</text>
  <text class="ol2mut" x="452" y="148" text-anchor="middle">BaseB 子对象</text>
  <text class="ol2mut" x="572" y="148" text-anchor="middle">Derive 自己</text>
  <text class="ol2ttl" x="60" y="190">vtable for Derive 前半段</text>
  <text class="ol2ttl" x="420" y="190">后半段（给 BaseB 子对象用）</text>
  <rect class="ol2hd" x="60" y="198" width="270" height="22"/>
  <rect class="ol2hd" x="60" y="220" width="270" height="22"/>
  <rect class="ol2tb" x="60" y="242" width="270" height="22"/>
  <rect class="ol2tb" x="60" y="264" width="270" height="22"/>
  <rect class="ol2tb" x="60" y="286" width="270" height="22"/>
  <rect class="ol2tb" x="60" y="308" width="270" height="22"/>
  <text class="ol2ink" x="70" y="214">offset_to_top = 0</text>
  <text class="ol2ink" x="70" y="236">typeinfo for Derive</text>
  <text class="ol2ink" x="70" y="258">~Derive（D1）</text>
  <text class="ol2ink" x="70" y="280">~Derive（D0）</text>
  <text class="ol2ink" x="70" y="302">FuncB → Derive::FuncB</text>
  <text class="ol2ink" x="70" y="324">FuncC → Derive::FuncC</text>
  <rect class="ol2hd" x="420" y="198" width="300" height="22"/>
  <rect class="ol2hd" x="420" y="220" width="300" height="22"/>
  <rect class="ol2tb" x="420" y="242" width="300" height="22"/>
  <rect class="ol2tb" x="420" y="264" width="300" height="22"/>
  <rect class="ol2tb" x="420" y="286" width="300" height="22"/>
  <text class="ol2ink" x="430" y="214">offset_to_top = −16</text>
  <text class="ol2ink" x="430" y="236">typeinfo for Derive</text>
  <text class="ol2ink" x="430" y="258">thunk：this −16，再跳 ~Derive（D1）</text>
  <text class="ol2ink" x="430" y="280">thunk：this −16，再跳 ~Derive（D0）</text>
  <text class="ol2ink" x="430" y="302">thunk：this −16，再跳 FuncC</text>
  <path class="ol2hl" d="M188,110 L188,168 L40,168 L40,253 L57,253" marker-end="url(#ol2r)"/>
  <path class="ol2hl" d="M380,110 L380,253 L417,253" marker-end="url(#ol2r)"/>
  <text class="ol2ink" x="24" y="356">两个 vptr 指向同一个 vtable 的两段；经 BaseB* 调用的函数先把 this 减 16，再进 Derive 的实现。</text>
</svg>

`D0` 的 thunk 说明了另一件事：`delete` 一个指向 `BaseB` 子对象的指针时，要释放的是从偏移 0 开始、40 字节的整块内存，不是从偏移 16 开始的 16 字节。thunk 先把指针减回去，再按 `Derive` 的大小调 `operator delete`，这就是 2.2 里析构函数要单独占表格的用处。**经第二个基类调用虚函数，要多走一次 thunk 调整 this，第一个基类没有这一步。**

### 3.4 虚继承：菱形里只留一份基类

`VB` 和 `VC` 都继承 `BaseA`，`Diamond` 再同时继承 `VB` 和 `VC`，普通继承下 `Diamond` 里会有两份 `BaseA`，`d.a` 不知道指哪个。虚继承让它们共用一份：

```cpp
struct VB : virtual BaseA { int x; };
struct VC : virtual BaseA { int y; };
struct Diamond : VB, VC { int z; };
static_assert(sizeof(VB) == 32 && sizeof(Diamond) == 48);
```

代价是那一份 `BaseA` 的位置不再固定。它被放到对象末尾，在单独的 `VB` 对象里离开头 16 字节，在 `Diamond` 里的 `VB` 部分看来就是另一个距离，编译 `VB` 的成员函数时根本不知道将来会被嵌在哪种对象里。所以这个距离只能运行时查：Itanium ABI 把它存在 vtable 里 offset_to_top 再往前的一格（vbase_offset），`VB` 的表开头那一格就是 16。访问虚基类的成员要先读 vptr、再读这个偏移、加上，然后才读到成员，比普通成员多两次读。MSVC 的做法不同，它在对象里另放一个虚基类表指针（vbptr）指向单独的一张表，很多资料里的 vbptr、vbtable 说的是 MSVC。**虚继承把"基类在哪"推迟到运行时查，换来菱形里只有一份基类。**

## 4. 自己看：sizeof、-fdump-lang-class、pahole、gdb

### 4.1 static_assert：把布局写成编译期检查

前面的代码都用了 `static_assert(sizeof(...) == ...)`。布局要对外承诺的结构体（写进文件、发到网络、和 C 代码共享），把大小和关键成员的 `offsetof` 写成 `static_assert`，以后有人加了成员、换了编译选项改变了布局，编译直接失败，不会等到运行时才读出乱码。**布局靠 static_assert 钉住，比靠注释说明可靠。**`offsetof` 只保证对标准布局类型有效，有虚函数的类用它，GCC 会给一个 `-Winvalid-offsetof` 警告。

### 4.2 -fdump-lang-class 和 Clang 的对应选项

`g++ -fdump-lang-class -c x.cpp` 生成 `x.cpp.001l.class`（文件名里的编号随版本变），里面是每个类的大小、对齐、基类子对象的偏移和完整的 vtable，2.2、3.3 里贴的就是它。Clang 用 `-Xclang -fdump-record-layouts` 看对象布局，`-Xclang -fdump-vtable-layouts` 看 vtable。

### 4.3 pahole：在编出来的程序里找空洞

`pahole` 在 Linux 上的 `dwarves` 包里，读带 `-g` 编出来的程序里的调试信息，逐个成员列出偏移和大小，在填充的地方标出 hole 有几个字节，最后统计整个结构体占几条缓存行、空洞一共多少。它看的是真正编出来的程序，所以能一次检查整个项目里所有结构体，适合找"哪些结构体值得重排"。

### 4.4 gdb：ptype /o、info vtbl

不想装别的工具，gdb 也能看（同样要 `-g`）。`ptype /o` 把偏移、大小和空洞一起列出来：

```text
(gdb) ptype /o Bad
/* offset      |    size */  type = struct Bad {
/*      0      |       1 */    char a;
/* XXX  7-byte hole      */
/*      8      |       8 */    int64_t b;
/*     16      |       1 */    char c;
/* XXX  3-byte hole      */
/*     20      |       4 */    int32_t d;

                               /* total size (bytes):   24 */
                             }
```

`info vtbl` 顺着对象里的每个 vptr 把表打出来，多继承时能直接看到第二张表里的 thunk；`p d` 会显示每个 vptr 指向 vtable 的哪个位置（下面省略了地址和没初始化的成员值，`p d` 那行换了行）：

```text
(gdb) info vtbl d
vtable for 'Derive' @ 0x... (subobject @ 0x...):
[0]: 0x... <Derive::~Derive()>
[1]: 0x... <Derive::~Derive()>
[2]: 0x... <Derive::FuncB()>
[3]: 0x... <Derive::FuncC()>

vtable for 'BaseB' @ 0x... (subobject @ 0x...):
[0]: 0x... <non-virtual thunk to Derive::~Derive()>
[1]: 0x... <non-virtual thunk to Derive::~Derive()>
[2]: 0x... <non-virtual thunk to Derive::FuncC()>

(gdb) p d
$1 = {<BaseA> = {_vptr.BaseA = 0x... <vtable for Derive+16>, a = ..., b = ...},
      <BaseB> = {_vptr.BaseB = 0x... <vtable for Derive+64>, a = ..., b = ...}, c = ...}
```

`+16` 和 `+64` 正好对上 3.3 那张表：两个 vptr 分别指向前半段和后半段的地址点。**sizeof 告诉你多大，-fdump-lang-class 告诉你编译器打算怎么摆，gdb 告诉你运行起来的对象里实际是什么**，三样对上了，布局就没有猜的成分。

对象摆好以后放在哪一段（栈、堆、`.data`），见[进程地图](/zh/ref/cpp-linux/#segments)；`new` 一个对象时内存从哪来，见 [new 一次走到哪](/zh/ref/new-malloc-page-fault/)。
