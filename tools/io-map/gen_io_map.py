#!/usr/bin/env python3
"""IO map for the reference page (/zh/ref/cpp-linux/).

One data definition below generates:
  static/images/ref/io-map.zh.svg   the static map shown on the page
  static/maps/io-map.zh.html        the interactive map (click a box, step through a path)

To change the map, edit NODES / EDGES / LABELS / TOURS and run from the repo root:
  python -X utf8 tools/io-map/gen_io_map.py
It prints a warning for every line of text that looks wider than its box.
Chinese only for now; the English version follows once the layout is settled.
"""
import html
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
W, H = 1600, 1150
FONT = 'PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif'
LANGS = ('zh',)
HW = '/maps/hardware-map.zh.html'
PM = '/maps/process-map.zh.html'
EPOLL = '/zh/posts/epoll-internals/'


def post(lang, slug, anchor=''):
    return ('/zh/posts/' if lang == 'zh' else '/posts/') + slug + '/' + ('#' + anchor if anchor else '')


def ref(lang, slug, anchor=''):
    return ('/zh/ref/' if lang == 'zh' else '/ref/') + slug + '/' + ('#' + anchor if anchor else '')


# ---------------------------------------------------------------- boxes
# cls: user = user-space box, file = file path, net = network path, dev = device or memory, note = explanation.
NODES = {}


def node(nid, box, cls, zh, mono=False, extra=None):
    NODES[nid] = dict(box=box, cls=cls, zh=zh, mono=mono, extra=extra or [])


node('app', (40, 150, 300, 150), 'user',
     zh=dict(title='你的进程',
             lines=['read / write：读写文件', 'send / recv：收发网络数据', 'mmap：把文件映射进地址空间', '每一个都是一次系统调用'],
             tags=[[('进程地图', PM)]],
             panel=['程序碰文件和网络，都要通过系统调用请内核去做：read、write 读写文件，send、recv 收发 socket 数据，mmap 把文件映射进自己的地址空间。',
                    '系统调用是同一个线程从用户态切到内核态，一次来回约 100 ns 到几百 ns；数据没好、线程要睡下去等，才会切换线程，要几 µs。']))

node('ubuf', (370, 150, 270, 150), 'user',
     zh=dict(title='用户缓冲区 buf',
             lines=['你自己分配的内存：栈上、堆上', 'read / recv：内核把数据拷进来', 'write / send：内核从这里拷走'],
             tags=[[('进程地图：栈、堆', PM)]],
             panel=['read(fd, buf, n) 里的 buf：一块你自己的内存，在栈上或堆上。',
                    'read、recv 把数据从内核的缓冲区拷进 buf；write、send 把 buf 里的数据拷进内核的缓冲区。这两次拷贝都是 CPU 在做，数据大时就是一笔实打实的开销。']))

node('umap', (670, 150, 270, 150), 'user',
     zh=dict(title='mmap 映射区',
             lines=['页缓存里的页直接映射进来', '读写就是普通的访存，不拷贝', '第一次碰一页要缺页'],
             tags=[[('进程地图：mmap 区', PM)]],
             panel=['mmap 一个文件，内核在进程的 mmap 区登记一段地址；第一次访问某一页时缺页，内核把页缓存里那一页直接填进页表。',
                    '之后读写这段内存就是读写页缓存本身，不经过 read、write，也没有拷进拷出。写过的页同样是脏页，由回写线程写回磁盘；msync 可以强制写回。']))

node('models', (980, 140, 580, 180), 'note',
     zh=dict(title='IO 模型：等数据的时候，线程在干什么',
             lines=['阻塞：数据没好，线程睡在 read / recv 里',
                    '非阻塞：数据没好，立刻返回 EAGAIN，过会儿再试',
                    'IO 多路复用（select / poll / epoll）：一个线程等很多 fd，读还是自己读',
                    '异步（io_uring）：把“读到 buf 里”交给内核，读完了再通知你',
                    '前三种都是同步 IO：把数据拷进 buf 这一步，是你的线程在等'],
             tags=[[('epoll：红黑树、就绪链表和回调', EPOLL)]],
             panel=['阻塞和非阻塞问的是：数据还没好时，这次调用等不等。同步和异步问的是：把数据从内核拷进你的 buf，是不是你的线程自己调用、自己等着做完。',
                    '阻塞、非阻塞、IO 多路复用都是同步 IO：epoll 只告诉你哪些 fd 现在去读不会卡住，读还得自己调 recv。异步 IO 是把整件事交给内核，内核把数据拷进 buf 以后再通知你，Linux 上是 io_uring。']))

