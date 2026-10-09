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

Add up the even numbers among 16384 random integers in 0–199, and repeat that 10000 times. Run the same code again after sorting the array first, and it is several times faster. Not one value changed and the sum is identical; the only difference is whether "is the next number even?" follows a pattern.

Then compile both with `g++ -O2`, and they run at the same speed again. Both facts start from the branch predictor in the CPU's front end: why it has to guess, how it guesses, what a wrong guess costs, and how the compiler can remove the branch altogether.

## 1. The Branch Predictor: Why the CPU Guesses and What a Wrong Guess Costs

### 1.1 Where It Sits: The Front End

Most of the [quick reference's hardware map](/ref/cpu-memory/#map) is the data side: loads and stores, caches, memory. Branch prediction lives on the other side, the **front end**, which fetches and decodes instructions and feeds them to the back end. In order:

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

A branch needs two guesses: **taken or not** (direction) and **where to** (target).

- **Target**: the **BTB** (branch target buffer) records, by the branch instruction's address, where it went last time; about 4000–12000 entries. One lookup at fetch tells whether this chunk holds a known branch and where it goes.
- **Function returns**: the target can differ every time (it depends on the caller), so they use the **RAS** (return address stack): `call` pushes the return address and `ret` pops it, 16–32 entries. Recursion or call depth beyond that mispredicts.
- **Indirect branches** (virtual functions, function pointers, `switch` jump tables): one instruction can go to many targets; the **indirect target predictor** records the target by "this instruction + recent history".
- **Direction**: the simplest scheme gives each branch a **2-bit saturating counter**: +1 when taken, −1 when not, clamped to 0–3, and predict "taken" at ≥ 2. It predicts loops well (taken 99 times, not taken once at the end, only the last one is wrong), and one odd outcome doesn't flip its mind at once.

Modern predictors add **history** on top: the outcomes (taken / not taken) of the last 50–1000 branches, recorded as one **global history** string, are used together with the branch address to look up a table. That lets them learn patterns like "if the previous branch was taken, this one isn't" or "taken once every 3 times". The mainstream design (the TAGE family) uses several tables with different history lengths and picks the longest one that hits. The upshot: **a branch with a pattern can be learned, even a long pattern; a branch without one can't be learned by anyone.** A condition that is a fresh 50/50 coin flip every time is predicted right half the time by even the best predictor.

In ordinary programs these structures together predict well over 95%–99% of branches.

### 1.4 What a Wrong Guess Costs: Flushing the Pipeline

When a branch executes and turns out to be mispredicted:

1. Every instruction fetched after it (still in the pipeline, already in the ROB, even already executed) is discarded.
2. Fetch goes back to the correct address and starts over.
3. The new instructions go through fetch, decode and rename again before the back end fills up.

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
- **Sorted**: each value in 0–199 appears about 82 times, so the sorted array alternates in runs: 82 evens, 82 odds, 82 evens… 200 runs in all. The direction changes only at run boundaries, so a pass of 16384 mispredicts only about 200 times, about 1%.

So the sorted run is several times faster (estimated from the numbers above). The lesson: **the same branch in the same code is predictable or not depending on the data.**

**There is a compiler trap here**: GCC 13.3 on x86-64 turns this `if` branch-free from `-O1` up. The inner loop has only an `and` (take the low bit) and a `cmove` (move the new sum into `evenSum` only if the condition holds), no conditional jump; `-O3` vectorizes it as well. Then sorted and unsorted run at the same speed and the experiment shows nothing. To see the cost of mispredictions you have to add `-fno-if-conversion -fno-if-conversion2 -fno-tree-vectorize`, which leaves a `je` in the inner loop. So before arguing about whether there's a branch, read the assembly. (Why `cmov` removes a branch and when the compiler won't use it is in Part 2.)

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
