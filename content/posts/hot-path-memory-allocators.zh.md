---
title: "交易系统笔记 #3：内存池与分配器"
date: 2026-09-17
slug: "hot-path-memory-allocators"
description: "为什么 malloc/free 真正的问题是方差而不是速度——以及四种越来越通用的办法，保证热路径上没有任何事是第一次发生：O(1) 的空闲链表对象池、锁定并预先缺页的内存、自定义 STL 分配器背后的 bump 指针 arena，以及 std：：pmr 这个运行时版本的替代方案。最后给出两个把前面技术合在一起的参考实现。"
summary: "这篇里的每一种技术，都是在不同的层面上做同一件事：把一个不确定的、牵涉内核的操作从热路径上挪走，强制它在开头一次性发生完，不让它伏击任何一个请求。对象池用永远 O(1) 的空闲链表，换掉 malloc 那种耗时可变的搜索。mlockall 加上仔细的 mallopt 调优，阻止内核悄悄把页收回——预先缺页则补上 mlock 单独留下的那个口子。手写的 arena 分配器让 STL 本身配合一个由 bump 指针内存支撑的自定义分配器。std：：pmr 用标准库的方式解决同一个「让 STL 配合」的问题——拿编译期的速度换运行时的灵活。"
chapter: 1
categories: [Systems]
tags: [cpp, memory-pool, allocator, mlock, tlb-shootdown, pmr, hft, low-latency, stl]
toc: true
homepage: false
---

`malloc` 和 `free` 并不慢。在一个紧循环里调一千次，平均耗时看起来完全没问题。HFT 代码和它们的矛盾不在平均值，而在**尾部**，而尾部取决于你控制不了的状态。glibc 为了避免锁竞争，给每个线程分 arena，可线程数一旦超过 arena 数，两个线程就开始抢同一个 arena 的锁。当前 arena 满足不了的请求，可能意味着一次新的 `brk` 或 `mmap` 系统调用进内核。释放的内存被分进按大小划分的 bin 里，要遍历、可能还要合并，这要花多久，取决于这个堆之前经历过的全部碎片化历史。这些代价没有一个是固定的，全都取决于“这个进程到目前为止干过什么”——而这恰恰是热路径问不起的问题。

这篇里的一切，都是同一个修法的变奏：找出那个代价取决于首次访问、竞争或碎片化的操作，**把它挪到程序生命里你不在乎它花多久的那个时刻**——通常是启动时。第 1 节挪走分配本身。第 2 节挪走内核的两个决定：你的页能不能离开内存，以及——不那么显然的——它们到底有没有物理内存撑着。第 3、4 节把这一招推广到任意 STL 容器，并在“灵活性的账该在哪里付”上分道扬镳：编译期，还是运行时。第 5 节把有用的部分合成两个参考实现。

---

## 1. 对象池：用一个指针换掉一次搜索

“我不想在热路径上调 malloc”的修法简单得几乎有点尴尬：启动时把你将来需要的一切一次分配好，需要时从这块预分配的内存里切一块出去、用完再收回来。这就是对象池——某个类型 `T` 的固定数量的实例，放在程序已经拥有的内存里。

### 1.1 朴素版本得的是同一种病，只是小一号

```cpp
struct ObjectBlock {
  T object_;
  bool is_free_ = true;
};
std::vector<ObjectBlock> store_;
size_t next_free_index_ = 0;
```

`allocate()` 在 `store_[next_free_index_]` 上原地构造，标记为已占用，然后调 `updateNextFreeIndex()` 为下一次找*下一个*空闲槽——从当前位置往后扫，到尾部再绕回来。在接近先进先出的访问模式下，下一个槽通常就是空的，扫描几乎立刻停下。但没有任何东西保证这种模式。乱序持有对象、乱序释放，扫描就可能走遍整个池才找到一个空位——**最坏 O（n），而这个最坏情况，和这个池本来要替换掉的、取决于碎片化的代价一样不可预测**。 进内核的往返是消掉了，池子里又长回来一个更小的、同样形状的问题。

