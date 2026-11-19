---
title: "交易系统笔记 #2：内存序与缓存行"
date: 2026-09-15
lastmod: 2026-11-19
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

两个问题背后是同一套硬件：每个核私有的缓存、64 字节的缓存行、让各核缓存保持一致的协议（MESI）。可它们是两类问题。**第一个问的是正确性：读到的值对不对，答案非对即错；第二个问的是性能：值都读对了，花了多少个周期。** 前者用 C++ 内存模型（`std::atomic`、`memory_order`）解决，后者用缓存行布局解决，混在一起就会拿错工具。第 1 节讲乱从哪来，第 2 节按内存序讲怎么在需要的地方补上顺序，第 3 节讲伪共享，第 4 节是案例。单个核内部的依赖链，是“值都对、照样慢”的另一种情况，放在 [#9 循环优化](/zh/posts/loop-optimization/#dependency-chains) 第 3 节。

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

还可以更进一步：没有原子操作和 IO 的循环，标准允许编译器假设它一定会结束，GCC `-O2` 实测会把整个函数编成一条 `ret`，不等就直接返回（[未定义行为 2.3](/zh/ref/undefined-behavior/#data-race)）。

这和 CPU 的内存模型无关，是编译器的合法优化。`volatile` 能阻止它，强制每一轮都真的读一次，但也只能做到这一点：**`volatile` 不等于同步**，它不规定和别的内存操作之间的顺序，管不了 1.1 那段时间。修好这个循环要用 `std::atomic<bool>`，也就是下一节。

---

## 2. 内存序：在需要的地方不许乱 {#release-acquire}

第 1 节讲的是乱从哪来：写先进 store buffer，别的核晚一点才看见；作废请求先排队，读可能拿到旧值；编译器也会挪。`memory_order` 就是告诉编译器和 CPU：**这几处的先后不许乱**。下面按内存序一种一种讲，每种先说管什么，再说在 x86 和 ARM 上花多少钱。

### 2.1 六种内存序一览：管什么，编成什么 {#mo-kinds}

**内存序越强，管住的乱序越多；花不花钱，看硬件本来放开了哪几种乱序：x86 只放开“先写后读”，所以只有 seq_cst 的写和读改写要付钱；ARM 四种都放开，acquire、release 也要专门的指令**。

| 内存序 | 管什么 | x86-64 | ARMv8 |
|---|---|---|---|
| `relaxed`（2.2） | 只管这个变量自己：不撕裂，所有线程看到它被改的顺序一致；不管和别的变量谁先谁后 | 普通 `mov` | 普通 `ldr` / `str` |
| `release`（写，2.3） | 这次写前面的读写，不许挪到它后面 | 普通 `mov` | `stlr` |
| `acquire`（读，2.3） | 这次读后面的读写，不许挪到它前面 | 普通 `mov` | `ldar` |
| `acq_rel`（读改写，2.4） | 两样都有，用在 `fetch_add`、CAS 上 | 带 `lock` 前缀的指令，和 relaxed 的读改写是同一条 | `ldaddal` 这类带 a、l 后缀的指令 |
| `seq_cst`（2.5） | 在 acquire/release 之上，所有 seq_cst 操作排成一条所有线程都认同的时间线，“先写后读”也不许乱；不写参数时的默认值 | 读是普通 `mov`，写是 `xchg`（或 `mov` 加 `mfence`） | `ldar` / `stlr` |
| `consume` | 已不推荐，编译器按 `acquire` 处理 | 同 acquire | 同 acquire |

- **release 只管它前面的，acquire 只管它后面的**：一个线程里“release 写在前、acquire 读在后”这一对，两条都不管，2.5 就卡在这里。
- **x86 只放开“先写后读”（1.3）**：release/acquire 要的另外三种顺序，普通 `mov` 本来就带着。

> **最容易忘的一点：不写内存序就是 `seq_cst`，不是 `relaxed`**
>
> - **默认值是最强的那一档**：`x.store(v)`、`x.load()`、`x.fetch_add(1)` 不写内存序参数，都按 `seq_cst`。
> - **运算符写法也一样，而且没地方写内存序**：`x = v` 是 `store`，直接读 `x` 是 `load`，`++x`、`x += n` 是 `fetch_add`，全按 `seq_cst`。
> - **x86 上多花钱的是写**：不写参数的 `store` 编成 `xchg`，要等 store buffer 排空，约 20–30 个周期；写了 `relaxed` 就是普通 `mov`。
> - **x86 上读和读改写两种写法一样**：读都是普通 `mov`，读改写都是带 `lock` 的指令（GCC 14.2 `-O2` 编出来核对过）。
> - **ARM 上读和写都多花钱**：不写参数的读是 `ldar`、写是 `stlr`，`relaxed` 是普通的 `ldr`、`str`。
> - **忘写只会变慢，不会出错**：`seq_cst` 比哪一档都严，正确性不受影响；反过来，该用 `acquire`、`release` 的地方写成 `relaxed`，才会出错。
> - **普通变量不是“更松的 relaxed”**：几个线程读写同一个普通变量是数据竞争，属于未定义行为，编译器可以把循环里的读提到循环外（1.4）；`volatile` 也代替不了 `std::atomic`。
> - **所以热路径上的原子操作，每一个都显式写内存序**：运算符写法换成 `store`、`load`、`fetch_add`，用不到 `seq_cst` 就别让默认值替你选。

### 2.2 relaxed：只管这个变量自己 {#mo-relaxed}

**relaxed 只保证这一个变量：读写不撕裂，所有线程看到它被改的顺序一致，读改写不丢更新；它不管和别的变量谁先谁后，所以不能拿它发布别的数据**。

- **够用的地方：读到旧值也不会出错的数据**
  - **统计计数器**：几个线程 `fetch_add(1, relaxed)`，只要最后总数对。
  - **读自己的下标**：SPSC 队列里生产者读 `write_idx_`，只有它自己写，读到的一定是最新的（2.3.2）。
  - **只分号的 CAS**：[#18](/zh/posts/thread-safe-queue/) 2.1 rte_ring 抢 `prod_head_` 那一步，数据靠后面的 release/acquire 传。
- **不够的地方：拿它当“数据写好了”的标志**：生产者先写数据、再 relaxed 写标志，消费者 relaxed 读到了标志，照样可能读到没写完的数据。这时要 2.3 的 release/acquire。
- **价钱**：读写在 x86 和 ARM 上都是普通指令；读改写在 x86 上照样是 `lock` 指令，和 acq_rel 一样贵（2.4）。

### 2.3 release / acquire：配成对，别的线程才看得见 {#mo-ra}

**release 写和 acquire 读在同一个变量上配成对，也就是 acquire 读到的正是这次 release 写进去的值：写方在 release 之前做的事，读方在 acquire 之后都看得见；没配上，什么都不保证**。

#### 2.3.1 三句话：别的线程写的，看不看得到 {#mo-pubsub}

> 1. **同一个线程里，写在前面的先发生。** 只对本线程算数：别的线程什么时候看到，这句不管。
> 2. **B 用 acquire 读一个变量，读到的正好是 A 用 release 写进去的值，那么 A 在这次写之前做的事，B 在这次读之后都看得见。** 别的线程要用上 A 线程里的先后，只有这一个办法。
> 3. **除此之外，别的线程的写，你什么时候能看到，没人保证。**

**第 2 句要配上，两个条件都要满足**：一是同一个原子变量；二是 acquire 读到的正是这次 release 写进去的值。读到的是更早的旧值，就没配上。变量是原子的也不够，原子只保证不撕裂，它照样归第 3 句管。

最常见的用法是发布和订阅，别的变量不用是原子的：

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

`payload` 能安全地传过去，靠的是代码的形状：**先读标志，读到了才用数据，没读到就不用。** 读到了，第 2 句就生效；没读到，也不碰数据。

回到 1.2 动画里的那个例子，给写 `ready` 加上 release、读 `ready` 加上 acquire，再走一遍：硬件还是那两个缓冲，**多出来的只有第 2 步和第 6 步这两个顺序约束**，一个管写方，一个管读方。

<iframe src="/maps/release-acquire.zh.html" title="release / acquire：分步动画" loading="lazy" scrolling="no" style="display:block;width:min(100%,860px);height:760px;overflow:hidden;margin:2.2em auto 0;border:1px solid var(--rule);border-radius:12px;background:transparent"></iframe>
<p style="text-align:center;font-size:.9em"><a href="/maps/release-acquire.zh.html" target="_blank" rel="noopener">在新窗口打开</a></p>

#### 2.3.2 画成图分析代码 {#mo-edges}

两边的代码并排放：第 1 句画成竖边，第 2 句画成横边（配上了才画）。从对方的写出发，沿竖边、横边、竖边走得到，就看得见；走不到的，归第 3 句。

> **分析步骤：只问一句，读到旧值会不会出错**
>
> 1. **找出跨线程用的数据**，逐个问：读到旧值会不会出错？
> 2. **不会出错**：不用管，`relaxed` 就够。
> 3. **会出错**：代码必须是“读到标志才用数据”，这样用数据时横边一定在。
> - **两类错误一眼看得出**：横边只有一头，是少了 release 或者少了 acquire；要发布的写画在了 release 下面，或者要用的读画在了 acquire 上面，是位置放错了。
> - **原子变量自己被改的先后不算边**：另一个线程更早改过同一个原子变量，只说明这个变量的值是按这个顺序变的，不说明它写的别的内存我看得到。
> - **release 之后紧接着的 CAS、`fetch_add` 不会弄断横边**：它们接着前一个值写，算作那次 release 的延续；普通的 `store` 是盲写，会弄断（[内存池 5.5](/zh/posts/hot-path-memory-allocators/#pool-ordering) 有一个 4 步的例子）。

**SPSC 环形队列**：

```cpp
template <class T, std::size_t N>   // N 是 2 的幂
class SpscQueue {
    std::array<T, N> buf_;
    alignas(64) std::atomic<std::size_t> read_idx_{0};    // 只有消费者写
    alignas(64) std::atomic<std::size_t> write_idx_{0};   // 只有生产者写
public:
    bool push(const T& x) {                                          // 生产者
        std::size_t w = write_idx_.load(std::memory_order_relaxed);  // 自己的下标
        if (w - read_idx_.load(std::memory_order_acquire) == N)      // 读到有空位才往下
            return false;
        buf_[w & (N - 1)] = x;                                       // 写格子
        write_idx_.store(w + 1, std::memory_order_release);          // 发布
        return true;
    }
    bool pop(T& out) {                                               // 消费者
        std::size_t r = read_idx_.load(std::memory_order_relaxed);   // 自己的下标
        if (r == write_idx_.load(std::memory_order_acquire))         // 读到有数据才往下
            return false;
        out = buf_[r & (N - 1)];                                     // 读格子
        read_idx_.store(r + 1, std::memory_order_release);           // 归还
        return true;
    }
};
```

- **下标读到旧值不会出错**：只会以为空了或满了，多等一轮。
- **格子读到旧值会出错**，两处都是“读到了才用”：
  - 消费者读到 `write_idx_` 比自己的位置大，才去读格子：写格子 →竖→ release 写 `write_idx_` →横→ acquire 读到它 →竖→ 读格子。
  - 生产者读到 `read_idx_` 说明有空位，才去覆盖格子：读格子 →竖→ release 写 `read_idx_` →横→ acquire 读到它 →竖→ 覆盖格子。
- **改错一处就断一条边**：`write_idx_` 的 release 改成 relaxed，消费者可能读到没写完的格子；`read_idx_` 这一对改成 relaxed，生产者可能覆盖没读完的格子。

再看一个带 CAS 的例子，[内存池 5.4](/zh/posts/hot-path-memory-allocators/#tagged-head) 的 `deallocate` 和 `allocate` 画出来是这样：

<img src="/images/memory-ordering/edges.zh.svg" alt="左边是线程 A 的 deallocate，右边是线程 B 的 allocate。蓝色横边从 deallocate 里 CAS 成功时的 release 出发，一条连到 allocate 开头的 head_.load(acquire)，一条连到 allocate 里 CAS 失败时的 acquire。灰色竖边在每个线程内部从上到下：A 这边 release 上面有两处写，析构时写的槽里的字节和 next；B 这边 acquire 下面读 next，再在同一段字节上构造对象。A 的 head_.load(relaxed) 和 CAS 失败的 relaxed 没有边通到，读回来的 old 只当一个数用。" loading="lazy" decoding="async">

#### 2.3.3 价钱：x86 上就是普通 mov，ARM 上要 ldar / stlr {#cost}

**x86 上 acquire 和 release 编出来就是普通 `mov`，因为它们要的顺序 x86 本来就给；ARM 四种乱序都可能做，要用专门的 `ldar`、`stlr`**。

- **x86 不用付钱的原因**：store buffer 先进先出，只让写晚一点被看见，不会把写排乱；读和读之间，被改了就作废重做，也不乱。release/acquire 要的正好是这两种顺序；写晚一点被看见没关系，反正读到了才用。
- **ARM 要付钱的原因**：store buffer 不保证先进先出，后面的读也可以先执行，所以要用 `ldar`、`stlr`（ARMv7 上是 `dmb` 屏障）。
- **x86 上碰巧能跑的代码，到 ARM 上会读到旧值**：比如用 `volatile` 代替 `atomic` 来传数据。C++ 内存模型按语义规定，不照搬 x86 的行为，就是为了让同一份代码在两种 CPU 上都对。

### 2.4 acq_rel：读改写一条边进、一条边出 {#mo-acq-rel}

**acq_rel 只用在读改写上，一次操作同时是 acquire 和 release：读的那一半接住之前改这个变量的线程交来的边，写的那一半把自己之前做的交给之后的线程**。

引用计数：每个线程用完对象减一，减到 0 的那个删对象。

<img src="/images/memory-ordering/acq-rel.zh.svg" alt="引用计数从 3 开始，三个线程各自先用对象（U1、U2、U3），再 fetch_sub(1, acq_rel)（F1、F2、F3）。这一次执行里依次减：F1 读到 3 写 2，F2 读到 2 写 1，F3 读到 1 写 0，T3 删对象。蓝色横边从 F1 到 F2、从 F2 到 F3。F2 一条边进、一条边出：acquire 一半接住 F1 的边，release 一半把 U1、U2 一起交给 F3。U1、U2、U3 都沿边走得到 delete。" loading="lazy" decoding="async">

- **每次减都要两半**：谁最后减到 0，事先不知道。不是最后一个时，release 把自己用过的交出去；是最后一个时，acquire 接住别人用过的。
- **价钱：x86 上和 relaxed 一样贵，钱花在读改写本身**：x86 的读改写只能用带 `lock` 的指令，`lock` 本身就是一道全屏障，约 20 个周期。同一个 `fetch_add`，写 relaxed 和写 acq_rel 编出来是同一条 `lock xadd`；在 x86 上换成 relaxed 省不下钱，只是丢了顺序保证。要省，得少做读改写，比如每个线程各记一份计数（[4.3](#case-counter)）。
- **ARM 上内存序才真有区别**：`ldadd`（relaxed）、`ldadda`（acquire）、`ldaddl`（release）、`ldaddal`（acq_rel），或者 `ldxr`/`stxr` 循环加 a、l 后缀。

### 2.5 seq_cst：所有线程认同同一条时间线，先写后读也不乱 {#mo-seq-cst}

**seq_cst 是唯一替全体线程排顺序的内存序：所有 seq_cst 操作排成一条所有线程都认同的时间线，每个线程自己的代码顺序在这条线上原样保留；release/acquire 只给在同一个变量上配成对的两个线程排先后**。

两个线程各自先写自己的变量、再读对方的变量，要的是**至少一边读到 1**：

<img src="/images/memory-ordering/seq-cst.zh.svg" alt="两个线程各自先写、再读对方，初始 x = y = 0。左栏 release/acquire：竖边 ① 到 ② 只对线程 1 算数，线程 2 要看到 ① 得沿边走到 ④，走到 ② 就断了，② 是读，发不出横边；硬件上 ①、③ 还在 store buffer 里，②、④ 先读完了，两边都读到 0 是可能的。右栏 seq_cst：线程里的先后对所有线程都成立，① 先于 ②、③ 先于 ④，交错只有 6 种，列出每种的 r1、r2，没有一种是两个 0。" loading="lazy" decoding="async">

- **竖边在，为什么不管用**：① → ② 只对线程 1 算数（第 1 句）。线程 2 要看到 ①，得从 ① 沿边走到 ④，走到 ② 就断了：② 是读，读发不出横边。硬件上就是 ①、③ 还在各自的 store buffer 里，②、④ 已经读完了（[4.1](#case-x86)）。
- **seq_cst 让线程里的先后对所有线程都成立**：① 一定先于 ② 生效，③ 一定先于 ④。四个操作交错只有 6 种排法，排第一的都是写，另一边的读在它后面，读到 1，所以没有一种是两个 0。
- **价钱：x86 上只有写要付钱**：seq_cst 的写编成 `xchg`，要等 store buffer 排空、这次写对所有核都可见了才往下走，约 20–30 个周期；seq_cst 的读还是普通 `mov`。`std::atomic` 不写参数默认就是 seq_cst，只需要发布、订阅的代码就多付了这一笔。
- **ARMv8 上不另外付钱**：它规定 `stlr` 后面的 `ldar` 不许越过它，“先写后读”也管住了，所以 seq_cst 用的也是这一对。
- **发布订阅用不着它**：它本来就是“读到了才用”，release/acquire 就够了。

---

## 3. 伪共享：代码完全正确，照样慢 {#false-sharing}

**这一节的问题都可以出现在完全正确的代码上**：每次读都读到了对的值，内存序也都用对了，按第 1、2 节的标准没有任何 bug。它是纯粹的性能问题，加原子操作、加屏障都修不好。

### 3.1 一致性协议管的是 64 字节的缓存行，不是变量 {#cache-line-unit}

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

**本来是 L1 命中、1 ns 左右的一次自增，变成了一次几十纳秒的跨核搬运**，而且每一轮都可能来一次。把 `a`、`b` 分到两条缓存行上（3.3），同样的循环通常快几倍到十几倍。只跑一个线程时两种布局一样快，这也是伪共享难查的原因：单线程的测试测不出来，要多核同时写才冒出来，用 `perf c2c` 能看到具体是哪一行（{{% bottleneck-ref "false-sharing" "plain" %}}）。

### 3.2 伪共享和读到旧值是两回事 {#not-stale-read}

两者都涉及缓存行被作废，很容易混在一起：

| | 读到旧值（1.2） | 伪共享 |
|---|---|---|
| 属于哪类问题 | 正确性：读到的值对不对 | 性能：读到要花多少周期 |
| 表现 | 在一小段时间里读到一次旧值 | 每次写都要把这一行的独占权抢过来，一直持续 |
| 修法 | `memory_order`，release/acquire | 改布局，`alignas(64)` |
| 没有任何原子操作也会发生吗 | 不会，得有线程间真正共享的数据 | **会**，两个互不相干的普通 `int` 就够了 |

最后一行最能说明区别：两个计数器各自只被一个线程写，没有原子操作，也没有数据竞争，只要在同一行里照样来回搬。**一致性协议不知道变量之间有没有关系，它只知道两个核都要同一条 64 字节缓存行的独占权。**

### 3.3 修法：一个热变量独占一条缓存行 {#padding}

3.1 的例子，只要让两个字段各占一条缓存行：

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

### 3.4 另一个“共享”：L3 被别的进程挤占 {#l3-cat}

L1、L2 是每个核私有的，L3 是同一颗 CPU 上所有核共享的，这是设计如此，不会引起一致性协议的来回搬运。L3 上的问题是**容量**：别的核上一个无关的进程只要扫过足够多的数据，就能把你的工作集从 L3 里挤出去。Intel CAT（Cache Allocation Technology）解决这个问题：用 `pqos` 把 L3 按路分开，给你的进程留一块别人用不了的份额。

三个都和“共享”沾边的问题，修法各不相同，也互相替代不了：

| 问题 | 性质 | 修法 |
|---|---|---|
| 读到旧值 | 顺序 | `memory_order`（第 2 节） |
| 两个核抢同一条缓存行 | 布局 | `alignas(64)`（3.3） |
| L3 被无关进程挤占 | 容量 | Intel CAT |

---

## 4. 案例：x86 上的内存序和 ping-pong {#case}

### 4.1 x86 上的内存序：只有“先写后读”会乱，写还停在 store buffer 里 {#case-x86}

**乱序说的是别的核看到的生效顺序和代码顺序不一样**。一次读，拿到值就生效；一次写，要离开 store buffer、写进 L1 才对别的核生效。**store buffer 只把写的生效往后推，不推读**，所以相邻两次访存里，只有“写在前、读在后”会被推反：

| 代码顺序 | 会不会反 | 为什么 |
|---|---|---|
| 写 A → 写 B | 不会 | store buffer 先进先出，A 先进 L1 |
| 读 A → 读 B | 不会 | 读可以提前执行，但读过、还没退休的行如果被别的核改了，这次读和它后面的指令作废重做 |
| 读 A → 写 B | 不会 | 写要等指令按顺序退休才离开 store buffer，那时读 A 早已拿到值 |
| **写 A → 读 B** | **会** | 写 A 还在 store buffer 里，读 B 已经从 L1 拿到了值 |

这套规则叫 TSO：所有核看到的写是同一个顺序，只有本核能从自己的 store buffer 提前读到自己的写。两个线程各自先写、再读对方，就会撞上第 4 行：

```text
// 初始 x = 0, y = 0
// 线程 1                  // 线程 2
x = 1;   (写 x)            y = 1;   (写 y)
r1 = y;  (读 y)            r2 = x;  (读 x)
```

1. **两个写各自进了自己核的 store buffer**：L1 里 x、y 还都是 0。
2. **两个读都从 L1 拿值**：读到的都是 0，读已经生效。
3. **两个写这时才进 L1**：太晚了，对方已经读完。

结果是 `r1 == 0` 并且 `r2 == 0`，好像两边的读都跑到了写前面。用 C++ 原子变量写出来是这样：

```cpp
std::atomic<int> x{0}, y{0};
int r1 = -1, r2 = -1;

// 线程 1：先写 x，再读 y
void t1() {
    x.store(1, std::memory_order_release);
    r1 = y.load(std::memory_order_acquire);
}
// 线程 2：先写 y，再读 x
void t2() {
    y.store(1, std::memory_order_release);
    r2 = x.load(std::memory_order_acquire);
}
// 可能出现 r1 == 0 并且 r2 == 0：两边的写都还停在各自的 store buffer 里，对方读不到
// 四个操作都换成 seq_cst，才保证至少有一边读到 1
```

**为什么 release 加 acquire 管不住它**：它们在 x86 上都是普通的 `mov`，TSO 本来就保证了它们要的那三种顺序，唯独不管“先写后读”。换成 `seq_cst` 以后，读还是 `mov`，写编成 `xchg`：它要等 store buffer 排空，写真正可见了才往下走，后面的读就越不过去。

2.5 有一张对照图：release/acquire 下两边都可能读到 0，`seq_cst` 下不可能。

每种内存序在 x86 上编成什么：

| 操作 | x86 上的指令 | 代价 |
|---|---|---|
| 读，不论哪种内存序 | `mov` | 和普通的读一样 |
| `relaxed`、`release` 的写 | `mov` | 和普通的写一样 |
| `seq_cst` 的写 | `xchg`（自带 `lock`），或者 `mov` 加 `mfence` | 约 20–30 个周期：要等 store buffer 排空 |
| `fetch_add`、CAS 这类读改写 | 带 `lock` 前缀的指令 | 约 20 个周期：本身就是一道全屏障 |

- **`acquire` 和 `release` 在 x86 的硬件上不花钱，但不能省**：它们还约束着编译器（1.4）。写成 `relaxed`，编译器可以把两次访问调换位置；在 x86 上也许碰巧能跑，换到 ARM 就会出错，ARM 的硬件四种乱序都会做，屏障是真的指令（2.3.3）。
- **只有 `seq_cst` 管得住“先写后读”**：两个线程各自先写自己的标志、再读对方的，就是要它的典型形状。

### 4.2 ping-pong：要写一条缓存行必须先独占它，两个核轮流写就来回搬 {#ping-pong}

- **写之前要独占**：一个核要写一条行，先发 RFO 或 invalidate 请求，别的核手里的副本作废，这条行在本核变成 M（已修改）。
- **另一个核再写，行又被要回去**：对方把行交出来，自己这份作废。两个核轮流写，这条行就在两个核的缓存之间来回搬。
- **每搬一次 20–100 ns**：同 socket 的两个核在低端，跨 socket 在高端；同一个核写自己 L1 里的行只要 1 ns 左右（[硬件地图](/zh/ref/cpu-memory/)）。所以吞吐掉几倍到几十倍，延迟也跟着抖。

**ping-pong 分两种**：

- **伪共享**：两个核写的是两个不同的变量，碰巧落在同一条 64 字节的缓存行里。改布局就能消掉（3.3）。
- **真共享**：两个核写的就是同一个变量。布局改不掉，只能少碰它。

交易系统里真共享最常见的是下面三处：一个全局计数器、队列两端的下标、一把自旋锁。三处的修法是同一个思路：**让每个核大多数时候只碰自己的行，只在必要时碰一次共享的那条**。

### 4.3 全局计数器：几个线程都加同一个变量，改成每个线程各记一份 {#case-counter}

几个线程处理订单，每处理一笔就给全局计数加 1：

```cpp
// 1. 改之前：所有线程加同一个原子变量
std::atomic<uint64_t> total{0};
void on_order() {
    total.fetch_add(1, std::memory_order_relaxed);
}
```

**每次 `fetch_add` 都要先把这条行抢成独占**：几个线程轮流抢，这条行就一直在核之间搬。`relaxed` 帮不上忙，它只放松了顺序，没有减少对这条行的独占。

```cpp
// 2. 改之后：每个线程一份，各占一条缓存行
struct alignas(64) PaddedCounter {
    std::atomic<uint64_t> v{0};
};
PaddedCounter per_thread[kMaxThreads];

void on_order(int tid) {
    // 3. 只有自己写这一份，用读加写代替 fetch_add，没有 lock 前缀
    auto& c = per_thread[tid].v;
    c.store(c.load(std::memory_order_relaxed) + 1, std::memory_order_relaxed);
}

// 4. 读的时候把每一份加起来
uint64_t read_total() {
    uint64_t sum = 0;
    for (auto& c : per_thread) sum += c.v.load(std::memory_order_relaxed);
    return sum;
}
```

**拆成每个线程一份只消掉了真共享，`alignas(64)` 再挡住伪共享**：拆开以后每份只有一个线程写，没有哪个变量是两个核都在写的了。但一份只有 8 字节，不补齐的话 8 个线程的计数会挤进同一条 64 字节的缓存行，各写各的变量，抢的还是同一条行，这就成了伪共享（3.3）。所以每份都对齐到 64 字节，单独占一条行。

**开销没有消失，而是从写的一侧挪到了读的一侧和内存上**：

| | 改之前：一个全局变量 | 改之后：每个线程一份 | 代价去了哪 |
|---|---|---|---|
| 写一次 | 20–100 ns：要从别的核把行抢成独占 | 1 ns 左右：写自己 L1 里的行 | 写的一侧几乎不花钱了 |
| 读一次 | 一次读 | 读 $N$ 条缓存行再加起来，$N$ 是线程数；每条都可能刚被别的核写过，要跨核取 | 挪到读的一侧 |
| 占多少内存 | 8 字节 | $N \times 64$ 字节：每份单独占一条缓存行 | 挪到内存上 |
| 读到的值准不准 | 读到的是某一时刻真实存在过的总数 | 几份是先后读的，读的过程中别的线程还在加，加出来的不是同一时刻的快照；只保证落在开始读和读完时的真实总数之间 | 挪到准确度上 |

**计数器通常写得多、读得少，读的一方也不要求精确到同一时刻**：监控每秒读一次，订单线程每笔都写，所以这样挪划算（{{% bottleneck-ref "shared-counter" "plain" %}}）。

### 4.4 SPSC 队列的下标：每次都读对方的下标，改成缓存一份 {#case-spsc}

单生产者单消费者的环形队列，生产者要知道队列满没满，就得读消费者的下标 `read_idx_`；消费者每取一个都会写它。生产者每次 `push` 都读一次，这条行就在两个核之间来回搬。

```cpp
bool push(const T& x) {
    size_t w = write_idx_.load(std::memory_order_relaxed);   // 自己的下标，只有自己写
    // 1. 先用缓存的旧值判断满没满，不碰对方那条行
    if (w - cached_read_idx_ == N) {
        // 2. 看起来满了，才去读一次真的，顺便更新缓存
        cached_read_idx_ = read_idx_.load(std::memory_order_acquire);
        if (w - cached_read_idx_ == N) return false;
    }
    buf_[w & (N - 1)] = x;
    write_idx_.store(w + 1, std::memory_order_release);
    return true;
}
```

**缓存的旧值只会往安全的方向错**：消费者只会往前读，真实的 `read_idx_` 只会比缓存的大。拿旧值算出来的空位只会偏少，最多是“以为满了”去多读一次，不会“以为有空位”写坏还没被读走的数据。队列不满的时候，生产者完全不碰消费者那条行（[#4 无锁队列 2.1](/zh/posts/lock-free-queue-logger-micro-batching/#cached-index)）。

### 4.5 自旋锁：等锁时一直交换，改成先读后抢 {#case-spinlock}

```cpp
void lock() {
    for (;;) {
        // 1. 抢：exchange 是一次写，要先把行抢成独占
        if (!locked_.exchange(true, std::memory_order_acquire)) return;
        // 2. 没抢到就只读，等它变成 false
        while (locked_.load(std::memory_order_relaxed)) _mm_pause();
    }
}
```

**只写第 1 步、在循环里一直 `exchange`**：每个等锁的核每一圈都要把行抢成独占，几个等待的核轮流抢，持锁的核解锁时还得从它们手里把行要回来。

**加上第 2 步**：等待的核只读，这条行可以同时在几个核里处于 S（共享）状态，不用搬。持锁的核解锁时写一次，作废所有副本；等待的核读到 `false`，才回到第 1 步去抢一次（[#16 自旋锁](/zh/posts/spinlock-implementation/)，{{% bottleneck-ref "tas-spinlock" "plain" %}}）。

### 4.6 怎么确认是 ping-pong、是哪一种：`perf c2c` 找到那条行，再看偏移 {#case-c2c}

`perf c2c`（cache to cache）专门找在核之间来回搬的缓存行。用起来是 3 步：采样，找到搬得最多的那条行，看这条行里被访问的是哪几个偏移。

**第 1 步，采样**：

```bash
# 1. 编译时带 -g，报告里才能对到源码行
g++ -O2 -g -pthread prog.cpp -o prog

# 2. 采样：从头跑一个程序，或者对整台机器的用户态采 10 秒
perf c2c record -- ./prog
perf c2c record -a --all-user sleep 10

# 3. 出文本报告
perf c2c report --stdio > c2c.txt
```

- **`record` 采的是一次次内存读写，不是函数耗时**：每个样本记下读写的数据地址、是哪条指令、在哪个 CPU 上，还有这次读的数据是从哪里拿到的：自己的 L1、L3，还是别的核。
- **HITM（hit modified）是“从别的核拿到”的那一种**：读的时候，这条行在另一个核里是 M（已修改），得从那个核搬过来。它就是 4.2 里 ping-pong 的一次搬运。Local HITM 是从同 socket 的另一个核搬，Remote HITM 是从另一个 socket 搬，后者更贵。
- **要 CPU 的精确采样支持**：Intel 上是 PEBS，AMD 上是 IBS。多数虚拟机里拿不到，要在物理机上跑（[perf 专题 3.3](/zh/posts/low-latency-perf-profiling/#c2c)）。

**第 2 步，在 Shared Data Cache Line Table 里找搬得最多的行**：这张表一行是一条缓存行，按 HITM 从多到少排。列名随 perf 版本略有不同，要看的是这几列：

| 列 | 含义 | 怎么用 |
|---|---|---|
| Cacheline | 这条缓存行的起始地址 | 拿它到下一张表里找这条行的明细 |
| Tot Hitm | 这条行的 HITM 占全部 HITM 的比例 | 先看占 5% 以上的行，它们就是在来回搬的行 |
| LclHitm、RmtHitm | 同 socket、跨 socket 各搬了多少次 | 单路机器上只有 LclHitm；RmtHitm 多说明线程分在了两个 socket 上 |
| Store Reference | 这条行被写了多少次 | 有 HITM 就一定有核在写它，这一列确认写得有多频繁 |

**第 3 步，在 Shared Cache Line Distribution Pareto 里看偏移**：这张表把每条热的缓存行展开，一行是“行内某个偏移上的某条指令”。偏移从这条行的起始地址算起，范围是 0x0–0x3f。下面两张是删减后的样子，只留了判断要用的列，数字只表示形状。

伪共享：两个线程各写各的变量，两个变量差 8 字节，落在同一条行里（3.1 的 `a` 和 `b`）。

| 行内偏移 | HITM 占比 | 写的占比 | CPU 数 | 函数 | 源码行 |
|---|---|---|---|---|---|
| 0x0 | 52% | 49% | 1 | `worker_a` | prog.cpp:12 |
| 0x8 | 48% | 51% | 1 | `worker_b` | prog.cpp:19 |

真共享：4.3 里 4 个线程加同一个 `total`。

| 行内偏移 | HITM 占比 | 写的占比 | CPU 数 | 函数 | 源码行 |
|---|---|---|---|---|---|
| 0x0 | 100% | 100% | 4 | `on_order` | prog.cpp:5 |

> **看偏移和 CPU 数，分出是哪一种**
>
> - **同一条行里有几个不同的偏移，每个偏移各由一个 CPU 访问**：伪共享。几个线程碰的是不同的变量，用 3.3 把它们隔到不同的行。
> - **只有一个偏移，CPU 数大于 1**：真共享。几个线程碰的就是同一个变量，按 4.3–4.5 的办法改设计。
> - **偏移对应哪个变量**：源码行直接指到访问它的那句代码；是结构体的字段，用 `pahole` 打出结构体布局，按偏移对到字段。
> - **只写不读的线程 HITM 是 0**：HITM 只记在读的样本上。找这样的线程要看“写的占比”那一列。
> - **改完重新采一次**：这条行从表里消失，或者 Tot Hitm 掉到 1% 以下，才算修对了。

## 应用 {#in-practice}

第 3 节的伪共享，在实际优化里对应“{{% bottleneck-ref "false-sharing" "plain" %}}”这张卡片：在 perf 里看到什么、怎么改、怎么验证。

{{% bottleneck "false-sharing" %}}
