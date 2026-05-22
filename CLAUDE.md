# BoxBoxF1Fantasy — System Overview

F1 Fantasy prediction pipeline and website for the 2026 season. Predicts qualifying/race positions, calculates fantasy points, runs Monte Carlo simulations, and serves results on [boxboxf1fantasy.com](https://boxboxf1fantasy.com).

## Quick Facts

- **Season:** 2026 (new regulations, 11 teams, 22 drivers, Cadillac is new)
- **Training data:** 2020-2026 (~2,600 rows), 2026 weighted 2.5x
- **ML:** XGBoost ranking models (LambdaMART) for qualifying and race position prediction
- **Frontend:** Vanilla JS, no framework, static JSON data, hosted on Vercel
- **Deployment:** `git push` to GitHub → Vercel auto-deploys
- **Sprint rounds 2026:** 2, 6, 7, 11, 14, 18
- **Cancelled rounds 2026:** 4, 5

## Project Structure

```
BoxBoxF1FantasyV2/
├── pipeline/               # Numbered Python scripts, run in order
│   ├── 01_download_data.py         # FastF1 telemetry + Jolpica API download
│   ├── 02_build_laps.py            # Parse raw data into lap-level parquets (FP1+SQ on sprint, FP1/2/3 otherwise)
│   ├── 03_extract_features.py      # FP telemetry features (40+ cols, sparse)
│   ├── 03a_normalize_jolpica.py    # Normalize historical results
│   ├── 03b_build_jolpica_features.py # Rolling features (91 cols, always available)
│   ├── 04_build_model_inputs.py    # Merge layers, create train/predict datasets
│   ├── 05_train_models.py          # Train XGBRanker quali + race models
│   ├── 06_run_predictions.py       # Generate position predictions for a round
│   ├── 07_calculate_fantasy.py     # Predicted positions → fantasy points
│   ├── 08_monte_carlo_fantasy.py   # 10K-sim MC for confidence intervals
│   ├── 08_export_website_json.py   # Parquets → JSON for website
│   ├── 09_post_race_analysis.py    # Predicted vs actual comparison
│   ├── 10_fp_analysis.py           # Free practice pace analysis
│   ├── 11_actual_fantasy_points.py # Calculate actual fantasy points from results
│   ├── 11_race_deep_dive.py        # Detailed race analysis
│   ├── 12_count_overtakes.py       # Overtakes from FastF1 sector data
│   ├── 13_fetch_openf1_overtakes.py # Overtakes from OpenF1 API
│   ├── 13_fetch_pitstop_stationary.py # Pit stop stationary times
│   ├── calibrate_confidence.py      # CI calibration: MC predictions vs actuals
│   ├── run_weekend.py              # Orchestrator: detects phase, runs pipeline
│   ├── predict_horizon.py          # Priors-only ML predictions for upcoming rounds (multi-week planner input)
│   ├── weather_forecast.py         # Open-Meteo weather forecasts
│   ├── feature_engineering.py      # Cross-layer engineered features
│   └── build_articles.py           # Article content generation
├── config/
│   ├── settings.py                 # All paths, constants, feature columns
│   ├── fantasy_scoring.py          # Official F1 Fantasy 2026 scoring rules
│   ├── track_classifications.py    # 9-dimensional circuit feature vectors
│   ├── track_similarity.py         # Cosine similarity for track weighting
│   ├── team_driver_ratings.py      # Manual skill ratings per team/driver
│   └── circuit_coordinates.py      # Track GPS coordinates
├── data/
│   ├── raw/fastf1/year{Y}/round{R}/ # FP1/2/3 + sprint quali parquets (sprint weekends)
│   ├── raw/jolpica/year{Y}/round{R}/ # Results, qualifying, sprint, pitstops JSON
│   ├── processed/                    # Intermediate: features, model inputs
│   ├── predictions/round{N}/         # Per-round prediction parquets
│   └── seed/                         # Manual data (prices, drivers, races, etc.)
│       ├── fantasy_prices.json       # Current + starting prices + price_history per round
│       ├── drivers.json              # 22-driver roster with constructor mapping
│       ├── constructors.json         # 11 constructors
│       ├── races.json                # 2026 calendar
│       ├── official_fantasy_points.json # Official F1 Fantasy points (manually entered)
│       └── mc_calibration.json       # MC noise calibration from actual results
├── models/trained/                   # Saved XGBoost models (.json)
├── web/public/
│   ├── index.html                    # Single-page app shell
│   ├── app.js                        # All frontend logic (~5,500+ lines)
│   ├── styles.css                    # CSS with custom properties for theming
│   └── data/                         # JSON files served to frontend
│       ├── predictions.json          # Current round predictions
│       ├── season_summary.json       # Rounds, driver/constructor prices
│       ├── actual_round{N}.json      # Actual results per round
│       ├── official_fantasy_points.json
│       ├── track_data.json           # Circuit feature vectors + race-circuit mappings
│       └── driver_history.json       # Per-driver/constructor actual points history
├── docs/                             # Technical documentation + user guide
├── dashboard/                        # Streamlit analytics dashboard
└── vercel.json                       # Vercel deployment config
```

## Architecture: Two-Layer Feature System

The core design: two data layers merged for XGBoost, which handles NaN natively.

- **Layer 1 — Jolpica Priors (91 features, always available):** Rolling averages (1/3/5 race windows), circuit experience, constructor trends, teammate deltas, DNF rates, form trends, track similarity features, skill ratings. Uses `.shift(1)` to prevent leakage.
- **Layer 2 — FP Telemetry (40+ features, sparse/NaN in training):** Lap times, sectors, degradation, long-run pace, compound-specific features (soft/medium/hard), relative pace deltas. Only ~160/2,600 training rows have this data.

XGBoost's native NaN handling means: when FP data exists → model uses it to refine; when missing → model relies on priors. No imputation needed.

Model features are extracted ONLY from FP sessions (`all_laps_fp*.parquet`). Sprint qualifying laps are saved separately and consumed only by `10_fp_analysis.py` for the Deep Dive page — they do not feed model training/inference. The model still picks up sprint qualifying as a grid input via `06_run_predictions.py` (the `sprint_grid` feature).

## Calendar Mapping: Internal Round vs External APIs

`data/seed/races.json` preserves original 2026 numbering with `cancelled: true` markers (Bahrain R4, Saudi R5). **Both FastF1 AND Jolpica/Ergast omit cancelled races from their numbering**, so external round numbers diverge from internal after the first cancellation. Use `config.settings.fastf1_round(internal_round, year)` at every external API boundary — it subtracts the count of cancelled rounds preceding the target round. (The helper is named `fastf1_round` for historical reasons but applies to Jolpica too — both APIs compress identically.)

The internal round number is preserved in file paths and logging, so we still write Miami to `data/raw/jolpica/year2026/round6/` even though the request URL is `2026/4/results.json`. Skipping this mapping leads to silently downloading the wrong race's data (e.g. internal R6 = Miami → FastF1 R6 = Monaco) or empty Jolpica responses (Jolpica has no round 6 yet — only 4 races run in their numbering).

Callsites that apply this mapping:
- FastF1: `01_download_data.py`, `02_build_laps.py`, `06_run_predictions.py`, `12_count_overtakes.py`
- Jolpica: `01_download_data.py` (`download_jolpica_round`)

**OpenF1 is different — no mapping needed.** OpenF1 preserves the ORIGINAL 2026 calendar with cancelled-round sessions still listed (Bahrain at position 4, Saudi at position 5). So internal round N maps 1:1 to the Nth race session in OpenF1's date-sorted list. Applying a cancelled-round offset to OpenF1 returns the wrong session — internal R6 (Miami) was previously resolving to Sakhir's session_key in `13_fetch_openf1_overtakes.py` until this was fixed.

## ML Models

- **Qualifying model:** `XGBRanker(n_estimators=1200, lr=0.025, depth=3, objective="rank:pairwise")`
- **Race model (post-quali):** `XGBRanker(n_estimators=650, lr=0.03, depth=5, objective="rank:pairwise")` — trained on ACTUAL `quali_position`, used at inference when qualifying has happened
- **Race-FP model (post-FP):** same hyperparams as race model but trained on WALK-FORWARD PREDICTED `quali_position` (each season's quali is predicted by a quali model trained on earlier seasons). Used at inference during the post-FP phase when qualifying hasn't happened yet. Eliminates the train/inference distribution shift that occurs when the race model is fed a noisy predicted quali at inference but was trained on clean actual quali.
- **Sprint model:** `XGBRanker(n_estimators=400, lr=0.035, depth=4, objective="rank:pairwise")` — trained on 501 sprint-only rows, uses sprint qualifying grid as top feature
- **FP signal model:** `ExtraTreesRegressor(n_estimators=500, depth=6)` — used only for confidence scoring, not direct predictions
- Output is relevance scores ranked to produce predicted positions per race
- **Phase-aware inference (06_run_predictions.py):** auto-detects whether actual qualifying data is available for the round. Post-quali → uses `race_model.json` with actual quali positions. Post-FP → uses `race_model_fp.json` with predicted quali positions.
- **Calibration:** `calibrate_confidence.py` compares MC predictions vs actuals, saves noise multiplier to `data/seed/mc_calibration.json`, auto-loaded by MC simulation

## Fantasy Scoring (07_calculate_fantasy.py)

**Drivers:** Qualifying position pts + race position pts + positions gained/lost + overtakes (+1 each) + fastest lap probability (10pts) + DOTD probability (10pts) - DNF risk (-20pts). Sprint weekends add sprint qualifying + sprint race with sprint-specific overtake estimation (~50% of race bases) and sprint-position-based FL probability.

**Constructors:** Sum of both drivers' qualifying + race pts (excl DOTD) + qualifying teamwork bonus (Both Q3=+10, ..., Neither Q2=-1) + expected pit stop points (analytical CDF over scoring brackets) - DNF impact. Constructor scoring uses **base driver scores only** — never boosted/multiplied values.

**Pit stop scoring brackets:** <2.0s=20pts, 2.0-2.2s=10pts, 2.2-2.5s=5pts, 2.5-3.0s=2pts, 3.0s+=0pts, fastest stop bonus=+5pts.

## Monte Carlo Simulation (08_monte_carlo_fantasy.py)

10,000 iterations per driver. Each iteration: add calibrated noise to model scores → re-rank → sample DNFs (two-stage: multi-car incidents + team-correlated mechanical failures) → sample overtakes → sample fastest lap/DOTD → compute full fantasy points. Noise bases auto-calibrated from `data/seed/mc_calibration.json` (computed by `calibrate_confidence.py`). Output: P5/P25/P50/P75/P95 percentiles.

Constructors simulated per-iteration: sum both drivers' simulated points (with exact per-sim DOTD subtraction) + qualifying bonus + sampled pit stop points. Constructor output includes P5/P25/P75/P95 percentiles.

## Multi-Week Transfer Planner (web/public/app.js)

Plans optimal transfer sequences across 2-5 upcoming rounds using beam search optimization. Future-round scores come from `horizon_projections.json` (priors-only ML predictions written by `predict_horizon.py`) when available, falling back to a confidence-weighted track-affinity heuristic (`base_form × affinity × sprint_multiplier`, affinity blended toward 1.0 by confidence so cold-start picks get a dampened signal instead of being silently defaulted). Beam search (width 60) explores 0/1/2-swap candidates per round — including the new constructor+constructor 2-swap (P12) and a PPM-aware candidate pool (P11) that surfaces cheap high-value picks for budget-relief swaps. Budget propagates across rounds via projected appreciation (P1) so the spending ceiling reflects held-asset value. Three strategies (Max Points, Balanced, Budget Gain) re-rank plans internally but plan totals always display raw net points (P14). Optional "Target Team" mode adds a continuous per-round distance penalty (P3) weighted by a user-selectable **Target Intensity** dropdown (Loose=10 / Balanced=30 / Strict=80, P13). A feasibility card (P2) classifies the target as reachable now / possibly reachable / unreachable before the search runs. Wild Card uses a true brute-force optimal-team search (target-aware); Limitless is a one-round dream team that correctly reverts (P5b). All constants live in `MW_TUNABLES` at the top of the planner section (P10). Plan cards show per-round budget evolution and "vs hold" trade-off lines (P4, P7); heatmap cells flag low-confidence projections (P8). Requires `track_data.json` + `driver_history.json` and optionally `horizon_projections.json` (all exported by pipeline).

## Website Frontend (web/public/app.js)

Single-page vanilla JS app with tab-based navigation. Tabs: Drivers, Constructors, Optimizer, Season, H2H, Accuracy, Deep Dive, Videos, Articles, About.

Key features:
- **Driver/Constructor cards** with predicted points, MC confidence intervals, price change brackets, scoring breakdowns
- **Lineup optimizer** — brute-force over C(22,5)xC(11,2)=1.4M combinations. 4 strategies (Max Points, Max Value, Budget Builder, Balanced). Lock/exclude picks (left-click to lock, right-click to exclude).
- **6 chips:** Limitless (no budget cap), 3x Boost (best driver 3x + second-best 2x), Wild Card (unlimited transfers), No Negative (negatives become 0), Autopilot (auto 2x on best), Final Fix (post-quali changes)
- **Transfer Advisor** — given current team + budget + free transfers + max extra transfers (0-2), finds optimal swaps respecting locked/excluded picks. Shows expected price change for each recommendation. Filters out transfers worse than keeping current team.
- **Multi-Week Transfer Planner** — beam search (width 60) over 2-5 upcoming rounds. Future-round scores from `horizon_projections.json` (priors-only ML) or confidence-weighted track-affinity fallback. Propagates budget across rounds, plans optimal transfers + chip deployment, supports target-team mode with Loose/Balanced/Strict intensity and feasibility classification
- **Price change prediction** — PPM rating system (Great/Good/Poor/Terrible) with A-tier (>$18.5M) and B-tier brackets
- **Season Overview** — championship standings, driver and constructor price trackers, cumulative fantasy standings
- **Accuracy dashboard** — per-round and per-driver MAE, scatter plots, 90% CI and 50% CI coverage metrics
- **Lazy tab loading** — only active tab loads its data

## Data Flow

```
APIs (FastF1, Jolpica, OpenF1, Open-Meteo)
  → Raw data (parquets, JSON)
  → Feature engineering (two-layer merge)
  → ML prediction (XGBRanker)
  → Fantasy scoring (deterministic)
  → Monte Carlo simulation (10K sims)
  → JSON export (08_export_website_json.py)
  → web/public/data/*.json
  → git push → GitHub → Vercel → boxboxf1fantasy.com
```

## Running the Pipeline

```bash
# Full weekend automation — pick the right phase for what's happened on track:
python pipeline/run_weekend.py --phase pre_fp_predict --round N   # Before FP1 — priors-only predictions
python pipeline/run_weekend.py --phase post_fp        --round N   # FP1 (sprint) or FP1+FP2+FP3 (regular) done
python pipeline/run_weekend.py --phase post_quali     --round N   # Sat/Sun qualifying done
python pipeline/run_weekend.py --phase post_race      --round N   # race done

# What pre_fp_predict runs (priors only, before any FP telemetry):
#   01_download_data → 03a_normalize_jolpica → 03b_build_jolpica_features →
#   06_run_predictions → 07_calculate_fantasy → 08_monte_carlo_fantasy →
#   08_export_website_json → predict_horizon (optional, non-fatal)
# (06_run_predictions falls back to "priors only" path when no FP features exist;
# Layer-2 telemetry features are NaN and XGBoost handles them natively.)
#
# What post_fp / post_quali runs:
#   01_download_data → 02_build_laps → 03_extract_features →
#   06_run_predictions → 07_calculate_fantasy → 08_monte_carlo_fantasy →
#   10_fp_analysis → 08_export_website_json → predict_horizon (optional, non-fatal)
#
# What post_race runs:
#   01_download_data → 09_post_race_analysis → 11_actual_fantasy_points →
#   11_race_deep_dive → 12_count_overtakes → 13_fetch_openf1_overtakes →
#   13_fetch_pitstop_stationary → 08_export_website_json
# (Jolpica/Ergast typically publishes results within a few hours of the race;
# if results.json is empty, wait and re-run.)

# Or individual steps:
python pipeline/01_download_data.py --round N
python pipeline/03_extract_features.py --round N
python pipeline/06_run_predictions.py --round N
python pipeline/07_calculate_fantasy.py --round N
python pipeline/08_monte_carlo_fantasy.py --round N
python pipeline/08_export_website_json.py --round N

# Calibration (run after adding actual results for completed rounds)
python pipeline/calibrate_confidence.py
```

## Seed Data Updates

Before each round, update `data/seed/fantasy_prices.json` with current F1 Fantasy prices. After each round, update `data/seed/official_fantasy_points.json` with official points if available. The `price_history` object in `fantasy_prices.json` tracks prices after each round for the price tracker feature.

## Key Config Files

- `config/settings.py` — All paths (`DATA_DIR`, `PREDICTIONS_DIR`, `WEB_DATA_DIR`, etc.), season constants, feature column lists, sprint/cancelled rounds
- `config/fantasy_scoring.py` — Every scoring rule: position points, overtakes, fastest lap, DOTD, DNF penalties, constructor bonuses, pit stop brackets
- `config/track_classifications.py` — Per-circuit 9D feature vectors (downforce, overtaking difficulty, safety car probability, etc.)

## Common Tasks

| Task | How |
|------|-----|
| Add a new round's predictions | `python pipeline/run_weekend.py --round N` then `python pipeline/08_export_website_json.py --round N` |
| Update prices | Edit `data/seed/fantasy_prices.json`, add entry to `price_history` |
| Retrain models | `python pipeline/05_train_models.py` (uses all historical data) |
| Add official fantasy points | Edit `data/seed/official_fantasy_points.json`, run export |
| Recalibrate MC intervals | `python pipeline/calibrate_confidence.py` (after adding actual results) |
| Deploy to website | `git add`, `git commit`, `git push` (Vercel auto-deploys) |
| Run local dev server | `python web/serve.py` (port 3000) |
| Run Streamlit dashboard | `streamlit run dashboard/app.py` |

## Important Conventions

- Pipeline scripts are numbered (01-13) and run sequentially
- All rolling features use `.shift(1)` to prevent data leakage
- Constructor scoring never includes driver boost multipliers (2x/3x)
- DNF probability is blended: historical rolling 5-race rate + current season actuals, dynamically weighted
- Price data in `fantasy_prices.json` has both `drivers` and `constructors` sections, plus `price_history` keyed by round number
- Cache version in `index.html` (`app.js?v=N`) must be bumped when `app.js` changes
- The website has no build step — edit `web/public/app.js` and `web/public/styles.css` directly
- **Calendar mapping is mandatory at every FastF1 boundary.** Always wrap `fastf1.get_session(year, round, ...)` calls with `fastf1_round(round, year)` from `config.settings`. Without it, cancelled-round offsets cause silently wrong sessions to load (e.g. internal R6 = Miami → FastF1 R6 = Monaco).
- **Sprint quali laps are saved separately** as `data/processed/laps/round{N}/all_laps_sprint_qualifying.parquet`. They are consumed only by `10_fp_analysis.py` (Deep Dive page). Model feature extraction (`03_extract_features.py`) only globs `all_laps_fp*.parquet`, keeping FP-only training inputs.
- **Sprint quali grid in 06_run_predictions.py:** Ergast doesn't expose Sprint Qualifying results, so FastF1's `Position`/`Q1`-`Q3` fields are NaN. The loader falls back to ranking by each driver's fastest lap when the official Position field is empty. This populates `sprint_grid` and switches inference from `sprint_model_fp.json` to `sprint_model.json`.
- **Jolpica/Ergast lag:** Race and sprint results typically publish a few hours after the session. If `data/raw/jolpica/year{Y}/round{N}/results.json` returns `Races: []`, wait and re-run `post_race`. FastF1-derived outputs (race pace, tyre management, overtakes, FP analysis) populate independently of Jolpica.
- **Race-completed guards:** `06_run_predictions.py`, `07_calculate_fantasy.py`, `08_monte_carlo_fantasy.py`, and `08_export_website_json.py` all refuse to overwrite outputs for already-completed rounds. Pass `--force` to override. This prevents accuracy-archive pollution from the model "predicting" a round it has already been trained on. See `config.settings.is_race_completed`.
- **Live-file downgrade guard in `08_export_website_json.py`:** Separate from the race-completed guard. Refuses to overwrite `web/public/data/predictions.json` (the homepage-facing current-round file) when the round being exported is OLDER than the round currently in the live file. This guards against the subtle bug where you run `--round 6` to refresh post-race derived data (e.g. pit stops) and accidentally clobber the live file that was already showing R7. Phase archive + canonical archive still get written (they have their own guards). Pass `--force` to override.
- **Phase-tagged archives:** Each weekend phase writes `predictions_round{N}_{phase}.json` (pre_fp/post_fp/post_quali) in addition to the canonical `predictions_round{N}.json`. `run_weekend.py` passes `--phase` to the exporter explicitly; standalone exports auto-detect from the sidecar. The accuracy tab uses these phase archives to show how the forecast improved as data arrived during the weekend.
- **prediction_metadata.json sidecar (source of truth for phase):** `06_run_predictions.py` writes `data/predictions/round{N}/prediction_metadata.json` recording the phase it actually ran in, the model SHA-256 hashes, and the flags. `detect_phase` in `08_export_website_json.py` reads this as the authoritative phase label, falling back to data-state inference only when the sidecar is missing. Backfill with `python pipeline/backfill_sidecars.py` for legacy rounds.
- **Append-only audit log (`data/audit/`):** Every `08_export_website_json.py` run appends one line to `data/audit/predictions_log.jsonl` and writes an immutable full snapshot to `data/audit/snapshots/round{N}/{ISO}_{phase}.json`. Filenames are timestamped, never reused. Use to (a) recover from corrupted archives — `jq '.predictions' snapshot.json > predictions_round{N}.json` — and (b) query prediction history by round/phase/model-hash. Library: `pipeline/audit.py`. Re-seed with `python pipeline/backfill_audit.py`.
- **Recovery script:** `pipeline/recover_archives.py --rounds 1,2,3` walks-forward retrains models with `--exclude-after 2026:{N}` for each polluted round, re-predicts with the leak-free model, and writes both `_pre_fp` and `_post_fp` archives flagged `reconstructed: true`. Used to rebuild the rounds 1/2/3 archives that were polluted before the guards existed (May 2026). WARNING: replaces the trained model on disk; retrain with full dataset afterwards.
- **Git restore points:** Trained models (`models/trained/*.json` + `fp_signal_model.pkl`), the historical baseline (`models/trained_v1_baseline/`), and feature data (`data/processed/jolpica/model_rows/*.parquet`) are tracked in git so a clean clone can predict without retraining. Named tags `backup/pre-audit-system` and `backup/post-audit-system` mark known-good revert points on the remote.
- **Stale-price guard in `08_export_website_json.py`:** Prints a loud `!!!!!`-banner warning if `data/seed/fantasy_prices.json::price_history` has fewer entries than there are completed races. Stale prices silently break price-change brackets, PPM ratings, value scores, and the optimizer's `budget_gain` strategy. After every race, update `fantasy_prices.json` (add new `price_history.{N}` entry, bump every `current_price`, update `last_updated` + `price_after_round`) BEFORE running `post_race` or any future prediction phase.
- **Donation links:** Ko-fi + PayPal anchor links are hard-coded in `web/public/index.html` (footer + About tab "Support BoxBox" card). Currently `https://ko-fi.com/boxboxf1fantasy` and `https://paypal.me/boxboxf1fantasy`. No backend, no third-party widgets — plain `<a target="_blank">` tags. To change them, edit both copies in `index.html` to stay in sync. Styles in `styles.css` under `Footer support links` / `About tab support card` comments.
- **Horizon projections for multi-week planner (P9):** `pipeline/predict_horizon.py` runs priors-only ML predictions for upcoming rounds and exports `web/public/data/horizon_projections.json`. The multi-week planner's `projectScoresForRound()` in `app.js` prefers this ML projection over the older track-similarity heuristic (heuristic remains as fallback when JSON is missing or doesn't cover a pick). Should be re-run on each `post_fp` / `post_quali` cycle (whenever current-round predictions change, future-round projections also need refreshing). Underlying per-round parquets land in `data/predictions/round{N}/predictions_horizon.parquet` (suffix `horizon` keeps them isolated from the canonical `predictions.parquet`); the race-completed guard in `06_run_predictions.py` is intentionally bypassed for suffixed runs. Cadillac drivers and other zero-history picks now get real ML signal here instead of the affinity-defaulted 1.0 they used to get.
- **Pit stop counts vs scoring:** OpenF1 sometimes returns `stop_duration` as null (SC/VSC stops, retirements, drive-throughs, sensor dropouts) but with `lane_duration` populated. `13_fetch_openf1_overtakes.py::fetch_pitstop_times` saves every record with either timing — flagging `stationary_missing: true` when stop_duration is null — and `13_fetch_pitstop_stationary.py` propagates that flag into `pitstops_round{N}.json` as `{lap, stationary, lane, stationary_missing}`. Constructor pit stop SCORING (`11_actual_fantasy_points.py::load_openf1_pitstops`) filters out null-stationary stops (can't score what wasn't measured), but the website display counts ALL stops, rendering missing-stationary ones as "n/a". Do not "estimate" missing stationary times from lane_duration — the user explicitly wants real data only, with transparent flagging when it's missing.
