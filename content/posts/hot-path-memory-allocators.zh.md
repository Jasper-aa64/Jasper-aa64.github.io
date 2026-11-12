---
title: "交易系统笔记 #3：内存池与分配器"
date: 2026-09-17
lastmod: 2026-11-11
slug: "hot-path-memory-allocators"
description: "为什么 malloc/free 真正的问题是方差而不是速度——以及四种越来越通用的办法，保证热路径上没有任何事是第一次发生：O(1) 的空闲链表对象池、自定义 STL 分配器背后的 bump 指针 arena、std：：pmr 这个运行时版本的替代方案，以及垫在三者底下的那一层：预先缺页、锁页，不让 glibc 把页还给内核。还有对象池和 arena 的参考实现，以及多线程对象池的无锁空闲栈和 ABA。"
summary: "这篇里的每一种技术，都是在不同的层面上做同一件事：把一个不确定的、牵涉内核的操作从热路径上挪走，强制它在开头一次性发生完，不让它伏击任何一个请求。对象池用永远 O(1) 的空闲链表，换掉 malloc 那种耗时可变的搜索。mlockall 加上仔细的 mallopt 调优，阻止内核悄悄把页收回——预先缺页则补上 mlock 单独留下的那个口子。手写的 arena 分配器让 STL 本身配合一个由 bump 指针内存支撑的自定义分配器。std：：pmr 用标准库的方式解决同一个「让 STL 配合」的问题——拿编译期的速度换运行时的灵活。"
chapter: 1
categories: [Systems]
tags: [cpp, memory-pool, allocator, mlock, tlb-shootdown, pmr, hft, low-latency, stl]
toc: true
homepage: false
---

`malloc` 和 `free` 并不慢。在一个紧循环里调一千次，平均耗时看起来完全没问题。HFT 代码和它们的矛盾不在平均值，而在**尾部**，而尾部取决于你控制不了的状态。glibc 为了避免锁竞争，给每个线程分 arena，可线程数一旦超过 arena 数，两个线程就开始抢同一个 arena 的锁。当前 arena 满足不了的请求，可能意味着一次新的 `brk` 或 `mmap` 系统调用进内核。释放的内存被分进按大小划分的 bin 里，要遍历、可能还要合并，这要花多久，取决于这个堆之前经历过的全部碎片化历史。这些代价没有一个是固定的，全都取决于“这个进程到目前为止干过什么”——而这恰恰是热路径问不起的问题。

> **为什么热路径上不用 malloc：快的时候很快，慢的时候慢上百倍**
> malloc 从便宜的地方往贵的地方找，走到哪一层，取决于这个进程之前分配、释放过什么（[new 一次走到哪](/zh/ref/new-malloc-page-fault/)）：
> 1. **tcache 命中**：本线程自己的小链表，只有本线程碰，不用加锁，约 10–20 ns。
> 2. **arena 的空闲链表**：要拿 arena 的锁，可能还要切分、合并相邻的空闲块，几十到一两百 ns；线程多了还要抢锁。
> 3. **brk / mmap 进内核**：手里的空闲块不够，一次系统调用几百 ns 到 1 µs。
> 4. **第一次写新拿到的页**：内核在第 3 步只登记了一段地址，每 4 KiB 第一次写时缺页一次，每次约 0.5–2 µs；一大块新内存第一遍写下来，是几十 µs 到 ms。
>
> - **平均看不慢**：大多数调用停在第 1 层。
> - **P99 的尖峰来自第 3、4 层**：哪一次会掉下去，事先没法知道。
> - **free 也会把下一次推回第 3 层**：glibc 释放大块时直接 `munmap` 还给内核，下一次再要，又得进内核。
> - **内存池和 arena 把第 2–4 层挪到启动时**：启动时一次要够、整块写一遍把页缺完、锁住。
> - **热路径上的分配每次都一样快**：只剩挪一下链表头或指针。

> **该换成对象池或 arena 的信号**
> - **中位数正常、P99 有尖峰**：尖峰的时刻 perf 里有缺页（`page-faults`）或 `brk`、`mmap` 系统调用，说明热路径上在向内核要内存。
> - **热路径上反复 new、delete 同样大小的对象**：比如订单、消息，用对象池（第 1 节），取放都是 O(1)。
> - **一批对象同生同死**：比如一个交易日的行情、一次请求里的临时数据，用 arena（第 2 节），只往前分配，最后整块释放。
> - **几个线程同时分配，perf 里 malloc 的锁占了时间**：每个线程一个池，或者用第 5 节的无锁空闲栈；先看 5.1 的框，判断是不是真要共用一个池。

这篇里的一切，都是同一个修法的变奏：找出那个代价取决于首次访问、竞争或碎片化的操作，**把它挪到程序生命里你不在乎它花多久的那个时刻**——通常是启动时。第 1 到 3 节挪走分配本身：对象池管同一种类型一个一个地分配、释放，arena 管一批对象一起用完一起扔，`std::pmr` 用运行时的灵活换掉编译期的类型。第 4 节往下一层，讲这三种分配器底下那块内存：页要在启动时就缺好、锁住，进程里谁都不许把页还回内核。第 1、2 节末尾各给一份能直接用的参考实现，第 5 节讲几个线程同时从池里分配时的无锁版本和 ABA。

---

## 1. 对象池：预先分好一批同类对象的槽，用时取、用完还 {#pool}

**对象池**：启动时给一种类型 `T` 一次分好固定数量的槽，热路径上分配就是取一个空槽，释放就是还回去，不再调 `malloc`。用在订单、行情消息这类数量有上限、反复创建和销毁的对象上。

### 1.1 扫描找空槽：最坏要扫完整个池 {#scan-pool}

关键在“找下一个空槽”这一步：**它必须每次都是同样的几条指令，和这个池之前被怎么用过无关。** 最直接的写法是每个槽带一个“空不空”的标记，分配完以后往后扫，找到下一个空槽备用。

```cpp
struct ObjectBlock {
  T    object_;
  bool is_free_ = true;
};
std::vector<ObjectBlock> store_;
std::size_t next_free_index_ = 0;   // 下一次分配用的槽

T* allocate() {
  ObjectBlock& b = store_[next_free_index_];
  b.is_free_ = false;               // 在 b.object_ 上原地构造，略
  // 为下一次找空槽：往后扫，到尾部绕回开头（池满的处理略）
  std::size_t i = next_free_index_;
  do {
    i = (i + 1) % store_.size();
  } while (!store_[i].is_free_ && i != next_free_index_);
  next_free_index_ = i;
  return &b.object_;
}
```

扫多远，取决于空槽在池里怎么分布：

- **对象按分配的顺序释放**（先进先出）：当前位置后面紧挨着就是空槽，扫一格就停。
- **对象持有的时间长短不一**：空槽散落在池里，一次扫描可能走过大半个池，最坏 O(n)。

**扫多久取决于这个池之前被怎么用过**，这和 `malloc` 的毛病是同一种：耗时取决于历史，尾部延迟没法预测。进内核的系统调用是省掉了，不确定性还在。

### 1.2 空闲链表：下一个空槽一直记在链表头 {#free-list}

修法是不去找：把所有空槽串成一条链表，分配从链表头取，释放放回链表头。“下一个空槽是哪个”一直记在 `head_` 里，要用的时候直接拿。

```cpp
T*           objects_;     // capacity 个槽，指向一块还没构造对象的内存
std::size_t* free_list_;   // free_list_[i]：槽 i 空闲时，链表里排在它后面的槽
std::size_t  head_;        // 第一个空闲槽，kInvalid 表示池用完了
static constexpr std::size_t kInvalid = static_cast<std::size_t>(-1);

T* allocate() {
  if (head_ == kInvalid) return nullptr;
  std::size_t i = head_;
  head_ = free_list_[i];                // 链表头移到下一个空槽
  return ::new (&objects_[i]) T();
}

void deallocate(T* p) {
  std::size_t i = static_cast<std::size_t>(p - objects_);
  p->~T();
  free_list_[i] = head_;                // 这个槽接到链表最前面
  head_ = i;
}
```

