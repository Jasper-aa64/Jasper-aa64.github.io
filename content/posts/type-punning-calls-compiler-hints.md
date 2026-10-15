---
title: "Trading System Notes #13: Type Punning, Function Calls, and Compiler Hints"
date: 2026-10-15
slug: "type-punning-calls-compiler-hints"
description: "Why flipping bits of a double through a pointer cast can read a stale value, and why memcpy and std::bit_cast cost nothing; how arguments are passed when a call can't be inlined, small by value and large by const&, and how the compiler already turns tail recursion into a loop; then a typical set of performance helper macros and the decision each one makes for the compiler. Assembly is measured with GCC 16 -O2 on x86-64."
summary: "How far the compiler can optimize depends on what it can see and what it dares to assume: different types are treated as non-overlapping, an invisible function body means arguments go by the calling convention, and helper macros are decisions you make for it, not all of them right."
chapter: 1
categories: [Systems]
tags: [cpp, type-punning, strict-aliasing, bit-cast, calling-convention, compiler-optimization, hft, low-latency]
toc: true
math: true
light: true
---

How far the compiler can optimize depends on what it can see and what it dares to assume. All three topics in this post hinge on that. Change a few bits of a double through an integer pointer, and the compiler, optimizing on the assumption that pointers of different types never point to the same memory, may treat your change as if it never happened. When a function can't be inlined, its arguments have to be laid out by the calling convention, and passing by value versus by reference costs a few instructions and can stop the compiler from optimizing. And the performance helper macros common in projects each make a decision for the compiler, not all of them right.

## 1. Binary Representation and Type Punning: How a Double Is Stored, and How to Change Its Bits Safely

### 1.1 IEEE 754: Sign, Exponent, Mantissa

A double is 8 bytes, 64 bits, split by IEEE 754 into three fields: the top bit is the sign, the next 11 bits are the exponent, and the remaining 52 bits are the mantissa. The value is:

$$x = (-1)^{s} \times 1.f \times 2^{\,e - 1023}$$

$1.f$ means there's an implicit 1 in front of the mantissa that isn't stored; the exponent $e$ is stored with 1023 added (the bias), so no negative numbers need to be stored. Take 100: $100 = 1.5625 \times 2^{6}$, so the sign stores 0, the exponent stores $6 + 1023 = 1029$, i.e. 0x405, and since 1.5625 is 1.1001 in binary, the mantissa stores the 1001 after the point, followed by zeros. Put together, that's 0x4059000000000000:

