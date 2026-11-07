# YouTube Collection Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the daily, incremental YouTube metadata collection pipeline plus the local progress dashboard/process page that produces the `data/videos.csv` dataset.

**Architecture:** A Python CLI job (run daily via Windows Task Scheduler) that discovers ~40 stratified-random channels, pulls each channel's new uploads incrementally with dedupe-by-`video_id`, derives per-video features (rolling median virality score, title/timing features), and writes local progress files. A static HTML/JS dashboard (`dashboard.html`) fetches `data/progress.json` to show per-run and per-channel status; `index.html` renders the research design.

**Tech Stack:** Python 3.12 (installed via winget), `requests`, `pandas`, `PyYAML`, `pytest`. Static HTML/CSS/JS (no build step, no Node).

**Spec:** `docs/superpowers/specs/2026-10-13-youtube-flop-vs-viral-design.md`

## Global Constraints

- Python 3.12 only; dependencies limited to `requests`, `pandas`, `PyYAML`, `pytest`.
- `YOUTUBE_API_KEY` lives in `.env` (gitignored); never committed or logged.
- `data/` and `.env` are gitignored; raw API JSON lives under `data/raw/`.
- English-only videos ≥ 90 days old at collection; ≥ 5 prior uploads required for a valid rolling median (spec §3).
- `virality_score = views / prior_90d_median_views`; `is_flop` = score ≤ 0.2; `is_viral` = score ≥ 3 (spec §3).
- Rolling median uses only strictly-prior videos in `[published_at − 90d, published_at)` — no lookahead (spec §3).
- Daily runs are incremental: stop fetching a channel's uploads at the first `video_id` already in `data/videos.csv` (spec §5).
- Progress files: `data/runs.csv`, `data/channel_status.csv`, `data/videos.csv`, `data/progress.json` (spec §8).
- `data/videos.csv` is upserted by `video_id` (spec §8).

## Review Focus

1. **Lookahead leakage** — a video's rolling median must exclude the video itself and every later video; a viral video must never inflate its own baseline.
2. **Cold-start channels** — fewer than `min_prior` prior uploads in the window must yield `NaN` median (video excluded from analysis), never a crash or a fabricated median.
3. **Missing/disabled like & comment counts** — `None` values from the API must not break feature derivation (`tag_count` = 0 for `None` tags; virality uses views only).
4. **Dedup correctness** — a second run on the same channel must add zero duplicate rows and stop at the first known `video_id`.
5. **QuotaExceeded / 403 on one channel** — that channel is marked `failed` with its error and the run continues over remaining channels instead of aborting.

---

