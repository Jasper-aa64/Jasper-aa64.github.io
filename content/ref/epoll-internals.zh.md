---
title: "epoll：红黑树、就绪链表和回调"
date: 2026-11-02
slug: "epoll-internals"
description: "一个线程要同时等几千个连接，select 和 poll 每次调用都把全部 fd 交给内核挨个查一遍。epoll 把“登记”和“等待”拆开：登记的 fd 放进内核里的一棵红黑树，只有 epoll_ctl 会碰它；登记时在每个 socket 上挂一个回调，数据到了，回调顺着指针把这一项挂上就绪链表；epoll_wait 只看这条链表。再讲水平触发和边缘触发的差别、每一步进不进内核、epoll 为什么算同步 IO，以及想再省还有哪些办法。"
summary: "epoll 在内核里有三样东西：红黑树记着关注哪些 fd，只给 epoll_ctl 用；就绪链表记着哪些 fd 现在有事，回调往里挂，epoll_wait 从里取；等待队列记着谁睡在 epoll_wait 里。事件来的时候不查树，靠的是登记时挂在 socket 上的那个指针。所以连接再多，每一圈事件循环的开销只看真正有事件的那几个；但每一次 epoll_wait、每一次 recv 仍然是一次系统调用。"
toc: true
group: cpplinux
weight: 109
aliases: ["/posts/epoll-internals/"]
---

一个 Web 服务器或者聊天服务，同时连着几千个客户端。给每个连接开一个线程、阻塞在 `recv` 上，线程数一多，每个线程的栈、每次切换的开销都扛不住。所以服务端的常见写法是：一个线程同时等很多个连接，哪个有数据就处理哪个。这就要回答一个问题：怎么便宜地知道，几千个连接里此刻是哪几个有数据。这篇从 `select` 的问题讲起，再进内核看 epoll 是怎么做到只处理有事件的那几个的。

## 1. 一个线程等很多个连接

### 1.1 IO 多路复用（I/O multiplexing）：一次问清哪些 fd 就绪了

最笨的办法是把每个 socket 设成非阻塞，在循环里挨个 `recv`：没数据的返回 `EAGAIN`，有数据的就处理。可每个 `recv` 都是一次系统调用，几千个连接里通常只有几个有数据，绝大多数调用白跑一趟。

所以要换个问法：用一次调用把一批 fd 交给内核，问它“这里面哪些可以读了”，内核答完再只对那几个 `recv`。这就是 IO 多路复用，`select`、`poll`、`epoll` 都是它的实现，差别在每次问的代价。

### 1.2 select 和 poll：每次调用都把要关注的 fd 全交一遍

`poll` 的典型写法：

```cpp
std::vector<pollfd> fds = /* 每个连接一项，events = POLLIN */;
for (;;) {
    poll(fds.data(), fds.size(), -1);   // 整个数组拷进内核，内核逐个检查
    for (auto& p : fds)                 // 回来以后自己再扫一遍
        if (p.revents & POLLIN) handle(p.fd);
}
```

每调一次，内核要做这几件事：把整个数组从用户态拷进来；对每个 fd 调一次它的 `poll` 方法，问它就绪没有，顺便在它的等待队列上挂一个等待项，这样之后不管哪个 fd 来了数据，都能把睡着的这个线程叫醒；一个都没就绪就睡；被叫醒以后再逐个查一遍，把挂上的等待项一个个摘掉；最后把结果拷回去，用户还得再扫一遍数组才知道是哪几个。`select` 一样，只是用位图代替数组：内核从 0 扫到最大的那个 fd 号，只对位是 1 的 fd 调 `poll`，所以开销跟着最大的 fd 号走，而且 fd 号不能超过 1023（位图只有 `FD_SETSIZE` = 1024 位）。

问题在于，这些步骤每一步都和关注的 fd 总数 n 成正比，和这次就绪的个数无关。连着一万个连接、此刻只有十个有数据，每次调用照样做一万份活。**select 和 poll 每次都在重新登记全部 fd，开销跟着连接数涨，而不是跟着事件数涨。**

### 1.3 epoll：登记一次，以后只问就绪的

既然关注哪些 fd 很少变，就没必要每次都交一遍。epoll 把这件事拆成三个调用：

