---
title: "lambda 和 std::function：闭包对象、捕获和类型擦除"
date: 2026-11-02
slug: "lambda-function"
description: "lambda 是编译器替你写的一个类的对象：捕获的变量是它的成员，函数体是它的 operator()。按值捕获在创建时拷一份，按引用捕获只存一个地址，[=] 不会拷全局变量，在成员函数里拷的是 this 指针；初始化捕获能把 unique_ptr 搬进去。每个 lambda 都是一个新类型，要统一存放就得用 std::function：它用类型擦除把任何可调用的东西装进一个 32 字节的对象，代价是捕获大了要分配堆内存，调用多一次间接跳转、没法内联，而且只能装可拷贝的东西。"
summary: "lambda 就是一个带 operator() 的类，按模板传进去和手写函数一样快；std::function 换来的是“任何可调用的东西都能放进同一个类型”，付出的是可能的堆分配和一次不能内联的间接调用。捕获引用时，被捕获的变量得比 lambda 活得久。"
toc: true
group: cpplinux
topic: cpp
weight: 106
---

排序时传一个比较规则，注册一个“数据到了就调用”的回调，开线程时告诉它要跑什么：这些地方都要把“一段代码”当成值传来传去。C++ 里最常用的写法是 lambda，存起来的时候常用 `std::function`。两样东西用起来很像，编译出来却差很多。

## 1. lambda 是一个类的对象

### 1.1 编译器替你写了一个类 {#closure}

写下一个 lambda，编译器就生成一个没有名字的类：捕获的变量是它的成员，函数体是它的 `operator()`。lambda 表达式本身得到的，是这个类的一个对象，叫闭包（closure）。下面两种写法编译出来一样：

```cpp
int k = 3;
auto f = [k](int y) { return k * y; };          // lambda

struct Closure {                                 // 编译器替你写的，大致就是这个
    int k;
    int operator()(int y) const { return k * y; }
};
Closure g{k};
```

所以闭包对象有多大，就看捕获了什么。用 GCC 16.2 打出来：不捕获的 lambda `sizeof` 是 1（空类也要占 1 字节），按值捕获一个 `int` 是 4，按引用捕获一个 `int` 是 8，存的是一个地址。

