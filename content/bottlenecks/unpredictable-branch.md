---
title: "Unpredictable Branch"
num: 15
signal: "perf stat: IPC < 1, branch miss rate > 3–5%; sampling on branch-misses, annotate shows the samples piled on one conditional jump"
source: "This site's #7 Branch Prediction 2.7 (Intel's performance-patterns has no such card)"
---

> - **Signal**: trace it from the totals down to the line, in layers.
>   - **Totals**: in [perf stat](/posts/low-latency-perf-profiling/#stat-ratios), IPC < 1 and the branch miss rate (`branch-misses / branches`) > 3–5%.
>   - **Function**: `perf record -e branch-misses` samples on mispredictions (add `:pp` on Intel for precise sampling); `perf report` shows which function they pile up in.
>   - **Line**: in `perf annotate` the samples pile up on one conditional jump (`jcc`); compiled with `-g` it maps back to a source line. Without precise sampling the samples skid one or two instructions later, so look just before them.
>   - **Source**: the branch's direction is decided by the data and close to random, for example dispatching on message type, handling buy and sell sides separately, or comparing two random numbers.
> - **Cause**: a wrong guess throws away all the work started after it, about 15–20 cycles; with random data the predictor is right only half the time.
> - **Fix**:
>   - **Read the assembly first**: the compiler may already have turned it into a `cmov`, and then there is nothing to change.
>   - **Both sides are cheap and touch no memory**: write a ternary so the compiler emits `cmov`, or compute the result directly from the comparison and a mask.
>   - **Several ways by type**: replace the `if-else` chain with a table lookup, or first split the data into batches by type, so there is no branch inside each batch.
> - **When not to change it**:
>   - **A well-predicted branch**: leaving it is faster. `cmov` trades "guess which way" for "wait for the condition", and pays a few more instructions on the chain every time.
>   - **The next address to read depends on this comparison**: binary search over a large array, for example. With the branch kept, the CPU guesses and issues the next read early; with `cmov` it has to wait for this read to come back, which is slower.
> - **Find the break-even point for each loop**: compare "miss rate × cost of one miss" with "what `cmov` adds per iteration". The loop measured in #7 broke even at about 4%; another loop needs its own measurement, it is not a general threshold.
> - **Verify**: output unchanged; the branch miss rate falls, and paired timing confirms it really got faster.
> - **Mechanism**: why a wrong guess is expensive is in [#7 1.4](/posts/branch-prediction-branch-optimization/#14-what-a-wrong-guess-costs-flushing-the-pipeline); `cmov`, masks and table lookups are in [#7 Part 2](/posts/branch-prediction-branch-optimization/#22-ternary-and-cmov-prepare-both-pick-one); the break-even point and the binary-search counterexample are in [#7 2.7](/posts/branch-prediction-branch-optimization/#27-branchless-isnt-always-faster-how-to-decide).
