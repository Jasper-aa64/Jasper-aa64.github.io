#!/usr/bin/env python3
"""Architecture map for the reference page (/ref/trading-architecture/).

One data definition below generates four files:
  static/images/ref/arch-map.{zh,en}.svg   the static map shown on the page
  static/maps/arch-map.{zh,en}.html        the interactive map (click a box, step through a path)

To change the map, edit NODES / EDGES / LABELS / TOURS and run from the repo root:
  python -X utf8 tools/arch-map/gen_arch_map.py
It prints a warning for every line of text that looks wider than its box.
"""
import html
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
W, H = 1600, 1140
FONT = 'PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif'
LANGS = ('zh', 'en')


def post(lang, slug, anchor=''):
    return ('/zh/posts/' if lang == 'zh' else '/posts/') + slug + '/' + ('#' + anchor if anchor else '')


def ref(lang, slug, anchor=''):
    return ('/zh/ref/' if lang == 'zh' else '/ref/') + slug + '/' + ('#' + anchor if anchor else '')


# ---------------------------------------------------------------- boxes
# box = (x, y, w, h); cls: ext = outside or hardware, hot = hot thread, data = hand-off structure,
# sync = join point, note = explanation, cold = side path.
# lines/tags are drawn in the box; panel is the longer text shown when the box is clicked.
NODES = {}


def node(nid, box, cls, zh, en):
    NODES[nid] = dict(box=box, cls=cls, zh=zh, en=en)


node('exch', (32, 170, 176, 230), 'ext',
     zh=dict(title='交易所', lines=['撮合引擎', '行情：按通道组播', '收报单，发回报'], tags=[],
             panel=['交易所的撮合引擎是行情的源头，也是报单的终点。',
                    '行情按通道组播发出：每个通道只带一部分证券，通道里的消息序号连续。报单进来撮合，结果以回报发回。']),
     en=dict(title='Exchange', lines=['Matching engine', 'Market data:', 'multicast by channel', 'Orders in, reports out'], tags=[],
             panel=['The matching engine is where market data starts and where orders end.',
                    'Market data goes out as multicast, split into channels: each channel carries a subset of the instruments, with consecutive sequence numbers. Orders come in to be matched; the results go back as execution reports.']))

node('counter', (32, 600, 176, 190), 'ext',
     zh=dict(title='券商柜台', lines=['券商的风控和报盘', '极速柜台：几十 µs', '普通柜台：到毫秒'], tags=[],
             panel=['报单一般不直接进交易所：先过券商的柜台系统，它做自己的风控和报盘，再转给交易所。',
                    '极速柜台几十微秒，普通柜台到毫秒（常见量级）。这一段在自己的系统之外，能优化的不多。']),
     en=dict(title='Broker system', lines=['Broker risk checks,', 'then routing', 'Fast tier: tens of µs', 'Standard: up to ms'], tags=[],
             panel=["Orders usually do not go straight to the exchange: they pass through the broker's trading system, which runs its own risk checks and routes them on.",
                    'A fast broker tier adds tens of microseconds, a standard one up to milliseconds (typical magnitudes). It sits outside your own system, so there is little to tune there.']))

node('nic', (260, 170, 220, 160), 'ext',
     zh=dict(title='网卡（NIC）', lines=['收行情包', '绕过内核：约 1 µs', '走内核协议栈：5–10 µs'],
             tags=[[('#1 中断别打到热核', post('zh', 'cpu-affinity-core-isolation-numa'))]],
             panel=['网卡收到行情包。走操作系统内核的协议栈，每个包要过中断、拷贝和系统调用，约 5–10 µs；绕过内核（kernel bypass），线程直接轮询网卡，约 1 µs。',
                    '网卡的中断要绑到别的核上，别打断热线程。']),
     en=dict(title='NIC', lines=['Receives market data', 'Kernel bypass: ~1 µs', 'Kernel stack: 5–10 µs'],
             tags=[[('#1 keep IRQs off hot cores', post('en', 'cpu-affinity-core-isolation-numa'))]],
             panel=['The network card receives the market data packets. Through the kernel network stack each packet pays for an interrupt, a copy and a system call, about 5–10 µs; with kernel bypass the thread polls the card directly, about 1 µs.',
                    "Route the card's interrupts to other cores so they never interrupt a hot thread."]))

node('feed', (520, 170, 220, 160), 'hot',
     zh=dict(title='行情接入线程', lines=['解码，转成内部格式', '按通道查序号，断档就补', '先写广播环，再按股票分发'],
             tags=[[('#5 广播环 1.7', post('zh', 'spmc-shared-memory-broadcast-ring', '17-什么时候不用广播环'))]],
             panel=['把网卡上的包解码成内部格式。',
                    '每个通道的序号必须连续：发现断档就要去补（重传或拿快照恢复），补齐之前这个通道的数据不可信。',
                    '解码完先写一份进广播环，给不赶时间的读者；再按股票查表，写进负责这只股票的分片队列。']),
     en=dict(title='Feed handler thread', lines=['Decode to internal format', 'Check per-channel', 'sequence, fill gaps', 'Ring first, then by stock'],
             tags=[[('#5 broadcast ring 1.7', post('en', 'spmc-shared-memory-broadcast-ring', '17-when-not-to-use-a-broadcast-ring'))]],
             panel=['Decodes the packets into the internal format.',
                    "Every channel's sequence numbers must be consecutive: a gap has to be recovered (retransmission or a snapshot), and until then that channel's data cannot be trusted.",
                    "It first writes each message into the broadcast ring for the readers that are not in a hurry, then looks up the stock's shard and writes into that shard's queue."]))

