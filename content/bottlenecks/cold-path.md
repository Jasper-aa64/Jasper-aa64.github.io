---
title: "Unmarked Cold Path"
weight: 8
signal: "A hot function calls functions only on rare branches: error handling, logging, asserts, one-time setup"
source: "skills/performance-patterns/patterns/cold-path-annotation.md"
---

> - **Signal**: a hot function calls functions only on rare branches, such as error and logging functions, asserts, one-time initialization, or calls inside `if (ret < 0)` or a `switch`'s `default`.
> - **What counts as cold**: the branch at the call site is taken less than about 0.1% of the time.
> - **Cause**: cold code sits between hot code in source order and takes up instruction cache; the compiler also cannot lay out the branch as "almost never taken".
> - **Fix**: put `[[gnu::cold]]` on the called function's **definition** (`__attribute__((cold))` for older standards and C); on the declaration alone it does nothing. Error functions called from a cold function must be marked too; it does not propagate.
> - **The caller is what benefits**: the cold function itself is no faster; the hot function's instructions get more compact.
> - **Verify**:
>   - first confirm the branch really is cold: Intel's `branchprob.py` measures each branch's actual taken rate with PMU events; with no workload to run, `gccbranchprob.py` parses GCC's compile-time static estimate (`-fdump-tree-profile_estimate-lineno`);
>   - then check with `-O2 -S` that the cold function has moved after the hot function's `ret`.
> - **Mechanism**: [#7 3.2 Hot/Cold Splitting](/posts/branch-prediction-branch-optimization/#32-hotcold-splitting-move-the-rare-path-out).
