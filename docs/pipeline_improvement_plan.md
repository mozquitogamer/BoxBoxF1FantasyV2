# Pipeline Accuracy Improvement Plan

## Context

Our pipeline (Jolpica priors + FP telemetry → XGBoost → Monte Carlo) is a solid foundation but has methodological weaknesses that limit accuracy compared to the gold standard (f1fantasytools.com). This plan addresses the gaps identified through internal audit, competitive analysis, and research into F1 prediction best practices.

**Key finding:** f1fantasytools uses NO ML and NO telemetry — just weighted session results + parametric Monte Carlo (N=10K). Their edge comes from sound simulation design (proper noise modeling, track similarity weighting, comprehensive scoring). We have a data advantage (FastF1 telemetry) but are undermining it with simulation-layer issues.

**Goal:** Fix the simulation/scoring layer first (highest ROI), then improve the ML layer, then add new data signals.

---

## Diagnosis: What's Wrong Today

| Issue | Impact | Where |
|-------|--------|-------|
| ~~**Quantile transform destroys pace gaps**~~ — ✅ Fixed: z-score normalization preserves performance gaps | ~~HIGH~~ | `08_monte_carlo_fantasy.py` |
| ~~**No teammate correlation**~~ — ✅ Fixed: shared team shocks (alpha=0.35) + individual noise | ~~HIGH~~ | `08_monte_carlo_fantasy.py` |
| ~~**Pit stop points completely missing**~~ — ✅ Fixed: analytical EV + per-iteration MC sampling | ~~HIGH~~ | `07_calculate_fantasy.py`, `08_monte_carlo_fantasy.py` |
| ~~**Constructor MC is approximate**~~ — ✅ Fixed: per-iteration simulation with pit stops | ~~MEDIUM~~ | `08_monte_carlo_fantasy.py` |
| ~~**Regression target treats positions as continuous**~~ — ✅ Fixed: switched to `rank:pairwise` (LambdaMART) | ~~MEDIUM~~ | `05_train_models.py` |
| ~~**FP features mix tyre compounds**~~ — ✅ Fixed: compound-aware feature extraction | ~~MEDIUM~~ | `03_extract_features.py` |
| ~~**No relative pace normalization**~~ — ✅ Fixed: session-relative delta features | ~~MEDIUM~~ | `03_extract_features.py` |
| **Independent DNF sampling** — misses correlated incidents (first-lap pileups, team reliability) | LOW-MED | `08_monte_carlo_fantasy.py` |
| **No betting odds calibration** — missing a free, highly-informative signal | LOW-MED | Not implemented |
| ~~**Confidence intervals uncalibrated**~~ — ✅ Fixed: auto-calibration from actual results, noise multiplier applied | ~~LOW~~ | `calibrate_confidence.py`, `08_monte_carlo_fantasy.py` |

---

## Plan: 3 Tiers, Ordered by Impact/Effort

### Tier 1: Fix the Monte Carlo Simulation (Highest ROI)

These changes fix fundamental methodology issues in the simulation layer. No ML retraining needed.

#### 1.1 Replace quantile transform with gap-preserving noise model ✅ COMPLETED (2026-04-04)
**File:** `08_monte_carlo_fantasy.py`

- Z-score normalization of raw XGBRanker scores preserves performance gaps (mean=0, std=1)
- Gaussian noise added per driver, scaled by confidence: `multiplier = 1 + 1.5 * (100 - confidence) / 50`
- Re-rank from noisy scores → natural position assignments
- Tightly-bunched drivers swap often, dominant drivers rarely upset — gaps drive swap probability
- Noise base calibrated at 0.3 (z-score units), matching ~1-2 position swaps for adjacent drivers

#### 1.2 Add teammate correlation to MC sampling ✅ COMPLETED (2026-04-04)
**File:** `08_monte_carlo_fantasy.py`

- Team-level shock drawn per team per simulation: `team_noise ~ N(0, alpha * noise_base)`
- Individual shock per driver: `individual_noise ~ N(0, (1-alpha) * noise_base) * confidence_multiplier`
- `alpha = 0.35` (35% shared, 65% individual)
- Separate team shocks for qualifying and race (independent draws)
- Produces realistic team outcomes: both drivers shift together with individual variation

#### 1.3 Add pit stop modeling for constructors
**Files:** `07_calculate_fantasy.py`, `08_monte_carlo_fantasy.py`, `config/fantasy_scoring.py`

**Current:** Pit stop points defined in config but never calculated.
**Scoring at stake:** 2-20 pts per stop + 5 pts fastest stop + 15 pts world record. With 1-2 stops per race, this is 5-50+ pts/race per constructor.