### Task 1: Scaffold, config, and .env handling

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `config.yaml`, `collector/__init__.py`, `collector/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_config(path="config.yaml") -> Config` and `load_api_key(path=".env") -> str`. `Config` is a dataclass with fields: `min_subs: int`, `min_uploads: int`, `per_cell: int`, `window_days: int`, `min_prior: int`, `seed: int`, `niches: dict[str, list[str]]`, `bands: list[tuple[int, int]]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
def test_load_config_loads_niches_and_bands():
    cfg = load_config("config.yaml")
    assert cfg.min_subs == 100000
    assert cfg.min_prior == 5
    assert list(cfg.niches) == ["tech", "cooking", "gaming", "education"]
    assert cfg.bands[0] == (100000, 500000)

def test_load_api_key_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("YOUTUBE_API_KEY=abc123\n")
    assert load_api_key(str(env)) == "abc123"

def test_load_api_key_missing_raises(tmp_path):
    import pytest
    with pytest.raises(RuntimeError):
        load_api_key(str(tmp_path / "nope.env"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (module/function not found).

- [ ] **Step 3: Implement `load_config` and `load_api_key` in `collector/config.py`**

`load_config` reads YAML via `PyYAML`, converts each `bands` entry to `tuple[int, int]`, returns `Config`. `load_api_key` parses `KEY=VALUE` lines (no external dotenv dep), strips whitespace, returns the value for `YOUTUBE_API_KEY`; raises `RuntimeError` if missing or empty. Also create `.gitignore` (`__pycache__/`, `.env`, `data/`, `.pytest_cache/`), `.env.example` (contains `YOUTUBE_API_KEY=`), `requirements.txt` (`requests`, `pandas`, `PyYAML`, `pytest`), and `config.yaml` with the exact values above (niches tech/cooking/gaming/education, bands `[100000,500000]/[500000,2000000]/[2000000,10000000]`, `per_cell: 3`, `window_days: 90`, `min_prior: 5`, `seed: 20261013`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Initialize repo and commit**

```bash
git init
python -m pip install -r requirements.txt
git add .gitignore .env.example requirements.txt config.yaml collector/__init__.py collector/config.py tests/test_config.py
git commit -m "chore: scaffold config, .env handling, and dependencies"
```

---

### Task 2: YouTube API client

**Files:**
- Create: `collector/youtube.py`
- Test: `tests/test_youtube.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class YouTubeClient` with `__init__(api_key: str)`, and methods returning plain dicts:
  - `search_channels(keyword: str, max_results: int = 50) -> list[dict]` — each `{"channel_id", "title"}`.
  - `get_channel(channel_id: str) -> dict` — `{"channel_id", "title", "subscriber_count"}`.
  - `list_uploads(channel_id: str) -> list[dict]` — newest-first, each `{"video_id", "published_at"}` (paginated via the channel's uploads playlist).
  - `get_video(video_id: str) -> dict` — `{"video_id", "title", "published_at", "duration_sec", "view_count", "like_count", "comment_count", "tags", "category_id", "default_audio_language"}`.
  - Raises `YouTubeError(message, status_code)` on non-200.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_youtube.py  (patch requests.get via unittest.mock)
def test_get_video_parses_all_parts():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = {"items": [{
            "id": "v1", "snippet": {"title": "T", "publishedAt": "2026-01-01T00:00:00Z",
            "tags": ["a"], "categoryId": "28"},
            "contentDetails": {"duration": "PT3M30S"},
            "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "2"}}]}
        v = client.get_video("v1")
    assert v["duration_sec"] == 210
    assert v["view_count"] == 100 and v["tags"] == ["a"]

def test_get_video_missing_stats_returns_none():
    client = YouTubeClient("k")
    with patch("collector.youtube.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = {"items": [{
            "id": "v1", "snippet": {"title": "T", "publishedAt": "2026-01-01T00:00:00Z"},
            "contentDetails": {"duration": "PT1M"}}]}  # no statistics key
        v = client.get_video("v1")
    assert v["like_count"] is None and v["view_count"] is None

def test_get_video_non_200_raises_youtube_error():
    # g.return_value.status_code = 403 -> pytest.raises(YouTubeError)
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `YouTubeClient` in `collector/youtube.py`**

Use `requests.get` against `https://www.googleapis.com/youtube/v3/{endpoint}` with `key`, `part`, and paging params. Convert ISO-8601 `duration` to seconds via a small `parse_duration` helper. `get_video` requests `snippet,contentDetails,statistics` and maps missing keys to `None`. `list_uploads` first resolves the uploads playlist id from `channels.list`, then pages `playlistItems.list`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/youtube.py tests/test_youtube.py
git commit -m "feat: add YouTube API client"
```

---

### Task 3: Rolling median (lookahead-free)

**Files:**
- Create: `collector/derive.py`
- Test: `tests/test_rolling_median.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `rolling_median_views(df: pd.DataFrame, window_days: int = 90, min_prior: int = 5) -> pd.Series`. `df` must have `channel_id`, `published_at` (datetime), `view_count`; returns a `pd.Series` aligned to `df.index`, `NaN` where fewer than `min_prior` strictly-prior in-window videos exist.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rolling_median.py
def test_rolling_median_excludes_self_and_future():
    df = pd.DataFrame({
        "channel_id": ["c"]*4,
        "published_at": pd.to_datetime(["2026-01-01","2026-01-15","2026-02-01","2026-02-15"]),
        "view_count": [100, 200, 100000, 300],
    })
    r = rolling_median_views(df, window_days=90, min_prior=1)
    # viral video (index 2, 100000 views) must not inflate its own or prior baselines
    assert r.iloc[1] == 100.0          # median of [100]
    assert r.iloc[2] == 150.0          # median of [100, 200] — NOT influenced by 100000
    assert r.iloc[3] == 200.0          # median of [100, 200, 100000] sorted -> 200

def test_rolling_median_cold_start_returns_nan():
    df = pd.DataFrame({"channel_id":["c"]*3,
        "published_at": pd.to_datetime(["2026-01-01","2026-01-10","2026-01-20"]),
        "view_count":[10,20,30]})
    r = rolling_median_views(df, window_days=90, min_prior=5)
    assert r.isna().all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rolling_median.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rolling_median_views` in `collector/derive.py`**

Sort by `published_at`; for each row compute the median of `view_count` of the same channel's rows with `published_at` strictly before the row and within `window_days`; return `NaN` when fewer than `min_prior` such rows exist. (Use a per-channel sorted walk, not a full Cartesian join.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rolling_median.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/derive.py tests/test_rolling_median.py
git commit -m "feat: lookahead-free rolling median"
```

