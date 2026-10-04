---
title: "交易系统笔记 #5:共享内存里的 SPMC 广播环"
date: 2026-10-04
slug: "spmc-shared-memory-broadcast-ring"
description: "一个生产者、多个读者、每个读者都要看到每一条、生产者永远不等:每个槽位自带序号戳,读者各持私有游标,一次回绕安全的减法有三种含义——代价改由读者承担:无声的套圈、撕裂读、读者越多生产者照样越慢,以及共享内存里地址、第一圈缺页和重启的坑。"
summary: "行情只有一个生产者,却有好几个消费者,每个都要看到每一条,而生产者是热路径,不能等任何人。答案是广播环:每个槽位自带序号戳,读者各持私有游标,生产者写满一圈就覆盖最老的槽位,从不读读者的状态。代价转给了读者:套圈是无声的;读完再复查一次戳,只有在写者先作废戳的前提下才抓得到写了一半的槽位;忙轮询的读者仍然让每次写变贵。放进共享内存再加三条:元素里不能有任何指针,第一圈每 32 条碰一次缺页,读者重启不存游标就全丢。"
categories: [Systems]
tags: [cpp, lock-free, spmc, shared-memory, ring-buffer, atomics, market-data, hft, low-latency]
toc: true
homepage: false
---

交易所的 Level-2 行情是从一个回调线程里进来的:逐笔成交、逐笔委托,行情一忙起来每秒几万条。下游的消费者不止一个——一个把每条都落盘,一个转发到 MQTT,一个做实时分析——而且**每个都要收到每一条**。

