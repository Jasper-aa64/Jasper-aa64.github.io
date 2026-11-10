---
title: "Trading System Notes #5: An SPMC Broadcast Ring in Shared Memory"
date: 2026-10-04
lastmod: 2026-11-10
slug: "spmc-shared-memory-broadcast-ring"
description: "A single-producer multi-consumer ring where every reader sees every message and the producer never waits: a sequence stamp in every slot, private reader cursors, one wrap-safe subtraction with three meanings — and the bill the readers pay instead: silent overruns, torn reads, readers that catch up taking the very line the producer writes next, and the shared-memory traps of addresses, first-lap page faults and restarts."
summary: "Market data has one producer and several consumers, each of which must see every message, and the producer is the hot path that may not wait for anyone. The answer is a broadcast ring: every slot carries its own sequence stamp, readers keep private cursors, and the producer overwrites the oldest slot without ever reading reader state. The price moves to the readers — overruns are silent, a re-check after reading can't catch a half-written slot unless the writer invalidates the stamp first, and readers that catch up take the line the producer writes next, so every flat-out write costs more. Moving the ring into shared memory adds three more rules: nothing inside it may be a pointer, the first lap pays a page fault every 32 messages, and a restarted reader loses everything unless it saved its cursor."
chapter: 1
categories: [Systems]
tags: [cpp, lock-free, spmc, shared-memory, ring-buffer, atomics, market-data, hft, low-latency]
toc: true
homepage: false
---

An exchange's Level-2 feed arrives on one callback thread: trades and order updates, tens of thousands a second when the market is busy. There is more than one consumer downstream — one writes every message to disk, one republishes over MQTT, one runs live analytics — and **each of them must receive every message**.

