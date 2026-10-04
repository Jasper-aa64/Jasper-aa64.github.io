---
title: "Trading System Notes #6: Alignment, Layout, and Cache and DRAM Geometry"
date: 2026-10-04
slug: "alignment-layout-cache-dram-geometry"
description: "Why every memory decision on a hot path comes down to which cache lines an access touches and where those lines live: alignment and padding, alignas on types versus variables, over-aligned heap memory and a two-tier allocator, AoS versus SoA, denormalization against dependency chains, then down into the hardware — L1 sets and the critical stride, power-of-two strides measured on an M1, DRAM row buffers, refresh, and channel balance."
summary: "An access never pays for bytes; it pays for cache lines, and the address decides which lines, which cache set they compete for, and which DRAM channel and bank they live on. Alignment keeps a value inside one line; padding keeps arrays aligned; alignas trades space for isolation and #pragma pack gives it up to match an external format. Layout decides how many lines an access touches — AoS or SoA, denormalized or chased through three lookups. Below that, the address bits pick an L1 set (so data 4 KiB apart competes for 8 slots no matter how empty the cache is), a DRAM row buffer (14 ns hit, 41 ns conflict), and a channel (only coprime strides spread the load). A column walk is slow for five stacked reasons, and the row buffer is only the last."
categories: [Systems]
tags: [cpp, alignment, cache, memory-layout, false-sharing, dram, numa, hft, low-latency]
toc: true
homepage: false
---

# Trading System Notes #6: Addresses Decide Neighbors — Alignment, Layout, and the Geometry of Caches and DRAM

> **One-line thesis**: memory is never paid for by the byte. Every access pays for whole cache lines, and the address decides which lines it touches, which cache set those lines compete for, and which DRAM channel, bank and row they live in. Alignment and layout control the first; the address bits you never think about control the rest.

## What You're Actually Fighting

The map below is where everything in this series happens. A load first gets its address translated by the TLB, looks in L1D, then L2, then the shared L3, and finally goes through the memory controller to a DIMM. Data always moves as whole 64-byte lines.

<a href="/images/memory-geometry/hardware-map.en.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/hardware-map.en.svg" alt="Hardware map from the pipeline and store buffer through L1, L2, L3, the memory controller and DIMMs, with a latency table and the fields of one address" loading="lazy" decoding="async"></a>

This post works through it from the top. The first half is about what you control directly — where a value starts, how a struct is padded, how records are laid out — measured in the number of lines an access touches. The second half goes inside the boxes: how L1 decides where a line may live, why some strides make an almost empty cache thrash, and what a DRAM access actually does once it leaves the chip.

---

## 1. Alignment Keeps a Value Inside One Line

A value is **aligned to N** when its address is a multiple of N; `alignof(T)` is the N a type requires. On x86-64 the fundamental types are aligned to their own size: `int` to 4, `double` and pointers to 8.

The reason the CPU cares is the cache line. Lines start at multiples of 64, and **64 is a multiple of 8**, so a `double` aligned to 8 can only start at offset 0, 8, … 56 inside a line, and the last one fills it exactly. It can never straddle two lines. A `double` at offset 60 would have four bytes in one line and four in the next.

Straddling has two consequences of very different weight:

- **Slower.** The load becomes two cache accesses (a *line split*), plus a second translation if the lines are in different pages. x86 doesn't fault, it quietly slows down — which is why misalignment is hard to notice on x86.
- **Much worse for atomics.** A `lock`-prefixed read-modify-write is indivisible because the core holds its line exclusively until it finishes ([MESI cache coherence](/posts/low-latency-mesi-cache-coherence/)). Across two lines that's impossible, so the CPU falls back to locking the bus — a **split lock**, far more expensive and harmful to other cores; Linux has been able to detect and report it since 5.7.

"Aligned to its size never straddles" only holds for sizes that are powers of two up to 64. A 12-byte struct with `alignof` 4 can start at offsets 56 or 60 and straddle — 2 of its 16 possible starting offsets (enumerated). Raise it to `alignas(16)`, which also pads it to 16 bytes, and none of the 4 starting offsets straddles.

