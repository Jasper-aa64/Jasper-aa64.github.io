---
title: "Trading System Notes #7: Branch Prediction and Branch Optimization"
date: 2026-10-09
slug: "branch-prediction-branch-optimization"
description: "Why a CPU has to guess branches, how it guesses, what a wrong guess costs, and how to remove, hint and separate branches. Part 1: the front end and speculative execution, the BTB / RAS / indirect target predictor / history-based direction prediction, a misprediction costing about 15–20 cycles, predictability coming from the data (the sorting experiment and the compiler's if-conversion), and which predictor handles each kind of C++ branch."
summary: "The front end has to fetch instructions every cycle, but a branch isn't resolved until a dozen-plus cycles later, so the CPU guesses. A right guess costs almost nothing; a wrong one throws away everything after it, about 15–20 cycles. The same if is predictable when the data has a pattern and a coin flip when it's random, and the compiler may already have turned it into a cmov."
chapter: 1
categories: [Systems]
tags: [cpp, branch-prediction, pipeline, speculative-execution, cmov, hft, low-latency]
toc: true
math: true
homepage: false
---

Add up the even numbers among a million random integers in 0–199, and repeat that 64 times. Run the same code again after sorting the array first, and it is about 7 times faster. Not one value changed and the sum is identical; the only difference is whether "is the next number even?" follows a pattern.

Then compile both with `g++ -O2`, and they run at the same speed again. Both facts start from the branch predictor in the CPU's front end: why it has to guess, how it guesses, what a wrong guess costs, and how the compiler can remove the branch altogether.

## 1. The Branch Predictor: Why the CPU Guesses and What a Wrong Guess Costs

### 1.1 Where It Sits: The Front End

Most of the quick reference's <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a> is the data side: loads and stores, caches, memory. Branch prediction lives on the other side, the **front end**, which fetches and decodes instructions and feeds them to the back end. In order:

1. **Fetch**: read a chunk of bytes from L1I (the instruction cache) at "the address of the next instruction".
2. **Decode**: split them into micro-ops (µops).
3. **Rename and enter the ROB**: into the out-of-order window (the ROB is covered in [Memory Latency and Bandwidth](/posts/low-latency-memory-latency-bandwidth/), 1.3.2).
4. **Execute**: only here is a branch's condition actually computed and its direction known.
5. **Retire**: confirmed in program order.

The **branch predictor** sits next to step 1: for every chunk fetched, it answers on the spot "is there a branch in here, and where does it go?", and the fetch unit fetches the next chunk from wherever it says.

### 1.2 Why It Has to Guess: The Pipeline Is Longer Than the Gap Between Branches

Put two numbers side by side:

- From fetch to execute, an instruction travels about 15–20 cycles (the pipeline depth).
- In ordinary code, one instruction in 5–7 is a branch (about 15%–20% of instructions). The front end fetches 4–8 instructions per cycle, so it meets a branch almost every cycle.

If fetch stopped at every branch and waited for it to execute, each branch would waste 15–20 cycles and the CPU would spend most of its time idle. So the front end doesn't wait: it keeps fetching and executing down the predicted path. This is **speculative execution**. Speculative results sit in the ROB and may retire only once the branch is confirmed to have been predicted right.

### 1.3 How It Guesses: Direction, Target, History

