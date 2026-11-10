---
title: "Low-Latency Trading — Context Switches, Page Tables and the TLB"
date: 2026-11-04
slug: "low-latency-context-switch-page-table-tlb"
list_after: "low-latency-memory-latency-bandwidth"
recent: false
description: "A thread switch and a process switch both cost 1–5 µs directly, and at that step they differ only in whether CR3 is rewritten; the real difference comes afterwards, in whether the TLB and caches are still warm. Page tables are per process, CR3 and the TLB are per core, and PCID lets a process switch skip flushing the TLB. The TLB has no MESI: changing a page table means sending an IPI to every core whose CR3 still points at it, which neither pinning nor isolcpus can stop. On the hot path, freeing a big block, munmap, transparent huge page collapsing, automatic NUMA balancing and fork all trigger it. Finally, how to see it happening."
summary: "Threads are lighter than processes because the TLB and caches stay usable after the switch, not because the switch itself is cheaper. The TLB has no MESI: when any thread in a process changes the page tables, every core still holding that page table gets interrupted, and pinning and isolcpus cannot prevent it, so once a hot-path process is running its address space is read-only."
chapter: 1
categories: [Systems]
tags: [linux, context-switch, page-table, tlb, pcid, tlb-shootdown, hft, low-latency]
toc: true
---

A hot thread is pinned to an isolated core and busy-polls, never making a system call, yet its p999 occasionally gains 1–5 µs. `perf` shows no hot spot, but the `TLB` row of `/proc/interrupts` keeps rising for that core: a logging thread in the same process `free`d a large block, glibc `munmap`ed it back to the kernel, the kernel changed the page tables, and that meant interrupting the hot core. To understand this you need to know what actually changes when the CPU switches threads or processes, and whether page tables and the TLB belong to a process or to a core. This post starts with a single switch, moves on to page tables and the TLB, and ends with why changing a page table interrupts other cores and which operations on the hot path set it off.

## 1. Context Switches: Where Threads and Processes Differ {#switch}

"Threads are lighter than processes" is often explained as: a thread switch doesn't change page tables or flush the TLB, it only swaps a few registers, so it is an order of magnitude faster. The first half is right; the second half is not.

### 1.1 What a Switch Does: Save, Swap Stacks, Restore {#what}

