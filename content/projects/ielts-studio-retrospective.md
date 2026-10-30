---
title: "IELTS Speaking Studio: Retrospective"
date: 2026-10-30
slug: "ielts-studio-retrospective"
description: "Four months and 587 commits, from a C++ desktop interview simulator to a website. Follow-ups went from over ten seconds to a first character in about 2 seconds by changing how the model is called, not the logic; examiner audio tearing was misdiagnosed twice and found only after adding logs; scoring stuck on “Analyzing” because two places were deciding when a task had failed."
weight: 2
toc: true
---
This is the retrospective for the [IELTS Speaking Studio](../ielts-studio-structure/). The conclusions first:

- **The slow part was the call path, not the logic.** Follow-ups went from over ten seconds to a first character in about 2 seconds without changing a line of what the follow-up asks; what changed was how the model is called.
- **Get evidence before fixing a bug.** Examiner audio tearing was misdiagnosed twice, and both times code was changed to no effect; the third attempt only added logs and changed no logic, and that is what found the cause.
- **Only one place may decide when something has failed.** The scoring page spun forever because a front-end timer and the back-end task status were each making their own call.

## 1. Four months, three shapes

| When | Shape | What happened |
|---|---|---|
| March | C++ desktop app | Job-interview simulator: read a CV PDF, LLM-generated questions, a real-time voice dialogue service for the conversation; finished with a pass of cppcheck and ASan |
| Early May | C++ command line | Became the three parts of IELTS speaking, with scoring that could use different models |
| Mid May | Single-file Python site | Recording in the browser, reports, a wallet; scoring calibration and an unattended long-run audit |
| Mid to late May | Django | Moved to Django and retired the old server; streamed HTTP follow-ups, WASM audio preprocessing, live recognition |
| June | Features | Corpus, Takeaway, spaced spelling review, public-network speed-ups (compression, caching, thumbnails), onboarding |
| July to September | Wrap-up | P3 bank progress, deployment docs, README |

By month the commits were 13 in March, 406 in May, 143 in June and 25 across July to September. Most of the code was written the same way: I wrote a spec, a coding agent implemented it, and I accepted it or not. Section 7 is about that.

## 2. Follow-up latency: the bottleneck was the call path

The experience that matters most in this product is an examiner who follows up on what you just said. A follow-up is a light job, one sentence, but at first every one started a command-line coding agent as a subprocess: a cold start plus reasoning, over ten seconds each time. Waiting that long after you finish speaking does not feel like an examiner.

The first thing was to be clear about where the time went. The follow-up logic and prompts were already written; the slowness was a cold start on every call. So this step changed only how the model was called, not what was asked:

1. **Call a streaming HTTP API directly.** Use a small, fast model with reasoning off. If HTTP fails, fall back to the command-line agent, then to a rule-based fallback that is clearly marked as such. At acceptance, HTTP succeeded 3 times out of 3 with a median of about 4.66 seconds and a best of 1.46 seconds; in the same comparison round the command-line agent failed.
2. **Stream the output.** Before, the model finished the sentence, the voice was synthesised, and text and audio appeared together. Now the text is pushed to the browser as it is generated, and synthesis starts as soon as the question is complete. From the end of speech to the first character measured about 2.11 seconds.

Two caveats. The 4.66-second figure is only 3 samples, from a different API than the one used later, which was never re-measured; it is an order of magnitude, nothing more. And the spec's target was a first character within 1 second, which was not reached.

## 3. Examiner audio tearing: misdiagnosed twice

The symptom: in P1 the examiner's voice for the first question was smooth, but from the follow-ups on it tore, with a stretch missing in the middle.

The first two attempts guessed a cause and changed code straight away:

1. **A race in playback state.** Playback got IDs and transaction checks. No effect.
2. **Starting too early, before enough was buffered.** The audio element started playing with only a little data buffered (`readyState` 3); the guess was that it caught up with the server, which streamed audio while still synthesising it. Playback was changed to wait for the whole clip (`readyState` 4). Still no effect.

The third attempt was different: add logs only, and change no playback logic. Every key media event on the audio element was logged with a timestamp, someone spoke into a real microphone until the tearing happened, and that stretch of log came back.

With the log the cause was clear: **the front end was playing the raw mp3 straight from the speech-synthesis service.** The backend already had a path that converted it into a format browsers play more reliably, but the front end had never been wired to it. Both earlier fixes were to the player; the problem was the source.

The final fix stopped patching the hand-written player. Playback moved to the open-source howler.js, the source became the converted URL only, and the old IDs, transactions and buffer polling were deleted. Playback state was cut down to four: ready, started, ended, failed.

Two lessons:

