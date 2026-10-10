---
title: "交易系统笔记 #7:分支预测与分支优化"
date: 2026-10-09
slug: "branch-prediction-branch-optimization"
description: "CPU 为什么必须猜分支、怎么猜、猜错多贵，以及怎么把分支消掉、提示和分离。第一部分：前端与推测执行、BTB / RAS / 间接目标预测器 / 带历史的方向预测、一次预测失败约 15–20 个周期、可预测性来自数据（排序实验和编译器的 if-conversion）、各种 C++ 分支归哪个预测器。"
summary: "前端每个周期都要取指令，可一条分支要十几个周期后才算出往哪走，所以只能先猜。猜对几乎不花钱，猜错要把之后的活全部扔掉，约 15–20 个周期。同一条 if，数据有规律就猜得准，随机就只能猜对一半；而编译器可能早已把它变成了 cmov。"
chapter: 1
categories: [Systems]
tags: [cpp, branch-prediction, pipeline, speculative-execution, cmov, hft, low-latency]
toc: true
math: true
homepage: false
---

把 100 万个 0–199 的随机整数加起来，只加偶数，重复 64 遍。同一段代码，先把数组排个序再跑，快约 7 倍。数据一个没变，加起来的结果也一样，差的只是“下一个数是奇是偶”有没有规律。

可是用 `g++ -O2` 编译，两个版本又一样快了。这两件事都要从 CPU 前端的分支预测器讲起：它为什么必须猜，怎么猜，猜错了要付多少，编译器又是怎么把分支整个拿掉的。

## 1. 分支预测器：CPU 为什么要猜、猜错多贵

### 1.1 在硬件地图上的位置：前端

速查页的<a href="/maps/hardware-map.zh.html" target="_blank" rel="noopener">硬件地图</a>上画的大多是“数据”那一侧：load / store、缓存、内存。分支预测在另一侧，**前端**（front end）：负责取指令、译码，把指令送进后端去执行。顺序是：

1. **取指**（fetch）：按“下一条指令的地址”从 L1I（指令缓存）取一段字节。
2. **译码**（decode）：拆成微操作（µop）。
3. **重命名、进 ROB**：进入乱序执行的窗口（ROB 见[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/) 1.3.2）。
4. **执行**：分支在这里才真正算出条件、知道往哪走。
5. **退休**：按程序顺序确认。

**分支预测器**（branch predictor）就挂在第 1 步旁边：每取一段指令，它当场回答“这里面有没有分支、往哪跳”，取指单元按它的回答去取下一段。

### 1.2 为什么必须猜：流水线比分支间隔长

两个数放在一起就明白了：

- 从取指到执行，一条指令要走约 15–20 个周期（流水线深度）。
- 普通代码里，每 5–7 条指令就有一条分支（约 15%–20% 的指令是分支）。前端每周期能取 4–8 条指令，也就是几乎每个周期都会碰到分支。

如果每碰到一条分支都停下来等它执行完再取后面的指令，每条分支要白等 15–20 个周期，CPU 一大半时间在空转。所以前端不等，先按预测的方向接着取、接着执行，这叫**推测执行**（speculative execution）。推测执行的结果先放在 ROB 里，分支算出来确认猜对了，才允许它们退休。

### 1.3 预测器怎么猜：方向、目标、历史

这里的“分支”泛指所有会改变“下一条指令从哪取”的指令：`if` 编译出的条件跳转、函数调用 `call`、函数返回 `ret`、虚函数这类间接跳转。预测器猜的始终是**下一条指令的地址**，不是数据的值（函数的返回值是数据，放在寄存器里，不用猜）。一条分支要猜两件事：**往不往跳**（方向），**跳到哪**（目标）。不同的分支，难的地方不一样：

