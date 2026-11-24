import sys
out = sys.argv[1]

C = dict(fg='#1f2328', mu='#57606a', line='#d0d7de', card='#f6f8fa',
         piv='#8250df', pivbg='#fbefff', bad='#cf222e', badbg='#ffebe9',
         free='#eaeef2', ok='#1a7f37', okbg='#dafbe1', x='#0969da', xbg='#ddf4ff', hl='#bf3989')

T = {
 'zh': dict(font='PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif',
   A_l='规范化前：行阶梯形', A_r='规范化后：简化行阶梯形',
   A_ops=['b[2] ^= b[0]', 'b[3] ^= b[2]', 'b[3] ^= b[0]'],
   A_red='红色：主元列里多出来的 1，要消掉', A_piv='紫色：主元（每行最高位）',
   A_free='灰色列：不是主元列，随便是什么', A_col='主元列 3、2、0 现在各只有一个 1',
   A_k='第 k 小（k 从 0 数）：k 的二进制 (c₂ c₁ c₀) 就是选法', A_krow='k', A_kbin='k 的二进制', A_val='值的二进制', A_dec='值',
   A_foot='值在主元位 3、2、0 上的三个比特正好就是 k 的三个比特，所以值的大小顺序和 k 一致',
   A_names='c₀ = b[0]，c₁ = b[2]，c₂ = b[3]（按主元位从低到高编号）',
   B_arr='数组（下标从 1 数）', B_t='每插入一个数之后的基：值@位置', B_after='插完 a',
   B_n3='a₃ = 011 位置更靠右，换下旧的 011@1，旧的被消成 0 丢掉',
   B_n4='a₄ = 100 进 b[2]，110@2 被挤下去，消成 001 存进 b[0]',
   B_q='询问 [3, 4]：只用位置 ≥ 3 的基', B_q2='100 ⊕ 011 = 111 = 7，和直接用 a₃ = 3、a₄ = 4 算的一样',
   B_drop='位置 2 < 3，不用', B_new='绿色：这一步新放进来的'),
 'en': dict(font='Helvetica, Arial, sans-serif',
   A_l='Before: row echelon form', A_r='After: reduced row echelon form',
   A_ops=['b[2] ^= b[0]', 'b[3] ^= b[2]', 'b[3] ^= b[0]'],
   A_red='Red: extra 1s in pivot columns, to clear', A_piv='Purple: pivots (highest bit of each row)',
   A_free='Grey column: not a pivot column, anything goes', A_col='Pivot columns 3, 2, 0 now each hold one 1',
   A_k='k-th smallest (k from 0): the bits of k (c₂ c₁ c₀) are the choice', A_krow='k', A_kbin='k in binary', A_val='value in binary', A_dec='value',
   A_foot='The value’s bits at pivots 3, 2, 0 are exactly the bits of k, so values sort in the order of k',
   A_names='c₀ = b[0], c₁ = b[2], c₂ = b[3] (numbered by pivot, low to high)',
   B_arr='Array (1-indexed)', B_t='Basis after each insertion: value@position', B_after='after a',
   B_n3='a₃ = 011 is further right, swaps out the old 011@1, which reduces to 0 and is dropped',
   B_n4='a₄ = 100 takes b[2]; 110@2 is pushed down, reduces to 001 and lands in b[0]',
   B_q='Query [3, 4]: use only basis vectors at position ≥ 3', B_q2='100 ⊕ 011 = 111 = 7, the same as using a₃ = 3 and a₄ = 4 directly',
   B_drop='position 2 < 3, unused', B_new='Green: placed in this step'),
}

def cell(x, y, txt, fill, stroke, color, w=34, h=32, bold=False, dash=False):
    d = ' stroke-dasharray="4 3"' if dash else ''
    fw = ' font-weight="700"' if bold else ''
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{fill}" stroke="{stroke}"{d}/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 5.5}" text-anchor="middle" font-family="Consolas, Menlo, monospace" font-size="16" fill="{color}"{fw}>{txt}</text>')

def text(x, y, s, size=14, color=C['mu'], anchor='start', bold=False, mono=False):
    s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    fw = ' font-weight="700"' if bold else ''
    ff = ' font-family="Consolas, Menlo, monospace"' if mono else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}"{fw}{ff}>{s}</text>'

