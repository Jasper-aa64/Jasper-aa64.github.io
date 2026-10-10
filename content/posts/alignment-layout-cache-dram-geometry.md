---
title: "Trading System Notes #6: Alignment, Layout, and Cache and DRAM Geometry"
date: 2026-10-04
slug: "alignment-layout-cache-dram-geometry"
description: "Why every hot-path memory decision comes down to which cache lines an access touches and where those lines live. Three parts: alignment (padding, alignas, over-aligned heap memory, a two-tier allocator, pack), layout (AoS/SoA, proxy views, denormalization, field order, inline arrays, function grouping), and hardware geometry (set associativity from scratch, the critical stride measured on an M1, storage classes, inside a DIMM, refresh, channel balance)."
summary: "An access never pays for bytes; it pays for cache lines, and the address decides which lines, which cache set they compete for, and which DRAM channel and bank they live on. Part 1 is alignment: why a double aligned to 8 never straddles a line, why padding exists for arrays, alignas on a type versus a member, and how to get 64-byte and 2 MiB alignment on the heap. Part 2 is layout: lines per access, AoS versus SoA, and denormalization as a way to cut a dependency chain. Part 3 goes into the hardware: L1 picks a set from address bits 6–11, so data 4 KiB apart competes for 8 slots however empty the cache is (measured on an M1); a DRAM bank has one row buffer, 14 ns on a hit and 41 ns on a conflict; a column walk loses at five layers; refresh adds a P99 tail software can't remove; and channels balance only when the hot stride is coprime with the channel count."
chapter: 1
categories: [Systems]
tags: [cpp, alignment, cache, memory-layout, false-sharing, dram, numa, hft, low-latency]
toc: true
homepage: false
---

People in low-latency work say "cache-friendly" a lot, but whether a piece of code is friendly always comes down to something concrete. Start with an example:

```cpp
int m[64][1024];             // 64 rows of 1024 ints
long long sum = 0;
for (int j = 0; j < 1024; ++j)
    for (int i = 0; i < 64; ++i)
        sum += m[i][j];      // add up the whole matrix, column by column
```

Here's the question: make each row 1040 `int`s instead of 1024. The 16 extra ints are never read, and the loop does exactly the same number of iterations. What happens to the speed?

The intuition is "nothing, maybe slightly slower — the array got bigger". In fact it usually gets several times faster. I ran the same experiment on an M1 (where the matching row width is 16 KiB, for reasons explained below), and the version padded by one cache line per row was 4× faster than the unpadded one.

How can bytes you never read make a program faster? The answer isn't in the algorithm; it's in the **addresses**. The CPU always moves data in whole 64-byte **cache lines**, and a few bits of an address decide which slot of the cache a line goes into and which corner of the DIMM it lives in. This post starts from alignment and works down to DRAM, and by the end the question answers itself (section 3.2.1).

First, the route. A load works its way down: the TLB translates the virtual address, then L1D, L2 and the shared L3 are asked in turn, and on a miss everywhere the memory controller goes to a DIMM. Everything below happens in one of the boxes along that route; the full <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a> lives on the Reference page and grows with the series.

So "is this code fast" is largely two questions. First, **how many lines does one access touch?** A value straddling two lines costs two; a loop that uses a third of each line moves the other two-thirds for nothing. That's alignment (Part 1) and layout (Part 2), which you control directly when writing code. Second, **where do those lines live?** If your access pattern keeps certain address bits equal, most of the hardware sits idle while a small part thrashes. That's Part 3, the layer that's easiest not to see.

## 1. Alignment: Keep a Value Inside One Line

### 1.1 What Alignment Is, and Why the CPU Cares

A value is **aligned to N** when its address is a multiple of N; `alignof(T)` is the N a type requires. On x86-64 the fundamental types are aligned to their own size: `char` 1, `int` 4, `double` and pointers 8.

The CPU cares because of cache lines. Lines start at multiples of 64, and **64 is a multiple of 8** — that's the key sentence. A `double` aligned to 8 starts at a multiple of 8, so inside a line it can only start at offset 0, 8, 16 … 56, and the last one, 56–63, fills the line exactly. It **can never straddle two lines**. `int` works the same way (64 is a multiple of 4). Conversely, a `double` at offset 60 has four bytes in this line and four in the next, and reading it touches two lines.

Straddling has a mild consequence and a severe one:

- **Mild: slower.** The load becomes two cache accesses — a **line split** — plus another translation if the two lines are in different 4 KiB pages. x86 doesn't fault, it just quietly slows down, which is why misalignment rarely announces itself on x86.
- **Severe: atomics.** A `lock`-prefixed read-modify-write is uninterruptible because the core holds its line exclusively until the instruction completes ([MESI cache coherence](/posts/low-latency-mesi-cache-coherence/)). Across two lines that's impossible, so the CPU falls back to locking the memory bus — a **split lock**, far more expensive than a normal atomic and disruptive to other cores; Linux has detected and reported it (`split_lock_detect`) since 5.7.

There's also a hard requirement: SIMD "aligned" loads and stores (SSE `movaps` and friends) need 16-byte alignment and fault without it.

Be careful generalizing. "Aligned to its own size never straddles" only holds for sizes that are **powers of two up to 64**. A 12-byte struct with `alignof` 4 only needs to start at a multiple of 4, and at offsets 56 or 60 it straddles — enumerate the 16 possible starting offsets in a line and 2 of them cross. Make it `alignas(16)`, which also pads it to 16 bytes, and none of its 4 possible starts crosses. Whether a struct straddles depends on **its size** and **the alignment you give it**, not on the word "aligned".

### 1.2 How the Compiler Does It: Padding

The compiler lays out a struct's members with three rules:

1. members go in declaration order, each at "the first offset from here on that's a multiple of its own alignment", with **padding** bytes in the gaps;
2. the struct's alignment is the largest member alignment;
3. `sizeof` is rounded up to a multiple of that alignment (**tail padding**).

```cpp
struct DefaultAlignedStruct {
    char a;      // offset 0, then 3 bytes of padding
    int b;       // offset 4
    double c;    // offset 8
};               // sizeof 16, alignof 8
static_assert(sizeof(DefaultAlignedStruct) == 16 && alignof(DefaultAlignedStruct) == 8);
```

