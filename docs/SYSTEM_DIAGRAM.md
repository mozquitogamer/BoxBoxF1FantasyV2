# BoxBoxF1Fantasy — System Diagrams

Visual representations of the pipeline, feature architecture, scoring, and the race-weekend workflow. For prose explanations of the same content, see [TECHNICAL_DEEP_DIVE.md](TECHNICAL_DEEP_DIVE.md). For operator workflow, see [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md).

---

## 1. Complete System Architecture

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                           BOXBOXF1FANTASY SYSTEM                                 ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  ┌─────────────────────────── DATA SOURCES ──────────────────────────────┐       ║
║  │                                                                       │       ║
║  │  ┌────────────┐    ┌─────────────┐    ┌────────────┐  ┌────────────┐  │       ║
║  │  │  FastF1    │    │ Jolpica API │    │ OpenF1 API │  │ Open-Meteo │  │       ║
║  │  │            │    │ (ex-Ergast) │    │            │  │ (weather)  │  │       ║
║  │  │ • FP laps  │    │ • Results   │    │ • Overtake │  │ • Per-     │  │       ║
║  │  │ • SQ laps  │    │ • Quali     │    │   counts   │  │   session  │  │       ║
║  │  │ • Sectors  │    │ • Sprint    │    │ • Pit data │  │   forecast │  │       ║
║  │  │ • Tyres    │    │ • Pit stops │    │            │  │            │  │       ║
║  │  └─────┬──────┘    └──────┬──────┘    └─────┬──────┘  └─────┬──────┘  │       ║
║  │        │                  │                 │               │         │       ║
║  └────────┼──────────────────┼─────────────────┼───────────────┼─────────┘       ║
║           │                  │                 │               │                 ║
║           ▼                  ▼                 │               ▼                 ║
║  ┌────────────────────────────────────────┐   │       ┌─────────────────┐        ║
║  │           RAW DATA STORAGE             │   │       │ weather.json    │        ║
║  │                                        │   │       │ (every 6h via   │        ║
║  │  data/raw/fastf1/year{Y}/round{R}/     │   │       │  GH Action)     │        ║
║  │    ├── fp1.parquet                     │   │       └─────────────────┘        ║
║  │    ├── fp2.parquet                     │   │                                  ║
║  │    ├── fp3.parquet                     │   │                                  ║
║  │    ├── sprint_qualifying.parquet       │   │                                  ║
║  │    ├── sprint.parquet                  │   │                                  ║
║  │    ├── qualifying.parquet              │   │                                  ║
║  │    └── race.parquet                    │   │                                  ║
║  │                                        │   │                                  ║
║  │  data/raw/jolpica/year{Y}/round{R}/    │   │                                  ║
║  │    ├── results.json                    │   │                                  ║
║  │    ├── qualifying.json                 │   │                                  ║
║  │    ├── sprint.json                     │   │                                  ║
║  │    └── pitstops.json                   │   │                                  ║
║  │                                        │   │                                  ║
║  │  ⚠️ Calendar mapping: FastF1 + Jolpica │   │                                  ║
║  │     compress around cancelled rounds.  │   │                                  ║
║  │     fastf1_round() in settings.py.     │   │                                  ║
║  └───────────┬────────────────────────────┘   │                                  ║
║              │                                │                                  ║
║              ▼                                │                                  ║
║  ┌──────────── PROCESSING ────────────────────┼──────────────────────┐           ║
║  │                                            │                      │           ║
║  │  LAYER 1: JOLPICA PRIORS                   │                      │           ║
║  │  ┌──────────────────────┐                  │                      │           ║
║  │  │ 03a_normalize        │                  │                      │           ║
║  │  │  → normalized CSVs   │                  │                      │           ║
║  │  └──────────┬───────────┘                  │                      │           ║
║  │             ▼                              │                      │           ║
║  │  ┌──────────────────────────┐              │                      │           ║
║  │  │ 03b_build_jolpica_       │              │                      │           ║
║  │  │ features                 │              │                      │           ║
║  │  │  → 91 rolling cols       │              │                      │           ║
║  │  │  → all_model_rows.parquet│              │                      │           ║
║  │  │  (~2,679 rows; 2020-2026)│              │                      │           ║
║  │  └──────────┬───────────────┘              │                      │           ║
║  │             │                              │                      │           ║
║  │  LAYER 2: FP TELEMETRY                     │                      │           ║
║  │  ┌──────────────────────┐                  │                      │           ║
║  │  │ 02_build_laps        │                  │                      │           ║
║  │  │  all_laps_fp{1,2,3}  │                  │                      │           ║
║  │  │  + sprint_qualifying │                  │                      │           ║
║  │  │  (sprint weekends)   │                  │                      │           ║
║  │  └──────────┬───────────┘                  │                      │           ║
║  │             ▼                              │                      │           ║
║  │  ┌──────────────────────┐                  │                      │           ║
║  │  │ 03_extract_features  │                  │                      │           ║
║  │  │  → 40+ pace features │                  │                      │           ║
║  │  │  (per-driver)        │                  │                      │           ║
║  │  │  Sprint quali laps   │                  │                      │           ║
║  │  │  EXCLUDED (only fed  │                  │                      │           ║
║  │  │  into Race Deep Dive)│                  │                      │           ║
║  │  └──────────┬───────────┘                  │                      │           ║
║  │             │                              │                      │           ║
║  │             ▼                              │                      │           ║
║  │  ┌──────────────────────────────┐          │                      │           ║
║  │  │  04_build_model_inputs       │          │                      │           ║
║  │  │  Layer 1 + Layer 2 → merged  │          │                      │           ║
║  │  │  ~100 features, NaN-aware    │          │                      │           ║
║  │  │  2026 weighted 2.5x          │          │                      │           ║
║  │  │  --exclude-after YYYY:N      │          │                      │           ║
║  │  └──────────┬───────────────────┘          │                      │           ║
║  │             │                              │                      │           ║
║  └─────────────┼──────────────────────────────┼──────────────────────┘           ║
║                │                              │                                  ║
║                ▼                              │                                  ║
║  ┌──────────────────── ML TRAINING ────────────────────────────────────────┐     ║
║  │                                                                         │     ║
║  │   05_train_models.py — produces 5 model files in models/trained/        │     ║
║  │                                                                         │     ║
║  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │     ║
║  │  │ QUALI MODEL     │  │ RACE MODEL      │  │ SPRINT MODEL    │          │     ║
║  │  │ XGBRanker       │  │ XGBRanker       │  │ XGBRanker       │          │     ║
║  │  │ 1200 trees      │  │ 650 trees       │  │ 400 trees       │          │     ║
║  │  │ depth=3, lr=.025│  │ depth=5, lr=.03 │  │ depth=4, lr=.035│          │     ║
║  │  │ 85 features     │  │ 101 features    │  │ 107 features    │          │     ║
║  │  │ target: quali   │  │ target: race    │  │ target: sprint  │          │     ║
║  │  │ position        │  │ position        │  │ position        │          │     ║
║  │  └────────┬────────┘  └────┬────────┬───┘  └────────┬────────┘          │     ║
║  │           │                │        │                │                   │     ║
║  │           │     ┌──────────▼────────▼──┐             │                   │     ║
║  │           │     │  Two race models:    │             │                   │     ║
║  │           │     │   race_model.json    │             │                   │     ║
║  │           │     │     (uses ACTUAL     │             │                   │     ║
║  │           │     │      quali — used    │             │                   │     ║
║  │           │     │      post-quali)     │             │                   │     ║
║  │           │     │   race_model_fp.json │             │                   │     ║
║  │           │     │     (uses walk-      │             │                   │     ║
║  │           │     │      forward         │             │                   │     ║
║  │           │     │      PREDICTED       │             │                   │     ║
║  │           │     │      quali — used    │             │                   │     ║
║  │           │     │      post-FP)        │             │                   │     ║
║  │           │     └──────────────────────┘             │                   │     ║
║  │           │                                          │                   │     ║
║  │           └──────────────────┬───────────────────────┘                   │     ║
║  │                              │                                           │     ║
║  │                  Walk-forward validation                                 │     ║
║  │             [2020..N] train → [N+1] test (5 folds)                       │     ║
║  │                                                                          │     ║
║  │  ┌─────────────────┐                                                     │     ║
║  │  │ FP SIGNAL MODEL │  ExtraTrees, 500 trees, depth=6                     │     ║
║  │  │ (confidence only)│  Used only for confidence scoring                  │     ║
║  │  └─────────────────┘                                                     │     ║
║  │                                                                          │     ║
║  └────────────────────────┬─────────────────────────────────────────────────┘     ║
║                           │                                                      ║
║                           ▼                                                      ║
║  ┌──────────────────── PREDICTION (06_run_predictions.py) ──────────────────┐    ║
║  │                                                                          │    ║
║  │  Phase-aware: detects whether ACTUAL quali is available                  │    ║
║  │   ├─ Yes → race_model.json                                               │    ║
║  │   └─ No  → race_model_fp.json                                            │    ║
║  │                                                                          │    ║
║  │  Predict-time feature recomputation:                                     │    ║
║  │   ├─ _recompute_sim_features (track-similarity-weighted rolling)         │    ║
║  │   └─ _recompute_circuit_features (driver/constructor circuit history)    │    ║
║  │                                                                          │    ║
║  │  ┌─────────────────────────────────────────────────────────────┐         │    ║
║  │  │  Build priors (Layer 1) + load FP features (Layer 2)        │         │    ║
║  │  │          │                                                  │         │    ║
║  │  │          ▼                                                  │         │    ║
║  │  │  Recompute sim_weighted_* and driver/constructor_circuit_*  │         │    ║
║  │  │          │                                                  │         │    ║
║  │  │          ▼                                                  │         │    ║
║  │  │  Predict Quali Positions (rank model scores)                │         │    ║
║  │  │          │                                                  │         │    ║
║  │  │          ▼                                                  │         │    ║
║  │  │  Build race features (using actual or predicted quali)      │         │    ║
║  │  │          │                                                  │         │    ║
║  │  │          ▼                                                  │         │    ║
║  │  │  Predict Race Positions                                     │         │    ║
║  │  │          │                                                  │         │    ║
║  │  │          ▼                                                  │         │    ║
║  │  │  Sprint inference (sprint weekends only — sprint_grid       │         │    ║
║  │  │  derived from FastF1 SQ; fastest-lap fallback when Ergast   │         │    ║
║  │  │  Position is NaN)                                           │         │    ║
║  │  │          │                                                  │         │    ║
║  │  │          ▼                                                  │         │    ║
║  │  │  Calculate Confidence (data + model agreement)              │         │    ║
║  │  └─────────────────────────────────────────────────────────────┘         │    ║
║  │                                                                          │    ║
║  └────────────────────────┬─────────────────────────────────────────────────┘    ║
║                           │                                                      ║
║                           ▼                                                      ║
║  ┌──────────────────── FANTASY SCORING (07) ────────────────────────────────┐    ║
║  │                                                                          │    ║
║  │  ┌───────────────────────────────────────────────────────┐               │    ║
║  │  │  DRIVERS:                                             │               │    ║
║  │  │  quali_pts + race_pts + overtake_pts + FL_bonus       │               │    ║
║  │  │  + DOTD_bonus + pos_change_pts - DNF_risk             │               │    ║
║  │  │  + sprint_pts (if sprint weekend)                     │               │    ║
║  │  │                                                       │               │    ║
║  │  │  CONSTRUCTORS:                                        │               │    ║
║  │  │  driver1_pts + driver2_pts (excl DOTD)                │               │    ║
║  │  │  + quali_bonus + expected_pitstop_pts - DNF_impact    │               │    ║
║  │  └───────────────────────────────────────────┬───────────┘               │    ║
║  │                                              │                           │    ║
║  └──────────────────────────────────────────────┼───────────────────────────┘    ║
║                                                 │                                ║
║                                                 ▼                                ║
║  ┌──────────────────── MONTE CARLO (08) ────────────────────────────────────┐    ║
║  │                                                                          │    ║
║  │  10,000 simulations:                                                     │    ║
║  │   1. Z-score raw scores → add team-correlated + individual noise         │    ║
║  │   2. Re-rank → sampled positions                                         │    ║
║  │   3. Two-stage DNF (multi-car incidents + team-correlated mech)          │    ║
║  │   4. Overtakes (driver history + grid bucket)                            │    ║
║  │   5. FL & DOTD (weighted random)                                         │    ║
║  │   6. Pit stops (per-team N(mu, sigma) → bracket)                         │    ║
║  │   7. Calculate full fantasy points                                       │    ║
║  │                                                                          │    ║
║  │  Output: P5/P25/P50/P75/P95 + prob_top_3/5/10                            │    ║
║  │  Calibration auto-loaded from data/seed/mc_calibration.json              │    ║
║  └────────────────────────┬─────────────────────────────────────────────────┘    ║
║                           │                                                      ║
║                           ▼                                                      ║
║  ┌──────────────────── WEB EXPORT (08_export_website_json) ─────────────────┐    ║
║  │                                                                          │    ║
║  │  Auto-syncs official points + price overrides from data/seed/.           │    ║
║  │                                                                          │    ║
║  │  ┌─────────────────────────────────────────────────────────┐             │    ║
║  │  │  web/public/data/                                       │             │    ║
║  │  │  ├── predictions.json          (current round)          │             │    ║
║  │  │  ├── predictions_round{N}.json (archive)                │             │    ║
║  │  │  ├── season_summary.json       (standings, prices)      │             │    ║
║  │  │  ├── actual_round{N}.json      (real results)           │             │    ║
║  │  │  ├── post_race_round{N}.json   (analysis)               │             │    ║
║  │  │  ├── deep_dive_round{N}.json   (detailed race breakdown)│             │    ║
║  │  │  ├── pitstops_round{N}.json    (stationary times)       │             │    ║
║  │  │  ├── fp_analysis.json          (FP/SQ analysis)         │             │    ║
║  │  │  ├── official_points.json      (synced from seed)       │             │    ║
║  │  │  ├── track_data.json           (9D feature vectors)     │             │    ║
║  │  │  ├── driver_history.json       (actual pts history)     │             │    ║
║  │  │  ├── weather.json              (Open-Meteo, every 6h)   │             │    ║
║  │  │  ├── articles.json             (manual articles)        │             │    ║
║  │  │  └── youtube_videos.json       (curation)               │             │    ║
║  │  └─────────────────────┬───────────────────────────────────┘             │    ║
║  │                        │                                                 │    ║
║  └────────────────────────┼─────────────────────────────────────────────────┘    ║
║                           │                                                      ║
║                           ▼                                                      ║
║  ┌──────────────────── DEPLOYMENT ──────────────────────────────────────────┐    ║
║  │                                                                          │    ║
║  │  git push → GitHub → Vercel → boxboxf1fantasy.com                        │    ║
║  │                                                                          │    ║
║  │  ┌─────────────────────────────────────────────────────┐                 │    ║
║  │  │  WEBSITE TABS                                       │                 │    ║
║  │  │  ├── Drivers, Constructors                          │                 │    ║
║  │  │  ├── Optimizer                                      │                 │    ║
║  │  │  │   ├── Lineup Optimizer (1.4M brute-force)        │                 │    ║
║  │  │  │   ├── Transfer Advisor (with penalty calc)       │                 │    ║
║  │  │  │   └── Multi-Week Planner (beam search, 2-5 rds)  │                 │    ║
║  │  │  ├── Season (standings + price tracker)             │                 │    ║
║  │  │  ├── H2H (matchup predictions)                      │                 │    ║
║  │  │  ├── Accuracy (drivers + constructors toggle)       │                 │    ║
║  │  │  ├── Race Deep Dive                                 │                 │    ║
║  │  │  ├── Videos, Articles, About                        │                 │    ║
║  │  │  └── Lock-deadline countdown                        │                 │    ║
║  │  └─────────────────────────────────────────────────────┘                 │    ║
║  │                                                                          │    ║
║  └──────────────────────────────────────────────────────────────────────────┘    ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. Race Weekend Workflow