- **The symptom was already pointing the way.** Only the first question did not tear, and the first question was a fixed recording while the rest were synthesised on the spot. The difference was in the source, not in the player's state.
- **When patches start fighting each other, replace the thing instead of adding another.** By the end the hand-written player had several mechanisms working against each other. Switching to a mature library and deleting the old code cleanly was faster than patching on.

## 4. Reports stuck on "Analyzing": two places deciding one thing

On 2026-06-19 a P1 report stayed on "Analyzing". Django and the tunnel were fine; the task was still `pending` and had never been claimed. The worker process had died when a terminal was closed, and the watchdog that should have restarted it was switched off. Nobody ran the task and the page just spun.

It was fixed three times:

1. **22 June, the back end decides "stuck".** A task queued for more than 180 seconds, or running for more than 900 seconds with no report, counts as stuck. The history list shows it as "not scored" with a button to regenerate.
2. **23 June, the front end gets deadlines.** The front end polled every 2.5 seconds with no deadline. Now it stopped after 90 seconds with nobody claiming the task or 240 seconds running, showed a failure, kept the recording and offered a re-run. The watchdog was switched back on, so a dead worker came back within minutes.
3. **29 July, the front-end deadlines set to infinity.** The back-end state was to decide, and the front end would no longer keep its own time.

The trouble is that after step 3 the back-end "stuck" check lived only in the history list and the report detail, not in the task endpoint the front end polls. So today, when the worker is down, the page that is waiting still spins, and only a refresh shows "not scored". The deployment rule also changed so that the worker and the watchdog do not start automatically, so this case does happen. The fix is to put the stuck check into the task endpoint too and have the front end stop on it, keeping the decision in one place, the back end.

Lessons:

- **Only one place may decide when something has failed.** With one deadline in the front end and another in the back end, changing one side left a gap on the other.
- **Whether a background process is alive cannot depend on someone remembering.** Either something restarts it automatically, or the interface tells the user quickly that it is not there.

## 5. Inflated scores: a check after the model that does not depend on the model

The model scored too generously: fluent-sounding answers full of stock phrases easily got 6.5 or 7. It was clearest in a few patterns common among candidates in China: a P2 answer that is too short, a P3 answer with a single opinion, the same words used over and over.

Two layers:

1. **Tighter prompts.** Score strictly against the four official criteria, with an explicit rule that sounding fluent is not enough for 6.5 or 7.
2. **A deterministic calibration after the model scores.** It looks at word count, whether the answer develops (reasons, examples, comparisons), how many stock phrases there are, how much vocabulary repeats and whether the sentences are too simple, with stricter requirements for P2 and P3.

Also, **do not invent what was not measured.** Without a real pronunciation assessment the pronunciation score stays empty, nothing is guessed from the transcript, and the overall score has a conservative cap so the other three criteria cannot lift it. Each rule became a test, for example "a short, generic P2 cannot score high" and "a normal short P1 answer is not pushed down".

## 6. Files that kept growing

The unattended audit on 2026-05-12 already said it: the front-end `app.js` at 1,149 lines, the stylesheet at 1,593 and the single back-end file at 3,229 were too big and should be split.

The back end was split: after the move to Django it became six apps, and the speaking services were split into synthesis, reports, scoring, corpus and others. The front end never was. Today `app.js` is almost 18,000 lines and the stylesheet over 40,000. In the weeks when features were added fastest, it was always "add it now, split it later", and the later it got the harder it was to split.

**Split early, while features are still being added.** By the time things settle, it is too late to split.

## 7. Working with a coding agent

Most of the code came from the same loop: I wrote a spec, a coding agent implemented it, I accepted it or not. Every spec had the same parts: why we are doing it, what counts as done, what is explicitly out of scope, and the red lines.

What worked:

- **Saying what not to do.** The latency spec, for example, said to change only the call path, not the prompts or the question logic, and not to touch the front end. That kept the change small and the acceptance easy.
- **Writing the red lines down.** Keys only in environment variables, never in code, logs or the repository; fallbacks always marked, never passed off as success; nothing from other uncommitted work in the tree gets swept in.

What did not:

- **Asking it to fix a guessed cause.** With the tearing, the first two times it was given a suspected cause to fix, it did exactly that, and the problem stayed. For a diagnosis task the first step should be logs and evidence only.
- **Acceptance that needs a person.** First-character latency, text appearing while speaking, whether audio tears: all of it needs someone talking into a microphone, and an unattended run can only mark those "not accepted".

## 8. What I would do differently

- Separate "the user is waiting" from "this can queue" on day one, and send slow work to a task table from the start.
- Keep the failure decision in one place, the back end, with the front end only displaying it.
- Split a file once it passes one or two thousand lines, not later.
- When a bug looks strange, add logs and get evidence before touching the code.
- For a stable public site, use a tunnel with a fixed domain or a real server. A temporary tunnel has no uptime guarantee, and its address changes every time it restarts.
