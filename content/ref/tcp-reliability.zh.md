---
title: "TCP 怎么做到可靠：确认重传、流量控制、拥塞控制"
date: 2026-11-02
slug: "tcp-reliability"
description: "IP 只管尽力把包送到，丢了、乱了、重了都不管；TCP 在它上面做出一条不丢、不乱、不重的字节流。靠的是给每个字节编号、累积确认、超时重传和快速重传；接收方用接收窗口告诉发送方自己还装得下多少（流量控制），发送方用拥塞窗口自己估计网络还扛得住多少（拥塞控制），实际能发的是两者里小的那个。再讲 Nagle 和延迟确认凑在一起时的 40 ms 卡顿、字节流为什么会“粘包”和怎么分出消息，以及 keepalive 和应用层心跳的分工。"
summary: "可靠靠编号加确认：没确认的就重传，连着 3 个重复确认不等超时就重传。能发多少看两个窗口：接收方的 rwnd 防止把对方的缓冲区塞爆，发送方自己的 cwnd 防止把网络塞爆，发送窗口取两者的较小值。TCP 是字节流，没有消息边界，消息要自己用长度前缀或分隔符切出来。"
toc: true
math: true
group: cpplinux
topic: net
weight: 119
---

IP 层只负责把一个个包尽力送到对方：路由器缓冲区满了就丢，两个包走不同的路就可能乱序，链路层重发还可能出现重复。TCP 要在这上面给程序一条“写进去什么，对面就按原样、按顺序读出来什么”的字节流。连接怎么建、怎么关，在 [TCP 状态](/zh/ref/tcp-states/)那页；这页讲连接建好以后，数据怎么做到不丢、不乱、不重，又怎么决定一次发多快。

## 1. TCP 和 UDP：各保证什么

### 1.1 UDP 只在 IP 上加了端口和校验和 {#udp}

UDP 的首部只有 8 字节：源端口、目的端口、长度、校验和。它把程序的一次 `sendto` 原样装进一个数据报发出去，对面一次 `recvfrom` 收到的就是完整的一个数据报。至于丢没丢、先后对不对，UDP 不管，也不建连接、不控制速度。TCP 的首部至少 20 字节，多了序号、确认号、窗口和一组标志位，选项最多再加 40 字节，这些字段就是后面几节那些机制的载体。

| | TCP | UDP |
|---|---|---|
| 连接 | 先握手建连接 | 不建连接，直接发 |
| 交付 | 不丢、不乱、不重 | 可能丢、乱、重 |
| 边界 | 字节流，没有消息边界 | 一次发送就是一个数据报 |
| 速度 | 受流量控制和拥塞控制约束 | 程序发多快就多快 |
| 首部 | 20–60 字节 | 8 字节 |
| 一对多 | 只能一对一 | 能广播、组播 |

### 1.2 什么时候用 UDP：宁可丢，也不要等 {#when-udp}

TCP 的可靠是用“等”换来的：中间丢了一个包，后面的数据即使到了也不能交给程序，要等丢的那个重传补上（队头阻塞）。对视频通话、直播、游戏来说，迟到的数据和丢掉的数据一样没用，等它反而让后面的画面一起卡住，所以它们用 UDP，丢了就跳过，或者用前向纠错补。DNS 查询一问一答，一个包就装得下，用 UDP 省掉握手的一个来回。HTTP/3 底下的 QUIC 也跑在 UDP 上，是把重传、拥塞控制这些搬到用户态自己做，好绕开 TCP 在内核里改不动、还会队头阻塞的部分。**选 UDP 不是因为它快，而是因为程序宁可自己处理丢包，也不愿意被重传拖住。**

## 2. 确认和重传：靠编号发现丢失

### 2.1 序号和累积确认 {#cumulative-ack}

TCP 给发出的每个字节编一个序号，报文里的 `seq` 是这段数据第一个字节的编号。接收方回的确认号 `ack = N` 意思是“编号 N 之前的字节我都按顺序收到了，下一个要 N”，这叫累积确认。乱序到达的数据，接收方先放在缓冲区里，但确认号停在缺口那里不动；缺口补上以后，确认号一下跳过整段。重复收到的数据按编号一比就知道收过了，直接丢掉。**编号同时解决了三件事：按编号排序消除乱序，按编号去重，确认号停在哪里就说明哪里丢了。**

