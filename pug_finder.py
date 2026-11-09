#!/usr/bin/env python3
"""Pug Finder: searches the web (DuckDuckGo) for pug listings, scrapes each result page,
filters them by criteria.yaml, writes results.html and opens it in your browser.

Usage:
  python pug_finder.py            # new matches only
  python pug_finder.py --all      # every match, including ones seen before
  python pug_finder.py --demo     # offline test using sample_pages.json
  python pug_finder.py --no-open  # don't open the browser
"""
import html
import json
import re
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

HERE = Path(__file__).parent
SEEN_FILE = HERE / "seen.json"
OUT_FILE = HERE / "results.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
NON_US_TLDS = (".ca", ".uk", ".au", ".nz", ".ie", ".in", ".ph", ".za", ".de", ".fr", ".es", ".it", ".nl", ".mx", ".br")
US_STATES = ("AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|"
             "NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC")


def load_criteria():
    return yaml.safe_load((HERE / "criteria.yaml").read_text())


# ---------- 1. Search the web ----------
def search_web(c):
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    ddg = DDGS()
    urls = []
    for q in c["queries"]:
        try:
            for r in ddg.text(q, region="us-en", max_results=c.get("results_per_query", 15)):
                u = r.get("href") or r.get("url")
                if u and allowed_url(u, c) and u not in urls:
                    urls.append(u)
        except Exception as ex:
            print(f"[warn] search failed for '{q}': {ex}")
    return urls[: c.get("max_pages", 40)]


def allowed_url(u, c):
    host = urlparse(u).netloc.lower()
    if any(b in host for b in c.get("blocked_domains", [])):
        return False
    return not host.endswith(NON_US_TLDS)


# ---------- 2. Scrape each result page ----------
def fetch_page(url):
    import httpx
    from bs4 import BeautifulSoup
    try:
        r = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return None
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag else None

    title = meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else url)
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)[:30000]
    return {"url": str(r.url), "title": title, "text": text, "photo": meta("og:image")}