怎么把一条消息交给三个人?最先想到的是 [#4](/zh/posts/lock-free-queue-logger-micro-batching/)里的 SPSC 队列:开三个,生产者每条写三遍。但 SPSC 的生产者要读消费者的位置,才知道队列满没满;任何一个读者慢下来、队列一满,生产者就只能丢消息或者等。而这里的生产者是行情热路径,**一刻都不能等任何一个读者**。

这篇讲一个五十行左右的答案:SPMC 广播环。思路一句话就能说完——把"这条消息已经发布"的信号,从一个所有人共享的下标,挪进每个槽位里。但这一挪带来的后果,要一节一节讲:第 1 部分讲环本身,以及它不保证什么;第 2 部分讲把它放进进程之间的共享内存,会多出哪些坑。

## 1. 广播环:一个生产者,多个读者

### 1.1 数据结构:一圈带戳的槽位

这个设计是一个小巧的开源环形队列(MengRao 的 SPMC_Queue),全部大约五十行:

```cpp
#include <atomic>
#include <cstdint>

template<class T, uint32_t CNT>
class SPMCQueue {
public:
    static_assert(CNT && !(CNT & (CNT - 1)), "CNT must be a power of 2");

    struct Reader {
        operator bool() const { return q; }
        T* read() {
            auto& blk = q->blks[next_idx % CNT];
            uint32_t new_idx = ((std::atomic<uint32_t>*)&blk.idx)->load(std::memory_order_acquire);
            if (int(new_idx - next_idx) < 0) return nullptr;   // 还没有新消息
            next_idx = new_idx + 1;
            return &blk.data;
        }
        T* readLast() {                                         // 读到没有为止,只留最新一条
            T* ret = nullptr;
            while (T* cur = read()) ret = cur;
            return ret;
        }
        SPMCQueue<T, CNT>* q = nullptr;
        uint32_t next_idx;                                      // 这个读者私有
    };

    Reader getReader() {                                        // 从"下一条"开始
        Reader reader;
        reader.q = this;
        reader.next_idx = write_idx + 1;
        return reader;
    }

    template<typename Writer>
    void write(Writer writer) {
        auto& blk = blks[++write_idx % CNT];
        writer(blk.data);                                       // 原地填槽位
        ((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release);  // 最后盖戳
    }

private:
    struct alignas(64) Block {
        uint32_t idx = 0;                                       // 这个槽位里是第几条消息
        T data;
    } blks[CNT];
    alignas(128) uint32_t write_idx = 0;
};
```

读任何一个函数之前,先注意三件事:

- **戳 `idx` 在每个槽位里。** 每个块自己记着"我现在装的是第几条消息"。发布信号不再是一个所有人都读的共享下标,而是跟着数据走。后面的一切都由此而来。
- **`write_idx` 是普通的 `uint32_t`,不是原子量。** 只有生产者写它;`getReader()` 建读者时读一次。
- **`CNT` 是 2 的幂**,所以 `% CNT` 编译成掩码([#4](/zh/posts/lock-free-queue-logger-micro-batching/) 的技巧)。戳是 32 位的,写到约 42.9 亿条会回绕;`read()` 里的比较就是为此写的。

用它原本服务的 Level-2 逐笔成交记录(88 字节)算:一个 `Block` 是 4 字节戳 + 4 字节填充 + 88 字节数据 = 96,`alignas(64)` 再补到 **128 字节,正好两条缓存行**。`CNT = 524288` 时,一个队列 64 MiB。

`alignas(64)` 让相邻的槽位不共用缓存行,生产者写第 *i* 块时,不会拽走读者正在用的第 *i − 1* 块所在的行(伪共享,[#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/))。`write_idx` 对齐到 128 而不是 64,常见的解释是有些 CPU 会成对预取相邻的两条缓存行;设计本身没说明,当成"可能的原因"而不是"写明的原因"。

---

### 1.2 生产者:先写数据,最后盖戳

```cpp
auto& blk = blks[++write_idx % CNT];
writer(blk.data);                                                                  // ① 调用者的 lambda 填槽位
((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release); // ② 再给这个槽位盖上新序号
```

这就是 [#4](/zh/posts/lock-free-queue-logger-micro-batching/) 的两步交接——先原地写,再发布——只是"发布"从推进一个共享下标,变成了给这个槽位盖戳。

而且生产者**从不读任何读者写的东西**。没有"满了"这回事:写满一圈就覆盖最老的槽位。所以它从不等待,走的步数也和有多少读者、读者多慢无关。

---

### 1.3 读者:一次减法,三种含义

`Reader` 里只有一个指向队列的指针和它自己的 `next_idx`——"我下一条想要第几条"。它放在读者自己的内存里,读者从不往队列里写。读者之间没有竞争,多一个或少一个读者,生产者的执行路径一步都不变。

`read()` 去看第 `next_idx` 条消息应该在的那个槽位,拿槽位里的戳 `new_idx` 和自己想要的比。用一张图看最直观:同一时刻,三个读者落后的程度不同,看到的正好是三种情形。

<a href="/images/spmc-ring/ring.zh.svg" target="_blank" rel="noopener"><img src="/images/spmc-ring/ring.zh.svg" alt="CNT = 8 的环,生产者写到第 11 条;读者 A 还没等到、读者 B 正好拿到、读者 C 被套圈跳过第 2–9 条" loading="lazy" decoding="async"></a>

把图里的三种情形写成规则:

| `int(new_idx - next_idx)` | 意思 | `read()` 做什么 |
|---|---|---|
| **< 0** | 槽位里还是上一圈的消息,生产者还没写到我要的那条 | 返回 `nullptr` |
| **== 0** | 正好是我在等的那一条 | 返回它,`next_idx = new_idx + 1` |
| **> 0** | 生产者已经套了我一圈,这个槽位装的是**更新的**消息 | 返回这条更新的,`next_idx = new_idx + 1`——**中间的全部跳过** |

两个细节撑起了大部分分量。

**为什么写 `int(new_idx - next_idx) < 0`,而不是 `new_idx < next_idx`。** 戳在 2³² 回绕。按无符号相减、再把差当有符号数看,只要两者相差不到 2³¹,回绕前后大小关系都对。直接比较在回绕点会判反:`next_idx = 0xFFFFFFFE`,回绕后新戳是 `1`,有符号差值是 +3——有新数据,对;而 `1 < 0xFFFFFFFE` 会说"还没写"。

**正的差值一定是 `CNT` 的整数倍。** 槽位里的戳是消息序号,槽位的位置是序号 mod `CNT`,所以读者去看的那个槽位,戳只可能是 `next_idx`、`next_idx ± CNT`、`± 2·CNT`……实测 `CNT = 8`:读者存着 `next_idx = 6`,生产者已经写到 30,读者拿到的第一条是 30——差值 24 = 3 × 8。

另外两个入口出自同一条规则:`getReader()` 从 `write_idx + 1` 开始,所以**从不回放历史**(写了五条之后才建的读者,先拿到 `nullptr`,下一次写入后拿到第 6 条);`readLast()` 一直读到 `nullptr`,只留最新一条——给只要最新快照的消费者用。

### 1.4 内存序:戳就是发布信号

内存序是 [#2](/zh/posts/memory-ordering-false-sharing-dependency-chains/) 的 release/acquire 配对,搬进了槽位里:生产者用普通写填数据,再对戳做 release 存储;读者对戳做 acquire 读取,之后才读数据。读者一旦看到新戳,就一定看得到在它之前写好的数据。因为信号是每个槽位一份,任意多个读者都能各自判断,彼此之间没有任何可写的共享状态。

---

### 1.5 这个设计不保证什么

这笔交易现在看清楚了:**生产者谁也不等,后果由读者承担。** 后果有三个:套圈是无声的(1.5.1),复查抓不住写了一半(1.5.2),读者仍然让生产者变贵(1.5.3)。

#### 1.5.1 套圈是无声的

第一个后果是套圈。`CNT = 8`,读者一条没读,生产者已经写了 20 条,读者依次拿到 **17、18、19、20**。第 1–16 条从没送到——而队列不会告诉你。`read()` 只返回指针、直接改写 `next_idx`,调用方从返回值看不出跳过了什么。

信息其实现成:正的差值恰好就是跳过的条数。要它可见只需一行——让 `read()` 把差值报出来,或者在 `Reader` 里累加 `skipped += diff`。否则就得靠消息里自带的序号。

生产环境 `CNT = 524288`,读者要落后五十多万条才会被套圈。但每条消息都做慢事的读者——拼字符串、同步发 MQTT、`fprintf`——只要比行情慢,就在一点点靠近这条边界。

---

#### 1.5.2 复查看不见写了一半

`read()` 返回的是 `&blk.data`,一个指向共享槽位的指针,读者随后逐个字段去读。这期间生产者要是绕回来重写这个槽位,读者看到的就是新旧字段的混合:**撕裂读**。

直觉的修法是:复制完数据,再读一次戳,变了就丢掉这份拷贝。它不管用,原因值得记住。压力测试:`CNT = 4`,生产者全速写,每组三秒——故意最恶劣的设置,只为证明这件事存在:

| 情形 | 被接受的读取 | 其中撕裂 |
|---|---|---|
| 原样:拿到指针就读 | 59,869,704 | 3,269,273(约 5.5%) |
| 复制后再读一次 `idx`,变了就丢 | 43,942,557(另有 8,861,343 次被丢弃) | 2,084,572(约 4.7%) |
| 生产者**先作废戳**、再写数据、最后盖戳;读者复查 | 38,607,078(另有 6,436,383 次被丢弃) | **0** |

第二行就是教训。这个生产者先写数据、**最后**才改戳。重写进行到一半时,戳还是旧的,读者复查看到"没变",就放行了一份写了一半的记录。只有生产者在动数据之前先把旧戳毁掉,复查才有用:

```cpp
// 生产者:两步改成三步
((std::atomic<uint32_t>*)&blk.idx)->store(0, std::memory_order_relaxed);         // ① 先作废戳
std::atomic_thread_fence(std::memory_order_release);
writer(blk.data);                                                                 // ② 再写数据
((std::atomic<uint32_t>*)&blk.idx)->store(write_idx, std::memory_order_release); // ③ 最后盖新序号
// 读者:复制数据 → atomic_thread_fence(acquire) → 再读一次 idx;
//       只要不是复制前看到的那个序号,就丢掉这份拷贝
```

这样推理就闭合了:**戳还是旧的 ⇒ 数据一个字节都没被动过。** 复制和重写只要有任何重叠,戳要么是 0(正在重写),要么是新序号(已经写完),两种情况都丢弃。两道栅栏保证"戳先变、数据后动"和"先复制数据、后复查戳"在编译器和 CPU 面前都成立。(在 x86 上测的;严格按 C++ 内存模型,数据字段本身也要是原子量。)

这些是压力测试划出的边界,不是说原来的环在生产上天天撕裂。环够大、读者够快,它就很少发生。很少不等于没有。

---

#### 1.5.3 不阻塞不等于免费

"生产者从不读读者的状态"听上去能推出"读者拖慢不了生产者"。前半句对——生产者从不**等**;后半句不对。生产者全速写,读者在不同物理核上忙轮询(Ryzen 5 5600GT,Windows,三次 1 秒运行的中位数):

| 每次 `write()` 的 ns | 0 个读者 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 512 KiB 的环(放得进 L2),读者只轮询 | 2.8 | 18.5 | 24.0 | 25.3 | 26.4 | 28.0 |
| 512 KiB 的环,读者还读载荷 | 2.8 | 22.8 | 25.8 | 28.5 | 32.5 | 37.0 |
| 64 MiB 的环(生产环境的大小),读者只轮询 | 12.6 | 15.3 | 17.4 | 19.9 | 22.5 | 26.0 |
| 64 MiB 的环,读者还读载荷 | 12.6 | 20.1 | 26.8 | 29.8 | 33.8 | 38.7 |

第一个读者最贵:放得进 L2 的环里,生产者从独占所有行、2.8 ns 一条,变成 18.5 ns。之后每多一个读者,再多 1–5 ns。

读者不改变生产者的**步数**,改变的是每一步的硬件代价。读者轮询或读一个槽位,会在自己的核里留下这条行的只读副本;生产者再写这个槽位之前,这些副本必须作废——就是 [MESI 缓存一致性](/zh/posts/low-latency-mesi-cache-coherence/)里讲的 S→M 升级。生产者慢的时候,store buffer 把它藏住了:每 2 µs 写一条时,0 到 5 个读者下 `write()` 的中位数都是 10 ns(计时分辨率),变的只有尾部——p99.9 从 20 ns 涨到 70 ns。全速写时 store buffer 排不过来,才体现成吞吐下降。

所以准确的说法是:**读者再多也不会让生产者等,但读者不是免费的。**

---

## 2. 放进共享内存

### 2.1 `shmmap`:四个调用

部署时生产者和读者是不同的进程。环放进 POSIX 共享内存:

```cpp
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

template <class Q> Q* shmmap(const char* name) {
    int fd = shm_open(name, O_CREAT | O_RDWR, 0666);                          // ① 按名字打开(没有就创建)
    if (fd == -1) return nullptr;
    if (ftruncate(fd, sizeof(Q))) { close(fd); return nullptr; }              // ② 设成队列那么大
    Q* ret = (Q*)mmap(nullptr, sizeof(Q), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);  // ③ 映射进来
    close(fd);                                                                 // ④ 映射不受影响
    return ret == MAP_FAILED ? nullptr : ret;
}
```

- **名字相同,就是同一块内存。** Linux 上它在 `/dev/shm` 下(tmpfs,不落盘)。生产者和读者都用同一个名字调 `shmmap`。
- **没有构造函数会运行。** `mmap` 返回的只是一段被**当成** `Q` 来看的字节。队列靠"新内存全是 0"当空队列——`idx = 0`、`write_idx = 0` 就是空队列——而 `ftruncate` 保证新扩出来的部分是全 0。
- **它比进程活得久**,直到 `shm_unlink` 或重启。
- **一个队列,一个写者。** `++write_idx` 是普通自增,两个写者会互相踩。每路行情各一个队列。

### 2.2 同样的字节,不同的地址

最要紧的一条规则来自实际运行。两个进程映射同一个命名区域(用 Windows 上的对应物 `CreateFileMapping` + `MapViewOfFile` 实测):

```
[producer] view at 0000017987cc0000
[reader  ] view at 000001ae3be70000
[reader  ] m->self = 0000017987cc0048   vs my address of this block = 000001ae3be70048   (DIFFERENT)
```

消息全部送到,而且**同一块物理内存在两个进程里位于不同的虚拟地址**。存在区域里的指针——哪怕是指向区域自己的——到了另一边就是错的。指向字符串字面量的指针这次碰巧对上了,因为两个进程是同一个可执行文件、加载在同一个基址;换成不同的程序或开了地址随机化就不成立。别依赖它。

所以**共享内存里的元素必须自包含**:整数、浮点、定长数组。不能有任何指针——指向堆的、指向区域内部的、指向字面量的都不行,虚函数表指针也不行,所以不能有虚函数。这就是证券代码写成 `char SecurityID[31]` 而不是 `std::string` 的原因,而 `std::string` 是双重不行:长串的字节在写者进程的堆上;短串(小字符串优化)存着一个**指向自己内部缓冲**的指针——libstdc++ 实测 `&s` 结尾是 `…880`、`s.data()` 是 `…890`——区域映射到别的地址后它就指错了。

同样的道理还带出双方必须一致的其他"合同":同一份结构体定义、同样的编译方式(改了布局,旧的共享对象就对不上——换名字,或先 `shm_unlink`);`alignas` 照样有效,因为 `mmap` 返回页对齐的地址,队列又放在开头。

---

### 2.3 部署时的三个坑

#### 2.3.1 第一圈会缺页

共享内存按需分配:一个 4 KiB 页第一次被碰到时才分到物理页。一个槽位 128 字节,所以**每写 32 条就踩进一个新页**。实测(Windows 上 64 MiB 的映射;Linux tmpfs 机制相同,数字不同):

| | 第 1 圈:平均 / p99 | 第 2 圈:平均 / p99 |
|---|---|---|
| 新映射 | 56.1 ns / 1,302 ns | 8.6 ns / 10 ns |
| 开始前对每个 4 KiB 页写一个字节 | 9.0 ns / 10 ns | 8.8 ns / 10 ns |

每次缺页约 1.5 µs((56.1 − 9.0) × 32)。开盘前把每一页碰一遍,第一圈就和第二圈一样——和内存池([#3](/zh/posts/hot-path-memory-allocators/))同一条规矩:别让"第一次"发生在热路径上。

#### 2.3.2 慢读者会被套圈:余量 = 容量 ÷ 速率差

读者每条花的时间比生产者的间隔长,就在稳定地落后;落后满 `CNT` 条就被套圈、无声丢数据。能撑的秒数 = 524,288 ÷(行情速率 − 处理速率);读者完全停住时是 524,288 ÷ 行情速率——每秒 5 万条的话约 10.5 秒。把慢活移出 `read()` 循环(交给别的队列或线程),并监控落后量 `write_idx − next_idx`。

#### 2.3.3 读者重启会全丢,除非存了游标

`getReader()` 从下一条开始,所以 10:00:00 崩溃、10:00:03 重启的记录进程会无声地跳过三秒——每秒 5 万条就是 15 万条。`next_idx` 是公开的、读者私有的,可以存下来再恢复。实测 `CNT = 8`:

```
reader read 1..5, "crashed" with next_idx = 6; producer wrote 6..10
  rebuilt with getReader()       -> 10            (6..9 lost)
  resumed from saved next_idx    -> 6 7 8 9 10    (nothing lost)
saved cursor more than a lap behind (producer at 30)
  first read() returns 30, skipping 24 (= 3 laps); 23..29 were still in the ring but are never revisited
```

只要落后不到一圈,续读就一条不丢;游标要存在进程外面,否则跟着进程一起没了。对称的坑:**队列被重建了**(比如每个交易日前 `shm_unlink`),**老读者却还在跑。** 新戳从 0 开始,读者的游标是几百万,`int(new_idx - next_idx) < 0` 永远成立,`read()` 一直返回 `nullptr`——看上去是"没有新消息",实际是卡死,直到新戳追上来(实测:游标 1000,新写者写 1..999 期间什么都读不到)。重建队列时一起重启读者,或者检测"戳倒退了"。