The pipeline has 5 named phases. Operators run them via `pipeline/run_weekend.py --phase {phase} --round N`.

```
                      RACE WEEKEND TIMELINE — REGULAR & SPRINT
    ════════════════════════════════════════════════════════════════════

    PRE-SEASON or every 6+ races
    ┌──────────────────────────────────────────────────────────┐
    │  PHASE: pre_fp                                            │
    │                                                           │
    │  01_download → 03a_normalize → 03b_build_jolpica          │
    │      → 04_build_model_inputs --exclude-after Y:N          │
    │      → 05_train_models                                    │
    │                                                           │
    │  Outputs: models/trained/*.json                           │
    │  Caution: validate before promoting (compare MAE/tau      │
    │  to current production)                                   │
    └──────────────────────────────────────────────────────────┘

    MON-THU BEFORE WEEKEND (or any time before FP1)
    ┌──────────────────────────────────────────────────────────┐
    │  PHASE: pre_fp_predict                                    │
    │                                                           │
    │  01_download (current round)                              │
    │      → 03a_normalize --all → 03b_build --all              │
    │      → 06_predict (priors only, recomputes circuit feats) │
    │      → 07_fantasy → 08_mc → 08_export                     │
    │                                                           │
    │  Confidence: ~65-70%                                      │
    │  Use: directional reads, transfer planning                │
    └──────────────────────────────────────────────────────────┘
                             │
                             ▼
    FRIDAY (sprint weekend) or SATURDAY MORNING (regular)
    ┌──────────────────────────────────────────────────────────┐
    │  REGULAR WEEKEND: FP1 (Fri) → FP2 (Fri) → FP3 (Sat)       │
    │  SPRINT WEEKEND:  FP1 (Fri) → Sprint Quali (Fri) →        │
    │                   Sprint (Sat) → Quali (Sat)              │
    │                                                           │
    │  Wait ~30 min after final FP session                      │
    │                                                           │
    │  PHASE: post_fp                                           │
    │                                                           │
    │  01_download → 02_build_laps → 03_extract_features        │
    │      → 06_predict (uses race_model_fp.json)               │
    │      → 07_fantasy → 08_mc → 10_fp_analysis → 08_export    │
    │                                                           │
    │  Confidence: ~85-95%                                      │
    │  ⚠️ MUST PUBLISH BEFORE QUALIFYING LOCK                   │
    │     (Sat for regular, Sat or Fri for sprint)              │
    └──────────────────────────────────────────────────────────┘
                             │
                             ▼
    SAT PM (regular) or SAT (sprint)
    ┌──────────────────────────────────────────────────────────┐
    │  QUALIFYING ENDS                                          │
    │                                                           │
    │  PHASE: post_quali                                        │
    │                                                           │
    │  Same step list as post_fp, but 06_predict detects        │
    │  actual quali → switches to race_model.json (which was    │
    │  trained on real quali, not predicted).                   │
    │                                                           │
    │  Confidence: ~95%                                         │
    └──────────────────────────────────────────────────────────┘
                             │
                             ▼
    SUNDAY (race day)
    ┌──────────────────────────────────────────────────────────┐
    │  RACE                                                     │
    │                                                           │
    │  Wait ~1h for FastF1, ~3-5h for Jolpica                   │
    │                                                           │
    │  Pre-step: update data/seed/overtakes.csv with official   │
    │            F1 Fantasy overtake counts                     │
    │                                                           │
    │  PHASE: post_race                                         │
    │                                                           │
    │  01_download (race results)                               │
    │      → 09_post_race (predicted vs actual)                 │
    │      → 11_actual_fantasy (real fantasy points,            │
    │           applies overtakes.csv override)                 │
    │      → 11_race_deep_dive (detailed race analysis)         │
    │      → 12_count_overtakes (FastF1 detection)              │
    │      → 13_fetch_openf1_overtakes (OpenF1 detection)       │
    │      → 13_fetch_pitstop_stationary                        │
    │      → 08_export                                          │
    │                                                           │
    │  Post-step (manual):                                      │
    │   • Update data/seed/fantasy_prices.json                  │
    │   • Update data/seed/official_fantasy_points.json         │
    │   • Update data/seed/dotd_winners.json                    │
    │   • Re-run 08_export to push seed updates                 │
    │   • Run calibrate_confidence.py if 3+ rounds done         │
    │                                                           │
    │  git push → Vercel auto-deploys                           │
    └──────────────────────────────────────────────────────────┘

    JOLPICA LAG
    ─ If results.json returns "Races": [] after race, FastF1-derived
      analyses (race pace, tyre, overtakes, FP analysis) still
      populate. Re-run --phase post_race later when Jolpica catches up.
```

