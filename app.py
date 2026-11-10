"""Pug Finder web app (Streamlit). Run locally: streamlit run app.py"""
import streamlit as st

import pug_finder
from pug_finder import describe, diagnose, fetch_all, fetch_demo, is_full_match, load_criteria, rank


def get_access_code():
    try:
        return st.secrets.get("ACCESS_CODE")
    except Exception:  # no secrets configured
        return None


st.set_page_config(page_title="Matthew-san's personal puggy finder", page_icon="🐶", layout="wide")
st.title("🐶 Matthew-san's personal puggy finder")
st.caption("Male pugs, about 1-3 years, fawn or apricot, healthy, in the US · "
           "best matches first, partial matches below")

code = get_access_code()
if code:
    entered = st.text_input("Access code", type="password")
    if entered != code:
        st.stop()

criteria = load_criteria()
demo = st.checkbox("Use sample data (offline test)")


@st.cache_data(ttl=600, show_spinner=False)  # reuse results for 10 min
def run_search(demo: bool):
    listings = fetch_demo(criteria) if demo else fetch_all(criteria)
    stats = dict(pug_finder.LAST_STATS)
    if not demo and not listings:
        raise RuntimeError("No source returned listings. " +
                           " | ".join(f"{k}: {v}" for k, v in (stats.get("sources") or {}).items()))
    return listings, rank(listings, criteria), stats


def card(l):
    with st.container(border=True):
        if l.get("photo"):
            st.image(l["photo"], use_container_width=True)
        st.subheader(l["name"][:80])
        st.write(describe(l))
        fee = f"${l['fee']:,}" if l.get("fee") else "Price not listed"
        st.write(f"**{fee}**" + (f" · {l['location']}" if l.get("location") else ""))
        if not is_full_match(l):
            st.caption("⚠️ " + ", ".join(l["misses"]))
        st.caption(l.get("snippet", ""))
        st.caption(l["source"])
        st.link_button("View listing", l["url"])


if st.button("Find pugs", type="primary"):
    with st.spinner("Searching Petfinder and the web..."):
        try:
            listings, ranked, stats = run_search(demo)
        except Exception as e:
            st.error(f"Search failed: {e}")
            st.stop()
    pug_finder.LAST_STATS.update(stats)
    full = [l for l in ranked if is_full_match(l)]
    partial = [l for l in ranked if not is_full_match(l)]
    st.success(f"{len(full)} full matches · {len(partial)} partial matches · {len(listings)} listings checked")

    with st.expander("Search details"):
        st.code("\n".join(diagnose(listings, criteria, stats.get("urls"))))

    for title, group in (("✅ Matches your criteria", full), ("Other pugs (don't meet every criterion)", partial)):
        if group:
            st.header(title)
            cols = st.columns(3)
            for i, l in enumerate(group):
                with cols[i % 3]:
                    card(l)

st.markdown("<p style='font-size:12px;color:#888'>Petfinder results powered by "
            "<a href='https://www.petfinder.com' target='_blank'>Petfinder</a>. "
            "Always verify details with the shelter or seller, and never pay before meeting the dog.</p>",
            unsafe_allow_html=True)