node('spsc', (780, 170, 200, 160), 'data',
     zh=dict(title='分片队列（SPSC）', lines=['股票 → 分片，查表', '同一只股票只进一片', '交接一次：几十 ns'],
             tags=[[('#4 无锁队列', post('zh', 'lock-free-queue-logger-micro-batching'))],
                   [('速查 2.6 跨核交接', ref('zh', 'cpu-memory', 'cross-core'))]],
             panel=['每个分片一个单生产者、单消费者的队列：接入线程写，分片线程读。',
                    '股票到分片是一张表，开盘前排好；同一只股票永远进同一片，顺序就不会乱。',
                    '交接一次，就是一条缓存行从一个核搬到另一个核，几十纳秒。']),
     en=dict(title='Shard queues', lines=['SPSC, one per shard', 'Stock → shard by table', 'One stock, one shard', 'Handoff: tens of ns'],
             tags=[[('#4 lock-free queue', post('en', 'lock-free-queue-logger-micro-batching'))],
                   [('Ref 2.6 cross-core', ref('en', 'cpu-memory', 'cross-core'))]],
             panel=['One single-producer single-consumer queue per shard: the feed thread writes, the shard thread reads.',
                    'A table maps each stock to a shard, fixed before the open; a stock always goes to the same shard, so its messages stay in order.',
                    'One handoff is one cache line moving from one core to another: tens of nanoseconds.']))

node('shard', (1020, 170, 270, 160), 'hot',
     zh=dict(title='分片线程 ×N', lines=['盘口重建 → 因子增量更新', '只碰自己那些股票的状态', '每条几百 ns 到几 µs'],
             tags=[[('缓存案例：一次行情重算 64 个期权', post('zh', 'low-latency-cache-case-study'))],
                   [('#14 在干活的核上预热', post('zh', 'prefetch-warmup-double-buffer'))]],
             panel=['每个分片线程只管自己那些股票：更新盘口，再增量更新因子。状态只有它自己碰，不用锁。',
                    '分片按消息量分，不按股票个数分：热门股的消息多得多。',
                    '开盘前在这个核上把要用的数据碰一遍（预热），别让第一次缺页、第一次缓存缺失落在开盘那几秒。']),
     en=dict(title='Shard threads ×N', lines=['Book rebuild → incremental factors', 'Touches only its own stocks', 'Hundreds of ns to µs a message'],
             tags=[[('Cache case study: 64 options a tick', post('en', 'low-latency-cache-case-study'))],
                   [('#14 warm up on the working core', post('en', 'prefetch-warmup-double-buffer'))]],
             panel=["Each shard thread owns a set of stocks: it updates their order books, then their factors, incrementally. Nobody else touches that state, so no locks.",
                    'Shards are balanced by message volume, not by the number of stocks: the busy names send far more messages.',
                    'Before the open, touch everything this core will use (warm-up), so the first page fault and the first cache miss do not land in the first seconds of trading.']))

node('barrier', (1330, 170, 230, 160), 'sync',
     zh=dict(title='汇合：bar 收齐', lines=['等所有分片算完这根 bar', '截面排名、标准化', '节奏：毫秒到秒'], tags=[],
             panel=['按 bar 截面的策略，要等所有分片都算完这一根 bar，才能一起排名、标准化。',
                    '这是一个汇合点，要等最慢的那个分片。',
                    '只有截面才要汇合；单只股票自己的因子不用等别人。']),
     en=dict(title='Join: bar complete', lines=['Wait for every shard', 'Cross-sectional rank, z-score', 'Cadence: ms to s'], tags=[],
             panel=['A cross-sectional strategy has to wait until every shard has finished the bar before it can rank and normalise.',
                    'This is a join point: it waits for the slowest shard.',
                    "Only cross-sectional work needs a join; a stock's own factors never wait for anyone."]))

node('ring', (520, 380, 220, 130), 'data',
     zh=dict(title='广播环（共享内存）', lines=['接入线程写一份', '落盘、监控各自来读', '生产者不等任何读者'],
             tags=[[('#5 SPMC 广播环', post('zh', 'spmc-shared-memory-broadcast-ring'))]],
             panel=['接入线程只写一份，要全量的读者各自来读：落盘、监控、研究。',
                    '生产者从不看读者读到哪，慢读者会被套圈，要自己发现。',
                    '读者再多也不会让生产者等，但死循环盯着最新槽位的读者，会在全速写时让每次写变贵（#5 1.6）。']),
     en=dict(title='Broadcast ring (shm)', lines=['Feed thread writes once', 'Recorder, monitor read', 'Producer waits for no one'],
             tags=[[('#5 SPMC broadcast ring', post('en', 'spmc-shared-memory-broadcast-ring'))]],
             panel=['The feed thread writes each message once; every reader that needs the full stream reads it on its own: recorder, monitor, research.',
                    'The producer never looks at where readers are; a slow reader gets lapped and has to notice it itself.',
                    'More readers never make the producer wait, but a reader that spins on the newest slot makes every write more expensive when the producer runs flat out (#5 1.6).']))

