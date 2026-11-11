---
title: "交易系统笔记 #2：内存序与缓存行"
date: 2026-09-15
slug: "memory-ordering-false-sharing-dependency-chains"
description: "为什么一个写不会马上被别的核看见（store buffer、invalidate queue），x86 为什么只允许 StoreLoad 乱序，release/acquire 怎么只在需要的地方补上顺序、在 x86 和 ARM 上各花多少钱；伪共享为什么和读到旧值是两回事。"
summary: "同一套缓存硬件带出两个不相干的问题。正确性：写先进 store buffer，别的核要过一段时间才看得见，靠 release/acquire 配对补上顺序。性能：就算每个值都读对了，两个核抢同一条缓存行（伪共享）照样慢，靠缓存行布局解决。"
chapter: 1
categories: [Systems]
tags: [cpp, memory-model, atomics, cache-coherence, false-sharing, mesi, x86, hft, low-latency]
toc: true
homepage: false
math: true
---

线程 A 先写 `y = 1`、再写 `x = 1`，线程 B 看到 `x == 1` 以后去读 `y`，一定能读到 1 吗？另一个问题：两个线程各自累加自己的计数器，不共享任何变量，代码也没有 bug，为什么两个计数器挨着放在同一个结构体里时，循环会慢好几倍？