---

## 3. Feature Layer Architecture

```
    ┌───────────────────────────────────────────────────────────────────────┐
    │                   TRAINING DATA COMPOSITION                            │
    │                                                                        │
    │  ┌────────────────────────────────────────────────────────────────┐    │
    │  │  LAYER 1: JOLPICA PRIORS (~91 columns, always populated)       │    │
    │  │                                                                │    │
    │  │  Driver Rolling          Constructor Rolling      Teammate     │    │
    │  │  ┌──────────────┐       ┌──────────────────┐    ┌───────────┐  │    │
    │  │  │ quali_last   │       │ quali_last       │    │ team_     │  │    │
    │  │  │ quali_roll_3 │       │ roll_quali_3/5   │    │ delta_    │  │    │
    │  │  │ quali_roll_5 │       │ season_avg_quali │    │ last      │  │    │
    │  │  │ roll_finish_ │       │ recent_form      │    │ team_     │  │    │
    │  │  │   pos_3/5    │       └──────────────────┘    │ delta_    │  │    │
    │  │  │ roll_points_ │                                │ roll_3/5  │  │    │
    │  │  │   3/5        │                                └───────────┘  │    │
    │  │  └──────────────┘                                                │    │
    │  │                                                                  │    │
    │  │  Track-Sim Weighted     Circuit-Specific      DNF Rates           │    │
    │  │  (recomputed per         (recomputed per       ┌──────────────┐   │    │
    │  │   target circuit at      target circuit at     │ roll_dnf_    │   │    │
    │  │   predict time)          predict time —        │   rate_5     │   │    │
    │  │  ┌──────────────┐        new!)                 │ roll_mech_   │   │    │
    │  │  │ sim_weighted │       ┌──────────────────┐   │   dnf_5_     │   │    │
    │  │  │ _quali_3/5   │       │ driver_circuit_  │   │   driver/team│   │    │
    │  │  │ sim_weighted │       │   exp            │   │ roll_coll_   │   │    │
    │  │  │ _finish_3/5  │       │ driver_circuit_  │   │   dnf_5      │   │    │
    │  │  │ sim_weighted │       │   roll_3         │   │ roll_drv_err │   │    │
    │  │  │ _points_3/5  │       │ constructor_     │   │   _dnf_5     │   │    │
    │  │  └──────────────┘       │   circuit_exp    │   └──────────────┘   │    │
    │  │                          └──────────────────┘                     │    │
    │  │                                                                  │    │
    │  │  Track Features (9D)    Skill Ratings        Race-only            │    │
    │  │  ┌──────────────┐       ┌──────────────┐    ┌──────────────┐     │    │
    │  │  │ is_street    │       │ tyre_mgmt    │    │ is_pole_pos  │     │    │
    │  │  │ overtaking_  │       │ wet_weather  │    │ is_front_row │     │    │
    │  │  │   difficulty │       │ overtaking   │    │ is_top10_    │     │    │
    │  │  │ corner_speed │       │ team_strategy│    │   quali      │     │    │
    │  │  │ straight_imp │       └──────────────┘    │ grid_        │     │    │
    │  │  │ downforce    │                            │   advantage  │     │    │
    │  │  │ turn1_risk   │                            └──────────────┘     │    │
    │  │  │ sc_prob      │                            (added to race      │    │
    │  │  │ track_evo    │                            model only)          │    │
    │  │  │ grip_level   │                                                  │    │
    │  │  └──────────────┘                                                  │    │
    │  └────────────────────────────────────────────────────────────────┘    │
    │                                                                        │
    │  ┌────────────────────────────────────────────────────────────────┐    │
    │  │  LAYER 2: FP TELEMETRY (40+ columns, mostly NaN in training)   │    │
    │  │                                                                │    │
    │  │  ███████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    │    │
    │  │  ▲ ~160 rows with data    ~2,500 rows NaN (XGBoost OK) ▲        │    │
    │  │                                                                │    │
    │  │  Pace          Consistency       Degradation     Sectors        │    │
    │  │  ┌──────────┐  ┌────────────┐   ┌────────────┐  ┌───────────┐   │    │
    │  │  │ avg_lap  │  │ lap_std    │   │ deg_rate   │  │ s1_best   │   │    │
    │  │  │ best_lap │  │ lap_var    │   │ long_run_  │  │ s2_best   │   │    │
    │  │  │ median   │  │ cv         │   │   avg      │  │ s3_best   │   │    │
    │  │  │ best_3   │  └────────────┘   │ short_run_ │  │ s1_avg    │   │    │
    │  │  │ best_5   │                    │   best     │  │ s2_avg    │   │    │
    │  │  │ best_10  │                    └────────────┘  │ s3_avg    │   │    │
    │  │  └──────────┘                                    └───────────┘   │    │
    │  │                                                                  │    │
    │  │  Compound-specific      Pace Deltas (circuit-portable)           │    │
    │  │  ┌──────────────────┐   ┌────────────────────────────┐          │    │
    │  │  │ soft_best_lap    │   │ pace_delta_to_fastest      │          │    │
    │  │  │ soft_avg_lap     │   │ pace_delta_to_median       │          │    │
    │  │  │ medium_long_run  │   │ race_pace_delta_to_median  │          │    │
    │  │  │ hard_long_run    │   │ sector_N_delta_to_fastest  │          │    │
    │  │  │ medium_deg       │   │ long_run_delta_to_median   │          │    │
    │  │  │ hard_deg         │   └────────────────────────────┘          │    │
    │  │  └──────────────────┘                                           │    │
    │  └────────────────────────────────────────────────────────────────┘    │
    │                                                                        │
    │  ┌────────────────────────────────────────────────────────────────┐    │
    │  │  ENGINEERED (cross-layer, applied at predict time)             │    │
    │  │                                                                │    │
    │  │  prior_vs_fp_rank = jolpica_quali_prior - fp_pace_rank          │    │
    │  │   (If history says P5 but FP pace says P2 → strong signal)      │    │
    │  │                                                                  │    │
    │  │  soft_medium_gap, medium_hard_gap, soft_vs_overall_best          │    │
    │  │   (Compound interaction features)                               │    │
    │  └────────────────────────────────────────────────────────────────┘    │
    │                                                                        │
    │  Total: ~2,679 rows × ~100 features                                   │
    │  XGBoost tree_method="hist" handles NaN natively — no imputation       │
    │                                                                        │
    └───────────────────────────────────────────────────────────────────────┘
```