node('clock', (780, 380, 200, 200), 'note',
     zh=dict(title='两种节奏', lines=['按 bar 截面（多因子）：', '分片 → 汇合 → 策略，', '毫秒到秒。', '逐笔触发（做市、套利）：', '分片线程里一路做到报单，', '不过汇合，微秒级。'], tags=[],
             panel=['两种策略的节奏不一样。',
                    '按 bar 截面（多因子）：所有股票算完一根 bar 再一起打分。几十纳秒的交接看不出来，要盯的是一波数据进来以后，多久全部算完。',
                    '逐笔触发（做市、套利）：一条行情就可能触发一笔报单。分片线程里一路算信号、过风控、发单，不过汇合、不过队列，全程微秒级。']),
     en=dict(title='Two cadences', lines=['Per bar (multi-factor):', 'shards → join → strategy,', 'ms to s.', 'Per tick (MM, arbitrage):', 'signal to order inside', 'the shard thread, in µs.'], tags=[],
             panel=['The two kinds of strategy run on different clocks.',
                    'Per bar (multi-factor): every stock finishes the bar, then everything is scored together. A handoff of tens of nanoseconds is invisible here; what matters is how long a wave of data takes to be fully processed.',
                    'Per tick (market making, arbitrage): one message can trigger one order. The shard thread computes the signal, runs the risk checks and sends the order itself, with no join and no queue: microseconds end to end.']))

node('acct', (1020, 400, 270, 100), 'data',
     zh=dict(title='账户状态', lines=['持仓、资金、在途单', '只有决策线程改，别人读快照'],
             tags=[[('#14 双缓冲读快照', post('zh', 'prefetch-warmup-double-buffer'))]],
             panel=['持仓、资金、在途单，是整个系统里最要紧的状态。',
                    '只让决策线程一个人改；推送、监控要看，就读它发布出来的快照，不碰正在改的那份。',
                    '快照怎么发才不会读到一半新一半旧，见 #14 的双缓冲。']),
     en=dict(title='Account state', lines=['Positions, cash, open orders', 'One writer; others read snapshots'],
             tags=[[('#14 double-buffered snapshots', post('en', 'prefetch-warmup-double-buffer'))]],
             panel=['Positions, cash and open orders are the most important state in the system.',
                    'Only the decision thread writes them; the push service and the monitor read the snapshots it publishes and never touch the copy being changed.',
                    'How to publish a snapshot without readers seeing half old and half new data: #14, double buffering.']))

node('strategy', (1330, 400, 230, 100), 'hot',
     zh=dict(title='策略', lines=['合成打分、排名', '对照持仓、资金、在途单', '给出买、卖、撤'], tags=[],
             panel=['把各股票的打分合成、排名，再对照现在的持仓、资金和还没成交的单子，决定买什么、卖什么、撤哪些。',
                    '它只决定“做什么、做多少”，“怎么下”交给后面的订单管理。']),
     en=dict(title='Strategy', lines=['Combine scores, rank', 'Check positions, cash, orders', 'Decide buy, sell, cancel'], tags=[],
             panel=['Combines and ranks the scores, checks them against current positions, cash and unfilled orders, and decides what to buy, sell or cancel.',
                    'It decides what and how much; how to send it is left to the order manager.']))

node('risk', (1330, 525, 230, 85), 'hot',
     zh=dict(title='事前风控', lines=['单笔、持仓上限，价格范围', '报撤频率，总开关'], tags=[],
             panel=['每一笔单子发出去之前都要过的检查：单笔和持仓上限、价格在不在合理范围、报撤单是不是太频繁。',
                    '总开关（kill switch）一关，什么都发不出去。它在热路径上，所以只做内存里的比较。']),
     en=dict(title='Pre-trade risk', lines=['Size and position limits,', 'price bands, rate, kill switch'], tags=[],
             panel=['The checks every order passes before it goes out: order size and position limits, whether the price is within a sane band, whether orders and cancels are coming too fast.',
                    'With the kill switch on, nothing goes out. It sits on the hot path, so it only compares numbers in memory.']))

node('oms', (1330, 640, 230, 150), 'hot',
     zh=dict(title='订单管理（OMS）', lines=['订单状态机：', '已报 → 部成 → 已成或已撤', '大单拆成小单按时间发', '（TWAP 等）'],
             tags=[[('#3 热路径不现分配内存', post('zh', 'hot-path-memory-allocators'))]],
             panel=['给每笔单子一个状态机：新建、已报、部分成交、全部成交、已撤、被拒。',
                    '大单不一次发出去，拆成小单按时间表发（TWAP 平均分到一段时间里，VWAP 按成交量分），免得一下把价格砸穿。',
                    '订单对象从预先分配好的池子里拿，热路径上不现分配内存（#3）。']),
     en=dict(title='Order manager (OMS)', lines=['Order state machine:', 'sent → partial → filled/cxl', 'Slice big orders over time', '(TWAP and the like)'],
             tags=[[('#3 no hot-path allocation', post('en', 'hot-path-memory-allocators'))]],
             panel=['Gives every order a state machine: new, sent, partly filled, filled, cancelled, rejected.',
                    'A big order is not sent at once: it is sliced and sent on a schedule (TWAP spreads it evenly over time, VWAP follows traded volume) so it does not push the price away.',
                    'Order objects come from a pool allocated in advance; nothing is allocated on the hot path (#3).']))

