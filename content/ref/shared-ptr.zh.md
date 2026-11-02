---
title: "shared_ptr 和 enable_shared_from_this"
date: 2026-11-02
slug: "shared-ptr"
description: "shared_ptr 是对象加一块存计数的控制块；复制它是拷两个指针加一次计数加 1，多线程时是一次原子操作。成员函数里要拿到自己的 shared_ptr，不能用 shared_ptr(this) 另起一个控制块，要继承 enable_shared_from_this 再调 shared_from_this()。"
summary: "shared_ptr 的计数在控制块里，make_shared 只分配一次；成员函数里要延长自己的寿命，用 shared_from_this() 共用外面那个控制块，自己另起一个会析构两次。"
toc: true
group: cpplinux
weight: 111
aliases: ["/posts/shared-ptr/"]
---

## 1. `shared_ptr` 是什么：对象 + 一块存计数的控制块 {#shared-ptr}

`std::shared_ptr<T>` 让好几个地方共同拥有一个对象：谁都可以持有一份，最后一份没了，对象才析构。它靠一个引用计数做到这一点。计数不在对象里，而在一块单独的内存里，叫**控制块**（control block）。

- `std::make_shared<T>()` 只分配一次，对象和控制块挨在一起。
- 每复制一个 `shared_ptr`，计数 +1；每销毁一个，计数 -1；减到 0 就析构对象。
- 一个 `shared_ptr` 本身是两个指针：一个指向对象，一个指向控制块，`sizeof` 是 16 B。

