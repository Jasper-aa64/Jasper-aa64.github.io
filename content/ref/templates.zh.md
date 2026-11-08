---
title: "模板：写一份，编译器按类型各生成一份"
date: 2026-11-08
slug: "templates"
description: "模板解决什么问题（类型不同逻辑一样、常量提到编译期、做法提到编译期），实例化（用到才生成、实参推导、为什么定义放头文件、代价），特化和偏特化，约束模板参数（SFINAE、enable_if、C++20 concepts、if constexpr），变参模板和折叠表达式，以及和虚函数的区别。"
summary: "模板是写给编译器的生成规则：用到哪种类型，编译器就照着生成一份，生成出来和手写的一样快、一样严格。代价是每种类型一份代码、编译变慢、报错难读；concepts 把约束写到签名上。"
toc: true
group: cpplinux
topic: cpp
weight: 106
aliases: ["/posts/templates/"]
---

同一个栈，要存 `int`，也要存 `std::string`。没有模板，只有两种写法：

- **每种类型抄一份**：`IntStack`、`StringStack`，修一个 bug 要改好几处。
- **存 `void*` 或公共基类的指针**：一份代码什么都能存，但类型信息丢了，取出来要自己转回去，转错了编译器不报；还多了一层指针。

模板是第三种写法：**逻辑只写一份，用到哪种类型，编译器就照着生成一份**。生成出来的代码和手写的 `IntStack` 一样快，类型检查也一样严格。

## 1. 模板解决什么问题 {#why}

1. **类型不同、逻辑一样：写一份，各类型各生成一份**
   - **例子**：`std::vector<T>`、`std::sort`、开头的栈。
   - **类型安全**：`Stack<int>` 里放不进字符串，编译时就报错；没有 `void*` 的来回转换。
2. **常量提到编译期：非类型模板参数**
   - **例子**：`std::array<int, 8>` 的长度是类型的一部分，编译时就知道，数组能直接放在栈上。
   - **编译器能按这个数优化**：循环次数固定，可以展开；`N` 是 2 的幂时，无符号数的 `i % N` 直接编成 `i & (N - 1)`。`N` 要是运行时传进来的变量，就得真做一次除法。编译期常量的细节见 [const 和 constexpr](/zh/ref/const-constexpr/)。
3. **做法提到编译期：把“怎么做”也做成模板参数**
   - **例子**：`std::sort` 的比较器、`std::unique_ptr<T, Deleter>` 的删除器、`std::map<K, V, Compare>` 的比较规则。
   - **调用能内联**：比较器的类型编译时就知道，每次比较都是直接调用；换成函数指针，每次比较都要先读出地址再跳过去。
   - **再往前一步就是静态多态**：基类模板拿子类当参数（CRTP），见 [CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/)。

> **被问“类模板能解决什么问题”：答三点**
> 1. **类型不同、逻辑一样**：写一份，编译器按用到的类型各生成一份，类型安全，没有 `void*` 的转换。
> 2. **常量提到编译期**：长度、容量这类非类型参数编译时就定了，循环能展开，取模能换成位运算。
> 3. **做法提到编译期**：比较器、删除器做成模板参数，调用能内联；再往前就是 CRTP 的静态多态。

## 2. 实例化：用到一种类型，才生成一份 {#instantiation}

```cpp
template <typename T>
class Stack {
public:
    void push(const T& x) { data_.push_back(x); }
    T pop() { T x = data_.back(); data_.pop_back(); return x; }
    bool empty() const { return data_.empty(); }
private:
    std::vector<T> data_;
};

Stack<int> a;            // 生成 Stack<int>
Stack<std::string> b;    // 再生成一份 Stack<std::string>
```

