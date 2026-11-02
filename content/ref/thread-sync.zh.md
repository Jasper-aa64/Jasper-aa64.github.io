---
title: "线程同步：互斥锁、条件变量、信号量、读写锁和死锁"
date: 2026-11-02
slug: "thread-sync"
description: "两个线程同时 ++ 同一个变量会丢更新，因为一次 ++ 是读、加、写三步。互斥锁让临界区同一时刻只进一个线程，没人抢时只是一两次原子操作，抢不到才进内核睡；条件变量让线程睡到某个条件成立，靠同一把锁避免丢掉唤醒；信号量是计数器加等待队列；读写锁让读者并行；死锁要四个条件同时成立，最常用的解法是固定加锁顺序或一次拿齐。只有一个变量时用原子操作，能不共享就用 thread_local。最后一张 pthread 对照表。"
summary: "共享数据要么同一时刻只让一个线程碰（互斥锁），要么让等的线程睡到条件成立（条件变量、信号量）；条件检查和睡下必须在同一把锁里完成，否则唤醒会丢。死锁的根源是环形等待，固定顺序或一次拿齐就拆掉了环。"
toc: true
group: cpplinux
weight: 112
---

多个线程共享同一个进程的地址空间（见[进程和线程](/zh/ref/process-thread-fork/)），一个线程写的全局变量，别的线程马上就能读到。共享方便，问题也出在这里：两个线程同时改同一块数据，结果取决于它们的指令怎么交错。这页从一个会丢数的 `++` 讲起，依次是互斥锁、条件变量、信号量、读写锁、死锁，最后是不加锁的两种办法：原子操作和 `thread_local`。

## 1. 数据竞争：两个线程同时改一个变量

### 1.1 `++counter` 为什么会丢 {#lost-update}

两个线程各把同一个 `counter` 加 1000 万次：

```cpp
long long counter = 0;                  // 两个线程共享
std::atomic<bool> go{false};

void add_racy(int n) { while (!go) {} for (int i = 0; i < n; ++i) ++counter; }

int main() {
    std::thread t1(add_racy, 10'000'000), t2(add_racy, 10'000'000);
    go = true;                          // 两个线程同时开跑
    t1.join(); t2.join();
    std::printf("%lld\n", counter);     // 应该是 20000000
}
```

本机（GCC 16.2，`-O0`，12 核）连跑 3 次，结果是 11369591、13080238、13657447，每次都少了三四成，每次还不一样。原因在 `++counter` 编出来的指令：

```asm
movq    counter(%rip), %rax     # 1. 从内存读到寄存器
addq    $1, %rax                # 2. 寄存器里加 1
movq    %rax, counter(%rip)     # 3. 写回内存
```

一次 `++` 是读、加、写三步，两个线程的这三步可以交错。A 读到 5，B 也读到 5，各自加成 6 写回，两次 `++` 只留下一次。**这种多个线程同时访问同一块内存、其中至少一个在写、又没有同步的情况叫数据竞争（data race）**，C++ 标准规定它是未定义行为，丢数只是最温和的后果。

