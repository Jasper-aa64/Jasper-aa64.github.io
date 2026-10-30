---
title: "IELTS：代码结构"
date: 2026-10-30
slug: "ielts-studio-structure"
description: "IELTS 现在由三部分组成：Qt 桌面壳套着网页前端，Django 后端加 AI worker，以及还没接进产品的 C++ 原生语音。语音实际走的是网页和后端那条路；完整的原生实时链路只有 3 月的旧原型有，新写的 native_voice 只到第一步。最后一节列出现在的问题。"
weight: 1
toc: true
---
IELTS 是我做的雅思口语和写作练习工具，最近加了模拟面试。代码在 [GitHub](https://github.com/Jasper-aa64/AI-realtime_speech-for-IELTS-Job_Interview)，最新的是 `ui-polish` 分支。这篇以现在的代码为基线，按三个问题讲：谁在什么时候干活，数据长什么样、放在哪，为什么这样切。第 5 节专门列现在的问题，踩坑的经过放在[复盘](../ielts-studio-retrospective/)里。

## 1. 总图

<a href="/images/projects/ielts/overview.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/overview.zh.svg" alt="现在的总图：左上是 Qt 桌面壳，里面用 QtWebEngine 加载网页前端，还有一个只报能力的 QWebChannel 桥；中间是 Django 和 AI worker；右边是外部服务：大模型 HTTP、Codex 命令行、火山 TTS、火山 ASR；下面红框是 C++ 原生语音，包括旧实时原型、IELTS 命令行、native_voice 和 audio_core，除了 audio_core 编成 WASM 给网页用之外，都没有接进桌面壳。" loading="lazy" decoding="async"></a>

现在的 IELTS 由三部分组成：

- **Qt 桌面壳套网页**：`desktop/` 是一个 QtWebEngine 程序，窗口里加载的就是 `web/static` 的网页前端。同一套网页，在浏览器里也能直接用。
- **Django 后端加 AI worker**：口语、写作、面试、AI 调用、计费都在这里。
- **C++ 原生语音**：3 月的旧实时原型、IELTS 命令行版、10 月新写的 `native_voice`，这三样**都没有接进桌面壳**。唯一用上的 C++ 是 `audio_core`，它编成 WASM，在网页里做录音预处理。

所以现在桌面版里的语音，走的是网页和后端那条路：浏览器录音，上传给后端，后端再调火山引擎。

## 2. 谁在什么时候干活

### 2.1 桌面壳

- 用 QtWebEngine 加载后端的网页，后端地址在设置里改，默认是本机的 `127.0.0.1:8767`。
- 只开一个窗口，网页里的 `window.open` 都重定向回这个窗口；后端连不上时显示一个本地出错页；退出后登录状态还在；菜单是中文。
- 网页和 Qt 之间有一个 QWebChannel 桥 `studioNative`，目前只有一个方法 `capabilities()`，返回"这是桌面版、可以用面试模式、`native_audio = false`"。网页靠它决定显不显示面试入口。
- QtWebEngine 虽然暴露了浏览器听写（Web Speech API），但里面没有语音服务，一调用渲染进程就会被杀掉，所以桌面壳启动时用脚本把它藏了起来。

### 2.2 IELTS 一轮问答：用户在等，所以在请求里做

1. 网页播考官语音（howler.js）。第一题是固定的录音，后面的题由后端调火山 TTS 现场合成。
2. 用户回答，网页用 MediaRecorder 录音。在普通浏览器里，还会用浏览器听写同时出一份转写；在桌面版里听写被藏起来了，转写只能等后端识别。
3. 停说后，网页上传录音，再提交这一轮。没有转写的，后端调火山 ASR，用整段录音补一份。
4. 网页开一个 SSE 连接要追问。Django 读这一轮的题目和转写，拼成提示词，向大模型要流式结果，逐字推给网页。
5. 一看到完整问句，后端就开一个线程合成语音，合成好了推 `tts_ready`，网页拿到地址就播。

### 2.3 整节评分：慢、会失败、要计费，所以交给 worker

网页提交评分后，Django 在任务表 `AITask` 里写一行，状态是 `pending`。worker 每 1 到 2.5 秒扫一次表，认领后调模型、写回报告、按实际用量扣费。网页每 2.5 秒查一次这条任务，到了终态就停。运行超过 900 秒的任务会被 worker 收回，重新排队或者标成失败。

### 2.4 面试模式：桌面版专有，不是实时的

后端的 `apps/interview` 负责面试：内置题库，也可以用简历和岗位描述（JD）让大模型出题；然后开会话，一题一题回答，可以要一次追问，最后出报告。每一题的回答可以打字，也可以录完音上传，由后端调火山 ASR 整段识别。

面试的 AI 调用也记在 `AITask` 里，但创建任务时就直接认领、当场执行，不经过 worker。面试里的"AI 助手"调的是本机的 Codex 命令行。

### 2.5 3 月的旧实时原型：完整，但没在产品里跑

<a href="/images/projects/ielts/cpp.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/cpp.zh.svg" alt="3 月实时原型的线程图：Qt 界面线程和会话线程；麦克风线程读 16 kHz 音频编帧发出；接收线程用 Boost.Beast 同步读帧，语音包进播放队列，事件交给 HandleEvent；播放线程把 24 kHz 音频写给 PortAudio，队列空时处理回答并把下一句发给服务端去念；右边是火山引擎实时语音对话服务和大模型 HTTP 接口；下面是 8 个状态的状态机。" loading="lazy" decoding="async"></a>

`src/` 下的这套代码，是目前唯一完整的原生实时链路。识别、对话、合成都在火山引擎的实时语音对话服务里做，客户端负责收发音频和维护状态。当时的界面是 Qt Widgets，现在已经不用了，但代码还能编译、还能跑。

一共五个线程：

| 线程 | 干什么 |
|---|---|
| Qt 界面线程 | 显示对话和状态，只处理别的线程投递过来的回调 |
| 会话线程 | 跑 `DialogSession::Start`：连服务、开会话、起麦克风线程和播放线程 |
| 麦克风线程 | 用阻塞方式读 PortAudio，每块 3200 帧（16 kHz 下是 200 ms），编成帧发出去；面试官说话时改发静音 |
| 接收线程 | 在 `RealtimeClient` 里用 Boost.Beast 同步读 WebSocket，语音包放进播放队列，事件交给 `HandleEvent` |
| 播放线程 | 从队列取 24 kHz float32 语音写给 PortAudio；队列空、在途计数 `tts_cnt` 归零时，处理候选人的回答 |

一轮问答是这样走的：

1. 面试官说话：语音包一个个进队列，播放线程把它们播出来。
2. 队列播空了，状态切到"空闲"，麦克风开始发真实音频。
3. 服务端识别出最终结果，存进 `pending_answer`，状态切到"面试官思考"。
4. 播放线程调大模型给回答打分，决定下一句是追问、下一题还是总结，然后把这句用 `CHAT_TEXT_QUERY` 发给服务端，前面加上"直接朗读下面文字："，让对话服务把它念出来。
5. 回到第 1 步。

IELTS 命令行版（`src/ielts/`）复用了这里的 `RealtimeClient` 和音频类，但只用上了识别那一半：每答一题临时打开一次麦克风，回调只收识别结果，服务端送回来的考官语音直接丢掉。

### 2.6 native_voice：新写的设备层

`native_voice/` 是 10 月 5 日新写的一个独立 C++17 工程，**不引用旧原型的任何代码**。它有这些东西：

- 由声卡回调把音频推进来，回调里不加锁、不分配内存、不阻塞；
- 预先分配好的单生产者单消费者环形队列；
- 一个自己的 worker 线程；
- 用"代号"（epoch）作废已经排队的旧音频；
- Qt Multimedia 和 PortAudio 两套适配，默认 48 kHz float。

它的 worker 目前只做一件事：把麦克风数据原样搬到播放端。网络、识别、合成都还没写，也没接到桌面壳上；测试和基准都是用合成数据跑的。

## 3. 数据长什么样、放在哪

### 3.1 后端

| 数据 | 放在哪 | 长什么样 |
|---|---|---|
| 口语练习 | `SpeakingAttempt` → `SpeakingTurn` → `SpeakingReport` | 部分、题目、录音路径、原始和清洗后的转写、追问来源、分数和讲评 |
| 面试 | `apps/interview` 的会话、每一轮、报告 | 题目来源（题库、简历和 JD）、打字还是语音、追问、报告 |
| AI 任务 | `AITask` | 状态、已试次数（上限 3）、请求和结果、兜底原因、用量；有唯一的幂等键 |
| 钱 | 钱包、预留、流水 | 开始前查余额，成功按实际用量扣，失败或走了兜底不扣 |
| 题库 | `data/ielts/` 下的 JSON | 口语按考季分文件，写作按来源分文件 |
| 录音、合成语音 | 文件 | 表里只存路径；考官语音按句缓存 |

### 3.2 旧原型的协议帧

和火山之间是一条 WebSocket，上面跑一套自定义的二进制帧：

| 部分 | 长度 | 内容 |
|---|---|---|
| 头 | 4 字节 | 版本、头长度、消息类型、标志、序列化方式、压缩方式各占 4 位，最后 1 字节保留 |
| 事件号 | 4 字节，大端 | 100 开始会话、200 音频、501 文本查询、350/359 语音开始/结束、450/451/459 用户开始说话/识别结果/停止说话 |
| 会话 ID | 4 字节长度 + 内容 | 建连接的几个事件不带 |
| 负载 | 4 字节长度 + 内容 | JSON 或原始音频，可以 gzip |

后端的 `volcengine_asr.py` 用 Python 把同一套帧格式又实现了一遍，连旧原型的配置文件都会读。

## 4. 为什么这样切

**桌面壳只套网页，不重写界面。** 一套网页同时服务浏览器和桌面，界面只改一处。桌面壳只负责网页做不了的事；按计划，原生语音也是其中一件。

**按"用户在不在等"分进程。** 追问用户在等，就在请求里用 SSE 流式做；整节评分慢、会失败、要计费，就进任务表交给 worker。worker 掉了，追问照样能用。

**模型调用只走一个入口。** 都经过 `AIProvider`，后面挂一条降级链：OpenAI 兼容的 HTTP 接口 → 本机 Codex 命令行 → 规则兜底，每个结果都标明是哪条路生成的。

**计划中，音频留在 C++，只让事件过桥。** 原生语音接进来以后，录音和播放都在 C++ 里做，网页只收"状态变了""这是转写"这类事件，不让音频数据经过网页。

**旧原型的几个取舍。** 一个线程只管一个会阻塞的东西；面试官说话时半双工，防止回声；拿端到端对话模型当朗读器，一条连接同时拿到识别和合成。这些取舍各自的代价，见下一节。

## 5. 现在的问题

### 5.1 原生语音没接进产品

- 桥只报能力，`native_audio` 写死是 `false`。`desktop/CMakeLists.txt` 只链接了 Qt Widgets、WebEngine、WebChannel，没有任何音频或网络库。
- 桌面版的语音完全走网页那条路，而且因为浏览器听写被藏了起来，转写只能等录音上传后由后端识别，比普通浏览器里还慢一步。
- 整个产品里没有一处是实时对话：IELTS 是"录完上传"，面试也是"打字或录完上传"。

### 5.2 同一件事做了好几遍

- **两套 C++ 语音互不相干。** 旧原型能跑完整链路，但线程模型有问题（见 5.3）；`native_voice` 的设备层写得干净，但上面什么都没有。
- **火山的协议实现了两遍**：一遍是 C++ 的 `Protocol`，一遍是后端 Python 的 `volcengine_asr.py`。
- **IELTS 命令行只复用了一半**：类复用了，线程模型和状态机没复用，考官语音收到后被丢掉。

### 5.3 旧实时原型自身的问题

**正确性问题**，都能局部修，不用动结构：

| 问题 | 在哪 | 后果 |
|---|---|---|
| TLS 不校验证书 | `realtime_client.cpp` 设了 `ssl::verify_none` | 中间人可以冒充服务端 |
| 多个线程同时写同一个 WebSocket | 麦克风线程发音频，播放线程发文本查询，都直接 `ws_->write`，没有锁 | 帧可能交错，连接可能出错 |
| 还没等服务端确认会话开始，就标成"已连接" | 握手一完成就设 `connected_ = true` | 会话还没开始就开始发数据 |
| 播放队列没有上限 | `std::queue<std::vector<float>>` | 服务端一次推太多时，内存和延迟一起涨 |
| 结束时起的分离线程捕获了 `this` | `ProcessPendingAnswer` 里 `detach` 的收尾线程，还不加锁就读队列 | 会话先析构就会访问已释放的内存，而且有数据竞争 |
| 状态回调在持锁的时候调用 | `InterviewStateMachine` 持着锁调回调 | 回调里再改状态或注销回调，就会死锁 |
| 信号处理函数里做完整的 `Stop()` | 命令行入口的信号处理 | 在信号处理里分配内存、拿锁、`join`，都不安全 |

**结构问题**，要动架构：

| 问题 | 现在的写法 | 后果 |
|---|---|---|
| 每次读写 200 ms | 输入一块 3200 帧（16 kHz），输出一块 4800 帧（24 kHz），都是阻塞读写，循环里还有 10 ms 的 sleep | 光缓冲就有几百毫秒的延迟下限 |
| 大模型调用卡在播放线程里 | 播放线程在队列空时，同步调打分和总结（libcurl），要等几秒 | 这几秒里语音只能排队；停止要等请求结束；结果回来时这一轮可能已经作废，还会被念出来 |
| 轮流说话和面试内容混在一起 | `DialogSession` 同时装着线程、队列、状态机和自我介绍、打分、追问、总结 | IELTS 想复用，只能整个复制一份 |
| 状态机是全局单例 | `InterviewStateMachine::Instance()` | 新旧两个会话会互相覆盖状态，测试也没法并行 |
| 半双工 | 面试官说话时麦克风发静音，忽略"用户开始说话" | 不能打断，抢着说的话直接丢掉；代码里清空队列的那段逻辑实际上执行不到 |
| 拿对话模型当朗读器 | 靠提示词"直接朗读下面文字……" | 它有没有照读、有没有自己接话，客户端都不知道 |

### 5.4 native_voice 只做到第一步

计划把这条线分成 6 片：2A 接口和基线、2B 回调适配和测量、2C 连服务端、2D 持续录音和打断、2E 接进桌面壳、2F 回声消除和长时间运行。现在只有 2B 的代码，而且没有真设备上的测量报告；真正干活的 2C 到 2E 都还没开始。

### 5.5 网页和后端

- **PCM WebSocket 中转**（默认关闭）：连接一来就 `accept()`，不检查是不是已登录的用户；转给火山的队列 `queue.Queue()` 没有上限。
- **评分页**：前端轮询的两个期限设成了无穷大，而后端的"卡住"判定只放在历史列表和报告详情里，任务查询接口没有。所以 worker 掉线时，正在等的页面会一直转。
- **前端文件太大**：`app.js` 将近 1.8 万行，`styles.css` 4.7 万行。

## 6. 从哪开始读

1. `desktop/src/`：`studio_page.cpp`、`studio_profile.cpp`（藏听写的脚本在这里）、`native_bridge.cpp`。
2. `backend_django/config/urls.py`，然后是 `apps/speaking/services.py` 里的 `start_attempt`、`complete_turn`、`stream_follow_up_sse_events`、`score_attempt`。
3. `backend_django/apps/ai/`：`models.py` 里是任务表，`worker.py` 是 worker 循环，`provider_adapters.py` 是降级链。
4. `backend_django/apps/interview/engine.py`：面试的会话和每一轮。
5. 旧原型：`src/interview/dialog_session.cpp`（`HandleEvent`、`MicrophoneThreadFunc`、`PlaybackThreadFunc`、`ProcessPendingAnswer`），`src/services/realtime_client.cpp`，`src/common/protocol.cpp`，配着 `tests/protocol_test.cpp` 一起看。
6. `native_voice/`：先看 `README.md` 里的契约，再看 `src/engine.cpp`。
