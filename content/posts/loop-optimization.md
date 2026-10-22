---
title: "Trading System Notes #9: Loop Optimization"
date: 2026-10-12
slug: "loop-optimization"
description: "There are a dozen loop transformations, and GCC does most of them by itself at -O3. This post groups them by why a loop is slow (redundant work per iteration, dependences between iterations, memory access pattern): what the compiler already does (hoisting, strength reduction, rotation, unrolling, unswitching), what blocks it (floating-point sums can't be reordered, pointers may alias, calls aren't inlined), what it won't do for you (multiple accumulators, tiling, multiplying by a reciprocal), and how to check with -fopt-info. All assembly is real GCC 13 output."
summary: "A dot-product loop reports “vectorized” at -O3, yet its four additions still wait on each other: floating-point addition isn't associative, so the compiler won't reorder it. What loop optimization really asks of you is to spot what blocks the compiler, and to make the changes it won't make for you."
chapter: 1
categories: [Systems]
tags: [cpp, loop-optimization, vectorization, simd, compiler-optimization, hft, low-latency]
toc: true
math: true
light: true
---

Start with a dot product:

```cpp
float dot(const float* v1, const float* v2, int n) {
    float sum = 0.0f;
    for (int i = 0; i < n; i++) sum += v1[i] * v2[i];
    return sum;
}
```

Compile it with GCC 13 `-O3 -fopt-info-vec` and the report says `loop vectorized using 16 byte vectors`. Now open the assembly and look at the loop body:

```text
.L4:
    movups  (%rcx,%rax), %xmm1      # load 4 of v1
    movups  (%rsi,%rax), %xmm3      # load 4 of v2
    addq    $16, %rax
    mulps   %xmm3, %xmm1            # 4 multiplies at once
    addss   %xmm1, %xmm0            # the 4 additions below wait on each other
    ...shufps / unpckhps extract products 2, 3 and 4...
    addss   %xmm2, %xmm0
    addss   %xmm2, %xmm0
    addss   %xmm1, %xmm0
    cmpq    %rdi, %rax
    jne     .L4
```

The multiplies really are done four at a time, but the additions are four `addss` in a queue, each waiting for the one before. The report says "vectorized", and the loop's bottleneck hasn't moved at all.

Loop transformations have a dozen names (unrolling, peeling, interchange, rotation, fusion, fission, tiling…), and GCC does most of them by itself at `-O2` / `-O3`. Two kinds of things deserve your attention: **what blocks the compiler**, like the floating-point sum above, and **what the compiler won't do for you**, such as changing how data is walked, tiling, or changing the algorithm. Below, the transformations are grouped by the three reasons a loop is slow, followed by how to check what the compiler actually did. The assembly and `-fopt-info` output are real results from GCC 13.3 on x86-64 with the default SSE2 (one vector instruction handles 4 `float`s); "N times faster" figures are estimates from instruction latencies, not timings.

## 1. Why a Loop Is Slow: Three Reasons

A slow loop usually comes down to one of three things, and every transformation targets one of them:

- **Redundant work every iteration**: an invariant value recomputed each time, or an invariant condition tested inside the loop. Handled by hoisting, strength reduction and unswitching (part 2).
- **Dependences between iterations**: this iteration has to wait for the previous one's result. Handled by multiple accumulators and software pipelining (part 3).
- **A bad memory access pattern**: strided reads, or the same data brought in from memory again and again. Handled by interchange, tiling and fusion (part 4).

Unrolling is often said to save "the overhead of the `i < n` test and `i++`". On a modern CPU that overhead is small: `cmp` + `jne` fuse into one micro-op, and the branch is predicted correctly almost every time. Unrolling earns its keep by making room for other transformations (2.4).

## 2. Transformations the Compiler Already Does

### 2.1 Loop-Invariant Code Motion (LICM): Do It Once, Outside the Loop

