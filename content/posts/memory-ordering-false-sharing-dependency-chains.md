---
title: "Trading System Notes #2: One Cache Line, Two Questions — Memory Ordering, False Sharing, and the Cost of a Dependency Chain"
date: 2026-09-15
slug: "memory-ordering-false-sharing-dependency-chains"
description: "Why the store buffer makes your own writes invisible to other cores, why x86 forbids three reorderings and allows one, how release/acquire buys back just enough order, why false sharing is a completely different problem from a stale read, and why loop unrolling has an optimal accumulator count."
summary: "The store buffer and the cache-coherence protocol are one piece of hardware, but they create two unrelated engineering problems. One is correctness: does a thread see the right value, in the right order — solved by memory_order and release/acquire pairing. The other is performance: how many cycles does touching shared or dependent data cost, even when every value read is already correct — solved by cache-line layout and instruction scheduling. Conflating the two is the single most common confusion in this part of systems programming."
categories: [Systems]
tags: [cpp, memory-model, atomics, cache-coherence, false-sharing, mesi, x86, hft, low-latency, pipelining]
toc: true
homepage: false
---

# Trading System Notes #2: One Cache Line, Two Questions — Memory Ordering, False Sharing, and the Cost of a Dependency Chain

> **One-line thesis**: a store buffer, an invalidate queue, and a 64-byte cache line are one piece of hardware. But they generate two completely independent engineering questions — *is the value I just read correct?* and *how many cycles did it cost to get it?* — and the single most common confusion in this part of systems programming is treating those as the same question.

## What You're Actually Fighting

Two questions, same hardware, and it matters which one you're asking:

**Question 1 — correctness.** If thread A writes `x = 1` and thread B reads `x`, does B ever see `1`? If B also reads `y` right after, is it guaranteed to see whatever A wrote to `y` *before* writing `x`? This question has a binary answer — right or wrong — and the tool for it is the C++ memory model: `std::atomic`, `memory_order`, release/acquire.

**Question 2 — performance.** Assume every read in your program is already correct — no data races, no missing fences, nothing wrong. Now: why does touching one particular variable cost 40 cycles instead of 4? Why did splitting one accumulator into four make the loop twice as fast, with the exact same arithmetic? This question has no binary answer, only a number of cycles, and the tool for it is cache-line layout and instruction scheduling — `alignas`, breaking dependency chains, watching the register file.

Both questions are answered by the *same* underlying machinery: cores, cache lines, the coherence protocol that keeps them consistent. That shared machinery is exactly why it's so easy to blur the two together — "the cache line got invalidated and reloaded" is a sentence that shows up in the explanation of *both* questions, for two unrelated reasons. This post keeps them on separate tracks on purpose: sections 1–3 are the correctness axis, sections 4–5 are the performance axis, and the transition between them is the point where the confusion usually happens — so it gets called out explicitly when we get there.

<!--
╔══════════════════════════════════════════════════════════════════╗
║  🖼  ILLUSTRATION  ——  One cache line, two questions             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Academic graphite pencil illustration on clean white paper.     ║
║  16:9. Precise technical linework, careful cross-hatching for    ║
║  shading and depth. Monochrome graphite only — no color, no      ║
║  watercolor, no graph-paper grid. Scientific-journal /           ║
║  textbook figure. NOT cartoon, NOT colorful.                     ║
║                                                                  ║
║  Topic: the same piece of hardware (a cache line) answers two    ║
║  completely unrelated engineering questions — is the value       ║
║  correct, and how many cycles did it cost.                       ║
║                                                                  ║
║  Main metaphor: a single precise rectangular data block labeled  ║
║  "CACHE LINE — 64 BYTES", drawn like a technical cross-section   ║
║  with faint byte divisions, sitting at the center. Two ruled     ║
║  callout lines branch off it to two different instruments on     ║
║  either side.                                                    ║
║                                                                  ║
║  Layout: single central object with two branching callouts       ║
║  (left/right symmetric).                                         ║
║                                                                  ║
║  Objects and labels:                                             ║
║   - center block: "CACHE LINE — 64 BYTES"                        ║
║   - left, a rubber inspection stamp stamping a checkmark onto a  ║
║     small ledger sheet: "CORRECT?" / "memory order /              ║
║     release-acquire"                                             ║
║   - right, a precise mechanical stopwatch/chronometer with a     ║
║     visible dial and sweep hand: "HOW MANY CYCLES?" / "layout /  ║
║     dependency chains"                                           ║
║   - thin dashed rule beneath the center block: "same hardware,   ║
║     two independent axes"                                        ║
║                                                                  ║
║  Title (top, large): "One Cache Line, Two Questions"             ║
║  Subtitle: "The same hardware answers two unrelated questions"   ║
║  Footer caption: "Correctness and performance are orthogonal —   ║
║  conflating them is the most common confusion in this part of    ║
║  systems programming."                                           ║
║                                                                  ║
║  All text in English. No Chinese characters. No color fills.     ║
║  No gradients. Monochrome graphite only.                         ║
╚══════════════════════════════════════════════════════════════════╝
-->

