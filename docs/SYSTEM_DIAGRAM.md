# BoxBoxF1Fantasy — System Diagrams

Visual representations of the entire system architecture, data flow, and race weekend workflow.

---

## 1. Complete System Architecture

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                           BOXBOXF1FANTASY SYSTEM                               ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  ┌─────────────────────────── DATA SOURCES ──────────────────────────────┐      ║
║  │                                                                      │      ║
║  │  ┌────────────┐     ┌─────────────┐     ┌────────────┐              │      ║
║  │  │  FastF1    │     │ Jolpica API │     │ OpenF1 API │              │      ║
║  │  │            │     │ (ex-Ergast) │     │            │              │      ║
║  │  │ • FP laps  │     │ • Results   │     │ • Overtake │              │      ║
║  │  │ • Sectors  │     │ • Quali     │     │   counts   │              │      ║
║  │  │ • Tyres    │     │ • Standings │     │ • Pit data │              │      ║
║  │  │ • Weather  │     │ • Pit stops │     │            │              │      ║
║  │  └─────┬──────┘     └──────┬──────┘     └─────┬──────┘              │      ║
║  │        │                   │                   │                    │      ║
║  └────────┼───────────────────┼───────────────────┼────────────────────┘      ║
║           │                   │                   │                           ║
║           ▼                   ▼                   │                           ║
║  ┌────────────────────────────────────────────┐   │                           ║
║  │           RAW DATA STORAGE                 │   │                           ║
║  │                                            │   │                           ║
║  │  data/raw/fastf1/year{Y}/round{R}/         │   │                           ║
║  │    ├── fp1.parquet                         │   │                           ║
║  │    ├── fp2.parquet                         │   │                           ║
║  │    ├── fp3.parquet                         │   │                           ║
║  │    └── race.parquet                        │   │                           ║
║  │                                            │   │                           ║
║  │  data/raw/jolpica/year{Y}/round{R}/        │   │                           ║
║  │    ├── results.json                        │   │                           ║
║  │    ├── qualifying.json                     │   │                           ║
║  │    ├── sprint.json                         │   │                           ║
║  │    └── pitstops.json                       │   │                           ║
║  └───────────┬────────────────────────────────┘   │                           ║
║              │                                    │                           ║
║              ▼                                    │                           ║
║  ┌──────────────────── PROCESSING ────────────────┼──────────────────────┐    ║
║  │                                                │                      │    ║
║  │  LAYER 1: JOLPICA PRIORS                       │                      │    ║
║  │  ┌──────────────────────┐                      │                      │    ║
║  │  │ 03a_normalize        │                      │                      │    ║
║  │  │  → normalized CSVs   │                      │                      │    ║
║  │  └──────────┬───────────┘                      │                      │    ║
║  │             ▼                                  │                      │    ║
║  │  ┌──────────────────────┐                      │                      │    ║
║  │  │ 03b_build_features   │                      │                      │    ║
║  │  │  → 91 rolling cols   │                      │                      │    ║
║  │  │  → ~2,600 rows       │                      │                      │    ║
║  │  │  (2020-2025 + 2026)  │                      │                      │    ║
║  │  └──────────┬───────────┘                      │                      │    ║
║  │             │                                  │                      │    ║
║  │  LAYER 2: FP TELEMETRY                         │                      │    ║
║  │  ┌──────────────────────┐                      │                      │    ║
║  │  │ 02_build_laps        │                      │                      │    ║
║  │  │  → clean lap data    │                      │                      │    ║
║  │  └──────────┬───────────┘                      │                      │    ║
║  │             ▼                                  │                      │    ║
║  │  ┌──────────────────────┐                      │                      │    ║
║  │  │ 03_extract_features  │                      │                      │    ║
║  │  │  → 23 pace features  │                      │                      │    ║
║  │  │  (per-driver)        │                      │                      │    ║
║  │  └──────────┬───────────┘                      │                      │    ║
║  │             │                                  │                      │    ║
║  │             ▼                                  │                      │    ║
║  │  ┌──────────────────────────────┐              │                      │    ║
║  │  │  04_build_model_inputs       │              │                      │    ║
║  │  │  Layer 1 + Layer 2 → merged  │              │                      │    ║
║  │  │  ~100 features, NaN-aware    │              │                      │    ║
║  │  │  2026 weighted 2.5x          │              │                      │    ║
║  │  └──────────┬───────────────────┘              │                      │    ║
║  │             │                                  │                      │    ║
║  └─────────────┼──────────────────────────────────┼──────────────────────┘    ║
║                │                                  │                           ║
║                ▼                                  │                           ║
║  ┌──────────────────── ML TRAINING ──────────────────────────────────────┐    ║
║  │                                                                       │    ║
║  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │    ║
║  │  │ QUALI MODEL     │  │ RACE MODEL      │  │ SPRINT MODEL    │       │    ║
║  │  │ XGBoost         │  │ XGBoost         │  │ XGBoost         │       │    ║
║  │  │ 1200 trees      │  │ 650 trees       │  │ 400 trees       │       │    ║
║  │  │ depth=3, lr=.025│  │ depth=5, lr=.03 │  │ depth=4, lr=.035│       │    ║
║  │  │ target: quali   │  │ target: race    │  │ target: sprint  │       │    ║
║  │  │ position        │  │ position        │  │ (501 rows)      │       │    ║
║  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘       │    ║
║  │           │                    │                     │                │    ║
║  │           └────────────────────┼─────────────────────┘                │    ║
║  │                    Walk-forward validation                            │    ║
║  │             [2020..N] train → [N+1] test                             │    ║
║  │                                                                       │    ║
║  │  ┌─────────────────┐                                                 │    ║
║  │  │ FP SIGNAL MODEL │  ExtraTrees, 500 trees, depth=6                 │    ║
║  │  │ (confidence only)│  Used only for confidence scoring               │    ║
║  │  └────────┬────────┘                                                 │    ║
║  │                                                                       │    ║
║  └────────────────────────┬──────────────────────────────────────────────┘    ║
║                           │                                                   ║
║                           ▼                                                   ║
║  ┌──────────────────── PREDICTION ───────────────────────────────────────┐    ║
║  │                                                                       │    ║
║  │  06_run_predictions.py                                                │    ║
║  │  ┌─────────────────────────────────────────────────────────────┐      │    ║
║  │  │  Jolpica priors + FP features (if available)                │      │    ║
║  │  │          │                                                  │      │    ║
║  │  │          ▼                                                  │      │    ║
║  │  │  Predict Quali Positions (rank model scores)                │      │    ║
║  │  │          │                                                  │      │    ║
║  │  │          ▼                                                  │      │    ║
║  │  │  Build race features (using predicted quali as input)       │      │    ║
║  │  │          │                                                  │      │    ║
║  │  │          ▼                                                  │      │    ║
║  │  │  Predict Race Positions                                     │      │    ║
║  │  │          │                                                  │      │    ║
║  │  │          ▼                                                  │      │    ║
║  │  │  Calculate Confidence (data + model agreement)              │      │    ║
║  │  └─────────────────────────────────────────────────────────────┘      │    ║
║  │                                                                       │    ║
║  └────────────────────────┬──────────────────────────────────────────────┘    ║
║                           │                                                   ║
║                           ▼                                                   ║
║  ┌──────────────────── FANTASY SCORING ──────────────────────────────────┐    ║
║  │                                                                       │    ║
║  │  07_calculate_fantasy.py                                              │    ║
║  │  ┌───────────────────────────────────────────────────────┐            │    ║
║  │  │  DRIVERS:                                             │            │    ║
║  │  │  quali_pts + race_pts + overtake_pts + FL_bonus       │◄───────────┼────┤
║  │  │  + DOTD_bonus + pos_change_pts - DNF_risk             │  overtakes │    │
║  │  │  + sprint_pts (if sprint weekend)                     │  from      │    │
║  │  │                                                       │  OpenF1    │    │
║  │  │  CONSTRUCTORS:                                        │            │    │
║  │  │  driver1_pts + driver2_pts (excl DOTD)                │            │    │
║  │  │  + quali_bonus + pitstop_bonus                        │            │    │
║  │  └───────────────────────────────────────────┬───────────┘            │    ║
║  │                                              │                        │    ║
║  └──────────────────────────────────────────────┼────────────────────────┘    ║
║                                                 │                             ║
║                                                 ▼                             ║
║  ┌──────────────────── MONTE CARLO ──────────────────────────────────────┐    ║
║  │                                                                       │    ║
║  │  08_monte_carlo_fantasy.py (10,000 simulations)                       │    ║
║  │  ┌───────────────────────────────────────────────────────┐            │    ║
║  │  │  For each simulation:                                 │            │    ║
║  │  │    1. Add calibrated noise to model scores            │            │    ║
║  │  │    2. Re-rank to get sampled positions                │            │    ║
║  │  │    3. Sample DNFs (per-driver probability)            │            │    ║
║  │  │    4. Sample overtakes (grid-based distribution)      │            │    ║
║  │  │    5. Sample FL & DOTD (weighted random)              │            │    ║
║  │  │    6. Calculate full fantasy points                   │            │    ║
║  │  │                                                       │            │    ║
║  │  │  Output: P5, P25, P50, P75, P95 per driver            │            │    ║
║  │  │  + prob_top3, prob_top5, prob_top10                   │            │    ║
║  │  │  + upside/downside risk metrics                       │            │    ║
║  │  └───────────────────────────────────────────────────────┘            │    ║
║  │                                                                       │    ║
║  └────────────────────────┬──────────────────────────────────────────────┘    ║
║                           │                                                   ║
║                           ▼                                                   ║
║  ┌──────────────────── WEB EXPORT ───────────────────────────────────────┐    ║
║  │                                                                       │    ║
║  │  08_export_website_json.py                                            │    ║
║  │                                                                       │    ║
║  │  ┌─────────────────────────────────────────────────────────┐          │    ║
║  │  │  web/public/data/                                       │          │    ║
║  │  │  ├── predictions.json          (current round)          │          │    ║
║  │  │  ├── predictions_round{N}.json (archive)                │          │    ║
║  │  │  ├── season_summary.json       (standings, prices)      │          │    ║
║  │  │  ├── actual_round{N}.json      (real results)           │          │    ║
║  │  │  ├── post_race_round{N}.json   (analysis)               │          │    ║
║  │  │  ├── fp_analysis.json          (FP breakdown)           │          │    ║
║  │  │  ├── track_data.json           (circuit features/maps)  │          │    ║
║  │  │  ├── driver_history.json       (actual pts history)     │          │    ║
║  │  │  └── pitstops_round{N}.json    (pit stop times)         │          │    ║
║  │  └─────────────────────┬───────────────────────────────────┘          │    ║
║  │                        │                                              │    ║
║  └────────────────────────┼──────────────────────────────────────────────┘    ║
║                           │                                                   ║
║                           ▼                                                   ║
║  ┌──────────────────── DEPLOYMENT ───────────────────────────────────────┐    ║
║  │                                                                       │    ║
║  │  git push → GitHub → Vercel → boxboxf1fantasy.com                     │    ║
║  │                                                                       │    ║
║  │  ┌─────────────────────────────────────────────────────┐              │    ║
║  │  │  WEBSITE FEATURES                                   │              │    ║
║  │  │  ├── Driver predictions (cards + table)             │              │    ║
║  │  │  ├── Constructor predictions (with scoring breakdown)│             │    ║
║  │  │  ├── Lineup optimizer (brute-force, 1.4M combos)    │              │    ║
║  │  │  ├── 6 chips: Limitless, 3x Boost, Wild Card,       │              │    ║
║  │  │  │   No Negative, Autopilot, Final Fix              │              │    ║
║  │  │  ├── Lock/exclude picks                             │              │    ║
║  │  │  ├── Price change predictions (PPM-based)           │              │    ║
║  │  │  ├── Monte Carlo confidence intervals               │              │    ║
║  │  │  ├── Post-race comparison (predicted vs actual)     │              │    ║
║  │  │  ├── Season standings & driver/constructor price     │              │    ║
║  │  │  │   trackers (current, starting, change, trend)    │              │    ║
║  │  │  ├── FP analysis (pace, degradation, sectors)       │              │    ║
║  │  │  ├── Multi-week transfer planner (beam search)      │              │    ║
║  │  │  ├── Accuracy dashboard (MAE, CI coverage)          │              │    ║
║  │  │  ├── Head-to-head matchup predictions               │              │    ║
║  │  │  └── Countdown timer to lock deadline               │              │    ║
║  │  └─────────────────────────────────────────────────────┘              │    ║
║  │                                                                       │    ║
║  └───────────────────────────────────────────────────────────────────────┘    ║
║                                                                                ║
╚════════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. Race Weekend Workflow

