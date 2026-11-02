---
title: "四种 cast：static_cast、dynamic_cast、const_cast、reinterpret_cast"
date: 2026-11-02
slug: "cpp-casts"
description: "C++ 把 C 的一种强制转换拆成了四种，各管一件事。static_cast 做编译期就能算清的转换：数值类型互转、void* 找回原类型、沿着继承关系转指针，多继承时它会给指针加减偏移，但向下转不做任何检查。dynamic_cast 在运行时顺着 vptr 找到 vtable 里的 typeinfo，确认对象真的是目标类型才给指针，不是就返回 nullptr 或抛 bad_cast，代价是一次库函数调用。const_cast 只去掉 const，对象本来就是 const 时写它是未定义行为。reinterpret_cast 不改任何位，只换个类型来看，换成不相关的类型去读写，会撞上严格别名规则，看字节要用 memcpy 或 std::bit_cast。C 风格的 (T)x 会按顺序试这几种，试中哪个用哪个，类型没定义完整时它会悄悄退成 reinterpret_cast。"
summary: "static_cast 是编译期的、会调整指针但不检查；dynamic_cast 是运行时的、会检查但要查表；const_cast 只动 const；reinterpret_cast 只换解释方式，拿来读写别的类型的对象多半是未定义行为，看字节用 std::bit_cast。C 风格转换会替你挑一种，挑的那种不一定是你以为的。"
toc: true
group: cpplinux
topic: cpp
weight: 107
---

C 只有一种强制转换 `(T)x`：数值截断是它，去掉 `const` 是它，把指针当成整数也是它，读代码的人看不出这一次是哪种。C++ 把它拆成四个关键字，每个只做一类事，写出来就看得到意图，用错了编译器能拦下一部分。下面挨个看它们做什么、编译出来是什么。

## 1. static_cast：编译期就能算清的转换

### 1.1 数值转换、void*、enum {#static-basic}

最常用的是相关类型之间的转换：`int` 和 `double` 互转（`static_cast<int>(3.9)` 是 3，小数直接截掉）、`enum class` 和整数互转、把 `void*` 找回原来的指针类型。这些转换不用转换函数也能隐式发生的不少，写成 `static_cast` 是为了把“这里有意丢精度”或“这里有意换类型”写明白，编译器也会因此不再给缩窄转换报警告。

它拒绝的是不相关的指针：`static_cast<float*>(int_ptr)` 编译不过，两个类型之间没有任何关系，这种只能用 `reinterpret_cast`，也就是明着说“我知道这很危险”。

### 1.2 沿着继承关系转指针：多继承时要加减偏移 {#static-hierarchy}

派生类指针转基类指针（向上转）总是安全的，隐式就能转；基类指针转派生类指针（向下转）要写 `static_cast`。单继承时基类子对象在派生类对象的开头，转换前后指针数值一样。多继承就不一样了：

```cpp
struct A { int a; };
struct B { int b; };
struct C : A, B { int c; };
```

`C` 对象里先放 `A` 子对象，再放 `B` 子对象（布局见[对象布局](/zh/ref/object-layout/)）。`B*` 必须指向 `B` 子对象，所以 `C*` 转 `B*` 时数值要加 4，`B*` 转回 `C*` 要减 4：