### 1.2 修法：不去找，而是一直维护着

```cpp
T* objects_;
std::size_t* free_list_;
std::size_t next_free_index_;                    // 空闲链表的头
static constexpr std::size_t kInvalidIndex = -1;  // 链表结束标记
```

`free_list_` 是一条空闲槽的链表——但它用**数组下标而不是指针**实现。`free_list_[i]` 记的不是“槽 `i` 空不空”，而是“如果 `i` 是链表头，它后面是哪个槽”。`next_free_index_` 就是那个链表头。`allocate()` 拿走 `next_free_index_` 当前指向的那个槽，再把链表头移到 `free_list_[那个槽]`——一次读，一次写，不扫描。`deallocate()` 用同样的方式把释放的槽推回链表头。两个操作**每一次都是完全相同的那几条指令**，因为空闲链表在每次调用时都被增量维护着——等你调用 `allocate()` 时，“下一个空闲槽是哪个”已经躺在一个变量里了，不需要去找。

这一点值得说准确，因为它常被叫错：这**不是侵入式链表**。侵入式链表把 `next` 指针存在*载荷类型本身*里面——对象自己兼作节点。这里的 `free_list_` 是一个和 `objects_` 并行的、完全独立的数组；`T` 根本不知道自己被链进了什么东西。真正侵入式的版本，会把“下一个空闲下标”用 `union` 放进一个还没构造的 `T` 本来要占的那块内存里，省掉第二个数组，代价是所有权关系没那么一目了然——这是一个真实的“内存 vs 简单”取舍，参考实现选择了不做。

还有一个值得保留的布局细节：`ObjectBlock` 把 `T` 和 `is_free_` 打包进一个结构体，而不是两个并行数组。一次 `allocate()` 会同时碰这两个字段，把它们放在一起，一次缓存行读取就够了，而不是两次落在不相干的行上的独立读取。

---

## 2. 锁住还不够：mmap 陷阱和 TLB shootdown 税

对象池解决的是“热路径上别向分配器要内存”。它管不了第二种、很容易漏掉的失败方式：你已经拿到的内存，仍然可能被收走，或者在你第一次碰它时给你一个意外。

### 2.1 光靠 mlockall 有个漏洞

`mlockall(MCL_CURRENT | MCL_FUTURE)` 告诉内核：这个进程现在持有的每一页、以后会持有的每一页，都常驻内存——永不换出。听上去很完整。其实不然，因为一个细节：**`munmap` 不是给一页解锁，而是把锁所依附的整个映射拆掉**。 glibc 把大于 `M_MMAP_THRESHOLD`（默认 128 KB）的分配走 `mmap` 而不是堆，`free()` 这块内存时立刻对它调 `munmap`——这块分配一释放，`mlockall` 给过的保证就悄无声息地没了。

![前后对比：台座上一个用链子锁住的保险箱；之后同一个台座上箱子整个不见了——只剩那条仍然锁着的链子和挂锁悬在它原来的位置](/images/hot-path-allocators/torn-down-not-unlocked.jpg)

堵上这个漏洞要三次 `mallopt` 调用，每一次堵住一条不同的回内核的路：

- **`M_MMAP_MAX = 0`**——彻底禁止 mmap 这条路。不管多大的分配都走堆；`free()` 只剩记账，永远不调 `munmap`。
- **`M_TRIM_THRESHOLD = -1`**——同样的想法用在堆本身。默认情况下，堆顶积累了足够多的连续空闲空间后，glibc 会用 `sbrk` 把堆往回缩、还给操作系统；这个设置把它关掉，堆顶一大块释放出来的空间永远不还回去。
- **`M_ARENA_MAX = 1`**——另一个维度：多个工作 arena 本身就由额外的 `mmap` 区域支撑。强制只用一个 arena（反正分配只在启动时发生，多 arena 的并发好处在这里没有意义），一开始就去掉了这些额外的 mmap 来源。

