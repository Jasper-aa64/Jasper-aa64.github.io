---
title: "静态多态：机器码里是什么"
description: "把“调哪个函数”定在编译期的几种写法，编译出来是什么、代价在哪：CRTP、std::variant、按类型分批、Mixin，以及静态多态和动态多态怎么选。虚函数本身见 C++ 与 Linux 板块的《虚函数》。"
date: 2026-10-10
lastmod: 2026-10-12
slug: "cpp-syntax"
weight: 20
toc: true
---

这页是随时翻的活页，不是一篇文章，讲静态多态：把“调哪个函数”从运行时挪到编译期。虚函数本身（vptr、vtable、一次虚调用的代价）是 C++ 基础，写在[虚函数](/zh/posts/virtual-functions/)那篇；`const` / `constexpr` 和 `shared_ptr` 也搬去了 C++ 与 Linux 板块（[const 和 constexpr](/zh/posts/const-constexpr/)、[shared_ptr](/zh/posts/shared-ptr/)）。汇编都是 GCC 13.3 `-O2`、x86-64 的真实输出。

## 1. 虚函数的替代：CRTP、variant、按类型分批 {#virtual-alternatives}


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

## 2. Mixin：用模板继承链在编译期叠功能 {#mixin}


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

每叠一层，就多一次堆分配（`unique_ptr`），每次调用往下多一次虚调用（[虚函数的代价](/zh/posts/virtual-functions/#virtual-cost)）。

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

### 2.1 顺序就是语义 {#mixin-order}

同一个矩阵 `{{1, 2, 3}, {}, {4, 5, 6}}`：

| 类型 | 输出 | 为什么 |
|---|---|---|
| `DoubleValue<OddOnly<MatrixWalk>>` | `2 6 10` | 先在原值上筛奇数（1、3、5），再翻倍 |
| `OddOnly<DoubleValue<MatrixWalk>>` | 空 | 先翻倍，全变成偶数，再筛奇数一个不剩 |

装饰器可以运行时按配置叠；Mixin 的顺序写在类型里，编译完就定了。

### 2.2 代价 {#mixin-cost}

- **类型组合爆炸**：每种组合都是新类型、实例化一份代码，编译时间和二进制体积涨。
- **报错难读**：模板嵌套几层后错误信息很长。
- **构造要转发**：每层把参数转给 `Base`（上面的可变参数模板构造函数，或者 `using Base::Base;`）。
- **遮蔽不是重写**：`OddOnly::next()` 只是遮住了 `Base::next()`，不是虚函数重写。拿着 `MatrixWalk&` 调 `next()`，调到的还是 `MatrixWalk::next()`。Mixin 只在一直用完整类型时成立。

## 3. 静态多态与动态多态：差别在什么时候做决定 {#polymorphism}

一句话：**两者的差别是“调哪个函数”在什么时候定下来。** 静态多态（模板、CRTP、Mixin、编译期决策树）在编译时定，动态多态（虚函数）在运行时按对象的类型定。速度、灵活性、工程代价，都是从这一点推出来的。

### 3.1 快在哪：内联，不只是省一次跳转 {#poly-speed}

动态多态的运行时代价见[虚函数 1.3](/zh/posts/virtual-functions/#virtual-cost)：一次要猜的间接跳转、两次读内存、每个对象 8 字节、挡住内联。其中最贵的通常是**挡住内联**。另有一笔只在冷启动时出现：行情安静了一阵，热路径的缓存被别的代码挤掉，下一个 tick 到来时 vtable 那条行也可能不在缓存里，排在读 vptr 之后多出一次串行未命中。办法是让热路径保持热（空闲时也定期用假数据跑一遍），或者换成 CRTP、`final`，根本没有 vtable 要读。

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

