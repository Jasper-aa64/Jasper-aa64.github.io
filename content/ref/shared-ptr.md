---
title: "shared_ptr and enable_shared_from_this"
date: 2026-11-02
slug: "shared-ptr"
description: "A shared_ptr is the object plus a control block holding the count; copying one copies two pointers and adds 1 to the count, which is an atomic operation once there are threads. To get your own shared_ptr inside a member function, don't start a second control block with shared_ptr(this); inherit enable_shared_from_this and call shared_from_this()."
summary: "The count lives in the control block and make_shared allocates once; to keep yourself alive from a member function, shared_from_this() shares the outside control block, while a second control block destroys the object twice."
toc: true
group: cpplinux
weight: 111
aliases: ["/posts/shared-ptr/"]
---

## 1. What `shared_ptr` Is: the Object Plus a Control Block Holding the Count {#shared-ptr}

`std::shared_ptr<T>` lets several places own one object together: anyone can hold a copy, and the object is destroyed when the last copy goes away. It does this with a reference count. The count isn't stored in the object but in a separate piece of memory called the **control block**.

- `std::make_shared<T>()` allocates once, with the object and the control block side by side.
- Every copy of a `shared_ptr` adds 1 to the count, every destroyed one subtracts 1, and at 0 the object is destroyed.
- A `shared_ptr` itself is two pointers, one to the object and one to the control block: `sizeof` is 16 B.

<svg viewBox="0 0 760 304" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="make_shared allocates once, object next to the control block; shared_ptr(new T) allocates twice and the control block holds a pointer to the object. Each shared_ptr stores an object pointer and a control-block pointer." style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
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
  <text class="sp0ink" x="103" y="71" text-anchor="middle">object ptr</text>
  <rect class="sp0p" x="158" y="52" width="110" height="30"/>
  <text class="sp0ink" x="213" y="71" text-anchor="middle">ctrl block ptr</text>
  <text class="sp0mut" x="26" y="227">p2</text>
  <rect class="sp0p" x="48" y="208" width="110" height="30"/>
  <text class="sp0ink" x="103" y="227" text-anchor="middle">object ptr</text>
  <rect class="sp0p" x="158" y="208" width="110" height="30"/>
  <text class="sp0ink" x="213" y="227" text-anchor="middle">ctrl block ptr</text>
  <rect class="sp0box" x="42" y="114" width="312" height="62" rx="6"/>
  <rect class="sp0t" x="48" y="120" width="110" height="50"/>
  <text class="sp0ink" x="103" y="149" text-anchor="middle">T object</text>
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
  <text class="sp0mut" x="24" y="266">One allocation: object next to control block</text>
  <text class="sp0ttl" x="408" y="32">std::shared_ptr&lt;T&gt;(new T)</text>
  <text class="sp0mut" x="410" y="71">p1</text>
  <rect class="sp0p" x="432" y="52" width="110" height="30"/>
  <text class="sp0ink" x="487" y="71" text-anchor="middle">object ptr</text>
  <rect class="sp0p" x="542" y="52" width="110" height="30"/>
  <text class="sp0ink" x="597" y="71" text-anchor="middle">ctrl block ptr</text>
  <text class="sp0mut" x="410" y="227">p2</text>
  <rect class="sp0p" x="432" y="208" width="110" height="30"/>
  <text class="sp0ink" x="487" y="227" text-anchor="middle">object ptr</text>
  <rect class="sp0p" x="542" y="208" width="110" height="30"/>
  <text class="sp0ink" x="597" y="227" text-anchor="middle">ctrl block ptr</text>
  <rect class="sp0t" x="432" y="120" width="100" height="50"/>
  <text class="sp0ink" x="482" y="149" text-anchor="middle">T object</text>
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
  <text class="sp0mut" x="408" y="266">Two allocations: control block also stores a T*</text>
  <text class="sp0mut" x="24" y="292">use_count sits at offset 8 of the control block in both: what addl $1, 8(%rdx) in section 2 adds to.</text>
</svg>

The two spellings differ in how many allocations they make. `make_shared` calls `operator new` once, so the object and the control block share one block of memory: one allocation fewer, and the count you touch along with the object is likely on a neighboring cache line. The cost shows up on release: when `use_count` reaches 0 the object is destroyed as usual, but its bytes are attached to the control block and can only be freed once `weak_count` also reaches 0 (the last `weak_ptr` is gone). **With a large object and a long-lived `weak_ptr`, `make_shared` keeps that memory around**, so there `shared_ptr<T>(new T)` allocates separately and the object's memory goes back as soon as it is destroyed.

## 2. What It Compiles To: a Copy = Copy Two Pointers + Add 1 to the Count {#shared-ptr-asm}

```cpp
std::shared_ptr<S> copy_sp(const std::shared_ptr<S>& p) { return p; }
```

```text
movdqu  (%rsi), %xmm0                    # read 16 B at once: object pointer + control-block pointer
movups  %xmm0, (%rdi)                    # write them into the new shared_ptr
movq    8(%rdi), %rdx                    # control-block address
testq   %rdx, %rdx
je      .L12                             # null: no count to bump
cmpb    $0, __libc_single_threaded(%rip) # is the process single-threaded?
je      .L14
addl    $1, 8(%rdx)                      # single-threaded: plain add
ret
.L14:
lock addl $1, 8(%rdx)                    # multi-threaded: atomic add
```

