---
title: "IV. 行情接入速览：券商柜台、行情源、“接入经验”分别指什么"
date: 2026-11-27T00:00:00+08:00
slug: "market-access"
description: "行情接入长什么样：HFT 直连和数据商 SDK 两条路的架构图。面试和招聘里常说的券商柜台、行情接入、柜台对接、交易所直连分别指什么。行情是从交易所往里收数据，柜台是券商替你往交易所报单的那一层；两类柜台、交易网关、行情从哪几种渠道来、各种“接入经验”被问时会问到什么。"
weight: 3
toc: true
---

> 这几个词的本质：行情是从交易所往里收的数据，柜台是券商替你往交易所报单的那一层。

## 概览 {#overview}

- **行情接入长什么样（[第 1 节](#shape)）**：交易所发出的消息，要有人收包、解码、按序号补齐，这一层叫 feed handler。
  - HFT 在托管机房里自己写 feed handler。
  - 用数据商 SDK 时，这层是数据商做的，回调交给你的已经是结构体。
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

## 1. 行情接入长什么样：HFT 直连和数据商 SDK {#shape}

### 1.1 一条行情走过的路 {#path}

回调里拿到的一个 tick，就是交易所发出来的一条消息：一张快照，或者一笔逐笔委托、逐笔成交。它到你手里之前，已经有人收好、解码、按序号排好了。区别只在这件事是谁做的：

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

### 1.2 feed handler 做的五件事 {#feed-handler}

真正意义上的“行情接入”就是这一层，按数据流的顺序：

1. **收包、切消息**：TCP 是字节流，一次可能收到半条或好几条，按消息头里的长度切；组播一个包里可能装好几条。
2. **解码**：按消息类型分派；字段是大端，要转字节序；上海的 Level-2 还要先解 FAST 编码。
3. **按频道查序号**：每个频道内序号连续，重复的丢掉，跳号说明丢了。
4. **缺了就补**：后到的先缓存，同时到交易所的重传端口要回缺的那段，补齐再按顺序放出去；快照不补，等下一张。
5. **转成统一结构，交给下游**：价格统一成定点整数，代码映射成下标，沪深的字段对齐；HFT 交给同机的订单簿和策略，数据商发给客户。

用 SDK 时，前四件是 SDK 和数据商做的；第五件里的“转统一结构、交给下游”是你做的。

### 1.3 两条路差在哪 {#compare}

| 项 | HFT 直连 | 数据商 SDK |
| --- | --- | --- |
| feed handler 谁写 | 自己 | 数据商；你只接 SDK |
| 机器在哪 | 交易所的托管机房 | 自己机房，经专线收数据商的推送 |
| 延迟 | 几微秒，再往下用 FPGA 解码 | 几十到几百微秒，抖动由厂商的库决定 |
| 你拿到的 | 网卡上的原始字节 | 回调里的结构体 |
| 要懂的 | 交易所协议、组播、重传、内核旁路 | SDK 的线程模型、字段口径、断线续传 |
| 面试里“行情接入”指 | 写 feed handler | 接 SDK 之后这一段：回调、统一结构、分发 |

### 1.4 我做的是哪一段 {#mine}

- **橙色那一框**：用两家厂商的 SDK 收沪深 Level-2，回调里转成统一结构，经广播环交给另一个进程落盘（[行情接入和 SPMC 广播环](/zh/interview/md-feed-spmc/)）。
- **这一段要保证的**：
  - 不丢、不乱：整日回放核条数，断线续传前后核不丢不重。
  - 字段对：厂商头文件不全，拿真实行情逐个字段核。
  - 回调不堵：回调线程是 SDK 的，不在里面做 I/O。
- **被问到时先说边界**：行情用的是数据商的 SDK，没直连交易所；左边那套了解结构，没在生产上写过。

## 2. 两条流 {#flows}

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

## 3. 券商柜台 {#counter}

### 3.1 柜台是什么 {#counter-what}

- **为什么一定要经过券商**：只有交易所的会员（券商）有交易单元（俗称席位），个人和机构的委托都要经券商报出去，券商还要替交易所把风控和清算这两关。
- **柜台做的事**：
  - 账户：客户资料、资金、持仓。
  - 事前风控：资金够不够买；持仓够不够卖，A 股当天买的当天不能卖（T+1）；价格和数量合不合规。
  - 报盘：把委托按交易所的协议发给交易所的交易网关。
  - 回报：收交易所的确认、成交、撤单，更新资金和持仓，再推给客户。
  - 清算：盘后和中国结算清算交收、对账。
- **一般分三块**：柜台核心（账户、资金、持仓那些表），对外接口（App、网上交易、程序化客户从这里进），报盘（和交易所交易网关通信）。

### 3.2 两类柜台 {#counter-types}

| 类 | 面向谁 | 放在哪 | 快慢 | 常见产品 |
| --- | --- | --- | --- | --- |
| 集中交易柜台（普通柜台） | 全体经纪客户；App、网上交易都落在这里 | 券商自己的数据中心 | 毫秒级 | 恒生 UF、金证、顶点 A5 |
| 极速柜台 | 量化私募等机构，客户用 API 程序化下单 | 交易所的托管机房，离交易网关近 | 微秒级 | 恒生 UFT、华锐 ATP、宽睿 OES、顶点 HTS、金证 FOS、盛立 REM；中泰 XTP 是券商自研的 |
| 期货柜台 | 期货公司的客户 | 期货公司机房或交易所托管 | 视部署 | CTP（上期技术）最常见，同一套给交易 API 和行情 API |

极速柜台快，是因为功能砍到只剩下单、撤单、查询，内存里做风控，而且机器就在交易所旁边。

### 3.3 柜台和交易所之间：交易网关 {#trade-gateway}

- **交易网关是交易所给会员的报单入口**：和收行情的行情网关对应，也部署在接入方的机房。
- **深交所是 TGW**：2016 年起用流式报盘，协议是 Binary 或 STEP。
- **上交所是 TDGW**：2022 年 7 月起分批上线，替换原来的 EzOES 数据库报盘。
- **数据库报盘和流式报盘的区别**：
  - 数据库报盘：券商把委托写进报盘库的表，交易所的报盘程序去读。
  - 流式报盘：券商和交易网关之间是一条 TCP 会话，委托和回报都是消息，直接收发，延迟低得多。

### 3.4 接柜台 API 要处理什么 {#counter-api}

- **下单是异步的**：下单函数返回只说明请求发出去了，柜台风控过没过、交易所确没确认、成没成交，都在之后的回调里。
- **每笔订单有状态**：
  - 正常走完：未报 → 已报 → 部分成交 → 全部成交。
  - 中途结束：已撤、部撤，或者被柜台、交易所拒掉成了废单。
- **两个编号要对上**：自己生成的报单编号（CTP 叫 OrderRef）和柜台、交易所回的委托编号，建一张映射，回报靠它找回自己的订单。
- **回报会乱序、会重复**：成交回报可能比委托确认先到，同一条回报可能来两次，按编号去重、按状态只往前走。
- **断线重连以后先查询再继续**：查委托、成交、持仓，和本地状态对账；不对账就重发，可能重复报单。
- **报单有流控**：柜台和交易所都限制每秒报单数，超了直接拒单，自己要先限速。

## 4. 行情从哪来 {#feed-sources}

| 渠道 | 谁在用 | 怎么收 |
| --- | --- | --- |
| 交易所直连 | 信息商（做行情软件的公司）、券商、在托管机房里的量化 | 向交易所的信息公司（上证信息、深证信息）买 Level-2 授权，在机房收行情网关或组播，自己解码 |
| 券商提供 | 极速柜台的客户 | 柜台附带的行情 API，或者在托管机房里收券商转发的组播 |
| 数据商的 SDK | 机构客户 | 数据商把行情转发出来，客户用 SDK 回调收；我实习就是这种 |
| 期货柜台的行情 API | 期货量化 | CTP 的行情 API 按合约订阅，回调 `OnRtnDepthMarketData` 交出深度行情 |

几种收法的延迟差别见 [A 股行情 1.3](/zh/ref/a-share-market/#feed-path)，序号和丢包见[第 3 节](/zh/ref/a-share-market/#seq)。

## 5. “接入经验”各指什么 {#phrases}

| 说法 | 指什么 | 被问时会问到 |
| --- | --- | --- |
| 行情接入经验 | 收行情：连接、订阅、解码、序号检查、补缺，变成统一结构 | 用的哪家 SDK、回调线程怎么处理、丢包怎么发现、字段怎么核 |
| 交易所直连经验 | 自己对接交易所的协议，不经过 SDK | 行情网关或交易网关的会话、心跳、重传，组播为什么还要 TCP |
| 券商柜台对接经验（交易接口经验） | 调柜台的 API 下单、撤单、查询 | 订单状态、回报乱序、两个编号怎么对、断线以后怎么对账 |
| CTP、XTP 经验 | 用过某一家具体柜台的 API | Api 发请求、Spi 收回调的模型；报单编号；流控 |
| FIX 经验 | 国际通用的交易协议，对接海外券商或交易所用 | 下单和执行回报这两类消息，会话序号和重发 |
| 低延迟经验 | 托管、绑核、忙轮询、内核旁路、FPGA | 延迟怎么测、抖动从哪来 |

## 6. 放在行情软件公司里 {#vendor-context}

做行情软件的信息商，两条流都有，但角色和量化公司不同：

- **行情这条，对内是接入，对外是分发**：
  - 接入：从交易所买 Level-2 授权，自己的行情服务器收进来，再加工成 K 线、指标。
  - 分发：推给大量 App 用户，先发一份全量快照，之后发增量；客户端处理不过来就合并更新，只发最新值。
- **交易这条，是对接各家券商的柜台**：App 里的“交易”背后，是登录某家券商的账户，委托经这家券商的集中交易柜台报出去。行情软件公司早年给券商做网上行情交易系统，因此拿到了很多券商的交易接口。
- **所以“行情接入”在这里可能指不同的东西**：
  - 服务端从交易所或数据源收行情。
  - 客户端从自己的行情服务器收推送。
  - 面试时听清是哪一个，反问时可以问。

## 7. 常问 {#qa}

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
