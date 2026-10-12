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

No copy. The caller reserves 64 bytes on its own stack and passes the address as a hidden argument in `%rdi`, and the function writes there directly. The `s` inside the function never has a copy of "its own". Structs of 16 bytes or less don't even touch memory: for `struct { int i; char c; double d; }`, the `int` and `char` are packed into `%rax` and the `double` comes back in `%xmm0`.

At the language level this is called **copy elision**. When it's guaranteed, when it's up to the compiler, and when it can never happen is the first part of this post; the second part covers another way of telling the compiler it may do less: pure-function attributes. All output and assembly are measured with GCC 13.3 / Clang 18, `-std=c++17 -O2`, x86-64.

## 1. Return Value Optimization: When Nothing Is Copied

The examples below use a class `Tracer` that prints every construction, copy and move; each one is measured output.

### 1.1 RVO: Returning a Temporary, Guaranteed Since C++17

`return T(...)` returns a temporary that has no name yet (a prvalue, in standard terms). Since C++17 this case is **guaranteed** not to call the copy or move constructor: the object is built in the caller's storage from the start. So even a type whose copy and move constructors are `= delete` can be returned by value:

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

Being a language rule rather than an optimization, it doesn't depend on compiler options. It's often said that with `-fno-elide-constructors`, `Tracer t = Tracer("x");` gets an extra copy; under C++17 that's wrong: with or without the flag there is exactly one construction.

### 1.2 NRVO: Returning a Named Local, Allowed but Not Guaranteed

```cpp
Tracer nrvoExample(const std::string& name) {
    Tracer obj(name);
    return obj;
}
```

`obj` has a name; the standard **allows** the compiler to build it directly in the caller's storage (NRVO, named RVO) but doesn't require it. Measured:

- GCC 13 / Clang 18 `-O2`: a single construction; NRVO happened.
- With `-fno-elide-constructors`: an extra move construction appears. That is the only output that changes in the whole test program, which is exactly the point: 1.1 is a guarantee, this is an optimization.
- When one path returns a temporary and another a named object, the two compilers differ:

```cpp
Tracer conditionalReturn(bool flag) {
    if (flag) {
        return Tracer("temporary");
    } else {
        Tracer named("named");
        return named;              // GCC 13: one move; Clang 18: NRVO, no move
    }
}
```

When the compiler can't do NRVO, it doesn't fall back to a copy: since C++11, `return local_variable;` is first treated as an rvalue and prefers the move constructor (implicit move). So the worst case is one move. For `std::string` or `std::vector` a move copies a few pointers and is cheap; for an all-data struct like `Snapshot`, a move is the same as a copy: 64 bytes.

### 1.3 Cases That Can Never Be Elided

- **Returning a parameter**: the parameter's storage is set up by the caller before the call and can't also be the return slot. Measured: one move.
- **Returning a member, a global or a static**: these outlive the function, so the return value must be a new object: a copy. If the caller only needs to read it, return a reference.
- **Returning part of an object** (such as `return p.first;` from a local `std::pair`): what's returned isn't the local object itself, so there's no elision, and no automatic move either (implicit move applies only to a plain local variable name); measured as a copy under both C++17 and C++23. To move, write `return std::move(p.first);`, which blocks no elision here.
- **`return std::move(local);`**: this turns a named object into something else, so NRVO no longer applies, and you force a move instead. GCC `-Wall` reports `-Wpessimizing-move`: "moving a local object in a return statement prevents copy elision".

### 1.4 Keep Logic Out of Copy Constructors

Copies and moves may or may not be elided, so side effects in a copy constructor (printing, counting, registering) run an unpredictable number of times. A `Counter` that counts in its copy constructor reads 1 after `Counter c = createCounter();`: the "copy" the code seems to imply was elided.

What this means on the hot path: returning a struct by value costs nothing, so there's no need to switch to out-parameters (`void make(Snapshot& out)`) to "save a copy"; just watch for the cases in 1.3.

## 2. Pure Functions: Telling the Compiler Calls Can Be Merged

### 2.1 `const` and `pure`: One Reads No Memory, the Other Reads but Never Writes

A pure function has no side effects, its result depends only on its arguments, and the same input always gives the same output. If the compiler knows a function is like that, it can call `f(x) * f(x)` once. GCC and Clang have two attributes:

- **`__attribute__((const))`**: the result depends only on the argument values; the function **neither reads nor writes** any memory (not even what pointer arguments point to).
- **`__attribute__((pure))`**: writes no memory but **may read** globals or memory behind pointers. So if anything writes memory between two calls, the compiler must call again.

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

In `P2`, the global `g_state` is written between the two calls, and a `pure` function might read it, so it's called again; the same code with the `const` `Func1` (`C2`) still calls it once.

### 2.2 Only Needed When the Compiler Can't See the Body

When the definition is in the same translation unit, GCC works out by itself whether a function is `const` / `pure` (or simply inlines it), so there's nothing to annotate. With the functions above defined in the same file, all three calls get inlined and merged; you need `__attribute__((noipa))` (no inference from the body) to see the difference at all. The attributes matter for functions defined in another `.cpp` or a library without LTO (link-time optimization), such as math-library or third-party pricing functions called on the hot path.

### 2.3 A Wrong Promise Is Undefined Behavior

An attribute is a promise the compiler doesn't check. Mark a function `const` when it actually reads a global configuration, and the compiler may cache its result and keep using the old value after the configuration changes. Annotate only genuinely pure computations: prices from arguments, hashes, math functions.

### 2.4 What the Other Spellings Mean

- **GCC / Clang**: `__attribute__((const))`, `__attribute__((pure))`, also spelled `[[gnu::const]]`, `[[gnu::pure]]`. Clang honors both.
- **MSVC `__declspec(noalias)`**: the function accesses memory only through its pointer parameters (no global state). It's about aliasing, only loosely related to purity.
- **`constexpr`**: means "can be evaluated at compile time", not "has no side effects". A `constexpr` function called at run time may modify the caller's variables through reference parameters.
- **`[[nodiscard]]`**: only warns when you discard the return value; nothing to do with purity.
- **Standards**: C++ has no standard pure-function attribute yet; C23 added `[[reproducible]]` (close to `pure`) and `[[unsequenced]]` (close to `const`).
