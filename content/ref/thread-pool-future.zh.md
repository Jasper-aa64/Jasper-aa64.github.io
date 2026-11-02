---
title: "线程池和 future：std::thread、promise、packaged_task、async"
date: 2026-11-02
slug: "thread-pool-future"
description: "std::thread 起一个线程，析构前必须 join 或 detach；参数默认按值拷进新线程。要拿回结果，promise 和 future 各握共享状态的一头：值或异常只写一次、只取一次。packaged_task 把函数和 promise 包在一起，async 再替你开线程，它返回的 future 析构时会等任务跑完。最后手写一个线程池：一个任务队列、一把锁、一个条件变量、N 个工作线程，submit 返回 future，关闭时把剩下的任务做完再退出。"
summary: "future 拿结果靠的是一块共享状态：promise 写、future 读，各一次；packaged_task 和 async 都是在它外面再包一层。线程池就是一个加锁的任务队列加几个一直在取任务的线程，难点在停止：标志要在锁里改，队列要先做完。"
toc: true
group: cpplinux
weight: 113
math: true
---

一个程序要同时做几件事，最直接的办法是每件事开一个线程。接下来马上有两个问题：线程算出来的结果怎么拿回来，以及任务一多，是不是每个任务都值得开一个新线程。前一个问题的答案是 `future` 这一族，后一个的答案是线程池。线程之间怎么用锁和条件变量配合，见[线程同步](/zh/ref/thread-sync/)。

## 1. std::thread：起一个线程

### 1.1 join 和 detach：析构前必须二选一 {#join-detach}

```cpp
std::thread t(work, 42);   // 构造完，新线程就开始跑 work(42)
// ……主线程干别的……
t.join();                  // 等它跑完
```

`std::thread` 对象只是新线程的一个把手。把手销毁时，标准要求你已经说清楚和这个线程的关系：`join()` 是等它结束，`detach()` 是放手不管、让它自己跑完。两样都没做，`std::thread` 的析构函数会直接调 `std::terminate`，整个进程退出。这样规定是因为两种默认都危险：默认 join 会让析构悄悄卡住，默认 detach 会让线程继续用着已经销毁的局部变量。**所以每个 `std::thread` 都要在析构之前 join 或 detach**，C++20 的 `std::jthread` 把“析构时自动 join”做成了默认行为。

detach 以后线程还在跑，主线程却不再等它。如果 `main` 先返回，进程退出，这个线程会被直接终止；它要是还引用着 `main` 里的局部变量，在那之前就已经是悬空引用了。

### 1.2 传参：默认按值拷进新线程 {#thread-args}

`std::thread t(f, a, b)` 会把 `a`、`b` **拷贝**一份存进新线程，再用这份拷贝调 `f`。即使 `f` 的参数声明成引用，它引用的也是那份拷贝，不是调用方的变量。原因是新线程什么时候开始跑不确定，按值存一份最安全。真要传引用，得用 `std::ref(x)` 明确说出来，并且自己保证 `x` 活得比线程久。

```cpp
void add_one(int& x) { ++x; }

int n = 0;
std::thread t1(add_one, std::ref(n));   // 改的是 n
t1.join();                              // n == 1
// std::thread t2(add_one, n);          // 编译不过：拷贝出来的临时值绑不到 int&
```

只能移动的参数（`std::unique_ptr`、`std::promise`）要 `std::move` 进去，下一节的 `promise` 就是这样交给工作线程的。

## 2. 拿回结果：共享状态的两头

### 2.1 promise 和 future：一次性的通道 {#promise-future}

线程函数的返回值会被 `std::thread` 丢掉，要把结果交回给别的线程，得有一个两边都能访问的地方，并且等的一方要能睡着等它准备好。`std::promise` 和 `std::future` 就是这样一对：创建 `promise` 时，标准库在堆上分配一块**共享状态**，里面放一个值（或者一个异常）和一个“好了没有”的标志；`promise` 握着写的一头，`get_future()` 拿到的 `future` 握着读的一头。

```cpp
std::promise<int> p;
std::future<int> f = p.get_future();

std::thread t([pr = std::move(p)]() mutable {
    pr.set_value(42);          // 写进共享状态，叫醒等着的人
});
int v = f.get();               // 没好就睡，好了取走：42
t.join();
```