node('vfs', (40, 390, 300, 110), 'file',
     zh=dict(title='VFS（虚拟文件系统）',
             lines=['按 fd 找到打开的文件', '再交给具体的文件系统（ext4、xfs……）'],
             tags=[],
             panel=['fd 只是进程打开文件表里的一个下标。VFS 按它找到打开的文件，再把读写交给具体的文件系统（ext4、xfs……），由文件系统算出数据在磁盘的哪些块上。',
                    'socket、管道也挂在同一套接口下，所以它们也能用 read、write、close，也能被 epoll 关注。']))

node('pcache', (40, 530, 300, 150), 'file',
     zh=dict(title='页缓存（page cache）',
             lines=['读过、写过的文件内容，按页缓存在内存里', 'read 命中就直接拷，不碰磁盘', 'write 写到这里、标成脏页就返回', 'free 命令里的 buff/cache 主要就是它'],
             tags=[],
             panel=['内核把读过、写过的文件内容按页（4 KiB）留在内存里，这就是页缓存。同一个文件第二次读，多半直接命中，不碰磁盘。',
                    'write 也只是把数据拷进页缓存、标成脏页就返回，真正写到磁盘是之后的事。所以 write 返回不代表数据落盘，断电会丢。',
                    '空闲内存都会被拿来当页缓存，内存紧张时再回收干净的页。free 命令里 buff/cache 那一栏大，不代表内存不够用。']))

node('flush', (370, 710, 250, 110), 'file',
     zh=dict(title='回写线程（writeback）',
             lines=['脏页过一会写回磁盘', '默认脏了约 30 s 必写，每 5 s 查一次', 'fsync：等这个文件写完才返回'],
             tags=[],
             panel=['内核的回写线程定期把脏页写回磁盘：默认每 5 s 醒来一次，脏了超过约 30 s 的页一定写回；脏页占内存的比例太高时，写文件的线程会被拖住，帮着写。',
                    '要确定数据落盘，调 fsync（或 fdatasync）：它等这个文件的脏页都写到磁盘、磁盘也确认了才返回，所以很慢，几百 µs 到几十 ms。数据库提交事务时就要 fsync。']))

node('blk', (40, 710, 300, 110), 'file',
     zh=dict(title='块设备层 + 磁盘驱动',
             lines=['把要读写的页组成请求，排队、合并', '交给 NVMe 驱动，发给磁盘'],
             tags=[],
             panel=['页缓存没命中，或者要回写脏页时，文件系统算出磁盘块号，块设备层把这些块组成请求，排队、合并相邻的请求，再交给磁盘驱动。',
                    'NVMe 盘有多条提交队列，每个核一条，请求直接放进队列，磁盘做完用中断通知。']))

node('sock', (670, 390, 300, 150), 'net',
     zh=dict(title='socket 缓冲区',
             lines=['接收缓冲：收到了、还没被 recv 的数据', '发送缓冲：send 拷进来、对方还没确认的', '满了：send 阻塞，或返回 EAGAIN'],
             tags=[],
             panel=['每个 TCP socket 有两块内核缓冲区。接收缓冲放已经收到、还没被 recv 取走的数据；发送缓冲放 send 拷进来、还没被对方确认收到的数据。',
                    'send 返回只代表数据拷进了发送缓冲，不代表对方收到，更不代表对方的程序读到了。发送缓冲满了（对方读得慢、网络慢），阻塞的 socket 上 send 会睡，非阻塞的返回 EAGAIN。',
                    '接收缓冲满了，TCP 会把接收窗口告诉对方为 0，让对方停发，这就是流量控制。']))

