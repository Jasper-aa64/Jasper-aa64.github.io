---
title: "IELTS: Retrospective"
date: 2026-10-30
slug: "ielts-studio-retrospective"
description: "Seven months and 688 commits: from a C++/Qt interview prototype to an IELTS command line, a website, and a Qt desktop shell around the web app. On the C++ side, the complete real-time pipeline exists only in the March prototype, the IELTS version reused the classes but not the threading model, and the new native_voice stops at the device layer, so the product still has no real-time voice anywhere. On the web side, the slowness was the Codex CLI cold start, audio tearing was misdiagnosed twice, and scoring got stuck because two places decided failure."
weight: 2
toc: true
---
This is the retrospective for [IELTS](../ielts-studio-structure/). What the code looks like now and what is wrong with it is listed in section 5 of the structure post; this post is about how those problems came about and what I would do next time. The conclusions first:

- **Reuse the threading model, not just the classes.** The complete real-time pipeline is only in the March prototype. The IELTS command-line version reused `RealtimeClient` and the audio classes but not the microphone and playback threads or the state machine, so the examiner's audio is sent and never played.
- **Get one simple end-to-end path working before polishing a layer.** The new `native_voice` written in October has a clean device layer and no network, recognition or synthesis, so the product still has no real-time voice anywhere. The old prototype, for all its faults, is the only thing that works end to end.
- **Every shortcut has a cost; write it down.** Half duplex keeps echo out at the cost of interruptions; using the dialogue model as a reader saved a speech-synthesis integration at the cost of having no way to check it reads verbatim.
- **Three from the website**: the slow part was the call path, not the logic; get evidence before fixing a bug; only one place may decide that something has failed.

## 1. Seven months, four shapes

| When | Shape | What happened |
|---|---|---|
| March | C++/Qt desktop prototype | Job-interview simulator: read a CV PDF, LLM-generated questions, Volcengine's real-time dialogue service for the conversation; finished with a pass of cppcheck and ASan |
| Early May | C++ command line | Became the three parts of IELTS speaking, with scoring through Codex, the OpenAI API or Claude |
| Mid May | Single-file Python site | Recording in the browser, reports, a wallet; scoring calibration and an unattended long-run audit |
| Mid to late May | Django | Moved to Django and retired the old server; streamed HTTP follow-ups, WASM audio preprocessing, live recognition |
| June to September | Features and wrap-up | Corpus, Takeaway, spaced spelling review, public-network speed-ups, onboarding, P3 bank progress, deployment docs |
| October | Qt desktop shell | QtWebEngine around the web app; interview mode and an AI assistant; the new `native_voice` device layer; an audit of the old C++ voice code |

By month: 13 commits in March, 406 in May, 143 in June, 25 across July to September and 101 in October. From May on, most code came from the same loop: I wrote a spec, Codex or Claude Code implemented it, and I accepted it or not.

## 2. The March real-time prototype

### 2.1 A Bluetooth headset took 600 ms to read one chunk

Each microphone read is 3200 frames, which at 16 kHz should block for 200 ms. With a Bluetooth headset (OPPO Enco X3), `Pa_ReadStream` blocked for 600 ms, so every pass of the microphone loop waited three times as long to get 200 ms of audio. The input stream had been opened with `framesPerBuffer` also set to 3200, and macOS Core Audio scheduled its callbacks badly with that setting. Setting it to 0 (letting PortAudio choose its internal buffer size) brought it back to 200 ms.

It showed up because the microphone loop always logged how long the read and the send took. **Keep one timing log line in a real-time loop**; when the device changes, the problem is visible at once.

### 2.2 Half duplex: keeps echo out, and turns off interruptions

While the interviewer talks, the microphone sends silence and `USER_START_SPEAKING` is ignored, so the speaker's sound is not picked up as the candidate. The cost is no interruptions. The code still has a "candidate cuts in, clear the playback queue" branch, but since the event is already ignored during playback, that branch never does anything. **To support interruptions, solve echo first** (require headphones, or cancel echo), then let the event through; half on each side does not work.

### 2.3 The dialogue model as a reader

Our own LLM decides what to say and the real-time dialogue service reads it out. The text sent is: "Read the following text out directly: … For the candidate's later answers, reply only '[OK, let's continue]', without picking up or commenting". One connection gives both recognition and synthesis, but it all rests on prompts, and **the client cannot tell whether it read verbatim or added something.** The recognition results include what it actually said, so next time that can be compared with the intended text.

### 2.4 Slow calls on the playback thread

Scoring an answer and generating the summary are blocking libcurl calls of a few seconds, made on the playback thread, because "handle the answer when the queue is empty" lives in the playback loop. Meanwhile audio waits in the queue and Stop waits for the request. **The playback thread should only play.** Answer handling belongs on its own thread, with results tagged by an epoch so that a result for a turn that is already void is simply dropped.

### 2.5 What the audit added

The October audit found several things I had missed reading the code myself: TLS set to `verify_none`; the microphone and playback threads both writing the same WebSocket without a lock; "connected" set as soon as the handshake finished, without waiting for the server to confirm the session; and the `detach`ed wrap-up thread capturing `this` and reading the queue without the lock.

They have one thing in common: **none of them shows up when one person runs it once.** They need a slow network, a quick exit or two sessions back to back. So ASan and TSan should not only run empty-session unit tests but also "start, stop, start again quickly" tests.

### 2.6 cppcheck reported 541 issues; 47 were in my code

Almost all of the report came from third-party headers installed by vcpkg; the 47 in my own code were all style or information level. The ASan commit added 13 lines of configuration and recorded nothing about what it found. **Limit the scan to your own code and write down the conclusion.**

