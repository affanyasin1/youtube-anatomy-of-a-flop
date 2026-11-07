import csv

from collector.config import Config
from collector.sampler import save_channels, select_channels


def _cfg():
    return Config(
        min_subs=100000,
        min_uploads=100,
        per_cell=3,
        window_days=90,
        min_prior=5,
        seed=42,
        niches={"tech": ["gadget"], "cooking": ["recipe"]},
        bands=[(100000, 500000), (500000, 2000000)],
    )


class FakeClient:
    def __init__(self, channels):
        self.channels = channels

    def search_channels(self, keyword, max_results=50):
        return [{"channel_id": c["channel_id"], "title": c["title"]} for c in self.channels]

    def get_channel(self, channel_id):
        c = next(x for x in self.channels if x["channel_id"] == channel_id)
        return {"channel_id": c["channel_id"], "title": c["title"],
                "subscriber_count": c["subscriber_count"],
                "video_count": c["uploads"]}


def _pool():
    return [
        {"channel_id": "c1", "title": "A", "subscriber_count": 200000, "uploads": 120},
        {"channel_id": "c2", "title": "B", "subscriber_count": 300000, "uploads": 150},
        {"channel_id": "c3", "title": "C", "subscriber_count": 400000, "uploads": 200},
        {"channel_id": "c4", "title": "D", "subscriber_count": 1000000, "uploads": 130},
        {"channel_id": "small", "title": "S", "subscriber_count": 50000, "uploads": 120},
        {"channel_id": "few_uploads", "title": "F", "subscriber_count": 250000, "uploads": 5},
    ]


def test_select_channels_is_deterministic_with_seed():
    a = select_channels(FakeClient(_pool()), _cfg())
    b = select_channels(FakeClient(_pool()), _cfg())
    assert [c["channel_id"] for c in a] == [c["channel_id"] for c in b]


def test_select_channels_filters_by_subs_and_uploads():
    ids = [c["channel_id"] for c in select_channels(FakeClient(_pool()), _cfg())]
    assert "small" not in ids and "few_uploads" not in ids


def test_save_channels_writes_csv(tmp_path):
    channels = [{"channel_id": "c1", "title": "A", "niche": "tech",
                 "band": (100000, 500000), "subscriber_count": 200000}]
    p = tmp_path / "channels.csv"
    save_channels(channels, p)
    with open(p) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["channel_id"] == "c1" and rows[0]["niche"] == "tech"
    assert list(rows[0].keys()) == ["channel_id", "title", "niche", "band", "subscriber_count"]
