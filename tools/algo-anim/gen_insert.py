import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui
out = sys.argv[1]
T = {
 'zh': dict(lang='zh-CN', title='线性基插入：分步看',
   font='PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Segoe UI, sans-serif',
   input='插入的数（空格分隔，0 到 255）：', apply='换这组数', prev='上一步', next='下一步', play='自动播放', pause='暂停', reset='重来',
   rank='秩 r', span='能异或出的值',
   L=dict(
     h0='开始之前', hnum='插入第 {j} 个数：{v}', hend='插完了', empty='空', many='共 {c} 个',
     err='请输入 1 到 12 个 0 到 255 之间的整数',
     start='b 全空，秩 0，能异或出的值只有 0。点“下一步”或按右方向键。',
     take='{v} = {bin}，x 从它开始，从最高位往下看。',
     zero='第 {i} 位是 0，跳过，看下一位。',
     xor='第 {i} 位是 1，b[{i}] = {bv} 已有数：x ^= b[{i}]，{xo} ⊕ {bb} = {xn}，第 {i} 位消成 0。这是一次行变换。',
     store='第 {i} 位是 1，b[{i}] 空着：把 x = {xb} 存进 b[{i}]。它的最高位和已有的基都不同，所以线性无关；秩变成 {r}，能异或出的值翻倍到 {c} 个。',
     dead='x 被消成 0：原来的 {v} 等于若干个基的异或，已经在张成的空间里。插入失败，空间不变。',
     done='秩 {r}，能异或出 {c} 个不同的值。插入失败的 {f} 个数都能由基表示。')),
 'en': dict(lang='en', title='XOR basis insertion, step by step',
   font='Segoe UI, Helvetica, Arial, sans-serif',
   input='Numbers to insert (space-separated, 0 to 255):', apply='Use these', prev='Back', next='Next', play='Play', pause='Pause', reset='Restart',
   rank='rank r', span='reachable values',
   L=dict(
     h0='Before we start', hnum='Insert number {j}: {v}', hend='All inserted', empty='empty', many='{c} in total',
     err='Enter 1 to 12 integers between 0 and 255',
     start='b is empty, rank 0, and the only reachable value is 0. Press Next or the right arrow key.',
     take='{v} = {bin}. x starts as this number; scan from the highest bit down.',
     zero='Bit {i} is 0, skip to the next bit.',
     xor='Bit {i} is 1 and b[{i}] = {bv} is occupied: x ^= b[{i}], {xo} ⊕ {bb} = {xn}, clearing bit {i}. This is one row operation.',
     store='Bit {i} is 1 and b[{i}] is empty: store x = {xb} in b[{i}]. Its highest bit differs from every other basis vector, so it is independent; the rank becomes {r} and the reachable values double to {c}.',
     dead='x is cleared to 0: the original {v} is an XOR of basis vectors, already in the span. The insertion fails and the space is unchanged.',
     done='Rank {r}, {c} distinct reachable values. Each of the {f} failed numbers can be written with the basis.')),
}
LEG = {
 'zh': ([('当前看的位', 'background:var(--hlbg);border-color:var(--hl)'), ('x', 'background:var(--xbg);border-color:var(--x)'),
         ('主元位（b[i] 的最高位）', 'background:var(--pivbg);border-color:var(--piv)'), ('空位', 'border-color:var(--muted);border-style:dashed')], '<kbd>←</kbd> <kbd>→</kbd> 也能翻页'),
 'en': ([('bit being looked at', 'background:var(--hlbg);border-color:var(--hl)'), ('x', 'background:var(--xbg);border-color:var(--x)'),
         ('pivot bit (highest bit of b[i])', 'background:var(--pivbg);border-color:var(--piv)'), ('empty slot', 'border-color:var(--muted);border-style:dashed')], '<kbd>←</kbd> <kbd>→</kbd> also step'),
}
TPL = open(sys.argv[2], encoding='utf-8').read()
for lang, t in T.items():
    s = ui.fill(TPL, t, *LEG[lang])
    for k, v in t.items():
        if k != 'L':
            s = s.replace('%%' + k + '%%', v)
    s = s.replace('%%JSON%%', json.dumps(t['L'], ensure_ascii=False))
    s = s.replace('%%UI%%', json.dumps({'play': t['play'], 'pause': t['pause']}, ensure_ascii=False))
    assert '%%' not in s, lang
    open(f'{out}/xor-basis-insert.{lang}.html', 'w', encoding='utf-8', newline='\n').write(s)
print('ok')
