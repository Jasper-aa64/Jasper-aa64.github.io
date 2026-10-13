---
title: "AI-Native Work: Judge First, Then Compare"
date: 2026-10-13
slug: "ai-native-judge-first"
description: "Once AI writes most of the code, the plan, the tests and the conclusions tend to go with it, leaving the human to approve and forward. This post collects practices you can start using right away: at five fixed points in every task, spend 5–15 minutes writing down your own judgment first, then compare it with what the AI produced and log the difference; plus how to ask an AI so you come away understanding, not just holding an answer."
summary: "Hand the code to the AI, keep the judgment: write half a page of design yourself, guess the number before the run, own the tests, review blind before reading the AI's review, and keep the first day of a new task AI-free. When you ask, ask “help me understand”, not “solve it for me”."
categories: [AI, Workflow]
tags: [ai-native, ai-coding, agent-workflow, code-review, testing, deliberate-practice]
toc: true
---

An agent hands back a report: "Clean checkout, all tests pass, p99 down 30%." It reads fine, so you merge. A few days later three things surface: it tested a different commit from the one you merged; the new test also passes on the code before the change, so it tests nothing; and the 30% came from a single run.

None of these is hard to spot, as long as you decided what to look for before reading the report. Once the code goes to the AI, the judgment quietly goes with it: the AI drafts the plan, writes the tests and summarizes the results, and you sit in the middle approving and forwarding. The practices below do one thing: at a few fixed points in every task, write down your own judgment first, then compare it with what the AI produced, and log the difference. Each point takes 5–15 minutes and doesn't hold up delivery.

## 1. The Judgment Leaves with the Code

When code gets cheap, three things become scarce: intent and design (where the boundaries are, who owns which state, what happens on failure), defining what "correct" means (tests and acceptance criteria), and finding the problems in code, reports and data. Simon Willison describes it as [AI amplifying the expertise you already have](https://simonwillison.net/2025/Oct/7/vibe-engineering/): automated tests, planning ahead and code review were always what senior engineers do; with agents they simply matter more.

The catch is that all three stay alive only by doing them. When [Anthropic surveyed its own engineers](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic), some worried about exactly this: lean on AI too much and the deeper skills needed to write and critique code fade, which makes supervising the AI harder. They reported using Claude in 59% of their work, yet said they could fully delegate, with no checking at all, only 0–20% of it.

Feelings aren't reliable either. In [METR's 2025 study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/), experienced open-source developers took 19% longer with AI, yet afterwards believed it had made them 20% faster (that was early-2025 tooling). So every practice below ends in a record: the judgment you wrote down first, and where it differed from the AI's result.

## 2. Five Checkpoints

In the order a task runs.

### 2.1 Half a Page, Not a Prompt

When a request lands, don't ask the AI for a plan yet. Write half a page yourself:

1. A one-line goal and a verifiable acceptance test: metric, threshold, correctness conditions.
2. Boundaries: what this module owns and what it doesn't.
3. Who owns state: which thread writes, which reads, who allocates, who frees.
4. Failure semantics: what happens on a startup failure, a disconnect mid-run, bad data (exit codes, counters, logs).
5. At least two options, with costs in numbers: extra copies, locks, system calls, network round trips.
6. What failure looks like: how far it can get and still not be done.

Then let the AI pick holes in it, and log the points it found that you missed. Questions like "run alongside the old implementation or replace it", "where does the config live" and "how many more vendors will we add" can't be settled by a prompt; the answers depend on who deploys it and who gets paged, which is exactly the part that's yours to decide.

**You've got it when** the AI finds fewer gaps each time, and more of the final plan's decisions are in your own words.

### 2.2 Guess the Number Before You See It

Before handing off an optimization or a load test, write three lines:

1. What it saves: a lock, a system call, a network round trip, a cache miss, or an allocation.
2. How much, as arithmetic, e.g. "one fewer round trip per message, so per-message latency drops by one round-trip time".
3. Which metric should move: tail latency or throughput.

Keep the prediction to yourself. Don't put it in the AI's task description, or it may tune thresholds to match. When results come back, run them through three checks before believing them: right direction, right order of magnitude, not below the theoretical floor. If CPU went down but wall-clock time didn't, you saved resources, not latency.

