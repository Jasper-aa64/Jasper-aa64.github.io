---
title: "IELTS: Retrospective"
date: 2026-10-30
slug: "ielts-studio-retrospective"
description: "Four months and 587 commits, from a C++/Qt interview simulator to an IELTS command-line version to a website. On the C++ side, the real-time pipeline is complete only in the interview version; the IELTS version reused the classes but not the threading model, so the examiner's audio is sent and never played. Half duplex and using the dialogue model as a reader saved work, at the cost of no interruptions and no check that it reads verbatim. On the web side, the slowness was the Codex CLI cold start, audio tearing was misdiagnosed twice, and scoring got stuck because two places decided failure."
weight: 2
toc: true
---
This is the retrospective for the [IELTS project](../ielts-studio-structure/): C++ first, then the website. The conclusions first:

- **Reuse the threading model, not just the classes.** The real-time pipeline is complete only in the Qt interview version. The IELTS command-line version reused `RealtimeClient` and the audio classes but not the microphone and playback threads or the state machine, and so the examiner's audio is sent and never played.
- **Every shortcut has a cost; write it down.** Half duplex keeps echo out, at the cost of interruptions; using the end-to-end dialogue model as a reader saved a speech-synthesis integration, at the cost of having no way to check that it really reads verbatim.
- **Three from the website**: the slow part was the call path, not the logic; get evidence before fixing a bug; only one place may decide that something has failed.

## 1. Four months, three shapes

| When | Shape | What happened |
|---|---|---|
| March | C++/Qt desktop app | Job-interview simulator: read a CV PDF, LLM-generated questions, Volcengine's real-time dialogue service for the conversation; finished with a pass of cppcheck and ASan |
| Early May | C++ command line | Became the three parts of IELTS speaking, with scoring through Codex, the OpenAI API or Claude |
| Mid May | Single-file Python site | Recording in the browser, reports, a wallet; scoring calibration and an unattended long-run audit |
| Mid to late May | Django | Moved to Django and retired the old server; streamed HTTP follow-ups, WASM audio preprocessing, live recognition |
| June | Features | Corpus, Takeaway, spaced spelling review, public-network speed-ups (compression, caching, thumbnails), onboarding |
| July to September | Wrap-up | P3 bank progress, deployment docs, README |

By month the commits were 13 in March, 406 in May, 143 in June and 25 across July to September. From May on, most code came from the same loop: I wrote a spec, Codex or Claude Code implemented it, and I accepted it or not.

## 2. The Qt interview version

### 2.1 A Bluetooth headset took 600 ms to read one chunk

Each microphone read is 3200 frames, which at 16 kHz should block for 200 ms. With a Bluetooth headset (OPPO Enco X3), `Pa_ReadStream` blocked for 600 ms, so every pass of the microphone loop waited three times as long to get 200 ms of audio. The cause: the input stream was opened with `framesPerBuffer` also set to 3200, and with that setting macOS Core Audio scheduled its callbacks badly. Setting it to 0 (`paFramesPerBufferUnspecified`, letting PortAudio choose its internal buffer size) brought it back to 200 ms.

It showed up because the microphone loop always logged how many milliseconds the read and the send took (the first 10 passes, then every 50th). **Keep one timing log line in a real-time loop**; when the device changes, the problem is visible at once.

### 2.2 Half duplex: keeps echo out, and turns off interruptions

While the interviewer talks, the microphone thread sends silence and `USER_START_SPEAKING` is ignored, so the speaker's sound picked up by the microphone cannot make the server think the candidate is talking.

The cost is that the candidate cannot interrupt. The code still has a "candidate cuts in, clear the playback queue" branch, but that event is already ignored during playback, so the branch only runs when nothing is playing and in practice does nothing. **To support interruptions, solve echo first** (echo cancellation, or require headphones), then let the event through; half on each side does not work.

### 2.3 Using the end-to-end dialogue model as a reader

Our own LLM decides what to say, and the real-time dialogue service reads it out. The text sent is:

> Read the following text out directly: … For the candidate's later answers, reply only "[OK, let's continue]", without picking up or commenting

The session configuration also gives it an interviewer persona and speaking style, such as "read the question word for word, do not shorten or rewrite it". The upside is one connection with both recognition and synthesis; the downside is that it rests entirely on prompts, and **the client has no idea whether it read verbatim or added something of its own.** The recognition results include the text it spoke, so next time that can be compared with the intended text and a mismatch logged.

### 2.4 Slow calls on the playback thread

Scoring an answer (`EvaluateAnswer`) and generating the summary (`GenerateSummary`) are blocking libcurl calls of a few seconds, and they run on the playback thread, because "handle the answer when the queue is empty" lives in the playback loop. During those seconds, any audio the server sends (such as that "OK, let's continue") just waits in the queue. **The playback thread should only play.** Answer handling belongs on its own thread or task queue, with the playback thread just signalling that it is time.

### 2.5 The detached thread at the end captures `this`

Wrapping up after the summary is a `detach`ed thread that captures `this`, polls until the audio is done and then calls `Stop()`. `Stop()` joins only the microphone and playback threads and cannot reach this one. If `DialogSession` is destroyed while it is still waiting, it touches freed memory. The thread should be owned by the session and joined on destruction, or the playback thread should check "summary finished" and stop the session itself.

### 2.6 cppcheck reported 541 issues; 47 were in my code

The March cppcheck report had 541 entries, almost all from third-party headers installed by vcpkg (nlohmann/json, fmt, gtest). Only 47 were in my own code, all style or information level, such as a function that could be static or is unused. The ASan commit added 13 lines to CMake and two tests and recorded nothing about what it found. **Limit the scan to your own code and write down the conclusion**, or a long report is just a file.

## 3. The IELTS command-line version: half reused

