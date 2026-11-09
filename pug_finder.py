#!/usr/bin/env python3
"""Pug finder: pulls pug listings, filters by criteria.yaml, writes results.html, opens it.

Usage:
  export PETFINDER_KEY=...  PETFINDER_SECRET=...   # free at petfinder.com/developers
  python pug_finder.py            # live run
  python pug_finder.py --demo     # offline test with sample data
  python pug_finder.py --all      # show all matches, not just new ones
"""
import html, json, os, re, sys, webbrowser
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).parent
SEEN_FILE = HERE / "seen.json"
OUT_FILE = HERE / "results.html"


# ---------- Sources (add one function per site) ----------
def fetch_petfinder(c):
    import httpx
    key, secret = os.environ.get("PETFINDER_KEY"), os.environ.get("PETFINDER_SECRET")
    if not key or not secret:
        sys.exit("Set PETFINDER_KEY and PETFINDER_SECRET (free: https://www.petfinder.com/developers/)")
    tok = httpx.post("https://api.petfinder.com/v2/oauth2/token", data={
        "grant_type": "client_credentials", "client_id": key, "client_secret": secret}, timeout=20)
    tok.raise_for_status()
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    params = {"type": "dog", "breed": "pug", "status": "adoptable", "limit": 100, "sort": "recent"}
    if c.get("location"):
        params["location"] = c["location"]
        if c.get("distance_miles"): params["distance"] = c["distance_miles"]
    if c.get("ages"): params["age"] = ",".join(c["ages"])
    if c.get("genders"): params["gender"] = ",".join(c["genders"])
    out, page = [], 1
    while page <= 20:
        r = httpx.get("https://api.petfinder.com/v2/animals", headers=headers,
                      params={**params, "page": page}, timeout=20)
        r.raise_for_status()
        data = r.json()
        for a in data["animals"]:
            out.append(normalize_petfinder(a))
        if page >= data["pagination"]["total_pages"]:
            break
        page += 1
    return out


def normalize_petfinder(a):
    desc = a.get("description") or ""
    fee = re.search(r"\$\s?([\d,]+)", desc)
    addr = a.get("contact", {}).get("address", {})
    return {
        "source": "Petfinder", "url": a["url"], "name": a["name"],
        "age": (a.get("age") or "").lower(), "gender": (a.get("gender") or "").lower(),
        "color": (a.get("colors", {}).get("primary") or "").lower(),
        "fee": int(fee.group(1).replace(",", "")) if fee else None,
        "good_with_children": a.get("environment", {}).get("children"),
        "location": f"{addr.get('city', '')}, {addr.get('state', '')}",
        "country": addr.get("country") or "",
        "special_needs": a.get("attributes", {}).get("special_needs"),
        "shots_current": a.get("attributes", {}).get("shots_current"),
        "distance": a.get("distance"),
        "photo": (a.get("photos") or [{}])[0].get("medium"),
        "description": desc, "posted": a.get("published_at", "")[:10],
    }


def fetch_demo(_c):
    return json.loads((HERE / "sample_listings.json").read_text())


# ---------- Filtering ----------
def matches(l, c):
    if c.get("ages") and l["age"] not in c["ages"]: return False
    if c.get("genders") and l["gender"] not in c["genders"]: return False
    if c.get("colors") and not any(col in l["color"] for col in c["colors"]): return False
    if any(col in l["color"] for col in c.get("exclude_colors", [])): return False
    if c.get("countries") and l.get("country") and l["country"] not in c["countries"]: return False
    if c.get("healthy_only") and (l.get("special_needs") is True or l.get("shots_current") is False): return False
    if c.get("max_fee") is not None and l["fee"] is not None and l["fee"] > c["max_fee"]: return False
    if c.get("must_be_good_with_children") and l["good_with_children"] is not True: return False
    if c.get("distance_miles") and l.get("distance") is not None and l["distance"] > c["distance_miles"]: return False
    text = (l["name"] + " " + l["description"]).lower()
    if any(k in text for k in c.get("exclude_keywords", [])): return False
    return True


# ---------- Output ----------
def render(listings, total, new_only):
    e = html.escape
    cards = "".join(f"""
    <a class="card" href="{e(l['url'])}" target="_blank">
      {'<img src="' + e(l['photo']) + '">' if l.get('photo') else '<div class="noimg">🐶</div>'}
      <div class="body"><h3>{e(l['name'])}</h3>
        <p>{e(l['age'].title())} · {e(l['gender'].title())} · {e(l['color'].title() or '—')}</p>
        <p><b>{'$' + format(l['fee'], ',') if l['fee'] is not None else 'Fee not listed'}</b> · {e(l['location'])}
        {f"· {l['distance']:.0f} mi" if l.get('distance') is not None else ''}</p>
        <p class="meta">{e(l['source'])} · posted {e(l['posted'])}</p></div></a>""" for l in listings)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Pug Finder</title><style>
body{{font-family:-apple-system,sans-serif;background:#f6f4f0;margin:0;padding:24px;color:#222}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}}
.card{{background:#fff;border-radius:12px;overflow:hidden;text-decoration:none;color:inherit;box-shadow:0 1px 4px #0002}}
.card:hover{{box-shadow:0 4px 12px #0003}} img,.noimg{{width:100%;height:180px;object-fit:cover;background:#eee;font-size:64px;display:flex;align-items:center;justify-content:center}}
.body{{padding:12px}} h3{{margin:0 0 6px}} p{{margin:4px 0;font-size:14px}} .meta{{color:#888;font-size:12px}}
</style></head><body><h1>🐶 Pug Finder</h1>
<p>{len(listings)} {'new ' if new_only else ''}matches out of {total} listings · {datetime.now():%b %d, %Y %I:%M %p}</p>
<div class="grid">{cards or '<p>No new matches today.</p>'}</div></body></html>"""


def main():
    demo, show_all = "--demo" in sys.argv, "--all" in sys.argv
    c = yaml.safe_load((HERE / "criteria.yaml").read_text())
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() and not demo else set()

    sources = [fetch_demo] if demo else [fetch_petfinder]
    listings = []
    for fetch in sources:
        try:
            listings += fetch(c)
        except Exception as ex:  # one broken source shouldn't kill the run
            print(f"[warn] {fetch.__name__} failed: {ex}")

    hits = [l for l in listings if matches(l, c)]
    new = hits if show_all else [l for l in hits if l["url"] not in seen]
    OUT_FILE.write_text(render(new, len(listings), not show_all))
    if not demo:
        SEEN_FILE.write_text(json.dumps(sorted(seen | {l["url"] for l in hits})))
    print(f"{len(listings)} listings → {len(hits)} match → {len(new)} shown. Wrote {OUT_FILE}")
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT_FILE.resolve().as_uri())


if __name__ == "__main__":
    main()