<svg viewBox="0 0 760 268" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="C 继承 A 和 B 时的对象：偏移 0 是 A::a，偏移 4 是 B::b，偏移 8 是 C::c。C* 和 A* 指向偏移 0，B* 指向偏移 4。static_cast 从 B* 转回 C* 时减 4，回到对象开头；在 C 只有声明的文件里写 C 风格转换，退成 reinterpret_cast，不减，结果还指着 B::b" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .cc0bg  { fill: #fbfaf7; }
    .cc0a   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .cc0b   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .cc0c   { fill: #f3ead2; stroke: #b89a4e; stroke-width: 1.3; }
    .cc0ink { fill: #1c1b18; font-size: 12.5px; }
    .cc0mono{ fill: #1c1b18; font-size: 12.5px; font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .cc0mut { fill: #6b6558; font-size: 12px; }
    .cc0ok  { fill: #4f7a28; font-size: 12.5px; }
    .cc0bad { fill: #b4533f; font-size: 12.5px; }
    .cc0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .cc0lok { stroke: #4f7a28; stroke-width: 1.6; fill: none; }
    .cc0lbad{ stroke: #b4533f; stroke-width: 1.6; fill: none; stroke-dasharray: 5 4; }
    .cc0hd  { fill: #6b6558; }
    .cc0hok { fill: #4f7a28; }
    .cc0hbad{ fill: #b4533f; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0a { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0b { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0c { fill: #3d3522; stroke: #a08a52; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0ink, :root:is([data-theme="dark"], [data-theme="black"]) .cc0mono { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0ok { fill: #9fca63; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0bad { fill: #e38b77; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0lok { stroke: #9fca63; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0lbad { stroke: #e38b77; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0hd { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0hok { fill: #9fca63; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc0hbad { fill: #e38b77; }
  </style>
  <defs>
    <marker id="cc0m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="cc0hd"/></marker>
    <marker id="cc0mok" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="cc0hok"/></marker>
    <marker id="cc0mbad" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="cc0hbad"/></marker>
  </defs>
  <rect class="cc0bg" x="0" y="0" width="760" height="268" rx="10"/>
  <text class="cc0mono" x="190" y="34">C* / A*</text>
  <text class="cc0mono" x="370" y="34">B*</text>
  <path class="cc0ln" d="M200,42 L200,79" marker-end="url(#cc0m)"/>
  <path class="cc0ln" d="M380,42 L380,79" marker-end="url(#cc0m)"/>
  <text class="cc0mut" x="196" y="76">0</text>
  <text class="cc0mut" x="386" y="76">4</text>
  <text class="cc0mut" x="566" y="76">8</text>
  <text class="cc0mut" x="740" y="76">12</text>
  <rect class="cc0a" x="200" y="82" width="180" height="44"/>
  <text class="cc0mono" x="262" y="109">A::a</text>
  <rect class="cc0b" x="380" y="82" width="180" height="44"/>
  <text class="cc0mono" x="442" y="109">B::b</text>
  <rect class="cc0c" x="560" y="82" width="180" height="44"/>
  <text class="cc0mono" x="622" y="109">C::c</text>
  <text class="cc0ink" x="30" y="109">一个 C 对象</text>
  <path class="cc0lok" d="M380,138 L380,152 L206,152 L206,140" marker-end="url(#cc0mok)"/>
  <text class="cc0ok" x="30" y="176">static_cast&lt;C*&gt;(pb)：减 4，回到对象开头</text>
  <path class="cc0lbad" d="M392,138 L392,206" marker-end="url(#cc0mbad)"/>
  <text class="cc0bad" x="404" y="200">C 只声明、没定义时写 (C*)pb：</text>
  <text class="cc0bad" x="404" y="220">退成 reinterpret_cast，不减，还指着 B::b</text>
  <text class="cc0mut" x="30" y="252">B* 必须指向 B 子对象，所以 C* 和 B* 之间的转换要加减偏移；空指针例外，转完还是空指针。</text>
</svg>

编译出来就是一条加减法，外加对空指针的特判（空指针转完必须还是空指针，不能变成 4）：

```cpp
B* up(C* p)   { return p; }                    // 隐式向上转
C* down(B* p) { return static_cast<C*>(p); }
```

```asm
_Z2upP1C:                         # g++ -O2，x86-64
        xorl    %edx, %edx
        leaq    4(%rdi), %rax         # p + 4
        testq   %rdi, %rdi
        cmove   %rdx, %rax            # p 是空的，结果也给空
        ret
_Z4downP1B:
        xorl    %edx, %edx
        leaq    -4(%rdi), %rax        # p - 4
        testq   %rdi, %rdi
        cmove   %rdx, %rax
        ret
```

转引用时没有这个特判，引用不能为空，就只剩一条 `leaq 4(%rdi), %rax`。

### 1.3 向下转不检查 {#static-unchecked}

上面 `down` 里只有减 4，没有任何一条指令去看 `p` 指向的到底是不是 `C` 里的那个 `B`。如果它其实指向一个单独的 `B` 对象，减 4 得到的地址根本不是一个 `C`，再通过它访问成员就是未定义行为。**static_cast 向下转的正确性完全靠你自己保证：你确实知道对象的真实类型时才能用。** 比如按消息头里的类型字段分发、`switch` 里每个分支已经知道是哪种消息；或者 [CRTP](/zh/posts/crtp-static-polymorphism/) 里基类把 `this` 转成模板参数给的派生类。不知道时，要用下一节的 `dynamic_cast`。

## 2. dynamic_cast：运行时查对象的真实类型

### 2.1 返回 nullptr，或者抛 bad_cast {#dynamic-result}

`dynamic_cast` 会在运行时确认对象真的是目标类型（或它的派生类），是就给出调整好的指针，不是就失败。失败的表现分两种，因为指针能表示“没有”，引用不能：

```cpp
P* p = make();                          // 可能是 Q，也可能是别的派生类
if (Q* q = dynamic_cast<Q*>(p)) { … }   // 不是 Q：得到 nullptr
Q& r = dynamic_cast<Q&>(*p);            // 不是 Q：抛 std::bad_cast
```

向下转时，源类型必须是多态类型，也就是至少有一个虚函数的类，否则编译不过。原因在下一节：它要找的类型信息挂在 vtable 上，没有虚函数就没有 vtable。

### 2.2 编译出来：顺着 vptr 找 typeinfo，再调一个库函数 {#dynamic-how}

```cpp
struct P { virtual ~P(); };
struct Q : P { int q; };
Q* dyn(P* p) { return dynamic_cast<Q*>(p); }
```

```asm
_Z3dynP1P:                        # g++ -O2，x86-64
        testq   %rdi, %rdi
        je      .L10                  # 空指针直接返回空
        xorl    %ecx, %ecx            # 第 4 个参数：提示，0 表示 P 在 Q 里偏移 0
        leaq    _ZTI1Q(%rip), %rdx    # 目标类型 Q 的 typeinfo
        leaq    _ZTI1P(%rip), %rsi    # 源类型 P 的 typeinfo
        jmp     __dynamic_cast        # 剩下的交给 C++ 运行库
.L10:
        xorl    %eax, %eax
        ret
```

编译器只准备好参数，真正的检查在运行库的 `__dynamic_cast` 里。它要做的事，顺序如下：

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="dynamic_cast 的查找路径：从对象开头的 vptr 找到 vtable，vtable 里函数地址前面的两格是 offset_to_top 和 typeinfo 指针；offset_to_top 用来找到完整对象的开头，typeinfo 记着真实类型和它的基类列表；__dynamic_cast 在这张基类图里找目标类型 Q，找到就返回调整后的指针，找不到返回 nullptr" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .cc1bg  { fill: #fbfaf7; }
    .cc1obj { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .cc1vt  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .cc1ti  { fill: #f3ead2; stroke: #b89a4e; stroke-width: 1.3; }
    .cc1ink { fill: #1c1b18; font-size: 12.5px; }
    .cc1mono{ fill: #1c1b18; font-size: 12px; font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .cc1mut { fill: #6b6558; font-size: 12px; }
    .cc1ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .cc1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .cc1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1obj { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1vt { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1ti { fill: #3d3522; stroke: #a08a52; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1ink, :root:is([data-theme="dark"], [data-theme="black"]) .cc1mono, :root:is([data-theme="dark"], [data-theme="black"]) .cc1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .cc1hd { fill: #a19caf; }
  </style>
  <defs><marker id="cc1m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="cc1hd"/></marker></defs>
  <rect class="cc1bg" x="0" y="0" width="760" height="300" rx="10"/>
  <text class="cc1ttl" x="30" y="32">对象（真实类型 Q）</text>
  <text class="cc1ttl" x="270" y="32">Q 的 vtable</text>
  <text class="cc1ttl" x="520" y="32">Q 的 typeinfo</text>
  <rect class="cc1obj" x="30" y="48" width="180" height="40"/>
  <text class="cc1mono" x="44" y="73">vptr</text>
  <rect class="cc1obj" x="30" y="88" width="180" height="40"/>
  <text class="cc1mono" x="44" y="113">int q</text>
  <rect class="cc1vt" x="270" y="48" width="200" height="40"/>
  <text class="cc1mono" x="284" y="73">offset_to_top = 0</text>
  <rect class="cc1vt" x="270" y="88" width="200" height="40"/>
  <text class="cc1mono" x="284" y="113">typeinfo 指针</text>
  <rect class="cc1vt" x="270" y="128" width="200" height="40"/>
  <text class="cc1mono" x="284" y="153">~Q()</text>
  <rect class="cc1vt" x="270" y="168" width="200" height="40"/>
  <text class="cc1mono" x="284" y="193">…</text>
  <path class="cc1ln" d="M210,68 L240,68 L240,148 L266,148" marker-end="url(#cc1m)"/>
  <text class="cc1mut" x="30" y="156">vptr 指向第一个函数，</text>
  <text class="cc1mut" x="30" y="174">往前两格是这两项</text>
  <rect class="cc1ti" x="520" y="48" width="210" height="40"/>
  <text class="cc1mono" x="534" y="73">类型名 "1Q"</text>
  <rect class="cc1ti" x="520" y="88" width="210" height="40"/>
  <text class="cc1mono" x="534" y="113">基类：P，偏移 0</text>
  <path class="cc1ln" d="M470,108 L516,108" marker-end="url(#cc1m)"/>
  <text class="cc1ink" x="520" y="160">① offset_to_top 找到完整对象</text>
  <text class="cc1ink" x="520" y="182">② typeinfo 给出真实类型</text>
  <text class="cc1ink" x="520" y="204">③ 在基类图里找目标 Q</text>
  <text class="cc1ink" x="520" y="226">找到：返回调整后的指针</text>
  <text class="cc1ink" x="520" y="248">找不到：nullptr / bad_cast</text>
  <text class="cc1mut" x="30" y="284">typeinfo 挂在 vtable 上，所以源类型要有虚函数；继承层次越深、越复杂，查得越久。</text>
</svg>

1. 通过 vptr 拿到 vtable，读 `offset_to_top`，找到完整对象的开头。`p` 可能指向一个中间的基类子对象，先回到整个对象才能谈“它是什么类型”。
2. 读 vtable 里的 typeinfo 指针，得到完整对象的真实类型。
3. 在这个类型的基类图里找目标类型。单继承链上只要往上比一串 typeinfo；多继承、虚继承时还要确认目标基类是唯一的、`public` 的，找到后算出它在完整对象里的偏移。

vtable 里的 `offset_to_top` 和 typeinfo 这两格，[对象布局](/zh/ref/object-layout/)那页有图。

### 2.3 代价：一次库函数调用 {#dynamic-cost}

`static_cast` 是一条加减法，`dynamic_cast` 是一次读几次内存、比几次 typeinfo 的函数调用，还挡住了内联。本机（GCC 16.2，`-O2`）对一个单继承、命中的 `dynamic_cast` 循环计时，大约 3–4 ns 一次，同样的循环换成 `static_cast` 不到 0.3 ns。继承层次越深，或者 typeinfo 要按名字比较（跨动态库时可能如此），它越慢。

偶尔用一次，这点开销无所谓。频繁地 `dynamic_cast` 往往说明设计在绕路：调用方需要先问“你到底是哪个子类”，通常是因为该放进虚函数里的行为放在了外面。把这件事做成虚函数，由对象自己去做，类型判断就省了（见[虚函数](/zh/ref/virtual-functions/)）。

## 3. const_cast：只去掉 const

### 3.1 合法用法：对象本身不是 const {#const-ok}

`const_cast` 只能加上或去掉 `const`、`volatile`，别的什么都不改。它存在的理由是对接写得不严谨的接口：一个老的 C 函数参数写成 `char*`，实际只读不写，你手里只有 `const char*`，就用 `const_cast` 去掉 `const` 传过去。另一个常见用法是让 `const` 和非 `const` 两个版本的成员函数共用一份实现：非 `const` 版本调 `const` 版本，再把结果的 `const` 去掉，这时对象本来就不是 `const`，去掉没有问题。

### 3.2 对象本来就是 const 时，写它是未定义行为 {#const-ub}

能不能通过去掉 `const` 的指针去写，取决于对象本身，而不是指针：对象定义时不是 `const`，只是被一个 `const` 指针指着，写没问题；**对象定义时就是 `const`，怎么转都不能写，写了就是未定义行为。** 原因有两个，都能看到：

```cpp
const int a = 10;
int* pa = const_cast<int*>(&a);
*pa = 20;
std::printf("a=%d *pa=%d\n", a, *pa);   // 打印 a=10 *pa=20
```

同一个地址，读出来两个值。编译器知道 `a` 是 `const`、初值是 10，用到 `a` 的地方直接换成了常数 10，根本不去读内存。

如果 `const` 对象是全局的，编译器把它放进只读段（Linux 上是 `.rodata`），这一页映射成只读，写它的那条指令直接触发段错误。本机把上面的 `a` 换成全局的 `const int limit = 100;` 去写，程序就崩在这一行。

## 4. reinterpret_cast：不改任何位，换个类型来看

### 4.1 能做什么 {#reinterpret-what}

`reinterpret_cast` 把一个指针原样当作另一个不相关类型的指针，或者在指针和整数（`std::uintptr_t`）之间转换。它不生成任何指令，只是告诉编译器“从现在起按这个类型看”。常见的合法用途：把指针转成整数打印、对齐检查、存进只收整数的接口里，再转回来；按字节看任何对象，转成 `char*`、`unsigned char*` 或 `std::byte*`；系统调用和网络接口约定好的转换，比如 `sockaddr_in*` 转 `sockaddr*`。

### 4.2 严格别名：换个类型去读写，编译器不认 {#strict-aliasing}

麻烦在“转完以后去读写”。C++ 有一条严格别名（strict aliasing）规则：**一个对象只能通过它自己的类型（或 `char`、`unsigned char`、`std::byte`）去访问。** 编译器依赖这条规则做优化：它认为 `int*` 和 `float*` 不会指向同一块内存，所以通过 `float*` 写入不会改变 `int*` 读到的值。

```cpp
int alias(int* i, float* f) { *i = 1; *f = 2.0f; return *i; }
```

```asm
_Z5aliasPiPf:                     # g++ -O2，x86-64
        movl    $1, (%rdi)            # *i = 1
        movl    $1, %eax              # 返回值直接定成 1，不再读 *i
        movl    $0x40000000, (%rsi)   # *f = 2.0f
        ret
```

把同一块内存的两个指针传进去，`alias(&buf, reinterpret_cast<float*>(&buf))`：`-O2` 下返回 1，可内存里实际是 `0x40000000`（2.0f 的位）；`-O0` 下不做这个优化，返回 1073741824，也就是把这 4 个字节当 `int` 读。同一份代码，优化级别不同结果就不同，这就是未定义行为的样子。

### 4.3 要看一个值的字节：memcpy 或 std::bit_cast {#bit-cast}

想知道一个 `float` 的二进制位，正确的写法是把字节拷出来，而不是换个指针去读：

```cpp
float f = 2.0f;
std::uint32_t u1;
std::memcpy(&u1, &f, sizeof u1);                   // 一直都对
auto u2 = std::bit_cast<std::uint32_t>(f);         // C++20，两边大小必须一样，还能在编译期用
```

两种写法都不会真的去调 `memcpy`，编译出来就是一条寄存器之间的移动：

```asm
_Z4bitsf:                         # bit_cast<unsigned>(f)，g++ -O2
        movd    %xmm0, %eax           # 浮点寄存器里的 32 位原样搬到整数寄存器
        ret
```

## 5. C 风格转换：替你挑一种

### 5.1 它按顺序试，试中哪个用哪个 {#c-style-order}

`(T)x` 和函数式的 `T(x)` 不是第五种转换，它依次尝试：`const_cast`；`static_cast`；`static_cast` 再加 `const_cast`；`reinterpret_cast`；`reinterpret_cast` 再加 `const_cast`。第一种能编译通过的就是结果。所以同样写 `(T)x`，有时是安全的数值转换，有时去掉了 `const`，有时是 `reinterpret_cast`，代码上看不出区别，搜索代码时也很难把它们找出来。

### 5.2 类型没定义完整时，悄悄退成 reinterpret_cast {#c-style-trap}

最隐蔽的情况和 1.2 节的指针偏移有关。在一个文件里，`C` 只有前向声明 `struct C;`，没有定义：

```cpp
struct B { int b; };
struct C;                          // 只声明
C* to_c(B* p) { return (C*)p; }    // C 风格转换
```

编译器不知道 `C` 继承了 `B`，`static_cast` 试不通，于是它选了 `reinterpret_cast`，不报错，也不减 4。在另一个文件里用完整定义的 `C` 调它，本机打出来是：

```text
&obj=0000003135fffcf4  (C*)pb with C complete=0000003135fffcf4  (C*)pb in a file where C is incomplete=0000003135fffcf8
```

同一个转换，在知道 `C` 定义的文件里得到对象开头，在不知道的文件里差了 4 字节。如果这里写的是 `static_cast<C*>(p)`，类型不完整时会直接编译报错，问题当场暴露。**C++ 风格转换的价值就在这里：你说清楚要哪一种，做不到时编译器拒绝，而不是换一种去做。**

上面的汇编和输出都来自本机 GCC 16.2（`-std=c++20`）编译、运行的结果；汇编是加 `-mabi=sysv` 生成的 Linux 调用约定版本，运行在 Windows 上，地址格式是 MinGW 的 `%p`。
