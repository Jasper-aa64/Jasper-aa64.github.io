import sys, json
wt = sys.argv[1]
here = sys.argv[2]

# ---------- interactive page ----------
T = {
 'zh': dict(lang='zh-CN', title='高斯消元：分步看', font='PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Segoe UI, sans-serif',
   prev='上一步', next='下一步', play='自动播放', reset='重来',
   tips='粉色是当前处理的列（只看当前行及以下），紫色是主元，绿色是这一步改过的行，虚线框是拿来消别人的主元行。分数是精确值。',
   J=dict(sep='；', p1='唯一解', p2='有自由元', p3='无解', play='自动播放', pause='暂停', row='第 {i} 行',
     h0='开始之前', hcol='第 {c} 列', hend='读结果',
     start='3 个方程 3 个未知数，写成增广矩阵，竖线右边是右端 b。从第 1 列开始，当前行是第 1 行。点“下一步”或按右方向键。',
     pick='在第 {r} 行及以下找第 {c} 列绝对值最大的数：第 {p} 行的 {v}，用它作主元。',
     nofree='第 {r} 行及以下，第 {c} 列全是 0，找不到主元：x{c} 是自由元。当前行不动，还是第 {r} 行，直接看下一列。',
     swap='交换第 {p} 行和第 {r} 行，主元换到当前行。交换不改变解集。',
     norm='第 {r} 行除以主元 {v}，主元变成 1。',
     elim='第 {i} 行减去第 {r} 行的 {f} 倍，第 {c} 列消成 0。上下都消，消完不用回代。',
     one='每列都有主元，没有自由元，唯一解：{s}。',
     many='没有 0 = 非零 的行，有自由元 {f}，解有无穷多个：{s}（自由元任取）。',
     none='第 {i} 行系数全是 0，右端是 {v}，写出来是 0 = {v}：无解。',
     noneFree='虽然也有自由元，但先查到矛盾，答案是无解。')),
 'en': dict(lang='en', title='Gaussian elimination, step by step', font='Segoe UI, Helvetica, Arial, sans-serif',
   prev='Back', next='Next', play='Play', reset='Restart',
   tips='Pink is the column being processed (current row and below), purple is the pivot, green is the row changed in this step, and the dashed cell marks the pivot row used to clear others. Fractions are exact.',
   J=dict(sep='; ', p1='Unique solution', p2='Free variable', p3='No solution', play='Play', pause='Pause', row='row {i}',
     h0='Before we start', hcol='Column {c}', hend='Read the result',
     start='Three equations in three unknowns, written as an augmented matrix; right of the bar is the right-hand side b. Start at column 1 with the current row at row 1. Press Next or the right arrow key.',
     pick='Among row {r} and below, the entry of largest absolute value in column {c} is {v} in row {p}; it becomes the pivot.',
     nofree='Column {c} is all 0 from row {r} down, so there is no pivot: x{c} is a free variable. The current row stays at row {r}; move to the next column.',
     swap='Swap rows {p} and {r} to bring the pivot to the current row. Swapping does not change the solutions.',
     norm='Divide row {r} by the pivot {v}, so the pivot becomes 1.',
     elim='Subtract {f} times row {r} from row {i}, clearing column {c}. Rows above are cleared too, so no back-substitution is needed.',
     one='Every column has a pivot and there is no free variable: the unique solution is {s}.',
     many='No row reads 0 = nonzero and {f} is free, so there are infinitely many solutions: {s} (free variables arbitrary).',
     none='Row {i} has all-zero coefficients and right-hand side {v}, i.e. 0 = {v}: no solution.',
     noneFree='There is also a free variable, but the contradiction is checked first, so the answer is no solution.')),
}
sys.path.insert(0, here)
import ui
LEG = {
 'zh': ([('当前列', 'background:var(--hlbg);border-color:var(--hl)'), ('候选主元', 'border-color:var(--x)'), ('主元', 'background:var(--pivbg);border-color:var(--piv)'),
         ('这一步改过的行', 'background:var(--okbg);border-color:var(--ok)'), ('拿来消别人的主元行', 'border-color:var(--piv);border-style:dashed')], '<kbd>←</kbd> <kbd>→</kbd> 也能翻页'),
 'en': ([('current column', 'background:var(--hlbg);border-color:var(--hl)'), ('pivot candidate', 'border-color:var(--x)'), ('pivot', 'background:var(--pivbg);border-color:var(--piv)'),
         ('row changed in this step', 'background:var(--okbg);border-color:var(--ok)'), ('pivot row used to clear', 'border-color:var(--piv);border-style:dashed')], '<kbd>←</kbd> <kbd>→</kbd> also step'),
}
tpl = open(f'{here}/gauss_tpl.html', encoding='utf-8').read()
for lang, t in T.items():
    s = ui.fill(tpl, t, *LEG[lang])
    for k, v in t.items():
        if k != 'J':
            s = s.replace('%%' + k + '%%', v)
    s = s.replace('%%JSON%%', json.dumps(t['J'], ensure_ascii=False))
    assert '%%' not in s
    open(f'{wt}/static/maps/gauss-steps.{lang}.html', 'w', encoding='utf-8', newline='\n').write(s)

# ---------- lights out SVG ----------
C = dict(fg='#1f2328', mu='#57606a', line='#d0d7de', card='#f6f8fa', x='#0969da', xbg='#ddf4ff',
         hl='#bf3989', hlbg='#ffeff7', piv='#8250df', pivbg='#fbefff', ok='#1a7f37', okbg='#dafbe1')
