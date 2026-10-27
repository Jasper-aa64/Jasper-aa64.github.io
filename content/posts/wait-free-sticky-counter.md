---
title: "Trading System Notes #17: Wait-Free"
date: 2026-10-26
slug: "wait-free-sticky-counter"
description: "Lock-free only promises that some thread makes progress, so one thread in a CAS loop can keep retrying; wait-free promises every thread a bounded number of steps. A reference count that may never come back from zero (a sticky counter) shows how: an unconditional fetch_add / fetch_sub followed by a look at the old value, high bits as status flags, readers finishing a half-done drop to zero, and an exchange so that only one thread claims the destruction. A failed CAS is not retried; the thread orders itself after the other one. The price is more atomic operations, and what it buys is a bound, not speed."
summary: "Wait-free is not a faster lock-free: it turns a failed CAS from \"try again\" into \"I come after you\", which bounds every thread's steps, at the cost of more atomics and code that is harder to get right."
chapter: 1
categories: [Systems]
tags: [cpp, atomics, wait-free, lock-free, linearizability, reference-counting, hft, low-latency]
toc: true
---

`weak_ptr::lock()` has to add 1 to the count while the strong references haven't reached zero. When several cores increment and decrement the same count, the usual way is a CAS loop: fast on average, but an unlucky thread may retry many times, with no bound on how many. On a path that cares about P99.9, "fast on average, sometimes very slow" is the problem. Wait-free takes a different approach: every thread's number of steps is bounded, and no other thread, however fast, slow or stalled, can hold it back. Below, a counter that may never come back from zero shows how that is done and what it costs.

## 1. Wait-Free: Every Thread's Steps Are Bounded

### 1.1 Progress Guarantees: How Locks, Lock-Free and Wait-Free Differ

