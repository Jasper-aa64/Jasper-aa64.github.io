---
title: "交易系统笔记 #3:内存池与分配器"
date: 2026-09-17
slug: "hot-path-memory-allocators"
description: "为什么 malloc/free 真正的问题是方差而不是速度——以及四种越来越通用的办法,保证热路径上没有任何事是第一次发生:O(1) 的空闲链表对象池、锁定并预先缺页的内存、自定义 STL 分配器背后的 bump 指针 arena,以及 std::pmr 这个运行时版本的替代方案。最后给出两个把前面技术合在一起的参考实现。"
summary: "这篇里的每一种技术,都是在不同的层面上做同一件事:把一个不确定的、牵涉内核的操作从热路径上挪走,强制它在开头一次性发生完,不让它伏击任何一个请求。对象池用永远 O(1) 的空闲链表,换掉 malloc 那种耗时可变的搜索。mlockall 加上仔细的 mallopt 调优,阻止内核悄悄把页收回——预先缺页则补上 mlock 单独留下的那个口子。手写的 arena 分配器让 STL 本身配合一个由 bump 指针内存支撑的自定义分配器。std::pmr 用标准库的方式解决同一个「让 STL 配合」的问题——拿编译期的速度换运行时的灵活。"
categories: [Systems]
tags: [cpp, memory-pool, allocator, mlock, tlb-shootdown, pmr, hft, low-latency, stl]
toc: true
homepage: false
---

`malloc` 和 `free` 并不慢。在一个紧循环里调一千次,平均耗时看起来完全没问题。HFT 代码和它们的矛盾不在平均值,而在**尾部**,而尾部取决于你控制不了的状态。glibc 为了避免锁竞争,给每个线程分 arena,可线程数一旦超过 arena 数,两个线程就开始抢同一个 arena 的锁。当前 arena 满足不了的请求,可能意味着一次新的 `brk` 或 `mmap` 系统调用进内核。释放的内存被分进按大小划分的 bin 里,要遍历、可能还要合并,这要花多久,取决于这个堆之前经历过的全部碎片化历史。这些代价没有一个是固定的,全都取决于"这个进程到目前为止干过什么"——而这恰恰是热路径问不起的问题。

这篇里的一切,都是同一个修法的变奏:找出那个代价取决于首次访问、竞争或碎片化的操作,**把它挪到程序生命里你不在乎它花多久的那个时刻**——通常是启动时。第 1 节挪走分配本身。第 2 节挪走内核的两个决定:你的页能不能离开内存,以及——不那么显然的——它们到底有没有物理内存撑着。第 3、4 节把这一招推广到任意 STL 容器,并在"灵活性的账该在哪里付"上分道扬镳:编译期,还是运行时。第 5 节把有用的部分合成两个参考实现。

---

## 1. 对象池:用一个指针换掉一次搜索

"我不想在热路径上调 malloc"的修法简单得几乎有点尴尬:启动时把你将来需要的一切一次分配好,需要时从这块预分配的内存里切一块出去、用完再收回来。这就是对象池——某个类型 `T` 的固定数量的实例,放在程序已经拥有的内存里。

### 1.1 朴素版本得的是同一种病,只是小一号

```cpp
struct ObjectBlock {
  T object_;
  bool is_free_ = true;
};
std::vector<ObjectBlock> store_;
size_t next_free_index_ = 0;
```

`allocate()` 在 `store_[next_free_index_]` 上原地构造,标记为已占用,然后调 `updateNextFreeIndex()` 为下一次找*下一个*空闲槽——从当前位置往后扫,到尾部再绕回来。在接近先进先出的访问模式下,下一个槽通常就是空的,扫描几乎立刻停下。但没有任何东西保证这种模式。乱序持有对象、乱序释放,扫描就可能走遍整个池才找到一个空位——**最坏 O(n),而这个最坏情况,和这个池本来要替换掉的、取决于碎片化的代价一样不可预测。** 进内核的往返是消掉了,池子里又长回来一个更小的、同样形状的问题。

### 1.2 修法:不去找,而是一直维护着

```cpp
T* objects_;
std::size_t* free_list_;
std::size_t next_free_index_;                    // 空闲链表的头
static constexpr std::size_t kInvalidIndex = -1;  // 链表结束标记
```

