#!/usr/bin/env python3
"""Process map for the reference page (/zh/ref/process-memory/).

One data definition below generates:
  static/images/ref/process-map.zh.svg   the static map shown on the page
  static/maps/process-map.zh.html        the interactive map (click a box, step through a path)

To change the map, edit NODES / EDGES / LABELS / TOURS and run from the repo root:
  python -X utf8 tools/process-map/gen_process_map.py
It prints a warning for every line of text that looks wider than its box.
Chinese only for now; the English version follows once the layout is settled.
"""
import html
import json
import os
import random

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
W, H = 1600, 1555
FONT = 'PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif'
LANGS = ('zh',)
HW = '/maps/hardware-map.zh.html'


def post(lang, slug, anchor=''):
    return ('/zh/posts/' if lang == 'zh' else '/posts/') + slug + '/' + ('#' + anchor if anchor else '')


def ref(lang, slug, anchor=''):
    return ('/zh/ref/' if lang == 'zh' else '/ref/') + slug + '/' + ('#' + anchor if anchor else '')


ALLOC = 'hot-path-memory-allocators'
LAYOUT = 'alignment-layout-cache-dram-geometry'
SPMC = 'spmc-shared-memory-broadcast-ring'

# ---------------------------------------------------------------- boxes
# box = (x, y, w, h); cls: kern = kernel, hole = unmapped, stack, mmap, heap, img = sections of the program file,
# buf = page table / page fault, mem = physical memory, note = explanation.
# lines/tags are drawn in the box; panel is the longer text shown when the box is clicked.
NODES = {}


def node(nid, box, cls, zh, mono=False, extra=None):
    NODES[nid] = dict(box=box, cls=cls, zh=zh, mono=mono, extra=extra or [])


node('kernel', (165, 128, 595, 152), 'kern',
     zh=dict(title='内核空间（128 TiB）：所有进程共用同一份',
             lines=['内核代码和数据、每个进程的页表、每个线程的内核栈（16 KiB）',
                    '系统调用、缺页、中断时，CPU 切到这里执行',
                    '还有全部物理内存的线性映射、页缓存（读写文件时缓存的文件内容）',
                    '用户态的代码读写这段地址 → SIGSEGV'],
             tags=[[('#19 调度策略与内核调优', post('zh', 'scheduling-priority-inversion-kernel-tuning'))]],
             panel=['64 位地址空间的高半区留给内核。每个进程的页表里，这一半映射的都是同一份内核，所以切换进程时内核这一半不用换。',
                    '系统调用、缺页、中断发生时，CPU 切到内核态，在这里执行。用户态的代码访问这段地址，页表里的权限位不允许，进程收到 SIGSEGV。',
                    '内核还把全部物理内存线性地映射在这一段里（direct map），所以内核能直接读写任何一页物理内存。']))

node('hole', (165, 292, 595, 58), 'hole',
     zh=dict(title='非规范地址空洞（约 16 M TiB）',
             lines=['地址只有 48 位有效：bit 47 往上必须全和 bit 47 相同，中间这一大段不能用'],
             tags=[],
             panel=['x86-64 的 4 级页表只翻译 48 位虚拟地址，64 位指针的高 16 位必须和第 47 位相同。所以能用的只有最低的 128 TiB（用户空间）和最高的 128 TiB（内核），中间约 16 M TiB 都不能用。',
                    '访问这里的地址，CPU 直接报一般保护错误（#GP），进程同样收到 SIGSEGV。开了 5 级页表的机器是 57 位，道理一样，只是两头更大。']))

node('stack', (177, 396, 571, 96), 'stack',
     zh=dict(title='主线程的栈 ↓',
             lines=['局部变量、函数参数、返回地址；每调用一层，往低地址长一段',
                    '上限默认 8 MiB（ulimit -s），用超了碰到保护页 → SIGSEGV'],
             tags=[[('#11 返回值优化：返回的对象直接构造在调用者的栈上', post('zh', 'rvo-pure-functions'))]],
             panel=['每调用一次函数，栈指针往低地址挪一段（一个栈帧），放局部变量、保存的寄存器和返回地址；返回时挪回来。所以栈上分配和释放就是一条加减指令，而且总在最近用过的那几条缓存行附近，几乎总命中 L1。',
                    '主线程的栈上限默认 8 MiB（ulimit -s）。递归太深或者局部数组太大，就会越过底下的保护页，收到 SIGSEGV，这就是栈溢出。',
                    '栈顶上方还放着 argv、环境变量和辅助向量（auxv），是内核启动程序时放进去的。']))

node('vdso', (177, 500, 571, 70), 'stack',
     zh=dict(title='[vvar] [vdso]：内核映射进来的一小段代码和数据',
             lines=['clock_gettime、gettimeofday 在这里直接读 TSC 算时间，不进内核'],
             tags=[[('#20 1.2 clock_gettime 走 vDSO', post('zh', 'tsc-latency-measurement', '12-rdtsc读一次约-10-ns但读数不一定一个-tick-一个-tick-地走'))]],
             panel=['vDSO 是内核映射进每个进程的一小段代码，vvar 是它要读的数据（时钟的换算参数）。',
                    'clock_gettime 调到这里，直接读 TSC 再换算成纳秒，不用陷入内核，所以只要约 20–30 ns；一次真正的系统调用要 100 ns 以上。']))

node('libs', (189, 614, 266, 134), 'mmap',
     zh=dict(title='共享库（.so）',
             lines=['libstdc++、libc、ld.so', '每个库也分代码段、数据段', '代码页所有进程共用一份'],
             tags=[],
             panel=['动态链接的程序，启动时由动态链接器 ld.so 把 libstdc++、libc 这些 .so 映射进这里。每个库自己也分成只读可执行的代码段和可写的数据段，所以在 /proc/<pid>/maps 里同一个文件连着好几行。',
                    '库的代码页是从同一个文件映射的只读页，所有用这个库的进程共用同一份物理页；数据段是写时复制的私有页，各进程一份。',
                    '调库函数要经过 .plt 跳板，从 GOT 表里查到真正的地址；静态链接（-static）就没有这一层，也没有这一块。']))

