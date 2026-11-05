---
title: "STL 容器的底层：vector、deque、list、map、unordered_map"
date: 2026-11-02
slug: "stl-containers"
description: "常用的 STL 容器在内存里是什么样：vector 是三个指针管着一块连续内存，容量用完就翻倍搬家；deque 是一串固定大小的块加一个中控数组；list 每个元素一个节点；map 是红黑树；unordered_map 是桶加链表，元素多了就 rehash。由此推出各自的复杂度、迭代器什么时候失效、怎么选，以及 list、map、unordered_map 这些节点式容器为什么慢（pointer chasing：每一步要读的地址都得等上一步读回来），priority_queue、string 的短字符串优化和 std::sort。数字都是 GCC 16.2 libstdc++ 上实测的。"
summary: "容器的复杂度和迭代器失效规则都不用背，从它在内存里的样子就能推出来：连续内存的 vector 搬家时一切都失效，节点式的 list、map 只有被删的那个失效，unordered_map rehash 时迭代器失效、引用不失效。"
toc: true
math: true
group: cpplinux
topic: ds
weight: 122
---

STL 由六部分组成：容器、算法、迭代器、函数对象、适配器、分配器。算法不直接认识容器，只认迭代器，所以 `std::sort` 能排 `vector`，却排不了 `list`：前者的迭代器能随机跳，后者只能一步一步走。容器之间真正的差别在内存里的样子，复杂度、迭代器什么时候失效，都是从这里推出来的。下面的数字都在 GCC 16.2（libstdc++）上实测，`sizeof` 按 64 位算。

## 1. vector：一块连续的内存

### 1.1 三个指针 {#vector-layout}

`sizeof(std::vector<int>)` 是 24：三个指针，分别指向数据开头（`begin`）、最后一个元素之后（`end`）、整块内存的末尾（`end_of_storage`）。`size()` 是 `end - begin`，`capacity()` 是 `end_of_storage - begin`。元素一个挨一个放在堆上，`v[i]` 就是“开头地址加 `i` 个元素”，一次计算一次读。

连续还带来一个好处：顺序遍历时，CPU 一次从内存取回 64 字节的一整条缓存行，后面十几个 `int` 跟着就到了，硬件预取器还会提前去取下一条（见[硬件地图](/zh/ref/cpu-memory/)）。所以哪怕中间插入要挪元素，几千个元素以内的 `vector` 往往仍然比链表快。

**`vector` 不能原样跨进程传，原因也在这三个指针上。** 每个进程有自己的页表，同一个地址在两个进程里指向不同的东西。把 `vector` 对象那 24 B 原样交给另一个进程，不管是写进管道、socket，还是放进共享内存，对方拿到的都只是写入方进程里的三个地址。结构体整个放进共享段也一样：

