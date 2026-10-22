---
title: "Slow CRC32C"
weight: 12
signal: "`crc32b/l/q` dominates annotate; a single `_mm_crc32_u64` accumulator, or a byte-by-byte table"
source: "skills/performance-patterns/patterns/fast-crc32c.md"
---

> - **Signal**: `crc32b/l/q` dominates [annotate](/posts/low-latency-perf-profiling/#annotate-scan); there is a single `_mm_crc32_u64` accumulator; or a byte-by-byte table implementation. A function name containing crc32c is worth a look.
> - **Cause**: `_mm_crc32_u64` has a latency of about 3 cycles and handles 8 bytes at a time, so a single accumulator tops out at about 2.5 GB/s per GHz.
> - **Fix**: use corsix fast-crc32's fusion algorithm. The vector path (VPCLMULQDQ) and the scalar crc32 instruction use different execution ports, so two streams run at once; the vector path also uses several independent accumulators.
> - **Three ready-made versions**, picked by CPU at run time:
>   - AVX-512 + VPCLMULQDQ (Ice Lake, AMD Zen 4 and later), 64–97 GB/s;
>   - SSE4.2 + PCLMULQDQ, 15–25 GB/s;
>   - plain C, 1–3 GB/s.
> - **Single-core comparison** (the table in the documentation): on Sapphire Rapids, a naive scalar version does about 23 GB/s, Chromium's AVX-512 version 65 GB/s, fusion 97 GB/s.
> - **New code**: if you need CRC32C, use a ready-made one; don't write your own.
> - **Verify**: an empty buffer with seed 0 gives 0; `crc32c(0, "123456789", 9) == 0xE3069283`.
> - **Mechanism**: a single accumulator's ceiling is set by the instruction's latency, and only several independent chains keep the execution units busy, see [#2 3.5 Turning "Break the Dependency Chain" Into a Formula](/posts/memory-ordering-false-sharing-dependency-chains/#35-turning-break-the-dependency-chain-into-a-formula).
