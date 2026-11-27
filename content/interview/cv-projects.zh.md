---
title: "IV. 项目 2：C++17 实时语音雅思训练平台"
date: 2026-11-12T00:00:00+08:00
slug: "cv-projects"
description: "简历项目 2 的专页，一条一节：整体和范围、四层架构与状态机、四个线程、音频与二进制帧、LLM 结构化输出、Pimpl 与测试。每节先放简历原文，再按步骤讲做法，配简化后的代码，最后照实说当时设计的问题。"
weight: 7
toc: true
math: true
---

这一页把简历项目 2 逐条拆开，一条一节；项目 1 性能优化 skill 在[另一页](/zh/interview/cv-skill/)。代码都是为了讲清楚做法重写的简化版，名字和结构不是原工程的。

## 1. 项目 2 整体：C++17 实时语音雅思训练平台 {#ielts-why}

> **简历原文**
>
> C++17 实时语音雅思训练平台，集成 ASR、TTS、VAD 和 LLM，提供雅思口语与写作训练。

### 1.1 它在做什么：一边说话，一边有人听、有人答 {#ielts-what}

- **用户对着麦克风说，系统要听出来、想一想、念出回答**：这条链上有四件事，识别（ASR）、对话（LLM）、合成（TTS）、判断什么时候说完了（VAD）。
- **识别、对话、合成都在火山引擎的实时语音对话服务里做**，客户端负责三件事：采集和播放音频，通过 WebSocket 和服务端收发数据，维护“现在轮到谁说话”的状态。
- **VAD（语音活动检测）由服务端做**，结果以“用户开始说话”“用户停止说话”的事件到客户端，客户端据此切换状态。
- **LLM 另外有一条路**：实时对话之外，对用户的回答打分、给修改建议，走的是单独的 OpenAI 兼容接口（第 5 节）。

### 1.2 这是 3 月的 C++ 原型，现在的产品结构不同 {#ielts-now}

- **简历里的是 2026 年 2–3 月做的 C++ 原生实时链路**，后来产品改成了 Qt 桌面壳套网页前端、Django 后端，C++ 实时语音引擎是桌面壳里的一个静态库。
- **旧原型的代码还在、还能跑**，但有几处我后来发现并记下来的问题（第 2、3、4 节会各讲一处）。
- **照实讲时**：简历上写的是原型当时的设计；现在知道哪里不好，也知道怎么改。完整的结构和问题列表在[代码结构](/zh/projects/ielts-studio-structure/)和[复盘](/zh/projects/ielts-studio-retrospective/)。

> **讲的时候按这个顺序**
>
> 1. **做什么**：对着麦克风说话，系统识别、对话、合成语音回答，用来练雅思口语。
> 2. **分工**：识别、对话、合成在火山的实时语音服务里；客户端管音频、网络和状态。
> 3. **范围**：简历写的是 3 月的原生原型；现在产品是桌面壳套网页，C++ 引擎是其中一个库。

## 2. 架构与状态机：四层分开，状态机是唯一的协调点 {#ielts-arch}

> **简历原文**
>
> 四层架构（通用层 / 服务层 / 业务层 / UI 层），模块间通过抽象接口解耦；线程安全的全局状态机作为唯一协调中心，跨线程行为通过事件投递驱动

### 2.1 四层各放什么，依赖只往下 {#arch-layers}

| 层 | 放什么 | 依赖谁 |
|---|---|---|
| 通用层 | 协议编解码、日志、配置、线程安全队列 | 只依赖标准库 |
| 服务层 | WebSocket 客户端、音频设备、LLM 客户端 | 通用层 |
| 业务层 | 对话会话、状态机、打分和跟进提问逻辑 | 服务层的抽象接口 |
| UI 层 | Qt 界面 | 业务层 |

- **依赖只往下，不往上**：服务层不知道业务层存在，通用层不知道服务层存在。
- **业务层依赖的是抽象接口，不是具体类**：业务层认的是“有一个能发音频、能收事件的东西”，而不是 Boost.Beast 的 WebSocket。

