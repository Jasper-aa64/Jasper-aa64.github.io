---
title: "HTTP 和 HTTPS：一次请求从输入网址到拿到页面"
date: 2026-11-02
slug: "http-basics"
description: "在浏览器里输入一个 https 网址，到第一个字节回来，中间要先查 DNS，再做 TCP 握手和 TLS 握手，最后才发出请求。这篇顺着这条路讲：请求和响应的文本格式，GET 和 POST 的真正区别（安全和幂等），常被问的状态码，在 TCP 字节流上靠 Content-Length 和分块传输划出一条消息，长连接；HTTP 无状态时怎么靠 Cookie、Session、Token 记住登录；从 HTTP/1.1 到 HTTP/2 再到 HTTP/3，队头阻塞怎样一层层往下挪；HTTPS 的 TLS 1.3 握手怎么商量出密钥、证书链凭什么可信、数据为什么用对称加密；最后是 WebSocket 怎样借一次 HTTP 握手换成全双工。"
summary: "一个新的 HTTPS 请求，要等 DNS、TCP 握手、TLS 握手各花掉时间，才轮到真正的请求，复用连接就是为了省掉前面几段。HTTP 消息在 TCP 字节流上靠空行和 Content-Length（或分块）划出边界；HTTP/2 用流解决了应用层的排队，却躲不开 TCP 的按序交付，HTTP/3 才把流做进 QUIC。TLS 用非对称密码学商量出密钥、证明服务器身份，数据本身用对称加密，因为快几个数量级。"
toc: true
math: true
group: cpplinux
weight: 121
---

在浏览器地址栏敲下 `https://example.com/` 回车，几百毫秒后页面出来。这几百毫秒里，真正“发请求、收响应”只占一小段，前面还要先找到服务器在哪、和它建立连接、商量出加密用的密钥。下面顺着时间往下讲，每一步都说清楚它为什么要存在，再回头看请求本身的格式、HTTP 各版本改了什么，以及 HTTPS 里的 S 到底做了什么。

## 1. 从输入网址到第一个字节

### 1.1 DNS：先把域名换成 IP 地址 {#dns}

TCP 连接要的是 IP 地址和端口，而用户给的是域名，所以第一步是查 DNS。浏览器先看自己的缓存，再问操作系统（`/etc/hosts` 和系统的解析缓存），都没有，就把问题交给配置好的递归解析器，通常是运营商的或者 8.8.8.8 这类公共解析器。递归解析器替你跑完整个查询：问根服务器 `.com` 归谁管，问 `.com` 的服务器 `example.com` 归谁管，最后问 `example.com` 的权威服务器拿到 IP。每一级的回答都带一个 TTL，在这个时间内各级缓存都直接用，所以绝大多数查询在本机或解析器那里就结束了，用不了一毫秒到几十毫秒。

DNS 查询一般走 UDP 的 53 端口，一问一答各一个报文，不用先握手；回答太大装不进一个 UDP 报文时，改走 TCP。端口没有写在网址里，就按协议用默认的：`http` 是 80，`https` 是 443。

### 1.2 TCP 和 TLS 握手：发请求之前要先等几个来回 {#handshakes}

拿到 IP，浏览器发起 TCP 连接，三次握手花 1 个 RTT（往返时间，一个报文到对方再回来的时间）：客户端收到 SYN+ACK 就可以开始发数据。HTTPS 还要在 TCP 之上做 TLS 握手，TLS 1.3 再花 1 个 RTT，商量出加密密钥、验证服务器身份（第 5 节）。然后才轮到真正的请求和响应，又是 1 个 RTT，再加上服务器处理的时间。

$$
\text{首字节时间} \approx \text{DNS} + \underbrace{1\ \text{RTT}}_{\text{TCP 握手}} + \underbrace{1\ \text{RTT}}_{\text{TLS 1.3}} + \underbrace{1\ \text{RTT}}_{\text{请求和响应}} + \text{服务器处理}
$$

