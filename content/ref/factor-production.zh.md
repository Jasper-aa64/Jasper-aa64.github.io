---
title: "因子生产：从研究到上线，回放、回算和一致性"
description: "一个因子从研究原型、批量回算成因子库、回测到上线实盘的五步；回放、回算、回测和实盘怎么共用同一个因子；批量回算怎么算得快、离线流水线怎么组织、收盘后的补算怎么挪回逐条路径；因子一致性：每天逐值对账、数据口径、pandas / NumPy 和 C++ 默认行为不同的地方（求和顺序、NaN、ddof、rolling、ewm、取整、整数除法、溢出、类型、排名、时间切分、编译选项）、对不上时怎么按差值的样子定位。"
date: 2026-11-03
lastmod: 2026-11-12
slug: "factor-production"
aliases: ["/interview/python-cpp-consistency/", "/ref/factor-consistency/"]
weight: 18
toc: true
math: true
---

一个因子从研究员的想法，到实盘里交给策略的一个值，要经过几道工序：研究侧写原型，工程把它批量算成历史值，研究员拿去回测，再上线实盘，每天盘后对账。这页按这个顺序讲：

- **第 1 节是五步流程**：每一步谁做、产出什么。
- **第 2 节是回放和回测的架构**：因子只写一份，实盘、回放、回算、回测只是喂法不同。
- **第 3 节是批量回算**：几年的全市场数据怎么算得快，离线流水线怎么组织，收盘后的补算为什么要挪回逐条路径。
- **第 4 节是因子一致性**：研究原型、因子库、实盘三处算出来要逐值相同；对不上时从系统、数据口径、数值、编译选项几层找原因。

单个因子怎么写成增量见[因子计算](/zh/ref/factor-computation/)，数据本身各记了什么见 [A 股行情](/zh/ref/a-share-market/)，行情怎么录下来、怎么重放见[交易系统架构](/zh/ref/trading-architecture/)。

## 1. 五步：一个因子从研究到上线 {#lifecycle}

| 步 | 谁做 | 做什么 | 产出 |
|---|---|---|---|
| 1. 原型 | 研究员 | 用 pandas 在历史数据上把因子算出来，看 IC、分组收益，判断有没有用 | 研究代码和结论 |
| 2. 批量生产历史值 | 工程 | 用 C++ 把因子接进离线流水线，按 全市场 × 多年 × 多组参数 批量算，和研究原型或旧版本的结果逐值对齐 | 因子库：每只股票、每个时间格一个值的文件 |
| 3. 组合和回测 | 研究员 | 拿因子库做组合、训练模型、回测策略 | 上不上线 |
| 4. 上线 | 工程 | 实盘行情来一条算一条，值交给策略 | 盘中的实时值 |
| 5. 对账 | 工程 | 每天盘后拿实盘的值和重放的值逐个比 | 差异和原因 |

- **第 2 步要用 C++**：全市场几千只股票，每只一天几千到几万条行情，还要跑多年、多组参数，pandas 跑不动。
- **第 2、3 步会来回好几轮**：改了参数或定义，因子库就要重新生产一遍。

**所以同一个因子要在三处算**：研究侧的原型（第 1 步）、因子库和回测（第 2、3 步）、实盘（第 4 步）。三处怎么逐值对上，是第 4 节的事。

## 2. 回放和回测：因子只写一份，喂法不同 {#replay}

围着同一个因子，有三种“把行情喂进去”的用法：

- **回放**：把录下来的行情按原来的顺序重新喂一遍，用来盘后对账、复现盘中的问题、重启以后把状态追回来。
- **回算**：在几年的历史行情上把因子值批量算出来，存成因子库（第 3 节）。
- **回测**：拿因子库里的值模拟交易、算收益（第 1 节的第 3 步）。

整个系统长这样：

