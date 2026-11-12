---
title: "IV：CV 项目经历拆解"
date: 2026-11-12T00:00:00+08:00
slug: "cv-projects"
description: "简历“项目经历”的两个项目、9 条，一条一节。项目 1 是 C++ 性能自动优化 Agent Skill：分诊与 perf、按信号加载修法、正确性与配对计时、缓存案例。项目 2 是 AI 实时语音雅思平台：状态机、四个线程、音频与二进制帧、LLM 结构化输出、Pimpl 与测试。每节先放简历原文，再按步骤讲做法，配简化后的代码。"
weight: 6
toc: true
math: true
---

这一页把简历“项目经历”逐条拆开。代码都是为了讲清楚做法重写的简化版，名字和结构不是原工程的。数字一律是百分比，因为测试机是虚拟机，绝对值偏高。

## 1. 项目 1 整体：三种常见的坏结果，对应三道关 {#skill-why}

> **简历原文**
>
> 针对 coding agent 自动优化中“改快但改错”“提速实为测量噪声”“过早停止”三类问题，设计性能优化流程并封装为 Agent skill，由 Agent 按流程自主完成剖析、改写、验证与决策，全程留痕、结果可复现。

### 1.1 让 Agent 自己优化代码，最容易出三种坏结果 {#skill-three-failures}

| 坏结果 | 为什么会发生 | 流程里挡它的一关 |
|---|---|---|
| 改快了，但结果错了 | Agent 的目标是“变快”，删一个检查、换一个编译选项、改一下测试都能变快 | 先比对输出，和原版不一致就否决，不看速度 |
| 提速其实是测量噪声 | 机器的频率、温度、别的进程会让两次运行差几个百分点，Agent 拿到一次“快了”就当成功 | 新旧版本紧挨着各跑一次、顺序随机，逐轮比较，多轮稳定更快才采纳 |
| 拿到一点收益就停 | 没有人告诉 Agent 离极限还有多远，也没有停的条件 | 停的条件开跑前写好：预算用完、连续几个候选落不了地、或者已经离估出来的下限很近 |

- **三道关都是流程规定，不靠 Agent 自觉**：Agent 想绕也没有地方绕，因为每一关的判据在开跑前就写进了“实验约定”。
- **我设计的是流程，Agent 照着跑**：判据怎么定、停在哪、什么叫一个候选，是我定的；改代码、跑命令是 Agent 做的。

### 1.2 一个 Agent skill 是什么：一份会被按需读取的说明书 {#skill-what}

- **skill 是放在仓库里的一组 Markdown 文件和脚本**：`SKILL.md` 是入口，Agent 开始优化任务时先读它；它按需再指向别的文件。
- **这个仓库的结构**：

```
performance-optimization/
├── SKILL.md                    入口：分诊表、实验约定、筛选与确认、停的规则、落地前检查
├── references/
│   ├── evidence.md             形成假设时的证据清单
│   ├── floors.md               两个“地板”：算的下限、等数据的下限
│   ├── continuous-line.md      一条优化线持续做下去时的授权、台账、恢复
│   └── convergence.md          收敛图怎么画
└── scripts/
    └── render_convergence_chart.py
```

- **每类性能瓶颈的成因和修法不放在 skill 里，放在博客的“瓶颈卡片”里**：`SKILL.md` 只写怎么按信号去查（见第 3 节），这样 skill 本身不会随着瓶颈种类变多而变长。

> **讲的时候按这个顺序**
>
> 1. **解决什么**：Agent 自动优化常见三种坏结果：改快了但错了、把噪声当提速、拿一点收益就停。
> 2. **怎么解决**：三道关，先比输出，再配对计时，停的条件开跑前写好。
> 3. **形态**：一个 skill 仓库，`SKILL.md` 做入口，按信号再去读对应的修法。
> 4. **我做了什么**：设计流程和判据，Agent 按流程跑。

## 2. 分诊与 perf 剖析：先问是在算还是在等，再选工具 {#skill-triage}

> **简历原文**
>
> 先比较墙钟与 CPU 时间等低成本指标，判断瓶颈属于 CPU 热点、等待与 I/O、锁竞争还是多核扩展，再选剖析手段；CPU 热点用 perf 逐层深入：perf stat 看整体指标，perf report 找热点函数，perf annotate 看热点汇编；跨核争用用 perf c2c 定位到具体缓存行

### 2.1 第一步只比两个数：墙钟时间和 CPU 时间 {#triage-two-clocks}

- **墙钟时间是挂钟走了多久，CPU 时间是这个程序真正占着 CPU 的时间**。
- **两个数接近：程序一直在算**，瓶颈是 CPU 热点，下一步用 perf 找热点。
- **CPU 时间远小于墙钟：程序大部分时间在等**，等 I/O、等锁、等调度。这时候 perf 的采样看不到这些时间，因为等待的时候程序不在 CPU 上，没有样本可采。
- **这一步便宜**：一行命令，不用重新编译，也不用特殊权限。

```bash
# %e 墙钟秒数，%U 用户态 CPU 秒数，%S 内核态 CPU 秒数，%c 被抢占的次数，%w 主动让出的次数
/usr/bin/time -f "wall=%e user=%U sys=%S preempted=%c waited=%w" ./prog

# 判断：
#   user + sys 接近 wall      → 在算，去第 2.2 步
#   user + sys 远小于 wall    → 在等；waited 很大是 I/O 或锁，用日志/trace 看阻塞在哪
#   user + sys 大于 wall      → 多个线程并行在算；再看加线程后墙钟是不是同步降
```

### 2.2 分成四类，每一类的下一步不同 {#triage-four-classes}

| 看到的现象 | 瓶颈类型 | 下一步用什么 |
|---|---|---|
| CPU 时间接近墙钟，采样集中在少数函数 | CPU 热点 | perf stat、report、annotate（2.3） |
| 墙钟远大于 CPU 时间，采样分散 | 等待与 I/O | 项目自己的日志、trace、服务端统计，找程序阻塞在哪 |
| 加线程后吞吐不涨，`perf lock` 里等待时间远大于持有时间 | 锁竞争 | 看锁保护的是什么、临界区多长 |
| 加核吞吐不涨，也没有锁 | 多核扩展 | `perf c2c`，找跨核争用的缓存行（2.4） |

- **先分类再选工具的原因**：每个工具只回答一类问题，拿错了工具得到的是“看起来有结论”的空话。比如等 I/O 的程序跑 perf，采样集中在几个函数上，其实是剩下那点 CPU 时间的分布。

### 2.3 CPU 热点：perf 逐层往下走，每层回答一个问题 {#triage-perf-three}

```bash
# 编译时带 -O2 -g，报告才对得上源码行
g++ -O2 -g -fno-omit-frame-pointer prog.cpp -o prog

# 1. perf stat：整体指标，回答“是在算，还是在等数据”
perf stat -e task-clock,cycles,instructions,cache-misses,branch-misses,page-faults,context-switches ./prog

# 2. perf record + report：热点函数，回答“时间在哪个函数里”
perf record -F 99 -g ./prog
perf report --stdio

# 3. perf annotate：热点函数的汇编，回答“慢在哪几条指令上”
perf annotate --stdio -s hot_function
```

