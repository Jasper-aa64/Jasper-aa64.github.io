---
title: "文件 IO：fd、打开的文件和 inode"
date: 2026-11-02
slug: "file-io"
description: "fd 只是进程 fd 表里的一个下标，状态分在后面两层：内核里“打开的文件”记着偏移和打开方式，inode 记着文件本身。dup 和 fork 共用前一层，两次 open 只在 inode 上相遇；O_APPEND、shell 的 > 和 2>&1、fork 后父子写同一个日志，都从这三层推出来。再讲 read/write 的返回值（少读、EINTR、0）、lseek 和空洞文件、stdio 的用户态缓冲为什么让输出乱序或出现两次、stat 里的类型和权限、硬链接和软链接、页缓存和 fsync、守护进程怎么处理 0/1/2，最后是 C++17 的 std::filesystem。"
summary: "fd → 打开的文件（偏移、O_APPEND、O_NONBLOCK）→ inode（大小、权限、链接数、数据块）。dup 和 fork 复制的是指向第二层的指针，所以共用偏移；重定向就是 open 加 dup2。数据到磁盘前要过两层缓冲：FILE* 的用户态缓冲靠 fflush 推进内核，页缓存靠 fsync 推上磁盘。"
toc: true
group: cpplinux
topic: proc
weight: 116
---

## 1. fd：进程手里的一个下标

### 1.1 文件描述符（file descriptor）：fd 表里的下标 {#fd}

`open` 返回的是一个小整数。内核给每个进程维护一张 fd 表，fd 就是这张表的下标，表项是一个指针，指向内核里代表“这次打开”的对象。进程拿不到这个指针，只能拿着下标请内核去查，所以用户态伪造不了 fd，一个进程的 fd 3 拿到另一个进程里也毫无意义。

分配规则只有一条：**`open`、`dup`、`socket`、`pipe` 都返回当前最小的空闲下标。** 0、1、2 在进程启动时已经被占了，分别是标准输入、标准输出、标准错误。它们不是什么特殊对象，只是 shell 在 exec 之前替你打开好的三个 fd，通常指向终端。第一个 `open` 因此拿到 3；先 `close(1)` 再 `open`，拿到的就是 1，之后所有 `printf` 都写进这个文件，早年的重定向就是这么做的（`dup2` 把它变成了一步，见 3.1）。

fd 表不是固定 1024 项的数组，内核按需扩大。1024 是每个进程同时能打开的 fd 个数的默认软上限（`ulimit -n`，即 `RLIMIT_NOFILE`），超了 `open` 返回 `EMFILE`（Too many open files），连接很多的服务器启动前通常要把它调高。

### 1.2 三层：fd 表、打开的文件、inode {#three-levels}

一次 `open` 在内核里留下两样东西。一是“打开的文件”（POSIX 叫 open file description，Linux 里是 `struct file`），记着**这次打开的状态**：当前偏移、打开方式（只读或只写、`O_APPEND`、`O_NONBLOCK`）、引用计数；二是 fd 表里的一项，指向它。`struct file` 再指向 inode，inode 记着**文件本身**：类型、权限、属主、大小、时间、链接数、数据在磁盘的哪些块上。一个文件在一个文件系统里只有一个 inode，不管被打开多少次。

“这个文件”“这次打开”“这个进程里的编号”本来就是三件事，各有各的共享方式，所以分成三层：

