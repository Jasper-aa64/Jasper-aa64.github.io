---
title: "new 一次走到哪：operator new、malloc、brk/mmap 和缺页"
date: 2026-11-02
slug: "new-malloc-page-fault"
description: "写一行 new，内存要过好几层才真正到手：编译器把 new 拆成 operator new 加构造函数；operator new 调 glibc 的 malloc；malloc 先在本线程的 tcache 和 arena 的空闲链表里找，不够才用 brk 推高堆顶，大块直接 mmap；内核这时只登记了一段地址，物理页要等第一次写、触发缺页才分配并清零。再讲 delete 之后内存回到哪、为什么 RSS 不降，overcommit 下 new 为什么几乎不抛 bad_alloc，以及第一次用慢的几种通用办法。"
summary: "new 拿到的是地址，不是内存。malloc 大多数时候在自己手里的空闲块里就找到了，进内核的 brk、mmap 也只是登记一段地址；物理页要等第一次写才由缺页分配，每页一次，每次约 0.5–2 µs。所以第一遍写一块新内存比第二遍慢，delete 之后 RSS 不降也不等于泄漏。"
toc: true
group: cpplinux
weight: 108
aliases: ["/posts/new-malloc-page-fault/"]
---

`Widget* p = new Widget(42);` 看起来是一步，其实要过好几层才拿到能用的内存：标准库、glibc 的分配器、内核，最后还有 CPU 的缺页异常。每一层只在自己手里不够时才往下一层要，所以绝大多数 `new` 在用户态几十 ns 以内就返回了，偶尔一次要进内核；而真正的物理内存，要等你第一次往里写才分配。地址空间里堆、mmap 区各在哪，可以对照[进程地图](/maps/process-map.zh.html)看。

## 1. new 表达式：先要内存，再构造对象

### 1.1 new 表达式（new-expression）：编译器拆成两步

new 表达式要做两件事：拿一块够大的内存，在上面调构造函数。编译器把它展开成大致这样的代码（类自己重载了 `operator new`，就调类里的那个）：

```cpp
#include <new>

struct Widget { int v; explicit Widget(int v) : v(v) {} };

Widget* make() {
    // Widget* p = new Widget(42); 大致等于：
    void* mem = ::operator new(sizeof(Widget));   // 1. 拿内存，失败抛 std::bad_alloc
    try {
        return ::new (mem) Widget(42);            // 2. 在这块内存上调构造函数
    } catch (...) {
        ::operator delete(mem);                   // 构造抛了异常：内存还回去，再往外抛
        throw;
    }
}

void destroy(Widget* p) {
    // delete p; 大致等于：
    p->~Widget();                                 // 1. 析构
    ::operator delete(p);                         // 2. 还内存
}
```

要拆成两步，是因为构造函数可能抛异常。这时内存已经拿到了，对象却没建成，调用者手里连指针都没有，这块内存只能由编译器生成的这段代码还回去。`delete p` 反过来，先析构，再还内存。

**你能替换的是第一步：`operator new` 只管要多少字节，不知道要建的是什么对象。** placement new 正好相反，跳过第一步，只做第二步（7.1 节）。

数组版多一个细节。`new Widget[n]` 遇到有非平凡析构函数的类型，会在数组前面多要 8 字节记下 n，`delete[]` 靠它知道要析构几个对象。所以 `new[]` 配 `delete`、`new` 配 `delete[]` 都是未定义行为：一个不知道前面有这 8 字节，一个会去读一个不存在的计数。

### 1.2 operator new：一层薄壳，调 malloc，拿不到就抛

libstdc++ 里默认的 `operator new` 很短，大致是：

```cpp
void* operator new(std::size_t sz) {
    if (sz == 0) sz = 1;                      // new 0 字节也要返回一个独一无二的地址
    void* p;
    while ((p = std::malloc(sz)) == nullptr) {
        std::new_handler h = std::get_new_handler();
        if (!h) throw std::bad_alloc();       // 没装处理函数：抛异常
        h();                                  // 装了：给程序一次腾内存的机会，再试
    }
    return p;
}
```