```cpp
int ep = epoll_create1(EPOLL_CLOEXEC);      // 建一个 epoll 实例，它本身也是一个 fd

epoll_event ev{};
ev.events = EPOLLIN | EPOLLET;               // 关心可读，边缘触发（3.3）
ev.data.fd = conn;                           // 事件回来时原样带回，用来认出是哪个连接
epoll_ctl(ep, EPOLL_CTL_ADD, conn, &ev);     // 登记一次

epoll_event evs[64];
for (;;) {
    int n = epoll_wait(ep, evs, 64, -1);     // 只返回就绪的，一次最多 64 个
    for (int i = 0; i < n; ++i)
        drain(evs[i].data.fd);               // 读到 EAGAIN 为止（3.3）
}
```

`epoll_ctl` 在连接建立、关闭时各调一次，`epoll_wait` 每一圈调一次，返回的数组里只有就绪的那几个。下面这张图对比两者每次调用要做的事：

<svg viewBox="0 0 760 236" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="select 和 poll 每次调用都要拷贝、检查、摘除全部 n 个 fd；epoll_wait 每次只看就绪链表，处理就绪的 k 个" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .e0bg  { fill: #fbfaf7; }
    .e0n   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .e0k   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .e0g   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .e0ink { fill: #1c1b18; font-size: 12.5px; }
    .e0mut { fill: #6b6558; font-size: 12px; }
    .e0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .e0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .e0hd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0n { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0k { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0g { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0ink, :root:is([data-theme="dark"], [data-theme="black"]) .e0ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e0hd { fill: #a19caf; }
  </style>
  <defs><marker id="e0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="e0hd"/></marker></defs>
  <rect class="e0bg" x="0" y="0" width="760" height="236" rx="10"/>
  <text class="e0ttl" x="24" y="30">select / poll：每调一次</text>
  <rect class="e0n" x="24" y="44" width="128" height="48" rx="6"/>
  <text class="e0ink" x="36" y="64">n 个 fd</text>
  <text class="e0ink" x="36" y="82">拷进内核</text>
  <rect class="e0n" x="172" y="44" width="150" height="48" rx="6"/>
  <text class="e0ink" x="184" y="64">逐个问就绪没有，</text>
  <text class="e0ink" x="184" y="82">挂等待项（n 次）</text>
  <rect class="e0g" x="342" y="44" width="110" height="48" rx="6"/>
  <text class="e0ink" x="354" y="64">没就绪就睡，</text>
  <text class="e0ink" x="354" y="82">等人叫醒</text>
  <rect class="e0n" x="472" y="44" width="134" height="48" rx="6"/>
  <text class="e0ink" x="484" y="64">逐个再查一遍，</text>
  <text class="e0ink" x="484" y="82">摘等待项（n 次）</text>
  <rect class="e0n" x="626" y="44" width="110" height="48" rx="6"/>
  <text class="e0ink" x="638" y="64">拷回去，用户</text>
  <text class="e0ink" x="638" y="82">再扫一遍（n）</text>
  <path class="e0ln" d="M152,68 L170,68" marker-end="url(#e0a)"/>
  <path class="e0ln" d="M322,68 L340,68" marker-end="url(#e0a)"/>
  <path class="e0ln" d="M452,68 L470,68" marker-end="url(#e0a)"/>
  <path class="e0ln" d="M606,68 L624,68" marker-end="url(#e0a)"/>
  <text class="e0ttl" x="24" y="128">epoll_wait：每调一次（登记早在 epoll_ctl 时做完了）</text>
  <rect class="e0k" x="24" y="142" width="128" height="48" rx="6"/>
  <text class="e0ink" x="36" y="162">看一眼</text>
  <text class="e0ink" x="36" y="180">就绪链表</text>
  <rect class="e0g" x="172" y="142" width="150" height="48" rx="6"/>
  <text class="e0ink" x="184" y="162">空的：睡，</text>
  <text class="e0ink" x="184" y="180">等回调叫醒</text>
  <rect class="e0k" x="342" y="142" width="264" height="48" rx="6"/>
  <text class="e0ink" x="354" y="162">不空：只处理链上的 k 个，</text>
  <text class="e0ink" x="354" y="180">拷 k 个事件回去</text>
  <path class="e0ln" d="M152,166 L170,166" marker-end="url(#e0a)"/>
  <path class="e0ln" d="M322,166 L340,166" marker-end="url(#e0a)"/>
  <text class="e0mut" x="24" y="218">n = 关注的连接数，k = 这一次就绪的个数。红框的活跟着 n 涨，绿框的活跟着 k 涨；连接多、活跃的少时，k 远小于 n。</text>
</svg>

能这样省，是因为内核替你记住了关注哪些 fd，并且在每个 fd 上留好了“有数据时通知谁”。下面进内核看这两样是怎么放的。

## 2. 内核里的三样东西

一个 epoll 实例在内核里是一个 `struct eventpoll`，里面最重要的是三样：一棵红黑树、一条就绪链表、一个等待队列。被关注的 socket 那边，还挂着一个指回来的等待项。先看全图，后面三节一样一样讲：

<svg viewBox="0 0 760 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="epoll 的内核结构：用户线程通过 epoll_ctl 改红黑树，通过 epoll_wait 取就绪链表；数据到达时软中断唤醒 socket 的等待队列，等待项上的回调顺着指针把 epitem 挂到就绪链表尾，再叫醒睡在 epoll 等待队列里的线程" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .e1bg  { fill: #fbfaf7; }
    .e1usr { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .e1krn { fill: #f7f4ee; stroke: #d6cfc2; stroke-width: 1.2; }
    .e1box { fill: #ffffff; stroke: #8c8577; stroke-width: 1.3; }
    .e1ep  { fill: #fdf8ec; stroke: #c9a85c; stroke-width: 1.5; }
    .e1sk  { fill: #eaf2fb; stroke: #7aa2cf; stroke-width: 1.5; }
    .e1nd  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .e1hot { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .e1ink { fill: #1c1b18; font-size: 12.5px; }
    .e1mut { fill: #6b6558; font-size: 11.5px; }
    .e1ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .e1num { fill: #b4532f; font-size: 13px; font-weight: 700; }
    .e1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .e1hl  { stroke: #b4532f; stroke-width: 1.6; fill: none; }
    .e1dash{ stroke: #8c8577; stroke-width: 1.2; fill: none; stroke-dasharray: 5 4; }
    .e1hd  { fill: #6b6558; }
    .e1hdr { fill: #b4532f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1usr { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1krn { fill: #1e1c1a; stroke: #3e3a33; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1box { fill: #26231f; stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1ep { fill: #2b2617; stroke: #9c8240; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1sk { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1nd { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1hot { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1ink, :root:is([data-theme="dark"], [data-theme="black"]) .e1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1num { fill: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1hl { stroke: #f0a07a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1dash { stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1hd { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e1hdr { fill: #f0a07a; }
  </style>
  <defs>
    <marker id="e1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="e1hd"/></marker>
    <marker id="e1r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="e1hdr"/></marker>
  </defs>
  <rect class="e1bg" x="0" y="0" width="760" height="430" rx="10"/>
  <rect class="e1usr" x="16" y="16" width="728" height="64" rx="8"/>
  <text class="e1ttl" x="28" y="38">用户态</text>
  <rect class="e1box" x="110" y="30" width="220" height="38" rx="6"/>
  <text class="e1ink" x="122" y="54">epoll_ctl(ADD / MOD / DEL)</text>
  <rect class="e1box" x="400" y="30" width="150" height="38" rx="6"/>
  <text class="e1ink" x="412" y="54">epoll_wait(…)</text>
  <path class="e1dash" d="M16,92 L744,92"/>
  <text class="e1mut" x="744" y="88" text-anchor="end">系统调用：同一个线程切到内核态</text>
  <rect class="e1krn" x="16" y="100" width="728" height="314" rx="8"/>
  <text class="e1ttl" x="28" y="122">内核态</text>
  <rect class="e1ep" x="32" y="134" width="448" height="264" rx="8"/>
  <text class="e1ttl" x="44" y="156">eventpoll（一个 epoll 实例）</text>
  <text class="e1mut" x="44" y="180">红黑树：关注的全部 fd（epitem）</text>
  <path class="e1ln" d="M132,212 L92,250 M132,212 L172,250 M92,250 L116,288 M172,250 L148,288"/>
  <circle class="e1nd" cx="132" cy="212" r="15"/><text class="e1ink" x="132" y="217" text-anchor="middle">7</text>
  <circle class="e1nd" cx="92" cy="250" r="15"/><text class="e1ink" x="92" y="255" text-anchor="middle">3</text>
  <circle class="e1nd" cx="172" cy="250" r="15"/><text class="e1ink" x="172" y="255" text-anchor="middle">12</text>
  <circle class="e1nd" cx="116" cy="288" r="15"/><text class="e1ink" x="116" y="293" text-anchor="middle">5</text>
  <circle class="e1nd" cx="148" cy="288" r="15"/><text class="e1ink" x="148" y="293" text-anchor="middle">9</text>
  <text class="e1mut" x="44" y="326">按（file, fd）排序；</text>
  <text class="e1mut" x="44" y="342">只有 epoll_ctl 和关闭文件时碰它</text>
  <text class="e1mut" x="236" y="180">就绪链表 rdllist</text>
  <rect class="e1box" x="236" y="192" width="70" height="30" rx="5"/>
  <text class="e1ink" x="246" y="212">rdllist</text>
  <rect class="e1hot" x="322" y="192" width="52" height="30" rx="5"/>
  <text class="e1ink" x="334" y="212">fd 3</text>
  <rect class="e1hot" x="390" y="192" width="52" height="30" rx="5"/>
  <text class="e1ink" x="402" y="212">fd 7</text>
  <path class="e1ln" d="M306,207 L320,207" marker-end="url(#e1a)"/>
  <path class="e1ln" d="M374,207 L388,207" marker-end="url(#e1a)"/>
  <text class="e1mut" x="236" y="242">链上是现在有事的 epitem，和树里</text>
  <text class="e1mut" x="236" y="258">是同一个对象，多一个链节 rdllink</text>
  <text class="e1mut" x="236" y="292">等待队列 wq：睡在 epoll_wait 里的线程</text>
  <rect class="e1box" x="236" y="304" width="132" height="30" rx="5"/>
  <text class="e1ink" x="248" y="324">线程 A（睡着）</text>
  <text class="e1mut" x="44" y="384">树给 epoll_ctl 用，链表给 epoll_wait 用，wq 记着谁在等。</text>
  <rect class="e1sk" x="504" y="134" width="224" height="170" rx="8"/>
  <text class="e1ttl" x="516" y="156">socket（fd 7）</text>
  <rect class="e1box" x="516" y="168" width="200" height="30" rx="5"/>
  <text class="e1ink" x="528" y="188">接收缓冲区</text>
  <text class="e1mut" x="516" y="220">socket 的等待队列：</text>
  <rect class="e1box" x="516" y="228" width="200" height="62" rx="5"/>
  <text class="e1ink" x="528" y="248">epoll 登记时挂的等待项</text>
  <text class="e1mut" x="528" y="266">回调 = ep_poll_callback</text>
  <text class="e1mut" x="528" y="282">能直接找回 fd 7 的 epitem</text>
  <rect class="e1box" x="504" y="330" width="224" height="68" rx="8"/>
  <text class="e1ink" x="516" y="352">网卡 → 中断 → 软中断</text>
  <text class="e1mut" x="516" y="370">把数据放进接收缓冲区，</text>
  <text class="e1mut" x="516" y="386">唤醒 socket 的等待队列</text>
  <path class="e1ln" d="M220,68 L220,110 L132,110 L132,132" marker-end="url(#e1a)"/>
  <text class="e1mut" x="140" y="128">增删改：按 fd 查树，O(log n)</text>
  <path class="e1hl" d="M616,330 L616,306" marker-end="url(#e1r)"/>
  <text class="e1num" x="624" y="322">①</text>
  <path class="e1hl" d="M516,258 L492,258 L492,207 L445,207" marker-end="url(#e1r)"/>
  <text class="e1num" x="474" y="256">②</text>
  <path class="e1hl" d="M516,280 L492,280 L492,319 L370,319" marker-end="url(#e1r)"/>
  <text class="e1num" x="474" y="306">③</text>
  <path class="e1hl" d="M416,192 L416,150 L475,150 L475,70" marker-end="url(#e1r)"/>
  <text class="e1num" x="483" y="112">④</text>
</svg>

红色箭头是一个包到达以后的路：① 软中断把数据放进 socket，唤醒它的等待队列；② 等待项上的回调顺着指针找到 fd 7 的 epitem，挂到就绪链表尾；③ 再叫醒睡在 `epoll_wait` 里的线程；④ 线程醒来，从就绪链表取走事件，回到用户态。灰色箭头是 `epoll_ctl`，它只改树。

### 2.1 eventpoll：一个 epoll 实例也是一个文件

`epoll_create1` 返回的是一个 fd，背后是一个匿名文件，文件的私有数据就是 `eventpoll`：

```c
struct eventpoll {                  // 内核里的结构，删减过
    struct mutex          mtx;      // 改树时拿：会睡眠的锁
    wait_queue_head_t     wq;       // 睡在 epoll_wait 里的线程
    struct list_head      rdllist;  // 就绪链表
    rwlock_t              lock;     // 保护就绪链表：不睡眠的锁，软中断里也能拿
    struct rb_root_cached rbr;      // 红黑树：关注的全部 fd
    struct epitem        *ovflist;  // epoll_wait 正在拷贝时，新就绪的先临时挂这里（3.2）
};
```

两把锁分开，是因为两种操作在完全不同的场合发生：改树发生在 `epoll_ctl` 里，是普通的进程上下文，可以睡眠，用互斥锁；往就绪链表上挂发生在软中断里，不能睡眠，只能用自旋式的锁。**树和就绪链表各用各的锁，软中断里的回调就不必等改树的人。**

因为 epoll 实例本身是文件，它也能被另一个 epoll 关注（嵌套），也能被 `close` 掉；关掉它，整棵树和上面的等待项都会被拆掉。

### 2.2 epitem 和红黑树：只在 epoll_ctl 时用

每关注一个 fd，内核就建一个 `epitem`，挂在红黑树上，按（`file` 指针，fd）排序：

```c
struct epitem {                     // 删减过
    struct rb_node      rbn;        // 挂在红黑树上
    struct list_head    rdllink;    // 就绪时挂进就绪链表用的链节
    struct epoll_filefd ffd;        // 关注的是哪个 file、哪个 fd：树按这个排序
    struct eppoll_entry *pwqlist;   // 挂在被关注文件的等待队列上的等待项（2.3）
    struct eventpoll   *ep;         // 属于哪个 epoll 实例
    struct epoll_event  event;      // 关心哪些事件，和用户给的 data
};
```

树只在这些时候被碰：

| 什么时候 | 在树上做什么 |
|---|---|
| `epoll_ctl(ADD)` | 先按（file, fd）查一遍，已经有了就返回 `EEXIST`；没有就插入新节点 |
| `epoll_ctl(MOD)` | 查到这一项，改它关心的事件 |
| `epoll_ctl(DEL)` | 查到这一项，删掉 |
| 被关注的文件彻底关闭 | 内核自动把它从树里删掉 |

最后一行有个细节：自动删除发生在这个打开的文件没有任何引用的时候。fd 被 `dup` 过、或者 `fork` 以后子进程还开着，`close` 掉你这一个 fd 并不会让它离开 epoll，它可能继续报事件，报回来的却是一个你已经关掉的 fd 号。所以稳妥的写法是先 `EPOLL_CTL_DEL`，再 `close`。

用红黑树，是因为 `epoll_ctl` 要按 fd 找到对应的那一项，而一个 epoll 实例可能管着几万个连接：查重、修改、删除都要 O(log n)，不能挨个扫。**红黑树解决的是“按 fd 找到这一项”，这件事只有 epoll_ctl 需要；事件到达时不查它。**

### 2.3 登记时挂的回调：socket 的等待队列

事件来的时候不查树，那怎么知道是哪一项？答案在 `epoll_ctl(ADD)` 多做的一步。Linux 里每个能被等待的文件（socket、管道、eventfd……）都有一个等待队列：谁想在它有数据时被叫醒，就往这个队列上挂一个等待项，等待项里记着一个回调函数。ADD 时，epoll 调这个 socket 的 `poll` 方法，顺手往它的等待队列上挂了一项：

```c
// epoll_ctl(ADD) 里做的事，示意
epi = 新建一个 epitem;  插进红黑树;
revents = 调这个文件的 poll 方法(file, &pt);
//   socket 的 poll 方法里会调 poll_wait(file, socket 的等待队列, &pt)，
//   epoll 借这个机会分配一个等待项：回调函数设成 ep_poll_callback，
//   等待项和 epi 放在一起，从等待项能直接找回 epi；然后挂进 socket 的等待队列
if (revents 里有关心的事件)            // 登记时就已经可读了
    把 epi 挂上就绪链表，叫醒等待的线程;
```

最后两行也是个细节：给一个已经有数据的 fd 做 ADD，不用等下一个包，下一次 `epoll_wait` 就会报它。

`select` 和 `poll` 其实也走同一套机制，只是它们每次调用都挂一遍、返回前再摘一遍（1.2 的红框）。epoll 把这个等待项长期留在 socket 上，直到 DEL 或文件关闭。**epoll 省下的，就是把“挂等待项”从每次调用挪到了登记那一次。**

## 3. 一个包到达以后

### 3.1 软中断里：回调顺着指针把 epitem 挂上就绪链表

网卡收到包，发中断，内核在软中断里跑协议栈，把数据放进 socket 的接收缓冲区，然后唤醒这个 socket 的等待队列：队列上的每一个等待项，依次调它的回调。epoll 挂的那一项被调到时，执行的是这个函数：

```c
static int ep_poll_callback(wait_queue_entry_t *wait, unsigned mode, int sync, void *key) {
    struct epitem *epi = ep_item_from_wait(wait);   // 等待项 → 它属于的 epitem：指针，O(1)
    struct eventpoll *ep = epi->ep;
    if (!(epi->event.events & key_to_poll(key)))    // 来的不是关心的事件，不管
        return 0;
    if (ep 正在被 epoll_wait 拷贝)                   // 3.2：先挂到临时的 ovflist
        挂进 ep->ovflist;
    else if (!ep_is_linked(epi))                    // 还没在就绪链表上，才挂上去
        list_add_tail(&epi->rdllink, &ep->rdllist);
    wake_up(&ep->wq);                               // 叫醒一个睡在 epoll_wait 里的线程
    return 1;
}
```

整个过程没有查树，也没有遍历任何东西：从 socket 到等待项、从等待项到 epitem、从 epitem 到 eventpoll，全是指针。这里也不能查树：回调跑在软中断里不能睡眠，而改树要拿的 `mtx` 是会睡眠的锁。**事件到达时，epoll 的开销是常数：几次指针跳转，加一次链表插入。**

这段代码跑在处理网卡中断的那个核上：中断交给哪个核，软中断、回调和唤醒就都从哪个核发起，被叫醒的线程可能在另一个核上。

### 3.2 epoll_wait：只看就绪链表

`epoll_wait` 进内核以后，也不碰树，只和就绪链表打交道：

```c
// epoll_wait 里取事件，示意
if (rdllist 是空的) {
    timeout == 0 ? 直接返回 0 : 挂进 ep->wq 睡觉，等回调叫醒或超时;
}
把 rdllist 整条摘下来，记作 txlist;      // 拷贝期间新就绪的，回调先挂到 ovflist
for (epi : txlist，最多 maxevents 个) {
    revents = 再调一次这个文件的 poll 方法;   // 再问一次：现在真的就绪吗？
    if (!revents) continue;              // 数据已经被别的线程读走了，这一项丢掉
    拷一个 epoll_event 给用户;            // events + 当初登记的 data
    if (EPOLLONESHOT)   停掉这一项，要 MOD 才重新打开;
    else if (!EPOLLET)  放回 rdllist;      // 水平触发：下次还会再查一次（3.3）
}
把 ovflist 上的挂回 rdllist;
```

整条摘下来再处理，是为了不在整个拷贝过程里一直占着链表的锁：拷事件到用户态可能缺页、可能慢，期间软中断里的回调照样能往 `ovflist` 上挂，互不耽误。

拿到事件前再问一次，是因为从回调挂上链表到 `epoll_wait` 来取，中间可能已经过了一段时间：别的线程可能已经把数据读走了，这一项就不该再报。

**epoll_wait 的开销只和这一次就绪的个数有关，和关注了多少个 fd 无关。**这就是图一里绿框的意思。

### 3.3 水平触发和边缘触发（LT / ET）：一项报完要不要放回去

3.2 代码里那句“放回 rdllist”，就是两种触发方式的全部差别：

- 水平触发（level-triggered，默认）：报完放回链表。下次 `epoll_wait` 再问一遍这个 socket，只要缓冲区里还有数据，就再报一次。
- 边缘触发（edge-triggered，`EPOLLET`）：报完不放回。要等回调再挂一次，也就是有新数据到达，才会再报。

差别在你没把数据读完的时候显出来。假设一个连接来了 4 KiB，你每次只读 1 KiB：

<svg viewBox="0 0 760 236" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="来了 4 KiB、每次只读 1 KiB 时：水平触发每次 epoll_wait 都报；边缘触发报一次以后，剩下的 3 KiB 一直没人管，直到 2 KiB 新数据到达才再报" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .e2bg  { fill: #fbfaf7; }
    .e2ink { fill: #1c1b18; font-size: 12.5px; }
    .e2mut { fill: #6b6558; font-size: 11.5px; }
    .e2ttl { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .e2ax  { stroke: #8c8577; stroke-width: 1.2; fill: none; }
    .e2arr { fill: #7aa2cf; }
    .e2yes { fill: #6f8f3f; }
    .e2no  { fill: #ffffff; stroke: #8c8577; stroke-width: 1.3; }
    .e2zz  { stroke: #c98a76; stroke-width: 6; stroke-linecap: round; fill: none; opacity: .55; }
    .e2tk  { stroke: #c9c2b4; stroke-width: 1; stroke-dasharray: 3 4; fill: none; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2ink, :root:is([data-theme="dark"], [data-theme="black"]) .e2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2ax { stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2arr { fill: #6f9bd0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2yes { fill: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2no { fill: #17161b; stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2zz { stroke: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .e2tk { stroke: #3e3a33; }
  </style>
  <rect class="e2bg" x="0" y="0" width="760" height="236" rx="10"/>
  <path class="e2tk" d="M220,40 L220,200 M330,40 L330,200 M440,40 L440,200 M640,40 L640,200"/>
  <text class="e2mut" x="220" y="34" text-anchor="middle">epoll_wait</text>
  <text class="e2mut" x="330" y="34" text-anchor="middle">epoll_wait</text>
  <text class="e2mut" x="440" y="34" text-anchor="middle">epoll_wait</text>
  <text class="e2mut" x="640" y="34" text-anchor="middle">epoll_wait</text>
  <text class="e2ttl" x="20" y="66">数据到达</text>
  <path class="e2ax" d="M130,62 L730,62"/>
  <path class="e2arr" d="M160,46 L172,62 L148,62 z"/>
  <text class="e2ink" x="160" y="84" text-anchor="middle">4 KiB</text>
  <path class="e2arr" d="M560,46 L572,62 L548,62 z"/>
  <text class="e2ink" x="560" y="84" text-anchor="middle">2 KiB</text>
  <text class="e2ttl" x="20" y="122">水平触发</text>
  <path class="e2ax" d="M130,118 L730,118"/>
  <circle class="e2yes" cx="220" cy="118" r="8"/><circle class="e2yes" cx="330" cy="118" r="8"/><circle class="e2yes" cx="440" cy="118" r="8"/><circle class="e2yes" cx="640" cy="118" r="8"/>
  <text class="e2mut" x="230" y="142">每次都报：缓冲区里还剩 3、2、1 KiB，读完为止</text>
  <text class="e2ttl" x="20" y="178">边缘触发</text>
  <path class="e2ax" d="M130,174 L730,174"/>
  <circle class="e2yes" cx="220" cy="174" r="8"/>
  <path class="e2zz" d="M330,174 L556,174"/>
  <circle class="e2no" cx="330" cy="174" r="8"/>
  <circle class="e2yes" cx="560" cy="174" r="8"/>
  <text class="e2mut" x="342" y="198">不报，线程睡着：剩下的 3 KiB 没人管</text>
  <text class="e2mut" x="568" y="198">新数据到了才再报</text>
  <text class="e2mut" x="20" y="226">实心点 = 这次 epoll_wait 报了这个 fd；空心点和红条 = 没报，线程一直睡到新数据到达。</text>
</svg>

边缘触发下，剩下的 3 KiB 卡在缓冲区里，直到对方再发数据才会被处理；对方如果在等你的回应，两边就一起干等。所以**用边缘触发，每次被通知都必须把数据读到 `EAGAIN` 为止**，socket 也必须设成非阻塞，否则最后那次 `recv` 会把整个线程卡住：

```cpp
void drain(int fd) {                         // fd 已设成 O_NONBLOCK
    char buf[4096];
    for (;;) {
        ssize_t r = recv(fd, buf, sizeof buf, 0);
        if (r > 0) { on_data(fd, buf, r); continue; }
        if (r == 0) { epoll_ctl(ep, EPOLL_CTL_DEL, fd, nullptr); close(fd); return; }  // 对端关了
        if (errno == EAGAIN || errno == EWOULDBLOCK) return;  // 读干净了，等下一次通知
        if (errno == EINTR) continue;                         // 被信号打断，再读
        epoll_ctl(ep, EPOLL_CTL_DEL, fd, nullptr); close(fd); return;  // 真出错了
    }
}
```

两种方式各有代价。水平触发写起来不容易错：没读完，下次还会报；代价是一个一直有数据、但你暂时不想读的 fd，会让每次 `epoll_wait` 都报它。边缘触发每有一批新数据只报一次，`epoll_wait` 返回得更少；代价是每个 fd 都要多一次只为看到 `EAGAIN` 的 `recv`，而且一处漏读，这个连接就会卡住。

## 4. 代价：哪一步进内核，进去要花多少

### 4.1 系统调用不等于切换线程

`epoll_ctl`、`epoll_wait`、`recv` 每调一次，都是一次系统调用：同一个线程把特权级从用户态切到内核态，执行内核代码，再切回来。内核那一半本来就映射在每个进程的地址空间里（[进程地图](/zh/ref/cpp-linux/#segments)最上面那块），红黑树、就绪链表都在那里，所以不用换进程、不用换线程。一次来回约 100 ns 到几百 ns，CPU 漏洞的缓解措施开得越多越贵。

受 Meltdown 影响的 Intel CPU 上开了 KPTI，用户态的页表里只留着进内核必需的一小块，每次进出内核都要换一次页表（CR3）。有 PCID 的话不用清空整个 TLB，但这一来一回仍然更贵。AMD 不受 Meltdown 影响，不开 KPTI。

真正贵的是 `epoll_wait` 睡着了：线程被调度出去，等回调把它叫醒、再调度回来，要几 µs，回来时缓存也凉了。**epoll 每一步都要进内核，但进内核本身只要百 ns 级；贵的是睡下去再被叫醒。**

### 4.2 一圈事件循环的账

| 这一步 | 系统调用 | 内核里做的事 |
|---|---|---|
| `epoll_wait` | 1 次 | 看就绪链表；空了就睡 |
| 对每个就绪的 fd `recv` | 每次 1 次 | 从接收缓冲区拷数据到用户的 `buf` |
| 边缘触发下读到 `EAGAIN` | 每个 fd 多 1 次 | 发现缓冲区空了，返回 `EAGAIN` |
| `epoll_ctl` | 连接建立、关闭时各 1 次 | 改树 |

一次 `epoll_wait` 可以带回很多个事件，分摊下来不贵；但后面每个 `recv` 仍然各要一次系统调用。连接多、每个连接上的消息小而密时，大部分时间花在 `recv` 的进出上，而不是 `epoll_wait`。

### 4.3 同步还是异步：epoll 只通知“可以读了”

这里常把两组概念混在一起。阻塞和非阻塞问的是：数据还没好的时候，这次调用等不等。`epoll_wait` 两种都行：`timeout = -1` 一直等，`0` 立刻返回，大于 0 最多等这么久。同步和异步问的是：把数据从内核搬到你的缓冲区这一步，是不是你的线程自己调用、自己等着它做完。

按后一个标准，epoll 是同步的：`epoll_wait` 只告诉你哪些 fd 现在去读不会卡住（就绪通知），搬数据还得你自己调 `recv`，你的线程等着内核把数据拷进 `buf` 才返回。这套模型叫 Reactor。异步 IO 是反过来：先把“读到这个 buf 里”整件事交给内核，内核做完再通知你“已经读好了，读了多少字节”（完成通知），这叫 Proactor，Linux 上是 io_uring：

```cpp
// io_uring：先把整件事交出去，内核做完再通知
io_uring_prep_recv(sqe, fd, buf, sizeof buf, 0);
io_uring_submit(&ring);            // 提交完就走
io_uring_wait_cqe(&ring, &cqe);    // 拿到的是“已经读完了，读了 cqe->res 字节”
```

**epoll 是“同步 IO 多路复用”：它把等待集中到了一个调用上，搬数据仍然是同步的。**

## 5. 多线程，以及还能怎么省

### 5.1 几个线程一起等

几个线程在同一个 epoll 上 `epoll_wait`，一个事件只叫醒其中一个（它们在 `ep->wq` 上排的是独占等待）。但水平触发下，这个线程取走事件时会把这一项放回链表，于是可能又叫醒另一个线程，两个线程同时去读同一个连接。所以多线程共用一个 epoll 时，通常配 `EPOLLONESHOT`：一项报出去就停掉，处理它的线程读完再用 `EPOLL_CTL_MOD` 重新打开，保证一个连接同一时间只有一个线程在处理。

另一种情况是好几个 epoll 实例都关注同一个监听 socket，来一个新连接会把它们全叫醒，最后只有一个 `accept` 得到，这叫惊群。办法是登记时加 `EPOLLEXCLUSIVE`（Linux 4.5 起），或者用 `SO_REUSEPORT` 给每个线程开一个自己的监听 socket，由内核按连接分给各个线程。

### 5.2 想再省：busy poll、io_uring、内核旁路

epoll 解决的是“连接很多时，怎么高效地等”，可每个事件仍然要付几次系统调用的钱，等的时候还可能睡着。按省得越来越多排，有这几条路：

1. busy poll（`SO_BUSY_POLL`，或者 epoll 自己的 busy poll）：等数据时不睡，在内核里轮询网卡队列，省掉睡眠和唤醒那几 µs；系统调用本身还在。
2. io_uring：提交请求和取结果都通过用户态和内核共享的环形队列。开了 SQPOLL，由一个内核线程专门盯着提交队列，稳定运行时可以做到零系统调用。
3. 内核旁路（kernel bypass：DPDK、ef_vi、Onload）：网卡的收包队列直接映射进用户态，程序自己轮询，整条路不进内核，也就用不着 epoll。Onload 稍有不同：它在用户态重新实现了 socket 和 epoll 这套接口，程序不用改。

回头看，epoll 的设计就是一句话：**把每次都要做的登记挪到一次，把每次都要做的查找换成一个指针。**树、链表、回调各管一件事，所以连接数再多，事件循环的每一圈也只为真正有事件的连接付钱。