`free_list_` 是一条空闲槽的链表——但它用**数组下标而不是指针**实现。`free_list_[i]` 记的不是"槽 `i` 空不空",而是"如果 `i` 是链表头,它后面是哪个槽"。`next_free_index_` 就是那个链表头。`allocate()` 拿走 `next_free_index_` 当前指向的那个槽,再把链表头移到 `free_list_[那个槽]`——一次读,一次写,不扫描。`deallocate()` 用同样的方式把释放的槽推回链表头。两个操作**每一次都是完全相同的那几条指令**,因为空闲链表在每次调用时都被增量维护着——等你调用 `allocate()` 时,"下一个空闲槽是哪个"已经躺在一个变量里了,不需要去找。

这一点值得说准确,因为它常被叫错:这**不是侵入式链表**。侵入式链表把 `next` 指针存在*载荷类型本身*里面——对象自己兼作节点。这里的 `free_list_` 是一个和 `objects_` 并行的、完全独立的数组;`T` 根本不知道自己被链进了什么东西。真正侵入式的版本,会把"下一个空闲下标"用 `union` 放进一个还没构造的 `T` 本来要占的那块内存里,省掉第二个数组,代价是所有权关系没那么一目了然——这是一个真实的"内存 vs 简单"取舍,参考实现选择了不做。

还有一个值得保留的布局细节:`ObjectBlock` 把 `T` 和 `is_free_` 打包进一个结构体,而不是两个并行数组。一次 `allocate()` 会同时碰这两个字段,把它们放在一起,一次缓存行读取就够了,而不是两次落在不相干的行上的独立读取。

---

## 2. 锁住还不够:mmap 陷阱和 TLB shootdown 税

对象池解决的是"热路径上别向分配器要内存"。它管不了第二种、很容易漏掉的失败方式:你已经拿到的内存,仍然可能被收走,或者在你第一次碰它时给你一个意外。

### 2.1 光靠 mlockall 有个漏洞

`mlockall(MCL_CURRENT | MCL_FUTURE)` 告诉内核:这个进程现在持有的每一页、以后会持有的每一页,都常驻内存——永不换出。听上去很完整。其实不然,因为一个细节:**`munmap` 不是给一页解锁,而是把锁所依附的整个映射拆掉。** glibc 把大于 `M_MMAP_THRESHOLD`(默认 128 KB)的分配走 `mmap` 而不是堆,`free()` 这块内存时立刻对它调 `munmap`——这块分配一释放,`mlockall` 给过的保证就悄无声息地没了。

![前后对比:台座上一个用链子锁住的保险箱;之后同一个台座上箱子整个不见了——只剩那条仍然锁着的链子和挂锁悬在它原来的位置](/images/hot-path-allocators/torn-down-not-unlocked.jpg)

堵上这个漏洞要三次 `mallopt` 调用,每一次堵住一条不同的回内核的路:

- **`M_MMAP_MAX = 0`**——彻底禁止 mmap 这条路。不管多大的分配都走堆;`free()` 只剩记账,永远不调 `munmap`。
- **`M_TRIM_THRESHOLD = -1`**——同样的想法用在堆本身。默认情况下,堆顶积累了足够多的连续空闲空间后,glibc 会用 `sbrk` 把堆往回缩、还给操作系统;这个设置把它关掉,堆顶一大块释放出来的空间永远不还回去。
- **`M_ARENA_MAX = 1`**——另一个维度:多个工作 arena 本身就由额外的 `mmap` 区域支撑。强制只用一个 arena(反正分配只在启动时发生,多 arena 的并发好处在这里没有意义),一开始就去掉了这些额外的 mmap 来源。

### 2.2 isolcpus 替你挡不住的税:TLB shootdown

任何页表变更——`munmap`、`mprotect`,或者内核自己的透明大页后台合并——都会引发一次 **TLB shootdown**:做变更的那个核不知道别的哪些核缓存了这条已经过期的地址翻译,于是给最近运行过这个进程地址空间的每一个核广播一个核间中断(IPI)。每个核都得停下来、陷入内核、作废受影响的 TLB 条目、再继续——微秒级,而且随共享这个地址空间的核数增长。