### 2.2 isolcpus 替你挡不住的税：TLB shootdown

任何页表变更——`munmap`、`mprotect`，或者内核自己的透明大页后台合并——都会引发一次 **TLB shootdown**：做变更的那个核不知道别的哪些核缓存了这条已经过期的地址翻译，于是给正在运行这个进程地址空间的每一个核广播一个核间中断（IPI）。每个核都得停下来、陷入内核、作废受影响的 TLB 条目、再继续——微秒级，而且随共享这个地址空间的核数增长。

尖锐又容易弄错的一点是：**`isolcpus` 挡不住它**。 `isolcpus` 工作在调度器这一层——它控制调度器会不会把*任务*放到某个核上。TLB shootdown 是一个硬件中断，按内核为这个地址空间记录的 `mm_cpumask` 里有哪些核来投递——一个调度器根本说不上话的、完全不同的机制。一个完美隔离、绑好核的热线程，照样可能被同一进程里的一个*冷*线程调用 `munmap` 或 `mprotect` 打断，因为两个线程共享同一个 `mm_struct`，而 shootdown 瞄准的是地址空间，不是调度类别。这也是调优过的系统要关掉 THP 和自动 NUMA 均衡的更深一层原因，不只是“后台合并带来不可预测的延迟”——两者都会频繁改写页表，而每一次改写都是一次 shootdown，会打到调度器被告知永远别碰的那些核上。

---

## 3. STL 背后的 arena：一个只往前走的指针

对象池只发一种类型 `T`。真实的热路径代码想用 `std::vector`、`std::string` 这些普通 STL 容器——又不想让这些容器碰全局堆。这就意味着要写一个满足 C++ 分配器接口、背后是程序已经拥有的内存的东西。

### 3.1 一个只往前走的指针

```cpp
struct MemoryBlock {
  size_t used, capacity;
  bool is_active;
  // ...
};
```

arena 从一块预留好的内存里分配，只跟踪一个数：这块内存已经用掉了多少字节。`allocate(size)` 把当前写入位置向上取整到要求的对齐，检查 `used + size` 还装不装得下 `capacity`，装得下就直接推进 `used`、返回旧位置——不用搜索，因为根本没什么可搜的：“下一个空闲位置”永远就是指针现在所在的地方。一块用满了，arena 用同样的方式启用下一块预留的内存。这比第 1 节的空闲链表还要便宜——连链表指针交换都没有，就是一次加法——代价是没办法从中间释放单独一次分配。没有任何东西记录每次分配从哪开始、到哪结束，所以就算你想释放一个也无从查起。唯一的回收操作是全局的：把每一块的 `used` 都倒回零，从头再来。对于一批生命周期完全相同的对象——处理一个 tick 时分配的所有东西，tick 处理完一起扔掉——这是正确的取舍；对于生命周期参差的对象则不然，它们还是属于第 1 节的池。

### 3.2 预先缺页：启动时把每一页都写一遍

arena 背后的内存在构造时一次拿到，用 `posix_memalign` 和 `mlock()`，这次只锁 arena 自己的这块区域，比第 2 节全进程的 `mlockall` 更精准。一段新拿到的虚拟地址范围，背后还没有物理内存：Linux 懒惰地映射页，真正的物理页要到第一次访问时才分配，靠的是一次陷入内核的缺页。`mlock` 成功返回时，会顺带把范围内的页都缺好、锁住。可它经常失败：没有 `CAP_IPC_LOCK` 时，能锁的总量受 `RLIMIT_MEMLOCK` 限制（常见默认值是 8 MB，老内核只有 64 KB），超了就返回错误，一页也不缺。

所以构造函数再加一行 `memset(raw_memory, 0, total_size)`，在启动时把每一页写一遍。`mlock` 成功时，它只是多走一遍；`mlock` 失败时，页虽然没锁住，首次缺页也已经在启动时付掉了。**等热路径运行时，arena 里的每一页都已经映射好，没有任何东西要第一次发生**。