<svg viewBox="0 0 760 196" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The 64 bits of the double 100.0: 1 sign bit, 11 exponent bits, 52 mantissa bits" style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif">
  <style>
    .fbg   { fill: #fbfaf7; }
    .fs    { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.4; }
    .fe    { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.4; }
    .fm    { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.4; }
    .ink   { fill: #1c1b18; font-size: 13px; }
    .muted { fill: #6b6558; font-size: 12px; }
    .bits  { fill: #1c1b18; font-size: 15px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .ttl   { fill: #1c1b18; font-size: 14px; font-weight: 700; }
      :root[data-theme="dark"] .fbg { fill: #17161b; }
      :root[data-theme="dark"] .fs { fill: #4a2f2c; stroke: #8f5a4c; }
      :root[data-theme="dark"] .fe { fill: #33421f; stroke: #8fb257; }
      :root[data-theme="dark"] .fm { fill: #23262c; stroke: #3f4650; }
      :root[data-theme="dark"] .ink { fill: #e9e7ef; }
      :root[data-theme="dark"] .bits { fill: #e9e7ef; }
      :root[data-theme="dark"] .ttl { fill: #e9e7ef; }
      :root[data-theme="dark"] .muted { fill: #a19caf; }
  </style>
  <rect class="fbg" x="0" y="0" width="760" height="196" rx="10"/>
  <text class="ttl" x="24" y="30">100.0 as a double: 64 bits (IEEE 754)</text>
  <text class="muted" x="40" y="58">bit 63</text>
  <text class="muted" x="126" y="58">bits 62–52</text>
  <text class="muted" x="362" y="58">bits 51–0</text>
  <rect class="fs" x="40" y="66" width="80" height="58" rx="6"/>
  <rect class="fe" x="120" y="66" width="236" height="58" rx="6"/>
  <rect class="fm" x="356" y="66" width="364" height="58" rx="6"/>
  <text class="ink" x="52" y="86">sign</text>
  <text class="bits" x="74" y="112">0</text>
  <text class="ink" x="132" y="86">exponent (11 bits)</text>
  <text class="bits" x="132" y="112">100 0000 0101</text>
  <text class="ink" x="368" y="86">mantissa (52 bits)</text>
  <text class="bits" x="368" y="112">1001 0000 0000 … 0000</text>
  <text class="muted" x="40" y="150">0 → positive</text>
  <text class="muted" x="40" y="170">1 → negative</text>
  <text class="muted" x="132" y="150">0x405 = 1029</text>
  <text class="muted" x="132" y="170">1029 − 1023 = 6</text>
  <text class="muted" x="368" y="150">add the implicit 1: 1.1001₂ = 1.5625</text>
  <text class="muted" x="368" y="170">1.5625 × 2⁶ = 100</text>
</svg>

The sign has the top bit to itself, so setting bit 63 and leaving the rest alone gives −100, 0xC059000000000000 in hex. A float has the same structure with 1 + 8 + 23 bits and a bias of 127: 2.0f is 0x40000000, and setting bit 31 gives 0xC0000000, which is −2.0f.

### 1.2 Changing the Sign Doesn't Need Bit Twiddling: The Compiler Already Uses Bit Operations

Since the sign is the top bit, negating or taking an absolute value is a single bit operation. But you don't need to do it yourself; write the math, and the compiler turns it into a bit operation:

```cpp
double neg(double x)    { return -x; }
double absd(double x)   { return std::fabs(x); }
double negabs(double x) { return -std::fabs(x); }    // set bit 63
```

```text
neg(double):
    xorpd   .LC1(%rip), %xmm0    # XOR with 0x8000000000000000: flip the sign bit
    ret
absd(double):
    andpd   .LC2(%rip), %xmm0    # AND with 0x7FFFFFFFFFFFFFFF: clear the sign bit
    ret
negabs(double):
    orpd    .LC1(%rip), %xmm0    # OR with 0x8000000000000000: set the sign bit
    ret
```

`-std::fabs(x)` is "set the top bit": one `orpd`, and the value stays in a floating-point register. The cases that really need to read or write a number as a string of bits are two others: the data arrives as bytes, such as a price field in an exchange's binary market data that has to be taken as 8 bytes from the receive buffer and read as a double; or the bits themselves are what you want, to hash a double, compare as integers, or serialize. Then the same memory has to be viewed as a different type. The handiest way is a pointer cast, and that's exactly the wrong one.

### 1.3 Strict Aliasing: Why a Pointer Cast Can Read a Stale Value

C++ has a rule called **strict aliasing**: an object of some type in memory may only be read or written through that type (or `char`, `unsigned char`, `std::byte`). Turned around, the compiler may assume that two pointers of different types never point to the same object. That's the same kind of information as `__restrict` in [#10](/posts/pointer-memory-access/), except you don't write it; the compiler infers it from the types. With it, after a store through a `uint64_t*` the compiler needn't worry that some `double` changed, so a `double` value can stay in a register instead of being reloaded from memory.

Point a `uint64_t*` at a `double` and the assumption no longer holds, but the compiler still optimizes on it:

```cpp
double alias(double* d, uint64_t* u) {
    *d = 1.0;
    *u = 0;          // the compiler assumes u and d point to different objects
    return *d;       // so it returns 1.0 without reloading
}
```

```text
alias(double*, unsigned long long*):
    movsd   .LC0(%rip), %xmm0    # .LC0 = 1.0
    movsd   %xmm0, (%rdi)        # *d = 1.0
    movq    $0, (%rsi)           # *u = 0
    ret                          # the return value is still the 1.0 in %xmm0
```

Called as `alias(&x, (uint64_t*)&x)`, it measurably returns 1 while memory already holds 0. With `-fno-strict-aliasing` turning the assumption off, it reloads before the `return` and returns 0.

Doing the change directly in one function often seems to work: after `double x = 100;` and `*(uint64_t*)&x |= 0x8000000000000000;`, printing `x` with GCC `-O2` gives −100. That's because both pointers come from `&x`, which the compiler can see this time. But it also warns on that line, `'x' is used uninitialized`: as far as it's concerned, the memory read as a `uint64_t` was never written. It works only because the compiler happened to see through it; put a function boundary in between and you get `alias` above.

Reading another member of a union has the same problem. C allows it; in C++, reading a member other than the one last written is undefined behavior. GCC's documentation explicitly supports reading through a union this way, so it works on GCC, with no guarantee on other compilers.

### 1.4 `memcpy` and `std::bit_cast`: The Correct Way Costs Nothing

The correct way is to copy the bytes into a variable of the target type, with `std::memcpy` or C++20's `std::bit_cast`. A copy sounds expensive, but the compiler recognizes a fixed 8-byte copy and emits a single register-to-register move:

```cpp
uint64_t bits_memcpy(double x) { uint64_t u; std::memcpy(&u, &x, sizeof u); return u; }
uint64_t bits_cast(double x)   { return std::bit_cast<uint64_t>(x); }
```

```text
bits_memcpy(double):
    movq    %xmm0, %rax          # move the 64 bits from the FP register to an integer register as is
    ret
bits_cast(double):
    movq    %xmm0, %rax
    ret
```

Both compile to the same thing. `std::bit_cast` also checks at compile time that both sides have the same size and are trivially copyable, and it works in `constexpr`. `bits_cast(100.0)` measures 0x4059000000000000, matching 1.1.

Reading fields from a receive buffer is `memcpy` too:

```cpp
double read_px(const unsigned char* p) { double d; std::memcpy(&d, p, sizeof d); return d; }
uint32_t read_be32(const unsigned char* p) {
    uint32_t v;
    std::memcpy(&v, p, sizeof v);
    return std::byteswap(v);             // big-endian field to little-endian
}
```

```text
read_px(unsigned char const*):
    movsd   (%rdi), %xmm0        # one 8-byte load
    ret
read_be32(unsigned char const*):
    movl    (%rdi), %eax
    bswap   %eax                 # reverse the byte order
    ret
```

`read_px` is a single load, and an unaligned address is fine because x86 allows unaligned loads; reading from byte 3 of a buffer measurably works. Writing `*(double*)p` reads `char` memory through a `double`, which breaks strict aliasing, plus another layer of undefined behavior when the address is misaligned. x86 is little-endian, with the low byte at the low address; some exchange protocols send integers big-endian (network byte order), Nasdaq's ITCH for example, so after the load the byte order has to be reversed, and C++23's `std::byteswap` compiles to one `bswap`.

Bits can be changed this way too, but it isn't always best: `std::bit_cast<double>(std::bit_cast<uint64_t>(x) | 0x8000000000000000)` measurably compiles to three instructions, `movq` into an integer register, `btsq` to set the bit, and `movq` back, while `-std::fabs(x)` from 1.2 is a single `orpd`. When there's a plain math form, write the math.

### 1.5 The Other Use of a Union: `std::variant`

A union has another use: one slot holding one of several types, to save memory. A market data message might be a new order, a cancel or a trade, each with different fields, kept in the same memory with a union. The trouble is that a union doesn't remember which one it currently holds, and reading the wrong member is the punning of 1.3 again. C++17's `std::variant` stores an extra index that records the current type:

```cpp
union U3 { int i; float f; std::array<char, 16> a; };    // 16 bytes
using V3 = std::variant<int, float, std::array<char, 16>>; // 20 bytes
```

The measured `sizeof` values are 16 and 20: the variant adds a 1-byte index, padded to 4-byte alignment. `std::get<int>(v)` throws `std::bad_variant_access` when `v` doesn't hold an `int`. Dispatching on the current type is `std::visit`:

```cpp
std::variant<int, float> v{42};
std::visit([](auto&& x) { std::cout << x << '\n'; }, v);
```

`std::visit` compiles to reading the index, comparing, and jumping to the matching branch, like a hand-written `switch`, with no virtual call: for `std::variant<int, float, double>` the visit measures one `movzbl` to read the index plus two `cmp`s.

## 2. Functions That Can't Be Inlined: How Arguments Are Passed, and What to Do About Recursion

### 2.1 The Calling Convention: Arguments Go in Registers First

When a function is inlined, it doesn't matter how arguments are passed; the compiler expands the body right at the call site. But sometimes a call can't be inlined: the function is defined in another file or a library, it's called through a function pointer or a virtual function, it's recursive, or it's too big for the compiler to want to expand it. Then the arguments are laid out by the **calling convention**. Linux x86-64 uses the System V convention: the first 6 integer or pointer arguments go into `rdi`, `rsi`, `rdx`, `rcx`, `r8` and `r9`, the first 8 floating-point arguments into `xmm0`–`xmm7`, and only the rest go on the stack; the return value goes in `rax` or `xmm0`, and a large return value uses the hidden address covered in [#11](/posts/rvo-pure-functions/).

### 2.2 Small by Value, Large by `const&`

Pass an `int` by value and the value sits in a register; pass it as `const int&` and what goes in is an address, so the function first has to load from memory, and the caller first has to put the value in memory to have an address to pass. The functions below are marked `noinline` to stand in for calls that can't be inlined:

```cpp
[[gnu::noinline]] int use_val(int x)        { return x * 3; }
[[gnu::noinline]] int use_ref(const int& x) { return x * 3; }
int call_val(int a) { return use_val(a + 1); }
int call_ref(int a) { return use_ref(a + 1); }
```

```text
use_val(int):
    leal    (%rdi,%rdi,2), %eax  # x is right there in %edi
    ret
use_ref(int const&):
    movl    (%rdi), %eax         # first load x through the address
    leal    (%rax,%rax,2), %eax
    ret
call_val(int):
    addl    $1, %edi
    jmp     use_val(int)         # the argument is already in place, just jump
call_ref(int):
    subq    $16, %rsp            # make room on the stack
    addl    $1, %edi
    movl    %edi, 12(%rsp)       # store a + 1 on the stack so it has an address
    leaq    12(%rsp), %rdi
    call    use_ref(int const&)
    addq    $16, %rsp
    ret
```

Structs behave the same way. A trivially copyable struct of up to 16 bytes passed by value is split across two registers; anything bigger, and the caller makes a copy on the stack:

```cpp
struct Small { double px; int64_t qty; };              // 16 bytes
struct Big   { double px; int64_t qty; int64_t id; };  // 24 bytes
```

Measured, `f_small(Small)` receives its two fields in `xmm0` and `rdi`, while `f_big(Big)` reads its fields from the stack, where the caller first builds a 24-byte copy. So pass small things by value, such as scalars, iterators, `std::string_view` and `std::span`; pass `const&` for things like `std::vector` and large structs that are expensive to copy and don't fit in registers.

### 2.3 `const&` Also Blocks Optimization: The Compiler Must Assume It Changes

Passing by reference has a hidden cost too: the compiler has to assume the referenced value may be changed by other stores. In the scaling function below, when `f` is passed by reference it might point at an element of `v`, so any write to `v[i]` might change `f`, and it has to be reloaded every iteration:

```cpp
void scale_ref(double* v, int n, const double& f) { for (int i = 0; i < n; ++i) v[i] *= f; }
void scale_val(double* v, int n, double f)        { for (int i = 0; i < n; ++i) v[i] *= f; }
```

```text
scale_ref(double*, int, double const&):    # loop body
.L9:
    movsd   (%rdi), %xmm0
    mulsd   (%rdx), %xmm0        # reload f from memory every iteration
    addq    $8, %rdi
    movsd   %xmm0, -8(%rdi)
    cmpq    %rax, %rdi
    jne     .L9
scale_val(double*, int, double):           # loop body
.L13:
    movsd   (%rdi), %xmm0
    addq    $8, %rdi
    mulsd   %xmm1, %xmm0         # f stays in register %xmm1
    movsd   %xmm0, -8(%rdi)
    cmpq    %rax, %rdi
    jne     .L13
```

The extra load usually hits L1 and isn't expensive by itself, but it shows the compiler won't treat `f` as unchanging. At `-O3`, when it wants to vectorize, GCC's report says the loop was "versioned for vectorization because of possible aliasing": it inserts a check of whether `f` and `v` overlap, and takes the slow copy if they do. `scale_val` has no such step. This is the same thing as 1.3: whether the compiler dares to optimize depends on whether it can be sure two pieces of memory don't overlap.

### 2.4 Recursion: The Compiler Turns Tail Calls into Loops Itself

Recursion can't be inlined: the function calls itself, and expanding one level leaves another. Every call leaves a return address on the stack and saves registers, and recursion that goes too deep runs out of stack. The most common part of that overhead, though, the compiler removes itself. When calling itself is the last thing a function does (a tail call), nothing is left to do after it returns, so GCC turns the call into a jump. In a preorder traversal, the call for the right subtree is a tail call:

```cpp
void preorder(Node* root) {
    if (root) {
        visit(root);
        preorder(root->left);
        preorder(root->right);   // the last step: a tail call
    }
}
```

```text
.L30:                            # innermost level emitted by GCC -O2 (excerpt)
    movq    %r14, %rdi
    call    visit(Node*)
    movq    8(%r14), %rdi        # root->left
    call    preorder(Node*)      # left subtree: a real recursive call
    movq    16(%r14), %r14       # root = root->right
    testq   %r14, %r14
    jne     .L30                 # right subtree: jump back to the top, no call
```

GCC also unrolled the recursion several levels deep. So rewriting tail recursion as a loop by hand mostly repeats the compiler's work. To remove recursion entirely, use an explicit stack backed by a fixed-size array rather than `std::stack`, which sits on `std::deque` and allocates. For walking a tree, the call overhead often isn't the main cost anyway: every step waits for the next node to come back from memory, the pointer chasing covered in [#10](/posts/pointer-memory-access/), and when a node isn't in cache, a step costs a full memory latency.

## 3. Helper Macros: Each One Makes a Decision for the Compiler

Projects often have a header full of cross-compiler performance macros. These are typical (only the GCC branch is kept):

```cpp
#define HPC_FAST_BEGIN _Pragma("GCC push_options") \
_Pragma("GCC optimize (\"O3,unroll-loops,associative-math,no-signed-zeros\")")
#define HPC_FAST_END _Pragma("GCC pop_options")

#define HPC_ALIGN(N) __attribute__((aligned(N)))

template <typename To, typename From>
inline const To& bit_cast_ref(const From* ptr) noexcept {
    return *reinterpret_cast<const To*>(ptr);
}
```

### 3.1 `HPC_FAST_BEGIN`: Per-Function Optimization Options, at the Cost of Inlining

Functions between `HPC_FAST_BEGIN` and `HPC_FAST_END` are compiled with `-O3`, loop unrolling, and associativity for floating-point addition. The effect is real: a float sum loop inside measurably compiles to `addps` vector additions, while the same loop outside is `addss`, one addition at a time. Allowing floating-point reassociation changes results; see [#12, section 3.2](/posts/strength-reduction-arithmetic/).

The cost is inlining. GCC won't inline functions with different optimization options into each other: a function inside the region calling a small function outside it, or the other way round, measurably turns even a one-line `static inline` function into a real `call`. The hot path is full of such small functions, reading a field or computing an index, so wrapping it in the macro can make it slower. GCC's documentation is blunt about the `optimize` attribute: it's meant for debugging and isn't suitable for production code. For more aggressive options, set compiler flags for the whole file or build target.

### 3.2 `HPC_ALIGN`: The Standard Already Has `alignas`

`HPC_ALIGN(N)` expands to `__attribute__((aligned(N)))` or `__declspec(align(N))` depending on the compiler. Since C++11 the standard has `alignas(N)`, which all three compilers accept, so no macro is needed. For what cache-line alignment buys you, see [#6](/posts/alignment-layout-cache-dram-geometry/).

### 3.3 `bit_cast_ref`: Named bit_cast, Does a Pointer Cast

Helpers like this are often described as a "type-safe replacement for `reinterpret_cast`", but the body is a `reinterpret_cast` followed by a dereference: reading memory of type `From` through a reference of type `To`, which is exactly the broken pattern from 1.3, and having bit_cast in the name doesn't make it safe. To convert bits, use `std::bit_cast` (for a value) or `memcpy`. When all you want is a pointer, `reinterpret_cast` itself is legal; you just can't use the resulting pointer to read or write an object that isn't of that type.