链表用数组下标串起来，不用指针：`free_list_[i]` 存的是下一个空槽的下标。拿 4 个槽走一遍：

| 操作 | 拿到或还回 | `head_` | 空闲链表 |
|---|---|---|---|
| 启动 | | 0 | 0 → 1 → 2 → 3 |
| `allocate()` | 槽 0 | 1 | 1 → 2 → 3 |
| `allocate()` | 槽 1 | 2 | 2 → 3 |
| `deallocate(槽 0)` | 槽 0 | 0 | 0 → 2 → 3 |
| `allocate()` | 槽 0 | 2 | 2 → 3 |

**分配和释放都是一次读、一次写，和池里有多少空槽、空槽在哪都无关。** 链表是后进先出的，还有一个附带的好处：刚还回来的槽最先被再分出去，它多半还在缓存里。

### 1.3 下一个空槽的下标存在哪：单独数组、同一个槽、还是对象自己的内存 {#free-link-layout}

1.2 的 `free_list_` 是和 `objects_` 并列的另一个数组，`T` 不知道自己被串在链表里，这叫**非侵入式**。下标还可以放在别的地方，三种放法各有代价：

| 下标存在哪 | 一次分配碰几条缓存行 | 额外内存 | 代价 |
|---|---|---|---|
| 单独的数组（1.2） | 两条：`free_list_[i]` 和 `objects_[i]` 不在一起 | 每槽 8 字节 | 每次分配多一次缓存未命中的机会 |
| 和对象放在同一个槽里（1.4） | `T` 不大时一条 | 每槽 8 字节 | 无 |
| 对象自己的内存，即**侵入式**（`union`） | 一条 | 0 | 要求 `sizeof(T) ≥ 8`；对象释放后又被误写（use-after-free），会直接改坏链表，很难查 |

侵入式能成立，是因为**空闲的槽里没有对象**：这块内存本来就闲着，正好拿来存“下一个空槽”的下标；分配时先读出下标，再在同一个地址上构造 `T`，把它覆盖掉。

> **下标放哪：默认放进同一个槽**
>
> - **一般情况**：和对象放在同一个槽里（1.4 的写法），一次分配只碰一条缓存行，代码也清楚。
> - **槽很多、内存紧，`T` 又不小于 8 字节**：用侵入式，每个槽省 8 字节。
> - **对象必须紧密排成一个 `T` 数组**（比如要按数组顺序遍历全部对象）：只能用单独的数组。


### 1.4 参考实现：一个能直接用的对象池 {#ref-pool}

下面这个池把空闲链表和第 4 节的启动处理（4.1 预先缺页、4.2 锁页）放在一起：

- **启动时一次拿到全部内存，锁住并缺完页**：`aligned_alloc` 一次分配 `capacity` 个槽，`mlock` 锁住，`memset` 把每一页写一遍（4.1、4.2）。
- **空闲槽串成一条链表，分配和释放都只动链表头**：`free_head_` 是第一个空闲槽的下标，每个空闲槽的 `next_free` 记着下一个。分配时取下链表头，释放时把槽放回链表头（1.2）。
- **“下一个空闲槽”和对象放在同一个槽里**：就是 1.3 表里的第二种。`next_free` 就在 `Slot` 里，分配时读 `next_free` 和接着构造 `T` 碰的是同一个槽，通常是同一条缓存行。

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

---

## 2. arena：一批对象一起用完、一起扔，分配只剩一次加法 {#arena}

对象池只发一种类型 `T`，一个一个分配、一个一个还。热路径上还有另一种用法：处理一个 tick 时，临时要一批大小不一、类型不一的对象，比如几个 `std::vector`、`std::string` 的缓冲区，tick 处理完一起扔掉。给每种对象都配一个池不现实，arena 就是为这种情况准备的。

### 2.1 一批对象同生同死：一个只往前走的指针，回收只能整块倒回 {#bump}

1. **arena 只记一个数：这块内存已经用掉了多少字节（`used`）**
   - **分配三步**：把 `used` 向上取整到要求的对齐；检查 `used + size` 还装不装得下 `capacity`；装得下就把 `used` 推过这一块，返回原来的位置。
   - **不用搜索**：下一个空闲位置永远就是指针现在的位置，没什么可找的。
   - **比第 1 节的空闲链表还便宜**：连链表头都不用改，就是一次加法。
   - **一块用满了**：用同样的方式接着用下一块预留的内存。
2. **代价是不能单独释放某一次分配**
   - **原因**：arena 不记录每次分配从哪开始、到哪结束，想还某一块也无从查起。
   - **回收只有一种**：`reset()`，把 `used` 倒回 0，整块从头再用。
3. **所以按对象的生命周期选**
   - **一批对象同生同死**（一个 tick 里分配的所有临时对象）：用 arena。
   - **生命周期参差不齐**：还是用第 1 节的池。

### 2.2 STL 容器默认找全局堆：把 arena 包成分配器，deallocate 故意什么都不做 {#stl-allocator}

1. **痛点：热路径代码想用普通的 `std::vector`、`std::string`**，可它们默认从全局堆拿内存，也就是 `malloc`。
2. **解决：把 arena 包成一个满足 C++ 分配器接口的类**，作为容器的模板参数传进去，容器的内存就都从 arena 里拿。
   - **接口大多是样板**：`allocate`、`deallocate`、`construct`、`destroy`、`rebind`，知道它存在就够了。
   - **唯一要注意的是 `deallocate()` 写成空操作**：arena 本来就不能单独还一块，回收只靠 `reset()`。
   - **对象的析构照常发生**：`destroy` 还是会调析构函数，被废掉的只是“把内存还回去”这一半。

### 2.3 参考实现：一个能直接用的 arena {#ref-arena}

启动时的处理和 1.4 的池一样（第 4 节）；分配逻辑更简单，没有空闲链表要维护，只有一个往前走的偏移 `used_`。

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

- **`allocate` 就是 2.1 的三步**：`base_` 按 64 字节对齐，所以偏移对齐了，地址也就对齐了，这也是 `alignment` 不能超过 64 的原因。
- **`reset()` 不调析构函数**：放进去的对象要么是平凡析构的，要么由调用方在 `reset()` 之前自己析构。
- **只有一块固定大小的缓冲区**：比 2.1 说的多块设计更容易写对，代价是容量有硬上限，用完返回 `nullptr`。

---

## 3. std::pmr：分配器写进了类型，函数就不认这个容器；pmr 把它挪到运行时 {#pmr}

### 3.1 分配器是类型的一部分：换了分配器，函数就不认；pmr 改成一个运行时指针 {#allocator-in-type}

1. **痛点：第 2 节的分配器是容器的模板参数**
   - **`std::vector<int>` 和 `std::vector<int, LowLatencyAllocator<int>>` 是两个毫不相干的类型**。
   - **后果**：一个写成接收 `std::vector<int>&` 的函数，不接受 arena 版本；想两种都收，每个函数都得在分配器上写成模板。
2. **解决：`std::pmr`（C++17）把“用哪种分配策略”从类型里挪到一个运行时指针**
   - **`std::pmr::memory_resource` 是抽象基类**：具体的分配策略继承它，实现 `do_allocate`、`do_deallocate`、`do_is_equal`。
   - **所有 pmr 容器都用同一个 `polymorphic_allocator<T>`**：它里面只有一个 `memory_resource*`。
   - **所以 `std::pmr::vector<int>` 背后不管是哪个 resource，都是同一个类型**：随便传、随便赋值、随便返回。
