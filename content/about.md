---
title: "About"
description: "Jasper: software engineering student, low-latency C++, competitive programming, and research on evaluating agent-generated performance patches."
---

I'm Jasper, a software engineering undergraduate at Anhui Normal University, class of 2027. Most of what I work on comes back to one question: **is this actually faster, and how would you know?**

## Low-latency C++

From April to September 2026 I was a C++ engineering intern at a quantitative trading firm, working on a factor-computation engine and on trading services for TWAP position pushing, bidding strategies and position management. Two pieces of that I still think about:

- A performance-critical module spent about 3.4% of its runtime in the kernel's page-fault and page-zeroing paths. Swapping the allocator through `LD_PRELOAD`, without recompiling, cut median wall-clock time by 4.77% with byte-identical outputs.
- The TWAP push service, for 5,000 instruments × 10 users, reached zero dropped pushes and 1.2 ms p95 once database writes left the hot path, each session got its own push queue, hot-path logging went away and Redis operations were batched.

The [Trading System Notes](/posts/#trading) series is me going back to the foundations under that work — CPU isolation, memory ordering, allocators, lock-free queues, cache and DRAM geometry — and writing each chapter up so it can be understood in one read.

## Research

The internship left me with a habit of A/B tests, stress tests and written rollback decisions, and a question: what happens when the patch was written by an agent? [promotion-gate-audit](https://github.com/Jasper-aa64/promotion-gate-audit) is an acceptance gate for agent-generated C++ optimizations — correctness checks, randomized paired measurements, window-level inference and independent confirmation — with preregistered experiments, null-patch tests and a technical report. On 30 null patches it promoted none, where a naive first-pair rule promoted 13.

## Competitive programming

Silver at the 2025 CCPC Jinan Regional and bronze at the 2025 ICPC Asia Wuhan Regional. The [algorithm notes](/algorithms/) here — combinatorics, number theory, matrix methods — are what I reread before contests.

## Elsewhere

- Code: [github.com/Jasper-aa64](https://github.com/Jasper-aa64)
- CV: <a href="/files/cv.pdf" target="_blank" rel="noopener">preview</a> · <a href="/files/cv.pdf" download>download</a>