- **目标**：靠 **BTB**（branch target buffer，分支目标缓冲），按分支指令的地址记“上次跳到了哪”，约 4000–12000 项。取指时一查，就知道这段字节里有没有已知的分支、目标在哪。
- **函数返回**：`ret` 一定会跳，难的是跳回哪。同一个函数被不同的地方调用，就要回到不同的地方：

  ```cpp
  void log_it() { /* … */ }                // 结尾是一条 ret
  void on_trade() { log_it(); update(); }  // 这次 ret 要回到这里，接着执行 update()
  void on_quote() { log_it(); quote(); }   // 下次同一条 ret 要回到这里，接着执行 quote()
  ```

  靠 **RAS**（return address stack，返回地址栈，16–32 项）：取指时看到 `call`，就把“调用完该回到哪”压进去；看到 `ret`，就弹出栈顶，当作目标去取指。它仍然是“猜”：压栈和弹栈都发生在取指的时候，而 `ret` 真正执行、从内存里的调用栈读出返回地址，要等 15–20 个周期以后，那时才核对对不对。只要 `call` 和 `ret` 一一配对，几乎总是对的。会猜错的有两种：调用层数超过 RAS 的容量（很深的递归）；`call` 和 `ret` 没配对，比如抛异常、`longjmp` 直接跳过了中间几层函数的 `ret`，RAS 里剩下的旧地址会让后面几次 `ret` 猜错。
- **间接分支**（虚函数、函数指针、`switch` 的跳转表）：一条指令可能跳到多个目标，用**间接目标预测器**，按“这条指令 + 最近的历史”记目标。
- **方向**：最简单的是给每条分支一个 **2 位饱和计数器**：跳一次加 1、不跳减 1，在 0–3 之间，≥ 2 就猜“跳”。它能把循环猜得很准（跳 99 次、最后不跳 1 次，只错最后一次），偶尔一次反常也不会立刻改主意。

<a href="/images/branch-prediction/two-bit-counter.zh.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/two-bit-counter.zh.svg" alt="2 位饱和计数器的 4 个状态 0、1、2、3：分支跳了加 1，没跳减 1，0 和 1 猜不跳，2 和 3 猜跳。下面的例子是一个循环跳 7 次、退出时不跳 1 次、再进循环：只在退出那次猜错，计数器从 3 降到 2 仍然猜跳。" loading="lazy" decoding="async"></a>

现代预测器在这之上加了**历史**：把最近 50–1000 条分支的结果（跳 / 不跳）记成一串**全局历史**（global history），和分支地址一起去查表。这样它能学会“上一条分支跳了，这一条就不跳”“每 3 次跳 1 次”这类规律。业界主流的设计（TAGE 一类）用几张表，各自配不同长度的历史，取最长的那个命中的。结果是：**有规律的分支，哪怕规律很长，也能学会；没有规律的分支，谁也学不会。** 一个每次都是随机 50/50 的条件，再好的预测器也只能猜对一半。

普通程序里，这些结构加起来能猜对 95%–99% 以上的分支。

### 1.4 猜错的代价：冲刷流水线

分支执行时发现猜错了：

1. 猜错之后取进来的所有指令（还在流水线里的、已经进 ROB 的、已经执行完的）全部作废。
2. 取指单元回到正确的地址，从头开始取。
3. 新指令要再走一遍取指、译码、重命名，才能重新填满后端。

<a href="/images/branch-prediction/pipeline-flush.zh.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/pipeline-flush.zh.svg" alt="4 级流水线（取指、译码、执行、退休）的时间线，横轴是周期 1–10。猜对时分支 B 后面的指令一个接一个进来。猜错时 B 在第 5 周期执行，错误路径上的 W1、W2 作废，第 6 周期起重新取 I3，执行级空了 2 个周期。" loading="lazy" decoding="async"></a>

代价约等于从取指到执行的流水线深度，**约 15–20 个周期**，4 GHz 下约 4–5 ns。按每周期 4–8 条算，等于丢掉 60–160 条指令的执行机会。（猜错的路径上发出的 load 已经把行搬进了缓存，这一点不会撤销，这也是 Spectre 这类漏洞的来源，这里不展开。）