node('gw', (1020, 680, 270, 110), 'hot',
     zh=dict(title='下单网关', lines=['编码成柜台、交易所的协议', '会话、序号、流控', '报单从网卡发出'], tags=[],
             panel=['把单子编码成柜台或交易所的协议，维护会话和序号，控制发送速度，再从网卡发出去。',
                    '回报也从这里进来，解码后交给订单管理。']),
     en=dict(title='Order gateway', lines=['Encode the broker/exchange protocol', 'Session, sequence numbers, throttle', 'Orders leave through the NIC'], tags=[],
             panel=['Encodes orders in the broker or exchange protocol, keeps the session and sequence numbers, throttles the rate and sends them out through the NIC.',
                    'Execution reports come in here too; they are decoded and handed to the order manager.']))

node('research', (32, 890, 200, 160), 'cold',
     zh=dict(title='离线回放与研究', lines=['录下的行情喂回', '同一份因子代码', '离线和盘中逐值对得上', '才说明回放可信'], tags=[],
             panel=['录下的行情按原来的顺序，喂回同一份因子代码。',
                    '离线算出来的和盘中算出来的逐值对得上，才说明回放可信。改了代码以后也靠它做回归：改前改后输出一个值都不变，才算没改坏。']),
     en=dict(title='Replay and research', lines=['Recorded data goes back', 'into the same factor code', 'Offline must match live,', 'value for value'], tags=[],
             panel=['The recorded data is fed, in its original order, back through the same factor code.',
                    'Only when offline results match live results value for value can the replay be trusted. It is also the regression test after a code change: same day of data, not a single output value may change.']))

node('rec', (270, 890, 210, 160), 'cold',
     zh=dict(title='行情落盘（录制）', lines=['全量写文件，攒批写', '落后满一圈会被套圈', '要能发现、要报警'],
             tags=[[('#5 2.3 部署时的坑', post('zh', 'spmc-shared-memory-broadcast-ring', '23-部署时的三个坑'))]],
             panel=['落盘进程从广播环读全量，写成文件，给回放和研究用。',
                    '它可以隔一会读一批，但不能落后满一圈，否则会被套圈、无声丢数据；重启要从存下的游标接着读（#5 2.3）。']),
     en=dict(title='Recorder', lines=['Writes all data to files', 'in batches', 'A ring behind = lapped:', 'detect it, alert'],
             tags=[[('#5 2.3 deployment traps', post('en', 'spmc-shared-memory-broadcast-ring', '23-three-deployment-traps'))]],
             panel=['The recorder reads the full stream from the broadcast ring and writes it to files for replay and research.',
                    'It may read in batches, but never a full ring behind, or it gets lapped and silently loses data; after a restart it resumes from a saved cursor (#5 2.3).']))

node('mon', (520, 890, 220, 160), 'cold',
     zh=dict(title='监控与告警', lines=['断档、积压、延迟分位数', '拒单、撤单率、仓位', '只读计数器，不进热路径'], tags=[],
             panel=['盯行情断档、各队列的积压、每一段延迟的分位数、拒单和撤单率、仓位。',
                    '只读各线程自己记的计数器，统计在监控自己的线程里算，不往热路径上加活。']),
     en=dict(title='Monitoring', lines=['Gaps, backlog, latency tails', 'Rejects, cancels, positions', 'Reads counters, off hot path'], tags=[],
             panel=['Watches feed gaps, queue backlogs, latency percentiles for every stage, rejects, cancel rates and positions.',
                    'It only reads counters that each thread keeps for itself and does its statistics on its own thread, adding no work to the hot path.']))

node('log', (780, 890, 200, 160), 'cold',
     zh=dict(title='异步日志', lines=['热线程往队列写一条', '就走，后台线程', '攒一批再写盘'],
             tags=[[('#4 无锁队列与攒批', post('zh', 'lock-free-queue-logger-micro-batching'))]],
             panel=['热线程打日志，只把一条记录写进队列就走；后台线程攒一批，再格式化、写盘。',
                    '格式化和写盘都不在热路径上（#4）。']),
     en=dict(title='Async logger', lines=['Hot threads enqueue', 'one record and move on;', 'a background thread', 'batches the writes'],
             tags=[[('#4 queue and batching', post('en', 'lock-free-queue-logger-micro-batching'))]],
             panel=['A hot thread logs by putting one record into a queue and moving on; a background thread batches records, formats them and writes them out.',
                    'Neither formatting nor disk writes happen on the hot path (#4).']))

