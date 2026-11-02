---
title: "左值、右值和移动语义：std::move、完美转发"
date: 2026-11-02
slug: "move-semantics"
description: "拷贝一个持有堆内存的对象要把整块内存复制一遍，可很多源对象马上就要销毁，复制完就扔。移动语义让编译器分清“之后还要用的对象”和“马上没人要的对象”，对后者直接把资源交过去。分辨的依据是值类别：左值、将亡值、纯右值。再讲三种引用各绑定什么、移动构造怎么写、std::move 为什么什么都不移动、vector 扩容为什么只认 noexcept 的移动、返回局部变量时发生了什么，以及模板里的 T&&、引用折叠和 std::forward。"
summary: "移动就是把源对象的指针拿过来、把源对象留成空的，只拷几个字节。std::move 只是一次类型转换，真正挑中移动构造的是重载决议；有名字的右值引用本身是左值，所以模板里要用 std::forward 把参数按原来的类别转出去。"
toc: true
group: cpplinux
topic: cpp
weight: 101
---

拷贝一个 `std::vector<int>` 或 `std::string`，要新开一块堆内存，再把元素一个个复制过去。如果源对象之后还要用，这一步省不掉；可很多时候源对象马上就要销毁：函数返回的临时对象、表达式算出来的中间结果，复制完就被扔掉。这时与其复制，不如把它那块内存直接交给新对象。**移动语义要解决的就是让编译器分清两种对象：之后还会被用到的，和马上没人要的**，后一种可以放心地把资源拿走。分辨的依据，是每个表达式的值类别。

## 1. 值类别：每个表达式都属于一类

### 1.1 两个问题：有没有身份，能不能被移动 {#value-categories}

值类别描述的是表达式，不是变量，也不是类型。判断它只要问两个问题：这个表达式是否指着一个能说出是“哪一个”的对象（有身份）；它的资源能不能被拿走（能被移动）。