![One cache line, two questions — a correctness stamp and a stopwatch pointed at the same 64-byte cache line](/images/memory-model-cache-line/two-axes.png)

---

## 1. The Store Buffer: Why Your Own Writes Lie to Everyone Else

Start with a fact that sounds wrong the first time you hear it: **when your thread executes `x = 1`, that write does not go to the cache.** It goes into a small, private, per-core structure called the **store buffer** — think of it as a notebook the core jots the write into before actually filing it away — and the instruction retires immediately. Your thread moves on to the next instruction without waiting.

Why does the hardware do this? Because actually committing a write to a cache line the core doesn't already own outright is expensive: the coherence protocol (MESI) has to send a **Request For Ownership (RFO)** to every other core that might be caching that line, wait for them to invalidate their copies, and only then let the write land. That round-trip is tens of nanoseconds. If the pipeline blocked on every store waiting for that, you'd throw away the entire point of having a pipeline. So the store buffer exists purely to **decouple "the instruction is done" from "the write is globally visible."** The instruction retires the moment it's queued in the notebook; the RFO and the actual cache update happen asynchronously, in the background, whenever the line shows up.

This creates exactly one gap, and everything about memory ordering in this post is a consequence of it: **for some window of time — typically tens of nanoseconds, an eternity at 4+ GHz — a write has already "happened" from thread A's point of view, but no other core can see it yet, because it's still sitting in A's private notebook.**

Note the asymmetry carefully: thread A itself never notices this gap. If A writes `x` and then reads `x` again three instructions later, the CPU forwards the value straight out of the store buffer (called **store-to-load forwarding**, which section 5 comes back to) — A always sees its own writes in program order. The gap is only visible from *outside* — from any other core's perspective, there is a real, physical delay between "A's store instruction retired" and "the write is visible anywhere else." That delay is not a bug and not a compiler artifact; it is a direct, unavoidable consequence of buffering writes to survive at 4 GHz.

Everything from here is about that one gap: how it turns into a specific class of bugs (section 2), and how C++ gives you a vocabulary to close it exactly where you need to, and nowhere else (section 3).

---

## 2. The Invalidate Queue, Four Reorderings, and x86's "Forbid Three, Allow One"

The store buffer explains why *A's* write is delayed. There's a mirror-image structure on the *receiving* side that explains why B might keep reading a stale value even after A's write has left the notebook and the RFO has arrived.

### The inbox on the receiving side

When core B's cache holds a line, and core A's RFO shows up asking to invalidate it, B doesn't have to process that invalidation instantly either. It can drop the message into an **invalidate queue** — an inbox — and send the acknowledgment back to A immediately, so A isn't blocked waiting for B. B then works through its inbox whenever it gets around to it. If B executes a load for that address *before* it has processed the pending invalidate sitting in its inbox, it can still read the old, stale cached value — even though, as far as the protocol is concerned, that line was already invalidated.

