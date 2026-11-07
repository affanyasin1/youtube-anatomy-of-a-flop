import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from collector.youtube import YouTubeError

MAX_VIDEOS = 200


@dataclass
class ChannelResult:
    new_videos: list
    status: str
    error: str | None
    duration_sec: float


def _fetch_video(client, vid):
    try:
        return client.get_video(vid)
    except Exception:
        return None


def collect_channel(client, channel: dict, existing_ids: set, raw_dir: Path,
                    max_videos: int = MAX_VIDEOS) -> ChannelResult:
    """Incrementally collect one channel's new uploads, capped at `max_videos`."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    new_videos = []

    try:
        uploads = client.list_uploads(channel["channel_id"], limit=max_videos)
    except YouTubeError as e:
        return ChannelResult(new_videos=[], status="failed", error=e.message,
                             duration_sec=time.monotonic() - start)

    new_ids = []
    for upload in uploads:
        vid = upload["video_id"]
        if vid in existing_ids:
            break
        new_ids.append(vid)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_video, client, vid): vid for vid in new_ids}
        for fut in futures:
            video = fut.result()
            if video is None:
                continue
            new_videos.append(video)
            vid = futures[fut]
            with open(raw_dir / f"{vid}.json", "w", encoding="utf-8") as f:
                json.dump(video, f)

    status = "success" if new_videos else "skipped"
    return ChannelResult(new_videos=new_videos, status=status, error=None,
                         duration_sec=time.monotonic() - start)