How do you hand one message to three readers? The first idea is the SPSC queue from [#4](/posts/lock-free-queue-logger-micro-batching/): three of them, with the producer writing every message three times. An SPSC producer reads the consumer's position to know whether the queue is full, and that read pays for itself: the producer never overwrites data a reader hasn't read, and if it does drop something, it knows on the spot whose message it dropped. The cost is that once any reader falls behind and its queue fills, the producer has to choose right there: drop, or wait. Here the producer is the market-data hot path. **It can never wait for any reader.**

This post walks through a roughly fifty-line answer: an SPMC broadcast ring. Its trade is that the producer doesn't look at the readers at all and simply overwrites the oldest slot once the ring is full. The idea fits in one sentence — move the "this message is published" signal out of a shared index and into each slot — but its consequences take a while to work through. Part 1 is the ring itself, what it does not guarantee, how readers still make the producer pay, and when not to use it; Part 2 is what changes when it moves into memory shared between processes.

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

The producer waits for nobody, and in exchange two things go unguaranteed on the readers' side: **a lapped reader doesn't know it lost messages, and a message it reads may be half-written**.

#### 1.5.1 Overruns: A Reader Skips Messages Without Knowing

With `CNT = 8`, a reader that hasn't read anything while the producer wrote 20 messages looks at the slot where message 1 should be. The stamp there is 17, the difference 16 > 0, so it gets message 17, then 18, 19, 20. **Messages 1–16 were never delivered, and `read()` says nothing about it**: it returns only a pointer and changes `next_idx` itself, and the caller can't tell from the return value that anything was skipped.

**The number skipped is that positive difference.** Have `read()` report it, or accumulate `skipped += diff` in the `Reader`, and one line makes overruns visible. Without changing the queue, the only way to find the gap is a sequence number carried in the message itself.

In production `CNT = 524288`, so a reader has to fall half a million messages behind before it's lapped, which looks far away. But as long as a reader handles a message more slowly than the feed delivers one — formatting a string, a synchronous MQTT publish, an `fprintf` per message — its lag only grows, and sooner or later it reaches that edge (how long it lasts is in 2.3.2).

---

#### 1.5.2 Torn Reads: Re-Checking the Stamp Works Only If the Producer Invalidates It First

`read()` returns `&blk.data`, a pointer into the shared slot, and the reader then reads the fields one by one. If the producer comes around and rewrites that slot meanwhile, the reader sees a mixture of old and new fields: a **torn read**.

The first fix that comes to mind is a re-check: copy the data out, read the stamp again, and discard the copy if the stamp changed. The stress test below uses the setting most likely to tear: `CNT = 4`, the producer writing flat out, three seconds per case. It only shows whether tearing happens and which fix stops it, not how often it happens in production.

| Case | Accepted reads | Torn among them |
|---|---|---|
| As written: read through the pointer | 59,869,704 | 3,269,273 (≈ 5.5%) |
| Re-read `idx` after copying, discard if changed | 43,942,557 (8,861,343 discarded) | 2,084,572 (≈ 4.7%) |
| Producer **invalidates the stamp first**, then writes, then stamps; reader re-checks | 38,607,078 (6,436,383 discarded) | **0** |

**The second row re-checks and still tears 4.7% of the time; the problem is when the producer changes the stamp.** This producer writes the data first and changes the stamp last. Halfway through a rewrite the stamp is still the old one, so the reader's re-check sees "unchanged" and accepts a half-written record. So the producer must invalidate the old stamp before it touches the data, which is the third row:

> **Making the re-check work: the producer writes in three steps, the reader re-checks after copying**
>
> ```cpp
> // producer: three steps instead of two
> ((std::atomic<uint32_t>*)&blk.idx)->store(0, std::memory_order_relaxed);         // ① invalidate the stamp first
> std::atomic_thread_fence(std::memory_order_release);
> writer(blk.data);                                                                 // ② then write the data
> ((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release); // ③ finally stamp the new number
> // reader: load the stamp (acquire); if it's the one wanted → copy the data → atomic_thread_fence(acquire) → load the stamp again;
> //         a number different from the one seen before the copy means discard this copy
> ```
>
> - **If the stamp is still that number at the re-check, not a byte of the data was touched.** Any overlap between the copy and a rewrite leaves the reader seeing a stamp of 0 (rewrite in progress) or the new number (rewrite done), and both are discarded.
> - **Each fence enforces one order.** The producer's release fence keeps "stamp invalidated first, data changed after"; the reader's acquire fence keeps "data copied first, stamp re-checked after"; neither the compiler nor the CPU may swap them.
> - **Under the strict C++ memory model, the data fields read during the copy must be atomics too**, or they race with the producer's writes. The numbers above were measured on x86.

**With a big ring and fast readers, tearing is rare**: the producer has to come back round to the same slot during the few tens of nanoseconds the reader spends copying, which means lapping the reader a full lap first. But a reader that can be lapped can tear, and only the three-step write plus re-check rules it out.

---

### 1.6 On Real Hardware, Do Readers Slow the Producer?

1.5 says the producer waits for nobody; that's what the code says. But the readers touch the same memory from other cores, and the hardware keeps its own account.

The conclusion first: **readers never make the producer wait, but every message travels between the two cores twice. Normally those two trips aren't charged to the producer; only when the producer writes flat out and the readers keep up does every write get more expensive. To remove them from the hot path entirely, the only way is not to hand off across cores there (1.6.4).**

#### 1.6.1 Two Cross-Core Trips: Invalidate, Then Fetch Back

Caches are managed in lines of 64 bytes. Several cores can each hold a copy of the same line; a core that wants to write has to have the others invalidate their copies and wait for their answers ([MESI](/posts/low-latency-mesi-cache-coherence/)). When the line is in another core, a round trip is about 20–100 ns ([reference 2.1](/ref/cpu-memory/#latency)).

A reader that has read the newest message keeps reading the stamp `idx` of the next slot, so it always holds a copy of the line that stamp is in (1.1). So every message makes two trips:

1. **The producer writes**: it first has the reader invalidate its copy and waits for the answer; only with the line exclusive can it write.
2. **The reader reads**: its copy has been invalidated, so its next read misses and has to fetch the changed line back from the producer's core.

**The two trips can't be saved**: the signal the reader waits for is the stamp, and publishing means writing the stamp. With several readers, the first trip has several copies to invalidate, but the notices go out together and the answers are awaited together.

False sharing comes on top of these two trips: if a reader's progress counter sat on the same line as the producer's write counter, every update by the reader would take that line away; separating them by cache line removes it ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)). This ring's reader cursors are private, so it doesn't pay that.

---

#### 1.6.2 Who Pays for the Two Trips: It Depends on How Fast the Producer Writes

The two trips always happen; what differs is whether the producer waits. A write first goes into a small queue inside the core, the store buffer, and the ring's `write()` (the member function from 1.2, pure user space, no kernel) returns at once while the first trip is handled in the background; the second trip is the reader's own fetch. So the question is whether the background keeps up.

**Normal times: the producer doesn't notice.** Level-2 messages are on average tens of microseconds apart, long enough for the background trip to finish. Measured with one write every 2 µs and 0 to 5 readers, the median `write()` stayed at 10 ns (the smallest step the timer can resolve); only the slowest one in a thousand moved, from 20 ns to 70 ns. For the message itself, though, the two trips are always on the way: **from the producer's write to the reader having it, end to end, about 40–200 ns — the price of a cross-core handoff itself**.

**Flat out, readers keeping up: every write costs more.** Right after the open the data comes in waves and the producer writes back to back. The store buffer has only a few dozen entries, a few messages fill it, and the core has to stop; writes drain in order, and when the one for the reader's line comes up, it has to wait for the first trip's answer. Measured: the producer writing flat out, readers on other physical cores only reading (Ryzen 5 5600GT, Windows, median of three 1-second runs; 512 KiB fits in cache, 64 MiB is the production size).

| ns per `write()` | 0 readers | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 512 KiB ring, readers check the stamp only | 2.8 | 18.5 | 24.0 | 25.3 | 26.4 | 28.0 |
| 512 KiB ring, readers also read the contents | 2.8 | 22.8 | 25.8 | 28.5 | 32.5 | 37.0 |
| 64 MiB ring, readers check the stamp only | 12.6 | 15.3 | 17.4 | 19.9 | 22.5 | 26.0 |
| 64 MiB ring, readers also read the contents | 12.6 | 20.1 | 26.8 | 29.8 | 33.8 | 38.7 |

**On the small ring the first reader takes each write from 2.8 to 18.5 ns, from "nobody takes my lines" to "every write has to take its line back first"**; after that each extra reader adds only 1–7 ns, because the invalidation notices go out together. On the large ring a line has been pushed out to memory by the time the producer comes round, so even with no reader it has to come from far away, and the first reader adds less. Each write pays less extra than a full round trip, which says the invalidation notices of consecutive writes are in flight overlapping one another.

**Flat out, readers falling behind: nothing taken.** Real readers do work on every message; if they can't keep up they fall behind and read slots finished long ago, never touching the line the producer is about to write. A different program measured this (64 MiB ring): 1–4 readers a few thousand messages behind took 13.0–13.9 ns a write, the same as the 12.6–14.0 ns with no readers; 1 reader right behind took 25.6–35.4 ns. The bill moves to the reader: the further behind, the longer new messages wait, and more than a lap behind it is overrun (2.3.2).

---

#### 1.6.3 How Should a Reader Wait: The Hot Path Watches, Side Readers Read in Batches

`read()` returns at once when there's nothing new; how to wait is up to the reader's own loop. A hot-path reader has to take every message the moment it lands, so it can only watch the next slot and pay both trips. Readers that aren't in a hurry, like the disk writer or a monitor, wake up every so often and read everything that piled up in one go: at 50,000 messages a second, waking every 1 ms means batches of only 50, far inside the overrun headroom (about 10 seconds, 2.3.2). Within a batch it touches the line the producer is about to write only once, on reaching the newest slot: **once per batch, not once per message**.

---

#### 1.6.4 Run-to-Completion: No Cross-Core Handoff on the Hot Path

Those two trips are the price of the cross-core handoff itself; no way of writing the ring removes them. To remove them from the hot path, don't hand off: **one thread does everything from receiving the market data, parsing and computing factors to emitting the signal (run-to-completion), and the data stays in this core's cache the whole way**. The alternative is a pipeline: each step on its own core, connected by queues, and every queue adds two trips.

The cost is that one core's compute is the ceiling, and if one step is slow, all later market data queues up behind it. It scales by sharding: split by stock or channel across several cores, each core handling its own share end to end. The broadcast ring stays, moved to the side, for readers in no hurry like the disk writer and monitors; the cross-core cost lands on them, and the hot path doesn't wait.

> **Cross cores on the hot path or not: first check whether two trips fit the budget**
> One handoff adds 40–200 ns end to end. When the hot path's budget from receiving data to emitting a signal is in microseconds, one or two handoffs are acceptable in exchange for each step owning a core; when the budget is down to a few hundred nanoseconds, merge the hot-path steps into one thread, scale by sharding by stock, and give only the work that isn't urgent to other cores.

---

### 1.7 When Not to Use a Broadcast Ring

Back to the opening choice: several SPSC queues, or one broadcast ring. They differ in one thing — **whether the producer looks at where the readers are**.

Several SPSC queues means looking. What looking buys is that 1.5.1 and 1.5.2 can't happen: the producer never overwrites a slot a reader hasn't finished, so there are no silent overruns and no half-written reads; and each queue can carry only the part its reader needs. What it costs: the producer's work grows with the number of readers, one copy per reader; when a reader falls far enough behind to fill its queue, the producer has to choose between waiting and dropping on the spot; and the set of readers has to be known up front, so attaching a new one means touching the producer.

A broadcast ring means not looking. One write, readers attach whenever they like, and the producer's steps never change. The cost is all of 1.5 and 1.6: readers carry overruns and torn reads themselves, every reader has to go through the full stream, and readers watching the newest slot still make every write cost more when the producer runs flat out.

The table in 1.6.2 also lets you work out the hardware bills: from the second reader on, each extra reader adds only 1–7 ns. If every reader needs everything, N SPSC queues mean N copies of every message, each watched by its own reader and each needing its own invalidation, while the broadcast ring writes once and every reader after the first adds a few nanoseconds. If each reader needs only a part — stocks split across a few compute threads, say — every message goes into exactly one queue with one reader watching, so the producer's cost stays at roughly the one-reader level, plus the check on that reader's position, however many readers there are; and no reader has to skip over messages meant for others.

So: when readers all need the full stream, come and go, or live in other processes (disk, republishing, monitoring), use the broadcast ring; when readers each need a subset, or a drop must be known the moment it happens, use per-reader SPSC queues. The two combine: the feed thread writes every message into the broadcast ring for the readers that aren't in a hurry, and also into the SPSC queue of the compute thread that owns that stock. Having a separate thread read the ring and redistribute instead puts one more cross-core handoff on the hot path.

---

## 2. Into Shared Memory: When Readers Are Other Processes, Where the Ring Goes and What Needs Rethinking {#shared-memory}

> **What this part solves: the producer and the readers are not in the same process**
>
> - **The pain: readers are deployed as separate processes, and processes don't share an address space**: the disk writer, the republisher and the monitor each run on their own, so one crashing doesn't take down the feed, and each can be restarted alone and attach at any time; but the ring from Part 1 is just an array inside the feed process, and other processes can't see it.
> - **The fix: move the ring into shared memory**: several processes map the same physical memory under one name, and each can read and write the ring (2.1).
> - **Not a line of the ring's code changes**: it hands off only through atomic loads and stores of the stamps, and lock-free atomics act on physical memory, so with two processes mapping the same physical memory they still hold.
> - **What needs rethinking is three things outside the ring**:
>   - **No constructor runs**: what makes the queue count as initialized (2.1).
>   - **The same memory sits at different addresses in the two processes**: what an element may and may not contain (2.2).
>   - **Memory is allocated on demand, and readers crash and restart on their own**: the three traps of deployment (2.3).
> - **It only reaches the same machine**: consumers on other machines can't read shared memory and have to go over the network (the MQTT box in 2.3.2).

### 2.1 `shmmap`: Four Calls

The ring goes into POSIX shared memory, and the producer and each reader call `shmmap` once with the same name:

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

> **Does republishing over MQTT solve a slow reader? No: it solves distribution, and the backlog just moves**
>
> - **MQTT is a publish/subscribe messaging protocol**: it runs over TCP with a broker in the middle (Mosquitto or EMQX, for example). A publisher sends a message to a topic (say `md/SH/600000`), and the broker forwards it to every client subscribed to that topic; the publisher neither knows nor cares how many subscribers there are. It was designed for IoT: the fixed header is as small as 2 bytes, and delivery comes in three levels: QoS 0 at most once, QoS 1 at least once, QoS 2 exactly once.
> - **What it's for is getting market data off this machine**: only processes on the same machine can read shared memory. A trader's desktop market-data screen, monitoring and risk dashboards on another machine, a researcher's Python program: none of them can read the ring, so the data has to go over the network.
> - **Without a broker, the republisher has to be the server itself**: open a TCP connection per receiver, remember who wants which symbols, filter and send to each separately; handle reconnects when someone drops, and buffer separately for whoever is slow. The more receivers, the more complex this process gets and the more easily it is slowed down. With a broker, the republisher sends each message once to the broker, and receivers connect to the broker and subscribe to their own topics: `md/SH/600000` for one stock, `md/SH/#` for the whole Shanghai exchange. Adding a receiver doesn't change a line of the republisher.
> - **The republisher is still a reader of the ring, and can still be lapped**: each `publish` is one TCP send, and sending one by one synchronously makes it exactly the slow reader of 1.5.1. Publish in batches (several messages in one packet), or hand the sending to another thread so that the loop reading the ring only copies.
> - **A slow subscriber's backlog moves into the broker; it doesn't disappear**: the broker keeps a send queue per subscriber, and when the subscriber is slow the queue grows; at the limit, QoS 0 messages are dropped or the broker disconnects that client. It doesn't slow the publisher or the other subscribers, just like the broadcast ring, but its buffers are bounded too.
> - **A buffer only absorbs bursts; it can't remove a sustained rate gap**: if a consumer is slower than the feed over the long run, the backlog grows with the rate gap whether the buffer is in the ring or in the broker, and how long it lasts is capacity ÷ rate gap either way. There are only three real fixes: make the consumer faster (batching, see [#4 Part 5](/posts/lock-free-queue-logger-micro-batching/#micro-batching)), split the work across several consumers, or allow drops (for data where only the latest value matters, like snapshots, keep only the last message per symbol).
> - **It also adds a hop of latency**: a message crosses two TCP legs with the broker in between, usually tens of µs to milliseconds on a LAN. So MQTT is only for consumers off the trading hot path; strategies still read the ring directly.

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