The IELTS command-line version shares `RealtimeClient`, `Protocol` and the audio classes with the interview version, but for each answer it opens the microphone afresh, replaces the response callback with one that **takes only recognition results**, and stops at the first final result (or on Enter, or on timeout). The examiner's question is printed in the terminal; the code still sends the read-it-out text query, but the audio the server sends back is dropped by that callback, so in practice there is no sound. Follow-ups are rules for P1 and P2 (under 30 words, no "because" and similar) and generated by the Claude CLI for P3; scoring uses `popen` to the Codex CLI, the OpenAI API or the Claude CLI.

So the problem is not one missing playback function, it is the level of reuse: **the classes were reused, the threading model and state machine were not.** The hard part of the interview version is knowing when to speak and when to listen, and all of it sits in `DialogSession`, written together with the interview content so it cannot be lifted out. To build the full real-time version, first pull that out into a content-independent "voice turn" layer, with interview and IELTS each answering only "what is the next line", then give the Qt UI an IELTS mode. The steps are in [section 5 of the structure post](../ielts-studio-structure/#5-the-ielts-command-line-version-only-half-wired-in).

## 4. After the move to the web

### 4.1 Follow-up latency: the Codex CLI cold start

Early on, every follow-up on the website started a `codex exec` subprocess: a cold start plus reasoning, over ten seconds each time. The follow-up logic and prompts were already written, so this step changed only how the model was called, not what was asked:

1. **Call an OpenAI-compatible streaming HTTP API directly**, with a small, fast model and reasoning off. If it fails, fall back to the Codex CLI, then to a rule-based fallback that is marked as such. At acceptance HTTP succeeded 3 times out of 3, median about 4.66 seconds, best 1.46 seconds; in the same comparison round the Codex CLI failed.
2. **Stream over SSE.** Text is pushed to the browser as it is generated, and Volcengine synthesis starts once the question is complete. From the end of speech to the first character measured about 2.11 seconds.

Two caveats: the 4.66-second figure is only 3 samples from a different API than the one used later, never re-measured; and the spec's target of a first character within 1 second was not reached.

### 4.2 Examiner audio tearing: misdiagnosed twice

The symptom: the examiner's voice on the first P1 question was smooth, but from the follow-ups on it tore, with a stretch missing. The first two attempts guessed and changed code: once a playback-state race (IDs and transaction checks), once starting at `readyState` 3 with too little buffered (wait for 4 instead). Neither helped. The third attempt only added logs: every key media event on the audio element, someone speaking into a real microphone until it tore, and the log brought back.

The cause: **the front end was playing the raw mp3 straight from Volcengine TTS.** The backend already had a conversion path to a format browsers play more reliably, but the front end had never been wired to it. The fix moved playback to howler.js, used only the converted source, and deleted the old mechanisms. The symptom had been pointing the way: only the first question did not tear, and that one was a fixed recording. The problem was the source, not the player.

### 4.3 Reports stuck on "Analyzing": two places deciding failure

On 2026-06-19 the worker process died with a closed terminal while the watchdog was off; the task stayed `pending` and the page spun. It was fixed three times: on 22 June the back end got a "stuck" check (queued over 180 seconds, or running over 900 seconds with no report); on 23 June the front end got deadlines (90 seconds unclaimed, 240 seconds running) and the watchdog came back on; on 29 July the front-end deadlines were set to infinity so the back end would decide.

The trouble is that the stuck check lives only in the history list and report detail, not in the task endpoint the front end polls. So today, when the worker is down, the waiting page still spins and only a refresh shows "not scored". The fix is to put the check into the task endpoint too, keeping the decision in one place, the back end.

### 4.4 Inflated scores: a check after the model that does not depend on it

The model scored generously; fluent stock answers easily got 6.5 or 7. Two layers fixed it: tighter prompts, then a deterministic calibration after the model scores, looking at word count, development, stock phrases and repeated vocabulary, stricter for P2 and P3. Without a real pronunciation assessment the pronunciation score stays empty rather than being guessed from the transcript, and the overall score has a conservative cap. Each rule became a test.

### 4.5 Files that kept growing

At the audit on 2026-05-12, `app.js` was 1,149 lines and the back-end file 3,229, already flagged for splitting. The back end became six Django apps; the front end never got split, and `app.js` is now almost 18,000 lines with a stylesheet over 40,000. **Split while features are still being added**; once things settle it is too late.

## 5. Working with Codex and Claude

From May on, most code came from the same loop: I wrote a spec, Codex or Claude Code implemented it, I accepted it or not. Every spec had the same parts: why, what counts as done, what is explicitly out of scope, and the red lines.

- **What worked**: saying what not to do (the latency work changed only the call path, not the prompts, and left the front end alone); writing the red lines down (keys only in environment variables; fallbacks always marked; nothing from other people's uncommitted work swept in).
- **What did not**: handing it a guessed cause to fix. With the tearing it implemented both guesses faithfully and the problem stayed; for a diagnosis task the first step should be logs and evidence only. And it cannot do any acceptance that needs a person talking into a microphone.

## 6. What I would do differently

- For the C++ real-time pipeline: write a content-independent "voice turn" layer first (threads, queue, state machine), and let interview and IELTS fill in only "what is the next line".
- Keep slow calls out of real-time threads, and keep a timing log line in them.
- Write the cost of shortcuts like half duplex and read-it-out into the code comments and docs, and check what can be checked.
- Keep the failure decision in the back end only, with the front end just displaying it.
- Split a file once it passes one or two thousand lines.
- When a bug looks strange, add logs and get evidence before touching the code.
- For a stable public site, use a Cloudflare named tunnel with a fixed domain, or a real server; a quick tunnel has no uptime guarantee and its address changes on every restart.
