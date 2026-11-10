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
LAST_STATS = {}
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
    """Search with pauses + retries so DuckDuckGo doesn't rate-limit us. Errors go into LAST_STATS."""
    import random
    import time
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    errors, urls = [], []
    LAST_STATS["errors"] = errors
    for i, q in enumerate(c["queries"]):
        if i:
            time.sleep(c.get("pause_seconds", 2) + random.random())
        for attempt in range(3):
            try:
                results = DDGS().text(q, region="us-en", max_results=c.get("results_per_query", 15)) or []
                for r in results:
                    u = r.get("href") or r.get("url")
                    if u and allowed_url(u, c) and u not in urls:
                        urls.append(u)
                break
            except Exception as ex:
                if attempt == 2:
                    errors.append(f"{q}: {type(ex).__name__}: {str(ex)[:150]}")
                    print(f"[warn] search failed for '{q}': {ex}")
                else:
                    time.sleep(5 * (attempt + 1))
        if len(urls) >= c.get("max_pages", 100):
            break
    return urls[: c.get("max_pages", 100)]


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
        r = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
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
    LAST_STATS["urls"] = len(urls)
    print(f"Search found {len(urls)} candidate pages; scraping...")
    with ThreadPoolExecutor(max_workers=16) as pool:
        pages = [p for p in pool.map(fetch_page, urls) if p]
    return [extract(p, c) for p in pages]


def fetch_demo(c):
    pages = json.loads((HERE / "sample_pages.json").read_text())
    return [extract(p, c) for p in pages]


# ---------- 3. Pull fields out of the page text ----------
NUM = r"(\d+(?:\.\d+)?)\s*-?\s*"


def ages_in(t):
    a = [float(x) for x in re.findall(NUM + r"(?:years?|yrs?)\b", t)]
    a += [float(x) / 12 for x in re.findall(NUM + r"(?:months?|mos?)\b", t)]
    a += [float(x) / 52 for x in re.findall(NUM + r"(?:weeks?|wks?)\b", t)]
    return a


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
        "price_count": len(set(int(x.replace(",", "")) for x in re.findall(r"\$\s?(\d{1,2},\d{3}|\d{2,5})(?![\d,])", raw[:2500]))),
        "age_count": len({round(a, 1) for a in ages_in(t[:2500])}),
        "head": ((p.get("title") or "") + " " + t[:1500]).lower(),
        "location": f"{loc.group(1)}, {loc.group(2)}" if loc else "",
        "snippet": snippet(raw),
    }


def snippet(raw, n=220):
    m = re.search(r"[^.]*\bpug\b[^.]*\.", raw, re.I)
    s = (m.group(0) if m else raw[:n]).strip()
    return s[:n] + ("..." if len(s) > n else "")


# ---------- API sources (structured data, much more accurate than scraping) ----------
def _env(name):
    import os
    return (os.environ.get(name) or "").strip()


def _age_years_from_text(text):
    a = ages_in((text or "").lower())
    return a[0] if a else None


def _colors(color_text, c):
    t = re.sub(r"\b(black|dark)\s+(mask|muzzle|ears?|face|points?)\b", " ", (color_text or "").lower())
    want = [x for x in c.get("colors", []) if re.search(rf"\b{re.escape(x)}\b", t)]
    dark = [x for x in c.get("exclude_colors", []) if re.search(rf"\b{re.escape(x)}\b", t)]
    return want, dark


def _api_listing(c, **kw):
    want, dark = _colors(kw.pop("color_text", ""), c)
    l = {"structured": True, "photo": None, "fee": None, "location": "", "age_years": None,
         "age_group": "", "gender": "", "special_needs": False, "description": "", "country": "US"}
    l.update(kw)
    l.update(colors_found=want, dark_found=dark, ages=[l["age_years"]] if l["age_years"] is not None else [],
             text=(l["name"] + " " + l["description"]).lower(), snippet=snippet(l["description"] or l["name"]))
    return l


# ---------- Petfinder (the public GraphQL endpoint the embeddable widget uses; undocumented) ----------
PF_GQL = "https://psl.petfinder.com/graphql"