<svg viewBox="0 0 760 316" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="两个线程交错执行 ++counter：A 读到 5，B 也读到 5，各自加成 6，A 写回 6，B 也写回 6，两次加一只留下一次" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ts0bg  { fill: #fbfaf7; }
    .ts0a   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .ts0b   { fill: #ddebf7; stroke: #6f93b8; stroke-width: 1.3; }
    .ts0m   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .ts0bad { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .ts0ink { fill: #1c1b18; font-size: 12.5px; }
    .ts0mut { fill: #6b6558; font-size: 12px; }
    .ts0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .ts0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .ts0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0a { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0b { fill: #1f3247; stroke: #5f8db8; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0m { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0bad { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0ink, :root:is([data-theme="dark"], [data-theme="black"]) .ts0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts0hd { fill: #a19caf; }
  </style>
  <defs><marker id="ts0arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ts0hd"/></marker></defs>
  <rect class="ts0bg" x="0" y="0" width="760" height="316" rx="10"/>
  <text class="ts0mut" x="14" y="34">时间</text>
  <path class="ts0ln" d="M26,44 L26,286" marker-end="url(#ts0arr)"/>
  <text class="ts0ttl" x="155" y="34" text-anchor="middle">线程 A</text>
  <text class="ts0ttl" x="405" y="34" text-anchor="middle">线程 B</text>
  <text class="ts0ttl" x="640" y="34" text-anchor="middle">内存里的 counter</text>
  <rect class="ts0a" x="40" y="48" width="230" height="30" rx="5"/>
  <text class="ts0ink" x="54" y="68">读 counter → 寄存器 = 5</text>
  <rect class="ts0m" x="560" y="48" width="160" height="30" rx="5"/>
  <text class="ts0ink" x="640" y="68" text-anchor="middle">5</text>
  <rect class="ts0b" x="290" y="88" width="230" height="30" rx="5"/>
  <text class="ts0ink" x="304" y="108">读 counter → 寄存器 = 5</text>
  <rect class="ts0m" x="560" y="88" width="160" height="30" rx="5"/>
  <text class="ts0ink" x="640" y="108" text-anchor="middle">5</text>
  <rect class="ts0a" x="40" y="128" width="230" height="30" rx="5"/>
  <text class="ts0ink" x="54" y="148">寄存器 + 1 = 6</text>
  <rect class="ts0m" x="560" y="128" width="160" height="30" rx="5"/>
  <text class="ts0ink" x="640" y="148" text-anchor="middle">5</text>
  <rect class="ts0b" x="290" y="168" width="230" height="30" rx="5"/>
  <text class="ts0ink" x="304" y="188">寄存器 + 1 = 6</text>
  <rect class="ts0m" x="560" y="168" width="160" height="30" rx="5"/>
  <text class="ts0ink" x="640" y="188" text-anchor="middle">5</text>
  <rect class="ts0a" x="40" y="208" width="230" height="30" rx="5"/>
  <text class="ts0ink" x="54" y="228">写回 counter = 6</text>
  <rect class="ts0m" x="560" y="208" width="160" height="30" rx="5"/>
  <text class="ts0ink" x="640" y="228" text-anchor="middle">6</text>
  <rect class="ts0b" x="290" y="248" width="230" height="30" rx="5"/>
  <text class="ts0ink" x="304" y="268">写回 counter = 6</text>
  <rect class="ts0bad" x="560" y="248" width="160" height="30" rx="5"/>
  <text class="ts0ink" x="640" y="268" text-anchor="middle">6，不是 7</text>
  <text class="ts0mut" x="40" y="304">两个线程各加了一次，counter 只从 5 变成 6：B 写回的 6 盖掉了 A 的结果。</text>
</svg>

开 `-O2` 时编译器会把整个循环合并成一次 `counter += n`，三条指令只执行一次，交错的窗口小到很难撞上，但这只是碰巧没出事：数据竞争照样存在，换个写法、换台机器就可能冒出来。

### 1.2 临界区：同一时刻只让一个线程进 {#critical-section}

访问共享数据的那段代码叫临界区。要让读、加、写三步不被打断，就得保证同一时刻只有一个线程在临界区里，别的线程到门口先等着。**同步做的就是这件事：不是让代码变快，而是让交错的结果和某种一个接一个执行的顺序一样。** 下面几种工具都是这个目的，差别在等的方式和放进去几个线程。

## 2. 互斥锁：同一时刻只放一个线程进去

### 2.1 加锁、解锁做了什么 {#mutex-inside}

互斥锁（mutex）本质上是内存里的一个状态值：没锁、锁了、锁了且有人在等。加锁是用一条原子指令（比如 x86 上的 `lock cmpxchg`）把“没锁”改成“锁了”。改成功的线程进临界区；改失败说明别人拿着，这时线程不会一直空转，而是通过 `futex` 系统调用进内核，挂到这把锁的等待队列上睡下。解锁把状态改回去，如果看到有人在等，再进一次内核叫醒一个。

所以一把锁的开销分两种情况。**没人抢时，加锁、解锁各是一次原子操作，全程不进内核，合起来十几到几十 ns；抢不到时要睡下、再被叫醒，涉及系统调用和线程切换，要几 µs。** 锁慢不慢，主要看抢得多不多，临界区越短、拿锁的线程越少，就越接近前一种情况。

锁有主人：谁加的锁，谁来解。普通的 `std::mutex` 也不能被同一个线程加两次，第二次加锁会等第一次释放，而第一次是它自己，于是永远等下去。确实需要在持锁时再调用一个也要拿这把锁的函数，可以用 `std::recursive_mutex`，它记着主人和次数，不过更常见的做法是把代码拆成“已经持锁”和“自己拿锁”两个版本。

### 2.2 lock_guard、unique_lock、scoped_lock：让解锁不会忘 {#raii-locks}

直接调 `m.lock()`、`m.unlock()`，中间只要有一个 `return` 或抛了异常，`unlock` 就被跳过，这把锁从此没人能拿。C++ 用对象的析构来解锁：构造时加锁，离开作用域时析构函数解锁，不管是怎么离开的。

```cpp
std::mutex m;
void add_locked(int n) {
    for (int i = 0; i < n; ++i) {
        std::lock_guard<std::mutex> g(m);   // 构造时加锁
        ++counter;
    }                                        // 每一轮结束 g 析构，解锁
}
```

同样两个线程各加 1000 万次，结果正好是 20000000。三种包装各管一类场景：

| 包装 | 能做什么 | 用在哪 |
|---|---|---|
| `std::lock_guard` | 只能在构造时加锁、析构时解锁 | 最常见的一段临界区 |
| `std::unique_lock` | 可以中途 `unlock()`、再 `lock()`，可以延迟加锁，可以移动 | 配合条件变量（3.2 节），或者要提前放锁 |
| `std::scoped_lock`（C++17） | 一次锁好几把，内部避免死锁 | 同时要两把以上的锁（6.2 节） |

### 2.3 锁的粒度：临界区里只放必须的 {#granularity}

锁住的代码越多，别的线程等得越久。上面的例子每次 `++` 都加锁一次，锁本身的开销比 `++` 大得多；把锁提到循环外面，整个循环只锁一次，可两个线程就完全串行了。哪种好取决于临界区外还有没有别的活能并行。**通用的原则是临界区里只放读写共享数据的那几行：** 读文件、发网络请求、打日志这些可能很慢的事，先在锁外做好，或者先把要用的数据拷出来再放锁。持锁调用别人传进来的回调尤其危险，你不知道它会不会去拿另一把锁（6.3 节）。

## 3. 条件变量：睡到某个条件成立

### 3.1 为什么要条件变量 {#why-condvar}

消费者要从队列里取数据，队列空了怎么办？在循环里反复加锁看一眼，CPU 白白空转；每看一次 `sleep` 1 ms，数据来了也要等到醒才处理，还白白醒了很多次。需要的是“睡下，直到有人告诉我队列里有东西了”，这就是条件变量（condition variable）：它本身不存任何条件，只是一个等待队列，`wait` 让线程睡在上面，`notify_one` / `notify_all` 叫醒其中一个或全部。

### 3.2 wait 为什么要带一把锁和一个条件 {#wait}

条件（“队列不空”）存在共享数据里，检查它要加锁。问题出在“检查完发现是空的”和“睡下”之间：如果在这两步之间生产者放进了数据、发了通知，这时消费者还没睡，通知没人接，就丢了；消费者随后睡下，可能再也没人叫它。

<svg viewBox="0 0 760 262" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="上：先检查队列是空的、再去睡，中间生产者放进数据并通知，通知没人接，消费者一直睡下去。下：wait 在同一把锁里放锁并睡下，生产者只能在它睡下之后拿到锁、放数据、通知，消费者被叫醒后重新拿锁、再检查" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ts1bg  { fill: #fbfaf7; }
    .ts1c   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .ts1p   { fill: #ddebf7; stroke: #6f93b8; stroke-width: 1.3; }
    .ts1bad { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .ts1ink { fill: #1c1b18; font-size: 12.5px; }
    .ts1mut { fill: #6b6558; font-size: 12px; }
    .ts1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .ts1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .ts1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1c { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1p { fill: #1f3247; stroke: #5f8db8; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1bad { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1ink, :root:is([data-theme="dark"], [data-theme="black"]) .ts1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts1hd { fill: #a19caf; }
  </style>
  <defs><marker id="ts1arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ts1hd"/></marker></defs>
  <rect class="ts1bg" x="0" y="0" width="760" height="262" rx="10"/>
  <text class="ts1ttl" x="24" y="30">检查和睡下分成两步：通知会丢</text>
  <rect class="ts1c" x="24" y="44" width="164" height="52" rx="6"/>
  <text class="ts1ink" x="36" y="66">消费者：看队列，</text>
  <text class="ts1ink" x="36" y="84">是空的</text>
  <rect class="ts1p" x="210" y="44" width="164" height="52" rx="6"/>
  <text class="ts1ink" x="222" y="66">生产者：放进一个，</text>
  <text class="ts1ink" x="222" y="84">notify</text>
  <rect class="ts1c" x="396" y="44" width="164" height="52" rx="6"/>
  <text class="ts1ink" x="408" y="66">消费者：去睡</text>
  <rect class="ts1bad" x="582" y="44" width="154" height="52" rx="6"/>
  <text class="ts1ink" x="594" y="66">没人再叫它，</text>
  <text class="ts1ink" x="594" y="84">一直睡下去</text>
  <path class="ts1ln" d="M188,70 L207,70" marker-end="url(#ts1arr)"/>
  <path class="ts1ln" d="M374,70 L393,70" marker-end="url(#ts1arr)"/>
  <path class="ts1ln" d="M560,70 L579,70" marker-end="url(#ts1arr)"/>
  <text class="ts1mut" x="210" y="116">通知发出时还没有人在等，这次通知就丢了。</text>
  <text class="ts1ttl" x="24" y="152">wait(lk, 条件)：放锁和睡下一步完成</text>
  <rect class="ts1c" x="24" y="166" width="164" height="52" rx="6"/>
  <text class="ts1ink" x="36" y="188">消费者：拿锁，</text>
  <text class="ts1ink" x="36" y="206">看队列，是空的</text>
  <rect class="ts1c" x="210" y="166" width="164" height="52" rx="6"/>
  <text class="ts1ink" x="222" y="188">wait：放锁并睡下，</text>
  <text class="ts1ink" x="222" y="206">中间没有空隙</text>
  <rect class="ts1p" x="396" y="166" width="164" height="52" rx="6"/>
  <text class="ts1ink" x="408" y="188">生产者：拿到锁，</text>
  <text class="ts1ink" x="408" y="206">放进一个，notify</text>
  <rect class="ts1c" x="582" y="166" width="154" height="52" rx="6"/>
  <text class="ts1ink" x="594" y="188">醒来重新拿锁，</text>
  <text class="ts1ink" x="594" y="206">再看：有了</text>
  <path class="ts1ln" d="M188,192 L207,192" marker-end="url(#ts1arr)"/>
  <path class="ts1ln" d="M374,192 L393,192" marker-end="url(#ts1arr)"/>
  <path class="ts1ln" d="M560,192 L579,192" marker-end="url(#ts1arr)"/>
  <text class="ts1mut" x="24" y="242">生产者要放数据必须先拿锁，而消费者睡下之前一直拿着锁，所以通知一定发在它睡下之后。</text>
</svg>

`cv.wait(lk)` 解决的就是这个空隙：调用时线程必须已经拿着锁，`wait` 把“放锁”和“挂到等待队列上睡下”作为一步完成，生产者想改队列必须先拿到这把锁，就只能排在消费者睡下之后，它发的通知一定有人接。被叫醒后，`wait` 先重新拿回锁再返回，所以返回时又可以安全地读共享数据。

条件为什么还要再检查一遍？有两个原因。一是虚假唤醒（spurious wakeup）：标准允许 `wait` 在没人通知时也返回，实现上这样更简单。二是醒来不等于条件还成立：两个消费者都被叫醒，前一个把唯一的数据拿走了，后一个醒来面对的仍是空队列。**所以 `wait` 永远放在检查条件的循环里，或者直接用带谓词的版本 `cv.wait(lk, [&]{ return !q.empty(); })`**，它内部就是 `while (!pred()) wait(lk);`。

### 3.3 有界队列：生产者和消费者 {#bounded-queue}

队列满了生产者也要等，所以一共两个条件、两个条件变量：

```cpp
template <class T>
class BoundedQueue {
public:
    explicit BoundedQueue(size_t cap) : cap_(cap) {}
    void push(T v) {
        std::unique_lock<std::mutex> lk(m_);
        not_full_.wait(lk, [&] { return q_.size() < cap_; });   // 满了就等
        q_.push_back(std::move(v));
        lk.unlock();
        not_empty_.notify_one();
    }
    T pop() {
        std::unique_lock<std::mutex> lk(m_);
        not_empty_.wait(lk, [&] { return !q_.empty(); });       // 空了就等
        T v = std::move(q_.front());
        q_.pop_front();
        lk.unlock();
        not_full_.notify_one();
        return v;
    }
private:
    std::mutex m_;
    std::condition_variable not_full_, not_empty_;
    std::deque<T> q_;
    size_t cap_;
};
```

容量 4，一个生产者放进 1 到 100000，一个消费者取出来求和，结果 5000050000，和公式算的一样。这里用 `unique_lock` 而不是 `lock_guard`，因为 `wait` 要在中途放锁、再拿锁。`notify` 放在 `unlock` 之后：被叫醒的线程第一件事是拿锁，如果通知时锁还在自己手里，它醒来马上又得等。

`notify_one` 只叫醒一个，适合“来了一个数据，够一个人用”；`notify_all` 叫醒全部，适合状态整体变了，比如队列关闭、所有人都该退出。每个被叫醒的线程都会去抢同一把锁再检查条件，所以只有一个人能用上时，用 `notify_all` 只是让其余的人白醒一次。

## 4. 信号量：一个计数器加一个等待队列 {#semaphore}

信号量（semaphore）里存一个非负整数。`acquire`（POSIX 里是 `sem_wait`）把它减 1，已经是 0 就睡下等；`release`（`sem_post`）把它加 1，有人在等就叫醒一个。它适合描述“还剩几个”：同一个有界队列，用两个信号量分别数空位和数据，就不用自己写条件判断：

```cpp
template <class T, std::ptrdiff_t N>
class SemQueue {
public:
    void push(T v) {
        free_.acquire();                       // 空位 -1，没有空位就睡
        { std::lock_guard<std::mutex> g(m_); q_.push_back(std::move(v)); }
        used_.release();                       // 数据 +1
    }
    T pop() {
        used_.acquire();
        T v;
        { std::lock_guard<std::mutex> g(m_); v = std::move(q_.front()); q_.pop_front(); }
        free_.release();
        return v;
    }
private:
    std::counting_semaphore<N> free_{N}, used_{0};   // C++20
    std::mutex m_;
    std::deque<T> q_;
};
```

同样的测试也得到 5000050000。信号量只管“够不够”，`deque` 本身被两个线程同时改，仍然要一把互斥锁保护。

计数只取 0 和 1 的二值信号量看起来像一把锁，差别在主人：互斥锁只能由加锁的线程解开，信号量谁都可以 `release`。**所以信号量常用来在线程之间传信号**，一个线程等，另一个线程完成某件事以后 `release` 一下放它走；用来保护临界区时，互斥锁的主人约束能帮你查出解错锁的错误，更合适。

## 5. 读写锁：读者可以一起进 {#rwlock}

很多数据读得多、改得少，比如配置表。读和读之间不会互相破坏，互斥锁却让它们也排队。读写锁（`std::shared_mutex`，pthread 里是 `pthread_rwlock_t`）分两种锁法：读锁（共享锁）可以被多个线程同时拿着，写锁（独占锁）同一时刻只能有一个，而且拿写锁时不能有任何读者。

```cpp
class Config {
public:
    std::string get(const std::string& k) const {
        std::shared_lock lk(m_);                // 读：可以多个一起
        auto it = kv_.find(k); return it == kv_.end() ? "" : it->second;
    }
    void set(const std::string& k, std::string v) {
        std::unique_lock lk(m_);                // 写：独占
        kv_[k] = std::move(v);
    }
private:
    mutable std::shared_mutex m_;               // const 的 get 里也要加锁，所以 mutable
    std::map<std::string, std::string> kv_;
};
```

读写锁要维护读者计数，每次加锁、解锁的开销比普通互斥锁大。**只有读的临界区比较长、读者又多时，并行读省下的时间才盖得过这笔开销**；临界区只有几十 ns 的话，普通互斥锁往往更快。

另一个要知道的是写者饥饿：读者一个接一个地来，读锁从不空闲，等写锁的线程就一直拿不到。glibc 的 `pthread_rwlock_t` 默认偏向读者，就有这个问题，可以用 `pthread_rwlockattr_setkind_np` 改成偏向写者（一旦有写者在等，新来的读者也要排队）。`std::shared_mutex` 的公平策略标准没有规定，看实现。

## 6. 死锁：互相等对方手里的锁

### 6.1 两把锁反着拿 {#deadlock-order}

转账要同时改两个账户，每个账户一把锁：

```cpp
struct Account { std::mutex m; long long balance = 0; };
void transfer_bad(Account& from, Account& to, long long x) {
    std::lock_guard<std::mutex> l1(from.m);     // 先锁转出方
    std::lock_guard<std::mutex> l2(to.m);       // 再锁转入方
    from.balance -= x; to.balance += x;
}
// 线程 1 反复 transfer_bad(a, b, 1)，线程 2 反复 transfer_bad(b, a, 1)
```

本机跑 3 次，3 次都卡住，5 秒超时被杀掉。线程 1 先锁 `a` 再锁 `b`，线程 2 先锁 `b` 再锁 `a`，只要两边都拿到了第一把，就各自等对方手里的第二把：

<svg viewBox="0 0 760 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="线程 1 持有锁 a、等锁 b；线程 2 持有锁 b、等锁 a。持有和等待连成一个环，谁也走不了" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ts2bg  { fill: #fbfaf7; }
    .ts2t   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .ts2l   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .ts2ink { fill: #1c1b18; font-size: 13px; }
    .ts2mut { fill: #6b6558; font-size: 12px; }
    .ts2hold { stroke: #6b6558; stroke-width: 1.6; fill: none; }
    .ts2wait { stroke: #b4553a; stroke-width: 1.6; fill: none; stroke-dasharray: 6 4; }
    .ts2hd  { fill: #6b6558; }
    .ts2hw  { fill: #b4553a; }
    .ts2red { fill: #b4553a; font-size: 12px; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2t { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2l { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2hold { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2hd { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2wait { stroke: #e08a6e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2hw { fill: #e08a6e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .ts2red { fill: #e08a6e; }
  </style>
  <defs>
    <marker id="ts2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ts2hd"/></marker>
    <marker id="ts2w" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ts2hw"/></marker>
  </defs>
  <rect class="ts2bg" x="0" y="0" width="760" height="290" rx="10"/>
  <rect class="ts2t" x="80" y="40" width="210" height="50" rx="6"/>
  <text class="ts2ink" x="96" y="62">线程 1</text>
  <text class="ts2mut" x="96" y="80">transfer_bad(a, b)</text>
  <rect class="ts2l" x="470" y="40" width="210" height="50" rx="6"/>
  <text class="ts2ink" x="486" y="70">锁 b（账户 b）</text>
  <rect class="ts2t" x="470" y="170" width="210" height="50" rx="6"/>
  <text class="ts2ink" x="486" y="192">线程 2</text>
  <text class="ts2mut" x="486" y="210">transfer_bad(b, a)</text>
  <rect class="ts2l" x="80" y="170" width="210" height="50" rx="6"/>
  <text class="ts2ink" x="96" y="200">锁 a（账户 a）</text>
  <path class="ts2hold" d="M185,170 L185,93" marker-end="url(#ts2a)"/>
  <text class="ts2mut" x="194" y="136">已持有</text>
  <path class="ts2wait" d="M290,65 L467,65" marker-end="url(#ts2w)"/>
  <text class="ts2red" x="340" y="56">等它释放</text>
  <path class="ts2hold" d="M575,90 L575,167" marker-end="url(#ts2a)"/>
  <text class="ts2mut" x="584" y="136">已持有</text>
  <path class="ts2wait" d="M470,195 L293,195" marker-end="url(#ts2w)"/>
  <text class="ts2red" x="340" y="186">等它释放</text>
  <text class="ts2mut" x="24" y="258">实线：锁在这个线程手里。虚线：线程在等这把锁。四条边连成一个环，环上每个线程都在等下一个，</text>
  <text class="ts2mut" x="24" y="276">没有谁会先放手。</text>
</svg>

### 6.2 四个条件：拆掉任意一个就不会死锁 {#four-conditions}

死锁要四个条件同时成立：互斥（锁同一时刻只能给一个线程）；持有并等待（拿着一把，再去等另一把）；不可抢占（锁只能由主人自己放，别人抢不走）；循环等待（等待关系连成环，就是上图那个环）。前三条是锁本身的性质，**实际能动手的主要是第四条，以及第二条**。

拆环最常用的办法是固定加锁顺序：所有代码都按同一个顺序拿锁，比如按锁的地址从小到大，`transfer(a, b)` 和 `transfer(b, a)` 就都是先拿同一把，环连不起来。另一个办法是一次拿齐：`std::scoped_lock lk(from.m, to.m);`（或者 C++11 的 `std::lock(m1, m2)`）把几把锁当成一件事来拿，内部用“锁一把、试着锁其余的、失败就全放掉重来”的办法避免一直占着一把等另一把。把上面的 `transfer_bad` 换成 `scoped_lock`，同样两个线程各转 20 万次，几乎瞬间跑完，两个账户的余额和开始时一样。

拆第二条的办法是 `try_lock`：拿不到第二把就把第一把也放掉，过一会儿再试。它不会死锁，但两个线程可能一直同时放、同时重试，谁也做不成，叫活锁，所以重试前通常随机等一小会儿。

### 6.3 一把锁也会卡死 {#other-hangs}

不需要两把锁也能卡住，常见的有三种。忘了解锁：手写 `lock()` / `unlock()`，中间某条路径提前 `return` 或抛了异常，用 2.2 节的 RAII 包装就不会有这个问题。同一个线程把普通互斥锁加两次：第二次等的是自己（2.1 节）。持锁时调用了不知道细节的代码：回调、虚函数、别的模块的接口，它们内部可能去拿另一把锁，或者回头来拿你手里这把。**能在锁外做的事都挪到锁外，持锁时只碰自己的数据**，这三种情况就都少了。

## 7. 只有一个变量时：原子操作 {#atomics}

1.1 节的计数器只是一个整数，为它加一把锁有点重。`std::atomic` 让一次读改写成为不可分割的一条指令，x86 上 `fetch_add` 就是一条 `lock xadd`：

```cpp
std::atomic<long long> acounter{0};
void add_atomic(int n) { for (int i = 0; i < n; ++i) acounter.fetch_add(1, std::memory_order_relaxed); }
```

两个线程各加 1000 万次，结果 20000000，不用锁，也不会睡。原子操作的边界也很清楚：**它保证的是单个变量的单次操作完整，几个变量要一起保持一致（比如转账两边的余额）时，还是要锁**。`memory_order_relaxed` 这类参数管的是这次操作和别的内存访问之间的顺序，计数器只要最终总数对，用最宽松的就够了；要靠一个原子变量去发布别的数据时就不行了，细节在[内存序与伪共享](/zh/posts/memory-ordering-false-sharing-dependency-chains/)。用原子变量自己实现一把锁（自旋锁），见[自旋锁](/zh/posts/spinlock-implementation/)；锁和原子操作做成的线程安全队列，见[线程安全队列](/zh/posts/thread-safe-queue/)。

## 8. thread_local：干脆不共享 {#thread-local}

最省事的同步是不共享。`thread_local` 变量每个线程各有一份，互不干扰，访问时不用任何同步。`errno` 就是这样：一个线程的系统调用失败不会改掉另一个线程看到的 `errno`。统计类的需求也可以这么做：每个线程累加自己的那份，最后汇总一次，只在汇总时需要同步。它的代价是每个线程启动时都要初始化自己那一份，而且线程退出后那份数据就没了，要汇总得在退出前交出来。在进程地图上，这些变量放在每个线程自己的 TLS 区，用 `fs` 寄存器找到（见[进程地图](/maps/process-map.zh.html)）。

## 9. pthread 对照 {#pthread}

Linux 上 `std::thread`、`std::mutex` 这些都是在 pthread 上包了一层，比如 `std::mutex` 里装的就是一个 `pthread_mutex_t`。读 C 代码或者老项目时会碰到 pthread 的写法：

| C++ 标准库 | pthread / POSIX | 说明 |
|---|---|---|
| `std::thread t(f)`、`t.join()`、`t.detach()` | `pthread_create`、`pthread_join`、`pthread_detach` | 线程的创建、等待、分离 |
| `std::mutex`：`lock` / `try_lock` / `unlock` | `pthread_mutex_t`：`pthread_mutex_lock` / `_trylock` / `_unlock` | 用完要 `pthread_mutex_destroy` |
| `std::recursive_mutex` | 属性设为 `PTHREAD_MUTEX_RECURSIVE` | 同一线程可重复加锁 |
| `std::condition_variable`：`wait` / `notify_one` / `notify_all` | `pthread_cond_t`：`pthread_cond_wait` / `_signal` / `_broadcast` | `pthread_cond_wait` 同样要传入已加锁的互斥锁 |
| `std::counting_semaphore`：`acquire` / `release` | `sem_t`：`sem_wait` / `sem_post` | `sem_init` 的第二个参数非 0 时可在进程间共享 |
| `std::shared_mutex`：`lock_shared` / `lock` | `pthread_rwlock_t`：`pthread_rwlock_rdlock` / `_wrlock` | 读锁、写锁 |
| `thread_local` | `__thread`、`pthread_key_create` | 每线程一份 |

pthread 的函数不抛异常，失败时返回错误码（不是设置 `errno`），所以每个返回值都要检查；也没有析构函数，忘记 `unlock`、`destroy` 的风险都要自己扛，这正是 C++ 用 RAII 包装它们的原因。
