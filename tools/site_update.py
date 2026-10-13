#!/usr/bin/env python3
"""Indian FM Insights - daily site freshness updater.

Rewrites the daily-changing parts of the static site from ONE JSON payload, so a
scheduled job can refresh the market brief, the numbers and the sitemap dates
without touching the rest of the pages.

Design: every updatable region is delimited by HTML comment markers
(<!--IFM:NAME:START--> ... <!--IFM:NAME:END-->). The script only ever replaces
the text BETWEEN a marker pair, so a malformed payload can never corrupt a page
- if a marker pair is missing, that region is left exactly as it was and the
script reports it.

Usage:
    python site_update.py --init  <site_dir>            # one-time: add markers
    python site_update.py --payload <payload.json> <site_dir>
"""
import argparse, json, os, re, sys

M = "<!--IFM:%s:START-->", "<!--IFM:%s:END-->"


def _region(html, name):
    s, e = M[0] % name, M[1] % name
    i, j = html.find(s), html.find(e)
    if i == -1 or j == -1 or j < i:
        return None
    return i + len(s), j


def replace_region(html, name, new, report):
    r = _region(html, name)
    if r is None:
        report.append("SKIP %s (marker missing)" % name)
        return html
    a, b = r
    report.append("OK   %s" % name)
    return html[:a] + new + html[b:]