<svg viewBox="0 0 760 600" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="回放和回测的架构：上面一条是实盘，交易所组播经行情接入线程进广播环，分片线程里的因子算完交给决策线程的策略和风控，再经下单网关到交易所；广播环旁边的落盘把行情录成录像，分片线程把因子值写进日志。中间一条是盘后回放：回放器读当天录像，按原顺序喂给同一份因子代码，算出的值和实盘因子值日志逐值对账，差异分成代码的和数据的。下面一条是研究用的回算和回测：数据商历史文件或录像先进中间层（按股票重排、合成订单簿），再切成一只股票一天的回算任务，任务里跑同一份因子代码，结果按天存成因子库；回测引擎里，策略读因子库下单，模拟撮合用历史行情判断成交，账户记持仓和资金，成交回报再回到策略，最后得到收益、回撤这些回测结果。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .ra1bg  { fill: #fbfaf7; }
    .ra1ln1 { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1; }
    .ra1ln2 { fill: #f3efe6; stroke: #c9bc9c; stroke-width: 1; }
    .ra1ln3 { fill: #f1eef6; stroke: #c3b9d6; stroke-width: 1; }
    .ra1b   { fill: #ffffff; stroke: #8a8f98; stroke-width: 1.3; }
    .ra1f   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .ra1fl  { fill: #fff8e6; stroke: #b8964a; stroke-width: 1.3; }
    .ra1eng { fill: none; stroke: #8a7ca8; stroke-width: 1.3; stroke-dasharray: 6 4; }
    .ra1ink { fill: #1c1b18; font-size: 12.5px; }
    .ra1sm  { fill: #4a463e; font-size: 11px; }
    .ra1mut { fill: #6b6558; font-size: 11.5px; }
    .ra1ttl { fill: #1c1b18; font-size: 15px; font-weight: 700; }
    .ra1hd  { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .ra1ar  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .ra1ad  { stroke: #6b6558; stroke-width: 1.3; fill: none; stroke-dasharray: 5 4; }
    .ra1hh  { fill: #6b6558; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1ln1 { fill: #20242a; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1ln2 { fill: #26231d; stroke: #5a5242; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1ln3 { fill: #23202b; stroke: #4c4560; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1b { fill: #1d1c22; stroke: #6f7380; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1f { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1fl { fill: #3a3220; stroke: #b8964a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1eng { stroke: #a89cc8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1ink, :root:is([data-theme="dark"], [data-theme="black"]) .ra1ttl, :root:is([data-theme="dark"], [data-theme="black"]) .ra1hd { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1sm, :root:is([data-theme="dark"], [data-theme="black"]) .ra1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1ar, :root:is([data-theme="dark"], [data-theme="black"]) .ra1ad { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .ra1hh { fill: #a19caf; }
  </style>
  <defs><marker id="ra1ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ra1hh"/></marker></defs>
  <rect class="ra1bg" x="0" y="0" width="760" height="600" rx="10"/>
  <text class="ra1ttl" x="20" y="30">回放和回测的架构：三条路，绿色的因子代码只有一份</text>
  <rect class="ra1ln1" x="10" y="46" width="740" height="168" rx="8"/>
  <text class="ra1hd" x="22" y="66">实盘：盘中，行情来一条算一条</text>
  <rect class="ra1b" x="20" y="80" width="96" height="46" rx="6"/>
  <text class="ra1ink" x="68" y="100" text-anchor="middle">交易所组播</text>
  <text class="ra1sm" x="68" y="116" text-anchor="middle">网卡收包</text>
  <rect class="ra1b" x="130" y="80" width="104" height="46" rx="6"/>
  <text class="ra1ink" x="182" y="100" text-anchor="middle">行情接入线程</text>
  <text class="ra1sm" x="182" y="116" text-anchor="middle">解码成 Tick</text>
  <rect class="ra1b" x="248" y="80" width="96" height="46" rx="6"/>
  <text class="ra1ink" x="296" y="100" text-anchor="middle">广播环</text>
  <text class="ra1sm" x="296" y="116" text-anchor="middle">共享内存</text>
  <rect class="ra1f" x="358" y="80" width="112" height="46" rx="6"/>
  <text class="ra1ink" x="414" y="100" text-anchor="middle">分片线程</text>
  <text class="ra1sm" x="414" y="116" text-anchor="middle">因子 on_tick</text>
  <rect class="ra1b" x="484" y="80" width="112" height="46" rx="6"/>
  <text class="ra1ink" x="540" y="100" text-anchor="middle">决策线程</text>
  <text class="ra1sm" x="540" y="116" text-anchor="middle">策略、风控</text>
  <rect class="ra1b" x="610" y="80" width="130" height="46" rx="6"/>
  <text class="ra1ink" x="675" y="100" text-anchor="middle">下单网关</text>
  <text class="ra1sm" x="675" y="116" text-anchor="middle">经柜台到交易所</text>
  <path class="ra1ar" d="M116 103 H126" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M234 103 H244" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M344 103 H354" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M470 103 H480" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M596 103 H606" marker-end="url(#ra1ah)"/>
  <rect class="ra1fl" x="238" y="154" width="116" height="44" rx="6"/>
  <text class="ra1ink" x="296" y="173" text-anchor="middle">落盘：行情录像</text>
  <text class="ra1sm" x="296" y="189" text-anchor="middle">收到什么录什么</text>
  <rect class="ra1fl" x="358" y="154" width="112" height="44" rx="6"/>
  <text class="ra1ink" x="414" y="173" text-anchor="middle">因子值日志</text>
  <text class="ra1sm" x="414" y="189" text-anchor="middle">每次算出的值</text>
  <path class="ra1ar" d="M296 126 V150" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M414 126 V150" marker-end="url(#ra1ah)"/>
  <rect class="ra1ln2" x="10" y="224" width="740" height="112" rx="8"/>
  <text class="ra1hd" x="22" y="244">回放：每天盘后，录像按原来的顺序重喂一遍</text>
  <rect class="ra1b" x="238" y="262" width="116" height="46" rx="6"/>
  <text class="ra1ink" x="296" y="282" text-anchor="middle">回放器</text>
  <text class="ra1sm" x="296" y="298" text-anchor="middle">读录像、按序号喂</text>
  <rect class="ra1f" x="368" y="262" width="112" height="46" rx="6"/>
  <text class="ra1ink" x="424" y="282" text-anchor="middle">因子 on_tick</text>
  <text class="ra1sm" x="424" y="298" text-anchor="middle">同一份代码</text>
  <rect class="ra1b" x="494" y="262" width="104" height="46" rx="6"/>
  <text class="ra1ink" x="546" y="282" text-anchor="middle">逐值对账</text>
  <text class="ra1sm" x="546" y="298" text-anchor="middle">按行情序号对齐</text>
  <rect class="ra1b" x="612" y="262" width="128" height="46" rx="6"/>
  <text class="ra1ink" x="676" y="282" text-anchor="middle">差异归因</text>
  <text class="ra1sm" x="676" y="298" text-anchor="middle">代码的还是数据的</text>
  <path class="ra1ar" d="M296 198 V258" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M354 285 H364" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M480 285 H490" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M598 285 H608" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M470 186 C520 186 546 210 546 258" marker-end="url(#ra1ah)"/>
  <text class="ra1mut" x="140" y="288" text-anchor="middle">同一天、同一份输入</text>
  <text class="ra1mut" x="140" y="304" text-anchor="middle">结果应该逐位相同</text>
  <rect class="ra1ln3" x="10" y="346" width="740" height="222" rx="8"/>
  <text class="ra1hd" x="22" y="366">回算和回测：研究用，几年的全市场</text>
  <rect class="ra1b" x="20" y="382" width="116" height="46" rx="6"/>
  <text class="ra1ink" x="78" y="402" text-anchor="middle">历史行情</text>
  <text class="ra1sm" x="78" y="418" text-anchor="middle">数据商文件或录像</text>
  <rect class="ra1b" x="150" y="382" width="130" height="46" rx="6"/>
  <text class="ra1ink" x="215" y="402" text-anchor="middle">中间层</text>
  <text class="ra1sm" x="215" y="418" text-anchor="middle">按股票重排、合成盘口</text>
  <rect class="ra1f" x="294" y="382" width="150" height="46" rx="6"/>
  <text class="ra1ink" x="369" y="402" text-anchor="middle">回算任务：因子 on_tick</text>
  <text class="ra1sm" x="369" y="418" text-anchor="middle">一只股票一天，多核多机</text>
  <rect class="ra1fl" x="456" y="382" width="112" height="46" rx="6"/>
  <text class="ra1ink" x="512" y="402" text-anchor="middle">因子库</text>
  <text class="ra1sm" x="512" y="418" text-anchor="middle">每格一个值，按天存</text>
  <path class="ra1ar" d="M136 405 H146" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M280 405 H290" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M444 405 H452" marker-end="url(#ra1ah)"/>
  <rect class="ra1eng" x="150" y="452" width="440" height="104" rx="8"/>
  <text class="ra1hd" x="162" y="470">回测引擎</text>
  <rect class="ra1b" x="166" y="488" width="106" height="46" rx="6"/>
  <text class="ra1ink" x="219" y="508" text-anchor="middle">策略</text>
  <text class="ra1sm" x="219" y="524" text-anchor="middle">读因子值，决定下单</text>
  <rect class="ra1b" x="316" y="488" width="120" height="46" rx="6"/>
  <text class="ra1ink" x="376" y="508" text-anchor="middle">模拟撮合</text>
  <text class="ra1sm" x="376" y="524" text-anchor="middle">能不能成交、成交价</text>
  <rect class="ra1b" x="480" y="488" width="100" height="46" rx="6"/>
  <text class="ra1ink" x="530" y="508" text-anchor="middle">账户</text>
  <text class="ra1sm" x="530" y="524" text-anchor="middle">持仓、资金、盈亏</text>
  <rect class="ra1b" x="612" y="488" width="128" height="46" rx="6"/>
  <text class="ra1ink" x="676" y="508" text-anchor="middle">回测结果</text>
  <text class="ra1sm" x="676" y="524" text-anchor="middle">收益、回撤、换手</text>
  <path class="ra1ar" d="M272 511 H312" marker-end="url(#ra1ah)"/>
  <text class="ra1mut" x="294" y="503" text-anchor="middle">报单</text>
  <path class="ra1ar" d="M436 511 H476" marker-end="url(#ra1ah)"/>
  <text class="ra1mut" x="458" y="503" text-anchor="middle">成交</text>
  <path class="ra1ar" d="M530 488 V476 H252 V484" marker-end="url(#ra1ah)"/>
  <text class="ra1mut" x="392" y="471" text-anchor="middle">成交回报</text>
  <path class="ra1ar" d="M576 511 H608" marker-end="url(#ra1ah)"/>
  <path class="ra1ar" d="M512 428 V444 H230 V484" marker-end="url(#ra1ah)"/>
  <path class="ra1ad" d="M60 428 V548 H376 V538" marker-end="url(#ra1ah)"/>
  <text class="ra1mut" x="66" y="480" text-anchor="start">行情（撮合用）</text>
  <rect class="ra1f" x="20" y="578" width="14" height="12" rx="2"/>
  <text class="ra1mut" x="40" y="588">同一份因子代码：实盘、回放、回算喂的都是它。黄色是存下来的文件。</text>
</svg>

- **实盘这条路**：行情接入线程把组播包解码成 `Tick`，写进广播环，分片线程里的因子来一条算一条，值交给决策线程。旁边有两份文件在一路记：落盘把广播环里的行情原样录下来，录的是实盘当时看到的样子，丢了的就没有、晚到的按晚到的顺序录；分片线程把每次算出的因子值写进日志。**这两份文件是回放的原料**。
- **回放这条路**：盘后回放器读当天的录像，按行情序号一条条喂给同一份因子代码，算出的值和实盘日志逐值比（[4.1](#reconcile)）。输入和代码都一样，结果就该逐位相同，差一位就说明系统里有不确定的东西。
- **回算这条路**：几年的历史行情先进中间层，按股票重排、合成盘口，只算一次；再切成“一只股票一天”的任务分到多核、多机，每个任务里跑的还是同一份因子代码，结果按天存成因子库（第 3 节）。
- **回测引擎**：策略读因子库里的值决定下单；模拟撮合拿历史行情判断这笔单能不能成交、按什么价成交，要考虑对手价有没有被打到、前面排了多少量、单子从发出到交易所要多久；账户记持仓、资金和盈亏，成交回报再交给策略。撮合是回测才有的一块，实盘里这一步由交易所完成。引擎里的事件循环、撮合怎么估，以及量大了怎么分到多台机器上跑，见[回测平台](/zh/ref/backtest-platform/)。

三种用法加上实盘，喂的都是同一个 `on_tick`，差别只在行情从哪来、算出来的值交给谁。**所以接口只定一个，回测和实盘跑同一份代码**：

```cpp
struct Factor {
    void on_tick(const Tick& t);   // 来一条行情，更新内部状态；Tick 泛指一条行情消息，快照和逐笔都算
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
- **实盘这样调**：行情接入线程把收到的组播包解码成 `Tick`，分片线程拿到一条就调一次 `on_tick`（[交易系统架构 1.1](/zh/ref/trading-architecture/#tick)）。
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

## 3. 批量回算：数据比缓存大几个数量级，瓶颈换成了带宽 {#batch}

这一节只讲因子回算：在几年的历史行情上把每个因子的值算出来，也就是第 1 节的第 2 步。拿这些因子值模拟交易、算收益，才是回测，那是下一步。

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
   | 怎么并行 | 按股票分片，一片绑一个核（[交易系统架构 3.2](/zh/ref/trading-architecture/#shard)） | 按交易日切成任务，单股票因子再按股票切，分到多核、多机 |

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
   - **分层**：逐笔 → 合成订单簿和定时快照（[A 股行情第 5 节](/zh/ref/a-share-market/#book)）→ 公共中间量 → 因子。
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
   - **多机要能单独重跑某一天**：哪天失败就重跑哪天；结果按天逐值比，用的就是 [4.1](#reconcile) 的对账。

5. **批量想向量化，一致想逐条增量**
   - **整列向量化最快**：但运算顺序和实盘逐条增量不同，末位会差；窗口没满、NaN、跨天预热这些边界也容易写成两套。
   - **逐条喂同一个 `on_tick` 最一致**：[第 2 节](#replay)的保证直接成立，代价是用不上整列的向量化，速度靠按天并行和数据布局补回来。

6. **离线批量流水线：代码怎么分层，收盘后的补算为什么要挪回逐条路径**
   - **批量流水线要的是一整张结果**：每只股票、一天里每个时间格一个值，全部算完写成文件。所以因子里除了算下一条要用的状态，还要一张按格的表，一格一行，行情按交易所时间落到第几格就改第几行。
   - **常见的结构是三层**：流水线只认一个接口，因为要算哪些因子、每个跑几组参数，是运行时从配置读的，由一个工厂按因子编号 `new` 出对应的类；表的代码每个因子都一样，只是一格要记的东西不同，所以行的类型留成模板参数；具体因子只写一格记什么、来一条怎么改。
   ```cpp
   // 1. 接口：流水线只认这个
   struct IFactor {
       virtual void on_tick(const Tick& t) = 0;
       virtual double value_at(int bar) const = 0;   // 第 bar 格的值
       virtual void reset() = 0;
       virtual ~IFactor() = default;
   };

   // 2. 表：一格一行，行的类型由具体因子定；每种行都要有 value 这个字段
   template <class Bar>
   struct FactorBase : IFactor {
       std::vector<Bar> bars = std::vector<Bar>(kBarsPerDay);
       double value_at(int i) const override { return bars[i].value; }
   };

   // 3. 具体因子：一格记这一格的累计收益和因子值
   struct ReversalBar { double ret = 0; double value = 0; };
   struct Reversal : FactorBase<ReversalBar> {
       void on_tick(const Tick& t) override;   // 算出格号，改那一行，更新窗口
       void reset() override;
   };
   ```
   - **整个程序分五层**：

     | 层 | 管什么 |
     |---|---|
     | 入口 | 读配置：算哪些因子、每个跑哪几组参数、算哪几天、用哪几个核；然后一天一天交给流水线 |
     | 调度 | 按因子任务调度；起绑核的工作线程；读当天的行情文件，写因子文件，和参考结果逐格比 |
     | 数据 | 全市场的股票数组，一只股票一个对象，装着它当天的行情和时间轴 |
     | 因子 | 上面的接口、按格的表、各个具体因子，和按编号 `new` 对象的工厂 |
     | 基础 | 行情结构体、时间工具、环形队列、配置加载、parquet 读写 |

   - **对象一层套一层**：
      - **流水线持有全市场的股票数组**：一只股票一个对象。
      - **一只股票的对象里有四样东西**：当天的快照，放在开好的定长数组里；当天的时间轴，A 股 4 小时按 3 秒一格是 4801 格；把快照时间换成格号的函数；挂在这只股票上的因子，`vector<unique_ptr<IFactor>>`。
      - **一个因子对象里有两样东西**：按格的表，4801 行，每行一个 `Bar`；它自己的状态，比如窗口、上一个价。
      - **几个因子都要的增量统计放在股票这一层共用**：滚动均值方差、滚动相关系数，用 Welford 的写法，能加一个也能减一个。
      - **数组都是开好的定长**：读写时没有动态分配，代价是有上限，一天的快照数、格数超了要有人拦。
   - **配置怎么变成任务**：每个因子写一个编号和一串参数，每组参数展开成一个任务，输出编号从因子编号往上数。所以枚举里相邻两个因子之间要留够空号：

     | 配置 | 展开成的任务 | 输出编号 |
     |---|---|---|
     | `id: 1000, params: [1, 3, 5, 10]` | 一个参数 n，取 1、3、5、10 各一个 | 1000、1001、1002、1003 |
     | `id: 1010, params: [[1, 5], [3, 20]]` | 两个参数 (n, m)，两组 | 1010、1011 |

   - **跑的顺序**：一天的行情全部读进内存 → 每只股票挂上因子 → 一个线程负责一只股票，按时间把这只股票的行情逐条喂给 `on_tick` → 全部股票算完，逐格读 `value_at` 写文件 → `reset`，换下一个因子。一只股票同一时刻只在一个线程里，因子和表都不跨线程，不用加锁。
   - **同一个因子的几组参数合成一批算**：每只股票同时挂上几个对象，快照只过一遍，再分别写出。
   - **加一个因子动四处**：枚举里加一个编号；写一个 `Bar` 结构体（必须有 `value`）和这个因子的类；工厂的 `switch` 里加一行；配置里加编号和参数，打开比对，和参考结果逐格比。
   - **两处边界要在入口挡住**：启动时就校验配置里的每个编号工厂都认识，不要算到一半才抛异常；快照时间换不出格号时返回空，取行的地方先判空再写。
   - **容易分叉的地方：收盘后把整张表重算一遍**。全天的数据已经在手里，很自然会加一个“收盘后”的函数，把每一格按定义重算、覆盖逐条算出的值。它多半是为了补上没有行情落进来的格：逐条的路径只改有行情的格，空格没人写。
   - **但实盘没有“收盘后”**：值在盘中就要交出去。因子库里的值要是靠收盘后那一遍才算对，因子库和实盘就成了两套逻辑，回测用的值实盘算不出来。
   - **修法：把收盘后做的事挪回逐条路径**。补空格可以在跳格的那一刻做。以“最近 N 格收益之和”这类因子为例，新行情落到的格号比上一条大不止 1，就把中间每一格按收益 0 推进窗口：
   ```cpp
   if (bar != cur) {
       close_bar(cur_ret);                                  // 上一格走完，推进窗口
       for (int g = cur + 1; g < bar; ++g) close_bar(0);    // 中间没有行情的格，收益记 0
       cur = bar;
       cur_ret = 0;
   }
   ```
   - **这样每一格最后一条行情算出的值，就等于收盘后按定义重算的值**：批量流水线把它存进表，实盘把它交给策略，两边跑的是同一个 `on_tick`。空格本身没有行情来，要它的值，就在要值的时刻先补格再读（[因子计算 3.2](/zh/ref/factor-computation/#template) 的读入口）。
   - **改完怎么确认**：同一天，每格取最后一条行情时的值，和收盘后全量重算的结果逐格比，用的就是 [4.1](#reconcile) 第 2 条的对账。

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
>   - **一个核放不下全部状态**：盘中按股票分片（[交易系统架构 3.2](/zh/ref/trading-architecture/#shard)），批量按股票重排（第 4 条）。
>   - **这些都做完缺失还在，各条之间又互不依赖**：往前看几条，提前预取状态（第 4 条）。

> **批量回算怎么选**
> - **因子多、回算不算频繁**：批量也逐条喂同一个 `on_tick`，一份代码，一致性最省心。
> - **某个因子回算特别重**：单写一套向量化的批量版，和增量版逐值对拍，容差按两边的运算顺序定。
> - **不管选哪个**：批量结果都要和实盘录像重放的结果对上，才能拿去做研究。

## 4. 因子一致性：研究原型、因子库、实盘逐值对上 {#consistency}

同一份行情喂进去，研究侧的原型、因子库、实盘三处算出的每个值都要一样（或在约定的容差内），否则回测的结果代表不了实盘。对不上的来源分几层：

- **4.1 是系统这一层**：每天用实盘录像重放、逐值对账，把差异分成代码的和输入数据的。
- **4.2 是数据口径**：累计量、缺失的快照、价格和金额的单位、时间，这些要先和研究侧约定。
- **4.3 到 4.7 是 pandas / NumPy 和 C++ 默认行为不同的地方**：对不上多半不是因子逻辑写错了，是两边的默认行为不同。比如 pandas 默认跳过 NaN，C++ 的算术不会；pandas 的 `std` 默认除以 n − 1，NumPy 默认除以 n。每一条都回答两个问题：两边默认各怎么做，C++ 怎么写才能和研究侧对上。
- **4.8 是对不上时怎么查**：先看差值的样子，再去对应的那一小节找原因。

### 4.1 系统这一层：每天用录像重放，逐值对账 {#reconcile}

1. **核心目标：解决“回测美好、实盘亏钱”时对不上账的问题**
   - **实盘表现比回测差，要先分清是谁的问题**：是策略本身失效了，还是实盘算出来的因子值和回测里不一样。后一种不排除掉，前一种就没法判断。
   - **例子**：某只股票 10:00:00 的因子值，回测里是 0.82，实盘里是 0.79。开仓线是 0.8，回测里这一刻开了仓，实盘没开，两边的收益从这一笔起就对不上了。
   - **对不上的原因分两类**：系统自己的（代码、状态、线程顺序），和输入数据的（丢包、时间口径、数据商修正）。回测和实盘先跑同一份代码（第 2 节），再用每天对账把差异找出来，分两个阶段把这两类分开。

2. **运维机制：每天盘后用实盘录像重放，逐值对账**
   - **盘中把输入和输出都存下来**：落盘读者从广播环里把实盘收到的每条行情原样存下（[交易系统架构 1.4](/zh/ref/trading-architecture/#side)），连同收到时间；分片线程把每次算出的因子值也写进日志。
   - **录的是实盘当时看到的样子**：丢了的那条录不到，晚到的按晚到的顺序录，补回来的按补回来的时刻录。所以重放的输入和实盘的输入一模一样。
   - **盘后用录像重放**：回放器读这份录像，喂给同一个 `on_tick`，得到另一串因子值。
   - **按行情序号逐值比**：把两串值按同一条行情对齐，一个一个比。
      - **同一份二进制、同一份输入，结果应该逐位相同**：阈值可以是 0，差一位就说明哪里有不确定的东西。
      - **和另一种语言写的研究原型比，才需要容差**：例如相对误差 1e-9，因为两边的浮点运算顺序本来就不同。
   - **例子**：全市场 5000 只股票，快照约 3 s 一个，一天交易 4 小时，约 14400 ÷ 3 × 5000 ≈ 2400 万个值，逐个比一遍要几秒到几十秒。
   - **改了代码也靠它做回归**：同一天的录像，改前改后输出逐位不变，才算没改坏；要变的，变化只出现在该变的因子上。

3. **差异排查：两阶段归因，先排除系统，再看数据**
   - **阶段一：实盘录像 vs 盘后重放，排除系统级问题**
      - **输入和代码都一样，结果还不同，只能是系统里有不确定的东西**。
      - **状态没重置、预热不一致**：开盘那一段对不上，等窗口滚过去才对上。修法是把预热条数和重启恢复的方式定成固定规则，回测照同一套来。
      - **多线程汇合顺序不固定**：浮点加法不满足结合律，截面汇总按“谁先算完先加谁”，每次结果末几位都不同。修法是按股票代码的顺序加（[交易系统架构 3.4](/zh/ref/trading-architecture/#barrier)）。
      - **未定义行为**：没初始化的变量、越界读，每次跑出来的值不一样。
      - **因子里读了系统时钟**：重放时拿到的是盘后的时间。修法是只用 `t.exch_time`。
   - **阶段二：实盘录像 vs 数据商历史文件，排除数据源差异**
      - **阶段一对上了，代码就是确定的；两份输入喂同一份代码还有差，只能是输入不同**。研究员的回测读的是数据商文件，所以最常发现差异的是这一步。
      - **UDP 组播丢包**：实盘少一条，数据商文件是事后补齐的。例如丢了 10:00:03 的快照，下一个快照算出的成交量增量就是 6 s 的量。
      - **网络延迟跨界切 bar**：交易所时间 09:59:59.990 的行情，10:00:00.002 才到，按收到时间就进了下一根 bar。修法是两边统一按交易所时间切。
      - **数据商事后修正**：改过错误数据，单位和取整也可能不同，例如成交金额舍掉了角分。
   - **两个阶段都对上了还有差，才是策略本身的问题**。

### 4.2 数据口径：写因子时要和研究侧对齐的地方 {#caliber}

| 地方 | 会怎么对不上 |
|---|---|
| 累计量相减 | 快照的量、额、笔数是开盘起的累计值。当天第一张，pandas `diff()` 给 NaN，C++ 上一张从 0 起算会得出开盘以来的全部量 |
| 快照不是每 3 秒都有 | 没变化通常不推，切 bar 时空格子用前值补还是留空要约定 |
| 价格和金额 | 价格是放大过的整数，倍数按数据商文档并用真实数据核；有的数据商成交金额是去掉角分的整数元，零股、科创板 201 股这类会少几毛，要准就用价×量 |
| 深圳撤单混在成交里 | 直接用逐笔成交算均价，价格 0、数量非 0 的撤单行会把均价拉低 |
| 时间 | 交易所时间还是本机收到时间；bar 左闭右开还是右闭；集合竞价和午休怎么切 |
| 快照和逐笔对齐 | 两者节拍和时间精度不同，按时间戳把逐笔加到快照时刻不一定等于快照的累计量；严格对齐要用逐笔重建盘口再比 |

### 4.3 数值本身：浮点加法不满足结合律 {#float}

#### 4.3.1 求和顺序 {#sum-order}

1. **为什么加的顺序会改结果**
   - **每做一次加法都要舍入一次**：所以 $(a+b)+c$ 和 $a+(b+c)$ 的末位可能不同。
   - **顺序一变，末几位就跟着变**：同样一列数，换个顺序加，结果的最后几位就可能不一样。

2. **两边各是怎么加的**

   | | 怎么加 |
   |---|---|
   | NumPy `np.sum` | 成对求和：分块两两相加，误差比顺序累加小 |
   | pandas `rolling(...).sum()` / `.mean()` | 窗口滑动时加新减旧，带误差补偿（Kahan 求和） |
   | C++ 手写循环 | 从头到尾顺序累加；滚动窗口常写成 `sum += x_new - x_old` |

   - **一次性求和通常只差末一两位**：C++ 用一个循环从头加到尾，和 `np.sum` 的成对求和比，一般只在最后一两位上不同。
   - **滚动窗口的误差会越积越大**：C++ 加新减旧时没有补偿，跑上一整天，误差一直累积，后面的值可能差得比末位还多。

3. **C++ 怎么和研究侧对上**
   - **先和研究侧定好标准**：是在容差内一致就行，还是要求逐位一致。**这一步要先定，后面的写法都取决于它**。
   - **容差内一致就按相对误差比**：例如 $|a-b| \le 10^{-9}\max(|a|,|b|)$ 就算对上。
   - **逐位一致就得按同样的顺序加**：一次性求和照成对求和的分块方式写；滚动窗口也加上 Kahan 补偿，或者每隔一段从头重算一次窗口和，把累积的误差清掉。

#### 4.3.2 数学函数 {#math-fn}

- **`exp`、`log`、`pow` 的实现两边可能不同**：NumPy 在支持 AVX-512 的机器上用自己的向量化实现，C++ 调的是 glibc 的实现，结果可能差一两个末位单位（ulp）。
- **只有要求逐位一致时才看得到**：差的量级很小，按容差比的话不会被发现。
- **先查两边是不是同一台机器、同一个库**：机器或库版本不同，这一类差别就可能冒出来。

### 4.4 缺失值和窗口 {#nan-window}

#### 4.4.1 NaN {#nan}

1. **两边默认怎么处理 NaN**

   | | 默认行为 |
   |---|---|
   | pandas `sum` / `mean` | 跳过 NaN（`skipna=True`）；全是 NaN 时，`sum` 得 0，`mean` 得 NaN |
   | NumPy `np.sum` / `np.mean` | NaN 会传染，结果是 NaN；要跳过得用 `np.nansum` / `np.nanmean` |
   | C++ 算术 | 和 NumPy 一样，NaN 一路传下去 |
   | C++ `std::max(a, b)` | 结果取决于参数顺序：`std::max(NaN, 1.0)` 得 NaN，`std::max(1.0, NaN)` 得 1.0 |

   - **例子**：`[1, NaN, 3]` 求平均，pandas 跳过 NaN 得 $(1+3)/2=2$；C++ 直接 `sum / n` 得 NaN；跳过了 NaN 却仍除以 3，得 $4/3$。

2. **`std::max` 的结果为什么看参数顺序**
   - **它只比一次大小**：`std::max(a, b)` 只做一次 `a < b`，成立就返回 `b`，否则返回 `a`。
   - **和 NaN 比较永远是 false**：所以只要有一个参数是 NaN，`a < b` 就不成立，它总是返回第一个参数。
   - **想忽略 NaN 就用 `std::fmax`**：它碰到一个 NaN 时会返回另一个数。

3. **C++ 怎么对上 pandas**
   - **显式写逻辑跳过 NaN**：累加之前先判断 `std::isnan(x)`，是 NaN 就不加。
   - **单独记下非 NaN 的个数**：平均值除以这个个数，不除以窗口长度，否则就是上面 $4/3$ 那种错法。
   - **全是 NaN 时照 pandas 的约定输出**：`sum` 给 0，`mean` 给 NaN。
   - **C++ 的算术不会替你跳过 NaN，要对上 pandas，每一处都得显式写出来**。

#### 4.4.2 ddof：方差的分母 {#ddof}

| | 默认分母 |
|---|---|
| pandas `std` / `var`，包括 `rolling(...).std()` | n − 1（`ddof=1`，样本标准差） |
| NumPy `np.std` / `np.var` | n（`ddof=0`） |

- **研究员用的是除以 n − 1 的那个**：研究员在 pandas 里调 `std`，默认得到的就是样本标准差。
- **例子**：`[1, 2, 3]` 的均值是 2，偏差平方和是 2，除以 3 得方差 0.667，除以 2 得 1。
- **除错了分母，每个值都偏同一个比例**：C++ 照教科书公式除以 n，窗口 20 时标准差差 $\sqrt{20/19}$ 倍，约 2.6%。**差值是固定比例，一眼就能认出是 ddof**。

#### 4.4.3 rolling 的前几个值 {#rolling}

1. **pandas 窗口没攒满时输出 NaN**
   - **默认 `min_periods=n`**：`rolling(n)` 的窗口里凑不满 n 个**非 NaN** 的值，就输出 NaN。
   - **所以开头前 n − 1 个都是 NaN**：例如 `rolling(3).mean()` 作用在 `[1, 2, 3, 4]` 上，输出是 `[NaN, NaN, 2, 3]`。
   - **中间夹一个 NaN 也一样**：这个 NaN 留在窗口里的 n 步，输出全是 NaN。
   - **按时间开的窗口规则不同**：`rolling("5min")` 这类默认 `min_periods=1`，有一个值就出数。

2. **C++ 怎么对上**
   - **自然写法从第一条就出值**：同样的输入，C++ 会输出 `[1, 1.5, 2, 3]`，前 n − 1 个对不上，窗口里有 NaN 时也对不上。
   - **C++ 要维护窗口里非 NaN 的个数，个数不够 n 就输出 NaN**。

#### 4.4.4 ewm 的 adjust {#ewm}

1. **ewm 是什么，因子里为什么常用**
   - **ewm 是指数加权移动平均**：和 `rolling(n).mean()` 一样是求平均，但不只看最近 n 个，而是看全部历史，最新的权重是 1，往前一个是 $1-\alpha$，再往前是 $(1-\alpha)^2$，越旧的权重越小。
   - **因子里常拿它平滑成交量、价差、收益这类噪声大的序列**：近的数据说话更多；也没有 rolling 那种硬边界，一个大值不会在第 n + 1 步突然整个掉出窗口。
   - **它天生适合逐 tick 增量算**：递推只要记住上一步的一个数，每来一条 O(1) 更新。
   - **`span` 换算成 $\alpha$**：$\alpha = 2/(\text{span}+1)$，`span=10` 时 $\alpha \approx 0.18$，大致相当于最近 10 条的平均。
   - **`adjust` 管的只是开头**：历史还短时，这个加权平均怎么算，下面两种算法就差在这里。

2. **pandas 有两种算法，默认的不是递推**
   - **`adjust=True`（默认）按全部历史加权**：每一步都用到目前为止的全部数据，按权重 $(1-\alpha)^i$ 加权，再除以权重之和：

   $$y_t=\frac{\sum_{i=0}^{t}(1-\alpha)^i\,x_{t-i}}{\sum_{i=0}^{t}(1-\alpha)^i}$$

   - **`adjust=False` 是递推**：这也是 C++ 最自然的写法：

   $$y_t=(1-\alpha)\,y_{t-1}+\alpha\,x_t,\qquad y_0=x_0$$

3. **两种算法差在开头**
   - **例子**：取 $\alpha=0.5$，数据是 `[10, 0]`。递推得 $y_1=0.5\times0+0.5\times10=5$；`adjust=True` 得 $y_1=\dfrac{1\times0+0.5\times10}{1+0.5}\approx3.33$。
   - **递推让第一个值的权重偏大**：$y_0=x_0$ 相当于把还没出现的历史全当成 $x_0$；`adjust=True` 只按真实出现过的数据加权。
   - **往后差距越来越小**：第一个值的权重按 $(1-\alpha)^t$ 衰减，权重之和趋近 $1/\alpha$，两种算法慢慢收敛到一起。
   - **大约 25 条以后两种算法就几乎一样**：$\alpha \approx 0.18$ 时，$(1-\alpha)^{25} \approx 0.007$，第一个值的影响已不到 1%。因子如果每天开盘重新开始算，每天开头这一段都会对不上。
   - **ewm 对不上，典型的样子是开头差得大、后面慢慢收敛**。

4. **C++ 怎么对上 `adjust=True`**
   - **分子和分母各自递推，每步相除**：两者每步都先乘 $1-\alpha$，分子再加 $x_t$，分母再加 1，输出两者之比。这样仍是 O(1) 的增量计算。
   - **`span`、`halflife` 换算 $\alpha$ 的公式照抄 pandas**：例如 $\alpha = 2/(\text{span}+1)$，换算写错了，每个值都会对不上。

### 4.5 取整和整数 {#rounding}

#### 4.5.1 四舍五入 {#round}

1. **正好在 .5 时两边取的方向不同**

   | | 结果 |
   |---|---|
   | Python `round`、`np.round`、pandas `.round` | 取偶数：`round(2.5)` 是 2，`round(3.5)` 是 4 |
   | C++ `std::round` | 远离 0：`std::round(2.5)` 是 3，`std::round(-2.5)` 是 −3 |

2. **二进制表示本身也会改变取整的结果**
   - **`2.675` 存不准**：它在二进制里存的是 2.67499999…，所以 Python `round(2.675, 2)` 得 2.67，不是 2.68。
   - **C++ 也有同样的问题**：`std::round(x * 100) / 100` 里乘 100 这一步也会舍入，结果不一定和 Python 一样。
   - **价格这类本来就是定点的数，一直用放大后的整数存，不在浮点上取整**。

#### 4.5.2 整数除法和取模 {#int-div}

1. **两边的规则**

   | | `7 / 2` | `-7 // 2` 或 `-7 / 2` | `-7 % 2` |
   |---|---|---|---|
   | Python | 3.5（`/` 是真除法） | −4（`//` 向负无穷取整） | 1（符号跟除数） |
   | C++（两个整数） | 3（整数除法） | −3（向 0 截断） | −1（符号跟被除数） |

2. **最常犯的是两类错**
   - **C++ 两个整数相除会丢掉小数**：例如成交量除以笔数求平均每笔量，Python 的 `/` 得小数，C++ 两边都是整数时直接截断。**这是最常见的一类**。
   - **负数时取整方向不同**：算时间桶编号时最容易遇到，例如时间减去基准时刻得到负数（集合竞价在 9:30 之前），Python 的 `//` 和 C++ 的 `/` 给出的桶号差 1。

#### 4.5.3 溢出 {#overflow}

- **Python 的整数不会溢出**：位数不够会自动变长。
- **NumPy、pandas 的 int64 会溢出而且不报错**：超出范围直接回绕。
- **C++ 有符号整数溢出是未定义行为**：编译器可能按“不会溢出”来优化，结果不可预测。
- **最容易撞上的是金额**：价格放大 10000 倍存成整数，100 元就是 1,000,000，再乘 100 万股是 $10^{12}$，远超 int32 的上限（约 $2.1\times10^9$）。
- **价×量一律用 int64 或 double，并且先转类型再相乘**。否则乘法本身已经在 int32 里溢出了，转换来不及救。

#### 4.5.4 类型 {#types}

- **带 NaN 的整数列在 pandas 里会变成 float64**：除非用可空整数类型 `Int64`，所以研究侧的“成交量”可能其实是浮点；超过 $2^{53}$ 的整数转成 float64 还会丢精度。
- **float32 只有约 7 位有效数字**：C++ 为了省内存用 `float` 存价格或因子值，和 pandas 的 float64 比，从第 7、8 位开始就不同了。

### 4.6 排名和时间 {#rank-time}

#### 4.6.1 rank {#rank}

1. **pandas 默认给并列的取平均名次**
   - **截面因子常用排名**：对全市场股票排名，再归一化到 0–1。
   - **同值用 `method="average"`**：并列的取它们名次的平均，例如两只并列第 3，都记 3.5。
   - **NaN 不参与排名**：结果也是 NaN（`na_option="keep"`）。

2. **C++ 的自然写法按下标给名次**
   - **排序后按位置编号**：这相当于 `method="first"`，同值的按出现顺序排成 3、4。
   - **同值并不少见**：停牌股的收益都是 0，涨停股的收益相同，名次就在这些股票上对不上。

3. **C++ 怎么对上**
   - **给同值的一段赋平均名次**：排序后找出值相同的一段，每只都记这段名次的平均。
   - **`pct=True` 除的是非 NaN 的个数**：不是股票总数，有停牌、缺数据的股票时两者不同。

#### 4.6.2 时间切分和前视 {#time}

- **bar 的边界和标签要照研究侧来**：区间是左闭右开还是左开右闭，标签用起点还是终点。pandas `resample` 按分钟切时默认左闭右开、标签在左；研究侧可能改过参数，要照着它的来。
- **bar 什么时候算结束，两边可能不同**：研究侧用 `shift(1)` 保证 t 时刻只用到 t 之前的数据；C++ 逐条收数据，只有下一条数据的时间越过边界、或者定时器到点时，才知道一根 bar 结束了。**触发时机定得不一样，同一根 bar 用到的数据就不一样**。
- **午休和集合竞价要单独约定**：11:30–13:00 中间没有数据，13:00 那根 bar 跟谁连在一起；9:25 集合竞价的成交归入哪根 bar，两边都要按同一个规则。
- **时序对齐的更多内容**：整理在[因子计算第 2 节](/zh/ref/factor-computation/#stream)。

### 4.7 编译选项：同一份 C++ 代码，换个选项结果就变 {#flags}

1. **三个选项各会不会改结果**

   | 选项 | 会不会改浮点结果 | 为什么 |
   |---|---|---|
   | `-O2` → `-O3` | 一般不会 | 只要不放开结合律，编译器不能为了向量化改变加法顺序 |
   | `-march=native` | 会 | 打开 FMA 指令后，GCC（默认的 gnu++ 方言）和 Clang 会把 `a * b + c` 合成一条乘加，中间结果不再单独舍入，末位就变了 |
   | `-ffast-math` | 会，而且可能更糟 | 放开结合律；假定没有 NaN 和无穷大；把非常小的数（次正规数）当成 0 |

2. **因子代码里不能开 `-ffast-math`**
   - **它会删掉 NaN 判断**：它假定没有 NaN，`std::isnan(x)` 可能被直接优化成 false，4.4 里所有跳过 NaN 的写法都会悄悄失效。
   - **它会重排求和**：放开结合律后，求和顺序会被向量化重排，4.3 的问题又回来了。

3. **想要 `-march=native` 又不要 FMA**
   - **加上 `-ffp-contract=off`**：这样能用上 `-march=native` 的其他指令，但编译器不再把乘和加合成一条 FMA。
   - **研究侧也要定死实现**：NumPy 内部也有自己的向量化实现，逐位一致的前提是两边都定死实现方式，不只管 C++ 这一边。

4. **构建配置要统一**
   - **例子**：回测框架用 `-O2`、实盘用 `-O3 -march=native`，同一份因子代码就可能在末位上对不上。
   - **研究侧和实盘侧的编译选项要一致，并写进构建配置**。

### 4.8 对不上时：先看差值的样子 {#diagnose}

1. **按差值的形状定位原因**
   - **不要一条条看**：逐值比完以后，先看差值在时间上怎么分布，形状通常直接指向原因。

   | 差值的样子 | 先查什么 |
   |---|---|
   | 整列错开一格（C++ 的第 t 个等于 pandas 的第 t + 1 个） | 时间对齐、`shift`、bar 的边界和标签 |
   | 只有开头几个不对，后面都对 | `min_periods`；ewm 的 `adjust`；初始值 |
   | 开头差得大，往后越来越小 | ewm 的 `adjust=True` 和递推写法的差别 |
   | 越往后差得越大 | 滚动窗口加新减旧，浮点误差在累积 |
   | 每个值都差同一个比例 | ddof；单位或放大倍数（价格放大了 10000 倍还是 100 倍） |
   | 零星几个点差很多 | NaN 的处理；停牌、涨跌停；同值排名；整数除法截断 |
   | 全部只差末一两位 | 求和顺序、FMA、数学函数实现；按约定的容差判过 |

2. **从源头避免：两边跑同一份实现**
   - **把 C++ 实现暴露给 Python**：同一份 C++ 因子代码用 pybind11 暴露给研究侧，研究和实盘跑的是同一个实现，一致性从源头上保证。
   - **代价是研究员迭代变慢**：改因子要改 C++、重新编译。
   - **所以通常只对稳定下来的因子这样做**。
