"""Shared look for the step-by-step animations in static/maps/ (algo posts).

Spec: one card layout; icon buttons (restart / back / play-pause / next, next is primary);
step counter + progress bar; colour legend as chips; the explanation panel (and any other
part whose height varies between steps) gets a min-height equal to the tallest step, so the
frame never changes height while stepping.
"""

ICON = {
    'reset': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 2.7-6.4"/><path d="M3 4v5h5"/></svg>',
    'prev': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>',
    'next': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>',
    'play': '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="fill" d="M7 4.5v15l12.5-7.5z"/></svg>',
    'pause': '<svg viewBox="0 0 24 24" aria-hidden="true"><rect class="fill" x="6" y="5" width="4" height="14" rx="1"/><rect class="fill" x="14" y="5" width="4" height="14" rx="1"/></svg>',
}

CSS = r"""
:root { --bg:#ffffff; --fg:#1f2328; --muted:#57606a; --line:#d0d7de; --card:#f6f8fa; --hl:#bf3989; --hlbg:#ffeff7;
  --x:#0969da; --xbg:#ddf4ff; --ok:#1a7f37; --okbg:#dafbe1; --bad:#cf222e; --badbg:#ffebe9; --piv:#8250df; --pivbg:#fbefff;
  --free:#eaeef2; --pri:#0969da; --prifg:#ffffff; --shadow:0 1px 2px rgba(31,35,40,.06); }
.dark { --bg:#17161b; --fg:#e9e7ef; --muted:#a19caf; --line:#3a3945; --card:#1f1e25; --hl:#ff7bb0; --hlbg:#3a1f2d;
  --x:#58a6ff; --xbg:#132a44; --ok:#3fb950; --okbg:#12301c; --bad:#ff7b72; --badbg:#4a1d22; --piv:#d2a8ff; --pivbg:#2e2148;
  --free:#2a2932; --pri:#58a6ff; --prifg:#0d1117; --shadow:none; }
html, body { margin: 0; background: var(--bg); color: var(--fg); overflow: hidden; }
body { font: 15px/1.65 %%font%%; }
.wrap { max-width: 860px; margin: 0 auto; padding: 14px 16px 12px; box-sizing: border-box; display: flex; flex-direction: column; gap: 10px; }
.stage { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; box-shadow: var(--shadow); overflow-x: auto; }
.seg { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; border-radius: 10px; background: var(--card); border: 1px solid var(--line); }
.seg button { border: 0; background: none; color: var(--muted); padding: 4px 14px; border-radius: 8px; font: inherit; font-size: 14px; cursor: pointer; }
.seg button:hover { color: var(--fg); }
.seg button.on { background: var(--bg); color: var(--fg); font-weight: 700; box-shadow: 0 0 0 1px var(--line), var(--shadow); }
.panel { box-sizing: border-box; padding: 12px 14px; background: var(--bg); border: 1px solid var(--line); border-left: 4px solid var(--hl); border-radius: 10px; }
.panel .ph { display: flex; align-items: center; gap: 8px; font-weight: 700; }
.panel .badge { display: inline-grid; place-items: center; min-width: 22px; height: 22px; padding: 0 6px; box-sizing: border-box; border-radius: 999px; background: var(--hl); color: #fff; font-size: 12.5px; font-weight: 700; }
.panel .t { margin: 6px 0 0; }
.panel.ok { border-left-color: var(--ok); } .panel.ok .badge { background: var(--ok); } .panel.ok .t { color: var(--ok); }
.panel.bad { border-left-color: var(--bad); } .panel.bad .badge { background: var(--bad); } .panel.bad .t { color: var(--bad); }
.ctl { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.ib { display: inline-flex; align-items: center; gap: 6px; font: inherit; font-size: 14px; line-height: 1; padding: 7px 14px; border-radius: 999px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); cursor: pointer; box-shadow: var(--shadow); }
.ib svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; flex: none; }
.ib svg .fill { fill: currentColor; stroke: none; }
.ib:hover { border-color: var(--pri); color: var(--pri); }
.ib.pri { background: var(--pri); border-color: var(--pri); color: var(--prifg); font-weight: 700; }
.ib.pri:hover { filter: brightness(1.08); color: var(--prifg); }
.ib:disabled { opacity: .38; cursor: default; filter: none; }
.ib:disabled:hover { border-color: var(--line); color: var(--fg); }
.ib.pri:disabled:hover { border-color: var(--pri); color: var(--prifg); }
.prog { margin-left: auto; display: flex; align-items: center; gap: 10px; color: var(--muted); font: 13px Consolas, Menlo, monospace; white-space: nowrap; }
.prog .bar { width: 120px; height: 6px; border-radius: 999px; background: var(--free); overflow: hidden; }
.prog .bar i { display: block; height: 100%; width: 0; background: var(--pri); border-radius: 999px; transition: width .25s; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 14px; height: 14px; border-radius: 4px; border: 1.5px solid; box-sizing: border-box; display: inline-block; }
.legend .kbd { margin-left: auto; }
kbd { font: 12px Consolas, Menlo, monospace; padding: 0 5px; border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; background: var(--card); color: var(--fg); }
@media (max-width: 560px) { .prog { margin-left: 0; width: 100%; } .prog .bar { flex: 1; } .ib { padding: 7px 11px; } .legend .kbd { display: none; } }
"""

