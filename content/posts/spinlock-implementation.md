---
title: "Trading System Notes #16: Spinlocks"
date: 2026-10-21
slug: "spinlock-implementation"
description: "When a lock is held for tens to a couple of hundred nanoseconds, std::mutex goes to sleep in the kernel (futex) as soon as the lock is taken, and a sleep plus a wake-up costs microseconds. A spinlock never sleeps, but it only pays while the lock holder keeps running. The simplest CAS loop takes the lock's cache line exclusively on every attempt, so waiters fight over the line and even the holder has to queue to release it; test-and-test-and-set lets each waiter read its own copy; PAUSE in the loop avoids a pipeline flush the moment the lock is freed; and exponential backoff spreads out the rush when it is released. Part 2: a ticket lock queues waiters in arrival order, and an MCS lock has each core watch its own line so a release disturbs only the next one; a reader-writer lock is no faster than a mutex for short reads; umonitor / umwait and WFE let a waiting core stop until the line is written."
summary: "Whether a spinlock is fast depends on what its waiters do: if every attempt is a read-modify-write, they drag the lock's line back and forth. Read before you grab, put PAUSE in the loop, back off after losing, and waiting costs the holder almost nothing."
chapter: 1
categories: [Systems]
tags: [cpp, spinlock, atomics, futex, mesi, pause, ticket-lock, mcs-lock, rwlock, umwait, hft, low-latency]
toc: true
math: true
---

Code such as updating one level of an order book or copying a market data snapshot has to be guarded by a lock; it is called a critical section (the stretch between `lock()` and `unlock()`), and the lock is held for only tens to a couple of hundred nanoseconds. Guard the critical section with `std::mutex`, and a thread that finds the lock taken gets suspended and woken again once the lock is free. That sleep and wake-up costs microseconds, 10 to a hundred or more times the time the lock is held. A spinlock simply doesn't sleep: a thread that can't get the lock stays where it is and keeps looking, and takes over the moment the lock is released.

How it keeps looking decides whether the lock is fast. Look the wrong way and the waiting cores drag the lock's cache line back and forth, slowing down even the core that holds the lock; when the lock is freed, they all rush at it together. Remove these problems one by one and you have a usable spinlock. Before writing any of it, though, it helps to see where the cost of sleeping comes from, and when spinning beats sleeping.

## 1. Writing a Spinlock: From a CAS Loop to TTAS and PAUSE

### 1.1 Futex: Where std::mutex Goes When the Lock Is Taken

What `std::mutex` does on Linux can be written with one atomic integer. It has three states: 0 is unlocked, 1 is locked with nobody waiting, and 2 is locked with someone possibly asleep.

```cpp
#include <atomic>

class SleepingMutex {  // 0 = unlocked, 1 = locked, nobody waiting, 2 = locked, someone may be asleep
public:
    void lock() {
        int c = 0;
        if (state_.compare_exchange_strong(c, 1, std::memory_order_acquire)) return;  // fast path: one CAS
        if (c != 2) c = state_.exchange(2, std::memory_order_acquire);
        while (c != 0) {
            state_.wait(2, std::memory_order_relaxed);  // still 2: sleep in the kernel (a futex on Linux)
            c = state_.exchange(2, std::memory_order_acquire);
        }
    }
    void unlock() {
        if (state_.exchange(0, std::memory_order_release) == 2)
            state_.notify_one();  // someone may be asleep: only then enter the kernel to wake one
    }

private:
    std::atomic<int> state_{0};
};
```