拿[内存延迟与带宽](/zh/posts/low-latency-memory-latency-bandwidth/)里的数对比：一次 L1 命中约 1 ns，一次 L2 命中约 3–5 ns，一次分支预测失败约 4–5 ns。热路径上一次猜错，和一次 L2 命中差不多贵。区别是：缓存缺失可以和别的缺失重叠（MLP），分支预测失败把后面的活全扔了，没法和自己后面的工作重叠。

### 1.5 数据决定猜得准不准：排序实验

一个经典的例子（`data` 是 16384 个 0–199 的随机整数，外层重复 10000 遍）：

```cpp
for (unsigned i = 0; i < 10000; ++i) {
    for (unsigned c = 0; c < arraySize; ++c) {
        if (data[c] % 2 == 0) {
            evenSum += data[c];
        }
    }
}
```

同一段循环，`data` 排序和不排序各跑一遍，排序版只多了一行 `std::sort(data, data + arraySize)`。

- **不排序**：每个数是奇是偶完全随机，这条 `if` 的方向没有规律，预测器只能猜对约一半。每个元素平均多付 $0.5 \times (15\text{–}20) \approx 8\text{–}10$ 个周期，比循环体本身（1–2 个周期）贵好几倍。
- **排序后**：0–199 每个值大约有 82 个，排好以后是 82 个偶数、82 个奇数、82 个偶数……这样一段一段交替。一共 200 段，方向只在段与段的边界上变，每个交界处猜错 1–2 次，一遍 16384 次里只错约 200–400 次，约 1%–2%。

<a href="/images/branch-prediction/sorted-strip.zh.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/sorted-strip.zh.svg" alt="两条格子：不排序时 20 个随机数奇偶乱跳，2 位计数器猜错 10 个；排序后是一段 36 接一段 37，只在交界处猜错 2 个。" loading="lazy" decoding="async"></a>

所以排序后快好几倍（实测见本节后面）。这个例子说明：**同一条分支、同一段代码，可预测性来自数据**。

**这里有一个编译器的坑**：GCC 13.3 在 x86-64 上从 `-O1` 起就把这个 `if` 变成了无分支的写法，内层循环里只剩 `and`（取最低位）加 `cmove`（条件成立才把加完的值搬回 `evenSum`），没有条件跳转；`-O3` 还会向量化。这时排不排序一样快，实验看不到差别。想看到分支预测失败的代价，要加 `-fno-if-conversion -fno-if-conversion2 -fno-tree-vectorize`，内层才会留下 `je`。所以讨论“这里有没有分支”之前，先看汇编。（`cmov` 为什么能消掉分支、什么时候编译器不敢用，放在第 2 部分讲。）


<a href="/images/branch-prediction/branch-predictability.zh.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/branch-predictability.zh.svg" alt="两条保留分支的曲线和一条 cmov 的平线，横轴是偶数比例 p，纵轴是每个元素的 ns。100 万个数时，保留分支的曲线是一顶帐篷，p = 50% 最高约 2.9 ns，两头约 0.25–0.44 ns；16384 个数时几乎贴着底，最高约 0.77 ns；cmov 全程约 0.44 ns；p = 50% 排序后约 0.40 ns。" loading="lazy" decoding="async"></a>

<a href="/images/branch-prediction/predictor-memorize.zh.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/predictor-memorize.zh.svg" alt="p = 50% 的随机数组，横轴是数组长度 1K 到 4M（对数），纵轴是每个元素的 ns。16K 以内约 0.6–0.7 ns，32K 跳到约 2.1 ns，256K 以上约 2.85 ns；排序后一直约 0.4 ns。" loading="lazy" decoding="async"></a>