---

### Task 4: Feature derivation

**Files:**
- Modify: `collector/derive.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `rolling_median_views` from Task 3.
- Produces: `add_features(df: pd.DataFrame, window_days: int = 90, min_prior: int = 5) -> pd.DataFrame`. Input has `channel_id, published_at, view_count, title, tags, duration_sec, channel_subs`; output adds `prior_90d_median_views, virality_score, is_flop, is_viral, title_length, has_number, has_question, caps_ratio, tag_count, publish_hour, publish_dayofweek, time_since_last_upload`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_features.py
def test_add_features_basic_columns():
    df = pd.DataFrame({
        "channel_id": ["c"]*2,
        "published_at": pd.to_datetime(["2026-01-01","2026-01-15"]),
        "view_count": [100, 200],
        "title": ["How to bake a cake", "10 Tricks!"],
        "tags": [["a","b"], None],
        "duration_sec": [210, 60],
        "channel_subs": [500000, 500000],
    })
    out = add_features(df, min_prior=1)
    assert out.loc[1, "virality_score"] == 2.0      # 200 / 100
    assert out.loc[0, "has_number"] == False
    assert out.loc[1, "has_number"] == True
    assert out.loc[1, "tag_count"] == 0             # None tags -> 0, not crash
    assert out.loc[1, "time_since_last_upload"].days == 14

def test_add_features_flags():
    # score 0.2 -> is_flop True; score 3 -> is_viral True; 1.0 -> neither
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_features.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `add_features` in `collector/derive.py`**

Compute `prior_90d_median_views` via Task 3, then `virality_score = view_count / prior_90d_median_views` (NaN where median is NaN). `is_flop = virality_score <= 0.2`; `is_viral = virality_score >= 3` (both False where NaN). `title_length = len(title)`; `has_number` = any char is a digit; `has_question` = `"?" in title`; `caps_ratio` = share of letters that are uppercase; `tag_count = len(tags) if tags else 0`; `publish_hour`/`publish_dayofweek` from `published_at`; `time_since_last_upload` = days since the channel's previous video.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_features.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/derive.py tests/test_features.py
git commit -m "feat: derive virality score and title/timing features"
```

---

### Task 5: Stratified-random channel sampler

**Files:**
- Create: `collector/sampler.py`
- Test: `tests/test_sampler.py`

**Interfaces:**
- Consumes: `YouTubeClient` (Task 2), `Config` (Task 1).
- Produces: `select_channels(client: YouTubeClient, cfg: Config) -> list[dict]`, each `{"channel_id", "title", "niche", "band", "subscriber_count"}`; `save_channels(channels: list[dict], path: Path) -> None` writes `data/channels.csv`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sampler.py  (fake client with a small seeded pool)
def test_select_channels_is_deterministic_with_seed():
    a = select_channels(fake_client(), cfg)
    b = select_channels(fake_client(), cfg)
    assert [c["channel_id"] for c in a] == [c["channel_id"] for c in b]

def test_select_channels_filters_by_subs_and_uploads():
    # channel with 50k subs excluded; channel with 5 uploads excluded
    ids = [c["channel_id"] for c in select_channels(fake_client(), cfg)]
    assert "small" not in ids and "few_uploads" not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sampler.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `select_channels` in `collector/sampler.py`**

For each niche, call `search_channels` on each keyword, dedupe by `channel_id`, enrich with `get_channel` to obtain `subscriber_count`, filter to `>= min_subs` and `>= min_uploads` (uploads count obtained via `list_uploads` length, or skipped in the fake by direct count), assign each channel to a `band` by subscriber range, then `random.Random(seed)` sample up to `per_cell` per (niche, band) cell. `save_channels` writes a CSV with the fixed column order.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sampler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/sampler.py tests/test_sampler.py
git commit -m "feat: stratified-random channel selection"
```

---

### Task 6: Incremental collector with dedupe and raw save

**Files:**
- Create: `collector/collector.py`
- Test: `tests/test_collector.py`

**Interfaces:**
- Consumes: `YouTubeClient` (Task 2).
- Produces: `collect_channel(client: YouTubeClient, channel: dict, existing_ids: set[str], raw_dir: Path) -> ChannelResult`, where `ChannelResult` is a dataclass `{new_videos: list[dict], status: str, error: str | None, duration_sec: float}` and `status ∈ {"success","failed","skipped"}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_collector.py  (fake client + tmp_path raw_dir)
def test_collect_stops_at_known_video(tmp_path):
    client = fake_client(uploads=["v3","v2","v1"], videos={"v3": {...}, "v2": {...}})
    res = collect_channel(client, channel, existing_ids={"v1"}, raw_dir=tmp_path)
    assert [v["video_id"] for v in res.new_videos] == ["v3", "v2"]   # v1 skipped, nothing after
    assert res.status == "success"

