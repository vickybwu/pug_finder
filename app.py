"""Pug Finder web app (Streamlit). Run locally: streamlit run app.py"""
import streamlit as st

from pug_finder import describe, fetch_demo, fetch_web, load_criteria, matches


def get_access_code():
    try:
        return st.secrets.get("ACCESS_CODE")
    except Exception:  # no secrets configured
        return None


st.set_page_config(page_title="Pug Finder", page_icon="🐶", layout="wide")
st.title("🐶 Pug Finder")
st.caption("Searches the web for male pugs, about 1-3 years old, fawn or apricot, healthy, in the US")

code = get_access_code()
if code:
    entered = st.text_input("Access code", type="password")
    if entered != code:
        st.stop()

criteria = load_criteria()
demo = st.checkbox("Use sample data (offline test)")


@st.cache_data(ttl=600, show_spinner=False)  # reuse results for 10 min so repeat clicks are instant
def run_search(demo: bool):
    listings = fetch_demo(criteria) if demo else fetch_web(criteria)
    return listings, [l for l in listings if matches(l, criteria)]


if st.button("Find pugs", type="primary"):
    with st.spinner("Searching the web and reading listings (about 30-60 seconds)..."):
        try:
            listings, hits = run_search(demo)
        except Exception as e:
            st.error(f"Search failed: {e}")
            st.stop()
    st.success(f"{len(hits)} matches out of {len(listings)} pages scanned")
    st.caption("Details are read automatically from each page and can be wrong. "
               "Always verify with the seller, and never pay before meeting the dog.")
    cols = st.columns(3)
    for i, l in enumerate(hits):
        with cols[i % 3]:
            with st.container(border=True):
                if l.get("photo"):
                    st.image(l["photo"], use_container_width=True)
                st.subheader(l["name"])
                st.write(describe(l))
                fee = f"${l['fee']:,}" if l.get("fee") else "Price not found"
                st.write(f"**{fee}**" + (f" · {l['location']}" if l["location"] else ""))
                st.caption(l["snippet"])
                st.caption(l["source"])
                st.link_button("View listing", l["url"])