def _esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inr(n):
    """Indian digit grouping: 150068 -> 1,50,068."""
    neg = n < 0
    s = "%d" % round(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "\u20b9" + s


def _num(q, key, money=False):
    q = (q or {}).get(key) or {}
    v = q.get("value")
    if v is None:
        return "\u2014"
    if money:
        return _inr(v)
    return ("{:,.%df}" % q.get("dp", 2)).format(v)


def _pct(q, key):
    q = (q or {}).get(key) or {}
    pct = q.get("pct")
    if pct is None:
        return "\u2014", "flat"
    d = "up" if pct > 0 else ("down" if pct < 0 else "flat")
    arrow = "\u25b2 " if pct > 0 else ("\u25bc " if pct < 0 else "")
    return "%s%.2f%%" % (arrow, abs(pct)), d


def _delta(q, key, money=False):
    q = (q or {}).get(key) or {}
    ch = q.get("change")
    if ch is None:
        return "\u2014", "flat"
    d = "up" if ch > 0 else ("down" if ch < 0 else "flat")
    if money:
        return ("+" if ch >= 0 else "-") + _inr(abs(ch)), d
    return ("+" if ch >= 0 else "") + ("%g" % ch), d


def render_snapshot(p):
    return json.dumps({"as_of": p.get("as_of", ""), "label": "Verified close",
                       "note": "Refreshed automatically each trading evening by Indian FM "
                               "Insights' own research pipeline, with every figure checked "
                               "against two independent sources.",
                       "quotes": p.get("quotes") or {},
                       "sources": p.get("sources", [])}, indent=2)


def render_index_lead(p):
    b = p.get("brief") or {}
    q = p.get("quotes") or {}
    npct, _ = _pct(q, "nifty")
    spct, _ = _pct(q, "sensex")
    return (
        '<span class="ifm-tag">Market brief \u00b7 %s</span>\n'
        '      <h1>%s</h1>\n'
        '      <p class="dek">%s</p>\n'
        '      <div class="ifm-lead-meta">\n'
        '        <span>Nifty 50 <b style="color:#fff">%s</b> <span class="ifm-down">%s</span></span>\n'
        '        <span>Sensex <b style="color:#fff">%s</b> <span class="ifm-down">%s</span></span>\n'
        '        <span>Rupee <b style="color:#fff">%s</b></span>\n'
        '      </div>\n'
        '      <p style="margin:18px 0 0"><a class="btn primary" href="markets.html">'
        'Read the full market brief <span class="arr">\u2192</span></a></p>'
        % (_esc(p.get("date_short")), _esc(b.get("headline")), _esc(b.get("dek")),
           _num(q, "nifty"), npct, _num(q, "sensex"), spct, _num(q, "usdinr"))
    )


def render_index_glance(p):
    q = p.get("quotes") or {}
    rows = [
        ("Nifty 50", _num(q, "nifty"), _pct(q, "nifty")),
        ("Sensex", _num(q, "sensex"), _pct(q, "sensex")),
        ("USD / INR", _num(q, "usdinr"), _delta(q, "usdinr")),
        ("Gold 24K (10 g)", _num(q, "gold", money=True), _delta(q, "gold", money=True)),
        ("Silver (1 kg)", _num(q, "silver", money=True), _delta(q, "silver", money=True)),
    ]
    body = "".join(
        '          <tr><td class="nm">%s</td><td class="n">%s</td>'
        '<td class="n ifm-%s">%s</td></tr>\n' % (n, lvl, ch[1], ch[0])
        for n, lvl, ch in rows)
    return (
        '<table class="ifm-table">\n'
        '        <thead><tr><th>Market</th><th style="text-align:right">Level</th>'
        '<th style="text-align:right">Change</th></tr></thead>\n'
        '        <tbody>\n%s        </tbody>\n      </table>\n'
        '      <p style="font-size:11.5px;color:var(--faint);margin:10px 0 0">'
        'Close of %s. Live values refresh at the top of this page when your browser can '
        'reach a market data source; otherwise the last verified close is shown.</p>'
        % (body, _esc(p.get("date_short")))
    )


def render_markets_brief(p):
    b = p.get("brief") or {}
    return (
        '<span class="ifm-kicker">Daily market brief \u00b7 %s</span>\n'
        '      <h1 style="font-family:var(--display);font-size:30px;line-height:1.22;'
        'margin:10px 0 14px;color:#fff">%s</h1>\n'
        '      <p style="font-size:16.5px;line-height:1.75;color:var(--text-soft)">\n'
        '        %s\n      </p>\n'
        '      <p style="font-size:16.5px;line-height:1.75;color:var(--text-soft)">\n'
        '        %s\n      </p>\n\n'
        '      <div class="keyfact" style="margin:20px 0">\n'
        '        <b>Why this matters to you:</b> %s\n      </div>'
        % (_esc(p.get("date_long")), _esc(b.get("headline")), _esc(b.get("para1")),
           _esc(b.get("para2")), _esc(b.get("keyfact")))
    )


def render_markets_moved(p):
    rows = ""
    for r in p.get("moved", []):
        rows += ('          <tr><td class="nm">%s</td><td class="n">%s</td>'
                 '<td class="n ifm-%s">%s</td></tr>\n'
                 % (_esc(r.get("name")), _esc(r.get("close")), r.get("dir", "flat"),
                    _esc(r.get("change"))))
    return (
        '<table class="ifm-table">\n'
        '        <thead><tr><th>Index</th><th style="text-align:right">Close</th>'
        '<th style="text-align:right">Change</th></tr></thead>\n'
        '        <tbody>\n%s        </tbody>\n      </table>\n'
        '      <p style="font-size:11.5px;color:var(--faint);margin:8px 0 0">'
        'Closing levels for %s, sourced from the day\'s market reports.</p>'
        % (rows, _esc(p.get("date_short")))
    )


def render_markets_bullion(p):
    rows = ""
    for r in p.get("bullion", []):
        rows += ('          <tr><td class="nm">%s</td><td class="n">%s</td>'
                 '<td class="n ifm-%s">%s</td></tr>\n'
                 % (_esc(r.get("name")), _esc(r.get("level")), r.get("dir", "flat"),
                    _esc(r.get("note"))))
    return ('<table class="ifm-table">\n'
            '        <thead><tr><th>Market</th><th style="text-align:right">Level</th>'
            '<th style="text-align:right">Note</th></tr></thead>\n'
            '        <tbody>\n%s        </tbody>\n      </table>' % rows)


def update_file(path, name, new, report):
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    out = replace_region(html, name, new, report)
    if out != html:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)


def update_snapshots(site, p, report):
    snap = render_snapshot(p)
    for page in ("index.html", "markets.html", "news.html"):
        path = os.path.join(site, page)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        new, n = re.subn(r'(<script type="application/json" id="ifm-snapshot">)(.*?)(</script>)',
                         lambda m: m.group(1) + "\n" + snap + "\n" + m.group(3),
                         html, count=1, flags=re.S)
        if n:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            report.append("OK   snapshot %s" % page)


