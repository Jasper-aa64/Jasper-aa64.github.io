---
title: "IELTS：代码结构"
date: 2026-10-30
slug: "ielts-studio-structure"
description: "这个项目从 3 月 C++/Qt 写的求职面试模拟器开始。Qt 面试版有完整的实时语音链路：五个线程、一条到火山引擎实时语音对话服务的 WebSocket，识别、对话、合成都在服务端。5 月的 IELTS 命令行版只复用了其中语音识别那一半，考官的声音和实时对话那一套还没接上。后来产品主线换成 Django 网站。"
weight: 1
toc: true
---
这个项目最早是 3 月用 C++/Qt 写的求职面试模拟器，5 月改成练雅思口语，先做了一个 C++ 命令行版，后来主线换成了 Django 网站。代码在 [GitHub](https://github.com/Jasper-aa64/AI-realtime_speech-for-IELTS-Job_Interview)。

这篇主要讲 C++ 部分，按三个问题讲：谁在什么时候干活，数据长什么样、放在哪，为什么这样切。C++ 部分有三块：

- **Qt 面试版**：完整的实时语音链路，边听边说。
- **IELTS 命令行版**：只复用了实时链路里语音识别那一半。考官的声音、实时对话那一套还没接上，Qt 界面也只有面试模式，没有 IELTS。
- **音频核心**：抽成纯函数，编成 WASM，给网站做录音预处理。

网站部分放在最后一节简单讲，踩过的坑放在[复盘](../ielts-studio-retrospective/)里。

## 1. Qt 面试版：总图

<a href="/images/projects/ielts/cpp.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/cpp.zh.svg" alt="Qt 面试版的线程图：左边 Qt 界面线程和会话线程；中间三个线程，麦克风线程读 16 kHz 音频编帧发出，接收线程用 Boost.Beast 同步读帧、语音包进播放队列、事件交给 HandleEvent，播放线程从队列取 24 kHz 音频写给 PortAudio，队列空时处理回答并把下一句发给服务端去念；右边是火山引擎实时语音对话服务和大模型 HTTP 接口；下面是 8 个状态的状态机。" loading="lazy" decoding="async"></a>

一句话：**识别、对话、合成都在火山引擎的实时语音对话服务里做，客户端只管收发音频和维护状态。** 出题、给回答打分、最后的总结，另走一个大模型的 HTTP 接口（配置里是 qwen3-8b，用 libcurl 调）。

## 2. 谁在什么时候干活

### 2.1 五个线程

| 线程 | 谁起的 | 干什么 |
|---|---|---|
| Qt 界面线程 | Qt | 显示对话和状态；只处理别的线程投递过来的回调 |
| 会话线程 | 界面点开始时起 | 跑 `DialogSession::Start`：连服务、开会话、起下面两个线程 |
| 麦克风线程 | 会话线程 | 循环读麦克风，每块编成一帧发出去 |
| 播放线程 | 会话线程 | 从播放队列取语音写给扬声器；队列空时处理候选人的回答 |
| 接收线程 | `RealtimeClient` | 循环读 WebSocket，解帧，交给回调 |

另外，面试结束时还会起一个分离的线程（`detach`），等总结的语音播完再停掉会话。

### 2.2 一轮问答

1. **面试官说话。** 服务端先发 `TTS_START`，接着语音包一个个到。接收线程把它们放进播放队列，播放线程取出来写给 PortAudio。这期间麦克风线程照常读麦克风，不读的话 PortAudio 的输入缓冲会溢出，但发出去的是静音。
2. **轮到候选人。** 播放队列空了，服务端也发完了 `TTS_END`（在途计数 `tts_cnt` 归零），播放线程把状态切到"空闲"，麦克风开始发真实音频。
3. **候选人说话。** 服务端判断用户开始说话，发 `USER_START_SPEAKING`，状态切到"候选人说话"。识别结果 `ASR_RESULT` 分中间结果和最终结果：中间结果只打日志，最终结果存进 `pending_answer`，状态切到"面试官思考"。
4. **处理回答。** 播放线程在队列空的时候取出 `pending_answer`，调大模型给这道题打分，同时判断要不要追问，然后决定下一句是追问、下一题，还是总结。这一步是同步的 libcurl 调用，要等几秒。
5. **把下一句念出来。** 下一句用 `CHAT_TEXT_QUERY` 发给服务端，前面加一句"直接朗读下面文字："，让对话模型把这句话原样念出来。服务端回 `TTS_START`，回到第 1 步。

所有题问完后，状态切到"结束中"，生成总结并念出来；那个分离的线程等语音播完，再停掉会话。

## 3. 数据长什么样、放在哪

### 3.1 协议帧

和服务端之间是一条 WebSocket，上面跑一套自定义的二进制帧，编解码都在 `Protocol` 里：

| 部分 | 长度 | 内容 |
|---|---|---|
| 头 | 4 字节 | 版本、头长度、消息类型、标志、序列化方式、压缩方式各占 4 位，最后 1 字节保留 |
| 事件号 | 4 字节，大端 | 例如 100 开始会话、200 音频、501 文本查询、350/359 语音开始/结束、450/451/459 用户开始说话/识别结果/停止说话 |
| 会话 ID | 4 字节长度 + 内容 | 建连接的几个事件（1、2、50–52）不带 |
| 负载 | 4 字节长度 + 内容 | JSON 或原始音频，可以 gzip 压缩（zlib） |

服务端发回来的帧分三种：完整响应（带事件和 JSON）、ACK（里面装的是语音）、错误。`protocol_test.cpp` 有 1495 行，是所有测试里最长的，测的就是这套编解码。

### 3.2 音频

- **上行**：16 kHz、单声道、int16，每块 3200 帧，也就是 200 ms。
- **下行**：24 kHz、float32，按包放进 `std::queue<std::vector<float>>`，用一个互斥锁加一个条件变量保护。

### 3.3 状态和面试内容

- **状态**：`InterviewStateMachine` 是单例，当前状态存在 `std::atomic` 里，一共 8 个：连接中、面试官说话、空闲、候选人说话、面试官思考、结束中、完成、错误。状态一变就回调到界面。
- **面试内容**：`InterviewSession` 存题目列表、每道题的回答、分数和反馈。题目有两种来源：一种是用 PoDoFo 把简历 PDF 读成文字，交给大模型出题；另一种是按岗位要求出题。最后汇总成一份报告。

## 4. 为什么这样切

**一个线程只管一个会阻塞的东西。** 读麦克风、读网络、写扬声器，各占一个线程，都用阻塞调用。线程之间只通过一个带条件变量的队列和几个 `atomic` 标志交换数据，逻辑简单，出问题也好查。

**半双工。** 面试官说话时，麦克风发静音，用户开始说话的事件也直接忽略。这是为了防止扬声器的声音被麦克风录进去，让服务端以为用户在说话。代价是不能打断面试官。

**拿端到端对话模型当朗读器。** 说什么由我们自己的大模型决定，再"请"实时对话服务原样念出来。这样一条连接就同时有了识别和合成，不用再单独接一个语音合成服务。

**Pimpl。** `DialogSession`、`RealtimeClient`、`InterviewSession` 都用 Pimpl，头文件里看不到 Boost、PortAudio 这些依赖。Qt 界面只认 `DialogSession` 的几个公开方法。

**界面线程不碰网络。** 会话放在单独的线程里跑。别的线程要更新界面时，用 `QMetaObject::invokeMethod` 加 `Qt::QueuedConnection` 把回调投递回界面线程，界面线程本身从不阻塞。

## 5. IELTS 命令行版：只接了一半

IELTS 版的结构是：`IELTSManager` 按考试模式跑 `Part1Session`、`Part2Session`、`Part3Session`；题库 JSON 读进 `QuestionBank`；`Scorer` 负责打分。它和面试版共用同一个 `RealtimeClient`、同一套协议和音频类，但只用上了其中一部分：

| 部分 | Qt 面试版 | IELTS 命令行版 |
|---|---|---|
| 连接和协议 | `RealtimeClient` + `Protocol` | 复用 |
| 麦克风 | 常驻的麦克风线程 | 每答一题临时打开一次 PortAudio，录完就关 |
| 识别 | 服务端事件驱动状态机 | 只收 `ASR_RESULT`，拿到第一个最终结果、按回车或者超时就停；没连上服务就让人打字 |
| 考官说话 | 文本查询，播放线程把语音播出来 | 题目打印在终端。也发了文本查询，但回调只收识别结果，服务端送回来的语音包被丢掉了，没人播 |
| 追问 | 大模型判断 | P1、P2 用规则（少于 30 个词、没有 because 之类的词）；P3 调 Claude 命令行生成 |
| 打分 | 大模型 HTTP 接口 | 用 `popen` 调 Codex 命令行、OpenAI 接口或 Claude 命令行，都失败就用规则 |
| 界面 | Qt | 终端 |

要拼成完整的实时版，大致是三步：

1. 把 `DialogSession` 里那套和面试内容无关的东西抽出来，做成一个"语音回合"层：常驻的麦克风线程、播放队列、状态机、"直接朗读"的发法。面试和 IELTS 各自只负责回答"下一句说什么"。
2. IELTS 的三个 Part 改成驱动这一层，考官的话由播放线程念出来。
3. Qt 界面加一个 IELTS 模式，复用同一个会话线程和同一套回调。

## 6. 音频核心编成 WASM

`audio_core` 是从 C++ 这边抽出来的一组纯函数：算音量（RMS、峰值）、检测有没有人说话（复用开源的 WebRTC VAD，也就是 libfvad）、裁掉首尾静音、重采样。它不依赖 PortAudio，也不依赖网络。所以它既能编进本地测试（`audio_core_test`），也能用 Emscripten 编成 WASM（`audio_core_wasm.cpp` 是导出层），放到网站里做录音预处理。

## 7. 后来的网站版

5 月中起，产品主线换成了网站：

<a href="/images/projects/ielts/structure.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/structure.zh.svg" alt="网站版总结构：浏览器单页、Django 进程、AI worker 进程，外部是大模型 HTTP 流式接口、本机命令行编码代理、语音合成、语音识别，数据在 SQLite、文件和题库 JSON 里。" loading="lazy" decoding="async"></a>

- **三个进程**：浏览器单页前端、Django（ASGI）、AI worker。
- **追问**：用户在等，所以在请求里做。Django 用 SSE 把大模型的输出逐字推给浏览器，问句一完整就调火山引擎合成考官语音。
- **整节评分**：要一分钟左右，会失败，还要扣费，所以写进任务表 `AITask`，由 worker 认领、调模型、写回报告，浏览器每 2.5 秒查一次。
- **模型调用**：都走同一个 `AIProvider` 接口，后面挂一条降级链：OpenAI 兼容的 HTTP 接口 → 本机 Codex 命令行 → 规则兜底，每个结果都标明是哪条路生成的。
- **实时识别**：是叠加的一条路。浏览器把 16 kHz PCM 通过 WebSocket 传给后端，后端转给火山引擎做识别；这条路坏了，就退回"录完上传"。

## 8. 从哪开始读

1. `src/interview/dialog_session.cpp`：`HandleEvent`、`MicrophoneThreadFunc`、`PlaybackThreadFunc`、`ProcessPendingAnswer` 四个函数，就是一轮问答的全过程。
2. `src/services/realtime_client.cpp` 和 `src/common/protocol.cpp`：连接、收发和帧格式；配着 `tests/protocol_test.cpp` 一起看。
3. `src/services/audio_manager.cpp`：PortAudio 的输入输出流。
4. `src/ui/mainwindow.cpp`：会话线程怎么起，回调怎么回到界面线程。
5. `src/ielts/realtime_speech_capture.cpp` 和 `src/ielts/part1_session.cpp`：IELTS 版复用了哪一半。
6. `src/ielts/audio_core.cpp`：音频核心；WASM 用 `scripts/build_audio_core_wasm.sh` 编出来。