Here "branch" means any instruction that changes where the next instruction is fetched from: the conditional jumps an `if` compiles to, `call`, `ret`, and indirect jumps such as virtual calls. The predictor always guesses **the address of the next instruction**, never a data value (a function's return value is data in a register and needs no guessing). A branch needs two guesses: **taken or not** (direction) and **where to** (target). What is hard differs by kind:

- **Target**: the **BTB** (branch target buffer) records, by the branch instruction's address, where it went last time; about 4000–12000 entries. One lookup at fetch tells whether this chunk holds a known branch and where it goes.
- **Function returns**: a `ret` always jumps; the hard part is where to. The same function called from different places has to return to different places:

  ```cpp
  void log_it() { /* … */ }                // ends in a single ret
  void on_trade() { log_it(); update(); }  // this time the ret returns here and runs update()
  void on_quote() { log_it(); quote(); }   // next time the same ret returns here and runs quote()
  ```

  This is the job of the **RAS** (return address stack, 16–32 entries): when fetch sees a `call`, it pushes "where to come back to"; when it sees a `ret`, it pops the top and fetches from there. It is still a guess: the push and the pop happen at fetch, while the `ret` actually executes, reading the return address from the call stack in memory, 15–20 cycles later, and only then is the guess checked. As long as every `call` is matched by a `ret`, it is almost always right. It goes wrong in two cases: call depth beyond the RAS's capacity (deep recursion), or calls and returns that don't pair up, such as a thrown exception or `longjmp` that skips the `ret`s of the frames in between, leaving stale addresses in the RAS that make the next few `ret`s mispredict.
- **Indirect branches** (virtual functions, function pointers, `switch` jump tables): one instruction can go to many targets; the **indirect target predictor** records the target by "this instruction + recent history".
- **Direction**: the simplest scheme gives each branch a **2-bit saturating counter**: +1 when taken, −1 when not, clamped to 0–3, and predict "taken" at ≥ 2. It predicts loops well (taken 99 times, not taken once at the end, only the last one is wrong), and one odd outcome doesn't flip its mind at once.

<a href="/images/branch-prediction/two-bit-counter.en.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/two-bit-counter.en.svg" alt="The four states 0, 1, 2, 3 of a 2-bit saturating counter: +1 when the branch is taken, −1 when not; 0 and 1 predict not taken, 2 and 3 predict taken. Below, a loop taken 7 times, not taken once at the exit, then entered again: only the exit is mispredicted, and the counter drops from 3 to 2, still predicting taken." loading="lazy" decoding="async"></a>

Modern predictors add **history** on top: the outcomes (taken / not taken) of the last 50–1000 branches, recorded as one **global history** string, are used together with the branch address to look up a table. That lets them learn patterns like "if the previous branch was taken, this one isn't" or "taken once every 3 times". The mainstream design (the TAGE family) uses several tables with different history lengths and picks the longest one that hits. The upshot: **a branch with a pattern can be learned, even a long pattern; a branch without one can't be learned by anyone.** A condition that is a fresh 50/50 coin flip every time is predicted right half the time by even the best predictor.

In ordinary programs these structures together predict well over 95%–99% of branches.

### 1.4 What a Wrong Guess Costs: Flushing the Pipeline

When a branch executes and turns out to be mispredicted:

1. Every instruction fetched after it (still in the pipeline, already in the ROB, even already executed) is discarded.
2. Fetch goes back to the correct address and starts over.
3. The new instructions go through fetch, decode and rename again before the back end fills up.

<a href="/images/branch-prediction/pipeline-flush.en.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/pipeline-flush.en.svg" alt="Timeline of a 4-stage pipeline (fetch, decode, execute, retire) over cycles 1–10. Predicted right, instructions after branch B flow in one per cycle. Mispredicted, B executes in cycle 5, wrong-path W1 and W2 are discarded, I3 is fetched from cycle 6, and Execute idles for 2 cycles." loading="lazy" decoding="async"></a>

The cost is roughly the pipeline depth from fetch to execute, **about 15–20 cycles**, about 4–5 ns at 4 GHz. At 4–8 instructions per cycle, that is 60–160 instructions' worth of execution lost. (Loads issued on the wrong path have already brought lines into the cache, and that is not undone; this is where Spectre-class vulnerabilities come from, not covered here.)

Compare with the numbers in [Memory Latency and Bandwidth](/posts/low-latency-memory-latency-bandwidth/): an L1 hit is about 1 ns, an L2 hit about 3–5 ns, a branch misprediction about 4–5 ns. One misprediction on the hot path costs about as much as an L2 hit. The difference: a cache miss can overlap with other misses (MLP), while a misprediction throws away the work after it and can't overlap with it.

### 1.5 Predictability Comes From the Data: The Sorting Experiment

A classic example (`data` holds 16384 random integers in 0–199, and the outer loop repeats 10000 times):

```cpp
for (unsigned i = 0; i < 10000; ++i) {
    for (unsigned c = 0; c < arraySize; ++c) {
        if (data[c] % 2 == 0) {
            evenSum += data[c];
        }
    }
}
```

Run the same loop with `data` unsorted and sorted; the sorted version adds a single line, `std::sort(data, data + arraySize)`.

- **Unsorted**: whether each number is even is completely random, the `if` has no pattern, and the predictor gets about half right. Each element pays about $0.5 \times (15\text{–}20) \approx 8\text{–}10$ extra cycles on average, several times the loop body itself (1–2 cycles).
- **Sorted**: each value in 0–199 appears about 82 times, so the sorted array alternates in runs: 82 evens, 82 odds, 82 evens… 200 runs in all. The direction changes only at run boundaries, each boundary mispredicts 1–2 times, so a pass of 16384 mispredicts only about 200–400 times, about 1%–2%.

<a href="/images/branch-prediction/sorted-strip.en.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/sorted-strip.en.svg" alt="Two strips: unsorted, 20 random numbers flip between even and odd and the 2-bit counter mispredicts 10; sorted, a run of 36s then a run of 37s, mispredicted only twice at the boundary." loading="lazy" decoding="async"></a>

So the sorted run is several times faster (measured later in this section). The lesson: **the same branch in the same code is predictable or not depending on the data.**

**There is a compiler trap here**: GCC 13.3 on x86-64 turns this `if` branch-free from `-O1` up. The inner loop has only an `and` (take the low bit) and a `cmove` (move the new sum into `evenSum` only if the condition holds), no conditional jump; `-O3` vectorizes it as well. Then sorted and unsorted run at the same speed and the experiment shows nothing. To see the cost of mispredictions you have to add `-fno-if-conversion -fno-if-conversion2 -fno-tree-vectorize`, which leaves a `je` in the inner loop. So before arguing about whether there's a branch, read the assembly. (Why `cmov` removes a branch and when the compiler won't use it is in Part 2.)

