---
title: "未定义行为：UB、严格别名和释放后使用"
date: 2026-11-11
slug: "undefined-behavior"
description: "未定义行为（UB）是标准不规定结果的行为。编译器按“程序里没有 UB”这个前提优化，可以据此删代码、重排代码，所以 -O0 下好好的代码到 -O2 就坏了，坏的地方离写错的地方很远。严格别名规则让编译器认为不同类型的指针不指向同一个对象，省掉重读；把字节直接 reinterpret_cast 成结构体读就违反它，合法写法是 memcpy 或 std::bit_cast。释放后使用最常见的形式是 vector 扩容后的旧指针、指向临时 string 的 string_view、按引用捕获局部变量的回调，在对象池里读到的是别人的数据。用 ASan、UBSan、TSan 查。"
summary: "编译器假设程序里没有 UB，据此优化；严格别名和释放后使用是最常见的两类。写对的办法：不写有符号溢出和先用后判空，看字节用 memcpy 或 std::bit_cast，所有权写进类型，池里用下标加版本号；测试和回放开 sanitizer。"
toc: true
group: cpplinux
topic: cpp
weight: 108
---

这三样放在一起讲，是因为出错的方式一样：代码在 `-O0` 下好好的，开了优化就坏了，而且坏的地方往往不是写错的那一行。原因是编译器假设它们不会发生，并据此改写了别处的代码。

## 1. 为什么出错的地方离写错的地方很远 {#overview}

> **三样东西是一回事：编译器假设它们不会发生**
>
> - **UB 是标准不规定结果的行为**：编译器按“程序里没有 UB”这个前提去优化，可以据此删代码、重排代码。
> - **所以同一份代码 `-O0` 下好好的，`-O2` 就坏了**：坏的地方往往不是写错的那一行，而是被编译器据此改写过的另一处。
> - **严格别名和释放后使用是 UB 里最常见的两类**：前一类让编译器不重读内存，后一类让指针指向别人的数据。

## 2. UB：编译器把它当成不可能发生，据此删代码 {#ub}

```cpp
// 1. 有符号整数溢出是 UB：编译器认为 x + 1 一定大于 x，整个函数折成 return true
bool always_true(int x) { return x + 1 > x; }

// 2. 先解引用、后判空：p->x 已经执行过，编译器推断 p 不为空，把后面的判断删掉
struct Item { int x; };
int read(Item* p) {
    int v = p->x;
    if (!p) return -1;
    return v;
}

// 3. 数据竞争是 UB：done 不是原子变量，编译器可以把这次读提到循环外面，循环永远不结束
bool done = false;
void spin() {
    while (!done) {}
}
```

- **常见的 UB 还有**：数组越界、读未初始化的变量、移位的位数不小于类型的宽度。
- **编译器从 UB 里得到的好处是真的**：循环变量是 `int` 时不用考虑溢出回绕，循环才能放心展开和向量化。所以这些假设关不掉，只能不写 UB。

## 3. 严格别名：不同类型的指针被认为不指向同一个对象 {#strict-aliasing}

```cpp
// 编译器认为 *f 和 *i 不是同一块内存：写 *f 改不到 *i，所以直接返回 1，不重新读
int alias(int* i, float* f) {
    *i = 1;
    *f = 2.0f;
    return *i;
}
```

- **规则**：用一种类型的指针去读写另一种类型的对象是 UB。例外是 `char`、`unsigned char`、`std::byte`，这三种可以指向任何对象。
- **编译器借此省掉重读**：写完一个类型的指针，不用重新读另一个类型的值，值可以一直留在寄存器里。
- **最常见的违规是解析网络包**：`reinterpret_cast<const Header*>(buf)` 把一段字节直接当结构体读。它同时还有对齐问题：`buf` 里的偏移不一定满足 `Header` 的对齐要求。
- **合法的写法是 `memcpy`**，或者 C++20 的 `std::bit_cast`。开了优化，`memcpy` 一个定长的小对象就是一条 `mov`，不会真的去调函数。
- **也可以整体关掉这条假设**：`-fno-strict-aliasing`，Linux 内核就是这样编的。

```cpp
// 从字节流里读一个 uint32_t：memcpy 没有别名和对齐的问题，开优化后是一条 mov
uint32_t load_u32(const unsigned char* buf) {
    uint32_t v;
    std::memcpy(&v, buf, sizeof v);
    return v;
}
```

更多例子见[四种 cast](/zh/ref/cpp-casts/)和[类型双关](/zh/posts/type-punning-calls-compiler-hints/)。

## 4. 释放后使用：内存还回去了，指针还在用 {#uaf}

- **不只是 `delete` 之后再用**，下面三种更常见：
  - **`vector` 扩容**：扩容后，原来的迭代器、指针、引用全部失效。
  - **`string_view` 指向临时对象**：临时的 `std::string` 在这条语句结束时销毁，`string_view` 还指着它的缓冲区。
  - **lambda 按引用捕获局部变量**：回调真正执行时，那个局部变量所在的栈帧已经没了。
- **在对象池里最危险**：槽位很快会被复用，旧指针读到的不是垃圾值，而是另一笔订单的数据。程序不崩溃，结果悄悄错了。
- **怎么防**：
  - **把所有权写进类型**：谁负责释放用 `unique_ptr` 表达，只是看一眼的用裸指针或引用，并且保证活得比所有者短（[智能指针](/zh/ref/smart-pointers/)）。
  - **池里用“下标加版本号”代替裸指针**：槽每复用一次版本号加 1，拿旧句柄来访问时版本号对不上，就知道它已经失效（[#3 内存池 5.4](/zh/posts/hot-path-memory-allocators/#tagged-head) 是同一个思路）。

## 5. 怎么查：sanitizer 加编译选项 {#detect}

> **怎么查这三类问题**
>
> - **`-fsanitize=address,undefined` 跑测试和行情回放**：ASan 抓释放后使用和越界，UBSan 抓整数溢出、空指针、没对齐的访问。
> - **数据竞争用 `-fsanitize=thread`**。
> - **`-Wall -Wextra` 不留警告**。
> - **怀疑是严格别名**：加上 `-fno-strict-aliasing` 再跑一次，结果变了，基本就是它。
