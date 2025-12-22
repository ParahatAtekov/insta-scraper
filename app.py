# app.py
import os
import re
import time
import logging

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from hikerapi import Client

from scrapers.instagram import (
    ScrapeRequest,
    scrape_instagram,
    scrape_user_full,
)

# -------------------------------------------------
# Setup
# -------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hikerapi-streamlit")

st.set_page_config(page_title="Instagram Scraper (HikerAPI)", layout="wide")
st.title("Instagram Scraper (HikerAPI)")

token = os.getenv("HIKERAPI_TOKEN")
if not token:
    st.error("HIKERAPI_TOKEN not found in .env")
    st.stop()

client = Client(token=token)

# -------------------------------------------------
# Helpers / Cache
# -------------------------------------------------
def sanitize_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value).strip("_") or "export"


@st.cache_data(show_spinner=False, ttl=300)
def cached_scrape(req_dict: dict) -> dict:
    req = ScrapeRequest(**req_dict)
    return scrape_instagram(client, req)


@st.cache_data(show_spinner=False)
def cached_user_full(username: str):
    return scrape_user_full(client, username)


# -------------------------------------------------
# Sidebar
# -------------------------------------------------
st.sidebar.header("Discovery")
method = st.sidebar.selectbox("Type", ["Hashtag", "Username"], index=0)
target = st.sidebar.text_input("Target", placeholder="dog | bitcoin | nasa")

st.sidebar.header("Feed")
if method == "Hashtag":
    feed = st.sidebar.selectbox(
        "Feed", ["Top", "Recent", "Clips", "Auto (Top → Recent)"], index=0
    )
else:
    feed = st.sidebar.selectbox("Feed", ["Posts", "Clips"], index=0)

st.sidebar.header("Depth")
max_posts = st.sidebar.slider("Max results", 1, 300, 50)
max_requests = st.sidebar.slider("Max API requests", 1, 30, 10)

st.sidebar.header("Filters")
days_ago = st.sidebar.number_input("Within last (days)", min_value=1, value=365)
min_plays = st.sidebar.number_input("Min plays", min_value=0, value=0)
min_likes = st.sidebar.number_input("Min likes", min_value=0, value=0)
min_comments = st.sidebar.number_input("Min comments", min_value=0, value=0)
include_unknown_dates = st.sidebar.checkbox(
    "Include items missing timestamps", value=True
)

st.sidebar.header("Output")
sort_by = st.sidebar.selectbox(
    "Sort by", ["Engagement", "Plays", "Likes", "Comments", "Date"], index=0
)
debug = st.sidebar.checkbox("Debug (show traceback)", value=False)

run = st.sidebar.button("Run")

# -------------------------------------------------
# Run scrape (STATEFUL)
# -------------------------------------------------
if run:
    t = target.strip().lstrip("#").lstrip("@")
    if not t:
        st.error("Target required.")
        st.stop()

    req = ScrapeRequest(
        method=method.lower(),
        target=t,
        feed=feed.lower().replace(" ", "_").replace("→", "to"),
        max_posts=int(max_posts),
        max_requests=int(max_requests),
        days_ago=int(days_ago),
        min_plays=int(min_plays),
        min_likes=int(min_likes),
        min_comments=int(min_comments),
        include_unknown_dates=bool(include_unknown_dates),
        debug=bool(debug),
    )

    logger.info(
        "UI trigger | method=%s | feed=%s | target=%s",
        req.method,
        req.feed,
        req.target,
    )

    with st.status("Scraping…", expanded=False):
        st.session_state["scrape_result"] = cached_scrape(req.__dict__)
        st.session_state["scrape_req"] = req

    # reset user inspection on new search
    st.session_state.pop("inspect_user", None)
    st.session_state.pop("inspect_user_data", None)

# -------------------------------------------------
# Render results (NOT tied to button)
# -------------------------------------------------
if "scrape_result" not in st.session_state:
    st.info("Configure options and press **Run**.")
    st.stop()

result = st.session_state["scrape_result"]
req = st.session_state["scrape_req"]

if result.get("error"):
    st.error(result["error"])
    if result.get("debug"):
        st.code(result["debug"])
    st.stop()

posts = result.get("posts") or []
profile = result.get("profile_info") or {}
meta = result.get("meta") or {}

if not posts:
    st.warning("No posts matched your filters.")
    st.stop()

df = pd.DataFrame(posts)

# Sorting
sort_map = {
    "Engagement": "engagement",
    "Plays": "plays",
    "Likes": "likes",
    "Comments": "comments",
    "Date": "date_ts",
}
df = df.sort_values(by=sort_map[sort_by], ascending=False)

# -------------------------------------------------
# Metrics
# -------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Requested", meta.get("requested", req.max_posts))
c2.metric("Fetched", meta.get("fetched", 0))
c3.metric("Kept", meta.get("kept", len(df)))
c4.metric("Requests", meta.get("requests", 0))

msg = f"Endpoint: {meta.get('endpoint') or '—'} | Feed used: {meta.get('effective_feed') or req.feed}"
if meta.get("fallback_used"):
    msg += " | Fallback: Top → Recent"
st.caption(msg)

# -------------------------------------------------
# Profile (username mode)
# -------------------------------------------------
if profile:
    st.subheader("Profile")
    st.table(pd.DataFrame(profile, index=["Value"]).T)

# -------------------------------------------------
# Results table
# -------------------------------------------------
st.subheader("Results")

selected = st.dataframe(
    df[
        [
            "date",
            "username",
            "plays",
            "likes",
            "comments",
            "engagement",
            "metrics_disabled",
            "source",
            "url",
        ]
    ],
    width="stretch",
    key="results_table",
    on_select="rerun",
    selection_mode="single-row",
)

if selected and selected.selection.rows:
    row = selected.selection.rows[0]
    username = df.iloc[row]["username"]

    if st.session_state.get("inspect_user") != username:
        st.session_state["inspect_user"] = username
        st.session_state.pop("inspect_user_data", None)

# -------------------------------------------------
# User inspection (ABOVE Export)
# -------------------------------------------------
if "inspect_user" in st.session_state:
    uname = st.session_state["inspect_user"]

    st.subheader(f"User details: @{uname}")

    if "inspect_user_data" not in st.session_state:
        with st.spinner("Fetching user info…"):
            st.session_state["inspect_user_data"] = cached_user_full(uname)

    info = st.session_state["inspect_user_data"]

    st.table(pd.DataFrame(info["profile"], index=["Value"]).T)
    st.caption(
        f"Posts sampled: {info['posts_count']} | Reels sampled: {info['reels_count']}"
    )

# -------------------------------------------------
# Export
# -------------------------------------------------
st.subheader("Export")
safe = sanitize_filename(req.target)

c1, c2 = st.columns(2)
with c1:
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"instagram_{safe}.csv",
        mime="text/csv",
    )
with c2:
    st.download_button(
        "Download JSON",
        df.to_json(orient="records", indent=2),
        file_name=f"instagram_{safe}.json",
        mime="application/json",
    )

with st.expander("Run metadata"):
    st.json(meta, expanded=False)