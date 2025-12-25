# Instagram & TikTok Scraper App

🔗 **Live App**  
https://insta-scraper-onc2fb9prn58mwq5gaqjja.streamlit.app/

---

## What Does the System Do?

The system scrapes **Instagram** and **TikTok** content based on user-defined filters and displays the results in a structured table.

### User Inputs
- Platform (Instagram or TikTok)
- Hashtag(s) or Username
- Minimum View Count
- Minimum Like Count
- Minimum Comment Count
- Posted in the last X days
- Number of posts to scrape

### Output Table Columns
- Hashtag
- Username
- View Count
- Like Count
- Comment Count
- Post URL
- User Profile URL
- Region
- User Follower Count

---

## How It Works

### 1. User Input
The Streamlit UI collects all scraping parameters from the user.

---

### 2. API Endpoint Selection

Based on the platform and input type, the system calls specific API endpoints.

#### TikTok
- `/v1/hashtag/info`  
  - Input: hashtag (string)  
  - Output: hashtag ID and metadata

- `/v1/hashtag/medias`  
  - Input: hashtag ID (integer)  
  - Output: media items

#### Instagram
- `/v1/user/by/username`  
  - Input: username (string)  
  - Output: user ID (integer)

- `/v1/user/medias/chunk`  
  - Input: user ID (integer)  
  - Output: user posts (paginated)

- `/v1/user/clips/chunk`  
  - Input: user ID (integer)  
  - Output: user reels (paginated)

- `/v1/hashtag/medias/top/chunk`  
  - Input: hashtag (string)  
  - Output: top posts (paginated)

- `/v1/hashtag/medias/top/recent/chunk`  
  - Input: hashtag (string)  
  - Output: recent top posts (paginated)

- `/v1/hashtag/medias/clips/chunk`  
  - Input: hashtag (string)  
  - Output: reels (paginated)

---

### 3. API Response
The APIs return large JSON payloads containing media, user, and engagement data.

---

### 4. Response Flattening
Only the relevant media objects (`items`) are extracted.

- Instagram: `flatten_items` function  
- TikTok: `LamatokClient` class

---

### 5. Data Extraction

#### TikTok Fields
```text
hashtag: str
post_id: str
video_url: Optional[str]
play_count: int
like_count: int
comment_count: int
create_time: int
username: Optional[str]
follower_count: int
profile_url: Optional[str]
region: Optional[str]
```

#### Instagram Fields
```text
id: Optional[str]
code: str
url: str
username: Optional[str]
date_ts: int
date: str
plays: int
likes: int
comments: int
engagement: int
metrics_disabled: bool
source: str
discovery: str
```

---

### 6. Filtering
Posts are removed if they do not meet the user-defined thresholds:
- Minimum view count
- Minimum like count
- Minimum comment count
- Posted within the last **X days**
- Optional exclusion of posts with missing timestamps

---

### 7. Table Formatting
All retained records are normalized into a consistent schema and formatted into a tabular structure suitable for display and export.

---

### 8. UI Output
The formatted table is rendered in the Streamlit interface, allowing users to:
- View scraped content
- Sort and scan results
- Export data for further analysis

---

## Why HikerAPI and LamatokAPI?

- **HikerAPI**: https://hikerapi.com/
- **LamatokAPI**: https://lamatok.com/

### Reasons for Choosing These APIs
- No social media account or login required
- No subscription required
- Charges only for successful requests
- More cost-effective than most alternatives
- Referral programs available
- Stable **v1 endpoints** with validated data
- High throughput (≈300 requests per second)
- Both APIs are maintained by the same developers

---

## Tech Stack
- **Python** – API integration and data processing
- **Streamlit** – UI framework

---

## Hosting
Hosted on **Streamlit Community Cloud**  
https://docs.streamlit.io/deploy/streamlit-community-cloud
