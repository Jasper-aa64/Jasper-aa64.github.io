---
title: "虚函数：vptr、vtable 和动态多态"
date: 2026-11-02
slug: "virtual-functions"
description: "虚函数让同一句 o->handle() 在运行时按对象的实际类型调到不同的函数。编译出来是读 vptr、查 vtable、间接跳转三步；代价在要猜的间接跳转、挡住内联、两次读内存和每个对象多 8 字节；编译器在 final、局部对象这些情况下能把它省掉。最后讲继承之前为什么先想组合。"
summary: "虚调用 = 读对象开头的 vptr → 读这个类 vtable 里那一格 → 按读到的地址跳。最贵的通常不是这一跳，而是编译器没法内联；类型在编译期就能定时，可以改用静态多态。要复用一个类的实现，放成成员，不要继承它。"
categories: [Linux]
tags: [cpp, virtual, vtable, polymorphism, inheritance]
toc: true
---

同一句 `o->handle()`，`o` 指向不同子类的对象，就调到不同的函数，这叫动态多态，靠的是虚函数。这篇从编译出来的两条指令讲起：每个对象里藏着什么、每个类多了什么、一次虚调用要付哪些代价、编译器什么时候能把它省掉。对象在内存里的完整布局（多重继承时的两个 vptr、vtable 里还有什么）见[对象布局](/zh/posts/object-layout/)。

## 1. 虚函数（virtual function）：运行时按对象的类型选函数 {#virtual}

### 1.1 是什么 {#virtual-what}

基类里声明 `virtual` 的函数，通过基类指针或引用调用时，调用的是**对象实际类型**的那个版本。调用处写的是同一句 `o->handle()`，到底执行哪个函数，要到运行时看 `o` 指向的是什么才知道。

```cpp
struct Msg {
    virtual ~Msg() = default;
    virtual int handle() const = 0;   // 纯虚函数：每个子类自己实现
    int qty = 1;
};
struct TextMsg : Msg {
    int handle() const override { return qty * 2; }
};
struct ImageMsg final : Msg {    // final：不会再有子类
    int handle() const override { return qty * 3; }
};

int run(const Msg* o) { return o->handle(); }   // 可能是 TextMsg，也可能是 ImageMsg
```

典型用法：一个容器里放着不同子类的对象（`std::vector<std::unique_ptr<Msg>>`），循环里统一调 `handle()`。

### 1.2 编译出来：vptr 和 vtable {#virtual-vtable}

`run` 编译出来只有两条指令：

```asm
run(Msg const*):
        movq    (%rdi), %rax      # 1. 读对象开头的 8 字节：vptr，指向这个类的虚函数表
        jmp     *16(%rax)         # 2. 从表里第 3 格读出函数地址，跳过去（间接跳转）
```

靠的是两样东西：

- **vtable**（虚函数表）：每个有虚函数的**类**一张，存在只读数据段里，按声明顺序列出这个类每个虚函数的地址。`TextMsg` 的表里 `handle` 那格是 `TextMsg::handle`，`ImageMsg` 的是 `ImageMsg::handle`。（前两格是析构函数，所以 `handle` 在偏移 16。）
- **vptr**（虚表指针）：每个**对象**开头藏着的一个 8 字节指针，构造时指向自己那个类的 vtable。`sizeof(TextMsg)` 因此是 16：vptr 8 字节，`qty` 4 字节，再补 4 字节对齐。

所以一次虚调用 = 读 vptr → 读表里那一格 → 按读到的地址跳。

### 1.3 代价在哪 {#virtual-cost}

