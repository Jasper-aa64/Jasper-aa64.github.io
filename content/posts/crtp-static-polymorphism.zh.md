---
title: "交易系统笔记 #8：CRTP 与静态多态"
date: 2026-10-12
slug: "crtp-static-polymorphism"
description: "CRTP（奇异递归模板）：子类把自己当模板参数传给基类，基类在编译期就知道子类是谁。它为什么合法、编译出来和虚函数差在哪（GCC 真实汇编，含推测性去虚化）、三种用途、四个坑（基类抄错静默 UB、同名无限递归、不完整类型、没有共同基类）、和虚函数怎么选，以及 C++23 deducing this。"
summary: "基类写流程、子类填细节，虚函数在运行时选，CRTP 在编译期选。省下的不只是一次间接跳转：调用能整个内联，对象里也没有 vptr。代价是 Base<A> 和 Base<B> 毫无关系，放不进同一个容器。"
chapter: 1
categories: [Systems]
tags: [cpp, crtp, static-polymorphism, virtual-functions, templates, hft, low-latency]
toc: true
homepage: false
---

行情网关要接好几个交易所。每家的处理流程大体一样：收包、校验序号、更新订单簿，只有“解析一条消息”这一步各不相同。最自然的写法是基类写流程、子类填“解析”这一步，用虚函数：基类调 `virtual on_tick()`，运行时按对象的类型选。

问题是这一步每秒要调几百万次。同一个 `on_tick`，用虚函数写，GCC `-O2` 编出来是 `movq (%rdi), %rax` + `jmp *16(%rax)`，一次间接跳转，函数体进不来；换一种写法，编出来只剩 `movl (%rdi), %eax` + `imull %esi, %eax` 两条指令。这种写法就是 CRTP。

## 1. CRTP：让基类在编译期知道子类是谁

### 1.1 是什么：子类把自己传给基类

```cpp
template <typename Derived>
class Base {
public:
    void doSomething() {
        static_cast<Derived*>(this)->doSomethingImpl();   // 转成子类，调子类的实现
    }
};

class Derived1 : public Base<Derived1> {
public:
    void doSomethingImpl() {
        std::cout << "Derived1 is doing something." << std::endl;
    }
};

template <typename T>
void performAction(Base<T>& obj) {
    obj.doSomething();
}
```

**名字的由来**：`class Derived1 : public Base<Derived1>`，一个类在自己的定义里，把自己当成基类的模板实参，看起来像是“递归”了，所以叫 curiously recurring template pattern（奇异递归模板模式）。

**为什么合法**：写到 `Base<Derived1>` 那一刻，`Derived1` 还没定义完，是个**不完整类型**（incomplete type）：编译器只知道有这么个类，不知道它有哪些成员、多大。`Base<Derived1>` 能实例化，是因为 `Base` 的类定义里没用到 `Derived` 的任何成员，只在 `doSomething()` 的**函数体**里用了。类模板的成员函数体要等真被调用时才实例化，那时 `Derived1` 早已定义完。这一点决定了 1.4.3 节的坑。

**为什么 `static_cast` 是安全的**：从基类指针转成子类指针（向下转型），只要这个对象**真的是**那个子类，`static_cast` 就是正确的，而且不需要运行时检查，编译出来通常什么指令都没有（单继承时基类子对象和子类对象地址相同）。CRTP 靠约定保证这一点：只有 `Derived1` 会继承 `Base<Derived1>`。约定被打破时会出什么事，见 1.4.1 节。

### 1.2 编译出来：和虚函数差在哪

同一个 `on_tick`，一个用 CRTP，一个用虚函数：

```cpp
template <typename Derived>
struct FeedBase {
    int on_tick(int px) { return static_cast<Derived*>(this)->on_tick_impl(px); }
};
struct BinanceFeed : FeedBase<BinanceFeed> {
    int mult = 2;
    int on_tick_impl(int px) { return px * mult; }
};
template <typename T>
int run_crtp(FeedBase<T>& f, int px) { return f.on_tick(px); }

struct IFeed {
    virtual ~IFeed() = default;
    virtual int on_tick(int px) = 0;
};
struct OkxFeed : IFeed {
    int mult = 3;
    int on_tick(int px) override { return px * mult; }
};
int run_virtual(IFeed& f, int px) { return f.on_tick(px); }
```

GCC 13 `-O2` 编出来：