`malloc` 返回空指针时，它先看程序有没有用 `std::set_new_handler` 装过处理函数。装了就调一下，让程序有机会释放一些缓存，然后再试；没装就抛 `std::bad_alloc`。`new (std::nothrow) Widget` 调的是另一个版本，失败时返回 `nullptr`，不抛异常。

**所以 C++ 里 new 出来的内存最终都是向 malloc 要的，new 快不快，基本就是 malloc 快不快。** 下面这张图是整条路，越往下越贵，也越少走到：

<svg viewBox="0 0 760 350" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="一次 new 经过的五层：new 表达式、operator new、malloc 都在用户态，大多数请求在 malloc 这一层返回；不够才用 brk 或 mmap 进内核要一段地址；物理页要等第一次写触发缺页才分配" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .nw0bg  { fill: #fbfaf7; }
    .nw0u   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .nw0k   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .nw0ink { fill: #1c1b18; font-size: 12.5px; }
    .nw0mut { fill: #6b6558; font-size: 12px; }
    .nw0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .nw0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .nw0hd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0u { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0k { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0ink, :root:is([data-theme="dark"], [data-theme="black"]) .nw0ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw0hd { fill: #a19caf; }
  </style>
  <defs><marker id="nw0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="nw0hd"/></marker></defs>
  <rect class="nw0bg" x="0" y="0" width="760" height="350" rx="10"/>
  <rect class="nw0u" x="24" y="16" width="320" height="46" rx="6"/>
  <text class="nw0ttl" x="38" y="36">① new 表达式</text>
  <text class="nw0mut" x="38" y="54">编译器把它拆成两步</text>
  <text class="nw0ink" x="372" y="34">先调 operator new 拿一块够大的内存，</text>
  <text class="nw0ink" x="372" y="52">再在这块内存上调构造函数。</text>
  <rect class="nw0u" x="24" y="78" width="320" height="46" rx="6"/>
  <text class="nw0ttl" x="38" y="98">② operator new</text>
  <text class="nw0mut" x="38" y="116">标准库里的一层薄壳</text>
  <text class="nw0ink" x="372" y="96">调 malloc；拿不到就调 new_handler，</text>
  <text class="nw0ink" x="372" y="114">没装 handler 就抛 std::bad_alloc。</text>
  <rect class="nw0u" x="24" y="140" width="320" height="46" rx="6"/>
  <text class="nw0ttl" x="38" y="160">③ malloc（glibc）</text>
  <text class="nw0mut" x="38" y="178">先在自己手里的空闲块里找</text>
  <text class="nw0ink" x="372" y="158">tcache、空闲链表、堆顶还没切的那块：</text>
  <text class="nw0ink" x="372" y="176">大多数请求在这一层返回，约 10–100 ns。</text>
  <rect class="nw0k" x="24" y="202" width="320" height="46" rx="6"/>
  <text class="nw0ttl" x="38" y="222">④ 内核：brk / mmap</text>
  <text class="nw0mut" x="38" y="240">手里不够了才进内核要</text>
  <text class="nw0ink" x="372" y="220">推高堆顶，或者新映射一段：一次系统调用，</text>
  <text class="nw0ink" x="372" y="238">内核只登记一段地址，还没有物理页。</text>
  <rect class="nw0k" x="24" y="264" width="320" height="46" rx="6"/>
  <text class="nw0ttl" x="38" y="284">⑤ 第一次写：缺页</text>
  <text class="nw0mut" x="38" y="302">这时才分配物理页</text>
  <text class="nw0ink" x="372" y="282">CPU 查页表发现没有这一页，进内核分配一页、</text>
  <text class="nw0ink" x="372" y="300">清零、填页表，再重做这次写：每页约 0.5–2 µs。</text>
  <path class="nw0ln" d="M184,62 L184,76" marker-end="url(#nw0a)"/>
  <path class="nw0ln" d="M184,124 L184,138" marker-end="url(#nw0a)"/>
  <path class="nw0ln" d="M184,186 L184,200" marker-end="url(#nw0a)"/>
  <path class="nw0ln" d="M184,248 L184,262" marker-end="url(#nw0a)"/>
  <text class="nw0mut" x="24" y="336">绿框在用户态，只是函数调用；红框要进内核。越往下越贵，也越少走到。</text>
</svg>

## 2. malloc：先在自己手里的空闲块里找

### 2.1 chunk（块）：每块前面有 8 字节的头

glibc 的分配器（ptmalloc）把内存切成一个个 chunk。每个 chunk 前面有 8 字节记着它的大小和几个标志位，`malloc` 返回的指针指向这个头的后面。大小按 16 字节对齐，最小 32 字节：`malloc(1)` 实际占 32 字节，`malloc(24)` 也是 32 字节，`malloc(25)` 就变成 48 字节。

**大小记在块头里，所以 `free(p)` 不用你告诉它这块多大：往前读 8 字节就知道。** 反过来，写越界会把下一块的头写坏，等这块被 free 时 glibc 检查出大小对不上，直接 abort，报出 `free(): invalid next size` 这类错误。崩溃的地方是 free，写坏的地方却在更早。

### 2.2 找的顺序：tcache、空闲链表、top chunk

free 掉的块不还给内核，而是按大小挂在各种空闲链表（bin）上，等下一次 malloc 来取。malloc 从便宜的地方往贵的地方找。

第一站是 tcache（thread cache，glibc 2.26 起有）。它是每个线程自己的一组小链表，按 16 字节一档，覆盖到约 1 KiB 的块，每档最多存 7 块。因为只有本线程会碰它，取和放都不用加锁，几条指令就完成。一个循环里反复 new、delete 同样大小的对象，几乎每次都在这里命中。

tcache 里没有，才去 arena 的空闲链表里找。小块有 fastbin（不和相邻的空闲块合并，取放快）和 smallbin，大块在 largebin 里按大小排好，刚 free 的块先进 unsorted bin，等下一次 malloc 顺手分拣。这一层要拿 arena 的锁，可能还要把大块切小、把相邻的空闲块合并，比 tcache 慢一截。

空闲链表里都没有合适的，就从 top chunk 切。top chunk 是堆最顶上还没被切过的一整块，够大就从它头上切一块下来返回。

**这三站都在用户态，不进内核：大多数 malloc 在这里就返回了。** 只有 top chunk 也不够大，才要去找内核。

<svg viewBox="0 0 760 436" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="malloc 找内存的顺序：不小于 128 KiB 的请求直接 mmap；否则先查本线程的 tcache，再查 arena 的空闲链表，再从 top chunk 切，都不够才进内核用 brk 或扩展 heap" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .nw1bg  { fill: #fbfaf7; }
    .nw1u   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .nw1k   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .nw1g   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .nw1ink { fill: #1c1b18; font-size: 12.5px; }
    .nw1mut { fill: #6b6558; font-size: 12px; }
    .nw1ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .nw1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .nw1hd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1u { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1k { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1g { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1ink, :root:is([data-theme="dark"], [data-theme="black"]) .nw1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw1hd { fill: #a19caf; }
  </style>
  <defs><marker id="nw1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="nw1hd"/></marker></defs>
  <rect class="nw1bg" x="0" y="0" width="760" height="436" rx="10"/>
  <rect class="nw1g" x="24" y="16" width="280" height="40" rx="6"/>
  <text class="nw1ttl" x="38" y="41">malloc(n)</text>
  <rect class="nw1g" x="24" y="76" width="280" height="40" rx="6"/>
  <text class="nw1ink" x="38" y="101">n ≥ 128 KiB 吗？</text>
  <rect class="nw1k" x="360" y="70" width="376" height="52" rx="6"/>
  <text class="nw1ttl" x="374" y="91">是：单独 mmap 一段，按页取整</text>
  <text class="nw1mut" x="374" y="110">阈值叫 M_MMAP_THRESHOLD；free 时直接 munmap</text>
  <rect class="nw1u" x="24" y="150" width="280" height="52" rx="6"/>
  <text class="nw1ttl" x="38" y="171">tcache：本线程的小缓存</text>
  <text class="nw1mut" x="38" y="190">按大小分档，每档最多 7 块，不加锁</text>
  <rect class="nw1u" x="24" y="226" width="280" height="52" rx="6"/>
  <text class="nw1ttl" x="38" y="247">arena 的空闲链表（要加锁）</text>
  <text class="nw1mut" x="38" y="266">fastbin、smallbin、largebin……</text>
  <rect class="nw1u" x="24" y="302" width="280" height="52" rx="6"/>
  <text class="nw1ttl" x="38" y="323">top chunk：堆顶还没切的那块</text>
  <text class="nw1mut" x="38" y="342">够大就从头上切一块</text>
  <rect class="nw1k" x="24" y="378" width="712" height="44" rx="6"/>
  <text class="nw1ttl" x="38" y="396">都不够：进内核要一段地址</text>
  <text class="nw1mut" x="38" y="413">主 arena 用 brk 推高堆顶，其他 arena 扩展自己那段 heap：一次系统调用</text>
  <path class="nw1ln" d="M164,56 L164,74" marker-end="url(#nw1a)"/>
  <path class="nw1ln" d="M304,96 L358,96" marker-end="url(#nw1a)"/>
  <text class="nw1mut" x="324" y="89">是</text>
  <path class="nw1ln" d="M164,116 L164,148" marker-end="url(#nw1a)"/>
  <text class="nw1mut" x="172" y="137">否</text>
  <path class="nw1ln" d="M164,202 L164,224" marker-end="url(#nw1a)"/>
  <path class="nw1ln" d="M164,278 L164,300" marker-end="url(#nw1a)"/>
  <path class="nw1ln" d="M164,354 L164,376" marker-end="url(#nw1a)"/>
  <text class="nw1mut" x="172" y="217">没有</text>
  <text class="nw1mut" x="172" y="293">没有</text>
  <text class="nw1mut" x="172" y="369">不够</text>
  <path class="nw1ln" d="M304,176 L326,176" marker-end="url(#nw1a)"/>
  <text class="nw1ink" x="334" y="172">找到就返回：约 10–20 ns，最常见</text>
  <text class="nw1mut" x="334" y="190">反复 new、delete 同样大小的对象，几乎都停在这里</text>
  <path class="nw1ln" d="M304,252 L326,252" marker-end="url(#nw1a)"/>
  <text class="nw1ink" x="334" y="248">找到就返回：要拿锁，可能还要切分、合并</text>
  <text class="nw1mut" x="334" y="266">几十 ns 到一两百 ns</text>
  <path class="nw1ln" d="M304,328 L326,328" marker-end="url(#nw1a)"/>
  <text class="nw1ink" x="334" y="324">切下来返回：仍然在用户态</text>
  <text class="nw1mut" x="334" y="342">top chunk 不够大，才往下走</text>
</svg>

### 2.3 arena（分配区）：线程多了不抢同一把锁

如果所有线程共用一套空闲链表，就得共用一把锁，线程一多就排队。glibc 的办法是开多个 arena：主线程用 main arena，别的线程碰上锁被占着，就新建或换到另一个 arena，之后一直用它。64 位上最多开到核数的 8 倍。每个 arena 有自己的锁和空闲链表，线程之间大多不再抢。

代价是内存更分散：线程 A 的 arena 里空着的块，线程 B 用不上。所以线程多的程序，RSS（实际占用的物理内存）常常比真正在用的多出不少，这时可以用 `MALLOC_ARENA_MAX` 环境变量限制 arena 的个数。**tcache 管“不加锁”，arena 管“锁不扎堆”，两层叠起来，多线程下的小块分配才便宜。**

## 3. 向内核要：brk 和 mmap

### 3.1 brk：小块不够时推高堆顶

main arena 的堆紧挨在 `.bss` 上面，往高地址长（见[进程地图的各段](/zh/ref/cpp-linux/#segments)）。堆顶的位置叫 program break，`brk` 系统调用就是把它往上推。top chunk 不够时，malloc 调一次 `brk`，推高的量是这次要的大小再加 128 KiB 余量（`M_TOP_PAD`），按页取整。

多推 128 KiB，是因为一次系统调用要几百 ns 到 1 µs，比在用户态切一块贵得多。多要一点，后面几十上百次小分配都从这块余量里切，不用再进内核。用 `strace` 看一个程序，开头常能看到这样一对调用：

```text
brk(NULL)                = 0x55d0c2a3e000     // 问当前堆顶在哪
brk(0x55d0c2a5f000)      = 0x55d0c2a5f000     // 往上推 132 KiB
```

其他 arena 不能用 brk，因为一个进程只有一个堆顶。它们先用 mmap 占一段 64 MiB 的地址当自己的 heap，要用多少再改成可读写多少。

### 3.2 mmap：大块单独映射

请求不小于 `M_MMAP_THRESHOLD`（默认 128 KiB）时，malloc 不碰堆，直接 `mmap` 一段匿名内存，大小按页取整；`free` 时 `munmap`，立刻还给内核。

大块单独映射，是因为放在堆里不好还。堆只能从顶上用 brk 往回缩，大块在堆中间被 free，留下的洞还不回去。单独映射的块用完整段还掉，不留洞。但每次 mmap、munmap 都是系统调用，还回去的页下次再要，又得重新缺页、清零。所以这个阈值是动态的：free 一个 mmap 来的块时，glibc 把阈值提高到这块的大小（64 位上最高 32 MiB），以后同样大小的请求改从堆里分，反复分配、释放同样大小的大块，就不用每次都进内核。用 `mallopt(M_MMAP_THRESHOLD, n)` 显式设过阈值，这个自动调整就关掉了。

**阈值以上单独 mmap，free 就还给内核；阈值以下从堆里切，free 了留着自己用。**

### 3.3 内核这时只登记了一段地址

不管 brk 还是 mmap，内核做的都只是改进程的内存区域表（VMA，`vm_area_struct`），记下“这一段地址合法、可读写、是匿名内存”。它没有分配物理页，也没有填页表。所以 `malloc(1 << 30)` 一下就返回了，RSS 一点没涨。

**new 拿到的是一段地址，不是内存。** 物理页要等下面这一步。

## 4. 第一次写：缺页才拿到物理页

### 4.1 缺页（page fault）：CPU 查不到，就进内核补上

程序第一次往 `p[0]` 写，CPU 拿虚拟地址查页表（先查 TLB，见[硬件地图](/zh/ref/cpu-memory/)），发现这一页没有映射，于是触发缺页异常，自动切进内核。内核按地址找到它所在的 VMA，确认是合法的匿名内存，就分配一个物理页、把 4 KiB 清零、填好页表项，再回到用户态，重新执行那条写指令。这一次查得到了，写成功。

清零这一步省不掉：这个物理页上一刻可能还属于别的进程，不清零就会把别人的数据交给你。也正因为内核保证新页全是 0，`calloc` 拿到的如果是刚 mmap 来的内存，就不用再 memset 一遍，比 `malloc` 加 `memset` 省一遍写。

<svg viewBox="0 0 760 304" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="一次缺页：new 只返回地址；第一次写某一页时 CPU 查页表查不到，同一个线程切进内核，找到 VMA、分配物理页、清零、填页表，再回到用户态重做这次写；同一页后面的访问不再缺页" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .nw2bg  { fill: #fbfaf7; }
    .nw2u   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .nw2k   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .nw2ink { fill: #1c1b18; font-size: 12.5px; }
    .nw2mut { fill: #6b6558; font-size: 12px; }
    .nw2ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .nw2ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .nw2sep { stroke: #b9c2cc; stroke-width: 1.2; stroke-dasharray: 5 4; fill: none; }
    .nw2hd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2u { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2k { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2ink, :root:is([data-theme="dark"], [data-theme="black"]) .nw2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2sep { stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .nw2hd { fill: #a19caf; }
  </style>
  <defs><marker id="nw2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="nw2hd"/></marker></defs>
  <rect class="nw2bg" x="0" y="0" width="760" height="304" rx="10"/>
  <text class="nw2mut" x="24" y="32">用户态：你的线程</text>
  <rect class="nw2u" x="24" y="44" width="150" height="56" rx="6"/>
  <text class="nw2ttl" x="36" y="67">new char[n]</text>
  <text class="nw2mut" x="36" y="87">只拿到地址，返回 p</text>
  <rect class="nw2u" x="190" y="44" width="150" height="56" rx="6"/>
  <text class="nw2ttl" x="202" y="67">写 p[0]</text>
  <text class="nw2mut" x="202" y="87">查页表：没有这一页</text>
  <rect class="nw2u" x="440" y="44" width="140" height="56" rx="6"/>
  <text class="nw2ttl" x="452" y="67">重做这次写</text>
  <text class="nw2mut" x="452" y="87">这次查到了，成功</text>
  <rect class="nw2u" x="596" y="44" width="140" height="56" rx="6"/>
  <text class="nw2ttl" x="608" y="67">同一页后面的写</text>
  <text class="nw2mut" x="608" y="87">不再缺页，普通访存</text>
  <path class="nw2sep" d="M24,116 L736,116"/>
  <text class="nw2ttl" x="24" y="186">内核</text>
  <text class="nw2mut" x="24" y="206">同一个线程，</text>
  <text class="nw2mut" x="24" y="222">切到了内核态</text>
  <rect class="nw2k" x="190" y="164" width="130" height="56" rx="6"/>
  <text class="nw2ttl" x="202" y="187">找 VMA</text>
  <text class="nw2mut" x="202" y="207">是 new 来的地址</text>
  <rect class="nw2k" x="334" y="164" width="120" height="56" rx="6"/>
  <text class="nw2ttl" x="346" y="187">分配一页</text>
  <text class="nw2mut" x="346" y="207">拿一个物理页</text>
  <rect class="nw2k" x="468" y="164" width="120" height="56" rx="6"/>
  <text class="nw2ttl" x="480" y="187">清零 4 KiB</text>
  <text class="nw2mut" x="480" y="207">不留别人的数据</text>
  <rect class="nw2k" x="602" y="164" width="134" height="56" rx="6"/>
  <text class="nw2ttl" x="614" y="187">填页表项</text>
  <text class="nw2mut" x="614" y="207">回到用户态</text>
  <path class="nw2ln" d="M174,72 L188,72" marker-end="url(#nw2a)"/>
  <path class="nw2ln" d="M265,100 L265,162" marker-end="url(#nw2a)"/>
  <text class="nw2mut" x="273" y="142">缺页异常</text>
  <path class="nw2ln" d="M320,192 L332,192" marker-end="url(#nw2a)"/>
  <path class="nw2ln" d="M454,192 L466,192" marker-end="url(#nw2a)"/>
  <path class="nw2ln" d="M588,192 L600,192" marker-end="url(#nw2a)"/>
  <path class="nw2ln" d="M669,164 L669,140 L510,140 L510,102" marker-end="url(#nw2a)"/>
  <path class="nw2ln" d="M580,72 L594,72" marker-end="url(#nw2a)"/>
  <text class="nw2ink" x="24" y="258">写到下一页再缺一次：每 4 KiB 一次，每次约 0.5–2 µs；1 GiB 就是 262144 次。</text>
  <text class="nw2ink" x="24" y="282">地址不在任何 VMA 里（空指针、越界太远）：走同一个入口，内核发 SIGSEGV。</text>
</svg>

同一页后面的 4095 个字节再写，页表里已经有了，不再缺页；写到下一页，又缺一次。**缺页按页算，每页一次，每次约 0.5–2 µs，大部分花在进出内核和清零上。** 地址如果不在任何 VMA 里（空指针、越界太远），走的是同一个入口，只是内核查不到 VMA，就给进程发 SIGSEGV。

还有个细节：匿名内存如果先读后写，第一次读时内核不分配新页，而是把一个全局共享的全零页只读地映射给你；等你真的写，再缺一次页，这时才复制出自己的一页。这和 fork 之后的写时复制是同一套机制（见[进程、线程和 fork](/zh/ref/process-thread-fork/)）。

### 4.2 第一次用为什么慢

把这些连起来，一块新 new 出来的大缓冲区，第一遍写比第二遍慢得多：第一遍每 4 KiB 都要进一次内核，1 GiB 就是 262144 次缺页，加起来零点几秒；第二遍页表都填好了，只剩普通的访存。

**慢的不是 new，而是 new 之后第一次碰每一页。** 这也解释了一个常见的现象：`std::vector<char> v(n)` 构造就很慢，因为它要把 n 个元素初始化成 0，构造时就把每页写了一遍；`new char[n]` 不初始化，所以构造很快，慢被推迟到第一次使用。

大页能把次数降下来。透明大页（THP）开着时，2 MiB 对齐的匿名区域可以一次缺页拿到一个 2 MiB 的页，缺页次数少 512 倍。每次要清零的内存也多了 512 倍，但进出内核的次数省下来了。

### 4.3 在自己机器上看

下面这个程序 new 256 MiB，在 new 之后、写满之后、delete 之后，分别打印 RSS 和到这时为止的次缺页（minor fault）次数（Linux）：

```cpp
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <sys/resource.h>

long rss_kib() {                         // /proc/self/status 里的 VmRSS，单位 KiB
    std::ifstream f("/proc/self/status");
    for (std::string line; std::getline(f, line);)
        if (line.rfind("VmRSS:", 0) == 0) return std::atol(line.c_str() + 6);
    return -1;
}

long minor_faults() {                    // 进程到现在为止的次缺页次数
    rusage ru;
    getrusage(RUSAGE_SELF, &ru);
    return ru.ru_minflt;
}

int main(int argc, char**) {
    const std::size_t n = 256u << 20;    // 256 MiB，远超 128 KiB，malloc 走 mmap
    std::printf("开始       RSS %7ld KiB  缺页 %ld\n", rss_kib(), minor_faults());
    char* p = new char[n];               // 不初始化：只拿地址
    std::printf("new 之后   RSS %7ld KiB  缺页 %ld\n", rss_kib(), minor_faults());
    std::memset(p, argc, n);             // 每页第一次写
    std::printf("写满之后   RSS %7ld KiB  缺页 %ld  (p[n-1] = %d)\n",
                rss_kib(), minor_faults(), p[n - 1]);
    delete[] p;                          // mmap 来的，free 时直接 munmap
    std::printf("delete 后  RSS %7ld KiB  缺页 %ld\n", rss_kib(), minor_faults());
}
```

`memset` 写的值取 `argc`、最后再读一个字节打印出来，是为了不让编译器发现这块内存没人用、把整段分配优化掉。

预期看到：new 之后 RSS 和缺页次数几乎不变；写满之后 RSS 涨 262144 KiB 左右，缺页多出约 65536 次（256 MiB ÷ 4 KiB），THP 开着时会少得多；delete 之后 RSS 掉回去，因为 256 MiB 远超阈值，这块是单独 mmap 的，free 时直接 munmap 了。

用 strace 跑同一个程序，前面一串 mmap 是动态链接器在加载 `.so`，最后能看到这一对映射和解除映射。大小比 256 MiB 多出一页，是 chunk 头按页取整多出来的：

```text
$ strace -e trace=mmap,munmap ./a.out
...
mmap(NULL, 268439552, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0) = 0x7f…
munmap(0x7f…, 268439552)                = 0
```

`perf stat -e page-faults ./a.out` 报出的总缺页数里，也会有这 65536 次左右。

## 5. delete：内存回到哪

### 5.1 小块回到空闲链表，不还给内核

`delete` 析构之后调 `free`。小块 free 时先放进本线程的 tcache，满了再挂回 arena 的空闲链表，和相邻的空闲块合并成大块。这些内存还在进程手里，页也还映射着，所以 RSS 不降。

只有两种情况会真的还给内核。一是堆顶那块空闲的超过 `M_TRIM_THRESHOLD`（默认 128 KiB，随 mmap 阈值动态变成它的 2 倍）时，free 用 brk 把堆顶往回缩。二是手动调 `malloc_trim(0)`，glibc 还会对堆中间整页空着的地方调 `madvise(MADV_DONTNEED)`，把物理页还掉、地址留着。brk 只能从顶上缩，堆顶附近夹着一个还在用的小块，它下面空出来的一大片就缩不回去，这就是碎片让 RSS 降不下来的原因。

**RSS 不降不等于泄漏：分配器只是把空闲块留着下次用。** 判断泄漏要看 RSS 是不是随着时间一直涨，或者用 ASan、Valgrind 这类工具查哪些块一直没被 free。

### 5.2 大块直接 munmap

mmap 来的大块 free 时直接 munmap，地址和物理页一起还给内核，RSS 立刻降。下次再要同样大小，就得重新 mmap、重新缺页。mmap 阈值会随着 free 往上调，就是为了让反复出现的大块改走堆，省掉这一来一回。

## 6. 内存不够时：bad_alloc 和 OOM killer

### 6.1 overcommit（超额分配）：malloc 几乎不会失败

既然 brk、mmap 只登记地址，内核就可以答应比实际物理内存更多的请求，赌大部分不会真的被写满。Linux 默认 `vm.overcommit_memory = 0`，只拒绝明显不可能的单次请求（比如一次要的比内存加交换区还大），其他都答应。

所以在默认设置下，`new` 很少因为内存不够而抛 `std::bad_alloc`：它在 new 那一刻已经成功了，真正缺内存是后来某次缺页时，内核找不到物理页可给。这时没有异常可抛，因为缺页发生在一条普通的写指令上，程序里没有哪个调用可以返回失败。内核只能启动 OOM killer，按每个进程的 `oom_score` 挑一个杀掉（SIGKILL），被杀的也未必是你的进程。

**默认设置下，内存不够的表现不是 new 抛异常，而是某个进程被 OOM killer 杀掉，`dmesg` 里留一行 `Out of memory: Killed process ...`。**

### 6.2 bad_alloc 什么时候真的会抛

想让 new 在要不到时如实失败，就得让内核在登记地址时就记账。`vm.overcommit_memory = 2` 是严格模式：所有进程答应出去的总量不能超过交换区加上物理内存的一定比例（`vm.overcommit_ratio`，默认 50%），超了 brk、mmap 直接失败，malloc 返回空指针，new 抛 `bad_alloc`。

默认模式下也有几种情况会抛。进程用 `ulimit -v`（`RLIMIT_AS`）限制了地址空间大小，地址先用完了；或者要的大小本身离谱，比如长度算错成一个巨大的数。`new T[n]` 里 n 大到 `n * sizeof(T)` 溢出时，抛的是它的子类 `std::bad_array_new_length`。

## 7. 第一次用慢：把代价挪到前面

malloc 偶尔要进内核，每页第一次写要缺页，这两笔开销都只在“第一次”发生。程序如果需要“第一次用和以后一样快”，通用的办法都是把这些代价挪到启动时一次付清。

### 7.1 placement new：内存要一次，对象可以建很多次

new 表达式拆成拿内存和构造两步，placement new 只做第二步：在你给的内存上构造对象，不分配。

```cpp
#include <cstdio>
#include <new>

struct Point {
    double x, y;
    Point(double x, double y) : x(x), y(y) { std::puts("构造"); }
    ~Point() { std::puts("析构"); }
};

int main() {
    alignas(Point) unsigned char buf[sizeof(Point)];   // 一块够大、对齐的内存
    Point* p = new (buf) Point(1, 2);                   // 只构造，不分配
    std::printf("%.0f %.0f\n", p->x, p->y);
    p->~Point();                                        // 只析构，不释放
    p = new (buf) Point(3, 4);                          // 同一块内存再建一个
    p->~Point();
}
```

placement new 建出来的对象不能 `delete`，因为那块内存不是 `operator new` 给的；要显式调析构函数，内存由你自己管。对象池就是这么做的：启动时要一大块内存，切成等大的槽；要用时从空闲槽里拿一个，placement new；不用了就析构，把槽挂回空闲链表。之后反复建、删对象，都不再碰 malloc。完整的对象池和 arena 实现见[内存池与分配器](/zh/posts/hot-path-memory-allocators/)。

### 7.2 预先缺页：启动时把每页写一遍

内存拿到了，物理页还没有。启动时把整块按页写一遍（每 4 KiB 写一个字节，或者整块 memset），缺页就在启动时发生完；也可以在 mmap 时加 `MAP_POPULATE`，让内核当场把页都分配好。再用 `mlock` 锁住，这些页就不会被换出到交换区，之后也不会因为换回来而再缺页。

**预先缺页之后，这块内存的每一次访问都是普通的访存，和第二遍一样快。** 代价是启动变慢，RSS 一开始就占满。

### 7.3 大页和换分配器

开透明大页，或者对这段内存 `madvise(MADV_HUGEPAGE)`，缺页次数少 512 倍，TLB 也更少 miss：一个 TLB 项管 2 MiB，而不是 4 KiB。如果慢在多线程的 malloc 本身，可以换成 jemalloc、tcmalloc 这类线程缓存更大、跨线程释放处理得更好的分配器，通常只要链接时换一个库，或者用 `LD_PRELOAD` 预加载，不用改代码。
