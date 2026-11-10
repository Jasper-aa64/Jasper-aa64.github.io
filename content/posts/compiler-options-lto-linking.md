---
title: "Trading System Notes #22: The Compiler: Which Options to Turn On, and How to See What It Did"
date: 2026-11-09
lastmod: 2026-11-10
slug: "compiler-options-lto-linking"
description: "A compiler only makes transformations it can prove leave the result unchanged. -O2 already contains almost every optimization, and what -O3 adds is mostly loop transformations and vectorization behind a run-time check; -march unlocks newer instructions and also ties the program to that CPU generation; each .cpp is compiled alone, so small functions in other files can't be inlined without LTO; a call into a shared library takes an extra indirect jump and blocks inlining. Last, how to confirm what the compiler actually did."
summary: "What a compiler can do depends on what it can prove. Options widen what it may do (-O3, -march, LTO), hints tell it what it can't prove (restrict, likely), and the assembly and the optimization report tell you whether it did it."
chapter: 2
light: true
categories: [Systems]
tags: [cpp, gcc, compiler, optimization, lto, pgo, linking, hft, low-latency]
toc: true
math: true
---

Many hot-path optimizations are ones the compiler already does: constant folding, inlining, turning a multiply into a shift, vectorizing a loop. When it doesn't, it usually isn't because it can't, but because **it can't prove the result stays the same**: whether two pointers point at the same memory, whether reordering a float addition changes the last bit, what a function in another `.cpp` looks like. So working with the compiler comes down to three things: use options to widen what it may do, use hints to tell it what it can't prove, and read the assembly to confirm it did it.

> **This post's chain of problems: each fix exposes the next one**
> 1. **The compiler only makes transformations it can prove**: first, what it does on its own and where it gets stuck (Part 1).
> 2. **Optimization is off by default**: `-O2` or `-O3` (Part 2).
> 3. **With optimization on, it still uses only SSE2 by default**: `-march` unlocks newer instructions, at the cost of tying you to the machine (Part 3).
> 4. **Each `.cpp` is compiled alone, so nothing is inlined across files**: LTO (Part 4).
> 5. **A hot-path call into a shared library takes an extra indirect jump and can't be inlined**: link statically, or tighten symbol visibility (Part 5).
> 6. **Options and hints are in place: did it actually do it?** Read the assembly and the optimization report (Part 6).

---

## 1. What the Compiler Does on Its Own: Only Transformations It Can Prove Keep the Result {#what-compiler-does}

