from __future__ import annotations

import time
import requests
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Iterable, Tuple

BASE_URL = "https://api.lamatok.com/v1"
PAGE_SIZE = 30
TIMEOUT = 40  # seconds


class LamatokError(RuntimeError):
    pass


class LamatokClient:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = {**params, "access_key": self.api_key}
        resp = self.session.get(
            f"{BASE_URL}{path}",
            params=params,
            timeout=TIMEOUT,
        )

        try:
            data = resp.json()
        except ValueError:
            raise LamatokError("Invalid JSON response")

        if not resp.ok:
            raise LamatokError(
                data.get("error")
                or data.get("message")
                or f"HTTP {resp.status_code}"
            )

        return data


# ---------------- Domain ----------------
@dataclass(frozen=True)
class Filters:
    last_days: int
    min_views: int
    min_likes: int
    min_comments: int


@dataclass(frozen=True)
class MediaRow:
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


# ---------------- API ----------------
def resolve_hashtag_id(client: LamatokClient, hashtag: str) -> Optional[int]:
    data = client.get("/hashtag/info", {"hashtag": hashtag})
    challenge = data.get("challengeInfo", {}).get("challenge", {})
    return int(challenge["id"]) if "id" in challenge else None


def iter_hashtag_medias(
    client: LamatokClient,
    hashtag_id: int,
) -> Iterable[Dict[str, Any]]:
    cursor = None
    while True:
        params = {
            "id": hashtag_id,
            "count": PAGE_SIZE,
        }
        if cursor is not None:
            params["cursor"] = cursor

        data = client.get("/hashtag/medias", params)

        for item in data.get("itemList", []):
            yield item

        if not data.get("hasMore"):
            break

        cursor = data.get("cursor")


# ---------------- Logic ----------------
def _passes_filters(item: Dict[str, Any], cutoff_ts: int, f: Filters) -> bool:
    if item.get("createTime", 0) < cutoff_ts:
        return False

    stats = item.get("stats", {})
    if stats.get("playCount", 0) < f.min_views:
        return False
    if stats.get("diggCount", 0) < f.min_likes:
        return False
    if stats.get("commentCount", 0) < f.min_comments:
        return False

    return True


def normalize(item: Dict[str, Any], hashtag: str) -> MediaRow:
    author = item.get("author", {}) or {}
    stats = item.get("stats", {}) or {}
    author_stats = item.get("authorStats", {}) or {}

    username = author.get("uniqueId")
    video_id = item.get("id")

    return MediaRow(
        hashtag=hashtag,
        post_id=video_id,
        video_url=(
            f"https://www.tiktok.com/@{username}/video/{video_id}"
            if username and video_id
            else None
        ),
        play_count=int(stats.get("playCount", 0)),
        like_count=int(stats.get("diggCount", 0)),
        comment_count=int(stats.get("commentCount", 0)),
        create_time=int(item.get("createTime", 0)),
        username=username,
        follower_count=int(author_stats.get("followerCount", 0)),
        profile_url=f"https://www.tiktok.com/@{username}" if username else None,
        region=(item.get("poi") or {}).get("name"),
    )


def fetch_hashtag_medias(
    client: LamatokClient,
    hashtag: str,
    hashtag_id: int,
    limit: int,
    filters: Filters,
) -> Tuple[List[MediaRow], int, int]:

    cutoff_ts = int(time.time()) - filters.last_days * 86400

    results: List[MediaRow] = []
    fetched = 0
    collected = 0

    for item in iter_hashtag_medias(client, hashtag_id):
        fetched += 1
        collected += 1

        if not _passes_filters(item, cutoff_ts, filters):
            continue

        results.append(normalize(item, hashtag))
        if len(results) >= limit:
            break

    return results, fetched, collected