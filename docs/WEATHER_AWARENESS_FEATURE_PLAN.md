# Weather-Awareness Feature Plan

**Status:** Planned. Filed 2026-05-23 after the R7 Canada prep highlighted the gap. To be implemented during a post-race break (priority: high — affects accuracy on every weekend where rain is plausible).

**Problem in one line:** The forecast is fetched and shown on the site, but **the model and the MC simulator both ignore it.** Wet races are predicted as if dry.

---

## What we already have

| Asset | Where | Status |
|---|---|---|
| Open-Meteo forecast pipeline | `pipeline/weather_forecast.py` | ✅ Works. Writes `web/public/data/weather.json` with per-day + per-session rain risk, precip probability, temps, wind, weather code. |
| `wet_skill` driver attribute | `config/team_driver_ratings.py` (`DRIVER_WET_WEATHER_SKILL`) → injected as feature in `03b_build_jolpica_features.py` | ⚠️ Present in all model feature lists (`quali_features`, `race_features`, `race_fp_features`, `sprint_features`). But useless because training data has no wet/dry label, so the gradient boost never learned to lean on it. |
| FastF1 weather data | `01_download_data.py` already downloads `session_weather` | ⚠️ Downloaded, not propagated into model inputs. The raw `weather_data` parquet exists per session but isn't aggregated into `model_data.parquet`. |

## What's broken

1. **No weather feature on the predictions row at inference.** `06_run_predictions.py` never reads `weather.json`. So the model can't know "this race is forecast wet."
2. **No wet/dry label on training rows.** `04_build_model_inputs.py` doesn't pull session weather into the feature table. So even if we plumbed forecast in at inference, the model wouldn't have learned how to use it.
3. **MC simulator is weather-blind.** `08_monte_carlo_fantasy.py` uses calibrated noise from `data/seed/mc_calibration.json` — a single global noise multiplier averaged across all completed races. Wet races have ~3× the DNF rate and much wider position variance, but the sim doesn't switch modes when forecast = rain.
4. **DNF features don't include weather context.** Risk ratings come from rolling DNF rates per driver/constructor. No "DNF rate in wet conditions" stratification.

---

## Level 2 — Weather-aware Monte Carlo (smaller, ship first)

**Goal:** When `weather.json::overall_rain_risk == HIGH`, widen the MC distribution and bump DNF rates so confidence intervals reflect rain reality even without retraining the model.

### Scope

- Read `web/public/data/weather.json` at the start of `08_monte_carlo_fantasy.py`.
- Map rain risk → multipliers:
  | rain_risk | position_noise × | dnf_rate × | wet_skill_weight | notes |
  |---|---|---|---|---|
  | NONE | 1.0 | 1.0 | 0 | normal |
  | LOW | 1.1 | 1.2 | 0.05 | moderate |
  | MEDIUM | 1.3 | 1.8 | 0.15 | meaningful chaos |
  | HIGH | 1.6 | 2.5 | 0.30 | full wet mode |
- Apply `wet_skill_weight × (wet_skill - 5)` as a per-driver score perturbation on each MC iteration (positive for wet maestros, negative for wet-weak drivers). Centered at 5 so an average-rated driver is unaffected.
- Multipliers are configurable in `MC_WEATHER_TUNABLES` block at top of the MC script.
- Document that this is a **heuristic widener** — not a re-trained model. CI bands widen, the median prediction shifts slightly toward wet-strong drivers, but the underlying deterministic prediction (Det Pts on the cards) stays the same.

### Why this is good first step

- Honest: it widens uncertainty rather than fabricating new mean predictions the model can't justify.
- Cheap: ~50 lines in one file. No retraining. No new training data infrastructure.
- Immediately visible: confidence intervals on driver cards widen on wet weekends — users see the band, not a misleading point estimate.
- Stepping stone: the same multiplier infrastructure feeds Level 3's training pipeline (we'll need similar mappings to label historical wet rows).

### Acceptance criteria

- For a forecast `HIGH` rain weekend, P5–P95 width on average expands ~40–60% vs dry forecast.
- Wet-skilled drivers (VER, HAM, ALO, NOR) see mc_total_mean shift up; rookies and wet-weak drivers shift down.
- DNF rate displayed on cards reflects the multiplier (HIGH risk → ~2–3× baseline DNF).
- A `weather_adjustments_active` field appears in the MC JSON for transparency.
- Comparison test: run MC twice on the same predictions, once with `rain_risk=NONE`, once with `rain_risk=HIGH`. Document the delta in a test report.