<svg viewBox="0 0 760 316" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="上：结构体里放 vector，共享段里只有 n 和 begin、end、end_of_storage 三个指针，begin 指向进程 A 私有堆上的元素 10、20、30，进程 B 看不见那块堆；下：结构体里放定长数组 int levels[4]，元素 10、20、30 就在共享段里" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .st9bg  { fill: #fbfaf7; }
    .st9seg { fill: #f3f6ee; stroke: #6f8f3f; stroke-width: 1.3; stroke-dasharray: 6 4; }
    .st9hp  { fill: #faf0ec; stroke: #c98a76; stroke-width: 1.3; stroke-dasharray: 6 4; }
    .st9ptr { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .st9el  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .st9elh { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .st9emp { fill: none; stroke: #b9c2cc; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .st9ink { fill: #1c1b18; font-size: 13px; }
    .st9mut { fill: #6b6558; font-size: 12px; }
    .st9ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .st9ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .st9hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9seg { fill: #1f2619; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9hp { fill: #2a1f1d; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9ptr { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9el { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9elh { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9emp { stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9ink, :root:is([data-theme="dark"], [data-theme="black"]) .st9ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st9hd { fill: #a19caf; }
  </style>
  <defs><marker id="st9a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="st9hd"/></marker></defs>
  <rect class="st9bg" x="0" y="0" width="760" height="316" rx="10"/>
  <text class="st9ttl" x="24" y="30">struct Book { uint32_t n; std::vector&lt;int&gt; levels; };</text>
  <rect class="st9seg" x="24" y="44" width="380" height="88" rx="6"/>
  <text class="st9mut" x="36" y="64">共享段（A、B 两个进程都映射了）</text>
  <rect class="st9ptr" x="36" y="76" width="72" height="36" rx="4"/>
  <text class="st9ink" x="72" y="99" text-anchor="middle">n = 3</text>
  <rect class="st9ptr" x="112" y="76" width="80" height="36" rx="4"/>
  <text class="st9ink" x="152" y="99" text-anchor="middle">begin</text>
  <rect class="st9ptr" x="196" y="76" width="80" height="36" rx="4"/>
  <text class="st9ink" x="236" y="99" text-anchor="middle">end</text>
  <rect class="st9ptr" x="280" y="76" width="112" height="36" rx="4"/>
  <text class="st9ink" x="336" y="99" text-anchor="middle">end_of_storage</text>
  <rect class="st9hp" x="456" y="44" width="280" height="88" rx="6"/>
  <text class="st9mut" x="468" y="64">进程 A 的私有堆（B 看不见）</text>
  <rect class="st9elh" x="468" y="76" width="60" height="36" rx="4"/>
  <text class="st9ink" x="498" y="99" text-anchor="middle">10</text>
  <rect class="st9elh" x="532" y="76" width="60" height="36" rx="4"/>
  <text class="st9ink" x="562" y="99" text-anchor="middle">20</text>
  <rect class="st9elh" x="596" y="76" width="60" height="36" rx="4"/>
  <text class="st9ink" x="626" y="99" text-anchor="middle">30</text>
  <rect class="st9emp" x="660" y="76" width="60" height="36" rx="4"/>
  <text class="st9mut" x="690" y="99" text-anchor="middle">空</text>
  <path class="st9ln" d="M152,112 C152,170 498,170 498,115" marker-end="url(#st9a)"/>
  <text class="st9mut" x="325" y="176" text-anchor="middle">begin 存的是元素在进程 A 里的绝对地址</text>
  <text class="st9ttl" x="24" y="214">struct Book { uint32_t n; int levels[4]; };</text>
  <rect class="st9seg" x="24" y="228" width="380" height="72" rx="6"/>
  <text class="st9mut" x="36" y="248">共享段（A、B 两个进程都映射了）</text>
  <rect class="st9ptr" x="36" y="256" width="72" height="34" rx="4"/>
  <text class="st9ink" x="72" y="278" text-anchor="middle">n = 3</text>
  <rect class="st9el" x="112" y="256" width="64" height="34" rx="4"/>
  <text class="st9ink" x="144" y="278" text-anchor="middle">10</text>
  <rect class="st9el" x="180" y="256" width="64" height="34" rx="4"/>
  <text class="st9ink" x="212" y="278" text-anchor="middle">20</text>
  <rect class="st9el" x="248" y="256" width="64" height="34" rx="4"/>
  <text class="st9ink" x="280" y="278" text-anchor="middle">30</text>
  <rect class="st9emp" x="316" y="256" width="64" height="34" rx="4"/>
  <text class="st9mut" x="348" y="278" text-anchor="middle">空</text>
  <text class="st9mut" x="430" y="256">元素就在段里，段里没有存任何地址；</text>
  <text class="st9mut" x="430" y="278">levels[i] 用各自进程的映射地址当场算出</text>
</svg>

`levels` 这个对象本身在结构体里，也就在共享段里；它管的元素却是进程 A `push_back` 时从自己的堆上分配的，那块堆只映射在 A 的页表里。进程 B 照着 `begin` 去读，读的是自己地址空间里的同一个地址，读到垃圾或者段错误。就算让元素也分配在共享段里，`begin` 存的仍是按 A 的映射地址算出的绝对地址，而同一个共享段在两个进程里的起始地址多半不同（见 [IPC 的 3.1 节](/zh/ref/ipc/)）。Boost.Interprocess 的容器为此把元素分配在段里，并把指针换成 `offset_ptr`：它存的是“目标地址减去自己所在的地址”，段映射到哪里，这个差值都不变。

下面那种写法没有这个问题，因为**数组不是指针**。`int levels[4]` 就是 4 个 `int` 本身，`sizeof` 是 16，内存里没有任何一处存着“开头的地址”。表达式里用到数组时，编译器会把它换成第一个元素的地址（数组到指针的转换，decay），这个地址是用数组当前所在的位置当场算出来的：A 把段映射在地址 X，`levels[3]` 算出来是 X + 16；B 映射在地址 Y，算出来是 Y + 16，两边落在同一个元素上。只有函数参数里的数组真的是指针：`void f(int a[])` 和 `void f(int* a)` 完全等价，函数里 `sizeof(a)` 是 8。

所以**能直接放进共享内存的，是只看这块字节就能完整描述的类型：里面没有地址，也不拥有段外的内存。**

| 能直接放 | 不能直接放 | 不能放的原因 |
|---|---|---|
| `int32_t`、`uint64_t`、`double`、`enum` | 指针、引用 | 存的是本进程的地址 |
| 定长数组 `T[N]`、`std::array<T, N>` | `vector`、`deque`、`map`、`unordered_map` | 元素在堆上，对象里存的是指向堆的指针 |
| 定长字符数组，比如 `char name[16]` | `std::string` | 长字符串在堆上；短字符串也存了一个指向自己内部缓冲区的指针（见 [6.2](#sso)） |
| 只由上面这些组成的 `struct` | 有虚函数的类 | 对象里的 vptr 指向本进程的虚表，两个进程的加载地址一般不同 |
| 无锁的 `std::atomic<int>`、`std::atomic<uint64_t>` | `std::shared_ptr`、`std::function` | `shared_ptr` 存着指向控制块的指针，`std::function` 可能把闭包放在堆上 |
| 设了 `PTHREAD_PROCESS_SHARED` 的 `pthread_mutex_t` | `std::mutex` | 标准不保证 `std::mutex` 能跨进程用 |

替换的办法照着上表来：`vector` 换成“定长数组 + 计数”，`string` 换成 `char[N]`，指针换成相对段首的偏移量；实在要用动态容器，就用 Boost.Interprocess。走管道或 socket 时发的是元素本身：先发 `size()`，再发 `data()` 开始的 `size() * sizeof(T)` 字节，对方收到后自己建一个 `vector`，前提是 `T` 也属于上表的左列。

还有两个容易漏的条件：

- **`static_assert(std::is_trivially_copyable_v<Book>)` 只是必要条件**：一个裸指针成员也满足 trivially copyable，结构体里有没有指针还得自己查。
- **两边对同一块字节的布局要理解一致**：用同一份结构体定义，用定宽类型（写 `uint32_t`，不写 `long`，`long` 在 Linux 上是 8 B、在 Windows 上是 4 B），对齐和填充也要一样，所以两边最好用同一个编译器、同一套编译选项。

### 1.2 扩容：翻倍，均摊 O(1) {#vector-growth}

容量用完以后，`push_back` 没法在原地把内存变大：后面的地址可能已经给了别人。它只能分配一块更大的新内存，把旧元素搬过去，再释放旧的。从空 `vector` 开始一个个 `push_back`，实测容量的变化是：

```text
1 2 4 8 16 32 64 128 256 512 1024 2048
```

libstdc++ 每次翻倍，MSVC 每次乘 1.5。**按倍数长，而不是每次多加固定几个，是均摊 O(1) 的关键**：攒到 $n$ 个元素，搬家搬过的元素一共是 $1 + 2 + 4 + \dots + n/2 < n$ 个，摊到每次 `push_back` 头上是常数；要是每次只多加 10 个，搬动次数就是 $n^2/20$ 量级。

<svg viewBox="0 0 760 262" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="容量为 4 的旧缓冲区已满；push_back 第 5 个元素时分配容量为 8 的新缓冲区，把 4 个元素移过去，放入第 5 个，再释放旧缓冲区，begin、end、end_of_storage 三个指针都指向新内存" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .st0bg  { fill: #fbfaf7; }
    .st0old { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .st0mv  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .st0new { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .st0emp { fill: none; stroke: #b9c2cc; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .st0ink { fill: #1c1b18; font-size: 13px; }
    .st0mut { fill: #6b6558; font-size: 12px; }
    .st0ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .st0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .st0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0old { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0mv { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0new { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0emp { stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0ink, :root:is([data-theme="dark"], [data-theme="black"]) .st0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st0hd { fill: #a19caf; }
  </style>
  <defs><marker id="st0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="st0hd"/></marker></defs>
  <rect class="st0bg" x="0" y="0" width="760" height="262" rx="10"/>
  <text class="st0ttl" x="24" y="83">旧缓冲区（容量 4）</text>
  <rect class="st0old" x="200" y="60" width="50" height="36" rx="4"/>
  <text class="st0ink" x="225" y="83" text-anchor="middle">1</text>
  <rect class="st0old" x="252" y="60" width="50" height="36" rx="4"/>
  <text class="st0ink" x="277" y="83" text-anchor="middle">2</text>
  <rect class="st0old" x="304" y="60" width="50" height="36" rx="4"/>
  <text class="st0ink" x="329" y="83" text-anchor="middle">3</text>
  <rect class="st0old" x="356" y="60" width="50" height="36" rx="4"/>
  <text class="st0ink" x="381" y="83" text-anchor="middle">4</text>
  <text class="st0mut" x="430" y="83">满了；搬完以后释放</text>
  <text class="st0mut" x="200" y="114">↑ begin</text>
  <text class="st0mut" x="400" y="114">↑ end = end_of_storage</text>
  <path class="st0ln" d="M300,100 L300,146" marker-end="url(#st0a)"/>
  <text class="st0mut" x="308" y="134">移过去</text>
  <text class="st0ttl" x="24" y="173">新缓冲区（容量 8）</text>
  <rect class="st0mv" x="200" y="150" width="50" height="36" rx="4"/>
  <text class="st0ink" x="225" y="173" text-anchor="middle">1</text>
  <rect class="st0mv" x="252" y="150" width="50" height="36" rx="4"/>
  <text class="st0ink" x="277" y="173" text-anchor="middle">2</text>
  <rect class="st0mv" x="304" y="150" width="50" height="36" rx="4"/>
  <text class="st0ink" x="329" y="173" text-anchor="middle">3</text>
  <rect class="st0mv" x="356" y="150" width="50" height="36" rx="4"/>
  <text class="st0ink" x="381" y="173" text-anchor="middle">4</text>
  <rect class="st0new" x="408" y="150" width="50" height="36" rx="4"/>
  <text class="st0ink" x="433" y="173" text-anchor="middle">5</text>
  <rect class="st0emp" x="460" y="150" width="50" height="36" rx="4"/>
  <rect class="st0emp" x="512" y="150" width="50" height="36" rx="4"/>
  <rect class="st0emp" x="564" y="150" width="50" height="36" rx="4"/>
  <text class="st0mut" x="200" y="204">↑ begin</text>
  <text class="st0mut" x="460" y="204">↑ end</text>
  <text class="st0mut" x="616" y="204">↑ end_of_storage</text>
  <text class="st0mut" x="24" y="232">容量用完没法原地变大：分配一块两倍大的新内存，把元素一个个移过去，放进新元素，再释放旧的。</text>
  <text class="st0mut" x="24" y="250">之前拿到的指针、引用、迭代器都还指着旧内存，全部失效。</text>
</svg>

搬家时用移动还是拷贝，取决于元素的移动构造函数是不是 `noexcept`。`push_back` 要保证搬到一半抛异常时，原来的 `vector` 完好无损；移动过的元素已经被掏空，退不回去，所以只有确定移动不会抛，它才敢移动，否则老老实实拷贝（`std::move_if_noexcept`）。**自己写的类，移动构造函数忘了标 `noexcept`，放进 `vector` 扩容时就会一个个深拷贝**。

事先知道大概要放多少个，就先 `reserve(n)`：实测 `reserve(1000)` 再 `push_back` 1000 次，容量一直是 1000，一次搬家都没有。

**均摊 O(1) 说的是平均，扩容的那一次是 O(n)，在延迟敏感的路径上就是一个尖峰。** 那一次要做三件事，每件都和元素个数成正比：

- **分配一块新内存**：大块内存（glibc 默认 128 KiB 以上）走 `mmap`，拿到的只是虚拟地址，第一次写每一页都要缺页，每页约 0.5–2 µs。
- **把旧元素搬过去**：100 万个 16 B 的元素是 16 MiB，光拷贝就要约 1–2 ms；新内存的 4000 来页缺页再加几 ms。
- **释放旧内存**：大块走 `munmap`，进程里正在跑的其他线程都要陪着处理一次 TLB shootdown（[进程和线程](/zh/ref/process-thread-fork/) 4.5）。

所以平时 `push_back` 每次几 ns，偶尔一次几 ms，P99.9 就被它拉高了。避免的办法都是同一个思路：**把扩容挪到热路径之外，或者干脆不让它发生。**

- **启动时 `reserve` 到上限，并把内存先碰一遍**：`reserve` 只分配不写，页还没真正拿到，第一次写进去照样缺页；启动时 `resize` 到上限再 `clear()`，或者逐页写一遍，缺页就都发生在启动阶段。
- **复用同一个 `vector`，不要每轮新建**：`clear()` 不还内存（1.4），下一轮接着用原来的容量，例如每个交易日、每批行情处理完 `clear()` 一下。
- **上限确定就用定长结构**：`std::array`、环形缓冲区，或者自己写一个固定容量的 `vector`，满了返回失败、丢数据并计数，而不是扩容。
- **必须能长，就换成不搬旧元素的结构**：`deque` 增长时只多分配一块，旧元素原地不动（2.1）；自己按块分配也行。
- **元素的移动构造标 `noexcept`**：扩容时就用移动而不是拷贝，那一次便宜很多，但仍然是 O(n)，只是减轻、不能消除尖峰。

### 1.3 迭代器失效：看内存有没有动 {#vector-invalidation}

迭代器、指针、引用本质上都是元素的地址，元素一挪地方它们就失效。`vector` 上有两种情况会挪：扩容时整块搬家，所有的都失效；没扩容时，`insert` 和 `erase` 要把后面的元素往后或往前挪一格，插入、删除位置之后的全部失效，之前的不受影响。

所以边遍历边删，要用 `erase` 的返回值接住下一个位置，而不是对已经失效的 `it` 做 `++`：

```cpp
std::vector<int> v{1, 2, 3, 4, 5, 6};
for (auto it = v.begin(); it != v.end();) {
    if (*it % 2 == 0) it = v.erase(it);   // erase 返回被删元素的下一个
    else ++it;
}
// v = 1 3 5
std::erase_if(v, [](int x) { return x % 2 == 0; });   // C++20 一句搞定
```

这种写法每删一个就把后面整体挪一次，删得多时是 O(n²)；`std::erase_if`（C++20 之前是 `remove_if` 加 `erase`）只把留下的元素往前挪一遍，O(n)。同样的循环写法对 `map`、`list` 也成立，实测删掉 `map` 里的偶数 key 后剩 `1 3`。

### 1.4 clear 不还内存，shrink_to_fit 才还 {#vector-shrink}

`clear()` 和 `resize(10)` 只是把 `end` 往回挪，容量不变，内存还占着。实测一个容量 1000 的 `vector`，`resize(10)` 以后容量仍是 1000，`shrink_to_fit()` 以后变成 10。标准只把 `shrink_to_fit` 定为“请求”，libstdc++ 的做法是分配一块刚好够的新内存、把元素搬过去。

`std::vector<bool>` 是个例外：它把每个 `bool` 压成 1 位，`v[i]` 返回的是一个代理对象而不是 `bool&`，所以拿不到元素的地址，也不能当普通容器用在要求真引用的地方。

## 2. deque、list、forward_list：不连续的几种

### 2.1 deque：一串固定大小的块 {#deque}

`deque` 想要两头都能 O(1) 插入，又保留下标访问。它把元素存在一个个固定大小的块里（libstdc++ 每块 512 字节，`int` 就是 128 个），再用一个中控数组（map）记各块的地址。`sizeof(std::deque<int>)` 是 80：中控数组的指针和大小，加上指向首尾的两个迭代器，每个迭代器自己要记 4 个指针。

<svg viewBox="0 0 760 266" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="deque 的中控数组有 5 格，中间 3 格指向 3 个固定大小的块；第一块右边 3 格有元素，第二块满，第三块左边 5 格有元素；push_front 往第一块左边的空位放，push_back 往第三块右边的空位放" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .st1bg  { fill: #fbfaf7; }
    .st1map { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .st1on  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.2; }
    .st1off { fill: none; stroke: #b9c2cc; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .st1ink { fill: #1c1b18; font-size: 12.5px; }
    .st1mut { fill: #6b6558; font-size: 12px; }
    .st1ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .st1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .st1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1map { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1on { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1off { stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1ink, :root:is([data-theme="dark"], [data-theme="black"]) .st1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st1hd { fill: #a19caf; }
  </style>
  <defs><marker id="st1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="st1hd"/></marker></defs>
  <rect class="st1bg" x="0" y="0" width="760" height="266" rx="10"/>
  <text class="st1ttl" x="40" y="38">中控数组 map</text>
  <text class="st1ttl" x="200" y="38">固定大小的块（libstdc++：512 字节一块）</text>
  <rect class="st1map" x="40" y="56" width="90" height="30"/>
  <text class="st1mut" x="85" y="76" text-anchor="middle">空</text>
  <rect class="st1map" x="40" y="88" width="90" height="30"/>
  <text class="st1ink" x="85" y="108" text-anchor="middle">块地址</text>
  <rect class="st1map" x="40" y="120" width="90" height="30"/>
  <text class="st1ink" x="85" y="140" text-anchor="middle">块地址</text>
  <rect class="st1map" x="40" y="152" width="90" height="30"/>
  <text class="st1ink" x="85" y="172" text-anchor="middle">块地址</text>
  <rect class="st1map" x="40" y="184" width="90" height="30"/>
  <text class="st1mut" x="85" y="204" text-anchor="middle">空</text>
  <path class="st1ln" d="M130,103 L197,103" marker-end="url(#st1a)"/>
  <path class="st1ln" d="M130,135 L197,135" marker-end="url(#st1a)"/>
  <path class="st1ln" d="M130,167 L197,167" marker-end="url(#st1a)"/>
  <rect class="st1off" x="200" y="90" width="34" height="26"/>
  <rect class="st1off" x="236" y="90" width="34" height="26"/>
  <rect class="st1off" x="272" y="90" width="34" height="26"/>
  <rect class="st1off" x="308" y="90" width="34" height="26"/>
  <rect class="st1off" x="344" y="90" width="34" height="26"/>
  <rect class="st1on" x="380" y="90" width="34" height="26"/>
  <rect class="st1on" x="416" y="90" width="34" height="26"/>
  <rect class="st1on" x="452" y="90" width="34" height="26"/>
  <rect class="st1on" x="200" y="122" width="34" height="26"/>
  <rect class="st1on" x="236" y="122" width="34" height="26"/>
  <rect class="st1on" x="272" y="122" width="34" height="26"/>
  <rect class="st1on" x="308" y="122" width="34" height="26"/>
  <rect class="st1on" x="344" y="122" width="34" height="26"/>
  <rect class="st1on" x="380" y="122" width="34" height="26"/>
  <rect class="st1on" x="416" y="122" width="34" height="26"/>
  <rect class="st1on" x="452" y="122" width="34" height="26"/>
  <rect class="st1on" x="200" y="154" width="34" height="26"/>
  <rect class="st1on" x="236" y="154" width="34" height="26"/>
  <rect class="st1on" x="272" y="154" width="34" height="26"/>
  <rect class="st1on" x="308" y="154" width="34" height="26"/>
  <rect class="st1on" x="344" y="154" width="34" height="26"/>
  <rect class="st1off" x="380" y="154" width="34" height="26"/>
  <rect class="st1off" x="416" y="154" width="34" height="26"/>
  <rect class="st1off" x="452" y="154" width="34" height="26"/>
  <text class="st1mut" x="504" y="107">push_front：放进这块左边的空位</text>
  <text class="st1mut" x="504" y="171">push_back：放进这块右边的空位</text>
  <text class="st1mut" x="40" y="236">块满了就再分配一块、在 map 里记一个地址，已有元素一个都不用搬，所以两端插入不让元素的引用失效。</text>
  <text class="st1mut" x="40" y="254">map 自己满了才扩容，搬的也只是这些地址。下标访问要两步：先算在第几块，再算块内第几个。</text>
</svg>

块大小固定，下标 `i` 换算成“第几块、块内第几个”只要一次除法和取余，所以 `d[i]` 仍是 O(1)，只是比 `vector` 多一次间接读。两端插入不搬已有元素，所以指向元素的引用和指针都还有效，但迭代器会失效：迭代器里记着中控数组的位置，中控数组可能已经换了一块。在中间插入要把一侧的元素整体挪一格，O(n)。`std::stack` 和 `std::queue` 默认就建在 `deque` 上。

### 2.2 list 和 forward_list：每个元素一个节点 {#list}

`std::list` 是双向链表：每个元素单独 `new` 一个节点，节点里除了元素还有 `prev`、`next` 两个指针。`sizeof(std::list<int>)` 是 24：一个哨兵节点的两个指针，加上一个计数（C++11 起 `size()` 必须是 O(1)，所以把个数存了下来）。`forward_list` 是单向链表，`sizeof` 只有 8，连 `size()` 都不提供，为的就是比手写的单链表不多花一个字节。

链表的长处是在已知位置插入、删除是 O(1)，而且不碰别的元素，所以除了被删的那个，迭代器永远有效；`splice` 能把节点从一个链表摘到另一个链表，不分配也不拷贝（[LRU 缓存](/zh/ref/lru-cache/)就靠它）。短处在内存：每个元素一次堆分配，节点散在堆上各处，顺序遍历时每走一步都可能是一次缓存未命中（[第 5 节](#pointer-chasing)）。`std::sort` 要随机访问迭代器，链表用不了，所以 `list` 自带一个成员函数 `sort()`，用归并排序。

## 3. map 和 set：红黑树 {#map}

`std::map`、`std::set` 是红黑树：每个元素一个节点，节点里有左、右、父三个指针和一个颜色。`sizeof(std::map<int,int>)` 是 48，放的是树头和元素个数。红黑树保证树高不超过 $2\log_2(n+1)$，所以查找、插入、删除都是 O(log n)，原理见[跳表、红黑树、B+ 树](/zh/ref/skiplist-rbtree-bplustree/)。

**它比哈希表多给的是顺序**：中序遍历就是按 key 从小到大，`lower_bound`、`upper_bound` 能找“第一个不小于 x 的”，范围查询是 O(log n + k)。节点式结构插入、删除不挪别的节点，旋转改的只是指针，所以和 `list` 一样，除了被删的那个，迭代器都不失效。`multimap`、`multiset` 是同一棵树，只是允许 key 重复。查找要从根一层层往下走，每层都要先把节点读回来才知道下一层在哪，这个代价见[第 5 节](#pointer-chasing)。

## 4. unordered_map：哈希桶

### 4.1 桶加链表 {#unordered-buckets}

`unordered_map` 有一个桶数组，key 按 `hash(key) % 桶数` 落进某个桶，同一个桶里的元素用链表串起来（叫拉链法）。key 分散得好时每个桶只有零到几个元素，查找平均 O(1)。

<svg viewBox="0 0 760 306" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="桶数为 13 的 unordered_map：key 按除以 13 的余数落进桶里；桶 0 串着 13 和 26，桶 1 是 1，桶 3 串着 3、16、29，桶 5 是 5，桶 2 和桶 4 空着" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .st2bg  { fill: #fbfaf7; }
    .st2bk  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .st2nd  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .st2ink { fill: #1c1b18; font-size: 12.5px; }
    .st2mut { fill: #6b6558; font-size: 12px; }
    .st2ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .st2ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .st2hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2bk { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2nd { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2ink, :root:is([data-theme="dark"], [data-theme="black"]) .st2ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .st2hd { fill: #a19caf; }
  </style>
  <defs><marker id="st2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="st2hd"/></marker></defs>
  <rect class="st2bg" x="0" y="0" width="760" height="306" rx="10"/>
  <text class="st2ttl" x="40" y="38">桶数组（13 个桶）</text>
  <text class="st2ttl" x="200" y="38">每个桶里的元素串成链表：key % 13 相同的落在一起</text>
  <rect class="st2bk" x="40" y="56" width="90" height="28"/>
  <text class="st2ink" x="85" y="75" text-anchor="middle">桶 0</text>
  <rect class="st2bk" x="40" y="86" width="90" height="28"/>
  <text class="st2ink" x="85" y="105" text-anchor="middle">桶 1</text>
  <rect class="st2bk" x="40" y="116" width="90" height="28"/>
  <text class="st2mut" x="85" y="135" text-anchor="middle">桶 2（空）</text>
  <rect class="st2bk" x="40" y="146" width="90" height="28"/>
  <text class="st2ink" x="85" y="165" text-anchor="middle">桶 3</text>
  <rect class="st2bk" x="40" y="176" width="90" height="28"/>
  <text class="st2mut" x="85" y="195" text-anchor="middle">桶 4（空）</text>
  <rect class="st2bk" x="40" y="206" width="90" height="28"/>
  <text class="st2ink" x="85" y="225" text-anchor="middle">桶 5</text>
  <text class="st2mut" x="85" y="252" text-anchor="middle">……</text>
  <rect class="st2nd" x="200" y="58" width="70" height="24" rx="4"/>
  <text class="st2ink" x="235" y="75" text-anchor="middle">13</text>
  <rect class="st2nd" x="310" y="58" width="70" height="24" rx="4"/>
  <text class="st2ink" x="345" y="75" text-anchor="middle">26</text>
  <rect class="st2nd" x="200" y="88" width="70" height="24" rx="4"/>
  <text class="st2ink" x="235" y="105" text-anchor="middle">1</text>
  <rect class="st2nd" x="200" y="148" width="70" height="24" rx="4"/>
  <text class="st2ink" x="235" y="165" text-anchor="middle">3</text>
  <rect class="st2nd" x="310" y="148" width="70" height="24" rx="4"/>
  <text class="st2ink" x="345" y="165" text-anchor="middle">16</text>
  <rect class="st2nd" x="420" y="148" width="70" height="24" rx="4"/>
  <text class="st2ink" x="455" y="165" text-anchor="middle">29</text>
  <rect class="st2nd" x="200" y="208" width="70" height="24" rx="4"/>
  <text class="st2ink" x="235" y="225" text-anchor="middle">5</text>
  <path class="st2ln" d="M130,70 L197,70" marker-end="url(#st2a)"/>
  <path class="st2ln" d="M270,70 L307,70" marker-end="url(#st2a)"/>
  <path class="st2ln" d="M130,100 L197,100" marker-end="url(#st2a)"/>
  <path class="st2ln" d="M130,160 L197,160" marker-end="url(#st2a)"/>
  <path class="st2ln" d="M270,160 L307,160" marker-end="url(#st2a)"/>
  <path class="st2ln" d="M380,160 L417,160" marker-end="url(#st2a)"/>
  <path class="st2ln" d="M130,220 L197,220" marker-end="url(#st2a)"/>
  <text class="st2mut" x="510" y="165">桶 3 有 3 个：查 29 要比较 3 次</text>
  <text class="st2mut" x="40" y="280">元素个数超过 桶数 × max_load_factor（默认 1.0）就 rehash：换一个大约两倍大的桶数组，</text>
  <text class="st2mut" x="40" y="298">每个节点按新桶数重新挂一遍。节点本身不动，所以引用和指针还有效，迭代器失效。</text>
</svg>

libstdc++ 的实际做法比图上多一层：所有节点串在同一条单链表上，同一个桶的节点在链上挨着，桶里存的是“指向本桶第一个节点的前一个节点”的指针。这样从头到尾遍历整个容器只是沿着这条链走，不用一个个桶去扫空桶。`sizeof(std::unordered_map<int,int>)` 是 56。

### 4.2 负载因子和 rehash {#rehash}

平均每个桶几个元素叫负载因子（load factor），超过上限 `max_load_factor`（默认 1.0）就 rehash。往一个空 `unordered_map` 里依次插 2000 个 key，实测桶数的变化是：

```text
1 → 13（第 1 个）→ 29（第 14 个）→ 59（第 30 个）→ 127（第 60 个）
  → 257（第 128 个）→ 541（第 258 个）→ 1109（第 542 个）→ 2357（第 1110 个）
```

每次大约翻倍，而且都取质数，让 `% 桶数` 更均匀。rehash 要把所有节点重新挂一遍，是一次 O(n) 的停顿，和 `vector` 扩容一样靠倍增摊成均摊 O(1)。**rehash 只改指针、不搬节点，所以引用和指针不失效，迭代器失效**：实测插入 1000 个 key、经历多次 rehash 之前拿到的 `int& ref = u[1]`，之后读出来仍是原值。事先知道大小就 `reserve(n)`，一次把桶数开够。

### 4.3 哈希不好，就退化成链表 {#bad-hash}

平均 O(1) 的前提是 key 能均匀落进各个桶。libstdc++ 的 `std::hash<int>` 就是 key 本身，桶数取质数才不怕 key 有规律；可要是自定义的哈希函数把很多 key 算成同一个值，它们全挤在一个桶里，查找退化成 O(n)。故意构造冲突 key 让服务端哈希表退化，就是哈希洪泛攻击，所以对外的服务常用带随机种子的哈希。`std::pair` 没有默认的 `std::hash`，拿它当 key 要自己写哈希，常见做法是把两个成员的哈希值用乘法和异或混合起来，而不是简单相加（`(1,2)` 和 `(2,1)` 会撞）。

## 5. pointer chasing：节点式容器慢在哪 {#pointer-chasing}

### 5.1 pointer chasing：下一次读的地址，要等这一次读回来 {#chasing-what}

`vector` 读 `v[i]`，地址是 `begin + i * sizeof(T)`，用寄存器里的数一算就有。所以顺序读 `v[0]`、`v[1]`、`v[2]` 时，CPU 不用等前一次读回来，就能把后面好几次读一起发出去；硬件预取器看出“地址每次加 4”的规律，还会提前去取后面的缓存行。

链表走到下一个节点，要读的是 `node->next`：下一个节点的地址存在当前节点里，当前节点没读回来，下一次读连地址都不知道。这种每一步的地址都要靠上一步读回来的访问，叫 **pointer chasing**（指针追逐）。它的时间只能一步一步往上加：

$$\text{总时间} \approx \text{依赖的步数} \times \text{一次访存的延迟}$$

节点不在缓存里时，一次访存就是一次 DRAM 访问，约 80–100 ns。**走 10 步就是 1 µs，CPU 能同时发出多少次读、内存带宽有多大，都帮不上忙。** 预取也帮不上：要提前取下一个节点，得先知道它的地址，而这个地址正是要等的东西。同时在路上的读为什么能重叠、依赖链为什么不能，见[内存延迟与带宽 1.4](/zh/posts/low-latency-memory-latency-bandwidth/)。

### 5.2 各个容器一次操作要跳几步 {#chasing-steps}

`list`、`map`、`set`、`unordered_map` 都是节点式容器：每个元素单独分配一个节点，节点之间靠指针连起来，所以它们的操作都是在顺着指针走。

| 容器和操作 | 依赖的读有几步 | 每一步在做什么 |
|---|---|---|
| `vector` 的 `v[i]`、顺序遍历 | 0 | 地址由下标算出，多次读可以同时进行 |
| `deque` 的 `d[i]` | 1 | 先从中控数组读出块的地址，再读元素；中控数组很小，通常在缓存里 |
| `list` 顺序遍历 | 每个元素 1 步 | 每个节点读回来，才知道下一个在哪 |
| `list` 走到第 k 个 | k 步 | 所以 2.2 说的 O(1) 插入，前面往往先要 O(n) 地走到那个位置 |
| `map`、`set` 的 `find` | 树高，100 万个元素时 20 多步 | 每层读出节点、比较 key，才知道往左还是往右 |
| `map`、`set` 顺序遍历 | 每个元素 1 到几步 | 找中序的下一个，要么往右子树走到最左，要么往上回到父节点 |
| `unordered_map` 的 `find` | 命中桶里第一个节点要 3 步，每多一个冲突加 1 步 | 读桶数组 → 读“本桶第一个节点的前一个节点”（4.1）→ 读节点、比较 key |
| `unordered_map` 顺序遍历 | 每个元素 1 步 | 沿着那条串起所有节点的单链表走 |

`map` 的 `find` 最典型。O(log n) 看着不错，可那 20 多步每一步都是一次依赖的读。树上面几层被访问得多，通常在缓存里；越往下节点越多，越难留在缓存里，后面十来层每层都可能是一次 DRAM 访问，一次查找就是几百 ns 到 1 µs 以上。

### 5.3 节点为什么散在堆上，又为什么占地方 {#chasing-scatter}

节点式容器每插入一个元素就 `malloc` 一次，节点之间夹着程序在别处分配的东西。`map` 的节点按插入的先后分配，在树里的位置却按 key 排；`unordered_map` rehash 以后，链表的顺序也变了。所以逻辑上相邻的两个节点，在内存里几乎从不相邻，每走一步都可能落在一条新的缓存行上。

节点还占地方，因为每个元素都背着几个指针。GCC 16.2 实测的节点大小：

| 容器 | 一个节点 | 节点里有什么 |
|---|---|---|
| `std::list<int>` | 24 B | `prev`、`next` 两个指针，加 4 B 的 `int` 和对齐填充 |
| `std::map<int, int>` | 40 B | 颜色、父、左、右共 32 B，加 8 B 的 `pair` |
| `std::unordered_map<int, int>` | 16 B | 一个 `next` 指针，加 8 B 的 `pair` |
| `std::unordered_map<std::string, int>` | 56 B | `next` 指针、32 B 的 `string`、`int`，再加一个缓存下来的哈希值 |

`malloc` 还要在每块前面加 8 B 的头，再按 16 B 取整，所以 `map<int, int>` 的一个节点实际占 48 B。同样是 100 万个 `int → int`，排好序的 `vector<pair<int, int>>` 是 8 MB，`map` 是 48 MB：前者还可能大半留在 L3 里，后者基本只能去 DRAM 读。**节点式容器慢在两处：每一步都要等上一步，而且每读一条缓存行，有用的数据只有一点点。**

测量时有一个坑：基准测试里先连续插入、再立刻查找，`malloc` 往往从一块新内存里一个挨一个地切出节点，节点碰巧是连续的，测出来比真实程序好看。真实程序里，节点和别的分配交错在一起，经过反复增删以后才是散的。所以测节点式容器，要打乱插入顺序、在插入之间穿插别的分配，或者直接在真实负载上测。

### 5.4 怎么避免：让数据连续，或者让节点挨在一起 {#chasing-fix}

- **按位置或按顺序访问，就用 `vector`**：顺序遍历没有依赖的读，预取器还会提前去取。
- **要有序查找、元素又不常改，就用排好序的连续数组加二分**：直接对 `vector` 用 `std::lower_bound`，或者用 C++23 的 `std::flat_map`（Boost 里有 `boost::container::flat_map`），它把 key 和 value 分别存在两个排好序的连续数组里。二分每一步读哪个位置也要看上一步的比较结果，但数组紧凑，大半在缓存里，而且不用先读出一个指针。代价是插入、删除要挪元素，是 O(n)。
- **只按 key 查，就用开放寻址的哈希表**：`absl::flat_hash_map`、`boost::unordered_flat_map` 把元素直接存在一个连续的槽数组里，冲突时看相邻的槽，查找通常 1–2 次访存。代价是 rehash 时元素会搬家，引用会失效，这正是标准不允许 `std::unordered_map` 这么做的原因（4.2）。
- **key 的集合固定，就不用哈希**：比如合约代码，启动时把每个代码映射成 0 到 N−1 的编号，之后直接拿编号索引数组，一次访存。
- **必须用节点式容器，就让节点从一块连续内存里分配**：给容器配一个内存池或 arena 分配器，比如 `std::pmr::monotonic_buffer_resource`。节点按分配顺序挨在一起，每一步仍然要等上一步，但更多步会落在同一条缓存行、或者已经在缓存里的行上，还省掉了每次 `malloc`。做法见[热路径内存分配器](/zh/posts/hot-path-memory-allocators/)。

## 6. 适配器、string 和 sort

### 6.1 priority_queue：vector 上的二叉堆 {#priority-queue}

`priority_queue` 不是独立的容器，而是在 `vector` 上维护一个二叉堆：下标 `i` 的子节点是 `2i+1`、`2i+2`，父节点的值总不小于子节点（默认大顶堆）。`top()` 是 O(1)，`push`、`pop` 各要沿树往上或往下调整一条路径，O(log n)。数据存在连续数组里，没有指针，这也是它比用 `set` 模拟优先队列快的原因。要小顶堆，第三个模板参数传 `std::greater<T>`。

### 6.2 string 的短字符串优化 {#sso}

libstdc++ 的 `sizeof(std::string)` 是 32：指针、长度，再加一块 16 字节的内部缓冲。不超过 15 个字符的字符串直接放在这块缓冲里，不碰堆，叫短字符串优化（SSO）；实测空字符串的 `capacity()` 就是 15。所以大量短字符串的创建、拷贝不会触发内存分配；代价是移动一个短字符串也得把这几个字节拷一遍，不能只交换指针。

### 6.3 std::sort：内省排序 {#sort}

`std::sort` 是内省排序（introsort）：主体是快速排序；递归太深（超过约 $2\log_2 n$ 层，说明枢轴一直选得很差）就改用堆排序，保证最坏也是 O(n log n)；区间小到 16 个元素以下，最后统一用插入排序收尾。它要求随机访问迭代器，而且不稳定，相等元素的先后可能变；要保持原顺序用 `std::stable_sort`（归并排序）。

## 7. 怎么选 {#choose}

| 容器 | 底层 | 按位置访问 | 查找 | 中间插入、删除 | 什么时候迭代器失效 |
|---|---|---|---|---|---|
| `vector` | 连续数组 | O(1) | O(n)，排好序可二分 | O(n) | 扩容时全部；否则插入、删除点之后的 |
| `deque` | 中控数组加固定块 | O(1) | O(n) | 两端 O(1)，中间 O(n) | 任何插入；引用在两端插入时不失效 |
| `list` | 双向链表 | O(n) | O(n) | 已知位置 O(1) | 只有被删的那个 |
| `map` / `set` | 红黑树 | — | O(log n)，有序 | O(log n) | 只有被删的那个 |
| `unordered_map` | 桶加链表 | — | 平均 O(1)，无序 | 平均 O(1) | rehash 时全部（引用不失效）；否则只有被删的 |

**默认用 `vector`。** 连续内存对缓存最友好，几千个元素以内，中间插入要挪一半元素，也往往比链表“只改两个指针”还快，因为链表那 O(1) 之前先要 O(n) 地一个个节点走到插入位置。真正适合 `list` 的，是手里已经握着节点位置、要频繁在中间摘挂节点，并且需要别的迭代器不失效的场景，比如 LRU。

`map` 和 `unordered_map` 之间看要不要顺序：要按 key 排序遍历、要找“比 x 大的第一个”、要范围查询，用 `map`；只按 key 查，用 `unordered_map`，平均 O(1)，但要付 rehash 的停顿和哈希函数的质量风险，而且每个节点也是一次堆分配。key 很少（几十个以内）时，排好序的 `vector` 加二分查找常常比两者都快。
