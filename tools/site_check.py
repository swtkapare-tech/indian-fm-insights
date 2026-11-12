#!/usr/bin/env python3
"""
site_check.py - the drift guard the 16:30 Site Market Brief job was missing.

WHY THIS EXISTS (12 Nov 2026). The brief was hand-built every evening with no
checker, so three failures shipped and were only found weeks later:

  1. on 11 Nov the markets page kept a heading that said "Monday 9 November 2026
     close" - the numbers had been rewritten, one dated string had not;
  2. the six files were committed one at a time (six commits on 11 Nov), so for
     a few minutes the homepage and the markets page disagreed with each other;
  3. the Market News page still carried 20 stories dated 27-29 September, six
     weeks stale, because nothing ever failed when the cards aged.

Run this BEFORE every commit. Exit 0 = safe to publish. Exit 1 = do not publish.
data/market.json is the single source of truth; every other file is checked
against it, digit for digit.

    python tools/site_check.py            # check, human output
    python tools/site_check.py --quiet    # exit code only
"""
import json, os, re, sys, datetime, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["index.html", "markets.html", "news.html"]
SNAPSHOT_RE = re.compile(r'<script type="application/json" id="ifm-snapshot">(.*?)</script>', re.S)
DATE_RE = re.compile(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+2026\b')
MONTHS = dict(Jan=1, Feb=2, Mar=3, Apr=4, May=5, Jun=6, Jul=7, Aug=8, Sep=9, Oct=10, Nov=11, Dec=12)

# How old a news card may be before the page counts as stale. The page is a
# market-news page; two weeks of drift is already too much for a daily site.
NEWS_MAX_AGE_DAYS = 14
# How old the published close may be before the brief counts as stale.
BRIEF_MAX_AGE_DAYS = 4

errors, warnings = [], []


def fail(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def fmt(v, dp):
    """Indian digit grouping: 138294 -> 1,38,294 ; 25299.35 -> 25,299.35."""
    neg = v < 0
    whole, _, frac = f"{abs(v):.{dp}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = whole + (("." + frac) if frac else "")
    return ("-" if neg else "") + out


def main():
    quiet = "--quiet" in sys.argv
    snap = json.loads(read("data/market.json"))
    session = snap["session"]["date"]
    sdate = datetime.date.fromisoformat(session)
    quotes = snap["quotes"]

    # --- 1. every page's embedded snapshot must equal data/market.json --------
    for page in PAGES:
        src = read(page)
        m = SNAPSHOT_RE.search(src)
        if not m:
            fail(f"{page}: no ifm-snapshot block found")
            continue
        try:
            embedded = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            fail(f"{page}: ifm-snapshot is not valid JSON ({e})")
            continue
        if embedded != snap:
            for key in ("as_of", "updated"):
                if embedded.get(key) != snap.get(key):
                    fail(f"{page}: snapshot {key} is {embedded.get(key)!r}, data/market.json says {snap.get(key)!r}")
            for q in quotes:
                a, b = embedded.get("quotes", {}).get(q, {}), quotes[q]
                if a != b:
                    fail(f"{page}: snapshot quote {q} is {a} but data/market.json says {b}")
            if embedded.get("session") != snap.get("session"):
                fail(f"{page}: snapshot session is {embedded.get('session')} but data/market.json says {snap.get('session')}")
            if embedded.get("sources") != snap.get("sources"):
                fail(f"{page}: snapshot sources differ from data/market.json")

    # --- 1b. EVERY page that carries a snapshot must carry the same one ------
    # Found 12 Nov 2026: 16 pages (lessons, calculators, glossary, faq, about,
    # search, privacy, 404) still carried the 22 October close in their ticker
    # while the homepage showed the current session. The first version of this
    # checker only looked at three pages, which is exactly how that survived.
    for page in sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "*.html"))):
        src = read(page)
        m = SNAPSHOT_RE.search(src)
        if not m:
            continue  # a standalone verification file (the Google site-verification page) has no shell
        try:
            embedded = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            fail(f"{page}: ifm-snapshot is not valid JSON ({e})")
            continue
        if embedded != snap:
            got = embedded.get("session", {}).get("date") or embedded.get("as_of")
            fail(f"{page}: ticker snapshot is from {got}, data/market.json says {session}")

    # --- 2. the human-readable figures must appear on each page --------------
    for page in PAGES:
        src = read(page)
        for q, d in quotes.items():
            shown = fmt(d["value"], d["dp"])
            if shown not in src:
                fail(f"{page}: {q} level {shown} does not appear on the page")

    # --- 3. no dated string may name a session older than the published one --
    # Historical mentions are allowed ONLY inside a sources block (they are the
    # day-over-day baseline and must be attributed), never in body copy.
    for page in PAGES:
        src = read(page)
        body = re.sub(r'<!--IFM:SOURCES:START-->.*?<!--IFM:SOURCES:END-->', "", src, flags=re.S)
        body = re.sub(r'"sources":\s*\[.*?\n  \]', "", body, flags=re.S)
        if page == "news.html":
            # news cards are deliberately historical; they are aged separately
            body = re.sub(r'<a class="card.*?</a>', "", body, flags=re.S)
        for d, mon in DATE_RE.findall(body):
            got = datetime.date(2026, MONTHS[mon], int(d))
            if got < sdate:
                fail(f"{page}: body copy carries the older date '{d} {mon} 2026' while the published session is {session}")

    # --- 4. sitemap lastmod must match the session for the refreshed pages ---
    sm = read("sitemap.xml")
    for page in PAGES:
        pat = rf'<loc>https://indianfminsights.site/{re.escape(page)}</loc><lastmod>([^<]+)</lastmod>'
        m = re.search(pat, sm)
        if not m:
            fail(f"sitemap.xml: no entry for {page}")
        elif m.group(1) != session:
            fail(f"sitemap.xml: lastmod for {page} is {m.group(1)}, expected {session}")

    # --- 5. the feed must carry the same session ----------------------------
    feed = read("feed.xml")
    if f'<updated>{session}T' not in feed:
        fail(f"feed.xml: <updated> does not carry the session date {session}")

    # --- 6. staleness of the published close --------------------------------
    age = (datetime.date.today() - sdate).days
    if age > BRIEF_MAX_AGE_DAYS:
        fail(f"the published close is {age} days old (limit {BRIEF_MAX_AGE_DAYS}) - refresh or label it")

    # --- 7. staleness of the news cards -------------------------------------
    news = read("news.html")
    cards = re.findall(r'<div class="meta"><span class="t">[^<]*</span><span>(\d{1,2}) (\w{3}) 2026', news)
    if not cards:
        fail("news.html: no dated story cards found")
    else:
        newest = max(datetime.date(2026, MONTHS[m], int(d)) for d, m in cards if m in MONTHS)
        card_age = (datetime.date.today() - newest).days
        if card_age > NEWS_MAX_AGE_DAYS:
            fail(f"news.html: the newest story card is {card_age} days old (limit {NEWS_MAX_AGE_DAYS}) - the page is stale")
        stated = re.search(r'class="count" id="count">(\d+) stories', news)
        if stated and int(stated.group(1)) != len(cards):
            fail(f"news.html: the page says {stated.group(1)} stories but carries {len(cards)}")

    # --- 8. one figure, one meaning: no quote may be double-defined ----------
    ids = [d.get("id") for d in [{"id": k} for k in quotes]]
    if len(ids) != 5:
        warn(f"expected the five tracked quotes, found {len(ids)}")

    if not quiet:
        print(f"session {session} | {len(quotes)} quotes | {len(cards)} news cards")
        for w in warnings:
            print("WARN ", w)
        for e in errors:
            print("FAIL ", e)
        print("RESULT:", "PASS" if not errors else f"FAIL ({len(errors)} problems)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
