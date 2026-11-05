---
title: "智能指针：unique_ptr、shared_ptr 和 weak_ptr"
date: 2026-11-02
slug: "smart-pointers"
translationKey: "smart-pointers"
description: "智能指针把“谁负责释放”写进类型。unique_ptr 独占一个对象，只能移动不能拷贝，默认和裸指针一样是 8 字节，自定义删除器能管文件和 C 库资源。shared_ptr 是对象加一块存计数的控制块，复制它是拷两个指针加一次计数加 1，多线程时是一次原子操作；多线程下只有计数是安全的。weak_ptr 指向控制块但不加 use_count，用 lock() 安全地取对象，能打破循环引用。成员函数里要拿到自己的 shared_ptr，继承 enable_shared_from_this 再调 shared_from_this()。最后是三种怎么选。"
summary: "默认用 unique_ptr：所有权只有一份，大小和裸指针一样。对象的寿命真要由几方共同决定时才用 shared_ptr，复制要付一次原子加，线程安全的只有计数；指回去的边、观察者、缓存用 weak_ptr，用之前 lock() 一下。"
toc: true
group: cpplinux
topic: mem
weight: 110
aliases: ["/posts/shared-ptr/", "/ref/shared-ptr/", "/ref/unique-ptr-weak-ptr/"]
---

## 1. 所有权写进类型

### 1.1 裸指针说不清谁来 delete {#raw-pointer}

函数返回一个 `Widget*`，调用方拿到以后要不要 `delete`？光看类型看不出来：它可能是新 `new` 出来交给你的，也可能指着别人管着的对象。猜错了就是两种结果之一：没人 `delete`，内存泄漏；两个人都 `delete`，同一块内存释放两次。中途抛个异常、提前 `return`，本该执行的 `delete` 也会被跳过。

智能指针的做法是把“谁负责释放”写进类型：持有 `unique_ptr<Widget>` 的就是唯一的主人，持有 `shared_ptr<Widget>` 的是主人之一，拿着 `Widget*` 或 `Widget&` 的只是借用。**释放这件事交给析构函数**：智能指针离开作用域时，析构函数里调 `delete`，不管是正常走完、提前返回还是抛了异常，析构函数都会执行。这就是 RAII（资源的生命期绑在对象的生命期上），见 [构造、析构和 RAII](/zh/ref/special-members-raii/)。

## 2. unique_ptr：独占，只能移动

### 2.1 只能移动，不能拷贝 {#move-only}

“独占”的意思是同一时刻只有一个 `unique_ptr` 指着这个对象。要做到这一点，它把拷贝构造和拷贝赋值删掉了（`= delete`），写 `auto q = p;` 直接编译不过。所有权可以转交，但要明着写 `std::move`：移动构造把指针拿过来，再把原来那个置空，于是原来的 `unique_ptr` 析构时什么也不做，对象只会被释放一次。

```cpp
std::unique_ptr<Widget> make() {
    auto p = std::make_unique<Widget>();
    p->v = 42;
    return p;                                   // 返回局部变量：自动移动，不用写 std::move
}
void sink(std::unique_ptr<Widget> p) { std::printf("sink got %d\n", p->v); }  // 拿走所有权
void use(const Widget& w) { std::printf("use %d\n", w.v); }                    // 只是用一下

auto w = make();
use(*w);
sink(std::move(w));                             // 所有权交给 sink，w 变成空
std::printf("after sink: w is %s\n", w ? "set" : "null");
```

用 GCC 16.2 跑出来是 `use 42`、`sink got 42`、`~Widget`、`after sink: w is null`：`Widget` 在 `sink` 返回时就析构了，因为那时它的主人是 `sink` 的参数。

