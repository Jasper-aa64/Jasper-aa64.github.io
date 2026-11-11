---
title: "交易系统笔记 #22：编译器：开哪些选项，怎么看它做了什么"
date: 2026-11-09
slug: "compiler-options-lto-linking"
description: "编译器只做它能证明结果不变的变换。-O2 已经包含绝大多数优化，-O3 多出来的主要是循环变换和带运行时检查的向量化；-march 放开新指令，也把程序绑在了那一代 CPU 上；每个 .cpp 单独编译，跨文件的小函数内联不了，要靠 LTO；动态库里的调用多一次间接跳转，还会挡住内联。最后是怎么确认编译器到底做了什么。"
summary: "编译器能做什么，取决于它能证明什么。选项放开它能做的范围（-O3、-march、LTO），提示告诉它证明不了的事（restrict、likely），汇编和优化报告告诉你它最后做了没有。"
chapter: 2
light: true
categories: [Systems]
tags: [cpp, gcc, compiler, optimization, lto, pgo, linking, hft, low-latency]
toc: true
math: true
build:
  list: never
---

热路径上的很多优化，编译器本来就会做：常量折叠、内联、把乘法换成移位、循环向量化。它不做，通常不是因为不会，而是**证明不了换了以后结果不变**：两个指针会不会指向同一块内存，浮点加法换个顺序末位会不会变，另一个 `.cpp` 里的函数长什么样。所以和编译器打交道就三件事：用选项放开它能做的范围，用提示告诉它证明不了的事，再看汇编确认它做了没有。

> **这篇的问题链：每解决一个，下一个就露出来**
> 1. **编译器只做能证明的变换**：先看它自己会做什么、卡在哪（第 1 节）。
> 2. **默认不开优化**：选 `-O2` 还是 `-O3`（第 2 节）。
> 3. **开了优化，默认只用 SSE2**：`-march` 放开新指令，代价是绑死机器（第 3 节）。
> 4. **每个 `.cpp` 单独编译，跨文件内联不了**：LTO（第 4 节）。
> 5. **热路径调到动态库里，多一次间接跳转、内联不了**：静态链接，或者收紧符号可见性（第 5 节）。
> 6. **选项和提示都加了，它到底做了没有**：看汇编和优化报告（第 6 节）。

---

## 1. 编译器自己会做什么：只做能证明结果不变的变换 {#what-compiler-does}

