#!/usr/bin/env python3
"""Build map for the reference page (/zh/ref/cpp-linux/#build): from source files to a running process.

One data definition below generates:
  static/images/ref/build-map.zh.svg   the static map shown on the page
  static/maps/build-map.zh.html        the interactive map (click a box, step through a path)

To change the map, edit NODES / EDGES / LABELS / TOURS and run from the repo root:
  python -X utf8 tools/build-map/gen_build_map.py
It prints a warning for every line of text that looks wider than its box.
Chinese only for now; the English version follows once the layout is settled.
The drawing and page code below the data is shared with tools/io-map/gen_io_map.py.
"""
import html
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
W, H = 1600, 960
FONT = 'PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif'
LANGS = ('zh',)
PM = '/maps/process-map.zh.html'
FORK = '/zh/posts/process-thread-fork/'


# ---------------------------------------------------------------- boxes
# cls: art = a file (source, .o, library, executable), step = a build step, run = load and run time,
# user = the process, note = explanation.
NODES = {}


def node(nid, box, cls, zh, mono=False, extra=None):
    NODES[nid] = dict(box=box, cls=cls, zh=zh, mono=mono, extra=extra or [])


node('src', (40, 150, 250, 170), 'art',
     zh=dict(title='源文件和头文件',
             lines=['a.cpp、b.cpp：各自单独编译', 'a.h：放声明，被 #include 进去', '一个 .cpp 加上它 include 的', '全部内容 = 一个翻译单元', '编译器一次只看一个翻译单元，', '不知道别的 .cpp 里写了什么'],
             tags=[],
             panel=['C++ 按翻译单元编译：一个 .cpp 文件，加上它 #include 进来的全部头文件，展开以后就是一个翻译单元。编译器一次只处理一个，看不到别的 .cpp 里写了什么。',
                    '所以 a.cpp 要调 b.cpp 里的函数 g，只能先看到 g 的声明（一般放在头文件里）。编译 a.cpp 时只留一个“这里要调 g”的记号，g 的地址等链接时再填。']))

node('pp', (320, 150, 250, 170), 'step',
     zh=dict(title='① 预处理：g++ -E',
             lines=['#include：把头文件原样粘进来', '#define：宏按文本替换', '#if、#ifdef：删掉不要的分支', '产物 a.ii：纯 C++ 文本，', '常常有几万行'],
             tags=[],
             panel=['预处理只做文本替换，不懂 C++ 语法：#include 把整个头文件的内容粘到这一行，宏按文本展开，#if 删掉条件不成立的代码。',
                    '只 include 了 <iostream> 的小文件，预处理后就有几万行。每个 .cpp 都要把同样的头文件再处理一遍，这是 C++ 编译慢的主要原因之一，预编译头和 C++20 的模块就是来省这一步的。',
                    'include 防护（#pragma once 或 #ifndef）防的是同一个翻译单元里把同一个头文件粘两遍，管不到别的翻译单元。']))

node('cc', (600, 150, 260, 170), 'step',
     zh=dict(title='② 编译：g++ -S',
             lines=['语法、类型检查：编译错误多在这', '模板在这里按具体类型实例化', '优化：内联、常量传播……', '名字修饰：f(int) → _Z1fi', '产物 a.s：汇编文本'],
             tags=[],
             panel=['编译器把一个翻译单元翻译成汇编：检查语法和类型，大部分编译错误在这一步报出来；用到的模板在这里按具体类型实例化；-O2 的优化（内联、常量传播、循环变换）也在这一步做。',
                    'C++ 允许重载，同名函数要靠参数区分，所以编译器把参数类型编进符号名，叫名字修饰（name mangling）：f(int) 变成 _Z1fi，f(double) 变成 _Z1fd，c++filt 能还原回来。',
                    'C 没有名字修饰。C++ 里调 C 写的函数，要用 extern "C" 声明，不然链接时找的是修饰过的名字，对不上。']))

node('as', (890, 150, 240, 170), 'step',
     zh=dict(title='③ 汇编：g++ -c',
             lines=['汇编指令 → 机器码', '产物 a.o：可重定位目标文件', '地址还没定：调别的文件里的', '函数，地址先填 0，', '旁边记一条重定位项'],
             tags=[],
             panel=['汇编器把汇编文本翻成机器码，输出 ELF 格式的可重定位目标文件 a.o。',
                    '这时每个函数、变量最终放在哪个地址还不知道。调另一个文件里的函数 g，call 指令里的地址先填 0，旁边记一条重定位项（relocation）：这 4 个字节将来要填 g 的地址。']))