```cpp
// 服务层给业务层看的接口：只有“发”和“收到事件时通知谁”
class IRealtimeClient {
public:
    virtual ~IRealtimeClient() = default;
    virtual void SendAudio(const float* pcm, size_t frames) = 0;
    virtual void SendTextQuery(const std::string& text) = 0;
    virtual void SetOnEvent(std::function<void(const Event&)> cb) = 0;
};
// 业务层只持有 IRealtimeClient*；真实现用 Boost.Beast，测试用假的
```

- **这样切的好处**：测试时业务层可以接一个假的客户端，不用联网；换一家语音服务只换服务层。

### 2.2 为什么要一个状态机：多个线程都想改“现在是谁在说话” {#arch-why-sm}

- **这个系统有几个并行的线程**：麦克风线程在发音频，播放线程在播放，接收线程在收事件。它们都要知道“现在是考官在说，还是用户在说”。
- **没有统一的协调点，状态就散在各个线程里**：每个线程各自设标志位，两个线程同时改的话，谁后改谁生效，行为随时序变化，很难复现。
- **所以只有一个状态机持有“现在的状态”**：线程不直接改别人的状态，也不直接调用别的线程的函数，只往状态机里投递事件。

### 2.3 事件投递：线程只说“发生了什么”，状态机决定“因此怎么办” {#arch-events}

```cpp
enum class State { Idle, InterviewerSpeaking, Listening, Thinking /* ...示意，原型里一共 8 个 */ };
enum class Ev    { PlaybackDrained, UserSpeechFinal, AnswerScored /* ... */ };

class StateMachine {
public:
    using Listener = std::function<void(State from, State to)>;

    void Post(Ev ev) {                              // 任何线程都可以调
        State from, to;
        std::vector<Listener> to_call;
        {
            std::lock_guard lk(mu_);
            from = state_;
            to   = Transition(state_, ev);          // 查转移表，不合法的返回原状态
            if (to == from) return;
            state_ = to;
            to_call = listeners_;                   // 拷出一份，锁外再调
        }
        for (auto& cb : to_call) cb(from, to);      // 不持锁调回调
    }

    State Get() const { std::lock_guard lk(mu_); return state_; }

private:
    static State Transition(State s, Ev ev);        // 一张转移表
    mutable std::mutex mu_;
    State state_ = State::Idle;
    std::vector<Listener> listeners_;
};
```

- **转移表是唯一决定“什么事件在什么状态下导致什么状态”的地方**：所有线程的行为都服从这一张表，要看逻辑只看这一处。
- **回调要在锁外调**：回调里如果又去改状态或注销回调，而锁还持着，就会死锁。做法是在锁里把状态改好、把回调列表拷出来，放锁以后再逐个调用。
- **线程读取状态要走 `Get()`**：比如麦克风线程每发一帧前看一眼，现在是不是该发真实音频，还是发静音。

### 2.4 照实说：全局单例有代价 {#arch-honest}

- **“全局”意味着整个进程只有一个状态机**：优点是协调点唯一，不用在对象之间传来传去。
- **缺点是两个会话会互相覆盖状态**，测试也不能并行，因为状态是全进程共享的。
- **后来 C++ 引擎里新写的 `VoiceSession` 把状态放进实例里**，一个会话一份，状态只在它自己的控制线程里改，对外回调也只在这个线程调，调用时不持任何锁。
- **“业务混在一起”也是一处**：旧原型的 `DialogSession` 同时装着线程、队列、状态机和打分、跟进提问、总结的逻辑，想让别的场景复用，只能整个复制。新引擎改成“只管说一段、听一段”，题目和评分交给后端。

> **讲的时候按这个顺序**
>
> 1. **分层**：通用、服务、业务、UI 四层，依赖只往下；业务层只认抽象接口，所以能接假实现测试，也能换语音服务商。
> 2. **状态机**：几个线程都要知道“谁在说话”，所以只让状态机持有状态，线程只投事件。
> 3. **实现要点**：转移表集中，加锁改状态，回调拷出来放锁后再调。
> 4. **代价**：全局单例让两个会话互相覆盖状态；后来的新引擎把状态放进会话实例里。

## 3. 并发模型：四个线程，每个只阻塞在一件事上 {#ielts-threads}

> **简历原文**
>
> 主线程、麦克风、播放、接收四个线程，用 std::atomic、std::mutex、condition_variable 协调，各线程职责单一

