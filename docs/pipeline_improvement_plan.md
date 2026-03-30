# Pipeline Accuracy Improvement Plan

## Context

Our pipeline (Jolpica priors + FP telemetry → XGBoost → Monte Carlo) is a solid foundation but has methodological weaknesses that limit accuracy compared to the gold standard (f1fantasytools.com). This plan addresses the gaps identified through internal audit, competitive analysis, and research into F1 prediction best practices.

**Key finding:** f1fantasytools uses NO ML and NO telemetry — just weighted session results + parametric Monte Carlo (N=10K). Their edge comes from sound simulation design (proper noise modeling, track similarity weighting, comprehensive scoring). We have a data advantage (FastF1 telemetry) but are undermining it with simulation-layer issues.

**Goal:** Fix the simulation/scoring layer first (highest ROI), then improve the ML layer, then add new data signals.

---

## Diagnosis: What's Wrong Today

| Issue | Impact | Where |
|-------|--------|-------|
| **Quantile transform destroys pace gaps** — forces all position gaps equal, making frontrunner predictions too noisy and midfield too stable | HIGH | `08_monte_carlo_fantasy.py:543-552` |
| **No teammate correlation** — MC samples each driver independently, producing unrealistic team outcomes (e.g. P1 + P15 for same team) | HIGH | `08_monte_carlo_fantasy.py:266` |
| **Pit stop points completely missing** — 15-50+ constructor pts/race left on table | HIGH | `07_calculate_fantasy.py`, `08_monte_carlo_fantasy.py` |
| **Constructor MC is approximate** — sums driver means instead of per-iteration simulation | MEDIUM | `08_monte_carlo_fantasy.py:800-822` |
| **Regression target treats positions as continuous** — P1→P2 gap = P15→P16 gap, but scoring is hugely nonlinear | MEDIUM | `05_train_models.py` |
| **FP features mix tyre compounds** — soft qualifying sims averaged with hard race sims | MEDIUM | `03_extract_features.py` |
| **No relative pace normalization** — absolute lap times don't transfer across circuits | MEDIUM | `03_extract_features.py` |
| **Independent DNF sampling** — misses correlated incidents (first-lap pileups, team reliability) | LOW-MED | `08_monte_carlo_fantasy.py` |
| **No betting odds calibration** — missing a free, highly-informative signal | LOW-MED | Not implemented |
| **Confidence intervals uncalibrated** — no validation that P5-P95 captures 90% of outcomes | LOW | `08_monte_carlo_fantasy.py` |

---

## Plan: 3 Tiers, Ordered by Impact/Effort

### Tier 1: Fix the Monte Carlo Simulation (Highest ROI)

These changes fix fundamental methodology issues in the simulation layer. No ML retraining needed.

#### 1.1 Replace quantile transform with gap-preserving noise model
**File:** `08_monte_carlo_fantasy.py`

**Current:** Raw XGBoost scores → quantile transform (evenly spaced) → add Gaussian noise → re-rank.
**Problem:** If XGBoost says P1 is way ahead but P8-P12 are bunched, the quantile transform erases that — making upsets equally likely everywhere.

**New approach:**
- Keep raw XGBoost scores (which encode performance gaps)
- Normalize scores to a standard scale per session (z-score)
- Add calibrated noise proportional to driver-specific uncertainty:
  - `noise_std = base_noise * (1 + position_uncertainty_factor)`
  - `position_uncertainty_factor` derived from confidence score + position (backmarkers more variable)
- Re-rank from noisy scores → natural position assignments
- The performance gaps in the raw scores now determine swap probabilities: tightly-bunched drivers swap often, dominant drivers rarely upset

#### 1.2 Add teammate correlation to MC sampling
**File:** `08_monte_carlo_fantasy.py`

**Current:** Each driver's noise is independent.
**New approach:**
- Draw a **team-level shock** per team per simulation (shared component): `team_noise ~ N(0, team_sigma)`
- Draw an **individual shock** per driver: `driver_noise ~ N(0, driver_sigma)`
- Combined: `total_noise = alpha * team_noise + (1-alpha) * driver_noise`
- `alpha ~ 0.3-0.4` (calibrate from historical teammate correlation data)
- This naturally produces realistic team outcomes (both drivers up or both down together, with individual variation)

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

#### 2.1 Switch to ranking objective
**File:** `05_train_models.py`

**Current:** `objective="reg:squarederror"` — treats position as continuous number.
**New:** Use XGBoost's `objective="rank:pairwise"` (LambdaMART variant):
- Learns to rank drivers within each race correctly, not predict exact position numbers
- Group by `(year, round)` so the model learns "Driver A beats Driver B" rather than "Driver A finishes 3.2"
- Better handles the nonlinear nature of positions (P1 vs P2 gap matters more than P15 vs P16)
- Walk-forward validation metric: NDCG or Kendall's tau instead of MAE

**Fallback:** If rank:pairwise degrades performance (possible with our sample size), keep regression but add `log(position)` as target to compress the tail.

#### 2.2 Tyre-compound-aware feature extraction
**File:** `03_extract_features.py`

**Current:** All laps averaged together regardless of compound.
**New features:**
- `soft_best_lap`, `soft_avg_lap` — qualifying simulation pace
- `medium_long_run_avg`, `hard_long_run_avg` — race pace by compound
- `medium_degradation_rate`, `hard_degradation_rate` — compound-specific deg
- Keep existing aggregate features as fallback when compound data is sparse

Requires reading the `Compound` column from FastF1 lap data (already available in the parquet files).

#### 2.3 Relative pace normalization
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

#### 2.5 Walk-forward validation improvements
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

#### 3.1 Track similarity weighting
- Classify circuits by characteristics (high/low downforce, street/permanent, overtaking difficulty)
- Weight historical results from similar tracks more heavily in rolling features
- f1fantasytools offers this as a user-adjustable slider — we could do it automatically

#### 3.2 Fuel-corrected practice pace
- Approximate fuel correction: ~0.035s/kg/lap (varies by circuit)
- Classify FP stints as low-fuel (qualifying sims) vs high-fuel (race sims) by lap time profile
- Apply correction to normalize comparisons

#### 3.3 Optimal team selection (integer linear programming)
- Given predicted fantasy points + confidence intervals, solve for the optimal 5-driver + 2-constructor team under the $100M budget constraint
- Consider chip deployment strategy across the season
- Several open-source projects implement this successfully

#### 3.4 Price change prediction
- f1fantasytools reverse-engineered the F1 Fantasy pricing algorithm
- Model expected price changes to help users grow budget early in season
- Valuable for long-term league performance

#### 3.5 Weather integration
- Incorporate weather forecasts to adjust predictions for wet sessions
- Use `driver_wet_skill` rating (already exists in 03b but unused)

---

## Implementation Order

```
Week 1:  1.1 (gap-preserving noise) + 1.3 (pit stops)
Week 2:  1.2 (teammate correlation) + 1.4 (constructor per-iteration MC)
Week 3:  1.5 (correlated DNF) + 2.3 (relative pace normalization)
Week 4:  2.2 (tyre-compound features) + 2.5 (validation improvements)
Week 5:  2.1 (ranking objective) + 2.4 (betting odds)
Ongoing: Tier 3 items as time permits
```

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

**Our disadvantages:** Simulation layer issues (quantile transform, missing pit stops, no correlation), less mature calibration.