**Approach:**
- Create `data/seed/pit_stop_priors.json` with per-team average pit stop time and std (from 2026 data + historical)
- In MC: sample pit stop time per team per stop from `N(team_mean, team_std)`
- Score each stop per the bracket thresholds (>3.0s = 0pts, 2.5-3.0s = 2pts, etc.)
- Award fastest-stop bonus to the team with the lowest sampled time
- In deterministic calc: use expected value based on team's distribution crossing each threshold

#### 1.4 Simulate constructors per MC iteration (not approximate)
**File:** `08_monte_carlo_fantasy.py`

**Current:** Constructor points = sum of driver means minus estimated DOTD. P5/P95 uses Gaussian approximation.
**New:** In each of the 10K iterations:
- Sum both drivers' simulated fantasy points (excluding DOTD, per rules)
- Add simulated qualifying teamwork bonus (based on both drivers' simulated quali positions)
- Add simulated pit stop points (from 1.3)
- Aggregate across iterations for true constructor distributions

This captures the full nonlinearity and correlations that the current approximation misses.

#### 1.5 Correlated DNF modeling
**File:** `08_monte_carlo_fantasy.py`

**Current:** Each driver has independent DNF probability.
**New:** Two-stage DNF sampling:
- **Stage 1 — Incident events:** Sample whether a first-lap incident occurs (probability ~15% per race). If yes, sample 2-4 involved drivers weighted by grid position (midfield/back more exposed).
- **Stage 2 — Mechanical DNF:** Sample independently per driver using team-specific reliability rates.
- This produces realistic DNF clustering (0 DNFs sometimes, 4+ DNFs sometimes) instead of the unrealistic binomial-like distribution from independent sampling.

---

### Tier 2: Improve the ML Model

#### 2.1 Switch to ranking objective ✅ COMPLETED (2026-03-31)
**File:** `05_train_models.py`

**Current:** `objective="reg:squarederror"` — treats position as continuous number.
**New:** Use XGBoost's `objective="rank:pairwise"` (LambdaMART variant):
- Learns to rank drivers within each race correctly, not predict exact position numbers
- Group by `(year, round)` so the model learns "Driver A beats Driver B" rather than "Driver A finishes 3.2"
- Better handles the nonlinear nature of positions (P1 vs P2 gap matters more than P15 vs P16)
- Walk-forward validation metric: NDCG or Kendall's tau instead of MAE

**Fallback:** If rank:pairwise degrades performance (possible with our sample size), keep regression but add `log(position)` as target to compress the tail.

#### 2.2 Tyre-compound-aware feature extraction ✅ COMPLETED (2026-03-31)
**File:** `03_extract_features.py`

**Current:** All laps averaged together regardless of compound.
**New features:**
- `soft_best_lap`, `soft_avg_lap` — qualifying simulation pace
- `medium_long_run_avg`, `hard_long_run_avg` — race pace by compound
- `medium_degradation_rate`, `hard_degradation_rate` — compound-specific deg
- Keep existing aggregate features as fallback when compound data is sparse

Requires reading the `Compound` column from FastF1 lap data (already available in the parquet files).

#### 2.3 Relative pace normalization ✅ COMPLETED (2026-03-31)
**File:** `03_extract_features.py`, `feature_engineering.py`

**Current:** Absolute lap times (circuit-dependent, don't transfer).
**New:** Add delta-to-session features:
- `pace_delta_to_median` = driver_avg - session_median (how much faster/slower than field)
- `pace_delta_to_fastest` = driver_avg - session_fastest
- `sector_delta_to_fastest_1/2/3` = per-sector relative pace
- These features transfer across circuits (a 0.5s advantage means the same at Monaco and Monza)

#### 2.4 Betting odds as ensemble signal
**New file:** `pipeline/03c_fetch_betting_odds.py`

**Approach:**
- Fetch pre-race betting odds from a public API or scrape (multiple sources available)
- Convert to implied probabilities (remove overround/vig)
- Create features: `implied_win_prob`, `implied_top3_prob`, `implied_top10_prob`
- These encode the market's consensus view, incorporating information our model may miss (driver fitness, car upgrades, team strategy intel)
- Use as features in XGBoost (the model learns how much to trust odds vs its own signals)
- Also use as a calibration check: if our predictions diverge wildly from odds, flag for review

#### 2.5 Walk-forward validation improvements ✅ COMPLETED (2026-03-31)
**File:** `05_train_models.py`

**Current issues:**
- Tests year-by-year, not round-by-round within a season
- Final production model trained on ALL data including 2026 races it's "predicting"
- Reports MAE on raw scores, not on ranked positions

**Fixes:**
- Add within-season round-by-round validation for 2026 specifically
- Final model: train on all data EXCEPT the round being predicted
- Report ranking metrics (Kendall's tau, top-3 accuracy, top-10 accuracy) alongside MAE
- Track prediction vs actual for each completed race to monitor calibration

---

### Tier 3: New Capabilities (After Tier 1-2 are solid)

#### 3.1 Track similarity weighting ✅ COMPLETED (2026-04-03)
- ~~Classify circuits by characteristics (high/low downforce, street/permanent, overtaking difficulty)~~
- ~~Weight historical results from similar tracks more heavily in rolling features~~
- Implemented in `config/track_similarity.py` + `config/track_classifications.py`
- 9-dimensional feature vectors (downforce, overtaking difficulty, corner speed, straight-line importance, safety car probability, etc.) for 26 circuits
- Cosine similarity with squared weighting for sharper contrast
- Produces 6 similarity-weighted rolling features (`sim_weighted_points_3/5`, `sim_weighted_finishpos_3/5`, `sim_weighted_quali_3/5`)
- Prediction-time recomputation against upcoming circuit via `06_run_predictions.py`

#### 3.2 Fuel-corrected practice pace ✅ COMPLETED (2026-03-31)
- Implemented in `11_race_deep_dive.py` deep dive analysis
- ~0.035s/lap fuel correction applied to normalize lap times
- Full stint-by-stint fuel-corrected pace analysis with degradation rates

#### 3.3 Optimal team selection ✅ COMPLETED (2026-04-03)
- ~~Given predicted fantasy points + confidence intervals, solve for the optimal 5-driver + 2-constructor team under the $100M budget constraint~~
- Brute-force optimizer checking C(22,5) x C(11,2) = ~1.4M combinations
- Transfer advisor: given current team + budget + free transfers, find optimal swaps with -10pt penalty per extra transfer
- All 6 chip types supported: Limitless, 3x Boost (3x + 2x dual boost), Wild Card, No Negative, Autopilot, Final Fix
- Lock/exclude picks: left-click to force into lineup, right-click to exclude
- 4 strategies: Max Points, Max Value, Budget Builder, Balanced

#### 3.4 Price change prediction ✅ COMPLETED (2026-04-01)
- PPM (Points Per Million) rating system based on rolling 3-round average
- A-tier (>$18.5M) and B-tier (≤$18.5M) with different price swing magnitudes
- Per-driver price bracket display showing points needed for each rating threshold
- Budget Builder optimizer strategy that prioritizes picks likely to increase in price

#### 3.5 Weather integration ✅ COMPLETED (2026-04-01)
- `pipeline/weather_forecast.py` fetches hourly forecasts from Open-Meteo API
- Per-session rain probability, temperature, wind speed
- Overall weekend rain risk assessment (NONE/LOW/MEDIUM/HIGH)
- Weather widget on website home page with session-by-session breakdown

---

### Tier 4: Next Wave

#### 4.1 DNF/reliability modeling ✅ COMPLETED (2026-04-04)
- Per-driver DNF probability calculated from blended historical rolling rates + current season actual DNF data
- Dynamically weighted: early season uses more historical data, shifts to 80-90% current season as data accumulates
- Capped at 13-50% depending on rounds completed, 2% floor for all drivers
- Two-stage correlated DNF in MC: multi-car incidents (2% base) + team-correlated failures (30% teammate correlation)
- Sprint DNF probability halved vs race
- DNF probability displayed on driver cards (color-coded: green/yellow/red)
- Constructor DNF impact shown in scoring breakdown

#### 4.2 Sprint-specific predictions ✅ COMPLETED (2026-04-04)
- Dedicated `XGBRanker` sprint model trained on 501 sprint-only rows (2021-2026)
- Lighter regularization: 400 trees, depth=4, lr=0.035, reg_lambda=1.5
- Walk-forward validation: MAE=3.696, tau=0.492, Top-3=63.3%
- Sprint predictions use dedicated model raw scores (falls back to race model if unavailable)
- MC simulation uses sprint raw z-scores with team-correlated noise (0.8x race noise)
- Sprint DNF probability halved, sprint-specific overtake calibration retained

#### 4.3 Enhanced constructor scoring ✅ COMPLETED (2026-04-04)
- Constructor scoring now includes: sum of drivers' points + qualifying teamwork bonus + expected pit stop points - DNF impact
- Expected pit stop points calculated analytically from team pit stop time distributions (normal distribution over scoring brackets)
- Per-iteration constructor simulation in Monte Carlo with pit stop sampling
- Scoring breakdown displayed on constructor cards: pit stop points, DNF probability, DNF impact, qualifying bonus
- Fast teams (Red Bull, McLaren, Mercedes) earn ~14-15 expected pit stop pts; slower teams ~7-8 pts

#### Confidence interval calibration ✅ COMPLETED (2026-04-04)
**Files:** `pipeline/calibrate_confidence.py`, `pipeline/08_monte_carlo_fantasy.py`

- New `calibrate_confidence.py` script analyzes MC predictions vs actual results across all completed rounds
- Computes empirical coverage at P5-P95 (target 90%) and P25-P75 (target 50%)
- PIT (Probability Integral Transform) histogram checks for uniform distribution of outcomes
- Per-tier analysis (front/midfield/back) and per-round breakdown
- DNF impact analysis (DNF outcomes are hardest to capture in CI)
- Computes noise multiplier: scales all noise bases to achieve target coverage
- Conservative cap: ±10% adjustment with <3 rounds of data, uncapped with 6+ rounds
- Saves calibration to `data/seed/mc_calibration.json`, auto-loaded by MC simulation
- Website Accuracy tab now shows both 90% CI and 50% CI coverage metrics
- Initial results (2 rounds): 90% CI=86.4% (slightly narrow), noise multiplier=1.1x

---

## Implementation Order

**Completed:**
- ✅ 1.1 Gap-preserving noise model (2026-04-04)
- ✅ 1.2 Teammate correlation (2026-04-04)
- ✅ 2.1 Ranking objective (2026-03-31)
- ✅ 2.2 Tyre-compound features (2026-03-31)
- ✅ 2.3 Relative pace normalization (2026-03-31)
- ✅ 2.5 Walk-forward validation (2026-03-31)
- ✅ 3.1 Track similarity weighting (2026-04-03)
- ✅ 3.2 Fuel-corrected pace (2026-03-31)
- ✅ 3.3 Optimal team selection (2026-04-03)
- ✅ 3.4 Price change prediction (2026-04-01)
- ✅ 3.5 Weather integration (2026-04-01)
- ✅ 4.1 DNF/reliability modeling (2026-04-04)
- ✅ 4.2 Sprint-specific predictions (2026-04-04)
- ✅ 4.3 Enhanced constructor scoring (2026-04-04)

- ✅ Confidence interval calibration (2026-04-04)
- ✅ Multi-week transfer planning (2026-04-04)

**Next up:**
- (All planned features completed)

## How to Validate Improvements

1. **Backtest against R1-R3 actual results:** For each change, re-run predictions for completed 2026 races and compare fantasy point accuracy (MAE, ranking correlation)
2. **Compare against f1fantasytools:** For upcoming races, compare our predicted distributions with theirs side-by-side
3. **Calibration check:** After 5+ races, verify that our P5-P95 intervals capture ~90% of actual outcomes
4. **Constructor accuracy:** Track constructor point prediction error specifically (currently worst due to missing pit stops)
5. **Track per-change impact:** A/B test each improvement against the baseline to measure marginal gain

## Key Files to Modify

| File | Changes |
|------|---------|
| `08_monte_carlo_fantasy.py` | Gap-preserving noise, teammate correlation, correlated DNF, per-iteration constructor sim, pit stop sampling |
| `07_calculate_fantasy.py` | Deterministic pit stop scoring, updated overtake model |
| `03_extract_features.py` | Tyre-compound features, relative pace normalization |
| `05_train_models.py` | Ranking objective, improved validation |
| `feature_engineering.py` | New relative pace features |
| `config/fantasy_scoring.py` | Pit stop priors reference |
| **New:** `data/seed/pit_stop_priors.json` | Per-team pit stop time distributions |
| **New:** `pipeline/03c_fetch_betting_odds.py` | Betting odds ingestion (Tier 2) |

---

## Competitive Analysis: f1fantasytools.com

**Their approach:** Qpace (weighted qualifying + FP results) → Rpace (+ overtake frequency) → Monte Carlo (N=10K) → violin plot distributions. No ML, no telemetry. Parametric model with manual tuning.

**Their strengths:** Sound simulation design, transparent methodology, 6,778-member Discord community, consistently top 0.05% of all F1 Fantasy players.

**Our advantages over them:** FastF1 telemetry data, ML-based predictions, automated pipeline, free website.

**Our disadvantages:** Less mature calibration (only 3 rounds of 2026 data), no betting odds integration.
