import csv
import json
from datetime import datetime, timedelta, timezone

from collector.progress import record_channel_status, record_run, write_live_progress, write_progress_json


def test_record_run_appends(tmp_path):
    p = tmp_path / "runs.csv"
    record_run(p, {"run_id": "r1", "channels_attempted": 2, "channels_success": 1,
                   "channels_failed": 1, "channels_skipped": 0, "videos_new": 5})
    with open(p) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["run_id"] == "r1" and rows[0]["channels_success"] == "1"


def test_record_channel_status_appends(tmp_path):
    p = tmp_path / "channel_status.csv"
    record_channel_status(p, [
        {"run_id": "r1", "channel_id": "c1", "title": "A", "niche": "tech",
         "subs": 200000, "status": "success", "error_message": "", "duration_sec": 1.0},
    ])
    record_channel_status(p, [
        {"run_id": "r2", "channel_id": "c1", "title": "A", "niche": "tech",
         "subs": 210000, "status": "success", "error_message": "", "duration_sec": 1.0},
    ])
    with open(p) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2 and rows[1]["run_id"] == "r2"


def test_write_progress_json_aggregates(tmp_path):
    runs = tmp_path / "runs.csv"
    record_run(runs, {"run_id": "r1", "channels_attempted": 2, "channels_success": 1,
                      "channels_failed": 1, "channels_skipped": 0, "videos_new": 5,
                      "videos_total": 5, "quota_used": 10})
    record_run(runs, {"run_id": "r2", "channels_attempted": 2, "channels_success": 2,
                      "channels_failed": 0, "channels_skipped": 0, "videos_new": 3,
                      "videos_total": 8, "quota_used": 6})

    status = tmp_path / "channel_status.csv"
    record_channel_status(status, [
        {"run_id": "r1", "channel_id": "c1", "title": "A", "niche": "tech",
         "subs": 200000, "status": "success", "error_message": "", "duration_sec": 1.0},
        {"run_id": "r2", "channel_id": "c1", "title": "A", "niche": "tech",
         "subs": 210000, "status": "success", "error_message": "", "duration_sec": 1.0},
        {"run_id": "r2", "channel_id": "c2", "title": "B", "niche": "cooking",
         "subs": 300000, "status": "failed", "error_message": "quota", "duration_sec": 2.0},
    ])

    videos = tmp_path / "videos.csv"
    videos.write_text("video_id,channel_id\nv1,c1\nv2,c1\nv3,c2\n")

    out = tmp_path / "progress.json"
    write_progress_json(runs, status, videos, out)

    data = json.loads(out.read_text())
    assert data["latest_run"]["run_id"] == "r2"
    assert len(data["run_history"]) == 2
    assert len(data["channels"]) == 2

    c1 = next(c for c in data["channels"] if c["channel_id"] == "c1")
    assert c1["status"] == "success" and c1["videos_count"] == 2
    assert str(c1["subs"]) == "210000"

    c2 = next(c for c in data["channels"] if c["channel_id"] == "c2")
    assert c2["status"] == "failed" and c2["error_message"] == "quota"
    assert c2["videos_count"] == 1


def test_write_progress_json_counts_eligible(tmp_path):
    runs = tmp_path / "runs.csv"
    record_run(runs, {"run_id": "r1", "channels_attempted": 1, "channels_success": 1,
                      "channels_failed": 0, "channels_skipped": 0, "videos_new": 2,
                      "videos_total": 2, "quota_used": 0})
    status = tmp_path / "channel_status.csv"
    record_channel_status(status, [{
        "run_id": "r1", "channel_id": "c1", "title": "A", "niche": "tech",
        "subs": 200000, "status": "success", "error_message": "", "duration_sec": 1.0,
    }])
    videos = tmp_path / "videos.csv"
    old = "2000-01-01T00:00:00Z"                                   # >= 90 days old -> eligible
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()  # < 90 days
    videos.write_text(f"video_id,channel_id,published_at\nv1,c1,{old}\nv2,c1,{recent}\n")

    out = tmp_path / "progress.json"
    write_progress_json(runs, status, videos, out)
    data = json.loads(out.read_text())
    assert data["channels"][0]["eligible_count"] == 1


def test_write_live_progress_lists_all_channels(tmp_path):
    runs = tmp_path / "runs.csv"
    videos = tmp_path / "videos.csv"
    videos.write_text("video_id,channel_id,published_at\nv1,c1,2025-01-01T00:00:00Z\n")

    channels = [
        {"channel_id": "c1", "title": "A", "niche": "tech", "subscriber_count": 200000},
        {"channel_id": "c2", "title": "B", "niche": "cooking", "subscriber_count": 300000},
    ]
    status_rows = [{"run_id": "r1", "channel_id": "c1", "title": "A", "niche": "tech",
                    "subs": 200000, "status": "success", "error_message": "", "duration_sec": 1.0}]
    run = {"run_id": "r1", "status": "running", "channels_attempted": 2}

    out = tmp_path / "progress.json"
    write_live_progress(runs, channels, status_rows, run, videos, out)

    data = json.loads(out.read_text())
    assert data["latest_run"]["status"] == "running"
    assert len(data["channels"]) == 2
    assert data["channels"][0]["status"] == "success"
    assert data["channels"][1]["status"] == "pending"