### Estimated effort

~1 weekend. The MC simulator already has noise plumbing; we're just adding a multiplier layer + reading a small JSON.

---

## Level 3 — Weather-conditioned model (bigger, ship second)

**Goal:** Train the quali / race / sprint models on **weather-labelled** historical rows so the model itself learns "when wet, weight wet_skill more, weight raw pace less, expect more grid shuffling."

### Scope

1. **Backfill historical weather conditions.** Iterate every session in `data/raw/fastf1/year{Y}/round{R}/`. The `session_weather.parquet` files already exist. Aggregate per-session:
   - `precip_avg_mm` (mean precip during session)
   - `precip_max_mm` (peak)
   - `track_temp_avg_C`
   - `air_temp_avg_C`
   - `was_wet_session` (bool: any precip > 0.5mm OR `Rainfall == True` for >10% of laps)
2. **Add weather feature columns** to `04_build_model_inputs.py`:
   - `was_wet_race`, `was_wet_quali`, `precip_total_mm`, `track_temp_avg`, `air_temp_avg`.
3. **Retrain** `05_train_models.py`. Validate via walk-forward that MAE doesn't regress on dry races. (Wet races are a small fraction of training — risk is the new features become noise rather than signal.)
4. **At inference, inject the forecast** into the prediction row in `06_run_predictions.py`. Read `weather.json`, map session forecast → feature values, write to `pred_df` before `model.predict`.
5. **Rebuild driver risk ratings** with wet-specific rolling DNF rates (`config/team_driver_ratings.py` already structured this way; just need historical data labelling).

### Risks

- **Training-set imbalance:** dry races vastly outnumber wet ones (~85/15). Models may underweight wet features. Mitigation: oversample wet rows in training, or use focal-loss-style reweighting.
- **Forecast vs reality mismatch:** the forecast at quali lock is 36h out and noisy. Model is trained on what actually happened. The forecast accuracy itself becomes a bottleneck — Open-Meteo on race-day forecast is generally good (±10% precip prob) but not perfect.
- **Adds inference dependency:** `weather.json` must exist when `06_run_predictions.py` runs. Need a fallback to "assume dry" if forecast missing.
- **Feature leakage check:** the wet-skill feature is per-driver constant, not per-race-conditional. With the new wet/dry label, the model can finally learn the interaction. But we have to be careful not to leak post-race weather info (use FORECAST as of session time, not actuals).

### Acceptance criteria

- Walk-forward backtest MAE on RACE position improves by ≥0.3 positions on wet races, doesn't regress more than 0.1 on dry races.
- Wet-skilled drivers get explicitly higher predicted positions on wet rounds vs the current model.
- A new metadata field in `predictions.json` indicates which forecast values were injected.
- Calibration: actual wet-race DNF rates from 2020-2025 match the model's predicted wet-race DNF probabilities within 5pp.

### Estimated effort

1–2 weekends end-to-end:
- 0.5–1 day: weather backfill + feature column wiring
- 0.5 day: retraining + walk-forward validation
- 0.5 day: inference plumbing + fallback
- 0.5 day: validation + calibration check

### Stretch (Level 3.5): DNF-by-weather risk model

The user specifically flagged this: **historical DNF correlated with weather AND track** would let us materially upgrade the risk component. A dedicated logistic / gradient-boost classifier predicting per-driver DNF probability given `(driver_id, constructor_id, was_wet_race, track_id, track_temp, recent_DNF_rate)` would be a small focused model that materially improves the fantasy-points-at-risk calculation. Feeds the MC simulator's DNF sampling step directly.

---

## Implementation order

1. **Level 2 first** (1 weekend) — ships immediate accuracy gain on uncertainty, validates the weather→model pipeline plumbing.
2. **Level 3** (1-2 weekends) — proper fix. Builds on Level 2's `MC_WEATHER_TUNABLES` for the historical labeller.
3. **Level 3.5 DNF model** as a stretch goal once Level 3 is verified.

---

## Where this builds from

- Existing `pipeline/weather_forecast.py` — already produces `weather.json` with per-day + per-session rain risk.
- Existing `wet_skill` feature (currently dormant, will become actively used).
- Existing FastF1 `session_weather.parquet` per-round files — the historical weather data is already on disk, just not in model inputs.
- `data/seed/mc_calibration.json` — the existing global noise multiplier pattern. Level 2 adds a weather-conditional multiplier on top of it.