node('obj', (1160, 150, 400, 170), 'art',
     zh=dict(title='a.o 里有什么（nm、readelf）',
             lines=['段：.text 机器码，.data，.bss，.rodata',
                    '符号表：T f = 这里定义了 f',
                    '        U g = 用了 g，定义不在这里',
                    '重定位表：.text+0x1c 处要填 g 的地址',
                    '每个 .o 都从地址 0 排起，互相不知道对方'],
             tags=[[('进程地图：这些段最后落在哪', PM)]],
             panel=['目标文件里有三样东西：各段的内容（.text 机器码、.data 有初值的全局变量、.bss 只记大小、.rodata 常量和字符串字面量）；符号表，列出这个文件定义了哪些名字、又用了哪些没定义的名字；重定位表，记着哪些位置要等链接时填地址。',
                    'nm a.o 看符号表：T 是定义在 .text 里的函数，D、B 是 .data、.bss 里的变量，U 是只用了、没定义的。readelf -r a.o 看重定位项。']))

node('staticlib', (40, 400, 300, 100), 'art',
     zh=dict(title='静态库 libx.a',
             lines=['一堆 .o 打成的包（ar）', '链接器只挑用得上的 .o，', '把代码拷进可执行文件'],
             tags=[],
             panel=['静态库是用 ar 把一组 .o 打成的包。链接时，链接器只从里面挑出能解决当前未定义符号的那几个 .o，把它们的段拷进可执行文件，和你自己的 .o 一样处理。',
                    '拷进去以后，可执行文件不再依赖这个库，拷到别的机器上也能跑；代价是体积大，库更新了要重新链接，十个程序用同一个静态库，内存里就有十份代码。',
                    'GNU ld 按命令行顺序扫，扫到一个库时只用它解决“到目前为止”还没定义的符号。所以 -lx 要写在用到它的文件后面：g++ main.o -lx 可以，g++ -lx main.o 会报 undefined reference。']))

node('so', (40, 520, 300, 100), 'art',
     zh=dict(title='动态库 libc.so.6',
             lines=['链接时只检查符号在不在，', '记下“运行时要 libc.so.6”，', '代码不拷进来'],
             tags=[],
             panel=['链接时，链接器检查动态库里确实有你要的符号，然后只在可执行文件里记一笔：运行时需要 libc.so.6（DT_NEEDED），代码一个字节都不拷。',
                    '运行时由动态链接器把它 mmap 进进程。代码段只读，所有用它的进程共享同一份物理页；库升级也不用重新链接程序。代价是启动时要找库、做重定位，调库函数要多经过一次 PLT 跳转。',
                    '动态库要编译成位置无关代码（-fPIC）：每个进程把它映射在不同的地址，代码里不能写死绝对地址。']))

node('ld', (390, 400, 420, 220), 'step',
     zh=dict(title='④ 链接：ld（g++ 最后一步替你调）',
             lines=['1. 符号解析：每个 U 都要找到唯一的定义',
                    '   一个都没有 → undefined reference',
                    '   有两个 → multiple definition',
                    '2. 合并：各个 .o 的 .text 拼成一个 .text，',
                    '   .data、.bss 同理；定下每个段、',
                    '   每个符号的最终地址',
                    '3. 重定位：按重定位项把地址填进去',
                    '产物：可执行文件，或者一个 .so'],
             tags=[],
             panel=['链接器做三件事。第一是符号解析：把所有 .o 和库的符号表放在一起，每个被引用（U）的名字都要找到恰好一个定义；一个都没有就是 undefined reference，有两个就是 multiple definition。',
                    '第二是合并、分配地址：各个 .o 的 .text 拼成一个 .text，.data 拼成一个 .data……再给每个段定起始地址，每个符号的地址也就定了。PIE 可执行文件（现在 g++ 的默认）定的是相对地址，加载时整体加一个随机基址（ASLR）。',
                    '第三是重定位：按各个 .o 里记的重定位项，把 call、取全局变量地址这些指令里先填的 0 改成真实的地址或相对偏移。']))

