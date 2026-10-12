---
title: "C++ 语法：机器码里是什么"
description: "常用的 C++ 语法编译出来是什么指令、要付什么代价、有什么替代。目前四条：虚函数；组合与 Mixin；静态多态与动态多态；const / constexpr / consteval / constinit。"
date: 2026-10-10
lastmod: 2026-10-12
slug: "cpp-syntax"
weight: 20
toc: true
---

这页是随时翻的活页，不是一篇文章。每一条按同一个顺序写：是什么 → 编译出来是什么 → 代价在哪 → 什么时候能省掉、拿什么替代。汇编都是 GCC 13.3 `-O2`、x86-64 的真实输出。后面讲到新的语法点，都补在这一页。

## 1. 虚函数（virtual function）：运行时按对象的类型选函数 {#virtual}

### 1.1 是什么 {#virtual-what}

基类里声明 `virtual` 的函数，通过基类指针或引用调用时，调用的是**对象实际类型**的那个版本。调用处写的是同一句 `o->handle()`，到底执行哪个函数，要到运行时看 `o` 指向的是什么才知道。

```cpp
struct Order {
    virtual ~Order() = default;
    virtual int handle() const = 0;   // 纯虚函数：每个子类自己实现
    int qty = 1;
};
struct LimitOrder : Order {
    int handle() const override { return qty * 2; }
};
struct MarketOrder final : Order {    // final：不会再有子类
    int handle() const override { return qty * 3; }
};

int run(const Order* o) { return o->handle(); }   // 可能是 LimitOrder，也可能是 MarketOrder
```

典型用法：一个容器里放着不同子类的对象（`std::vector<std::unique_ptr<Order>>`），循环里统一调 `handle()`。

### 1.2 编译出来：vptr 和 vtable {#virtual-vtable}

`run` 编译出来只有两条指令：

```asm
run(Order const*):
        movq    (%rdi), %rax      # 1. 读对象开头的 8 字节：vptr，指向这个类的虚函数表
        jmp     *16(%rax)         # 2. 从表里第 3 格读出函数地址，跳过去（间接跳转）
```

靠的是两样东西：

- **vtable**（虚函数表）：每个有虚函数的**类**一张，存在只读数据段里，按声明顺序列出这个类每个虚函数的地址。`LimitOrder` 的表里 `handle` 那格是 `LimitOrder::handle`，`MarketOrder` 的是 `MarketOrder::handle`。（前两格是析构函数，所以 `handle` 在偏移 16。）
- **vptr**（虚表指针）：每个**对象**开头藏着的一个 8 字节指针，构造时指向自己那个类的 vtable。`sizeof(LimitOrder)` 因此是 16：vptr 8 字节，`qty` 4 字节，再补 4 字节对齐。

所以一次虚调用 = 读 vptr → 读表里那一格 → 按读到的地址跳。

### 1.3 代价在哪 {#virtual-cost}

