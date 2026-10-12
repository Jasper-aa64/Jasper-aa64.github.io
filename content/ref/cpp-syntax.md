---
title: "C++ Syntax: What It Compiles To"
description: "What common C++ features compile to, what they cost, and the alternatives. So far: virtual functions; composition and mixins; static vs. dynamic polymorphism; const / constexpr / consteval / constinit."
date: 2026-10-10
lastmod: 2026-10-12
slug: "cpp-syntax"
weight: 20
toc: true
---

This page is a reference to keep open, not a post. Each entry follows the same order: what it is → what it compiles to → where the cost is → when it can be avoided and what to use instead. All assembly is real GCC 13.3 `-O2` x86-64 output. New language features get added to this page as they come up.

## 1. Virtual Functions: Pick the Function by the Object's Type at Run Time {#virtual}

### 1.1 What It Is {#virtual-what}

A function declared `virtual` in a base class, when called through a base-class pointer or reference, runs the version for the object's **actual type**. The call site is always the same `o->handle()`; which function runs is known only at run time, from what `o` points to.

```cpp
struct Order {
    virtual ~Order() = default;
    virtual int handle() const = 0;   // pure virtual: every subclass implements it
    int qty = 1;
};
struct LimitOrder : Order {
    int handle() const override { return qty * 2; }
};
struct MarketOrder final : Order {    // final: no further subclasses
    int handle() const override { return qty * 3; }
};

int run(const Order* o) { return o->handle(); }   // may be a LimitOrder or a MarketOrder
```

Typical use: a container holds objects of different subclasses (`std::vector<std::unique_ptr<Order>>`), and a loop calls `handle()` on each.

### 1.2 What It Compiles To: vptr and vtable {#virtual-vtable}

`run` compiles to just two instructions:

```asm
run(Order const*):
        movq    (%rdi), %rax      # 1. load the object's first 8 bytes: the vptr, pointing at its class's vtable
        jmp     *16(%rax)         # 2. load the function address from the table's 3rd slot and jump (indirect jump)
```

Two things make it work:

- **vtable** (virtual function table): one per **class** with virtual functions, in read-only data, listing the address of each virtual function in declaration order. In `LimitOrder`'s table the `handle` slot holds `LimitOrder::handle`; in `MarketOrder`'s, `MarketOrder::handle`. (The first two slots are destructors, so `handle` sits at offset 16.)
- **vptr** (vtable pointer): a hidden 8-byte pointer at the start of every **object**, set at construction to its class's vtable. That's why `sizeof(LimitOrder)` is 16: 8 bytes of vptr, 4 of `qty`, 4 of padding.

So one virtual call = load the vptr → load the table slot → jump to the loaded address.

### 1.3 Where the Cost Is {#virtual-cost}