### 3.1 四个线程各自阻塞在哪里 {#threads-what}

| 线程 | 阻塞在 | 干什么 |
|---|---|---|
| 主线程（Qt） | 事件循环 | 显示对话和状态，只处理别的线程投递过来的回调 |
| 麦克风线程 | PortAudio 阻塞读 | 读一块音频，编成帧发出去；对面在说话时改发静音 |
| 接收线程 | WebSocket 阻塞读 | 收到语音包放进播放队列，收到事件投给状态机 |
| 播放线程 | 播放队列的条件变量 | 取出语音包，阻塞写给 PortAudio |

- **每个线程只阻塞在一件事上**：麦克风线程卡在读麦克风，卡在读时不影响别的线程播放；接收线程卡在读网络，不影响麦克风。这就是“职责单一”：一个会阻塞的调用，独占一个线程。
- **不用一个线程轮流做**：轮流做的话，一个调用卡住，其它所有事情都停；而这四件事（读麦克风、读网络、写扬声器、画界面）的节奏互不相干。

### 3.2 播放队列：互斥锁加条件变量 {#threads-queue}

接收线程往队列里放语音包，播放线程从队列里取。队列空的时候播放线程要等，不能空转：

```cpp
class PlaybackQueue {
public:
    void Push(std::vector<float> chunk) {
        { std::lock_guard lk(mu_); q_.push(std::move(chunk)); }
        cv_.notify_one();                           // 锁外通知，被唤醒的线程不用立刻再等锁
    }

    // 返回 false 表示已经停止
    bool Pop(std::vector<float>& out) {
        std::unique_lock lk(mu_);
        cv_.wait(lk, [&] { return !q_.empty() || stopped_; });   // 带条件的等待
        if (q_.empty()) return false;
        out = std::move(q_.front());
        q_.pop();
        return true;
    }

    void Stop() {
        { std::lock_guard lk(mu_); stopped_ = true; }
        cv_.notify_all();                           // 叫醒所有等着的线程
    }

private:
    std::mutex mu_;
    std::condition_variable cv_;
    std::queue<std::vector<float>> q_;
    bool stopped_ = false;
};
```

- **`wait` 带条件**：条件变量可能被无故唤醒（虚假唤醒），所以醒来要重新检查队列是否真的不空。
- **条件变量代替 `sleep` 轮询**：轮询要么延迟大，要么白占 CPU；条件变量让线程睡到真有数据才醒。
- **`stopped_` 也在锁里改**：停止的时候要叫醒等着的线程，让它看到 `stopped_` 退出。否则线程会永远睡着，`join` 永远等不到。

### 3.3 `std::atomic` 用在不需要锁的单个变量上 {#threads-atomic}

```cpp
std::atomic<bool> running{true};                    // 所有线程的循环条件
std::atomic<int>  tts_in_flight{0};                 // 已发出还没播完的语音包数

void MicLoop() {
    while (running.load(std::memory_order_acquire)) {
        ReadBlock(buf);                             // 阻塞读
        client->SendAudio(buf, frames);
    }
}
```

- **单个标志位、单个计数，用原子变量就够**：不用为了读一个 `bool` 去拿锁。
- **多个变量必须一起保持一致时用锁**：比如队列和 `stopped_`，所以放在同一把锁下。
- **停止的顺序**：`running` 设为假，对每个阻塞的地方想办法叫醒它（队列 `Stop()`，网络连接关闭使读返回，音频流关闭），然后逐个 `join`。

### 3.4 照实说：这个模型有三个后来发现的问题 {#threads-honest}

- **多个线程同时写同一个 WebSocket 对象**：麦克风线程发音频，播放线程发文本查询，都直接调 `write`。Boost.Beast 规定同一个对象同一时刻只能有一个线程在用，撞上时两帧的字节会交错，服务端判协议错误，表现是“偶尔莫名其妙断线”。
- **大模型调用卡在播放线程里**：播放线程在队列空时同步调大模型打分，要等几秒，这几秒语音只能排队，停止要等请求结束。
- **关闭时一个线程写、一个线程读**：接收线程还阻塞在读里，关闭的线程就在同一个连接上发结束帧，窗口还可能关不掉。
- **后来的改法**：让一个 I/O 线程独占这条连接，别的线程只往队列里投递，立刻返回；控制帧优先发，音频队列有上限，满了丢最旧的并计数；关闭是投给 I/O 线程按顺序执行的一个任务，有总时限。测试配 TSan 跑。详见[代码结构 5.4](/zh/projects/ielts-studio-structure/)。

