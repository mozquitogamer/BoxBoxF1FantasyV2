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

Plans optimal transfer sequences across 2-5 upcoming rounds using beam search optimization. Since ML predictions only exist for the current round, future rounds use track-similarity-weighted historical performance as score projections (`base_form × track_affinity × sprint_multiplier`). Track affinity comes from cosine similarity between circuit 9D feature vectors (similarity > 0.7 threshold, clamped 0.6-1.4). Beam search (width 60) explores 0-2 swaps per round with transfer banking (max 5), -10pts/extra transfer penalty, and chip deployment. Three strategies: Max Points, Balanced, Budget Gain. Optional "Target Team" mode steers the planner toward a user-defined dream team. Team evolution view shows full roster per round with new/held badges and projected points. Requires `track_data.json` and `driver_history.json` (exported by `08_export_website_json.py`).

## Website Frontend (web/public/app.js)

Single-page vanilla JS app with tab-based navigation. Tabs: Drivers, Constructors, Optimizer, Season, H2H, Accuracy, Deep Dive, Videos, Articles, About.

Key features:
- **Driver/Constructor cards** with predicted points, MC confidence intervals, price change brackets, scoring breakdowns
- **Lineup optimizer** — brute-force over C(22,5)xC(11,2)=1.4M combinations. 4 strategies (Max Points, Max Value, Budget Builder, Balanced). Lock/exclude picks (left-click to lock, right-click to exclude).
- **6 chips:** Limitless (no budget cap), 3x Boost (best driver 3x + second-best 2x), Wild Card (unlimited transfers), No Negative (negatives become 0), Autopilot (auto 2x on best), Final Fix (post-quali changes)
- **Transfer Advisor** — given current team + budget + free transfers + max extra transfers (0-2), finds optimal swaps respecting locked/excluded picks. Shows expected price change for each recommendation. Filters out transfers worse than keeping current team.
- **Multi-Week Transfer Planner** — beam search (width 60) over 2-5 upcoming rounds, projects scores using track-similarity-weighted historical performance, plans optimal transfer sequences with chip deployment
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
python pipeline/run_weekend.py --phase post_fp    --round N   # FP1 (sprint) or FP1+FP2+FP3 (regular) done
python pipeline/run_weekend.py --phase post_quali --round N   # Sat/Sun qualifying done
python pipeline/run_weekend.py --phase post_race  --round N   # race done

# What each phase runs (post_fp / post_quali):
#   01_download_data → 02_build_laps → 03_extract_features →
#   06_run_predictions → 07_calculate_fantasy → 08_monte_carlo_fantasy →
#   10_fp_analysis → 08_export_website_json
#
# What post_race runs:
#   01_download_data → 09_post_race_analysis → 11_actual_fantasy_points →
#   12_count_overtakes → 13_fetch_openf1_overtakes → 08_export_website_json
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