- **间接跳转要猜**：目标地址是读出来的，前端要靠**间接目标预测器**去猜（[#7 第 1.3 节](/zh/posts/branch-prediction-branch-optimization/)）。同一处调用，对象类型有规律（全是同一种，或者短周期重复）几乎不会错；类型随机混在一起就经常错，每次约 15–20 个周期。
- **挡住内联**：编译器不知道会调到哪个函数，就没法把它内联进来，也没法跨这次调用做优化（常量传播、合并计算、向量化）。函数体越小，这一条越亏：`handle()` 本身只有一条乘法，调用开销比它大得多。
- **多两次读内存**：vptr 和 vtable 那一格。热循环里它们一般在 L1，约 1 ns；对象散在堆上、很久没碰时，第一次读 vptr 可能缓存未命中。
- **每个对象多 8 字节**：小对象（比如 16 字节的订单）会因此大一截，一条缓存行装得更少。

### 1.4 编译器什么时候能省掉虚调用（devirtualization） {#virtual-devirt}

编译器能确定对象的实际类型时，就直接调用、甚至内联。三种常见情况，前两种是实测：

```cpp
int run_market(const MarketOrder* o) { return o->handle(); }   // MarketOrder 是 final
int run_local() { LimitOrder l; return run(&l); }              // 对象就在眼前
```

- **`final`**：`MarketOrder` 标了 `final`，不可能有子类，`o->handle()` 只能是 `MarketOrder::handle`。`run_market` 编出来是 `movl 8(%rdi), %eax` + `leal (%rax,%rax,2), %eax`，乘 3 直接内联了，没有跳转。
- **局部对象**：`run_local` 里对象的类型就写在那，`run` 内联进来以后，整个函数编成了 `movl $2, %eax`。
- **只有一个实现**：开 `-flto`（链接期优化）后，编译器看到整个程序，某个虚函数只有一个实现时也能直接调用（这一条没有实测）。

### 1.5 不用虚函数的替代 {#virtual-alternatives}

**CRTP**（curiously recurring template pattern，奇异递归模板）：子类把自己当模板参数传给基类，基类里用 `static_cast` 转回子类再调用。类型在编译期就定了，调用直接内联。

```cpp
template <typename Derived>
struct OrderBase {
    int handle() const { return static_cast<const Derived*>(this)->handle_impl(); }
};
struct Limit2 : OrderBase<Limit2> {
    int qty = 1;
    int handle_impl() const { return qty * 2; }
};
template <typename T> int run_crtp(const OrderBase<T>& o) { return o.handle(); }
```

`run_crtp(l2)` 编出来是 `movl (%rdi), %eax` + `addl %eax, %eax`，没有 vptr，`sizeof(Limit2)` 是 4。代价：不同子类是不同的类型，不能放进同一个容器里统一处理。适合“每处代码只处理一种类型，但这种类型在编译期才选”的场景。完整讲解（用途、四个坑、C++23 deducing this）见 [#8 CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/)。

**`std::variant` + `std::visit`**：类型的集合固定、事先都知道时，用一个 `variant` 装其中之一，按里面存的类型编号分派。

```cpp
struct L { int qty; int handle() const { return qty * 2; } };
struct M { int qty; int handle() const { return qty * 3; } };
struct S { int qty; int handle() const { return qty * 5; } };
using AnyOrder = std::variant<L, M, S>;

int run_variant(const AnyOrder& o) {
    return std::visit([](const auto& x) { return x.handle(); }, o);
}
```

编出来是读类型编号（1 个字节）+ 两次比较跳转，三个 `handle()` 都内联在分支里，没有间接调用。对象按值存，`sizeof(AnyOrder)` 是 8（`qty` 4 字节 + 编号，补齐），`std::vector<AnyOrder>` 里是连续的一排，不用每个对象单独 `new`。代价：加一种新类型要改 `variant` 的定义；分支还在，类型随机混在一起时照样会猜错（变成了条件跳转）。

**按类型分批**：不换语法，换数据的排法。把订单先按类型分到几个数组里，每个数组一个循环。同一个循环里类型都一样，虚调用（或者分支）每次目标都一样，几乎不会猜错；类型已知时还能直接用具体类型、让编译器内联。

**编译期拼好的结构**：策略树这类“节点之间怎么连”在部署前就定好的东西，可以把节点做成类型，整棵树在编译期拼好，见 [#7 第 3.6 节](/zh/posts/branch-prediction-branch-optimization/)的编译期决策树。

### 1.6 怎么选 {#virtual-choose}

- **类型在运行时才知道、集合开放（插件、配置里读出来）**：虚函数。热路径上尽量让同一处调用的类型有规律，或者按类型分批。
- **类型集合固定、对象要放在一起**：`std::variant` + `std::visit`。
- **类型在编译期就能定**：模板或 CRTP，能标 `final` 的就标上。
- **不在热路径上**：虚函数最好读，不用纠结。

## 2. 组合与继承：复用实现用成员，叠加功能用 Mixin {#composition}

### 2.1 组合（composition）：复用一个类的实现，把它放成成员 {#composition-member}

```cpp
class InheritanceOrderBook : public std::vector<Order> {   // 继承：直接“是”一个 vector
};

class CompositionOrderBook {                                // 组合：“有”一个 vector
    std::vector<Order> orders_;
public:
    auto size() const noexcept { return orders_.size(); }  // 只暴露需要的接口
};
```

**编译出来一样**：读成员和调 `size()` 都是直接读 `orders_` 里的字段，`size()` 内联。差别全在设计上，public 继承 `std::vector` 有三个问题：

- **接口全部暴露**：`push_back`、`erase` 谁都能调，订单簿“按价格排序”这类不变量就守不住。组合只给出愿意给的函数。
- **析构函数不是虚的**：`std::vector<Order>* p = new InheritanceOrderBook;` 再 `delete p` 是未定义行为。标准容器不是设计来当基类的。
- **和底层绑死**：想把 `std::vector` 换成别的容器，继承的写法所有调用方都要改，组合只改类内部。

规则：要的是“用它的实现”，放成成员（has-a）；真要“当成它来用”（is-a），并且基类是为继承设计的（有虚析构函数），才 public 继承。

### 2.2 Mixin：用模板继承链在编译期叠功能 {#mixin}

先说清两个名词，再看代码。

**装饰器模式（decorator pattern）**：一种常见的设计模式，用来**不改原来的类，给它一层层加功能**。做法是写一个“包装层”，它和被包的对象长得一样（实现同一个接口），自己持有被包的对象。别人调包装层，包装层先转给里面那个，再在前后加上自己的那点功能。包装层还能再被包，所以功能可以一层叠一层，叠几层、按什么顺序叠，运行时拼对象的时候决定。

**Mixin**：字面意思是“混进去的东西”，指一个**只提供一项功能、自己不能单独用的小类**，要“混进”别的类里才有用。C++ 里通常写成 `template <class Base> class X : public Base`：`X` 不知道自己会叠在谁上面，基类由模板参数在编译期指定。

**两者的关系**：目标一样，都是一层层叠功能；差别在层与层怎么连。装饰器是运行时用指针连（动态多态），Mixin 是编译期用继承连（静态多态）。所以说 Mixin 是装饰器模式的静态多态版本。

**例子**：一个迭代器要叠几层功能（遍历矩阵 → 只保留奇数 → 值翻倍），还想随意组合。先看装饰器的写法，每层是一个对象，持有下一层的指针：

```cpp
struct Iterator {                      // 统一接口：每层都长这样
    virtual ~Iterator() = default;
    virtual bool valid() const = 0;
    virtual Cell cell() const = 0;
    virtual void next() = 0;
};

struct DoubleValueDeco : Iterator {    // 一层装饰：包住下一层，只改 cell()
    std::unique_ptr<Iterator> inner;
    explicit DoubleValueDeco(std::unique_ptr<Iterator> i) : inner(std::move(i)) {}
    bool valid() const override { return inner->valid(); }
    Cell cell() const override { Cell x = inner->cell(); x.value *= 2; return x; }
    void next() override { inner->next(); }
};
```

每叠一层，就多一次堆分配（`unique_ptr`），每次调用往下多一次虚调用（[第 1 条](#virtual-cost)的代价）。

**Mixin 的写法**：每层是一个模板，把下一层当模板参数并继承它。

```cpp
template <class Base>
class OddOnly : public Base {          // 只保留奇数
public:
    template <class... Args>
    explicit OddOnly(Args&&... args) : Base(std::forward<Args>(args)...) {
        while (Base::valid() && (Base::cell().value % 2 == 0)) Base::next();
    }
    void next() {
        do {
            Base::next();
        } while (Base::valid() && (Base::cell().value % 2 == 0));
    }
};

template <class Base>
class DoubleValue : public Base {      // 值翻倍
public:
    template <class... Args>
    explicit DoubleValue(Args&&... args) : Base(std::forward<Args>(args)...) {}
    Cell cell() const {
        Cell x = Base::cell();
        x.value *= 2;
        return x;
    }
};

using Iter = DoubleValue<OddOnly<MatrixWalk>>;   // 模板实参的顺序就是叠加的顺序
```

（`MatrixWalk` 是最底层，按行遍历一个二维 `vector`，提供 `valid()`、`cell()`、`next()`。）**编译出来**：`Iter` 是**一个对象**，没有每层的堆对象、没有指针、没有虚函数，`Base::next()`、`Base::cell()` 都是直接调用，可以一路内联。它是装饰器模式的**静态多态**版本，和 [CRTP 替代虚函数](#virtual-alternatives)是同一笔交易。

<a href="/images/ref/mixin-vs-decorator.zh.svg" target="_blank" rel="noopener"><img src="/images/ref/mixin-vs-decorator.zh.svg" alt="上：装饰器是 3 个堆上的对象，每个带 vptr，用 inner 指针连起来；调一次 cell() 每往下一层都要读指针、读 vtable、做一次间接调用，编译器没法内联。下：Mixin 是 1 个 32 字节的对象，DoubleValue、OddOnly 是 MatrixWalk 外面套的基类，不加成员，没有 vptr 和指针，调用全部内联；筛奇数的条件跳转还在。" loading="lazy" decoding="async"></a>

### 2.3 顺序就是语义 {#mixin-order}

同一个矩阵 `{{1, 2, 3}, {}, {4, 5, 6}}`：

| 类型 | 输出 | 为什么 |
|---|---|---|
| `DoubleValue<OddOnly<MatrixWalk>>` | `2 6 10` | 先在原值上筛奇数（1、3、5），再翻倍 |
| `OddOnly<DoubleValue<MatrixWalk>>` | 空 | 先翻倍，全变成偶数，再筛奇数一个不剩 |

装饰器可以运行时按配置叠；Mixin 的顺序写在类型里，编译完就定了。

### 2.4 代价 {#mixin-cost}

- **类型组合爆炸**：每种组合都是新类型、实例化一份代码，编译时间和二进制体积涨。
- **报错难读**：模板嵌套几层后错误信息很长。
- **构造要转发**：每层把参数转给 `Base`（上面的可变参数模板构造函数，或者 `using Base::Base;`）。
- **遮蔽不是重写**：`OddOnly::next()` 只是遮住了 `Base::next()`，不是虚函数重写。拿着 `MatrixWalk&` 调 `next()`，调到的还是 `MatrixWalk::next()`。Mixin 只在一直用完整类型时成立。

## 3. 静态多态与动态多态：差别在什么时候做决定 {#polymorphism}

一句话：**两者的差别是“调哪个函数”在什么时候定下来。** 静态多态（模板、CRTP、Mixin、编译期决策树）在编译时定，动态多态（虚函数）在运行时按对象的类型定。速度、灵活性、工程代价，都是从这一点推出来的。

### 3.1 快在哪：内联，不只是省一次跳转 {#poly-speed}

动态多态的运行时代价见 [1.3](#virtual-cost)：一次要猜的间接跳转、两次读内存、每个对象 8 字节、挡住内联。其中最贵的通常是**挡住内联**。

- 间接跳转本身：同一处调用的类型有规律时几乎不会猜错，只是多几个周期；类型随机混在一起时，每次猜错约 15–20 个周期。
- 内联：函数体被展开进调用方以后，编译器能做常量传播、合并计算、向量化。函数体越小，这一条差得越多。

所以“静态比动态快”要加两个条件：调用在热路径上，而且函数体小。函数体本身要跑几百 ns 的话，省下的几 ns 不显眼。另外，静态多态也不等于“没有分支”：编译期决策树里由数据决定的条件，编出来照样是条件跳转（[#7 第 3.6 节](/zh/posts/branch-prediction-branch-optimization/)那棵树是 3 条条件跳转）。省掉的是“选哪个函数”的那次间接跳转。

### 3.2 静态多态的代价 {#poly-cost}

- **代码膨胀**：模板每种实参实例化一份代码。二进制变大通常不要紧，要紧的是热路径上同时活跃的那几份能不能都放进指令缓存（L1I，约 32 KiB）。10 个品种各一份，但同一段时间只跑其中一两份，一般不会因此变慢。
- **编译时间**：实例化、内联展开都在编译期做，模板用得多的项目编译明显变慢。
- **报错难读**：嵌套几层模板以后，一个类型写错能刷出很长的错误信息。C++20 的 concepts 能把一部分错误提前到“约束不满足”这一行。
- **类型集合在编译时定死**：这一条单独讲，见下一节。

### 3.3 “运行时灵活性”具体丢了什么 {#poly-flexibility}

先分清两件事：**运行时从几个已经编译好的类型里挑一个，静态多态做得到；运行时加一个编译时没见过的新类型，做不到。**

**能做到的：在循环外分派一次。** 配置文件里写 `"fast"` 还是 `"safe"`，运行时才知道；两个算法类型都提前写好，用一个 `if` 选一份已经实例化好的代码：

```cpp
struct Fast { int apply(int x) const { return x * 2; } };
struct Safe { int apply(int x) const { return x * 4; } };

template <typename Algo>
long long run_loop(const int* xs, int n) {
    Algo a;
    long long s = 0;
    for (int i = 0; i < n; ++i) s += a.apply(xs[i]);   // 编译期已知是哪个 apply，直接内联
    return s;
}

long long run(const std::string& cfg, const int* xs, int n) {
    if (cfg == "fast") return run_loop<Fast>(xs, n);     // 只在这里判断一次
    if (cfg == "safe") return run_loop<Safe>(xs, n);
    return 0;
}
```

`run_loop<Fast>` 编出来，循环里 `apply` 就是一条 `addl %eax, %eax`，没有 `call`。判断只在进循环前做一次，和 [#7 第 3.5 节](/zh/posts/branch-prediction-branch-optimization/)的“把 if 提到循环外”是同一个思路。热路径上几乎都是这样用的：启动时读配置、选好类型，之后的循环里没有分派。

**几个维度一起分派：写起来不难，实例化份数难。** 算法 3 种 × 内存策略 3 种，不用手写 9 个分支，`std::visit` 接受多个 `variant`，自动生成全部组合：

```cpp
using AlgoV = std::variant<A1, A2, A3>;
using MemV  = std::variant<B1, B2, B3>;

void dispatch(const AlgoV& a, const MemV& m) {
    std::visit([](auto x, auto y) { run_combo<decltype(x), decltype(y)>(); }, a, m);
}
```

这里 `run_combo` 实例化了 3 × 3 = 9 份。5 个维度各 3 种就是 3<sup>5</sup> = 243 份，代码不用手写，但编译时间和体积按乘法涨。常见做法是只把热路径上真正影响性能的一两个维度做成类型，日志级别、校验开关这类不在热循环里的，留成普通的运行时变量。

**做不到的：开放的类型集合。**

- **插件**：程序跑起来以后用 `dlopen`（Windows 上是 `LoadLibrary`）加载一个 `.so` / `.dll`，里面的类是主程序编译时没见过的。模板没法给它实例化，只能约定一个虚函数接口，主程序通过 vtable 调进去。插件内部照样可以用模板，只是插件和主程序之间这一层得是动态的。
- **类型不固定的容器**：`std::vector<std::unique_ptr<Strategy>>` 能放任何 `Strategy` 的子类，包括以后才写的。`std::variant<L, M, S>` 也能把几种类型放进同一个 `vector`，而且按值连续存，但只能放这几种，加一种要改定义、重新编译。
- **运行时改结构**：比如盘中从后台下发一棵新的风控树，节点怎么连事先不知道，只能在运行时用对象和指针拼（[#7 第 3.6 节](/zh/posts/branch-prediction-branch-optimization/)的运行时虚函数树）。

### 3.4 怎么选 {#poly-choose}

按两个问题判断：

1. **类型集合在编译时能不能定下来？** 定不下来（插件、运行时下发的结构），用虚函数。能定下来，往下看。
2. **这次调用在不在热路径上？** 不在（启动、配置加载、每秒几次的管理逻辑），用虚函数，好读、好改。在热路径上，用模板、CRTP，或者 `std::variant`（集合固定、对象要放在一起时），并且把运行时的选择放到循环外面做一次。

两者常常混用：外层用虚函数或 `variant` 选一次，选中的那份代码内部全是静态的。

## 4. `const` / `constexpr` / `consteval` / `constinit`：哪个保证编译期算 {#compile-time}

四个关键字长得像，回答的是不同的问题：

| 关键字 | 修饰什么 | 保证在编译期算出来吗 | 之后能改吗 |
|---|---|---|---|
| `const` | 变量、参数、成员函数 | **不保证** | 不能 |
| `constexpr` | 变量 | 保证 | 不能 |
| `constexpr` | 函数 | 不保证：用在要求常量的地方才在编译期算 | — |
| `consteval` | 函数 | 保证：每次调用都在编译期算 | — |
| `constinit` | 静态生命周期的变量 | 保证初始化在编译期完成 | **能**（不带 `const`） |

### 4.1 `const`：只读，不是编译期常量 {#const}

`const` 只说初始化之后不能改，初始值可以是运行时的（`const int scale = get_config("scale");`）。对性能要分清两种：

- **`const` 对象本身**（`const int max_len = 100;`）：改它是未定义行为，编译器可以直接把 100 当立即数用。整型 `const` 用常量初始化时，还能当模板实参。
- **`const T*` / `const T&`**：只是**你**不能通过它改，别的指针照样能改，编译器得防着：

```cpp
int f(const int* p, int* q) {
    int a = *p;
    *q = 1;          // q 可能和 p 指向同一个 int
    return a + *p;   // 所以这里要重新读 *p
}
```

编出来 `movl (%rdi), %eax` → `movl $1, (%rsi)` → `addl (%rdi), %eax`，`*p` 读了两次。所以 `const &` 参数的好处是不拷贝、防误改，不是让编译器多优化。

### 4.2 `constexpr`：变量一定编译期算，函数“能”编译期算 {#constexpr}

- **`constexpr` 变量**：初始值必须在编译期算出来，否则编译报错。
- **`constexpr` 函数**：**允许**在编译期算。用在要求常量的地方（`constexpr` 变量、模板实参、数组大小、`static_assert`），一定在编译期算；参数是运行时的值，就是一次普通调用。

```cpp
constexpr int twice(int x) { return x + x; }
constexpr int four = twice(2);           // 编译期算出 4
int twice_rt(int n) { return twice(n); } // 运行时算
```

`twice_rt` 编出来是一条 `leal (%rdi,%rdi), %eax`，和普通函数一样。`constexpr` 不是“优化提示”。

### 4.3 `consteval`：每次调用都必须在编译期 {#consteval}

`consteval` 函数（立即函数）每次调用都必须在编译期算完，参数不是常量就编译报错。用在“运行时算就是 bug”的地方，比如编译期校验配置、生成哈希。

```cpp
consteval int get_dim() { return 4; }
Vector<get_dim()> v;     // 可以当模板实参
```

陷阱：`consteval` 函数的**形参在函数体里不是常量表达式**，不能 `static_assert(i == 1)`，也不能拿 `i` 当模板实参。要这样用，得把它写成模板参数 `template <int I>`。

**`if consteval`**（C++23）：同一个 `constexpr` 函数里，编译期走一套能在编译期跑的实现，运行时走更快的实现：

```cpp
constexpr std::size_t my_strlen(const char* s) {
    if consteval {
        std::size_t n = 0;          // 编译期：一个字节一个字节数
        while (s[n]) ++n;
        return n;
    } else {
        return std::strlen(s);      // 运行时：库函数（不是 constexpr）
    }
}
```

### 4.4 `constinit`：静态变量在编译期初始化，但可以改 {#constinit}

`constinit` 只管一件事：**全局变量、`static` 变量的初始化必须在编译期完成**，做不到就编译报错。它**不**带 `const`，之后可以改。

```cpp
constexpr int somefunc() { return 27; }    // 必须是 constexpr，否则下一行编译失败
constinit int g_counter = somefunc();      // 进 .data，初值 27 写在可执行文件里
// ...
++g_counter;                               // 可以改
```

它防的是**静态初始化顺序问题**（static initialization order fiasco）：运行时初始化的全局变量由启动代码在 `main` 之前去算，不同源文件之间谁先谁后标准不规定，一个全局变量读到另一个还没初始化的就是 bug。`constinit` 保证没有这一步。

### 4.5 非类型模板参数：把常量变成类型的一部分 {#nttp}

模板参数可以是一个值（NTTP，non-type template parameter）：

```cpp
template <int Dim>
struct Vector {
    float data[Dim];
    float dot(const Vector& other) const {
        float sum = 0.0f;
        for (int i = 0; i < Dim; i++) sum += data[i] * other.data[i];
        return sum;
    }
};
```

`Vector<4>` 和 `Vector<8>` 是两个类型，各编一份，循环次数是常量，编译器能整个展开或向量化。代价是[第 3 条](#poly-cost)的代码膨胀。模板实参必须是编译期常量：`const int d = 4;` 可以，`int n = 4; const int d = n;` 不行。

### 4.6 编译期生成查找表 {#lut}

```cpp
constexpr std::array<uint64_t, 20> make_pow10() {
    std::array<uint64_t, 20> t{};
    uint64_t v = 1;
    for (auto& x : t) { x = v; v *= 10; }
    return t;
}
constexpr auto kPow10 = make_pow10();     // 编译期填好，放进 .rodata
uint64_t pow10(unsigned e) { return kPow10[e]; }
```

`pow10` 编出来是 `leaq kPow10(%rip), %rax` + `movq (%rax,%rdi,8), %rax`：一次读内存。查表的代价就是这次读：表在 L1D 里约 1 ns，表大、访问又随机就会落到 L2、L3 甚至内存（[速查：延迟](/zh/ref/cpu-memory/#latency)），这时直接算可能更快。

### 4.7 怎么选 {#compile-time-choose}

- 值必须编译期就有，算不出来应该报错 → `constexpr` 变量，或 `consteval` 函数。
- 一份实现编译期、运行时都要用 → `constexpr` 函数，需要时加 `if consteval`。
- 全局 / `static` 变量要能改，但不要运行时初始化 → `constinit`。
- 只是不想被改 → `const`。