node('exe', (860, 400, 400, 220), 'art',
     zh=dict(title='可执行文件 a.out（readelf -l）',
             lines=['ELF 头：入口地址 _start',
                    '程序头：加载时每一段 mmap 到哪',
                    '  LOAD r-x：.text',
                    '  LOAD r--：.rodata、.eh_frame',
                    '  LOAD rw-：.data、.bss（.bss 只记大小）',
                    'INTERP：/lib64/ld-linux-x86-64.so.2',
                    'DYNAMIC：需要 libc.so.6……',
                    '.plt、.got：调 .so 里函数的跳板'],
             tags=[[('进程地图：.text、.data、.bss', PM)]],
             panel=['可执行文件也是 ELF，但多了程序头。它不按 .text、.data 这些节来描述，而是告诉内核：文件里的这一段，按什么权限映射到哪个地址。通常是三四个 LOAD 段：可读可执行的代码、只读的常量、可读写的数据。',
                    '.bss 在文件里不占空间，只记一个大小，加载时由内核映射全零的页。所以没有初值的大全局数组不会让可执行文件变大。',
                    '动态链接的程序还有 INTERP（由谁来做动态链接）和 DYNAMIC（需要哪些 .so、动态符号表在哪）。']))

node('errs', (1290, 400, 270, 220), 'note',
     zh=dict(title='链接报错，多半是这几种',
             lines=['undefined reference to f：',
                    ' · 只声明没定义，或那个 .cpp',
                    '   没参与链接',
                    ' · 少了 -l，或 -l 写在了前面',
                    ' · 模板的定义写在 .cpp 里',
                    ' · C 函数没加 extern "C"',
                    'multiple definition of x：',
                    ' · 头文件里定义了普通函数或变量',
                    '可以多处定义：inline、模板'],
             tags=[],
             panel=['undefined reference 是链接器在说：有人用了这个名字，可所有参与链接的文件里都没有它的定义。最常见的原因：函数只声明没写实现，或者写实现的那个 .cpp 没加进编译命令；库没加 -l，或者写在了用它的文件前面；模板的定义放在 .cpp 里，别的翻译单元看不到定义，没法实例化；C 写的函数在 C++ 里没用 extern "C" 声明，名字修饰对不上。',
                    'multiple definition 是同一个名字有两个定义，典型是在头文件里定义了普通函数或全局变量，又被两个 .cpp include 了。',
                    'ODR（一处定义规则）：普通函数和变量在整个程序里只能定义一次；inline 函数、inline 变量、模板可以在多个翻译单元里各定义一次，但每一份必须一模一样，链接器只留一份。static 和匿名命名空间里的名字只在本翻译单元可见，每个翻译单元各有一份，互不冲突。']))

node('procmap', (40, 700, 330, 170), 'user',
     zh=dict(title='落到进程地图上',
             lines=['.text → 代码段（r-x）', '.rodata → 只读数据（r--）', '.data、.bss → 读写数据（rw-）', 'libc.so、ld.so → mmap 区', '栈：内核放好 argv、环境变量'],
             tags=[[('进程地图', PM)]],
             panel=['加载完以后，可执行文件的几个 LOAD 段就是进程地图最下面那几段；.so 的各段落在 mmap 区；栈顶由内核放好 argc、argv、环境变量和辅助向量（auxv）。',
                    'cat /proc/<pid>/maps 能看到每一段对应哪个文件、什么权限。']))

node('ldso', (410, 700, 370, 170), 'run',
     zh=dict(title='⑥ 动态链接器 ld.so',
             lines=['按 DT_NEEDED 找 .so：rpath、', 'LD_LIBRARY_PATH、/etc/ld.so.cache', '找到的库 mmap 进来，做重定位', '跑全局对象的构造函数', '最后跳到 _start，由它调 main'],
             tags=[],
             panel=['动态链接的程序，内核先把控制权交给 INTERP 里写的动态链接器 ld.so。它按 DYNAMIC 段里的 DT_NEEDED 找库：先看 rpath/runpath 和环境变量 LD_LIBRARY_PATH，再查 /etc/ld.so.cache 和默认目录；找不到就报 error while loading shared libraries，程序的 main 根本没开始跑。',
                    '找到的库 mmap 进 mmap 区，再做重定位，把 GOT 里的地址填好。然后依次运行各个库和程序的初始化代码，C++ 全局对象的构造函数就在这时跑。最后跳到程序入口 _start，由它调 main。',
                    'ldd a.out 列出会加载哪些库、各在哪个路径。']))