def controls(t):
    return ('<div class="ctl">'
            f'<button class="ib" id="reset" title="{t["reset"]}">{ICON["reset"]}<span>{t["reset"]}</span></button>'
            f'<button class="ib" id="prev" title="{t["prev"]}">{ICON["prev"]}<span>{t["prev"]}</span></button>'
            f'<button class="ib" id="play">{ICON["play"]}<span>{t["play"]}</span></button>'
            f'<button class="ib pri" id="next" title="{t["next"]}"><span>{t["next"]}</span>{ICON["next"]}</button>'
            '<div class="prog"><div class="bar"><i id="bar"></i></div><span id="cnt"></span></div>'
            '</div>')

def legend(items, kbd):
    """items: list of (label, css for the swatch)"""
    s = ''.join(f'<span><i style="{css}"></i>{lab}</span>' for lab, css in items)
    return f'<div class="legend">{s}<span class="kbd">{kbd}</span></div>'

# JS shared by both pages: theme sync, iframe fit, play button, progress, height lock helper
JS = r"""
  var root = document.documentElement;
  function theme() {
    var t = null;
    try { if (window.parent !== window) t = window.parent.document.documentElement.dataset.theme; } catch (e) {}
    if (!t) t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    root.classList.toggle('dark', t !== 'light');
  }
  theme();
  try { if (window.parent !== window) new MutationObserver(theme).observe(window.parent.document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); } catch (e) {}
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', theme);
  function fit() {
    try {
      var f = window.frameElement; if (!f) return;
      var h = Math.ceil(document.querySelector('.wrap').getBoundingClientRect().height) + (f.offsetHeight - f.clientHeight);
      if (Math.abs(parseFloat(f.style.height || 0) - h) > 0.5) f.style.height = h + 'px';
    } catch (e) {}
  }
  var ICON_PLAY = %%ICON_PLAY%%, ICON_PAUSE = %%ICON_PAUSE%%;
  function playBtn(on) { document.getElementById('play').innerHTML = (on ? ICON_PAUSE : ICON_PLAY) + '<span>' + (on ? UI.pause : UI.play) + '</span>'; }
  function progress(k, n) {
    document.getElementById('cnt').textContent = (k + 1) + ' / ' + n;
    document.getElementById('bar').style.width = (n > 1 ? 100 * k / (n - 1) : 100) + '%';
    document.getElementById('prev').disabled = k === 0;
    document.getElementById('next').disabled = k === n - 1;
  }
  // give each element a min-height equal to its tallest state; measure(fn) must visit every state
  function lockHeights(els, visitAll) {
    els.forEach(function (el) { el.style.minHeight = ''; });
    var h = els.map(function () { return 0; });
    visitAll(function () { els.forEach(function (el, i) { h[i] = Math.max(h[i], el.offsetHeight); }); });
    els.forEach(function (el, i) { el.style.minHeight = h[i] + 'px'; });
  }
"""

def fill(tpl, t, legend_items, kbd):
    import json
    s = tpl.replace('%%UICSS%%', CSS).replace('%%CONTROLS%%', controls(t)).replace('%%LEGEND%%', legend(legend_items, kbd))
    s = s.replace('%%UIJS%%', JS.replace('%%ICON_PLAY%%', json.dumps(ICON['play'])).replace('%%ICON_PAUSE%%', json.dumps(ICON['pause'])))
    return s
