import json
from datetime import datetime
from pathlib import Path


def parse_datetime(date_str, time_str):
    """Combine a YYYY-MM-DD date and HH:MM time into a naive local datetime."""
    return datetime.fromisoformat(f"{date_str}T{time_str}:00")


def write_schedule(path, plan):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def load_schedule(path):
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_due(plan, now):
    """True when plan['run_at'] is at or before `now`. Handles aware or naive times."""
    run_at = datetime.fromisoformat(plan["run_at"])
    if run_at.tzinfo is not None:
        run_at = run_at.astimezone().replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    return run_at <= now


def load_sync(path, default=True):
    """Read the sync-enabled flag; defaults to True when the file is absent/invalid."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("enabled", default))
    except Exception:
        return default


def write_sync(path, enabled):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": bool(enabled)}), encoding="utf-8")
