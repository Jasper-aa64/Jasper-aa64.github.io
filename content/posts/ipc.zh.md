---
title: "进程间通信：管道、共享内存、信号和 socket"
date: 2026-11-02
slug: "ipc"
description: "两个进程的地址空间是隔开的，同一个虚拟地址在两边指向不同的物理页，所以传数据只有两条路：让内核转交（管道、FIFO、消息队列、Unix 域套接字、TCP 回环），或者把同一批物理页映射进两个进程（共享内存、MAP_SHARED 映射文件）。前一条每条消息付两次拷贝、两次系统调用，换来内核替你排队、阻塞、唤醒；后一条不拷贝也不进内核，同步和通知要自己做。最后讲只传通知的信号和 eventfd，以及怎么选。"
summary: "进程间通信的方式看起来很多，按数据走不走内核只分两类。管道和 socket 让内核转交：写的一方拷进内核缓冲区，读的一方拷出来，内核顺便管了排队、满了阻塞、空了等待、对端关闭。共享内存让两个页表指向同一批物理页：建好以后读写就是普通访存，0 次拷贝、0 次系统调用，但没人告诉对方“数据到了”，也没人拦着两边同时写。信号和 eventfd 只传通知，不传数据。"
categories: [Linux]
tags: [linux, ipc, pipe, shared-memory, signal, unix-socket, cpp]
toc: true
---

两个进程要交换数据，最直接的想法是把一个指针传过去。可这个指针到了另一个进程里没有意义：每个进程有自己的页表，同一个虚拟地址在两个进程里指向不同的物理页，甚至根本没有映射。所以进程之间传数据，只能找一个两边都碰得到的地方：要么是内核，要么是两个页表都映射进来的同一批物理页。Linux 上各种进程间通信（IPC）的方式，都是这两条路之一；另有信号和 eventfd 两种，只传一个通知，不传数据。

## 1. 地址空间隔开了，数据要找个两边都碰得到的地方

### 1.1 地址空间隔离（address space isolation）：同一个地址，各指各的页

`fork` 出来的子进程和父进程，全局变量的地址一模一样，可子进程改了，父进程看不到：

```cpp
#include <cstdio>
#include <sys/wait.h>
#include <unistd.h>

int x = 0;

int main() {
    if (fork() == 0) { x = 1; _exit(0); }    // 子进程改的是自己那一份
    wait(nullptr);
    std::printf("%p %d\n", (void*)&x, x);    // 地址和子进程里一样，值还是 0
}
```

`fork` 之后，两个进程的页表一开始指向同一批物理页，并且都标成只读。子进程写 `x` 时触发缺页，内核给它复制一页、改它的页表，从这一刻起两边的 `&x` 就落在了不同的物理页上（写时复制，COW）。**地址相同不代表是同一块内存：虚拟地址要经过各自的页表才落到物理页上，而页表每个进程一份**。这就是[进程地图](/maps/process-map.zh.html)上“虚拟地址 → 页表 → 物理内存”那条线。

### 1.2 两条路：让内核转交，或者共用物理页

既然用户态的内存互相看不见，数据要么交给内核、由内核转给对方，要么让两个进程的页表指向同一批物理页：

