---
title: "Trading System Notes #5: An SPMC Broadcast Ring in Shared Memory"
date: 2026-10-04
slug: "spmc-shared-memory-broadcast-ring"
description: "A single-producer multi-consumer ring where every reader sees every message and the producer never waits: a sequence stamp in every slot, private reader cursors, one wrap-safe subtraction with three meanings — and the bill the readers pay instead: silent overruns, torn reads, a producer that still slows down as readers join, and the shared-memory traps of addresses, first-lap page faults and restarts."
summary: "Market data has one producer and several consumers, each of which must see every message, and the producer is the hot path that may not wait for anyone. The answer is a broadcast ring: every slot carries its own sequence stamp, readers keep private cursors, and the producer overwrites the oldest slot without ever reading reader state. The price moves to the readers — overruns are silent, a re-check after reading can't catch a half-written slot unless the writer invalidates the stamp first, and polling readers still make every write more expensive. Moving the ring into shared memory adds three more rules: nothing inside it may be a pointer, the first lap pays a page fault every 32 messages, and a restarted reader loses everything unless it saved its cursor."
chapter: 1
categories: [Systems]
tags: [cpp, lock-free, spmc, shared-memory, ring-buffer, atomics, market-data, hft, low-latency]
toc: true
homepage: false
---

An exchange's Level-2 feed arrives on one callback thread: trades and order updates, tens of thousands a second when the market is busy. There is more than one consumer downstream — one writes every message to disk, one republishes over MQTT, one runs live analytics — and **each of them must receive every message**.