1. **Mainstream compilers all do the integer and control-flow transformations**
   - **Constant folding and constant propagation**: `x = 3 * 4` becomes 12 at compile time, and the 12 is substituted wherever `x` is used.
   - **Common subexpression elimination and loop-invariant code motion**: an expression computed twice is kept once, and work that doesn't change inside a loop moves out of it.
   - **Strength reduction**: a multiply by a constant becomes shifts and adds, a divide by a constant becomes a multiply by a magic number and a shift ([#12](/posts/strength-reduction-arithmetic/)).
   - **Inlining, tail calls into jumps, devirtualization**: a function whose body it can see gets inlined; a virtual call whose target it can pin down becomes a direct call ([#8](/posts/crtp-static-polymorphism/)).
2. **What stops it are three kinds of "can't prove"**
   - **Floating-point arithmetic isn't associative**: `(a + b) + c` and `a + (b + c)` can differ in the last bit, so without `-ffast-math` GCC won't reorder a float sum to vectorize it ([#9](/posts/loop-optimization/)).
   - **Pointers may overlap (aliasing)**: writing `a[i]` may change `b[i]`, so the compiler has to reload on every iteration or check at run time first ([#10](/posts/pointer-memory-access/) Part 1).
   - **It can't see other translation units**: for a function in another `.cpp` it knows only the signature, not the body, so it can't inline it or know whether it changes your variables (Part 4).
3. **Compilers differ in how aggressive they are, not in what they know how to do**
   - **Examples**: splitting an integer sum into several accumulators, Clang does on its own and GCC doesn't ([the memory latency and bandwidth special](/posts/low-latency-memory-latency-bandwidth/) 1.5.1); Clang unrolls array loops further.
   - **So after changing compiler or version, read the assembly of the hot functions again** (Part 6).

## 2. Optimization Is Off by Default: -O2 Already Has Almost Everything, -O3 Adds Loop Transformations {#opt-levels}

### 2.1 What -O3 Adds Over -O2: Only 13 Flags in GCC 16 {#o2-vs-o3}

1. **`-Q --help=optimizers` shows exactly which flags each level turns on**
   - **Result**: GCC 16.2 turns on 145 at `-O2` and 158 at `-O3`. Inlining (`-finline-functions`), both kinds of auto-vectorization and small-loop unrolling are already on at `-O2`.
   - **Almost everything `-O3` adds is a loop transformation**: `-funswitch-loops` (hoist an `if` that doesn't change inside the loop, making two copies of the loop), `-floop-interchange` (swap the order of nested loops), `-ftree-loop-distribution` (split one loop into several), `-fpeel-loops`, `-fsplit-loops`, `-floop-unroll-and-jam`, plus `-fipa-cp-clone` (make a specialized copy of a function for a constant argument) and `-fpredictive-commoning`.
   - **The other difference is the vectorizer's cost model**: `-O2` uses `very-cheap`, which vectorizes only when no run-time check and no extra tail loop are needed; `-O3` uses `dynamic`, which is willing to pay for them.
2. **Example: the same array add is not vectorized at `-O2` and is at `-O3`**

   ```cpp
   void add(float* a, const float* b, const float* c, int n) {
     for (int i = 0; i < n; ++i) a[i] = b[i] + c[i];   // a may overlap b or c
   }
   ```

   - **`-O2`**: `-fopt-info-vec-optimized` reports nothing. `a` may overlap `b` and `c`, so vectorizing needs a run-time check first, and `very-cheap` won't pay for it.
   - **`-O3`**: reports "loop versioned for vectorization because of possible aliasing". The compiler emits two versions and compares the addresses at run time: no overlap takes the vector version, overlap takes the scalar one.
   - **With `__restrict` on all three pointers**: `-O2` vectorizes it too. You proved for it that they don't overlap, so no run-time check is needed.
3. **`-O3` is not always faster**
   - **The code grows**: the extra loop versions and unrolled loops take instruction-cache space. A hot path is small to begin with, and pushing it out of L1i makes it slower.
   - **So build both levels and compare latency distributions (p50, p99) on your own replay data, not averages** ([#21](/posts/trading-system-latency-metrics/) 1.2).

### 2.2 Options That Touch the Result: Turn On the Ones That Keep Semantics, Think Before the Ones That Don't {#semantic-flags}

1. **The ones that don't change results, hot-path programs usually turn on**
   - **`-fno-exceptions`, `-fno-rtti`**: a hot path shouldn't throw or use `dynamic_cast` anyway. Without them the code is a little smaller, and the compiler doesn't have to keep a cleanup path for every call that might throw. Libraries that rely on exceptions can't be built this way.
   - **`-fomit-frame-pointer`**: already on by default at `-O2`, freeing a register. The cost is that `perf` walking the stack by frame pointers breaks, so use `perf record --call-graph dwarf` ([the perf special](/posts/low-latency-perf-profiling/) 2.2).
   - **`-g` doesn't change the generated code**: GCC guarantees the same instructions with or without `-g`, so production binaries can carry debug info, or have it split off and stored separately.
2. **The ones that change results must match between factor research and production**
   - **`-ffast-math`**: allows reassociation and assumes no NaN or infinity, so `std::isnan` may be optimized to false.
   - **FMA**: once `-march` enables FMA, `a * b + c` can be fused into one multiply-add whose intermediate isn't rounded on its own, so the last bit changes.
   - **When research and production disagree, these options are among the first things to check.**

## 3. With Optimization On, It Still Uses Only SSE2: -march Unlocks Newer Instructions, and Ties the Program to That CPU Generation {#march}

1. **Pain point: without `-march`, GCC only uses instructions every x86-64 has**
   - **x86-64 only guarantees SSE2**: vector registers are used only up to 128 bits, and AVX2, FMA, BMI and the like go unused ([#15](/posts/simd-vectorization-intrinsics/) Part 1).
2. **Fix: compile for the model of the deployment machine**
   - **`-march=native`**: use every instruction the compiling machine supports.
   - **Naming the model, as in `-march=icelake-server` or `-march=znver4`, is safer**: the build machine and the production machine are often not the same box, and `native` carries the build machine's instructions over.
   - **`-march=x86-64-v3`**: a generic baseline that includes AVX2 and FMA, for when one binary has to run on several generations of machines.
   - **`-mtune` only changes instruction scheduling and unlocks nothing**: the binary runs anywhere and is just tuned for one generation.
3. **Cost one: on a CPU that lacks the instructions, it crashes when it reaches one**
   - **It shows up as `SIGILL` (illegal instruction)**, and not at startup but the first time that code runs.
   - **So check the production machine's `/proc/cpuinfo` flags before deploying**; if it really has to span generations, pick the implementation by run-time detection ([#15](/posts/simd-vectorization-intrinsics/) 3.3).
4. **Cost two: on some older Intel servers, AVX-512 makes the core downclock**
   - **Why**: heavy 512-bit instructions draw a lot of power, so the core drops its frequency by a few hundred MHz, and after they finish it takes a while (on the order of 1 ms) to come back up, during which the scalar code that follows is slower too.
   - **Newer cores (Intel from Ice Lake on, AMD Zen 4) drop far less**, but measure on your own machine.
   - **What to do**: keep the hot path on AVX2 or scalar code, and leave AVX-512 to a separate batch core. `-mprefer-vector-width=256` caps auto-vectorization at 256 bits, and GCC already defaults to that for most Intel server models.

## 4. Each .cpp Is Compiled Alone, So Small Functions in Other Files Can't Be Inlined: LTO {#lto}

1. **Pain point: the compiler sees one translation unit at a time**
   - **Example**: `on_tick()` in `strategy.cpp` calls `best_bid()` in `book.cpp` every time, and its body is one line. Compiling `strategy.cpp`, the compiler knows only the signature and can only emit a `call`.
   - **What's lost is more than the `call`**: without inlining it can't propagate constants at the call site or hoist what the function computes out of the loop, and it has to assume the call may have changed any global.
2. **Fix one: LTO (link-time optimization)**
   - **How**: add `-flto` to both compiling and linking. Each `.o` then holds the compiler's intermediate representation, and at link time the whole program goes back to the compiler, which inlines across files and drops functions nobody calls.
   - **Cost**: linking gets slower and uses more memory. `-flto=auto` compiles in parallel at link time.
3. **Fix two: put small hot-path functions straight in headers**
   - **This is the most common approach in HFT codebases**: define small functions in headers (inside the class or with `inline`, which governs linkage, not inlining), so every translation unit that uses one sees its body, without depending on LTO.
4. **There is also reordering by real run statistics: PGO**
   - **How it works, and the trap in a trading system, are in [#7](/posts/branch-prediction-branch-optimization/) 3.3**: if training barely exercised the order path, it gets treated as cold code and moved to the cold section, so use dummy executions or `-fprofile-partial-training`.

## 5. A Hot-Path Call Into a Shared Library: an Extra Indirect Jump, and No Inlining {#dynamic-linking}

1. **Pain point: calling a function in a shared library (`.so`) goes through the PLT**
   - **The PLT (procedure linkage table) is a small trampoline**: the `call foo` in the program actually calls the trampoline, which reads `foo`'s real address from the GOT (global offset table, a table of addresses filled in at load time) and jumps there. Every call costs an extra load and an indirect jump.
   - **Calls inside the library are the same**: compiled with `-fPIC` and symbols visible by default, `f()` in a library calling `g()` in the same library also goes through the PLT, and the compiler won't inline `g()`. The reason is that another library (via `LD_PRELOAD`, say) may replace `g` at load time; this is called **semantic interposition**.
2. **Fix one: link the hot path statically**
   - **`-static`, or build every hot-path dependency as a static library**: a call is then one direct `call`, and with LTO it can be inlined across libraries. Most ultra-low-latency trading programs do this.
3. **Fix two: when a shared library is unavoidable, tighten the symbols**
   - **Why shared libraries still get used**: strategies built as plugins, loaded on demand and released separately, or strategy code kept secret from the platform.
   - **`-fvisibility=hidden`**: export nothing by default, and mark only the public interface with `__attribute__((visibility("default")))`. Functions that aren't exported are called directly inside the library and can be inlined.
   - **`-fno-semantic-interposition`**: tells the compiler that exported functions won't be replaced either, so calls inside the library can be inlined.
   - **`-fno-plt`**: an external call reads the address straight from the GOT and calls it, skipping the trampoline hop.
4. **Fix three: do all the loading and symbol lookup at startup**
   - **`dlopen` with `RTLD_NOW`**: resolve every symbol at load time, so a missing symbol fails right there; the default lazy binding leaves the resolution cost of the first call on the hot path.
   - **Keep the function pointers `dlsym` returns**: the hot path calls the pointer directly, with no lookup.

## 6. Options and Hints Are in Place: Did It Actually Do It? Read the Assembly and the Optimization Report {#inspect}

1. **Check the flags first, then the report, then the assembly**
   - **Which flags are on**: `g++ -O2 -Q --help=optimizers`; that's how the counts in 2.1 were taken.
   - **Whether it vectorized, and why not**: `-fopt-info-vec-optimized` reports what was done, `-fopt-info-vec-missed` reports what wasn't and why; in Clang, `-Rpass=loop-vectorize` and `-Rpass-missed=loop-vectorize`.
   - **Last, the assembly**: `g++ -O2 -S -masm=intel` writes an assembly file, `objdump -d -C --no-show-raw-insn` reads a binary that's already built, and Compiler Explorer (godbolt.org) is good for comparing compilers and options.
2. **The report saying it did something doesn't mean it got faster**
   - **Example**: for a `float` sum without `-ffast-math`, GCC 16's `-O3` report says "loop vectorized", yet the assembly is all `addss`, and the additions are still one serial chain ([#15](/posts/simd-vectorization-intrinsics/) 2.1).
   - **So the final call is made on the assembly, and `perf annotate` then shows which instructions are hot** ([the perf special](/posts/low-latency-perf-profiling/) 4.5).
3. **Telling it what it can't prove: the hints and builtins are in earlier posts**
   - **Pointers don't overlap**: `__restrict` ([#10](/posts/pointer-memory-access/) Part 1).
   - **Which way a branch usually goes**: `[[likely]]`, `__builtin_expect`, which change code layout, not the predictor ([#7](/posts/branch-prediction-branch-optimization/) 3.1).
   - **A function has no side effects**: `__attribute__((const))`, `pure` ([#11](/posts/rvo-pure-functions/)).
   - **Data is about to be used**: `__builtin_prefetch` ([#14](/posts/prefetch-warmup-double-buffer/)).
   - **Every one of these hints is a promise from you, and the compiler doesn't check it**: get one wrong and it's undefined behavior, and the result may quietly be wrong.