```text
run_crtp<BinanceFeed>:           run_virtual（程序里只有 OkxFeed 一个实现）：
    movl  (%rdi), %eax               movq  (%rdi), %rax           # 读 vptr
    imull %esi, %eax                 leaq  OkxFeed::on_tick, %rdx
    ret                              movq  16(%rax), %rax         # 读 vtable 那一格
                                     cmpq  %rdx, %rax             # 是不是 OkxFeed::on_tick？
                                     jne   .L18                   # 不是：去做间接调用
                                     movl  8(%rdi), %eax          # 是：走内联好的版本
                                     imull %esi, %eax
                                     ret
```

- **CRTP**：`on_tick` → `on_tick_impl` 全部内联，只剩“读 `mult`、乘”两条指令。`mult` 在偏移 0，因为对象里没有 vptr。
- **虚函数**：GCC 在这里做了**推测性去虚化**（speculative devirtualization）：它看到整个程序只有 `OkxFeed` 一个实现，就先比较 vtable 那一格是不是 `OkxFeed::on_tick`，是的话走内联好的版本。即便如此，也还要多读 vptr、读 vtable、比较一次。程序里再加一个 `BybitFeed : IFeed`，`run_virtual` 就变回了开头那两条：`movq (%rdi), %rax` + `jmp *16(%rax)`，一次纯粹的间接跳转，`on_tick` 的函数体没法内联进来。
- **对象大小**：`sizeof(BinanceFeed)` 是 4（只有一个 `int`，空基类不占空间），`sizeof(OkxFeed)` 是 16（vptr 8 字节 + `int` 4 字节 + 补齐 4 字节）。