Walk it: `a` at 0; `b` needs a multiple of 4, the next is 4, so bytes 1–3 are padding; `b` occupies 4–7; `c` needs a multiple of 8, and 8 fits, so 8–15; the end, 16, is already a multiple of 8.

**Rule 3 exists because of arrays.** Element *i* of `T arr[N]` sits at `base + i × sizeof(T)`. If `sizeof` weren't a multiple of `alignof`, element 0 would be aligned and element 1 wouldn't. For example `{double; int;}` ends its data at 12; without padding to 16, `arr[1]`'s `double` would sit at offset 12. So `sizeof` is always a multiple of `alignof`, even if the last member doesn't fill it.

**Member order changes the size:**

```cpp
struct Bad  { char a; double b; char c; int d; };   // 0, 8, 16, 20 → sizeof 24 (11 bytes padding)
struct Good { double b; int d; char a; char c; };   // 0, 8, 12, 13 → sizeof 16
static_assert(sizeof(Bad) == 24 && sizeof(Good) == 16);
```

`Bad`: `a` at 0; `b` jumps to 8 (7 bytes of padding); `c` at 16; `d` jumps to 20 (3 bytes); end 24. `Good`: `b` 0, `d` 8, `a` 12, `c` 13, end 14, tail-padded to 16. Same four members, 24 bytes versus 16. Rule of thumb: **order members from largest to smallest alignment and padding is minimal.** In an array the difference is real — a line holds 64 ÷ 24 ≈ 2.7 of one and exactly 4 of the other, so a scan touches a third fewer lines.

That only saves bytes, though. A hot-path struct also has to ask which members are always used together — that's Part 2, and section 2.4 settles what happens when the two goals collide.

### 1.3 `alignas`: Asking for More Alignment

`alignas(N)` requests stricter alignment than the default. On a **type** and on a **variable** it does different things:

```cpp
struct alignas(32) AlignasType { int data[5]; };    // 20 bytes of data
static_assert(sizeof(AlignasType) == 32 && alignof(AlignasType) == 32);

alignas(64) char buffer[100];                       // this variable starts on a line
static_assert(sizeof(buffer) == 100 && alignof(decltype(buffer)) == 1);
```

- **On a type**: 20 bytes of data, but the type's alignment becomes 32 and rule 3 pads `sizeof` to 32. Every object of this type starts at a multiple of 32 and occupies 32 bytes.
- **On a variable**: only this variable's **address** becomes a multiple of 64; `sizeof` stays 100 and the type `char[100]` keeps its own alignment.

64 is the usual choice: the object starts at the beginning of a line, and if its `sizeof` is also a multiple of 64 (64, 128, 192 … a whole number of lines) it **owns** those lines and no neighbour's writes contend with it. That's how false sharing is fixed ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)), and it's MESI's one-writer rule applied to memory layout.

**What "`sizeof` a multiple of 64" means.** Yes, the object may be bigger than a line. The point isn't size; it's that **both ends** fall on line boundaries: the start via `alignas(64)`, the end via `sizeof` being a multiple of 64. Otherwise the last line is only partly used, the rest may be taken by whatever follows, and writes on both sides fight over that line.

On a type the compiler does it for you: `struct alignas(64) { char x[100]; }` is 128, two whole lines. What you have to watch is `alignas(64)` on a **member**, which only moves the start and leaves `sizeof` alone:

```cpp
struct Two   { alignas(64) char a[100]; char b; };              // b at offset 100, sharing a's tail line
struct Three { alignas(64) char a[100]; alignas(64) char b; };  // b at offset 128, a line of its own
static_assert(offsetof(Two, b) == 100 && offsetof(Three, b) == 128);
```

```text
Two:     alignas(64) char a[100]; char b;        Big:  struct alignas(64) { char x[100]; }
line 0   a[0..63]                                line 0   x[0..63]
line 1   a[64..99] | b@100 | free                line 1   x[64..99] | 28 bytes padding   ← all of it is Big's
         ↑ a's tail and b share this line        line 2   the next object starts here
```

For a portable "line size", C++17 offers `std::hardware_destructive_interference_size` in `<new>` where the library provides it. And name the price: `alignas(64)` turns a 4-byte counter into 64 bytes. **You're buying isolation with space.**

### 1.4 Heap Alignment: `malloc` and Plain `new` Don't Care About 64

On the stack and for globals, write `alignas` and the compiler handles it. The heap is different: `malloc` and plain `new` only guarantee alignment for any fundamental type — 16 on x86-64 (`alignof(std::max_align_t)`). For 64 or more you need another interface.

**`std::aligned_alloc(alignment, size)`.** `size` must be a multiple of `alignment`, so round the request up first: 200 becomes 256 at 64-byte alignment, 300 becomes 320. Skip the rounding and the allocation fails with a null pointer, so check the result.

```cpp
#include <cstdlib>

void* make_buffer() {
    const size_t alignment = 64, requested = 300;
    size_t size = (requested + alignment - 1) / alignment * alignment;   // 320
    return std::aligned_alloc(alignment, size);                          // free with std::free
}
```

(Windows/MinGW has no `std::aligned_alloc`; the equivalent is `_aligned_malloc`, which must be paired with `_aligned_free`.)

**Over-aligned `new` (C++17).** When a type's own alignment exceeds the default (16), `new T` automatically calls `operator new(size_t, std::align_val_t)`, and `delete p` the matching deallocation — `new` on a `struct alignas(64) X` with plain `delete` is fine.

**The trap: alignment only at the `new` call, and `delete` doesn't follow.**

```cpp
struct Plain { float v[4]; };                              // the type itself only needs 4
auto* p = new (std::align_val_t{128}) Plain();             // allocation: the aligned version
delete p;                                                  // deallocation: the plain version — mismatched, UB
```

The `new` explicitly passes 128 and uses the aligned allocation; `delete p` looks at the **type's** alignment (not over-aligned) and calls the plain `operator delete`. Allocation and deallocation aren't a pair. Measured on Windows (g++, MinGW-w64), this crashes with exit code `0xC0000374` (heap corruption) — most likely the aligned allocation goes through `_aligned_malloc` and the plain `delete` through `free`. The rule: **to exceed a type's own alignment, either put the alignment on the type so `new`/`delete` pair themselves, or use the `align_val_t` versions on both sides**: `p->~Plain(); ::operator delete(p, std::align_val_t{128});`.

