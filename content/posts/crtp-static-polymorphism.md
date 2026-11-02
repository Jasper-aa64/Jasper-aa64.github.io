---
title: "Trading System Notes #8: CRTP and Static Polymorphism"
date: 2026-10-12
lastmod: 2026-11-02
slug: "crtp-static-polymorphism"
description: "CRTP (the curiously recurring template pattern): the subclass passes itself to its base as a template argument, so the base knows the subclass at compile time. Why it is legal, how it compiles compared with a virtual call (real GCC assembly, including speculative devirtualization), three uses, four pitfalls (silent UB from a wrong base, infinite recursion on same names, incomplete types, no common base), how to choose against virtual functions, and C++23 deducing this. The second half covers the techniques beyond CRTP (variant, batching by type, mixins) and how to choose between static and dynamic polymorphism."
summary: "The base class writes the flow and the subclass fills in the details: virtual functions pick the subclass at run time, CRTP at compile time. What you save is more than one indirect jump: the call inlines completely and the object has no vptr. The price is that Base<A> and Base<B> are unrelated types and can't share a container."
chapter: 1
categories: [Systems]
tags: [cpp, crtp, static-polymorphism, virtual-functions, templates, hft, low-latency]
toc: true
homepage: false
aliases: ["/ref/cpp-syntax/"]
---

A market-data gateway connects to several exchanges. The processing flow is mostly the same for each: receive the packet, check the sequence number, update the order book. Only "parse one message" differs. The natural design is a base class that owns the flow and subclasses that fill in parsing, with a virtual function: the base calls `virtual on_tick()`, picked at run time by the object's type.

The problem is that this step runs millions of times a second, and every virtual call costs two things an ordinary call doesn't:

- **Look up a table, then jump**: at compile time the subclass isn't known, so the compiler can only emit code that loads the vtable address from the object, loads the address of `on_tick` from the vtable, and jumps there. Where it jumps is known only once that address has been loaded; this is an **indirect jump**. The CPU doesn't wait: it guesses a target and keeps executing, and a wrong guess throws away everything done on that guess, about 15–20 cycles each time.
- **No inlining**: **inlining** means the compiler copies the called function's body straight into the call site, which removes the call itself and lets that code be optimized together with what surrounds it. Not knowing which subclass's `on_tick` will run, the compiler doesn't know which body to copy, so a real function call has to stay.

CRTP lets the compiler know the subclass at compile time, which removes both costs. The same `on_tick` written with CRTP ends up as two instructions (section 1.2 has the full assembly for both versions).

## 1. CRTP: Let the Base Class Know Its Subclass at Compile Time

### 1.1 What It Is: the Subclass Passes Itself to the Base

```cpp
template <typename Derived>
class Base {
public:
    void doSomething() {
        static_cast<Derived*>(this)->doSomethingImpl();   // cast to the subclass and call its implementation
    }
};

class Derived1 : public Base<Derived1> {
public:
    void doSomethingImpl() {
        std::cout << "Derived1 is doing something." << std::endl;
    }
};

template <typename T>
void performAction(Base<T>& obj) {
    obj.doSomething();
}
```

**The name**: in `class Derived1 : public Base<Derived1>` a class uses itself, inside its own definition, as the template argument of its base. That looks recursive, hence "curiously recurring template pattern".

**Why it's legal**: at the point of `Base<Derived1>`, `Derived1` isn't fully defined yet; it is an **incomplete type**: the compiler knows the class exists but not its members or size. `Base<Derived1>` can still be instantiated because the class definition of `Base` uses no member of `Derived`; only the **body** of `doSomething()` does. Member function bodies of a class template are instantiated only when called, and by then `Derived1` is complete. This is what causes the pitfall in section 1.4.3.

**Why `static_cast` is safe**: a cast from a base pointer to a subclass pointer (a downcast) is correct as long as the object **really is** that subclass. `static_cast` needs no run-time check, and usually compiles to no instruction at all (with single inheritance the base subobject and the full object share an address). CRTP guarantees this by convention: only `Derived1` inherits from `Base<Derived1>`. What happens when the convention breaks is in section 1.4.1.

### 1.2 What It Compiles To, Compared with a Virtual Call

The same `on_tick`, once with CRTP and once with a virtual function:

```cpp
template <typename Derived>
struct FeedBase {
    int on_tick(int px) { return static_cast<Derived*>(this)->on_tick_impl(px); }
};
struct BinanceFeed : FeedBase<BinanceFeed> {
    int mult = 2;
    int on_tick_impl(int px) { return px * mult; }
};
template <typename T>
int run_crtp(FeedBase<T>& f, int px) { return f.on_tick(px); }

struct IFeed {
    virtual ~IFeed() = default;
    virtual int on_tick(int px) = 0;
};
struct OkxFeed : IFeed {
    int mult = 3;
    int on_tick(int px) override { return px * mult; }
};
int run_virtual(IFeed& f, int px) { return f.on_tick(px); }
```

GCC 13 `-O2` output:

```text
run_crtp<BinanceFeed>:           run_virtual (OkxFeed is the only implementation):
    movl  (%rdi), %eax               movq  (%rdi), %rax           # load vptr
    imull %esi, %eax                 leaq  OkxFeed::on_tick, %rdx
    ret                              movq  16(%rax), %rax         # load the vtable slot
                                     cmpq  %rdx, %rax             # is it OkxFeed::on_tick?
                                     jne   .L18                   # no: do the indirect call
                                     movl  8(%rdi), %eax          # yes: run the inlined copy
                                     imull %esi, %eax
                                     ret
```

- **CRTP**: `on_tick` → `on_tick_impl` inlines completely, leaving two instructions: load `mult`, multiply. `mult` is at offset 0 because the object has no vptr.
- **Virtual**: GCC applied **speculative devirtualization** here. Seeing only one implementation, `OkxFeed`, in the whole program, it first checks whether the vtable slot is `OkxFeed::on_tick` and, if so, runs an inlined copy. Even then it still loads the vptr, loads the vtable slot and compares. Add a `BybitFeed : IFeed` to the program and `run_virtual` goes back to the two instructions from the opening: `movq (%rdi), %rax` + `jmp *16(%rax)`, a plain indirect jump, with no way to inline the body of `on_tick`.
- **Object size**: `sizeof(BinanceFeed)` is 4 (one `int`; the empty base takes no space), `sizeof(OkxFeed)` is 16 (8-byte vptr + 4-byte `int` + 4 bytes of padding).

What's saved is the list in [Virtual Functions: where the cost is](/ref/virtual-functions/#virtual-cost): an indirect jump to predict, two memory loads, 8 bytes of vptr, and, most valuable, inlining.

**Why inlining is the most valuable part**: first, is the jump itself expensive? If a call site always goes to the same target (as when one feed object receives a whole stream of ticks), the indirect target predictor gets it right almost every time, and the jump plus `call` / `ret` costs a few cycles, under 1–2 ns. The 4–5 ns (15–20 cycles) figure is the cost of **one misprediction**, not something paid on every call. Looked at as a single call, the virtual version isn't much slower.

The gap opens once the call sits in a loop. Same two classes, summing `on_tick` over n prices:

```cpp
long sum_crtp(BinanceFeed& f, const int* px, int n) {
    long s = 0;
    for (int i = 0; i < n; ++i) s += f.on_tick(px[i]);
    return s;
}
long sum_virtual(IFeed& f, const int* px, int n) {
    long s = 0;
    for (int i = 0; i < n; ++i) s += f.on_tick(px[i]);
    return s;
}
```

The loop bodies GCC 13 `-O2` produces:

```text
sum_crtp:
    movl  (%rdi), %edi        # before the loop: load mult once
.L3:
    movl  (%rsi), %eax        # load one price
    addq  $4, %rsi
    imull %edi, %eax          # multiply by mult
    cltq
    addq  %rax, %rdx          # add to s
    cmpq  %rsi, %rcx
    jne   .L3
```

```text
sum_virtual:
    pushq %r13 / %r12 / %rbp / %rbx    # save 4 registers on entry
.L9:
    movq  0(%rbp), %rax       # load vptr every iteration
    movl  (%rbx), %esi        # load one price
    movq  %rbp, %rdi
    addq  $4, %rbx
    call  *16(%rax)           # one indirect call per iteration (on_tick loads mult again inside)
    cltq
    addq  %rax, %r12
    cmpq  %r13, %rbx
    jne   .L9
```

- **CRTP**: the body is copied into the loop, so the compiler can see that `on_tick` just loads `mult` and multiplies. It hoists the load of `mult` out of the loop to run once (loop-invariant code motion), leaving a few instructions per price: load, multiply, add. At `-O3` the loop is also vectorized (`pmuludq` multiplies 4 prices per instruction).
- **Virtual**: every iteration loads the vptr and makes an indirect call, and the called `on_tick` loads `mult` again, because the compiler can't see the body and can't assume `mult` is unchanged between calls. To keep loop variables alive across the `call`, the function saves 4 registers to the stack on entry. Vectorization is out of the question: every price is a separate function call.

