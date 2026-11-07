from datetime import datetime

from collector.scheduler import is_due, load_schedule, load_sync, parse_datetime, write_schedule, write_sync


def test_parse_datetime():
    dt = parse_datetime("2026-10-15", "04:30")
    assert dt.year == 2026 and dt.month == 10 and dt.day == 15
    assert dt.hour == 4 and dt.minute == 30
    assert dt.tzinfo is None  # local time, not UTC


def test_schedule_roundtrip(tmp_path):
    p = tmp_path / "schedule.json"
    write_schedule(p, {"run_at": "2026-10-15T04:30:00", "max_videos": 500})
    assert load_schedule(p)["max_videos"] == 500


def test_load_schedule_missing(tmp_path):
    assert load_schedule(tmp_path / "nope.json") is None


def test_is_due_naive():
    now = datetime.fromisoformat("2026-10-15T05:00:00")
    assert is_due({"run_at": "2026-10-15T04:30:00"}, now) is True
    assert is_due({"run_at": "2026-10-15T06:00:00"}, now) is False


def test_is_due_aware():
    now = datetime.fromisoformat("2026-10-15T05:00:00+00:00")
    assert is_due({"run_at": "2026-10-15T04:30:00+00:00"}, now) is True
    assert is_due({"run_at": "2026-10-15T06:00:00+00:00"}, now) is False


def test_sync_defaults_enabled(tmp_path):
    assert load_sync(tmp_path / "sync.json") is True


def test_sync_roundtrip(tmp_path):
    p = tmp_path / "sync.json"
    write_sync(p, False)
    assert load_sync(p) is False
    write_sync(p, True)
    assert load_sync(p) is True