So there are now two independent buffering structures, one on each side of every cross-core write: the store buffer delays *publishing*, the invalidate queue delays *noticing*. Put together, they are the physical root cause of every kind of memory reordering you'll ever debug on a multi-core x86 box.

### Four reorderings, and the one x86 keeps

In the general (formal) shared-memory model, there are exactly four ways a load and a store to *different* addresses can appear reordered to another observer:

| Reordering | Meaning | Allowed on x86? |
|---|---|---|
| **StoreStore** | two of your stores become visible out of order | No |
| **LoadLoad** | two of your loads read memory out of order | No |
| **LoadStore** | a later store becomes visible before an earlier load completes | No |
| **StoreLoad** | a later load runs before an earlier store becomes visible | **Yes** |

x86 uses a model called **TSO (Total Store Order)**, and the one-line summary of it is "forbid three, allow one." The forbidden three are guaranteed by hardware for free — a plain `mov` already has that ordering built in, no fence needed. The one that's allowed, StoreLoad, is *exactly* the store-buffer gap from section 1 given a name: your store sits in the notebook while a subsequent load — to a different address — is free to run immediately, so from another core's point of view your load can appear to have completed before your earlier store did. This is the textbook cause of the classic "I set the flag, then checked another variable, and the other thread saw them in the wrong order" bug — and on x86 it is the *only* reordering you have to explicitly guard against; every other combination the hardware already forbids on its own.

### A bug the hardware can't see: the compiler got there first

Before blaming the CPU, check the compiler. This loop:

```cpp
while (ready == false) {}
```

looks like it polls memory every iteration. Without `volatile` or `std::atomic`, the compiler is free to assume nothing outside this thread can change `ready`, load it into a register exactly once, and rewrite the whole loop as:

```cpp
if (!ready) { while (true) {} }   // infinite loop — the load never happens again
```

This has *nothing to do with the CPU's memory model.* It's a pure compiler-level optimization, legal precisely because ordinary (non-atomic, non-volatile) memory carries no promise that another thread might be watching it. `volatile` stops the compiler from doing this — it forces a real load every iteration — but that's *all* it does. **`volatile` ≠ synchronization.** It says nothing about ordering relative to other memory operations, and nothing about the store-buffer/invalidate-queue gap from the last two sections. A `volatile bool` still lets a reader see a stale value for the full duration of that gap; it only guarantees the compiler won't hide the memory access from you while you wait. Fixing this loop for real needs `std::atomic<bool>`, which is section 3.

---

