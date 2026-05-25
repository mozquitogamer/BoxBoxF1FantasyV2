# Weather Awareness — Level 3 Implementation Plan

**Status:** Planning only. No code written. Awaiting explicit user approval before implementation.
**Filed:** 2026-05-25, after Phase 1 of User Scenarios shipped.
**Supersedes the Level 3 section of:** `docs/WEATHER_AWARENESS_FEATURE_PLAN.md` (which was the high-level roadmap). This doc is the detailed plan for Level 3 only.

---

## 1. Goal (one line)

Train the qualifying / race / sprint models on historical sessions that are **labelled by actual weather conditions**, then **inject the live weather forecast** at inference time, so the model genuinely conditions its predictions on rain rather than ignoring it.

### What success looks like
- On wet-race weekends, the model's predicted finishing order shifts toward wet-skilled drivers automatically (no manual scenario bumps needed).
- Walk-forward backtest on wet races shows measurably better MAE than the current model.
- On dry-race weekends, MAE is at worst marginally worse than the current model (ideally unchanged).
- A user reading the Drivers tab on a rainy weekend sees predictions that reflect the forecast, with confidence intervals appropriately widened.

### What success does NOT look like
- Always-on "rain mode" that distorts dry predictions.
- A model that knows about weather only at training time but not inference time, or vice versa.
- Hidden assumptions ("if forecast missing, fabricate dry") that silently degrade accuracy when the weather plumbing breaks.

---

## 2. Why Level 3 (not Level 2)

User chose to skip Level 2 (a heuristic MC widener that fakes "wet mode" via fixed multipliers on noise + DNF rate). Reasons that justify going straight to the real fix:

- **Level 2's mean prediction is unchanged.** It only widens uncertainty. So the "Top Pick" / "Dark Horse" hero cards still display dry-race rankings on a rainy weekend.
- **Level 2 is throwaway code.** Its multipliers are guesses. Level 3 replaces them with learned coefficients.
- **The hard work is the same either way.** Both levels need: weather backfill, historical labelling, forecast plumbing into the codebase. Level 2 wastes the labelling effort on a heuristic; Level 3 reuses it for the actual model.

The trade-off: Level 3 takes longer to ship (1-2 weekends vs ~1 weekend) and carries retraining risk (could regress on dry races if the new features become noise). That risk is what most of the plan below addresses.

---

## 3. Plan — high-level shape

Four sequential phases. Each phase is independently testable; do not skip walk-forward validation between phases.

### Phase A — Historical weather backfill (1 day)
Produce a per-(season, round, session) Parquet recording the weather conditions that actually occurred. **No model changes yet.**

### Phase B — Feature wiring (0.5 day)
Plumb backfilled weather into `04_build_model_inputs.py` so training rows gain weather columns. **Still no model changes — verify columns land correctly first.**

### Phase C — Retraining + validation (0.5–1 day)
Retrain quali / race / race_fp / sprint models. **Mandatory walk-forward MAE check on dry races BEFORE shipping.** Roll back if dry MAE regresses by more than 0.1 positions.

### Phase D — Inference plumbing (0.5 day)
Read `weather.json` in `06_run_predictions.py`, map forecast → feature values on the prediction row, plus a sane fallback ("assume dry") when forecast is missing.

### Phase E — Recalibration (0.5 day)
Re-run `calibrate_confidence.py` on completed races so MC intervals reflect the new model's actual error distribution. Update the Changelog tab with a release note.

---

## 4. Detailed implementation

### Phase A — Historical weather backfill

**Where the data lives:**
- FastF1 cache has `weather_data.ff1pkl` per session for every race we have on disk (2020–2026). Verified by glob: `data/raw/fastf1/cache/**/weather_data.ff1pkl`.
- FastF1's `session.weather_data` DataFrame has these columns: `Time, AirTemp, Humidity, Pressure, Rainfall, TrackTemp, WindDirection, WindSpeed`. Rainfall is a boolean per timestamp (~1 sample/minute).
- We currently extract only mean `track_temperature` + `air_temperature` from this DataFrame in `01_download_data.py` (lines 139-144). Everything else is discarded.