---

## 4. Fantasy Scoring Breakdown

```
    ┌─────────────────────────────────────────────────────────────────┐
    │               DRIVER FANTASY POINTS CALCULATION                  │
    │                                                                  │
    │   QUALIFYING                                                     │
    │   ┌──────────────────────────────────────────────────────┐       │
    │   │  P1:10  P2:9  P3:8  P4:7  P5:6  P6:5  P7:4  P8:3    │       │
    │   │  P9:2   P10:1  P11-P22:0   DSQ/No time: -5            │       │
    │   └──────────────────────────────────────────────────────┘       │
    │                          +                                       │
    │   RACE                                                           │
    │   ┌──────────────────────────────────────────────────────┐       │
    │   │  Position:  P1:25  P2:18  P3:15  P4:12  P5:10         │       │
    │   │             P6:8   P7:6   P8:4   P9:2   P10:1         │       │
    │   │             P11-P22: 0                                │       │
    │   │                                                       │       │
    │   │  Pos gained:    +1 per position gained                │       │
    │   │  Pos lost:      -1 per position lost                  │       │
    │   │  Overtakes:     +1 per overtake                       │       │
    │   │  Fastest lap:   +10                                   │       │
    │   │  DOTD:          +10                                   │       │
    │   │  DNF/DSQ:       -20                                   │       │
    │   └──────────────────────────────────────────────────────┘       │
    │                          +                                       │
    │   SPRINT (if sprint weekend)                                     │
    │   ┌──────────────────────────────────────────────────────┐       │
    │   │  Position:  P1:8  P2:7  ...  P8:1  P9+:0              │       │
    │   │  Pos gained/lost: ±1                                  │       │
    │   │  Overtakes: +1 each                                   │       │
    │   │  Fastest lap: +5                                      │       │
    │   │  DNF/DSQ: -10 (2026 rule, was -20)                    │       │
    │   └──────────────────────────────────────────────────────┘       │
    │                          =                                       │
    │   TOTAL DRIVER POINTS                                            │
    │                                                                  │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │            CONSTRUCTOR FANTASY POINTS CALCULATION                │
    │                                                                  │
    │   ┌──────────────────────────────────────────────────────┐       │
    │   │  Driver 1 (quali + race + sprint) — excl DOTD         │       │
    │   │                    +                                  │       │
    │   │  Driver 2 (quali + race + sprint) — excl DOTD         │       │
    │   │                    +                                  │       │
    │   │  Qualifying Bonus:                                    │       │
    │   │    Both Q3: +10  │  One Q3: +5  │  Both Q2: +3        │       │
    │   │    One Q2: +1    │  Neither: -1                       │       │
    │   │                    +                                  │       │
    │   │  Expected Pit Stop Points (analytical EV from         │       │
    │   │    N(team_mean, team_std)):                           │       │
    │   │    <2.0s: +20  │  2.0-2.19s: +10  │  2.2-2.49s: +5   │       │
    │   │    2.5-2.99s: +2  │  Fastest pit: +5                  │       │
    │   │    World record (<1.80s): +15                         │       │
    │   │                    -                                  │       │
    │   │  DNF Impact (expected pts lost from DNF probability)  │       │
    │   └──────────────────────────────────────────────────────┘       │
    │                          =                                       │
    │   TOTAL CONSTRUCTOR POINTS                                       │
    │                                                                  │
    │   Note: Constructor scoring uses BASE driver scores only —       │
    │   never boosted/multiplied (chip plays are a frontend concept).  │
    └─────────────────────────────────────────────────────────────────┘
```

