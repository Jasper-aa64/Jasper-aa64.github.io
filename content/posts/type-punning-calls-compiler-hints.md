---
title: "Trading System Notes #13: Type Punning, Function Calls, and Compiler Hints"
date: 2026-10-15
lastmod: 2026-11-19
slug: "type-punning-calls-compiler-hints"
description: "The compiler assumes memory of different types never overlaps: when bytes from a receive buffer or the bits of a double are read as another type, a pointer cast can read a stale value, while memcpy, std::bit_cast and C++23's std::start_lifetime_as are correct and cost nothing. When a call can't be inlined, arguments go by the calling convention, small by value and large by const&, and the compiler already turns tail recursion into a loop; when it can, the compiler decides whether to expand it, the inline keyword is about linking, and per-function optimization options block inlining; last, the four parts of inline assembly. Assembly is measured with GCC 16 -O2 on x86-64."
summary: "How far the compiler can optimize depends on what it dares to assume and what it can see: different types are treated as non-overlapping, so reading bytes as another type takes memcpy or bit_cast; an invisible function body means arguments go by the calling convention, and whether to expand a call is its own estimate, which decisions made for it don't always improve."
chapter: 1
categories: [Systems]
tags: [cpp, type-punning, strict-aliasing, bit-cast, calling-convention, compiler-optimization, hft, low-latency]
toc: true
math: true
light: true
---

How far the compiler can optimize depends on what it dares to assume and what it can see. The two sections of this post take one each:

- **The compiler assumes pointers of different types never point to the same memory**: read 8 bytes of a receive buffer as a `double`, or change the bits of a `double` as an integer, through a pointer cast, and the compiler optimizes on that assumption and may hand back a stale value (Section 1).
- **When the compiler can't see a function body, it passes arguments by the calling convention and assumes the worst**: by value versus by reference costs a few instructions and can block optimizations. When it can see the body, whether to expand the call is its own estimate; decisions made for it, such as `always_inline` or per-function optimization options, sometimes make the code slower (Section 2).

## 1. Type Punning and Strict Aliasing: The Compiler Assumes Different Types Don't Overlap {#type-punning}

### 1.1 Type Punning: When Bytes Have to Be Read as Another Type {#punning-need}

- **An exchange's binary market data lands in a receive buffer first**: a price is 8 bytes at some offset in the buffer and has to be read as a `double`; the sequence number and length in the header are integers that also come out of the bytes.
- **Sometimes the bits themselves are what you want**: hashing a `double`, comparing as integers, or serializing means viewing a `double` as a `uint64_t`.
- **The handiest way is a pointer cast**: `*(double*)(buf + 8)`, `*(uint64_t*)&x`, or `reinterpret_cast`ing the whole header to a struct pointer. **All of these break strict aliasing, and with optimization on, the result can differ from the unoptimized build**.

### 1.2 Strict Aliasing: An Object May Only Be Accessed Through Its Own Type {#alias-rule}

1. **The rule: only a few types may read or write an object of type `T`**
   - **`T` itself, and its signed or unsigned counterpart**: `int` and `unsigned int` may access each other, with or without `const` and `volatile`.
   - **`char`, `unsigned char` and `std::byte` may access any object**: this is the opening left for looking at memory as bytes. `uint8_t` is `unsigned char`.
   - **Access through any other type is undefined behavior**: the compiler doesn't have to warn, and the result can change with the optimization level.

