---
title: "C++ 与 Linux：总图"
description: "C++ 程序在 Linux 上最常翻的两张总图。进程地图：一个进程的虚拟地址空间有哪几段，C++ 里的变量、new 出来的内存、线程栈各落在哪，虚拟地址怎么经页表落到物理内存。IO 地图：读写文件、mmap、收发网络包时，数据在设备、内核和你的缓冲区之间怎么走，哪一步是 CPU 拷贝、哪一步是 DMA，IO 模型和零拷贝各省在哪。"
date: 2026-11-02
slug: "cpp-linux"
aliases: ["/ref/process-memory/"]
weight: 12
toc: true
---

这页放 C++ 程序在 Linux 上最常翻的总图，和[硬件地图](/zh/ref/cpu-memory/)是一对：硬件地图讲一次访存经过哪些硬件，这页讲在那之前，操作系统替程序做了什么。两张图：[进程地图](#map)讲一个进程的内存长什么样，[IO 地图](#io)讲数据怎么进出这个进程。细分的知识点（epoll、fork、动态链接……）写成 [C++ 与 Linux](/zh/categories/linux/) 分类下的单篇文章，这页只放总图和最常翻的表。

## 1. 进程地图：一个进程的虚拟地址空间 {#map}

<a href="/maps/process-map.zh.html" target="_blank" rel="noopener"><img src="/images/ref/process-map.zh.svg" alt="进程地图：左边是 x86-64 上一个进程的虚拟地址空间，从高到低依次是内核空间、非规范地址空洞、主线程的栈、vDSO、mmap 区（共享库、大块 malloc、其他线程的栈和 TLS、文件映射和共享内存）、没映射的空地、堆、.bss、.data、.rodata、.text 和最低 64 KiB 的不映射区；右边是 C++ 变量各放在哪、线程共享什么、页表和缺页怎么把虚拟地址落到物理内存、在自己机器上怎么看、出了错落在哪一段。" loading="lazy" decoding="async"></a>

左边一列是一个进程看到的全部地址，高地址在上，不按比例。右边是这些地址怎么经页表落到物理内存上。点图打开可交互的版本：点一个框看它放什么、在哪篇讲过；选“变量放在哪”“new 一块内存”这些路径，一步一步看。页表和物理内存两个框的蓝字会打开硬件地图，接着走一次 load 的路。

### 1.1 从高到低每一段 {#segments}

| 段 | 放什么 | 权限 | 大小怎么定 | `/proc/<pid>/maps` 里 |
|---|---|---|---|---|
| 内核空间 | 内核代码和数据、各进程的页表、各线程的内核栈 | 用户态不能访问 | 高 128 TiB | 不显示 |
| 主线程的栈 | 局部变量、参数、返回地址 | `rw-` | 上限 `ulimit -s`，默认 8 MiB | `[stack]` |
| vDSO | `clock_gettime` 这类不进内核的系统调用 | `r-x` | 一两页 | `[vvar]` `[vdso]` |
| mmap 区 | `.so`、大块 malloc、其他线程的栈、文件映射、共享内存 | 看映射 | 用多少映射多少 | 文件名，或者没有名字 |
| 堆 | `new`、`malloc` 的小块 | `rw-` | `brk` 往上推 | `[heap]` |
| `.bss` | 没有初值的全局变量和 `static` 变量 | `rw-` | 链接时定 | 紧跟 `.data` 的一行 |
| `.data` | 有初值的全局变量和 `static` 变量 | `rw-` | 链接时定 | 程序文件的 `rw-p` |
| `.rodata` | 字符串字面量、常量、查找表；重定位后的 vtable | `r--` | 链接时定 | 程序文件的 `r--p` |
| `.text` | 机器码 | `r-x` | 链接时定 | 程序文件的 `r-xp` |
| 最低 64 KiB | 不映射 | 无 | `vm.mmap_min_addr` | 不显示 |

用户空间只有低 128 TiB，是因为 x86-64 的 4 级页表只翻译 48 位地址：64 位指针的高 16 位必须和第 47 位相同，能用的只有最低和最高两段，最高那段留给内核。网上常见的“用户空间 3 GB、内核 1 GB”那张图是 32 位系统的。

栈和 mmap 区从高往低长，堆从低往高长，中间留着整个地址空间里最大的一块空地，谁先长都不容易撞上谁。程序本身的几段（`.text` 到 `.bss`）大小在链接时就定了，**运行时能变大的只有栈、堆和 mmap 区**。

### 1.2 C++ 里写的东西放在哪 {#cpp}

```cpp
int g = 1;                    // .data
int z;                        // .bss
const char* s = "hi";         // s 在 .data，"hi" 在 .rodata
thread_local int t;           // 每个线程一份（TLS）

void f() {                    // f 的指令在 .text
    int x = 0;                // 栈
    int* p = new int(2);      // p 在栈，*p 在堆
    char* b = new char[1 << 20];  // 1 MiB，超过 128 KiB：glibc 直接 mmap
    delete[] b;
    delete p;
}
```

判断一个东西放在哪，看它的生命周期：跟着整个程序的（全局、`static`）在 `.data` 和 `.bss`，编译期就定了的只读数据在 `.rodata`，跟着函数调用的在栈上，跟着 `new`、`delete` 的在堆或 mmap 区，跟着线程的在 TLS。

堆和栈是同一种内存，访问一样快。栈快在分配：挪一下栈指针就行，而且总在最近用过的那几条缓存行附近。堆慢在 `malloc` 的耗时不固定，以及对象一个个 `new` 出来散在各处、局部性差。

### 1.3 和硬件地图怎么接：虚拟地址 → 页表 → 物理页 {#to-hardware}

程序里的指针存的都是虚拟地址。CPU 每次访存，先在 dTLB 里查这个地址对应哪一页物理内存：命中不额外花时间；没命中，硬件按 4 级页表一级一级查，约 15–30 ns（[速查 2.1](/zh/ref/cpu-memory/#latency)）。页表每个进程一份，所以两个进程里同一个虚拟地址可以对应完全不同的物理页；反过来，同一个 `.so` 的代码页、`/dev/shm` 里的共享内存，是几个进程的页表指向同一批物理页。拿到物理地址以后，就是[硬件地图](/maps/hardware-map.zh.html#load)上那条路：L1 → L2 → L3 → 内存控制器 → 通道。

`new`、`mmap`、`brk` 只在进程的映射表里登记一段虚拟地址，页表里还没有这一项。第一次写这一页时 CPU 查不到，触发缺页，陷入内核；内核分一页物理内存、清零、填进页表，再回到原来那条指令，约 0.5–2 µs。**`new` 只拿到虚拟地址，第一次写才有物理页**，所以 `new` 了一大块还没写，进程的 RSS 不涨。地址不在任何映射里（空指针、越过栈的保护页），或者权限不对（写 `.rodata`），内核就发 SIGSEGV，这就是段错误。

### 1.4 在自己机器上看 {#see}

下面这段打印各段里一个变量的地址，再把自己的 `/proc/self/maps` 打出来，对着看每个地址落在哪一行：

```cpp
#include <cstdio>
#include <cstdlib>

int g = 1;
int z;
const char* s = "hi";
thread_local int t;
void f() {}

int main() {
    int x = 0;
    int* p = new int(2);
    char* b = new char[1 << 20];
    std::printf(".text %p\n.rodata %p\n.data %p\n.bss %p\nTLS %p\nheap %p\nmmap %p\nstack %p\n",
                reinterpret_cast<void*>(&f), static_cast<const void*>(s), static_cast<void*>(&g),
                static_cast<void*>(&z), static_cast<void*>(&t), static_cast<void*>(p),
                static_cast<void*>(b), static_cast<void*>(&x));
    std::system("cat /proc/$PPID/maps");   // system 起的 sh，父进程就是这个程序
    delete[] b;
    delete p;
}
```

```bash
cat /proc/<pid>/maps     # 每一段的地址范围、权限、来源文件
pmap -x <pid>            # 每一段实际占了多少物理内存（RSS）
size a.out               # .text、.data、.bss 各多大
perf stat -e page-faults,dTLB-load-misses ./a.out
```

`maps` 里程序文件自己的几行，权限依次是 `r--p`、`r-xp`、`r--p`、`rw-p`，就是 ELF 头、`.text`、`.rodata`、`.data` 加 `.bss`；`[heap]`、`[stack]`、`[vdso]` 有名字，`mmap` 来的匿名内存（那 1 MiB、线程栈）没有名字。开了 ASLR，每次运行地址都不一样，但顺序不变。

## 2. IO 地图：数据怎么进出一个进程 {#io}

<a href="/maps/io-map.zh.html" target="_blank" rel="noopener"><img src="/images/ref/io-map.zh.svg" alt="IO 地图：上面是用户态的进程、用户缓冲区和 mmap 映射区，中间是内核里的 VFS、页缓存、回写线程、块设备层，以及 socket 缓冲区、epoll、TCP/IP 协议栈、网卡驱动，下面是磁盘、内存和网卡；橙线是 CPU 拷贝，蓝色虚线是 DMA，绿色虚线是映射；右边是 IO 模型和零拷贝两个说明框。" loading="lazy" decoding="async"></a>

上面是用户态，中间是内核，下面是设备和内存；左边一列是文件，中间一列是网络。橙线是 CPU 在拷贝，蓝色虚线是设备用 DMA 直接读写内存，绿色虚线是映射、不拷贝。点图打开可交互的版本，选“读一个文件”“收一个包”“把文件发到网络”这些路径一步一步看。

### 2.1 读写文件：中间隔着页缓存 {#file}

`read` 不直接读磁盘，先查页缓存：内核把读过、写过的文件内容按页留在内存里。命中就把数据从页缓存拷进你的 `buf`，几百 ns 到几 µs；没命中才发请求给磁盘，NVMe 读一次约 10–100 µs，线程在这期间睡着，磁盘用 DMA 把数据写进页缓存后再叫醒它。

`write` 也只写到页缓存，标成脏页就返回，回写线程过一会（默认脏了约 30 s）再写回磁盘。**`write` 返回不代表落盘**，要确定落盘得调 `fsync`，它等磁盘确认才返回，几百 µs 到几十 ms。`mmap` 则是把页缓存的页直接映射进进程的 mmap 区，读写不经过 `read`、`write`，也就没有那次拷贝（[进程地图](#segments)）。

### 2.2 收发网络：socket 缓冲区和协议栈 {#net}

收包时，网卡用 DMA 把包写进内存里的收包环，发中断；软中断里协议栈校验、去包头，按 IP 和端口找到 socket，把数据放进它的接收缓冲，唤醒等它的线程（被 epoll 关注的，回调把它挂上就绪链表，见 [epoll](/zh/posts/epoll-internals/)）。你调 `recv`，内核再把数据拷进 `buf`。

发包反过来：`send` 把数据拷进 socket 的发送缓冲就返回，**返回只代表拷进去了，不代表对方收到**；TCP 分段发出去，数据留在发送缓冲里，直到对方确认，丢了重传。发送缓冲满了，`send` 阻塞，或者在非阻塞 socket 上返回 `EAGAIN`。

### 2.3 零拷贝：sendfile 省的是哪几次 {#zero-copy}

把一个文件原样发给客户端，用 `read` 加 `write` 要拷 4 次：磁盘到页缓存（DMA）、页缓存到 `buf`（CPU）、`buf` 到 socket 缓冲（CPU）、socket 缓冲到网卡（DMA），还有 4 次用户态、内核态切换。中间两次 CPU 拷贝，程序根本没看过这些数据。

| 写法 | CPU 拷贝 | DMA 拷贝 | 态切换 |
|---|---|---|---|
| `read` + `write` | 2 | 2 | 4 |
| `mmap` + `write` | 1 | 2 | 4 |
| `sendfile` | 1 | 2 | 2 |
| `sendfile`，网卡支持分散收集 DMA | 0 | 2 | 2 |

`sendfile` 让数据不出内核；网卡支持分散收集（scatter-gather）DMA 时，socket 里只记页缓存里那些页的位置，网卡直接从页缓存读，CPU 一个字节都不拷。零拷贝省的是 CPU 拷贝和切换，DMA 那两次省不掉。

### 2.4 IO 模型：阻塞、非阻塞、多路复用、异步 {#io-models}

| 模型 | 数据没好时 | 谁把数据拷进 `buf` |
|---|---|---|
| 阻塞 | 线程睡在 `read` / `recv` 里 | 你的线程，在 `read` 里等着拷完 |
| 非阻塞 | 立刻返回 `EAGAIN`，过会儿再试 | 你的线程 |
| IO 多路复用（`select` / `poll` / `epoll`） | 线程睡在 `epoll_wait` 里，一次等很多 fd | 你的线程，醒来以后自己 `recv` |
| 异步（io_uring） | 线程不用等，先去干别的 | 内核拷完再通知你 |

阻塞和非阻塞问的是数据没好时等不等；同步和异步问的是拷贝这一步是不是你的线程在等。**前三种都是同步 IO**，只有最后一种是异步。
