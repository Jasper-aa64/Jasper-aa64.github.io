---
title: "unique_ptr 和 weak_ptr：独占所有权和打破循环引用"
date: 2026-11-02
slug: "unique-ptr-weak-ptr"
description: "智能指针把“谁负责释放”写进类型。unique_ptr 独占一个对象，只能移动不能拷贝，默认和裸指针一样是 8 字节，自定义删除器能管文件和 C 库资源；函数参数按值收 unique_ptr 就是拿走所有权。weak_ptr 指向控制块但不加 use_count，用 lock() 安全地取对象；两个对象互相用 shared_ptr 指着，计数永远到不了 0，把其中一条换成 weak_ptr 就解开了。最后是三种怎么选。"
summary: "默认用 unique_ptr：所有权只有一份，转交时写 std::move，大小和裸指针一样。只有对象的寿命真要由几方共同决定时才用 shared_ptr；指回去的那条边、观察者、缓存用 weak_ptr，它不让对象活着，用之前 lock() 一下。"
toc: true
group: cpplinux
weight: 110
---

`shared_ptr` 的控制块、复制的代价和 `enable_shared_from_this` 在 [shared_ptr](/zh/ref/shared-ptr/) 那页。这页讲另外两种：只允许一个主人的 `unique_ptr`，和只看不管的 `weak_ptr`。

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

一个右值 `unique_ptr` 可以直接用来构造 `shared_ptr`：`std::shared_ptr<Widget> s = make();`，所有权从独占变成共享（反过来不行，共享的所有权收不回独占）。所以工厂函数通常返回 `unique_ptr`：调用方只要一个主人就直接用，要共享就转一下。代价是这样转来的 `shared_ptr` 要另外分配一次控制块，享受不到 `make_shared` 的“一次分配”。

## 3. weak_ptr：看着对象，不让它活着

### 3.1 指向控制块，不加 use_count {#weak-what}

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

### 3.2 用 lock，不用“先 expired 再用” {#lock}

`expired()` 也能告诉你对象还在不在，但在多线程里，“查一次 `expired()`，再去用对象”之间有一个窗口：你刚查完说还活着，另一个线程就把最后一个 `shared_ptr` 放掉了。`lock()` 把“检查还活着”和“把 `use_count` 加 1”做成一次原子操作：要么拿到一份让对象一定活着的 `shared_ptr`，要么拿到空的，没有中间状态。**所以 `weak_ptr` 的标准用法就是 `if (auto p = w.lock())`**，`expired()` 只适合“不用对象、只想知道它在不在”的场合。

### 3.3 循环引用：两个计数都停在 1 {#cycle}

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

### 3.4 还有哪些地方该用 weak_ptr {#weak-when}

凡是“要能找到它，但不该由我决定它活多久”的地方：

- **观察者**：被观察的对象维护一个观察者列表。列表里存 `shared_ptr`，观察者本来该销毁了，却被列表拉着活下去；存 `weak_ptr`，通知时逐个 `lock()`，拿不到的说明观察者已经没了，顺手从列表里删掉。
- **缓存**：按 key 缓存加载过的对象，表里存 `weak_ptr`。还有人在用，`lock()` 能拿到，直接复用；没人用了，对象自然释放，缓存不会把所有东西都攥在手里。
- **回调里的 `this`**：异步回调要用对象，但对象被销毁了回调就该什么也不做，这时捕获 `weak_ptr`，回调开头 `lock()`。要回调期间保证对象活着，才捕获 `shared_ptr`（见 [shared_ptr 的回调场景](/zh/ref/shared-ptr/#shared-from-this-why)）。

### 3.5 对象没了，控制块还在 {#control-block-lives}

`use_count` 归零时析构的是对象，控制块要等 `weak_count` 也归零才释放：`weak_ptr` 还得靠它回答“对象还在不在”。用 `shared_ptr<T>(new T)` 时控制块单独一块，对象那块内存在析构时就还了；用 `make_shared` 时对象和控制块在同一块内存里，对象虽然析构了，整块内存要等最后一个 `weak_ptr` 也没了才能还（见 [shared_ptr 那页的控制块图](/zh/ref/shared-ptr/#shared-ptr)）。对象很大、`weak_ptr` 又活得很久时，这是选 `make_shared` 前要想到的一点。

## 4. 三种怎么选 {#choose}

**默认用 `unique_ptr`。** 绝大多数对象只有一个明确的主人：容器里的元素、类的成员、工厂造出来交给调用方的对象。它和裸指针一样大，没有计数，转交所有权时代码里能看到 `std::move`。

**只有对象的寿命真要由几方共同决定时才用 `shared_ptr`**：比如异步操作的回调可能在发起方之后才执行、几个线程都要用同一份配置而说不清谁最后用完。它的代价是 16 字节、一块控制块、多线程下每次复制一次原子操作。

**`weak_ptr` 配合 `shared_ptr` 用**，放在指回去的边、观察者列表、缓存里。只是在函数里借用一下对象，用引用或裸指针，不需要任何智能指针。

`shared_ptr` 的线程安全常被问到：控制块里的计数是原子操作，所以不同线程各拿一份 `shared_ptr` 复制、销毁是安全的；但它指着的对象本身不受保护，多线程改对象要自己加锁。多个线程同时读写同一个 `shared_ptr` 变量（不是各自的副本）也不安全，C++20 起可以用 `std::atomic<std::shared_ptr<T>>`。

C++98 的 `auto_ptr` 想做 `unique_ptr` 的事，但那时还没有移动语义，它只能把拷贝写成“偷”：`auto_ptr<T> b = a;` 之后 `a` 悄悄变成空的。看起来是拷贝，实际是转移，放进容器、传给按值收参数的函数都会莫名其妙地把原来那个弄空。C++11 有了右值引用以后，`unique_ptr` 把拷贝禁掉、只留移动，转移必须写成 `std::move(a)`，`auto_ptr` 在 C++17 里被删掉了。移动语义本身见 [左值、右值和移动语义](/zh/ref/move-semantics/)。