```
                         RACE WEEKEND TIMELINE
    ════════════════════════════════════════════════════════

    THURSDAY / EARLY FRIDAY
    ┌─────────────────────────────────────────────────────┐
    │  PHASE 1: PRE-FP PREDICTIONS (Optional)            │
    │                                                     │
    │  01_download → 03a/03b (if needed)                  │
    │       → 06_predict → 07_fantasy → 08_mc → 08_export │
    │                                                     │
    │  Uses: Jolpica priors only (no FP data)             │
    │  Confidence: ~65-70%                                │
    └────────────────────────┬────────────────────────────┘
                             │
                             ▼
    FRIDAY
    ┌─────────────────────────────────────────────────────┐
    │  FP1 (60 min) ─── wait for data ───┐               │
    │  FP2 (60 min) ─── wait for data ───┤               │
    │                                     │               │
    │  [Sprint weekends: Sprint Quali     │               │
    │   happens Friday PM — get           │               │
    │   predictions out before this!]     │               │
    └─────────────────────────────────────┼───────────────┘
                                          │
    SATURDAY MORNING                      │
    ┌─────────────────────────────────────┼───────────────┐
    │  FP3 (60 min) ─── wait 30 min ─────┘               │
    │                                                     │
    │  PHASE 2: POST-FP PREDICTIONS (Critical)            │
    │                                                     │
    │  01_download (FP data)                              │
    │       → 02_build_laps                               │
    │       → 03_extract_features                         │
    │       → 06_predict (now with FP!)                   │
    │       → 07_fantasy                                  │
    │       → 08_monte_carlo                              │
    │       → 08_export                                   │
    │       → git push (website live!)                    │
    │                                                     │
    │  Uses: Jolpica priors + FP telemetry                │
    │  Confidence: ~85-95%                                │
    │                                                     │
    │  ⚠️  MUST BE DONE BEFORE QUALIFYING START           │
    │     (F1 Fantasy lock deadline!)                     │
    └────────────────────────┬────────────────────────────┘
                             │
    SATURDAY PM              │
    ┌────────────────────────┼────────────────────────────┐
    │  QUALIFYING            │                            │
    │                        ▼                            │
    │  PHASE 3: FP ANALYSIS (Optional)                    │
    │  10_fp_analysis → 08_export → git push              │
    └────────────────────────┬────────────────────────────┘
                             │
    SUNDAY                   │
    ┌────────────────────────┼────────────────────────────┐
    │  RACE                  │                            │
    │                        ▼                            │
    │  Wait ~1 hour for data to finalize                  │
    │                                                     │
    │  PHASE 4: POST-RACE                                 │
    │                                                     │
    │  01_download (race results)                         │
    │       → 11_actual_fantasy (compute real scores)     │
    │       → 13_openf1_overtakes (official OT counts)    │
    │       → 09_post_race (pace analysis)                │
    │       → 08_export                                   │
    │       → Update fantasy_prices.json (manual)         │
    │       → Update dotd_winners.json (manual)           │
    │       → 03a/03b (rebuild features for next round)   │
    │       → git push                                    │
    └─────────────────────────────────────────────────────┘
```

