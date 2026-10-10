---
title: "C++ 语法：机器码里是什么"
description: "常用的 C++ 语法编译出来是什么指令、要付什么代价、有什么替代。第一条：虚函数。"
date: 2026-10-10
lastmod: 2026-10-10
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

`run_crtp(l2)` 编出来是 `movl (%rdi), %eax` + `addl %eax, %eax`，没有 vptr，`sizeof(Limit2)` 是 4。代价：不同子类是不同的类型，不能放进同一个容器里统一处理。适合“每处代码只处理一种类型，但这种类型在编译期才选”的场景。

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
