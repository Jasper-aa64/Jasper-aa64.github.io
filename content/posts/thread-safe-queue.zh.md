---
title: "交易系统笔记 #18：线程安全队列"
date: 2026-10-27
slug: "thread-safe-queue"
description: "无锁 SPSC 环靠的是每个下标只有一个写者。这个前提一被打破，就要换写法：消费者空了要睡，用一把锁加两个条件变量写阻塞队列，醒来要再查条件，条件不在锁里改就会丢失唤醒；几个生产者往一个环里写，rte_ring 先用 CAS 抢位置、再按顺序发布，一个生产者停住后面全停；Disruptor 用 fetch_add 抢号、每一格标圈数，生产者不互相等，消费者停在空洞前。最后是队列满了的三种做法：阻塞、丢弃、覆盖。"
summary: "从一把锁到多生产者：阻塞队列的条件变量和丢失唤醒，rte_ring 的两对下标和按顺序发布，Disruptor 的可用标记，以及队列满了该阻塞、丢弃还是覆盖。"
chapter: 3
categories: [Systems]
tags: [cpp, concurrency, condition-variable, lock-free, mpmc, disruptor, ring-buffer, hft, low-latency]
toc: true
math: true
---

策略线程把落盘请求交给存档线程，几个策略线程把订单交给同一个网关线程，行情线程把更新交给好几个策略：交易系统里的线程几乎都靠队列连起来。[#4](/zh/posts/lock-free-queue-logger-micro-batching/) 的 SPSC 环不用锁，靠的是每个下标只有一个写者，生产者只改写下标，消费者只改读下标。可上面三个场景里，有的要让没活干的线程睡下，有的有好几个生产者，这个前提都不成立了。下面从最朴素的一把锁开始，一路走到多生产者的无锁环，最后看队列满了该怎么办。

## 1. 带锁的阻塞队列

### 1.1 结构：一把锁、两个条件变量

先看第一个场景：存档线程大部分时间没活干，队列是空的。它要是转着等（[#16](/zh/posts/spinlock-implementation/)），就白白占住一个核；它要的是没东西就睡，有东西来了被叫醒。队列有容量上限时反过来也一样：满了，生产者睡，腾出位置时被叫醒。

```cpp
template <class T>
class BlockingQueue {
public:
    explicit BlockingQueue(std::size_t cap) : cap_(cap) {}

    bool push(T v) {                       // 满了就睡；关闭以后返回 false
        std::unique_lock lk(m_);
        not_full_.wait(lk, [&] { return q_.size() < cap_ || closed_; });
        if (closed_) return false;
        q_.push_back(std::move(v));
        lk.unlock();                       // 先放锁再叫醒，醒来的线程不用马上又等这把锁
        not_empty_.notify_one();
        return true;
    }

    std::optional<T> pop() {               // 空了就睡；关闭并且取空以后返回 nullopt
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
        not_empty_.notify_all();           // 睡着的全叫醒，让它们看到 closed_
        not_full_.notify_all();
    }

private:
    std::mutex m_;
    std::condition_variable not_empty_;    // 消费者在这里等“有数据”
    std::condition_variable not_full_;     // 生产者在这里等“有空位”
    std::deque<T> q_;
    const std::size_t cap_;
    bool closed_ = false;
};
```

一把互斥锁 `m_` 保护 `q_` 和 `closed_`，对它们的读写全在锁里。**条件变量（condition variable）**是让线程睡着等一个条件的工具：`wait` 把线程挂到它上面睡下，别的线程 `notify_one` 叫醒一个、`notify_all` 叫醒全部。

这里用两个条件变量，各管一种等待：消费者在 `not_empty_` 上等“有数据”，生产者在 `not_full_` 上等“有空位”。分成两个，是为了叫醒对的人。生产者放进一个元素，该叫醒的是一个消费者；如果大家都睡在同一个条件变量上，`notify_one` 可能叫醒另一个生产者，它醒来看到队列还是满的，又睡回去，真正该醒的消费者却没人叫。

`push` 和 `pop` 都是放了锁再 `notify`。在锁里 notify 也对，只是醒来的线程第一件事是重新拿锁，而锁还在通知方手里，它马上又得等一下。**放锁再通知只是少等一下，前提是条件已经在锁里改好了**，1.3 会讲为什么这个前提不能少。

### 1.2 条件变量：等的是条件，不是通知

`not_empty_.wait(lk, pred)` 等价于下面的循环：

```cpp
while (!pred())
    not_empty_.wait(lk);   // 放锁和睡下是一步；醒来时先重新拿锁，再返回
```

**醒来以后必须再查一遍条件**，原因有两个：

- **虚假唤醒（spurious wakeup）**：标准允许 `wait` 在没人 notify 的情况下返回，比如底层的 futex 等待被信号打断。醒来时队列可能还是空的。
- **被抢走**：生产者放进一个元素，`notify_one` 叫醒了睡着的消费者 A。A 要先重新拿锁才能返回，这中间一个刚到、没睡过的消费者 B 先拿到了锁，看到队列不空，把元素取走了。等 A 拿到锁，队列又空了。

如果写成 `if (q_.empty()) not_empty_.wait(lk);`，这两种情况下 A 醒来都会对空的 `deque` 调 `front()`，这是未定义行为。

条件变量本身不记任何状态：没人在等的时候 notify，这次通知就没了。“有没有数据”记在受锁保护的 `q_` 里，条件变量只传一句话：条件可能变了，回去再看看。

### 1.3 丢失唤醒：改条件和发通知之间要隔着这把锁

`wait` 能可靠地等，靠的是一个原子性：从查完条件到睡下，消费者一直拿着锁，“放锁”和“睡下”是同一步。生产者也必须拿着同一把锁去改条件，这个原子性才有用：生产者要么在消费者查之前改完（消费者查到了就不睡），要么在消费者睡下以后才拿到锁去改（之后的 notify 一定叫得醒它）。

生产者改条件时不拿这把锁，就会丢失唤醒（lost wakeup）。**最常见的出错写法是给无锁环加阻塞等待**：生产者只用原子变量发布序号、不拿锁，接着 notify；消费者在锁里查序号，不够就睡。下面这段就是这种错的写法：

```cpp
// 生产者（错：改 cursor 时没拿锁 m）
cursor.store(seq, std::memory_order_release);
cv.notify_all();

// 消费者
std::unique_lock lk(m);
cv.wait(lk, [&] { return cursor.load(std::memory_order_acquire) >= seq; });
```

<a href="/images/thread-safe-queue/lost-wakeup.zh.svg" target="_blank" rel="noopener"><img src="/images/thread-safe-queue/lost-wakeup.zh.svg" alt="丢失唤醒的时间线：上半张，消费者加锁、查条件不满足，还没睡下时，生产者写了 cursor 并 notify，这时没人在睡，通知落空；消费者接着睡下，再也没人叫醒它。下半张，生产者 notify 前先加锁，要等消费者睡下放锁才拿得到，所以 notify 在消费者睡下之后，消费者被叫醒、再查条件，满足。" loading="lazy" decoding="async"></a>

上半张图：消费者查完条件、还没睡下时，生产者改了 `cursor`，紧接着 notify。这时没人在睡，通知落空。消费者随后睡下，之后再没有通知，它就一直睡，尽管数据早就到了。修法是生产者在 notify 之前拿一下这把锁：

```cpp
cursor.store(seq, std::memory_order_release);
{ std::lock_guard lk(m); }   // 消费者要么还没查（查时能看到新 cursor），要么已经睡下
cv.notify_all();
```

下半张图：消费者从查条件到睡下一直拿着锁，生产者加锁只能等它睡下，所以 notify 一定落在它睡下之后。**条件只要不是在这把锁里改的，通知之前就要拿一下锁。**

### 1.4 关闭：让睡着的线程能出来

程序退出时要 `join` 消费者线程，可它们可能正睡在 `pop` 里，没人再放数据，就永远不会醒，`join` 跟着卡死。所以队列要能关闭：`close()` 在锁里把 `closed_` 设成 `true`，再把两个条件变量上睡着的线程全部叫醒；两个 `wait` 的条件里都带上 `closed_`，醒来的线程看到它就不再等。

关闭以后，`push` 返回 `false`。`pop` 先把剩下的元素取完，只有队列空了才返回 `nullopt`，**已经放进队列的东西不会因为关闭而丢掉**。这里要用 `notify_all`，因为每个睡着的线程都得醒来看到 `closed_`。

### 1.5 代价：不睡几十 ns，睡一次几 µs

- **没人抢、不用睡**：一次 `push` 是加锁、放锁两次原子读改写，加上 `deque` 的操作，约 20–50 ns。
- **有人抢**：锁所在的缓存行要在核之间搬，和 [#16](/zh/posts/spinlock-implementation/) 一样，每次多一次跨核搬行（约 20–100 ns），抢的核越多越慢。
- **要睡**：在 futex 上睡下、再被叫醒，从 notify 到对方真正跑起来约 2–10 µs（[速查 2.1](/zh/ref/cpu-memory/#latency)）。

所以**带锁的阻塞队列赢在省 CPU、容易写对，不在快**。它适合落盘、对账、管理命令这类等得起几 µs 的路径；行情到策略这种热路径用无锁环加忙等（[#4](/zh/posts/lock-free-queue-logger-micro-batching/)、[#5](/zh/posts/spmc-shared-memory-broadcast-ring/)），线程绑核，不睡。

## 2. 多生产者的无锁环：rte_ring 和 Disruptor

### 2.1 rte_ring：先抢位置，再按顺序发布

几个策略线程往同一个订单网关线程发单（多生产者单消费者，MPSC），写下标就有了多个写者，只能用 CAS 抢。抢到位置以后还要写数据，“抢到”和“写完”之间隔着一段时间，消费者不能去读一个抢到了、还没写完的槽。rte_ring（DPDK 的无锁环）的办法是每一边用两个下标：

- `prod_head_`：生产者抢到哪了，生产者之间用 CAS 抢它；
- `prod_tail_`：生产者写完、消费者能读到哪；
- 消费者一边对称：`cons_head_` 是消费者抢到哪了，`cons_tail_` 是消费者读完、生产者能覆盖到哪。

rte_ring 本身是多生产者多消费者（MPMC）的，下面的代码也是完整的 MPMC 版，消费者一边按多个写。**只有一个消费者时，`cons_head_` 和 `cons_tail_` 总是相等**，2.2 末尾会说怎么简化。

```cpp
template <class T, uint32_t N>             // N 是 2 的幂
class MpmcRing {
    static_assert((N & (N - 1)) == 0);
public:
    explicit MpmcRing(uint32_t start = 0)  // 起点可调，测试下标回绕用
        : prod_head_(start), prod_tail_(start), cons_head_(start), cons_tail_(start) {}

    bool try_push(const T& v) {
        uint32_t head = prod_head_.load(std::memory_order_relaxed);
        do {
            if (head - cons_tail_.load(std::memory_order_acquire) == N)
                return false;                                        // 满了
        } while (!prod_head_.compare_exchange_weak(head, head + 1,   // ① 抢一个位置
                                                   std::memory_order_relaxed));
        buf_[head & (N - 1)] = v;                                    // ② 写自己抢到的槽
        while (prod_tail_.load(std::memory_order_acquire) != head)   // ③ 等前面的生产者发布完
            _mm_pause();
        prod_tail_.store(head + 1, std::memory_order_release);       // ④ 按顺序发布
        return true;
    }

    bool try_pop(T& out) {
        uint32_t head = cons_head_.load(std::memory_order_relaxed);
        do {
            if (head == prod_tail_.load(std::memory_order_acquire))
                return false;                                        // 空的
        } while (!cons_head_.compare_exchange_weak(head, head + 1,
                                                   std::memory_order_relaxed));
        out = buf_[head & (N - 1)];
        while (cons_tail_.load(std::memory_order_acquire) != head)
            _mm_pause();
        cons_tail_.store(head + 1, std::memory_order_release);       // 这一格可以给生产者了
        return true;
    }

private:
    alignas(64) std::atomic<uint32_t> prod_head_{0};   // 生产者抢到哪了
    alignas(64) std::atomic<uint32_t> prod_tail_{0};   // 生产者写完、消费者能读到哪
    alignas(64) std::atomic<uint32_t> cons_head_{0};   // 消费者抢到哪了
    alignas(64) std::atomic<uint32_t> cons_tail_{0};   // 消费者读完、生产者能覆盖到哪
    alignas(64) T buf_[N];
};
```

`try_push` 分四步：

1. 读 `prod_head_`，用 `head - cons_tail_ == N` 查满，再用 CAS 把它从 `head` 改成 `head + 1`。CAS 失败说明被别的生产者抢先了，这时 `head` 已被改成最新值，回到循环开头重新查满。
2. 往抢到的槽里写数据。
3. 等 `prod_tail_` 走到 `head`，也就是等前面的生产者都发布完。
4. 把 `prod_tail_` 改成 `head + 1`（release），消费者从这一刻起能读到这一格。

下标是 `uint32_t`，只加不减，存的是没掩码的值，用的时候才 `& (N - 1)`。空是 `head == tail`，满是 `head - tail == N`。如果把掩码后的值存回去，下标只能在 0 到 N − 1 之间取值，空和满都表现为两个下标相等，就分不开了（[#4](/zh/posts/lock-free-queue-logger-micro-batching/) 1.1）。

下标加到 $2^{32} - 1$ 再加 1，会回到 0，判断照样对。无符号减法按 $2^{32}$ 取模，只要真实差值不超过 N，`head - tail` 算出来就是真实的差值。N 是 2 的幂，能整除 $2^{32}$，所以回绕前后的槽位也接得上：$2^{32} - 1$ 落在第 N − 1 格，下一个下标 0 落在第 0 格。**下标只加不减、N 是 2 的幂，回绕就不用特殊处理。**下面的测试让下标从 $2^{32} - 1001$ 起跑，跑的过程中回绕过 0，结果仍然对。

### 2.2 按顺序发布：一个数只能说“前面全好了”

第 ③ 步的等待是这个设计的关键。`prod_tail_` 只是一个数，消费者把它理解成“它以下的槽都写好了”。A 抢到 5、B 抢到 6，B 先写完，如果 B 直接把 `prod_tail_` 改成 7，消费者就会去读 5，可 A 还没写。所以 B 必须等 `prod_tail_` 先变成 6（A 发布完），自己再改成 7：**发布的顺序必须和抢位置的顺序一样。**

第 ③ 步的读要用 acquire。A 发布时用 release 写 `prod_tail_ = 6`，B 用 acquire 读到 6，A 往槽 5 写的数据就先于 B 的 release 写。消费者用 acquire 读到 7，槽 5 和槽 6 的数据就都看得到。

代价是：A 如果在 ① 和 ④ 之间被换下 CPU，B、C……全都卡在 ③ 转圈，一直转到 A 回来。这和 [#16](/zh/posts/spinlock-implementation/) 2.1 票据锁里“轮到号的线程被换下、整条队跟着停”是同一个问题。所以严格说它不是 lock-free：**一个停住的生产者能让其他所有生产者都停住。**DPDK 敢这么用，是因为它的线程都绑核独占，不会被换下；普通线程会被抢占，用这种环最坏要停几 ms。

消费者一侧完全对称：几个消费者用 CAS 抢 `cons_head_`，读完按顺序推进 `cons_tail_`，生产者看 `cons_tail_` 判断能不能覆盖。订单网关这种只有一个消费者的情况（MPSC），没人跟它抢，前面也没人要等，CAS 和第 ③ 步那样的等待都可以省掉：读完直接用 release 写 `cons_tail_`，两个下标合成一个就行。rte_ring 的单消费者模式就是这么做的。

### 2.3 Disruptor：每一格自己标“写好了”

Disruptor 是 LMAX（一家外汇交易所）为撮合引擎做的环形队列。它换了一种记法，让生产者之间不用互相等：

- **序号代替下标**：用 64 位有符号序号，只加不减，实际上永远用不完；槽的位置是 `seq & (N - 1)`。
- **抢号用 `fetch_add`**：每个生产者用 `fetch_add(1)` 一步拿到自己的号，不会失败，也不用重试。满了还得等，见 2.4。
- **每一格一个可用标记**：生产者写完自己的槽，就在这一格的标记里写下“第几圈”（`seq / N`），不管前面的号写没写完。

```cpp
template <class T, int64_t N>              // N 是 2 的幂
class MultiProducerRing {
    static_assert(N > 0 && (N & (N - 1)) == 0);
public:
    MultiProducerRing() {
        for (auto& a : avail_) a.store(-1, std::memory_order_relaxed);
    }

    // ---- 生产者，可以有多个 ----
    int64_t claim() {
        int64_t seq = claim_.fetch_add(1, std::memory_order_relaxed);  // 抢号：一步拿到，不重试
        while (seq - N > consumed_.load(std::memory_order_acquire))   // 满了：等消费者读完 seq - N
            _mm_pause();
        return seq;
    }
    T& slot(int64_t seq) { return buf_[seq & (N - 1)]; }
    void publish(int64_t seq) {                                       // 只标自己这一格，不等别人
        avail_[seq & (N - 1)].store(seq / N, std::memory_order_release);
    }

    // ---- 消费者，只有一个 ----
    bool try_consume(T& out) {
        const int64_t seq = next_;
        if (avail_[seq & (N - 1)].load(std::memory_order_acquire) != seq / N)
            return false;                                             // 这一格还没写好（这一圈的）
        out = buf_[seq & (N - 1)];
        consumed_.store(seq, std::memory_order_release);              // seq 读完了，可以覆盖
        next_ = seq + 1;
        return true;
    }

private:
    alignas(64) std::atomic<int64_t> claim_{0};       // 下一个要发的号
    alignas(64) std::atomic<int64_t> consumed_{-1};   // 消费者读完的最后一个号
    alignas(64) int64_t next_ = 0;                    // 消费者下一个要读的号
    std::array<std::atomic<int64_t>, N> avail_;       // 每一格最后一次写好时是第几圈
    alignas(64) T buf_[N];
};
```

生产者写一条是三步：`claim()` 拿号，往 `slot(seq)` 里写，`publish(seq)` 标记。消费者从 `next_` 往后读，每读一格先看它的标记是不是 `next_ / N`：是就读，不是就停在这里，下次再看。标记写圈数而不是写 `true`，是因为同一格每 N 个号就要用一次，上一圈留下的 `true` 和这一圈的分不出来，而圈数每圈都不一样。

和 rte_ring 对比：A 抢到 5、B 抢到 6，B 先写完，`publish(6)` 后直接返回。消费者读到 5，发现标记不对，停住。A 写完 `publish(5)`，消费者接着读 5、6。**按顺序交付就躲不开空洞，两种做法的区别只是谁等**：rte_ring 让后面的生产者转着等；Disruptor 让消费者停在空洞前，其他生产者照常往下写，直到环满。A 一直停住的话，两种做法都交付不了 5 以后的数据，Disruptor 只是不再把其他生产者的线程也卡住。

### 2.4 背压和等待策略：满了等最慢的消费者，空了怎么等

**满了。** 生产者拿到号 `seq`，要写的那一格上一次装的是 `seq - N`，必须等消费者读完 `seq - N` 才能覆盖，所以 `claim()` 里要等到 `consumed_ >= seq - N`。消费者慢，生产者就跟着慢，数据一条不丢，这叫**背压**（backpressure）。

有多个消费者时，Disruptor 让每个消费者都读全部事件（广播），各记各的序号；生产者等的是其中最慢的那个，Disruptor 里叫 gating sequence，取所有消费者序号的最小值。消费者之间还可以排依赖：C 只读 A 和 B 都处理完的序号，也就是两者的最小值。常见的菱形结构是：生产者 → 落盘、复制 → 业务处理。

**空了。** Disruptor 有四种等待策略，正好是 [#17](/zh/posts/wait-free-sticky-counter/) 1.9 的四种选择：

- BusySpin：用 `_mm_pause` 转着等；
- Yielding：先转 100 圈，再 `yield`；
- Sleeping：先转、再让、最后 `sleep_for`；
- Blocking：锁加条件变量。

Blocking 正是 1.3 的场景：序号是原子变量，不在锁里改，生产者通知之前要拿一下锁。拿一个生产者一直灌数据测吞吐，四种策略几乎一样（500 万条都是约 30 ms），因为消费者几乎不用等；**等待策略的差别在空闲以后第一条数据的延迟，吞吐测试测不出来。**

## 3. 队列满了怎么办：阻塞、丢弃、覆盖

有界队列满了，只有三种做法：

| 做法 | 生产者 | 数据 | 用在哪 |
|---|---|---|---|
| 阻塞（背压） | 等，被消费者拖慢 | 不丢 | 订单、成交回报、必须落盘的日志 |
| 失败返回、丢弃 | 不等，马上知道失败了 | 丢掉新来的这条 | 行情：丢了记数，盘口按快照重建 |
| 覆盖 | 不等，也不知道谁没读完 | 慢的读者丢掉旧的 | 一对多广播、只要最新状态（[#5](/zh/posts/spmc-shared-memory-broadcast-ring/) 的 SPMC 环） |

**选哪种，看丢一条数据的代价和拖慢生产者的代价哪个大。**订单一条都不能丢，但也不该让热线程无限期地等：常见的做法是 `try` 失败就把这一单拒掉，报给风控和策略，而不是悄悄阻塞，也不是悄悄丢掉。