### 1.5 A Two-Tier Aligned Allocator

A production STL allocator wraps all of this; its core is this allocation logic:

```cpp
#include <cstdlib>
#include <cstring>
#include <new>
#include <sys/mman.h>

void* allocate_bytes(size_t num_bytes) {
    void* ptr = nullptr;
    if (num_bytes <= (1 << 14)) {                        // up to 16 KiB: line-aligned
        const size_t a = 64;
        size_t sz = (num_bytes + a - 1) & ~(a - 1);
        if ((ptr = std::aligned_alloc(a, sz))) std::memset(ptr, 0, sz);
    } else {                                             // larger: 2 MiB-aligned
        const size_t a = 1 << 21;
        size_t sz = (num_bytes + a - 1) & ~(a - 1);
        if ((ptr = std::aligned_alloc(a, sz))) {
#if defined(__linux__)
            madvise(ptr, sz, MADV_HUGEPAGE);             // must come before the first touch
#endif
            std::memset(ptr, 0, sz);
        }
    }
    if (!ptr) throw std::bad_alloc();
    return ptr;
}
```

Two tiers by request size:

- **≤ 16 KiB**: 64-byte aligned, size rounded to a multiple of 64, zeroed. Every allocation starts on a line and occupies whole lines, so two allocations never share one.
- **> 16 KiB**: **2 MiB aligned**, size rounded to a multiple of 2 MiB, `madvise(MADV_HUGEPAGE)` on Linux, then zeroed.

**Why the rounding mask works.** `(n + a - 1) & ~(a - 1)`: when `a` is a power of two, `a - 1` has all low bits set and `~(a - 1)` clears them, i.e. rounds *down* to a multiple of `a`; adding `a - 1` first turns that into rounding up. **Only for powers of two**: compared against the division version for every n from 0 to 100,000, `a = 48` disagrees on 66,672 values (the first is n = 1: 48 by division, 16 by mask) while `a = 64` disagrees on none. It's the same reason ring buffers use power-of-two capacities and `& mask` instead of `%` ([#4](/posts/lock-free-queue-logger-micro-batching/)).

**Why big blocks are aligned to 2 MiB.** 2 MiB is the x86-64 huge page size, and transparent huge pages (THP) can only back a range that is 2 MiB-aligned and 2 MiB long with one huge page. Misalign the start and the head and tail fall back to 4 KiB pages, eating into the TLB benefit; align the whole block and all of it qualifies.

**Why `madvise` must come before `memset`.** Pages are allocated on **first touch**, and that's when the kernel checks for the "huge page wanted" hint to decide between a huge page and a 4 KiB page. Zero first and advise afterwards and the pages are already small; small pages can't be promoted in place, so the background `khugepaged` thread has to copy and merge them later — which the application sees as an unpredictable stall. Zeroing has a useful side effect too: every page's first-touch fault (about 1.5 µs per page, measured in [#5](/posts/spmc-shared-memory-broadcast-ring/)) is paid at allocation time instead of the first time the hot path touches it.

Two costs of this design:

1. **Space amplification in the big tier.** A 20 KiB request lands in the big tier, rounds to 2 MiB and zeroes 2 MiB — a 20 KiB container physically occupies 2 MiB. Good for a few large arrays, bad for many medium containers.
2. **THP + `madvise` depends on a system setting.** HFT deployments more often reserve explicit huge pages (`mmap(MAP_HUGETLB)`) and disable THP; with THP set to `never`, `madvise` does nothing. If asked how an allocator gets huge pages: explicit huge pages are more predictable; THP + `madvise` is convenient but configuration-dependent.

### 1.6 `#pragma pack`: Giving Alignment Up

```cpp
#pragma pack(push, 1)
struct PackedStruct { char a; int b; double c; };   // offsets 0, 1, 5; sizeof 13, alignof 1
#pragma pack(pop)
static_assert(sizeof(PackedStruct) == 13);
```

`#pragma pack(push, 1)` tells the compiler "no padding between members, alignment 1". It reverses section 1.1: `b` and `c` no longer sit at aligned addresses, may straddle lines depending on where the struct lands, and in an array of 13-byte elements the starting offsets drift so some elements always straddle. Taking `&p.c` gives an unaligned `double*`; dereferencing it is undefined behaviour — x86 tolerates it, other architectures may not. **The compiler doesn't warn**: converting `&p.b` to `int*` and `&p.c` to `double*` is silent under `-Wall -Wextra -Wpedantic`. Atomics on such members can split-lock.

So what's it for? Making a struct's **byte layout match an external format** exactly — wire protocols, file formats. It describes the outside world; it isn't a memory optimization. When reading such data, `memcpy` fields into aligned locals first; a fixed-size `memcpy` compiles to a single load.

---

## 2. Layout: How Many Lines Does One Access Touch?

Every layout optimization asks the same thing: **how many cache lines does this access touch?** The tighter the data you need is packed into the lines you touch, the fewer lines you touch.

### 2.1 AoS or SoA: Which Members Does the Loop Read?

```cpp
struct Point1 { float x, y, z; };
Point1 points1[1000];                                  // array of structures (AoS)

struct Point2 { float x[1000], y[1000], z[1000]; };
Point2 points2;                                        // structure of arrays (SoA)
```

**AoS** (array of structures) stores complete structs, so one point's x, y and z are adjacent. **SoA** (structure of arrays) stores each member as its own array, so all the x values are adjacent.

Summing only x, the two layouts drag different data into cache. In AoS each element is 12 bytes, of which x is 4; y and z (8 bytes) come along with every line and go unused: 1000 points are 12,000 bytes, **188 lines**. SoA's x array is 4,000 bytes, **63 lines**. The factor of three is "useful bytes are one third".

Reverse it — use x, y and z of the same point together (say x² + y² + z²) — and AoS has the whole element in one line (two at most), while SoA's x, y and z are in three arrays 4,000 bytes apart, three lines. The rule is that symmetry: **all members of an element together → AoS; a scan over some members → SoA.**

Two caveats:

- **12 bytes isn't a power of two**, so AoS falls into section 1.1's trap: `Point1` has `alignof` 4, and with a 64-aligned array 2 of every 16 elements straddle a line. SoA's `float` arrays hold 16 per line and never straddle.
- **This example is only 12 KB and fits in L1D** (typically 32 KiB). The first pass pulls in 188 or 63 lines; after that everything is in L1 and the line count doesn't become time. The gap shows when **the working set is much larger than the cache** (every pass refetches lines from L2/L3/DRAM and bandwidth is the bottleneck) or with **vectorization**: SoA's contiguous x values fill an AVX register with 8 floats per load, while AoS has to pick them out from between y and z.

SoA's costs: `points[i].x` becomes `x[i]`; adding or removing elements touches N arrays whose lengths must stay in sync; fetching one complete element touches several lines.

### 2.2 AoS View over SoA Storage: Proxy Objects

To get SoA's memory layout without SoA's `x[i]` everywhere, put an interface that looks like AoS on top:

```cpp
#include <cstddef>
#include <vector>

class ParticleSoA;
struct ParticleRef {                                   // a "virtual element": storage + index
    ParticleSoA* storage;
    size_t index;
    float& x() const;
    float& vx() const;
};

class ParticleSoA {
    std::vector<float> x_, vx_;
    friend struct ParticleRef;
public:
    explicit ParticleSoA(size_t n) : x_(n), vx_(n) {}
    size_t size() const { return x_.size(); }
    ParticleRef operator[](size_t i) { return {this, i}; }
    std::vector<float>& x_array()  { return x_; }      // hot loops take the raw arrays
    std::vector<float>& vx_array() { return vx_; }
};

inline float& ParticleRef::x()  const { return storage->x_[index]; }
inline float& ParticleRef::vx() const { return storage->vx_[index]; }

void step(ParticleSoA& p) {
    p[0].x() = 10.0f;                                  // reads like AoS
    auto& x = p.x_array(); auto& vx = p.vx_array();
    for (size_t i = 0; i < p.size(); ++i) x[i] += vx[i];   // runs like SoA
}
```

The points:

- The **proxy** returned by `operator[]` has two fields, a storage pointer and an index (16 bytes), and is cheap to pass by value. `p[0].x()` returns a **reference** into the underlying array, so writes through the proxy change the real data — by design, not a bug.
- Callers read like AoS while memory is SoA. Performance-critical loops use the second form and get the contiguous `float` arrays, which is where SoA's cache and SIMD benefits actually come from; the proxy adds an index computation per access, and whether the compiler removes it depends on inlining.

### 2.3 Denormalization: Redundancy for Fewer Lookups

**Normalization** stores each fact once and joins by id, like a database. Checking an order against its risk limit:

```cpp
#include <cstdint>
#include <unordered_map>

struct RiskProfile { uint32_t max_order_size; double max_position_value; };
struct Client      { uint32_t client_id; uint32_t risk_profile_id; };
struct Order       { uint64_t order_id; uint32_t client_id; uint32_t quantity; double price; };

std::unordered_map<uint32_t, RiskProfile> risk_profiles;
std::unordered_map<uint32_t, Client>      clients;
std::unordered_map<uint64_t, Order>       orders;

bool check_risk_normalized(uint64_t order_id) {
    const auto& order  = orders.at(order_id);                      // possible miss #1
    const auto& client = clients.at(order.client_id);              // possible miss #2: needs #1's result
    const auto& risk   = risk_profiles.at(client.risk_profile_id); // possible miss #3: needs #2's result
    return order.quantity <= risk.max_order_size;
}
```

This costs more than "three misses", for two reasons:

- **The three lookups depend on each other.** The second key is only known once the first has read `order.client_id`, the third once the second has finished. Out-of-order execution only overlaps **independent** accesses; here every address depends on the previous load's data, so it waits, then does a step, then waits. The three latencies **add up** instead of overlapping. Reading an address and then reading what it points to is called **pointer chasing**.
- **Each `unordered_map::at` is more than one access.** libstdc++'s `unordered_map` is a bucket array plus a separately allocated node per element: read the bucket for the node pointer, then the node. "One miss per lookup" is an underestimate.

**Denormalization** copies the fields you'll need into the order:

```cpp
struct EnrichedOrder {
    uint64_t order_id;
    uint32_t quantity;
    double   price;
    uint32_t client_id;
    uint32_t max_order_size;        // copied from the risk profile
    double   max_position_value;    // copied from the risk profile
};                                  // 40 bytes instead of 24
std::unordered_map<uint64_t, EnrichedOrder> enriched_orders;

bool check_risk_denormalized(uint64_t order_id) {
    const auto& o = enriched_orders.at(order_id);   // the only lookup
    return o.quantity <= o.max_order_size;
}
```

One lookup, then only lines that just arrived. The price is that **the copies must be kept in sync**. When a risk parameter changes there are two paths:

- **Update every copy now**: one change rewrites many orders (write amplification), with a consistency problem halfway through.
- **Tolerate stale copies**: existing orders keep the parameter they were created with (snapshot semantics) and only new orders get the new value. No write amplification; old orders may carry old limits.

So the test isn't "how often does the parameter change" by itself but **whether the copies must be updated immediately**, and how many there are. Immediate sync with millions of orders per second moves the cost from reads to writes and doesn't fit; if the business accepts snapshot semantics, it usually pays off.

### 2.4 Field Order and `alignas(64)`

An order struct sorted from hottest field to coldest:

```cpp
struct alignas(64) OptimalOrder {
    uint64_t price;        // hottest
    uint32_t quantity;
    uint32_t orderId;
    uint64_t timestamp;    // less hot
    char symbol[8];        // coldest
};                         // 32 bytes of fields; sizeof is 64 because of alignas(64) on the type
static_assert(sizeof(OptimalOrder) == 64);
```

The fields total 32 bytes, but **`alignas(64)` on the type pads `sizeof` to 64** (section 1.3): the data ends at offset 32 and the next 32 bytes are tail padding. Choose by the effect you want:

- **Two per line, neither straddling: `alignas(32)`** (`sizeof` 32). Without any `alignas`, `alignof` is only 8 and straddling depends on the array's **base address**: at a multiple of 64 nothing straddles, at offset 16 (all `malloc` guarantees) every other element does. "32 bytes is exactly half a line" requires a 32-aligned base, which `alignas(32)` or the allocator must provide. Right for a single thread scanning or many threads only reading: two objects sharing a line is harmless and halves the lines.
- **One per line: `alignas(64)`.** Right when different threads write different orders (breaking false sharing). False sharing needs a **write**; many threads reading one line is fine. The price is half of every line being padding, so a sequential scan pulls twice the lines.

