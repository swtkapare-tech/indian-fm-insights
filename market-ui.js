/* ============================================================
   Indian FM Insights — market-ui.js  (v3 "Market Desk")
   Small, dependency-free enhancements for the market surfaces:
     1. Tab bar (Overview / Movers / Currency & bullion / Explained)
     2. Watchlist — pin instruments to the front of the index band,
        saved in the browser. No account, no server, no tracking.
     3. "Copy today's figures" — one clean text block for sharing.
   Reads the same verified snapshot the rest of the page uses, so
   it always agrees with the daily-refreshed numbers.
   ============================================================ */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var KEY = "ifm.watch.v1";

  function readSnap() {
    if (window.__ifmSnapshot) return window.__ifmSnapshot;
    var el = document.getElementById("ifm-snapshot");
    if (el) { try { return JSON.parse(el.textContent); } catch (e) { } }
    return null;
  }
  function fmt(v, dp) {
    if (v === null || v === undefined || isNaN(v)) return "\u2014";
    return Number(v).toLocaleString("en-IN", { minimumFractionDigits: dp || 0, maximumFractionDigits: dp || 0 });
  }
  var META = {
    nifty: { name: "Nifty 50", money: false },
    sensex: { name: "Sensex", money: false },
    usdinr: { name: "USD / INR", money: false },
    gold: { name: "Gold 24K /10g", money: true },
    silver: { name: "Silver /kg", money: true }
  };

  /* ---------- tabs ---------- */
  function initTabs() {
    var bar = $(".ifm-tabs");
    if (!bar) return;
    var tabs = $$(".ifm-tab", bar);
    tabs.forEach(function (t) {
      t.addEventListener("click", function () {
        var id = t.getAttribute("data-tab");
        tabs.forEach(function (x) {
          var on = x === t;
          x.classList.toggle("on", on);
          x.setAttribute("aria-selected", on ? "true" : "false");
        });
        $$(".ifm-tabpanel").forEach(function (p) {
          p.hidden = p.getAttribute("data-panel") !== id;
        });
      });
    });
  }

  /* ---------- watchlist ---------- */
  function loadWatch() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
  }
  function saveWatch(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) { } }

  function renderWatch() {
    var box = $(".ifm-watch");
    if (!box) return;
    var pins = loadWatch(), snap = readSnap();
    var q = (snap && snap.quotes) || {};
    box.innerHTML = "";
    if (!pins.length) {
      box.innerHTML = '<p class="ifm-wempty">Nothing pinned yet. Tap the \u2606 star on any card above to follow it here. Saved in your browser \u2014 no account needed.</p>';
      return;
    }
    pins.forEach(function (id) {
      var m = META[id]; if (!m) return;
      var x = q[id] || {};
      var v = m.money ? ("\u20b9" + fmt(x.value, x.dp)) : fmt(x.value, x.dp);
      var cls = x.pct == null ? "ifm-flat" : (x.pct > 0 ? "ifm-up" : (x.pct < 0 ? "ifm-down" : "ifm-flat"));
      var chg = x.pct == null ? "" : (" <span class=\"" + cls + "\">" + (x.pct >= 0 ? "\u25b2" : "\u25bc") + " " + Math.abs(Number(x.pct)).toFixed(2) + "%</span>");
      var row = document.createElement("div");
      row.className = "ifm-wrow";
      row.innerHTML = '<span class="k">' + m.name + chg + '</span><span class="v">' + v + "</span>";
      box.appendChild(row);
    });
  }

  function applyPins() {
    var band = $(".ifm-idxband");
    if (!band) return;
    var pins = loadWatch();
    var cards = $$(".ifm-idx", band);
    cards.forEach(function (c) {
      var id = c.getAttribute("data-id");
      var pinned = pins.indexOf(id) > -1;
      var b = $(".pin", c);
      if (b) { b.classList.toggle("on", pinned); b.textContent = pinned ? "\u2605" : "\u2606"; b.setAttribute("aria-pressed", pinned ? "true" : "false"); }
    });
    var sorted = cards.slice().sort(function (a, b) {
      var ai = pins.indexOf(a.getAttribute("data-id")), bi = pins.indexOf(b.getAttribute("data-id"));
      if (ai < 0) ai = 999; if (bi < 0) bi = 999;
      return ai - bi;
    });
    sorted.forEach(function (c) { band.appendChild(c); });
  }

  function initPins() {
    var band = $(".ifm-idxband");
    if (!band) return;
    band.addEventListener("click", function (e) {
      var b = e.target && e.target.closest ? e.target.closest(".pin") : null;
      if (!b) return;
      var card = b.closest(".ifm-idx"); if (!card) return;
      var id = card.getAttribute("data-id");
      var pins = loadWatch(), i = pins.indexOf(id);
      if (i > -1) pins.splice(i, 1); else pins.push(id);
      saveWatch(pins); applyPins(); renderWatch();
    });
    applyPins();
    renderWatch();
  }

  /* ---------- copy today's figures ---------- */
  function initCopy() {
    var btn = $(".ifm-copy");
    if (!btn) return;
    var label = btn.textContent;
    btn.addEventListener("click", function () {
      var s = readSnap();
      if (!s || !s.quotes) return;
      var q = s.quotes;
      var order = ["nifty", "sensex", "usdinr", "gold", "silver"];
      var lines = ["Indian FM Insights \u2014 verified close" + (s.as_of ? " (" + s.as_of.slice(0, 10) + ")" : "")];
      order.forEach(function (id) {
        var x = q[id], m = META[id]; if (!x || !m) return;
        var v = m.money ? ("\u20b9" + fmt(x.value, x.dp)) : fmt(x.value, x.dp);
        var p = x.pct == null ? "" : ("  " + (x.pct >= 0 ? "+" : "") + Number(x.pct).toFixed(2) + "%");
        lines.push(m.name + ": " + v + p);
      });
      var text = lines.join("\n");
      function done() { btn.textContent = "Copied \u2713"; setTimeout(function () { btn.textContent = label; }, 1800); }
      function fallback() {
        var ta = document.createElement("textarea");
        ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "absolute"; ta.style.left = "-9999px";
        document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (e) { }
        document.body.removeChild(ta); done();
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(fallback);
      } else { fallback(); }
    });
  }

  function boot() { initTabs(); initPins(); initCopy(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
