from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    min_subs: int
    min_uploads: int
    per_cell: int
    window_days: int
    min_prior: int
    seed: int
    niches: dict
    bands: list
    max_videos: int = 200


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    bands = [tuple(b) for b in raw["bands"]]
    return Config(
        min_subs=raw["min_subs"],
        min_uploads=raw["min_uploads"],
        per_cell=raw["per_cell"],
        window_days=raw["window_days"],
        min_prior=raw["min_prior"],
        seed=raw["seed"],
        niches=raw["niches"],
        bands=bands,
        max_videos=raw.get("max_videos", 200),
    )


def load_api_key(path: str = ".env") -> str:
    env_path = Path(path)
    if not env_path.exists():
        raise RuntimeError(f"missing env file: {path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "YOUTUBE_API_KEY":
            value = value.strip()
            if value:
                return value
    raise RuntimeError("YOUTUBE_API_KEY not found or empty")
