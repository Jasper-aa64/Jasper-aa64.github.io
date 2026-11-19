---
title: "交易系统笔记 #13：类型双关、函数调用与编译提示"
date: 2026-10-15
lastmod: 2026-11-19
slug: "type-punning-calls-compiler-hints"
description: "编译器按类型假设两块内存不重叠：把收包缓冲区里的字节、double 的位当成另一种类型读时，指针强转会读到旧值，memcpy、std::bit_cast 和 C++23 的 std::start_lifetime_as 才是正确写法，而且都不花钱。函数调不进去时，参数按调用约定传，小的传值、大的传 const&，递归的尾调用编译器自己会变成循环；调得进去时，展不展开由编译器估计，inline 关键字管的是链接，按函数改优化选项反而挡住内联；最后是内联汇编的四段写法。汇编是 GCC 16 -O2 在 x86-64 上的实测。"
summary: "编译器能优化到什么程度，取决于它敢假设什么、看得见什么：类型不同就当成不重叠，所以按别的类型读字节要用 memcpy 或 bit_cast；看不见函数体就照调用约定传参，展不展开由它估计，替它做的决定不一定对。"
chapter: 1
categories: [Systems]
tags: [cpp, type-punning, strict-aliasing, bit-cast, calling-convention, compiler-optimization, hft, low-latency]
toc: true
math: true
light: true
---

编译器能把代码优化到什么程度，取决于它敢假设什么、看得见什么。这一篇的两节各讲一件：

- **编译器假设类型不同的指针不指向同一块内存**：把收包缓冲区里的 8 个字节当成 `double` 读、把 `double` 的位当成整数改，用指针强转来写，编译器照这个假设优化，读到的可能是旧值（第 1 节）。
- **编译器看不见函数体时，只能按调用约定传参，并且往保守的方向假设**：传值还是传引用会差出几条指令，还可能挡住优化。看得见时，展不展开由编译器自己估计；`always_inline`、按函数改优化选项这类替它做的决定，有的反而让代码更慢（第 2 节）。

## 1. 类型双关与严格别名：编译器按类型假设两块内存不重叠 {#type-punning}

### 1.1 类型双关（type punning）：同一块字节，换一种类型去读 {#punning-need}

**类型双关的本质是换一种解释：字节一个不动，只换编译器把它当成什么类型；合法的换法是把字节拷进目标类型的对象，或者明说这里有一个目标类型的对象（1.4），直接换个指针类型去读是未定义行为**。

- **内存里只有字节，类型是编译器的假设**：同样 8 个字节，当 `double` 读还是当 `uint64_t` 读，取到的位一模一样，差别只在编译器怎么理解、能怎么优化。
- **换个指针去读，错在那块地址上没有这个类型的对象**：编译器按 1.2 的严格别名规则，认定不同类型的指针不指向同一块内存，就可能把读写挪走或删掉（1.3）。

交易系统里有两处躲不开它：

```cpp
struct Header { uint32_t seq; uint16_t len; uint16_t type; };   // 8 字节的包头

void on_packet(const unsigned char* buf) {
    // 1. 包头：把缓冲区开头的 8 个字节当成 Header
    const Header* h = reinterpret_cast<const Header*>(buf);
    // 2. 价格：把偏移 8 处的 8 个字节当成 double
    double px = *reinterpret_cast<const double*>(buf + 8);
    handle(h->seq, h->type, px);
}

uint64_t hash_bits(double x) {
    // 3. 把 double 的 64 位当成整数，拿去算哈希
    return *reinterpret_cast<const uint64_t*>(&x) * 0x9E3779B97F4A7C15ull;
}
```

