---
title: "Trading System Notes #11: Return Value Optimization and Pure Functions"
date: 2026-10-12
slug: "rvo-pure-functions"
description: "Returning a 64-byte market snapshot by value compiles to neither a copy nor a move: the caller passes an address and the function writes straight into it. This post separates RVO (guaranteed since C++17), NRVO (up to the compiler; GCC and Clang measurably differ) and the cases that can never be elided (returning a parameter, a member, std::move of a local), then covers how const / pure attributes let the compiler merge repeated calls, and when you actually need them. All output and assembly are measured with GCC 13 / Clang 18."
summary: "Returning a struct by value is usually free, so there's no need for out-parameters; what to watch are the few patterns that always move or copy. Pure-function attributes are a promise to the compiler: right, and it calls less; wrong, and it's undefined behavior."
chapter: 1
categories: [Systems]
tags: [cpp, rvo, copy-elision, move-semantics, pure-functions, hft, low-latency]
toc: true
light: true
---

Market-data code is full of functions like this: compute a book snapshot and return it by value.

```cpp
struct Snapshot { double bid[4]; double ask[4]; };
Snapshot make_snap(double px) {
    Snapshot s;
    for (int k = 0; k < 4; k++) { s.bid[k] = px - k; s.ask[k] = px + k; }
    return s;
}
```

Does returning a 64-byte struct by value build one copy inside the function and then copy it to the caller? GCC 13 `-O2` compiles it to:

```text
make_snap(double):
    movq    %rdi, %rax         # the return value is the address the caller passed in
    ...
    movups  %xmm1, (%rdi)      # written straight into the caller's memory
    movups  %xmm1, 16(%rdi)
    movups  %xmm1, 32(%rdi)
    movups  %xmm0, 48(%rdi)
    ret
```

No copy. The caller reserves 64 bytes on its own stack and passes the address as a hidden argument in `%rdi`, and the function writes there directly. The `s` inside the function never has a copy of "its own", so `return s` has nothing to copy. A plain struct of 16 bytes or less doesn't even need that memory: it comes back in registers.

This is called **copy elision**, and there is only one way to do it: the object being returned has to live in the caller's storage from the moment it is created. Whether a copy can be avoided comes down to whether the function can arrange that. The second half of the post covers another way the compiler does less work: when two calls with the same argument can become one. All output and assembly are measured with GCC 13.3 / Clang 18, `-std=c++17 -O2`, x86-64.

## 1. Return Value Optimization: When Nothing Is Copied

The examples below use a class `Tracer` that prints every construction, copy and move; each one is measured output.

### 1.1 RVO: Returning a Temporary, Guaranteed Since C++17

`return T(...)` creates its object right at the `return`, so that object can always be built directly in the caller's storage. C++17 made this a language rule: a value like `T(...)` that has no name yet (a prvalue, in the standard's terms) is no longer turned into a temporary and then copied out; it directly initializes the final object. There is no second object, so there is nothing to copy or move, and even a type whose copy and move constructors are both `= delete` can be returned by value this way:

```cpp
class NonCopyableNonMovable {
public:
    explicit NonCopyableNonMovable(int id) : id_(id) {}
    NonCopyableNonMovable(const NonCopyableNonMovable&) = delete;
    NonCopyableNonMovable(NonCopyableNonMovable&&) = delete;
private:
    int id_;
};

NonCopyableNonMovable create() {
    return NonCopyableNonMovable(42);       // fine in C++17; fails to compile with -std=c++14
}
```

Since this is a language rule rather than an optimization, no compiler flag turns it off. It's often said that with `-fno-elide-constructors` (the flag that disables copy elision), `Tracer t = Tracer("x");` makes an extra copy; under C++17 that's wrong: measured with and without the flag, there is exactly one construction.

### 1.2 NRVO: Returning a Named Local, Allowed but Not Guaranteed

A named local object is different: it is created on the line that declares it, before the `return`. To build it directly in the caller's storage, the compiler has to decide at that point that "this is the one that will be returned".

