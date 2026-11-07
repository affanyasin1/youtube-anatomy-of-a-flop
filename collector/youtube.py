import re

import requests


BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _parse_duration(iso):
    """Convert an ISO-8601 duration like 'PT3M30S' to seconds."""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, minutes, seconds = (int(x or 0) for x in m.groups())
    return h * 3600 + minutes * 60 + seconds


class YouTubeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params)
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
            raise YouTubeError(msg, r.status_code)
        return r.json()

    def search_channels(self, keyword: str, max_results: int = 50) -> list[dict]:
        data = self._get("search", {
            "part": "snippet",
            "type": "channel",
            "q": keyword,
            "maxResults": max_results,
        })
        return [
            {"channel_id": item["id"]["channelId"], "title": item["snippet"]["title"]}
            for item in data.get("items", [])
        ]

    def get_channel(self, channel_id: str) -> dict:
        data = self._get("channels", {"part": "snippet,statistics", "id": channel_id})
        items = data.get("items", [])
        if not items:
            raise YouTubeError(f"channel not found: {channel_id}", 200)
        item = items[0]
        stats = item.get("statistics", {})
        return {
            "channel_id": item["id"],
            "title": item["snippet"]["title"],
            "subscriber_count": int(stats.get("subscriberCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }

    def list_uploads(self, channel_id: str, limit: int | None = None) -> list[dict]:
        data = self._get("channels", {"part": "contentDetails", "id": channel_id})
        items = data.get("items", [])
        if not items:
            raise YouTubeError(f"channel not found: {channel_id}", 200)
        uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        result = []
        page_token = None
        while True:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": uploads_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            data = self._get("playlistItems", params)
            for item in data.get("items", []):
                result.append({
                    "video_id": item["contentDetails"]["videoId"],
                    "published_at": item["snippet"]["publishedAt"],
                })
                if limit is not None and len(result) >= limit:
                    return result
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return result

    def get_video(self, video_id: str) -> dict:
        data = self._get("videos", {
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
        })
        items = data.get("items", [])
        if not items:
            raise YouTubeError(f"video not found: {video_id}", 200)
        item = items[0]
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats = item.get("statistics", {})
        return {
            "video_id": item["id"],
            "title": snippet.get("title"),
            "published_at": snippet.get("publishedAt"),
            "duration_sec": _parse_duration(content.get("duration", "")),
            "view_count": int(stats["viewCount"]) if "viewCount" in stats else None,
            "like_count": int(stats["likeCount"]) if "likeCount" in stats else None,
            "comment_count": int(stats["commentCount"]) if "commentCount" in stats else None,
            "tags": snippet.get("tags"),
            "category_id": snippet.get("categoryId"),
            "default_audio_language": snippet.get("defaultAudioLanguage"),
        }