node('bigmalloc', (470, 614, 266, 134), 'mmap',
     zh=dict(title='大块 malloc（≥ 128 KiB）',
             lines=['glibc 直接 mmap 一块新映射', 'free 时立刻 munmap 还给内核', '门槛会随使用自动调高'],
             tags=[[('#3 2.1 mmap 陷阱', post('zh', ALLOC, '21-光靠-mlockall-有个漏洞'))]],
             panel=['glibc 的 malloc 遇到大于 M_MMAP_THRESHOLD（默认 128 KiB）的请求，不从堆里切，而是直接 mmap 一块新的匿名映射；free 时立刻 munmap。',
                    '所以反复分配、释放大块内存，每次都要进内核 mmap、munmap，下次再碰又要缺页；munmap 改了页表，内核还得通知跑过这个进程的其他核把旧的 TLB 项作废（TLB shootdown）。',
                    '这个门槛是动态的：释放过一块 mmap 来的大块以后，glibc 把门槛调到那块的大小（64 位上最多 32 MiB），之后同样大小的分配改走堆。']))

node('tstack', (189, 760, 266, 134), 'mmap',
     zh=dict(title='其他线程的栈 + TLS',
             lines=['每个线程一块，默认 8 MiB', '最低处留一页保护页', 'thread_local 在栈顶那头'],
             tags=[],
             panel=['pthread_create（std::thread 底下就是它）给每个新线程 mmap 一块栈，默认大小等于 ulimit -s，通常 8 MiB。最低处留一页不可访问的保护页，栈溢出时碰到它就 SIGSEGV，不会悄悄写坏挨着的映射。',
                    '线程控制块和 TLS（thread_local 变量）放在这块栈的最高处，线程的 fs 寄存器指着它，访问 thread_local 就是“fs + 偏移”。',
                    '8 MiB 只是虚拟地址，真正用到的页才占物理内存，所以开几百个线程不会立刻吃掉几 GB。']))

node('filemap', (470, 760, 266, 134), 'mmap',
     zh=dict(title='文件映射、共享内存',
             lines=['mmap 文件：读写的就是页缓存', '/dev/shm：几个进程映射同一批页', '大页（hugetlbfs）也映射在这里'],
             tags=[[('#5 2 放进共享内存', post('zh', SPMC, '2-放进共享内存'))]],
             panel=['mmap 一个文件，读写这段内存就是直接读写内核的页缓存，省掉 read、write 在内核缓冲和用户缓冲之间的那次拷贝。',
                    'shm_open 加 mmap（/dev/shm 下的文件）让几个进程把同一批物理页映射进各自的地址空间。同样的字节，在每个进程里的虚拟地址可以不同，所以共享内存里不能存指针，只能存偏移。',
                    'hugetlbfs 的大页、MAP_ANONYMOUS 的匿名映射也都在这一区。']))

node('heap', (177, 976, 571, 96), 'heap',
     zh=dict(title='堆 ↑（brk）',
             lines=['new、malloc 的小块从这里切：先查本线程的缓存（tcache），不够再找 arena',
                    'arena 不够了，brk 把堆顶往上推；推出来的只是虚拟地址'],
             tags=[[('#3 内存池与分配器', post('zh', ALLOC))]],
             panel=['new 先调 operator new，再调 malloc。glibc 的 malloc 先查本线程的缓存（tcache），再到 arena 的空闲块里找。主线程的 arena 就是这块用 brk 长出来的堆，其他线程的 arena 是另外 mmap 的。',
                    '空闲块不够了，malloc 调 brk 把堆顶往高地址推一段，这一步要进内核。推出来的只是虚拟地址，第一次写才缺页、拿到物理页。',
                    '堆上的数据访问起来和栈一样快，都是普通内存。慢在别处：分配和释放要走 malloc，耗时不固定；对象一个个 new 出来散在各处，局部性差。']))

node('bss', (177, 1080, 571, 58), 'img',
     zh=dict(title='.bss：没有初值的全局变量和 static 变量',
             lines=['初值都是 0，文件里只记大小，启动时映射成全 0 的页'],
             tags=[],
             panel=['没写初值（或初值为 0）的全局变量、static 变量放在 .bss。它们的初值都是 0，所以可执行文件里不用存内容，只记一个大小；启动时内核把这段映射成全 0 的匿名页。',
                    '所以声明一个 1 GB 的全局数组，可执行文件不会变大，用 size 命令看是 bss 那一栏变大。']))

node('data', (177, 1146, 571, 58), 'img',
     zh=dict(title='.data：有初值的全局变量和 static 变量',
             lines=['初值存在可执行文件里，启动时映射进来，可读可写'],
             tags=[],
             panel=['int g = 1; 这种有非零初值的全局变量、static 变量放在 .data。初值存在可执行文件里，启动时映射进来。这些页是写时复制的：只读不写时和文件共用页缓存，第一次写才复制成这个进程私有的一页。',
                    '.data 和 .bss 的大小链接时就定死了，运行时不会变；要能变大的数据放堆上。']))

node('rodata', (177, 1212, 571, 90), 'img',
     zh=dict(title='.rodata：只读数据',
             lines=['字符串字面量、有常量初值的 const 全局变量、编译期算好的查找表',
                    'vtable 在 .data.rel.ro：启动时填好函数地址，再改成只读'],
             tags=[[('速查 C++ 语法 1.2 vptr 和 vtable', ref('zh', 'cpp-syntax', 'virtual-vtable'))]],
             panel=['字符串字面量（"hi"）、有常量初值的 const 全局变量、编译期算好的查找表放在 .rodata。这些页是只读的，写它会收到 SIGSEGV。',
                    'vtable 和 typeinfo 里存的是函数和对象的地址。开了 PIE 以后，这些地址要等加载基址定下来才能填，所以放在 .data.rel.ro：动态链接器启动时填好，再用 mprotect 改成只读（RELRO）。效果上和 .rodata 一样只读。',
                    '常说的“常量区”就是这一段。']))