> 实测（AMD Ryzen 5 5600GT，一个核，GCC 16.2.0，`-O2`；保留分支的版本加 `-fno-if-conversion -fno-if-conversion2 -fno-tree-vectorize`。数组里偶数的比例 p 从 0% 扫到 100%，同一组数反复跑约 6700 万个元素，每个点测 5 次取最快）：
>
> - **保留分支、100 万个数：一顶帐篷**。p = 50% 时约 2.87 ns/个，排序后约 0.40 ns，快约 7 倍。曲线几乎是直线爬上去、再直线降下来：方向随机时，最好的猜法是一直猜多的那一边，猜错率就是 $\min(p, 1-p)$。每个元素多出来的时间约为 $\min(p, 1-p) \times 4.9\ \text{ns}$：p = 50% 时多 2.43 ns，也就是每次猜错约 4.9 ns；拿它去算 p = 25%，0.25 × 4.9 ≈ 1.2 ns，实测多 1.21 ns。
> - **`cmov` 版：一条平线**，约 0.44 ns/个，和 p、排不排序都没关系。每个元素都要等上一次的和算完（`add` 再 `cmove`，约 2 个周期），这条依赖链就是它的速度。
> - **两头，留着分支反而更快**。p = 100% 时全猜对，约 0.25 ns，比 `cmov` 快；p = 0% 时约 0.44 ns，因为每个元素要跳两次（跳过加法、循环回跳），被“每个周期大约只能执行一次跳转”卡住。什么时候该换成 `cmov`，第 2 部分讲。
> - **只有 16384 个数时，几乎看不出代价**。同样随机，p = 50% 只要约 0.66 ns，排序后约 0.44 ns，只差 1.5 倍。同一串 16384 个方向被反复跑了 4000 多遍，预测器用长历史把它背了下来。第二张图在 p = 50% 上扫数组长度：16384 个以内都是约 0.6–0.7 ns，32768 个就跳到约 2.1 ns，26 万个以上稳定在约 2.85 ns。所以测分支的代价，不能拿一小段数据反复回放：真实的行情不会重复，回放测出来的会偏乐观。

**怎么测**：Linux 上 `perf stat -e branches,branch-misses ./prog`，直接给出分支总数和猜错的次数，比值就是预测失败率。Windows 上没有 `perf`，AMD 的机器用 AMD uProf，Intel 用 VTune。热路径上看到预测失败率在几个百分点以上，才值得动手。

### 1.6 分支类型：各归哪个预测器

C++ 里会产生分支的写法，按 1.3 对上号：

| 写法 | 机器码里是什么 | 谁来猜 |
|---|---|---|
| `if` / `else`、三元 `?:`、`&&` / `\|\|` 的短路求值、循环条件、`break` / `continue` | 条件跳转（`jcc`），目标固定 | 方向预测器 |
| 直接函数调用 | `call` 一个固定地址 | BTB（无条件，几乎不会错） |
| 函数返回 | `ret` | RAS |
| `switch`（编译成跳转表时） | 间接跳转 `jmp [表 + 下标×8]` | 间接目标预测器 |
| 虚函数、函数指针 | 间接调用 `call [寄存器]` | 间接目标预测器 |

三元 `?:` 和短路求值不一定真的产生跳转：编译器可能把它们变成 `cmov`，就像 1.5 那样。短路求值则相反，`a && b` 往往会多出一条分支（`a` 为假就跳过 `b`）。

虚函数的预测看的是“这一处调用的实际类型有没有规律”：一个循环里对象类型总是一样，目标每次一样，几乎不错；类型随机混在一起，每次都可能错，和 1.5 的不排序一样。

## 2. 消除分支：把“猜往哪走”换成“按条件选”

第 1 部分最后留了一个问题：100 万个随机数时，`cmov` 版平在约 0.44 ns/个，比保留分支的 2.87 ns 快 6 倍多；可数据全是偶数时，保留分支只要约 0.25 ns，又比 `cmov` 快。消除分支不是白拿的，这一部分讲它换掉了什么、有哪几种写法、什么时候该换。

### 2.1 控制依赖与数据依赖：消除分支换掉了什么

一条 `if` 在机器码里是条件跳转，后面的指令**取哪条**取决于条件，这叫**控制依赖**（control dependency）。1.2 讲过，CPU 不等它，直接猜一个方向往下跑：猜对了，条件什么时候算出来都不影响速度；猜错了，付约 15–20 个周期。

