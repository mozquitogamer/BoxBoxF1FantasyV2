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
│   ├── 02_build_laps.py            # Parse raw data into lap-level parquets
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
│   ├── raw/fastf1/year{Y}/round{R}/ # FP1/2/3 parquets
│   ├── raw/jolpica/year{Y}/round{R}/ # Results, qualifying, pitstops JSON
│   ├── processed/                    # Intermediate: features, model inputs
│   ├── predictions/round{N}/         # Per-round prediction parquets
│   └── seed/                         # Manual data (prices, drivers, races, etc.)
│       ├── fantasy_prices.json       # Current + starting prices + price_history per round
│       ├── drivers.json              # 22-driver roster with constructor mapping
│       ├── constructors.json         # 11 constructors
│       ├── races.json                # 2026 calendar
│       └── official_fantasy_points.json # Official F1 Fantasy points (manually entered)
├── models/trained/                   # Saved XGBoost models (.json)
├── web/public/
│   ├── index.html                    # Single-page app shell
│   ├── app.js                        # All frontend logic (~4,800 lines)
│   ├── styles.css                    # CSS with custom properties for theming
│   └── data/                         # JSON files served to frontend
│       ├── predictions.json          # Current round predictions
│       ├── season_summary.json       # Rounds, driver/constructor prices
│       ├── actual_round{N}.json      # Actual results per round
│       └── official_fantasy_points.json
├── docs/                             # Technical documentation
├── dashboard/                        # Streamlit analytics dashboard
└── vercel.json                       # Vercel deployment config
```

## Architecture: Two-Layer Feature System

The core design: two data layers merged for XGBoost, which handles NaN natively.

- **Layer 1 — Jolpica Priors (91 features, always available):** Rolling averages (1/3/5 race windows), circuit experience, constructor trends, teammate deltas, DNF rates, form trends, track similarity features, skill ratings. Uses `.shift(1)` to prevent leakage.
- **Layer 2 — FP Telemetry (40+ features, sparse/NaN in training):** Lap times, sectors, degradation, long-run pace, compound-specific features (soft/medium/hard), relative pace deltas. Only ~160/2,600 training rows have this data.

XGBoost's native NaN handling means: when FP data exists → model uses it to refine; when missing → model relies on priors. No imputation needed.

## ML Models

- **Qualifying model:** `XGBRanker(n_estimators=1200, lr=0.025, depth=3, objective="rank:pairwise")`
- **Race model:** `XGBRanker(n_estimators=650, lr=0.03, depth=5, objective="rank:pairwise")`
- **FP signal model:** `ExtraTreesRegressor(n_estimators=500, depth=6)` — used only for confidence scoring, not direct predictions
- Output is relevance scores ranked to produce predicted positions per race

## Fantasy Scoring (07_calculate_fantasy.py)

**Drivers:** Qualifying position pts + race position pts + positions gained/lost + overtakes (+1 each) + fastest lap probability (10pts) + DOTD probability (10pts) - DNF risk (-20pts). Sprint weekends add sprint qualifying + sprint race.

**Constructors:** Sum of both drivers' qualifying + race pts (excl DOTD) + qualifying teamwork bonus (Both Q3=+10, ..., Neither Q2=-1) + expected pit stop points (analytical CDF over scoring brackets) - DNF impact. Constructor scoring uses **base driver scores only** — never boosted/multiplied values.

**Pit stop scoring brackets:** <2.0s=20pts, 2.0-2.2s=10pts, 2.2-2.5s=5pts, 2.5-3.0s=2pts, 3.0s+=0pts, fastest stop bonus=+5pts.

## Monte Carlo Simulation (08_monte_carlo_fantasy.py)

10,000 iterations per driver. Each iteration: add calibrated noise to model scores → re-rank → sample DNFs (two-stage: multi-car incidents + team-correlated mechanical failures) → sample overtakes → sample fastest lap/DOTD → compute full fantasy points. Output: P5/P25/P50/P75/P95 percentiles.

Constructors simulated per-iteration: sum both drivers' simulated points + qualifying bonus + sampled pit stop points.

## Website Frontend (web/public/app.js)

Single-page vanilla JS app with tab-based navigation. Tabs: Drivers, Constructors, Optimizer, Season, H2H, Accuracy, Deep Dive, Videos, Articles, About.

Key features:
- **Driver/Constructor cards** with predicted points, MC confidence intervals, price change brackets, scoring breakdowns
- **Lineup optimizer** — brute-force over C(22,5)xC(11,2)=1.4M combinations. 4 strategies (Max Points, Max Value, Budget Builder, Balanced). Lock/exclude picks.
- **6 chips:** Limitless (no budget cap), 3x Boost (best driver 3x + second-best 2x), Wild Card (unlimited transfers), No Negative (negatives become 0), Autopilot (auto 2x on best), Final Fix (post-quali changes)
- **Transfer Advisor** — given current team + budget + free transfers, finds optimal swaps with -10pts/extra transfer penalty
- **Price change prediction** — PPM rating system (Great/Good/Poor/Terrible) with A-tier (>$18.5M) and B-tier brackets
- **Season Overview** — championship standings, driver and constructor price trackers, cumulative fantasy standings
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
# Full weekend automation (detects phase: pre-FP, post-FP, post-quali, post-race)
python pipeline/run_weekend.py --round N

# Or individual steps:
python pipeline/01_download_data.py --round N
python pipeline/03_extract_features.py --round N
python pipeline/06_run_predictions.py --round N
python pipeline/07_calculate_fantasy.py --round N
python pipeline/08_monte_carlo_fantasy.py --round N
python pipeline/08_export_website_json.py --round N
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