---

## 2. Padding Exists for Arrays

The compiler lays out a struct with three rules:

1. members go in declaration order, each at the first offset that is a multiple of its own alignment, with **padding** bytes in the gaps;
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

Rule 3 exists because of arrays: element *i* of `T arr[N]` sits at `base + i × sizeof(T)`. If `sizeof` weren't a multiple of `alignof`, element 0 would be aligned and element 1 wouldn't.

Member order changes the size:

```cpp
struct Bad  { char a; double b; char c; int d; };   // 0, 8, 16, 20 → sizeof 24 (11 bytes padding)
struct Good { double b; int d; char a; char c; };   // 0, 8, 12, 13 → sizeof 16
static_assert(sizeof(Bad) == 24 && sizeof(Good) == 16);
```

Ordering members from largest to smallest alignment minimizes padding. In an array the difference is real: a 64-byte line holds 2.7 of the first and exactly 4 of the second, so a scan touches a third fewer lines. Saving bytes is only half the story, though — hot fields belong together too (section 7), and when the two goals collide, touching fewer lines wins.

---

## 3. `alignas` on a Type vs. on a Variable

`alignas(N)` asks for more alignment than the default, and *where* you write it matters:

```cpp
struct alignas(32) AlignasType { int data[5]; };    // 20 bytes of data
static_assert(sizeof(AlignasType) == 32 && alignof(AlignasType) == 32);

alignas(64) char buffer[100];                       // this variable starts on a line
static_assert(sizeof(buffer) == 100 && alignof(decltype(buffer)) == 1);
```

- **On a type**, every object starts at a multiple of 32, and rule 3 pads `sizeof` up to 32.
- **On a variable**, only that variable's address changes; its type, and its `sizeof`, stay the same.

The common choice is 64: the object starts on a line, and if its size is a whole number of lines it **owns** those lines, so a neighbour's writes never contend with it — the fix for false sharing ([#2](/posts/memory-ordering-false-sharing-dependency-chains/)) and the hardware form of MESI's one-writer rule. On a type, `alignas(64)` makes the size a multiple of 64 automatically (`struct alignas(64) { char x[100]; }` is 128). On a member, it only moves the start:

```cpp
struct Two   { alignas(64) char a[100]; char b; };              // b at offset 100, sharing a's last line
struct Three { alignas(64) char a[100]; alignas(64) char b; };  // b at offset 128, a line of its own
static_assert(offsetof(Two, b) == 100 && offsetof(Three, b) == 128);
```

`std::hardware_destructive_interference_size` (C++17, `<new>`) is the portable spelling of "line size" where the library provides it. The price is explicit: `alignas(64)` turns a 4-byte counter into 64 bytes. You're buying isolation with space.

---

## 4. Over-Aligned Heap Memory

`malloc` and plain `new` only guarantee the alignment of the largest fundamental type — 16 on x86-64. Anything more needs a different interface.

**`std::aligned_alloc(alignment, size)`** requires `size` to be a multiple of `alignment`; otherwise it fails and returns null. Round up first: 300 bytes at 64-byte alignment means asking for 320.

```cpp
#include <cstdlib>

void* make_buffer() {
    const size_t alignment = 64, requested = 300;
    size_t size = (requested + alignment - 1) / alignment * alignment;   // 320
    return std::aligned_alloc(alignment, size);                          // free with std::free
}
```

**Over-aligned `new`** (C++17) kicks in automatically when a *type* is over-aligned, and `delete` picks the matching function. The trap is passing the alignment only at the call site:

```cpp
struct Plain { float v[4]; };                              // the type itself only needs 4
auto* p = new (std::align_val_t{128}) Plain();             // aligned allocation...
delete p;                                                  // ...ordinary deallocation: mismatched, UB
```

`delete` looks at the type, sees nothing special and calls the plain `operator delete`. Allocation and deallocation don't match; on MinGW this crashed with heap corruption (`0xC0000374`). Either put the alignment on the type, or pair both sides by hand: `p->~Plain(); ::operator delete(p, std::align_val_t{128});`.