node('text', (177, 1310, 571, 90), 'img',
     zh=dict(title='.text：机器码（只读 + 可执行）',
             lines=['函数编译出来的指令；.plt 是调 .so 里函数的跳板',
                    'PIE 每次加载到随机地址；gdb 默认关掉随机化，基址常见 0x5555 5555 4000'],
             tags=[[('#6 2.6 函数分组：代码也走缓存', post('zh', LAYOUT, '26-函数分组代码也走缓存'))]],
             panel=['函数编译出来的机器码放在 .text，页是只读可执行的。因为不能写，多个进程跑同一个程序时共用同一份物理页。',
                    '开了 PIE（现在的默认），整个程序每次加载到一个随机的基址（ASLR），地址常见 0x55… 或 0x56… 开头；gdb 默认关掉随机化，基址常见 0x5555 5555 4000。',
                    '指令也走缓存：取指从 L1I 取。经常一起调用的函数挤在一起，占的 L1I 和 iTLB 就少。']))

node('null', (177, 1408, 571, 56), 'hole',
     zh=dict(title='0 – 64 KiB：不映射',
             lines=['空指针解引用落在这里 → SIGSEGV（vm.mmap_min_addr = 65536）'],
             tags=[],
             panel=['地址最低的这一段故意不映射（vm.mmap_min_addr 默认 65536）。空指针解引用，或者空指针加一个不大的偏移（比如通过空指针访问结构体成员），都落在这里，立刻收到 SIGSEGV，而不是悄悄读到垃圾。']))

node('code', (800, 128, 360, 250), 'note', mono=True,
     zh=dict(title='C++ 里写的东西放在哪',
             lines=['int g = 1;             // .data',
                    'int z;                 // .bss',
                    'const char* s = "hi";  // s：.data，"hi"：.rodata',
                    'thread_local int t;    // 每个线程一份（TLS）',
                    'void f() {             // 指令：.text',
                    '  int x = 0;           // 栈',
                    '  int* p = new int(2); // p：栈，*p：堆',
                    '  char* b = new char[1 << 20];',
                    '                       // 1 MiB：mmap 区',
                    '}'],
             tags=[],
             panel=['选上面的“变量放在哪”，一步一步看每一行落在左边哪一段。',
                    '规律是看生命周期：跟着整个程序的（全局、static）在 .data、.bss；编译期就定了的只读数据在 .rodata；跟着函数调用的在栈上；跟着 new、delete 的在堆或 mmap 区；跟着线程的在 TLS。']))

node('thread', (1220, 128, 360, 250), 'note',
     zh=dict(title='线程：共享什么，各有什么',
             lines=['共享：整个地址空间，同一份页表',
                    '（代码、全局变量、堆、mmap 区、文件描述符）',
                    '各一份：栈、TLS、寄存器、内核栈',
                    '所以全局和堆上的数据要同步；',
                    '栈上的变量地址不传出去，就只有自己用'],
             tags=[[('#2 内存序与缓存行', post('zh', 'memory-ordering-false-sharing-dependency-chains'))],
                   [('#18 线程安全队列', post('zh', 'thread-safe-queue'))]],
             panel=['同一个进程的线程共用一个地址空间：页表只有一份，代码、全局变量、堆、mmap 区、打开的文件都共享。',
                    '每个线程自己有：一块栈、一份 TLS、一套寄存器（包括栈指针和 fs），以及进内核时用的内核栈。',
                    '所以两个线程都看得见全局变量和堆上的对象，要用锁或原子操作同步。栈也在同一个地址空间里：把局部变量的地址交给别的线程，它一样能读写，只是函数返回以后那块就失效了。',
                    '进程之间正好相反：页表各一份，默认什么都不共享，要共享得专门把同一批页 mmap 进来。']))

node('pt', (800, 400, 360, 200), 'buf',
     zh=dict(title='页表：虚拟地址 → 物理地址',
             lines=['每个进程一份；4 级，每级用 9 位，页内偏移 12 位',
                    'TLB 命中不额外花时间；没命中查页表约 15–30 ns',
                    '2 MiB 大页少查一级，一项 TLB 管 512 倍的地址'],
             tags=[[('硬件地图：dTLB → 一次 load 走到内存', HW + '#load')],
                   [('#6 2 MiB 大页', post('zh', LAYOUT))],
                   [('速查 2.1 TLB 覆盖范围', ref('zh', 'cpu-memory', 'latency'))]],
             panel=['程序里的地址都是虚拟地址。CPU 每次访存都要把它翻译成物理地址：先查 dTLB，命中就直接得到；没命中，硬件按 4 级页表一级一级查（每级用 9 位地址选一项，最后 12 位是页内偏移），约 15–30 ns，查到的结果填进 TLB。',
                    '页表每个进程一份，切换进程就换一份（换 CR3 寄存器），所以两个进程里同一个虚拟地址可以对应完全不同的物理页。',
                    '4 KiB 的页，一级 TLB 几十项只管得到几百 KiB；2 MiB 大页少查一级，一项就管 2 MiB，经常访问的大块数据放大页，能少很多 TLB 未命中。']))

