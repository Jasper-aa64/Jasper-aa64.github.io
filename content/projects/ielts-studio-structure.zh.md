---
title: "雅思口语练习站：代码结构"
date: 2026-10-30
slug: "ielts-studio-structure"
description: "一个练雅思口语和写作的网站：考官出题，对着麦克风回答，AI 贴着回答追问一句，最后出一份带分数和改写的报告。三个进程：浏览器单页、Django、AI worker。用户在等的追问在请求里流式做；一分钟级、会失败、要计费的整节评分进任务表，交给 worker。"
weight: 1
toc: true
---
这是一个练雅思口语和写作的网站。口语部分像真考场：考官念题，你对着麦克风回答，考官贴着你的回答追问一句，一节结束后出一份报告，里面有分数、逐题讲评和 7 分示范回答。写作部分是题库、每日写作和段落级批改。代码在 [GitHub](https://github.com/Jasper-aa64/AI-realtime_speech-for-IELTS-Job_Interview)。

这篇按三个问题讲结构：谁在什么时候干活，数据长什么样、放在哪，为什么这样切。踩过的坑放在[复盘](../ielts-studio-retrospective/)里。

## 1. 总图

<a href="/images/projects/ielts/structure.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/structure.zh.svg" alt="总结构：左边浏览器单页负责录音、听写、播考官语音；中间 Django 进程负责开场、收录音、流式追问、合成考官语音和各类接口，下面是 AI worker 进程，轮询任务表、调模型、写回报告；右边是四类外部服务：大模型 HTTP 流式接口、本机命令行编码代理（兜底）、语音合成、语音识别；底部是数据：SQLite 主表、录音和语音文件、题库 JSON。" loading="lazy" decoding="async"></a>

整个系统是三个进程：

- **浏览器里的单页前端**：录音、显示转写、播考官语音、查评分进度。
- **Django 进程**：所有 HTTP 接口，加一个可选的 WebSocket 通道，跑在 ASGI 上。
- **AI worker 进程**：只做一件事，扫任务表，把排队的评分和批改做完。

外部服务有四类：大模型（走 HTTP 流式接口）、本机的命令行编码代理（HTTP 失败时兜底）、语音合成、语音识别。数据都在一个 SQLite 里，录音和合成好的语音是文件，表里只存路径。

## 2. 谁在什么时候干活

### 2.1 一轮问答：用户在等，所以在请求里做

<a href="/images/projects/ielts/turn.zh.svg" target="_blank" rel="noopener"><img src="/images/projects/ielts/turn.zh.svg" alt="上半部分是一轮问答的时序：浏览器播考官语音，录音加听写，停说后上传录音、提交本轮；Django 开一个 SSE 流式追问，大模型逐字返回，浏览器逐字显示；问句完整时 Django 用后台线程合成语音，就绪后发 tts_ready，浏览器播放追问语音，进入下一轮。下半部分是整节评分：浏览器提交评分，Django 建一条 pending 的 AITask，worker 认领后调模型、写报告，浏览器每 2.5 秒查一次任务状态，到终态就显示报告。" loading="lazy" decoding="async"></a>

一轮问答是用户盯着屏幕等的那段，按时间顺序：

1. 浏览器播考官语音。第一题是固定的录音，后面的题是现场合成的。
2. 用户回答。浏览器一边录音，一边用浏览器自带的听写出转写。
3. 停说后，浏览器上传录音，再提交这一轮。转写以浏览器听写为准；听写没拿到的，后端再用语音识别从录音补一份。
4. 浏览器打开一个 SSE 连接要追问。Django 读这一轮的题目和转写，拼成提示词，向大模型要流式结果，每收到一小段就往下推一个 `chunk` 事件，浏览器逐字显示。
5. 后端一看到完整问句（有问号或生成结束），先推 `question_complete`，同时开一个后台线程合成这句的语音；合成好了再推 `tts_ready`，浏览器拿到地址就播。

追问先出文字、后出语音，是为了让用户停说后尽快看到考官"开口"。从停说到追问出第一个字，实测大约 2 秒。

### 2.2 整节评分：慢、会失败、要计费，所以交给 worker

一节结束后要给整节打分、逐题讲评、写 7 分示范回答，一次要一分钟左右，中途可能失败要重试，还要扣费。这些都不适合放在请求线程里做，所以：

1. 浏览器提交评分，Django 在任务表 `AITask` 里写一行，状态 `pending`。建之前先查钱包余额够不够。
2. worker 每 1 到 2.5 秒扫一次表，按创建时间取排队的任务，认领后改成 `running`，调模型，把报告写回练习记录，任务改成 `succeeded`，按这次实际用掉的量扣费。
3. 浏览器每 2.5 秒查一次这条任务，到了终态就停，显示报告或失败原因。失败时录音已经存下，可以直接重新分析，不用重录。

worker 每一轮扫表时，还会把超过 900 秒还在 `running` 的任务收回来：没用完重试次数的重新排队，用完的标成失败，不扣费。

### 2.3 实时识别：叠加的一条路，不替换主流程

浏览器可以选择把录音转成 16 kHz PCM，通过 WebSocket 实时传给后端，后端转交语音识别服务，边说边出字。这条路出问题时，主流程照旧"录完上传"，录音不受影响。为了接 WebSocket，Django 从 WSGI 换到了 ASGI；换的时候，验收条件是现有 HTTP 接口的行为一个都不变、原有测试全部通过。

## 3. 数据长什么样、放在哪

| 数据 | 放在哪 | 长什么样 |
|---|---|---|
| 一次练习 | 表 `SpeakingAttempt` | 考哪个部分、抽到的题、状态 |
| 每一轮 | 表 `SpeakingTurn` | 题目、录音路径、原始转写、清洗后的转写、追问是谁生成的 |
| 报告 | 表 `SpeakingReport` | 分数、逐题讲评、示范回答 |
| AI 任务 | 表 `AITask` | 状态、已试次数（上限 3）、何时可再试、哪个 worker 在做、请求和结果、兜底原因、关联的预留 |
| 钱 | 钱包、预留、流水等几张表 | 开始前查余额，成功按实际用量扣，失败或走了兜底不扣，每笔都进流水 |
| 题库 | `data/ielts/` 下的 JSON | 口语按考季分文件，写作按来源分文件，导入数据库 |
| 录音、合成语音 | 文件 | 表里只存路径；考官语音按句缓存，同一句不重复合成 |

`AITask` 有两点要说明：

- **同一件事只建一个任务**。`AITask` 有唯一的幂等键，同一份报告重复提交，拿到的还是原来那个任务。
- **结果都带来源**。任务结果里写明是哪条路生成的，HTTP、命令行代理，还是规则兜底，兜底的结果不会冒充 AI 成功。

另外几样数据：语料库（自己准备的口语素材）、Takeaway（练习里攒下的表达）、拼写复习词，各占一张表，都挂在用户下面。

## 4. 为什么这样切

**按"用户在不在等"分进程。** 追问用户在等，放在请求里流式做；整节评分慢、会失败、要计费，放进任务表交给 worker。worker 掉了，追问照样能用，只是评分排着队。任务状态都在数据库里，所以刷新页面、重启 Django 都不会丢。

**模型调用只走一个入口，后面挂一条降级链。** 所有模型调用都经过同一个 `AIProvider` 接口，后面按顺序试：HTTP 流式接口、本机命令行代理、规则兜底。走哪条由一个环境变量控制，可以只走 HTTP，也可以整条链都走。HTTP 慢了或失败了，不影响其他代码。

**前端不打包。** 页面是纯 JS，没有构建这一步，Django 直接把静态文件发出去，改完刷新就能看到。代价是主文件 `app.js` 长到了将近 1.8 万行，复盘里会讲这件事。

**C++ 留下来的部分编成 WASM。** 这个项目最早是一个 C++ 写的桌面面试程序。改成网站时，它的音频核心抽成了纯函数：算音量、检测有没有人说话（复用开源的 WebRTC VAD）、裁掉静音、重采样。这部分用 Emscripten 编成 WASM，在浏览器里做录音预处理。

## 5. 从哪开始读

1. `backend_django/config/urls.py`：100 多个接口都列在这里，先看口语的 `attempts/...` 这一组。
2. `backend_django/apps/speaking/services.py`：`start_attempt`、`complete_turn`、`stream_follow_up_sse_events`、`score_attempt` 四个函数就是一次练习的全过程。
3. `backend_django/apps/ai/`：`models.py` 里是任务表，`worker.py` 是 worker 循环，`services.py` 里的 `claim_ai_task` 负责认领，`provider_adapters.py` 是各条调用路和降级链。
4. `web/static/app.js`：搜 `playExaminerTurn`、`startRecording`、`streamFollowUpForCompletedTurn`，就是前端一轮问答的三段。
5. `src/ielts/audio_core.cpp`：音频核心，WASM 由 `scripts/build_audio_core_wasm.sh` 编出来。