The spinlocks of [#16](/posts/spinlock-implementation/) have one problem they can't escape: if the lock holder is taken off the CPU, every waiting thread stops. Whether they finish depends on when another thread comes back. Sorted by "if other threads get into trouble (slow down, get descheduled, even die), can I still finish?", progress guarantees come in four levels:

- **Blocking**: if others stop, I may never finish. Every lock is like this.
- **Obstruction-free**: I can finish alone only when everyone else pauses; when everyone moves together, nobody may finish. Rarely mentioned in practice.
- **Lock-free**: at any time some thread finishes in a bounded number of steps, so the system as a whole keeps moving; but a particular thread may keep losing. A CAS retry loop is like this.
- **Wait-free**: every thread finishes in a bounded number of steps, however fast or slow the others are, and whether or not they stop.

What separates lock-free from wait-free is the starvation from #16 1.7: **lock-free allows one thread to keep retrying, wait-free does not**.

"Bounded steps" is not "bounded time". Wait-free only bounds the number of steps I take; it doesn't promise those steps won't be interrupted by the operating system, page-fault or miss in the cache. To make the time predictable you still need core pinning and isolation ([#1](/posts/cpu-affinity-core-isolation-numa/)), `mlockall`, and data on cache lines of its own, all together.

### 1.2 Sticky Counter: A Counter That Never Comes Back From Zero

A counter that "sticks" at zero, with three operations:

- `increment_if_not_zero()`: if it hasn't reached zero, add 1 and return `true`; if it has, refuse and return `false`.
- `decrement()`: subtract 1. The one call that takes it exactly to zero returns `true`; all others return `false`.
- `read()`: read the current value.

It is a reference count: `weak_ptr::lock()` does exactly "add 1 only if the strong count hasn't reached zero", and the thread whose `decrement()` returns `true` destroys the object. So the whole design has to hold one line: **exactly one `decrement()` returns `true`**. One more means a double destruction; one fewer means a leak.

### 1.3 The Lock-Free Version: Why a CAS Loop Has No Bound

First, the usual lock-free version:

```cpp
struct LockFreeStickyCounter {
    std::atomic<uint64_t> n{1};

    bool increment_if_not_zero() {
        uint64_t cur = n.load(std::memory_order_relaxed);
        while (cur != 0) {
            if (n.compare_exchange_weak(cur, cur + 1, std::memory_order_relaxed))
                return true;  // on failure cur is updated to the latest value; check again
        }
        return false;
    }
    bool decrement() {
        if (n.fetch_sub(1, std::memory_order_release) != 1) return false;
        std::atomic_thread_fence(std::memory_order_acquire);  // only the thread that destroys pays for acquire
        return true;
    }
    uint64_t read() { return n.load(std::memory_order_relaxed); }
};
```

`increment_if_not_zero()` must "add only if not zero", so the check and the add have to be one atomic operation, hence the CAS loop from #16 1.3: read the current value and, if it isn't 0, try to change it from `cur` to `cur + 1`. A failed CAS means another thread changed `n` between the read and the change; that thread's operation succeeded, so the system as a whole moved forward, which makes this lock-free. But this thread has to retry, and if others keep changing `n` it may keep failing. **The number of retries has no bound**, so it isn't wait-free.

In practice, with little contention, the first CAS succeeds and this version is light. What it has to guard against is the tail: when many cores increment and decrement the same count, an occasional thread retries many times, and on a path that cares about P99.9 that is the risk.

### 1.4 The Wait-Free Version: Act First, Then Look at the Old Value

The way to remove the loop is not to check and then change, but to change unconditionally and then look at what was there before. For that, the count has to carry "has it reached zero yet" as state, so two high bits are borrowed as flags:

```cpp
struct WaitFreeStickyCounter {
    static constexpr uint64_t is_zero = 1ull << 63;  // pinned at zero
    static constexpr uint64_t helped = 1ull << 62;   // pinned by a reader
    std::atomic<uint64_t> counter{1};                // the low 62 bits are the count

    bool increment_if_not_zero() {
        // add first, then check whether the old value had is_zero: only without it does the add count
        return (counter.fetch_add(1, std::memory_order_relaxed) & is_zero) == 0;
    }

    bool decrement() {
        if (counter.fetch_sub(1, std::memory_order_release) == 1) {  // ① I took it to 0
            uint64_t expect = 0;
            if (counter.compare_exchange_strong(expect, is_zero, std::memory_order_relaxed)) {
                std::atomic_thread_fence(std::memory_order_acquire);  // acquire only once the claim is mine
                return true;                                           // ② I pin it at zero myself
            }
            if ((expect & helped) &&
                (counter.exchange(is_zero, std::memory_order_relaxed) & helped)) {
                std::atomic_thread_fence(std::memory_order_acquire);  // acquire only once the claim is mine
                return true;                                           // ③ a reader pinned it for me; I claim it
            }
        }
        return false;  // didn't reach 0, or someone added it back
    }

    uint64_t read() {
        uint64_t val = counter.load(std::memory_order_relaxed);
        if (val == 0 && counter.compare_exchange_strong(val, is_zero | helped,
                                                        std::memory_order_relaxed))
            return 0;  // saw the 0 inside the window: don't wait, help pin it
        return (val & is_zero) ? 0 : (val & ~(is_zero | helped));
    }
};
```

Once `is_zero` is set, the count has reached zero for good. "Add only if not zero" then becomes: `fetch_add(1)` first, then check the returned old value for `is_zero`. Without it, the add counts; with it, treat the add as not having happened. When the count has already reached zero the add is not undone and the low bits grow by 1, but `is_zero` stays set, and `read()` and later increments look only at that bit, so the extra count doesn't affect any result. On x86 `fetch_add` is a single `lock xadd`, which can't fail, so there is no loop.

`decrement()` subtracts 1 with `fetch_sub`. An old value of 1 means I took it to 0, but memory then holds a plain 0 without `is_zero`, and another CAS is needed to change it from 0 to `is_zero` before it is pinned. Each operation does at most one `fetch`, one CAS and one `exchange`: **the number of steps has a fixed bound, with no loop at all**.

### 1.5 The Window: A 0 in Memory Is Not Yet Zero

Between `decrement()`'s `fetch_sub` taking the value to 0 and its CAS pinning it as `is_zero`, there is a stretch where memory holds 0 but the count hasn't logically reached zero. A thread arriving then meets one of three cases, and the whole algorithm is built around this window:

| What happens in the window | Result |
|---|---|
| Nobody interferes | `decrement()`'s own CAS changes 0 to `is_zero` and returns `true` |
| An `increment` comes in and adds the 0 back to 1 (the old value has no `is_zero`, so the add counts) | `decrement()`'s CAS fails, the value it reads back has no `helped`, and it returns `false`: this decrement is taken to come after that increment, so it didn't reach zero |
| A `read` comes in and sees 0 | `read` uses a CAS to change 0 to `is_zero \| helped` and returns 0; `decrement()`'s CAS fails, but it sees `helped` and goes to claim `true` |

The third case is called helping. `read()` sees 0 and knows some `decrement()` is half done. If it waited for that thread to pin the zero before returning, and that thread got taken off the CPU, it would wait indefinitely, which is blocking again. So **`read()` doesn't wait; it does the remaining step itself**, returns 0 at once, and leaves `helped` behind to tell that thread "I pinned the zero for you; the `true` is still yours".

### 1.6 `exchange`: Only One Claim Ticket

In step ③ of `decrement()`, seeing `helped` isn't enough to return `true`, because there may be more than one `decrement()` in the window. For example: T1 takes 1 to 0; T2's `increment` adds it back to 1, and T2 then immediately decrements it back to 0. Now T1 and T2 both believe "I took it to 0". A `read` that comes in pins the zero once and leaves a single `helped`; both T1's and T2's CAS fail, and both read back a value with `helped`. If seeing it were enough to return `true`, both threads would destroy the object.

`exchange(is_zero)` atomically "takes the old value and writes the new one": whoever runs it first gets an old value with `helped` and returns `true`; whoever runs it later gets an old value already replaced by `is_zero`, without `helped`, and returns `false`. It works like a ticket issued once: **whoever takes it first claims it**, which guarantees exactly one `true`.

### 1.7 Linearizability: Ordering Instead of Retrying

Linearizability means: every operation appears to happen all at once at some instant between its call and its return, the results of all operations can be put in one order that matches running them one by one on a single thread, and an operation that finished before another started comes first in that order.

The lock-free version retries on conflict until its operation slots in cleanly. The wait-free version doesn't retry; it explains the conflict instead. If `decrement()`'s CAS fails because an `increment` added the 0 back to 1, this decrement is ordered after that increment: at that moment the count was 2, the decrement left it at 1, it didn't reach zero, and returning `false` is consistent. **A failed CAS no longer means "try again" but "I come after it"**, so no loop is needed.

This explanation has limits: the return values of `increment` and `decrement` and "is it zero" can all be ordered this way, but a non-zero number returned by `read()` can't always. The smallest example (initial count 1):

1. T1 `decrement`: `fetch_sub`, 1 → 0.
2. T2 `increment`: `fetch_add`, 0 → 1; the old value has no `is_zero`, so the add counts.
3. T3 `read`: reads 1 and returns 1.
4. T2 `decrement`: `fetch_sub`, 1 → 0.
5. T1's CAS changes 0 to `is_zero` and returns `true`.
6. T2's CAS fails, the value has no `helped`, and it returns `false`.

T1 got the "last one" `true`, so in the order it must come after T2's decrement; T2's increment finished before the `read`, and T2's decrement started after it. So the logical count at the moment of the `read` should be 2, yet it returned the 1 in memory. **Whether it is zero is reliable; the exact non-zero value is only an approximation**, for the same reason `shared_ptr::use_count()` is only approximate with several threads.

### 1.8 Costs and Preconditions: A Bound Is Not Speed

**What wait-free buys is a bound, not speed.** With nobody competing, the lock-free version adds with one CAS and subtracts with one `fetch_sub`; the wait-free version needs one more CAS when it reaches zero, possibly an `exchange` on top, and the code is much harder to get right. So only low-level paths that are read-mostly, sensitive to P99 and P99.9, and must not be held back by other threads, such as reference counts, make it worthwhile; when writes are dense or the tail doesn't matter, lock-free or a spinlock may do better.

**Nor does it care how expensive each step is.** When 8 cores hammer `fetch_add` on the same count, every step is a read-modify-write on the same line, and the line moves between cores (#16 1.4). The number of steps is bounded, but the time per step grows with contention. Wait-free removes retries, not cache line contention.

**"No loop" also depends on the hardware.** On x86, `fetch_add`, `exchange` and `compare_exchange_strong` are each a single `lock`-prefixed instruction that can't fail and retry. ARM before the LSE (Large System Extensions) of ARMv8.1 has no single-instruction atomics of this kind, and the compiler turns them into "exclusive load, exclusive store, start over on failure" loops; strictly speaking that is only lock-free.

Memory order: whether the count itself is right (exactly one `true`) depends only on the atomicity of RMWs; RMWs on one word line up in a single order whatever their memory order. Memory order protects what lies outside the count, the object itself, and the code asks for ordering in only two places:

- The decrement uses release: my reads and writes of the object before I let go must be visible before this decrement is, or my write could land after the object has been destroyed.
- A successful claim (returning `true`) is followed by an acquire fence: destruction and `delete` cannot move ahead of it, and they see every holder's accesses from before it let go. The fence is only on the `true` path, so no other thread pays for it.

Everything else (the increment, pinning, `read()`) uses `relaxed`: none of them touch the object afterwards, so there is nothing to pass on. Boost and libc++'s `shared_ptr` also use `relaxed` to add a reference.

Two details. **The acquire goes after the read that decides the claim, not right after `fetch_sub`.** Inside the window the count can be added back, the object used, and the count taken to 0 again: in the 1.7 example T1 claims at step 5 and has to see what T2 wrote while holding the object, and what links T1 to T2's release decrement at step 4 is the value T1's CAS reads, not the 1 its `fetch_sub` read. The relaxed pinning CAS and `exchange` don't break that link either: after a release write, every RMW on the same variable, whatever its memory order, extends that write's release sequence. Every modification of this counter is an RMW, so a claimer that reads the final value synchronizes with every earlier release decrement.

On x86 none of this costs an instruction: a `lock`-prefixed RMW is already a full barrier and the acquire fence only constrains the compiler, so `acq_rel` everywhere and the weakest orders compile to the same machine code. The difference shows on ARM: `ldaddal` becomes `ldaddl`, and only the claimer adds a `dmb ishld`.

### 1.9 When You Can't Proceed: Spin, Yield, Sleep, or Return a Failure

When an operation can't proceed (the lock is taken, the queue is full), a thread has four choices; [#16](/posts/spinlock-implementation/) covered the first three:

- **Spin**: wait in place. Fastest when the thread is pinned to its own core and the wait is shorter than a sleep (2–10 µs).
- **Yield** (`sched_yield`): give the CPU to another thread on the same core. A pinned, isolated core has no other thread, so this is spinning plus a system call; it is hardly ever used.
- **Sleep** (futex, condition variable): for long waits, unpinned threads, or when CPU has to be saved; the cost is microseconds to wake up.
- **Return a failure**: don't wait; tell the caller "can't do it now" and let the caller decide whether to drop it, count it, take another path, or try again later.

A wait-free interface takes the fourth way. The SPSC ring in [#4](/posts/lock-free-queue-logger-micro-batching/) is an example: `try_claim()` returns `nullptr` when the ring is full, a few loads and stores with no loop, and is wait-free; `claim()` spins in a loop until the consumer makes room, never returning if the consumer doesn't move, and is blocking. **Whether a ring is wait-free depends on the interface for when it is full, not on the ring itself.** A ring where several producers grab slots with CAS has to retry when it loses, and is lock-free. A trading system's hot path usually chooses to return a failure: if market data arrives faster than it can be handled, drop the old data and count it, rather than let the hot path be held back by someone else.