把分支消掉，就是让后面要执行的指令固定下来，条件只决定**选哪个值**。这叫**数据依赖**（data dependency）：结果要等条件和两个候选值都算出来才能定，下一条用到结果的指令也得等。没有东西可猜，所以不会猜错。可它也没法“先往下跑”，条件那几个周期的延迟每次都要付。

所以消除分支是拿“偶尔一次 15–20 周期”换“每次多 1–2 个周期”。下面五种写法（2.2–2.6）都是这一笔交易，2.7 算什么时候划算。下面的汇编都是 GCC 13.3 `-O2` 的真实输出。

### 2.2 三元与 cmov：两个值都备好，按条件选

```cpp
int pick(int input, int threshold, int value1, int value2) {
    return (input > threshold) ? value1 : value2;
}
```

GCC 生成：

```asm
cmpl    %esi, %edi        # input 和 threshold 比较
movl    %edx, %eax        # 先放 value1
cmovle  %ecx, %eax        # 如果 input <= threshold，换成 value2
ret
```

**`cmov`**（conditional move，条件传送）不是跳转：它总是执行，只是按标志位决定目标寄存器要不要换成源的值。前端不用猜任何东西，取指一路往下走。

编译器只在“两边都算一遍也安全、也不贵”时才这么做：

- **两边有副作用**（函数调用、写内存、I/O）：两边都执行就改变了程序的行为，不能变。
- **有一边要读内存、而这次读可能不合法**：

  ```cpp
  int load_or_zero(const int* p) {
      return p ? *p : 0;
  }
  ```

  GCC 生成的是 `testq %rdi, %rdi` + `je`，保留了分支。变成 `cmov` 就得无条件执行 `*p`，`p` 是空指针时会崩。
- **两边的计算很长**：两边都算，就把便宜那边省下的活白白做了。

反过来也成立：写成 `if`，编译器也可能自己变成 `cmov`。1.5 的 `even_sum` 就是这样；下一节 `sign` 的有分支写法，在 GCC `-O2` 下也被编成了 `setne` + `cmovg`。三元只是更容易被变成 `cmov`，不保证。要确认，就看汇编。Clang 有 `__builtin_unpredictable(cond)`，告诉编译器这个条件难猜，倾向用 `cmov`。

### 2.3 无分支计算：用比较结果和掩码算出来

**比较的结果本身就是 0 或 1**：

```cpp
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    return 0;
}

int sign_branchless(int x) {
    return (x > 0) - (x < 0);   // 比较结果是 0 或 1，正数 1 - 0，负数 0 - 1
}
```

GCC 把 `sign_branchless` 编成 `setg` 取 `x > 0`，再用 `shrl $31` 取出符号位当作 `x < 0`，两者相减，没有跳转。

**掩码选择**：条件为真时掩码全 1，为假时全 0，再用 `&` 和 `|` 拼出结果。

```cpp
int select_mask(bool cond, int a, int b) {
    int mask = -static_cast<int>(cond);   // 1 -> 0xFFFFFFFF，0 -> 0
    return (a & mask) | (b & ~mask);      // cond ? a : b
}
```

掩码必须是“全 1 或全 0”。直接拿 `bool` 去 `&`，`1 & a` 只留下 `a` 的最低位，结果是错的。要按符号得到掩码，可以写 `x >> 31`：负数得到全 1，非负得到 0（C++20 起规定有符号右移是算术右移，之前是实现定义）。

**1.5 的 `even_sum` 不用 `if`**：

```cpp
for (unsigned c = 0; c < n; ++c) {
    int x = data[c];
    sum += x & -static_cast<int>((x & 1) == 0);   // 偶数加 x，奇数加 0
}
```

编出来是 `not`、`and $1`、`neg`、`and`、`add`，循环里只剩末尾那条回跳。和 `cmov` 一样，`sum` 每次都要等这几条算完。

适合数值计算、选最大最小、钳位（clamp）。代价是可读性差，而且多数情况下编译器自己就能把简单的 `if` 变成 `cmov`，手写前先看汇编。

### 2.4 查表：用下标取结果