---

## 3. Feature Layer Architecture

```
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    TRAINING DATA COMPOSITION                        │
    │                                                                     │
    │  ┌───────────────────────────────────────────────────────────────┐  │
    │  │  LAYER 1: JOLPICA PRIORS (91 columns, always populated)      │  │
    │  │                                                               │  │
    │  │  Rolling Stats          Season Stats        Track Features    │  │
    │  │  ┌──────────────┐      ┌──────────────┐    ┌──────────────┐  │  │
    │  │  │ quali_last   │      │ season_avg   │    │ is_street    │  │  │
    │  │  │ quali_roll_3 │      │ season_med   │    │ overtaking   │  │  │
    │  │  │ quali_roll_5 │      │ vs_field     │    │ corner_speed │  │  │
    │  │  │ race_roll_3  │      │ points_rate  │    │ straight_imp │  │  │
    │  │  │ race_roll_5  │      │ win_rate     │    │ downforce    │  │  │
    │  │  │ points_roll_3│      │ podium_rate  │    │ sc_prob      │  │  │
    │  │  │ dnf_rate_5   │      │ form_trend   │    │ grip_level   │  │  │
    │  │  │ mech_dnf_5   │      │ hot_streak   │    │ evolution    │  │  │
    │  │  │ teammate_gap │      │ dominant     │    │ turn1_risk   │  │  │
    │  │  └──────────────┘      └──────────────┘    └──────────────┘  │  │
    │  │                                                               │  │
    │  │  Circuit Experience    Ratings              Interactions      │  │
    │  │  ┌──────────────┐      ┌──────────────┐    ┌──────────────┐  │  │
    │  │  │ circuit_exp  │      │ tyre_mgmt    │    │ strategy×sc  │  │  │
    │  │  │ circuit_avg  │      │ wet_weather   │    │ top10×street │  │  │
    │  │  │ team_circuit │      │ overtaking   │    │ grid_penalty │  │  │
    │  │  │ season_prog  │      │ team_strategy│    │ form×track   │  │  │
    │  │  └──────────────┘      └──────────────┘    └──────────────┘  │  │
    │  └───────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │  ┌───────────────────────────────────────────────────────────────┐  │
    │  │  LAYER 2: FP TELEMETRY (23 columns, mostly NaN in training)  │  │
    │  │                                                               │  │
    │  │  ███████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │
    │  │  ▲ ~160 rows with data    ~2,500 rows NaN (XGBoost OK) ▲     │  │
    │  │                                                               │  │
    │  │  Pace            Consistency       Degradation    Sectors     │  │
    │  │  ┌────────────┐  ┌────────────┐   ┌───────────┐  ┌────────┐  │  │
    │  │  │ avg_lap    │  │ lap_std    │   │ deg_rate  │  │ s1_best│  │  │
    │  │  │ best_lap   │  │ lap_var    │   │ long_run  │  │ s2_best│  │  │
    │  │  │ median_lap │  │ cv         │   │ short_run │  │ s3_best│  │  │
    │  │  │ best_3_avg │  │            │   │ deg×laps  │  │ s1_avg │  │  │
    │  │  │ best_5_avg │  └────────────┘   └───────────┘  │ s2_avg │  │  │
    │  │  │ best_10_avg│                                   │ s3_avg │  │  │
    │  │  └────────────┘                                   └────────┘  │  │
    │  └───────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │  ┌───────────────────────────────────────────────────────────────┐  │
    │  │  ENGINEERED (cross-layer interactions)                        │  │
    │  │                                                               │  │
    │  │  prior_vs_fp_rank = jolpica_quali_prior - fp_pace_rank       │  │
    │  │  (If history says P5 but FP pace says P2 → strong signal)    │  │
    │  └───────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │  Total: ~2,600 rows × ~100 features                                │
    │  XGBoost tree_method="hist" handles NaN natively — no imputation   │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Fantasy Scoring Breakdown

```
    ┌─────────────────────────────────────────────────────────────────┐
    │               DRIVER FANTASY POINTS CALCULATION                 │
    │                                                                 │
    │   QUALIFYING                                                    │
    │   ┌──────────────────────────────────────────────────────┐      │
    │   │  P1:10  P2:9  P3:8  P4:7  P5:6  P6:5  P7:4  P8:3   │      │
    │   │  P9:2   P10:1  P11-P22:0   DSQ/No time: -5          │      │
    │   └──────────────────────────────────────────────────────┘      │
    │                          +                                      │
    │   RACE                                                          │
    │   ┌──────────────────────────────────────────────────────┐      │
    │   │  Position:  P1:25  P2:18  P3:15  P4:12  P5:10        │      │
    │   │             P6:8   P7:6   P8:4   P9:2   P10:1        │      │
    │   │             P11-P22: 0                                │      │
    │   │                                                      │      │
    │   │  Pos gained:    +1 per position gained               │      │
    │   │  Pos lost:      -1 per position lost                 │      │
    │   │  Overtakes:     +1 per overtake                      │      │
    │   │  Fastest lap:   +10                                  │      │
    │   │  DOTD:          +10                                  │      │
    │   │  DNF/DSQ:       -20                                  │      │
    │   └──────────────────────────────────────────────────────┘      │
    │                          +                                      │
    │   SPRINT (if sprint weekend)                                    │
    │   ┌──────────────────────────────────────────────────────┐      │
    │   │  Position:  P1:8  P2:7  ...  P8:1  P9+:0            │      │
    │   │  Pos gained/lost: ±1                                 │      │
    │   │  Overtakes: +1 each                                  │      │
    │   │  Fastest lap: +5                                     │      │
    │   │  DNF/DSQ: -10 (2026 rule change, was -20)            │      │
    │   └──────────────────────────────────────────────────────┘      │
    │                          =                                      │
    │   TOTAL DRIVER POINTS                                           │
    │                                                                 │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                 │
    │            CONSTRUCTOR FANTASY POINTS CALCULATION                │
    │                                                                 │
    │   ┌──────────────────────────────────────────────────────┐      │
    │   │  Driver 1 (quali + race + sprint) — excl DOTD        │      │
    │   │                    +                                  │      │
    │   │  Driver 2 (quali + race + sprint) — excl DOTD        │      │
    │   │                    +                                  │      │
    │   │  Qualifying Bonus:                                    │      │
    │   │    Both Q3: +10  │  One Q3: +5  │  Both Q2: +3       │      │
    │   │    One Q2: +1    │  Neither: -1                       │      │
    │   │                    +                                  │      │
    │   │  Expected Pit Stop Points (from team priors):         │      │
    │   │    <2.0s: +20  │  2.0-2.19s: +10  │  2.2-2.49s: +5   │      │
    │   │    2.5-2.99s: +2  │  Fastest pit: +5                  │      │
    │   │    World record (<1.80s): +15                         │      │
    │   │    (analytical EV from N(team_mean, team_std))        │      │
    │   │                    -                                  │      │
    │   │  DNF Impact (expected pts lost from DNF probability): │      │
    │   │    Both drivers' dnf_prob × soft_penalty              │      │
    │   └──────────────────────────────────────────────────────┘      │
    │                          =                                      │
    │   TOTAL CONSTRUCTOR POINTS                                      │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