同城的 RTT 是几毫秒，跨洲是 100–300 ms，所以一个跨洲的新连接光握手就要等几百毫秒，而请求本身可能只要几毫秒就处理完了。**一个新 HTTPS 连接，至少三个来回才能拿到响应的第一个字节，握手的那两个来回只付一次。** HTTP 的长连接、HTTP/2 让所有请求挤进一条连接、TLS 的会话恢复、HTTP/3 的 0-RTT，都是在省前面这两段。TCP 握手每一步的状态，在 [TCP 状态](/zh/ref/tcp-states/) 里讲过。

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="一个新 HTTPS 请求的时间线：先查 DNS，然后 TCP 握手 1 个 RTT，TLS 1.3 握手 1 个 RTT，最后请求和响应 1 个 RTT 加服务器处理" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .h1bg  { fill: #fbfaf7; }
    .h1dns { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.3; }
    .h1lane { stroke: #6b6558; stroke-width: 2; fill: none; }
    .h1tcp { stroke: #7d98b8; stroke-width: 1.6; fill: none; }
    .h1tls { stroke: #b99254; stroke-width: 1.6; fill: none; }
    .h1htp { stroke: #6f8f3f; stroke-width: 1.6; fill: none; }
    .h1prc { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.2; }
    .h1ink { fill: #1c1b18; font-size: 12.5px; }
    .h1mut { fill: #6b6558; font-size: 12px; }
    .h1ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
    .h1br  { stroke: #6b6558; stroke-width: 1.2; fill: none; }
    .h1ht  { fill: #7d98b8; }
    .h1hl  { fill: #b99254; }
    .h1hh  { fill: #6f8f3f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1dns { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1lane, :root:is([data-theme="dark"], [data-theme="black"]) .h1br { stroke: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1tcp { stroke: #8fb0d6; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1tls { stroke: #d6b27a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1htp { stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1prc { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1ink, :root:is([data-theme="dark"], [data-theme="black"]) .h1ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1mut { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1ht { fill: #8fb0d6; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1hl { fill: #d6b27a; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h1hh { fill: #8fb257; }
  </style>
  <defs>
    <marker id="h1at" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="h1ht"/></marker>
    <marker id="h1al" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="h1hl"/></marker>
    <marker id="h1ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="h1hh"/></marker>
  </defs>
  <rect class="h1bg" x="0" y="0" width="760" height="300" rx="10"/>
  <text class="h1ttl" x="24" y="75">浏览器</text>
  <text class="h1ttl" x="24" y="195">服务器</text>
  <rect class="h1dns" x="104" y="52" width="96" height="36" rx="6"/>
  <text class="h1ink" x="122" y="75">查 DNS</text>
  <path class="h1lane" d="M200,70 L740,70"/>
  <path class="h1lane" d="M104,190 L740,190"/>
  <path class="h1tcp" d="M220,70 L298,188" marker-end="url(#h1at)"/>
  <path class="h1tcp" d="M300,190 L378,72" marker-end="url(#h1at)"/>
  <text class="h1ink" x="220" y="58" text-anchor="middle">SYN</text>
  <text class="h1ink" x="300" y="210" text-anchor="middle">SYN+ACK</text>
  <path class="h1tls" d="M380,70 L458,188" marker-end="url(#h1al)"/>
  <path class="h1tls" d="M460,190 L538,72" marker-end="url(#h1al)"/>
  <text class="h1ink" x="380" y="58" text-anchor="middle">ClientHello（带密钥份额）</text>
  <text class="h1ink" x="460" y="210" text-anchor="middle">ServerHello、证书、Finished</text>
  <path class="h1htp" d="M540,70 L618,188" marker-end="url(#h1ah)"/>
  <rect class="h1prc" x="620" y="182" width="30" height="16" rx="3"/>
  <path class="h1htp" d="M652,190 L730,72" marker-end="url(#h1ah)"/>
  <text class="h1ink" x="545" y="58" text-anchor="middle">Finished + GET</text>
  <text class="h1ink" x="660" y="216" text-anchor="middle">处理，200 OK</text>
  <path class="h1br" d="M220,238 L220,246 L378,246 L378,238"/>
  <text class="h1mut" x="299" y="264" text-anchor="middle">TCP 握手：1 RTT</text>
  <path class="h1br" d="M382,238 L382,246 L538,246 L538,238"/>
  <text class="h1mut" x="460" y="264" text-anchor="middle">TLS 1.3：1 RTT</text>
  <path class="h1br" d="M542,238 L542,246 L730,246 L730,238"/>
  <text class="h1mut" x="636" y="264" text-anchor="middle">请求和响应：1 RTT + 处理</text>
  <text class="h1mut" x="24" y="288">TLS 1.2 的握手要 2 RTT；连接复用时，TCP 和 TLS 两段都省掉</text>
</svg>

### 1.3 请求和响应：几行文本，加一个空行，再加正文 {#message-format}

HTTP/1.1 的报文是纯文本，每行以 `\r\n` 结束。请求的第一行是方法、路径、版本，接着是若干行头部，然后一个空行，空行后面是正文（可以没有）：

```http
POST /cart/add HTTP/1.1
Host: shop.example.com
Cookie: sid=abc123
Content-Type: application/json
Content-Length: 32

{"product_id":1024,"quantity":1}
```

响应把第一行换成状态行，版本、状态码、一句说明，其余结构一样：

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 1256
Cache-Control: max-age=3600

<!doctype html>...
```

`Host` 是 HTTP/1.1 唯一必须带的头部。一台机器的一个 IP 上常常跑着很多个网站，TCP 连接只知道 IP 和端口，服务器要靠 `Host` 才知道这个请求是给哪个站点的。浏览器拿到 HTML 以后边解析边发现它引用的 CSS、JS、图片，再对每一个发请求；同一个服务器的请求复用已经建好的连接，所以后面这些请求不用再握手。

## 2. 请求本身

### 2.1 方法：GET、POST，以及安全和幂等 {#methods}

方法表达的是这次请求打算对资源做什么：`GET` 读，`POST` 提交（通常是新建，或者触发一个处理），`PUT` 用请求里的内容整个替换资源，`PATCH` 只改其中几个字段，`DELETE` 删除，`HEAD` 和 `GET` 一样但只要头部。它们按两个性质分。**安全**（safe）是只读，不改服务器上的状态，`GET`、`HEAD`、`OPTIONS` 是安全的。**幂等**（idempotent）是执行一次和执行很多次，服务器最后的状态一样：`PUT` 把用户 1 改成同一份内容，改几次结果都一样；`DELETE` 删同一条记录，第二次删时它已经不在了，状态没有再变；而 `POST /orders` 每发一次就多一张订单，所以不幂等。安全的方法一定幂等，反过来不成立。

幂等之所以要紧，是因为网络会出错：请求发出去以后连接断了，客户端不知道服务器到底执行了没有。幂等的请求可以放心重发，浏览器、代理、HTTP 客户端库都会自动重试；`POST` 重发可能让用户付两次钱，所以浏览器在你刷新一个 `POST` 提交的结果页时要弹窗确认。常见的做法是提交成功以后回一个 302，让浏览器跳到结果页再 `GET` 一次（Post/Redirect/Get），这样刷新的只是那个 `GET`。

GET 和 POST 的其他区别都从这里来。`GET` 安全、幂等，所以它的响应可以被浏览器和中间的代理缓存，地址可以收藏、分享、写进历史记录；参数只能放在 URL 的查询串里，按 URL 编码（中文变成 `%E8%80%B3` 这样的字节序列）。协议本身没有给 URL 规定长度上限，限制来自实现：服务器通常接受 8 KB 左右的请求行和头部，超过就回 414 或 431。`GET` 带正文在协议里没有定义含义，很多服务器和代理会忽略或拒绝，所以实际上不用。`POST` 的数据放在正文里，不出现在地址栏和日志里，但没有 TLS 的话，正文和 URL 一样是明文，**说 POST 比 GET 安全，只是不那么显眼，真正防窃听的是 HTTPS。**

### 2.2 状态码：第一位数字说明这是谁的事 {#status-codes}

| 范围 | 含义 | 常被问到的 |
|---|---|---|
| 1xx | 还没完，继续 | 100 Continue，101 Switching Protocols |
| 2xx | 成功 | 200 OK，201 Created，204 No Content，206 Partial Content |
| 3xx | 去别处拿 | 301 永久重定向，302 临时重定向，304 Not Modified，307 / 308 |
| 4xx | 客户端的错 | 400 Bad Request，401 Unauthorized，403 Forbidden，404 Not Found，405，429 Too Many Requests |
| 5xx | 服务端的错 | 500 Internal Server Error，502 Bad Gateway，503 Service Unavailable，504 Gateway Timeout |

第一位数字决定了客户端该怎么反应：4xx 原样重试没用，得改请求；5xx 换个时间、换台服务器重试可能就好了。几对容易混的码，区别都在“谁、为什么”：

301 和 302 都让浏览器去 `Location` 头给的新地址，301 说的是永久搬家，浏览器和搜索引擎会记住，下次直接去新地址；302 只是这一次，下次还来问。历史上浏览器跟着 301/302 跳转时会把 `POST` 改成 `GET`，所以后来补了 307 和 308，要求跳转时方法和正文都不变。304 不是跳转：浏览器带着 `If-None-Match`（上次拿到的 `ETag`）或者 `If-Modified-Since` 来问“我手上这份还新吗”，服务器回 304、不带正文，浏览器直接用缓存。

401 是“不知道你是谁”，没登录或者凭证无效，响应里会告诉你怎么认证；403 是“知道你是谁，但你没这个权限”，重新登录也没用。502 和 504 都出在网关或反向代理（比如 Nginx）身上：它把请求转给后端，后端回了一个它看不懂的东西或者直接断开，是 502；后端一直不回、等超时了，是 504。503 是服务器自己说忙不过来或者正在维护，通常带一个 `Retry-After`。

### 2.3 Content-Length 和分块传输：在字节流上找到一条消息的结尾 {#framing}

TCP 只给一串连续的字节，不告诉你一条消息在哪儿结束（[socket 编程](/zh/ref/socket-programming/) 的 3.3 节）。HTTP 自己划边界：头部以第一个空行（`\r\n\r\n`）结束；正文有多长，由头部说。服务器的读取逻辑因此是：把读到的字节攒进缓冲区，先找空行，找到了就解析头部，再按长度等正文收够，收够了才算一条完整的请求，多出来的字节属于下一条。下面这个简化版只认 `Content-Length`，用一条 `POST` 加一条 `GET` 被切成几段读进来的情形测了一下：

```cpp
// 缓冲区里是否已经有一条完整的请求；有就返回它的总长度，没有返回 0
size_t complete_request(std::string_view buf) {
    size_t end = buf.find("\r\n\r\n");               // 头部以一个空行结束
    if (end == std::string_view::npos) return 0;     // 头还没收完
    size_t head = end + 4;
    size_t body = 0;
    size_t p = buf.find("Content-Length:");          // 简化：不处理大小写和 chunked
    if (p != std::string_view::npos && p < end)
        body = std::strtoul(buf.data() + p + 15, nullptr, 10);
    return buf.size() >= head + body ? head + body : 0;   // 体也要收够
}
```

```text
read  10 bytes, buffered  10:
read  30 bytes, buffered  40:
read  25 bytes, buffered  65:
read   9 bytes, buffered  74: [request 67 bytes]
read  24 bytes, buffered  31: [request 31 bytes]
```

前三次读完，头部还没收齐，什么也做不了；第四次读完，第一条请求（67 字节）齐了，缓冲区里剩下的 7 字节是第二条的开头，等第五次读进来才凑成完整的 `GET`。

响应在开始发送时不一定知道自己有多长，比如一边查数据库一边往外写。这时用分块传输（`Transfer-Encoding: chunked`）：正文切成若干块，每块前面用十六进制写上这一块的字节数，最后用一个长度为 0 的块表示结束：

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked

7
Hello, 
6
world!
0

```

两样都没有的话，HTTP/1.0 的做法是以关闭连接表示正文结束，代价是这条连接不能再用。**正文的长度要么事先写明，要么分块逐段写明，连接才能接着承载下一个请求。** 所以长连接离不开它们。

### 2.4 长连接（keep-alive）：一条 TCP 连接发好多个请求 {#keep-alive}

HTTP/1.0 默认每个请求一条 TCP 连接，响应完就关。一个页面要几十个资源，每个都付一遍 1.2 节的握手，太贵。HTTP/1.1 改成默认长连接：响应发完连接不关，下一个请求接着用；哪一方想关，就在头部带 `Connection: close`。服务器不能无限期留着闲置的连接，每条都占着一个 fd 和内存，所以会给空闲连接设一个超时，常见是几秒到一两分钟，到点就主动关掉。服务端常用一个按到期时间排序的定时器（最小堆或时间轮）配合 `epoll_wait` 的超时参数来做这件事。

长连接省了握手，但没解决并发：HTTP/1.1 的一条连接上，同一时刻只能有一个请求在等响应。管线化（pipelining）允许不等响应就连发几个请求，可响应必须按请求的顺序回来，又因为很多代理处理不好，浏览器实际都没有打开它。于是浏览器对同一个域名同时开几条连接（通常 6 条），这就是下面第 4 节的起点。

## 3. 无状态，怎么记住登录

### 3.1 Cookie：服务器让浏览器替它记一个值 {#cookie}

HTTP 是无状态的：服务器处理每个请求时，不记得这个客户端之前发过什么，同一条连接上的两个请求也不必来自同一个用户（代理会把很多用户的请求合并到一条连接上）。所以“已登录”这种状态得由请求自己带着。

Cookie 就是让浏览器带的那个东西。服务器在响应里写 `Set-Cookie: sid=abc123; HttpOnly; Secure; SameSite=Lax; Max-Age=86400`，浏览器把它存下来，之后发往同一个站点的每个请求都自动带上 `Cookie: sid=abc123`。后面的属性决定它在什么时候带、谁能读到：`Domain` 和 `Path` 限定发给哪些地址；`Max-Age` 或 `Expires` 决定活多久，没有就在关浏览器时删掉；`HttpOnly` 让页面里的 JavaScript 读不到它，网页被注入了恶意脚本也偷不走；`Secure` 只在 HTTPS 上发送；`SameSite` 限制别的网站发起的请求带不带它。**Cookie 会被浏览器自动带上，这既是它方便的地方，也是它被利用的地方：** 恶意网站诱导你的浏览器向银行发一个请求，Cookie 照样跟着去，这叫 CSRF（跨站请求伪造），`SameSite` 和表单里的 CSRF token 就是防这个的。

### 3.2 Session 和 Token：状态存在服务器还是客户端 {#session-token}

Cookie 里放什么有两种思路。Session 方案只放一个随机的 session id，真正的状态（是哪个用户、什么角色、购物车里有什么）存在服务器的内存或 Redis 里，按 id 去查。Cookie 只是钥匙，数据在服务器手里，所以服务器能随时让某个 session 失效，踢人下线很容易。代价是状态在服务端：有多台服务器时，要么所有机器共用一个 session 存储，要么让负载均衡把同一个用户总是转发到同一台。

Token 方案把状态本身放进令牌里交给客户端，最常见的是 JWT：三段用点连起来，头部和载荷是 Base64 编码的 JSON（用户 id、过期时间等），第三段是服务器用自己的密钥对前两段算的签名。服务器收到以后不查任何存储，只验签名：签名对得上，就说明内容是自己签发的、没被改过。所以任何一台服务器都能独立验证，适合多服务、多机房。代价也在这里：令牌签发出去以后，过期之前服务器收不回来，只能把有效期设短，再配一个长期的刷新令牌；**而且载荷只是编码、没有加密，任何拿到令牌的人都能读，不能往里放秘密。** Token 一般放在 `Authorization: Bearer <token>` 头里由代码显式带上，浏览器不会自动附加，所以没有 CSRF 的问题，但要防它被脚本偷走。

## 4. HTTP/1.1、2、3：队头阻塞一层层往下挪

### 4.1 HTTP/1.1：一条连接上，前一个响应没发完，后一个只能等 {#http1-hol}

HTTP/1.1 的响应是一整块字节，一条连接上必须一个响应发完，才能开始发下一个。前面那个响应很大或者服务器生成得慢，后面的请求哪怕早就能答，也只能排着，这叫队头阻塞（head-of-line blocking）。浏览器开 6 条连接，相当于开 6 个队，缓解但不消除；每条连接还都要单独握手、单独经历 TCP 的慢启动。

### 4.2 HTTP/2：一条连接里多条流，帧交错着发 {#http2}

HTTP/2 不再传文本，而是把每个请求和响应切成小的二进制帧，每帧标着它属于哪条流（stream），一个请求和它的响应就是一条流。不同流的帧可以在同一条 TCP 连接上交错发送，接收方按流 id 重新拼起来，于是慢的响应不再挡住快的，一个域名只要一条连接。头部用 HPACK 压缩：两端各维护一张表，重复出现的头部（`User-Agent`、`Cookie`）第二次只发一个索引号。HTTP/2 还设计了服务器推送，让服务器不等请求就把页面要用的 CSS、JS 推过来，但它很难用对，经常推了浏览器已经缓存的东西，主流浏览器已经把它去掉了。

可流只存在于 HTTP 层，TCP 看到的仍然是一串字节，它只保证按序交付。**一个 TCP 段丢了，内核就把它后面已经收到的所有字节都扣着，等重传到了才一起交给应用，不管这些字节属于哪条流。** 所有流都被这一个丢包卡住，队头阻塞只是从 HTTP 层挪到了 TCP 层；丢包率高的网络上，一条 HTTP/2 连接甚至可能不如 HTTP/1.1 的 6 条连接，因为后者一次丢包只卡一条。

### 4.3 HTTP/3：QUIC 把流做进传输层 {#http3}

要让丢包只影响它所在的那条流，传输层本身就得知道流的存在，而 TCP 在内核里、协议固定，改不动。HTTP/3 于是换掉了 TCP，用 QUIC：它跑在 UDP 上，在用户态实现了可靠传输、重传、拥塞控制，而且每条流各自保证顺序。一个包丢了，只有它所在的流等重传，别的流的数据照常交给应用。

QUIC 把 TLS 1.3 直接做进了握手，传输握手和加密握手合在一起，新连接 1 个 RTT 就能发请求，比 TCP 加 TLS 少一个来回；以前连过的服务器还能 0-RTT，在第一个报文里就带上请求。0-RTT 的数据可能被攻击者截下来重放，所以只该用于幂等的请求。QUIC 的连接用一个连接 id 标识，而不是 IP 和端口的四元组，手机从 Wi-Fi 切到蜂窝网络、IP 变了，连接还能接着用。代价是它在用户态处理每个包，CPU 开销比内核里的 TCP 高；有些网络会限制或丢弃 UDP，所以浏览器总是准备着退回 HTTP/2。

<svg viewBox="0 0 760 312" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="三条流 A、B、C 的数据：HTTP/1.1 里 B 和 C 排在 A 后面；HTTP/2 里帧交错，但一个 A 的包丢了，后面所有流的数据都等重传；HTTP/3 里同样丢一个 A 的包，只有 A 后面的数据等，B 和 C 照常交付" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .h2bg  { fill: #fbfaf7; }
    .h2a   { fill: #f6ddd6; stroke: #c98a76; stroke-width: 1.2; }
    .h2b   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.2; }
    .h2c   { fill: #e3ecf6; stroke: #7d98b8; stroke-width: 1.2; }
    .h2w   { fill: #eceae4; stroke: #b5afa2; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .h2x   { fill: #fbfaf7; stroke: #b4553e; stroke-width: 1.6; stroke-dasharray: 4 3; }
    .h2xt  { fill: #b4553e; font-size: 14px; font-weight: 700; }
    .h2ink { fill: #1c1b18; font-size: 12.5px; }
    .h2mut { fill: #6b6558; font-size: 12px; }
    .h2ttl { fill: #1c1b18; font-size: 14px; font-weight: 700; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2a { fill: #4a2f2c; stroke: #8f5a4c; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2b { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2c { fill: #23303f; stroke: #5d7898; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2w { fill: #23262c; stroke: #5a5f68; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2x { fill: #17161b; stroke: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2xt { fill: #e08a70; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2ink, :root:is([data-theme="dark"], [data-theme="black"]) .h2ttl { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .h2mut { fill: #a19caf; }
  </style>
  <rect class="h2bg" x="0" y="0" width="760" height="312" rx="10"/>
  <text class="h2ttl" x="24" y="52">HTTP/1.1</text>
  <rect class="h2a" x="160" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="177" y="52">A</text>
  <rect class="h2a" x="208" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="225" y="52">A</text>
  <rect class="h2a" x="256" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="273" y="52">A</text>
  <rect class="h2a" x="304" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="321" y="52">A</text>
  <rect class="h2w" x="352" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="369" y="52">B</text>
  <rect class="h2w" x="400" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="417" y="52">B</text>
  <rect class="h2w" x="448" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="465" y="52">C</text>
  <rect class="h2w" x="496" y="32" width="44" height="30" rx="4"/><text class="h2ink" x="513" y="52">C</text>
  <text class="h2mut" x="160" y="82">B、C 早就能答，也要等 A 的响应整块发完</text>
  <text class="h2ttl" x="24" y="132">HTTP/2</text>
  <rect class="h2a" x="160" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="177" y="132">A</text>
  <rect class="h2b" x="208" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="225" y="132">B</text>
  <rect class="h2c" x="256" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="273" y="132">C</text>
  <rect class="h2x" x="304" y="112" width="44" height="30" rx="4"/><text class="h2xt" x="321" y="133">×</text>
  <rect class="h2w" x="352" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="369" y="132">B</text>
  <rect class="h2w" x="400" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="417" y="132">C</text>
  <rect class="h2w" x="448" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="465" y="132">A</text>
  <rect class="h2w" x="496" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="513" y="132">B</text>
  <rect class="h2w" x="544" y="112" width="44" height="30" rx="4"/><text class="h2ink" x="561" y="132">C</text>
  <text class="h2mut" x="160" y="162">A 的一个包丢了：后面的字节都到了，TCP 按序交付，全部等重传</text>
  <text class="h2ttl" x="24" y="212">HTTP/3</text>
  <rect class="h2a" x="160" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="177" y="212">A</text>
  <rect class="h2b" x="208" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="225" y="212">B</text>
  <rect class="h2c" x="256" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="273" y="212">C</text>
  <rect class="h2x" x="304" y="192" width="44" height="30" rx="4"/><text class="h2xt" x="321" y="213">×</text>
  <rect class="h2b" x="352" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="369" y="212">B</text>
  <rect class="h2c" x="400" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="417" y="212">C</text>
  <rect class="h2w" x="448" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="465" y="212">A</text>
  <rect class="h2b" x="496" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="513" y="212">B</text>
  <rect class="h2c" x="544" y="192" width="44" height="30" rx="4"/><text class="h2ink" x="561" y="212">C</text>
  <text class="h2mut" x="160" y="242">同样丢一个 A 的包：QUIC 知道流，只有 A 等，B、C 照常交给应用</text>
  <rect class="h2a" x="160" y="272" width="16" height="14" rx="2"/>
  <rect class="h2b" x="182" y="272" width="16" height="14" rx="2"/>
  <rect class="h2c" x="204" y="272" width="16" height="14" rx="2"/>
  <text class="h2mut" x="228" y="284">已交给应用</text>
  <rect class="h2w" x="320" y="272" width="16" height="14" rx="2"/>
  <text class="h2mut" x="344" y="284">已收到或已就绪，还在等</text>
  <rect class="h2x" x="520" y="272" width="16" height="14" rx="2"/>
  <text class="h2mut" x="544" y="284">丢失，等重传</text>
</svg>

## 5. HTTPS：HTTP 跑在 TLS 上

### 5.1 TLS 要解决三件事：别人看不到、改不了、冒充不了 {#tls-goals}

HTTP 是明文，路上的每一台路由器、每一个 Wi-Fi 热点都能看到、也能改你的请求和响应。HTTPS 就是在 TCP 和 HTTP 之间插一层 TLS，HTTP 报文本身一个字都不改。TLS 要同时给出三样：保密，内容只有两端能读；完整，内容被改了一个比特接收方也能发现；认证，客户端确认对面真的是 `example.com`，而不是一个夹在中间、两头转发的人（中间人攻击）。前两样靠两端共享一把只有它们知道的密钥，第三样靠证书。难点在于两端事先没有任何共同的秘密，又只能通过一条谁都能偷听的线路商量出一把。

### 5.2 TLS 1.3 握手：一个来回商量出密钥 {#tls13-handshake}

商量密钥用的是 Diffie-Hellman 密钥交换（现在多用椭圆曲线版本 ECDHE，比如 X25519）。双方各自随机生成一个私钥，算出对应的公钥发给对方；每一方用自己的私钥和对方的公钥，能算出同一个共享秘密，而偷听的人只看到两个公钥，算不出来。TLS 1.3 的握手就是把这件事塞进一个来回：

客户端发 ClientHello，里面有它支持的加密套件、一个随机数、要访问的域名（SNI，让一个 IP 上的服务器知道该出示哪个网站的证书），以及它的密钥份额（key share），也就是它这一次的 DH 公钥。服务器回 ServerHello，带上自己的密钥份额。到这里两边都能算出共享秘密，再用 HKDF 从中派生出各个方向的密钥，从下一条消息起全部加密。服务器接着发出自己的证书、一个 CertificateVerify（用证书对应的私钥，对到此为止的整段握手记录签名）、以及 Finished（用派生出的密钥对握手记录算的 MAC）。客户端验证证书链、验证这个签名、验证 Finished，再回自己的 Finished，然后就能发 HTTP 请求了。

CertificateVerify 是认证的关键：证书是公开的，谁都能拿到一份发给你，但只有持有对应私钥的服务器才能对这次握手的内容签出能被证书公钥验证通过的签名。中间人能转发证书，签不出这个名。而签名覆盖了整段握手记录，包括双方的 DH 公钥，中间人偷偷换掉密钥份额也会被发现。每次握手的 DH 私钥用完就扔，所以即使服务器的证书私钥日后泄露，攻击者也解不开以前录下来的流量，这叫前向保密。TLS 1.2 还允许用服务器的 RSA 公钥直接加密传送密钥，没有前向保密，而且握手要 2 个 RTT，TLS 1.3 把这两样都去掉了。

### 5.3 证书链：凭什么相信这把公钥是这个网站的 {#cert-chain}

服务器证书里写着域名、公钥、有效期，以及签发它的机构（CA）对这些内容的签名。客户端要相信它，就得先相信那个 CA 的公钥；CA 的证书又由上一级签发，这样一级级往上，直到一个根证书。根证书不靠别人签发，它们直接预装在操作系统或浏览器的信任库里，一共一两百个。实际部署通常是三级：根 CA 很少露面，它签发几个中间 CA，中间 CA 再给网站签证书；服务器在握手时把自己的证书和中间证书一起发过来，客户端用信任库里的根接上这条链。

验证时客户端检查：链上每一级的签名都能用上一级的公钥验证通过，且最后接到一个受信任的根；每张证书都在有效期内；网站证书的 SAN 字段里包含正在访问的域名；证书没有被吊销。**中间人可以伪造一张写着 `example.com` 的证书，但没有任何受信任 CA 的私钥替它签名，所以链接不上。** 公司内网的流量审查设备能解密 HTTPS，正是因为公司在员工电脑的信任库里装了自己的根证书。

### 5.4 为什么数据用对称加密 {#symmetric}

握手里的非对称运算（DH、签名）解决的是“没有共同秘密时怎么建立信任”，但它们慢：一次 RSA-2048 签名要零点几到一毫秒，一次 X25519 要几十微秒。对称加密有 CPU 的专用指令（x86 的 AES-NI），AES-GCM 一个核每秒能处理几 GB。所以分工很清楚：**非对称密码学每条连接只在握手时用几次，用来商量密钥和证明身份；之后所有数据用握手得到的对称密钥加密。** TLS 1.3 只留下了认证加密（AEAD）的套件，AES-GCM 或 ChaCha20-Poly1305，一次运算同时完成加密和防篡改校验，对应 5.1 节的保密和完整。

为了不让每个新连接都重做完整握手，TLS 支持会话恢复：服务器在握手后给客户端一张票据（session ticket），下次连接带上它，双方可以跳过证书验证，直接从上次的秘密派生新密钥；TLS 1.3 在此基础上还允许 0-RTT，和 4.3 节一样，只适合幂等请求。

## 6. WebSocket：借 HTTP 握手，换成全双工

### 6.1 Upgrade：一个 101 响应以后，这条连接就不再说 HTTP 了 {#websocket-upgrade}

HTTP 是客户端问、服务器答，服务器没法主动推消息给浏览器。聊天、行情、协同编辑这类场景，以前只能靠轮询，或者让服务器把请求挂着、有消息再答（长轮询），每条消息都要付一遍头部的开销。WebSocket 让浏览器先发一个普通的 HTTP 请求，要求把这条连接升级：

```http
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

服务器同意，就回 `101 Switching Protocols`，带上 `Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=`。这个值是把客户端的 key 和一个协议规定的固定 GUID 拼起来，算 SHA-1 再 Base64 得到的，它只证明对面确实理解 WebSocket 协议，而不是一个把请求当普通 HTTP 处理、碰巧回了 101 的服务器，跟加密和认证无关。从这一刻起，同一条 TCP 连接上不再有 HTTP，双方都可以随时发 WebSocket 帧：每帧有一个很小的头（几个字节，标明帧类型、长度），文本、二进制、ping/pong 心跳、关闭各是一种帧。客户端发出的帧必须用一个随机掩码异或一遍，为的是防止路上不懂 WebSocket 的代理把帧内容误当成 HTTP 请求去缓存。**WebSocket 只在开头借用一次 HTTP，好处是能走 80 和 443 端口、穿过只认 HTTP 的防火墙和代理，之后就是 TCP 上一条两端都能随时说话的消息通道。** `wss://` 就是在 TLS 上做同样的事。只需要服务器往下推、不需要客户端往上发的场景，也可以用 Server-Sent Events：一个不结束的 HTTP 响应，服务器有事就往里写一段。