**What to build:**
- New script `pipeline/03c_extract_session_weather.py` that walks the FastF1 cache and writes one Parquet per round per session.
- Output schema (one row per session): `season, round, session_name (FP1/FP2/FP3/Q/SQ/SR/R), was_wet (bool), precip_minutes (int), pct_session_wet (float), track_temp_avg, track_temp_min, track_temp_max, air_temp_avg, humidity_avg, wind_avg, n_samples`.
- "was_wet" definition: `Rainfall == True` for ≥10% of weather samples OR `precip_minutes >= 5`. This threshold matters — too low and damp-but-dry-line sessions get mis-labelled; too high and we miss short showers. The 10% threshold is a starting point, will tune based on what historical wet races we correctly identify (Silverstone 2024, Spa 2021, Brazil 2024 are obvious anchors).
- Idempotent: re-running shouldn't re-process already-computed sessions unless `--force`.

**Why a separate script (not bolt onto 01_download):**
- `01_download_data.py` is hot path on race weekends — adding weather aggregation slows it.
- This is a one-time backfill plus per-new-round update; cleaner as its own concern.
- Independent of FastF1 download success — if a session weather file is corrupt, we want a clear error here, not a cascading failure mid-download.

**Verification:**
- Spot-check known wet races (Silverstone 2024 R12, Brazil 2024 R20, Belgium 2021) — these should come up as `was_wet=True`.
- Spot-check known dry races (Bahrain 2024 R1, Saudi 2024 R2) — these should come up as `was_wet=False`.

### Phase B — Feature wiring

**Where to add columns:**

`04_build_model_inputs.py` is the script that joins jolpica priors + FP features into the training table. It currently doesn't touch weather. The plan:

1. Load the new session weather Parquets from Phase A.
2. Join onto `model_rows` by `(season, round)`. Resolve session naming carefully — we need:
   - `was_wet_race` (from Race session)
   - `was_wet_quali` (from Q session)
   - `was_wet_sprint` (from SR session, only for sprint weekends)
   - `precip_total_race_mm` (proxy via `precip_minutes` × calibration constant; documented as approximate since FastF1 only gives boolean rainfall)
   - `track_temp_race_avg`, `air_temp_race_avg`, `humidity_race_avg`
3. Add these as columns in the training table.

**Where features land in model feature lists:**