**值查表**：输入范围小，就把每个输入的结果提前算好，运行时用输入当下标去取。

```cpp
constexpr int fee_bps[3] = {2, 5, 10};   // 三种订单类型的手续费率（万分之几）
int fee_lookup(unsigned type) { return fee_bps[type]; }
```

编出来就是一条 `movl (%rax,%rdi,4), %eax`，真的没有分支。代价变成一次访存：表在 L1D 里约 1 ns；表大到落进 L2 约 3–5 ns，已经和一次猜错差不多；落到内存约 80–120 ns，比猜错贵得多（见<a href="/zh/ref/cpu-memory/#latency" target="_blank" rel="noopener">速查页 2.1</a>）。所以查表只适合小表，热路径上的表要能一直待在 L1D 里。

**函数指针表**：

```cpp
using HandlerFunc = void(*)(const Order&);
constexpr HandlerFunc handlers[] = {handle_type_0, handle_type_1, handle_type_2};

void process_order(const Order& order) {
    if (order.type < 3) {
        handlers[order.type](order);
    }
}
```

编出来是：

```asm
movl    (%rdi), %eax            # order.type
cmpl    $2, %eax
ja      .L28                    # 边界检查：一条条件跳转
leaq    handlers(%rip), %rdx
jmp     *(%rdx,%rax,8)          # 间接跳转：目标从表里读
```

它没有消除分支，是把几条条件跳转换成了**一条间接跳转**，归**间接目标预测器**（1.3）。订单类型有规律（全是同一种、或者短周期重复），几乎不错；类型随机混在一起，照样经常猜错，和虚函数一样。它的好处是：不管有多少种类型，都只有一条要猜的跳转，而不是一串 `if`。边界检查那条 `ja` 几乎总是不跳，好猜。

### 2.5 if-else 链与 switch：编译器怎么排

**`if-else` 链**：每个条件是一条单独的条件跳转。代价看“一次走下来执行了几条、每条好不好猜”：最常见的情况放最前面，大多数时候只执行一两条就出来了。每条各自有预测器的记录，条件多了不会让每一条更难猜，只是走得越深，要过的条件跳转越多。

**`switch`**：GCC 按 `case` 的分布选三种做法。

- **`case` 连续、每个 `case` 做不同的事 → 跳转表**：

  ```cpp
  switch (kind) {
      case 0: handle_type_0(o); break;
      case 1: handle_type_1(o); break;
      // ... case 2、3、4
  }
  ```

  ```asm
  cmpl    $4, %eax
  ja      .L30                     # 超出 0–4 就跳走
  leaq    .L33(%rip), %rdx         # .L33 是一张表，存每个 case 代码的相对地址
  movslq  (%rdx,%rax,4), %rax
  addq    %rdx, %rax
  notrack jmp *%rax                # 间接跳转
  ```

  和函数指针表一样，是一条间接跳转。查表本身和 `case` 数量无关，但“猜不猜得准”仍看 `kind` 有没有规律。
- **`case` 连续、每个 `case` 只返回一个值 → 值查表**：

  ```cpp
  switch (type) {
      case 0: return 2;
      case 1: return 5;
      // ... case 2、3、4
      default: return 0;
  }
  ```

  GCC 直接生成一张常量数组（汇编里叫 `CSWTCH`），一条 `movl (%rax,%rdi,4), %eax` 取值，只剩一条好猜的边界检查。这才是真的没有分支。
- **`case` 稀疏（1、10、1000）→ 一串比较**：`cmpl $10` + `je`、`cmpl $1000` + `je`，最后一个用 `cmovne`。`case` 多时会排成二分查找的比较树。

所以“把 `case` 改成连续”有用，但它换来的是跳转表或值查表。前者仍要猜，后者才消掉了分支。

### 2.6 循环展开：少几次回跳，主要的收益不在分支

一次迭代做原来几次的活：

