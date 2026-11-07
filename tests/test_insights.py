import pandas as pd

from collector.insights import compute_comparison, compute_insights


def _make_videos(tmp_path):
    df = pd.DataFrame({
        "video_id": ["v1", "v2", "v3", "v4", "v5"],
        "channel_id": ["c1", "c1", "c1", "c2", "c2"],
        "published_at": ["2025-01-01T00:00:00Z"] * 5,
        "view_count": [100, 200, 10000, 500, 600],
        "duration_sec": [60, 120, 300, 400, 900],
        "is_flop": [True, False, False, True, False],
        "is_viral": [False, False, True, False, True],
        "virality_score": [0.1, 0.8, 3.5, 0.15, 4.0],
        "title_length": [10, 20, 30, 15, 25],
        "has_number": [True, False, True, False, True],
        "has_question": [False, True, False, False, True],
        "caps_ratio": [0.1, 0.2, 0.3, 0.15, 0.25],
        "publish_hour": [1, 2, 3, 1, 2],
        "publish_dayofweek": [0, 1, 2, 0, 1],
    })
    p = tmp_path / "videos.csv"
    df.to_csv(p, index=False)
    return p


def _make_channels(tmp_path):
    df = pd.DataFrame({
        "channel_id": ["c1", "c2"],
        "title": ["A", "B"],
        "niche": ["tech", "cooking"],
        "band": ["(100000, 500000)", "(500000, 2000000)"],
        "subscriber_count": [200000, 1000000],
    })
    p = tmp_path / "channels.csv"
    df.to_csv(p, index=False)
    return p


def test_compute_insights(tmp_path):
    data = compute_insights(_make_videos(tmp_path), _make_channels(tmp_path), tmp_path / "insights.json")

    assert (tmp_path / "insights.json").exists()
    assert data["totals"]["videos"] == 5
    assert data["totals"]["flops"] == 2
    assert data["totals"]["virals"] == 2
    assert len(data["by_niche"]) == 2
    assert data["by_niche"][0]["videos"] == 3
    assert len(data["publish_hour"]) == 24
    assert len(data["publish_day"]) == 7
    assert sum(b["count"] for b in data["virality_histogram"]) == 5
    assert data["title_features"]["pct_has_number"] == 60.0  # 3 of 5


def test_compute_comparison(tmp_path):
    data = compute_comparison(_make_videos(tmp_path), _make_channels(tmp_path), tmp_path / "comparison.json")

    assert (tmp_path / "comparison.json").exists()
    assert data["totals"]["flops"] == 2
    assert data["totals"]["virals"] == 2
    assert len(data["publish_hour"]["flop"]) == 24
    assert data["publish_hour"]["flop"][1] == 100.0   # both flops published at hour 1
    assert data["publish_day"]["flop"][0] == 100.0    # both flops on day 0 (Mon)
    assert data["title_flags"]["flop"][0] == 50.0     # 1 of 2 flops has a number
