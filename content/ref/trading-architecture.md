---
title: "Trading System Architecture: Map, Times, How to Split"
description: "Which threads and data structures a market data message passes through on its way from the NIC to an order and back as a fill; roughly how long each stage takes; and how industrial systems split threads, where they put queues, and where they must join."
date: 2026-10-20
lastmod: 2026-11-07
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
| Several threads' orders converging on one gateway (multi-producer queues), blocking queues on side paths, whether a full queue blocks or drops | [#18 Thread-Safe Queues](/posts/thread-safe-queue/) |
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

### 3.7 Backtest and Live: One Codebase, Reconciled Value by Value Every Day {#replay}

1. **Backtest and live must compute the same factor value**
   - **A backtest result only counts if it holds live**: when a researcher shows in a backtest that a factor works, that assumes the live system computes the same values. If the two differ and live performance is worse, you cannot tell whether the strategy stopped working or the factor was computed wrong.
   - **Example**: for one stock at 10:00:00 the factor is 0.82 in the backtest and 0.79 live. The entry threshold is 0.8, so the backtest opens a position at that moment and live does not; from that trade on, the two P&Ls no longer match.
   - **The difference comes from five places**: different code, different input data, a different time convention, a different floating-point evaluation order, and different state. The steps below rule them out one at a time.

2. **One codebase: the factor has a single `on_tick` entry point**
   ```cpp
   struct Factor {
       void on_tick(const Tick& t);   // one message in, update internal state
       double value() const;          // read the current factor value
   };
   ```
   - **The factor does not know whether it is in a backtest or live**: it only takes one message and updates its state once. Where the messages come from is decided by the layer that calls it.
   - **Live calls it like this**: the feed thread decodes the multicast packets into `Tick`s, and the shard thread calls `on_tick` on each ([1.1](#tick)).
   - **The backtest calls it like this**: a replayer reads historical data one trading day at a time, builds `Tick`s in time order and calls the same `on_tick`.
   - **Two implementations, one for research and one for live, drift apart sooner or later**: with one in Python and another in C++, details end up different, for example one skips NaN and the other does not, or one uses the close price and the other the last price.
   - **With one codebase, "the two implementations differ" is no longer a possible cause**.

3. **Daily reconciliation: replay what live recorded, after the close**
   - **During the session, store both the inputs and the outputs**: the recorder reads every message live received from the broadcast ring and stores it as is ([1.4](#side)), together with the receive time; the shard threads log every factor value they compute.
   - **The recording is what live actually saw**: a dropped message is not in it, a late message is stored in its late position, and a recovered message is stored at the moment it was recovered. So the replay input is exactly the live input.
   - **After the close, replay the recording**: the replayer reads the recording, feeds it to the same `on_tick`, and gets a second series of factor values.
   - **Compare value by value, keyed by message sequence number**: line the two series up by message and compare each pair.
      - **Same binary, same input: the results should be bit-identical**: the threshold can be 0, and a single differing bit means something in the system is nondeterministic.
      - **Only a comparison with a research prototype in another language needs a tolerance**: a relative error of 1e-9, say, because the two sides evaluate floating point in different orders anyway.
   - **Example**: 5000 stocks, a snapshot about every 3 s, 4 trading hours: about 14400 ÷ 3 × 5000 ≈ 24 million values, a few seconds to a few tens of seconds to compare.
   - **Then compare the recording with the vendor's historical file**: researchers usually backtest on the vendor's files, not on live recordings. This step finds where the two inputs themselves differ, and it is the step that turns up differences most often.
   - **It is also the regression test after a code change**: on the same day's recording, the output must not change by a single bit; where a change is intended, it should appear only in the factors that were meant to change.

4. **When they do not match, check these four places first**
   - **Different data: drops, reordering, vendor conventions**:
      - **Drops**: multicast runs over UDP; one lost packet and live is missing a message. Until it is recovered, live has already computed on data with a gap; the vendor's historical file is the complete version, filled in afterwards. For example, if the 10:00:03 snapshot is lost, the next snapshot's volume increment covers 6 s, and the factor jumps at that point.
      - **Reordering**: packets from different channels arrive in no fixed order; live processes them in arrival order, while the historical file is sorted by the exchange's sequence numbers. A factor on one stock is unaffected; a market-wide factor that merges several channels is.
      - **Vendor conventions**: historical files may have bad data corrected afterwards, and field units or rounding may differ from the exchange's raw feed, for example a turnover field with the fractions of a yuan dropped.
   - **Different time convention: receive time or exchange time, and how bars are cut**:
      - **A message carries two times**: the exchange's timestamp and the time this machine received it. Live has both; historical files usually have only the exchange time.
      - **Cutting bars by receive time pushes messages near a boundary into the next bar**: a message stamped 09:59:59.990 by the exchange may arrive at 10:00:00.002. By receive time it goes into the 10:00 bar; by exchange time it belongs to 09:59. The two bars then differ by one message, and so do their average price and volume.
      - **The fix is to cut bars by exchange time on both sides**.
   - **Different floating-point evaluation order: compiler flags, target machine, join order**:
      - **Floating-point addition is not associative**: in double, `(1e16 + 1) - 1e16` is 0 and `(1e16 - 1e16) + 1` is 1; reorder the operations and the last digits, or even the whole result, can change.
      - **`-ffast-math` lets the compiler reorder operations**: with it, the compiler rewrites sums into vectorised partial sums and assumes NaN never occurs, so the result can depend on whether the flag is on.
      - **A different target machine can change the result too**: with `-ffast-math`, the vector width decides how the partial sums are grouped (AVX2 holds 4 doubles, AVX-512 holds 8); when the target supports FMA, GCC by default fuses `a * b + c` into one FMA instruction, which rounds once instead of twice.
      - **Add in a fixed order at the join**: cross-sectional scoring sums the shards' results ([3.4](#barrier)). Adding in "whoever finishes first" order gives a different order every day; adding in stock-code order gives the same result every time.
      - **Rolling windows amplify the difference**: each step differs a little, and the longer the window, the more it accumulates.
      - **The fix is the same compiler flags for backtest and live, ideally the very same executable**.
   - **Different state: overnight warm-up, intraday restarts**:
      - **Factors carry state**: a 20-minute rolling mean needs the previous 20 minutes of data; an EMA depends on all the data before it.
      - **A different warm-up makes the opening stretch disagree**: for example, live warms up each morning on the previous day's last 400 snapshots while the backtest starts from the day's first message; the factor values after the open differ until the window has rolled past.
      - **An intraday restart breaks the state**: live crashes at 10:30 and restarts, with its state either reset or restored from a checkpoint, while the backtest runs straight through.
      - **The fix is to make the warm-up length and the restart recovery fixed rules**: the backtest follows the same rules, and a restart must be reproducible in the backtest.

5. **Conclusion**
   - **Value-by-value reconciliation turns "it does not match" into a few causes you can rule out one by one**: one codebase rules out code differences, the same input rules out data differences, exchange time on both sides rules out time differences, the same binary and a fixed join order rule out evaluation-order differences, and fixed warm-up and restart rules rule out state differences.
   - **A difference that survives all of these is a problem with the strategy itself**.
