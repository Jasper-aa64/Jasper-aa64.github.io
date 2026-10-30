---
title: "IELTS Speaking Studio: Code Structure"
date: 2026-10-30
slug: "ielts-studio-structure"
description: "A site for practising IELTS speaking and writing: an examiner asks, you answer into the microphone, the AI asks one follow-up based on what you said, and a report with scores and rewrites comes at the end. Three processes: the browser page, Django and an AI worker. The follow-up the user waits for streams inside the request; section scoring, which takes about a minute, can fail and is billed, goes to a task table for the worker."
weight: 1
toc: true
---
This is a site for practising IELTS speaking and writing. The speaking part works like the real test: the examiner reads a question, you answer into the microphone, the examiner asks a follow-up based on your answer, and when the section ends you get a report with scores, per-question feedback and a Band 7 model answer. The writing part has a question bank, daily writing and paragraph-level marking. The code is on [GitHub](https://github.com/Jasper-aa64/AI-realtime_speech-for-IELTS-Job_Interview).

This post walks through the structure with three questions: who does the work and when, what the data looks like and where it lives, and why it is split this way. The problems along the way are in the [retrospective](../ielts-studio-retrospective/).

## 1. The overall picture

<a href="/images/projects/ielts/structure.en.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/structure.en.svg" alt="Overall structure: on the left the browser page records, dictates and plays the examiner's voice; in the middle the Django process handles the start of a session, audio upload, streamed follow-ups, examiner voice synthesis and the other APIs, with the AI worker process below it polling the task table, calling the model and writing reports back; on the right four outside services: an LLM over streaming HTTP, a local command-line coding agent as fallback, speech synthesis and speech recognition; at the bottom the data: SQLite tables, audio files and question-bank JSON." loading="lazy" decoding="async"></a>

The system is three processes:

- **The single-page app in the browser**: records, shows the transcript, plays the examiner's voice, checks scoring progress.
- **The Django process**: every HTTP API, plus an optional WebSocket channel, running on ASGI.
- **The AI worker process**: does one thing, scans the task table and finishes the queued scoring and marking jobs.

There are four kinds of outside service: an LLM (over a streaming HTTP API), a local command-line coding agent (the fallback when HTTP fails), speech synthesis and speech recognition. All data is in one SQLite database; recordings and synthesised audio are files, and the tables store only their paths.

## 2. Who does the work, and when

### 2.1 One turn: the user is waiting, so it runs in the request

<a href="/images/projects/ielts/turn.en.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/turn.en.svg" alt="Top half, one turn: the browser plays the examiner, records and dictates, then uploads the audio and completes the turn when the user stops; Django opens an SSE follow-up stream, the LLM returns tokens and the browser shows them one by one; once the question is complete Django synthesises the voice on a background thread and sends tts_ready, the browser plays it and moves to the next turn. Bottom half, section scoring: the browser asks for a score, Django creates a pending AITask, the worker claims it, calls the model and writes the report, and the browser polls the task every 2.5 seconds until it reaches a final state." loading="lazy" decoding="async"></a>

A turn is the part the user sits and watches. In order:

1. The browser plays the examiner's voice. The first question is a fixed recording; later ones are synthesised on the spot.
2. The user answers. The browser records and, at the same time, gets a transcript from its built-in dictation.
3. When the user stops, the browser uploads the recording and completes the turn. The browser's dictation is the transcript of record; where it got nothing, the backend fills one in from the recording with speech recognition.
4. The browser opens an SSE connection for the follow-up. Django reads the question and the transcript, builds the prompt, asks the LLM for a streamed answer and pushes a `chunk` event for every piece it receives, so the browser shows the text as it arrives.
5. As soon as the backend sees a complete question (a question mark, or the end of generation) it pushes `question_complete` and starts a background thread to synthesise the voice; when the audio is ready it pushes `tts_ready` and the browser plays it.

Text comes before voice so that the examiner appears to "start talking" as soon as possible after the user stops. From the end of speech to the first character of the follow-up measured about 2 seconds.

### 2.2 Section scoring: slow, can fail, billed, so it goes to the worker

When a section ends it has to be scored as a whole, with per-question feedback and Band 7 model answers. That takes about a minute, may fail and need a retry, and is billed. None of that belongs on a request thread, so:

1. The browser asks for a score and Django writes a row into the task table `AITask` with status `pending`, after checking that the wallet has enough balance.
2. The worker scans the table every 1 to 2.5 seconds, takes queued tasks in creation order, claims one by setting it to `running`, calls the model, writes the report back to the attempt, sets the task to `succeeded`, and charges for the usage actually consumed.
3. The browser polls that task every 2.5 seconds and stops at a final state, showing either the report or the reason it failed. On failure the recording is already saved, so the user can re-run the analysis without recording again.

On every scan the worker also takes back tasks that have been `running` for more than 900 seconds: those with retries left go back in the queue, the rest are marked failed and not charged.

### 2.3 Live recognition: an added path, not a replacement

The browser can optionally turn the recording into 16 kHz PCM and send it over a WebSocket, and the backend passes it to a speech-recognition service so text appears while the user speaks. If this path fails, the main flow still records and uploads as before, and the recording is not affected. Django moved from WSGI to ASGI to carry the WebSocket; the acceptance condition for that move was that no existing HTTP API changed behaviour and every existing test still passed.

## 3. What the data looks like and where it lives

| Data | Where | Shape |
|---|---|---|
| One practice session | table `SpeakingAttempt` | which part, the questions drawn, status |
| Each turn | table `SpeakingTurn` | question, recording path, raw transcript, cleaned transcript, who generated the follow-up |
| Report | table `SpeakingReport` | scores, per-question feedback, model answers |
| AI task | table `AITask` | status, attempts so far (at most 3), when it may retry, which worker has it, request and result, fallback reason, linked hold |
| Money | wallet, holds, ledger and a few more tables | balance checked before starting; charged by actual usage on success; not charged on failure or fallback; every movement goes in the ledger |
| Question bank | JSON under `data/ielts/` | speaking split by test season, writing by source, imported into the database |
| Recordings, synthesised audio | files | tables store only the path; examiner audio is cached per sentence, so the same sentence is never synthesised twice |

Two things about `AITask`:

- **One job, one task.** `AITask` has a unique idempotency key, so submitting the same report twice returns the task that already exists.
- **Every result says where it came from.** The result records which path produced it, HTTP, the command-line agent or the rule-based fallback, and a fallback result cannot pass itself off as an AI success.

The rest of the data, the corpus (speaking material the user prepares), the Takeaway (expressions collected during practice) and spelling review words, each has its own table under the user.

## 4. Why it is split this way

**Processes are split by whether the user is waiting.** The user waits for the follow-up, so it streams inside the request; section scoring is slow, can fail and is billed, so it goes to the task table and the worker. If the worker dies, follow-ups still work and scoring just waits in the queue. Task state lives in the database, so refreshing the page or restarting Django loses nothing.

**Every model call goes through one entry point with a fallback chain behind it.** All model calls go through the same `AIProvider` interface, which tries in order: the streaming HTTP API, the local command-line agent, the rule-based fallback. One environment variable chooses the route, from HTTP only to the whole chain. When HTTP is slow or down, nothing else in the code has to change.

**The front end has no build step.** The page is plain JavaScript and Django serves the static files directly, so a change shows up on refresh. The cost is that the main file `app.js` has grown to almost 18,000 lines; the retrospective comes back to this.

**What was left of the C++ became WASM.** The project started as a desktop interview simulator in C++. When it became a site, its audio core was pulled out into pure functions: loudness, voice activity detection (reusing the open-source WebRTC VAD), silence trimming and resampling. That part is compiled to WASM with Emscripten and does recording preprocessing in the browser.

## 5. Where to start reading

1. `backend_django/config/urls.py`: all hundred-odd APIs are listed here; start with the speaking `attempts/...` group.
2. `backend_django/apps/speaking/services.py`: the four functions `start_attempt`, `complete_turn`, `stream_follow_up_sse_events` and `score_attempt` are one whole practice session.
3. `backend_django/apps/ai/`: the task table is in `models.py`, the worker loop in `worker.py`, claiming in `claim_ai_task` in `services.py`, and the call paths and fallback chain in `provider_adapters.py`.
4. `web/static/app.js`: search for `playExaminerTurn`, `startRecording` and `streamFollowUpForCompletedTurn`, the three stages of a turn on the front end.
5. `src/ielts/audio_core.cpp`: the audio core; the WASM build is `scripts/build_audio_core_wasm.sh`.