> **讲的时候按这个顺序**
>
> 1. **四个线程**：主线程画界面，麦克风读音频发出去，接收读网络，播放写扬声器；每个线程只阻塞在一件事上。
> 2. **怎么协调**：队列用互斥锁加条件变量，等到有数据才醒；单个标志位用原子变量；停止时设标志、叫醒、再 `join`。
> 3. **后来发现的问题**：四个线程共用一个 WebSocket 对象，写和写、读和写会撞车。
> 4. **改法**：一个 I/O 线程独占连接，别的线程只投递。

## 4. 音频与网络：PortAudio 采集播放，WSS 上跑自定义二进制帧 {#ielts-audio-net}

> **简历原文**
>
> 跨平台音频采集与播放；Boost.Beast WSS 长连接承载自定义二进制协议（帧头 / 事件 / 压缩）

### 4.1 音频：PortAudio 屏蔽了各平台的设备接口 {#av-portaudio}

- **各平台的音频接口不同**：Windows 是 WASAPI，macOS 是 CoreAudio，Linux 是 ALSA。PortAudio 在上面统一成一套接口，同一份代码三个平台都能编。
- **采集和播放用的是阻塞读写**：麦克风线程调一次读，等一块音频到了才返回；播放线程调一次写，把一块数据交给设备。
- **上行和下行格式不同**：上行 16 kHz，下行 24 kHz float32。每一块的大小决定延迟：原型里输入一块 3200 帧，在 16 kHz 下是 200 ms，后来改成 320 帧（20 ms）。

### 4.2 网络：一条 WSS 长连接 {#av-wss}

- **WSS 是 WebSocket 加 TLS**：先 TCP 连接，再 TLS 握手，再 HTTP 升级成 WebSocket，之后双方随时可以发消息，不用像 HTTP 那样一问一答。
- **长连接适合实时对话**：音频是连续不断的小块，每块一个 HTTP 请求的话开销太大。
- **用 Boost.Beast 是因为它是 C++ 里成熟的 WebSocket 实现**，在 Asio 上，同步和异步两种写法都有。

### 4.3 自定义二进制帧：头、事件号、会话 ID、负载 {#av-frame}

火山的实时语音服务规定了一套二进制帧，每个消息由四部分组成：

| 部分 | 长度 | 内容 |
|---|---|---|
| 头 | 4 字节 | 版本、头长度、消息类型、标志、序列化方式、压缩方式各 4 位，最后 1 字节保留 |
| 事件号 | 4 字节，大端 | 100 开始会话、200 音频、300 打招呼文本、500 指定文本合成等 |
| 会话 ID | 4 字节长度 + 内容 | 建连接的几个事件不带 |
| 负载 | 4 字节长度 + 内容 | JSON 或原始音频，可以 gzip 压缩 |

```cpp
#include <cstdint>
#include <string>
#include <vector>

// 大端写 4 字节
inline void PutU32(std::vector<uint8_t>& out, uint32_t v) {
    out.push_back(v >> 24); out.push_back(v >> 16); out.push_back(v >> 8); out.push_back(v);
}

std::vector<uint8_t> Pack(uint8_t msg_type, uint8_t flags, uint8_t serial, uint8_t compress,
                          uint32_t event, const std::string& session,
                          const std::vector<uint8_t>& payload) {
    std::vector<uint8_t> out;
    out.push_back((1 << 4) | 1);                       // 版本 1，头长度 1（单位 4 字节）
    out.push_back((msg_type << 4) | flags);            // 消息类型、标志各 4 位
    out.push_back((serial << 4) | compress);           // 序列化方式、压缩方式各 4 位
    out.push_back(0);                                  // 保留
    PutU32(out, event);                                // 事件号
    PutU32(out, session.size());                       // 会话 ID：长度 + 内容
    out.insert(out.end(), session.begin(), session.end());
    PutU32(out, payload.size());                       // 负载：长度 + 内容
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}
```