把这个 arena 适配到 STL 接口（`allocate`/`deallocate`/`construct`/`destroy`/`rebind`）的分配器，大部分是样板代码，知道它存在就够了，不必细究——只有一个例外：`deallocate()` 被故意写成空操作，原因和 `reset()` 是唯一回收内存的办法一样。单个对象的构造和析构仍然通过 `construct`/`destroy` 正常发生；被废掉的只有契约里“内存”的那一半。

---

## 4. std：：pmr：同一个答案，在运行时付钱

### 4.1 把分配器从类型里挪出去

第 3 节的自定义分配器有一个类型系统不会提醒你的锋利边缘：`std::vector<int>` 和 `std::vector<int, LowLatencyAllocator<int>>` 是两个毫不相干的类型。分配器是模板参数——是容器类型的一部分，不是一个运行时设置——所以一个写成接收 `std::vector<int>&` 的函数，会直接拒绝 arena 版本，每个需要两者都接收的函数也得在分配器上模板化。

`std::pmr`（C++17）用相反的方式解决同一个“让 STL 用我的分配策略”的问题：把策略的选择从类型里挪出去，放进一个运行时指针。`std::pmr::memory_resource` 是一个抽象基类——`do_allocate`、`do_deallocate`、`do_is_equal`——任何具体的分配策略都通过继承它来表达。所有 `std::pmr` 容器都用同一个统一的 `std::pmr::polymorphic_allocator<T>`，它里面只有一个 `memory_resource*`；因为这个指针具体指向什么不是类型的一部分，`std::pmr::vector<int>` 不管背后是哪个 resource，永远是同一个类型——随便传、随便赋值、随便返回，不用任何模板体操。代价在每一次分配时付：通过那个指针的一次虚调用，运行时分派，而第 3 节的版本里具体的分配器类型在编译期就知道，可以被完全内联掉。这正是 C++ 程序员在虚函数和模板之间早就在权衡的静态多态 vs 动态多态，只是这次用在了内存本身上。

### 4.2 标准库自带的 resource，对应第 1 节和第 3 节

标准库自带了几个 resource，直接对应前面讲过的东西：

- **`monotonic_buffer_resource`** 就是标准化的第 3 节 arena：只往前分配，一起释放，不能单独回收。它甚至接受调用者提供的初始缓冲区（比如栈上的一个 `std::array`），外加一个溢出时用的后备 resource——标准库版本的 `allow_fallback_` 参数。
- **`unsynchronized_pool_resource`** 更接近第 1 节的池，推广到了多种对象大小而不是一个固定类型，按大小类别管理成一个个 “slab”。
- **`synchronized_pool_resource`** 是上面那个的线程安全版——名字已经说明了它的代价：一把锁，正是这整篇文章想要避免的那一类竞争。

### 4.3 生命周期陷阱

`std::pmr::vector` 看上去和普通的值类型一模一样——按值返回一个，似乎和返回任何别的 `std::vector` 一样安全。并不是，原因很具体：`polymorphic_allocator` 只是*指向*它的 `memory_resource`，从不拥有它。如果那个 resource 是一个局部变量，返回 vector 对延长 resource 的生命周期毫无帮助：

```cpp
auto create_vec() -> std::pmr::vector<int> {
  auto resource = PrintingResource{};           // 局部变量,出作用域就销毁
  auto vec = std::pmr::vector<int>{&resource};  // vec 只存了 &resource
  return vec;                                   // resource 在这里被销毁
}
auto vec = create_vec();
vec.emplace_back(1);  // 未定义行为
```

