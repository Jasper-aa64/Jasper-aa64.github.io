---
title: "Trading System Notes #18: Thread-Safe Queues"
date: 2026-10-27
slug: "thread-safe-queue"
description: "A lock-free SPSC ring works because each index has exactly one writer. Once that stops being true, the code has to change: a consumer with nothing to do should sleep, so a blocking queue uses one mutex and two condition variables, rechecks its condition after waking, and loses wakeups if the condition is changed outside the mutex; several producers sharing one ring make rte_ring claim a slot with CAS and publish in claim order, so one stalled producer stalls the rest; Disruptor claims with fetch_add and marks each slot with its lap, so producers never wait for each other and the consumer stops at the gap. Last, the three things a full queue can do: block, drop, or overwrite."
summary: "From one mutex to many producers: condition variables and lost wakeups in a blocking queue, rte_ring's two pairs of indices and in-order publishing, Disruptor's availability flags, and whether a full queue should block, drop, or overwrite."
chapter: 3
categories: [Systems]
tags: [cpp, concurrency, condition-variable, lock-free, mpmc, disruptor, ring-buffer, hft, low-latency]
toc: true
---

A strategy thread hands persistence requests to an archiving thread, several strategy threads hand orders to one gateway thread, a market-data thread hands updates to several strategies: almost every thread in a trading system is connected to the next by a queue. The SPSC ring in [#4](/posts/lock-free-queue-logger-micro-batching/) needs no lock because each index has exactly one writer: the producer only changes the write index and the consumer only changes the read index. In the three cases above, some threads should sleep when they have nothing to do and some queues have several producers, and that premise no longer holds. What follows starts from the plainest version, one mutex, works up to a multi-producer lock-free ring, and ends with what to do when a queue is full.

## 1. A Blocking Queue with a Mutex

### 1.1 The Structure: One Mutex, Two Condition Variables

Start with the first case: the archiving thread has nothing to do most of the time, and its queue is empty. If it spins while it waits ([#16](/posts/spinlock-implementation/)), it ties up a whole core for nothing; what it wants is to sleep when there is nothing to do and be woken when something arrives. With a capacity limit the reverse holds too: when the queue is full the producer sleeps, and it is woken when a slot frees up.

```cpp
template <class T>
class BlockingQueue {
public:
    explicit BlockingQueue(std::size_t cap) : cap_(cap) {}

    bool push(T v) {                       // sleeps while full; returns false once closed
        std::unique_lock lk(m_);
        not_full_.wait(lk, [&] { return q_.size() < cap_ || closed_; });
        if (closed_) return false;
        q_.push_back(std::move(v));
        lk.unlock();                       // unlock before notifying, so the woken thread doesn't wait for the lock again
        not_empty_.notify_one();
        return true;
    }

    std::optional<T> pop() {               // sleeps while empty; returns nullopt once closed and drained
        std::unique_lock lk(m_);
        not_empty_.wait(lk, [&] { return !q_.empty() || closed_; });
        if (q_.empty()) return std::nullopt;
        T v = std::move(q_.front());
        q_.pop_front();
        lk.unlock();
        not_full_.notify_one();
        return v;
    }

    void close() {
        {
            std::lock_guard lk(m_);
            closed_ = true;
        }
        not_empty_.notify_all();           // wake every sleeper so it sees closed_
        not_full_.notify_all();
    }

private:
    std::mutex m_;
    std::condition_variable not_empty_;    // consumers wait here for "has data"
    std::condition_variable not_full_;     // producers wait here for "has room"
    std::deque<T> q_;
    const std::size_t cap_;
    bool closed_ = false;
};
```

One mutex `m_` protects `q_` and `closed_`, and every read and write of them happens under it. A **condition variable** is the tool that lets a thread sleep until a condition holds: `wait` puts the thread to sleep on it, and another thread wakes one sleeper with `notify_one` or all of them with `notify_all`.

There are two condition variables here, one per kind of wait: consumers wait on `not_empty_` for data, producers wait on `not_full_` for room. They are separate so that a notify wakes the right thread. A producer that adds an element should wake a consumer; if everyone slept on one condition variable, `notify_one` could wake another producer, which would find the queue still full and go back to sleep, while the consumer that should have woken stays asleep.

Both `push` and `pop` release the lock before notifying. Notifying under the lock is also correct, but the first thing the woken thread does is reacquire the lock, which the notifier still holds, so it immediately waits again. **Unlocking before notifying only saves that short wait, and it relies on the condition having been changed under the lock**; 1.3 shows why that premise matters.

### 1.2 Condition Variables: You Wait for a Condition, Not a Notification

`not_empty_.wait(lk, pred)` is the same as this loop:

```cpp
while (!pred())
    not_empty_.wait(lk);   // unlocking and sleeping are one step; on waking it relocks, then returns
```

**After waking, the condition has to be checked again**, for two reasons:

- **Spurious wakeups**: the standard allows `wait` to return when nobody notified, for example when the underlying futex wait is interrupted by a signal. The queue may still be empty.
- **Someone else got there first**: a producer adds an element and `notify_one` wakes sleeping consumer A. A has to reacquire the lock before returning, and in the meantime consumer B, which just arrived and never slept, takes the lock first, sees a non-empty queue, and takes the element. By the time A has the lock, the queue is empty again.

Written as `if (q_.empty()) not_empty_.wait(lk);`, both cases leave A calling `front()` on an empty `deque`, which is undefined behavior.

A condition variable stores no state: a notify sent while nobody waits is simply gone. Whether there is data is recorded in `q_`, under the lock; the condition variable only carries one message: the condition may have changed, go and look again.

### 1.3 Lost Wakeups: Changing the Condition and Notifying Must Be Separated by the Mutex

`wait` can be relied on because of one atomicity: from checking the condition until falling asleep the consumer holds the lock, and "unlock" and "sleep" are a single step. That only helps if the producer changes the condition while holding the same lock. Then the producer either changes it before the consumer checks (the consumer sees it and doesn't sleep), or gets the lock only after the consumer is asleep (and the notify that follows is sure to wake it).

If the condition is not changed under that lock, wakeups get lost. The usual setting is a blocking wait added on top of a lock-free ring: the producer publishes a sequence number with an atomic and then notifies; the consumer checks the sequence under the lock and sleeps if it is too low.

```cpp
// producer
cursor.store(seq, std::memory_order_release);
cv.notify_all();

// consumer
std::unique_lock lk(m);
cv.wait(lk, [&] { return cursor.load(std::memory_order_acquire) >= seq; });
```

<a href="/images/thread-safe-queue/lost-wakeup.en.svg" target="_blank" rel="noopener"><img src="/images/thread-safe-queue/lost-wakeup.en.svg" alt="Lost-wakeup timeline. Top: the consumer locks and finds the condition false; before it sleeps, the producer writes cursor and notifies, nobody is asleep, and the notify is lost; the consumer then sleeps and nobody wakes it. Bottom: the producer locks before notifying and only gets the lock once the consumer has gone to sleep and released it, so the notify comes after the sleep; the consumer wakes, checks again, and the condition holds." loading="lazy" decoding="async"></a>

Top half: after the consumer has checked but before it sleeps, the producer changes `cursor` and notifies right away. Nobody is asleep, so the notify is lost. The consumer then goes to sleep, no further notify comes, and it sleeps on although the data arrived long ago. The fix is for the producer to take the lock once before notifying:

```cpp
cursor.store(seq, std::memory_order_release);
{ std::lock_guard lk(m); }   // the consumer has either not checked yet (and will see the new cursor) or is already asleep
cv.notify_all();
```

Bottom half: the consumer holds the lock from the check until it sleeps, so the producer's lock has to wait until it is asleep, and the notify always lands after that. **Whenever the condition is not changed under the mutex, take the mutex once before notifying.**

### 1.4 Closing: Letting Sleeping Threads Out

On shutdown the program has to `join` the consumer threads, but they may be asleep in `pop`; with no more data coming they never wake, and the `join` hangs with them. So the queue must be closable: `close()` sets `closed_` under the lock and wakes every thread sleeping on either condition variable, and both `wait` conditions include `closed_`, so a thread that wakes and sees it stops waiting.

After closing, `push` returns `false`. `pop` first drains what is left and returns `nullopt` only once the queue is empty, **so nothing already in the queue is lost by closing it**. This needs `notify_all`, because every sleeping thread has to wake up and see `closed_`.

### 1.5 Cost: Tens of Nanoseconds Without Sleeping, Microseconds With

- **No contention, no sleeping**: one `push` is a lock and an unlock, two atomic read-modify-writes, plus the `deque` work, about 20–50 ns.
- **Contention**: the cache line holding the lock moves between cores, as in [#16](/posts/spinlock-implementation/); each operation pays one extra cross-core transfer (about 20–100 ns), and the more cores contend, the slower it gets.
- **Sleeping**: going to sleep on a futex and being woken, from the notify until the other thread actually runs, takes about 2–10 µs ([Reference 2.1](/ref/cpu-memory/#latency)).

So **a blocking queue wins on CPU use and on being easy to get right, not on speed**. It suits paths that can afford a few microseconds, such as persistence, reconciliation and admin commands; hot paths like market data to strategy use lock-free rings with busy waiting ([#4](/posts/lock-free-queue-logger-micro-batching/), [#5](/posts/spmc-shared-memory-broadcast-ring/)), on pinned threads that never sleep.

## 2. Lock-Free Rings for Multiple Producers: rte_ring and Disruptor

### 2.1 rte_ring: Claim a Slot First, Then Publish in Order

When several strategy threads send orders to one gateway thread (multi-producer, single-consumer, MPSC), the write index has several writers and has to be claimed with CAS. After claiming a slot the producer still has to write the data, so there is a gap between "claimed" and "written", and the consumer must not read a slot that has been claimed but not yet written. rte_ring (DPDK's lock-free ring) handles this with two indices per side:

- `prod_head_`: how far producers have claimed; producers compete for it with CAS;
- `prod_tail_`: how far producers have finished writing, i.e. how far consumers may read;
- the consumer side mirrors it: `cons_head_` is how far consumers have claimed, `cons_tail_` how far they have finished reading, i.e. how far producers may overwrite.

```cpp
template <class T, uint32_t N>             // N is a power of two
class MpmcRing {
    static_assert((N & (N - 1)) == 0);
public:
    explicit MpmcRing(uint32_t start = 0)  // adjustable start, for testing index wraparound
        : prod_head_(start), prod_tail_(start), cons_head_(start), cons_tail_(start) {}

    bool try_push(const T& v) {
        uint32_t head = prod_head_.load(std::memory_order_relaxed);
        do {
            if (head - cons_tail_.load(std::memory_order_acquire) == N)
                return false;                                        // full
        } while (!prod_head_.compare_exchange_weak(head, head + 1,   // ① claim a slot
                                                   std::memory_order_relaxed));
        buf_[head & (N - 1)] = v;                                    // ② write the claimed slot
        while (prod_tail_.load(std::memory_order_acquire) != head)   // ③ wait for earlier producers to publish
            _mm_pause();
        prod_tail_.store(head + 1, std::memory_order_release);       // ④ publish in order
        return true;
    }

    bool try_pop(T& out) {
        uint32_t head = cons_head_.load(std::memory_order_relaxed);
        do {
            if (head == prod_tail_.load(std::memory_order_acquire))
                return false;                                        // empty
        } while (!cons_head_.compare_exchange_weak(head, head + 1,
                                                   std::memory_order_relaxed));
        out = buf_[head & (N - 1)];
        while (cons_tail_.load(std::memory_order_acquire) != head)
            _mm_pause();
        cons_tail_.store(head + 1, std::memory_order_release);       // this slot can go back to producers
        return true;
    }

private:
    alignas(64) std::atomic<uint32_t> prod_head_{0};   // how far producers have claimed
    alignas(64) std::atomic<uint32_t> prod_tail_{0};   // how far producers have written, i.e. consumers may read
    alignas(64) std::atomic<uint32_t> cons_head_{0};   // how far consumers have claimed
    alignas(64) std::atomic<uint32_t> cons_tail_{0};   // how far consumers have read, i.e. producers may overwrite
    alignas(64) T buf_[N];
};
```

`try_push` has four steps:

1. Read `prod_head_`, check for full with `head - cons_tail_ == N`, then CAS it from `head` to `head + 1`. A failed CAS means another producer got there first; `head` now holds the latest value, and the loop checks for full again.
2. Write the data into the claimed slot.
3. Wait until `prod_tail_` reaches `head`, i.e. until every earlier producer has published.
4. Set `prod_tail_` to `head + 1` (release); from this moment consumers can read the slot.

The indices are `uint32_t` and only ever increase; they are stored unmasked and masked with `& (N - 1)` only when used. Empty is `head == tail`, full is `head - tail == N`. If the masked value were stored back, the indices could only range over 0 to N − 1, and empty and full would both look like two equal indices, with no way to tell them apart ([#4](/posts/lock-free-queue-logger-micro-batching/) 1.1).

When an index reaches $2^{32} - 1$ and is incremented, it wraps to 0, and the checks still work. Unsigned subtraction is modulo $2^{32}$, so as long as the real difference is at most N, `head - tail` gives the real difference. N is a power of two and divides $2^{32}$, so the slots also line up across the wrap: $2^{32} - 1$ lands in slot N − 1 and the next index, 0, lands in slot 0. **With indices that only increase and a power-of-two N, wraparound needs no special handling.** The test below starts the indices at $2^{32} - 1001$, so they wrap past 0 during the run, and the results are still correct.

### 2.2 Publishing in Order: One Number Can Only Say "Everything Before Is Done"

The wait in step ③ is the heart of this design. `prod_tail_` is just one number, and consumers read it as "every slot below here has been written". Say A claims 5 and B claims 6, and B finishes writing first. If B set `prod_tail_` to 7 straight away, a consumer would go and read 5, which A hasn't written yet. So B has to wait until `prod_tail_` becomes 6 (A has published) before setting it to 7: **publishing has to happen in the same order as claiming.**

The load in step ③ has to be acquire. A publishes `prod_tail_ = 6` with a release store and B reads 6 with acquire, so A's write into slot 5 happens before B's release store. A consumer that reads 7 with acquire then sees the data in both slot 5 and slot 6.

The price: if A is descheduled between ① and ④, B, C and everyone after them spin at ③ until A comes back. This is the same problem as the ticket lock in [#16](/posts/spinlock-implementation/) 2.1, where the thread whose turn it is gets descheduled and the whole queue stops. So strictly speaking this is not lock-free: **one stalled producer can stall every other producer.** DPDK can get away with it because its threads are pinned to dedicated cores and never descheduled; with ordinary, preemptible threads, the worst case for this ring is a stall of several milliseconds.

The consumer side is fully symmetric: consumers claim from `cons_head_` with CAS, advance `cons_tail_` in order once they have read, and producers check `cons_tail_` to see whether they may overwrite.

### 2.3 Disruptor: Every Slot Marks Itself "Written"

The Disruptor is the ring buffer LMAX (a foreign-exchange trading venue) built for its matching engine. It keeps track differently, so that producers never wait for each other:

- **Sequence numbers instead of indices**: 64-bit signed sequence numbers that only increase and in practice never run out; a slot's position is `seq & (N - 1)`.
- **Claiming with `fetch_add`**: each producer gets its number with one `fetch_add(1)`, which cannot fail and never retries. It still has to wait when the ring is full; see 2.4.
- **An availability flag per slot**: when a producer has written its slot, it writes the lap (`seq / N`) into that slot's flag, regardless of whether earlier numbers are done.

```cpp
template <class T, int64_t N>              // N is a power of two
class MultiProducerRing {
    static_assert(N > 0 && (N & (N - 1)) == 0);
public:
    MultiProducerRing() {
        for (auto& a : avail_) a.store(-1, std::memory_order_relaxed);
    }

    // ---- producers, any number of them ----
    int64_t claim() {
        int64_t seq = claim_.fetch_add(1, std::memory_order_relaxed);  // claim a number: one step, no retry
        while (seq - N > consumed_.load(std::memory_order_acquire))   // full: wait until the consumer has read seq - N
            _mm_pause();
        return seq;
    }
    T& slot(int64_t seq) { return buf_[seq & (N - 1)]; }
    void publish(int64_t seq) {                                       // mark only this slot, wait for no one
        avail_[seq & (N - 1)].store(seq / N, std::memory_order_release);
    }

    // ---- the single consumer ----
    bool try_consume(T& out) {
        const int64_t seq = next_;
        if (avail_[seq & (N - 1)].load(std::memory_order_acquire) != seq / N)
            return false;                                             // this slot isn't written yet (for this lap)
        out = buf_[seq & (N - 1)];
        consumed_.store(seq, std::memory_order_release);              // seq has been read and may be overwritten
        next_ = seq + 1;
        return true;
    }

private:
    alignas(64) std::atomic<int64_t> claim_{0};       // next number to hand out
    alignas(64) std::atomic<int64_t> consumed_{-1};   // last number the consumer has read
    alignas(64) int64_t next_ = 0;                    // next number the consumer will read
    std::array<std::atomic<int64_t>, N> avail_;       // the lap each slot was last written in
    alignas(64) T buf_[N];
};
```

A producer writes one element in three steps: `claim()` for a number, write into `slot(seq)`, then `publish(seq)`. The consumer reads forward from `next_`, and before each slot it checks whether the flag equals `next_ / N`: if so it reads, if not it stops there and tries again later. The flag holds the lap rather than `true` because each slot is reused every N numbers, and a `true` left over from the previous lap would look the same as this lap's; the lap number is different every time round.

Compare with rte_ring: A claims 5, B claims 6, B finishes first, calls `publish(6)` and returns. The consumer reaches 5, sees the flag isn't set, and stops. When A finishes and calls `publish(5)`, the consumer goes on to read 5 and 6. **Delivering in order means a gap can't be avoided; the two designs differ only in who waits**: rte_ring makes the later producers spin, Disruptor makes the consumer stop at the gap while the other producers keep writing until the ring is full. If A stays stalled, neither design can deliver anything past 5; Disruptor just stops tying up the other producers' threads as well.

### 2.4 Backpressure and Wait Strategies: When Full, Wait for the Slowest Consumer; When Empty, Choose How to Wait

**When full.** A producer holding number `seq` is about to write a slot whose previous occupant was `seq - N`; it may only overwrite once the consumer has read `seq - N`, so `claim()` waits until `consumed_ >= seq - N`. A slow consumer slows the producer down and no data is lost; this is called **backpressure**.

With several consumers, the Disruptor has every consumer read every event (a broadcast), each tracking its own sequence; producers wait for the slowest one, which the Disruptor calls the gating sequence, the minimum over all consumers' sequences. Consumers can also depend on each other: C only reads sequences that both A and B have finished, i.e. the minimum of the two. A common diamond is: producer → journaling and replication → business logic.

**When empty.** The Disruptor has four wait strategies, which are exactly the four choices in [#17](/posts/wait-free-sticky-counter/) 1.9:

- BusySpin: spin with `_mm_pause`;
- Yielding: spin 100 times, then `yield`;
- Sleeping: spin, then yield, then `sleep_for`;
- Blocking: a mutex and a condition variable.

Blocking is exactly the situation in 1.3: the sequence is an atomic that isn't changed under the mutex, so the producer has to take the mutex once before notifying. A throughput test with one producer pouring data in shows the four strategies almost identical (about 30 ms for 5 million events each), because the consumer hardly ever waits; **wait strategies differ in the latency of the first event after an idle period, which a throughput test can't measure.**

## 3. When the Queue Is Full: Block, Drop, or Overwrite

A bounded queue that is full has only three options:

| Option | Producer | Data | Where it's used |
|---|---|---|---|
| Block (backpressure) | waits, slowed by the consumer | nothing lost | orders, fills, logs that must reach disk |
| Fail and drop | doesn't wait, learns at once that it failed | the new element is dropped | market data: count the drops, rebuild the book from a snapshot |
| Overwrite | doesn't wait, doesn't know who hasn't read | slow readers lose old data | one-to-many broadcast where only the latest state matters (the SPMC ring in [#5](/posts/spmc-shared-memory-broadcast-ring/)) |

**Which one to pick depends on whether losing an element or slowing the producer costs more.** Orders can't be lost, but a hot thread shouldn't wait without bound either: the usual approach is that a failed `try` rejects the order and reports it to risk and the strategy, rather than silently blocking or silently dropping.
