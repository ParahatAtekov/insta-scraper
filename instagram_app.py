# app.py
def main():

    import os
    import re
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


    def normalize_feed(method: str, feed_label: str) -> str:
        if method == "Hashtag":
            return "auto_(top_to_recent)" if feed_label.startswith("Auto") else feed_label.lower()
        return feed_label.lower()


    def parse_targets(method: str, raw: str):
        raw = raw.strip()
        if method == "Hashtag":
            tags_raw = [x.strip() for x in raw.split(",")]
            targets, invalid = [], []
            for x in tags_raw:
                if not x:
                    continue
                t = x.lstrip("#").strip()
                if not re.fullmatch(r"[A-Za-z0-9_]+", t):
                    invalid.append(x)
                    continue
                targets.append(t)
            return targets, invalid
        u = raw.lstrip("@").strip()
        return ([u] if u else []), []


    # -------------------------------------------------
    # Sidebar
    # -------------------------------------------------
    st.sidebar.header("Discovery")
    method = st.sidebar.selectbox("Type", ["Hashtag", "Username"], index=0)
    target = st.sidebar.text_input("Target", placeholder="dog, bitcoin, nasa")

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
    # Run scrape
    # -------------------------------------------------
    if run:
        raw = target.strip()
        if not raw:
            st.error("Target required.")
            st.stop()

        targets, invalid = parse_targets(method, raw)
        if invalid:
            st.warning(f"Ignored invalid hashtag(s): {', '.join(invalid)}")
        if not targets:
            st.error("No valid targets found.")
            st.stop()

        base_req = ScrapeRequest(
            method=method.lower(),
            target="",
            feed=normalize_feed(method, feed),
            max_posts=int(max_posts),
            max_requests=int(max_requests),
            days_ago=int(days_ago),
            min_plays=int(min_plays),
            min_likes=int(min_likes),
            min_comments=int(min_comments),
            include_unknown_dates=bool(include_unknown_dates),
            debug=bool(debug),
        )

        all_posts = []
        meta = {
            "method": base_req.method,
            "targets": targets,
            "effective_feed": base_req.feed,
            "requested": base_req.max_posts,
            "total_fetched": 0,
            "total_kept": 0,
            "total_requests": 0,
            "fallback_used": False,
        }

        with st.status("Scraping…", expanded=False):
            for t in targets:
                req = ScrapeRequest(**{**base_req.__dict__, "target": t})
                res = cached_scrape(req.__dict__)

                if res.get("error"):
                    st.warning(f"{t}: {res['error']}")
                    continue

                posts = res.get("posts", [])
                m = res.get("meta", {})

                for p in posts:
                    p["hashtag"] = f"#{t}"

                all_posts.extend(posts)
                meta["total_fetched"] += m.get("fetched", 0)
                meta["total_kept"] += m.get("kept", len(posts))
                meta["total_requests"] += m.get("requests", 0)
                meta["fallback_used"] |= bool(m.get("fallback_used", False))

        st.session_state["scrape_result"] = {"posts": all_posts, "meta": meta}
        st.session_state["scrape_req"] = base_req
        st.session_state.pop("inspect_user", None)
        st.session_state.pop("inspect_user_data", None)

    # -------------------------------------------------
    # Render results
    # -------------------------------------------------
    if "scrape_result" not in st.session_state:
        st.info("Configure options and press **Run**.")
        st.stop()

    posts = st.session_state["scrape_result"]["posts"]
    meta = st.session_state["scrape_result"]["meta"]

    if not posts:
        st.warning("No posts matched your filters.")
        st.stop()

    df = pd.DataFrame(posts)

    # Ensure columns exist
    for col, default in {
        "hashtag": "",
        "plays": 0,
        "likes": 0,
        "comments": 0,
        "engagement": 0,
        "date": "Unknown",
        "date_ts": 0,
        "username": "unknown",
        "url": "",
        "source": "",
        "metrics_disabled": False,
    }.items():
        if col not in df.columns:
            df[col] = default

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
    c1.metric("Requested (per hashtag)", meta["requested"])
    c2.metric("Fetched (total)", meta["total_fetched"])
    c3.metric("Kept (total)", meta["total_kept"])
    c4.metric("Requests (total)", meta["total_requests"])

    # -------------------------------------------------
    # Results table (ROW SELECTION RESTORED)
    # -------------------------------------------------
    st.subheader("Results")

    selection = st.dataframe(
        df[
            [
                "hashtag",
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
        use_container_width=True,
        key="results_table",
        on_select="rerun",
        selection_mode="single-row",
    )

    if selection and selection.selection.rows:
        row = selection.selection.rows[0]
        uname = df.iloc[row]["username"]

        if st.session_state.get("inspect_user") != uname:
            st.session_state["inspect_user"] = uname
            st.session_state.pop("inspect_user_data", None)

    # -------------------------------------------------
    # User inspection (RESTORED)
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
    safe = sanitize_filename("_".join(meta["targets"]))

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

if __name__ == "__main__":
    main()