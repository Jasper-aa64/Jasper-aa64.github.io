---
title: "const、constexpr、consteval、constinit：哪个保证编译期算"
date: 2026-11-02
slug: "const-constexpr"
description: "四个关键字长得像，回答的是不同的问题：const 只读，不保证编译期；constexpr 变量一定编译期算，函数只是能；consteval 每次调用都必须在编译期；constinit 保证静态变量在编译期初始化，但之后可以改。再讲非类型模板参数和编译期生成查找表。"
summary: "const 管的是能不能改，不管什么时候算；要编译期算出来，变量用 constexpr，函数用 consteval；静态变量怕初始化顺序问题，用 constinit。"
toc: true
group: cpplinux
weight: 105
aliases: ["/posts/const-constexpr/"]
---

四个关键字长得像，回答的是不同的问题：

| 关键字 | 修饰什么 | 保证在编译期算出来吗 | 之后能改吗 |
|---|---|---|---|
| `const` | 变量、参数、成员函数 | **不保证** | 不能 |
| `constexpr` | 变量 | 保证 | 不能 |
| `constexpr` | 函数 | 不保证：用在要求常量的地方才在编译期算 | — |
| `consteval` | 函数 | 保证：每次调用都在编译期算 | — |
| `constinit` | 静态生命周期的变量 | 保证初始化在编译期完成 | **能**（不带 `const`） |

## 1. `const`：只读，不是编译期常量 {#const}

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

## 2. `constexpr`：变量一定编译期算，函数“能”编译期算 {#constexpr}

- **`constexpr` 变量**：初始值必须在编译期算出来，否则编译报错。
- **`constexpr` 函数**：**允许**在编译期算。用在要求常量的地方（`constexpr` 变量、模板实参、数组大小、`static_assert`），一定在编译期算；参数是运行时的值，就是一次普通调用。

```cpp
constexpr int twice(int x) { return x + x; }
constexpr int four = twice(2);           // 编译期算出 4
int twice_rt(int n) { return twice(n); } // 运行时算
```

`twice_rt` 编出来是一条 `leal (%rdi,%rdi), %eax`，和普通函数一样。`constexpr` 不是“优化提示”。

## 3. `consteval`：每次调用都必须在编译期 {#consteval}

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

## 4. `constinit`：静态变量在编译期初始化，但可以改 {#constinit}

`constinit` 只管一件事：**全局变量、`static` 变量的初始化必须在编译期完成**，做不到就编译报错。它**不**带 `const`，之后可以改。

```cpp
constexpr int somefunc() { return 27; }    // 必须是 constexpr，否则下一行编译失败
constinit int g_counter = somefunc();      // 进 .data，初值 27 写在可执行文件里
// ...
++g_counter;                               // 可以改
```

它防的是**静态初始化顺序问题**（static initialization order fiasco）：运行时初始化的全局变量由启动代码在 `main` 之前去算，不同源文件之间谁先谁后标准不规定，一个全局变量读到另一个还没初始化的就是 bug。`constinit` 保证没有这一步。

## 5. 非类型模板参数：把常量变成类型的一部分 {#nttp}

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

`Vector<4>` 和 `Vector<8>` 是两个类型，各编一份，循环次数是常量，编译器能整个展开或向量化。代价是[第 3 条](/zh/ref/cpp-syntax/#poly-cost)的代码膨胀。模板实参必须是编译期常量：`const int d = 4;` 可以，`int n = 4; const int d = n;` 不行。

## 6. 编译期生成查找表 {#lut}

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

## 7. 怎么选 {#compile-time-choose}

- 值必须编译期就有，算不出来应该报错 → `constexpr` 变量，或 `consteval` 函数。
- 一份实现编译期、运行时都要用 → `constexpr` 函数，需要时加 `if consteval`。
- 全局 / `static` 变量要能改，但不要运行时初始化 → `constinit`。
- 只是不想被改 → `const`。

