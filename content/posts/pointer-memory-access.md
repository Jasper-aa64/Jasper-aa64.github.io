---
title: "Trading System Notes #10: Pointer and Memory-Access Optimization"
date: 2026-10-12
slug: "pointer-memory-access"
description: "Three things: telling the compiler two pointers don't overlap with __restrict (fewer loads at -O2, no run-time check at -O3); storing “next” in a linked structure as an index, a pointer or a 3-byte compact index (addressing mode costs one cycle, size doubles, and for big chains only bytes matter); pointer compression that stores offsets instead of addresses (and the null-vs-first-object collision at 0), plus the rules for streaming stores and PCIe / MMIO writes. All assembly is real GCC 13 output."
summary: "In a loop like a[i] = *b, the compiler re-reads *b every iteration, because writing a[i] might change it. Pointer optimization is about letting the compiler read less, and fitting linked structures into nearer caches."
chapter: 1
categories: [Systems]
tags: [cpp, pointers, aliasing, restrict, pointer-chasing, pointer-compression, hft, low-latency]
toc: true
math: true
light: true
---

This loop fills the array `a` with the value of `*b`:

```cpp
void func(int *a, int *b, int n) {
    for (int i = 0; i < n; ++i) {
        a[i] = *b;
    }
}
```

`*b` is never assigned in the loop, so reading it once should be enough. Yet GCC 13 `-O2` reads it every iteration:

```text
.L3:
    movl  (%rsi), %eax      # read *b every iteration
    addq  $4, %rdi
    movl  %eax, -4(%rdi)    # write a[i]
    cmpq  %rdx, %rdi
    jne   .L3
```

The reason is that `b` might point into `a`, so writing `a[i]` might change `*b`, and the compiler can't assume it didn't. This post covers three things: how to let the compiler read memory less; how to store data more compactly, from how many bytes "where's the next one" takes in a linked structure to packing pointers and several IDs into one integer; and which instructions to use for large writes and writes to devices. The assembly is real GCC 13.3 x86-64 output; cycle counts are ranges for intuition, not timings.

## 1. `__restrict`: Promising the Compiler Two Pointers Don't Overlap

### 1.1 Aliasing: Two Pointers May Point at the Same Memory

Two pointers to the same memory **alias** each other. Aliasing is what blocked the optimization above. Add `__restrict` to the parameters:

```cpp
void func_restrict(int *__restrict a, int *__restrict b, int n) {
    for (int i = 0; i < n; ++i) {
        a[i] = *b;
    }
}
```

It means "within this function, memory accessed through this pointer is not accessed through any other pointer". The compiler then hoists `movl (%rsi), %eax` out of the loop and reads it once; the loop only writes, and it is unrolled to two writes per iteration as well.

### 1.2 `-O3`: the Compiler Checks at Run Time Itself

At `-O3`, `func` without `__restrict` vectorizes too. The compiler emits two versions of the loop and compares addresses first: if `b` doesn't fall inside `a[0..n)`, it takes a vector version that writes 16 B at a time; if it does, it takes the element-by-element version that re-reads `*b`. This is **loop versioning**. So at `-O3`, `__restrict` saves those comparisons and the fallback copy of the code; the big difference shows up at `-O2`, or when the aliasing is too complex for the compiler to bother generating a check.

### 1.3 The Cost: It's Your Promise, and Nobody Checks It

- **Breaking it is undefined behavior.** If you write `__restrict` and then pass overlapping pointers, the compiler still optimizes as if they don't overlap, and the result is silently wrong, with no error anywhere.
- **It affects only the compiler; the CPU never sees it.** There's no "restrict" in machine code; its whole effect is in which instructions the compiler emits. The CPU still checks every load against earlier stores to the same address.
- **It isn't standard C++.** C99 has `restrict`, C++ doesn't; GCC, Clang and MSVC all support the `__restrict` extension.
- **Different types don't need it.** Under strict aliasing, `int*` and `float*` are assumed not to overlap; `__restrict` is about two pointers of the same type. A `const T*` parameter doesn't replace it either: `const` only says you won't modify through it, while other pointers still can ([Reference: `const`](/ref/cpp-syntax/#const)).