node('exec', (820, 700, 330, 170), 'run',
     zh=dict(title='⑤ execve("./a.out")',
             lines=['内核读 ELF 头和程序头', '按 LOAD 段 mmap，建好栈', '有 INTERP：把 ld.so 也映射进来，', '先从 ld.so 开始跑', '静态链接的：直接从 _start 开始'],
             tags=[[('进程和线程：fork 和 exec', FORK)]],
             panel=['shell 里敲 ./a.out，就是 fork 出一个子进程，子进程再调 execve。内核丢掉它原来的地址空间，读新文件的 ELF 头和程序头，按每个 LOAD 段的权限把文件 mmap 进来，再建好栈。mmap 这时并不读盘，第一次访问某一页时缺页，才从页缓存或磁盘读进来。',
                    '如果有 INTERP 段，内核把动态链接器也映射进来，先从它的入口开始执行；静态链接的程序没有 INTERP，直接从 _start 开始。']))

node('plt', (1190, 700, 370, 170), 'run',
     zh=dict(title='⑦ 调 .so 里的函数：PLT 和 GOT',
             lines=['call printf@plt：先跳到 PLT 的跳板', '跳板去 GOT 里取真实地址，再跳过去', '延迟绑定：第一次取到的是解析函数，', '解析完把 printf 的地址写回 GOT', '-z now：启动时全填好，再设只读'],
             tags=[],
             panel=['可执行文件链接时不知道 printf 会被加载到哪，所以 call 的不是 printf，而是本文件 PLT 里的一个小跳板 printf@plt。跳板只做一件事：从 GOT（全局偏移表）对应的表项里取一个地址，跳过去。',
                    'GOT 在可写的数据段里，由动态链接器往里填真实地址。默认是延迟绑定：表项一开始指向解析函数，第一次调用时才去找 printf、把地址写回 GOT，之后再调就直接跳到 printf。',
                    '链接时加 -z now -z relro（full RELRO），启动时就把所有表项填好，再把 GOT 设成只读：启动慢一点，但之后没有第一次调用的额外开销，GOT 也没法被缓冲区溢出改写。']))

# ---------------------------------------------------------------- lines between boxes
# kind: ctl = the next step, cpy = code copied into the output, ref = only a name recorded, map = mmap at load time
EDGES = [
    ('e_src_pp', 'M290,235 L318,235', 'ctl'),
    ('e_pp_cc', 'M570,235 L598,235', 'ctl'),
    ('e_cc_as', 'M860,235 L888,235', 'ctl'),
    ('e_as_obj', 'M1130,235 L1158,235', 'ctl'),
    ('e_obj_ld', 'M1360,320 L1360,350 L600,350 L600,398', 'ctl'),
    ('e_lib_ld', 'M340,450 L388,450', 'cpy'),
    ('e_so_ld', 'M340,570 L388,570', 'ref'),
    ('e_ld_exe', 'M810,510 L858,510', 'ctl'),
    ('e_exe_exec', 'M985,620 L985,698', 'ctl'),
    ('e_exe_plt', 'M1230,620 L1230,698', 'ctl'),
    ('e_exec_ldso', 'M820,785 L782,785', 'ctl'),
    ('e_so_ldso', 'M300,620 L300,650 L595,650 L595,698', 'map'),
    ('e_ldso_pm', 'M410,785 L372,785', 'map'),
]

# (x, y, text-anchor, class, zh)
LABELS = [
    (1000, 343, 'start', 'lab', '所有 .o 一起交给链接器'),
    (364, 442, 'middle', 'labc', '拷进来'),
    (364, 562, 'middle', 'labd', '只记名字'),
    (993, 652, 'start', 'lab', './a.out'),
    (1238, 652, 'start', 'lab', '运行时调库函数'),
    (801, 777, 'middle', 'lab', '跳过去'),
    (391, 777, 'middle', 'labm', 'mmap'),
    (604, 684, 'start', 'labm', '运行时 mmap 进来，进程间共享'),
]

REGIONS = [
    # (y, height, fill, stroke, label color, TEXT key)
    (112, 228, '#fbf7ff', '#c297ff', '#8250df', 'r_build'),
    (360, 280, '#fffdf2', '#d4a72c', '#9a6700', 'r_link'),
    (660, 250, '#fff8f7', '#ff8182', '#cf222e', 'r_run'),
]