Work that isn't optimization has arithmetic too: compute memory as element count × element size before looking at the process's actual footprint; work out how long a 32-bit counter lasts at the current rate.

**You've got it when** the share of runs where you got the order of magnitude right (within 10×) and got it close (within 2×) both rise month over month.

### 2.3 You Own the Tests, It Owns the Code

For a new task, write 3–5 invariants and acceptance tests yourself, and let the AI write only the implementation. It may add tests, but deleting or loosening yours needs your OK first and has to be listed separately in its report. When Kent Beck coded with an agent, [his warning signs](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes) included the AI disabling or deleting tests.

For data-pipeline work, these almost always apply:

- N messages of each kind in, N out.
- Within a channel, sequence numbers increase with no duplicates and no gaps; gaps get counted, never silently skipped.
- A format conversion round-trips to the original value, e.g. an integer price converted to decimal and back.
- If there's a second, independent source, reconcile against it.

Then design inputs that break it: outages, reordering, duplicates, bursts, slow consumers.

Make every new test prove it can fail first: run it against the code before the change, or a deliberately broken implementation, and it must fail. Assertions like "the file does not contain X" pass falsely most easily: point one at the wrong file and it's still green. So pair every "does not contain" with a "does contain" on the same file.

**You've got it when** every task's acceptance tests include invariants you wrote, and on bug-fix tasks your test is red on the old code.

### 2.4 Review Blind, Then Check the Key

When the AI hands back a change and a report, don't read its summary yet, and don't pass it to another AI for review yet. Write three lines: what changed, why it's correct (or faster), and where it's most likely wrong. Then go sentence by sentence: which test, which conditions and which commit back this claim? Only then read the AI's review, and note what you missed.

Prompts to review with:

- How many records does one message hold, and how many were handled?
- Is every `memcpy` between the same type and the same size?
- For each shared variable: who writes, who reads, on which thread?
- When a `return` signals failure, does the caller find out?
- Can any log line print a password?
- Does every call exist on the target platform (an old OS and compiler)?
- Units and time formats: a time packed into an integer (like `HHMMSSmmm`) can't be subtracted to get a duration.
- Is each counter wide enough, and is dropped data counted?
- For performance changes, add: allocations, locks and system calls on the hot path, memory ordering on atomics, false sharing and layout, branches, object lifetimes.

The list only jogs your memory; conclusions come from the code, the assembly and the measurements. Three questions do most of the work when checking a report: where does the number come from, and only then how big is it; if it says "none", which places were checked; if it says "exact", "thread-safe" or "lossless", which line of code or which test delivers that.

**You've got it when** a rising share of the issues the AI's review finds were already in your blind review, and your "what I missed" list keeps shrinking.

### 2.5 No-AI Days on Real Work, Not Toy Problems

On the first day of a new task, don't let the AI write code: read the materials, write the design, write the tests first and hand-write the key functions yourself. The AI acts only as a coach: it sets questions, keeps its answers hidden, and you compare after handing in. The bulk of the implementation and the regression tests go to the agent afterwards. The first day is when the request is fuzziest and design is worth the most, so practice and delivery are the same work. Some Anthropic engineers do this too: even when they know Claude could nail a problem, now and then they don't ask it, to stay sharp.

Build the practice environment along the way: write a fake for each external dependency (a fake SDK, a fake service) that can inject init failures, login failures, subscription failures and out-of-order pushes. That's a high-fidelity practice ground with traps already laid and instant feedback, and it's also test infrastructure the delivery needs anyway.

When you want to hand-write a piece on an ordinary day, you can also switch on Claude Code's Learning output style for a while: the AI leaves `TODO(human)` markers in the code and you write the key lines.

**You've got it when** three numbers improve each time: after reviewing the materials, how many issues you found and which kinds you missed against the answer key; how many gaps get found in your design; and how often your hand-written functions pass their tests on the first run.

## 3. Ask to Understand, Not to Be Rescued

### 3.1 How You Ask Matters More Than How Much

