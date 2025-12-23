# app.py (ROOT APP)

import streamlit as st

st.set_page_config(
    page_title="Social Media Scraper",
    layout="wide",
)

# -------------------------------------------------
# Platform selector (FIRST STEP)
# -------------------------------------------------
st.sidebar.title("Platform")
platform = st.sidebar.radio(
    "Choose platform",
    ["Instagram", "TikTok"],
    index=0,
)

# Optional: clear state when switching platforms
if st.session_state.get("active_platform") != platform:
    st.session_state.clear()
    st.session_state["active_platform"] = platform

st.sidebar.markdown("---")

# -------------------------------------------------
# Route to selected platform
# -------------------------------------------------
if platform == "Instagram":
    from instagram_app import main as instagram_main
    instagram_main()

elif platform == "TikTok":
    from tiktok_app import main as tiktok_main
    tiktok_main()