```cpp
Tracer nrvoExample(const std::string& name) {
    Tracer obj(name);
    return obj;
}
```

Here there is only one object and every path returns it, so the decision is safe. GCC 13 and Clang 18 at `-O2` both do it, with a single construction measured; this is NRVO (named RVO). But it is only an optimization the standard allows: with `-fno-elide-constructors`, an extra move appears here, while the example in 1.1 is unaffected.

With two objects alive at the same time, the decision can't be made:

```cpp
Tracer pick(bool flag) {
    Tracer a("a"), b("b");
    if (flag) return a;    // one move
    return b;              // one move
}
```

The caller's storage can hold only one object. Put `a` there and it is still occupying it when the code reaches `return b`; the same goes for `b`. So both have to be built on the function's own stack and moved over at the return. Cases in between are where compilers differ. When one path returns a temporary and another returns a named object, the two paths never have objects at the same time, so it could be done: measured, Clang 18 does it and GCC 13 doesn't, adding a move. Whether the decision gets made depends on how closely the compiler analyzes the function.

When the decision can't be made, the compiler doesn't fall back to a copy: since C++11, `return local_variable;` is first treated as an rvalue and prefers the move constructor (implicit move), so the worst case is one move. For `std::string` or `std::vector` a move copies a few pointers and is cheap; for an all-data struct like `Snapshot`, a move is the same as a copy: 64 bytes.

### 1.3 Cases That Can Never Be Elided

In the following cases the returned object can never be created in the caller's storage: the function didn't create it, or it isn't a whole object, or the `return` doesn't name it directly.

- **Returning a parameter**: the caller creates the parameter before the call, somewhere else, so it can't be created a second time in the return slot. A parameter counts as a local variable and is moved automatically: measured, one move.
- **Returning a member, a global or a static**: these exist before the function runs and are still needed after it, so the return value has to be a new object: a copy. If the caller only needs to read it, return a reference.
- **Returning part of an object** (such as `return p.first;` from a local `std::pair`): only one member of `p` is returned, and the whole of `p` doesn't fit in the return slot. It isn't moved automatically either (implicit move applies only to a plain local variable name); measured as a copy under both C++17 and C++23. To move, write `return std::move(p.first);`; there is no elision here for it to block.
- **`return std::move(local);`**: `local` could have had NRVO, but what follows `return` is no longer its name, it's the result of a function call, so the compiler no longer recognizes it and is forced to move instead. GCC `-Wall` reports `-Wpessimizing-move`: "moving a local object in a return statement prevents copy elision".

So on the hot path, write by-value returns the way `make_snap` does: one object used from start to finish and returned on every path, or a plain `return T(...)`. That neither copies nor moves, so there's no need to switch to out-parameters (`void make(Snapshot& out)`) to "save a copy". Extra moves or copies come only from the cases in 1.2 the compiler can't decide and the ones above.

### 1.4 Copy Constructors Only Copy: The Compiler May Skip Them

`Tracer` prints a line on every copy and move, yet several examples above printed only the constructor line: the copy and move constructors were not called at all. Normally a compiler isn't allowed to do that. Optimizations keep one rule: what the program visibly does must match running the code line by line (the as-if rule). Printing is visible, so the compiler can't drop a call that prints. Copy elision is an exception the standard makes on purpose: even if a copy or move constructor prints or counts, the compiler may skip it. When a function returns a temporary directly, as in 1.1, the standard requires skipping it.

As a result, how many times the copy and move constructors run depends on how the function is written, which compiler you use and which flags you pass. For the function in 1.2 where one path returns a temporary and another returns a named object, GCC 13 prints one more move and Clang 18 doesn't; `nrvoExample` with `-fno-elide-constructors` also prints one more. With printing, only the output differs. If they do real work, such as counting how many copies were made, giving the copy a new ID or writing an audit log line, the program's results change with the compiler.

So copy and move constructors should only copy and move. Work that must happen once per object goes into the constructors and the destructor, as a pair. A `Counter` that tracks how many objects are alive adds 1 in every constructor and subtracts 1 in the destructor:

