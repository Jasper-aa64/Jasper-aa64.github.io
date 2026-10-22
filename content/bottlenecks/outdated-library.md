---
title: "Outdated System Library"
weight: 11
signal: "In perf report the hot symbol is in a system `.so` and is listed in the version table"
source: "skills/performance-patterns/patterns/library-version-upgrade.md"
---

> - **Signal**: in [perf report](/posts/low-latency-perf-profiling/#report-lines) the hot symbol's DSO (dynamic shared object) is a system `.so`, and the symbol is listed in Intel's version table (`references/library-versions.md`).
> - **Fix**: check the installed version; if it is below the table's minimum, report the gap. No code changes; how to upgrade is the user's call.
> - **Checking the version**: for most libraries, `readlink -f` on the file gives the real file name with the full version; OpenSSL's file name only carries the major version, so use `openssl version`.
> - **What the table holds**: so far only a few OpenSSL AES-GCM and AES-XTS symbols, minimum 3.3, because the AVX-512 implementation got much faster from 3.3 on. A hot non-AVX-512 `aesni_xts_encrypt` on a new CPU means even the AVX-512 version is missing.
> - **New enough and still hot**: the bottleneck is inside the function; go back to perf (the [annotate scan](/posts/low-latency-perf-profiling/#annotate-scan)).
