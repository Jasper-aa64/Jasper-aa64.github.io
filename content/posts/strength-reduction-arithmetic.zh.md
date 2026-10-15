---
title: "交易系统笔记 #12：强度削弱与算术优化"
date: 2026-10-15
slug: "strength-reduction-arithmetic"
description: "整数除法要 10–90 个周期，加法只要 1 个。常数乘除、2 的幂、重复的表达式，编译器会自己换成便宜的写法；除数到运行时才知道、只有你知道一个数不会是负的、浮点换了结果会变，这几种要你来换。最后讲价格为什么用整数存。汇编是 GCC 16 -O2 在 x86-64 上的实测。"
summary: "编译器只做它能证明结果不变的替换，常数乘除它做得比人好；要人动手的，是它缺信息或者换了结果会变的地方：运行时的除数、符号、浮点。价格用整数存，精确也快。"
chapter: 1
categories: [Systems]
tags: [cpp, strength-reduction, integer-division, floating-point, fixed-point, hft, low-latency]
toc: true
math: true
light: true
---

行情和订单的热路径上全是小算术：价格除以最小变动价位，换成 tick 数；环形队列的下标对容量取余，绕回开头；成交额乘费率，算手续费。每一行都只有一个运算符，CPU 花的时间却差得很远：一次整数加法 1 个周期，一次整数除法要 10–90 个周期。

把贵的运算换成结果相同的便宜写法，叫**强度削弱**（strength reduction）。编译器一直在做这件事，但它只换自己能证明结果不变的。所以要人动手的地方，都是编译器证明不了的：除数要到运行时才知道，一个数不会是负的但只有你知道，或者换了以后浮点结果真的会变。

## 1. 运算延迟：除法为什么贵

要判断一处换不换得值，先得知道各种运算差多少。这些运算都发生在<a href="/maps/hardware-map.zh.html" target="_blank" rel="noopener">硬件地图</a>后端的执行单元里：操作数已经在寄存器里，不用访存，差别全在执行单元算一次要多久。执行单元不止一种，加减和位运算由 ALU（arithmetic logic unit，算术逻辑单元）做，乘法、除法、浮点运算各有自己的电路。一次运算从开始到结果能用的时间（延迟）大约是：

| 运算 | 延迟 |
|---|---|
| 整数加减、位运算、移位 | 1 个周期 |
| 整数乘法 | 3 个周期 |
| 浮点加减、乘法 | 3–5 个周期 |
| 浮点除法、开方 | 10–20 个周期 |
| 整数除法、取余 | 10–90 个周期 |

加法一个周期就出结果。乘法要把好几行部分积加起来，硬件把这件事拆成三步流水做：每一步做完就能接下一条乘法，所以一条乘法要等 3 个周期，但每个周期都能开始一条新的。除法拆不成这样。商只能一轮一轮地求，每一轮都要用上一轮剩下的余数，一轮只出几位。64 位除法要求的位数比 32 位多，轮数就多；近几年的芯片一轮出的位数多，快了不少，所以这个范围很宽。除法器也没法像乘法器那样每个周期接一条新的，前一条没算完，后面的除法多半只能排队。循环里给每个元素除一次，元素之间就算互不依赖，也快不起来。

所以最值得换掉的是除法和取余，其次才是乘法。

## 2. 编译器自己会换的：常数乘除、2 的幂、重复的表达式

乘数、除数是编译期常数时，换成什么是确定的，编译器能证明结果不变，`-O2` 下都会自己换。下面的汇编是 GCC 16 `-O2` 在 x86-64 上的实际输出：第一个参数在 `%edi`（它的 64 位版本叫 `%rdi`），结果放在 `%eax`。

### 2.1 乘以常数：`lea`、移位或一条 `imul`

```cpp
int mul8(int x)   { return x * 8; }
int mul5(int x)   { return x * 5; }
int mul100(int x) { return x * 100; }
```

```text
mul8(int):
    leal    0(,%rdi,8), %eax      # x * 8
    ret
mul5(int):
    leal    (%rdi,%rdi,4), %eax   # x + x * 4
    ret
mul100(int):
    imull   $100, %edi, %eax
    ret
```