def test_collect_saves_raw_json(tmp_path):
    res = collect_channel(client, channel, existing_ids=set(), raw_dir=tmp_path)
    assert (tmp_path / "v3.json").exists()

def test_collect_marks_failed_on_api_error(tmp_path):
    res = collect_channel(raising_client(), channel, existing_ids=set(), raw_dir=tmp_path)
    assert res.status == "failed" and res.error is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_collector.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `collect_channel` in `collector/collector.py`**

Iterate `list_uploads` newest-first; on the first `video_id` in `existing_ids`, break; otherwise `get_video` and append to `new_videos`, saving each raw response JSON to `raw_dir/<video_id>.json`. Wrap the whole channel body in try/except: on `YouTubeError`, return `status="failed"` with the message; on success, `status="success"`. Record `duration_sec` via `time.monotonic()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_collector.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/collector.py tests/test_collector.py
git commit -m "feat: incremental channel collector with dedupe and raw save"
```

---

### Task 7: Progress tracking files

**Files:**
- Create: `collector/progress.py`
- Test: `tests/test_progress.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `record_run(runs_csv: Path, run: dict) -> None` (appends one row); `record_channel_status(path: Path, rows: list[dict]) -> None` (appends rows); `write_progress_json(runs_csv, channel_status_csv, videos_csv, out: Path) -> None` (writes `data/progress.json` with keys `latest_run`, `run_history`, `channels`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_progress.py
def test_record_run_appends(tmp_path):
    p = tmp_path / "runs.csv"
    record_run(p, {"run_id":"r1","channels_attempted":2,"channels_success":1,
                   "channels_failed":1,"channels_skipped":0,"videos_new":5})
    import csv
    with open(p) as f: rows = list(csv.DictReader(f))
    assert rows[0]["run_id"] == "r1" and rows[0]["channels_success"] == "1"

def test_write_progress_json_aggregates(tmp_path):
    # build tiny runs.csv + channel_status.csv + videos.csv, assert latest_run
    # and channels lists have the right shapes/values
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_progress.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the three functions in `collector/progress.py`**

`record_run` and `record_channel_status` create the file with a header row if absent, then append. `write_progress_json` reads the CSVs with `pandas`, computes `latest_run` (last row of `runs.csv`), `run_history` (list of dicts), and `channels` (latest status per `channel_id` joined with `niche`/`subs`/video count), and writes compact JSON. All outputs go under `data/`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_progress.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/progress.py tests/test_progress.py
git commit -m "feat: run and channel progress tracking"
```

---

### Task 8: Daily run orchestration (CLI)

**Files:**
- Create: `collector/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `YouTubeClient` (Task 2), `select_channels`/`save_channels` (Task 5), `collect_channel` (Task 6), `add_features` (Task 4), progress writers (Task 7).
- Produces: `run_daily(cfg: Config, client: YouTubeClient) -> int` (exit code 0/1); `main() -> None` CLI wrapper (`python -m collector.main`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py  (fake client, tmp data dir)
def test_run_daily_writes_all_four_files(tmp_path, monkeypatch):
    code = run_daily(cfg, fake_client())
    assert code == 0
    for name in ["runs.csv","channel_status.csv","videos.csv","progress.json"]:
        assert (DATA_DIR / name).exists()

def test_run_daily_continues_past_channel_failure(tmp_path):
    # fake client: first channel raises YouTubeError, second succeeds
    code = run_daily(cfg, failing_then_ok_client())
    assert code == 0
    rows = list(csv.DictReader(open(DATA_DIR / "channel_status.csv")))
    assert {r["status"] for r in rows} == {"failed", "success"}

def test_run_daily_filters_non_english_videos(tmp_path):
    # new video with default_audio_language="es" is excluded from videos.csv
    run_daily(cfg, fake_client(videos=[{"video_id": "v1", "default_audio_language": "es"}]))
    ids = pd.read_csv(DATA_DIR / "videos.csv")["video_id"].tolist()
    assert "v1" not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `run_daily` in `collector/main.py`**

Load `data/channels.csv` if it exists (re-selecting only when missing), load existing `video_id` set from `data/videos.csv`, `collect_channel` each channel, record per-channel status, then filter new videos to English (`default_audio_language` is `None` or `"en"`), run `add_features` over the union of new + existing videos, upsert `data/videos.csv` by `video_id`, write `runs.csv` and `progress.json`, and print a one-line summary (attempted/success/failed/skipped, videos new/total). A per-channel failure does not abort the run.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add collector/main.py tests/test_main.py
git commit -m "feat: daily run orchestration CLI"
```

