---
title: "交易系统笔记 #2:内存序与缓存行"
date: 2026-09-15
slug: "memory-ordering-false-sharing-dependency-chains"
description: "为什么 store buffer 让你自己的写对别的核不可见,为什么 x86 禁三放一,release/acquire 怎么买回刚好够用的顺序,为什么伪共享和读到旧值是完全不同的问题,以及为什么循环展开有一个最优的累加器个数。"
summary: "store buffer 和缓存一致性协议是同一套硬件,却带出两个毫不相干的工程问题。一个是正确性:线程有没有按正确的顺序看到正确的值——靠 memory_order 和 release/acquire 配对解决。另一个是性能:就算每个值都读对了,碰共享的或有依赖的数据要花多少周期——靠缓存行布局和指令调度解决。把两者混为一谈,是系统编程这一块最常见的困惑。"
chapter: 1
categories: [Systems]
tags: [cpp, memory-model, atomics, cache-coherence, false-sharing, mesi, x86, hft, low-latency, pipelining]
toc: true
homepage: false
---

线程 A 写 `x = 1`,线程 B 读 `x`。B 一定能看到 `1` 吗?如果 A 在写 `x` 之前还写了 `y`,B 看到新的 `x` 之后,能保证看到新的 `y` 吗?再来一个完全不同的问题:两个线程各自累加**自己的**计数器,不共享任何变量,代码里也没有任何 bug——为什么两个计数器挨着放在同一个结构体里时,循环会慢十倍?

这两个问题由同一套硬件回答——核、64 字节的缓存行、让它们保持一致的一致性协议——这也正是它们容易被搅在一起的原因:"缓存行被作废、又重新加载"这句话,在两个问题的解释里都会出现,却是出于不相干的理由。但它们是两个问题。第一个关于**正确性**:我读到的值对不对?答案非对即错,工具是 C++ 内存模型——`std::atomic`、`memory_order`、release/acquire。第二个关于**性能**:假设每个值都已经读对了,花了多少个周期?它没有对错,只有一个数,工具是缓存行布局和指令调度。

![同一条缓存行,两个问题:一枚检验正确性的印章和一块秒表,对着同一条 64 字节的缓存行](/images/memory-model-cache-line/two-axes.jpg)

这篇把两条轴分开讲。第 1 部分是正确性:乱序在物理上从哪来,release/acquire 怎么买回刚好够用的顺序。第 2 部分用伪共享跨到性能这条轴——两者最容易被混淆的地方就在这里,所以会把区别一条一条摆出来。第 3 部分还是性能,但换了一种资源:从缓存行换成流水线上的依赖链。

---

## 1. 正确性:我读到的值对不对

### 1.1 store buffer:你自己的写,对别人"撒谎"

先说一个第一次听会觉得不对的事实:**你的线程执行 `x = 1` 时,这个写并不是直接进缓存的。** 它先进一个每个核私有的小结构,叫 **store buffer**——可以把它想成一个小本子,核先把写记在本子上,之后再真正归档——然后这条指令立刻就退休了。你的线程不等它,直接执行下一条指令。

硬件为什么这么做?因为真正把一个写提交到一条本核还没独占的缓存行上,代价很高:一致性协议(MESI)要给所有可能缓存了这一行的核发 **RFO**(Request For Ownership),等它们把副本作废,写才能落地。这一来一回要几十纳秒。要是流水线每遇到一次写都停下来等,流水线就白设计了。所以 store buffer 存在的唯一目的,是**把"指令做完了"和"写对所有人可见了"解耦**:指令一记进本子就退休,RFO 和真正的缓存更新在后台异步进行,行什么时候到手什么时候办。

这就制造出一个缺口,这篇里所有关于内存序的内容都是它的后果:**在一段时间里——通常几十纳秒,对 4 GHz 的核来说相当漫长——一个写从线程 A 的角度看已经"发生"了,但别的核还看不到,因为它还躺在 A 私有的小本子里。**

注意这里的不对称:线程 A 自己永远察觉不到这个缺口。A 写了 `x`,隔三条指令再读 `x`,CPU 会直接从 store buffer 里把值转发过来(叫 **store-to-load forwarding**,3.4 会再讲到它)——A 看自己的写,永远是程序顺序。缺口只能从*外面*看到:从别的核的角度,"A 的写指令退休"和"这个写在别处可见"之间,有一段真实的物理延迟。它不是 bug,也不是编译器搞的鬼,而是为了在 4 GHz 下活下去而缓冲写的直接、必然的后果。