With nobody competing (the state is 0 when `lock()` runs, and no other thread tries to take the lock while it is held, so the state never becomes 2), `lock()` does a single CAS (compare-and-swap: change the value to 1 only if it is 0) and `unlock()` a single `exchange` that turns the 1 back into 0. Both stay in user space and take about 2–6 ns each ([Reference 2.1](/ref/cpu-memory/#latency)); at this point the mutex is as cheap as a spinlock.

The paths split only when the lock is taken. `lock()` first sets the state to 2, meaning "a thread is waiting for this lock; wake it when you release", and then this thread calls `wait` and goes to sleep. On Linux, C++20's `atomic::wait` ends up in the futex (fast userspace mutex) system call: the kernel checks that the integer is still 2, puts the thread on a wait queue keyed by that address, and switches to another thread. The unlocking side sees the old value 2 come back from its `exchange` and calls `notify_one` (another futex call) to wake one waiter. The woken thread has to wait for the scheduler to put it back on a core before it can run its `exchange` and try again. The glibc mutex underneath `std::mutex` uses the same three states.

That round trip costs two system calls (about 0.1–0.5 µs each) plus two thread switches, out and back in, for the waiter (about 1–5 µs each, plus the cost of caches another thread has flushed). If the waiter's core had dropped into a power-saving state, waking it takes longer still ([#1](/posts/cpu-affinity-core-isolation-numa/), section 2.2). Altogether, **from the unlock until the waiter actually runs again takes about 2–10 µs**. But the lock is held for only tens to a couple of hundred nanoseconds: it comes free soon, yet the thread that went to sleep takes over only microseconds later, 10 to a hundred or more times too late. A thread that stays awake and keeps watching the lock takes over the moment it comes free, and that is why spinlocks exist.

Here is where the tens to a couple of hundred nanoseconds come from, from taking the lock through running the critical section to releasing it:

| Step while holding the lock | What actually happens | Nobody competing (data in the core's own cache) | Others competing (lines come from another core) |
|---|---|---|---|
| Lock | One CAS | about 2–6 ns | about 20–100 ns: the previous holder's core just wrote the lock's line |
| Update one order book level | Find the level by price, add the quantity, write it back: about ten instructions | a few to a dozen or so ns | about 20–200 ns: another core just modified the one or two lines holding the level |
| Copy a 10-level snapshot | 10 levels per side, an 8 B price and an 8 B quantity each, 320 B in all, about 5 cache lines | a dozen or so ns | tens of ns to one or two hundred: the 5 lines can be fetched at the same time |
| Unlock | One `exchange` | about 2–6 ns | about 20–100 ns: waiting cores hold copies of the line, which must be invalidated first |

A critical section does one of the two middle rows, plus the lock and the unlock, so the lock is held for tens of nanoseconds with nobody competing and one or two hundred with others competing.

### 1.2 When Spinning Pays: The Holder Must Keep Running

Spinning beats sleeping because the lock will be released soon. That takes two conditions: **the holder keeps running, and the lock is held only briefly**. If either fails, the lock stays taken for a long time.

The first one fails through scheduling. If the holder is taken off the CPU (its time slice ran out, another thread preempted it, it is waiting for I/O), the lock stops with it, and the waiting cores spin for nothing, for a whole time slice: milliseconds, far more than one sleep. It gets worse when a waiter and the holder share a core: the waiter occupies the core spinning, the holder can't get scheduled, and the lock can't be released until the time slice ends. That is why user-space spinlocks always come with pinning: every thread that touches the lock gets its own isolated core ([#1](/posts/cpu-affinity-core-isolation-numa/), section 1.2), so the OS has no reason to take the holder off its core.

The second one fails when the critical section does something slow. Logging, `malloc`, system calls, database queries, waiting on the network: these start at microseconds or may block outright. If the waiting thread is pinned to its own isolated core, the spinning itself wastes nothing, since that core has no other work anyway. The damage lands on the waiting thread: it is usually on the hot path (the one that reads the order book to send an order, say), so every microsecond the holder spends is a microsecond it is late, by an amount nobody can predict, and the tail latency stretches. Spinning and sleeping both pay this, and switching to `std::mutex` doesn't save it. If the slow work can block (a system call, a page fault, waiting on the network), the holder is also taken off the CPU, and the first condition fails too. So keep only the few lines that change data inside the lock: do the lookups and computation outside it, and only write the result inside.

If you can't guarantee both, use the sleeping `std::mutex`, or a compromise: spin for a little while, then sleep if the lock still isn't free. glibc's adaptive mutex (`PTHREAD_MUTEX_ADAPTIVE_NP`) does exactly that, though `std::mutex` doesn't use that type by default.

### 1.3 The Simplest Spinlock: One Atomic and a CAS Loop

A spinlock is just an integer `locked_`: 0 means the lock is free, 1 means someone holds it. `lock()` has to change it from 0 to 1 itself; if it does, it holds the lock and may enter the critical section, and if it can't, someone else holds it. `unlock()` writes 0 back, so the next thread can succeed. Not sleeping means replacing the "sleep in the kernel" step of `SleepingMutex` with "try again":

```cpp
#include <atomic>

class CasSpinLock {
public:
    void lock() {
        int expected = 0;
        while (!locked_.compare_exchange_weak(expected, 1, std::memory_order_acquire,
                                              std::memory_order_relaxed)) {
            expected = 0;  // on failure, expected was overwritten with the current value 1: reset it
        }
    }
    void unlock() { locked_.store(0, std::memory_order_release); }

private:
    std::atomic<int> locked_{0};
};
```

`compare_exchange_weak(expected, 1, …)` means: if `locked_` equals `expected` (0), set it to 1 and return true; otherwise write the current value of `locked_` into `expected` and return false. So after a failure `expected` holds 1 and has to be reset to 0 before the next round. Without the reset, the next round would ask "if it equals 1, set it to 1": the CAS would succeed while someone else holds the lock, and two threads would be in the critical section at once. CAS works this way because its most common use is read the old value, compute a new one, write it back: a failure means someone else just changed it, and the computation has to be redone from the latest value. Handing that value back on failure saves a separate load, and the hardware has read it anyway (x86's `lock cmpxchg` leaves the current value in EAX on failure; ARM's exclusive load has already read it). To double an atomic, for example: `int old = x.load(); while (!x.compare_exchange_weak(old, old * 2)) {}`; after a failure `old` already holds the latest value, so the loop just recomputes: if `x` is 5, `old = 5` is read, and another thread then changes `x` to 7, this CAS fails, `old` becomes 7, and the next round turns 7 into 14. A lock is the opposite case: the expected value is always 0, so it has to be reset every round. `weak` may occasionally report failure even when the values are equal, which happens on ARM when it is built from a pair of exclusive load and store instructions: if an interrupt arrives between the two, or another core touches the line, the exclusive store fails even though the value hasn't changed. x86's `lock cmpxchg` is a single instruction and never does this, so `weak` and `strong` compile to the same code there. On ARM, `strong` wraps the pair in a loop of its own to hide such failures. There is a loop around it anyway, so `weak` is enough; `strong` is for a single check that gives up on failure.

Of the two memory orders passed to `compare_exchange_weak`, the first applies when the CAS succeeds and the second when it fails. The memory orders keep the critical section's reads and writes from leaking out of the lock ([#2](/posts/memory-ordering-false-sharing-dependency-chains/), section 1.5). The successful CAS in `lock()` uses acquire: reads and writes in the critical section can't move before taking the lock, so they see what the previous holder wrote. The store in `unlock()` uses release: reads and writes in the critical section can't move after the release. Paired up, they guarantee that whatever the previous holder wrote inside the critical section is visible to the next holder. The failed CASes acquire nothing, so relaxed is enough for them. Taking the lock needs no release, since release orders what comes before the lock, which has nothing to do with the critical section.

`exchange` makes it shorter: `while (locked_.exchange(1, std::memory_order_acquire)) {}` writes 1 and returns the old value, and an old value of 0 means you took the lock. That is test-and-set (TAS). Either way, every attempt is a read-modify-write (RMW), and both versions share the same flaw.

### 1.4 RMWs Steal the Line: Every Attempt Takes It Exclusive

`locked_` lives in a cache line. On the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a>, that line can have a copy in the L1D of several cores, under the rule in the MESI box on the right: whoever wants to write must first invalidate everyone else's copy ([the MESI post](/posts/low-latency-mesi-cache-coherence/)).

**An RMW is a write**. On x86 the CAS compiles to `lock cmpxchg`, which brings the line into this core in exclusive state (MESI's M or E) whether or not the comparison succeeds, writing the old value back when it fails. On ARM it becomes an instruction like `casal`, again an RMW on that one line. So with 3 cores waiting, each of them steals the line from another core on every spin, at about 20–100 ns per steal ([Reference 2.6](/ref/cpu-memory/#cross-core)). The line travels between the waiting cores nonstop.

Moving the line is only waste in itself; the real damage is that it gets in the holder's way. To release the lock, the holder has to write `locked_`, so it too must get the line back, queued behind the waiters' RMWs: the lock should have been released long ago, but the releasing store still hasn't landed. If the protected data shares the line with `locked_`, every write to the data inside the critical section has to steal the line too, and the lock is held longer. The second problem is easy to fix by giving the lock its own line (`alignas(64)`, [#6](/posts/alignment-layout-cache-dram-geometry/)); the first one needs a different way of waiting.

### 1.5 TTAS: Read First, Grab Only When It Looks Free

A waiter really only needs to know whether the lock has been released, and a read tells it that; only when it sees the lock free is grabbing worth it. That is test-and-test-and-set (TTAS):

```cpp
#include <atomic>
#include <immintrin.h>  // _mm_pause, see 1.6

class TtasSpinLock {
public:
    void lock() {
        for (;;) {
            if (!locked_.exchange(true, std::memory_order_acquire)) return;  // grab once: uncontended, this is the only RMW
            while (locked_.load(std::memory_order_relaxed)) _mm_pause();    // taken: just read until it looks free, then grab again
        }
    }
    void unlock() { locked_.store(false, std::memory_order_release); }

private:
    alignas(64) std::atomic<bool> locked_{false};  // a cache line of its own
};
```

The change is the second line of the loop: once a grab fails, the waiter only does plain reads. **Reads don't need exclusive ownership**, so the 3 waiters each hold a shared copy (MESI's S), and every read hits in their own L1D at about 1 ns, without a single message leaving the core. The holder isn't disturbed, and nobody steals the line during the critical section.

When the lock is released, the holder writes `locked_` and sends one round of invalidations that kills the 3 copies. Each waiter's next read misses, pulls the line back, sees `false`, and only then goes back to the first line to `exchange`. The RMW happens only when the lock looks free; with nobody competing, the first line succeeds at once, as fast as `CasSpinLock`.

Relaxed is enough for the read in the loop. It only decides that grabbing is worth a try; the lock is actually taken by the acquire `exchange`.

### 1.6 PAUSE: Don't Fill the Pipeline With Loads of the Lock Word

The loop `while (locked_.load(...))` is only two or three instructions: load, compare, jump back. When a core spins on it, the moment the lock is freed costs that core a pipeline flush. Here is how it happens:

1. **Loads run ahead.** An out-of-order core doesn't wait for one lap to finish before starting the next. It follows the branch predictor ([#7](/posts/branch-prediction-branch-optimization/)), guessing "spin again" over and over, and issues the loads of dozens of later laps in advance. They all get the old value `true` and queue in the ROB to retire (retiring means confirming results in program order). A value a load got only counts once the load retires.
2. **The lock is released.** The holder writes `locked_ = false`, and an invalidation reaches the waiting core and invalidates the line in its L1. At this point the loads in the ROB have their values but none has retired.
3. **The core checks the order.** x86 promises that loads take effect in program order: a later load may not see an older value than an earlier one. Running a load ahead is a bet that nobody changes the line between the load getting its value and retiring. If the bet wins, the early value is the same one an in-order load would have seen. Now the line has changed inside that window, so those values are no longer guaranteed to be what in-order loads should see. Checking each one would be too expensive, so the hardware doesn't: if any load that has its value but hasn't retired had its line invalidated, the core treats it as a violation.
4. **The pipeline is flushed.** Everything from the oldest affected load on is thrown away and re-executed. This is a memory ordering machine clear. Like a branch mispredict it empties the whole pipeline, tens of cycles, and it lands exactly when the lock has just been freed and speed matters most. The re-executed load gets `false` and the loop should exit, but the predictor kept guessing "spin again", so the exit is one more mispredict and one more flush.

On the hardware map this spans two boxes: the invalidation follows the grey dashed line into the invalidate queue and runs into the row of unretired loads in the ROB.

<a href="/images/spinlock-implementation/pause-rob.en.svg" target="_blank" rel="noopener"><img src="/images/spinlock-implementation/pause-rob.en.svg" alt="What the waiting core's ROB holds when the lock is released. Top, the empty loop: lap 1's load has retired, the loads of laps 2 to 10 already read the old true and haven't retired; when core 0's invalidation arrives all 9 are thrown away and rerun (a memory ordering machine clear), and exiting the loop is one more mispredict. Bottom, with pause: lap 1's load has retired, then a pause of about 140 cycles, and lap 2's load isn't issued yet, so the invalidation finds nothing to throw away and only the mispredict is left. A note gives the cost: noticing the free lock up to about 140 cycles (about 35 ns) late." loading="lazy" decoding="async"></a>

The `pause` instruction exists for exactly this kind of loop. It makes the core wait about 140 cycles (about 35 ns) before going on, and the next lap's load is issued only after that. The load in each lap hits L1 and retires within a few cycles, so when the invalidation arrives there is usually no load that has its value but hasn't retired: step 3 has nothing to check, **the flush of step 4 is avoided**, and only the mispredict at the exit is left. The cost is noticing the free lock a little later: the lock may be freed in the middle of a pause, and the next load waits for it to end, up to one `pause`, about 35 ns, late. It has two more benefits: spinning more slowly lowers the core's power draw, and if the core runs two hardware threads (SMT), the sibling gets the execution resources ([#1](/posts/cpu-affinity-core-isolation-numa/), section 2.1).

One `pause` is about 140 cycles on today's trading servers (Xeons from Skylake on), and that is the number to estimate with. It isn't fixed: on Intel chips before Skylake it is only about 10 cycles, so the same code on another machine can see a tenfold difference per `pause`. A budget counted in iterations, like "spin 1000 times, then sleep", can't be trusted; if you want a limit, count time. ARM has no `pause`: `yield` is a hint meant for multithreaded cores and is a no-op on many cores, so some libraries use `isb` to burn a short delay instead; to actually save power while waiting, use `wfe` to let the core sleep until someone writes the line. A portable version wraps it in a small function:

```cpp
#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
inline void cpu_relax() { _mm_pause(); }
#elif defined(__aarch64__)
inline void cpu_relax() { asm volatile("yield" ::: "memory"); }
#else
inline void cpu_relax() {}
#endif
```

Don't use `std::this_thread::yield()` instead. On Linux it is the `sched_yield` system call, about 0.1–0.5 µs each time, and when another thread is ready to run on the core, it gives the core away, which amounts to taking yourself off the CPU.

### 1.7 The Moment of Release: Every Waiter Rushes at Once

TTAS makes the hold quiet, but the release is still chaotic. Once the lock is freed, all 3 waiters read `false` and go back to the first line to `exchange` almost at once. Only the first one succeeds and the other 2 fail, yet every `exchange` pulls the line over, failed ones included. The more waiters, the longer this burst of RMWs; if the new owner holds the lock only briefly, its releasing store has to queue behind the burst. So each handover takes time roughly linear in the number of waiting cores $N$:

$$t_{\text{handover}} \approx N \times t_{\text{line}}, \qquad t_{\text{line}} \approx 20\text{–}100\ \text{ns}$$

With 4 cores waiting, one handover takes about 80–400 ns, longer than holding the lock once.

One remedy is to step back after losing:

```cpp
#include <algorithm>
#include <atomic>

class BackoffSpinLock {
public:
    void lock() {
        for (int backoff = 1;; backoff = std::min(backoff * 2, kMaxBackoff)) {
            if (!locked_.exchange(true, std::memory_order_acquire)) return;
            for (int i = 0; i < backoff; ++i) cpu_relax();  // lost: rest a little, then look again (cpu_relax: see 1.6)
            while (locked_.load(std::memory_order_relaxed)) cpu_relax();
        }
    }
    void unlock() { locked_.store(false, std::memory_order_release); }

private:
    static constexpr int kMaxBackoff = 64;
    alignas(64) std::atomic<bool> locked_{false};
};
```

Every loss doubles the next rest (exponential backoff), so the cores come back at different times and fewer of them rush together. Resting mostly adds no delay: losing means another core just took the lock and will hold it for a whole hold time, and if other cores are waiting too, your turn was several hold times away anyway. A rest no longer than that unavoidable wait doesn't make you later; it only removes one grab of the line. The more you lose, the more cores are competing and the longer the wait ahead, so the rest should grow, hence the doubling. Real implementations also add a little randomness to the rest, so that cores in lockstep don't collide again. Resting too long is what adds delay: the lock is freed while you are still resting, and it sits idle or goes to a core that arrived later. With only one or two cores competing there are few hold times to wait through anyway, so backoff saves few grabs and adds real delay; keep the cap small. The cap should be thought of in time too: 64 `pause`s take about 3 µs, and only about 0.2 µs on an older machine where `pause` is about 10 cycles. Backoff also makes the lock less fair: a core that has lost often rests longer and is even less likely to win next time, while a newcomer starts at one rest and reacts fastest. An unlucky core can keep losing, which is called starvation. The cap guarantees it comes back to try every so often, but not that it ever wins.

With many waiters, backoff only eases the problem. The real fix is a queue: hand the lock over in arrival order (the ticket lock, 2.1), and let each waiter spin on a line of its own so a release disturbs only the next in line (the MCS lock, 2.2). In a trading system, though, **a lock that several cores keep fighting over is itself a sign that the design should change**: have a single thread do the writing, and let the others hand it their changes through a queue ([#4](/posts/lock-free-queue-logger-micro-batching/), [#5](/posts/spmc-shared-memory-broadcast-ring/)). That helps more than any better lock.

## 2. Many Cores Waiting: Ticket Locks, MCS Locks, Reader-Writer Locks and Address-Monitor Waits

### 2.1 Ticket Lock: Take a Number

1.7 left two problems. When the lock is released, the waiting cores all charge at once, so a handoff takes longer the more cores are waiting; and who wins is pure luck, so an unlucky core can starve. Both come from the same place: the lock has only two states, free and taken, so on release every waiting core sees the same event, "it's free", and all they can do is grab at once. A ticket lock gives each waiting core a different thing to wait for:

```cpp
class TicketSpinLock {
public:
    void lock() {
        unsigned my = next_.fetch_add(1, std::memory_order_relaxed);  // take a number
        while (serving_.load(std::memory_order_acquire) != my) cpu_relax();  // wait to be called
    }
    void unlock() {
        // only the holder changes serving_, so read it, add 1 and write it back: no read-modify-write needed
        serving_.store(serving_.load(std::memory_order_relaxed) + 1, std::memory_order_release);
    }

private:
    alignas(64) std::atomic<unsigned> next_{0};     // ticket dispenser: +1 for each arriving thread
    alignas(64) std::atomic<unsigned> serving_{0};  // "now serving" display: every waiter reads it
};
```

It works like the number queue at a bank. An arriving thread first takes a number with `fetch_add` on `next_`: a read-modify-write that returns the value before the increment, so every thread gets a different number. Then it watches `serving_` until its own number comes up. Releasing the lock means adding 1 to `serving_` to call the next number. Only the holder ever changes `serving_`, so nobody competes for it: reading it, adding 1 and writing it back is enough, a plain `mov` on x86. `fetch_add` would also be correct, but that is a `lock`-prefixed read-modify-write and costs about 2–6 ns more. `next_` and `serving_` get a line each: if they shared one, every arriving thread's `fetch_add` would take that line exclusive and invalidate the copies of every core reading `serving_`, so even the time the lock is held would not be quiet.

On release, every waiting core still has to re-read `serving_`: the line was written, all their copies are invalidated, and each reads it again, so N cores mean N read misses. But after reading the new value, **only the core whose number matches leaves the loop**; the others keep reading and waiting, and nobody grabs. In 1.7, a TTAS release was followed by a burst of read-modify-writes, each taking the line exclusive, with the new owner's release queued behind them. Here only reads are left, and readers each get a shared copy without taking the line away. Numbers are handed out in arrival order, so the lock is strictly first come, first served, and nobody starves.

The remaining cost is in those N reads. The core whose number was called is one of them, and its read is not necessarily served first; in the worst case it waits for the other N−1 reads, so a handoff still grows with N, only now each step is a read instead of a read-modify-write. A waiting core knows how many are ahead of it (`my - serving_`), so it can rest in proportion: with 5 ahead, rest for about 5 hold times before looking again. This is proportional backoff, and it is more accurate than the exponential backoff of 1.7.

The ticket lock's weak spot is first come, first served itself: the thread whose number comes up has to take over immediately. If it has been taken off the CPU (not pinned, preempted), the lock sits free while everyone behind it waits for it to come back, for a scheduling period, milliseconds. TTAS doesn't queue: whoever is there can take a free lock, so it doesn't have this problem. A queue lock therefore tightens the condition from 1.2: **not only the holder but also the waiting threads have to keep running**.

### 2.2 MCS Lock: Each Core Waits on Its Own Line

On a ticket-lock release N cores re-read because they all watch the same line. For a release to disturb only the next waiter, each waiting core has to watch a different line: each brings its own node, the nodes form a linked list, each core watches a flag in its own node, and a release writes only the next node's flag. That is the MCS lock, named after its authors Mellor-Crummey and Scott:

```cpp
class McsSpinLock {
public:
    struct alignas(64) Node {  // one per waiting thread, each on its own cache line
        std::atomic<Node*> next{nullptr};
        std::atomic<bool> granted{false};  // set to true by the previous holder on handoff
    };

    void lock(Node* me) {
        me->next.store(nullptr, std::memory_order_relaxed);
        me->granted.store(false, std::memory_order_relaxed);
        Node* prev = tail_.exchange(me, std::memory_order_acq_rel);  // join the tail, get the old tail
        if (prev == nullptr) return;                                 // queue was empty: lock acquired
        prev->next.store(me, std::memory_order_release);             // link in behind the previous node
        while (!me->granted.load(std::memory_order_acquire)) cpu_relax();  // watch only my own node
    }

    void unlock(Node* me) {
        Node* next = me->next.load(std::memory_order_acquire);
        if (next == nullptr) {
            Node* expected = me;
            if (tail_.compare_exchange_strong(expected, nullptr, std::memory_order_release,
                                              std::memory_order_relaxed))
                return;  // really nobody behind: queue emptied
            // someone has joined the tail but not linked in yet: wait for the link
            while ((next = me->next.load(std::memory_order_acquire)) == nullptr) cpu_relax();
        }
        next->granted.store(true, std::memory_order_release);  // wake only the next one
    }

private:
    alignas(64) std::atomic<Node*> tail_{nullptr};
};
```

`lock()` first clears its node, then with one `tail_.exchange(me)` makes itself the tail and gets the old tail `prev` back. If `prev` is null, nobody holds the lock and it returns; otherwise it links itself into `prev->next` and from then on watches only its own `granted`.

`unlock()` has to check whether anyone is behind it. If `next` isn't null, it sets that node's `granted` to `true` and the handoff is done. A null `next` can mean two things: nobody is waiting, or someone has already done the `exchange` and joined the tail but hasn't yet run `prev->next.store(me)` to link in. Looking at `next` alone can't tell them apart, so it tries a CAS to change the tail from itself back to null. Success means the tail was still itself, so nobody is really behind it. Failure means the tail is now someone else, who is about to link in; it waits for the link and then hands over. Simply writing null into `tail_` would lose the thread that just joined: nobody would ever set its `granted`.

The payoff is at release. Each waiting core fetches the line only on its first read of its own `granted`, then keeps hitting its own L1, so these lines carry no traffic while the lock is held. A release writes the next node's line, which only the next core holds a copy of, so the invalidation goes to that one core, and one re-read gets it `true`. **A handoff is always one line transfer (about 20–100 ns), no matter how many cores are waiting**. Nor does this linked list miss everywhere the way linked lists usually do: walking a list means chasing pointers one by one, each load waiting for the previous one to return; MCS never walks the list. Each thread touches its own node and, once each, its predecessor's and its successor's, so the misses are only the few line transfers at handoff, a fixed number. Nodes need a line each (`alignas(64)`); if two cores' nodes shared a line, writing one node would invalidate the other core's copy too, and we would be back to everyone watching the same line.

The memory orders pair up, each for its own reason:

- `tail_.exchange` uses `acq_rel`. On the empty-queue path the thread gets the lock without going through `granted`, so only the acquire of this `exchange`, pairing with the release of the previous holder's CAS, lets it see the previous holder's writes from the critical section. The release half is there because the exchange hands the node out: a later thread will use this pointer to write the node's `next`, and the node's initialisation has to come before those writes.
- `prev->next.store` uses release, and `unlock()` reads `next` with acquire. After getting my pointer, the previous holder will write `true` into my `granted`, so my write clearing `granted` to `false` at the top of `lock()` must come first; otherwise my `false` could overwrite its `true`, and I would wait forever.
- The release write and acquire read of `granted` at handoff are the pairing from 1.3: the critical section's writes are handed to the next holder along with the lock.

The cost shows up in three places. The interface takes a node, and the node must live until `unlock()`, usually on the caller's stack with `lock` and `unlock` in the same scope. With nobody competing, `lock()` is one `exchange`, same as TTAS, but `unlock()` is a load plus a CAS, one read-modify-write more than TTAS's plain store. And like the ticket lock it is a queue lock: if the thread whose turn it is gets taken off the CPU, the whole queue stalls. The Linux kernel's spinlock (qspinlock) combines the best of both: with nobody competing it only changes a 4-byte word, the MCS nodes come in only when threads queue up, and every CPU has its nodes ready in advance, so callers don't pass one.

### 2.3 The Three Locks Side by Side

| | TTAS + backoff | Ticket lock | MCS lock |
|---|---|---|---|
| Cores disturbed by a release | N: all re-read, then a burst of read-modify-writes | N: all re-read, only 1 gets in | 1 |
| One handoff | about N × 20–100 ns | 1 round of invalidations + up to N reads | about 20–100 ns, independent of N |
| First come, first served | No, can starve | Yes | Yes |
| With nobody competing | Lock: 1 `exchange`; unlock: 1 plain store | Lock: 1 `fetch_add` + 1 load; unlock: 1 plain store | Lock: 1 `exchange`; unlock: 1 load + 1 CAS |
| A waiting thread is taken off the CPU | Other cores can still take the lock | The queue stalls when its turn comes | Same as the ticket lock |

For 2–4 pinned threads that occasionally compete, TTAS with backoff is enough: it is the cheapest with nobody competing and doesn't care who gets taken off the CPU. When many cores fight over the same lock for long stretches, MCS gives the steadiest handoff. The closing point of 1.7 still stands, though: on a trading system's hot path, several cores fighting over one lock is itself a sign the design should change, to a single thread that writes while the others hand it their changes through a queue.

### 2.4 Reader-Writer Locks: Readers Get In Together, but All Update One Counter

Data like a market data snapshot has many reading threads and a single writer that writes now and then. A mutex makes readers go in one at a time too, even though reads don't conflict with each other. A reader-writer lock (`std::shared_mutex`) has two ways in: readers call `lock_shared()`, and several can be inside at once; a writer calls `lock()`, waits until no reader is inside, and once in keeps everyone else out. The simplest version keeps the state in one integer:

```cpp
class RwSpinLock {  // state_: -1 = a writer holds it, 0 = free, n > 0 = n readers inside
public:
    void lock_shared() {
        for (;;) {
            int n = state_.load(std::memory_order_relaxed);
            if (n >= 0 && state_.compare_exchange_weak(n, n + 1, std::memory_order_acquire,
                                                       std::memory_order_relaxed))
                return;
            cpu_relax();
        }
    }
    void unlock_shared() { state_.fetch_sub(1, std::memory_order_release); }

    void lock() {
        for (;;) {
            int expected = 0;
            if (state_.load(std::memory_order_relaxed) == 0 &&
                state_.compare_exchange_weak(expected, -1, std::memory_order_acquire,
                                             std::memory_order_relaxed))
                return;
            cpu_relax();
        }
    }
    void unlock() { state_.store(0, std::memory_order_release); }

private:
    alignas(64) std::atomic<int> state_{0};
};
```

A reader coming in adds 1 with a CAS as long as the state isn't −1 (no writer inside) and subtracts 1 on the way out; a writer has to change the state from 0 to −1 and writes 0 back on the way out.

**It beats a mutex only when two conditions hold together: readers stay inside for a long time (microseconds, say walking a whole table), and reads far outnumber writes**. Then the readers' critical sections really do overlap.

**With short reads it is no faster than a mutex, because readers write too**. `lock_shared()` and `unlock_shared()` are both read-modify-writes on `state_`, and each takes the line exclusive. Four cores each reading one order book level spend about 20 ns in the critical section, but every read moves the line twice (about 2 × 20–100 ns). The line bounces between the four cores and the readers actually line up on it one after another, as serial as with a mutex, with more complex state and slower. The bouncing line from 1.4, "waiting cores fight over the lock's line", reaches even readers that already hold the lock.

With many writes it doesn't work either. The version above favours readers: as long as readers keep coming and going, the state never reaches 0, and the writer never gets in; it is the writer that starves. A writer-preferring version does the opposite: once a writer is waiting, new readers are kept out, so readers queue. glibc's `pthread_rwlock` (what `std::shared_mutex` uses on Linux) favours readers by default. With many writes, a reader-writer lock is just a mutex with more expensive bookkeeping.

For data that is read often, written rarely and read briefly, trading systems **make readers write nothing at all**: a version number (seqlock) or double buffering ([#14](/posts/prefetch-warmup-double-buffer/)). Readers only read a version number or an index and re-read on a mismatch, and the writer never waits for readers. The cost is a single writer and an occasional re-read.

### 2.5 Address-Monitor Waits: `umonitor` / `umwait`, `WFE`

So far there are two ways to wait. Spinning with `pause` keeps the core running, burns power, and with SMT still takes execution resources from the sibling thread. A futex sleep in the kernel frees the core, but it takes 2–10 µs from release to actually waking up. Address-monitor waiting sits in between: tell the hardware "watch this line and wake me when someone writes it", then put the core into a light sleep. The wake-up comes from cache coherence: before another core can write the line it has to send an invalidation to drop this core's copy, and when the invalidation arrives the hardware also wakes the core. No system call, and no spinning. On the [hardware map](/ref/cpu-memory/) this happens between the core and L1D.

On x86 these instructions are part of the WAITPKG extension, available on Intel from Tremont, Alder Lake and Sapphire Rapids on, so check CPUID before using them; AMD's counterpart is `monitorx` / `mwaitx`.

```cpp
#include <atomic>
#include <cstdint>
#include <immintrin.h>  // compile with -mwaitpkg; check CPUID for WAITPKG before running
#include <x86intrin.h>  // __rdtsc

inline void wait_until_set(std::atomic<uint32_t>& flag) {
    while (flag.load(std::memory_order_acquire) == 0) {
        _umonitor(&flag);                                      // 1. arm the monitor on this line
        if (flag.load(std::memory_order_acquire) != 0) break;  // 2. look once more after arming
        _umwait(1, __rdtsc() + 100000);  // 3. wait in C0.1: a write to the line, the deadline or an interrupt wakes it
    }
}

inline void signal(std::atomic<uint32_t>& flag) {
    flag.store(1, std::memory_order_release);  // a plain store is enough
}
```

`_umonitor(addr)` arms the monitor on the line containing `addr`. `_umwait(ctrl, deadline)` stops the core until the line is written, the TSC (time stamp counter) reaches `deadline`, an interrupt arrives, or the operating system's cap is hit (on Linux about 100,000 TSC cycles by default, tens of microseconds). `ctrl` picks how deep to sleep: 1 is C0.1, which wakes faster; 0 is C0.2, which saves more power and wakes a little slower. Both stay in C0, short of C1, C6 and the other states that stop the clock, so waking is much faster than a wake-up from the kernel and a bit slower than spinning with `pause`. Waking doesn't mean the condition holds (it may be the deadline or an interrupt), so the call sits in a loop that checks again.

The three steps can't be reordered: **arm, look again, then sleep**. If you look first and arm afterwards, someone may write 1 between "saw 0" and arming; that write happened before the monitor was armed, so it doesn't wake the core, and the core sleeps until `deadline`. Looking again after arming covers both cases: a write before arming is seen in step 2, and a write after arming wakes step 3. `deadline` is an absolute TSC value, not a duration, so write it as `__rdtsc() + how long`; 0 is a moment long past, so `umwait` returns immediately and the loop turns into plain spinning.

On ARM the counterpart is `WFE` (wait for event). First read the address with an exclusive load, `ldaxr`, and the hardware remembers the line (the exclusive monitor); then `WFE` sleeps. When another core writes the line the monitor is cleared, which itself counts as an event, and the core wakes up; the writer doesn't need to send `SEV`. This is how Linux waits for a variable to change on ARM64 (`smp_cond_load_acquire`). `WFE` can also wake for no reason, so it too checks again in a loop.

In a trading system, pinned threads on the hot path still spin with `pause`; they don't want to pay even tens of extra nanoseconds. `umwait` suits waits off the hot path that shouldn't go to sleep in the kernel, such as a logging thread waiting for its queue to fill: the core is freed, and with SMT the sibling gets the whole core. It also pairs well with queue locks: each waiting core in MCS already watches only its own line, so it can `umonitor` that line and `umwait`, and the previous holder's handoff write is exactly what wakes it. Many trading machines turn off the deep C-states in the BIOS, which doesn't affect C0.1 and C0.2; the operating system can also turn off C0.2 on its own (`IA32_UMWAIT_CONTROL`), and then `ctrl = 0` only reaches C0.1.

## In Practice {#in-practice}

The line-stealing read-modify-writes and TTAS of 1.3 to 1.5 match the {{% bottleneck-ref "tas-spinlock" "plain" %}} card below, and the cost of a thread sleeping and being woken in 1.1 is the mechanism behind the {{% bottleneck-ref "thundering-herd" "plain" %}} card. Both cards list what perf shows, how to fix it and how to verify the fix.

{{% bottleneck "tas-spinlock" %}}

{{% bottleneck "thundering-herd" %}}
