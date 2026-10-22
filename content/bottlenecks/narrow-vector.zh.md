---
title: "向量太窄"
num: 2
signal: "热循环是标量浮点；或支持 AVX2 的机器上用 xmm，支持 AVX-512 的机器上用 ymm"
source: "skills/performance-patterns/patterns/simd-upconversion.md"
---

> - **信号**：热循环是标量浮点；或支持 AVX2 的机器上用 xmm；或支持 AVX-512 的机器上用 ymm（[annotate 扫描](/zh/posts/low-latency-perf-profiling/#annotate-scan)第 1、2 条）。
> - **原因**：向量单元每周期发一条指令，跟寄存器宽度无关。宽度每翻一倍，吞吐约翻倍；标量到 zmm 最多快 8 倍。
> - **先排除三种情况**：
>   - 已经卡在内存带宽上的循环，加宽的收益远小于 2 倍。IPC 接近或超过 1、缺失少，才算计算瓶颈。
>   - 有串行累加的，先改多累加器（[串行累加](/zh/ref/bottlenecks/#serial-accumulator)），单靠加宽没用。
>   - ymm 到 zmm 这一步：很多 Intel CPU 跑 zmm 会降频，抵掉一部分甚至全部收益。前后用 turbostat 核持续频率；频率掉得多、负载又不是重计算的，拿 AVX2 版本比一比。
> - **修法**（已有 intrinsics 或汇编时）是一套十步的“拉链”改写：
>   - 复制一份原循环，留作窄宽度的回退；
>   - 原循环展开一次，后半段换用另一组寄存器；
>   - 把后半段的指令逐条挪到前半段对应指令的正下方；
>   - 相邻的两条整数加法合成一条，成对的窄向量操作合成一条宽操作，相邻的乘和加可以融合成 FMA；
>   - 处理循环不变量和累加器，最后改 clobber 列表和 CPUID 注释；
>   - 任何一步做不下去（交换不合法、寄存器合并不了），整个放弃。
> - **尾部**：AVX-512 可以用掩码寄存器做一次带掩码的操作，去掉标量尾巴。
> - **没有手写 intrinsics**、只是编译器只出了 xmm：用 `target_clones` 让编译器出多个版本（见[自动选指令集](/zh/ref/bottlenecks/#isa-dispatch)）。
> - **验证**：
>   - 浮点结果允许差 1 ULP（unit in the last place，末位上的一个单位；重排和 FMA 都改变舍入），逐位比对的参考值要用新代码重新生成；
>   - 整数循环要核有无符号语义；
>   - CPUID 守卫覆盖新用到的指令集；
>   - annotate 里出现宽寄存器。
> - **原理**：寄存器有多宽、不指定指令集为什么只有 128 位，见 [#15 第 1 节](/zh/posts/simd-vectorization-intrinsics/#1-寄存器有多宽不指定指令集就只有-128-位)；挡住向量化的几种情况见 [#15 2.2](/zh/posts/simd-vectorization-intrinsics/#22-挡住向量化的几种情况)。
