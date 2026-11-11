---
title: "未定义行为：编译器据此删代码，最常见的是严格别名和释放后使用"
date: 2026-11-11
lastmod: 2026-11-11
slug: "undefined-behavior"
description: "未定义行为（UB）是标准不规定结果的行为。编译器按“程序里没有 UB”这个前提优化：有符号加法不会溢出，所以 x + 1 > x 折成 true；解引用过的指针不会是空，所以后面的判空被删；没有原子操作的空循环一定会结束，所以等标志位的循环被编成一条 ret。严格别名是其中一类：不同类型的指针被认为不指向同一个对象，编译器因此能把值留在寄存器里、把循环向量化；把字节流 reinterpret_cast 成结构体读就违反它，合法写法是 memcpy 或 std::bit_cast。释放后使用是另一类：内存还给分配器、没还给系统，所以旧指针通常不崩，而是读到下一个对象的数据。查法是 ASan、UBSan、TSan 加编译警告。"
summary: "编译器假设程序里没有 UB，并据此改写别处的代码，所以坏的地方离写错的地方很远。严格别名和释放后使用是最常撞上的两类：看字节用 memcpy 或 std::bit_cast，所有权写进类型，池里用下标加版本号；测试和回放开 sanitizer。"
toc: true
group: cpplinux
topic: cpp
weight: 108
---

未定义行为（UB）是标准不规定结果的行为，实际代码里最常撞上的两类是严格别名违规和释放后使用。它们出错的方式一样：代码在 `-O0` 下好好的，开了优化就坏了，坏的地方往往不是写错的那一行，因为编译器假设 UB 不会发生，并据此改写了别处的代码。查法也一样，都靠 sanitizer。

下面的汇编都是 GCC 16.2 `-O2` 的实测输出，按 Linux 的调用约定：第一个参数在 `edi`/`rdi`，第二个在 `rsi`，返回值在 `eax`。

## 1. UB 是什么：标准不规定结果，编译器就当它不会发生 {#what}

### 1.1 标准里有三种“不规定”：只有第三种能让编译器删代码 {#three-kinds}

C++ 标准对一段代码的结果，有三种不同程度的“不规定”。前两种结果虽然不固定，但程序仍然是对的；只有第三种让整个程序失去意义。

| 种类 | 标准怎么说 | 例子 | 后果 |
|---|---|---|---|
| 实现定义（implementation-defined） | 每个编译器自己选一种，并且写进文档 | `sizeof(long)` 在 Linux 上是 8、在 Windows 上是 4 | 换平台结果可能变，同一平台上是确定的 |
| 未指定（unspecified） | 几种结果里出哪种都行，不用写文档 | `f(a(), b())` 里 `a()` 和 `b()` 谁先算 | 每次都是合法结果之一，代码不该依赖它 |
| 未定义（undefined） | 标准对结果不提任何要求 | 有符号整数溢出、解引用空指针 | **整个程序的行为都不再有保证**，包括 UB 发生之前的代码 |

**UB 不是“结果随机”，而是“这条路径不存在”**：标准对它不提要求，编译器就可以假设任何执行都不会走到 UB，再从这个假设往回推，删掉它认为走不到的分支。

### 1.2 编译器为什么敢删：每个假设都换来一种优化 {#why}

这些假设不是编译器故意刁难，而是优化的前提。

- **假设有符号整数不溢出**：循环变量 `int i` 不会从最大值绕回负数，循环次数就能提前算出来，循环才能展开和向量化（2.1）。
- **假设解引用过的指针不为空**：后面的判空可以删掉，函数内联以后这类冗余检查很多（2.2）。
- **假设不同类型的指针不指向同一块内存**：写一个 `float*` 不会改到 `int*` 指向的值，值可以留在寄存器里不重读（第 3 节）。
- **假设没有原子操作和 IO 的循环一定会结束**：这叫向前推进保证（forward progress），空循环可以删掉或者挪动（2.3）。

**所以这些假设关不掉，只能不写 UB**：GCC 给了几个开关单独关掉其中一条（5.2），代价是对应的优化一起没了。

### 1.3 常见的 UB：一张表 {#list}

