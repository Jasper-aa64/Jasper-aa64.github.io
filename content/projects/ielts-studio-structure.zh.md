---
title: "IELTS：代码结构"
date: 2026-10-30
slug: "ielts-studio-structure"
description: "IELTS 现在由三部分组成：Qt 桌面壳套着网页前端，Django 后端加 AI worker，以及桌面壳里的 C++ 实时语音引擎。面试的追问压力模式用引擎念题、收听，其余练习用它出实时字幕；3 月的旧原型和 native_voice 仍没接进产品。最后一节列出现在的问题。"
weight: 1
toc: true
---
IELTS 是我做的雅思口语和写作练习工具，最近加了模拟面试。代码在 [GitHub](https://github.com/Jasper-aa64/AI-realtime_speech-for-IELTS-Job_Interview)，最新的是 `desktop-realtime-voice` 分支。这篇以现在的代码为基线，按三个问题讲：谁在什么时候干活，数据长什么样、放在哪，为什么这样切。第 5 节专门列现在的问题，踩坑的经过放在[复盘](../ielts-studio-retrospective/)里。

## 1. 总图

<a href="/images/projects/ielts/overview.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/overview.zh.svg" alt="现在的总图：左边是 Qt 桌面壳，里面从上到下是网页前端、QWebChannel 桥（studioNative 报能力，studioVoice 只传控制和文字）、C++ 实时语音引擎 voice_engine；引擎通过 TLS WebSocket 直连右边外部服务里的火山实时语音对话；中间是 Django 和 AI worker；外部服务还有大模型 HTTP、Codex 命令行、火山 TTS、火山 ASR；下面红框是还没接进产品的 C++：旧实时原型、IELTS 命令行、native_voice。" loading="lazy" decoding="async"></a>

现在的 IELTS 由三部分组成：

- **Qt 桌面壳套网页**：`desktop/` 是一个 QtWebEngine 程序，窗口里加载的就是 `web/static` 的网页前端。同一套网页，在浏览器里也能直接用。
- **Django 后端加 AI worker**：口语、写作、面试、AI 调用、计费都在这里。
- **C++ 实时语音引擎**：静态库 `voice_engine`（`VoiceSession`、`RealtimeClient`、PortAudio），10 月 31 日接进了桌面壳。3 月的旧实时原型、IELTS 命令行版、10 月新写的 `native_voice` 仍然没有接进产品。另有 `audio_core` 编成 WASM，在网页里做录音预处理。

所以浏览器和桌面版里的语音走的路不一样：

- **浏览器里**：录音上传给后端，后端再调火山引擎。
- **桌面版面试的追问压力模式**：C++ 引擎直接和火山的实时语音对话服务通话，负责念题、收听、出转写。
- **桌面版的其余练习**：照旧录音，引擎同时出实时字幕，当作这一题的文字稿。

## 2. 谁在什么时候干活

### 2.1 桌面壳

- 用 QtWebEngine 加载后端的网页，后端地址在设置里改，默认是本机的 `127.0.0.1:8767`。
- 只开一个窗口，网页里的 `window.open` 都重定向回这个窗口；后端连不上时显示一个本地出错页；退出后登录状态还在；菜单是中文。
- 网页和 Qt 之间有两个 QWebChannel 对象：
  - `studioNative.capabilities()` 报能力：是不是桌面版、能不能用面试模式、`native_audio`。`native_audio` 要三条都满足才是 `true`：引擎能初始化（PortAudio 有输入和输出设备）、本机配置里有火山凭据、麦克风已授权。
  - `studioVoice` 控制实时语音，见 2.5。
- 火山凭据放在本机的 `~/.ielts-studio/realtime_voice.json`，不进仓库，也不经过网页。
- QtWebEngine 虽然暴露了浏览器听写（Web Speech API），但里面没有语音服务，一调用渲染进程就会被杀掉，所以桌面壳启动时用脚本把它藏了起来。

### 2.2 IELTS 一轮问答：用户在等，所以在请求里做

1. 网页播考官语音（howler.js）。第一题是固定的录音，后面的题由后端调火山 TTS 现场合成。
2. 用户回答，网页用 MediaRecorder 录音。转写的来源分两种：
   - 普通浏览器：用浏览器听写同时出一份转写；
   - 桌面版：听写被藏起来了，改由实时引擎在录音期间出字幕，交卷时这段字幕就是这一题的文字稿（来源记作 `desktop_realtime_captions`）。
3. 停说后，网页上传录音，再提交这一轮。没有转写的，后端调火山 ASR，用整段录音补一份。
4. 网页开一个 SSE 连接要追问。Django 读这一轮的题目和转写，拼成提示词，向大模型要流式结果，逐字推给网页。
5. 一看到完整问句，后端就开一个线程合成语音，合成好了推 `tts_ready`，网页拿到地址就播。

### 2.3 整节评分：慢、会失败、要计费，所以交给 worker

网页提交评分后，Django 在任务表 `AITask` 里写一行，状态是 `pending`。worker 每 1 到 2.5 秒扫一次表，认领后调模型、写回报告、按实际用量扣费。网页每 2.5 秒查一次这条任务，到了终态就停。运行超过 900 秒的任务会被 worker 收回，重新排队或者标成失败。

### 2.4 面试模式：桌面版专有，追问压力是实时语音

后端的 `apps/interview` 负责面试：内置题库，也可以用简历和岗位描述（JD）让大模型出题；然后开会话，一题一题回答，最后出报告。两种模式：

- **标准模式**：不追问，回答完直接进下一道预定的题，不调大模型做决定。回答方式是录音上传，桌面版里引擎同时出字幕当文字稿。
- **追问压力模式**：每答完一题都要等面试官（大模型）决定追问还是换题。没有评分表，也不限追问次数，只设了一个安全上限。在桌面版里，这个模式走实时语音：引擎念题、收听，最终转写自动提交，走原来的文字回答接口（来源记作 `desktop_realtime_asr`，不上传音频）。出错、断线或超时，这一题退回录音流程，下一题再试实时语音。

面试的 AI 调用也记在 `AITask` 里，但创建任务时就直接认领、当场执行，不经过 worker。面试里的"AI 助手"调的是本机的 Codex 命令行。

### 2.5 桌面壳里的实时语音引擎

`voice_engine` 是一个 C++ 静态库（`cmake/voice_engine.cmake`），不依赖 Qt 和 Django，也不含题目内容。核心是 `VoiceSession`，只会两件事：念一段指定的文字；听一段话、给出转写。说什么、转写拿去做什么，由网页和 Django 决定，所以面试和 IELTS 共用同一个引擎。

一个会话里有五个线程：

| 线程 | 干什么 |
|---|---|
| Qt 界面线程 | `VoiceBridge` 接网页的调用，转给引擎；引擎的事件先排到这个线程上，再作为信号发给网页 |
| 控制线程 | 按顺序处理命令和服务端消息；状态机只在这里改，对外回调也只在这里调，调用时不持有任何锁 |
| 采集线程 | 每 20 ms 从 PortAudio 读一包（320 帧，640 字节），只在收听时上传 |
| 播放线程 | 从有上限的队列里取 40 ms 一块写扬声器；队列超过 60 秒就丢最旧的块 |
| I/O 线程 | `RealtimeClient` 独占这条连接（见 5.4）；它的回调只把消息放进控制线程的队列 |

所有线程都由 `Stop()` 收回（join），没有一个是分离线程（detach）的；`Stop()` 总共最多等 4 秒。

追问压力模式下的一题是这样走的：

1. **念题**：网页从 Django 拿到题目，调 `speak`。引擎让服务端念这段指定的文字，用的是正规的指定文本接口：
   - 上一次念完之后收到过"识别结束"（ASR_ENDED，表示用户说过一段话），就用 ChatTTSText（500），因为它只能在识别结束之后发；
   - 否则用 SayHello（300）。

   播放线程只播这段指定文字的语音，模型自己生成的回复只记日志、不播。
2. **收听**：念完后，网页调 `startListening`，采集线程开始上传麦克风。AI 说话时麦克风不上传（StartSession 里 `input_mod = keep_alive`），所以仍然是半双工。
3. **转写**：服务端的中间结果和最终结果经桥推给网页，实时显示。用户停顿超过判停窗口（`end_smooth_window_ms`，默认配置是 2000 ms），服务端就判定说完了。网页拿到最终转写后停 0.6 秒，自动提交。
4. **下一句**：Django 决定追问还是换题，然后回到第 1 步。

其余练习只用引擎的"听"：录音照旧，引擎同时出字幕；服务端判定停顿后，引擎自动接着听；交卷时，累积的字幕就是这一题的文字稿。

引擎会把计时写成 JSON 行日志，"用户停下"的时刻按麦克风的音量算：

- 打开麦克风后的前 1 秒取底噪；
- 一包比底噪高出 20 dB 算有声；
- 连续 3 包（60 ms）有声才算一段语音，键盘声、扬声器开关的爆音不算。

`tools/voice_probe` 可以不开界面，直接驱动一个会话连真实服务。它能把准备好的回答按数字方式混进真实的麦克风信号里，房间里不出声，而回答在哪一刻结束是已知的，可以拿来校准计时。

### 2.6 3 月的旧实时原型：完整，但没在产品里跑

<a href="/images/projects/ielts/cpp.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/cpp.zh.svg" alt="3 月实时原型的线程图：Qt 界面线程和会话线程；麦克风线程读 16 kHz 音频编帧发出；接收线程用 Boost.Beast 同步读帧，语音包进播放队列，事件交给 HandleEvent；播放线程把 24 kHz 音频写给 PortAudio，队列空时处理回答并把下一句发给服务端去念；右边是火山引擎实时语音对话服务和大模型 HTTP 接口；下面是 8 个状态的状态机。" loading="lazy" decoding="async"></a>

`src/interview/` 下的这套代码，是 3 月写的第一条原生实时链路。识别、对话、合成都在火山引擎的实时语音对话服务里做，客户端负责收发音频和维护状态。当时的界面是 Qt Widgets，现在已经不用了，但代码还能编译、还能跑。

上图是 3 月时的样子。它的连接层 `RealtimeClient` 后来按 5.4 改成了一个 I/O 线程独占连接，和新引擎共用；图里的接收线程现在就是那个 I/O 线程。其余部分没改，一共五个线程：

| 线程 | 干什么 |
|---|---|
| Qt 界面线程 | 显示对话和状态，只处理别的线程投递过来的回调 |
| 会话线程 | 跑 `DialogSession::Start`：连服务、开会话、起麦克风线程和播放线程 |
| 麦克风线程 | 用阻塞方式读 PortAudio，编成帧发出去；面试官说话时改发静音。原来每块 3200 帧（16 kHz 下 200 ms），现在配置改成了 320 帧（20 ms） |
| 接收线程 | 3 月时在 `RealtimeClient` 里用 Boost.Beast 同步读 WebSocket，语音包放进播放队列，事件交给 `HandleEvent` |
| 播放线程 | 从队列取 24 kHz float32 语音写给 PortAudio；队列空、在途计数 `tts_cnt` 归零时，处理候选人的回答 |

一轮问答是这样走的：

1. 面试官说话：语音包一个个进队列，播放线程把它们播出来。
2. 队列播空了，状态切到"空闲"，麦克风开始发真实音频。
3. 服务端识别出最终结果，存进 `pending_answer`，状态切到"面试官思考"。
4. 播放线程调大模型给回答打分，决定下一句是追问、下一题还是总结，然后把这句用 `CHAT_TEXT_QUERY` 发给服务端，前面加上"直接朗读下面文字："，让对话服务把它念出来。
5. 回到第 1 步。

IELTS 命令行版（`src/ielts/`）复用了这里的 `RealtimeClient` 和音频类，但只用上了识别那一半：每答一题临时打开一次麦克风，回调只收识别结果，服务端送回来的考官语音直接丢掉。

### 2.7 native_voice：新写的设备层

`native_voice/` 是 10 月 5 日新写的一个独立 C++17 工程，**不引用旧原型的任何代码**。它有这些东西：

- 由声卡回调把音频推进来，回调里不加锁、不分配内存、不阻塞；
- 预先分配好的单生产者单消费者环形队列；
- 一个自己的 worker 线程；
- 用"代号"（epoch）作废已经排队的旧音频；
- Qt Multimedia 和 PortAudio 两套适配，默认 48 kHz float。

它的 worker 目前只做一件事：把麦克风数据原样搬到播放端。网络、识别、合成都没写，测试和基准都是用合成数据跑的。实时语音最后没走这条线（见 5.5），所以产品的任何构建都不引用它。

## 3. 数据长什么样、放在哪

### 3.1 后端

| 数据 | 放在哪 | 长什么样 |
|---|---|---|
| 口语练习 | `SpeakingAttempt` → `SpeakingTurn` → `SpeakingReport` | 部分、题目、录音路径、原始和清洗后的转写、转写来源、追问来源、分数和讲评 |
| 面试 | `apps/interview` 的会话、每一轮、报告 | 题目来源（题库、简历和 JD）、打字还是语音、追问、报告 |
| AI 任务 | `AITask` | 状态、已试次数（上限 3）、请求和结果、兜底原因、用量；有唯一的幂等键 |
| 钱 | 钱包、预留、流水 | 开始前查余额，成功按实际用量扣，失败或走了兜底不扣 |
| 题库 | `data/ielts/` 下的 JSON | 口语按考季分文件，写作按来源分文件 |
| 录音、合成语音 | 文件 | 表里只存路径；考官语音按句缓存 |

### 3.2 和火山之间的协议帧

和火山之间是一条 WebSocket，上面跑一套自定义的二进制帧：

| 部分 | 长度 | 内容 |
|---|---|---|
| 头 | 4 字节 | 版本、头长度、消息类型、标志、序列化方式、压缩方式各占 4 位，最后 1 字节保留 |
| 事件号 | 4 字节，大端 | 100 开始会话、200 音频、300 打招呼文本、500 指定文本合成、501 文本查询、350/352/359 语音开始/语音数据/结束、450/451/459 用户开始说话/识别结果/停止说话 |
| 会话 ID | 4 字节长度 + 内容 | 建连接的几个事件不带 |
| 负载 | 4 字节长度 + 内容 | JSON 或原始音频，可以 gzip |

C++ 这边只有一份实现（`src/common/protocol.cpp`），旧原型和新引擎共用。后端的 `volcengine_asr.py` 用 Python 把同一套帧格式又实现了一遍，连旧原型的配置文件都会读。

## 4. 为什么这样切

**桌面壳只套网页，不重写界面。** 一套网页同时服务浏览器和桌面，界面只改一处。桌面壳只负责网页做不了的事，实时语音就是其中一件。

**按"用户在不在等"分进程。** 追问用户在等，就在请求里用 SSE 流式做；整节评分慢、会失败、要计费，就进任务表交给 worker。worker 掉了，追问照样能用。

**模型调用只走一个入口。** 都经过 `AIProvider`，后面挂一条降级链：OpenAI 兼容的 HTTP 接口 → 本机 Codex 命令行 → 规则兜底，每个结果都标明是哪条路生成的。

**音频留在 C++，只让控制和文字过桥。** 录音、播放、联网都在 C++ 引擎里。`studioVoice` 上只有开会话、念、开始听、停止听、结束这几个命令，以及状态、转写、错误三类信号，PCM 和凭据都不经过网页。

**语音层不含题目内容。** `VoiceSession` 只管"说一段、听一段"，题目、追问、评分都在 Django。这样面试和 IELTS 不用各写一套轮流说话的逻辑；旧原型的 `DialogSession` 把两者写在一起（见 5.3），是反例。

**旧原型的几个取舍。** 一个线程只管一个会阻塞的东西；面试官说话时半双工，防止回声；拿端到端对话模型当朗读器，一条连接同时拿到识别和合成。这些取舍各自的代价，见下一节。

## 5. 现在的问题

### 5.1 实时语音只覆盖了一部分

- **只有面试追问压力是实时对话。** IELTS 各 Part 的考官语音还是网页播后端合成的 TTS，回答还是录音上传；引擎在这里只负责出字幕。
- **还是半双工。** AI 说话时麦克风不上传，所以不能打断。
- **桌面壳的构建说明只有 macOS 一种**（vcpkg 的 `arm64-osx`）。
- **在普通浏览器里**，转写只能等录音上传后由后端识别，比桌面版慢一步。

### 5.2 同一件事做了好几遍

- **C++ 语音有三套。** 新引擎在产品里用；旧原型和它共用 `RealtimeClient`，线程模型是旧的，有 5.3 的问题；`native_voice` 的设备层没被用到。
- **火山的协议实现了两遍**：一遍是 C++ 的 `Protocol`，一遍是后端 Python 的 `volcengine_asr.py`。
- **IELTS 命令行只复用了一半**：类复用了，线程模型和状态机没复用，考官语音收到后被丢掉。

### 5.3 旧实时原型自身的问题

**正确性问题**，都能局部修，不用动结构。表里前三行在连接层，已经随 5.4 的改动修掉了，因为旧原型和新引擎共用同一个 `RealtimeClient`；其余几行还在旧原型自己的代码里。

| 问题 | 在哪 | 后果 |
|---|---|---|
| TLS 不校验证书（已修） | `realtime_client.cpp` 设了 `ssl::verify_none` | 中间人可以冒充服务端 |
| 多个线程同时写同一个 WebSocket（已修） | 麦克风线程发音频，播放线程发文本查询，都直接 `ws_->write`，没有锁 | 帧可能交错，连接可能出错 |
| 还没等服务端确认会话开始，就标成"已连接"（已修） | 握手一完成就设 `connected_ = true` | 会话还没开始就开始发数据 |
| 播放队列没有上限 | `std::queue<std::vector<float>>` | 服务端一次推太多时，内存和延迟一起涨 |
| 结束时起的分离线程捕获了 `this` | `ProcessPendingAnswer` 里 `detach` 的收尾线程，还不加锁就读队列 | 会话先析构就会访问已释放的内存，而且有数据竞争 |
| 状态回调在持锁的时候调用 | `InterviewStateMachine` 持着锁调回调 | 回调里再改状态或注销回调，就会死锁 |
| 信号处理函数里做完整的 `Stop()` | 命令行入口的信号处理 | 在信号处理里分配内存、拿锁、`join`，都不安全 |

**结构问题**，要动架构：

| 问题 | 现在的写法 | 后果 |
|---|---|---|
| 输出每块 200 ms | 输入块已经改成 320 帧（20 ms）；输出还是一块 4800 帧（24 kHz 下 200 ms），阻塞写，循环里还有 10 ms 的 sleep | 下行光缓冲就有 200 ms 的延迟下限 |
| 大模型调用卡在播放线程里 | 播放线程在队列空时，同步调打分和总结（libcurl），要等几秒 | 这几秒里语音只能排队；停止要等请求结束；结果回来时这一轮可能已经作废，还会被念出来 |
| 轮流说话和面试内容混在一起 | `DialogSession` 同时装着线程、队列、状态机和自我介绍、打分、追问、总结 | IELTS 想复用，只能整个复制一份 |
| 状态机是全局单例 | `InterviewStateMachine::Instance()` | 新旧两个会话会互相覆盖状态，测试也没法并行 |
| 半双工 | 面试官说话时麦克风发静音，忽略"用户开始说话" | 不能打断，抢着说的话直接丢掉；代码里清空队列的那段逻辑实际上执行不到 |
| 拿对话模型当朗读器 | 靠提示词"直接朗读下面文字……" | 它有没有照读、有没有自己接话，客户端都不知道。新引擎改用了指定文本接口（2.5） |

新引擎没有在旧原型上改，而是另写了一层（2.5），所以上面这些在旧原型里都还在。

### 5.4 连接层：四个线程共用一个连接

这一节把 5.3 表里"多个线程同时写同一个 WebSocket"和关闭的问题展开讲，再给出改法。下面描述的是改之前的代码。

<a href="/images/projects/ielts/ws-now.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/ws-now.zh.svg" alt="改之前的连接层：麦克风线程每 200 ms 调一次 ws_->write，播放线程每轮调一次 ws_->write，接收线程一直阻塞在 ws_->read，调 Stop 的线程在 Close 里写结束帧、close、join；它们用的是同一个对象 ws_，里面套着 websocket::stream、ssl_stream、tcp::socket 三层；下面两个红框是两种撞车。" loading="lazy" decoding="async"></a>

整条连接就是 `realtime_client.cpp:495` 里的一个对象 `ws_`，类型是 `websocket::stream<ssl_stream<tcp::socket>>`，三层套在一起：最外层拼 WebSocket 帧，中间做 TLS 加密，最里层是 TCP。写缓冲、帧状态、OpenSSL 会话的加密状态和记录序号，全都装在这一个对象里。Boost.Beast 和 Asio 对它的规定是：**同一个对象，同一时刻只能有一个线程在用。** 可当时有四个线程直接用它，而 `RealtimeClientImpl` 里没有一把锁是管 `ws_` 的。

**撞车 1：两个线程同时写。** 播放线程发下一句（`SendNextPrompt` → `SendTextQuery`）时，麦克风线程还在每 200 ms 发一帧静音。两次 `write` 撞上时，字节可能交错成这样：

<a href="/images/projects/ielts/ws-interleave.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/ws-interleave.zh.svg" alt="麦克风线程要发帧头 A 加 6400 多字节音频，播放线程要发帧头 B 加文本查询；TCP 上实际可能是帧头 A、音频前半、帧头 B、文本查询、音频后半；服务端按帧头 A 往后读 6400 多字节，把文本查询当成了音频，剩下的半截音频被当成下一个帧头，于是判协议错误、关连接。" loading="lazy" decoding="async"></a>

服务端只看到一串字节，分不出哪段来自哪个线程。它按帧头 A 的长度往后读，读到的就是乱的，于是按协议错误关掉连接；如果是 TLS 那一层的状态被同时改了，就是 TLS 错误。火山允许音频和文本交替着发，但前提是每一帧完整发完再发下一帧，**这个前提要由客户端自己保证。** 每次写只占几毫秒，撞上的概率不高，所以表现出来是"偶尔莫名其妙断线，复现不了"。

**撞车 2：关闭时，一个线程写、一个线程读。** 关窗口时，界面线程在 `~MainWindow` 里调 `Stop()`。`Stop()` 先 `join` 麦克风和播放线程，再调 `Close()`：发结束会话帧、发结束连接帧、`ws_->close`，最后 `join` 接收线程。可这时候，接收线程还阻塞在 `ws_->read` 里，于是有三个后果：

- **结束帧可能发坏。** 同一个 TLS 会话被两个线程同时用着。
- **窗口可能关不掉。** 读没有时限（`idle_timeout = 0`，心跳也关了）。服务端不回的话，接收线程会一直等，`join` 就一直不返回，界面线程卡在析构函数里。
- **结束连接帧时有时无。** 服务端回 `SESSION_FINISHED` 时，接收线程会把 `connected_` 改成 `false`，而 `Close()` 要看 `connected_` 才决定发不发结束连接帧，两个线程在赛跑。

**还有一个问题：麦克风线程自己也在写网络。** 网络一卡，TCP 发送缓冲满了，麦克风线程就卡在 `write` 里，没人去读 PortAudio。设备的输入缓冲被填满后，新来的声音就被丢掉，候选人的话会少一截。

**改法有两种。**

一种是止血，改几十行：

- 6 处 `ws_->write` 统一过一把锁；
- 读打开 10 秒的空闲超时和心跳，这样关闭最多卡十来秒；
- `Close()` 发完结束会话帧后，最多等 2 秒的确认，再发结束连接帧，不再看 `connected_` 去赛跑。

这样能堵住"写和写撞车"，但"读和写撞车"还在，麦克风线程也照样会被网络卡住。

另一种是根治：让一个 I/O 线程独占这条连接，对外接口不变。最后做的是这一种。

<a href="/images/projects/ielts/ws-io-owner.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/ws-io-owner.zh.svg" alt="改法：麦克风线程、播放线程、界面线程只往队列里投递，立刻返回；控制队列放文本查询和结束帧，优先发，音频队列有上限，满了丢最旧的并计数；只有 I/O 线程碰 ws_，同一时刻只有一个 async_write，async_read 循环把语音交给回调进播放队列；下面是按顺序执行的关闭：发结束会话，最多等 2 秒确认，发结束连接，async_close，总时限 5 秒。" loading="lazy" decoding="async"></a>

- **只有 I/O 线程碰 `ws_`。** 读、写、关闭都在一个 I/O 线程上执行：只有它在跑这条连接的 `io_context`，所有回调天然一个接一个，不用加锁。别的线程调 `SendAudioData`、`SendTextQuery`、`SendEvent`、`Close`，只是把消息 post 过去，立刻返回，所以麦克风线程再也不会被网络卡住。
- **两个发送队列。** 控制帧（文本查询、指定文本、结束帧）优先发，不会被丢。音频队列有上限，积压超过 0.5 秒左右就丢掉最旧的帧，并且计数，不让延迟一直往上涨。
- **同一时刻只有一个 `async_write` 在途。** `async_read` 循环把收到的消息交给回调，回调只做入队这一件事。
- **关闭是投给 I/O 线程的一个任务**，按写死的顺序执行，并且有总时限。挂着的读会被正常取消，不再靠 `running_` 标志去碰运气。
- **顺手修掉两处**："已连接"改成收到会话已开始的事件才算；TLS 改成校验证书。

测试用一个假的 WebSocket 服务端，配合 TSan 跑：

- 两个线程同时狂发，服务端收到的每一帧都完整；
- 服务端一直不回时，`Close()` 在总时限内返回；
- 服务端卡住不读时，`SendAudioData` 从不阻塞，丢弃计数在涨；
- 同一个对象连接、发送、关闭，反复 20 次也不崩。

这一步放在最前面做，因为连接是最底下一层：它会随机断线的话，上面"轮流说话"的逻辑出了问题，就分不清是谁的锅。而且它不改对外接口，上层的代码不用跟着动。

**结果。**

- **10 月 30 日做完**：上面四项测试，加上证书校验、关闭帧的顺序、服务端先结束会话、连不上时的清理，一共 10 个用例；在 Linux（gcc）上 release、ASan+UBSan、TSan 三种构建都通过。对照火山的接入文档，补上了 StartSession 里标为必传、旧代码一直没发的 `dialog.extra.model`。
- **证书查找**：改成校验证书后，Mac 上会找不到根证书。vcpkg 编的 OpenSSL，默认路径指向它自己的安装目录，那里没有证书包；macOS 的根证书在钥匙串里，OpenSSL 读不到。所以 `ca_file` 为空时，依次查 `SSL_CERT_FILE`、OpenSSL 的默认文件、macOS 自带的 `/etc/ssl/cert.pem` 等几处；都找不到就报错，校验不会悄悄关掉。
- **20 ms 分块**：麦克风线程不再被网络卡住，读麦克风的块才敢从 200 ms 改成 20 ms。在 Mac 上实测，每次读 320 帧，各跑 5 秒，都没有溢出：
  - 蓝牙耳机：中位 18.8 ms、90 分位 24.3 ms、最长 71 ms；
  - 内置麦克风：中位 18.7 ms、90 分位 24.0 ms、最长 29 ms。
- **之后**：在 `RealtimeClient` 上面写了 2.5 的引擎，10 月 31 日接进桌面壳，连真实服务跑通。

### 5.5 native_voice 只做到第一步

计划把这条线分成 6 片：2A 接口和基线、2B 回调适配和测量、2C 连服务端、2D 持续录音和打断、2E 接进桌面壳、2F 回声消除和长时间运行。只有 2B 的代码，而且没有真设备上的测量报告。

后来连服务端、接进桌面壳，都是在改好的 `RealtimeClient` 上另写 `VoiceSession` 做的，没有走这条线。`native_voice` 剩下的价值是它的回调式设备层：如果实测发现阻塞读写的抖动太大，可以拿它替换 `AudioDevice` 的 PortAudio 实现。

### 5.6 网页和后端

- **PCM WebSocket 中转**（默认关闭）：连接一来就 `accept()`，不检查是不是已登录的用户；转给火山的队列 `queue.Queue()` 没有上限。
- **评分页**：前端轮询的两个期限设成了无穷大，而后端的"卡住"判定只放在历史列表和报告详情里，任务查询接口没有。所以 worker 掉线时，正在等的页面会一直转。
- **前端文件太大**：`app.js` 将近 1.8 万行，`styles.css` 4.7 万行。

## 6. 从哪开始读

1. `desktop/src/`：`studio_page.cpp`、`studio_profile.cpp`（藏听写的脚本在这里）、`native_bridge.cpp`。
2. `backend_django/config/urls.py`，然后是 `apps/speaking/services.py` 里的 `start_attempt`、`complete_turn`、`stream_follow_up_sse_events`、`score_attempt`。
3. `backend_django/apps/ai/`：`models.py` 里是任务表，`worker.py` 是 worker 循环，`provider_adapters.py` 是降级链。
4. `backend_django/apps/interview/engine.py`：面试的会话和每一轮。
5. 实时语音，从下往上读：
   - `include/services/realtime_client.h` 和 `src/services/realtime_client.cpp`（连接层）；
   - `include/voice/voice_session.h`（线程和状态的约定都写在注释里），然后是 `src/voice/voice_session.cpp`；
   - `desktop/src/voice_bridge.h`、`realtime_voice_engine.cpp`；
   - `web/static/interview-voice.js`。

   测试是 `tests/realtime_client_test.cpp` 和 `tests/voice_session_test.cpp`，共用 `tests/fake_realtime_server.h`。
6. 旧原型：`src/interview/dialog_session.cpp`（`HandleEvent`、`MicrophoneThreadFunc`、`PlaybackThreadFunc`、`ProcessPendingAnswer`），`src/common/protocol.cpp`，配着 `tests/protocol_test.cpp` 一起看。
7. `native_voice/`：先看 `README.md` 里的契约，再看 `src/engine.cpp`。