So what inlining saves isn't the few cycles of one jump; it lets the compiler optimize the call together with the code around it: hoisting, merging, vectorizing. The smaller the body and the denser the calls, the more this is worth.

### 1.3 Three Uses

#### 1.3.1 A Static Interface: Replacing Virtual Functions on Hot Paths

That's the example above: the base runs the flow (receive, check sequence) and calls a subclass hook at one step; the subclass only implements the hook. It's most common in market-data handling and strategy callbacks, which run millions of times a second and where the exchange is known at deployment.

#### 1.3.2 Injecting Features: the Subclass Writes a Little, the Base Fills in the Rest

Because the base knows the subclass type, it can write generic code on top of functions the subclass already has. For example, the subclass writes only `==` and the base supplies `!=`:

```cpp
template <typename Derived>
struct EqualityOps {
    friend bool operator!=(const Derived& a, const Derived& b) { return !(a == b); }
};
struct Price : EqualityOps<Price> {
    long ticks;
    friend bool operator==(const Price& a, const Price& b) { return a.ticks == b.ticks; }
};
```

The `!=` example is unnecessary in C++20: once `==` exists, the compiler supports `!=` automatically. A standard-library example of the same use, still common today, is `std::enable_shared_from_this<T>`: with `class Session : public std::enable_shared_from_this<Session>`, the subclass writes nothing and gains a member function `shared_from_this()`, which, inside a member function, returns a `std::shared_ptr<Session>` to itself that shares the reference count with the outside owners. To write the return type as `shared_ptr<Session>`, the base must know the subclass, hence CRTP. What problem it solves and what the wrong way does: see [shared_ptr and enable_shared_from_this](/ref/shared-ptr/#shared-from-this-right).

#### 1.3.3 A Separate Static Member per Subclass

`Base<A>` and `Base<B>` are different types, so a `static` member of the base exists once for each. That gives every kind of object its own counter:

```cpp
template <typename Derived>
struct InstanceCounter {
    static inline int alive = 0;
    InstanceCounter() { ++alive; }
    InstanceCounter(const InstanceCounter&) { ++alive; }
    ~InstanceCounter() { --alive; }
};
struct OrderA : InstanceCounter<OrderA> {};
struct OrderB : InstanceCounter<OrderB> {};
```

Create 3 `OrderA` and 2 `OrderB`, destroy one of each, and `InstanceCounter<OrderA>::alive` is 2 while `InstanceCounter<OrderB>::alive` is 1; they don't interfere. With an ordinary base class there would be just one `static` member and no way to tell them apart.

### 1.4 Four Pitfalls

#### 1.4.1 The Wrong Template Argument on the Base: Silently Wrong Results

```cpp
template <typename D> struct Base { int run() { return static_cast<D*>(this)->impl(); } };
struct A : Base<A> { int x = 1; int impl() { return x; } };
struct B : Base<A> { long y = 2; int impl() { return 99; } };   // copied from A, base not updated
```

`B b; b.run();` compiles without complaint and prints 2: `run()` casts a `B` object to `A`, calls `A::impl()`, and reads "where `A` keeps `x`", which is actually `B`'s `y`. That's undefined behavior, and the compiler doesn't check it, because a downcasting `static_cast` trusts the programmer by design.

**The guard**: make the base constructor private and befriend only the class named in the template argument:

```cpp
template <typename Derived>
class SafeBase {
public:
    void run() { static_cast<Derived*>(this)->run_impl(); }
private:
    SafeBase() = default;
    friend Derived;                    // only Derived can construct SafeBase<Derived>
};
struct GoodA : SafeBase<GoodA> { void run_impl() {} };
struct BadB : SafeBase<GoodA> { void run_impl() {} };   // wrong base copied
BadB b;                                                  // compile error: can't be constructed
```

The definition of `BadB` itself compiles, but constructing an object needs the constructor of `SafeBase<GoodA>`, which only `GoodA` may call, so GCC reports `SafeBase() ... is private within this context`. The miscopied subclass fails to compile as soon as it's used.

#### 1.4.2 The Subclass Forgets the Implementation and the Names Match: Infinite Recursion

```cpp
template <typename D> struct Base { int area() { return static_cast<D*>(this)->area(); } };
struct Sq : Base<Sq> { };   // forgot area()
```

`Sq` has no `area()`, so `static_cast<Sq*>(this)->area()` finds the inherited `Base<Sq>::area()` itself and calls itself until the stack overflows. GCC `-Wall` warns `infinite recursion detected`, but only warns. That's why the usual style names the subclass function `doSomethingImpl`, different from the base's `doSomething`: forgetting it becomes a "no such member" compile error.

#### 1.4.3 The Base's Class Definition Can't Use the Subclass's Member Types

```cpp
template <typename D> struct Base { using value_type = typename D::value_type; };
struct C : Base<C> { using value_type = int; };   // compile error
```

GCC reports `invalid use of incomplete type 'struct C'`, for the reason in section 1.1: when `Base<C>` is instantiated, `C` isn't defined yet. Function bodies can use it (by then `C` is complete); the class definition (member types, member variable types, function signatures) can't. If you need it, pass an extra template parameter or keep the subclass's type information in a separate traits template.

#### 1.4.4 No Common Base: No Shared Container

`Base<Derived1>` and `Base<Derived2>` are unrelated types; there is no `std::vector<Base*>`. Every function that takes one has to be a template too (`performAction` above is `template <typename T> void performAction(Base<T>&)`). To keep different subclasses together, see [Section 4.3](#poly-flexibility): `std::variant` + `std::visit` (a fixed set of types), batching by type with one loop each, or one virtual call on the outside to pick, with CRTP all the way down inside.

### 1.5 Choosing Between CRTP and Virtual Functions

| | Virtual functions | CRTP |
|---|---|---|
| When the function is chosen | run time, by the object's actual type | compile time, by the base's template argument |
| One call | load vptr, load vtable, indirect jump | direct call, usually inlined away |
| Object size | one extra vptr (8 bytes) | unchanged |
| Same container | yes (`vector<unique_ptr<Base>>`) | no: `Base<A>` and `Base<B>` are unrelated |
| Adding a subclass | callers needn't recompile; plugins work | every template that uses it is re-instantiated |
| When you get it wrong | a function missing `override` may fail to override | a wrong base is silent UB; matching names recurse forever |

If the type is known at compile time and the call is on a hot path, use CRTP; if objects must share a container or types are added at run time, use virtual functions. The fuller trade-off (code bloat, compile time, picking among already-compiled types at run time) is in [Section 4](#polymorphism).

### 1.6 The C++23 Alternative: Deducing This

C++23 lets `this` be written as an explicit first parameter of a member function (an explicit object parameter, usually called deducing this), with its type deduced from the object the function is called on. The base can then get the subclass type without a template parameter:

```cpp
struct FeedBase23 {
    template <typename Self>
    int on_tick(this Self&& self, int px) { return self.on_tick_impl(px); }
};
struct BybitFeed : FeedBase23 {
    int on_tick_impl(int px) { return px * 4; }
};
```

For `bybit.on_tick(3)`, `Self` is deduced as `BybitFeed&` and `self.on_tick_impl` calls straight into the subclass: the same effect as CRTP, but the "wrong base" of section 1.4.1 can't happen (there's no template argument to get wrong), and `FeedBase23` is an ordinary class. It's supported from GCC 14 and in Clang 18, not in GCC 13. Existing code still mostly uses CRTP.

The same idea of fixing the structure at compile time, applied to stacking features layer by layer, is the mixin ([Section 3](#mixin)); applied to computing values ahead of time, it's the `constexpr` family ([const, constexpr, consteval, constinit](/ref/const-constexpr/)).

## 2. Beyond CRTP: variant and Batching by Type {#virtual-alternatives}

CRTP needs every piece of code to know at compile time which one type it handles. When the set of types is fixed but several types must share one container, two more techniques avoid the virtual call.

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

## 3. Mixins: Stack Features at Compile Time with a Template Inheritance Chain {#mixin}


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

(`MatrixWalk` is the bottom layer: it walks a 2-D `vector` row by row and provides `valid()`, `cell()` and `next()`.) **What it compiles to**: `Iter` is **one object**, with no per-layer heap objects, no pointers and no virtual functions; `Base::next()` and `Base::cell()` are direct calls that inline all the way down. It's the **static polymorphism** version of the decorator pattern, the same trade as CRTP in Section 1.

<a href="/images/ref/mixin-vs-decorator.en.svg" target="_blank" rel="noopener"><img src="/images/ref/mixin-vs-decorator.en.svg" alt="Top: the decorator is 3 heap objects, each with a vptr, linked by inner pointers; one call to cell() loads a pointer, loads the vtable and makes an indirect call at every layer, and the compiler cannot inline. Bottom: the mixin is one 32-byte object; DoubleValue and OddOnly are base classes wrapped around MatrixWalk with no members, no vptr and no pointers, and every call inlines; the conditional jump of the odd filter remains." loading="lazy" decoding="async"></a>

### 3.1 Order Is Meaning {#mixin-order}

For the same matrix `{{1, 2, 3}, {}, {4, 5, 6}}`:

| Type | Output | Why |
|---|---|---|
| `DoubleValue<OddOnly<MatrixWalk>>` | `2 6 10` | keep the odd originals (1, 3, 5), then double |
| `OddOnly<DoubleValue<MatrixWalk>>` | empty | doubling makes everything even, so the odd filter keeps nothing |

A decorator can be stacked at run time from config; a mixin's order is written into the type and fixed at compile time.

### 3.2 Costs {#mixin-cost}

- **Combinatorial types**: every combination is a new type with its own instantiated code, growing compile time and binary size.
- **Hard-to-read errors**: a few levels of nested templates make long error messages.
- **Constructors must forward**: each layer passes its arguments to `Base` (the variadic constructor above, or `using Base::Base;`).
- **Hiding, not overriding**: `OddOnly::next()` only hides `Base::next()`; it isn't a virtual override. Call `next()` through a `MatrixWalk&` and you get `MatrixWalk::next()`. Mixins only work when you keep using the full type.

## 4. Static vs. Dynamic Polymorphism: When the Decision Is Made {#polymorphism}

In one line: **the difference is when "which function to call" gets decided.** Static polymorphism (templates, CRTP, mixins, compile-time decision trees) decides at compile time; dynamic polymorphism (virtual functions) decides at run time from the object's type. Speed, flexibility, and engineering cost all follow from that.

### 4.1 Where the Speed Comes From: Inlining, Not Just One Jump Saved {#poly-speed}

The run-time cost of dynamic polymorphism is in [Virtual Functions 1.3](/ref/virtual-functions/#virtual-cost): one indirect jump to predict, two extra memory reads, 8 bytes per object, and no inlining. The most expensive item is usually **no inlining**. One more cost appears only on a cold start: after the market has been quiet for a while, other code has pushed the hot path out of the cache, and when the next tick arrives the vtable's line may be missing too, adding one serial miss behind the vptr read. The fix is to keep the hot path hot (run it on dummy data periodically even when idle), or use CRTP or `final` so there is no vtable to read.

- The indirect jump itself: when the types at one call site follow a pattern it is almost never mispredicted and costs only a few cycles; with randomly mixed types each mispredict costs about 15–20 cycles.
- Inlining: once the body is expanded into the caller, the compiler can propagate constants, merge computation, and vectorize. The smaller the body, the bigger this gap.

So "static is faster than dynamic" needs two conditions: the call is on a hot path, and the body is small. If the body itself runs for hundreds of ns, the few ns saved don't show. Also, static polymorphism doesn't mean "no branches": conditions that depend on data still compile to conditional jumps in a compile-time decision tree (the tree in [#7 section 3.6](/posts/branch-prediction-branch-optimization/) is 3 conditional jumps). What disappears is the indirect jump that picks the function.

### 4.2 What Static Polymorphism Costs {#poly-cost}

- **Code bloat**: a template is instantiated once per set of arguments. A bigger binary usually doesn't matter; what matters is whether the copies active on the hot path at the same time fit in the instruction cache (L1I, about 32 KiB). One copy for each of 10 symbols, with only one or two running at a time, generally doesn't slow anything down.
- **Compile time**: instantiation and inlining happen at compile time, so template-heavy projects build noticeably slower.
- **Hard-to-read errors**: a few levels of nested templates can turn one wrong type into a very long error. C++20 concepts move some of these up to a single "constraint not satisfied" line.
- **The set of types is fixed at compile time**: covered on its own in the next section.

### 4.3 What "Run-Time Flexibility" Actually Means {#poly-flexibility}

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

### 4.4 How to Choose {#poly-choose}

Two questions:

1. **Can the set of types be fixed at compile time?** If not (plugins, structure pushed at run time), use virtual functions. If so, go on.
2. **Is this call on a hot path?** If not (startup, config loading, management logic that runs a few times a second), use virtual functions; they're easier to read and change. If so, use templates, CRTP, or `std::variant` (when the set is fixed and the objects should be stored together), and make the run-time choice once, outside the loop.

The two are often mixed: an outer virtual call or `variant` picks once, and the chosen code is static all the way down.