| 写法 | 编译器借此做什么 | 正确写法 |
|---|---|---|
| 有符号整数溢出：`INT_MAX + 1` | 认为 `x + 1 > x` 恒真；循环次数可提前算出 | 用无符号数；或 `__builtin_add_overflow` 检查 |
| 移位的位数不小于类型宽度，或者是负数：`1 << 32` | 不生成边界检查 | 先判断位数；x86 的移位指令只取低 5 位或 6 位，不同硬件结果不同 |
| 除以 0；`INT_MIN / -1` | 做过 `a / b` 以后，认为 `b` 不为 0，删掉后面对 `b == 0` 的判断 | 先判断再除 |
| 数组越界、指针算到对象范围之外 | 认为下标在范围内，删掉后面的边界判断 | `std::span`、`at()` 调试时用 |
| 解引用空指针 | 删掉之后的判空（2.2） | 先判空再用 |
| 读未初始化的局部变量 | 认为它可以是任何值，两次读可以不一样 | 声明时初始化；C++26 把这一条改成“错误行为”，不再是 UB，但值仍然不可靠 |
| 数据竞争：两个线程不加同步地读写同一个非原子变量 | 把读提到循环外面，或者删掉循环（2.3） | `std::atomic` 或者加锁 |
| 用别的类型的指针读写对象（严格别名） | 不重读，值留在寄存器里（第 3 节） | `memcpy`、`std::bit_cast` |
| 访问没对齐的地址：`*(int*)(buf + 1)` | 生成要求对齐的向量指令 | `memcpy` |
| 用已经释放或者生命周期已经结束的对象（释放后使用） | 无，但分配器已经把这块内存给了别人（第 4 节） | 所有权写进类型；池里用版本号 |
| 非 `void` 函数没有 `return` 就走到结尾 | 认为那条路径走不到，直接删掉（2.4） | 开 `-Wall`，警告当错误处理 |
| 修改本来就是 `const` 的对象：`const_cast` 之后写 | 认为值不变，直接用常量 | 不要写 |

## 2. 编译器怎么利用 UB：四个实测例子 {#examples}

### 2.1 有符号溢出：`x + 1 > x` 被折成常量 true {#signed-overflow}

```cpp
bool always_true(int x)    { return x + 1 > x; }
bool wraps_u(unsigned x)   { return x + 1 > x; }
```

```nasm
always_true:              ; 1. int：编译器认为不会溢出，结果恒为真
    mov   eax, 1
    ret
wraps_u:                  ; 2. unsigned：溢出时回绕到 0 是定义好的，只有 x 等于最大值时为假
    cmp   edi, -1
    setne al
    ret
```

**同一个表达式，换成无符号就要真的比一次**：无符号数溢出按 $2^{32}$ 取模回绕，是标准规定好的行为，编译器必须照顾 `x` 等于最大值的情况。有符号数溢出是 UB，编译器只按数学上的整数来推。

**这个假设换来的是循环优化**：

```cpp
int sum(int* a, int n) {
    int s = 0;
    for (int i = 0; i <= n; ++i) s += a[i];
    return s;
}
```

- **默认**：编译器认为 `i` 不会溢出，所以循环正好跑 $n+1$ 次，先算出结束地址 `a + n + 1`，循环里只剩“加、指针加 4、比较”三条。
- **加上 `-fwrapv`（规定有符号溢出回绕）**：`n` 等于 `INT_MAX` 时 `i <= n` 永远为真，循环可能不结束，次数算不出来。生成的代码每一圈都要把 32 位的 `i` 符号扩展成 64 位再算地址（多一条 `movsxd`），也不能再按结束地址比较。

### 2.2 先解引用、后判空：判空被删掉 {#null-check}

```cpp
struct Item { int x; };
int read_item(Item* p) {
    int v = p->x;          // 1. 这里已经解引用了 p
    if (!p) return -1;     // 2. 编译器推断 p 不为空，这个判断永远为假
    return v;
}
```

```nasm
read_item:
    mov   eax, DWORD PTR [rdi]    ; 只剩读 p->x，判空没了
    ret
```

**真实事故**：2009 年 Linux 内核的 tun 驱动就是这个写法，判空被 GCC 删掉，攻击者在 0 地址映射一页内存，就能绕过检查。之后内核一直用 `-fno-delete-null-pointer-checks` 编译。

**容易出现在内联以后**：两个函数各自看都没问题，一个解引用、另一个判空，内联到一起就成了上面的样子。所以判空要放在第一次使用之前。

### 2.3 等标志位的空循环：整个函数变成一条 `ret` {#data-race}

```cpp
bool done = false;              // 另一个线程会把它置为 true
void spin() {
    while (!done) {}
}
```

```nasm
spin:
    ret                         ; 循环整个没了
```