- **收包缓冲区里的字段**：缓冲区是一串 `unsigned char`，包头的几个整数、偏移 8 处的价格都在里面。注释 1、2 直接把这些字节当成 `Header` 和 `double` 读。
- **要的就是位本身**：注释 3 把 `double` 的 64 位当成整数算哈希；按整数比较大小、做序列化也一样。
- **三处都是错的，而且编译器不一定提醒你**：GCC 16.2 开 `-Wall` 实测只对注释 3 报 `dereferencing type-punned pointer will break strict-aliasing rules`，对 1、2 一声不吭。缓冲区是从参数传进来的，编译器不知道那块内存原本是什么类型。

### 1.2 严格别名（strict aliasing）：类型不同，编译器就当它们不重叠 {#alias-rule}

**编译器假设一个对象只会通过它自己的类型被读写，所以两个类型不同的指针不会指向同一块内存。这个假设让值能一直留在寄存器里，代价是双关的代码会被它优化错**。

- **能读写一个 `T` 对象的类型只有几种**：`T` 本身（加不加 `const`、`volatile` 都算）、`T` 对应的有符号或无符号版本，以及 `char`、`unsigned char`、`std::byte`。用别的类型读写就是未定义行为，更多例子见[未定义行为第 3 节](/zh/ref/undefined-behavior/#strict-aliasing)。
- **编译器拿它换优化**：往 `uint64_t*` 写了一个值，编译器确定没有哪个 `double` 被改，`double` 不用重新从内存读；循环的边界、系数也能提到循环外，循环才能向量化。这和 [#10](/zh/posts/pointer-memory-access/) 的 `__restrict` 是同一类信息，只是不用你写，编译器按类型自己推出来。
- **字节类型是例外，也有代价**：`char`、`unsigned char`（`uint8_t` 就是它）能访问任何对象，所以通过字节指针写一次，编译器就得假设别的变量都可能变了，要重新读。热循环里通过 `uint8_t*` 写内存，会让编译器对其他指针都变保守（实测见[未定义行为 3.2](/zh/ref/undefined-behavior/#alias-benefit)）。

### 1.3 违反严格别名：编译器照样按“不重叠”优化，读到旧值 {#alias-violation}

**指针强转改变不了编译器的假设：它仍然认为两个指针指的不是同一个对象，于是不重新读内存，直接用寄存器里的旧值**。

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

- **`*u = 0` 之后，`*d` 没有重新读**：用 `alias(&x, (uint64_t*)&x)` 调它，实测返回 1，内存里却已经是 0。加 `-fno-strict-aliasing` 关掉这条假设，就会重新读、返回 0；Linux 内核就是整体关掉它编译的，代价是 1.2 的那些优化全没了。
- **同一个函数里强转有时能跑对，那是碰巧**：`double x = 100;` 之后写 `*(uint64_t*)&x |= 0x8000000000000000;`，GCC `-O2` 实测打印 −100，因为编译器这次看得出两个指针都从 `&x` 来；它同时在这一行报了 `'x' is used uninitialized`。中间隔一个函数，就成了上面的 `alias`。
- **union 读另一个成员、`bit_cast_ref` 这类 helper，都是同一件事**：C++ 里读的不是最后写入的那个 union 成员，就是未定义行为（GCC 作为扩展支持，别的编译器不保证）；`bit_cast_ref<To>(ptr)` 的函数体就是 `*reinterpret_cast<const To*>(ptr)`，名字里有 bit_cast 也不会让它变安全。
- **`reinterpret_cast` 本身没错**：错的是拿转出来的指针去读写不是那个类型的对象。只转指针、用之前再转回原来的类型，没有问题。

### 1.4 合法写法：把字节拷进目标类型，或者明说这里有一个对象 {#alias-fix}

**合法的写法只有两类：把字节拷进一个目标类型的变量（`memcpy`、`std::bit_cast`），或者明确告诉编译器这块字节上开始了一个对象（`std::start_lifetime_as`）。两类编出来都是一条读，不花钱**。

1. **拷进变量：`memcpy` 和 `std::bit_cast`**

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

   - **拷贝不花钱**：长度是编译期常量、又小时，编译器直接编成一条寄存器之间的搬运，两种写法编出来一样。
   - **`std::bit_cast` 多了编译期检查**：两边要一样大、都能按字节拷贝，否则编译不过；它也能用在 `constexpr` 里。`bits_cast(100.0)` 实测是 0x4059000000000000，1.5 会把这个数拆开看。

2. **收包缓冲区的字段：同样用 `memcpy`**

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

   - **一次读就够，地址不对齐也行**：x86 允许不对齐的读，实测从缓冲区第 3 个字节开始读也对。写成 `*(double*)p`，除了违反严格别名，地址不对齐时还多一层未定义行为。
   - **大端字段要翻转字节序**：有的交易所协议按大端（网络字节序）发整数，比如 Nasdaq 的 ITCH；x86 是小端，C++23 的 `std::byteswap` 编出来就是一条 `bswap`。

3. **整个结构体就地用：C++23 的 `std::start_lifetime_as`**

   ```cpp
   uint32_t seq_of(unsigned char* p) {
       return std::start_lifetime_as<Header>(p)->seq;   // p 处从现在起有一个 Header
   }
   ```

   - **不拷贝、不调构造函数**：只告诉编译器，这块内存上从现在起有一个 `Header`，原来的字节就是它的值；之后通过返回的指针读写是合法的。GCC 16.2 实测和 `memcpy` 一样，只有一条 4 字节读。
   - **用在大结构体和别人写好的内存上**：几百字节的行情快照逐字段 `memcpy` 太啰嗦，整个拷出来编译器不一定省得掉；网卡 DMA 进来的包、共享内存里的结构体，都是“字节已经在那里，只差一个对象”。
   - **有两个前提**：`Header` 要是隐式生存期类型（implicit-lifetime type，只有标量成员、没有自定义析构函数的结构体就是）；地址要按 `alignof(Header)` 对齐，不对齐还是只能 `memcpy`。用之前查 `__cpp_lib_start_lifetime_as` 这个宏，GCC 16.2 的 libstdc++ 已经有了。

### 1.5 IEEE 754：改符号用不着双关 {#ieee754}

**double 的符号单独占最高位，所以取反、取绝对值都只是一次位运算；直接写数学式子，编译器自己就编成位运算，比手写双关还少两条指令**。

- **64 位分三段**：最高 1 位是符号，接着 11 位是指数，剩下 52 位是尾数。它表示的值是：

$$x = (-1)^{s} \times 1.f \times 2^{\,e - 1023}$$

- **尾数前面默认有一个 1，不占位置**：存的只是 $1.f$ 里小数点后面的部分。
- **指数存的时候加了 1023（偏置）**：这样就不用存负数。
- **例子：100 存成 0x4059000000000000**：$100 = 1.5625 \times 2^{6}$，符号存 0；指数存 $6 + 1023 = 1029$，也就是 0x405；1.5625 写成二进制是 1.1001，尾数只存小数点后面的 1001，后面补 0。

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
      :root:is([data-theme="dark"], [data-theme="black"]) .fbg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fs { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fe { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fm { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ink { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .bits { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .muted { fill: #a19caf; }
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

- **只改最高位就是取反**：第 63 位置 1、别的位不动，得到 −100，也就是 0xC059000000000000。float 的结构一样，只是 1 + 8 + 23 位、偏置 127：2.0f 是 0x40000000，−2.0f 是 0xC0000000。
- **改符号、取绝对值，直接写数学式子**：

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

- **`-std::fabs(x)` 就是一条 `orpd`**：值一直待在浮点寄存器里。
- **手写 `bit_cast` 改位反而是三条**：`std::bit_cast<double>(std::bit_cast<uint64_t>(x) | 0x8000000000000000)` 实测编成 `movq` 搬进整数寄存器、`btsq` 置位、再 `movq` 搬回来。1.4 的写法留给数据本来就是字节、或者要的就是位本身的时候。

### 1.6 `std::variant`：union 不记得自己放的是什么，variant 记得 {#variant}

**union 让一块内存放几种类型里的一种，但它不记得现在放的是哪种，读错成员就是 1.3 的双关；`std::variant` 多存一个下标记住类型，代价是几个字节和一次按下标的分派**。

- **典型用途是行情消息**：一条消息可能是新增订单、撤单或成交，字段各不相同，放进同一块内存省地方。

```cpp
union U3 { int i; float f; std::array<char, 16> a; };    // 16 字节
using V3 = std::variant<int, float, std::array<char, 16>>; // 20 字节
```

- **variant 多了几个字节**：实测 `sizeof` 分别是 16 和 20，下标占 1 字节，再按 4 字节对齐补齐。
- **取错类型会抛异常**：`std::get<int>(v)` 在 `v` 里放的不是 `int` 时，抛 `std::bad_variant_access`。
- **按当前类型分发用 `std::visit`**：

```cpp
std::variant<int, float> v{42};
std::visit([](auto&& x) { std::cout << x << '\n'; }, v);
```

- **`std::visit` 不走虚函数**：编出来就是读下标、比较、跳到对应的分支，和手写 `switch` 一样。`std::variant<int, float, double>` 的 visit 实测是一条 `movzbl` 读下标，加两次 `cmp`。

## 2. 函数调用与内联：看不见函数体时怎么传参，看得见时谁决定展开 {#calls}

### 2.1 调用约定（calling convention）：参数先放寄存器 {#calling-convention}

- **函数被内联时，参数怎么传都无所谓**：编译器把函数体直接展开在调用的地方。
- **有几种情况调不进去**：函数定义在别的文件或库里，通过函数指针或虚函数调用，递归，或者函数太大、编译器不愿意展开。
- **调不进去时，参数按调用约定摆好**：Linux x86-64 用 System V 约定，前 6 个整数或指针参数依次放进 `rdi`、`rsi`、`rdx`、`rcx`、`r8`、`r9`，前 8 个浮点参数放进 `xmm0`–`xmm7`，放不下的才压栈。
- **返回值放在 `rax` 或 `xmm0`**：大的返回值走 [#11](/zh/posts/rvo-pure-functions/) 讲的那个隐藏地址。

### 2.2 小的传值，大的传 `const&` {#pass-by}

1. **按引用传一个 `int`，调用两边各多一步内存操作**

   下面的函数都标了 `noinline`，模拟调不进去的情况：

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

   - **按值传，值就在寄存器里**：`use_val` 直接拿 `%edi` 算，`call_val` 算完 `a + 1` 参数已经在位，一条 `jmp` 跳过去。
   - **按 `const int&` 传，传进去的是地址**：`use_ref` 要先读一次内存；`call_ref` 还得先开栈、把 `a + 1` 存进去，才有地址可传。

2. **结构体：不超过 16 字节的拆进寄存器，再大就在栈上复制一份**

   ```cpp
   struct Small { double px; int64_t qty; };              // 16 字节
   struct Big   { double px; int64_t qty; int64_t id; };  // 24 字节
   ```

   - **`f_small(Small)` 的两个字段分别从 `xmm0` 和 `rdi` 进来**：不超过 16 字节、能按字节拷贝的结构体，按值传时被拆进两个寄存器。
   - **`f_big(Big)` 从栈上读字段**：实测调用方先在栈上搭了一份 24 字节的副本。
   - **所以小东西按值传，拷一份很贵的传 `const&`**：标量、迭代器、`std::string_view`、`std::span` 按值传；`std::vector`、大结构体这种拷一份很贵、也放不进寄存器的，传 `const&`。

### 2.3 `const&` 还会挡住优化：编译器得假设它会变 {#const-ref-alias}

- **引用指向的值，可能被别的写操作改掉**：下面这个缩放函数，`f` 按引用传时，它可能就指向 `v` 里的某个元素，写一次 `v[i]` 就可能改了 `f`，所以每轮都要重新读。

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

- **多读的那一次多半命中 L1，单看不贵**：但它说明编译器不敢把 `f` 当成不变的值。
- **开 `-O3` 想向量化时，循环要先分版本**：GCC 的报告写着“因为可能重叠，循环先分了版本”，先插一段检查 `f` 和 `v` 重不重叠的代码，重叠就走慢的那份；`scale_val` 没有这一步。
- **这和 1.2 是同一个问题，只是类型帮不上忙**：严格别名让编译器按类型断定不重叠，可 `f` 和 `v` 都是 `double`，只有按值传（或者加 `__restrict`），编译器才能确定两者不重叠。

### 2.4 递归：尾调用编译器自己变循环 {#tail-call}

- **递归调不进去**：函数要调用自己，展开一层还有下一层。每次调用都要在栈上留返回地址、保存寄存器，递归太深还会把栈用完。
- **尾调用的开销，编译器自己会去掉**：函数最后一步才调用自己时（尾调用），调用完不用再回来做事，GCC 直接把这次调用变成一次跳转。前序遍历里遍历右子树的那次调用就是尾调用：

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

- **GCC 还把递归往里展开了好几层**：所以手写“把尾递归改成循环”，多半是在重复编译器的工作。
- **真要彻底去掉递归，用固定大小的数组做显式栈**：别用 `std::stack`，它底下是 `std::deque`，要分配内存。
- **遍历树时，调用开销往往不是大头**：每走一步都要等下一个节点从内存里读回来，这是 [#10](/zh/posts/pointer-memory-access/) 讲的指针追逐；节点不在缓存里时，一步就是一次内存延迟。

### 2.5 `inline`：这个关键字管的是链接，不是内联 {#inline}

前面几节讲的都是调不进去的函数。反过来，函数调得进去，也就是被内联（展开）时，参数怎么摆都无所谓。可决定展不展开的，并不是 `inline` 这个关键字。**`inline` 有两个含义，共用一个词：一个是语言规则，一定生效；一个是给编译器的提示，编译器可以不听**。

1. **第一个含义：允许同一个定义在多个 `.cpp` 里各出现一次**
   - **函数定义写在头文件里，被两个 `.cpp` 包含，链接时就有两份同名定义**：链接器报 `multiple definition`，因为它不知道该留哪一份。
   - **标上 `inline`，就是告诉链接器这几份是同一个定义，留一份就行**：同一个头文件，GCC 16 实测不加 `inline` 链接报错，加了就通过。
   - **类里直接写出函数体的成员函数、函数模板，都隐式是 `inline`**：所以只有头文件的库（header-only）也能链接通过。
   - **C++17 的 `inline` 变量把这条规则扩展到全局变量**：头文件里写 `inline int counter = 0;`，所有 `.cpp` 用的都是同一个对象，实测两个 `.cpp` 里取到的地址相同。以前要在头文件里写 `extern` 声明，再挑一个 `.cpp` 写定义。

2. **第二个含义：建议编译器把调用处换成函数体，但编译器按自己的估计决定**
   - **展开省的不只是调用本身**：参数不用按 2.1 的约定摆，没有 `call` 和 `ret`。更值钱的是，展开以后函数体和调用处能放在一起优化：常量能传进去，分支能删掉，循环能向量化。
   - **`-O2` 起，编译器按自己的成本估计决定展不展开**：没标 `inline` 的小函数照样展开，标了的大函数照样不展开。看不见函数体的一定展不开，比如定义在别的 `.cpp` 里、又没开 LTO。
   - **所以同一个函数可能“必须标 `inline`，却没被展开”**：两个含义各管各的。

3. **真要编译器听你的：`always_inline`、`flatten`，以及反方向的 `noinline`**
   - **`__attribute__((always_inline))`**：这个函数在每个调用处都必须展开。用在 profile 过、确认编译器判断错了的小函数上。
   - **`__attribute__((flatten))`**：把这个函数里调用的函数，也尽量一层层展开进来。用在一条又小又热的调用链上。
   - **`noinline` 加 `cold`**：把很少走的错误处理挪出热函数（[#7](/zh/posts/branch-prediction-branch-optimization/)），省出来的是指令缓存。
   - **这几个都是 GCC 和 Clang 的扩展，不是标准 C++**。

4. **按函数改优化选项会挡住内联：`#pragma GCC optimize`**

   ```cpp
   #define HPC_FAST_BEGIN _Pragma("GCC push_options") \
   _Pragma("GCC optimize (\"O3,unroll-loops,associative-math,no-signed-zeros\")")
   #define HPC_FAST_END _Pragma("GCC pop_options")
   ```

   - **项目里常有这样一对宏，夹在中间的函数改用 `-O3`、展开循环、放开浮点加法的结合律**：效果是真的，一个 float 求和循环放进去，实测编成了 `addps` 向量加法，放在外面的同一个循环是一次加一个的 `addss`。浮点结合律放开以后结果会变，见 [#12 第 3.2 节](/zh/posts/strength-reduction-arithmetic/)。
   - **代价在内联：GCC 不把优化选项不同的函数互相内联**：区域里的函数调区域外的小函数，区域外的调区域里的，实测连一行的 `static inline` 函数都变成了真的 `call`。
   - **热路径上到处是这种小函数，包一层宏反而可能更慢**：取个字段、算个下标，每个都多一次调用，展开以后才有的常量传播、删分支也没了。
   - **GCC 文档对 `optimize` 属性说得直接：它只该用来调试，不适合放进生产代码**：要更激进的选项，就给整个文件或整个构建目标加编译选项。

5. **展开太多，热代码反而变慢：指令也占缓存**
   - **L1i 只有 32 KiB 左右，按缓存行装指令**：错误处理被展开进热函数，就算从不执行，它的指令字节也夹在热代码中间，把常跑的指令挤出 L1i。
   - **所以强制展开以后要用 perf 验**：看总耗时，再看 L1i 缺失（`L1-icache-load-misses`）有没有涨。

### 2.6 内联汇编：只写 C++ 表达不了的那几条指令 {#inline-asm}

1. **能不写就不写**
   - **编译器看不进汇编块**：常量传播、寄存器分配，到汇编块的边界就断了。
   - **多数需求已经有现成的写法**：SIMD 有 intrinsics（[#15](/zh/posts/simd-vectorization-intrinsics/)），读 TSC 有 `__rdtsc()`，预取有 `__builtin_prefetch`。

2. **GNU 写法分四段，用冒号隔开：指令、输出、输入、会被改动的东西**

   ```cpp
   static inline uint64_t rdtsc() {
       uint32_t lo, hi;
       asm volatile("rdtsc" : "=a"(lo), "=d"(hi));   // 输出：eax → lo，edx → hi
       return (uint64_t)hi << 32 | lo;
   }
   ```

   - **约束告诉编译器值在哪个寄存器**：`"=a"` 是 `eax`，`"=d"` 是 `edx`，`=` 表示只写。这个函数和 `__rdtsc()` 读到的是同一个计数器（[#20](/zh/posts/tsc-latency-measurement/)）。
   - **第四段漏写，编译器会以为那些寄存器没变**：结果是错的，而且不报错。
   - **第四段写 `"memory"`，表示汇编块会读写内存**：编译器不能把前后的读写挪过它。一行指令都没有的 `asm volatile("" ::: "memory")`，就是常说的编译器屏障。
   - **`volatile` 不让编译器删掉或合并这个汇编块**：读 TSC 每次结果都不一样，不能当成没有副作用的计算。

3. **AVX 和老的 SSE 指令混着用，要在切换前加 `vzeroupper`**
   - **不加的话，CPU 要保存和恢复向量寄存器的高半部分**：每次几十个周期。
   - 怎么在 perf 里认出它、怎么修，见卡片 {{% bottleneck-ref "missing-vzeroupper" %}}。
