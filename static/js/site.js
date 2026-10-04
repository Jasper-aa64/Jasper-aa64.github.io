/* Jasper — site behaviour. No dependencies; every feature checks for its own markup. */
(function () {
  "use strict";
  window.__siteReady = true;

  var root = document.documentElement;
  var reduce = root.classList.contains("reduce-motion");
  var I18N = window.SITE_I18N || { copy: "Copy", copied: "Copied", copyAria: "Copy code" };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  };

  /* ---------- Theme ---------- */
  var themeBtn = document.querySelector(".theme-btn");
  if (themeBtn) {
    var sync = function () { themeBtn.setAttribute("aria-pressed", String(root.dataset.theme === "dark")); };
    sync();
    var flip = function () {
      root.classList.add("theme-switching");
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      store.set("theme", root.dataset.theme);
      sync();
      void root.offsetWidth;
      setTimeout(function () { root.classList.remove("theme-switching"); }, 60);
    };
    themeBtn.addEventListener("click", function () {
      if (document.startViewTransition && !reduce) document.startViewTransition(flip);
      else flip();
    });
  }

  /* ---------- Mobile nav ---------- */
  var navBtn = document.querySelector(".nav-btn");
  var nav = document.getElementById("site-nav");
  if (navBtn && nav) {
    var setOpen = function (open) {
      root.classList.toggle("nav-open", open);
      navBtn.setAttribute("aria-expanded", String(open));
    };
    navBtn.addEventListener("click", function () { setOpen(!root.classList.contains("nav-open")); });
    nav.addEventListener("click", function (e) { if (e.target.closest("a")) setOpen(false); });
    window.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });
    window.addEventListener("resize", function () { if (window.innerWidth > 760) setOpen(false); }, { passive: true });
  }

  /* ---------- Header border, reading progress ---------- */
  var header = document.querySelector(".site-header");
  var bar = document.querySelector(".read-progress span");
  var article = document.querySelector(".post-body");
  var onScroll = function () {
    var y = window.scrollY;
    if (header) header.classList.toggle("is-scrolled", y > 8);
    if (bar && article) {
      var r = article.getBoundingClientRect();
      var total = r.height - window.innerHeight * 0.6;
      var p = total > 0 ? Math.min(1, Math.max(0, -r.top / total)) : 1;
      bar.style.setProperty("--progress", p.toFixed(4));
    }
  };
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { onScroll(); ticking = false; });
  }, { passive: true });
  onScroll();

  /* ---------- Reveal on scroll ---------- */
  var reveals = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  if (root.classList.contains("reveal-ready")) {
    if (!("IntersectionObserver" in window)) {
      root.classList.remove("reveal-ready");
    } else {
      var groups = new Map();
      reveals.forEach(function (el) {
        var n = groups.get(el.parentNode) || 0;
        el.style.setProperty("--d", Math.min(n, 6) * 55 + "ms");
        groups.set(el.parentNode, n + 1);
      });
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
        });
      }, { rootMargin: "0px 0px -6% 0px", threshold: 0.05 });
      reveals.forEach(function (el) { io.observe(el); });
    }
  }

  /* ---------- Photo deck ---------- */
  var deck = document.querySelector("[data-deck]");
  if (deck) {
    var cards = Array.prototype.slice.call(deck.querySelectorAll(".deck__card"));
    var busy = false;
    var order = cards.slice();
    var place = function () { order.forEach(function (c, i) { c.dataset.pos = String(i); }); };
    var advance = function () {
      if (busy || order.length < 2) return;
      var front = order.shift();
      order.push(front);
      if (reduce) { place(); return; }
      busy = true;
      front.classList.add("is-leaving");
      order.forEach(function (c, i) { if (c !== front) c.dataset.pos = String(i); });
      setTimeout(function () {
        front.classList.add("no-anim");
        front.classList.remove("is-leaving");
        place();
        void front.offsetWidth;
        front.classList.remove("no-anim");
        busy = false;
      }, 480);
    };
    deck.addEventListener("click", advance);
    deck.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); advance(); }
    });
  }

  /* ---------- Home showcase: auto-slides on wide screens, pauses on hover / focus / hidden tab ---------- */
  var show = document.querySelector("[data-showcase]");
  if (show) {
    var track = show.querySelector(".showcase__track");
    var slides = Array.prototype.slice.call(show.querySelectorAll(".slide"));
    var dots = Array.prototype.slice.call(show.querySelectorAll(".showcase__dot"));
    var wide = window.matchMedia("(min-width: 1200px)");
    var cur = 0, timer = null, hold = false;
    var go = function (n) {
      cur = (n + slides.length) % slides.length;
      track.style.transform = "translateX(" + (-100 * cur) + "%)";
      slides.forEach(function (sl, i) {
        var on = i === cur;
        sl.setAttribute("aria-hidden", on ? "false" : "true");
        sl.tabIndex = on ? 0 : -1;
      });
      dots.forEach(function (d, i) { d.classList.toggle("is-on", i === cur); });
    };
    var stop = function () { if (timer) { clearInterval(timer); timer = null; } };
    var start = function () {
      stop();
      if (reduce || hold || slides.length < 2 || !wide.matches || document.hidden) return;
      timer = setInterval(function () { go(cur + 1); }, 5000);
    };
    var wake = function () {
      if (!wide.matches) return;
      show.querySelectorAll("img[loading=lazy]").forEach(function (im) { im.loading = "eager"; });
      start();
    };
    dots.forEach(function (d) { d.addEventListener("click", function () { go(+d.dataset.go); start(); }); });
    show.querySelectorAll("[data-step]").forEach(function (b) {
      b.addEventListener("click", function () { go(cur + +b.dataset.step); });
    });
    show.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); go(cur - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(cur + 1); }
    });
    show.addEventListener("mouseenter", function () { hold = true; stop(); });
    show.addEventListener("mouseleave", function () { hold = false; start(); });
    show.addEventListener("focusin", function () { hold = true; stop(); });
    show.addEventListener("focusout", function () { hold = false; start(); });
    document.addEventListener("visibilitychange", start);
    if (wide.addEventListener) wide.addEventListener("change", wake);
    wake();
  }

  /* ---------- Notes filter: top level (#lowlatency) and second level (#algorithms/number-theory) ---------- */
  var writing = document.querySelector("[data-writing]");
  if (writing) {
    var tops = Array.prototype.slice.call(writing.querySelectorAll("[data-filter]"));
    var subRows = Array.prototype.slice.call(writing.querySelectorAll("[data-subs-for]"));
    var entries = Array.prototype.slice.call(writing.querySelectorAll(".card"));
    var empty = writing.querySelector("[data-empty]");
    var state = { key: "all", sub: "" };
    var press = function (els, test) {
      els.forEach(function (b) { var on = test(b); b.classList.toggle("is-active", on); b.setAttribute("aria-pressed", String(on)); });
    };
    var apply = function (key, sub, push) {
      if (!tops.some(function (b) { return b.dataset.filter === key; })) { key = "all"; sub = ""; }
      var row = null;
      subRows.forEach(function (r) { var on = r.dataset.subsFor === key; r.hidden = !on; if (on) row = r; });
      var chips = row ? Array.prototype.slice.call(row.querySelectorAll("[data-sub]")) : [];
      if (!chips.some(function (c) { return c.dataset.sub === sub; })) sub = "";
      state = { key: key, sub: sub };
      press(tops, function (b) { return b.dataset.filter === key; });
      press(chips, function (c) { return c.dataset.sub === sub; });
      var shown = 0;
      entries.forEach(function (el) {
        var vis = key === "all" || (el.dataset.series === key && (!sub || el.dataset.sub === sub));
        el.hidden = !vis;
        if (vis) shown++;
      });
      if (empty) empty.hidden = shown > 0;
      if (push) history.replaceState(null, "", key === "all" ? location.pathname : "#" + key + (sub ? "/" + sub : ""));
    };
    tops.forEach(function (b) { b.addEventListener("click", function () { apply(b.dataset.filter, "", true); }); });
    subRows.forEach(function (r) {
      r.addEventListener("click", function (e) {
        var c = e.target.closest("[data-sub]");
        if (c) apply(state.key, c.dataset.sub, true);
      });
    });
    var legacy = { trading: "lowlatency", topics: "lowlatency", engineering: "ainative" };
    var fromHash = function () {
      var parts = decodeURIComponent(location.hash.replace("#", "")).split("/");
      apply(legacy[parts[0]] || parts[0] || "all", parts[1] || "", false);
    };
    window.addEventListener("hashchange", fromHash);
    fromHash();
  }

  /* ---------- Table of contents: highlight the section being read ---------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".toc a"));
  if (tocLinks.length && article) {
    var ids = [];
    tocLinks.forEach(function (a) {
      var id = decodeURIComponent((a.getAttribute("href") || "").replace(/^#/, ""));
      if (id && ids.indexOf(id) < 0) ids.push(id);
    });
    var heads = ids.map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var side = document.querySelector(".toc-side");
    var current = null;
    var mark = function () {
      var line = 140;
      var active = heads[0];
      for (var i = 0; i < heads.length; i++) {
        if (heads[i].getBoundingClientRect().top <= line) active = heads[i]; else break;
      }
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) active = heads[heads.length - 1];
      if (!active || active === current) return;
      current = active;
      tocLinks.forEach(function (a) {
        var on = decodeURIComponent(a.getAttribute("href")) === "#" + active.id;
        a.classList.toggle("is-active", on);
        if (on && side && side.contains(a)) {
          var top = a.offsetTop, h = side.clientHeight;
          if (top < side.scrollTop + 40 || top > side.scrollTop + h - 60) side.scrollTo({ top: top - h / 3, behavior: reduce ? "auto" : "smooth" });
        }
      });
    };
    if (heads.length) {
      window.addEventListener("scroll", function () { requestAnimationFrame(mark); }, { passive: true });
      mark();
    }
    document.querySelectorAll(".toc-mobile a").forEach(function (a) {
      a.addEventListener("click", function () { var d = a.closest("details"); if (d) d.open = false; });
    });
  }

  /* ---------- Code blocks: language label + copy ---------- */
  if (article) {
    article.querySelectorAll("pre").forEach(function (pre) {
      var host = pre.closest(".highlight") || pre;
      if (host.parentNode.classList && host.parentNode.classList.contains("code-block")) return;
      var code = pre.querySelector("code");
      var lang = code && (code.dataset.lang || (code.className.match(/language-(\S+)/) || [])[1]);
      var wrap = document.createElement("div");
      wrap.className = "code-block" + (lang ? " has-lang" : "");
      host.parentNode.insertBefore(wrap, host);
      wrap.appendChild(host);
      var barEl = document.createElement("div");
      barEl.className = "code-block__bar";
      var label = document.createElement("span");
      label.className = "code-block__lang";
      label.textContent = lang || "";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "code-block__copy";
      btn.textContent = I18N.copy;
      btn.setAttribute("aria-label", I18N.copyAria);
      barEl.appendChild(label);
      barEl.appendChild(btn);
      wrap.appendChild(barEl);
      btn.addEventListener("click", function () {
        var text = (code || pre).innerText;
        var done = function () {
          btn.textContent = I18N.copied;
          btn.classList.add("is-copied");
          setTimeout(function () { btn.textContent = I18N.copy; btn.classList.remove("is-copied"); }, 1500);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
        } else { fallbackCopy(text); done(); }
      });
    });
    article.querySelectorAll("table").forEach(function (t) {
      if (t.closest("svg") || (t.parentNode.classList && t.parentNode.classList.contains("table-wrap"))) return;
      var w = document.createElement("div");
      w.className = "table-wrap";
      t.parentNode.insertBefore(w, t);
      w.appendChild(t);
    });
  }
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    ta.remove();
  }

  /* ---------- Language preference + "no Chinese version" notice ---------- */
  var lang = root.dataset.siteLang;
  var hasZh = root.dataset.hasZh === "true";
  if (lang === "zh") store.set("lang", "zh");
  else if (hasZh) store.set("lang", "en");
  /* Switching language keeps your place: same heading (translations share structure) plus the
     offset past it on articles, the same scroll fraction everywhere else. */
  var anchors = function () {
    return Array.prototype.slice.call(document.querySelectorAll(".post-body h1[id], .post-body h2[id], .post-body h3[id], .post-body h4[id]"));
  };
  var maxScroll = function () { return Math.max(1, document.documentElement.scrollHeight - window.innerHeight); };
  document.querySelectorAll("[data-lang-target]").forEach(function (a) {
    a.addEventListener("click", function () {
      store.set("lang", a.dataset.langTarget);
      var state = { to: a.pathname, ratio: window.scrollY / maxScroll(), idx: -1, off: 0, y: window.scrollY };
      var hs = anchors();
      for (var i = 0; i < hs.length; i++) {
        var top = hs[i].getBoundingClientRect().top + window.scrollY;
        if (top <= window.scrollY + 100) { state.idx = i; state.off = window.scrollY - top; } else break;
      }
      try { sessionStorage.setItem("langScroll", JSON.stringify(state)); } catch (e) {}
    });
  });
  (function restore() {
    var raw = null;
    try { raw = sessionStorage.getItem("langScroll"); sessionStorage.removeItem("langScroll"); } catch (e) {}
    if (!raw) return;
    var st; try { st = JSON.parse(raw); } catch (e) { return; }
    if (!st || st.to !== location.pathname || location.hash || st.y < 4) return;
    var target = function () {
      var hs = anchors();
      if (st.idx >= 0 && hs[st.idx]) return hs[st.idx].getBoundingClientRect().top + window.scrollY + st.off;
      return st.ratio * maxScroll();
    };
    var userMoved = false;
    var go = function () { if (!userMoved) window.scrollTo({ top: target(), behavior: "instant" }); };
    go();
    setTimeout(function () {
      ["wheel", "touchstart", "keydown"].forEach(function (ev) { window.addEventListener(ev, function () { userMoved = true; }, { once: true, passive: true }); });
    }, 0);
    window.addEventListener("load", go);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(go);
  })();
  var notice = document.querySelector(".lang-notice");
  var noticeBtn = document.querySelector("[data-lang-notice]");
  if (notice && noticeBtn) {
    var show = function (on) {
      notice.hidden = !on;
      noticeBtn.textContent = on ? "EN" : "中文";
      noticeBtn.setAttribute("aria-pressed", String(on));
    };
    show(store.get("lang") === "zh");
    noticeBtn.addEventListener("click", function () {
      var on = notice.hidden;
      store.set("lang", on ? "zh" : "en");
      show(on);
    });
  }

  /* ---------- Brain mascot in the home panel: fly far enough to leave through the panel's top edge ---------- */
  var mascot = document.querySelector(".hero__mascot");
  var mascotBox = mascot && mascot.closest(".hero__panel");
  if (mascot && mascotBox) {
    var setFly = function () {
      var m = mascot.getBoundingClientRect(), p = mascotBox.getBoundingClientRect();
      // bottom of the brain to the top of the panel, plus room for the balloon above its head
      mascot.style.setProperty("--fly", Math.ceil(m.bottom - p.top + m.height * 0.9) + "px");
    };
    setFly();
    window.addEventListener("resize", setFly);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(setFly);
  }

  /* ---------- Brain mascot: a fresh balloon colour every loop ---------- */
  var colors = ["#fb7185", "#f59e0b", "#34d399", "#38bdf8", "#a78bfa", "#f472b6", "#facc15", "#4ade80", "#fb923c"];
  var pick = function () { return colors[Math.floor(Math.random() * colors.length)]; };
  document.querySelectorAll(".p2-brain-icon").forEach(function (icon) {
    icon.style.setProperty("--p2-balloon-color", pick());
    icon.addEventListener("animationiteration", function (e) {
      if (e.animationName === "p2BrainFloat") icon.style.setProperty("--p2-balloon-color", pick());
    });
  });

  /* ---------- Back to top ---------- */
  document.querySelectorAll("[data-to-top]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  });
})();