<svg viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="左边是管道：进程 A 用 write 把 buf 里的数据拷进内核的管道缓冲区，进程 B 用 read 拷出来，每条消息 2 次 CPU 拷贝、2 次系统调用；右边是共享内存：两个进程地址空间里的共享段，经各自的页表落到同一批物理页，建好以后 0 次拷贝、0 次系统调用" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ip0bg  { fill: #fbfaf7; }
    .ip0p   { fill: #ffffff; stroke: #ddd7c8; stroke-width: 1.2; }
    .ip0u   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .ip0b   { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.1; }
    .ip0k   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .ip0m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .ip0d   { fill: #f3efe6; stroke: #b8ab8c; stroke-width: 1.2; }
    .ip0ink { fill: #1c1b18; font-size: 12.5px; }
    .ip0sm  { fill: #1c1b18; font-size: 11.5px; }
    .ip0mut { fill: #6b6558; font-size: 12px; }
    .ip0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .ip0hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .ip0ln  { stroke: #8c959f; stroke-width: 1.2; stroke-dasharray: 5 4; fill: none; }
    .ip0cp  { stroke: #bc4c00; stroke-width: 2; fill: none; }
    .ip0cpt { fill: #bc4c00; font-size: 11.5px; }
    .ip0hc  { fill: #bc4c00; }
    .ip0mp  { stroke: #4f7a28; stroke-width: 2; stroke-dasharray: 3 3; fill: none; }
    .ip0mpt { fill: #4f7a28; font-size: 11.5px; }
    .ip0hm  { fill: #4f7a28; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0p { fill: #1d1c22; stroke: #3a3842; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0u { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0b { fill: #17161b; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0k { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0m { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0d { fill: #2a2721; stroke: #6b6250; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0ink, :root:is([data-theme="dark"], [data-theme="black"]) .ip0sm, :root:is([data-theme="dark"], [data-theme="black"]) .ip0ttl, :root:is([data-theme="dark"], [data-theme="black"]) .ip0hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0ln { stroke: #6e6a7a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0cp { stroke: #f0883e; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0cpt, :root:is([data-theme="dark"], [data-theme="black"]) .ip0hc { fill: #f0883e; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0mp { stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip0mpt, :root:is([data-theme="dark"], [data-theme="black"]) .ip0hm { fill: #8fb257; }
  </style>
  <defs>
    <marker id="ip0ac" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ip0hc"/></marker>
    <marker id="ip0am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ip0hm"/></marker>
  </defs>
  <rect class="ip0bg" x="0" y="0" width="760" height="340" rx="10"/>
  <rect class="ip0p" x="16" y="16" width="356" height="308" rx="10"/>
  <rect class="ip0p" x="388" y="16" width="356" height="308" rx="10"/>
  <text class="ip0ttl" x="32" y="42">管道：让内核转交</text>
  <rect class="ip0u" x="32" y="56" width="140" height="70" rx="6"/>
  <text class="ip0hd" x="44" y="76">进程 A</text>
  <rect class="ip0b" x="44" y="86" width="116" height="28" rx="4"/>
  <text class="ip0sm" x="54" y="105">buf：要发的数据</text>
  <rect class="ip0u" x="216" y="56" width="140" height="70" rx="6"/>
  <text class="ip0hd" x="228" y="76">进程 B</text>
  <rect class="ip0b" x="228" y="86" width="116" height="28" rx="4"/>
  <text class="ip0sm" x="238" y="105">buf：收到的数据</text>
  <path class="ip0ln" d="M24,146 L364,146"/>
  <text class="ip0mut" x="30" y="140">用户态</text>
  <text class="ip0mut" x="30" y="163">内核态</text>
  <rect class="ip0k" x="72" y="176" width="244" height="64" rx="6"/>
  <text class="ip0hd" x="84" y="200">管道缓冲区</text>
  <text class="ip0sm" x="84" y="222">内核内存里的环，默认 64 KiB</text>
  <path class="ip0cp" d="M102,114 L102,174" marker-end="url(#ip0ac)"/>
  <text class="ip0cpt" x="110" y="166">① write：拷进内核</text>
  <path class="ip0cp" d="M286,176 L286,116" marker-end="url(#ip0ac)"/>
  <text class="ip0cpt" x="278" y="140" text-anchor="end">② read：拷出来</text>
  <text class="ip0ink" x="32" y="294">每条消息：2 次 CPU 拷贝，2 次系统调用</text>
  <text class="ip0mut" x="32" y="314">内核替你排队、阻塞、唤醒</text>
  <text class="ip0ttl" x="404" y="42">共享内存：共用物理页</text>
  <rect class="ip0u" x="404" y="56" width="150" height="112" rx="6"/>
  <text class="ip0hd" x="416" y="76">进程 A 的地址空间</text>
  <rect class="ip0b" x="416" y="86" width="126" height="18" rx="3"/>
  <text class="ip0sm" x="424" y="99">栈</text>
  <rect class="ip0b" x="416" y="108" width="126" height="18" rx="3"/>
  <text class="ip0sm" x="424" y="121">堆、代码</text>
  <rect class="ip0m" x="416" y="130" width="126" height="26" rx="3"/>
  <text class="ip0sm" x="424" y="147">共享段（地址 A）</text>
  <rect class="ip0u" x="578" y="56" width="150" height="112" rx="6"/>
  <text class="ip0hd" x="590" y="76">进程 B 的地址空间</text>
  <rect class="ip0b" x="590" y="86" width="126" height="18" rx="3"/>
  <text class="ip0sm" x="598" y="99">栈</text>
  <rect class="ip0m" x="590" y="108" width="126" height="26" rx="3"/>
  <text class="ip0sm" x="598" y="125">共享段（地址 B）</text>
  <rect class="ip0b" x="590" y="138" width="126" height="18" rx="3"/>
  <text class="ip0sm" x="598" y="151">其他映射</text>
  <rect class="ip0d" x="404" y="214" width="324" height="56" rx="6"/>
  <rect class="ip0b" x="416" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0b" x="448" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0b" x="480" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0m" x="512" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0m" x="544" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0b" x="576" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0b" x="608" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0b" x="640" y="222" width="28" height="22" rx="3"/>
  <rect class="ip0b" x="672" y="222" width="28" height="22" rx="3"/>
  <text class="ip0sm" x="416" y="262">物理内存：/dev/shm/demo 的那几页</text>
  <path class="ip0mp" d="M479,156 L479,196 L526,196 L526,220" marker-end="url(#ip0am)"/>
  <text class="ip0mpt" x="486" y="190">A 的页表</text>
  <path class="ip0mp" d="M716,121 L722,121 L722,204 L558,204 L558,220" marker-end="url(#ip0am)"/>
  <text class="ip0mpt" x="650" y="198">B 的页表</text>
  <text class="ip0ink" x="404" y="294">建好以后：0 次拷贝，0 次系统调用</text>
  <text class="ip0mut" x="404" y="314">没人替你排队、阻塞、唤醒</text>
</svg>

左边这条路，写的一方调 `write`，内核把数据从它的 `buf` 拷进内核里的一块缓冲区；读的一方调 `read`，内核再拷进它的 `buf`。每条消息两次 CPU 拷贝、两次系统调用，读的一方要是睡着在等，还要加上一次唤醒的几 µs。可内核在中间也替你干了不少活：缓冲区空了让读的一方睡、满了让写的一方睡、来了数据把人叫醒、一端关了告诉另一端。

右边这条路，内核只在开头帮忙把同一批物理页映射进两个进程，之后读写就是普通的访存，不拷贝也不进内核。代价是内核不在中间了：数据写好了没人通知对方，两边同时写也没人拦着。**内核转交省心，但每条消息都要付两次拷贝和两次系统调用；共享内存不付这笔钱，同步和通知要自己做**。

## 2. 让内核转交：管道和 socket

### 2.1 管道（pipe）：内核里一块先进先出的缓冲区

`pipe` 在内核里建一块缓冲区，返回两个 fd：`fd[0]` 只能读，`fd[1]` 只能写。它本身只在一个进程里，要靠 `fork` 才能连起两个进程：子进程复制了父进程的 fd 表，两边的 fd 指向内核里同一个管道。

```cpp
#include <cstdio>
#include <sys/wait.h>
#include <unistd.h>

int main() {
    int fd[2];
    pipe(fd);                                // fd[0] 读端，fd[1] 写端
    if (fork() == 0) {                       // 子进程：只写
        close(fd[0]);
        const char msg[] = "hello from child";
        write(fd[1], msg, sizeof msg - 1);   // 拷进内核的管道缓冲区
        close(fd[1]);
        _exit(0);
    }
    close(fd[1]);                            // 父进程：只读，先关掉自己的写端（2.2）
    char buf[64];
    ssize_t n;
    while ((n = read(fd[0], buf, sizeof buf)) > 0)   // 从内核拷出来
        std::fwrite(buf, 1, n, stdout);
    close(fd[0]);
    wait(nullptr);
}
```

shell 里的 `ls | wc -l` 就是这么接起来的：shell 建一个管道，`fork` 两次，把一个子进程的标准输出、另一个的标准输入分别换成管道的两端，再各自 `exec`。

**管道是字节流，没有消息边界**：写的一方连写两次各 10 字节，读的一方可能一次读到 20 字节，也可能分三次读到。要按条收发，得自己在数据里加长度前缀之类的分隔。只有一条保证：一次写入不超过 `PIPE_BUF`（4096 字节）时是原子的，几个进程同时往一个管道写短消息，内容不会互相穿插。

缓冲区默认 16 页，也就是 64 KiB，可以用 `fcntl(fd, F_SETPIPE_SZ, n)` 调大，上限看 `/proc/sys/fs/pipe-max-size`（默认 1 MiB）。`ulimit -a` 里那行 pipe size（8 × 512 字节 = 4 KiB）说的是 `PIPE_BUF`，即原子写入的上限，不是缓冲区容量。这块缓冲区和 socket 缓冲区、[epoll 的红黑树](/zh/posts/epoll-internals/)一样，都是内核内存，不算在进程的 RSS 里，在 [IO 地图](/maps/io-map.zh.html)上属于中间那层内核。

### 2.2 管道的四种边界：空、满、写端全关、读端全关

内核替你管的那些事，落到管道上就是这四条规矩：

<svg viewBox="0 0 760 240" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="管道缓冲区是一个先进先出的环，写端写进来，读端读出去，默认 16 页 64 KiB；四种边界：管道空且写端还开着时 read 阻塞；管道满时 write 阻塞；写端全关时 read 返回 0 即 EOF；读端全关时 write 收到 SIGPIPE，忽略它就返回 EPIPE" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ip1bg  { fill: #fbfaf7; }
    .ip1e   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .ip1c   { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.1; }
    .ip1f   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .ip1g   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .ip1n   { fill: #fbe9d0; stroke: #d4a15a; stroke-width: 1.3; }
    .ip1ink { fill: #1c1b18; font-size: 12px; }
    .ip1mut { fill: #6b6558; font-size: 11.5px; }
    .ip1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .ip1hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .ip1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .ip1hh  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1e, :root:is([data-theme="dark"], [data-theme="black"]) .ip1g { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1c { fill: #1d1c22; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1f { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1n { fill: #45361d; stroke: #9a7638; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1ink, :root:is([data-theme="dark"], [data-theme="black"]) .ip1ttl, :root:is([data-theme="dark"], [data-theme="black"]) .ip1hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip1hh { fill: #a19caf; }
  </style>
  <defs><marker id="ip1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ip1hh"/></marker></defs>
  <rect class="ip1bg" x="0" y="0" width="760" height="240" rx="10"/>
  <text class="ip1ttl" x="24" y="32">管道缓冲区：先写进来的先被读走</text>
  <rect class="ip1e" x="24" y="56" width="112" height="40" rx="6"/>
  <text class="ip1ink" x="36" y="81">写端 fd[1]</text>
  <path class="ip1ln" d="M136,76 L152,76" marker-end="url(#ip1a)"/>
  <rect class="ip1c" x="156" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="184" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="212" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="240" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="268" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="296" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="324" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="352" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="380" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="408" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="436" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="464" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="492" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1f" x="520" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="548" y="60" width="26" height="32" rx="3"/>
  <rect class="ip1c" x="576" y="60" width="26" height="32" rx="3"/>
  <path class="ip1ln" d="M604,76 L620,76" marker-end="url(#ip1a)"/>
  <rect class="ip1e" x="624" y="56" width="112" height="40" rx="6"/>
  <text class="ip1ink" x="636" y="81">读端 fd[0]</text>
  <text class="ip1mut" x="435" y="52" text-anchor="middle">已写、还没被读走的数据</text>
  <text class="ip1mut" x="380" y="114" text-anchor="middle">默认 16 页 = 64 KiB；读走一页，那一页就空出来给写用</text>
  <rect class="ip1g" x="24" y="136" width="170" height="84" rx="6"/>
  <text class="ip1hd" x="36" y="160">管道空，写端还开着</text>
  <text class="ip1ink" x="36" y="182">read 阻塞，</text>
  <text class="ip1ink" x="36" y="202">等有人写进来</text>
  <rect class="ip1g" x="206" y="136" width="170" height="84" rx="6"/>
  <text class="ip1hd" x="218" y="160">管道满了</text>
  <text class="ip1ink" x="218" y="182">write 阻塞，</text>
  <text class="ip1ink" x="218" y="202">等有人读走、腾出地方</text>
  <rect class="ip1n" x="388" y="136" width="170" height="84" rx="6"/>
  <text class="ip1hd" x="400" y="160">写端全关了</text>
  <text class="ip1ink" x="400" y="182">read 返回 0：</text>
  <text class="ip1ink" x="400" y="202">这就是 EOF，读完了</text>
  <rect class="ip1n" x="570" y="136" width="170" height="84" rx="6"/>
  <text class="ip1hd" x="582" y="160">读端全关了</text>
  <text class="ip1ink" x="582" y="182">write 收到 SIGPIPE；</text>
  <text class="ip1ink" x="582" y="202">忽略它就返回 EPIPE</text>
</svg>

前两条是普通的等待：读的一方等数据，写的一方等空间，内核用等待队列把睡着的一方挂起来，另一方读写之后叫醒它，和 [epoll 那篇](/zh/posts/epoll-internals/)讲的等待队列是同一套机制。把 fd 设成 `O_NONBLOCK`，这两种情况就不睡，返回 `EAGAIN`，这时管道也能交给 epoll 去等。

后两条看的是“还有没有人拿着另一端”。内核给读端和写端各记一个计数：所有进程里指向写端的 fd 都关掉了，读的一方读完剩下的数据后 `read` 返回 0，这就是 EOF；指向读端的 fd 全关了，再写就没有意义，内核给写的一方发 `SIGPIPE`，默认动作是直接杀掉进程。

这就是上面代码里那两个 `close` 的原因。`fork` 之后父进程手里也有一个写端，它要是不关，写端的计数永远不为 0，子进程写完退出了，父进程的 `read` 也等不到 EOF，会一直阻塞下去。**管道的 EOF 看的是所有进程里的写端都关了没有，所以 `fork` 之后每个进程都要关掉自己用不着的那一端**。往一个已经关掉的 socket 写也会收到 `SIGPIPE`，所以服务器程序一般在启动时 `signal(SIGPIPE, SIG_IGN)`，或者 `send` 时带 `MSG_NOSIGNAL`，改成检查 `EPIPE` 错误。

### 2.3 有名管道（FIFO）和消息队列：给没有亲缘关系的进程用

普通管道没有名字，只能靠 `fork` 继承 fd，所以只能连父子、兄弟这类有共同祖先的进程。`mkfifo("/tmp/myfifo", 0600)` 在文件系统里建一个名字，两个毫不相干的进程各自 `open` 这个路径，一个读一个写，就连上了同一个管道。**数据仍然只经过内核里的缓冲区，从不落盘，文件系统里那个名字只是一个会面地点**。打开时有一点不同：只读打开会阻塞到有人以写方式打开为止，反过来也一样，因为一端没人时读写都没有意义。

POSIX 消息队列（`mq_open`、`mq_send`、`mq_receive`）也走内核，也是两次拷贝，区别是它保留消息边界，一次 `mq_receive` 取走一条完整消息，还能按优先级排队。它的默认限制比较小（`/proc/sys/fs/mqueue` 下，默认一个队列最多 10 条、每条最多 8 KiB），现在用得不多，需要消息边界时多半直接用下一节的 Unix 域套接字。

### 2.4 Unix 域套接字（Unix domain socket）：本机上的 socket，不走协议栈

`socket(AF_UNIX, ...)` 用的是和网络 socket 一样的接口（`bind`、`listen`、`connect`、`send`、`recv`），地址换成一个文件路径。数据还是两次拷贝：发送方的数据拷进一个内核缓冲区，直接挂到接收方 socket 的接收队列上，接收方再拷出来。中间没有 TCP/IP 协议栈：不分段、不算校验和、不等 ACK、没有拥塞控制，所以比本机 TCP 便宜。它也比管道多几样东西：一条连接两个方向都能读写；`SOCK_DGRAM` 和 `SOCK_SEQPACKET` 保留消息边界；`SO_PEERCRED` 能查到对端进程的 pid、uid，可以拿来做权限检查。本机的 PostgreSQL、Docker（`/var/run/docker.sock`）都用它让客户端连进来。

它独有的一样本事是传 fd（`SCM_RIGHTS`）：

```cpp
#include <cstring>
#include <sys/socket.h>

// 把 fd 通过 Unix 域套接字 sock 交给对端进程
void send_fd(int sock, int fd) {
    char dummy = 'x';
    iovec iov{&dummy, 1};                       // 至少要带 1 字节的普通数据
    alignas(cmsghdr) char ctl[CMSG_SPACE(sizeof(int))];
    msghdr msg{};
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;
    msg.msg_control = ctl;
    msg.msg_controllen = sizeof ctl;
    cmsghdr* c = CMSG_FIRSTHDR(&msg);
    c->cmsg_level = SOL_SOCKET;
    c->cmsg_type = SCM_RIGHTS;                  // 这条消息里带着 fd
    c->cmsg_len = CMSG_LEN(sizeof(int));
    std::memcpy(CMSG_DATA(c), &fd, sizeof(int));
    sendmsg(sock, &msg, 0);
}
```

传过去的不是那个整数：fd 只是发送方 fd 表里的一个下标，换个进程就没有意义。内核做的是在接收方的 fd 表里新开一格，指向发送方那个 fd 背后同一个打开的文件，对方拿到的编号多半不一样，可文件读写位置是共用的。这和 1.1 的道理一样：**能跨进程共享的只能是内核里的对象，用户态的地址和 fd 编号都只在自己的进程里有意义**。后面 4.3 节的 eventfd、3.1 节共享内存的 fd，都可以这样交给一个不相干的进程。

### 2.5 TCP 回环（loopback）：多走一遍协议栈，换来能跨机器

连 `127.0.0.1` 的 TCP 也能做本机通信。数据照样是两次拷贝，但中间要完整走一遍协议栈：发送方的 TCP 分段、加 IP 头，经过回环设备 `lo` 交给接收方向，再由软中断走一遍 IP、TCP 的收包处理，还要回 ACK。这些都是 Unix 域套接字省掉的 CPU 开销，所以本机通信时延迟和 CPU 占用通常都比它高一截。

换来的是**同一份代码不用改就能跨机器**：今天两个服务在一台机器上，明天拆到两台，只要把地址从 `127.0.0.1` 换成对方的 IP。在 [IO 地图](/maps/io-map.zh.html)上，回环走的就是“发一个包”和“收一个包”两条路径，只是跳过了网卡那一段。

## 3. 共用物理页：共享内存

### 3.1 POSIX 共享内存：`shm_open` 加 `mmap`

共享内存的做法是让两个进程映射同一个内存对象。POSIX 的接口是 `shm_open`，它在 `/dev/shm`（一个放在内存里的 tmpfs 文件系统）下建一个对象，返回 fd，再用 `mmap` 以 `MAP_SHARED` 映射进来：

```cpp
// shared.h：两个进程都 include
#include <atomic>
#include <cstdint>

struct Shared {
    std::atomic<uint64_t> seq;   // 写完数据再加 1，读的一方看到它变了才去读
    char data[4096];
};
static_assert(std::atomic<uint64_t>::is_always_lock_free);   // 带锁的 atomic 不能跨进程用（3.2）
```

```cpp
// 写的一方
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "shared.h"

int main() {
    int fd = shm_open("/demo", O_CREAT | O_RDWR, 0600);   // 建出 /dev/shm/demo
    ftruncate(fd, sizeof(Shared));                          // 新建的对象长度是 0，先定长度
    auto* s = static_cast<Shared*>(mmap(nullptr, sizeof(Shared),
                     PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0));
    close(fd);                                              // 映射建好以后 fd 就可以关了
    std::strcpy(s->data, "hello");                          // 普通的写内存，不进内核
    s->seq.fetch_add(1, std::memory_order_release);         // 先写数据，再发布
}
```

```cpp
// 读的一方
#include <cstdio>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "shared.h"

int main() {
    int fd = shm_open("/demo", O_RDWR, 0);
    auto* s = static_cast<Shared*>(mmap(nullptr, sizeof(Shared),
                     PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0));
    close(fd);
    while (s->seq.load(std::memory_order_acquire) == 0) { }   // 没人叫醒你，只能自己看（3.2）
    std::puts(s->data);
    shm_unlink("/demo");                                       // 删掉名字，最后一个映射解除后内存才释放
}
```

两个进程各自 `mmap` 以后，共享段出现在各自[进程地图](/maps/process-map.zh.html)的 mmap 区里，`/proc/<pid>/maps` 里能看到一行 `/dev/shm/demo`。每个进程第一次碰到某一页时会缺页，内核把这个对象的那一页填进自己的页表；之后两个页表指向同一批物理页，写的一方 `strcpy` 进去的字节，读的一方直接就能读到。

有一点容易踩坑：同一个共享段在两个进程里的起始地址多半不一样，就像图里的地址 A 和地址 B。所以共享内存里不能存指针，一个进程存进去的指针，在另一个进程里指向的是别的东西。要表示“指向共享段里的某处”，存相对段首的偏移量。同理，`std::string`、`std::vector` 这类自己在堆上分配内存的类型也不能直接放进去，它们的数据在写的那个进程的堆上，对方看不见。**共享内存里只能放不含指针的平坦数据，位置用偏移量表示**。

`shm_open` 建的对象不随进程退出而消失：它挂在 `/dev/shm` 下，要等有人 `shm_unlink` 删掉名字、而且所有映射都解除了，内存才回收，否则一直占到重启。较老的 System V 接口（`shmget`、`shmat`）道理相同，用一个整数 key 而不是路径找到同一段内存，用 `ipcs -m` 查看、`ipcrm` 删除。

### 3.2 同步要自己做：原子变量、进程间的锁、futex

内核不在中间了，管道替你做的那几件事都要自己补上。第一件是“写完了”：读的一方得知道数据已经完整写进去了，才能去读。上面的代码用的是一个原子计数器配 release、acquire 内存序：写的一方先写数据，再用 release 加计数；读的一方用 acquire 读到新计数后，保证能看到计数之前写进去的数据。这和线程之间的写法完全一样，因为两个进程跑在同一台机器的 CPU 上，看到的是同一套缓存一致性和内存序。唯一的额外要求是这个原子变量必须是无锁的（lock-free）：有些平台上过大的 `std::atomic<T>` 内部是用一把放在进程自己内存里的锁实现的，另一个进程看不到那把锁。

第二件是互斥：两个进程要改同一份结构，得有一把两边都看得见的锁。`std::mutex` 做不到，要用 pthread 的锁并标成进程间共享，锁本身放在共享内存里：

```cpp
#include <pthread.h>

struct SharedWithLock {
    pthread_mutex_t mu;
    int counter;
};

void init(SharedWithLock* s) {                     // 只由建共享段的那个进程调一次
    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setpshared(&a, PTHREAD_PROCESS_SHARED);   // 允许别的进程用这把锁
    pthread_mutexattr_setrobust(&a, PTHREAD_MUTEX_ROBUST);      // 持锁的进程死了，下一个加锁的会收到 EOWNERDEAD
    pthread_mutex_init(&s->mu, &a);
    pthread_mutexattr_destroy(&a);
}
```

`ROBUST` 是进程之间才需要操心的事：线程崩了整个进程一起死，可一个进程拿着锁被杀掉，另一个进程还活着，没有这个属性它就会永远等下去。设了以后，下一个 `pthread_mutex_lock` 返回 `EOWNERDEAD`，它检查、修好数据，再调 `pthread_mutex_consistent` 把锁恢复成正常状态。

第三件是“没数据时去睡，来了数据被叫醒”。上面读的一方是空转着等，CPU 一直在烧。要睡下去，就得有一个内核能看到的等待点：进程间共享的条件变量（`pthread_condattr_setpshared`）、POSIX 信号量（`sem_init` 第二个参数传 1）、4.3 节的 eventfd，底下都是 futex（fast userspace mutex）。futex 让内核在共享内存里的一个 32 位整数上挂等待队列：没竞争时只在用户态做原子操作，不进内核；真要等时才用系统调用睡下去。**共享内存把拷贝省了，可每次需要等待和唤醒时，照样要进内核**。所以只有每条消息不必都叫醒对方时（批量处理、对方一直在忙），共享内存的好处才完整拿得到。一个写、多个读的共享内存环形队列怎么写，在[共享内存里的 SPMC 广播环](/zh/posts/spmc-shared-memory-broadcast-ring/)里讲过。

### 3.3 映射同一个文件：`MAP_SHARED` 和 `MAP_PRIVATE`

不用 `shm_open`，两个进程 `mmap` 同一个普通文件，也能共享内存。`MAP_SHARED` 时，两个进程映射的都是这个文件在页缓存里的那些页，一边写了，另一边马上读得到，因为是同一个物理页；数据之后由内核的回写线程写回磁盘，不是写一下就同步一下，要确定落盘调 `msync`。这条路在 [IO 地图](/maps/io-map.zh.html)上就是“映射一个文件”那条路径，只是映射它的有两个进程。

`MAP_PRIVATE` 正相反：一开始也映射页缓存里的页，但谁一写就触发写时复制，复制出来的那一页只属于自己，别的进程看不到，也永远不会写回文件。所以 **`MAP_PRIVATE` 不能用来通信**，它的用途是加载程序：可执行文件和 `.so` 的数据段都是这样映射的，每个进程改的是自己那一份。

有亲缘关系的进程还有一种不需要文件的写法：`fork` 之前 `mmap(nullptr, n, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0)`。这段映射标成了共享，`fork` 以后父子进程指向同一批物理页，不做写时复制。映射文件时要注意长度：访问超出文件末尾的那部分页，进程会收到 `SIGBUS`，所以新建的文件要先 `ftruncate` 到需要的长度。

## 4. 只传一个通知：信号和 eventfd

### 4.1 信号（signal）：内核在目标进程里置一位

`kill(pid, SIGUSR1)` 并不会马上打断对方。内核只是在目标进程的“待处理信号”位图里把这一位置 1，`kill` 就返回了；对方真正处理，要等它下一次从内核回到用户态的时候：

<svg viewBox="0 0 760 320" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="信号的投递：进程 A 调 kill，内核在 B 的待处理位图里把 SIGUSR1 置 1 后 kill 就返回；B 下一次从内核回到用户态之前，内核查到这一位，在 B 的栈上压一个信号帧，让它先跳去处理函数；处理函数跑完调 sigreturn 回到内核，再回到原来的代码接着跑" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ip2bg  { fill: #fbfaf7; }
    .ip2u   { fill: #f3f8ec; stroke: #b5cc8e; stroke-width: 1.2; stroke-dasharray: 6 4; }
    .ip2k   { fill: #f4f2ee; stroke: #b8ab8c; stroke-width: 1.2; }
    .ip2b   { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.3; }
    .ip2ink { fill: #1c1b18; font-size: 12.5px; }
    .ip2mut { fill: #6b6558; font-size: 12px; }
    .ip2hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .ip2lab { fill: #6b6558; font-size: 12px; font-weight: 700; }
    .ip2ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .ip2hh  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2u { fill: #1f2419; stroke: #4d6130; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2k { fill: #24221e; stroke: #5e5646; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2b { fill: #1d1c22; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2ink, :root:is([data-theme="dark"], [data-theme="black"]) .ip2hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2mut, :root:is([data-theme="dark"], [data-theme="black"]) .ip2lab { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ip2hh { fill: #a19caf; }
  </style>
  <defs><marker id="ip2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ip2hh"/></marker></defs>
  <rect class="ip2bg" x="0" y="0" width="760" height="320" rx="10"/>
  <rect class="ip2u" x="16" y="40" width="728" height="106" rx="8"/>
  <rect class="ip2k" x="16" y="156" width="728" height="106" rx="8"/>
  <text class="ip2lab" x="24" y="64">用户态</text>
  <text class="ip2lab" x="24" y="180">内核态</text>
  <rect class="ip2b" x="76" y="52" width="158" height="84" rx="6"/>
  <text class="ip2hd" x="88" y="72">① 进程 A</text>
  <text class="ip2ink" x="88" y="94">kill(B, SIGUSR1)</text>
  <rect class="ip2b" x="246" y="168" width="158" height="84" rx="6"/>
  <text class="ip2hd" x="258" y="188">② 内核</text>
  <text class="ip2ink" x="258" y="208">在 B 的 pending 里</text>
  <text class="ip2ink" x="258" y="226">把 SIGUSR1 置 1</text>
  <text class="ip2ink" x="258" y="244">kill 到这就返回</text>
  <rect class="ip2b" x="416" y="168" width="158" height="84" rx="6"/>
  <text class="ip2hd" x="428" y="188">③ B 回用户态之前</text>
  <text class="ip2ink" x="428" y="208">查到 pending 有一位</text>
  <text class="ip2ink" x="428" y="226">在 B 的栈上压一个帧</text>
  <text class="ip2ink" x="428" y="244">让它先跳去 handler</text>
  <rect class="ip2b" x="586" y="52" width="158" height="84" rx="6"/>
  <text class="ip2hd" x="598" y="72">④ 进程 B</text>
  <text class="ip2ink" x="598" y="92">跑 handler，</text>
  <text class="ip2ink" x="598" y="110">跑完调 sigreturn，</text>
  <text class="ip2ink" x="598" y="128">回原来的代码接着跑</text>
  <path class="ip2ln" d="M155,136 L155,151 L325,151 L325,166" marker-end="url(#ip2a)"/>
  <path class="ip2ln" d="M404,210 L414,210" marker-end="url(#ip2a)"/>
  <path class="ip2ln" d="M495,168 L495,151 L665,151 L665,138" marker-end="url(#ip2a)"/>
  <text class="ip2mut" x="24" y="288">② 到 ③ 隔多久不确定：B 下一次从内核回用户态时才处理，系统调用返回、被中断打断后返回都算。</text>
  <text class="ip2mut" x="24" y="308">标准信号只是一位：处理之前又来一次，只算一次；B 正睡在 read 里的话会被叫醒，read 返回 EINTR。</text>
</svg>

这张图说明了信号能带的东西有多少：一个编号。标准信号（1–31 号）在内核里就是一位，处理之前同一个信号又来几次，也只算一次，所以不能拿它来计数。实时信号（`SIGRTMIN` 到 `SIGRTMAX`）会排队，用 `sigqueue` 发还能带一个整数，可也就这么多。**信号是一个通知，不是一条数据通道**。

它适合的是“发生了某件事”这一类：`Ctrl+C` 是 `SIGINT`，`kill` 命令默认发 `SIGTERM` 请进程退出，子进程退出时父进程收到 `SIGCHLD`，访问非法地址时内核给进程发 `SIGSEGV`，前面管道读端关了的 `SIGPIPE` 也是。`SIGKILL` 和 `SIGSTOP` 不能被捕获、也不能忽略，内核直接执行，这是保证管理员总能停掉一个进程的底线。

### 4.2 信号处理函数：只能做异步信号安全的事

从上图第 ③ 步能看出处理函数危险在哪：它插在 B 原来代码的任意一条指令之后执行。如果 B 那时正在 `malloc` 里、刚拿到分配器的锁，处理函数里再调 `malloc`（或者内部会调它的 `printf`），就会等一把被自己拿着的锁，进程卡死；不卡死的话，也可能看到分配器改了一半的数据结构。所以**处理函数里只能调一小批“异步信号安全”（async-signal-safe）的函数**，`man 7 signal-safety` 列着，`write`、`_exit` 在里面，`printf`、`malloc`、`new` 都不在。

常见写法是处理函数里只置一个标志，真正的事放回主循环去做：

```cpp
#include <csignal>

volatile std::sig_atomic_t stop = 0;
void on_term(int) { stop = 1; }               // 只置一个标志，别的都不做

int main() {
    struct sigaction sa{};
    sa.sa_handler = on_term;
    sigaction(SIGTERM, &sa, nullptr);
    while (!stop) { /* 干活 */ }
    // 回到这里再做清理：printf、free 都可以放心调
}
```

更彻底的办法是不让信号打断你，把它变成一个可读的 fd。`signalfd` 就是干这个的：

```cpp
#include <csignal>
#include <sys/signalfd.h>

sigset_t m;
sigemptyset(&m);
sigaddset(&m, SIGTERM);
sigaddset(&m, SIGCHLD);
sigprocmask(SIG_BLOCK, &m, nullptr);       // 先挡住，不让它们按老办法打断你
int sfd = signalfd(-1, &m, SFD_CLOEXEC);   // 这两个信号来了，sfd 就变成可读
// 把 sfd 交给 epoll；可读时 read 出 signalfd_siginfo，里面有信号编号和发送者的 pid
```

挡住的信号不会被丢掉，而是一直挂在待处理里，`signalfd` 把它们变成可以 `read` 的数据。这样信号就和 socket、管道一样，在事件循环里按顺序处理，不再有“插在任意一条指令之后”的问题。多线程程序要在创建线程之前就挡住，新线程会继承这个屏蔽字；否则信号可能投给某个没挡住它的线程，按老办法打断它。没有 `signalfd` 的系统上，老办法是 self-pipe：处理函数里往一个管道写 1 字节（`write` 是异步信号安全的），事件循环监听管道的读端。

### 4.3 eventfd：一个能被 epoll 等的计数器

只想告诉另一个进程“有事了”，不需要信号那么重的打断，也不需要管道那块 64 KiB 的缓冲区。`eventfd` 在内核里只有一个 8 字节的计数器：

```cpp
#include <cstdint>
#include <sys/eventfd.h>
#include <unistd.h>

int efd = eventfd(0, EFD_CLOEXEC);   // 内核里一个 8 字节的计数器，初值 0
uint64_t one = 1;
write(efd, &one, 8);                 // 计数加 1，等在它上面的人被叫醒
uint64_t n;
read(efd, &n, 8);                    // 读出累计值并清零；计数是 0 时 read 阻塞
```

`write` 往计数上加，`read` 取出累计值并清零（建的时候带 `EFD_SEMAPHORE`，就改成每次 `read` 只减 1）。**几次 `write` 合并成一次唤醒**，正好适合“有新东西了，你去看看”这种通知。它是一个 fd，所以能交给 epoll，也能靠 `fork` 继承或者用 2.4 节的 `SCM_RIGHTS` 传给别的进程。

它最常见的搭档是共享内存：数据放在共享段里，零拷贝；写的一方写完，往 eventfd 里写一次，读的一方在 epoll 里等这个 fd，被叫醒后去共享段里取。这样既不用空转，也不用为每个字节付拷贝的钱，付的只是每次唤醒的那两次系统调用。

## 5. 怎么选

把上面几种放在一张表里，按“数据走不走内核”看：

| 方式 | 数据怎么走 | 每条消息的 CPU 拷贝 | 消息边界 | 同步要自己做 | 能跨机器 | 能交给 epoll |
|---|---|---|---|---|---|---|
| 管道、FIFO | 内核缓冲区转交 | 2 次 | 没有（字节流） | 否 | 否 | 能 |
| POSIX 消息队列 | 内核转交 | 2 次 | 有 | 否 | 否 | 能（Linux 上它是 fd） |
| Unix 域套接字 | 内核转交，不走协议栈 | 2 次 | stream 没有，dgram 有 | 否 | 否 | 能 |
| TCP 回环 | 内核转交，走完整个协议栈 | 2 次 | 没有 | 否 | 能 | 能 |
| 共享内存、`MAP_SHARED` | 两个页表指向同一批物理页 | 0 次 | 自己定 | 是 | 否 | 不能，要配一个通知 |
| 信号 | 只传一个编号 | 不传数据 | — | — | 否 | 用 signalfd 才能 |
| eventfd | 只传一个计数 | 不传数据 | — | — | 否 | 能 |

表里的“能交给 epoll”决定了它能不能放进一个事件循环和别的连接一起等；“同步要自己做”那一列是共享内存省下拷贝要付的代价。

落到具体场景：父子进程之间单向传一串字节，像 shell 的管道，用 `pipe`。本机两个不相干的服务之间要请求和应答、要双向、可能还要传 fd，用 Unix 域套接字。以后可能拆到两台机器上，直接用 TCP，本机时多花的那点 CPU 换来不改代码。数据量大、来回频繁，拷贝已经成了开销，用共享内存，再配 eventfd、futex 或者进程间的条件变量做通知。只是要告诉对方“发生了某件事”，用 eventfd；要处理的是外面发来的终止请求、子进程退出这类事件，那就是信号，最好用 `signalfd` 收进事件循环。

回头看，**进程间通信只有一个问题：数据要不要经过内核。经过内核，内核替你排队、阻塞、唤醒，每条消息付两次拷贝；不经过内核，拷贝省了，排队、阻塞和唤醒就要自己做**。
