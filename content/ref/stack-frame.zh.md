---
title: "函数调用栈帧：返回地址、寄存器传参和栈溢出"
date: 2026-11-02
slug: "stack-frame"
description: "每调一次函数，栈上就多出一块栈帧：call 压进去的返回地址、保存的 rbp、局部变量。用 GCC 真实生成的汇编，一格一格画出两层嵌套调用时栈上的样子；再讲 x86-64 System V 的调用约定（前 6 个参数走寄存器、谁保存哪些寄存器、call 前 16 字节对齐、叶子函数的红区）、返回大对象时的隐藏指针和 RVO、省掉帧指针以后 gdb 和异常怎么靠 .eh_frame 找回调用栈，以及栈上会出的三种错：栈溢出、返回局部变量的地址、缓冲区溢出和栈金丝雀。"
summary: "栈帧就是一次调用在栈上占的那一块：call 把返回地址压进去，函数开头保存旧的 rbp、把 rsp 往下挪出局部变量的位置，ret 再把返回地址弹回 rip。参数前 6 个走寄存器，大对象由调用者在自己的帧里留好位置、把地址悄悄传进去，RVO 就是被调用者直接在那里构造。栈上的三种常见错误都能在这张图上找到位置：越过栈底的保护页、指向已经被下一帧覆盖的格子、写过头盖掉返回地址。"
toc: true
group: cpplinux
weight: 109
aliases: ["/posts/stack-frame/"]
---