---

## 5. File Dependency Graph

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                    PIPELINE SCRIPT DEPENDENCIES                 │
    │                                                                  │
    │    SEED DATA              CONFIG FILES                            │
    │    ┌──────────┐          ┌──────────────────┐                    │
    │    │drivers   │          │ settings.py      │                    │
    │    │races     │          │ fantasy_scoring  │                    │
    │    │prices    │          │ track_classify   │                    │
    │    │driver_ids│          │ team_ratings     │                    │
    │    │overtakes │          │ track_similarity │                    │
    │    │official  │          │ circuit_coords   │                    │
    │    │dotd      │          │ feature_eng      │                    │
    │    │mc_calib  │          └────────┬─────────┘                    │
    │    └────┬─────┘                   │                              │
    │         │                         │                              │
    │         └─────────┬───────────────┘                              │
    │                   │                                              │
    │    ┌──────────────▼─────────────────┐                            │
    │    │     01_download_data.py        │  ← Entry point             │
    │    │     (FastF1 + Jolpica)         │  Calendar mapping at the   │
    │    │     --mode current/historical  │  external API boundary     │
    │    └──────────┬───────────┬─────────┘                            │
    │               │           │                                       │
    │         ┌─────▼──┐   ┌───▼───────────┐                            │
    │         │FastF1  │   │Jolpica JSON   │                            │
    │         │parquet │   │               │                            │
    │         └─┬──────┘   └───┬───────────┘                            │
    │           │              │                                        │
    │     ┌─────▼──────┐  ┌───▼────────────┐                           │
    │     │02_build    │  │03a_normalize   │                           │
    │     │_laps       │  │_jolpica        │                           │
    │     │            │  │ (--year/--all) │                           │
    │     └─────┬──────┘  └───┬────────────┘                           │
    │           │              │                                        │
    │     ┌─────▼──────┐  ┌───▼────────────┐                           │
    │     │03_extract  │  │03b_build       │                           │
    │     │_features   │  │_jolpica_feats  │                           │
    │     │            │  │ (--year/--all) │                           │
    │     └─────┬──────┘  └───┬────────────┘                           │
    │           │              │                                        │
    │           └──────┬───────┘                                        │
    │                  │                                                │
    │           ┌──────▼──────────────┐                                 │
    │           │04_build             │  ← Merges layers,               │
    │           │_model_inputs        │    --exclude-after Y:N          │
    │           └──────┬──────────────┘                                 │
    │                  │                                                │
    │           ┌──────▼──────┐                                         │
    │           │05_train     │  ← One-time / periodic retrain          │
    │           │_models      │   (5 models: quali, race, race_fp,      │
    │           └──────┬──────┘    sprint, fp_signal)                   │
    │                  │                                                │
    │           ┌──────▼──────────────┐                                 │
    │           │06_run_predictions   │  ← Per-round, phase-aware       │
    │           │  - phase detection  │    (auto-switches race_model    │
    │           │  - circuit recomp   │    vs race_model_fp based on    │
    │           │  - sim recomp       │    actual-quali availability)   │
    │           └──────┬──────────────┘                                 │
    │                  │                                                │
    │           ┌──────▼──────┐                                         │
    │           │07_calculate │                                         │
    │           │_fantasy     │                                         │
    │           └──────┬──────┘                                         │
    │                  │                                                │
    │         ┌────────┼─────────┐                                      │
    │         │        │         │                                      │
    │   ┌─────▼───┐ ┌──▼──────┐ ┌▼──────────────┐ ┌──────────────┐     │
    │   │08_monte │ │08_exp   │ │11_actual_     │ │10_fp_         │     │
    │   │_carlo   │ │_web_json│ │ fantasy_pts   │ │ analysis      │     │
    │   └────▲────┘ └────┬────┘ │ (uses         │ │ (Race Deep    │     │
    │        │           │      │  overtakes.csv│ │  Dive page)   │     │
    │        │           │      │  override)    │ └───────────────┘     │
    │        │           │      └──────┬────────┘                        │
    │        │           │             │                                 │
    │        │           │             │  Post-race set:                  │
    │        │           │             │   09_post_race                  │
    │        │           │             │   11_race_deep_dive             │
    │        │           │             │   12_count_overtakes            │
    │        │           │             │   13_fetch_openf1_overtakes     │
    │        │           │             │   13_fetch_pitstop_stationary   │
    │        │           ▼             │                                 │
    │        │      ┌─────────────────────────────┐                     │
    │        │      │ calibrate_confidence.py     │                     │
    │        │      │ (MC predictions vs actuals  │                     │
    │        │      │  → mc_calibration.json)     │                     │
    │        │      └─────────────┬───────────────┘                     │
    │        │                    │                                      │
    │        │  mc_calibration.json                                     │
    │        └────────────────────┘                                     │
    │                                                                    │
    │              ┌───────────┐                                         │
    │              │ git push  │                                         │
    │              │ → Vercel  │                                         │
    │              │ → LIVE    │                                         │
    │              └───────────┘                                         │
    │                                                                    │
    │   Orchestrator: pipeline/run_weekend.py --phase {phase} --round N │
    │   Phases: pre_fp, pre_fp_predict, post_fp, post_quali, post_race  │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Single-Driver Prediction Flow