- **头里把几个字段压进半个字节**：版本和头长度共用 1 字节，用移位和或运算打包。
- **整数用大端**：网络字节序，不管两边机器字节序是什么，对得上。
- **长度前缀让接收方知道读多少**：先读 4 字节长度，再读那么多字节，不需要分隔符，负载里是任意二进制也不会误判。
- **解包是打包的逆过程**：每读一段前要检查剩余长度够不够，不够就报错，不能越界读。服务端或网络给来的数据不能默认是对的。
- **协议测试**：打包再解包，应该得到同样的字段；少一个字节、长度写大了，应该报错而不是崩。

### 4.4 照实说：跨平台只验证了其中一部分 {#av-honest}

- **“跨平台”靠的是 PortAudio 和 CMake 加 vcpkg**：代码里没有写平台专用的调用。构建说明目前只写了 macOS 一种，别的平台没有逐个验证过。
- **旧原型的连接层原来不校验证书**，后来改成校验。

> **讲的时候按这个顺序**
>
> 1. **音频**：PortAudio 统一各平台设备接口，阻塞读写，上行 16 kHz，下行 24 kHz。
> 2. **网络**：WSS 长连接，因为音频是连续的小块，实时对话要双方随时能发。
> 3. **帧**：4 字节头、4 字节大端事件号、会话 ID 和负载各是“长度加内容”，负载可以压缩。
> 4. **要点**：长度前缀不用分隔符；解包前检查剩余长度，不信任对端的数据。

## 5. LLM 集成：libcurl 调 OpenAI 兼容接口，约束输出 JSON {#ielts-llm}

> **简历原文**
>
> 基于 libcurl 封装 OpenAI 兼容客户端，约束 LLM 返回结构化 JSON，实现实时评分；逐句评估，支持原地修改、把认可的表达加入个人语料库、改完重新评分

### 5.1 用 libcurl 封装一个 HTTP 客户端 {#llm-client}

- **OpenAI 兼容的接口就是一个 HTTPS POST**：请求体是 JSON（模型名、消息列表），返回体也是 JSON。许多服务商用同一套格式，所以换服务商只改地址和密钥。
- **libcurl 的用法**：设 URL、请求头、请求体，设一个回调把返回的数据收进字符串，调 `curl_easy_perform` 同步执行。

```cpp
static size_t WriteCb(char* p, size_t sz, size_t n, void* user) {
    static_cast<std::string*>(user)->append(p, sz * n);   // curl 分块回调，把每块追加进字符串
    return sz * n;
}

struct HttpResult { long status; std::string body; };

HttpResult PostJson(const std::string& url, const std::string& key, const std::string& body,
                    long timeout_s) {
    CURL* c = curl_easy_init();
    std::string resp;
    curl_slist* hdr = nullptr;
    hdr = curl_slist_append(hdr, "Content-Type: application/json");
    hdr = curl_slist_append(hdr, ("Authorization: Bearer " + key).c_str());
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, hdr);
    curl_easy_setopt(c, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, WriteCb);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &resp);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, timeout_s);        // 一定要设超时
    CURLcode rc = curl_easy_perform(c);
    long status = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &status);
    curl_slist_free_all(hdr);
    curl_easy_cleanup(c);
    return {rc == CURLE_OK ? status : -1, resp};
}
```

- **把 curl 的句柄和链表包进 RAII 对象更稳**：上面示意里为了短没写，真实代码里不要中途 `return` 漏掉清理。
- **超时必须设**：不设的话，服务端不回，这个线程就一直卡着。

### 5.2 约束 LLM 返回结构化 JSON：三层 {#llm-json}

自由文本的评分没法程序处理，所以要求模型只返回 JSON：

1. **在提示词里写清楚结构**：字段名、类型、取值范围，给一个示例。
2. **接口支持的话，打开 JSON 模式**（`response_format` 设为 JSON 对象），让服务端保证返回合法 JSON。
3. **收到之后一律校验**：不信任模型。解析失败、缺字段、分数超出范围，都当失败处理。