```cpp
long long sum_unroll4(const int* a, unsigned n) {
    long long s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    unsigned i = 0;
    for (; i + 4 <= n; i += 4) {
        s0 += a[i];
        s1 += a[i + 1];
        s2 += a[i + 2];
        s3 += a[i + 3];
    }
    for (; i < n; ++i) s0 += a[i];   // 剩下不到 4 个
    return s0 + s1 + s2 + s3;
}
```

**分支上省了什么**：每 4 个元素才有一次回跳。可 1.3 讲过，固定往回跳的循环分支本来就几乎不会猜错，展开省下的主要是 `i++`、`cmp`、`jne` 这几条指令本身，猜错几乎没少。循环体里如果有一条难猜的 `if`，展开以后它变成 4 条，一条也没少。

**真正的收益**：四个累加器 `s0`–`s3` 是四条独立的依赖链，可以同时跑（[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 讲过的多累加器），这和分支无关。

- 固定 4 次这种短循环，GCC `-O2` 自己就会全部展开，不用手写。
- 让编译器展开：GCC 写 `#pragma GCC unroll 4`，`#pragma unroll` 是 Clang 的写法。
- 展开越多，代码越大，会挤占 L1I 和 uop 缓存，热路径上不是越多越好。

### 2.7 无分支不总是更快：怎么判断

先看 `even_sum` 每个元素的依赖链：

<a href="/images/branch-prediction/cmov-chain.zh.svg" target="_blank" rel="noopener"><img src="/images/branch-prediction/cmov-chain.zh.svg" alt="两行依赖链，横轴是周期 1–8。保留分支并猜对时，链上只有 add，每个元素 1 个周期，load、and、je 不在链上。cmov 版链上是 add 加 cmove，每个元素 2 个周期，cmove 要等条件和 sum + x 都算出来。实测猜对时约 0.25 ns/个，cmov 约 0.44 ns/个。" loading="lazy" decoding="async"></a>

`sum` 每次都要等上一次的结果。保留分支并且猜对时，链上只有一条 `add`，约 1 个周期；判断奇偶的 `and`、`je` 不在链上，晚点核对就行。换成 `cmov`，链上是 `add` 再 `cmove`，`cmove` 还要等条件，约 2 个周期。1.5 的实测正好对上：p = 100% 时分支版约 0.25 ns/个，`cmov` 版约 0.44 ns/个；排序后分支版约 0.40 ns/个，也比 `cmov` 快。

**什么时候换**：比较两边每个元素多付的时间。

$$
\underbrace{\text{猜错率} \times \text{一次猜错的代价}}_{\text{留分支多付的}}
\quad\text{vs}\quad
\underbrace{\text{cmov 每个元素多付的}}_{\text{约 } 0.44 - 0.25 = 0.19\ \text{ns}}
$$

一次猜错约 4.9 ns，所以这个循环的平衡点在猜错率约 $0.19 / 4.9 \approx 4\%$：低于约 4% 留分支，高于约 4% 换 `cmov`。实测里，p = 95%（猜错约 5%）时分支版约 0.51 ns，已经比 `cmov` 慢；p = 100% 时约 0.25 ns，比 `cmov` 快。这个 4% 只属于这个循环：`cmov` 多付多少看链上多了什么，换一个循环要重新算。

**`cmov` 会把访存也挂到链上**：二分查找用 `cmov` 选下一步的左右边界，就没有猜错了。可下一次读的地址要等这次 `cmov` 算完才知道。数组小、在缓存里时，这很划算。数组大到放不下缓存时，每一层都要等一次完整的内存延迟（约 80–120 ns）。有分支的版本虽然一半会猜错，但猜对的那一半已经提前把下一层的读发出去了，推测执行顺带起了预取的作用。所以大数组上谁快要实测，不能想当然。

**怎么决定**：

1. 先看汇编，确认那条分支真的在：编译器可能已经把它变成了 `cmov`，也可能把你写的三元编回了分支。
2. 用 `perf stat -e branches,branch-misses` 看猜错率。几个百分点以下，留着分支。
3. 猜错率高、而且分支在关键路径上，再换 `cmov`、掩码或查表，换完再测一次。
