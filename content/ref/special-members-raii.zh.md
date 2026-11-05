---
title: "构造、拷贝、析构和 RAII：对象的一生和异常安全"
date: 2026-11-02
slug: "special-members-raii"
description: "一个类有六个特殊成员函数，不写时编译器按成员逐个替你生成，可写了其中一个，别的会被悄悄删掉或退化。类里管着一块堆内存时，编译器生成的拷贝只拷指针，两个对象析构时把同一块内存释放两次，这就是三法则、五法则的来历，而零法则说的是干脆别自己管。再讲初始化列表按声明顺序执行、析构顺序和构造相反、RAII 把释放写进析构函数，以及异常抛出后栈怎么展开、为什么析构函数不能抛、异常安全的三个等级和异常的代价。"
summary: "类自己管资源，就要自己写析构、拷贝和移动；能交给 std::string、vector、unique_ptr 管的，一个都不用写。RAII 让资源跟着对象走：不管是正常 return 还是异常，离开作用域都会调析构函数，这是 C++ 里做清理的标准办法。"
toc: true
group: cpplinux
topic: cpp
weight: 102
---

C++ 里一个对象从创建到销毁，每一步都有一个函数负责：构造、拷贝、移动、赋值、析构。大多数时候你一个都不写，编译器替你生成；可类里一旦管着一块堆内存、一个文件或一把锁，生成的那些版本就会出错。这页从编译器生成了什么讲起，到 RAII 和异常为止，它们说的其实是同一件事：资源的释放要绑在对象的析构上。

## 1. 六个特殊成员函数：编译器替你写了什么

### 1.1 六个函数，默认都是“按成员逐个来” {#six}

| 函数 | 签名 | 什么时候调用 |
|---|---|---|
| 默认构造 | `T()` | `T a;` |
| 拷贝构造 | `T(const T&)` | `T b = a;`、按值传参 |
| 拷贝赋值 | `T& operator=(const T&)` | `b = a;`（`b` 已经存在） |
| 移动构造 | `T(T&&)` | `T b = std::move(a);`、返回局部对象 |
| 移动赋值 | `T& operator=(T&&)` | `b = std::move(a);` |
| 析构 | `~T()` | 对象离开作用域、`delete` |

你不写，编译器生成的版本就是对每个成员（和基类）各做一遍同样的事：拷贝构造就是逐个拷贝成员，析构就是逐个析构成员。这对 `int`、`std::string`、`std::vector` 这类成员都对，因为它们自己知道怎么拷、怎么析构。

生成的默认构造也是逐个默认构造成员，可 `int`、指针这种内置类型的“默认构造”什么都不做。**局部对象里没写初值的 `int` 成员是不确定的值，不是 0**，所以内置类型的成员最好直接在声明处给初值：`int count_ = 0;`。

### 1.2 写了一个，别的会被删掉或退化 {#generation}

编译器并不总是六个都生成。规则的出发点是：你亲手写了其中一个，说明这个类在管什么特殊的东西，编译器就不敢再替你生成某些别的。

| 你写了 | 默认构造 | 拷贝构造 / 拷贝赋值 | 移动构造 / 移动赋值 |
|---|---|---|---|
| 什么都没写 | 生成 | 生成 | 生成 |
| 任何一个普通构造函数（拷贝、移动以外） | **不生成** | 生成 | 生成 |
| 析构函数 | 生成 | 生成（已不推荐依赖） | **不生成，退化成拷贝** |
| 拷贝构造或拷贝赋值 | 写了拷贝构造就不生成 | 另一个生成（已不推荐依赖） | **不生成，退化成拷贝** |
| 移动构造或移动赋值 | 写了移动构造就不生成 | **删除** | 另一个不生成 |

最容易踩的是第三行：只写了一个析构函数（哪怕是空的），移动操作就不生成了，`std::move` 过去调的是拷贝。下面这段程序里，`OnlyDtor` 只多了一个空析构函数：

```cpp
struct Nothing  { Tracer t; };
struct OnlyDtor { Tracer t; ~OnlyDtor() {} };

Nothing  a; Nothing  b = std::move(a);   // 输出：move ctor
OnlyDtor c; OnlyDtor d = std::move(c);   // 输出：copy ctor
```