S = {
 'zh': dict(font='PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif',
   t1='按开关 (2, 3)', s1='翻转十字形的 5 盏灯', s1b='= A 的第 9 列',
   t2='灯 (1, 1) 的方程', s2='只有 3 个开关会翻转它', s2b='= A 的第 1 行',
   t2e='x(1,1) ⊕ x(1,2) ⊕ x(2,1) = 灯 (1,1) 一开始的状态',
   t3='系数矩阵 A（30 × 30）', s3='行 = 灯，列 = 开关，黑格是 1', l3='第 9 列', l4='第 1 行',
   foot='按开关的顺序无所谓、按两次等于没按，所以每个开关是一个 0/1 未知数，每盏灯是一条模 2 方程。'),
 'en': dict(font='Helvetica, Arial, sans-serif',
   t1='Press switch (2, 3)', s1='flips the 5 lights in a plus', s1b='= column 9 of A',
   t2='The equation of light (1, 1)', s2='only 3 switches flip it', s2b='= row 1 of A',
   t2e='x(1,1) ⊕ x(1,2) ⊕ x(2,1) = initial state of light (1,1)',
   t3='Coefficient matrix A (30 × 30)', s3='rows = lights, columns = switches, black = 1', l3='column 9', l4='row 1',
   foot='Order does not matter and pressing twice cancels, so each switch is a 0/1 unknown and each light is one equation mod 2.'),
}
R, CC = 5, 6
def nb(i, j):
    return [(i + di, j + dj) for di, dj in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)) if 0 <= i + di < R and 0 <= j + dj < CC]
def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
def text(x, y, s, size=14, color=C['mu'], anchor='start', bold=False):
    fw = ' font-weight="700"' if bold else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}"{fw}>{esc(s)}</text>'
def grid(x0, y0, on, mark, color, bg, markcolor):
    o = []
    for i in range(R):
        for j in range(CC):
            x, y = x0 + j * 38, y0 + i * 38
            if (i, j) == mark:
                o.append(f'<rect x="{x}" y="{y}" width="34" height="34" rx="6" fill="{bg}" stroke="{markcolor}" stroke-width="3"/>')
            elif (i, j) in on:
                o.append(f'<rect x="{x}" y="{y}" width="34" height="34" rx="6" fill="{bg}" stroke="{color}" stroke-width="1.5"/>')
            else:
                o.append(f'<rect x="{x}" y="{y}" width="34" height="34" rx="6" fill="#ffffff" stroke="{C["line"]}"/>')
    return ''.join(o)
for lang, t in S.items():
    W, H = 1000, 470
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{t["font"]}">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    # panel 1
    o.append(f'<rect x="16" y="16" width="290" height="380" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(161, 46, t['t1'], 16, C['fg'], 'middle', True))
    o.append(grid(48, 70, nb(1, 2), (1, 2), C['hl'], C['hlbg'], C['hl']))
    o.append(text(161, 290, t['s1'], 14, C['fg'], 'middle'))
    o.append(text(161, 314, t['s1b'], 14, C['hl'], 'middle', True))
    # panel 2
    o.append(f'<rect x="322" y="16" width="290" height="380" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(467, 46, t['t2'], 16, C['fg'], 'middle', True))
    o.append(grid(354, 70, nb(0, 0), (0, 0), C['x'], C['xbg'], C['x']))
    o.append(text(467, 290, t['s2'], 14, C['fg'], 'middle'))
    o.append(text(467, 314, t['s2b'], 14, C['x'], 'middle', True))
    o.append(text(467, 350, t['t2e'], 12.5, C['mu'], 'middle'))
    # panel 3: matrix
    o.append(f'<rect x="628" y="16" width="356" height="380" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(806, 46, t['t3'], 16, C['fg'], 'middle', True))
    o.append(text(806, 68, t['s3'], 12.5, C['mu'], 'middle'))
    cs, x0, y0 = 9, 696, 86
    col9, row1 = 1 * CC + 2, 0
    o.append(f'<rect x="{x0 + col9 * cs}" y="{y0}" width="{cs}" height="{30 * cs}" fill="{C["hlbg"]}"/>')
    o.append(f'<rect x="{x0}" y="{y0 + row1 * cs}" width="{30 * cs}" height="{cs}" fill="{C["xbg"]}"/>')
    for r in range(30):
        ri, rj = divmod(r, CC)
        for c in range(30):
            ci, cj = divmod(c, CC)
            if abs(ri - ci) + abs(rj - cj) <= 1:
                fill = C['hl'] if c == col9 else (C['x'] if r == row1 else C['fg'])
                o.append(f'<rect x="{x0 + c * cs + 1}" y="{y0 + r * cs + 1}" width="{cs - 2}" height="{cs - 2}" fill="{fill}"/>')
    o.append(f'<rect x="{x0}" y="{y0}" width="{30 * cs}" height="{30 * cs}" fill="none" stroke="{C["line"]}"/>')
    o.append(text(x0 + col9 * cs + 4, y0 + 30 * cs + 18, '↑ ' + t['l3'], 12.5, C['hl'], 'middle', True))
    o.append(text(x0 - 5, y0 + 8, t['l4'] + ' →', 12.5, C['x'], 'end', True))
    o.append(text(500, 432, t['foot'], 14, C['fg'], 'middle'))
    o.append('</svg>')
    open(f'{wt}/static/images/algo/lights-out-matrix.{lang}.svg', 'w', encoding='utf-8', newline='\n').write('\n'.join(o))
print('ok')