**这里撞上了两条假设**：

- **没有数据竞争**：`done` 不是原子变量，编译器可以认为没有别的线程在改它，读一次就够。
- **没有原子操作和 IO 的循环一定会结束**：循环体是空的，如果 `done` 一开始是 `false`，这个循环永远不会结束，违反了向前推进保证，所以这种情况“不会发生”。剩下的可能只有 `done` 一开始就是 `true`，循环一圈都不跑，函数直接返回。

**结果和想要的正好相反**：本来想等别的线程把 `done` 置为 `true`，现在不管 `done` 是什么都立刻返回。换成 `std::atomic<bool>`，用 `load(std::memory_order_acquire)` 读，每一圈都会重新从内存读：

```nasm
spin2:
.L16:
    movzx eax, BYTE PTR done2[rip]   ; 每一圈都重新读
    test  al, al
    je    .L16
    ret
```

x86 上 acquire 读就是一条普通的 `mov`，不比原来慢；变的只是编译器不能再删掉或挪走它（[内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/)）。

### 2.4 少写一个 `return`：`sign(0)` 返回 -1 {#missing-return}

```cpp
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    // 1. x == 0 时没有 return，走到函数结尾，这是 UB
}
```

```nasm
sign:
    xor   eax, eax
    test  edi, edi
    setg  al                    ; eax = (x > 0) ? 1 : 0
    lea   eax, -1[rax+rax]      ; 返回 2 * eax - 1，也就是 1 或 -1
    ret
```

**编译器认为 `x == 0` 走不到**：只剩两种情况，就用一个公式把两个分支合成一个，`sign(0)` 就得到 -1。GCC 对这种写法会给 `-Wreturn-type` 警告，**开 `-Wall` 并且不留警告，就能挡住这一类**。

## 3. 严格别名：不同类型的指针被认为不指向同一个对象 {#strict-aliasing}

### 3.1 规则：一个对象只能用它自己的类型去读写 {#alias-rule}

能合法访问一个 `T` 类型对象的，只有下面这几种类型的左值：

- **`T` 本身**，以及加了 `const`、`volatile` 的 `T`。
- **`T` 对应的有符号或无符号版本**：`int` 和 `unsigned int` 可以互相访问。
- **`char`、`unsigned char`、`std::byte`**：这三种可以访问任何对象，是留给“按字节看内存”的口子。

用其他类型去读写就是 UB。最典型的是 `int*` 和 `float*`：

```cpp
int alias(int* i, float* f) {
    *i = 1;
    *f = 2.0f;        // 1. 编译器认为 *f 和 *i 不是同一块内存
    return *i;        // 2. 所以 *i 还是 1，不用重读
}
int alias_same(int* i, int* j) {
    *i = 1;
    *j = 2;           // 3. 同类型的指针可能指向同一块内存
    return *i;        // 4. 必须重读
}
```

```nasm
alias:
    mov   DWORD PTR [rdi], 1
    mov   eax, 1                       ; 返回值直接是常量 1
    mov   DWORD PTR [rsi], 0x40000000  ; 2.0f 的位模式
    ret
alias_same:
    mov   DWORD PTR [rdi], 1
    mov   DWORD PTR [rsi], 2
    mov   eax, DWORD PTR [rdi]         ; 重新从内存读
    ret
```

**调用 `alias(&x, (float*)&x)` 时**：内存里的 `x` 已经被改成 `2.0f` 的位模式，函数却返回 1。本机实测：`-O2` 返回 1；`-O0` 会重读，返回 1073741824，也就是 0x40000000 当成整数。同一份代码，两种优化级别结果不一样。

### 3.2 编译器从中得到什么：值留在寄存器里，循环才能向量化 {#alias-benefit}

```cpp
void scale(float* a, const int* n) {
    for (int k = 0; k < *n; ++k) a[k] *= 2.0f;
}
```

- **默认**：写 `a[k]` 是写 `float`，改不到 `int` 类型的 `*n`。编译器在循环前把 `*n` 读一次放进寄存器，循环用 SSE 一次处理 4 个 `float`（`movups`、`addps`）。
- **加上 `-fno-strict-aliasing`**：写 `a[k]` 可能改到 `*n`，每一圈都要重读 `*n`（`cmp DWORD PTR [rsi], eax`），一次只处理一个 `float`（`movss`、`addss`），不能向量化。

