---
title: "TCP：三次握手、四次挥手和 TIME_WAIT"
date: 2026-11-02
slug: "tcp-states"
description: "一条 TCP 连接从建立到关闭要经过 11 个状态，每一步由一个报文推动。握手为什么是三次：两个方向各对一次序列号，还要让发起方有机会拒绝旧的 SYN；listen、connect、accept 各对应哪一步，半连接队列和全连接队列满了会怎样。挥手为什么是四次，CLOSE_WAIT 为什么几乎总是程序忘了 close，TIME_WAIT 为什么要等 60 s、太多了怎么办，RST 什么时候出现，以及怎么用 ss 和 tcpdump 亲眼看到这些状态。"
summary: "握手是两个方向各对一次序列号，中间两步合成了 SYN+ACK；第三个报文让发起方能拒绝迟到的旧 SYN。accept 不参与握手，只从全连接队列里取走一条建好的连接。挥手时 ACK 由内核当场回，FIN 要等程序 close，所以通常是四个报文。CLOSE_WAIT 没有超时，成堆出现就是程序漏了 close；TIME_WAIT 是先关的一方替连接收尾，在 Linux 上固定 60 s，太多时靠复用连接解决。"
toc: true
math: true
group: cpplinux
weight: 110
aliases: ["/posts/tcp-states/"]
---

写过 TCP 服务的人，迟早会在 `ss` 里看到成堆的 `TIME-WAIT` 或 `CLOSE-WAIT`，或者在日志里看到 `Connection reset by peer`。这些都是连接状态留下的痕迹：一条 TCP 连接从建立到关闭要经过一串状态，每一步都由一个报文推动；`connect`、`accept`、`close`、`shutdown` 这些调用，只是让内核去发其中某个报文，或者从内核手里取走一个结果。弄清每个状态在等什么，看到这些痕迹时就知道该查哪里。

## 1. 建立连接：三次握手

### 1.1 序列号（sequence number）：两个方向各有一个起点

TCP 传的是字节流，它靠给每个字节编号来保证不丢、不乱、不重：收的一方按编号把数据排好，再用确认号（ack）告诉对方“编号 N 之前的都收到了”；发的一方没等到确认，就超时重传。编号不从 0 开始，每条连接的每个方向都随机挑一个起点，叫初始序列号（ISN，initial sequence number）。挑随机数，是为了让旧连接遗留的报文、或者别人伪造的报文，编号很难恰好落进这条新连接正在收的范围里。

两个方向的编号互不相干：客户端发出的字节从客户端的 ISN 往后编，服务端发出的从服务端的 ISN 往后编。所以建立连接要办成两件事：服务端知道客户端的起点，客户端知道服务端的起点，而且发起点的一方要确认对方真的收到了。每件事要“告诉”和“确认”两个报文，一共四个；可服务端确认客户端的起点、报上自己的起点，这两件事可以放进同一个报文（SYN+ACK），合并以后就剩三个。**三次握手就是两个方向各对一次序列号，中间两步合成了一个报文。**

SYN 和后面关闭时用的 FIN 各占一个序号，虽然它们不带数据。所以对 `seq = x` 的 SYN，确认号是 `ack = x + 1`。

### 1.2 为什么不能两次：网络里还漂着旧的 SYN

假设两次就算建好：服务端收到 SYN、回出 SYN+ACK，就认为连接已经建立，分配好缓冲区等数据。客户端早先发过一个 SYN，它在网络里绕了很久才到，客户端那边早就超时放弃、改用重发的 SYN 建好连接，甚至用完关掉了。这个旧 SYN 现在才到服务端，服务端照样建一条连接，可客户端根本不知道有这条连接，服务端的资源就一直白白挂着。

第三个报文就是把判断权交回给发起方。客户端收到 SYN+ACK，先看确认号对上的是不是自己正在连的那个 SYN：对得上，回 ACK，连接才算建立；对不上，说明是旧 SYN 引出来的，回一个 RST，服务端把这条半成品连接扔掉。服务端自己分不清一个 SYN 是新是旧，只有发起方知道。**第三个报文让发起方有机会说“这不是我现在要的连接”，同时也是服务端那个起点的确认。**

### 1.3 socket 调用对应哪一步：握手在 accept 之前就完成了

服务端和客户端的典型写法如下：

```cpp
// 服务端
int lfd = socket(AF_INET, SOCK_STREAM, 0);
int on = 1;
setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof on);  // 重启时能马上 bind，见 2.5

sockaddr_in addr{};
addr.sin_family = AF_INET;
addr.sin_port = htons(8080);
addr.sin_addr.s_addr = htonl(INADDR_ANY);
bind(lfd, reinterpret_cast<sockaddr*>(&addr), sizeof addr);
listen(lfd, 128);                    // 从这里开始，握手由内核替你完成

for (;;) {
    int cfd = accept(lfd, nullptr, nullptr);   // 只是从全连接队列里取走一条建好的
    handle(cfd);
}

// 客户端
int fd = socket(AF_INET, SOCK_STREAM, 0);
connect(fd, reinterpret_cast<sockaddr*>(&srv), sizeof srv);  // 发 SYN，收到 SYN+ACK、回完 ACK 才返回
```