def update_sitemap(site, p, report):
    path = os.path.join(site, "sitemap.xml")
    if not os.path.exists(path):
        return
    iso = (p.get("as_of") or "")[:10] or p.get("date_iso", "")
    if not iso:
        report.append("SKIP sitemap (no date)")
        return
    with open(path, encoding="utf-8") as fh:
        xml = fh.read()
    new = re.sub(r"<lastmod>[^<]*</lastmod>", "<lastmod>%s</lastmod>" % iso, xml)
    if new != xml:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        report.append("OK   sitemap lastmod -> %s" % iso)


def update_feed(site, p, report):
    path = os.path.join(site, "feed.xml")
    if not os.path.exists(path):
        return
    iso = (p.get("as_of") or "")[:10]
    if not iso:
        return
    now = iso + "T16:30:00+05:30"
    with open(path, encoding="utf-8") as fh:
        xml = fh.read()
    new = re.sub(r"<updated>[^<]*</updated>", "<updated>%s</updated>" % now, xml)
    if new != xml:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        report.append("OK   feed updated -> %s" % now)


def init_markers(site):
    """One-time: wrap the known regions with marker comments (idempotent)."""
    specs = {
        "index.html": [
            ("LEAD", r'(<article class="ifm-lead">)(.*?)(</article>)'),
            ("GLANCE", r'(<div class="ifm-sec-head" style="margin-top:0"><h2>At a glance</h2>'
                       r'<a class="more" href="markets.html">Full data \u2192</a></div>\s*)'
                       r'(<table class="ifm-table">.*?</table>\s*<p style="font-size:11.5px;'
                       r'color:var\(--faint\);margin:10px 0 0">.*?</p>)'),
        ],
        "markets.html": [
            ("BRIEF", r'(<span class="ifm-kicker">Daily market brief \u00b7 .*?</span>.*?)'
                      r'(?=<div class="ifm-sec-head"><h2>What moved today</h2></div>)'),
            ("MOVED", r'(<div class="ifm-sec-head"><h2>What moved today</h2></div>\s*)'
                      r'(<table class="ifm-table">.*?</table>)'),
            ("BULLION", r'(<div class="ifm-sec-head" style="margin-top:30px"><h2>'
                        r'Currency &amp; bullion</h2></div>\s*)(<table class="ifm-table">.*?</table>)'),
        ],
    }
    for page, regions in specs.items():
        path = os.path.join(site, page)
        if not os.path.exists(path):
            print("init: missing", page); continue
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        for name, pat in regions:
            if (M[0] % name) in html:
                print("init: %s/%s already marked" % (page, name)); continue
            def wrap(m, name=name):
                return (M[0] % name) + "\n" + m.group(0) + "\n" + (M[1] % name)
            html, n = re.subn(pat, wrap, html, count=1, flags=re.S)
            print("init: %s/%s %s" % (page, name, "marked" if n else "NOT FOUND"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--payload")
    ap.add_argument("site_dir")
    a = ap.parse_args()
    if a.init:
        init_markers(a.site_dir); return 0
    if not a.payload:
        print("need --payload or --init"); return 2
    with open(a.payload, encoding="utf-8") as fh:
        p = json.load(fh)
    rep = []
    update_snapshots(a.site_dir, p, rep)
    update_file(os.path.join(a.site_dir, "index.html"), "LEAD", render_index_lead(p), rep)
    update_file(os.path.join(a.site_dir, "index.html"), "GLANCE", render_index_glance(p), rep)
    update_file(os.path.join(a.site_dir, "markets.html"), "BRIEF", render_markets_brief(p), rep)
    update_file(os.path.join(a.site_dir, "markets.html"), "MOVED", render_markets_moved(p), rep)
    update_file(os.path.join(a.site_dir, "markets.html"), "BULLION", render_markets_bullion(p), rep)
    update_sitemap(a.site_dir, p, rep)
    update_feed(a.site_dir, p, rep)
    print("\n".join(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
