import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUN_COLUMNS = [
    "run_id", "started_at", "finished_at", "status",
    "channels_attempted", "channels_success", "channels_failed",
    "channels_skipped", "videos_new", "videos_total", "quota_used",
]

CHANNEL_COLUMNS = [
    "run_id", "channel_id", "title", "niche", "subs",
    "status", "error_message", "duration_sec",
]


def _append_csv(path, fieldnames, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def record_run(runs_csv, run):
    _append_csv(runs_csv, RUN_COLUMNS, [run])


def record_channel_status(path, rows):
    _append_csv(path, CHANNEL_COLUMNS, rows)


def _read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _video_counts(videos_csv):
    video_counts = {}
    eligible_counts = {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    for v in _read_csv(videos_csv):
        cid = v.get("channel_id")
        if not cid:
            continue
        video_counts[cid] = video_counts.get(cid, 0) + 1
        ts = v.get("published_at")
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                qualified = str(v["analysis_eligible"]).lower() in ("true", "1") if "analysis_eligible" in v else dt < cutoff
                if qualified:
                    eligible_counts[cid] = eligible_counts.get(cid, 0) + 1
            except ValueError:
                pass
    return video_counts, eligible_counts


def _write_json(out, obj):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def write_progress_json(runs_csv, channel_status_csv, videos_csv, out):
    runs = _read_csv(runs_csv)
    status = _read_csv(channel_status_csv)
    video_counts, eligible_counts = _video_counts(videos_csv)

    latest_run = runs[-1] if runs else {}

    latest_status = {}
    for row in status:
        cid = row.get("channel_id")
        if cid:
            latest_status[cid] = row

    channels = []
    for cid, row in latest_status.items():
        rec = dict(row)
        rec["videos_count"] = video_counts.get(cid, 0)
        rec["eligible_count"] = eligible_counts.get(cid, 0)
        channels.append(rec)

    _write_json(out, {"latest_run": latest_run, "run_history": runs, "channels": channels})


def write_live_progress(runs_csv, channels, status_rows, run, videos_csv, out):
    """Write progress.json mid-run: every channel listed, pending unless processed."""
    video_counts, eligible_counts = _video_counts(videos_csv)
    status_by_id = {r.get("channel_id"): r for r in status_rows}
    chan_list = []
    for ch in channels:
        cid = ch["channel_id"]
        rec = dict(status_by_id.get(cid, {
            "channel_id": cid,
            "title": ch.get("title", ""),
            "niche": ch.get("niche", ""),
            "subs": ch.get("subscriber_count", ch.get("subs", "")),
            "status": "pending",
            "error_message": "",
            "duration_sec": "",
        }))
        rec["title"] = ch.get("title", rec.get("title", ""))
        rec["niche"] = ch.get("niche", rec.get("niche", ""))
        rec["subs"] = ch.get("subscriber_count", ch.get("subs", rec.get("subs", "")))
        rec["videos_count"] = video_counts.get(cid, 0)
        rec["eligible_count"] = eligible_counts.get(cid, 0)
        chan_list.append(rec)
    _write_json(out, {"latest_run": run, "run_history": _read_csv(runs_csv), "channels": chan_list})
