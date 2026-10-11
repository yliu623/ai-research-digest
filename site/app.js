(function () {
  "use strict";
  var NOTEBOOKLM = "https://notebooklm.google.com/";
  var PAGE = 7;
  var SECTIONS = [
    { k: "all", label: "All" },
    { k: "econ", label: "Economics" },
    { k: "fin", label: "Finance" },
    { k: "ops", label: "Operations" },
    { k: "news", label: "News" }
  ];
  var state = { days: [], filter: "all", q: "", shown: PAGE };
  var $ = function (id) { return document.getElementById(id); };

  function secKey(name) {
    var n = name.toLowerCase();
    if (n.indexOf("econom") >= 0) return "econ";
    if (n.indexOf("financ") >= 0) return "fin";
    if (n.indexOf("operation") >= 0 || n.indexOf("supply") >= 0) return "ops";
    if (n.indexOf("news") >= 0) return "news";
    return "other";
  }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var a in attrs) {
      if (a === "text") e.textContent = attrs[a];
      else if (a === "html") e.innerHTML = attrs[a];
      else e.setAttribute(a, attrs[a]);
    }
    (kids || []).forEach(function (k) { if (k) e.appendChild(k); });
    return e;
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function highlight(text, q) {
    var safe = esc(text);
    if (!q) return safe;
    var re = new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
    return safe.replace(re, "<mark>$1</mark>");
  }
  function splitTag(desc) {
    var m = desc.match(/\s*\[([^\]]+)\]\s*$/);
    return m ? [desc.slice(0, m.index).trim(), m[1]] : [desc.trim(), ""];
  }
  function prettyDate(iso) {
    var d = new Date(iso + "T12:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "short", day: "numeric" });
  }
  function toast(msg) {
    var t = $("toast");
    t.textContent = msg; t.classList.add("on");
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("on"); }, 4200);
  }
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    var ta = el("textarea", {}); ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    ta.remove();
    return Promise.resolve();
  }
  function listen(url) {
    // Open the tab synchronously (popup blockers), then copy.
    window.open(NOTEBOOKLM, "_blank", "noopener");
    copy(url).then(function () {
      toast("Link copied. In NotebookLM: New notebook → Add source → Website → paste → Audio Overview.");
    }, function () {
      toast("Couldn't copy automatically. Copy the Full text link, then add it in NotebookLM.");
    });
  }

  function itemMatches(it, q) {
    if (!q) return true;
    var hay = (it.title + " " + it.desc + " " + it.url).toLowerCase();
    return q.toLowerCase().split(/\s+/).every(function (w) { return hay.indexOf(w) >= 0; });
  }

  function renderItem(it, q) {
    var parts = splitTag(it.desc);
    var full = it.fulltext || it.url;
    var btn = el("button", { class: "btn", type: "button", title: "Copy the full-text link and open NotebookLM", text: "🎧 NotebookLM" });
    btn.addEventListener("click", function () { listen(full); });
    return el("div", { class: "item" }, [
      el("a", { class: "t", href: it.url, target: "_blank", rel: "noopener", html: highlight(it.title, state.q) }),
      el("p", { class: "d", html: highlight(parts[0], state.q) }),
      el("div", { class: "meta" }, [
        parts[1] ? el("span", { text: parts[1] }) : null,
        el("a", { href: full, target: "_blank", rel: "noopener", text: "Full text" }),
        btn
      ])
    ]);
  }

  function renderDay(day, q, filter) {
    var secs = [], total = 0;
    day.sections.forEach(function (s) {
      var k = secKey(s.name);
      if (filter !== "all" && k !== filter) return;
      var items = s.items.filter(function (it) { return itemMatches(it, q); });
      if (!items.length) return;
      total += items.length;
      secs.push(el("section", { class: "sec", "data-k": k }, [el("h3", { text: s.name.replace(/^\W+\s*/, "") + " (" + items.length + ")" })]
        .concat(items.map(function (it) { return renderItem(it, q); }))));
    });
    var hasAudio = !!day.audio && !q;
    if (!total && !(hasAudio && filter === "all")) return null;
    var head = el("div", { class: "day-head" }, [
      el("h2", {}, [el("a", { href: "#" + day.date, text: prettyDate(day.date) })]),
      el("span", { class: "counts", text: total + (total === 1 ? " item" : " items") })
    ]);
    var kids = [head];
    if (hasAudio && filter === "all") {
      var b = el("div", { class: "briefing" }, [
        el("p", { class: "label", text: "🎧 Daily briefing (two voices)" }),
        el("audio", { controls: "", preload: "none", src: day.audio })
      ]);
      if (day.briefing && day.briefing.length) {
        var det = el("details", {}, [el("summary", { text: "Read transcript" })]);
        day.briefing.forEach(function (l) {
          det.appendChild(el("p", { html: '<span class="spk">' + (l.speaker === "A" ? "Alex" : "Sam") + ":</span> " + esc(l.text) }));
        });
        b.appendChild(det);
      }
      kids.push(b);
    }
    kids = kids.concat(secs);
    if (day.footnote && !q) kids.push(el("p", { class: "foot", text: day.footnote }));
    return el("article", { class: "day", id: day.date }, kids);
  }

  function render() {
    var box = $("days"); box.innerHTML = "";
    var q = state.q.trim(), shown = 0, matched = 0, rendered = 0;
    var limit = q ? Infinity : state.shown;
    for (var i = 0; i < state.days.length; i++) {
      var node = renderDay(state.days[i], q, state.filter);
      if (!node) continue;
      matched++;
      if (rendered < limit) { box.appendChild(node); rendered++; }
    }
    shown = rendered;
    $("more").hidden = q || shown >= matched;
    var items = state.days.reduce(function (n, d) { return n + d.sections.reduce(function (m, s) { return m + s.items.length; }, 0); }, 0);
    $("status").textContent = q
      ? matched + " day(s) match “" + q + "”."
      : state.days.length + " digests · " + items + " items · showing " + shown + " of " + matched + " days";
  }

  function ensureShown(date) {
    for (var i = 0; i < state.days.length; i++) {
      if (state.days[i].date === date) { if (i >= state.shown) { state.shown = i + 1; } break; }
    }
  }
  function goHash() {
    var h = decodeURIComponent(location.hash.slice(1));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(h)) return;
    if (state.q) { state.q = ""; $("q").value = ""; }
    ensureShown(h); render();
    var t = $(h); if (t) t.scrollIntoView({ block: "start" });
    $("jump").value = h;
  }

  function init(data) {
    state.days = data.days || [];
    var chips = $("chips");
    SECTIONS.forEach(function (s) {
      var c = el("button", { class: "chip", type: "button", "aria-pressed": s.k === "all" ? "true" : "false", text: s.label });
      c.addEventListener("click", function () {
        state.filter = s.k;
        Array.prototype.forEach.call(chips.children, function (x) { x.setAttribute("aria-pressed", "false"); });
        c.setAttribute("aria-pressed", "true");
        render();
      });
      chips.appendChild(c);
    });
    var jump = $("jump");
    jump.appendChild(el("option", { value: "", text: "Jump to date…" }));
    state.days.forEach(function (d) { jump.appendChild(el("option", { value: d.date, text: d.date })); });
    jump.addEventListener("change", function () { if (jump.value) location.hash = jump.value; });
    var timer;
    $("q").addEventListener("input", function (e) {
      clearTimeout(timer);
      timer = setTimeout(function () { state.q = e.target.value; render(); }, 150);
    });
    $("more").addEventListener("click", function () { state.shown += PAGE; render(); });
    window.addEventListener("hashchange", goHash);
    render();
    goHash();
  }

  fetch("all.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch(function (e) { $("status").textContent = "Couldn't load the archive (" + e.message + ")."; });
})();
