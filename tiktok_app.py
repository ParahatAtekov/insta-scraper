from __future__ import annotations
def main():

    # -------------------------------------------------
    # Streamlit config MUST be first
    # -------------------------------------------------
    import streamlit as st

    st.set_page_config(
        page_title="TikTok Hashtag Scraper",
        layout="wide",
    )

    # -------------------------------------------------
    # Standard imports AFTER config
    # -------------------------------------------------
    import os
    from datetime import datetime, timezone

    import pandas as pd
    from dotenv import load_dotenv

    from scrapers.tiktok import (
        LamatokClient,
        Filters,
        resolve_hashtag_id,
        fetch_hashtag_medias,
    )

    # -------------------------------------------------
    # App setup
    # -------------------------------------------------
    load_dotenv()

    st.title("TikTok Hashtag Scraper (Lamatok API)")

    API_KEY = os.getenv("LAMATOK_KEY")
    if not API_KEY:
        st.error("LAMATOK_KEY missing in .env")
        st.stop()

    client = LamatokClient(API_KEY)

    # -------------------------------------------------
    # Sidebar Inputs
    # -------------------------------------------------
    st.sidebar.header("Hashtags")
    hashtags_raw = st.sidebar.text_input(
        "Comma-separated hashtags",
        placeholder="bitcoin, crypto, trading",
    )

    posts_per_hashtag = st.sidebar.number_input(
        "Posts per hashtag", 1, 1000, 100
    )

    st.sidebar.header("Time Filter")
    last_days = st.sidebar.number_input(
        "Last X days", 1, 3650, 365
    )

    st.sidebar.header("Engagement Filters")
    min_views = st.sidebar.number_input("Min views", value=0)
    min_likes = st.sidebar.number_input("Min likes", value=0)
    min_comments = st.sidebar.number_input("Min comments", value=0)

    st.sidebar.header("Ordering")
    order_column = st.sidebar.selectbox(
        "Order by",
        ["play_count", "like_count", "comment_count", "follower_count", "create_time"],
    )
    order_direction = st.sidebar.radio(
        "Direction", ["Descending", "Ascending"]
    )

    run = st.sidebar.button("Run")

    # -------------------------------------------------
    # Execution
    # -------------------------------------------------
    rows = []
    total_fetched = 0
    total_collected = 0
    total_kept = 0

    if run:
        hashtags = [h.strip().lower() for h in hashtags_raw.split(",") if h.strip()]
        if not hashtags:
            st.error("At least one hashtag required")
            st.stop()

        filters = Filters(
            last_days=last_days,
            min_views=min_views,
            min_likes=min_likes,
            min_comments=min_comments,
        )

        with st.spinner("Scraping TikTok…"):
            for tag in hashtags:
                try:
                    hid = resolve_hashtag_id(client, tag)
                    if not hid:
                        st.warning(f"Hashtag not found: {tag}")
                        continue

                    items, fetched, collected = fetch_hashtag_medias(
                        client=client,
                        hashtag=tag,
                        hashtag_id=hid,
                        limit=posts_per_hashtag,
                        filters=filters,
                    )

                    total_fetched += fetched
                    total_collected += collected
                    total_kept += len(items)
                    rows.extend(items)

                except Exception as e:
                    st.error(f"{tag}: {e}")

    # -------------------------------------------------
    # Output
    # -------------------------------------------------
    if rows:
        st.subheader("Scrape Statistics")

        c1, c2, c3 = st.columns(3)
        c1.metric("Videos fetched", total_fetched)
        c2.metric("Videos collected", total_collected)
        c3.metric("Videos kept (after filters)", total_kept)

        df = pd.DataFrame([r.__dict__ for r in rows])

        numeric_cols = [
            "play_count",
            "like_count",
            "comment_count",
            "follower_count",
            "create_time",
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df = df.sort_values(
            by=order_column,
            ascending=(order_direction == "Ascending"),
            kind="mergesort",
        )

        df["create_time"] = df["create_time"].apply(
            lambda ts: datetime.fromtimestamp(int(ts), timezone.utc).strftime("%d.%m.%Y")
            if ts else None
        )

        st.subheader("Results")
        st.dataframe(
            df,
            width="stretch",
            column_config={
                "video_url": st.column_config.LinkColumn("Video"),
                "profile_url": st.column_config.LinkColumn("Profile"),
            },
        )

        st.download_button(
            "Download CSV",
            df.to_csv(index=False).encode("utf-8"),
            "tiktok_results.csv",
            "text/csv",
        )

        st.download_button(
            "Download JSON",
            df.to_json(orient="records", indent=2),
            "tiktok_results.json",
            "application/json",
        )
    elif run:
        st.warning("No results found.")

if __name__ == "__main__":
    main()