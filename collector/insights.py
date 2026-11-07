import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from collector.quality import analysis_rows


def clean_json(value):
    if isinstance(value, dict): return {k:clean_json(v) for k,v in value.items()}
    if isinstance(value, list): return [clean_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value): return None
    return value

VIRALITY_BUCKETS = [-1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0, float("inf")]
VIRALITY_LABELS = ["≤0.2", "0.2–0.5", "0.5–1", "1–2", "2–3", "3–5", ">5"]

VIEW_BUCKETS = [0, 1000, 10000, 100000, 1000000, 10000000, float("inf")]
VIEW_LABELS = ["<1K", "1–10K", "10–100K", "100K–1M", "1–10M", ">10M"]

DURATION_BUCKETS = [0, 180, 300, 600, 1200, 1800, float("inf")]
DURATION_LABELS = ["0–3 min (incl.)", "3–5 min", "5–10 min", "10–20 min", "20–30 min", ">30 min"]

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_BAND_LABELS = {
    "(100000, 500000)": "100K–500K",
    "(500000, 2000000)": "500K–2M",
    "(2000000, 10000000)": "2M–10M",
}


def _band_label(band):
    return _BAND_LABELS.get(str(band).strip(), str(band))


def _histogram(series, bins, labels):
    counts = pd.cut(series, bins=bins, labels=labels, include_lowest=True).value_counts().to_dict()
    return [{"bucket": lab, "count": int(counts.get(lab, 0))} for lab in labels]


def compute_insights(videos_csv, channels_csv, out_path):
    vids = pd.read_csv(videos_csv)
    chans = pd.read_csv(channels_csv)

    for col in ["is_flop", "is_viral", "has_number", "has_question"]:
        if col in vids:
            vids[col] = vids[col].astype(str).str.lower().isin(["true", "1"])

    chans["band_label"] = chans["band"].apply(_band_label)
    merge = vids.merge(chans[["channel_id", "niche", "band_label"]], on="channel_id", how="left")

    total = len(merge)
    flops = int(merge["is_flop"].sum())
    virals = int(merge["is_viral"].sum())
    unknown = int(merge["virality_score"].isna().sum())
    neutral = total - flops - virals - unknown

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    published = pd.to_datetime(merge["published_at"], utc=True, errors="coerce")
    eligible = len(analysis_rows(merge)) if "analysis_eligible" in merge else int((published < cutoff).sum())

    def _agg(group):
        return {
            "videos": int(len(group)),
            "flops": int(group["is_flop"].sum()),
            "virals": int(group["is_viral"].sum()),
            "median_virality": round(float(group["virality_score"].median()), 3) if len(group) else None,
            "avg_views": round(float(group["view_count"].mean()), 1) if len(group) else None,
        }

    by_niche = [{"niche": k, **_agg(g)} for k, g in merge.groupby("niche", sort=False)]
    by_band = [{"band": k, **_agg(g)} for k, g in merge.groupby("band_label", sort=False)]

    scores = merge["virality_score"].dropna()
    views = merge["view_count"].dropna()
    durations = merge["duration_sec"].dropna()

    hour_counts = merge["publish_hour"].value_counts().to_dict()
    day_counts = merge["publish_dayofweek"].value_counts().to_dict()

    insights = {
        "totals": {
            "videos": total,
            "eligible": eligible,
            "flops": flops,
            "virals": virals,
            "neutral": neutral,
            "unknown": unknown,
            "median_virality": round(float(scores.median()), 3) if len(scores) else None,
        },
        "by_niche": by_niche,
        "by_band": by_band,
        "virality_histogram": _histogram(scores, VIRALITY_BUCKETS, VIRALITY_LABELS),
        "view_histogram": _histogram(views, VIEW_BUCKETS, VIEW_LABELS),
        "publish_hour": [{"hour": h, "count": int(hour_counts.get(h, 0))} for h in range(24)],
        "publish_day": [{"day": DAY_NAMES[d], "count": int(day_counts.get(d, 0))} for d in range(7)],
        "duration_buckets": _histogram(durations, DURATION_BUCKETS, DURATION_LABELS),
        "title_features": {
            "avg_title_length": round(float(merge["title_length"].mean()), 1),
            "pct_has_number": round(float(merge["has_number"].mean() * 100), 1),
            "pct_has_question": round(float(merge["has_question"].mean() * 100), 1),
            "avg_caps_ratio": round(float(merge["caps_ratio"].mean()), 3),
        },
    }

    insights = clean_json(insights)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(insights, indent=2, default=str), encoding="utf-8")
    return insights


def _pct(counts):
    total = sum(counts)
    return [round(c / total * 100, 1) if total else 0 for c in counts]


def _count_hours(series):
    c = series.value_counts().to_dict()
    return [int(c.get(h, 0)) for h in range(24)]


def _count_days(series):
    c = series.value_counts().to_dict()
    return [int(c.get(d, 0)) for d in range(7)]


def _count_hist(series, bins, labels):
    counts = pd.cut(series.dropna(), bins=bins, labels=labels, include_lowest=True).value_counts().to_dict()
    return [int(counts.get(lab, 0)) for lab in labels]


def compute_comparison(videos_csv, channels_csv, out_path):
    """Flop vs. viral distributions (normalized to % of each class)."""
    vids = pd.read_csv(videos_csv)
    for col in ["is_flop", "is_viral", "has_number", "has_question"]:
        if col in vids:
            vids[col] = vids[col].astype(str).str.lower().isin(["true", "1"])

    vids = analysis_rows(vids)
    flop = vids[vids["is_flop"]]
    viral = vids[vids["is_viral"]]

    title_bins = [0, 20, 40, 60, 80, 100, float("inf")]
    title_labels = ["0–20 (incl.)", "20–40", "40–60", "60–80", "80–100", ">100"]

    comparison = {
        "scope": "Qualified English metadata, age >=90d, valid baseline; UTC. Observational pooled distributions, not causal effects." if "analysis_eligible" in vids else "Legacy unfiltered input",
        "sample_videos": int(len(vids)),
        "sample_channels": int(vids["channel_id"].nunique()),
        "totals": {"flops": int(len(flop)), "virals": int(len(viral))},
        "publish_hour": {
            "labels": [str(h) for h in range(24)],
            "flop": _pct(_count_hours(flop["publish_hour"])),
            "viral": _pct(_count_hours(viral["publish_hour"])),
        },
        "publish_day": {
            "labels": DAY_NAMES,
            "flop": _pct(_count_days(flop["publish_dayofweek"])),
            "viral": _pct(_count_days(viral["publish_dayofweek"])),
        },
        "duration_buckets": {
            "labels": DURATION_LABELS,
            "flop": _pct(_count_hist(flop["duration_sec"], DURATION_BUCKETS, DURATION_LABELS)),
            "viral": _pct(_count_hist(viral["duration_sec"], DURATION_BUCKETS, DURATION_LABELS)),
        },
        "title_length_buckets": {
            "labels": title_labels,
            "flop": _pct(_count_hist(flop["title_length"], title_bins, title_labels)),
            "viral": _pct(_count_hist(viral["title_length"], title_bins, title_labels)),
        },
        "title_flags": {
            "labels": ["has number", "has question"],
            "flop": [round(float(flop["has_number"].mean() * 100), 1),
                     round(float(flop["has_question"].mean() * 100), 1)],
            "viral": [round(float(viral["has_number"].mean() * 100), 1),
                      round(float(viral["has_question"].mean() * 100), 1)],
        },
    }

    comparison = clean_json(comparison)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")
    return comparison