2. **From the rule, the compiler concludes that two pointers of different types never point to the same object**
   - **This is the same kind of information as `__restrict` in [#10](/posts/pointer-memory-access/)**: the difference is that you don't write it; the compiler infers it from the types.
   - **With it, values can stay in registers**: after a store through a `uint64_t*`, the compiler needn't worry that some `double` changed and doesn't reload it; loop bounds and coefficients can be hoisted out of the loop, which is what lets the loop vectorize.
   - **Writing through `char*` or `uint8_t*` is the reverse case**: byte types may access any object, so after one such store the compiler has to assume any other variable may have changed and reload it. Byte-pointer stores in a hot loop make the compiler conservative about every other pointer: in a loop that doubles `a[k]` up to a bound `*n`, changing `float* a` to `char* a` makes the compiler reload `*n` every iteration and give up on vectorizing.

### 1.3 Breaking Strict Aliasing: A Pointer Cast Reads a Stale Value {#alias-violation}

1. **Point a `uint64_t*` at a `double`, and the compiler still optimizes on "no overlap"**

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

   - **After `*u = 0`, `*d` isn't reloaded**: the compiler assumes `u` can't change `d` and returns the 1.0 already in a register.
   - **Called as `alias(&x, (uint64_t*)&x)`, it measurably returns 1 while memory already holds 0**: with `-fno-strict-aliasing` turning the assumption off, it reloads before the `return` and returns 0. The Linux kernel is built with the rule turned off entirely, at the price of all the optimizations from 1.2.

2. **A cast inside one function sometimes happens to work**
   - **After `double x = 100;`, write `*(uint64_t*)&x |= 0x8000000000000000;`**: with GCC `-O2`, printing `x` measurably gives −100, because both pointers come from `&x` and the compiler can see that this time.
   - **The compiler warns on that same line, `'x' is used uninitialized`**: as far as it's concerned, the memory read as a `uint64_t` was never written. It works only because the compiler happened to see through it; put a function boundary in between and you get `alias` above.

3. **Reading another union member, or a helper named bit_cast, is the same problem**
   - **Write one union member, read another**: C allows it; in C++, reading a member other than the one last written is undefined behavior. GCC's documentation explicitly supports reading through a union this way, so it works on GCC, with no guarantee on other compilers.
   - **Some projects wrap the cast in a helper**: for example `bit_cast_ref<To>(ptr)`, whose body is `*reinterpret_cast<const To*>(ptr)`. Having bit_cast in the name doesn't change what it does: reading memory of another type through `To`.
   - **`reinterpret_cast` itself is legal**: what's wrong is using the resulting pointer to read or write an object that isn't of that type. Casting a pointer and casting it back to the original type before use is fine.

### 1.4 The Legal Ways: `memcpy`, `std::bit_cast`, `std::start_lifetime_as`, Each One Load {#alias-fix}

1. **Copy the bytes into a variable of the target type: `memcpy` and `std::bit_cast`**

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

   - **The copy costs nothing**: when the length is a small compile-time constant, the compiler recognizes the copy and emits a single register-to-register move; both versions compile to the same thing.
   - **`std::bit_cast` adds compile-time checks**: both sides must have the same size and be trivially copyable, or it doesn't compile; it also works in `constexpr`. `bits_cast(100.0)` measures 0x4059000000000000, a number 1.5 takes apart.

2. **Reading fields from a receive buffer: `memcpy` again**

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

   - **`read_px` is a single 8-byte load**: an unaligned address is fine because x86 allows unaligned loads; reading from byte 3 of a buffer measurably works.
   - **Writing `*(double*)p` has two problems**: reading `char` memory through a `double` breaks strict aliasing, and a misaligned address adds another layer of undefined behavior; if the compiler relies on it and emits a vector instruction that requires alignment, the program crashes.
   - **Big-endian fields need their byte order reversed**: x86 is little-endian, with the low byte at the low address; some exchange protocols send integers big-endian (network byte order), Nasdaq's ITCH for example. C++23's `std::byteswap` compiles to one `bswap`.

3. **Using a whole struct in place without copying: C++23's `std::start_lifetime_as`**

   ```cpp
   struct Header { uint32_t seq; uint16_t len; uint16_t type; };

   uint32_t seq_of(unsigned char* p) {
       return std::start_lifetime_as<Header>(p)->seq;   // from now on there is a Header at p
   }
   ```

   - **It copies no bytes and runs no constructor**: it only tells the compiler that from now on a `Header` object lives in this memory, with the existing bytes as its value. Reading and writing through the returned pointer is then legal.
   - **It compiles the same as `memcpy`**: measured with GCC 16.2, `seq_of` and "`memcpy` the whole `Header` out, then take `seq`" are both a single 4-byte load.
   - **It pays off for large structs and memory someone else filled**: a market data snapshot of a few hundred bytes is tedious to read field by field with `memcpy`, and copying the whole thing out is a copy the compiler may not be able to remove; a packet DMA'd in by the NIC or a struct in shared memory is likewise "the bytes are already there, only the object is missing".
   - **There are two preconditions**: `Header` must be an implicit-lifetime type (a struct with only scalar members and no user-provided destructor, like `Header`, is one), and `p` must be aligned to `alignof(Header)`; an unaligned address still needs `memcpy`.
   - **Check the standard library before using it**: look for the `__cpp_lib_start_lifetime_as` macro; libstdc++ in GCC 16.2 defines it.

### 1.5 IEEE 754: Sign, Exponent, Mantissa, and No Need to Touch Bits to Change the Sign {#ieee754}

- **A double is 8 bytes, 64 bits, split by IEEE 754 into three fields**: the top bit is the sign, the next 11 bits are the exponent, and the remaining 52 bits are the mantissa. The value is:

$$x = (-1)^{s} \times 1.f \times 2^{\,e - 1023}$$

- **There's an implicit 1 in front of the mantissa that isn't stored**: only the part of $1.f$ after the point is stored.
- **The exponent is stored with 1023 added (the bias)**: so no negative numbers need to be stored.
- **Example: 100 is stored as 0x4059000000000000**: $100 = 1.5625 \times 2^{6}$, so the sign stores 0; the exponent stores $6 + 1023 = 1029$, i.e. 0x405; 1.5625 is 1.1001 in binary, so the mantissa stores the 1001 after the point, followed by zeros.

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
      :root:is([data-theme="dark"], [data-theme="black"]) .fbg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fs { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fe { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fm { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ink { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .bits { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .muted { fill: #a19caf; }
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

- **The sign has the top bit to itself, so changing only that bit negates the value**: set bit 63, leave the rest alone, and you get −100, 0xC059000000000000 in hex.
- **A float has the same structure**: 1 + 8 + 23 bits and a bias of 127. 2.0f is 0x40000000; setting bit 31 gives 0xC0000000, which is −2.0f.
- **To negate or take an absolute value, just write the math**: the compiler turns it into a bit operation itself.

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

- **`-std::fabs(x)` is "set the top bit"**: one `orpd`, and the value stays in a floating-point register.
- **Changing the bit yourself with `bit_cast` costs two more instructions**: `std::bit_cast<double>(std::bit_cast<uint64_t>(x) | 0x8000000000000000)` measurably compiles to three, `movq` into an integer register, `btsq` to set the bit, and `movq` back.
- **When there's a plain math form, write the math**: keep the techniques of 1.4 for data that really is bytes, or when the bits themselves are what you want.

### 1.6 The Other Use of a Union: `std::variant` Remembers Which Type It Holds {#variant}

- **A union can also hold one of several types in one slot, to save memory**: a market data message might be a new order, a cancel or a trade, each with different fields, kept in the same memory with a union.
- **The trouble is that a union doesn't remember which one it currently holds**: reading the wrong member is the punning of 1.3 again.
- **C++17's `std::variant` stores an extra index that records the current type**:

```cpp
union U3 { int i; float f; std::array<char, 16> a; };    // 16 bytes
using V3 = std::variant<int, float, std::array<char, 16>>; // 20 bytes
```

- **The variant costs a few bytes**: the measured `sizeof` values are 16 and 20; the variant adds a 1-byte index, padded to 4-byte alignment.
- **Asking for the wrong type throws**: `std::get<int>(v)` throws `std::bad_variant_access` when `v` doesn't hold an `int`.
- **Dispatching on the current type is `std::visit`**:

```cpp
std::variant<int, float> v{42};
std::visit([](auto&& x) { std::cout << x << '\n'; }, v);
```

- **`std::visit` makes no virtual call**: it compiles to reading the index, comparing, and jumping to the matching branch, like a hand-written `switch`. For `std::variant<int, float, double>` the visit measures one `movzbl` to read the index plus two `cmp`s.

## 2. Function Calls and Inlining: Passing Arguments When the Body Is Invisible, and Who Decides to Expand It When It Isn't {#calls}

### 2.1 The Calling Convention: Arguments Go in Registers First {#calling-convention}

- **When a function is inlined, it doesn't matter how arguments are passed**: the compiler expands the body right at the call site.
- **Some calls can't be inlined**: the function is defined in another file or a library, it's called through a function pointer or a virtual function, it's recursive, or it's too big for the compiler to want to expand.
- **Then the arguments are laid out by the calling convention**: Linux x86-64 uses the System V convention, where the first 6 integer or pointer arguments go into `rdi`, `rsi`, `rdx`, `rcx`, `r8` and `r9`, the first 8 floating-point arguments into `xmm0`–`xmm7`, and only the rest go on the stack.
- **The return value goes in `rax` or `xmm0`**: a large return value uses the hidden address covered in [#11](/posts/rvo-pure-functions/).

### 2.2 Small by Value, Large by `const&` {#pass-by}

1. **Passing an `int` by reference adds a memory operation on each side of the call**

   The functions below are marked `noinline` to stand in for calls that can't be inlined:

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

   - **By value, the value sits in a register**: `use_val` computes straight from `%edi`, and once `call_val` has computed `a + 1`, the argument is already in place, so a single `jmp` gets there.
   - **By `const int&`, what goes in is an address**: `use_ref` first has to load from memory, and `call_ref` first has to make room on the stack and store `a + 1` there to have an address to pass.

2. **Structs: up to 16 bytes are split across registers; anything bigger is copied onto the stack**

   ```cpp
   struct Small { double px; int64_t qty; };              // 16 bytes
   struct Big   { double px; int64_t qty; int64_t id; };  // 24 bytes
   ```

   - **`f_small(Small)` receives its two fields in `xmm0` and `rdi`**: a trivially copyable struct of up to 16 bytes passed by value is split across two registers.
   - **`f_big(Big)` reads its fields from the stack**: measured, the caller first builds a 24-byte copy there.
   - **So pass small things by value and expensive-to-copy things by `const&`**: scalars, iterators, `std::string_view` and `std::span` go by value; `std::vector` and large structs, which are expensive to copy and don't fit in registers, go by `const&`.

### 2.3 `const&` Also Blocks Optimization: The Compiler Must Assume It Changes {#const-ref-alias}

- **The referenced value may be changed by other stores**: in the scaling function below, when `f` is passed by reference it might point at an element of `v`, so any write to `v[i]` might change `f`, and it has to be reloaded every iteration.

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

- **The extra load usually hits L1 and isn't expensive by itself**: but it shows the compiler won't treat `f` as unchanging.
- **At `-O3`, to vectorize, the loop first gets versioned**: GCC's report says the loop was "versioned for vectorization because of possible aliasing": it inserts a check of whether `f` and `v` overlap and takes the slow copy if they do. `scale_val` has no such step.
- **This is the problem from 1.2, except the types don't help**: strict aliasing lets the compiler rule out overlap by type, but `f` and `v` are both `double`, so only passing by value (or `__restrict`) lets it be sure they don't overlap.

### 2.4 Recursion: The Compiler Turns Tail Calls into Loops Itself {#tail-call}

- **Recursion can't be inlined**: the function calls itself, and expanding one level leaves another. Every call leaves a return address on the stack and saves registers, and recursion that goes too deep runs out of stack.
- **The compiler removes the overhead of tail calls itself**: when calling itself is the last thing a function does (a tail call), nothing is left to do after it returns, so GCC turns the call into a jump. In a preorder traversal, the call for the right subtree is a tail call:

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

- **GCC also unrolled the recursion several levels deep**: so rewriting tail recursion as a loop by hand mostly repeats the compiler's work.
- **To remove recursion entirely, use an explicit stack backed by a fixed-size array**: not `std::stack`, which sits on `std::deque` and allocates.
- **For walking a tree, the call overhead often isn't the main cost**: every step waits for the next node to come back from memory, the pointer chasing covered in [#10](/posts/pointer-memory-access/), and when a node isn't in cache, a step costs a full memory latency.

### 2.5 `inline`: The Keyword Is About Linking, Not Inlining {#inline}

The sections so far were about calls that can't be inlined. The other way round, when a call can be inlined (expanded), it doesn't matter how arguments are laid out. But what decides whether it gets expanded isn't the `inline` keyword. **`inline` has two meanings sharing one word: one is a language rule that always applies; the other is a hint the compiler is free to ignore**.

1. **The first meaning: the same definition may appear once in each of several `.cpp` files**
   - **A function defined in a header and included by two `.cpp` files gives the linker two definitions of the same name**: the linker reports `multiple definition`, because it doesn't know which one to keep.
   - **Marking it `inline` tells the linker these are all the same definition and one copy is enough**: with the same header, GCC 16 measurably fails to link without `inline` and links with it.
   - **Member functions with their body written inside the class, and function templates, are implicitly `inline`**: which is why header-only libraries link.
   - **C++17's `inline` variables extend the rule to global variables**: write `inline int counter = 0;` in a header and every `.cpp` uses the same object; measured, two `.cpp` files get the same address. Before that, you wrote an `extern` declaration in the header and picked one `.cpp` for the definition.

2. **The second meaning: a suggestion to replace the call with the body, which the compiler decides on by its own estimate**
   - **Expansion saves more than the call itself**: arguments don't have to be laid out by the convention from 2.1, and there's no `call` or `ret`. More valuable, after expansion the body and the call site are optimized together: constants propagate in, branches get removed, loops get vectorized.
   - **From `-O2` up, the compiler decides by its own cost estimate**: small functions not marked `inline` get expanded anyway, and large ones marked `inline` don't. A function whose body it can't see is never expanded, for example one defined in another `.cpp` without LTO.
   - **So the same function can "need `inline`, yet not be expanded"**: the two meanings are independent.

3. **To make the compiler do what you say: `always_inline`, `flatten`, and the opposite, `noinline`**
   - **`__attribute__((always_inline))`**: the function must be expanded at every call site. Use it on small functions that profiling shows the compiler misjudged.
   - **`__attribute__((flatten))`**: expand the functions this one calls, and theirs, as far as possible. Use it on a small, hot call chain.
   - **`noinline` plus `cold`**: move rarely taken error handling out of a hot function ([#7](/posts/branch-prediction-branch-optimization/)); what it saves is instruction cache.
   - **All of these are GCC and Clang extensions, not standard C++**.

4. **Per-function optimization options block inlining: `#pragma GCC optimize`**

   ```cpp
   #define HPC_FAST_BEGIN _Pragma("GCC push_options") \
   _Pragma("GCC optimize (\"O3,unroll-loops,associative-math,no-signed-zeros\")")
   #define HPC_FAST_END _Pragma("GCC pop_options")
   ```

   - **Projects often have a pair of macros like this, compiling the functions between them with `-O3`, loop unrolling, and associativity for floating-point addition**: the effect is real; a float sum loop inside measurably compiles to `addps` vector additions, while the same loop outside is `addss`, one addition at a time. Allowing floating-point reassociation changes results; see [#12, section 3.2](/posts/strength-reduction-arithmetic/).
   - **The cost is inlining: GCC won't inline functions with different optimization options into each other**: a function inside the region calling a small function outside it, or the other way round, measurably turns even a one-line `static inline` function into a real `call`.
   - **The hot path is full of such small functions, so wrapping it in the macro can make it slower**: reading a field or computing an index each costs a call, and the constant propagation and branch removal that expansion would have enabled are gone.
   - **GCC's documentation is blunt about the `optimize` attribute: it's meant for debugging and isn't suitable for production code**: for more aggressive options, set compiler flags for the whole file or build target.

5. **Expanding too much makes hot code slower: instructions take up cache too**
   - **L1i is only about 32 KiB and holds instructions by cache line**: error handling expanded into a hot function sits between the hot instructions even if it never runs, pushing frequently run code out of L1i.
   - **So verify forced expansion with perf**: look at total time, then at whether L1i misses (`L1-icache-load-misses`) went up.

### 2.6 Inline Assembly: Only for the Few Instructions C++ Can't Express {#inline-asm}

1. **Don't write it if you can avoid it**
   - **The compiler can't see into an asm block**: constant propagation and register allocation stop at its boundary.
   - **Most needs already have a ready-made form**: SIMD has intrinsics ([#15](/posts/simd-vectorization-intrinsics/)), reading the TSC has `__rdtsc()`, and prefetching has `__builtin_prefetch`.

2. **The GNU syntax has four parts separated by colons: instructions, outputs, inputs, and what gets clobbered**

   ```cpp
   static inline uint64_t rdtsc() {
       uint32_t lo, hi;
       asm volatile("rdtsc" : "=a"(lo), "=d"(hi));   // outputs: eax → lo, edx → hi
       return (uint64_t)hi << 32 | lo;
   }
   ```

   - **Constraints tell the compiler which register holds a value**: `"=a"` is `eax`, `"=d"` is `edx`, and `=` means write-only. This function reads the same counter as `__rdtsc()` ([#20](/posts/tsc-latency-measurement/)).
   - **Leave out the fourth part and the compiler assumes those registers are unchanged**: the result is wrong, with no error.
   - **Writing `"memory"` in the fourth part says the block reads or writes memory**: the compiler can't move loads and stores across it. With no instructions at all, `asm volatile("" ::: "memory")` is the usual compiler barrier.
   - **`volatile` keeps the compiler from removing or merging the block**: reading the TSC gives a different result every time and can't be treated as a computation without side effects.

3. **When mixing AVX and legacy SSE instructions, put a `vzeroupper` before switching**
   - **Without it, the CPU has to save and restore the upper halves of the vector registers**: tens of cycles each time.
   - How to spot it in perf and fix it: see the card {{% bottleneck-ref "missing-vzeroupper" %}}.
