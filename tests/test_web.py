import http.server
import shutil
import socketserver
import threading
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _serve(root):
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(root), **k)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
        return r.status


def test_pages_and_progress_served(tmp_path):
    # Stage the static files plus a progress.json, then serve and check reachability.
    shutil.copy(PROJECT_ROOT / "index.html", tmp_path / "index.html")
    shutil.copy(PROJECT_ROOT / "dashboard.html", tmp_path / "dashboard.html")
    shutil.copytree(PROJECT_ROOT / "assets", tmp_path / "assets")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "progress.json").write_text(
        '{"latest_run": {}, "run_history": [], "channels": []}'
    )

    httpd, port = _serve(tmp_path)
    try:
        assert _get(port, "/dashboard.html") == 200
        assert _get(port, "/index.html") == 200
        assert _get(port, "/data/progress.json") == 200
    finally:
        httpd.shutdown()