---

### Task 9: Static web app (process page + dashboard)

**Files:**
- Create: `index.html`, `dashboard.html`, `assets/style.css`, `assets/dashboard.js`, `README.md`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `data/progress.json` (Task 7) via `fetch()`; the spec (rendered into `index.html`).
- Produces: two pages served from the project root; `assets/dashboard.js` exposes `buildPanels(progress)` returning `{latest, history, channels}` for the three panels.

- [ ] **Step 1: Write the failing test (HTTP smoke)**

```python
# tests/test_web.py
def test_pages_and_progress_served(tmp_path):
    # start http.server on project root in a thread; assert:
    # GET /dashboard.html -> 200; GET /index.html -> 200; GET /data/progress.json -> 200
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web.py -v`
Expected: FAIL (files do not exist yet).

- [ ] **Step 3: Implement the pages in `index.html`, `dashboard.html`, `assets/`**

`index.html` is a static rendering of the research design (RQ, sampling grid, features, phases) from the spec. `dashboard.html` loads `assets/dashboard.js`, which `fetch()`es `data/progress.json` every 5s and renders: **latest run** (success/fail/skip counts, videos, quota, runtime, timestamp), **run history** (daily success vs failed bars), and **per-channel table** (niche, subs, videos, last-run status + error), with an explicit **extracted (total)** vs **analysis-eligible (≥ 90d)** split. `buildPanels(progress)` is a pure function (no DOM) so it is unit-testable; `renderDashboard()` calls it and mutates the DOM. `README.md` documents `pip install -r requirements.txt`, `python -m collector.main`, and `python -m http.server 8000` from the project root.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`
Expected: PASS.

- [ ] **Step 5: Manual verification**

Run: `python -m http.server 8000` from project root; open `http://localhost:8000/dashboard.html`; confirm the three panels render from `data/progress.json` and refresh. Then `git add index.html dashboard.html assets README.md tests/test_web.py && git commit -m "feat: process page and live dashboard"`.

---

### Task 10: First real run and scheduler wiring

**Files:**
- Create: `.env` (gitignored, from `.env.example`) with the provided `YOUTUBE_API_KEY`
- Modify: none (writes `data/` at runtime)

**Interfaces:**
- Consumes: everything above.
- Produces: a populated `data/` directory from a real API run.

- [ ] **Step 1: Write the API key to `.env`** (never commit it; `.gitignore` already excludes it).

- [ ] **Step 2: Dry run against the real API (channel selection only)**

Run: `python -m collector.main --select-only`
Expected: `data/channels.csv` contains ~40 rows across 4 niches × 3 bands; print per-cell counts.

- [ ] **Step 3: First full collection run**

Run: `python -m collector.main`
Expected: exits 0; `data/videos.csv`, `data/runs.csv`, `data/channel_status.csv`, `data/progress.json` exist; summary line reports channels attempted/success/failed and videos new.

- [ ] **Step 4: Verify dashboard against real data**

Run: `python -m http.server 8000`; open `http://localhost:8000/dashboard.html`.
Expected: latest run + history + per-channel table populated; failed channels (if any) show an error.

- [ ] **Step 5: Register the daily job in Windows Task Scheduler**

Run: `schtasks /Create /TN "YoutubeFlopCollector" /TR "python -m collector.main" /SC DAILY /ST 03:00`
Expected: task listed via `schtasks /Query /TN YoutubeFlopCollector`.

---

## Scope note

This plan covers **Plan 1**: collection + feature derivation + progress tracking + web app. The analysis work (descriptive stats, LightGBM modeling, matched pairs, topic-entity extraction, and the Wikipedia-pageviews topic-demand proxy — spec §6–§7) is a separate follow-up plan (**Plan 2**) that consumes `data/videos.csv`; it is deliberately out of scope here so the daily collector and dashboard start producing data first.
