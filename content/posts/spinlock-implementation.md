---
title: "Trading System Notes #16: Spinlocks"
date: 2026-10-21
slug: "spinlock-implementation"
description: "When a critical section takes tens of nanoseconds, std::mutex goes to sleep in the kernel (futex) as soon as the lock is taken, and a sleep plus a wake-up costs microseconds. A spinlock never sleeps, but it only pays while the lock holder keeps running. The simplest CAS loop takes the lock's cache line exclusively on every attempt, so waiters fight over the line and even the holder has to queue to release it; test-and-test-and-set lets each waiter read its own copy; PAUSE in the loop avoids a pipeline flush the moment the lock is freed; and exponential backoff spreads out the rush when it is released."
summary: "Whether a spinlock is fast depends on what its waiters do: if every attempt is a read-modify-write, they drag the lock's line back and forth. Read before you grab, put PAUSE in the loop, back off after losing, and waiting costs the holder almost nothing."
chapter: 1
categories: [Systems]
tags: [cpp, spinlock, atomics, futex, mesi, pause, hft, low-latency]
toc: true
math: true
---

Code such as updating one level of an order book or copying a market data snapshot has to be guarded by a lock; it is called a critical section (the stretch between `lock()` and `unlock()`), and one run of it takes tens of nanoseconds. Guard it with `std::mutex`, and a thread that finds the lock taken gets suspended and woken again once the lock is free. That sleep and wake-up costs microseconds, a hundred times the critical section itself. A spinlock simply doesn't sleep: a thread that can't get the lock stays where it is and keeps looking, and takes over the moment the lock is released.

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

That round trip costs two system calls (about 0.1–0.5 µs each) plus two thread switches, out and back in, for the waiter (about 1–5 µs each, plus the cost of caches another thread has flushed). If the waiter's core had dropped into a power-saving state, waking it takes longer still ([#1](/posts/cpu-affinity-core-isolation-numa/), section 2.2). Altogether, from the unlock until the waiter actually runs again takes about 2–10 µs. One run of the critical section takes tens of nanoseconds, so one sleep pays for a hundred runs of it, and that is why spinlocks exist.

### 1.2 When Spinning Pays: The Holder Must Keep Running

Spinning beats sleeping because the lock will be released soon. That takes two conditions: the holder keeps running, and the critical section is short. If either fails, spinning just burns CPU.

