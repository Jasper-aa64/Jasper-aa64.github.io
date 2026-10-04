---
title: "交易系统笔记 #4:无锁队列与 Micro-Batching"
date: 2026-09-20
slug: "lock-free-queue-logger-micro-batching"
description: "单生产者单消费者的环形队列怎么做到不用锁——2 的幂掩码、两步交接、两边各需要的内存序——以及悄悄把竞争带回来的那些陷阱:一个共享的元素计数器、每次调用都去读对方核的判满、一行日志按字符一个槽地推。然后在它上面搭一个日志器和一个 micro-batching 处理器,最后问 lock-free 和 wait-free 到底承诺了什么。"
summary: "无锁 SPSC 队列能成立,是因为每个共享变量都只有一个写者:每一边只更新自己的计数器,只读对方的。剩下的工作就是别让这个性质被悄悄破坏——两个核都去争的共享元素计数(改成两个计数器相减)、每次调用都读对方核的判满(缓存对方的游标,它只会往安全的方向出错)、用双重映射消掉回绕处的接缝,以及一个按字符一个槽推日志的日志器(一行日志 30 个槽,改成按文本段推只要 5 个)。最后是让 lock-free 说法保持诚实的几个词:SPSC 只在快速失败的接口下才是 wait-free,有限步不等于有限时间,有界队列满了永远得在丢弃和阻塞之间二选一。"
categories: [Systems]
tags: [cpp, lock-free, wait-free, spsc, ring-buffer, atomics, logging, micro-batching, hft, low-latency]
toc: true
homepage: false
---

一个热线程要把活交给另一个线程——一行日志、一条行情、一个订单事件——它不能伸手去拿互斥锁。不是因为加锁指令慢(没有竞争时它很便宜),而是因为一把*有竞争*的锁会变成什么:抢输的一方在内核里睡下,什么时候醒由调度器说了算,不由你。如果持锁的是一个低优先级的后台线程,你就亲手在自己的关键路径上造了一个优先级反转。你要避开的不是多少纳秒,而是一个拖着长尾、你又控制不了的延迟分布。