1. **模板本身不是代码，是生成代码的规则**
   - **写下 `Stack<int>` 时**：编译器把 `T` 换成 `int`，生成一个真正的类，这一步叫实例化。
   - **`Stack<int>` 和 `Stack<std::string>` 是两个不相关的类型**：各有一份机器码，不能互相赋值。
   - **成员函数用到才生成**：从没调用过的 `pop`，就不会为这个类型生成。所以 `T` 只要支持实际用到的那些操作就行。
2. **实参能推导出来的，就不用写**
   - **函数模板**：`std::max(3, 5)` 从参数推出 `T = int`；`std::max(3, 5.0)` 两个参数推出的类型不一样，推导失败，要写成 `std::max<double>(3, 5.0)`。
   - **类模板（C++17 起）**：`std::vector v{1, 2, 3};` 从构造函数推出 `std::vector<int>`，叫 CTAD。
3. **模板的定义要放在头文件里**
   - **原因**：实例化发生在用到它的那个 `.cpp` 里，编译器要看到完整的定义，才能照着生成。
   - **放进 `.cpp` 会怎样**：别的 `.cpp` 只看得到声明，生成不了，链接时报 `undefined reference`（[C++ 与 Linux 总图 3](/zh/ref/cpp-linux/#build)）。
   - **多个 `.cpp` 都生成同一份 `Stack<int>` 不会冲突**：模板和 `inline` 函数一样，允许每个翻译单元各有一份，链接器只留一份。
4. **代价有三笔**
   - **代码变多**：每种实参一份机器码，类型多了，可执行文件变大，指令缓存也更挤。
   - **编译变慢**：每个用到它的 `.cpp` 都要实例化一遍；`extern template class Stack<int>;` 能让这个 `.cpp` 不再生成，用别处生成好的那份。
   - **报错难读**：传了不支持的类型，错误出在模板里面好几层，一屏一屏的。第 4 节的约束就是解决这个的。

## 3. 特化和偏特化：给某些类型换一种实现 {#specialization}

1. **全特化：某一个具体类型单独写**

   ```cpp
   template <typename T>
   struct TypeName { static const char* get() { return "unknown"; } };

   template <>
   struct TypeName<int> { static const char* get() { return "int"; } };
   ```

   - **`TypeName<int>` 用特化的版本**：其他类型都用通用版。
   - **标准库里的例子**：`std::hash<std::string>` 是对 `std::hash` 的特化；`std::vector<bool>` 也是特化，按位存储，所以 `v[0]` 拿到的不是 `bool&`。
2. **偏特化：一类类型单独写，只有类模板能用**

   ```cpp
   template <typename T>
   struct IsPointer { static constexpr bool value = false; };

   template <typename T>
   struct IsPointer<T*> { static constexpr bool value = true; };   // 所有指针类型

   static_assert(IsPointer<int*>::value && !IsPointer<int>::value);
   ```

   - **为什么叫“偏”**：`IsPointer<T*>` 里还留着一个参数 `T`，所以它匹配的是“所有指针”这一类，不是某一个类型。
   - **这类模板叫 type traits**：输入一个类型，在编译期算出一个值或另一个类型。标准库的 `std::is_pointer`、`std::remove_reference` 都是这样写的。
   - **函数模板不能偏特化**：要给一类类型换实现，写一个重载。

## 4. 约束模板参数：从 SFINAE 到 concepts {#constraints}

模板对什么类型都会试着实例化，传错了类型，报错出现在模板深处，看不出是哪里不满足。所以要把“这个模板只接受哪些类型”写到签名上。

1. **SFINAE：替换失败不是错误**
   - **规则**：编译器把实参代进模板签名时出了错，不报错，只是把这个候选从重载里去掉，再试别的。
   - **`std::enable_if` 就是靠这条规则**：条件不满足时它没有 `type` 成员，签名替换失败，这个重载就不存在了。

   ```cpp
   template <typename T, typename = std::enable_if_t<std::is_integral_v<T>>>
   T half(T x) { return x / 2; }      // 只接受整数；half(1.5) 找不到能用的重载
   ```

   - **缺点**：写法绕；报错只说“没有匹配的函数”，看不出是哪个条件不满足。
2. **concepts（C++20）：约束直接写在签名上**

   ```cpp
   template <std::integral T>
   T half(T x) { return x / 2; }

   template <typename T>
   concept Pushable = requires(T c, typename T::value_type v) { c.push_back(v); };
   ```

   - **报错会说哪个约束没满足**：`half(1.5)` 的报错里直接写着 `constraints not satisfied`，指向 `integral<T>`。
   - **自己定义概念用 `requires`**：上面的 `Pushable` 要求类型有 `value_type`，并且能 `push_back`。
3. **`if constexpr`：同一个函数里按类型走不同的代码**

   ```cpp
   template <typename T>
   std::string to_text(const T& x) {
       if constexpr (std::is_arithmetic_v<T>) return std::to_string(x);
       else                                    return std::string(x);
   }
   ```

   - **没选中的分支不实例化**：`T` 是 `const char*` 时，`std::to_string(x)` 那一行不会被编译，所以不报错。
   - **换成普通 `if` 就不行**：两个分支都要能编译通过，`std::to_string(const char*)` 编不过。

> **约束怎么选**
> - **能用 C++20**：用 concepts，约束写在签名上，报错最清楚。
> - **只能用 C++17，几个重载要互斥**：用 `enable_if`。
> - **同一个函数里按类型走不同代码**：用 `if constexpr`。
> - **只想在类型不对时给一句清楚的报错**：函数体里写 `static_assert(条件, "说明")`。

## 5. 变参模板和折叠表达式：参数个数也不固定 {#variadic}

1. **`typename... Ts` 接任意多个类型**

   ```cpp
   template <typename... Ts>
   auto sum(Ts... xs) { return (xs + ...); }   // 折叠表达式

   sum(1, 2, 3);     // 6
   sum(1.5, 2);      // 3.5
   ```

   - **`Ts...` 是一包类型，`xs...` 是一包参数**：`sizeof...(Ts)` 是包里有几个。
   - **折叠表达式（C++17）把一包展开成一串运算**：`(xs + ...)` 展开成 `x1 + (x2 + x3)`；`(f(xs), ...)` 用逗号连起来，按顺序对每个参数调一次 `f`。
2. **`std::tuple` 加 `std::apply`：对一组不同类型的对象各做一次**

   ```cpp
   std::tuple<int, double, std::string> t{1, 2.5, "x"};
   std::apply([](const auto&... e) { ((std::cout << e << ' '), ...); }, t);   // 输出 1 2.5 x
   ```

   - **`std::apply` 把 tuple 拆成一包参数**：交给 lambda，lambda 里再用折叠对每个元素做一次。
   - **每个元素的类型编译时都知道**：每次调用都是直接调用，能内联。[CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/) 1.6.3 用的就是这种写法。
3. **完美转发也靠变参模板**
   - **例子**：`std::make_unique`、`emplace_back` 都是 `template <typename... Args>` 加 `std::forward<Args>(args)...`，把一包参数原样转给构造函数，见 [移动语义](/zh/ref/move-semantics/)。

## 6. 模板和虚函数：两种多态 {#vs-virtual}

1. **模板在编译时选**
   - **调用能内联**：编译器知道调的是谁。
   - **代价**：每种类型一份代码；`Stack<int>` 和 `Stack<double>` 不相关，放不进同一个容器。
2. **虚函数在运行时选**
   - **一份代码**：能放进 `std::vector<Base*>`，运行时还能加新的子类。
   - **代价**：每次调用先查 vtable，编译器不知道调的是谁，没法内联。
3. **细节在别处**：虚函数怎么调见 [虚函数](/zh/ref/virtual-functions/)；两种多态怎么选见 [CRTP 与静态多态](/zh/posts/crtp-static-polymorphism/) 第 4 节。