How do you hand one message to three readers? The first idea is the SPSC queue from [#4](/posts/lock-free-queue-logger-micro-batching/): three of them, with the producer writing every message three times. An SPSC producer reads the consumer's position to know whether the queue is full, and that read pays for itself: the producer never overwrites data a reader hasn't read, and if it does drop something, it knows on the spot whose message it dropped. The cost is that once any reader falls behind and its queue fills, the producer has to choose right there: drop, or wait. Here the producer is the market-data hot path. **It can never wait for any reader.**

This post walks through a roughly fifty-line answer: an SPMC broadcast ring. Its trade is that the producer doesn't look at the readers at all and simply overwrites the oldest slot once the ring is full. The idea fits in one sentence — move the "this message is published" signal out of a shared index and into each slot — but its consequences take a while to work through. Part 1 is the ring itself, what it does not guarantee, and when not to use it; Part 2 is what changes when it moves into memory shared between processes.

## 1. The Broadcast Ring: One Producer, Many Readers

### 1.1 The Structure: A Ring of Stamped Slots

The design is a compact open-source ring (MengRao's SPMC_Queue); the whole thing is about fifty lines:

```cpp
#include <atomic>
#include <cstdint>

template<class T, uint32_t CNT>
class SPMCQueue {
public:
    static_assert(CNT && !(CNT & (CNT - 1)), "CNT must be a power of 2");

    struct Reader {
        operator bool() const { return q; }
        T* read() {
            auto& blk = q->blks[next_idx % CNT];
            uint32_t new_idx = ((std::atomic<uint32_t>*)&blk.idx)->load(std::memory_order_acquire);
            if (int(new_idx - next_idx) < 0) return nullptr;   // nothing new yet
            next_idx = new_idx + 1;
            return &blk.data;
        }
        T* readLast() {                                         // drain, keep only the newest
            T* ret = nullptr;
            while (T* cur = read()) ret = cur;
            return ret;
        }
        SPMCQueue<T, CNT>* q = nullptr;
        uint32_t next_idx;                                      // private to this reader
    };

    Reader getReader() {                                        // starts at the *next* message
        Reader reader;
        reader.q = this;
        reader.next_idx = write_idx + 1;
        return reader;
    }

    template<typename Writer>
    void write(Writer writer) {
        auto& blk = blks[++write_idx % CNT];
        writer(blk.data);                                       // fill the slot in place
        ((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release);  // then stamp it
    }

private:
    struct alignas(64) Block {
        uint32_t idx = 0;                                       // which message this slot holds
        T data;
    } blks[CNT];
    alignas(128) uint32_t write_idx = 0;
};
```

Three things to notice before reading any function:

- **The stamp `idx` lives in every slot.** Each block records *which message number it currently holds*. The publication signal is no longer one shared index that everyone reads; it travels with the data.
- **`write_idx` is a plain `uint32_t`, not an atomic.** Only the producer writes it; `getReader()` reads it once when a reader is created.
- **`CNT` is a power of two**, so `% CNT` compiles to a mask (the trick from [#4](/posts/lock-free-queue-logger-micro-batching/)). The stamps are 32-bit and wrap after about 4.29 billion messages; the comparison in `read()` is written for that.

With the Level-2 trade record from the deployment this ring was built for — 88 bytes — a `Block` is 4 bytes of stamp, 4 of padding and 88 of data = 96, rounded up by `alignas(64)` to **128 bytes, exactly two cache lines**. With `CNT = 524288`, one queue is 64 MiB.

Keeping the stamp next to the data also saves a round trip: a block's first cache line holds the stamp plus the first 56 bytes of data. When a reader pulls that line over to check the stamp, those 56 bytes come with it and any field inside them is ready to use. With the stamp kept somewhere else, the reader would fetch the stamp's line, check it, and only then fetch the data's line — one more round trip to wait for.

The `alignas(64)` keeps neighbouring slots on different lines, so the producer writing slot *i* doesn't drag a line a reader is using for slot *i − 1* (false sharing, [#2](/posts/memory-ordering-false-sharing-dependency-chains/)). Aligning `write_idx` to 128 rather than 64 is commonly explained by CPUs that prefetch cache lines in adjacent pairs; the design doesn't say, so treat that as the likely reason rather than a stated one.

---

### 1.2 The Producer: Write, Then Stamp

```cpp
auto& blk = blks[++write_idx % CNT];
writer(blk.data);                                                                  // ① the caller's lambda fills the slot
((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release); // ② then the slot gets its new number
```

It's the two-step hand-off from [#4](/posts/lock-free-queue-logger-micro-batching/) — write in place, then publish — except that publishing now means stamping this slot instead of advancing a shared index.

And the producer **never reads anything a reader writes**. There is no "full": after one lap it simply overwrites the oldest slot. So it never waits, and the number of steps it takes doesn't depend on how many readers exist or how slow they are.

---

### 1.3 The Reader: One Subtraction, Three Meanings

A `Reader` holds only a pointer to the queue and its own `next_idx` — "the message number I want next". It lives in the reader's own memory, and the reader never writes to the queue. Readers don't contend with each other, and adding or removing one doesn't change a single step of the producer's code path.

`read()` looks at the slot where message `next_idx` would be, and compares that slot's stamp `new_idx` with what it wants. A picture makes it obvious: at the same moment, three readers that are behind by different amounts see exactly the three cases.

<a href="/images/spmc-ring/ring.en.svg" target="_blank" rel="noopener"><img src="/images/spmc-ring/ring.en.svg" alt="A ring with CNT = 8 and the producer at message 11; reader A finds nothing new yet, reader B gets exactly its message, reader C is lapped and skips messages 2 to 9" loading="lazy" decoding="async"></a>

The same three cases as a rule:

| `int(new_idx - next_idx)` | Meaning | What `read()` does |
|---|---|---|
| **< 0** | The slot still holds last lap's message; the producer hasn't reached mine | returns `nullptr` |
| **== 0** | Exactly the message I'm waiting for | returns it, `next_idx = new_idx + 1` |
| **> 0** | The producer lapped me; this slot already holds a *newer* message | returns the newer message, `next_idx = new_idx + 1` — **everything in between is skipped** |

Two details carry most of the weight.

**Why `int(new_idx - next_idx) < 0` and not `new_idx < next_idx`.** The stamps wrap at 2³². Subtracting as unsigned and reinterpreting the difference as signed gives the right order as long as the two are less than 2³¹ apart, across the wrap too. A direct comparison flips at the wrap: with `next_idx = 0xFFFFFFFE` and a new stamp of `1` after wrapping, the signed difference is +3 — new data, correct — while `1 < 0xFFFFFFFE` claims "not written yet".

**A positive difference is always a multiple of `CNT`.** A slot's stamp is a message number and its position is that number mod `CNT`, so the stamp in the slot a reader looks at can only be `next_idx`, `next_idx ± CNT`, `± 2·CNT`… Measured with `CNT = 8`: a reader holding `next_idx = 6` while the producer was at 30 got message 30 first — a difference of 24 = 3 × 8.

The two other entry points follow from the same rule: `getReader()` starts at `write_idx + 1`, so **it never replays history** (a reader created after five messages gets `nullptr`, then message 6); `readLast()` drains until `nullptr` and keeps only the newest — for a consumer that only wants the latest snapshot.

### 1.4 Memory Order: The Stamp Is the Publication

The memory orders are the release/acquire pair from [#2](/posts/memory-ordering-false-sharing-dependency-chains/), moved into the slot: the producer fills the data with ordinary stores and then release-stores the stamp; the reader acquire-loads the stamp and only then reads the data. Once the reader sees the new stamp, it is guaranteed to see the data written before it. Because the signal is per slot, any number of readers decide independently, with no writable state shared among them.

---

### 1.5 What the Design Does Not Guarantee

The trade is now visible: **the producer waits for nobody, so the readers absorb the consequences.** There are three: overruns are silent (1.5.1), a re-check can't catch a half-write (1.5.2), and readers still make the producer pay (1.5.3).

#### 1.5.1 Overruns Are Silent

The first consequence is overrun. With `CNT = 8`, a reader that hasn't read anything while the producer wrote 20 messages receives **17, 18, 19, 20**. Messages 1–16 were never delivered — and the queue doesn't say so. `read()` returns only a pointer and overwrites `next_idx`; the caller can't tell from the return value that anything was skipped.

The information is right there: the positive difference is exactly the number of skipped messages. Making it visible is one line — have `read()` report it, or accumulate `skipped += diff` in the `Reader`. Otherwise you need a sequence number inside the message itself.

In production `CNT = 524288`, so a reader has to fall half a million messages behind before it's lapped. But a reader that does slow work per message — formatting a string, a synchronous MQTT publish, an `fprintf` — moves toward that edge every time it's slower than the feed.

---

#### 1.5.2 A Re-Check That Can't See a Half-Write

`read()` returns `&blk.data`, a pointer into the shared slot, and the reader then reads the fields one by one. If the producer comes around and rewrites that slot meanwhile, the reader sees a mixture of old and new fields: a **torn read**.

The obvious fix is to re-read the stamp after copying the data and discard the copy if it changed. It doesn't work, and the reason is instructive. Stress test: `CNT = 4`, producer writing flat out, three seconds per case — deliberately the worst setting, to show the effect exists:

| Case | Accepted reads | Torn among them |
|---|---|---|
| As written: read through the pointer | 59,869,704 | 3,269,273 (≈ 5.5%) |
| Re-read `idx` after copying, discard if changed | 43,942,557 (8,861,343 discarded) | 2,084,572 (≈ 4.7%) |
| Producer **invalidates the stamp first**, then writes, then stamps; reader re-checks | 38,607,078 (6,436,383 discarded) | **0** |

The second row is the lesson. This producer writes the data first and changes the stamp *last*. Halfway through a rewrite the stamp is still the old one, so the reader's re-check sees "unchanged" and accepts a half-written record. The re-check only works if the producer destroys the old stamp before touching any data:

```cpp
// producer: three steps instead of two
((std::atomic<uint32_t>*)&blk.idx)->store(0, std::memory_order_relaxed);         // ① invalidate the stamp
std::atomic_thread_fence(std::memory_order_release);
writer(blk.data);                                                                 // ② write the data
((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release); // ③ stamp the new number
// reader: copy the data → atomic_thread_fence(acquire) → re-read idx;
//         anything other than the number seen before the copy means "discard this copy"
```

Now the reasoning closes: **if the stamp is still the old one, not a byte of the data has been touched.** Any overlap between the copy and a rewrite leaves the stamp either 0 (rewrite in progress) or the new number (rewrite done), and either way the copy is discarded. The two fences make "stamp changes before data changes" and "data is copied before the stamp is re-read" hold against both the compiler and the CPU. (Measured on x86; under the strict C++ memory model the data fields themselves would also need to be atomics.)

These are boundaries found under stress, not a claim that the original ring tears reads every day in production. A big ring and fast readers make it rare. Rare is not zero.

---

#### 1.5.3 Not Blocking Is Not Free

"Readers can't slow the producer down" sounds like it follows from "the producer never reads reader state". The first half is true — the producer never *waits*. The second half isn't: readers don't change the producer's *steps*, but they change what each step costs in hardware.

The experiment first. The producer writes flat out while readers busy-poll on separate physical cores (Ryzen 5 5600GT, Windows, median of three 1-second runs). There are two rings: 512 KiB, which fits in L2, and 64 MiB, the production size, larger than both L2 and L3. And two kinds of reader: one that only polls the stamp, and one that also reads the payload of each message it gets.

| ns per `write()` | 0 readers | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 512 KiB ring (fits in L2), readers only poll | 2.8 | 18.5 | 24.0 | 25.3 | 26.4 | 28.0 |
| 512 KiB ring, readers also read the payload | 2.8 | 22.8 | 25.8 | 28.5 | 32.5 | 37.0 |
| 64 MiB ring (the production size), readers only poll | 12.6 | 15.3 | 17.4 | 19.9 | 22.5 | 26.0 |
| 64 MiB ring, readers also read the payload | 12.6 | 20.1 | 26.8 | 29.8 | 33.8 | 38.7 |

**What a reader is waiting on.** `read()` looks once and returns `nullptr` if nothing is new; the readers in this experiment call it in a busy loop. Once a reader has caught up, the slot it keeps looking at — where message `next_idx` will land — is **exactly the slot the producer writes next**. The first look leaves a read-only copy of that slot's first cache line in the reader's core; after that, as long as nobody writes the line, every spin reads the local copy, generates no cross-core traffic and never touches the producer.

**The cost lands on the producer's write.** To write a line, the producer has to own it exclusively. If other cores hold copies, it must tell them to invalidate and wait for their acknowledgements before the write can go through — the S→M upgrade from [MESI cache coherence](/posts/low-latency-mesi-cache-coherence/) is exactly such a cross-core round trip. After the write, each reader finds its copy gone on its next spin and asks for the new line, which the producer's cache has to forward. Every reader watching that slot goes through this once per message.

With that mechanism in hand, read the table again.

**Zero readers: the two rings start from different floors.** In the 512 KiB ring, the line the producer comes back to has long left L1 but is still in its own L2, still Modified and still its alone — nobody to ask, 2.8 ns a message. In the 64 MiB ring, a lap later the line has been pushed out to memory and has to be fetched back before the write; the hardware prefetcher sees the sequential pattern and fetches ahead with many requests in flight, so 12.6 ns a message is essentially the cost of moving data. In both cases only the producer touches these lines; there isn't a single cross-core round trip.

**The first reader is the expensive one.** Going from "no other core holds my lines" to "every write needs a cross-core round trip" changes the kind of work, and it shows most in the ring that fits in L2: 2.8 ns becomes 18.5 ns. From the second reader on, it's one more recipient in the same round trip — the invalidations go out together and the producer waits for the slowest acknowledgement — so in that ring each extra reader adds 1–5 ns, not another full round trip.

(In the last two paragraphs the numbers are measured; why they come out this way is reasoned from the coherence mechanism and was not verified level by level.)

**When the producer isn't flat out, the store buffer hides the bill.** A write happens in two stages inside the core:

```
producer core
  │
  │ ① the store: address and data go into the store buffer
  ▼
┌──────────────┐
│ store buffer │ ──► the core runs on and write() returns
└──────┬───────┘
       │ ② finished later by the hardware, without holding up later instructions
       ▼
  coherence between cores
       ├──► invalidate every reader core holding a copy of the line
       ├──► wait for all of them to acknowledge
       └──► only once it owns the line does the store reach L1
```

The cross-core round trip — invalidate, wait for the acknowledgements — all happens in ②. When the producer is slow (one message every 2 µs), ② is long finished before the next write and the store buffer always has room, so the median `write()` stayed at 10 ns (timer resolution) for 0 to 5 readers, and only the tail moved — p99.9 from 20 to 70 ns. Flat out, earlier stores are still waiting for acknowledgements while new ones keep arriving; the store buffer fills, the core has to stall, and only then does it show up as slower writes and lower throughput. "Flat out" in the table means writing and doing nothing else; a real producer decodes and builds each record first, and that work sits between its writes.

**Who runs up the bill: a reader that sits spinning on the newest slot.** The loop belongs to the caller, so each reader picks how it waits. A reader on the hot path has to spin and pay. A reader that isn't in a hurry — the disk writer, a monitor — can wake up every so often and read everything that piled up in one go. At 50,000 messages a second, a disk writer that wakes every 1 ms reads batches of 50, far inside the roughly 10-second overrun headroom worked out in 2.3.2, and it costs the producer about one invalidation per wake-up rather than one per message. (That last part follows from the mechanism; it wasn't measured separately.)

So the honest sentence is: **more readers never make the producer wait, but they are not free.**

One more thing the table doesn't say: it measures how much readers slow the producer down, not how long a reader waits for a message. That is roughly one cross-core transfer, and it isn't measured here.

---

### 1.6 When Not to Use a Broadcast Ring

Back to the opening choice: several SPSC queues, or one broadcast ring. They differ in one thing — **whether the producer looks at where the readers are**.

Several SPSC queues means looking. What looking buys is that 1.5.1 and 1.5.2 can't happen: the producer never overwrites a slot a reader hasn't finished, so there are no silent overruns and no half-written reads; and each queue can carry only the part its reader needs. What it costs: the producer's work grows with the number of readers, one copy per reader; when a reader falls far enough behind to fill its queue, the producer has to choose between waiting and dropping on the spot; and the set of readers has to be known up front, so attaching a new one means touching the producer.

A broadcast ring means not looking. One write, readers attach whenever they like, and the producer's steps never change. The cost is all of 1.5: readers carry overruns and torn reads themselves, every reader has to go through the full stream, and busy-polling readers still make each write more expensive.

The table in 1.5.3 also lets you compare the hardware bills. The first reader is the expensive one; each extra reader adds 1–5 ns. If every reader needs everything, N SPSC queues mean N copies of every message, each watched by its own reader and each needing its own invalidation, while the broadcast ring writes once and every reader after the first adds a few nanoseconds. If each reader needs only a part — stocks split across a few compute threads, say — every message goes into exactly one queue with one reader watching, so the producer's cost stays at roughly the one-reader level, plus the check on that reader's position, however many readers there are; and no reader has to skip over messages meant for others. (This paragraph is reasoned from the table and the mechanism; it was not measured with SPSC queues.)

So: when readers all need the full stream, come and go, or live in other processes (disk, republishing, monitoring), use the broadcast ring; when readers each need a subset, or a drop must be known the moment it happens, use per-reader SPSC queues. The two combine: the feed thread writes every message into the broadcast ring for the readers that aren't in a hurry, and also into the SPSC queue of the compute thread that owns that stock. Having a separate thread read the ring and redistribute instead puts one more cross-core handoff on the hot path.

---

## 2. Into Shared Memory

### 2.1 `shmmap`: Four Calls

In deployment the producer and the readers are separate processes. The ring goes into POSIX shared memory:

```cpp
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

template <class Q> Q* shmmap(const char* name) {
    int fd = shm_open(name, O_CREAT | O_RDWR, 0666);                          // ① open (or create) by name
    if (fd == -1) return nullptr;
    if (ftruncate(fd, sizeof(Q))) { close(fd); return nullptr; }              // ② size it to the queue
    Q* ret = (Q*)mmap(nullptr, sizeof(Q), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);  // ③ map it
    close(fd);                                                                 // ④ the mapping survives
    return ret == MAP_FAILED ? nullptr : ret;
}
```

- **Same name, same memory.** On Linux the object lives under `/dev/shm` (tmpfs, never on disk). Producer and readers all call `shmmap` with the same name.
- **No constructor runs.** `mmap` returns bytes that are merely *viewed* as a `Q`. The queue relies on fresh memory being zero — `idx = 0` and `write_idx = 0` is an empty queue — and `ftruncate` guarantees the new range is zero-filled.
- **It outlives the processes** until `shm_unlink` or reboot.
- **One queue, one writer.** `++write_idx` is a plain increment; two writers would trample each other. Each feed gets its own queue.

### 2.2 Same Bytes, Different Addresses

The rule that matters most comes from running it. Two processes mapped the same named region (measured with Windows' equivalent, `CreateFileMapping` + `MapViewOfFile`):

```
[producer] view at 0000017987cc0000
[reader  ] view at 000001ae3be70000
[reader  ] m->self = 0000017987cc0048   vs my address of this block = 000001ae3be70048   (DIFFERENT)
```

All messages arrived, and **the same physical memory sat at different virtual addresses in the two processes.** A pointer stored inside the region — even a pointer to the region itself — is wrong on the other side. A pointer to a string literal happened to match because both processes were the same executable, loaded at the same base; different programs or address-space randomization break that. Don't rely on it.

So **elements in shared memory must be self-contained**: integers, floats, fixed-size arrays. No pointers of any kind — not to the heap, not into the region, not to literals, and no vtable pointers, so no virtual functions. That's why the security ID is `char SecurityID[31]` and not `std::string`, and `std::string` fails twice over: a long string's bytes live on the writer's heap, and a short one (small-string optimization) stores a pointer to *its own internal buffer* — measured with libstdc++, `&s` ended in `…880` and `s.data()` in `…890` — which points to the wrong place once the region is mapped elsewhere.

The same reasoning yields the other contracts both sides must share: one struct definition compiled the same way (change the layout and old shared objects no longer match — rename the region or `shm_unlink` it first); and `alignas` still holds, because `mmap` returns page-aligned addresses and the queue sits at the start.

---

### 2.3 Three Deployment Traps

#### 2.3.1 The First Lap Pays Page Faults

Shared memory is allocated on demand: a 4 KiB page gets a physical page the first time it's touched. A slot is 128 bytes, so **every 32 writes step into a fresh page**. Measured on a 64 MiB Windows mapping (Linux tmpfs works the same way; the numbers differ):

| | Lap 1: mean / p99 | Lap 2: mean / p99 |
|---|---|---|
| fresh mapping | 56.1 ns / 1,302 ns | 8.6 ns / 10 ns |
| one byte written to every 4 KiB page before starting | 9.0 ns / 10 ns | 8.8 ns / 10 ns |

That's about 1.5 µs per fault ((56.1 − 9.0) × 32). Touch every page before the open and the first lap looks like the second — the same rule as for memory pools ([#3](/posts/hot-path-memory-allocators/)): never let a first time happen on the hot path.

#### 2.3.2 A Slow Reader Gets Lapped: Headroom = Capacity ÷ Rate Gap

If a reader spends longer per message than the producer's interval, it falls behind steadily; once it is `CNT` messages behind, it's lapped and drops data silently. Seconds of headroom = 524,288 ÷ (feed rate − processing rate); a reader that stops entirely has 524,288 ÷ feed rate — at 50,000 messages per second, about 10.5 seconds. Keep slow work out of the `read()` loop (hand it to another queue or thread) and monitor the lag, `write_idx − next_idx`.

#### 2.3.3 A Restarted Reader Loses Everything Unless It Saved Its Cursor

`getReader()` starts at the next message, so a recorder that crashes at 10:00:00 and comes back at 10:00:03 silently skips three seconds — 150,000 messages at 50,000 per second. `next_idx` is public and private to the reader, so it can be persisted and restored. Measured with `CNT = 8`:

```
reader read 1..5, "crashed" with next_idx = 6; producer wrote 6..10
  rebuilt with getReader()       -> 10            (6..9 lost)
  resumed from saved next_idx    -> 6 7 8 9 10    (nothing lost)
saved cursor more than a lap behind (producer at 30)
  first read() returns 30, skipping 24 (= 3 laps); 23..29 were still in the ring but are never revisited
```

Resuming works as long as the reader is less than one lap behind; save the cursor outside the process, or it dies with it. The mirror-image trap: **the queue is recreated** (say, `shm_unlink` before each trading day) **but an old reader keeps running.** New stamps start at 0, the reader's cursor is in the millions, `int(new_idx - next_idx) < 0` holds forever, and `read()` returns `nullptr` — it looks like "no new messages" and is actually stuck until the new stamps catch up (measured: cursor 1000, nothing read while the new writer wrote 1..999). Restart readers with the queue, or detect stamps going backwards.