尖锐又容易弄错的一点是:**`isolcpus` 挡不住它。** `isolcpus` 工作在调度器这一层——它控制调度器会不会把*任务*放到某个核上。TLB shootdown 是一个硬件中断,按内核为这个地址空间记录的 `mm_cpumask` 里有哪些核来投递——一个调度器根本说不上话的、完全不同的机制。一个完美隔离、绑好核的热线程,照样可能被同一进程里的一个*冷*线程调用 `munmap` 或 `mprotect` 打断,因为两个线程共享同一个 `mm_struct`,而 shootdown 瞄准的是地址空间,不是调度类别。这也是调优过的系统要关掉 THP 和自动 NUMA 均衡的更深一层原因,不只是"后台合并带来不可预测的延迟"——两者都会频繁改写页表,而每一次改写都是一次 shootdown,会打到调度器被告知永远别碰的那些核上。

---

## 3. STL 背后的 arena:一个只往前走的指针

对象池只发一种类型 `T`。真实的热路径代码想用 `std::vector`、`std::string` 这些普通 STL 容器——又不想让这些容器碰全局堆。这就意味着要写一个满足 C++ 分配器接口、背后是程序已经拥有的内存的东西。

### 3.1 一个只往前走的指针

```cpp
struct MemoryBlock {
  size_t used, capacity;
  bool is_active;
  // ...
};
```

arena 从一块预留好的内存里分配,只跟踪一个数:这块内存已经用掉了多少字节。`allocate(size)` 把当前写入位置向上取整到要求的对齐,检查 `used + size` 还装不装得下 `capacity`,装得下就直接推进 `used`、返回旧位置——不用搜索,因为根本没什么可搜的:"下一个空闲位置"永远就是指针现在所在的地方。一块用满了,arena 用同样的方式启用下一块预留的内存。这比第 1 节的空闲链表还要便宜——连链表指针交换都没有,就是一次加法——代价是没办法从中间释放单独一次分配。没有任何东西记录每次分配从哪开始、到哪结束,所以就算你想释放一个也无从查起。唯一的回收操作是全局的:把每一块的 `used` 都倒回零,从头再来。对于一批生命周期完全相同的对象——处理一个 tick 时分配的所有东西,tick 处理完一起扔掉——这是正确的取舍;对于生命周期参差的对象则不然,它们还是属于第 1 节的池。

### 3.2 预先缺页:补上 mlock 在首次访问时留下的口子

arena 背后的内存在构造时一次拿到,用 `posix_memalign` 和 `mlock()`——这次只锁 arena 自己的这块区域,比第 2 节全进程的 `mlockall` 更精准。但一段新拿到的虚拟地址范围,背后还没有物理内存:Linux 懒惰地映射页,真正的物理页要到**第一次写**时才分配,通过一次陷入内核的缺页。`mlock` 保证一页一旦有了物理内存就不会被换出——它不管映射建立了没有。构造函数用一行补上这个口子:`memset(raw_memory, 0, total_size)`,在启动时把每一页碰一遍,所有本来会发生的缺页都已经发生过了。等热路径运行时,arena 里的每一页不只是锁住了,而且*已经映射好了*——没有任何东西要第一次被发现。

把这个 arena 适配到 STL 接口(`allocate`/`deallocate`/`construct`/`destroy`/`rebind`)的分配器,大部分是样板代码,知道它存在就够了,不必细究——只有一个例外:`deallocate()` 被故意写成空操作,原因和 `reset()` 是唯一回收内存的办法一样。单个对象的构造和析构仍然通过 `construct`/`destroy` 正常发生;被废掉的只有契约里"内存"的那一半。

---

## 4. std::pmr:同一个答案,在运行时付钱

### 4.1 把分配器从类型里挪出去

第 3 节的自定义分配器有一个类型系统不会提醒你的锋利边缘:`std::vector<int>` 和 `std::vector<int, LowLatencyAllocator<int>>` 是两个毫不相干的类型。分配器是模板参数——是容器类型的一部分,不是一个运行时设置——所以一个写成接收 `std::vector<int>&` 的函数,会直接拒绝 arena 版本,每个需要两者都接收的函数也得在分配器上模板化。