`vec` 本身干干净净地移出来了——没有深拷贝，返回这一步看不出任何问题。危险在调用处是看不见的，恰恰因为 `std::pmr::vector<int>` 摆出和 `std::vector<int>` 一样的值语义，却并不拥有它的正确性所依赖的那个东西。这逼出来的规则毫不起眼，但没有例外：`memory_resource` 的生命周期必须长过建在它上面的每一个容器——这通常意味着它得住在一个严格更外层的作用域里，绝不能放在那个只是构造并返回容器的函数里面。

---

## 5. 合在一起：两个参考实现，再加一个多线程版本

前四节的做法可以收拢成两份能直接拿去用的代码：生命周期各自独立、一个一个释放的对象用对象池（5.1），一批一起扔掉的对象用 arena（5.2）。几个线程都要从池里分配时，空闲链表要换成无锁栈，这时会遇到 ABA（5.3）。

> **对象池、arena 还是 std：：pmr：看对象怎么释放**
>
> 1. **对象一个一个分配、一个一个释放，类型固定**：用对象池。分配和释放都只动空闲链表的头，O（1）。
> 2. **一批对象一起用完、一起扔掉**（处理一个 tick、一笔订单时碰到的所有临时对象）：用 arena。分配就是一次加法，不能单独释放，用完整体 `reset()`。
> 3. **同一种容器类型要换着用不同的内存来源**：用 `std::pmr`。它解决的是类型兼容，不是性能，每次分配多一次虚调用，热路径上不如前两种。

### 5.1 一个参考对象池 {#ref-pool}

这个池把第 1、2 节的三件事放在一起：

- **启动时一次拿到全部内存，锁住并缺完页**：`aligned_alloc` 一次分配 `capacity` 个槽，`mlock` 锁住，`memset` 把每一页写一遍（第 2 节、3.2）。
- **空闲槽串成一条链表，分配和释放都只动链表头**：`free_head_` 是第一个空闲槽的下标，每个空闲槽的 `next_free` 记着下一个。分配时取下链表头，释放时把槽放回链表头（第 1 节）。
- **“下一个空闲槽”和对象放在同一个槽里**：第 1 节用一个单独的 `free_list_` 数组；这里 `next_free` 就在 `Slot` 里，分配时读 `next_free` 和接着构造 `T` 碰的是同一个槽，通常是同一条缓存行。

```cpp
template <typename T>
class ObjectPool {
  struct Slot {
    alignas(T) unsigned char storage[sizeof(T)];  // 构造之后 T 就在这里
    std::size_t next_free;                        // 空闲时：下一个空闲槽的下标
  };
  static constexpr std::size_t kInvalid = static_cast<std::size_t>(-1);

  Slot* slots_;
  std::size_t capacity_;
  std::size_t free_head_;                         // 第一个空闲槽的下标

 public:
  explicit ObjectPool(std::size_t capacity)
      : capacity_(capacity), free_head_(capacity ? 0 : kInvalid) {
    std::size_t bytes = sizeof(Slot) * capacity_;
    slots_ = static_cast<Slot*>(std::aligned_alloc(alignof(Slot), bytes));
    if (!slots_) throw std::bad_alloc{};
    if (mlock(slots_, bytes) != 0) {
      // 没有 CAP_IPC_LOCK 或超过 RLIMIT_MEMLOCK：记一条日志，下面的 memset 照样提前缺完页
    }
    std::memset(slots_, 0, bytes);
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
    if (free_head_ == kInvalid) return nullptr;   // 池用完了：热路径上不抛异常
    Slot& slot = slots_[free_head_];
    free_head_ = slot.next_free;                  // 取下链表头
    return ::new (slot.storage) T(std::forward<Args>(args)...);
  }

  void deallocate(T* obj) {
    obj->~T();
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));
    slot->next_free = free_head_;                 // 放回链表头
    free_head_ = static_cast<std::size_t>(slot - slots_);
  }
};
```

**池用完时 `allocate` 返回 `nullptr`，不抛异常**：热路径上由调用方决定是走慢路径还是丢掉这条消息。`std::aligned_alloc` 要求字节数是对齐值的倍数，`sizeof(Slot)` 本来就是 `alignof(Slot)` 的倍数，所以这里自然满足。

