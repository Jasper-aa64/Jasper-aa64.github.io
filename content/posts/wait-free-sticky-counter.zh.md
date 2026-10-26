---
title: "交易系统笔记 #17：wait-free"
date: 2026-10-26
slug: "wait-free-sticky-counter"
description: "lock-free 只保证总有线程在前进，CAS 循环里某个线程可能一直重试；wait-free 保证每个线程的步数都有上界。用一个归零以后不许复活的引用计数（sticky counter）看它怎么做到：无条件 fetch_add / fetch_sub 再看旧值，高位标志记状态，读的一方帮忙把做了一半的归零做完，exchange 保证只有一个线程认领销毁；CAS 失败时不重试，而是把自己排在别人后面。代价是更多原子操作，买到的是上界，不是速度。"
summary: "wait-free 不是更快的 lock-free：它把 CAS 失败从“再来一次”变成“我排在你后面”，每个线程的步数因此有了上界，代价是更多原子操作和更难写对的代码。"
chapter: 1
categories: [Systems]
tags: [cpp, atomics, wait-free, lock-free, linearizability, reference-counting, hft, low-latency]
toc: true
---

`weak_ptr::lock()` 要在强引用还没归零时把计数加 1。几个核同时加减同一个计数，最常见的写法是 CAS 循环：平均很快，可某个线程运气差时要重试很多次，重试多少次没有上界。对 P99.9 敏感的路径上，这种“平均快、偶尔很慢”就是问题。wait-free 换了个思路：每个线程走的步数都有上界，别的线程再快、再慢、甚至停住，都拖不住它。下面用一个归零以后不许复活的计数器，看这件事怎么做到，代价又是什么。

## 1. wait-free：每个线程的步数都有上界

### 1.1 进度保证：锁、lock-free、wait-free 差在哪

