---
title: "C++ 与 Linux：总图"
description: "C++ 程序在 Linux 上最常翻的三张总图。进程地图：一个进程的虚拟地址空间有哪几段，C++ 里的变量、new 出来的内存、线程栈各落在哪，虚拟地址怎么经页表落到物理内存。IO 地图：读写文件、mmap、收发网络包时，数据在设备、内核和你的缓冲区之间怎么走，哪一步是 CPU 拷贝、哪一步是 DMA，IO 模型和零拷贝各省在哪。从源码到进程：编译、链接、加载各做什么，静态库和动态库差在哪，链接报错从哪来。"
date: 2026-11-02
slug: "cpp-linux"
aliases: ["/ref/process-memory/"]
weight: 12
group: cpplinux
hub: true
toc: true
---

这页放 C++ 程序在 Linux 上最常翻的总图，和[硬件地图](/zh/ref/cpu-memory/)是一对：硬件地图讲一次访存经过哪些硬件，这页讲在那之前，操作系统替程序做了什么。三张图：[进程地图](#map)讲一个进程的内存长什么样，[IO 地图](#io)讲数据怎么进出这个进程，[从源码到进程](#build)讲一个可执行文件是怎么编出来、又怎么变成进程的。细分的知识点（epoll、fork、动态链接……）写成单页，和这页一起放在[速查的 C++ 与 Linux 这一组](/zh/ref/#cpplinux)，这页只放总图和最常翻的表。

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

收包时，网卡用 DMA 把包写进内存里的收包环，发中断；软中断里协议栈校验、去包头，按 IP 和端口找到 socket，把数据放进它的接收缓冲，唤醒等它的线程（被 epoll 关注的，回调把它挂上就绪链表，见 [epoll](/zh/ref/epoll-internals/)）。你调 `recv`，内核再把数据拷进 `buf`。

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

## 3. 从源码到进程：编译、链接、加载 {#build}

<a href="/maps/build-map.zh.html" target="_blank" rel="noopener"><img src="/images/ref/build-map.zh.svg" alt="从源码到进程：上面一行是编译，源文件经过预处理、编译、汇编变成目标文件 a.o，a.o 里有段、符号表和重定位表；中间一行是链接，静态库的代码拷进来，动态库只记名字，链接器做符号解析、合并、重定位，输出可执行文件，右边列出常见的链接报错；下面一行是运行，execve 按程序头映射各段，动态链接器把 .so 映射进来、跑全局构造、跳到 main，PLT 和 GOT 负责调用 .so 里的函数，最后落到进程地图上的位置。" loading="lazy" decoding="async"></a>

上面一行是编译，每个 `.cpp` 各自变成一个 `.o`；中间一行是链接，所有 `.o` 和库拼成一个可执行文件；下面一行是运行，内核和动态链接器把它变成进程地图上的那几段。橙线是代码被拷进输出文件，蓝色虚线是只记一个名字、运行时再找，绿色虚线是加载时映射进地址空间。点图打开可交互的版本，选“一个 .cpp 变成 .o”“undefined reference 从哪来”“./a.out 之后”这些路径一步一步看。

### 3.1 四步各产出什么：错误报在哪一步 {#compile-steps}

| 步骤 | 只做到这一步 | 产物 | 这一步报的错 |
|---|---|---|---|
| 预处理 | `g++ -E a.cpp` | `a.ii`，纯 C++ 文本 | 头文件找不到 |
| 编译 | `g++ -S a.cpp` | `a.s`，汇编 | 语法、类型错误，模板实例化失败 |
| 汇编 | `g++ -c a.cpp` | `a.o`，可重定位目标文件 | 几乎不出错 |
| 链接 | `g++ a.o b.o -o a.out` | 可执行文件或 `.so` | `undefined reference`、`multiple definition` |

前三步每次只看一个翻译单元，也就是一个 `.cpp` 加上它 include 的全部内容，所以编译 `a.cpp` 时只要看到 `g` 的声明就能过：它在 `a.o` 里给 `g` 留一个空位和一条重定位项。**能不能找到 `g` 的定义，要到链接才知道**，所以“编译过了、链接报错”是很常见的组合，报错信息里带的是符号名，不是行号。

### 3.2 静态库和动态库：拷进来，还是只记名字 {#static-dynamic}

| | 静态库 `libx.a` | 动态库 `libx.so` |
|---|---|---|
| 链接时 | 挑出用到的 `.o`，代码拷进可执行文件 | 只检查符号在不在，记下运行时要哪个库 |
| 运行时 | 不再需要这个库 | 动态链接器找到它、映射进来、做重定位 |
| 多个进程同时用 | 每个程序里各一份代码 | 代码页只读，所有进程共享同一份物理页 |
| 库更新了 | 程序要重新链接 | 换掉 `.so`、重启程序就生效 |
| 调用一个库函数 | 直接 `call` | 经过一次 PLT 跳板，去 GOT 里取地址 |

动态库省内存、好升级，代价在启动和调用上：启动时要找库、映射、重定位，库找不到程序根本起不来（`error while loading shared libraries`）；调库函数多一次经 GOT 的间接跳转。静态链接的程序拷到别的机器上直接能跑，所以发布单个工具时常用静态链接。

### 3.3 链接报错：从报错找原因 {#link-errors}

| 报错 | 常见原因 | 怎么改 |
|---|---|---|
| `undefined reference to f` | 只有声明没有定义，或者写定义的 `.cpp` 没加进编译命令 | 补上定义，把那个文件加进来 |
| 同上 | 库没加 `-l`，或者 `-l` 写在了用它的文件前面 | `g++ main.o -lx`，库放后面 |
| 同上 | 模板的定义写在 `.cpp` 里，别的翻译单元没法实例化 | 模板定义放进头文件 |
| 同上 | C 写的函数，C++ 里没用 `extern "C"` 声明 | 头文件里包一层 `extern "C" { … }` |
| `multiple definition of x` | 头文件里定义了普通函数或全局变量，被两个 `.cpp` include | 改成 `inline`，或者头文件只放声明、定义放进一个 `.cpp` |

这些都是同一条规则的两面：**普通函数和变量在整个程序里只能有一个定义（ODR）**，一个都没有是 `undefined reference`，多了是 `multiple definition`。`inline` 函数、`inline` 变量和模板允许每个翻译单元各定义一次，前提是每份一模一样，链接器只留一份；`static` 和匿名命名空间里的名字只在本翻译单元可见，各有一份，互不冲突。

### 3.4 自己看：每一步的产物 {#see-build}

```bash
g++ -E a.cpp | wc -l          # 预处理后有多少行
g++ -c a.cpp && nm -C a.o     # 符号表：T 是定义，U 是只用了
readelf -r a.o                # 重定位项：哪些位置等着填地址
g++ a.o b.o -o a.out
readelf -l a.out              # 程序头：每个 LOAD 段的权限和地址，还有 INTERP
readelf -d a.out | grep NEEDED  # 运行时要哪些 .so
ldd a.out                     # 这些 .so 实际会从哪个路径加载
objdump -d a.out | grep -A3 '<puts@plt>'  # PLT 跳板
```

`nm -C` 的 `-C` 把修饰过的名字还原成 C++ 的写法，`_Z1gi` 显示成 `g(int)`；`undefined reference` 报错里的名字也是这样还原过的。

## 4. 细分的单页 {#posts}

总图上每个框背后的细节，写成单页，都在[速查的 C++ 与 Linux 这一组](/zh/ref/#cpplinux)：

| 单页 | 讲什么 | 在哪张图上 |
|---|---|---|
| **C++ 语言** | | |
| [移动语义](/zh/ref/move-semantics/) | 值类别、`std::move`、`noexcept` 移动、完美转发 | 进程地图：堆（谁拿走缓冲区） |
| [构造、拷贝、析构和 RAII](/zh/ref/special-members-raii/) | 六个特殊成员、三/五/零法则、栈展开、异常安全 | 进程地图：栈 |
| [虚函数](/zh/ref/virtual-functions/) | vptr、vtable、一次虚调用的代价、组合与继承 | 进程地图：`.rodata` 里的 vtable |
| [对象布局](/zh/ref/object-layout/) | 对齐、填充、vptr 和 vtable、多重继承 | 进程地图：`.rodata` 里的 vtable |
| [const 和 constexpr](/zh/ref/const-constexpr/) | `const` / `constexpr` / `consteval` / `constinit`，编译期查找表 | 进程地图：`.rodata`、`.data` |
| [lambda 和 std::function](/zh/ref/lambda-function/) | 闭包对象、捕获、类型擦除和它的分配 | 进程地图：栈、堆 |
| [四种 cast](/zh/ref/cpp-casts/) | 指针调整、`dynamic_cast` 查 typeinfo、严格别名 | 进程地图：`.rodata` |
| **内存** | | |
| [new 一次走到哪](/zh/ref/new-malloc-page-fault/) | `operator new`、malloc、`brk` / `mmap`、第一次写时缺页 | 进程地图：堆、mmap 区 |
| [函数调用栈帧](/zh/ref/stack-frame/) | 返回地址、寄存器传参、RVO、栈溢出 | 进程地图：栈 |
| [unique_ptr 和 weak_ptr](/zh/ref/unique-ptr-weak-ptr/) | 独占所有权、删除器、打破循环引用 | 进程地图：堆 |
| [shared_ptr](/zh/ref/shared-ptr/) | 控制块、复制的代价、`enable_shared_from_this` | 进程地图：堆 |
| **并发** | | |
| [线程同步](/zh/ref/thread-sync/) | 互斥锁、条件变量、信号量、读写锁、死锁 | 进程地图：线程共享的段 |
| [线程池和 future](/zh/ref/thread-pool-future/) | `std::thread`、promise、`async`、手写线程池 | 进程地图：每个线程的栈 |
| **进程和文件** | | |
| [进程和线程](/zh/ref/process-thread-fork/) | `fork`、写时复制、共享与独占、进程状态 | 进程地图、从源码到进程：`execve` |
| [进程间通信](/zh/ref/ipc/) | 管道、共享内存、信号、Unix socket | 进程地图：mmap 区；IO 地图 |
| [文件 IO](/zh/ref/file-io/) | fd 三层结构、重定向、stdio 缓冲、inode、fsync | IO 地图：写文件 |
| [epoll](/zh/ref/epoll-internals/) | 红黑树、就绪链表、回调，LT 和 ET | IO 地图：epoll |
| **网络** | | |
| [TCP 连接](/zh/ref/tcp-states/) | 三次握手、四次挥手、`TIME_WAIT`、握手丢包 | IO 地图：TCP/IP 协议栈 |
| [TCP 可靠传输](/zh/ref/tcp-reliability/) | 重传、流量控制、拥塞控制、Nagle、粘包 | IO 地图：收一个包 |
| [socket 编程](/zh/ref/socket-programming/) | 服务端和客户端的调用、回显服务器、Reactor | IO 地图：socket |
| [HTTP 和 HTTPS](/zh/ref/http-basics/) | 一次请求的全过程、状态码、Cookie、TLS 握手 | IO 地图：TCP/IP 协议栈之上 |
| **数据结构** | | |
| [STL 容器](/zh/ref/stl-containers/) | vector 扩容、deque、红黑树 map、哈希桶 | 进程地图：堆 |
| [LRU 缓存](/zh/ref/lru-cache/) | 哈希表加双向链表、`splice`、带哨兵的手写链表 | IO 地图：页缓存怎么淘汰 |
| [跳表、红黑树、B+ 树](/zh/ref/skiplist-rbtree-bplustree/) | 三种有序结构的原理和用处（std::map、Redis、InnoDB） | — |
