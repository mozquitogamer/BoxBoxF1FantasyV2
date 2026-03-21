# BoxBoxF1Fantasy — Operations Guide

**A complete step-by-step guide to running the F1 Fantasy prediction system.**

Someone with zero knowledge of the internals should be able to follow this document and produce predictions, update the website, and perform post-race analysis for any race weekend.

---

## Table of Contents

1. [Prerequisites & Setup](#1-prerequisites--setup)
2. [Season Calendar & Key Dates](#2-season-calendar--key-dates)
3. [Race Weekend Timeline](#3-race-weekend-timeline)
4. [Phase 1: Pre-FP (Before Free Practice)](#4-phase-1-pre-fp)
5. [Phase 2: Post-FP (After Free Practice Sessions)](#5-phase-2-post-fp)
6. [Phase 3: Post-Qualifying / Pre-Race](#6-phase-3-post-qualifying)
7. [Phase 4: Post-Race](#7-phase-4-post-race)
8. [Updating the Website](#8-updating-the-website)
9. [Retraining Models](#9-retraining-models)
10. [Sprint Weekend Differences](#10-sprint-weekend-differences)
11. [Manual Data Updates](#11-manual-data-updates)
12. [Troubleshooting](#12-troubleshooting)
13. [Quick Reference Commands](#13-quick-reference-commands)

---

## 1. Prerequisites & Setup

### Environment

```bash
# Python 3.10+ required
python --version

# Install dependencies
pip install -r requirements.txt

# Key packages: fastf1, xgboost, scikit-learn, pandas, numpy, requests, joblib, pyarrow
```

### Project Location

```
D:\OneDrive\BoxBoxF1FantasyV2\
```

All commands below assume you're in this directory.

### Verify Trained Models Exist

Before generating predictions, trained models must exist:

```
models/trained/quali_model.pkl    (~1.4 MB)
models/trained/race_model.pkl     (~1.5 MB)
models/trained/fp_model.pkl       (~2.0 MB)
```

If these don't exist, see [Section 9: Retraining Models](#9-retraining-models).

### Verify Seed Data

Static reference files that rarely change (update at season start or when prices change):

```
data/seed/races.json            # 2026 calendar (24 races)
data/seed/drivers.json          # 22 driver roster
data/seed/constructors.json     # 11 teams
data/seed/driver_ids.json       # ID mappings across data sources
data/seed/fantasy_prices.json   # Current F1 Fantasy prices
data/seed/dotd_winners.json     # Driver of the Day winners (update after each race)
```

---

## 2. Season Calendar & Key Dates

### 2026 F1 Calendar

| Round | Race | Date | Sprint? | Status |
|-------|------|------|---------|--------|
| 1 | Australian GP (Melbourne) | Mar 8 | No | Completed |
| 2 | Chinese GP (Shanghai) | Mar 15 | Yes | Completed |
| 3 | Japanese GP (Suzuka) | Mar 29 | No | Upcoming |
| 4 | ~~Bahrain GP~~ | ~~Apr 12~~ | - | Cancelled |
| 5 | ~~Saudi Arabian GP~~ | ~~Apr 19~~ | - | Cancelled |
| 6 | Miami GP | May 3 | Yes | - |
| 7 | Canadian GP | May 24 | No | - |
| 8 | Monaco GP | Jun 7 | No | - |
| 9 | Spanish GP (Barcelona) | Jun 14 | No | - |
| 10 | Austrian GP (Spielberg) | Jun 28 | Yes | - |
| 11 | British GP (Silverstone) | Jul 5 | No | - |
| 12 | Belgian GP (Spa) | Jul 19 | No | - |
| 13 | Hungarian GP (Budapest) | Jul 26 | No | - |
| 14 | Dutch GP (Zandvoort) | Aug 23 | No | - |
| 15 | Italian GP (Monza) | Sep 6 | No | - |
| 16 | Spanish GP (Madrid) | Sep 13 | No | - |
| 17 | Azerbaijan GP (Baku) | Sep 26 | No | - |
| 18 | Singapore GP | Oct 11 | No | - |
| 19 | US GP (Austin) | Oct 25 | Yes | - |
| 20 | Mexican GP | Nov 1 | No | - |
| 21 | Brazilian GP (Sao Paulo) | Nov 8 | Yes | - |
| 22 | Las Vegas GP | Nov 21 | No | - |
| 23 | Qatar GP (Lusail) | Nov 29 | Yes | - |
| 24 | Abu Dhabi GP (Yas Marina) | Dec 6 | No | - |

**Sprint Rounds:** 2, 6, 10, 19, 21, 23

---

## 3. Race Weekend Timeline

### Standard Weekend

| Day | Session | Your Action |
|-----|---------|-------------|
| Friday | FP1 (60 min) | Wait for session to end |
| Friday | FP2 (60 min) | Wait for session to end |
| Saturday AM | FP3 (60 min) | Run **Phase 2** (post-FP pipeline) |
| Saturday PM | Qualifying | Observe (optional Phase 3) |
| Sunday | Race | Run **Phase 4** (post-race) after race ends |

### Sprint Weekend

| Day | Session | Your Action |
|-----|---------|-------------|
| Friday AM | FP1 (60 min) | Only 1 FP session available |
| Friday PM | Sprint Qualifying | Run **Phase 2** before this if possible |
| Saturday AM | Sprint Race | - |
| Saturday PM | Qualifying | - |
| Sunday | Race | Run **Phase 4** after race ends |

**F1 Fantasy Lock Deadline:** Teams lock at qualifying start (or sprint qualifying start for sprint weekends). Get predictions published before then.

---

## 4. Phase 1: Pre-FP (Before Free Practice)

**When:** Before the weekend starts (e.g., Thursday or early Friday).
**Purpose:** Generate predictions using only historical priors (no FP data yet).

### Step 1: Download Jolpica Data for Previous Rounds

If new races have completed since last update:

```bash
python pipeline/01_download_data.py
# Select option: download current round Jolpica data
# This fetches race results, qualifying, pit stops for completed rounds
```

### Step 2: Update Jolpica Features (if new rounds completed)

```bash
python pipeline/03a_normalize_jolpica.py
python pipeline/03b_build_jolpica_features.py
```

This rebuilds the historical rolling averages with the latest race data.

### Step 3: Generate Pre-FP Predictions

```bash
python pipeline/06_run_predictions.py --round 3
# Replace 3 with the current round number
```

This generates predictions using Jolpica priors only (no FP telemetry). Confidence will be lower (~65-70%) since there's no FP data.

### Step 4: Calculate Fantasy Points

```bash
python pipeline/07_calculate_fantasy.py --round 3
```

### Step 5: Run Monte Carlo Simulation

```bash
python pipeline/08_monte_carlo_fantasy.py --round 3 --simulations 10000
```

### Step 6: Export to Website

```bash
python pipeline/08_export_website_json.py --round 3
```

### Step 7: Push to Website

```bash
git add web/public/data/
git commit -m "Pre-FP predictions for Round 3"
git push origin master
```

Vercel will auto-deploy from the push.

---

## 5. Phase 2: Post-FP (After Free Practice Sessions)

**When:** After FP sessions are complete. Ideally after FP3 on Saturday morning (standard weekend) or after FP1 on Friday (sprint weekend).
**Purpose:** Enhance predictions with real FP telemetry data. This is the most important prediction update.

### Step 1: Download FP Data

```bash
python pipeline/01_download_data.py
# Select: download current round FastF1 data
# This downloads FP1, FP2, FP3 session telemetry
```

Wait ~30 minutes after FP3 ends for FastF1 data to become available.

**Alternative (non-interactive):**
```bash
python pipeline/download_helper.py --mode fastf1_round --year 2026 --round 3
```

### Step 2: Build Clean Lap Data

```bash
python pipeline/02_build_laps.py
# Enter the round number when prompted
```

This cleans raw telemetry: removes in/out laps, safety car laps, normalizes tyre compounds.

### Step 3: Extract Performance Features

```bash
python pipeline/03_extract_features.py
# Enter the round number when prompted
```

Produces 23 features per driver: pace, consistency, degradation, long-run performance, sector times.

### Step 4: Generate Predictions (with FP data)

```bash
python pipeline/06_run_predictions.py --round 3
```

Now predictions incorporate FP telemetry. Confidence jumps to ~90%+ for drivers with FP data.

### Step 5: Calculate Fantasy Points

```bash
python pipeline/07_calculate_fantasy.py --round 3
```

### Step 6: Run Monte Carlo Simulation

```bash
python pipeline/08_monte_carlo_fantasy.py --round 3
```

### Step 7: Export to Website

```bash
python pipeline/08_export_website_json.py --round 3
```

### Step 8: Publish

```bash
git add web/public/data/
git commit -m "Post-FP predictions for Round 3 (Japanese GP)"
git push origin master
```

### Alternative: One-Command Pipeline

```bash
python publish_weekend.py
```

This runs steps 1-3 + 6-8 in sequence interactively. It checks for trained models and prompts for the round number.

---

## 6. Phase 3: Post-Qualifying

**When:** After qualifying ends (optional — predictions don't change, but you can run FP analysis).
**Purpose:** Generate FP analysis insights for the website.

```bash
python pipeline/10_fp_analysis.py --round 3
python pipeline/08_export_website_json.py --round 3
git add web/public/data/ && git commit -m "Add FP analysis for Round 3" && git push
```

---

## 7. Phase 4: Post-Race

**When:** After the race ends. Wait ~1 hour for data to be finalized.
**Purpose:** Record actual results, compare predictions vs. reality, update the website.

### Step 1: Download Race Results

```bash
python pipeline/01_download_data.py
# Download both FastF1 race data and Jolpica results for the round
```

### Step 2: Calculate Actual Fantasy Points

```bash
python pipeline/11_actual_fantasy_points.py --round 3
```

This uses official race results to compute what each driver/constructor actually scored.

### Step 3: Fetch Overtake Data

```bash
python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round 3
```

Gets official overtake counts from OpenF1 API.

### Step 4: Post-Race Analysis

```bash
python pipeline/09_post_race_analysis.py --round 3
```

Analyzes race pace, pit stops, tyre strategy, position changes.

### Step 5: Generate Pitstop Data for Website

The pitstop data for the website is extracted from the overtakes JSON. After running step 3, create/update the pitstop JSON:

```bash
# This is done automatically by 08_export_website_json.py
python pipeline/08_export_website_json.py --round 3
```

### Step 6: Update Seed Data

After each race, manually update:

1. **`data/seed/fantasy_prices.json`** — Update driver/constructor prices from fantasy.formula1.com
2. **`data/seed/dotd_winners.json`** — Add the Driver of the Day winner for this round

### Step 7: Export Everything to Website

```bash
python pipeline/08_export_website_json.py --round 3
```

### Step 8: Publish

```bash
git add web/public/data/ data/seed/
git commit -m "Post-race data for Round 3 (Japanese GP)"
git push origin master
```

### Step 9: Rebuild Jolpica Features (for next round)

After the race results are downloaded, rebuild historical features so the next round's predictions include this round's data:

```bash
python pipeline/03a_normalize_jolpica.py
python pipeline/03b_build_jolpica_features.py
```

---

## 8. Updating the Website

### How Deployment Works

1. All website data lives in `web/public/data/*.json`
2. Push changes to `origin/master` on GitHub
3. Vercel automatically deploys from GitHub
4. Site is live at **boxboxf1fantasy.com** within ~1 minute

### What Files Power the Website

| File | Content | When to Update |
|------|---------|----------------|
| `predictions.json` | Current round predictions | After Phase 2 (post-FP) |
| `predictions_round{N}.json` | Archived predictions per round | After Phase 2 |
| `season_summary.json` | Season standings, prices, calendar | After Phase 4 (post-race) |
| `actual_round{N}.json` | Actual fantasy points for round N | After Phase 4 |
| `post_race_round{N}.json` | Post-race analysis for round N | After Phase 4 |
| `fp_analysis.json` | FP session analysis | After Phase 3 |
| `pitstops_round{N}.json` | Pit stop times by constructor | After Phase 4 |

### Local Development

To preview the website locally:

```bash
python web/serve.py
# Opens at http://127.0.0.1:3000
```

Or use the desktop shortcut if one was created.

---

## 9. Retraining Models

**When to retrain:**
- After every 3-5 races (to incorporate new 2026 data)
- After regulation changes or major team shake-ups
- If prediction accuracy drops significantly

### Full Retraining Pipeline

```bash
# Step 1: Ensure all race data is downloaded
python pipeline/01_download_data.py

# Step 2: Normalize all Jolpica data (2020-2026)
python pipeline/03a_normalize_jolpica.py

# Step 3: Build rolling features from all seasons
python pipeline/03b_build_jolpica_features.py

# Step 4: Merge Jolpica priors + FP features into training dataset
python pipeline/04_build_model_inputs.py

# Step 5: Train models with walk-forward validation
python pipeline/05_train_models.py
```

After training, the script prints walk-forward MAE results:
- **Qualifying MAE target:** ~3.0 positions
- **Race MAE target:** ~3.5-4.0 positions

Models are saved to `models/trained/`.

### Experimental Model Tuning

```bash
python pipeline/05b_experiment_models.py
```

Tests different algorithms (XGBoost, LightGBM, Random Forest, stacking) and hyperparameters.

---

## 10. Sprint Weekend Differences

Sprint weekends have a compressed schedule and additional scoring:

### Schedule Differences
- Only **FP1** available (no FP2/FP3)
- Sprint Qualifying on Friday afternoon
- Sprint Race on Saturday morning
- Regular Qualifying on Saturday afternoon
- Race on Sunday

### Pipeline Differences
- Run Phase 2 after FP1 only (less data, lower confidence)
- Sprint scoring is included automatically when `is_sprint_weekend=True` in predictions
- Fantasy points calculation handles sprint separately (different point scale)
- Monte Carlo simulates sprint + race independently

### Sprint Scoring (2026 rules)
- Sprint Qualifying: same as regular qualifying points
- Sprint Race: P1=8pts down to P8=1pt (P9+=0)
- Sprint overtakes: +1 each
- Sprint fastest lap: +5pts
- Sprint DNF: -10pts (not -20 like main race)

---

## 11. Manual Data Updates

### Fantasy Prices (`data/seed/fantasy_prices.json`)

Update after each race. Get prices from fantasy.formula1.com:

```json
{
    "drivers": {
        "VER": 28.1,
        "RUS": 28.0,
        ...
    },
    "constructors": {
        "mercedes": 32.5,
        ...
    }
}
```

### Driver of the Day (`data/seed/dotd_winners.json`)

Add the winner after each race:

```json
{
    "1": "RUS",
    "2": "LEC",
    "3": "..."
}
```

### Lock Deadlines (`web/public/app.js`)

If F1 changes qualifying times, update the `LOCK_DEADLINES` array at the top of `app.js`. Times are in UTC.

### Track Classifications (`config/track_classifications.py`)

Update if a new circuit is added to the calendar. Each track needs 9 feature scores.

### Team/Driver Ratings (`config/team_driver_ratings.py`)

Update if driver transfers occur mid-season, or to adjust ratings based on performance.

---

## 12. Troubleshooting

### "No predictions available" on website
- Run `pipeline/08_export_website_json.py --round N`
- Check that `web/public/data/predictions.json` exists and is valid JSON

### FastF1 data not available
- Wait 30-60 minutes after session ends
- FastF1 sometimes has delays; check https://github.com/theOehrly/Fast-F1/issues
- Use `--cache` flag or check `data/fastf1_cache/`

### Model predictions seem wrong
- Check if models are trained on recent data
- Verify FP features are being loaded (check console output for "FP features found for N drivers")
- Re-run `03b_build_jolpica_features.py` to update historical priors

### Jolpica API errors
- API may be rate-limited; wait and retry
- Check https://api.jolpi.ca/ergast/ for status
- Historical data (2020-2025) only needs downloading once

### Monte Carlo simulation is slow
- Default is 10,000 simulations (~30-60 seconds)
- Reduce with `--simulations 5000` for faster results
- 10,000 provides stable P5/P95 estimates

### Website not updating after push
- Check Vercel dashboard for deployment status
- Verify `git push` succeeded (check `git log --oneline -1` matches remote)
- Hard refresh browser (Ctrl+Shift+R) to clear cache

### OpenF1 API not returning data
- OpenF1 data appears ~1-2 hours after race
- Some sessions may not have data; fall back to FastF1-based overtake detection

---

## 13. Quick Reference Commands

### Full Weekend Pipeline (Post-FP)

```bash
python pipeline/01_download_data.py          # Download FP data
python pipeline/02_build_laps.py              # Clean laps
python pipeline/03_extract_features.py        # Extract features
python pipeline/06_run_predictions.py --round N
python pipeline/07_calculate_fantasy.py --round N
python pipeline/08_monte_carlo_fantasy.py --round N
python pipeline/08_export_website_json.py --round N
git add web/public/data/ && git commit -m "Round N predictions" && git push
```

### Post-Race Pipeline

```bash
python pipeline/01_download_data.py          # Download race results
python pipeline/11_actual_fantasy_points.py --round N
python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round N
python pipeline/09_post_race_analysis.py --round N
python pipeline/08_export_website_json.py --round N
# Update fantasy_prices.json and dotd_winners.json manually
python pipeline/03a_normalize_jolpica.py     # Rebuild for next round
python pipeline/03b_build_jolpica_features.py
git add . && git commit -m "Post-race Round N" && git push
```

### Retrain Models

```bash
python pipeline/03a_normalize_jolpica.py
python pipeline/03b_build_jolpica_features.py
python pipeline/04_build_model_inputs.py
python pipeline/05_train_models.py
```

### Local Website Preview

```bash
python web/serve.py
# → http://127.0.0.1:3000
```

### Streamlit Dashboard

```bash
streamlit run dashboard/app.py
```
