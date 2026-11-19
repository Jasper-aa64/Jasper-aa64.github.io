---
title: "交易系统笔记 #15：SIMD 向量化与 intrinsics"
date: 2026-10-15
slug: "simd-vectorization-intrinsics"
description: "不指定指令集时 GCC 只用 128 位的 SSE2；-O2 碰到可能重叠的指针就不向量化，-O3 的报告说“向量化了”也不一定真并行；float 求和用 omp simd reduction 只给一个循环放开重排。手写 AVX2 intrinsics 时，竖着算便宜、横着算贵，结果和标量版差在最后几位，还要处理对齐、运行时检测指令集和 vzeroupper。汇编是 GCC 16 的实测。"
summary: "一条指令算一排数，前提是编译器知道能用多宽的寄存器、确定没有重叠、允许重排；这三条做不到时，用 intrinsics 自己写，代价是对齐、指令集检测和结果的最后几位。"
chapter: 1
categories: [Systems]
tags: [cpp, simd, vectorization, avx2, intrinsics, hft, low-latency]
toc: true
light: true
---

向量化（vectorization）是让一条指令同时算一排数：AVX2 的一条 `vaddps` 一次做 8 个 float 加法，标量的 `addss` 一次只做 1 个。它发生在<a href="/maps/hardware-map.zh.html" target="_blank" rel="noopener">硬件地图</a>后端的执行单元里，执行单元能一次处理多宽的数据，取决于用的是哪套指令集。[#9](/zh/posts/loop-optimization/) 讲过循环怎么写才好向量化，[速查 2.4](/zh/ref/cpu-memory/#appetite) 有它带来的吞吐差别。这一篇讲实际会碰到的几件事：编出来到底用了多宽的寄存器，编译器什么时候不肯向量化、数据要怎么摆，自己用 intrinsics 写时要注意什么，几个线程一起算时怎么分活。

## 1. 寄存器有多宽：不指定指令集，就只有 128 位

x86 的向量寄存器随指令集变宽：

| 指令集 | 寄存器 | 宽度 | 一次几个 float | 一次几个 double |
|---|---|---|---|---|
| SSE / SSE2 | XMM | 128 位 | 4 | 2 |
| AVX / AVX2 | YMM | 256 位 | 8 | 4 |
| AVX-512 | ZMM | 512 位 | 16 | 8 |

AVX 把浮点运算扩到了 256 位，AVX2 再把整数运算也扩到 256 位。x86-64 只保证每颗 CPU 都有 SSE2，所以 GCC 不加 `-march` 时只敢用 SSE2：同一个数组相加的循环，`-O3` 编出来是 128 位的 `addps %xmm`，加上 `-mavx2` 才变成 256 位的 `vaddps %ymm`，一次多算一倍。交易用的机器是自己的，可以按它编译：`-march=native` 用上这台机器支持的所有指令，`-march=x86-64-v3` 是包含 AVX2、FMA 的一档。代价是编出来的程序放到不支持的 CPU 上，一执行到这些指令就崩（illegal instruction），3.3 节讲怎么在运行时挑。

## 2. 自动向量化：先确认它真做了

### 2.1 看报告，也看汇编

`-fopt-info-vec-optimized` 让 GCC 报告哪些循环向量化了，`-fopt-info-vec-missed` 报告没向量化的原因。看报告时要知道两件事。

一是 `-O2` 比想象中保守。最简单的数组相加：

```cpp
void add_arrays(float* c, const float* a, const float* b, int n) {
    for (int i = 0; i < n; i++) c[i] = a[i] + b[i];
}
```

GCC 16 `-O2` 实测没有向量化，还是一次一个的 `addss`。原因是 `c` 可能和 `a`、`b` 重叠，要向量化就得先插一段检查重叠的代码，`-O2` 用的代价模型不肯插；`-O3` 会插。三个指针加上 `__restrict` 告诉它不重叠（[#10](/zh/posts/pointer-memory-access/)），`-O2` 就向量化了。

二是报告说“向量化了”，不一定真的并行。没开 `-ffast-math` 的 float 求和，`-O3` 的报告写着向量化了，汇编里却是 4 次 `addss` 依次加进同一个累加器：每次加法还是要等上一次的结果，依赖链一点没变短，只是按顺序一次读进 4 个数。真正的并行，汇编里是 `addps` 或 `vaddps`。

### 2.2 挡住向量化的几种情况

> **本质：编译器只有能证明“一排数同时算”和“一个一个算”结果一样，才会自动向量化**。
>
> - **要知道能用多宽**：不加 `-march`，最多用 128 位（第 1 节）。
> - **要确定没有重叠、没有循环间依赖**：指针加 `__restrict`，`a[i]` 不能依赖 `a[i - 1]`。
> - **浮点归约要允许重排**：开 `-ffast-math`，或者只给这个循环加 `omp simd reduction`。
> - **数据要连续、循环体要简单**：要同时算的数在内存里挨着（2.3），循环里没有调不进去的函数，分支能换成按掩码挑值。

下面是具体挡住的几种情况：

- **可能重叠**：编译器不知道两个指针指的内存重不重叠，要么插检查，要么放弃。用 `__restrict`，或者把参数按值传（[#13 第 2.3 节](/zh/posts/type-punning-calls-compiler-hints/)）。
- **循环之间有依赖**：`a[i]` 要用 `a[i - 1]` 的结果，一排数没法同时算。
- **浮点要重排**：求和这类归约，向量化等于换了加法的顺序，浮点结果会变，默认不允许（[#12 第 3.2 节](/zh/posts/strength-reduction-arithmetic/)）。
- **循环里有调不进去的函数**、访问不连续（要一个个去不同地址取数）、控制流太复杂。

浮点求和不想为此开全局的 `-ffast-math`（它还会把 `std::isnan` 编没），可以只给这一个循环放开重排：

```cpp
float sum_omp(const float* a, int n) {
    float s = 0;
    #pragma omp simd reduction(+:s)
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
```

编译时加 `-fopenmp-simd`，它只打开 OpenMP 里和 SIMD 有关的这几个指令，不引入线程和运行时库。实测 `-O2` 下这个循环编成了 `addps`；不加 `-fopenmp-simd`，这行 pragma 被忽略，还是 `addss`。另一种不改编译选项的办法是手动拆成几个累加器，见[速查 2.4](/zh/ref/cpu-memory/#appetite)。还有一个 `#pragma GCC ivdep`，告诉 GCC 忽略它推测出来的循环间依赖，等于你替这个循环保证没有重叠，保证错了结果就错了。

### 2.3 数据布局：要同时算的数挨着放，一条指令才装得满 {#layout}

> **本质：一条向量 load 只能从一段连续地址读一排数，所以要同时算的那些数必须在内存里挨着，SoA 正好把同一个字段排成一个连续数组**。
>
> - **AoS 里同一个字段中间隔着别的字段**：编译器要么放弃，要么多读几倍的数据，再洗牌把要的那几格挑出来。
> - **SoA 一条 `vmovups` 装 8 个 x**：读、算、写各一条指令，读进来的字节全是有用的。

给每个点的 x 乘一个系数，两种布局：

```cpp
struct P { float x, y, z; };
void scale_aos(P* __restrict p, int n, float k)     { for (int i = 0; i < n; ++i) p[i].x *= k; }
void scale_soa(float* __restrict x, int n, float k) { for (int i = 0; i < n; ++i) x[i] *= k; }
```

GCC 15 `-O3 -march=x86-64-v3` 实测，两个循环的报告都写着“vectorized using 32 byte vectors”，汇编差很多：

- **SoA 每 8 个元素 3 条指令**：`vmovups` 读、`vmulps` 乘、`vmovups` 写回。
- **AoS 每 8 个元素二十多条**：读 3 个 ymm（96 B，里面只有 32 B 是 x），用 `vpermd`、`vblendps` 把 8 个 x 挑进一个寄存器，乘一次，再用 8 条 `vmovss`、`vextractps` 一格一格写回原位。

1. **AoS 改成 SoA 可能更快，原因有三个**
   - **缓存和带宽**：循环只用 x 时，SoA 只把 x 拖进缓存，AoS 连 y、z 一起搬，同样大的缓存装的有用数据只有三分之一（[#6 第 2.1 节](/zh/posts/alignment-layout-cache-dram-geometry/)）。
   - **向量化**：上面的例子，SoA 竖着算，AoS 要洗牌。
   - **硬件预取**：一个字段一个连续数组，是预取器最容易认出来的访问模式。

2. **什么时候 SoA 不快**
   - **每次用一个对象的全部字段**：AoS 一个对象在一条缓存行里，SoA 要碰 3 条行。
   - **按下标随机取单个对象**：同样是 SoA 碰的行多。
   - **折中是 AoSoA**：每 8 个对象一组，组内按字段排，一组正好一个向量宽。

## 3. 手写 intrinsics

### 3.1 什么时候值得

> **本质：先让编译器自动向量化，看报告和汇编确认它做了；它做不到、或者做得不对的热点，才手写 intrinsics**。
>
> - **自动向量化的好处**：代码还是标量写法，换一台机器重新编译，就能用上更宽的寄存器。
> - **手写的代价**：绑死一套指令集，对齐、尾巴、运行时检测都要自己处理，结果的最后几位和标量版不同。
> - **典型的手写场景**：编译器认不出来的并行，比如几个对象各走一遍同一套算式，手动把它们并排放进一条指令；还有要在一排数之内洗牌、要用特殊指令的地方。

intrinsics 是一组 C 函数，一个函数对应一条指令，比如 `_mm256_add_ps` 就是 `vaddps`。类型名写明了宽度和元素：`__m256` 是 8 个 float，`__m256d` 是 4 个 double，`__m256i` 是 256 位整数，头文件是 `<immintrin.h>`，每个函数的含义查 Intel 的 Intrinsics Guide。编译器不肯做、或者做不好的时候才值得手写：你愿意接受重排带来的误差、要在一排数之内交换位置、要用某条特殊指令，或者热路径上要保证就是这几条指令。

### 3.2 例子：AVX2 + FMA 点积

```cpp
__attribute__((target("avx2,fma")))
float dot_avx2(const float* a, const float* b, int n) {   // n 是 8 的倍数
    __m256 acc = _mm256_setzero_ps();
    for (int i = 0; i < n; i += 8)
        acc = _mm256_fmadd_ps(_mm256_loadu_ps(a + i), _mm256_loadu_ps(b + i), acc);
    __m128 s = _mm_add_ps(_mm256_castps256_ps128(acc), _mm256_extractf128_ps(acc, 1));
    s = _mm_add_ps(s, _mm_movehl_ps(s, s));
    s = _mm_add_ss(s, _mm_movehdup_ps(s));
    return _mm_cvtss_f32(s);
}
```

```text
dot_avx2(float const*, float const*, int):
    ...
.L3:
    vmovups      (%rdi,%rax,4), %ymm2
    vfmadd231ps  (%rsi,%rax,4), %ymm2, %ymm0   # 8 个乘加
    addq         $8, %rax
    cmpl         %eax, %edx
    jg           .L3
.L2:
    vextractf128 $0x1, %ymm0, %xmm1            # 下面 6 条：把 8 个部分和加成 1 个
    vaddps       %xmm0, %xmm1, %xmm1
    vmovhlps     %xmm1, %xmm1, %xmm0
    vaddps       %xmm1, %xmm0, %xmm0
    vmovshdup    %xmm0, %xmm1
    vaddss       %xmm1, %xmm0, %xmm0
    vzeroupper
    ret
```

循环里每 8 个元素只有一条 `vfmadd231ps`，8 个乘法和 8 个加法一起做，每一格只和另一个向量的同一格运算，这叫竖着算（vertical），很便宜。最后要把累加器里的 8 个部分和加成一个数，就得在一个寄存器内部挪位置，这叫横着算（horizontal），要好几条洗牌指令，所以只在最后做一次。

结果和标量循环差在最后几位：实测 `dot_avx2` 是 559.515015，按顺序算的标量版是 559.514893。8 个部分和分开累加，等于换了加法的顺序，FMA 还少了一次中间舍入，和 #12 讲的浮点重排是一回事。这个版本只有一个累加器，每次 `vfmadd231ps` 都要等上一次的结果，循环被 FMA 的延迟卡住；拆成 2–4 个累加器，几条 FMA 就能同时在流水线里（[速查 2.4](/zh/ref/cpu-memory/#appetite)）。

### 3.3 对齐、指令集检测、`vzeroupper`

**对齐**。`_mm256_load_ps` 要求地址按 32 字节对齐，不对齐直接崩；`_mm256_loadu_ps` 什么地址都行。在近几年的 CPU 上，数据本来对齐时，`loadu` 和 `load` 一样快，跨了缓存行才多花时间（[#6](/zh/posts/alignment-layout-cache-dram-geometry/)）。所以一般用 `loadu`，再用 `alignas(32)` 把数据对齐。

**运行时选指令集**。上面的函数用 `__attribute__((target("avx2,fma")))` 只给自己开 AVX2，整个程序还是按基线编译；启动时检测一次 CPU，支持才走这条路：

```cpp
float dot(const float* a, const float* b, int n) {
    static const bool has_avx2 = __builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma");
    return has_avx2 ? dot_avx2(a, b, n) : dot_scalar(a, b, n);
}
```

GCC 的 `target_clones` 属性能自动生成几个版本、在程序加载时挑一个，它依赖 Linux 的 ifunc 机制。

**`vzeroupper`**。用过 256 位寄存器之后，如果接着执行老的、不带 VEX 前缀的 SSE 指令，不少 Intel 核要付一次状态切换的代价。编译器会在用过 256 位寄存器的函数末尾插一条 `vzeroupper`，把上半截清零，上面的汇编里就有。自己写汇编、或者调用老的 SSE 库时才需要操心。

### 3.4 NaN 在向量里

向量比较的结果是一个掩码，每一格全 1 或全 0。NaN 和谁比较都是“无序”的，连和自己比也是，所以 `_mm256_cmp_ps(x, x, _CMP_UNORD_Q)` 正好标出哪几格是 NaN，再用 `_mm256_movemask_ps` 收成一个 8 位整数：

```cpp
__attribute__((target("avx2")))
int count_nan8(const float* p) {
    __m256 x = _mm256_loadu_ps(p);
    __m256 m = _mm256_cmp_ps(x, x, _CMP_UNORD_Q);   // NaN 和自己比较是“无序”
    return __builtin_popcount(_mm256_movemask_ps(m));
}
```

实测 8 个数里放 2 个 NaN，返回 2。浮点异常默认是屏蔽的，NaN 不会报错，只会一路传下去：把这 8 个数加起来，实测结果就是 nan。汇总价格这类计算，与其每个元素都判断一次，不如对一批数据算一次掩码，有 NaN 再单独处理。

## 4. 几个线程一起算一个大矩阵：按输出切，每个线程只写自己的行 {#threads}

### 4.1 不让两个线程写同一个元素：输入只读，输出按行分给线程 {#parallel-matrix}

> **本质：数据竞争是两个线程同时访问同一个位置、至少一个在写、中间没有同步；让每个输出元素只有一个线程写、输入大家只读，就没有数据竞争，不用锁也不用原子**。
>
> - **按输出切，不按输入切**：每个线程负责若干行，只写这几行；输入向量所有线程都读，只读不算竞争。
> - **结果在 `join` 之后再读**：`join` 保证线程里的写对调用 `join` 的线程可见。
> - **两个线程的分界别落在同一条缓存行里**：这不是数据竞争，但两个线程写同一条行就是伪共享。

N 个向量两两算相似度，输出是 N×N 的矩阵 `S`：

```cpp
float dot(const float* __restrict a, const float* __restrict b, int d) {
    float s = 0;
    #pragma omp simd reduction(+:s)
    for (int k = 0; k < d; ++k) s += a[k] * b[k];
    return s;
}

// N 个 D 维向量两两算相似度。S 是 N×N、按行存，一行占 ld 个 float
void sim_rows(const float* V, float* S, int N, int D, int ld, int first, int step) {
    for (int i = first; i < N; i += step)            // 这个线程只写第 first、first+step… 行
        for (int j = 0; j < N; ++j)
            S[(size_t)i * ld + j] = dot(V + (size_t)i * D, V + (size_t)j * D, D);
}

const int ld = (N + 15) / 16 * 16;                   // 每行补到 16 个 float（64 B）的倍数
float* S = static_cast<float*>(std::aligned_alloc(64, (size_t)N * ld * sizeof(float)));
std::vector<std::thread> ts;
for (int t = 0; t < T; ++t) ts.emplace_back(sim_rows, V, S, N, D, ld, t, T);
for (auto& th : ts) th.join();                       // join 之后，主线程才读 S
```

- **每个元素只有一个线程写**：第 i 行只归 `i % T` 号线程，没有两个线程写同一个 `S[i][j]`。
- **交错分行，负载才均匀**：对称矩阵只算上三角时，第 i 行要算 N−i 个，按连续块切，前面的线程活多；按 `i % T` 交错分，各线程差不多。`join` 之后再把上三角抄到下三角。
- **交错分行时，每一行的边界都是两个线程的分界**：一行 1000 个 float 是 4000 B，不是 64 B 的倍数，相邻两行会共用一条缓存行。所以把行距 `ld` 补到 16 个 float 的倍数，矩阵按 64 B 对齐，每一行从一条新的缓存行开始（[#2 第 3 节](/zh/posts/memory-ordering-false-sharing-dependency-chains/#false-sharing)）。
- **要往一个共享结果里累加时**（比如求所有相似度的和）：每个线程先加到自己的局部变量里，最后汇总一次，不要每次都原子加同一个变量（[#2 4.3](/zh/posts/memory-ordering-false-sharing-dependency-chains/#case-counter)）。
- **每个线程内部再用 SIMD**：`dot` 里的 `omp simd reduction` 让内层循环向量化（2.2）。实测 N = 1000、D = 64、4 个线程，GCC 15 `-O2 -march=x86-64-v3 -fopenmp-simd` 编出来是 `vmulps`、`vaddps %ymm`，结果和逐个按顺序算的参考值最大差 1.1e-5，差在加法顺序。

## 应用 {#in-practice}

第 1 节的寄存器宽度、第 2 节的自动向量化和 3.3 节的 `vzeroupper`，在实际优化里对应下面两张卡片（{{% bottleneck-ref "narrow-vector" "num" %}}、{{% bottleneck-ref "missing-vzeroupper" "num" %}}）：在 perf 里看到什么、怎么改、怎么验证。

{{% bottleneck "narrow-vector" %}}

{{% bottleneck "missing-vzeroupper" %}}