node('ctrl', (1020, 890, 270, 160), 'cold',
     zh=dict(title='交易员指令', lines=['启停、撤单、改参数', '经服务进程走队列，', '送进决策线程', '次数少，但要尽快生效'], tags=[],
             panel=['交易员的指令：启停策略或算法单、撤单、改参数。',
                    '经服务进程校验后走队列送进决策线程，由决策线程自己改状态。次数少，但人点了要尽快生效，撤单尤其要快。']),
     en=dict(title='Trader commands', lines=['Start/stop, cancel, set params', 'via a service and a queue', 'into the decision thread', 'Rare, but must act fast'], tags=[],
             panel=['Commands from traders: start or stop a strategy or an algo order, cancel, change parameters.',
                    'A service validates them and passes them through a queue into the decision thread, which changes its own state. They are rare, but must take effect quickly, cancels above all.']))

node('push', (1330, 890, 230, 160), 'cold',
     zh=dict(title='客户端推送', lines=['订单、持仓、算法进度', '推到交易员的屏幕', '人看的：几十毫秒够用', '读快照，不碰热状态'], tags=[],
             panel=['把订单状态、持仓、算法单进度推到交易员的屏幕上。',
                    '是给人看的：几十毫秒够用，到百毫秒、秒级才开始误事。',
                    '读决策线程发布的快照，不碰热路径正在改的状态。']),
     en=dict(title='Client push', lines=['Orders, positions, algo', "progress to traders' screens", 'For people: tens of ms is fine', 'Reads snapshots only'], tags=[],
             panel=["Pushes order states, positions and algo-order progress to the traders' screens.",
                    'It is for people: tens of milliseconds is fine; trouble starts at hundreds of milliseconds or seconds.',
                    'It reads the snapshots the decision thread publishes and never touches the state the hot path is changing.']))

# ---------------------------------------------------------------- lines between boxes
# kind: line = hot path (market data to order), ret = reports coming back, side = side path
EDGES = [
    ('e_exch_nic', 'M208,250 L258,250', 'line'),
    ('e_nic_feed', 'M480,250 L518,250', 'line'),
    ('e_feed_spsc', 'M740,250 L778,250', 'line'),
    ('e_spsc_shard', 'M980,250 L1018,250', 'line'),
    ('e_shard_barrier', 'M1290,250 L1328,250', 'line'),
    ('e_barrier_strategy', 'M1445,330 L1445,398', 'line'),
    ('e_strategy_risk', 'M1445,500 L1445,523', 'line'),
    ('e_risk_oms', 'M1445,610 L1445,638', 'line'),
    ('e_oms_gw', 'M1330,705 L1292,705', 'line'),
    ('e_gw_counter', 'M1020,720 L210,720', 'line'),
    ('e_counter_exch', 'M90,600 L90,402', 'line'),
    ('e_exch_counter_r', 'M150,400 L150,598', 'ret'),
    ('e_counter_gw_r', 'M208,770 L1018,770', 'ret'),
    ('e_gw_oms_r', 'M1290,770 L1328,770', 'ret'),
    ('e_oms_acct_r', 'M1330,660 L1310,660 L1310,470 L1292,470', 'ret'),
    ('e_acct_strategy_r', 'M1290,430 L1328,430', 'ret'),
    ('e_feed_ring', 'M630,330 L630,378', 'side'),
    ('e_ring_rec', 'M590,510 L590,840 L375,840 L375,888', 'side'),
    ('e_ring_mon', 'M680,510 L680,888', 'side'),
    ('e_rec_research', 'M270,970 L234,970', 'side'),
    ('e_hot_log', 'M880,822 L880,888', 'side'),
    ('e_ctrl_dec', 'M1155,890 L1155,807', 'side'),
    ('e_oms_push', 'M1445,790 L1445,888', 'side'),
]

# (x, y, text-anchor, class, zh, en)
LABELS = [
    (233, 242, 'middle', 'lab', '行情', 'data'),
    (638, 360, 'start', 'lab', '写一份', 'write once'),
    (420, 712, 'middle', 'lab', '← 报单', '← orders'),
    (96, 505, 'start', 'lab', '报单', 'orders'),
    (156, 505, 'start', 'labr', '回报', 'reports'),
    (420, 790, 'middle', 'labr', '回报：确认、成交、撤单 →', 'reports: acks, fills, cancels →'),
    (888, 842, 'start', 'lab', '各热线程写一条就走', 'each hot thread enqueues and moves on'),
    (1163, 848, 'start', 'lab', '指令走队列进来', 'commands via a queue'),
    (1453, 830, 'start', 'lab', '订单、持仓变化', 'order/position changes'),
]

