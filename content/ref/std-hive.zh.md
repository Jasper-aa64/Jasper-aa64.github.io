---
title: "C++26 std::hive：复杂度、用法与边界"
date: 2026-11-15
slug: "std-hive"
description: "std::hive 是 C++26 的分块序列容器：存活对象增删时地址稳定，遍历能跳过删除留下的空槽。本文从 vector、list、map 的对比讲起，列出插入、删除、遍历、reserve、sort 的复杂度，并用活跃订单索引说明基本用法。"
summary: "std::hive 适合对象频繁增删、又要稳定引用或指针的场景。单元素插入常数复杂度；删除通常常数，但清空内存块时还要处理块元数据。它不是 map，也不是 vector：没有按键查找、下标和连续存储。"
toc: true
math: true
group: cpplinux
topic: ds
weight: 123
---

`std::hive` 是 C++26 新增的序列容器，源自 `plf::colony`。它针对一个很具体的组合：**对象会频繁插入、删除；其他数据结构还要长期引用仍存活的对象；程序又需要比链表更适合遍历的存储方式。**

先把它放在容器地图里看：

| 容器 | 适合的访问方式 | 主要代价 |
|---|---|---|
| `std::vector` | 连续遍历、随机访问、下标 | 扩容会搬家，中间增删会移动后续元素 |
| `std::list` | 已知位置频繁插入删除，保留其他节点地址 | 节点分散，遍历要追指针，分配次数多 |
| `std::map` | 按键查找、保持键的有序关系 | 查找、增删为 O(log N)，逐节点遍历 |
| `std::hive` | 遍历一组对象，同时需要存活对象地址稳定 | 分块、有空槽；没有按键查找和随机访问 |

**一句话：hive 管对象集合，不管键索引。**若订单要按 ID 查找，仍需要 `map` 或哈希表；hive 本身不提供 `find(id)`。

## 1. 内存里发生什么

元素保存在多个内存块中。删除一个元素时，在它自己的槽位析构，不把后面的元素搬过来。块内的 skipfield 标记哪些位置已经删除，遍历时跨过这些空槽。之后插入可以复用空槽；没有可用槽位时，容器才需要申请新块。

```text
同一个元素块：
[ Order A ][ 删除留下的空槽 ][ Order D ][ Order E ]
                         └── 遍历跳过空槽
```

因此，插入或删除其他元素不会搬动仍存活元素，它们的指针和引用保持有效。被删除元素自己的指针、引用和迭代器则失效。skipfield 的具体表示由实现决定；标准没有承诺无分支代码，也没有承诺插入永远不向分配器要内存。

插入位置由容器决定，可能复用任意空槽，**不能用遍历顺序代表订单优先级、FIFO 顺序或插入顺序**。迭代器是双向迭代器：可以向前后走，但不支持 `it + n` 的随机跳转。容器也没有 `operator[]` 和 `data()`。

## 2. 复杂度表：Big O 不等于延迟上界

以下是 C++ 工作草案对主要操作的复杂度要求。令 `N` 为存活元素数、`k` 为被删除的元素数、`B` 为相关内存块数。

| 操作 | 复杂度 | 实际需要留意的事 |
|---|---:|---|
| `emplace(args...)` / 单元素 `insert` | O(1) | 可能申请新块；常数复杂度不代表固定纳秒数 |
| `erase(pos)` | O(1)，若因此清空块，另有 O(B) 级块处理 | 被删元素的对象会析构；其他存活元素不搬动 |
| `erase(first, last)` | O(k)，若清空块，另有 O(B) 级块处理 | 大范围删除自然随删除数量增长 |
| `++it` / `--it` | O(1) | 整体遍历 N 个存活元素为 O(N)，跳过空槽不改变线性总量级 |
| `size()` / `empty()` / `capacity()` | O(1) | `capacity()` 是不再申请新块时可容纳的元素总量 |
| `reserve(n)` | 随预留块数量线性增长 | 可能分配多个块；不会搬动现存元素，能减少后续分配 |
| `get_iterator(pointer)` | O(B) | 从裸指针反查迭代器会扫块，别未经测量放进热路径 |
| `sort()` | O(N log N) 次比较 | 可能分配，并可能使元素指针、引用和迭代器失效 |

这些复杂度刻画容器操作的增长率，不是实时延迟保证。O(1) 的 `emplace` 仍可能遇到分配器、首次触页和缓存未命中；反过来，给容器预留容量后，元素插入不一定需要申请新块。`reserve()` 也不等于把所有页都预先触碰进物理内存。低延迟系统还要单独处理分配器和缺页，并按目标标准库实测。

