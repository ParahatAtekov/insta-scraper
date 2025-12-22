# scrapers/instagram.py
import time
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from hikerapi import Client
from typing import Any, Dict, List, Union

logger = logging.getLogger("hikerapi-scraper")


@dataclass(frozen=True)
class ScrapeRequest:
    method: str                     # "hashtag" | "username"
    target: str                     # "dog" | "nasa"
    feed: str                       # hashtag: top|recent|clips|auto_(top_to_recent) ; username: posts|clips
    max_posts: int = 50
    max_requests: int = 10

    days_ago: int = 365
    min_plays: int = 0
    min_likes: int = 0
    min_comments: int = 0
    include_unknown_dates: bool = True

    debug: bool = False


# ----------------------------
# Response normalization
# ----------------------------
def _flatten_items(resp: Any) -> List[Dict[str, Any]]:
    if isinstance(resp, dict):
        items = resp.get("items", [])
    elif isinstance(resp, list):
        items = resp
    else:
        return []

    out: List[Dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
        elif isinstance(it, list):
            out.extend([x for x in it if isinstance(x, dict)])
    return out


def _cursor(resp: Any) -> Optional[str]:
    if not isinstance(resp, dict):
        return None
    for k in ("max_id", "next_max_id", "end_cursor", "next_end_cursor"):
        v = resp.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _ts(item: Dict[str, Any]) -> Optional[int]:
    v = item.get("taken_at_ts") or item.get("taken_at_timestamp")
    if isinstance(v, (int, float)) and v > 0:
        return int(v)
    return None


def _plays(item: Dict[str, Any]) -> int:
    # prefer play_count (reels/clips) over view_count (often 0/disabled)
    v = item.get("play_count")
    if isinstance(v, int):
        return v
    v = item.get("view_count")
    if isinstance(v, int):
        return v
    return 0


def _i(item: Dict[str, Any], key: str) -> int:
    v = item.get(key)
    return v if isinstance(v, int) else 0


def _date_str(ts: Optional[int]) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "Unknown"


def _row(item: Dict[str, Any], source: str, discovery: str) -> Optional[Dict[str, Any]]:
    code = item.get("code")
    if not isinstance(code, str) or not code:
        return None

    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    username = user.get("username") if isinstance(user.get("username"), str) else "unknown"

    ts = _ts(item)
    plays = _plays(item)
    likes = _i(item, "like_count")
    comments = _i(item, "comment_count")

    return {
        "id": item.get("pk"),
        "code": code,
        "url": f"https://www.instagram.com/p/{code}/",
        "username": username,
        "date_ts": ts or 0,
        "date": _date_str(ts),
        "plays": plays,
        "likes": likes,
        "comments": comments,
        "engagement": plays + likes + comments,
        "metrics_disabled": bool(item.get("like_and_view_counts_disabled", False)),
        "source": source,
        "discovery": discovery,
    }


def _passes(item: Dict[str, Any], req: ScrapeRequest, cutoff_ts: int) -> bool:
    ts = _ts(item)
    if ts is None:
        if not req.include_unknown_dates:
            return False
    else:
        if ts < cutoff_ts:
            return False

    if _plays(item) < req.min_plays:
        return False
    if _i(item, "like_count") < req.min_likes:
        return False
    if _i(item, "comment_count") < req.min_comments:
        return False

    return True



def scrape_user_full(client: Client, username: str) -> Dict[str, Any]:
    user = client.user_by_username_v1(username=username)
    if isinstance(user, dict):
        u = user.get("user", user)
    else:
        raise ValueError("Unexpected user response")

    user_id = u.get("pk") or u.get("id")
    if not user_id:
        raise ValueError("User ID not found")

    profile = {
        "Username": u.get("username"),
        "Full Name": u.get("full_name"),
        "Followers": u.get("follower_count"),
        "Following": u.get("following_count"),
        "Posts": u.get("media_count"),
        "Verified": u.get("is_verified"),
        "Private": u.get("is_private"),
        "Bio": u.get("biography"),
        "Profile URL": f"https://www.instagram.com/{username}",
    }

    # Handle user_medias_chunk_v1 response (list or dict)
    medias_resp = client.user_medias_chunk_v1(user_id=user_id)
    if isinstance(medias_resp, list):
        posts = medias_resp
    elif isinstance(medias_resp, dict):
        posts = medias_resp.get("items", [])
    else:
        posts = []

    # Handle user_clips_chunk_v1 response (list or dict)
    clips_resp = client.user_clips_chunk_v1(user_id=user_id)
    if isinstance(clips_resp, list):
        reels = clips_resp
    elif isinstance(clips_resp, dict):
        reels = clips_resp.get("items", [])
    else:
        reels = []

    return {
        "profile": profile,
        "posts_count": len(posts),
        "reels_count": len(reels),
        "sample_posts": posts[:10],
        "sample_reels": reels[:10],
    }



# ----------------------------
# Paging
# ----------------------------
def _paginate(
    fetch_fn: Callable[[Optional[str]], Tuple[Any, str]],
    *,
    req: ScrapeRequest,
    source: str,
    discovery: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cutoff_ts = int(time.time() - req.days_ago * 86400)

    kept_rows: List[Dict[str, Any]] = []
    fetched = 0
    kept = 0
    requests = 0
    cursor = None
    endpoint = None

    while kept < req.max_posts and requests < req.max_requests:
        resp, endpoint = fetch_fn(cursor)
        requests += 1

        items = _flatten_items(resp)
        fetched += len(items)

        logger.info(
            "Page %d | source=%s | items=%d | cursor_in=%s",
            requests,
            source,
            len(items),
            bool(cursor),
        )

        for it in items:
            if kept >= req.max_posts:
                break
            if _passes(it, req, cutoff_ts):
                r = _row(it, source=source, discovery=discovery)
                if r:
                    kept_rows.append(r)
                    kept += 1

        cursor = _cursor(resp)
        if not cursor or not items:
            break

    meta = {
        "endpoint": endpoint,
        "cursor": cursor,
        "fetched": fetched,
        "kept": kept,
        "requests": requests,
    }
    return kept_rows, meta


# ----------------------------
# Fetch adapters
# ----------------------------
def _resolve_user_id(client: Client, username: str) -> Tuple[str, Dict[str, Any]]:
    user_info = client.user_by_username_v1(username=username)
    if isinstance(user_info, dict):
        user = user_info.get("user", user_info)
    elif isinstance(user_info, list) and user_info and isinstance(user_info[0], dict):
        user = user_info[0]
    else:
        raise ValueError("Unexpected user response")

    user_id = user.get("pk") or user.get("id") or user.get("user_id")
    if not user_id:
        raise ValueError("User ID not found")

    profile = {
        "Username": username,
        "Follower Count": user.get("follower_count", "N/A"),
        "Profile URL": f"https://www.instagram.com/{username}",
    }
    return str(user_id), profile


def scrape_instagram(client: Client, req: ScrapeRequest) -> Dict[str, Any]:
    try:
        posts: List[Dict[str, Any]] = []
        profile_info: Dict[str, Any] = {}
        effective_feed = req.feed
        fallback_used = False

        if req.method == "username":
            user_id, profile_info = _resolve_user_id(client, req.target)

            if req.feed not in ("posts", "clips"):
                raise ValueError("Username feed must be Posts or Clips")

            def fetch_user(cursor: Optional[str]) -> Tuple[Any, str]:
                if req.feed == "posts":
                    return client.user_medias_chunk_v1(user_id=user_id, end_cursor=cursor), "user_medias_chunk_v1"
                return client.user_clips_chunk_v1(user_id=user_id, end_cursor=cursor), "user_clips_chunk_v1"

            posts, meta = _paginate(fetch_user, req=req, source=f"user_{req.feed}", discovery=f"@{req.target}")

        else:
            # hashtag
            norm_feed = req.feed
            if norm_feed == "auto_(top_to_recent)" or norm_feed == "auto_(top_to_recent)":
                norm_feed = "auto_(top_to_recent)"
            if norm_feed not in ("top", "recent", "clips", "auto_(top_to_recent)", "auto_(top_to_recent)"):
                # app uses "auto_(top_to_recent)" via replacements; keep tolerant
                pass

            def fetch_hashtag(feed: str) -> Callable[[Optional[str]], Tuple[Any, str]]:
                if feed == "top":
                    return lambda c: (client.hashtag_medias_top_chunk_v1(name=req.target, max_id=c), "hashtag_medias_top_chunk_v1")
                if feed == "recent":
                    return lambda c: (client.hashtag_medias_top_recent_chunk_v1(name=req.target, max_id=c), "hashtag_medias_top_recent_chunk_v1")
                if feed == "clips":
                    return lambda c: (client.hashtag_medias_clips_chunk_v1(name=req.target, max_id=c), "hashtag_medias_clips_chunk_v1")
                raise ValueError(f"Unknown hashtag feed: {feed}")

            if req.feed.startswith("auto"):
                effective_feed = "top"
                top_req = ScrapeRequest(**{**req.__dict__, "feed": "top"})
                top_posts, top_meta = _paginate(fetch_hashtag("top"), req=top_req, source="hashtag_top", discovery=f"#{req.target}")
                posts.extend(top_posts)

                if len(posts) < req.max_posts:
                    fallback_used = True
                    remaining = req.max_posts - len(posts)
                    effective_feed = "top+recent"
                    recent_req = ScrapeRequest(**{**req.__dict__, "feed": "recent", "max_posts": remaining})
                    recent_posts, recent_meta = _paginate(fetch_hashtag("recent"), req=recent_req, source="hashtag_recent", discovery=f"#{req.target}")
                    posts.extend(recent_posts)

                    meta = {
                        "endpoint": f"{top_meta.get('endpoint')} + {recent_meta.get('endpoint')}",
                        "cursor": recent_meta.get("cursor") or top_meta.get("cursor"),
                        "fetched": top_meta.get("fetched", 0) + recent_meta.get("fetched", 0),
                        "kept": len(posts),
                        "requests": top_meta.get("requests", 0) + recent_meta.get("requests", 0),
                    }
                else:
                    meta = top_meta
            else:
                effective_feed = req.feed
                posts, meta = _paginate(
                    fetch_hashtag(req.feed),
                    req=req,
                    source=f"hashtag_{req.feed}",
                    discovery=f"#{req.target}",
                )

        meta.update(
            {
                "requested": req.max_posts,
                "method": req.method,
                "target": req.target,
                "effective_feed": effective_feed,
                "fallback_used": fallback_used,
            }
        )
        return {"profile_info": profile_info, "posts": posts, "meta": meta}

    except Exception as e:
        debug = None
        if req.debug:
            import traceback
            debug = traceback.format_exc()
        return {"profile_info": {}, "posts": [], "error": str(e), "debug": debug}