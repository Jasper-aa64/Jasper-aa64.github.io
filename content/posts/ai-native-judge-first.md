---
title: "AI-Native Work: Judge First, Then Compare"
date: 2026-10-13
slug: "ai-native-judge-first"
draft: true
description: "Once AI writes most of the code, the plan, the tests and the conclusions tend to go with it, leaving the human to approve and forward. When Jane Street rebuilt its intern curriculum for the AI era, it centered on three things: design, testing and code review. This post turns those three into practices you can start using right away: for each one, write down your own judgment first, then compare it with what the AI produced and log the difference; it ends with how to ask an AI so you come away understanding, not just holding an answer."
summary: "Hand the code to the AI, keep design, testing and review: write half a page of design yourself, own the tests and make each one prove it can fail, and review blind before reading the AI's review. When you ask, ask “help me understand”, not “solve it for me”."
categories: [AI, Workflow]
tags: [ai-native, ai-coding, agent-workflow, design, testing, code-review]
toc: true
---

An agent hands back a report: "Clean checkout, all tests pass, edge cases handled." It reads fine, so you merge. A few days later three things surface: it tested a different commit from the one you merged; the new test also passes on the code before the change, so it tests nothing; and for all the edge cases supposedly handled, not one test touches a reconnect.

None of these is hard to spot, as long as you decided what to look for before reading the report. Once the code goes to the AI, the judgment quietly goes with it: the AI drafts the plan, writes the tests and summarizes the results, and you sit in the middle approving and forwarding.

## 1. Code Got Cheap; Three Things Got Expensive

