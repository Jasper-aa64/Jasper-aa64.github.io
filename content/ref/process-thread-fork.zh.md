---
title: "进程和线程：fork、写时复制、共享与独占、进程状态"
date: 2026-11-02
slug: "process-thread-fork"
description: "在 Linux 内核里，进程和线程都是一个 task_struct，区别只在创建时 clone 给了哪些共享标志：线程共用地址空间、fd 表和信号处理函数，各自只留栈、寄存器、TLS 和信号掩码。fork 不复制内存，只复制页表并把可写页改成只读，谁先写谁触发缺页、复制那一页；fd 表复制一份，但打开的文件是同一个，连文件偏移都共用。再讲 fork 加 exec、多线程程序里 fork 为什么危险，以及 R、S、D、T、Z 五种状态，僵尸进程和孤儿进程从哪来、怎么收。"
summary: "进程和线程在内核里是同一种东西，差别是共享多少：线程共用一份地址空间和一张 fd 表，只独占栈、寄存器和 TLS。fork 只复制页表，物理页等到有人写才复制，所以 fork 加 exec 很便宜；fork 之后两边的 fd 指着同一个打开的文件。进程退出后留下一条记录等父进程 wait，没人收就是僵尸；父进程先走，子进程交给 init 或最近的 subreaper 收。"
toc: true
group: cpplinux
topic: proc
weight: 114
aliases: ["/posts/process-thread-fork/"]
---

写服务端程序，迟早要回答几个问题：开线程还是开进程，fork 出来的子进程和父进程到底共用什么，`ps` 里那个 `Z` 是什么、为什么 `kill -9` 杀不掉。这几个问题的答案都在内核怎么表示一个进程上：它用同一个结构体表示进程和线程，差别只在创建时选择共享多少。

## 1. 进程和线程在内核里是同一种东西

### 1.1 task_struct：内核只调度“任务”

内核为每个能被调度的执行流建一个 `struct task_struct`，里面记着它的状态、寄存器保存在哪、属于哪个用户、能用多少资源，以及几根指向“资源”的指针：`mm` 指向地址空间（页表、各段的映射），`files` 指向 fd 表，`sighand` 指向信号处理函数表，`fs` 指向当前目录和 umask。

调度器只认 `task_struct`，不区分进程和线程：一个进程里有 4 个线程，在调度器眼里就是 4 个任务，各自排队、各自上 CPU。**进程和线程的区别不在调度，而在这几根资源指针指向的是自己的一份，还是和别人共用一份。** 指向同一个 `mm` 的几个任务，看到的是同一份内存，用户态就把它们叫作同一个进程里的线程。

所以 Linux 里线程也有一个号，叫 tid，和 pid 来自同一个编号空间。同一个进程里的线程共用一个线程组号 tgid，`getpid()` 返回的其实是 tgid，`gettid()` 返回的才是每个线程自己的号。主线程的 tid 等于 tgid，这就是为什么主线程的 tid 和 pid 一样。

### 1.2 clone 的标志：共享多少，在创建那一刻决定

新任务都由 `clone` 系统调用创建，它的标志位逐项决定新任务和调用者共用哪些资源：

```c
// glibc 的 pthread_create 最后调 clone，给的标志是这些：
CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND | CLONE_THREAD |
CLONE_SYSVSEM | CLONE_SETTLS | CLONE_PARENT_SETTID | CLONE_CHILD_CLEARTID
// CLONE_VM：共用地址空间          CLONE_FILES：共用 fd 表
// CLONE_FS：共用当前目录和 umask   CLONE_SIGHAND：共用信号处理函数
// CLONE_THREAD：放进同一个线程组（同一个 tgid）
// CLONE_SETTLS：给新线程设好自己的 TLS 基址

// fork 相当于一个共享标志都不给，只给 SIGCHLD：
// 每样资源都复制一份，退出时给父进程发 SIGCHLD
```

给了 `CLONE_VM`，新任务的 `mm` 指针直接指向调用者的那份，不复制任何东西；不给，内核就要为新任务复制一份地址空间，这就是 fork 要做的事（第 2 部分）。**创建线程比 fork 快，是因为它少做了“复制地址空间”这一步，而不是因为线程是更轻的另一种对象。** 创建一个线程约几 µs 到几十 µs，主要花在准备它的栈上；fork 一个小进程约几十到几百 µs，进程用的内存越多越慢。

### 1.3 线程共享什么、独占什么

按上面的标志，同一个进程里的线程共用一份资源，每个线程只留下“正在执行”所必需的那些状态：

| 资源 | 线程之间 | 为什么这样分 |
|---|---|---|
| 地址空间：代码、全局变量、堆、共享库，以及所有线程的栈 | 共用，同一套页表 | `CLONE_VM`：线程之间要靠共享内存交换数据 |
| fd 表：打开的文件、socket | 共用 | `CLONE_FILES`：一个线程 `accept` 的连接，交给另一个线程去读 |
| 信号处理函数 | 共用 | 信号是发给整个进程的，处理方式只能有一种 |
| 当前目录、umask、用户 ID、pid | 共用 | 它们描述的是“这个程序”，不是某一条执行流 |
| 寄存器：`rip`、`rsp`…… | 各一份 | 每个线程执行到不同的地方，切走时各自保存 |
| 栈 | 各用一段 | 每个线程有自己的调用链；主线程的在地址空间最高处，其他线程的由 `pthread_create` 从 mmap 区分配，默认 8 MiB |
| TLS（线程局部存储） | 各一份 | `thread_local` 变量和 `errno` 放在这里，靠 `fs` 寄存器指向各自那块 |
| 信号掩码、调度优先级、CPU 亲和性 | 各一份 | 每个线程可以各自屏蔽信号、各自绑核 |
| 内核栈 | 各一份 | 每个线程都可能同时在内核里执行系统调用 |