## 2. How Wide to Store "Next" in a Linked Structure

### 2.1 The Premise: Pointer Chasing Waits on Every Step

Linked lists, price-level chains in an order book, free lists in an object pool: all of them "read where the next one is, then go read it". The address of the next load isn't known until this load finishes, so **pointer chasing** like this can't issue loads early ([memory latency and bandwidth](/posts/low-latency-memory-latency-bandwidth/)), and every step pays a full access latency: L1 about 1 ns (4–5 cycles), L2 about 3–5 ns, L3 about 10–30 ns, memory about 70–120 ns. When the whole chain sits in L1, a step takes only a few cycles and one extra instruction shows; once the chain falls to memory, every step is a full memory latency, a few extra instructions don't matter, and what matters is whether the chain is small enough to land in a nearer level. So a chain's speed comes down to two things: **how long each step's instructions take** and **how big the whole chain is**. How wide you store "next" affects both.

### 2.2 Index or Pointer: One Cycle of Addressing, Twice the Size

"Next" can be stored as a 4-byte index (`k = q[k]`) or an 8-byte pointer (`k = k->ptr`). Each step compiles to one instruction:

```text
chase_int:   movslq (%rcx,%rax,4), %rax     # base + index × 4, load 4 bytes and sign-extend to 64 bits
chase_ptr:   movq   (%rax), %rax            # load 8 bytes straight through the pointer
```

The index version doesn't add a multiply: `× 4` is part of the x86 addressing mode (the scale). The difference is the addressing mode itself: on many x86 cores, only a simple "one register (plus a small offset)" address gives a result in about 4 cycles on an L1 hit, while an indexed address takes about 5. So when everything is in L1, the pointer chain is about one cycle per step faster.

On the other hand, a pointer is 8 bytes and an index 4, so for the same number of nodes the pointer chain is twice as big. With 1024 nodes it's 8 KiB versus 4 KiB, both in L1, and the pointer wins. With a million nodes it's 8 MiB versus 4 MiB: the index chain may still be in L3 while the pointer chain has to read memory, and that step differs by 10–30 ns versus 70–120 ns; the one-cycle addressing advantage stops mattering. **For small chains count instructions; for big chains count bytes.**

### 2.3 "32-Bit Pointers": in a 64-Bit Program, Usually Just an Index

The pointer wins on addressing and the index wins on size, so the natural wish is to have both: a pointer that takes only 4 bytes and can be loaded through directly. That's what people call a "32-bit pointer".

In a 64-bit program that usually doesn't work, because 4 bytes can't hold an address. Four bytes reach only 4 GiB (`0xffffffff`), while addresses in a 64-bit program usually sit far above that; on Linux something like `0x7ffd5a3c1e80` is typical. Casting an address straight to `uint32_t` is a compile error in g++ (`cast ... loses precision`: the cast would lose information). Forcing it (casting to `uintptr_t` first, then truncating to `uint32_t`) compiles, but the high bits are thrown away, and the pointer you rebuild from it points somewhere else.

What 4 bytes can hold is "which slot of the array the next node is in" (or how many bytes it is from the start of the array). To follow it, you first compute "array start + slot × node size", which is exactly the index version above, and you pay the same extra cycle. **So most of the time a "32-bit pointer" is just another name for an index**, and the trade-off between pointer and index doesn't go away.

There are two exceptions. If the nodes already live below 4 GiB (for example, memory from Linux `mmap` with `MAP_32BIT`, which lands in the lowest 2 GiB), 4 bytes do hold the full address and can be loaded through directly. Or the whole program can be built with 4-byte pointers: a 32-bit build (`-m32`), or the rarely used x32 ABI (`-mx32`).

### 2.4 A 24-Bit Compact Index: 25% Less Space, More Instructions per Step

If the index chain is only slightly bigger than some cache level, you can squeeze further: each element takes only 3 bytes, 25% less than a 4-byte index. The cost is reading 3 bytes and stitching them together at every step:

```cpp
int chase_24(const uint8_t* q, int k, int steps) {   // k is a byte offset = index × 3
    for (int i = 0; i < steps; i++) {
        int next_val = q[k] | (q[k + 1] << 8) | (q[k + 2] << 16);
        k = next_val & ((1 << 24) - 1);
    }
    return k;
}
```

Each step compiles to 3 loads, 2 shifts and 2 ORs, plus a few address and sign-extension instructions, all on the dependence chain. When everything is in L1 it is slower than a 4-byte index; it only pays off when the 25% saved is exactly what lets the chain drop back from one cache level to the one above.

Get the capacity right too: this stores a **byte offset** (index × 3), and 24 bits top out at $2^{24} - 1$, so at most about $2^{24} / 3 \approx 5.59$ million elements, not $2^{24}$. For about 16 million, store the index itself and multiply by 3 at each step (one `lea`).

## 3. Pointer Compression: Store Offsets, Not Addresses

An index works only because every element in the pool has the same size: element k sits at "start + k × element size". When objects differ in size, or several types share one block of memory (order and price-level nodes in one arena, messages of different lengths in one buffer), there is no "k-th element", only a byte position: how far from the start of the pool.

Storing the raw byte offset in 4 bytes covers only 4 GiB. But objects are usually aligned to $2^s$ bytes, so every object starts at a multiple of $2^s$ and the low $s$ bits of its offset are always 0; storing them is pure waste. Shift the offset right by $s$ before storing it, and back left when using it:

$$
\text{code} = \frac{\text{address} - \text{base}}{2^{s}}, \qquad \text{address} = \text{base} + \text{code} \times 2^{s}
$$

With 16-byte alignment ($s = 4$), an object `0x1230` bytes from the start of the pool has 0 in its low 4 bits, so you store just `0x123`; to use it, shift left by 4 to get `0x1230` back and add the pool's start. The same 4 bytes now cover $2^{32} \times 16$ B = 64 GiB instead of 4 GiB.

Seen this way, an index is a special case: when all objects have the same size and that size is exactly $2^s$, the offset shifted right by $s$ is the index. The two differ only in their unit: an index counts elements, a compressed pointer counts $2^s$-byte alignment slots. Because the unit is the alignment, it can point at any aligned object in the pool, whatever its type or size. It doesn't beat an index on capacity: with the same 4 bytes, an index covers $2^{32}$ elements, and the bigger the elements, the more bytes that is (256 GiB for 64-byte nodes).

The cost lands on every step, just as with an index: decoding is one shift and one add. With a shift of 0–3 (×1, 2, 4 or 8), the x86 addressing mode folds this into the load as a single instruction, about 5 cycles like the index version; a shift of 4 needs a separate shift first, about one cycle more. In exchange, every pointer in a node shrinks from 8 bytes to 4. Structures whose nodes carry several pointers, such as order books and intrusive lists, save half on each, so nodes get noticeably smaller and more of them fit in a cache line. The JVM's compressed oops do exactly this: a 32-bit code, 8-byte alignment, shift by 3, covering a 32 GB heap.

An easy mistake: null is usually encoded as 0, and the **first object** in the pool also has offset 0. Once pointers become small integers, "nothing" and "the first one" collide: with "the code is the offset", compressing `&pool[0]` and decompressing gives `nullptr`. So reserve 0 for null and add 1 to every other code:

```cpp
template <typename T>
struct Compressed32 {
    T* base;
    uint32_t shift;                                         // log2(alignof(T))
    uint32_t pack(const T* p) const {
        if (!p) return 0;
        return uint32_t(((reinterpret_cast<uintptr_t>(p) - reinterpret_cast<uintptr_t>(base)) >> shift) + 1);
    }
    T* unpack(uint32_t c) const {
        if (c == 0) return nullptr;
        return reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(base) + (uintptr_t(c - 1) << shift));
    }
};
```

The $-1$ in decoding costs nothing if you precompute $\text{base} - 2^s$: it merges into the add. Another value (such as `UINT32_MAX`) can stand for null instead. Two more rules: the pool must not exceed what the code can represent, and object addresses must really be aligned to $2^s$, or the shifted-out low bits are lost.

