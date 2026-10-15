---
title: "Trading System Notes #12: Strength Reduction and Arithmetic Optimization"
date: 2026-10-15
slug: "strength-reduction-arithmetic"
description: "An integer division takes 10–90 cycles; an addition takes 1. Constant multiplies and divides, powers of two and repeated expressions are rewritten into cheaper forms by the compiler itself; a divisor known only at run time, a value only you know is never negative, and floating-point rewrites that change the result are yours to handle. The post ends with why prices are stored as integers. Assembly is measured with GCC 16 -O2 on x86-64."
summary: "The compiler only makes rewrites it can prove don't change the result, and it does constant multiplies and divides better than you. What's left for you is where it lacks information or where the rewrite changes the result: run-time divisors, signs, floating point. Integer prices are exact and fast."
chapter: 1
categories: [Systems]
tags: [cpp, strength-reduction, integer-division, floating-point, fixed-point, hft, low-latency]
toc: true
math: true
light: true
---

The hot path for market data and orders is full of small arithmetic: divide a price by the tick size to get a tick count; take a ring buffer index modulo its capacity to wrap around; multiply a notional by a fee rate. Each line has a single operator, yet the CPU time differs widely: an integer addition takes 1 cycle, an integer division 10–90 cycles.

Replacing an expensive operation with a cheaper one that gives the same result is called **strength reduction**. Compilers do this all the time, but only where they can prove the result is unchanged. So the places that need you are exactly the ones the compiler can't prove: the divisor is known only at run time, a value can never be negative but only you know it, or the rewrite really does change a floating-point result.

## 1. Operation Latency: Why Division Is Expensive

To judge whether a rewrite is worth it, you first need to know how far apart the operations are. They all happen in the execution units in the back end of the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a>: the operands are already in registers, there's no memory access, and the only difference is how long an execution unit takes to compute one result. There's more than one kind of unit: additions, subtractions and bit operations run on the ALU (arithmetic logic unit), while multiplication, division and floating point each have their own circuits. The time from starting an operation to having its result usable (latency) is roughly:

| Operation | Latency |
|---|---|
| Integer add/subtract, bit operations, shifts | 1 cycle |
| Integer multiply | 3 cycles |
| Floating-point add/subtract, multiply | 3–5 cycles |
| Floating-point divide, square root | 10–20 cycles |
| Integer divide, remainder | 10–90 cycles |

An addition finishes in one cycle. A multiplication has to add up several rows of partial products, and the hardware splits that into three pipelined steps: as soon as one step finishes it can take the next multiplication, so a multiply waits 3 cycles for its result but a new one can start every cycle. Division can't be split like that. The quotient has to be found round by round, each round uses the remainder left by the previous one, and each round produces only a few bits. A 64-bit division needs more bits than a 32-bit one, so it takes more rounds; recent chips produce more bits per round and are much faster, which is why the range is so wide. The divider also can't accept a new division every cycle the way the multiplier can: until the previous one finishes, later divisions mostly have to wait. A loop that divides every element stays slow even when the elements don't depend on each other.

So the operations most worth replacing are division and remainder, then multiplication.

## 2. What the Compiler Rewrites Itself: Constant Multiplies and Divides, Powers of Two, Repeated Expressions

When the multiplier or divisor is a compile-time constant, the replacement is fixed, the compiler can prove the result is unchanged, and at `-O2` it does the rewrite itself. The assembly below is the actual output of GCC 16 `-O2` on x86-64: the first argument arrives in `%edi` (its 64-bit name is `%rdi`) and the result goes in `%eax`.

### 2.1 Multiplying by a Constant: `lea`, a Shift, or One `imul`

```cpp
int mul8(int x)   { return x * 8; }
int mul5(int x)   { return x * 5; }
int mul100(int x) { return x * 100; }
```

```text
mul8(int):
    leal    0(,%rdi,8), %eax      # x * 8
    ret
mul5(int):
    leal    (%rdi,%rdi,4), %eax   # x + x * 4
    ret
mul100(int):
    imull   $100, %edi, %eax
    ret
```