- **第 1 层 `perf stat`，看比例，不看绝对值**：
  - IPC（每周期退休的指令数）低，同时缓存缺失多：卡在等内存；
  - 分支预测失败率高：卡在分支；
  - 缺页多：卡在第一次碰内存；
  - 上下文切换多：在等或在抢锁。
- **第 2 层 `perf report`，找占比最高的函数**：只有占比够大的函数才值得往下挖，因为把它整个优化掉也只能省它那一份。
- **第 3 层 `perf annotate`，看汇编里哪条指令吃了样本**：样本常常落在慢指令的后一条上，所以要往前看一条。比如落在一条加法上，要看是不是每次加法都在等上一次加法的结果（串行累加）。

- **虚拟机上没有硬件计数器**：`cycles`、`cache-misses` 会显示 `<not supported>` 或者 0。这不是“没有开销”，是“拿不到”。这时改用 `cpu-clock` 软件时钟采样，再用 skill 里的“两个地板”把算和等分开（见 [perf 专题](/zh/posts/low-latency-perf-profiling/#demo-probe)）。

### 2.4 跨核争用：`perf c2c` 定位到缓存行，再看偏移 {#triage-c2c}

- **多个线程互相拖慢，perf report 里看不出来是哪个变量**：每个线程各自的函数都不算热，但它们访问的缓存行在核之间来回搬。
- **`perf c2c` 统计的是“读的时候这条行在别的核里是已修改状态”（HITM）的次数**：按缓存行排序，最多的那几条就是在来回搬的行。
- **再展开这条行，看行内是哪几个偏移、各被哪几个 CPU 访问**：
  - 不同偏移、各被一个 CPU 访问：伪共享，把变量隔到不同的行；
  - 同一个偏移、多个 CPU 访问：真共享，要改设计。
- **完整的用法和输出怎么读，在[内存序与伪共享的 3.6](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-c2c)**。

> **讲的时候按这个顺序**
>
> 1. **先分算还是等**：比墙钟和 CPU 时间，因为便宜，而且决定后面用哪个工具。
> 2. **算：perf 三层**：stat 看比例，report 找函数，annotate 看指令，每一层缩小一次范围。
> 3. **争用：c2c**：定位到缓存行，再看偏移分伪共享和真共享。
> 4. **照实说限制**：测试机是虚拟机，拿不到硬件计数器，改用软件时钟采样，结论最后靠配对计时确认。

## 3. 按信号渐进式披露修法：命中信号才加载这一类 {#skill-signals}

> **简历原文**
>
> Agent 以剖析结果或源码中的信号（如某缓存行跨核争用严重、热点循环为单一累加器串行累加）匹配对应的性能瓶颈，命中后才加载其成因、修复方法与验证方法；按需加载控制上下文占用，新增一类性能瓶颈只需新增一条信号索引

### 3.1 不把所有修法一次给 Agent，原因是上下文有限 {#signals-why}

- **每类瓶颈的成因、修法、验证方法都有一整页**：几十类全塞进上下文，既挤掉看代码的空间，也让 Agent 容易乱套用。
- **渐进式披露**：先只给一张“信号 → 卡片”的索引，Agent 剖析出一个信号，才去读对应那一张卡片。

### 3.2 信号索引：每张卡片一行，写着“看到什么算命中” {#signals-index}

每张卡片的第一行是一个 `signal:`，描述这类瓶颈在剖析结果或源码里长什么样：

```yaml
# bottlenecks/serial-accumulator.md
---
title: "Serial Accumulator"
signal: "One `vaddss`/`vfmadd` (or the instruction after it) dominates annotate; IPC ≪ 1 while cache misses stay low"
---
> - **Signal**: …
> - **Cause**: every `+=` waits for the previous result …
> - **Fix**: split into several independent accumulators …
> - **Verify**: the output agrees within rounding error, and IPC at least doubles.
```

Agent 查索引就是把所有卡片的 `signal:` 行取出来：

```bash
grep -rH "^signal:" --include="*.md" --exclude="*.zh.md" <blog-root>/content/bottlenecks
```

一次输出十几行，每行一个卡片名加一句信号描述，大约几百个字。Agent 拿着剖析结果和这十几行对：

| 剖析里看到 | 命中的卡片 | 然后才读卡片 |
|---|---|---|
| c2c 里某条行占 5% 以上，不同偏移被不同线程写 | 伪共享 | 成因、`alignas` 隔开、验证看 c2c 里这条行消失 |
| annotate 里一条 `vaddss` 占大头，IPC 很低但缓存缺失不多 | 单累加器串行 | 成因是每次加法等上一次，修法是拆成几个累加器 |
| 热点是一个 `mutex` 保护的读多写少的数据 | 读写锁 | 改成读写锁，验证看 lock stat 里的等待时间 |

### 3.3 一张卡片里有四样：信号、成因、修法、验证 {#signals-card}

- **信号**让 Agent 判断是不是这一类；
- **成因**让 Agent 知道为什么，不是照抄修法；
- **修法**给出改动的方向和前提（比如拆累加器要求运算满足结合律，结果会差一点舍入误差）；
- **验证**给出改完看什么指标，判断真的修对了，而不只是跑得快了。

### 3.4 新增一类瓶颈：加一张卡片，索引自己多一行 {#signals-add}

- **索引是从卡片文件里取出来的，不是另外维护的一份清单**：新增一张卡片，`grep` 的输出就多一行，`SKILL.md` 不用改。
- **信号库是越用越多的**：遇到新问题，复盘以后补一张卡片，下次 Agent 看到同样的信号就能认出来。

### 3.5 匹配错了怎么办 {#signals-wrong}

- **匹配错了不会直接变成错误的优化**：套上去的修法还要过第 4 节的两关，输出不一致被否决，速度没有稳定变快也不采纳。
- **索引不是唯一的路**：没有命中任何信号，就退回第 2 节的分诊表，从算还是等重新来。

> **讲的时候按这个顺序**
>
> 1. **问题**：几十类修法一次塞给 Agent，上下文装不下，也容易乱套用。
> 2. **做法**：每类一张卡片，卡片第一行是信号；Agent 把剖析结果对信号索引，命中了才读这一张。
> 3. **好处**：新增一类只加一张卡片；套错的修法过不了后面的验证。
> 4. **举例**：c2c 里不同偏移被不同线程写，命中伪共享；annotate 里一条累加指令占大头，命中串行累加。

## 4. 正确性与性能验证：先比输出，再配对计时 {#skill-verify}

> **简历原文**
>
> 每个改动单独验证：先比对输出，与原版不一致即否决；再测速度，每轮让新旧版本紧挨着各跑一次、先后顺序随机，逐轮对比，避免机器频率、温度等随时间漂移偏向某一方，多轮结果稳定更快才采纳

### 4.1 每个改动单独验证：一次只改一件事 {#verify-one-change}

- **一个候选只含一个改动思路**：Agent 把几个改动打包一起测，快了也不知道是哪个起作用，还可能一个快一个慢互相抵消。
- **改动之后再改，算新的候选**：看到结果之后又调整的补丁，不继承之前的证据，从头验证。

### 4.2 先比输出，不一致就否决，不看速度 {#verify-correctness}

- **比对要对到所有被约定的输出**：只比一个汇总数会漏掉“少了一条记录”这类错误。
- **浮点的比对要定容差**：把串行累加拆成几个累加器，运算顺序变了，结果会差一点舍入误差，逐位比对会把正确的改动否决。能接受什么容差，开跑前写在约定里；要求逐位一致，这类改法就不能用。
- **要用已知的错误检验比对本身**：故意改坏一个版本，确认比对能发现。比对抓不到的错误，记成“没有覆盖”，靠读代码补。

```bash
# 先比输出：不一致直接否决，后面的计时不做
./prog_base  < input > out_base.txt
./prog_cand  < input > out_cand.txt
python compare.py out_base.txt out_cand.txt --rtol 1e-9 || { echo REJECT; exit 1; }
```

### 4.3 配对计时：新旧紧挨着跑，顺序随机，逐轮比 {#verify-paired}

- **机器的状态会随时间漂移**：频率、温度、别的进程。先把旧版本跑 20 次再把新版本跑 20 次，漂移就混进了“新旧差异”里。
- **所以一轮里新旧各跑一次，紧挨着**：同一轮里两边的机器状态几乎一样，轮与轮之间的漂移对两边一样。
- **一轮里谁先跑是随机的**：固定先跑旧版本的话，旧版本总是在“冷”状态下跑，新版本总是在“热”状态下跑，这个差异会被算成提速。
- **逐轮算差，看差的分布**：不比两边各自的平均值，因为轮与轮之间的波动比新旧之间的差异大得多，算差把这部分波动抵消掉了。

```python
import random, statistics, subprocess, time

def run(binary):
    t = time.perf_counter()
    subprocess.run([binary], stdin=open("input"), stdout=subprocess.DEVNULL, check=True)
    return time.perf_counter() - t

def paired(base, cand, rounds=30):
    diffs = []                                   # 每轮：新比旧慢（正）还是快（负），用比例
    for _ in range(rounds):
        order = [base, cand]
        random.shuffle(order)                    # 谁先跑是随机的
        t = {order[0]: run(order[0]), order[1]: run(order[1])}
        diffs.append((t[cand] - t[base]) / t[base])
    diffs.sort()
    lo, hi = diffs[int(0.05 * rounds)], diffs[int(0.95 * rounds) - 1]   # 简易 90% 区间
    return statistics.median(diffs), (lo, hi)

med, (lo, hi) = paired("./prog_base", "./prog_cand")
print(f"median {med:+.1%}, 90% range [{lo:+.1%}, {hi:+.1%}]")
# 区间整个在 0 的负侧：稳定更快；区间跨过 0：判成噪声，不采纳
```

### 4.4 先证明测量本身可靠：A/A {#verify-aa}

- **A/A 是拿同一个版本当新旧两边**：按同样的流程跑，两边的差应该围着 0，区间要跨过 0。
- **A/A 的区间如果偏离 0，或者宽得离谱**：测量入口有问题（顺序没真随机、有残留状态、机器太吵），这时候的“提速”一律不算数，先修测量。
- **A/A 的宽度告诉你能测到多小的提速**：A/A 的区间是 ±2%，那 1% 的提速就测不出来。

### 4.5 筛选和确认分开：筛选的数据不能拿来确认 {#verify-confirm}

- **筛选用来选候选**：便宜，样本少，只决定哪些候选值得确认。
- **确认用新跑的数据**：同一批候选，筛选里最好的那个数是被“挑出来”的，天然偏乐观；确认必须重新测，报告里写确认的数。
- **每个候选还有守卫指标**：目标指标变好的同时，内存、启动时间、另一端的尾部延迟不能变差，超过容差就否决。

### 4.6 改动涉及共享数据时，再加一道消毒器 {#verify-sanitizer}

- **涉及线程间共享数据、内存序、对象生命周期、对齐的改动**：另外用 `-fsanitize=address,undefined` 和 `-fsanitize=thread` 各编一遍，跑同样的测试。
- **原因**：这类改动出的错，输出比对常常看不出来，只是偶尔错一次。

> **讲的时候按这个顺序**
>
> 1. **一次一个改动**：改动混在一起，快了不知道是谁，错了也不知道是谁。
> 2. **先比输出**：不一致直接否决，不看速度；浮点用容差，容差开跑前定。
> 3. **再配对计时**：新旧紧挨着各跑一次，顺序随机，逐轮算差，因为频率温度会随时间漂，按轮配对能抵消。
> 4. **采纳的条件**：区间整个落在更快的一侧；先做 A/A 证明测量可靠；确认用新跑的数据，不用筛选时的。

## 5. 缓存性能瓶颈案例：卡在等内存，先让缺失重叠，再分给两个核 {#skill-case}

> **简历原文**
>
> 公开 C++ 低延迟案例（期权定价，单条行情访问上百条缓存行，性能瓶颈在访存延迟与长依赖链），Agent 按流程优化，采用双核分担、软件预取、SIMD 向量化，P50 延迟降低约 67%

### 5.1 这个案例是什么 {#case-what}

- **一条行情进来，重算这只股票挂着的 64 个期权**：每个期权只有 25 次浮点运算，可是要读两条缓存行，散在 52 万条期权记录里。
- **一次事件要碰 140 条缓存行**：事件本身 3 条、股票记录 9 条、期权 $64 \times 2 = 128$ 条。大部分读落在 L3，少部分到内存。
- **瓶颈是等内存，不是算**：计算量很小，时间花在等数据到。
- **长依赖链**：每个期权的 alpha 是一串前后相依的浮点运算，这一串在数据到之前不能开始，开始后也只能一步等一步。
- **完整的案例和数据**：[低时延交易缓存案例](/zh/posts/low-latency-cache-case-study/)，这一节只讲流程怎么用在它上面。

### 5.2 先判断：哪一类瓶颈 {#case-diagnose}

按第 2 节的分诊走：

1. **墙钟和 CPU 时间接近**：在算，不是在等 I/O。
2. **perf stat 的比例**：演讲里这段代码每周期退休的指令数是 1.98，一次事件有 130 次 L1 缺失，说明大量时间在等内存。
3. **annotate 里的热点集中在读期权字段的那几条 load**：样本落在等数据的指令上。
4. **结论**：CPU 热点，但具体是访存延迟，加上每个期权内部的依赖链。

虚拟机上没有硬件计数器，所以第 2 条用“两个地板”代替：把数据缩到装进缓存、其余不变，得到“算”的下限；把计算去掉、访存保留，得到“等数据”的下限。两个下限哪个更接近实测值，哪个就是瓶颈。

### 5.3 第一个改动：把一批期权的读集中到一起，让缺失同时在路上 {#case-batch}

- **问题**：基线是一个期权一个期权地读、算。两个期权的读之间夹着一整个期权的计算，计算占住了乱序窗口，后面期权的读发不出去，缺失只能一个接一个地等。
- **做法**：分成两趟。第一趟只取数，把一批期权要用的字段读进小数组；第二趟再集中算。

```cpp
// 一批 D 个：第一趟只取数，第二趟集中算
for (int b = 0; b < count; b += D) {
    for (int k = 0; k < D; ++k) {                  // 第一趟：D 个期权的读紧挨着发出去
        o[k]   = &options[h[b + k].option];
        px[k]  = o[k]->curr_px + move * h[b + k].delta;
        ref[k] = o[k]->actual_px;
        arg[k] = o[k]->aux[0] + o[k]->aux[4];
        ema[k] = o[k]->ema;
    }
    for (int k = 0; k < D; ++k) {                  // 第二趟：算完写回
        o[k]->alpha = alpha_of(px[k], ref[k], arg[k], ema[k]);
        // ...
    }
}
```

- **批的大小受限于每个核同时能挂的缺失数**：每个核有 16 个行填充缓冲（LFB），一个期权两条行，一批 D 个就是 2D 个缺失。D = 4（8 条行）最好，D = 8 已经占满全部 LFB，股票记录和硬件预取器要用的位置没了。
- **这一步的效果**：中位数降约 8%，p90 降约 23%（演讲机器上的数）。

### 5.4 第二个改动：软件预取，算这一批的时候，下一批已经在路上 {#case-prefetch}

- **问题**：批处理后，一批的缺失一起在路上了，但算的时候没有新请求发出去：算和等还是轮流来。
- **做法**：下一批要哪些期权，股票记录里早就写着。在两趟之间，把下一批的两条行先预取。

```cpp
for (int k = b + D; k < min(b + 2 * D, count); ++k) {          // 下一批
    const char* p = (const char*)&options[h[k].option];
    _mm_prefetch(p,      _MM_HINT_T0);                          // 价格那条行
    _mm_prefetch(p + 64, _MM_HINT_T0);                          // 状态那条行
}
```

- **预取和普通的读不一样**：预取没有目标寄存器，没有指令等它，发出去就能退休，不占乱序窗口；普通的读数据不回来就不能退休，会重新把窗口堵上。
- **提示用 `_MM_HINT_T0`，不用 NTA**：NTA 告诉硬件这些行用完就扔，可这些期权下一条行情还要用，换成 NTA 反而慢了约 65%。
- **这一步的效果**：在批处理的基础上，中位数再降约 12%。

### 5.5 第三个改动：拆给两个核，主核 40 个，辅核 24 个 {#case-split}

- **问题**：64 个期权互不相干，一个核算完要的时间，两个核各算一半就能缩短。
- **前面那段拆不了**：轮询环形缓冲区、查股票、算 `move`，前后依赖，所以主核做这一段，再把后 24 个期权交给辅核，自己算前 40 个。
- **交接用 release 写、acquire 读**：主核写好请求再发布序号，辅核看到序号再读；结果反过来走一遍。请求和结果各占独立的缓存行，免得两边抢同一条行。
- **交接本身也有成本**：每条行要从一个核走到另一个核，读一次约 30 ns。所以不平分，主核多留一些，主核最后一个算完，事件的时间由它定。

### 5.6 第四个改动：SIMD，把 4 个期权的同一套算式放进一条指令 {#case-simd}

- **第二趟里 D 个期权的算式完全一样**，只是数据不同，而且已经放在小数组里（`px[]`、`ref[]`、`arg[]`、`ema[]`）。
- **AVX2 一条指令处理 4 个 double**，所以 4 个期权的 alpha 可以一起算：

```cpp
#include <immintrin.h>
// 4 个期权同时算 alpha；编译加 -mavx2 -mfma
inline __m256d alpha4(__m256d px, __m256d ref, __m256d arg, __m256d& ema) {
    ema = _mm256_fmadd_pd(_mm256_set1_pd(0.9), ema, _mm256_mul_pd(_mm256_set1_pd(0.1), px));
    __m256d x = _mm256_div_pd(_mm256_sub_pd(px, ref), _mm256_add_pd(arg, _mm256_set1_pd(1.0)));
    __m256d a = x;
    for (int i = 0; i < 10; ++i)
        a = _mm256_fmadd_pd(a, x, _mm256_set1_pd(0.01 * i));      // 一条指令做乘加
    return _mm256_fmadd_pd(_mm256_set1_pd(0.01), _mm256_sub_pd(px, ema), a);
}
```

- **依赖链的长度没变，但每一步同时做 4 个期权**：一个期权内部那串前后相依的运算仍然是一步等一步，可 4 个期权的链并排走，总时间接近一个期权的。
- **乘加合并成一条指令会改变舍入**：结果和标量版相差最后几位，所以第 4 节的比对要用容差，或者标量版也用同样的 fma 开关。

### 5.7 这个案例证明了什么，没证明什么 {#case-honest}

- **代码是 Agent 改的，我做的是判断和把关**：定瓶颈属于哪一类、定验证的判据、否决不过关的改法。三道关是我定的，Agent 照着跑。
- **流程里有几条规则，是我知道这个案例的答案之后补的**：比如“两个地板”。所以它证明的是流程能走通，不是流程能推广到没见过的代码。要证明能推广，得拿 Agent 没见过的代码盲测。
- **上面每一步的百分比是演讲者原版代码在他机器上的数**，用来说明每个技术各值多少；简历上的 67% 是 Agent 按流程做这个案例的结果。两套数不能连着讲。
- **P50 降约 67% 是在测试机（虚拟机）上测的**，只说百分比。

> **讲的时候按这个顺序**
>
> 1. **案例**：一条行情重算 64 个期权，每个只有 25 次浮点运算，但要碰 140 条缓存行，卡在等内存。
> 2. **我的判断**：既然卡在等内存，先让缺失重叠（分批取、预取下一批），再把剩下的分给两个核，最后把相同的算式向量化。
> 3. **每一步为什么有效**：批处理是不让计算占住乱序窗口；预取是不占窗口地提前要；双核是把 64 个互不相干的更新分摊；SIMD 是 4 个期权并排走同一条依赖链。
> 4. **照实说**：代码是 Agent 写的，流程和判据是我定的；有几条规则是知道答案后补的，所以证明的是流程能走通。

## 6. 项目 2 整体：C++17 实时语音雅思训练平台 {#ielts-why}

> **简历原文**
>
> C++17 实时语音雅思训练平台，集成 ASR、TTS、VAD 和 LLM，提供雅思口语与写作训练。

### 6.1 它在做什么：一边说话，一边有人听、有人答 {#ielts-what}

- **用户对着麦克风说，系统要听出来、想一想、念出回答**：这条链上有四件事，识别（ASR）、对话（LLM）、合成（TTS）、判断什么时候说完了（VAD）。
- **识别、对话、合成都在火山引擎的实时语音对话服务里做**，客户端负责三件事：采集和播放音频，通过 WebSocket 和服务端收发数据，维护“现在轮到谁说话”的状态。
- **VAD（语音活动检测）由服务端做**，结果以“用户开始说话”“用户停止说话”的事件到客户端，客户端据此切换状态。
- **LLM 另外有一条路**：实时对话之外，对用户的回答打分、给修改建议，走的是单独的 OpenAI 兼容接口（第 10 节）。

### 6.2 这是 3 月的 C++ 原型，现在的产品结构不同 {#ielts-now}

- **简历里的是 2026 年 2–3 月做的 C++ 原生实时链路**，后来产品改成了 Qt 桌面壳套网页前端、Django 后端，C++ 实时语音引擎是桌面壳里的一个静态库。
- **旧原型的代码还在、还能跑**，但有几处我后来发现并记下来的问题（第 7、8、9 节会各讲一处）。
- **照实讲时**：简历上写的是原型当时的设计；现在知道哪里不好，也知道怎么改。完整的结构和问题列表在[代码结构](/zh/projects/ielts-studio-structure/)和[复盘](/zh/projects/ielts-studio-retrospective/)。

> **讲的时候按这个顺序**
>
> 1. **做什么**：对着麦克风说话，系统识别、对话、合成语音回答，用来练雅思口语。
> 2. **分工**：识别、对话、合成在火山的实时语音服务里；客户端管音频、网络和状态。
> 3. **范围**：简历写的是 3 月的原生原型；现在产品是桌面壳套网页，C++ 引擎是其中一个库。

## 7. 架构与状态机：四层分开，状态机是唯一的协调点 {#ielts-arch}

> **简历原文**
>
> 四层架构（通用层 / 服务层 / 业务层 / UI 层），模块间通过抽象接口解耦；线程安全的全局状态机作为唯一协调中心，跨线程行为通过事件投递驱动

### 7.1 四层各放什么，依赖只往下 {#arch-layers}

| 层 | 放什么 | 依赖谁 |
|---|---|---|
| 通用层 | 协议编解码、日志、配置、线程安全队列 | 只依赖标准库 |
| 服务层 | WebSocket 客户端、音频设备、LLM 客户端 | 通用层 |
| 业务层 | 对话会话、状态机、打分和跟进提问逻辑 | 服务层的抽象接口 |
| UI 层 | Qt 界面 | 业务层 |

- **依赖只往下，不往上**：服务层不知道业务层存在，通用层不知道服务层存在。
- **业务层依赖的是抽象接口，不是具体类**：业务层认的是“有一个能发音频、能收事件的东西”，而不是 Boost.Beast 的 WebSocket。

```cpp
// 服务层给业务层看的接口：只有“发”和“收到事件时通知谁”
class IRealtimeClient {
public:
    virtual ~IRealtimeClient() = default;
    virtual void SendAudio(const float* pcm, size_t frames) = 0;
    virtual void SendTextQuery(const std::string& text) = 0;
    virtual void SetOnEvent(std::function<void(const Event&)> cb) = 0;
};
// 业务层只持有 IRealtimeClient*；真实现用 Boost.Beast，测试用假的
```

- **这样切的好处**：测试时业务层可以接一个假的客户端，不用联网；换一家语音服务只换服务层。

### 7.2 为什么要一个状态机：多个线程都想改“现在是谁在说话” {#arch-why-sm}

- **这个系统有几个并行的线程**：麦克风线程在发音频，播放线程在播放，接收线程在收事件。它们都要知道“现在是考官在说，还是用户在说”。
- **没有统一的协调点，状态就散在各个线程里**：每个线程各自设标志位，两个线程同时改的话，谁后改谁生效，行为随时序变化，很难复现。
- **所以只有一个状态机持有“现在的状态”**：线程不直接改别人的状态，也不直接调用别的线程的函数，只往状态机里投递事件。

### 7.3 事件投递：线程只说“发生了什么”，状态机决定“因此怎么办” {#arch-events}

```cpp
enum class State { Idle, InterviewerSpeaking, Listening, Thinking /* ...示意，原型里一共 8 个 */ };
enum class Ev    { PlaybackDrained, UserSpeechFinal, AnswerScored /* ... */ };

class StateMachine {
public:
    using Listener = std::function<void(State from, State to)>;

    void Post(Ev ev) {                              // 任何线程都可以调
        State from, to;
        std::vector<Listener> to_call;
        {
            std::lock_guard lk(mu_);
            from = state_;
            to   = Transition(state_, ev);          // 查转移表，不合法的返回原状态
            if (to == from) return;
            state_ = to;
            to_call = listeners_;                   // 拷出一份，锁外再调
        }
        for (auto& cb : to_call) cb(from, to);      // 不持锁调回调
    }

    State Get() const { std::lock_guard lk(mu_); return state_; }

private:
    static State Transition(State s, Ev ev);        // 一张转移表
    mutable std::mutex mu_;
    State state_ = State::Idle;
    std::vector<Listener> listeners_;
};
```

- **转移表是唯一决定“什么事件在什么状态下导致什么状态”的地方**：所有线程的行为都服从这一张表，要看逻辑只看这一处。
- **回调要在锁外调**：回调里如果又去改状态或注销回调，而锁还持着，就会死锁。做法是在锁里把状态改好、把回调列表拷出来，放锁以后再逐个调用。
- **线程读取状态要走 `Get()`**：比如麦克风线程每发一帧前看一眼，现在是不是该发真实音频，还是发静音。

### 7.4 照实说：全局单例有代价 {#arch-honest}

- **“全局”意味着整个进程只有一个状态机**：优点是协调点唯一，不用在对象之间传来传去。
- **缺点是两个会话会互相覆盖状态**，测试也不能并行，因为状态是全进程共享的。
- **后来 C++ 引擎里新写的 `VoiceSession` 把状态放进实例里**，一个会话一份，状态只在它自己的控制线程里改，对外回调也只在这个线程调，调用时不持任何锁。
- **“业务混在一起”也是一处**：旧原型的 `DialogSession` 同时装着线程、队列、状态机和打分、跟进提问、总结的逻辑，想让别的场景复用，只能整个复制。新引擎改成“只管说一段、听一段”，题目和评分交给后端。

> **讲的时候按这个顺序**
>
> 1. **分层**：通用、服务、业务、UI 四层，依赖只往下；业务层只认抽象接口，所以能接假实现测试，也能换语音服务商。
> 2. **状态机**：几个线程都要知道“谁在说话”，所以只让状态机持有状态，线程只投事件。
> 3. **实现要点**：转移表集中，加锁改状态，回调拷出来放锁后再调。
> 4. **代价**：全局单例让两个会话互相覆盖状态；后来的新引擎把状态放进会话实例里。

## 8. 并发模型：四个线程，每个只阻塞在一件事上 {#ielts-threads}

> **简历原文**
>
> 主线程、麦克风、播放、接收四个线程，用 std::atomic、std::mutex、condition_variable 协调，各线程职责单一

### 8.1 四个线程各自阻塞在哪里 {#threads-what}

| 线程 | 阻塞在 | 干什么 |
|---|---|---|
| 主线程（Qt） | 事件循环 | 显示对话和状态，只处理别的线程投递过来的回调 |
| 麦克风线程 | PortAudio 阻塞读 | 读一块音频，编成帧发出去；对面在说话时改发静音 |
| 接收线程 | WebSocket 阻塞读 | 收到语音包放进播放队列，收到事件投给状态机 |
| 播放线程 | 播放队列的条件变量 | 取出语音包，阻塞写给 PortAudio |

- **每个线程只阻塞在一件事上**：麦克风线程卡在读麦克风，卡在读时不影响别的线程播放；接收线程卡在读网络，不影响麦克风。这就是“职责单一”：一个会阻塞的调用，独占一个线程。
- **不用一个线程轮流做**：轮流做的话，一个调用卡住，其它所有事情都停；而这四件事（读麦克风、读网络、写扬声器、画界面）的节奏互不相干。

### 8.2 播放队列：互斥锁加条件变量 {#threads-queue}

接收线程往队列里放语音包，播放线程从队列里取。队列空的时候播放线程要等，不能空转：

```cpp
class PlaybackQueue {
public:
    void Push(std::vector<float> chunk) {
        { std::lock_guard lk(mu_); q_.push(std::move(chunk)); }
        cv_.notify_one();                           // 锁外通知，被唤醒的线程不用立刻再等锁
    }

    // 返回 false 表示已经停止
    bool Pop(std::vector<float>& out) {
        std::unique_lock lk(mu_);
        cv_.wait(lk, [&] { return !q_.empty() || stopped_; });   // 带条件的等待
        if (q_.empty()) return false;
        out = std::move(q_.front());
        q_.pop();
        return true;
    }

    void Stop() {
        { std::lock_guard lk(mu_); stopped_ = true; }
        cv_.notify_all();                           // 叫醒所有等着的线程
    }

private:
    std::mutex mu_;
    std::condition_variable cv_;
    std::queue<std::vector<float>> q_;
    bool stopped_ = false;
};
```

- **`wait` 带条件**：条件变量可能被无故唤醒（虚假唤醒），所以醒来要重新检查队列是否真的不空。
- **条件变量代替 `sleep` 轮询**：轮询要么延迟大，要么白占 CPU；条件变量让线程睡到真有数据才醒。
- **`stopped_` 也在锁里改**：停止的时候要叫醒等着的线程，让它看到 `stopped_` 退出。否则线程会永远睡着，`join` 永远等不到。

### 8.3 `std::atomic` 用在不需要锁的单个变量上 {#threads-atomic}

```cpp
std::atomic<bool> running{true};                    // 所有线程的循环条件
std::atomic<int>  tts_in_flight{0};                 // 已发出还没播完的语音包数

void MicLoop() {
    while (running.load(std::memory_order_acquire)) {
        ReadBlock(buf);                             // 阻塞读
        client->SendAudio(buf, frames);
    }
}
```

- **单个标志位、单个计数，用原子变量就够**：不用为了读一个 `bool` 去拿锁。
- **多个变量必须一起保持一致时用锁**：比如队列和 `stopped_`，所以放在同一把锁下。
- **停止的顺序**：`running` 设为假，对每个阻塞的地方想办法叫醒它（队列 `Stop()`，网络连接关闭使读返回，音频流关闭），然后逐个 `join`。

### 8.4 照实说：这个模型有三个后来发现的问题 {#threads-honest}

- **多个线程同时写同一个 WebSocket 对象**：麦克风线程发音频，播放线程发文本查询，都直接调 `write`。Boost.Beast 规定同一个对象同一时刻只能有一个线程在用，撞上时两帧的字节会交错，服务端判协议错误，表现是“偶尔莫名其妙断线”。
- **大模型调用卡在播放线程里**：播放线程在队列空时同步调大模型打分，要等几秒，这几秒语音只能排队，停止要等请求结束。
- **关闭时一个线程写、一个线程读**：接收线程还阻塞在读里，关闭的线程就在同一个连接上发结束帧，窗口还可能关不掉。
- **后来的改法**：让一个 I/O 线程独占这条连接，别的线程只往队列里投递，立刻返回；控制帧优先发，音频队列有上限，满了丢最旧的并计数；关闭是投给 I/O 线程按顺序执行的一个任务，有总时限。测试配 TSan 跑。详见[代码结构 5.4](/zh/projects/ielts-studio-structure/)。

> **讲的时候按这个顺序**
>
> 1. **四个线程**：主线程画界面，麦克风读音频发出去，接收读网络，播放写扬声器；每个线程只阻塞在一件事上。
> 2. **怎么协调**：队列用互斥锁加条件变量，等到有数据才醒；单个标志位用原子变量；停止时设标志、叫醒、再 `join`。
> 3. **后来发现的问题**：四个线程共用一个 WebSocket 对象，写和写、读和写会撞车。
> 4. **改法**：一个 I/O 线程独占连接，别的线程只投递。

## 9. 音频与网络：PortAudio 采集播放，WSS 上跑自定义二进制帧 {#ielts-audio-net}

> **简历原文**
>
> 跨平台音频采集与播放；Boost.Beast WSS 长连接承载自定义二进制协议（帧头 / 事件 / 压缩）

### 9.1 音频：PortAudio 屏蔽了各平台的设备接口 {#av-portaudio}

- **各平台的音频接口不同**：Windows 是 WASAPI，macOS 是 CoreAudio，Linux 是 ALSA。PortAudio 在上面统一成一套接口，同一份代码三个平台都能编。
- **采集和播放用的是阻塞读写**：麦克风线程调一次读，等一块音频到了才返回；播放线程调一次写，把一块数据交给设备。
- **上行和下行格式不同**：上行 16 kHz，下行 24 kHz float32。每一块的大小决定延迟：原型里输入一块 3200 帧，在 16 kHz 下是 200 ms，后来改成 320 帧（20 ms）。

### 9.2 网络：一条 WSS 长连接 {#av-wss}

- **WSS 是 WebSocket 加 TLS**：先 TCP 连接，再 TLS 握手，再 HTTP 升级成 WebSocket，之后双方随时可以发消息，不用像 HTTP 那样一问一答。
- **长连接适合实时对话**：音频是连续不断的小块，每块一个 HTTP 请求的话开销太大。
- **用 Boost.Beast 是因为它是 C++ 里成熟的 WebSocket 实现**，在 Asio 上，同步和异步两种写法都有。

### 9.3 自定义二进制帧：头、事件号、会话 ID、负载 {#av-frame}

火山的实时语音服务规定了一套二进制帧，每个消息由四部分组成：

| 部分 | 长度 | 内容 |
|---|---|---|
| 头 | 4 字节 | 版本、头长度、消息类型、标志、序列化方式、压缩方式各 4 位，最后 1 字节保留 |
| 事件号 | 4 字节，大端 | 100 开始会话、200 音频、300 打招呼文本、500 指定文本合成等 |
| 会话 ID | 4 字节长度 + 内容 | 建连接的几个事件不带 |
| 负载 | 4 字节长度 + 内容 | JSON 或原始音频，可以 gzip 压缩 |

```cpp
#include <cstdint>
#include <string>
#include <vector>

// 大端写 4 字节
inline void PutU32(std::vector<uint8_t>& out, uint32_t v) {
    out.push_back(v >> 24); out.push_back(v >> 16); out.push_back(v >> 8); out.push_back(v);
}

std::vector<uint8_t> Pack(uint8_t msg_type, uint8_t flags, uint8_t serial, uint8_t compress,
                          uint32_t event, const std::string& session,
                          const std::vector<uint8_t>& payload) {
    std::vector<uint8_t> out;
    out.push_back((1 << 4) | 1);                       // 版本 1，头长度 1（单位 4 字节）
    out.push_back((msg_type << 4) | flags);            // 消息类型、标志各 4 位
    out.push_back((serial << 4) | compress);           // 序列化方式、压缩方式各 4 位
    out.push_back(0);                                  // 保留
    PutU32(out, event);                                // 事件号
    PutU32(out, session.size());                       // 会话 ID：长度 + 内容
    out.insert(out.end(), session.begin(), session.end());
    PutU32(out, payload.size());                       // 负载：长度 + 内容
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}
```

- **头里把几个字段压进半个字节**：版本和头长度共用 1 字节，用移位和或运算打包。
- **整数用大端**：网络字节序，不管两边机器字节序是什么，对得上。
- **长度前缀让接收方知道读多少**：先读 4 字节长度，再读那么多字节，不需要分隔符，负载里是任意二进制也不会误判。
- **解包是打包的逆过程**：每读一段前要检查剩余长度够不够，不够就报错，不能越界读。服务端或网络给来的数据不能默认是对的。
- **协议测试**：打包再解包，应该得到同样的字段；少一个字节、长度写大了，应该报错而不是崩。

### 9.4 照实说：跨平台只验证了其中一部分 {#av-honest}

- **“跨平台”靠的是 PortAudio 和 CMake 加 vcpkg**：代码里没有写平台专用的调用。构建说明目前只写了 macOS 一种，别的平台没有逐个验证过。
- **旧原型的连接层原来不校验证书**，后来改成校验。

> **讲的时候按这个顺序**
>
> 1. **音频**：PortAudio 统一各平台设备接口，阻塞读写，上行 16 kHz，下行 24 kHz。
> 2. **网络**：WSS 长连接，因为音频是连续的小块，实时对话要双方随时能发。
> 3. **帧**：4 字节头、4 字节大端事件号、会话 ID 和负载各是“长度加内容”，负载可以压缩。
> 4. **要点**：长度前缀不用分隔符；解包前检查剩余长度，不信任对端的数据。

## 10. LLM 集成：libcurl 调 OpenAI 兼容接口，约束输出 JSON {#ielts-llm}

> **简历原文**
>
> 基于 libcurl 封装 OpenAI 兼容客户端，约束 LLM 返回结构化 JSON，实现实时评分；逐句评估，支持原地修改、把认可的表达加入个人语料库、改完重新评分

### 10.1 用 libcurl 封装一个 HTTP 客户端 {#llm-client}

- **OpenAI 兼容的接口就是一个 HTTPS POST**：请求体是 JSON（模型名、消息列表），返回体也是 JSON。许多服务商用同一套格式，所以换服务商只改地址和密钥。
- **libcurl 的用法**：设 URL、请求头、请求体，设一个回调把返回的数据收进字符串，调 `curl_easy_perform` 同步执行。

```cpp
static size_t WriteCb(char* p, size_t sz, size_t n, void* user) {
    static_cast<std::string*>(user)->append(p, sz * n);   // curl 分块回调，把每块追加进字符串
    return sz * n;
}

struct HttpResult { long status; std::string body; };

HttpResult PostJson(const std::string& url, const std::string& key, const std::string& body,
                    long timeout_s) {
    CURL* c = curl_easy_init();
    std::string resp;
    curl_slist* hdr = nullptr;
    hdr = curl_slist_append(hdr, "Content-Type: application/json");
    hdr = curl_slist_append(hdr, ("Authorization: Bearer " + key).c_str());
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, hdr);
    curl_easy_setopt(c, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, WriteCb);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &resp);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, timeout_s);        // 一定要设超时
    CURLcode rc = curl_easy_perform(c);
    long status = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &status);
    curl_slist_free_all(hdr);
    curl_easy_cleanup(c);
    return {rc == CURLE_OK ? status : -1, resp};
}
```

- **把 curl 的句柄和链表包进 RAII 对象更稳**：上面示意里为了短没写，真实代码里不要中途 `return` 漏掉清理。
- **超时必须设**：不设的话，服务端不回，这个线程就一直卡着。

### 10.2 约束 LLM 返回结构化 JSON：三层 {#llm-json}

自由文本的评分没法程序处理，所以要求模型只返回 JSON：

1. **在提示词里写清楚结构**：字段名、类型、取值范围，给一个示例。
2. **接口支持的话，打开 JSON 模式**（`response_format` 设为 JSON 对象），让服务端保证返回合法 JSON。
3. **收到之后一律校验**：不信任模型。解析失败、缺字段、分数超出范围，都当失败处理。

```cpp
struct SentenceVerdict {
    int         index;          // 第几句
    int         score;          // 0–9
    std::string issue;          // 问题在哪
    std::string suggestion;     // 建议的改法
};

std::optional<std::vector<SentenceVerdict>> ScoreEssay(const std::string& essay) {
    std::string prompt =
        "Return ONLY a JSON object: {\"sentences\":[{\"index\":int,\"score\":0-9,"
        "\"issue\":string,\"suggestion\":string}]}.\n\nEssay:\n" + essay;
    for (int attempt = 0; attempt < 2; ++attempt) {              // 失败重试一次
        auto r = PostJson(url_, key_, BuildRequest(prompt), 30);
        if (r.status != 200) continue;
        auto v = ParseVerdicts(r.body);                          // 解析 + 校验，失败返回空
        if (v) return v;
    }
    return std::nullopt;                                         // 调用方显示“评分失败，重试”
}
```

- **校验是为了不把模型的偶发错误传给界面**：模型偶尔会多一句解释、漏一个字段、把分数写成字符串。
- **失败时重试一次，再失败就告诉用户**：不能让界面卡在“评分中”。

### 10.3 逐句评估：每一句一个独立的结果 {#llm-sentence}

- **整篇一个总分不够用**：用户要知道具体哪句有问题。所以让模型对每一句单独返回分数、问题和建议。
- **每一句有稳定的编号**：用户改第 3 句，不会让第 4 句的结果错位。
- **原地修改**：界面上用户直接改某一句的文字，不用重新输入整篇。
- **改完重新评分**：只把改过的这一句发给模型重新评，不整篇重评，更快也更便宜。
- **加入个人语料库**：用户认可的好表达（模型建议的，或自己写的），保存到本地的语料库，下次写作可以查。

```cpp
void OnUserEdited(int index, const std::string& new_text) {
    sentences_[index].text = new_text;
    auto v = ScoreSentence(context_around(index), new_text);     // 只评这一句，附上前后文
    if (v) sentences_[index].verdict = *v;
}

void OnUserAccepted(int index) {                                  // 认可这句的表达
    corpus_.Add(sentences_[index].text);
}
```

- **只评一句也要带前后文**：句子的好坏要看它在段落里的位置，单独拿出来评会失真。

### 10.4 照实说：LLM 调用同步卡在线程里 {#llm-honest}

- **旧原型里，评分是在播放线程里同步调用的**（第 8 节），要等几秒，期间语音排队；结果回来时，这一轮可能已经作废。
- **正确的写法**：LLM 调用放在单独的线程或任务里，结果带着“这一轮的编号”回来，编号对不上就丢掉。新引擎把题目、跟进提问、评分都放在后端，客户端只管说和听。

> **讲的时候按这个顺序**
>
> 1. **客户端**：libcurl 发 HTTPS POST，OpenAI 兼容格式，设超时，换服务商只改地址和密钥。
> 2. **结构化输出**：提示词写清楚 JSON 结构，接口支持就开 JSON 模式，收到之后一律校验，失败重试一次。
> 3. **逐句**：每一句单独评分和建议，改一句只重评这一句，认可的表达存进语料库。
> 4. **问题**：旧原型里这个调用卡在播放线程里，应该放到单独的线程。

## 11. 工程质量：Pimpl 隔离重依赖，日志、测试、ASan 兜底 {#ielts-quality}

> **简历原文**
>
> Pimpl 隔离 Boost.Beast、PortAudio、PoDoFo 等重依赖；spdlog 日志、GTest 单元测试、AddressSanitizer；Qt6 桌面界面，支持导出 JSON 报告

### 11.1 Pimpl：头文件里只放接口，重依赖藏进 .cpp {#quality-pimpl}

- **Boost.Beast 的头文件很重**：包含它的每个源文件都要多编译很久；它还会把一大堆宏和类型带进所有包含你头文件的地方。
- **Pimpl（pointer to implementation）**：类的头文件里只声明一个指向实现类的指针，实现类的定义和所有重依赖都放在 `.cpp` 里。

```cpp
// realtime_client.h：没有任何 Boost 头文件
class RealtimeClient {
public:
    RealtimeClient();
    ~RealtimeClient();                      // 必须声明，在 .cpp 里定义
    void SendAudio(const float* pcm, size_t frames);
private:
    struct Impl;                            // 只声明
    std::unique_ptr<Impl> impl_;
};

// realtime_client.cpp：重依赖只在这里
#include <boost/beast/websocket.hpp>
struct RealtimeClient::Impl {
    boost::beast::websocket::stream<boost::beast::ssl_stream<boost::asio::ip::tcp::socket>> ws;
};
RealtimeClient::RealtimeClient() : impl_(std::make_unique<Impl>()) {}
RealtimeClient::~RealtimeClient() = default;   // 这里 Impl 是完整类型，unique_ptr 才能销毁它
```

- **析构函数要放在 `.cpp` 里定义**：`unique_ptr<Impl>` 销毁时需要完整的 `Impl`，头文件里只有声明，编译器在头文件里生成默认析构就会报错。
- **好处有三个**：改实现不触发所有包含者重编译；重依赖的头文件和宏不泄漏到别处；换 PortAudio 或 Beast 的版本只影响一个源文件。
- **代价是一次堆分配和一次间接访问**：所以只用在不在热路径上的类上。音频每 20 ms 一块，这个开销可以忽略。

### 11.2 日志、单元测试、AddressSanitizer {#quality-test}

- **spdlog 日志带级别**：调试时看详细，发布时只留警告。日志里记线程、事件、状态转移，线程问题靠它复盘。
- **GTest 测什么**：能脱离设备和网络测的东西。协议的打包解包、状态机的转移表、JSON 校验。

```cpp
TEST(Protocol, PackThenParseRoundTrips) {
    auto bytes = Pack(/*msg_type=*/1, /*flags=*/4, /*serial=*/1, /*compress=*/0,
                      /*event=*/200, "session-1", {1, 2, 3});
    Frame f;
    ASSERT_TRUE(Parse(bytes, f));
    EXPECT_EQ(f.event, 200u);
    EXPECT_EQ(f.session, "session-1");
    EXPECT_EQ(f.payload, (std::vector<uint8_t>{1, 2, 3}));
}

TEST(Protocol, TruncatedFrameIsRejected) {
    auto bytes = Pack(1, 4, 1, 0, 200, "s", {1, 2, 3});
    bytes.resize(bytes.size() - 1);                    // 少一个字节
    Frame f;
    EXPECT_FALSE(Parse(bytes, f));                     // 必须报错，不能越界读
}

TEST(StateMachine, IllegalEventKeepsState) {
    StateMachine sm;
    sm.Post(Ev::AnswerScored);                         // 空闲状态下不该出现的事件
    EXPECT_EQ(sm.Get(), State::Idle);
}
```

- **AddressSanitizer 抓内存错误**：编译时加 `-fsanitize=address -g`，越界读写、释放后使用、内存泄漏在运行时直接报，带调用栈。
- **ASan 管不到的**：数据竞争要用 TSan（`-fsanitize=thread`）。原型当时只配了 ASan，所以多线程撞车的问题是后来加了假服务端和 TSan 才测出来的。

### 11.3 Qt6 界面和 JSON 报告 {#quality-ui}

- **UI 层只做显示和输入**：不含业务逻辑，业务层的状态变化通过回调投递到 Qt 主线程再更新界面。
- **跨线程更新界面要走投递**：别的线程不能直接改控件，用 Qt 的 `QMetaObject::invokeMethod` 或信号槽把调用排到主线程。
- **导出 JSON 报告**：把一次练习的题目、转写、每句评分和建议序列化成 JSON 文件，用户可以保存或复盘。

> **讲的时候按这个顺序**
>
> 1. **Pimpl**：Boost.Beast 的头文件很重，头文件里只留接口和指针，实现放 `.cpp`，改实现不触发大量重编译；析构要放在 `.cpp` 里。
> 2. **测试**：GTest 测协议打包解包、状态机转移、JSON 校验，这些不依赖设备和网络。
> 3. **ASan**：抓越界、释放后使用；管不到数据竞争，那要 TSan，后来加了。
> 4. **UI**：Qt 只显示，跨线程更新走投递，可以导出 JSON 报告。