```

---

## 5. File Dependency Graph

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                    PIPELINE SCRIPT DEPENDENCIES                  │
    │                                                                  │
    │    SEED DATA              CONFIG FILES                           │
    │    ┌──────────┐          ┌──────────────────┐                   │
    │    │drivers   │          │ settings.py      │                   │
    │    │races     │          │ fantasy_scoring   │                   │
    │    │prices    │          │ track_classify    │                   │
    │    │driver_ids│          │ team_ratings      │                   │
    │    └────┬─────┘          └────────┬─────────┘                   │
    │         │                         │                              │
    │         └─────────┬───────────────┘                              │
    │                   │                                              │
    │    ┌──────────────▼─────────────────┐                           │
    │    │     01_download_data.py        │  ← Entry point            │
    │    │     (FastF1 + Jolpica)         │                           │
    │    └──────────┬───────────┬─────────┘                           │
    │               │           │                                      │
    │         ┌─────▼──┐   ┌───▼───────────┐                         │
    │         │FastF1  │   │Jolpica JSON   │                         │
    │         │parquet │   │               │                         │
    │         └─┬──────┘   └───┬───────────┘                         │
    │           │              │                                      │
    │     ┌─────▼──────┐  ┌───▼────────────┐                         │
    │     │02_build    │  │03a_normalize   │                         │
    │     │_laps       │  │_jolpica        │                         │
    │     └─────┬──────┘  └───┬────────────┘                         │
    │           │              │                                      │
    │     ┌─────▼──────┐  ┌───▼────────────┐                         │
    │     │03_extract  │  │03b_build       │                         │
    │     │_features   │  │_jolpica_feats  │                         │
    │     └─────┬──────┘  └───┬────────────┘                         │
    │           │              │                                      │
    │           └──────┬───────┘                                      │
    │                  │                                              │
    │           ┌──────▼──────┐                                      │
    │           │04_build     │                                      │
    │           │_model_inputs│  ← Merges both layers                │
    │           └──────┬──────┘                                      │
    │                  │                                              │
    │           ┌──────▼──────┐                                      │
    │           │05_train     │  ← One-time / periodic               │
    │           │_models      │                                      │
    │           └──────┬──────┘                                      │
    │                  │                                              │
    │           ┌──────▼──────┐                                      │
    │           │06_run       │  ← Per-round                         │
    │           │_predictions │                                      │
    │           └──────┬──────┘                                      │
    │                  │                                              │
    │           ┌──────▼──────┐    ┌──────────────────┐              │
    │           │07_calculate │    │13_fetch_openf1   │              │
    │           │_fantasy     │◄───│_overtakes        │              │
    │           └──────┬──────┘    └──────────────────┘              │
    │                  │                                              │
    │         ┌────────┼────────┐                                     │
    │         │        │        │                                     │
    │   ┌─────▼───┐ ┌──▼─────┐ ┌▼────────────┐                      │
    │   │08_monte │ │08_exp  │ │11_actual    │                      │
    │   │_carlo   │ │_web_json│ │_fantasy_pts │                      │
    │   └────▲────┘ └────────┘ └──────┬──────┘                      │
    │        │                        │                              │
    │        │  ┌─────────────────────▼──────┐                       │
    │        │  │ calibrate_confidence.py    │                       │
    │        │  │ (MC predictions vs actuals)│                       │
    │        │  └─────────────┬─────────────┘                       │
    │        │                │                                      │
    │        │  mc_calibration.json                                   │
    │        └────────────────┘                                      │
    │                                                                │
    │              ┌───────────┐                                     │
    │              │ git push  │                                     │
    │              │ → Vercel  │                                     │
    │              │ → LIVE    │                                     │
    │              └───────────┘                                     │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
```