[#16](/zh/posts/spinlock-implementation/) 的自旋锁有一个躲不开的问题：持锁的线程被换下 CPU，等锁的线程全部停住。它们能不能做完，取决于另一个线程什么时候回来。按“别的线程出了事（变慢、被换下、甚至死掉），我还能不能做完”，进度保证分四档：

- **阻塞式（blocking）**：别人停住，我可能永远做不完。所有的锁都是。
- **obstruction-free**：只有别人都停下时，我一个人能做完；大家一起动时可能谁都做不完。实际里很少提。
- **lock-free**：任何时候总有某个线程能在有限步内做完，整体一直在前进；但具体某个线程可能一直输。CAS 重试循环就是。
- **wait-free**：每个线程都在有限步内做完，不管别人快慢、停不停。

lock-free 和 wait-free 差的就是 #16 1.7 说的饿死：**lock-free 允许某个线程一直重试，wait-free 不允许**。

“有限步”不等于“有限时间”。wait-free 只保证我自己要走的步数有上界，不保证这几步不被操作系统打断、不缺页、不碰上缓存不命中。所以要让耗时可预测，还要绑核隔离（[#1](/zh/posts/cpu-affinity-core-isolation-numa/)）、`mlockall`、数据独占缓存行这些层一起上。

### 1.2 sticky counter：归零以后不许复活的计数器

一个“粘”在零上的计数器，三个操作：

- `increment_if_not_zero()`：还没归零就加 1，返回 `true`；已经归零就拒绝，返回 `false`。
- `decrement()`：减 1。恰好把它减到零的那一次返回 `true`，其余都返回 `false`。
- `read()`：读当前值。

它就是引用计数：`weak_ptr::lock()` 要做的正是“强引用还没归零才能加 1”，`decrement()` 返回 `true` 的那个线程负责销毁对象。所以整个设计要守住一条：**恰好一个 `decrement()` 返回 `true`**。多一个是重复销毁，少一个是泄漏。

### 1.3 lock-free 版：CAS 循环为什么没有上界

先看常见的 lock-free 写法：

```cpp
struct LockFreeStickyCounter {
    std::atomic<uint64_t> n{1};

    bool increment_if_not_zero() {
        uint64_t cur = n.load(std::memory_order_relaxed);
        while (cur != 0) {
            if (n.compare_exchange_weak(cur, cur + 1, std::memory_order_acq_rel,
                                        std::memory_order_relaxed))
                return true;  // 失败时 cur 被改成最新值，再判断一次
        }
        return false;
    }
    bool decrement() { return n.fetch_sub(1, std::memory_order_acq_rel) == 1; }
    uint64_t read() { return n.load(std::memory_order_acquire); }
};
```

`increment_if_not_zero()` 要“没归零才加”，判断和加必须是一个原子操作，所以用 #16 1.3 的 CAS 循环：读出当前值，不是 0 就试着把它从 `cur` 改成 `cur + 1`。CAS 失败，说明在“读”和“改”之间有别的线程改了 `n`；那个线程的操作成功了，所以整体在前进，这是 lock-free。可这个线程自己要重试，别的线程一直在改，它就可能一直失败，**重试次数没有上界**，所以不是 wait-free。

实际里争得不凶时，一次 CAS 就成功，这个版本很轻。要防的是尾部：很多核一起加减同一个计数时，个别线程会重试很多次，对 P99.9 敏感的地方，这就是风险。

### 1.4 wait-free 版：先做，再看旧值

去掉循环的办法是：不先判断再改，而是无条件地改，再看改之前是什么。要做到这一点，计数里得带着“已经归零了没有”这个状态，所以借两个高位当标志：

```cpp
struct WaitFreeStickyCounter {
    static constexpr uint64_t is_zero = 1ull << 63;  // 已经钉成零
    static constexpr uint64_t helped = 1ull << 62;   // 是读的一方帮忙钉的
    std::atomic<uint64_t> counter{1};                // 低 62 位是计数

    bool increment_if_not_zero() {
        // 先加，再看加之前有没有 is_zero：没有才算加上了
        return (counter.fetch_add(1, std::memory_order_acq_rel) & is_zero) == 0;
    }

    bool decrement() {
        if (counter.fetch_sub(1, std::memory_order_acq_rel) == 1) {  // ① 是我把它减到了 0
            uint64_t expect = 0;
            if (counter.compare_exchange_strong(expect, is_zero, std::memory_order_acq_rel))
                return true;                                           // ② 我自己钉成零
            if ((expect & helped) &&
                (counter.exchange(is_zero, std::memory_order_acq_rel) & helped))
                return true;                                           // ③ 读的一方替我钉了，我来认领
        }
        return false;  // 没减到 0，或者被别人加回去了
    }

    uint64_t read() {
        uint64_t val = counter.load(std::memory_order_acquire);
        if (val == 0 && counter.compare_exchange_strong(val, is_zero | helped,
                                                        std::memory_order_acq_rel))
            return 0;  // 读到窗口里的 0：不等，帮忙钉成零
        return (val & is_zero) ? 0 : (val & ~(is_zero | helped));
    }
};
```

`is_zero` 一旦被设上，这个计数就算永久归零。“没归零才加”于是变成：先 `fetch_add(1)`，再看返回的旧值里有没有 `is_zero`。没有，加上了；有，就当没加。已经归零时这次加并没有撤回，低位多了 1，但 `is_zero` 还在，`read()` 和以后的 `increment` 只认这一位，多出来的计数不影响任何结果。`fetch_add` 在 x86 上是一条 `lock xadd`，不会失败，也就没有循环。

`decrement()` 用 `fetch_sub` 减 1。旧值是 1，说明是我把它减到了 0，但这时内存里只是一个普通的 0，还没有 `is_zero`，要再用一次 CAS 把它从 0 改成 `is_zero`，才算钉死。每个操作最多一次 `fetch`、一次 CAS、一次 `exchange`，**步数有固定上界，没有任何循环**。

### 1.5 窗口：内存里的 0 还不算归零

`decrement()` 的 `fetch_sub` 把值减成 0，到 CAS 把它钉成 `is_zero`，中间隔着一段：内存里是 0，逻辑上还没归零。别的线程这时进来，会碰上三种情况，整个算法就是围着这段窗口设计的：

| 窗口里发生了什么 | 结果 |
|---|---|
| 没人打扰 | `decrement()` 自己的 CAS 把 0 改成 `is_zero`，返回 `true` |
| `increment` 进来，把 0 加回 1（旧值里没有 `is_zero`，所以算加上了） | `decrement()` 的 CAS 失败，读回来的值里也没有 `helped`，返回 `false`：当作这次减发生在那次加之后，没减到零 |
| `read` 进来，读到 0 | `read` 用 CAS 把 0 改成 `is_zero \| helped`，返回 0；`decrement()` 的 CAS 失败，但看到 `helped`，去认领 `true` |

第三种情况叫 helping（协作）。`read()` 读到 0，知道有个 `decrement()` 做了一半。它要是等那个线程把零钉好再返回，那个线程被换下 CPU，它就得一直等，又成了阻塞式。所以 **`read()` 不等，替它把剩下的一步做完**，自己立刻返回 0，再留下 `helped` 告诉那个线程“零是我替你钉的，`true` 还是你的”。

### 1.6 `exchange`：认领只发一张

`decrement()` 的第 ③ 步，看到 `helped` 还不能直接返回 `true`，因为窗口里可能不止一个 `decrement()`。例如：T1 把 1 减到 0；T2 的 `increment` 把它加回 1，T2 又马上 `decrement`，把它减回 0。这时 T1、T2 都认为“是我减到 0 的”。`read` 进来只会钉一次零、留一个 `helped`，T1 和 T2 的 CAS 都失败，读回来的值里都有 `helped`。看到就返回 `true` 的话，两个线程都去销毁对象。

`exchange(is_zero)` 是原子地“取走旧值、写入新值”：谁先执行，谁拿到的旧值里带 `helped`，返回 `true`；后执行的拿到的旧值已经被换成了 `is_zero`，不带 `helped`，返回 `false`。它像一张只发一次的票，**谁先取走谁认领**，保证恰好一个 `true`。

### 1.7 线性一致性：用排先后代替重试

线性一致性（linearizability）的意思是：每个操作看起来都在它调用和返回之间的某一个瞬间一次做完，所有操作的结果能排成一个先后顺序，和单线程依次执行得到的结果一样，而且先结束的操作排在后开始的操作前面。

lock-free 版遇到冲突就重试，直到自己的操作能干净地插进去。wait-free 版不重试，而是给冲突一个解释：`decrement()` 的 CAS 因为 `increment` 把 0 加回了 1 而失败，就把这次减排在那次加之后，那一刻计数是 2，减完是 1，没减到零，返回 `false` 自洽。**CAS 失败不再意味着“再来一次”，而是“我排在它后面”**，所以不需要循环。

这个解释有边界：`increment`、`decrement` 的返回值和“是不是零”都能这样排通，`read()` 返回的非零数值不一定能。最小的例子（初始计数 1）：

1. T1 `decrement`：`fetch_sub`，1 → 0。
2. T2 `increment`：`fetch_add`，0 → 1，旧值没有 `is_zero`，加上了。
3. T3 `read`：读到 1，返回 1。
4. T2 `decrement`：`fetch_sub`，1 → 0。
5. T1 的 CAS 把 0 改成 `is_zero`，返回 `true`。
6. T2 的 CAS 失败，值里没有 `helped`，返回 `false`。

T1 拿到了“最后一个”的 `true`，按先后它得排在 T2 的减之后；T2 的加在 `read` 之前就结束了，T2 的减在 `read` 之后才开始。所以 `read` 那一刻逻辑上的计数应该是 2，它返回的却是内存里的 1。**是不是零是可靠的，具体的非零数值只能当近似值**，和 `shared_ptr::use_count()` 在多线程下只是近似值一个道理。

### 1.8 代价和前提：有上界不等于更快

**wait-free 买到的是上界，不是速度。** 没人争时，lock-free 版加一次是一次 CAS，减一次是一次 `fetch_sub`；wait-free 版减到零时要多一次 CAS，可能再多一次 `exchange`，代码也难写对得多。所以只有读多写少、对 P99、P99.9 敏感、不能被别人拖住的底层场景，比如引用计数，才值得；写得密、不在乎尾部时，lock-free 或自旋锁可能更好。

**它也不管每一步多贵。** 8 个核一起高频 `fetch_add` 同一个计数，每一步都是对同一条行的读改写，行要在核之间搬（#16 1.4）。步数有上界，每一步的时间却随争用变长。wait-free 去掉的是重试，不是缓存行争用。

**“没有循环”还要靠硬件。** x86 上 `fetch_add`、`exchange`、`compare_exchange_strong` 各是一条带 `lock` 的指令，不会失败重试。ARM 在 ARMv8.1 的 LSE（大型系统扩展）之前没有这些单指令原子操作，编译器会把它们编成“独占读、独占写、失败就重来”的循环，这时严格说只是 lock-free。

内存序：上面的代码全写 `acq_rel`，是够用的保守写法。按引用计数的需要，减 1 至少要 release（我对对象的使用要先于别人销毁它），拿到 `true`、要去销毁的那一方要 acquire；加 1 只要原子就行，Boost 的文档和 libc++ 的 `shared_ptr` 加引用都用 `relaxed`。

### 1.9 等不到时怎么办：自旋、让出、睡，还是失败返回

一个操作做不下去（锁被拿着、队列满了），线程有四种选择，[#16](/zh/posts/spinlock-implementation/) 讲了前三种：

- **自旋**：原地转着等。线程绑在自己的核上、要等的时间比睡一次（2–10 µs）短时最快。
- **让出**（`sched_yield`）：把 CPU 让给同核的别的线程。绑核隔离的核上本来没有别的线程，等于空转再加一次系统调用，基本不用。
- **睡**（futex、条件变量）：要等得久、线程没绑核、或者要省 CPU 时用，代价是醒来要几 µs。
- **失败返回**：不等，告诉调用者“现在做不了”，由调用者决定丢掉、记一笔、换条路还是过会儿再试。

wait-free 的接口走的是第四条。[#4](/zh/posts/lock-free-queue-logger-micro-batching/) 的 SPSC 环就是例子：`try_claim()` 满了返回 `nullptr`，几次读写、没有循环，是 wait-free；`claim()` 满了就在循环里空转，等消费者腾出位置，消费者不动它就永远返回不了，是阻塞式。**环是不是 wait-free，看的是满了以后的接口，不是环本身。** 多个生产者用 CAS 抢槽位的环，抢输了要重试，是 lock-free。交易系统的热路径通常选失败返回：行情来不及处理就丢掉旧的、记一个计数，不让热路径被别人拖住。
