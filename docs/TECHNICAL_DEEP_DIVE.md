# BoxBoxF1Fantasy — Technical Deep Dive

**How the system works, why decisions were made, and where it's heading.**

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Data Sources & Why Each Was Chosen](#2-data-sources)
3. [The Two-Layer Feature System](#3-the-two-layer-feature-system)
4. [Machine Learning Models](#4-machine-learning-models)
5. [Fantasy Scoring Engine](#5-fantasy-scoring-engine)
6. [Monte Carlo Simulation](#6-monte-carlo-simulation)
7. [Overtake Estimation](#7-overtake-estimation)
8. [Risk & Confidence System](#8-risk--confidence-system)
9. [Price Change Prediction](#9-price-change-prediction)
10. [Lineup Optimizer](#10-lineup-optimizer)
11. [Website & Deployment](#11-website--deployment)
12. [Known Limitations](#12-known-limitations)
13. [Future Feature Ideas](#13-future-feature-ideas)

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA COLLECTION                              │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   FastF1     │    │  Jolpica API │    │  OpenF1 API  │          │
│  │  (Telemetry) │    │ (Historical) │    │ (Overtakes)  │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                    │                  │
└─────────┼───────────────────┼────────────────────┼──────────────────┘
          │                   │                    │
          ▼                   ▼                    │
┌─────────────────────────────────────────────┐    │
│              FEATURE ENGINEERING            │    │
│                                             │    │
│  ┌─────────────────┐  ┌──────────────────┐  │    │
│  │  Layer 1:       │  │  Layer 2:        │  │    │
│  │  Jolpica Priors │  │  FP Telemetry    │  │    │
│  │  (91 features,  │  │  (23 features,   │  │    │
│  │   always avail) │  │   sparse/NaN)    │  │    │
│  └────────┬────────┘  └────────┬─────────┘  │    │
│           │                    │             │    │
│           └────────┬───────────┘             │    │
│                    ▼                         │    │
│           ┌────────────────┐                 │    │
│           │ Merged Dataset │                 │    │
│           │ ~100 features  │                 │    │
│           └────────┬───────┘                 │    │
│                    │                         │    │
└────────────────────┼─────────────────────────┘    │
                     │                              │
                     ▼                              │
┌─────────────────────────────────────────────┐     │
│              ML PREDICTIONS                 │     │
│                                             │     │
│  ┌─────────────┐    ┌─────────────┐         │     │
│  │ XGBoost     │───▶│ XGBoost     │         │     │
│  │ Quali Model │    │ Race Model  │         │     │
│  │ (1200 trees)│    │ (650 trees) │         │     │
│  └─────────────┘    └──────┬──────┘         │     │
│                            │                │     │
│  ┌─────────────┐           │                │     │
│  │ ExtraTrees  │──(confidence scoring)──┐   │     │
│  │ FP Model    │                        │   │     │
│  └─────────────┘                        │   │     │
│                                         │   │     │
└─────────────────────────────────────────┼───┘     │
                                         │         │
                     ┌───────────────────┘          │
                     ▼                              │
┌─────────────────────────────────────────────┐     │
│           FANTASY SCORING                   │     │
│                                             │     │
│  Predicted positions → Fantasy points       │     │
│  + Overtake estimation ◄────────────────────┼─────┘
│  + DNF risk adjustment                      │
│  + Fastest lap / DOTD probability           │
│  + Sprint scoring (if applicable)           │
│  + Constructor aggregation & pit stops      │
│                                             │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│         MONTE CARLO SIMULATION              │
│                                             │
│  10,000 simulations per driver              │
│  → P5/P25/P50/P75/P95 percentiles          │
│  → Upside/downside risk                    │
│  → Position probabilities (top 3/5/10)     │
│                                             │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│              WEB EXPORT                     │
│                                             │
│  predictions.json + season_summary.json     │
│  + actual_round{N}.json + post_race data    │
│         │                                   │
│         ▼                                   │
│  ┌─────────────┐    ┌──────────────┐        │
│  │  Vercel CDN │    │ Local Dev    │        │
│  │ (Production)│    │ (serve.py)   │        │
│  └─────────────┘    └──────────────┘        │
│                                             │
│  boxboxf1fantasy.com                        │
└─────────────────────────────────────────────┘
```

---

## 2. Data Sources

### FastF1 (Free Practice Telemetry)

**What:** Lap-by-lap timing data from FP1, FP2, FP3 sessions.
**Why:** Free practice is the only real-world data available before qualifying and the race. It tells us how fast each car actually is on the current track in current conditions.
**Data includes:** Lap times, sector times (3 sectors per lap), tyre compound, pit in/out flags, deleted lap flags, weather conditions.
**Limitations:**
- Data availability: ~30 min delay after session ends
- Teams sandbag (don't show true pace) in FP — we mitigate by looking at consistency and long-run pace, not just headline lap times
- Sprint weekends only have FP1

### Jolpica API (Historical Results)

**What:** Race results, qualifying results, standings, pit stops for every F1 race since 1950. Successor to the Ergast API.
**Why:** Historical performance is the backbone of predictions. A driver's rolling average over the last 3-5 races is one of the strongest predictors of future performance.
**Data includes:** Finishing positions, grid positions, lap counts, pit stops (count + duration), constructor results, driver standings.
**Why not just FastF1 for history?** FastF1 telemetry is only reliably available from ~2019 onward. Jolpica provides structured result data going back decades, and we use 2020-2025 for training.

### OpenF1 API (Overtakes)

**What:** Real-time position tracking data from official F1 timing.
**Why:** Overtakes are worth +1 point each in F1 Fantasy, but they're hard to predict and measure. OpenF1 provides official position change data.
**Limitations:** Overcounts due to pit stop position swaps (we filter these out with a 30-second window). Still slightly higher than official F1 Fantasy counts (~18 vs 13 for Verstappen R1).

### Seed Data (Manual/Static)

**What:** Fantasy prices, driver roster, calendar, track classifications.
**Why:** Some data doesn't come from APIs — fantasy prices are set by F1 and need manual updates. Track characteristics (street circuit, overtaking difficulty) are expert-curated because they capture track DNA that raw data alone can't.

---

## 3. The Two-Layer Feature System

This is the core architectural decision of the project. Understanding it is key to understanding everything else.

### The Problem

We have two very different data sources:
1. **Historical data (Jolpica):** Available for every race 2020-2025 (~2,600 rows). Always available at prediction time.
2. **FP telemetry (FastF1):** Only available for ~160 of those rows in training. Available at prediction time if we run the pipeline after FP.

A model trained only on FP telemetry has just ~160 training samples — not enough.
A model trained only on historical data misses the crucial "how fast is the car THIS weekend" signal.

### The Solution: Two-Layer Merge

**Layer 1 — Jolpica Priors (always available, 91 features):**
- Rolling qualifying averages (last 1, 3, 5 races)
- Rolling race finishing averages
- Rolling points scored
- Season averages and medians
- Circuit-specific experience (how does this driver do at THIS track?)
- Constructor performance trends
- Teammate delta (gap to teammate)
- DNF rates (overall, mechanical, collision, driver error — all on 5-race rolling windows)
- Recent form: wins, podiums, points rate over last 5 races
- Form trend (improving or declining)
- Track features (9 dimensions from track_classifications.py)
- Team/driver skill ratings (strategy, tyre management, overtaking, etc.)
- Season progress (early vs. late season dynamics)

**Layer 2 — FP Telemetry (sparse, 40+ features):**
- Average, best, median lap times
- Best 3/5/10 lap averages
- Consistency (standard deviation, coefficient of variation)
- Degradation rate (linear regression of lap times across longest stint)
- Long-run pace (average over stints >= 5 laps)
- Short-run pace (best of first 3 laps)
- Sector-level best and average times (3 sectors)
- **Compound-specific features (Tier 2):** soft_best_lap, soft_avg_lap, medium_long_run_avg, hard_long_run_avg, medium_degradation, hard_degradation — separates qualifying sim pace (soft) from race sim pace (medium/hard)
- **Relative pace normalization (Tier 2):** pace_delta_to_fastest, pace_delta_to_median, avg_pace_delta_to_median, race_pace_delta_to_median, sector_N_delta_to_fastest, long_run_delta_to_median — these transfer across circuits (a 0.5s advantage means the same at Monaco and Monza)

**Why XGBoost handles this perfectly:**
XGBoost's `tree_method="hist"` handles NaN (missing values) natively. When an FP feature is NaN (no FP data for that row), XGBoost learns a default split direction. This means:
- In training on 2020-2024 rows without FP data, XGBoost relies on Jolpica priors
- When FP data IS present, XGBoost can use it to refine predictions
- No imputation needed, no two separate models needed

**Engineered Cross-Layer Features:**
- `prior_vs_fp_rank`: Gap between Jolpica prior qualifying prediction and FP pace rank. If a driver's historical data says "P5" but FP pace says "P2", that's a strong signal of improvement.
- `soft_medium_gap`, `medium_hard_gap`, `soft_vs_overall_best`: Compound-based interaction features that capture qualifying vs race pace tradeoffs.

### Why Shift(1) Matters

All rolling features use `.shift(1)` — the current race's result is NOT included in its own features. This prevents data leakage. When computing "driver's rolling 3-race average" for Round 5, we use Rounds 2, 3, 4 (not 3, 4, 5).

---

## 4. Machine Learning Models

### Why XGBoost?

We tested multiple algorithms (see `05b_experiment_models.py`): XGBoost, LightGBM, Random Forest, Gradient Boosting, ExtraTrees, stacking ensembles, voting ensembles.

XGBoost won because:
1. **Native NaN handling** — critical for our two-layer system
2. **Strong with sparse features** — FP features are sparse (90%+ NaN in training)
3. **Good regularization** — prevents overfitting on 2,600 rows
4. **Fast training** — important for experimentation

### Model Evolution

The models have gone through two generations:

**V1 (Baseline):** XGBRegressor with `reg:squarederror` objective. Treated positions as continuous numbers (P1=1, P22=22). Simple and effective but doesn't capture the fact that the gap between P1 and P2 matters more than P15 and P16.

**V2 (Current — Tier 2):** XGBRanker with `rank:pairwise` (LambdaMART) objective. Learns to rank drivers *within each race* correctly rather than predicting exact position numbers. This better handles the nonlinear nature of positions and fantasy scoring. Old V1 models are preserved in `models/trained_v1_baseline/` for reference.

### Qualifying Model (V2 — XGBRanker)

```
XGBRanker(n_estimators=1200, learning_rate=0.025, max_depth=3,
          objective="rank:pairwise", subsample=0.85, colsample_bytree=0.85)
```

- **Target:** Relevance labels derived from qualifying_position (P1 → label 21, P22 → label 0)
- **Group key:** (season, round) — each race is a ranking group with its own qid
- **Features:** ~62 (Jolpica priors + track + ratings + FP pace + relative pace features)
- **Why depth=3?** Qualifying is relatively predictable from historical data. Shallow trees prevent overfitting.
- **Walk-forward results:** MAE=3.26, Kendall's tau=0.536, Top-3 accuracy=57.3%

### Race Model (V2 — XGBRanker)

```
XGBRanker(n_estimators=650, learning_rate=0.03, max_depth=5,
          objective="rank:pairwise", subsample=0.85, colsample_bytree=0.85)
```

- **Target:** Relevance labels derived from finish_position (clean finishers only)
- **Group key:** (season, round) — per-group weights (2026 samples weighted 2.5x)
- **Features:** ~85 (all quali features + grid position + race-specific + compound features)
- **Key input:** Predicted qualifying position feeds in as a feature
- **Why depth=5?** Races have more complex interactions than qualifying: safety cars, strategy, tyre degradation, traffic.
- **Walk-forward results:** MAE=2.20, Kendall's tau=0.647, Top-3 accuracy=67.2%
- **2026-specific fold:** MAE=1.586, tau=0.741, Top-3=83.3%

### Why Ranking Objective Over Regression?

The ranking objective (`rank:pairwise`) uses LambdaMART, which optimizes for *correct ordering* rather than exact position numbers. Benefits:
- Naturally handles the nonlinear gap between positions (P1→P2 matters more than P15→P16)
- Groups by race so the model learns relative performance within each event
- Output is relevance scores (higher = better) which are ranked to produce positions
- Better aligns with the downstream fantasy scoring where rank order determines points

### FP Signal Model (ExtraTrees)

```
ExtraTreesRegressor(n_estimators=500, max_depth=6, random_state=42)
```

- **Purpose:** NOT for direct predictions. Used for confidence scoring.
- **How:** Measures how much FP pace data alone can predict race outcomes. When this model agrees with the XGBoost models, confidence is higher.
- **Why ExtraTrees?** More robust to noise than XGBoost for this smaller dataset. We only have ~160 rows with FP features.

### Walk-Forward Validation

**Why not standard cross-validation?**
F1 data is time-series. Using 2024 data to predict 2022 would be cheating — regulations change, teams evolve, drivers switch. Walk-forward respects this:

```
Fold 1: Train [2020-2021] → Test 2022
Fold 2: Train [2020-2022] → Test 2023
Fold 3: Train [2020-2023] → Test 2024
Fold 4: Train [2020-2024] → Test 2025
Fold 5: Train [2020-2025] → Test 2026 (R1-R3)
```

**Metrics (V2 Tier 2 models):**
- **Qualifying:** MAE=3.26, Kendall's tau=0.536, Top-3 accuracy=57.3%
- **Race:** MAE=2.20, Kendall's tau=0.647, Top-3 accuracy=67.2%
- **2026-only fold:** Race MAE=1.586, tau=0.741, Top-3=83.3%

**Backtest results (2026 R1 Australian GP):**
- Race MAE=2.71, Kendall's tau=0.853, Top-3=3/3 (predicted RUS, ANT, LEC correctly)

**Backtest results (2026 R3 Japanese GP):**
- Race MAE=2.55, Kendall's tau=0.695, Top-3=1/3 (predicted ANT correct)

For the ranking models, we report Kendall's tau (rank correlation) and top-3 accuracy alongside MAE, since ranking quality matters more than exact position numbers for fantasy scoring.

### Sample Weighting

2026 has new regulations (ground effect changes, new tyres). Data from 2020-2025 under old regulations is still useful (driver skill, track characteristics persist) but less relevant. We weight 2026 samples 2.5x to ensure the models prioritize current-regulation patterns.

For XGBRanker, sample weights must be per-group (one weight per race), not per-sample. All drivers in the same race share the same weight based on the season's regulation relevance.

---

## 5. Fantasy Scoring Engine

### Why Not Just Predict Positions?

F1 Fantasy scoring is **highly nonlinear**:
- P1 = 25pts, P2 = 18pts (7-point gap)
- P10 = 1pt, P11 = 0pts (1-point cliff)
- P20 with 5 overtakes = 5pts (position is irrelevant, overtakes carry the value)

This means small position changes have vastly different point impacts depending on WHERE in the grid they happen. A model that's "off by 2 positions" performs very differently if it predicts P1 vs P3 (7pts off) or P10 vs P12 (1pt off).

### How Fantasy Points Are Calculated

```
pipeline/07_calculate_fantasy.py
```

For each driver:
1. **Qualifying points:** Lookup table (P1=10, P2=9, ..., P10=1, P11+=0)
2. **Race points:** Lookup table (P1=25, P2=18, ..., P10=1, P11+=0)
3. **Positions gained/lost:** (grid_position - finish_position) × 1pt
4. **Overtakes:** estimated_overtakes × 1pt
5. **Fastest lap:** probability × 10pts (F1 Fantasy bonus, separate from championship FL which was removed in 2026)
6. **Driver of the Day:** probability × 10pts
7. **DNF risk:** probability × (-20pts)
8. **Sprint (if applicable):** separate scoring (P1=8, ..., P8=1; FL=5pts; DNF=-10pts)

For each constructor:
1. **Sum both drivers' qualifying + race points** (excluding DOTD — per official rules)
2. **Qualifying bonus:** Based on which Q sessions both drivers reach
3. **Pitstop bonus:** Based on estimated pitstop times

### Why DOTD Is Excluded from Constructors

This was a bug we caught in our audit. Official F1 Fantasy 2026 rules explicitly exclude Driver of the Day bonus from constructor point totals. Before fixing this, constructors were inflated by ~1-2 points per weekend.

### Fastest Lap Probability

Weighted by predicted finishing position:
- P1-P3: Higher probability (they're more likely to pit for fresh tyres at the end)
- P4-P10: Medium probability
- P11+: Low probability

### DOTD Probability

Currently uses a simple estimate based on positions gained and finishing position. Drivers who gain the most positions and finish well tend to win DOTD.

---

## 6. Monte Carlo Simulation

### Why Monte Carlo?

**The fundamental problem:** `E[fantasy_points(position)] ≠ fantasy_points(E[position])`

Example: If a driver has a 50% chance of P1 and 50% chance of P11:
- Expected position = P6
- Fantasy points at P6 = 8pts
- But actual expected points = 0.5 × 25 + 0.5 × 0 = 12.5pts

Monte Carlo captures this by simulating thousands of possible outcomes.

### How It Works

```
pipeline/08_monte_carlo_fantasy.py
```

For each of 10,000 simulations:
1. **Sample qualifying positions:** Add calibrated Gaussian noise to model scores, re-rank
2. **Sample race positions:** Same approach, with grid position influence
3. **Sample DNFs:** Each driver has a probability of DNF (from rolling 5-race history)
4. **Sample overtakes:** Draw from calibrated distribution based on grid position
5. **Sample fastest lap:** Weighted random selection based on finishing position
6. **Sample DOTD:** Weighted random selection
7. **Calculate full fantasy points** for this simulation
8. After 10,000 runs, compute percentiles: P5, P25, P50, P75, P95

### Calibration (From Actual Data)

All noise parameters are calibrated from R1+R2 actual results:

| Parameter | Value | Source |
|-----------|-------|--------|
| Qualifying noise base | 1.4 positions | RMSE of quali predictions vs actual (R1) |
| Race noise base | 1.6 positions | Typical race-day variance (incidents, strategy) |
| Confidence scaling | 1 + 1.5 × (100 - conf) / 50 | Higher confidence → tighter distribution |
| DNF rate | 13.6% overall | 6/44 drivers DNF across R1+R2 |
| Overtake CV | 0.35 | Coefficient of variation from OpenF1 data |

### Sprint Weekend Adjustments
- Sprint noise = 80% of race noise (shorter race, less chaos)
- Sprint DNF = 50% of race DNF (fewer laps = less attrition)
- Sprint overtakes = 45% of race overtakes (fewer laps, fewer chances)

### Output: What Users See

On driver cards: **MC 90% CI: -10 — 53 pts**
This means: "In 90% of our 10,000 simulations, this driver scored between -10 and 53 fantasy points."

The spread indicates risk. A narrow CI = predictable outcome. A wide CI = high variance (could score big or flop).

---

## 7. Overtake Estimation

### Why Overtakes Matter

Each overtake is worth +1 fantasy point. A midfield driver who gains 5 positions and makes 10 overtakes can outscore a frontrunner. This is one of the most impactful and hardest-to-predict components.

### Current Approach

```
Estimated overtakes = base_overtakes(grid_position) + max(0, positions_gained)
```

**Base overtakes by grid position (calibrated from R1+R2 actual data):**

| Grid Position | Base Overtakes | Reasoning |
|---------------|---------------|-----------|
| P1-P3 | 2-3 | Front runners mostly defend, occasional re-passes |
| P4-P6 | 3-4 | Some wheel-to-wheel racing |
| P7-P12 | 5-7 | Midfield chaos, lots of battles |
| P13-P22 | 7-10 | Back markers have many cars to pass |

**Why positions_gained is added:** If a driver goes from P15 to P8, they gained 7 positions. Most of those involve overtakes, plus there may be additional overtakes from battles with cars they ultimately finished behind (re-passes, back-and-forth).

### Known Limitation

Our R1 prediction for Verstappen was 18 overtakes vs. 13 actual. OpenF1 tends to slightly overcount (pit stop position changes). The official F1 Fantasy count is lower. We haven't found a reliable source for the exact F1 Fantasy overtake numbers — this is a known gap.

### Data Sources for Overtakes

1. **OpenF1 API** (`13_fetch_openf1_overtakes.py`): Official position tracking, filters pit stops with 30s window
2. **FastF1 sector times** (`12_count_overtakes.py`): Detects overtakes from sector-by-sector position changes. Less accurate but works when OpenF1 is unavailable.

---

## 8. Risk & Confidence System

### Confidence Score (0-100%)

**What it represents:** How much data we have and how much our models agree.

**Components:**
1. **Data completeness:** Is FP data available? (Big boost: +20-25%)
2. **Historical data availability:** How many prior races for this driver/track combo?
3. **Model agreement:** Do the XGBoost model and FP signal model predict similar positions?

**Typical values:**
- With FP data: 85-95%
- Without FP data: 60-75%

**How it's used:**
- Displayed on driver cards
- Scales Monte Carlo noise (low confidence → wider uncertainty bands)
- Factored into optimizer recommendations

### Risk Rating

**What it represents:** DNF probability based on recent history.

**Calculation:** Rolling 5-race DNF rate from Jolpica data, capped at 25%.

**Labels:**
- LOW: ≤ 10% (most reliable drivers)
- MEDIUM: 11-25% (some reliability concerns)
- HIGH: 26-50% (significant DNF risk)
- VERY HIGH: > 50% (rare — e.g., driver with 3+ DNFs in last 5 races)

**How it's used:**
- Displayed as color-coded badge on driver cards
- Drives DNF probability in Monte Carlo simulation
- Factored into expected fantasy points (risk-adjusted scoring)

---

## 9. Price Change Prediction

### How F1 Fantasy Prices Work

F1 Fantasy adjusts player prices after each race based on performance (Points Per Million ratio). The exact algorithm isn't public, but community research has established thresholds.

### Our PPM Rating System

```javascript
PPM = avg_fantasy_points_last_3_rounds / current_price
```

We compute PPM using a rolling window of the last 2 actual scores plus the predicted score for the upcoming race (window of 3). The website's price change bracket display shows exactly how many points are needed this round to reach each threshold.

**Thresholds:**

| Rating | PPM | Expected Change (A-tier, >$18.5M) | Expected Change (B-tier, ≤$18.5M) |
|--------|-----|----------------------------------|----------------------------------|
| Great | ≥ 1.2 | +$0.3M | +$0.6M |
| Good | ≥ 0.9 | +$0.1M | +$0.2M |
| Poor | ≥ 0.6 | -$0.1M | -$0.2M |
| Terrible | < 0.6 | -$0.3M | -$0.6M |

**Why two tiers?** Expensive drivers (A-tier, >$18.5M) have smaller price swings. Budget drivers (B-tier) swing more aggressively. This matches observed F1 Fantasy behavior.

**Data sources:** Price change calculations use official F1 Fantasy points (from `data/seed/official_fantasy_points.json`) when available, falling back to pipeline-calculated actuals. The export pipeline auto-syncs official points to the web directory.

### Application in Optimizer

The "Budget Builder" strategy uses predicted price changes to recommend lineups that maximize asset appreciation. This is useful for players who want to build budget for later in the season.

---

## 10. Lineup Optimizer

### The Constraint

F1 Fantasy lineup: 5 drivers + 2 constructors, total cost ≤ budget cap (default $100M).

### Brute-Force Approach

**Why brute force?** With 22 drivers and 11 constructors:
- C(22, 5) = 26,334 driver combinations
- C(11, 2) = 55 constructor combinations
- Total: 26,334 × 55 = **1,448,370 combinations**

This is small enough to enumerate exhaustively in JavaScript in ~1-2 seconds. No heuristics or approximations needed — we check every valid lineup.

### Strategies

| Strategy | Scoring Function | Use Case |
|----------|-----------------|----------|
| Max Points | Sum of expected_points | Maximize this week's score |
| Max Value | Sum of value_scores | Best points per dollar |
| Budget Builder | price_change × 100 + value × 5 | Maximize asset appreciation |
| Balanced | 0.6 × points + 0.4 × value × 10 | Balanced approach |

### Lock & Exclude

- **Lock (left-click):** Force a pick into the lineup. Reduces search space.
- **Exclude (right-click):** Remove from consideration. Useful for ruling out players you don't own or don't want.

### Generator-Based Combinations

Combinations use a JavaScript generator function (`function*`) instead of building arrays. This means we never hold all 1.4M lineups in memory — we stream through them and keep only the top 200.

---

## 11. Website & Deployment

### Technology Stack

- **Frontend:** Vanilla JavaScript (no framework). Single `app.js` file (~4,000 lines).
- **Styling:** Pure CSS with CSS custom properties for theming.
- **Hosting:** Vercel (static file hosting, CDN).
- **Deployment:** Push to GitHub → Vercel auto-deploys.
- **Data:** Static JSON files served from `web/public/data/`.

**Why no framework?** The site is a single-page data dashboard. React/Vue would add complexity without benefit. The data is pre-computed — the frontend just renders it. Vanilla JS keeps it fast, simple, and dependency-free.

### Performance: Lazy Tab Loading

The site uses lazy tab loading to minimize time-to-interactive:

1. **Phase 1 (blocking):** Fetch `predictions.json` + `season_summary.json` (2 requests)
2. **Phase 2 (immediate):** Render the Drivers tab (hero, cards/table)
3. **Phase 3 (background):** Deferred loads for weather, official points, actual round data
4. **Phase 4 (on-demand):** Each tab renders on first click, with a loading spinner while data loads

Tabs like Accuracy, Season, Deep Dive, Videos, and Articles only fetch their data when the user navigates to them. This brings initial page load from ~5s to ~1s.

### Data Flow to Website

```
Pipeline → .parquet files → 08_export_website_json.py → .json files → git push → Vercel → CDN
```

The export script also:
- **Auto-syncs official fantasy points** from `data/seed/official_fantasy_points.json` to the web directory
- **Overrides prices** in predictions with latest values from `data/seed/fantasy_prices.json`

The website loads JSON files client-side. No server, no database, no API calls at runtime.

### Countdown Timer

The lock deadline countdown uses a hardcoded `LOCK_DEADLINES` array with UTC timestamps for each round's qualifying start. It computes the diff against the user's device time and updates every second.

---

## 12. Known Limitations

### Overtake Accuracy
Our overtake estimates are ~30% higher than official F1 Fantasy counts. OpenF1 data includes some pit-related position changes that we can't fully filter out. Until an official overtake data source exists, this remains an approximation.

### New Driver/Team Performance
2026 has new regulations and a new team (Cadillac). Historical data may not capture the true performance shift. The 2.5x sample weight for 2026 data helps, but early-season predictions for new entities (Cadillac, rookies like Antonelli/Lindblad/Bortoleto) have higher uncertainty.

### Sandbag Detection
Teams deliberately hide pace in FP sessions ("sandbagging"). Our features (best lap, consistency, long-run pace) partially mitigate this, but a team doing all their running on hard tyres in FP while planning to use softs in qualifying will appear slower than they are.

### Q-Session Qualifying Progression
The qualifying bonus for constructors depends on which Q sessions each driver reaches (Q1/Q2/Q3). We currently estimate this from predicted qualifying position rather than modeling Q-session elimination directly.

### Weather Impact
The current model doesn't explicitly model wet weather. FP features captured in dry conditions may not reflect wet race performance. Wet weather is rare but dramatically changes outcomes.

### Sprint Weekend Data Scarcity
Sprint weekends only have FP1 (60 minutes vs. 180 minutes of FP data on normal weekends). Predictions for sprint weekends have inherently lower confidence.

---

## 13. Future Feature Ideas

### High Priority (Immediate Value)

### Recently Completed

1. ~~**Automated Pipeline Runner**~~ ✅
   `pipeline/run_weekend.py` detects current race weekend phase and runs appropriate pipeline steps automatically.

2. ~~**Weather Integration**~~ ✅
   `pipeline/weather_forecast.py` pulls Open-Meteo forecasts. Per-session rain probability, temperature, wind speed. Weather widget on website.

3. ~~**Chip Strategy Advisor**~~ ✅
   All 5 chips supported in the lineup optimizer: Mega Driver (3x), Extra DRS (+1 driver), No Negative, Limitless, Wildcard.

4. ~~**Team Setup Integration / Transfer Advisor**~~ ✅
   Users input current team, budget, free transfers. Optimizer recommends optimal transfers with penalty calculation.

5. ~~**Head-to-Head Matchup Predictions**~~ ✅
   Dedicated H2H tab with win probabilities (normal CDF on MC distributions), stat comparisons, historical record, and pick recommendation.

6. ~~**Historical Accuracy Dashboard**~~ ✅
   Dedicated Accuracy tab with per-round and per-driver MAE, scatter plots, CI coverage analysis, and round filter toggles.

7. ~~**Track Similarity Weighting**~~ ✅
   9-dimensional circuit feature vectors with cosine similarity. Produces 6 similarity-weighted rolling features in the ML pipeline.

8. ~~**Price Change Prediction**~~ ✅
   PPM-based A/B tier system with bracket displays showing points needed for each price change threshold.

9. ~~**Fuel-Corrected Practice Pace**~~ ✅
   Race deep dive applies ~0.035s/lap fuel correction for normalized pace comparisons.

### High Priority (Next Up)

1. **DNF/Reliability Modeling**
   Predict per-driver DNF probability using team reliability rates + historical patterns. Apply negative expected points adjustment. Two-stage MC sampling: correlated incident events + independent mechanical failures.

2. **Sprint-Specific Predictions**
   Dedicated sprint model trained on sprint-only data. Sprint dynamics differ from race (shorter distance, limited strategy, different scoring table).

3. **Enhanced Constructor Scoring**
   Currently constructors = sum of two drivers. Add: expected pit stop fantasy points (from team pit stop time distributions), qualifying teamwork bonus prediction, DNF penalty adjustment. Per-iteration constructor simulation in Monte Carlo.

4. **Grid Penalty Integration**
   Detect and automatically apply grid penalties (engine penalties, gearbox changes, pit lane starts). These dramatically affect fantasy scoring.

5. **Q-Session Progression Model**
   Build a classifier to predict Q1/Q2/Q3 progression for each driver, improving constructor qualifying bonus estimates.

### Medium Priority (Season Enhancement)

6. **Track-Specific Model Tuning**
   Train specialized models for different track types (street circuits, power tracks, high-downforce tracks).

7. **Tyre Strategy Prediction**
   Predict likely tyre strategies (1-stop, 2-stop, 3-stop) based on FP degradation data and track characteristics.

8. **Multi-Week Transfer Planning**
   Forecast multiple rounds ahead for transfer planning — which drivers to buy now for future value growth.

9. **Betting Odds Integration**
   Fetch pre-race odds, convert to implied probabilities, use as ensemble signal in XGBoost.

### Lower Priority (Future Season)

10. **Live Race Tracking**
    Real-time fantasy point tracking during the race using live timing data.

11. **Social/Community Features**
    Let users share and compare lineups. Leaderboard for prediction accuracy.

12. **Push Notifications**
    Alert when predictions are updated, lock deadline approaches, or grid penalties announced.

13. **Multi-Season Backtesting**
    Run the full pipeline on 2022-2025 seasons as if predicting in real-time.

14. **Natural Language Race Previews**
    Auto-generate written race previews from prediction data.

### Technical Improvements

15. **Incremental Model Updates**
    Use XGBoost's `process_type='update'` to incrementally add new race data.

16. **Bayesian Optimization for Hyperparameters**
    Replace manual tuning with Optuna or similar.

17. **Ensemble of Specialized Models**
    Separate models for wet/dry, sprint/standard, street/permanent circuits.

18. **Telemetry-Based Features**
    Use FastF1 car telemetry (throttle %, brake %, speed traces, DRS activation) for richer FP features.
