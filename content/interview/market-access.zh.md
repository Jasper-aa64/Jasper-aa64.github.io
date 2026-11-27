---
title: "IV. 行情接入速览：券商柜台、行情源、“接入经验”分别指什么"
date: 2026-11-27T00:00:00+08:00
slug: "market-access"
description: "行情接入长什么样：HFT 直连和数据商 SDK 两条路的架构图；HFT 热路径一个线程从收包跑到报单，配一份能跑的简化 feed handler，以及行情软件公司和 HFT 的异同。面试和招聘里常说的券商柜台、行情接入、柜台对接、交易所直连分别指什么。行情是从交易所往里收数据，柜台是券商替你往交易所报单的那一层；两类柜台、交易网关、行情从哪几种渠道来、各种“接入经验”被问时会问到什么。"
weight: 3
toc: true
---

> 这几个词的本质：行情是从交易所往里收的数据，柜台是券商替你往交易所报单的那一层。

## 概览 {#overview}

- **行情接入长什么样（[第 1 节](#shape)）**：交易所发出的消息，要有人收包、解码、按序号补齐，这一层叫 feed handler；之后转成统一结构，送给策略、客户或 App。
  - HFT 在托管机房里自己写 feed handler。
  - 用数据商 SDK 时，这层是数据商做的，回调交给你的已经是结构体。
- **HFT 那套（[第 2 节](#hft)）**：一个绑核的线程忙轮询，从收包、解码、查序号一路跑到订单簿、策略、报单，中间不换线程；行情软件公司前半段一样，后半段拼的是推给大量用户。
- **两条流，方向相反**：
  - 行情：从交易所流向你。
  - 交易：委托从你经券商柜台流向交易所，回报再原路回来。
- **券商柜台是券商的交易核心系统**：管客户的账户、资金、持仓，下单前做风控，再把委托报给交易所。
- **柜台分两类**：
  - 集中交易柜台（普通柜台）：服务全体经纪客户，手机 App 下的单最后都落到这里，毫秒级。
  - 极速柜台：面向量化机构，放在交易所的托管机房里，只留基本的交易功能，微秒级。
- **“行情接入经验”指收行情**：用 SDK 收，或者直连交易所的行情网关收，最后变成自己系统里统一的结构。
- **“柜台对接经验”指下单**：调柜台的 API 报单、撤单、查询，处理异步回报，维护每笔订单的状态。
- **我的经验只在行情这一侧**：用数据商的 SDK 收沪深 Level-2，没接过柜台（[行情接入和 SPMC 广播环](/zh/interview/md-feed-spmc/)）。

## 1. 行情接入长什么样：完整架构和两条路 {#shape}

### 1.1 完整的架构：从交易所到用行情的程序 {#full}

<svg viewBox="0 0 680 620" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="完整的行情接入架构，分四层。第一层交易所：撮合主机产生每笔委托和成交，行情系统按频道编号，用组播发出，缺的用 TCP 补。第二层是直连交易所的接入方的 feed handler：收包（组播或 TCP）、解码（分帧、大端、FAST）、查序号和补缺（按频道，去重传端口要），这三步是前半段；然后转统一结构，从这里起是后半段。HFT、券商、数据商、信息商都在这一层。第三层是转成统一结构之后送到哪：同一台机器上写广播环给订单簿、策略、落盘；数据商和券商经专线转发给客户；信息商经行情服务器推给 App。第四层是客户进程：SDK 收包、解码、续传，相当于替客户做了前半段；回调交出结构体，客户再转统一结构，写广播环给落盘和策略，这是客户自己写的后半段。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .fa1bg  { fill: #fbfaf7; }
    .fa1bd  { fill: #f4f3ef; stroke: #b9b6ac; stroke-width: 1; stroke-dasharray: 5 4; }
    .fa1fr  { fill: #ffffff; stroke: #8a8f98; stroke-width: 1.3; }
    .fa1bk  { fill: #e6f2ec; stroke: #5f9a80; stroke-width: 1.4; }
    .fa1ink { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .fa1sm  { fill: #4a463e; font-size: 11.5px; }
    .fa1hd  { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .fa1mut { fill: #6b6558; font-size: 12px; }
    .fa1ar  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .fa1hh  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1bd { fill: #1f1e24; stroke: #4a4855; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1fr { fill: #1d1c22; stroke: #6f7380; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1bk { fill: #1c2a24; stroke: #5f9a80; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1ink, :root:is([data-theme="dark"], [data-theme="black"]) .fa1hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1sm, :root:is([data-theme="dark"], [data-theme="black"]) .fa1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1ar { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .fa1hh { fill: #a19caf; }
  </style>
  <defs><marker id="fa1ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="fa1hh"/></marker></defs>
  <rect class="fa1bg" x="0" y="0" width="680" height="620" rx="10"/>

  <rect class="fa1bd" x="20" y="14" width="640" height="112" rx="12"/>
  <text class="fa1hd" x="36" y="36">① 交易所</text>
  <rect class="fa1fr" x="50" y="52" width="240" height="56" rx="8"/>
  <text class="fa1ink" x="170" y="75" text-anchor="middle">撮合主机</text>
  <text class="fa1sm" x="170" y="95" text-anchor="middle">产生每笔委托、每笔成交</text>
  <path class="fa1ar" d="M290 80 L348 80" marker-end="url(#fa1ah)"/>
  <rect class="fa1fr" x="350" y="52" width="280" height="56" rx="8"/>
  <text class="fa1ink" x="490" y="75" text-anchor="middle">行情系统</text>
  <text class="fa1sm" x="490" y="95" text-anchor="middle">按频道编号，组播发出，TCP 补</text>


  <rect class="fa1bd" x="20" y="150" width="640" height="122" rx="12"/>
  <text class="fa1hd" x="36" y="172">② 直连交易所的接入方：feed handler</text>
  <text class="fa1mut" x="644" y="265" text-anchor="end">HFT、券商、数据商、信息商都在这层</text>
  <rect class="fa1fr" x="41" y="192" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="108" y="215" text-anchor="middle">收包</text>
  <text class="fa1sm" x="108" y="235" text-anchor="middle">组播或 TCP</text>
  <path class="fa1ar" d="M176 220 L192 220" marker-end="url(#fa1ah)"/>
  <rect class="fa1fr" x="194" y="192" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="261" y="215" text-anchor="middle">解码</text>
  <text class="fa1sm" x="261" y="235" text-anchor="middle">分帧、大端、FAST</text>
  <path class="fa1ar" d="M329 220 L345 220" marker-end="url(#fa1ah)"/>
  <rect class="fa1fr" x="347" y="192" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="414" y="215" text-anchor="middle">查序号、补缺</text>
  <text class="fa1sm" x="414" y="235" text-anchor="middle">按频道，去重传端口</text>
  <path class="fa1ar" d="M482 220 L498 220" marker-end="url(#fa1ah)"/>
  <rect class="fa1bk" x="500" y="192" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="567" y="215" text-anchor="middle">转统一结构</text>
  <text class="fa1sm" x="567" y="235" text-anchor="middle">价格、代码、字段对齐</text>


  <rect class="fa1bd" x="20" y="300" width="640" height="122" rx="12"/>
  <rect class="fa1bk" x="40" y="326" width="190" height="56" rx="8"/>
  <text class="fa1ink" x="135" y="349" text-anchor="middle">同一台机器：广播环</text>
  <text class="fa1sm" x="135" y="369" text-anchor="middle">订单簿、策略、落盘来读</text>
  <rect class="fa1bk" x="245" y="326" width="190" height="56" rx="8"/>
  <text class="fa1ink" x="340" y="349" text-anchor="middle">转发给客户</text>
  <text class="fa1sm" x="340" y="369" text-anchor="middle">数据商、券商，走专线</text>
  <rect class="fa1bk" x="450" y="326" width="190" height="56" rx="8"/>
  <text class="fa1ink" x="545" y="349" text-anchor="middle">推给用户</text>
  <text class="fa1sm" x="545" y="369" text-anchor="middle">信息商：行情服务器 → App</text>
  <text class="fa1hd" x="36" y="408">③ 转成统一结构之后，送到哪</text>


  <rect class="fa1bd" x="20" y="450" width="640" height="122" rx="12"/>
  <rect class="fa1fr" x="41" y="476" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="108" y="499" text-anchor="middle">SDK</text>
  <text class="fa1sm" x="108" y="519" text-anchor="middle">收包、解码、续传</text>
  <path class="fa1ar" d="M176 504 L192 504" marker-end="url(#fa1ah)"/>
  <rect class="fa1bk" x="194" y="476" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="261" y="499" text-anchor="middle">回调</text>
  <text class="fa1sm" x="261" y="519" text-anchor="middle">SDK 的线程交出结构体</text>
  <path class="fa1ar" d="M329 504 L345 504" marker-end="url(#fa1ah)"/>
  <rect class="fa1bk" x="347" y="476" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="414" y="499" text-anchor="middle">转统一结构</text>
  <text class="fa1sm" x="414" y="519" text-anchor="middle">厂商字段、单位对齐</text>
  <path class="fa1ar" d="M482 504 L498 504" marker-end="url(#fa1ah)"/>
  <rect class="fa1bk" x="500" y="476" width="135" height="56" rx="8"/>
  <text class="fa1ink" x="567" y="499" text-anchor="middle">写广播环</text>
  <text class="fa1sm" x="567" y="519" text-anchor="middle">落盘、策略来读</text>
  <text class="fa1hd" x="36" y="558">④ 客户的进程：SDK 做了前半段，后半段自己写</text>

  <text class="fa1mut" x="340" y="600" text-anchor="middle">白框是前半段（收到完整、按顺序的消息）；绿框是后半段（转成自己的结构，送给用的人）</text>

  <path class="fa1ar" d="M490 108 L490 190" marker-end="url(#fa1ah)"/>
  <path class="fa1ar" d="M567 248 L567 288 L135 288"/>
  <path class="fa1ar" d="M135 288 L135 324" marker-end="url(#fa1ah)"/>
  <path class="fa1ar" d="M340 288 L340 324" marker-end="url(#fa1ah)"/>
  <path class="fa1ar" d="M545 288 L545 324" marker-end="url(#fa1ah)"/>
  <path class="fa1ar" d="M340 382 L340 432 L108 432 L108 474" marker-end="url(#fa1ah)"/>
</svg>

- **① 交易所**：撮合主机每产生一笔委托、一笔成交，行情系统就打包成一条消息，按频道编号发出去；组播发实时数据，缺了的用 TCP 补。
- **② 直连交易所的接入方**：机器放在交易所的机房或托管机房里，自己写 feed handler。前三步得到完整、按顺序的消息，是前半段；转成自己的统一结构以后是后半段。
- **③ 后半段送到哪，决定了你是谁**：
  - 交给同机的订单簿、策略，是 HFT。
  - 转发给客户，是数据商、券商。
  - 推给大量 App 用户，是做行情软件的信息商。
- **④ 客户的进程**：从数据商或券商收行情的一方，进程里跑的是对方给的 SDK。SDK 替你做了收包、解码、续传，相当于前半段；回调交出厂商的结构体以后，转统一结构、交给下游，是你自己写的后半段。
- **④ 和 ② 是同一个形状**：都是“拿到完整的消息 → 转统一结构 → 分给下游”，只是 ② 自己解交易所的协议，④ 让 SDK 解。

### 1.2 这些名字在哪一层 {#who}

| 名字 | 是什么 | 在图里哪一层 |
| --- | --- | --- |
| 上证信息、深证信息 | 交易所下属的信息公司，发布 Level-2，卖行情授权 | ① |
| 万得宏汇（TDF） | 数据商，万得旗下的行情系统，直连交易所，给机构客户实时行情 API（[万得](https://wind.com.cn/portal/en/WDS/marketdata.html)） | ② ③ 转发给客户；客户在 ④ 用它的 SDK |
| 国泰海通、开源证券这些券商 | 给自己的客户提供行情 SDK，常和极速柜台一起提供 | ② ③ 转发给客户；客户在 ④ |
| 恒生（NSQ 极速行情）、华锐、宽睿 | 系统厂商，把行情系统、柜台卖给券商，券商部署以后给自己的客户用 | 软件跑在券商的 ② ③；客户在 ④ 用券商给的 SDK |
| 中泰 XTP、华鑫奇点 | 券商自研的极速柜台，附带行情 API | 同上一行 |
| 做行情软件的信息商 | 直连交易所，加工后推给 App 用户 | ② ③ 推给用户 |
| HFT 公司 | 直连交易所，只给自己用 | ② ③ 同机 |

- **同一家公司可以在好几层**：数据商、券商在 ② 解交易所的协议，在 ③ 转发；它们的客户在 ④ 接 SDK。
- **从客户这边看，只分两种来源**：数据商的 SDK，或者券商给的 SDK（底下可能是券商自研的，也可能是恒生这类厂商的软件）。

### 1.3 两条路：HFT 直连和数据商 SDK {#path}

回调里拿到的一个 tick，就是交易所发出来的一条消息：一张快照，或者一笔逐笔委托、逐笔成交。它到你手里之前，已经有人收好、解码、按序号排好了。把 1.1 的图按“前半段谁做”拆成两条路：

<svg viewBox="0 0 680 540" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="行情接入的两条路。最上面是交易所，撮合后按频道编号发出行情。左边是 HFT 在托管机房里直连：网卡收组播（机器放在交易所旁，内核旁路），自己写的 feed handler（解码、按频道查序号、缺了补），订单簿重建（用逐笔还原每只股票的盘口），策略下单（同一台机器，全程几微秒）。右边是数据商的 SDK：数据商的 feed handler（它直连交易所，做左边那套），数据商转发（自己的协议，专线发给客户），你进程里的 SDK（收包、解码、断线续传），最后回调进入你的代码（统一结构、写环、落盘）。左边每一层都自己写；右边上三层是别人做好的，你从回调开始。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .mk1bg  { fill: #fbfaf7; }
    .mk1ex  { fill: #f1efe8; stroke: #8a8f98; stroke-width: 1.3; }
    .mk1lnA { fill: #f1eef6; stroke: #c3b9d6; stroke-width: 1; stroke-dasharray: 5 4; }
    .mk1lnB { fill: #eaf3ef; stroke: #9cc5b3; stroke-width: 1; stroke-dasharray: 5 4; }
    .mk1b   { fill: #ffffff; stroke: #8a8f98; stroke-width: 1.3; }
    .mk1me  { fill: #fbe7df; stroke: #c4673f; stroke-width: 1.8; }
    .mk1ink { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .mk1sm  { fill: #4a463e; font-size: 11.5px; }
    .mk1hd  { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .mk1mut { fill: #6b6558; font-size: 12px; }
    .mk1ar  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .mk1hh  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1ex { fill: #2a2925; stroke: #6f7380; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1lnA { fill: #23202b; stroke: #4c4560; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1lnB { fill: #1c2723; stroke: #3f5a4f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1b { fill: #1d1c22; stroke: #6f7380; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1me { fill: #3d261d; stroke: #d88a63; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1ink, :root:is([data-theme="dark"], [data-theme="black"]) .mk1hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1sm, :root:is([data-theme="dark"], [data-theme="black"]) .mk1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1ar { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .mk1hh { fill: #a19caf; }
  </style>
  <defs><marker id="mk1ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="mk1hh"/></marker></defs>
  <rect class="mk1bg" x="0" y="0" width="680" height="540" rx="10"/>

  <rect class="mk1ex" x="190" y="20" width="300" height="56" rx="8"/>
  <text class="mk1ink" x="340" y="43" text-anchor="middle">交易所</text>
  <text class="mk1sm" x="340" y="63" text-anchor="middle">撮合，按频道编号发出行情</text>
  <path class="mk1ar" d="M290 76 L200 106" marker-end="url(#mk1ah)"/>
  <path class="mk1ar" d="M390 76 L480 106" marker-end="url(#mk1ah)"/>

  <rect class="mk1lnA" x="30" y="110" width="300" height="366" rx="12"/>
  <text class="mk1hd" x="180" y="134" text-anchor="middle">HFT：托管机房里直连</text>
  <rect class="mk1lnB" x="350" y="110" width="300" height="366" rx="12"/>
  <text class="mk1hd" x="500" y="134" text-anchor="middle">数据商的 SDK（我实习用的）</text>

  <rect class="mk1b" x="50" y="150" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="180" y="173" text-anchor="middle">网卡收组播</text>
  <text class="mk1sm" x="180" y="193" text-anchor="middle">机器放在交易所旁，内核旁路</text>
  <path class="mk1ar" d="M180 206 L180 230" marker-end="url(#mk1ah)"/>
  <rect class="mk1b" x="50" y="234" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="180" y="257" text-anchor="middle">自己写的 feed handler</text>
  <text class="mk1sm" x="180" y="277" text-anchor="middle">解码、按频道查序号、缺了补</text>
  <path class="mk1ar" d="M180 290 L180 314" marker-end="url(#mk1ah)"/>
  <rect class="mk1b" x="50" y="318" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="180" y="341" text-anchor="middle">订单簿重建</text>
  <text class="mk1sm" x="180" y="361" text-anchor="middle">用逐笔还原每只股票的盘口</text>
  <path class="mk1ar" d="M180 374 L180 398" marker-end="url(#mk1ah)"/>
  <rect class="mk1b" x="50" y="402" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="180" y="425" text-anchor="middle">策略下单</text>
  <text class="mk1sm" x="180" y="445" text-anchor="middle">同一台机器，全程几微秒</text>

  <rect class="mk1b" x="370" y="150" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="500" y="173" text-anchor="middle">数据商的 feed handler</text>
  <text class="mk1sm" x="500" y="193" text-anchor="middle">它直连交易所，做左边那套</text>
  <path class="mk1ar" d="M500 206 L500 230" marker-end="url(#mk1ah)"/>
  <rect class="mk1b" x="370" y="234" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="500" y="257" text-anchor="middle">数据商转发</text>
  <text class="mk1sm" x="500" y="277" text-anchor="middle">自己的协议，专线发给客户</text>
  <path class="mk1ar" d="M500 290 L500 314" marker-end="url(#mk1ah)"/>
  <rect class="mk1b" x="370" y="318" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="500" y="341" text-anchor="middle">SDK（在你的进程里）</text>
  <text class="mk1sm" x="500" y="361" text-anchor="middle">收包、解码、断线续传</text>
  <path class="mk1ar" d="M500 374 L500 398" marker-end="url(#mk1ah)"/>
  <rect class="mk1me" x="370" y="402" width="260" height="56" rx="8"/>
  <text class="mk1ink" x="500" y="425" text-anchor="middle">回调 → 你的代码</text>
  <text class="mk1sm" x="500" y="445" text-anchor="middle">统一结构 → 写环 → 落盘</text>

  <text class="mk1mut" x="340" y="506" text-anchor="middle">左边每一层都自己写；右边上三层是别人做好的，你从回调开始（橙色框）</text>
</svg>

- **左边是 HFT 说的“行情接入”**：机器放进交易所的托管机房，网卡直接收交易所的组播，自己写 feed handler，后面紧接着订单簿和策略，从收到行情到报单全程几微秒。
- **右边是数据商 SDK 这条路**：数据商在它那边做了左边那套，再用自己的协议转发给客户；你进程里的 SDK 收包、解码、断线续传，回调交给你的已经是结构体，延迟在几十到几百微秒（[A 股行情 1.3](/zh/ref/a-share-market/#feed-path)）。
- **做行情软件的信息商在右边上面两个框的位置**：自己直连交易所做 feed handler，再分发出去，只是下游是大量 App 用户，不是机构。

### 1.4 feed handler 做的五件事 {#feed-handler}

真正意义上的“行情接入”就是这一层，按数据流的顺序：

1. **收包、切消息**：TCP 是字节流，一次可能收到半条或好几条，按消息头里的长度切；组播一个包里可能装好几条。
2. **解码**：按消息类型分派；字段是大端，要转字节序；上海的 Level-2 还要先解 FAST 编码。
3. **按频道查序号**：每个频道内序号连续，重复的丢掉，跳号说明丢了。
4. **缺了就补**：后到的先缓存，同时到交易所的重传端口要回缺的那段，补齐再按顺序放出去；快照不补，等下一张。
5. **转成统一结构，交给下游**：价格统一成定点整数，代码映射成下标，沪深的字段对齐；HFT 交给同机的订单簿和策略，数据商发给客户。

用 SDK 时，前四件是 SDK 和数据商做的；第五件里的“转统一结构、交给下游”是你做的。

### 1.5 两条路差在哪 {#compare}

| 项 | HFT 直连 | 数据商 SDK |
| --- | --- | --- |
| feed handler 谁写 | 自己 | 数据商；你只接 SDK |
| 机器在哪 | 交易所的托管机房 | 自己机房，经专线收数据商的推送 |
| 延迟 | 几微秒，再往下用 FPGA 解码 | 几十到几百微秒，抖动由厂商的库决定 |
| 你拿到的 | 网卡上的原始字节 | 回调里的结构体 |
| 要懂的 | 交易所协议、组播、重传、内核旁路 | SDK 的线程模型、字段口径、断线续传 |
| 面试里“行情接入”指 | 写 feed handler | 接 SDK 之后这一段：回调、统一结构、分发 |

### 1.6 我做的是哪一段 {#mine}

- **在 1.1 的图里是 ④ 的后半段**：用两家厂商的 SDK 收沪深 Level-2，一家是数据商的，一家是券商给的；回调里转成统一结构，经广播环交给另一个进程落盘（[行情接入和 SPMC 广播环](/zh/interview/md-feed-spmc/)）。前半段是 SDK 和对方的 ② 做的。
- **这一段要保证的**：
  - 不丢、不乱：整日回放核条数，断线续传前后核不丢不重。
  - 字段对：厂商头文件不全，拿真实行情逐个字段核。
  - 回调不堵：回调线程是 SDK 的，不在里面做 I/O。
- **被问到时先说边界**：整体结构清楚，实习里只做过回调之后这一段；行情用的是数据商的 SDK，没直连交易所（[2.6](#hft-say)）。

## 2. HFT 那套展开：一天怎么跑，代码长什么样 {#hft}

### 2.1 一天怎么跑 {#hft-day}

- **盘前**：
  - 起进程、绑核，订单簿和缓冲区一次性分配好，加载当天的代码表。
  - 连上行情的实时会话和重传会话、柜台的交易会话，各自登录。
  - 预热：把热路径的代码和数据先跑几遍，让它们进缓存。
- **盘中**：一个绑核的线程忙轮询，来一个包就从收包一路跑到策略；要报单，也在这个线程里编码发出去。落盘、监控在别的核上，经环拿数据，不挡热路径。
- **盘后**：对账；当天收到的原始包已经录成录像，用来回放复现问题、做回测。

### 2.2 热路径：一个线程从收包跑到报单 {#hft-hot}

<svg viewBox="0 0 680 390" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="HFT 行情热路径：一个绑核、忙轮询的线程里，依次是网卡组播包、收包（忙轮询、内核旁路）、分帧校验（按长度切、验校验和）、解码（大端转结构体）、查序号（跳号先缓存再去补）、订单簿（逐笔改盘口）、策略（算信号）、报单（编码发给柜台）。线程外面有三样：查序号缺号时找重传会话（TCP）补；订单簿之后写一份进广播环，给别的核上的落盘和监控；报单发往柜台和交易所。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .hf1bg  { fill: #fbfaf7; }
    .hf1th  { fill: #f1eef6; stroke: #c3b9d6; stroke-width: 1; stroke-dasharray: 5 4; }
    .hf1b   { fill: #ffffff; stroke: #8a8f98; stroke-width: 1.3; }
    .hf1o   { fill: #eaf3ef; stroke: #6f9f8a; stroke-width: 1.3; }
    .hf1ink { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .hf1sm  { fill: #4a463e; font-size: 11.5px; }
    .hf1hd  { fill: #1c1b18; font-size: 13.5px; font-weight: 700; }
    .hf1mut { fill: #6b6558; font-size: 12px; }
    .hf1ar  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .hf1ad  { stroke: #6b6558; stroke-width: 1.3; fill: none; stroke-dasharray: 5 4; }
    .hf1hh  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1th { fill: #23202b; stroke: #4c4560; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1b { fill: #1d1c22; stroke: #6f7380; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1o { fill: #1c2723; stroke: #5f8f7a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1ink, :root:is([data-theme="dark"], [data-theme="black"]) .hf1hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1sm, :root:is([data-theme="dark"], [data-theme="black"]) .hf1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1ar, :root:is([data-theme="dark"], [data-theme="black"]) .hf1ad { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .hf1hh { fill: #a19caf; }
  </style>
  <defs><marker id="hf1ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="hf1hh"/></marker></defs>
  <rect class="hf1bg" x="0" y="0" width="680" height="390" rx="10"/>
  <rect class="hf1th" x="20" y="20" width="640" height="232" rx="12"/>
  <text class="hf1hd" x="340" y="44" text-anchor="middle">一个绑核的线程，忙轮询，从收包跑到报单</text>

  <rect class="hf1b" x="41" y="64" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="106" y="85" text-anchor="middle">网卡</text>
  <text class="hf1sm" x="106" y="104" text-anchor="middle">交易所的组播包</text>
  <path class="hf1ar" d="M171 90 L195 90" marker-end="url(#hf1ah)"/>
  <rect class="hf1b" x="197" y="64" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="262" y="85" text-anchor="middle">收包</text>
  <text class="hf1sm" x="262" y="104" text-anchor="middle">忙轮询，内核旁路</text>
  <path class="hf1ar" d="M327 90 L351 90" marker-end="url(#hf1ah)"/>
  <rect class="hf1b" x="353" y="64" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="418" y="85" text-anchor="middle">分帧、校验</text>
  <text class="hf1sm" x="418" y="104" text-anchor="middle">按长度切，验校验和</text>
  <path class="hf1ar" d="M483 90 L507 90" marker-end="url(#hf1ah)"/>
  <rect class="hf1b" x="509" y="64" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="574" y="85" text-anchor="middle">解码</text>
  <text class="hf1sm" x="574" y="104" text-anchor="middle">大端 → 结构体</text>

  <path class="hf1ar" d="M574 116 L574 138 L106 138 L106 170" marker-end="url(#hf1ah)"/>

  <rect class="hf1b" x="41" y="172" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="106" y="193" text-anchor="middle">查序号</text>
  <text class="hf1sm" x="106" y="212" text-anchor="middle">跳号先缓存，去补</text>
  <path class="hf1ar" d="M171 198 L195 198" marker-end="url(#hf1ah)"/>
  <rect class="hf1b" x="197" y="172" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="262" y="193" text-anchor="middle">订单簿</text>
  <text class="hf1sm" x="262" y="212" text-anchor="middle">逐笔改盘口</text>
  <path class="hf1ar" d="M327 198 L351 198" marker-end="url(#hf1ah)"/>
  <rect class="hf1b" x="353" y="172" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="418" y="193" text-anchor="middle">策略</text>
  <text class="hf1sm" x="418" y="212" text-anchor="middle">算信号，决定报不报</text>
  <path class="hf1ar" d="M483 198 L507 198" marker-end="url(#hf1ah)"/>
  <rect class="hf1b" x="509" y="172" width="130" height="52" rx="8"/>
  <text class="hf1ink" x="574" y="193" text-anchor="middle">报单</text>
  <text class="hf1sm" x="574" y="212" text-anchor="middle">编码，发给柜台</text>

  <path class="hf1ad" d="M106 224 L106 278" marker-end="url(#hf1ah)"/>
  <path class="hf1ad" d="M262 224 L340 278" marker-end="url(#hf1ah)"/>
  <path class="hf1ar" d="M574 224 L574 278" marker-end="url(#hf1ah)"/>
  <rect class="hf1o" x="31" y="280" width="150" height="52" rx="8"/>
  <text class="hf1ink" x="106" y="301" text-anchor="middle">重传会话（TCP）</text>
  <text class="hf1sm" x="106" y="320" text-anchor="middle">要回缺的那段</text>
  <rect class="hf1o" x="250" y="280" width="180" height="52" rx="8"/>
  <text class="hf1ink" x="340" y="301" text-anchor="middle">广播环 → 别的核</text>
  <text class="hf1sm" x="340" y="320" text-anchor="middle">落盘录像、监控</text>
  <rect class="hf1o" x="499" y="280" width="150" height="52" rx="8"/>
  <text class="hf1ink" x="574" y="301" text-anchor="middle">柜台 → 交易所</text>
  <text class="hf1sm" x="574" y="320" text-anchor="middle">回报从这里回来</text>

  <text class="hf1mut" x="340" y="364" text-anchor="middle">框里是热路径，中间不经过队列、不换线程；框外的旁路不挡它</text>
</svg>

- **一个线程跑到底，是为了中间不交接**：每交接一次，就多一次跨核搬缓存行和等待，抖动也跟着来（[交易系统架构 3.1](/zh/ref/trading-architecture/#run-to-completion)）。
- **忙轮询、内核旁路，是为了收包不进内核**：网卡的包直接进用户态，线程一直在问“有新包吗”，不睡，也不等中断。
- **落盘、监控放在框外**：热路径只往环里写一份就走，慢活在别的核上做。我实习的回调写环、落盘线程批量读，就是这一块的做法。

### 2.3 代码：简化后的完整程序 {#hft-code}

下面把热路径写成一个能跑的程序：消息格式仿深交所 Binary（头是 MsgType 和 BodyLength，尾是校验和，整数都是大端），包用手工造的代替网卡。故意让第 1 个包装两条消息、3 号丢掉、4 号重复，看序号检查怎么处理。

```cpp
// HFT 行情热路径的简化版：收包 → 分帧校验 → 大端解码 → 按频道查序号、缺了补 → 订单簿 → 策略
// 消息格式仿深交所 Binary：头 MsgType(u32) + BodyLength(u32)，体，尾 Checksum(u32)，整数都是大端
// 真实程序里包来自网卡（组播 + 内核旁路），这里用一串手工造的包代替，好在一个文件里跑起来
// g++ -std=c++20 -O2 -Wall -Wextra feed_handler.cpp -o feed && ./feed
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>

// ---------- 1. 大端读写 ----------
static uint32_t rd32(const uint8_t* p) { uint32_t v; std::memcpy(&v, p, 4); return __builtin_bswap32(v); }
static uint64_t rd64(const uint8_t* p) { uint64_t v; std::memcpy(&v, p, 8); return __builtin_bswap64(v); }
static void wr32(std::vector<uint8_t>& b, uint32_t v) { for (int i = 3; i >= 0; --i) b.push_back(uint8_t(v >> (8 * i))); }
static void wr64(std::vector<uint8_t>& b, uint64_t v) { for (int i = 7; i >= 0; --i) b.push_back(uint8_t(v >> (8 * i))); }

// ---------- 2. 解码后的统一结构 ----------
constexpr uint32_t kOrder = 300192;   // 逐笔委托
constexpr uint32_t kTrade = 300191;   // 逐笔成交
struct Tick {
    uint32_t type;
    uint16_t channel;
    uint64_t seq;          // 频道内连续编号（深交所叫 ApplSeqNum）
    int64_t  price;        // 定点数，4 位小数：186400 = 18.64 元
    int64_t  qty;
    char     side;         // '1' 买，'2' 卖；成交里填主动方
};

// ---------- 3. 订单簿和策略：只做一只股票，只记每个价位的总量 ----------
struct Book {
    std::map<int64_t, int64_t, std::greater<>> bids;   // 价高的在前
    std::map<int64_t, int64_t> asks;                    // 价低的在前
    void apply(const Tick& t) {
        if (t.type == kOrder) {
            (t.side == '1' ? bids[t.price] : asks[t.price]) += t.qty;
        } else if (t.side == '1') {                     // 成交：主动买吃卖一，主动卖吃买一
            eat(asks, t.qty);
        } else {
            eat(bids, t.qty);
        }
    }
    static void eat(auto& lv, int64_t qty) {
        auto it = lv.begin();
        if (it != lv.end() && (it->second -= qty) <= 0) lv.erase(it);
    }
};
struct Strategy {
    void onBook(const Book& b, uint64_t seq) {
        int64_t bid = b.bids.empty() ? 0 : b.bids.begin()->first;
        int64_t ask = b.asks.empty() ? 0 : b.asks.begin()->first;
        std::printf("seq %2llu  买一 %.2f  卖一 %.2f\n", (unsigned long long)seq, bid / 1e4, ask / 1e4);
        // 真实策略在这里判断要不要报单，报单也在这个线程里编码发出去
    }
};

// ---------- 4. 按频道查序号：重复丢掉，跳号先缓存，同时要求重传 ----------
template <class Deliver, class Resend>
struct Sequencer {
    uint64_t expected = 1;
    std::map<uint64_t, Tick> pending;   // 先到的、序号靠后的消息
    Deliver deliver; Resend resend;
    void on(const Tick& t) {
        if (t.seq < expected || pending.count(t.seq)) return;           // 收过了，丢
        if (t.seq > expected) {                                         // 中间缺了
            if (pending.empty()) resend(t.channel, expected, t.seq - 1);
            pending.emplace(t.seq, t);
            return;
        }
        deliver(t); ++expected;
        for (auto it = pending.begin(); it != pending.end() && it->first == expected; it = pending.erase(it)) {
            deliver(it->second); ++expected;                            // 补齐了，按顺序放出去
        }
    }
};

// ---------- 5. 分帧、校验、解码：一个包里可能有好几条消息 ----------
template <class OnTick>
void onPacket(const uint8_t* p, size_t n, OnTick onTick) {
    while (n >= 12) {
        uint32_t type = rd32(p), len = rd32(p + 4);
        if (n < 8 + len + 4) return;                                    // 半条，等下一个包（TCP 才会有）
        uint32_t sum = 0;
        for (size_t i = 0; i < 8 + len; ++i) sum += p[i];
        if (sum % 256 != rd32(p + 8 + len)) return;                     // 校验和不对，丢掉这个包
        const uint8_t* b = p + 8;
        Tick t{type, uint16_t(rd32(b)), rd64(b + 4), int64_t(rd64(b + 12)), int64_t(rd64(b + 20)), char(b[28])};
        onTick(t);
        p += 8 + len + 4; n -= 8 + len + 4;
    }
}

// ---------- 造包：模拟交易所发出来的东西 ----------
static std::vector<uint8_t> msg(uint32_t type, uint64_t seq, int64_t price, int64_t qty, char side) {
    std::vector<uint8_t> b;
    wr32(b, type); wr32(b, 29);
    wr32(b, 2011); wr64(b, seq); wr64(b, uint64_t(price)); wr64(b, uint64_t(qty)); b.push_back(uint8_t(side));
    uint32_t sum = 0; for (uint8_t c : b) sum += c;
    wr32(b, sum % 256);
    return b;
}

int main() {
    std::vector<std::vector<uint8_t>> m = {
        msg(kOrder, 1, 186300, 500, '1'),   // 买 18.63
        msg(kOrder, 2, 186500, 300, '2'),   // 卖 18.65
        msg(kOrder, 3, 186400, 200, '1'),   // 买 18.64
        msg(kTrade, 4, 186500, 300, '1'),   // 主动买吃掉卖一
        msg(kOrder, 5, 186600, 100, '2'),   // 卖 18.66
    };
    Book book; Strategy strat;
    std::vector<uint64_t> resendFrom;
    auto deliver = [&](const Tick& t) { book.apply(t); strat.onBook(book, t.seq); };
    auto resend  = [&](uint16_t ch, uint64_t from, uint64_t to) {
        std::printf("频道 %u 缺 %llu..%llu，到重传端口要\n", ch, (unsigned long long)from, (unsigned long long)to);
        resendFrom.push_back(from);
    };
    Sequencer<decltype(deliver), decltype(resend)> seq{1, {}, deliver, resend};
    auto onTick = [&](const Tick& t) { seq.on(t); };

    // 组播包：第 1 个包里装两条；3 号丢了；4 号到了两次
    std::vector<uint8_t> pkt = m[0]; pkt.insert(pkt.end(), m[1].begin(), m[1].end());
    onPacket(pkt.data(), pkt.size(), onTick);
    onPacket(m[3].data(), m[3].size(), onTick);
    onPacket(m[3].data(), m[3].size(), onTick);
    onPacket(m[4].data(), m[4].size(), onTick);
    // 重传端口把 3 号补回来，3、4、5 按顺序放出
    onPacket(m[2].data(), m[2].size(), onTick);

    bool ok = book.bids.begin()->first == 186400 && book.asks.begin()->first == 186600 && resendFrom.size() == 1;
    std::puts(ok ? "全部测试通过！" : "结果不对");
    return ok ? 0 : 1;
}
```

输出：

```text
seq  1  买一 18.63  卖一 0.00
seq  2  买一 18.63  卖一 18.65
频道 2011 缺 3..3，到重传端口要
seq  3  买一 18.64  卖一 18.65
seq  4  买一 18.64  卖一 0.00
seq  5  买一 18.64  卖一 18.66
全部测试通过！
```

4 号先到，没有直接用，先缓存起来并要求重传；3 号补回来以后，3、4、5 按顺序放出。重复的那个 4 号被丢掉了。

真实程序里，包从网卡来。用普通 socket 收组播是下面这样，HFT 会把 `recv` 换成内核旁路的接口，循环不变：

```cpp
int fd = socket(AF_INET, SOCK_DGRAM, 0);
sockaddr_in addr{};
addr.sin_family = AF_INET;
addr.sin_port = htons(port);
addr.sin_addr.s_addr = htonl(INADDR_ANY);
bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof addr);

ip_mreq mreq{};                                    // 加入组播组：交易所往这个组地址发
mreq.imr_multiaddr.s_addr = inet_addr(group);
mreq.imr_interface.s_addr = inet_addr(nic_ip);     // 从哪块网卡收
setsockopt(fd, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof mreq);
fcntl(fd, F_SETFL, O_NONBLOCK);

uint8_t buf[2048];
for (;;) {                                         // 线程绑在独占的核上，一直问，不睡
    ssize_t n = recv(fd, buf, sizeof buf, 0);
    if (n > 0) onPacket(buf, size_t(n), onTick);
}
```

### 2.4 简化掉了什么 {#hft-real}

- **收包**：真实的用 ef_vi、DPDK 或 Onload 绕过内核，再往前一步是 FPGA 网卡直接解码。
- **上海要先解 FAST**：字段按“没带值就沿用上一条”编码，解码要记住每个字段上一条的值。
- **A、B 两路择优**：同一份数据从两条线路各收一份，按序号谁先到用谁。
- **重传要设超时**：补不回来要报警；快照不补，等下一张。
- **频道多**：按频道分给几个线程，一个频道只能一个线程处理，才能保证顺序。
- **订单簿不用 `std::map`**：按价位下标的数组，盘前一次分配好，热路径上不分配内存；还要处理撤单（深圳的撤单在成交消息里）和没有价格的市价单。

### 2.5 行情软件公司是不是这一套 {#vendor-vs-hft}

以“转成统一结构”为界分成两半（[1.1 的图](#full)里白框和绿框）：前半段是收包、解码、查序号补缺，得到完整、按顺序的消息；后半段从转成自己的统一结构开始，是送到哪、怎么用。

- **前半段一样**：都要直连交易所，自己收包、解码、查序号、补缺。
- **后半段不一样**：HFT 交给同一个线程里的订单簿和策略，要的是自己最快下单；行情软件公司要加工再一级级推给大量用户，要的是吞吐和稳定。
- **我实习做的也在后半段**：SDK 替我做了前半段，我从回调拿到结构体开始，转统一结构、经广播环交给落盘。

| 项 | HFT | 行情软件公司（信息商） |
| --- | --- | --- |
| 收行情 | 直连交易所，自己写 feed handler | 一样 |
| 目标 | 自己比别人先下单 | 把行情及时、稳定地推给大量用户 |
| 延迟要求 | 微秒级，看单线程的延迟和抖动 | 用户看盘，毫秒级就够；更看吞吐和稳定 |
| 难点 | 热路径上每一步的耗时 | 扇出：全市场加工（K 线、指标）、多级转发、海量连接、处理不过来的客户端 |
| 下游 | 同一台机器上的策略 | 一级级行情服务器，最后到 App |
| 常用做法 | 内核旁路、绑核、忙轮询、一个线程跑到底 | 先发全量快照再发增量、慢客户端合并更新只发最新值、主备和水平扩展 |

行情软件公司内部具体怎么实现，没有公开资料；上表是按业务推出来的，面试时可以反问确认。

### 2.6 怎么说 {#hft-say}

| 问 | 答 |
| --- | --- |
| 你了解行情接入吗 | 了解整体结构：交易所按频道编号发出来，接入方收包、解码、查序号、缺了到重传端口补，再转成统一结构分发出去；HFT 还会在同一个线程里接着做订单簿和策略。实习里我用的是数据商的 SDK，只做过回调之后这一段：转统一结构、经广播环交给落盘，加上字段核对和断线续传的验证。 |
| 你写过 feed handler 吗 | 没在生产上写过。结构和难点知道：分帧、大端解码、按频道查序号、缺了先缓存再补，上海还要解 FAST。 |
| HFT 和行情软件公司的行情系统有什么不同 | 前半段一样，都要直连交易所解码、补缺；后半段 HFT 要自己最快下单，拼单线程延迟，行情软件公司要推给大量用户，拼吞吐、扇出和稳定。 |

## 3. 两条流 {#flows}

```
行情：交易所 ─► 行情网关 / 组播 ─► 接入方（信息商、券商、数据商）─► SDK 或自己的 feed handler ─► 你的系统

交易：你的系统 ─► 券商柜台（资金、持仓、风控）─► 交易所交易网关 ─► 撮合
回报：你的系统 ◄─ 券商柜台 ◄─ 交易所交易网关 ◄─ 确认、成交、撤单
```

| 项 | 行情 | 交易 |
| --- | --- | --- |
| 方向 | 交易所 → 你 | 你 → 柜台 → 交易所，回报原路回来 |
| 内容 | 快照、逐笔委托、逐笔成交 | 报单、撤单、查询；委托确认、成交回报、撤单回报 |
| 你对接的 | 行情 SDK，或交易所的行情网关 | 柜台的交易 API |
| 丢了一条会怎样 | 快照等下一张；逐笔按序号发现缺口，找回来补 | 必须查回来，不然资金、持仓和真实情况对不上 |

## 4. 券商柜台 {#counter}

### 4.1 柜台是什么 {#counter-what}

- **为什么一定要经过券商**：只有交易所的会员（券商）有交易单元（俗称席位），个人和机构的委托都要经券商报出去，券商还要替交易所把风控和清算这两关。
- **柜台做的事**：
  - 账户：客户资料、资金、持仓。
  - 事前风控：资金够不够买；持仓够不够卖，A 股当天买的当天不能卖（T+1）；价格和数量合不合规。
  - 报盘：把委托按交易所的协议发给交易所的交易网关。
  - 回报：收交易所的确认、成交、撤单，更新资金和持仓，再推给客户。
  - 清算：盘后和中国结算清算交收、对账。
- **一般分三块**：柜台核心（账户、资金、持仓那些表），对外接口（App、网上交易、程序化客户从这里进），报盘（和交易所交易网关通信）。

### 4.2 两类柜台 {#counter-types}

| 类 | 面向谁 | 放在哪 | 快慢 | 常见产品 |
| --- | --- | --- | --- | --- |
| 集中交易柜台（普通柜台） | 全体经纪客户；App、网上交易都落在这里 | 券商自己的数据中心 | 毫秒级 | 恒生 UF、金证、顶点 A5 |
| 极速柜台 | 量化私募等机构，客户用 API 程序化下单 | 交易所的托管机房，离交易网关近 | 微秒级 | 恒生 UFT、华锐 ATP、宽睿 OES、顶点 HTS、金证 FOS、盛立 REM；中泰 XTP 是券商自研的 |
| 期货柜台 | 期货公司的客户 | 期货公司机房或交易所托管 | 视部署 | CTP（上期技术）最常见，同一套给交易 API 和行情 API |

极速柜台快，是因为功能砍到只剩下单、撤单、查询，内存里做风控，而且机器就在交易所旁边。

### 4.3 柜台和交易所之间：交易网关 {#trade-gateway}

- **交易网关是交易所给会员的报单入口**：和收行情的行情网关对应，也部署在接入方的机房。
- **深交所是 TGW**：2016 年起用流式报盘，协议是 Binary 或 STEP。
- **上交所是 TDGW**：2022 年 7 月起分批上线，替换原来的 EzOES 数据库报盘。
- **数据库报盘和流式报盘的区别**：
  - 数据库报盘：券商把委托写进报盘库的表，交易所的报盘程序去读。
  - 流式报盘：券商和交易网关之间是一条 TCP 会话，委托和回报都是消息，直接收发，延迟低得多。

### 4.4 接柜台 API 要处理什么 {#counter-api}

- **下单是异步的**：下单函数返回只说明请求发出去了，柜台风控过没过、交易所确没确认、成没成交，都在之后的回调里。
- **每笔订单有状态**：
  - 正常走完：未报 → 已报 → 部分成交 → 全部成交。
  - 中途结束：已撤、部撤，或者被柜台、交易所拒掉成了废单。
- **两个编号要对上**：自己生成的报单编号（CTP 叫 OrderRef）和柜台、交易所回的委托编号，建一张映射，回报靠它找回自己的订单。
- **回报会乱序、会重复**：成交回报可能比委托确认先到，同一条回报可能来两次，按编号去重、按状态只往前走。
- **断线重连以后先查询再继续**：查委托、成交、持仓，和本地状态对账；不对账就重发，可能重复报单。
- **报单有流控**：柜台和交易所都限制每秒报单数，超了直接拒单，自己要先限速。

## 5. 行情从哪来 {#feed-sources}

| 渠道 | 谁在用 | 怎么收 |
| --- | --- | --- |
| 交易所直连 | 信息商（做行情软件的公司）、券商、在托管机房里的量化 | 向交易所的信息公司（上证信息、深证信息）买 Level-2 授权，在机房收行情网关或组播，自己解码 |
| 券商提供 | 极速柜台的客户 | 柜台附带的行情 API，或者在托管机房里收券商转发的组播 |
| 数据商的 SDK | 机构客户 | 数据商把行情转发出来，客户用 SDK 回调收；我实习就是这种 |
| 期货柜台的行情 API | 期货量化 | CTP 的行情 API 按合约订阅，回调 `OnRtnDepthMarketData` 交出深度行情 |

几种收法的延迟差别见 [A 股行情 1.3](/zh/ref/a-share-market/#feed-path)，序号和丢包见[第 3 节](/zh/ref/a-share-market/#seq)。

## 6. “接入经验”各指什么 {#phrases}

| 说法 | 指什么 | 被问时会问到 |
| --- | --- | --- |
| 行情接入经验 | 收行情：连接、订阅、解码、序号检查、补缺，变成统一结构 | 用的哪家 SDK、回调线程怎么处理、丢包怎么发现、字段怎么核 |
| 交易所直连经验 | 自己对接交易所的协议，不经过 SDK | 行情网关或交易网关的会话、心跳、重传，组播为什么还要 TCP |
| 券商柜台对接经验（交易接口经验） | 调柜台的 API 下单、撤单、查询 | 订单状态、回报乱序、两个编号怎么对、断线以后怎么对账 |
| CTP、XTP 经验 | 用过某一家具体柜台的 API | Api 发请求、Spi 收回调的模型；报单编号；流控 |
| FIX 经验 | 国际通用的交易协议，对接海外券商或交易所用 | 下单和执行回报这两类消息，会话序号和重发 |
| 低延迟经验 | 托管、绑核、忙轮询、内核旁路、FPGA | 延迟怎么测、抖动从哪来 |

## 7. 放在行情软件公司里 {#vendor-context}

做行情软件的信息商，两条流都有，但角色和量化公司不同：

- **行情这条，对内是接入，对外是分发**：
  - 接入：从交易所买 Level-2 授权，自己的行情服务器收进来，再加工成 K 线、指标。
  - 分发：推给大量 App 用户，先发一份全量快照，之后发增量；客户端处理不过来就合并更新，只发最新值。
- **交易这条，是对接各家券商的柜台**：App 里的“交易”背后，是登录某家券商的账户，委托经这家券商的集中交易柜台报出去。行情软件公司早年给券商做网上行情交易系统，因此拿到了很多券商的交易接口。
- **所以“行情接入”在这里可能指不同的东西**：
  - 服务端从交易所或数据源收行情。
  - 客户端从自己的行情服务器收推送。
  - 面试时听清是哪一个，反问时可以问。

## 8. 常问 {#qa}

| 问 | 答 |
| --- | --- |
| 你有券商柜台的对接经验吗 | 没有，实习做的是行情这一侧，用数据商的 SDK 收沪深 Level-2。柜台的流程了解：下单是异步的，结果走回调；要维护订单状态，断线重连先查询对账再继续。 |
| 券商柜台是干什么的 | 券商的交易核心：管账户、资金、持仓，下单前做风控，再报给交易所；回报回来更新资金和持仓，盘后清算。 |
| 普通柜台和极速柜台有什么区别 | 普通柜台服务全体客户、功能全、毫秒级；极速柜台面向量化机构，放在交易所托管机房，功能精简、微秒级。 |
| 为什么不能直接报给交易所 | 只有会员券商有交易单元，委托必须经券商报出去，风控和清算也由券商负责。 |
| 下单函数返回了，单子就成了吗 | 没有。返回只说明请求发出去了；风控、交易所确认、成交都在之后的回报里，可能被拒成废单。 |
| 行情 SDK 和柜台 API 有什么共同点 | 都是对方的线程回调你，回调里不能做慢活，都要处理断线。不同的是行情丢了可以等下一张快照或者补，回报丢了必须查回来。 |
| 交易网关和行情网关是一回事吗 | 不是。行情网关是交易所发行情的出口，交易网关是会员报单的入口，两者都部署在接入方的机房。 |

## 来源

- 极速柜台的厂商和定位：[财联社](https://www.cls.cn/detail/663513)、[财联社](https://www.cls.cn/detail/1082242)。
- 集中交易柜台的三块结构、行情软件公司和券商交易接口：[人人都是产品经理](https://www.woshipm.com/pd/5499131.html)、[格隆汇](https://m.gelonghui.com/p/467243)。
- 上交所 TDGW 替换 EzOES、深交所 2016 年起流式报盘：[证券之星](https://stock.stockstar.com/IG2022072100011207.shtml)、[深交所 Binary 交易数据接口规范](https://www.szse.cn/marketServices/technicalservice/interface/P020250328367803673293.pdf)。
- CTP 行情回调：[CTP 客户端开发指南](https://eastmoneyfutures.com/software/9809db08-c8cb-4cc4-b631-8a16f0c2dfb9/0f757a06-10a5-48c2-817e-362b42202b51/a7a19350-141d-48c0-b586-253cb3ec5b18/CTPcdg_ch_2016-10-27.pdf)。