TEXT = {
    'zh': dict(
        title='从源码到进程：编译、链接、加载',
        legend=['上面是编译：每个 .cpp 各自变成一个 .o。中间是链接：所有 .o 和库拼成一个可执行文件。下面是运行：内核和动态链接器把它变成进程地图上的那几段。',
                '橙线 = 代码拷进输出文件；蓝色虚线 = 只记一个名字，运行时再找；绿色虚线 = 加载时 mmap 进地址空间；灰线 = 下一步。',
                '蓝字 = 在哪里讲过，进程地图会打开对应的那张图。'],
        r_build='编译：一次一个翻译单元', r_link='链接：把所有 .o 和库拼成一个文件', r_run='加载和运行',
        footer=['图随文章更新：讲到模板实例化、内联和链接时优化（LTO）时再往上补。']),
}

UI = {
    'zh': dict(page_title='从源码到进程', lead='点一个框看它做什么、在哪篇讲过；选一条路径，一步一步看一个 .cpp 怎么变成 .o、链接时报的错从哪来、./a.out 之后发生了什么。蓝字可以直接点开对应的文章或地图。',
               other_lang=['进程地图', PM], static=['静态图', '/images/ref/build-map.zh.svg'],
               ref=['速查页', '/zh/ref/cpp-linux/#build'], prev='上一步', next='下一步', exit='退出',
               step='第 {i} / {n} 步', panel_empty='点图里的任意一个框。', zoom=['看原尺寸', '适应宽度'], panel_links='在哪里讲过'),
}

# ---------------------------------------------------------------- guided paths
TOURS = [
    ('compile', '一个 .cpp 变成 .o', '', [
        (['src'], 'a.cpp 调了 b.cpp 里的 g，只 include 了 b.h 里 g 的声明。编译器一次只看 a.cpp 这一个翻译单元。', ''),
        (['e_src_pp', 'pp'], '预处理：把 b.h 的内容原样粘进来，宏展开，得到一个只剩纯 C++ 的大文本。', ''),
        (['e_pp_cc', 'cc'], '编译：检查语法和类型，实例化模板，优化，翻成汇编。g(int) 的名字被修饰成 _Z1gi。', ''),
        (['e_cc_as', 'as'], '汇编：翻成机器码。call g 的地址还不知道，先填 0，记一条重定位项。', ''),
        (['e_as_obj', 'obj'], '得到 a.o：符号表里 f 是 T（定义在这里），g 是 U（只用了）。b.cpp 同样单独变成 b.o，里面 g 是 T。', ''),
    ]),
    ('link', '链接：拼成可执行文件', '', [
        (['obj', 'e_obj_ld', 'ld'], 'a.o、b.o 一起交给链接器。先做符号解析：a.o 里的 U g，在 b.o 里找到了定义 T g。', ''),
        (['ld'], '再合并：a.o、b.o 的 .text 拼成一个 .text，.data 拼成一个 .data，每个函数的最终地址就定了。', ''),
        (['ld'], '最后重定位：回到 a.o 里那条重定位项，把 call g 先填的 0 改成 g 的真实偏移。', ''),
        (['e_ld_exe', 'exe'], '输出可执行文件：程序头写着每一段加载时映射到哪、什么权限，还有入口地址和需要哪些 .so。', ''),
    ]),
    ('libs', '静态库和动态库', '', [
        (['staticlib', 'e_lib_ld', 'ld'], '静态库：链接器从 .a 里挑出用得上的 .o，把代码拷进可执行文件。之后不再依赖这个库。', ''),
        (['so', 'e_so_ld', 'ld'], '动态库：链接器只确认符号在，记下“运行时要 libc.so.6”，代码不拷。', ''),
        (['e_ld_exe', 'exe'], '所以 a.out 里有 printf 的名字、没有它的代码；运行时由动态链接器把 libc.so.6 映射进来。', ''),
    ]),
    ('run', './a.out 之后', '', [
        (['exe', 'e_exe_exec', 'exec'], 'shell fork 出子进程，子进程调 execve：内核读程序头，把各个 LOAD 段 mmap 进来，建好栈。', ''),
        (['e_exec_ldso', 'ldso'], '有 INTERP 段，内核先从动态链接器 ld.so 开始执行。', ''),
        (['so', 'e_so_ldso', 'ldso'], 'ld.so 按 DT_NEEDED 找到 libc.so.6，mmap 进来，做重定位，跑全局对象的构造函数。', ''),
        (['e_ldso_pm', 'procmap'], '这时进程地图已经完整：代码、数据在最下面，.so 在 mmap 区。ld.so 跳到 _start，main 开始执行。', ''),
    ]),
    ('plt', '第一次调 printf', '', [
        (['exe', 'e_exe_plt', 'plt'], 'main 里 call printf@plt：跳到本文件 PLT 里的跳板。', ''),
        (['plt'], '跳板从 GOT 里取地址。第一次取到的是解析函数：它在 libc.so 里找到 printf，把地址写回 GOT，再跳过去。', ''),
        (['plt'], '第二次调用，GOT 里已经是 printf 的真实地址，跳板一跳就到。加了 -z now 的程序在启动时就全部填好了。', ''),
    ]),
    ('err', 'undefined reference 从哪来', '', [
        (['src'], 'a.cpp 调了 g，b.h 里有 g 的声明，所以编译通过：编译器只要看到声明。', ''),
        (['obj'], 'a.o 的符号表里，g 是 U：用了，定义不在这里。', ''),
        (['ld'], '链接时，所有参与链接的文件里都找不到 T g：可能 b.cpp 没加进命令，或者 g 只写了声明。', ''),
        (['errs'], '链接器报 undefined reference to g。同一个错误还有几种来路，都列在这里。', ''),
    ]),
]