## 4. Composite Indexes: Several IDs Packed Into One 64-Bit Integer

Positions and risk records are often looked up by several IDs together. Kept as separate fields, a comparison takes several compares and a hash has to mix several values. Packing a client ID (32 bits), a member ID (12 bits) and a contract ID (20 bits) into one `uint64_t` lets it act as a single integer: a hash-map key, a sort key, a one-instruction compare:

```cpp
struct CompositeIndex {
    uint64_t client : 32;
    uint64_t member : 12;
    uint64_t contract : 20;
};
uint64_t encode(CompositeIndex idx) {
    return uint64_t(idx.client) | (uint64_t(idx.member) << 32) | (uint64_t(idx.contract) << 44);
}
CompositeIndex decode(uint64_t val) {
    return {
        .client = val & 0xFFFFFFFF,
        .member = (val >> 32) & 0xFFF,
        .contract = (val >> 44) & 0xFFFFF
    };
}
```

The `uint64_t(...)` casts in `encode` are required. A 12- or 20-bit bit-field is first **promoted to `int`** before arithmetic (an `int` can hold all its values), so writing `idx.member << 32` shifts a 32-bit `int` by 32: undefined behavior. GCC 13 gives only a `-Wshift-count-overflow` warning, and `member` and `contract` vanish from the result; Clang 18 returns 0 outright. Also, bit-field layout in memory is implementation-defined, so for a stable encoding shift explicitly as `encode` does, rather than reinterpreting the struct's bytes as an integer.

## 5. Large Writes and Writes to Devices

### 5.1 Non-Temporal Stores: No Read-Back, No Cache

An ordinary store to a line that isn't cached first reads the whole line back (RFO) and later writes it back, so each line crosses the bus twice. A **streaming store** (non-temporal store, such as `_mm256_stream_si256`) fills 64 B in a WC (write-combining) buffer and writes it straight to memory, crossing once, for up to twice the bandwidth (the mechanism is in the streaming-store section of [memory latency and bandwidth](/posts/low-latency-memory-latency-bandwidth/)). Rules for using it:

- **Only for large blocks you won't read again soon.** Afterwards the data isn't in cache; reading it right away means going back to memory. For blocks smaller than the cache, ordinary stores are faster.
- **Align the address.** `_mm256_stream_si256` requires 32-byte alignment and crashes otherwise.
- **It's weakly ordered.** Streaming stores don't keep the ordering ordinary stores have: write the data, then a "ready" flag, and another core may see the flag before the data. Issue `_mm_sfence()` before publishing.
- **`memset` / `memcpy` already use it.** glibc switches to streaming stores by itself once a block is on the order of the shared cache (L3). Writing it by hand is worth it to control the threshold explicitly, or where glibc wouldn't use it.

### 5.2 Writing PCIe / MMIO: Whole 8-Byte Writes, Not a Generic `memcpy`

The registers and descriptor areas of a NIC or FPGA are mapped into the process address space (MMIO), often as WC (write-combining) memory. Every write to it ends up as a write transaction on the PCIe bus. A generic `memcpy`, handling every length and alignment, may break a copy into 1- and 2-byte pieces, each of which may become a separate transaction. Whole, aligned 8-byte writes are more likely to merge in the WC buffer into fewer transactions:

```cpp
inline void copy_u64_blocks(volatile void* dst, const void* src, size_t nbytes) {
    // nbytes must be a multiple of 8; dst/src should be 8-byte aligned
    auto* d = static_cast<volatile uint64_t*>(dst);
    const auto* s = static_cast<const uint64_t*>(src);
    const size_t n = nbytes / sizeof(uint64_t);
    for (size_t i = 0; i < n; ++i) {
        d[i] = s[i];
    }
}
```

The destination is a `volatile` pointer so the compiler won't merge, reorder or drop these writes; if the device must be guaranteed to have seen them, add an `sfence` afterwards. This applies only to device memory: `memcpy` on ordinary memory is already highly optimized, so don't replace it.
