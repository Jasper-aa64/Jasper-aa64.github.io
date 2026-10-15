---
title: "交易系统笔记 #13：类型双关、函数调用与编译提示"
date: 2026-10-15
slug: "type-punning-calls-compiler-hints"
description: "把 double 当整数改几位，指针强转为什么会读到旧值，memcpy 和 std::bit_cast 为什么不花钱；函数调不进去时参数按调用约定怎么传，小的传值、大的传 const&，递归的尾调用编译器自己会变循环；最后看一组常见的性能辅助宏，每个宏替编译器做了什么决定。汇编是 GCC 16 -O2 在 x86-64 上的实测。"
summary: "编译器能优化到什么程度，取决于它看得见什么、敢假设什么：类型不同就当成不重叠，看不见函数体就照调用约定传参，提示宏是你直接替它做的决定，有的决定并不对。"
chapter: 1
categories: [Systems]
tags: [cpp, type-punning, strict-aliasing, bit-cast, calling-convention, compiler-optimization, hft, low-latency]
toc: true
math: true
light: true
---

编译器能把代码优化到什么程度，取决于它看得见什么、敢假设什么。这一篇的三件事都卡在这上面。把一个 double 当成整数改几位，编译器按“类型不同的指针不会指向同一块内存”来优化，你的改动可能被它当成没发生。一个函数调不进去，参数就得按调用约定一个个摆好，传值还是传引用会差出几条指令，还会让编译器不敢优化。项目里常见的性能辅助宏，每一个都替编译器做了一个决定，有的决定并不对。

## 1. 二进制表示与类型双关：double 怎么存，怎么安全地改它的位

### 1.1 IEEE 754：符号、指数、尾数

double 占 8 字节、64 位，按 IEEE 754 分成三段：最高 1 位是符号，接着 11 位是指数，剩下 52 位是尾数。它表示的值是：

$$x = (-1)^{s} \times 1.f \times 2^{\,e - 1023}$$

$1.f$ 是说尾数前面默认有一个 1，不占位置；指数 $e$ 存的时候加了 1023（偏置），这样就不用存负数。以 100 为例：$100 = 1.5625 \times 2^{6}$，符号存 0，指数存 $6 + 1023 = 1029$，也就是 0x405；1.5625 写成二进制是 1.1001，尾数只存小数点后面的 1001，后面补 0。三段拼起来是 0x4059000000000000：