node('epollk', (1010, 390, 550, 150), 'net',
     zh=dict(title='epoll：就绪通知',
             lines=['socket 收到数据，回调把它挂上 epoll 的就绪链表，', '再叫醒睡在 epoll_wait 里的线程', '只通知“可以读了”，数据还得你自己 recv'],
             tags=[[('epoll：红黑树、就绪链表和回调', EPOLL)]],
             panel=['epoll 登记一个 socket 时，在它的等待队列上挂了一个回调。数据进了接收缓冲，回调就把这个 socket 挂上 epoll 的就绪链表，再叫醒睡在 epoll_wait 里的线程。',
                    'epoll 只负责告诉你“可以读了”，数据还在接收缓冲里，要你自己调 recv 拷出来。']))

node('tcp', (670, 570, 300, 110), 'net',
     zh=dict(title='TCP/IP 协议栈',
             lines=['收：校验、去包头，按 IP 和端口找到 socket', '发：分段、等确认、丢了重传'],
             tags=[],
             panel=['收包时，协议栈校验 IP 和 TCP 头，按（源 IP，源端口，目的 IP，目的端口）找到对应的 socket，把数据按序号放进接收缓冲，并回 ACK。',
                    '发包时，按对方的接收窗口和拥塞窗口把发送缓冲里的数据切成段发出去；收到 ACK 才把那部分从发送缓冲里删掉，超时没确认就重传。']))

node('drv', (670, 710, 300, 110), 'net',
     zh=dict(title='网卡驱动 + 收发环',
             lines=['收：软中断（NAPI）一次取一批包', '发：把包挂到发送环，通知网卡'],
             tags=[],
             panel=['网卡和驱动之间用内存里的环形队列交接：收包环里放着空的缓冲区，网卡收到包就用 DMA 写进去；发送环里放着要发的包，网卡用 DMA 读出来发走。',
                    '收到包，网卡发中断。中断处理只做一点点，真正的活交给软中断：NAPI 一次从收包环里取一批包往上送；包多的时候先关掉中断改成轮询，省得每个包都打断一次 CPU。']))

node('zc', (1010, 570, 550, 250), 'note',
     zh=dict(title='零拷贝：把文件发到网络上',
             lines=['read + write：',
                    '  磁盘 → 页缓存（DMA）→ buf（CPU）→ socket 缓冲（CPU）→ 网卡（DMA）',
                    '  4 次拷贝，4 次用户态、内核态切换',
                    'mmap + write：页缓存直接映射进来，省掉拷进 buf 那一次',
                    'sendfile：数据不出内核，页缓存 → 网卡',
                    '  网卡支持分散收集 DMA 时，CPU 一次都不拷，只剩 2 次 DMA、2 次切换',
                    'splice：在两个 fd 之间搬，中间经过一个管道，也不拷进用户态'],
             tags=[],
             panel=['静态文件服务器、Kafka 这类要把文件原样发出去的程序，用 read + write 要走四次拷贝：磁盘到页缓存、页缓存到 buf、buf 到 socket 缓冲、socket 缓冲到网卡。中间两次是 CPU 在搬，而且数据根本没被程序看过。',
                    'sendfile(out_fd, in_fd, …) 让内核直接把页缓存里的数据交给 socket。网卡支持分散收集（scatter-gather）DMA 时，socket 缓冲里只放页的地址和长度，网卡直接从页缓存读，CPU 一个字节都不拷，这就是“零拷贝”。',
                    '零拷贝省的是 CPU 拷贝和切换次数，DMA 那两次省不掉。']))

node('disk', (40, 940, 300, 130), 'dev',
     zh=dict(title='磁盘（NVMe SSD）',
             lines=['一次随机读约 10–100 µs', '机械硬盘要几 ms', '做完用 DMA 写进内存，再发中断'],
             tags=[[('硬件地图：外部设备', HW)]],
             panel=['NVMe SSD 一次随机读约 10–100 µs，机械硬盘要寻道，约几 ms。比内存慢几百到几万倍，所以页缓存命中与否，决定了一次 read 是微秒还是毫秒。',
                    '磁盘不经过 CPU，用 DMA 把数据直接写进内存里的页缓存，做完发中断告诉内核。']))