<svg viewBox="0 0 760 470" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="一个进程里的三个线程：地址空间、fd 表、信号处理函数、当前目录和 pid 只有一份，三个线程共用；每个线程独有寄存器、栈、TLS、信号掩码和内核栈，而每个线程的栈只是那份共用地址空间里的一段" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .pt0bg  { fill: #fbfaf7; }
    .pt0pr  { fill: #f7f4ee; stroke: #d6cfc2; stroke-width: 1.2; }
    .pt0sh  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .pt0seg { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.1; }
    .pt0t1  { fill: #dbe9f7; stroke: #5b8bc0; stroke-width: 1.4; }
    .pt0t2  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.4; }
    .pt0t3  { fill: #f6e3c8; stroke: #c08a3e; stroke-width: 1.4; }
    .pt0ink { fill: #1c1b18; font-size: 12px; }
    .pt0mut { fill: #6b6558; font-size: 12px; }
    .pt0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0pr { fill: #1e1c1a; stroke: #3e3a33; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0sh { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0seg { fill: #1d1d22; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0t1 { fill: #1f3247; stroke: #6f9fd6; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0t2 { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0t3 { fill: #47351c; stroke: #d1a15a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0ink, :root:is([data-theme="dark"], [data-theme="black"]) .pt0ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt0mut { fill: #a19caf; }
  </style>
  <rect class="pt0bg" x="0" y="0" width="760" height="470" rx="10"/>
  <rect class="pt0pr" x="16" y="16" width="728" height="420" rx="8"/>
  <text class="pt0ttl" x="32" y="42">一个进程：下面这些只有一份，三个线程共用</text>
  <rect class="pt0sh" x="32" y="56" width="360" height="196" rx="6"/>
  <text class="pt0ink" x="44" y="78">虚拟地址空间（同一套页表）</text>
  <rect class="pt0t1" x="48" y="88" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="103">主线程的栈</text>
  <rect class="pt0t2" x="48" y="110" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="125">线程 2 的栈、TLS</text>
  <rect class="pt0t3" x="48" y="132" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="147">线程 3 的栈、TLS</text>
  <rect class="pt0seg" x="48" y="154" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="169">共享库（.so）</text>
  <rect class="pt0seg" x="48" y="176" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="191">堆</text>
  <rect class="pt0seg" x="48" y="198" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="213">.data / .bss（全局变量）</text>
  <rect class="pt0seg" x="48" y="220" width="200" height="20" rx="3"/>
  <text class="pt0ink" x="58" y="235">.text（代码）</text>
  <text class="pt0mut" x="262" y="104">每个线程的栈，</text>
  <text class="pt0mut" x="262" y="122">只是这份地址</text>
  <text class="pt0mut" x="262" y="140">空间里的一段：</text>
  <text class="pt0mut" x="262" y="158">拿到指针，别的</text>
  <text class="pt0mut" x="262" y="176">线程照样能读写</text>
  <rect class="pt0sh" x="408" y="56" width="320" height="40" rx="6"/>
  <text class="pt0ink" x="420" y="81">fd 表：打开的文件、socket、epoll</text>
  <rect class="pt0sh" x="408" y="104" width="320" height="40" rx="6"/>
  <text class="pt0ink" x="420" y="129">信号处理函数（sigaction 设的）</text>
  <rect class="pt0sh" x="408" y="152" width="320" height="40" rx="6"/>
  <text class="pt0ink" x="420" y="177">当前目录、umask、用户 ID</text>
  <rect class="pt0sh" x="408" y="200" width="320" height="52" rx="6"/>
  <text class="pt0ink" x="420" y="222">pid（= 线程组号 tgid）：</text>
  <text class="pt0ink" x="420" y="240">每个线程调 getpid() 都一样</text>
  <text class="pt0ttl" x="32" y="284">每个线程独占</text>
  <rect class="pt0t1" x="32" y="296" width="216" height="126" rx="6"/>
  <text class="pt0ttl" x="44" y="318">主线程（tid = pid）</text>
  <text class="pt0ink" x="44" y="338">寄存器：rip、rsp……</text>
  <text class="pt0ink" x="44" y="356">rsp 指着自己那段栈</text>
  <text class="pt0ink" x="44" y="374">fs 指着自己的 TLS</text>
  <text class="pt0ink" x="44" y="392">信号掩码、调度优先级</text>
  <text class="pt0ink" x="44" y="410">内核栈：进内核时用</text>
  <rect class="pt0t2" x="272" y="296" width="216" height="126" rx="6"/>
  <text class="pt0ttl" x="284" y="318">线程 2（自己的 tid）</text>
  <text class="pt0ink" x="284" y="338">寄存器：rip、rsp……</text>
  <text class="pt0ink" x="284" y="356">rsp 指着自己那段栈</text>
  <text class="pt0ink" x="284" y="374">fs 指着自己的 TLS</text>
  <text class="pt0ink" x="284" y="392">信号掩码、调度优先级</text>
  <text class="pt0ink" x="284" y="410">内核栈：进内核时用</text>
  <rect class="pt0t3" x="512" y="296" width="216" height="126" rx="6"/>
  <text class="pt0ttl" x="524" y="318">线程 3（自己的 tid）</text>
  <text class="pt0ink" x="524" y="338">寄存器：rip、rsp……</text>
  <text class="pt0ink" x="524" y="356">rsp 指着自己那段栈</text>
  <text class="pt0ink" x="524" y="374">fs 指着自己的 TLS</text>
  <text class="pt0ink" x="524" y="392">信号掩码、调度优先级</text>
  <text class="pt0ink" x="524" y="410">内核栈：进内核时用</text>
  <text class="pt0mut" x="24" y="458">颜色对应：每个线程的卡片和它在地址空间里那段栈同色。errno 是 thread_local 变量，放在各自的 TLS 里。</text>
</svg>

注意栈的位置：**每个线程的栈“独占”，只是说每个线程用自己那一段，而不是说别的线程碰不到。** 栈就在共用的地址空间里，线程 A 把自己栈上一个局部变量的地址交给线程 B，B 照样能读写；等 A 的函数返回，那块栈被下一次调用复用，B 手里的指针就悬空了。线程间传数据要放在堆上或全局变量里，原因就在这里。各段在地址空间里的具体位置见[进程地图](/zh/ref/cpp-linux/#segments)，栈里一帧放了什么见[函数调用栈帧](/zh/ref/stack-frame/)。

在自己机器上看一个进程的线程：

```bash
ls /proc/<pid>/task                          # 每个线程一个目录，目录名就是 tid
ps -L -o pid,tid,stat,comm -p <pid>          # pid 列都一样，tid 列各不相同
grep -E 'Tgid|Pid|Threads' /proc/<pid>/status
```

### 1.4 心智模型：进程是容器，线程是在里面跑的执行流

把 1.1–1.3 合起来，可以这样记：**进程是一份资源的容器，线程是在容器里跑的执行流。** 容器里装的是地址空间（CR3 指向的那份页表）、fd 表、信号处理函数、当前目录和用户身份；执行流自己只有“跑到哪了”：寄存器、栈、TLS、信号掩码、绑在哪个核。调度器放到核上跑的是执行流，一个容器里至少有一个。单线程进程就是只有一个执行流的容器，所以平时感觉不到这是两样东西。

拿不准一样东西归谁，就问它描述的是“这个程序”，还是“这一条执行流”：

- `errno` 归线程：它放在 TLS 里，否则一个线程的系统调用失败，会覆盖另一个线程刚要读的错误码。
- fd 归进程：一个线程 `close(fd)`，其他线程手里的同一个号也跟着失效，这个号还可能马上被别的 `open` 复用。
- 进程号归进程：`getpid()` 在每个线程里都一样，`gettid()` 才各不相同（1.1）。

后面几部分的结论，都能从这个模型直接推出来：

- **切换**：在同一个容器里换执行流，容器不用动，CR3 和 TLB 接着用；换到另一个容器，地址空间跟着换（第 4 部分）。
- **崩溃**：一个线程写坏了堆，坏的是整个容器，进程里所有线程一起完蛋（4.7）。
- **fork**：复制的是容器，执行流只带走调 fork 的那一个，所以多线程程序 fork 出的子进程里只剩一个线程（2.5）。
- **改页表**：页表是容器的，一个线程 `munmap`，容器里正在跑的其他线程都要陪着处理一次 TLB shootdown（4.5）。

内核里两者是同一种 `task_struct`（1.1），容器和执行流之间的界线由 `clone` 的标志来划：全都共用，是同一进程里的线程；全都复制，是新进程；中间也有别的组合（比如只共用地址空间、不共用 fd 表），只是很少用。

## 2. fork：复制一个进程

### 2.1 fork 返回两次：子进程从同一行接着跑

`fork` 创建一个子进程，它是调用者的副本：同样的代码、同样的内存内容、同样的寄存器，所以子进程也从 `fork` 返回的地方接着执行。两边唯一的区别是返回值：父进程拿到子进程的 pid，子进程拿到 0，程序靠它分岔：

```c
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

int num = 10;                          // 全局变量，在 .data 里

int main(void) {
    pid_t pid = fork();
    if (pid == 0) {                    // 子进程
        num += 100;
        printf("child  num=%d &num=%p\n", num, (void *)&num);
        return 0;
    }
    waitpid(pid, NULL, 0);             // 父进程：等子进程结束
    printf("parent num=%d &num=%p\n", num, (void *)&num);
    return 0;
}
```

输出里子进程是 110，父进程还是 10，可两边打印的 `&num` 是同一个地址。同一个虚拟地址读出不同的值，说明两个进程各有一套页表，同一个虚拟页被映射到了不同的物理页。这两个物理页是什么时候分开的，就是下一节的内容。

### 2.2 写时复制（copy-on-write）：先共用物理页，谁写谁复制

如果 fork 真把父进程的内存全拷一遍，一个用了 4 GiB 的进程，fork 一次就要拷 4 GiB，而大多数子进程紧接着就调 `exec` 换成别的程序，拷的东西全白费。所以内核这样做：

1. 复制页表，不复制物理页：子进程的页表项和父进程的指向同一批物理页，每页的引用计数加 1；
2. 把两边所有可写的私有页都改成只读，代码这类本来就只读的页不用动；
3. 之后任何一方写其中一页，因为页表项是只读的，CPU 触发缺页异常；
4. 内核在缺页处理里看出这是写时复制的页：分配一个新物理页，把原来那页的 4 KiB 拷过去，让写的一方的页表项指向新页、改回可写，再回去重新执行那条写指令。

<svg viewBox="0 0 760 356" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="写时复制：fork 之后父子两份页表的三项都指向同一批物理页 A、B、C，并且都改成只读；子进程写 num 所在的那一页后，内核复制出 B 的副本 B′，子进程那一项改指 B′ 并改回可写，B 只剩父进程在用" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .pt1bg  { fill: #fbfaf7; }
    .pt1pan { fill: #f7f4ee; stroke: #d6cfc2; stroke-width: 1.2; }
    .pt1pte { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .pt1pg  { fill: #ffffff; stroke: #8c8577; stroke-width: 1.3; }
    .pt1new { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.5; }
    .pt1ink { fill: #1c1b18; font-size: 12px; }
    .pt1mut { fill: #6b6558; font-size: 12px; }
    .pt1ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .pt1ln  { stroke: #8c8577; stroke-width: 1.3; fill: none; }
    .pt1hl  { stroke: #4f7a28; stroke-width: 1.8; fill: none; }
    .pt1hd  { fill: #8c8577; }
    .pt1hdg { fill: #4f7a28; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1pan { fill: #1e1c1a; stroke: #3e3a33; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1pte { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1pg { fill: #26231f; stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1new { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1ink, :root:is([data-theme="dark"], [data-theme="black"]) .pt1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1ln { stroke: #8a8478; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1hl { stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1hd { fill: #8a8478; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt1hdg { fill: #8fb257; }
  </style>
  <defs>
    <marker id="pt1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="pt1hd"/></marker>
    <marker id="pt1g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="pt1hdg"/></marker>
  </defs>
  <rect class="pt1bg" x="0" y="0" width="760" height="356" rx="10"/>
  <rect class="pt1pan" x="16" y="12" width="356" height="290" rx="8"/>
  <text class="pt1ttl" x="28" y="36">fork 之后：两边指着同一批物理页</text>
  <text class="pt1mut" x="28" y="66">父进程的页表</text>
  <rect class="pt1pte" x="28" y="74" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="38" y="89">.text · 只读</text>
  <rect class="pt1pte" x="28" y="100" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="38" y="115">num 所在页 · 只读</text>
  <rect class="pt1pte" x="28" y="126" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="38" y="141">堆 · 只读</text>
  <text class="pt1mut" x="28" y="184">子进程的页表</text>
  <rect class="pt1pte" x="28" y="192" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="38" y="207">.text · 只读</text>
  <rect class="pt1pte" x="28" y="218" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="38" y="233">num 所在页 · 只读</text>
  <rect class="pt1pte" x="28" y="244" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="38" y="259">堆 · 只读</text>
  <text class="pt1mut" x="246" y="66">物理内存</text>
  <rect class="pt1pg" x="246" y="80" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="256" y="97">物理页 A</text>
  <text class="pt1mut" x="256" y="113">2 个页表在用</text>
  <rect class="pt1pg" x="246" y="140" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="256" y="157">物理页 B</text>
  <text class="pt1mut" x="256" y="173">2 个页表在用</text>
  <rect class="pt1pg" x="246" y="200" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="256" y="217">物理页 C</text>
  <text class="pt1mut" x="256" y="233">2 个页表在用</text>
  <path class="pt1ln" d="M168,85 L244,98" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M168,111 L244,158" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M168,137 L244,218" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M168,203 L244,104" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M168,229 L244,164" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M168,255 L244,224" marker-end="url(#pt1a)"/>
  <rect class="pt1pan" x="388" y="12" width="356" height="290" rx="8"/>
  <text class="pt1ttl" x="400" y="36">子进程写 num 以后：缺页，复制一页</text>
  <text class="pt1mut" x="400" y="66">父进程的页表</text>
  <rect class="pt1pte" x="400" y="74" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="410" y="89">.text · 只读</text>
  <rect class="pt1pte" x="400" y="100" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="410" y="115">num 所在页 · 只读</text>
  <rect class="pt1pte" x="400" y="126" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="410" y="141">堆 · 只读</text>
  <text class="pt1mut" x="400" y="184">子进程的页表</text>
  <rect class="pt1pte" x="400" y="192" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="410" y="207">.text · 只读</text>
  <rect class="pt1new" x="400" y="218" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="410" y="233">num 所在页 · 可写</text>
  <rect class="pt1pte" x="400" y="244" width="140" height="22" rx="3"/>
  <text class="pt1ink" x="410" y="259">堆 · 只读</text>
  <text class="pt1mut" x="618" y="66">物理内存</text>
  <rect class="pt1pg" x="618" y="80" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="628" y="97">物理页 A</text>
  <text class="pt1mut" x="628" y="113">2 个页表在用</text>
  <rect class="pt1pg" x="618" y="140" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="628" y="157">物理页 B</text>
  <text class="pt1mut" x="628" y="173">只剩父进程在用</text>
  <rect class="pt1pg" x="618" y="200" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="628" y="217">物理页 C</text>
  <text class="pt1mut" x="628" y="233">2 个页表在用</text>
  <rect class="pt1new" x="618" y="250" width="114" height="40" rx="4"/>
  <text class="pt1ink" x="628" y="267">B′：B 的副本</text>
  <text class="pt1mut" x="628" y="283">子进程独占</text>
  <path class="pt1ln" d="M540,85 L616,98" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M540,111 L616,158" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M540,137 L616,218" marker-end="url(#pt1a)"/>
  <path class="pt1ln" d="M540,203 L616,104" marker-end="url(#pt1a)"/>
  <path class="pt1hl" d="M540,229 L616,268" marker-end="url(#pt1g)"/>
  <path class="pt1ln" d="M540,255 L616,226" marker-end="url(#pt1a)"/>
  <text class="pt1mut" x="24" y="326">fork 只复制页表，并把两边可写的私有页改成只读；谁先写，谁触发一次缺页，内核复制这一页、改回可写。</text>
  <text class="pt1mut" x="24" y="344">复制以后 B 只剩父进程在用，父进程再写它时，内核直接把那一项改回可写，不用再复制。</text>
</svg>

**fork 的代价因此分成两笔：fork 那一刻复制页表，之后每写一个共用页付一次缺页加 4 KiB 拷贝。** 第一笔和进程用了多少内存成正比，每 GiB 已用内存约几 ms 到十几 ms，所以一个几十 GiB 的进程 fork 一次，主线程会停顿几百 ms。第二笔是一次次摊开的，每次约 1–2 µs；如果父进程在 fork 之后大量写内存，被写到的页都要复制一份，最坏时内存用量接近翻倍。用快照做持久化的程序（比如 Redis 的 `BGSAVE`）就是这样：子进程慢慢把 fork 那一刻的内存写到磁盘，父进程照常改数据，改到哪页复制哪页。缺页本身怎么处理，见 [`new` 一次走到哪](/zh/ref/new-malloc-page-fault/)。

### 2.3 fork 之后的 fd：表复制一份，打开的文件是同一个

fd 只是 fd 表里的下标，表里每一项指向内核里一个“打开的文件”对象（`struct file`），文件偏移、打开方式（读写、`O_APPEND`、非阻塞）都记在这个对象里。fork 复制的是 fd 表，表项还指着原来那些对象，对象的引用计数加 1。所以父子两边的 fd 3 指的是同一个打开的文件，**连文件偏移都是共用的**：

```c
int fd = open("out.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
if (fork() == 0) {
    write(fd, "child\n", 6);
    _exit(0);
}
wait(NULL);
write(fd, "parent\n", 7);   // 接在 child 后面，不会从文件开头覆盖：偏移是共用的
```

这个规则能推出几件常见的事。子进程 `close(fd)` 只是去掉自己表里那一项，父进程不受影响，文件对象要等最后一个引用关掉才真正关闭；所以服务器 fork 出子进程处理连接以后，父进程必须关掉自己手里的那个连接 fd，否则子进程关了连接，对端也收不到 FIN。epoll 实例也是一个文件，fork 之后父子两边的 epoll fd 指向内核里同一个 `eventpoll`，共用同一棵红黑树和就绪链表（见 [epoll 那篇](/zh/ref/epoll-internals/)），一边 `epoll_ctl` 改了，另一边也看得到。

### 2.4 fork 加 exec：换掉整个程序

fork 出来的子进程还在跑父进程的代码，要运行另一个程序，就调 `exec` 系列函数。`exec` 丢掉当前的整个地址空间，按新程序的 ELF 文件重新建一份：代码段、数据段映射进来，新建堆和栈，从新程序的入口开始执行。pid 不变，父子关系不变，打开的 fd 默认也保留，只有设了 `O_CLOEXEC`（或 `FD_CLOEXEC`）的会在 exec 时关掉；设了处理函数的信号恢复默认处理，因为原来那些函数的代码已经不在了（设成忽略的仍然忽略）。

**写时复制让 fork 加 exec 很便宜：fork 时只复制页表，紧接着 exec 把这套页表整个扔掉，中间几乎没有页被真正复制。** 剩下的成本是复制页表本身，父进程很大时它仍然明显。所以还有两个更省的办法：`vfork` 让子进程直接借用父进程的地址空间、连页表都不复制，父进程暂停到子进程 exec 或 `_exit` 为止，代价是子进程在这之间不能改任何内存、不能从函数返回；`posix_spawn` 把 fork 加 exec 包成一个调用，glibc 用 `clone(CLONE_VM | CLONE_VFORK)` 加一块单独的栈实现它，既有 vfork 的速度，又没有那些限制。只是想启动一个程序时，用 `posix_spawn` 最省心。

### 2.5 多线程程序里 fork：子进程里只剩一个线程

一个有 8 个线程的进程调 fork，子进程里只有 1 个线程，就是调 fork 的那个；其他 7 个线程不会被复制。但内存是整份复制的，包括那 7 个线程正拿着的锁：

```cpp
std::mutex m;

// 线程 A：
{
    std::lock_guard<std::mutex> g(m);
    // ……拿着锁干活，这时候线程 B 调了 fork
}

// 线程 B：
if (fork() == 0) {
    std::lock_guard<std::mutex> g(m);   // 子进程里的 m 是“已锁”状态的副本，
                                        // 拿锁的线程 A 在子进程里不存在：永远等下去
}
```

子进程里那把锁的状态是“被线程 A 锁着”，可 A 在子进程里根本不存在，没有人会去解锁。**所以多线程程序 fork 之后，子进程在 exec 之前只能调异步信号安全的函数**（`write`、`dup2`、`close`、`exec` 这类，清单见 `man 7 signal-safety`），不能用 `printf`、不能 `new`，因为谁也不知道 fork 那一刻哪个线程正拿着它们内部的锁。glibc 会在 fork 前后处理好自己 malloc 的锁，但你自己的锁、第三方库的锁它管不到；`pthread_atfork` 能注册 fork 前后的回调去处理，但很难写对。实际的做法是：多线程程序要起子进程，就用 `posix_spawn`，或者 fork 之后立刻 exec。

## 3. 进程状态：一生经过哪几种

### 3.1 R、S、D、T、Z：ps 第一列字母的意思

`ps` 的 `STAT` 列、`top` 的 `S` 列，第一个字母就是任务当前的状态：

<svg viewBox="0 0 760 425" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="进程状态：创建后进入 R；等事件进入 S，事件到了或来信号回到 R；等磁盘 IO 进入 D，IO 完成回到 R；SIGSTOP 进入 T，SIGCONT 回到 R；退出后进入 Z，父进程 wait 以后彻底消失" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .pt2bg  { fill: #fbfaf7; }
    .pt2r   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.5; }
    .pt2s   { fill: #eaf2fb; stroke: #7aa2cf; stroke-width: 1.3; }
    .pt2d   { fill: #f6e3c8; stroke: #c08a3e; stroke-width: 1.3; }
    .pt2z   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .pt2g   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .pt2ink { fill: #1c1b18; font-size: 12px; }
    .pt2lab { fill: #6b6558; font-size: 11.5px; }
    .pt2ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .pt2ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .pt2hd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2r { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2s { fill: #1c2633; stroke: #4f74a0; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2d { fill: #47351c; stroke: #d1a15a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2z { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2g { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2ink, :root:is([data-theme="dark"], [data-theme="black"]) .pt2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2lab { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .pt2hd { fill: #a19caf; }
  </style>
  <defs><marker id="pt2a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="pt2hd"/></marker></defs>
  <rect class="pt2bg" x="0" y="0" width="760" height="425" rx="10"/>
  <rect class="pt2s" x="280" y="10" width="200" height="64" rx="6"/>
  <text class="pt2ttl" x="292" y="34">S：可中断睡眠</text>
  <text class="pt2ink" x="292" y="54">recv、epoll_wait、sleep</text>
  <rect class="pt2g" x="40" y="140" width="140" height="40" rx="6"/>
  <text class="pt2ink" x="52" y="165">fork / clone</text>
  <rect class="pt2r" x="300" y="120" width="160" height="80" rx="6"/>
  <text class="pt2ttl" x="312" y="144">R：可运行</text>
  <text class="pt2ink" x="312" y="164">正在 CPU 上跑，</text>
  <text class="pt2ink" x="312" y="182">或在运行队列里等核</text>
  <rect class="pt2d" x="560" y="120" width="180" height="60" rx="6"/>
  <text class="pt2ttl" x="572" y="144">D：不可中断睡眠</text>
  <text class="pt2ink" x="572" y="164">等磁盘 IO，信号也叫不醒</text>
  <rect class="pt2g" x="300" y="260" width="160" height="56" rx="6"/>
  <text class="pt2ttl" x="312" y="284">T：停止</text>
  <text class="pt2ink" x="312" y="304">被暂停或被调试器跟踪</text>
  <rect class="pt2z" x="560" y="250" width="180" height="60" rx="6"/>
  <text class="pt2ttl" x="572" y="274">Z：僵尸</text>
  <text class="pt2ink" x="572" y="294">已退出，只剩一条记录</text>
  <rect class="pt2g" x="560" y="346" width="180" height="40" rx="6"/>
  <text class="pt2ink" x="572" y="371">被回收，pid 可以再用</text>
  <path class="pt2ln" d="M180,160 L298,160" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="239" y="152" text-anchor="middle">新建</text>
  <path class="pt2ln" d="M350,120 L350,76" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="342" y="102" text-anchor="end">等事件</text>
  <path class="pt2ln" d="M410,74 L410,118" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="418" y="102">事件到了、来信号</text>
  <path class="pt2ln" d="M460,146 L558,146" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="509" y="140" text-anchor="middle">等磁盘 IO</text>
  <path class="pt2ln" d="M560,170 L462,170" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="511" y="188" text-anchor="middle">IO 完成</text>
  <path class="pt2ln" d="M350,200 L350,258" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="342" y="240" text-anchor="end">SIGSTOP、Ctrl-Z</text>
  <path class="pt2ln" d="M410,260 L410,202" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="418" y="240">SIGCONT</text>
  <path class="pt2ln" d="M445,200 L445,214 L520,214 L520,280 L558,280" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="528" y="240">exit、被信号杀死</text>
  <path class="pt2ln" d="M650,310 L650,344" marker-end="url(#pt2a)"/>
  <text class="pt2lab" x="658" y="332">父进程 wait</text>
  <text class="pt2lab" x="24" y="412">课本里的“就绪”和“运行”在 Linux 里都是 R；“阻塞”分成 S 和 D 两种，差别在信号能不能把它叫醒。</text>
</svg>

**R 不等于正在跑，而是“只差一个 CPU”**：正在某个核上执行的，和在运行队列里排队等核的，都显示 R。课本的三态模型把这两种分成“运行”和“就绪”，Linux 不分，因为对任务自己来说没有区别，轮到它就跑。

**S 是绝大多数进程的常态**。一个空闲的服务器进程睡在 `epoll_wait` 里，一个 shell 睡在 `read` 里等你敲键盘，都是 S：它们在等一个事件，事件来了被叫醒回到 R（epoll 那篇里“睡在等待队列上”说的就是这个状态）。“可中断”是说信号也能把它叫醒，所以 `Ctrl-C` 能打断一个睡在 `read` 里的程序，那次系统调用返回 `EINTR`。

D 也是睡着在等，但信号叫不醒，`kill -9` 也要等它醒来以后才生效。内核在一些不能半途放弃的等待里用这个状态，最常见的是等磁盘 IO：读一页文件读到一半被信号打断，内核没法把这件事干净地撤回。D 正常只持续几 µs 到几 ms；如果 `ps` 里一批进程长时间卡在 D，通常是磁盘或网络文件系统（NFS）出了问题，它们都在等一个不回来的 IO。D 状态的任务也算进系统负载（load average），所以 CPU 很闲、负载却很高时，先看有没有一堆 D。

T 是被 `SIGSTOP` 或 `Ctrl-Z`（`SIGTSTP`）暂停，`SIGCONT` 让它继续；被调试器停住时显示小写的 `t`。Z 是已经退出、还没被父进程回收，下一节讲。

在自己机器上看：

```bash
ps -eo pid,ppid,stat,nlwp,cmd | head          # stat 第一个字母是状态，nlwp 是线程数
grep -E 'State|PPid|ctxt_switches' /proc/<pid>/status
# voluntary_ctxt_switches：自己睡下让出 CPU 的次数（进了 S 或 D）
# nonvoluntary_ctxt_switches：时间片用完被换下的次数
```

### 3.2 僵尸进程（zombie）：已经退出，等父进程来收

进程退出时，内核马上释放它的内存、关掉它的 fd，但留下 `task_struct` 里的一小部分：pid、退出码、用了多少 CPU 时间。留着它是因为父进程可能想知道子进程是怎么结束的，要等父进程调 `wait` 或 `waitpid` 把退出码取走，内核才删掉这条记录、把 pid 还回去。从退出到被 `wait` 之间，它就是僵尸进程，`ps` 里显示 `Z`，后面标着 `<defunct>`。

**僵尸进程已经死了，所以 `kill -9` 对它没用：信号要发给一个还在跑的进程才有意义。** 它几乎不占内存，危害在于占着 pid：系统的 pid 有上限（`/proc/sys/kernel/pid_max`，小系统默认 32768，64 位的发行版常设成 4194304），父进程一直不收，僵尸越积越多，最后 fork 会因为没有 pid 可用而失败。要清掉它，只能让父进程去 `wait`，或者杀掉父进程，让它变成孤儿，交给新的父进程去收。

`wait` 的行为也由此而来：有子进程已经是僵尸时，它立刻返回那个子进程的 pid 并把它收掉；子进程都还活着时，它阻塞到有一个退出；一个子进程都没有了，才返回 -1，`errno` 是 `ECHILD`。

### 3.3 孤儿进程（orphan）：父进程先走了

父进程先退出，子进程还在跑，子进程就成了孤儿。内核会给它重新找一个父进程：默认是 pid 1 的 init（现在通常是 systemd）；如果它的某个祖先进程用 `prctl(PR_SET_CHILD_SUBREAPER)` 把自己设成了“收养者”（subreaper），就交给离它最近的那个。新父进程负责在它退出时 `wait`，init 一直在循环做这件事，所以孤儿本身没有害处，等它自己退出时会被收掉。

容器里有一个由此而来的坑：容器里 pid 为 1 的是你的程序，不是 init。如果你的程序 fork 了子进程，子进程又生了孙进程，子进程先退出，孙进程就交给了你的程序；而你的程序从来不 `wait` 它不认识的进程，孙进程退出后就一直是僵尸。所以容器常用一个很小的 init（比如 `docker run --init` 带的 tini）当 pid 1，专门负责收养和回收。

### 3.4 不留僵尸的三种写法

最直接的是父进程在合适的地方 `waitpid`。父进程有自己的事件循环、不能阻塞等时，就在 `SIGCHLD` 里收：子进程退出时内核给父进程发 `SIGCHLD`，处理函数里循环调非阻塞的 `waitpid`：

```c
#include <errno.h>
#include <signal.h>
#include <sys/wait.h>

static void on_child(int sig) {
    (void)sig;
    int saved = errno;                          // waitpid 会改 errno，别弄坏被打断的代码
    while (waitpid(-1, NULL, WNOHANG) > 0) {}   // 循环收：几个子进程同时退出，信号只来一次
    errno = saved;
}

int install_reaper(void) {
    struct sigaction sa = {0};
    sa.sa_handler = on_child;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_RESTART | SA_NOCLDSTOP;    // 被打断的系统调用自动重来；子进程暂停时不通知
    return sigaction(SIGCHLD, &sa, NULL);
}
```

必须用循环，是因为同一种信号在被处理之前只记一次：3 个子进程几乎同时退出，父进程可能只收到 1 个 `SIGCHLD`，只 `waitpid` 一次就会漏掉两个。

另外两种写法都是让别人去收。一种是把 `SIGCHLD` 设成忽略（`signal(SIGCHLD, SIG_IGN)`），Linux 上这样设了以后，子进程退出时直接被回收，不留僵尸，代价是父进程再也拿不到它们的退出码。另一种是两次 fork：父进程 fork 出子进程，子进程再 fork 出孙进程后立刻退出，父进程 `wait` 收掉子进程，孙进程成了孤儿，交给 init 去收；守护进程传统上就这样脱离启动它的终端和父进程。

## 4. 切换的代价：同一进程的线程之间，和不同进程之间

“线程比进程轻”常被说成：线程切换不用换页表、不用刷 TLB，只换几个寄存器，所以快一个数量级。前半句对，后半句不对。同一进程的两个线程互相切换，和两个进程互相切换，连同唤醒、调度在内都在 1 到几 µs，直接开销差得不多。**线程真正轻的地方在切换之后：接着跑的线程，还能用上一个线程留在 TLB 和缓存里的东西。** 下面一路追到硬件：切换做了什么，页表和 TLB 是每个进程一份还是每个核一份，线程换了个核会怎样，改页表时又要通知谁。

### 4.1 一次切换做了什么：保存、换栈、恢复

线程进内核的时候（系统调用、中断、被抢占），用户态的寄存器已经存到它自己的内核栈上了。调度器决定换下一个任务后，`context_switch()` 做两件事：

- **换地址空间**（`switch_mm`）：下一个任务属于另一个进程，才把 CR3 改成那个进程的页表（4.2）。同一个进程的线程共用一个 `mm`，这一步直接跳过。
- **换执行现场**（`switch_to`）：保存当前任务在内核里的几个寄存器和栈指针，换到下一个任务的内核栈，恢复它的寄存器；回用户态时，再从它的内核栈上把用户态寄存器取回来。浮点和向量寄存器也要换，开了 AVX-512 时这一份就有 2 KiB 多。

这些都在 CPU 上做，不碰磁盘、不等别人。1 到几 µs 里，更多花在进出内核、唤醒和调度器挑下一个任务上。**线程切换和进程切换在这一步只差一处：要不要改写 CR3。**

### 4.2 CR3：每个核一个，指向页表的根

程序里用的是虚拟地址，访存前要翻译成物理地址，翻译规则就是进程的页表。x86-64 上它是一棵 4 级的树，每级 512 项，根那一页的物理地址放在 **CR3** 里。**CR3 是每个核一个的寄存器**，存的是这个核上正在跑的那个地址空间的页表根。

页表是每个进程一份（内核里的 `mm_struct`），同一进程的线程共用它。所以同一时刻，几个核的 CR3 可以指向同一份页表（同一进程的几个线程在各自的核上跑），也可以指向不同的页表（跑的是不同进程）。切到同一进程的另一个线程，CR3 的值本来就对，不用动；切到别的进程，要写入那个进程页表根的物理地址。从这一刻起，这个核看到的是另一份地址空间：同一个虚拟地址，翻译出来是另一个物理页，或者根本没有映射。

<svg viewBox="0 0 760 356" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="两个核各有一个 CR3 和一份私有的 TLB。核 0 的 CR3 指向进程 A 的页表，进程 A 的线程 T1、T2、T3 共用这一份；核 1 的 CR3 指向进程 B 的页表。同进程的线程切换 CR3 不动；换到进程 B 要改写 CR3，没有 PCID 时 TLB 跟着清空。线程换到核 1 时，核 1 的 CR3 也指向页表 A，只是核 1 的 TLB 里还没有 A 的项。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .cx-bg    { fill: #fbfaf7; }
    .cx-panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .cx-muted { fill: #6b6558; }
    .cx-reg   { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .cx-tlb   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .cx-pt    { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .cx-hot   { fill: #f6ddd6; stroke: #c15b3f; stroke-width: 1.8; }
    .cx-off   { fill: none; stroke: #b4ae9f; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .cx-arrow { stroke: #8a8474; stroke-width: 2; fill: none; marker-end: url(#ahcx); }
    .cx-ipi   { stroke: #c15b3f; stroke-width: 2; fill: none; marker-end: url(#ahcx2); }
    .cx-title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .cx-lbl   { fill: #3a372f; font-size: 11px; }
    .cx-cap   { fill: #6b6558; font-size: 10.5px; }
    .cx-red   { fill: #c15b3f; font-size: 11px; font-weight: 700; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-panel { fill: #201f26; stroke: #3a3945; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-muted { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-reg { fill: #2a2933; stroke: #47454f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-tlb { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-pt { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-hot { fill: #4a2f2c; stroke: #e0795b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-off { stroke: #5a5664; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-arrow { stroke: #9a9384; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-ipi { stroke: #e0795b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-title { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-lbl { fill: #d7d3c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-cap { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-red { fill: #e0795b; }
  </style>
  <defs>
    <marker id="ahcx" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ahcx2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="cx-bg" x="0" y="0" width="760" height="356" rx="10"/>
  <text class="cx-title" x="24" y="30">CR3 每个核一个，页表每个进程一份</text>
  <rect class="cx-panel" x="24" y="48" width="380" height="124" rx="8"/>
  <text class="cx-muted" x="40" y="70" font-size="12" font-weight="700">核 0：正在跑进程 A 的线程 T1</text>
  <rect class="cx-tlb" x="40" y="84" width="196" height="72" rx="6"/>
  <text class="cx-lbl" x="52" y="106" font-weight="700">TLB（本核私有）</text>
  <text class="cx-cap" x="52" y="124">缓存 A 的地址翻译</text>
  <text class="cx-cap" x="52" y="142">几十到几千项</text>
  <rect class="cx-reg" x="252" y="84" width="136" height="72" rx="6"/>
  <text class="cx-lbl" x="264" y="106" font-weight="700">CR3</text>
  <text class="cx-cap" x="264" y="124">页表 A 根页的</text>
  <text class="cx-cap" x="264" y="142">物理地址</text>
  <rect class="cx-panel" x="24" y="188" width="380" height="124" rx="8"/>
  <text class="cx-muted" x="40" y="210" font-size="12" font-weight="700">核 1：正在跑进程 B</text>
  <rect class="cx-tlb" x="40" y="224" width="196" height="72" rx="6"/>
  <text class="cx-lbl" x="52" y="246" font-weight="700">TLB（本核私有）</text>
  <text class="cx-cap" x="52" y="264">缓存 B 的地址翻译</text>
  <text class="cx-cap" x="52" y="282">几十到几千项</text>
  <rect class="cx-reg" x="252" y="224" width="136" height="72" rx="6"/>
  <text class="cx-lbl" x="264" y="246" font-weight="700">CR3</text>
  <text class="cx-cap" x="264" y="264">页表 B 根页的</text>
  <text class="cx-cap" x="264" y="282">物理地址</text>
  <rect class="cx-panel" x="468" y="48" width="268" height="124" rx="8"/>
  <text class="cx-muted" x="484" y="70" font-size="12" font-weight="700">进程 A（一个 mm）</text>
  <rect class="cx-pt" x="484" y="84" width="236" height="36" rx="6"/>
  <text class="cx-lbl" x="496" y="107" font-weight="700">页表 A（4 级）</text>
  <text class="cx-cap" x="484" y="142">线程 T1、T2、T3 共用这一份</text>
  <text class="cx-cap" x="484" y="160">同进程的线程切换：CR3 不动</text>
  <rect class="cx-panel" x="468" y="188" width="268" height="124" rx="8"/>
  <text class="cx-muted" x="484" y="210" font-size="12" font-weight="700">进程 B（另一个 mm）</text>
  <rect class="cx-pt" x="484" y="224" width="236" height="36" rx="6"/>
  <text class="cx-lbl" x="496" y="247" font-weight="700">页表 B（4 级）</text>
  <text class="cx-cap" x="484" y="282">核 0 换到进程 B：CR3 改写成这里</text>
  <text class="cx-cap" x="484" y="300">没有 PCID 时，TLB 跟着清空</text>
  <path class="cx-arrow" d="M388 120 L482 102"/>
  <path class="cx-arrow" d="M388 260 L482 242"/>
  <text class="cx-red" x="24" y="338">线程换到核 1：核 1 的 CR3 也指向页表 A，翻译规则没变，只是核 1 的 TLB 里还没有 A 的项。</text>
</svg>

> 图：CR3 和 TLB 跟着核走，页表跟着进程走。同一进程的线程查的是同一份页表，切过去 CR3 不用动；换进程才要改写 CR3。

### 4.3 TLB：地址翻译的缓存，也是每个核一份

每次访存都去 4 级页表里查一遍太慢，所以每个核有自己的 **TLB**（translation lookaside buffer），缓存最近用过的翻译：L1 dTLB 64–96 项，二级的 STLB 1500–3000 项，每项管一页（[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/) 第 3.2 节讲了它能盖住多大的内存、大页怎么帮忙）。TLB 命中，翻译几乎不花时间；没命中，硬件的 page walker 从 CR3 出发，一级一级往下读页表项。页表项本身也是内存里的数据，会被缓存在 L1、L2、L3 里，所以从内存读一个数，TLB 命中约 70–90 ns，没命中约 85–120 ns，只多出 15–30 ns（[速查 2.1](/zh/ref/cpu-memory/#latency)）。4 级页表项全都要从内存读的情况很少，真遇上了，一次就是几百 ns。

TLB 里的每一项都是按某一份页表算出来的。改写了 CR3，旧的翻译对新进程就是错的，所以没有 PCID 时，写 CR3 会把 TLB 里所有非全局的项清掉；内核的映射在每个进程里都一样，标了全局（global），不跟着清。**PCID**（process-context identifier）给每一项打上地址空间的标签，写 CR3 时带上新标签，就不用清：旧进程的项还在，只是新进程查不到，等它切回来还能接着用。Linux 从 4.14 起用 PCID，但每个核只轮换几个号，TLB 总共也就几千项，一个进程歇了一阵再回来，它的项多半已经被别人挤掉了。

同一进程的线程之间切换，CR3 不动，TLB 里的项全部有效，接着跑的线程直接用。**这才是“线程更轻”里真正属于硬件的那一部分。**

### 4.4 切换之后要重新热起来，换核也一样

换进程之后，新进程的数据多半已经不在 L1、L2 里（每个核只有几十 KiB 和一两 MiB），每次访问都要去 L3 或内存取；TLB 里它的项也少，每碰一个新页就走一遍页表。同一进程的线程好一些：代码、堆上共享的数据、TLB 里的翻译都还热，但各自的栈和私有数据未必在缓存里。这笔账不记在切换本身上，而是摊在切换之后的一段执行里。**只测切换本身，会低估切换的代价。**

线程被调度器挪到另一个核，是另一种“切换之后”。新核的 CR3 指向同一份页表，翻译规则没变，什么都不用清；可是 **L1、L2 和 TLB 都是每个核私有的**，线程在原来那个核上攒下的热数据、指令和地址翻译都留在那里，到了新核，数据要从 L3（另一个插槽的话，从远端内存）重新取，TLB 也要一页一页重新查表填回来。绑核（[#1](/zh/posts/cpu-affinity-core-isolation-numa/)）消掉的就是这一笔。线程走了，它在原来那个核的 TLB 里留下的项也不会跟着消失，改页表时这些旧项也得处理（4.5）。

### 4.5 改页表：TLB 没有 MESI

数据缓存之间有 [MESI](/zh/posts/low-latency-mesi-cache-coherence/)：一个核写一条行，硬件自动让别的核的副本作废。**TLB 没有这套机制：内存里的页表项被改了，别的核 TLB 里缓存的旧翻译不会自己作废。** 内核改了页表（`munmap`、`mprotect`、搬页、合并透明大页）之后，先用 `invlpg` 作废本核的项，再给可能拿着旧翻译的核发一个核间中断（IPI）。对方进中断处理程序作废对应的项、回话；发起的核等齐所有回话才能接着往下走，因为在那之前，别的核还可能顺着旧翻译写到一个已经还给系统的物理页。这一来一回叫 **TLB shootdown**。

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="核 2 上的冷线程调 munmap：改页表项，invlpg 作废本核的项，给正在跑这个进程的核发 IPI，等齐回话才往下走。同进程热线程所在的核 5 和跑着同进程另一个线程的核 3 都收到 IPI；核 7 刚跑过这个进程、现在在跑别的进程，不发 IPI，切回来时发现页表改过再自己清。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <rect class="cx-bg" x="0" y="0" width="760" height="300" rx="10"/>
  <text class="cx-title" x="24" y="30">TLB 没有 MESI：改了页表，要发 IPI 一个个通知</text>
  <rect class="cx-reg" x="24" y="60" width="250" height="114" rx="6"/>
  <text class="cx-lbl" x="36" y="84" font-weight="700">核 2：冷线程调 munmap</text>
  <text class="cx-cap" x="36" y="106">① 改页表项</text>
  <text class="cx-cap" x="36" y="124">② invlpg 作废本核的项</text>
  <text class="cx-cap" x="36" y="142">③ 给正在跑这个进程的核发 IPI</text>
  <text class="cx-cap" x="36" y="160">④ 等齐回话才往下走</text>
  <path class="cx-ipi" d="M274 100 L428 73"/>
  <text class="cx-red" x="336" y="78">IPI</text>
  <path class="cx-ipi" d="M274 124 L428 137"/>
  <text class="cx-red" x="336" y="146">IPI</text>
  <rect class="cx-hot" x="430" y="48" width="306" height="50" rx="6"/>
  <text class="cx-lbl" x="442" y="68" font-weight="700">核 5：热线程（同一进程，已隔离）</text>
  <text class="cx-cap" x="442" y="86">被打断：进内核作废这一项，再回话</text>
  <rect class="cx-tlb" x="430" y="112" width="306" height="50" rx="6"/>
  <text class="cx-lbl" x="442" y="132" font-weight="700">核 3：同进程的另一个线程正在跑</text>
  <text class="cx-cap" x="442" y="150">也在名单上，同样被打断</text>
  <rect class="cx-off" x="430" y="176" width="306" height="50" rx="6"/>
  <text class="cx-lbl" x="442" y="196" font-weight="700">核 7：刚跑过，现在在跑别的进程</text>
  <text class="cx-cap" x="442" y="214">不发 IPI：切回来时发现页表改过，再自己清</text>
  <text class="cx-red" x="24" y="262">发起的核同步等待；收到 IPI 的核被打断一次，绑核和 isolcpus 都挡不住。</text>
  <text class="cx-cap" x="24" y="282">通知谁：此刻 CR3 还指着这份页表的核。改的是内核自己的映射，才要通知所有核。</text>
</svg>

> 图：数据缓存靠硬件互相作废，TLB 靠内核发中断。正在跑这个进程的核都要停下来处理一次，发起的核等它们全部回话；不在跑的核留到切回来时再清。

IPI 发给谁，不是“正在跑这个进程的核”，也不是“跑过它的所有核”，而是**此刻 CR3 还指着这份页表的核**。

1. **为什么按 CR3 划线**
   - **TLB 项只有一个来源**：查页表。CPU 查的永远是自己 CR3 指着的那份，推测执行也会提前去查。
   - **CR3 指着这份页表的核**：手里可能有旧项，下一刻还可能从这份表里填进新项，必须当场通知。
   - **CR3 已经指着别的页表的核**：再也查不到这份表，最多留着几项旧的。有 PCID 时，这些旧项带着这个进程的标签，换了进程也不会被清掉。可这些旧项要等它切回这个进程才用得上，而切回来必然经过内核的 `switch_mm`。
   - **所以**：前一种核必须马上打断，后一种可以等它切回来时自己处理。
2. **内核怎么做**
   - **名单**：每个地址空间记一份核的集合 `mm_cpumask`，核切到这个进程时把自己加进去。发 IPI 前，内核再看一遍每个核此刻装着的地址空间（每核变量 `loaded_mm`），只给还装着这一份的核发。
   - **版本号**：每个地址空间记一个页表版本号 `tlb_gen`，每改一次加一；每个核记着自己对这个地址空间刷到了哪一版。核切回这个进程时比一下，落后了就先清再跑，不用打断一个正在干别的事的核。
   - **结论**：**改用户空间的页表，只打断此刻还装着这份页表的核；跑过、已经切走的核，把清理推迟到切回来那一刻，自己做。**
3. **lazy TLB：CR3 还指着，但先不打断**
   - **是什么**：内核线程没有自己的用户地址空间，切过去时不换 CR3，沿用上一个进程的页表。这叫 lazy TLB。
   - **平常改页表**：不发 IPI。内核线程不访问用户地址，旧项暂时用不上；它离开这个状态时，按版本号补清。
   - **释放页表页时要发**：CR3 还指着这套页表，推测执行可能顺着它读到已经还给系统的页表页，所以这时 lazy 的核也要当场通知。
4. **内核自己的映射**：`vmalloc` 出来的区域、加载的模块，在每个地址空间里都有，改了就要通知所有核。内核会攒一批，再一起清。
5. **硬件广播**：ARM64 的 `TLBI … IS` 和较新 AMD 的 `INVLPGB` 由硬件把作废请求广播给所有核，对方不进中断。这种情况下不按进程挑核，也就没有上面这份名单。

线程多的进程要记住一点：**同一个进程里，一个线程 `munmap`，正在跑的其他线程都要陪着被打断一次。** 绑核和 `isolcpus` 挡不住它，因为 IPI 按 `mm_cpumask` 投递，不经过调度器；低延迟程序怎么从源头上不改页表，见 [#3](/zh/posts/hot-path-memory-allocators/) 第 2 节。

### 4.6 三种情况放在一起

| | CR3 | TLB | L1、L2 |
|---|---|---|---|
| 同一进程的线程，同一个核 | 不动 | 接着用 | 共享的数据还热，各自的栈和私有数据未必 |
| 线程换核 | 新核指向同一份页表 | 新核上是冷的，按需查表填回来 | 冷，从 L3 或内存重新取 |
| 换进程 | 改写 | 没有 PCID 就清空；有 PCID 也多半被挤掉了 | 多半被上一个任务挤掉了 |

差别都在切换之后。创建也是一样的道理：线程用 `clone` 共用 `mm`，不复制页表；`fork` 要给子进程复制一份页表（2.2）。

### 4.7 开线程还是开进程

把上面几节合起来，取舍就清楚了。线程共用地址空间，所以创建快、切换后缓存热、交换数据只要传一个指针；代价是没有隔离，一个线程越界写坏了堆、或者段错误，整个进程一起完蛋，共享的数据还得自己加锁。进程各有一份地址空间，一个崩了不影响别的，可以分别以不同的用户、不同的权限运行；代价是创建慢、交换数据要走进程间通信（管道、共享内存、socket，见[进程间通信](/zh/ref/ipc/)）。

所以要的是并行干同一件事、频繁共享数据，用线程；要的是隔离，一个出错不能拖垮其他，或者要跑另一个程序，用进程。浏览器给每个标签页一个进程、Web 服务器用一个进程里的线程池处理请求，就是这两种取舍。