<svg viewBox="0 0 760 196" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="100.0 这个 double 的 64 位：符号 1 位、指数 11 位、尾数 52 位" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .fbg   { fill: #fbfaf7; }
    .fs    { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.4; }
    .fe    { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.4; }
    .fm    { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.4; }
    .ink   { fill: #1c1b18; font-size: 13px; }
    .muted { fill: #6b6558; font-size: 12px; }
    .bits  { fill: #1c1b18; font-size: 15px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .ttl   { fill: #1c1b18; font-size: 14px; font-weight: 700; }
      :root[data-theme="dark"] .fbg { fill: #17161b; }
      :root[data-theme="dark"] .fs { fill: #4a2f2c; stroke: #8f5a4c; }
      :root[data-theme="dark"] .fe { fill: #33421f; stroke: #8fb257; }
      :root[data-theme="dark"] .fm { fill: #23262c; stroke: #3f4650; }
      :root[data-theme="dark"] .ink { fill: #e9e7ef; }
      :root[data-theme="dark"] .bits { fill: #e9e7ef; }
      :root[data-theme="dark"] .ttl { fill: #e9e7ef; }
      :root[data-theme="dark"] .muted { fill: #a19caf; }
  </style>
  <rect class="fbg" x="0" y="0" width="760" height="196" rx="10"/>
  <text class="ttl" x="24" y="30">100.0 的 64 位（double，IEEE 754）</text>
  <text class="muted" x="40" y="58">第 63 位</text>
  <text class="muted" x="126" y="58">第 62–52 位</text>
  <text class="muted" x="362" y="58">第 51–0 位</text>
  <rect class="fs" x="40" y="66" width="80" height="58" rx="6"/>
  <rect class="fe" x="120" y="66" width="236" height="58" rx="6"/>
  <rect class="fm" x="356" y="66" width="364" height="58" rx="6"/>
  <text class="ink" x="52" y="86">符号</text>
  <text class="bits" x="74" y="112">0</text>
  <text class="ink" x="132" y="86">指数（11 位）</text>
  <text class="bits" x="132" y="112">100 0000 0101</text>
  <text class="ink" x="368" y="86">尾数（52 位）</text>
  <text class="bits" x="368" y="112">1001 0000 0000 … 0000</text>
  <text class="muted" x="40" y="150">0 → 正</text>
  <text class="muted" x="40" y="170">置 1 → 负</text>
  <text class="muted" x="132" y="150">0x405 = 1029</text>
  <text class="muted" x="132" y="170">1029 − 1023 = 6</text>
  <text class="muted" x="368" y="150">前面补上不存的 1：1.1001₂ = 1.5625</text>
  <text class="muted" x="368" y="170">1.5625 × 2⁶ = 100</text>
</svg>

符号单独占最高位，所以只把第 63 位置 1、别的位不动，得到的就是 −100，十六进制 0xC059000000000000。float 的结构一样，只是 1 + 8 + 23 位、偏置 127：2.0f 是 0x40000000，把第 31 位置 1 得到 0xC0000000，就是 −2.0f。

### 1.2 改符号不用碰位：编译器自己就用位运算

既然符号在最高位，改符号、取绝对值都只是一次位运算。但这种事不用自己动手，直接写数学式子，编译器就会编成位运算：

```cpp
double neg(double x)    { return -x; }
double absd(double x)   { return std::fabs(x); }
double negabs(double x) { return -std::fabs(x); }    // 把第 63 位置 1
```

```text
neg(double):
    xorpd   .LC1(%rip), %xmm0    # 和 0x8000000000000000 异或：符号位取反
    ret
absd(double):
    andpd   .LC2(%rip), %xmm0    # 和 0x7FFFFFFFFFFFFFFF 与：符号位清 0
    ret
negabs(double):
    orpd    .LC1(%rip), %xmm0    # 和 0x8000000000000000 或：符号位置 1
    ret
```

`-std::fabs(x)` 就是“把最高位置 1”，一条 `orpd`，值一直待在浮点寄存器里。真正需要把一个数当成一串位来读写的，是另外两种情况：数据本来就是字节，比如交易所二进制行情里的价格字段，要从收包缓冲区里取 8 个字节当成 double；或者要的就是位本身，比如拿 double 的位算哈希、按整数比较大小、做序列化。这时就得把同一块内存当成另一种类型来看。最顺手的写法是指针强转，可它恰恰是错的。

### 1.3 严格别名（strict aliasing）：指针强转为什么会读到旧值

C++ 有一条规则叫**严格别名**：一块内存放的是什么类型的对象，就只能通过这个类型（或者 `char`、`unsigned char`、`std::byte`）去读写它。反过来说，编译器可以假设两个类型不同的指针不会指向同一个对象。这和 [#10](/zh/posts/pointer-memory-access/) 的 `__restrict` 是同一类信息，只是不用你写，编译器按类型自己推出来。有了它，往 `uint64_t*` 写了一个值之后，编译器不用担心哪个 `double` 被改了，`double` 的值可以继续放在寄存器里用，不必重新读内存。

一旦拿 `uint64_t*` 去指一个 `double`，这个假设就不成立了，编译器却照样按它优化：

```cpp
double alias(double* d, uint64_t* u) {
    *d = 1.0;
    *u = 0;          // 编译器认为 u 和 d 指的不是同一个对象
    return *d;       // 所以直接返回 1.0，不重新读
}
```

```text
alias(double*, unsigned long long*):
    movsd   .LC0(%rip), %xmm0    # .LC0 = 1.0
    movsd   %xmm0, (%rdi)        # *d = 1.0
    movq    $0, (%rsi)           # *u = 0
    ret                          # 返回的还是 %xmm0 里的 1.0
```

用 `alias(&x, (uint64_t*)&x)` 调它，实测返回 1，内存里却已经是 0。加 `-fno-strict-aliasing` 关掉这条假设，`return` 前会重新读一次，返回 0。

在同一个函数里直接改，常常能跑出对的结果：`double x = 100;` 之后 `*(uint64_t*)&x |= 0x8000000000000000;`，再打印 `x`，GCC `-O2` 实测是 −100。这是因为两个指针都从 `&x` 来，编译器这次看得出来。可它同时在这一行报了警告 `'x' is used uninitialized`：按 `uint64_t` 读的那块内存，在它看来从没被写过。能跑对，靠的是编译器碰巧看得见，隔一个函数就成了上面的 `alias`。

用 union 读另一个成员也是同样的问题。C 语言允许这样读；C++ 里读的不是最后写入的那个成员，就是未定义行为。GCC 在文档里明确支持通过 union 这样读，所以在 GCC 上能用，换个编译器就不保证了。

### 1.4 `memcpy` 与 `std::bit_cast`：零成本的正确写法

正确的写法是把字节拷进一个目标类型的变量：用 `std::memcpy`，或者 C++20 的 `std::bit_cast`。拷贝听起来要花时间，实际上编译器认得这种固定 8 字节的拷贝，直接编成一条寄存器之间的搬运：

```cpp
uint64_t bits_memcpy(double x) { uint64_t u; std::memcpy(&u, &x, sizeof u); return u; }
uint64_t bits_cast(double x)   { return std::bit_cast<uint64_t>(x); }
```

```text
bits_memcpy(double):
    movq    %xmm0, %rax          # 浮点寄存器里的 64 位原样搬进整数寄存器
    ret
bits_cast(double):
    movq    %xmm0, %rax
    ret
```

两种写法编出来一样。`std::bit_cast` 还会在编译期检查两边一样大、都能按字节拷贝，也能用在 `constexpr` 里。`bits_cast(100.0)` 实测是 0x4059000000000000，和 1.1 算的一样。

从收包缓冲区里读字段也用 `memcpy`：

```cpp
double read_px(const unsigned char* p) { double d; std::memcpy(&d, p, sizeof d); return d; }
uint32_t read_be32(const unsigned char* p) {
    uint32_t v;
    std::memcpy(&v, p, sizeof v);
    return std::byteswap(v);             // 大端字段换成小端
}
```

```text
read_px(unsigned char const*):
    movsd   (%rdi), %xmm0        # 一次 8 字节读
    ret
read_be32(unsigned char const*):
    movl    (%rdi), %eax
    bswap   %eax                 # 翻转字节序
    ret
```

`read_px` 就是一次读，地址不对齐也没关系，x86 允许不对齐的读，实测从缓冲区第 3 个字节开始读也对。写成 `*(double*)p` 又是用 `double` 去读一块 `char` 内存，违反严格别名，地址不对齐时还多一层未定义行为。x86 是小端，低位字节放在低地址；有的交易所协议按大端（网络字节序）发整数，比如 Nasdaq 的 ITCH，读出来要再翻转一次字节序，C++23 的 `std::byteswap` 编出来就是一条 `bswap`。

改位也能这样写，但不一定最好：`std::bit_cast<double>(std::bit_cast<uint64_t>(x) | 0x8000000000000000)` 实测编成三条，`movq` 搬进整数寄存器、`btsq` 置位、再 `movq` 搬回来；1.2 的 `-std::fabs(x)` 只要一条 `orpd`。有现成数学写法的，就写数学式子。

### 1.5 union 的另一种用法：`std::variant`

union 还有另一种用法：一块地方放几种类型里的一种，省内存。比如一条行情消息可能是新增订单、撤单或成交，字段各不相同，用 union 放进同一块内存。问题是 union 不记得现在放的是哪一种，读错了成员，就又回到了 1.3 的双关。C++17 的 `std::variant` 多存一个下标，记住当前是哪种类型：

```cpp
union U3 { int i; float f; std::array<char, 16> a; };    // 16 字节
using V3 = std::variant<int, float, std::array<char, 16>>; // 20 字节
```

实测 `sizeof` 分别是 16 和 20：variant 多了 1 字节的下标，再按 4 字节对齐补齐。`std::get<int>(v)` 在 `v` 里放的不是 `int` 时会抛 `std::bad_variant_access`。按当前类型分发用 `std::visit`：

```cpp
std::variant<int, float> v{42};
std::visit([](auto&& x) { std::cout << x << '\n'; }, v);
```

`std::visit` 编出来就是读下标、比较、跳到对应的分支，和手写一个 `switch` 一样，没有虚函数调用：`std::variant<int, float, double>` 的 visit 实测是一条 `movzbl` 读下标，加两次 `cmp`。

## 2. 调不进去的函数：参数怎么传，递归怎么办

### 2.1 调用约定：参数先放寄存器

函数被内联时，参数怎么传都无所谓，编译器把函数体直接展开在调用的地方。可总有调不进去的时候：函数定义在别的文件或库里，通过函数指针或虚函数调用，递归，或者函数太大编译器不愿意展开。这时参数要按**调用约定**（calling convention）摆好。Linux x86-64 用的 System V 约定：前 6 个整数或指针参数依次放进 `rdi`、`rsi`、`rdx`、`rcx`、`r8`、`r9`，前 8 个浮点参数放进 `xmm0`–`xmm7`，放不下的才压栈；返回值放在 `rax` 或 `xmm0`，大的返回值走 [#11](/zh/posts/rvo-pure-functions/) 讲的那个隐藏地址。

### 2.2 小的传值，大的传 `const&`

按值传一个 `int`，值就在寄存器里；按 `const int&` 传，传进去的是地址，函数里要先读一次内存，调用方还得先把值放进内存，才有地址可传。下面的函数都标了 `noinline`，模拟调不进去的情况：

```cpp
[[gnu::noinline]] int use_val(int x)        { return x * 3; }
[[gnu::noinline]] int use_ref(const int& x) { return x * 3; }
int call_val(int a) { return use_val(a + 1); }
int call_ref(int a) { return use_ref(a + 1); }
```

```text
use_val(int):
    leal    (%rdi,%rdi,2), %eax  # x 就在 %edi 里
    ret
use_ref(int const&):
    movl    (%rdi), %eax         # 先按地址读出 x
    leal    (%rax,%rax,2), %eax
    ret
call_val(int):
    addl    $1, %edi
    jmp     use_val(int)         # 参数已经在位，直接跳过去
call_ref(int):
    subq    $16, %rsp            # 开一块栈
    addl    $1, %edi
    movl    %edi, 12(%rsp)       # 把 a + 1 存进栈里，才有地址
    leaq    12(%rsp), %rdi
    call    use_ref(int const&)
    addq    $16, %rsp
    ret
```

结构体也一样。不超过 16 字节、能按字节拷贝的结构体，按值传时会被拆进两个寄存器；再大，调用方就在栈上复制一份：

```cpp
struct Small { double px; int64_t qty; };              // 16 字节
struct Big   { double px; int64_t qty; int64_t id; };  // 24 字节
```

实测 `f_small(Small)` 的两个字段分别从 `xmm0` 和 `rdi` 进来，`f_big(Big)` 从栈上读字段，调用方先在栈上搭了一份 24 字节的副本。所以标量、迭代器、`std::string_view`、`std::span` 这类小东西按值传；`std::vector`、大结构体这种拷一份很贵、也放不进寄存器的，传 `const&`。

### 2.3 `const&` 还会挡住优化：编译器得假设它会变

传引用还有一个看不见的代价：编译器得假设引用指向的值，可能被别的写操作改掉。下面这个缩放函数，`f` 按引用传时，它可能就指向 `v` 里的某个元素，写一次 `v[i]` 就可能改了 `f`，所以每轮都要重新读：

```cpp
void scale_ref(double* v, int n, const double& f) { for (int i = 0; i < n; ++i) v[i] *= f; }
void scale_val(double* v, int n, double f)        { for (int i = 0; i < n; ++i) v[i] *= f; }
```

```text
scale_ref(double*, int, double const&):    # 循环部分
.L9:
    movsd   (%rdi), %xmm0
    mulsd   (%rdx), %xmm0        # 每轮重新从内存读 f
    addq    $8, %rdi
    movsd   %xmm0, -8(%rdi)
    cmpq    %rax, %rdi
    jne     .L9
scale_val(double*, int, double):           # 循环部分
.L13:
    movsd   (%rdi), %xmm0
    addq    $8, %rdi
    mulsd   %xmm1, %xmm0         # f 一直在寄存器 %xmm1 里
    movsd   %xmm0, -8(%rdi)
    cmpq    %rax, %rdi
    jne     .L13
```

多读的那一次多半命中 L1，单看不贵，但它说明编译器不敢把 `f` 当成不变的值。开 `-O3` 想向量化时，GCC 的报告写着“因为可能重叠，循环先分了版本”：先插一段检查 `f` 和 `v` 重不重叠的代码，重叠就走慢的那份。`scale_val` 没有这一步。这和 1.3 是同一件事：编译器敢不敢优化，看它能不能确定两块内存不重叠。

### 2.4 递归：尾调用编译器自己变循环

递归调不进去：函数要调用自己，展开一层还有下一层。每次调用都要在栈上留返回地址、保存寄存器，递归太深还会把栈用完。不过最常见的那部分开销，编译器自己会去掉。函数最后一步才调用自己时（尾调用），调用完不用再回来做事，GCC 直接把这次调用变成一次跳转。前序遍历里遍历右子树的那次调用就是尾调用：

```cpp
void preorder(Node* root) {
    if (root) {
        visit(root);
        preorder(root->left);
        preorder(root->right);   // 最后一步：尾调用
    }
}
```

```text
.L30:                            # GCC -O2 编出来的最内层（节选）
    movq    %r14, %rdi
    call    visit(Node*)
    movq    8(%r14), %rdi        # root->left
    call    preorder(Node*)      # 左子树：真的递归调用
    movq    16(%r14), %r14       # root = root->right
    testq   %r14, %r14
    jne     .L30                 # 右子树：跳回开头，没有 call
```

GCC 还把递归往里展开了好几层。所以手写“把尾递归改成循环”，多半是在重复编译器的工作。真要把递归彻底去掉，就用一个显式的栈，栈用固定大小的数组，别用 `std::stack`，它底下是 `std::deque`，要分配内存。对遍历一棵树来说，调用开销往往还不是大头：每走一步都要等下一个节点从内存里读回来，这是 [#10](/zh/posts/pointer-memory-access/) 讲的指针追逐，节点不在缓存里时，一步就是一次内存延迟。

## 3. 辅助宏：每个宏都替编译器做了一个决定

项目里常有一个头文件，放一堆跨编译器的性能宏。下面这几个很典型（只留了 GCC 那一支）：

```cpp
#define HPC_FAST_BEGIN _Pragma("GCC push_options") \
_Pragma("GCC optimize (\"O3,unroll-loops,associative-math,no-signed-zeros\")")
#define HPC_FAST_END _Pragma("GCC pop_options")

#define HPC_ALIGN(N) __attribute__((aligned(N)))

template <typename To, typename From>
inline const To& bit_cast_ref(const From* ptr) noexcept {
    return *reinterpret_cast<const To*>(ptr);
}
```

### 3.1 `HPC_FAST_BEGIN`：按函数改优化选项，代价是挡住内联

`HPC_FAST_BEGIN` 和 `HPC_FAST_END` 之间的函数改用 `-O3`、展开循环，还放开了浮点加法的结合律。效果是真的：一个 float 求和循环放进去，实测编成了 `addps` 向量加法，放在外面的同一个循环是一次加一个的 `addss`。浮点结合律放开以后结果会变，见 [#12 第 3.2 节](/zh/posts/strength-reduction-arithmetic/)。

代价在内联。GCC 不把优化选项不同的函数互相内联：区域里的函数调区域外的小函数，区域外的调区域里的，实测连一行的 `static inline` 函数都变成了真的 `call`。热路径上到处是这种小函数，取个字段、算个下标，包一层宏反而可能更慢。GCC 文档对 `optimize` 属性也说得直接：它只该用来调试，不适合放进生产代码。要更激进的选项，就给整个文件或整个构建目标加编译选项。

### 3.2 `HPC_ALIGN`：标准里已经有 `alignas`

`HPC_ALIGN(N)` 按编译器换成 `__attribute__((aligned(N)))` 或 `__declspec(align(N))`。C++11 起标准里就有 `alignas(N)`，三家编译器都认，用不着宏。按缓存行对齐有什么用，见 [#6](/zh/posts/alignment-layout-cache-dram-geometry/)。

### 3.3 `bit_cast_ref`：名字叫 bit_cast，做的是指针强转

这类 helper 常被说成“类型安全的 `reinterpret_cast` 替代品”，可函数体就是一次 `reinterpret_cast` 再解引用：拿 `To` 类型的引用去读一块 `From` 类型的内存，正是 1.3 里出错的写法，名字里有 bit_cast 也不会让它变安全。要按位转换，用 `std::bit_cast`（转一个值）或 `memcpy`。要的只是一个指针时，`reinterpret_cast` 本身合法，只是不能拿转出来的指针去读写不是那个类型的对象。
