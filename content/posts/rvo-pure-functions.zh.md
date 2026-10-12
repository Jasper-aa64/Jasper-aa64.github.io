---
title: "交易系统笔记 #11：返回值优化与纯函数"
date: 2026-10-12
slug: "rvo-pure-functions"
description: "按值返回一个 64 字节的行情快照，编出来既不拷贝也不移动：调用方把地址传进来，函数直接写进去。这篇分清 RVO（C++17 起保证）、NRVO（看编译器，GCC 和 Clang 实测不一样）和一定做不了的几种（返回参数、成员、std::move 局部变量），再讲 const / pure 属性怎么让编译器合并重复调用、什么时候才需要标。输出和汇编都是 GCC 13 / Clang 18 的实测。"
summary: "按值返回结构体通常是零成本的，不用改成传出参数；要留意的是几种一定会移动或拷贝的写法。纯函数属性是向编译器做承诺：说对了少调几次，说错了是未定义行为。"
chapter: 1
categories: [Systems]
tags: [cpp, rvo, copy-elision, move-semantics, pure-functions, hft, low-latency]
toc: true
light: true
---

行情处理里常有这样的函数：算出一份盘口快照，按值返回。

```cpp
struct Snapshot { double bid[4]; double ask[4]; };
Snapshot make_snap(double px) {
    Snapshot s;
    for (int k = 0; k < 4; k++) { s.bid[k] = px - k; s.ask[k] = px + k; }
    return s;
}
```

64 字节的结构体按值返回，会不会先在函数里建一份、再拷给调用方？GCC 13 `-O2` 编出来是这样：

```text
make_snap(double):
    movq    %rdi, %rax         # 返回值就是调用方传进来的那个地址
    ...
    movups  %xmm1, (%rdi)      # 直接写进调用方的那块内存
    movups  %xmm1, 16(%rdi)
    movups  %xmm1, 32(%rdi)
    movups  %xmm0, 48(%rdi)
    ret
```

没有拷贝。调用方先在自己的栈上留好 64 字节，把地址当成一个隐藏参数放在 `%rdi` 里传进来，函数直接在那里写。函数里的 `s` 根本没有一个“自己的”副本。不超过 16 字节的小结构体连内存都不用：比如 `struct { int i; char c; double d; }`，`int` 和 `char` 拼进 `%rax`，`double` 留在 `%xmm0` 返回。

这件事在语言层面叫**拷贝消除**（copy elision）。它什么时候是保证、什么时候看编译器、什么时候一定做不了，是这篇的第一部分；第二部分讲另一种“告诉编译器可以少做事”的办法：纯函数属性。输出和汇编都是 GCC 13.3 / Clang 18、`-std=c++17 -O2`、x86-64 的实测。

## 1. 返回值优化：什么时候不拷贝

下面用一个会打印每次构造、拷贝、移动的类 `Tracer` 来看，每个例子都是实测输出。

### 1.1 RVO：返回临时对象，C++17 起是保证

`return T(...)` 返回的是一个还没有名字的临时对象（标准里叫 prvalue）。C++17 起，这种情况**保证**不调用拷贝和移动构造函数，对象从一开始就建在调用方那里。所以连拷贝、移动构造都 `= delete` 的类型也能按值返回：

```cpp
class NonCopyableNonMovable {
public:
    explicit NonCopyableNonMovable(int id) : id_(id) {}
    NonCopyableNonMovable(const NonCopyableNonMovable&) = delete;
    NonCopyableNonMovable(NonCopyableNonMovable&&) = delete;
private:
    int id_;
};

NonCopyableNonMovable create() {
    return NonCopyableNonMovable(42);       // C++17 可以；-std=c++14 实测编不过
}
```

既然是语言规则，不是优化，它就不受编译选项影响。常有人说加了 `-fno-elide-constructors`，`Tracer t = Tracer("x");` 就会多一次拷贝，在 C++17 下不对：实测加不加这个选项，都只有一次构造。

### 1.2 NRVO：返回有名字的局部对象，编译器可以做，不保证

```cpp
Tracer nrvoExample(const std::string& name) {
    Tracer obj(name);
    return obj;
}
```

`obj` 有名字，标准**允许**编译器把它直接建在调用方那里（NRVO，named RVO），但不强制。实测：

- GCC 13 / Clang 18 `-O2`：只有一次构造，NRVO 做了。
- 加 `-fno-elide-constructors`：多出一次移动构造。整个测试程序里只有这一处的输出变了，正好说明 1.1 是保证、这里是优化。
- 一条路径返回临时对象、另一条返回有名字的对象时，两个编译器不一样：

```cpp
Tracer conditionalReturn(bool flag) {
    if (flag) {
        return Tracer("temporary");
    } else {
        Tracer named("named");
        return named;              // GCC 13：一次移动；Clang 18：NRVO，没有移动
    }
}
```