- **间接跳转要猜**：目标地址是读出来的，前端要靠**间接目标预测器**去猜（[#7 第 1.3 节](/zh/posts/branch-prediction-branch-optimization/)）。同一处调用，对象类型有规律（全是同一种，或者短周期重复）几乎不会错；类型随机混在一起就经常错，每次约 15–20 个周期。
- **挡住内联**：编译器不知道会调到哪个函数，就没法把它内联进来，也没法跨这次调用做优化（常量传播、合并计算、向量化）。函数体越小，这一条越亏：`handle()` 本身只有一条乘法，调用开销比它大得多。
- **多两次读内存**：第一次从对象开头读 vptr（`movq (%rdi), %rax`），第二次从 vtable 那一格读函数地址（`jmp *16(%rax)` 里的 `16(%rax)`）。这两次读落到内存的话一次约 70–120 ns，比一次调用本身贵得多，但平时很少落到内存，原因两次各不相同：
  - **vptr 和对象的数据在同一条缓存行里。** 不用虚函数，也得读这个对象的成员（比如 `mult`）。对象冷了，两种写法都要为这条行付一次缓存未命中；读 vptr 不会多出第二次未命中。虚函数这边多出来的，只有对象大了 8 字节、一条行装得更少。
  - **vtable 每个类一份，不是每个对象一份。** 它在只读数据段里，两三个类就是两三条缓存行，所有调用共用。调用频繁时一直有人读，它就一直在 L1，约 1 ns。
  - **猜对时，这两次读基本不拖慢。** CPU 不等它们读完才决定跳去哪：预测器先给出目标，CPU 接着执行被调函数，两次读在旁边并行完成，只用来核对猜得对不对。猜错了，或者这处调用还没有预测记录，就得真的等：先读 vptr，拿到它才知道去哪读函数地址，再读那一格，才能跳。两次读一前一后，没法并行。
  - **真正贵的是冷启动。** 程序空闲了一阵，这段代码用的缓存行被别的代码挤掉，下一次调用时，对象那条行和 vtable 那条行都可能不在缓存里。对象那次两种写法都要付；vtable 那次是虚函数独有的，还排在读 vptr 之后，最坏多出一次约 70–120 ns 的串行未命中（按[延迟范围](/zh/ref/cpu-memory/#latency)估算，没有实测）。在乎这一次的地方，可以换成[静态多态](/zh/ref/cpp-syntax/)，根本没有 vtable 要读。
- **每个对象多 8 字节**：小对象（比如 16 字节的消息）会因此大一截，一条缓存行装得更少。

### 1.4 编译器什么时候能省掉虚调用（devirtualization） {#virtual-devirt}

编译器能确定对象的实际类型时，就直接调用、甚至内联。三种常见情况，前两种是实测：

```cpp
int run_image(const ImageMsg* o) { return o->handle(); }   // ImageMsg 是 final
int run_local() { TextMsg l; return run(&l); }              // 对象就在眼前
```

- **`final`**：`ImageMsg` 标了 `final`，不可能有子类，`o->handle()` 只能是 `ImageMsg::handle`。`run_image` 编出来是 `movl 8(%rdi), %eax` + `leal (%rax,%rax,2), %eax`，乘 3 直接内联了，没有跳转。
- **局部对象**：`run_local` 里对象的类型就写在那，`run` 内联进来以后，整个函数编成了 `movl $2, %eax`。
- **只有一个实现**：开 `-flto`（链接期优化）后，编译器看到整个程序，某个虚函数只有一个实现时也能直接调用（这一条没有实测）。

### 1.5 不用虚函数：静态多态 {#virtual-alternatives}

类型在编译期就能定下来时，可以不要 vtable：模板和 CRTP 让“调哪个函数”在编译时就定好，调用直接内联；类型集合固定时，`std::variant` 按类型编号分派。这些写法统称静态多态，编译出来是什么、各自的代价，见[静态多态](/zh/ref/cpp-syntax/)。

### 1.6 怎么选 {#virtual-choose}

- **类型在运行时才知道、集合开放（插件、配置里读出来）**：虚函数。
- **类型集合固定、对象要放在一个容器里**：`std::variant` + `std::visit`。
- **类型在编译期就能定**：模板或 CRTP；能标 `final` 的类就标上，编译器可以直接调用。
- **大多数情况**：虚函数最好读、最好改，先用它。只有调用非常频繁、函数体又很小的地方，虚调用的代价才显眼，那时再换成[静态多态](/zh/ref/cpp-syntax/)。

## 2. 组合与继承：复用实现用成员 {#composition}


```cpp
class InheritanceInbox : public std::vector<Msg> {   // 继承：直接“是”一个 vector
};

class CompositionInbox {                                // 组合：“有”一个 vector
    std::vector<Msg> msgs_;
public:
    auto size() const noexcept { return msgs_.size(); }  // 只暴露需要的接口
};
```

**编译出来一样**：读成员和调 `size()` 都是直接读 `msgs_` 里的字段，`size()` 内联。差别全在设计上，public 继承 `std::vector` 有三个问题：

- **接口全部暴露**：`push_back`、`erase` 谁都能调，收件箱“按时间排序”这类不变量就守不住。组合只给出愿意给的函数。
- **析构函数不是虚的**：`std::vector<Msg>* p = new InheritanceInbox;` 再 `delete p` 是未定义行为。标准容器不是设计来当基类的。
- **和底层绑死**：想把 `std::vector` 换成别的容器，继承的写法所有调用方都要改，组合只改类内部。

规则：要的是“用它的实现”，放成成员（has-a）；真要“当成它来用”（is-a），并且基类是为继承设计的（有虚析构函数），才 public 继承。