### 5.2 一个参考 arena {#ref-arena}

arena 用于和池相反的情况：一批分配，大小可能不同、类型可能不同，最后一起释放。启动时的处理和池一样，分配逻辑更简单：没有空闲链表要维护，只有一个往前走的偏移 `used_`。

```cpp
class Arena {
  unsigned char* base_;
  std::size_t capacity_;
  std::size_t used_ = 0;

 public:
  explicit Arena(std::size_t capacity) : capacity_(capacity) {
    base_ = static_cast<unsigned char*>(std::aligned_alloc(64, capacity_));  // capacity 要是 64 的倍数
    if (!base_) throw std::bad_alloc{};
    if (mlock(base_, capacity_) != 0) {
      // 同上：记一条日志
    }
    std::memset(base_, 0, capacity_);
  }

  ~Arena() {
    munlock(base_, capacity_);
    std::free(base_);
  }

  Arena(const Arena&) = delete;
  Arena& operator=(const Arena&) = delete;

  // alignment 必须是 2 的幂，且不超过 64
  void* allocate(std::size_t size, std::size_t alignment = alignof(std::max_align_t)) {
    std::size_t start = (used_ + alignment - 1) & ~(alignment - 1);  // 向上取整到对齐
    if (start + size > capacity_) return nullptr;                    // 装不下了
    used_ = start + size;                                            // 往前推
    return base_ + start;
  }

  void reset() noexcept { used_ = 0; }
};
```

`allocate` 就三步：把 `used_` 向上取整到要求的对齐，检查装不装得下，把 `used_` 推过这一块。`base_` 按 64 字节对齐，所以偏移对齐了，地址也就对齐了，这也是 `alignment` 不能超过 64 的原因。

**arena 不能单独释放一个对象，回收只有 `reset()` 一种**。 它不记录每次分配，所以没法单独还一块；`reset()` 也不调析构函数，放进去的对象要么是平凡析构的，要么由调用方在 `reset()` 之前自己析构。和第 3 节的多块设计相比，这里只有一块固定大小的缓冲区，更容易写对，代价是容量有硬上限，用完返回 `nullptr`。

### 5.3 多线程分配：无锁空闲栈和 ABA {#aba}

5.1 的池只能在一个线程里用：两个线程同时读 `free_head_`，会拿到同一个槽。要让几个线程同时分配，就把链表头换成原子变量，用 CAS 取下它：读出 `head` 和它的 `next`，再 CAS 把 `head` 从读到的值换成 `next`；这期间别的线程改过 `head`，CAS 失败，重读重试。空闲链表只在头上进出，所以它就是一个无锁栈。

**这种栈有一个经典的坑，叫 ABA：CAS 只比较值，看不出这个值中间变过、又变了回来**。 名字说的就是 `head` 从 A 变成 B，又变回 A。下面用 X、Y、Z 表示三个空闲槽，栈里一开始是 X → Y → Z：

| 时刻 | 线程 A（分配） | 别的线程 | 空闲栈 |
|---|---|---|---|
| 1 | 读到 `head = X`、`X.next = Y`，还没 CAS 就被换下 | | X → Y → Z |
| 2 | | 线程 B 分配两次，拿走 X 和 Y | Z |
| 3 | | 有线程把 X 还回来 | X → Z |
| 4 | CAS：`head` 还是 X，成功，`head` 改成 Y | | Y → Z，可 Y 正被 B 用着 |

时刻 4 以后，下一次分配会把 Y 再发出去，同一个槽同时给了两个使用者；刚还回来的 X 反而从栈里丢了，再也分不出去。

**修法是给 `head` 带一个版本号，每改一次加 1，CAS 同时比较下标和版本号**。 时刻 1 线程 A 读到的是（X，版本 5）；时刻 2、3 一共改了三次，`head` 变成（X，版本 8）。A 拿（X，5）去比，不相等，CAS 失败，重读以后重试。

