from unittest.mock import patch

import pytest

from collector.youtube import YouTubeClient, YouTubeError


def _resp(payload, status=200):
    r = type("FakeResponse", (), {})()
    r.status_code = status
    r.json = lambda: payload
    return r


def test_get_video_parses_all_parts():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value = _resp({"items": [{
            "id": "v1",
            "snippet": {"title": "T", "publishedAt": "2026-01-01T00:00:00Z",
                        "tags": ["a"], "categoryId": "28",
                        "defaultAudioLanguage": "en"},
            "contentDetails": {"duration": "PT3M30S"},
            "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "2"}}]})
        v = client.get_video("v1")
    assert v["duration_sec"] == 210
    assert v["view_count"] == 100 and v["tags"] == ["a"]
    assert v["category_id"] == "28"
    assert v["default_audio_language"] == "en"


def test_get_video_missing_stats_returns_none():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value = _resp({"items": [{
            "id": "v1",
            "snippet": {"title": "T", "publishedAt": "2026-01-01T00:00:00Z"},
            "contentDetails": {"duration": "PT1M"}}]})  # no statistics key
        v = client.get_video("v1")
    assert v["like_count"] is None and v["view_count"] is None
    assert v["default_audio_language"] is None


def test_get_video_non_200_raises_youtube_error():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value = _resp({"error": {"message": "quota"}}, status=403)
        with pytest.raises(YouTubeError):
            client.get_video("v1")


def test_get_channel_parses_subscriber_count():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value = _resp({"items": [{
            "id": "c1",
            "snippet": {"title": "Chan"},
            "statistics": {"subscriberCount": "123456", "videoCount": "789"}}]})
        c = client.get_channel("c1")
    assert c == {"channel_id": "c1", "title": "Chan",
                 "subscriber_count": 123456, "video_count": 789}


def test_search_channels_returns_ids_and_titles():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value = _resp({"items": [
            {"id": {"channelId": "c1"}, "snippet": {"title": "A"}},
            {"id": {"channelId": "c2"}, "snippet": {"title": "B"}}]})
        chans = client.search_channels("gadget")
    assert chans == [{"channel_id": "c1", "title": "A"},
                     {"channel_id": "c2", "title": "B"}]


def test_list_uploads_paginates_newest_first():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.side_effect = [
            _resp({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}),
            _resp({"items": [
                {"contentDetails": {"videoId": "v1"},
                 "snippet": {"publishedAt": "2026-01-02T00:00:00Z"}},
                {"contentDetails": {"videoId": "v2"},
                 "snippet": {"publishedAt": "2026-01-01T00:00:00Z"}}],
                "nextPageToken": "t2"}),
            _resp({"items": [
                {"contentDetails": {"videoId": "v3"},
                 "snippet": {"publishedAt": "2025-12-31T00:00:00Z"}}]}),
        ]
        uploads = client.list_uploads("c1")
    assert uploads == [
        {"video_id": "v1", "published_at": "2026-01-02T00:00:00Z"},
        {"video_id": "v2", "published_at": "2026-01-01T00:00:00Z"},
        {"video_id": "v3", "published_at": "2025-12-31T00:00:00Z"},
    ]


def test_list_uploads_respects_limit():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.side_effect = [
            _resp({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}),
            _resp({"items": [
                {"contentDetails": {"videoId": "v1"},
                 "snippet": {"publishedAt": "2026-01-01T00:00:00Z"}},
                {"contentDetails": {"videoId": "v2"},
                 "snippet": {"publishedAt": "2026-01-01T00:00:00Z"}},
            ], "nextPageToken": "t2"}),
        ]
        uploads = client.list_uploads("c1", limit=1)
    assert uploads == [{"video_id": "v1", "published_at": "2026-01-01T00:00:00Z"}]
