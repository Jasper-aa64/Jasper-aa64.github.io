---
title: "Low-Latency Trading — MESI Cache Coherence"
date: 2026-10-04
slug: "low-latency-mesi-cache-coherence"
description: "How cores keep their private copies of one cache line consistent: the single-writer / many-readers rule, the four MESI states as two yes/no questions, one line followed through six steps, what each kind of write really costs, and the two things coherence never promised — atomicity across a multi-word read, and ordering across different addresses."
summary: "MESI enforces one rule: a cache line has either one core that may write it or any number of cores that may only read it, never both. The four states are the answers to two questions — does anyone else hold this line, and have I changed it? — and every cost in the protocol comes from moving data between layers or waiting for another core to confirm. False sharing, a cached queue cursor and a producer that slows down as readers join are all the same state machine. Coherence still doesn't make a multi-word read atomic, and it says nothing about the order of writes to different addresses; that is what fences are for."
categories: [Systems]
tags: [cpp, mesi, cache-coherence, false-sharing, atomics, memory-model, hft, low-latency]
toc: true
homepage: false
---

Start with something counterintuitive. Two threads each increment their own counter. They share no variable at all; the two counters just happen to sit next to each other in one struct, on the same 64-byte cache line. That alone makes them over ten times slower than counters kept apart (measured in [#2](/posts/memory-ordering-false-sharing-dependency-chains/)). The threads share nothing, yet the hardware makes them drag each other down.

Explaining it means knowing how a multi-core CPU manages several copies of one cache line. Each core has its own L1 and L2 holding copies of memory; when two cores have both read a line, each holds a copy. As soon as one of them writes, the other copy is stale — and the hardware must guarantee no core keeps using a stale copy. That machinery is the cache coherence protocol, and the classic one is MESI.

Once it makes sense, several seemingly unrelated effects line up: false sharing, why an SPSC queue caches the other side's cursor ([#4](/posts/lock-free-queue-logger-micro-batching/)), and an SPMC queue whose producer slows down as readers join ([#5](/posts/spmc-shared-memory-broadcast-ring/)). This post starts from one rule, derives the four states, follows one line through its life, and ends with what MESI does **not** guarantee — the part interviewers like to push on.

## 1. One Writer or Many Readers

The hardware does not keep copies consistent by having the writer update everyone else's copy. It uses a cheaper rule: **before you write a line, every other core must throw its copy away; then you write alone.**

Stated as an invariant — textbooks call it SWMR, single-writer / multiple-reader — at any moment a cache line has either **exactly one** core allowed to write it, or **any number** of cores allowed only to read it. Never both.

MESI is the bookkeeping that enforces it. Each core's cache controller tags every line it holds with a state, and watches requests from other cores (snooping) to decide how to respond and whether to change its own tag. There are four tags: M, E, S and I.

Real chips don't broadcast every request to every core; a snoop filter or directory records which cores hold which lines and only asks those. That changes how messages travel, not what the four states mean.

---

## 2. Four States, Two Questions

To label a line in my cache I need two answers: **does anyone else hold it?** and **is my copy the same as memory, or have I changed it?** Add "I have no valid copy" and you have all four:

- **M (Modified)**: only I have it, and I've changed it; memory is stale. I can read and write freely without telling anyone. If someone wants to read it, I must supply the data. If it's evicted, I write it back first.
- **E (Exclusive)**: only I have it, and it matches memory. I can read it; I can also write it **without telling anyone**, and it becomes M.
- **S (Shared)**: several cores may hold clean copies. Read-only; to write, the other holders must be invalidated first.
- **I (Invalid)**: I have no valid copy — never had one, or someone invalidated it. Reading or writing means asking first.

Laid out as a table, the structure is obvious, including the empty cell:

| | Clean (matches memory) | Dirty (I changed it) |
|---|---|---|
| **Only I have it** | E | M |
| **Others may have it** | S | — (doesn't exist in MESI) |

The bottom-right cell is empty because MESI requires exclusivity before any write: dirty always means "only me". When another core reads a dirty line, the owner hands it over and both become clean S.

The variants real chips use are edits to this table. **AMD's MOESI adds O (Owned)** — exactly the empty cell: I've changed it, others may hold read-only copies, memory stays stale, and I answer read requests, saving a write-back. **Intel's MESIF adds F (Forward)**: among many clean S copies, one is designated to answer reads so they don't all respond. Neither is new machinery; one fills a cell, the other names a responder.

**Why have E at all?** It's the private-data fast path. When I read a line and nobody else holds it, I get E; later, when I write it, I don't even need to check that nobody holds it — no message at all. Without E, the first write to purely private data would still go through the "invalidate everyone" round trip with nobody to invalidate. E has exactly one origin: **a read miss when no one else holds the line.**

---

## 3. One Line's Life, Step by Step

Two cores, A and B, one line X that neither holds:

| # | Event | A | B | What happens |
|---|---|---|---|---|
| 0 | start | I | I | nobody has it |
| 1 | A reads X | **E** | I | nobody else has it; A fetches it from memory and holds it alone, clean → E |
| 2 | A writes X | **M** | I | E→M with **no message**; A's copy is now newer than memory |
| 3 | B reads X | **S** | **S** | B asks; A snoops, sees its copy is M — memory is stale, so **A must supply the data**; both drop to S |
| 4 | B writes X | **I** | **M** | B holds S and can't just write: it sends an invalidate (it already has the data); A → I; B → M |
| 5 | A reads X | **S** | **S** | A misses; B holds M, so **B supplies the data** and drops to S |
| 6 | A writes X | **M** | **I** | mirror of step 4: A invalidates B |

Step 3 is a read that hits a line another core holds in M. That's a **HITM**, the event `perf c2c` counts. Step 4's S→M is an **upgrade**: the data is already local; what's being bought is ownership.

Steps 1 and 2 are a core's private business. Every step from 3 on involves another core, and every cost below is a variant of that.

---

## 4. The Rules: Read, Write, Snoop

Every transition above is one of three events.

**Read**

- Hit (M, E or S): read the local copy, no message.
- Miss (I): ask. If another core holds M, it supplies the data and drops to S; if others hold E or S, everyone ends in S; if nobody holds it, fetch from memory and take E.

**Write** — exclusivity first, four starting points, four prices:

- **M**: write directly, no message.
- **E**: write directly, become M, no message.
- **S**: send invalidations to the other holders and wait for acknowledgements, then become M. No data moves, but it's a **cross-core round trip**.
- **I** (write miss): send an **RFO** — read for ownership, "give me this line, exclusively". The line is fetched *and* every other copy is invalidated; then M.

A write miss goes **straight from I to M**. There is no "first E, then M" step to pay for; some diagrams draw I→E→M, splitting "gain exclusivity" from "modify", but E as a resting state only follows a read miss. So a queue producer writing its ring is never doing "silent E→M writes": lines it wrote stay M if nobody touched them; if a reader read them, the next lap is S→M; if they were evicted, it's I→M.

**Snooped** (how I respond to another core's request)

- Someone reads: if I'm M, I supply the data and drop to S; E drops to S; S stays S.
- Someone writes (RFO or invalidate): M, E or S all go to I — M hands over its data first.

Drawn as one picture — the top half is this core's own reads and writes, the bottom half is what it snoops from other cores:

<a href="/images/mesi/mesi-states.en.svg" target="_blank" rel="noopener"><img src="/images/mesi/mesi-states.en.svg" alt="MESI state diagram: local reads and writes move a line to E, S or M; a remote read drops M and E to S; a remote write turns M, E and S into I" loading="lazy" decoding="async"></a>

That's the whole rule set. For any new scenario, ask: who reads, who writes, and what state does everyone else hold?

---

## 5. Where a Write's Cost Comes From

**The cost of a write = the cost of getting the data + whether another core has to confirm.**

- **M or E**: local, a few cycles, no other core involved.
- **S→M**: the data is local, nothing moves; but the other holders must acknowledge the invalidation — one cross-core round trip.
- **I→M**: the data must be fetched, and the price depends on where it comes from — a few ns from L2, a dozen or so from L3, tens from another core's cache, around a hundred from DRAM (typical magnitudes) — plus invalidations if others hold it.

So **S→M versus I→M has no fixed order.** It depends on which layer the data comes from and whether a confirmation is needed. A single isolated access to data in DRAM makes I→M the expensive one. Streaming writes can flip it: prefetching and many outstanding misses overlap the DRAM latency, while a confirmation per message doesn't overlap well. In the SPMC measurements of [#5](/posts/spmc-shared-memory-broadcast-ring/) a 64 MiB ring with no readers — mostly I→M from memory — cost 12.6 ns per message, while a 512 KiB ring with one polling reader — mostly S→M — cost 18.5 ns (measured on different configurations; the attribution to S→M versus I→M is an interpretation, not a counter readout).

The most expensive *read* is a HITM: the line you want is M in another core, which must hand it over — a full cross-core transfer.

**Cost Is Not the Same as Stalling.** A plain store like `x = 1` goes into the store buffer ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)) and the core keeps executing while ownership is acquired in the background. The core only waits when the store buffer fills up, or for a `lock`-prefixed read-modify-write or a fence. That's why `fetch_add` on a line another core owns is so expensive: it must hold exclusive ownership until the instruction finishes, and it can't be parked in the store buffer.

---

## 6. Three Old Results, One Machine

**False sharing.** Two cores each write their own variable, but the variables share a line. Drop the reads from steps 4–6: A writes (A is M, B is I); B writes — B is I, sends an RFO, A hands over the data and goes to I, B becomes M; A writes again, and so on. **Every increment is an I→M, a full-line transfer and an M→I on the other side.** M→I is the core of the ping-pong: each core is kicked out right after its write. `perf c2c` counts the HITMs in this loop; `alignas(64)` fixes it by giving each variable its own line.

**The cached cursor of an SPSC queue ([#4](/posts/lock-free-queue-logger-micro-batching/)).** The consumer writes its head index on every message, so that line is M in the consumer's core. If the producer read it on every enqueue, it would pull the line to S, and the consumer's next write would have to upgrade it again — two extra cross-core round trips per message. A cached copy of the cursor makes the producer read the real one only when the queue looks full.

**A producer that slows down as readers join ([#5](/posts/spmc-shared-memory-broadcast-ring/)).** Measured on a Ryzen 5 5600GT under Windows, 512 KiB ring: 2.8 ns per message with no readers, 18.5 ns with one busy-polling reader, 28.0 ns with five. With no readers the ring fits in L2 and every line stays M in the producer's core. A polling reader pulls lines to S; the producer's next lap must upgrade each one, and the reader then pulls it away again. Five readers mean five copies to invalidate. (This reading is inferred, not verified with hardware counters, and it applies to a small ring with readers right behind the producer.)

**Why HFT cares.** Every cache line shared across cores is a line item on the latency bill. Keep **one writer per line** on the hot path — the SPMC ring is built that way — and remember that even read-only sharers make the writer pay. Counters that several threads must update should be sharded per thread and summed later, not bounced between cores.

---

## 7. Coherent, Not Atomic; Coherent, Not Ordered

These are the follow-ups interviewers love: *if MESI keeps caches consistent, why do we still need…?*

**Coherent, not atomic.** MESI guarantees that all cores agree on one order of writes *to a single line*, and that no core keeps using a stale copy forever. It does not make a multi-step read or write a unit. A writer updating a record with several stores, and a reader loading it with several loads, can interleave: every load returns a value the line really held at some moment, and the combination is still half old, half new. That is the torn read measured in [#5](/posts/spmc-shared-memory-broadcast-ring/) — about 5.5% of accepted reads under a deliberately hostile stress test. Holding an S copy doesn't prevent it: the copy can be invalidated and replaced between the reader's first and second field. And a 128-byte record spans two lines, each coherent on its own, with nothing tying them to the same instant.

**Coherent, not ordered.** MESI talks about writes to *one* address. Whether another core can see the new value of `y` before the new value of `x`, after you wrote `x` then `y`, is outside its scope. That is decided inside the core — the store buffer that publishes writes late, the invalidate queue that applies invalidations late — and by the compiler ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)). Hence the classic answer: **MESI keeps caches consistent with each other; fences order the reads and writes queued inside a core.**

The "three pieces of lock-free programming" now each have a job: the `lock` prefix makes one read-modify-write indivisible by holding the line exclusively until it completes; MESI keeps the copies of each line consistent; memory fences order accesses to different addresses. Drop any one and something breaks.