```cpp
struct SentenceVerdict {
    int         index;          // 第几句
    int         score;          // 0–9
    std::string issue;          // 问题在哪
    std::string suggestion;     // 建议的改法
};

std::optional<std::vector<SentenceVerdict>> ScoreEssay(const std::string& essay) {
    std::string prompt =
        "Return ONLY a JSON object: {\"sentences\":[{\"index\":int,\"score\":0-9,"
        "\"issue\":string,\"suggestion\":string}]}.\n\nEssay:\n" + essay;
    for (int attempt = 0; attempt < 2; ++attempt) {              // 失败重试一次
        auto r = PostJson(url_, key_, BuildRequest(prompt), 30);
        if (r.status != 200) continue;
        auto v = ParseVerdicts(r.body);                          // 解析 + 校验，失败返回空
        if (v) return v;
    }
    return std::nullopt;                                         // 调用方显示“评分失败，重试”
}
```

- **校验是为了不把模型的偶发错误传给界面**：模型偶尔会多一句解释、漏一个字段、把分数写成字符串。
- **失败时重试一次，再失败就告诉用户**：不能让界面卡在“评分中”。

### 5.3 逐句评估：每一句一个独立的结果 {#llm-sentence}

- **整篇一个总分不够用**：用户要知道具体哪句有问题。所以让模型对每一句单独返回分数、问题和建议。
- **每一句有稳定的编号**：用户改第 3 句，不会让第 4 句的结果错位。
- **原地修改**：界面上用户直接改某一句的文字，不用重新输入整篇。
- **改完重新评分**：只把改过的这一句发给模型重新评，不整篇重评，更快也更便宜。
- **加入个人语料库**：用户认可的好表达（模型建议的，或自己写的），保存到本地的语料库，下次写作可以查。

```cpp
void OnUserEdited(int index, const std::string& new_text) {
    sentences_[index].text = new_text;
    auto v = ScoreSentence(context_around(index), new_text);     // 只评这一句，附上前后文
    if (v) sentences_[index].verdict = *v;
}

void OnUserAccepted(int index) {                                  // 认可这句的表达
    corpus_.Add(sentences_[index].text);
}
```

- **只评一句也要带前后文**：句子的好坏要看它在段落里的位置，单独拿出来评会失真。

### 5.4 照实说：LLM 调用同步卡在线程里 {#llm-honest}

- **旧原型里，评分是在播放线程里同步调用的**（第 3 节），要等几秒，期间语音排队；结果回来时，这一轮可能已经作废。
- **正确的写法**：LLM 调用放在单独的线程或任务里，结果带着“这一轮的编号”回来，编号对不上就丢掉。新引擎把题目、跟进提问、评分都放在后端，客户端只管说和听。

> **讲的时候按这个顺序**
>
> 1. **客户端**：libcurl 发 HTTPS POST，OpenAI 兼容格式，设超时，换服务商只改地址和密钥。
> 2. **结构化输出**：提示词写清楚 JSON 结构，接口支持就开 JSON 模式，收到之后一律校验，失败重试一次。
> 3. **逐句**：每一句单独评分和建议，改一句只重评这一句，认可的表达存进语料库。
> 4. **问题**：旧原型里这个调用卡在播放线程里，应该放到单独的线程。

## 6. 工程质量：Pimpl 隔离重依赖，日志、测试、ASan 兜底 {#ielts-quality}

> **简历原文**
>
> Pimpl 隔离 Boost.Beast、PortAudio、PoDoFo 等重依赖；spdlog 日志、GTest 单元测试、AddressSanitizer；Qt6 桌面界面，支持导出 JSON 报告

### 6.1 Pimpl：头文件里只放接口，重依赖藏进 .cpp {#quality-pimpl}

- **Boost.Beast 的头文件很重**：包含它的每个源文件都要多编译很久；它还会把一大堆宏和类型带进所有包含你头文件的地方。
- **Pimpl（pointer to implementation）**：类的头文件里只声明一个指向实现类的指针，实现类的定义和所有重依赖都放在 `.cpp` 里。