槽用 32 位下标表示，下标和 32 位版本号正好打包进一个 `uint64_t`，普通的 64 位 CAS 就能一起比较。链表要是用指针，就得用 16 字节的 CAS（x86-64 的 `cmpxchg16b`），或者把版本号塞进 64 位指针用不到的高 16 位。版本号会回绕，但那要求线程 A 被换下的这一会儿里正好错过 $2^{32}$ 次修改，实际不会发生。

```cpp
template <typename T>
class ConcurrentPool {
  struct Slot {
    alignas(T) unsigned char storage[sizeof(T)];
    std::atomic<std::uint32_t> next;              // 空闲时：下一个空闲槽的下标
  };
  static constexpr std::uint32_t kNil = UINT32_MAX;
  static std::uint64_t pack(std::uint32_t ver, std::uint32_t idx) {
    return (std::uint64_t(ver) << 32) | idx;      // 高 32 位版本号，低 32 位下标
  }

  Slot* slots_;                                   // 分配、mlock、memset、串链表同 5.1
  std::atomic<std::uint64_t> head_;               // 初值 pack(0, 0)

 public:
  template <typename... Args>
  T* allocate(Args&&... args) {
    std::uint64_t old = head_.load(std::memory_order_acquire);
    for (;;) {
      std::uint32_t idx = static_cast<std::uint32_t>(old);
      if (idx == kNil) return nullptr;
      std::uint32_t next = slots_[idx].next.load(std::memory_order_relaxed);
      std::uint64_t desired = pack(static_cast<std::uint32_t>(old >> 32) + 1, next);
      if (head_.compare_exchange_weak(old, desired,
                                      std::memory_order_acquire,    // 成功
                                      std::memory_order_acquire))   // 失败：old 被换成最新值
        return ::new (slots_[idx].storage) T(std::forward<Args>(args)...);
    }
  }

  void deallocate(T* obj) {
    obj->~T();
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));
    std::uint32_t idx = static_cast<std::uint32_t>(slot - slots_);
    std::uint64_t old = head_.load(std::memory_order_relaxed);
    for (;;) {
      slot->next.store(static_cast<std::uint32_t>(old), std::memory_order_relaxed);
      std::uint64_t desired = pack(static_cast<std::uint32_t>(old >> 32) + 1, idx);
      if (head_.compare_exchange_weak(old, desired,
                                      std::memory_order_release,
                                      std::memory_order_relaxed))
        return;
    }
  }
};
```

用 GCC 16.2 跑过一个压力测试：8 个线程共用一个 64 槽的池，各自分配、释放 20 万次，没有一个槽同时发给两个线程，结束后 64 个槽全部收回。

内存序这样选：

- **分配时的读和 CAS 都用 acquire**：拿到槽的线程，要看得到上一个使用者释放前写进这个槽的内容，也要看得到释放时写下的 `next`。CAS 失败时会把最新的 `head` 读回 `old`，下一轮接着要读它的 `next`，所以失败的那一路也要 acquire。
- **释放的 CAS 用 release**：这个槽里的写入和刚写下的 `next`，随着这次 CAS 一起发布给下一个拿到它的线程。

`next` 单独放、做成 `std::atomic`，不和 `storage` 共用字节，是因为时刻 1 的线程 A 读 `X.next` 时，X 可能已经被别的线程拿走、正在往 `storage` 里构造对象。两者分开，这次读就不是数据竞争；读到的旧值会随着失败的 CAS 被丢掉。

**池比一般的无锁栈少一个难题：槽永远不还给系统**。 一般的无锁栈弹出节点以后会 `delete` 它，别的线程可能还拿着它的地址要读 `next`，读的就是已经释放的内存，这要靠 hazard pointer、epoch 这类回收方案解决。池里的槽一直都在，最多读到过时的 `next`。
