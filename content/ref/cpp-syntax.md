---
title: "C++ Syntax: What It Compiles To"
description: "What common C++ features compile to, what they cost, and the alternatives. First entry: virtual functions."
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
