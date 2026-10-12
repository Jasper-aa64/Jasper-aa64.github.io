---
title: "Trading System Notes #8: CRTP and Static Polymorphism"
date: 2026-10-12
slug: "crtp-static-polymorphism"
description: "CRTP (the curiously recurring template pattern): the subclass passes itself to its base as a template argument, so the base knows the subclass at compile time. Why it is legal, how it compiles compared with a virtual call (real GCC assembly, including speculative devirtualization), three uses, four pitfalls (silent UB from a wrong base, infinite recursion on same names, incomplete types, no common base), how to choose against virtual functions, and C++23 deducing this."
summary: "The base class writes the flow and the subclass fills in the details: virtual functions pick the subclass at run time, CRTP at compile time. What you save is more than one indirect jump: the call inlines completely and the object has no vptr. The price is that Base<A> and Base<B> are unrelated types and can't share a container."
chapter: 1
categories: [Systems]
tags: [cpp, crtp, static-polymorphism, virtual-functions, templates, hft, low-latency]
toc: true
homepage: false
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

What's saved is the list in [reference: the cost of virtual functions](/ref/cpp-syntax/#virtual-cost): an indirect jump to predict, two memory loads, 8 bytes of vptr, and, most valuable, inlining.

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

`std::enable_shared_from_this<T>` in the standard library is CRTP: `class Session : public std::enable_shared_from_this<Session>`. Because the base knows `T`, it can return `std::shared_ptr<T>` rather than a `shared_ptr` to the base. (The `!=` example is unnecessary in C++20: once `==` exists, the compiler supports `!=` automatically.)

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

`Base<Derived1>` and `Base<Derived2>` are unrelated types; there is no `std::vector<Base*>`. Every function that takes one has to be a template too (`performAction` above is `template <typename T> void performAction(Base<T>&)`). To keep different subclasses together, see [reference: what run-time flexibility actually means](/ref/cpp-syntax/#poly-flexibility): `std::variant` + `std::visit` (a fixed set of types), batching by type with one loop each, or one virtual call on the outside to pick, with CRTP all the way down inside.

### 1.5 Choosing Between CRTP and Virtual Functions

| | Virtual functions | CRTP |
|---|---|---|
| When the function is chosen | run time, by the object's actual type | compile time, by the base's template argument |
| One call | load vptr, load vtable, indirect jump | direct call, usually inlined away |
| Object size | one extra vptr (8 bytes) | unchanged |
| Same container | yes (`vector<unique_ptr<Base>>`) | no: `Base<A>` and `Base<B>` are unrelated |
| Adding a subclass | callers needn't recompile; plugins work | every template that uses it is re-instantiated |
| When you get it wrong | a function missing `override` may fail to override | a wrong base is silent UB; matching names recurse forever |

If the type is known at compile time and the call is on a hot path, use CRTP; if objects must share a container or types are added at run time, use virtual functions. The fuller trade-off (code bloat, compile time, picking among already-compiled types at run time) is in [reference: static vs. dynamic polymorphism](/ref/cpp-syntax/#polymorphism).

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

The same idea of fixing the structure at compile time, applied to stacking features layer by layer, is the mixin ([reference: composition and mixins](/ref/cpp-syntax/#mixin)); applied to computing values ahead of time, it's the `constexpr` family ([reference: which one guarantees compile time](/ref/cpp-syntax/#compile-time)).
