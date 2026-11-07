import json
import subprocess
import sys
import threading
import time
import argparse
from urllib.parse import urlsplit, unquote
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from collector.config import load_config
from collector.scheduler import is_due, load_schedule, load_sync, parse_datetime, write_schedule, write_sync

ROOT = Path(__file__).resolve().parent
SCHEDULE = ROOT / "data" / "schedule.json"
SYNC = ROOT / "data" / "sync.json"
PORT = 8000
DISPLAY_DATA = ROOT / "data"
DEMO_MODE = False


def spawn_collector(max_videos=None, reselect=False, per_cell=None):
    cmd = [sys.executable, "-m", "collector.main"]
    if max_videos:
        cmd += ["--max-videos", str(max_videos)]
    if reselect:
        cmd += ["--reselect"]
    if per_cell:
        cmd += ["--per-cell", str(per_cell)]
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    log_path = ROOT / "data" / "collector.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n=== run {datetime.now().isoformat()} cmd={' '.join(cmd)}\n")
        subprocess.Popen(cmd, cwd=str(ROOT), creationflags=flags,
                         stdout=log, stderr=subprocess.STDOUT)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path):
        clean = unquote(urlsplit(path).path)
        if any(part.startswith('.') for part in clean.split('/') if part):
            return str(ROOT / '__not_found__')
        if clean.startswith('/data/'):
            target = (DISPLAY_DATA / clean[len('/data/'):]).resolve()
            if target.is_relative_to(DISPLAY_DATA.resolve()):
                return str(target)
            return str(ROOT / '__not_found__')
        return super().translate_path(path)

    def do_GET(self):
        clean = unquote(urlsplit(self.path).path)
        # Never publish local credentials, repository history or interpreter files.
        if any(part.startswith('.') for part in clean.split('/') if part):
            return self.send_error(404)
        if clean == '/':
            self.path = '/dashboard.html'
        if self.path == "/api/schedule":
            return self._json(200, load_schedule(SCHEDULE) or {})
        if self.path == "/api/sync":
            return self._json(200, {"enabled": False if DEMO_MODE else load_sync(SYNC), "demo": DEMO_MODE})
        if self.path == "/api/config":
            try:
                cfg = load_config(str(ROOT / "config.yaml"))
                return self._json(200, {"max_videos": cfg.max_videos, "per_cell": cfg.per_cell})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        return super().do_GET()

    def do_POST(self):
        if DEMO_MODE:
            return self._json(403, {"error": "Offline snapshot mode: collection and scheduling disabled"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json(400, {"error": "invalid JSON"})

        if self.path == "/api/sync":
            try:
                enabled = bool(data.get("enabled", True))
                write_sync(SYNC, enabled)
                return self._json(200, {"enabled": enabled})
            except Exception as e:
                return self._json(400, {"error": str(e)})

        if self.path == "/api/schedule":
            try:
                run_at = parse_datetime(data["date"], data["time"]).isoformat()
                plan = {
                    "run_at": run_at,
                    "max_videos": int(data.get("max_videos") or 200),
                    "reselect": bool(data.get("reselect")),
                    "per_cell": int(data.get("per_cell") or 3),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                write_schedule(SCHEDULE, plan)
                return self._json(200, {"ok": True, "plan": plan})
            except Exception as e:
                return self._json(400, {"error": str(e)})

        if self.path == "/api/run":
            if not load_sync(SYNC):
                return self._json(200, {"ok": False, "error": "sync is disabled"})
            spawn_collector(
                max_videos=int(data.get("max_videos") or 0) or None,
                reselect=bool(data.get("reselect")),
                per_cell=int(data.get("per_cell") or 0) or None,
            )
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


def scheduler_loop():
    while True:
        try:
            plan = load_schedule(SCHEDULE)
            if plan and load_sync(SYNC) and is_due(plan, datetime.now()):
                spawn_collector(
                    max_videos=plan.get("max_videos"),
                    reselect=bool(plan.get("reselect")),
                    per_cell=plan.get("per_cell"),
                )
                SCHEDULE.unlink(missing_ok=True)
        except Exception:
            pass
        time.sleep(15)


def main():
    global DISPLAY_DATA, DEMO_MODE
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=None, help='Serve offline snapshot data; disables all writes and scheduling')
    parser.add_argument('--port', type=int, default=PORT)
    args=parser.parse_args()
    DEMO_MODE = args.data_dir is not None
    if DEMO_MODE:
        DISPLAY_DATA=args.data_dir.resolve()
        if not (DISPLAY_DATA/'manifest.json').exists():
            parser.error('Run python -m collector.rebuild first to prepare the snapshot')
    else:
        threading.Thread(target=scheduler_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Flop Lab server on http://127.0.0.1:{args.port} (offline={DEMO_MODE})")
    server.serve_forever()


if __name__ == "__main__":
    main()
