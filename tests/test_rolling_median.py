import pandas as pd

from collector.derive import rolling_median_views


def test_rolling_median_excludes_self_and_future():
    df = pd.DataFrame({
        "channel_id": ["c"] * 4,
        "published_at": pd.to_datetime(["2026-01-01", "2026-01-15", "2026-02-01", "2026-02-15"]),
        "view_count": [100, 200, 100000, 300],
    })
    r = rolling_median_views(df, window_days=90, min_prior=1)
    # viral video (index 2, 100000 views) must not inflate its own or prior baselines
    assert r.iloc[1] == 100.0          # median of [100]
    assert r.iloc[2] == 150.0          # median of [100, 200] — NOT influenced by 100000
    assert r.iloc[3] == 200.0          # median of [100, 200, 100000] sorted -> 200


def test_rolling_median_cold_start_returns_nan():
    df = pd.DataFrame({
        "channel_id": ["c"] * 3,
        "published_at": pd.to_datetime(["2026-01-01", "2026-01-10", "2026-01-20"]),
        "view_count": [10, 20, 30],
    })
    r = rolling_median_views(df, window_days=90, min_prior=5)
    assert r.isna().all()
