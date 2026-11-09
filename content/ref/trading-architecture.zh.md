---
title: "交易系统架构：地图、时间、怎么切"
description: "一条行情从网卡进来，到变成一笔报单、拿回成交，经过哪些线程和数据结构；每一段大概多久；工业级系统怎么分线程、在哪里放队列、哪里必须汇合；回测和实盘的因子怎么逐值对上；实盘和回测差在哪、上线前怎么验、盘中出事怎么办；AMD 和 Intel 差在哪；订单簿怎么用逐笔合成、怎么验；批量回算怎么算得快。"
date: 2026-10-20
lastmod: 2026-11-09
slug: "trading-architecture"
weight: 15
toc: true
math: true
---

这页是随时翻的架构总图，和[硬件地图](/zh/ref/cpu-memory/)是一对：那页讲一次访存经过哪些硬件，这页讲一条行情经过哪些线程。前三部分按“在哪 → 多快 → 怎么切”排，后面五部分各讲一件事：

1. [架构地图](#map)：一条行情变成一笔成交，经过哪些框，每个框在哪篇文章里讲过。
2. [时间](#numbers)：每一段大概多久，用来判断该抠哪一段。都是量级，不对应哪套系统。
3. [怎么切](#rules)：工业级系统怎么分线程、在哪里放队列、哪里必须汇合。
4. [因子一致性](#factors)：从同一份代码到每天对账，让回测和实盘的因子逐值相同，策略上了实盘不会因为因子算错而失效。
5. [实盘](#live)：实盘和回测差在哪，上线前怎么验，盘中出事怎么办。
6. [AMD 和 Intel](#ccx)：差在核分组，绑核要按组排；内存序一样。
7. [订单簿](#book)：用逐笔合成每只股票的订单簿，因子按需读前几档或直接读逐笔；价格档用数组、委托号用哈希表，和快照逐档比。
8. [批量回算](#batch)：几年的历史数据比缓存大几个数量级，因子回算怎么算得快：每份数据只搬一次、中间结果分层、按交易日切。

后面讲到新的组件，都补在这一页。

## 1. 架构地图：一条行情经过哪些框 {#map}

<a href="/maps/arch-map.zh.html" target="_blank" rel="noopener"><img src="/images/ref/arch-map.zh.svg" alt="交易系统架构地图：交易所的行情经网卡进行情接入线程，先写一份进广播环给落盘和监控，再按股票分到各分片线程算盘口和因子，汇合后进决策线程的策略、风控、订单管理和下单网关，经券商柜台到交易所；回报沿红线回到订单管理和账户状态，再回到策略。最下面一排是旁路：离线回放、落盘、监控、日志、交易员指令和客户端推送。" loading="lazy" decoding="async"></a>

绿框是热线程，各绑一个隔离核；蓝框是线程之间交接数据的结构；黄框是汇合点；最下面一排虚线框是旁路。黑线是行情到报单，红线是回报回来，灰色虚线是旁路。点图打开可交互的版本：点一个框看它做什么、为什么这样设计；选一条路径，一步一步看怎么走。

### 1.1 一条行情的路：行情 → 报单 {#tick}

1. 交易所把行情按通道组播出来，网卡收到包。
2. 行情接入线程解码，按通道查序号，断档了就去补。
3. 它先把这条写进广播环，给落盘、监控这些不赶时间的读者，写完就走（[#5](/zh/posts/spmc-shared-memory-broadcast-ring/)）。
4. 再按股票查表，写进负责这只股票的分片队列（[#4](/zh/posts/lock-free-queue-logger-micro-batching/)）。同一只股票永远进同一片，顺序不会乱。
5. 分片线程更新这只股票的盘口，再增量更新它的因子，只碰自己那些股票的状态。
6. 按 bar 截面的策略，要等所有分片算完这根 bar，再一起排名、打分。
7. 决策线程里，策略定买什么、卖什么、撤哪些，过事前风控，交给订单管理；大单拆成小单按时间发。
8. 下单网关编码成协议发出去，经券商柜台到交易所。

回测时，第 1–4 步换成回放器：按交易日读历史行情，按时间顺序一条条喂给同一个 `on_tick`，第 5 步往后的因子代码不变（[4.1](#replay)）。

### 1.2 一笔回报的路：成交 → 持仓 → 策略 {#fill}

1. 交易所撮合以后发出回报：确认、成交、撤单都算。回报经柜台回到下单网关。
2. 订单管理更新这笔单子的状态：部分成交、全部成交、已撤。
3. 账户状态跟着变：持仓、资金、在途单。它只让决策线程一个人改。
4. 下一次决策用的就是新的持仓和资金，回路闭合；推送把变化送到交易员的屏幕上。

### 1.3 两种节奏：按 bar 截面，还是逐笔触发 {#clocks}

按 bar 截面（多因子选股）：所有股票算完一根 bar 再一起打分，节奏是毫秒到秒。几十纳秒的交接看不出来，要盯的是一波数据进来以后，多久全部算完。

逐笔触发（做市、套利）：一条行情就可能触发一笔报单。分片线程里一路算信号、过风控、发单，不过汇合、不过队列，全程在微秒级；每多一次跨核交接，就多几十纳秒和一份抖动。

### 1.4 旁路：慢了也不能拖住热路径 {#side}

落盘、日志、监控、客户端推送都在旁路上：热线程只往环或队列里写一条就走，慢活交给别的线程或进程。旁路可以隔一会读一批，但要算好容量，别被套圈。交易员的指令（启停、撤单、改参数）方向相反，经服务进程走队列送进决策线程。

### 1.5 文章索引：每个框在哪篇讲过 {#posts}

| 框 | 文章 |
|---|---|
| 热线程绑核、网卡中断别打到热核 | [#1 CPU 隔离与 NUMA](/zh/posts/cpu-affinity-core-isolation-numa/) |
| AMD 和 Intel 差在哪：核分组、绑核、内存序 | 本页 [第 6 部分](#ccx) |
| 分片线程里的盘口：订单簿怎么合成、用什么数据结构、怎么验 | 本页[第 7 部分](#book) · [IV：A 股业务知识 8](/zh/interview/a-share-business/#8-订单簿重建用逐笔推出每一刻的盘口) |
| 实盘和回测差在哪、上线前怎么验、盘中出事怎么办 | 本页[第 5 部分](#live) |
| 批量回算：带宽受限、每份数据只搬一次、中间结果分层、按交易日切 | 本页[第 8 部分](#batch) |
| 跨核交接为什么要几十纳秒、伪共享 | [#2 内存序与缓存行](/zh/posts/memory-ordering-false-sharing-dependency-chains/) · [MESI 专题](/zh/posts/low-latency-mesi-cache-coherence/) · [速查 2.6](/zh/ref/cpu-memory/#cross-core) |
| 热路径不现分配内存（订单、消息对象） | [#3 内存池与分配器](/zh/posts/hot-path-memory-allocators/) |
| 分片队列（SPSC）、异步日志 | [#4 无锁队列与 Micro-Batching](/zh/posts/lock-free-queue-logger-micro-batching/) |
| 广播环、落盘读者被套圈、重启续读、什么时候不用广播环 | [#5 SPMC 广播环](/zh/posts/spmc-shared-memory-broadcast-ring/) |
| 几个线程的订单汇到一个网关（多生产者队列）、旁路的阻塞队列、队列满了阻塞还是丢 | [#18 线程安全队列](/zh/posts/thread-safe-queue/) |
| 分片线程里一条行情的计算 | [缓存案例：一次行情重算 64 个期权](/zh/posts/low-latency-cache-case-study/) |
| 开盘前预热、账户快照的双缓冲 | [#14 预取、预热与双缓冲](/zh/posts/prefetch-warmup-double-buffer/) |
| 汇合、策略、风控、订单管理、下单网关 | 本页第 3 部分；以后的文章再补 |

## 2. 时间：每一段大概多久 {#numbers}

这里的数都是帮助理解的量级，不对应哪套系统。标了“本站测过”的出自对应文章，其余是常见量级。

| 一段 | 大约多久 | 说明 |
|---|---|---|
| 交易所 → 本机网卡 | 托管机房直连：几 µs；经行情供应商转发：几 ms | 看离交易所多远、中间转几手 |
| 网卡 → 程序拿到包 | 绕过内核：约 1 µs；走内核协议栈：约 5–10 µs | 内核协议栈要过中断、拷贝、系统调用 |
| 解码一条行情 | 约 0.1–1 µs | 看格式 |
| 跨核交接一次（队列、环） | 约 20–100 ns | 一条缓存行从一个核搬到另一个核（[速查 2.1](/zh/ref/cpu-memory/#latency)） |
| 往广播环写一条 | 约 3–40 ns | 本站测过：全速写时，守在最新槽位上的读者越多越贵（[#5 1.6](/zh/posts/spmc-shared-memory-broadcast-ring/#16-硬件上读者会不会拖慢生产者)） |
| 一条行情更新盘口和因子 | 几百 ns 到几 µs | 看因子多少；缓存命中差一层，就差好几倍 |
| 汇合 | 等最慢的那个分片 | 截面策略的节奏是 bar：毫秒到秒 |
| 策略和风控 | 逐笔判断：微秒级；几千只股票一起排名：约百 µs | 都在内存里算 |
| 报单到交易所、拿回回报 | 托管直连：往返几十到几百 µs；经普通券商柜台：到毫秒 | 网络和撮合，自己能优化的不多 |
| 推送到交易员屏幕 | 几十 ms | 给人看的，够用就行 |
| 写盘 | 毫秒级 | 所以只能放在旁路上 |

这张表说明两件事。一是几十纳秒的交接，放进毫秒级的链路里看不出来，只有整条链只有几微秒的系统才值得抠它。二是行情蜂拥的时候，慢的不是交接，是排队（[3.5](#burst)）。

## 3. 怎么切：工业级系统的几条规则 {#rules}

### 3.1 关键路径一个线程跑到底，队列只放旁路 {#run-to-completion}

最快的系统把收包、解码、更新盘口、判断、发单放在同一个线程里，一个函数接一个函数调下去，数据一直留在这个核的缓存里。每过一次线程之间的队列，就是一次跨核搬运，几十纳秒，外加一份抖动；所以队列只用来把落盘、日志、监控这些慢活甩出去。再快一档，是把解码甚至发单放进网卡上的 FPGA，软件只设参数。

### 3.2 多核靠按股票分片，片内跑到底 {#shard}

一个线程算不过来全市场，就按股票分给几个线程。同一只股票的消息必须按顺序处理，所以一只股票永远交给同一个线程；不同股票的线程并行算。要按消息量分，不按股票个数分：热门股的消息多得多，一般按前几天的消息量排一张“股票 → 线程”的表，开盘前定好。交易所的行情本来就按通道发，能直接按通道收，就不用自己再分一次；源头是一路全量的（比如供应商转发），才由接入线程按表分发。

### 3.3 一份数据给几个读者：广播环还是分开的 SPSC {#fanout}

读者都要全量、会增会减、在别的进程里（落盘、转发、监控），用广播环：写一份，生产者不看读者。读者各要一部分，或者丢了数据必须当场知道，用按读者分开的 SPSC。两者常叠着用：接入线程写一份进广播环，同时按股票写进各分片的队列（[#5 1.7](/zh/posts/spmc-shared-memory-broadcast-ring/#17-什么时候不用广播环)）。

### 3.4 汇合只放在必须汇合的地方，状态只让一个线程写 {#barrier}

截面打分要等所有股票，所以有汇合点；单只股票自己的因子不用等别人。持仓、资金、在途单只让决策线程一个人改；推送、监控要看，就读它发布出来的快照，不碰正在改的那份。快照怎么发才不会读到一半新一半旧，见 [#14](/zh/posts/prefetch-warmup-double-buffer/) 的双缓冲。

### 3.5 行情蜂拥：慢在排队，不在交接 {#burst}

开盘、收盘、消息面的时候，消息量是平时的好几倍。只要每条要做的活比消息到来的间隔长，就开始积压：后来的消息要等前面的算完，因子用的就是旧行情。过一次队列几十纳秒，跟排队比可以忽略；要省的是排队：按股票分给更多线程，或者让每条的活变少。

积压都堆在环和队列里：积压 =（到达速度 − 处理速度）× 持续时间，不能超过容量，广播环超过就会套圈（[#5 2.3.2](/zh/posts/spmc-shared-memory-broadcast-ring/#232-慢读者会被套圈余量--容量--速率差)）。要知道够不够，拿真实行情把开盘那几分钟按原速放一遍，量每条从进来到算完的时间，再看积压怎么涨落。

### 3.6 旁路不许拖住热路径 {#side-rule}

热线程打日志、交给落盘，只往队列或环里写一条就走（[#4](/zh/posts/lock-free-queue-logger-micro-batching/)）；格式化、写盘、推送都在别的线程。不赶时间的读者不要死循环盯着最新槽位，隔一会读一批，省得每条都把生产者要写的那一行抢走一次（[#5 1.6.5](/zh/posts/spmc-shared-memory-broadcast-ring/#165-读者该怎么等)）。

## 4. 因子一致性：从架构到运维，保证回测和实盘的因子逐值相同 {#factors}

### 4.1 回测和实盘：同一份代码，每天逐值对账 {#replay}

1. **核心目标：解决“回测美好、实盘亏钱”时对不上账的问题**
   - **实盘表现比回测差，要先分清是谁的问题**：是策略本身失效了，还是实盘算出来的因子值和回测里不一样。后一种不排除掉，前一种就没法判断。
   - **例子**：某只股票 10:00:00 的因子值，回测里是 0.82，实盘里是 0.79。开仓线是 0.8，回测里这一刻开了仓，实盘没开，两边的收益从这一笔起就对不上了。
   - **对不上的原因分两类**：系统自己的（代码、状态、线程顺序），和输入数据的（丢包、时间口径、数据商修正）。下面先用同一份代码和每天对账把差异找出来，再分两个阶段把这两类分开。

2. **架构方案：统一接口，回测和实盘跑同一份代码**
   ```cpp
   struct Factor {
       void on_tick(const Tick& t);   // 来一条行情，更新内部状态
       double value() const;          // 读当前的因子值
       void reset();                  // 换交易日，清掉内部状态
   };
   ```
   <svg viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="上面一行是实盘：交易所组播经网卡进来，行情接入线程解码成 Tick，分片线程来一条调一次 on_tick；下面一行是回测：历史行情（实盘录像或数据商文件）由回放器按交易日、按时间排序，一条条构造 Tick 调用；两行都指向右边同一个 Factor，它只有 on_tick、value、reset 三个函数；回测一天喂完调 reset 再读下一天；因子里的时间只用行情自带的交易所时间" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
     <style>
       .rp0bg  { fill: #fbfaf7; }
       .rp0u   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
       .rp0d   { fill: #f3efe6; stroke: #b8ab8c; stroke-width: 1.3; }
       .rp0m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.5; }
       .rp0ink { fill: #1c1b18; font-size: 12.5px; }
       .rp0sm  { fill: #1c1b18; font-size: 11.5px; }
       .rp0mut { fill: #6b6558; font-size: 12px; }
       .rp0ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
       .rp0hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
       .rp0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
       .rp0lp  { stroke: #8c7a52; stroke-width: 1.3; stroke-dasharray: 5 4; fill: none; }
       .rp0hh  { fill: #6b6558; }
       .rp0hp  { fill: #8c7a52; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0bg { fill: #17161b; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0u { fill: #23262c; stroke: #3f4650; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0d { fill: #2a2721; stroke: #6b6250; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0m { fill: #33421f; stroke: #8fb257; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0ink, :root:is([data-theme="dark"], [data-theme="black"]) .rp0sm, :root:is([data-theme="dark"], [data-theme="black"]) .rp0ttl, :root:is([data-theme="dark"], [data-theme="black"]) .rp0hd { fill: #e9e7ef; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0mut { fill: #a19caf; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0ln { stroke: #a19caf; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0hh { fill: #a19caf; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0lp { stroke: #b8ab8c; }
         :root:is([data-theme="dark"], [data-theme="black"]) .rp0hp { fill: #b8ab8c; }
     </style>
     <defs>
       <marker id="rp0ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="rp0hh"/></marker>
       <marker id="rp0ap" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="rp0hp"/></marker>
     </defs>
     <rect class="rp0bg" x="0" y="0" width="760" height="340" rx="10"/>
     <text class="rp0ttl" x="24" y="32">喂法不同，因子是同一个</text>
     <text class="rp0hd" x="24" y="100">实盘</text>
     <rect class="rp0u" x="70" y="70" width="120" height="50" rx="6"/>
     <text class="rp0ink" x="130" y="91" text-anchor="middle">交易所组播</text>
     <text class="rp0sm" x="130" y="109" text-anchor="middle">网卡收包</text>
     <rect class="rp0u" x="215" y="70" width="140" height="50" rx="6"/>
     <text class="rp0ink" x="285" y="91" text-anchor="middle">行情接入线程</text>
     <text class="rp0sm" x="285" y="109" text-anchor="middle">解码成 Tick</text>
     <rect class="rp0u" x="380" y="70" width="130" height="50" rx="6"/>
     <text class="rp0ink" x="445" y="91" text-anchor="middle">分片线程</text>
     <text class="rp0sm" x="445" y="109" text-anchor="middle">来一条调一次</text>
     <path class="rp0ln" d="M190 95 H211" marker-end="url(#rp0ah)"/>
     <path class="rp0ln" d="M355 95 H376" marker-end="url(#rp0ah)"/>
     <text class="rp0hd" x="24" y="240">回测</text>
     <rect class="rp0d" x="70" y="210" width="120" height="50" rx="6"/>
     <text class="rp0ink" x="130" y="231" text-anchor="middle">历史行情</text>
     <text class="rp0sm" x="130" y="249" text-anchor="middle">录像或数据商文件</text>
     <rect class="rp0d" x="215" y="210" width="140" height="50" rx="6"/>
     <text class="rp0ink" x="285" y="231" text-anchor="middle">回放器</text>
     <text class="rp0sm" x="285" y="249" text-anchor="middle">按交易日、按时间排序</text>
     <rect class="rp0d" x="380" y="210" width="130" height="50" rx="6"/>
     <text class="rp0ink" x="445" y="231" text-anchor="middle">逐条构造 Tick</text>
     <text class="rp0sm" x="445" y="249" text-anchor="middle">一条条调用</text>
     <path class="rp0ln" d="M190 235 H211" marker-end="url(#rp0ah)"/>
     <path class="rp0ln" d="M355 235 H376" marker-end="url(#rp0ah)"/>
     <path class="rp0lp" d="M445 260 V280 H285 V264" marker-end="url(#rp0ap)"/>
     <text class="rp0mut" x="365" y="298" text-anchor="middle">一天喂完 → reset() → 读下一天</text>
     <rect class="rp0m" x="560" y="115" width="180" height="100" rx="8"/>
     <text class="rp0hd" x="650" y="140" text-anchor="middle">Factor（只有一份）</text>
     <text class="rp0sm" x="578" y="164">on_tick(t)：更新状态</text>
     <text class="rp0sm" x="578" y="184">value()：读因子值</text>
     <text class="rp0sm" x="578" y="204">reset()：换交易日</text>
     <path class="rp0ln" d="M510 95 C535 95 535 150 556 150" marker-end="url(#rp0ah)"/>
     <path class="rp0ln" d="M510 235 C535 235 535 182 556 182" marker-end="url(#rp0ah)"/>
     <text class="rp0mut" x="24" y="326">因子里的“现在”一律用 t.exch_time，不读系统时钟；需要前一天数据的，reset() 之后先预热。</text>
   </svg>

   - **因子不知道自己在回测还是实盘里**：它只管来一条行情、更新一次状态。行情从哪来，由调用它的那一层决定。
   - **实盘这样调**：行情接入线程把收到的组播包解码成 `Tick`，分片线程拿到一条就调一次 `on_tick`（[1.1](#tick)）。
   - **回测这样调**：回放器按交易日读历史行情，按时间顺序一条条构造 `Tick`，调的是同一个 `on_tick`；一天喂完，调 `reset()`，再读下一天。
   ```cpp
   // 实盘：分片线程从队列里读，来一条调一次
   while (running)
       if (queue.read(t)) factor.on_tick(t);

   // 回测：按交易日读历史行情，按时间顺序调同一个函数
   for (Date d : days) {
       factor.reset();
       for (const Tick& t : load_day(d)) factor.on_tick(t);
   }
   ```
   - **喂的顺序要和实盘一样**：只用到一只股票的因子，可以每只股票单独跑完一天；截面因子要把全市场的行情按交易所时间归并成一条流（同一时刻按序号排），和实盘到达的顺序一致。
   - **因子里的“现在”一律用行情自带的时间**：实盘的“现在”是墙上时间，回测的“现在”是这条行情的时间。因子里要是读了系统时钟，回测时拿到的是今天的时间，窗口和 bar 边界全错，**所以因子里只用 `t.exch_time`**。
   - **研究和实盘各写一份，迟早会分叉**：研究用 Python 写一份、实盘用 C++ 再写一份，细节总会不一样，例如一份跳过 NaN、一份没跳，或者一份按收盘价算、一份按最新价算。
   - **只有一份代码，“两份代码写得不一样”这个原因就没了**。

3. **运维机制：每天盘后用实盘录像重放，逐值对账**
   - **盘中把输入和输出都存下来**：落盘读者从广播环里把实盘收到的每条行情原样存下（[1.4](#side)），连同收到时间；分片线程把每次算出的因子值也写进日志。
   - **录的是实盘当时看到的样子**：丢了的那条录不到，晚到的按晚到的顺序录，补回来的按补回来的时刻录。所以重放的输入和实盘的输入一模一样。
   - **盘后用录像重放**：回放器读这份录像，喂给同一个 `on_tick`，得到另一串因子值。
   - **按行情序号逐值比**：把两串值按同一条行情对齐，一个一个比。
      - **同一份二进制、同一份输入，结果应该逐位相同**：阈值可以是 0，差一位就说明哪里有不确定的东西。
      - **和另一种语言写的研究原型比，才需要容差**：例如相对误差 1e-9，因为两边的浮点运算顺序本来就不同。
   - **例子**：全市场 5000 只股票，快照约 3 s 一个，一天交易 4 小时，约 14400 ÷ 3 × 5000 ≈ 2400 万个值，逐个比一遍要几秒到几十秒。
   - **改了代码也靠它做回归**：同一天的录像，改前改后输出逐位不变，才算没改坏；要变的，变化只出现在该变的因子上。

4. **差异排查：两阶段归因，先排除系统，再看数据**
   - **阶段一：实盘录像 vs 盘后重放，排除系统级问题**
      - **输入和代码都一样，结果还不同，只能是系统里有不确定的东西**。
      - **状态没重置、预热不一致**：开盘那一段对不上，等窗口滚过去才对上。修法是把预热条数和重启恢复的方式定成固定规则，回测照同一套来。
      - **多线程汇合顺序不固定**：浮点加法不满足结合律，截面汇总按“谁先算完先加谁”，每次结果末几位都不同。修法是按股票代码的顺序加（[3.4](#barrier)）。
      - **未定义行为**：没初始化的变量、越界读，每次跑出来的值不一样。
      - **因子里读了系统时钟**：重放时拿到的是盘后的时间。修法是只用 `t.exch_time`。
   - **阶段二：实盘录像 vs 数据商历史文件，排除数据源差异**
      - **阶段一对上了，代码就是确定的；两份输入喂同一份代码还有差，只能是输入不同**。研究员的回测读的是数据商文件，所以最常发现差异的是这一步。
      - **UDP 组播丢包**：实盘少一条，数据商文件是事后补齐的。例如丢了 10:00:03 的快照，下一个快照算出的成交量增量就是 6 s 的量。
      - **网络延迟跨界切 bar**：交易所时间 09:59:59.990 的行情，10:00:00.002 才到，按收到时间就进了下一根 bar。修法是两边统一按交易所时间切。
      - **数据商事后修正**：改过错误数据，单位和取整也可能不同，例如成交金额舍掉了角分。
   - **两个阶段都对上了还有差，才是策略本身的问题**。

## 5. 实盘：和回测差在哪，上线和出事怎么办 {#live}

### 5.1 实盘和回测差在四件事 {#live-vs-backtest}

回测是在一个可控的世界里跑：数据是事后补齐的，时间可以快进，算错了重跑一遍就行。实盘把这些都拿掉了。

1. **输入不受你控制**
   - **数据会脏**：丢包、乱序、晚到，数据商的字段口径和交易所不一致，某档价格突然是 0。回测读的历史文件是事后修过、补齐的版本。
   - **只看得到一次**：实盘当时收到什么就是什么，没法让交易所重发一遍“刚才那一刻”。所以要在当时就录下来（[4.1](#replay) 第 3 条）。
2. **时间不等你**
   - **不能暂停**：一个环节慢了，后面的消息就排队，因子用的是旧行情（[3.5](#burst)）。回测里慢一点只是跑得久一点。
   - **看的是尾部**：开盘那几分钟消息量是平时的好几倍，中位数好看没用，要看最慢的那些条。
3. **错了有代价**
   - **算错就是下错单**：回测里算错了改了重跑，实盘里算错的那一刻，单子可能已经发出去了。
   - **所以先求对、再求快**：宁可这只股票先不交易，也不拿不可信的数据算；每个改动先证明输出没变，再谈快了多少。
4. **状态一直是连续的**
   - **一个进程从开盘跑到收盘**：滚动窗口、盘口都是一路累积出来的。回测每天从头算，实盘中途崩了，状态就断了。
   - **跨天要预热，重启要能追回来**：预热条数和重启恢复的方式都要定成固定规则（[4.1](#replay) 第 4 条）。

> **接触过实盘，真正学到的是这四条缝在哪**
> - **写代码时就为它们设计**：能复现（录像加同一份代码），能发现（盘中监控、盘后对账），能止损（隔离、告警、停），能恢复（重启后把状态追回来）。
> - **判断优先级的顺序会变**：先保证对，再保证稳，最后才是快。

### 5.2 上线前：先逐值对上，再影子跑，最后小额放量 {#go-live}

1. **第一步，同一份录像逐值相同**
   - **怎么做**：新写的或改过的因子，先拿几天的实盘录像重放，和研究原型逐值比（容差见 [4.1](#replay) 第 3 条）。
   - **它证明的是算得对**：同一份输入，新版本和参考结果一致。
2. **第二步，影子模式**
   - **怎么做**：新版本接真实行情、真跑，算出的信号和“假如发了单”的订单只记下来、不发出去，和正在跑的版本并排比几天到几周。
   - **它查的是重放查不出来的东西**：真实流量下每条行情的处理时间、内存涨不涨、开盘蜂拥时会不会积压（[3.5](#burst)）。重放能证明算得对，证明不了跑得动。
3. **第三步，小额放量**
   - **怎么做**：先用很小的仓位真发单，确认成交和回报都正常，再一步步放大。
4. **以后每改一次代码或参数，都重跑第一步**
   - **标准**：同一天的录像，改前改后只有该变的因子变了。

### 5.3 盘中出了事：先止损、不下错单，原因留到盘后用录像复现 {#incidents}

1. **行情断档**
   - **影响**：丢了逐笔，这只股票的盘口和相关因子就不可信。
   - **处理：只停这一只股票**：标成不可信以后，策略对它不再下新单，已经挂着的单撤掉，已有的持仓先不动；补齐以后再恢复（断档怎么发现见 [1.1](#tick) 第 2 步）。
   - **为什么要撤挂单**：挂单的价格是按断档前的行情定的，行情已经变了，挂着就可能按过时的价格成交。
2. **数据异常**
   - **例子**：价格为 0、涨跌停时一边整排为空、数据商的字段口径突然变了。
   - **处理**：因子在入口先检查，异常的这一条不更新状态、记一笔告警，**不让一个坏值污染整个滚动窗口**。
3. **开盘蜂拥、延迟突增**
   - **影响**：每条要做的活比消息间隔长，就开始积压，因子用的是旧行情。
   - **处理**：盘中盯积压深度和每条的处理时间；盘后拿录像按原速放一遍，就能复现（[3.5](#burst)）。
4. **进程崩了要重启**
   - **丢的是内存里的状态**：滚动窗口、EMA、盘口都在内存里，进程一崩就没了，要先把它们追回来才能接着出信号。
   - **中间的行情不丢，前提是录像不在同一个进程里**：行情接入和落盘单独一个进程，通过共享内存的广播环把行情给因子进程（[1.4](#side)）。崩的是因子进程，接入和落盘照常在跑，崩掉的这段时间行情照样录进了文件。
   - **怎么追**：
      - **起点**：有存档就从存档恢复，存档里记着它对应的行情序号，从下一条开始重放；没有存档就从当天第一条重放。
      - **追到现在**：用同一个 `on_tick` 读录像，读到录像的末尾时，接着从广播环里按序号往下读，从文件切到实时行情，中间一条不漏也不重。
      - **追的这段时间不出信号**：状态还停在过去，按它下单就是按旧行情下单。
   - **为什么追得回来**：同样的行情按同样的顺序喂给同一个 `on_tick`，结果逐位相同（[4.1](#replay) 第 4 条阶段一），追出来的状态和没崩时一样。
   - **接入进程自己也崩了，这段行情就真丢了**：只能按断档处理（第 1 条），向交易所或数据商补；补不齐，用到这段逐笔的因子就先标成不可信，等窗口滚过去。

> **盘中只止损，原因盘后查**
> - **盘中只做三件事**：隔离、告警、必要时重启或停。
> - **盘后拿录像喂同一个 `on_tick`**：问题会在同一条行情上重现，再改、再用同一份录像验证。

## 6. AMD 和 Intel：差在核分组，不在内存序 {#ccx}

1. **AMD 把核分成一组一组（CCX），每组共用一块 L3**
   - **Intel 的一颗 CPU，一般所有核共用一块 L3**：随便挑两个核，交接的代价差不多。
   - **AMD 一组常见 8 个核、32 MB L3**：EPYC 服务器上有十几组。
2. **组内交接快，跨组慢几倍**
   - **交接要把一条缓存行从一个核搬到另一个核**：走的是两个核共用的那层缓存（[速查 2.6](/zh/ref/cpu-memory/#cross-core)）。
   - **同组走自己那块 L3，约 15–30 ns；跨组要绕片间互联，约 80–150 ns**。
   - **一个线程只用得上自己那组的 L3**：EPYC 标着几百 MB，工作集能放下的只有那一组的 32 MB。
3. **内存序上，AMD 和 Intel 一样；不一样的是 ARM**
   - **AMD 和 ARM 不是一类东西**：AMD 是一家做 CPU 的公司，和 Intel 一样做 x86 的 CPU，同一个可执行文件两家的机器都能跑；ARM 是另一套指令集，手机、苹果 M 系列、AWS Graviton 用的都是它，x86 的程序要重新编译才能跑。

     | | 是什么 | 指令集 | 内存序 |
     |---|---|---|---|
     | Intel | 做 CPU 的公司 | x86-64 | TSO |
     | AMD | 做 CPU 的公司 | x86-64 | TSO |
     | ARM | 指令集，授权给苹果、高通、亚马逊等公司做芯片 | AArch64 | 弱内存序 |

   - **内存序跟着指令集走，不跟着厂商走**：AMD 和 Intel 都是 x86，内存模型都是 TSO，acquire/release 编出来都是普通的 `mov`，同一份代码不用为 AMD 另写。
   - **ARM 是弱内存序**：acquire/release 要编成 `ldar`/`stlr`；内存序写错的代码，在 x86 上可能碰巧是对的，换到 ARM 上才出错。

> **上了 AMD 的机器，绑核按组排**
> - **先看分组**：`lscpu -e` 里 L3 编号相同的核在一组，或者用 `lstopo` 画出来。
> - **互相交接的线程放进同一组**：接入线程和它喂的分片线程。
> - **不交接的分到别的组**：不同分片之间不交接（[3.2](#shard)），落盘、监控这些旁路也放到别的组。
> - **工作集按一组的 L3 算**：别按整颗 CPU 标的总量算。

## 7. 订单簿：用逐笔合成每只股票的盘口 {#book}

1. **先分清几个名词：订单簿是全部，盘口是最前面几档，快照是每 3 秒拍的照片，逐笔是每一次变化**

   | 名词 | 是什么 | 谁有、多久一次 |
   |---|---|---|
   | **订单簿**（order book） | 交易所里所有还没成交的挂单，买卖两边各按价格排好，同一价格按时间排 | 完整的只在交易所的撮合系统里，每一笔都在变 |
   | **档** | 一个价位，比如 10.00 元那一档，就是所有挂在 10.00 的单加起来 | |
   | **盘口** | 订单簿里最靠近成交价的那几档：买一到买十、卖一到卖十，每档一个价格、一个总量 | 口语里常和订单簿混着说 |
   | **买一、卖一** | 买方出价最高的那档、卖方要价最低的那档，两者之间的差叫价差 | |
   | **快照** | 交易所隔一段时间拍的一张照片：十档盘口，加上最新价、累计成交量和成交额 | Level-2 约 3 秒一张 |
   | **逐笔委托** | 每来一笔新的挂单发一条：价格、数量、方向、委托号 | 每一笔都发 |
   | **逐笔成交** | 每成交一笔发一条：价格、数量、买卖双方的委托号；深圳的撤单也在这一路里 | 每一笔都发 |
   | **合成订单簿**（重建） | 自己拿逐笔，从开盘起一笔笔加、一笔笔减，在本地把订单簿复原出来 | 每来一条逐笔，就有一本最新的 |
   | **Level-1 / Level-2** | 行情的两个等级：Level-1 只有五档快照；Level-2 有十档快照，加上逐笔 | |

   - **逐笔是变化，订单簿是结果，快照是隔一会看一眼结果**：

     $$\underbrace{\text{订单簿}(t)}_{\text{全部挂单}} = \text{开盘时的订单簿} + \underbrace{\text{到 } t \text{ 为止的所有逐笔}}_{\text{每一次变化}}$$

     $$\underbrace{\text{快照}(t)}_{\text{每 3 秒一张}} = \underbrace{\text{订单簿}(t) \text{ 的前十档}}_{\text{盘口}} + \text{累计成交量、成交额}$$

   - **合成订单簿就是按第一个式子自己算**：算出来的前十档，在快照时刻应该和快照一样，这就是第 5 条的对拍。
   - **快照不是谁加工过的盘口**：它是交易所自己拍的，用快照算因子就是直接用交易所给的十档；合成订单簿才是自己用逐笔推出来的。
   - **本页代码里的 `Tick` 泛指一条行情消息**：可以是一张快照，也可以是一条逐笔。

2. **合成订单簿：拿逐笔在本地把订单簿一笔笔维护出来**
   - **快照太粗**：约 3 秒一张，只有十档。因子想每来一条逐笔就更新，就得自己维护一本订单簿。
   - **在架构里的位置**：分片线程拿到一条逐笔，先更新这只股票的订单簿，再更新因子（[1.1](#tick) 第 5 步，那里说的盘口就是这本订单簿）。所以订单簿和因子一样，只有一个线程写，不用加锁。
   - **规则一句话：委托加，成交和撤单减**：成交和撤单都按委托号找到原来那笔挂单，扣掉对应的量，扣到 0 就删掉。沪深每类消息的处理不一样，见 [IV：A 股业务知识 8.1](/zh/interview/a-share-business/#81-每类消息怎么改盘口)。

3. **因子怎么用订单簿：订单簿一直维护着，因子按需去读**

   <svg viewBox="0 0 760 290" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="逐笔先进订单簿，订单簿一直维护着；盘口类因子读订单簿的前几档，深度类和排队类因子读更深的档和每档的排队；逐笔类因子不经过订单簿，直接读这条逐笔；订单簿下方虚线框：定时取前十档，用于对拍和给研究侧合成快照" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
     <style>
       .ob7bg  { fill: #fbfaf7; }
       .ob7u   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
       .ob7d   { fill: #f3efe6; stroke: #b8ab8c; stroke-width: 1.3; }
       .ob7m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.5; }
       .ob7x   { fill: none; stroke: #8c7a52; stroke-width: 1.3; stroke-dasharray: 5 4; }
       .ob7ink { fill: #1c1b18; font-size: 12.5px; }
       .ob7sm  { fill: #1c1b18; font-size: 11.5px; }
       .ob7mut { fill: #6b6558; font-size: 12px; }
       .ob7hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
       .ob7ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
       .ob7lp  { stroke: #8c7a52; stroke-width: 1.3; stroke-dasharray: 5 4; fill: none; }
       .ob7hh  { fill: #6b6558; }
       .ob7hp  { fill: #8c7a52; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7bg { fill: #17161b; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7u { fill: #23262c; stroke: #3f4650; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7d { fill: #2a2721; stroke: #6b6250; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7m { fill: #33421f; stroke: #8fb257; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7x { stroke: #b8ab8c; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7ink, :root:is([data-theme="dark"], [data-theme="black"]) .ob7sm, :root:is([data-theme="dark"], [data-theme="black"]) .ob7hd { fill: #e9e7ef; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7mut { fill: #a19caf; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7ln { stroke: #a19caf; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7hh { fill: #a19caf; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7lp { stroke: #b8ab8c; }
         :root:is([data-theme="dark"], [data-theme="black"]) .ob7hp { fill: #b8ab8c; }
     </style>
     <defs>
       <marker id="ob7ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ob7hh"/></marker>
       <marker id="ob7ap" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ob7hp"/></marker>
     </defs>
     <rect class="ob7bg" x="0" y="0" width="760" height="290" rx="10"/>
     <rect class="ob7u" x="20" y="135" width="110" height="50" rx="6"/>
     <text class="ob7hd" x="75" y="156" text-anchor="middle">逐笔</text>
     <text class="ob7sm" x="75" y="174" text-anchor="middle">委托、成交、撤单</text>
     <rect class="ob7m" x="200" y="55" width="150" height="70" rx="8"/>
     <text class="ob7hd" x="275" y="84" text-anchor="middle">订单簿</text>
     <text class="ob7sm" x="275" y="106" text-anchor="middle">一直维护，每条改一次</text>
     <rect class="ob7d" x="520" y="30" width="220" height="40" rx="6"/>
     <text class="ob7ink" x="630" y="55" text-anchor="middle">盘口类因子：不均衡、价差</text>
     <rect class="ob7d" x="520" y="90" width="220" height="40" rx="6"/>
     <text class="ob7ink" x="630" y="115" text-anchor="middle">深度类、排队类因子</text>
     <rect class="ob7d" x="520" y="230" width="220" height="40" rx="6"/>
     <text class="ob7ink" x="630" y="255" text-anchor="middle">逐笔类因子：主动大单、撤单占比</text>
     <rect class="ob7x" x="190" y="165" width="170" height="46" rx="6"/>
     <text class="ob7ink" x="275" y="184" text-anchor="middle">定时取前十档</text>
     <text class="ob7sm" x="275" y="202" text-anchor="middle">对拍、给研究侧合成快照</text>
     <path class="ob7ln" d="M130 150 C 165 150 165 95 196 95" marker-end="url(#ob7ah)"/>
     <path class="ob7ln" d="M350 75 C 430 75 430 50 516 50" marker-end="url(#ob7ah)"/>
     <text class="ob7mut" x="435" y="45" text-anchor="middle">读前几档（盘口）</text>
     <path class="ob7ln" d="M350 105 C 430 105 430 110 516 110" marker-end="url(#ob7ah)"/>
     <text class="ob7mut" x="435" y="130" text-anchor="middle">读更深的档、排队</text>
     <path class="ob7lp" d="M275 125 V161" marker-end="url(#ob7ap)"/>
     <path class="ob7ln" d="M130 172 C 160 172 160 250 200 250 H516" marker-end="url(#ob7ah)"/>
     <text class="ob7mut" x="420" y="243" text-anchor="middle">直接读这条逐笔，不经过订单簿</text>
   </svg>

   - **盘口不是单独的一步，是去读订单簿的前几档**：盘口类因子直接读订单簿里买一、卖一的下标，往外看几档。不会每条逐笔都把前十档拷出来另存一份，那是白做功。
   - **深度类、排队类因子读得更深**：比如前二十档的总量、买一那档排在前面的单有多少。快照给不了这些，只有自己的订单簿有。
   - **逐笔类因子不经过订单簿**：主动大单净流入看的是这一笔成交谁主动、多大，直接读这条逐笔，和订单簿长什么样无关。
   - **定时取前十档只在两处**：
      - **对拍**：每到交易所快照时刻取一次，和快照比（第 5 条）。
      - **给研究侧合成快照**：研究员的因子按快照写的，就每隔固定时间（比如 1 秒）从订单簿取一份前十档。比交易所的快照更密，时刻也能自己定。

4. **数据结构：价格档用数组，委托号用哈希表**
   ```cpp
   struct Order { int32_t px; int64_t qty; bool is_bid; };   // 一笔挂单：价位下标、剩余量、方向

   struct Book {
       int32_t lo;                                     // 跌停价，单位是最小价位（0.01 元）
       std::vector<int64_t> bid_qty, ask_qty;          // 每档总量，下标 = 价格 - 跌停价
       int32_t best_bid, best_ask;                     // 买一、卖一的下标
       std::unordered_map<uint64_t, Order> orders;     // 委托号 → 挂单

       void add(uint64_t id, int32_t price, int64_t qty, bool is_bid) {
           int32_t i = price - lo;
           orders[id] = {i, qty, is_bid};
           (is_bid ? bid_qty : ask_qty)[i] += qty;
       }
       void reduce(uint64_t id, int64_t qty) {         // 成交和撤单都走这里
           auto it = orders.find(id);
           if (it == orders.end()) return;             // 上海的主动方本来就不在盘口里
           Order& o = it->second;
           (o.is_bid ? bid_qty : ask_qty)[o.px] -= qty;
           if ((o.qty -= qty) == 0) orders.erase(it);
       }
   };
   ```
   - **价格档用数组，以最小价位为下标**：A 股有涨跌幅限制，一天里能出现的价位是有限的。10 元的主板股票涨跌 10%，价格只能在 9.00–11.00 之间，一共 201 档。`价格 − 跌停价` 就是下标，增删都是直接定位，不用查找。
   - **委托号用哈希表**：成交和撤单只带委托号，要先按号找到那笔挂单，才知道它在哪一档、还剩多少。热路径上用开放寻址的哈希表（比如 `absl::flat_hash_map`），元素连续放，比 `std::unordered_map` 的链表少几次缓存缺失。
   - **买一、卖一单独记一个下标**：买一被吃空了，从这个下标往下扫到下一个非空的档。档位稀疏时扫得慢，可以再加一个位图，每一位表示一档空不空，一条指令就能找到下一个非空档。
   - **为什么不用 `std::map`（红黑树）**：每次更新都要往下走好几层，每层一次缓存缺失，插入还要分配节点。价格范围本来就是固定的，数组直接定位更快。
   - **每档只存总量就够大多数因子用**：要算某笔单排在这一档的第几位，才需要再按时间存每档的委托队列。
   - **例外：新股上市头几天没有涨跌幅限制**：价格范围定不下来，数组要开大一些，或者随价格变化往外扩。

5. **怎么验：和交易所快照逐档比**
   - **错了没人告诉你**：盘口重建错了，程序照样跑，因子照样出数。能拿来核对的只有交易所的快照，所以重建和对拍要一起做。

> **合成的订单簿怎么验**
> - **每到一个快照时刻，拿重建出来的十档和快照逐档比**：比每档的价和量，再比累计成交量和成交额。
> - **先对齐时刻**：快照不带逐笔的序号，先把时间不晚于快照的逐笔处理完再比；对不上，在前后一小段里逐条往前推。
> - **集合竞价那段不比**：只挂单不撮合，买一可以高于卖一，从连续竞价开始比。
> - **对不上先查三处**：丢了逐笔（按序号查连续）；撤单那一路漏了（深圳在逐笔成交里，上海在逐笔委托里）；市价单、本方最优单的价格没按规则补。
> - **盘中对不上只停这一只股票**（[5.3](#incidents)），原因盘后查。各种对不上分别说明什么，见 [IV：A 股业务知识 8.2–8.3](/zh/interview/a-share-business/#82-和快照十档对拍)。

> **重建订单簿不撮合，撮合逻辑用在别处**
> - **撮合是交易所做的，逐笔成交就是撮合的结果**：重建只是照着消息加、减，不判断能不能成交。
> - **深圳盘口会暂时交叉，也不用自己撮**：一笔够得着对面的限价委托进来，它的成交消息稍后才到，这中间买一可能不低于卖一；等成交消息来了再扣量。上海的委托消息给的是撮合后剩下的量，没有这一步。
> - **回测里的撮合模拟器，是撮合逻辑用得最多的地方**：历史行情里没有自己的单，挂在哪一档、前面排着多少量、什么时候成交、成交多少、从发单到交易所的延迟，都要自己模拟。模拟得太乐观，回测收益就是虚的。
> - **集合竞价的参考价，按撮合规则算**：竞价阶段只收单不成交，参考价取成交量最大的那个价。快照里一般带着，自己算是为了推算多一笔单价格会怎么变。
> - **测试用的模拟交易所**：联调时用一个本地撮合引擎扮演交易所，接报单、回成交和回报，不用连真实柜台就能测下单、撤单、部分成交。
> - **因子回算用不到它**：因子只读行情，不下单。要模拟自己的单怎么成交，那是策略回测的事。

## 8. 批量回算：数据比缓存大几个数量级，瓶颈换成了带宽 {#batch}

这一部分只讲因子回算：在几年的历史行情上把每个因子的值算出来。拿这些因子值模拟交易、算收益，才是回测，那是下一步，不在这里。

<svg viewBox="0 0 760 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="批量回算的流程：原始逐笔（按天、全市场按时间排）先进中间层，只算一次、记版本：按股票重排、合成订单簿、定时快照、公共中间量；中间层切成互不通信的任务，每个任务是一只股票的一天，分到多核、多机，多日因子往前多读 N 天预热；截面因子再做一步截面汇总，每个时刻几千只股票的值排名、打分，单股票因子直接出结果；因子值按天存，给回测用；最后按天和实盘录像重放的结果逐值对账" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .bt8bg  { fill: #fbfaf7; }
    .bt8u   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .bt8d   { fill: #f3efe6; stroke: #b8ab8c; stroke-width: 1.3; }
    .bt8m   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.5; }
    .bt8x   { fill: none; stroke: #8c7a52; stroke-width: 1.3; stroke-dasharray: 5 4; }
    .bt8ink { fill: #1c1b18; font-size: 12.5px; }
    .bt8sm  { fill: #1c1b18; font-size: 11.5px; }
    .bt8mut { fill: #6b6558; font-size: 12px; }
    .bt8hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .bt8ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .bt8lp  { stroke: #8c7a52; stroke-width: 1.3; stroke-dasharray: 5 4; fill: none; }
    .bt8hh  { fill: #6b6558; }
    .bt8hp  { fill: #8c7a52; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8bg { fill: #17161b; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8u { fill: #23262c; stroke: #3f4650; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8d { fill: #2a2721; stroke: #6b6250; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8m { fill: #33421f; stroke: #8fb257; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8x { stroke: #b8ab8c; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8ink, :root:is([data-theme="dark"], [data-theme="black"]) .bt8sm, :root:is([data-theme="dark"], [data-theme="black"]) .bt8hd { fill: #e9e7ef; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8mut { fill: #a19caf; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8ln { stroke: #a19caf; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8hh { fill: #a19caf; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8lp { stroke: #b8ab8c; }
  :root:is([data-theme="dark"], [data-theme="black"]) .bt8hp { fill: #b8ab8c; }
  </style>
  <defs>
    <marker id="bt8ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="bt8hh"/></marker>
    <marker id="bt8ap" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="bt8hp"/></marker>
  </defs>
  <rect class="bt8bg" x="0" y="0" width="760" height="360" rx="10"/>
  <rect class="bt8u" x="20" y="50" width="150" height="56" rx="6"/>
  <text class="bt8hd" x="95" y="73" text-anchor="middle">原始逐笔</text>
  <text class="bt8sm" x="95" y="93" text-anchor="middle">按天、全市场按时间排</text>
  <rect class="bt8m" x="215" y="40" width="250" height="76" rx="8"/>
  <text class="bt8hd" x="340" y="63" text-anchor="middle">中间层：只算一次，记版本</text>
  <text class="bt8sm" x="340" y="84" text-anchor="middle">按股票重排 · 合成订单簿</text>
  <text class="bt8sm" x="340" y="103" text-anchor="middle">定时快照 · 公共中间量</text>
  <path class="bt8ln" d="M170 78 H211" marker-end="url(#bt8ah)"/>
  <rect class="bt8x" x="500" y="20" width="240" height="200" rx="8"/>
  <text class="bt8hd" x="620" y="42" text-anchor="middle">多核、多机：任务互不通信</text>
  <rect class="bt8u" x="520" y="56" width="200" height="34" rx="5"/>
  <text class="bt8ink" x="620" y="78" text-anchor="middle">股票 A · 第 d 天</text>
  <rect class="bt8u" x="520" y="98" width="200" height="34" rx="5"/>
  <text class="bt8ink" x="620" y="120" text-anchor="middle">股票 B · 第 d 天</text>
  <rect class="bt8u" x="520" y="140" width="200" height="34" rx="5"/>
  <text class="bt8ink" x="620" y="162" text-anchor="middle">…… 每只股票每天一个</text>
  <text class="bt8mut" x="620" y="203" text-anchor="middle">多日因子：往前多读 N 天预热</text>
  <path class="bt8ln" d="M465 78 H496" marker-end="url(#bt8ah)"/>
  <rect class="bt8d" x="500" y="258" width="240" height="56" rx="6"/>
  <text class="bt8hd" x="620" y="281" text-anchor="middle">截面汇总（截面因子才要）</text>
  <text class="bt8sm" x="620" y="301" text-anchor="middle">每个时刻几千只：排名、打分</text>
  <path class="bt8ln" d="M640 220 V254" marker-end="url(#bt8ah)"/>
  <rect class="bt8d" x="260" y="258" width="190" height="56" rx="6"/>
  <text class="bt8hd" x="355" y="281" text-anchor="middle">因子值</text>
  <text class="bt8sm" x="355" y="301" text-anchor="middle">按天存，给回测用</text>
  <path class="bt8ln" d="M500 286 H454" marker-end="url(#bt8ah)"/>
  <path class="bt8lp" d="M540 220 C 540 240 440 238 430 254" marker-end="url(#bt8ap)"/>
  <text class="bt8mut" x="470" y="236" text-anchor="middle">单股票因子</text>
  <rect class="bt8u" x="20" y="258" width="190" height="56" rx="6"/>
  <text class="bt8hd" x="115" y="281" text-anchor="middle">按天逐值对账</text>
  <text class="bt8sm" x="115" y="301" text-anchor="middle">和实盘录像重放比（4.1）</text>
  <path class="bt8ln" d="M260 286 H214" marker-end="url(#bt8ah)"/>
  <text class="bt8mut" x="380" y="344" text-anchor="middle">输入流按顺序读，只花带宽；每个任务的状态只有一只股票，放得进缓存。</text>
</svg>

1. **盘中和批量，慢在不同的地方**

   | | 盘中逐条 | 批量回算 |
   |---|---|---|
   | 关心什么 | 一条行情从进来到算完多少微秒 | 全部数据算一遍要几小时、要几台机器 |
   | 瓶颈 | 每条行情碰到的几次缓存缺失，延迟受限 | 内存带宽、磁盘 IO，带宽受限 |
   | 缓存怎么用 | 让热数据一直留在缓存里 | 每份数据只从内存搬一次 |
   | 热路径是什么 | 一条行情经过的那条调用链 | 最内层那个循环，跑几百亿次 |
   | 怎么并行 | 按股票分片，一片绑一个核（[3.2](#shard)） | 按交易日切成任务，单股票因子再按股票切，分到多核、多机 |

   - **量级**：全市场一天的逐笔约 1–3 亿条，一年几百亿条、TB 级。按交易日切开以后，一个任务是一天的全市场，输入还有几 GB 到十几 GB。
   - **输入流不用装进缓存，要装下的是状态**：
      - **输入流每条只用一次**：按顺序读，硬件预取跟得上，比缓存大多少都没关系，花的只是带宽。这一点盘中和批量一样。
      - **状态每条都要随机去碰**：按股票代码找这只股票的盘口和因子状态，按委托号找原来那笔挂单。状态放不进缓存，每条行情的这几次访问就是缓存缺失，和盘中缓存案例里是同一种问题。
   - **盘中不爆、批量爆，差在一个核要管多少状态**：盘中一片只管几百只股票，状态放得进缓存；批量一个任务要是一个线程处理一天的全市场，状态就是全市场的，光委托号哈希表就比 L3 大。

2. **缓存照样决定快慢，只是用法变了：每份数据只从内存搬一次**
   - **按顺序整段读**：硬件预取跟得上，这时卡的是内存带宽，不是延迟。
   - **最浪费的是多遍扫**：每个因子各把整列扫一遍，还生成一堆中间数组，同一份数据从内存搬了几十次。
   - **改成分块加融合**：读一块能放进缓存的数据，所有因子在这一块上一次算完，再读下一块。
   - **带宽受限，就少搬字节**：只读要用的列（按列存储），字段用够用的最小类型，价格用整数分。
   - **最内层循环就是批量的热路径**：跑几百亿次，每次省 1 ns 就是几十秒，所以数据布局、SIMD、分支这些照样有用。

3. **中间结果分层存，别每次都从逐笔重来**
   - **分层**：逐笔 → 合成订单簿和定时快照（[第 7 部分](#book)）→ 公共中间量 → 因子。
   - **最贵的一层只算一次**：合成订单簿要把逐笔从头推一遍，算好存下来，所有因子都从这一层读；新加一个因子，不用再碰逐笔。
   - **代价是要管版本**：中间层改了，比如修了订单簿的一个 bug，它下游的所有因子都要重算，所以每一层要记是哪个版本算出来的。

4. **并行按交易日切，多日窗口要往前多读几天**
   - **天和天之间只差跨天的状态**：按交易日切成独立的任务，分到多核、多机。
   - **用到前 N 天数据的因子，每块往前多读 N 天**：多读的这段只用来预热，不输出。
   - **状态放不下，有两种办法**：
      - **再按股票切**：先把一天的数据按股票重排存下来，这一步本身要全量扫一遍，放在中间层里只做一次（第 3 条）。之后每个任务是“一只股票的一天”，状态只有这一只的，放得进缓存，不再缺失。
      - **往前看几条，提前预取状态**：批量的数据都在手上，处理第 i 条时就能看到第 i+8 条是哪只股票、哪笔委托，提前把它的状态预取进来，让几次缺失重叠起来（[缓存案例](/zh/posts/low-latency-cache-case-study/)里的做法）。盘中做不到，下一条还没来。
      - **怎么选**：重排一次，后面所有因子都受益；预取不用改数据格式，但每个碰状态的地方都要改。
   - **截面因子分两步**：先按股票算好每只的中间量，最后一步在每个时刻几千只股票的值上做排名、打分，这一步的数据很小。
   - **多机要能单独重跑某一天**：哪天失败就重跑哪天；结果按天逐值比，用的就是 [4.1](#replay) 的对账。

5. **批量想向量化，一致想逐条增量**
   - **整列向量化最快**：但运算顺序和实盘逐条增量不同，末位会差；窗口没满、NaN、跨天预热这些边界也容易写成两套。
   - **逐条喂同一个 `on_tick` 最一致**：[4.1](#replay) 的保证直接成立，代价是用不上整列的向量化，速度靠按天并行和数据布局补回来。

> **主要是顺序扫的数据，从哪几方面优化：少搬字节、少开流**
> - **几趟循环合成一趟**：同一份数据过一遍，就把几个因子都算完，不要每个因子各扫一遍。这样搬的字节少了，同时在扫的流也少了。
> - **按访问方式选布局**：每次只扫少数几列，就按列存（SoA）；每条记录的字段都要一起用，就按行存（AoS）。按行存时一条记录只算一个流，不会冒出几十个流。
> - **数据类型缩小**：价格用 `int32` 按最小变动单位存，能用 `float` 的不用 `double`（要和实盘逐值对上的量别降精度）。字节减半，带宽压力也减半。
> - **分块，让工作集留在 L2**：一大块数据要反复用几次，就切成能放进 L2 的小块，一块用完再换下一块，不要每次都从内存重新读。
> - **用大页**：顺序扫每过一页就要查一次 TLB，大页让 TLB 缺失少得多。
> - **卡在带宽上时，要么多核分摊，要么让每个字节多算点东西**：单核能用到的带宽有上限，因为一个核同时在途的缺失被 LFB 的项数卡住；多核能一直加到内存通道的峰值。

> **按股票查状态慢，本质是访存延迟受限：随机访问比缓存大的工作集，缺失一次接一次地等**
> - **和缓存案例是同一类瓶颈**：[缓存案例](/zh/posts/low-latency-cache-case-study/)里一次事件散着碰 128 条期权行，这里每条行情散着碰几只股票的状态。两边算得都很少，时间都花在等缺失上；地址要先读出来才知道下一步去哪（查哈希表、读股票记录），这一跳依赖也一样。
> - **热点落在查找上**：`perf record` 排在前面的是 `find`、哈希、读状态的第一个字段，不是因子公式本身。
> - **IPC 低、缺失多，带宽却没跑满**：IPC 低于 1、L1D 和 LLC 缺失率高，说明核在等数据；带宽没满，说明卡的是延迟，改布局、加预取有用。带宽已经满了，就该少搬字节（第 2 条）。
> - **dTLB 缺失多**：状态散在太多页上，每次查找还要先走页表。
> - **股票越多越慢，每条行情的工作量却没变**：工作集是股票数乘每只状态的大小，超过 L2 就开始掉出缓存。
> - **按股票排好再喂明显更快**：同一份数据按时间交错着来就慢，差别只在局部性；冷门股每条特别慢，因为它的状态早被挤出缓存了。
> - **改法分两个方向：先让缺失变少，再让剩下的缺失重叠起来**。前 4 条是让缺失变少，最后一条是让缺失重叠，缓存案例的批处理和预取走的是后一个方向：
>   - **热点在 `find`、哈希**：股票代码先映射成连续下标，状态放进按下标的数组。
>   - **每次只用到状态里几个字段**：冷热字段拆开，把结构体做小。
>   - **dTLB 缺失多**：状态数组用大页。
>   - **一个核放不下全部状态**：盘中按股票分片（[3.2](#shard)），批量按股票重排（第 4 条）。
>   - **这些都做完缺失还在，各条之间又互不依赖**：往前看几条，提前预取状态（第 4 条）。

> **批量回算怎么选**
> - **因子多、回算不算频繁**：批量也逐条喂同一个 `on_tick`，一份代码，一致性最省心。
> - **某个因子回算特别重**：单写一套向量化的批量版，和增量版逐值对拍，容差按两边的运算顺序定。
> - **不管选哪个**：批量结果都要和实盘录像重放的结果对上，才能拿去做研究。