# physical pages: a fixed scatter of cells coloured by the segment they belong to
_rng = random.Random(7)
_cells = []
_kinds = ['img'] * 8 + ['heap'] * 10 + ['mmap'] * 14 + ['stack'] * 5 + ['kern'] * 9 + ['free'] * 24
_rng.shuffle(_kinds)
for i, k in enumerate(_kinds):
    cx, cy = 1232 + (i % 10) * 34, 520 + (i // 10) * 34
    cls = 'hole' if k == 'free' else k
    _cells.append('<rect x="%d" y="%d" width="28" height="28" rx="3" class="%s"/>' % (cx, cy, cls))
_cells.append('<text x="1232" y="784" class="lab">每格 = 一页物理内存（4 KiB），颜色 = 属于左边哪一段；</text>')
_cells.append('<text x="1232" y="802" class="lab">白格 = 空闲或属于别的进程。同一种颜色的格子并不挨着。</text>')

node('dram', (1220, 400, 360, 440), 'mem', extra=_cells,
     zh=dict(title='物理内存（内存条）',
             lines=['物理页零散地分在内存条上',
                    '连续的虚拟地址，背后的物理页不一定连续',
                    '同一个 .so 的代码页、/dev/shm 的页：几个进程共用'],
             tags=[[('硬件地图：内存控制器 → 通道', HW + '#load')]],
             panel=['页表把每一页虚拟地址映射到某一页物理内存上。物理页是内核从空闲页里拿的，所以虚拟地址连续，背后的物理页往往不连续。',
                    '不同进程可以映射同一页物理内存：同一个 .so 的代码页、同一个程序的 .text、/dev/shm 的共享内存都是这样。fork 之后，父子进程一开始也共用全部物理页，谁先写，内核再给谁复制一份（写时复制）。',
                    '物理地址交给缓存以后的路，就是硬件地图上那条：L1 → L2 → L3 → 内存控制器 → 通道。']))

node('fault', (800, 640, 360, 200), 'buf',
     zh=dict(title='缺页：第一次碰到才给物理页',
             lines=['new、mmap、brk 只拿到虚拟地址，页表里还没有',
                    '第一次写：陷入内核，分一页、清零、填进页表',
                    '约 0.5–2 µs；要读磁盘的（major）几十 µs 到 ms',
                    '地址不在任何映射里，或权限不对 → SIGSEGV'],
             tags=[[('#3 3.2 预先缺页 + mlock', post('zh', ALLOC, '32-预先缺页补上-mlock-在首次访问时留下的口子'))]],
             panel=['Linux 分配内存是“先记账，后给页”：new、mmap、brk 只在进程的映射表里登记一段虚拟地址，页表里还没有对应的物理页。',
                    '第一次写这一页时，CPU 查页表查不到，触发缺页异常，陷入内核。内核确认这个地址属于某个合法的映射，就分一页物理内存、清零（文件映射则从页缓存里找到那一页），填进页表，再回到原来那条指令重新执行。只读不写的匿名页，先映射一个公用的全 0 页，第一次写时才真正分配。',
                    '这种 minor fault 约 0.5–2 µs；要从磁盘读的 major fault 要几十 µs 到毫秒。',
                    '地址不在任何映射里（空指针、野指针、越过栈的保护页），或者权限不对（写 .rodata、写 .text），内核就给进程发 SIGSEGV，这就是段错误。']))

node('errs', (800, 860, 780, 150), 'note',
     zh=dict(title='出了错，落在图上哪里',
             lines=['空指针解引用 → 最低 64 KiB 的不映射区：SIGSEGV',
                    '递归太深、局部数组太大 → 越过栈底的保护页：SIGSEGV',
                    '改字符串字面量 → 写只读的 .rodata：SIGSEGV',
                    '越界、用已经释放的内存 → 多半还落在堆的映射里，不一定立刻崩，要用 ASan 查',
                    '内存泄漏 → 堆或 mmap 区一直涨，RSS 跟着涨；double free → glibc 检查到后 abort'],
             tags=[],
             panel=['段错误（SIGSEGV）的意思是：这次访问的地址不在任何映射里，或者映射的权限不允许。所以空指针、栈溢出、写 .rodata 都会立刻崩，因为它们分别落在不映射区、保护页、只读页上。',
                    '越界和释放后使用（use-after-free）麻烦在于：地址多半还在堆的映射里，权限也对，内核不会拦，程序悄悄读到或写坏别的对象，过很久才在别处崩。编译时加 -fsanitize=address（ASan），每次访问都检查，能在出错的那一行报出来。',
                    '内存泄漏不会崩，只是堆或 mmap 区越长越大，pmap 里看到 RSS 一直涨。double free 是 glibc 的 malloc 在释放时发现这块已经在空闲链表里，主动 abort。']))

node('see', (800, 1030, 780, 150), 'note', mono=True,
     zh=dict(title='在自己机器上看',
             lines=['cat /proc/<pid>/maps    # 每一段的地址范围、权限、来源文件（r-xp 就是 .text）',
                    'pmap -x <pid>           # 每一段实际占了多少物理内存（RSS）',
                    'size a.out              # .text、.data、.bss 各多大',
                    'perf stat -e page-faults,dTLB-load-misses ./a.out   # 缺页、TLB 未命中各几次',
                    'ulimit -s               # 栈上限（KiB）'],
             tags=[],
             panel=['/proc/<pid>/maps 一行一个映射：地址范围、权限（r 读、w 写、x 执行、p 私有、s 共享）、偏移、来源文件。程序自己的几行（r--p、r-xp、r--p、rw-p）依次是 ELF 头、.text、.rodata、.data 加 .bss；[heap]、[stack]、[vdso] 有名字，mmap 来的匿名内存没有名字。',
                    'pmap -x 多给一列 RSS：这一段里真正有物理页的部分。new 了一大块但还没写，虚拟大小涨了，RSS 不涨。',
                    'perf stat 看缺页和 TLB 未命中的次数，用来判断该不该预先缺页、该不该上大页。']))

node('myth', (800, 1200, 780, 150), 'note',
     zh=dict(title='几个常见说法，哪里不对',
             lines=['“堆比栈慢”：访问一样快，都是普通内存；慢在 malloc 耗时不固定，以及对象散开以后局部性差',
                    '“用户空间 3 GB、内核 1 GB”：那是 32 位。64 位上用户空间是低 128 TiB，内核是高 128 TiB',
                    '“全局区空间大”：.data、.bss 的大小链接时就定死了，要能变大的数据放堆上',
                    '“new 了就占内存”：第一次写之前不占物理页，RSS 不涨',
                    '“栈上的变量别的线程碰不到”：地址传过去就能读写，栈也在同一个地址空间里'],
             tags=[],
             panel=['这几条都是把一个结论说过头了。堆和栈是同一种内存，差别在分配方式和局部性；3 GB / 1 GB 是 32 位系统的划分；.data、.bss 的大小在链接时就定了；new 只拿到虚拟地址；线程之间本来就共享整个地址空间，只是各用各的栈。']))

# ---------------------------------------------------------------- lines between boxes
# kind: line = an address being translated, ret = the kernel filling the page table on a fault
EDGES = [
    ('e_space_pt', 'M762,500 L798,500', 'line'),
    ('e_pt_dram', 'M1162,500 L1218,500', 'line'),
    ('e_fault_pt', 'M980,638 L980,602', 'ret'),
]

# (x, y, text-anchor, class, zh)
LABELS = [
    (780, 492, 'middle', 'lab', '虚拟'),
    (780, 518, 'middle', 'lab', '地址'),
    (1190, 492, 'middle', 'lab', '物理地址'),
    (988, 625, 'start', 'labr', '内核填一项'),
]

# address ruler on the left: (y, text)
RULER = [
    (141, '0xffff ffff ffff ffff'),
    (278, '0xffff 8000 0000 0000'),
    (377, '0x0000 7fff ffff ffff'),
    (412, '≈ 0x7ffc …'),
    (628, '≈ 0x7f…'),
    (1330, '≈ 0x55… / 0x56…'),
    (1420, '0x0000 0000 0001 0000'),
    (1462, '0x0'),
]

TEXT = {
    'zh': dict(
        title='进程地图：一个 C++ 程序的虚拟地址空间',
        legend=['左边是一个进程的虚拟地址空间，高地址在上（x86-64、4 级页表、开了 PIE；不按比例）。右边是这些地址怎么落到物理内存上，以及出了错落在哪一段。',
                '蓝字 = 在哪里讲过（#N = 交易系统笔记 #N，速查 = 速查页的小节，硬件地图 = 打开硬件地图上对应的路径）。数字都是量级。',
                '红线 = 缺页时内核往页表里填一项。'],
        hi='高地址', lo='低地址',
        r_user='用户空间（128 TiB）：每个进程一份',
        r_mmap='mmap 区 ↓：从高往低分配，下面四类都在这里',
        r_gap='没映射的空地：堆往上长，mmap 区往下长，中间留得最大',
        footer=['地址范围按 x86-64 Linux 的默认布局；开了 ASLR，栈、mmap 区、堆和程序本身的起点每次运行都随机挪一点。',
                '图随文章更新：讲到 fork、动态链接、IO 时再往上补。']),
}

UI = {
    'zh': dict(page_title='进程地图', lead='点一个框看它放什么、在哪篇讲过；选一条路径，一步一步看变量落在哪、一块内存怎么来的。蓝字可以直接点开对应的文章，“硬件地图”会打开硬件地图上接着走的那条路。',
               other_lang=['硬件地图', HW], static=['静态图', '/images/ref/process-map.zh.svg'],
               ref=['速查页', '/zh/ref/cpp-linux/'], prev='上一步', next='下一步', exit='退出',
               step='第 {i} / {n} 步', panel_empty='点图里的任意一个框。', zoom=['看原尺寸', '适应宽度'], panel_links='在哪里讲过'),
}

# ---------------------------------------------------------------- guided paths
TOURS = [
    ('where', '变量放在哪', '', [
        (['code', 'data'], 'int g = 1;：有初值的全局变量在 .data。这个 1 就存在可执行文件里，启动时映射进来。', ''),
        (['bss'], 'int z;：没写初值的全局变量（初值是 0）在 .bss。文件里只记大小，启动时映射成全 0 的页。', ''),
        (['data', 'rodata'], '"hi" 这个字符串字面量在 .rodata，只读，改它会 SIGSEGV。指针 s 本身是个可写的全局变量，在 .data。', ''),
        (['tstack'], 'thread_local int t;：每个线程各一份，放在那个线程栈顶那头的 TLS 里，访问时用 fs 寄存器加偏移。', ''),
        (['text'], 'f 的机器码在 .text，只读可执行。', ''),
        (['stack'], 'f 里的 x 和 p 在栈上：调用 f 时栈指针往下挪一段，返回时挪回来，分配和释放就是一条加减指令。', ''),
        (['heap'], 'new int(2) 的那 4 个字节在堆上，glibc 从堆里切一小块给它。p 在栈上，p 里存的是堆上的地址。', ''),
        (['bigmalloc'], 'new char[1 << 20] 有 1 MiB，超过 128 KiB 的门槛，glibc 直接 mmap 一块新映射，delete[] 时 munmap 还给内核。', ''),
    ]),
    ('new', 'new 一块内存', '', [
        (['heap'], 'new int[1000] 先进 operator new，再进 malloc。小块从本线程的缓存（tcache）或 arena 里切，不进内核。', ''),
        (['heap', 'bigmalloc'], 'arena 不够了，malloc 调 brk 把堆顶往上推；超过 128 KiB 的大块直接 mmap。这两步都要进内核。', ''),
        (['e_space_pt', 'pt'], '这时拿到的只是虚拟地址：页表里还没有这一页，也还没有物理内存。', ''),
        (['pt', 'e_fault_pt', 'fault'], '第一次写：CPU 查页表查不到，触发缺页，陷入内核。内核分一页物理内存、清零、填进页表，约 0.5–2 µs。', ''),
        (['e_pt_dram', 'dram'], '之后再访问，地址翻译走 TLB，数据走缓存和内存，就是硬件地图上那条 load 的路。', ''),
    ]),
    ('access', '访问一个地址', '', [
        (['heap'], '*p = 5;：p 里存的是一个虚拟地址，指向堆上的某一页。', ''),
        (['e_space_pt', 'pt'], 'CPU 先查 dTLB。命中就直接得到物理地址；没命中，硬件按 4 级页表一级一级查，约 15–30 ns，查到后填进 TLB。', ''),
        (['null', 'rodata', 'fault'], '页表里没有这一项，就缺页。地址在某个合法映射里（比如刚 new 的堆），内核补一页；不在任何映射里（空指针），或者权限不对（写 .rodata），内核发 SIGSEGV。', ''),
        (['e_pt_dram', 'dram'], '有了物理地址，后面就是硬件地图上的路：L1 → L2 → L3 → 内存。', ''),
    ]),
    ('thread', '起一个线程', '', [
        (['thread', 'tstack'], 'std::thread 底下调 pthread_create，先给新线程 mmap 一块栈，默认 8 MiB，最低处留一页保护页。', ''),
        (['tstack'], '线程控制块和 TLS 放在这块栈的最高处，新线程的 fs 寄存器指着这里。', ''),
        (['text', 'data', 'bss', 'heap', 'libs', 'filemap', 'thread'], '代码、全局变量、堆、其他映射都和原来的线程共享：页表是同一份。', ''),
        (['thread'], '所以 g 和堆上的对象两个线程都看得见，要同步；栈上的局部变量只要不把地址传出去，就只有自己用。', ''),
    ]),
    ('start', '程序启动', '', [
        (['kernel', 'text', 'rodata', 'data', 'bss'], 'execve 进内核：丢掉旧的映射，按 ELF 文件头把 .text、.rodata、.data 映射进来，.bss 映射成全 0 的页。', ''),
        (['stack', 'vdso'], '内核在用户空间顶上建好主线程的栈，放进 argv 和环境变量，再映射 vDSO。', ''),
        (['libs'], '跳到动态链接器 ld.so：它把 libstdc++、libc 这些 .so 映射进 mmap 区，填好 GOT，再把 .data.rel.ro 改成只读。', ''),
        (['heap'], '全局对象的构造函数跑完，才进 main。这时堆几乎是空的，第一次 malloc 才开始长。', ''),
    ]),
]

SVG_STYLE = '''
      .t  { font-size: 15px; font-weight: 600; fill: #1f2328; }
      .s  { font-size: 12px; fill: #57606a; }
      .h  { font-size: 17px; font-weight: 700; fill: #1f2328; }
      .tag{ font-size: 12px; fill: #0969da; }
      .lab{ font-size: 11.5px; fill: #57606a; }
      .labr{ font-size: 11.5px; fill: #cf222e; }
      .lane-h { font-size: 13px; font-weight: 700; }
      .code { font-size: 12px; fill: #1f2328; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre; }
      .addr { font-size: 11px; fill: #57606a; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
      .kern  { fill: #eaeef2; stroke: #57606a; stroke-width: 1.2; }
      .hole  { fill: #ffffff; stroke: #8c959f; stroke-width: 1; stroke-dasharray: 4 3; }
      .stack { fill: #eefbf1; stroke: #1a7f37; stroke-width: 1.3; }
      .mmap  { fill: #ddf4ff; stroke: #54aeff; stroke-width: 1.2; }
      .heap  { fill: #fff1e5; stroke: #fb8f44; stroke-width: 1.2; }
      .img   { fill: #fbefff; stroke: #c297ff; stroke-width: 1.2; }
      .buf   { fill: #fff8c5; stroke: #d4a72c; stroke-width: 1.2; }
      .mem   { fill: #ffebe9; stroke: #ff8182; stroke-width: 1.2; }
      .note  { fill: #fbfbfc; stroke: #8c959f; stroke-width: 1; }
      .user  { fill: #ffffff; stroke: #1f2328; stroke-width: 2; }
      .line { stroke: #555; stroke-width: 1.6; fill: none; }
      .ret  { stroke: #cf222e; stroke-width: 1.6; fill: none; }'''

MARKERS = {'line': 'arr', 'ret': 'arrR'}
WARNINGS = []


def esc(s):
    return html.escape(s, quote=True)


def text_w(s, size, bold=False):
    """Rough width estimate: CJK and full-width characters are one em, Latin about half."""
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o >= 0x2E80 or ch in '“”—…':
            w += size
        elif ch in 'mwMW@':
            w += size * 0.85
        elif ch in 'il.,:;|!\'()[] ':
            w += size * 0.32
        elif ch.isupper() or ch.isdigit():
            w += size * 0.62
        else:
            w += size * 0.55
    return w * (1.06 if bold else 1.0)


def check(label, s, size, room, bold=False):
    if text_w(s, size, bold) > room:
        WARNINGS.append('%s: "%s" is about %d px, room %d px' % (label, s, text_w(s, size, bold), room))


def tag_text(x, y, segs):
    inner = ''
    for txt, url in segs:
        if url:
            inner += '<a href="%s" target="_blank" rel="noopener"><tspan>%s</tspan></a>' % (esc(url), esc(txt))
        else:
            inner += '<tspan>%s</tspan>' % esc(txt)
    return '<text x="%d" y="%d" class="tag">%s</text>' % (x, y, inner)


def svg(lang, interactive):
    T = TEXT[lang]
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="%s">' % (W, H, W, H, FONT),
         '  <defs>']
    for mid, color in (('arr', '#555'), ('arrR', '#cf222e')):
        o.append('    <marker id="%s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' % mid)
        o.append('      <path d="M0,0 L10,5 L0,10 z" fill="%s"/>' % color)
        o.append('    </marker>')
    o.append('    <style>' + SVG_STYLE + '\n    </style>')
    o.append('  </defs>')
    o.append('  <rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('  <text x="20" y="38" class="h" style="font-size:23px">%s</text>' % esc(T['title']))
    for i, line in enumerate(T['legend']):
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (62 + 20 * i, esc(line)))
        check('legend', line, 12, W - 40)

    # address ruler
    o.append('  <text x="155" y="122" class="lab" text-anchor="end">%s ↑</text>' % esc(T['hi']))
    o.append('  <text x="155" y="1492" class="lab" text-anchor="end">%s ↓</text>' % esc(T['lo']))
    for y, s in RULER:
        o.append('  <text x="155" y="%d" class="addr" text-anchor="end">%s</text>' % (y, esc(s)))

    # regions
    o.append('  <rect x="165" y="362" width="595" height="1114" rx="10" class="user"/>')
    o.append('  <text x="177" y="386" class="h">%s</text>' % esc(T['r_user']))
    o.append('  <rect x="177" y="580" width="571" height="324" rx="8" fill="#f3f9ff" stroke="#54aeff" stroke-dasharray="6 4"/>')
    o.append('  <text x="189" y="602" class="lane-h" style="fill:#0969da">%s</text>' % esc(T['r_mmap']))
    o.append('  <rect x="177" y="912" width="571" height="56" rx="8" class="hole"/>')
    o.append('  <text x="462" y="945" class="lab" text-anchor="middle">%s</text>' % esc(T['r_gap']))

    # boxes
    for nid, n in NODES.items():
        x, y, w, h = n['box']
        d = n[lang]
        if interactive:
            o.append('  <g id="%s" class="node" tabindex="0" role="button" aria-label="%s">' % (nid, esc(d['title'])))
        else:
            o.append('  <g id="%s">' % nid)
        o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="6" class="%s"/>' % (x, y, w, h, n['cls']))
        yy = y + 24
        o.append('  <text x="%d" y="%d" class="t">%s</text>' % (x + 12, yy, esc(d['title'])))
        check('%s/%s title' % (lang, nid), d['title'], 15, w - 24, True)
        for line in d['lines']:
            yy += 18
            o.append('  <text x="%d" y="%d" class="%s">%s</text>' % (x + 12, yy, 'code' if n['mono'] else 's', esc(line)))
            check('%s/%s' % (lang, nid), line, 12, w - 24)
        for segs in d['tags']:
            yy += 18
            o.append('  ' + tag_text(x + 12, yy, segs))
            check('%s/%s tag' % (lang, nid), ''.join(t for t, _ in segs), 12, w - 24)
        if yy + 10 > y + h:
            WARNINGS.append('%s/%s: text runs to y=%d, box ends at y=%d' % (lang, nid, yy + 10, y + h))
        for e in n['extra']:
            o.append('  ' + e)
        o.append('  </g>')

    # lines and labels
    for eid, path, kind in EDGES:
        o.append('  <path d="%s" class="%s edge" id="%s" marker-end="url(#%s)"/>' % (path, kind, eid, MARKERS[kind]))
    for x, y, anchor, cls, zh in LABELS:
        o.append('  <text x="%d" y="%d" class="%s" text-anchor="%s">%s</text>' % (x, y, cls, anchor, esc(zh)))

    for i, line in enumerate(T['footer']):
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (1515 + 20 * i, esc(line)))
    o.append('</svg>')
    return '\n'.join(o)