Jane Street rebuilt its intern curriculum for summer 2026, for a blunt reason: the four-week project interns used to start with is now one prompt and done, so it neither evaluates anyone nor counts as useful work. The new curriculum is built around three things: design, testing and code review ([Signals and Threads, episode 30](https://signalsandthreads.com/learning-goals-and-the-goals-of-learning-teaching-in-the-age-of-ai/)). Spelled out:

- **Intent and design**: turning a fuzzy request into a clear structure: where the boundaries are, who owns which state, how modules are decoupled. The AI can't make these calls out of thin air; give it a clear structure and it fills in the details.
- **Deep testing**: the machine wrote the code, so how do you show it's right? Testing stops being a chore done afterwards and becomes the spec that defines what "correct" means.
- **Review and taste**: you go from author to editor-in-chief, and have to spot smells and hidden concurrency bugs in a lot of code. Taste only comes from good and bad systems you've taken apart yourself.

All three are kept alive only by doing them. Simon Willison describes [AI as amplifying the expertise you already have](https://simonwillison.net/2025/Oct/7/vibe-engineering/); when [Anthropic surveyed its own engineers](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic), some worried about exactly this: lean on AI too much and the deeper skills needed to write and critique code fade, which makes supervising the AI harder. Feelings aren't reliable either: in [METR's 2025 study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/), experienced open-source developers took 19% longer with AI, yet afterwards believed it had made them 20% faster. So the practices in the next three sections follow one pattern: write down your own judgment first, then compare it with what the AI produced, and log the difference. Each takes 5–15 minutes and doesn't hold up delivery.

## 2. Intent and Design: Half a Page, Not a Prompt

### 2.1 Write Half a Page First

When a request lands, don't ask the AI for a plan yet. Write half a page yourself:

1. A one-line goal and a verifiable acceptance test: metric, threshold, correctness conditions.
2. Boundaries: what this module owns and what it doesn't.
3. Who owns state: which thread writes, which reads, who allocates, who frees.
4. Failure semantics: what happens on a startup failure, a disconnect mid-run, bad data (exit codes, counters, logs).
5. At least two options, each with one line on its cost and risk.
6. What failure looks like: how far it can get and still not be done.

Then let the AI pick holes in it, and log the points it found that you missed; in the other direction, find the flaws in any design doc the AI drafts before using it. Jane Street's new curriculum has exactly this kind of exercise: reading design docs, judging what makes one good, and discussing what's wrong with a few bad ones.

Questions like "run alongside the old implementation or replace it", "where does the config live" and "how many more vendors will we add" can't be settled by a prompt; the answers depend on who deploys it and who gets paged, which is exactly the part that's yours to decide. If the AI's draft has already decided them for you, pull those decisions out and make them again yourself.

### 2.2 Ask What Was Said; Write Down What Was Assumed

Another activity in the new curriculum has full-timers role-play stakeholders while the interns talk to them and gather the requirements themselves. At work nobody plays that part for you, but you can always ask the AI one question: what did the requester actually say, and what are we inferring? Each inference either goes back to a person as a question or goes into the design doc as an assumption, rather than quietly becoming a fact. Before asking people, search the repository and the docs.

**You've got it when** the AI finds fewer gaps each time, and more of the final plan's decisions are in your own words.

## 3. Deep Testing: You Own the Tests, It Owns the Code

### 3.1 Invariants First, Implementation Second

Ron Minsky makes the point on the show: testing was always important, but it matters more now, because models run on feedback; without a way to tell right from wrong, they won't get anything beyond simple tasks right in one shot. The new curriculum has a dedicated piece on writing a really good test suite for a database-backed application.

For a new task, write 3–5 invariants and acceptance tests yourself, and let the AI write only the implementation. It may add tests, but deleting or loosening yours needs your OK first and has to be listed separately in its report. When Kent Beck coded with an agent, [his warning signs](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes) included the AI disabling or deleting tests.

For data-pipeline work, these almost always apply:

- N messages of each kind in, N out.
- Within a channel, sequence numbers increase with no duplicates and no gaps; gaps get counted, never silently skipped.
- A format conversion round-trips to the original value, e.g. an integer price converted to decimal and back.
- If there's a second, independent source, reconcile against it.

Then design inputs that break it: outages, reordering, duplicates, bursts, slow consumers.

### 3.2 Every Test Proves It Can Fail

Run each new test against the code before the change, or a deliberately broken implementation; it must fail. If it passes, it can't catch the bug being fixed. Assertions like "the file does not contain X" pass falsely most easily: point one at the wrong file and it's still green. So pair every "does not contain" with a "does contain" on the same file.

### 3.3 Property-Based Tests and Controllable Time

The testing workshop Jane Street runs for early-career engineers teaches two things: property-based testing, and deterministic control of time in tests.

- **Property-based tests**: instead of individual input/output examples, write rules that should hold for every input, such as "decoding what you encoded gives back the original" or "after sorting, the output is ordered and has the same elements". The framework generates lots of random inputs looking for a counterexample, then shrinks any it finds to the smallest one. Fix the random seed and a failure reproduces exactly. Hypothesis for Python and RapidCheck for C++ are tools of this kind.
- **Controllable time**: for timeouts, retries and scheduled jobs, don't use the real clock in tests. Make the clock an injectable interface and advance it by hand in the test, so the result is the same on every run.

External dependencies work the same way: write a fake for each one (a fake SDK, a fake service) that can inject init failures, login failures, disconnects and out-of-order pushes. It's a practice ground, and also test infrastructure the delivery needs anyway.

**You've got it when** every task's acceptance tests include invariants you wrote; on bug-fix tasks your test is red on the old code; and you can write a property-based test for an input with a nested structure, which is the very example Jane Street uses when it writes learning goals.

## 4. Review and Taste: Editor, Not Rubber Stamp

### 4.1 Reviewing Is Harder Than Writing

Aaron Bauer explains on the show why review is hard: when you write code, you build your understanding step by step, and each mistake you catch corrects your mental model; when you review someone else's code, you get the finished result and have to build a model from scratch. It struck him that this is exactly the position AI puts you in when it writes your code. So the new curriculum keeps hammering one message: you own the code the AI generates; review it carefully and get it into good shape, rather than stamping whatever it produced.

### 4.2 Review Blind, Then Check the Key

Jane Street interns traditionally didn't review other people's code. This summer the curriculum added three days of code review training: interns review pre-made features and leave comments, then compare them with a reference answer key, see what they missed and where they disagree, and discuss it as a group. At work nobody hands you an answer key, but the AI's review can serve as one, as long as you finish your own review first.

When the AI hands back a change and a report, don't read its summary yet, and don't pass it to another AI for review yet. Write three lines: what changed, why it's correct, and where it's most likely wrong. Then go sentence by sentence: which test, which conditions and which commit back this claim? Only then read the AI's review, and note what you missed.

Prompts to review with:

- How many records does one message hold, and how many were handled?
- Is every `memcpy` between the same type and the same size?
- For each shared variable: who writes, who reads, on which thread?
- When a `return` signals failure, does the caller find out?
- Can any log line print a password?
- Does every call exist on the target platform (an old OS and compiler)?
- Units and time formats: a time packed into an integer (like `HHMMSSmmm`) can't be subtracted to get a duration.
- Is each counter wide enough, and is dropped data counted?

The list only jogs your memory; conclusions come from the code and the test results. Three questions do most of the work when checking a report: where does the number come from, and only then how big is it; if it says "none", which places were checked; if it says "exact", "thread-safe" or "lossless", which line of code or which test delivers that.

### 4.3 Changes Small Enough to Review

Their first run hit a snag here too: the features handed to interns for review were too big and had too many problems, so the issues they actually wanted noticed got lost; and when people generated more code with AI than they had time to polish, "you own this code" never landed. Working with AI on your own is no different: have it hand back one reviewable change at a time, split big ones into steps, and review each step on its own.

### 4.4 Taste Comes from Doing

- **No-AI days on real work**: on the first day of a new task, don't let the AI write code. Read the materials, write the design, write the tests first and hand-write the key functions yourself. The AI acts only as a coach: it sets questions, keeps its answers hidden, and you compare after handing in. The bulk of the implementation and the regression tests go to the agent afterwards. The first day is when the request is fuzziest and design is worth the most, so practice and delivery are the same work. Some Anthropic engineers do this too: even when they know Claude could nail a problem, now and then they don't ask it, to stay sharp.
- **Let the AI leave a few lines for you**: Aaron tried Claude Code's learning mode (originally an output style, now a plugin): the AI stops partway and leaves a `TODO(human)` for you to fill in. To fill in those lines he first had to understand what it had written so far, and he came away having enjoyed writing it more and understanding the generated code better. It made him doubt that "let the AI write everything, then read it at the end" is the best way to work.

**You've got it when** a rising share of the issues the AI's review finds were already in your blind review, and your "what I missed" list keeps shrinking.

## 5. Ask to Understand, Not to Be Rescued

### 5.1 How You Ask Matters More Than How Much

In [a January 2026 Anthropic experiment](https://www.anthropic.com/research/AI-assistance-coding-skills), 52 engineers learned an unfamiliar async library and took a quiz right after the task. The hand-coding group averaged 67%, the AI group 50%, with the largest gap on debugging questions. Among the AI users, those who asked follow-ups after generating code, asked for code together with explanations, or asked only conceptual questions averaged 65% or more; those who handed the whole task over, gradually slid into handing everything over, or kept having the AI debug for them scored under 40%. The group that kept having the AI debug asked more questions, and still scored low and finished slower.

The samples are small (2–7 people per pattern), the patterns were identified after the fact, and the study itself draws no causal conclusion. But the direction is clear: what matters is not how many questions you ask but whether they say "help me understand" or "solve it for me". Under delivery pressure it's easy to slide into "it errors, fix it".

### 5.2 What to Ask About, What to Hand Off

Ask about whatever you're accountable for when it breaks: design decisions, correctness conventions (units, sequence numbers, reconciliation rules), concurrency (locks, atomics, publication order), the semantics of external interfaces (callback threads, reconnect and replay), whether the tested commit is the one being merged, and anything you send to other people.

Hand off test scaffolding and scripts, log formats, doc formatting, charts and boilerplate. Even then, keep one checkable point: for an encoding conversion, check that the text matches character for character before and after.

### 5.3 Places Where You Always Ask

**When integrating a third-party SDK or service**

- Which thread runs the callbacks? Can you call shutdown from inside one?
- How many records does one message hold?
- Which page of the docs or which line of the header defines each field's units and values? Mark anything without a source as unconfirmed.
- After a reconnect or a replay from the start, will data already written be pushed again?
- Does the runtime library load on the target platform?

**While the code is being written**

- Mostly stay out. Read the key lines in concurrent code and core logic yourself: what does this lock or atomic protect? Why this memory order? Who frees this object, and how long does it live? Does every path that acquires a resource release it?

**When the report comes back** (review blind first; see 4.2)

- What wrong implementation would also pass these tests? If you can name one, add a test.
- What is inferred rather than measured? What isn't covered?

**Before delivery**

- Without reading the AI's summary, write three lines: what changed, why it's correct, when it breaks. Whichever line you can't write is what you don't understand yet.
- For anything sent to others, ask first: do they need this? Does it decide something for them, or ask for something we shouldn't? Say only what's done and how far it's been tested, e.g. "tested against simulated data, not yet connected to the real environment".

### 5.4 Debugging: Guess First, Then Ask

| Solve it for me | Help me understand |
|---|---|
| "It errors, fix it." | "I think it's X because I see Y. Do you agree? What else could it be? How do we check?" |
| Move on once it's fixed | "What's the root cause? Why did the old code do this? Which symptom would tell me next time?" |

## 6. Log the Difference, or It Didn't Happen

Every section above leaves a difference behind: your design vs. the gaps found in it, your blind review vs. what the AI's review found. Only logged differences turn into calibration; otherwise they're gone once the task ends.

Two tables are enough:

- **Design log**: date, task, the points the AI found that I missed, how I'd catch them earlier next time.
- **Blind-review log**: date, subject (a commit or a report), my three lines, what I missed.

Keep them somewhere of your own, not in the team repository: things there get reviewed by others, and personal practice notes don't belong.

You can also measure yourself: log how long each AI-produced change takes from start to merge, and how many rounds of rework it needs. Those two numbers say more about how much the AI helps than "it feels much faster", and they show which kinds of work are worth handing over.