1. **Before the switch**
   - **Already in the kernel**: when a thread enters the kernel (a system call, an interrupt, preemption), its user-mode registers have already been saved on its own kernel stack ([user and kernel mode](/zh/ref/user-kernel-mode/#entry), in Chinese).
   - **Only inside the kernel**: the scheduler is kernel code, so a thread can only be switched out after entering the kernel.
2. **`context_switch()` does two things**
   - **Switch address space (`switch_mm`)**: only if the next task belongs to another process is CR3 changed to that process's page table (2.1). Threads of one process share one `mm`, so this step is skipped.
   - **Switch execution state (`switch_to`)**: save the current task's few kernel registers and stack pointer, move to the next task's kernel stack, restore its registers. On the way back to user mode, its user registers are taken back off its kernel stack. Floating-point and vector registers are swapped too; with AVX-512 enabled that alone is over 2 KiB.
3. **Where the time goes**
   - **Direct cost**: about 1–5 µs including wakeup and scheduling, and thread and process switches cost about the same.
   - **Not in swapping registers**: all of this is done on the CPU, with no disk and no waiting on anyone. Most of the time goes into entering and leaving the kernel, waking up, and the scheduler picking the next task.
   - **Conclusion**: **at this step a thread switch and a process switch differ in one place only: whether CR3 is rewritten.**

### 1.2 Warming Up Again After the Switch, and After Moving Cores {#after}

1. **After switching processes**
   - **Cold caches**: the new process's data is mostly gone from L1 and L2 (each core has only tens of KiB and a MiB or two), so every access goes to L3 or memory.
   - **Cold TLB**: it has few TLB entries left, so every new page it touches needs a page-table walk (2.2).
2. **Between threads of one process**
   - **Still warm**: the code, shared heap data, and the translations in the TLB.
   - **Not necessarily warm**: each thread's own stack and private data.
3. **A thread moving to another core**
   - **Page tables untouched**: the new core's CR3 points at the same page table, the translation rules are the same, nothing needs flushing.
   - **But everything is cold**: L1, L2 and the TLB are private to each core, so the hot data, instructions and translations the thread built up stay behind on the old core. On the new core, data is fetched again from L3 (from remote memory across sockets), and the TLB is refilled page by page. Pinning ([#1](/posts/cpu-affinity-core-isolation-numa/)) removes exactly this cost.
   - **Conclusion**: **most of a switch's cost is spread over the execution that follows it, so timing only the switch underestimates it. Threads are lighter because the TLB and caches stay usable after the switch.**
4. **How to see it**

   ```bash
   grep ctxt_switches /proc/<PID>/task/<TID>/status          # voluntary: went to sleep; nonvoluntary: preempted
   perf stat -e context-switches,cpu-migrations -t <TID> -- sleep 10
   ```

   - **`ctxt_switches`**: one per thread in `/proc`. `voluntary` rising means a call on the hot path sleeps; `nonvoluntary` rising means another task is competing for the core.
   - **`cpu-migrations`**: how many times the thread was moved to another core; if it rises, the pinning isn't holding.
   - **Hot threads**: all of these should stay near 0.

## 2. Page Tables, CR3 and the TLB: Which Layer Translates Addresses {#page-table-tlb}

### 2.1 One Page Table per Process, One CR3 per Core {#cr3}

1. **Page tables**
   - **What they are**: programs use virtual addresses, which must be translated to physical addresses before memory is accessed, and the rules are the process's page table. On x86-64 it is a 4-level tree with 512 entries per level.
   - **One per process**: the kernel's `mm_struct`, shared by all threads of the process.
2. **CR3**
   - **What it is**: a register, one per core, holding the physical address of the root page of the page table that core is using right now.
   - **At any moment**: several cores' CR3 can point at the same page table (several threads of one process on different cores) or at different ones (different processes).
   - **On a switch**: switching to another thread of the same process, CR3 is already right and stays; switching to another process writes that process's page-table root. From then on, the same virtual address on this core translates to a different physical page, or to nothing at all.

<svg viewBox="0 0 760 356" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Two cores, each with its own CR3 and private TLB. Core 0's CR3 points at process A's page table, shared by A's threads T1, T2 and T3; core 1's CR3 points at process B's page table. A switch between threads of one process leaves CR3 alone; switching to process B rewrites CR3, and without PCID the TLB is flushed. When a thread moves to core 1, core 1's CR3 also points at page table A, but core 1's TLB has none of A's entries yet." style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif">
  <style>
    .cx-bg    { fill: #fbfaf7; }
    .cx-panel { fill: #ffffff; stroke: #d9d4c7; stroke-width: 1.5; }
    .cx-muted { fill: #6b6558; }
    .cx-reg   { fill: #f1efe8; stroke: #c8c1ad; stroke-width: 1.2; }
    .cx-tlb   { fill: #dcecc6; stroke: #6f8f3f; stroke-width: 1.6; }
    .cx-pt    { fill: #eef1f4; stroke: #b9c2cc; stroke-width: 1.2; }
    .cx-hot   { fill: #f6ddd6; stroke: #c15b3f; stroke-width: 1.8; }
    .cx-off   { fill: none; stroke: #b4ae9f; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .cx-arrow { stroke: #8a8474; stroke-width: 2; fill: none; marker-end: url(#ahcx); }
    .cx-ipi   { stroke: #c15b3f; stroke-width: 2; fill: none; marker-end: url(#ahcx2); }
    .cx-title { fill: #1c1b18; font-size: 13px; font-weight: 700; }
    .cx-lbl   { fill: #3a372f; font-size: 11px; }
    .cx-cap   { fill: #6b6558; font-size: 10.5px; }
    .cx-red   { fill: #c15b3f; font-size: 11px; font-weight: 700; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-bg { fill: #17161b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-panel { fill: #201f26; stroke: #3a3945; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-muted { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-reg { fill: #2a2933; stroke: #47454f; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-tlb { fill: #33421f; stroke: #8fb257; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-pt { fill: #23262c; stroke: #3f4650; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-hot { fill: #4a2f2c; stroke: #e0795b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-off { stroke: #5a5664; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-arrow { stroke: #9a9384; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-ipi { stroke: #e0795b; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-title { fill: #e9e7ef; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-lbl { fill: #d7d3c8; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-cap { fill: #a19caf; }
      :root:is([data-theme="dark"], [data-theme="black"]) .cx-red { fill: #e0795b; }
  </style>
  <defs>
    <marker id="ahcx" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#8a8474"/>
    </marker>
    <marker id="ahcx2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="#c15b3f"/>
    </marker>
  </defs>
  <rect class="cx-bg" x="0" y="0" width="760" height="356" rx="10"/>
  <text class="cx-title" x="24" y="30">One CR3 per core, one page table per process</text>
  <rect class="cx-panel" x="24" y="48" width="380" height="124" rx="8"/>
  <text class="cx-muted" x="40" y="70" font-size="12" font-weight="700">Core 0: running thread T1 of process A</text>
  <rect class="cx-tlb" x="40" y="84" width="196" height="72" rx="6"/>
  <text class="cx-lbl" x="52" y="106" font-weight="700">TLB (private to this core)</text>
  <text class="cx-cap" x="52" y="124">caches A's translations</text>
  <text class="cx-cap" x="52" y="142">tens to thousands of entries</text>
  <rect class="cx-reg" x="252" y="84" width="136" height="72" rx="6"/>
  <text class="cx-lbl" x="264" y="106" font-weight="700">CR3</text>
  <text class="cx-cap" x="264" y="124">physical address of</text>
  <text class="cx-cap" x="264" y="142">the root page</text>
  <rect class="cx-panel" x="24" y="188" width="380" height="124" rx="8"/>
  <text class="cx-muted" x="40" y="210" font-size="12" font-weight="700">Core 1: running process B</text>
  <rect class="cx-tlb" x="40" y="224" width="196" height="72" rx="6"/>
  <text class="cx-lbl" x="52" y="246" font-weight="700">TLB (private to this core)</text>
  <text class="cx-cap" x="52" y="264">caches B's translations</text>
  <text class="cx-cap" x="52" y="282">tens to thousands of entries</text>
  <rect class="cx-reg" x="252" y="224" width="136" height="72" rx="6"/>
  <text class="cx-lbl" x="264" y="246" font-weight="700">CR3</text>
  <text class="cx-cap" x="264" y="264">physical address of</text>
  <text class="cx-cap" x="264" y="282">the root page</text>
  <rect class="cx-panel" x="468" y="48" width="268" height="124" rx="8"/>
  <text class="cx-muted" x="484" y="70" font-size="12" font-weight="700">Process A (one mm)</text>
  <rect class="cx-pt" x="484" y="84" width="236" height="36" rx="6"/>
  <text class="cx-lbl" x="496" y="107" font-weight="700">Page table A (4 levels)</text>
  <text class="cx-cap" x="484" y="142">shared by threads T1, T2, T3</text>
  <text class="cx-cap" x="484" y="160">thread switch in A: CR3 unchanged</text>
  <rect class="cx-panel" x="468" y="188" width="268" height="124" rx="8"/>
  <text class="cx-muted" x="484" y="210" font-size="12" font-weight="700">Process B (another mm)</text>
  <rect class="cx-pt" x="484" y="224" width="236" height="36" rx="6"/>
  <text class="cx-lbl" x="496" y="247" font-weight="700">Page table B (4 levels)</text>
  <text class="cx-cap" x="484" y="282">core 0 switches to B: CR3 set here</text>
  <text class="cx-cap" x="484" y="300">without PCID the TLB is flushed</text>
  <path class="cx-arrow" d="M388 120 L482 102"/>
  <path class="cx-arrow" d="M388 260 L482 242"/>
  <text class="cx-red" x="24" y="338">Thread moves to core 1: same page table A, same rules, but core 1's TLB holds none of A's entries yet.</text>
</svg>

> Figure: CR3 and the TLB belong to the core, the page table belongs to the process. Threads of one process walk the same page table, so switching between them leaves CR3 alone; only a process switch rewrites CR3.

### 2.2 The TLB: a Translation Cache, One per Core {#tlb}

1. **Why it exists**
   - **Walking the table is slow**: walking the 4-level page table on every access would mean four extra memory reads before each one.
   - **So translations are cached**: each core keeps recently used translations in its own TLB (translation lookaside buffer).
2. **How big, and how much it covers**
   - **Two levels**: the L1 dTLB has 64–96 entries, the second-level STLB 1500–3000, each entry covering one page.
   - **TLB reach**: with 4 KiB pages the STLB covers about 6–12 MiB; with 2 MiB huge pages the same number of entries covers 3–6 GiB.
   - **More detail**: working-set steps and how huge pages help are in section 3.2 of [Memory Latency and Bandwidth](/posts/low-latency-memory-latency-bandwidth/).
3. **What a miss costs**
   - **Page walk**: the hardware starts from CR3 and reads page-table entries level by level. Those entries are ordinary data in memory, the frequently used ones sit in L1, L2 and L3, and the CPU also has a page-walk cache for the upper levels.
   - **So only a little more**: reading a value from memory takes about 70–90 ns with a TLB hit and about 85–120 ns with a miss, 15–30 ns more ([Reference 2.1](/ref/cpu-memory/#latency)). Having to read all four levels from memory is rare; when it happens, one access takes about 300–400 ns.
   - **Large tables on the hot path**: order books, id maps and other randomly accessed tables larger than a few MiB lose this cost when placed on huge pages.

### 2.3 PCID: a Process Switch Need Not Flush the TLB {#pcid}

1. **Without PCID**
   - **Writing CR3 flushes**: every TLB entry was computed from one particular page table; after switching tables the old translations are wrong for the new process, so writing CR3 drops every non-global entry.
   - **Global entries stay**: kernel mappings are the same in every process, are marked global, and are not flushed.
2. **With PCID**
   - **Tagging**: PCID (process-context identifier) tags each entry with its address space. Writing CR3 with the new tag needs no flush: the old process's entries remain, the new process just can't see them, and they are usable again when the old one returns.
   - **Limited help**: Linux has used PCID since 4.14, but each core rotates through only a few tags, and the TLB holds only a few thousand entries in total, so a process that was away for a while usually finds its entries evicted.
3. **KPTI depends on it too**
   - **Why switch at all**: on CPUs affected by Meltdown, every kernel entry and exit writes CR3 to switch between the user page table and the full one ([user and kernel mode](/zh/ref/user-kernel-mode/#kpti), in Chinese).
   - **What PCID saves**: without it, every system call would flush the TLB; with it, the entries of the two page tables carry different tags, and switching back and forth needs no flush.

### 2.4 The Three Cases Side by Side {#compare}

| | CR3 | TLB | L1, L2 |
|---|---|---|---|
| Thread of the same process, same core | Unchanged | Still usable | Shared data still warm, each thread's stack and private data maybe not |
| Thread moves to another core | New core points at the same page table | Cold on the new core, refilled by walks on demand | Cold, fetched again from L3 or memory |
| Process switch | Rewritten | Flushed without PCID; mostly evicted even with PCID | Mostly evicted by the previous task |

**The differences all come after the switch.** Creation works the same way: a thread created with `clone` shares the `mm` and copies no page table; `fork` must copy a page table for the child ([processes and threads](/zh/ref/process-thread-fork/) section 2.2, in Chinese).

## 3. TLB Shootdown: Changing a Page Table Interrupts Other Cores {#shootdown}

### 3.1 The TLB Has No MESI {#no-mesi}

1. **Data caches and the TLB differ**
   - **Data caches**: they have [MESI](/posts/low-latency-mesi-cache-coherence/) between them; when one core writes a line, the hardware invalidates the copies in other cores.
   - **The TLB**: has no such mechanism. When a page-table entry in memory changes, stale translations cached in other cores' TLBs do not invalidate themselves.
2. **How the kernel makes up for it**
   - **Local core**: after changing the entries (`munmap`, `mprotect`, page migration, transparent huge page collapsing), it first invalidates its own entries with `invlpg`.
   - **Other cores**: it sends an inter-processor interrupt (IPI) to the cores that need to know; each enters its interrupt handler, invalidates the entries, and replies.
   - **Wait for every reply**: the initiating core cannot continue until all replies are in. Before that, another core could still follow a stale translation and write to a physical page already given back to the system.
   - **The name**: this round trip is a **TLB shootdown**.

<svg viewBox="0 0 760 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A cold thread on core 2 calls munmap: it changes the page-table entry, invalidates its own entry with invlpg, sends IPIs to the cores whose CR3 still points at this page table, and waits for every reply. Core 5, running the hot thread of the same process, and core 3, running another thread of it, both get the IPI; core 7 ran this process recently but now runs another, gets no IPI, and flushes by itself when it switches back." style="max-width:100%;height:auto;font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif">
  <rect class="cx-bg" x="0" y="0" width="760" height="300" rx="10"/>
  <text class="cx-title" x="24" y="30">The TLB has no MESI: a page-table change means IPIs, one per core</text>
  <rect class="cx-reg" x="24" y="60" width="250" height="114" rx="6"/>
  <text class="cx-lbl" x="36" y="84" font-weight="700">Core 2: a cold thread calls munmap</text>
  <text class="cx-cap" x="36" y="106">① change the page-table entry</text>
  <text class="cx-cap" x="36" y="124">② invlpg its own entry</text>
  <text class="cx-cap" x="36" y="142">③ IPI cores whose CR3 points here</text>
  <text class="cx-cap" x="36" y="160">④ wait for every reply</text>
  <path class="cx-ipi" d="M274 100 L428 73"/>
  <text class="cx-red" x="336" y="78">IPI</text>
  <path class="cx-ipi" d="M274 124 L428 137"/>
  <text class="cx-red" x="336" y="146">IPI</text>
  <rect class="cx-hot" x="430" y="48" width="306" height="50" rx="6"/>
  <text class="cx-lbl" x="442" y="68" font-weight="700">Core 5: hot thread (same process, isolated)</text>
  <text class="cx-cap" x="442" y="86">interrupted: enters the kernel, invalidates, replies</text>
  <rect class="cx-tlb" x="430" y="112" width="306" height="50" rx="6"/>
  <text class="cx-lbl" x="442" y="132" font-weight="700">Core 3: another thread of the process</text>
  <text class="cx-cap" x="442" y="150">also on the list, interrupted too</text>
  <rect class="cx-off" x="430" y="176" width="306" height="50" rx="6"/>
  <text class="cx-lbl" x="442" y="196" font-weight="700">Core 7: ran it recently, now runs another</text>
  <text class="cx-cap" x="442" y="214">no IPI: flushes by itself on switching back</text>
  <text class="cx-red" x="24" y="262">The initiator waits; each core that gets an IPI is interrupted once, pinning and isolcpus can't stop it.</text>
  <text class="cx-cap" x="24" y="282">Who is told: cores whose CR3 still points at this table. Only kernel mappings need every core.</text>
</svg>

> Figure: data caches invalidate each other in hardware; the TLB relies on the kernel sending interrupts. Every core still holding this page table stops to handle one, and the initiator waits for all their replies; cores that have switched away clean up when they come back.

3. **Who pays**
   - **The initiating core**: waits synchronously, for the slowest core to reply.
   - **Cores receiving the IPI**: interrupted once to enter the kernel, invalidate and reply, about like an interrupt, 1–5 µs, and their caches have been disturbed when they return.
   - **Conclusion**: **neither pinning nor `isolcpus` can stop it.** They control where the scheduler places tasks, while the IPI is a hardware interrupt that never goes through the scheduler ([#3](/posts/hot-path-memory-allocators/#shootdown) section 4.4).

### 3.2 Who Is Notified: Cores Whose CR3 Still Points at This Page Table {#who}

The IPI goes neither to "the cores running this process" nor to "every core that ever ran it", but to **the cores whose CR3 still points at this page table right now**.

1. **Why the line is drawn at CR3**
   - **TLB entries have one source**: page walks. A CPU only ever walks the table its own CR3 points at, and speculative execution walks ahead of time too.
   - **Cores whose CR3 points at this table**: may hold stale entries and may fill new ones from it at any moment, so they must be told immediately.
   - **Cores whose CR3 already points elsewhere**: can no longer walk this table and hold at most a few stale entries. With PCID those entries carry this process's tag and survive the process switch. But they only become usable when the core switches back to this process, and switching back always goes through the kernel's `switch_mm`.
   - **So**: the first kind must be interrupted now; the second kind can deal with it when it switches back.
2. **What the kernel does**
   - **The list**: each address space keeps a set of cores, `mm_cpumask`, and a core adds itself when it switches to the process. Before sending IPIs the kernel also checks which address space each core has loaded right now (the per-core `loaded_mm`) and sends only to the cores still holding this one.
   - **The version number**: each address space keeps a page-table generation `tlb_gen`, incremented on every change; each core records which generation it has flushed up to for that address space. When a core switches back it compares the two, and if it is behind it flushes before running, so a core busy with something else never has to be interrupted.
   - **Conclusion**: **a change to user page tables interrupts only the cores still holding that page table; cores that ran it and switched away postpone the cleanup to the moment they return, and do it themselves.**
3. **Lazy TLB: CR3 still points at it, but no interrupt yet**
   - **What it is**: kernel threads have no user address space of their own, so switching to one keeps CR3 and borrows the previous process's page table. This is called lazy TLB.
   - **Ordinary page-table changes**: no IPI. Kernel threads don't touch user addresses, so stale entries are harmless for now; when the core leaves lazy mode it flushes according to the version number.
   - **Freeing page-table pages needs one**: CR3 still points at these tables, and speculative execution could follow it into page-table pages already given back, so lazy cores are told immediately in this case.
4. **The kernel's own mappings**
   - **Which**: `vmalloc` regions and loaded modules, present in every address space.
   - **Who is told**: every core. The kernel batches these and flushes them together.
5. **Hardware broadcast**
   - **Which CPUs**: the ARM64 `TLBI … IS` instructions, and `INVLPGB` on newer AMD.
   - **How it works**: the hardware broadcasts the invalidation to all cores, which don't take an interrupt.
   - **No list**: cores are not picked per process, so the list above isn't needed.

### 3.3 What Triggers It on the Hot Path {#triggers}

**In one process, whenever any thread changes the user page tables, every other running thread is interrupted along with it.** Even if the hot thread changes nothing, other threads in the process and kernel background tasks do. Adding a mapping needs no notification: an unmapped address never enters the TLB, so only removing mappings, tightening permissions and replacing physical pages require invalidation.

| Source | Why it changes the page table | How to avoid it | More |
|---|---|---|---|
| `free` of a large block | Allocations of 128 KiB and up get their own `mmap` by default and are `munmap`ed on `free`; with enough free space glibc also shrinks the heap and gives pages back with `madvise` | Preallocate at startup and use pools on the hot path; turn off mmap and trimming with `mallopt` | [#3](/posts/hot-path-memory-allocators/#keep-memory) Part 4 |
| `munmap`, `mprotect`, `mremap` at run time | Directly remove mappings, tighten permissions, move mappings | Finish mapping at startup and leave it alone while running | [where one new goes](/zh/ref/new-malloc-page-fault/) (in Chinese) |
| `fork` | Every writable page of the parent becomes read-only (copy-on-write), and later whoever writes first gets a new page | No `fork` while the hot-path process runs; start child processes at startup | [processes and threads](/zh/ref/process-thread-fork/) section 2.2 (in Chinese) |
| Transparent huge page collapsing (`khugepaged`) | Replaces 512 small pages with one huge page, so old translations must go | `transparent_hugepage=never`; request huge pages explicitly when you want them | [#19](/posts/scheduling-priority-inversion-kernel-tuning/) section 4.4 |
| Automatic NUMA balancing | Periodically marks pages inaccessible, uses the faults to see who uses them, then migrates them | `kernel.numa_balancing=0`, bind with `numactl` yourself | [#19](/posts/scheduling-priority-inversion-kernel-tuning/) section 4.4 |
| KSM, memory compaction | Merging identical pages and moving physical pages both change translations | Turn off KSM; `vm.compact_unevictable_allowed=0` so compaction doesn't move locked pages | [#19](/posts/scheduling-priority-inversion-kernel-tuning/) section 4.4 |

- **Threads in the process**: the first three rows come from your own code; find them and move them to startup.
- **Kernel background tasks**: the last three rows are the kernel's own work and have to be turned off with boot parameters and sysctl.
- **Conclusion**: **once a hot-path process is running, its address space is read-only: map, touch and lock the memory it needs at startup; leave freeing and tidying until after the close.**

### 3.4 How to See It {#see}

```bash
watch -d -n 1 'grep TLB /proc/interrupts'                  # one column per core: is the hot core's column rising?
strace -f -e trace=munmap,mprotect,mremap,madvise -p <PID>  # which thread in the process changes mappings
```

- **The `TLB` row of `/proc/interrupts`**: how many TLB shootdowns each core has received. If the hot core's column rises, something is changing this process's page tables.
- **strace catches calls**: a thread of the process itself is doing it; `-f` prints the thread id, so you can tell which.
- **strace catches nothing**: check whether the kernel background tasks (transparent huge pages, NUMA balancing, KSM) are on.
- **strace slows the traced process**: every system call stops to be recorded, so use it only while investigating, never on a production hot-path process.
