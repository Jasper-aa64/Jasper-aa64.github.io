---
title: "低时延交易 —— 上下文切换、页表与 TLB"
date: 2026-11-04
slug: "low-latency-context-switch-page-table-tlb"
list_after: "low-latency-memory-latency-bandwidth"
recent: false
description: "线程切换和进程切换的直接开销都在 1–5 µs，两者在这一步只差要不要改写 CR3，真正的差别在切换之后 TLB 和缓存还热不热。页表每个进程一份，CR3 和 TLB 每个核一份，PCID 让换进程不必清空 TLB。TLB 没有 MESI，改页表要发 IPI 通知此刻 CR3 还指着这份页表的核，绑核和 isolcpus 都挡不住；热路径上 free 一大块内存、munmap、透明大页合并、NUMA 自动平衡、fork 都会触发它。最后是怎么看出来。"
summary: "线程比进程轻，轻在切换之后 TLB 和缓存还能接着用，不在切换本身。TLB 没有 MESI：同一个进程里任何一个线程改了页表，此刻还装着这份页表的核都要被打断一次，绑核和 isolcpus 挡不住，所以热路径进程跑起来以后地址空间只读不改。"
chapter: 1
categories: [Systems]
tags: [linux, context-switch, page-table, tlb, pcid, tlb-shootdown, hft, low-latency]
toc: true
---

热线程绑在隔离核上忙轮询，不调系统调用，p999 却偶尔多出 1–5 µs。`perf` 里找不到热点，`/proc/interrupts` 里这个核的 `TLB` 那一行却在涨：同一个进程里的日志线程 `free` 了一大块内存，glibc 把它 `munmap` 还给内核，内核改了页表，就得打断热核。要看懂这件事，得先知道切换线程、切换进程时到底换了什么，页表和 TLB 各是每个进程一份还是每个核一份。这篇从一次切换讲起，再讲页表和 TLB，最后讲改页表时为什么要打断别的核、热路径上有哪些操作会触发它。

## 1. 上下文切换：线程和进程差在哪 {#switch}

“线程比进程轻”常被说成：线程切换不用换页表、不用刷 TLB，只换几个寄存器，所以快一个数量级。前半句对，后半句不对。

### 1.1 一次切换做了什么：保存、换栈、恢复 {#what}

