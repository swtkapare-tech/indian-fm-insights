/* ============================================================
   Indian FM Insights — app.js
   Market ticker (live attempt + verified-snapshot fallback),
   market open/closed status in IST, mobile nav, reading progress.
   No tracking. No cookies. No third-party scripts beyond an
   optional public data fetch that fails silently.
   ============================================================ */
(function () {
  "use strict";
  var base = (document.body && document.body.getAttribute("data-base")) || "";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- helpers ---------- */
  function fmtNum(n, dp) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toLocaleString("en-IN", { minimumFractionDigits: dp || 0, maximumFractionDigits: dp || 0 });
  }
  function pctClass(p) { return p > 0.0001 ? "ifm-up" : (p < -0.0001 ? "ifm-down" : "ifm-flat"); }
  function arrow(p) { return p > 0.0001 ? "▲" : (p < -0.0001 ? "▼" : "■"); }

  /* IST market status — computed locally, always correct, no API */
  function istNow() {
    var d = new Date();
    return new Date(d.getTime() + (d.getTimezoneOffset() + 330) * 60000);
  }
  function marketStatus() {
    var t = istNow();
    var day = t.getDay();                       // 0 Sun .. 6 Sat
    var mins = t.getHours() * 60 + t.getMinutes();
    if (day === 0 || day === 6) return { open: false, label: "Market closed · weekend" };
    if (mins >= 555 && mins <= 930) return { open: true, label: "Market open" };        // 9:15–15:30
    if (mins < 555) return { open: false, label: "Pre-open · opens 9:15 IST" };
    return { open: false, label: "Market closed · next session 9:15 IST" };
  }

  /* ---------- ticker ---------- */
  var TILES = [
    { id: "nifty",  label: "Nifty 50" },
    { id: "sensex", label: "Sensex" },
    { id: "usdinr", label: "USD / INR", dp: 2 },
    { id: "gold",   label: "Gold 24K /10g", dp: 0 },
    { id: "silver", label: "Silver /kg", dp: 0 }
  ];

  function tileEl(t) {
    var d = document.createElement("div");
    d.className = "ifm-tk";
    d.setAttribute("data-tile", t.id);
    d.innerHTML = '<span class="k">' + t.label + '</span><span class="v">—</span><span class="c ifm-flat">—</span>';
    return d;
  }
  function paintTile(t, v, chg, pct) {
    var el = $('[data-tile="' + t.id + '"]');
    if (!el || v === null || v === undefined) return;
    var val = el.querySelector(".v"), c = el.querySelector(".c");
    val.textContent = fmtNum(v, t.dp);
    if (chg === null || chg === undefined || isNaN(chg)) {
      c.textContent = "—"; c.className = "c ifm-flat";
    } else {
      c.textContent = arrow(chg) + " " + fmtNum(Math.abs(chg), t.dp) + " (" + (pct >= 0 ? "+" : "") + Number(pct).toFixed(2) + "%)";
      c.className = "c " + pctClass(pct);
    }
  }
  function paintMeta(text, live) {
    var m = $(".ifm-tk-meta");
    if (m) m.innerHTML = '<span class="ifm-dot ' + (live ? "open" : "closed") + '"></span>&nbsp;' + text;
  }

  function buildTicker() {
    var strip = $("#ifm-ticker");
    if (!strip) return;
    TILES.forEach(function (t) { strip.appendChild(tileEl(t)); });
    var meta = document.createElement("div");
    meta.className = "ifm-tk-meta";
    meta.innerHTML = "Loading market data…";
    strip.appendChild(meta);
  }

  function applySnapshot(snap) {
    if (!snap || !snap.quotes) return;
    TILES.forEach(function (t) {
      var q = snap.quotes[t.id];
      if (q) paintTile(t, q.value, q.change, q.pct);
    });
    var when = snap.as_of ? new Date(snap.as_of) : null;
    var stamp = when ? when.toLocaleDateString("en-IN", { day: "numeric", month: "short" }) + " close" : "last verified close";
    paintMeta(stamp + " · verified", false);
    window.__ifmSnapshot = snap;
  }

  /* Try a live refresh. Any failure is silent — the snapshot stays. */
  function tryLive() {
    var snap = window.__ifmSnapshot;
    var targets = [
      { t: TILES[0], y: "^NSEI" }, { t: TILES[1], y: "^BSESN" }
    ];
    var proxies = [
      function (u) { return "https://api.allorigins.win/raw?url=" + encodeURIComponent(u); },
      function (u) { return "https://corsproxy.io/?url=" + encodeURIComponent(u); }
    ];
    function yahoo(sym) {
      return "https://query1.finance.yahoo.com/v8/finance/chart/" + encodeURIComponent(sym) + "?range=1d&interval=1d";
    }
    function sane(id, v) {
      if (!isFinite(v)) return false;
      if (id === "nifty")  return v > 5000 && v < 200000;
      if (id === "sensex") return v > 20000 && v < 700000;
      if (id === "usdinr") return v > 40 && v < 200;
      return true;
    }
    var got = 0, want = targets.length + 1;

    function done() {
      if (++got >= want) {
        if (got) {
          var s = marketStatus();
          paintMeta((s.open ? "Live" : "Latest close") + " · " + s.label, s.open);
        }
      }
    }

    targets.forEach(function (tg) {
      var url = yahoo(tg.y), settled = false;
      (function next(i) {
        if (i >= proxies.length || settled) { done(); return; }
        var ctl = ("AbortController" in window) ? new AbortController() : null;
        var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 6500);
        fetch(proxies[i](url), ctl ? { signal: ctl.signal } : {})
          .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("http")); })
          .then(function (j) {
            clearTimeout(timer);
            var res = j && j.chart && j.chart.result && j.chart.result[0];
            var meta = res && res.meta;
            if (!meta || typeof meta.regularMarketPrice !== "number") return next(i + 1);
            var v = meta.regularMarketPrice, prev = meta.chartPreviousClose || meta.previousClose;
            if (!sane(tg.t.id, v)) return next(i + 1);
            var chg = prev ? v - prev : 0, pct = prev ? (chg / prev) * 100 : 0;
            paintTile(tg.t, v, chg, pct);
            settled = true; done();
          })
          .catch(function () { clearTimeout(timer); next(i + 1); });
      })(0);
    });

    /* USD/INR — a genuinely CORS-friendly public source, tried directly first */
    (function () {
      var ctl = ("AbortController" in window) ? new AbortController() : null;
      var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 6500);
      fetch("https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR", ctl ? { signal: ctl.signal } : {})
        .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("http")); })
        .then(function (j) {
          clearTimeout(timer);
          var v = j && j.rates && j.rates.INR;
          if (v && sane("usdinr", v)) {
            var prev = snap && snap.quotes && snap.quotes.usdinr ? snap.quotes.usdinr.value : null;
            var chg = prev ? v - prev : null, pct = prev ? (chg / prev) * 100 : null;
            paintTile(TILES[2], v, chg, pct);
          }
          done();
        })
        .catch(function () { clearTimeout(timer); done(); });
    })();
  }

  /* ---------- mobile nav ---------- */
  function initNav() {
    var b = $("#ifm-burger"), m = $("#ifm-nav");
    if (!b || !m) return;
    b.addEventListener("click", function () {
      var open = m.classList.toggle("open");
      b.setAttribute("aria-expanded", open ? "true" : "false");
    });
    $$("a", m).forEach(function (a) {
      a.addEventListener("click", function () { m.classList.remove("open"); b.setAttribute("aria-expanded", "false"); });
    });
  }

  /* ---------- reading progress on lesson pages ---------- */
  function initProgress() {
    if (!document.querySelector(".article-wrap")) return;
    var bar = document.createElement("div");
    bar.className = "ifm-prog";
    document.body.appendChild(bar);
    function upd() {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (h > 0 ? Math.min(100, (window.scrollY / h) * 100) : 0) + "%";
    }
    window.addEventListener("scroll", upd, { passive: true });
    upd();
  }

  /* ---------- year ---------- */
  function initYear() {
    var y = $("#yr") || $("#year");
    if (y) y.textContent = new Date().getFullYear();
  }

  /* ---------- inline snapshot (baked into every page) ---------- */
  function readInline() {
    var el = document.getElementById("ifm-snapshot");
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function paintStatus() {
    var s = marketStatus();
    var dot = document.getElementById("ifm-mkt-dot"), txt = document.getElementById("ifm-mkt-status");
    if (dot) dot.className = "ifm-dot " + (s.open ? "open" : "closed");
    if (txt) txt.textContent = s.label;
    return s;
  }

  /* ---------- boot ----------
     Order: baked-in snapshot first (always renders something correct),
     then the live data/market.json (freshest, updated by the pipeline),
     then an optional live quote refresh. Nothing can leave the strip empty. */
  function boot() {
    buildTicker();
    initNav();
    initProgress();
    initYear();
    paintStatus();

    var inline = readInline();
    if (inline) applySnapshot(inline);
    else paintMeta(marketStatus().label, false);

    fetch(base + "data/market.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("no snapshot")); })
      .then(function (snap) { applySnapshot(snap); })
      .catch(function () { /* baked-in values already shown */ })
      .then(function () { tryLive(); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
