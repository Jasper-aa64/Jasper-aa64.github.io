---
title: "socket 编程：服务端和客户端各调哪几个函数"
date: 2026-11-02
slug: "socket-programming"
description: "一条 TCP 连接，服务端要调 socket、bind、listen、accept，客户端只要 socket 和 connect。这篇讲每个调用在内核里做了什么，sockaddr_in 和网络字节序，SO_REUSEADDR 为什么几乎每个服务端都设，再给一个完整的阻塞回显服务器和客户端。然后讲 TCP 是字节流带来的后果：read 和 write 都可能只做一部分，所以要循环、要自己分消息。最后从每连接一个进程、每连接一个线程讲到非阻塞 socket 加 epoll 的 Reactor，以及 UDP 和 Unix 域套接字在接口上的差别。"
summary: "服务端的 socket 先 bind 地址、再 listen 变成监听 socket，握手由内核完成，accept 只是从队列里取走一条建好的连接，换来一个新 fd；客户端 connect 时内核替它挑本地端口。TCP 只保证字节按序到达，不保证一次 read 拿到一条完整消息，所以读写都要循环、消息边界要协议自己定。并发从每连接一个进程或线程，走到一个线程用 epoll 等很多个非阻塞 socket，回调里绝不能阻塞。"
toc: true
group: cpplinux
topic: net
weight: 120
---

两个进程隔着网络说话，各自手里都要有一个通信的端点，这就是 socket。它在 Linux 里是一个 fd，读写用的还是 `read` 和 `write`，差别全在建立连接的那几步：服务端要先占一个地址等别人来，客户端要知道去哪儿找它。下面先把两边的调用顺序和每一步在内核里发生了什么讲清楚，再写一个能跑的回显服务器，最后看它怎么从一次服务一个客户端，变成一个线程服务几千个。

## 1. 一条 TCP 连接，两端各调哪几个函数

### 1.1 socket 是一个 fd：背后是内核里的两块缓冲区和一份协议状态 {#socket-fd}

`socket(AF_INET, SOCK_STREAM, 0)` 让内核建一个 TCP socket：一块发送缓冲区、一块接收缓冲区、一份 TCP 状态（序列号、窗口、定时器），再分一个 fd 指向它。第一个参数是地址族（`AF_INET` 是 IPv4，`AF_INET6` 是 IPv6，`AF_UNIX` 是本机），第二个参数选字节流还是数据报，第三个参数填 0 就让内核按前两个挑默认协议，字节流就是 TCP，数据报就是 UDP。

因为它是 fd，`read`、`write`、`close`、`epoll` 这些通用的文件接口都能用在它上面。`write` 把数据从用户缓冲区拷进 socket 的发送缓冲区就返回，什么时候切成段、发出去、等对方确认，都是内核的事；`read` 从接收缓冲区往外拷，缓冲区空着就睡。**所以 `write` 返回只说明数据进了本机内核，不说明对方收到了。** 刚建出来的 socket 还没有地址，也没有连接，下面几个调用就是给它补上这些。

### 1.2 服务端：socket → bind → listen → accept {#server-calls}

服务端要让别人找得到，得先占一个固定的地址。`bind` 把一个本地 IP 和端口绑到 socket 上；端口已经被别的 socket 占着，就失败，`errno` 是 `EADDRINUSE`。IP 填 `INADDR_ANY`（也就是 0.0.0.0），表示本机所有网卡上的这个端口都收；填 127.0.0.1 就只收本机发来的。

`listen` 把这个 socket 变成监听 socket：内核从此替它回应别人的握手，握手完成的连接排进一个队列。它的第二个参数 backlog 限制的就是这个已完成队列的长度。

`accept` 从这个队列里取走一条已经建好的连接，给它建一个新的 socket，返回新 fd；队列空着就睡。**三次握手在 `accept` 之前就由内核做完了，`accept` 只是取货。** 返回的新 fd 才是和这个客户端通信用的，监听 fd 留着继续收下一个。所以一个服务端同时有一个监听 fd 和很多个连接 fd，它们的本地端口都一样，内核靠对端的 IP 和端口区分是哪条连接。

每个调用对应握手和状态机的哪一步、两个队列满了会怎样，在 [TCP 状态](/zh/ref/tcp-states/) 里讲过，这里不重复。

### 1.3 客户端：socket → connect，本地地址交给内核挑 {#client-calls}

