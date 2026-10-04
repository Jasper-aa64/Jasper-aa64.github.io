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

How do you hand one message to three readers? The first idea is the SPSC queue from [#4](/posts/lock-free-queue-logger-micro-batching/): three of them, with the producer writing every message three times. But an SPSC producer has to read the consumer's position to know whether the queue is full, and once any reader falls behind and its queue fills, the producer must drop or wait. Here the producer is the market-data hot path. **It can never wait for any reader.**

This post walks through a roughly fifty-line answer: an SPMC broadcast ring. The idea fits in one sentence — move the "this message is published" signal out of a shared index and into each slot — but its consequences take a while to work through. Part 1 is the ring itself and what it does not guarantee; Part 2 is what changes when it moves into memory shared between processes.

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

- **The stamp `idx` lives in every slot.** Each block records *which message number it currently holds*. The publication signal is no longer one shared index that everyone reads; it travels with the data. Everything below follows from that.
- **`write_idx` is a plain `uint32_t`, not an atomic.** Only the producer writes it; `getReader()` reads it once when a reader is created.
- **`CNT` is a power of two**, so `% CNT` compiles to a mask (the trick from [#4](/posts/lock-free-queue-logger-micro-batching/)). The stamps are 32-bit and wrap after about 4.29 billion messages; the comparison in `read()` is written for that.

With the Level-2 trade record from the deployment this ring was built for — 88 bytes — a `Block` is 4 bytes of stamp, 4 of padding and 88 of data = 96, rounded up by `alignas(64)` to **128 bytes, exactly two cache lines**. With `CNT = 524288`, one queue is 64 MiB.

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

"Readers can't slow the producer down" sounds like it follows from "the producer never reads reader state". The first half is true — the producer never *waits*. The second half isn't. Producer writing flat out, readers busy-polling on separate physical cores (Ryzen 5 5600GT, Windows, median of three 1-second runs):

| ns per `write()` | 0 readers | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 512 KiB ring (fits in L2), readers only poll | 2.8 | 18.5 | 24.0 | 25.3 | 26.4 | 28.0 |
| 512 KiB ring, readers also read the payload | 2.8 | 22.8 | 25.8 | 28.5 | 32.5 | 37.0 |
| 64 MiB ring (the production size), readers only poll | 12.6 | 15.3 | 17.4 | 19.9 | 22.5 | 26.0 |
| 64 MiB ring, readers also read the payload | 12.6 | 20.1 | 26.8 | 29.8 | 33.8 | 38.7 |

The first reader is the expensive one: in a ring that fits in L2, the producer goes from owning every line and writing at 2.8 ns to 18.5 ns. Each extra reader adds another 1–5 ns.

Readers don't change the producer's *steps*; they change what each step costs in hardware. A reader that polls or reads a slot leaves a read-only copy of that line in its own core. Before the producer can write the slot again, those copies must be invalidated — the S→M upgrade explained in [MESI cache coherence](/posts/low-latency-mesi-cache-coherence/). When the producer is slow, the store buffer hides it: writing one message every 2 µs, the median `write()` stayed at 10 ns (timer resolution) for 0 to 5 readers, and only the tail moved — p99.9 from 20 to 70 ns. Flat out, the store buffer can't keep up and it shows as throughput.

So the honest sentence is: **more readers never make the producer wait, but they are not free.**

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

