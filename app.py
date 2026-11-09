"""Pug Finder web app (Streamlit). Run locally: streamlit run app.py"""
import os
from pathlib import Path

import streamlit as st
import yaml

# Load secrets (Streamlit Cloud) into env vars before using the finder
try:
    for k in ("PETFINDER_KEY", "PETFINDER_SECRET"):
        if k in st.secrets:
            os.environ[k] = st.secrets[k]
    APP_PASSWORD = st.secrets.get("APP_PASSWORD")
except Exception:  # no secrets file locally
    APP_PASSWORD = None

from pug_finder import fetch_petfinder, fetch_demo, matches

st.set_page_config(page_title="Pug Finder", page_icon="🐶", layout="wide")
st.title("🐶 Pug Finder")
st.caption("Male · about 1-3 years · fawn or apricot · healthy · US")

# Optional shared password to protect your API quota
if APP_PASSWORD and st.text_input("Password", type="password") != APP_PASSWORD:
    st.stop()

criteria = yaml.safe_load((Path(__file__).parent / "criteria.yaml").read_text())
demo = not os.environ.get("PETFINDER_KEY")
if demo:
    st.info("No Petfinder key configured - showing sample data.")


@st.cache_data(ttl=600, show_spinner=False)  # cache 10 min so repeat clicks don't burn quota
def run_search(demo: bool):
    listings = fetch_demo(criteria) if demo else fetch_petfinder(criteria)
    return listings, [l for l in listings if matches(l, criteria)]


if st.button("Find pugs", type="primary"):
    with st.spinner("Searching..."):
        try:
            listings, hits = run_search(demo)
        except Exception as e:
            st.error(f"Search failed: {e}")
            st.stop()
    st.success(f"{len(hits)} matches out of {len(listings)} listings")
    cols = st.columns(3)
    for i, l in enumerate(hits):
        with cols[i % 3]:
            with st.container(border=True):
                if l.get("photo"):
                    st.image(l["photo"], use_container_width=True)
                st.subheader(l["name"])
                st.write(f"{l['age'].title()} · {l['gender'].title()} · {l['color'].title() or '-'}")
                fee = f"${l['fee']:,}" if l.get("fee") is not None else "Fee not listed"
                st.write(f"**{fee}** · {l['location']}")
                st.caption(f"{l['source']} · posted {l['posted']}")
                st.link_button("View listing", l["url"])
