---
title: "Virtual Functions: vptr, vtable and Dynamic Polymorphism"
date: 2026-11-02
slug: "virtual-functions"
description: "A virtual function lets the same o->handle() call a different function at run time depending on the object's actual type. It compiles to three steps: load the vptr, look up the vtable, jump indirectly. The cost is an indirect jump to predict, blocked inlining, two memory loads and 8 extra bytes per object; with final or a local object the compiler can remove it. Last, why to think of composition before inheritance."
summary: "A virtual call = load the vptr at the start of the object → load one slot of the class's vtable → jump to that address. The expensive part is usually not the jump but the lost inlining; when the type is known at compile time, static polymorphism avoids it. To reuse a class's implementation, make it a member, don't inherit from it."
toc: true
group: cpplinux
topic: cpp
weight: 103
aliases: ["/posts/virtual-functions/"]
---

The same `o->handle()` calls a different function depending on which subclass `o` points to: that is dynamic polymorphism, and virtual functions provide it. This post starts from the two instructions it compiles to: what each object hides, what each class gains, what one virtual call costs, and when the compiler can remove it.

## 1. Virtual Functions: Pick the Function by the Object's Type at Run Time {#virtual}

### 1.1 What It Is {#virtual-what}

A function declared `virtual` in a base class, when called through a base-class pointer or reference, runs the version for the object's **actual type**. The call site is always the same `o->handle()`; which function runs is known only at run time, from what `o` points to.

```cpp
struct Msg {
    virtual ~Msg() = default;
    virtual int handle() const = 0;   // pure virtual: every subclass implements it
    int qty = 1;
};
struct TextMsg : Msg {
    int handle() const override { return qty * 2; }
};
struct ImageMsg final : Msg {    // final: no further subclasses
    int handle() const override { return qty * 3; }
};

int run(const Msg* o) { return o->handle(); }   // may be a TextMsg or a ImageMsg
```

Typical use: a container holds objects of different subclasses (`std::vector<std::unique_ptr<Msg>>`), and a loop calls `handle()` on each.

### 1.2 What It Compiles To: vptr and vtable {#virtual-vtable}

`run` compiles to just two instructions:

```asm
run(Msg const*):
        movq    (%rdi), %rax      # 1. load the object's first 8 bytes: the vptr, pointing at its class's vtable
        jmp     *16(%rax)         # 2. load the function address from the table's 3rd slot and jump (indirect jump)
```

Two things make it work:

- **vtable** (virtual function table): one per **class** with virtual functions, in read-only data, listing the address of each virtual function in declaration order. In `TextMsg`'s table the `handle` slot holds `TextMsg::handle`; in `ImageMsg`'s, `ImageMsg::handle`. (The first two slots are destructors, so `handle` sits at offset 16.)
- **vptr** (vtable pointer): a hidden 8-byte pointer at the start of every **object**, set at construction to its class's vtable. That's why `sizeof(TextMsg)` is 16: 8 bytes of vptr, 4 of `qty`, 4 of padding.

So one virtual call = load the vptr → load the table slot → jump to the loaded address.

### 1.3 Where the Cost Is {#virtual-cost}

