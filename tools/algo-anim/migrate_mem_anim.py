"""One-off: move the memory-ordering animations (static/maps/store-path.*, release-acquire.*) onto the
shared spec in ui.py. Keeps the SVG and its step data; replaces style, panel, controls, legend and script.
Run from the repo root: python tools/algo-anim/migrate_mem_anim.py
"""
import re, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui

KBD = {'zh': '<kbd>←</kbd> <kbd>→</kbd> 也能翻页', 'en': '<kbd>←</kbd> <kbd>→</kbd> also step'}
BTN = {'zh': dict(reset='重来', prev='上一步', next='下一步'), 'en': dict(reset='Restart', prev='Back', next='Next')}

EXTRA_CSS = r"""
.wrap svg#sp { display: block; width: 100%; height: auto; }
.note { margin: 8px 0 0; padding-top: 8px; border-top: 1px dashed var(--line); color: var(--muted); font-size: 14px; }
.note b { color: var(--fg); }
.legend b { display: inline-grid; place-items: center; min-width: 22px; height: 20px; border-radius: 4px; border: 1.5px solid; font: 700 12.5px Consolas, Menlo, monospace; }
.lM { background: #ffebe9; border-color: #cf222e !important; color: #a40e26; }
.lE { background: #fbefff; border-color: #8250df !important; color: #6639ba; }
.lS { background: #dafbe1; border-color: #1a7f37 !important; color: #116329; }
.lI { background: #f6f8fa; border-color: #8c959f !important; border-style: dashed !important; color: #6e7781; }
.dark .lM { background: #4a1d22; border-color: #f85149 !important; color: #ffa198; }
.dark .lE { background: #2e2148; border-color: #a371f7 !important; color: #d2a8ff; }
.dark .lS { background: #12301c; border-color: #3fb950 !important; color: #7ee787; }
.dark .lI { background: #26252d; border-color: #6e6a7a !important; color: #a19caf; }
"""

SCRIPT = r"""<script>
(function () {
  %%D%%
  var UI = { play: D.play, pause: D.pause };
%%UIJS%%
  var svg = document.getElementById('sp'), LAST = %%LAST%%, k = 0, timer = null;
  var parts = svg.querySelectorAll('[data-from]');
  svg.querySelectorAll('%%SEL%%').forEach(function (p) {
    p.style.setProperty('--len', Math.ceil(p.getTotalLength ? p.getTotalLength() : 600));
  });
  var head = document.getElementById('head'), txt = document.getElementById('txt'), note = document.getElementById('note');
  var badge = document.getElementById('badge'), panel = document.getElementById('panel');
  function fill(n) {
    badge.hidden = n === 0;
    badge.textContent = n;
    var c = D.colors[n];
    badge.style.background = !c || c === '#1f2328' ? 'var(--muted)' : c;
    head.textContent = D.titles[n];
    txt.textContent = D.texts[n];
    note.hidden = n !== LAST;
  }
  function show(n, quiet) {
    k = Math.max(0, Math.min(LAST, n));
    parts.forEach(function (el) {
      var on = k >= +el.dataset.from && k <= +el.dataset.to;
      el.classList.toggle('hide', !on);
      el.classList.remove('cur');
      if (on && el.dataset.step !== undefined && +el.dataset.step === k) { void el.getBBox(); el.classList.add('cur'); }
    });
    fill(k);
    progress(k, LAST + 1);
    document.getElementById('cnt').textContent = k + ' / ' + LAST;
    if (!quiet) fit();
  }
  function lock() {
    var save = k;
    lockHeights([panel], function (measure) { for (var n = 0; n <= LAST; n++) { fill(n); measure(); } });
    show(save);
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } playBtn(false); }
  function play() {
    if (timer) { stop(); return; }
    if (k === LAST) show(0);
    playBtn(true);
    timer = setInterval(function () { if (k >= LAST) stop(); else show(k + 1); }, 2400);
  }
  document.getElementById('prev').onclick = function () { stop(); show(k - 1); };
  document.getElementById('next').onclick = function () { stop(); show(k + 1); };
  document.getElementById('play').onclick = play;
  document.getElementById('reset').onclick = function () { stop(); show(0); };
  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') { stop(); show(k + 1); }
    if (e.key === 'ArrowLeft') { stop(); show(k - 1); }
  });
  var rz = null;
  window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(lock, 120); });
  window.addEventListener('load', lock);
  show(0, true);
  lock();
})();
</script>"""

for name in ('store-path', 'release-acquire'):
    for lang in ('zh', 'en'):
        p = f'static/maps/{name}.{lang}.html'
        s = open(p, encoding='utf-8').read()
        if 'class="ctl"' in s:
            print('already migrated', p); continue
        font = re.search(r'body \{ font: 15px/1\.65 ([^;]+); \}', s).group(1)
        D = re.search(r'^  (var D = \{.*\};)$', s, re.M).group(1)
        play = json.loads(D[len('var D = '):-1])['play']
        LAST = re.search(r'LAST = (\d+)', s).group(1)
        SEL = re.search(r"svg\.querySelectorAll\('([^']+)'\)\.forEach", s).group(1)
        note = re.search(r'(<p class="note" id="note" hidden>.*?</p>)', s, re.S).group(1)
        legend_spans = re.search(r'<div class="legend">(.*?)</div>', s, re.S).group(1)
        svg = re.search(r'(<svg xmlns.*?</svg>)', s, re.S).group(1)
        head = s[:s.index('<style>')]
        t = dict(BTN[lang], play=play)
        css = ui.CSS.replace('%%font%%', font) + EXTRA_CSS
        body = ('<body>\n<div class="wrap">\n' + svg + '\n'
                '<div class="panel" id="panel"><div class="ph"><span class="badge" id="badge"></span><span id="head"></span></div>'
                '<p class="ptxt" id="txt"></p>\n  ' + note + '\n</div>\n'
                + ui.controls(t) + '\n'
                f'<div class="legend">{legend_spans}<span class="kbd">{KBD[lang]}</span></div>\n'
                '</div>\n')
        script = SCRIPT.replace('%%D%%', D).replace('%%LAST%%', LAST).replace('%%SEL%%', SEL)
        script = script.replace('%%UIJS%%', ui.JS.replace('%%ICON_PLAY%%', json.dumps(ui.ICON['play'])).replace('%%ICON_PAUSE%%', json.dumps(ui.ICON['pause'])))
        out = head + '<style>' + css + '</style>\n</head>\n' + body + script + '\n</body>\n</html>\n'
        assert '%%' not in out
        open(p, 'w', encoding='utf-8', newline='\n').write(out)
        print('migrated', p)