程序崩溃时 gdb 打出来的调用栈，“栈溢出”，“不要返回局部变量的地址”，“RVO 省掉了一次拷贝”：这些说法背后是同一件事，每调一次函数，栈上就多出一块，用来放返回地址、保存的寄存器和局部变量，这一块叫栈帧（stack frame）。这篇用 GCC 实际生成的汇编，把一次调用在栈上留下了什么一格一格画出来，再看哪些错误会落在这些格子上。栈本身在进程地址空间的哪里、默认多大，见[进程地图](/maps/process-map.zh.html)里的“栈”那一格（[速查页](/zh/ref/cpp-linux/#segments)有文字版）。

下面的汇编都是 GCC 16.2 按 x86-64 System V 调用约定（Linux 用的就是这一套）编出来的，用的是 AT&T 写法（源操作数在前），去掉了和讲解无关的伪指令。

## 1. 一次调用在栈上留下什么

### 1.1 call 和 ret：返回地址压在栈上

`call f` 做两件事：把下一条指令的地址压到栈上，再跳到 `f`。`ret` 做相反的事：从栈顶弹出一个地址，跳回去。被调用的函数并不知道自己是被谁调的，它只认栈顶那 8 个字节，**所以返回地址只存在栈上这一处，这一格被写坏，`ret` 就会跳到别处去**，第 5 部分的缓冲区溢出就是冲着这一格来的。

栈从高地址往低地址长。`rsp` 永远指向栈顶，也就是当前最低的那个已用地址。压栈是先把 `rsp` 减 8 再写，弹栈是先读再把 `rsp` 加 8。

### 1.2 序言和尾声（prologue / epilogue）：保存 rbp，挪出局部变量的位置

拿两个函数来看，`mid` 调 `leaf`：

```cpp
int leaf(int a, int b) {
    int t = a * b;
    return t + 1;
}

int mid(int x) {
    int buf[4] = {x, x + 1, x + 2, x + 3};
    return leaf(buf[0], buf[3]) + buf[1];
}
```

不开优化（`-O0`）时，`mid` 编出来是这样：

```text
mid(int):
	pushq	%rbp              # 序言：保存调用者的 rbp
	movq	%rsp, %rbp        #       rbp 指向这一格，从此按 rbp 找局部变量
	subq	$32, %rsp         #       挪出 32 字节放局部变量
	movl	%edi, -20(%rbp)   # 参数 x 从寄存器存进栈里
	movl	-20(%rbp), %eax
	movl	%eax, -16(%rbp)   # buf[0] = x
	movl	-20(%rbp), %eax
	addl	$1, %eax
	movl	%eax, -12(%rbp)   # buf[1] = x + 1
	movl	-20(%rbp), %eax
	addl	$2, %eax
	movl	%eax, -8(%rbp)    # buf[2] = x + 2
	movl	-20(%rbp), %eax
	addl	$3, %eax
	movl	%eax, -4(%rbp)    # buf[3] = x + 3
	movl	-4(%rbp), %edx
	movl	-16(%rbp), %eax
	movl	%edx, %esi        # 第 2 个参数：buf[3]
	movl	%eax, %edi        # 第 1 个参数：buf[0]
	call	leaf(int, int)
	movl	-12(%rbp), %edx
	addl	%edx, %eax        # 返回值在 eax，加上 buf[1]
	leave                     # 尾声：rsp = rbp，再弹出旧的 rbp
	ret
```

开头三条叫序言。`push %rbp` 把调用者的 `rbp` 存起来，因为接下来要拿 `rbp` 当自己的基准；`mov %rsp, %rbp` 让 `rbp` 指向刚存下的那一格；`sub $32, %rsp` 把栈顶往下挪 32 字节，中间这段就是局部变量的地方。之后局部变量都按 `rbp` 减一个固定偏移来找，`buf[0]` 在 `rbp-16`，`x` 在 `rbp-20`。结尾的 `leave` 等于 `mov %rbp, %rsp` 加 `pop %rbp`，把栈顶挪回来、把调用者的 `rbp` 还回去，然后 `ret`。

**在栈上分配局部变量就是一条 `sub`，释放就是一条 `leave`，和局部变量有多少个、多大都无关**，这是栈比堆分配便宜的原因（堆要在空闲块里找一块合适的，见 [new 一次走到哪](/zh/ref/new-malloc-page-fault/)）。两者访问的都是同一种内存，栈的另一个好处是同一段地址被一层层调用反复使用，几乎总在 L1 缓存里（[硬件地图](/zh/ref/cpu-memory/)）。

`mid` 调 `leaf`、`leaf` 刚执行完自己的序言时，栈上是这样：

<svg viewBox="0 0 760 450" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="mid 调 leaf 时的栈：从高地址往下依次是调用者的帧、回到调用者的返回地址、保存的 rbp、mid 的局部变量 buf 和 x、对齐用的空位；然后是 call leaf 压进去的返回地址、leaf 保存的 mid 的 rbp；leaf 没有挪 rsp，它的局部变量放在 rsp 下面的红区里。每个保存的 rbp 指向上一帧保存 rbp 的那一格，连成一条链" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sf0bg  { fill: #fbfaf7; }
    .sf0old { fill: #f1efe9; stroke: #b9b2a3; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .sf0mid { fill: #fdf8ec; stroke: #c9a85c; stroke-width: 1.2; }
    .sf0lf  { fill: #eef6e4; stroke: #8fae62; stroke-width: 1.2; }
    .sf0ret { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .sf0rbp { fill: #e3eef9; stroke: #7aa2cf; stroke-width: 1.2; }
    .sf0rz  { fill: none; stroke: #6f8f3f; stroke-width: 1.4; stroke-dasharray: 6 4; }
    .sf0ink { fill: #1c1b18; font-size: 12.5px; }
    .sf0mut { fill: #6b6558; font-size: 11.5px; }
    .sf0ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .sf0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sf0ch  { stroke: #4f74a0; stroke-width: 1.5; fill: none; }
    .sf0hd  { fill: #6b6558; }
    .sf0hdb { fill: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0old { fill: #1f1e22; stroke: #4a4740; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0mid { fill: #2b2617; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0lf { fill: #232c1b; stroke: #6f8f3f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0ret { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0rbp { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0rz { stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0ink, :root:is([data-theme="dark"], [data-theme="black"]) .sf0ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0ch { stroke: #7fa6d6; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0hd { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf0hdb { fill: #7fa6d6; }
  </style>
  <defs>
    <marker id="sf0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sf0hd"/></marker>
    <marker id="sf0b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sf0hdb"/></marker>
  </defs>
  <rect class="sf0bg" x="0" y="0" width="760" height="450" rx="10"/>
  <text class="sf0ttl" x="150" y="36">高地址</text>
  <rect class="sf0old" x="150" y="50" width="320" height="30"/>
  <text class="sf0mut" x="232" y="70">调用 mid 的那一帧（main 等）</text>
  <rect class="sf0ret" x="150" y="80" width="320" height="30"/>
  <text class="sf0mut" x="162" y="100">rbp+8</text>
  <text class="sf0ink" x="232" y="100">返回地址：回到调 mid 的下一条</text>
  <rect class="sf0rbp" x="150" y="110" width="320" height="30"/>
  <text class="sf0mut" x="162" y="130">rbp</text>
  <text class="sf0ink" x="232" y="130">保存的 rbp（调用者的）</text>
  <rect class="sf0mid" x="150" y="140" width="320" height="30"/>
  <text class="sf0mut" x="162" y="160">rbp−8</text>
  <text class="sf0ink" x="232" y="160">buf[2]、buf[3]</text>
  <rect class="sf0mid" x="150" y="170" width="320" height="30"/>
  <text class="sf0mut" x="162" y="190">rbp−16</text>
  <text class="sf0ink" x="232" y="190">buf[0]、buf[1]</text>
  <rect class="sf0mid" x="150" y="200" width="320" height="30"/>
  <text class="sf0mut" x="162" y="220">rbp−24</text>
  <text class="sf0ink" x="232" y="220">x（参数从 edi 存下来）</text>
  <rect class="sf0mid" x="150" y="230" width="320" height="30"/>
  <text class="sf0mut" x="162" y="250">rbp−32</text>
  <text class="sf0ink" x="232" y="250">空着：凑够 16 字节对齐</text>
  <rect class="sf0ret" x="150" y="260" width="320" height="30"/>
  <text class="sf0mut" x="162" y="280">rbp+8</text>
  <text class="sf0ink" x="232" y="280">返回地址：回到 mid 里 call 之后</text>
  <rect class="sf0rbp" x="150" y="290" width="320" height="30"/>
  <text class="sf0mut" x="162" y="310">rbp</text>
  <text class="sf0ink" x="232" y="310">保存的 rbp（mid 的）</text>
  <rect class="sf0lf" x="150" y="320" width="320" height="30"/>
  <text class="sf0mut" x="162" y="340">rbp−8</text>
  <text class="sf0ink" x="232" y="340">t（leaf 的局部变量）</text>
  <rect class="sf0lf" x="150" y="350" width="320" height="30"/>
  <text class="sf0mut" x="162" y="370">rbp−16</text>
  <text class="sf0ink" x="232" y="370">空</text>
  <rect class="sf0lf" x="150" y="380" width="320" height="30"/>
  <text class="sf0mut" x="162" y="400">rbp−24</text>
  <text class="sf0ink" x="232" y="400">b、a（参数从 esi、edi 存下来）</text>
  <rect class="sf0rz" x="146" y="318" width="328" height="94" rx="4"/>
  <text class="sf0mut" x="20" y="358">红区：rsp 以下</text>
  <text class="sf0mut" x="20" y="374">128 字节</text>
  <text class="sf0ttl" x="150" y="436">低地址：栈往这边长</text>
  <path class="sf0ch" d="M150,305 L110,305 L110,135 L148,135" marker-end="url(#sf0b)"/>
  <path class="sf0ch" d="M150,118 L125,118 L125,65 L148,65" marker-end="url(#sf0b)"/>
  <text class="sf0mut" x="24" y="206">保存的 rbp</text>
  <text class="sf0mut" x="24" y="222">指向上一帧</text>
  <text class="sf0mut" x="24" y="238">的 rbp 那格</text>
  <path class="sf0ln" d="M488,125 L474,125" marker-end="url(#sf0a)"/>
  <text class="sf0ink" x="492" y="129">mid 的 rbp</text>
  <path class="sf0ln" d="M488,245 L474,245" marker-end="url(#sf0a)"/>
  <text class="sf0ink" x="492" y="249">mid 的 rsp（调用前）</text>
  <path class="sf0ln" d="M488,305 L474,305" marker-end="url(#sf0a)"/>
  <text class="sf0ink" x="492" y="309">leaf 的 rbp、rsp</text>
  <path class="sf0ln" d="M648,82 L656,82 L656,258 L648,258"/>
  <text class="sf0ttl" x="664" y="174">mid 的栈帧</text>
  <path class="sf0ln" d="M648,262 L656,262 L656,410 L648,410"/>
  <text class="sf0ttl" x="664" y="340">leaf 的栈帧</text>
</svg>

每一格 8 字节，偏移都是相对各自那一帧的 `rbp`。两个红色的格子是两次 `call` 压进去的返回地址，蓝色的是两次序言保存的 `rbp`。每个保存的 `rbp` 都指向上一帧保存 `rbp` 的那一格，连成一条链，**顺着这条链往上走，每一格上面紧挨着的就是返回地址，调试器就是这样一层层列出“谁调了谁”的**（第 4 部分讲没有这条链时怎么办）。

### 1.3 红区（red zone）：叶子函数不用挪 rsp

再看 `leaf` 的 `-O0` 汇编：

```text
leaf(int, int):
	pushq	%rbp
	movq	%rsp, %rbp
	movl	%edi, -20(%rbp)   # 没有 sub rsp，直接往 rsp 下面写
	movl	%esi, -24(%rbp)
	movl	-20(%rbp), %eax
	imull	-24(%rbp), %eax
	movl	%eax, -4(%rbp)    # t = a * b
	movl	-4(%rbp), %eax
	addl	$1, %eax
	popq	%rbp
	ret
```

它少了 `sub $N, %rsp`，局部变量直接写在 `rsp` 下面。平时这样做是危险的：栈顶以下的地方被认为是空的，信号处理函数一来，内核会把现场压在当前 `rsp` 下面，正好盖掉这些变量。System V 调用约定为此留了一条规矩：`rsp` 下面 128 字节是红区，内核压信号现场时先跳过这 128 字节，谁也不会动它。

`leaf` 是叶子函数，它不再调别的函数，没有人会往它的栈顶下面压东西，所以它可以省掉挪 `rsp` 的那两条指令，直接用红区。**红区只对叶子函数有用：一旦要 `call`，返回地址就会压进红区，盖掉里面的东西。** Linux 内核自己编译时加了 `-mno-red-zone`，因为中断会直接压在被打断的内核栈上，内核不能跳过红区。

## 2. 调用约定：参数和返回值放在哪

### 2.1 寄存器传参：前 6 个整数参数走寄存器

调用者和被调用者必须对“第 1 个参数放在哪”有同样的约定，否则两边各编各的就对不上。x86-64 Linux 用的是 System V ABI 里规定的那一套：

| 放什么 | 放在哪 |
|---|---|
| 第 1–6 个整数或指针参数 | `rdi`、`rsi`、`rdx`、`rcx`、`r8`、`r9` |
| 第 1–8 个浮点参数 | `xmm0`–`xmm7` |
| 更多的参数 | 从右往左压栈，第 7 个整数参数在 `call` 前的 `rsp` 处 |
| 整数返回值 | `rax`（128 位的再加 `rdx`） |
| 浮点返回值 | `xmm0` |

8 个整数参数时，多出的两个就要走栈：

```cpp
int many(int a, int b, int c, int d, int e, int f, int g, int h) {
    return a + b + c + d + e + f + g + h;
}
```

`-O2` 下：

```text
many(int, int, int, int, int, int, int, int):
	addl	%esi, %edi        # a 在 edi，b 在 esi
	addl	%edx, %edi
	addl	%ecx, %edi
	addl	%r8d, %edi
	leal	(%rdi,%r9), %eax  # 前 6 个都在寄存器里
	addl	8(%rsp), %eax     # g：在返回地址上面那格
	addl	16(%rsp), %eax    # h
	ret
```

进到 `many` 时 `rsp` 指着返回地址，所以第 7 个参数在 `8(%rsp)`，第 8 个在 `16(%rsp)`。**参数先走寄存器，是因为大多数函数参数不超过 6 个，这样一次调用通常完全不碰内存。** 寄存器只有 6 个能拿来传整数，传一个大结构体时，按大小和类型要么拆进寄存器，要么整块放到栈上；成员函数的 `this` 就是第 1 个参数，占 `rdi`。

### 2.2 调用者保存和被调用者保存：call 前后哪些寄存器还在

`mid` 在调 `leaf` 之后还要用 `x + 1`，这个值放在哪个寄存器里，才能保证 `leaf` 回来时它还在？约定把寄存器分成两类：

| 类别 | 寄存器 | 规矩 |
|---|---|---|
| 被调用者保存（callee-saved） | `rbx`、`rbp`、`r12`–`r15`（还有 `rsp`） | 被调用的函数要用，就得先存起来、返回前还原 |
| 调用者保存（caller-saved） | `rax`、`rcx`、`rdx`、`rsi`、`rdi`、`r8`–`r11`，全部 `xmm` | 被调用的函数随便改；调用者想留住，就自己在 `call` 前存 |

`leaf` 放在另一个 `.cpp` 里、`mid` 开 `-O2` 编译：

```text
mid(int):
	pushq	%rbx              # 要用 rbx，先替调用者存起来
	leal	3(%rdi), %esi     # 第 2 个参数 x + 3
	movl	%edi, %ebx        # x 放进 rbx：leaf 保证不改它
	call	leaf(int, int)    # 第 1 个参数 x 本来就在 edi 里
	leal	1(%rbx,%rax), %eax # leaf 的结果 + x + 1
	popq	%rbx              # 还原调用者的 rbx
	ret
```

`buf` 数组整个被优化掉了，`mid` 只需要在调用前后留住 `x`。它把 `x` 放进 `rbx`，因为 `rbx` 是被调用者保存的，`leaf` 若要用它必须自己存、自己还原，所以 `call` 回来以后 `rbx` 里还是 `x`；代价是 `mid` 自己也是“被调用者”，它动了 `rbx`，就得在开头 `push`、结尾 `pop`，替它的调用者守住这个规矩。**两类寄存器各占一半，是在“调用者每次都存”和“被调用者每次都存”之间折中：短命的临时值放调用者保存的寄存器，跨调用要活下来的值放被调用者保存的寄存器。**

### 2.3 16 字节对齐：call 之前 rsp 必须是 16 的倍数

约定还要求：执行 `call` 的那一刻，`rsp` 必须是 16 的倍数。`call` 再压 8 字节返回地址，所以每个函数刚进来时，`rsp` 除以 16 余 8。这条规矩是给 SSE 指令留的：`movaps` 这类指令要求内存地址 16 字节对齐，编译器敢用它们读写栈上的局部变量，前提就是栈是对齐的。

回头看上面两段汇编，凑对齐的痕迹都在：`-O0` 的 `mid` 进来时余 8，`push %rbp` 后变成 0，于是 `sub` 的是 32 而不是刚好够用的 20；`-O2` 的 `mid` 里那条 `push %rbx` 一举两得，既保存了 `rbx`，也把 `rsp` 从余 8 推到了余 0，`call leaf` 时正好对齐。**手写汇编或者自己切栈时最容易忘这一条，忘了不会马上出事，直到某个用了 `movaps` 的库函数（`printf` 就常见）在栈上读写时崩掉。**

## 3. 返回一个大对象

### 3.1 隐藏指针：调用者留位置，被调用者往里写

返回值超过两个寄存器（16 字节），或者类型不能按位拷贝（有自定义的拷贝构造或析构），就没法放在 `rax` 里带回来。约定的办法是让调用者先在自己的帧里留好一块地方，把这块地方的地址当作一个看不见的第 1 个参数，放在 `rdi` 里传进去：

```cpp
struct Big { long long a[8]; };   // 64 字节

Big make(int x) {
    Big b{};
    b.a[0] = x;
    return b;
}

long long use() {
    Big b = make(3);
    return b.a[0] + b.a[7];
}
```

`-O2` 下：

```text
make(int):
	pxor	%xmm0, %xmm0
	movslq	%esi, %rsi        # x 在 esi：rdi 已经被隐藏指针占了
	movq	$0, 56(%rdi)
	movq	%rdi, %rax        # 返回时把这个地址放进 rax
	movq	%rsi, (%rdi)      # b.a[0] = x，直接写进调用者的那块地方
	movups	%xmm0, 8(%rdi)
	movups	%xmm0, 24(%rdi)
	movups	%xmm0, 40(%rdi)
	ret
use():
	subq	$72, %rsp         # 64 字节放 b，再加 8 字节凑对齐
	movl	$3, %esi          # x 成了第 2 个参数
	movq	%rsp, %rdi        # 隐藏的第 1 个参数：b 的地址
	call	make(int)
	movq	56(%rsp), %rax    # b.a[7]
	addq	(%rsp), %rax      # + b.a[0]
	addq	$72, %rsp
	ret
```

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="返回大对象：use 在自己的帧里留出 64 字节给 b，把 b 的地址放进 rdi 传给 make；make 直接往 rdi 指的地方写，返回时把同一个地址放进 rax。整个过程 b 只有一份，没有临时对象，也没有拷贝" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sf1bg  { fill: #fbfaf7; }
    .sf1use { fill: #fdf8ec; stroke: #c9a85c; stroke-width: 1.2; }
    .sf1obj { fill: #eef6e4; stroke: #6f8f3f; stroke-width: 1.6; }
    .sf1ret { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .sf1fn  { fill: #eaf2fb; stroke: #7aa2cf; stroke-width: 1.4; }
    .sf1reg { fill: #ffffff; stroke: #8c8577; stroke-width: 1.2; }
    .sf1ink { fill: #1c1b18; font-size: 12.5px; }
    .sf1mut { fill: #6b6558; font-size: 11.5px; }
    .sf1ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .sf1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sf1hl  { stroke: #4e7a2a; stroke-width: 1.8; fill: none; }
    .sf1hd  { fill: #6b6558; }
    .sf1hdg { fill: #4e7a2a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1use { fill: #2b2617; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1obj { fill: #232c1b; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1ret { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1fn { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1reg { fill: #26231f; stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1ink, :root:is([data-theme="dark"], [data-theme="black"]) .sf1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1hl { stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1hd { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf1hdg { fill: #8fb257; }
  </style>
  <defs>
    <marker id="sf1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sf1hd"/></marker>
    <marker id="sf1g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sf1hdg"/></marker>
  </defs>
  <rect class="sf1bg" x="0" y="0" width="760" height="300" rx="10"/>
  <text class="sf1ttl" x="40" y="34">use 的栈帧（高地址在上）</text>
  <rect class="sf1ret" x="40" y="46" width="280" height="30"/>
  <text class="sf1ink" x="52" y="66">返回地址：回到调 use 的地方</text>
  <rect class="sf1use" x="40" y="76" width="280" height="30"/>
  <text class="sf1ink" x="52" y="96">空 8 字节：凑 16 字节对齐</text>
  <rect class="sf1obj" x="40" y="106" width="280" height="110"/>
  <text class="sf1ttl" x="52" y="130">b：64 字节</text>
  <text class="sf1ink" x="52" y="154">a[7]（rsp+56）</text>
  <text class="sf1mut" x="52" y="174">……</text>
  <text class="sf1ink" x="52" y="198">a[0]（rsp+0）</text>
  <rect class="sf1ret" x="40" y="216" width="280" height="30"/>
  <text class="sf1ink" x="52" y="236">返回地址：回到 use（call 压的）</text>
  <path class="sf1ln" d="M334,216 L322,216" marker-end="url(#sf1a)"/>
  <text class="sf1mut" x="338" y="232">use 的 rsp</text>
  <rect class="sf1reg" x="430" y="60" width="290" height="58" rx="6"/>
  <text class="sf1ink" x="442" y="82">rdi = use 的 rsp（b 的地址）</text>
  <text class="sf1ink" x="442" y="104">esi = 3（x 挪到第 2 个参数）</text>
  <rect class="sf1fn" x="430" y="150" width="290" height="96" rx="8"/>
  <text class="sf1ttl" x="442" y="172">make(int)</text>
  <text class="sf1ink" x="442" y="196">往 (%rdi) 起的 64 字节里写</text>
  <text class="sf1ink" x="442" y="216">rax = rdi：把同一个地址交回去</text>
  <text class="sf1mut" x="442" y="236">自己的帧里没有 b</text>
  <path class="sf1ln" d="M575,118 L575,148" marker-end="url(#sf1a)"/>
  <path class="sf1hl" d="M430,200 L380,200 L380,160 L322,160" marker-end="url(#sf1g)"/>
  <text class="sf1mut" x="40" y="276">b 从头到尾只有这一份：make 写的就是 use 的局部变量，没有临时对象，也没有拷贝。</text>
</svg>

`use` 的 `x` 本来该是第 1 个参数，现在挪到了 `esi`，因为 `rdi` 被隐藏指针占了。`make` 里那个 `b` 根本没有自己的位置，它的每次写入都直接落在 `use` 帧里的 `b` 上。**返回大对象并不意味着“先在被调用者里造一个、再拷给调用者”：调用约定本来就是让被调用者直接写调用者留好的那块内存。**

### 3.2 RVO 和 NRVO：直接在调用者的位置上构造

3.1 的 `make` 返回的是一个具名的局部变量 `b`，编译器把 `b` 直接放在调用者给的地址上，于是 `return b` 时什么都不用做。这叫具名返回值优化（NRVO）。返回一个临时对象，比如 `return Big{};`，直接在那块地址上构造它叫返回值优化（RVO）。两者在 C++ 标准里的地位不一样：

```cpp
#include <cstdio>
#include <utility>

struct Noisy {
    Noisy() {}
    Noisy(const Noisy&) { std::puts("  拷贝"); }
    Noisy(Noisy&&) noexcept { std::puts("  移动"); }
};

Noisy f1() { return Noisy{}; }                  // 返回纯右值：C++17 起保证不拷不移
Noisy f2() { Noisy n; return n; }               // 返回具名局部变量：NRVO，允许省、不保证
Noisy f3() { Noisy n; return std::move(n); }    // 自己写 std::move：NRVO 做不成了
Noisy f4(bool c) {                              // 两个分支返回不同的对象：NRVO 做不成
    Noisy a, b;
    if (c) return a;
    return b;                                   // 但不会拷贝：返回局部变量时自动当右值，走移动
}

int main() {
    std::puts("f1:"); Noisy x1 = f1();
    std::puts("f2:"); Noisy x2 = f2();
    std::puts("f3:"); Noisy x3 = f3();
    std::puts("f4:"); Noisy x4 = f4(true);
}
```

GCC `-std=c++17`，`-O0` 和 `-O2` 输出一样：

```text
f1:
f2:
f3:
  移动
f4:
  移动
```

`f1` 是 C++17 规定的：用纯右值初始化同类型的对象，根本不存在中间那个临时对象，所以就算类型不能拷贝也不能移动，`f1` 照样能编译。`f2` 的 NRVO 标准允许做、不要求做，GCC 在所有 `return` 都返回同一个局部变量时会做，连 `-O0` 也做。`f3` 多写的 `std::move(n)` 让返回表达式不再是“一个局部变量的名字”，NRVO 的条件就不满足了，只能老老实实移动一次，GCC 会用 `-Wpessimizing-move` 警告这一行。`f4` 的两个分支返回不同的对象，编译器没法让 `a` 和 `b` 同时住在调用者给的那一块地址上，NRVO 做不成；但返回一个局部变量时，语言规定先把它当右值试一遍，所以走的是移动，不是拷贝。

**所以写法上的结论很简单：直接 `return` 局部变量，不要加 `std::move`，更不要为了“省拷贝”改成返回引用**：返回局部变量的引用，引用的是一块函数返回后就作废的栈内存（5.2）。

## 4. 没有帧指针时，怎么找回调用栈

### 4.1 -O2 默认省掉帧指针

对比 1.2 的 `-O0` 和 2.2 的 `-O2`，`-O2` 的 `mid` 没有 `push %rbp; mov %rsp, %rbp`。GCC 在 x86-64 上从 `-O1` 起默认打开 `-fomit-frame-pointer`：局部变量直接按 `rsp` 加偏移找，`rbp` 省下来当普通寄存器用，每次调用也少两条指令。代价是 1.2 那条 `rbp` 链断了，调试器没法再顺着它一层层往上走。想留着它，编译时加 `-fno-omit-frame-pointer`；有些发行版（比如 Fedora 38 起、Ubuntu 24.04 起）为了让性能分析工具好用，整个系统的软件包都是这样编的。

### 4.2 .eh_frame 和 CFI：按指令地址查“上一帧在哪”

没有帧指针也能打出调用栈，靠的是编译器另外生成的一张表。把 2.2 的 `mid` 带上这张表的伪指令再编一次：

```text
mid(int):
	.cfi_startproc
	pushq	%rbx
	.cfi_def_cfa_offset 16        # 从这里起：CFA = rsp + 16
	.cfi_offset 3, -16            #           rbx（3 号寄存器）存在 CFA − 16
	leal	3(%rdi), %esi
	movl	%edi, %ebx
	call	leaf(int, int)
	leal	1(%rbx,%rax), %eax
	popq	%rbx
	.cfi_def_cfa_offset 8         # 从这里起：CFA = rsp + 8
	ret
	.cfi_endproc
```

CFA（canonical frame address）是这一帧的基准点，定义成"调用这个函数的那条 `call` 执行之前的 `rsp`"，所以返回地址永远在 CFA − 8。`.cfi_*` 这些伪指令告诉汇编器：在函数里的每一段指令范围内，CFA 等于 `rsp` 加多少，哪些被调用者保存的寄存器存在 CFA 减多少的地方。汇编器把它们整理成 `.eh_frame` 段里的一张表，跟着程序一起加载。

回溯时，调试器拿当前的 `rip` 去表里查到这一段的规则，算出 CFA，从 CFA − 8 读出返回地址，就知道上一层停在哪条指令；再把 `rsp` 设成 CFA、按规则还原 `rbx` 这些寄存器，拿上一层的 `rip` 继续查。**有了这张表，回溯就不需要 `rbp` 链：每一帧的大小和保存位置，编译时就已经写进了表里。** C++ 抛异常时一层层退栈、调析构函数，用的也是这张表，这就是它的名字里有 `eh`（exception handling）的原因；所以就算是 C 程序，x86-64 Linux 上默认也会生成它。

自己想看这张表，`readelf --debug-dump=frames 程序` 会把每个函数的规则打出来。`perf record --call-graph=dwarf` 用的就是它，而默认的 `--call-graph=fp` 只会顺着 `rbp` 链走，程序没有帧指针时，后者打出的调用栈是断的。

## 5. 栈上会出的错

### 5.1 栈溢出：递归太深、局部数组太大

主线程的栈有上限，默认是 `ulimit -s` 给的 8 MiB。这 8 MiB 并不是一开始就分好的：内核只先映射一小段，栈往下长、碰到还没映射的页时触发缺页，内核把栈的映射往下扩，直到碰上限。再往下，内核还在栈和下面的映射之间留了一段永远不映射的空隙（保护间隔，默认 256 页，也就是 1 MiB），写到那里就是 SIGSEGV。

```cpp
int depth(int n) {
    volatile char pad[1024];       // volatile：不让编译器把数组优化掉
    pad[0] = static_cast<char>(n);
    if (n == 0) return pad[0];
    return depth(n - 1) + pad[0];  // 不是尾调用：每一层的帧都留着
}
```

每层帧一千多字节，8 MiB 大约够几千层，`depth(100000)` 必然越过上限。局部数组太大是同一回事：一个函数里写 `char buf[16 << 20];`，这一帧就要 16 MiB，第一次碰到它就越界。**栈的大小是 MiB 级的，适合放小而短命的东西；大块数据、深度不可控的递归，应该放到堆上或者改成循环。**

线程的栈不在这里，它是 glibc 用 `mmap` 在 [mmap 区](/maps/process-map.zh.html)分出来的一块，大小在创建时就定死、不会长，最低处留一页不可访问的保护页。glibc 默认取的也是 `ulimit -s` 的值，所以通常同样是 8 MiB；musl 这类 C 库默认只有 128 KiB，从 glibc 换过去时深递归最容易出事。`std::thread` 没法指定栈大小，要改得用 pthread：

```cpp
#include <pthread.h>

void* work(void*) { return nullptr; }

int main() {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 64 << 20);   // 64 MiB
    pthread_t t;
    pthread_create(&t, &attr, work, nullptr);
    pthread_join(t, nullptr);
    pthread_attr_destroy(&attr);
}
```

保护页只有一页时还有个漏洞：一帧比保护页还大，第一次写入就可能直接跳过保护页，落进下面别的映射里，不崩溃但默默写坏了别人的数据。GCC 的 `-fstack-clash-protection` 会在分配大帧时每隔一页先探一下，保证一定先碰到保护页；不少发行版的 GCC 默认就开着它。

### 5.2 返回局部变量的地址：指向一块马上会被覆盖的格子

```cpp
int* bad() {
    int x = 42;
    return &x;
}
```

`x` 住在 `bad` 的帧里。`bad` 一返回，`rsp` 挪回去，那一格就成了栈顶以下的空地，下一次调用任何函数，新的帧就会盖在同一个位置上。所以这个指针“有时候还能读到 42”，完全取决于中间有没有别的调用。GCC 对这种写法会警告 `-Wreturn-local-addr`，而且干脆把返回值编成空指针：上面的函数 `-O2` 下编出来是 `xorl %eax, %eax` 加 `ret`，`-O0` 下是 `movl $0, %eax`，解引用时马上崩，比读到一个看起来正常的值好查。返回局部变量的引用、lambda 按引用捕获了局部变量再被带出函数，都是同一类问题，只是编译器不一定看得出来，要靠 ASan 的 `detect_stack_use_after_return` 查。

### 5.3 缓冲区溢出和栈金丝雀（stack canary）：写过头会盖到返回地址

局部数组和返回地址在同一个帧里，而且数组在下面、返回地址在上面。往数组里写是从低地址往高地址写的，写过了头就会依次盖掉上面的东西：

```cpp
#include <cstring>
#include <cstdio>

void greet(const char* name) {
    char buf[16];
    std::strcpy(buf, name);   // name 超过 15 个字符，就写出 buf 的范围
    std::printf("hello %s\n", buf);
}
```

<svg viewBox="0 0 760 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="greet 的栈帧：从高地址往下依次是返回地址、保存的 rbp、金丝雀、buf 的后 8 字节、buf 的前 8 字节。strcpy 从 buf[0] 往高地址写，写过头先盖掉金丝雀，再盖掉保存的 rbp 和返回地址；函数返回前检查金丝雀变没变，变了就调 __stack_chk_fail 终止程序" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sf2bg  { fill: #fbfaf7; }
    .sf2old { fill: #f1efe9; stroke: #b9b2a3; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .sf2ret { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .sf2rbp { fill: #e3eef9; stroke: #7aa2cf; stroke-width: 1.2; }
    .sf2can { fill: #fff3c4; stroke: #c9a227; stroke-width: 1.6; }
    .sf2buf { fill: #eef6e4; stroke: #8fae62; stroke-width: 1.2; }
    .sf2ink { fill: #1c1b18; font-size: 12.5px; }
    .sf2mut { fill: #6b6558; font-size: 11.5px; }
    .sf2ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .sf2red { fill: #b4532f; font-size: 12.5px; font-weight: 700; }
    .sf2hl  { stroke: #b4532f; stroke-width: 2; fill: none; }
    .sf2ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sf2hdr { fill: #b4532f; }
    .sf2hd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2old { fill: #1f1e22; stroke: #4a4740; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2ret { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2rbp { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2can { fill: #3a3215; stroke: #c9a227; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2buf { fill: #232c1b; stroke: #6f8f3f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2ink, :root:is([data-theme="dark"], [data-theme="black"]) .sf2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2red { fill: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2hl { stroke: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2hdr { fill: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sf2hd { fill: #a19caf; }
  </style>
  <defs>
    <marker id="sf2r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sf2hdr"/></marker>
    <marker id="sf2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sf2hd"/></marker>
  </defs>
  <rect class="sf2bg" x="0" y="0" width="760" height="290" rx="10"/>
  <text class="sf2ttl" x="200" y="34">greet 的栈帧（高地址在上）</text>
  <rect class="sf2old" x="200" y="46" width="300" height="30"/>
  <text class="sf2mut" x="212" y="66">调用者的帧</text>
  <rect class="sf2ret" x="200" y="76" width="300" height="30"/>
  <text class="sf2ink" x="212" y="96">返回地址</text>
  <rect class="sf2rbp" x="200" y="106" width="300" height="30"/>
  <text class="sf2ink" x="212" y="126">保存的 rbp</text>
  <rect class="sf2can" x="200" y="136" width="300" height="30"/>
  <text class="sf2ink" x="212" y="156">金丝雀：进函数时抄的随机值</text>
  <rect class="sf2buf" x="200" y="166" width="300" height="30"/>
  <text class="sf2ink" x="212" y="186">buf[8] … buf[15]</text>
  <rect class="sf2buf" x="200" y="196" width="300" height="30"/>
  <text class="sf2ink" x="212" y="216">buf[0] … buf[7]</text>
  <path class="sf2hl" d="M520,216 L520,86" marker-end="url(#sf2r)"/>
  <text class="sf2red" x="532" y="160">strcpy 写过头：</text>
  <text class="sf2red" x="532" y="180">从 buf[0] 往高地址写，</text>
  <text class="sf2red" x="532" y="200">依次盖掉上面的格子</text>
  <text class="sf2mut" x="20" y="146">ret 之前比一下：</text>
  <text class="sf2mut" x="20" y="162">变了就调</text>
  <text class="sf2mut" x="20" y="178">__stack_chk_fail</text>
  <path class="sf2ln" d="M150,151 L196,151" marker-end="url(#sf2a)"/>
  <text class="sf2mut" x="200" y="256">没有金丝雀时，ret 会跳到被盖掉的返回地址：攻击者往 name 里放什么地址，程序就跳去哪。</text>
</svg>

`name` 超过 15 个字符，`strcpy` 就会接着往上写，先盖掉 `buf` 上面的东西，再盖掉保存的 `rbp` 和返回地址。函数照常运行到 `ret`，从被盖掉的那一格取出地址跳过去：如果这串字符是精心构造的，程序就跳到了攻击者想让它去的地方，这就是经典的栈溢出攻击。

栈金丝雀（stack canary）是编译器加的一道检查：在局部数组和保存的寄存器之间放一个随机值，进函数时写进去，`ret` 之前读出来和原值比，变了就说明有人从下面写穿了，直接调 `__stack_chk_fail` 打印 `*** stack smashing detected ***` 并终止程序。x86-64 Linux 上这个随机值每个进程一个，放在线程局部存储里，代码读的是 `%fs:0x28`；它的最低字节固定是 0，`strcpy` 这类以 0 结尾的字符串拷贝没法把它原样写回去。**金丝雀不能防止写坏，它只是保证写坏了返回地址的函数走不到 `ret` 那一步。** GCC 的 `-fstack-protector-strong` 给带局部数组、或者取过局部变量地址的函数加这道检查，Ubuntu 等发行版的 GCC 默认就打开它。

金丝雀之外还有几层：栈所在的页不可执行（NX），攻击者就没法把代码放在栈上直接跳过去；地址空间布局随机化（ASLR）让栈、堆、共享库每次运行的地址都不一样，攻击者很难事先知道该往返回地址里填什么。根本的办法还是别让写入越界：用 `std::string`、`snprintf` 这类带长度的接口，开发时开 ASan，越界的第一个字节就会报出来。

## 6. 自己看栈帧

### 6.1 读汇编：-S 和 objdump

```bash
g++ -O0 -S -fno-asynchronous-unwind-tables -o - frame.cpp | c++filt   # 不优化：能看到完整的序言、尾声
g++ -O2 -S -fno-asynchronous-unwind-tables -o - frame.cpp | c++filt   # 优化后：帧指针省掉，局部变量多半在寄存器里
objdump -d --no-show-raw-insn -C ./a.out | less                       # 看已经编好的程序
```

`-fno-asynchronous-unwind-tables` 去掉 4.2 那些 `.cfi_*` 伪指令，汇编干净一些；想看 CFI 时把它去掉。`c++filt` 把 `_Z4leafii` 这样的修饰名还原成 `leaf(int, int)`。读的时候先找三样东西：开头动了哪些寄存器和 `rsp`（帧有多大、存了谁），`call` 前参数放进了哪些寄存器，`ret` 前 `rax` 里是什么。

### 6.2 gdb：bt、frame、info frame、x

带 `-g` 编译，在 gdb 里停下来以后：

| 命令 | 看什么 |
|---|---|
| `bt` | 调用栈，每层一行：第几帧、函数名、参数、源码行；`bt full` 连局部变量一起打 |
| `frame 1`、`up`、`down` | 切到某一层，之后 `print` 看的是那一层的局部变量 |
| `info frame` | 这一层的帧在哪（`frame at` 就是 4.2 的 CFA）、保存的 `rip`（返回地址）、被调用者保存的寄存器存在哪 |
| `info registers rsp rbp rip` | 三个寄存器现在的值 |
| `x/8gx $rsp` | 从栈顶起按 8 字节一格打 8 格，对照第 1 部分的图能认出返回地址和保存的 `rbp` |
| `disassemble` | 当前函数的汇编，`=>` 标着停在哪一条 |

`x/8gx $rsp` 打出来的那些数里，落在程序代码段地址范围内的通常就是返回地址，`info symbol 地址` 能告诉你它在哪个函数里。栈被写坏时 `bt` 往往打出一串 `??`，这时候手动看 `x/32gx $rsp` 找残存的返回地址，是定位从哪一层开始坏的办法。

### 6.3 core dump：崩溃以后再看调用栈

程序在线上崩溃时没有 gdb 挂着，要靠 core dump：内核在进程因为 SIGSEGV、SIGABRT 这类信号死掉时，把它的内存和寄存器写成一个文件。

```bash
ulimit -c unlimited                 # 允许生成 core（默认常是 0）
cat /proc/sys/kernel/core_pattern   # core 写到哪：一个路径模板，或者交给 systemd-coredump
coredumpctl list                    # 交给 systemd-coredump 时：列出最近的 core
coredumpctl gdb                     # 直接用 gdb 打开最近那个
gdb ./prog core.12345               # core 是普通文件时
```

打开以后和 6.1 一样用 `bt`、`frame`、`info frame`，看的是进程死掉那一刻的栈。栈溢出死掉的进程，`bt` 会打出成千上万层同一个函数，用 `bt -10` 看最外面 10 层，就能找到递归是从哪里开始的。**core 里只有内存，没有符号；拿来分析的那份程序必须和崩溃的是同一次编译出来的，带着 `-g` 的符号（或者单独保存的调试信息文件）才能对上源码行。**