- **The indirect jump has to be predicted**: the target is loaded from memory, so the front end relies on the **indirect target predictor** ([#7 Section 1.3](/posts/branch-prediction-branch-optimization/)). When the object types at one call site follow a pattern (all the same, or a short repeating cycle), it almost never misses; when they're randomly mixed, it misses often, about 15–20 cycles each time.
- **It blocks inlining**: the compiler doesn't know which function will run, so it can't inline it or optimize across the call (constant propagation, merging computations, vectorization). The smaller the function, the worse this is: `handle()` itself is a single multiply, much cheaper than the call.
- **Two extra memory reads**: the vptr and the vtable slot. In a hot loop they're usually in L1, about 1 ns; with objects scattered on the heap and untouched for a while, the first vptr read may miss in cache.
- **8 more bytes per object**: a small object (say a 16-byte order) grows noticeably, so fewer fit in a cache line.

### 1.4 When the Compiler Removes the Virtual Call (Devirtualization) {#virtual-devirt}

When the compiler can prove the actual type, it calls the function directly, or inlines it. Three common cases; the first two are measured:

```cpp
int run_market(const MarketOrder* o) { return o->handle(); }   // MarketOrder is final
int run_local() { LimitOrder l; return run(&l); }              // the object is right there
```

- **`final`**: `MarketOrder` is `final`, so there can't be a subclass and `o->handle()` can only be `MarketOrder::handle`. `run_market` compiles to `movl 8(%rdi), %eax` + `leal (%rax,%rax,2), %eax`: the multiply by 3 is inlined, no jump.
- **Local objects**: in `run_local` the type is written right there; once `run` is inlined, the whole function compiles to `movl $2, %eax`.
- **A single implementation**: with `-flto` (link-time optimization) the compiler sees the whole program, and a virtual function with only one implementation can be called directly too (not measured here).

### 1.5 Alternatives to Virtual Functions {#virtual-alternatives}

**CRTP** (curiously recurring template pattern): the subclass passes itself as a template parameter to the base, and the base `static_cast`s back to the subclass to call it. The type is fixed at compile time and the call inlines.

```cpp
template <typename Derived>
struct OrderBase {
    int handle() const { return static_cast<const Derived*>(this)->handle_impl(); }
};
struct Limit2 : OrderBase<Limit2> {
    int qty = 1;
    int handle_impl() const { return qty * 2; }
};
template <typename T> int run_crtp(const OrderBase<T>& o) { return o.handle(); }
```

`run_crtp(l2)` compiles to `movl (%rdi), %eax` + `addl %eax, %eax`, with no vptr; `sizeof(Limit2)` is 4. The cost: different subclasses are different types and can't share one container. It fits code where each place handles one type, chosen at compile time.

**`std::variant` + `std::visit`**: when the set of types is fixed and known up front, a `variant` holds one of them and dispatches on the stored type index.

```cpp
struct L { int qty; int handle() const { return qty * 2; } };
struct M { int qty; int handle() const { return qty * 3; } };
struct S { int qty; int handle() const { return qty * 5; } };
using AnyOrder = std::variant<L, M, S>;

int run_variant(const AnyOrder& o) {
    return std::visit([](const auto& x) { return x.handle(); }, o);
}
```

This compiles to a load of the type index (1 byte) plus two compare-and-jumps, with all three `handle()`s inlined into the branches and no indirect call. Objects are stored by value, `sizeof(AnyOrder)` is 8 (4 bytes of `qty` + the index, padded), and a `std::vector<AnyOrder>` is one contiguous run with no per-object `new`. The cost: adding a type means changing the `variant`'s definition; and the branches remain, so randomly mixed types still mispredict (now as conditional jumps).

**Batch by type**: don't change the syntax, change how the data is laid out. Split orders by type into a few arrays and loop over each. Within one loop the type never changes, so the virtual call (or the branch) has the same target every time and almost never misses; with the type known, you can also use the concrete type and let the compiler inline.

**Structure assembled at compile time**: for things like a strategy tree, where how the nodes connect is fixed before deployment, make the nodes types and assemble the whole tree at compile time; see the compile-time decision tree in [#7 Section 3.6](/posts/branch-prediction-branch-optimization/).

### 1.6 How to Choose {#virtual-choose}

- **Types known only at run time, open set (plugins, read from config)**: virtual functions. On hot paths, keep the types at one call site patterned, or batch by type.
- **Fixed set of types, objects stored together**: `std::variant` + `std::visit`.
- **Type known at compile time**: templates or CRTP; mark classes `final` where you can.
- **Not on a hot path**: virtual functions read best; don't agonize.

## 2. Composition and Inheritance: Reuse an Implementation as a Member, Stack Features with Mixins {#composition}

### 2.1 Composition: To Reuse a Class's Implementation, Make It a Member {#composition-member}

```cpp
class InheritanceOrderBook : public std::vector<Order> {   // inheritance: "is" a vector
};

class CompositionOrderBook {                                // composition: "has" a vector
    std::vector<Order> orders_;
public:
    auto size() const noexcept { return orders_.size(); }  // expose only what's needed
};
```

**They compile the same**: member access and `size()` both read the field inside `orders_` directly, and `size()` inlines. The difference is all design; publicly inheriting `std::vector` has three problems:

- **The whole interface is exposed**: anyone can call `push_back` or `erase`, so invariants like "the book is sorted by price" can't be protected. Composition exposes only the functions you choose.
- **The destructor isn't virtual**: `std::vector<Order>* p = new InheritanceOrderBook;` followed by `delete p` is undefined behavior. Standard containers aren't designed to be base classes.
- **Tied to the implementation**: replacing `std::vector` with another container means changing every caller with inheritance, but only the class's internals with composition.

The rule: if you want "its implementation," make it a member (has-a); public inheritance only when you really mean "usable as one" (is-a) and the base is designed for it (it has a virtual destructor).

### 2.2 Mixins: Stack Features at Compile Time with a Template Inheritance Chain {#mixin}

Two terms first, then the code.

**Decorator pattern**: a common design pattern for **adding features to a class layer by layer without changing it**. You write a wrapper that looks the same as the wrapped object (implements the same interface) and holds that object. A call to the wrapper is forwarded to the inner object, with the wrapper's own bit of behavior added before or after. A wrapper can itself be wrapped, so features stack, and how many layers and in what order is decided at run time when the objects are assembled.

**Mixin**: literally "something mixed in": **a small class that provides one feature and can't be used on its own**; it only makes sense mixed into another class. In C++ it's usually written `template <class Base> class X : public Base`: `X` doesn't know what it will sit on top of; the base class is supplied as a template parameter at compile time.

**How they relate**: same goal, stacking features layer by layer; the difference is how the layers are connected. A decorator connects them with pointers at run time (dynamic polymorphism); a mixin connects them with inheritance at compile time (static polymorphism). That's why a mixin is the static-polymorphism version of the decorator pattern.

**Example**: an iterator needs several stacked features (walk a matrix → keep only odd values → double the value), in any combination. The decorator version first: each layer is an object holding a pointer to the next:

```cpp
struct Iterator {                      // common interface: every layer looks like this
    virtual ~Iterator() = default;
    virtual bool valid() const = 0;
    virtual Cell cell() const = 0;
    virtual void next() = 0;
};

struct DoubleValueDeco : Iterator {    // one decorator layer: wraps the next, changes only cell()
    std::unique_ptr<Iterator> inner;
    explicit DoubleValueDeco(std::unique_ptr<Iterator> i) : inner(std::move(i)) {}
    bool valid() const override { return inner->valid(); }
    Cell cell() const override { Cell x = inner->cell(); x.value *= 2; return x; }
    void next() override { inner->next(); }
};
```

Every extra layer is one more heap allocation (`unique_ptr`), and every call costs one more virtual call on the way down (the costs in [entry 1](#virtual-cost)).

**The mixin version**: each layer is a template that takes the next layer as its template parameter and inherits from it.

```cpp
template <class Base>
class OddOnly : public Base {          // keep only odd values
public:
    template <class... Args>
    explicit OddOnly(Args&&... args) : Base(std::forward<Args>(args)...) {
        while (Base::valid() && (Base::cell().value % 2 == 0)) Base::next();
    }
    void next() {
        do {
            Base::next();
        } while (Base::valid() && (Base::cell().value % 2 == 0));
    }
};

template <class Base>
class DoubleValue : public Base {      // double the value
public:
    template <class... Args>
    explicit DoubleValue(Args&&... args) : Base(std::forward<Args>(args)...) {}
    Cell cell() const {
        Cell x = Base::cell();
        x.value *= 2;
        return x;
    }
};

using Iter = DoubleValue<OddOnly<MatrixWalk>>;   // the template-argument order is the stacking order
```

(`MatrixWalk` is the bottom layer: it walks a 2-D `vector` row by row and provides `valid()`, `cell()` and `next()`.) **What it compiles to**: `Iter` is **one object**, with no per-layer heap objects, no pointers and no virtual functions; `Base::next()` and `Base::cell()` are direct calls that inline all the way down. It's the **static polymorphism** version of the decorator pattern, the same trade as [replacing virtual functions with CRTP](#virtual-alternatives).

<a href="/images/ref/mixin-vs-decorator.en.svg" target="_blank" rel="noopener"><img src="/images/ref/mixin-vs-decorator.en.svg" alt="Top: the decorator is 3 heap objects, each with a vptr, linked by inner pointers; one call to cell() loads a pointer, loads the vtable and makes an indirect call at every layer, and the compiler cannot inline. Bottom: the mixin is one 32-byte object; DoubleValue and OddOnly are base classes wrapped around MatrixWalk with no members, no vptr and no pointers, and every call inlines; the conditional jump of the odd filter remains." loading="lazy" decoding="async"></a>

### 2.3 Order Is Meaning {#mixin-order}

For the same matrix `{{1, 2, 3}, {}, {4, 5, 6}}`:

| Type | Output | Why |
|---|---|---|
| `DoubleValue<OddOnly<MatrixWalk>>` | `2 6 10` | keep the odd originals (1, 3, 5), then double |
| `OddOnly<DoubleValue<MatrixWalk>>` | empty | doubling makes everything even, so the odd filter keeps nothing |

A decorator can be stacked at run time from config; a mixin's order is written into the type and fixed at compile time.

### 2.4 Costs {#mixin-cost}

- **Combinatorial types**: every combination is a new type with its own instantiated code, growing compile time and binary size.
- **Hard-to-read errors**: a few levels of nested templates make long error messages.
- **Constructors must forward**: each layer passes its arguments to `Base` (the variadic constructor above, or `using Base::Base;`).
- **Hiding, not overriding**: `OddOnly::next()` only hides `Base::next()`; it isn't a virtual override. Call `next()` through a `MatrixWalk&` and you get `MatrixWalk::next()`. Mixins only work when you keep using the full type.

## 3. Static vs. Dynamic Polymorphism: When the Decision Is Made {#polymorphism}

In one line: **the difference is when "which function to call" gets decided.** Static polymorphism (templates, CRTP, mixins, compile-time decision trees) decides at compile time; dynamic polymorphism (virtual functions) decides at run time from the object's type. Speed, flexibility, and engineering cost all follow from that.

### 3.1 Where the Speed Comes From: Inlining, Not Just One Jump Saved {#poly-speed}

The run-time cost of dynamic polymorphism is in [1.3](#virtual-cost): one indirect jump to predict, two extra memory reads, 8 bytes per object, and no inlining. The most expensive item is usually **no inlining**.

- The indirect jump itself: when the types at one call site follow a pattern it is almost never mispredicted and costs only a few cycles; with randomly mixed types each mispredict costs about 15–20 cycles.
- Inlining: once the body is expanded into the caller, the compiler can propagate constants, merge computation, and vectorize. The smaller the body, the bigger this gap.

So "static is faster than dynamic" needs two conditions: the call is on a hot path, and the body is small. If the body itself runs for hundreds of ns, the few ns saved don't show. Also, static polymorphism doesn't mean "no branches": conditions that depend on data still compile to conditional jumps in a compile-time decision tree (the tree in [#7 section 3.6](/posts/branch-prediction-branch-optimization/) is 3 conditional jumps). What disappears is the indirect jump that picks the function.

### 3.2 What Static Polymorphism Costs {#poly-cost}

- **Code bloat**: a template is instantiated once per set of arguments. A bigger binary usually doesn't matter; what matters is whether the copies active on the hot path at the same time fit in the instruction cache (L1I, about 32 KiB). One copy for each of 10 symbols, with only one or two running at a time, generally doesn't slow anything down.
- **Compile time**: instantiation and inlining happen at compile time, so template-heavy projects build noticeably slower.
- **Hard-to-read errors**: a few levels of nested templates can turn one wrong type into a very long error. C++20 concepts move some of these up to a single "constraint not satisfied" line.
- **The set of types is fixed at compile time**: covered on its own in the next section.

### 3.3 What "Run-Time Flexibility" Actually Means {#poly-flexibility}

Separate two things first: **picking one of several already-compiled types at run time is something static polymorphism can do; adding a new type the compiler never saw is something it can't.**

**What it can do: dispatch once, outside the loop.** Whether the config file says `"fast"` or `"safe"` is only known at run time; both algorithm types are written ahead of time, and one `if` picks an already-instantiated copy:

```cpp
struct Fast { int apply(int x) const { return x * 2; } };
struct Safe { int apply(int x) const { return x * 4; } };

template <typename Algo>
long long run_loop(const int* xs, int n) {
    Algo a;
    long long s = 0;
    for (int i = 0; i < n; ++i) s += a.apply(xs[i]);   // apply is known at compile time, inlined
    return s;
}

long long run(const std::string& cfg, const int* xs, int n) {
    if (cfg == "fast") return run_loop<Fast>(xs, n);     // the only check, done once
    if (cfg == "safe") return run_loop<Safe>(xs, n);
    return 0;
}
```

In the compiled `run_loop<Fast>`, `apply` inside the loop is a single `addl %eax, %eax`, with no `call`. The check runs once before the loop, the same idea as "hoist the if out of the loop" in [#7 section 3.5](/posts/branch-prediction-branch-optimization/). This is how it's almost always used on hot paths: read the config at startup, pick the types, and the loops after that have no dispatch.

**Several dimensions at once: easy to write, costly in instantiations.** 3 algorithms × 3 memory policies doesn't need 9 hand-written branches: `std::visit` takes several `variant`s and generates every combination:

```cpp
using AlgoV = std::variant<A1, A2, A3>;
using MemV  = std::variant<B1, B2, B3>;

void dispatch(const AlgoV& a, const MemV& m) {
    std::visit([](auto x, auto y) { run_combo<decltype(x), decltype(y)>(); }, a, m);
}
```

Here `run_combo` is instantiated 3 × 3 = 9 times. Five dimensions with 3 options each is 3<sup>5</sup> = 243 copies: no hand-written code, but compile time and binary size grow multiplicatively. The usual approach is to make types out of only the one or two dimensions that really affect hot-path performance, and leave things like log level or validation switches, which aren't in the hot loop, as ordinary run-time variables.

**What it can't do: an open set of types.**

- **Plugins**: after the program starts, `dlopen` (`LoadLibrary` on Windows) loads a `.so` / `.dll` whose classes the main program never saw at compile time. No template can be instantiated for them; the only option is an agreed virtual interface that the main program calls through the vtable. The plugin can still use templates internally; only the boundary between plugin and main program has to be dynamic.
- **Containers of unknown types**: `std::vector<std::unique_ptr<Strategy>>` holds any subclass of `Strategy`, including ones written later. `std::variant<L, M, S>` also puts several types in one `vector`, stored by value and contiguous, but only those types; adding one means changing the definition and recompiling.
- **Changing structure at run time**: for example, pushing a new risk tree to the system mid-session, where how the nodes connect isn't known in advance. That can only be assembled at run time from objects and pointers (the run-time virtual tree in [#7 section 3.6](/posts/branch-prediction-branch-optimization/)).

### 3.4 How to Choose {#poly-choose}

Two questions:

1. **Can the set of types be fixed at compile time?** If not (plugins, structure pushed at run time), use virtual functions. If so, go on.
2. **Is this call on a hot path?** If not (startup, config loading, management logic that runs a few times a second), use virtual functions; they're easier to read and change. If so, use templates, CRTP, or `std::variant` (when the set is fixed and the objects should be stored together), and make the run-time choice once, outside the loop.

The two are often mixed: an outer virtual call or `variant` picks once, and the chosen code is static all the way down.

## 4. `const` / `constexpr` / `consteval` / `constinit`: Which One Guarantees Compile Time {#compile-time}

Four look-alike keywords that answer different questions:

| Keyword | Applies to | Guaranteed to be computed at compile time? | Can it change later? |
|---|---|---|---|
| `const` | variables, parameters, member functions | **no** | no |
| `constexpr` | variables | yes | no |
| `constexpr` | functions | no: only where a constant is required | — |
| `consteval` | functions | yes: every call is evaluated at compile time | — |
| `constinit` | variables with static storage duration | the initialization is | **yes** (not `const`) |

### 4.1 `const`: Read-Only, Not a Compile-Time Constant {#const}

`const` only says the value can't change after initialization; the initial value can come from run time (`const int scale = get_config("scale");`). For performance, separate two cases:

- **A `const` object itself** (`const int max_len = 100;`): modifying it is undefined behavior, so the compiler can use 100 as an immediate. An integral `const` initialized with a constant can even be a template argument.
- **`const T*` / `const T&`**: only *you* can't modify through it; another pointer still can, so the compiler has to assume it might:

```cpp
int f(const int* p, int* q) {
    int a = *p;
    *q = 1;          // q may point to the same int as p
    return a + *p;   // so *p has to be loaded again
}
```

It compiles to `movl (%rdi), %eax` → `movl $1, (%rsi)` → `addl (%rdi), %eax`: `*p` is loaded twice. The benefit of a `const &` parameter is no copy and no accidental writes, not extra optimization.

### 4.2 `constexpr`: Variables Are Computed at Compile Time, Functions *Can* Be {#constexpr}

- **A `constexpr` variable**: its initial value must be computed at compile time, or it's a compile error.
- **A `constexpr` function**: is *allowed* to run at compile time. Where a constant is required (a `constexpr` variable, a template argument, an array size, `static_assert`), it must; with a run-time argument it's an ordinary call.

```cpp
constexpr int twice(int x) { return x + x; }
constexpr int four = twice(2);           // computed at compile time: 4
int twice_rt(int n) { return twice(n); } // computed at run time
```

`twice_rt` compiles to a single `leal (%rdi,%rdi), %eax`, like any ordinary function. `constexpr` is not an optimization hint.

### 4.3 `consteval`: Every Call Must Happen at Compile Time {#consteval}

A `consteval` function (an immediate function) must be fully evaluated at compile time on every call; a non-constant argument is a compile error. Use it where computing at run time would be a bug, such as validating configuration or generating a hash at compile time.

```cpp
consteval int get_dim() { return 4; }
Vector<get_dim()> v;     // usable as a template argument
```

The catch: **inside a `consteval` function its parameters are not constant expressions**, so you can't write `static_assert(i == 1)` or use `i` as a template argument. For that, make it a template parameter, `template <int I>`.

**`if consteval`** (C++23): inside one `constexpr` function, use an implementation that can run at compile time when evaluated at compile time, and a faster one at run time:

```cpp
constexpr std::size_t my_strlen(const char* s) {
    if consteval {
        std::size_t n = 0;          // compile time: count byte by byte
        while (s[n]) ++n;
        return n;
    } else {
        return std::strlen(s);      // run time: the library function (not constexpr)
    }
}
```

### 4.4 `constinit`: Static Variables Initialized at Compile Time, Still Mutable {#constinit}

`constinit` does one thing: **a global or `static` variable must be initialized at compile time**, or it's a compile error. It is **not** `const`; the variable can change afterwards.

```cpp
constexpr int somefunc() { return 27; }    // must be constexpr, or the next line fails to compile
constinit int g_counter = somefunc();      // goes in .data, with 27 stored in the executable
// ...
++g_counter;                               // allowed
```

It guards against the **static initialization order fiasco**: globals initialized at run time are computed by startup code before `main`, the order across source files is unspecified, and a global that reads another one not yet initialized is a bug. `constinit` guarantees that step doesn't exist.

### 4.5 Non-Type Template Parameters: Make a Constant Part of the Type {#nttp}

A template parameter can be a value (an NTTP, non-type template parameter):

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

`Vector<4>` and `Vector<8>` are two types, each compiled separately; the trip count is a constant, so the compiler can fully unroll or vectorize. The cost is the code bloat in [entry 3](#poly-cost). The template argument must be a compile-time constant: `const int d = 4;` works, `int n = 4; const int d = n;` doesn't.

### 4.6 Generating a Lookup Table at Compile Time {#lut}

```cpp
constexpr std::array<uint64_t, 20> make_pow10() {
    std::array<uint64_t, 20> t{};
    uint64_t v = 1;
    for (auto& x : t) { x = v; v *= 10; }
    return t;
}
constexpr auto kPow10 = make_pow10();     // filled at compile time, placed in .rodata
uint64_t pow10(unsigned e) { return kPow10[e]; }
```

`pow10` compiles to `leaq kPow10(%rip), %rax` + `movq (%rax,%rdi,8), %rax`: one memory load. That load is the cost of a lookup: about 1 ns from L1D, but a big table accessed randomly falls to L2, L3 or even DRAM ([reference: latency](/ref/cpu-memory/#latency)), and then computing directly may be faster.

### 4.7 How to Choose {#compile-time-choose}

- The value must exist at compile time and failing to compute it should be an error → a `constexpr` variable or a `consteval` function.
- One implementation used both at compile time and at run time → a `constexpr` function, with `if consteval` if needed.
- A global or `static` variable that must be mutable but shouldn't be initialized at run time → `constinit`.
- You just don't want it modified → `const`.