---

## 6. Model Prediction Flow (Single Driver)

```
    ┌─────────────────────────────────────────────────────────────┐
    │        PREDICTION FLOW FOR ONE DRIVER (e.g., VER)          │
    │                                                             │
    │  INPUTS:                                                    │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ Jolpica Priors:                                      │   │
    │  │   quali_roll_3 = 2.3    (avg P2.3 last 3 races)     │   │
    │  │   race_roll_3 = 1.7     (avg P1.7 last 3 races)     │   │
    │  │   circuit_avg = 3.0     (avg P3 at this track)       │   │
    │  │   dnf_rate_5 = 0.05     (5% DNF last 5 races)       │   │
    │  │   hot_streak = 1        (on a hot streak)            │   │
    │  │   ... (91 total features)                            │   │
    │  ├──────────────────────────────────────────────────────┤   │
    │  │ FP Telemetry (if available):                         │   │
    │  │   avg_lap = 89.234s     (average FP lap)             │   │
    │  │   best_lap = 88.912s    (best FP lap)                │   │
    │  │   degradation = 0.02    (tyre deg rate)              │   │
    │  │   long_run_avg = 90.1s  (race sim pace)              │   │
    │  │   ... (23 total features)                            │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                         │                                   │
    │                         ▼                                   │
    │  ┌──────────────────────────────────────┐                   │
    │  │ QUALI MODEL predicts raw score: 1.8  │                   │
    │  │ After ranking all 22 drivers: P2     │                   │
    │  └──────────────────┬───────────────────┘                   │
    │                     │                                       │
    │                     ▼                                       │
    │  ┌──────────────────────────────────────┐                   │
    │  │ RACE MODEL (uses predicted quali P2) │                   │
    │  │ raw score: 2.1                       │                   │
    │  │ After ranking: P2                    │                   │
    │  └──────────────────┬───────────────────┘                   │
    │                     │                                       │
    │                     ▼                                       │
    │  ┌──────────────────────────────────────────┐               │
    │  │ FANTASY SCORING                          │               │
    │  │                                          │               │
    │  │ Quali:  P2 → 9 pts                       │               │
    │  │ Race:   P2 → 18 pts                      │               │
    │  │ Pos change: P2 grid → P2 finish = 0 pts  │               │
    │  │ Overtakes: ~3 estimated → 3 pts          │               │
    │  │ FL prob: 15% × 10 = 1.5 pts              │               │
    │  │ DOTD prob: 8% × 10 = 0.8 pts             │               │
    │  │ DNF risk: 5% × -20 = -1.0 pts            │               │
    │  │                                          │               │
    │  │ TOTAL: 31.3 expected pts                  │               │
    │  │ Confidence: 93%                          │               │
    │  │ Risk: LOW                                │               │
    │  └──────────────────┬───────────────────────┘               │
    │                     │                                       │
    │                     ▼                                       │
    │  ┌──────────────────────────────────────────┐               │
    │  │ MONTE CARLO (10,000 sims)                │               │
    │  │                                          │               │
    │  │ P5:  8 pts    (worst 5% of outcomes)     │               │
    │  │ P25: 22 pts                              │               │
    │  │ P50: 32 pts   (median outcome)           │               │
    │  │ P75: 43 pts                              │               │
    │  │ P95: 53 pts   (best 5% of outcomes)      │               │
    │  │                                          │               │
    │  │ MC 90% CI: 8 — 53 pts                    │               │
    │  └──────────────────────────────────────────┘               │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```
