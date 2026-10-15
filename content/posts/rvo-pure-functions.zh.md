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

没有拷贝。调用方先在自己的栈上留好 64 字节，把这块地方的地址当成一个隐藏参数放在 `%rdi` 里传进来，函数直接往那里写。函数里的 `s` 根本没有一个“自己的”副本，`return s` 也就什么都不用拷。不超过 16 字节的普通结构体连这块内存都不用，直接放在寄存器里带回来。

这叫**拷贝消除**（copy elision），办法只有一个：让要返回的对象从一出生就住在调用方准备的那块内存里。能不能省掉拷贝，全看函数能不能做到这一点。后半篇讲另一件让编译器少做事的事：同样的参数把函数调两次，什么时候能只调一次。输出和汇编都是 GCC 13.3 / Clang 18、`-std=c++17 -O2`、x86-64 的实测。

## 1. 返回值优化：什么时候不拷贝

下面用一个会打印每次构造、拷贝、移动的类 `Tracer` 来看，每个例子都是实测输出。

### 1.1 RVO：返回临时对象，C++17 起是保证

`return T(...)` 返回的对象，是在 `return` 这一刻才造出来的，所以它总能直接造在调用方那里。C++17 把这件事写成了语言规则：`T(...)` 这种还没有名字的值（标准里叫 prvalue）不再先变成一个临时对象再拷走，而是直接拿去初始化最终的那个对象。中间没有第二个对象，也就谈不上拷贝或移动，连拷贝、移动构造都 `= delete` 的类型也能这样按值返回：

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

既然是语言规则而不是优化，编译选项也关不掉它。常有人说加了 `-fno-elide-constructors`（关掉拷贝消除的选项），`Tracer t = Tracer("x");` 就会多一次拷贝，在 C++17 下不对：实测加不加，都只有一次构造。

### 1.2 NRVO：返回有名字的局部对象，编译器可以做，不保证

有名字的局部对象不一样：它在声明那一行就出生了，比 `return` 早。编译器想把它直接建在调用方那里，就得在它出生时认定“最后返回的就是它”。

```cpp
Tracer nrvoExample(const std::string& name) {
    Tracer obj(name);
    return obj;
}
```

这里只有一个对象，每条路径都返回它，认定没有风险。GCC 13 和 Clang 18 `-O2` 都做了，实测只有一次构造，这叫 NRVO（named RVO）。但它只是标准允许的优化：加上 `-fno-elide-constructors`，这里就多出一次移动，1.1 的例子却不受影响。

两个对象同时活着，就没法认定了：

```cpp
Tracer pick(bool flag) {
    Tracer a("a"), b("b");
    if (flag) return a;    // 一次移动
    return b;              // 一次移动
}
```

调用方那块内存只能放一个对象。把 `a` 放进去，走到 `return b` 时它还占着，放 `b` 也一样，所以两个都只能先建在函数自己的栈上，返回时再挪过去。介于两者之间的情况，编译器就不一样了。一条路径返回临时对象、另一条返回有名字的对象时，两条路径不会同时有对象，其实可以做：实测 Clang 18 做了，GCC 13 没做，多一次移动。能不能认定，要看编译器分析得多细。

认定不了时，编译器也不会退到拷贝：从 C++11 起，`return 局部变量;` 会先把它当成右值，优先调用移动构造（implicit move），所以最坏是一次移动。对 `std::string`、`std::vector` 来说，一次移动就是拷几个指针，很便宜；对 `Snapshot` 这种全是数据成员的结构体，移动和拷贝一样，要搬 64 字节。

### 1.3 一定做不了的几种

下面几种情况根本没法让要返回的对象出生在调用方那里：它不是这个函数自己造的，或者不是一个完整的对象，或者 `return` 后面没直接写它的名字。

- **返回参数**：参数在调用之前就由调用方造好了，放在别处，不可能再出生一次。参数也算局部变量，会自动移动，实测是一次移动。
- **返回成员、全局或静态对象**：它们在函数之前就在，之后还要接着用，返回值只能另造一份，是一次拷贝。只想让调用方读一下，就返回引用。
- **返回对象的一部分**（例如局部 `std::pair` 的 `return p.first;`）：要返回的只是 `p` 的一个成员，整个 `p` 放不进返回值那块内存。它也不会自动移动（自动移动只认直接写名字的局部变量），实测 C++17 和 C++23 下都是拷贝。想要移动就写 `return std::move(p.first);`，这里本来就没有消除可挡。
- **`return std::move(local);`**：`local` 本来可以 NRVO，但 `return` 后面写的已经不是它的名字，而是一次函数调用的结果，编译器就不认了，反而强制一次移动。GCC `-Wall` 实测会报 `-Wpessimizing-move`：“moving a local object in a return statement prevents copy elision”。

所以热路径上按值返回，照 `make_snap` 那样写就行：一个对象从头用到尾、每条路径都返回它，或者直接 `return T(...)`。这样写既不拷贝也不移动，用不着为了“省一次拷贝”改成传出参数（`void make(Snapshot& out)`）。会多出移动或拷贝的，只有 1.2 里编译器认定不了的写法和上面这几种。

