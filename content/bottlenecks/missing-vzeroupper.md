---
title: "Missing vzeroupper"
num: 3
signal: "The first SSE instruction after an AVX function takes a huge number of cycles; the AVX-to-SSE assist event is non-zero"
source: "skills/performance-patterns/patterns/missing-vzeroupper.md"
---

> - **Signal**: `other_assists.avx_to_sse` is non-zero; the first SSE instruction after an AVX function takes a huge number of cycles; a cold start, before any AVX code has run, does not pay it.
> - **Cause**: once ymm or zmm0–15 have been written, the upper halves of the registers are "dirty". The next legacy SSE instruction has to save and restore the whole register state, which costs hundreds of cycles on some microarchitectures. `vzeroupper` clears it in about 1 cycle.
> - **Fix**:
>   - in intrinsics code, add `_mm256_zeroupper()` before every exit that may reach SSE: before return, before calling an SSE function, before a callback;
>   - at the end of inline assembly, add `vzeroupper` and put all of ymm0–15 in the clobber list, because it clears the upper half of every register.
> - **When it is not needed**: only zmm16–31 are used, or only xmm. Functions using `target("avx2")` or `target_clones` get it inserted by the compiler.
> - **Verify**: `other_assists.avx_to_sse` drops to zero. If it does not, search `objdump -d` output for ymm/zmm to find other missed spots.
> - **Mechanism**: [#15 3.3 Alignment, Instruction-Set Detection, vzeroupper](/posts/simd-vectorization-intrinsics/#33-alignment-instruction-set-detection-vzeroupper).