<svg viewBox="0 0 760 262" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="一个 Widget 的所有权依次从 make 里的 p 交给 main 里的 w，再交给 sink 的参数 p；交出去的那个变成空指针，任何时刻只有一个 unique_ptr 指向 Widget，sink 返回时析构它" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .uq0bg  { fill: #fbfaf7; }
    .uq0p   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .uq0own { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .uq0obj { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .uq0ink { fill: #1c1b18; font-size: 13px; }
    .uq0mut { fill: #6b6558; font-size: 12px; }
    .uq0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .uq0own2 { stroke: #6f8f3f; stroke-width: 1.8; fill: none; }
    .uq0hd  { fill: #6b6558; }
    .uq0hd2 { fill: #6f8f3f; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0p { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0own { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0obj { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0own2 { stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0hd { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq0hd2 { fill: #8fb257; }
  </style>
  <defs>
    <marker id="uq0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="uq0hd"/></marker>
    <marker id="uq0b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="uq0hd2"/></marker>
  </defs>
  <rect class="uq0bg" x="0" y="0" width="760" height="262" rx="10"/>
  <text class="uq0mut" x="24" y="34">make() 里的 p</text>
  <rect class="uq0p" x="24" y="44" width="180" height="48" rx="6"/>
  <text class="uq0ink" x="40" y="73">空（交出去了）</text>
  <text class="uq0mut" x="290" y="34">main 里的 w</text>
  <rect class="uq0p" x="290" y="44" width="180" height="48" rx="6"/>
  <text class="uq0ink" x="306" y="73">空（交出去了）</text>
  <text class="uq0mut" x="556" y="34">sink 的参数 p</text>
  <rect class="uq0own" x="556" y="44" width="180" height="48" rx="6"/>
  <text class="uq0ink" x="572" y="73">现在的主人</text>
  <path class="uq0ln" d="M204,68 L287,68" marker-end="url(#uq0a)"/>
  <path class="uq0ln" d="M470,68 L553,68" marker-end="url(#uq0a)"/>
  <text class="uq0mut" x="212" y="112">return p</text>
  <text class="uq0mut" x="212" y="128">（自动移动）</text>
  <text class="uq0mut" x="478" y="112">sink(</text>
  <text class="uq0mut" x="478" y="128">std::move(w))</text>
  <rect class="uq0obj" x="556" y="164" width="180" height="48" rx="6"/>
  <text class="uq0ink" x="572" y="193">Widget（堆上）</text>
  <path class="uq0own2" d="M646,92 L646,161" marker-end="url(#uq0b)"/>
  <text class="uq0mut" x="24" y="190">一直只有这一个 Widget，被转交的只是指着它的那个 8 字节指针。</text>
  <text class="uq0mut" x="24" y="244">交出去的 unique_ptr 被置空，析构时什么也不做；sink 返回时它的参数析构，Widget 跟着释放。</text>
</svg>

### 2.2 和裸指针一样大 {#size}

默认的 `unique_ptr<T>` 里只有一个指针，析构时调 `delete`，用它没有额外的内存开销。删除器是它的第二个模板参数，是否占空间要看删除器本身有没有状态：

| 类型 | `sizeof`（GCC 16.2，64 位） |
|---|---|
| `unique_ptr<Widget>` | 8 |
| `unique_ptr<Widget[]>` | 8 |
| `unique_ptr<FILE, void(*)(FILE*)>`（函数指针做删除器） | 16 |
| `unique_ptr<FILE, decltype(lambda)>`（不捕获的 lambda） | 8 |
| `unique_ptr<FILE, decltype(lambda)>`（捕获了一个 `int`） | 16 |
| `shared_ptr<Widget>`、`weak_ptr<Widget>` | 16 |

函数指针是一个运行时的值，得存下来，所以多 8 字节。不捕获的 lambda 是一个空类，它要调用的函数在类型里就定了，标准库实现把它放在空基类（或者 `[[no_unique_address]]`）里，不占空间，原理见[对象布局的空类一节](/zh/ref/object-layout/)。**所以写删除器时优先用不捕获的 lambda 或者空的函数对象**，`unique_ptr` 仍然只有 8 字节。

### 2.3 自定义删除器：不只管 new 出来的内存 {#deleter}

`unique_ptr` 管的其实是“离开时要做的一件事”，默认这件事是 `delete`。换成别的删除器，就能管 C 库里成对出现的资源：

```cpp
auto close_file = [](std::FILE* f) { if (f) std::fclose(f); };
std::unique_ptr<std::FILE, decltype(close_file)> f(std::fopen("a.txt", "r"), close_file);
// 离开作用域时 fclose；中途 return、抛异常也一样
```

同样的写法能管 `malloc` 出来的内存（删除器调 `free`）、`opendir` 的目录、各种 C 库的句柄。fd 这种不是指针的资源，`unique_ptr` 装不下，要自己写一个小的 RAII 类。

### 2.4 make_unique 和数组 {#make-unique}

`std::make_unique<T>(args...)`（C++14）在内部 `new`，直接返回 `unique_ptr`，代码里就不再出现裸的 `new`：每个 `new` 都立刻有了主人，不存在“`new` 完、还没交给智能指针，中间抛了异常”的窗口。

`unique_ptr<T[]>` 是数组版本，析构时调的是 `delete[]`，还提供 `operator[]`。它和 `unique_ptr<T>` 不能混用：用单个对象的版本去管 `new T[n]`，析构时调 `delete` 而不是 `delete[]`，是未定义行为。大多数时候数组直接用 `std::vector` 更好，它还记着长度。

### 2.5 函数参数怎么写：看要不要所有权 {#passing}

参数的类型就是函数在声明“我要对这个对象做什么”：

| 参数写成 | 意思 |
|---|---|
| `unique_ptr<T>`（按值） | 我要拿走所有权，调用方得写 `std::move`，之后它手里是空的 |
| `T&`、`const T&`、`T*` | 我只是用一下，不管它活多久；`T*` 表示可以传空 |
| `unique_ptr<T>&` | 我可能要换掉你手里的那个对象（`reset` 成别的），很少用 |

**不需要所有权时，不要传 `unique_ptr` 本身**，传引用或裸指针：这样函数也能用在栈上的对象、别人管着的对象上，不被绑死在“必须由 `unique_ptr` 管理”上。裸指针在这里不危险，因为它只借不还，释放的责任清清楚楚在 `unique_ptr` 那边。

### 2.6 转成 shared_ptr {#to-shared}

一个右值 `unique_ptr` 可以直接用来构造 `shared_ptr`：`std::shared_ptr<Widget> s = make();`，所有权从独占变成共享（反过来不行，共享的所有权收不回独占）。所以工厂函数通常返回 `unique_ptr`：调用方只要一个主人就直接用，要共享就转一下。代价是这样转来的 `shared_ptr` 要另外分配一次控制块，享受不到 `make_shared` 的“一次分配”（[3.1](#shared-ptr)）。


## 3. shared_ptr：共享所有权，计数在控制块里

### 3.1 对象 + 一块存计数的控制块 {#shared-ptr}

`std::shared_ptr<T>` 让好几个地方共同拥有一个对象：谁都可以持有一份，最后一份没了，对象才析构。它靠一个引用计数做到这一点。计数不在对象里，而在一块单独的内存里，叫**控制块**（control block）。

- `std::make_shared<T>()` 只分配一次，对象和控制块挨在一起。
- 每复制一个 `shared_ptr`，计数 +1；每销毁一个，计数 -1；减到 0 就析构对象。
- 一个 `shared_ptr` 本身是两个指针：一个指向对象，一个指向控制块，`sizeof` 是 16 B。

<svg viewBox="0 0 760 304" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="make_shared 一次分配，对象和控制块挨在一起；shared_ptr(new T) 分配两次，控制块里多一个指向对象的指针。两个 shared_ptr 都各存一个对象指针和一个控制块指针。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sp0bg  { fill: #fbfaf7; }
    .sp0p   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .sp0c   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .sp0t   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .sp0box { fill: none; stroke: #6b6558; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .sp0ink { fill: #1c1b18; font-size: 12px; }
    .sp0mut { fill: #6b6558; font-size: 12px; }
    .sp0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .sp0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sp0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0p { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0c { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0t { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0box { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0ink, :root:is([data-theme="dark"], [data-theme="black"]) .sp0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0hd { fill: #a19caf; }
  </style>
  <defs><marker id="sp0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sp0hd"/></marker></defs>
  <rect class="sp0bg" x="0" y="0" width="760" height="304" rx="10"/>
  <text class="sp0ttl" x="24" y="32">std::make_shared&lt;T&gt;()</text>
  <text class="sp0mut" x="26" y="71">p1</text>
  <rect class="sp0p" x="48" y="52" width="110" height="30"/>
  <text class="sp0ink" x="103" y="71" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="158" y="52" width="110" height="30"/>
  <text class="sp0ink" x="213" y="71" text-anchor="middle">控制块指针</text>
  <text class="sp0mut" x="26" y="227">p2</text>
  <rect class="sp0p" x="48" y="208" width="110" height="30"/>
  <text class="sp0ink" x="103" y="227" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="158" y="208" width="110" height="30"/>
  <text class="sp0ink" x="213" y="227" text-anchor="middle">控制块指针</text>
  <rect class="sp0box" x="42" y="114" width="312" height="62" rx="6"/>
  <rect class="sp0t" x="48" y="120" width="110" height="50"/>
  <text class="sp0ink" x="103" y="149" text-anchor="middle">T 对象</text>
  <rect class="sp0c" x="158" y="120" width="46" height="50"/>
  <text class="sp0ink" x="181" y="149" text-anchor="middle">vptr</text>
  <rect class="sp0c" x="204" y="120" width="72" height="50"/>
  <text class="sp0ink" x="240" y="149" text-anchor="middle">use = 2</text>
  <rect class="sp0c" x="276" y="120" width="72" height="50"/>
  <text class="sp0ink" x="312" y="149" text-anchor="middle">weak</text>
  <path class="sp0ln" d="M103,82 L103,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M103,208 L103,173" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M213,82 L213,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M213,208 L213,173" marker-end="url(#sp0a)"/>
  <text class="sp0mut" x="24" y="266">一次分配：对象和控制块挨在一起</text>
  <text class="sp0ttl" x="408" y="32">std::shared_ptr&lt;T&gt;(new T)</text>
  <text class="sp0mut" x="410" y="71">p1</text>
  <rect class="sp0p" x="432" y="52" width="110" height="30"/>
  <text class="sp0ink" x="487" y="71" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="542" y="52" width="110" height="30"/>
  <text class="sp0ink" x="597" y="71" text-anchor="middle">控制块指针</text>
  <text class="sp0mut" x="410" y="227">p2</text>
  <rect class="sp0p" x="432" y="208" width="110" height="30"/>
  <text class="sp0ink" x="487" y="227" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="542" y="208" width="110" height="30"/>
  <text class="sp0ink" x="597" y="227" text-anchor="middle">控制块指针</text>
  <rect class="sp0t" x="432" y="120" width="100" height="50"/>
  <text class="sp0ink" x="482" y="149" text-anchor="middle">T 对象</text>
  <rect class="sp0c" x="552" y="120" width="40" height="50"/>
  <text class="sp0ink" x="572" y="149" text-anchor="middle">vptr</text>
  <rect class="sp0c" x="592" y="120" width="58" height="50"/>
  <text class="sp0ink" x="621" y="149" text-anchor="middle">use = 2</text>
  <rect class="sp0c" x="650" y="120" width="44" height="50"/>
  <text class="sp0ink" x="672" y="149" text-anchor="middle">weak</text>
  <rect class="sp0c" x="694" y="120" width="52" height="50"/>
  <text class="sp0ink" x="720" y="149" text-anchor="middle">ptr→T</text>
  <path class="sp0ln" d="M482,82 L482,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M482,208 L482,173" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M597,82 L597,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M597,208 L597,173" marker-end="url(#sp0a)"/>
  <text class="sp0mut" x="408" y="266">两次分配：控制块里另存一个指向 T 的指针</text>
  <text class="sp0mut" x="24" y="292">两种写法的 use_count 都在控制块偏移 8 处：3.2 里 addl $1, 8(%rdx) 加的就是它。</text>
</svg>

两种写法差在分配次数。`make_shared` 只调一次 `operator new`，对象和控制块在同一块内存里，少一次分配，用对象时顺带碰到的计数也多半在相邻的缓存行。代价在释放：`use_count` 归零时对象照常析构，可它占的那段内存和控制块连在一起，要等 `weak_count` 也归零（最后一个 `weak_ptr` 没了）才能整块还掉。**对象很大、又有 `weak_ptr` 长期挂着时，`make_shared` 会让这块内存一直留着**，这时用 `shared_ptr<T>(new T)` 分开分配，对象析构时它的内存就能先还。

### 3.2 编译出来是什么：复制 = 拷两个指针 + 计数加 1 {#shared-ptr-asm}

```cpp
std::shared_ptr<S> copy_sp(const std::shared_ptr<S>& p) { return p; }
```

```text
movdqu  (%rsi), %xmm0                    # 一次读 16 B：对象指针 + 控制块指针
movups  %xmm0, (%rdi)                    # 写进新的 shared_ptr
movq    8(%rdi), %rdx                    # 控制块地址
testq   %rdx, %rdx
je      .L12                             # 空指针就不用加计数
cmpb    $0, __libc_single_threaded(%rip) # 进程是不是单线程
je      .L14
addl    $1, 8(%rdx)                      # 单线程：普通加 1
ret
.L14:
lock addl $1, 8(%rdx)                    # 多线程：原子加 1
```

`__libc_single_threaded` 是 glibc 维护的标志，进程还没起第二个线程时为真。一旦有了多个线程，每次复制（以及每次销毁时的减 1）都是一次 `lock` 原子操作：没有别的核在抢时约 5–10 ns；几个核同时复制同一个对象的 `shared_ptr` 时，计数所在的缓存行在核之间来回搬（缓存行乒乓），一次要几十到上百 ns。所以频繁调用的函数不要按值传 `shared_ptr`：只是用一下、不需要“拥有”，就传 `const std::shared_ptr<T>&`，或者直接传 `T&` / `T*`。

### 3.3 多线程下安不安全：只有计数是安全的 {#shared-ptr-threads}

问 `shared_ptr` 线程安不安全，先分清楚它涉及的三样东西。它们放在不同的地方，安全与否也各不相同：

<svg viewBox="0 0 760 286" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="线程 A、线程 B 各有自己的 shared_ptr 变量，全局变量 g_cfg 被 A 和 B 同时读写；三个变量都指向同一块内存，里面是 Config 对象和控制块。控制块里的计数原子加减，安全；同一个变量 g_cfg 被同时读写，要同步；对象内容 shared_ptr 不管。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sp3bg  { fill: #fbfaf7; }
    .sp3p   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .sp3c   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .sp3t   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .sp3box { fill: none; stroke: #6b6558; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .sp3warn { fill: none; stroke: #c0563f; stroke-width: 1.5; stroke-dasharray: 6 4; }
    .sp3ink { fill: #1c1b18; font-size: 12px; }
    .sp3mut { fill: #6b6558; font-size: 12px; }
    .sp3red { fill: #b04a35; font-size: 12px; }
    .sp3ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sp3hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3p { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3c { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3t { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3box { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3warn { stroke: #e08a74; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3red { fill: #e08a74; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp3hd { fill: #a19caf; }
  </style>
  <defs><marker id="sp3a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sp3hd"/></marker></defs>
  <rect class="sp3bg" x="0" y="0" width="760" height="286" rx="10"/>
  <text class="sp3mut" x="24" y="64">线程 A 自己的一份</text>
  <rect class="sp3p" x="180" y="44" width="100" height="30"/>
  <text class="sp3ink" x="230" y="63" text-anchor="middle">对象指针</text>
  <rect class="sp3p" x="280" y="44" width="110" height="30"/>
  <text class="sp3ink" x="335" y="63" text-anchor="middle">控制块指针</text>
  <text class="sp3mut" x="24" y="116">线程 B 自己的一份</text>
  <rect class="sp3p" x="180" y="96" width="100" height="30"/>
  <text class="sp3ink" x="230" y="115" text-anchor="middle">对象指针</text>
  <rect class="sp3p" x="280" y="96" width="110" height="30"/>
  <text class="sp3ink" x="335" y="115" text-anchor="middle">控制块指针</text>
  <text class="sp3mut" x="24" y="190">全局变量 g_cfg</text>
  <text class="sp3mut" x="24" y="208">A 和 B 都直接读写它</text>
  <rect class="sp3warn" x="170" y="164" width="230" height="50" rx="6"/>
  <rect class="sp3p" x="180" y="174" width="100" height="30"/>
  <text class="sp3ink" x="230" y="193" text-anchor="middle">对象指针</text>
  <rect class="sp3p" x="280" y="174" width="110" height="30"/>
  <text class="sp3ink" x="335" y="193" text-anchor="middle">控制块指针</text>
  <text class="sp3red" x="170" y="234">② 同一个变量，A 赋值、B 同时复制：要同步</text>
  <rect class="sp3box" x="464" y="64" width="278" height="68" rx="6"/>
  <rect class="sp3t" x="470" y="70" width="120" height="56"/>
  <text class="sp3ink" x="530" y="102" text-anchor="middle">Config 对象</text>
  <rect class="sp3c" x="590" y="70" width="80" height="56"/>
  <text class="sp3ink" x="630" y="102" text-anchor="middle">use = 3</text>
  <rect class="sp3c" x="670" y="70" width="66" height="56"/>
  <text class="sp3ink" x="703" y="102" text-anchor="middle">weak</text>
  <path class="sp3ln" d="M390,59 C430,59 424,84 461,84" marker-end="url(#sp3a)"/>
  <path class="sp3ln" d="M390,111 C428,111 424,98 461,98" marker-end="url(#sp3a)"/>
  <path class="sp3ln" d="M400,189 C440,189 426,114 461,114" marker-end="url(#sp3a)"/>
  <text class="sp3mut" x="470" y="156">① 计数：原子加减，安全</text>
  <text class="sp3mut" x="470" y="178">③ 对象里的数据：shared_ptr 不管</text>
  <text class="sp3mut" x="24" y="268">线程 A、B 自己的那份是不同的变量，只共用控制块里的计数；g_cfg 是同一个变量，A 和 B 都在直接读写它。</text>
</svg>

- **① 控制块里的计数是线程安全的**：指向同一个对象的所有 `shared_ptr` 共用这一个计数，不管它们在哪个线程里，复制一份就 +1，销毁一份就 −1。标准库知道这个计数一定会被几个线程同时改，所以用 3.2 里那条 `lock` 原子指令来加减它。最后放手的那个线程把它减到 0、析构对象，对象只会析构一次。
- **② `shared_ptr` 变量本身不是线程安全的**：一个 `shared_ptr` 变量就是两个指针，和一个装着两个指针的普通 `struct` 没有区别。标准库对它的保证和对一个 `int` 变量一样：几个线程同时读它（包括同时从它复制）没问题，只要有一个线程在写它，别的线程就不能同时读写。
- **③ 指向的对象不受保护**：`shared_ptr` 只管对象什么时候析构，不管对象里的数据。两个线程通过各自的 `shared_ptr` 同时改 `Config` 的成员，照样是数据竞争，要对象自己加锁。

**判断的关键是：几个线程用的是不是同一个 `shared_ptr` 变量。** 每个线程拿着自己的一份时，各是各的变量，只是指向同一个对象，它们之间唯一共用的是计数，而计数是原子的，所以安全。几个线程直接读写同一个变量时，比如一个全局的 `shared_ptr`、一个对象的成员，就落到了第 ② 条。

```cpp
auto cfg = std::make_shared<Config>();
std::thread t1([cfg] { use(*cfg); });   // 按值捕获：t1 有自己的一份，安全
std::thread t2([cfg] { use(*cfg); });   // t2 也有自己的一份，安全

std::shared_ptr<Config> g_cfg;          // 全局变量：两个线程都直接读写它
// 线程 A：g_cfg = std::make_shared<Config>(load());   换一份新配置
// 线程 B：auto c = g_cfg;                              同时复制一份来用，数据竞争
```

**为什么计数是原子的还不够。** 线程 B 的 `auto c = g_cfg;` 分两步：先从 `g_cfg` 读出控制块的地址，再给那个控制块的计数 +1。线程 A 的赋值也分两步：先把 `g_cfg` 的两个指针改成新配置的，再给旧控制块的计数 −1。两边的 +1、−1 各自都是原子的，可 B 的“读地址”和“+1”之间有空隙，A 的赋值能插进来：

| 时刻 | 线程 B：`auto c = g_cfg;` | 线程 A：`g_cfg = 新配置;` | 旧配置 |
|---|---|---|---|
| 1 | 读出 `g_cfg` 里的控制块地址，是旧配置的 | | 计数 1，只有 `g_cfg` 这一份 |
| 2 | | 把 `g_cfg` 的两个指针改成新配置的 | 计数还是 1 |
| 3 | | 给旧控制块 −1，减到 0：析构旧配置，释放控制块 | 已经释放 |
| 4 | 给时刻 1 读到的旧控制块 +1 | | 写进了已经释放的内存 |
| 5 | 拿着旧配置的地址去用 | | 用的是已经析构的对象 |

**原子的只是计数这一个整数，不是“读出指针、再加计数”这一整套。** 要修，就得把这一整套变成一个整体，让赋值插不进来：

- **C++20 起用 `std::atomic<std::shared_ptr<Config>>`**：线程 A 调 `g_cfg.store(p)`，线程 B 调 `g_cfg.load()`。`load()` 把读指针和加计数做成一次不可分割的操作，`store()` 插不到中间。
- **C++20 之前用 `std::atomic_load(&g_cfg)` 和 `std::atomic_store(&g_cfg, p)`**：作用和上面一样，只是作用在普通的 `shared_ptr` 变量上，C++20 起标为不推荐（deprecated）。
- **用一把互斥锁保护这个变量**：读的一方在锁里复制出一份，出了锁再用这份副本；写的一方在锁里赋值。锁只护住复制和赋值的那一下，用配置的时候不用锁着。

前两种在 libstdc++ 里都不是无锁的：GCC 16 实测 `std::atomic<std::shared_ptr<int>>::is_lock_free()` 返回 `false`，内部还是靠锁。

三条合起来，就是“后台换配置”的常见写法。配置对象做成只读的 `std::shared_ptr<const Config>`，发布以后谁也不改它，第 ③ 条就不用操心；全局那个变量用 `atomic<shared_ptr>` 或者锁来读写，管住第 ② 条；读的线程先 `load()` 出自己的一份再用，就算写的线程这时已经换上了新配置，它手里这份也还活着，靠的是第 ① 条。**要改配置，就新建一份、改好，再整个换上去，而不是在原来那份上改。**

还有三点常被追问：

- **`use_count()` 在多线程下只能当参考**：读到的那一刻，别的线程可能已经复制或者放掉了一份，所以不能用 `use_count() == 1` 判断“只有我在用，可以放心改”。
- **析构函数在最后放手的那个线程里执行**：哪个线程把计数减到 0，就由哪个线程析构对象。析构要释放大块内存或者关文件时，这段时间就算在那个线程头上。
- **`weak_ptr` 要用 `lock()` 取对象**：`lock()` 把“检查对象还活着”和“计数加 1”做成一次原子操作，先 `expired()` 再用中间有窗口，见 [4.2](#lock)。

## 4. weak_ptr：看着对象，不让它活着

### 4.1 指向控制块，不加 use_count {#weak-what}

`weak_ptr` 只能从 `shared_ptr`（或另一个 `weak_ptr`）得到。它也是两个指针、16 字节，同样指着那块控制块，但它加的是控制块里的 `weak_count`，不是 `use_count`。对象的死活只看 `use_count`：最后一个 `shared_ptr` 没了，对象照样析构，不管还有多少 `weak_ptr` 指着它。

所以 `weak_ptr` 不能直接解引用：它指着的对象可能已经没了。要用对象，先调 `lock()`：对象还活着，返回一个新的 `shared_ptr`（`use_count` 加 1，用的这段时间对象不会被析构）；已经死了，返回空的 `shared_ptr`。

```cpp
std::shared_ptr<Widget> s = make();
std::weak_ptr<Widget> weak = s;
if (auto locked = weak.lock())                  // 活着：拿到一份 shared_ptr
    std::printf("lock ok, use_count = %ld\n", locked.use_count());   // 2
s.reset();                                      // 最后一个 shared_ptr 没了：~Widget
std::printf("expired = %d, lock = %s\n", weak.expired(), weak.lock() ? "set" : "null");
// expired = 1, lock = null
```

### 4.2 用 lock，不用“先 expired 再用” {#lock}

`expired()` 也能告诉你对象还在不在，但在多线程里，“查一次 `expired()`，再去用对象”之间有一个窗口：你刚查完说还活着，另一个线程就把最后一个 `shared_ptr` 放掉了。`lock()` 把“检查还活着”和“把 `use_count` 加 1”做成一次原子操作：要么拿到一份让对象一定活着的 `shared_ptr`，要么拿到空的，没有中间状态。**所以 `weak_ptr` 的标准用法就是 `if (auto p = w.lock())`**，`expired()` 只适合“不用对象、只想知道它在不在”的场合。

### 4.3 循环引用：两个计数都停在 1 {#cycle}

父节点用 `shared_ptr` 持有子节点，子节点也用 `shared_ptr` 指回父节点：

```cpp
struct Node {
    std::string name;
    std::shared_ptr<Node> child;
    std::shared_ptr<Node> parent;               // 指回去也用 shared_ptr
    ~Node() { std::printf("~Node %s\n", name.c_str()); }
};
{
    auto p = std::make_shared<Node>("parent");
    auto c = std::make_shared<Node>("child");
    p->child = c; c->parent = p;                // 此时两个 use_count 都是 2
}   // 离开作用域：一行 ~Node 都没有打印
```

离开作用域时，局部变量 `p`、`c` 各放掉一份，两个 `use_count` 都从 2 降到 1，剩下的那一份正是对方成员里的那个 `shared_ptr`。父节点要析构，得先等子节点放掉它；子节点要放掉它，得先析构自己，而子节点也在等父节点。两个计数都停在 1，谁都到不了 0，两个对象永远不析构，内存泄漏。实测的输出里确实一行 `~Node` 都没有。

把指回去的那一条改成 `weak_ptr<Node> parent;`，父节点的 `use_count` 只剩局部变量 `p` 那一份（实测是 1，子节点是 2）。离开作用域时父节点归零、析构，析构时放掉 `child`，子节点跟着归零。实测输出 `~Node2 parent`、`~Node2 child`。子节点要用父节点时，`if (auto pp = parent.lock())`。

<svg viewBox="0 0 760 270" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="左：父子互相用 shared_ptr 指着，局部变量离开作用域后两边的 use_count 都停在 1，谁也不析构；右：子节点指回父节点的那条换成 weak_ptr，父节点的 use_count 归零先析构，再放掉子节点" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .uq1bg  { fill: #fbfaf7; }
    .uq1bad { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .uq1ok  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .uq1ink { fill: #1c1b18; font-size: 13px; }
    .uq1mut { fill: #6b6558; font-size: 12px; }
    .uq1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .uq1ln  { stroke: #6b6558; stroke-width: 1.5; fill: none; }
    .uq1wk  { stroke: #6b6558; stroke-width: 1.3; fill: none; stroke-dasharray: 5 4; }
    .uq1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1bad { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1ok { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1ink, :root:is([data-theme="dark"], [data-theme="black"]) .uq1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1ln, :root:is([data-theme="dark"], [data-theme="black"]) .uq1wk { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .uq1hd { fill: #a19caf; }
  </style>
  <defs><marker id="uq1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="uq1hd"/></marker></defs>
  <rect class="uq1bg" x="0" y="0" width="760" height="270" rx="10"/>
  <text class="uq1ttl" x="24" y="32">两条都是 shared_ptr</text>
  <text class="uq1mut" x="24" y="52">局部变量 p、c 已经离开作用域</text>
  <rect class="uq1bad" x="24" y="76" width="130" height="62" rx="6"/>
  <text class="uq1ink" x="38" y="102">parent</text>
  <text class="uq1mut" x="38" y="124">use_count = 1</text>
  <rect class="uq1bad" x="224" y="76" width="130" height="62" rx="6"/>
  <text class="uq1ink" x="238" y="102">child</text>
  <text class="uq1mut" x="238" y="124">use_count = 1</text>
  <path class="uq1ln" d="M154,92 L221,92" marker-end="url(#uq1a)"/>
  <path class="uq1ln" d="M224,122 L157,122" marker-end="url(#uq1a)"/>
  <text class="uq1mut" x="164" y="84">child</text>
  <text class="uq1mut" x="164" y="152">parent</text>
  <text class="uq1mut" x="24" y="190">各自剩下的一份，正好是对方成员里的那个。</text>
  <text class="uq1mut" x="24" y="210">谁都到不了 0：两个都不析构，泄漏。</text>
  <text class="uq1ttl" x="406" y="32">指回去的那条换成 weak_ptr</text>
  <text class="uq1mut" x="406" y="52">局部变量 p、c 已经离开作用域</text>
  <rect class="uq1ok" x="406" y="76" width="130" height="62" rx="6"/>
  <text class="uq1ink" x="420" y="102">parent</text>
  <text class="uq1mut" x="420" y="124">use_count = 0</text>
  <rect class="uq1ok" x="606" y="76" width="130" height="62" rx="6"/>
  <text class="uq1ink" x="620" y="102">child</text>
  <text class="uq1mut" x="620" y="124">use_count = 1</text>
  <path class="uq1ln" d="M536,92 L603,92" marker-end="url(#uq1a)"/>
  <path class="uq1wk" d="M606,122 L539,122" marker-end="url(#uq1a)"/>
  <text class="uq1mut" x="546" y="84">child</text>
  <text class="uq1mut" x="546" y="152">weak</text>
  <text class="uq1mut" x="406" y="190">weak_ptr 不算数：parent 先归零、析构，</text>
  <text class="uq1mut" x="406" y="210">析构时放掉 child，child 也归零。</text>
  <text class="uq1mut" x="24" y="252">实线 = shared_ptr，计入 use_count；虚线 = weak_ptr，只计入 weak_count，不让对象活着。</text>
</svg>

**打破环的规则：拥有关系画成一棵树，指回去、指旁边的边都用 `weak_ptr`。** 父拥有子，子只是要找得到父；反过来写就会成环。

### 4.4 还有哪些地方该用 weak_ptr {#weak-when}

凡是“要能找到它，但不该由我决定它活多久”的地方：

- **观察者**：被观察的对象维护一个观察者列表。列表里存 `shared_ptr`，观察者本来该销毁了，却被列表拉着活下去；存 `weak_ptr`，通知时逐个 `lock()`，拿不到的说明观察者已经没了，顺手从列表里删掉。
- **缓存**：按 key 缓存加载过的对象，表里存 `weak_ptr`。还有人在用，`lock()` 能拿到，直接复用；没人用了，对象自然释放，缓存不会把所有东西都攥在手里。
- **回调里的 `this`**：异步回调要用对象，但对象被销毁了回调就该什么也不做，这时捕获 `weak_ptr`，回调开头 `lock()`。要回调期间保证对象活着，才捕获 `shared_ptr`（见 [5.1 的回调场景](#shared-from-this-why)）。

### 4.5 对象没了，控制块还在 {#control-block-lives}

`use_count` 归零时析构的是对象，控制块要等 `weak_count` 也归零才释放：`weak_ptr` 还得靠它回答“对象还在不在”。用 `shared_ptr<T>(new T)` 时控制块单独一块，对象那块内存在析构时就还了；用 `make_shared` 时对象和控制块在同一块内存里，对象虽然析构了，整块内存要等最后一个 `weak_ptr` 也没了才能还（见 [3.1 的控制块图](#shared-ptr)）。对象很大、`weak_ptr` 又活得很久时，这是选 `make_shared` 前要想到的一点。

## 5. 成员函数里拿到自己的 `shared_ptr`：`enable_shared_from_this` {#shared-from-this}

### 5.1 场景：对象要活到回调执行完 {#shared-from-this-why}

一个 `Session` 对象代表和服务器的一条连接，由 `shared_ptr` 管理。`Session::send_request()` 把请求发出去，服务器要过一会儿（比如几十 µs）才回包。程序不会停下来等，而是先登记一个函数，意思是“回包到了就调用它”。这种先登记、以后由别人来调用的函数叫**回调**。登记完，`send_request()` 立刻返回，程序接着干别的。负责“看到回包到了，就调用登记过的回调”的，通常是一个一直在转的循环，叫**事件循环**。

问题出在等待的这段时间里。回包到之前，程序别处可能已经不用这条连接了（比如风控把它断开），丢掉了手里的 `shared_ptr`。如果回调里没有持有一份 `shared_ptr<Session>`，计数就到 0，`Session` 被析构；回包一到，回调去用的是一个已经析构的对象。回调自己持有一份，计数就不会在它执行之前归零：

| 时刻 | 发生了什么 | 回调不持有时的计数 | 回调持有一份时的计数 |
|---|---|---|---|
| 1 | `make_shared<Session>()`，外面持有一份 | 1 | 1 |
| 2 | `send_request()` 登记回调 | 1 | 2 |
| 3 | 外面丢掉自己那份 | 0，`Session` 被析构 | 1，`Session` 还活着 |
| 4 | 回包到了，事件循环调用回调 | 用到已析构的对象，未定义行为 | 正常处理回包 |
| 5 | 回调执行完、被删掉 | — | 0，这时才析构 |

难点在于：回调是在 `send_request()` 这个成员函数里登记的，函数里手上只有 `this`，一个裸指针（`Session*`），不是 `shared_ptr`。怎么从 `this` 得到一份和外面**共用同一个计数**的 `shared_ptr`？

### 5.2 错误写法：`shared_ptr<Session>(this)` 另起一个控制块 {#shared-this-wrong}

```cpp
void send_request() {
    std::shared_ptr<Session> self(this);   // 错：又分配了一个新的控制块
    g_loop.push_back([self] { self->on_reply(); });
}
```

用裸指针构造 `shared_ptr` 时，它不知道这个对象已经有人管了，就新建一个控制块，计数从 1 开始。于是两个计数各数各的：时刻 3 外面那份数到 0，对象析构；回调这份还是 1，指着已经析构的对象；时刻 5 它也数到 0，再 delete 一次。GCC 13 实测程序直接 abort（`munmap_chunk(): invalid pointer`），ASan 报 bad-free。

### 5.3 正确写法：继承 `enable_shared_from_this`，调 `shared_from_this()` {#shared-from-this-right}

```cpp
std::vector<std::function<void()>> g_loop;     // 假装是事件循环：登记的回调先存起来，回包到了再调用

struct Session : std::enable_shared_from_this<Session> {
    int id = 7;
    void on_reply() { std::printf("reply on session %d\n", id); }
    void send_request() {
        // ……把请求发出去……
        auto self = shared_from_this();        // 计数 +1，和外面那份共用控制块
        g_loop.push_back([self] { self->on_reply(); });
    }
};

void demo() {
    auto s = std::make_shared<Session>();      // 时刻 1：计数 1
    s->send_request();                           // 时刻 2：计数 2
    s.reset();                                 // 时刻 3：外面丢掉自己那份，计数 1，Session 还活着
    for (auto& cb : g_loop) cb();              // 时刻 4：回包到了，打印 reply on session 7
    g_loop.clear();                            // 时刻 5：回调删掉，计数 0，这时才析构
}
```

**它怎么做到的。** `enable_shared_from_this<Session>` 里藏了一个 `std::weak_ptr<Session>` 成员。`weak_ptr` 也指向控制块，但不让计数 +1，所以不会让对象一直活着（第 4 节）。`make_shared` 建对象时，发现它继承了 `enable_shared_from_this`，就把这个 `weak_ptr` 指向刚建好的控制块。`shared_from_this()` 只是把它升级成 `shared_ptr`：同一个控制块，计数 +1。

**这是 CRTP。** `enable_shared_from_this` 是一个往子类里注入功能的 CRTP 基类（见 [#8 的 1.3.2 节](/zh/posts/crtp-static-polymorphism/)）：子类什么都不写，就多了 `shared_from_this()`。基类里的 `weak_ptr` 成员和 `shared_from_this()` 的返回值都要写成 `Session`，所以模板参数传的是子类自己。基类如果不是模板，只能存、只能返回 `shared_ptr<基类>`，每次用都要先 `static_pointer_cast` 转回 `shared_ptr<Session>`，转错了就是未定义行为。

### 5.4 用 `shared_from_this()` 的三个坑 {#shared-from-this-pitfalls}

都在 GCC 13 上实测过：

- **对象必须已经归 `shared_ptr` 管。** 对栈上的对象调用，或者在构造函数里调用（这时 `make_shared` 还没填 `weak_ptr`），C++17 起抛 `std::bad_weak_ptr`，更早的标准是未定义行为。
- **必须 `public` 继承。** 私有继承时 `shared_ptr` 看不见这个基类，`weak_ptr` 没人填，同样抛 `bad_weak_ptr`。
- **对象变大，调用不免费。** 对象多一个 `weak_ptr`（两个指针，16 B；实测 `sizeof(Session)` 是 24，含对齐填充）；每次 `shared_from_this()` 都是 3.2 那次原子加。所以它用在连接管理这种冷路径上（Asio 风格的异步服务器里，回调常写成 `[self = shared_from_this()]`），每秒要处理几百万条消息的循环里不这么做。

## 6. 三种怎么选 {#choose}

**默认用 `unique_ptr`。** 绝大多数对象只有一个明确的主人：容器里的元素、类的成员、工厂造出来交给调用方的对象。它和裸指针一样大，没有计数，转交所有权时代码里能看到 `std::move`。

**只有对象的寿命真要由几方共同决定时才用 `shared_ptr`**：比如异步操作的回调可能在发起方之后才执行、几个线程都要用同一份配置而说不清谁最后用完。它的代价是 16 字节、一块控制块、多线程下每次复制一次原子操作。

**`weak_ptr` 配合 `shared_ptr` 用**，放在指回去的边、观察者列表、缓存里。只是在函数里借用一下对象，用引用或裸指针，不需要任何智能指针。

`shared_ptr` 的线程安全常被问到：控制块里的计数是原子操作，所以不同线程各拿一份 `shared_ptr` 复制、销毁是安全的；但它指着的对象本身不受保护，同一个 `shared_ptr` 变量一边赋值一边读也是数据竞争。几种情况和修法见 [3.3](#shared-ptr-threads)。

C++98 的 `auto_ptr` 想做 `unique_ptr` 的事，但那时还没有移动语义，它只能把拷贝写成“偷”：`auto_ptr<T> b = a;` 之后 `a` 悄悄变成空的。看起来是拷贝，实际是转移，放进容器、传给按值收参数的函数都会莫名其妙地把原来那个弄空。C++11 有了右值引用以后，`unique_ptr` 把拷贝禁掉、只留移动，转移必须写成 `std::move(a)`，`auto_ptr` 在 C++17 里被删掉了。移动语义本身见 [左值、右值和移动语义](/zh/ref/move-semantics/)。