`lea` (load effective address) is an instruction for computing addresses. Addresses are often written as "base + index × 1, 2, 4 or 8", and the CPU has a dedicated circuit that computes that in one step, so the compiler borrows it to multiply by small constants such as 2, 3, 4, 5, 8 and 9 in 1 cycle. Multiplying by 100 would take several shifts and adds, which is worse than one 3-cycle `imul`, so the compiler just multiplies. Inside a loop, an `i * 10` computed every iteration is also turned into adding 10 each iteration; that's the kind of strength reduction covered in [#9, section 2.2](/posts/loop-optimization/).

So writing `x << 3` or `x + x + x` by hand gains nothing, since the compiler already picks the cheapest form. Hand-written shifts also invite a precedence bug: `x << 1 + 2` is `x << 3`, because the addition binds first.

### 2.2 Dividing by a Constant: Multiply by a "Magic Number", Then Shift

Division by a constant can also become a multiplication. Dividing by 100 is multiplying by $\frac{1}{100}$; integers just don't have fractions. The trick is to scale $\frac{1}{100}$ up by $2^{37}$, round it up and store it as an integer $M$; after multiplying, shift right by 37 bits to divide the scale back out:

$$\left\lfloor \frac{x}{100} \right\rfloor = \left\lfloor \frac{x \cdot M}{2^{37}} \right\rfloor, \qquad M = \left\lceil \frac{2^{37}}{100} \right\rceil = 1374389535$$

With a large enough scale, the small error from rounding up never makes any 32-bit $x$ come out wrong; the compiler picks a big enough shift for each divisor.

```cpp
unsigned udiv100(unsigned x) { return x / 100; }
```

```text
udiv100(unsigned int):
    movl    %edi, %eax
    imulq   $1374389535, %rax, %rax   # x * M
    shrq    $37, %rax                 # shift right by 37
    ret
```

One multiply and one shift, about 4 cycles (3 + 1), replace a 10–90 cycle division. The remainder works the same way: $x \bmod 100 = x - 100 \cdot \lfloor x / 100 \rfloor$, one more multiply and one subtraction. The condition is that the divisor is known at compile time, because the magic number is computed from it.

### 2.3 Powers of Two: One Instruction Unsigned, a Fix-Up When Signed

When the divisor is a power of two it's even simpler: dividing by 4 is a right shift by 2, and the remainder modulo 512 keeps only the low 9 bits, i.e. an AND with 511. That's exactly what the compiler does for unsigned numbers, but signed numbers get a few extra instructions:

```cpp
unsigned udiv4(unsigned x)   { return x / 4; }
unsigned umod512(unsigned x) { return x % 512; }
int sdiv4(int x)             { return x / 4; }
```

```text
udiv4(unsigned int):
    movl    %edi, %eax
    shrl    $2, %eax
    ret
umod512(unsigned int):
    movl    %edi, %eax
    andl    $511, %eax
    ret
sdiv4(int):
    testl   %edi, %edi
    leal    3(%rdi), %eax
    cmovns  %edi, %eax        # use x if it isn't negative, x + 3 if it is
    sarl    $2, %eax
    ret
```

The extra instructions are there for negative numbers, where a right shift and a division give different results. C++ integer division rounds toward zero, so `-7 / 4` is `-1`; a right shift rounds toward negative infinity, so `-7 >> 2` is `-2`. The compiler therefore adds 3 to negative values before shifting. The remainder is the same story: `-1 % 512` is `-1`, but `-1 & 511` is `511`, so a signed `x % 512` compiles to 6 instructions.

