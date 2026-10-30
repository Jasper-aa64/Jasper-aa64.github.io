---
title: "IELTS: Code Structure"
date: 2026-10-30
slug: "ielts-studio-structure"
description: "The project started in March as a C++/Qt job-interview simulator. The Qt version has the full real-time voice pipeline: five threads and one WebSocket to Volcengine's real-time dialogue service, with recognition, dialogue and synthesis all on the server. The May IELTS command-line version reuses only the recognition half; the examiner's voice and the real-time dialogue loop are not wired in yet. The product later moved to a Django site."
weight: 1
toc: true
---
The project began in March as a job-interview simulator written in C++/Qt. In May it became an IELTS speaking trainer, first as a C++ command-line program, and later the main line moved to a Django website. The code is on [GitHub](https://github.com/Jasper-aa64/AI-realtime_speech-for-IELTS-Job_Interview).

This post is mostly about the C++ side, walked through with three questions: who does the work and when, what the data looks like and where it lives, and why it is split this way. The C++ side has three parts:

- **The Qt interview version**: the full real-time voice pipeline, listening and speaking as it goes.
- **The IELTS command-line version**: reuses only the recognition half of that pipeline. The examiner's voice and the real-time dialogue loop are not wired in, and the Qt UI only has the interview mode, not IELTS.
- **The audio core**: pulled out into pure functions and compiled to WASM for recording preprocessing on the website.

The website gets a short section at the end; what went wrong is in the [retrospective](../ielts-studio-retrospective/).

## 1. The Qt interview version: overall picture

<a href="/images/projects/ielts/cpp.en.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/cpp.en.svg" alt="Thread diagram of the Qt interview version: on the left the Qt UI thread and the session thread; in the middle three threads: the microphone thread reads 16 kHz audio and sends frames, the receive thread reads frames with Boost.Beast, puts audio in the playback queue and passes events to HandleEvent, and the playback thread writes 24 kHz audio to PortAudio and, when the queue is empty, handles the answer and sends the next line to the server to read out; on the right Volcengine's real-time dialogue service and an LLM over HTTP; at the bottom an eight-state state machine." loading="lazy" decoding="async"></a>

In one sentence: **recognition, dialogue and synthesis all happen in Volcengine's real-time dialogue service; the client only moves audio and keeps state.** Generating questions, scoring answers and writing the final summary go through a separate LLM over HTTP (qwen3-8b in the config, called with libcurl).

## 2. Who does the work, and when

### 2.1 Five threads

| Thread | Started by | Does |
|---|---|---|
| Qt UI thread | Qt | Shows the dialogue and state; only handles callbacks posted from other threads |
| Session thread | the UI, on Start | Runs `DialogSession::Start`: connect, open the session, start the next two threads |
| Microphone thread | session thread | Reads the microphone in a loop and sends each chunk as a frame |
| Playback thread | session thread | Takes audio from the playback queue and writes it to the speaker; handles the candidate's answer when the queue is empty |
| Receive thread | `RealtimeClient` | Reads the WebSocket in a loop, decodes frames, hands them to the callback |

At the end of the interview one more thread is started and `detach`ed; it waits for the summary audio to finish and then stops the session.

### 2.2 One turn

1. **The interviewer talks.** The server sends `TTS_START`, then audio packets arrive. The receive thread puts them in the playback queue and the playback thread writes them to PortAudio. Meanwhile the microphone thread keeps reading the microphone, because otherwise PortAudio's input buffer would overflow, but it sends silence.
2. **The candidate's turn.** The playback queue is empty and the server has sent `TTS_END` (the in-flight count `tts_cnt` is back to zero), so the playback thread switches the state to Idle and the microphone starts sending real audio.
3. **The candidate talks.** The server detects speech and sends `USER_START_SPEAKING`; the state becomes Candidate speaking. Recognition results (`ASR_RESULT`) come as interim and final: interim ones are only logged, the final one goes into `pending_answer`, and the state becomes Interviewer thinking.
4. **Handle the answer.** With the queue empty, the playback thread takes `pending_answer`, asks the LLM to score it and say whether to follow up, then decides whether the next line is a follow-up, the next question or the summary. This is a blocking libcurl call of a few seconds.
5. **Read the next line out.** The next line goes to the server as a `CHAT_TEXT_QUERY` prefixed with "read the following text out directly:", so the dialogue model reads it verbatim. The server answers with `TTS_START` and we are back at step 1.

When every question has been asked, the state becomes Ending and the summary is generated and read out; the detached thread waits for that audio to finish and stops the session.

## 3. What the data looks like and where it lives

### 3.1 Protocol frames

There is one WebSocket to the server, carrying a custom binary framing; encoding and decoding live in `Protocol`:

| Part | Length | Content |
|---|---|---|
| Header | 4 bytes | Version, header size, message type, flags, serialisation and compression take 4 bits each; the last byte is reserved |
| Event | 4 bytes, big-endian | e.g. 100 start session, 200 audio, 501 text query, 350/359 TTS start/end, 450/451/459 user started speaking / ASR result / stopped |
| Session ID | 4-byte length + bytes | Omitted for the connection events (1, 2, 50–52) |
| Payload | 4-byte length + bytes | JSON or raw audio, optionally gzip-compressed (zlib) |

Server frames come in three kinds: full responses (event plus JSON), ACKs (carrying audio) and errors. `protocol_test.cpp` is 1,495 lines, the longest test in the project, and covers exactly this encoding.

### 3.2 Audio

- **Up**: 16 kHz, mono, int16, 3200 frames per chunk, i.e. 200 ms.
- **Down**: 24 kHz float32, in packets placed in a `std::queue<std::vector<float>>` guarded by a mutex and a condition variable.

### 3.3 State and interview content

- **State**: `InterviewStateMachine` is a singleton with the current state in a `std::atomic`, eight states in all: Connecting, Interviewer speaking, Idle, Candidate speaking, Interviewer thinking, Ending, Completed, Error. Every change calls back to the UI.
- **Interview content**: `InterviewSession` keeps the question list and, for each question, the answer, score and feedback. Questions come either from the CV, read from PDF into text with PoDoFo and given to the LLM, or from a job description. At the end everything is summarised into a report.

## 4. Why it is split this way

**One thread per blocking thing.** Reading the microphone, reading the network and writing the speaker each get a thread and use blocking calls. Threads exchange data only through one queue with a condition variable and a few `atomic` flags, so the logic is simple and problems are easy to trace.

**Half duplex.** While the interviewer talks, the microphone sends silence and the user-started-speaking event is ignored, so the speaker's sound picked up by the microphone cannot make the server think the user is talking. The cost is that the user cannot interrupt.

**The end-to-end dialogue model as a reader.** Our own LLM decides what to say, and the real-time dialogue service is asked to read it out verbatim. One connection then provides both recognition and synthesis, with no separate speech-synthesis service to integrate.

**Pimpl.** `DialogSession`, `RealtimeClient` and `InterviewSession` all use Pimpl, so no header shows Boost or PortAudio. The Qt UI knows only the few public methods of `DialogSession`.

**The UI thread never touches the network.** The session runs on its own thread. When another thread needs to update the UI it posts the callback back with `QMetaObject::invokeMethod` and `Qt::QueuedConnection`, so the UI thread never blocks.

## 5. The IELTS command-line version: only half wired in

The IELTS version is laid out like this: `IELTSManager` runs `Part1Session`, `Part2Session` and `Part3Session` according to the exam mode; the question-bank JSON is loaded into `QuestionBank`; `Scorer` does the scoring. It shares `RealtimeClient`, the protocol and the audio classes with the interview version, but uses only part of them:

| Part | Qt interview version | IELTS command-line version |
|---|---|---|
| Connection and protocol | `RealtimeClient` + `Protocol` | reused |
| Microphone | a long-lived microphone thread | opens PortAudio for each answer and closes it afterwards |
| Recognition | state machine driven by server events | takes only `ASR_RESULT` and stops at the first final result, on Enter, or on timeout; without a connection the user types |
| Examiner speaking | text query, audio played by the playback thread | the question is printed in the terminal. A text query is sent as well, but the callback takes only recognition results, so the audio the server sends back is dropped and never played |
| Follow-up | LLM decides | rules for P1 and P2 (under 30 words, no "because" and similar); P3 generated by the Claude CLI |
| Scoring | LLM over HTTP | `popen` to the Codex CLI, the OpenAI API or the Claude CLI, falling back to rules |
| UI | Qt | terminal |

Turning it into the full real-time version takes roughly three steps:

1. Pull the content-independent part of `DialogSession` out into a "voice turn" layer: the long-lived microphone thread, the playback queue, the state machine and the read-it-out query. Interview and IELTS then only answer "what is the next line".
2. Make the three IELTS parts drive this layer, so the examiner's lines are read out by the playback thread.
3. Add an IELTS mode to the Qt UI, reusing the same session thread and callbacks.

## 6. The audio core as WASM

`audio_core` is a set of pure functions pulled out of the C++ side: loudness (RMS, peak), voice activity detection (reusing the open-source WebRTC VAD, i.e. libfvad), trimming silence at the ends, and resampling. It depends on neither PortAudio nor the network, so it builds into a native test (`audio_core_test`) and, with Emscripten, into WASM (`audio_core_wasm.cpp` is the export layer) for recording preprocessing on the website.

## 7. The website that came later

From mid-May the main line of the product became a website:

<a href="/images/projects/ielts/structure.en.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/structure.en.svg" alt="Website structure: the browser single-page app, the Django process and the AI worker process; outside, an LLM over streaming HTTP, a local command-line coding agent, speech synthesis and speech recognition; data in SQLite, files and question-bank JSON." loading="lazy" decoding="async"></a>

- **Three processes**: the single-page front end in the browser, Django (ASGI) and an AI worker.
- **Follow-ups** run in the request, because the user is waiting: Django streams the LLM's output to the browser over SSE, and once the question is complete it asks Volcengine to synthesise the examiner's voice.
- **Section scoring** takes about a minute, can fail and is billed, so it is written to the `AITask` table; the worker claims it, calls the model and writes the report back, and the browser polls every 2.5 seconds.
- **Model calls** all go through one `AIProvider` interface with a fallback chain: an OpenAI-compatible HTTP API → the local Codex CLI → rule-based fallback, and every result records which path produced it.
- **Live recognition** is an added path: the browser streams 16 kHz PCM over a WebSocket and the backend passes it to Volcengine; if it breaks, the flow falls back to record-then-upload.

## 8. Where to start reading

1. `src/interview/dialog_session.cpp`: the four functions `HandleEvent`, `MicrophoneThreadFunc`, `PlaybackThreadFunc` and `ProcessPendingAnswer` are one whole turn.
2. `src/services/realtime_client.cpp` and `src/common/protocol.cpp`: connection, send/receive and the frame format; read them alongside `tests/protocol_test.cpp`.
3. `src/services/audio_manager.cpp`: the PortAudio input and output streams.
4. `src/ui/mainwindow.cpp`: how the session thread is started and how callbacks get back to the UI thread.
5. `src/ielts/realtime_speech_capture.cpp` and `src/ielts/part1_session.cpp`: which half the IELTS version reuses.
6. `src/ielts/audio_core.cpp`: the audio core; the WASM build is `scripts/build_audio_core_wasm.sh`.
