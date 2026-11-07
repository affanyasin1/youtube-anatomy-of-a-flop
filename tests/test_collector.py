from collector.collector import collect_channel
from collector.youtube import YouTubeError


class FakeClient:
    def __init__(self, uploads, videos):
        self.uploads = uploads
        self.videos = videos

    def list_uploads(self, channel_id, limit=None):
        uploads = [{"video_id": v, "published_at": "2026-01-01T00:00:00Z"} for v in self.uploads]
        return uploads[:limit] if limit else uploads

    def get_video(self, video_id):
        return self.videos[video_id]


class RaisingClient:
    def list_uploads(self, channel_id, limit=None):
        raise YouTubeError("quota", 403)


def _video(vid):
    return {"video_id": vid, "title": vid, "published_at": "2026-01-01T00:00:00Z",
            "duration_sec": 60, "view_count": 100, "like_count": 1,
            "comment_count": 0, "tags": [], "category_id": "28",
            "default_audio_language": "en"}


def test_collect_stops_at_known_video(tmp_path):
    client = FakeClient(uploads=["v3", "v2", "v1"], videos={"v3": _video("v3"), "v2": _video("v2")})
    res = collect_channel(client, {"channel_id": "c1"}, existing_ids={"v1"}, raw_dir=tmp_path)
    assert [v["video_id"] for v in res.new_videos] == ["v3", "v2"]   # v1 skipped, nothing after
    assert res.status == "success"


def test_collect_saves_raw_json(tmp_path):
    client = FakeClient(uploads=["v3"], videos={"v3": _video("v3")})
    collect_channel(client, {"channel_id": "c1"}, existing_ids=set(), raw_dir=tmp_path)
    assert (tmp_path / "v3.json").exists()


def test_collect_marks_failed_on_api_error(tmp_path):
    res = collect_channel(RaisingClient(), {"channel_id": "c1"}, existing_ids=set(), raw_dir=tmp_path)
    assert res.status == "failed" and res.error is not None