**A two-tier allocator.** A production STL allocator built on these does:

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

- Small requests start on a line and occupy whole lines, so two allocations never share one.
- Large ones are aligned to **2 MiB, the x86-64 huge page size**: transparent huge pages can only back a 2 MiB-aligned, 2 MiB-long range with one huge page.
- **`madvise` comes before `memset`** because pages are allocated on first touch, and that is when the kernel checks for the "huge page wanted" hint. Zero first and you get 4 KiB pages, left for the background `khugepaged` to merge later — an unpredictable stall. The `memset` also pays every first-touch page fault up front (about 1.5 µs per page measured in [#5](/posts/spmc-shared-memory-broadcast-ring/)) instead of on the hot path.
- The rounding mask `(n + a - 1) & ~(a - 1)` only works because `a` is a power of two; with `a = 48` it disagrees with division for 66,672 of the values 0..100,000.

Two costs to name. Anything over 16 KiB is rounded to 2 MiB, so a 20 KiB container occupies and zeroes 2 MiB — fine for a few big arrays, wasteful for many medium ones. And THP plus `madvise` depends on the system setting; HFT deployments more often reserve explicit huge pages (`MAP_HUGETLB`) and disable THP, because explicit is more predictable.

---

## 5. `#pragma pack` Describes the Outside World

```cpp
#pragma pack(push, 1)
struct PackedStruct { char a; int b; double c; };   // offsets 0, 1, 5; sizeof 13, alignof 1
#pragma pack(pop)
static_assert(sizeof(PackedStruct) == 13);
```

Packing undoes section 1: `b` and `c` sit at unaligned addresses, an array's elements drift across line boundaries, a pointer to `c` is an unaligned `double*` that's undefined behaviour to dereference, and atomics on such a field can split-lock. The compiler doesn't warn when you take those addresses. Use it to match an external byte layout — a wire protocol, a file format — not to save memory, and copy fields into aligned locals with `memcpy` before working with them (a fixed-size `memcpy` compiles to a plain load).

---

## 6. Count Lines, Not Bytes: AoS vs. SoA

Every layout question below is the same question: **how many cache lines does this access touch?**

```cpp
struct Point1 { float x, y, z; };
Point1 points1[1000];                                  // array of structures (AoS)

struct Point2 { float x[1000], y[1000], z[1000]; };
Point2 points2;                                        // structure of arrays (SoA)
```

Summing only the x coordinates: AoS drags y and z along in every line — 12,000 bytes, **188 lines**. SoA reads a contiguous 4,000-byte array — **63 lines**. The factor of three is "useful bytes are a third of each line". Reverse the access (x, y and z of the same point together) and AoS wins: one line versus three arrays 4,000 bytes apart. **Use all fields of an element together → AoS; scan a few fields across all elements → SoA.**

Two caveats. A 12-byte element isn't a power of two, so in AoS 2 of every 16 elements straddle a line (section 1); the SoA `float` arrays never do. And this example is 12 KB — it fits in L1, so after the first pass the line count stops mattering. The gap shows up when the working set is far larger than the cache, or with vectorization, where SoA's contiguous floats fill a SIMD register in one load.

You can keep AoS-style code over SoA storage with a **proxy view**: `operator[]` returns a small object holding a pointer to the storage and an index, whose accessors forward to the arrays.

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

Callers get readable AoS syntax; the performance-critical loop goes straight to the contiguous arrays, which is where SoA's cache and SIMD benefits actually come from.

---

## 7. Denormalize to Break a Dependency Chain

The normalized way to check an order's risk limit:

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
    const auto& order  = orders.at(order_id);                      // miss #1
    const auto& client = clients.at(order.client_id);              // miss #2: needs #1's result
    const auto& risk   = risk_profiles.at(client.risk_profile_id); // miss #3: needs #2's result
    return order.quantity <= risk.max_order_size;
}
```

It's worse than "three misses". Each lookup's key comes from the previous lookup's data, so out-of-order execution can't overlap them: **the latencies add**. That's *pointer chasing*. And each `unordered_map::at` is itself a bucket read followed by a node read.

Denormalizing copies what the check needs into the order:

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
    const auto& o = enriched_orders.at(order_id);   // one lookup
    return o.quantity <= o.max_order_size;
}
```

The bill arrives on writes. When a risk parameter changes, either every copy is updated at once — write amplification, and a consistency problem halfway through — or existing orders keep the value they were created with (snapshot semantics). So the deciding question isn't "how often does the parameter change" but **"must the copies be updated immediately?"** If yes and orders are many, denormalization moves the cost from reads to writes. If snapshot semantics are acceptable, it's usually worth it.

---

## 8. `alignas(64)` Is Isolation, `alignas(32)` Is Packing

```cpp
struct alignas(64) OptimalOrder {
    uint64_t price;        // hottest
    uint32_t quantity;
    uint32_t orderId;
    uint64_t timestamp;    // less hot
    char symbol[8];        // coldest
};                         // 32 bytes of fields; sizeof is 64 because of alignas(64)
static_assert(sizeof(OptimalOrder) == 64);
```

Thirty-two bytes of data, but `alignas(64)` on the type pads `sizeof` to 64. Pick by what you want:

- **Two per line, neither straddling: `alignas(32)`.** Without any `alignas`, `alignof` is only 8 and the result depends on the array's base address — at a 16-byte offset (all `malloc` promises), every other element straddles. Good for single-threaded scans and read-only sharing.
- **One per line: `alignas(64)`.** Right when different threads *write* different orders; false sharing needs a write, so read-only sharing is harmless. The cost is half of every line being padding.

"Order fields by access frequency" only matters for structs **larger than a line**: the whole line moves at once, so ordering inside a 32-byte struct changes nothing. In a bigger struct, put the hot fields in the first line; if there are many cold fields, split them into a separate struct entirely (hot/cold splitting).

The same arithmetic applies to strings. A record with an inline `char Name[32]` is 36 bytes — 8 of every 16 straddle a line, and a scan of the index drags the name along. A `const char*` version is 16 bytes and scans compactly, but reading the name is one dependent load somewhere else. And code is data too: functions that call each other should sit together in the instruction cache, which compilers and linkers handle via hot/cold sections, PGO and BOLT once the hot path outgrows L1I.

---

## 9. Inside L1D: 64 Sets × 8 Ways

Now the boxes themselves. L1D doesn't let any line go anywhere.

<a href="/images/memory-geometry/l1d-sets.en.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/l1d-sets.en.svg" alt="L1D as a cabinet of 64 rows by 8 slots: an address splits into tag, set index and offset; the set index picks one row, and 8 tags are compared in parallel" loading="lazy" decoding="async"></a>

A 32 KiB L1D with 64-byte lines holds 512 lines. Letting a line go anywhere (fully associative) would mean comparing 512 tags on every access — impossible in a nanosecond. Giving each line exactly one slot (direct-mapped) means two hot lines that map to the same slot evict each other forever. The compromise is **set-associative**: 512 slots arranged as **64 sets × 8 ways**. An address splits into three fields:

- **offset**, bits 0–5: which byte in the 64-byte line;
- **set index**, bits 6–11: which of the 64 sets — computed, not searched;
- **tag**, bit 12 and up: compared against all 8 ways of that set at once.

Take address 10000 = `10 011100 010000` in binary: offset 16, set 28, tag 2. Add 4096: `11 011100 010000` — **same set 28**, tag 3. So addresses that differ by a multiple of 4096 always compete for the same 8 slots, and the 9th one evicts somebody **even if the other 63 sets are empty**. That distance is the **critical stride**: cache size ÷ ways = 32 KiB ÷ 8 = 4 KiB. A miss caused this way is a *conflict miss*, distinct from a capacity miss. The same arithmetic gives L2 (512 KiB, 8-way) 1024 sets and a 64 KiB critical stride; L3s usually hash the high bits to pick a set and slice, so their pattern is less clean.

Why exactly 4 KiB? L1 starts selecting the set *while* the TLB is still translating the address (virtually indexed, physically tagged — VIPT). That only works if the set-index bits are the same before and after translation, i.e. inside the page offset. A 4 KiB page has 12 offset bits: 6 for the byte, 6 for the set. So sets × line size is capped at 4 KiB, and the only way to grow L1 is more ways: 32 KiB = 4 KiB × 8. Apple's M1 uses 16 KiB pages and a 128 KiB L1D — 16 KiB × 8, the same constraint.

---

## 10. Power-of-Two Strides Crowd One Set

The pattern to recognise: **data used together whose addresses differ by multiples of the critical stride all lands in one set.** It shows up in two common forms.

### 10.1 Walking a Matrix by Column

```cpp
int m[64][1024];             // each row is exactly 4096 bytes
long long sum = 0;
for (int j = 0; j < 1024; ++j)
    for (int i = 0; i < 64; ++i)
        sum += m[i][j];      // each step: +4096 bytes
```

Column 0 brings in 64 lines — only 4 KiB, while L1 has 32 KiB — and each line also holds columns 1–15, so the next fifteen columns should all hit. But all 64 lines are in **one set** with 8 ways, so only the last 8 survive and almost every access misses.

Fixes: **pad by a whole line** — `int m[64][1040]` (4160 bytes per row) shifts each row one set further, and 64 rows fill 64 sets exactly; padding by a single `int` (`[64][1025]`) shifts each row only 4 bytes, so 16 consecutive rows still share a set, 16 per set exceeds 8 ways, and rows no longer start on a line. Or **tile**: process an 8 × 16 block at a time and use each line's 16 ints before it's evicted. Or simply walk by row.

Measured on an Apple M1 MacBook Air (Apple clang 21, `-O2`, best of 7, high QoS, not pinned). The M1's numbers differ from x86 — 128 KiB L1D, 128-byte lines, and a **critical stride of 16 KiB** (8 ways assumed from the published spec) — so the test sweeps the row stride, padding by one 128-byte line as the control:

| Row stride | Column walk ns/access | Same + 128 B padding | Row walk |
|---|---|---|---|
| 1 KiB | 0.25 | 0.18 | 0.05 |
| 2 KiB | 0.27 | 0.18 | 0.05 |
| 4 KiB | 0.40 | 0.19 | 0.05 |
| 8 KiB | 0.62 | 0.21 | 0.07 |
| **16 KiB** (M1 critical stride) | **0.81** | 0.20 | 0.06 |
| 32 KiB | 0.78 | 0.20 | 0.06 |

The padded column is flat: sets are spread, the lines stay in L1. Unpadded, it slows as the stride grows and **caps at 16 KiB** — at 4 KiB the 64 rows share 4 sets (32 slots), at 8 KiB 2 sets, from 16 KiB on a single set with 8 slots — exactly where the critical stride says it should, and 32 KiB is no worse because it's already "one set".

**Why only 4× and not 20×?** These numbers are *throughput* (total time ÷ accesses), not latency. Each address is computed, not loaded, so many misses are in flight at once; with an L2 hit around 5 ns, 0.81 ns per access means roughly six overlapping. And the largest matrix is 2 MiB, inside the M1's 12 MiB L2, so evicted lines only fall to L2. With *dependent* loads — the next address comes from the last load, as in a hash chain or an order-book tree — misses can't overlap and set conflicts expose the full latency. Hot-path lookups in HFT are usually the dependent kind.

### 10.2 Several Page-Aligned Arrays Read Together

```cpp
float* a[10];                          // ten large, separately allocated arrays
for (size_t i = 0; i < n; ++i)
    out[i] = a[0][i] + a[1][i] + a[2][i] + a[3][i] + a[4][i]
           + a[5][i] + a[6][i] + a[7][i] + a[8][i] + a[9][i];
```

Large allocations tend to start at the same offset within a page (glibc serves big requests straight from the kernel as page start plus a fixed header). Then the ten elements at index *i* share bits 6–11 — ten lines competing for 8 ways. And because the loop cycles through more lines than there are ways, least-recently-used replacement evicts exactly the line needed next: every access misses. Advancing *i* doesn't help; all ten arrays move together.

The fix is to offset array *k* by *k* lines:

```cpp
#include <cstdlib>

constexpr int kArrays = 10;
constexpr size_t kLine = 64;
void*  raw[kArrays];
float* arr[kArrays];

void allocate(size_t bytes) {
    for (int k = 0; k < kArrays; ++k) {
        raw[k] = std::aligned_alloc(4096, bytes + 4096);                            // one spare page
        arr[k] = reinterpret_cast<float*>(static_cast<char*>(raw[k]) + k * kLine);  // shift by k lines
    }
}
void release() { for (int k = 0; k < kArrays; ++k) std::free(raw[k]); }             // free the originals
```

Compiled and run on the M1: the ten start addresses modulo 4096 were 0, 64, … 576 — sets 0 through 9, one each.

A related effect with a similar name, **L1 bank conflicts** — two loads in the same cycle hitting the same internal bank — is a port contention, not a capacity problem, and is highly microarchitecture-specific (older Intel cores like Sandy Bridge showed it; most newer ones don't).

---

## 11. Inside a DIMM: Channels, Ranks, Banks, Row Buffers

After an L3 miss, the request goes to the memory controller on the CPU die, and from there to a DIMM.

<a href="/images/memory-geometry/dram-geometry.en.svg" target="_blank" rel="noopener"><img src="/images/memory-geometry/dram-geometry.en.svg" alt="Inside the DIMMs: the memory controller drives two channels; a rank is eight chips side by side; each chip has 16 banks; a bank is a table of rows with one row buffer, and a read costs about 14 ns on a row hit, 28 ns on an empty bank and 41 ns on a row conflict" loading="lazy" decoding="async"></a>

**The smallest unit: a bank and its row buffer.** A DRAM cell is a tiny capacitor plus a switch, and its charge is too small to read on its own. So a **bank** — a table of tens of thousands of rows, about 1 KiB each per chip — is read by first **opening a whole row**: connecting all its cells to a row of sense amplifiers that amplify and latch the values. That latched row is the **row buffer**. The requested bytes are then taken from it by column. A bank has one row buffer, so one open row; reading another row of the same bank means closing (precharging) the current one first.

**Three cases.** On DDR4-3200 CL22 each of the three steps — open, read, close — takes about 22 clocks × 0.625 ns ≈ 14 ns:

- **row hit**: the row is already open → read only, **~14 ns**;
- **row empty**: no row open in this bank → open + read, **~28 ns**;
- **row conflict**: another row of the same bank is open → close + open + read, **~41 ns**.

Add queuing in the controller, the on-chip interconnect and the cache lookups on the way down, and a full DRAM access is typically 80–100 ns.

**Up the hierarchy.** A channel is 64 data bits wide; a common chip supplies 8, so **eight chips side by side form a rank** and respond together — a 64-byte line is eight beats of eight bytes, eight bytes from each chip, all opening the same row and column. Each chip has 16 banks (DDR4) that open rows independently, so the DIMM serves several requests concurrently. Ranks on one channel share its wires and take turns. **Channels** are independent sets of wires: bandwidth ≈ channels × per-channel bandwidth, while a single access gets no faster.

**Splitting the address.** Exactly like L1's set index, the controller splits the physical address into channel, rank, bank, row and column fields. Low bits pick the column, so consecutive addresses share an open row; channel and bank bits sit in between and are usually hashed. The exact mapping varies by platform and is rarely documented.

**Why a column walk is slow — five layers at once.** With `int matrix[31250][2048]` (8 KiB rows, 256 MB), walking down a column adds 8,192 bytes per step:

1. **Each line is 1/16 used**: a fresh 64-byte line per step, 4 bytes of it read.
2. **The rest is evicted before it's used**: the other 15 ints belong to the next 15 columns, 31,250 steps later. A column's lines total 2 MB, beyond L1 and L2, and an 8 KiB stride puts the whole column in one L1 set and in only 8 of L2's sets.
3. **Every step is a new page**: 31,250 pages per column against a TLB of a couple of thousand entries — a page walk almost every time.
4. **The prefetcher can't help**: hardware prefetchers generally don't cross 4 KiB pages.
5. **DRAM row conflicts**: neighbouring accesses 8 KiB apart often land in different rows of the same bank — ~41 ns each instead of ~14.

A row walk inverts all five: one opened DRAM row serves many lines, every line is fully used, the prefetcher runs ahead, and the TLB changes page once per 1,024 ints. The row buffer is only the bottom layer. The fixes are the same as before: change the traversal order (or transpose first), or tile.

---

## 12. Refresh: A Tail You Can't Turn Off

DRAM capacitors leak, so the controller must periodically read and rewrite every row. All rows within 64 ms, split into 8,192 batches, means a refresh command about every **7.8 µs** (tREFI); while it runs, the rank is unavailable for a few hundred ns (tRFC, about 350 ns for an 8 Gb DDR4 chip). That's 350 ÷ 7,800 ≈ **4.5%**: a random DRAM access has roughly that chance of waiting up to several hundred ns extra (estimated for all-bank refresh). It's invisible in the mean and shows up in **P99 and P99.9**.

Software can't turn it off. Keep the hot data set in cache so the hot path never reaches DRAM; use memory with fine-grained or per-bank refresh to shorten each stall; and when tail measurements show spikes with a ~7.8 µs period, think refresh.

---

## 13. Channel Balance: Make the Line Count Coprime

Channels only add bandwidth if they are busy at the same time. The controller interleaves consecutive addresses across them. In the simplest model, granularity 64 bytes: `channel = (address ÷ 64) mod N`.

Four channels, an array of 256-byte objects (4 lines each), a hot path that reads only each object's **first line**: object *i*'s first line is line 4*i*, and 4*i* mod 4 = 0. **Every hot line is on channel 0**, three channels idle. Pad the object to 5 lines (320 bytes): 5*i* mod 4 cycles 0, 1, 2, 3 — all four channels in turn.

The rule: **round the object to L lines and choose L coprime with the channel count N** — for 2 or 4 channels, an odd number of lines. Three channels balance naturally because any power-of-two line count is coprime with 3. Two caveats: real controllers mostly XOR-hash high address bits precisely to break such patterns, so check the platform's mapping and measure before padding by hand; and only bandwidth-bound workloads care — a hot set that lives in cache never reaches a channel.

---

## Recap

1. **Accesses pay in lines.** Alignment keeps a value inside one (64 is a multiple of every power-of-two size up to 64); padding keeps arrays aligned; member order changes `sizeof`.
2. **`alignas` buys isolation with space; `#pragma pack` gives alignment up to match an external format.** On a type, `alignas(64)` also pads `sizeof`; on a member it only moves the start. Heap memory needs `aligned_alloc` with a rounded size, `new`/`delete` paired on the same alignment, and `madvise` before the first touch for huge pages.
3. **Layout is line counting.** SoA for scans of a few fields, AoS for whole elements; denormalize to break a dependency chain, deciding by whether copies must be updated immediately; `alignas(64)` for per-thread writers, `alignas(32)` for packing two per line.
4. **The address picks an L1 set.** 64 sets × 8 ways makes addresses 4 KiB apart compete for 8 slots however empty the cache is; pad by a whole line, offset arrays by whole lines, or tile. Measured on an M1 with a 16 KiB critical stride: 0.20 → 0.81 ns per access — throughput, with dependent loads exposing far more.
5. **DRAM is rows, banks and channels.** Row hit ~14 ns, row conflict ~41 ns; a column walk loses at five layers; refresh adds a P99 tail no software removes; channels balance only when the hot stride is coprime with the channel count.