`std::pmr`(C++17)用相反的方式解决同一个"让 STL 用我的分配策略"的问题:把策略的选择从类型里挪出去,放进一个运行时指针。`std::pmr::memory_resource` 是一个抽象基类——`do_allocate`、`do_deallocate`、`do_is_equal`——任何具体的分配策略都通过继承它来表达。所有 `std::pmr` 容器都用同一个统一的 `std::pmr::polymorphic_allocator<T>`,它里面只有一个 `memory_resource*`;因为这个指针具体指向什么不是类型的一部分,`std::pmr::vector<int>` 不管背后是哪个 resource,永远是同一个类型——随便传、随便赋值、随便返回,不用任何模板体操。代价在每一次分配时付:通过那个指针的一次虚调用,运行时分派,而第 3 节的版本里具体的分配器类型在编译期就知道,可以被完全内联掉。这正是 C++ 程序员在虚函数和模板之间早就在权衡的静态多态 vs 动态多态,只是这次用在了内存本身上。

### 4.2 标准库自带的 resource,对应第 1 节和第 3 节

标准库自带了几个 resource,直接对应前面讲过的东西:

- **`monotonic_buffer_resource`** 就是标准化的第 3 节 arena:只往前分配,一起释放,不能单独回收。它甚至接受调用者提供的初始缓冲区(比如栈上的一个 `std::array`),外加一个溢出时用的后备 resource——标准库版本的 `allow_fallback_` 参数。
- **`unsynchronized_pool_resource`** 更接近第 1 节的池,推广到了多种对象大小而不是一个固定类型,按大小类别管理成一个个 "slab"。
- **`synchronized_pool_resource`** 是上面那个的线程安全版——名字已经说明了它的代价:一把锁,正是这整篇文章想要避免的那一类竞争。

### 4.3 生命周期陷阱

`std::pmr::vector` 看上去和普通的值类型一模一样——按值返回一个,似乎和返回任何别的 `std::vector` 一样安全。并不是,原因很具体:`polymorphic_allocator` 只是*指向*它的 `memory_resource`,从不拥有它。如果那个 resource 是一个局部变量,返回 vector 对延长 resource 的生命周期毫无帮助:

```cpp
auto create_vec() -> std::pmr::vector<int> {
  auto resource = PrintingResource{};           // 局部变量,出作用域就销毁
  auto vec = std::pmr::vector<int>{&resource};  // vec 只存了 &resource
  return vec;                                   // resource 在这里被销毁
}
auto vec = create_vec();
vec.emplace_back(1);  // 未定义行为
```

`vec` 本身干干净净地移出来了——没有深拷贝,返回这一步看不出任何问题。危险在调用处是看不见的,恰恰因为 `std::pmr::vector<int>` 摆出和 `std::vector<int>` 一样的值语义,却并不拥有它的正确性所依赖的那个东西。这逼出来的规则毫不起眼,但没有例外:`memory_resource` 的生命周期必须长过建在它上面的每一个容器——这通常意味着它得住在一个严格更外层的作用域里,绝不能放在那个只是构造并返回容器的函数里面。

---

## 5. 合在一起:两个参考实现

上面几节里,有两种形状值得保留成完整、可复用的参考:一个给生命周期各自独立的对象用的固定类型池,一个给一批一起扔掉的对象用的 arena。`std::pmr` 不算第三个——它解决的是类型兼容的问题,不是性能问题,而每次分配都付一次虚调用,让它对于真正要放在热路径上的东西来说,是比这两者都差的默认选择。只有当那份灵活值得这个具体的代价时才用它。

