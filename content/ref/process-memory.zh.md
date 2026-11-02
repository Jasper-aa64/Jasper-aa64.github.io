---
title: "进程地图：一个 C++ 程序在内存里的样子"
description: "一个进程的虚拟地址空间从高到低有哪几段，C++ 里写的全局变量、局部变量、new 出来的内存、线程栈各落在哪；这些虚拟地址怎么经页表落到物理内存上，为什么第一次碰一页要缺页；在自己机器上怎么看，低延迟系统怎么用。"
date: 2026-11-02
slug: "process-memory"
weight: 12
toc: true
---

这页是随时翻的总图，和[硬件地图](/zh/ref/cpu-memory/)是一对。硬件地图讲一次访存经过哪些硬件；这页讲访存之前的那一步：程序里的地址是从哪来的，指向哪一段，又怎么变成硬件地图上的物理地址。细分的知识点（fork、动态链接、IO）写在各自的文章里，这页只放总图和最常翻的几张表。

## 1. 进程地图：一个进程的虚拟地址空间 {#map}

<a href="/maps/process-map.zh.html" target="_blank" rel="noopener"><img src="/images/ref/process-map.zh.svg" alt="进程地图：左边是 x86-64 上一个进程的虚拟地址空间，从高到低依次是内核空间、非规范地址空洞、主线程的栈、vDSO、mmap 区（共享库、大块 malloc、其他线程的栈和 TLS、文件映射和共享内存）、没映射的空地、堆、.bss、.data、.rodata、.text 和最低 64 KiB 的不映射区；右边是 C++ 变量各放在哪、线程共享什么、页表和缺页怎么把虚拟地址落到物理内存、在自己机器上怎么看、低延迟系统怎么用。" loading="lazy" decoding="async"></a>

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

### 1.5 低延迟系统怎么用 {#hft}

热路径最怕“第一次”：第一次碰一页要缺页，第一次 `malloc` 一块大内存要进内核。所以启动时就把要用的内存全分好、每页写一遍，再 `mlockall` 锁住，运行时只在这些内存里分配（[#3](/zh/posts/hot-path-memory-allocators/)）。热数据放 2 MiB 大页，同样大小的数据占的 TLB 项少得多（[#6](/zh/posts/alignment-layout-cache-dram-geometry/)）。改页表（`munmap`、`mprotect`）会让内核给跑过这个进程的核都发中断、刷 TLB，热路径上一律不做（[#3 2.2](/zh/posts/hot-path-memory-allocators/#22-isolcpus-替你挡不住的税tlb-shootdown)）。共享内存的同一批物理页在每个进程里的虚拟地址可能不同，所以里面只存偏移、不存指针（[#5 2.2](/zh/posts/spmc-shared-memory-broadcast-ring/#22-同样的字节不同的地址)）。
