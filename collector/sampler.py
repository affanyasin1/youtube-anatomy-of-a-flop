import csv
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from collector.config import Config
from collector.youtube import YouTubeClient, YouTubeError


def _fetch_channel(client, channel_id, title):
    try:
        info = client.get_channel(channel_id)
        return channel_id, title, info
    except Exception:
        return None


def _band_of(subs: int, bands: list) -> tuple | None:
    for lo, hi in bands:
        if lo <= subs <= hi:
            return (lo, hi)
    return None


def select_channels(client: YouTubeClient, cfg: Config) -> list[dict]:
    """Stratified-random channel selection: niche × subscriber band, per_cell each."""
    results = []
    rng = random.Random(cfg.seed)

    for niche, keywords in cfg.niches.items():
        seen = {}
        for kw in keywords:
            for ch in client.search_channels(kw):
                seen[ch["channel_id"]] = ch["title"]

        qualified = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(_fetch_channel, client, cid, t) for cid, t in seen.items()]
            for fut in futures:
                res = fut.result()
                if res is None:
                    continue
                channel_id, title, info = res
                subs = info["subscriber_count"]
                if subs < cfg.min_subs:
                    continue
                band = _band_of(subs, cfg.bands)
                if band is None:
                    continue
                if info.get("video_count", 0) < cfg.min_uploads:
                    continue
                qualified.append({
                    "channel_id": channel_id,
                    "title": title,
                    "subscriber_count": subs,
                    "band": band,
                })
        print(f"niche {niche}: {len(seen)} candidates, {len(qualified)} qualified")

        by_band = {}
        for ch in qualified:
            by_band.setdefault(ch["band"], []).append(ch)

        for band, pool in by_band.items():
            for ch in rng.sample(pool, min(len(pool), cfg.per_cell)):
                results.append({
                    "channel_id": ch["channel_id"],
                    "title": ch["title"],
                    "niche": niche,
                    "band": band,
                    "subscriber_count": ch["subscriber_count"],
                })

    return results


def save_channels(channels: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["channel_id", "title", "niche", "band", "subscriber_count"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ch in channels:
            writer.writerow(ch)
