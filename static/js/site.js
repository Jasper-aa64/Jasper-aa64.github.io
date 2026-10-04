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
    themeBtn.addEventListener("click", function () {
      root.classList.add("theme-switching");
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      store.set("theme", root.dataset.theme);
      sync();
      setTimeout(function () { root.classList.remove("theme-switching"); }, 500);
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
      setTimeout(function () {
        front.classList.add("no-anim");
        front.classList.remove("is-leaving");
        place();
        void front.offsetWidth;
        front.classList.remove("no-anim");
        busy = false;
      }, 480);
      order.forEach(function (c, i) { if (c !== front) c.dataset.pos = String(i); });
    };
    deck.addEventListener("click", advance);
    deck.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); advance(); }
    });
  }

  /* ---------- Writing filter ---------- */
  var writing = document.querySelector("[data-writing]");
  if (writing) {
    var buttons = Array.prototype.slice.call(writing.querySelectorAll("[data-filter]"));
    var entries = Array.prototype.slice.call(writing.querySelectorAll(".entry"));
    var groupsEls = Array.prototype.slice.call(writing.querySelectorAll("[data-year-group]"));
    var empty = writing.querySelector("[data-empty]");
    var apply = function (key, push) {
      if (!buttons.some(function (b) { return b.dataset.filter === key; })) key = "all";
      buttons.forEach(function (b) {
        var on = b.dataset.filter === key;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", String(on));
      });
      var shown = 0;
      entries.forEach(function (li) {
        var vis = key === "all" || li.dataset.series === key;
        li.hidden = !vis;
        if (vis) shown++;
      });
      groupsEls.forEach(function (g) { g.hidden = !g.querySelector(".entry:not([hidden])"); });
      if (empty) empty.hidden = shown > 0;
      if (push) history.replaceState(null, "", key === "all" ? location.pathname : "#" + key);
    };
    buttons.forEach(function (b) {
      b.addEventListener("click", function () { apply(b.dataset.filter, true); });
    });
    var fromHash = function () { apply(location.hash.replace("#", "") || "all", false); };
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
  document.querySelectorAll("[data-lang-target]").forEach(function (a) {
    a.addEventListener("click", function () { store.set("lang", a.dataset.langTarget); });
  });
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

  /* ---------- Back to top ---------- */
  document.querySelectorAll("[data-to-top]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  });
})();