<svg viewBox="0 0 760 266" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="三类值：左值有身份、不能被移动；将亡值既有身份又能被移动；纯右值没有身份、能被移动。左值和将亡值合称泛左值，将亡值和纯右值合称右值" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .mv0bg  { fill: #fbfaf7; }
    .mv0l   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .mv0x   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .mv0p   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .mv0ink { fill: #1c1b18; font-size: 12.5px; }
    .mv0mut { fill: #6b6558; font-size: 12px; }
    .mv0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .mv0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0l { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0x { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0p { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0ink, :root:is([data-theme="dark"], [data-theme="black"]) .mv0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv0ln { stroke: #a19caf; }
  </style>
  <rect class="mv0bg" x="0" y="0" width="760" height="266" rx="10"/>
  <text class="mv0mut" x="260" y="38" text-anchor="middle">glvalue（泛左值）：有身份，能说出是哪一个对象</text>
  <path class="mv0ln" d="M24,58 L24,48 L496,48 L496,58"/>
  <rect class="mv0l" x="24" y="66" width="232" height="104" rx="6"/>
  <text class="mv0ttl" x="38" y="90">lvalue 左值</text>
  <text class="mv0ink" x="38" y="112">有名字的变量 x、s</text>
  <text class="mv0ink" x="38" y="131">返回引用的调用 ref(s)</text>
  <text class="mv0ink" x="38" y="150">字符串字面量 "abc"</text>
  <rect class="mv0x" x="264" y="66" width="232" height="104" rx="6"/>
  <text class="mv0ttl" x="278" y="90">xvalue 将亡值</text>
  <text class="mv0ink" x="278" y="112">std::move(s)</text>
  <text class="mv0ink" x="278" y="131">返回 T&amp;&amp; 的调用</text>
  <text class="mv0ink" x="278" y="150">指着一个对象，但可以搬空它</text>
  <rect class="mv0p" x="504" y="66" width="232" height="104" rx="6"/>
  <text class="mv0ttl" x="518" y="90">prvalue 纯右值</text>
  <text class="mv0ink" x="518" y="112">字面量 42、x + 1</text>
  <text class="mv0ink" x="518" y="131">按值返回的调用 make()</text>
  <text class="mv0ink" x="518" y="150">std::string("a")</text>
  <path class="mv0ln" d="M264,178 L264,188 L736,188 L736,178"/>
  <text class="mv0mut" x="500" y="208" text-anchor="middle">rvalue（右值）：能被移动，资源可以拿走</text>
  <text class="mv0mut" x="24" y="236">有身份、不能移动 = 左值；两样都有 = 将亡值；没有身份、能移动 = 纯右值。</text>
  <text class="mv0mut" x="24" y="254">纯右值用来初始化一个对象，需要时编译器才把它落成一个临时对象。</text>
</svg>

用 `decltype((表达式))` 可以让编译器自己说出类别：结果是 `T&` 就是左值，`T&&` 是将亡值，不带引用的 `T` 是纯右值。下面是 GCC 16.2 的实际输出：

```cpp
template <class T> struct Cat      { static constexpr const char* v = "prvalue"; };
template <class T> struct Cat<T&>  { static constexpr const char* v = "lvalue"; };
template <class T> struct Cat<T&&> { static constexpr const char* v = "xvalue"; };
#define CAT(e) std::printf("%-22s %s\n", #e, Cat<decltype((e))>::v)

std::string make() { return "hi"; }
std::string& ref(std::string& s) { return s; }

int x = 1; std::string s; int&& r = 2;
CAT(x); CAT(42); CAT(x + 1); CAT(s); CAT(make()); CAT(ref(s));
CAT(std::move(s)); CAT(r); CAT("abc"); CAT(std::string("a"));
```

```text
x                      lvalue
42                     prvalue
x + 1                  prvalue
s                      lvalue
make()                 prvalue
ref(s)                 lvalue
std::move(s)           xvalue
r                      lvalue
"abc"                  lvalue
std::string("a")       prvalue
```

“能放在等号左边的是左值”这个说法只是近似：`const int c = 1;` 里的 `c` 是左值，却不能赋值；`std::string() = "x"` 左边是纯右值，却能编译。“右值没有地址”也不对：`std::string("a")` 落成临时对象以后就在栈上有地址，只是语言不让你对它写 `&`。**真正的分界是身份和能否移动**，字符串字面量 `"abc"` 是左值，因为它是放在 `.rodata` 里的一个数组，一直都在（[进程地图](/zh/ref/cpp-linux/#segments)）。

### 1.2 有名字的右值引用是左值 {#named-rvalue-ref}

上面输出里最反直觉的一行是 `r`：它的类型是 `int&&`，表达式 `r` 却是左值。原因是它有名字。有名字就意味着后面的代码还能再用它，如果编译器在第一次用到 `r` 时就把它的资源搬走，第二次用到的就是一个空壳。所以规则是：**变量的类型可以是右值引用，但只要通过名字去用它，它就是左值**；想再把它当右值用，得自己写 `std::move(r)`，明确表示“后面不再用它了”。这一条是第 5 节完美转发要解决的问题的根源。

## 2. 三种引用：各自能绑定什么

### 2.1 左值引用、const 左值引用、右值引用 {#references}

| 参数类型 | 能绑定左值 | 能绑定右值 | 用来做什么 |
|---|---|---|---|
| `T&` | 能 | 不能 | 要改调用者的对象 |
| `const T&` | 能 | 能，临时对象的寿命延长到引用结束 | 只读，什么都收 |
| `T&&` | 不能 | 能 | 收“马上没人要”的对象，好拿走它的资源 |

`const T&` 什么都能接，所以 C++11 以前一个拷贝构造函数 `T(const T&)` 就能处理所有情况，代价是对临时对象也只能复制。右值引用 `T&&` 只接右值，它和 `const T&` 一起出现时，重载决议会让右值优先选 `T&&`、左值只能选 `const T&`。**拷贝构造和移动构造就是靠这一组重载分开的**：传进来的是左值，调 `T(const T&)` 复制；是右值，调 `T(T&&)` 搬走。

## 3. 移动构造和移动赋值

### 3.1 移动：拿走指针，把源对象留成空的 {#move-ctor}

一个持有堆内存的类，拷贝和移动的差别就在构造函数里：

```cpp
class Buf {
public:
    explicit Buf(std::size_t n) : p_(new char[n]), n_(n) {}
    ~Buf() { delete[] p_; }
    Buf(const Buf& o) : p_(new char[o.n_]), n_(o.n_) {        // 拷贝：新开一块，逐字节复制
        std::memcpy(p_, o.p_, n_);
    }
    Buf(Buf&& o) noexcept : p_(o.p_), n_(o.n_) {              // 移动：拿走指针
        o.p_ = nullptr; o.n_ = 0;                             // 源对象留成空的，析构时 delete[] nullptr 什么也不做
    }
    Buf& operator=(Buf o) noexcept {                          // 按值传参：拷贝还是移动由调用方决定
        std::swap(p_, o.p_); std::swap(n_, o.n_);
        return *this;                                         // 旧资源跟着参数 o 一起析构
    }
private:
    char* p_;
    std::size_t n_;
};
```

<svg viewBox="0 0 760 252" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="左边是拷贝：b 和 c 各指向一块 1 KiB 的堆内存，c 那块是新分配再逐字节复制的。右边是移动：b 拿走了 a 原来那块内存的指针，a 的指针被置空、大小为 0，只拷了 16 字节" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .mv1bg  { fill: #fbfaf7; }
    .mv1o   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .mv1h   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .mv1new { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .mv1ink { fill: #1c1b18; font-size: 12.5px; }
    .mv1mut { fill: #6b6558; font-size: 12px; }
    .mv1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .mv1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .mv1cut { stroke: #b9b2a6; stroke-width: 1.4; fill: none; stroke-dasharray: 4 4; }
    .mv1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1o { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1h { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1new { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1ink, :root:is([data-theme="dark"], [data-theme="black"]) .mv1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1cut { stroke: #55505e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .mv1hd { fill: #a19caf; }
  </style>
  <defs><marker id="mv1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="mv1hd"/></marker></defs>
  <rect class="mv1bg" x="0" y="0" width="760" height="252" rx="10"/>
  <text class="mv1ttl" x="24" y="32">拷贝：Buf c = b;</text>
  <rect class="mv1o" x="24" y="56" width="140" height="46" rx="6"/>
  <text class="mv1ink" x="36" y="84">b：p，n = 1024</text>
  <rect class="mv1o" x="24" y="140" width="140" height="46" rx="6"/>
  <text class="mv1ink" x="36" y="168">c：p，n = 1024</text>
  <rect class="mv1h" x="226" y="56" width="140" height="46" rx="6"/>
  <text class="mv1ink" x="238" y="84">堆上 1 KiB</text>
  <rect class="mv1new" x="226" y="140" width="140" height="46" rx="6"/>
  <text class="mv1ink" x="238" y="160">新开 1 KiB，</text>
  <text class="mv1ink" x="238" y="177">逐字节复制过来</text>
  <path class="mv1ln" d="M164,79 L223,79" marker-end="url(#mv1a)"/>
  <path class="mv1ln" d="M164,163 L223,163" marker-end="url(#mv1a)"/>
  <text class="mv1mut" x="24" y="222">两块内存，复制了 1 KiB</text>
  <text class="mv1ttl" x="404" y="32">移动：Buf b = std::move(a);</text>
  <rect class="mv1o" x="404" y="56" width="150" height="46" rx="6"/>
  <text class="mv1ink" x="416" y="84">a：nullptr，n = 0</text>
  <rect class="mv1o" x="404" y="140" width="150" height="46" rx="6"/>
  <text class="mv1ink" x="416" y="168">b：p，n = 1024</text>
  <rect class="mv1h" x="606" y="98" width="130" height="46" rx="6"/>
  <text class="mv1ink" x="618" y="126">原来那 1 KiB</text>
  <path class="mv1cut" d="M554,79 L590,79 L590,110 L603,110"/>
  <text class="mv1mut" x="560" y="72">断开</text>
  <path class="mv1ln" d="M554,163 L590,163 L590,132 L603,132" marker-end="url(#mv1a)"/>
  <text class="mv1mut" x="404" y="222">一块内存，只拷了指针和大小，共 16 字节</text>
</svg>

移动构造做了两件事：把 `o` 的指针和大小拿过来；把 `o` 的指针置空。第二步不能省，否则两个对象指着同一块内存，析构时会 `delete[]` 两次。**移动的开销和对象持有多少数据无关**，`Buf` 管着 1 KiB 还是 1 GiB，移动都只拷 16 字节。反过来，没有堆资源的类型（`int`、只含几个 `int` 的结构体）移动和拷贝是一回事，移动语义对它们没有意义。

### 3.2 std::move：只是一次类型转换，什么都不移动 {#std-move}

`std::move(x)` 的实现就是 `static_cast<T&&>(x)`：把左值 `x` 转成将亡值，告诉重载决议“这个对象可以被搬空”。它本身不调用任何构造函数，单独写一句什么也不会发生：

```cpp
Buf a(1024);
std::move(a);                // 结果被丢掉：GCC 警告 ignoring return value，a 原封不动
Buf b = std::move(a);        // 这一句才调用移动构造
Buf c = b;                   // 拷贝
a = std::move(c);            // 参数 o 由移动构造得到，再和 a 交换
```

运行输出（构造函数里加了打印）：

```text
a.size()=1024
move
a.size()=0 b.size()=1024
copy
move
a.size()=1024 c.size()=0
```

第一行说明单独的 `std::move(a)` 没碰 `a`；真正的移动发生在 `Buf b = ...` 这次初始化里，因为右边是将亡值，重载决议挑中了 `Buf(Buf&&)`。**`std::move` 只负责改类别，挑中移动构造的是重载决议。**

由此还有一个容易漏掉的情况：对 `const` 对象调 `std::move`，得到的是 `const T&&`。它绑不到 `T&&`（会丢掉 const），却能绑到 `const T&`，于是悄悄调了拷贝构造，不报错也不警告。const 对象没法被搬空，移动对它不起作用。

### 3.3 被移走的对象：只能析构或重新赋值 {#moved-from}

`Buf` 的移动构造明确把源对象设成了“空”，所以 `a.size()` 是 0。标准库类型的约定更宽松：被移走的对象处于“有效但未指定”的状态，也就是它的不变量还成立、可以析构、可以重新赋值，但它现在装着什么不作保证。libstdc++ 里被移走的 `std::string` 实际上是空串，可代码不能依赖这一点。**对被移走的对象，安全的操作只有两种：析构它，或者给它赋一个新值。**

### 3.4 noexcept：vector 扩容只认不会抛异常的移动 {#noexcept}

`std::vector` 满了要扩容：分配一块更大的内存，把旧元素搬过去，释放旧内存。`push_back` 承诺强异常保证：如果中途抛了异常，vector 要恢复原样，像什么都没发生过。用拷贝来搬，这一点很容易做到：拷到第 5 个元素时抛了异常，旧内存里的元素都还完好，扔掉新内存就行。用移动来搬就不行了：前 4 个元素已经被搬空，第 5 个移动时抛异常，要把前 4 个搬回去，而往回搬的移动也可能抛异常，恢复不了。

所以 vector 扩容用的是 `std::move_if_noexcept`：元素的移动构造标了 `noexcept`（或者这个类型根本不能拷贝），才用移动；否则退回拷贝。同一个类型，只差一个 `noexcept`，往 vector 里放 1000 个元素：

```cpp
int copies = 0, moves = 0;
template <bool NoExcept>
struct Item {
    Item() = default;
    Item(const Item&) { ++copies; }
    Item(Item&&) noexcept(NoExcept) { ++moves; }
};
// 各自 emplace_back 1000 次
```

```text
move is noexcept:      copies=0 moves=1023 capacity=1024
move may throw:        copies=1023 moves=0 capacity=1024
```

容量从 1 一路翻倍到 1024，扩容时一共搬了 1 + 2 + 4 + … + 512 = 1023 次元素。**没标 `noexcept` 的移动构造，在 vector 扩容时一次都不会被用到**，全部变成拷贝。所以自己写移动构造和移动赋值时要标 `noexcept`；`= default` 的移动构造，只要每个成员的移动都不抛异常，编译器会自动把它算成 `noexcept`。

## 4. 不写 std::move 也会移动的地方

### 4.1 返回局部变量：先尝试 NRVO，不行就隐式移动 {#return}

```cpp
N plain()     { N n; return n; }                       // NRVO
N moved()     { N n; return std::move(n); }            // 多此一举
N two(bool f) { N a, b; if (f) return a; return b; }   // 两个候选
```

`-O2` 和 `-O0` 输出一样：

```text
plain:
  ctor
moved:
  ctor
  move
two:
  ctor
  ctor
  move
```

`plain` 只构造了一次：编译器让 `n` 直接构造在调用者给返回值留的位置上，连移动都省了，这叫具名返回值优化（NRVO），原理见[函数调用栈帧](/zh/ref/stack-frame/)。`moved` 多了一次移动：`return std::move(n)` 返回的不再是“一个局部变量的名字”，NRVO 的条件不满足了，只能先构造 `n` 再移动出去，GCC 为此专门报 `-Wpessimizing-move`。`two` 有两个候选，编译器没法提前知道该把哪个构造在返回位置上，NRVO 做不了；但 C++11 起，`return 局部变量` 会先把它当右值试一次，所以这里是移动而不是拷贝。**返回局部变量时不要写 `std::move`**：能省的时候它挡住 NRVO，省不了的时候编译器本来就会移动。

返回纯右值（`return N();`）更简单：C++17 起保证直接构造在返回位置上，不需要移动构造存在。

### 4.2 临时对象和“按值接收再移动” {#sink}

传给函数的临时对象本来就是纯右值，`v.push_back(std::string("x"))` 会自动选中 `push_back(T&&)`，不用写 `std::move`。只有当源对象是有名字的变量、而你确定之后不再用它时，才需要 `std::move` 把它转成右值。

一个常见写法是让函数按值接收参数，再把参数移动到成员里：

```cpp
class User {
    std::string name_;
public:
    void set_name(std::string s) { name_ = std::move(s); }
};
```

调用者传左值，参数 `s` 由拷贝得到，再移动进 `name_`：一次拷贝加一次移动；传右值，`s` 由移动得到，再移动进去：两次移动，没有拷贝。一个函数同时照顾了两种调用者，代价是比分别写 `const std::string&` 和 `std::string&&` 两个重载多一次移动，对 `std::string` 这类移动很便宜的类型通常值得。`Buf::operator=(Buf o)` 用的也是这个思路。

## 5. 模板里的 T&&：万能引用和完美转发

### 5.1 万能引用：T 要靠推导得出 {#forwarding-ref}

在函数模板里，`template <class T> void f(T&& t)` 的 `T&&` 不是右值引用，而是**万能引用**（标准里叫转发引用，forwarding reference）：传左值进来，`T` 推导成 `U&`；传右值进来，`T` 推导成 `U`。所以它左值右值都能接。`auto&& x = ...` 也是一样。

这个特殊规则只在 `T` 需要推导、而且形式恰好是 `T&&` 时才生效。`void f(std::vector<T>&& v)`、`void f(const T&& t)`、类模板成员函数里已经定下来的 `T&&`，都是普通的右值引用，只接右值。

### 5.2 引用折叠：出现一个 & 就是左值引用 {#collapsing}

`T` 推导成 `U&` 以后，参数类型 `T&&` 就成了 `U& &&`，引用的引用。C++ 用引用折叠把它化简成一个引用：

| 组合 | 结果 |
|---|---|
| `U& &` | `U&` |
| `U& &&` | `U&` |
| `U&& &` | `U&` |
| `U&& &&` | `U&&` |

两个都是 `&&` 才得到 `&&`，只要有一个 `&` 就是 `&`。所以传左值时参数是 `U&`，传右值时是 `U&&`，万能引用就是这么“万能”的。

### 5.3 std::forward：把参数按原来的类别转出去 {#forward}

万能引用解决了“接”，没解决“转”：按 1.2 节，参数 `t` 有名字，在函数体里它永远是左值。直接把 `t` 传给下一层，右值也会被当成左值，本来可以移动的变成了拷贝：

```cpp
void sink(const std::string&) { std::puts("  copy into sink"); }
void sink(std::string&&)      { std::puts("  move into sink"); }

template <class T> void by_name(T&& t)  { sink(t); }                  // t 有名字，是左值
template <class T> void forward_(T&& t) { sink(std::forward<T>(t)); } // 按原来的类别转出去
```

```text
by_name(s):
  copy into sink
by_name(std::move(s)):
  copy into sink
forward_(s):
  copy into sink
forward_(std::string("x")):
  move into sink
```

`by_name(std::move(s))` 传进去的明明是将亡值，到 `sink` 那里却成了拷贝。`std::forward<T>(t)` 就是 `static_cast<T&&>(t)`，配合引用折叠：传左值时 `T` 是 `U&`，`T&&` 折叠成 `U&`，转出去还是左值；传右值时 `T` 是 `U`，转出去是 `U&&`，恢复成右值。**`std::move` 是无条件转成右值，`std::forward` 是按调用者传进来的类别原样还原**，所以前者用在“我不再用它了”，后者只用在万能引用的参数上。

完美转发最常见的用处是“替别人构造对象”的函数：`std::make_unique`、`std::make_shared`、`vector::emplace_back` 都要把一串参数原样交给 `T` 的构造函数。写一个简化版：

```cpp
template <class T, class... Args>
std::unique_ptr<T> my_make_unique(Args&&... args) {
    return std::unique_ptr<T>(new T(std::forward<Args>(args)...));
}
auto p = my_make_unique<std::string>(3, 'z');   // *p == "zzz"
```

可变参数包里每个参数各自推导、各自转发，传进来的临时对象到了 `T` 的构造函数那里仍然是右值，能被移动。`emplace_back` 比 `push_back` 好在这里：它直接在 vector 的内存里用这些参数构造元素，连“先构造一个临时对象再移动进去”的那次移动都省了。

本页代码都在 GCC 16.2 `-std=c++20 -O2 -Wall -Wextra` 下编译运行过，输出是实际结果。