```
    ┌───────────────────────────────────────────────────────────────┐
    │           PREDICTION FLOW FOR ONE DRIVER (e.g., VER)           │
    │                                                                │
    │  INPUTS:                                                       │
    │  ┌──────────────────────────────────────────────────────────┐  │
    │  │ Layer 1 — Jolpica priors (always present):               │  │
    │  │   driver_roll_quali_3 = 9.5  (last 3 races: bad form)    │  │
    │  │   roll_finishpos_3 = 10.0    (mid-pack recent races)     │  │
    │  │   driver_circuit_exp = 1.5    (RECOMPUTED for target —   │  │
    │  │                                his career Canada quali   │  │
    │  │                                avg across 4 starts)      │  │
    │  │   sim_weighted_quali_3 = 7.0  (RECOMPUTED for target —   │  │
    │  │                                track-sim weighted)       │  │
    │  │   roll_dnf_rate_5 = 0.22     (22% rolling DNF)           │  │
    │  │   ... (91 total features)                                │  │
    │  ├──────────────────────────────────────────────────────────┤  │
    │  │ Layer 2 — FP telemetry (if post-FP phase):                │  │
    │  │   avg_lap_time = 89.234s                                  │  │
    │  │   best_lap_time = 88.912s                                 │  │
    │  │   degradation_rate = 0.02s/lap                            │  │
    │  │   long_run_avg = 90.1s                                    │  │
    │  │   pace_delta_to_fastest = 0.3                             │  │
    │  │   ... (40+ features; ALL NaN in pre_fp_predict phase)     │  │
    │  └──────────────────────────────────────────────────────────┘  │
    │                          │                                     │
    │                          ▼                                     │
    │  ┌──────────────────────────────────────────────────────┐      │
    │  │  Phase detection (06_run_predictions.py):            │      │
    │  │   - actual quali available? (Jolpica norm or FastF1) │      │
    │  │   - YES → race_model.json (trained on actual quali)  │      │
    │  │   - NO  → race_model_fp.json (trained on walk-       │      │
    │  │           forward predicted quali)                   │      │
    │  └──────────────────────────────────────────────────────┘      │
    │                          │                                     │
    │                          ▼                                     │
    │  ┌──────────────────────────────────────┐                      │
    │  │ QUALI MODEL → raw score: 1.12         │                      │
    │  │ Rank against 22 drivers → P7          │                      │
    │  └──────────────────┬───────────────────┘                      │
    │                     │                                          │
    │                     ▼                                          │
    │  ┌──────────────────────────────────────┐                      │
    │  │ RACE MODEL (uses predicted quali P7   │                      │
    │  │ if pre-quali, else actual)            │                      │
    │  │ Raw score: 0.97                       │                      │
    │  │ Rank → P7 race finish                 │                      │
    │  └──────────────────┬───────────────────┘                      │
    │                     │                                          │
    │                     ▼                                          │
    │  ┌──────────────────────────────────────────┐                  │
    │  │ FANTASY SCORING (07_calculate_fantasy)   │                  │
    │  │                                          │                  │
    │  │ Quali:  P7 → 4 pts                       │                  │
    │  │ Race:   P7 → 6 pts                       │                  │
    │  │ Pos change: P7 grid → P7 finish = 0      │                  │
    │  │ Overtakes: ~6 estimated → 6 pts          │                  │
    │  │ FL prob: 5% × 10 = 0.5 pts               │                  │
    │  │ DOTD prob: 3% × 10 = 0.3 pts             │                  │
    │  │ DNF risk: 22% × -20 = -4.4 pts           │                  │
    │  │ Sprint quali: 4 pts (sprint weekend)     │                  │
    │  │ Sprint race: -3.7 pts (predicted P10)    │                  │
    │  │                                          │                  │
    │  │ TOTAL: ~17 expected pts                  │                  │
    │  │ Confidence: 67% (no FP data yet)         │                  │
    │  │ Risk: MEDIUM (22% DNF)                   │                  │
    │  └──────────────────┬───────────────────────┘                  │
    │                     │                                          │
    │                     ▼                                          │
    │  ┌──────────────────────────────────────────┐                  │
    │  │ MONTE CARLO (08, 10K sims)               │                  │
    │  │                                          │                  │
    │  │ P5:  -17 pts  (5% of sims, includes DNFs)│                  │
    │  │ P25: -2 pts                              │                  │
    │  │ P50: 17 pts   (median)                   │                  │
    │  │ P75: 33 pts                              │                  │
    │  │ P95: 50 pts   (best 5% — strong race)    │                  │
    │  │                                          │                  │
    │  │ MC 90% CI: -17 — 50 pts                  │                  │
    │  │ Wide CI = high variance                  │                  │
    │  └──────────────────────────────────────────┘                  │
    │                                                                │
    └───────────────────────────────────────────────────────────────┘
```