**`char*` 是反过来的例子**：把上面的 `float* a` 换成 `char* a`，即使不加任何选项，编译器也每圈重读 `*n`，不向量化。因为 `char` 可以访问任何对象，写 `a[k]` 真的可能改到 `*n`。`uint8_t` 就是 `unsigned char`，有同样的问题。**热循环里通过 `char*`、`uint8_t*` 写内存，会让编译器对其他所有指针都变保守**；能用 `__restrict` 声明不重叠，或者先把 `*n` 读到局部变量里。

### 3.3 常见的违规：把字节流当结构体读、用 union 转类型 {#alias-violations}

```cpp
struct Header { uint32_t seq; uint16_t len; uint16_t type; };

// 1. 违规：buf 里存的是 unsigned char，不是 Header
const Header* h = reinterpret_cast<const Header*>(buf + off);
uint32_t seq = h->seq;

// 2. 违规（C++ 里）：写 f、读 u
union { float f; uint32_t u; } pun;
pun.f = 1.0f;
uint32_t bits = pun.u;
```

- **解析网络包最常见**：`reinterpret_cast` 同时还有对齐问题，`buf + off` 不一定是 4 的倍数。x86 上没对齐的标量读只是慢一点，编译器如果据此生成了要求对齐的向量指令，就会直接崩。
- **union 转类型**：C 语言允许，C++ 是 UB。GCC 和 Clang 作为扩展支持它，所以常常“能用”，但换编译器或者开更激进的优化就没有保证。

### 3.4 合法写法：`memcpy`、`std::bit_cast`，开了优化都是一条 `mov` {#alias-fix}

```cpp
// 1. memcpy：按字节拷贝，没有别名和对齐的问题
uint32_t load_u32(const unsigned char* buf) {
    uint32_t v;
    std::memcpy(&v, buf, sizeof v);
    return v;
}

// 2. C++20 的 std::bit_cast：两种大小相同、可平凡拷贝的类型之间换解释，可以在编译期用
uint32_t bits = std::bit_cast<uint32_t>(1.0f);   // 0x3f800000
```

```nasm
load_u32:
    mov   eax, DWORD PTR [rdi]   ; 定长的小 memcpy 被编成一条 mov，没有函数调用
    ret
```

**不用担心 `memcpy` 慢**：长度是编译期常量、而且很小时，编译器认得它，直接换成一条读指令。读整个包头也一样，拷进一个局部的 `Header` 再用。

**整体关掉这条规则也可以**：`-fno-strict-aliasing`，Linux 内核就是这样编的。代价是 3.2 那种优化全部没有了。

## 4. 释放后使用：内存还回去了，指针还在用 {#uaf}

### 4.1 为什么通常不崩：内存还给了分配器，没有还给系统 {#uaf-why}

`delete` 以后，这块内存回到 `malloc` 的空闲链表里，所在的页仍然映射在进程里，所以通过旧指针读写不会触发段错误。接下来会发生两件事：

- **分配器在这块内存里写自己的东西**：glibc 的 tcache 把空闲块串成链表，前 16 字节改写成“下一块的地址”和一个校验值。旧指针读到的头两个字段已经不是原来的数据了。
- **下一次同样大小的 `new` 拿回这块内存**：tcache 是后进先出，刚释放的那块最先被分出去。旧指针读到的就是新对象的数据；通过旧指针写，改的也是新对象。

**所以释放后使用的典型症状不是崩溃，而是别处的数据被悄悄改了**；崩的话，往往是写坏了分配器的链表，下一次 `malloc` 或 `free` 时才崩，崩溃点和写错的地方没有关系。

### 4.2 常见的四种写法：大多数不是 `delete` 之后再用 {#uaf-forms}

```cpp
// 1. vector 扩容：元素搬到新内存，旧的指针、引用、迭代器全部失效
std::vector<Order> v;
Order* first = &v.emplace_back();
v.emplace_back();                 // 容量不够时整体搬家
first->qty = 0;                   // 写的是已经还回去的旧内存

// 2. string_view 指向临时对象：临时 string 在这一行结束时销毁
std::string_view name = make_name();   // make_name 返回 std::string
use(name);                             // 指向已经释放的缓冲区

// 3. 回调按引用捕获局部变量：回调执行时，这个栈帧已经没了
void subscribe(Bus& bus) {
    int count = 0;
    bus.on_tick([&count] { ++count; });   // 稍后在别的地方执行
}

// 4. 返回局部变量的引用
const std::string& name() {
    std::string s = "abc";
    return s;
}
```