## 3. The IELTS command line: half reused

For each answer the IELTS command-line version opens the microphone afresh and replaces the response callback with one that takes only recognition results. The question is printed in the terminal; the code still sends "read this out", but the audio that comes back is dropped by that callback, so in practice there is no sound.

The problem is not a missing playback function but the level of reuse: **the classes were reused, the threading model and state machine were not.** The hard part of the prototype is knowing when to speak and when to listen, and it all sits in `DialogSession`, written together with the interview content, so it cannot be lifted out.

## 4. October: the desktop shell and native_voice

### 4.1 A shell around the web app does not bring every web capability

Wrapping the web app in QtWebEngine lets one UI serve browser and desktop, which saves work. But it soon turned out that QtWebEngine exposes browser dictation without any speech service behind it, and calling it gets the renderer killed, so it had to be hidden. As a result the desktop transcript has to wait for the upload and backend recognition, one step slower than in an ordinary browser. **Before wrapping, try each browser capability the pages rely on inside the shell.**

### 4.2 A new engine, or change the old prototype

The audit concluded "keep the voice engine in C++, keep the old prototype as a reference and baseline, write the new engine separately", and so came `native_voice`: a callback device layer, preallocated rings, epoch interruption, all neatly done. But it has a single commit, its worker only echoes the microphone, and the slices that do the real work (connecting to the server, continuous recording and interruption, wiring into the desktop shell) have not started.

In hindsight the cost of starting over is that **everything the prototype already had (protocol, recognition, reading out, turn-taking) has to be rewritten, and until it is, the product has no real-time voice at all.** Most of the prototype's problems are local fixes (structure post 5.3); only a few need the structure changed. So the plan for next is the other way round: on the old prototype, fix correctness first, then shrink the buffers and measure, then give the connection a single owning thread (structure post 5.4), then split `DialogSession` and wire it into the desktop shell. If measurement shows blocking I/O is too jittery, bring over `native_voice`'s device layer then.

## 5. The website

### 5.1 Follow-up latency: the Codex CLI cold start

Early on, every follow-up started a `codex exec` subprocess: cold start plus reasoning, over ten seconds. The follow-up logic and prompts were already written, so only how the model was called changed: first an OpenAI-compatible streaming HTTP API (3 out of 3 at acceptance, median about 4.66 s, best 1.46 s), then SSE streaming with Volcengine synthesis starting once the question was complete, measuring about 2.11 s from the end of speech to the first character.

Two caveats: the 4.66 s figure is only 3 samples from a different API than the one used later, never re-measured; and the spec's target of a first character within 1 second was not reached.

### 5.2 Examiner audio tearing: misdiagnosed twice

The first P1 question sounded fine; from the follow-ups on, the voice tore. The first two attempts guessed and changed code, once a playback-state race and once starting at `readyState` 3, and neither helped. The third only added logs, someone spoke into a real microphone until it tore, and the log came back.

The cause: **the front end was playing the raw mp3 from Volcengine TTS**, and the backend's conversion path had never been wired in. The fix moved playback to howler.js, used only the converted source and deleted the old mechanisms. Only the first question did not tear, and it was a fixed recording: the symptom had pointed at the source from the start.

### 5.3 Reports stuck on "Analyzing": two places deciding failure

On 2026-06-19 the worker died with a closed terminal while the watchdog was off; the task stayed `pending` and the page spun. It was fixed three times: a back-end "stuck" check, front-end deadlines, then front-end deadlines set to infinity so the back end would decide. But the back-end check lives only in the history list and report detail, not in the task endpoint the front end polls, so to this day a dead worker leaves the waiting page spinning. **Only one place may decide when something has failed**; changing one side and missing the other is what two deciders lead to.

### 5.4 Inflated scores, and files that kept growing

- **Inflated scores**: the model scored generously, and fluent stock answers easily got 6.5 or 7. Prompts were tightened, then a calibration that does not depend on the model was added after it; without a real pronunciation assessment the pronunciation score stays empty and the overall score is capped. Each rule became a test.
- **Growing files**: the 12 May audit already suggested splitting `app.js` (then 1,149 lines). The back end was split into several Django apps; the front end never was, and `app.js` is now almost 18,000 lines. **Split while features are still being added.**

## 6. Working with Codex and Claude

Every spec had the same parts: why, what counts as done, what is explicitly out of scope, and the red lines.

- **What worked**: saying what not to do; writing the red lines down, such as keys only in environment variables, fallbacks always marked, and nothing from other people's uncommitted work swept in.
- **What did not**: handing it a guessed cause to fix. With the tearing it implemented both guesses faithfully and the problem stayed; for a diagnosis task the first step should be logs only. And it cannot do acceptance that needs a person talking into a microphone. Read-only audits, on the other hand, suit it well; section 2.5 came from one.

## 7. What I would do differently

- Get one simple end-to-end path working before polishing any layer.
- For the C++ real-time pipeline, write a content-independent "voice turn" layer (threads, queue, state machine) and let interview and IELTS fill in only "what is the next line".
- Keep slow calls out of real-time threads, and keep a timing log line in them.
- Concurrency and lifetime tests include "start, stop, start again quickly", run under TSan.
- Before wrapping a web app in a shell, try each browser capability it relies on inside the shell.
- Write down the cost of shortcuts like half duplex and read-it-out, and check what can be checked.
- Keep the failure decision in the back end only, with the front end just displaying it.
- Split a file once it passes one or two thousand lines.
- When a bug looks strange, add logs and get evidence before touching the code.