TEXT = {
    'zh': dict(
        title='交易系统架构地图：一条行情怎么变成一笔成交',
        legend=['蓝字 = 在哪里讲过（#N = 交易系统笔记 #N，速查 = 速查页的小节）。时间都是量级。',
                '黑线 = 热路径（行情 → 报单）；红线 = 回报回来（成交 → 持仓 → 策略）；灰色虚线 = 旁路（落盘、日志、监控、推送）。',
                '绿框 = 热线程，各绑一个隔离核；蓝框 = 线程之间交接数据的结构；黄框 = 汇合点；虚线框 = 旁路上的线程或进程。'],
        r_ext='场外', r_srv='交易服务器：热线程各绑一个隔离核', r_srv_tag='#1 绑核 / 隔离',
        r_dec='决策线程：一路调下去，不过队列', r_cold='旁路与控制面：慢了不能拖住热路径',
        footer=['时间都是量级，用来判断该抠哪一段，不对应哪套系统；每一段的数见速查页第 2 部分。',
                '图随文章更新：后续文章讲到新的组件时再往上补。']),
    'en': dict(
        title='Trading system architecture map: how a market data message becomes a fill',
        legend=['Blue text = where it is covered (#N = Trading System Notes #N, Ref = a section of the reference page). Times are orders of magnitude.',
                'Black = hot path (market data → order); red = reports coming back (fill → position → strategy); grey dashed = side paths (recording, logging, monitoring, push).',
                'Green = hot thread, each pinned to an isolated core; blue = a structure that hands data between threads; yellow = a join point; dashed = side-path threads or processes.'],
        r_ext='Outside', r_srv='Trading server: each hot thread pinned to an isolated core', r_srv_tag='#1 pinning / isolation',
        r_dec='Decision thread: plain calls, no queues', r_cold='Side paths: never block the hot path',
        footer=['Times are orders of magnitude to show which stage is worth optimising, not measurements of any one system; see Part 2 of the reference page.',
                'The map grows with the series: new components are added as later posts cover them.']),
}

UI = {
    'zh': dict(page_title='架构地图', lead='点一个框看它做什么、为什么这样设计；选一条路径，一步一步看一条行情怎么变成一笔成交。蓝字可以直接点开对应的文章。',
               other_lang=['English', 'arch-map.en.html'], static=['静态图', '/images/ref/arch-map.zh.svg'],
               ref=['速查页', '/zh/ref/trading-architecture/'], prev='上一步', next='下一步', exit='退出',
               step='第 {i} / {n} 步', panel_empty='点图里的任意一个框。', zoom=['看原尺寸', '适应宽度'], panel_links='在哪里讲过'),
    'en': dict(page_title='Architecture Map', lead='Click a box to see what it does and why it is built that way. Pick a path to step through how a market data message becomes a fill. Blue labels open the posts.',
               other_lang=['中文', 'arch-map.zh.html'], static=['Static image', '/images/ref/arch-map.en.svg'],
               ref=['Reference', '/ref/trading-architecture/'], prev='Back', next='Next', exit='Exit',
               step='Step {i} of {n}', panel_empty='Click any box in the map.', zoom=['Actual size', 'Fit width'], panel_links='Covered in'),
}