PAGE_CSS = '''
:root { --bg:#f6f7f9; --card:#ffffff; --fg:#1f2328; --muted:#57606a; --line:#d0d7de; --accent:#0969da; --hl:#bf3989; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#1c1a19; --card:#26231f; --fg:#ece6df; --muted:#b3aaa0; --line:#463f38; --accent:#e9a0b4; --hl:#ff7bb0; } }
:root[data-theme="dark"] { --bg:#1c1a19; --card:#26231f; --fg:#ece6df; --muted:#b3aaa0; --line:#463f38; --accent:#e9a0b4; --hl:#ff7bb0; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font: 15px/1.6 PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif; -webkit-tap-highlight-color: transparent; }
header { padding: 14px 16px 10px; display:flex; flex-wrap:wrap; gap:8px 16px; align-items:baseline; }
h1 { font-size: 22px; margin: 0; }
header .lead { flex: 1 1 420px; margin:0; color:var(--muted); font-size:14px; }
header nav { display:flex; gap:12px; font-size:14px; }
a { color: var(--accent); }
.tours { display:flex; flex-wrap:wrap; gap:8px; padding: 0 16px 10px; }
.tours button, .stepbar button { font: inherit; font-size:14px; padding: 5px 12px; border-radius: 999px; border:1px solid var(--line); background:var(--card); color:var(--fg); cursor:pointer; }
.tours button[aria-pressed="true"] { border-color: var(--hl); color: var(--hl); }
.tours .zoom { margin-left: auto; }
.map.full svg { width: 1600px; max-width: none; }
.layout { display:grid; grid-template-columns: minmax(0,1fr) 340px; gap: 12px; padding: 0 16px 16px; align-items:start; }
.map { background:#ffffff; border:1px solid var(--line); border-radius:10px; overflow:auto; max-height: calc(100vh - 140px); }
.map svg { display:block; width:100%; height:auto; min-width: 1000px; }
.side { position: sticky; top: 12px; display:flex; flex-direction:column; gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding: 12px 14px; }
.card h2 { font-size:17px; margin:0 0 6px; }
.card p { margin: 4px 0; color: var(--muted); font-size:14px; }
.card h3 { font-size:13px; margin:10px 0 4px; color:var(--muted); font-weight:600; }
.card ul { margin:0; padding-left: 18px; font-size:14px; }
.stepbar { display:none; }
.stepbar.on { display:block; }
.stepbar .count { font-size:13px; color:var(--muted); }
.stepbar .cap { margin: 6px 0 10px; font-size:15px; color:var(--fg); }
.stepbar .btns { display:flex; gap:8px; }
.node { cursor:pointer; outline:none; }
.node:hover > rect:first-of-type, .node:focus-visible > rect:first-of-type { stroke:#bf3989; stroke-width:2.5; }
.node.sel > rect:first-of-type { stroke:#bf3989; stroke-width:3; }
svg .tag a tspan { text-decoration: underline; text-decoration-color: rgba(9,105,218,.35); }
svg .tag a:hover tspan { fill:#bf3989; }
svg.dim .node, svg.dim .edge { opacity:.18; transition: opacity .25s; }
svg.dim .node.on, svg.dim .edge.on { opacity:1; }
svg .edge.on { stroke:#bf3989; stroke-width:3; }
svg.dim .node.on > rect:first-of-type { stroke:#bf3989; stroke-width:3; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .side { position: static; order: -1; }
  .map { max-height: 70vh; }
}
@media (prefers-reduced-motion: reduce) { svg.dim .node, svg.dim .edge { transition:none; } }
'''