### 2.2 超时重传：RTO 跟着 RTT 走 {#rto}

发送方每发出一段数据就等它的确认，等太久就认为丢了、重发。等多久叫重传超时（RTO）。固定一个值不行：同机房往返几十 µs，跨洋往返一两百 ms，定短了会把只是慢一点的包当成丢了，定长了真丢时干等。所以 RTO 跟着实测的往返时间（RTT）算：

$$
\text{SRTT} \leftarrow \tfrac{7}{8}\,\text{SRTT} + \tfrac{1}{8}\,\text{RTT}_{\text{新样本}},\qquad
\text{RTTVAR} \leftarrow \tfrac{3}{4}\,\text{RTTVAR} + \tfrac{1}{4}\,\lvert \text{SRTT} - \text{RTT}_{\text{新样本}} \rvert,\qquad
\text{RTO} = \text{SRTT} + 4\,\text{RTTVAR}
$$

平滑的 RTT 加上 4 倍的波动幅度，RTT 越抖，留的余量越大。Linux 上 RTO 最小 200 ms，最大 120 s，还没测到 RTT 时（比如握手）从 1 s 开始。重传过的那段数据，收到的确认分不清是对原来那次还是对重传那次，所以不拿它来测 RTT。同一段数据再超时，RTO 翻倍再等（指数退避）：网络可能正堵着，越重发越堵。

### 2.3 快速重传：三个重复确认就重发 {#fast-retransmit}

超时重传最少也要等 200 ms，对同机房的连接来说太久了。接收方其实早就在“报告”丢包：缺口后面每到一段数据，它都回一个确认号停在缺口处的 ACK，也就是重复 ACK。发送方连着收到 3 个重复 ACK，就判断那一段丢了，不等超时立刻重传。