node('mem', (380, 940, 250, 130), 'dev',
     zh=dict(title='内存（DRAM）',
             lines=['页缓存、socket 缓冲、收发环', '其实都是内存里的页', 'DMA：设备直接读写内存，不占 CPU'],
             tags=[[('硬件地图：内存控制器 → 通道', HW + '#load')]],
             panel=['图上内核里的页缓存、socket 缓冲、网卡的收发环，物理上都是内存里的页。DMA 让磁盘和网卡直接读写这些页，CPU 只在拷贝（比如拷进你的 buf）时才动手。',
                    'CPU 去读刚被 DMA 写进来的数据，走的就是硬件地图上那条 load 的路。']))

node('nic', (670, 940, 300, 130), 'dev',
     zh=dict(title='网卡（NIC）',
             lines=['收：DMA 写进收包环，再发中断', '发：DMA 从发送环读出来发走', '同一机房往返约几十 µs'],
             tags=[[('硬件地图：网卡 → 中断 → 某个核', HW)]],
             panel=['网卡收到包，用 DMA 写进内存里的收包环，再发中断；要发的包，驱动挂到发送环上，网卡用 DMA 读出来发走。',
                    '中断交给哪个核处理，软中断、协议栈和唤醒就在哪个核上跑。多队列网卡按连接把包分到不同的队列，每个队列的中断交给不同的核。']))

# ---------------------------------------------------------------- lines between boxes
# kind: ctl = a call or a notification, cpu = a copy done by the CPU, dma = a copy done by a device, map = mapped, no copy
EDGES = [
    ('e_app_vfs', 'M190,300 L190,388', 'ctl'),
    ('e_app_sock', 'M320,300 L320,330 L820,330 L820,388', 'ctl'),
    ('e_vfs_pc', 'M190,500 L190,528', 'ctl'),
    ('e_pc_ubuf', 'M340,580 L420,580 L420,302', 'cpu'),
    ('e_sock_ubuf', 'M670,450 L560,450 L560,302', 'cpu'),
    ('e_pc_umap', 'M340,640 L650,640 L650,250 L668,250', 'map'),
    ('e_pc_blk', 'M190,680 L190,708', 'ctl'),
    ('e_pc_flush', 'M320,680 L320,695 L470,695 L470,708', 'ctl'),
    ('e_flush_blk', 'M370,770 L342,770', 'ctl'),
    ('e_blk_disk', 'M190,820 L190,938', 'ctl'),
    ('e_disk_mem', 'M340,1005 L378,1005', 'dma'),
    ('e_nic_mem', 'M670,1005 L632,1005', 'dma'),
    ('e_nic_drv', 'M820,938 L820,822', 'ctl'),
    ('e_drv_tcp', 'M820,708 L820,682', 'ctl'),
    ('e_tcp_sock', 'M820,568 L820,542', 'ctl'),
    ('e_sock_ep', 'M970,465 L1008,465', 'ctl'),
]

# (x, y, text-anchor, class, zh)
LABELS = [
    (198, 352, 'start', 'lab', 'read / write'),
    (560, 324, 'start', 'lab', 'send / recv'),
    (428, 560, 'start', 'labc', 'CPU 拷贝'),
    (566, 440, 'start', 'labc', 'CPU 拷贝'),
    (480, 632, 'start', 'labm', '映射，不拷贝'),
    (198, 880, 'start', 'lab', '读写请求'),
    (360, 996, 'middle', 'labd', 'DMA'),
    (651, 996, 'middle', 'labd', 'DMA'),
    (828, 880, 'start', 'lab', '中断'),
    (989, 457, 'middle', 'lab', '回调'),
    (198, 518, 'start', 'lab', '查'),
    (198, 698, 'start', 'lab', '没命中'),
]

TEXT = {
    'zh': dict(
        title='IO 地图：数据怎么在设备、内核和你的缓冲区之间走',
        legend=['上面是用户态，中间是内核，下面是设备和内存。左边一列是文件，中间一列是网络。数字都是量级。',
                '橙线 = CPU 拷贝；蓝色虚线 = DMA（设备直接读写内存，不占 CPU）；绿色虚线 = 映射，不拷贝；灰线 = 调用或通知。',
                '蓝字 = 在哪里讲过，进程地图、硬件地图会打开对应的那张图。'],
        r_user='用户态：你的进程', r_krn='内核态', r_dev='设备和内存',
        r_sys='系统调用：同一个线程切到内核态，一次来回约 100 ns 到几百 ns',
        footer=['图随文章更新：讲到 io_uring、管道和信号时再往上补。']),
}