- **`vector` 扩容最常见**：本机实测，容量从 3 扩到 6 时，`&v[0]` 换了地址。拿着元素指针的地方，只要中间有 `push_back`，就要想一下会不会扩容；能提前 `reserve` 就提前。
- **第 4 种编译器会警告**（`-Wreturn-local-addr`），前三种不会。

### 4.3 对象池里更隐蔽：槽马上被复用，读到的是别的订单 {#uaf-pool}

对象池把释放的槽立刻给下一个请求，所以释放后使用在池里几乎一定会读到另一个有效对象，数据看起来完全正常，只是属于别人。

**防法是“下标加版本号”代替裸指针**：

```cpp
struct Handle { uint32_t index; uint32_t gen; };

struct Slot { Order order; uint32_t gen = 0; bool used = false; };

Order* get(std::vector<Slot>& pool, Handle h) {
    Slot& s = pool[h.index];
    // 1. 槽每释放一次版本号加 1；旧句柄的版本号对不上，说明它已经失效
    if (!s.used || s.gen != h.gen) return nullptr;
    return &s.order;
}
```

和[内存池 5.4 的带版本号的头指针](/zh/posts/hot-path-memory-allocators/#tagged-head)是同一个思路：用一个计数器区分“同一个位置的不同次使用”。

### 4.4 怎么防：把所有权写进类型 {#uaf-prevent}

- **谁负责释放用 `unique_ptr` 表达**：只是看一眼的用裸指针或引用，并且保证它活得比所有者短（[智能指针](/zh/ref/smart-pointers/)）。
- **异步回调按值捕获，或者捕获 `shared_ptr`/`weak_ptr`**：回调执行时再 `lock()`，对象没了就不做（[智能指针 5.1](/zh/ref/smart-pointers/#shared-from-this-why)）。
- **池里不发裸指针**：发句柄，每次用都查版本号。

## 5. 怎么查：sanitizer 跑测试，编译选项兜底 {#detect}

### 5.1 三个 sanitizer：各抓什么、多慢 {#sanitizers}

| 选项 | 抓什么 | 怎么做到 | 代价 |
|---|---|---|---|
| `-fsanitize=address`（ASan） | 释放后使用、越界、重复释放、返回栈上地址 | 每 8 字节内存配 1 字节影子内存，记录哪些能访问；释放的块先放进隔离区，不马上给别人 | 慢 1.5–3 倍，内存多 2–3 倍 |
| `-fsanitize=undefined`（UBSan） | 有符号溢出、移位越界、空指针、没对齐的访问、少 `return` | 在每个可能出 UB 的操作前插一个检查 | 慢 10%–50% |
| `-fsanitize=thread`（TSan） | 数据竞争 | 记录每次访问的线程和时间戳，比较有没有先后关系 | 慢 5–15 倍，内存多 5–10 倍 |

- **ASan 和 TSan 不能同时开**：两者都要接管内存布局。一般是两套构建，各跑一遍。
- **UBSan 可以和 ASan 一起开**：`-fsanitize=address,undefined`。
- **严格别名没有好用的 sanitizer**：只能靠 3.4 的写法和下面的选项来排查。

### 5.2 编译选项：警告当错误，单独关掉某条假设 {#flags}

- **`-Wall -Wextra`，并且不留警告**：少 `return`、返回局部变量的地址、有符号和无符号比较，这些都有警告。
- **`-fwrapv`**：有符号溢出按回绕处理，不再是 UB；代价见 2.1。
- **`-fno-strict-aliasing`**：关掉严格别名；代价见 3.2。
- **`-fno-delete-null-pointer-checks`**：不删判空；内核在用。

这几条都是用性能换安全，适合用来定位问题，或者用在没法逐行审查的旧代码上。

> **怀疑是 UB 时怎么定位**
>
> - **先比 `-O0` 和 `-O2` 的结果**：只在开优化后出错，UB 的可能性很大。
> - **再开 `-fsanitize=address,undefined` 跑同一份输入**：多数情况会直接报出出错的那一行。多线程的再单独用 TSan 跑一次。
> - **sanitizer 没报，就逐个加 5.2 的选项**：加上 `-fno-strict-aliasing` 结果就对了，基本是别名问题；加上 `-fwrapv` 就对了，是有符号溢出。
> - **最后看汇编**：找到被删掉的判断或者被挪走的读，对着本页第 2、3 节的例子找原因。