<svg viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="三层结构：进程 A 的 fd 3 和 dup 出来的 fd 4 指向同一个打开的文件 X，fork 出来的进程 B 继承的 fd 3 也指向 X；A 的 fd 5 是对同一路径的另一次 open，指向打开的文件 Y；X 和 Y 都指向同一个 inode" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .fabg  { fill: #fbfaf7; }
    .fafd  { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.2; }
    .fagr  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .faox  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .faoy  { fill: #e3eaf6; stroke: #6f86b3; stroke-width: 1.3; }
    .fain  { fill: #f6e7c8; stroke: #b8954a; stroke-width: 1.3; }
    .faink { fill: #1c1b18; font-size: 12.5px; }
    .fabd  { fill: #1c1b18; font-size: 12.5px; font-weight: 700; }
    .famut { fill: #6b6558; font-size: 12px; }
    .fattl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .faln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .fahd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fabg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fafd { fill: #1d1c22; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fagr { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .faox { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .faoy { fill: #26304a; stroke: #7f97c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fain { fill: #45381f; stroke: #c9a55a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .faink, :root:is([data-theme="dark"], [data-theme="black"]) .fabd, :root:is([data-theme="dark"], [data-theme="black"]) .fattl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .famut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .faln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fahd { fill: #a19caf; }
  </style>
  <defs><marker id="faa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="fahd"/></marker></defs>
  <rect class="fabg" x="0" y="0" width="760" height="340" rx="10"/>
  <text class="fattl" x="24" y="28">fd 表：每个进程一张</text>
  <text class="fattl" x="300" y="28">打开的文件：每次 open 一个</text>
  <text class="fattl" x="600" y="28">inode：每个文件一个</text>
  <text class="famut" x="24" y="52">进程 A</text>
  <rect class="fagr" x="24" y="60" width="176" height="26" rx="4"/>
  <text class="faink" x="34" y="78">0 1 2 → 终端</text>
  <rect class="fafd" x="24" y="90" width="176" height="26" rx="4"/>
  <text class="faink" x="34" y="108">3 = open("a.log")</text>
  <rect class="fafd" x="24" y="120" width="176" height="26" rx="4"/>
  <text class="faink" x="34" y="138">4 = dup(3)</text>
  <rect class="fafd" x="24" y="150" width="176" height="26" rx="4"/>
  <text class="faink" x="34" y="168">5 = open("a.log")</text>
  <text class="famut" x="24" y="206">进程 B：A fork 出来的</text>
  <rect class="fagr" x="24" y="214" width="176" height="26" rx="4"/>
  <text class="faink" x="34" y="232">0 1 2 → 终端</text>
  <rect class="fafd" x="24" y="244" width="176" height="26" rx="4"/>
  <text class="faink" x="34" y="262">3（继承）</text>
  <rect class="fafd" x="24" y="274" width="176" height="26" rx="4"/>
  <text class="famut" x="34" y="292">4、5 同理，箭头省略</text>
  <rect class="faox" x="300" y="80" width="230" height="74" rx="6"/>
  <text class="fabd" x="314" y="102">打开的文件 X</text>
  <text class="faink" x="314" y="122">偏移 120，只写，O_APPEND</text>
  <text class="famut" x="314" y="142">A 的 3、4 和 B 的 3 共用</text>
  <rect class="faoy" x="300" y="184" width="230" height="74" rx="6"/>
  <text class="fabd" x="314" y="206">打开的文件 Y</text>
  <text class="faink" x="314" y="226">偏移 0，只读</text>
  <text class="famut" x="314" y="246">另一次 open：偏移各算各的</text>
  <rect class="fain" x="600" y="112" width="136" height="116" rx="6"/>
  <text class="fabd" x="612" y="134">inode 8812</text>
  <text class="faink" x="612" y="154">大小、权限、属主</text>
  <text class="faink" x="612" y="172">时间、链接数</text>
  <text class="faink" x="612" y="190">数据块在哪</text>
  <text class="famut" x="612" y="214">没有文件名</text>
  <path class="faln" d="M200,103 L297,104" marker-end="url(#faa)"/>
  <path class="faln" d="M200,133 L297,120" marker-end="url(#faa)"/>
  <path class="faln" d="M200,163 C250,163 250,214 297,214" marker-end="url(#faa)"/>
  <path class="faln" d="M200,257 C255,257 250,146 297,146" marker-end="url(#faa)"/>
  <path class="faln" d="M530,117 L597,150" marker-end="url(#faa)"/>
  <path class="faln" d="M530,221 L597,192" marker-end="url(#faa)"/>
  <text class="famut" x="24" y="326">dup 和 fork 共用同一个打开的文件，所以共用偏移；两次 open 各有一个，只在 inode 上相遇。</text>
</svg>

图里每种箭头对应一种调用。`dup(3)` 在同一张表里再加一项，指向同一个打开的文件；fork 把整张 fd 表复制给子进程，表项还指着原来那些对象；对同一个路径再 `open` 一次，内核新建一个 `struct file`，偏移从 0 开始，和上一次只在 inode 上相遇。所以**判断两个 fd 会不会互相挪动偏移，只看它们是不是指向同一个打开的文件**：dup 出来的、fork 继承的会，各自 open 的不会。

有一个标志不在这三层的规律里：`FD_CLOEXEC` 记在 fd 表项上，不在打开的文件上，它是每个 fd 自己的，dup 出来的新 fd 默认不带。

### 1.3 一切皆文件（everything is a file）：同一套 read 和 write {#everything-is-a-file}

普通文件、目录、管道、socket、终端、`/dev/null`、epoll 实例、eventfd、timerfd，打开以后都是一个 `struct file`，都用 fd 引用。能做到这一点，是因为 `struct file` 带着一张函数表 `f_op`（`read`、`write`、`poll`、`release` 等），每种对象填自己的实现：同一个 `read`，落到 ext4 上是查页缓存，落到 socket 上是从接收队列取数据，落到管道上是从环形缓冲区取。系统调用这一层只认 fd，查到 `struct file` 以后调它的 `f_op->read`。

**好处是工具可以组合**：`cat` 不用知道它读的是文件还是管道，`epoll` 能同时等 socket 和 timerfd（[epoll 那篇](/zh/ref/epoll-internals/)），`close` 一个 fd 就能释放任何种类的资源。这个抽象也有不成立的地方：socket 和管道不能 `lseek`（返回 `ESPIPE`），普通文件上 `O_NONBLOCK` 不起作用，各种对象的 `read` 什么时候返回、返回多少也各不相同，下一节就是在处理这些差别。

## 2. open、read、write、lseek

### 2.1 open 的标志：一个 int 里的若干位 {#open-flags}

```c
int fd = open("data.log", O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
if (fd == -1) { perror("open"); return -1; }   // 失败返回 -1，原因在 errno 里
```

`flags` 是一个 int，每个标志占一位，所以用 `|` 拼起来。访问方式 `O_RDONLY`、`O_WRONLY`、`O_RDWR` 三选一，必须恰好给一个，其余标志各管一件事。

`O_CREAT` 在文件不存在时创建它，这时才用得上第三个参数 `mode`，最终权限是 `mode & ~umask`（5.2）。再加 `O_EXCL`，文件已经存在就失败，返回 `EEXIST`。**“检查不存在”和“创建”在内核里是一步**，两个进程同时抢，只有一个能成功，所以它常用来做锁文件、建唯一的临时文件；先用 `access` 查一遍再 `open` 就做不到，两步之间别人可能已经建好了。`O_TRUNC` 打开时把已有文件截成 0 长度，shell 的 `>` 带的就是它。

`O_APPEND` 让每次 `write` 之前先把偏移移到文件末尾，并且“移到末尾”和“写”是一个原子操作。不带它，多个进程各自 open 同一个日志文件，每个 `struct file` 都有自己的偏移，后写的会从自己的偏移处盖掉别人刚写的内容；自己先 `lseek(fd, 0, SEEK_END)` 再 `write` 也不行，两步之间别人可能已经把文件写长了。**多个进程往同一个文件追加，靠的就是 `O_APPEND`。** 在本地文件系统上，一次 `write` 的内容还会连成一段，不和别人的交错；NFS 上这两点都不保证。

`O_CLOEXEC` 给新 fd 带上 `FD_CLOEXEC`，exec 时自动关掉。fd 默认会跨过 exec 留给新程序，一个开着数据库连接或密钥文件的服务器 fork 出去执行外部命令，那个命令就继承了这些 fd。`open` 以后再用 `fcntl(fd, F_SETFD, FD_CLOEXEC)` 补上不够：多线程程序里，另一个线程可能恰好在这两步之间 fork 加 exec。所以 `socket`、`pipe2`、`accept4`、`epoll_create1`、`dup3` 都有对应的 `CLOEXEC` 标志，**在 fd 诞生的那一刻就设好**。

`O_NONBLOCK` 让本来会阻塞的读写立刻返回 -1，errno 设成 `EAGAIN`。它只对管道、socket、终端这类“数据什么时候来说不准”的对象有用。**普通文件上它不起作用**：内核认为磁盘文件永远“就绪”，页缓存没命中时 `read` 照样睡着等磁盘。想让读磁盘不卡住线程，要用 `io_uring` 或者另开线程。

`O_DIRECT` 让读写绕过页缓存，在用户 buffer 和磁盘之间直接 DMA，要求 buffer 地址、长度、文件偏移都按块大小（通常 512 B 或 4 KiB）对齐。自己管缓存的数据库会用它，免得同一份数据在自己的缓存和页缓存里各存一份。

打开以后，`O_APPEND`、`O_NONBLOCK` 还能用 `fcntl` 改；访问方式和 `O_CREAT` 这类只在打开那一刻有意义的标志改不了：

```c
int fl = fcntl(fd, F_GETFL);
fcntl(fd, F_SETFL, fl | O_NONBLOCK);   // 改的是打开的文件：dup 出来的、fork 继承的 fd 一起变
```

### 2.2 read 和 write 的返回值：少读、EINTR、0 {#read-write}

`read(fd, buf, n)` 返回实际读到的字节数，可能比 n 小。普通文件上，只有读到文件末尾附近才会少读；管道、socket、终端上，少读是常态，因为 `read` 只等到“有数据”就返回，有多少给多少：管道里此刻只有 100 字节，要 4096 也只给 100。返回 0 表示到头了，对普通文件是读到末尾，对管道是写端全都关了，对 socket 是对端关了连接。返回 -1 时看 errno：`EAGAIN` 是非阻塞 fd 上此刻没有数据，`EINTR` 是一个字节还没读到就被信号打断了。

`write` 也一样。写普通文件通常一次写完；写阻塞的 socket 或管道，内核会等到全部写进去才返回，中途被信号打断时例外，返回已经写进去的字节数；写非阻塞的，缓冲区剩多少空间就写多少，剩下的要自己再写。所以**read 和 write 都要放进循环，按返回值推进指针**：

```c
#include <errno.h>
#include <unistd.h>

/* 写满 n 个字节才返回：write 可能只写了一部分，也可能被信号打断 */
ssize_t write_all(int fd, const void* buf, size_t n) {
    const char* p = buf;
    size_t left = n;
    while (left > 0) {
        ssize_t w = write(fd, p, left);
        if (w < 0) {
            if (errno == EINTR) continue;   /* 还没写进去任何字节就被信号打断：重来 */
            return -1;                      /* 真出错了，errno 里是原因 */
        }
        p += w;
        left -= (size_t)w;
    }
    return (ssize_t)n;
}

/* 读到 EOF 为止，返回读到的总字节数 */
ssize_t read_to_end(int fd, char* buf, size_t cap) {
    size_t got = 0;
    while (got < cap) {
        ssize_t r = read(fd, buf + got, cap - got);
        if (r == 0) break;                  /* 0：文件读完了（socket 上是对方关了） */
        if (r < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        got += (size_t)r;                   /* 可能比要的少：继续读 */
    }
    return (ssize_t)got;
}
```

`EINTR` 只出现在“慢设备”上。读写管道、socket、终端时线程可能睡很久，这期间信号来了，内核把它叫醒去跑信号处理函数，系统调用就以 `EINTR` 结束。用 `sigaction` 注册处理函数时设 `SA_RESTART`，内核会自动重新发起大多数这类调用，但不是全部：设了超时的 socket 读写、`epoll_wait` 这些照样返回 `EINTR`，所以循环里那句 `continue` 仍然要留着。

### 2.3 lseek 和空洞文件（sparse file） {#lseek}

偏移记在打开的文件里，`read` 和 `write` 从偏移处开始，做完把它往后推。`lseek(fd, off, whence)` 直接改它：`SEEK_SET` 从文件头算，`SEEK_CUR` 从当前位置算，`SEEK_END` 从文件末尾算，返回新的偏移，所以 `lseek(fd, 0, SEEK_END)` 顺便拿到了文件大小（`fstat` 更直接）。返回类型是 `off_t`，64 位系统上是 64 位，存进 `int` 会在 2 GiB 以上的文件上截断。

偏移可以移到文件末尾之后。光移过去文件不会变长，接着写一个字节，文件大小才变成“偏移加 1”；中间那段从来没写过的区域就是空洞，读出来全是 0，但文件系统不给它分配磁盘块：

```c
int fd = open("sparse.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
lseek(fd, 1L << 30, SEEK_SET);   // 跳到 1 GiB 处
write(fd, "x", 1);               // 文件大小 1 GiB + 1 字节，实际只占一个块
close(fd);
```

**`ls -l` 看的是大小（`st_size`，约 1 GiB），`du` 看的是实际占用的块（`st_blocks`，几 KiB）。** 虚拟机镜像、数据库预分配的文件、core dump 常是这种稀疏文件。用 `ftruncate(fd, size)` 把文件拉长，多出来的部分同样是空洞。复制时，普通的读写循环会把空洞读成真的 0 再写出去，目标文件就不再稀疏；`cp` 默认会探测源文件里的空洞，尽量在目标里保留下来。

管道和 socket 没有“位置”可言，对它们 `lseek` 返回 `ESPIPE`。多个线程共用一个 fd 读写不同位置时，`lseek` 加 `read` 两步之间偏移可能被别的线程改掉，这时用 `pread(fd, buf, n, off)` 和 `pwrite`：位置作为参数传进去，既不读也不改共享的偏移。

## 3. dup、重定向和 fork

### 3.1 dup 和 dup2：再拿一个 fd 指向同一个打开的文件 {#dup}

`dup(old)` 在 fd 表里找最小的空位，让它指向 old 指着的那个打开的文件，返回新下标。`dup2(old, new)` 指定新下标：new 开着就先关掉，再让它指向 old 的对象，“关”和“指”在一步里完成，中间不会被别的线程的 `open` 抢走 new 这个号。新 fd 和 old 共用偏移和 `O_APPEND` 这类状态，因为它们本来就是同一个 `struct file`；只有 `FD_CLOEXEC` 不跟过来，需要的话用 `dup3(old, new, O_CLOEXEC)` 或 `fcntl(old, F_DUPFD_CLOEXEC, 0)`。

```c
int fd = open("1.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
int fd2 = dup(fd);
write(fd, "hello ", 6);
write(fd2, "world\n", 6);   // 接在 hello 后面：两个 fd 共用一个偏移
close(fd);                  // 文件还没关：fd2 还引用着它
```

打开的文件带引用计数，每个指向它的 fd 算一个。`close` 只是去掉表里那一项、计数减 1，**减到 0 内核才真正释放它**，对 socket 来说，这时才发 FIN。

### 3.2 shell 的重定向：`>` 和 `2>&1` 就是 open 加 dup2 {#redirection}

shell 执行 `cmd > out.txt 2>&1` 时，先 fork 出子进程，在子进程里、exec 之前按从左到右的顺序改 fd 表，再 exec 成 `cmd`。`cmd` 对此一无所知，照常往 1 和 2 写，只是这两个下标已经换了目标：

<svg viewBox="0 0 760 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="cmd > out.txt 2>&1 的三步：一开始 fd 0、1、2 都指向终端；open 加 dup2(3, 1) 之后 fd 1 指向 out.txt；dup2(1, 2) 之后 fd 2 也指向 out.txt。反过来写时 2 会留在终端" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .fbbg  { fill: #fbfaf7; }
    .fbpn  { fill: #f4f2ec; stroke: #ddd8cc; stroke-width: 1.2; }
    .fbfd  { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.2; }
    .fbtm  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .fbfl  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .fbink { fill: #1c1b18; font-size: 12.5px; }
    .fbmut { fill: #6b6558; font-size: 12px; }
    .fbttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .fbln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .fbhd  { fill: #6b6558; }
    .fbhi  { stroke: #c0703a; stroke-width: 2; fill: none; }
    .fbhh  { fill: #c0703a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbbg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbpn { fill: #1f1e24; stroke: #34333b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbfd { fill: #17161b; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbtm { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbfl { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbink, :root:is([data-theme="dark"], [data-theme="black"]) .fbttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbmut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbhd { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbhi { stroke: #e0955c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fbhh { fill: #e0955c; }
  </style>
  <defs><marker id="fba" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="fbhd"/></marker><marker id="fbb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="fbhh"/></marker></defs>
  <rect class="fbbg" x="0" y="0" width="760" height="290" rx="10"/>
  <rect class="fbpn" x="24" y="14" width="224" height="216" rx="8"/>
  <text class="fbttl" x="36" y="38">1. 从 shell 继承</text>
  <rect class="fbfd" x="36" y="56" width="76" height="26" rx="4"/>
  <text class="fbink" x="48" y="74">fd 0</text>
  <rect class="fbfd" x="36" y="90" width="76" height="26" rx="4"/>
  <text class="fbink" x="48" y="108">fd 1</text>
  <rect class="fbfd" x="36" y="124" width="76" height="26" rx="4"/>
  <text class="fbink" x="48" y="142">fd 2</text>
  <rect class="fbtm" x="164" y="56" width="72" height="60" rx="6"/>
  <text class="fbink" x="176" y="91">终端</text>
  <path class="fbln" d="M112,69 L162,74" marker-end="url(#fba)"/>
  <path class="fbln" d="M112,103 L162,90" marker-end="url(#fba)"/>
  <path class="fbln" d="M112,137 L162,106" marker-end="url(#fba)"/>
  <text class="fbmut" x="36" y="200">shell fork 之后，</text>
  <text class="fbmut" x="36" y="218">exec 之前</text>
  <rect class="fbpn" x="268" y="14" width="224" height="216" rx="8"/>
  <text class="fbttl" x="280" y="38">2. &gt; out.txt</text>
  <rect class="fbfd" x="280" y="56" width="76" height="26" rx="4"/>
  <text class="fbink" x="292" y="74">fd 0</text>
  <rect class="fbfd" x="280" y="90" width="76" height="26" rx="4"/>
  <text class="fbink" x="292" y="108">fd 1</text>
  <rect class="fbfd" x="280" y="124" width="76" height="26" rx="4"/>
  <text class="fbink" x="292" y="142">fd 2</text>
  <rect class="fbtm" x="408" y="56" width="72" height="60" rx="6"/>
  <text class="fbink" x="420" y="91">终端</text>
  <rect class="fbfl" x="408" y="136" width="72" height="36" rx="6"/>
  <text class="fbink" x="417" y="159">out.txt</text>
  <path class="fbln" d="M356,69 L406,76" marker-end="url(#fba)"/>
  <path class="fbhi" d="M356,103 L405,148" marker-end="url(#fbb)"/>
  <path class="fbln" d="M356,137 L406,106" marker-end="url(#fba)"/>
  <text class="fbmut" x="280" y="200">open → fd 3</text>
  <text class="fbmut" x="280" y="218">dup2(3, 1); close(3)</text>
  <rect class="fbpn" x="512" y="14" width="224" height="216" rx="8"/>
  <text class="fbttl" x="524" y="38">3. 2&gt;&amp;1</text>
  <rect class="fbfd" x="524" y="56" width="76" height="26" rx="4"/>
  <text class="fbink" x="536" y="74">fd 0</text>
  <rect class="fbfd" x="524" y="90" width="76" height="26" rx="4"/>
  <text class="fbink" x="536" y="108">fd 1</text>
  <rect class="fbfd" x="524" y="124" width="76" height="26" rx="4"/>
  <text class="fbink" x="536" y="142">fd 2</text>
  <rect class="fbtm" x="652" y="56" width="72" height="60" rx="6"/>
  <text class="fbink" x="664" y="91">终端</text>
  <rect class="fbfl" x="652" y="136" width="72" height="36" rx="6"/>
  <text class="fbink" x="661" y="159">out.txt</text>
  <path class="fbln" d="M600,69 L650,80" marker-end="url(#fba)"/>
  <path class="fbln" d="M600,103 L650,146" marker-end="url(#fba)"/>
  <path class="fbhi" d="M600,137 L649,160" marker-end="url(#fbb)"/>
  <text class="fbmut" x="524" y="200">dup2(1, 2)</text>
  <text class="fbmut" x="524" y="218">2 指向 1 此刻的目标</text>
  <text class="fbmut" x="24" y="256">反过来写 cmd 2&gt;&amp;1 &gt; out.txt：先做 dup2(1, 2)，那时 1 还指着终端，2 也就指向终端；</text>
  <text class="fbmut" x="24" y="276">之后 1 才改指 out.txt，错误输出仍然打在屏幕上。</text>
</svg>

翻成调用：

```c
// 子进程里，exec 之前
int fd = open("out.txt", O_WRONLY | O_CREAT | O_TRUNC, 0666);   // >；>> 把 O_TRUNC 换成 O_APPEND
dup2(fd, 1);     // 1 改指 out.txt
close(fd);
dup2(1, 2);      // 2>&1：让 2 指向 1 此刻指着的东西
execvp(argv[0], argv);
```

`2>&1` 是一次 `dup2(1, 2)`，意思是“让 2 指向 1 **此刻**指着的那个打开的文件”，不是“以后 2 一直跟着 1”。所以**重定向的顺序决定结果**，图下面那行就是写反时的情形。

1 和 2 最后指向同一个打开的文件，共用一个偏移，两路输出依次接在后面。写成 `cmd > out.txt 2> out.txt` 就不一样了：两次 `open` 各有一个 `struct file`、各有一个偏移，两路输出会互相覆盖。管道 `a | b` 用的是同一个办法：shell 先 `pipe(p)` 拿到读端和写端，fork 出 a 并 `dup2(p[1], 1)`，fork 出 b 并 `dup2(p[0], 0)`，各自关掉用不着的那一端。写端要是有谁忘了关，b 读完数据也等不到返回 0，因为内核看到写端还有人开着。

### 3.3 fork 和 exec 之后：fd 跟着走 {#fork-exec}

fork 复制 fd 表，子进程的 fd 和父进程的指向同一批打开的文件，**偏移也共用**：父子轮流往同一个 fd 写日志，内容依次接起来，不会互相覆盖（例子和推论在 [进程和 fork 那篇](/zh/ref/process-thread-fork/)）。反过来，父子同时从同一个 fd 读，会互相“抢”数据，一方读走的那段，另一方的偏移已经越过去了。exec 不动 fd 表，只关掉带 `FD_CLOEXEC` 的那些，重定向正是靠这一点把改好的 0、1、2 交给新程序。

## 4. stdio 缓冲：FILE* 在 fd 上面又加了一层

### 4.1 FILE*：一个 fd 加一块用户态缓冲区 {#stdio}

`fopen` 返回的 `FILE*` 是 C 库在用户态维护的结构，里面有一个 fd（`fileno(fp)` 能取出来）和一块缓冲区。`fwrite`、`fprintf`、`printf` 只是把数据拷进这块缓冲区，攒够了才调一次 `write`；`fread` 一次 `read` 读进一大块，之后的小读取直接从缓冲区拿。这样做是因为每次系统调用都有固定开销（进出内核一趟约 100 ns 到 1 µs），逐字节 `write` 一万次和攒成一次 `write`，时间能差两三个数量级。C++ 的 `std::ofstream`、`std::cout` 是同样的设计。

于是两者的语义差了一层：**`write` 返回时数据已经在内核里了，`fwrite` 返回时数据可能还在你自己进程的内存里。** 这时进程崩溃或者调了 `_exit`，缓冲区里的东西就丢了；正常 `exit`、从 `main` 返回，C 库会把所有 `FILE*` 刷出去。

### 4.2 全缓冲、行缓冲、无缓冲：什么时候真正调 write {#buffering-modes}

“攒够”的标准取决于缓冲方式：

| 方式 | 什么时候调 write | 默认用在 |
|---|---|---|
| 全缓冲 | 缓冲区满（glibc 按文件系统块大小分配，常见 4 KiB） | 普通文件、管道，以及被重定向的 stdout |
| 行缓冲 | 遇到 `\n`，或者缓冲区满 | 指向终端的 stdout |
| 无缓冲 | 每次调用都写 | stderr |

stdout 用哪种是程序启动后第一次输出时决定的：C 库检查 fd 1 是不是终端，是就行缓冲，否则全缓冲。stderr 不缓冲，是为了错误信息在程序崩溃前一定能出去。下面这个程序在终端上按 1、2、3 的顺序输出，接到管道或文件上，顺序就变了：

```cpp
#include <cstdio>

int main() {
    std::printf("1 stdout\n");
    std::fprintf(stderr, "2 stderr\n");
    std::printf("3 stdout\n");
}
```

```text
$ ./buf 2>&1 | cat
2 stderr
1 stdout
3 stdout
```

stdout 接到管道上成了全缓冲，1 和 3 一直留在缓冲区，`main` 返回时才一起写出；stderr 不缓冲，2 当场就进了管道。**两路输出谁先谁后，看的是各自什么时候真正调了 `write`，不是代码里的先后。** 要控制顺序，就在关键处 `fflush(stdout)`，或者在第一次输出之前用 `setvbuf(stdout, nullptr, _IOLBF, 0)` 把 stdout 改成行缓冲。同一个 fd 上混用 `printf` 和 `write(1, ...)` 也会乱序，道理相同：`write` 直接进了内核，`printf` 的还在缓冲区里排队。

C++ 这边，`std::endl` 是“换行再 flush”，往文件里写大量行时每行触发一次 `write`，只想换行就写 `'\n'`。`std::cout` 默认和 C 的 stdout 同步（`sync_with_stdio(true)`），混用 `printf` 和 `cout` 顺序不会乱；调了 `std::ios::sync_with_stdio(false)` 以后 `cout` 有了自己的缓冲区，就不能再混用了。

### 4.3 fork 之前没 flush：同一段输出出现两次 {#fork-twice}

fork 复制整个地址空间，`FILE*` 的缓冲区也在里面。缓冲区里还有没写出去的数据时 fork，父子各带一份，各自在退出时刷出去，同一段内容就写了两次：

```c
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    printf("before fork ");          // 没有换行：留在 stdout 的缓冲区里
    if (fork() == 0) {
        printf("child\n");
        return 0;                    // 子进程退出时刷缓冲区：before fork child
    }
    wait(NULL);
    printf("parent\n");              // before fork parent
    return 0;
}
```

输出是 `before fork child` 和 `before fork parent` 两行。即使第一句带了 `\n`，只要把输出重定向到文件，照样出现两次，因为那时 stdout 是全缓冲，`\n` 不触发写出。所以**fork 之前先 `fflush(stdout)`**（`fflush(NULL)` 刷所有输出流）；fork 出来只为了 exec、或者 exec 失败要退出的子进程，用 `_exit` 而不是 `exit`，免得把从父进程继承来的缓冲区再刷一遍。

## 5. inode 里记着什么

### 5.1 stat：类型、权限、大小、时间 {#stat}

`stat(path, &st)` 按路径查 inode，`fstat(fd, &st)` 查一个已打开的 fd 背后的 inode，`lstat` 遇到软链接时查链接本身、不跟过去。`struct stat` 的字段几乎就是 inode 的内容：

```c
struct stat {
    dev_t     st_dev;      // 在哪个设备（文件系统）上
    ino_t     st_ino;      // inode 号：和 st_dev 一起唯一确定一个文件
    mode_t    st_mode;     // 文件类型 + 权限位
    nlink_t   st_nlink;    // 硬链接数
    uid_t     st_uid;      // 属主
    gid_t     st_gid;      // 属组
    off_t     st_size;     // 大小（字节）
    blkcnt_t  st_blocks;   // 实际占用的块数，以 512 B 为单位
    struct timespec st_atim, st_mtim, st_ctim;   // 访问、内容修改、inode 修改
    /* ... */
};
```

`st_mode` 的高位是文件类型，用 `S_ISREG(st.st_mode)`、`S_ISDIR`、`S_ISLNK` 这些宏判断，或者拿 `st.st_mode & S_IFMT` 和 `S_IFREG` 等比较。七种类型就是 `ls -l` 第一列那个字符：`-` 普通文件、`d` 目录、`l` 软链接、`c` 字符设备（终端、`/dev/null`）、`b` 块设备（磁盘）、`p` 命名管道、`s` Unix 域 socket。

三个时间里，`ctime` 常被当成创建时间，其实是 **inode 最后一次被改的时间**：改权限、改属主、增删硬链接、改内容都会更新它，`mtime` 只在内容变化时更新。传统的 `stat` 里没有创建时间，Linux 上要用 `statx` 的 `stx_btime` 才拿得到（还要文件系统支持）。

还有一样 inode 里没有：**文件名**。名字记在目录里，硬链接就建立在这一点上。

### 5.2 权限位和 umask {#permissions}

权限是 9 位，分属主、属组、其他人三组，每组 `r`、`w`、`x`，写成八进制就是 `0644`（属主读写，其他人只读）、`0755`（再加上执行）。进程访问文件时，内核按“属主 → 属组 → 其他人”找第一组和自己身份匹配的，只用那一组判断，root 绕过大部分检查。

对目录，这三位的意思换了：`r` 是能列出里面的名字，`w` 是能在里面创建、删除、改名，`x` 是能进入它、按名字查到里面的东西。所以**删除一个文件要的是它所在目录的写权限**，和文件本身的权限无关，一个只读文件，只要目录可写照样能删。`/tmp` 是 `1777`，多出来的那一位叫粘滞位（`t`）：谁都能在里面建文件，但只能删自己的。

新建文件时，`open` 的 `mode` 还要去掉 umask 里置 1 的位，最终权限是 `mode & ~umask`。umask 通常是 `022`，于是 `open(..., 0666)` 建出来是 `0644`，`mkdir(..., 0777)` 建出来是 `0755`。umask 是进程属性，fork 时继承，`umask(m)` 设新值并返回旧值。正因为有它，程序一般把 mode 写成 `0666` 或 `0777`，收紧多少交给用户的 umask，而不是自己写死 `0644`。

### 5.3 硬链接和软链接：同一个 inode 的两个名字，和一个存着路径的文件 {#links}

目录本身也是文件，内容是一张“名字 → inode 号”的表，每一项叫一个目录项。打开 `/home/a/x.txt`，内核就是逐级查目录项，最后拿到 x.txt 的 inode 号。

硬链接（`ln x.txt y.txt`，即 `link()`）是在某个目录里再加一个目录项，指向**同一个 inode**。两个名字地位完全相同，没有“原件”和“链接”之分，`ls -i` 看到的 inode 号一样，`st_nlink` 变成 2。`rm` 调的是 `unlink`，只删目录项、把 `st_nlink` 减 1；**数据要等链接数归 0、并且没有进程还开着它，才真正释放**。

后半句对应一个常见的现场问题：日志写满了磁盘，`rm` 掉以后 `df` 显示空间没回来，因为写日志的进程还开着它，`struct file` 还引用着那个 inode。`ls -l /proc/<pid>/fd` 能看到一个标着 `(deleted)` 的 fd，让那个进程重新打开日志或者重启它，空间才释放。反过来，这个规则也能拿来做“用完自动消失”的临时文件：`open` 以后立刻 `unlink`，进程一退出文件就没了。

硬链接只能建在同一个文件系统里，因为 inode 号只在一个文件系统内有意义；也不能给目录建，否则目录树里会出现环，遍历就停不下来。软链接（`ln -s`，即 `symlink()`）没有这些限制：它是一个**单独的 inode**，类型是 `l`，内容就是一个路径字符串，内核解析路径时遇到它，就把里面的路径接上继续查。它能跨文件系统、能指向目录，也能指向不存在的东西：目标被删或被改名，链接就悬空了，访问时报 `ENOENT`。

| | 硬链接 | 软链接 |
|---|---|---|
| 本质 | 又一个目录项，指向同一个 inode | 一个新 inode，内容是路径 |
| inode 号 | 和原文件相同 | 自己的 |
| 跨文件系统、指向目录 | 不能 | 能 |
| 原来的名字被删 | 数据还在（链接数没归 0） | 悬空 |

## 6. 页缓存和 fsync：write 返回不等于落盘

### 6.1 两层缓冲，各有各的推法 {#page-cache}

`write` 把数据拷进内核的页缓存，标成脏页就返回，回写线程过一阵（脏了约 30 s，或者脏页太多时）才写回磁盘；`read` 先查页缓存，命中就不碰磁盘（过程和数字见 [IO 地图的读写文件一节](/zh/ref/cpp-linux/#file)，全景在 [IO 地图](/maps/io-map.zh.html)）。再加上 stdio 的缓冲，数据从你的变量到磁盘要过两层：

<svg viewBox="0 0 760 230" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="数据从用户变量经 fwrite 拷进 FILE* 缓冲区，缓冲区满、遇到换行或 fflush 时调 write 进入页缓存，回写线程或 fsync 再把脏页写到磁盘；进程崩溃丢 FILE* 缓冲区里的数据，断电丢页缓存里的脏页" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .fcbg  { fill: #fbfaf7; }
    .fcu   { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.3; }
    .fcs   { fill: #e3eaf6; stroke: #6f86b3; stroke-width: 1.3; }
    .fck   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .fcd   { fill: #f6e7c8; stroke: #b8954a; stroke-width: 1.3; }
    .fcbd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .fcmut { fill: #6b6558; font-size: 12px; }
    .fcttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .fcw   { fill: #b0503a; font-size: 12px; }
    .fcln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .fchd  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcbg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcu { fill: #1d1c22; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcs { fill: #26304a; stroke: #7f97c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fck { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcd { fill: #45381f; stroke: #c9a55a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcbd, :root:is([data-theme="dark"], [data-theme="black"]) .fcttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcmut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcw { fill: #e38a72; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fcln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fchd { fill: #a19caf; }
  </style>
  <defs><marker id="fca" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="fchd"/></marker></defs>
  <rect class="fcbg" x="0" y="0" width="760" height="230" rx="10"/>
  <text class="fcttl" x="24" y="28">从你的变量到磁盘：两层缓冲</text>
  <rect class="fcu" x="24" y="48" width="130" height="60" rx="6"/>
  <text class="fcbd" x="38" y="72">你的变量</text>
  <text class="fcmut" x="38" y="94">buf、字符串</text>
  <rect class="fcs" x="218" y="48" width="130" height="60" rx="6"/>
  <text class="fcbd" x="232" y="72">FILE* 缓冲区</text>
  <text class="fcmut" x="232" y="94">用户态，每个进程</text>
  <rect class="fck" x="412" y="48" width="130" height="60" rx="6"/>
  <text class="fcbd" x="426" y="72">页缓存</text>
  <text class="fcmut" x="426" y="94">内核，整机共享</text>
  <rect class="fcd" x="606" y="48" width="130" height="60" rx="6"/>
  <text class="fcbd" x="620" y="72">磁盘</text>
  <text class="fcmut" x="620" y="94">断电也还在</text>
  <path class="fcln" d="M154,78 L215,78" marker-end="url(#fca)"/>
  <path class="fcln" d="M348,78 L409,78" marker-end="url(#fca)"/>
  <path class="fcln" d="M542,78 L603,78" marker-end="url(#fca)"/>
  <text class="fcmut" x="186" y="134" text-anchor="middle">fwrite、printf</text>
  <text class="fcmut" x="186" y="152" text-anchor="middle">拷进缓冲区</text>
  <text class="fcmut" x="380" y="134" text-anchor="middle">满了、换行、fflush</text>
  <text class="fcmut" x="380" y="152" text-anchor="middle">才调 write()</text>
  <text class="fcmut" x="574" y="134" text-anchor="middle">回写线程（约 30 s）</text>
  <text class="fcmut" x="574" y="152" text-anchor="middle">或者 fsync()</text>
  <text class="fcw" x="283" y="192" text-anchor="middle">进程崩溃、_exit：</text>
  <text class="fcw" x="283" y="210" text-anchor="middle">这里的丢了</text>
  <text class="fcw" x="477" y="192" text-anchor="middle">断电：</text>
  <text class="fcw" x="477" y="210" text-anchor="middle">没写回的脏页丢了</text>
</svg>

`fflush` 只把用户态缓冲推进内核，之后进程崩溃不会丢，机器断电仍然会丢。`fsync(fd)` 把这个文件的脏页和 inode 一起写到磁盘，还让磁盘把它自己的写缓存也刷掉，返回时才算落盘；`fdatasync` 省掉和读回数据无关的元数据（比如 mtime），文件长度没变时少写一次 inode。`close` 两件事都不管：`fclose` 会刷用户态缓冲，但也只刷到内核，**关闭文件不等于落盘**。

三步的成本差得很远：`fwrite` 是一次内存拷贝，`write` 多一趟进出内核，`fsync` 要等磁盘确认，几百 µs 到几十 ms。所以数据库只在提交事务时 fsync 日志，还常把多个事务攒到一次 fsync 里（group commit）。`O_DIRECT`（2.1）跳过的是中间那层页缓存，跳过以后写仍然可能停在磁盘的写缓存里，要落盘照样得 fsync。

### 6.2 安全地替换一个文件：写临时文件、fsync、rename {#atomic-replace}

直接 `open(path, O_TRUNC)` 再写新内容，中途崩溃或断电，留下的是一个被截短、只写了一半的文件。标准做法借助 `rename` 的原子性：同一文件系统内，`rename(tmp, path)` 让 path 这个目录项一步从旧 inode 换到新 inode，别人打开 path 看到的要么全是旧的，要么全是新的。

```c
int fd = open("config.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0644);
write_all(fd, data, len);
fsync(fd);                          // 1. 新内容先落盘
close(fd);
rename("config.tmp", "config");     // 2. 原子地换名字
int dir = open(".", O_RDONLY | O_DIRECTORY);
fsync(dir);                         // 3. 目录项的修改也要落盘
close(dir);
```

少了第 1 步，改名可能先于数据落盘，断电后得到一个名字对了、内容是空的文件；少了第 3 步，改名本身可能还没落盘，断电后回到旧文件。**rename 保证的是“要么旧要么新”，fsync 保证的是“断电后还在”**，两样都要才算安全。

## 7. 守护进程：0、1、2 该指向哪里

### 7.1 守护进程（daemon）：脱离终端，把 0、1、2 指向 /dev/null {#daemon}

守护进程是在后台长期运行、不属于任何终端的进程。从终端启动的程序，0、1、2 指向那个终端，进程也属于终端的会话：终端关掉时会话里的进程收到 `SIGHUP`，Ctrl+C 给前台进程组发 `SIGINT`。传统的“变成守护进程”就是一步步切断这些联系，每一步都有具体原因：

```c
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

void daemonize(void) {
    if (fork() > 0) exit(0);     // 1. 父进程退出，shell 认为命令结束；子进程一定不是进程组组长
    setsid();                    // 2. 新建会话，脱离控制终端（组长调 setsid 会失败，所以要先 fork）
    if (fork() > 0) exit(0);     // 3. 再 fork：不是会话首进程，以后打开终端也不会成为控制终端
    umask(0);                    // 4. 不受启动者 umask 影响，权限由程序自己给的 mode 决定
    chdir("/");                  // 5. 不占着启动时的目录，否则那个文件系统卸载不了
    for (long fd = sysconf(_SC_OPEN_MAX) - 1; fd >= 0; --fd)
        close((int)fd);          // 6. 关掉继承来的所有 fd
    int fd = open("/dev/null", O_RDWR);   // 0 是最小的空号，所以拿到 0
    dup2(fd, 1);                 // 7. 1、2 也指向 /dev/null
    dup2(fd, 2);
}
```

最后一步最容易省掉，防的却是最隐蔽的事：**0、1、2 只关不补，下一次 `open` 就会拿到 1**（最小空号规则），之后库里某处的 `printf` 或 `perror` 就直接写进了这个数据文件。三个号都指向 `/dev/null` 以后，它们被占住，误写的输出被丢掉，读 stdin 立刻得到 EOF。

现在 Linux 上的服务大多交给 systemd 管理，这些它都替进程做好了：服务直接在前台运行，日志写到 stdout 和 stderr，systemd 把这两个 fd 接到 journal 上。上面这几步仍然值得懂，因为它们刚好把 fd 的分配规则、会话和终端、umask 串在了一起。

## 8. C++17 std::filesystem：跨平台的路径和目录操作

### 8.1 path、遍历和 error_code {#std-filesystem}

前面的调用都是 POSIX 的，Windows 上是另一套 API。C++17 的 `<filesystem>` 把路径拼接、查类型和大小、建目录、遍历、复制、改名、删除统一成一套接口，在 Linux 上底下调的就是 `stat`、`mkdir`、`opendir`/`readdir`、`rename`、`unlink`。读写文件内容不归它管，那仍然是 `fstream` 或 fd 的事。

```cpp
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <system_error>

namespace fs = std::filesystem;

int main() {
    fs::path dir = fs::temp_directory_path() / "fio-demo";
    fs::create_directories(dir / "logs");                 // 中间缺的目录一起建
    std::ofstream(dir / "logs" / "a.txt", std::ios::binary) << "hello\n";

    for (const auto& e : fs::recursive_directory_iterator(dir))
        std::cout << fs::relative(e.path(), dir).generic_string()
                  << (e.is_directory() ? "/" : "  " + std::to_string(e.file_size()) + " B") << '\n';

    std::error_code ec;                                   // 不想要异常：传一个 error_code
    auto n = fs::file_size(dir / "nope.txt", ec);
    std::cout << "nope.txt: " << (ec ? ec.message() : std::to_string(n)) << '\n';

    std::cout << "removed " << fs::remove_all(dir) << " entries\n";
}
```

```text
logs/
logs/a.txt  6 B
nope.txt: No such file or directory
removed 3 entries
```

`path` 的 `/` 运算符负责拼接，分隔符按平台处理，`generic_string()` 统一输出成 `/`。几乎每个函数都有两个版本：默认出错时抛 `fs::filesystem_error`，多传一个 `std::error_code&` 就改成把错误写进它、不抛异常，适合“文件不存在很正常”的场合。`remove_all` 返回删掉的条目数，这里是目录本身、`logs` 和 `a.txt` 三个。

遍历时 `directory_entry` 顺手缓存了 `readdir` 返回的类型，`e.is_directory()` 通常不用再调一次 `stat`；`e.file_size()` 则仍然要查 inode。**先 `exists` 再操作，和先 `access` 再 `open` 是同一个问题**：两步之间文件可能已经变了，直接做、处理 `error_code` 更可靠。