`lea`（load effective address）本来是算地址的指令。地址常写成“基址 + 下标 × 1、2、4 或 8”，CPU 有专门的电路一步算完，编译器就借它来乘 2、3、4、5、8、9 这类小常数，1 个周期。乘 100 拆成移位和加法要好几条，不如一条 3 个周期的 `imul`，编译器就直接乘。循环里每轮都要算的 `i * 10`，编译器还会换成每轮加 10，这是 [#9 第 2.2 节](/zh/posts/loop-optimization/)讲的那种强度削弱。

所以手写 `x << 3`、`x + x + x` 换不来什么，编译器本来就会挑最便宜的写法。手写移位还容易踩优先级：`x << 1 + 2` 是 `x << 3`，加法先算。

### 2.2 除以常数：乘一个“魔数”再右移

除以常数也能换成乘法。除以 100 就是乘 $\frac{1}{100}$，只是整数里没有小数。办法是把 $\frac{1}{100}$ 放大 $2^{37}$ 倍，向上取整存成整数 $M$；乘完再右移 37 位，把放大的倍数除回去：

$$\left\lfloor \frac{x}{100} \right\rfloor = \left\lfloor \frac{x \cdot M}{2^{37}} \right\rfloor, \qquad M = \left\lceil \frac{2^{37}}{100} \right\rceil = 1374389535$$

放大的倍数够大，向上取整带来的那点误差就不会让任何一个 32 位的 $x$ 算错，编译器会按除数挑一个够用的位数。

```cpp
unsigned udiv100(unsigned x) { return x / 100; }
```

```text
udiv100(unsigned int):
    movl    %edi, %eax
    imulq   $1374389535, %rax, %rax   # x * M
    shrq    $37, %rax                 # 右移 37 位
    ret
```

一次乘法加一次移位，约 4 个周期（3 + 1），替掉了 10–90 个周期的除法。取余也能这样算：$x \bmod 100 = x - 100 \cdot \lfloor x / 100 \rfloor$，多一次乘法和一次减法。前提是除数在编译期就知道，因为魔数要按它来算。

### 2.3 2 的幂：无符号一条指令，有符号要修正

除数是 2 的幂时更简单：除以 4 就是右移 2 位，对 512 取余就是只留低 9 位，也就是和 511 做与运算。无符号数编译器就是这么换的，有符号数却多出几条：

```cpp
unsigned udiv4(unsigned x)   { return x / 4; }
unsigned umod512(unsigned x) { return x % 512; }
int sdiv4(int x)             { return x / 4; }
```

```text
udiv4(unsigned int):
    movl    %edi, %eax
    shrl    $2, %eax
    ret
umod512(unsigned int):
    movl    %edi, %eax
    andl    $511, %eax
    ret
sdiv4(int):
    testl   %edi, %edi
    leal    3(%rdi), %eax
    cmovns  %edi, %eax        # x 不是负数就用 x，是负数就用 x + 3
    sarl    $2, %eax
    ret
```

多出来的几条是为负数准备的：负数右移和除法的结果不一样。C++ 的整数除法向 0 取整，`-7 / 4` 是 `-1`；右移向负无穷取整，`-7 >> 2` 是 `-2`。所以编译器先给负数加 3，再右移。取余也一样，`-1 % 512` 是 `-1`，`-1 & 511` 却是 `511`，有符号的 `x % 512` 编出来要 6 条指令。

下标、数量这类不会是负数的值，用无符号类型，就只剩一条 `shr` 或 `and`。类型改不了时，C++23 可以写 `[[assume(x >= 0)]]` 告诉编译器，实测 `sdiv4` 也只剩一条 `sar`。这和 [#11](/zh/posts/rvo-pure-functions/) 的纯函数属性一样，是你向编译器做的承诺，说错了就是未定义行为。

### 2.4 公共子表达式与常量折叠：多余的运算直接删掉

除了把运算换便宜，编译器还会把多余的运算删掉。同一个表达式写了几遍，它只算一遍，这叫**公共子表达式消除**（common subexpression elimination，CSE）：`(i * i) + (i * i) + sqrtf(i * i)` 编出来只有一条 `imull`。全由常量组成的表达式，编译期就算完，这叫**常量折叠**（constant folding）：`float scale = sqrt(2.0) * 3.14159;` 编出来就是一个现成的数，运行时既不开方也不乘。布尔代数也一样，`(a && b) || (a && c)` 和 `a && (b || c)` 编出来一模一样。这些都不用手动改写。`constexpr` 的作用是保证在编译期算，`-O2` 下并不会更快。

常数乘除、2 的幂、重复的表达式，编译器都换得比人好，手写移位换不来速度，只会让代码更难读。

## 3. 要你来换的：编译器缺信息，或者换了结果会变

编译器停手的地方有两种：做替换要用的信息它没有，或者换了以后结果真的不一样。

### 3.1 除数到运行时才知道：`div` 省不掉

魔数是按除数算出来的。除数要到运行时才知道，比如从配置里读出的队列容量，编译器就没法提前算，只能发一条 `div`：

```cpp
unsigned wrap_mod_n(unsigned x, unsigned n) { return (x + 1) % n; }
```

```text
wrap_mod_n(unsigned int, unsigned int):
    leal    1(%rdi), %eax
    xorl    %edx, %edx
    divl    %esi              # 10–90 个周期
    movl    %edx, %eax        # 余数在 %edx 里
    ret
```

要省掉它，只能从设计上让除法消失。

**容量取 2 的幂**。容量是 $2^k$ 时，`idx % cap` 可以写成 `idx & (cap - 1)`，容量到运行时才定也只要一条 `and`。[#4 的环形队列](/zh/posts/lock-free-queue-logger-micro-batching/)把容量向上取到 2 的幂、存一个 `mask_ = 容量 - 1`，就是为了这个。

**绕回用比较**。下标每次只加 1 时，`x = (x + 1) % N` 可以写成 `x = (x == N - 1) ? 0 : x + 1`。编译器不会自己这样换：只有 $0 \le x < N$ 时两者才相等，这一点只有你知道。即使 $N$ 是常数，两种写法也差不少：

```cpp
int wrap_mod(int x) { const int N = 100; return (x + 1) % N; }
int wrap_cmp(int x) { const int N = 100; return (x == N - 1) ? 0 : x + 1; }
```

```text
wrap_mod(int):
    addl    $1, %edi
    movslq  %edi, %rax
    movl    %edi, %edx
    imulq   $1374389535, %rax, %rax
    sarl    $31, %edx
    sarq    $37, %rax
    subl    %edx, %eax
    imull   $100, %eax, %edx
    movl    %edi, %eax
    subl    %edx, %eax
    ret
wrap_cmp(int):
    xorl    %edx, %edx
    leal    1(%rdi), %eax
    cmpl    $99, %edi
    cmove   %edx, %eax        # x == 99 时换成 0
    ret
```

`% 100` 已经换成了魔数乘法，但要乘两次，前后还有移位和减法，一条等一条，约 11 个周期（1 + 1 + 3 + 1 + 1 + 3 + 1）。比较的写法里，加 1 和比较同时做，再一条 `cmove`，约 2 个周期。这里也没有分支可猜错：`cmove` 是按条件挑一个值，不跳转，就是 [#7](/zh/posts/branch-prediction-branch-optimization/) 讲过的条件传送。

**同一个除数反复用**。有的除数运行时才知道，但定下来就不再变，比如每个合约的最小变动价位，启动时读一次。那就在启动时按它算好魔数，之后每次除法都是一次乘法加移位。[libdivide](https://libdivide.com/) 就是做这个的库。

### 3.2 浮点：换了以后结果会变

浮点除法也慢，`g / 100.0f` 看着能换成 `g * 0.01f`，编译器却不换：

```cpp
float fdiv100(float g) { return g / 100.0f; }
float fdiv4(float g)   { return g / 4.0f; }
```

```text
fdiv100(float):
    divss   .LC0(%rip), %xmm0    # .LC0 = 100.0f，照样除
    ret
fdiv4(float):
    mulss   .LC1(%rip), %xmm0    # .LC1 = 0.25f，换成了乘法
    ret
```

差别在常数本身。浮点数是二进制的，0.25 是 $2^{-2}$，存得准，除以 4 和乘 0.25 结果完全一样，编译器就换了。0.01 写成二进制是无限循环小数，`0.01f` 存的只是离它最近的数，乘它和除以 100 舍入出来的结果不一定一样：`g = 5` 时，`g / 100` 得 0.0500000007，也就是离 0.05 最近的 float，`g * 0.01f` 却得 0.049999997，差在最后一位。1 到 10000 的整数里，有 2669 个这样不一样。

同样的原因挡住了提公因子。整数的 `a * x + a * y`，编译器自己改成 `a * (x + y)`，省一次乘法；浮点的不改，因为每次乘、加都要舍入，先乘后加和先加后乘，舍入的地方不同，结果可能差最后一位：

```cpp
int   ifactor(int a, int x, int y)       { return a * x + a * y; }
float ffactor(float a, float x, float y) { return a * x + a * y; }
```

```text
ifactor(int, int, int):
    leal    (%rdx,%rsi), %eax    # x + y
    imull   %edi, %eax           # 只乘一次
    ret
ffactor(float, float, float):
    mulss   %xmm0, %xmm1         # a * x
    mulss   %xmm2, %xmm0         # a * y
    addss   %xmm1, %xmm0
    ret
```

`-ffast-math` 允许这类替换，开了它 `g / 100.0f` 也会变成乘法。但它对整个文件生效，还假设程序里不会出现 NaN 和无穷大：开了它，`std::isnan(px)` 实测直接编成 `return false`，检查坏价格的那行代码就这么没了。所以浮点的替换只在你接受这点误差的地方手写。最常见的是循环里每个元素都除以同一个数，先算好倒数再乘：

```cpp
void process(float* v, int n) {
    for (int i = 0; i < n; i++) v[i] /= sqrtf(3.14159f);    // 每个元素一次除法
}
void process_optimized(float* v, int n) {
    const float scale = 1.0f / sqrtf(3.14159f);             // 编译期就算好了
    for (int i = 0; i < n; i++) v[i] *= scale;              // 只剩乘法
}
```

两个函数里的 `sqrtf(3.14159f)` 都在编译期算掉了，但 `process` 的循环里还是 `divps`（一次除 4 个），换成 `process_optimized` 才变成 `mulps`。代价是结果可能和除法差最后一位。[#9 第 4.3 节](/zh/posts/loop-optimization/)里 BatchNorm 先算 `1.0f / sqrtf(var + eps)` 再乘，也是这个取舍。

还有一种结果会变、编译器不能替你省的：float 和 double 混用。

```cpp
float mix_double(float x) { return x * 3.14159; }    // 3.14159 是 double
float pure_float(float x) { return x * 3.14159f; }
```

```text
mix_double(float):
    cvtss2sd  %xmm0, %xmm0       # float 转成 double
    mulsd     .LC4(%rip), %xmm0
    cvtsd2ss  %xmm0, %xmm0       # 乘完再转回 float
    ret
pure_float(float):
    mulss     .LC5(%rip), %xmm0
    ret
```

不带 `f` 的 `3.14159` 是 double，比 `3.14159f` 更接近真正的 3.14159。按规则，`x` 要先转成 double 再乘，乘完舍入回 float，结果可能和用 `3.14159f` 直接乘差最后一位，所以编译器不能省掉这两次转换，开 `-ffast-math` 实测也还在。要的本来就是 float 精度，就写 `3.14159f`。2.4 里 `sqrt(2.0) * 3.14159` 那种全是常量的写法，编译期就算完了，看不出这个代价；乘的是变量，才会每次都多两次转换。

## 4. 价格用整数：精确，也快

浮点存不准，在价格上最要命。价格是十进制的，0.29、19.99 这样的数，二进制都存不准。把 double 价格换成以分为单位的整数时，直接截断就会差 1：

```cpp
double px = 0.29;
int cents = (int)(px * 100);    // 28：px * 100 是 28.999999999999996
```

0.00 到 99.99 这 10000 个价格里，有 573 个这样换出来少 1；写成 `px / 0.01` 更糟，有 1076 个。换算要取最近的整数，`std::llround(px * 100)` 得 29。

更彻底的是一开始就用整数存价格，单位取分或 tick，类型用 `int64_t`。加减和比较都是 1 个周期的整数运算，而且是精确的：

```cpp
int64_t price_cents = 1999;               // 19.99
int64_t total_cents = price_cents * 5;    // 9995，精确
```

同样的计算用 float，`19.99f` 存的是 19.9899998，乘 5 得 99.9499969。整数只在显示时才拆成元和分，`total_cents / 100` 和 `% 100` 的除数是常数，编译器会换成乘法，而且不在热路径上。
