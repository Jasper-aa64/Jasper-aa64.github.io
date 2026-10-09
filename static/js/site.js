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

  /* ---------- Click feedback: a ring and six sparks where the mouse clicks ---------- */
  if (!reduce && window.matchMedia("(pointer: fine)").matches) {
    document.addEventListener("pointerdown", function (e) {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      var fx = document.createElement("span");
      fx.className = "click-fx";
      fx.style.left = e.clientX + "px";
      fx.style.top = e.clientY + "px";
      for (var k = 0; k < 6; k++) {
        var sp = document.createElement("i");
        sp.style.setProperty("--a", (k * 60 + 30) + "deg");
        fx.appendChild(sp);
      }
      document.body.appendChild(fx);
      setTimeout(function () { fx.remove(); }, 600);
    }, { passive: true });
  }

  /* ---------- Home showcase: cross-fades on wide screens; the progress bar of the current slide
     drives autoplay (its fill animation ending = next slide), so pausing the bar pauses the show ---------- */
  var show = document.querySelector("[data-showcase]");
  if (show) {
    var slides = Array.prototype.slice.call(show.querySelectorAll(".slide"));
    var segs = Array.prototype.slice.call(show.querySelectorAll(".showcase__seg"));
    var countEl = show.querySelector("[data-count]");
    var wide = window.matchMedia("(min-width: 1200px)");
    var cur = 0, hold = false;
    if (reduce || slides.length < 2) show.classList.add("no-auto");
    var go = function (n) {
      cur = (n + slides.length) % slides.length;
      slides.forEach(function (sl, i) {
        var on = i === cur;
        sl.classList.toggle("is-active", on);
        sl.setAttribute("aria-hidden", on ? "false" : "true");
        sl.tabIndex = on ? 0 : -1;
      });
      segs.forEach(function (g, i) {
        g.classList.remove("is-on");
        g.classList.toggle("is-done", i < cur);
      });
      void show.offsetWidth;                    // restart the fill animation
      if (segs[cur]) segs[cur].classList.add("is-on");
      if (countEl) countEl.textContent = (cur < 9 ? "0" : "") + (cur + 1);
    };
    var sync = function () {
      show.classList.toggle("is-paused", hold || document.hidden || !wide.matches);
    };
    show.addEventListener("animationend", function (e) {
      if (e.animationName === "seg-fill" && !hold) go(cur + 1);
    });
    segs.forEach(function (g) { g.addEventListener("click", function () { go(+g.dataset.go); }); });
    show.querySelectorAll("[data-step]").forEach(function (b) {
      b.addEventListener("click", function () { go(cur + +b.dataset.step); });
    });
    show.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); go(cur - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(cur + 1); }
    });
    show.addEventListener("mouseenter", function () { hold = true; sync(); });
    show.addEventListener("mouseleave", function () { hold = false; sync(); });
    show.addEventListener("focusin", function () { hold = true; sync(); });
    show.addEventListener("focusout", function () { hold = false; sync(); });
    document.addEventListener("visibilitychange", sync);
    var wake = function () {
      if (wide.matches) show.querySelectorAll("img[loading=lazy]").forEach(function (im) { im.loading = "eager"; });
      sync();
    };
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
    var subsBox = writing.querySelector("[data-subs]");
    var inner = subsBox && subsBox.querySelector(".filter__subs-inner");
    var list = writing.querySelector("[data-list]");
    var filterBox = writing.querySelector(".filter");
    var closing = null;
    // Geometry of the tree branch: from the active top-level button down to its sub row.
    var branch = function (row) {
      var btn = tops.filter(function (b) { return b.classList.contains("is-active"); })[0];
      if (!row || !btn || !inner) return;
      var rr = row.getBoundingClientRect(), br = btn.getBoundingClientRect();
      var bx = Math.round(br.left + br.width / 2 - rr.left);
      var pad = Math.max(40, Math.min(bx + 28, Math.round(rr.width * 0.5)));
      inner.style.setProperty("--bx", bx + "px");
      inner.style.setProperty("--pad", pad + "px");
      inner.style.setProperty("--bt", Math.max(4, Math.round(rr.top - br.bottom)) + "px");
    };
    var first = true;
    var apply = function (key, sub, push) {
      if (!tops.some(function (b) { return b.dataset.filter === key; })) { key = "all"; sub = ""; }
      var row = null;
      subRows.forEach(function (r) { if (r.dataset.subsFor === key) row = r; });
      var chips = row ? Array.prototype.slice.call(row.querySelectorAll("[data-sub]")) : [];
      if (!chips.some(function (c) { return c.dataset.sub === sub; })) sub = "";
      var changed = state.key !== key || state.sub !== sub;
      var sameRow = state.key === key;
      state = { key: key, sub: sub };
      press(tops, function (b) { return b.dataset.filter === key; });
      press(chips, function (c) { return c.dataset.sub === sub; });

      if (subsBox && !sameRow) {
        if (closing) { clearTimeout(closing); closing = null; }
        if (row) {
          var wasOpen = subsBox.classList.contains("is-open");
          subRows.forEach(function (r) { r.hidden = r !== row; });
          // Opening from closed: jump the branch to its place first, then let the box grow.
          if (!wasOpen || first) inner.classList.add("is-instant");
          branch(row);
          if (!wasOpen || first) { void inner.offsetWidth; inner.classList.remove("is-instant"); }
          subsBox.classList.add("is-open");
        } else {
          // Closing: keep the current row visible while the box folds up, hide it afterwards.
          subsBox.classList.remove("is-open");
          var hideAll = function () { subRows.forEach(function (r) { r.hidden = true; }); closing = null; };
          if (first || reduce) hideAll(); else closing = setTimeout(hideAll, 320);
        }
      }

      var show = function () {
        var shown = 0;
        entries.forEach(function (el) {
          var vis = key === "all" || (el.dataset.series === key && (!sub || el.dataset.sub === sub));
          el.hidden = !vis;
          if (vis) shown++;
        });
        if (empty) empty.hidden = shown > 0;
      };
      if (first || reduce || !changed || !list) { show(); }
      else {
        list.classList.add("is-switching");
        setTimeout(function () {
          show();
          // If the reader had scrolled into the list, bring its start back under the sticky filter.
          var top = list.getBoundingClientRect().top;
          var under = filterBox ? filterBox.getBoundingClientRect().bottom : 0;
          if (top < under) window.scrollBy({ top: top - under - 8, behavior: "auto" });
          list.classList.remove("is-switching");
        }, 180);
      }
      first = false;
      if (push) history.replaceState(null, "", key === "all" ? location.pathname : "#" + key + (sub ? "/" + sub : ""));
    };
    window.addEventListener("resize", function () {
      var row = subRows.filter(function (r) { return !r.hidden; })[0];
      if (row && inner) { inner.classList.add("is-instant"); branch(row); void inner.offsetWidth; inner.classList.remove("is-instant"); }
    });
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

  /* ---------- Categories page: open a tag group to show its single-post tags ---------- */
  document.querySelectorAll("[data-tag-more]").forEach(function (b) {
    b.addEventListener("click", function () {
      var g = b.closest(".tag-group");
      if (g) { g.classList.add("is-open"); b.setAttribute("aria-expanded", "true"); }
    });
  });

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
    // A jump leaves a heading below the root's scroll-padding plus its own scroll-margin (the two add up),
    // so the "being read" line sits just below that point instead of at a fixed 140px.
    var line = 140;
    var setLine = function () {
      var pad = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
      var margin = parseFloat(getComputedStyle(heads[0]).scrollMarginTop) || 0;
      line = pad + margin + 8;
    };
    // After a click in the table of contents, keep that entry lit while its heading is on screen,
    // even when the page bottoms out before the heading reaches the line. Any user scroll releases it.
    var pinned = null;
    tocLinks.forEach(function (a) {
      a.addEventListener("click", function () {
        pinned = document.getElementById(decodeURIComponent((a.getAttribute("href") || "").replace(/^#/, "")));
      });
    });
    ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (t) {
      window.addEventListener(t, function () { pinned = null; }, { passive: true });
    });
    var mark = function () {
      var active = heads[0];
      for (var i = 0; i < heads.length; i++) {
        if (heads[i].getBoundingClientRect().top <= line) active = heads[i]; else break;
      }
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) active = heads[heads.length - 1];
      if (pinned) {
        var r = pinned.getBoundingClientRect();
        if (r.top >= 0 && r.top < window.innerHeight) active = pinned;
      }
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
      setLine();
      window.addEventListener("resize", setLine, { passive: true });
      window.addEventListener("scroll", function () { requestAnimationFrame(mark); }, { passive: true });
      mark();
    }
    document.querySelectorAll(".toc-mobile a").forEach(function (a) {
      a.addEventListener("click", function () { var d = a.closest("details"); if (d) d.open = false; });
    });
  }

  /* ---------- Heading anchors: a "#" link beside each h2 / h3 in an article ---------- */
  if (article) {
    article.querySelectorAll(".post-body :is(h2, h3)[id]").forEach(function (h) {
      var a = document.createElement("a");
      a.className = "heading-anchor";
      a.href = "#" + h.id;
      a.textContent = "#";
      a.setAttribute("aria-label", h.textContent.trim());
      h.prepend(a);
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