3. **代价在每一次分配时付**
   - **每次分配都要通过那个指针做一次虚调用**；第 2 节的分配器类型在编译期就知道，可以整个内联掉。
   - **这就是静态多态和动态多态的取舍**（[#8](/zh/posts/crtp-static-polymorphism/)），只是这次用在了内存上。

### 3.2 标准库自带的 resource，对应第 1 节和第 2 节 {#std-resources}

- **`monotonic_buffer_resource` 就是标准化的第 2 节 arena**：只往前分配，一起释放，不能单独回收。构造时可以交给它一块调用者准备好的缓冲区，比如栈上的一个 `std::array`。
  - **缓冲区用完时它会去找上游 resource，默认的上游就是 `new`**：等于在热路径上悄悄 `malloc`。
  - **上游设成 `std::pmr::null_memory_resource()`**：用完就抛 `std::bad_alloc`，容量不够立刻暴露出来。
- **`unsynchronized_pool_resource` 更接近第 1 节的池**：推广到多种对象大小，按大小类别各管一组槽。
- **`synchronized_pool_resource` 是它的线程安全版**：代价是一把锁，正是这篇想避开的那一类竞争。

### 3.3 resource 只被指着、不被拥有：它先销毁，容器就悬空 {#lifetime}

1. **痛点：`std::pmr::vector` 看上去和普通值类型一样，按值返回好像很安全**
   - **但 `polymorphic_allocator` 只指向它的 resource，不拥有它**：resource 是局部变量时，返回 vector 并不能让 resource 活得更久。

   ```cpp
   auto create_vec() -> std::pmr::vector<int> {
     auto resource = PrintingResource{};           // 局部变量，出作用域就销毁
     auto vec = std::pmr::vector<int>{&resource};  // vec 只存了 &resource
     return vec;                                   // resource 在这里被销毁
   }
   auto vec = create_vec();
   vec.emplace_back(1);  // 未定义行为
   ```

   - **返回这一步看不出问题**：`vec` 本身正常移出来，没有深拷贝；可它指着的 resource 已经没了，之后再往里加元素就是未定义行为。
2. **规则：resource 的生命周期必须长过建在它上面的每一个容器**
   - **放在更外层的作用域里**：不能放在“构造并返回容器”的那个函数里。

### 3.4 对象池、arena 还是 std::pmr：看对象怎么释放 {#which}

> **按对象怎么释放来选**
>
> 1. **对象一个一个分配、一个一个释放，类型固定**：用对象池。分配和释放都只动空闲链表的头，O（1）。
> 2. **一批对象一起用完、一起扔掉**（处理一个 tick、一笔订单时碰到的所有临时对象）：用 arena。分配就是一次加法，不能单独释放，用完整体 `reset()`。
> 3. **同一种容器类型要换着用不同的内存来源**：用 `std::pmr`。它解决的是类型兼容，不是性能，每次分配多一次虚调用，热路径上不如前两种。

---

## 4. 页这一层：一大块内存拿到手，热路径用它时为什么还会进内核 {#keep-memory}

前三节的分配器都在启动时拿下一大块内存：池的槽位数组、arena 的那几块、pmr 的 resource 背后的缓冲区。热路径上的分配只在这块内存里挪指针，不再找 `malloc`。**可拿到一大块，还不等于热路径用它时不进内核**：这块内存的页什么时候真正到、会不会被收走，归内核管，和用的是哪种分配器无关。下面四个痛点一个接一个冒出来，每解决一个，下一个就露出来。

> **四个痛点，一关接一关**
> - **拿到的只是地址，第一次写每一页都要缺页**：启动时把整块写一遍（4.1）。
> - **缺好的页，内存紧张时会被换出**：用 `mlock`、`mlockall` 锁住（4.2）。
> - **锁住的页，glibc 会自己拆掉映射还给内核，锁跟着没了**：三个 `mallopt` 关掉 glibc 还内存的三条路（4.3）。
> - **拆映射、改页表，会用核间中断打断热核**：进程跑起来以后，地址空间只读不改（4.4）。
>
> 前两关管的是池、arena 自己那一块；后两关管的是整个进程，第三方库、冷线程通过 glibc 拿的内存也在里面。

### 4.1 拿到的只是地址：第一次写每一页都要缺页，启动时先把整块写一遍 {#prefault}

**痛点**：`aligned_alloc`、`posix_memalign`、`mmap` 返回时，内核只登记了一段虚拟地址，背后还没有物理内存。Linux 懒惰地映射页：每个 4 KiB 页第一次被访问时，才陷入内核缺页，分配一个物理页，每次约 0.5–2 µs。池第一次发出去的那个槽、arena 第一次推进到的那一页，都会在热路径上缺页。

**解决**：构造函数里加一行 `memset(raw_memory, 0, total_size)`，启动时把每一页写一遍，缺页全在启动时付掉；用 `mmap` 拿内存的，也可以加 `MAP_POPULATE`，让内核在映射时就把页缺好。**等热路径运行时，池和 arena 里的每一页都已经映射好，没有任何东西要第一次发生**。1.4 的池和 2.2 的 arena 都是这么做的。

### 4.2 缺好的页会被换出：mlock 锁住一块，mlockall 锁住整个进程 {#mlockall}

**痛点**：页缺好了，也不保证一直在。内存紧张时，内核会把一段时间没碰的页换出到磁盘；热路径再碰它，要从磁盘读回来，是 ms 级。

**解决**：锁页。

- **`mlock(addr, len)` 锁一块**：池或 arena 构造时对自己那块调一次，范围里的页常驻内存，不会被换出；成功返回时还会顺带把这些页缺好。
- **`mlockall(MCL_CURRENT | MCL_FUTURE)` 锁整个进程**：现在已经映射的页全部锁住；`MCL_FUTURE` 让以后新映射的页在映射时就一次缺完、锁住。
- **锁页经常失败，失败时一页也不锁、一页也不缺**：没有 `CAP_IPC_LOCK` 时，能锁的总量受 `RLIMIT_MEMLOCK` 限制（常见默认值是 8 MB，老内核只有 64 KB）。所以启动时要检查返回值；4.1 的 `memset` 照样做，页虽然没锁住，至少首次缺页已经付掉了。

### 4.3 锁住的页会被 glibc 还给内核：三个 mallopt 各关一条路 {#mallopt}

**痛点**：`mlockall` 挡不住 glibc 自己把页还给内核。锁跟着映射走，`munmap` 不是给页解锁，而是把整个映射拆掉，锁也跟着没了。glibc 正会这么做：大于 `M_MMAP_THRESHOLD`（默认 128 KB）的分配单独 `mmap` 一块，`free` 时马上 `munmap`。下次再要，又是一对系统调用，再加上缺页（`MCL_FUTURE` 下，新映射的页在 `mmap` 里一次缺完）。池和 arena 自己那块不会被 `free`，可进程里还有别人在走 glibc：第三方库、默认分配器的 STL 容器、日志和监控这些冷线程。

![前后对比：台座上一个用链子锁住的保险箱；之后同一个台座上箱子整个不见了——只剩那条仍然锁着的链子和挂锁悬在它原来的位置](/images/hot-path-allocators/torn-down-not-unlocked.jpg)

**解决**：glibc 把内存还给内核有三条路，用三个 `mallopt` 各关一条：

| 设置 | 关掉的路 | 效果 |
|---|---|---|
| `M_MMAP_MAX = 0` | 大分配单独 `mmap`，`free` 时 `munmap` | 所有分配都走堆，`free` 只在堆里记账 |
| `M_TRIM_THRESHOLD = -1` | 堆顶空出一大块时，缩堆还给内核 | 堆只涨不缩 |
| `M_ARENA_MAX = 1` | 每个新 arena 各自 `mmap` 一块内存 | 只用主 arena；分配只在启动时发生，多 arena 减少锁竞争的好处用不上 |

> **启动时先设 mallopt，再锁页**
>
> ```cpp
> mallopt(M_MMAP_MAX, 0);
> mallopt(M_TRIM_THRESHOLD, -1);
> mallopt(M_ARENA_MAX, 1);
> mlockall(MCL_CURRENT | MCL_FUTURE);   // 需要 CAP_IPC_LOCK，或 RLIMIT_MEMLOCK 足够大
> ```
>
> - **`mallopt` 要在第一次大分配之前调**：已经 `mmap` 出去的块不受影响。
> - **`mlockall` 可能失败**：权限或额度不够时返回错误，一页也不锁，启动时要检查返回值；补救办法见 4.1 的预先缺页。

### 4.4 拆映射会打断热核：TLB shootdown，进程跑起来以后地址空间只读不改 {#shootdown}

**痛点**：每个核的 TLB 缓存着虚拟地址到物理地址的翻译。一个核删掉映射（`munmap`）或收紧权限（`mprotect`）以后，别的核 TLB 里的旧翻译要作废，硬件不会自动同步，**只能给正在跑这个进程的每个核发一个核间中断（IPI），让它们自己清**。被打断的核要陷入内核、清掉 TLB 条目、再回来，这叫 **TLB shootdown**，一次几微秒。

**`isolcpus` 挡不住它。** `isolcpus` 管的是调度器把线程放到哪个核上；shootdown 的 IPI 按“哪些核正在跑这个进程的地址空间”投递，和调度无关。热线程隔离、绑核做得再好，同一进程里一个冷线程 `free` 了一大块内存，热核照样被打断一次。

**解决**：4.3 关掉 glibc 的 `munmap`，除了省掉系统调用和缺页，也省掉了 shootdown。**热路径进程跑起来以后，地址空间就不要再改了**：透明大页的后台合并、自动 NUMA 平衡也会改页表，要一起关掉。完整的触发来源和关法见 [TLB 专题 3.3](/zh/posts/low-latency-context-switch-page-table-tlb/#triggers)。

---

## 5. 几个线程共用一个池：链表头要无锁地取放，还要防 ABA {#aba}

前四节的池和 arena 都只在一个线程里用。这一节先说清为什么会有几个线程共用一个池的需求、什么时候其实不用共用，再讲共用时链表头怎么改成无锁栈，以及无锁栈特有的 ABA 问题。

### 5.1 为什么要共用：对象常在一个线程分配、在另一个线程释放 {#why-shared}

1. **最常见的需求是跨线程归还**
   - **典型场景**：行情接入线程从池里拿一个 `Message`，填好以后经 SPSC 环交给策略线程；策略线程处理完，要把它还回去。
   - **每个线程各管一个池就出问题**：策略线程只能还给自己的池。接入线程的池只出不进，很快用完；策略线程的池只进不出，越堆越多。
2. **其次是省内存**
   - **每个线程各留一份峰值容量，总量就是线程数倍**：池的内存还要锁住、预先缺页（第 4 节），留多了很贵。
   - **共用一个池，按全系统的峰值留就够了**：各线程的峰值一般不会同时到。
3. **共用以后，1.4 的池直接拿来用会出错**
   - **两个线程同时读 `free_head_`，会拿到同一个槽**：同一块内存发给了两个使用者。
   - **加一把 `mutex` 能修好，但又回到了抖动**：没人抢时每次加锁也要一次原子读改写；有人抢时，拿不到锁的线程睡下去，叫醒要几到几十 µs，正好落在尾延迟上（[#1](/zh/posts/cpu-affinity-core-isolation-numa/#share-nothing) 3.4）。

> **先判断要不要共用池**
> - **分配和释放在同一个线程**：每个线程一个池，用 1.4 的单线程版本，连原子操作都不要。
> - **跨线程归还，但只有一对线程、方向固定**：用完的对象（或它的下标）经一个 SPSC 环还给分配它的线程，由那个线程自己放回池里。池仍然是单线程的，HFT 里很常见。
> - **好几个线程都在分配、都在释放**：共用一个池，链表头改成无锁栈（5.2）。
> - **线程多、分配又频繁**：分两级。每个线程先用自己的一个小缓存，空了或满了再成批地找共用的池拿、还。glibc 的 tcache、tcmalloc 都是这个思路。

### 5.2 链表头改成原子变量，用 CAS 取放：这就是无锁空闲栈 {#lock-free-stack}

1. **分配（出栈）**：读出 `head` 和它的 `next`，用 CAS 把 `head` 从读到的值换成 `next`。这期间别的线程改过 `head`，CAS 失败，重读重试。
2. **释放（入栈）**：把还回来的槽的 `next` 指向当前的 `head`，再用 CAS 把 `head` 换成这个槽。
3. **为什么叫栈**：空闲链表只在头上进出，后进先出，所以它就是一个无锁栈。没有锁，谁也不会睡下去；CAS 失败的线程只是重试一次。

### 5.3 ABA：CAS 只比较值，head 变过又变回来它看不出 {#aba-problem}

**这种栈有一个经典的坑，叫 ABA：CAS 只比较值，看不出这个值中间变过、又变了回来**。 名字说的就是 `head` 从 A 变成 B，又变回 A。下面用 X、Y、Z 表示三个空闲槽，栈里一开始是 X → Y → Z：

| 时刻 | 线程 A（分配） | 别的线程 | 空闲栈 |
|---|---|---|---|
| 1 | 读到 `head = X`、`X.next = Y`，还没 CAS 就被换下 | | X → Y → Z |
| 2 | | 线程 B 分配两次，拿走 X 和 Y | Z |
| 3 | | 有线程把 X 还回来 | X → Z |
| 4 | CAS：`head` 还是 X，成功，`head` 改成 Y | | Y → Z，可 Y 正被 B 用着 |

时刻 4 以后，下一次分配会把 Y 再发出去，同一个槽同时给了两个使用者；刚还回来的 X 反而从栈里丢了，再也分不出去。

### 5.4 修法：链表头带一个版本号，CAS 连版本号一起比 {#tagged-head}

**修法是给 `head` 带一个版本号，每改一次加 1，CAS 同时比较下标和版本号**。 时刻 1 线程 A 读到的是（X，版本 5）；时刻 2、3 一共改了三次，`head` 变成（X，版本 8）。A 拿（X，5）去比，不相等，CAS 失败，重读以后重试。

槽用 32 位下标表示，下标和 32 位版本号正好打包进一个 `uint64_t`，普通的 64 位 CAS 就能一起比较。链表要是用指针，就得用 16 字节的 CAS（x86-64 的 `cmpxchg16b`），或者把版本号塞进 64 位指针用不到的高 16 位。版本号会回绕，但那要求线程 A 被换下的这一会儿里正好错过 $2^{32}$ 次修改，实际不会发生。

代码分三段看：槽和链表头怎么放，取一个槽，还一个槽。

**第一段：槽和链表头，一个 64 位的数里装下标和版本号**

```cpp
template <typename T>
class ConcurrentPool {
  struct Slot {
    // 对象就构造在这段字节上；放在第一个成员，对象地址就是槽地址
    alignas(T) unsigned char storage[sizeof(T)];
    // 空闲时：下一个空闲槽的下标（单独占字节、做成原子，原因见 5.5）
    std::atomic<std::uint32_t> next;
  };

  // 链表尾：栈空时，栈顶下标就是它
  static constexpr std::uint32_t kNil = UINT32_MAX;

  // 打包：高 32 位放版本号，低 32 位放槽的下标
  static std::uint64_t pack(std::uint32_t ver, std::uint32_t idx) {
    return (std::uint64_t(ver) << 32) | idx;
  }

  // 槽数组：分配、mlock、memset、串链表同 1.4
  Slot* slots_;
  // 链表头 =（版本号，栈顶下标），初值 pack(0, 0)
  std::atomic<std::uint64_t> head_;
```

- **用下标不用指针，是为了和版本号一起装进 64 位**：普通的 64 位 CAS（x86 上是 `lock cmpxchg`）一次就把两样一起比较。
- **`next` 单独占几个字节，而且是原子的**：别的线程读它时，这个槽可能正被人用着，原因见 5.5。

**第二段：`allocate`，从栈顶取一个槽**

```cpp
 public:
  template <typename... Args>
  T* allocate(Args&&... args) {
    // 1. 读栈顶的打包值（版本号 + 下标）
    //    acquire：和把这个槽压上栈的那次 CAS（release）配对，
    //    压栈的线程在 CAS 之前写的东西（槽里的字节、next）这里都看得到
    std::uint64_t old = head_.load(std::memory_order_acquire);
    for (;;) {
      // 2. 拆出低 32 位：栈顶槽的下标；是 kNil 说明池用完了
      std::uint32_t idx = static_cast<std::uint32_t>(old);
      if (idx == kNil) return nullptr;

      // 3. 读栈顶下面那个槽的下标
      //    这时它可能已经被别的线程改过，过时的值会在第 5 步被筛掉
      std::uint32_t next = slots_[idx].next.load(std::memory_order_relaxed);

      // 4. 算出新栈顶：版本号 + 1，下标换成 next
      std::uint64_t desired = pack(static_cast<std::uint32_t>(old >> 32) + 1, next);

      // 5. CAS：head_ 还等于 old（下标和版本号都没变），才换成 desired
      //    失败时 old 被自动换成最新值，回到第 2 步重来
      if (head_.compare_exchange_weak(old, desired,
                                      std::memory_order_acquire,     // 成功
                                      std::memory_order_acquire)) {  // 失败：接着要读新栈顶的 next
        // 6. 这个槽已经从栈上摘下来、只属于我，在它的字节上原地构造对象
        return ::new (slots_[idx].storage) T(std::forward<Args>(args)...);
      }
    }
  }
```

- **第 3 步读到的 `next` 过时了也没关系**：第 1 步到第 5 步之间有别的线程动过 `head_`，版本号就变了，第 5 步一定失败，过时的 `next` 跟着被丢掉。
- **第 5 步比较的是整个 64 位**：栈顶下标哪怕又变回了 X，版本号也对不上。5.3 表里时刻 4 的那次 CAS，就是在这里失败的。
- **失败时 `old` 已经是最新值**：所以循环里不用再 `load`，直接从第 2 步重来。`weak` 版本偶尔会无故失败，反正在循环里，重试一次就好。
- **只有 CAS 成功的线程才走到第 6 步**：这个槽只属于它，这时才构造对象。

**第三段：`deallocate`，把槽压回栈顶**

```cpp
  void deallocate(T* obj) {
    // 1. 先析构对象，槽里只剩原始字节
    obj->~T();

    // 2. 由对象地址倒推回槽地址，再算出槽的下标
    auto* slot = reinterpret_cast<Slot*>(
        reinterpret_cast<unsigned char*>(obj) - offsetof(Slot, storage));
    std::uint32_t idx = static_cast<std::uint32_t>(slot - slots_);

    std::uint64_t old = head_.load(std::memory_order_relaxed);
    for (;;) {
      // 3. 让这个槽的 next 指向当前栈顶
      slot->next.store(static_cast<std::uint32_t>(old), std::memory_order_relaxed);

      // 4. 算出新栈顶：版本号 + 1，下标换成这个槽
      std::uint64_t desired = pack(static_cast<std::uint32_t>(old >> 32) + 1, idx);

      // 5. CAS：栈顶没变，才把这个槽压上去
      //    release：析构和刚写的 next 一起发布给下一个拿到它的线程
      //    失败说明栈顶换了，回到第 3 步，让 next 指向新栈顶
      if (head_.compare_exchange_weak(old, desired,
                                      std::memory_order_release,
                                      std::memory_order_relaxed)) {
        return;
      }
    }
  }
};
```

- **第 3 步每一轮都要重写 `next`**：CAS 失败说明栈顶换了，`next` 必须指向新的栈顶，再试一次。
- **压回栈顶，后进先出**：刚还回来的槽下一次最先被发出去，它多半还在缓存里。
- **入栈时也给版本号加 1**：严格说只靠出栈时加就防得住 ABA，因为一个槽要被别人拿走再还回来，中间一定有一次出栈；每改一次都加 1，规则更简单。

用 GCC 16.2 跑过一个压力测试：8 个线程共用一个 64 槽的池，各自分配、释放 20 万次，没有一个槽同时发给两个线程，结束后 64 个槽全部收回。

### 5.5 内存序：分配用 acquire，释放用 release {#pool-ordering}


- **分配时的读和 CAS 都用 acquire**：拿到槽的线程，要看得到上一个使用者释放前写进这个槽的内容，也要看得到释放时写下的 `next`。CAS 失败时会把最新的 `head` 读回 `old`，下一轮接着要读它的 `next`，所以失败的那一路也要 acquire。
- **释放的 CAS 用 release**：这个槽里的写入和刚写下的 `next`，随着这次 CAS 一起发布给下一个拿到它的线程。

把两段代码并排放，连上 release 到 acquire 的边（画法见 [#2 的 1.5](/zh/posts/memory-ordering-false-sharing-dependency-chains/#release-acquire)）：

<a href="/images/memory-ordering/edges.zh.svg" target="_blank" rel="noopener"><img src="/images/memory-ordering/edges.zh.svg" alt="左边是线程 A 的 deallocate，右边是线程 B 的 allocate。蓝色横边从 deallocate 里 CAS 成功时的 release 出发，一条连到 allocate 开头的 head_.load(acquire)，一条连到 allocate 里 CAS 失败时的 acquire。灰色竖边在每个线程内部从上到下：A 这边 release 上面有两处写，析构时写的槽里的字节和 next；B 这边 acquire 下面读 next，再在同一段字节上构造对象。A 的 head_.load(relaxed) 和 CAS 失败的 relaxed 没有边通到，读回来的 old 只当一个数用。" loading="lazy" decoding="async"></a>

**一个槽换手，是从释放它的线程交到下一个分配到它的线程手里**，所以配对的是 `deallocate` 的 release 和 `allocate` 的 acquire。释放的线程在 CAS 之前往这个槽里写过两样东西：

- **`storage` 里的字节**：对象活着时写的成员，加上析构函数里的写。析构不会把这段字节清零。
- **`next`**：`deallocate` 第 3 步写的，指向当时的栈顶。

下一个线程拿到槽以后要读 `next`，还要在 `storage` 上构造新对象。没有这一对 release 和 acquire，两件事都没有保证：

- **`next` 可能读到更早的值**：`head_` 已经指向这个槽，读到的 `next` 却是它上一次在栈上时的旧值。这时 `head_` 没有变过，第 5 步的 CAS 会成功，链表就接错了。版本号只筛得掉“读完以后栈顶又变了”，筛不掉这一种。
- **`storage` 是普通内存**：两个线程先后写同一段字节，中间没有先后关系，就是数据竞争。

**中间隔着别的线程的出栈，也配得上**。acquire 的规则是：读到的值是哪一次 release 的写入写的，就和那一次配对。可下面这种情况里，读到的值不是压栈的线程写的：

| 时刻 | 谁 | 做了什么 | `head_` | 这次写带 release 吗 |
|---|---|---|---|---|
| 1 | 线程 P | 写 `Y.next`，压入 Y | （Y，6） | 带 |
| 2 | 线程 Q | 写 `X.next` = Y，压入 X | （X，7） | 带 |
| 3 | 线程 R | 弹出 X | （Y，8） | 不带，出栈的 CAS 是 acquire |
| 4 | 线程 B | acquire 读到（Y，8），接着要读 `Y.next` | （Y，8） | |

B 读到的（Y，8）是 R 写的，R 那次写不带 release；`Y.next` 却是 P 在时刻 1 写的。只按“读到谁写的值就和谁配对”，B 和 P 配不上。

标准为这种情况补了一条规则，叫 release 序列：**一次 release 的写入之后，同一个原子变量上紧接着的修改只要是“读、改、写”一体的操作（CAS、`fetch_add` 这类），就都算作这次 release 的延续**；acquire 读到延续里的任何一个值，都和打头的那次 release 配对。道理是这类操作不会盲写，它先读到前一个值、在它的基础上才写，前一个值带着的先后关系跟着传了下去。

`head_` 的每一次修改都是 CAS，所以时刻 2、3 的写都是时刻 1 那次 release 的延续。B 读到（Y，8），就和 P 的 CAS 配上了对，P 在那之前写的 `Y.next` 和 Y 里的字节，B 都看得到。**这条链只有一种断法：有线程用普通的 `store` 直接覆盖 `head_`**，这里没有这样的写。

**CAS 的两个内存序，前一个管成功，后一个管失败**。成功是一次“读、比较、写”，失败只是一次读：

| | 成功 | 失败 |
|---|---|---|
| `deallocate` | release：把槽里的字节和 `next` 发布出去 | relaxed：读回来的新栈顶只当一个数用（写进 `next`、下一轮拿去比较），不去读它指的槽 |
| `allocate` | acquire：和第 1 步读到的是同一个值，第 1 步已经配过对，这里写 acquire 只是不用再多想一层 | acquire：读回来的是新栈顶，下一轮马上要读它指的槽的 `next` |

x86 上这几种写法编出来是同一条 `lock cmpxchg`，普通的读本来就有 acquire 的效果；区别出在 ARM 这类弱序的 CPU 上，以及编译器能不能把前后的读写挪过这条指令。

`next` 单独放、做成 `std::atomic`，不和 `storage` 共用字节，是因为时刻 1 的线程 A 读 `X.next` 时，X 可能已经被别的线程拿走、正在往 `storage` 里构造对象。两者分开，这次读就不是数据竞争；读到的旧值会随着失败的 CAS 被丢掉。

### 5.6 CAS 循环：按读到的栈顶算好新值，栈顶没变才提交 {#cas-loop}

`allocate` 和 `deallocate` 的循环是同一个形状，一共 3 步：

1. **读**：把 `head_` 读进 `old`，这是栈顶在某一刻的样子。
2. **算**：按 `old` 算出想要的新栈顶 `desired`。这一步只动自己手里的东西，别的线程看不到。
3. **提交**：CAS 问一句“`head_` 还等于 `old` 吗”。等于，说明第 2 步的依据还成立，换成 `desired`；不等于，说明依据过时了，算出来的 `desired` 作废，拿着新读回来的 `old` 回到第 2 步。

**CAS 不拦人，只在提交的那一刻检查依据还成不成立**。锁是先拿到资格再干活，别人等着；CAS 循环是每个线程先各干各的，提交时只有一个成功，别的发现依据变了，重算一遍。

所以不管几个线程在做什么操作、动的是不是同一个槽，它们抢的都只有 `head_` 这一个数。下面是线程 A 在 `allocate`、线程 B 在 `deallocate` 槽 S9，两边同时开始，栈是 S1 → S2：

| | 线程 A：`allocate` | 线程 B：`deallocate`（S9） | `head_` |
|---|---|---|---|
| 读 | `old` =（S1，版本 5） | `old` =（S1，版本 5） | （S1，5） |
| 算 | 读 `S1.next` 得 S2，`desired` =（S2，6） | 写 `S9.next` = S1，`desired` =（S9，6） | （S1，5） |
| 提交 | | CAS 成功 | （S9，6） |
| 提交 | CAS 失败，`old` 换成（S9，6） | | （S9，6） |
| 重算 | 读 `S9.next` 得 S1，`desired` =（S1，7） | | （S9，6） |
| 提交 | CAS 成功，A 拿到 S9 | | （S1，7） |

结果和“B 先还完 S9、A 再来取”一模一样。反过来 A 的 CAS 先成功也一样：A 拿走 S1，`head_` 变成（S2，6）；B 失败后把 `S9.next` 改写成 S2，再提交，结果和“A 先取、B 再还”一样。**成功的 CAS 排成一队，每一次都是按它前一个值算出来的**，所以并发的结果总等于这些操作一个接一个做的结果。

这个形状要成立，有 3 个条件：

- **比较的那个值要能代表全部依据**：“`head_` 等于 `old`”必须意味着“从读到现在栈没变过”。只比下标做不到，栈顶可以变过又变回来（5.3），所以要带版本号。
- **提交之前做的事，别的线程看不到，或者作废了也无妨**：`deallocate` 在 CAS 之前写的是 `S9.next`，这时 S9 还在 B 自己手里；`allocate` 在 CAS 之前只读不写，构造对象放在成功之后。失败时要撤销的东西一样也没有。
- **一个线程失败，一定是因为另一个线程成功了**：所以整体总在往前走，没有谁能卡住所有人，这就是无锁（lock-free）。单个线程可能连着失败几次，不保证它在多少步内完成。

**CAS 管的是先后，内存序管的是槽里的东西带不带得过去**：谁的修改排在前面由 CAS 决定；排在后面的线程看不看得到前面的线程写进槽里的字节和 `next`，由 5.5 的 release 和 acquire 保证。

### 5.7 槽不还给系统：省掉了无锁栈最难的回收问题 {#no-reclaim}

**池里的槽从栈上弹出以后，还在那个数组里**：用完再压回来，从头到尾不还给系统。所以别的线程晚一步去读它的 `next`，读的总是一块有效的内存；读到的值过时了，也会在 CAS 时被版本号筛掉（5.4 `allocate` 的第 3 步）。

**但一般的无锁栈，弹出一个节点以后要 `delete` 它**。这时别的线程可能刚读到这个节点的地址，正要读它的 `next`，读的就是已经释放的内存。

**于是一般的无锁栈必须多做一件事：等所有还拿着这个节点的线程都放手，才释放它**。hazard pointer、epoch 这类回收方案做的就是这件事，它是无锁结构里最难写对的部分。池不 `delete`，这件事就不用做。

## 6. 案例：无锁哈希表，难的是换下来的旧节点什么时候能释放 {#case-lockfree-map}

**要做的东西**：一张几个线程同时读写的哈希表，读和写都不加锁；值被更新或删除以后，旧的值要释放掉，而且释放不能让读写的线程停下来等。回收用 epoch-based reclamation（和内核的 RCU 是同一个思路）。

这里面有两件事：表本身怎么写，换下来的旧值什么时候释放。5.7 的池靠槽永远不还给系统躲开了第二件，这张表的值用完要 `delete`，躲不开。下面先把表做到最简单（6.1），看清楚释放到底卡在哪（6.2），再解决它（6.3）。

### 6.1 表：固定容量、开放寻址，键只占槽不腾槽，值整个换指针 {#case-map}

这张表用在键的个数有上限的地方，比如键是合约 id、订单号段。有了这个前提，无锁哈希表里最难写的三样（扩容、把键从槽里拿掉、就地改值）都用不上，表可以定成下面这个样子。工业库里也有这个形状的表：folly 的 `AtomicHashArray` 就是固定容量、线性探测、删掉的键不腾槽。没有这个前提、三样都要做的时候怎么做，放在 6.6。

- **固定容量、不扩容**：键的个数有上限，直接按上限开够。
- **开放寻址、线性探测**：槽连续放在一个数组里，探测时访问的是相邻的内存。
- **键一旦写进槽就不再改，删除只把值指针换成空**：探测链不会断，找键这一步也就不需要任何保护。代价是删掉的键仍然占着槽，所以键的总数不能超过容量。
- **值不就地改**：更新时分配一个新节点，一次原子交换把指针换过去。读者要么看到旧节点、要么看到新节点，不会看到改了一半的。

这样一个槽里只有两样东西：一个键，一个指向值节点的指针。键用 CAS 占，值用原子交换换。

```cpp
#include <atomic>
#include <cstdint>
#include <utility>
#include <vector>

struct Node {
    uint64_t val;
    explicit Node(uint64_t v) : val(v) {}
};

class Ebr;   // 回收器，定义在 6.3

// 固定容量、开放寻址的无锁哈希表：键是非 0 的 64 位整数，值是指向节点的指针
class LockFreeMap {
public:
    LockFreeMap(size_t cap_pow2, Ebr& ebr) : slots_(cap_pow2), mask_(cap_pow2 - 1), ebr_(ebr) {}

    // 插入或更新；表满了返回 false
    bool put(int tid, uint64_t key, uint64_t val) {
        Slot* s = find_slot(key, true);
        if (!s) return false;
        // 1. 不就地改：分配一个新节点，一次原子交换把指针换过去
        Node* old = s->node.exchange(new Node(val), std::memory_order_seq_cst);
        // 2. 换下来的旧节点可能还有读者在读，交给 Ebr
        if (old) ebr_.retire(tid, old);
        return true;
    }

    // 删除：只把值指针换成空；键留在槽里，探测链不会断
    void erase(int tid, uint64_t key) {
        Slot* s = find_slot(key, false);
        if (!s) return;
        Node* old = s->node.exchange(nullptr, std::memory_order_seq_cst);
        if (old) ebr_.retire(tid, old);
    }

    bool get(int tid, uint64_t key, uint64_t& out) {
        // 1. 进临界区：从这里到 leave，读到的节点都不会被释放
        ebr_.enter(tid);
        Slot* s = find_slot(key, false);
        Node* n = s ? s->node.load(std::memory_order_seq_cst) : nullptr;
        if (n) out = n->val;
        // 2. 值已经拷出来了，离开以后不再碰 n
        ebr_.leave(tid);
        return n != nullptr;
    }

private:
    struct Slot {
        std::atomic<uint64_t> key{0};        // 0 表示空槽
        std::atomic<Node*> node{nullptr};
    };

    // 线性探测。键一旦写进槽就不再改，所以找键这一步不需要保护
    Slot* find_slot(uint64_t key, bool claim) {
        size_t i = (key * 0x9E3779B97F4A7C15ull) >> 32 & mask_;
        for (size_t n = 0; n <= mask_; ++n, i = (i + 1) & mask_) {
            uint64_t cur = slots_[i].key.load(std::memory_order_acquire);
            if (cur == key) return &slots_[i];
            if (cur != 0) continue;
            // 1. 碰到空槽：查找到此为止；插入就用 CAS 把它占下来
            if (!claim) return nullptr;
            if (slots_[i].key.compare_exchange_strong(cur, key, std::memory_order_acq_rel)) return &slots_[i];
            // 2. CAS 失败说明别人刚占了这个槽；占的正好是同一个键就用它，否则接着往后找
            if (cur == key) return &slots_[i];
        }
        return nullptr;
    }

    std::vector<Slot> slots_;
    size_t mask_;
    Ebr& ebr_;
};
```

- **两个线程同时插入同一个键**：只有一个 CAS 成功，失败的那个看到槽里已经是这个键，直接用它。两个线程随后各自交换值指针，后换的留下，先换的那个节点被当成旧节点交给回收。
- **读路径没有锁，也不写共享的缓存行**（读者自己的那条公告除外，见 6.3），所以多个读者之间不会互相拖慢。

### 6.2 卡在哪：旧节点换下来的那一刻，可能还有读者拿着它 {#case-problem}

6.1 的 `put` 和 `erase` 都会换下来一个旧节点 `old`。它不能马上 `delete`，因为 `get` 是分两步的：先读出指针 `n`，再读 `n->val`。写者正好插在这两步中间时：

| 时刻 | 读者（`get`） | 写者（`put`） |
|---|---|---|
| 1 | 读出指针 `n`，指向旧节点 | |
| 2 | | 把指针换成新节点，拿到 `old`（就是 `n` 指的那个） |
| 3 | | 如果这时 `delete old` |
| 4 | 读 `n->val`：读的是已经释放的内存 | |

所以 `old` 要等一等再释放。等到什么时候，由两条事实决定：

- **换下来以后才来的读者拿不到它**：表里的指针已经是新节点了。
- **可能拿着它的，只有换下来之前就已经在读的那些读者**。

**结论：换下来之前就在读的读者全都读完了，`old` 就可以释放**。剩下的问题是写者怎么知道这一点。问每个读者“你读完了吗”不行，读者不停地进进出出。6.3 的办法是让读者自己报到，写者只看报到的记录。

### 6.3 回收：读者公告自己在第几代，旧节点等 epoch 多 2 再释放 {#case-ebr}

办法分 4 步：

1. **全局有一个 epoch 号，一个不断变大的整数**。读者开始读之前公告“我是第 e 代进来的”，e 就是当时的 epoch；读完以后把公告改成“不在”。从公告到改成“不在”这一段叫临界区。
2. **写者把节点换下来以后不释放**：记下这时是第几代，把（代数，节点）放进自己的待释放列表。
3. **epoch 前进有一个条件**：每个还在临界区里的读者，公告的都是当前这一代，epoch 才能加 1。有一个读者还停在旧的一代，就推不动。
4. **节点是第 r 代换下来的，epoch 到了 r + 2 才释放**。

第 4 步为什么是多 2，用一次具体的过程看：

| 时刻 | 发生了什么 | epoch | 读者 R 的公告 | 旧节点 X |
|---|---|---|---|---|
| 1 | R 进临界区，公告 5，读到 X 的指针 | 5 | 5 | 在表里 |
| 2 | 写者把 X 换下来，记下“第 5 代换下来的” | 5 | 5 | 待释放 |
| 3 | 写者试着推进：R 公告的 5 等于当前 epoch，可以加 1 | 6 | 5 | 待释放，R 还拿着它 |
| 4 | 再试着推进：R 公告的 5 不等于 6，推不动 | 6 | 5 | 待释放 |
| 5 | R 读完离开 | 6 | 不在 | 待释放 |
| 6 | 再试着推进：没有读者停在旧的一代，加 1 | 7 | 不在 | $7 = 5 + 2$，释放 |

- **多 1 不够**：时刻 3 epoch 已经是 6，R 还拿着 X。epoch 从 5 走到 6，只要求在场的读者公告的是 5，R 正好满足。
- **多 2 就够了**：epoch 从 6 走到 7，要求在场的读者公告的都是 6。换下 X 之前就进来的读者，公告的不会超过 5，只要其中还有一个在场，epoch 就停在 6。所以 epoch 到了 7，这些读者一定都走了。

```cpp
// epoch-based reclamation：读者进临界区时公告自己所在的 epoch，旧节点等所有读者都离开那个 epoch 才释放
class Ebr {
public:
    static constexpr int kMaxThreads = 64;
    static constexpr uint64_t kIdle = ~0ull;   // 不在临界区里

    // 读者进入：公告“我在第 e 代”
    void enter(int tid) {
        // 1. 公告（写）之后才去读共享指针（读）：先写后读正是 x86 会重排的那一种，所以用 seq_cst
        rec_[tid].epoch.store(global_.load(std::memory_order_seq_cst), std::memory_order_seq_cst);
    }
    // 读者离开：之后不再碰临界区里拿到的任何指针
    void leave(int tid) { rec_[tid].epoch.store(kIdle, std::memory_order_release); }

    // 写者：n 已经从表里摘下来，新来的读者拿不到它；记下摘的时候是第几代
    void retire(int tid, Node* n) {
        auto& limbo = rec_[tid].limbo;
        limbo.push_back({global_.load(std::memory_order_seq_cst), n});
        // 1. 攒够一批再处理，释放不是每次写都做
        if (limbo.size() < 64) return;
        try_advance();
        // 2. epoch 比节点的那一代多了 2，摘它之前进来的读者都已经离开，可以释放
        uint64_t g = global_.load(std::memory_order_seq_cst);
        size_t keep = 0;
        for (auto& [e, p] : limbo) {
            if (e + 2 <= g) delete p;
            else limbo[keep++] = {e, p};
        }
        limbo.resize(keep);
    }

private:
    // 所有在临界区里的线程都已经公告了当前这一代，epoch 才能加 1
    void try_advance() {
        uint64_t g = global_.load(std::memory_order_seq_cst);
        for (auto& r : rec_) {
            uint64_t e = r.epoch.load(std::memory_order_seq_cst);
            if (e != kIdle && e != g) return;   // 有读者还停在旧的一代，这次不推进
        }
        global_.compare_exchange_strong(g, g + 1, std::memory_order_seq_cst);
    }

    struct alignas(64) Rec {
        std::atomic<uint64_t> epoch{kIdle};
        std::vector<std::pair<uint64_t, Node*>> limbo;   // 这个线程摘下来、还没释放的节点
    };
    Rec rec_[kMaxThreads];
    std::atomic<uint64_t> global_{0};
};
```

- **回收不打断任何线程**：读路径上没有释放；写路径上攒够一批才处理一次；没有任何一步要让所有线程停下来等。要更平滑，可以把待释放列表交给后台线程去放。
- **公告要用 `seq_cst`**：读者先写自己的公告、再读共享指针，正是 x86 会重排的“先写后读”（[#2 1.3](/zh/posts/memory-ordering-false-sharing-dependency-chains/#four-reorderings)）。重排以后，写者扫描时看不到这个读者，读者却已经拿到了旧节点。
- **线程编号**：代码里由调用方传 `tid`，实际用的时候每个线程第一次进来时登记一个，存在 `thread_local` 里。

### 6.4 取舍：一个读者卡住，内存就一直涨 {#case-ebr-tradeoff}

- **epoch 回收的弱点**：只要有一个读者停在临界区里不出来（被调度走了、死循环了），epoch 就推进不了，所有线程的待释放列表都只进不出。
- **hazard pointer 是另一种方案**：读者公告的不是“我在第几代”，而是“我正在用这个指针”。一个读者卡住只拖住它公告的那几个节点，待释放的内存有上限。代价是每读一个节点都要多一次公告的写，而且同样是先写后读，要一道全屏障。
- **RCU 是同一个思想在内核里的做法**：读端几乎不花钱；写端等一个宽限期，确认每个 CPU 都经过了一次不在读端临界区的时刻，再释放。epoch 前进两次，相当于一个宽限期。
- **交易系统里常见的做法是绕开它**：
  - **按合约分片，每个线程只碰自己那一片**：表根本不共享，也就没有回收问题（[交易系统架构 3.2](/zh/ref/trading-architecture/#shard)）。
  - **节点从固定大小的池里取，用完还回池里，永远不还给系统**：读到的最多是被复用的槽，配上版本号就能发现（[未定义行为 4.3](/zh/ref/undefined-behavior/#uaf-pool)）。
  - **热线程都绑在隔离核上、一直在跑**：读者不会被调度走，epoch 推得动，epoch 回收的弱点碰不到。

### 6.5 另外两种做法：按哈希低位分片加锁，回收交给后台线程 {#case-shard-lock}

**按哈希低位分片加锁：不追求无锁，把一把大锁拆成很多把小锁**

- **怎么拆**：开 $2^k$ 个分片，每个分片是一张普通哈希表加一把锁。键算出哈希 $h$ 后，用低 $k$ 位 `h & (2^k - 1)` 选分片，只锁这一片。
- **为什么够用**：两个线程只有落到同一片时才会互相等，分片数取线程数的几倍，撞上的概率就很低。读多写少时，每片用读写锁或者 seqlock，读者几乎不等。
- **一个容易踩的地方**：分片用了哈希的低位，分片里面选桶就不能再用同样的低位，否则一个分片里的键低位全相同，只落在几个桶里。分片里改用高位，或者用 $h \gg k$ 再取模。
- **代价**：拿锁要一次原子操作，抢同一片时要排队；读者也拿锁（互斥锁或读写锁）时没有回收问题，删掉的节点在锁里直接释放，因为拿到锁之后不会有人还在读它；读者用 seqlock 不拿锁时，又回到要延迟释放。

**回收交给后台线程：热路径上只入队，不释放**

- **做法**：写线程把换下来的旧节点连同当时的 epoch，放进一个队列（每个写线程一条 SPSC 队列就够），立刻返回。后台线程不断从队列里取，等到 epoch 前进两次、确认没有读者还拿着它，再 `delete`。
- **为什么更平滑**：6.3 里的 `retire` 攒满 64 个会在写线程上做一次批量释放，这一下的耗时落在热路径上。挪到后台线程以后，写线程每次只多一次入队，延迟稳定。
- **代价**：多一个线程、多一条队列；后台线程如果跟不上，队列会涨，所以要监控队列长度。内核的 RCU 也是这样做的：`call_rcu` 只登记回调，宽限期过了由后台处理。

### 6.6 键的个数没有上限时：扩容、腾槽、小的值直接放进槽里 {#case-map-full}

6.1 的表靠“键的个数有上限”这个前提省掉了三样。前提不成立时，每一样的常见做法如下（一般做法，本页没有给出代码，也没有实测）。

- **扩容：开一张更大的新表，一格一格搬过去，旧表整张交给 6.3 的回收**
  - 写者发现表快满了，分配一张 2 倍大的新表，用 CAS 把“新表的指针”挂到旧表上；挂上以后，所有写者都知道正在搬。
  - 搬一格分两步：先把旧槽的值换成一个“已搬走”的标记，再把值写进新表。读者和写者在旧表里碰到这个标记，就去新表找。
  - 所有格都搬完，把表的入口指针换成新表；旧表和一个旧节点一样，可能还有读者拿着，所以同样等 epoch 多 2 再释放。
  - 难写对的是搬的过程中同时有人改同一格：改的人要么在标记之前改完（值会被搬走），要么看到标记以后去新表改，不能两头都落空。
- **腾槽：删掉的键留一个墓碑，墓碑多了就重建一次**
  - 开放寻址的表不能把键直接清成空，否则探测链在这里断开，后面的键就找不到了。所以删除只留一个墓碑：查找时跳过它继续往后探测。
  - 墓碑仍然占槽。占得多了，就按扩容的办法搬到一张同样大小的新表里，搬的时候不带墓碑。
- **值不超过 8 字节时：直接放进槽里的原子变量，不要节点**
  - 值是一个整数或一个价格时，槽里放 `std::atomic<uint64_t>`，更新就是一次 `store` 或 CAS。
  - 没有节点，也就没有“旧节点什么时候释放”的问题，6.2 和 6.3 整个用不上。能这样做时优先这样做。
