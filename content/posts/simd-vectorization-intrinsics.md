---
title: "Trading System Notes #15: SIMD Vectorization and Intrinsics"
date: 2026-10-15
slug: "simd-vectorization-intrinsics"
description: "Without an instruction-set flag GCC uses only 128-bit SSE2; -O2 skips vectorizing when pointers might overlap, and an -O3 report saying 'vectorized' isn't always real parallelism; omp simd reduction allows reordering a float sum in one loop only. Hand-written AVX2 intrinsics: vertical math is cheap, horizontal math is expensive, results differ from scalar in the last digits, and alignment, runtime instruction-set detection and vzeroupper need handling. Assembly measured with GCC 16."
summary: "One instruction computes a row of numbers only if the compiler knows how wide a register it may use, is sure nothing overlaps, and is allowed to reorder; when it can't get all three, intrinsics let you write it yourself, at the cost of alignment, instruction-set detection and the last few digits of the result."
chapter: 1
categories: [Systems]
tags: [cpp, simd, vectorization, avx2, intrinsics, hft, low-latency]
toc: true
light: true
---

Vectorization means one instruction computing a row of numbers at once: one AVX2 `vaddps` does 8 float additions, while a scalar `addss` does 1. It happens in the execution units in the back end of the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a>, and how wide a chunk of data a unit can process at once depends on which instruction set is used. [#9](/posts/loop-optimization/) covered how to write loops that vectorize well, and [Ref 2.4](/ref/cpu-memory/#appetite) shows the throughput difference it makes. This post covers the things you actually run into: how wide the registers in the compiled code really are, when the compiler refuses to vectorize and how the data should be laid out, what to watch for when writing intrinsics yourself, and how to split the work when several threads compute together.

## 1. How Wide the Registers Are: Without an Instruction-Set Flag, Only 128 Bits

x86 vector registers get wider with each instruction set:

| Instruction set | Register | Width | Floats at once | Doubles at once |
|---|---|---|---|---|
| SSE / SSE2 | XMM | 128 bits | 4 | 2 |
| AVX / AVX2 | YMM | 256 bits | 8 | 4 |
| AVX-512 | ZMM | 512 bits | 16 | 8 |

AVX widened floating-point operations to 256 bits, and AVX2 widened integer operations to 256 bits too. x86-64 only guarantees that every CPU has SSE2, so without `-march` GCC only dares to use SSE2: the same array-add loop compiles at `-O3` to 128-bit `addps %xmm`, and only with `-mavx2` does it become 256-bit `vaddps %ymm`, twice as much per instruction. Trading machines are your own, so you can compile for them: `-march=native` uses every instruction the machine supports, and `-march=x86-64-v3` is the level that includes AVX2 and FMA. The price is that the binary crashes on a CPU without those instructions as soon as it reaches one (illegal instruction); section 3.3 covers choosing at run time.

## 2. Auto-Vectorization: First Make Sure It Really Happened

### 2.1 Read the Report, and the Assembly

`-fopt-info-vec-optimized` makes GCC report which loops it vectorized, and `-fopt-info-vec-missed` reports why others weren't. Two things to know when reading the report.

First, `-O2` is more conservative than you might expect. The simplest array add:

```cpp
void add_arrays(float* c, const float* a, const float* b, int n) {
    for (int i = 0; i < n; i++) c[i] = a[i] + b[i];
}
```

GCC 16 `-O2` measurably doesn't vectorize it; it's still one `addss` at a time. The reason is that `c` might overlap `a` or `b`, so vectorizing would require inserting an overlap check first, which the cost model used at `-O2` won't do; `-O3` will. Mark the three pointers `__restrict` to say they don't overlap ([#10](/posts/pointer-memory-access/)), and `-O2` vectorizes it.

Second, a report saying "vectorized" doesn't necessarily mean parallel. A float sum without `-ffast-math` is reported as vectorized at `-O3`, but the assembly is 4 `addss` adding into the same accumulator one after another: each addition still waits for the previous result, and the dependency chain is no shorter; it just loads 4 numbers at a time in order. Real parallelism shows up in the assembly as `addps` or `vaddps`.

### 2.2 What Blocks Vectorization

> **Essence: The compiler auto-vectorizes only when it can prove that computing a row of numbers at once gives the same result as computing them one by one**.

- **It has to know how wide it may go**: without `-march`, 128 bits at most (Part 1).
- **It has to be sure there is no overlap and no dependency between iterations**: add `__restrict` to the pointers, and `a[i]` must not depend on `a[i - 1]`.
- **Floating-point reductions must be allowed to reorder**: turn on `-ffast-math`, or add `omp simd reduction` to just this loop.
- **The data must be contiguous and the loop body simple**: the numbers computed together sit next to each other in memory (2.3), the loop calls nothing that can't be inlined, and branches can become a masked select.

The specific cases that block it:

- **Possible overlap**: the compiler doesn't know whether the memory two pointers refer to overlaps, so it either inserts a check or gives up. Use `__restrict`, or pass the parameter by value ([#13, section 2.3](/posts/type-punning-calls-compiler-hints/)).
- **Dependencies between iterations**: when `a[i]` needs the result of `a[i - 1]`, a row of numbers can't be computed at once.
- **Floating point that would need reordering**: vectorizing a reduction such as a sum changes the order of the additions, which changes floating-point results, so it isn't allowed by default ([#12, section 3.2](/posts/strength-reduction-arithmetic/)).
- **Calls that can't be inlined** inside the loop, non-contiguous access (fetching values one by one from scattered addresses), or overly complex control flow.

If you don't want global `-ffast-math` just for a float sum (it also compiles `std::isnan` away), you can allow reordering for this one loop only:

```cpp
float sum_omp(const float* a, int n) {
    float s = 0;
    #pragma omp simd reduction(+:s)
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
```

Compile with `-fopenmp-simd`, which enables only OpenMP's SIMD-related directives, without threads or a runtime library. Measured, this loop compiles to `addps` at `-O2`; without `-fopenmp-simd` the pragma is ignored and it stays `addss`. Another way that needs no flag change is splitting the sum across several accumulators by hand; see [Ref 2.4](/ref/cpu-memory/#appetite). There's also `#pragma GCC ivdep`, which tells GCC to ignore the loop-carried dependencies it suspects; that amounts to you guaranteeing there's no overlap for this loop, and if the guarantee is wrong, so is the result.

### 2.3 Data Layout: Numbers Computed Together Must Sit Together to Fill One Instruction {#layout}

> **Essence: A vector load reads a row of numbers only from one contiguous range of addresses, so the numbers computed together must sit next to each other in memory, and SoA lays out each field as exactly such a contiguous array**.

- **In AoS the same field is separated by other fields**: the compiler either gives up, or reads several times as much data and shuffles out the lanes it wants.
- **In SoA one `vmovups` loads 8 x values**: one instruction each to read, compute and write, and every byte read is useful.

Scaling the x of every point by a constant, in both layouts:

```cpp
struct P { float x, y, z; };
void scale_aos(P* __restrict p, int n, float k)     { for (int i = 0; i < n; ++i) p[i].x *= k; }
void scale_soa(float* __restrict x, int n, float k) { for (int i = 0; i < n; ++i) x[i] *= k; }
```

Measured with GCC 15 `-O3 -march=x86-64-v3`: the report says "vectorized using 32 byte vectors" for both loops, but the assembly differs a lot:

- **SoA: 3 instructions per 8 elements**: `vmovups` to read, `vmulps` to multiply, `vmovups` to write back.
- **AoS: twenty-odd per 8 elements**: it reads 3 ymm registers (96 B, of which only 32 B are x), picks the 8 x values into one register with `vpermd` and `vblendps`, multiplies once, then writes them back one lane at a time with 8 `vmovss` and `vextractps`.

1. **Why switching AoS to SoA can be faster: three reasons**
   - **Cache and bandwidth**: when the loop uses only x, SoA brings only x into the cache, while AoS drags y and z along, so the same cache holds a third as much useful data ([#6 Part 2.1](/posts/alignment-layout-cache-dram-geometry/)).
   - **Vectorization**: as above, SoA computes vertically while AoS has to shuffle.
   - **Hardware prefetch**: one contiguous array per field is the access pattern a prefetcher recognizes most easily.

2. **When SoA isn't faster**
   - **Each use needs every field of one object**: in AoS one object sits in one cache line, while SoA touches 3 lines.
   - **Single objects are picked by index at random**: again SoA touches more lines.
   - **The compromise is AoSoA**: groups of 8 objects, laid out by field inside each group, so one group is exactly one vector wide.

## 3. Hand-Written Intrinsics

### 3.1 When It's Worth It

> **Essence: Let the compiler auto-vectorize first and confirm it did from the report and the assembly; hand-write intrinsics only for hot spots it can't do, or does wrong**.

- **What auto-vectorization gives you**: the code stays scalar, and recompiling on another machine uses its wider registers.
- **What hand-writing costs**: it ties you to one instruction set, you handle alignment, tails and runtime detection yourself, and the last few digits differ from the scalar version.
- **Typical cases for hand-writing**: parallelism the compiler can't see, such as several objects each running the same formula, which you place side by side in one instruction; and places that shuffle within a row of numbers or need a special instruction.

Intrinsics are C functions that each map to one instruction; `_mm256_add_ps`, for instance, is `vaddps`. The type names spell out width and element type: `__m256` is 8 floats, `__m256d` is 4 doubles, `__m256i` is 256 bits of integers, and the header is `<immintrin.h>`; look up what each function does in Intel's Intrinsics Guide. Hand-writing is worth it only when the compiler won't do something or does it badly: you accept the error that comes with reordering, you need to move values around within a row, you need a particular special instruction, or the hot path has to be exactly these instructions.

### 3.2 Example: An AVX2 + FMA Dot Product

```cpp
__attribute__((target("avx2,fma")))
float dot_avx2(const float* a, const float* b, int n) {   // n is a multiple of 8
    __m256 acc = _mm256_setzero_ps();
    for (int i = 0; i < n; i += 8)
        acc = _mm256_fmadd_ps(_mm256_loadu_ps(a + i), _mm256_loadu_ps(b + i), acc);
    __m128 s = _mm_add_ps(_mm256_castps256_ps128(acc), _mm256_extractf128_ps(acc, 1));
    s = _mm_add_ps(s, _mm_movehl_ps(s, s));
    s = _mm_add_ss(s, _mm_movehdup_ps(s));
    return _mm_cvtss_f32(s);
}
```

```text
dot_avx2(float const*, float const*, int):
    ...
.L3:
    vmovups      (%rdi,%rax,4), %ymm2
    vfmadd231ps  (%rsi,%rax,4), %ymm2, %ymm0   # 8 multiply-adds
    addq         $8, %rax
    cmpl         %eax, %edx
    jg           .L3
.L2:
    vextractf128 $0x1, %ymm0, %xmm1            # the next 6: add the 8 partial sums into 1
    vaddps       %xmm0, %xmm1, %xmm1
    vmovhlps     %xmm1, %xmm1, %xmm0
    vaddps       %xmm1, %xmm0, %xmm0
    vmovshdup    %xmm0, %xmm1
    vaddss       %xmm1, %xmm0, %xmm0
    vzeroupper
    ret
```

The loop has a single `vfmadd231ps` per 8 elements, doing 8 multiplications and 8 additions together, each lane combining only with the same lane of another vector. That's vertical math, and it's cheap. At the end, the 8 partial sums in the accumulator have to be added into one number, which means moving values around inside a register. That's horizontal math, it takes several shuffle instructions, so it's done only once at the end.

The result differs from the scalar loop in the last digits: `dot_avx2` measures 559.515015, while the in-order scalar version gives 559.514893. Accumulating 8 partial sums separately changes the order of the additions, and FMA also skips one intermediate rounding; it's the floating-point reordering from #12. This version has a single accumulator, so every `vfmadd231ps` waits for the previous one and the loop is bound by FMA latency; split it into 2–4 accumulators and several FMAs can be in the pipeline at once ([Ref 2.4](/ref/cpu-memory/#appetite)).

### 3.3 Alignment, Instruction-Set Detection, `vzeroupper`

**Alignment**. `_mm256_load_ps` requires a 32-byte-aligned address and crashes otherwise; `_mm256_loadu_ps` accepts any address. On recent CPUs, when the data happens to be aligned, `loadu` is as fast as `load`; it only costs extra when a load crosses a cache line ([#6](/posts/alignment-layout-cache-dram-geometry/)). So use `loadu` in general, and align the data with `alignas(32)`.

**Choosing the instruction set at run time**. The function above uses `__attribute__((target("avx2,fma")))` to enable AVX2 for itself only, while the rest of the program is compiled for the baseline; check the CPU once at startup and take this path only when it's supported:

```cpp
float dot(const float* a, const float* b, int n) {
    static const bool has_avx2 = __builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma");
    return has_avx2 ? dot_avx2(a, b, n) : dot_scalar(a, b, n);
}
```

GCC's `target_clones` attribute can generate several versions automatically and pick one when the program loads; it relies on Linux's ifunc mechanism.

**`vzeroupper`**. After using 256-bit registers, running old SSE instructions without the VEX prefix makes many Intel cores pay a state-transition cost. The compiler inserts a `vzeroupper` at the end of functions that used 256-bit registers, zeroing the upper halves, and it's there in the assembly above. You only need to worry about it in hand-written assembly or when calling old SSE libraries.

### 3.4 NaN in a Vector

A vector comparison produces a mask, each lane all ones or all zeros. NaN is "unordered" against anything, even itself, so `_mm256_cmp_ps(x, x, _CMP_UNORD_Q)` marks exactly the lanes holding NaN, and `_mm256_movemask_ps` packs that into an 8-bit integer:

```cpp
__attribute__((target("avx2")))
int count_nan8(const float* p) {
    __m256 x = _mm256_loadu_ps(p);
    __m256 m = _mm256_cmp_ps(x, x, _CMP_UNORD_Q);   // NaN compared with itself is "unordered"
    return __builtin_popcount(_mm256_movemask_ps(m));
}
```

Measured, with 2 NaNs among 8 numbers it returns 2. Floating-point exceptions are masked by default, so a NaN raises no error and just propagates: adding those 8 numbers measurably gives nan. For computations like aggregating prices, rather than checking every element, compute a mask once per batch and handle NaNs separately when there are any.

## 4. Several Threads Computing One Large Matrix: Split by Output, Each Thread Writes Only Its Own Rows {#threads}

### 4.1 Never Let Two Threads Write the Same Element: Inputs Are Read-Only, Output Rows Are Divided Among Threads {#parallel-matrix}

> **Essence: A data race is two threads accessing the same location at the same time, at least one writing, with no synchronization between them; if each output element is written by only one thread and the inputs are only read, there is no data race, and no lock or atomic is needed**.

- **Split by output, not by input**: each thread owns some rows and writes only those; every thread reads the input vectors, and reads alone don't race.
- **Read the result after `join`**: `join` makes the thread's writes visible to the thread that called it.
- **Don't let a boundary between two threads fall inside one cache line**: that isn't a data race, but two threads writing one line is false sharing.

Pairwise similarity of N vectors, with output an N×N matrix `S`:

```cpp
float dot(const float* __restrict a, const float* __restrict b, int d) {
    float s = 0;
    #pragma omp simd reduction(+:s)
    for (int k = 0; k < d; ++k) s += a[k] * b[k];
    return s;
}

// Pairwise similarity of N vectors of dimension D. S is N×N, row-major, ld floats per row
void sim_rows(const float* V, float* S, int N, int D, int ld, int first, int step) {
    for (int i = first; i < N; i += step)            // this thread writes only rows first, first+step, ...
        for (int j = 0; j < N; ++j)
            S[(size_t)i * ld + j] = dot(V + (size_t)i * D, V + (size_t)j * D, D);
}

const int ld = (N + 15) / 16 * 16;                   // pad each row to a multiple of 16 floats (64 B)
float* S = static_cast<float*>(std::aligned_alloc(64, (size_t)N * ld * sizeof(float)));
std::vector<std::thread> ts;
for (int t = 0; t < T; ++t) ts.emplace_back(sim_rows, V, S, N, D, ld, t, T);
for (auto& th : ts) th.join();                       // read S only after join
```

- **Each element has exactly one writer**: row i belongs only to thread `i % T`, so no two threads write the same `S[i][j]`.
- **Interleave the rows to balance the load**: when a symmetric matrix computes only the upper triangle, row i has N−i entries, so contiguous blocks give the first threads more work; interleaving by `i % T` evens it out. Copy the upper triangle to the lower one after `join`.
- **With interleaved rows, every row boundary is a boundary between two threads**: a row of 1000 floats is 4000 B, not a multiple of 64 B, so neighbouring rows share a cache line. So pad the row stride `ld` to a multiple of 16 floats and align the matrix to 64 B, and every row starts on a new cache line ([#2 Part 3](/posts/memory-ordering-false-sharing-dependency-chains/#3-false-sharing-when-correctness-was-never-the-question)).
- **When adding into one shared result** (say, the sum of all similarities): each thread adds into its own local variable and they are combined once at the end, instead of atomically adding to one variable every time.
- **Use SIMD inside each thread too**: the `omp simd reduction` in `dot` vectorizes the inner loop (2.2). Measured with N = 1000, D = 64 and 4 threads: GCC 15 `-O2 -march=x86-64-v3 -fopenmp-simd` emits `vmulps` and `vaddps %ymm`, and the result differs from a reference computed in order by at most 1.1e-5, because the addition order changed.

## In Practice {#in-practice}

Register width from Part 1, auto-vectorization from Part 2 and `vzeroupper` from 3.3 match the two cards below ({{% bottleneck-ref "narrow-vector" "num" %}}, {{% bottleneck-ref "missing-vzeroupper" "num" %}}): what perf shows, how to fix it, how to verify the fix.

{{% bottleneck "narrow-vector" %}}

{{% bottleneck "missing-vzeroupper" %}}