<a href="/images/branch-prediction/branch-predictability.en.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/branch-predictability.en.svg" alt="Two branch-kept curves and a flat cmov line; x is the share of even numbers p, y is ns per element. With a million numbers the branch-kept curve is a tent, peaking near 2.9 ns at p = 50% and about 0.25–0.44 ns at the edges; with 16384 numbers it hugs the bottom, peaking near 0.77 ns; cmov stays at about 0.44 ns; sorted at p = 50% is about 0.40 ns." loading="lazy" decoding="async"></a>

<a href="/images/branch-prediction/predictor-memorize.en.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/predictor-memorize.en.svg" alt="A random p = 50% array; x is the array length from 1K to 4M (log), y is ns per element. Up to 16K it is about 0.6–0.7 ns, at 32K it jumps to about 2.1 ns, from 256K on about 2.85 ns; sorted stays near 0.4 ns." loading="lazy" decoding="async"></a>

> Measured (AMD Ryzen 5 5600GT, one core, GCC 16.2.0, `-O2`; the branch-kept build adds `-fno-if-conversion -fno-if-conversion2 -fno-tree-vectorize`. The share of even numbers p sweeps 0% to 100%, the same numbers are re-run for about 67 million elements, best of 5 per point):
>
> - **Branch kept, a million numbers: a tent**. At p = 50% it takes about 2.87 ns per element; sorted, about 0.40 ns, about 7 times faster. The curve climbs and falls almost in straight lines: when the direction is random, the best guess is always the majority side, so the misprediction rate is $\min(p, 1-p)$. The extra time per element is about $\min(p, 1-p) \times 4.9\ \text{ns}$: 2.43 ns extra at p = 50%, so about 4.9 ns per mispredict; use it for p = 25% and 0.25 × 4.9 ≈ 1.2 ns, against 1.21 ns measured.
> - **The `cmov` build: a flat line** at about 0.44 ns per element, regardless of p or sorting. Each element waits for the previous sum (`add` then `cmove`, about 2 cycles), and that dependency chain sets its speed.
> - **At the edges, keeping the branch is faster**. At p = 100% every guess is right, about 0.25 ns, faster than `cmov`; at p = 0% it is about 0.44 ns, because each element jumps twice (over the add, and the loop back edge) and hits the limit of roughly one taken jump per cycle. When to switch to `cmov` is Part 2.
> - **With only 16384 numbers, the cost almost disappears**. Equally random, p = 50% takes only about 0.66 ns, sorted about 0.44 ns, just 1.5 times apart. The same string of 16384 directions is replayed over 4000 times and the predictor memorizes it with its long history. The second chart sweeps the array length at p = 50%: up to 16384 numbers it stays around 0.6–0.7 ns, at 32768 it jumps to about 2.1 ns, and from 260 thousand on it settles at about 2.85 ns. So don't measure branch costs by replaying a short input over and over: real market data doesn't repeat, and a replay looks too optimistic.

**How to measure**: on Linux, `perf stat -e branches,branch-misses ./prog` gives the number of branches and how many were mispredicted; the ratio is the misprediction rate. Windows has no `perf`; use AMD uProf on AMD and VTune on Intel. Only a hot-path misprediction rate of several percent or more is worth acting on.

### 1.6 Branch Kinds: Which Predictor Handles Each