`listen` 把这个 socket 变成 LISTEN 状态。从这一刻起，有人发来 SYN，内核在收包的软中断里直接回 SYN+ACK、收第三个 ACK，整个握手不需要你的线程参与。客户端的 `connect` 发出 SYN 就阻塞，收到 SYN+ACK、回出 ACK 才返回，所以一次 `connect` 大约花一个往返时间（RTT）。注意两边进入 ESTABLISHED 的时刻不一样：客户端发出第三个报文时就建立了，服务端要等这个报文到达才建立。

`accept` 不发任何报文。它只是从内核的队列里取走一条已经握手完成的连接，给它分配一个新的 fd，以后的收发都走这个新 fd，监听用的 `lfd` 继续等别人来连。**握手在 `accept` 之前就完成了，程序就算一直不调 `accept`，客户端的 `connect` 也照样成功。** 下图是一条连接从建立到关闭的完整时间线，左右两边写的是各自的状态和那一刻的调用：

<svg viewBox="0 0 760 640" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="一条 TCP 连接的时间线：客户端 connect 发 SYN 进入 SYN_SENT，服务端回 SYN+ACK 进入 SYN_RCVD，客户端回 ACK 后两边 ESTABLISHED；客户端先 close 发 FIN 进入 FIN_WAIT_1，服务端回 ACK 进入 CLOSE_WAIT，客户端进入 FIN_WAIT_2；服务端 close 发 FIN 进入 LAST_ACK，客户端回 ACK 进入 TIME_WAIT，等 60 秒后关闭" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .tc0bg   { fill: #fbfaf7; }
    .tc0ttl  { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .tc0st   { fill: #8a4b2f; font-size: 12.5px; font-weight: 700; }
    .tc0mut  { fill: #6b6558; font-size: 11.5px; }
    .tc0lab  { fill: #1c1b18; font-size: 12px; }
    .tc0ink  { fill: #1c1b18; font-size: 12.5px; }
    .tc0ax   { stroke: #8c8577; stroke-width: 1.2; fill: none; }
    .tc0h    { stroke: #4f7fb0; stroke-width: 1.6; fill: none; }
    .tc0f    { stroke: #c06a45; stroke-width: 1.6; fill: none; }
    .tc0hh   { fill: #4f7fb0; }
    .tc0fh   { fill: #c06a45; }
    .tc0band { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1; }
    .tc0tw   { stroke: #c98a76; stroke-width: 6; stroke-linecap: round; fill: none; opacity: .55; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0ttl, :root:is([data-theme="dark"], [data-theme="black"]) .tc0lab, :root:is([data-theme="dark"], [data-theme="black"]) .tc0ink { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0st { fill: #e0a07e; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0ax { stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0h { stroke: #7fa8d6; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0f { stroke: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0hh { fill: #7fa8d6; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0fh { fill: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0band { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc0tw { stroke: #e08a70; }
  </style>
  <defs>
    <marker id="tc0mh" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tc0hh"/></marker>
    <marker id="tc0mf" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tc0fh"/></marker>
  </defs>
  <rect class="tc0bg" x="0" y="0" width="760" height="640" rx="10"/>
  <text class="tc0ttl" x="250" y="34" text-anchor="middle">客户端</text>
  <text class="tc0ttl" x="510" y="34" text-anchor="middle">服务端</text>
  <path class="tc0ax" d="M250,46 L250,590"/>
  <path class="tc0ax" d="M510,46 L510,550"/>
  <text class="tc0st" x="522" y="72">LISTEN</text>
  <text class="tc0mut" x="522" y="90">listen() 之后，等别人来连</text>
  <text class="tc0st" x="238" y="106" text-anchor="end">SYN_SENT</text>
  <text class="tc0mut" x="238" y="124" text-anchor="end">connect()：发 SYN，阻塞</text>
  <path class="tc0h" d="M250,112 L508,146" marker-end="url(#tc0mh)"/>
  <text class="tc0lab" transform="translate(380,129) rotate(7.45)" y="-6" text-anchor="middle">SYN  seq = x</text>
  <text class="tc0st" x="522" y="150">SYN_RCVD</text>
  <text class="tc0mut" x="522" y="168">放进半连接队列</text>
  <path class="tc0h" d="M510,156 L252,190" marker-end="url(#tc0mh)"/>
  <text class="tc0lab" transform="translate(380,173) rotate(-7.45)" y="-6" text-anchor="middle">SYN+ACK  seq = y, ack = x+1</text>
  <text class="tc0st" x="238" y="194" text-anchor="end">ESTABLISHED</text>
  <text class="tc0mut" x="238" y="212" text-anchor="end">connect() 返回</text>
  <path class="tc0h" d="M250,200 L508,234" marker-end="url(#tc0mh)"/>
  <text class="tc0lab" transform="translate(380,217) rotate(7.45)" y="-6" text-anchor="middle">ACK  ack = y+1</text>
  <text class="tc0st" x="522" y="238">ESTABLISHED</text>
  <text class="tc0mut" x="522" y="256">移进全连接队列</text>
  <text class="tc0mut" x="522" y="274">accept() 取走它，返回新 fd</text>
  <rect class="tc0band" x="170" y="290" width="420" height="32" rx="6"/>
  <text class="tc0ink" x="380" y="311" text-anchor="middle">两边收发数据</text>
  <text class="tc0st" x="238" y="344" text-anchor="end">FIN_WAIT_1</text>
  <text class="tc0mut" x="238" y="362" text-anchor="end">close()：发 FIN</text>
  <path class="tc0f" d="M250,346 L508,380" marker-end="url(#tc0mf)"/>
  <text class="tc0lab" transform="translate(380,363) rotate(7.45)" y="-6" text-anchor="middle">FIN  seq = u</text>
  <text class="tc0st" x="522" y="384">CLOSE_WAIT</text>
  <text class="tc0mut" x="522" y="402">内核回 ACK；read() 返回 0</text>
  <path class="tc0f" d="M510,390 L252,424" marker-end="url(#tc0mf)"/>
  <text class="tc0lab" transform="translate(380,407) rotate(-7.45)" y="-6" text-anchor="middle">ACK  ack = u+1</text>
  <text class="tc0mut" x="522" y="426">这段时间还能接着发数据</text>
  <text class="tc0st" x="238" y="428" text-anchor="end">FIN_WAIT_2</text>
  <text class="tc0mut" x="238" y="446" text-anchor="end">只等对方的 FIN</text>
  <text class="tc0st" x="522" y="466">LAST_ACK</text>
  <text class="tc0mut" x="522" y="484">close()：发 FIN</text>
  <path class="tc0f" d="M510,468 L252,502" marker-end="url(#tc0mf)"/>
  <text class="tc0lab" transform="translate(380,485) rotate(-7.45)" y="-6" text-anchor="middle">FIN  seq = v</text>
  <text class="tc0st" x="238" y="506" text-anchor="end">TIME_WAIT</text>
  <text class="tc0mut" x="238" y="524" text-anchor="end">回 ACK，再等 60 s</text>
  <path class="tc0f" d="M250,508 L508,542" marker-end="url(#tc0mf)"/>
  <text class="tc0lab" transform="translate(380,525) rotate(7.45)" y="-6" text-anchor="middle">ACK  ack = v+1</text>
  <text class="tc0st" x="522" y="546">CLOSED</text>
  <path class="tc0tw" d="M250,514 L250,580"/>
  <text class="tc0st" x="238" y="594" text-anchor="end">CLOSED</text>
  <text class="tc0mut" x="20" y="624">蓝线 = 握手，橙线 = 挥手，粗红条 = TIME_WAIT。SYN 和 FIN 各占一个序号，所以确认号是 x+1、u+1。</text>
</svg>

### 1.4 两个队列：半连接队列和全连接队列（backlog）

服务端回了 SYN+ACK、还在等第三个报文的连接，放在半连接队列（SYN 队列）里，状态是 SYN_RCVD（`ss` 里显示成 `SYN-RECV`）。第三个报文到了，连接建好，挪进全连接队列（accept 队列），等程序 `accept` 取走。`listen` 的第二个参数 backlog 限制的是全连接队列的长度，实际上限是它和 `net.core.somaxconn` 中较小的那个；`somaxconn` 在 5.4 以后的内核默认是 4096，更早是 128。

全连接队列满了，说明程序 `accept` 得比连接来得慢，通常是处理线程卡住了。这时 Linux 默认不回 RST，而是把第三个 ACK 直接丢掉，新来的 SYN 也丢掉。客户端那边早已 ESTABLISHED，可能已经把请求发出去了，服务端却当这条连接还没建好，过一会儿重发 SYN+ACK，等队列有了空位才接受它。于是客户端看到的是请求莫名其妙慢了几秒，甚至超时，日志里却没有任何错误。把 `net.ipv4.tcp_abort_on_overflow` 设成 1，内核才改成直接回 RST，客户端立刻收到 `connection reset`。**队列满是 `accept` 跟不上的信号，该查的是程序为什么取得慢；调大 backlog 只是让连接多排一会儿。** 4.1 节的 `ss -lnt` 能直接看到这个队列有多满。

### 1.5 SYN 洪泛（SYN flood）：用假 SYN 塞满半连接队列

攻击者用伪造的源地址大量发 SYN，自己从不回第三个报文。每个 SYN 都在半连接队列里占一项，服务端还要把 SYN+ACK 重发几次（默认 5 次，前后约 1 分钟）才放弃，所以队列很快被占满，正常用户的 SYN 就进不来了。

Linux 的对策是 SYN cookie（`net.ipv4.tcp_syncookies`，默认值 1：队列满了才启用）。启用以后，内核不再为这个 SYN 在队列里留一项，而是把这条连接的关键信息（四元组的哈希、时间片、MSS）编码进自己挑的那个起始序号，随 SYN+ACK 发出去。真客户端回第三个报文时，确认号就是这个序号加 1，内核从里面解出信息、校验通过才建连接；伪造的源地址收不到 SYN+ACK，也就不会回，服务端没为它花一点内存。**SYN cookie 把“记住半成品连接”的状态塞进了序列号，让对方原样带回来，服务端就不用存。** 代价是序号里只装得下少数几位：SYN 里的窗口扩大、SACK 这些选项要靠 TCP 时间戳带回，没开时间戳就丢了。

## 2. 关闭连接：四次挥手

### 2.1 FIN：只表示“我不再发了”

TCP 连接是两条方向相反的字节流，关闭时也是两条分开关。一方调 `close`，内核把发送缓冲区里剩下的数据发完，再发一个 FIN，意思是“我这个方向的数据发完了”。对方内核回 ACK；对方程序下一次 `read` 读到 0，就知道对端不会再发了（EOF）。另一个方向这时还开着，对方可以继续发，直到它也调 `close`、发出自己的 FIN、被确认。两个方向各一个 FIN、各一个 ACK，就是四次挥手。

握手能把中间两步合成一个 SYN+ACK，是因为服务端回这两样都不用等程序，内核当场就能一起发。挥手时，收到 FIN 的一方内核立刻回 ACK，可自己的 FIN 要等程序调 `close` 才发，中间隔多久由程序决定，可能几微秒，也可能几分钟。**ACK 由内核当场回，FIN 要等程序 `close`，两件事的时间对不上，所以通常是四个报文。** 被动方如果收到 FIN 后马上就 `close`，内核可以把还没发出的 ACK 和 FIN 合成一个报文，这时抓包看到的就只有三个。

先调 `close` 的一方叫主动关闭方。它发出 FIN 进入 FIN_WAIT_1，收到 ACK 进入 FIN_WAIT_2，收到对方的 FIN、回出 ACK 进入 TIME_WAIT，等 60 s 才彻底关闭。被动关闭方收到 FIN 进入 CLOSE_WAIT，程序调 `close` 发出 FIN 后进入 LAST_ACK，收到最后的 ACK 就关闭。1.3 那张时间线的下半段画的就是这个过程。

### 2.2 半关闭（half-close）：shutdown 只关一个方向

`close` 关的是 fd，`shutdown` 关的是连接的一个方向。`shutdown(fd, SHUT_WR)` 立刻发 FIN，告诉对方“我发完了”，但 fd 还在，还能继续读对方的回复。典型的用法是客户端把整个请求发完，用 `SHUT_WR` 告诉服务端“请求就这些”，服务端读到 EOF 才开始处理，把结果写回来，再关自己那一边：

```cpp
write_all(fd, req.data(), req.size());  // 循环 send，直到全部发完
shutdown(fd, SHUT_WR);                   // 发 FIN：我发完了；fd 还能读

std::string reply;
char buf[4096];
ssize_t r;
while ((r = recv(fd, buf, sizeof buf, 0)) > 0)   // 读到 0：对方也发完了
    reply.append(buf, r);
close(fd);                               // shutdown 不释放 fd，最后还得 close
```

两者的另一个差别，出现在多个 fd 指向同一个 socket 时，比如 `fork` 以后父子进程各有一个，或者 `dup` 出来的。`close` 只是把这个 socket 的引用计数减 1，减到 0 才真正发 FIN；`shutdown` 不看引用计数，直接作用在连接上，别的进程手里的 fd 也跟着不能写了。所以“每来一个连接 `fork` 一个子进程”的服务器，父进程要是忘了 `close` 自己那份 `cfd`，子进程 `close` 以后计数还剩 1，FIN 发不出去，客户端会一直等。**想让对方收到 FIN，要么指向这个 socket 的 fd 全都 `close` 掉，要么用 `shutdown`。** `fork` 之后父子进程共享哪些东西，在[进程、线程和 fork](/zh/ref/process-thread-fork/)那篇里讲。

### 2.3 CLOSE_WAIT：对方关了，你还没 close

被动方收到 FIN 进入 CLOSE_WAIT，要一直待到程序调 `close` 才离开。内核不知道程序还要不要往这条连接上写，所以没给这个状态设超时：程序不 `close`，它就永远停在那里。因此 `ss` 里成堆的 CLOSE_WAIT，几乎总是程序的 bug，`read` 返回 0 时没有 `close`，或者某个出错分支漏了 `close`，fd 就泄漏了。连接越积越多，最后进程的 fd 用完，`accept` 开始报 `EMFILE`，新连接一个都接不进来。

```cpp
ssize_t r = recv(fd, buf, sizeof buf, 0);
if (r == 0) {
    // 对端发了 FIN。漏了这一行，这条连接就一直停在 CLOSE_WAIT
    close(fd);
}
```

对面那一方这时停在 FIN_WAIT_2，等你的 FIN。它如果是用 `close` 关的，已经不能再读，内核不会陪它无限等，过了 `net.ipv4.tcp_fin_timeout`（默认 60 s）就直接释放；如果是 `shutdown(SHUT_WR)` 半关的，它还要读你的数据，就一直等着。**CLOSE_WAIT 多，查自己的代码；TIME_WAIT 多，多半是正常现象。** 用 epoll 写的服务端，这个 `close` 通常就写在 `recv` 返回 0 的分支里，[epoll](/zh/ref/epoll-internals/) 那篇的 `drain()` 就是这么做的。

### 2.4 TIME_WAIT：先 close 的一方最后要等 60 s

主动关闭方收到对方的 FIN、回出最后一个 ACK 以后，不马上释放连接，而是进入 TIME_WAIT，等 2MSL。MSL（maximum segment lifetime）是一个报文在网络里最多能存活多久，RFC 793 定的是 2 分钟；Linux 不按 MSL 算，直接把 TIME_WAIT 写死成 60 s（内核里的 `TCP_TIMEWAIT_LEN`），没有 sysctl 能改它。

要等，有两个原因。第一个是最后那个 ACK 可能丢：丢了，对方收不到确认，会重发 FIN；如果这边已经把连接删了，收到这个 FIN 只能回 RST，对方的关闭就以一个错误告终。留在 TIME_WAIT，这边还能再回一次 ACK。第二个是迟到的旧报文：同一个四元组（两边的 IP 和端口）马上又建了一条新连接，旧连接在网络里迟到的报文可能恰好落进新连接的序号范围，被当成新数据收下。等够两倍的报文寿命，一来一回两个方向上的旧报文都已经在网络里消失了。**TIME_WAIT 是在替已经关掉的连接收尾：补发可能丢掉的最后一个 ACK，并挡住它迟到的旧报文。**

谁进 TIME_WAIT 只看谁先发 FIN，和谁是客户端无关；HTTP/1.0 那种由服务端先关的短连接，TIME_WAIT 就堆在服务端。一个 TIME_WAIT 的代价并不大：内核只留一个精简的结构，一两百字节，它不占 fd，程序也看不到它。

### 2.5 TIME_WAIT 太多：端口用完和 bind 失败

TIME_WAIT 本身不贵，麻烦在它占着那个四元组。有两种情况会撞上。

一种在客户端，或者代理（代理对后端也是客户端）：每次请求都新建一条短连接，用完自己先 `close`，每条都留下一个 TIME_WAIT。连同一个服务端 IP 和端口时，四元组里只有本地端口能变，而临时端口的范围默认是 32768–60999（`net.ipv4.ip_local_port_range`），一共 28232 个。每个端口要在 TIME_WAIT 里占 60 s，所以对同一个目标，新建连接的速度有个上限：

$$
\text{每秒新建连接上限} \approx \frac{\text{临时端口个数}}{\text{TIME\_WAIT 时长}} = \frac{28232}{60\ \text{s}} \approx 470\ \text{个/s}
$$

超过这个速度，端口很快用光，`connect` 开始报 `EADDRNOTAVAIL`。最根本的办法是复用连接：HTTP keep-alive、连接池，让一条连接跑很多个请求，TIME_WAIT 自然就少了。其次可以让服务端先关。再不行，打开 `net.ipv4.tcp_tw_reuse = 1`，允许新的 `connect` 直接复用一个还在 TIME_WAIT 的四元组；它靠 TCP 时间戳判断报文的新旧，所以两边都要开时间戳，默认值 2 只对本机回环地址生效。以前还有个 `tcp_tw_recycle`，会把 NAT 后面多台机器发来的连接误判成旧报文丢掉，4.12 内核已经把它删了。

另一种在服务端重启：老进程退出时主动关掉了一批连接，这些连接停在 TIME_WAIT，占着监听的那个端口，新进程 `bind` 同一个端口就报 `EADDRINUSE`。在 `bind` 之前给监听 socket 设上 `SO_REUSEADDR`，就能绑上，1.3 节代码里的那一行就是做这个的。**`SO_REUSEADDR` 解决的是服务端重启 bind 不上；客户端端口耗尽要靠复用连接和 `tcp_tw_reuse`，这是两件事。**

## 3. 全部状态和 RST

### 3.1 状态图：11 个状态，两条主路

把前面两节的状态画在一起，就是下面这张图。每条线上写的是“收到什么报文、发出什么报文”，程序的调用只出现在几处：`listen`、`connect`、`close`（或 `shutdown`）。

<svg viewBox="0 0 760 650" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="TCP 状态图：主动方 CLOSED 经 connect 到 SYN_SENT，收 SYN+ACK 到 ESTABLISHED，close 后经 FIN_WAIT_1、FIN_WAIT_2 到 TIME_WAIT，等 60 秒回到 CLOSED；被动方 CLOSED 经 listen 到 LISTEN，收 SYN 到 SYN_RCVD，收 ACK 到 ESTABLISHED，收 FIN 到 CLOSE_WAIT，close 后到 LAST_ACK，收 ACK 回到 CLOSED；两边同时 close 时经 CLOSING 到 TIME_WAIT" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .tc1bg  { fill: #fbfaf7; }
    .tc1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .tc1box { fill: #ffffff; stroke: #8c8577; stroke-width: 1.3; }
    .tc1est { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .tc1hot { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.3; }
    .tc1nm  { fill: #1c1b18; font-size: 12.5px; font-weight: 700; }
    .tc1a   { stroke: #c06a45; stroke-width: 1.6; fill: none; }
    .tc1p   { stroke: #5f8a32; stroke-width: 1.6; fill: none; stroke-dasharray: 5 4; }
    .tc1s   { stroke: #8c8577; stroke-width: 1.4; fill: none; }
    .tc1ah  { fill: #c06a45; }
    .tc1ph  { fill: #5f8a32; }
    .tc1sh  { fill: #8c8577; }
    .tc1la  { fill: #9a4f2e; font-size: 11.5px; }
    .tc1lp  { fill: #4f6b2a; font-size: 11.5px; }
    .tc1ls  { fill: #6b6558; font-size: 11.5px; }
    .tc1mut { fill: #6b6558; font-size: 11.5px; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1ttl, :root:is([data-theme="dark"], [data-theme="black"]) .tc1nm { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1box { fill: #23262c; stroke: #6f685c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1est { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1hot { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1a { stroke: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1p { stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1s { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1ah { fill: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1ph { fill: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1sh { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1la { fill: #e0a07e; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1lp { fill: #a9c97a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .tc1ls, :root:is([data-theme="dark"], [data-theme="black"]) .tc1mut { fill: #a19caf; }
  </style>
  <defs>
    <marker id="tc1ma" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tc1ah"/></marker>
    <marker id="tc1mp" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tc1ph"/></marker>
    <marker id="tc1ms" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="tc1sh"/></marker>
  </defs>
  <rect class="tc1bg" x="0" y="0" width="760" height="650" rx="10"/>
  <text class="tc1ttl" x="20" y="30">TCP 状态图</text>
  <path class="tc1p" d="M318,50 L200,50 L200,113" marker-end="url(#tc1mp)"/>
  <text class="tc1lp" x="208" y="88">listen()</text>
  <path class="tc1a" d="M442,50 L600,50 L600,113" marker-end="url(#tc1ma)"/>
  <text class="tc1la" x="608" y="82">connect()</text>
  <text class="tc1la" x="608" y="98">发 SYN</text>
  <path class="tc1p" d="M200,145 L200,203" marker-end="url(#tc1mp)"/>
  <text class="tc1lp" x="208" y="172">收 SYN</text>
  <text class="tc1lp" x="208" y="188">回 SYN+ACK</text>
  <path class="tc1a" d="M600,145 L600,300 L452,300" marker-end="url(#tc1ma)"/>
  <text class="tc1la" x="608" y="212">收 SYN+ACK</text>
  <text class="tc1la" x="608" y="228">回 ACK</text>
  <path class="tc1p" d="M200,235 L200,300 L308,300" marker-end="url(#tc1mp)"/>
  <text class="tc1lp" x="208" y="268">收 ACK</text>
  <path class="tc1a" d="M340,315 L340,345 L160,345 L160,373" marker-end="url(#tc1ma)"/>
  <text class="tc1la" x="172" y="338">close()：发 FIN</text>
  <path class="tc1p" d="M420,315 L420,345 L600,345 L600,373" marker-end="url(#tc1mp)"/>
  <text class="tc1lp" x="432" y="338">收 FIN，回 ACK</text>
  <path class="tc1a" d="M160,405 L160,463" marker-end="url(#tc1ma)"/>
  <text class="tc1la" x="168" y="438">收 ACK</text>
  <path class="tc1s" d="M222,390 L380,390 L380,463" marker-end="url(#tc1ms)"/>
  <text class="tc1ls" x="388" y="420">两边同时 close：</text>
  <text class="tc1ls" x="388" y="436">收 FIN，回 ACK</text>
  <path class="tc1p" d="M600,405 L600,463" marker-end="url(#tc1mp)"/>
  <text class="tc1lp" x="608" y="438">close()：发 FIN</text>
  <path class="tc1a" d="M160,495 L160,548" marker-end="url(#tc1ma)"/>
  <text class="tc1la" x="152" y="525" text-anchor="end">收 FIN，回 ACK</text>
  <path class="tc1s" d="M380,495 L380,530 L200,530 L200,548" marker-end="url(#tc1ms)"/>
  <text class="tc1ls" x="290" y="524">收 ACK</text>
  <path class="tc1p" d="M600,495 L600,548" marker-end="url(#tc1mp)"/>
  <text class="tc1lp" x="608" y="525">收 ACK</text>
  <path class="tc1a" d="M222,565 L536,565" marker-end="url(#tc1ma)"/>
  <text class="tc1la" x="238" y="558">等 2MSL（Linux 上固定 60 s）</text>
  <rect class="tc1box" x="318" y="35" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="380" y="55" text-anchor="middle">CLOSED</text>
  <rect class="tc1box" x="138" y="115" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="200" y="135" text-anchor="middle">LISTEN</text>
  <rect class="tc1box" x="538" y="115" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="600" y="135" text-anchor="middle">SYN_SENT</text>
  <rect class="tc1box" x="138" y="205" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="200" y="225" text-anchor="middle">SYN_RCVD</text>
  <rect class="tc1est" x="310" y="285" width="140" height="30" rx="6"/>
  <text class="tc1nm" x="380" y="305" text-anchor="middle">ESTABLISHED</text>
  <rect class="tc1box" x="98" y="375" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="160" y="395" text-anchor="middle">FIN_WAIT_1</text>
  <rect class="tc1hot" x="538" y="375" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="600" y="395" text-anchor="middle">CLOSE_WAIT</text>
  <rect class="tc1box" x="98" y="465" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="160" y="485" text-anchor="middle">FIN_WAIT_2</text>
  <rect class="tc1box" x="318" y="465" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="380" y="485" text-anchor="middle">CLOSING</text>
  <rect class="tc1box" x="538" y="465" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="600" y="485" text-anchor="middle">LAST_ACK</text>
  <rect class="tc1hot" x="98" y="550" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="160" y="570" text-anchor="middle">TIME_WAIT</text>
  <rect class="tc1box" x="538" y="550" width="124" height="30" rx="6"/>
  <text class="tc1nm" x="600" y="570" text-anchor="middle">CLOSED</text>
  <text class="tc1mut" x="20" y="612">橙色实线 = 主动的一方（先 connect、先 close）；绿色虚线 = 被动的一方（listen、后 close）；</text>
  <text class="tc1mut" x="20" y="630">灰线 = 两边同时 close。红底的两个状态，是最常在 ss 里成堆出现的。</text>
</svg>

橙线和绿线是两条主路，一条连接的两端各走一条。灰线是少见的同时关闭：两边几乎同时 `close`，各自发了 FIN、正等着 ACK，却先收到了对方的 FIN，于是进入 CLOSING，等收到 ACK 再进 TIME_WAIT，这时两边都会经过 TIME_WAIT。图上没画超时和 RST 的边：比如 SYN_SENT 一直收不到回应，内核重发 SYN（`net.ipv4.tcp_syn_retries` 默认 6 次，前后约 2 分钟）后放弃，`connect` 返回 `ETIMEDOUT`；在多数状态下收到 RST，连接都直接回到 CLOSED。**连接走到最后，只有 CLOSE_WAIT 必须等你的程序动手，其余状态都会被报文或计时器推着走完。**

### 3.2 RST（reset）：不走挥手，直接作废

RST 的意思是“这条连接不存在，或者出错了，立刻作废”。收到的一方不回任何报文，直接把连接删掉，正阻塞在上面的读写调用返回错误。它不走挥手，所以也没有 TIME_WAIT。常见的来源有这几种：

| 情况 | 谁发 RST | 你的程序看到什么 |
|---|---|---|
| `connect` 一个没人监听的端口 | 对方内核 | `connect` 立刻失败，`ECONNREFUSED` |
| 接收缓冲区里还有没读的数据，就 `close` | 你这边的内核，用 RST 代替 FIN | 对方下一次 `read` 得到 `ECONNRESET`，而不是 0 |
| 对方已经彻底关掉，你还往里写 | 对方内核 | 你第一次写成功；之后的 `read` 得到 `ECONNRESET`，再写返回 `EPIPE`，并收到 `SIGPIPE` |
| 设了 `SO_LINGER {1, 0}` 再 `close` | 你这边的内核 | 对方 `ECONNRESET`；你这边跳过 TIME_WAIT |

第二行是在告诉对方：你发过来的东西我没读就扔了，别当它们已经被处理了。第三行里的 `SIGPIPE` 默认会直接杀掉进程，一个客户端断开就能把整个服务端带走，所以服务端通常在启动时 `signal(SIGPIPE, SIG_IGN)`，或者每次 `send` 带上 `MSG_NOSIGNAL`，改成只返回 `EPIPE`。日志里常见的 `Connection reset by peer`，多半就是第二、三行这两种情况。

第四行常被当成消灭 TIME_WAIT 的办法：

```cpp
linger lg{1, 0};   // l_onoff = 1，l_linger = 0
setsockopt(fd, SOL_SOCKET, SO_LINGER, &lg, sizeof lg);
close(fd);         // 发 RST，发送缓冲区里没发完的数据也一起丢掉
```

它确实不留 TIME_WAIT，但等于同时放弃了 2.4 节那两层保护，没发完的数据也丢了，对方还会看到一个 reset 错误。**`SO_LINGER {1, 0}` 是“出错了，直接作废”的工具，不是消除 TIME_WAIT 的正常手段。**

## 4. 亲眼看到

### 4.1 ss：看状态和队列

`ss` 直接读内核里的 socket 表，比老的 `netstat` 快，参数也差不多：

```bash
ss -tan                              # 所有 TCP 连接和它们的状态
ss -tan state time-wait | wc -l      # 数一数 TIME_WAIT（多一行表头）
ss -tanp state close-wait            # 谁的 CLOSE_WAIT：最后一列是进程名和 pid
ss -s                                # 各个状态的总数
ss -lnt                              # 只看监听 socket
nstat -az TcpExtListenOverflows      # 全连接队列满、丢掉第三个 ACK 的累计次数
```

`ss -lnt` 的输出里，`Recv-Q` 和 `Send-Q` 两列在监听 socket 上有专门的意思：`Recv-Q` 是全连接队列里此刻有几条连接在等 `accept`，`Send-Q` 是这个队列的上限，也就是 1.4 节说的那个较小值。**`Recv-Q` 长期贴着 `Send-Q`，就是 `accept` 跟不上了**：

```text
State   Recv-Q  Send-Q   Local Address:Port   Peer Address:Port
LISTEN  0       4096           0.0.0.0:8080        0.0.0.0:*
```

在普通连接上，这两列变回字节数：`Recv-Q` 是接收缓冲区里还没被 `read` 走的，`Send-Q` 是发送缓冲区里还没被对方确认的。这两块缓冲区在 [IO 地图](/maps/io-map.zh.html#recv)里是 TCP/IP 协议栈上面那个“socket 缓冲区”框，`Send-Q` 一直很大，说明对方读得慢或者网络慢。

### 4.2 tcpdump：看握手和挥手的报文

在本机开一个监听，再连上去、断开，同时抓回环网卡上的包：

```bash
sudo tcpdump -i lo -nn 'tcp port 8080'   # 一个终端抓包
nc -l 8080                               # 另一个终端：监听
nc 127.0.0.1 8080                        # 第三个终端：连上去，再按 Ctrl+C 断开
```

输出大致是下面这样，序号每次都不一样，后面的字段这里省掉了。`Flags` 里 `S` 是 SYN，`.` 是 ACK，`F` 是 FIN，`R` 是 RST，`P` 是 PUSH（带了数据）；握手以后，tcpdump 默认把序号显示成相对第一个序号的偏移，所以会看到 `ack 1`、`ack 2` 这样的小数字：

```text
127.0.0.1.52344 > 127.0.0.1.8080: Flags [S],  seq 1928374650, ...
127.0.0.1.8080 > 127.0.0.1.52344: Flags [S.], seq 3141592653, ack 1928374651, ...
127.0.0.1.52344 > 127.0.0.1.8080: Flags [.],  ack 1, ...
127.0.0.1.52344 > 127.0.0.1.8080: Flags [F.], seq 1, ack 1, ...
127.0.0.1.8080 > 127.0.0.1.52344: Flags [F.], seq 1, ack 2, ...
127.0.0.1.52344 > 127.0.0.1.8080: Flags [.],  ack 2, ...
```

前三行是三次握手。后三行是挥手，这次只抓到三个报文：`nc -l` 读到 EOF 就退出，被动方的 ACK 和它自己的 FIN 合成了一个 `[F.]`，正是 2.1 节说的那种情况；被动方关得慢一点，就会看到 ACK 和 FIN 分成两个报文。断开以后马上 `ss -tan | grep 8080`，就能看到先断开的客户端那一头停在 `TIME-WAIT`，一分钟后消失。整个过程在 [C++ 与 Linux 总图](/zh/ref/cpp-linux/#net)的 IO 地图上，对应网卡收包、经协议栈进 socket 缓冲区的那条路。