Now "order fields by access frequency". **If the struct fits in one line, field order inside it doesn't matter** — the whole line moves as a unit (lines, not words, are the transfer unit), so ordering a 32-byte struct changes nothing. Ordering matters for structs **larger than 64 bytes**: put the hottest fields in the **first line** and the cold ones after, so the hot path touches one line and the cold ones never come in.

That collides with section 1.2's "order by alignment to minimize padding": one saves bytes, the other groups hot fields. Priority: **first make the hot path touch one line, then sort by size within that constraint**; on the hot path, one fewer line beats eight fewer bytes. With many cold fields, go further and do **hot/cold splitting**: move cold fields into a separate struct and keep only hot ones in the hot struct.

### 2.5 Inline Character Arrays vs. Pointers

```cpp
struct First  { int nIndex; char Name[32]; };          // sizeof 36, alignof 4
struct Second { int nIndex; const char* Name; };       // sizeof 16, alignof 8
static_assert(sizeof(First) == 36 && sizeof(Second) == 16);
```

In cache lines:

- **Scanning only `nIndex`**: `Second` fits 4 per line. `First` is 36 bytes, which doesn't divide 64, so 8 of every 16 elements straddle a line — and 32 bytes per element you never read come along. `Second` is far more compact.
- **Reading the name**: `First` has it inline, no extra hop; `Second` follows a pointer elsewhere, one dependent load. If the strings are literals they sit together in read-only data and hit often; if each one is separately `new`ed and scattered across the heap, it's a miss.
- `const char*` doesn't own the string; someone else manages its lifetime, so it only suits constant data. (`std::string`'s small-string optimization keeps short strings inside the object — the same idea as `First`.)

### 2.6 Function Grouping: Code Goes Through Caches Too

