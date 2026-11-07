"""Explicit language and snapshot rules shared by collection and offline demos."""
import pandas as pd


def language_status(value):
    if value is None or pd.isna(value) or not str(value).strip():
        return "unknown"
    code = str(value).strip().lower().replace("_", "-")
    return "english" if code == "en" or code.startswith("en-") else "other"


def annotate_quality(df, as_of):
    out = df.copy()
    stamp = pd.Timestamp(as_of)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    published = pd.to_datetime(out["published_at"], utc=True, errors="coerce")
    out["language_status"] = out["default_audio_language"].map(language_status)
    out["age_eligible"] = published.le(stamp - pd.Timedelta(days=90))
    out["score_valid"] = (out["prior_90d_median_views"].gt(0) &
                          out["virality_score"].notna() & out["view_count"].ge(0))
    out["analysis_eligible"] = out["age_eligible"] & out["score_valid"] & out["language_status"].eq("english")
    out["analysis_as_of"] = stamp.isoformat()
    reasons = []
    for _, row in out.iterrows():
        flags = []
        if row["language_status"] != "english": flags.append("language_" + row["language_status"])
        if not row["age_eligible"]: flags.append("age_under_90d_or_invalid_date")
        if not row["score_valid"]: flags.append("invalid_baseline_or_score")
        reasons.append(";".join(flags) or "included")
    out["exclusion_reason"] = reasons
    return out


def analysis_rows(df):
    if "analysis_eligible" not in df:
        return df  # Legacy inputs remain usable; offline demo always annotates them.
    return df[df["analysis_eligible"].astype(str).str.lower().isin(["true", "1"])].copy()