接下来的内容都围绕这一个缺口:它怎么变成一类特定的 bug(1.2–1.4),以及 C++ 怎么给你一套词汇,只在需要的地方把它补上,别处一概不补(1.5)。

### 1.2 invalidate queue:接收方的收件箱

store buffer 解释了为什么 *A 的* 写会延迟。接收方还有一个镜像结构,解释了为什么 A 的写已经离开小本子、RFO 也到了,B 还可能继续读到旧值。

核 B 的缓存里有一条行,核 A 的 RFO 来了要求作废它,B 也不必立刻处理这个作废。它可以把消息丢进一个 **invalidate queue**——收件箱——并且马上给 A 回确认,让 A 不用等 B。B 之后有空再处理收件箱。如果 B 在处理掉收件箱里那条作废请求*之前*,就执行了对这个地址的 load,它仍然可能读到旧的缓存值——尽管按协议,这条行已经算作废了。

于是每一次跨核写的两侧,各有一个独立的缓冲结构:store buffer 推迟了*发布*,invalidate queue 推迟了*察觉*。合在一起,它们就是你在多核 x86 机器上会调试到的所有内存乱序的物理根源。

<svg viewBox="0 0 760 460" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="写方核的 store buffer 和读方核的 invalidate queue,在写指令退休和写对别处可见之间制造出一个可见性缺口" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .bg    { fill: #fbfaf7; }
    .panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .ink   { fill: #1c1b18; }
    .muted { fill: #6b6558; }
    .core  { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .buf   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .inbox { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.6; }
    .line  { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .arrow { stroke: #8a8474; stroke-width: 2; fill: none; marker-end: url(#ahz); }
    .rfo   { stroke: #c15b3f; stroke-width: 2; fill: none; marker-end: url(#ahz2); }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .lbl   { fill: #3a372f; font-size: 11px; }
    .cap   { fill: #6b6558; font-size: 10.5px; }
    .gap   { fill: #c15b3f; font-size: 11px; font-weight: 700; }
      :root[data-theme="dark"] .bg { fill: #17161b; }
      :root[data-theme="dark"] .panel { fill: #201f26; stroke: #3a3945; }
      :root[data-theme="dark"] .ink { fill: #e9e7ef; }
      :root[data-theme="dark"] .muted { fill: #a19caf; }
      :root[data-theme="dark"] .core { fill: #2a2933; stroke: #47454f; }
      :root[data-theme="dark"] .buf { fill: #33421f; stroke: #8fb257; }
      :root[data-theme="dark"] .inbox { fill: #4a2f2c; stroke: #8f5a4c; }
      :root[data-theme="dark"] .line { fill: #23262c; stroke: #3f4650; }
      :root[data-theme="dark"] .arrow { stroke: #9a9384; }
      :root[data-theme="dark"] .rfo { stroke: #e0795b; }
      :root[data-theme="dark"] .title { fill: #e9e7ef; }
      :root[data-theme="dark"] .lbl { fill: #d7d3c8; }
      :root[data-theme="dark"] .cap { fill: #a19caf; }
      :root[data-theme="dark"] .gap { fill: #e0795b; }
  </style>
  <defs>
    <marker id="ahz" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ahz2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="760" height="460" rx="10"/>
  <text class="title" x="24" y="30">为什么 A 的写已经"退休",B 还能读到旧的 x</text>
  <rect class="panel" x="24" y="48" width="320" height="230" rx="8"/>
  <text class="muted" x="40" y="70" font-size="12" font-weight="700">核 A(写方)</text>
  <rect class="core" x="40" y="86" width="120" height="46" rx="6"/>
  <text class="lbl" x="50" y="106">x = 1</text>
  <text class="cap" x="50" y="122">写指令</text>
  <rect class="buf" x="40" y="148" width="270" height="46" rx="6"/>
  <text class="lbl" x="50" y="168" font-weight="700">store buffer("小本子")</text>
  <text class="cap" x="50" y="184">x=1 记进本子——指令就在这里退休</text>
  <path class="arrow" d="M100 132 L100 148"/>
  <path class="rfo" d="M310 171 C 350 171, 372 200, 392 228"/>
  <text class="cap" x="316" y="214" fill="#c15b3f">RFO 异步发出</text>
  <text class="gap" x="40" y="240">A 已经认为 x=1 做完了。</text>
  <text class="gap" x="40" y="256">别的核还一个都看不到。</text>
  <rect class="panel" x="416" y="48" width="320" height="230" rx="8"/>
  <text class="muted" x="432" y="70" font-size="12" font-weight="700">核 B(读方)</text>
  <rect class="inbox" x="432" y="86" width="270" height="46" rx="6"/>
  <text class="lbl" x="442" y="106" font-weight="700">invalidate queue("收件箱")</text>
  <text class="cap" x="442" y="122">x 的 RFO 躺在这里,确认已立刻回给 A</text>
  <rect class="core" x="432" y="148" width="120" height="46" rx="6"/>
  <text class="lbl" x="442" y="168">读 x</text>
  <text class="cap" x="442" y="184">可能在收件箱清空前就执行</text>
  <path class="arrow" d="M492 132 L492 148"/>
  <text class="gap" x="432" y="240">B 的读要是抢在自己的收件箱前面,</text>
  <text class="gap" x="432" y="256">读到的仍是旧的缓存值 x。</text>
  <rect class="panel" x="220" y="300" width="320" height="140" rx="8"/>
  <text class="title" x="236" y="324" font-size="12.5">什么能补上这个缺口</text>
  <text class="cap" x="236" y="346" font-size="11">默认什么都不能——这个缺口就是硬件的正常行为。</text>
  <text class="cap" x="236" y="364" font-size="11">x86-TSO 禁止它和其他地址的读写乱序</text>
  <text class="cap" x="236" y="380" font-size="11">(StoreStore / LoadLoad / LoadStore)——</text>
  <text class="cap" x="236" y="396" font-size="11">但正是从这个缺口生出来的 StoreLoad 乱序,</text>
  <text class="cap" x="236" y="412" font-size="11" font-weight="700">是 x86 唯一允许的。1.5 讲怎么补上它。</text>
</svg>

> 图:A 的写一进自己的 store buffer 就退休了,但真正去拿缓存行的 RFO 是异步的。B 的 invalidate queue 吸收这个 RFO,不让 B 的流水线停下,于是一个抢在 B 自己收件箱前面的 load,仍可能看到写之前的值。两个缓冲存在的理由是同一个——别让流水线为一次跨核往返停下来——合起来就是 1.3 里四种乱序的全部物理原因。

### 1.3 四种乱序,以及 x86 留下的那一种

在一般的(形式化的)共享内存模型里,对**不同**地址的一个读和一个写,在另一个观察者看来,恰好有四种乱序方式:

| 乱序 | 含义 | x86 允许吗? |
|---|---|---|
| **StoreStore** | 你的两个写以错乱的顺序变得可见 | 不允许 |
| **LoadLoad** | 你的两个读以错乱的顺序读内存 | 不允许 |
| **LoadStore** | 后面的写在前面的读完成之前就可见了 | 不允许 |
| **StoreLoad** | 后面的读在前面的写可见之前就执行了 | **允许** |

x86 用的模型叫 **TSO**(Total Store Order),一句话概括就是"禁三放一"。被禁止的三种由硬件免费保证——一条普通的 `mov` 自带这种顺序,不用加屏障。被允许的那一种 StoreLoad,*恰好*就是 1.1 里 store buffer 的那个缺口换了个名字:你的写躺在小本子里,后面一个对另一个地址的读可以立刻执行,于是从别的核看,你的读好像在你之前的写之前就完成了。经典的"我先置了标志位、再去读另一个变量,另一个线程看到的顺序却是反的"这类 bug,教科书上的原因就是它——而在 x86 上,这是你**唯一**需要显式防范的乱序,其他组合硬件自己就禁止了。

### 1.4 硬件看不见的 bug:编译器先动了手

怪 CPU 之前,先查编译器。这个循环:

```cpp
while (ready == false) {}
```

看上去每一轮都在读内存。可是没有 `volatile` 或 `std::atomic`,编译器有权假设这个线程之外没有任何东西会改 `ready`,于是只把它读进寄存器一次,把整个循环改写成:

```cpp
if (!ready) { while (true) {} }   // 死循环——再也不会去读内存了
```

这和 CPU 的内存模型**毫无关系**。它纯粹是编译器层面的优化,之所以合法,恰恰因为普通的(非原子、非 volatile)内存没有承诺"可能有别的线程在盯着它"。`volatile` 能阻止编译器这么做——它强制每一轮都真的读一次——但它**只**做这件事。**`volatile` 不等于同步。** 它不规定和其他内存操作之间的顺序,也管不了前面讲的 store buffer / invalidate queue 那个缺口。一个 `volatile bool` 照样会让读者在缺口存在的整段时间里看到旧值,它只保证编译器不会在你等待的时候把这次读藏起来。真正修好这个循环要用 `std::atomic<bool>`,也就是下一节。

### 1.5 release/acquire:买回刚好够用的顺序

带上正确 `memory_order` 的 `std::atomic`,会**恰好在你点名的地方**补上 1.1–1.3 的缺口,别处一概不补——这种精确就是它的设计意图。C++ 提供六种内存序:`relaxed`、`consume`(实际上已被废弃,编译器把它当 `acquire`)、`acquire`、`release`、`acq_rel` 和 `seq_cst`。实践中最要紧的是 **release** 和 **acquire**,最干净的心智模型是**发布/订阅**:

- **release** 写在说:*"我在这之前写的东西都定稿了——发布吧。"*
- **acquire** 读在说:*"给我最新的值,而且我在这之后做的任何事,都不许被重排到它前面。"*

当一个 acquire 读**在同一个原子变量上**看到了一个 release 写写下的值,两者就配成一对,C++ 保证跨线程有一条 **happens-before** 边:写方在 release 之前做的一切,对读方在配对的 acquire 之后做的一切都可见。别的东西都不必是原子的。一个最小的例子:

```cpp
struct SPSCFlag {
  std::atomic<bool> ready{false};
  int payload = 0;   // 普通 int——不是原子的,也不需要是
};

// 生产者线程
void publish(SPSCFlag &f, int value) noexcept {
  f.payload = value;                                // 1. 普通写
  f.ready.store(true, std::memory_order_release);    // 2. release:"1 已定稿"
}

// 消费者线程
auto try_consume(SPSCFlag &f) noexcept -> std::optional<int> {
  if (f.ready.load(std::memory_order_acquire)) {     // 3. acquire:和 2 配对
    return f.payload;                                // 4. 保证看到第 1 步的值
  }
  return std::nullopt;
}
```

`payload` 是一个普通的、非原子的 `int`。它之所以安全,**只**因为有 `ready` 上的 release/acquire 配对把它带了过去——交易系统里你能找到的每一个 SPSC(单生产者单消费者)环形队列,都是这个标准形状:一个原子下标负责同步,其余全是普通变量。

### 1.6 为什么 x86 上它几乎免费,ARM 上却要收钱

回到 1.3 那张"禁三放一"的表。acquire 和 release 只需要禁止 x86-TSO 在每条普通 `mov` 上*已经*禁止了的乱序——LoadLoad、LoadStore、StoreStore。所以在 x86 上,`memory_order_acquire` 的读和 `memory_order_release` 的写,编译出来就是普通的读和普通的写;硬件本来就会遵守这个顺序。**acquire/release 在 x86 上几乎免费**——这不是巧合,这正是 C++ 内存模型要单独设 `acquire`/`release`、而不是只有"relaxed 或者全序"的原因。

`seq_cst` 则额外禁止了 x86 *唯一*允许的那种乱序——StoreLoad——这需要一条真正的屏障:`MFENCE`。这是 x86 上唯一一种相对普通读写真正昂贵的原子操作,也是为什么 `std::atomic` 的*默认*内存序(不写就是 `seq_cst`)对只需要发布/订阅语义的代码来说,付了不必要的钱。

在 ARM 这种弱内存序架构上,"禁三"一样都不是免费的——除非你明确要求,硬件可以重排全部四种组合,所以 acquire/release 需要真正的指令(ARMv8 上的 `LDAR`/`STLR`,ARMv7 上显式的 `DMB` 屏障)。这就是为什么 C++ 内存模型是抽象地规定的,而不是简单地"照 x86 那样做":语义可移植,价钱却取决于架构;在 x86 上因为 acquire/release 几乎免费而"碰巧能跑"的代码,到了 ARM 上可能明显变慢——如果有人习惯性地用了 `volatile` 而不是 `atomic`,那就是直接出错。

---

## 2. 伪共享:这里从来就不是正确性问题

两条轴就在这里彻底分开,所以值得说得明明白白:**下面的一切,都可能发生在已经 100% 正确的代码上**——每次读都看到正确的值,每个 `memory_order` 都恰到好处,按第 1 部分的标准一个 bug 都没有。这是一个纯粹的性能问题,加多少原子操作、多少屏障都修不好它。

### 2.1 一致性的单位是 64 字节,不是一个变量

MESI 协议不会作废单个变量——它作废的是**缓存行**,而在几乎所有现役 x86 核上,一行固定是 64 字节。两个线程各自拥有一个毫不相干的 `int`,而这两个 `int` 恰好落在同一条 64 字节的行里——比如结构体里相邻的两个字段——那么线程 A 每写一次*它自己的*变量,就会作废*整条行*,连带线程 B 的变量,逼着 B 去重新加载它从没打算共享的数据。这就是**伪共享**:这种"共享"是内存布局的意外,两个变量在逻辑上并没有关系。

### 2.2 和"读到旧值"是两种不同的机制——到底哪里不同

很容易把它归到"1.2 里 invalidate queue 那回事"——同样的 MESI 消息、同样的缓存行、同样的术语。这正是整篇文章想要预防的混淆。把两者并排摆开:

| | 读到旧值,1.2(正确性) | 伪共享(性能) |
|---|---|---|
| 在保护什么 | *我读到的值对不对?* | *读到它花了多少周期?* |
| 出问题的方式 | 在一个特定的顺序窗口里,读到一次旧值 | 每次写都要把独占权交来交去,一直持续 |
| 怎么修 | `memory_order` / release-acquire | 物理布局(`alignas`) |
| 一个原子操作都没有也会发生? | 不会——得有真实共享数据上的竞争 | **会**——两个完全不同步的 `int` 照样伪共享 |
| `memory_order` 完全正确也会发生? | 不适用,它本身就是修法 | **会**——正确的原子操作挡不住它 |

最后一行是最锋利的检验:拿两个完全无关、互不同步的 `int` 计数器,各自只被自己的线程写,没有任何原子操作,按任何合理的定义都不存在数据竞争——只要它们共用一条缓存行,照样会来回乒乓。因为*协议*不知道、也不关心这两个变量逻辑上无关,它只知道两个核一直在要同一块 64 字节的独占权。"读到旧值"的机制要求真的有跨线程的值依赖;伪共享的机制什么都不要,只要结构体布局不走运——它完全是在说*所有权来回易手*的物理代价,和有没有读错值无关。

### 2.3 修法,以及它修不了什么

```cpp
struct alignas(64) PaddedCounter {
  std::atomic<uint64_t> value{0};
  // 填充是隐式的:alignas(64) 会把 sizeof() 向上补到 64 字节的边界
};

PaddedCounter counters[num_threads];   // 每个计数器现在独占一整条缓存行
```

`alignas(64)`(或者可移植的 `std::hardware_destructive_interference_size` 常量)强制每个热变量独占一条行,不同线程的写就不再相撞。但这只修**伪**共享——本来就不该绑在一起的变量。如果多个线程确实、逻辑上就在累加*同一个*原子计数器,填充毫无用处:那是**真共享**,数据真的是共享的,行就得来回搬,这个代价是算法固有的,不是布局的意外。

对于真共享而又太热的情况,标准的缓解办法(LMAX Disruptor 一类设计背后的模式)是:别每次操作都去碰那条共享行。保留一份最近看到的游标/值的**本地缓存副本**,对本地副本批量做若干次操作,只是周期性地和真正的共享行重新同步。你用有限的过期换来大幅减少的跨核流量——概念上和 1.1 里 store buffer 的"小本子"是同一个想法,只不过是在应用层有意为之,而不是硬件自动做的。

### 2.4 同一个词下面藏着的第三个问题:L3 与 Intel CAT

还有一个区分值得备着,因为它也用到"共享缓存"这个词,常常被意外地卷进伪共享的讨论:**L1 和 L2 是每个核私有的;L3 在架构上就是整个插槽共享的,这很正常。** 一个很热的 L3 不是伪共享问题——共享 L3 不会引起一致性协议的来回折腾,因为共享 L3 本来就是设计。真正的风险是**容量争用**:另一个核上一个和你的程序毫无关系的进程,只要扫过足够多的数据,就能纯粹靠占空间把你的工作集从共享的 L3 里挤出去——这是"吵闹的邻居",不是一致性问题。**Intel CAT(Cache Allocation Technology)**,用 `pqos` 配置,就是干这个的:它把 L3 按路划分,给你的进程保留一块有保障的份额,吵闹的邻居爱怎么填剩下的 L3 都行,挤不走你的数据。三个不同的问题,三种不同的修法:读到旧值是顺序问题(第 1 部分);两个协作线程之间的乒乓是布局问题(第 2 部分);共享的 L3 被无关进程挤掉是容量问题,CAT 解决——三种修法都解决不了另外两个问题。

---

## 3. 依赖链:你在和最长的那条链赛跑,不是和指令条数

和第 2 部分同一条性能轴,换了一种资源:不再问"这个地址属于哪条缓存行",而是问"CPU 的流水线到底在等哪条指令"。两句话概括:现代核是超标量、流水线化的——可以同时有好几条指令在飞——但一条指令只有在所有输入都就绪时才能开始。**代码里算术操作的条数几乎不重要,决定实际耗时的是最长那条依赖链的长度。**

### 3.1 两种排法,同样的操作数,不同的代价

```cpp
// 链式:每个乘/加都依赖前一个
double chained(double a, double b, double c, double d) {
  return ((a * b) + c) + d;   // 一条依赖链:mul -> add -> add
}

// 独立:只有那个乘法在关键路径上
double parallel(double a, double b, double c, double d) {
  double sum = c + d;         // 和下面的乘法同时进行
  return (a * b) + sum;       // 真正串起来的只有 1 个乘 + 1 个加
}
```

同样三个操作,同样的结果。`chained` 逼着 CPU 严格按 mul → add → add 的顺序执行——总延迟是三者之*和*。`parallel` 让 `c + d` 和 `a * b` 同时算(它们互不依赖),关键路径只剩一个乘加一个加;"做的是同样的活",却快了大约三分之一。这就是指令级并行的全部玩法:**重新安排独立的工作,让流水线能重叠执行,而不是留下让它干等的偶然依赖。**

流水线真正会停下来等的,是**数据冒险**(下一条指令需要上一条还没产出的值——这一部分讲的都是它)和**控制冒险**(方向还不知道的分支,推测执行和乱序执行就是为了把它藏起来)。解决数据冒险归结为三个优先级:打断不必要的依赖链,把数据放进寄存器而不是反复读内存,平衡不同类型指令争抢的执行端口。

### 3.2 第一优先级里的陷阱:并不存在的依赖

有些指令——`popcnt`、`lzcnt`、`tzcnt` 是有据可查的例子,出现在好几代 Intel 和 AMD 核上——会把**目标寄存器当成隐式输入**,尽管它们算出来的结果根本不依赖寄存器原来的内容。硬件不知道这一点,它只看到"这条指令读了寄存器 X",于是一个每轮都复用同一个目标寄存器的循环,就毫无逻辑理由地被跨轮串成了一条链:

```asm
; 伪依赖:rax "依赖"它上一轮留下的旧值,
; 尽管 popcnt 的结果和 rax 的旧内容毫无关系
loop:
    popcnt rax, rbx
    ...
    jmp loop

; 修法:紧挨着之前把目标寄存器清零——CPU 的清零惯用法识别器
; 认得 xor 自己 是"没有真实依赖",于是打断这条链
loop_fixed:
    xor eax, eax
    popcnt rax, rbx
    ...
    jmp loop_fixed
```

这是一个很窄、很具体的硬件勘误——读源码是看不出来的,因为伪依赖藏在微架构里,不在你代码的逻辑里。现实中这得靠剖析器(`perf stat` 数停顿周期,和预期对比),或者一个已经知道勘误列表的编译器,而不是靠肉眼。实际的收获是知道有这种*模式*,这样一条"不该是链"的链出现了说不清的停顿时,你有个方向可查。

### 3.3 第一优先级用过头:寄存器溢出

手工打断依赖链——3.1 第一个例子里的修法,也是 3.5 要进一步推的技术——意味着同时创造出更多*独立*的值。独立的值需要各自的寄存器。x86-64 只有 16 个通用架构寄存器。展开得太猛、追求独立追得太远,寄存器就不够用了:编译器开始把多出来的活跃值**溢出**到栈上,于是治依赖停顿的"药",悄悄地把内存流量又带了回来——恰恰是第一优先级想消除的那种代价。这是一个相当讽刺的失败方式:修停顿的技术,用过了寄存器能承受的程度,自己又造出一种停顿。

### 3.4 store-to-load forwarding:回到 store buffer

store-to-load forwarding——1.1 里顺带提过——是为什么一个写紧跟着一个对同一地址的读,不必绕缓存走一圈:CPU 直接从 store buffer 里把值转发出来。它是实打实的延迟收益,但有一个严格的物理要求:**读的地址、宽度和对齐,必须和 store buffer 里的某一条记录完全对上。** 转发只匹配一条具体的记录——它不会把部分重叠的几条拼起来。一个具体的失败例子:写 4 字节,紧接着从同一地址读 8 字节。这个读不能被任何一条缓冲的写完整满足,转发失败,读退回慢路径——要等写真正落进缓存,才能读回来。让 1.1 里的写变便宜的是 store buffer,让这条捷径成为可能的也是它,而它的宽度/对齐规则,也会在你不小心时让这条捷径悄无声息地失效。

### 3.5 把"打断依赖链"变成一个公式

`chained` 对 `parallel` 的例子可以直接推广到循环:不用一个持续累加的累加器(一条完全串行的依赖链——每 `latency` 个周期才做一次操作),而是把累加拆到 `K` 个独立的累加器上,最后合并一次。

```cpp
// 朴素版:一个累加器,一条完全串行的依赖链
double dot_serial(const double *a, const double *b, size_t n) {
  double acc = 0.0;
  for (size_t i = 0; i < n; ++i) acc += a[i] * b[i];   // 每次 += 都要等上一次
  return acc;
}

// K 个独立累加器,只在最后合并一次——不是每一轮都合并
template <size_t K>
double dot_unrolled(const double *a, const double *b, size_t n) {
  double acc[K] = {};
  size_t i = 0;
  for (; i + K <= n; i += K)
    for (size_t k = 0; k < K; ++k)
      acc[k] += a[i + k] * b[i + k];        // K 条链,跨轮没有依赖
  for (; i < n; ++i) acc[0] += a[i] * b[i];  // 余下的部分
  double total = 0.0;
  for (double v : acc) total += v;
  return total;
}
```

`K` 该取多大?刚好大到在一条链的 `latency` 还没走完时,能把执行端口喂饱:**K = 延迟 × 吞吐**,吞吐指核每个周期能*发射*多少个这种操作。以延迟 4 个周期、有两个能做 FMA 的端口(相当典型的现代桌面/服务器核)的乘加为例:

| K(累加器个数) | 每个元素的周期 | 实际每周期操作数 | 相对单端口上限 |
|---|---|---|---|
| 1 | 4(完全串行) | 0.25 | 25% |
| 4 | 4 | 1.0 | 100%——喂饱一个端口 |
| 8 | 4 | 2.0 | 200%——喂饱两个端口 |
| 16 | 4 | 2.0 | 不再提升——瓶颈从链变成了端口 |

这里 `K = 8` 是最佳点——独立的活刚好够把 4 个周期的延迟藏在两个端口的吞吐后面,再往上没有收益(按 3.3 的寄存器溢出陷阱,还有实打实的风险)。这是一个标准技术(推导和 Agner Fog 优化手册里对任意延迟/吞吐组合的推导是同一套),也要附上诚实的说明:这个上限假设瓶颈在算术单元。实际上,内存带宽或者喂数据的 load 端口个数可能先卡住吞吐——这正是 **roofline 模型**核心的**计算受限 vs 访存受限**之分——所以公式告诉你算术上限,`perf` 告诉你有没有真的达到它。