UI = {
    'zh': dict(page_title='IO 地图', lead='点一个框看它做什么、在哪篇讲过；选一条路径，一步一步看一次 read、一次 recv、一次 sendfile 怎么走。蓝字可以直接点开对应的文章或地图。',
               other_lang=['进程地图', PM], static=['静态图', '/images/ref/io-map.zh.svg'],
               ref=['速查页', '/zh/ref/cpp-linux/#io'], prev='上一步', next='下一步', exit='退出',
               step='第 {i} / {n} 步', panel_empty='点图里的任意一个框。', zoom=['看原尺寸', '适应宽度'], panel_links='在哪里讲过'),
}

# ---------------------------------------------------------------- guided paths
TOURS = [
    ('read', '读一个文件', '', [
        (['app', 'e_app_vfs', 'vfs'], 'read(fd, buf, n)：系统调用进内核，VFS 按 fd 找到打开的文件，交给文件系统。', ''),
        (['e_vfs_pc', 'pcache'], '先查页缓存。命中就直接跳到最后一步，整个 read 只要几百 ns 到几 µs。', ''),
        (['e_pc_blk', 'blk', 'e_blk_disk', 'disk'], '没命中：块设备层组成请求，交给 NVMe 驱动。磁盘读一次约 10–100 µs，线程这时睡着。', ''),
        (['e_disk_mem', 'mem'], '磁盘用 DMA 把数据直接写进内存里的页缓存，不占 CPU，写完发中断，内核把线程叫醒。', ''),
        (['e_pc_ubuf', 'ubuf'], '内核把数据从页缓存拷进你的 buf，这一次是 CPU 拷贝。read 返回读到的字节数。', ''),
    ]),
    ('write', '写一个文件', '', [
        (['app', 'e_app_vfs', 'vfs'], 'write(fd, buf, n)：进内核，VFS 找到文件。', ''),
        (['pcache'], '数据从 buf 拷进页缓存，这一页标成脏页，write 就返回了。返回不代表落盘，这时断电数据会丢。', ''),
        (['e_pc_flush', 'flush'], '回写线程过一会把脏页写回：默认每 5 s 查一次，脏了约 30 s 的一定写。', ''),
        (['e_flush_blk', 'blk', 'e_blk_disk', 'disk'], '要确定落盘，调 fsync：等这个文件的脏页都写到磁盘、磁盘确认了才返回，几百 µs 到几十 ms。', ''),
    ]),
    ('mmap', '映射一个文件', '', [
        (['app', 'umap'], 'mmap 只在进程的 mmap 区登记一段地址，还没有任何页。', ''),
        (['e_pc_umap', 'pcache'], '第一次访问某一页：缺页，内核把页缓存里那一页直接填进你的页表，不拷贝。页缓存里没有，就先从磁盘读进来。', ''),
        (['umap'], '之后读写就是普通访存。写过的页同样是脏页，由回写线程写回；msync 强制写回。', ''),
    ]),
    ('recv', '收一个包', '', [
        (['nic', 'e_nic_mem', 'mem'], '网卡收到包，用 DMA 写进内存里的收包环，再发中断。', ''),
        (['e_nic_drv', 'drv'], '中断处理很短，真正的活交给软中断（NAPI）：一次从收包环里取一批包往上送。', ''),
        (['e_drv_tcp', 'tcp'], '协议栈校验、去掉包头，按 IP 和端口找到对应的 socket，回 ACK。', ''),
        (['e_tcp_sock', 'sock'], '数据放进这个 socket 的接收缓冲，唤醒等在它上面的线程。', ''),
        (['e_sock_ep', 'epollk'], '如果它被 epoll 关注，回调把它挂上就绪链表，epoll_wait 返回。', ''),
        (['e_sock_ubuf', 'ubuf'], '你调 recv，内核把数据从接收缓冲拷进 buf（CPU 拷贝）。', ''),
    ]),
    ('send', '发一个包', '', [
        (['app', 'e_app_sock', 'sock'], 'send 把 buf 里的数据拷进 socket 的发送缓冲就返回：返回只代表拷进去了，不代表对方收到。发送缓冲满了，send 就阻塞或返回 EAGAIN。', ''),
        (['tcp'], 'TCP 按对方的接收窗口和拥塞窗口分段发出去，数据留在发送缓冲里，直到对方确认；超时没确认就重传。', ''),
        (['drv', 'nic', 'mem'], '驱动把包挂到发送环，网卡用 DMA 从内存读出来发走。', ''),
    ]),
    ('sendfile', '把文件发到网络', '', [
        (['zc'], '要把一个文件原样发给客户端（静态文件服务器、Kafka），看两种写法各拷几次。', ''),
        (['disk', 'e_disk_mem', 'pcache', 'e_pc_ubuf', 'ubuf'], 'read：磁盘 DMA 进页缓存，再由 CPU 拷进 buf。', ''),
        (['e_sock_ubuf', 'sock', 'drv', 'nic'], 'write 到 socket：CPU 再从 buf 拷进 socket 缓冲，网卡 DMA 发走。一共 4 次拷贝、4 次切换，其中两次 CPU 拷贝的数据程序根本没看过。', ''),
        (['pcache', 'sock', 'nic', 'zc'], 'sendfile：数据不出内核，socket 里只记页缓存里那些页的位置，网卡直接从页缓存 DMA。CPU 一次不拷，剩 2 次 DMA、2 次切换。', ''),
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
      .user { fill: #eefbf1; stroke: #1a7f37; stroke-width: 1.3; }
      .file { fill: #fbefff; stroke: #c297ff; stroke-width: 1.2; }
      .net  { fill: #ddf4ff; stroke: #54aeff; stroke-width: 1.2; }
      .dev  { fill: #ffebe9; stroke: #ff8182; stroke-width: 1.2; }
      .note { fill: #fbfbfc; stroke: #8c959f; stroke-width: 1; }
      .ctl { stroke: #555; stroke-width: 1.5; fill: none; }
      .cpu { stroke: #bc4c00; stroke-width: 2; fill: none; }
      .dma { stroke: #0969da; stroke-width: 2; fill: none; stroke-dasharray: 6 4; }
      .map { stroke: #1a7f37; stroke-width: 2; fill: none; stroke-dasharray: 3 3; }'''

MARKERS = {'ctl': 'arr', 'cpu': 'arrC', 'dma': 'arrD', 'map': 'arrM'}
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
    o.append('  <rect x="20" y="112" width="1560" height="230" rx="10" fill="#f6fbf7" stroke="#4ac26b" stroke-dasharray="6 4"/>')
    o.append('  <text x="32" y="134" class="lane-h" style="fill:#1a7f37">%s</text>' % esc(T['r_user']))
    o.append('  <path d="M20,356 L1580,356" stroke="#8c959f" stroke-width="1.2" stroke-dasharray="5 4" fill="none"/>')
    o.append('  <text x="1576" y="351" class="lab" text-anchor="end">%s</text>' % esc(T['r_sys']))
    o.append('  <rect x="20" y="364" width="1560" height="478" rx="10" fill="#fbfbfc" stroke="#1f2328" stroke-width="2"/>')
    o.append('  <text x="32" y="383" class="lane-h" style="fill:#1f2328">%s</text>' % esc(T['r_krn']))
    o.append('  <rect x="20" y="900" width="1560" height="190" rx="10" fill="#fff8f7" stroke="#ff8182" stroke-dasharray="6 4"/>')
    o.append('  <text x="32" y="922" class="lane-h" style="fill:#cf222e">%s</text>' % esc(T['r_dev']))

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
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (1120 + 20 * i, esc(line)))
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
        write('static/images/ref/io-map.%s.svg' % lang, svg(lang, False))
        write('static/maps/io-map.%s.html' % lang, page(lang))
    for w in sorted(set(WARNINGS)):
        print('WARN', w)


if __name__ == '__main__':
    main()