def fetch_web(c):
    urls = search_web(c)
    print(f"Search found {len(urls)} candidate pages; scraping...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = [p for p in pool.map(fetch_page, urls) if p]
    return [extract(p, c) for p in pages]


def fetch_demo(c):
    pages = json.loads((HERE / "sample_pages.json").read_text())
    return [extract(p, c) for p in pages]


# ---------- 3. Pull fields out of the page text ----------
NUM = r"(\d+(?:\.\d+)?)\s*-?\s*"


def extract(p, c):
    raw = p["text"]
    t = raw.lower()
    # ignore markings so "fawn with black mask" isn't treated as a black pug
    t_color = re.sub(r"\b(black|dark)\s+(mask|muzzle|ears?|face|points?)\b", " ", t)
    ages = [float(x) for x in re.findall(NUM + r"(?:years?|yrs?)\b", t)]
    ages += [float(x) / 12 for x in re.findall(NUM + r"(?:months?|mos?)\b", t)]
    ages += [float(x) / 52 for x in re.findall(NUM + r"(?:weeks?|wks?)\b", t)]
    male = bool(re.search(r"\b(male|boy)\b", t))
    female = bool(re.search(r"\b(female|girl)\b", t))
    gender = "male" if male and not female else "female" if female and not male else "mixed" if male else ""
    wanted = [col for col in c.get("colors", []) if re.search(rf"\b{re.escape(col)}\b", t_color)]
    dark = [col for col in c.get("exclude_colors", []) if re.search(rf"\b{re.escape(col)}\b", t_color)]
    prices = [int(x.replace(",", "")) for x in re.findall(r"\$\s?(\d{1,2},\d{3}|\d{2,5})(?![\d,])", raw)]
    prices = [x for x in prices if 50 <= x <= 10000]
    loc = re.search(rf"\b([A-Z][a-zA-Z.]+(?: [A-Z][a-zA-Z.]+)?),\s*({US_STATES})\b", raw)
    return {
        "url": p["url"], "name": (p.get("title") or p["url"])[:120], "photo": p.get("photo"),
        "source": urlparse(p["url"]).netloc.replace("www.", ""),
        "text": t, "ages": ages, "puppy_words": bool(re.search(r"\bpupp(y|ies)\b", t)),
        "gender": gender, "colors_found": wanted, "dark_found": dark,
        "fee": prices[0] if prices else None,
        "location": f"{loc.group(1)}, {loc.group(2)}" if loc else "",
        "snippet": snippet(raw),
    }


def snippet(raw, n=220):
    m = re.search(r"[^.]*\bpug\b[^.]*\.", raw, re.I)
    s = (m.group(0) if m else raw[:n]).strip()
    return s[:n] + ("..." if len(s) > n else "")


# ---------- 4. Filter by criteria ----------
def matches(l, c):
    t, unknown_ok = l["text"], c.get("allow_unknown", True)
    if "pug" not in t:
        return False
    if not any(k in t for k in c.get("listing_keywords", [])):
        return False  # probably an article, not a listing
    if any(k in t for k in c.get("exclude_keywords", [])):
        return False  # health issues or scam wording
    genders = c.get("genders", [])
    if "male" in genders and "female" not in genders:
        if l["gender"] == "female" or (not l["gender"] and not unknown_ok):
            return False
    lo, hi = c.get("min_age_years", 0), c.get("max_age_years", 99)
    if l["ages"]:
        if not any(lo <= a <= hi for a in l["ages"]):
            return False
    elif l["puppy_words"] and lo >= 1:
        return False
    elif not unknown_ok:
        return False
    if l["dark_found"] and not l["colors_found"]:
        return False
    if not l["colors_found"] and not unknown_ok:
        return False
    if c.get("max_fee") and l["fee"] and l["fee"] > c["max_fee"]:
        return False
    return True


def describe(l):
    ages = sorted(set(l["ages"]))[:3]
    age = ", ".join(f"{a:g} yrs" if a >= 1 else f"{round(a * 12)} mo" for a in ages) or "age not stated"
    sex = {"male": "Male", "mixed": "Male & female listed", "female": "Female"}.get(l["gender"], "sex not stated")
    color = ", ".join(l["colors_found"]).title() or "color not stated"
    return f"{sex} · {age} · {color}"


# ---------- 5. Results page ----------
def render(listings, total, new_only):
    e = html.escape
    cards = "".join(f"""
    <a class="card" href="{e(l['url'])}" target="_blank">
      {'<img src="' + e(l['photo']) + '">' if l.get('photo') else '<div class="noimg">🐶</div>'}
      <div class="body"><h3>{e(l['name'])}</h3>
        <p>{e(describe(l))}</p>
        <p><b>{'$' + format(l['fee'], ',') if l['fee'] else 'Price not found'}</b>{' · ' + e(l['location']) if l['location'] else ''}</p>
        <p class="snip">{e(l['snippet'])}</p>
        <p class="meta">{e(l['source'])}</p></div></a>""" for l in listings)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Pug Finder</title><style>
body{{font-family:-apple-system,sans-serif;background:#f6f4f0;margin:0;padding:24px;color:#222}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.card{{background:#fff;border-radius:12px;overflow:hidden;text-decoration:none;color:inherit;box-shadow:0 1px 4px #0002}}
.card:hover{{box-shadow:0 4px 12px #0003}}
img,.noimg{{width:100%;height:180px;object-fit:cover;background:#eee;font-size:64px;display:flex;align-items:center;justify-content:center}}
.body{{padding:12px}} h3{{margin:0 0 6px;font-size:16px}} p{{margin:4px 0;font-size:14px}}
.snip{{color:#555;font-size:13px}} .meta{{color:#888;font-size:12px}}
</style></head><body><h1>🐶 Pug Finder</h1>
<p>{len(listings)} {'new ' if new_only else ''}matches out of {total} pages scanned · {datetime.now():%b %d, %Y %I:%M %p}</p>
<p class="meta">Details are read automatically from each page and can be wrong. Always verify with the seller, and never pay before meeting the dog.</p>
<div class="grid">{cards or '<p>No new matches.</p>'}</div></body></html>"""


def main():
    demo, show_all = "--demo" in sys.argv, "--all" in sys.argv
    c = load_criteria()
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() and not demo else set()
    try:
        listings = fetch_demo(c) if demo else fetch_web(c)
    except Exception as ex:
        print(f"[error] search failed: {ex}")
        listings = []
    hits = [l for l in listings if matches(l, c)]
    new = hits if (show_all or demo) else [l for l in hits if l["url"] not in seen]
    OUT_FILE.write_text(render(new, len(listings), not (show_all or demo)))
    if not demo:
        SEEN_FILE.write_text(json.dumps(sorted(seen | {l["url"] for l in hits})))
    print(f"{len(listings)} pages -> {len(hits)} match -> {len(new)} shown. Wrote {OUT_FILE}")
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT_FILE.resolve().as_uri())


if __name__ == "__main__":
    main()