所以目标不是"快",而是"有界",工具是无锁队列。整个设计立在一个想法上:**每个共享变量只有一个写者**——每一边只更新自己的计数器,只读对方的,两个核永远不会抢着写同一个东西。第 1 部分搭起这个环,并指出第一个悄悄破坏这条规则的陷阱。第 2 部分把剩下的跨核流量再压一压。第 3 部分在上面搭一个日志器,发现一行日志能吃掉 30 个槽。第 4 部分问 lock-free 和 wait-free 到底承诺了什么,第 5 部分用这个队列做 micro-batching。周边的功课默认已经做好:热线程绑了核、做了隔离([#1](/zh/posts/cpu-affinity-core-isolation-numa/)),它碰的内存锁住了、预先缺过页([#3](/zh/posts/hot-path-memory-allocators/)),[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 里缓存行的那套机制——release/acquire 配对和一条被争抢的行的代价——几乎在下面每一行都会出现。

---

## 1. SPSC 环

### 1.1 两个计数器和一个掩码

单生产者单消费者(SPSC)队列就是一个固定的槽数组加两个计数器。生产者拥有 `write_idx`——只有它会写这个变量。消费者拥有 `read_idx`。每一边都*读*对方的计数器,来知道还有没有空位(生产者)或有没有数据(消费者),但从不写它。这种不对称就是整个设计:每个变量只有一个写者,就没什么要锁的,也没什么要重试的。

```cpp
template <typename T>
class SpscQueue {
  std::vector<T> slots_;                       // 容量是 2 的幂
  size_t         mask_;                        // 容量 - 1

  alignas(64) std::atomic<size_t> write_idx_{0};   // 只有生产者写
  alignas(64) std::atomic<size_t> read_idx_{0};    // 只有消费者写

 public:
  explicit SpscQueue(size_t n) : slots_(round_up_pow2(n)), mask_(slots_.size() - 1) {}

  // ---- 生产者 ----
  T* try_claim() {                             // 第 1 步:往哪写?nullptr = 满了
    const size_t w = write_idx_.load(std::memory_order_relaxed);   // 我自己的计数器
    const size_t r = read_idx_.load(std::memory_order_acquire);    // 对方的
    if (w - r == slots_.size()) return nullptr;
    return &slots_[w & mask_];
  }
  void publish() {                             // 第 2 步:让元素可见
    write_idx_.store(write_idx_.load(std::memory_order_relaxed) + 1,
                     std::memory_order_release);
  }

  // ---- 消费者 ----
  T* try_peek() {                              // nullptr = 空的
    const size_t r = read_idx_.load(std::memory_order_relaxed);    // 我的
    const size_t w = write_idx_.load(std::memory_order_acquire);   // 对方的
    if (r == w) return nullptr;
    return &slots_[r & mask_];
  }
  void release() {                             // 读完了:把槽还回去
    read_idx_.store(read_idx_.load(std::memory_order_relaxed) + 1,
                    std::memory_order_release);
  }
};
```

里面有三个细节值得放慢看。

**掩码。** 计数器只增不减;槽的位置是 `idx & mask_`,其中 `mask_ = 容量 - 1`。它对每个 `idx` 都等于 `idx % 容量`——但前提是容量是 2 的幂,因为这时 `容量 - 1` 是一串 1,按位与只是保留低位。容量是运行时的值,编译器没法替你把 `%` 变成移位;所以构造函数把要求的大小向上取整到下一个 2 的幂(`round_up_pow2` 是常见的位扩散小函数),热路径上就是一个周期的按位与,而不是一次硬件除法。

**两步,不是一步。** 生产者拿到的不是 `push(const T&)`,而是一个指向槽的指针,在槽里*原地*构造元素,然后再发布。元素只写一次,直接写进它最终的位置;`push(const T&)` 则要在别处构造好再拷进来。发布单独成一步,因为那是消费者被允许察觉"这个元素存在了"的唯一时刻。

**每一边用 relaxed 读自己的计数器,用 acquire 读对方的,用 release 发布自己的。** 只有拥有者会写一个计数器,所以读自己的用 `relaxed` 就够——一个线程总能看到自己之前的写。对方的计数器才是跨核传递信息的那一个。生产者对 `write_idx_` 的 release 写,保证任何一个 acquire 读到新下标的消费者都能看到槽里的内容;消费者对 `read_idx_` 的 release 写,保证它已经读完一个槽,之后看到这个槽空出来的生产者才会去覆盖它。这就是 [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 里的 release/acquire 配对在真正干活。在 x86 上 release 写编译出来就是一条普通的 `mov`——顺序是免费的;在 ARM 上是 `stlr`,就不免费了。

还有一个运算符优先级的陷阱,如果你用回绕过的(掩码后的)下标而不是单调计数器来写判满:`(w + 1) & mask == r & mask` 的意思*不是*它看上去的那样。`==` 比 `&` 结合得更紧,所以它被解析成 `(w + 1) & (mask == r) & mask`,"满了吗"的判断几乎永远是假——生产者会高高兴兴地覆盖还没读的数据。要么给两个掩码后的操作数都加括号,要么像上面那样用不回绕的计数器,拿 `w - r` 和容量比。

### 1.2 相减,别计数:那个让两个核打起来的计数器

很容易想再加第三个字段:一个原子的元素计数,生产者发布时加一,消费者释放时减一,这样 `size()` 就是一次读。

```cpp
std::atomic<size_t> count_{0};
// 生产者,发布之后:   count_.fetch_add(1, std::memory_order_release);
// 消费者,释放之后:   count_.fetch_sub(1, std::memory_order_release);
```

这个计数器是*两个*核都写的那个变量。`fetch_add` 和 `fetch_sub` 是读改写,而读改写需要缓存行处于独占状态(Modified 或 Exclusive)——于是每一次入队都把这条行从消费者那里拽走,每一次出队又拽回来。这就是 [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 里所有权来回乒乓的问题,只有一个值得注意的区别:这是*真*共享,不是伪共享。把计数器填充到单独一条缓存行上也没用,因为两个核确实都要改同一个变量。

修法是意识到你早就有答案了。元素个数就是 `write_idx - read_idx`,算它只要两次普通的读——而读只需要行处于共享状态,不需要转移所有权:

```cpp
size_t size_approx() const {
  const size_t r = read_idx_.load(std::memory_order_acquire);    // 先读落后的那个……
  const size_t w = write_idx_.load(std::memory_order_acquire);   // ……再读领先的那个
  return w - r;
}
```

要记住两个性质。**它是两个快照拼起来的,不是同一瞬间。** 两次读发生在略有先后的两个时刻,所以结果是近似的——用来看"大概积压了多少"没问题,用来做需要精确答案的决定就不行。先读落后的计数器,得到的是一个高估:它永远不会是负数,但如果两次读之间两边都前进了很多,它甚至可能读出超过容量的值,在意的话要夹一下。**对外部观察者来说,读的顺序很重要。** `w >= r` 在每一个瞬间都成立;先读 `r`,保证你看到的 `w` 不会比那一刻更旧,差值就不会是负的。(第一次读用 `acquire`,也是为了防止第二次读被重排到它前面;两次都是 `relaxed` 的话,这个顺序只是个建议。)反过来读,第三个线程——比如一个监控循环——就可能拿到两边都前进之前的 `w` 和之后的 `r`:`w - r` 变成负数,对无符号计数器来说就回绕成一个巨大的数。(生产者或消费者自己调 `size_approx()` 碰不到这个问题,因为它自己的计数器不可能在它自己的调用中途变化。这条规则是为任何线程都可能调用的公开 `size()` 准备的。)

---

## 2. 把剩下的跨核流量再压一压

### 2.1 缓存对方的游标:一个只会往安全方向出错的旧值

看看 `try_claim()` 每次调用都做了什么:对 `read_idx_` 的一次 acquire 读——一个*消费者*写的计数器。如果队列几乎是空的、离满还远着,这次读就白读了,而且不是免费的:消费者每推进一次自己的计数器,生产者的下一次读就得跨核去取更新过的那条行。消费者的 `try_peek()` 对 `write_idx_` 有镜像的问题。

修法就是 [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 为这种情况预告过的本地缓存副本,现在放进了一个真正的队列里:生产者保留一个私有的 `cached_read_idx_`,拿*它*来判断,只有当缓存说"满了"时,才付一次真正的跨核读、刷新缓存、再判断一次。

```cpp
alignas(64) std::atomic<size_t> write_idx_{0};
            size_t              cached_read_idx_ = 0;    // 生产者私有:和生产者自己的行放在一起
alignas(64) std::atomic<size_t> read_idx_{0};
            size_t              cached_write_idx_ = 0;   // 消费者私有

T* try_claim() {
  const size_t w = write_idx_.load(std::memory_order_relaxed);
  if (w - cached_read_idx_ == slots_.size()) {                       // 看起来满了——缓存可能过期
    cached_read_idx_ = read_idx_.load(std::memory_order_acquire);    // 付一次跨核读
    if (w - cached_read_idx_ == slots_.size()) return nullptr;       // 真的满了
  }
  return &slots_[w & mask_];
}

T* try_peek() {
  const size_t r = read_idx_.load(std::memory_order_relaxed);
  if (r == cached_write_idx_) {                                      // 看起来空了——刷新
    cached_write_idx_ = write_idx_.load(std::memory_order_acquire);
    if (r == cached_write_idx_) return nullptr;                      // 真的空了
  }
  return &slots_[r & mask_];
}
```

**为什么过期的缓存是安全的。** 消费者的计数器只往前走,所以生产者缓存的副本永远*最多*等于真实值——不会跑到它前面。空余空间按 `容量 - (w - cached_read_idx_)` 算,所以过期的缓存只会*低*估空位。它可能在其实还有空间时说"满了"——这时代码会刷新、发现真相——但它绝不会在没有空间时说"还有地方"。每一个*拒绝*写入的决定,都基于一次新鲜的 acquire 读;缓存只决定现在值不值得付那一次读。消费者的缓存也往同样安全的方向过期:它可能太早说"空了",绝不会在没有数据时说"有数据"。

还有第二个更安静的收益。消费者真去刷新缓存时,通常会发现*很多*元素已经到了,可以把它们全处理完再去碰生产者的行。跨核读是每一批付一次,而不是每个元素付一次。

### 2.2 镜像的是地址,不是数据

字节环形缓冲区——或者变长记录的环——有一个别扭的时刻:一次从末尾附近开始、越过末尾的写。通常的处理是把它拆成两次拷贝,一次拷到物理末尾,一次从开头开始,再加一个分支决定什么时候拆。有一个技巧能消掉这道接缝:把*同一块物理内存*映射到两段相邻的虚拟地址上,于是缓冲区看起来有两倍长,后一半是前一半的镜像。一次越过前一半末尾的写,直接继续写进后一半,正好落在回绕本该把它放到的位置。一次 `memcpy`,没有分支。

一共三步,都是 Linux 上的:

```cpp
void* base = mmap(nullptr, 2 * N, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);      // 只预留地址,别的什么都不要
int   fd   = memfd_create("ring", 0);                                                  // 一个内存里的"文件"……
ftruncate(fd, N);                                                                      // ……长 N 字节
mmap(base,                          N, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);   // 第一个视图
mmap(static_cast<char*>(base) + N,  N, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, 0);   // 第二个视图:同样的页
```

1. 用 `PROT_NONE` 预留 `2N` 字节的地址空间——只占下地址,别的什么都不要。
2. 用 `memfd_create` 建一个 `N` 字节的内存文件,用 `ftruncate` 设好大小。
3. 把这个文件描述符分别映射到预留区的前一半和后一半,都用 `MAP_SHARED | MAP_FIXED`。

两个视图背后是同样的页,所以 `buf[i]` 和 `buf[i + N]` 就是同一个字节。

![两幅图。左:一排八块编号的石砖,尽头是一堵墙,一次写被切成两段箭头。右:三排对齐的同样八块编号石砖(第一个视图、物理页、第二个视图),相同编号之间用竖直虚线相连,一次写从第一个视图的末尾继续写到第二个视图的前两块砖上。](/images/lock-free-queue/mirror-the-addresses.jpg)

**为什么要文件描述符?** 两个 `MAP_ANONYMOUS` 映射做不到这一点:每个匿名映射都拿到自己全新的、独立的页,第二个映射没有任何东西可以指向。要让两段虚拟地址共享页,你需要一个两者都能引用的具名对象——这里是一个 fd,System V 共享内存段也能起同样的作用。

**一切都在构造时完成。** 预留、描述符、两次映射都只做一次;之后每一次入队出队都是普通的内存访问,没有系统调用。这和 [#3](/zh/posts/hot-path-memory-allocators/) 是同一招——热路径上没有任何事是第一次发生——这些页也该享受同样的待遇:预先缺页、锁住。

**它的代价,以及什么时候用不上。** `N` 必须是页大小的倍数;中途失败要干净地回滚(`munmap`、`close`);第二个视图会增加页表项和 TLB 压力。也要注意 1.1 的队列*不需要*它:槽是固定大小的,一个元素永远不会跨过末尾,单个元素的写永远不会在拷贝中途回绕。镜像在字节流、变长记录、一次批量读写好几个元素时才划算——这些场景里拷贝本身是大头,跨过末尾又很常见。

---

## 3. 在队列上搭一个日志器

### 3.1 一个读者慢得起的队列

日志是这种队列的经典用户。热路径想记点东西;昂贵的部分——格式化、文件 I/O、`write` 系统调用——应该在一个没人等着的地方发生。所以热线程只负责填一个队列槽,一个专门的后台线程负责把它排空。

队列的槽是固定大小的,所以放进槽里的东西得是一个带标签的 union——一个类型标签,加上能放下你可能记录的最大东西的空间:

```cpp
enum class Tag : uint8_t { Char, Int, Long, Double, Text /* … */ };

struct LogElement {
  Tag tag;
  union {
    char c;  int i;  long l;  double d;  /* …其他数值类型… */
    char s[256];                          // 决定了每个槽价钱的那个成员
  } u;
};   // x86-64 上 264 字节:标签补齐到 8,再加 256 字节的成员
```

那个 `char s[256]` 决定了每个槽的大小:一个只装了一个 `char` 的元素,照样占 264 字节。800 万个这样的元素大约 2 GiB——一个故意开得很大的缓冲,因为慢吞吞的读者在突发时一定会落后。

读者那边是一个循环:把现有的排空,刷文件,睡一会儿:

```cpp
while (running_) {
  while (LogElement* e = queue_.try_peek()) {
    write_to_file(*e);                  // 按 e->tag 分情况处理
    queue_.release();
  }
  file_.flush();
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
}
```

10 ms 的睡眠是一个选择,不是必须的:这个线程对延迟不敏感,把核让出去比空转好——代价是日志行最多晚约 10 ms 落到文件里,而且队列要吸收这段时间里产生的全部东西。SPSC 带出两条结构性规则。**一个日志器实例只服务一个生产线程**——第二个生产者会打破"每个计数器一个写者"的约定,所以要么每个线程一个日志器,要么每个线程一个队列。**关闭的顺序很重要**:先等队列排空,*再*停读者线程,然后关文件。先停读者,还在队列里的东西就无声地丢了。

### 3.2 一行日志 30 个槽

生产者这边有一种很自然的写法:沿着格式串走,每个字面字符作为一个元素推进去,每个 `%` 占位符作为一个值元素推进去。

```cpp
template <typename T, typename... Rest>
void log(const char* fmt, const T& value, const Rest&... rest) {
  for (; *fmt; ++fmt) {
    if (*fmt == '%') { push(value); log(fmt + 1, rest...); return; }
    push(*fmt);                                  // 一个字符 = 一个 264 字节的槽
  }
}
void log(const char* fmt) { for (; *fmt; ++fmt) push(*fmt); }   // 没有参数了
```

数一数 `log("Order Executed, id=%, price=%\n", id, price)` 做了什么:`Order Executed, id=` 的 19 个字符,一个整数,`, price=` 的 8 个字符,一个 double,一个换行——**30 次推入**,每次一个 264 字节的元素。总共 7,920 字节,约 124 条缓存行,只为了记录大约 40 字节的实际内容。

<svg viewBox="0 0 760 274" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="同一行日志两种推法:按字符推占 30 个 264 字节的队列槽,约 7.7 KiB;按三段文本加两个值推只占 5 个槽,约 1.3 KiB" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .bg    { fill: #fbfaf7; }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .row   { fill: #3a372f; font-size: 12px; font-weight: 700; }
    .lbl   { fill: #3a372f; font-size: 11.5px; }
    .cap   { fill: #6b6558; font-size: 11px; }
    .chr   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .val   { fill: #eef1f4; stroke: #9fb0c0; stroke-width: 1.2; }
    .txt   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.4; }
    .brk   { fill: none; stroke: #8a8474; stroke-width: 1.4; }
      :root[data-theme="dark"] .bg { fill: #17161b; }
      :root[data-theme="dark"] .title { fill: #e9e7ef; }
      :root[data-theme="dark"] .row { fill: #d7d3c8; }
      :root[data-theme="dark"] .lbl { fill: #d7d3c8; }
      :root[data-theme="dark"] .cap { fill: #a19caf; }
      :root[data-theme="dark"] .chr { fill: #4a2f2c; stroke: #8f5a4c; }
      :root[data-theme="dark"] .val { fill: #2b3038; stroke: #8391a0; }
      :root[data-theme="dark"] .txt { fill: #33421f; stroke: #8fb257; }
      :root[data-theme="dark"] .brk { stroke: #9a9384; }
  </style>
  <rect class="bg" x="0" y="0" width="760" height="274" rx="10"/>
  <text class="title" x="24" y="30">同一行日志,两种推法——每个方块是一个 264 字节的队列槽</text>
  <text class="row" x="24" y="58">按字符推</text>
  <rect class="chr" x="24.0" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="47.7" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="71.4" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="95.1" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="118.8" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="142.5" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="166.2" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="189.9" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="213.6" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="237.3" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="261.0" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="284.7" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="308.4" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="332.1" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="355.8" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="379.5" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="403.2" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="426.9" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="450.6" y="68" width="21" height="26" rx="3"/>
  <rect class="val" x="474.3" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="498.0" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="521.7" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="545.4" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="569.1" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="592.8" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="616.5" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="640.2" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="663.9" y="68" width="21" height="26" rx="3"/>
  <rect class="val" x="687.6" y="68" width="21" height="26" rx="3"/>
  <rect class="chr" x="711.3" y="68" width="21" height="26" rx="3"/>
  <path class="brk" d="M24.0,107 L24.0,112 L732.3,112 L732.3,107"/>
  <text class="lbl" x="24" y="132">30 个槽 × 264 B ≈ 写了 7.7 KiB——其中真正的文本和数值只有约 40 字节</text>
  <text class="row" x="24" y="166">按文本段推</text>
  <rect class="txt" x="24.0" y="176" width="21" height="26" rx="3"/>
  <rect class="val" x="47.7" y="176" width="21" height="26" rx="3"/>
  <rect class="txt" x="71.4" y="176" width="21" height="26" rx="3"/>
  <rect class="val" x="95.1" y="176" width="21" height="26" rx="3"/>
  <rect class="txt" x="118.8" y="176" width="21" height="26" rx="3"/>
  <path class="brk" d="M24.0,215 L24.0,220 L139.8,220 L139.8,215"/>
  <text class="lbl" x="24" y="240">5 个槽 × 264 B ≈ 1.3 KiB——同样的内容,字节数只有六分之一</text>
  <text class="cap" x="156.5" y="193">文本段 · id · 文本段 · price · 文本段</text>
  <rect class="chr" x="24" y="254" width="12" height="12" rx="2"/>
  <text class="cap" x="42" y="264">一个字符</text>
  <rect class="val" x="152" y="254" width="12" height="12" rx="2"/>
  <text class="cap" x="170" y="264">一个值(int、double……)</text>
  <rect class="txt" x="342" y="254" width="12" height="12" rx="2"/>
  <text class="cap" x="360" y="264">一段文本(最多 255 个字符)</text>
</svg>

> 图:两行记录的是同一行日志。队列、内存序、读者都没变——变的只是每次调用的工作单位。30 次发布变成了 5 次。

代价体现在三个地方:

- **热路径按槽付钱。** 每次 log 调用 30 次拷贝、30 次 release 写——如果队列还维护着一个共享元素计数(1.2),那就是在消费者也在抢的那条行上做 30 次有竞争的读改写。
- **它会把热路径自己的数据挤出去。** 每次调用 7.7 KiB,占典型的 32–48 KB L1 数据缓存相当大的一部分;一次弄脏六分之一到四分之一 L1 的日志调用,对紧接着运行的代码来说不是免费的。
- **缓冲区比看起来小。** 800 万个槽、每行日志 30 个槽,只能装约 28 万行日志,不是 800 万行。慢读者会更早把它塞满,"队列大到永远填不满"的余量大半都没了。

**什么都不用改的修法:按文本段推。** 不再一个字符一个槽,而是把两个占位符之间的字面文本收集起来,作为一个 `Text` 元素推进去——每个槽最多 255 个字符,更长的拆成几个槽。上面的例子从 30 次推入降到 5 次(三个文本段、两个值),从 7.7 KiB 降到约 1.3 KiB。只改生产者这边的 `log()`;读者本来就知道怎么写一个文本槽。

```cpp
LogElement* claim() {                       // 策略点:队列满了怎么办?
  LogElement* s;
  while ((s = queue_.try_claim()) == nullptr) { /* 在这里空转——或者记一次丢弃、放弃这条记录 */ }
  return s;
}

void push_text(const char* p, size_t n) {
  while (n > 0) {
    const size_t k = std::min<size_t>(n, 255);         // 给结尾的 NUL 留位置
    LogElement* slot = claim();
    slot->tag = Tag::Text;
    std::memcpy(slot->u.s, p, k);
    slot->u.s[k] = '\0';
    queue_.publish();
    p += k;  n -= k;
  }
}

template <typename T, typename... Rest>
void log(const char* fmt, const T& value, const Rest&... rest) {
  const char* run = fmt;                                // 当前文本段的起点
  for (; *fmt; ++fmt) {
    if (*fmt == '%') {
      push_text(run, static_cast<size_t>(fmt - run));   // 占位符之前的全部内容,一次推完
      push(value);
      log(fmt + 1, rest...);
      return;
    }
  }
}
void log(const char* fmt) { push_text(fmt, std::strlen(fmt)); }
```

这是个草图:`%%` 转义和参数个数错误都没处理。

**两个更大的改动,以及各自在哪里失效。**

*推格式串的指针。* 字符串字面量有静态存储期、不能修改,所以它的地址在整个运行期间都有效:热路径可以只把一个 8 字节指针加上参数值放进队列,由读者来格式化。这改的是协议,不只是 `log()`。读者现在得解析格式串、取正确个数的参数槽——而因为队列一次只发布一个槽,它可能看到一条指针已经到了、参数还没到的记录。你得一次预留好几个槽、一起发布,或者改成变长记录。

这个技巧之所以成立,只因为被指的东西活得比读者久,而且永远不变。参数没有这个性质:

```cpp
void on_fill(const Fill& f) {
  std::string sym = f.symbol();
  logger.log("symbol=%\n", sym);     // 假设只把 sym 的字符指针放进队列……
}                                    // ……sym 在这里就销毁了;读者是之后、在另一个线程上才来的
```

读者要在排队延迟加上最多 10 ms 的睡眠之后才会到——那时 `sym` 早没了,`c_str()` 指针或栈上的缓冲区也一样会失效。所以参数是在生产者线程里、趁它还拥有它们的时候*拷贝*进队列的;只有活满整个运行期、又永远不变的东西,才能按指针传。

*在编译期解析格式串。* 把上一个想法推到底:一条日志语句里所有静态的东西——格式串、参数类型——在编译期抽出来,换成一个小 ID;运行时只记录 ID 和原始参数值,把它们变成文本推迟到离线步骤去做。[NanoLog](https://github.com/PlatformLab/NanoLog) 就是这么做的,它的 README 报告每次调用中位数约 7 ns(它自己的测量,我没复现过)。[Quill](https://github.com/odygrd/quill) 走的是另一条路:热线程把参数编码进自己的队列,后台线程做格式化和 I/O,队列可以有界或无界、满了阻塞或丢弃,还带着丢弃/阻塞次数的计数器。所有这些修法的模式都一样:一次 log 调用的代价是*每次调用的槽数 × 每个槽的代价*,每一个真正的修法都在缩小第一个因子,而不是打磨第二个。

---

## 4. lock-free 承诺的是进展,不是速度

### 4.1 一串由弱到强的保证

"lock-free"这个词常被用得很随意。其实有一串由弱到强的保证,一个操作落在哪一级,取决于*别的*线程慢了、被挂起了、或者死了的时候会怎样:

| 保证 | 承诺了什么 | 典型形状 |
|---|---|---|
| **阻塞** | 什么都不承诺:另一个线程被换下去了,你可能被无限期地卡住 | 一把锁;空转等另一个线程的标志位 |
| **无障碍(obstruction-free)** | *如果别人都停下来*,你能在有限步内完成;有竞争时大家可能活锁 | 多半是文献里的过渡概念 |
| **无锁(lock-free)** | *整个系统*总在前进——总有某个线程在有限步内完成——但某个特定线程可能永远输 | 一个 CAS 重试循环 |
| **无等待(wait-free)** | *每个*线程都在自己的有限步内完成,不管别人做什么 | 一段固定的步骤,没有重试循环 |

lock-free 承诺的是*有人*在前进;wait-free 承诺的是*每个人*都在前进。所以 lock-free 不等于"从不等待"——一个卡在 CAS 循环里的线程就在等,只是它的等待总是意味着别人在前进。

### 4.2 SPSC 队列落在哪一级

1.1 的队列落在哪?

| 操作 | 为什么 | 保证 |
|---|---|---|
| `try_claim` + `publish`(生产者;满了返回 `nullptr`) | 固定的几次读和写;没有循环;完成与否不取决于消费者 | wait-free |
| 一个*空转*直到有槽空出来的生产者 | 一个退出条件取决于另一个线程动作的循环 | 阻塞 |
| `try_peek` + `release`(消费者;空了返回 `nullptr`) | 和生产者一侧同样的形状 | wait-free |
| 共享计数器上的 `fetch_add` / `fetch_sub` | 一次原子读改写——x86 上是一条 `lock xadd`;在没有 LSE 扩展的 ARM 上(ARMv8.1 之前)编译成一个 load-exclusive/store-exclusive 重试循环 | x86 上 wait-free;老 ARM 上退化成 lock-free |

由此得出四点。

**"SPSC 是 wait-free"说的是接口,不是数据结构。** 队列之所以做得到,是把"满了"和"空了"的决定推给了*调用者*:`try_` 操作失败就返回,由调用者选择丢弃、重试还是阻塞。"空转等空位"的版本把第三个选择写死在了里面——连同阻塞一起。这也解释了为什么去掉 1.2 那个共享计数器让这个说法更干净:热路径上剩下的只有读和写,不依赖硬件怎么实现原子读改写。

**"消费者崩了也伤不到生产者",只在队列还有空位时成立。** 环是有界的。它一满,生产者只有两条路——丢掉这一项,或者等——而"等"又把消费者的健康状况放回了你的关键路径上。更大的缓冲区把悬崖推得更远,但并没有消除它。这就是为什么成熟的日志库把这个选择做成配置(Quill 让你选满了是阻塞还是丢弃,并报告各自发生了多少次),也是为什么 3.2 里每次 log 调用占几个槽,是一个可靠性问题,不只是速度问题。

**有限步不等于有限时间。** wait-free 限制的是*你*执行的步数,不管别人做什么。它不管操作系统在你执行到一半时抢占你,不管缺页,也不管缓存缺失。可预测的延迟是三层叠起来的:算法(操作不依赖别的线程)、操作系统(绑核、隔离、实时优先级——[#1](/zh/posts/cpu-affinity-core-isolation-numa/))、内存和硬件(锁定并预先缺页的页——[#3](/zh/posts/hot-path-memory-allocators/);缓存行卫生——[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/);热路径上没有系统调用)。wait-free 防止别的线程卡住你;另外两层防止*你自己*被卡住。

**而且 wait-free 不会自动更快。** 竞争不多时,一个普通的 CAS 循环版本通常第一次就成功,做的活比一个为了保证上界而带着整套机制的构造还少。wait-free 买到的是上界——当目标是尾部(P99.9)而不是平均值时,这才值得。一个用 CAS 认领槽位的多生产者队列,是教科书式的"lock-free 但不是 wait-free"形状,而且常常就是正确的选择。

---

## 5. Micro-Batching:让积压量来决定批大小

### 5.1 有多少拿多少,绝不等着凑满

批处理能摊薄每条消息的开销——一次唤醒、一次下游调用处理很多条消息——但每一条为了凑满一批而等待的消息,都要用延迟来付钱。固定的批大小两头都不对:有负载时太小,空闲时太慢。出路是让积压量来选:

| 积压量 | 模式 | 批大小 |
|---|---|---|
| ≤ 10 | 不忙——优化延迟 | 1 |
| ≤ 100 | 中等 | 100 |
| > 100 | 已经落后了——优化吞吐 | 1000 |

```cpp
size_t pick_batch(size_t backlog) {
  if (backlog <= 10)  return 1;
  if (backlog <= 100) return 100;
  return 1000;
}

size_t drain(Queue& q, std::vector<Msg>& out, size_t target) {
  size_t n = 0;
  Msg m;
  while (n < target && q.try_pop(m)) { out.push_back(m); ++n; }   // 绝不等着凑满一批
  return n;
}
```

关键是那行循环条件:`drain` **最多**拿 `target` 条消息,队列一空就停。它从不等着凑满一批。所以没有积压时,一批就是一条消息,不增加任何延迟;批只有在消息*已经*堆起来时才变大——反正它们本来就要等。批大小不需要定时器就跟着负载走。

### 5.2 积压量从哪来

很诱人的答案是一个计数器:入队时 `fetch_add(1)`,每批之后 `fetch_sub(batch_size)`。这又是 1.2 里那条被争抢的行——而且它还不准。计数器是在入队*之后*才加的,所以一个快的消费者可能在生产者计数之前就把消息取走并减了一;对无符号计数器来说,值会有一瞬间回绕成一个巨大的数,恰好在这个窗口里读到的人就会看到一个巨大的积压。还是去问队列吧。这有代价,而且体现在类型系统里:一个只知道 `enqueue` 和 `dequeue` 的通用批处理器看不到队列的计数器,所以队列类型必须承诺一个 O(1) 的近似大小:

```cpp
template <typename Q, typename Msg>
concept BatchSource = requires(Q q, Msg& m) {
  { q.try_pop(m) }   -> std::convertible_to<bool>;
  { q.size_approx() } -> std::convertible_to<size_t>;
};
```

一个近似的快照就够了——它只是在三档里选一档,差几条消息什么都不会改变。不自己计数并不是免费的;代价是对队列提出了更强的要求。
