from statistics import median
import ast

import pandas as pd


def rolling_median_views(df: pd.DataFrame, window_days: int = 90, min_prior: int = 5) -> pd.Series:
    """Lookahead-free prior-90d median views per channel.

    For each video, median of the channel's videos published strictly before it
    and within `window_days`. Returns NaN when fewer than `min_prior` such
    videos exist. Aligned to the input index.
    """
    orig_index = df.index
    work = df[["channel_id", "published_at", "view_count"]].copy()
    work = work.sort_values(["channel_id", "published_at"])

    result = {}
    window = pd.Timedelta(days=window_days)

    for _, group in work.groupby("channel_id", sort=False):
        idxs = list(group.index)
        times = group["published_at"].to_numpy()
        views = group["view_count"].to_numpy()
        for pos, g_idx in enumerate(idxs):
            t = times[pos]
            prior = []
            j = pos - 1
            while j >= 0:
                if (t - times[j]) > window:
                    break
                if times[j] >= t:
                    j -= 1
                    continue
                v = views[j]
                if not pd.isna(v):
                    prior.append(v)
                j -= 1
            result[g_idx] = median(prior) if len(prior) >= min_prior else float("nan")

    return pd.Series({idx: result.get(idx, float("nan")) for idx in orig_index})


def _caps_ratio(title: str) -> float:
    letters = [c for c in title if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)


def add_features(df: pd.DataFrame, window_days: int = 90, min_prior: int = 5) -> pd.DataFrame:
    """Derive the virality score plus title/timing features on top of raw video rows."""
    out = df.copy()

    out["prior_90d_median_views"] = rolling_median_views(df, window_days, min_prior)
    baseline = out["prior_90d_median_views"].where(out["prior_90d_median_views"] > 0)
    out["virality_score"] = (out["view_count"] / baseline).replace([float("inf"), -float("inf")], float("nan"))

    flop = out["virality_score"] <= 0.2
    viral = out["virality_score"] >= 3
    out["is_flop"] = flop.fillna(False).astype(bool)
    out["is_viral"] = viral.fillna(False).astype(bool)

    title = out["title"].fillna("")
    out["title_length"] = title.str.len()
    out["has_number"] = title.str.contains(r"\d", regex=True)
    out["has_question"] = title.str.contains("?", regex=False)
    out["caps_ratio"] = title.apply(_caps_ratio)
    out["tag_count"] = out["tags"].apply(tag_count)

    out["publish_hour"] = out["published_at"].dt.hour
    out["publish_dayofweek"] = out["published_at"].dt.dayofweek

    sorted_idx = out.sort_values(["channel_id", "published_at"]).index
    ts = out.loc[sorted_idx].groupby("channel_id", sort=False)["published_at"].diff()
    out["time_since_last_upload"] = ts.reindex(out.index)

    return out


def tag_count(value):
    """Handle both API lists and CSV-serialized lists without counting characters."""
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return 0
    return len(value) if isinstance(value, (list, tuple)) else 0