Computations whose result is the same every iteration (an array length, a constant factor, a member variable) get hoisted in front of the loop and done once. `sum_crtp` in [section 1.2 of #8](/posts/crtp-static-polymorphism/) is an example: `mult` is hoisted and read only once.

Two things block it:

- **A call that isn't inlined**: the compiler can't see the body, so it can't assume the callee leaves the value alone. `sum_virtual` in #8 re-reads `mult` inside the callee every iteration.
- **Pointers that may alias**: if the loop writes through `int* q`, the compiler can't be sure it didn't write `*p`, so `*p` must be re-read every iteration (there's an example under [Reference: `const`](/ref/cpp-syntax/#const)).

### 2.2 Strength Reduction: Replace a Multiply With a Running Sum

Replacing the multiply in `a[i] = 10 * i` with an add of 10 per iteration looks like this when written by hand:

```cpp
void fill_10i(int* a, int n) {          // original
    for (int i = 0; i < n; i++) a[i] = 10 * i;
}

void fill_10i_sr(int* a, int n) {       // after strength reduction
    int x = 0;
    for (int i = 0; i < n; i++) {
        a[i] = x;                       // x is always 10 * i
        x += 10;
    }
}
```

The compiler does this step by itself. At `-O2` both functions compile to exactly the same loop, with no multiply:

```text
.L3:
    movl  %eax, (%rdi)      # a[i] = x
    addl  $10, %eax         # x += 10
    addq  $4, %rdi
    cmpl  %edx, %eax
    jne   .L3
```

`x += 10` looks like it makes each iteration depend on the previous one's `x`, so it couldn't be parallelized. It doesn't: `x` is an **induction variable** (one that changes by a fixed step every iteration), and the compiler recognizes it and knows its value in iteration i is $10i$. At `-O3` both versions vectorize, writing 4 at a time:

- `fill_10i_sr`: one register holds `{0, 10, 20, 30}`, and each iteration adds 40 to all of it (`paddd`).
- `fill_10i`: the register holds `{0, 1, 2, 3}`, each iteration adds 4, and ×10 is computed with shifts and adds: `pslld $2` (×4), `paddd` (add itself, ×5), `pslld $1` (×2).

So there's no need to write this by hand; just write `10 * i`.

### 2.3 Loop Rotation: `for` Becomes `do-while` Plus a Test in Front

```text
for (i = 0; i < n; i++) body;     →     if (0 < n) { i = 0; do { body; i++; } while (i < n); }
```

The `if` in front is the **loop guard**. After rotation, entering the `do` guarantees the body runs at least once. Only then is it safe to hoist invariant computations in front of the `do`: if `n` is 0, the original loop never runs, so the hoisted computation mustn't run either (it might read through a pointer that isn't valid). Rotation is groundwork for hoisting, and almost every loop you see in assembly has this shape: a `testl %edx, %edx; jle` up front to skip it, and the loop test at the bottom.

### 2.4 Loop Unrolling: Fewer Tests, but the Dependence Chain Stays as Long

Copy the body a few times and handle several elements per iteration, so `i < n` and `i++` run fewer times:

```cpp
float dot_unroll4(const float* v1, const float* v2, int n) {
    float sum = 0.0f;
    int i = 0;
    for (; i < n - 3; i += 4) {
        sum += v1[i] * v2[i];
        sum += v1[i+1] * v2[i+1];
        sum += v1[i+2] * v2[i+2];
        sum += v1[i+3] * v2[i+3];
    }
    for (; i < n; i++) sum += v1[i] * v2[i];   // the remaining 0-3
    return sum;
}
```

This is unrolled, but there is **only one `sum`**: the four additions still wait on each other. At `-O3` it compiles to the same shape as the plain loop at the top: the multiplies merge into `mulps`, the additions stay serial `addss`. Unrolling pays off together with multiple accumulators and vectorization (3.2); and since the compiler unrolls by itself at `-O3`, hand unrolling alone is rarely needed.

The unroll width should match the vector width: SSE handles 4 `float`s at a time, AVX / AVX2 8, AVX-512 16.

### 2.5 Loop Unswitching: Move an Invariant `if` Out of the Loop

A loop that tests a condition that doesn't change for the whole loop:

```cpp
void add_or_sub(float* a, const float* b, int n, bool do_add) {
    for (int i = 0; i < n; i++) {
        if (do_add) a[i] += b[i];
        else        a[i] -= b[i];
    }
}
```

Moving the test out and splitting into two clean loops is **loop unswitching**. Written by hand:

```cpp
void add_or_sub_unswitched(float* a, const float* b, int n, bool do_add) {
    if (do_add) {
        for (int i = 0; i < n; i++) a[i] += b[i];
    } else {
        for (int i = 0; i < n; i++) a[i] -= b[i];
    }
}
```

**`-O2` doesn't do it.** The test stays in the loop, a `testb` every iteration, one element at a time:

```text
.L5:
    movss  (%rdi,%rax), %xmm0     # load a[i]
    movss  (%rsi,%rax), %xmm1     # load b[i]
    testb  %cl, %cl               # test do_add every iteration
    jne    .L10                   # true: go to the addss side
    subss  %xmm1, %xmm0
    movss  %xmm0, (%rdi,%rax)
    ...
```

**`-O3` does it for you.** `-fopt-info-loop` reports `unswitching loop 1 on 'if' with condition: do_add`. The function tests once at the top, then splits into two loops, each vectorized:

```text
    testb  %cl, %cl               # the only test
    jne    .L3                    # true: take the add copy
    ...                           # false: take the subtract copy (same shape, subps)
.L16:                             # main loop of the add copy, 4 at a time
    movups (%rax,%rcx), %xmm0
    movups (%rsi,%rcx), %xmm3
    addps  %xmm3, %xmm0
    movups %xmm0, (%rax,%rcx)
    addq   $16, %rcx
    cmpq   %rdi, %rcx
    jne    .L16
```

Before each copy's loop, it also compares the addresses of `a` and `b`: if they overlap, it takes an element-by-element version, and only otherwise the vector one. That's the loop versioning from [section 1.2 of #10](/posts/pointer-memory-access/), a separate thing from unswitching that just happens to stack on top of it.

The branch would never have been mispredicted anyway (`do_add` doesn't change during the loop), so unswitching doesn't save mispredicts. It saves the per-iteration test and, more importantly, buys vectorization: with the test inside the loop, the compiler can hardly merge 4 iterations into one instruction. The price is a second copy of the code. Writing it by hand at `-O2` (or making `do_add` a template parameter so the split happens at compile time) removes the per-iteration test, but the loops still don't vectorize; they stay element-by-element `addss` / `subss`, because `-O2` vectorizes very conservatively (part 6). To get both, use `-O3`.

## 3. Dependence Chains: Whether Iterations Can Run in Parallel

### 3.1 Dependences Between Iterations: Only True Read-After-Write Gets in the Way

When two statements touch the same location, there are three orderings:

- **RAW (read after write, a true dependence)**: write first, read later; the later one needs the value. A cross-iteration example: `a[i] = a[i-1] * 2 + b[i]`; iteration i has to wait for iteration i-1 to produce `a[i-1]`. This chain can't be broken, so iterations can't be done together.
- **WAR (write after read)**: read first, write later, e.g. `a[i] = b[i]; b[i] = c[i];` in the same iteration; it only needs the read to happen before the write.
- **WAW (write after write)**: two writes to the same location; the final value has to be the right one.

WAR and WAW are "name conflicts": a different variable name or one extra temporary removes them. Only a cross-iteration RAW actually blocks vectorization.

### 3.2 Floating-Point Sums: the Compiler Won't Reorder, So Use Several Accumulators

In the dot product at the top, every addition waits for the previous one: a RAW chain running through the whole loop. The compiler may reorder an integer sum freely, and a `long` sum indeed vectorizes straight away at `-O3` (`paddq`). A `float` sum it may not, because floating-point addition isn't associative: `(a + b) + c` and `a + (b + c)` can round differently, and by default the compiler must not change your summation order. A floating-point add takes about 3–4 cycles, so the loop at the top spends 12–16 cycles per 4 elements.

The fix is **several accumulators**:

```cpp
float dot_acc4(const float* v1, const float* v2, int n) {
    float s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    int i = 0;
    for (; i + 3 < n; i += 4) {
        s0 += v1[i] * v2[i];
        s1 += v1[i + 1] * v2[i + 1];
        s2 += v1[i + 2] * v2[i + 2];
        s3 += v1[i + 3] * v2[i + 3];
    }
    for (; i < n; i++) s0 += v1[i] * v2[i];
    return (s0 + s1) + (s2 + s3);
}
```

The four chains are independent; the compiler packs the four accumulators into one register, and the loop body becomes one `mulps` + one `addps`. Every 4 elements now wait for a single addition, about 3–4 cycles: roughly 4 times faster, by estimate. More accumulators (say 8, two vector registers added alternately) can also fill the adder's several pipelines.

The price is a different summation order, so the result may differ in the last few bits. You accept that explicitly, which is why you write it yourself. The other route is `-ffast-math` (or just `-fassociative-math`), which lets the compiler reorder; with it the plain version at the top also becomes `addps`. But it is a switch for the whole translation unit and changes other floating-point behavior too (such as the division in 4.3), so trading systems usually don't turn it on globally.

### 3.3 Software Pipelining and MII: Throughput Is Capped by Resources or by a Dependence Cycle

**Software pipelining** overlaps neighboring iterations: iteration i is still computing while iteration i+1 has started loading. The **initiation interval** (II) is the number of cycles between the starts of consecutive iterations; the smaller, the higher the throughput. It has a lower bound, MII, set by two things:

$$
\text{MII} = \max(\text{ResMII},\ \text{RecMII})
$$

**ResMII (the resource bound)**: for each kind of execution unit, how many times an iteration uses it divided by how many such units there are, maximized over kinds:

$$
\text{ResMII} = \max_{\text{unit kinds}} \left\lceil \frac{\text{instructions of this kind per iteration}}{\text{units of this kind}} \right\rceil
$$

For example, 3 adds and 2 multiplies per iteration, with 2 adders and 1 multiplier: adds give $\lceil 3/2 \rceil = 2$, multiplies $\lceil 2/1 \rceil = 2$, so ResMII = 2.

**RecMII (the recurrence bound)**: for each cross-iteration dependence cycle, the sum of the latencies on it divided by how many iterations it spans:

$$
\text{RecMII} = \max_{\text{dependence cycles}} \frac{\text{sum of latencies on the cycle}}{\text{iterations the cycle spans}}
$$

For example `a[i] = a[i-1] * 2 + b[i]`: the cycle is "multiply, add, produce `a[i]`, used by the next iteration". Assuming a 2-cycle multiply and a 1-cycle add, RecMII = 3; ResMII is only 2, so the bottleneck is the cycle, and more execution units won't help. (The latencies are assumed to keep the arithmetic tidy; on x86 `* 2` compiles to an add or a shift, and `a[i-1]` stays in a register rather than being reloaded from memory.)

On x86 this is mostly done by the hardware: out-of-order execution keeps several iterations in flight and overlaps them automatically, so compilers rarely pipeline explicitly. The analysis is still useful, because it is the [critical path](/posts/memory-ordering-false-sharing-dependency-chains/): **to judge a loop, first find the cross-iteration dependence chain (RecMII), then count the execution units each iteration uses (ResMII); the larger is the ceiling.** The dot product in 3.2 is limited by RecMII: a single addition chain, with at least one add latency per iteration. Several accumulators split one cycle into four unrelated ones, cutting RecMII to a quarter.

## 4. Memory Access: Move the Data Fewer Times

### 4.1 Loop Interchange: the Inner Loop Should Walk Along Contiguous Memory

C++ two-dimensional arrays are stored by rows, so `m[i][j]` and `m[i][j+1]` are neighbors. An inner loop over `j` reads memory in order: every 64-byte cache line is fully used and the prefetcher keeps up. An inner loop over `i` jumps a whole row per step, each access possibly a new cache line. Swapping the loops turns the latter into the former; "walking by column is slow" in [#6](/posts/alignment-layout-cache-dram-geometry/) is exactly this. The compiler only interchanges when it can prove the result is unchanged, so usually you have to write it right.

### 4.2 Loop Tiling: Only Useful When Data Is Reused

Tiling cuts a large array into small blocks and finishes one block before the next, so the data in a block stays in cache while it is being reused. The precondition is **reuse**: matrix multiplication uses the same row and column many times; a transpose reads by rows and writes by columns, and walking by blocks keeps both the reads and the writes in cache:

```cpp
constexpr int N = 256, T = 16;
void transpose_tiled(const float* a, float* b) {
    for (int i = 0; i < N; i += T)
        for (int j = 0; j < N; j += T)
            for (int ti = i; ti < i + T; ti++)
                for (int tj = j; tj < j + T; tj++)
                    b[tj * N + ti] = a[ti * N + tj];
}
```

The `tj` loop inside a tile still writes `b` with a stride. Is that cache thrashing? No. A transpose touches each element once too; **what gets reused is the cache line, not the element**: one line of `b` holds 16 `float`s and is filled by 16 separate writes.
- **Untiled**: the inner loop over `j` writes `b[j*N+i]`, a new line every step. The second write to a given line comes only after writing a whole column of N other lines. For large N those N lines don't fit in L1; here N = 256 is only 16 KiB, but the lines are 1 KiB apart, so by set index $(\text{address} / 64) \bmod 64$ they land in just 4 sets, and an 8-way L1 keeps at most 32 of them. Each line is evicted long before its next write and gets brought in 16 times.
- **Tiled**: a tile touches only 16 lines of `b` (1 KiB). The `ti` loop runs 16 times, each pass writing one `float` into each of those lines; after 16 passes they are full and leave. The 16 lines sit in 4 sets, 4 per set, which an 8-way L1 holds. Strided writes that hit lines already in L1 are as cheap as sequential ones; each line comes in from the next level once.

A common "further optimization" copies the tile of `a` into a stack buffer `tile[T][T]` first and then writes `b` row by row from it. On a CPU that isn't faster (an analysis of memory traffic, not a timing): every line of `a` and `b` still moves once, plus an extra 1 KiB copy, and the stride hasn't gone away, it just moved from writing `b` to reading `tile`. The pattern comes from GPUs, where strided global-memory writes can't be coalesced into one access, so you stage through shared memory; on a CPU the L1 already does that for you. The real next step on a CPU is **transposing in registers**: load 4 rows of 4 `float`s into 4 `xmm` registers, swap them into 4 columns with `unpcklps` / `shufps` (`_MM_TRANSPOSE4_PS`), and store whole rows, so reads and writes go from one `float` at a time to 16 B at a time.

Conversely, a loop that touches each element once gains nothing from tiling. Take "clear a matrix": writing straight down the rows is already the best order. GCC `-O2` compiles the untiled version into a single `memset`; forcing 16×16 tiles instead leaves it writing 64 B per row and then jumping 2 KiB to the next row.

### 4.3 Fusion and Fission: One Pass or Several

- **Fusion**: put several operations on the same data into one loop, so the data comes from memory once. The cost is a bigger loop body: registers may run out, vectorization may be blocked, and it takes more instruction cache.
- **Fission**: the reverse, splitting one loop into several. Each body is simple and easy to vectorize, but the data is scanned several times.

The choice depends on data size: if the data fits in L2 / L3, the extra passes still hit in cache and split loops are better; if the data is far bigger than the caches, every extra pass is another pass of memory bandwidth, and fusion wins. When unsure, compare the two with `perf stat` on icache and LLC misses.

A common misuse is splitting "subtract the mean, divide by the standard deviation" into two passes. The single loop `v[i] = (v[i] - mean) / denom` already vectorizes: at `-O3` it compiles to `subps` + `divps`, 4 at a time. Splitting it into "subtract everything, then multiply everything" doesn't make either loop vectorize better; it just scans the array one more time. What actually saves time here is **multiplying by the reciprocal instead of dividing**: a division takes about 10–15 cycles and has several times lower throughput, a multiply about 3–4 cycles. One pass is enough:

```cpp
void normalize(float v[], int n, float mean, float var, float eps) {
    float inv_denom = 1.0f / sqrtf(var + eps);
    for (int i = 0; i < n; i++) v[i] = (v[i] - mean) * inv_denom;
}
```

The compiler won't do this for you by default, because multiplying by the reciprocal can differ from dividing in the last bit; under `-ffast-math` it does (`divps` becomes `mulps`).

### 4.4 Loop Collapsing: Merge Two Loops Into One

**1. The setup.** `rows` instruments, each storing `cols` price levels, rows stored back to back, all multiplied by one factor. The level count is known only at run time, say 3:

```cpp
void scale_nested(float* m, int rows, int cols, float s) {
    for (int i = 0; i < rows; i++)
        for (int j = 0; j < cols; j++)
            m[i * cols + j] *= s;
}
```

**2. Where the time goes.** `-O3` vectorizes the inner loop: `mulps` multiplies 4 at a time, and fewer than 4 go through remainder handling. With `cols = 3`, every row does this (GCC 13, measured, excerpted in execution order):

```text
    cmpl    $2, %r12d       # fewer than 4 → skip the 4-wide main loop
    jbe     .L24
    ...
    mulps   %xmm3, %xmm1    # remainder: 2 first
    ...
    mulss   %xmm0, %xmm1    # then 1
    ...                     # update row index and row start, next row
```

About 30 instructions and 4 conditional jumps per row, for 2 multiplies. The cost comes from **re-entering the inner loop on every row**; the shorter the row, the bigger its share.

**3. Merged.** No gaps between rows and the same work for every number, so treat it as one array of length `rows * cols`:

```cpp
void scale_flat(float* m, int rows, int cols, float s) {
    int total = rows * cols;
    for (int k = 0; k < total; k++)
        m[k] *= s;
}
```

The main loop is `movups` / `mulps` / `movups` plus 3 loop-control instructions: 6 instructions per 4 numbers, with the remainder handled once at the end of the array. A group of 4 spanning two rows is fine. Counting instructions, about 10 per number drops to about 1.5 (an estimate, not a timing).

**4. When you needn't, and when you can't.**
- Column count a compile-time constant (hard-coded 3): GCC unrolls the inner loop and vectorizes the outer one, 4 rows / 12 numbers per iteration, collapsing it for you.
- Gaps between rows (rows padded to 64 B, `vector<vector<float>>`): can't merge.
- Work depends on the row (each row times its own `s[i]`): no direct merge; recovering the row with `k / cols` costs a division, not worth it.

## 5. Edges: Peeling, Remainders, Sentinels

### 5.1 Peeling and Remainder Loops: Take the Irregular Iterations Out

A vectorized main loop handles 4 (or 8) elements at a time; when `n` isn't a multiple of 4, the remaining 0–3 are handled separately in a **remainder loop** (also called the epilogue), like the second `for` in 2.4. **Peeling** takes the first or last few iterations out, for example doing a few elements on their own so the main loop starts at a 16- or 32-byte-aligned address. Both serve the same purpose: no "is this iteration a special case" test inside the main loop. The compiler generates the remainder loop automatically when it vectorizes; in the assembly at the top, what follows `.L4` is a tail of element-by-element `mulss`.

### 5.2 Sentinels: Put a Guaranteed Hit at the End, Drop One Test From the Loop

Finding the first negative number normally tests two things per step: `i < n` and `a[i] < 0`. Reserve one extra slot at the end and put a negative number there; the loop is guaranteed to stop there, so only `a[i] < 0` needs testing:

```cpp
int find_first_negative(int* a, int n) {   // a has at least n + 1 slots
    int saved = a[n];
    a[n] = -1;
    int i = 0;
    while (a[i] >= 0) ++i;
    a[n] = saved;
    return i;                              // == n means not found
}
```

It requires that the extra slot really exists and is writable, and that no other thread is reading the array at the same time.

## 6. How to See What the Compiler Did

No guessing needed; let GCC tell you:

- `-fopt-info-vec`: which loops were vectorized, and with what vector width.
- `-fopt-info-vec-missed`: which weren't, and why (pointers may alias, a call in the loop, floating point can't be reordered…).
- `-fopt-info-loop`: loop transformations such as unrolling and unswitching.
- And look at the loop body with `-S`. The dot product at the top shows that "the report says vectorized" doesn't mean the addition chain got shorter; in the end you have to read the instructions.

Since GCC 12, `-O2` also vectorizes, but only under the most conservative cost model. At `-O2`, the plainly written loops in this post (the dot product at the top, the integer sum, `fill_10i`, the normalization, `add_or_sub`) were not vectorized at all; only the two dot products hand-written as four identical statements per iteration got vector multiplies (the multiple-accumulator one got `addps` too). That is SLP vectorization: merging identical statements within one iteration into one vector instruction, not merging iterations. At `-O3` all of these loops vectorized. For a key loop on the hot path, either build it with `-O3` or confirm against the report.

## In Practice {#in-practice}

The multiple accumulators of 3.2 match the {{% bottleneck-ref "serial-accumulator" "plain" %}} card below: what perf shows, how to fix it, how to verify the fix.

{{% bottleneck "serial-accumulator" %}}
