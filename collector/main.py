import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collector.collector import collect_channel
from collector.config import Config, load_api_key, load_config
from collector.derive import add_features
from collector.quality import language_status, annotate_quality
from collector.insights import compute_comparison, compute_insights
from collector.progress import record_channel_status, record_run, write_live_progress, write_progress_json
from collector.sampler import save_channels, select_channels
from collector.scheduler import load_sync
from collector.youtube import YouTubeClient

DATA_DIR = Path("data")

RAW_COLUMNS = [
    "video_id", "channel_id", "title", "published_at", "view_count",
    "like_count", "comment_count", "duration_sec", "tags", "category_id",
    "default_audio_language", "channel_subs",
]

VIDEO_COLUMNS = RAW_COLUMNS + [
    "prior_90d_median_views", "virality_score", "is_flop", "is_viral",
    "title_length", "has_number", "has_question", "caps_ratio", "tag_count",
    "publish_hour", "publish_dayofweek", "time_since_last_upload",
]


def _read_channels(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["subscriber_count"] = int(r["subscriber_count"])
    return rows


def run_daily(cfg: Config, client: YouTubeClient, max_videos: int | None = None,
              reselect: bool = False, per_cell: int | None = None) -> int:
    data_dir = DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    if not load_sync(data_dir / "sync.json"):
        print("sync disabled — skipping run")
        return 0
    raw_dir = data_dir / "raw"
    if per_cell:
        cfg.per_cell = per_cell

    channels_csv = data_dir / "channels.csv"
    if reselect and channels_csv.exists():
        channels_csv.unlink()
    if not channels_csv.exists():
        channels = select_channels(client, cfg)
        save_channels(channels, channels_csv)
    channels = _read_channels(channels_csv)

    videos_csv = data_dir / "videos.csv"
    existing_df = pd.read_csv(videos_csv) if videos_csv.exists() else pd.DataFrame()
    existing_ids = set(existing_df["video_id"]) if len(existing_df) else set()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at = datetime.now(timezone.utc).isoformat()

    runs_csv = data_dir / "runs.csv"
    progress_path = data_dir / "progress.json"

    def _live_run(status_rows):
        statuses = [r["status"] for r in status_rows]
        return {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": "",
            "status": "running",
            "channels_attempted": len(channels),
            "channels_success": statuses.count("success"),
            "channels_failed": statuses.count("failed"),
            "channels_skipped": statuses.count("skipped"),
            "videos_new": len(new_videos),
            "videos_total": len(existing_df),
            "quota_used": "",
        }

    channel_status_rows = []
    new_videos = []
    write_live_progress(runs_csv, channels, [], _live_run([]), videos_csv, progress_path)
    for ch in channels:
        res = collect_channel(client, ch, existing_ids, raw_dir / ch["channel_id"],
                              max_videos=max_videos or cfg.max_videos)
        channel_status_rows.append({
            "run_id": run_id,
            "channel_id": ch["channel_id"],
            "title": ch["title"],
            "niche": ch["niche"],
            "subs": ch["subscriber_count"],
            "status": res.status,
            "error_message": res.error or "",
            "duration_sec": round(res.duration_sec, 3),
        })
        if res.status == "success":
            for v in res.new_videos:
                v["channel_id"] = ch["channel_id"]
                v["channel_subs"] = ch["subscriber_count"]
                new_videos.append(v)
        write_live_progress(runs_csv, channels, channel_status_rows, _live_run(channel_status_rows),
                            videos_csv, progress_path)

    # English-only filter: keep videos with no language tag or English audio.
    # Unknown-language records remain stored for review, but not analysis-eligible.
    new_videos = [v for v in new_videos if language_status(v.get("default_audio_language")) != "other"]

    if new_videos:
        new_raw = pd.DataFrame(new_videos)[RAW_COLUMNS]
        new_raw["published_at"] = pd.to_datetime(new_raw["published_at"])
        if len(existing_df):
            existing_raw = existing_df[RAW_COLUMNS].copy()
            existing_raw["published_at"] = pd.to_datetime(existing_raw["published_at"])
        else:
            existing_raw = pd.DataFrame(columns=RAW_COLUMNS)
        combined = pd.concat([existing_raw, new_raw], ignore_index=True)
        combined = combined.drop_duplicates("video_id", keep="last").reset_index(drop=True)
        combined["published_at"] = pd.to_datetime(combined["published_at"], utc=True)
        featured = add_features(combined, cfg.window_days, cfg.min_prior)
        final = annotate_quality(featured, started_at)
    else:
        final = existing_df

    if len(final.columns) == 0:
        final = pd.DataFrame(columns=VIDEO_COLUMNS)
    final.to_csv(videos_csv, index=False)

    statuses = [r["status"] for r in channel_status_rows]
    run = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if statuses.count("failed") else "success",
        "channels_attempted": len(channels),
        "channels_success": statuses.count("success"),
        "channels_failed": statuses.count("failed"),
        "channels_skipped": statuses.count("skipped"),
        "videos_new": len(new_videos),
        "videos_total": len(final),
        "quota_used": 2 * len(channels) + len(new_videos),
    }
    record_run(data_dir / "runs.csv", run)
    record_channel_status(data_dir / "channel_status.csv", channel_status_rows)
    write_progress_json(data_dir / "runs.csv", data_dir / "channel_status.csv",
                        videos_csv, data_dir / "progress.json")
    compute_insights(videos_csv, channels_csv, data_dir / "insights.json")
    compute_comparison(videos_csv, channels_csv, data_dir / "comparison.json")

    print(f"run {run_id}: attempted={run['channels_attempted']} "
          f"success={run['channels_success']} failed={run['channels_failed']} "
          f"skipped={run['channels_skipped']} videos_new={run['videos_new']} "
          f"videos_total={run['videos_total']}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--select-only", action="store_true",
                        help="only (re)select channels and write channels.csv")
    parser.add_argument("--max-videos", type=int, default=None,
                        help="cap uploads collected per channel (overrides config)")
    parser.add_argument("--reselect", action="store_true",
                        help="re-discover channels before collecting")
    parser.add_argument("--per-cell", type=int, default=None,
                        help="channels per niche×band cell (used with --reselect)")
    args = parser.parse_args()

    cfg = load_config("config.yaml")
    client = YouTubeClient(load_api_key(".env"))

    if args.select_only:
        channels = select_channels(client, cfg)
        save_channels(channels, DATA_DIR / "channels.csv")
        print(f"selected {len(channels)} channels")
        return 0

    sys.exit(run_daily(cfg, client, max_videos=args.max_videos,
                       reselect=args.reselect, per_cell=args.per_cell))


if __name__ == "__main__":
    main()
