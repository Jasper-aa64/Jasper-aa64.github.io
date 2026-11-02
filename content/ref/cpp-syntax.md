---
title: "Static Polymorphism: What It Compiles To"
description: "Ways to fix \"which function\" at compile time, what they compile to and what they cost: CRTP, std::variant, batching by type, mixins, and how to choose between static and dynamic polymorphism. Virtual functions themselves are in the Virtual Functions post in the C++ & Linux section."
date: 2026-10-10
lastmod: 2026-10-12
slug: "cpp-syntax"
weight: 20
toc: true
---

This page is a reference to keep open, not a post. It covers static polymorphism: moving "which function to call" from run time to compile time. Virtual functions themselves (vptr, vtable, the cost of a virtual call) are C++ basics and live in the [Virtual Functions](/ref/virtual-functions/) post; `const` / `constexpr` and `shared_ptr` moved to the C++ & Linux section as well ([const and constexpr](/ref/const-constexpr/), [shared_ptr](/ref/shared-ptr/)). All assembly is real GCC 13.3 `-O2` x86-64 output.

## 1. Alternatives to Virtual Functions: CRTP, variant, Batching by Type {#virtual-alternatives}


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

The full treatment (uses, four pitfalls, C++23 deducing this) is in [#8 CRTP and Static Polymorphism](/posts/crtp-static-polymorphism/).

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

## 2. Mixins: Stack Features at Compile Time with a Template Inheritance Chain {#mixin}


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

Every extra layer is one more heap allocation (`unique_ptr`), and every call costs one more virtual call on the way down (the costs in [Virtual Functions](/ref/virtual-functions/#virtual-cost)).

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

### 2.1 Order Is Meaning {#mixin-order}

For the same matrix `{{1, 2, 3}, {}, {4, 5, 6}}`:

| Type | Output | Why |
|---|---|---|
| `DoubleValue<OddOnly<MatrixWalk>>` | `2 6 10` | keep the odd originals (1, 3, 5), then double |
| `OddOnly<DoubleValue<MatrixWalk>>` | empty | doubling makes everything even, so the odd filter keeps nothing |

A decorator can be stacked at run time from config; a mixin's order is written into the type and fixed at compile time.

### 2.2 Costs {#mixin-cost}

- **Combinatorial types**: every combination is a new type with its own instantiated code, growing compile time and binary size.
- **Hard-to-read errors**: a few levels of nested templates make long error messages.
- **Constructors must forward**: each layer passes its arguments to `Base` (the variadic constructor above, or `using Base::Base;`).
- **Hiding, not overriding**: `OddOnly::next()` only hides `Base::next()`; it isn't a virtual override. Call `next()` through a `MatrixWalk&` and you get `MatrixWalk::next()`. Mixins only work when you keep using the full type.

## 3. Static vs. Dynamic Polymorphism: When the Decision Is Made {#polymorphism}

In one line: **the difference is when "which function to call" gets decided.** Static polymorphism (templates, CRTP, mixins, compile-time decision trees) decides at compile time; dynamic polymorphism (virtual functions) decides at run time from the object's type. Speed, flexibility, and engineering cost all follow from that.

### 3.1 Where the Speed Comes From: Inlining, Not Just One Jump Saved {#poly-speed}

The run-time cost of dynamic polymorphism is in [Virtual Functions 1.3](/ref/virtual-functions/#virtual-cost): one indirect jump to predict, two extra memory reads, 8 bytes per object, and no inlining. The most expensive item is usually **no inlining**. One more cost appears only on a cold start: after the market has been quiet for a while, other code has pushed the hot path out of the cache, and when the next tick arrives the vtable's line may be missing too, adding one serial miss behind the vptr read. The fix is to keep the hot path hot (run it on dummy data periodically even when idle), or use CRTP or `final` so there is no vtable to read.

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