`__libc_single_threaded` is a flag maintained by glibc; it is true until the process starts a second thread. Once there are several threads, every copy (and every decrement on destruction) is a `lock` atomic operation: about 5–10 ns when no other core is competing; when several cores copy `shared_ptr`s to the same object at once, the cache line holding the count bounces between cores (cache-line ping-pong), and one operation takes tens to hundreds of ns. So don't pass `shared_ptr` by value in frequently called functions: if you only use the object and don't need to own it, pass `const std::shared_ptr<T>&`, or just `T&` / `T*`.

## 3. The Scenario: the Object Must Outlive the Callback {#shared-from-this-why}

A `Session` object represents one connection to a server and is managed by a `shared_ptr`. `Session::send_request()` sends a request, and the server replies a little later (say tens of µs). The program doesn't stop and wait; it first registers a function meaning "call this when the reply arrives". A function registered now and called later by someone else is a **callback**. After registering, `send_request()` returns immediately and the program moves on. What notices the reply and calls the registered callback is usually a loop that keeps spinning, called the **event loop**.

The problem is the waiting period. Before the reply arrives, some other part of the program may stop using this connection (risk control disconnects it, say) and drop its `shared_ptr`. If the callback doesn't hold its own `shared_ptr<Session>`, the count drops to 0 and the `Session` is destroyed; when the reply arrives, the callback uses a destroyed object. If the callback holds a copy, the count can't reach 0 before it runs:

| Step | What happens | Count if the callback holds nothing | Count if the callback holds a copy |
|---|---|---|---|
| 1 | `make_shared<Session>()`; the outside holds one | 1 | 1 |
| 2 | `send_request()` registers the callback | 1 | 2 |
| 3 | The outside drops its copy | 0, `Session` destroyed | 1, `Session` still alive |
| 4 | The reply arrives; the event loop calls the callback | uses a destroyed object: undefined behavior | handles the reply normally |
| 5 | The callback finishes and is removed | — | 0, destroyed only now |

The catch: the callback is registered inside the member function `send_request()`, where all you have is `this`, a raw pointer (`Session*`), not a `shared_ptr`. How do you get from `this` a `shared_ptr` that **shares the same count** as the outside one?

## 4. The Wrong Way: `shared_ptr<Session>(this)` Starts a Second Control Block {#shared-this-wrong}

```cpp
void send_request() {
    std::shared_ptr<Session> self(this);   // wrong: allocates a new control block
    g_loop.push_back([self] { self->on_reply(); });
}
```

A `shared_ptr` built from a raw pointer doesn't know the object is already owned, so it creates a new control block with the count starting at 1. Now two counts run independently: at step 3 the outside one reaches 0 and destroys the object; the callback's copy is still 1 and points at a destroyed object; at step 5 it reaches 0 too and deletes again. Measured on GCC 13, the program aborts (`munmap_chunk(): invalid pointer`), and ASan reports a bad-free.

## 5. The Right Way: Inherit `enable_shared_from_this` and Call `shared_from_this()` {#shared-from-this-right}

```cpp
std::vector<std::function<void()>> g_loop;     // a stand-in event loop: registered callbacks wait here until the reply arrives

struct Session : std::enable_shared_from_this<Session> {
    int id = 7;
    void on_reply() { std::printf("reply on session %d\n", id); }
    void send_request() {
        // ...send the request...
        auto self = shared_from_this();        // count +1, sharing the outside copy's control block
        g_loop.push_back([self] { self->on_reply(); });
    }
};

void demo() {
    auto s = std::make_shared<Session>();      // step 1: count 1
    s->send_request();                           // step 2: count 2
    s.reset();                                 // step 3: the outside drops its copy; count 1, Session alive
    for (auto& cb : g_loop) cb();              // step 4: the reply arrives; prints reply on session 7
    g_loop.clear();                            // step 5: callback removed; count 0, destroyed only now
}
```

**How it works.** `enable_shared_from_this<Session>` holds a hidden `std::weak_ptr<Session>` member. A `weak_ptr` also points at the control block but doesn't add to the count, so it doesn't keep the object alive. When `make_shared` builds an object and sees that it inherits `enable_shared_from_this`, it points that `weak_ptr` at the new control block. `shared_from_this()` just upgrades it to a `shared_ptr`: same control block, count +1.

**This is CRTP.** `enable_shared_from_this` is a CRTP base that injects a feature into the subclass (see [section 1.3.2 of #8](/posts/crtp-static-polymorphism/)): the subclass writes nothing and gains `shared_from_this()`. Both the base's `weak_ptr` member and `shared_from_this()`'s return type must say `Session`, so the template argument is the subclass itself. A non-template base could only store and return `shared_ptr<Base>`, and every use would need a `static_pointer_cast` back to `shared_ptr<Session>`; a wrong cast is undefined behavior.

## 6. Three Pitfalls {#shared-from-this-pitfalls}

All measured on GCC 13:

- **The object must already be owned by a `shared_ptr`.** On a stack object, or inside the constructor (before `make_shared` has filled the `weak_ptr`), it throws `std::bad_weak_ptr` since C++17; in older standards it is undefined behavior.
- **The inheritance must be `public`.** With private inheritance `shared_ptr` can't see the base, nobody fills the `weak_ptr`, and it throws `bad_weak_ptr` as well.
- **The object grows and the call isn't free.** The object gains a `weak_ptr` (two pointers, 16 B; measured `sizeof(Session)` is 24 including padding), and every `shared_from_this()` is the atomic add from 5.2. So it belongs on cold paths such as connection management (in Asio-style async servers the callback is typically written `[self = shared_from_this()]`), not in a loop that handles millions of messages a second.