1. **整数和控制流上的变换，主流编译器都会做**
   - **常量折叠和常量传播**：`x = 3 * 4` 编译时就算成 12，再顺着用到 `x` 的地方代进去。
   - **公共子表达式消除和循环不变代码外提**：同一个式子算两遍只留一遍，循环里不变的计算提到循环外面。
   - **强度削弱**：乘常数换成移位加法，除以常数换成乘一个魔数再移位（[#12](/zh/posts/strength-reduction-arithmetic/)）。
   - **内联、尾调用变跳转、去虚拟化**：能看到函数体就内联；虚调用能确定目标就改成直接调用（[#8](/zh/posts/crtp-static-polymorphism/)）。
2. **卡住它的是三类“证明不了”**
   - **浮点运算不满足结合律**：`(a + b) + c` 和 `a + (b + c)` 末位可能不同，所以不开 `-ffast-math` 时，GCC 不会为了向量化重排浮点求和（[#9](/zh/posts/loop-optimization/)）。
   - **指针可能重叠（别名）**：写 `a[i]` 可能改到 `b[i]`，编译器只能每轮重读，或者在运行时先检查一遍（[#10](/zh/posts/pointer-memory-access/) 第 1 节）。
   - **看不到别的编译单元**：另一个 `.cpp` 里的函数只知道签名，不知道函数体，就没法内联，也没法知道它会不会改你的变量（第 4 节）。
3. **编译器之间差在激进程度，不在会不会**
   - **例子**：整数求和拆成多个累加器，Clang 会自己做，GCC 不做（[内存延迟与带宽专题](/zh/posts/low-latency-memory-latency-bandwidth/) 1.5.1）；数组循环展开，Clang 展得更多。
   - **所以换编译器、换版本以后，热函数要重新看一遍汇编**（第 6 节）。

## 2. 默认不开优化：-O2 已经包含绝大多数，-O3 多的是循环变换 {#opt-levels}

### 2.1 -O3 比 -O2 多什么：GCC 16 实测只多 13 个开关 {#o2-vs-o3}

1. **用 `-Q --help=optimizers` 直接看每一级打开了哪些开关**
   - **结果**：GCC 16.2 在 `-O2` 下打开 145 个，`-O3` 下 158 个。内联（`-finline-functions`）、两种自动向量化、小循环展开，`-O2` 都已经开了。
   - **`-O3` 多出来的几乎都是循环变换**：`-funswitch-loops`（把循环里不变的 `if` 提到外面，复制出两个循环）、`-floop-interchange`（交换嵌套循环的顺序）、`-ftree-loop-distribution`（一个循环拆成几个）、`-fpeel-loops`、`-fsplit-loops`、`-floop-unroll-and-jam`，加上 `-fipa-cp-clone`（为常量参数复制一份专用的函数）和 `-fpredictive-commoning`。
   - **还有一处是向量化的成本模型**：`-O2` 用 `very-cheap`，只在不需要运行时检查、不需要额外尾巴循环时才向量化；`-O3` 用 `dynamic`，肯为向量化付这些代价。
2. **例子：同一个数组相加，`-O2` 不向量化，`-O3` 向量化**

   ```cpp
   void add(float* a, const float* b, const float* c, int n) {
     for (int i = 0; i < n; ++i) a[i] = b[i] + c[i];   // a 可能和 b、c 重叠
   }
   ```

   - **`-O2`**：`-fopt-info-vec-optimized` 什么都不报。`a` 可能和 `b`、`c` 重叠，要向量化就得先在运行时检查，`very-cheap` 不肯付这个钱。
   - **`-O3`**：报“loop versioned for vectorization because of possible aliasing”。编译器生成两个版本，运行时先比一下地址，不重叠走向量版，重叠走标量版。
   - **三个指针都加上 `__restrict`**：`-O2` 也向量化了。你替它证明了不重叠，就不需要运行时检查。
3. **`-O3` 不一定更快**
   - **代码变大**：复制出来的循环版本、展开的循环都要占指令缓存。热路径本来就小，被撑出 L1i 反而更慢。
   - **所以两级都编一份，用自己的回放数据比延迟分布（p50、p99），不比平均值**（[#21](/zh/posts/trading-system-latency-metrics/) 1.2）。

### 2.2 和结果有关的几个选项：不改语义的随便开，改语义的要想清楚 {#semantic-flags}

1. **不改结果的，热路径程序通常都开**
   - **`-fno-exceptions`、`-fno-rtti`**：热路径本来就不该抛异常、不该用 `dynamic_cast`。去掉以后代码小一些，编译器也不用为每个可能抛出的调用留一条清理路径。依赖异常的库不能这样编。
   - **`-fomit-frame-pointer`**：`-O2` 已经默认打开，省出一个寄存器。代价是 `perf` 按帧指针回溯调用栈时会断，要用 `perf record --call-graph dwarf`（[perf 专题](/zh/posts/low-latency-perf-profiling/) 2.2）。
   - **`-g` 不改生成的代码**：GCC 保证加不加 `-g` 指令一样，线上二进制也可以带着调试信息，或者把调试信息拆出去单独存。
2. **会改结果的，因子计算和实盘必须一致**
   - **`-ffast-math`**：放开结合律、假定没有 NaN 和无穷大，`std::isnan` 可能被优化成 false。
   - **FMA**：`-march` 打开 FMA 以后，`a * b + c` 会被合成一条乘加，中间结果不再单独舍入，末位就变了。
   - **研究侧和实盘对不上时，这几个选项是第一批要查的**（[因子一致性](/zh/ref/factor-consistency/#flags) 第 7 节）。

## 3. 开了优化，默认只用 SSE2：-march 放开新指令，也把程序绑在那一代 CPU 上 {#march}

1. **痛点：不加 `-march`，GCC 只敢用每颗 x86-64 都有的指令**
   - **x86-64 只保证有 SSE2**：向量寄存器只用到 128 位，AVX2、FMA、BMI 这些都不用（[#15](/zh/posts/simd-vectorization-intrinsics/) 第 1 节）。
2. **解决：按部署机器的型号编译**
   - **`-march=native`**：用编译这台机器支持的所有指令。
   - **`-march=icelake-server`、`-march=znver4` 这种写死型号的写法更稳**：编译机和生产机常常不是同一台，`native` 会把编译机的指令带过去。
   - **`-march=x86-64-v3`**：一档“含 AVX2、FMA”的通用基线，同一个二进制要跑在几代机器上时用。
   - **`-mtune` 只改指令排布，不放开新指令**：二进制在哪都能跑，只是按某一代调优。
3. **代价一：放到不支持的 CPU 上，执行到新指令就崩**
   - **表现是 `SIGILL`（illegal instruction）**，而且不在启动时崩，在第一次走到那段代码时崩。
   - **所以部署前对一下生产机的 `/proc/cpuinfo` flags**；必须跨代的，用运行时检测挑实现（[#15](/zh/posts/simd-vectorization-intrinsics/) 3.3）。
4. **代价二：一些较老的 Intel 服务器上，AVX-512 会让核降频**
   - **原因**：重的 512 位指令功耗高，核会把频率降几百 MHz，执行完还要过一段时间（约 1 ms 量级）才升回来，这段时间里后面的标量代码也跟着变慢。
   - **新一点的核（Intel Ice Lake 以后、AMD Zen 4）降得少得多**，但要以自己机器上的实测为准。
   - **做法**：热路径用 AVX2 或标量；AVX-512 留给单独的批处理核。`-mprefer-vector-width=256` 让自动向量化最宽只用 256 位，GCC 对多数 Intel 服务器型号默认就是这样。

## 4. 每个 .cpp 单独编译，跨文件的小函数内联不了：LTO {#lto}

1. **痛点：编译器一次只看一个编译单元**
   - **例子**：`on_tick()` 在 `strategy.cpp` 里，每次都要调 `book.cpp` 里的 `best_bid()`，函数体只有一行。编译 `strategy.cpp` 时只知道签名，只能生成一次 `call`。
   - **少的不只是 `call` 本身**：内联不了，就没法在调用点做常量传播、没法把它算的东西提到循环外面，还得假设它可能改了任何全局变量。
2. **解决一：LTO（link-time optimization，链接时优化）**
   - **做法**：编译和链接都加 `-flto`。编译时 `.o` 里存的是编译器的中间表示，链接时再把整个程序交回编译器，跨文件内联、删掉没人调的函数。
   - **代价**：链接变慢、吃内存。`-flto=auto` 让链接时并行编译。
3. **解决二：热路径上的小函数直接写在头文件里**
   - **这是 HFT 代码库最常见的做法**：小函数在头文件里定义（类内定义或加 `inline`，管的是链接，见 [#13](/zh/posts/type-punning-calls-compiler-hints/#inline) 2.5），每个用到它的编译单元都看得见函数体，不依赖 LTO。
4. **还有一种是按真实运行统计重排：PGO**
   - **做法和交易系统里的坑在 [#7](/zh/posts/branch-prediction-branch-optimization/) 3.3**：训练时下单路径没怎么走，它就被当成冷代码挪进冷区，要用 dummy 执行或 `-fprofile-partial-training`。

## 5. 热路径调到动态库里：多一次间接跳转，还内联不了 {#dynamic-linking}

1. **痛点：调动态库（`.so`）里的函数要经过 PLT**
   - **PLT（procedure linkage table）是一小段跳板**：程序里写的 `call foo`，实际调到跳板，跳板再从 GOT（global offset table，加载时填好地址的表）里读出 `foo` 的真实地址跳过去。每次调用多一次读和一次间接跳转。
   - **库里面互相调也一样**：用 `-fPIC` 编译、符号默认可见时，库里的 `f()` 调同一个库里的 `g()` 也要走 PLT，而且编译器不敢内联 `g()`。原因是别的库（比如 `LD_PRELOAD`）可以在加载时把 `g` 换掉，这叫**符号插入**（semantic interposition）。
2. **解决一：热路径静态链接**
   - **`-static` 或者把热路径的依赖都编成静态库**：调用就是一条直接 `call`，再配合 LTO 跨库内联。超低延迟的交易程序多数这样做。
3. **解决二：非用动态库不可时，收紧符号**
   - **为什么还会用动态库**：策略做成插件，按需加载、单独发布，或者策略代码要对平台保密。
   - **`-fvisibility=hidden`**：默认不导出，只给对外接口标 `__attribute__((visibility("default")))`。不导出的函数库内直接调用，也能内联。
   - **`-fno-semantic-interposition`**：告诉编译器导出的函数也不会被换掉，库内调用可以内联。
   - **`-fno-plt`**：调外部函数时直接从 GOT 读地址再调，省掉跳板那一跳。
4. **解决三：加载和找符号都在启动时做完**
   - **`dlopen` 用 `RTLD_NOW`**：加载时就把所有符号解析完，缺符号当场报错；默认的懒绑定会把第一次调用的解析成本留到热路径上。
   - **`dlsym` 拿到的函数指针存下来**：热路径上直接调这个指针，不再查表。

## 6. 选项和提示都加了，它到底做了没有：看汇编和优化报告 {#inspect}

1. **先看开关，再看报告，最后看汇编**
   - **哪些开关打开了**：`g++ -O2 -Q --help=optimizers`，2.1 的数就是这样数出来的。
   - **向量化做了没有、为什么没做**：`-fopt-info-vec-optimized` 报做了的，`-fopt-info-vec-missed` 报没做的和原因；Clang 用 `-Rpass=loop-vectorize`、`-Rpass-missed=loop-vectorize`。
   - **最后看汇编**：`g++ -O2 -S -masm=intel` 出汇编文件，`objdump -d -C --no-show-raw-insn` 看已经编好的二进制，Compiler Explorer（godbolt.org）适合比较不同编译器和选项。
2. **报告说做了，不等于快了**
   - **例子**：不开 `-ffast-math` 的 `float` 求和，GCC 16 `-O3` 的报告里有 “loop vectorized”，可汇编里全是 `addss`，加法还是一条串行的链（[#15](/zh/posts/simd-vectorization-intrinsics/) 2.1）。
   - **所以最后的判断看汇编，再用 `perf annotate` 看热的是哪几条指令**（[perf 专题](/zh/posts/low-latency-perf-profiling/) 4.5）。
3. **告诉它证明不了的事：提示和内建函数都在前面的文章里**
   - **指针不重叠**：`__restrict`（[#10](/zh/posts/pointer-memory-access/) 第 1 节）。
   - **分支哪边常走**：`[[likely]]`、`__builtin_expect`，改的是代码布局，不是预测器（[#7](/zh/posts/branch-prediction-branch-optimization/) 3.1）。
   - **函数没有副作用**：`__attribute__((const))`、`pure`（[#11](/zh/posts/rvo-pure-functions/)）。
   - **数据快要用到了**：`__builtin_prefetch`（[#14](/zh/posts/prefetch-warmup-double-buffer/)）。
   - **这些提示都是你的承诺，编译器不检查**：说错了就是未定义行为，结果可能悄悄变错。