两个问题背后是同一套硬件：每个核私有的缓存、64 字节的缓存行、让各核缓存保持一致的协议（MESI）。可它们是两类问题。**第一个问的是正确性：读到的值对不对，答案非对即错；第二个问的是性能：值都读对了，花了多少个周期。** 前者用 C++ 内存模型（`std::atomic`、`memory_order`）解决，后者用缓存行布局解决，混在一起就会拿错工具。第 1 节讲正确性，第 2 节讲伪共享。单个核内部的依赖链，是“值都对、照样慢”的另一种情况，放在 [#9 循环优化](/zh/posts/loop-optimization/#dependency-chains) 第 3 节。

---

## 1. 正确性：一个写为什么不会马上被别的核看见 {#ordering}

### 1.1 store buffer：写先记下来，指令就算做完了 {#store-buffer}

线程执行 `x = 1` 时，这个写不是直接进缓存的。它先进每个核私有的一个小队列，叫 **store buffer**，进去以后这条指令就算执行完了，线程接着执行下一条。

这样做是因为**真正把写放进缓存很慢**：如果别的核的缓存里也有这一行，就得先让它们把副本作废、等它们回确认（ACK），本核拿到这一行的独占权，写才能落进去，一来一回要几十纳秒。要是每个写都停下来等，流水线就一直在空转。有了 store buffer，等独占权这件事在后台进行，只有队列满了，流水线才会停下来。

<svg viewBox="0 0 760 410" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="store buffer 夹在执行单元和 L1D 之间：写进队尾，指令就算做完；队头的写先向核 1 发 invalidate 请求，核 1 放进 invalidate queue 马上回 ACK；收齐 ACK、拿到独占权后，队头的写才进 L1D。x86 上先进先出，data 进 L1D 之后 ready 才轮到。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sb-bg    { fill: #fbfaf7; }
    .sb-panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .sb-muted { fill: #6b6558; }
    .sb-core  { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .sb-buf   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .sb-inbox { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.6; }
    .sb-line  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .sb-slot  { fill: #ffffff; stroke: #6f8f3f; stroke-width: 1.2; }
    .sb-empty { fill: none; stroke: #9db577; stroke-width: 1; stroke-dasharray: 4 3; }
    .sb-arrow { stroke: #8a8474; stroke-width: 2; fill: none; marker-end: url(#ahsb); }
    .sb-rfo   { stroke: #c15b3f; stroke-width: 2; fill: none; marker-end: url(#ahsb2); }
    .sb-title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .sb-lbl   { fill: #3a372f; font-size: 11px; }
    .sb-cap   { fill: #6b6558; font-size: 10.5px; }
    .sb-red   { fill: #c15b3f; font-size: 10.5px; }
    .sb-gap   { fill: #c15b3f; font-size: 11px; font-weight: 700; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-panel { fill: #201f26; stroke: #3a3945; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-muted { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-core { fill: #2a2933; stroke: #47454f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-buf { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-inbox { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-line { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-slot { fill: #201f26; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-empty { stroke: #5f7a3a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-arrow { stroke: #9a9384; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-rfo { stroke: #e0795b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-title { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-lbl { fill: #d7d3c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-cap { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-red { fill: #e0795b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .sb-gap { fill: #e0795b; }
  </style>
  <defs>
    <marker id="ahsb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ahsb2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="sb-bg" x="0" y="0" width="760" height="410" rx="10"/>
  <text class="sb-title" x="24" y="30">store buffer 夹在流水线和 L1D 之间：等 ACK 的是队头这条写</text>
  <rect class="sb-panel" x="24" y="48" width="420" height="298" rx="8"/>
  <text class="sb-muted" x="40" y="70" font-size="12" font-weight="700">核 0（写方）</text>
  <rect class="sb-core" x="40" y="84" width="388" height="46" rx="6"/>
  <text class="sb-lbl" x="52" y="104" font-weight="700">执行单元（流水线）</text>
  <text class="sb-cap" x="52" y="120">写一进队尾就算做完，接着执行下一条</text>
  <path class="sb-arrow" d="M234 130 L234 152"/>
  <rect class="sb-buf" x="40" y="154" width="388" height="100" rx="6"/>
  <text class="sb-lbl" x="52" y="174" font-weight="700">store buffer（本核私有，先进先出）</text>
  <rect class="sb-empty" x="56" y="186" width="80" height="34" rx="4"/>
  <rect class="sb-empty" x="148" y="186" width="80" height="34" rx="4"/>
  <rect class="sb-slot" x="240" y="186" width="80" height="34" rx="4"/>
  <text class="sb-lbl" x="280" y="207" text-anchor="middle">ready = 1</text>
  <rect class="sb-slot" x="332" y="186" width="80" height="34" rx="4" stroke-width="2"/>
  <text class="sb-lbl" x="372" y="207" text-anchor="middle" font-weight="700">data = 42</text>
  <text class="sb-cap" x="280" y="240" text-anchor="middle">后进</text>
  <text class="sb-cap" x="372" y="240" text-anchor="middle">队头</text>
  <path class="sb-arrow" d="M372 254 L372 286"/>
  <rect class="sb-line" x="40" y="288" width="388" height="46" rx="6"/>
  <text class="sb-lbl" x="52" y="308" font-weight="700">L1D</text>
  <text class="sb-cap" x="52" y="324">队头拿到这一行的独占权（M），才写进来</text>
  <rect class="sb-panel" x="536" y="48" width="200" height="298" rx="8"/>
  <text class="sb-muted" x="552" y="70" font-size="12" font-weight="700">核 1（有 data 的副本）</text>
  <path class="sb-rfo" d="M428 178 L550 178"/>
  <text class="sb-red" x="490" y="170" text-anchor="middle">invalidate 请求</text>
  <path class="sb-arrow" d="M552 204 L430 204"/>
  <text class="sb-cap" x="490" y="222" text-anchor="middle">ACK</text>
  <rect class="sb-inbox" x="552" y="154" width="168" height="62" rx="6"/>
  <text class="sb-lbl" x="564" y="178" font-weight="700">invalidate queue</text>
  <text class="sb-cap" x="564" y="198">先回 ACK，之后才作废</text>
  <path class="sb-arrow" d="M636 216 L636 286"/>
  <rect class="sb-line" x="552" y="288" width="168" height="46" rx="6"/>
  <text class="sb-lbl" x="564" y="308" font-weight="700">L1D</text>
  <text class="sb-cap" x="564" y="324">data 的旧副本 → I</text>
  <text class="sb-gap" x="24" y="372">流水线不等 ACK；store buffer 满了，流水线才停。</text>
  <text class="sb-cap" x="24" y="392" font-size="11">x86 上先进先出：data 进了 L1D，ready 才轮到，所以别的核不会先看到 ready。</text>
</svg>

> 图：store buffer 在执行单元和 L1D 之间排成一队。写进队尾，指令就退休；队头那条写要先让别的核作废副本、收齐 ACK，拿到这一行才进 L1D。所以要等 ACK 的是这条写，不是流水线；只有队满了，流水线才停下来。

代价是：**一个写从“指令做完了”到“别的核看得见”，中间隔着一段时间，通常几十纳秒。** 这段时间里，写还在 A 自己的 store buffer 里，别的核去读 `x`，读到的还是旧值。

线程 A 自己感觉不到这段时间。A 写了 `x` 以后马上读 `x`，CPU 会直接从 store buffer 里把刚写的值转给这次读（store-to-load forwarding），所以 A 看自己的写永远是按程序顺序来的。**这段时间只有别的核才看得到**，它不是 bug，也不是编译器造成的，是硬件为了不让流水线停下来必然付的代价。后面讲的乱序，都是从这里来的。

**转发有一个条件：这次读要的字节，必须完整地落在 store buffer 里的某一条写之内。** 读 4 字节、前面写过 8 字节且覆盖了这 4 字节，可以转发；写了 4 字节、紧接着从同一地址读 8 字节，一条写满足不了，转发失败，这次读要等写真正进了缓存才能完成，多等十几个周期。转发不会把几条写拼起来用。

### 1.2 invalidate queue：收到作废请求，先回 ACK 再处理 {#invalidate-queue}

读的一方也有一个类似的缓冲。核 B 的缓存里有 `x` 这一行，核 A 发来作废请求时，B 不马上处理，而是把请求放进自己的 **invalidate queue**，立刻回 ACK，让 A 不用等。B 在处理这条请求之前去读 `x`，读到的还是自己缓存里的旧值。

两个缓冲合在一起，就是跨核读写会乱序的物理原因：

| 缓冲 | 在哪一侧 | 推迟了什么 | 会造成的乱序 |
|---|---|---|---|
| store buffer | 写方 | 写对别的核可见 | 后面的读越过前面的写（StoreLoad） |
| invalidate queue | 读方 | 察觉到别人已经写了 | 后面的读比前面的读还旧（LoadLoad） |

x86 硬件保证读和读不乱序，所以在 x86 上，invalidate queue 造不成可见的乱序；ARM 这类弱序 CPU 不保证，两种都会出现。

<svg viewBox="0 0 760 480" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="核 A 写 x = 1：写进 store buffer，指令退休，发出 invalidate 请求；核 B 把请求放进 invalidate queue，立刻回 ACK；核 B 读 x，队列里的请求还没处理，L1D 里还是旧值 0" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .iq2bg { fill: #fbfaf7; }
    .iq2pn { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .iq2cd { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .iq2sb { fill: #fff3c4; stroke: #c9a227; stroke-width: 1.4; }
    .iq2q  { fill: #fbe3d4; stroke: #d0773f; stroke-width: 1.4; }
    .iq2l1 { fill: #e3f0fb; stroke: #6aa7d8; stroke-width: 1.4; }
    .iq2sl { fill: #ffffff; stroke: #8a8474; stroke-width: 1.2; }
    .iq2bad { fill: #fde7e4; stroke: #c84b3a; stroke-width: 1.4; }
    .iq2t  { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .iq2h  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .iq2x  { fill: #1c1b18; font-size: 12.5px; }
    .iq2m  { fill: #6b6558; font-size: 12px; }
    .iq2c  { fill: #1c1b18; font-size: 13px; font-family: 'JetBrains Mono', Consolas, ui-monospace, monospace; }
    .iq2r  { fill: #c84b3a; font-size: 12px; font-weight: 700; }
    .iq2go { stroke: #6b6558; stroke-width: 2; fill: none; }
    .iq2in { stroke: #d0773f; stroke-width: 2.2; fill: none; }
    .iq2ak { stroke: #3f8f4a; stroke-width: 2.2; fill: none; }
    .iq2rd { stroke: #3a7dc0; stroke-width: 2.2; fill: none; }
    .iq2n  { font-size: 12px; font-weight: 700; fill: #ffffff; }
    .iq2ah-go { fill: #6b6558; } .iq2ah-in { fill: #d0773f; } .iq2ah-ak { fill: #3f8f4a; } .iq2ah-rd { fill: #3a7dc0; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2pn { fill: #201f26; stroke: #3a3945; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2cd { fill: #2a2933; stroke: #47454f; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2sb { fill: #3a3216; stroke: #a8892a; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2q { fill: #3d2618; stroke: #c06b37; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2l1 { fill: #16263a; stroke: #3f78ad; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2sl { fill: #26252d; stroke: #6e6a7a; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2bad { fill: #3d1d1f; stroke: #e5655a; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2t, :root:is([data-theme="dark"], [data-theme="black"]) .iq2h, :root:is([data-theme="dark"], [data-theme="black"]) .iq2x, :root:is([data-theme="dark"], [data-theme="black"]) .iq2c { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2m { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2r { fill: #ff7b72; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2go { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2ah-go { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2in { stroke: #f0883e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2ah-in { fill: #f0883e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2ak { stroke: #56c26a; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2ah-ak { fill: #56c26a; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2rd { stroke: #58a6ff; }
    :root:is([data-theme="dark"], [data-theme="black"]) .iq2ah-rd { fill: #58a6ff; }
  </style>
  <defs>
    <marker id="iq2go" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="iq2ah-go"/></marker>
    <marker id="iq2in" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="iq2ah-in"/></marker>
    <marker id="iq2ak" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="iq2ah-ak"/></marker>
    <marker id="iq2rd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="iq2ah-rd"/></marker>
  </defs>
  <rect class="iq2bg" x="0" y="0" width="760" height="480" rx="10"/>
  <text class="iq2t" x="20" y="32">写的一方有 store buffer，读的一方有 invalidate queue</text>
  <rect class="iq2pn" x="20" y="50" width="310" height="350" rx="10"/>
  <text class="iq2h" x="38" y="76">核 A（写方）</text>
  <rect class="iq2cd" x="38" y="90" width="274" height="40" rx="6"/>
  <text class="iq2c" x="56" y="115">x = 1;</text>
  <path class="iq2go" d="M175,130 V158" marker-end="url(#iq2go)"/>
  <circle cx="200" cy="144" r="10" fill="#6b6558"/><text class="iq2n" x="200" y="148" text-anchor="middle">1</text>
  <text class="iq2m" x="216" y="148">写进 store buffer</text>
  <rect class="iq2sb" x="38" y="162" width="274" height="80" rx="6"/>
  <text class="iq2h" x="52" y="184">store buffer</text>
  <rect class="iq2sl" x="52" y="196" width="110" height="30" rx="4"/>
  <text class="iq2c" x="107" y="216" text-anchor="middle">x = 1</text>
  <text class="iq2m" x="172" y="208">指令到这里</text>
  <text class="iq2m" x="172" y="224">就算执行完了</text>
  <rect class="iq2l1" x="38" y="262" width="274" height="60" rx="6"/>
  <text class="iq2h" x="52" y="284">L1D</text>
  <text class="iq2x" x="52" y="308">x = 0，收齐 ACK 才写成 1</text>
  <text class="iq2m" x="38" y="352">A 自己读 x，从 store buffer</text>
  <text class="iq2m" x="38" y="370">直接拿到 1；别的核还看不到。</text>
  <rect class="iq2pn" x="430" y="50" width="310" height="350" rx="10"/>
  <text class="iq2h" x="448" y="76">核 B（读方）</text>
  <rect class="iq2q" x="448" y="162" width="274" height="80" rx="6"/>
  <text class="iq2h" x="462" y="184">invalidate queue</text>
  <rect class="iq2sl" x="462" y="196" width="130" height="30" rx="4"/>
  <text class="iq2x" x="527" y="216" text-anchor="middle">作废 x</text>
  <text class="iq2r" x="604" y="216">还没处理</text>
  <rect class="iq2l1" x="448" y="262" width="274" height="60" rx="6"/>
  <text class="iq2h" x="462" y="284">L1D</text>
  <rect class="iq2bad" x="462" y="292" width="246" height="24" rx="4"/>
  <text class="iq2x" x="474" y="309">x = 0（旧值，还没被作废）</text>
  <rect class="iq2cd" x="448" y="344" width="274" height="40" rx="6"/>
  <text class="iq2c" x="466" y="369">r = x;</text>
  <text class="iq2r" x="560" y="369">读到 0</text>
  <path class="iq2rd" d="M680,344 V324" marker-end="url(#iq2rd)"/>
  <circle cx="700" cy="334" r="10" fill="#3a7dc0"/><text class="iq2n" x="700" y="338" text-anchor="middle">4</text>
  <path class="iq2in" d="M312,190 H446" marker-end="url(#iq2in)"/>
  <circle cx="340" cy="174" r="10" fill="#d0773f"/><text class="iq2n" x="340" y="178" text-anchor="middle">2</text>
  <text class="iq2m" x="356" y="178">invalidate x</text>
  <path class="iq2ak" d="M448,224 H316" marker-end="url(#iq2ak)"/>
  <circle cx="340" cy="242" r="10" fill="#3f8f4a"/><text class="iq2n" x="340" y="246" text-anchor="middle">3</text>
  <text class="iq2m" x="356" y="246">先回 ACK</text>
  <text class="iq2x" x="20" y="428">① A 的写进 store buffer，指令退休。② A 发出作废 x 的请求。③ B 把请求放进队列，马上回 ACK。</text>
  <text class="iq2x" x="20" y="450">④ B 读 x：请求还在队列里没处理，L1D 里的 x 没被作废，读到旧值 0。</text>
  <text class="iq2m" x="20" y="470">两个缓冲都是为了不让流水线等一次跨核往返；它们造成的乱序见上表。</text>
</svg>

> 图：A 的写进了自己的 store buffer，指令就退休了；B 收到作废请求，先放进 invalidate queue、马上回 ACK。B 在处理这条请求之前读 x，读到的还是旧值。两个缓冲存在的理由相同：别让流水线为一次跨核往返停下来。

把这两个缓冲放回整块芯片上，一次写要走过的路径如下，按步骤点下去看。invalidate 请求经片上互连，只发给缓存里有这一行的核，谁有由 L3 旁的 snoop filter 记着；新值不会被推过去，读方要用时自己来取。最后一步，读方已经看到了新的 `ready`，读 `data` 却拿到旧值，这就是读和读的乱序。

<iframe src="/maps/store-path.zh.html" title="写的路径：分步动画" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:760px;overflow:hidden;margin:2.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/store-path.zh.html" target="_blank" rel="noopener">在新窗口打开</a> · <a href="/images/ref/store-path.zh.svg" target="_blank" rel="noopener">静态全图</a></p>

### 1.3 四种乱序：x86 只允许 StoreLoad {#four-reorderings}

对两个不同地址的读写，别的核可能看到四种乱序：

| 乱序 | 含义 | x86 允许吗？ |
|---|---|---|
| StoreStore | 两个写被别人看到的顺序反了 | 不允许 |
| LoadLoad | 后面的读拿到的值比前面的读还旧 | 不允许 |
| LoadStore | 后面的写在前面的读完成之前就可见了 | 不允许 |
| StoreLoad | 后面的读在前面的写可见之前就执行了 | **允许** |

x86 的内存模型叫 TSO（Total Store Order）：前三种由硬件保证，普通的 `mov` 就带着这个顺序，不用加屏障。**唯一允许的 StoreLoad，就是 1.1 那段时间换了个名字**：写还在 store buffer 里，后面对另一个地址的读已经执行了。

经典的例子是两个线程各自“先写自己的标志，再读对方的标志”：

```cpp
// 开始时 x = y = 0
// 线程 1          // 线程 2
x = 1;             y = 1;
r1 = y;            r2 = x;
```

直觉上至少有一个线程能读到 1，可在 x86 上 `r1 == 0 && r2 == 0` 是可能的：两个写都还在各自的 store buffer 里，两个读已经读完了。**在 x86 上需要专门防的只有这一种乱序**，其他三种硬件已经禁止了。

### 1.4 先排除编译器：它也会重排 {#compiler}

怀疑 CPU 乱序之前，先看编译器有没有动过代码。这个循环看上去每一轮都在读内存：

```cpp
while (ready == false) {}
```

可是 `ready` 不是 `std::atomic` 也不是 `volatile`，编译器就可以认为这个线程之外没人会改它，只读一次，把循环改成：

```cpp
if (!ready) { while (true) {} }   // 死循环，再也不读内存
```

这和 CPU 的内存模型无关，是编译器的合法优化。`volatile` 能阻止它，强制每一轮都真的读一次，但也只能做到这一点：**`volatile` 不等于同步**，它不规定和别的内存操作之间的顺序，管不了 1.1 那段时间。修好这个循环要用 `std::atomic<bool>`，也就是下一节。

### 1.5 release / acquire：只在需要的地方补上顺序 {#release-acquire}

`std::atomic` 的读写可以带一个 `memory_order` 参数，说明这次操作要保证什么顺序：

| 内存序 | 保证什么 |
|---|---|
| `relaxed` | 只保证这一个变量的读写是原子的，不管和别的变量之间的顺序 |
| `release`（写） | 这次写之前的所有读写，都不能被挪到它后面 |
| `acquire`（读） | 这次读之后的所有读写，都不能被挪到它前面 |
| `acq_rel`（读改写） | 同时是 acquire 和 release |
| `seq_cst` | 在 acquire/release 之上，所有 `seq_cst` 操作还有一个全局一致的先后顺序；不写参数时的默认值 |
| `consume` | 已不推荐使用，编译器实际按 `acquire` 处理 |

最常用的是一对 release 和 acquire，用法像“发布、订阅”：**一个 acquire 读在同一个原子变量上读到了一个 release 写的值，写方在 release 之前写的所有东西，读方在 acquire 之后都看得到。** 别的变量不用是原子的：

```cpp
struct SPSCFlag {
  std::atomic<bool> ready{false};
  int payload = 0;   // 普通 int，不需要是原子的
};

// 生产者线程
void publish(SPSCFlag &f, int value) noexcept {
  f.payload = value;                                 // 1. 普通写
  f.ready.store(true, std::memory_order_release);    // 2. release：1 已经写完了
}

// 消费者线程
auto try_consume(SPSCFlag &f) noexcept -> std::optional<int> {
  if (f.ready.load(std::memory_order_acquire)) {     // 3. acquire：和 2 配对
    return f.payload;                                // 4. 保证看到第 1 步的值
  }
  return std::nullopt;
}
```

`payload` 能安全地传过去，靠的只是 `ready` 上这一对 release/acquire。交易系统里的单生产者单消费者（SPSC）环形队列都是这个形状：一个原子下标负责同步，其余都是普通变量。

回到 1.2 动画里的那个例子，给写 `ready` 加上 release、读 `ready` 加上 acquire，再走一遍：硬件还是那两个缓冲，**多出来的只有第 2 步和第 6 步这两个顺序约束**，一个管写方，一个管读方。

<iframe src="/maps/release-acquire.zh.html" title="release / acquire：分步动画" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:760px;overflow:hidden;margin:2.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/release-acquire.zh.html" target="_blank" rel="noopener">在新窗口打开</a></p>

### 1.6 价钱：x86 上几乎免费，ARM 上要专门的指令 {#cost}

同样的内存序，在不同 CPU 上编出来的指令不同：

| 操作 | x86-64 | ARMv8 |
|---|---|---|
| `acquire` 读 | 普通 `mov` | `ldar` |
| `release` 写 | 普通 `mov` | `stlr` |
| `seq_cst` 读 | 普通 `mov` | `ldar` |
| `seq_cst` 写 | `xchg`（或 `mov` 加 `mfence`） | `stlr` |
| `fetch_add` 这类读改写 | 带 `lock` 前缀的指令 | `ldadd` 一类原子指令，或 `ldaxr`/`stlxr` 循环 |

**x86 上 acquire 和 release 编出来就是普通的 `mov`**：它们要禁止的三种乱序，TSO 本来就禁止了。x86 上真正贵的是 `seq_cst` 的写和所有读改写操作，它们要把 store buffer 清空，等前面的写都可见了才能往下走，也就是要禁止 StoreLoad。这一笔大约 20–30 个周期，要等 store buffer 排空。所以 `std::atomic` 不写参数、用默认的 `seq_cst` 时，只需要发布、订阅的代码就多付了一笔。

ARM 的硬件四种乱序都可能做，所以 acquire/release 要用专门的 `ldar`、`stlr`（ARMv7 上是 `dmb` 屏障）。在 x86 上碰巧能跑的代码，比如用 `volatile` 代替 `atomic` 来传数据，到了 ARM 上就会读到旧值。C++ 内存模型按语义规定，而不是照搬 x86 的行为，就是为了让同一份代码在两种 CPU 上都对。

---

## 2. 伪共享：代码完全正确，照样慢 {#false-sharing}

**这一节的问题都可以出现在完全正确的代码上**：每次读都读到了对的值，内存序也都用对了，按第 1 节的标准没有任何 bug。它是纯粹的性能问题，加原子操作、加屏障都修不好。

### 2.1 一致性协议管的是 64 字节的缓存行，不是变量 {#cache-line-unit}

MESI 作废的单位是**缓存行**，x86 上一行是 64 字节。两个线程各写各的 `int`，两个 `int` 却恰好落在同一行里（比如结构体里相邻的两个字段），A 每写一次自己的变量，B 缓存里的整行就被作废；B 写自己的变量时，又要把这一行的独占权从 A 那里拿回来。这一行就在两个核之间来回搬，每次几十纳秒。这叫**伪共享**：两个变量在逻辑上毫无关系，“共享”只是内存布局造成的。

**例子：两个线程各加各的计数器。**

```cpp
struct Counters {
  std::atomic<uint64_t> a{0};   // 只有线程 1 写
  std::atomic<uint64_t> b{0};   // 只有线程 2 写；和 a 挨着，落在同一条缓存行里
};
Counters c;

// 线程 1，绑在核 0
for (int i = 0; i < 100'000'000; ++i)
  c.a.store(c.a.load(std::memory_order_relaxed) + 1, std::memory_order_relaxed);

// 线程 2，绑在核 1
for (int i = 0; i < 100'000'000; ++i)
  c.b.store(c.b.load(std::memory_order_relaxed) + 1, std::memory_order_relaxed);
```

这里用 `std::atomic` 加 `relaxed`，只是为了让编译器每一轮都真的读写内存（1.4），x86 上编出来是普通的 `mov`，没有 `lock` 前缀，也没有屏障。每个变量只有一个线程写，代码完全正确。慢在这一条缓存行的独占权上：

1. 核 0 读、写 `a`，要拿到这一行的独占权（M）。
2. 核 1 读、写 `b`，是同一行，于是发请求把整行要过去，核 0 那一份变成 I。
3. 核 0 下一轮读 `a`，本地已经没有这一行，只能等它从核 1 搬回来。

**本来是 L1 命中、1 ns 左右的一次自增，变成了一次几十纳秒的跨核搬运**，而且每一轮都可能来一次。把 `a`、`b` 分到两条缓存行上（2.3），同样的循环通常快几倍到十几倍。只跑一个线程时两种布局一样快，这也是伪共享难查的原因：单线程的测试测不出来，要多核同时写才冒出来，用 `perf c2c` 能看到具体是哪一行（{{% bottleneck-ref "false-sharing" "plain" %}}）。

### 2.2 伪共享和读到旧值是两回事 {#not-stale-read}

两者都涉及缓存行被作废，很容易混在一起：

| | 读到旧值（1.2） | 伪共享 |
|---|---|---|
| 属于哪类问题 | 正确性：读到的值对不对 | 性能：读到要花多少周期 |
| 表现 | 在一小段时间里读到一次旧值 | 每次写都要把这一行的独占权抢过来，一直持续 |
| 修法 | `memory_order`，release/acquire | 改布局，`alignas(64)` |
| 没有任何原子操作也会发生吗 | 不会，得有线程间真正共享的数据 | **会**，两个互不相干的普通 `int` 就够了 |

最后一行最能说明区别：两个计数器各自只被一个线程写，没有原子操作，也没有数据竞争，只要在同一行里照样来回搬。**一致性协议不知道变量之间有没有关系，它只知道两个核都要同一条 64 字节缓存行的独占权。**

### 2.3 修法：一个热变量独占一条缓存行 {#padding}

2.1 的例子，只要让两个字段各占一条缓存行：

```cpp
struct Counters {
  alignas(64) std::atomic<uint64_t> a{0};
  alignas(64) std::atomic<uint64_t> b{0};   // b 从下一条缓存行开始
};
```

每个线程一个计数器的数组也一样，给元素类型加 `alignas(64)`：

```cpp
struct alignas(64) PaddedCounter {
  std::atomic<uint64_t> value{0};
  // alignas(64) 让 sizeof 也补到 64，相邻元素不会落进同一行
};

PaddedCounter counters[num_threads];   // 每个计数器独占一整条缓存行
```

`alignas(64)` 也可以写成 `std::hardware_destructive_interference_size`。有些 Intel 核的预取器会把相邻的两条缓存行成对取进来，所以也有代码按 128 字节隔开。

**填充只能修伪共享，修不了真共享**：几个线程确实在改同一个计数器时，这一行本来就得来回搬，这是算法决定的。缓解办法是少碰这条共享的行：每个线程先在自己的副本上累积，攒够一批或者隔一段时间，再合并到共享变量上一次，用一点延迟换大幅减少的跨核流量。

### 2.4 另一个“共享”：L3 被别的进程挤占 {#l3-cat}

L1、L2 是每个核私有的，L3 是同一颗 CPU 上所有核共享的，这是设计如此，不会引起一致性协议的来回搬运。L3 上的问题是**容量**：别的核上一个无关的进程只要扫过足够多的数据，就能把你的工作集从 L3 里挤出去。Intel CAT（Cache Allocation Technology）解决这个问题：用 `pqos` 把 L3 按路分开，给你的进程留一块别人用不了的份额。

三个都和“共享”沾边的问题，修法各不相同，也互相替代不了：

| 问题 | 性质 | 修法 |
|---|---|---|
| 读到旧值 | 顺序 | `memory_order`（第 1 节） |
| 两个核抢同一条缓存行 | 布局 | `alignas(64)`（2.3） |
| L3 被无关进程挤占 | 容量 | Intel CAT |

---

### 2.5 真共享也会来回搬：ping-pong 的两种，和各自的修法 {#ping-pong}

一条缓存行在两个核之间来回搬，叫 ping-pong。2.1 的伪共享是其中一种，另一种是真共享：

- **伪共享**：两个核写的是两个不同的变量，碰巧落在同一条 64 字节的缓存行里。改布局就能消掉（2.3）。
- **真共享**：两个核写的就是同一个变量，比如一个全局计数器、一把锁、队列的下标。布局改不掉，只能少碰它。

**两种的代价一样**：每搬一次 20–100 ns，同核、同 socket 在低端，跨 socket 在高端；同一个核写自己 L1 里的行只要 1 ns 左右（[硬件地图](/zh/ref/cpu-memory/)）。所以吞吐掉几倍到几十倍，延迟也跟着抖。

**真共享的修法都是同一个思路：让每个核大多数时候只碰自己的行**

- **计数器每个线程各记一份**：读的时候再加起来，或者攒一批再合并一次（2.3 末尾，{{% bottleneck-ref "shared-counter" "plain" %}}）。
- **队列里缓存一份对方的下标**：SPSC 队列的生产者要知道消费者读到哪了，每次都去读对方的下标，那条行就来回搬；先读自己缓存的旧值，只有看起来满了才去读一次真的（[#4 无锁队列](/zh/posts/lock-free-queue-logger-micro-batching/)）。
- **自旋锁先读后抢**：等锁的核如果一直 CAS，每次 CAS 都要把行抢成独占，几个等待的核轮流抢；先只读，读到锁空了才 CAS，等待时这条行在几个核里都是 S（共享），不用搬（[#16 自旋锁](/zh/posts/spinlock-implementation/)，{{% bottleneck-ref "tas-spinlock" "plain" %}}）。

> **怎么确认是 ping-pong，是哪一种**
>
> - **用 `perf c2c`**：它统计 HITM，也就是“要读的行正被另一个核改着”的次数，按缓存行排序，并且列出行里被访问的偏移和访问它的函数。
> - **几个线程访问的偏移不同、落在同一条行**：伪共享，用 2.3 隔开。
> - **偏移相同**：真共享，用上面三种办法之一改设计。

## 应用 {#in-practice}

第 2 节的伪共享，在实际优化里对应“{{% bottleneck-ref "false-sharing" "plain" %}}”这张卡片：在 perf 里看到什么、怎么改、怎么验证。

{{% bottleneck "false-sharing" %}}