```cpp
// realtime_client.h：没有任何 Boost 头文件
class RealtimeClient {
public:
    RealtimeClient();
    ~RealtimeClient();                      // 必须声明，在 .cpp 里定义
    void SendAudio(const float* pcm, size_t frames);
private:
    struct Impl;                            // 只声明
    std::unique_ptr<Impl> impl_;
};

// realtime_client.cpp：重依赖只在这里
#include <boost/beast/websocket.hpp>
struct RealtimeClient::Impl {
    boost::beast::websocket::stream<boost::beast::ssl_stream<boost::asio::ip::tcp::socket>> ws;
};
RealtimeClient::RealtimeClient() : impl_(std::make_unique<Impl>()) {}
RealtimeClient::~RealtimeClient() = default;   // 这里 Impl 是完整类型，unique_ptr 才能销毁它
```

- **析构函数要放在 `.cpp` 里定义**：`unique_ptr<Impl>` 销毁时需要完整的 `Impl`，头文件里只有声明，编译器在头文件里生成默认析构就会报错。
- **好处有三个**：改实现不触发所有包含者重编译；重依赖的头文件和宏不泄漏到别处；换 PortAudio 或 Beast 的版本只影响一个源文件。
- **代价是一次堆分配和一次间接访问**：所以只用在不在热路径上的类上。音频每 20 ms 一块，这个开销可以忽略。

### 6.2 日志、单元测试、AddressSanitizer {#quality-test}

- **spdlog 日志带级别**：调试时看详细，发布时只留警告。日志里记线程、事件、状态转移，线程问题靠它复盘。
- **GTest 测什么**：能脱离设备和网络测的东西。协议的打包解包、状态机的转移表、JSON 校验。

```cpp
TEST(Protocol, PackThenParseRoundTrips) {
    auto bytes = Pack(/*msg_type=*/1, /*flags=*/4, /*serial=*/1, /*compress=*/0,
                      /*event=*/200, "session-1", {1, 2, 3});
    Frame f;
    ASSERT_TRUE(Parse(bytes, f));
    EXPECT_EQ(f.event, 200u);
    EXPECT_EQ(f.session, "session-1");
    EXPECT_EQ(f.payload, (std::vector<uint8_t>{1, 2, 3}));
}

TEST(Protocol, TruncatedFrameIsRejected) {
    auto bytes = Pack(1, 4, 1, 0, 200, "s", {1, 2, 3});
    bytes.resize(bytes.size() - 1);                    // 少一个字节
    Frame f;
    EXPECT_FALSE(Parse(bytes, f));                     // 必须报错，不能越界读
}

TEST(StateMachine, IllegalEventKeepsState) {
    StateMachine sm;
    sm.Post(Ev::AnswerScored);                         // 空闲状态下不该出现的事件
    EXPECT_EQ(sm.Get(), State::Idle);
}
```

- **AddressSanitizer 抓内存错误**：编译时加 `-fsanitize=address -g`，越界读写、释放后使用、内存泄漏在运行时直接报，带调用栈。
- **ASan 管不到的**：数据竞争要用 TSan（`-fsanitize=thread`）。原型当时只配了 ASan，所以多线程撞车的问题是后来加了假服务端和 TSan 才测出来的。

### 6.3 Qt6 界面和 JSON 报告 {#quality-ui}

- **UI 层只做显示和输入**：不含业务逻辑，业务层的状态变化通过回调投递到 Qt 主线程再更新界面。
- **跨线程更新界面要走投递**：别的线程不能直接改控件，用 Qt 的 `QMetaObject::invokeMethod` 或信号槽把调用排到主线程。
- **导出 JSON 报告**：把一次练习的题目、转写、每句评分和建议序列化成 JSON 文件，用户可以保存或复盘。

> **讲的时候按这个顺序**
>
> 1. **Pimpl**：Boost.Beast 的头文件很重，头文件里只留接口和指针，实现放 `.cpp`，改实现不触发大量重编译；析构要放在 `.cpp` 里。
> 2. **测试**：GTest 测协议打包解包、状态机转移、JSON 校验，这些不依赖设备和网络。
> 3. **ASan**：抓越界、释放后使用；管不到数据竞争，那要 TSan，后来加了。
> 4. **UI**：Qt 只显示，跨线程更新走投递，可以导出 JSON 报告。