**复杂度表按当前公开工作草案列出，相关措辞仍有待标准问题处理。**LWG 4320 目前以新问题状态讨论插入、删除是否应规定为 O(log N)，LWG 4380 也在讨论 `reserve()` 复杂度是否计入释放块的工作。因此，表中的 O(1) 是当前草案文字，不能当成所有已发布标准库都必须兑现的实际延迟承诺；依赖这个界限前，要核对目标标准版本和库实现。[LWG 活跃问题列表](https://www.open-std.org/jtc1/sc22/wg21/docs/lwg-active.html)

## 3. 基本用法：hive 存对象，索引按 ID 查

例如 OMS 的订单既要按 ID 撤单，也要按存活对象遍历计算风险。可以让 hive 管对象，让哈希表保存 ID 到 hive 迭代器的映射：

```cpp
#include <cstdint>
#include <hive>
#include <unordered_map>
#include <utility>

struct Order {
  std::uint64_t id;
  std::int64_t price;
  std::uint32_t quantity;
};

std::hive<Order> active_orders;
using OrderIt = std::hive<Order>::iterator;
std::unordered_map<std::uint64_t, OrderIt> by_id;

void prepare() {
  active_orders.reserve(100'000);  // 在进入热路径前预留容量
}

void add_order(Order order) {
  auto it = active_orders.emplace(std::move(order));
  by_id.emplace(it->id, it);
}

void cancel_order(std::uint64_t id) {
  auto index_it = by_id.find(id);
  if (index_it == by_id.end()) return;

  active_orders.erase(index_it->second);
  by_id.erase(index_it);
}

void visit_orders() {
  for (const Order& order : active_orders) {
    // 用 order 计算风险或更新状态
  }
}
```

插入或删除别的订单时，`OrderIt` 仍指向原来的存活对象；这样不必把对象地址塞进键表。若确实要保存 `Order*`，普通插入和删除其他元素时地址也保持稳定，但要记得对象被撤销后立即清理指针。

注意：`by_id` 自己仍可能在 rehash 时搬动哈希桶；它存的 hive 迭代器指向的订单不受影响。容器不是并发容器，多线程同时修改它需要外部同步。`std::hive` 及 `<hive>` 的可用性取决于编译器和标准库版本，部署前要确认目标工具链已经实现所需接口。

## 4. 什么场景该选它

适合考虑 hive 的信号：

- 元素的地址需要稳定，且对象会频繁插入、删除。
- 程序要反复遍历存活对象；链表的局部性和分配成本已经成为问题。
- 集合本身不需要按键排序，也不需要随机访问。

不适合的信号：

- 主要工作是紧密顺序扫描、几乎不删除：优先测 `vector`，它连续存储，往往更快。
- 主要工作是按键查找：使用 `map`、`unordered_map` 或“hive + 单独索引”，按访问模式测。
- 必须严格按插入顺序处理：使用明确保序的结构；hive 的新元素位置不由调用者指定。
- 需要硬实时延迟或热路径绝不分配：hive 的 O(1) 复杂度本身不足以保证这一点，要预留、预热、检查标准库实现并测量尾延迟。

如果调用 `sort()`，标准允许它移动元素并使相关指针、引用和迭代器失效；用 hive 的稳定地址承载外部句柄时，不要假定排序后句柄仍指向原来的对象。需要按优先级访问时，通常应排序 ID/迭代器索引，而不是直接排序存活对象。

## 5. 一页记住

- **hive 是序列容器，不是 map。**它不存 key，也不按 key 查找。
- **单元素插入、删除通常是 O(1)，**范围删除是 O(k)；清空块时还要处理块结构。
- **其他存活元素地址稳定，**但被删除元素的句柄失效；`sort()` 等重排操作也可能使句柄失效。
- **分块让它比链表更适合遍历，但不如 vector 连续。**用它的理由应是“稳定地址 + 频繁增删”，不是泛泛地追求更快。

参考：WG21 [C++ 工作草案：hive 概览](https://eel.is/c++draft/hive.overview)、[修饰操作与复杂度](https://eel.is/c++draft/hive.modifiers)、[容量与 reserve](https://eel.is/c++draft/hive.capacity)、[其他操作](https://eel.is/c++draft/hive.operations)，以及提案 [P0447R28](https://www.open-std.org/jtc1/sc22/WG21/docs/papers/2024/p0447r28.html)。

