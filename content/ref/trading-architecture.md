---
title: "Trading System Architecture: Map, Times, How to Split"
description: "Which threads and data structures a market data message passes through on its way from the NIC to an order and back as a fill; roughly how long each stage takes; and how industrial systems split threads, where they put queues, and where they must join."
date: 2026-10-20
lastmod: 2026-10-20
slug: "trading-architecture"
weight: 15
toc: true
---

This page is an architecture map to keep open, and a companion to the [hardware map](/ref/cpu-memory/): that page follows one memory access through the hardware, this one follows one market data message through the threads. It has three parts, in the order "where → how fast → how to split":

1. [Architecture map](#map): the boxes a message passes through on its way to a fill, and which post covers each box.
2. [Times](#numbers): roughly how long each stage takes, to tell which stage is worth optimising. They are orders of magnitude, not measurements of any one system.
3. [How to split](#rules): how industrial systems split threads, where they put queues, and where they have to join.

When a later post covers a new component, it goes here.

## 1. Architecture Map: The Boxes a Message Passes Through {#map}

<a href="/maps/arch-map.en.html" target="_blank" rel="noopener"><img src="/images/ref/arch-map.en.svg" alt="Trading system architecture map: market data from the exchange goes through the NIC to the feed handler thread, which writes it once into a broadcast ring for the recorder and the monitor and dispatches it by stock to shard threads that update books and factors; after the join, the decision thread runs the strategy, pre-trade risk, the order manager and the order gateway, and the order goes through the broker's system to the exchange. Reports follow the red line back to the order manager and the account state and on to the strategy. The bottom row holds the side paths: replay and research, recorder, monitoring, logging, trader commands and client push." loading="lazy" decoding="async"></a>

Green boxes are hot threads, each pinned to an isolated core; blue boxes hand data between threads; yellow is a join point; the dashed boxes along the bottom are side paths. Black lines carry market data to an order, red lines carry reports back, and grey dashed lines are side paths. Click the map to open the interactive version: click a box to see what it does and why it is built that way, or pick a path and step through it.

### 1.1 The Path of a Tick: Market Data → Order {#tick}

1. The exchange multicasts market data by channel, and the NIC receives the packet.
2. The feed handler thread decodes it and checks the channel's sequence number; a gap has to be recovered.
3. It first writes the message into the broadcast ring for readers that are not in a hurry, such as the recorder and the monitor, and moves on ([#5](/posts/spmc-shared-memory-broadcast-ring/)).
4. Then it looks up the stock's shard and writes into that shard's queue ([#4](/posts/lock-free-queue-logger-micro-batching/)). A stock always goes to the same shard, so its messages stay in order.
5. The shard thread updates the stock's order book, then its factors, incrementally, touching only its own stocks' state.
6. A cross-sectional strategy waits until every shard has finished the bar, then ranks and scores everything together.
7. In the decision thread, the strategy decides what to buy, sell or cancel, pre-trade risk checks it, and the order manager takes over; big orders are sliced and sent over time.
8. The order gateway encodes the order and sends it through the broker's system to the exchange.

### 1.2 The Path of a Report: Fill → Position → Strategy {#fill}

1. After matching, the exchange sends execution reports: acknowledgements, fills and cancels. They come back through the broker's system to the order gateway.
2. The order manager updates the order's state: partly filled, filled, cancelled.
3. The account state follows: positions, cash, open orders. Only the decision thread writes it.
4. The next decision uses the new positions and cash, which closes the loop; the client push sends the changes to the traders' screens.

### 1.3 Two Cadences: Per Bar or Per Tick {#clocks}

Per bar (cross-sectional, multi-factor): every stock finishes the bar, then everything is scored together, at a cadence of milliseconds to seconds. A handoff of tens of nanoseconds is invisible here; what matters is how long a wave of data takes to be fully processed.

Per tick (market making, arbitrage): one message can trigger one order. The shard thread computes the signal, runs the risk checks and sends the order itself, with no join and no queue, in microseconds end to end; every extra cross-core handoff adds tens of nanoseconds and some jitter.

### 1.4 Side Paths: Slow Is Fine, Blocking Is Not {#side}

Recording, logging, monitoring and client push are side paths: a hot thread writes one entry into a ring or a queue and moves on, and other threads or processes do the slow work. Side readers may read in batches, but their capacity has to be sized so they never get lapped. Trader commands (start/stop, cancel, change parameters) go the other way, through a service and a queue into the decision thread.

### 1.5 Index: Which Post Covers Each Box {#posts}

| Box | Post |
|---|---|
| Pinning hot threads, keeping NIC interrupts off hot cores | [#1 CPU Isolation and NUMA](/posts/cpu-affinity-core-isolation-numa/) |
| Why a cross-core handoff costs tens of nanoseconds, false sharing | [#2 Memory Ordering and Cache Lines](/posts/memory-ordering-false-sharing-dependency-chains/) · [MESI](/posts/low-latency-mesi-cache-coherence/) · [Ref 2.6](/ref/cpu-memory/#cross-core) |
| No allocation on the hot path (orders, message objects) | [#3 Memory Pools and Allocators](/posts/hot-path-memory-allocators/) |
| Shard queues (SPSC), async logging | [#4 Lock-Free Queues and Micro-Batching](/posts/lock-free-queue-logger-micro-batching/) |
| Broadcast ring, lapped recorders, resuming after a restart, when not to use a broadcast ring | [#5 An SPMC Broadcast Ring in Shared Memory](/posts/spmc-shared-memory-broadcast-ring/) |
| The computation for one message in a shard thread | [A Cache Case Study: Repricing 64 Options per Tick](/posts/low-latency-cache-case-study/) |
| Warming up before the open, double-buffered account snapshots | [#14 Prefetching, Cache Warming, and Double Buffering](/posts/prefetch-warmup-double-buffer/) |
| Join, strategy, risk, order manager, order gateway | Part 3 of this page; later posts will add more |

## 2. Times: Roughly How Long Each Stage Takes {#numbers}

These are orders of magnitude to aid understanding, not measurements of any one system. Rows marked "measured here" come from the linked posts; the rest are typical figures.

| Stage | Roughly | Notes |
|---|---|---|
| Exchange → this machine's NIC | Co-located: a few µs; through a market data vendor: a few ms | Depends on distance and how many hops |
| NIC → the program has the packet | Kernel bypass: about 1 µs; kernel network stack: about 5–10 µs | The kernel path pays for an interrupt, a copy and a system call |
| Decode one message | About 0.1–1 µs | Depends on the format |
| One cross-core handoff (queue, ring) | About 20–100 ns | One cache line moving between cores ([Ref 2.1](/ref/cpu-memory/#latency)) |
| One write into the broadcast ring | About 3–40 ns | Measured here: flat out, more readers sitting on the newest slot cost more ([#5 1.6](/posts/spmc-shared-memory-broadcast-ring/#16-on-real-hardware-do-readers-slow-the-producer)) |
| Book and factor update for one message | Hundreds of ns to a few µs | Depends on the factors; one cache level further away costs several times more |
| Join | Waits for the slowest shard | A cross-sectional strategy runs per bar: milliseconds to seconds |
| Strategy and risk | Per-tick decision: microseconds; ranking a few thousand stocks: about 100 µs | All in memory |
| Order to the exchange and report back | Co-located: tens to hundreds of µs round trip; through a standard broker tier: up to ms | Network and matching; little to tune on your side |
| Push to traders' screens | Tens of ms | For people; enough is enough |
| Disk write | Milliseconds | Which is why it lives on a side path |

The table says two things. First, a handoff of tens of nanoseconds disappears in a chain measured in milliseconds; it is only worth chasing in systems whose whole chain takes a few microseconds. Second, when market data surges, what slows things down is queueing, not handoffs ([3.5](#burst)).

## 3. How to Split: Rules from Industrial Systems {#rules}

### 3.1 Run the Critical Path to Completion on One Thread; Queues Only for Side Paths {#run-to-completion}

The fastest systems receive, decode, update the book, decide and send on a single thread, one function call after another, with the data staying in that core's cache. Every queue between threads is a cross-core transfer of tens of nanoseconds plus some jitter, so queues are used only to push slow work (recording, logging, monitoring) off the hot thread. One step faster, decoding and even order sending move into an FPGA on the network card, and software only sets parameters.

### 3.2 Use More Cores by Sharding by Stock, and Run Each Shard to Completion {#shard}

When one thread cannot keep up with the whole market, split the stocks across threads. A stock's messages must be processed in order, so each stock always belongs to one thread, and the threads run in parallel. Balance by message volume, not by number of stocks: the busy names send far more messages, so the usual approach is a stock → thread table built from the last few days' volumes and fixed before the open. Exchanges already publish market data by channel; if you can receive channels directly, there is no need to split again yourself. Only when the source is a single full stream (a vendor feed, say) does the feed thread dispatch by the table.

### 3.3 One Stream, Several Readers: Broadcast Ring or Separate SPSC Queues {#fanout}

When readers all need the full stream, come and go, or live in other processes (recording, republishing, monitoring), use a broadcast ring: one write, and the producer never looks at the readers. When readers each need a subset, or a drop must be known the moment it happens, use per-reader SPSC queues. The two often combine: the feed thread writes each message into the broadcast ring and also into the queue of the shard that owns the stock ([#5 1.7](/posts/spmc-shared-memory-broadcast-ring/#17-when-not-to-use-a-broadcast-ring)).

### 3.4 Join Only Where You Must, and Give State a Single Writer {#barrier}

Cross-sectional scoring needs every stock, so it has a join point; a stock's own factors never wait for anyone. Positions, cash and open orders have a single writer, the decision thread; the push service and the monitor read the snapshots it publishes and never touch the copy being changed. How to publish a snapshot without readers seeing half old, half new data: [#14](/posts/prefetch-warmup-double-buffer/), double buffering.

### 3.5 Surges: Queueing, Not Handoffs {#burst}

At the open, at the close and on news, messages arrive several times faster than usual. As soon as each message takes longer to process than the gap before the next one, a backlog builds: later messages wait for earlier ones, and the factors run on stale data. A queue handoff of tens of nanoseconds is negligible next to that; what to save is the queueing, by spreading stocks across more threads or doing less work per message.

The backlog sits in the rings and queues: backlog = (arrival rate − service rate) × duration, and it must stay below capacity; a broadcast ring that overflows laps its readers ([#5 2.3.2](/posts/spmc-shared-memory-broadcast-ring/#232-a-slow-reader-gets-lapped-headroom--capacity--rate-gap)). To find out whether you have enough, replay the first minutes of a real trading day at the original pace, measure the time from arrival to the end of processing for every message, and watch how the backlog rises and falls.

### 3.6 Side Paths Must Never Block the Hot Path {#side-rule}

A hot thread logs or hands data to the recorder by writing one entry into a queue or ring and moving on ([#4](/posts/lock-free-queue-logger-micro-batching/)); formatting, disk writes and pushes happen on other threads. Readers that are not in a hurry should not spin on the newest slot: reading in batches every so often keeps them from taking the producer's line on every message ([#5 1.6.5](/posts/spmc-shared-memory-broadcast-ring/#165-how-should-a-reader-wait)).

### 3.7 Replay Through the Same Code {#replay}

Feed the recorded data, in its original order, back through the same factor code; only when offline results match live results value for value can the replay be trusted. It is also the regression test after a code change: on the same day of data, not a single output value may change.