**Code lives in memory and goes through caches too** — the instruction cache (L1I, typically 32 KiB) and the instruction TLB. Functions that call each other should sit close together, so the hot path's code occupies fewer pages and lines. Today compilers and linkers do this: GCC's `-freorder-functions` with `__attribute__((hot))` / `((cold))` places hot functions in `.text.hot` and cold ones in `.text.unlikely`; PGO (reordering by a real run's profile) and post-link optimizers like BOLT do the same. It pays off once **the hot path's code exceeds L1I**; a few kilobytes of hot code is already in the instruction cache.

---

## 3. Hardware Geometry: Where the Lines Live

Parts 1 and 2 asked how many lines an access touches. Part 3 goes one level down: **where those lines sit in the cache and where they live on the DIMMs.** Some address bits decide which cache set a line goes into and which channel and bank it lives on; if your access pattern keeps those bits equal, most of the hardware is idle and a small part thrashes. Numbers use a typical x86 core (Zen 3: L1D 32 KiB 8-way, L2 512 KiB 8-way) and DDR4.

### 3.1 Set Associativity: Address Bits Decide Where a Line May Go

#### 3.1.1 Where It Happens and What Problem It Solves

On the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a> this is the **inside** of the "L1D 32 KiB · 8-way" box; L2 and L3 have the same structure, only bigger. It happens at the first step of a load: the CPU takes an address to L1D and asks "do you have this line?" — set associativity is **how L1D answers that question**.

<a href="/images/memory-geometry/l1d-sets.en.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/l1d-sets.en.svg" alt="L1D as a cabinet of 64 rows by 8 slots: an address splits into tag, set index and offset; the set index picks one row, and 8 tags are compared in parallel" loading="lazy" decoding="async"></a>

**Prerequisite 1: the cache is a cabinet; each slot holds one whole line.** 32 KiB of L1D in 64-byte lines is 512 lines. Besides 64 bytes of data, each slot records a **tag** saying which line it holds — otherwise you couldn't tell what you'd found.

**Prerequisite 2: how an address splits.** An address is just a number. Take 10000: offset in line = 10000 mod 64 = 16 (the byte we want is the 16th of its line); line number = 10000 ÷ 64 = 156 (it belongs to line 156 of memory). 64 is 2⁶, so "÷ 64" drops the lowest 6 binary digits and "mod 64" keeps only them. 10000 is `10 011100 010000` in binary; the lowest 6 bits, `010000`, are 16 — the offset.

**The problem: given a line number, which slot do you look in?** Three options:

- Any line in any of 512 slots: every read compares 512 tags — not doable in a nanosecond.
- Each line number in exactly one fixed slot: two hot lines that happen to map to the same slot evict each other forever.
- The compromise, **set-associative**: arrange the 512 slots as **64 sets × 8 ways**. The line number picks the set (set = line number mod 64), and the line may go into any of that set's 8 ways. A lookup compares only those 8 tags, with 8 comparators at once.

These are the three "main memory to cache mappings" from a computer organization textbook, in different words:

| Textbook name | Cabinet layout | Problem |
|---|---|---|
| Direct-mapped | 512 sets × 1 way | two hot lines in one slot evict each other |
| Fully associative | 1 set × 512 ways | 512 tag compares per access, too slow |
| Set-associative | 64 sets × 8 ways | the compromise; the other two are its extreme cases |

The textbook's "block" is the cache line, "set = block number mod number of sets" is "set = line number mod 64", "tag" is the tag, and "thrashing" is the conflict miss below. Textbooks draw one cache; real machines give every level its own mapping, all splitting the same address. Full associativity isn't only theory either: small tables like the L1 TLB are often fully associative, because with few entries comparing all tags at once is feasible.

#### 3.1.2 A Lookup in Three Steps

Continue with 10000: set = 156 mod 64 = **28**, the next 6 bits `011100`; the remaining high bits `10` = 2 are the tag. An address splits into three fields: **tag (bit 12 and up) | set index (bits 6–11) | offset (bits 0–5)**.

1. Go straight to set 28 (computed, not searched);
2. compare that set's 8 tags with 2, all at once;
3. a match is a hit — read from byte 16 of that line; no match is a miss — fetch the whole line from L2 into one of set 28's slots, and if all 8 are full, evict the least recently used one.

#### 3.1.3 Where the Critical Stride Comes From

Take 10000 + 4096 = 14096, binary `11 011100 010000`: the set is still `011100` = 28; only the tag changed, to 3. Adding 4096 only changes bit 12 and up, so **addresses that differ by a multiple of 4096 land in the same set**. A set has 8 slots; the 9th such address evicts one **even if the other 63 sets are empty**. That's a **conflict miss**, a different thing from "the cache is full" (a capacity miss).

The distance is the **critical stride** = cache size ÷ ways = 32 KiB ÷ 8 = 4 KiB. Likewise L2 (512 KiB, 8-way): 8192 lines ÷ 8 = 1024 sets, critical stride 64 KiB. Many L3s hash the high bits before choosing set and slice, so the pattern there is less clean.

#### 3.1.4 Why L1's Critical Stride Equals the Page Size

To be fast, L1 starts selecting the set from the virtual address **while** the TLB is still translating it (VIPT: virtually indexed, physically tagged). That requires the set-index bits to be the same before and after translation, i.e. to sit inside the page offset. A 4 KiB page's offset is bits 0–11 — exactly 6 bits of line offset plus 6 bits of set index. So L1's sets × line size is capped at 4 KiB, and the only way to make it bigger is more ways: 32 KiB = 4 KiB × 8 ways. Apple's M1 uses 16 KiB pages and a 128 KiB L1D on its big cores = 16 KiB × 8 ways — the same constraint.

### 3.2 How Power-of-Two Strides Crowd the Cache

With the critical stride in hand, the opening question is easy. There's one rule: **when data used together sits at addresses that differ by multiples of the critical stride, all of it crowds into one set.** It usually shows up in two forms — inside one array (3.2.1, the matrix from the opening) and across several arrays (3.2.2). A similarly named but different mechanism, bank conflicts, is in 3.2.3.

#### 3.2.1 Example 1: Walking a Matrix by Column

Back to the opening loop. Each row of `int m[64][1024]` is exactly 4096 bytes, so walking a column adds 4096 to the address at every step.

**Why it's slow.** Walking a column, each step adds 4096 to the address, so all 64 elements **land in the same set**. Ideally column 0 pulls in 64 lines and columns 1–15 are in those same 64 lines (16 ints per line), so they should all hit — 64 lines are only 4 KiB and L1 has 32 KiB. But they all crowd into one 8-way set, only the last 8 survive, and the next column misses almost every time.

**Fixes:**

- **Pad by a whole cache line.** `int m[64][1040]` (1040 × 4 = 4160 = 4096 + 64). Row *i* starts 64 × *i* bytes past "4096 × *i*", so each row moves one set further and 64 rows fill 64 sets, one each. Padding by one `int` (`[64][1025]`, 4100 bytes per row) also spreads them, but each row moves only 4 bytes: 16 consecutive rows still share a set, 64 rows crowd into 4 sets of 16 — still more than 8 ways — and rows no longer start on a line.
- **Tile.** Process a small block at a time (say 8 rows × 16 columns) and use all 16 ints of each line before it's evicted. Standard for matrix multiply and transpose.
- **Change the traversal order.** Walk by row whenever you can.

**Measured on an M1.** First the prediction from the M1's parameters: big-core L1D 128 KiB, 16 KiB pages, 128-byte lines (read with `sysctl`); assuming 8 ways (published spec), **critical stride = 128 KiB ÷ 8 = 16 KiB**, not x86's 4 KiB. So the slowest point should be a 16 KiB row stride, with no further slowdown beyond it. The test walks 64 rows and the first 1024 columns, same number of accesses for every stride, changing only the distance between adjacent rows; the control pads each row by 128 bytes. (Apple M1 MacBook Air, Apple clang 21, `-O2`, QoS user-interactive, not pinned; best of 7 per cell, two runs within ±0.05 ns.)

| Row stride (distance between rows) | Column walk ns/access | Same + 128 B padding | Row walk ns/access |
|---|---|---|---|
| 1 KiB | 0.25 | 0.18 | 0.05 |
| 2 KiB | 0.27 | 0.18 | 0.05 |
| 4 KiB | 0.40 | 0.19 | 0.05 |
| 8 KiB | 0.62 | 0.21 | 0.07 |
| **16 KiB** (M1 critical stride) | **0.81** | 0.20 | 0.06 |
| 32 KiB | 0.78 | 0.20 | 0.06 |

Reading it:

- **The padded column is flat (about 0.2 ns)**: sets are spread out, the 64 lines go to different sets and stay in L1.
- **The unpadded column slows as the stride grows and caps at 16 KiB**: at 4 KiB the 64 rows fall into 4 sets, which hold at most 4 × 8 = 32 lines, not 64; at 8 KiB, 2 sets and 16 lines; from 16 KiB on, a single set of 8. 32 KiB is no slower than 16 KiB, so 16 KiB is already "one set" — matching the predicted critical stride.
- The row walk stays around 0.05 ns: all 32 ints of a line are used in a row, prefetched and vectorized.

**Why only 4× slower?** The measurement is solid (about 13 million accesses per timing); the numbers are small because they're **throughput** (total time ÷ accesses), not the **latency** of one miss:

- An L2 hit on the M1 is about 5 ns. Each address in this loop is computed, not taken from the previous load, so the CPU keeps several misses in flight; 5 ÷ 0.81 ≈ 6, roughly six or seven overlapping.
- The largest matrix is 2 MiB, inside the M1's 12 MiB L2, so lines evicted from L1 only fall to L2, never to DRAM.

The gap gets much bigger when **loads depend on each other** — the next address waits for the previous load, as in a linked list or the pointer chasing of section 2.3 — so misses can't overlap and each pays full latency; and if conflicts also overflow L2, the fall is to DRAM (about 100 ns). Independent loads: set conflicts cost a few times the throughput. Dependent loads: set conflicts expose the full latency. Hot-path lookups in HFT are mostly the second kind.

#### 3.2.2 Example 2: Several Page-Aligned Arrays Read Together

```cpp
float* a[10];                          // ten large, separately allocated arrays
for (size_t i = 0; i < n; ++i)
    out[i] = a[0][i] + a[1][i] + a[2][i] + a[3][i] + a[4][i]
           + a[5][i] + a[6][i] + a[7][i] + a[8][i] + a[9][i];
```

**Why it's slow.** Large allocations usually start page-aligned, or at least with identical low 12 bits: glibc's `malloc`, for example, serves big requests (128 KiB and up by default) straight from the kernel and returns "page start + a fixed 16-byte header". So:

- `a[k][i]` is at start<sub>k</sub> + 4*i*, and all start<sub>k</sub> share their low 12 bits;
- so for any *i*, the ten elements have **identical** bits 6–11 — ten lines in one set;
- the set has 8 slots and the ten lines take turns; the 9th and 10th evict the least recently used line, which is exactly the one needed next. With a loop cycling through more lines than there are slots, LRU replacement makes **every access a miss**.

Advancing *i* doesn't help: *i* + 1 moves 4 bytes within the same line, all ten arrays move together and stay in the same set.

**Fix.** Offset array *k*'s start by *k* cache lines, so every array has a different set:

```cpp
#include <cstdlib>

constexpr int kArrays = 10;
constexpr size_t kLine = 64;
void*  raw[kArrays];
float* arr[kArrays];

void allocate(size_t bytes) {
    for (int k = 0; k < kArrays; ++k) {
        raw[k] = std::aligned_alloc(4096, bytes + 4096);                            // one spare page for the offset
        arr[k] = reinterpret_cast<float*>(static_cast<char*>(raw[k]) + k * kLine);  // shift array k by k lines
    }
}
void release() { for (int k = 0; k < kArrays; ++k) std::free(raw[k]); }             // free the original pointers
```

Compiled and run on the M1: the ten start addresses modulo 4096 were 0, 64, 128 … 576 — sets 0 through 9, one each.

#### 3.2.3 Aside: L1 Bank Conflicts (a Different Mechanism)

L1 is internally split into **banks** that can be accessed in parallel; two loads issued in the same cycle to the same bank have to queue. That's not a set conflict: a set conflict is "too few slots, lines evict each other"; a bank conflict is "two accesses want the same port in the same cycle". It's highly microarchitecture-specific — prominent on older Intel cores like Sandy Bridge, mostly gone on newer ones; look it up in the optimization manual for the specific core when it matters.

### 3.3 Where a Variable Lives Decides Who Shares Its Lines

Storage classes, seen through the cache:

- **Stack**: repeated calls reuse the same addresses, which stay hot in L1. Locals have good locality for free.
- **Registers**: the compiler keeps frequently used locals in registers and never touches memory. Help it by not taking a local's address and passing it around (once the address escapes, it can't live only in a register).
- **Global / static**: not slow in itself — a hot global sits in L1 like anything else. The question is **who its neighbours are**: the linker places them by its own rules, and two globals written by different threads can share a line — false sharing — so separate them with `alignas(64)`.
- **`volatile`**: only forces the compiler to actually load and store every time, without merging or eliding. It is **not** a synchronization tool — no atomicity, no ordering; use `std::atomic` between threads. It's for memory-mapped device registers, signal handlers and the like.
- **`thread_local`**: one copy per thread, no false sharing by construction. Defined and used in the executable, on x86-64 Linux it's one load relative to the `fs` segment register; defined in a shared library and accessed through the general-dynamic model it may call `__tls_get_addr`. Copy it into a local if the hot path uses it repeatedly.
- **Heap**: allocation and deallocation are expensive and take unpredictable time, and separately allocated objects scatter, so locality depends on the allocator. HFT preallocates at startup and uses memory pools ([#3](/posts/hot-path-memory-allocators/)).

### 3.4 Inside a DIMM: Channels, Ranks, Banks, Rows

If a cache is a cabinet, a DIMM is cabinets inside cabinets: the memory controller splits the physical address into fields that pick the channel, bank and row. Here is the picture up front; the subsections take it apart layer by layer, and by the end it's clear that the most expensive case is **switching rows within one bank**.

<a href="/images/memory-geometry/dram-geometry.en.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/dram-geometry.en.svg" alt="Inside the DIMMs: the memory controller drives two channels; a rank is eight chips side by side; each chip has 16 banks; a bank is a table of rows with one row buffer, and a read costs about 14 ns on a row hit, 28 ns on an empty bank and 41 ns on a row conflict" loading="lazy" decoding="async"></a>

#### 3.4.1 Where This Is

On the <a href="/maps/hardware-map.en.html" target="_blank" rel="noopener">hardware map</a>, it's the "memory controller" and "DIMMs" boxes below L3. When a load misses L1, L2 and L3, the request goes to the **memory controller** — on the CPU die, not on the DIMM — which fetches the whole 64-byte line over the motherboard traces. This section is about that last stretch: how the DIMM finds those 64 bytes.

#### 3.4.2 The Smallest Unit: a Bank and Its Row Buffer

A DRAM cell is just **a tiny capacitor and a switch**: charged is 1, discharged is 0. The charge is too small to read a single cell on its own, so DRAM reads like this:

1. A **bank** is a big table: tens of thousands of rows, about 1 KiB per row (per chip).
2. To read any byte, first **open its whole row**: connect every cell in the row to a row of sense amplifiers that amplify and latch the values. That row of amplifiers is the **row buffer**.
3. Then take the wanted bytes out of the row buffer by column number.

Each bank has **one row buffer**, so one row can be open at a time. Reading another row of the same bank means **closing** the current one first (writing it back to the capacitors and resetting the amplifiers — a precharge), then opening the new one. Think of a desk: from the bookshelf (bank) you can only bring a whole shelf (open a row) to the desk, and the desk holds one shelf; for a book on another shelf, put this shelf back first (close the row).

#### 3.4.3 Three Cases for One Read

Opening a row, reading a column and closing a row each take about 22 clocks × 0.625 ns ≈ **14 ns** on DDR4-3200 CL22. How many steps a read needs depends on what's in the row buffer:

- **Row hit**: the row is already open → read only, about **14 ns**.
- **Row empty**: no row open in this bank → open + read, about **28 ns**.
- **Row conflict**: **another row of the same bank** is open → close + open + read, about **41 ns**.

That's only the time inside the DIMM. Add queuing in the controller, the on-chip interconnect and the L1/L2/L3 misses on the way down, and a full DRAM access is typically **80–100 ns**.

#### 3.4.4 Going Up: Chip → Rank → Channel

- **Chips and ranks**: a channel's data bus is **64 bits** (8 bytes) wide, and a common chip supplies 8 bits at a time. So 8 chips side by side, each supplying 8 bits in the same beat, make 64 — **this group of chips responding together is a rank**. A 64-byte line is 8 beats × 8 bytes, 8 bytes from each chip, and all 8 chips open the same row and column.
- **Banks**: each chip has 16 banks (DDR4). Different banks open rows and prepare data independently: while bank 0 spends its 14 ns opening a row, bank 1 can be transferring. That's how a DIMM serves several requests at once.
- **A DIMM can carry 1–2 ranks** (often one per side). Ranks on the same channel share its 64 data wires; only one transfers at a time, taking turns. So **channels and ranks are not one-to-one**: a channel can hold 1–2 DIMMs of 1–2 ranks each, i.e. 1–4 ranks per channel (channel 0 in the figure has 2).
- **Channels**: each channel is an independent set of 64 data wires plus command lines, and channels transfer in parallel. So **total bandwidth ≈ channels × per-channel bandwidth** — 2 channels on a desktop, 6–12 on a server. More channels don't make a single access faster; they let more requests run at once.

#### 3.4.5 How the Controller Splits an Address

Exactly like L1 using bits 6–11 to pick a set (3.1): the memory controller splits the physical address into fields that pick **the channel, rank, bank, row and column**. **Low bits go to the column**, so consecutive addresses share a DRAM row and sequential access keeps hitting the open row; channel and bank bits usually sit in between and are hashed, spreading large contiguous blocks across channels and banks. The exact bit assignment varies by platform and is rarely documented.

#### 3.4.6 Example: a Column Walk Loses at Five Layers

```cpp
int matrix[31250][2048];     // each row 2048 ints = 8 KiB, 256 MB in total
long long sum = 0;
// row walk: consecutive addresses, fast
for (int i = 0; i < 31250; ++i)
    for (int j = 0; j < 2048; ++j)
        sum += matrix[i][j];
// column walk: each step jumps 8 KiB, slow
for (int j = 0; j < 2048; ++j)
    for (int i = 0; i < 31250; ++i)
        sum += matrix[i][j];
```

`matrix[i][j]` is at base + *i* × 8192 + *j* × 4. A row walk adds 4 per step; a column walk adds **8192**. From the top down, every layer loses:

1. **Each cache line is 1/16 used.** Every step lands on a new 64-byte line and uses 4 bytes of it. The other 15 ints in that line belong to columns *j*+1 … *j*+15, which are only needed after a whole column (31,250 steps).
2. **By then those lines are long gone.** A column touches 31,250 lines, about 2 MB — more than L1 or L2 to begin with; and since 8 KiB is a multiple of 4 KiB, the whole column crowds into **one set** in L1 (3.1.3) and only 8 sets × 8 ways = 64 lines in L2 (critical stride 64 KiB).
3. **Every step is a new page.** An 8 KiB stride exceeds the 4 KiB page, so a column touches 31,250 pages against a TLB of a couple of thousand entries — a page walk almost every time.
4. **The prefetcher can't help.** Hardware prefetchers generally predict within one 4 KiB page and don't cross pages; with a new page every step, they never get a chance.
5. **And at DRAM, row conflicts.** The first four layers send almost every access to the DIMM. Neighbouring accesses 8 KiB apart often land in different rows of the same bank: close + open + read every time, about 41 ns instead of a row hit's 14.

A row walk reverses all of it: 8 KiB of consecutive data mostly sits in one DRAM row, so one open row serves many cache lines; all 16 ints of each line are used; the prefetcher sees the pattern and runs ahead; the TLB changes page once per 1024 ints. **A column walk is slow because five layers stack, and the row buffer is only the bottom one.** The fixes are those of 3.2.1: change the traversal order (or transpose first), or tile.

### 3.5 DRAM Refresh: a Spike Software Can't Remove

DRAM stores data in capacitors that leak, so the controller must periodically read every row and write it back — **refresh**. The standard is all rows within 64 ms, split into 8192 batches, so a refresh command goes out about every **7.8 µs** (tREFI); during each, the rank being refreshed is inaccessible for a few hundred ns (tRFC, about 350 ns for an 8 Gb DDR4 chip).

Estimate: 350 ÷ 7800 ≈ **4.5%**. A random DRAM access has about a 4.5% chance of hitting a refresh and waiting up to several hundred ns longer (assuming all-bank refresh). Invisible in the mean, it shows up in **P99 / P99.9** tail latency. Software can't turn it off, only work around it:

- **Keep the hot data set in cache**, so the hot path never goes to DRAM — by far the most effective.
- Use memory with fine-granularity refresh (FGR) or per-bank refresh, which shortens each stall.
- When measuring latency, look at P99 / P99.9, and when spikes recur about every 7.8 µs, think refresh.

### 3.6 Balancing Multiple Channels

Channels add bandwidth only when they're **busy at the same time**. The controller distributes consecutive addresses across them at some granularity — **channel interleaving**. The simplest model shows the problem: granularity 64 bytes, `channel = (address ÷ 64) mod N`.

Four channels, an array of 256-byte objects (4 lines each), and a hot path that reads only each object's **first line**:

- Object *i*'s first line is line 4*i*, channel 4*i* mod 4 = **0**. Every hot line is on channel 0; the other three sit idle.
- If the object's size in lines is **coprime** with the channel count, hot lines rotate across channels. Pad the object to 5 lines (320 bytes): object *i*'s hot line is line 5*i*, and 5*i* mod 4 cycles 0, 1, 2, 3, 0 … — all four channels in turn.

The rule: **round the object up to L lines, then adjust L so it's coprime with the channel count N** — for N = 2 or 4, an odd number of lines. Three channels balance naturally, because any power-of-two line count is coprime with 3.

Two realities:

- **Real controllers rarely just take a modulus.** Most XOR-hash high address bits before choosing channel and bank, precisely to break such patterns, and the interleave granularity varies by platform. Before padding by hand, find out the platform's mapping, then measure.
- Only **bandwidth-bound** work (scanning many objects, hot lines spread over a large working set) needs this. A hot set that lives in cache never reaches a channel.