客户端一般不 `bind`。`connect` 发现 socket 还没有本地地址，就替它挑一个：IP 按路由表选出去的那块网卡的地址，端口从临时端口范围（默认 32768–60999）里拿一个空闲的。然后发 SYN，阻塞到握手完成才返回。对方没在那个端口上监听，会回 RST，`connect` 失败，`errno` 是 `ECONNREFUSED`；一直没有回应，内核重发几次 SYN 以后放弃，默认大约两分钟后返回 `ETIMEDOUT`。

`connect` 成功以后，两边对等：都用 `read`、`write` 收发，谁先 `close` 都行，`close` 让内核发 FIN。

<svg viewBox="0 0 760 452" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="服务端依次调用 socket、setsockopt、bind、listen、accept，再循环 read 和 write，最后 close；客户端调用 socket 和 connect，connect 发出的握手由服务端内核完成，连接进队列后 accept 才取走它" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .s1bg  { fill: #fbfaf7; }
    .s1sv  { fill: #e3ecf6; stroke: #7d98b8; stroke-width: 1.3; }
    .s1cl  { fill: #f3e6cf; stroke: #b99254; stroke-width: 1.3; }
    .s1io  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .s1ink { fill: #1c1b18; font-size: 12.5px; }
    .s1mut { fill: #6b6558; font-size: 12px; }
    .s1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .s1ln  { stroke: #6b6558; stroke-width: 1.4; fill: none; }
    .s1net { stroke: #b4553e; stroke-width: 1.5; fill: none; }
    .s1nt  { fill: #b4553e; font-size: 12px; }
    .s1hd  { fill: #6b6558; }
    .s1hr  { fill: #b4553e; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1sv { fill: #23303f; stroke: #5d7898; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1cl { fill: #3d3222; stroke: #a4824a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1io { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1ink, :root:is([data-theme="dark"], [data-theme="black"]) .s1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1ln { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1hd { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1net { stroke: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s1nt, :root:is([data-theme="dark"], [data-theme="black"]) .s1hr { fill: #e08a70; }
  </style>
  <defs>
    <marker id="s1a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="s1hd"/></marker>
    <marker id="s1r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="s1hr"/></marker>
  </defs>
  <rect class="s1bg" x="0" y="0" width="760" height="452" rx="10"/>
  <text class="s1ttl" x="40" y="30">服务端</text>
  <text class="s1ttl" x="460" y="30">客户端</text>
  <rect class="s1sv" x="40" y="44" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="66">socket()　拿到一个 fd，还没有地址</text>
  <rect class="s1sv" x="40" y="94" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="116">setsockopt(SO_REUSEADDR)</text>
  <rect class="s1sv" x="40" y="144" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="166">bind()　占住 IP 和端口</text>
  <rect class="s1sv" x="40" y="194" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="216">listen()　内核开始替它回握手</text>
  <rect class="s1sv" x="40" y="264" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="286">accept()　取走一条建好的连接</text>
  <rect class="s1io" x="40" y="330" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="352">read() / write()　用新 fd 收发</text>
  <rect class="s1sv" x="40" y="396" width="260" height="34" rx="6"/>
  <text class="s1ink" x="54" y="418">close()　发 FIN</text>
  <path class="s1ln" d="M170,78 L170,92" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M170,128 L170,142" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M170,178 L170,192" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M170,228 L170,262" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M170,298 L170,328" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M170,364 L170,394" marker-end="url(#s1a)"/>
  <rect class="s1cl" x="460" y="44" width="260" height="34" rx="6"/>
  <text class="s1ink" x="474" y="66">socket()</text>
  <rect class="s1cl" x="460" y="194" width="260" height="34" rx="6"/>
  <text class="s1ink" x="474" y="216">connect()　握手完成才返回</text>
  <rect class="s1io" x="460" y="330" width="260" height="34" rx="6"/>
  <text class="s1ink" x="474" y="352">write() / read()</text>
  <rect class="s1cl" x="460" y="396" width="260" height="34" rx="6"/>
  <text class="s1ink" x="474" y="418">close()　发 FIN</text>
  <path class="s1ln" d="M590,78 L590,192" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M590,228 L590,328" marker-end="url(#s1a)"/>
  <path class="s1ln" d="M590,364 L590,394" marker-end="url(#s1a)"/>
  <path class="s1net" d="M458,211 L304,240" marker-end="url(#s1r)"/>
  <text class="s1nt" x="318" y="200">三次握手</text>
  <text class="s1nt" x="318" y="216">内核完成</text>
  <text class="s1mut" x="318" y="258">进已完成队列</text>
  <path class="s1net" d="M304,342 L456,342" marker-end="url(#s1r)"/>
  <path class="s1net" d="M456,352 L304,352" marker-end="url(#s1r)"/>
  <text class="s1nt" x="356" y="336">字节流</text>
  <path class="s1net" d="M304,413 L456,413" marker-end="url(#s1r)"/>
  <path class="s1net" d="M456,413 L304,413" marker-end="url(#s1r)"/>
  <text class="s1nt" x="346" y="406">四次挥手</text>
</svg>

## 2. 地址和字节序

### 2.1 sockaddr_in：所有地址都从一个通用指针传进去 {#sockaddr}

`bind`、`connect`、`accept` 要支持 IPv4、IPv6、本机路径好几种地址，而 C 没有重载，于是参数统一写成 `struct sockaddr*` 加一个长度，每种地址结构的第一个字段都是地址族，内核先读这个字段，再按对应的结构解释后面的字节。IPv4 用的是 `sockaddr_in`：

```cpp
struct sockaddr_in {
    sa_family_t    sin_family;   // AF_INET
    in_port_t      sin_port;     // 端口，网络字节序
    struct in_addr sin_addr;     // IPv4 地址，网络字节序
    unsigned char  sin_zero[8];  // 填充，凑成和 sockaddr 一样大
};
```

所以调用时要把 `sockaddr_in*` 强转成 `sockaddr*`。不知道对方是 IPv4 还是 IPv6 时，用 `sockaddr_storage` 接，它大到放得下任何一种。要从域名得到地址，用 `getaddrinfo`：它查 DNS，直接返回填好的 `sockaddr` 链表，IPv4 和 IPv6 都有，代码不用关心是哪种。

### 2.2 网络字节序（network byte order）：多字节整数一律按大端放 {#byte-order}

一个 2 字节的端口号 9000，十六进制是 0x2328。x86 和常见的 ARM 都是小端，低位字节放在低地址，内存里是 `28 23`；TCP/IP 的协议头规定用大端，高位字节在前，线上必须是 `23 28`。两种机器要靠同一套报文头互通，就得在填协议头之前转一次。下面这段在 x86 上跑的结果：

```text
9000 = 0x2328, in memory: 28 23
after htons, in memory: 23 28
192.168.1.1 network order: 192 168 1 1
```

转换函数的名字自己就说明了方向：h 是 host（本机），n 是 network，s 是 16 位（端口），l 是 32 位（IPv4 地址）。`htons` 把端口从本机序转成网络序，`ntohs` 反过来，`htonl`、`ntohl` 同理。在大端机器上它们什么都不做，所以照着写总是对的。点分十进制的字符串用 `inet_pton` 转成 4 个字节，出来就已经是网络序，不用再 `htonl`；`inet_ntop` 反过来，打印对方地址时用。

**要转的只是放进 `sockaddr` 的端口和地址，因为那是内核要拿去填协议头的。** 自己 `write` 出去的数据，内核一个字节都不看，里面的整数用什么字节序，由你的协议规定；两端都按同一个约定编码，或者干脆传文本。

### 2.3 SO_REUSEADDR：重启服务时不被 TIME_WAIT 挡住 {#so-reuseaddr}

服务端主动关掉的连接，会在 TIME_WAIT 里停 60 s，这段时间它还占着那个本地端口。服务进程一重启，`bind` 同一个端口就会失败，报 `EADDRINUSE`，要等一分钟才能起来。在 `bind` 之前设上 `SO_REUSEADDR`，内核就允许绑定一个只被 TIME_WAIT 连接占着的端口，所以服务端几乎都设它。

它不允许两个进程同时监听同一个端口；第二个 `bind` 照样失败。那是 `SO_REUSEPORT` 的事：几个 socket 都设上它，就能绑同一个端口，内核把新连接按四元组散到它们中间，常用来让几个进程或线程各自 `accept`，不用抢同一个监听 socket。TIME_WAIT 为什么要等、客户端端口耗尽怎么办，在 [TCP 状态](/zh/ref/tcp-states/) 的第 2 节。

## 3. 一个完整的回显服务器

### 3.1 服务端：一次服务一个客户端 {#echo-server}

收到什么就原样发回去，客户端断开以后再 `accept` 下一个：

```cpp
// echo_server.cpp：一次服务一个客户端的回显服务器
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>

static void die(const char* what) { std::perror(what); std::exit(1); }

// write 可能只写进去一部分，循环到写完为止
static bool write_all(int fd, const char* p, size_t n) {
    while (n > 0) {
        ssize_t k = write(fd, p, n);
        if (k < 0) {
            if (errno == EINTR) continue;           // 被信号打断，重来
            return false;
        }
        p += k;
        n -= static_cast<size_t>(k);
    }
    return true;
}

int main() {
    int lfd = socket(AF_INET, SOCK_STREAM, 0);     // ① 一个还没有地址的 TCP socket
    if (lfd < 0) die("socket");
    int on = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof on);  // 重启时不被旧连接占着端口

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(9000);                   // 端口转成网络字节序
    addr.sin_addr.s_addr = htonl(INADDR_ANY);      // 本机所有地址都收
    if (bind(lfd, reinterpret_cast<sockaddr*>(&addr), sizeof addr) < 0) die("bind");  // ②
    if (listen(lfd, SOMAXCONN) < 0) die("listen");                                     // ③

    for (;;) {
        sockaddr_in peer{};
        socklen_t len = sizeof peer;
        int cfd = accept(lfd, reinterpret_cast<sockaddr*>(&peer), &len);  // ④ 取一个建好的连接
        if (cfd < 0) {
            if (errno == EINTR) continue;
            die("accept");
        }
        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &peer.sin_addr, ip, sizeof ip);
        std::printf("client %s:%d\n", ip, ntohs(peer.sin_port));

        char buf[4096];
        for (;;) {
            ssize_t n = read(cfd, buf, sizeof buf);    // ⑤ 缓冲区里有多少拿多少
            if (n == 0) break;                         // 对方关了写的方向
            if (n < 0) {
                if (errno == EINTR) continue;
                break;                                 // 比如对方发了 RST
            }
            if (!write_all(cfd, buf, static_cast<size_t>(n))) break;
        }
        close(cfd);                                    // ⑥ 发 FIN
    }
}
```

`accept` 的后两个参数是传出参数：`len` 进去时是缓冲区大小，出来时是对方地址的实际长度，所以每次调用前都要重新设。`read` 返回 0 表示对方发来了 FIN，不会再有数据，这时关掉自己这一端；返回 -1 且 `errno` 是 `ECONNRESET`，说明对方直接发了 RST。编译运行以后，用 `nc 127.0.0.1 9000` 连上去敲几行，每行都会原样回来。

### 3.2 客户端 {#echo-client}

```cpp
// echo_client.cpp：发一句，等回显
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

int main(int argc, char** argv) {
    const char* host = argc > 1 ? argv[1] : "127.0.0.1";
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) { std::perror("socket"); return 1; }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(9000);
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1) {    // "127.0.0.1" → 4 个字节，网络字节序
        std::fprintf(stderr, "bad address: %s\n", host);
        return 1;
    }
    if (connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof addr) < 0) {  // 三次握手在这里完成
        std::perror("connect");
        return 1;
    }

    const char* msg = "hello";
    size_t want = std::strlen(msg);
    if (write(fd, msg, want) != static_cast<ssize_t>(want)) { std::perror("write"); return 1; }

    char buf[64];
    size_t got = 0;
    while (got < want) {                       // 回显可能分几次到，收够了再停
        ssize_t n = read(fd, buf + got, sizeof buf - got);
        if (n <= 0) break;
        got += static_cast<size_t>(n);
    }
    std::printf("echo: %.*s\n", static_cast<int>(got), buf);
    close(fd);
}
```

客户端知道自己发了 5 个字节，所以读到 5 个才停，而不是读一次就算完。这个“收够了再停”正是下一节要讲的东西。

### 3.3 TCP 是字节流：read 和 write 都可能只做一部分 {#partial-io}

TCP 只保证字节按发送的顺序、不多不少地到达，它不记得你是分几次 `write` 的。一端连着 `write` 了 `"hello"` 和 `"world"`，另一端可能一次 `read` 到 `"helloworld"`，也可能先读到 `"hel"`，再读到剩下的；一次 `write` 了 10 KB，对面多半要读好几次，每次拿到多少取决于当时接收缓冲区里攒了多少。**一次 `read` 对应的不是一条消息，所以消息的边界必须由应用协议自己划。** 常用的办法有三种：定长消息；用分隔符，比如按行，或者 HTTP 头部用一个空行结束；在消息前面放一个长度字段，先读够长度、再读够正文，HTTP 的 `Content-Length` 就是这种。接收端因此都要有一块缓冲区，把读到的字节攒起来，凑够一条完整消息再处理，剩下的留给下一条。所谓“粘包”说的就是这件事，它不是 TCP 的毛病，而是把字节流当成了消息流。

写的一侧也一样。阻塞 socket 上，`write` 通常会等到全部拷进发送缓冲区才返回，但中途被信号打断，就可能只写进去一部分；非阻塞 socket 上，发送缓冲区剩多少空间就写多少，返回实际写入的字节数。所以 3.1 的 `write_all` 要循环，每次从上次停下的地方接着写。

还有两个边界要处理。对方已经关闭连接以后再往里写，第一次 `write` 往往还能成功（数据进了本机缓冲区），对方回一个 RST；再写一次，`write` 返回 `EPIPE`，同时内核给进程发 `SIGPIPE`，这个信号默认会直接杀死进程。所以服务端一般在启动时 `signal(SIGPIPE, SIG_IGN)`，或者用 `send(fd, buf, n, MSG_NOSIGNAL)` 代替 `write`，把它当成普通的错误码处理。另一个是 `EINTR`：阻塞在 `read`、`accept` 里的时候来了信号，调用会以 `EINTR` 返回，重试就行。

## 4. 同时服务很多个客户端

### 4.1 每个连接一个进程：fork {#fork-per-conn}

3.1 的服务器在服务一个客户端时，别的客户端只能在队列里等。最直接的改法是每 `accept` 到一个连接就 `fork` 一个子进程去服务它，父进程马上回去 `accept`：

```cpp
signal(SIGCHLD, SIG_IGN);                 // 子进程退出时内核直接回收，不留僵尸
for (;;) {
    int cfd = accept(lfd, nullptr, nullptr);
    if (cfd < 0) continue;
    if (fork() == 0) {                    // 子进程
        close(lfd);                       // 子进程用不到监听 socket
        serve(cfd);
        close(cfd);
        _exit(0);
    }
    close(cfd);                           // 父进程关掉自己那份，连接的引用只剩子进程一个
}
```

`fork` 以后父子进程各有一份 fd 表，指向同一个连接，内核要等最后一个引用关掉才发 FIN。父进程不 `close(cfd)` 的话，子进程服务完关掉自己那份，连接也不会断，客户端一直等不到 FIN，父进程的 fd 还会越积越多。子进程退出后要有人回收，否则变成僵尸进程，所以要么忽略 `SIGCHLD`，要么在它的处理函数里循环 `waitpid(-1, nullptr, WNOHANG)`。

这种写法最大的好处是隔离：一个连接的处理代码崩了，只死一个子进程。代价是每个连接一个进程，`fork` 要复制页表，进程之间切换要换地址空间，几百个连接还行，上万个就扛不住。`fork` 和写时复制的细节在 [进程、线程和 fork](/zh/ref/process-thread-fork/)。

### 4.2 每个连接一个线程 {#thread-per-conn}

把 `fork` 换成 `std::thread(serve, cfd).detach()`，每个连接一个线程，创建比进程便宜，线程之间切换不用换页表，数据也能直接共享。代码还是阻塞式的，一个连接从头到尾顺着写，最好读。

问题在于线程数等于连接数。每个线程有自己的栈（Linux 默认预留 8 MiB 虚拟空间，用多少才真正占多少物理内存），连接一多，调度器要在几千个线程之间来回切，每次切换都要保存和恢复寄存器、冲掉一部分缓存；而这些线程绝大多数时间都睡在 `read` 上，只是在等数据。这就是所谓的 C10K 问题：一万个连接，不该需要一万个线程。用固定大小的线程池也解决不了，因为线程一旦阻塞在某个慢客户端的 `read` 上，就被它占住了，池子很快被慢连接占满。**根子在于“等数据”占用了一整个线程，要省线程，就得让等待不再占线程。**

### 4.3 非阻塞 socket：没数据时返回 EAGAIN，而不是睡 {#nonblocking}

给 fd 加上 `O_NONBLOCK`（`fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK)`，或者建 socket 时直接传 `SOCK_NONBLOCK`），所有可能睡的调用都改成立刻返回：`read` 没数据时返回 -1，`errno` 是 `EAGAIN`（和 `EWOULDBLOCK` 是同一个值）；`write` 在发送缓冲区满时也返回 `EAGAIN`，或者只写进去一部分；`accept` 在队列空时返回 `EAGAIN`；`connect` 不等握手，返回 `EINPROGRESS`，之后等 fd 变成可写，再用 `getsockopt(fd, SOL_SOCKET, SO_ERROR, ...)` 看握手是成功还是失败。

光有非阻塞还不够，挨个去试几千个 fd 太浪费，所以要配上 IO 多路复用：用一次 `epoll_wait` 问内核哪些 fd 现在能读能写，只对这些 fd 动手。反过来，用了 epoll 以后 fd 也必须是非阻塞的，因为单线程的事件循环里，任何一次阻塞都会让所有连接一起停下。边缘触发要求一直读到 `EAGAIN`，阻塞 fd 读空了就睡死在那里；即使是水平触发，`epoll_wait` 报了可读，客户端可能在你 `accept` 之前就发 RST 撤销了连接，阻塞的 `accept` 就会一直等下一个连接。epoll 内部怎么只看就绪的 fd、水平触发和边缘触发差在哪，在 [epoll](/zh/ref/epoll-internals/) 里讲过。

### 4.4 Reactor：一个线程等事件，再把事件分给各连接的处理函数 {#reactor}

把上面两样合起来，就是 Reactor 模式：一个事件循环阻塞在 `epoll_wait` 上，这是整个线程唯一会睡的地方；醒来以后，对每个就绪的 fd 调它登记的处理函数；处理函数只做不会阻塞的事，做完立刻回到循环。

```cpp
// reactor.cpp：一个线程，一个 epoll，非阻塞 socket
#include <netinet/in.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>

int make_listener();                      // socket + bind + listen，同上，只是 socket 带 SOCK_NONBLOCK

static void on_readable(int fd) {         // 边缘触发：一直读到 EAGAIN
    char buf[4096];
    for (;;) {
        ssize_t n = read(fd, buf, sizeof buf);
        if (n > 0) { /* 处理这 n 个字节；回写也要处理写不完的情况 */ continue; }
        if (n == 0) { close(fd); return; }                 // 对方关了
        if (errno == EAGAIN || errno == EWOULDBLOCK) return;  // 这会儿读空了
        if (errno == EINTR) continue;
        close(fd); return;
    }
}

int main() {
    int lfd = make_listener();
    int ep = epoll_create1(EPOLL_CLOEXEC);
    epoll_event ev{};
    ev.events = EPOLLIN;
    ev.data.fd = lfd;
    epoll_ctl(ep, EPOLL_CTL_ADD, lfd, &ev);

    epoll_event evs[64];
    for (;;) {
        int n = epoll_wait(ep, evs, 64, -1);               // 唯一会睡的地方
        for (int i = 0; i < n; ++i) {
            int fd = evs[i].data.fd;
            if (fd == lfd) {                               // 监听 socket 可读 = 有新连接
                for (;;) {
                    int cfd = accept4(lfd, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
                    if (cfd < 0) break;                    // EAGAIN：这一批取完了
                    epoll_event cev{};
                    cev.events = EPOLLIN | EPOLLET;
                    cev.data.fd = cfd;
                    epoll_ctl(ep, EPOLL_CTL_ADD, cfd, &cev);
                }
            } else {
                on_readable(fd);                           // 分派给这个连接的处理函数
            }
        }
    }
}
```

真正的服务器还要给每个连接配两块缓冲区。输入缓冲区攒读到的字节，凑够一条完整消息再处理（3.3 节）。输出缓冲区接住写不完的部分：`write` 返回 `EAGAIN` 时，把剩下的字节存起来，给这个 fd 加上 `EPOLLOUT`；等它可写了接着写，写完再把 `EPOLLOUT` 去掉。不去掉的话，水平触发下发送缓冲区几乎总是有空位，`epoll_wait` 会一直报可写，事件循环空转。

一个事件循环只能用一个核。要用多核，常见的做法是每个线程一个事件循环（one loop per thread）：主线程的循环只管 `accept`，把新连接轮流交给几个子线程的循环，此后这条连接的所有读写都在那个子线程里完成，不用加锁；muduo、Netty 都是这个结构。处理一条消息要算很久、或者要调一个阻塞的接口（查数据库、读磁盘）时，交给单独的 [线程池](/zh/ref/thread-pool-future/)，算完再把结果送回连接所在的循环去写。**Reactor 的全部约束就一条：事件循环里不能阻塞，阻塞一次，这个循环上的所有连接都跟着等。** 与它相对的是 Proactor：程序直接提交“读到这块缓冲区里”，内核做完再通知，Windows 的 IOCP 和 Linux 的 io_uring 是这一类；epoll 只告诉你“可以读了”，拷贝还得自己调 `read`。

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="三种并发模型：每连接一个进程，主进程 accept 后 fork 子进程；每连接一个线程，线程数等于连接数；一个线程加 epoll，所有连接登记在 epoll 上，事件循环把就绪事件分派给各连接的回调" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .s2bg  { fill: #fbfaf7; }
    .s2pn  { fill: #f4f2ec; stroke: #d6d1c4; stroke-width: 1.2; }
    .s2top { fill: #e3ecf6; stroke: #7d98b8; stroke-width: 1.3; }
    .s2wk  { fill: #f3e6cf; stroke: #b99254; stroke-width: 1.3; }
    .s2ev  { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.3; }
    .s2cn  { fill: #fbfaf7; stroke: #6b6558; stroke-width: 1.2; }
    .s2ink { fill: #1c1b18; font-size: 12.5px; }
    .s2mut { fill: #6b6558; font-size: 12px; }
    .s2ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .s2ln  { stroke: #6b6558; stroke-width: 1.3; fill: none; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2pn { fill: #1f1e24; stroke: #3a3842; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2top { fill: #23303f; stroke: #5d7898; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2wk { fill: #3d3222; stroke: #a4824a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2ev { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2cn { fill: #17161b; stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2ink, :root:is([data-theme="dark"], [data-theme="black"]) .s2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .s2ln { stroke: #a19caf; }
  </style>
  <rect class="s2bg" x="0" y="0" width="760" height="300" rx="10"/>
  <rect class="s2pn" x="12" y="12" width="236" height="276" rx="8"/>
  <text class="s2ttl" x="26" y="38">每连接一个进程</text>
  <rect class="s2top" x="56" y="54" width="148" height="34" rx="6"/>
  <text class="s2ink" x="74" y="76">主进程：accept</text>
  <path class="s2ln" d="M130,88 L54,128"/>
  <path class="s2ln" d="M130,88 L130,128"/>
  <path class="s2ln" d="M130,88 L206,128"/>
  <text class="s2mut" x="140" y="112">fork</text>
  <rect class="s2wk" x="24" y="128" width="60" height="34" rx="6"/>
  <text class="s2ink" x="34" y="150">子进程</text>
  <rect class="s2wk" x="100" y="128" width="60" height="34" rx="6"/>
  <text class="s2ink" x="110" y="150">子进程</text>
  <rect class="s2wk" x="176" y="128" width="60" height="34" rx="6"/>
  <text class="s2ink" x="186" y="150">子进程</text>
  <path class="s2ln" d="M54,162 L54,190"/>
  <path class="s2ln" d="M130,162 L130,190"/>
  <path class="s2ln" d="M206,162 L206,190"/>
  <circle class="s2cn" cx="54" cy="200" r="10"/>
  <circle class="s2cn" cx="130" cy="200" r="10"/>
  <circle class="s2cn" cx="206" cy="200" r="10"/>
  <text class="s2mut" x="26" y="238">各管一个连接，崩了只死一个</text>
  <text class="s2mut" x="26" y="258">fork、切换地址空间都贵</text>
  <rect class="s2pn" x="262" y="12" width="236" height="276" rx="8"/>
  <text class="s2ttl" x="276" y="38">每连接一个线程</text>
  <rect class="s2top" x="306" y="54" width="148" height="34" rx="6"/>
  <text class="s2ink" x="324" y="76">主线程：accept</text>
  <path class="s2ln" d="M380,88 L304,128"/>
  <path class="s2ln" d="M380,88 L380,128"/>
  <path class="s2ln" d="M380,88 L456,128"/>
  <rect class="s2wk" x="274" y="128" width="60" height="34" rx="6"/>
  <text class="s2ink" x="290" y="150">线程</text>
  <rect class="s2wk" x="350" y="128" width="60" height="34" rx="6"/>
  <text class="s2ink" x="366" y="150">线程</text>
  <rect class="s2wk" x="426" y="128" width="60" height="34" rx="6"/>
  <text class="s2ink" x="442" y="150">线程</text>
  <path class="s2ln" d="M304,162 L304,190"/>
  <path class="s2ln" d="M380,162 L380,190"/>
  <path class="s2ln" d="M456,162 L456,190"/>
  <circle class="s2cn" cx="304" cy="200" r="10"/>
  <circle class="s2cn" cx="380" cy="200" r="10"/>
  <circle class="s2cn" cx="456" cy="200" r="10"/>
  <text class="s2mut" x="276" y="238">代码顺着写，阻塞也没关系</text>
  <text class="s2mut" x="276" y="258">线程数 = 连接数，大多在睡</text>
  <rect class="s2pn" x="512" y="12" width="236" height="276" rx="8"/>
  <text class="s2ttl" x="526" y="38">一个线程 + epoll</text>
  <rect class="s2ev" x="556" y="54" width="148" height="34" rx="6"/>
  <text class="s2ink" x="580" y="76">epoll_wait</text>
  <path class="s2ln" d="M630,88 L630,128"/>
  <rect class="s2ev" x="540" y="128" width="180" height="34" rx="6"/>
  <text class="s2ink" x="556" y="150">分派给各连接的回调</text>
  <path class="s2ln" d="M554,190 L600,162"/>
  <path class="s2ln" d="M630,190 L630,162"/>
  <path class="s2ln" d="M706,190 L660,162"/>
  <circle class="s2cn" cx="554" cy="200" r="10"/>
  <circle class="s2cn" cx="630" cy="200" r="10"/>
  <circle class="s2cn" cx="706" cy="200" r="10"/>
  <text class="s2mut" x="526" y="238">线程数固定，不随连接数涨</text>
  <text class="s2mut" x="526" y="258">回调里一阻塞，全部连接都停</text>
</svg>

## 5. UDP 和本机 socket

### 5.1 UDP：没有连接，一次 recvfrom 一个报文 {#udp}

`socket(AF_INET, SOCK_DGRAM, 0)` 得到的 UDP socket 没有握手，也就没有 `listen` 和 `accept`。服务端 `bind` 一个端口，然后用 `recvfrom` 收：它除了数据，还把发送方的地址填进传出参数，回信时把这个地址交给 `sendto`。客户端可以不 `bind`，第一次 `sendto` 时内核替它挑一个临时端口：

```cpp
int main() {                                  // UDP 回显：没有 listen，没有 accept
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(9001);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof addr) < 0) { std::perror("bind"); return 1; }
    for (;;) {
        char buf[1500];
        sockaddr_in peer{};
        socklen_t len = sizeof peer;
        ssize_t n = recvfrom(fd, buf, sizeof buf, 0, reinterpret_cast<sockaddr*>(&peer), &len);  // 一次正好一个报文
        if (n < 0) continue;
        sendto(fd, buf, static_cast<size_t>(n), 0, reinterpret_cast<sockaddr*>(&peer), len);       // 发回给来的那个地址
    }
}
```

因为没有连接，一个 socket 就能和任意多个客户端说话，每个报文自己带着对方是谁，服务端不需要 fork 或开线程就能同时应付很多客户端。和 TCP 最大的接口差别在边界：**UDP 保留消息边界，对方 `sendto` 一次，你 `recvfrom` 一次正好拿到那一整个报文**，不会拆开也不会和下一个粘在一起；缓冲区比报文小，多出来的部分直接丢掉。代价是 UDP 不管可靠：报文可能丢、可能重复、可能乱序，也没有流量控制和拥塞控制，发得比对方收得快，多出来的就在对方接收缓冲区满时被丢掉。报文超过链路的 MTU（以太网是 1500 字节）会被 IP 层分片，任何一片丢了整个报文都作废，所以实际应用把每个报文控制在 1200–1472 字节以内。

UDP socket 也可以 `connect`，但不发任何报文，只是在内核里记下一个默认的对端：之后能用 `send`、`recv`，内核会过滤掉别的地址发来的报文，对方端口没人监听时回来的 ICMP 错误也能以 `ECONNREFUSED` 报给你。DNS 查询、音视频、游戏、QUIC 都跑在 UDP 上，可靠性要么不需要，要么由应用自己按需要做。

### 5.2 Unix 域套接字：同一套函数，地址换成一个文件路径 {#unix-socket}

只在本机两个进程之间通信时，把地址族换成 `AF_UNIX`，地址结构换成 `sockaddr_un`，里面放一个路径，比如 `/tmp/echo.sock`。`bind`、`listen`、`accept`、`connect`、`read`、`write` 全都照旧，上面的回显服务器改三行就能用；`SOCK_STREAM` 是字节流，`SOCK_DGRAM` 保留消息边界，而且在本机不会丢。

`bind` 会在文件系统里建出这个路径，进程退出后文件还在，下次 `bind` 同一个路径会报 `EADDRINUSE`，所以服务端启动前先 `unlink` 它。不想在磁盘上留文件，Linux 支持抽象命名空间：`sun_path` 第一个字节放 `'\0'`，名字只活在内核里，最后一个 socket 关掉就消失。父子进程之间还可以用 `socketpair` 直接得到一对已经连好的 socket，连路径都不用。它为什么比本机 TCP 便宜、怎么用它把 fd 传给另一个进程，在 [进程间通信](/zh/ref/ipc/) 的 2.4 节。