（`Tracer` 是一个在每个特殊成员函数里打印一行的类。）`std::is_move_constructible_v<OnlyDtor>` 照样是真的：类型特征只问“能不能用右值构造”，拷贝构造接受 `const T&`，右值也能绑上去。**所以移动“退化成拷贝”时没有任何报错，只是变慢了**。反过来，只写了移动构造的类，拷贝构造被删除，`std::is_copy_constructible_v` 是假的，拷贝它直接编译不过。移动本身怎么工作，见[左值、右值和移动语义](/zh/ref/move-semantics/)。

## 2. 拷贝：浅拷贝和深拷贝

### 2.1 浅拷贝：两个对象指着同一块内存 {#shallow}

一个自己管堆内存的类：

```cpp
class Buffer {
public:
    explicit Buffer(const char* s) : size_(std::strlen(s) + 1), data_(new char[size_]) {
        std::memcpy(data_, s, size_);
    }
    ~Buffer() { delete[] data_; }
private:
    std::size_t size_;
    char* data_;
};

Buffer a("hello");
Buffer b = a;          // 编译器生成的拷贝构造
```

编译器生成的拷贝构造逐个拷成员，`data_` 是个指针，拷的就是指针的值：`b.data_` 和 `a.data_` 指向同一块内存。离开作用域时 `b`、`a` 先后析构，同一块内存被 `delete[]` 两次（double free）；在那之前，改 `b` 的内容 `a` 也跟着变。这叫浅拷贝。要的是深拷贝：新对象自己 `new` 一块，把内容拷过去。