SVG_STYLE = '''
      .t  { font-size: 15px; font-weight: 600; fill: #1f2328; }
      .s  { font-size: 12px; fill: #57606a; }
      .h  { font-size: 17px; font-weight: 700; fill: #1f2328; }
      .tag{ font-size: 12px; fill: #0969da; }
      .lab{ font-size: 11.5px; fill: #57606a; }
      .labc{ font-size: 11.5px; fill: #bc4c00; }
      .labd{ font-size: 11.5px; fill: #0969da; }
      .labm{ font-size: 11.5px; fill: #1a7f37; }
      .lane-h { font-size: 13px; font-weight: 700; }
      .art  { fill: #fff8c5; stroke: #d4a72c; stroke-width: 1.2; }
      .step { fill: #fbefff; stroke: #c297ff; stroke-width: 1.2; }
      .run  { fill: #ffebe9; stroke: #ff8182; stroke-width: 1.2; }
      .user { fill: #eefbf1; stroke: #1a7f37; stroke-width: 1.3; }
      .note { fill: #fbfbfc; stroke: #8c959f; stroke-width: 1; }
      .ctl { stroke: #555; stroke-width: 1.5; fill: none; }
      .cpy { stroke: #bc4c00; stroke-width: 2; fill: none; }
      .ref { stroke: #0969da; stroke-width: 2; fill: none; stroke-dasharray: 6 4; }
      .map { stroke: #1a7f37; stroke-width: 2; fill: none; stroke-dasharray: 3 3; }'''

MARKERS = {'ctl': 'arr', 'cpy': 'arrC', 'ref': 'arrD', 'map': 'arrM'}
MARKER_COLORS = (('arr', '#555'), ('arrC', '#bc4c00'), ('arrD', '#0969da'), ('arrM', '#1a7f37'))


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
    for mid, color in MARKER_COLORS:
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

    # regions
    for ry, rh, fill, stroke, color, key in REGIONS:
        o.append('  <rect x="20" y="%d" width="1560" height="%d" rx="10" fill="%s" stroke="%s" stroke-dasharray="6 4"/>' % (ry, rh, fill, stroke))
        o.append('  <text x="32" y="%d" class="lane-h" style="fill:%s">%s</text>' % (ry + 22, color, esc(T[key])))

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
            o.append('  <text x="%d" y="%d" class="s" style="white-space:pre">%s</text>' % (x + 12, yy, esc(line)))
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
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (H - 30 + 20 * i, esc(line)))
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
        write('static/images/ref/build-map.%s.svg' % lang, svg(lang, False))
        write('static/maps/build-map.%s.html' % lang, page(lang))
    for w in sorted(set(WARNINGS)):
        print('WARN', w)


if __name__ == '__main__':
    main()