In [a January 2026 Anthropic experiment](https://www.anthropic.com/research/AI-assistance-coding-skills), 52 engineers learned an unfamiliar async library and took a quiz right after the task. The hand-coding group averaged 67%, the AI group 50%, with the largest gap on debugging questions. Among the AI users, those who asked follow-ups after generating code, asked for code together with explanations, or asked only conceptual questions averaged 65% or more; those who handed the whole task over, gradually slid into handing everything over, or kept having the AI debug for them scored under 40%. The group that kept having the AI debug asked more questions, and still scored low and finished slower.

The samples are small (2–7 people per pattern), the patterns were identified after the fact, and the study itself draws no causal conclusion. But the direction is clear: what matters is not how many questions you ask but whether they say "help me understand" or "solve it for me". Under delivery pressure it's easy to slide into "it errors, fix it".

### 3.2 What to Ask About, What to Hand Off

Ask about whatever you're accountable for when it breaks: hot paths and concurrency (publication protocols, memory ordering, locks), correctness conventions (units, sequence numbers, reconciliation rules), the semantics of external interfaces (callback threads, reconnect and replay), whether the tested commit is the one being merged, and anything you send to other people.

Hand off test scaffolding and scripts, log formats, doc formatting, charts and boilerplate. Even then, keep one checkable point: for an encoding conversion, check that the text matches character for character before and after.

### 3.3 What to Ask at Each Step

**When a request lands**

- Ask the AI: what did the requester actually say, and what are we inferring? What's missing from the materials? Search the repository before asking people, and assume questions you send out get no reply.
- Ask yourself: can the success criterion be written as one verifiable sentence?

**When integrating a third-party SDK or service**

- Which thread runs the callbacks? Can you call shutdown from inside one?
- How many records does one message hold?
- Which page of the docs or which line of the header defines each field's units and values? Mark anything without a source as unconfirmed.
- After a reconnect or a replay from the start, will data already written be pushed again?
- Does the runtime library load on the target platform?

**When planning**

- Give 2–3 options with costs in numbers. If traffic goes up 10×, what breaks first?
- Are there decisions in here that were made for me? Pull out the ones that are mine.
- What does failure look like? How far can it get and still not be done?

**While the code is being written**

- Mostly stay out. Read the key lines on hot paths and in concurrent code yourself: what does this lock or atomic protect? Why this memory order? Who frees this object, and how long does it live? Does every path that acquires a resource release it?

**When the report comes back** (review blind first; see 2.4)

- Which test, which conditions and which commit back this conclusion? Is it the commit being merged? Was it a clean checkout?
- Does the new test pass on the code before the change? If it does, it can't catch the bug being fixed.
- What wrong implementation would also pass these tests? If you can name one, add a test.
- What's the mechanism behind this speedup? Is there another explanation, such as noise, a warm cache, or the compiler deleting the code?
- What is inferred rather than measured? What isn't covered?

**Before delivery**

- Without reading the AI's summary, write three lines: what changed, why it's correct, when it breaks. Whichever line you can't write is what you don't understand yet.
- For anything sent to others, ask first: do they need this? Does it decide something for them, or ask for something we shouldn't? Say only what's done and how far it's been tested, e.g. "tested against simulated data, not yet connected to the real environment".

### 3.4 Debugging: Guess First, Then Ask

| Solve it for me | Help me understand |
|---|---|
| "It errors, fix it." | "I think it's X because I see Y. Do you agree? What else could it be? How do we check?" |
| Move on once it's fixed | "What's the root cause? Why did the old code do this? Which symptom would tell me next time?" |

## 4. Log the Difference, or It Didn't Happen

Every checkpoint above leaves a difference behind: what you predicted vs. what was measured, what your blind review found vs. what the AI's review found, your design vs. the gaps found in it. Only logged differences turn into calibration; otherwise they're gone once the task ends.

Two tables are enough:

- **Prediction log**: date, task, mechanism, arithmetic, metric that should move, measured value, how far off, why.
- **Blind-review log**: date, subject (a commit or a report), my three lines, what I missed.

Keep them somewhere of your own, not in the team repository: things there get reviewed by others, and personal practice notes don't belong. A prediction can't be written after the run, so write it before handing off the work.

Finally, measure yourself too: log how long each AI-produced change takes from start to merge, and how many rounds of rework it needs. Those two numbers say more about how much the AI helps than "it feels much faster", and they show which kinds of work are worth handing over.