<svg viewBox="0 0 760 270" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="左边浅拷贝：对象 a 和 b 的 data_ 指针指向同一块堆内存，析构时被释放两次；右边深拷贝：a 和 b 各自指向自己的一块堆内存" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sm0bg  { fill: #fbfaf7; }
    .sm0obj { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .sm0bad { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .sm0ok  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .sm0ink { fill: #1c1b18; font-size: 13px; }
    .sm0mut { fill: #6b6558; font-size: 12px; }
    .sm0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .sm0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sm0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0obj { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0bad { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0ok { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0ink, :root:is([data-theme="dark"], [data-theme="black"]) .sm0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm0hd { fill: #a19caf; }
  </style>
  <defs><marker id="sm0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sm0hd"/></marker></defs>
  <rect class="sm0bg" x="0" y="0" width="760" height="270" rx="10"/>
  <text class="sm0ttl" x="24" y="32">浅拷贝：编译器生成的拷贝构造</text>
  <text class="sm0ttl" x="404" y="32">深拷贝：自己写的拷贝构造</text>
  <rect class="sm0obj" x="24" y="56" width="150" height="56" rx="6"/>
  <text class="sm0ink" x="38" y="78">对象 a</text>
  <text class="sm0mut" x="38" y="100">size_ = 6，data_</text>
  <rect class="sm0obj" x="24" y="146" width="150" height="56" rx="6"/>
  <text class="sm0ink" x="38" y="168">对象 b</text>
  <text class="sm0mut" x="38" y="190">size_ = 6，data_</text>
  <rect class="sm0bad" x="236" y="104" width="124" height="44" rx="6"/>
  <text class="sm0ink" x="250" y="131">堆上 "hello"</text>
  <path class="sm0ln" d="M174,95 L205,95 L205,118 L233,118" marker-end="url(#sm0a)"/>
  <path class="sm0ln" d="M174,185 L205,185 L205,134 L233,134" marker-end="url(#sm0a)"/>
  <text class="sm0mut" x="24" y="232">两个指针，一块内存：b、a 先后析构，</text>
  <text class="sm0mut" x="24" y="250">同一块被 delete[] 两次</text>
  <rect class="sm0obj" x="404" y="56" width="150" height="56" rx="6"/>
  <text class="sm0ink" x="418" y="78">对象 a</text>
  <text class="sm0mut" x="418" y="100">size_ = 6，data_</text>
  <rect class="sm0obj" x="404" y="146" width="150" height="56" rx="6"/>
  <text class="sm0ink" x="418" y="168">对象 b</text>
  <text class="sm0mut" x="418" y="190">size_ = 6，data_</text>
  <rect class="sm0ok" x="612" y="62" width="124" height="44" rx="6"/>
  <text class="sm0ink" x="626" y="89">堆上 "hello"</text>
  <rect class="sm0ok" x="612" y="152" width="124" height="44" rx="6"/>
  <text class="sm0ink" x="626" y="179">堆上 "hello"</text>
  <path class="sm0ln" d="M554,85 L609,85" marker-end="url(#sm0a)"/>
  <path class="sm0ln" d="M554,175 L609,175" marker-end="url(#sm0a)"/>
  <text class="sm0mut" x="404" y="232">各自一块：谁析构谁释放自己那块，</text>
  <text class="sm0mut" x="404" y="250">改 b 也不影响 a</text>
</svg>

### 2.2 三法则、五法则、零法则 {#rule-of-three}

`Buffer` 写了析构函数，是因为它亲手 `new` 了内存；可只要析构函数里要释放什么，编译器生成的拷贝就一定是错的，拷贝构造和拷贝赋值也得一起写。这就是**三法则**：析构、拷贝构造、拷贝赋值，写了一个，另外两个也要写。C++11 有了移动，再加上移动构造和移动赋值，就是**五法则**：不写移动不会出错，但按 1.2 的规则，移动会退化成拷贝，白白多一次 `new` 和 `memcpy`。

**更好的办法是零法则：一个都不写，把资源交给会自己管理的成员。** `Buffer` 的 `char*` 换成 `std::string` 或 `std::vector<char>`，编译器生成的六个函数就全对了，因为每个成员自己会深拷贝、会移动、会释放。要独占一块资源（文件、句柄）就用 `std::unique_ptr` 加自定义删除器（见 [智能指针](/zh/ref/smart-pointers/)）。真正需要自己写五个函数的，只有 `std::string`、`std::vector` 这种本身就是“资源管理者”的类。

### 2.3 拷贝赋值：自赋值和 copy-and-swap {#copy-and-swap}

拷贝赋值比拷贝构造难写，因为左边的对象已经有一块内存了。直觉的写法是先释放旧的，再按右边的大小分配新的、拷过去：

```cpp
Buffer& operator=(const Buffer& o) {
    delete[] data_;                       // 1. 释放旧的
    size_ = o.size_;
    data_ = new char[size_];              // 2. 分配新的：可能抛 std::bad_alloc
    std::memcpy(data_, o.data_, size_);   // 3. 自赋值时 o.data_ 已经在第 1 步被释放了
    return *this;
}
```

两个问题。`a = a` 时 `o` 就是自己，第 1 步把要拷的数据先删了。第 2 步 `new` 失败抛异常时，`data_` 还指着已经释放的内存，对象处在一个析构时会再释放一次的坏状态。

copy-and-swap 一次解决两个问题：参数按值传，进函数前已经用拷贝构造拷好了一份；函数里只把自己和这份副本的成员交换，旧的内容随副本离开函数时析构。

```cpp
Buffer(const Buffer& o) : size_(o.size_), data_(new char[size_]) {   // 深拷贝
    std::memcpy(data_, o.data_, size_);
}
Buffer& operator=(Buffer o) noexcept {   // 按值传：拷贝在进函数之前完成
    swap(o);
    return *this;
}                                        // o 带着旧的 data_ 析构
void swap(Buffer& o) noexcept {
    std::swap(size_, o.size_);
    std::swap(data_, o.data_);
}
```

**可能失败的那一步（分配和拷贝）发生在动 `*this` 之前**：拷贝失败，异常在进函数前抛出，左边的对象一点没变；拷贝成功，剩下的只有交换两个指针，不会失败。自赋值也不用特判，拷一份再换，结果还是自己。代价是自赋值时白拷一次，而且旧对象有足够大的内存时也不会复用。上面这个 `Buffer` 用 GCC 16.2 编译，跑 `a = b; a = a; Buffer c = a;` 后打印出三个 `world`，没有重复释放。传值的参数还顺带让同一个函数兼任移动赋值：传进来的是右值时，副本是移动构造出来的。

## 3. 构造和析构的顺序

### 3.1 初始化列表：按声明的顺序，不按你写的顺序 {#init-order}

构造函数的初始化列表（冒号后面那串）才是真正初始化成员的地方，进到函数体 `{}` 里时，成员已经全部构造好了，在函数体里再写 `x = 1;` 就成了“先默认构造、再赋值”两步。`const` 成员、引用成员、没有默认构造函数的成员只能在初始化列表里初始化，因为它们不能先“空着”再赋值。

成员初始化的顺序是它们**在类里声明的顺序**，和初始化列表里写的先后无关：

```cpp
struct Derived : Base {
    M x, y;                                    // 声明顺序：x、y
    Derived() : y("y"), x("x") { /* ... */ }   // 写的顺序：y、x
};
```

实际先构造 `x` 再构造 `y`，GCC 开 `-Wall` 会给 `-Wreorder` 警告。顺序不一致本身不出错，出错的是成员之间有依赖时：比如 `available_` 声明在 `alloc_` 前面，初始化列表写 `available_(alloc_ - len_)`，用到的 `alloc_` 这时还没初始化。**有依赖的成员，按依赖顺序声明，初始化列表也照这个顺序写**。

### 3.2 explicit 和委托构造 {#explicit}

只接受一个参数的构造函数，默认还兼做隐式类型转换：`Buffer` 的构造函数如果不加 `explicit`，`void send(Buffer b); send("hi");` 就会悄悄从字符串构造一个 `Buffer`，`Buffer b = "hi";` 也能编过。单参数构造函数一般都标 `explicit`，只有那种“本来就该能自动转换”的（比如从 `int` 构造一个有理数）才不标。

几个构造函数有一段共同的初始化时，可以让一个构造函数调用另一个（委托构造，C++11）：`Buffer() : Buffer("") {}`。被委托的那个构造函数完整跑完，对象就算构造好了；委托的这个如果在自己的函数体里抛异常，析构函数会被调用，这一点和普通构造函数里抛异常不同（见 5.2）。

### 3.3 析构顺序：和构造正好反过来 {#dtor-order}

构造一个派生类对象的顺序是：基类（它的成员，再它的构造函数体）→ 自己的成员（按声明顺序）→ 自己的构造函数体。析构完全反过来。上面那个 `Derived` 实际打印出来是：

```text
ctor Base::b        Base body       ctor x       ctor y       Derived body
~Derived body       dtor y          dtor x       ~Base body   dtor Base::b
```

反过来的原因是后构造的可能依赖先构造的：成员构造时可以用基类，基类不会用到派生类的成员；析构时先拆掉依赖别人的，被依赖的最后走。析构函数体运行时，成员都还在，可以放心使用。

基类的析构函数要不要是虚函数，取决于会不会通过基类指针 `delete` 派生类对象：会，就必须是虚的，否则只调基类的析构函数，派生类的部分不析构，是未定义行为（见[虚函数](/zh/ref/virtual-functions/)）；不会被当作基类用的类（比如标了 `final` 的），不需要虚析构函数，加了反而让每个对象多一个 vptr。

## 4. RAII：把释放写进析构函数

### 4.1 资源跟着对象走 {#raii}

RAII（resource acquisition is initialization，资源获取即初始化）的意思是：构造函数里拿到资源，析构函数里释放，资源的寿命和一个对象绑在一起。C++ 保证一个对象离开作用域时一定调它的析构函数，不管是正常走到 `}`、中途 `return`、`break`，还是有异常穿过这一层，所以释放这一步不会被漏掉。

```cpp
void append_log(const std::string& line) {
    std::lock_guard<std::mutex> lock(log_mutex);   // 构造时加锁
    std::ofstream out("app.log", std::ios::app);   // 构造时打开文件
    if (!out) return;                              // 提前返回：文件没打开，锁照样解
    out << line << '\n';                           // 抛异常：文件照样关，锁照样解
}                                                  // 正常走到这里：先关文件，再解锁
```

C 里同样的函数要在每个返回点之前手动 `unlock`、`fclose`，常见写法是把清理代码集中到函数末尾、出错时 `goto` 过去；漏一个返回点就泄漏一个资源。**RAII 把“记得释放”从每个调用者身上，挪到了写类的那个人身上，写一次析构函数，所有用法都对**。标准库里的 `std::lock_guard`、`std::unique_lock`、`std::fstream`、`std::unique_ptr`、`std::vector`，都是 RAII。

RAII 管的不只是内存，凡是“拿了要还”的都算：锁、文件、socket、数据库连接、临时目录。和对象大不大、大小在编译期确不确定都没有关系。

### 4.2 自己写包装类：先把拷贝删掉 {#raii-copy}

给一个裸指针写最简单的 RAII 包装：

```cpp
class NumberHolder {
public:
    explicit NumberHolder(Number* p) : p_(p) {}
    ~NumberHolder() { delete p_; }
    NumberHolder(const NumberHolder&) = delete;              // 不删，拷一份就 delete 两次
    NumberHolder& operator=(const NumberHolder&) = delete;
private:
    Number* p_;
};

{
    NumberHolder h(create_number(kInteger));   // 要有名字：没名字的临时对象在这一行结束就析构了
    use(h);
}                                              // 在这里 delete
```

析构函数里释放资源，编译器生成的拷贝就会让两个对象各释放一次，所以要么写深拷贝，要么像这里一样禁止拷贝。“独占一个指针、离开作用域 `delete`、不能拷贝只能移动”，标准库里已经有了，就是 `std::unique_ptr<Number>`，自己写包装类时先想想它能不能直接用。

## 5. 异常：出错时栈怎么展开

### 5.1 throw 之后发生什么：栈展开 {#unwinding}

`throw` 以后，程序沿着调用链往回找最近的、类型匹配的 `catch`。每离开一层函数，这一层里已经构造好的局部对象都按构造的反顺序析构，这个过程叫栈展开（stack unwinding）。下面的程序里 `h` 抛异常，`g` 没有 `catch`，`f` 有：

```cpp
struct Guard { const char* n; ~Guard() { std::printf("  ~Guard %s\n", n); } };
void h() { Guard g{"h"}; std::puts("  h throws"); throw std::runtime_error("disk full"); }
void g() { Guard g{"g"}; h(); std::puts("  never printed"); }
void f() {
    Guard a{"f"};
    try { g(); }
    catch (const std::exception& e) { std::printf("  caught in f: %s\n", e.what()); }
}
```

<svg viewBox="0 0 760 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="栈展开：h 抛出异常，先析构 h 里的 Guard，离开 h；g 没有 catch，析构 g 里的 Guard，离开 g；到 f 的 try 找到匹配的 catch，执行 catch；f 正常结束时才析构 f 里的 Guard" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sm1bg  { fill: #fbfaf7; }
    .sm1fr  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .sm1th  { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .sm1ct  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .sm1ink { fill: #1c1b18; font-size: 13px; }
    .sm1mut { fill: #6b6558; font-size: 12px; }
    .sm1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .sm1ex  { stroke: #c0543c; stroke-width: 2; fill: none; }
    .sm1exh { fill: #c0543c; }
    .sm1exl { fill: #c0543c; font-size: 12px; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1fr { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1th { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1ct { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1ink, :root:is([data-theme="dark"], [data-theme="black"]) .sm1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1ex { stroke: #f08a72; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1exh { fill: #f08a72; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sm1exl { fill: #f08a72; }
  </style>
  <defs><marker id="sm1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sm1exh"/></marker></defs>
  <rect class="sm1bg" x="0" y="0" width="760" height="290" rx="10"/>
  <text class="sm1ttl" x="24" y="32">调用栈（新的在上面）</text>
  <text class="sm1ttl" x="430" y="32">实际打印的顺序</text>
  <rect class="sm1th" x="24" y="48" width="280" height="56" rx="6"/>
  <text class="sm1ink" x="38" y="70">h()：局部 Guard h</text>
  <text class="sm1mut" x="38" y="92">throw runtime_error("disk full")</text>
  <rect class="sm1fr" x="24" y="114" width="280" height="56" rx="6"/>
  <text class="sm1ink" x="38" y="136">g()：局部 Guard g</text>
  <text class="sm1mut" x="38" y="158">没有 catch，后面那行不执行</text>
  <rect class="sm1fr" x="24" y="180" width="280" height="88" rx="6"/>
  <text class="sm1ink" x="38" y="202">f()：局部 Guard f</text>
  <rect class="sm1ct" x="38" y="214" width="252" height="42" rx="6"/>
  <text class="sm1ink" x="50" y="240" style="font-size:12px">try { g(); } catch (exception&amp;)</text>
  <path class="sm1ex" d="M304,76 L340,76 L340,235 L293,235" marker-end="url(#sm1a)"/>
  <text class="sm1exl" x="348" y="112">~Guard h</text>
  <text class="sm1exl" x="348" y="178">~Guard g</text>
  <text class="sm1ink" x="430" y="70">① h throws</text>
  <text class="sm1ink" x="430" y="100">② ~Guard h：离开 h</text>
  <text class="sm1ink" x="430" y="130">③ ~Guard g：离开 g</text>
  <text class="sm1ink" x="430" y="160">④ caught in f: disk full</text>
  <text class="sm1ink" x="430" y="190">⑤ ~Guard f：f 正常返回时</text>
  <text class="sm1mut" x="430" y="230">Guard f 不在被展开的那几层里：</text>
  <text class="sm1mut" x="430" y="248">异常在 f 里就被接住了，它等 f</text>
  <text class="sm1mut" x="430" y="266">自己结束时才析构</text>
</svg>

**栈展开会调析构函数，这是 RAII 能在异常时照样释放资源的原因。** C 里的 `setjmp` / `longjmp` 也能跳回很多层以外，但它只是恢复寄存器，不析构跳过的那些局部对象，在 C++ 里用它跳过有析构函数的对象是未定义行为。一个异常一直没被 `catch` 时，程序调 `std::terminate` 结束，这时栈展不展开由实现决定，所以 `main` 里通常要有一个兜底的 `catch`。

C++ 的异常是语言里的控制流机制，和 CPU 的“异常”（缺页、除零这类故障和陷阱）不是一回事：空指针解引用不会变成一个能 `catch` 的 C++ 异常，它在 Linux 上是一个 `SIGSEGV` 信号（见[进程地图](/zh/ref/cpp-linux/#segments)）。

### 5.2 构造函数可以抛，析构函数不要抛 {#ctor-dtor-throw}

构造函数没法返回错误码，抛异常是它报告失败的正常方式：文件打不开、内存分不到，就别让一个“半成品”对象存在。构造函数里抛出异常时，已经构造好的成员和基类会被析构，**但这个对象自己的析构函数不会被调用**，因为它从没构造完成。这就是为什么资源要放进成员（每个成员各自 RAII）：构造函数里先 `new` 一块给裸指针成员、再做别的事抛了异常，那块内存没人释放。

析构函数反过来，不应该抛。栈展开时正在析构局部对象，如果某个析构函数又抛出一个异常，同时就有两个异常在飞，C++ 不知道该处理哪个，直接调 `std::terminate`。C++11 起析构函数默认就是 `noexcept` 的，在里面 `throw` 而没在函数内接住，也会直接 `terminate`。析构函数里可能失败的操作（比如关闭文件时刷盘失败），要么在析构函数里自己吞掉，要么另外提供一个 `close()` 让调用者显式调用、自己处理错误。

### 5.3 noexcept：承诺不抛 {#noexcept}

`noexcept` 是函数对调用者的承诺：我不会抛异常。真的抛了，异常不会往外传，程序直接 `std::terminate`。这个承诺有实际用处：`std::vector` 扩容时要把旧元素搬到新内存，只有元素的移动构造是 `noexcept` 的，它才敢用移动，否则用拷贝，因为搬到一半移动抛了异常，旧数组已经被移空，没法恢复原样（详见[移动语义](/zh/ref/move-semantics/)）。所以移动构造、移动赋值、`swap`、析构函数，能标 `noexcept` 的都标上。

### 5.4 异常安全的三个等级 {#guarantees}

一个函数抛异常以后，对象处在什么状态，分三个等级：

| 等级 | 抛异常以后 | 例子 |
|---|---|---|
| 基本保证 | 不泄漏资源，对象仍然合法（能析构、能再赋值），但值可能变了 | 大多数标准库操作 |
| 强保证 | 要么完全成功，要么像没调用过一样，状态回到调用前 | `vector::push_back`（元素的移动 `noexcept` 或可拷贝时）、copy-and-swap 的赋值 |
| 不抛保证 | 一定不抛 | 析构函数、`swap`、移动操作 |

强保证的通用做法和 copy-and-swap 一样：**先在副本上做所有可能失败的事，成功了再用一个不会失败的操作（交换指针）换上去**。不抛保证是这一切的地基：`swap` 和析构函数要是能抛，任何更高的保证都做不出来。

### 5.5 代价：不抛几乎不花钱，抛一次很贵 {#cost}

GCC、Clang 在 Linux 上用的是“零开销”异常：正常路径上不执行任何额外指令，展开时要用的信息（哪段代码有哪些对象要析构、`catch` 在哪）放在单独的 `.eh_frame`、`.gcc_except_table` 表里（见[函数调用栈帧](/zh/ref/stack-frame/)的 CFI）。代价全在抛出那一刻：在堆上分配异常对象，按返回地址一层层查表、逐层析构，再在运行时比对 `catch` 的类型，一次 `throw` 加 `catch` 是微秒级。本机（Windows，MinGW GCC 16.2 `-O2`）测了一个只隔一层函数的 `throw` + `catch`，平均约 1.5 µs 一次，不抛时那次调用约 1 ns。

正常路径也不是完全免费：可能抛异常的调用会限制编译器的部分优化，表本身让二进制变大。所以异常适合真正罕见的错误（文件不存在、内存不够、配置写错），不适合当作每秒发生成千上万次的普通分支，比如解析用户输入时“这一项不是数字”更适合用返回值（`std::optional`、`std::expected`）表示。