<svg viewBox="0 0 760 440" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="发送方连续发出 seq 1 到 5，seq 2 在路上丢了；接收方收到 1 回 ack 2，之后收到 3、4、5 每次都只能回 ack 2，形成 3 个重复 ACK；发送方收到第 3 个重复 ACK 后立刻重传 seq 2，接收方补齐后一次确认到 ack 6" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .rl1bg  { fill: #fbfaf7; }
    .rl1ax  { stroke: #6b6558; stroke-width: 2; fill: none; }
    .rl1d   { stroke: #2f6f9f; stroke-width: 1.5; fill: none; }
    .rl1a   { stroke: #6f8f3f; stroke-width: 1.5; fill: none; }
    .rl1rt  { stroke: #bc4c00; stroke-width: 2; fill: none; }
    .rl1x   { stroke: #cf222e; stroke-width: 2.2; fill: none; }
    .rl1ink { fill: #1c1b18; font-size: 12.5px; }
    .rl1mut { fill: #6b6558; font-size: 12px; }
    .rl1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .rl1red { fill: #cf222e; font-size: 12px; }
    .rl1org { fill: #bc4c00; font-size: 12.5px; }
    .rl1hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1ax { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1d { stroke: #6cb6e8; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1a { stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1rt { stroke: #f0883e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1x { stroke: #ff7b72; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1ink, :root:is([data-theme="dark"], [data-theme="black"]) .rl1ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1red { fill: #ff7b72; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1org { fill: #f0883e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl1hd { fill: #a19caf; }
  </style>
  <defs><marker id="rl1m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="rl1hd"/></marker></defs>
  <rect class="rl1bg" x="0" y="0" width="760" height="440" rx="10"/>
  <text class="rl1ttl" x="150" y="40" text-anchor="middle">发送方</text>
  <text class="rl1ttl" x="610" y="40" text-anchor="middle">接收方</text>
  <path class="rl1ax" d="M150,52 L150,384"/>
  <path class="rl1ax" d="M610,52 L610,384"/>
  <path class="rl1d" d="M150,70 L608,120" marker-end="url(#rl1m)"/>
  <path class="rl1d" d="M150,95 L380,120"/>
  <path class="rl1x" d="M382,114 L394,126 M394,114 L382,126"/>
  <text class="rl1red" x="400" y="113">丢了</text>
  <path class="rl1d" d="M150,120 L608,170" marker-end="url(#rl1m)"/>
  <path class="rl1d" d="M150,145 L608,195" marker-end="url(#rl1m)"/>
  <path class="rl1d" d="M150,170 L608,220" marker-end="url(#rl1m)"/>
  <path class="rl1a" d="M610,120 L152,170" marker-end="url(#rl1m)"/>
  <path class="rl1a" d="M610,170 L152,220" marker-end="url(#rl1m)"/>
  <path class="rl1a" d="M610,195 L152,245" marker-end="url(#rl1m)"/>
  <path class="rl1a" d="M610,220 L152,270" marker-end="url(#rl1m)"/>
  <path class="rl1rt" d="M150,270 L608,320" marker-end="url(#rl1m)"/>
  <path class="rl1a" d="M610,320 L152,370" marker-end="url(#rl1m)"/>
  <text class="rl1ink" x="140" y="74" text-anchor="end">seq 1</text>
  <text class="rl1ink" x="140" y="99" text-anchor="end">seq 2</text>
  <text class="rl1ink" x="140" y="124" text-anchor="end">seq 3</text>
  <text class="rl1ink" x="140" y="149" text-anchor="end">seq 4</text>
  <text class="rl1ink" x="140" y="174" text-anchor="end">seq 5</text>
  <text class="rl1org" x="140" y="274" text-anchor="end">重传 seq 2</text>
  <text class="rl1ink" x="620" y="124">ack 2</text>
  <text class="rl1ink" x="620" y="174">ack 2（重复 1）</text>
  <text class="rl1ink" x="620" y="199">ack 2（重复 2）</text>
  <text class="rl1ink" x="620" y="224">ack 2（重复 3）</text>
  <text class="rl1ink" x="620" y="324">ack 6</text>
  <text class="rl1mut" x="24" y="408">seq 3、4、5 先到了，接收方先存着，但确认号只能停在缺口 2：每来一段，就是一个重复的 ack 2。</text>
  <text class="rl1mut" x="24" y="428">发送方收到第 3 个重复 ACK，不等超时就重传 seq 2；缺口补上，接收方一次确认到 6。</text>
</svg>

为什么是 3 个而不是 1 个：一两个重复 ACK 也可能只是乱序，晚到的那段过一会儿就来了，马上重发是浪费；连着 3 个，丢包的可能性就大多了。**快速重传让发送方在大约一个 RTT 内发现丢包，不用干等 RTO。**

### 2.4 SACK：告诉对方缺的是哪几段 {#sack}

累积确认只能说“2 之前都收到了”，说不出 3、4、5 其实也到了。发送方要是不知道，可能把 2 之后的都重发一遍。SACK（选择确认）是握手时协商的选项，开了以后，ACK 里可以附上“我还收到了哪几段”，发送方就只补真正缺的那段。Linux 默认开着。

## 3. 流量控制：别把对方的缓冲区塞爆

### 3.1 接收窗口 rwnd：对方还装得下多少 {#rwnd}

接收方收到的数据先放在 socket 的接收缓冲区里，等程序 `recv` 取走（[IO 地图](/maps/io-map.zh.html#recv)上那一格）。程序读得慢，缓冲区就会满，再收只能丢。所以接收方在每个 ACK 里带上窗口字段 `rwnd`：缓冲区里还空着多少字节。发送方保证“已发出、还没被确认”的数据不超过这个数。

发送方这边可以把字节流看成一条带子，分成四段：已经确认的、发出去还没确认的、窗口里还能发的、窗口外暂时不能发的。中间两段合起来就是发送窗口。

<svg viewBox="0 0 760 230" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="发送方的字节流分成四段：已发送且已确认、已发送等确认、在窗口里还能发、在窗口外暂时不能发；中间两段合起来是发送窗口，大小为 rwnd 和 cwnd 中较小的那个；收到确认后窗口左边界右移，窗口变大时右边界右移" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .rl0bg  { fill: #fbfaf7; }
    .rl0ok  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .rl0fly { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .rl0can { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.2; }
    .rl0no  { fill: #ffffff; stroke: #b9c2cc; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .rl0ink { fill: #1c1b18; font-size: 12.5px; }
    .rl0mut { fill: #6b6558; font-size: 12px; }
    .rl0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .rl0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0ok { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0fly { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0can { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0no { fill: #17161b; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0ink, :root:is([data-theme="dark"], [data-theme="black"]) .rl0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl0ln { stroke: #a19caf; }
  </style>
  <rect class="rl0bg" x="0" y="0" width="760" height="230" rx="10"/>
  <path class="rl0ln" d="M200,64 L200,56 L520,56 L520,64"/>
  <text class="rl0ttl" x="360" y="46" text-anchor="middle">发送窗口 = min(rwnd, cwnd)</text>
  <rect class="rl0ok" x="40" y="74" width="160" height="44"/>
  <rect class="rl0fly" x="200" y="74" width="160" height="44"/>
  <rect class="rl0can" x="360" y="74" width="160" height="44"/>
  <rect class="rl0no" x="520" y="74" width="200" height="44"/>
  <text class="rl0ink" x="120" y="101" text-anchor="middle">字节 1–400</text>
  <text class="rl0ink" x="280" y="101" text-anchor="middle">401–800</text>
  <text class="rl0ink" x="440" y="101" text-anchor="middle">801–1200</text>
  <text class="rl0ink" x="620" y="101" text-anchor="middle">1201 以后</text>
  <text class="rl0mut" x="120" y="140" text-anchor="middle">已发出，已确认</text>
  <text class="rl0mut" x="280" y="140" text-anchor="middle">已发出，等确认</text>
  <text class="rl0mut" x="440" y="140" text-anchor="middle">窗口里，还能发</text>
  <text class="rl0mut" x="620" y="140" text-anchor="middle">窗口外，先不能发</text>
  <text class="rl0mut" x="200" y="164" text-anchor="middle">↑ 左边界：最早没确认的字节</text>
  <text class="rl0mut" x="24" y="196">收到确认，左边界右移；rwnd 或 cwnd 变大，右边界右移。窗口整体往右滑，所以叫滑动窗口。</text>
  <text class="rl0mut" x="24" y="216">“已发出，等确认”这段的数据还得留在发送缓冲区里：万一要重传，得有东西可发。</text>
</svg>

### 3.2 零窗口和坚持定时器 {#zero-window}

接收方的程序一直不读，缓冲区满了，它回的 ACK 里 `rwnd = 0`，发送方停下来。之后程序读走了数据，接收方会发一个窗口更新的 ACK；可这个 ACK 不带数据，丢了也没人重传，两边就会互相干等：发送方等窗口打开，接收方等数据。为了打破这个僵局，发送方收到零窗口后会启动坚持定时器（persist timer），定期发一个很小的探测报文，逼对方回一个带当前窗口的 ACK。**流量控制管的是接收方的缓冲区，和网络堵不堵无关；网络的事归下一节的拥塞控制。**

### 3.3 窗口要多大才跑得满：带宽时延积 {#bdp}

发送方一个 RTT 里最多只能发出一个窗口的数据，所以一条连接的吞吐上限是 窗口 ÷ RTT。要跑满带宽，窗口至少要等于带宽乘 RTT，叫带宽时延积（BDP）：

$$
\text{BDP} = 1\ \text{Gbit/s} \times 20\ \text{ms} = 125\ \text{MB/s} \times 0.02\ \text{s} = 2.5\ \text{MB}
$$

TCP 首部里的窗口字段只有 16 位，最大 64 KiB，远不够。所以握手时可以协商窗口扩大选项（window scale），把这个字段左移若干位再用，最多到 1 GiB（握手里协商了哪些选项，见 [TCP 状态 1.6](/zh/ref/tcp-states/#handshake-options)）。Linux 会按 `net.ipv4.tcp_rmem` 自动调接收缓冲区，一般不用手动设；手动 `setsockopt(SO_RCVBUF)` 反而会关掉这种自动调整。

## 4. 拥塞控制：别把网络塞爆

### 4.1 拥塞窗口 cwnd：发送方自己估的 {#cwnd}

接收方的缓冲区够大，不代表路上的网络扛得住。所有连接都按对方的 `rwnd` 全速发，中间路由器的队列就会排满、丢包，大家一起重传，网络越重传越堵。所以发送方还要自己维护一个拥塞窗口 `cwnd`，估计网络此刻能承受多少在途数据。没人告诉它网络的容量，它只能试探：没丢包就慢慢加，丢了包就认为堵了、往回减。实际能发的是两个窗口里小的那个：

$$
\text{发送窗口} = \min(\text{rwnd},\ \text{cwnd})
$$

**rwnd 是接收方说的，cwnd 是发送方自己猜的；流量控制保护对方的缓冲区，拥塞控制保护中间的网络。**

### 4.2 慢启动和拥塞避免 {#slow-start}

新连接不知道网络能承受多少，`cwnd` 从一个小值开始，Linux 上是 10 个 MSS（一个 MSS 在以太网上约 1460 字节）。每收到一个确认，`cwnd` 加 1 个 MSS；一个 RTT 里整个窗口都被确认，窗口就翻了一倍。这叫慢启动，名字里的“慢”指的是起点小，涨起来其实是指数级的。

涨到慢启动阈值 `ssthresh` 以后，改成每个 RTT 只加 1 个 MSS，叫拥塞避免：离上次出问题的地方近了，小心地往上试。

<svg viewBox="0 0 760 410" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="cwnd 随时间变化：慢启动阶段每个 RTT 翻倍，到 ssthresh 32 后改为每个 RTT 加 1；收到 3 个重复 ACK 时 ssthresh 和 cwnd 都减半到 19，继续线性增长；超时时 ssthresh 变成 11，cwnd 回到 1 重新慢启动" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .rl2bg  { fill: #fbfaf7; }
    .rl2ax  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .rl2cw  { stroke: #bc4c00; stroke-width: 2.4; fill: none; stroke-linejoin: round; }
    .rl2th  { stroke: #6b6558; stroke-width: 1.2; fill: none; stroke-dasharray: 5 4; }
    .rl2ink { fill: #1c1b18; font-size: 12.5px; }
    .rl2mut { fill: #6b6558; font-size: 12px; }
    .rl2org { fill: #bc4c00; font-size: 12.5px; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2ax { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2cw { stroke: #f0883e; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2th { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2ink { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .rl2org { fill: #f0883e; }
  </style>
  <rect class="rl2bg" x="0" y="0" width="760" height="410" rx="10"/>
  <path class="rl2ax" d="M70,24 L70,330 L736,330"/>
  <text class="rl2mut" x="76" y="20">cwnd（MSS）</text>
  <text class="rl2mut" x="736" y="350" text-anchor="end">时间（RTT）</text>
  <text class="rl2mut" x="62" y="259" text-anchor="end">10</text>
  <text class="rl2mut" x="62" y="184" text-anchor="end">20</text>
  <text class="rl2mut" x="62" y="109" text-anchor="end">30</text>
  <text class="rl2mut" x="62" y="34" text-anchor="end">40</text>
  <path class="rl2th" d="M70,90 L400,90"/>
  <path class="rl2th" d="M400,187.5 L520,187.5"/>
  <path class="rl2th" d="M520,247.5 L730,247.5"/>
  <path class="rl2cw" d="M70,322.5 L100,315 L130,300 L160,270 L190,210 L220,90 L250,82.5 L280,75 L310,67.5 L340,60 L370,52.5 L400,45 L430,187.5 L460,180 L490,172.5 L520,165 L550,322.5 L580,315 L610,300 L640,270 L670,247.5 L700,240 L730,232.5"/>
  <text class="rl2mut" x="74" y="84">ssthresh = 32</text>
  <text class="rl2org" x="228" y="150">← 慢启动：每个 RTT 翻倍</text>
  <text class="rl2org" x="250" y="30">拥塞避免：每个 RTT 加 1</text>
  <text class="rl2org" x="436" y="130">3 个重复 ACK：减半</text>
  <text class="rl2mut" x="436" y="204">ssthresh = 19</text>
  <text class="rl2org" x="556" y="230">超时：回到 1 重新慢启动</text>
  <text class="rl2mut" x="736" y="286" text-anchor="end">ssthresh = 11</text>
  <text class="rl2mut" x="24" y="374">图里 cwnd 从 1 开始，好看清翻倍；Linux 实际从 10 个 MSS 开始。减半是 Reno 的做法，Linux 默认的 CUBIC 乘 0.7。</text>
  <text class="rl2mut" x="24" y="394">两种丢包的处理不一样：还能收到重复 ACK，说明网络还通，减半就行；超时说明可能整条路都堵死了，退回 1。</text>
</svg>

### 4.3 丢包以后：两种信号，两种力度 {#fast-recovery}

发送方把丢包当成网络拥塞的信号，但两种丢包说明的事不一样。收到 3 个重复 ACK，说明后面的包还在不断到达，网络只是有点挤：把 `ssthresh` 设成当前 `cwnd` 的一半，`cwnd` 也降到这里，直接进拥塞避免，不回到起点，这叫快速恢复。等到超时才发现丢包，说明连重复 ACK 都回不来，可能路已经堵死了：`ssthresh` 设成一半，`cwnd` 退回 1，重新慢启动。**加性增、乘性减（AIMD）让多条连接共用一段瓶颈链路时，各自的窗口会慢慢收敛到差不多的份额。**

### 4.4 CUBIC 和 BBR：Linux 上实际用的 {#cubic-bbr}

上面讲的是经典的 Reno。Linux 从 2.6.19 起默认用 CUBIC：丢包时乘 0.7 而不是减半，恢复时窗口按时间的三次函数增长，先快速回到上次丢包的位置附近，在那里放慢试探，过了以后再加速，适合带宽大、RTT 长的链路。BBR 换了一个思路：不把丢包当拥塞信号，而是持续测量瓶颈带宽和最小 RTT，按两者的乘积来控制在途数据量，在有随机丢包的链路上（比如无线）吞吐比 CUBIC 高。用哪个由 `net.ipv4.tcp_congestion_control` 决定；`ss -ti` 能看到每条连接当前的 `cwnd`、`ssthresh`、`rtt` 和用的算法。

## 5. 小包：Nagle 和延迟确认

### 5.1 Nagle 算法：小包攒一攒再发 {#nagle}

程序一次只写几个字节（比如交互式终端里每敲一个键），每个都单独发出去，40 字节的首部只带 1 字节数据，网络上全是小包。Nagle 算法的规则是：只要还有一个没被确认的小包在路上，新的小数据就先攒在缓冲区里，等那个确认回来，或者攒够一个 MSS，再一起发。

### 5.2 延迟确认：确认也攒一攒 {#delayed-ack}

接收方这边也在省：收到数据后不马上回 ACK，等一小会儿，看程序会不会很快写回复，好把 ACK 顺带在回复的数据报文里；或者等第二个数据报文到了，一次确认两个。Linux 上这个等待最短 40 ms。

### 5.3 两个凑在一起：40 ms 的卡顿 {#nagle-delayed-ack}

单看哪个都合理，凑在一起就出问题。典型场景是客户端把一个请求分两次写：先写请求头，再写请求体，然后等服务端回复。

1. 请求头立刻发出去了，这时路上没有未确认的包。
2. 请求体是小数据，路上有一个未确认的请求头，Nagle 让它等。
3. 服务端收到请求头，请求不完整，程序不会回复；内核也就没有可以顺带 ACK 的数据，延迟确认让 ACK 等 40 ms。
4. 40 ms 后 ACK 才回来，请求体这才发出。

每个请求都平白多出 40 ms。**两种省法单独都对，合在一起变成“我等你确认，你等我数据”。** 解决办法有三种：把一个请求一次写完（拼好缓冲区，或者用 `writev` 一次交多段）；对请求-响应型的协议关掉 Nagle：

```cpp
int one = 1;
setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);   // 小包也立刻发
```

或者反过来，要发一大批小数据时用 `TCP_CORK` 先塞住、写完再拔掉，让内核攒成满包再发。关掉 Nagle 以后，程序自己要注意别一次只写几个字节。

## 6. 字节流：粘包、拆包和消息边界

### 6.1 为什么会“粘包” {#sticky-packets}

TCP 交给程序的是字节流，不保留每次 `send` 的边界。客户端调两次 `send`，各发 100 字节，服务端一次 `recv` 可能读到 200 字节（两条“粘”在一起），也可能先读到 150、再读到 50（一条被“拆”开）。原因不止一个：Nagle 会把两次小写合成一个报文；发送缓冲区里的数据按 MSS 切段，切口不管你的消息在哪结束；接收方的数据先进接收缓冲区，程序什么时候读、一次读多少，读到的就是缓冲区里当时有的。**TCP 从来没有“包”的概念给程序，粘包不是 bug，是字节流的本来面目；消息边界要应用层自己定。** UDP 没有这个问题，一次 `recvfrom` 就是对面一次 `sendto` 的整条数据报。

### 6.2 定边界：长度前缀或分隔符 {#framing}

常见的定法有两种。文本协议用分隔符：HTTP 的请求头以空行 `\r\n\r\n` 结束，Redis 的命令以 `\r\n` 分行，代价是正文里出现分隔符要转义。二进制协议用长度前缀：每条消息前面放一个固定长度的字段，写明后面的正文有多长。接收方的做法是：收到多少就攒多少，攒够一条就切一条，剩下的半截留着等下一次。

```cpp
// 消息格式：4 字节大端长度 + 正文
std::string encode(const std::string& msg) {
    uint32_t n = msg.size();
    char h[4] = {char(n >> 24), char(n >> 16), char(n >> 8), char(n)};
    return std::string(h, 4) + msg;
}

class FrameDecoder {
public:
    // recv 收到多少字节就喂多少，返回这次凑齐的完整消息
    std::vector<std::string> feed(const char* data, size_t n) {
        buf_.append(data, n);
        std::vector<std::string> out;
        size_t pos = 0;
        while (buf_.size() - pos >= 4) {                   // 长度字段到齐了
            auto p = reinterpret_cast<const unsigned char*>(buf_.data() + pos);
            uint32_t len = uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
            if (len > kMaxFrame) throw std::runtime_error("frame too large");
            if (buf_.size() - pos - 4 < len) break;        // 正文没到齐：留着等下一次
            out.emplace_back(buf_, pos + 4, len);
            pos += 4 + len;
        }
        buf_.erase(0, pos);                                // 用掉的删掉，半截消息留在 buf_ 里
        return out;
    }
private:
    static constexpr uint32_t kMaxFrame = 16u << 20;       // 防止坏数据让它分配几 GiB
    std::string buf_;
};
```

用的时候，`recv` 读到多少就喂多少，不关心这一次读到的是半条、一条还是好几条：

```cpp
char buf[4096];
ssize_t r;
while ((r = recv(fd, buf, sizeof buf, 0)) > 0)
    for (auto& msg : dec.feed(buf, r))
        handle(msg);
```

长度字段用固定的字节序（这里是大端，也就是网络字节序），两端的 CPU 字节序不同也能对上。上限检查不能省：长度字段是对面发来的，一个坏掉或恶意的值可能是 4 GiB。这段解码器在本机用 GCC 16.2 跑过：把 4 条消息（含一条空消息、一条 300 字节）编码后，按每次 1、2、3、7、64、1000 字节切开喂进去，解出来的都和原来一致。

## 7. 连接还活着吗：keepalive 和心跳

### 7.1 TCP keepalive：内核替你探一探 {#keepalive}

一条连接上长时间没有数据，两端都不知道对面是不是还在：对方机器断电、网线被拔，不会发 FIN，这边的连接就一直以为自己是 ESTABLISHED。TCP keepalive 是内核的一个选项：连接空闲一段时间后，发一个探测报文，对方回了说明还在，连续几次没回就判定断开，程序的下一次读写会报错。Linux 的默认参数很保守：空闲 7200 s 才开始探，每 75 s 一次，9 次不回才算断，前后两个多小时。要用就按连接把它调短：

```cpp
int on = 1, idle = 30, intvl = 5, cnt = 3;
setsockopt(fd, SOL_SOCKET,  SO_KEEPALIVE,  &on,    sizeof on);
setsockopt(fd, IPPROTO_TCP, TCP_KEEPIDLE,  &idle,  sizeof idle);   // 空闲 30 s 开始探
setsockopt(fd, IPPROTO_TCP, TCP_KEEPINTVL, &intvl, sizeof intvl);  // 每 5 s 一次
setsockopt(fd, IPPROTO_TCP, TCP_KEEPCNT,   &cnt,   sizeof cnt);    // 3 次不回就断
```

### 7.2 为什么还要应用层心跳 {#heartbeat}

keepalive 只能证明对方的内核还在回 ACK，证明不了对方的程序还在干活：进程死锁了、卡在某个调用里，内核照样替它回探测。另外，中间的 NAT 和负载均衡器会把空闲几分钟的连接从表里删掉，比默认的 2 小时短得多。所以长连接的服务（推送、即时通讯、数据库连接池）一般自己定一个心跳：每隔几秒到几十秒发一条应用层的 ping，对面的程序回 pong，几次收不到就主动断开重连。**keepalive 检查的是连接，心跳检查的是对面的程序；后者还顺便让中间设备看到流量，不把连接当成闲置。**
