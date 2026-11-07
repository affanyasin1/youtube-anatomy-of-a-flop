import csv

import pandas as pd
import pytest

import collector.main as main_mod
from collector.config import Config
from collector.main import run_daily
from collector.youtube import YouTubeError


def _cfg():
    return Config(
        min_subs=100000, min_uploads=100, per_cell=3, window_days=90, min_prior=1,
        seed=42, niches={"tech": ["gadget"]}, bands=[(100000, 500000)],
    )


def _write_channels(data_dir, two=False):
    if two:
        content = ("channel_id,title,niche,band,subscriber_count\n"
                   "c1,A,tech,band1,200000\n"
                   "c2,B,tech,band1,300000\n")
    else:
        content = ("channel_id,title,niche,band,subscriber_count\n"
                   "c1,A,tech,band1,200000\n")
    (data_dir / "channels.csv").write_text(content)


def _video(vid, lang="en"):
    return {"video_id": vid, "title": vid, "published_at": "2026-01-01T00:00:00Z",
            "duration_sec": 60, "view_count": 100, "like_count": 1,
            "comment_count": 0, "tags": [], "category_id": "28",
            "default_audio_language": lang}


class FakeClient:
    def __init__(self, uploads, videos):
        self.uploads = uploads
        self.videos = videos

    def list_uploads(self, channel_id, limit=None):
        uploads = [{"video_id": v, "published_at": "2026-01-01T00:00:00Z"} for v in self.uploads]
        return uploads[:limit] if limit else uploads

    def get_video(self, video_id):
        return self.videos[video_id]


class FailingThenOkClient:
    def __init__(self):
        self.calls = 0

    def list_uploads(self, channel_id, limit=None):
        self.calls += 1
        if self.calls == 1:
            raise YouTubeError("quota", 403)
        return [{"video_id": "v1", "published_at": "2026-01-01T00:00:00Z"}]

    def get_video(self, video_id):
        return _video("v1")


def test_run_daily_writes_all_four_files(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path)
    _write_channels(tmp_path)
    client = FakeClient(uploads=["v1"], videos={"v1": _video("v1")})
    code = run_daily(_cfg(), client)
    assert code == 0
    for name in ["runs.csv", "channel_status.csv", "videos.csv", "progress.json"]:
        assert (tmp_path / name).exists()


def test_run_daily_continues_past_channel_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path)
    _write_channels(tmp_path, two=True)
    code = run_daily(_cfg(), FailingThenOkClient())
    assert code == 0
    with open(tmp_path / "channel_status.csv") as f:
        rows = list(csv.DictReader(f))
    assert {r["status"] for r in rows} == {"failed", "success"}


def test_run_daily_filters_non_english_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path)
    _write_channels(tmp_path)
    client = FakeClient(uploads=["v1"], videos={"v1": _video("v1", lang="es")})
    run_daily(_cfg(), client)
    ids = pd.read_csv(tmp_path / "videos.csv")["video_id"].tolist()
    assert "v1" not in ids


@pytest.mark.parametrize('lang', ['en-US', 'en-IN', None])
def test_daily_retains_variants_and_marks_unknown(tmp_path, monkeypatch, lang):
    monkeypatch.setattr(main_mod, 'DATA_DIR', tmp_path)
    _write_channels(tmp_path)
    run_daily(_cfg(), FakeClient(['v1'], {'v1': _video('v1',lang)}))
    row=pd.read_csv(tmp_path/'videos.csv').iloc[0]
    assert row['video_id']=='v1'
    assert row['language_status']==('unknown' if lang is None else 'english')
    import json
    # Browser JSON parsing must work even when no valid score exists yet.
    def reject(s): raise ValueError(s)
    json.loads((tmp_path/'insights.json').read_text(),parse_constant=reject)
    json.loads((tmp_path/'comparison.json').read_text(),parse_constant=reject)
