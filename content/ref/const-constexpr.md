---
title: "const, constexpr, consteval, constinit: Which One Guarantees Compile Time"
date: 2026-11-02
slug: "const-constexpr"
description: "Four keywords that look alike answer different questions: const is read-only and guarantees nothing about compile time; a constexpr variable is always computed at compile time, a constexpr function only can be; every consteval call must happen at compile time; constinit guarantees a static variable is initialized at compile time but can still change. Plus non-type template parameters and generating a lookup table at compile time."
summary: "const is about whether a value can change, not when it is computed; for compile-time values use constexpr variables and consteval functions; for static variables with initialization-order problems use constinit."
toc: true
group: cpplinux
weight: 105
aliases: ["/posts/const-constexpr/"]
---

Four look-alike keywords that answer different questions:

| Keyword | Applies to | Guaranteed to be computed at compile time? | Can it change later? |
|---|---|---|---|
| `const` | variables, parameters, member functions | **no** | no |
| `constexpr` | variables | yes | no |
| `constexpr` | functions | no: only where a constant is required | — |
| `consteval` | functions | yes: every call is evaluated at compile time | — |
| `constinit` | variables with static storage duration | the initialization is | **yes** (not `const`) |

## 1. `const`: Read-Only, Not a Compile-Time Constant {#const}

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

## 2. `constexpr`: Variables Are Computed at Compile Time, Functions *Can* Be {#constexpr}

- **A `constexpr` variable**: its initial value must be computed at compile time, or it's a compile error.
- **A `constexpr` function**: is *allowed* to run at compile time. Where a constant is required (a `constexpr` variable, a template argument, an array size, `static_assert`), it must; with a run-time argument it's an ordinary call.

```cpp
constexpr int twice(int x) { return x + x; }
constexpr int four = twice(2);           // computed at compile time: 4
int twice_rt(int n) { return twice(n); } // computed at run time
```

`twice_rt` compiles to a single `leal (%rdi,%rdi), %eax`, like any ordinary function. `constexpr` is not an optimization hint.

## 3. `consteval`: Every Call Must Happen at Compile Time {#consteval}

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

## 4. `constinit`: Static Variables Initialized at Compile Time, Still Mutable {#constinit}

`constinit` does one thing: **a global or `static` variable must be initialized at compile time**, or it's a compile error. It is **not** `const`; the variable can change afterwards.

```cpp
constexpr int somefunc() { return 27; }    // must be constexpr, or the next line fails to compile
constinit int g_counter = somefunc();      // goes in .data, with 27 stored in the executable
// ...
++g_counter;                               // allowed
```

It guards against the **static initialization order fiasco**: globals initialized at run time are computed by startup code before `main`, the order across source files is unspecified, and a global that reads another one not yet initialized is a bug. `constinit` guarantees that step doesn't exist.

## 5. Non-Type Template Parameters: Make a Constant Part of the Type {#nttp}

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

`Vector<4>` and `Vector<8>` are two types, each compiled separately; the trip count is a constant, so the compiler can fully unroll or vectorize. The cost is the code bloat in [entry 3](/ref/cpp-syntax/#poly-cost). The template argument must be a compile-time constant: `const int d = 4;` works, `int n = 4; const int d = n;` doesn't.

## 6. Generating a Lookup Table at Compile Time {#lut}

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

## 7. How to Choose {#compile-time-choose}

- The value must exist at compile time and failing to compute it should be an error → a `constexpr` variable or a `consteval` function.
- One implementation used both at compile time and at run time → a `constexpr` function, with `if consteval` if needed.
- A global or `static` variable that must be mutable but shouldn't be initialized at run time → `constinit`.
- You just don't want it modified → `const`.