<svg viewBox="0 0 760 304" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="make_shared 一次分配，对象和控制块挨在一起；shared_ptr(new T) 分配两次，控制块里多一个指向对象的指针。两个 shared_ptr 都各存一个对象指针和一个控制块指针。" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .sp0bg  { fill: #fbfaf7; }
    .sp0p   { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .sp0c   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .sp0t   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .sp0box { fill: none; stroke: #6b6558; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .sp0ink { fill: #1c1b18; font-size: 12px; }
    .sp0mut { fill: #6b6558; font-size: 12px; }
    .sp0ttl { fill: #1c1b18; font-size: 13.5px; font-weight: 700; font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .sp0ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .sp0hd  { fill: #6b6558; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0bg { fill: #17161b; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0p { fill: #23262c; stroke: #3f4650; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0c { fill: #4a2f2c; stroke: #8f5a4c; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0t { fill: #33421f; stroke: #8fb257; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0box { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0ink, :root:is([data-theme="dark"], [data-theme="black"]) .sp0ttl { fill: #e9e7ef; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0mut { fill: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0ln { stroke: #a19caf; }
    :root:is([data-theme="dark"], [data-theme="black"]) .sp0hd { fill: #a19caf; }
  </style>
  <defs><marker id="sp0a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="sp0hd"/></marker></defs>
  <rect class="sp0bg" x="0" y="0" width="760" height="304" rx="10"/>
  <text class="sp0ttl" x="24" y="32">std::make_shared&lt;T&gt;()</text>
  <text class="sp0mut" x="26" y="71">p1</text>
  <rect class="sp0p" x="48" y="52" width="110" height="30"/>
  <text class="sp0ink" x="103" y="71" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="158" y="52" width="110" height="30"/>
  <text class="sp0ink" x="213" y="71" text-anchor="middle">控制块指针</text>
  <text class="sp0mut" x="26" y="227">p2</text>
  <rect class="sp0p" x="48" y="208" width="110" height="30"/>
  <text class="sp0ink" x="103" y="227" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="158" y="208" width="110" height="30"/>
  <text class="sp0ink" x="213" y="227" text-anchor="middle">控制块指针</text>
  <rect class="sp0box" x="42" y="114" width="312" height="62" rx="6"/>
  <rect class="sp0t" x="48" y="120" width="110" height="50"/>
  <text class="sp0ink" x="103" y="149" text-anchor="middle">T 对象</text>
  <rect class="sp0c" x="158" y="120" width="46" height="50"/>
  <text class="sp0ink" x="181" y="149" text-anchor="middle">vptr</text>
  <rect class="sp0c" x="204" y="120" width="72" height="50"/>
  <text class="sp0ink" x="240" y="149" text-anchor="middle">use = 2</text>
  <rect class="sp0c" x="276" y="120" width="72" height="50"/>
  <text class="sp0ink" x="312" y="149" text-anchor="middle">weak</text>
  <path class="sp0ln" d="M103,82 L103,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M103,208 L103,173" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M213,82 L213,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M213,208 L213,173" marker-end="url(#sp0a)"/>
  <text class="sp0mut" x="24" y="266">一次分配：对象和控制块挨在一起</text>
  <text class="sp0ttl" x="408" y="32">std::shared_ptr&lt;T&gt;(new T)</text>
  <text class="sp0mut" x="410" y="71">p1</text>
  <rect class="sp0p" x="432" y="52" width="110" height="30"/>
  <text class="sp0ink" x="487" y="71" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="542" y="52" width="110" height="30"/>
  <text class="sp0ink" x="597" y="71" text-anchor="middle">控制块指针</text>
  <text class="sp0mut" x="410" y="227">p2</text>
  <rect class="sp0p" x="432" y="208" width="110" height="30"/>
  <text class="sp0ink" x="487" y="227" text-anchor="middle">对象指针</text>
  <rect class="sp0p" x="542" y="208" width="110" height="30"/>
  <text class="sp0ink" x="597" y="227" text-anchor="middle">控制块指针</text>
  <rect class="sp0t" x="432" y="120" width="100" height="50"/>
  <text class="sp0ink" x="482" y="149" text-anchor="middle">T 对象</text>
  <rect class="sp0c" x="552" y="120" width="40" height="50"/>
  <text class="sp0ink" x="572" y="149" text-anchor="middle">vptr</text>
  <rect class="sp0c" x="592" y="120" width="58" height="50"/>
  <text class="sp0ink" x="621" y="149" text-anchor="middle">use = 2</text>
  <rect class="sp0c" x="650" y="120" width="44" height="50"/>
  <text class="sp0ink" x="672" y="149" text-anchor="middle">weak</text>
  <rect class="sp0c" x="694" y="120" width="52" height="50"/>
  <text class="sp0ink" x="720" y="149" text-anchor="middle">ptr→T</text>
  <path class="sp0ln" d="M482,82 L482,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M482,208 L482,173" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M597,82 L597,117" marker-end="url(#sp0a)"/>
  <path class="sp0ln" d="M597,208 L597,173" marker-end="url(#sp0a)"/>
  <text class="sp0mut" x="408" y="266">两次分配：控制块里另存一个指向 T 的指针</text>
  <text class="sp0mut" x="24" y="292">两种写法的 use_count 都在控制块偏移 8 处：第 2 节里 addl $1, 8(%rdx) 加的就是它。</text>
</svg>

两种写法差在分配次数。`make_shared` 只调一次 `operator new`，对象和控制块在同一块内存里，少一次分配，用对象时顺带碰到的计数也多半在相邻的缓存行。代价在释放：`use_count` 归零时对象照常析构，可它占的那段内存和控制块连在一起，要等 `weak_count` 也归零（最后一个 `weak_ptr` 没了）才能整块还掉。**对象很大、又有 `weak_ptr` 长期挂着时，`make_shared` 会让这块内存一直留着**，这时用 `shared_ptr<T>(new T)` 分开分配，对象析构时它的内存就能先还。

## 2. 编译出来是什么：复制 = 拷两个指针 + 计数加 1 {#shared-ptr-asm}

```cpp
std::shared_ptr<S> copy_sp(const std::shared_ptr<S>& p) { return p; }
```

```text
movdqu  (%rsi), %xmm0                    # 一次读 16 B：对象指针 + 控制块指针
movups  %xmm0, (%rdi)                    # 写进新的 shared_ptr
movq    8(%rdi), %rdx                    # 控制块地址
testq   %rdx, %rdx
je      .L12                             # 空指针就不用加计数
cmpb    $0, __libc_single_threaded(%rip) # 进程是不是单线程
je      .L14
addl    $1, 8(%rdx)                      # 单线程：普通加 1
ret
.L14:
lock addl $1, 8(%rdx)                    # 多线程：原子加 1
```

`__libc_single_threaded` 是 glibc 维护的标志，进程还没起第二个线程时为真。一旦有了多个线程，每次复制（以及每次销毁时的减 1）都是一次 `lock` 原子操作：没有别的核在抢时约 5–10 ns；几个核同时复制同一个对象的 `shared_ptr` 时，计数所在的缓存行在核之间来回搬（缓存行乒乓），一次要几十到上百 ns。所以频繁调用的函数不要按值传 `shared_ptr`：只是用一下、不需要“拥有”，就传 `const std::shared_ptr<T>&`，或者直接传 `T&` / `T*`。

## 3. 场景：对象要活到回调执行完 {#shared-from-this-why}

一个 `Session` 对象代表和服务器的一条连接，由 `shared_ptr` 管理。`Session::send_request()` 把请求发出去，服务器要过一会儿（比如几十 µs）才回包。程序不会停下来等，而是先登记一个函数，意思是“回包到了就调用它”。这种先登记、以后由别人来调用的函数叫**回调**。登记完，`send_request()` 立刻返回，程序接着干别的。负责“看到回包到了，就调用登记过的回调”的，通常是一个一直在转的循环，叫**事件循环**。

问题出在等待的这段时间里。回包到之前，程序别处可能已经不用这条连接了（比如风控把它断开），丢掉了手里的 `shared_ptr`。如果回调里没有持有一份 `shared_ptr<Session>`，计数就到 0，`Session` 被析构；回包一到，回调去用的是一个已经析构的对象。回调自己持有一份，计数就不会在它执行之前归零：

| 时刻 | 发生了什么 | 回调不持有时的计数 | 回调持有一份时的计数 |
|---|---|---|---|
| 1 | `make_shared<Session>()`，外面持有一份 | 1 | 1 |
| 2 | `send_request()` 登记回调 | 1 | 2 |
| 3 | 外面丢掉自己那份 | 0，`Session` 被析构 | 1，`Session` 还活着 |
| 4 | 回包到了，事件循环调用回调 | 用到已析构的对象，未定义行为 | 正常处理回包 |
| 5 | 回调执行完、被删掉 | — | 0，这时才析构 |

难点在于：回调是在 `send_request()` 这个成员函数里登记的，函数里手上只有 `this`，一个裸指针（`Session*`），不是 `shared_ptr`。怎么从 `this` 得到一份和外面**共用同一个计数**的 `shared_ptr`？

## 4. 错误写法：`shared_ptr<Session>(this)` 另起一个控制块 {#shared-this-wrong}

```cpp
void send_request() {
    std::shared_ptr<Session> self(this);   // 错：又分配了一个新的控制块
    g_loop.push_back([self] { self->on_reply(); });
}
```

用裸指针构造 `shared_ptr` 时，它不知道这个对象已经有人管了，就新建一个控制块，计数从 1 开始。于是两个计数各数各的：时刻 3 外面那份数到 0，对象析构；回调这份还是 1，指着已经析构的对象；时刻 5 它也数到 0，再 delete 一次。GCC 13 实测程序直接 abort（`munmap_chunk(): invalid pointer`），ASan 报 bad-free。

## 5. 正确写法：继承 `enable_shared_from_this`，调 `shared_from_this()` {#shared-from-this-right}

```cpp
std::vector<std::function<void()>> g_loop;     // 假装是事件循环：登记的回调先存起来，回包到了再调用

struct Session : std::enable_shared_from_this<Session> {
    int id = 7;
    void on_reply() { std::printf("reply on session %d\n", id); }
    void send_request() {
        // ……把请求发出去……
        auto self = shared_from_this();        // 计数 +1，和外面那份共用控制块
        g_loop.push_back([self] { self->on_reply(); });
    }
};

void demo() {
    auto s = std::make_shared<Session>();      // 时刻 1：计数 1
    s->send_request();                           // 时刻 2：计数 2
    s.reset();                                 // 时刻 3：外面丢掉自己那份，计数 1，Session 还活着
    for (auto& cb : g_loop) cb();              // 时刻 4：回包到了，打印 reply on session 7
    g_loop.clear();                            // 时刻 5：回调删掉，计数 0，这时才析构
}
```

**它怎么做到的。** `enable_shared_from_this<Session>` 里藏了一个 `std::weak_ptr<Session>` 成员。`weak_ptr` 也指向控制块，但不让计数 +1，所以不会让对象一直活着。`make_shared` 建对象时，发现它继承了 `enable_shared_from_this`，就把这个 `weak_ptr` 指向刚建好的控制块。`shared_from_this()` 只是把它升级成 `shared_ptr`：同一个控制块，计数 +1。

**这是 CRTP。** `enable_shared_from_this` 是一个往子类里注入功能的 CRTP 基类（见 [#8 的 1.3.2 节](/zh/posts/crtp-static-polymorphism/)）：子类什么都不写，就多了 `shared_from_this()`。基类里的 `weak_ptr` 成员和 `shared_from_this()` 的返回值都要写成 `Session`，所以模板参数传的是子类自己。基类如果不是模板，只能存、只能返回 `shared_ptr<基类>`，每次用都要先 `static_pointer_cast` 转回 `shared_ptr<Session>`，转错了就是未定义行为。

## 6. 三个坑 {#shared-from-this-pitfalls}

都在 GCC 13 上实测过：

- **对象必须已经归 `shared_ptr` 管。** 对栈上的对象调用，或者在构造函数里调用（这时 `make_shared` 还没填 `weak_ptr`），C++17 起抛 `std::bad_weak_ptr`，更早的标准是未定义行为。
- **必须 `public` 继承。** 私有继承时 `shared_ptr` 看不见这个基类，`weak_ptr` 没人填，同样抛 `bad_weak_ptr`。
- **对象变大，调用不免费。** 对象多一个 `weak_ptr`（两个指针，16 B；实测 `sizeof(Session)` 是 24，含对齐填充）；每次 `shared_from_this()` 都是 第 2 节那次原子加。所以它用在连接管理这种冷路径上（Asio 风格的异步服务器里，回调常写成 `[self = shared_from_this()]`），每秒要处理几百万条消息的循环里不这么做。
