# BoxBoxF1Fantasy — Technical Deep Dive

**Architecture and design rationale.** Read this when you need to understand *why* something is the way it is, or when modifying the pipeline.

For *how to operate* the system day-to-day (run phases, CLI args, troubleshooting), see [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md).
For end-user UI documentation, see [USER_GUIDE.md](USER_GUIDE.md). For a narrated walkthrough / ready-to-record video script, see [SITE_TUTORIAL.md](SITE_TUTORIAL.md).

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Repository Layout](#2-repository-layout)
3. [Data Sources](#3-data-sources)
4. [The 2026 Calendar Mapping](#4-the-2026-calendar-mapping)
5. [The Two-Layer Feature System](#5-the-two-layer-feature-system)
6. [Machine Learning Models](#6-machine-learning-models)
7. [Phase-Aware Inference](#7-phase-aware-inference)
8. [Predict-Time Feature Recomputation](#8-predict-time-feature-recomputation)
9. [Fantasy Scoring Engine](#9-fantasy-scoring-engine)
10. [Monte Carlo Simulation](#10-monte-carlo-simulation)
11. [Overtake Estimation](#11-overtake-estimation)
12. [Risk & Confidence System](#12-risk--confidence-system)
13. [Price Change Prediction](#13-price-change-prediction)
14. [Lineup Optimizer](#14-lineup-optimizer)
15. [Multi-Week Transfer Planner](#15-multi-week-transfer-planner)
16. [Confidence Interval Calibration](#16-confidence-interval-calibration)
17. [Website Architecture](#17-website-architecture)
18. [Known Limitations](#18-known-limitations)
19. [Future Feature Ideas](#19-future-feature-ideas)

---

## 1. System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          DATA COLLECTION                                  │
│  FastF1 (telemetry)    Jolpica/Ergast (results)    OpenF1 (overtakes)    │
│       │                       │                           │              │
└───────┼───────────────────────┼───────────────────────────┼──────────────┘
        │                       │                           │
        ▼                       ▼                           │
┌──────────────────────┬──────────────────────────┐         │
│  Layer 1: Jolpica    │  Layer 2: FP Telemetry   │         │
│  priors (91 cols,    │  (40+ cols, sparse —     │         │
│  always present)     │  ~160/2,679 rows have    │         │
│                      │  data in training)       │         │
└──────────┬───────────┴──────────┬───────────────┘         │
           │                      │                         │
           └──────────┬───────────┘                         │
                      ▼                                     │
            ┌──────────────────┐                            │
            │  Merged dataset  │                            │
            │  ~2,679 rows     │                            │
            │  XGBoost native  │                            │
            │  NaN handling    │                            │
            └────────┬─────────┘                            │
                     │                                      │
                     ▼                                      │
┌─────────────────────────────────────────────────┐         │
│                ML PREDICTIONS                   │         │
│                                                 │         │
│  Quali Model      Race Models (2)   Sprint     │         │
│  XGBRanker        XGBRanker          XGBRanker │         │
│  85 features      101 features       107 feats │         │
│  1200 trees       650 trees          400 trees │         │
│  depth=3          depth=5            depth=4   │         │
│                                                 │         │
│  Phase-aware: race_model.json (post-quali)      │         │
│  vs race_model_fp.json (post-FP, pre-quali)     │         │
└────────────────────────┬────────────────────────┘         │
                         │                                  │
                         ▼                                  │
┌─────────────────────────────────────────────────┐         │
│                FANTASY SCORING                  │         │
│   Predicted positions → Fantasy points          │         │
│   + Overtake estimation ◄───────────────────────┼─────────┘
│   + DNF risk + FL prob + DOTD prob              │
│   + Sprint scoring (sprint weekends)            │
│   + Constructor aggregation + pit stops         │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│            MONTE CARLO SIMULATION               │
│   10,000 simulations per driver                 │
│   → P5/P25/P50/P75/P95 percentiles              │
│   → DNF + overtake + FL + DOTD sampling         │
│   → Constructor pit-stop simulation             │
│   → Calibrated noise from mc_calibration.json   │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│              JSON EXPORT → Vercel               │
│   web/public/data/*.json → boxboxf1fantasy.com  │
└─────────────────────────────────────────────────┘
```

The pipeline is a **directed sequence of numbered Python scripts** (01 through 13) plus a few unnumbered utilities. Each script reads from upstream artifacts (parquets, JSON) and writes to downstream artifacts. Nothing in the pipeline is interactive at runtime — `pipeline/run_weekend.py` orchestrates the right subset of scripts for each weekend phase.

---

## 2. Repository Layout

```
BoxBoxF1FantasyV2/
├── pipeline/                       # Numbered Python scripts + utilities
│   ├── 01_download_data.py         # FastF1 + Jolpica downloader
│   ├── 02_build_laps.py            # Raw → cleaned lap parquets (FP1+SQ on sprint, FP1/2/3 otherwise)
│   ├── 03_extract_features.py      # FP telemetry features (40+ cols, sparse)
│   ├── 03a_normalize_jolpica.py    # Raw Jolpica JSON → normalized CSVs
│   ├── 03b_build_jolpica_features.py # Layer-1 rolling features (91 cols)
│   ├── 04_build_model_inputs.py    # Merge Layer 1 + Layer 2 → training_data.parquet
│   ├── 05_train_models.py          # Train 5 models (quali, race, race_fp, sprint, fp_signal)
│   ├── validate_model_config.py     # 97-fold walk-forward config validator (research gate)
│   ├── 06_run_predictions.py       # Inference (phase-aware, recomputes circuit/sim features)
│   ├── 07_calculate_fantasy.py     # Fantasy points (deterministic)
│   ├── 08_monte_carlo_fantasy.py   # 10K-iteration MC
│   ├── 08_export_website_json.py   # Parquets → JSON for website
│   ├── 09_post_race_analysis.py    # Predicted vs actual comparison
│   ├── 10_fp_analysis.py           # FP & sprint quali analytics (Race Deep Dive page)
│   ├── 11_actual_fantasy_points.py # Real fantasy points from race results (uses overtakes.csv override)
│   ├── 11_race_deep_dive.py        # Detailed race analysis (pace, tyre, stints, fuel-corrected)
│   ├── 12_count_overtakes.py       # FastF1 sector-method overtake detection
│   ├── 12_official_fantasy_points.py # CLI manager for official_fantasy_points.json
│   ├── 13_fetch_openf1_overtakes.py # OpenF1 API overtake counts (filters pit stops)
│   ├── 13_fetch_pitstop_stationary.py # Pit stop stationary times (the actual scoring metric)
│   ├── calibrate_confidence.py     # MC interval calibration (MC predictions vs actuals)
│   ├── run_weekend.py              # Phase orchestrator (pre_fp / pre_fp_predict / post_fp / post_quali / post_race)
│   ├── weather_forecast.py         # Open-Meteo forecasts
│   ├── feature_engineering.py      # Cross-layer engineered features (library, no CLI)
│   ├── build_articles.py           # Articles JSON builder
│   ├── youtube_videos.py           # Video curation
│   ├── download_helper.py          # Programmatic download wrapper
│   └── download_fp_missing.py      # Backfill missing FP sessions
├── config/
│   ├── settings.py                 # All paths, season constants, FEATURE_COLUMNS, fastf1_round() helper
│   ├── fantasy_scoring.py          # 2026 official scoring rules (lookup tables, brackets)
│   ├── track_classifications.py    # 9-dim circuit feature vectors (TRACK_DATABASE) + race-name mapping
│   ├── track_similarity.py         # Cosine similarity over 9D vectors
│   ├── team_driver_ratings.py      # Manual skill ratings (tyre management, overtaking, wet, etc.)
│   └── circuit_coordinates.py      # Track GPS for weather lookup
├── data/
│   ├── raw/
│   │   ├── fastf1/year{Y}/round{R}/   # FP/race/quali/sprint parquets
│   │   └── jolpica/year{Y}/round{R}/  # results, qualifying, sprint, pitstops JSON
│   ├── processed/
│   │   ├── laps/round{N}/             # all_laps_fp{1,2,3}.parquet (+ sprint_qualifying on sprint weekends)
│   │   ├── features/round{N}/         # FP feature parquets
│   │   ├── jolpica/
│   │   │   ├── normalized/{year}/     # CSVs from 03a
│   │   │   └── model_rows/            # all_model_rows.parquet (Layer-1 features for 2020-2026)
│   │   ├── model_inputs/              # training_data.parquet
│   │   ├── deep_dive/round{N}/        # Race deep dive JSON
│   │   ├── fp_analysis/round{N}/      # FP analysis JSON
│   │   ├── pitstops/year{Y}/round{N}/ # Pit stop stationary times
│   │   └── post_race/                 # Predicted vs actual JSON
│   ├── predictions/round{N}/          # predictions.parquet, fantasy_points.parquet, MC outputs
│   ├── actuals/round{N}/              # actual_fantasy.parquet (from script 11)
│   ├── overtakes/year{Y}/round{N}/    # overtakes.json (OpenF1 + FastF1 detection results)
│   └── seed/                          # Manually-maintained reference data (see OPERATIONS_GUIDE §10)
├── models/
│   ├── trained/                       # Production XGBoost models (.json)
│   │   ├── quali_model.json
│   │   ├── race_model.json            # Trained on actual quali — used in post-quali phase
│   │   ├── race_model_fp.json         # Trained on walk-forward predicted quali — used in post-FP phase
│   │   ├── sprint_model.json
│   │   ├── fp_signal_model.pkl        # ExtraTreesRegressor (confidence only)
│   │   ├── feature_columns.json       # Feature lists per model (quali=85, race=101, sprint=107)
│   │   └── model_metadata.json        # Training timestamp, row counts, val metrics
│   └── trained_v1_baseline/           # Legacy XGBRegressor models (kept for reference)
├── web/
│   ├── public/
│   │   ├── index.html                 # SPA shell (cache version: app.js?v=N)
│   │   ├── app.js                     # All frontend logic (~7,800 lines)
│   │   ├── styles.css                 # CSS with custom properties for theming
│   │   ├── articles/*.md              # Article content
│   │   └── data/*.json                # All website data (predictions, actuals, etc.)
│   └── serve.py                       # Local dev server (port 3000)
├── docs/
│   ├── OPERATIONS_GUIDE.md            # ← How to run the system
│   ├── TECHNICAL_DEEP_DIVE.md         # ← This file
│   ├── SYSTEM_DIAGRAM.md              # Visual diagrams
│   ├── USER_GUIDE.md                  # End-user UI documentation
│   └── pipeline_improvement_plan.md
├── dashboard/                         # Streamlit analytics dashboard (internal use)
├── .github/workflows/
│   └── weather-update.yml             # Automated weather forecast every 6 hours
├── vercel.json                        # Vercel deployment config
├── requirements.txt                   # Python dependencies
└── CLAUDE.md                          # AI-agent context file (system overview)
```

---

## 3. Data Sources

### FastF1 (Free Practice + Race Telemetry)

- **What:** Lap-by-lap timing data from FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race, and Race sessions. Also race results when available.
- **Why:** Free practice is the only real-world data we have *before* qualifying. Tells us the actual pace of each car this weekend.
- **Coverage:** Lap times, sector times (3 sectors), tyre compound, pit in/out flags, deleted-lap flags, weather conditions.
- **Latency:** ~30 minutes after session ends.
- **Calendar quirk:** FastF1's 2026 calendar omits cancelled rounds (Bahrain R4, Saudi R5). Always use `fastf1_round(internal_round, year)` from `config/settings.py` before any `fastf1.get_session(...)` call.
- **Limitations:** Teams sandbag in FP. Mitigated partially by emphasizing consistency, long-run pace, and compound-relative deltas.

### Jolpica/Ergast (Historical Results)

- **What:** Race results, qualifying results, standings, pit stops for every F1 race since 1950. Successor to the discontinued Ergast API.
- **Why:** Historical performance is the backbone of predictions. A driver's rolling 3-5 race average is one of the strongest predictors of future performance.
- **Coverage:** Finishing positions, grid positions, lap counts, pit stops (count + duration), constructor results, standings.
- **Why not FastF1 for history?** FastF1 telemetry is reliably available only from ~2019. Jolpica gives structured result data going back decades. We train on 2020-2026.
- **Calendar quirk:** Same as FastF1 — Jolpica/Ergast also omits cancelled rounds. The `download_jolpica_round` function in `01_download_data.py` translates internal → API numbering at the request URL while preserving internal numbering in file paths.
- **Latency:** Race results typically publish within a few hours of the chequered flag, but sprint sometimes lags longer. Sprint Qualifying Position/Q1-Q3 fields are NOT exposed (see §6 Sprint Model).

### OpenF1 API (Overtake Counts)

- **What:** Position-tracking data from official F1 timing.
- **Why:** Overtakes = +1 fantasy point each. Important and hard to predict.
- **Coverage:** Per-driver overtake counts per session.
- **Latency:** ~1-2 hours after race.
- **Limitations:** Slightly overcounts due to pit stop position changes. The 30-second window filter in `13_fetch_openf1_overtakes.py` removes most. Official F1 Fantasy counts are still typically lower — when official counts are known, they're entered manually into `data/seed/overtakes.csv` and override detected counts via `load_seed_overtakes()` in `11_actual_fantasy_points.py`.

### Open-Meteo (Weather Forecasts)

- **What:** Per-session rain probability, temperature, wind speed.
- **Why:** Wet/dry can flip race outcomes. Used for the weather widget on the website.
- **Latency:** Real-time forecast API. Auto-updated every 6 hours via GitHub Actions.

### Manual / Seed Data

- **What:** Fantasy prices, official points, DOTD winners, overtake corrections, calendar.
- **Why:** Some data has no API source — F1 Fantasy prices and official overtake counts need manual entry.

---

## 4. The 2026 Calendar Mapping

This is the single most error-prone part of the codebase, so it deserves its own section.

### The Setup

`data/seed/races.json` preserves *original* 2026 numbering: 24 races, with `round: 4` (Bahrain) and `round: 5` (Saudi Arabian) marked `cancelled: true`.

### The Problem

**Both FastF1 AND Jolpica/Ergast omit cancelled races from their numbering.** Their 2026 calendars are 22 races, not 24. So:

| Race | Internal round | FastF1/Jolpica round |
|------|---------------|----------------------|
| Australia | 1 | 1 |
| China | 2 | 2 |
| Japan | 3 | 3 |
| Bahrain | 4 (cancelled) | — |
| Saudi | 5 (cancelled) | — |
| Miami | 6 | 4 |
| Canada | 7 | 5 |
| Monaco | 8 | 6 |
| ... | ... | ... |

### The Fix

`config/settings.py::fastf1_round(internal_round, year)` returns the external round number. It subtracts the count of cancelled rounds *strictly before* the target.

```python
def fastf1_round(internal_round: int, year: int = CURRENT_SEASON) -> int:
    if year != 2026:
        return internal_round
    skipped = sum(1 for r in CANCELLED_ROUNDS_2026 if r < internal_round)
    return internal_round - skipped
```

### Where it's used

Mandatory at every external API boundary:
- **FastF1:** `01_download_data.py`, `02_build_laps.py`, `06_run_predictions.py`, `12_count_overtakes.py`, `11_race_deep_dive.py`, etc.
- **Jolpica:** `01_download_data.py::download_jolpica_round()`. The internal round is used for the file path (`data/raw/jolpica/year2026/round6/`) but the URL uses the translated round (`2026/4/results.json`).

### Why we keep internal numbering everywhere else

1. **Consistency with the seed `races.json`** — original 2026 schedule preservation.
2. **Logging legibility** — humans recognize "Miami" as round 6, not round 4.
3. **Future-proofing** — if F1 retroactively reinstates a round, the schedule entries don't shift.
4. **Audit trail** — file paths preserve which race the data is *for*, regardless of API quirks.

The cost: every external API boundary needs the translation. Skipping it leads to:
- FastF1 silently loading the wrong race (e.g. requesting `(2026, 6, 'Race')` returns Monaco, not Miami)
- Jolpica returning empty `Races: []` (their round 6 hasn't run yet — only 4 races in their numbering)

---

## 5. The Two-Layer Feature System

The core architectural decision. Understanding this is key to understanding everything downstream.

### The Problem

We have two very different data sources:

1. **Historical (Jolpica):** Available for every race 2020-2026. Always present at prediction time. Total: ~2,679 rows in training.
2. **FP telemetry (FastF1):** Only available for ~160 of those rows in training (most pre-2023 races don't have parsable FP telemetry in our processing pipeline). Available at prediction time IF we run after FP sessions.

A model trained only on FP telemetry has ~160 training samples — not enough.
A model trained only on historicals misses the "how fast is the car *this weekend*" signal.

### The Solution: Two Layers, One Merged Dataset

#### Layer 1 — Jolpica Priors (always populated, ~91 columns)

Rolling stats with `.shift(1)` to prevent leakage:
- **Driver rolling avg:** quali_last, quali_roll_3, quali_roll_5 (per-driver)
- **Race rolling avg:** roll_finishpos_3, roll_finishpos_5
- **Points rolling:** roll_points_3, roll_points_5
- **Sim-weighted rolling:** sim_weighted_quali_3/5, sim_weighted_finishpos_3/5, sim_weighted_points_3/5 (track-similarity weighted; recomputed per target circuit at predict time — see §8)
- **Constructor stats:** constructor_quali_last, constructor_roll_quali_3/5, constructor_season_avg
- **Teammate delta:** team_delta_last, team_delta_roll_3/5
- **Circuit experience:** driver_circuit_exp, driver_circuit_roll_3, constructor_circuit_exp (recomputed per target circuit at predict time — see §8)
- **DNF rates:** roll_dnf_rate_5, roll_mech_dnf_rate_5_driver, roll_mech_dnf_rate_5_constructor, roll_collision_dnf_rate_5_driver, roll_drivererror_dnf_rate_5_driver
- **Form trend:** form_trend, hot_streak indicators
- **Track features (9D):** is_street, overtaking_difficulty, avg_corner_speed, straight_line_importance, downforce_level, turn1_incident_risk, safety_car_probability, track_evolution, grip_level
- **Skill ratings:** tyre_management, wet_weather, overtaking, team_strategy (manual from `team_driver_ratings.py`)
- **Race-model only:** is_pole_position, is_front_row, is_top10_quali, grid_advantage (depend on `quali_position` — known at race-prediction time)

Built in `pipeline/03b_build_jolpica_features.py`.

#### Layer 2 — FP Telemetry (sparse, 40+ columns)

- **Pace:** avg_lap_time, best_lap_time, median_lap_time, best_3_lap_avg, best_5_lap_avg, best_10_lap_avg, p50_to_p95_avg
- **Consistency:** lap_time_std, lap_time_variance, coefficient of variation
- **Degradation:** degradation_rate (linear regression slope across longest stint)
- **Long run / short run:** long_run_avg, long_run_rank, short_run_best
- **Sectors:** avg_sector_{1,2,3}, best_sector_{1,2,3}
- **Compound-specific:** soft_best_lap, soft_avg_lap, medium_long_run_avg, hard_long_run_avg, medium_degradation, hard_degradation — separates qualifying-sim pace (soft) from race-sim pace (medium/hard)
- **Pace deltas:** pace_delta_to_fastest, pace_delta_to_median, race_pace_delta_to_median, sector_N_delta_to_fastest, long_run_delta_to_median — **circuit-portable** features (a 0.5s gap means the same at Monaco and Monza)

Built in `pipeline/03_extract_features.py`. Features extracted **only** from `all_laps_fp*.parquet`. Sprint qualifying laps are saved separately (`all_laps_sprint_qualifying.parquet`) and feed only the Race Deep Dive page (`10_fp_analysis.py`), not model training.

#### Engineered cross-layer features

In `pipeline/feature_engineering.py`, applied at predict time:
- `prior_vs_fp_rank`: Gap between Jolpica prior quali rank and FP pace rank. If history says "P5" but FP says "P2", that's a strong signal of weekend-specific improvement.
- `soft_medium_gap`, `medium_hard_gap`, `soft_vs_overall_best`: Compound interaction features capturing quali-vs-race tradeoffs.

### Why XGBoost Handles This Perfectly

XGBoost's `tree_method="hist"` handles NaN natively. When a Layer-2 feature is NaN (no FP data for that historical row), XGBoost learns a default split direction. So:
- During training on 2020-2024 rows without FP data, XGBoost relies on Layer-1 priors.
- When FP data IS present (some 2024 rows, all 2026 post-FP rows), XGBoost can use it to refine.
- **No imputation needed. No two separate models needed.**

### Why `.shift(1)` Matters

All rolling features use `.shift(1)` — the current race's result is NOT included in its own features. This prevents data leakage. When computing "driver's rolling 3-race average" for Round 5, we use Rounds 2, 3, 4 (not 3, 4, 5).

---

## 6. Machine Learning Models

### Why XGBoost?

We tested LightGBM, Random Forest, CatBoost, Gradient Boosting, ExtraTrees, and stacking/voting ensembles (the evaluation harnesses live in `validate_alt_algorithm.py` / `validate_alt_algo_v2.py` and the 97-fold `validate_model_config.py`). XGBoost won because:

1. **Native NaN handling** — critical for the two-layer system
2. **Strong with sparse features** — Layer 2 is 90%+ NaN in training
3. **Good regularization** — prevents overfitting on 2,679 rows
4. **Fast training** — important for experimentation

### Model Generations

- **V1 baseline:** XGBRegressor with `reg:squarederror`. Treated positions as continuous numbers (P1=1, P22=22). Simple but doesn't capture the nonlinear gap (P1→P2 matters more than P15→P16). Preserved in `models/trained_v1_baseline/` for reference.
- **V2 (current):** XGBRanker with `rank:pairwise` (LambdaMART). Learns to rank drivers *within each race* correctly. Output is relevance scores; positions come from ranking.

### The Five Models

#### Qualifying Model — `quali_model.json`

```python
XGBRanker(n_estimators=1200, learning_rate=0.025, max_depth=3,
          objective="rank:pairwise", subsample=0.85, colsample_bytree=0.85)
```

- **Target:** Relevance labels derived from `qualifying_position` (P1 → label 21, P22 → label 0)
- **Group key:** `(season, round)` — each race is one ranking group
- **Features:** 85 (Layer-1 priors + track features + skill ratings + Layer-2 pace + relative pace deltas)
- **Why depth=3:** Qualifying is relatively predictable from historical data. Shallow trees prevent overfitting.

#### Race Model — `race_model.json` (post-quali phase)

```python
XGBRanker(n_estimators=650, learning_rate=0.03, max_depth=5,
          objective="rank:pairwise", subsample=0.85, colsample_bytree=0.85)
```

- **Target:** Relevance labels from `finish_position` (clean finishers only — DNFs handled separately)
- **Group key:** `(season, round)`. Per-group sample weight: 2.5x for 2026 rows.
- **Features:** 101 (all quali features + grid_advantage + race-specific + compound features). Trained with **actual** `quali_position` as a feature.
- **Why depth=5:** Races have more complex interactions than qualifying — safety cars, strategy, tyre degradation, traffic.
- **Used:** When actual qualifying data is available (post-quali phase).

#### Race-FP Model — `race_model_fp.json` (post-FP phase, before quali)

Same hyperparameters as the race model, **but trained on walk-forward predicted `quali_position`**: each season's quali is predicted by a quali model trained on earlier seasons, and that predicted value is fed into the race model during training.

- **Why two race models?** Eliminates train/inference distribution shift. The original race model was trained on clean actual quali but at post-FP inference time, we feed it noisy *predicted* quali — that's a covariate shift the model wasn't optimized for. The FP variant is trained on the same noisy predicted-quali distribution it sees at inference time.
- **Used:** Post-FP phase, before qualifying happens.
- **Switching logic:** `06_run_predictions.py::_load_actual_quali()` detects whether actual quali exists. If yes → race_model.json. If no → race_model_fp.json.

#### Sprint Model — `sprint_model.json`

```python
XGBRanker(n_estimators=400, learning_rate=0.035, max_depth=4,
          objective="rank:pairwise", reg_lambda=1.5, subsample=0.80, colsample_bytree=0.80)
```

- **Training data:** 501 sprint-only rows (2021-2026). Sprints have different dynamics than full races.
- **Top feature:** `sprint_grid` (importance ~0.032). Derived: `sprint_grid_advantage`, `sprint_is_front_row`, `sprint_is_top3`, `sprint_is_top10`, `quali_to_sprint_grid_delta`.
- **Why lighter regularization:** Smaller dataset (501 rows vs 2,679) — fewer trees, shallower depth, higher learning rate.
- **At prediction time:** Loads actual sprint qualifying results from normalized CSV or FastF1 session. **Critical fallback:** Ergast doesn't expose Sprint Qualifying results (Position/Q1/Q2/Q3 are NaN), so the loader ranks drivers by their fastest SQ lap as the canonical fallback. Falls back to predicted qualifying if sprint qualifying hasn't happened yet.

#### FP Signal Model — `fp_signal_model.pkl`

```python
ExtraTreesRegressor(n_estimators=500, max_depth=6, random_state=42)
```

- **Purpose:** NOT for direct predictions. Used **only** for confidence scoring.
- **How:** Measures how much FP pace data alone can predict race outcomes. When this model agrees with the XGBoost models, confidence is higher.
- **Why ExtraTrees:** More robust to noise on the smaller FP-only dataset.

### Walk-Forward Validation

F1 data is time-series — using 2024 to predict 2022 would be cheating (regulations change, teams evolve, drivers switch). Walk-forward respects this:

```
Fold 1: Train [2020-2021] → Test 2022
Fold 2: Train [2020-2022] → Test 2023
Fold 3: Train [2020-2023] → Test 2024
Fold 4: Train [2020-2024] → Test 2025
Fold 5: Train [2020-2025] → Test 2026
```

For the race-FP model specifically, the walk-forward also includes a *nested* walk-forward to generate the predicted-quali feature for each season.

### Sample Weighting

2026 has new regulations (ground effect changes, new tyres, new aero). Data from 2020-2025 under old regulations is still useful (driver skill, track characteristics persist) but less relevant. We weight 2026 rows **2.5x** in training (`config/settings.py::REGULATION_WEIGHT_MULTIPLIER`). For XGBRanker, weights must be per-group (one weight per race, applied to all 22 driver rows in that race).

---

## 7. Phase-Aware Inference

`pipeline/06_run_predictions.py` is the entry point for prediction. Its phase awareness is what lets the pipeline serve `pre_fp_predict`, `post_fp`, and `post_quali` from the same script.

### Detection

```python
actual_quali = _load_actual_quali(year, round_num, abbrev_to_jolpica)
phase = "post-quali" if actual_quali else "post-FP"
race_model_path = "race_model.json" if actual_quali else "race_model_fp.json"
```

`_load_actual_quali()` checks two sources in order:
1. Normalized Jolpica CSV: `data/processed/jolpica/normalized/{year}/qualifying_results.csv`
2. FastF1 qualifying session (loaded with telemetry off for speed)

### Pre-FP path

If neither FP features nor actual quali exist, the script:
1. Loads `data/processed/features/round{N}/features.parquet` if present (it won't be in pre-FP).
2. Falls back to "priors only" — Layer-2 columns in the feature DataFrame are all NaN.
3. Uses `race_model_fp.json` (since no quali exists).
4. XGBoost handles NaN natively — no failure.

### Post-FP path

1. FP features parquet exists → merged in.
2. No actual quali → uses `race_model_fp.json`.
3. Predicted quali is generated first, then fed into the race model.

### Post-quali path

1. FP features exist (almost always — quali only happens after FP3).
2. Actual quali exists → uses `race_model.json` with real quali positions.
3. The model is operating in-distribution (trained on actual quali, inferred with actual quali).

### Sprint inference

When `is_sprint_weekend == True`:
- `predicted_sprint_quali_position`: from FastF1 SQ session (with fastest-lap fallback) if SQ has happened, else equal to `predicted_qualifying_position`.
- `predicted_sprint_position`: from `sprint_model.json` if actual SQ grid is available, else from a fallback path that uses the sprint model with predicted quali as proxy.

### Persisting the phase: `prediction_metadata.json` sidecar

After determining the phase, `06_run_predictions.py` writes a small sidecar to `data/predictions/round{N}/prediction_metadata.json` recording:

```json
{
  "round": 7, "year": 2026,
  "phase": "pre_fp",
  "generated_at": "2026-05-16T07:00:00+00:00",
  "is_post_quali": false,
  "used_fp_features": false,
  "race_model_used": "race_model_fp.json",
  "quali_model_sha256_16": "351e624720117624",
  "race_model_sha256_16": "bea91f44ad9dcb80"
}
```

This is the **source of truth** for phase labelling. `08_export_website_json.py` reads it via `detect_phase()` to tag the per-round archive (`predictions_round{N}_{phase}.json`) — never inferring from current data state, which can drift over time. The model hashes let any downstream tool verify it's looking at predictions from a specific trained model.

### Race-completed guards

`06_run_predictions.py`, `07_calculate_fantasy.py`, `08_monte_carlo_fantasy.py`, and `08_export_website_json.py` all consult `config.settings.is_race_completed(round_num)` (which reads `races.json`) before writing. If the race is in the past and the output already exists, the write is refused with a `[SKIP]` message. `--force` overrides.

The pollution problem this fixes: re-running predictions for a race that already happened, using a model that's been retrained on the very data being "predicted" — producing artificially-perfect accuracy. See [Audit Log](#audit-log) below for the recovery story.

### Audit Log

Every successful export from `08_export_website_json.py` appends to two places under `data/audit/`:

- `predictions_log.jsonl` — one JSON object per line: timestamp, round, phase, MAE vs actuals (if known), git HEAD SHA, model hashes, snapshot path. Append-only.
- `snapshots/round{N}/{ISO}_{phase}.json` — full immutable snapshot of the exported predictions payload, plus the sidecar metadata. Filenames are timestamped so older snapshots are never overwritten.

This is the safety net: if a per-round archive in `web/public/data/` is corrupted or accidentally clobbered, you can recover from the audit snapshot. It's also the historical record of how the algorithm has evolved — each prediction is stamped with the git SHA + model hashes that produced it.

The audit module is `pipeline/audit.py`. The hook is in `08_export_website_json.py:main()`. Disable with `--no-audit` (rarely needed). Tag entries with `--audit-label "..."` for filtering later.

---

## 8. Predict-Time Feature Recomputation

A subtle but important detail: when generating predictions for an upcoming round, the "stub row" we feed the model is built from each driver's *most recent completed race* (their latest priors). But some features need to be **recomputed for the target circuit** before scoring.

### `_recompute_sim_features` (track-similarity weighted)

The Layer-1 features `sim_weighted_quali_3`, `sim_weighted_quali_5`, `sim_weighted_finishpos_3`, etc. are computed during feature-build (`03b`) by weighting each driver's recent races by similarity to *that race's circuit*. For a stub row whose latest race was Miami, those values are weighted toward Miami-similar tracks.

But for predicting Canada, we want them weighted toward *Canada-similar tracks*. So `_recompute_sim_features(priors_df, target_circuit)`:
1. Loads `all_model_rows.parquet`.
2. For each driver, takes their last 3 (and 5) races.
3. Computes `weight = similarity(target_circuit, race_circuit)²` for each.
4. Recomputes `sim_weighted_*` as the weighted average.

### `_recompute_circuit_features` (circuit-specific history)

Added recently to fix a bug where `driver_circuit_exp`, `driver_circuit_roll_3`, and `constructor_circuit_exp` were inheriting their values from the most recent race. For a Canada prediction, VER's `driver_circuit_exp` was showing 9.5 (his Miami quali avg) instead of 1.5 (his actual Canada quali avg across 4 starts).

The fix:
1. Filters `all_model_rows.parquet` to rows where `circuit_id == target_circuit`.
2. For each driver in the prediction set, computes:
   - `driver_circuit_exp` = expanding mean of their prior quali_positions at this circuit
   - `driver_circuit_roll_3` = rolling-3 mean of same
3. For each constructor, similarly computes `constructor_circuit_exp`.
4. Drivers/constructors with no history at the target circuit get NaN (rather than inheriting an unrelated track's value, which was actively misleading).

### Why this matters

Both recomputations live in `06_run_predictions.py` and are called immediately after building the prior stub:

```python
priors_df = build_live_priors(round_num, year)
if target_circuit and target_circuit != "unknown":
    priors_df = _recompute_sim_features(priors_df, target_circuit)
    priors_df = _recompute_circuit_features(priors_df, target_circuit)
```

Without these, the model is fed misleading "history at this circuit" features. With them, the model gets accurate per-circuit signals — every driver at every circuit. The biggest impact is mid-pack drivers where a circuit is genuinely informative; for top runners, rolling-3 form often dominates the model's learned weights regardless.

### Note on constructors not changing the rank

The fix corrects feature inputs but does NOT change the model's *learned weights*. If the trained model heavily weights rolling-3 form vs circuit history, that ratio stays the same — we're just feeding it correct circuit-history values. To shift the ratio, we'd retrain.

---

## 9. Fantasy Scoring Engine

### Why Predicting Positions Isn't Enough

F1 Fantasy 2026 scoring is **highly nonlinear**:
- P1 = 25 pts, P2 = 18 pts (7-point gap)
- P10 = 1 pt, P11 = 0 pts (1-point cliff)
- P20 with 5 overtakes = 5 pts (position is irrelevant, overtakes carry the value)

Small position errors have vastly different impact depending on where they happen. A model "off by 2" performs very differently between P1↔P3 (7 pts off) and P10↔P12 (1 pt off).

### Driver Scoring (`pipeline/07_calculate_fantasy.py`)

For each driver:
1. **Qualifying points:** Lookup table P1=10, P2=9, ..., P10=1, P11+=0; DSQ/no time = -5
2. **Race points:** P1=25, P2=18, P3=15, P4=12, P5=10, P6=8, P7=6, P8=4, P9=2, P10=1, P11+=0
3. **Positions gained/lost:** `(grid_position - finish_position) × 1pt`
4. **Overtakes:** `estimated_overtakes × 1pt`
5. **Fastest lap probability:** `prob × 10pts` (F1 Fantasy bonus, separate from championship FL which was removed in 2026)
6. **DOTD probability:** `prob × 10pts`
7. **DNF risk:** `prob × (-20pts)`
8. **Sprint scoring** (if sprint weekend): see §6 Sprint Model. Sprint DNF = -10 pts (vs -20 main race in 2026).

### Constructor Scoring

1. **Sum both drivers' qualifying + race points**, **excluding DOTD** (per official 2026 rules)
2. **Qualifying teamwork bonus:** Both Q3 = +10, One Q3 = +5, Both Q2 = +3, One Q2 = +1, Neither = -1
3. **Expected pit stop points:** Analytically computed from team pit-stop time priors using a normal distribution over scoring brackets:
   - <2.0s: +20 pts
   - 2.0-2.19s: +10 pts
   - 2.2-2.49s: +5 pts
   - 2.5-2.99s: +2 pts
   - 3.0s+: 0 pts
   - World record (<1.80s): +15 (rare)
   - Fastest stop bonus: +5 pts (1/N_teams probability)
4. **DNF impact:** Expected points lost from both drivers' DNF probabilities

Constructor scoring uses **base driver scores only** — never the boosted/multiplied values from chip plays. Chip multipliers are a frontend/optimizer concept; the underlying expected_points is the constructor's input.

### Why DOTD is Excluded from Constructors

Official 2026 rules. In deterministic scoring (script 07), the expected DOTD contribution is subtracted from each driver's points before summing for the constructor. In MC simulation (script 08), the actual DOTD winner index is tracked per-iteration and exactly 10 points are subtracted from whichever driver won DOTD in that simulation — giving precise per-iteration constructor scores.

### Fastest Lap Probability

Weighted by predicted finishing position (P1-P3 highest — they pit for fresh tyres at the end; P11+ lowest).

### DOTD Probability

Estimate based on positions gained and finishing position. Drivers gaining the most positions while finishing well tend to win DOTD.

---

## 10. Monte Carlo Simulation

### Why Monte Carlo?

`E[fantasy_points(position)] ≠ fantasy_points(E[position])`.

Example: 50% chance of P1, 50% chance of P11 → expected position = P6, fantasy points at P6 = 8. Actual expected points = 0.5×25 + 0.5×0 = 12.5. The deterministic scoring underestimates the upside.

### Simulation Loop (`pipeline/08_monte_carlo_fantasy.py`)

For each of 10,000 simulations:

1. **Sample qualifying positions:** Z-score normalize raw XGBRanker scores (preserving model gaps), add team-correlated + individual Gaussian noise, re-rank.
2. **Sample DNFs:** Two-stage correlated sampling — multi-car incidents (~2% base) + team-correlated mechanical failures (30% teammate correlation, 3x elevated probability when one teammate has already DNF'd).
3. **Sample race positions:** Same gap-preserving approach as quali, with separate team shocks. DNF drivers assigned last position.
4. **Sample overtakes:** Driver-specific history when available (blended with grid-bucket estimates), otherwise grid-bucket base + excess gains, with stochastic variation.
5. **Sample fastest lap:** Weighted random selection by finishing position.
6. **Sample DOTD:** Weighted random selection (position + positions gained).
7. **Sample pit stops (constructors):** Per-team stop times from `N(team_mean, team_std)`, scored per bracket; fastest-stop bonus awarded.
8. **Compute full fantasy points** for this simulation.

After 10,000 runs, compute percentiles: P5, P25, P50, P75, P95.

### Noise Model

Z-score normalization of raw XGBRanker scores preserves the performance gaps the model predicted. Tightly-bunched midfield drivers swap positions frequently; a dominant leader rarely gets upset. (Old quantile-transform approach forced equal spacing — replaced.)

**Teammate correlation (alpha=0.35):** Each simulation draws a shared team shock per constructor for quali and separately for race. ~35% of position variance is team-level (car setup, reliability), ~65% individual (driver skill, luck).

### Calibration (from actual data)

Auto-loaded from `data/seed/mc_calibration.json` (output of `calibrate_confidence.py`):

| Parameter | Value | Source |
|-----------|-------|--------|
| Quali noise base | ~0.3 (z-score units) | Calibrated per round |
| Race noise base | ~0.3 | Same |
| Teammate correlation alpha | 0.35 | Historical teammate correlation |
| Confidence scaling | `1 + 1.5 × (100 - conf) / 50` | Lower confidence → wider distribution |
| DNF rate | Per-driver blended | Rolling 5-race historical + current season, dynamically weighted |
| Team DNF correlation | 0.30 | If one teammate DNFs, other has elevated risk |
| Overtake CV | 0.35 | Coefficient of variation from OpenF1 data |

### Sprint Adjustments

- Sprint noise = 80% of race noise (shorter race, less chaos)
- Sprint DNF = 50% of race DNF (fewer laps = less attrition)
- Sprint overtakes = ~45% of race overtakes (fewer laps, fewer chances)

### Output

Per driver: P5/P25/P50/P75/P95, prob_top_3, prob_top_5, prob_top_10, mean, std, mc_overtakes_mean, mc_quali_pts_mean, mc_race_pts_mean, mc_dnf_rate.
Per constructor: P5/P25/P50/P75/P95 with per-iteration DOTD subtraction and pit-stop sampling.

On the website: "MC 90% CI: -10 — 53 pts" means "in 90% of our 10K simulations, this driver scored between -10 and 53 fantasy points." Wide CI = high variance, narrow CI = predictable.

---

## 11. Overtake Estimation

Each overtake = +1 fantasy point. A midfield driver gaining 5 positions and making 10 overtakes can outscore a frontrunner. Hard to predict.

### Race Overtakes Formula

```
estimated_overtakes = base_overtakes(grid_position) + max(0, positions_gained)
```

Base overtakes by grid bucket (calibrated from R1-R3 actuals):

| Grid | Base | Reasoning |
|------|------|-----------|
| P1-P3 | 2-3 | Front runners mostly defend, occasional re-passes |
| P4-P6 | 3-4 | Some wheel-to-wheel |
| P7-P12 | 5-7 | Midfield chaos, lots of battles |
| P13-P22 | 7-10 | Back markers have many cars to pass |

`positions_gained` is added because most position gains involve overtakes, plus there may be additional overtakes from re-passes / back-and-forth battles.

### Sprint Overtakes

Sprints are ~45% of race distance. `estimate_sprint_overtakes()` uses reduced base values (~50% of race base) and `sprint_gains = max(0, positions_gained - 1)` to reflect fewer laps to convert position changes.

### Detection (post-race)

Two paths:
1. **OpenF1** (`13_fetch_openf1_overtakes.py`): Official position tracking with 30s pit-stop window filter. Generally most reliable.
2. **FastF1 sector method** (`12_count_overtakes.py`): Detects overtakes from sector-by-sector position changes. Less accurate but works when OpenF1 is unavailable.

Both detected counts are saved for reference. The actual fantasy scoring uses `data/seed/overtakes.csv` if entries exist (manual override for the official F1 Fantasy count, which sometimes differs from auto-detected).

### Known Limitation

Auto-detected counts are typically 20-30% higher than F1 Fantasy's official numbers. Until an authoritative source for the F1 Fantasy count exists, manual entry into `overtakes.csv` is the only way to ensure scoring matches the game exactly.

---

## 12. Risk & Confidence System

### Confidence Score (0-100)

How much data we have and how much our models agree.

Components (computed in `06_run_predictions.py::calculate_confidence`):
1. **Data completeness:** FP laps available (+0 to +20), FP sessions count (+0 to +10).
2. **Prior data richness:** Non-NaN Jolpica priors (+0 to +10).
3. **Model agreement:** Rank correlation between race XGBoost output and FP signal model output (+0 to +10).

Base 50, maximum 100. Typical: ~85-95% with FP data, ~60-75% without.

### Risk Rating

Based on DNF probability (rolling 5-race DNF rate from Jolpica, blended with current season actuals):

| Label | DNF probability |
|-------|-----------------|
| LOW | ≤ 10% |
| MEDIUM | 11-25% |
| HIGH | 26-50% |
| VERY HIGH | > 50% (rare) |

Drives the DNF probability used in MC simulation and the deterministic scoring's DNF penalty.

---

## 13. Price Change Prediction

### How F1 Fantasy Prices Work

F1 Fantasy adjusts prices after each race based on a Points-Per-Million (PPM) ratio. The exact algorithm isn't public; community research established the thresholds we use.

### PPM Computation

```javascript
PPM = avg_fantasy_points_last_3_rounds / current_price
```

We compute PPM using a rolling window of the last 2 actual scores plus the predicted score for the upcoming race (window of 3).

### Thresholds

| Rating | PPM | A-tier (>$18.5M) | B-tier (≤$18.5M) |
|--------|-----|------------------|------------------|
| Great | ≥ 1.2 | +$0.3M | +$0.6M |
| Good | ≥ 0.9 | +$0.1M | +$0.2M |
| Poor | ≥ 0.6 | -$0.1M | -$0.2M |
| Terrible | < 0.6 | -$0.3M | -$0.6M |

**Why two tiers:** Expensive drivers swing in smaller dollar amounts. Budget drivers swing more aggressively.

### Data sources

Price change calculations use official F1 Fantasy points (from `data/seed/official_fantasy_points.json`) when available, falling back to pipeline-calculated actuals. The export pipeline auto-syncs official points to the web directory.

### Application in optimizer

The "Budget Builder" strategy uses predicted price changes to recommend lineups maximizing asset appreciation.

---

## 14. Lineup Optimizer

### The Constraint

5 drivers + 2 constructors, total cost ≤ budget cap (default $100M).

### Search

C(22, 5) × C(11, 2) = 26,334 × 55 = **1,448,370** combinations. Small enough for brute force in JavaScript with budget pruning.

The current implementation uses iterative branch-and-bound with budget pruning (`searchCombosWithPruning` in `app.js`):
1. Driver pool sorted by current_price.
2. Pre-computed price-suffix sums for "minimum remaining cost" pruning.
3. Recursion stops as soon as `current_cost + min_remaining_cost > remaining_budget`.

### Strategies

| Strategy | Scoring (lineupScore) | Use case |
|----------|----------------------|----------|
| Max Points | Sum of expected_points (chip-aware) | Maximize this week's score |
| Max Value | total_points / total_cost | Best points per dollar |
| Budget Gain | predictPriceChange × 100 + total_points × 0.1 | Maximize asset appreciation |
| Balanced | total_points × 0.6 + (points/cost) × 50 | Mix |

`lineupScore` is chip-aware — when a chip like 3x Boost is selected, the boosted points are passed in (best driver × 3 + second-best × 2) so the strategy ranks lineups according to the realistic post-chip score.

### Lock & Exclude

- **Lock (left-click):** Force a pick into the lineup. Stored in `lockedDrivers`/`lockedConstructors` Sets.
- **Exclude (right-click):** Remove from consideration. Stored in `excludedDrivers`/`excludedConstructors` Sets.

Enforced across all three optimizer modes (Lineup, Transfer Advisor, Multi-Week Planner).

### The 6 Chips

1. **Limitless:** No budget cap.
2. **3x Boost:** Best driver scores 3x, second-best scores 2x.
3. **Wild Card:** Unlimited free transfers (no penalties).
4. **No Negative:** Negative scores become 0.
5. **Autopilot:** Auto 2x on best driver.
6. **Final Fix:** Post-quali roster changes.

---

## 15. Multi-Week Transfer Planner

### Problem

F1 Fantasy allows 2-3 free transfers per round; extra transfers cost -10 pts each. Planning one round at a time is suboptimal — you might trade away a driver who's great for the next 3 tracks just to gain 5 points this week.

### Architecture: Beam Search Over Transfer Sequences

ML predictions exist for the current round; future rounds are projected in two layers:

1. **Preferred — `horizon_projections.json` (P9):** populated by `pipeline/predict_horizon.py`, which runs priors-only ML predictions for the upcoming 5 rounds at the end of every prediction phase. When this file exists and contains the round, the planner uses real ML expected-points (full confidence).
2. **Fallback — confidence-weighted track-affinity heuristic:**

   ```
   projected_score = base_form × affinity × sprint_multiplier
   affinity        = 1 + confidence × (rawAffinity − 1)   [clamped to 0.6–1.4]
   ```

   - `base_form` = each pick's `expected_points` from the current ML prediction
   - `rawAffinity` = `Σ(history_pts × weight) / Σ(weight) / hist_average`, where `weight = max(0, cos_sim − 0.5) × 2` against the 9D circuit feature vector
   - `confidence ∈ [0,1]` = `min(1, Σweight / 1.0)` — relaxes the old hard-gate (≥2 races, sim > 0.7) so cold-start picks (rookies, Cadillac) get a dampened partial signal instead of being silently defaulted to 1.0
   - `sprint_multiplier` = 1.35× for sprint rounds (relative)

### Beam Search Details

- **Width:** 60 beams (top 60 states kept at each round). See `MW_TUNABLES.beamWidth`.
- **Candidates per state:** 0 swaps (hold) + every single swap + 2-swap combos (driver+driver, driver+constructor, constructor+constructor) + Wild Card optimal team + Limitless dream team + each "chip on top of swap" augmentation.
- **2-swap pool (P11):** `(top-N by raw projected score) ∪ (top-N by PPM)` for both drivers and constructors. PPM pool surfaces cheap high-value picks that enable budget-relief swaps. Defaults: 8+8 drivers, 4+3 constructors (deduped).
- **State tracking:** team composition, budget, banked transfers (max 5), chips used + remaining, cumulative score, transfer history, per-round budget evolution.
- **Budget propagation (P1):** after each round, `state.budget` advances by `Σ predictPriceChange(pick).expectedChange` across the persisted team, so the next round's transfer search sees the appreciated spending ceiling.
- **Deduplication (P6):** key = `sorted(drivers) | sorted(constructors) | sorted(chipsAvailable) | bankedTransfers`. Earlier version collapsed states with same team but different chip/FT portfolios, silently losing strictly-better futures.
- **Penalty:** -10 pts per extra transfer beyond free allocation (`MW_TUNABLES.transferPenalty`).

### Strategies

The Strategy dropdown re-ranks plans via a weighted internal score that is **not displayed**. Every plan card always shows raw net projected points so plans can be compared across strategies (P14 hint surfaces this in the UI).

| Strategy | Internal score |
|----------|---|
| Max Points | Pure `netPts` (`pts − penalty`) |
| Balanced | `0.7 × netPts + 30 × ppm` (weights from `MW_TUNABLES.balancedPointsWeight/PpmWeight`) |
| Budget Gain | `netPts + 50 × priceGain` (PPM bracket scoring on each held pick) |

### Chip Support

- **Wild Card:** at every beam state, `findOptimalWildcardTeam` runs a true brute-force search (constructor-pair × driver-combo with branch-and-bound pruning). Memoized per `(round_index, budget_bucket)` so the ~60-state × 3-round horizon performs the search ~3–10 times instead of 180.
- **Limitless (P5b):** one-round dream team. The planner correctly carries the persisted (pre-Limitless) team forward — no transfers consumed, no penalty, no held-asset appreciation on the dream team, target distance measured against the persistent team. Greedy top-N selection is provably optimal here because Limitless ignores the budget constraint entirely.
- **3x Boost / No Negative / Autopilot / Final Fix:** layered on top of any 0/1/2-swap candidate during beam expansion so combinations like "swap A→B AND fire 3x Boost on the new driver" are explored.

### Target Team Mode

Optional. Users select an ideal 5+2 team and a **target intensity** (P13). The beam search applies a continuous per-round distance penalty (P3):

```
penalty_for_round = distance × TARGET_WEIGHT × (ri + 1) / horizon
```

- `distance` = count of target picks not in the candidate team (0..7), measured against the **persisted** team (so Limitless dream teams don't earn false convergence credit).
- `TARGET_WEIGHT` is set by the dropdown — Loose=10, Balanced=30 *(default)*, Strict=80 — via `MW_TUNABLES.targetIntensity`.
- The `(ri+1)/horizon` factor ramps recency so late rounds penalize more than early ones, but early rounds still actively path-find toward the target instead of waiting for a final-round cliff.

`findOptimalWildcardTeam` is also target-aware when target mode is on — its internal objective subtracts the same distance × weight × roundProgress so Wild Card converges on the target naturally rather than defaulting to max-points.

### Feasibility Card (P2)

Before the beam search runs, when target mode is active the planner emits a `feasibilityInfo` object summarizing reachability:
- `targetCost` vs `currentBudget` vs `currentBudget + horizonAppreciation` (with `horizonAppreciation` = sum of projected price changes if the user holds their CURRENT team across the whole horizon — an upper-bound ceiling)
- Classification: `isReachableNow` (green), `isPossiblyReachable` (orange), or `isUnreachable` (red, with explicit shortfall and the 2 most expensive target picks called out)
- Held-target-count + transfers needed

Rendered as a colour-coded card above the plan grid via `renderFeasibilityCard`.

### Tunables (P10)

All planner constants live in a single `MW_TUNABLES` block at the top of the multi-week section in `app.js`. Covers beam width, transfer penalty, max banked FT, target weight + intensity map, candidate pool sizes, wildcard pool, strategy weights, PPM bracket thresholds, and affinity heuristic parameters (similarity floor, full-confidence weight, clamp range). Single-spot tuning + clear comments per constant.

### Data Requirements

Three JSON files (all exported by pipeline scripts):
- `track_data.json` — 22 circuits, 9D feature vectors, race-to-circuit mapping, sprint round list
- `driver_history.json` — per-driver and per-constructor actual points per completed round with circuit_id mapping
- `horizon_projections.json` *(optional)* — priors-only ML projections for the next 5 rounds from `predict_horizon.py`; planner falls back to the affinity heuristic when missing

### Display

- **Feasibility card:** green/orange/red status banner with target cost, current budget, projected appreciation, ceiling, shortfall (if any), and priciest target picks
- **Projection heatmap:** top 12 drivers + top 6 constructors × planning rounds, color-coded by performance vs row average. Low-confidence cells (P8) get italic styling + dotted underline + tooltip
- **Plan cards:** top 5 plans. Each card shows raw net projected points, horizon budget summary, hold/swap/chip per round, per-round budget evolution (`budgetBefore → budgetAfter`, appreciation), and a "vs hold" tradeoff line on swap rounds showing whether the extra-transfer penalty paid off (P7)
- **Team Evolution view:** expandable per plan card. Full roster at each round with NEW badges and per-member projected points. After a Limitless round, the next-round NEW badges are computed against the persisted team (not the dream team) to avoid false positives

---

## 16. Confidence Interval Calibration

### The problem

MC simulations produce CIs (P5-P95). No guarantee these are well-calibrated. If the 90% CI only captures 70% of actual outcomes, we're giving false certainty.

### The solution

`pipeline/calibrate_confidence.py` empirically calibrates by analyzing MC predictions vs actuals across all completed rounds.

1. **Coverage analysis:** For each driver prediction, check if actual points fell within P5-P95 (target 90%) and P25-P75 (target 50%).
2. **PIT histogram:** Probability Integral Transform — maps each actual outcome to its percentile in the predicted distribution. Well-calibrated → uniform histogram.
3. **Per-tier analysis:** Front-runners (P1-P5), midfield (P6-P15), back-markers (P16-P22). Back-markers are hardest to predict.
4. **Noise multiplier:** Computes scaling factor to achieve target coverage. If too narrow (e.g. 86%), multiplier > 1.0 expands intervals.

### Conservative correction

With limited data (<3 rounds), multiplier capped at ±10%. With 6+ rounds, the cap is removed. Saved to `data/seed/mc_calibration.json`, auto-loaded by MC simulation.

---

## 17. Website Architecture

### Stack

- **Frontend:** Vanilla JavaScript (no framework). Single `app.js` (~7,800 lines).
- **Styling:** Pure CSS with custom properties.
- **Hosting:** Vercel (static file hosting, CDN).
- **Deployment:** `git push` → GitHub → Vercel auto-deploys.
- **Data:** Static JSON files served from `web/public/data/`.

**No build step.** Edit `app.js` directly. Bump `app.js?v=N` in `index.html` to bust browser cache.

### Lazy Tab Loading

1. **Phase 1 (blocking):** Fetch `predictions.json` + `season_summary.json`.
2. **Phase 2 (immediate):** Render Drivers tab.
3. **Phase 3 (background):** Deferred loads for weather, official points, actuals.
4. **Phase 4 (on-demand):** Each tab renders on first click with a loading spinner.

Tabs: Drivers, Constructors, Optimizer, Analysis, Season, H2H, Accuracy, Race Deep Dive, Videos, Articles, Changelog, About.

### Data Flow

```
Pipeline → .parquet → 08_export_website_json.py → .json → git push → Vercel → CDN
```

The export script also:
- **Auto-syncs official points** from `data/seed/official_fantasy_points.json` to `web/public/data/official_points.json`
- **Overrides prices** in predictions with latest values from `data/seed/fantasy_prices.json`
- **Exports driver/constructor price history** to `season_summary.json` for the price tracker tables

### Countdown Timer

Lock deadline countdown uses a hardcoded `LOCK_DEADLINES` array of UTC timestamps for each round's qualifying start. Computed against the user's device time.

---

## 18. Known Limitations

### Overtake Accuracy

Auto-detected overtake counts are ~20-30% higher than F1 Fantasy's official numbers. Mitigated by `data/seed/overtakes.csv` manual override, but this requires operator effort post-race.

### New Driver/Team Performance

2026 has new regulations and a new team (Cadillac). Historical data may not capture the true performance shift. The 2.5x sample weight helps, but early-season predictions for new entities (Cadillac, rookies like Antonelli/Lindblad/Bortoleto) have higher uncertainty. The `_recompute_circuit_features` fix sets these to NaN at unfamiliar circuits rather than inheriting irrelevant track values.

### Sandbag Detection

Teams deliberately hide pace in FP. Compound-specific features and consistency/long-run metrics partially mitigate, but a team running only hard tyres in FP while planning to use softs in qualifying will appear slower than they are.

### Q-Session Progression

The constructor qualifying bonus depends on which Q sessions both drivers reach (Q1/Q2/Q3). We currently estimate this from predicted qualifying positions, not modeled directly.

### Weather Impact

**Updated 2026-05-25 (Weather Level 3 shipped):** the quali/race/sprint models now ingest per-session weather features (`weather_was_wet_*`, `weather_track_temp_*`, `weather_air_temp_*`, `weather_humidity_*`, plus `weather_precip_minutes_race`) and a `CONSTRUCTOR_COLD_WEATHER_SKILL` rating. Inference reads `weather.json` and injects the forecast. The Monte Carlo widens noise + DNF rate and applies per-driver wet/cold perturbations based on rain risk and air temperature (`MC_WEATHER_TUNABLES` in `08_monte_carlo_fantasy.py`).

**Remaining limitation:** the validation gate was relaxed from the original +0.30 wet MAE target — achieved +0.185 due to small wet-race sample size (11 wet rounds in test window). The MC widener multipliers (1.7× noise, 2.6× DNF on HIGH rain) are reasonable first-pass values, not yet recalibrated from observed prediction error on wet 2026 weekends. See `docs/WEATHER_LEVEL3_IMPLEMENTATION_PLAN.md` for full Phase A-E report.

**Still open (Level 3.5):** dedicated DNF-by-weather classifier — would predict per-driver DNF probability conditional on `(driver_id, constructor_id, was_wet, track, temp, recent_DNF)` and feed MC's DNF sampling directly. More robust than the current rolling 5-race blended DNF rate when applied to wet conditions.

### Sprint Weekend Data Scarcity

Sprint weekends only have FP1 (60 minutes vs 180). Lower-confidence predictions inherently.

### Model weights vs corrected features

The `_recompute_circuit_features` fix corrects feature inputs but doesn't change the model's learned weights. If the trained model heavily weights rolling-3 form vs circuit history, that ratio stays — we're just feeding correct circuit values now. Shifting the ratio requires retraining.

---

## 19. Future Feature Ideas

### Recently Completed

✅ **Weather-conditioned ML model (Level 3) + MC weather widener** — race/quali/sprint models trained with per-session weather features; MC widens CI + DNF on wet weekends and biases toward wet-strong drivers + cold-strong constructors. (2026-05-25)
✅ **What-If Scenarios overlay (Phase 1)** — per-card ± slider for visitors to dial driver/constructor pace bumps; client-side overlay with share-via-URL. (2026-05-25)
✅ **Changelog tab** — JSON-driven release notes describing model + feature updates over time. (2026-05-25)
✅ Automated phase-aware pipeline runner (`run_weekend.py`)
✅ Weather integration (`weather_forecast.py` + GH Action)
✅ Chip strategy advisor (all 6 chips in optimizer)
✅ Transfer Advisor with penalty calculation
✅ Head-to-Head matchup predictions
✅ Historical accuracy dashboard (per-round + per-driver MAE, scatter, CI coverage)
✅ Track similarity weighting (9D cosine, 6 sim-weighted features)
✅ Price change prediction (PPM-based A/B tier system)
✅ Fuel-corrected practice pace (Race Deep Dive)
✅ DNF/Reliability modeling (per-driver blended; correlated DNF in MC)
✅ Sprint-specific predictions (`sprint_model.json`)
✅ Enhanced constructor scoring (qualifying bonus, expected pit stops, DNF impact)
✅ Multi-week transfer planner (beam search, 2-5 rounds, target team mode)
✅ Constructor accuracy dashboard (toggle in Accuracy tab)
✅ Predict-time circuit feature recomputation (`_recompute_circuit_features`)

### High Priority (Next Up)

1. **Weather Level 3.5 — dedicated DNF-by-weather classifier**
   Small `(driver_id, constructor_id, was_wet, track, temp, recent_DNF) → DNF_prob` model that feeds MC's DNF sampling directly. More robust than the current rolling-5 blended DNF rate when weather conditions diverge from training-set average. Spec in `docs/WEATHER_AWARENESS_FEATURE_PLAN.md` Level 3.5 section.

2. **Versioned model artifacts + validation gate before promotion**
   Currently `05_train_models.py` overwrites in place. Add timestamped subdirectories (`models/trained/v_2026-05-06_pre-canada/`) and a pointer file selecting active version. Promotion gated by walk-forward MAE comparison vs current production. Partial step taken with `models/trained_pre_weather/` backup on 2026-05-25.

3. **What-If Scenarios Phases 2-3** — optimizer + transfer advisor + multi-week planner consulting scenario state; compare-two-scenarios side-by-side; MC band overlay on scenarios; suggest-a-bump hints based on FP signal.

4. **MC weather widener calibration from observed data**
   The current widener tunables (1.7× noise on HIGH rain, 2.6× DNF, etc.) are reasonable first-pass values. After 2-3 real wet weekends in 2026, recalibrate from observed prediction-vs-actual deltas.

5. **Grid Penalty Integration**
   Auto-detect and apply engine/gearbox penalties. Dramatic fantasy impact.

6. **Q-Session Progression Model**
   Classifier predicting Q1/Q2/Q3 progression for each driver, improving constructor qualifying bonus estimates.

7. **Sharper track similarity**
   Current 9D cosine gives most circuit pairs ≥ 0.95 similarity, making the weighting nearly uniform. Consider rank-transforming track features per dimension, weighted Euclidean, or Mahalanobis distance.

8. **Fix overtake count gap**
   Find authoritative F1 Fantasy overtake source or build a heuristic that matches their numbers consistently. Removes manual `overtakes.csv` step.

### Medium Priority

6. Track-specific model tuning (street vs power vs high-DF)
7. Tyre strategy prediction (1-stop / 2-stop / 3-stop)
8. Betting odds as ensemble signal
9. Live race tracking (real-time fantasy point updates)
10. Multi-season backtesting

### Lower Priority / Technical

11. Incremental model updates (XGBoost `process_type='update'`)
12. Bayesian hyperparameter optimization (Optuna)
13. Specialized model ensembles (wet/dry, sprint/standard)
14. Telemetry-based features (throttle, brake, speed traces, DRS)
15. Push notifications (lineup lock approaching, predictions updated)
16. Natural-language race previews