编译器做不了 NRVO 时，也不会退到拷贝：从 C++11 起，`return 局部变量;` 会先当成右值、优先调用移动构造（implicit move）。所以最坏是一次移动。对 `std::string`、`std::vector` 来说，一次移动就是拷几个指针，很便宜；对 `Snapshot` 这种全是数据成员的结构体，移动和拷贝一样，要搬 64 字节。

### 1.3 一定做不了的几种

- **返回参数**：参数的内存是调用方在调用前就准备好的，不可能再和返回值那块重合。实测是一次移动。
- **返回成员、全局或静态对象**：它们活得比函数长，返回值必须是一份新对象，是一次拷贝。只是想让调用方读一下，就返回引用。
- **返回对象的一部分**（例如局部 `std::pair` 的 `return p.first;`）：返回的不是那个局部对象本身，没法消除，也不会自动移动（自动移动只针对直接写名字的局部变量），实测 C++17 和 C++23 下都是拷贝。想要移动就写 `return std::move(p.first);`，这里不会挡住任何消除。
- **`return std::move(local);`**：这把一个有名字的对象变成了别的东西，NRVO 的条件就不满足了，反而强制一次移动。GCC `-Wall` 实测会报 `-Wpessimizing-move`：“moving a local object in a return statement prevents copy elision”。

### 1.4 拷贝构造函数里不要放逻辑

拷贝和移动可能被消除，也可能不被消除，所以拷贝构造函数里的副作用（打印、计数、注册）执行几次是不确定的。一个在拷贝构造里加计数的 `Counter`，`Counter c = createCounter();` 之后实测计数是 1：代码里看起来该有的那次“拷贝”被消除了。

对热路径的意义：按值返回结构体是零成本的写法，不需要为了“省一次拷贝”改成传出参数（`void make(Snapshot& out)`）；要留意的只是 1.3 那几种情况。

## 2. 纯函数：告诉编译器调用之间能合并

### 2.1 `const` 和 `pure`：一个不读内存，一个只读不写

纯函数是这样的函数：没有副作用，返回值只取决于参数，同样的输入永远同样的输出。编译器知道一个函数是这样的，`f(x) * f(x)` 就可以只调一次。GCC 和 Clang 有两个属性：

- **`__attribute__((const))`**：返回值只取决于参数的值，函数**不读也不写**任何内存（参数是指针时，也不能读它指向的东西）。
- **`__attribute__((pure))`**：不写内存，但**可以读**全局变量或指针指向的内存。所以两次调用之间只要有一次写内存，编译器就得重新调。

实测（被调函数的定义编译器看不见时）：

```cpp
double g_state = 0;

double Func1(double) __attribute__((const));
double Func2(double x) { return Func1(x) * Func1(x) + 1.; }                     // 1 次 call
double C2(double x) { double a = Func1(x); g_state = 1; return a * Func1(x); }  // 1 次 call

double G1(double);
double G2(double x) { return G1(x) * G1(x) + 1.; }                             // 2 次 call

double P1(double) __attribute__((pure));
double P2(double x) { double a = P1(x); g_state = 1; return a * P1(x); }        // 2 次 call
```

`P2` 里两次调用之间写了全局变量 `g_state`，`pure` 函数可能读它，所以要再调一次；同样的写法换成 `const` 的 `Func1`（`C2`），还是只调一次。

### 2.2 只在编译器看不见函数体时才需要

函数定义在同一个编译单元里时，GCC 会自己分析出它是不是 `const` / `pure`（或者干脆内联），不用你标。把上面几个函数的定义写在同一个文件里，三个调用全被内联合并了，要加 `__attribute__((noipa))`（不让编译器看函数体做推断）才看得出区别。真正需要标属性的，是定义在别的 `.cpp` 或库里、又没开 LTO（链接期优化）的函数，比如热路径上调的数学库函数或第三方的定价函数。

### 2.3 说错了就是未定义行为

属性是承诺，编译器不检查。一个实际会读全局配置的函数被标成 `const`，编译器就可能把它的结果缓存起来，配置改了以后照样用旧值。所以只给真正的纯计算标：按参数算价格、算哈希、算数学函数。

### 2.4 别的写法各是什么意思

- **GCC / Clang**：`__attribute__((const))`、`__attribute__((pure))`，也可以写成 `[[gnu::const]]`、`[[gnu::pure]]`。Clang 同样认这两个属性。
- **MSVC `__declspec(noalias)`**：意思是函数只通过参数里的指针访问内存（不碰全局状态），说的是别名，和“纯”只是沾边。
- **`constexpr`**：说的是“能在编译期算”，不是“没有副作用”。`constexpr` 函数在运行时调用时，可以通过引用参数改调用方的变量。
- **`[[nodiscard]]`**：只是在你丢掉返回值时给警告，和纯不纯无关。
- **标准**：C++ 还没有标准的纯函数属性；C23 加了 `[[reproducible]]`（接近 `pure`）和 `[[unsequenced]]`（接近 `const`）。