**这是一次性的通道：值只能写一次，也只能取一次。** 第二次 `set_value` 抛 `future_error`；`get()` 把值移出来交给你，之后这个 `future` 就失效了。要让好几个线程都读同一个结果，用 `f.share()` 换成 `std::shared_future`，它的 `get()` 返回的是引用，可以反复调。

写的一方要是还没写就析构了（比如线程中途出错退出），共享状态里永远不会有值。为了不让 `get()` 永远睡下去，`promise` 析构时会往共享状态里放一个 `broken_promise` 异常，`get()` 会把它抛出来。

<svg viewBox="0 0 760 272" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="promise 和 future 各握共享状态的一头：promise 写值或异常，future 等就绪后取走；packaged_task 是可调用对象加一个 promise，async 再替你开一个线程去跑 packaged_task" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .tp0bg  { fill: #fbfaf7; }
    .tp0w   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .tp0s   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .tp0r   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .tp0wrap { fill: none; stroke: #6b6558; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .tp0ink { fill: #1c1b18; font-size: 13px; }
    .tp0b   { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .tp0mut { fill: #6b6558; font-size: 12px; }
    .tp0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .tp0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0w { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0s { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0r { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0wrap { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0ink, :root:is([data-theme="dark"], [data-theme="black"]) .tp0b { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp0hd { fill: #a19caf; }
  </style>
  <defs><marker id="tp0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tp0hd"/></marker></defs>
  <rect class="tp0bg" x="0" y="0" width="760" height="272" rx="10"/>
  <rect class="tp0wrap" x="8" y="8" width="744" height="194" rx="10"/>
  <text class="tp0b" x="262" y="34">async = packaged_task + 替你开一个线程</text>
  <text class="tp0mut" x="262" y="54">（deferred 策略不开线程：推迟到第一次 get，在调用方线程里跑）</text>
  <rect class="tp0wrap" x="18" y="18" width="222" height="176" rx="8"/>
  <text class="tp0b" x="30" y="40">packaged_task</text>
  <text class="tp0b" x="30" y="58">= 函数 + promise</text>
  <rect class="tp0s" x="30" y="70" width="198" height="32" rx="6"/>
  <text class="tp0ink" x="42" y="91">函数 f（你的代码）</text>
  <path class="tp0ln" d="M129,102 L129,115" marker-end="url(#tp0a)"/>
  <rect class="tp0w" x="30" y="118" width="198" height="66" rx="6"/>
  <text class="tp0b" x="42" y="138">promise</text>
  <text class="tp0mut" x="42" y="156">set_value / set_exception</text>
  <text class="tp0mut" x="42" y="174">只能写一次</text>
  <rect class="tp0s" x="300" y="118" width="180" height="66" rx="6"/>
  <text class="tp0b" x="312" y="138">共享状态（在堆上）</text>
  <text class="tp0ink" x="312" y="157">值 或 异常</text>
  <text class="tp0mut" x="312" y="175">+ 好了没有的标志</text>
  <rect class="tp0r" x="556" y="118" width="180" height="66" rx="6"/>
  <text class="tp0b" x="568" y="138">future</text>
  <text class="tp0ink" x="568" y="157">get()：没好就睡</text>
  <text class="tp0mut" x="568" y="175">好了取走，只能取一次</text>
  <path class="tp0ln" d="M228,151 L297,151" marker-end="url(#tp0a)"/>
  <path class="tp0ln" d="M480,151 L553,151" marker-end="url(#tp0a)"/>
  <text class="tp0mut" x="556" y="106">在要结果的线程里读</text>
  <text class="tp0mut" x="24" y="230">两头各握一个指向共享状态的指针，共享状态等两头都没了才释放。</text>
  <text class="tp0mut" x="24" y="252">promise 没写就析构，会往里放一个 broken_promise 异常，get() 不会永远睡下去。</text>
</svg>

### 2.2 packaged_task：把函数包成能交出 future 的任务 {#packaged-task}

自己写 `promise` 时，干活的函数得知道 `promise` 的存在，在最后调 `set_value`。更常见的需求是：手上有一个普通函数，想把它丢给别的线程跑，同时拿到它返回值的 `future`。`std::packaged_task` 就是干这个的：它里面装着这个函数和一个 `promise`，调用 `packaged_task` 时，它调用函数，把返回值 `set_value` 进去，函数抛了异常就 `set_exception`。

```cpp
std::packaged_task<int(int, int)> task([](int a, int b) { return a + b; });
std::future<int> f = task.get_future();
std::thread t(std::move(task), 2, 3);   // 在别的线程里调用这个任务
t.join();
int v = f.get();                        // 5
```

`packaged_task` 本身只能移动不能拷贝（里面的 `promise` 只能有一份），所以交给 `std::thread` 时要 `std::move`。第 3 节的线程池就是用它把“任意函数”变成“队列里一个没有参数、没有返回值的任务，外加一个 `future`”。

### 2.3 async：再替你开线程 {#async}

`std::async(f, args...)` 又往前走了一步：它内部包一个 `packaged_task`，开一个线程去跑，把 `future` 还给你。一行就是“异步调用一个函数、以后拿结果”。它有两个容易忽略的行为：

- **启动策略**：`std::launch::async` 保证开新线程；`std::launch::deferred` 不开线程，等你第一次调 `get()` 或 `wait()` 时才在**你的线程**里同步执行。不写策略时，两者由实现挑，所以真想并行就写明 `std::launch::async`。
- **返回的 future 析构时会等任务跑完。** `async` 返回的 `future` 是唯一能等那个线程的东西，标准规定它的析构函数要阻塞到任务结束。所以 `std::async(std::launch::async, f);` 这样不接返回值，临时的 `future` 当场析构，当场等 `f` 跑完，整句就变成了同步调用。

本机实测（GCC 16.2）：一个睡 200 ms 的任务，用 `async` 起完马上让 `future` 出作用域，这一句耗时约 213 ms。

### 2.4 异常也走这条通道 {#exceptions}

在别的线程里抛出、没被接住的异常，会让那个线程调 `std::terminate`，整个进程退出，调用方根本接不住。共享状态里能放异常，就是为了解决这个问题：`packaged_task` 和 `async` 跑的函数抛了异常，异常被存进共享状态，**等调用方 `get()` 时在调用方的线程里重新抛出**，像同步调用一样用 `try` 接住。线程池里的任务也是靠这一点，一个任务出错不会把工作线程带走。

## 3. 线程池

### 3.1 为什么不每个任务开一个线程 {#why-pool}

开一个线程要做的事不少：分配栈（几 MiB 的虚拟地址，见[进程地图](/zh/ref/cpp-linux/#segments)）、建内核里的任务结构、调度它跑起来，结束时还要回收，合起来是几十 µs 的量级。任务本身只要几 µs 时，这笔开销比干活还贵。另一个问题是数量失控：一下来一万个请求就开一万个线程，栈占掉几十 GiB 的虚拟地址，CPU 时间也耗在线程之间来回切换上。

线程池把这两件事都管住：**线程预先开好、一直留着反复用，线程数也固定在一个上限。** 任务来了不开线程，只是放进队列，由空闲的线程取走。

### 3.2 结构：一个队列、一把锁、一个条件变量、N 个线程 {#pool-structure}

<svg viewBox="0 0 760 262" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="线程池结构：调用方 submit 把任务放进由互斥锁保护的任务队列，并通过条件变量叫醒一个工作线程；四个工作线程循环取任务、在锁外执行；packaged_task 把结果或异常写进 future，调用方以后 get 取回" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .tp1bg  { fill: #fbfaf7; }
    .tp1c   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .tp1q   { fill: #fdf5e3; stroke: #c9a24a; stroke-width: 1.3; }
    .tp1t   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .tp1w   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .tp1ink { fill: #1c1b18; font-size: 13px; }
    .tp1b   { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .tp1mut { fill: #6b6558; font-size: 12px; }
    .tp1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .tp1dash { stroke: #6b6558; stroke-width: 1.4; fill: none; stroke-dasharray: 5 4; }
    .tp1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1c { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1q { fill: #3a321f; stroke: #a8873f; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1t { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1w { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1ink, :root:is([data-theme="dark"], [data-theme="black"]) .tp1b { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1ln, :root:is([data-theme="dark"], [data-theme="black"]) .tp1dash { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .tp1hd { fill: #a19caf; }
  </style>
  <defs><marker id="tp1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tp1hd"/></marker></defs>
  <rect class="tp1bg" x="0" y="0" width="760" height="262" rx="10"/>
  <rect class="tp1c" x="24" y="56" width="166" height="44" rx="6"/>
  <text class="tp1ink" x="36" y="83">调用方 A：submit(f)</text>
  <rect class="tp1c" x="24" y="140" width="166" height="44" rx="6"/>
  <text class="tp1ink" x="36" y="167">调用方 B：submit(g)</text>
  <rect class="tp1q" x="222" y="40" width="260" height="160" rx="8"/>
  <text class="tp1b" x="236" y="64">任务队列</text>
  <text class="tp1mut" x="236" y="84">每个任务：void() 外加一个 future</text>
  <rect class="tp1t" x="238" y="100" width="52" height="40" rx="4"/>
  <text class="tp1ink" x="250" y="125">任务</text>
  <rect class="tp1t" x="298" y="100" width="52" height="40" rx="4"/>
  <text class="tp1ink" x="310" y="125">任务</text>
  <rect class="tp1t" x="358" y="100" width="52" height="40" rx="4"/>
  <text class="tp1ink" x="370" y="125">任务</text>
  <text class="tp1mut" x="236" y="166">一把 mutex 护着队列</text>
  <text class="tp1mut" x="236" y="186">一个条件变量：有任务时叫醒一个</text>
  <rect class="tp1w" x="548" y="40" width="188" height="34" rx="6"/>
  <text class="tp1ink" x="560" y="62">工作线程 1</text>
  <rect class="tp1w" x="548" y="82" width="188" height="34" rx="6"/>
  <text class="tp1ink" x="560" y="104">工作线程 2</text>
  <rect class="tp1w" x="548" y="124" width="188" height="34" rx="6"/>
  <text class="tp1ink" x="560" y="146">工作线程 3</text>
  <rect class="tp1w" x="548" y="166" width="188" height="34" rx="6"/>
  <text class="tp1ink" x="560" y="188">工作线程 4</text>
  <path class="tp1ln" d="M190,78 L219,78" marker-end="url(#tp1a)"/>
  <path class="tp1ln" d="M190,162 L219,162" marker-end="url(#tp1a)"/>
  <path class="tp1ln" d="M482,57 L545,57" marker-end="url(#tp1a)"/>
  <path class="tp1ln" d="M482,99 L545,99" marker-end="url(#tp1a)"/>
  <path class="tp1ln" d="M482,141 L545,141" marker-end="url(#tp1a)"/>
  <path class="tp1ln" d="M482,183 L545,183" marker-end="url(#tp1a)"/>
  <text class="tp1mut" x="488" y="122">取走</text>
  <path class="tp1dash" d="M642,200 L642,232 L107,232 L107,187" marker-end="url(#tp1a)"/>
  <text class="tp1mut" x="230" y="252">任务跑完，packaged_task 把返回值或异常写进 future，调用方以后 get() 取回</text>
</svg>

每个工作线程都在同一个循环里：拿锁，队列空就在条件变量上睡；被叫醒、队列里有任务，就取一个，**放开锁**再执行。调用方 `submit` 时拿锁、把任务放进队列、放锁，再叫醒一个睡着的线程。锁只保护队列本身，任务的执行在锁外，所以几个线程可以同时跑各自的任务。

### 3.3 代码 {#pool-code}

```cpp
#include <condition_variable>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <vector>

class ThreadPool {
public:
    explicit ThreadPool(size_t n) {
        for (size_t i = 0; i < n; ++i)
            workers_.emplace_back([this] { work(); });
    }
    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;

    ~ThreadPool() {
        {
            std::lock_guard<std::mutex> lk(mu_);
            stop_ = true;                    // 在锁里改，等待的线程才不会错过
        }
        cv_.notify_all();                    // 叫醒所有人：把剩下的任务做完就退出
        for (auto& t : workers_) t.join();
    }

    template <class F, class... Args>
    auto submit(F&& f, Args&&... args) -> std::future<std::invoke_result_t<F, Args...>> {
        using R = std::invoke_result_t<F, Args...>;
        auto task = std::make_shared<std::packaged_task<R()>>(
            std::bind(std::forward<F>(f), std::forward<Args>(args)...));
        std::future<R> fut = task->get_future();
        {
            std::lock_guard<std::mutex> lk(mu_);
            if (stop_) throw std::runtime_error("submit on a stopped pool");
            tasks_.emplace([task] { (*task)(); });
        }
        cv_.notify_one();                    // 来了一个任务，叫醒一个线程就够
        return fut;
    }

private:
    void work() {
        for (;;) {
            std::function<void()> task;
            {
                std::unique_lock<std::mutex> lk(mu_);
                cv_.wait(lk, [this] { return stop_ || !tasks_.empty(); });
                if (stop_ && tasks_.empty()) return;   // 停了，而且活干完了
                task = std::move(tasks_.front());
                tasks_.pop();
            }
            task();                          // 在锁外执行，别的线程可以同时取任务
        }
    }

    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex mu_;
    std::condition_variable cv_;
    bool stop_ = false;
};
```

用法：

```cpp
ThreadPool pool(4);
auto f = pool.submit([](int a, int b) { return a + b; }, 2, 3);
int v = f.get();   // 5
```

`submit` 里有两层包装，各有原因。队列里要放同一种类型的东西，而每个任务的参数、返回值都不一样，所以先用 `std::bind` 把参数绑进去，得到一个“无参数、返回 `R`”的调用，再包成 `packaged_task<R()>`，拿出它的 `future` 还给调用方。可 `packaged_task` 只能移动，`std::function` 却要求里面的东西能拷贝，所以把它放进 `shared_ptr`，队列里存的是一个拷贝这个指针的 lambda。C++23 的 `std::move_only_function` 能装只能移动的东西，用它就不需要这层 `shared_ptr`。

本机用 GCC 16.2（`-std=c++20 -O2 -Wall -Wextra`）测过，连跑 3 次结果一致：4 个线程、提交 10000 个算平方的任务，结果加起来和公式算的一样；一个抛异常的任务，异常在 `get()` 里接住了，工作线程照常继续；析构前还在排队的 100 个任务，析构结束时全部跑完。

### 3.4 停止：标志在锁里改，队列先做完 {#pool-stop}

线程池最容易写错的是停止，有两处。

**第一处：`stop_` 必须在持有锁的时候改。** `cv_.wait(lk, pred)` 的过程是：拿着锁检查条件，不满足就**原子地**放锁、睡下。如果在锁外改 `stop_`，可能出现这样的顺序：工作线程拿着锁检查，`stop_` 还是假，正准备睡；析构函数这时把 `stop_` 改成真，调了 `notify_all`；可工作线程还没睡下，这次通知谁也没叫到；接着它睡下，再也没人叫它，析构函数里的 `join` 就永远等下去。在锁里改，就保证了“检查条件”和“改条件”不会穿插在一起：要么工作线程检查时已经看到真，要么它已经睡下、能被通知叫醒。把 `stop_` 换成 `std::atomic<bool>` 也解决不了这个问题，原子性管的是读写本身，管不到“查完、睡下之前”这段空隙。

**第二处：停止时队列里还有任务怎么办。** 一种写法是被叫醒发现 `stop_` 为真就直接退出，队列里剩下的任务连同它们的 `packaged_task` 一起被销毁。那些任务的 `future` 永远等不到值，`get()` 会抛 `broken_promise`。上面的代码选的是另一种：`stop_` 为真且队列空了才退出，**析构函数会等所有已经提交的任务跑完**。要“立刻停、丢掉剩下的”也可以，但要让调用方知道，比如清空队列时让每个 `future` 收到一个明确的异常。

还有两个小处。来一个任务只需要叫醒一个线程，用 `notify_one`；用 `notify_all` 会把所有睡着的线程都叫起来抢一个任务，抢不到的再睡回去，白白多了几次切换。停止时则要 `notify_all`，因为每个线程都得醒来看到 `stop_`。

### 3.5 开几个线程 {#pool-size}

线程数取决于任务的时间花在哪。任务一直在算（CPU 密集），线程数等于核数就够了，`std::thread::hardware_concurrency()` 给出逻辑核数；再多开，线程只会轮流抢核，多出切换。任务大部分时间在等（读磁盘、等网络、等数据库），等的时候核是空的，可以多开一些线程把空着的核用上。常用的估算是：

$$
N = N_\text{核} \times \left(1 + \frac{W}{C}\right)
$$

$W$ 是一个任务等待的时间，$C$ 是它真正占用 CPU 的时间。比如每个请求算 2 ms、等数据库 8 ms，8 个核大约开 $8 \times (1 + 4) = 40$ 个线程。这只是起点，实际还要压测看吞吐量和延迟再调。等待特别多的场景，与其开几百个线程，不如改成 [epoll](/zh/ref/epoll-internals/) 那样一个线程等很多个连接。

队列也该有个上限。任务进来的速度长期大于处理速度时，无界队列会一直涨到内存耗尽；有界队列满了以后，`submit` 可以阻塞、可以直接拒绝，把压力反推回调用方。只许一个线程放、一个线程取，或者要更低的开销时，队列本身还有别的写法，见 [线程安全队列](/zh/posts/thread-safe-queue/)。