往回看一眼,上面每一节其实都是在不同的层面上重新问同一个问题:*这块存储到底从哪来,谁在管它?*
<svg viewBox="0 0 640 1180" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="从 malloc/free 不可预测的延迟,到对象池 v1 的线性扫描被 v2 的空闲链表取代,到分配器环境调优,到 arena 的 bump 指针,再到 STL 分配器和 std::pmr——终点是内存策略与容器类型解耦" style="max-width:100%;height:auto;font-family:'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',ui-sans-serif,system-ui,sans-serif">
  <style>
    .bg  { fill: #fbfaf7; }
    .ink { fill: #1c1b18; }
    .muted { fill: #6b6558; }
    .title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .boxN  { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .boxGone { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; stroke-dasharray: 4 3; opacity: 0.8; }
    .boxGo   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 2; }
    .edge     { stroke: #b3ab98; stroke-width: 1.6; fill: none; marker-end: url(#ahN2z); }
    .edgeGone { stroke: #b3ab98; stroke-width: 1.4; fill: none; stroke-dasharray: 4 3; opacity: 0.75; marker-end: url(#ahN2z); }
    .edgeGo   { stroke: #6f8f3f; stroke-width: 2; fill: none; marker-end: url(#ahGo2z); }
    @media (prefers-color-scheme: dark) {
      .bg  { fill: #17161b; }
      .ink { fill: #e9e7ef; }
      .muted { fill: #a19caf; }
      .title { fill: #e9e7ef; }
      .boxN  { fill: #201f26; stroke: #3a3945; }
      .boxGone { fill: #2a2933; stroke: #47454f; }
      .boxGo   { fill: #33421f; stroke: #8fb257; }
      .edge     { stroke: #55525f; }
      .edgeGone { stroke: #55525f; }
      .edgeGo   { stroke: #8fb257; }
    }
  </style>
  <defs>
    <marker id="ahN2z" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ahGo2z" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#6f8f3f"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="640" height="1180" rx="10"/>
  <text class="title" x="20" y="26">从池到 pmr:同一个问题——存储从哪来——</text>
  <text class="title" x="20" y="42">五种不同的回答</text>
  <rect class="boxN" x="180" y="56" width="280" height="56" rx="8"/>
  <text class="ink" x="320" y="80" font-size="14" font-weight="700" text-anchor="middle">malloc / free</text>
  <text class="muted" x="320" y="98" font-size="11" text-anchor="middle">不可预测、耗时可变</text>
  <path class="edge" d="M320,112 L320,154"/>
  <rect class="boxN" x="190" y="156" width="260" height="50" rx="8"/>
  <text class="ink" x="320" y="180" font-size="14" font-weight="700" text-anchor="middle">对象池</text>
  <text class="muted" x="320" y="197" font-size="11" text-anchor="middle">第 1 节</text>
  <path class="edgeGone" d="M300,206 L170,246"/>
  <path class="edgeGo" d="M340,206 L470,246"/>
  <rect class="boxGone" x="40" y="248" width="240" height="64" rx="8"/>
  <text class="muted" x="160" y="272" font-size="12.5" font-weight="700" text-anchor="middle">v1 · 线性扫描</text>
  <text class="muted" x="160" y="290" font-size="10.5" text-anchor="middle">O(N) · 被 v2 取代</text>
  <rect class="boxGo" x="360" y="248" width="240" height="64" rx="8"/>
  <text class="ink" x="480" y="272" font-size="12.5" font-weight="700" text-anchor="middle">v2 · 显式空闲链表</text>
  <text class="ink" x="480" y="290" font-size="10.5" text-anchor="middle">O(N) → O(1)</text>
  <path class="edgeGo" d="M460,312 L340,354"/>
  <rect class="boxN" x="170" y="356" width="300" height="64" rx="8"/>
  <text class="ink" x="320" y="380" font-size="14" font-weight="700" text-anchor="middle">侵入式空闲链表</text>
  <text class="muted" x="320" y="398" font-size="10.5" text-anchor="middle">next 住在 T 里面,不需要额外节点</text>
  <path class="edge" d="M320,420 L320,450"/>
  <rect class="boxN" x="160" y="452" width="320" height="50" rx="8"/>
  <text class="ink" x="320" y="476" font-size="13.5" font-weight="700" text-anchor="middle">收紧对分配器的控制</text>
  <text class="muted" x="320" y="493" font-size="11" text-anchor="middle">第 2 节</text>
  <path class="edge" d="M300,502 L160,542"/>
  <path class="edge" d="M340,502 L480,542"/>
  <rect class="boxN" x="40" y="544" width="240" height="64" rx="8"/>
  <text class="ink" x="160" y="568" font-size="12.5" font-weight="700" text-anchor="middle">glibc 调优</text>
  <text class="muted" x="160" y="586" font-size="10" text-anchor="middle">M_MMAP_MAX=0 · M_TRIM_THRESHOLD=-1</text>
  <rect class="boxN" x="360" y="544" width="240" height="64" rx="8"/>
  <text class="ink" x="480" y="568" font-size="12.5" font-weight="700" text-anchor="middle">mlockall</text>
  <text class="muted" x="480" y="586" font-size="10" text-anchor="middle">锁在内存里 · swappiness=0</text>
  <path class="edge" d="M180,608 L300,650"/>
  <path class="edge" d="M460,608 L340,650"/>
  <rect class="boxN" x="170" y="652" width="300" height="50" rx="8"/>
  <text class="ink" x="320" y="682" font-size="13.5" font-weight="700" text-anchor="middle">一个稳定的内存环境</text>
  <path class="edge" d="M320,702 L320,738"/>
  <rect class="boxN" x="190" y="740" width="260" height="50" rx="8"/>
  <text class="ink" x="320" y="764" font-size="14" font-weight="700" text-anchor="middle">arena 分配器</text>
  <text class="muted" x="320" y="781" font-size="11" text-anchor="middle">第 3 节 · bump 指针 arena</text>
  <path class="edge" d="M320,790 L320,826"/>
  <rect class="boxN" x="170" y="828" width="300" height="56" rx="8"/>
  <text class="ink" x="320" y="852" font-size="14" font-weight="700" text-anchor="middle">bump 指针</text>
  <text class="muted" x="320" y="870" font-size="10.5" text-anchor="middle">只往前走 · O(1) 分配</text>
  <path class="edge" d="M320,884 L320,920"/>
  <rect class="boxN" x="150" y="922" width="340" height="50" rx="8"/>
  <text class="ink" x="320" y="946" font-size="13.5" font-weight="700" text-anchor="middle">STL 分配器</text>
  <text class="muted" x="320" y="963" font-size="10" text-anchor="middle">自定义分配器 · 编译期多态</text>
  <path class="edge" d="M320,972 L320,1008"/>
  <rect class="boxN" x="190" y="1010" width="260" height="56" rx="8"/>
  <text class="ink" x="320" y="1034" font-size="14" font-weight="700" text-anchor="middle">std::pmr</text>
  <text class="muted" x="320" y="1052" font-size="10.5" text-anchor="middle">第 4 节 · 运行时多态</text>
  <path class="edgeGo" d="M320,1066 L320,1100"/>
  <rect class="boxGo" x="90" y="1102" width="460" height="64" rx="8"/>
  <text class="ink" x="320" y="1126" font-size="14" font-weight="700" text-anchor="middle">内存策略与容器类型解耦</text>
  <text class="ink" x="320" y="1144" font-size="10.5" text-anchor="middle">"内存从哪来"和"怎么管"彼此独立</text>
</svg>

### 5.1 一个参考对象池

第 1、2 节可以干净地合成一个独立的东西:一个 alloc/dealloc 都是 O(1) 的固定类型池,背后的内存在热路径运行之前就预分配、预先缺页、锁好了。比第 1 节两个版本都多一处改进:不再单独用一个 `free_list_` 数组,"下一个空闲槽"的下标*就住在*和 `T` 同一个槽里,一次分配只碰一条缓存行,而不是两个不相干的数组。

```cpp
template <typename T>
class ObjectPool {
  struct Slot {
    alignas(T) unsigned char storage[sizeof(T)];  // 构造之后 T 就住在这里
    std::size_t next_free;                        // 空闲链表的链接,和 T 放在一起
  };
  static constexpr std::size_t kInvalid = static_cast<std::size_t>(-1);

  Slot* slots_;
  std::size_t capacity_;
  std::size_t free_head_ = 0;

 public:
  explicit ObjectPool(std::size_t capacity) : capacity_(capacity) {
    std::size_t bytes = sizeof(Slot) * capacity_;
    slots_ = static_cast<Slot*>(std::aligned_alloc(alignof(Slot), bytes));
    if (!slots_) throw std::bad_alloc{};

    mlock(slots_, bytes);            // 永不换出(生产上要检查返回值——
    std::memset(slots_, 0, bytes);   // 需要 CAP_IPC_LOCK / RLIMIT_MEMLOCK);memset 现在就把每一页缺页一遍

    for (std::size_t i = 0; i < capacity_; ++i)
      slots_[i].next_free = (i + 1 < capacity_) ? i + 1 : kInvalid;
  }

  ~ObjectPool() {
    munlock(slots_, sizeof(Slot) * capacity_);
    std::free(slots_);
  }

  ObjectPool(const ObjectPool&) = delete;
  ObjectPool& operator=(const ObjectPool&) = delete;

  template <typename... Args>
  T* allocate(Args&&... args) {
    if (free_head_ == kInvalid) return nullptr;      // 池用完了——热路径上不抛异常
    Slot& slot = slots_[free_head_];
    free_head_ = slot.next_free;                     // O(1):下一个槽早就知道了
    return ::new (slot.storage) T(std::forward<Args>(args)...);
  }

  void deallocate(T* obj) {
    obj->~T();
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));
    std::size_t index = slot - slots_;
    slot->next_free = free_head_;                    // 推回空闲链表头
    free_head_ = index;
  }
};
```

每一部分具体来自哪里:`next_free` 放在 `Slot` 里面的布局和链表头交换,是第 1 节的空闲链表;`aligned_alloc` + `mlock` + 一开始就 `memset`,是第 2 节的"别让内核把它收走,也别在第一次碰它时缺页"。

### 5.2 一个参考 arena

上面的池一个个地发一种类型,对象的生命周期各自独立。arena 用于相反的形状:一批分配——大小可能不同、类型可能不同——一起释放。启动时的处理和池一样(一次分配、`mlock`、`memset` 预先缺页),但分配逻辑本身更简单:根本没有空闲链表要维护,只有一个不断往前走的偏移。

```cpp
class Arena {
  unsigned char* base_;
  std::size_t capacity_;
  std::size_t used_ = 0;
  bool allow_malloc_fallback_;

 public:
  explicit Arena(std::size_t capacity, bool allow_malloc_fallback = false)
      : capacity_(capacity), allow_malloc_fallback_(allow_malloc_fallback) {
    base_ = static_cast<unsigned char*>(
        std::aligned_alloc(alignof(std::max_align_t), capacity_));
    if (!base_) throw std::bad_alloc{};

    mlock(base_, capacity_);           // 和池一样的锁定 + 预先缺页
    std::memset(base_, 0, capacity_);  // (生产上要检查 mlock 的返回值)
  }

  ~Arena() {
    munlock(base_, capacity_);
    std::free(base_);
  }

  Arena(const Arena&) = delete;
  Arena& operator=(const Arena&) = delete;

  void* allocate(std::size_t size, std::size_t alignment = alignof(std::max_align_t)) {
    std::size_t aligned_used = (used_ + alignment - 1) & ~(alignment - 1);
    if (aligned_used + size > capacity_) {
      return allow_malloc_fallback_ ? std::malloc(size) : nullptr;  // arena 用完了
    }
    void* ptr = base_ + aligned_used;
    used_ = aligned_used + size;
    return ptr;
  }

  void reset() noexcept { used_ = 0; }  // 唯一的回收办法——整批,不是逐个
};
```

`allocate()` 用四行就是 bump 分配器的全部思想:把当前偏移向上取整到要求的对齐,检查还装得下,推进偏移,返回旧的那个。没有搜索,没有链表要维护——"下一个空闲位置"永远就是 `used_`。`reset()` 是唯一的回收路径,和 arena 的整个前提一致:它不跟踪单次分配,所以没法单独释放一个。相比第 3 节的多块设计,这里有一处有意的简化:一块固定容量的缓冲区,而不是一串预留的块——更容易写对,代价是有一个硬性的容量上限,不能继续增长。`allow_malloc_fallback_` 就是第 3 节的 arena 为这个上限准备的同一个逃生口。

对象生命周期各自独立、一个一个释放,选池。一整批东西——处理一个 tick、一笔订单、一个请求时碰过的所有东西——共享同一个生命周期、作为一个整体扔掉,选 arena。
