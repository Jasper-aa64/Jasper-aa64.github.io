---
title: "系统库版本旧"
weight: 11
signal: "perf report 里热符号在系统 `.so` 里，而且在版本表里"
source: "skills/performance-patterns/patterns/library-version-upgrade.md"
---

> - **信号**：[perf report](/zh/posts/low-latency-perf-profiling/#report-lines) 里热符号的 DSO（动态共享对象）是系统 `.so`，而且这个符号在 Intel 的版本表（`references/library-versions.md`）里。
> - **修法**：查装的版本，低于表里的最低版本就报差距。不改代码，怎么升级由用户定。
> - **查版本**：多数库 `readlink -f` 一下真实文件名就有完整版本号；OpenSSL 的文件名只到大版本，用 `openssl version`。
> - **版本表里有什么**：目前只有 OpenSSL 的 AES-GCM、AES-XTS 几个符号，最低 3.3，因为 3.3 起 AVX-512 实现大幅优化。在新 CPU 上看到非 AVX-512 的 `aesni_xts_encrypt` 热，说明连 AVX-512 版本都没有。
> - **版本已经够新还热**：瓶颈在函数内部，回到 perf 接着看（[annotate 扫描](/zh/posts/low-latency-perf-profiling/#annotate-scan)）。