`models/trained/feature_columns.json` defines the four feature lists. The current quali list has 85 features, race has 101, race_fp has 101, sprint has 107. All four already contain `wet_skill` (dormant — present but never actively used because there's no wet/dry context to interact with).

Add to **each** of the four lists:
- `was_wet_race` (binary)
- `was_wet_quali` (binary)
- `was_wet_sprint` (binary)
- `track_temp_avg` (continuous, °C)
- `air_temp_avg` (continuous, °C)
- `humidity_avg` (continuous, %)

For the race / race_fp models, these are the conditions for the race specifically. For the quali model, use the quali session's weather. For sprint, use sprint race's weather. XGBoost handles missing values natively, so for the race_fp model that may run pre-quali, `was_wet_quali` can be NaN.

**Why include temperature even though rain is the main signal:**
- Hot tracks chew tyres differently from cold ones — strategy matters more. Wet → cold is correlated but not identical (Singapore wet ≠ Spa wet).
- Cheap to include if we're already extracting it from the same DataFrame.
- Risk: if temp adds noise rather than signal, XGBoost will down-weight it via tree splits. Low cost to test.

**Verification before retraining:**
- Print histogram of `was_wet_race` across training rows. Expect roughly 10-15% wet given F1's calendar bias toward arid venues.
- Spot-check 20 specific rows — pick known wet races and confirm `was_wet_race=True`, plus a few known dry races confirming False.
- Print correlation of `was_wet_race` with `is_dnf` — wet races should have noticeably higher DNF rate. Sanity check on the labelling.

### Phase C — Retraining + validation

**Walk-forward backtest (mandatory):**

Current `05_train_models.py` trains on all historical rows with 2026 weighted 2.5×. Before shipping the new model:

1. Train **two models**: one with weather features (call it `race_model_v2_weather`), one without (`race_model_v2_dry` = current baseline retrained on the same data). Same hyperparams, same training split.
2. Walk-forward backtest both models on each completed 2026 round + the last ~10 rounds of 2025. For each held-out round:
   - Train on everything before that round
   - Predict the round
   - Compute MAE on actual finishing positions
3. Compare per-round MAE between the two models. Stratify by:
   - **Wet rounds** (was_wet_race=True): weather model should be meaningfully better. Target: MAE improvement ≥0.3 positions.
   - **Dry rounds** (was_wet_race=False): weather model should be no worse than baseline. Threshold: MAE regression ≤0.1 positions per round on average.
4. **Decision gate:** if dry MAE regresses by more than 0.1 positions, do NOT ship. Either (a) reduce the number of weather features (drop temp / humidity, keep only `was_wet_*`), or (b) try training-time reweighting (see Phase C risks below).

**Why walk-forward matters here:**

The training set is 90% dry races. A vanilla retrain might just learn "ignore the new features because dry is always the answer" and we'd ship a noop. Walk-forward stratified by wet/dry is the only way to tell if the model actually learned the conditional.

**Training-set imbalance mitigation (only if walk-forward dictates):**

Three options, from cheapest to most invasive:
1. **No mitigation** — let XGBoost handle it. Try this first. If walk-forward passes the gate, ship it.
2. **Sample weighting** — multiply `sample_weight` for wet rows by ~2-3× during training. Low risk, easy revert.
3. **Oversampling** — duplicate wet rows ~2× before training. More disruptive, only if option 2 fails.

Do NOT use SMOTE or synthetic generation — F1 sample sizes are too small and the structure is too domain-specific.

### Phase D — Inference plumbing

**Read forecast in `06_run_predictions.py`:**

`weather.json` schema (verified):
```
{
  "round": 7,
  "overall_rain_risk": "NONE|LOW|MEDIUM|HIGH",
  "max_rain_probability": 13,         // %, max across sessions
  "sessions": [
    {
      "name": "FP1|FP2|FP3|Qualifying|Sprint Qualifying|Sprint|Race",
      "rain_probability": 0,           // %, 0-100
      "avg_temp": 18.0,                // °C
      "total_precip_mm": 0.0,
      "rain_risk": "NONE|LOW|MEDIUM|HIGH",
      ...
    }
  ]
}
```

**Mapping forecast → feature values:**

Continuous features come straight from the forecast:
- `track_temp_avg` ≈ `session.avg_temp + 8-12°C` (track is hotter than air; use a constant offset learned from historical data — TBD which constant during implementation, probably +10°C as a starting heuristic).
- `air_temp_avg` = `session.avg_temp`
- `humidity_avg` = derive from hourly data (avg of `humidity` field across session hours).

Binary "was_wet_*" needs a thresholding rule. Plan:
- If `session.rain_probability >= 60` OR `session.total_precip_mm >= 1.0`, set `was_wet_X = True`.
- Otherwise `False`.
- This threshold is conservative — favouring False — because false positives (predicting wet when it stays dry) materially distort dry-race predictions. Better to under-react.

The threshold is tunable; will live in a `WEATHER_INFERENCE_TUNABLES` block at the top of `06_run_predictions.py` for easy iteration.

**Fallback behaviour when `weather.json` missing:**
- All weather features → NaN. XGBoost handles natively; effectively a "weather unknown" code path that falls back to whatever the model learned from the rest of the features.
- Print a loud warning to logs: `[WARN] weather.json not found — running prediction without weather conditioning. Predictions may be inaccurate if conditions differ from dry baseline.`
- Do NOT silently assume dry. If the forecast pipeline broke, we want the prediction to reflect that uncertainty.

**Metadata on the prediction row:**

`prediction_metadata.json` (sidecar from current pipeline) gains a `weather_features_used` block:
```
{
  "weather_features_used": {
    "was_wet_race": false,
    "was_wet_quali": false,
    "track_temp_avg": 28.0,
    "air_temp_avg": 18.0,
    "source": "weather.json:2026-05-25T02:36:37Z"
  }
}
```
Lets users on the Changelog / Accuracy tabs see exactly which weather values went into each prediction. Critical for diagnosing "why does the model think this round will be wet" complaints.

### Phase E — Recalibration

After the new model is shipped:

1. Run `pipeline/calibrate_confidence.py` against the post-Level-3 predictions for completed rounds. The MC noise multiplier in `data/seed/mc_calibration.json` will likely change because the deterministic predictions are now slightly different.
2. Add a Changelog tab entry. Tag it `model`. Explain in plain English that weather conditioning is now active and what it changes.

---

## 5. Why each design choice (the "why")

### Why backfill from FastF1 cache rather than re-download
The cache `.ff1pkl` files are already on disk and contain the full `weather_data` DataFrame. Re-downloading would re-fetch from the FastF1 API (slow, rate-limited, occasional outages). The data is already there — we just never extracted Rainfall when we wrote the lap parquets.

### Why a separate `03c_extract_session_weather.py`
Three reasons:
- **Separation of concerns**: download is one job, aggregation is another, feature joining is a third.
- **Independent failure mode**: if FastF1's pickle for one round is corrupt, we want a clear "session weather extract failed for X" rather than the whole download script blowing up.
- **Future flexibility**: the script becomes the place to add humidity / wind / pressure aggregations later, when we want them.

### Why train both a `_dry` and a `_weather` model for validation
Otherwise we can't tell if any MAE change comes from the new features or from incidental retraining noise (different random seed, different training data freshness, etc.). Holding everything constant except the feature list isolates the effect.

### Why a conservative wet-probability threshold (60%) at inference
False positives hurt more than false negatives here. If we predict wet at 50% probability and it ends up dry, the model produces a prediction shifted toward wet-skilled drivers, the user picks them, and gets burned. If we predict dry at 50% probability and it ends up wet, the model is just "as wrong as before" — no worse than the current state of the world. Asymmetric cost → asymmetric threshold.

### Why expose `weather_features_used` in metadata
Two reasons:
- **Debuggability**: when someone says "this prediction looks wrong", we can immediately check what weather values went in.
- **Accuracy tab fidelity**: phase archives can show how forecast accuracy changed across the weekend (pre-FP forecast vs post-quali forecast). Without metadata we'd lose that signal.

### Why retraining is the right unit of work (not transfer learning, not online learning)
F1 training data is small (~2,600 rows). Anything fancier than gradient-boost-from-scratch is unjustified at this scale. Retraining is fast (~30 seconds), reproducible, and reverts cleanly if something breaks.

---

## 6. Possible shortcomings & quirks

These are the honest pitfalls. Each one needs to be either accepted or mitigated. Some are mitigated by design; some are residual risks we accept.

### 6a. Training-set imbalance (residual risk, partly mitigated)

About 10-15% of historical races were meaningfully wet. XGBoost may underweight the new features simply because the dry signal dominates.

**Mitigation:** walk-forward validation gates the release. If dry MAE regresses, we try sample weighting. If that fails, we strip features down to `was_wet_*` only.

**Residual risk:** the model may still under-react to wet conditions even after passing the gate. The gate guarantees we're not worse, not that we're optimally responsive. Acceptable starting point — we can iterate based on observed wet-race accuracy in 2026.

### 6b. Forecast accuracy is a ceiling on prediction accuracy

The forecast at quali lock is 24-36h out. Open-Meteo is generally good (±10-15% precip probability vs actual outcome) but not perfect. Even with a perfect model, a wrong forecast produces a wrong prediction.

**Mitigation:** none directly — we can't outpredict the weather service. But:
- Phase archives capture which forecast value was used → after the race, the Accuracy tab can show "predicted wet, was dry; predicted dry, was wet" misses separately from regular MAE.
- The Changelog tab entry will explicitly call out the forecast dependency so users know what the model is conditioning on.

### 6c. Mixed-condition races

A race that starts dry and gets a 15-minute shower in the middle (or vice versa) is neither cleanly "wet" nor "dry". Our binary `was_wet_race` label is a simplification.

**Mitigation:** include `precip_minutes` as a continuous feature alongside the binary. The model can learn the conditional. Realistically, this is a category we'll often mis-classify; the calibration impact is small because pure-wet and pure-dry are more common.

**Residual risk:** mixed-condition races (Imola 2022, Singapore 2024 ish) will be poorly served until we have enough of them to learn a sub-pattern. We accept this — they're rare.

### 6d. The `wet_skill` feature is hand-curated and stale

`config/team_driver_ratings.py::DRIVER_WET_WEATHER_SKILL` is a manual dictionary. It hasn't been updated since early 2026. If Hadjar turns out to be a wet maestro, we won't know until someone manually updates the file.

**Mitigation:** out of scope for Level 3, but worth flagging. Future enhancement: derive `wet_skill` from historical wet-race finishing positions vs teammate (rolling, 3-race window over wet races only). Level 3.5 territory.

**Residual risk:** Cadillac drivers, rookies, and any 2026 newcomer get a default `wet_skill=6` (neutral). On wet races their predictions will be unchanged from the dry baseline.

### 6e. `track_temperature` already exists but as a session-mean repeated per lap

Current lap parquets have `track_temperature` set to `weather.TrackTemp.mean()` for the whole session — so per-lap track temp variance is lost. For Level 3 this is fine: we want session aggregates anyway. But it means we can't ever build a "track temp at lap 30" feature without re-extracting from the cache pickles.

**Mitigation:** Phase A's `session_weather` extraction takes min/max/avg from the raw weather DataFrame, sidestepping the lap-parquet's compression. Future per-stint pace features could use the cache pickles directly.

### 6f. Sprint weekends complicate the label

A sprint weekend has FP1, Sprint Qualifying, Sprint Race, Qualifying, Race — five labelled sessions. Each can have different weather. Plus the sprint-vs-race weather can differ (e.g. dry sprint, wet race). The model needs `was_wet_sprint` and `was_wet_race` as separate features.

**Mitigation:** schema in Phase A explicitly separates by session name. The model gets all relevant labels.

**Residual risk:** sprint rounds are only ~6 per year. Sample size for "wet sprint" specifically is tiny (probably <10 across all of 2020-2025). The sprint model may not learn a wet-sprint signal at all. Accept this — sprint predictions will fall back to non-conditional behaviour for wet conditions, which is no worse than today.

### 6g. The "wet" label depends on FastF1's `Rainfall` boolean — which is the meteorological station's report, not "is the track actually wet"

FastF1's Rainfall column is what the weather feed reports — which can be drizzle, mist, or steady rain. The track might be wet without active rain (drying line) or dry despite light rain (light enough that rubber stays). Our binary label conflates all these states.

**Mitigation:** none for Level 3. The model learns from imperfect labels; that's life. The 10% session-time threshold ("Rainfall=True for ≥10% of session") at least filters out brief drizzle that doesn't affect the racing surface.

**Residual risk:** edge cases will be mis-labelled. Acceptable.

### 6h. Walk-forward backtest is on a small set of wet races

We probably have ~30-40 historical wet races to validate against. That's small. A 0.3-position MAE improvement on wet races might be noisy.

**Mitigation:** report confidence intervals on the MAE delta, not just point estimates. If the 95% CI of the wet-race MAE improvement crosses zero, we're not confident the improvement is real → don't ship.

### 6i. Inference falls back to NaN when `weather.json` is missing — but the model was trained on rows where the features are *populated* (the historical weather is known)

So the inference fallback (NaN for all weather features) takes the model into a region of feature space it hasn't seen. XGBoost handles NaN natively, but the behaviour in that region is uncalibrated.

**Mitigation:** train the model on a small fraction (~5%) of rows with weather features artificially set to NaN. Forces the model to learn "if weather unknown, ignore the weather branch" gracefully. Low cost; adds robustness.

**Residual risk:** if the forecast feed is down for an extended period, predictions will degrade. We'd notice and fix the fetch.

### 6j. Once weather is in the model, the Multi-Week Planner's future-round projections (priors-only via `predict_horizon.py`) become awkward

The planner projects 2-5 weeks out. We don't have weather forecasts that far ahead. So `predict_horizon.py` will need to default `was_wet_*` to False for future rounds, which is fine but loses the weather signal entirely.

**Mitigation:** explicitly set weather features to "assume dry" inside `predict_horizon.py` and document this. The planner's future projections were already an approximation (priors only, no FP), so this is consistent with existing limitations.

**Residual risk:** none new — existing planner limitations.

### 6k. The race-completed guards in 06/07/08 prevent re-prediction of completed rounds

Which is normally what we want (prevents accuracy archive pollution). But the very first run after retraining will want to **regenerate** historical predictions to populate the accuracy tab with the new model's view of past rounds.

**Mitigation:** use `pipeline/recover_archives.py` (which exists for this exact purpose — walk-forward retrain + rebuild archives with `reconstructed: true` flag). New model goes live; recovery script rebuilds 2026 historical archives marked as reconstructions. Accuracy tab can then compare old vs new model.

**Residual risk:** the rebuilt archives are not the predictions users actually saw at the time. We must clearly mark them as `reconstructed: true` (which the recovery script already does) so the Accuracy tab can split "as-predicted-at-the-time" from "as-the-new-model-would-have-predicted".

---

## 7. Estimated effort & sequencing

| Phase | Work | Est. time | Blocked by |
|---|---|---|---|
| A | Historical weather backfill script + verification | 1 day | — |
| B | Wire into `04_build_model_inputs` + feature lists | 0.5 day | A |
| C | Retrain + walk-forward validation + decision gate | 0.5-1 day | B |
| D | Inference plumbing + fallback + metadata | 0.5 day | C |
| E | Recalibration + Changelog entry | 0.5 day | D |
| **Total** | | **3-3.5 days** | |

Realistically across two weekends of focused work, with a gap in between to think about Phase C results before committing.

---

## 8. Acceptance criteria (re-stated from goal, made concrete)

Before shipping to production:
1. **Walk-forward wet-race MAE improves by ≥0.3 positions** vs the current baseline, with 95% CI excluding zero.
2. **Walk-forward dry-race MAE does not regress by more than 0.1 positions** on average across the held-out rounds.
3. **Inference pipeline works end-to-end** with a known-wet historical round: re-predict R20 2024 (Brazil, soaking wet) with weather injection enabled and confirm the model's top-5 shifts toward wet-strong drivers.
4. **Inference fallback works**: rename `weather.json` temporarily, re-run prediction, confirm the warning prints and predictions still generate without crashing.
5. **MC calibration is re-run**: `data/seed/mc_calibration.json` reflects the new model's error distribution.
6. **Changelog tab has an entry** describing the change in plain English.

---

## 9. Where this builds from

Existing assets that this plan uses (in order of how they're consumed):

1. `data/raw/fastf1/cache/**/weather_data.ff1pkl` — historical per-session weather data, already on disk.
2. `data/processed/jolpica/model_rows/*.parquet` — the per-row training table that we'll add weather columns to.
3. `pipeline/04_build_model_inputs.py` — where we wire weather joins in.
4. `models/trained/feature_columns.json` — where we register the new feature names.
5. `pipeline/05_train_models.py` — retrains with the new features.
6. `pipeline/06_run_predictions.py` — inference plumbing.
7. `web/public/data/weather.json` — already produced by `pipeline/weather_forecast.py`; this plan only consumes it.
8. `pipeline/calibrate_confidence.py` — re-run after retrain.
9. `pipeline/recover_archives.py` — for rebuilding historical predictions with the new model.
10. `web/public/data/changelog.json` — new entry post-ship.

Nothing is being deleted or moved. New assets:
- `pipeline/03c_extract_session_weather.py` (new script)
- `data/processed/weather/session_weather_year{Y}.parquet` (new output)
- `models/trained/{quali,race,race_fp,sprint}_model.json` (retrained, replacing existing)
- Weather columns in `data/processed/jolpica/model_rows/*.parquet` (additive change)

---

## 10. Approval needed before any code is written

Per user instruction (2026-05-25): no implementation work begins on this feature until the user has reviewed this plan and explicitly approved it.

When approval comes, the suggested first deliverable is Phase A alone — produce the session weather Parquets and verify against known wet/dry races. That's a self-contained piece that informs the rest of the plan without committing to the retrain.