```cpp
class Counter {
public:
    Counter() { ++instance_count_; }
    Counter(const Counter&) { ++instance_count_; }
    ~Counter() { --instance_count_; }
    static int instance_count() { return instance_count_; }
private:
    static int instance_count_;
};

Counter createCounter() { return Counter(); }
```

After `Counter c = createCounter();` the count reads 1. To see it without elision you have to go back to C++14 and add `-fno-elide-constructors` (from C++17 on, the copy in this form can't be turned off). Then the temporary in the function is copied into the return value and the return value is copied into `c`: two extra copies, and the count still reads 1, because both intermediate objects are destroyed after use and take back the 1 they added. When the copy is elided, the intermediate object is never created, so its constructor and its destructor are skipped together, and the +1 and the -1 disappear together. Bookkeeping done in pairs stays correct whether or not copies are elided.

## 2. Pure Functions: Telling the Compiler Calls Can Be Merged

Call a function twice with the same argument, as in `f(x) * f(x)`: can the compiler call it once? If the body is right there, it can tell for itself. If the function is defined in another `.cpp` or a library, it can't see what the function does, so it has to assume it might change a global or write a log; the two calls might return different results or have different effects, so both calls must happen. A pure-function attribute is your promise to the compiler, on the function's behalf, that it has no such side effects and its result depends only on its inputs.

### 2.1 `const` and `pure`: One Reads No Memory, the Other Reads but Never Writes

The promise comes in two strengths, one attribute each in GCC and Clang:

- **`__attribute__((const))`**: the result depends only on the argument values; the function **neither reads nor writes** any memory (not even what pointer arguments point to).
- **`__attribute__((pure))`**: writes no memory but **may read** globals or memory behind pointers. If anything writes memory between two calls, what it reads may have changed, so the compiler must call again.

Measured (with the callee's definition invisible to the compiler):

```cpp
double g_state = 0;

double Func1(double) __attribute__((const));
double Func2(double x) { return Func1(x) * Func1(x) + 1.; }                     // 1 call
double C2(double x) { double a = Func1(x); g_state = 1; return a * Func1(x); }  // 1 call

double G1(double);
double G2(double x) { return G1(x) * G1(x) + 1.; }                             // 2 calls

double P1(double) __attribute__((pure));
double P2(double x) { double a = P1(x); g_state = 1; return a * P1(x); }        // 2 calls
```

In `P2`, the global `g_state` is written between the two calls, and the `pure` `P1` might read it, so it's called again; the same code with the `const` `Func1` (`C2`) still calls it once, because `Func1` promises not to read memory, so the write can't matter.

### 2.2 Only Needed When the Compiler Can't See the Body

When the definition is in the same translation unit, GCC works out by itself whether a function is `const` / `pure`, or simply inlines it, so there's nothing to annotate. The attributes matter for functions defined in another `.cpp` or a library without LTO (link-time optimization, which looks at the bodies from all files together only at link time), such as math-library or third-party pricing functions called on the hot path.

### 2.3 A Wrong Promise Is Undefined Behavior

An attribute is a promise the compiler doesn't check. Mark a function `const` when it actually reads a global configuration, and the compiler may cache its result and keep using the old value after the configuration changes. Annotate only genuinely pure computations: prices from arguments, hashes, math functions.

### 2.4 What the Other Spellings Mean

- **GCC / Clang**: `__attribute__((const))`, `__attribute__((pure))`, also spelled `[[gnu::const]]`, `[[gnu::pure]]`. Clang honors both.
- **MSVC `__declspec(noalias)`**: the function accesses memory only through its pointer parameters (no global state). It's about aliasing, only loosely related to purity.
- **`constexpr`**: means "can be evaluated at compile time", not "has no side effects". A `constexpr` function called at run time may modify the caller's variables through reference parameters.
- **`[[nodiscard]]`**: only warns when you discard the return value; nothing to do with purity.
- **Standards**: C++ has no standard pure-function attribute yet; C23 added `[[reproducible]]` (close to `pure`) and `[[unsequenced]]` (close to `const`).