For values that are never negative, such as indices and quantities, use an unsigned type and you're left with a single `shr` or `and`. If the type can't change, C++23 lets you write `[[assume(x >= 0)]]` to tell the compiler, and `sdiv4` measurably drops to a single `sar`. Like the pure-function attributes in [#11](/posts/rvo-pure-functions/), it's a promise you make to the compiler: get it wrong and it's undefined behavior.

### 2.4 Common Subexpressions and Constant Folding: Redundant Work Is Deleted

Besides making operations cheaper, the compiler deletes redundant ones. An expression written several times is computed once, which is called **common subexpression elimination** (CSE): `(i * i) + (i * i) + sqrtf(i * i)` compiles to a single `imull`. An expression made only of constants is computed at compile time, which is called **constant folding**: `float scale = sqrt(2.0) * 3.14159;` compiles to a ready-made number, with no square root and no multiply at run time. Boolean algebra too: `(a && b) || (a && c)` and `a && (b || c)` compile to identical code. None of this needs rewriting by hand. What `constexpr` adds is a guarantee that the value is computed at compile time; at `-O2` it isn't any faster.

Constant multiplies and divides, powers of two and repeated expressions are all handled better by the compiler than by hand; hand-written shifts buy no speed and only make the code harder to read.

## 3. What You Have to Rewrite: Missing Information, or a Changed Result

The compiler stops in two kinds of places: where it lacks information the rewrite needs, or where the rewrite really changes the result.

### 3.1 A Divisor Known Only at Run Time: `div` Stays

The magic number is computed from the divisor. When the divisor is known only at run time, say a queue capacity read from a config file, the compiler can't compute it ahead of time and has to emit a `div`:

```cpp
unsigned wrap_mod_n(unsigned x, unsigned n) { return (x + 1) % n; }
```

```text
wrap_mod_n(unsigned int, unsigned int):
    leal    1(%rdi), %eax
    xorl    %edx, %edx
    divl    %esi              # 10–90 cycles
    movl    %edx, %eax        # the remainder is in %edx
    ret
```

The only way to get rid of it is to design the division away.

**Make the capacity a power of two.** With a capacity of $2^k$, `idx % cap` can be written `idx & (cap - 1)`, which is a single `and` even when the capacity is set at run time. The [ring buffer in #4](/posts/lock-free-queue-logger-micro-batching/) rounds its capacity up to a power of two and stores `mask_ = capacity - 1` for exactly this reason.

**Wrap with a comparison.** When the index only ever grows by 1, `x = (x + 1) % N` can be written `x = (x == N - 1) ? 0 : x + 1`. The compiler won't do this by itself: the two are equal only when $0 \le x < N$, and only you know that. Even with a constant $N$ the two forms differ quite a bit:

```cpp
int wrap_mod(int x) { const int N = 100; return (x + 1) % N; }
int wrap_cmp(int x) { const int N = 100; return (x == N - 1) ? 0 : x + 1; }
```

```text
wrap_mod(int):
    addl    $1, %edi
    movslq  %edi, %rax
    movl    %edi, %edx
    imulq   $1374389535, %rax, %rax
    sarl    $31, %edx
    sarq    $37, %rax
    subl    %edx, %eax
    imull   $100, %eax, %edx
    movl    %edi, %eax
    subl    %edx, %eax
    ret
wrap_cmp(int):
    xorl    %edx, %edx
    leal    1(%rdi), %eax
    cmpl    $99, %edi
    cmove   %edx, %eax        # becomes 0 when x == 99
    ret
```

`% 100` has already become a magic-number multiply, but it needs two multiplies with shifts and subtractions around them, each waiting for the last, about 11 cycles (1 + 1 + 3 + 1 + 1 + 3 + 1). In the comparison form, the increment and the compare run at the same time, followed by one `cmove`: about 2 cycles. There's no branch to mispredict either: `cmove` picks one of two values by a condition without jumping, the conditional move covered in [#7](/posts/branch-prediction-branch-optimization/).

**Reuse the same divisor.** Some divisors are known only at run time but never change once set, such as each instrument's tick size, read once at startup. Compute the magic number for it at startup, and every later division is a multiply and a shift. [libdivide](https://libdivide.com/) is a library that does exactly this.

### 3.2 Floating Point: The Rewrite Changes the Result

Floating-point division is slow too, and `g / 100.0f` looks like it could become `g * 0.01f`, yet the compiler doesn't do it:

```cpp
float fdiv100(float g) { return g / 100.0f; }
float fdiv4(float g)   { return g / 4.0f; }
```

```text
fdiv100(float):
    divss   .LC0(%rip), %xmm0    # .LC0 = 100.0f, still a division
    ret
fdiv4(float):
    mulss   .LC1(%rip), %xmm0    # .LC1 = 0.25f, now a multiplication
    ret
```

The difference is in the constant. Floating-point numbers are binary; 0.25 is $2^{-2}$ and stored exactly, so dividing by 4 and multiplying by 0.25 give identical results, and the compiler rewrites it. 0.01 is a repeating fraction in binary, so `0.01f` holds only the nearest representable value, and multiplying by it doesn't always round the same way as dividing by 100: for `g = 5`, `g / 100` gives 0.0500000007, the float nearest to 0.05, while `g * 0.01f` gives 0.049999997, off in the last bit. Among the integers 1 to 10000, 2669 differ like this.

The same reason blocks factoring. For integers, the compiler turns `a * x + a * y` into `a * (x + y)` and saves a multiply; for floats it doesn't, because every multiply and add rounds, and multiply-then-add rounds in different places from add-then-multiply, so the results can differ in the last bit:

```cpp
int   ifactor(int a, int x, int y)       { return a * x + a * y; }
float ffactor(float a, float x, float y) { return a * x + a * y; }
```

```text
ifactor(int, int, int):
    leal    (%rdx,%rsi), %eax    # x + y
    imull   %edi, %eax           # one multiply
    ret
ffactor(float, float, float):
    mulss   %xmm0, %xmm1         # a * x
    mulss   %xmm2, %xmm0         # a * y
    addss   %xmm1, %xmm0
    ret
```

`-ffast-math` allows these rewrites, and with it `g / 100.0f` becomes a multiplication too. But it applies to the whole file and also assumes the program never sees NaN or infinity: with it on, `std::isnan(px)` measurably compiles to `return false`, and the line that checks for bad prices is simply gone. So write floating-point rewrites by hand only where you accept the small error. The most common case is a loop that divides every element by the same number: compute the reciprocal first, then multiply:

```cpp
void process(float* v, int n) {
    for (int i = 0; i < n; i++) v[i] /= sqrtf(3.14159f);    // one division per element
}
void process_optimized(float* v, int n) {
    const float scale = 1.0f / sqrtf(3.14159f);             // computed at compile time
    for (int i = 0; i < n; i++) v[i] *= scale;              // only multiplications left
}
```

In both functions `sqrtf(3.14159f)` is computed at compile time, but the loop in `process` still uses `divps` (four divisions at once); only `process_optimized` turns it into `mulps`. The cost is that results can differ from the division in the last bit. In [#9, section 4.3](/posts/loop-optimization/), BatchNorm computing `1.0f / sqrtf(var + eps)` first and then multiplying makes the same trade.

One more case where the result changes and the compiler can't save you the work: mixing float and double.

```cpp
float mix_double(float x) { return x * 3.14159; }    // 3.14159 is a double
float pure_float(float x) { return x * 3.14159f; }
```

```text
mix_double(float):
    cvtss2sd  %xmm0, %xmm0       # float to double
    mulsd     .LC4(%rip), %xmm0
    cvtsd2ss  %xmm0, %xmm0       # back to float after the multiply
    ret
pure_float(float):
    mulss     .LC5(%rip), %xmm0
    ret
```

Without the `f`, `3.14159` is a double, closer to the true 3.14159 than `3.14159f`. By the rules, `x` is converted to double, multiplied, and the product rounded back to float, which can differ in the last bit from multiplying by `3.14159f` directly, so the compiler can't drop the two conversions; they're still there with `-ffast-math`. If float precision is what you want, write `3.14159f`. An all-constant expression like `sqrt(2.0) * 3.14159` in 2.4 is computed at compile time and hides this cost; only when the multiplicand is a variable do you pay two extra conversions every time.

## 4. Integer Prices: Exact, and Fast

Floats being inexact hurts most with prices. Prices are decimal, and numbers like 0.29 or 19.99 can't be stored exactly in binary. Converting a double price to an integer number of cents by truncation can come out 1 short:

```cpp
double px = 0.29;
int cents = (int)(px * 100);    // 28: px * 100 is 28.999999999999996
```

Of the 10000 prices from 0.00 to 99.99, 573 come out 1 short this way; writing `px / 0.01` is worse, with 1076. Conversion has to round to the nearest integer: `std::llround(px * 100)` gives 29.

The more thorough fix is to store prices as integers from the start, in cents or ticks, as `int64_t`. Additions and comparisons are 1-cycle integer operations, and they're exact:

```cpp
int64_t price_cents = 1999;               // 19.99
int64_t total_cents = price_cents * 5;    // 9995, exact
```

The same calculation in float stores `19.99f` as 19.9899998 and gives 99.9499969 after multiplying by 5. Integer prices are split into dollars and cents only for display, and since `total_cents / 100` and `% 100` divide by constants, the compiler turns them into multiplications, off the hot path anyway.