The C++ constructs that produce branches, matched against 1.3:

| Construct | In machine code | Predicted by |
|---|---|---|
| `if` / `else`, ternary `?:`, short-circuit `&&` / `\|\|`, loop conditions, `break` / `continue` | conditional jump (`jcc`), fixed target | direction predictor |
| direct function call | `call` to a fixed address | BTB (unconditional, almost never wrong) |
| function return | `ret` | RAS |
| `switch` (compiled to a jump table) | indirect jump `jmp [table + index×8]` | indirect target predictor |
| virtual function, function pointer | indirect call `call [register]` | indirect target predictor |

A ternary `?:` doesn't necessarily become a jump: the compiler may turn it into a `cmov`, as in 1.5. Short-circuit evaluation goes the other way: `a && b` often adds a branch (skip `b` when `a` is false).

A virtual call is predictable to the extent that "the actual type at this call site" follows a pattern: if a loop always sees the same type, the target is the same every time and almost never wrong; if types are mixed at random, every call can miss, just like the unsorted case in 1.5.

## 2. Eliminating Branches: Select, Don't Guess

Part 1 ended on a puzzle. With a million random numbers, the `cmov` build sits flat at about 0.44 ns per element, more than 6× faster than the 2.87 ns of the branchy build. Yet when every number is even, the branchy build takes only about 0.25 ns and beats `cmov`. Removing a branch isn't free. This part covers what it trades away, the ways to do it, and when the trade pays.

### 2.1 Control Dependency vs Data Dependency: What Gets Traded

An `if` in machine code is a conditional jump: **which** instructions come next depends on the condition. That is a **control dependency**. As 1.2 showed, the CPU doesn't wait for it; it guesses a direction and runs ahead. When the guess is right, it doesn't matter how late the condition is computed. When it's wrong, the CPU pays about 15–20 cycles.

Eliminating the branch fixes which instructions run, and the condition only decides **which value to keep**. That is a **data dependency**: the result is known only once the condition and both candidate values are computed, and the next instruction that uses it has to wait too. There is nothing to guess, so nothing can be mispredicted. But there is also no running ahead, so the condition's latency is paid every time.

So eliminating a branch trades "an occasional 15–20 cycles" for "1–2 extra cycles every time." The five techniques below (2.2–2.6) are all this same trade, and 2.7 works out when it pays. All assembly below is real GCC 13.3 `-O2` output.

### 2.2 Ternary and cmov: Prepare Both, Pick One

```cpp
int pick(int input, int threshold, int value1, int value2) {
    return (input > threshold) ? value1 : value2;
}
```

GCC emits:

```asm
cmpl    %esi, %edi        # compare input with threshold
movl    %edx, %eax        # start with value1
cmovle  %ecx, %eax        # if input <= threshold, replace with value2
ret
```

**`cmov`** (conditional move) is not a jump. It always executes; the flags only decide whether the destination register takes the source value. The front end has nothing to guess and keeps fetching straight ahead.

The compiler does this only when evaluating both sides is safe and cheap:

- **A side has side effects** (a function call, a memory write, I/O): running both sides would change what the program does, so it can't.
- **A side reads memory that may not be valid to read**:

  ```cpp
  int load_or_zero(const int* p) {
      return p ? *p : 0;
  }
  ```

  GCC emits `testq %rdi, %rdi` + `je` and keeps the branch. A `cmov` would need to execute `*p` unconditionally, which crashes when `p` is null.
- **Both sides are long computations**: computing both throws away the work the cheap side would have saved.

The reverse also holds: write an `if` and the compiler may turn it into `cmov` on its own. 1.5's `even_sum` is one example; the branchy `sign` in the next section also compiles to `setne` + `cmovg` under GCC `-O2`. A ternary is only more likely to become `cmov`, not guaranteed. To be sure, read the assembly. Clang has `__builtin_unpredictable(cond)`, which tells the compiler the condition is hard to predict and nudges it toward `cmov`.

### 2.3 Branchless Arithmetic: Compute It from Comparisons and Masks

**A comparison already yields 0 or 1**:

```cpp
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    return 0;
}

int sign_branchless(int x) {
    return (x > 0) - (x < 0);   // comparisons yield 0 or 1: positive 1 - 0, negative 0 - 1
}
```

GCC compiles `sign_branchless` to `setg` for `x > 0`, uses `shrl $31` to pull out the sign bit as `x < 0`, and subtracts. No jump.