<svg viewBox="0 0 760 460" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Store buffer on the writing core and invalidate queue on the reading core create a visibility gap between a store retiring and the write becoming observable elsewhere" style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif">
  <style>
    .bg    { fill: #fbfaf7; }
    .panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .ink   { fill: #1c1b18; }
    .muted { fill: #6b6558; }
    .core  { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .buf   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .inbox { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.6; }
    .line  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .arrow { stroke: #8a8474; stroke-width: 2; fill: none; marker-end: url(#ah); }
    .rfo   { stroke: #c15b3f; stroke-width: 2; fill: none; marker-end: url(#ah2); }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .lbl   { fill: #3a372f; font-size: 11px; }
    .cap   { fill: #6b6558; font-size: 10.5px; }
    .gap   { fill: #c15b3f; font-size: 11px; font-weight: 700; }
    @media (prefers-color-scheme: dark) {
      .bg    { fill: #17161b; }
      .panel { fill: #201f26; stroke: #3a3945; }
      .ink   { fill: #e9e7ef; }
      .muted { fill: #a19caf; }
      .core  { fill: #2a2933; stroke: #47454f; }
      .buf   { fill: #33421f; stroke: #8fb257; }
      .inbox { fill: #4a2f2c; stroke: #8f5a4c; }
      .line  { fill: #23262c; stroke: #3f4650; }
      .arrow { stroke: #9a9384; }
      .rfo   { stroke: #e0795b; }
      .title { fill: #e9e7ef; }
      .lbl   { fill: #d7d3c8; }
      .cap   { fill: #a19caf; }
      .gap   { fill: #e0795b; }
    }
  </style>
  <defs>
    <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="760" height="460" rx="10"/>
  <text class="title" x="24" y="30">Why B can still read stale x after A's store has "retired"</text>

  <rect class="panel" x="24" y="48" width="320" height="230" rx="8"/>
  <text class="muted" x="40" y="70" font-size="12" font-weight="700">CORE A (writer)</text>
  <rect class="core" x="40" y="86" width="120" height="46" rx="6"/>
  <text class="lbl" x="50" y="106">x = 1</text>
  <text class="cap" x="50" y="122">store instruction</text>
  <rect class="buf" x="40" y="148" width="270" height="46" rx="6"/>
  <text class="lbl" x="50" y="168" font-weight="700">Store Buffer ("the notebook")</text>
  <text class="cap" x="50" y="184">x=1 queued — instruction retires HERE</text>
  <path class="arrow" d="M100 132 L100 148"/>
  <path class="rfo" d="M310 171 C 350 171, 372 200, 392 228"/>
  <text class="cap" x="316" y="214" fill="#c15b3f">RFO sent, async</text>
  <text class="gap" x="40" y="240">A already believes x=1 is done.</text>
  <text class="gap" x="40" y="256">No other core can see it yet.</text>

  <rect class="panel" x="416" y="48" width="320" height="230" rx="8"/>
  <text class="muted" x="432" y="70" font-size="12" font-weight="700">CORE B (reader)</text>
  <rect class="inbox" x="432" y="86" width="270" height="46" rx="6"/>
  <text class="lbl" x="442" y="106" font-weight="700">Invalidate Queue ("the inbox")</text>
  <text class="cap" x="442" y="122">RFO for x sits here, ACKed immediately</text>
  <rect class="core" x="432" y="148" width="120" height="46" rx="6"/>
  <text class="lbl" x="442" y="168">read x</text>
  <text class="cap" x="442" y="184">may run before inbox is drained</text>
  <path class="arrow" d="M492 132 L492 148"/>
  <text class="gap" x="432" y="240">If B's load beats its own inbox,</text>
  <text class="gap" x="432" y="256">B still reads the OLD cached x.</text>

  <rect class="panel" x="220" y="300" width="320" height="140" rx="8"/>
  <text class="title" x="236" y="324" font-size="12.5">What closes this gap</text>
  <text class="cap" x="236" y="346" font-size="11">Nothing, by default — this gap is the hardware's normal behavior.</text>
  <text class="cap" x="236" y="364" font-size="11">x86-TSO forbids reordering it with other loads/stores to</text>
  <text class="cap" x="236" y="380" font-size="11">different addresses (StoreStore/LoadLoad/LoadStore) —</text>
  <text class="cap" x="236" y="396" font-size="11">but StoreLoad reordering, born from exactly this gap,</text>
  <text class="cap" x="236" y="412" font-size="11" font-weight="700">is the one x86 allows. Section 3 shows how to close it.</text>
</svg>

> Figure: A's store retires into its own store buffer instantly, but the RFO that actually claims the cache line is asynchronous. B's invalidate queue absorbs that RFO without stalling B's pipeline, which means a load that races ahead of B's own inbox can still observe the pre-write value. Both buffers exist for the same reason — don't stall the pipeline for a cross-core round trip — and together they are the entire physical cause of section 2's four reorderings.

---

## 3. Release/Acquire: Buying Back Just Enough Order

`std::atomic` with the right `memory_order` closes the gap from sections 1–2 *exactly where you name it*, and nowhere else — that specificity is the whole design intent. C++ exposes six orderings: `relaxed`, `consume` (deprecated in practice — compilers treat it as `acquire`), `acquire`, `release`, `acq_rel`, and `seq_cst`. The two that matter most in practice are **release** and **acquire**, and the cleanest mental model for them is **publish/subscribe**:

- A **release** store says: *"everything I wrote before this point is now final — go ahead and publish it."*
- An **acquire** load says: *"give me the latest value, and don't let anything I do after this point get reordered ahead of it."*

When an acquire load *observes* a value written by a release store **on that same atomic variable**, the two form a pair, and C++ guarantees a **happens-before** edge across threads: everything the writer did before the release is guaranteed visible to everything the reader does after the matching acquire. Nothing else needs to be atomic. A minimal example:

```cpp
struct SPSCFlag {
  std::atomic<bool> ready{false};
  int payload = 0;   // ordinary int — not atomic, and doesn't need to be
};

// producer thread
void publish(SPSCFlag &f, int value) noexcept {
  f.payload = value;                                // 1. plain write
  f.ready.store(true, std::memory_order_release);    // 2. release: "1 is now final"
}

// consumer thread
auto try_consume(SPSCFlag &f) noexcept -> std::optional<int> {
  if (f.ready.load(std::memory_order_acquire)) {     // 3. acquire: paired with 2
    return f.payload;                                // 4. guaranteed to see step 1's value
  }
  return std::nullopt;
}
```

`payload` is an ordinary, non-atomic `int`. It's safe *only* because it's carried across by the release/acquire pair on `ready` — this is the standard shape of every SPSC (single-producer single-consumer) ring buffer you'll find in a trading system: one atomic index for synchronization, everything else plain.

### Why x86 barely charges for this, and ARM does

Go back to the "forbid three, allow one" table in section 2. Acquire and release only need to forbid reorderings that x86-TSO *already* forbids on every plain `mov` — LoadLoad, LoadStore, StoreStore. So on x86, a `memory_order_acquire` load and a `memory_order_release` store compile down to an ordinary load and an ordinary store; the hardware was already going to honor that ordering. **Acquire/release is nearly free on x86** — that's not a coincidence, it's the whole reason the C++ model has separate `acquire`/`release` orderings instead of just relaxed-or-nothing.

`seq_cst`, on the other hand, additionally forbids the *one* reordering x86 does allow — StoreLoad — and that requires a real fence: `MFENCE`. That's the one atomic operation on x86 that's genuinely expensive relative to a plain load/store, and it's the reason `std::atomic`'s *default* memory order (`seq_cst`, if you don't specify one) is more costly than it needs to be for code that only needs publish/subscribe semantics.

On a weak-memory architecture like ARM, none of the "forbid three" comes for free — the hardware is allowed to reorder all four combinations unless told otherwise, so acquire/release need real instructions (`LDAR`/`STLR` on ARMv8, explicit `DMB` barriers on ARMv7). This is *why* the C++ memory model is specified abstractly instead of just "do what x86 does": the semantics are portable, but the price tag is architecture-dependent, and code that "happens to work" on x86 because acquire/release are nearly free there can be measurably slower — or, if someone reached for `volatile` instead of `atomic` out of habit, outright broken — on ARM.

---

## 4. False Sharing: When Correctness Was Never the Question

This is the section where the two axes from the introduction split apart for good, so it's worth being explicit: **everything below can happen with code that is already 100% correct** — every read sees the right value, every `memory_order` is exactly right, there is no bug per sections 1–3 at all. This is a pure performance problem, and no amount of atomics or fences fixes it.

### The unit of coherence is 64 bytes, not one variable

The MESI protocol doesn't invalidate individual variables — it invalidates **cache lines**, and a line is a fixed 64 bytes on essentially every current x86 core. If two threads each own a completely unrelated `int`, and those two `int`s happen to land in the same 64-byte line — say, adjacent fields in a struct — then every write by thread A to *its* variable invalidates the *entire line*, including thread B's variable, forcing B to reload data it never asked to share. This is **false sharing**: the sharing is an accident of memory layout, not a real logical relationship between the two variables.

### This is a different mechanism from section 2's stale read — say why, precisely

It's tempting to file this under "the invalidate-queue thing from section 2" — same MESI messages, same cache lines, same vocabulary. That's the confusion this whole post is structured to head off. Line them up directly:

| | Section 2 (correctness) | Section 4 (performance) |
|---|---|---|
| What's being protected | *Is the value I read correct?* | *How many cycles did reading it cost?* |
| Failure mode | A stale read, once, in a specific ordering window | Repeated, ongoing exclusive-ownership hand-off, every write, forever |
| Fixed by | `memory_order` / release-acquire | Physical layout (`alignas`) |
| Happens with zero atomics? | No — needs a race on real shared data | **Yes** — two `int`s with no synchronization at all still false-share |
| Happens with perfect `memory_order`? | N/A, this *is* the fix | **Yes** — correct atomics do nothing to stop it |

That last row is the sharpest test: take two completely unrelated, unsynchronized `int` counters, each written only by its own thread, no atomics anywhere, no data race by any reasonable definition of the term — and they will still ping-pong if they share a cache line, because the *protocol* doesn't know or care that the two variables are logically unrelated; it only knows two different cores keep asking for exclusive ownership of the same 64 bytes. Section 2's mechanism requires an actual cross-thread dependency on a value. Section 4's mechanism requires nothing but unlucky struct layout — it is entirely a statement about the physical cost of *ownership churn*, independent of whether any value was ever read incorrectly.

### The fix, and what it doesn't fix

```cpp
struct alignas(64) PaddedCounter {
  std::atomic<uint64_t> value{0};
  // padding is implicit: alignas(64) rounds sizeof() up to the next 64-byte boundary
};

PaddedCounter counters[num_threads];   // each counter now owns a whole cache line
```

`alignas(64)` (or the portable `std::hardware_destructive_interference_size` constant) forces each hot variable onto its own line, so writes from different threads no longer collide. But this only fixes *false* sharing — variables that shouldn't have been coupled in the first place. If multiple threads are genuinely, logically incrementing the *same* atomic counter, padding does nothing: that's **true sharing**, the line has to move because the data really is shared, and that cost is inherent to the algorithm, not a layout accident.

For true sharing that's still too hot, the standard mitigation (the pattern behind LMAX Disruptor-style designs) is to stop touching the shared line on every single operation: keep a **locally-cached copy** of the last-seen cursor/value, batch several operations against the local copy, and only re-synchronize against the real shared line periodically. You trade a bounded amount of staleness for a large reduction in cross-core traffic — conceptually the same "notebook" idea as the store buffer in section 1, just applied deliberately at the application level instead of automatically by hardware.

### A third, unrelated problem hiding in the same word: L3 and Intel CAT

One more distinction worth having on hand, because it uses the word "shared cache" and gets folded into "false sharing" conversations by accident: **L1 and L2 are private per core; L3 is architecturally shared across the whole socket, and that's normal and fine.** A hot L3 isn't a false-sharing problem — there's no coherence protocol churn from *sharing* L3, because sharing L3 was the design. The actual risk is **capacity contention**: an unrelated process on another core, with no logical connection to your program at all, can run through enough data to evict your working set out of the shared L3 purely by using up space — a "noisy neighbor," not a coherence problem. That's what **Intel CAT (Cache Allocation Technology)**, configured via `pqos`, is for: it partitions L3 into ways and reserves a guaranteed slice for your process, so a noisy neighbor can fill the rest of L3 as much as it wants without evicting your data. Three different problems, three different fixes: a stale read is a section-2/3 ordering problem; ping-pong between two cooperating threads is a section-4 layout problem; a hot shared L3 getting evicted by an unrelated process is a capacity problem CAT solves — none of the three fixes solve either of the other two.

---

## 5. Instruction-Level Parallelism: You're Racing the Dependency Chain, Not the Instruction Count

Same performance axis as section 4, different resource: instead of "which cache line does this address belong to," this section is about "which instruction is the CPU's pipeline actually waiting on." The two-line summary: a modern core is superscalar and pipelined — it can have several instructions in flight simultaneously — but it can only start an instruction once every one of its inputs is ready. **The number of arithmetic operations in your code barely matters. The length of the longest dependency chain is what determines wall-clock time.**

### Two arrangements, same op count, different cost

```cpp
// chained: every multiply/add depends on the one before it
double chained(double a, double b, double c, double d) {
  return ((a * b) + c) + d;   // one dependency chain: mul -> add -> add
}

// independent: the multiply is the only thing on the critical path
double parallel(double a, double b, double c, double d) {
  double sum = c + d;         // runs concurrently with the multiply below
  return (a * b) + sum;       // only 1 multiply + 1 add are actually chained
}
```

Same three operations, same result. `chained` forces the CPU to execute mul → add → add strictly in sequence — total latency is the *sum* of all three. `parallel` computes `c + d` and `a * b` at the same time (they don't depend on each other), so the critical path is only one multiply plus one add; the CPU finishes roughly a third faster despite doing "the same work." This is the whole game of instruction-level parallelism: **rearrange independent work so the pipeline can overlap it, instead of leaving accidental dependencies that force it to wait.**

The two things a pipeline actually stalls on are **data hazards** (the next instruction needs a value the previous one hasn't produced yet — everything in this section) and **control hazards** (a branch whose direction isn't known yet, which is what speculative/out-of-order execution from section 2 is there to hide). Fixing data hazards comes down to three priorities: break unnecessary dependency chains, get data into registers instead of re-reading memory, and balance which execution ports different instruction types compete for.

### A trap in priority one: dependencies that aren't real

Some instructions — `popcnt`, `lzcnt`, `tzcnt` are the well-documented examples, on several Intel and AMD generations — treat their **destination register as an implicit input**, even though the result they compute never actually depends on the register's previous contents. The hardware doesn't know that; it just sees "this instruction reads register X," and a loop that reuses the same destination register every iteration ends up chained across iterations for no logical reason at all:

```asm
; false dependency: rax "depends" on its own stale value from last iteration,
; even though popcnt's result has nothing to do with rax's old contents
loop:
    popcnt rax, rbx
    ...
    jmp loop

; fix: zero the destination immediately before — the CPU's zeroing-idiom
; detector recognizes xor-self as "no real dependency" and breaks the chain
loop_fixed:
    xor eax, eax
    popcnt rax, rbx
    ...
    jmp loop_fixed
```

This is a narrow, specific erratum — not something you'll spot by reading source, because the false dependency lives in the microarchitecture, not in your code's logic. It's realistically a job for a profiler (`perf stat` counting stalled cycles against expectation) or a compiler that already knows the erratum list, not for eyeballing — the practical takeaway is knowing the *pattern* exists, so an unexplained stall on a chain that "shouldn't" be a chain has somewhere to point.

### Priority one, overused: register spill

Breaking dependency chains by hand — the fix in the very first code sample above, and the technique the next section pushes further — means creating more *independent* values in flight at once. Independent values need their own registers. x86-64 has 16 general-purpose architectural registers. Unroll too aggressively, chase independence too far, and you run out: the compiler starts **spilling** the extra live values to the stack, which means the "fix" for a dependency stall quietly reintroduces memory traffic — the exact kind of cost priority one was trying to eliminate in the first place. It is a genuinely ironic failure mode: the technique for fixing stalls, used past the point the register file can hold, causes its own kind of stall.

### STLF: the payoff comes back to section 1

Store-to-load forwarding — mentioned in passing back in section 1 — is why a store followed immediately by a load to the same address doesn't have to round-trip through the cache: the CPU forwards the value straight out of the store buffer. It's a genuine latency win, but it has a strict physical requirement: **the load's address, width, and alignment have to line up exactly with a single buffered store entry.** Forwarding matches one specific record — it does not stitch together partial overlaps. A concrete failure case: write 4 bytes, then immediately read 8 bytes starting at the same address. The read isn't fully satisfied by any single buffered store, forwarding fails, and the load falls back to the slow path — waiting for the write to actually land in cache before it can be read back. The store buffer that made section 1's writes cheap is the same structure that makes this shortcut possible, and the same structure whose width/alignment rules make the shortcut fail silently if you're not careful about it.

### Turning "break the dependency chain" into a formula

The `chained` vs. `parallel` example generalizes directly to loops: instead of one running accumulator (a single, fully serial dependency chain — one operation every `latency` cycles), split the accumulation across `K` independent accumulators and combine them once at the end.

```cpp
// naive: one accumulator, one fully serial dependency chain
double dot_serial(const double *a, const double *b, size_t n) {
  double acc = 0.0;
  for (size_t i = 0; i < n; ++i) acc += a[i] * b[i];   // each += waits on the last
  return acc;
}

// K independent accumulators, combined once — not every iteration
template <size_t K>
double dot_unrolled(const double *a, const double *b, size_t n) {
  double acc[K] = {};
  size_t i = 0;
  for (; i + K <= n; i += K)
    for (size_t k = 0; k < K; ++k)
      acc[k] += a[i + k] * b[i + k];        // K chains, no cross-iteration dependency
  for (; i < n; ++i) acc[0] += a[i] * b[i];  // remainder
  double total = 0.0;
  for (double v : acc) total += v;
  return total;
}
```

How large should `K` be? Exactly large enough to keep the execution ports fed while a single chain's `latency` is still in flight: **K = latency × throughput**, where throughput is how many of that operation the core can *issue* per cycle. For a fused multiply-add with 4-cycle latency and two FMA-capable ports (a fairly typical modern desktop/server core):

| K (accumulators) | cycles per element | ops/cycle achieved | vs. one-port ceiling |
|---|---|---|---|
| 1 | 4 (fully chained) | 0.25 | 25% |
| 4 | 4 | 1.0 | 100% — saturates one port |
| 8 | 4 | 2.0 | 200% — saturates both ports |
| 16 | 4 | 2.0 | no further gain — the ports, not the chain, are now the ceiling |

`K = 8` is the sweet spot here — enough independent work to hide the full 4-cycle latency behind both ports' throughput, with no benefit (and, per the register-spill trap above, real risk) in going further. This is a standard technique (the derivation is the same one Agner Fog's optimization manuals walk through for any latency/throughput pair), and the honest caveat that goes with it: this ceiling assumes the arithmetic units are the bottleneck. In practice, memory bandwidth or the number of load ports feeding data in can cap throughput first — this is exactly the **compute-bound vs. memory-bound** distinction at the heart of the **roofline model** — so the formula tells you the arithmetic ceiling, and `perf` tells you whether you actually reached it.

---

## Recap

1. **Two axes, one hardware.** Correctness — *is the value right* — and performance — *how many cycles did it cost* — are answered by the same cores, cache lines, and coherence protocol, which is exactly why they get confused. Keep asking which question a given optimization actually answers.
2. **The store buffer (§1) and the invalidate queue (§2) are the physical cause of every x86 reordering you'll debug.** x86-TSO forbids three of the four possible reorderings for free and allows exactly one — StoreLoad — because that one is just the store-buffer gap given a name.
3. **`volatile` stops the compiler from hiding a read from you. It says nothing about cross-core ordering.** That's `std::atomic`'s job.
4. **Release/acquire buys back exactly the ordering you name, and nearly for free on x86** — because acquire/release only need what TSO already guarantees; only `seq_cst` needs a real fence (`MFENCE`) to kill the one reordering x86 allows.
5. **False sharing (§4) is a completely different mechanism from a stale read (§2)** — it needs no atomics, no race, and no incorrect value to be expensive; it's purely the cost of exclusive-ownership churn on an accidentally-shared 64-byte line, fixed by layout (`alignas`), not by ordering.
6. **A hot, shared L3 is a third, unrelated problem** — capacity contention from a noisy neighbor, not coherence traffic — and Intel CAT fixes that one specifically.
7. **Instruction count doesn't determine latency; the longest dependency chain does.** Breaking chains (multi-accumulator unrolling, `K = latency × throughput`) buys real speedups, up to the point where you run out of registers or ports — after that, you're not fixing a stall anymore, you're causing a different one.

---

*The knowledge skeleton for this post — the store buffer, the invalidate queue, release/acquire, false sharing, and the pipeline/dependency material — comes from a close reading of [`zzxscodes/trading-system-notes`](https://github.com/zzxscodes/trading-system-notes); the causal chains connecting them, the correctness-vs-performance framing, the reordering table, the STLF failure case, and the accumulator-count derivation are built on top of it.*