def _gql(query, variables=None):
    import httpx
    r = httpx.post(PF_GQL, json={"query": query, "variables": variables or {}}, timeout=25,
                   headers={**HEADERS, "Content-Type": "application/json",
                            "Origin": "https://www.petfinder.com", "Referer": "https://www.petfinder.com/"})
    r.raise_for_status()
    return r.json()


def petfinder_schema():
    """List the endpoint's top-level query fields (used to fix the query if Petfinder changes it)."""
    q = "{ __schema { queryType { fields { name args { name } } } } }"
    try:
        fields = _gql(q)["data"]["__schema"]["queryType"]["fields"]
        return [f"{f['name']}({', '.join(a['name'] for a in f['args'])})" for f in fields]
    except Exception as ex:
        return [f"schema lookup failed: {type(ex).__name__}: {str(ex)[:120]}"]


def _walk_animals(obj):
    """Find animal-like dicts anywhere in a GraphQL response (robust to unknown shapes)."""
    if isinstance(obj, dict):
        keys = {k.lower() for k in obj}
        if "name" in keys and ({"gender", "sex"} & keys or "breed" in " ".join(keys)):
            yield obj
        for v in obj.values():
            yield from _walk_animals(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_animals(v)


def _txt(v):
    if isinstance(v, dict):
        return " ".join(_txt(x) for x in v.values())
    if isinstance(v, list):
        return " ".join(_txt(x) for x in v)
    return "" if v is None else str(v)


def fetch_petfinder(c):
    qfile = HERE / "petfinder_query.graphql"
    if not qfile.exists():
        raise RuntimeError("no petfinder_query.graphql file")
    data = _gql(qfile.read_text(), c.get("petfinder_variables", {}))
    if data.get("errors"):
        LAST_STATS["petfinder_schema"] = petfinder_schema()
        raise RuntimeError("query rejected: " + "; ".join(e.get("message", "")[:120] for e in data["errors"][:3]))
    out = []
    for a in _walk_animals(data.get("data")):
        low = {k.lower(): v for k, v in a.items()}
        breed = _txt(low.get("breeds") or low.get("breed") or low.get("primarybreed"))
        desc = _txt(low.get("description"))
        addr = low.get("address") or low.get("location") or (low.get("contact") or {}).get("address") or {}
        photos = low.get("photos") or low.get("photo") or []
        photo = None
        if isinstance(photos, list) and photos:
            photo = photos[0] if isinstance(photos[0], str) else next(
                (v for v in photos[0].values() if isinstance(v, str) and v.startswith("http")), None)
        url = _txt(low.get("url") or low.get("weburl") or low.get("link"))
        if not url and low.get("id"):
            url = f"https://www.petfinder.com/dog/{low['id']}"
        fee = re.search(r"\$\s?([\d,]{2,6})", desc)
        l = _api_listing(
            c, source="Petfinder", url=url, name=_txt(low.get("name")) or "Pet",
            age_group=_txt(low.get("age") or low.get("agegroup")).lower(),
            age_years=_age_years_from_text(desc), gender=_txt(low.get("gender") or low.get("sex")).lower(),
            color_text=_txt(low.get("colors") or low.get("color")) + " " + desc,
            fee=int(fee.group(1).replace(",", "")) if fee else None,
            special_needs=bool((low.get("attributes") or {}).get("special_needs") or low.get("specialneeds")),
            location=", ".join(filter(None, [_txt(addr.get("city")), _txt(addr.get("state"))])) if isinstance(addr, dict) else _txt(addr),
            country=(_txt(addr.get("country")) if isinstance(addr, dict) else "") or "US",
            photo=photo, description=desc)
        l["breed"] = breed.lower()
        out.append(l)
    if not out:
        LAST_STATS["petfinder_schema"] = petfinder_schema()
    return out


def fetch_rescuegroups(c):
    import httpx
    key = _env("RESCUEGROUPS_KEY")
    if not key:
        raise RuntimeError("skipped: no RESCUEGROUPS_KEY set")
    body = {"data": {"filters": [
        {"fieldName": "breeds.name", "operation": "contains", "criteria": "Pug"},
        {"fieldName": "animals.sex", "operation": "equals", "criteria": "Male"},
    ]}}
    url = ("https://api.rescuegroups.org/v5/public/animals/search/available/dogs/"
           "?limit=250&include=locations,pictures&fields[animals]=name,ageGroup,ageString,birthDate,sex,"
           "colorDetails,adoptionFeeString,descriptionText,url,isSpecialNeeds,breedString,pictureThumbnailUrl")
    r = httpx.post(url, json=body, timeout=30,
                   headers={"Authorization": key, "Content-Type": "application/vnd.api+json"})
    r.raise_for_status()
    data = r.json()
    locs = {i["id"]: i.get("attributes", {}) for i in data.get("included", []) if i.get("type") == "locations"}
    return [normalize_rescuegroups(a, locs, c) for a in data.get("data", [])]


def normalize_rescuegroups(a, locs, c):
    from datetime import date
    at = a.get("attributes") or {}
    age = None
    if at.get("birthDate"):
        try:
            y, m, d = (int(x) for x in str(at["birthDate"])[:10].split("-"))
            age = (date.today() - date(y, m, d)).days / 365.25
        except Exception:
            age = None
    if age is None:
        age = _age_years_from_text(at.get("ageString"))
    loc_ids = [x.get("id") for x in ((a.get("relationships") or {}).get("locations") or {}).get("data", [])]
    loc = locs.get(loc_ids[0], {}) if loc_ids else {}
    fee = re.search(r"([\d,]{2,6})", at.get("adoptionFeeString") or "")
    desc = at.get("descriptionText") or ""
    return _api_listing(
        c, source="RescueGroups", url=at.get("url") or f"https://rescuegroups.org/animals/{a.get('id')}",
        name=at.get("name") or "Pug", age_group=(at.get("ageGroup") or "").lower(), age_years=age,
        gender=(at.get("sex") or "").lower(), color_text=(at.get("colorDetails") or "") + " " + desc,
        fee=int(fee.group(1).replace(",", "")) if fee else None,
        special_needs=bool(at.get("isSpecialNeeds")),
        location=", ".join(filter(None, [loc.get("city"), loc.get("state")])),
        country=loc.get("country") or "US", photo=at.get("pictureThumbnailUrl"), description=desc)


SOURCES = {"petfinder": fetch_petfinder, "rescuegroups": fetch_rescuegroups}


def fetch_all(c):
    """Run every enabled source. One failing source doesn't stop the others."""
    LAST_STATS.clear()
    LAST_STATS["sources"] = {}
    out = []
    for name in c.get("sources", ["petfinder", "rescuegroups"]):
        try:
            got = fetch_web(c) if name == "web" else SOURCES[name](c)
            LAST_STATS["sources"][name] = f"{len(got)} listings"
            out += got
        except Exception as ex:
            LAST_STATS["sources"][name] = f"{type(ex).__name__}: {str(ex)[:160]}" if "skipped" not in str(ex) else str(ex)
    seen, uniq = set(), []
    for l in out:
        if l["url"] not in seen:
            seen.add(l["url"]); uniq.append(l)
    return uniq


def structured_reason(l, c):
    lo, hi = c.get("min_age_years", 0), c.get("max_age_years", 99)
    if l["gender"] != "male":
        return "not male"
    if l.get("country") and l["country"] not in c.get("countries", ["US"]):
        return "outside US"
    if l["special_needs"] or any(k in l["text"] for k in c.get("exclude_keywords", [])):
        return "health issue or scam wording"
    if l["age_years"] is not None:
        if not (lo <= l["age_years"] <= hi):
            return f"age outside {lo}-{hi} yrs"
    elif l["age_group"] not in c.get("api_age_groups", ["young", "adult"]):
        return "age group outside range"
    elif c.get("require_exact_age", False):
        return "no exact age"
    if l["dark_found"] and not l["colors_found"]:
        return "dark color"
    if not l["colors_found"]:
        return "no color stated"
    if c.get("require_price", False) and not l["fee"]:
        return "no price"
    if c.get("max_fee") and l["fee"] and l["fee"] > c["max_fee"]:
        return "over max price"
    return None


# ---------- Ranking (nothing is dropped for missing criteria; misfits go to the bottom) ----------
def hard_drop(l, c):
    """Only remove things that clearly aren't a pug listing, or look like scams."""
    t = l["text"]
    if l.get("structured"):
        if l.get("breed") and "pug" not in l["breed"]:
            return "not a pug"
    elif "pug" not in t:
        return "not about pugs"
    elif not any(k in t for k in c.get("listing_keywords", [])):
        return "not a listing (article/guide)"
    if any(k in t for k in c.get("scam_keywords", [])):
        return "scam wording"
    return None


def misses(l, c):
    """Criteria this listing doesn't meet (or doesn't state). Empty list = perfect match."""
    m = []
    if l["gender"] != "male":
        m.append({"female": "female", "mixed": "male & female listed"}.get(l["gender"], "sex not stated"))
    lo, hi = c.get("min_age_years", 0), c.get("max_age_years", 99)
    if l["ages"]:
        if not any(lo <= a <= hi for a in l["ages"]):
            m.append(f"age outside {lo}-{hi} yrs")
    elif l.get("age_group"):
        if l["age_group"] not in c.get("api_age_groups", ["young", "adult"]):
            m.append(f"age group: {l['age_group']}")
    else:
        m.append("age not stated")
    if l["dark_found"] and not l["colors_found"]:
        m.append("dark color")
    elif not l["colors_found"]:
        m.append("color not stated")
    if l.get("special_needs") or any(k in l["text"] for k in c.get("health_keywords", [])):
        m.append("possible health issue")
    if l.get("country") and l["country"] not in c.get("countries", ["US"]):
        m.append("outside US")
    if not l.get("fee"):
        m.append("price not listed")
    elif c.get("max_fee") and l["fee"] > c["max_fee"]:
        m.append("over max price")
    return m


def rank(listings, c):
    """Drop only non-listings/scams; sort the rest so full matches come first."""
    kept = []
    for l in listings:
        if hard_drop(l, c):
            continue
        l["misses"] = misses(l, c)
        # price missing is a minor miss; everything else counts fully
        l["score"] = sum(0.25 if x == "price not listed" else 1 for x in l["misses"])
        kept.append(l)
    return sorted(kept, key=lambda l: l["score"])


def is_full_match(l):
    return not [x for x in l.get("misses", []) if x != "price not listed"]


# ---------- 4. Filter by criteria ----------
def reject_reason(l, c):
    """Return why a page was dropped, or None if it matches."""
    if l.get("structured"):
        return structured_reason(l, c)
    t, unknown_ok = l["text"], c.get("allow_unknown", False)
    if "pug" not in t:
        return "not about pugs"
    if not any(k in t for k in c.get("listing_keywords", [])):
        return "not a listing (article/guide)"
    if any(k in t for k in c.get("exclude_keywords", [])):
        return "health issue or scam wording"
    if c.get("require_complete", True):
        if not l["ages"]:
            return "no age stated"
        if l["gender"] != "male":
            return {"female": "female", "mixed": "male & female listed"}.get(l["gender"], "no sex stated")
        if not l["colors_found"]:
            return "dark color" if l["dark_found"] else "no color stated"
        if c.get("require_price", False) and not l["fee"]:
            return "no price"
        if l["price_count"] > c.get("max_prices_on_page", 2) or l["age_count"] > c.get("max_ages_on_page", 2):
            return "several dogs on page"
        if re.search(r"\b(litters?|dogs available|available dogs|our pugs)\b", l["head"]):
            return "litter / catalog page"
    genders = c.get("genders", [])
    if "male" in genders and "female" not in genders:
        if l["gender"] == "female" or (not l["gender"] and not unknown_ok):
            return "not male"
    lo, hi = c.get("min_age_years", 0), c.get("max_age_years", 99)
    if l["ages"]:
        if not any(lo <= a <= hi for a in l["ages"]):
            return f"age outside {lo}-{hi} yrs"
    elif not unknown_ok:
        return "no age stated"
    if l["dark_found"] and not l["colors_found"]:
        return "dark color"
    if c.get("max_fee") and l["fee"] and l["fee"] > c["max_fee"]:
        return "over max price"
    return None


def matches(l, c):
    return reject_reason(l, c) is None


def diagnose(listings, c, n_urls=None):
    from collections import Counter
    reasons = Counter(hard_drop(l, c) or ("FULL MATCH" if is_full_match({"misses": misses(l, c)}) else "partial match (shown lower)") for l in listings)
    lines = [f"{k}: {v}" for k, v in (LAST_STATS.get("sources") or {}).items()]
    if LAST_STATS.get("petfinder_schema"):
        lines.append("petfinder query fields available: " + ", ".join(LAST_STATS["petfinder_schema"][:40]))
    if n_urls is not None:
        lines.append(f"search links found: {n_urls}")
        errs = LAST_STATS.get("errors") or []
        if errs:
            lines.append(f"searches that failed: {len(errs)}")
            lines += ["  " + e for e in errs[:5]]
        lines.append(f"pages that loaded: {len(listings)} (others blocked or timed out)")
    lines += [f"{v:>3}  {k}" for k, v in reasons.most_common()]
    return lines


def describe(l):
    ages = sorted(set(l["ages"]))[:3]
    age = ", ".join(f"{a:.1f} yrs".replace(".0 ", " ") if a >= 1 else f"{round(a * 12)} mo" for a in ages) \
        or (l.get("age_group", "").title() + " (age group)" if l.get("age_group") else "age not stated")
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
        <p class="meta">{'✅ Matches your criteria' if is_full_match(l) else '⚠️ ' + e(', '.join(l.get('misses', [])))}</p>
        <p><b>{'$' + format(l['fee'], ',') if l['fee'] else 'Price not listed'}</b>{' · ' + e(l['location']) if l['location'] else ''}</p>
        <p class="snip">{e(l['snippet'])}</p>
        <p class="meta">{e(l['source'])}</p></div></a>""" for l in listings)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Matthew-san's personal puggy finder</title><style>
body{{font-family:-apple-system,sans-serif;background:#f6f4f0;margin:0;padding:24px;color:#222}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.card{{background:#fff;border-radius:12px;overflow:hidden;text-decoration:none;color:inherit;box-shadow:0 1px 4px #0002}}
.card:hover{{box-shadow:0 4px 12px #0003}}
img,.noimg{{width:100%;height:180px;object-fit:cover;background:#eee;font-size:64px;display:flex;align-items:center;justify-content:center}}
.body{{padding:12px}} h3{{margin:0 0 6px;font-size:16px}} p{{margin:4px 0;font-size:14px}}
.snip{{color:#555;font-size:13px}} .meta{{color:#888;font-size:12px}}
</style></head><body><h1>🐶 Matthew-san's personal puggy finder</h1>
<p>{len(listings)} {'new ' if new_only else ''}matches out of {total} pages scanned · {datetime.now():%b %d, %Y %I:%M %p}</p>
<p class="meta">Details are read automatically from each page and can be wrong. Always verify with the seller, and never pay before meeting the dog.</p>
<div class="grid">{cards or '<p>No new matches.</p>'}</div></body></html>"""


def main():
    demo, show_all = "--demo" in sys.argv, "--all" in sys.argv
    c = load_criteria()
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() and not demo else set()
    try:
        listings = fetch_demo(c) if demo else fetch_all(c)
    except Exception as ex:
        print(f"[error] search failed: {ex}")
        listings = []
    hits = rank(listings, c)
    print("\n".join(diagnose(listings, c, LAST_STATS.get("urls"))))
    new = hits if (show_all or demo) else [l for l in hits if l["url"] not in seen]
    OUT_FILE.write_text(render(new, len(listings), not (show_all or demo)))
    if not demo:
        SEEN_FILE.write_text(json.dumps(sorted(seen | {l["url"] for l in hits})))
    print(f"{len(listings)} pages -> {len(hits)} match -> {len(new)} shown. Wrote {OUT_FILE}")
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT_FILE.resolve().as_uri())


if __name__ == "__main__":
    main()