PAGE_JS = r'''
const svg = document.querySelector('.map svg');
const panel = document.getElementById('panel');
const bar = document.getElementById('stepbar');
let tour = null, step = 0;
function esc(s){ return s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function show(id){
  svg.querySelectorAll('.node.sel').forEach(n => n.classList.remove('sel'));
  const n = DATA.nodes[id]; if (!n) return;
  document.getElementById(id).classList.add('sel');
  let h = '<h2>' + esc(n.title) + '</h2>' + n.lines.map(l => '<p>' + esc(l) + '</p>').join('');
  const links = [];
  n.tags.forEach(line => line.forEach(([txt, url]) => { if (url) links.push('<li><a href="' + url + '" target="_blank" rel="noopener">' + esc(txt.replace(/^ · /, '')) + '</a></li>'); }));
  if (links.length) h += '<h3>' + esc(DATA.ui.panel_links) + '</h3><ul>' + links.join('') + '</ul>';
  panel.innerHTML = h;
}
svg.querySelectorAll('.node').forEach(g => {
  g.addEventListener('click', e => { if (e.target.closest('a')) return; show(g.id); });
  g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(g.id); } });
});
function render(){
  svg.querySelectorAll('.on').forEach(x => x.classList.remove('on'));
  document.querySelectorAll('.tours button[data-k]').forEach(b => b.setAttribute('aria-pressed', b.dataset.k === tour ? 'true' : 'false'));
  if (!tour) { svg.classList.remove('dim'); bar.classList.remove('on'); return; }
  const steps = DATA.ui.tours[tour][1];
  svg.classList.add('dim'); bar.classList.add('on');
  for (let i = 0; i <= step; i++) steps[i][0].forEach(id => { const el = document.getElementById(id); if (el) el.classList.add('on'); });
  bar.querySelector('.count').textContent = DATA.ui.step.replace('{i}', step + 1).replace('{n}', steps.length);
  bar.querySelector('.cap').textContent = steps[step][1];
  bar.querySelector('.prev').disabled = step === 0;
  bar.querySelector('.next').disabled = step === steps.length - 1;
  const last = steps[step][0].map(id => document.getElementById(id)).filter(el => el && el.classList.contains('node')).pop();
  if (last) { show(last.id); last.scrollIntoView({block:'nearest', inline:'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}); }
}
document.querySelector('.tours .zoom').addEventListener('click', e => {
  const on = document.querySelector('.map').classList.toggle('full');
  e.currentTarget.setAttribute('aria-pressed', on ? 'true' : 'false');
  e.currentTarget.textContent = on ? DATA.ui.zoom[1] : DATA.ui.zoom[0];
});
document.querySelectorAll('.tours button[data-k]').forEach(b => b.addEventListener('click', () => { tour = tour === b.dataset.k ? null : b.dataset.k; step = 0; render(); }));
bar.querySelector('.prev').addEventListener('click', () => { step--; render(); });
bar.querySelector('.next').addEventListener('click', () => { step++; render(); });
bar.querySelector('.exit').addEventListener('click', () => { tour = null; render(); });
document.addEventListener('keydown', e => {
  if (!tour) return;
  const n = DATA.ui.tours[tour][1].length;
  if (e.key === 'ArrowRight' && step < n - 1) { step++; render(); }
  if (e.key === 'ArrowLeft' && step > 0) { step--; render(); }
  if (e.key === 'Escape') { tour = null; render(); }
});
const h = location.hash.slice(1);
if (DATA.ui.tours[h]) { tour = h; step = 0; render(); }
try { const t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
'''