- **The indirect jump has to be predicted**: the target is loaded from memory, so the front end relies on the **indirect target predictor** ([#7 Section 1.3](/posts/branch-prediction-branch-optimization/)). When the object types at one call site follow a pattern (all the same, or a short repeating cycle), it almost never misses; when they're randomly mixed, it misses often, about 15–20 cycles each time.
- **It blocks inlining**: the compiler doesn't know which function will run, so it can't inline it or optimize across the call (constant propagation, merging computations, vectorization). The smaller the function, the worse this is: `handle()` itself is a single multiply, much cheaper than the call.
- **Two extra memory reads**: first the vptr from the start of the object (`movq (%rdi), %rax`), then the function address from the vtable slot (the `16(%rax)` in `jmp *16(%rax)`). If either goes to memory it costs about 70–120 ns, far more than the call itself, but they rarely do, for two different reasons:
  - **The vptr sits in the same cache line as the object's data.** Without virtual functions you still read the object's members (such as `mult`). If the object is cold, both versions pay one cache miss for that line; reading the vptr doesn't add a second one. What the virtual version adds is only an object 8 bytes bigger, so fewer fit in a line.
  - **There is one vtable per class, not per object.** It lives in the read-only data section; two or three classes means two or three cache lines, shared by every call. When calls are frequent something reads it all the time, so it stays in L1, about 1 ns.
  - **When the prediction is right, the two reads barely slow anything.** The CPU doesn't wait for them to decide where to jump: the predictor supplies the target, the CPU starts executing the callee, and the two reads complete alongside, only to check the guess. On a mispredict, or when this call site has no prediction history yet, it really has to wait: read the vptr, and only then does it know where to read the function address; read that slot, and only then can it jump. The two reads happen one after the other and can't overlap.
  - **What's really expensive is a cold start.** After the program has been idle for a while, other code has pushed this code's cache lines out, and on the next call both the object's line and the vtable's line may be missing. Both versions pay for the object; the vtable miss belongs to the virtual version alone and queues behind the vptr read, adding in the worst case one serial miss of about 70–120 ns (estimated from the [latency ranges](/ref/cpu-memory/#latency), not measured). Where that one miss matters, switch to [static polymorphism](/posts/crtp-static-polymorphism/), which has no vtable to read.
- **8 more bytes per object**: a small object (say a 16-byte message) grows noticeably, so fewer fit in a cache line.

### 1.4 When the Compiler Removes the Virtual Call (Devirtualization) {#virtual-devirt}

When the compiler can prove the actual type, it calls the function directly, or inlines it. Three common cases; the first two are measured:

```cpp
int run_image(const ImageMsg* o) { return o->handle(); }   // ImageMsg is final
int run_local() { TextMsg l; return run(&l); }              // the object is right there
```

- **`final`**: `ImageMsg` is `final`, so there can't be a subclass and `o->handle()` can only be `ImageMsg::handle`. `run_image` compiles to `movl 8(%rdi), %eax` + `leal (%rax,%rax,2), %eax`: the multiply by 3 is inlined, no jump.
- **Local objects**: in `run_local` the type is written right there; once `run` is inlined, the whole function compiles to `movl $2, %eax`.
- **A single implementation**: with `-flto` (link-time optimization) the compiler sees the whole program, and a virtual function with only one implementation can be called directly too (not measured here).

### 1.5 Without Virtual Functions: Static Polymorphism {#virtual-alternatives}

When the type is known at compile time, you don't need a vtable: templates and CRTP fix "which function" at compile time and the call inlines; when the set of types is fixed, `std::variant` dispatches on a type index. Together these are called static polymorphism; what they compile to and what each costs is in [Static Polymorphism](/posts/crtp-static-polymorphism/).

### 1.6 How to Choose {#virtual-choose}

- **The type is only known at run time and the set is open (plugins, read from config)**: virtual functions.
- **The set of types is fixed and objects share one container**: `std::variant` + `std::visit`.
- **The type is known at compile time**: templates or CRTP; mark classes `final` where you can so the compiler can call directly.
- **Most of the time**: virtual functions read and change most easily, so start with them. Only where calls are very frequent and the function body is tiny does the virtual-call cost show, and then switch to [static polymorphism](/posts/crtp-static-polymorphism/).

## 2. Composition and Inheritance: Reuse an Implementation as a Member {#composition}


```cpp
class InheritanceInbox : public std::vector<Msg> {   // inheritance: "is" a vector
};

class CompositionInbox {                                // composition: "has" a vector
    std::vector<Msg> msgs_;
public:
    auto size() const noexcept { return msgs_.size(); }  // expose only what's needed
};
```

**They compile the same**: member access and `size()` both read the field inside `msgs_` directly, and `size()` inlines. The difference is all design; publicly inheriting `std::vector` has three problems:

- **The whole interface is exposed**: anyone can call `push_back` or `erase`, so invariants like "the inbox is sorted by time" can't be protected. Composition exposes only the functions you choose.
- **The destructor isn't virtual**: `std::vector<Msg>* p = new InheritanceInbox;` followed by `delete p` is undefined behavior. Standard containers aren't designed to be base classes.
- **Tied to the implementation**: replacing `std::vector` with another container means changing every caller with inheritance, but only the class's internals with composition.

The rule: if you want "its implementation," make it a member (has-a); public inheritance only when you really mean "usable as one" (is-a) and the base is designed for it (it has a virtual destructor).

