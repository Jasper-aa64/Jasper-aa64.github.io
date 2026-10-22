---
title: "Performance Bottlenecks: Signals, Causes, Fixes"
description: "One card per common performance bottleneck: what perf shows, why it is slow, how to fix it, how to confirm the fix, and a link to the post that explains the mechanism. The last two parts cover the traps to avoid from the start in new code, and letting a program pick its instruction set on each CPU."
date: 2026-10-22
lastmod: 2026-10-22
slug: "bottlenecks"
weight: 30
toc: true
math: true
---

<!-- Card source files live in content/bottlenecks/: <id>.md (English), <id>.zh.md (Chinese); the file name is the id and the anchor below. Parts 1 and 2 are gathered from those files by the bottleneck-lookup and bottleneck-cards shortcodes; posts embed the same card with the bottleneck shortcode and the id. Adding a bottleneck means adding those two files only. -->

Once [perf](/posts/low-latency-perf-profiling/) has found the hot spot, the next step is recognizing which bottleneck it is and how to fix it. This page writes each common bottleneck as a card: the signal is what you see in perf or in the source, the cause is why it is slow, the fix is how to change it, verify is how to confirm the fix, and the mechanism links to the post on this site that explains it.

This material belongs to Intel's open-source performance-patterns ([intel/intel-performance-skills](https://github.com/intel/intel-performance-skills), commit 3e33aec, MIT license). The thresholds and speedups on the cards are the original's numbers and were not re-measured on my own machines; the serial accumulator is the exception, measured in [the perf special, 4.6](/posts/low-latency-perf-profiling/#demo-fix).

## 1. From Signal to Bottleneck: A Lookup Table {#lookup}

When perf shows you something, find its card in this table first. The left column is what you see in perf's output or the source; the right column links to the card.

{{% bottleneck-lookup "What you see" "Bottleneck" %}}

## 2. Bottleneck Cards: Signal, Cause, Fix, Verify {#cards}

Each card's title is the bottleneck's name and its anchor is its English id. Cards are in the order they were added, with new ones at the end; a post that explains a bottleneck's mechanism carries the same card at its end.

{{% bottleneck-cards %}}

## 3. Writing New Code: Avoid These Traps from the Start {#new-code}

When writing new code from scratch, follow this list and the bottlenecks of Part 2 are avoided from the start. Each item links to its card.

- **Pointers**: give non-overlapping pointer parameters `restrict` (C), and read-only inputs `const` ([Missing restrict](#missing-restrict)).
- **Floating-point reductions such as sums**: no single accumulator in a hot loop; state in the function's documentation that a changed summation order shifts the result by a rounding error ([Serial Accumulator](#serial-accumulator)).
- **SIMD**:
  - use the widest registers the target machine supports ([Vectors Too Narrow](#narrow-vector));
  - functions that used ymm or zmm0–15 add `vzeroupper` at their exits ([Missing vzeroupper](#missing-vzeroupper));
  - handle the tail when the length is not a multiple of the vector width;
  - annotate inline assembly with `/* CPUID: <feature> */`, and add `"cc"` to the clobbers when flags change.
- **Several SIMD versions**: when one function has several versions, pick one by CPU at run time (Part 4) rather than hard-coding it with a compile-time `#ifdef`.
- **Multithreading**:
  - pad per-thread data apart at 64-byte alignment ([False Sharing](#false-sharing));
  - one counter per CPU or per thread, no global atomics ([Shared Statistics Counter](#shared-counter));
  - spinlocks read before they CAS ([Test-and-Set Spinlock](#tas-spinlock)).
- **Rare paths**: mark error-handling and rare-path functions `[[gnu::cold]]` ([Unmarked Cold Path](#cold-path)).
- **Don't rewrite what exists**: use a ready-made CRC32C ([Slow CRC32C](#slow-crc32c)); write known algorithms by the table ([Known Algorithms](#known-algorithms)); sort numbers with x86-simd-sort ([std::sort on Numeric Arrays](#std-sort-numeric)).

## 4. Letting a Program Pick Its Instruction Set on Each CPU {#isa-dispatch}

Prepare several versions of one function, say one each for SSE2, AVX2 and AVX-512, and have the program check at run time which instructions the CPU supports and pick the fastest. The same binary then runs on old machines and still uses wide vectors on new ones. There are two ways:

- **Let the compiler generate them (`target_clones`)**: suits ordinary loops the compiler can vectorize by itself. Put the attribute on the function and list the tiers to generate (say AVX-512 and AVX2); the compiler builds several versions and one is picked by CPU when the program loads.
  - the last tier is `"default"` as the fallback; name each tier by feature, since GCC does not accept level names such as `x86-64-v3` in this attribute;
  - the function must not be static and must be `noinline`: if it is inlined everywhere, no dispatch code is generated and the automatic choice silently stops working;
  - it does not upgrade hand-written `_mm256_*` to `_mm512_*`.
- **Write the dispatch yourself (`__builtin_cpu_supports`)**: suits hand-written intrinsics and assembly. When unsure, use this one: the logic is out in the open and can be reviewed.
  - on the first call, check `x86-64-v4`, `v3`, `v2` from high to low and store the chosen version in a static function pointer; every later call costs only one extra indirect jump. Several threads making the first call at once is harmless, because they all write the same value;
  - put an attribute such as `__attribute__((target("avx2,fma")))` on each version's definition: when the whole file is compiled for a lower `-march`, this is what lets the compiler emit the higher tier's instructions for that function.
- **The check must cover every instruction set used**: miss one and the program dies with an illegal instruction on a CPU that passes the check but lacks that feature. Re-check after every widening or rewrite.
- **Other platforms**:
  - Clang supports both ways equally;
  - MSVC checks features with `IsProcessorFeaturePresent()`;
  - ARM/AArch64 checks features with `getauxval(AT_HWCAP)` and has no counterpart to `target_clones`;
  - shared libraries should prefer writing the dispatch themselves, since the compiler-generated kind has initialization-order problems with some linkers.

An example on this site is [#15 3.3](/posts/simd-vectorization-intrinsics/#33-alignment-instruction-set-detection-vzeroupper): `__attribute__((target("avx2,fma")))` turns on AVX2 for one function only, and the CPU is checked once at start-up before that path is taken.
