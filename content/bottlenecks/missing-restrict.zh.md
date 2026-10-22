---
title: "漏 restrict"
num: 4
signal: "循环前有一段指针相减、比较、跳转的重叠检查；同一个循环编出向量和标量两个版本"
source: "skills/performance-patterns/patterns/missing-restrict.md"
---

> - **适用**：只适用于 C。
> - **信号**：循环前有一段指针相减、比较、跳转的重叠检查；同一个循环编出向量和标量两个版本；或者一个没有依赖、没有分支的简单循环完全没向量化。
> - **原因**：编译器不敢假设输出指针和输入不重叠，只能加运行时检查（10–20 条指令，外加两份循环），或者干脆放弃向量化。
> - **修法**：只读输入写成 `const float * restrict`，输出写成 `float * restrict`。C++ 没有标准的 restrict，只有 GCC/Clang 的 `__restrict__`。
> - **坑**：restrict 是对编译器的承诺。调用方真传了重叠指针就是未定义行为，不只是变慢。故意原地处理的参数不能加。
> - **验证**：`gcc -O2 -S` 前后对比，检查段消失。加了以后测试挂了，说明调用方在传重叠指针，要去掉 restrict、改调用方。
> - **原理**：[#10 第 1 节 __restrict](/zh/posts/pointer-memory-access/#1-__restrict向编译器保证两个指针不重叠)：两个指针为什么可能指向同一块内存，见 [1.1](/zh/posts/pointer-memory-access/#11-别名aliasing两个指针可能指向同一块内存)；编译器在运行时自己检查一遍，见 [1.2](/zh/posts/pointer-memory-access/#12--o3编译器自己在运行时检查一遍)。