### 1.4 拷贝构造函数只做拷贝：编译器可以不调用它

`Tracer` 每拷贝、移动一次就打印一行，可上面好几个例子实测只打印了一行构造：拷贝、移动构造函数压根没被调用。按说编译器不能这么做。优化一般守一条底线：程序能看到的结果，要和一行一行照着代码执行时一样（标准里叫 as-if 规则）。打印就是能看到的结果，所以一次会打印的函数调用，编译器不能自己删掉。拷贝消除是标准专门开的例外：拷贝、移动构造函数里就算打印了、计了数，编译器也可以不调用它。像 1.1 那样直接返回临时对象时，标准干脆规定不调用。

这样一来，拷贝、移动构造函数会被调用几次，要看函数怎么写、用哪个编译器、开了什么选项。1.2 里一条路径返回临时对象、另一条返回有名字对象的函数，GCC 13 多打印一次移动，Clang 18 不打印；`nrvoExample` 加上 `-fno-elide-constructors`，也会多打印一次。打印只是输出不一样。这两个构造函数里要是做了有用的事，比如统计一共拷贝了几次、给拷出来的那份分配新编号、写一条审计日志，程序的结果就会跟着编译器变。

所以拷贝、移动构造函数里只做拷贝和移动。每个对象都要做一次的事，放进构造函数和析构函数，成对地做。比如数“现在有几个对象活着”的 `Counter`，每个构造函数里加 1，析构函数里减 1：

```cpp
class Counter {
public:
    Counter() { ++instance_count_; }
    Counter(const Counter&) { ++instance_count_; }
    ~Counter() { --instance_count_; }
    static int instance_count() { return instance_count_; }
private:
    static int instance_count_;
};

Counter createCounter() { return Counter(); }
```

`Counter c = createCounter();` 之后实测计数是 1。想看不省拷贝时的样子，得退回 C++14 再加 `-fno-elide-constructors`（C++17 起这种写法的拷贝关不掉）。这时函数里的临时对象先拷成返回值，返回值再拷进 `c`，多了两次拷贝，计数还是 1：两份中间对象用完就析构，加上去的 1 又减了回来。省掉拷贝时，中间对象根本没造出来，它的构造和析构一起省掉，加 1 和减 1 同时没了。所以成对记的账，省不省拷贝都对得上。

## 2. 纯函数：告诉编译器调用之间能合并

同样的参数把一个函数调两次，比如 `f(x) * f(x)`，编译器能不能只调一次？函数体就在眼前时，它自己看得出来；函数定义在别的 `.cpp` 或库里时，它看不见里面做了什么，只能假设它可能改了全局变量、可能写了日志，两次调用的结果和效果都可能不同，只能老老实实调两次。纯函数属性就是你替这个函数向编译器保证：它没有这些副作用，返回值只取决于输入。

### 2.1 `const` 和 `pure`：一个不读内存，一个只读不写

保证有两种强度，GCC 和 Clang 各用一个属性：

- **`__attribute__((const))`**：返回值只取决于参数的值，函数**不读也不写**任何内存（参数是指针时，也不能读它指向的东西）。
- **`__attribute__((pure))`**：不写内存，但**可以读**全局变量或指针指向的内存。两次调用之间只要写过内存，它读到的东西就可能变了，编译器得重新调。

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

`P2` 里两次调用之间写了全局变量 `g_state`，`pure` 的 `P1` 可能读它，所以要再调一次；同样的写法换成 `const` 的 `Func1`（`C2`），它保证不读内存，写了也不影响，还是只调一次。

### 2.2 只在编译器看不见函数体时才需要

函数定义在同一个编译单元里时，GCC 会自己分析出它是不是 `const` / `pure`，或者干脆内联，用不着你标。真正需要标属性的，是定义在别的 `.cpp` 或库里、又没开 LTO（链接期优化：链接时才把各个文件的函数体放在一起看）的函数，比如热路径上调的数学库函数或第三方的定价函数。

### 2.3 说错了就是未定义行为

属性是承诺，编译器不检查。一个实际会读全局配置的函数被标成 `const`，编译器就可能把它的结果缓存起来，配置改了以后照样用旧值。所以只给真正的纯计算标：按参数算价格、算哈希、算数学函数。

### 2.4 别的写法各是什么意思

- **GCC / Clang**：`__attribute__((const))`、`__attribute__((pure))`，也可以写成 `[[gnu::const]]`、`[[gnu::pure]]`。Clang 同样认这两个属性。
- **MSVC `__declspec(noalias)`**：意思是函数只通过参数里的指针访问内存（不碰全局状态），说的是别名，和“纯”只是沾边。
- **`constexpr`**：说的是“能在编译期算”，不是“没有副作用”。`constexpr` 函数在运行时调用时，可以通过引用参数改调用方的变量。
- **`[[nodiscard]]`**：只是在你丢掉返回值时给警告，和纯不纯无关。
- **标准**：C++ 还没有标准的纯函数属性；C23 加了 `[[reproducible]]`（接近 `pure`）和 `[[unsequenced]]`（接近 `const`）。