**Mask select**: the mask is all ones when the condition is true and all zeros when it's false; `&` and `|` then assemble the result.

```cpp
int select_mask(bool cond, int a, int b) {
    int mask = -static_cast<int>(cond);   // 1 -> 0xFFFFFFFF, 0 -> 0
    return (a & mask) | (b & ~mask);      // cond ? a : b
}
```

The mask has to be all ones or all zeros. ANDing with the `bool` directly is wrong: `1 & a` keeps only the lowest bit of `a`. To get a mask from the sign, `x >> 31` works: all ones for negative values, zero otherwise (C++20 defines signed right shift as arithmetic; before that it was implementation-defined).

**1.5's `even_sum` without `if`**:

```cpp
for (unsigned c = 0; c < n; ++c) {
    int x = data[c];
    sum += x & -static_cast<int>((x & 1) == 0);   // add x if even, 0 if odd
}
```

This compiles to `not`, `and $1`, `neg`, `and`, `add`, and the only branch left in the loop is the back edge. As with `cmov`, every `sum` waits for those instructions.

It suits numeric code: min/max, clamping. The costs are readability, and the fact that the compiler can usually turn a simple `if` into `cmov` by itself. Read the assembly before hand-writing it.

### 2.4 Lookup Tables: Index, Don't Branch

**A value table**: when the input range is small, precompute the result for every input and index with the input at run time.

```cpp
constexpr int fee_bps[3] = {2, 5, 10};   // fee rates for three order types, in basis points
int fee_lookup(unsigned type) { return fee_bps[type]; }
```

That compiles to a single `movl (%rax,%rdi,4), %eax`: truly branchless. The cost becomes one memory access: about 1 ns if the table is in L1D; about 3–5 ns once it spills into L2, already about the price of a mispredict; about 80–120 ns from memory, far worse (see <a href="/ref/cpu-memory/#latency" target="_blank" rel="noopener">Reference 2.1</a>). Lookup tables only pay when they're small; a hot-path table needs to stay in L1D.

**A function-pointer table**:

```cpp
using HandlerFunc = void(*)(const Order&);
constexpr HandlerFunc handlers[] = {handle_type_0, handle_type_1, handle_type_2};

void process_order(const Order& order) {
    if (order.type < 3) {
        handlers[order.type](order);
    }
}
```

compiles to:

```asm
movl    (%rdi), %eax            # order.type
cmpl    $2, %eax
ja      .L28                    # bounds check: a conditional jump
leaq    handlers(%rip), %rdx
jmp     *(%rdx,%rax,8)          # indirect jump: target read from the table
```

This doesn't eliminate the branch. It replaces several conditional jumps with **one indirect jump**, which the **indirect target predictor** handles (1.3). When order types follow a pattern (all the same, or a short repeating cycle), it almost never misses; when the types are randomly mixed, it misses often, just like a virtual call. The benefit is that however many types there are, there's only one jump to predict instead of a chain of `if`s. The bounds-check `ja` is almost never taken and easy to predict.

### 2.5 if-else Chains and switch: How the Compiler Lays Them Out

**An `if-else` chain**: every condition is its own conditional jump. The cost is how many of them run on the way through and how predictable each is: put the most common case first and most passes exit after one or two. Each jump has its own predictor history, so more conditions don't make each one harder to predict; going deeper just means passing more conditional jumps.

**`switch`**: GCC picks one of three layouts depending on how the `case` values are spread.

- **Dense cases, each doing something different → jump table**:

  ```cpp
  switch (kind) {
      case 0: handle_type_0(o); break;
      case 1: handle_type_1(o); break;
      // ... case 2, 3, 4
  }
  ```

  ```asm
  cmpl    $4, %eax
  ja      .L30                     # outside 0–4: jump away
  leaq    .L33(%rip), %rdx         # .L33 is a table of relative addresses of each case's code
  movslq  (%rdx,%rax,4), %rax
  addq    %rdx, %rax
  notrack jmp *%rax                # indirect jump
  ```

  Like the function-pointer table, it's one indirect jump. The lookup cost doesn't depend on the number of cases, but whether it's predicted well still depends on whether `kind` has a pattern.
- **Dense cases, each only returning a value → value table**:

  ```cpp
  switch (type) {
      case 0: return 2;
      case 1: return 5;
      // ... case 2, 3, 4
      default: return 0;
  }
  ```

  GCC emits a constant array (named `CSWTCH` in the assembly) and reads it with one `movl (%rax,%rdi,4), %eax`, leaving only an easy bounds check. This one is truly branchless.
