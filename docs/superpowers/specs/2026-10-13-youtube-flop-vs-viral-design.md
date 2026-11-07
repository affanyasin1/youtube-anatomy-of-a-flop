# Design Spec: "Anatomy of a Flop" — Within-Channel Predictors of YouTube Under/Over-Performance

**Date:** 2026-10-13
**Status:** Draft for review
**Goal:** Publishable paper + open (metadata-only) dataset

---

## 1. Objective

Quantify what distinguishes videos that *flop* from videos that go *viral* among established YouTube creators (100k+ subscribers), holding creator-level factors constant — production quality, budget, authority, niche, and upload cadence — by comparing each video against its own channel's prior performance.

## 2. Research Question & Hypotheses

**RQ:** Within established creators (100k+ subs), holding channel/quality/niche constant, which metadata and topic-demand features differentiate flops from viral videos?

**Hypotheses (to falsify):**

- **H1** — Timing effects are niche-specific; there is no universal best posting hour/day.
- **H2** — Duration effects are stronger within-channel than across channels (drift from a creator's proven format predicts flop).
- **H3** — Title valence/sentiment separates flops from viral (neutral/informational titles underperform).
- **H4** — Topic demand (proxied by Wikipedia pageviews at publish time) predicts virality beyond title/duration/timing alone.

## 3. Outcome Variables

**Primary (continuous):** `log10(virality_score)`, where
`virality_score = views / prior_90d_median_views`.

**Secondary (binary):** `is_flop` (score ≤ 0.2) and `is_viral` (score ≥ 3). Used for classification and SHAP interpretation only; the continuous regression is the primary analysis.

**Inclusion rules:**

- English-language videos only.
- Videos ≥ 90 days old at collection time.
- ≥ 5 prior uploads in the rolling window (excludes cold-start videos).

**Rolling median (lookahead-free):** for each video, the median views of the channel's videos published in `[publish_time − 90d, publish_time)` — strictly prior, never including the target or any later video.

## 4. Sampling Design (Pre-Registered)

- **Niches:** tech, cooking, gaming, education.
- **Subscriber bands:** 100k–500k, 500k–2M, 2M–10M.
- **Grid:** 4 × 3 = 12 cells; target ~3–4 channels per cell → ~40 channels total.
- **Selection rule** (frozen in config before collection = the pre-registration artifact):
  1. Per niche, generate a seed list via YouTube `search.list` (channel type) on a fixed keyword set.
  2. Dedupe; filter to 100k+ subs, ≥ 100 public uploads, primarily English.
  3. Systematic random sample (fixed seed) to per-cell targets.

**Quota note:** `search.list` costs **100 units/call** (vs. 1 for `videos.list` / `channels.list` / `playlistItems.list`). Channel discovery is therefore budgeted separately: expect ~1,000–1,500 units one-time for seed-list generation. Backfill of video metadata is the ~300–500 units cited in the plan.

## 5. Data Collection Pipeline

**Schedule:** daily job via Windows Task Scheduler.

**Per run, per channel:**

1. `channels.list` → refresh subscriber count.
2. Fetch recent uploads via `playlistItems.list` (uploads playlist), newest-first; **stop at the first `video_id` already in the dataset** (incremental, deduped).
3. For each new video: `videos.list` (`snippet,contentDetails,statistics`) → id, title, published_at, duration, views, likes, comments, tags, categoryId.
4. Save raw API JSON first (`data/raw/<channel_id>/...`); derive the CSV separately so derivation is idempotent and re-runnable.

**Quota:** ~40–80 units/day incremental; one-time backfill ~300–500 units.

**Error handling:** per-channel try/except; failures recorded with error message; channel marked failed/skipped; the run continues and reports aggregate success/failure at the end.

## 6. Feature Engineering

**Baseline:** `title_length`, `has_number`, `has_question`, `caps_ratio`, `tag_count`, `duration_sec`, `publish_hour`, `publish_dayofweek`, `channel_subs`, `time_since_last_upload`.

**Topic:** primary entity/keyphrase extracted from title via TF-IDF clustering within niche/channel (dependency-light).

**Topic-demand proxy:** map entity → Wikipedia pageviews at publish time (stable, free, scriptable API). Primary demand signal. Google Trends is optional and gated behind rate-limit/coverage issues.

## 7. Analysis Plan

**Phase 1 — Descriptive.** Flop vs. viral on every feature. Within-channel paired effect sizes + mixed-effects models (channel random intercept). FDR correction. No naive pooled Mann-Whitney U as primary inference.

**Phase 2 — Predictive.** Baseline logistic regression (duration + title_length + topic demand) vs. LightGBM gradient boosting. Grouped per-channel cross-validation (train/test split by channel, never random). Report AUC + SHAP values (direction and magnitude).

**Phase 3 — Matched Pairs (sensitivity).** For each viral video, match the nearest flop within the same channel by title/tag TF-IDF cosine similarity. Conditional logistic regression on within-pair differences (title, duration, timing, topic demand). Answers: *holding topic constant, do title/timing/duration still matter?*

## 8. Progress Tracking & Data Model

Local files only — no database required for v1.

| File | Contents |
|------|----------|
| `data/runs.csv` | `run_id, started_at, finished_at, status, channels_attempted, channels_success, channels_failed, channels_skipped, videos_new, videos_total, quota_used` |
| `data/channel_status.csv` | `run_id, channel_id, title, niche, subs, status (success/failed/skipped), error_message, duration_sec` |
| `data/videos.csv` | main dataset, upserted by `video_id` (full schema below) |
| `data/progress.json` | aggregate for the dashboard: latest run summary, per-channel latest status, run history |

**`data/videos.csv` schema:** `video_id, channel_id, title, published_at, views, likes, comments, duration_sec, tags, category_id, channel_subs, prior_90d_median_views, virality_score, is_flop, is_viral, title_length, has_number, has_question, caps_ratio, tag_count, publish_hour, publish_dayofweek, time_since_last_upload, topic_entity, topic_demand`.

## 9. Web App (Local-First Static)

Single static app (HTML/CSS/JS, no build step), served locally.

- **Process page** — renders this research design for humans (RQ, sampling, features, phases).
- **Dashboard** — `fetch()`es `data/progress.json`, auto-refresh ~5s. Three panels:
  1. **Latest run** — success/fail/skip counts, videos extracted, quota used, runtime, timestamp.
  2. **Run history** — daily success vs. failed over time.
  3. **Per-channel table** — niche, subs, videos, last-run status (+ error), sortable/filterable.

The dashboard distinguishes **extracted (total)** from **analysis-eligible (≥ 90 days old)** — the two diverge by design as new videos age into the analysis.

## 10. Reproducibility & Testing

- Locked environment (`requirements.txt` + Python version), fixed seeds, versioned raw data.
- **Leakage tests:** assert no future views leak into the median; assert train/test channels are disjoint.
- **Unit tests:** title feature functions; rolling-median computation on synthetic data.
- **Self-verify:** static build + runtime smoke test of the dashboard (fetch `progress.json`, render panels).

## 11. Deliverables

1. **Open dataset** — metadata-only CSV + codebook (schema, units, sampling method), permissive license, fully ToS-compliant.
2. **Paper** — mapped to the three analysis phases.
3. **Local web app** — process page + live dashboard.

## 12. Out of Scope (v1)

- Hook analysis (OpenCV/Whisper), comment forensics, video download.
- "Pre-publish checker" creator tool.
- Cloud hosting (the static app is trivially deployable later if desired).

## 13. Assumptions / Open Items

- The existing collection script is **not** in this workspace (directory is empty). Implementation either imports it or rebuilds the collection layer.
- Wikipedia pageviews is the chosen demand signal; switch to Google Trends only if rate limits or coverage demand it.
- Niche keyword sets and the fixed random seed are finalized in `config.yaml` before collection begins (the pre-registration step).