The first one fails through scheduling. If the holder is taken off the CPU (its time slice ran out, another thread preempted it, it is waiting for I/O), the lock stops with it, and the waiting cores spin for nothing, for a whole time slice: milliseconds, far more than one sleep. It gets worse when a waiter and the holder share a core: the waiter occupies the core spinning, the holder can't get scheduled, and the lock can't be released until the time slice ends. That is why user-space spinlocks always come with pinning: every thread that touches the lock gets its own isolated core ([#1](/posts/cpu-affinity-core-isolation-numa/), section 1.2), so the OS has no reason to take the holder off its core.

The second one fails when the critical section does something slow. Logging, `malloc`, system calls, database queries, waiting on the network: these start at microseconds or may block outright, so the hold time grows and becomes unpredictable, and the waiting cores spin along with it. Keep only the few lines that change data inside the lock: do the lookups and computation outside it, and only write the result inside.

If you can't guarantee both, use the sleeping `std::mutex`, or a compromise: spin for a little while, then sleep if the lock still isn't free. glibc's adaptive mutex (`PTHREAD_MUTEX_ADAPTIVE_NP`) does exactly that, though `std::mutex` doesn't use that type by default.

### 1.3 The Simplest Spinlock: One Atomic and a CAS Loop

Not sleeping means replacing the "sleep in the kernel" step of `SleepingMutex` with "try again":

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

`compare_exchange_weak(expected, 1, …)` means: if `locked_` equals `expected` (0), set it to 1 and return true; otherwise write the current value of `locked_` into `expected` and return false. So after a failure `expected` holds 1 and has to be reset to 0 before the next round. `weak` may occasionally report failure even when the values are equal, which happens on ARM when it is built from a pair of exclusive load and store instructions. There is a loop around it anyway, so `weak` is enough; `strong` is for a single check that gives up on failure.

The memory orders keep the critical section's reads and writes from leaking out of the lock ([#2](/posts/memory-ordering-false-sharing-dependency-chains/), section 1.5). The successful CAS in `lock()` uses acquire: reads and writes in the critical section can't move before taking the lock, so they see what the previous holder wrote. The store in `unlock()` uses release: reads and writes in the critical section can't move after the release. Paired up, they guarantee that whatever the previous holder wrote inside the critical section is visible to the next holder. The failed CASes acquire nothing, so relaxed is enough for them. Taking the lock needs no release, since release orders what comes before the lock, which has nothing to do with the critical section.

`exchange` makes it shorter: `while (locked_.exchange(1, std::memory_order_acquire)) {}` writes 1 and returns the old value, and an old value of 0 means you took the lock. That is test-and-set (TAS). Either way, every attempt is a read-modify-write (RMW), and both versions share the same flaw.

### 1.4 RMWs Steal the Line: Every Attempt Takes It Exclusive

`locked_` lives in a cache line. On the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a>, that line can have a copy in the L1D of several cores, under the rule in the MESI box on the right: whoever wants to write must first invalidate everyone else's copy ([the MESI post](/posts/low-latency-mesi-cache-coherence/)).

An RMW is a write. On x86 the CAS compiles to `lock cmpxchg`, which brings the line into this core in exclusive state (MESI's M or E) whether or not the comparison succeeds, writing the old value back when it fails. On ARM it becomes an instruction like `casal`, again an RMW on that one line. So with 3 cores waiting, each of them steals the line from another core on every spin, at about 20–100 ns per steal ([Reference 2.6](/ref/cpu-memory/#cross-core)). The line travels between the waiting cores nonstop.

Moving the line is only waste in itself; the real damage is that it gets in the holder's way. To release the lock, the holder has to write `locked_`, so it too must get the line back, queued behind the waiters' RMWs: the lock should have been released long ago, but the releasing store still hasn't landed. If the protected data shares the line with `locked_`, every write to the data inside the critical section has to steal the line too, and the critical section itself gets longer. The second problem is easy to fix by giving the lock its own line (`alignas(64)`, [#6](/posts/alignment-layout-cache-dram-geometry/)); the first one needs a different way of waiting.

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

The change is the second line of the loop: once a grab fails, the waiter only does plain reads. Reads don't need exclusive ownership, so the 3 waiters each hold a shared copy (MESI's S), and every read hits in their own L1D at about 1 ns, without a single message leaving the core. The holder isn't disturbed, and nobody steals the line during the critical section.

When the lock is released, the holder writes `locked_` and sends one round of invalidations that kills the 3 copies. Each waiter's next read misses, pulls the line back, sees `false`, and only then goes back to the first line to `exchange`. The RMW happens only when the lock looks free; with nobody competing, the first line succeeds at once, as fast as `CasSpinLock`.

Relaxed is enough for the read in the loop. It only decides that grabbing is worth a try; the lock is actually taken by the acquire `exchange`.

### 1.6 PAUSE: Don't Fill the Pipeline With Loads of the Lock Word

The loop `while (locked_.load(...))` is only two or three instructions: load, compare, jump back. An out-of-order core doesn't wait for one round to finish before starting the next. It follows the branch predictor ([#7](/posts/branch-prediction-branch-optimization/)), guessing "spin again" over and over, and issues the loads of dozens of later rounds in advance. The ROB ends up holding a long row of loads of `locked_`, none of them retired yet (retiring means confirming results in program order).

The moment the lock is freed, that row of loads becomes a problem. x86 forbids reordering loads with other loads: a later load in program order may not see an older value than an earlier one. But these loads were issued early, and many of them already read the old value `true`. When the holder's invalidation arrives, the core can no longer guarantee they obey that rule, so it throws away everything from that point on and re-executes it. This is a memory ordering machine clear. Like a branch mispredict, it flushes the whole pipeline, also tens of cycles, and it lands exactly when the lock has just been freed and speed matters most. The loop exit is itself a branch mispredict, so you pay twice. On the hardware map this spans two boxes: the invalidation follows the grey dashed line into the invalidate queue and runs into the row of unretired loads in the ROB.

The `pause` instruction exists for exactly this kind of loop. It delays the start of the next round, so only one or two loads are in flight at a time; when the lock is freed there is no long row to throw away, and the flush is avoided. It has two more benefits: spinning more slowly lowers the core's power draw, and if the core runs two hardware threads (SMT), the sibling gets the execution resources ([#1](/posts/cpu-affinity-core-isolation-numa/), section 2.1).

How long one `pause` stalls varies a lot between generations, about 10–150 cycles: since Skylake, Intel stretched it from about 10 cycles to about 140. So a budget counted in iterations, like "spin 1000 times, then sleep", can differ tenfold in time on another CPU; if you want a limit, count time. ARM has no `pause`: `yield` is a hint meant for multithreaded cores and is a no-op on many cores, so some libraries use `isb` to burn a short delay instead; to actually save power while waiting, use `wfe` to let the core sleep until someone writes the line. A portable version wraps it in a small function:

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

TTAS makes the hold quiet, but the release is still chaotic. Once the lock is freed, all 3 waiters read `false` and go back to the first line to `exchange` almost at once. Only the first one succeeds and the other 2 fail, yet every `exchange` pulls the line over, failed ones included. The more waiters, the longer this burst of RMWs; if the new owner's critical section is short, its releasing store has to queue behind the burst. So each handover takes time roughly linear in the number of waiting cores $N$:

$$t_{\text{handover}} \approx N \times t_{\text{line}}, \qquad t_{\text{line}} \approx 20\text{–}100\ \text{ns}$$

With 4 cores waiting, one handover takes about 80–400 ns, longer than the critical section itself.

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

Every loss doubles the next rest (exponential backoff), so the cores come back at different times and fewer of them rush together. Real implementations also add a little randomness to the rest, so that cores in lockstep don't collide again. The price is that when the lock is freed, everyone may be resting, and the lock sits idle with nobody taking it. The cap should be thought of in time too: 64 `pause`s take about 0.2 µs on a machine where `pause` is about 10 cycles and about 3 µs where it is about 140, more than ten times apart.

With many waiters, backoff only eases the problem. The real fix is to let each waiter spin on a line of its own and hand the lock over in arrival order, so a release disturbs only the next in line; that is what queue locks (ticket locks, MCS locks) do. In a trading system, though, a lock that several cores keep fighting over is itself a sign that the design should change: have a single thread do the writing, and let the others hand it their changes through a queue ([#4](/posts/lock-free-queue-logger-micro-batching/), [#5](/posts/spmc-shared-memory-broadcast-ring/)). That helps more than any better lock.

## In Practice {#in-practice}

The line-stealing read-modify-writes and TTAS of 1.3 to 1.5 match the {{% bottleneck-ref "tas-spinlock" "plain" %}} card below, and the cost of a thread sleeping and being woken in 1.1 is the mechanism behind the {{% bottleneck-ref "thundering-herd" "plain" %}} card. Both cards list what perf shows, how to fix it and how to verify the fix.

{{% bottleneck "tas-spinlock" %}}

{{% bottleneck "thundering-herd" %}}