<svg viewBox="0 0 760 296" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="三种 lambda 生成的闭包对象：不捕获时没有成员，大小 1 字节；按值捕获 x 时对象里有一份 x 的副本，4 字节；按引用捕获 x 时对象里存的是 x 的地址，8 字节，指向栈上的 x" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .lf0bg  { fill: #fbfaf7; }
    .lf0src { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .lf0obj { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .lf0emp { fill: none; stroke: #6f8f3f; stroke-width: 1.3; stroke-dasharray: 5 4; }
    .lf0var { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .lf0ink { fill: #1c1b18; font-size: 12.5px; }
    .lf0mono{ fill: #1c1b18; font-size: 12.5px; font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .lf0mut { fill: #6b6558; font-size: 12px; }
    .lf0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .lf0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .lf0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0src { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0obj { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0emp { stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0var { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0ink, :root:is([data-theme="dark"], [data-theme="black"]) .lf0mono, :root:is([data-theme="dark"], [data-theme="black"]) .lf0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf0hd { fill: #a19caf; }
  </style>
  <defs><marker id="lf0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="lf0hd"/></marker></defs>
  <rect class="lf0bg" x="0" y="0" width="760" height="296" rx="10"/>
  <text class="lf0ttl" x="30" y="30">不捕获</text>
  <text class="lf0ttl" x="280" y="30">按值捕获 x</text>
  <text class="lf0ttl" x="530" y="30">按引用捕获 x</text>
  <rect class="lf0src" x="30" y="42" width="210" height="36" rx="6"/>
  <text class="lf0mono" x="44" y="65">[](int y) { … }</text>
  <rect class="lf0src" x="280" y="42" width="210" height="36" rx="6"/>
  <text class="lf0mono" x="294" y="65">[x](int y) { … }</text>
  <rect class="lf0src" x="530" y="42" width="210" height="36" rx="6"/>
  <text class="lf0mono" x="544" y="65">[&amp;x](int y) { … }</text>
  <path class="lf0ln" d="M135,78 L135,105" marker-end="url(#lf0a)"/>
  <path class="lf0ln" d="M385,78 L385,105" marker-end="url(#lf0a)"/>
  <path class="lf0ln" d="M635,78 L635,105" marker-end="url(#lf0a)"/>
  <rect class="lf0emp" x="30" y="108" width="210" height="44" rx="6"/>
  <text class="lf0ink" x="44" y="135">没有成员</text>
  <text class="lf0mut" x="30" y="172">sizeof = 1</text>
  <rect class="lf0obj" x="280" y="108" width="210" height="44" rx="6"/>
  <text class="lf0ink" x="294" y="135">int x = 10（创建时的副本）</text>
  <text class="lf0mut" x="280" y="172">sizeof = 4</text>
  <text class="lf0mut" x="280" y="200">外面的 x 再改，副本不变</text>
  <rect class="lf0obj" x="530" y="108" width="210" height="44" rx="6"/>
  <text class="lf0ink" x="544" y="135">int&amp; x：存的是地址</text>
  <text class="lf0mut" x="530" y="172">sizeof = 8</text>
  <path class="lf0ln" d="M700,152 L700,205" marker-end="url(#lf0a)"/>
  <rect class="lf0var" x="600" y="208" width="140" height="36" rx="6"/>
  <text class="lf0ink" x="614" y="231">栈上的 x</text>
  <text class="lf0mut" x="30" y="278">捕获的变量就是这个类的成员：按值存一份，按引用存一个地址。函数体是它的 operator()，默认是 const 成员函数。</text>
</svg>

**闭包就是一个普通的类，所以它的调用和手写的函数对象一样快。** 把 lambda 传给一个模板函数，编译器知道调的是哪个 `operator()`，能整个内联进来：

```cpp
template <class F> int apply3(F f) { return f(3); }
int by_template(int k) { return apply3([k](int y) { return k * y; }); }
```

```asm
_Z11by_templatei:                 # g++ -O2，x86-64
        leal    (%rdi,%rdi,2), %eax   # k * 3，lambda 已经内联没了
        ret
```

### 1.2 每个 lambda 都是一个新类型 {#unique-type}

两个一模一样的 lambda 也是两个不同的类：`std::is_same_v<decltype(l1), decltype(l2)>` 是 `false`。这个类型没有名字，写不出来，所以存 lambda 只能用 `auto`，或者让模板去推导。这也是 `std::sort(v.begin(), v.end(), [](int a, int b) { return a > b; })` 快的原因：`sort` 为这个比较规则单独实例化一份，比较直接内联进排序循环。

参数写成 `auto` 的 lambda（C++14 起）叫泛型 lambda，它的 `operator()` 是一个模板，每种实参类型实例化一份：

```cpp
auto print = [](const auto& v) { std::cout << v << '\n'; };
print(1);        // operator()<int>
print("hi");     // operator()<char[3]>
```

不捕获任何东西的 lambda 没有成员，不依赖哪个对象，所以能隐式转成普通函数指针。这正好用在只收函数指针的 C 接口上，比如 `qsort` 的比较函数、`pthread_create` 的线程入口：

```cpp
int (*fp)(int) = [](int v) { return v + 1; };   // 只有不捕获的 lambda 才能这样转
```

## 2. 捕获

### 2.1 按值捕获：创建时拷一份 {#by-value}

`[x]` 在 lambda 被创建的那一刻把 `x` 拷进闭包对象，之后外面的 `x` 怎么变，闭包里的都不变：

```cpp
int x = 10;
auto by_value = [x](int y) { return x * y; };
x = 20;
by_value(4);      // 40：用的还是创建时的 10
```

`operator()` 默认是 `const` 成员函数，所以函数体里不能改按值捕获的成员。要改，加 `mutable`。改的是闭包自己的那份，每个闭包对象各有一份状态：

```cpp
auto counter = [n = 0]() mutable { return ++n; };
auto copy = counter;          // 拷贝的是整个闭包对象，n 也拷了一份
counter(); counter();
counter();                    // 3
copy();                       // 1：copy 有自己的 n
```

### 2.2 按引用捕获：存的是地址，活多久要你管 {#by-ref}

`[&z]` 只存 `z` 的地址，每次调用都去读 `z` 现在的值，所以看得到外面的修改。代价是生命周期：**闭包只拿着一个地址，被捕获的变量没了，地址就悬空了。** 最典型的是把它带出了作用域：

```cpp
std::function<int()> make_counter() {
    int n = 0;
    return [&n] { return ++n; };   // 返回以后 n 已经没了，调用就是未定义行为
}
```

异步回调是同一个问题换了个样子：登记一个按引用捕获局部变量（或者捕获了 `this`）的回调，函数返回了，回调要过一会儿才执行，那时它引用的东西早已销毁。解决办法是让闭包自己持有它要的东西：按值捕获；对象由 `shared_ptr` 管的，捕获一份 `shared_ptr`，成员函数里用 `shared_from_this()` 拿（见 [智能指针那页](/zh/ref/smart-pointers/#shared-from-this-right)）。

### 2.3 [=] 和 [&]：捕获了什么，没捕获什么 {#default-capture}

`[=]`、`[&]` 不是把所有变量都拷一遍，而是函数体里用到哪个局部变量，就按值或按引用捕获哪个。有两类东西不在其中：

- **全局变量和 `static` 变量不捕获。** 它们一直在，不需要捕获，函数体里直接用。所以 `[=]` 里读全局变量 `g`，读到的是调用时的值：先创建闭包，再把 `g` 从 1 改成 7，闭包返回的是 7，不是创建时的 1。
- **成员变量不单独捕获，捕获的是 `this` 指针。** 成员函数里写 `[=] { return count_; }`，`count_` 其实是 `this->count_`，闭包里存的只是 `this`。看着像按值捕获，其实是通过指针读；对象销毁以后再调用，照样悬空。

所以 C++20 起，`[=]` 隐式捕获 `this` 被标为弃用，要捕获就明着写 `[this]`；想要一份对象的副本，C++17 起写 `[*this]`。

### 2.4 初始化捕获：把对象搬进去 {#init-capture}

C++14 起可以在捕获列表里定义一个新成员并给它初值，最常用来把只能移动的对象搬进闭包：

```cpp
auto up = std::make_unique<int>(42);
auto owner = [p = std::move(up)] { return *p; };   // 现在 p 归闭包所有，up 是空的
```

闭包有一个 `unique_ptr` 成员，它自己也就只能移动、不能拷贝（`std::is_copy_constructible_v` 是 `false`）。这一点在下一节会碰到。

## 3. std::function：能装下任何可调用的东西

### 3.1 类型擦除：把不同的类型装进同一个类型 {#type-erasure}

每个 lambda 一个类型，可很多地方要的是一个统一的类型：一个回调表 `std::vector<回调>`，一个类的成员 `回调 on_message_`，它们不能是模板。`std::function<int(int)>` 就是这个统一的类型：任何能用 `int` 调用、返回 `int` 的东西（lambda、函数指针、函数对象、绑定了对象的成员函数）都能放进去。

它的做法叫类型擦除（type erasure）：对象里不记“装的是什么类型”，只记两个函数指针，一个负责调用，一个负责拷贝和销毁。这两个函数是在赋值那一刻、按真实类型实例化出来的。libstdc++ 里一个 `std::function` 是 32 字节：

<svg viewBox="0 0 760 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="libstdc++ 的 std::function 是 32 字节：前 16 字节是小缓冲，接着是 manager 和 invoker 两个函数指针。小而且可以平凡拷贝的闭包直接放进小缓冲；大的或者拷贝不平凡的闭包放在堆上，小缓冲里存它的指针。调用时先检查 manager 是否为空，再通过 invoker 间接调用闭包的 operator()" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .lf1bg  { fill: #fbfaf7; }
    .lf1cell{ fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .lf1buf { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .lf1heap{ fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .lf1ink { fill: #1c1b18; font-size: 12.5px; }
    .lf1mut { fill: #6b6558; font-size: 12px; }
    .lf1ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .lf1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .lf1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1cell { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1buf { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1heap { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1ink, :root:is([data-theme="dark"], [data-theme="black"]) .lf1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .lf1hd { fill: #a19caf; }
  </style>
  <defs><marker id="lf1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="lf1hd"/></marker></defs>
  <rect class="lf1bg" x="0" y="0" width="760" height="290" rx="10"/>
  <text class="lf1ttl" x="40" y="30">std::function&lt;int(int)&gt;：32 字节</text>
  <text class="lf1mut" x="40" y="54">0</text>
  <text class="lf1mut" x="360" y="54">16</text>
  <text class="lf1mut" x="520" y="54">24</text>
  <text class="lf1mut" x="666" y="54">32</text>
  <rect class="lf1buf" x="40" y="60" width="320" height="36"/>
  <text class="lf1ink" x="56" y="83">小缓冲（16 字节）</text>
  <rect class="lf1cell" x="360" y="60" width="160" height="36"/>
  <text class="lf1ink" x="376" y="83">manager 指针</text>
  <rect class="lf1cell" x="520" y="60" width="160" height="36"/>
  <text class="lf1ink" x="536" y="83">invoker 指针</text>
  <path class="lf1ln" d="M120,96 L120,127" marker-end="url(#lf1a)"/>
  <path class="lf1ln" d="M320,96 L320,187" marker-end="url(#lf1a)"/>
  <rect class="lf1buf" x="40" y="130" width="250" height="40" rx="6"/>
  <text class="lf1ink" x="54" y="155">小闭包：直接放在小缓冲里</text>
  <rect class="lf1heap" x="40" y="190" width="300" height="56" rx="6"/>
  <text class="lf1ink" x="54" y="212">大闭包，或拷贝不平凡的闭包：</text>
  <text class="lf1ink" x="54" y="232">放在堆上，小缓冲里只存它的指针</text>
  <path class="lf1ln" d="M440,96 L440,197" marker-end="url(#lf1a)"/>
  <rect class="lf1cell" x="380" y="200" width="160" height="46" rx="6"/>
  <text class="lf1ink" x="394" y="228">拷贝、销毁闭包</text>
  <path class="lf1ln" d="M600,96 L600,127" marker-end="url(#lf1a)"/>
  <rect class="lf1cell" x="560" y="130" width="180" height="46" rx="6"/>
  <text class="lf1ink" x="574" y="158">转去调闭包的 operator()</text>
  <text class="lf1mut" x="40" y="276">调用 f(3)：manager 为空就抛 bad_function_call，否则 call *24(%rdi) 跳到 invoker。</text>
</svg>

### 3.2 代价：可能分配，调用不能内联 {#function-cost}

第一笔是内存。闭包放不进 16 字节的小缓冲，赋值时就要 `new` 一块堆内存。libstdc++ 还多一个条件：闭包得能平凡拷贝（按字节拷就行），才放进小缓冲。把不同的 lambda 赋给 `std::function`，数一次 `operator new`：

| 捕获了什么 | 闭包大小 | 赋值时分配几次 |
|---|---|---|
| 一个 `int` | 4 B | 0 |
| 一个指针加一个 `int` | 16 B | 0 |
| 三个 `long long` | 24 B | 1：超过 16 字节 |
| 一个 `shared_ptr` | 16 B | 1：放得下，但拷贝它要改引用计数，不平凡 |

（GCC 16.2，libstdc++。别的标准库的缓冲大小和规则不一样，MSVC 和 libc++ 都更大一些。）

第二笔是调用。同一个 `f(3)`，通过 `std::function` 调：

```cpp
int by_function(const std::function<int(int)>& f) { return f(3); }
```

```asm
_Z11by_functionRKSt8functionIFiiEE:   # g++ -O2，x86-64
        subq    $24, %rsp
        movl    $3, 12(%rsp)          # 参数 3 放到栈上，按地址传给 invoker
        cmpq    $0, 16(%rdi)          # manager 为空 = 没装东西
        je      .L5                   # → 抛 bad_function_call
        leaq    12(%rsp), %rsi
        call    *24(%rdi)             # 间接调用 invoker
        addq    $24, %rsp
        ret
```

和 1.1 节模板版本的那一条 `leal` 比，多了判空、一次间接调用，参数还得经过内存。**更重要的是编译器不知道 `24(%rdi)` 里是哪个函数，没法内联，也就没法跨这次调用做优化**，和[虚函数](/zh/ref/virtual-functions/#virtual-cost)挡住内联是同一件事。函数体本身要跑很久时，这点差别看不出来；函数体只有一两条指令、又要调很多次时，差别就是好几倍。

### 3.3 只能装能拷贝的：move_only_function {#move-only}

`std::function` 自己能拷贝，拷贝时要把装着的闭包也拷一份，所以它要求闭包可拷贝。把 2.4 节那个持有 `unique_ptr` 的闭包塞进去，编译报错：

```text
error: static assertion failed: std::function target must be copy-constructible
```

C++23 加了 `std::move_only_function`，它自己只能移动，也就不要求闭包可拷贝，装这种闭包正好。用 C++23 之前的标准，常见的绕法是改捕获 `shared_ptr`，代价是多一次引用计数。

### 3.4 怎么选 {#choose}

- **调用的地方在编译期就知道是哪个函数**（传给算法、传给一个立刻就用的函数）：参数写成模板或 `auto`，lambda 照原样传进去，能内联。
- **要存起来，或者要把不同的 lambda 放在一起**（回调表、类成员、跨编译单元的接口）：`std::function`；装的东西只能移动时用 `std::move_only_function`。
- **对接只收函数指针的 C 接口**：不捕获的 lambda 直接转成函数指针；要带状态，就靠接口另给的 `void*` 参数把状态传进去。

上面的数字和汇编，都来自本机 GCC 16.2（`-std=c++23 -O2`）编译、运行的结果；汇编是加 `-mabi=sysv` 生成的 Linux 调用约定版本。