省下来的东西，就是[速查：虚函数的代价](/zh/ref/cpp-syntax/#virtual-cost)列的那几条：要猜的间接跳转、两次读内存、vptr 的 8 字节，以及最值钱的内联。

### 1.3 三种用途

#### 1.3.1 静态接口：替代热路径上的虚函数

就是上面的例子：基类写流程（收包、校验序号），在某一步调子类的钩子；子类只实现钩子。行情处理、策略回调这种每秒几百万次、部署时就知道是哪个交易所的地方最常用。

#### 1.3.2 往子类里注入功能：子类写一点，基类补全其余

基类知道子类类型，就能写出“基于子类已有的函数”的通用代码。例如子类只写 `==`，基类给出 `!=`：

```cpp
template <typename Derived>
struct EqualityOps {
    friend bool operator!=(const Derived& a, const Derived& b) { return !(a == b); }
};
struct Price : EqualityOps<Price> {
    long ticks;
    friend bool operator==(const Price& a, const Price& b) { return a.ticks == b.ticks; }
};
```

标准库里的 `std::enable_shared_from_this<T>` 就是 CRTP：`class Session : public std::enable_shared_from_this<Session>`，基类因为知道 `T`，才能返回 `std::shared_ptr<T>` 而不是 `shared_ptr<基类>`。（`!=` 这个例子在 C++20 里已经不需要了：写了 `==`，编译器自动支持 `!=`。）

#### 1.3.3 每个子类一份独立的静态成员

`Base<A>` 和 `Base<B>` 是两个不同的类型，所以基类里的 `static` 成员也是各一份。用来给每种对象单独计数：

```cpp
template <typename Derived>
struct InstanceCounter {
    static inline int alive = 0;
    InstanceCounter() { ++alive; }
    InstanceCounter(const InstanceCounter&) { ++alive; }
    ~InstanceCounter() { --alive; }
};
struct OrderA : InstanceCounter<OrderA> {};
struct OrderB : InstanceCounter<OrderB> {};
```

建 3 个 `OrderA`、2 个 `OrderB`，各析构一个以后，`InstanceCounter<OrderA>::alive` 是 2，`InstanceCounter<OrderB>::alive` 是 1，互不干扰。如果用一个普通基类，`static` 成员只有一份，就分不开了。

### 1.4 四个坑

#### 1.4.1 基类的模板实参抄错：静默算错

```cpp
template <typename D> struct Base { int run() { return static_cast<D*>(this)->impl(); } };
struct A : Base<A> { int x = 1; int impl() { return x; } };
struct B : Base<A> { long y = 2; int impl() { return 99; } };   // 复制 A 的代码，基类忘了改
```

`B b; b.run();` 编译不报错，运行输出 2：`run()` 把一个 `B` 对象当成 `A` 转过去，调的是 `A::impl()`，读的是“`A` 的 `x` 所在的位置”，那里其实是 `B` 的 `y`。这是未定义行为，编译器不检查，因为向下转型的 `static_cast` 本来就信任程序员。

**防法**：基类构造函数设成私有，只让模板实参那个类当友元：

```cpp
template <typename Derived>
class SafeBase {
public:
    void run() { static_cast<Derived*>(this)->run_impl(); }
private:
    SafeBase() = default;
    friend Derived;                    // 只有 Derived 能构造 SafeBase<Derived>
};
struct GoodA : SafeBase<GoodA> { void run_impl() {} };
struct BadB : SafeBase<GoodA> { void run_impl() {} };   // 抄错了基类
BadB b;                                                  // 编译报错：构造不了
```

`BadB` 的定义本身能过，一构造对象就要调 `SafeBase<GoodA>` 的构造函数，可它只对 `GoodA` 开放，GCC 报 `SafeBase() ... is private within this context`。抄错的子类一旦被用到就编译失败。

#### 1.4.2 子类忘了写实现、名字又和基类一样：无限递归

```cpp
template <typename D> struct Base { int area() { return static_cast<D*>(this)->area(); } };
struct Sq : Base<Sq> { };   // 忘了写 area()
```

`Sq` 里没有 `area()`，`static_cast<Sq*>(this)->area()` 找到的就是继承来的 `Base<Sq>::area()` 自己，调用自己，直到栈溢出。GCC `-Wall` 会警告 `infinite recursion detected`，但只是警告。所以常见写法把子类的函数叫 `doSomethingImpl`，和基类的 `doSomething` 不同名：忘了写，就是“没有这个成员”的编译错误。

#### 1.4.3 基类的类定义里用不了子类的类型成员

```cpp
template <typename D> struct Base { using value_type = typename D::value_type; };
struct C : Base<C> { using value_type = int; };   // 编译错误
```

GCC 报 `invalid use of incomplete type 'struct C'`。原因就是 1.1 节说的：实例化 `Base<C>` 时 `C` 还没定义完。函数体里可以用（那时 `C` 已经完整），类定义里（成员类型、成员变量的类型、函数签名）不行。要用就多传一个模板参数，或者另写一个 traits 模板放子类的类型信息。

#### 1.4.4 没有共同的基类：放不进同一个容器

`Base<Derived1>` 和 `Base<Derived2>` 是两个毫无关系的类型，没有 `std::vector<Base*>` 这种东西。所有接受它的函数也得是模板（上面的 `performAction` 就是 `template <typename T> void performAction(Base<T>&)`）。要把不同子类放在一起，见[速查：运行时灵活性丢了什么](/zh/ref/cpp-syntax/#poly-flexibility)：`std::variant` + `std::visit`（类型集合固定）、按类型分批各跑一个循环、或者外层用一次虚函数选中、里面全是 CRTP。

### 1.5 CRTP 和虚函数怎么选

| | 虚函数 | CRTP |
|---|---|---|
| 调哪个函数什么时候定 | 运行时，按对象的实际类型 | 编译时，按基类的模板实参 |
| 一次调用 | 读 vptr、读 vtable、间接跳转 | 直接调用，通常内联掉 |
| 对象大小 | 多一个 vptr（8 字节） | 不变 |
| 放进同一个容器 | 可以（`vector<unique_ptr<Base>>`） | 不行，`Base<A>` 和 `Base<B>` 无关 |
| 加新的子类 | 不用重编调用方，插件也行 | 用到它的模板都要重新实例化 |
| 写错的后果 | 漏写 `override` 的函数可能没覆盖上 | 基类抄错静默 UB；同名会无限递归 |

类型在编译期能定、在热路径上，用 CRTP；要放进一个容器、要运行时加类型，用虚函数。更完整的权衡（代码膨胀、编译时间、运行时从编好的类型里挑一个）见[速查：静态多态与动态多态](/zh/ref/cpp-syntax/#polymorphism)。

### 1.6 C++23 的替代写法：deducing this

C++23 允许把 `this` 写成成员函数的第一个显式参数（explicit object parameter，常叫 deducing this），类型由编译器按调用的对象推导。基类于是不用模板参数也能拿到子类类型：

```cpp
struct FeedBase23 {
    template <typename Self>
    int on_tick(this Self&& self, int px) { return self.on_tick_impl(px); }
};
struct BybitFeed : FeedBase23 {
    int on_tick_impl(int px) { return px * 4; }
};
```

`bybit.on_tick(3)` 时 `Self` 推导成 `BybitFeed&`，`self.on_tick_impl` 直接调到子类，效果和 CRTP 一样，但 1.4.1 节的“基类抄错”不存在了（没有模板实参可抄），`FeedBase23` 也成了一个普通类。GCC 14 起、Clang 18 支持，GCC 13 还不支持。现有代码里还是 CRTP 为主。

同一套“编译期就把结构定下来”的思路，用在“一层层叠功能”上就是 Mixin（[速查：组合与 Mixin](/zh/ref/cpp-syntax/#mixin)），用在“把值提前算好”上就是 `constexpr` 一族（[速查：哪个保证编译期算](/zh/ref/cpp-syntax/#compile-time)）。