def page(lang):
    u = UI[lang]
    data = {'nodes': {}, 'ui': dict(u)}
    for nid, n in NODES.items():
        d = n[lang]
        data['nodes'][nid] = {'title': d['title'], 'lines': d['panel'], 'tags': [[list(seg) for seg in segs] for segs in d['tags']]}
    data['ui']['tours'] = {}
    ids = set(NODES) | {e[0] for e in EDGES}
    for key, zh, en, steps in TOURS:
        out = []
        for idlist, czh, cen in steps:
            for i in idlist:
                if i not in ids:
                    WARNINGS.append('tour %s refers to unknown id %s' % (key, i))
            out.append([idlist, czh if lang == 'zh' else cen])
        data['ui']['tours'][key] = [zh if lang == 'zh' else en, out]
    buttons = ''.join('<button type="button" data-k="%s" aria-pressed="false">%s</button>' % (k, esc(zh if lang == 'zh' else en))
                      for k, zh, en, _ in TOURS)
    js_data = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    return '\n'.join([
        '<!doctype html>',
        '<html lang="%s">' % ('zh-CN' if lang == 'zh' else 'en'),
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>%s</title>' % esc(u['page_title']),
        '<link rel="icon" href="/images/logo.svg?v=20261008-rounded-brain-1">',
        '<style>' + PAGE_CSS + '</style>',
        '</head>',
        '<body>',
        '<header>',
        '<h1>%s</h1>' % esc(u['page_title']),
        '<p class="lead">%s</p>' % esc(u['lead']),
        '<nav><a href="%s">%s</a><a href="%s">%s</a><a href="%s">%s</a></nav>' % (
            u['other_lang'][1], esc(u['other_lang'][0]), u['ref'][1], esc(u['ref'][0]), u['static'][1], esc(u['static'][0])),
        '</header>',
        '<div class="tours">%s<button type="button" class="zoom" aria-pressed="false">%s</button></div>' % (buttons, esc(u['zoom'][0])),
        '<div class="layout">',
        '<div class="map">',
        svg(lang, True),
        '</div>',
        '<aside class="side">',
        '<div class="card stepbar" id="stepbar"><div class="count"></div><div class="cap"></div><div class="btns">'
        '<button type="button" class="prev">%s</button><button type="button" class="next">%s</button><button type="button" class="exit">%s</button></div></div>' % (
            esc(u['prev']), esc(u['next']), esc(u['exit'])),
        '<div class="card" id="panel"><p>%s</p></div>' % esc(u['panel_empty']),
        '</aside>',
        '</div>',
        '<script>',
        'const DATA = %s;' % js_data,
        PAGE_JS.strip('\n'),
        '</script>',
        '</body>',
        '</html>',
    ])


def write(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(text + '\n')
    os.replace(tmp, path)  # write-then-rename, so a running hugo server never reads half a file
    print('wrote', rel)


def main():
    for lang in LANGS:
        write('static/images/ref/process-map.%s.svg' % lang, svg(lang, False))
        write('static/maps/process-map.%s.html' % lang, page(lang))
    for w in sorted(set(WARNINGS)):
        print('WARN', w)


if __name__ == '__main__':
    main()