1. **切换之前**
   - **已经在内核里**：线程进内核时（系统调用、中断、被抢占），用户态寄存器已经存到它自己的内核栈上了（[用户态和内核态](/zh/ref/user-kernel-mode/#entry)）。
   - **只在内核里换**：调度器是内核代码，所以换线程只发生在进了内核以后。
2. **`context_switch()` 做两件事**
   - **换地址空间（`switch_mm`）**：下一个任务属于另一个进程，才把 CR3 改成那个进程的页表（2.1）。同一个进程的线程共用一个 `mm`，这一步跳过。
   - **换执行现场（`switch_to`）**：保存当前任务在内核里的几个寄存器和栈指针，换到下一个任务的内核栈，恢复它的寄存器。回用户态时，再从它的内核栈上取回用户态寄存器。浮点和向量寄存器也要换，开了 AVX-512 时这一份就有 2 KiB 多。
3. **时间花在哪**
   - **直接开销**：连同唤醒、调度在内约 1–5 µs，线程切换和进程切换差得不多。
   - **大头不在换寄存器**：这些都在 CPU 上做，不碰磁盘、不等别人。时间更多花在进出内核、唤醒和调度器挑下一个任务上。
   - **结论**：**线程切换和进程切换在这一步只差一处：要不要改写 CR3。**

### 1.2 切换之后要重新热起来，换核也一样 {#after}

1. **换进程之后**
   - **缓存是冷的**：新进程的数据多半已经不在 L1、L2 里（每个核只有几十 KiB 和一两 MiB），每次访问都要去 L3 或内存取。
   - **TLB 也是冷的**：TLB 里它的项很少，每碰一个新页就要查一遍页表（2.2）。
2. **同一进程的线程之间**
   - **还热的**：代码、堆上共享的数据、TLB 里的翻译。
   - **未必热的**：各自的栈和私有数据。
3. **线程换核**
   - **页表不用动**：新核的 CR3 指向同一份页表，翻译规则没变，什么都不用清。
   - **但都是冷的**：L1、L2 和 TLB 都是每个核私有的，线程攒下的热数据、指令和翻译都留在原来那个核上。到了新核，数据要从 L3（跨插槽时从远端内存）重新取，TLB 也要一页一页查表填回来。绑核（[#1](/zh/posts/cpu-affinity-core-isolation-numa/)）消掉的就是这一笔。
   - **结论**：**切换的代价大半摊在切换之后的那段执行里，只测切换本身会低估。线程比进程轻，轻在切换之后 TLB 和缓存还能接着用。**
4. **怎么看出来**

   ```bash
   grep ctxt_switches /proc/<PID>/task/<TID>/status          # voluntary：自己睡下；nonvoluntary：被抢占
   perf stat -e context-switches,cpu-migrations -t <TID> -- sleep 10
   ```

   - **`ctxt_switches`**：`/proc` 里每个线程一份。`voluntary` 在涨，说明热路径上有会睡的调用；`nonvoluntary` 在涨，说明核上还有别的任务在抢。
   - **`cpu-migrations`**：线程被挪到别的核的次数，在涨说明没绑住。
   - **热线程**：这几个数都应当接近 0。

## 2. 页表、CR3 与 TLB：地址翻译在哪一层 {#page-table-tlb}

### 2.1 页表每个进程一份，CR3 每个核一个 {#cr3}

1. **页表**
   - **是什么**：程序用的是虚拟地址，访存前要翻译成物理地址，翻译规则就是进程的页表。x86-64 上它是一棵 4 级的树，每级 512 项。
   - **每个进程一份**：内核里的 `mm_struct`，同一进程的线程共用它。
2. **CR3**
   - **是什么**：每个核一个的寄存器，存着这个核此刻在用的那份页表的根页物理地址。
   - **同一时刻**：几个核的 CR3 可以指向同一份页表（同一进程的几个线程各在一个核上跑），也可以指向不同的页表（跑的是不同进程）。
   - **切换时**：切到同一进程的另一个线程，CR3 本来就对，不用动；切到别的进程，要写入那个进程的页表根。从这一刻起，同一个虚拟地址在这个核上翻译出来是另一个物理页，或者根本没有映射。

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

### 2.2 TLB：每个核一份的翻译缓存 {#tlb}

1. **为什么要有**
   - **查页表太慢**：每次访存都去 4 级页表里查一遍，等于每次访存前先多读 4 次内存。
   - **所以缓存翻译**：每个核把最近用过的翻译放在自己的 TLB（translation lookaside buffer）里。
2. **多大、能盖住多少**
   - **两级**：L1 dTLB 64–96 项，二级的 STLB 1500–3000 项，每项管一页。
   - **TLB reach**：4 KiB 页时，STLB 盖住约 6–12 MiB；换成 2 MiB 大页，同样的项数能盖住 3–6 GiB。
   - **详见**：工作集台阶、大页怎么帮忙，在[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/)第 3.2 节。
3. **没命中要多久**
   - **page walk**：硬件从 CR3 出发，一级一级读页表项。页表项也是内存里的普通数据，常用的那些就在 L1、L2、L3 里，CPU 还有缓存上面几级页表项的 page-walk cache。
   - **所以只多一点**：从内存读一个数，TLB 命中约 70–90 ns，没命中约 85–120 ns，多出 15–30 ns（[速查 2.1](/zh/ref/cpu-memory/#latency)）。4 级页表项全都要从内存读的情况很少，真遇上了，一次约 300–400 ns。
   - **热路径上的大表**：订单簿、id 映射这类随机访问、又超过几 MiB 的表，放在大页上，就能去掉这一级。

### 2.3 PCID：换进程不一定清空 TLB {#pcid}

1. **没有 PCID 时**
   - **写 CR3 就清**：TLB 里每一项都是按某一份页表算出来的，换了页表，旧的翻译对新进程就是错的，所以写 CR3 会清掉所有非全局的项。
   - **全局项不清**：内核的映射在每个进程里都一样，标了全局（global），不跟着清。
2. **有 PCID 时**
   - **打标签**：PCID（process-context identifier）给每一项打上地址空间的标签。写 CR3 时带上新标签，不用清：旧进程的项还在，只是新进程查不到，等它切回来还能接着用。
   - **作用有限**：Linux 从 4.14 起用 PCID，但每个核只轮换几个号，TLB 一共也就几千项，一个进程歇了一阵再回来，它的项多半已经被别人挤掉了。
3. **KPTI 也靠它**
   - **为什么要切**：受 Meltdown 影响的 CPU 上，每次进出内核都要写 CR3，在用户页表和完整页表之间切换（[用户态和内核态](/zh/ref/user-kernel-mode/#kpti)）。
   - **PCID 省的是清空**：没有 PCID，每次系统调用都要清一遍 TLB；有了它，两份页表的项各带各的标签，切来切去不用清。

### 2.4 三种情况放在一起 {#compare}

| | CR3 | TLB | L1、L2 |
|---|---|---|---|
| 同一进程的线程，同一个核 | 不动 | 接着用 | 共享的数据还热，各自的栈和私有数据未必 |
| 线程换核 | 新核指向同一份页表 | 新核上是冷的，按需查表填回来 | 冷，从 L3 或内存重新取 |
| 换进程 | 改写 | 没有 PCID 就清空；有 PCID 也多半被挤掉了 | 多半被上一个任务挤掉了 |

**差别都在切换之后。** 创建也一样：线程用 `clone` 共用 `mm`，不复制页表；`fork` 要给子进程复制一份页表（[进程和线程](/zh/ref/process-thread-fork/)第 2.2 节）。

## 3. TLB shootdown：改页表要打断别的核 {#shootdown}

### 3.1 TLB 没有 MESI {#no-mesi}

1. **数据缓存和 TLB 不一样**
   - **数据缓存**：之间有 [MESI](/zh/posts/low-latency-mesi-cache-coherence/)，一个核写一条行，硬件自动让别的核的副本作废。
   - **TLB**：没有这套机制。内存里的页表项被改了，别的核 TLB 里缓存的旧翻译不会自己作废。
2. **内核怎么补**
   - **本核**：改完页表项（`munmap`、`mprotect`、搬页、合并透明大页），先用 `invlpg` 作废本核的项。
   - **别的核**：给要通知的核发一个核间中断（IPI），对方进中断处理程序作废对应的项，再回话。
   - **等齐回话**：发起的核要等所有回话到齐才往下走。在那之前，别的核还可能顺着旧翻译，写到一个已经还给系统的物理页。
   - **名字**：这一来一回叫 **TLB shootdown**。

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="核 2 上的冷线程调 munmap：改页表项，invlpg 作废本核的项，给此刻 CR3 还指着这份页表的核发 IPI，等齐回话才往下走。同进程热线程所在的核 5 和跑着同进程另一个线程的核 3 都收到 IPI；核 7 刚跑过这个进程、现在在跑别的进程，不发 IPI，切回来时发现页表改过再自己清。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <rect class="cx-bg" x="0" y="0" width="760" height="300" rx="10"/>
  <text class="cx-title" x="24" y="30">TLB 没有 MESI：改了页表，要发 IPI 一个个通知</text>
  <rect class="cx-reg" x="24" y="60" width="250" height="114" rx="6"/>
  <text class="cx-lbl" x="36" y="84" font-weight="700">核 2：冷线程调 munmap</text>
  <text class="cx-cap" x="36" y="106">① 改页表项</text>
  <text class="cx-cap" x="36" y="124">② invlpg 作废本核的项</text>
  <text class="cx-cap" x="36" y="142">③ 给 CR3 还指着这份页表的核发 IPI</text>
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

> 图：数据缓存靠硬件互相作废，TLB 靠内核发中断。此刻还装着这份页表的核都要停下来处理一次，发起的核等它们全部回话；已经切走的核留到切回来时再清。

3. **谁付代价**
   - **发起的核**：同步等待，等最慢的那个核回话。
   - **收到 IPI 的核**：被打断一次，进内核、作废、回话，和一次中断差不多，约 1–5 µs，回来以后缓存还被挤过一遍。
   - **结论**：**绑核和 `isolcpus` 都挡不住它。** 它们管的是调度器把任务放到哪，IPI 是硬件中断，不经过调度器（[#3](/zh/posts/hot-path-memory-allocators/) 第 2.2 节）。

### 3.2 通知谁：此刻 CR3 还指着这份页表的核 {#who}

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
4. **内核自己的映射**
   - **哪些**：`vmalloc` 出来的区域、加载的模块，在每个地址空间里都有。
   - **通知谁**：改了就要通知所有核。内核会攒一批，再一起清。
5. **硬件广播**
   - **哪些 CPU**：ARM64 的 `TLBI … IS` 指令，较新 AMD 的 `INVLPGB` 指令。
   - **怎么做**：硬件把作废请求广播给所有核，对方不进中断。
   - **没有名单**：不按进程挑核，也就用不上上面这份名单。

### 3.3 热路径上谁会触发 {#triggers}

**同一个进程里，任何一个线程改了用户空间的页表，正在跑的其他线程都要陪着被打断一次。** 热线程自己不改，进程里别的线程、内核的后台任务也会改。新增映射不用通知：没有映射的地址不会进 TLB，要作废的只有删掉映射、收紧权限、换掉物理页这几种。

| 来源 | 为什么会改页表 | 怎么避开 | 详见 |
|---|---|---|---|
| `free` 一大块内存 | 128 KiB 以上默认单独 `mmap`，`free` 时直接 `munmap`；空闲多了，glibc 还会缩堆、`madvise` 还页 | 启动时预分配，热路径用内存池；`mallopt` 关掉 mmap 和缩堆 | [#3](/zh/posts/hot-path-memory-allocators/) 第 2 节 |
| 运行期间 `munmap`、`mprotect`、`mremap` | 直接删映射、收紧权限、搬映射 | 映射在启动时做完，运行期间不动 | [new 一次走到哪](/zh/ref/new-malloc-page-fault/) |
| `fork` | 父进程的可写页全改成只读（写时复制），之后谁先写谁换页 | 热路径进程运行期间不 `fork`，要起子进程在启动时起好 | [进程和线程](/zh/ref/process-thread-fork/)第 2.2 节 |
| 透明大页的后台合并（`khugepaged`） | 把 512 个小页换成一个大页，旧的翻译要作废 | `transparent_hugepage=never`；要大页就自己申请 | [#19](/zh/posts/scheduling-priority-inversion-kernel-tuning/) 第 4.4 节 |
| 自动 NUMA 平衡 | 周期性把页标成不可访问，借缺页统计谁在用，再把页迁过去 | `kernel.numa_balancing=0`，自己用 `numactl` 绑 | [#19](/zh/posts/scheduling-priority-inversion-kernel-tuning/) 第 4.4 节 |
| KSM、内存压缩 | 合并相同的页、搬动物理页，都要换翻译 | 关掉 KSM；`vm.compact_unevictable_allowed=0`，让压缩不搬锁住的页 | [#19](/zh/posts/scheduling-priority-inversion-kernel-tuning/) 第 4.4 节 |

- **进程里的线程**：前三行是自己的代码做的，在代码里找出来、挪到启动阶段。
- **内核的后台任务**：后三行是内核自己做的，要靠启动参数和 sysctl 关掉。
- **结论**：**热路径进程跑起来以后，地址空间只读不改：要的内存启动时映射好、写一遍、锁住；释放、整理留到收盘以后。**

### 3.4 怎么看出来 {#see}

```bash
watch -d -n 1 'grep TLB /proc/interrupts'                  # 每个核一列，看热核那一列涨不涨
strace -f -e trace=munmap,mprotect,mremap,madvise -p <PID>  # 进程里谁在改映射
```

- **`/proc/interrupts` 的 `TLB` 行**：每个核收到的 TLB shootdown 次数。热核那一列在涨，就是有东西在改这个进程的页表。
- **strace 抓到调用**：是进程自己的线程在改，`-f` 会带上线程号，能对上是哪个线程。
- **strace 什么都没抓到**：再看内核那几项后台任务（透明大页、NUMA 平衡、KSM）开着没有。
- **strace 会拖慢被跟踪的进程**：每个系统调用都要停下来记录，只在排查时用，别挂在生产的热路径进程上。