# ---------------------------------------------------------------- guided paths
TOURS = [
    ('tick', '一条行情到下单', 'A tick to an order', [
        (['exch', 'e_exch_nic', 'nic'],
         '交易所把行情按通道组播出来，网卡收到包。绕过内核直接收约 1 µs，走内核协议栈要 5–10 µs。',
         'The exchange multicasts market data by channel and the NIC receives the packet: about 1 µs with kernel bypass, 5–10 µs through the kernel stack.'),
        (['e_nic_feed', 'feed'],
         '行情接入线程解码，按通道查序号：断档了就去补。',
         'The feed handler thread decodes it and checks the channel sequence number; a gap has to be recovered.'),
        (['e_feed_ring', 'ring'],
         '先写一份进广播环，给落盘、监控这些不赶时间的读者。写完就走，不等任何读者。',
         'It first writes the message into the broadcast ring for readers that are not in a hurry, such as the recorder and the monitor, and moves on without waiting for anyone.'),
        (['e_feed_spsc', 'spsc'],
         '再按股票查表，写进负责这只股票的分片队列。同一只股票永远进同一片，顺序不会乱；交接一次几十纳秒。',
         "Then it looks up the stock's shard and writes into that shard's queue. A stock always goes to the same shard, so its messages stay in order; the handoff costs tens of nanoseconds."),
        (['e_spsc_shard', 'shard'],
         '分片线程更新这只股票的盘口，再增量更新它的因子。每个分片只碰自己那些股票的状态，不用锁。',
         "The shard thread updates the stock's order book, then its factors, incrementally. Each shard touches only its own stocks' state, so no locks."),
        (['e_shard_barrier', 'barrier'],
         '按 bar 截面的策略要等所有分片都算完这根 bar，再一起排名、标准化。这是汇合点，要等最慢的那个分片。',
         'A cross-sectional strategy waits until every shard has finished the bar, then ranks and normalises everything together. This is a join: it waits for the slowest shard.'),
        (['e_barrier_strategy', 'strategy'],
         '策略对照持仓、资金、在途单，决定买什么、卖什么、撤哪些。',
         'The strategy checks positions, cash and open orders and decides what to buy, sell or cancel.'),
        (['e_strategy_risk', 'risk'],
         '事前风控检查单笔和持仓上限、价格范围、报撤频率；总开关一关，什么都发不出去。',
         'Pre-trade risk checks size and position limits, price bands and order rates; with the kill switch on, nothing goes out.'),
        (['e_risk_oms', 'oms'],
         '订单管理给每笔单子建状态。大单不一次发出去，拆成小单按时间表发（TWAP 等）。',
         'The order manager gives every order a state. A big order is not sent at once but sliced and sent on a schedule (TWAP and the like).'),
        (['e_oms_gw', 'gw', 'e_gw_counter', 'counter', 'e_counter_exch'],
         '下单网关编码成协议发出去，经券商柜台到交易所。托管直连往返几十到几百 µs，经普通柜台可到毫秒。',
         "The order gateway encodes the order and sends it through the broker's system to the exchange: tens to hundreds of µs round trip from co-location, up to milliseconds through a standard broker tier."),
    ]),
    ('fast', '逐笔触发', 'Per-tick strategies', [
        (['exch', 'e_exch_nic', 'nic', 'e_nic_feed', 'feed'],
         '前面一样：行情进网卡，接入线程解码。最快的系统让交易所的通道直接对应线程，连按股票分发这一步都省掉。',
         "Same start: data reaches the NIC and is decoded. The fastest systems map the exchange's channels straight to threads and skip the per-stock dispatch altogether."),
        (['e_feed_spsc', 'spsc', 'e_spsc_shard', 'shard'],
         '消息交给负责这只股票的线程。',
         'The message reaches the thread that owns the stock.'),
        (['clock', 'shard'],
         '逐笔触发的策略（做市、套利）不等汇合：在这个线程里一路算信号，算完马上决定发不发单。',
         'A per-tick strategy (market making, arbitrage) does not wait for a join: the same thread computes the signal and decides right away whether to send an order.'),
        (['risk', 'oms', 'gw'],
         '风控、订单管理、网关的代码也在这个线程里接着调，中间不过任何队列。每多一次跨核交接，就多几十纳秒和一份抖动。',
         'The risk, order-manager and gateway code then run in the same thread, with no queue in between. Every extra cross-core handoff would add tens of nanoseconds and some jitter.'),
    ]),
    ('fill', '一笔成交回来', 'A fill coming back', [
        (['exch', 'e_exch_counter_r', 'counter'],
         '交易所撮合以后发出回报：确认、成交、撤单都算。回报先回到券商柜台。',
         "After matching, the exchange sends execution reports: acknowledgements, fills and cancels. They come back through the broker's system."),
        (['e_counter_gw_r', 'gw'],
         '柜台把回报转给下单网关，网关解码。',
         'The broker system passes them to the order gateway, which decodes them.'),
        (['e_gw_oms_r', 'oms'],
         '订单管理更新这笔单子的状态：部分成交、全部成交、已撤。',
         "The order manager updates the order's state: partly filled, filled or cancelled."),
        (['e_oms_acct_r', 'acct'],
         '账户状态跟着变：持仓、资金、在途单。这些只让决策线程一个人改，别的线程只读快照。',
         'The account state follows: positions, cash, open orders. Only the decision thread writes it; every other thread reads snapshots.'),
        (['e_acct_strategy_r', 'strategy'],
         '下一次决策用的就是新的持仓和资金，回路闭合。风控检查上限时，读的也是这份状态。',
         'The next decision uses the new positions and cash, which closes the loop. Risk checks read the same state.'),
        (['e_oms_push', 'push'],
         '旁边，推送把订单和持仓的变化送到交易员的屏幕上。给人看的，几十毫秒够用。',
         "On the side, the client push sends the order and position changes to the traders' screens; for people, tens of milliseconds is fine."),
    ]),
    ('side', '旁路与指令', 'Side paths and commands', [
        (['e_ring_rec', 'rec'],
         '落盘进程读广播环，全量写文件。它可以隔一会读一批，但不能落后满一圈，否则会被套圈、丢数据。',
         'The recorder reads the broadcast ring and writes everything to files. It may read in batches, but never a full ring behind, or it gets lapped and loses data.'),
        (['e_rec_research', 'research'],
         '录下的行情拿去离线回放：喂回同一份因子代码，离线结果和盘中逐值对得上，才说明回放可信。',
         'The recordings are replayed offline through the same factor code; only if offline matches live value for value can the replay be trusted.'),
        (['e_ring_mon', 'mon'],
         '监控读环和各线程的计数器：断档、积压、延迟分位数、拒单。它慢了不要紧，但不能拖住热路径。',
         "The monitor reads the ring and each thread's counters: gaps, backlog, latency percentiles, rejects. It may be slow, but it must never hold up the hot path."),
        (['e_hot_log', 'log'],
         '热线程打日志只往队列里写一条就走，后台线程攒一批再写盘。',
         'A hot thread logs by putting one record into a queue and moving on; a background thread batches the writes.'),
        (['ctrl', 'e_ctrl_dec'],
         '交易员的指令（启停、撤单、改参数）经服务进程走队列送进决策线程。次数少，但人点了要尽快生效。',
         'Trader commands (start/stop, cancel, change parameters) go through a service and a queue into the decision thread: rare, but they must take effect quickly.'),
    ]),
    ('burst', '开盘蜂拥', 'The opening rush', [
        (['exch', 'e_exch_nic', 'nic', 'e_nic_feed', 'feed'],
         '开盘、收盘、消息面的时候，消息一下涌进来，是平时的好几倍。接入线程每条只做解码和分发，扛得住。',
         'At the open, the close and on news, messages arrive several times faster than usual. The feed thread only decodes and dispatches each one, so it keeps up.'),
        (['e_feed_spsc', 'spsc', 'e_spsc_shard', 'shard'],
         '慢的是后面：每条要算的因子多了，分片线程算不过来，消息就在分片队列里排队，因子用的就是旧行情。',
         'The slow part is further on: when each message carries a lot of factor work, the shard threads fall behind, messages queue up, and the factors run on stale data.'),
        (['e_feed_ring', 'ring', 'e_ring_rec', 'rec'],
         '积压都堆在环和队列里：积压 =（到达速度 − 处理速度）× 持续时间，不能超过容量。广播环超过就会套圈。',
         'The backlog sits in the rings and queues: backlog = (arrival rate − service rate) × duration, and it must stay below capacity. A broadcast ring that overflows laps its readers.'),
        (['shard', 'clock'],
         '所以要省的是排队，不是交接：按消息量分片，多开几个分片线程，让每条的活变少。',
         'So what to save is the queueing, not the handoff: shard by message volume, add shard threads, and cut the work per message.'),
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
      .ext  { fill: #f6f8fa; stroke: #57606a; stroke-width: 1.2; }
      .hot  { fill: #eefbf1; stroke: #1a7f37; stroke-width: 1.4; }
      .data { fill: #ddf4ff; stroke: #54aeff; stroke-width: 1.2; }
      .sync { fill: #fff8c5; stroke: #d4a72c; stroke-width: 1.2; }
      .note { fill: #fbfbfc; stroke: #8c959f; stroke-width: 1; stroke-dasharray: 3 3; }
      .cold { fill: #ffffff; stroke: #8c959f; stroke-width: 1.2; stroke-dasharray: 5 3; }
      .sock { fill: #fbfbfc; stroke: #1f2328; stroke-width: 2; }
      .line { stroke: #555; stroke-width: 1.6; fill: none; }
      .ret  { stroke: #cf222e; stroke-width: 1.6; fill: none; }
      .side { stroke: #6e7781; stroke-width: 1.4; fill: none; stroke-dasharray: 5 3; }'''

MARKERS = {'line': 'arr', 'ret': 'arrR', 'side': 'arrG'}
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
    for mid, color in (('arr', '#555'), ('arrR', '#cf222e'), ('arrG', '#6e7781')):
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
    o.append('  <rect x="20" y="120" width="200" height="700" rx="10" fill="#f6f8fa" stroke="#8c959f" stroke-dasharray="6 4"/>')
    o.append('  <text x="32" y="146" class="lane-h" style="fill:#57606a">%s</text>' % esc(T['r_ext']))
    o.append('  <rect x="240" y="120" width="1340" height="700" rx="10" class="sock"/>')
    o.append('  <text x="256" y="148" class="h">%s</text>' % esc(T['r_srv']))
    tx = 256 + int(text_w(T['r_srv'], 17, True)) + 14
    o.append('  ' + tag_text(tx, 148, [(T['r_srv_tag'], post(lang, 'cpu-affinity-core-isolation-numa'))]))
    o.append('  <rect x="1005" y="365" width="565" height="440" rx="8" fill="#f4fbf5" stroke="#4ac26b" stroke-dasharray="6 4"/>')
    o.append('  <text x="1017" y="388" class="lane-h" style="fill:#1a7f37">%s</text>' % esc(T['r_dec']))
    check('decision heading', T['r_dec'], 13, 1325 - 1017, True)
    o.append('  <rect x="20" y="850" width="1560" height="220" rx="10" fill="#ffffff" stroke="#8c959f" stroke-dasharray="6 4"/>')
    o.append('  <text x="32" y="874" class="lane-h" style="fill:#57606a">%s</text>' % esc(T['r_cold']))
    check('side heading', T['r_cold'], 13, 370 - 32, True)

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
            o.append('  <text x="%d" y="%d" class="s">%s</text>' % (x + 12, yy, esc(line)))
            check('%s/%s' % (lang, nid), line, 12, w - 24)
        for segs in d['tags']:
            yy += 18
            o.append('  ' + tag_text(x + 12, yy, segs))
            check('%s/%s tag' % (lang, nid), ''.join(t for t, _ in segs), 12, w - 24)
        if yy + 10 > y + h:
            WARNINGS.append('%s/%s: text runs to y=%d, box ends at y=%d' % (lang, nid, yy + 10, y + h))
        o.append('  </g>')

    # lines and labels
    for eid, path, kind in EDGES:
        o.append('  <path d="%s" class="%s edge" id="%s" marker-end="url(#%s)"/>' % (path, kind, eid, MARKERS[kind]))
    for x, y, anchor, cls, zh, en in LABELS:
        s = zh if lang == 'zh' else en
        o.append('  <text x="%d" y="%d" class="%s" text-anchor="%s">%s</text>' % (x, y, cls, anchor, esc(s)))
        if anchor == 'start' and x + text_w(s, 11.5) > W - 4:
            WARNINGS.append('label "%s" runs past the right edge' % s)

    for i, line in enumerate(T['footer']):
        o.append('  <text x="20" y="%d" class="s">%s</text>' % (1098 + 22 * i, esc(line)))
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
        write('static/images/ref/arch-map.%s.svg' % lang, svg(lang, False))
        write('static/maps/arch-map.%s.html' % lang, page(lang))
    for w in sorted(set(WARNINGS)):
        print('WARN', w)


if __name__ == '__main__':
    main()
