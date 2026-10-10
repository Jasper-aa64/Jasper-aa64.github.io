---
title: "C++ Syntax: What It Compiles To"
description: "What common C++ features compile to, what they cost, and the alternatives. So far: virtual functions; composition and mixins."
date: 2026-10-10
lastmod: 2026-10-10
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

**The problem**: an iterator needs several stacked features (walk a matrix → keep only odd values → double the value), in any combination. The run-time decorator pattern makes each layer an object holding an `Iterator*` to the next, with a virtual interface: every layer adds a heap allocation and a virtual call (the costs in [entry 1](#virtual-cost)).

**A mixin**: each layer is a template that takes the next layer as its template parameter and inherits from it.

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