- **Sparse cases (1, 10, 1000) → a chain of compares**: `cmpl $10` + `je`, `cmpl $1000` + `je`, and a `cmovne` for the last one. With many cases it becomes a binary-search tree of compares.

So "make the cases dense" helps, but what it buys is a jump table or a value table. The first still has to be predicted; only the second removes the branch.

### 2.6 Loop Unrolling: Fewer Back Edges, but the Win Isn't in Branches

One iteration does the work of several:

```cpp
long long sum_unroll4(const int* a, unsigned n) {
    long long s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    unsigned i = 0;
    for (; i + 4 <= n; i += 4) {
        s0 += a[i];
        s1 += a[i + 1];
        s2 += a[i + 2];
        s3 += a[i + 3];
    }
    for (; i < n; ++i) s0 += a[i];   // fewer than 4 left
    return s0 + s1 + s2 + s3;
}
```

**What it saves on branches**: one back edge per 4 elements. But as 1.3 showed, a loop's back edge is almost never mispredicted anyway, so unrolling mainly saves the `i++`, `cmp`, `jne` instructions themselves, not mispredicts. If the body has a hard-to-predict `if`, unrolling turns it into 4 of them; not one goes away.

**The real win**: the four accumulators `s0`–`s3` are four independent dependency chains that run in parallel (the multiple accumulators from [#2](/posts/memory-ordering-false-sharing-dependency-chains/)), which has nothing to do with branches.

- A short fixed-count loop like 4 iterations is fully unrolled by GCC `-O2` already; no need to do it by hand.
- To ask the compiler to unroll: GCC uses `#pragma GCC unroll 4`; `#pragma unroll` is Clang's spelling.
- More unrolling means more code, which competes for L1I and the uop cache. On a hot path, more is not always better.

### 2.7 Branchless Isn't Always Faster: How to Decide

Start with `even_sum`'s dependency chain per element:

<a href="/images/branch-prediction/cmov-chain.en.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/cmov-chain.en.svg" alt="Two dependency chains over cycles 1–8. With the branch kept and predicted right, only add is on the chain, 1 cycle per element; load, and, je are off the chain. The cmov build has add plus cmove on the chain, 2 cycles per element, and cmove waits for both the condition and sum + x. Measured: about 0.25 ns per element when predicted right, about 0.44 ns for cmov." loading="lazy" decoding="async"></a>

Every `sum` waits for the previous one. With the branch kept and predicted right, only one `add` sits on the chain, about 1 cycle; the `and` and `je` that test parity are off the chain and checked later. With `cmov`, the chain is `add` then `cmove`, and `cmove` also waits for the condition: about 2 cycles. 1.5's measurements line up: at p = 100% the branchy build takes about 0.25 ns per element and `cmov` about 0.44 ns; sorted, the branchy build takes about 0.40 ns, also faster than `cmov`.

**When to switch**: compare what each side adds per element.

$$
\underbrace{\text{miss rate} \times \text{cost of one mispredict}}_{\text{extra for the branch}}
\quad\text{vs}\quad
\underbrace{\text{extra per element for cmov}}_{\approx\, 0.44 - 0.25 = 0.19\ \text{ns}}
$$

One mispredict costs about 4.9 ns, so for this loop the break-even miss rate is about $0.19 / 4.9 \approx 4\%$: below about 4% keep the branch, above about 4% switch to `cmov`. In the measurements, at p = 95% (about 5% misses) the branchy build is already at about 0.51 ns, slower than `cmov`; at p = 100% it's about 0.25 ns, faster. That 4% belongs to this loop only: what `cmov` adds depends on what it puts on the chain, so another loop needs its own arithmetic.

**`cmov` can put memory accesses on the chain too**: a binary search that picks the next bounds with `cmov` never mispredicts, but the next load's address isn't known until this `cmov` finishes. With a small array in cache that's a clear win. With an array too large for the caches, every level waits a full memory latency (about 80–120 ns). The branchy version mispredicts half the time, but on the half it guesses right it has already issued the next level's load: speculation doubles as prefetching. So on large arrays, measure instead of assuming.

**How to decide**:

1. Read the assembly and confirm the branch is really there: the compiler may already have turned it into `cmov`, or turned your ternary back into a branch.
2. Measure the miss rate with `perf stat -e branches,branch-misses`. Below a few percent, keep the branch.
3. If the miss rate is high and the branch is on the critical path, switch to `cmov`, a mask, or a table, then measure again.
