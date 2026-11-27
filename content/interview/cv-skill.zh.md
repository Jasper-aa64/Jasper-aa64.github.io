---
title: "IV. 项目 1：C++ 性能自动优化 Agent Skill"
date: 2026-11-12T00:00:00+08:00
slug: "cv-skill"
description: "简历项目 1 的专页，一条一节：整体的三种坏结果、分诊与 perf、按信号加载修法、正确性与配对计时、缓存案例。每节先放简历原文，再按步骤讲做法，配简化后的代码。第 6 节是缓存案例能跑的完整代码，用来手写练习。"
weight: 6
toc: true
math: true
---

这一页把简历项目 1 逐条拆开，一条一节；项目 2 雅思平台在[另一页](/zh/interview/cv-projects/)。代码都是为了讲清楚做法重写的简化版，名字和结构不是原工程的。数字一律是百分比，因为测试机是虚拟机，绝对值偏高。

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
- **完整的用法和输出怎么读，在[内存序与伪共享的 4.6](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-c2c)**。

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

**手写练习**：这个案例四个版本的完整代码在[第 6 节](#handwrite)。

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

## 6. 手写练习：缓存案例四个版本的完整代码 {#handwrite}

[第 5 节](#skill-case)的代码是片段，这一节把它补成一个带测试的完整程序：基线、分批取数加预取、SIMD、两个核 40 / 24，四个版本跑同一串事件，和基线比结果，再看每个事件的中位耗时。限时 25 分钟。其余各节是流程和设计，按问答准备，不写代码。

> **怎么练**
>
> 1. **先说**：不展开代码，按“开写前说”出声说一遍设计，30 秒以内。
> 2. **再写**：从空白写，编译、运行，打印“全部测试通过！”才算写对；对不上再展开参考代码。
> 3. **第二天重写**：面试官要确认的是“这是你自己写的”，能边写边说出每一行为什么这样写，比写得快更重要。
>
> 参考代码是为了能在一个文件里跑起来重写的简化版：名字和结构不是原工程的，厂商 SDK、文件、设备都用假的代替；只用标准库，g++ 15 加 `-Wall -Wextra` 零警告。编译命令在每份代码的开头。手撕组件的轮换见[准备计划第 4 节](/zh/interview/plan/#handwrite)。

- **开写前说**：基线一个一个读、一个一个算；分批时一批 D = 4 个，第一趟只取数，第二趟集中算；两趟之间预取下一批的两条行，用 `T0` 不用 `NTA`；SIMD 把 4 个期权的同一套算式放进一条指令；两个核时主核算前 40 个、辅核算后 24 个，请求和结果各占一条缓存行，release 写、acquire 读。
- **写的时候注意**：编译加 `-ffp-contract=off`，否则编译器会自己把标量的 `a*x+c` 合成 fma，标量版之间末位也会不一样；SIMD 版用了 fma，按容差比；两个核那一版没加 SIMD，好和基线逐位比。
- **我机器上的一次输出**（Windows，不是案例原来的机器）：每个事件的中位耗时，基线约 3200 ns，分批加预取约 1700 ns，再加 SIMD 约 1500 ns，两个核约 1200 ns。

<details>
<summary><strong>参考代码</strong>（137 行，先自己写，写完或卡住再展开）</summary>

```cpp
// 项目 1 案例：一条行情重算 64 个期权，卡在等内存。基线 → 分批取数 → 预取下一批 → SIMD → 两个核 40 / 24
// 每个版本都和基线比结果（SIMD 用了 fma，按容差比；其余逐位一致），再看每个事件的中位耗时
// 编译：g++ -std=c++17 -O2 -Wall -Wextra -pthread -mavx2 -mfma -ffp-contract=off p5_cache_case.cpp -o cache_case && ./cache_case
// -ffp-contract=off：不让编译器自己把标量的 a*x+c 合成 fma，否则标量版之间末位也会不一样，逐位比对过不了
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <random>
#include <thread>
#include <vector>
#include <immintrin.h>

struct alignas(64) Option {                // 两条缓存行
    double curr_px, actual_px, aux[6];     // 第 1 条：价格那条
    double ema, alpha, pad[6];             // 第 2 条：状态那条
};
static_assert(sizeof(Option) == 128, "一个期权正好两条缓存行");
struct Holding { uint32_t option; double delta; };
constexpr int kPerStock = 64, kMain = 40, D = 4;   // 一批 D 个：2D 条行，留出 LFB 给股票记录和硬件预取
struct Stock { Holding h[kPerStock]; };

inline double alpha_of(double px, double ref, double arg, double& ema) {   // 一串前后相依的运算
    ema = 0.9 * ema + 0.1 * px;
    double x = (px - ref) / (arg + 1.0), a = x;
    for (int i = 0; i < 10; ++i) a = a * x + 0.01 * i;
    return 0.01 * (px - ema) + a;
}

// ---- 基线：一个一个读、一个一个算 ----
void update_base(Option* opt, const Stock& s, double move, int lo, int hi) {
    for (int k = lo; k < hi; ++k) {
        Option& o = opt[s.h[k].option];
        double px = o.curr_px + move * s.h[k].delta;
        o.alpha = alpha_of(px, o.actual_px, o.aux[0] + o.aux[4], o.ema);
    }
}

// ---- 分批 + 预取下一批（+ 可选 SIMD）：第一趟只取数，第二趟集中算 ----
template <bool kSimd>
void update_batched(Option* opt, const Stock& s, double move, int lo, int hi) {
    for (int b = lo; b < hi; b += D) {
        Option* o[D]; alignas(32) double px[D], ref[D], arg[D], ema[D], alpha[D];
        for (int k = 0; k < D; ++k) {                               // 第一趟：D 个期权的读紧挨着发出去
            o[k] = &opt[s.h[b + k].option];
            px[k] = o[k]->curr_px + move * s.h[b + k].delta;
            ref[k] = o[k]->actual_px; arg[k] = o[k]->aux[0] + o[k]->aux[4]; ema[k] = o[k]->ema;
        }
        for (int k = b + D; k < std::min(b + 2 * D, hi); ++k) {     // 下一批的两条行先预取
            const char* p = reinterpret_cast<const char*>(&opt[s.h[k].option]);
            _mm_prefetch(p, _MM_HINT_T0);
            _mm_prefetch(p + 64, _MM_HINT_T0);                      // 用 T0，不用 NTA：下一条行情还要用
        }
        if constexpr (kSimd) {                                      // 4 个期权并排走同一条依赖链
            __m256d P = _mm256_load_pd(px), R = _mm256_load_pd(ref), A = _mm256_load_pd(arg), E = _mm256_load_pd(ema);
            E = _mm256_fmadd_pd(_mm256_set1_pd(0.9), E, _mm256_mul_pd(_mm256_set1_pd(0.1), P));
            __m256d x = _mm256_div_pd(_mm256_sub_pd(P, R), _mm256_add_pd(A, _mm256_set1_pd(1.0))), a = x;
            for (int i = 0; i < 10; ++i) a = _mm256_fmadd_pd(a, x, _mm256_set1_pd(0.01 * i));
            _mm256_store_pd(alpha, _mm256_fmadd_pd(_mm256_set1_pd(0.01), _mm256_sub_pd(P, E), a));
            _mm256_store_pd(ema, E);
        } else {
            for (int k = 0; k < D; ++k) alpha[k] = alpha_of(px[k], ref[k], arg[k], ema[k]);
        }
        for (int k = 0; k < D; ++k) { o[k]->alpha = alpha[k]; o[k]->ema = ema[k]; }   // 写回
    }
}

// ---- 两个核：主核做前 40 个，辅核做后 24 个；请求、结果各占一条缓存行，release 写、acquire 读 ----
struct alignas(64) Request { const Stock* stock; double move; std::atomic<uint64_t> seq{0}; };
struct alignas(64) Result  { std::atomic<uint64_t> seq{0}; };
class Helper {
    Request req_; Result res_; std::atomic<bool> stop_{false}; Option* opt_; std::thread t_;
public:
    explicit Helper(Option* opt) : opt_(opt), t_([this] { loop(); }) {}
    ~Helper() { stop_ = true; t_.join(); }
    void loop() {
        uint64_t seen = 0;
        while (!stop_.load(std::memory_order_relaxed)) {
            uint64_t s = req_.seq.load(std::memory_order_acquire);   // 看到序号，请求内容一定写好了
            if (s == seen) { _mm_pause(); continue; }
            update_batched<false>(opt_, *req_.stock, req_.move, kMain, kPerStock);
            seen = s;
            res_.seq.store(s, std::memory_order_release);            // 结果反过来走一遍
        }
    }
    void event(const Stock& s, double move, uint64_t seq) {
        req_.stock = &s; req_.move = move;
        req_.seq.store(seq, std::memory_order_release);              // 先写请求，再发布序号
        update_batched<false>(opt_, s, move, 0, kMain);              // 主核同时算自己那 40 个
        while (res_.seq.load(std::memory_order_acquire) != seq) _mm_pause();
    }
};

int main() {
    const size_t kOptions = 520000, kStocks = kOptions / kPerStock, kEvents = 20000;
    std::mt19937 rng(3);
    std::vector<Option> init(kOptions);
    for (auto& o : init) { o.curr_px = 1 + rng() % 1000 * 0.01; o.actual_px = o.curr_px * 0.99; o.aux[0] = 0.5; o.aux[4] = 0.25; o.ema = o.curr_px; o.alpha = 0; }
    std::vector<uint32_t> perm(kOptions); for (size_t i = 0; i < kOptions; ++i) perm[i] = uint32_t(i);
    std::shuffle(perm.begin(), perm.end(), rng);                      // 期权散在整块内存里
    std::vector<Stock> stocks(kStocks);
    for (size_t s = 0; s < kStocks; ++s) for (int k = 0; k < kPerStock; ++k) stocks[s].h[k] = {perm[s * kPerStock + k], 0.1 + 0.01 * k};
    std::vector<std::pair<uint32_t, double>> events(kEvents);
    for (auto& e : events) e = {uint32_t(rng() % kStocks), (int(rng() % 21) - 10) * 0.01};

    auto run = [&](auto&& update_event, std::vector<Option>& opt) {
        opt = init;
        std::vector<double> ns; ns.reserve(kEvents);
        for (size_t i = 0; i < kEvents; ++i) {
            auto t0 = std::chrono::steady_clock::now();
            update_event(stocks[events[i].first], events[i].second, i + 1);
            ns.push_back(std::chrono::duration<double, std::nano>(std::chrono::steady_clock::now() - t0).count());
        }
        std::nth_element(ns.begin(), ns.begin() + ns.size() / 2, ns.end());
        return ns[ns.size() / 2];
    };

    std::vector<Option> base, batched, simd, dual;
    double t_base = run([&](const Stock& s, double m, uint64_t) { update_base(base.data(), s, m, 0, kPerStock); }, base);
    double t_bat  = run([&](const Stock& s, double m, uint64_t) { update_batched<false>(batched.data(), s, m, 0, kPerStock); }, batched);
    double t_simd = run([&](const Stock& s, double m, uint64_t) { update_batched<true>(simd.data(), s, m, 0, kPerStock); }, simd);
    dual = init;
    double t_dual;
    { Helper h(dual.data()); t_dual = run([&](const Stock& s, double m, uint64_t seq) { h.event(s, m, seq); }, dual); }

    for (size_t i = 0; i < kOptions; ++i) {
        assert(batched[i].alpha == base[i].alpha && batched[i].ema == base[i].ema);   // 只改顺序，逐位一致
        assert(dual[i].alpha == base[i].alpha);
        assert(std::fabs(simd[i].alpha - base[i].alpha) <= 1e-12 * (1 + std::fabs(base[i].alpha)));  // fma 改了舍入
    }
    std::printf("每个事件的中位耗时：基线 %.0f ns，分批+预取 %.0f ns，再加 SIMD %.0f ns，两个核 %.0f ns\n",
                t_base, t_bat, t_simd, t_dual);
    std::printf("全部测试通过！\n");
}
```

</details>