def svg_rref(t):
    W, H = 1000, 640
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{t["font"]}">',
         '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#57606a"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    before = {3: 0b1101, 2: 0b0111, 1: 0, 0: 0b0001}
    after = {3: 0b1010, 2: 0b0110, 1: 0, 0: 0b0001}
    pivc = {3, 2, 0}
    def matrix(x0, y0, rows, reduced):
        s = []
        for j, c in enumerate([3, 2, 1, 0]):
            s.append(text(x0 + 70 + j * 40 + 17, y0, c, 13, C['mu'], 'middle', mono=True))
        if not reduced:
            pass
        else:
            for j, c in enumerate([3, 2, 1, 0]):
                if c in pivc:
                    s.append(f'<rect x="{x0 + 66 + j * 40}" y="{y0 + 8}" width="42" height="{4 * 40 + 4}" rx="7" fill="none" stroke="{C["piv"]}" stroke-width="1.5" stroke-dasharray="5 4"/>')
        for r, i in enumerate([3, 2, 1, 0]):
            y = y0 + 12 + r * 40
            s.append(text(x0 + 56, y + 21, f'b[{i}]', 14, C['mu'], 'end', mono=True))
            v = rows[i]
            for j, c in enumerate([3, 2, 1, 0]):
                x = x0 + 70 + j * 40
                if not v:
                    s.append(cell(x, y, '', '#ffffff', C['line'], C['mu'], dash=True))
                    continue
                bit = v >> c & 1
                if c == i:
                    s.append(cell(x, y, bit, C['pivbg'], C['piv'], C['piv'], bold=True))
                elif c in pivc and bit and not reduced:
                    s.append(cell(x, y, bit, C['badbg'], C['bad'], C['bad'], bold=True))
                elif c == 1:
                    s.append(cell(x, y, bit, C['free'], C['line'], C['fg']))
                else:
                    s.append(cell(x, y, bit, C['card'], C['line'], C['fg']))
            s.append(text(x0 + 70 + 4 * 40 + 8, y + 21, f'= {v}' if v else '', 14, C['mu'], mono=True))
        return ''.join(s)
    o.append(f'<rect x="20" y="16" width="370" height="250" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(f'<rect x="610" y="16" width="370" height="250" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(205, 42, t['A_l'], 16, C['fg'], 'middle', True))
    o.append(text(795, 42, t['A_r'], 16, C['fg'], 'middle', True))
    o.append(matrix(60, 66, before, False))
    o.append(matrix(650, 66, after, True))
    o.append(f'<line x1="402" y1="140" x2="598" y2="140" stroke="#57606a" stroke-width="2" marker-end="url(#arr)"/>')
    o.append(text(500, 128, 'reduce()', 14, C['mu'], 'middle', mono=True))
    for n, op in enumerate(t['A_ops']):
        o.append(text(500, 168 + n * 22, f'{n + 1}. {op}', 14, C['fg'], 'middle', mono=True))
    o.append(text(40, 290, t['A_piv'], 13.5, C['piv']))
    o.append(text(40, 310, t['A_red'], 13.5, C['bad']))
    o.append(text(630, 290, t['A_col'], 13.5, C['piv']))
    o.append(text(630, 310, t['A_free'], 13.5, C['mu']))
    # bottom: k table
    o.append(f'<rect x="20" y="330" width="960" height="294" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(40, 358, t['A_k'], 16, C['fg'], bold=True))
    o.append(text(40, 382, t['A_names'], 13.5, C['mu']))
    basis = [0b0001, 0b0110, 0b1010]
    pbit = [0, 2, 3]
    colx0, colw = 190, 98
    o.append(text(176, 424, t['A_krow'], 14, C['mu'], 'end'))
    o.append(text(176, 466, t['A_kbin'], 14, C['mu'], 'end'))
    o.append(text(176, 520, t['A_val'], 14, C['mu'], 'end'))
    o.append(text(176, 566, t['A_dec'], 14, C['mu'], 'end'))
    kc = [C['x'], C['ok'], C['hl']]
    for k in range(8):
        cx = colx0 + k * colw + colw / 2
        o.append(text(cx, 424, k, 15, C['fg'], 'middle', True, mono=True))
        # k binary: c2 c1 c0
        for j, t_ in enumerate([2, 1, 0]):
            b = k >> t_ & 1
            o.append(cell(cx - 39 + j * 26, 448, b, '#ffffff', kc[t_], kc[t_], w=24, h=28, bold=True))
        v = 0
        for t_ in range(3):
            if k >> t_ & 1:
                v ^= basis[t_]
        for j, c in enumerate([3, 2, 1, 0]):
            b = v >> c & 1
            if c in pbit:
                t_ = pbit.index(c)
                o.append(cell(cx - 45 + j * 23, 502, b, '#ffffff', kc[t_], kc[t_], w=21, h=28, bold=True))
            else:
                o.append(cell(cx - 45 + j * 23, 502, b, C['free'], C['line'], C['mu'], w=21, h=28))
        o.append(text(cx, 566, v, 16, C['fg'], 'middle', True, mono=True))
    o.append(text(500, 604, t['A_foot'], 14, C['fg'], 'middle'))
    o.append('</svg>')
    return '\n'.join(o)

def svg_prefix(t):
    W, H = 1000, 560
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{t["font"]}">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    a = [5, 6, 3, 4]
    o.append(text(40, 40, t['B_arr'], 15, C['fg'], bold=True))
    for p, v in enumerate(a, 1):
        x = 230 + (p - 1) * 110
        o.append(cell(x, 18, f'{v:03b}', '#ffffff', C['x'], C['x'], w=70, h=32, bold=True))
        o.append(text(x + 35, 68, f'a{"₁₂₃₄"[p - 1]} = {v}', 13, C['mu'], 'middle'))
    # timeline
    o.append(f'<rect x="20" y="84" width="960" height="270" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(40, 112, t['B_t'], 15, C['fg'], bold=True))
    o.append(text(960, 112, t['B_new'], 13, C['ok'], 'end'))
    states = [
        {2: ('101', 1), 1: None, 0: None},
        {2: ('110', 2), 1: ('011', 1), 0: None},
        {2: ('110', 2), 1: ('011', 3), 0: None},
        {2: ('100', 4), 1: ('011', 3), 0: ('001', 2)},
    ]
    new = [{2}, {2, 1}, {1}, {2, 0}]
    for p in range(4):
        x = 150 + p * 205
        o.append(text(x + 70, 142, f'{t["B_after"]}{"₁₂₃₄"[p]}', 14, C['mu'], 'middle', True))
        for r, i in enumerate([2, 1, 0]):
            y = 154 + r * 42
            if p == 0:
                o.append(text(120, y + 22, f'b[{i}]', 14, C['mu'], 'end', mono=True))
            s = states[p][i]
            if s is None:
                o.append(cell(x, y, '', '#ffffff', C['line'], C['mu'], w=140, h=34, dash=True))
            elif i in new[p]:
                o.append(cell(x, y, f'{s[0]} @{s[1]}', C['okbg'], C['ok'], C['ok'], w=140, h=34, bold=True))
            else:
                o.append(cell(x, y, f'{s[0]} @{s[1]}', '#ffffff', C['line'], C['fg'], w=140, h=34))
    o.append(text(40, 312, '③ ' + t['B_n3'], 13.5, C['fg']))
    o.append(text(40, 336, '④ ' + t['B_n4'], 13.5, C['fg']))
    # query
    o.append(f'<rect x="20" y="370" width="960" height="174" rx="10" fill="{C["card"]}" stroke="{C["line"]}"/>')
    o.append(text(40, 398, t['B_q'], 15, C['fg'], bold=True))
    fin = states[3]
    for r, i in enumerate([2, 1, 0]):
        y = 412 + r * 40
        v, p = fin[i]
        o.append(text(120, y + 22, f'b[{i}]', 14, C['mu'], 'end', mono=True))
        if p >= 3:
            o.append(cell(150, y, f'{v} @{p}', C['pivbg'], C['piv'], C['piv'], w=140, h=34, bold=True))
        else:
            o.append(f'<g opacity="0.45">{cell(150, y, f"{v} @{p}", "#ffffff", C["line"], C["mu"], w=140, h=34, dash=True)}</g>')
            o.append(text(306, y + 22, t['B_drop'], 13.5, C['mu']))
    o.append(text(330, 448, t['B_q2'], 14.5, C['fg']))
    o.append('</svg>')
    return '\n'.join(o)

for lang, t in T.items():
    open(f'{out}/xor-basis-rref-kth.{lang}.svg', 'w', encoding='utf-8', newline='\n').write(svg_rref(t))
    open(f'{out}/xor-basis-prefix.{lang}.svg', 'w', encoding='utf-8', newline='\n').write(svg_prefix(t))
