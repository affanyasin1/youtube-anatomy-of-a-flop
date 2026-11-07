import pandas as pd

from collector.derive import add_features


def test_add_features_basic_columns():
    df = pd.DataFrame({
        "channel_id": ["c"] * 2,
        "published_at": pd.to_datetime(["2026-01-01", "2026-01-15"]),
        "view_count": [100, 200],
        "title": ["How to bake a cake", "10 Tricks!"],
        "tags": [["a", "b"], None],
        "duration_sec": [210, 60],
        "channel_subs": [500000, 500000],
    })
    out = add_features(df, min_prior=1)
    assert out.loc[1, "virality_score"] == 2.0      # 200 / 100
    assert out.loc[0, "has_number"] == False
    assert out.loc[1, "has_number"] == True
    assert out.loc[1, "tag_count"] == 0             # None tags -> 0, not crash
    assert out.loc[1, "time_since_last_upload"].days == 14


def test_add_features_flags():
    df = pd.DataFrame({
        "channel_id": ["c"] * 3,
        "published_at": pd.to_datetime(["2026-01-01", "2026-01-15", "2026-02-01"]),
        "view_count": [100, 20, 300],
        "title": ["a", "b", "c"],
        "tags": [[], [], []],
        "duration_sec": [10, 10, 10],
        "channel_subs": [100000, 100000, 100000],
    })
    out = add_features(df, min_prior=1)
    assert bool(out.loc[1, "is_flop"])       # 20 / 100 = 0.2
    assert bool(out.loc[2, "is_viral"])      # 300 / median([100, 20]) = 5
    assert not bool(out.loc[0, "is_flop"]) and not bool(out.loc[0, "is_viral"])
