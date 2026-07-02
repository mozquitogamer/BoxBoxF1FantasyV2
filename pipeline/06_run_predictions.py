"""
Script 06 — Run Predictions (Combined Jolpica Priors + FP Telemetry)

At prediction time, both data layers are available:
  Layer 1: Jolpica priors — built from all historical model_rows
  Layer 2: FP telemetry — extracted from current weekend's practice sessions

Pipeline:
  1. Load historical model_rows (all completed rounds)
  2. Build stub rows for current weekend drivers
  3. Run rolling feature computation to get priors for current round
  4. Merge FP telemetry features
  5. Apply feature engineering
  6. Predict qualifying -> use predicted quali to build race features -> predict race
  7. Calculate confidence scores
  8. Output predictions

Usage:
    python pipeline/06_run_predictions.py --round 3
    python pipeline/06_run_predictions.py --round 3 --year 2026

Output:
    data/predictions/roundX/predictions.parquet
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    FEATURES_DIR,
    PREDICTIONS_DIR,
    TRAINED_DIR,
    RACE_MODEL_ALGORITHM,
    SEED_DIR,
    JOLPICA_MODEL_ROWS_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
    WEB_DATA_DIR,
    fastf1_round,
    is_race_completed,
)
from pipeline.feature_engineering import engineer_features
from config.track_classifications import (
    get_circuit_id_from_race_name,
    grid_anchor_weight,
    fp_quali_blend_weight,
)
from config.track_similarity import get_similarity


# ============================================================
# Weather inference (Level 3 Phase D)
# ============================================================
# Reads web/public/data/weather.json (produced by pipeline/weather_forecast.py)
# and injects per-session weather features into the prediction row so the
# model can condition on the forecast at inference time.
#
# The features mirror what pipeline/04_build_model_inputs.py joins onto
# training rows from data/processed/weather/all_session_weather.parquet:
#   weather_was_wet_{quali,race,sprint}     0.0 / 1.0
#   weather_track_temp_{quali,race,sprint}  deg C
#   weather_air_temp_{quali,race,sprint}    deg C
#   weather_humidity_{quali,race,sprint}    %
#   weather_precip_minutes_race             approximate from forecast precip
#
# Tunables here are conservative: we under-predict wet risk because the
# product cost of "predicted wet, was dry" (user picks rain-strong drivers,
# gets average finish) > "predicted dry, was wet" (no worse than current
# state of the world). See docs/WEATHER_LEVEL3_IMPLEMENTATION_PLAN.md §5.

# ============================================================
# FP-pace qualifying blend (Level: post-FP accuracy, added 2026-06-05)
# ============================================================
# The F1 Fantasy team-lock deadline is BEFORE qualifying, so the post-FP
# prediction is the ONLY actionable one — we never have qualifying data at
# decision time. The trained quali model underweights FP telemetry (it's present
# in only ~6% of training rows, so XGBoost leans on always-present priors).
#
# Backtest on 2026 completed rounds (R1/R3/R6/R7 — all normal-overtaking tracks)
# showed raw FP single-lap pace predicts ACTUAL quali BETTER than the full model:
#   FP single-lap rank -> actual quali  MAE 2.44  (Spearman ~0.9)
#   model predicted quali -> actual     MAE 2.88
# Blending the model's quali toward the FP pace ranking (weight swept in the same
# z-score space used below) minimises MAE at ~0.6 (2.73 -> 2.32); 0.5-0.8 all
# clearly beat 0.0. Because it was validated ON normal tracks and improves them,
# this applies to EVERY round, not just hard-overtake circuits. The FP pace signal
# is a composite (best lap + best-3 + best-5 lap averages) — see
# FP_QUALI_BLEND_TUNABLES below — which backtests better than any single metric.
#
# Race finish is deliberately NOT blended toward FP: FP long-run pace is a poor
# finish predictor (MAE 6.4 vs model 4.3 — finishes are dominated by DNFs /
# strategy / start chaos). The improved quali still flows to the race because
# (a) quali_position/grid_advantage are race-model features and (b) on hard-to-
# overtake tracks grid-anchoring carries the grid into the finish.
# The base weight (0.6) is the backtest optimum on normal-overtake tracks. On
# quali-dominant circuits (Monaco, Singapore, Hungary) one-lap pace decides the
# weekend far more than season race form, so the weight is scaled UP toward
# `weight_hard_track` via overtaking_difficulty (same track property as grid-
# anchoring). At difficulty 10 (Monaco) the quali prediction is ~80% practice
# pace; normal tracks keep 0.6; mild tracks (e.g. Barcelona, diff 7) get a small
# bump. Note this is a domain-knowledge choice for hard tracks (no completed
# Monaco-tier round in the 2026 backtest yet) — recalibrate once one exists.
# Quali-pace signal is a COMPOSITE of the single best lap plus best-3 and best-5
# lap averages (mean of per-metric z-scores). A single best lap can be a one-off
# banker (tow, perfect lap, low fuel); the multi-lap averages reward repeatable
# pace. Backtest on 2026 R1/3/6/7: composite MAE 2.24 vs 2.36 for best-lap alone
# — better than any single metric. (best_10_lap_avg excluded: 2.67, too diluted
# by traffic/fuel laps.)
FP_QUALI_BLEND_TUNABLES = {
    "weight": 0.6,                 # base (normal tracks): 0 = pure model, 1 = pure FP pace
    "weight_hard_track": 0.80,     # FP weight at overtaking_difficulty 10 (Monaco)
    "hard_track_pivot": 6,         # at/below this difficulty, use base weight
    "min_drivers_with_pace": 10,   # need at least this many FP times to blend
    "pace_cols": ["best_lap_time", "best_3_lap_avg", "best_5_lap_avg"],  # composite; lower = faster
}


WEATHER_INFERENCE_TUNABLES = {
    # When session rain_probability >= this OR total_precip_mm >= 1.0,
    # set was_wet_X = 1.0. 60 is conservative — favours False.
    "wet_probability_threshold_pct": 60,
    "wet_precip_threshold_mm": 1.0,
    # Track temperature is hotter than air. Constant offset works as a
    # starting heuristic; can be refined later from historical (track-air)
    # deltas per circuit.
    "track_vs_air_offset_C": 10.0,
    # Approximate `precip_minutes` for a session from total_precip_mm.
    # Drizzle (1mm) ~= 5min of FastF1 Rainfall=True at training; steady rain
    # (10mm) ~= ~50min. Linear scale; ~5 min per mm.
    "precip_min_per_mm": 5.0,
}


def _classify_session_to_label(session_name: str) -> str | None:
    """Map weather.json session name to our internal session label.

    Returns one of 'quali', 'race', 'sprint', or None (skip).
    """
    n = (session_name or "").lower()
    if "race" in n and "sprint" not in n:
        return "race"
    if "sprint" in n and "qualif" not in n and "shoot" not in n:
        # "Sprint" or "Sprint Race"
        return "sprint"
    if "qualif" in n and "sprint" not in n:
        return "quali"
    return None


def _aggregate_forecast_session(sess: dict) -> dict:
    """Convert one weather.json session block into our feature dict."""
    tunables = WEATHER_INFERENCE_TUNABLES
    rain_p = sess.get("rain_probability")
    precip_mm = sess.get("total_precip_mm") or 0.0
    air_temp = sess.get("avg_temp")

    # Was wet? Conservative thresholding.
    was_wet = False
    if rain_p is not None and rain_p >= tunables["wet_probability_threshold_pct"]:
        was_wet = True
    if precip_mm >= tunables["wet_precip_threshold_mm"]:
        was_wet = True

    # Humidity from hourly average, if available.
    hourly = sess.get("hourly") or []
    humidities = [h.get("humidity") for h in hourly if h.get("humidity") is not None]
    humidity_avg = (sum(humidities) / len(humidities)) if humidities else None

    return {
        "was_wet": 1.0 if was_wet else 0.0,
        "air_temp": float(air_temp) if air_temp is not None else None,
        "track_temp": (
            float(air_temp) + tunables["track_vs_air_offset_C"]
            if air_temp is not None else None
        ),
        "humidity": float(humidity_avg) if humidity_avg is not None else None,
        "precip_minutes": float(precip_mm) * tunables["precip_min_per_mm"],
        "rain_probability_pct": float(rain_p) if rain_p is not None else None,
        "total_precip_mm": float(precip_mm),
    }


def inject_weather_features(pred_df: pd.DataFrame, round_num: int) -> tuple[pd.DataFrame, dict]:
    """Read weather.json and add weather_*_{quali,race,sprint} columns to pred_df.

    Returns (enriched pred_df, metadata dict for the prediction_metadata sidecar).
    All drivers in the round share the same weather (session-level fact), so we
    populate every row identically.

    On missing/stale weather.json: leaves weather columns as NaN (XGBoost handles
    natively) and prints a loud warning. We never silently fabricate "dry" —
    that would hide a broken forecast pipeline.
    """
    weather_path = WEB_DATA_DIR / "weather.json"
    weather_meta: dict = {"source": None, "missing": True, "per_session": {}}

    if not weather_path.exists():
        print(f"  [WARN] {weather_path} not found — running prediction WITHOUT weather conditioning.")
        print(f"         If conditions differ from dry baseline, predictions may be inaccurate.")
        # Ensure NaN columns exist so feature_columns alignment doesn't break
        for sess in ("quali", "race", "sprint"):
            for metric in ("was_wet", "track_temp", "air_temp", "humidity", "precip_minutes"):
                col = f"weather_{metric}_{sess}"
                if col not in pred_df.columns:
                    pred_df[col] = np.nan
        return pred_df, weather_meta

    try:
        with open(weather_path) as f:
            wjson = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] weather.json unreadable ({e}) — running WITHOUT weather conditioning.")
        for sess in ("quali", "race", "sprint"):
            for metric in ("was_wet", "track_temp", "air_temp", "humidity", "precip_minutes"):
                col = f"weather_{metric}_{sess}"
                if col not in pred_df.columns:
                    pred_df[col] = np.nan
        return pred_df, weather_meta

    # Sanity-check: weather.json should be for the same round we're predicting
    weather_round = wjson.get("round")
    if weather_round is not None and weather_round != round_num:
        print(f"  [WARN] weather.json is for round {weather_round}, but predicting round {round_num}.")
        print(f"         Using forecast anyway, but verify pipeline/weather_forecast.py ran for this round.")

    weather_meta["source"] = wjson.get("last_updated") or "unknown"
    weather_meta["missing"] = False
    weather_meta["overall_rain_risk"] = wjson.get("overall_rain_risk")
    weather_meta["weather_round"] = weather_round

    # Collect per-session aggregates. If multiple sessions share a label
    # (e.g. FP1+FP2+FP3 all map to None and quali maps to quali), we keep the
    # last one seen — for quali/race/sprint there's only one each per weekend.
    per_session: dict[str, dict] = {}
    for sess in wjson.get("sessions", []) or []:
        label = _classify_session_to_label(sess.get("name", ""))
        if not label:
            continue
        per_session[label] = _aggregate_forecast_session(sess)

    # Populate pred_df columns. NaN where forecast is missing.
    for label in ("quali", "race", "sprint"):
        agg = per_session.get(label, {})
        pred_df[f"weather_was_wet_{label}"] = float(agg.get("was_wet")) if agg.get("was_wet") is not None else np.nan
        pred_df[f"weather_track_temp_{label}"] = agg.get("track_temp") if "track_temp" in agg else np.nan
        pred_df[f"weather_air_temp_{label}"] = agg.get("air_temp") if "air_temp" in agg else np.nan
        pred_df[f"weather_humidity_{label}"] = agg.get("humidity") if "humidity" in agg else np.nan
        if label == "race":
            # Only race model expects precip_minutes
            pred_df[f"weather_precip_minutes_{label}"] = agg.get("precip_minutes") if "precip_minutes" in agg else np.nan
        weather_meta["per_session"][label] = agg

    # Log what we injected
    rsess = weather_meta["per_session"].get("race", {})
    qsess = weather_meta["per_session"].get("quali", {})
    print(f"  Weather forecast injected (source: {weather_meta['source']}):")
    if rsess:
        was_wet_str = "WET" if rsess.get("was_wet") == 1.0 else "dry"
        print(f"    Race: {was_wet_str} "
              f"(rain {int(rsess.get('rain_probability_pct') or 0)}%, "
              f"{rsess.get('total_precip_mm') or 0:.1f}mm, "
              f"air {rsess.get('air_temp') or 0:.1f}C)")
    if qsess:
        was_wet_str = "WET" if qsess.get("was_wet") == 1.0 else "dry"
        print(f"    Quali: {was_wet_str} (air {qsess.get('air_temp') or 0:.1f}C)")

    return pred_df, weather_meta


# -- Driver ID mapping ---------------------------------------------------------

def load_driver_id_maps() -> tuple[dict, dict]:
    """Load bidirectional mappings between abbreviation and Jolpica IDs."""
    driver_ids_path = SEED_DIR / "driver_ids.json"
    with open(driver_ids_path) as f:
        data = json.load(f)

    abbrev_to_jolpica = {}
    jolpica_to_abbrev = {}
    for m in data["mappings"]:
        abbrev_to_jolpica[m["abbrev"]] = m["jolpica"]
        jolpica_to_abbrev[m["jolpica"]] = m["abbrev"]
    return abbrev_to_jolpica, jolpica_to_abbrev


# -- Build live priors ---------------------------------------------------------

def build_live_priors(
    round_num: int,
    year: int,
) -> pd.DataFrame:
    """
    Build Jolpica prior features for the current round by running the
    feature builder on all historical data plus stub rows for this weekend.

    Returns a DataFrame with one row per driver, with all Jolpica prior
    features populated.
    """
    # Load all historical model rows
    model_rows_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    if not model_rows_path.exists():
        raise FileNotFoundError(
            f"Model rows not found: {model_rows_path}\n"
            "Run 03b_build_jolpica_features.py first."
        )

    all_rows = pd.read_parquet(model_rows_path)
    print(f"  Loaded {len(all_rows):,} historical model rows")

    # Filter to completed rounds only (exclude current round if present)
    completed = all_rows[
        ~((all_rows["season"] == year) & (all_rows["round"] == round_num))
    ].copy()

    # Get current round rows if they exist in the data (e.g., already normalized)
    current_round = all_rows[
        (all_rows["season"] == year) & (all_rows["round"] == round_num)
    ]

    if not current_round.empty:
        # Rows exist — use them (features already computed by 03b)
        print(f"  Found {len(current_round)} pre-computed rows for round {round_num}")
        return current_round

    # If no rows exist for this round, we need the last known priors per driver.
    # Take the most recent row per driver as their "prior state".
    print(f"  No pre-computed rows for {year} R{round_num} — using latest priors per driver")

    # Get the most recent row for each active driver
    completed_sorted = completed.sort_values(["season", "round"])
    latest_per_driver = completed_sorted.groupby("driver_id").last().reset_index()

    # Filter to current season drivers only
    with open(SEED_DIR / "drivers.json") as f:
        current_drivers = json.load(f)["drivers"]
    abbrev_to_jolpica, _ = load_driver_id_maps()
    current_jolpica_ids = {
        abbrev_to_jolpica.get(d["driver_id"], d["driver_id"])
        for d in current_drivers
    }
    latest_per_driver = latest_per_driver[
        latest_per_driver["driver_id"].isin(current_jolpica_ids)
    ].copy()

    # These rows carry the rolling features from the driver's last race
    # which is exactly what we want as priors
    latest_per_driver["season"] = year
    latest_per_driver["round"] = round_num

    return latest_per_driver


# -- Confidence scoring --------------------------------------------------------

def calculate_confidence(
    df: pd.DataFrame,
    quali_pred: np.ndarray,
    race_pred: np.ndarray,
    fp_signal_pred: np.ndarray | None,
) -> np.ndarray:
    """Calculate 0-100 confidence score per driver."""
    n = len(df)
    scores = np.full(n, 50.0)

    # Data completeness: FP laps (up to +20)
    if "total_laps" in df.columns:
        lap_counts = df["total_laps"].fillna(0)
        scores += np.clip(lap_counts.values / 30.0, 0, 1) * 20

    # FP sessions (up to +10)
    if "fp_sessions_used" in df.columns:
        sessions = df["fp_sessions_used"].fillna(0)
        scores += np.clip(sessions.values / 3.0, 0, 1) * 10

    # Prior data richness: non-NaN Jolpica priors (up to +10)
    prior_cols = [c for c in df.columns if c.startswith("roll_") or c.startswith("driver_roll")]
    if prior_cols:
        non_nan_ratio = df[prior_cols].notna().mean(axis=1)
        scores += non_nan_ratio.values * 10

    # Model agreement: rank correlation between race and FP signal (up to +10)
    if fp_signal_pred is not None:
        race_rank = pd.Series(race_pred).rank()
        fp_rank = pd.Series(fp_signal_pred).rank()
        rank_diff = np.abs(race_rank.values - fp_rank.values)
        scores += np.clip(1 - (rank_diff / max(n, 1)), 0, 1) * 10

    return np.clip(scores, 0, 100).astype(int)


# -- Track similarity recomputation for prediction round ----------------------

def _resolve_circuit(round_num: int, year: int) -> str:
    """Resolve the circuit_id for a given round from the race schedule."""
    races_path = SEED_DIR / "races.json"
    if not races_path.exists():
        return "unknown"
    with open(races_path) as f:
        races = json.load(f)
    for r in races.get("races", []):
        if r.get("round") == round_num:
            return get_circuit_id_from_race_name(r.get("name", ""))
    return "unknown"


def _load_actual_quali(
    year: int, round_num: int, abbrev_to_jolpica: dict[str, str]
) -> dict[str, int]:
    """
    Load actual qualifying positions for a completed round.

    Returns a dict {jolpica_driver_id: quali_position} if available, empty dict
    otherwise. Used to detect post-FP vs post-quali phase and, when available,
    to feed actual quali positions into the race model.
    """
    # Method 1: normalized jolpica CSV
    norm_path = JOLPICA_MODEL_ROWS_DIR.parent / "normalized" / str(year) / "qualifying_results.csv"
    if norm_path.exists():
        try:
            df = pd.read_csv(norm_path)
            df = df[df["round"] == round_num]
            if not df.empty and "quali_position" in df.columns:
                out = {}
                for _, row in df.iterrows():
                    did = row.get("driver_id")
                    qp = row.get("quali_position")
                    if pd.notna(did) and pd.notna(qp):
                        out[str(did)] = int(qp)
                if out:
                    return out
        except Exception:
            pass

    # Method 2: FastF1 qualifying session (fallback)
    try:
        import fastf1
        ff1_round = fastf1_round(round_num, year)
        session = fastf1.get_session(year, ff1_round, "Qualifying")
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results
        if results is not None and not results.empty:
            if "Abbreviation" in results.columns and "Position" in results.columns:
                out = {}
                for _, row in results.iterrows():
                    abbrev = row["Abbreviation"]
                    pos = row["Position"]
                    did = abbrev_to_jolpica.get(abbrev)
                    if did is not None and pd.notna(pos):
                        out[str(did)] = int(pos)
                if out:
                    return out
    except Exception:
        pass

    return {}


def _recompute_circuit_features(df: pd.DataFrame, target_circuit: str) -> pd.DataFrame:
    """
    Recompute circuit-specific historical features against the target circuit.

    The priors carry driver_circuit_exp / driver_circuit_roll_3 / constructor_circuit_exp
    values computed against each driver's LAST race circuit (because the stub row
    inherits everything from the most recent completed race). For a prediction at
    a different circuit, these are wrong — they encode "VER's avg quali at Miami",
    not "VER's avg quali at Montreal".

    For Canada (R7) specifically, VER has won 3 of the last 4 GPs there. That
    history exists in all_model_rows but isn't flowing to the model unless we
    explicitly recompute these features for the target circuit.

    Definitions match 03b_build_jolpica_features.py::add_jolpica_features:
      - driver_circuit_exp:    expanding mean of driver's prior quali_position at this circuit
      - driver_circuit_roll_3: rolling-3 mean of driver's prior quali_position at this circuit
      - constructor_circuit_exp: expanding mean of constructor's prior quali_position at this circuit

    Drivers/constructors with no history at the target circuit are left unchanged
    (XGBoost handles NaN, but inheriting Miami's value is misleading; we set to NaN).
    """
    model_rows_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    if not model_rows_path.exists():
        return df

    all_rows = pd.read_parquet(model_rows_path)
    if "circuit_id" not in all_rows.columns:
        return df

    # Filter to target circuit only, sorted chronologically
    at_circuit = all_rows[all_rows["circuit_id"] == target_circuit].copy()
    if at_circuit.empty:
        # No history at this circuit (e.g. brand-new track) — set to NaN
        for col in ("driver_circuit_exp", "driver_circuit_roll_3", "constructor_circuit_exp"):
            if col in df.columns:
                df[col] = np.nan
        # Also stamp the circuit_id so downstream code knows
        df["circuit_id"] = target_circuit
        return df

    at_circuit = at_circuit.sort_values(["season", "round"])

    for i, row in df.iterrows():
        driver = row["driver_id"]
        constructor = row.get("constructor_id")

        # Driver history at this circuit
        d_hist = at_circuit[at_circuit["driver_id"] == driver]
        d_qualis = pd.to_numeric(d_hist["quali_position"], errors="coerce").dropna().tolist()
        if d_qualis:
            df.at[i, "driver_circuit_exp"] = float(np.mean(d_qualis))
            df.at[i, "driver_circuit_roll_3"] = float(np.mean(d_qualis[-3:]))
        else:
            df.at[i, "driver_circuit_exp"] = np.nan
            df.at[i, "driver_circuit_roll_3"] = np.nan

        # Constructor history at this circuit
        if constructor is not None and pd.notna(constructor):
            c_hist = at_circuit[at_circuit["constructor_id"] == constructor]
            c_qualis = pd.to_numeric(c_hist["quali_position"], errors="coerce").dropna().tolist()
            if c_qualis:
                df.at[i, "constructor_circuit_exp"] = float(np.mean(c_qualis))
            else:
                df.at[i, "constructor_circuit_exp"] = np.nan

    # Stamp the target circuit so any downstream check is accurate
    df["circuit_id"] = target_circuit
    return df


def _recompute_sim_features(df: pd.DataFrame, target_circuit: str) -> pd.DataFrame:
    """
    Recompute similarity-weighted rolling features against the target circuit.

    The priors carry sim_weighted_* values computed against each driver's LAST
    race circuit. For predictions, we want them weighted against the UPCOMING
    circuit instead. We recompute by looking at each driver's recent race
    history in all_model_rows and weighting by similarity to target_circuit.
    """
    model_rows_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    if not model_rows_path.exists():
        return df

    all_rows = pd.read_parquet(model_rows_path)
    all_rows = all_rows.sort_values(["driver_id", "season", "round"])

    for i, row in df.iterrows():
        driver = row["driver_id"]
        # Get this driver's full history
        hist = all_rows[all_rows["driver_id"] == driver].copy()
        if hist.empty:
            continue

        for w in (3, 5):
            # Take last `w` races
            recent = hist.tail(w)

            weights, pts_vals, fin_vals, qua_vals = [], [], [], []
            for _, h in recent.iterrows():
                cid = str(h.get("circuit_id", "unknown"))
                sim = get_similarity(target_circuit, cid)
                weight = sim * sim  # squared for sharper contrast
                weights.append(weight)
                pts_vals.append(float(h["points"]) if pd.notna(h.get("points")) else 0.0)
                fin_vals.append(float(h["finish_position"]) if pd.notna(h.get("finish_position")) else np.nan)
                qua_vals.append(float(h["quali_position"]) if pd.notna(h.get("quali_position")) else np.nan)

            if not weights:
                continue

            w_sum = sum(weights)
            if w_sum < 1e-9:
                w_sum = len(weights)
                weights = [1.0] * len(weights)

            # Points (always valid)
            df.at[i, f"sim_weighted_points_{w}"] = (
                sum(wt * v for wt, v in zip(weights, pts_vals)) / w_sum
            )

            # Finish position
            fin_pairs = [(wt, v) for wt, v in zip(weights, fin_vals) if pd.notna(v)]
            if fin_pairs:
                ws, vs = zip(*fin_pairs)
                df.at[i, f"sim_weighted_finishpos_{w}"] = sum(
                    w_ * v_ for w_, v_ in zip(ws, vs)
                ) / sum(ws)

            # Quali position
            qua_pairs = [(wt, v) for wt, v in zip(weights, qua_vals) if pd.notna(v)]
            if qua_pairs:
                ws, vs = zip(*qua_pairs)
                df.at[i, f"sim_weighted_quali_{w}"] = sum(
                    w_ * v_ for w_, v_ in zip(ws, vs)
                ) / sum(ws)

    return df


# -- Main prediction pipeline -------------------------------------------------

def run_predictions(
    round_num: int,
    year: int = CURRENT_SEASON,
    force: bool = False,
    skip_fp: bool = False,
    output_suffix: str = "",
) -> pd.DataFrame:
    """
    Generate predictions for a specific round.

    output_suffix (P9): when non-empty, results go to
        data/predictions/round{N}/predictions_{suffix}.parquet
        data/predictions/round{N}/prediction_metadata_{suffix}.json
    instead of the canonical predictions.parquet. Used by predict_horizon.py
    to compute priors-only future-round projections without clobbering the
    canonical current-round predictions or polluting the accuracy archive.
    """
    """Generate predictions for a specific round."""
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Predictions for {year} Round {round_num}")
    print("=" * 70)

    if year == 2026 and round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled.")
        return pd.DataFrame()

    # Race-completed guard: refuse to re-predict for a past race (would pollute
    # the accuracy archive with hindsight). Pass --force to override (e.g. when
    # rebuilding for the recovery script).
    # P9: when output_suffix is set we're writing to a non-canonical file, so the
    # archive-pollution concern doesn't apply — the guard is skipped for suffixed runs.
    out_filename = f"predictions_{output_suffix}.parquet" if output_suffix else "predictions.parquet"
    output_path = PREDICTIONS_DIR / f"round{round_num}" / out_filename
    if not force and not output_suffix and is_race_completed(round_num, year) and output_path.exists():
        print(f"\n  [SKIP] Race for round {round_num} has already happened and "
              f"predictions.parquet exists.")
        print(f"  Refusing to overwrite — this would pollute the accuracy archive.")
        print(f"  Pass --force to override.")
        return pd.read_parquet(output_path)

    is_sprint = (year == 2026 and round_num in SPRINT_ROUNDS_2026)
    print(f"Sprint weekend: {'Yes' if is_sprint else 'No'}")

    # Load driver ID maps
    abbrev_to_jolpica, jolpica_to_abbrev = load_driver_id_maps()

    # ---- Step 1: Build Jolpica priors ----
    print(f"\n[Step 1] Building Jolpica priors...")
    priors_df = build_live_priors(round_num, year)
    print(f"  Prior rows: {len(priors_df)} drivers")

    # ---- Step 1b: Recompute track-similarity AND circuit-specific features ----
    target_circuit = _resolve_circuit(round_num, year)
    if target_circuit and target_circuit != "unknown":
        print(f"  Recomputing similarity features for target circuit: {target_circuit}")
        priors_df = _recompute_sim_features(priors_df, target_circuit)
        print(f"  Recomputing circuit-specific features for target circuit: {target_circuit}")
        priors_df = _recompute_circuit_features(priors_df, target_circuit)
    else:
        print(f"  Could not resolve target circuit — using prior circuit/similarity features as-is")

    # ---- Step 2: Load FP features ----
    print(f"\n[Step 2] Loading FP telemetry features...")
    fp_path = FEATURES_DIR / f"round{round_num}" / "features.parquet"
    fp_df = None
    if skip_fp:
        print(f"  --no-fp set: ignoring FP features (priors-only prediction)")
    elif fp_path.exists():
        fp_df = pd.read_parquet(fp_path)
        print(f"  Loaded FP features for {len(fp_df)} drivers from {fp_path}")
    else:
        print(f"  No FP features found at {fp_path} — using priors only")

    # ---- Step 3: Merge FP onto priors ----
    print(f"\n[Step 3] Merging FP features onto priors...")
    pred_df = priors_df.copy()

    if fp_df is not None and not fp_df.empty:
        # Convert FP driver_id (abbreviation) to Jolpica ID
        fp_merged = fp_df.copy()
        if fp_merged["driver_id"].iloc[0] in abbrev_to_jolpica:
            fp_merged["driver_id"] = fp_merged["driver_id"].map(abbrev_to_jolpica)
            fp_merged = fp_merged.dropna(subset=["driver_id"])

        # Left-join FP features onto priors
        fp_cols_to_merge = [c for c in fp_merged.columns
                           if c != "driver_id" and c not in pred_df.columns]
        if fp_cols_to_merge:
            merge_cols = ["driver_id"] + fp_cols_to_merge
            pred_df = pred_df.merge(
                fp_merged[merge_cols], on="driver_id", how="left"
            )
            fp_matched = pred_df[fp_cols_to_merge[0]].notna().sum()
            print(f"  Merged {len(fp_cols_to_merge)} FP columns, "
                  f"{fp_matched}/{len(pred_df)} drivers matched")
        else:
            # FP columns may already be in pred_df — update them
            for _, fp_row in fp_merged.iterrows():
                driver_mask = pred_df["driver_id"] == fp_row["driver_id"]
                if driver_mask.any():
                    for col in fp_merged.columns:
                        if col != "driver_id" and col in pred_df.columns:
                            if pd.notna(fp_row[col]):
                                pred_df.loc[driver_mask, col] = fp_row[col]
            print(f"  Updated existing FP columns in priors")

    # ---- Step 3.5: Inject weather forecast (Level 3 Phase D) ----
    print(f"\n[Step 3.5] Injecting weather forecast...")
    pred_df, weather_meta = inject_weather_features(pred_df, round_num)

    # ---- Step 4: Feature engineering ----
    print(f"\n[Step 4] Applying feature engineering...")
    pred_df = engineer_features(pred_df)
    print(f"  Columns after engineering: {pred_df.shape[1]}")

    # ---- Step 5: Load models ----
    print(f"\n[Step 5] Loading trained models...")
    try:
        import xgboost as xgb
    except ImportError:
        print("ERROR: xgboost not installed. Run: pip install xgboost")
        return pd.DataFrame()

    quali_path = TRAINED_DIR / "quali_model.json"
    race_path = TRAINED_DIR / "race_model.json"
    race_fp_path = TRAINED_DIR / "race_model_fp.json"
    fp_model_path = TRAINED_DIR / "fp_signal_model.pkl"
    feature_cols_path = TRAINED_DIR / "feature_columns.json"

    for p in [quali_path, race_path, feature_cols_path]:
        if not p.exists():
            print(f"ERROR: Model not found: {p}")
            print("Run 05_train_models.py first.")
            return pd.DataFrame()

    # ---- Detect phase: post-FP (no actual quali yet) vs post-quali ----
    # Check if actual quali data exists for this (year, round). If so, we're
    # in post-quali phase and can use both the actual quali + race_model.
    # Otherwise we're in post-FP and should use race_model_fp.json if available.
    actual_quali_map = _load_actual_quali(year, round_num, abbrev_to_jolpica)
    is_post_quali = len(actual_quali_map) > 0

    # Select race model: post-FP uses race_model_fp (trained on predicted quali)
    # to match the distribution it sees at inference; post-quali uses race_model
    # (trained on actual quali) since actual quali is known.
    use_fp_race_model = (not is_post_quali) and race_fp_path.exists()

    # Load ranking models. Quali stays XGBoost (rank:pairwise). The RACE models
    # can be CatBoost YetiRank (settings.RACE_MODEL_ALGORITHM) — both emit
    # relevance scores where higher = better (P1), so the downstream grid-anchor
    # blend and ranking are identical. Both .predict() take a named-column
    # DataFrame, so the call site below is unchanged regardless of algorithm.
    quali_model = xgb.XGBRanker()
    quali_model.load_model(str(quali_path))

    chosen_json = race_fp_path if use_fp_race_model else race_path
    chosen_cbm = chosen_json.with_suffix(".cbm")
    use_catboost_race = (RACE_MODEL_ALGORITHM == "catboost") and chosen_cbm.exists()
    if use_catboost_race:
        from catboost import CatBoost
        race_model = CatBoost()
        race_model.load_model(str(chosen_cbm))
        algo_desc = f"CatBoost ({chosen_cbm.name})"
    else:
        race_model = xgb.XGBRanker()
        race_model.load_model(str(chosen_json))
        algo_desc = f"XGBoost ({chosen_json.name})"
    if use_fp_race_model:
        print(f"  Phase: post-FP (no actual quali) -> {algo_desc}")
    else:
        phase_desc = "post-quali (actual quali known)" if is_post_quali else "post-FP (fallback; no race_model_fp)"
        print(f"  Phase: {phase_desc} -> {algo_desc}")

    # Load feature column lists
    with open(feature_cols_path) as f:
        feature_cols_data = json.load(f)
    quali_feature_list = feature_cols_data["quali_features"]
    race_feature_list = feature_cols_data.get("race_fp_features") if use_fp_race_model else None
    if not race_feature_list:
        race_feature_list = feature_cols_data["race_features"]

    # Load FP signal model (optional, pkl format)
    fp_info = joblib.load(fp_model_path) if fp_model_path.exists() else None

    # ---- Step 6: Predict qualifying ----
    print(f"\n[Step 6] Predicting qualifying positions...")
    # XGBoost requires ALL training features present (NaN is fine for missing)
    for col in quali_feature_list:
        if col not in pred_df.columns:
            pred_df[col] = np.nan
    X_q = pred_df[quali_feature_list].copy()
    quali_raw = quali_model.predict(X_q)

    # ---- FP-pace blend for qualifying (see FP_QUALI_BLEND_TUNABLES) ----
    # Lean the model's quali ordering toward this weekend's FP single-lap pace,
    # which backtests as a stronger quali predictor than the model alone. Done in
    # z-score space and OVERWRITES quali_raw so both predicted_quali_position AND
    # predicted_quali_raw (-> MC sim, -> race model's quali_position feature)
    # inherit the blend. Only blends drivers that actually set an FP lap.
    fp_blend = FP_QUALI_BLEND_TUNABLES
    pace_cols = [c for c in fp_blend["pace_cols"] if c in pred_df.columns]
    # Scale the FP weight up on quali-dominant (hard-to-overtake) tracks.
    w_fp = fp_quali_blend_weight(
        target_circuit, fp_blend["weight"], fp_blend["weight_hard_track"],
        fp_blend["hard_track_pivot"],
    )
    if w_fp > 0 and pace_cols:
        def _zscore_q(a: np.ndarray) -> np.ndarray:
            a = np.asarray(a, dtype=float)
            s = a.std()
            return (a - a.mean()) / s if s > 1e-9 else a - a.mean()

        # Composite FP quali-pace signal: mean of per-metric z-scores, negated so
        # a faster (lower) time scores higher. Blending the single best lap with
        # best-3 and best-5 lap averages rewards repeatable pace over a one-off
        # banker lap (backtests better than any single metric — see tunables).
        zmat = []
        for c in pace_cols:
            col = pd.to_numeric(pred_df[c], errors="coerce")
            sd = col.std()
            zmat.append(-(col - col.mean()) / sd if sd and sd > 1e-9 else col * 0.0)
        fp_pace_z = pd.concat(zmat, axis=1).mean(axis=1, skipna=True)  # NaN if all metrics NaN
        has_pace = fp_pace_z.notna().values
        if int(has_pace.sum()) >= fp_blend["min_drivers_with_pace"]:
            z_model = _zscore_q(quali_raw)
            comp_z = np.zeros(len(pred_df))
            comp_z[has_pace] = _zscore_q(fp_pace_z.values[has_pace])
            blended = z_model.copy()
            blended[has_pace] = (1.0 - w_fp) * z_model[has_pace] + w_fp * comp_z[has_pace]
            quali_raw = blended
            print(f"  FP-pace quali blend applied (weight={w_fp:.2f}, "
                  f"cols={pace_cols}, {int(has_pace.sum())}/{len(pred_df)} drivers)")
        else:
            print(f"  FP-pace quali blend skipped (only {int(has_pace.sum())} drivers "
                  f"with FP pace < {fp_blend['min_drivers_with_pace']} min)")

    # Ranking model: higher score = better position (P1). Rank descending.
    quali_ranks = pd.Series(-quali_raw).rank(method="first").astype(int)
    pred_df["predicted_quali_position"] = quali_ranks.values
    pred_df["predicted_quali_raw"] = quali_raw

    # ---- Step 7: Build race features, then predict race ----
    # Use actual quali if post-quali (known), otherwise predicted quali.
    # This is consistent with how each race model was trained:
    #   race_model    -> trained on actual quali    -> post-quali inference
    #   race_model_fp -> trained on predicted quali -> post-FP inference
    print(f"\n[Step 7] Predicting race positions...")
    if is_post_quali and not use_fp_race_model:
        # Map actual quali onto pred_df by driver_id
        pred_df["quali_position"] = pred_df["driver_id"].map(actual_quali_map)
        # For any driver missing actual quali, fall back to predicted
        missing = pred_df["quali_position"].isna()
        if missing.any():
            pred_df.loc[missing, "quali_position"] = pred_df.loc[missing, "predicted_quali_position"]
            print(f"  Using actual quali for {(~missing).sum()}/{len(pred_df)} drivers (rest from predicted)")
        else:
            print(f"  Using actual quali for all {len(pred_df)} drivers")
    else:
        pred_df["quali_position"] = pred_df["predicted_quali_position"]
        print(f"  Using predicted quali for all {len(pred_df)} drivers")
    pred_df["grid"] = pred_df["quali_position"]

    # Recompute grid-dependent features
    # NOTE: grid_advantage formula MUST match 03b_build_jolpica_features.py::add_race_model_features
    # (training data) to avoid train/inference distribution mismatch.
    pred_df["is_pole_position"] = (pred_df["quali_position"] == 1).astype(int)
    pred_df["is_front_row"] = (pred_df["quali_position"] <= 2).astype(int)
    pred_df["is_top10_quali"] = (pred_df["quali_position"] <= 10).astype(int)
    pred_df["grid_advantage"] = 11.0 - pred_df["quali_position"].astype(float)
    pred_df["grid_penalty"] = 0  # No grid penalties at prediction time

    # Recompute interaction features if track data available
    if "overtaking_difficulty" in pred_df.columns:
        pred_df["grid_importance_factor"] = pred_df["overtaking_difficulty"] / 10.0
        pred_df["pole_advantage"] = pred_df["is_pole_position"] * (
            1 + 2 * pred_df["grid_importance_factor"]
        )
        pred_df["front_row_advantage"] = pred_df["is_front_row"] * (
            0.5 + 1 * pred_df["grid_importance_factor"]
        )
    if "team_strategy_rating" in pred_df.columns and "safety_car_probability" in pred_df.columns:
        pred_df["strategy_sc_advantage"] = (
            pred_df["team_strategy_rating"] * pred_df["safety_car_probability"] / 10.0
        )
    if "is_top10_quali" in pred_df.columns:
        for col_pair in [("safety_car_probability", "top10_sc_interaction"),
                         ("turn1_incident_risk", "top10_turn1_interaction"),
                         ("is_street", "top10_street_interaction")]:
            track_col, out_col = col_pair
            if track_col in pred_df.columns:
                pred_df[out_col] = pred_df["is_top10_quali"] * pred_df[track_col]

    # Re-engineer FP features that depend on quali
    if "pace_rank" in pred_df.columns:
        pred_df["quali_vs_fp_rank"] = pred_df["quali_position"] - pred_df["pace_rank"]

    for col in race_feature_list:
        if col not in pred_df.columns:
            pred_df[col] = np.nan
    X_r = pred_df[race_feature_list].copy()
    race_raw = race_model.predict(X_r)

    # ---- Grid-anchoring on hard-to-overtake circuits ----
    # At tracks like Monaco the race result tracks the starting grid far more
    # than pure race-pace ranking implies — a P4 starter shouldn't be predicted
    # to win when overtaking is near-impossible. Blend the race model's ordering
    # toward the grid, scaled by the circuit's overtaking_difficulty (0 weight at
    # normal tracks). We blend in z-score space so the grid (uniform 1..N) and
    # the model scores are on a comparable scale, then OVERWRITE predicted_race_raw
    # so the anchoring flows to BOTH the deterministic finish AND the Monte Carlo
    # sim (08 re-ranks from predicted_race_raw). The MC re-normalizes anyway, so
    # only the ordering + relative gaps change — the noise treatment is untouched.
    anchor_w = grid_anchor_weight(target_circuit)
    if anchor_w > 0:
        def _zscore(a: np.ndarray) -> np.ndarray:
            a = np.asarray(a, dtype=float)
            s = a.std()
            return (a - a.mean()) / s if s > 1e-9 else a - a.mean()

        grid_pos = pred_df["quali_position"].astype(float).values
        z_race = _zscore(race_raw)
        z_grid = _zscore(-grid_pos)  # pole (grid 1) -> highest score
        race_raw = (1.0 - anchor_w) * z_race + anchor_w * z_grid
        print(f"  Grid-anchoring applied (circuit={target_circuit}, "
              f"difficulty-scaled weight={anchor_w:.2f})")

    # Ranking model: higher score = better position (P1). Rank descending.
    race_ranks = pd.Series(-race_raw).rank(method="first").astype(int)
    pred_df["predicted_race_position"] = race_ranks.values
    pred_df["predicted_race_raw"] = race_raw

    # ---- Step 8: FP signal + confidence ----
    print(f"\n[Step 8] Computing confidence scores...")
    fp_signal_pred = None
    if fp_info is not None:
        fp_features = [c for c in fp_info["features"] if c in pred_df.columns]
        if fp_features:
            X_fp = pred_df[fp_features].fillna(pred_df[fp_features].median())
            fp_signal_pred = fp_info["model"].predict(X_fp)

    confidence = calculate_confidence(pred_df, quali_raw, race_raw, fp_signal_pred)
    pred_df["confidence"] = confidence

    # ---- Sprint predictions (dedicated sprint model) ----
    if is_sprint:
        print(f"\n[Sprint] Generating sprint predictions...")
        sprint_model_path = TRAINED_DIR / "sprint_model.json"
        sprint_fp_model_path = TRAINED_DIR / "sprint_model_fp.json"
        sprint_feature_list = feature_cols_data.get("sprint_features", race_feature_list)
        sprint_fp_feature_list = feature_cols_data.get(
            "sprint_fp_features", sprint_feature_list
        )

        # === Load actual sprint qualifying grid ===
        # For sprint weekends, sprint qualifying (Shootout) happens BEFORE our deadline.
        # This is analogous to how quali_position feeds the race model.
        sprint_grid_loaded = False

        # Method 1: Check normalized sprint_results.csv (for completed sprint rounds)
        sprint_csv = Path(JOLPICA_MODEL_ROWS_DIR).parent / "normalized" / str(year) / "sprint_results.csv"
        if sprint_csv.exists():
            sprint_res = pd.read_csv(sprint_csv)
            sprint_res = sprint_res[sprint_res["round"] == round_num]
            if not sprint_res.empty and "grid" in sprint_res.columns:
                grid_map = dict(zip(sprint_res["driver_id"], sprint_res["grid"]))
                pred_df["sprint_grid"] = pred_df["driver_id"].map(grid_map)
                n_mapped = pred_df["sprint_grid"].notna().sum()
                if n_mapped > 0:
                    sprint_grid_loaded = True
                    print(f"  Loaded sprint grid from sprint_results.csv: {n_mapped}/{len(pred_df)} drivers")

        # Method 2: Try FastF1 Sprint Shootout / Sprint Qualifying session results
        if not sprint_grid_loaded:
            try:
                import fastf1
                ff1_round = fastf1_round(round_num, year)
                abbrev_to_jolpica, _ = load_driver_id_maps()
                for sq_name in ["Sprint Shootout", "Sprint Qualifying", "SQ"]:
                    try:
                        sq_session = fastf1.get_session(year, ff1_round, sq_name)
                        # Load laps too — Ergast doesn't expose sprint-quali results,
                        # so Position is often NaN even when timing data is available.
                        # We fall back to ranking by each driver's fastest lap.
                        sq_session.load(laps=True, telemetry=False, weather=False, messages=False)
                        sq_results = sq_session.results
                        if sq_results is not None and not sq_results.empty:
                            # Path A: official Position column populated
                            if (
                                "Abbreviation" in sq_results.columns
                                and "Position" in sq_results.columns
                                and sq_results["Position"].notna().any()
                            ):
                                for _, row in sq_results.iterrows():
                                    pos = row["Position"]
                                    if pd.isna(pos):
                                        continue
                                    did = abbrev_to_jolpica.get(row["Abbreviation"])
                                    if did is not None:
                                        mask = pred_df["driver_id"] == did
                                        pred_df.loc[mask, "sprint_grid"] = int(pos)
                                n_mapped = pred_df["sprint_grid"].notna().sum()
                                if n_mapped > 0:
                                    sprint_grid_loaded = True
                                    print(f"  Loaded sprint grid from FastF1 {sq_name} results: {n_mapped}/{len(pred_df)} drivers")
                                    break

                            # Path B: derive from fastest lap per driver
                            laps = sq_session.laps
                            if laps is not None and not laps.empty and "LapTime" in laps.columns:
                                fastest = (
                                    laps.dropna(subset=["LapTime"])
                                        .groupby("Driver")["LapTime"].min()
                                        .sort_values()
                                )
                                if len(fastest) > 0:
                                    for rank, abbrev in enumerate(fastest.index, start=1):
                                        did = abbrev_to_jolpica.get(abbrev)
                                        if did is not None:
                                            mask = pred_df["driver_id"] == did
                                            pred_df.loc[mask, "sprint_grid"] = rank
                                    n_mapped = pred_df["sprint_grid"].notna().sum()
                                    if n_mapped > 0:
                                        sprint_grid_loaded = True
                                        print(f"  Loaded sprint grid from FastF1 {sq_name} fastest laps: {n_mapped}/{len(pred_df)} drivers")
                                        break
                    except Exception:
                        continue
            except Exception as e:
                print(f"  Could not load FastF1 sprint qualifying: {e}")

        # Method 3: Fall back to predicted qualifying positions
        if not sprint_grid_loaded:
            print(f"  No sprint qualifying data available — using predicted qualifying as sprint grid proxy")
            pred_df["sprint_grid"] = pred_df["predicted_quali_position"]

        # Flag whether the sprint grid is the ACTUAL sprint-qualifying result
        # (known, post-SQ) or a predicted proxy (pre-SQ). The MC (08) uses this:
        # when actual, the sprint grid is fixed every simulation instead of being
        # resampled from the Sunday-quali distribution.
        pred_df["sprint_grid_is_actual"] = bool(sprint_grid_loaded)

        # Compute sprint-grid-derived features (formulas MUST match
        # 05_train_models.py sprint training block)
        sg = pred_df["sprint_grid"]
        pred_df["sprint_is_front_row"] = (sg <= 2).astype(int)
        pred_df["sprint_is_top3"] = (sg <= 3).astype(int)
        pred_df["sprint_is_top10"] = (sg <= 10).astype(int)
        pred_df["sprint_grid_advantage"] = 1.0 / (sg + 0.5)
        if "quali_position" in pred_df.columns:
            pred_df["quali_to_sprint_grid_delta"] = pred_df["quali_position"] - sg

        # Sprint qualifying position for display / fantasy scoring
        pred_df["predicted_sprint_quali_position"] = pred_df["sprint_grid"].astype(int)

        # Phase-aware sprint model selection:
        #   - Post-FP (pre-sprint-quali, sprint_grid is fallback proxy) -> sprint_model_fp.json
        #     (trained with WF-predicted quali as both quali_position and sprint_grid)
        #   - Post-sprint-quali (actual sprint_grid loaded)             -> sprint_model.json
        use_fp_sprint_model = (not sprint_grid_loaded) and sprint_fp_model_path.exists()
        if use_fp_sprint_model:
            # For consistency with training: when the fp variant is chosen, the
            # training data substituted sprint_grid == predicted_quali, so the
            # quali_to_sprint_grid_delta feature is 0 by construction. Replicate
            # that at inference so the feature distribution matches.
            pred_df["quali_to_sprint_grid_delta"] = 0.0

        active_sprint_path = sprint_fp_model_path if use_fp_sprint_model else sprint_model_path
        active_sprint_features = sprint_fp_feature_list if use_fp_sprint_model else sprint_feature_list

        if active_sprint_path.exists():
            if use_fp_sprint_model:
                phase_label = "post-FP (pre-sprint-quali) -> sprint_model_fp.json"
            elif sprint_grid_loaded:
                phase_label = "post-sprint-quali (sprint_grid known) -> sprint_model.json"
            else:
                phase_label = ("post-FP (pre-sprint-quali) -> sprint_model.json "
                               "(no sprint_model_fp.json available; falling back)")
            print(f"  Phase: {phase_label}")
            sprint_model = xgb.XGBRanker()
            sprint_model.load_model(str(active_sprint_path))

            for col in active_sprint_features:
                if col not in pred_df.columns:
                    pred_df[col] = np.nan
            X_s = pred_df[active_sprint_features].copy()
            sprint_raw = sprint_model.predict(X_s)
            sprint_ranks = pd.Series(-sprint_raw).rank(method="first").astype(int)
            pred_df["predicted_sprint_position"] = sprint_ranks.values
            pred_df["predicted_sprint_raw"] = sprint_raw
        else:
            print(f"  No sprint model found — falling back to race model")
            pred_df["predicted_sprint_position"] = pred_df["predicted_race_position"].values
            pred_df["predicted_sprint_raw"] = race_raw

    # ---- Build output ----
    # Map driver_id back to abbreviation for readability
    _, jolpica_to_abbrev = load_driver_id_maps()
    pred_df["driver_abbrev"] = pred_df["driver_id"].map(jolpica_to_abbrev)

    output_cols = [
        "driver_id", "driver_abbrev", "constructor_id",
        "predicted_quali_position", "predicted_race_position", "confidence",
        "predicted_quali_raw", "predicted_race_raw",
    ]
    if is_sprint:
        output_cols += ["predicted_sprint_position", "predicted_sprint_quali_position",
                        "predicted_sprint_raw", "sprint_grid", "sprint_grid_is_actual"]

    # Add key features for transparency
    extra = ["best_lap_time", "avg_lap_time", "pace_rank", "long_run_avg",
             "driver_roll_quali_3", "roll_finishpos_3", "team_recent_form"]
    for col in extra:
        if col in pred_df.columns:
            output_cols.append(col)

    output_cols = [c for c in output_cols if c in pred_df.columns]
    output_df = pred_df[output_cols].copy()
    output_df["season"] = year
    output_df["round"] = round_num
    output_df["is_sprint_weekend"] = is_sprint

    # Save
    output_dir = PREDICTIONS_DIR / f"round{round_num}"
    output_dir.mkdir(parents=True, exist_ok=True)
    # P9: same suffix convention as the guard above
    output_path = output_dir / out_filename
    output_df.to_parquet(output_path, index=False, engine="pyarrow")

    # Write prediction metadata sidecar — the DEFINITIVE record of what phase
    # this prediction ran in. Read by 08_export_website_json.py instead of
    # inferring from data state (which can drift). The sidecar is the source
    # of truth.
    from datetime import datetime, timezone
    import hashlib
    has_fp = (fp_df is not None) and (not fp_df.empty) and (not skip_fp)
    if is_post_quali:
        resolved_phase = "post_quali"
    elif has_fp:
        resolved_phase = "post_fp"
    else:
        resolved_phase = "pre_fp"

    # Hash the model file we actually used so anyone can verify reproducibility.
    def _file_sha256(p):
        try:
            with open(p, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception:
            return None

    # Record the model that ACTUALLY made the prediction (CatBoost .cbm when the
    # flag selected it, else the XGBoost .json) so the audit trail / accuracy
    # archive attribute the forecast to the right algorithm.
    race_model_used = chosen_cbm if use_catboost_race else chosen_json
    metadata = {
        "round": round_num,
        "year": year,
        "phase": resolved_phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_post_quali": is_post_quali,
        "used_fp_features": has_fp,
        "skip_fp_flag": skip_fp,
        "force_flag": force,
        "race_model_used": race_model_used.name,
        "race_model_algorithm": "catboost" if use_catboost_race else "xgboost",
        "quali_model_sha256_16": _file_sha256(quali_path),
        "race_model_sha256_16": _file_sha256(race_model_used),
        # Level 3: record exactly which weather values the model conditioned on,
        # so the Accuracy / Changelog tabs can diagnose "why does this round
        # predict X" without re-running the pipeline.
        "weather_features_used": weather_meta,
    }
    # P9: suffix the metadata file alongside the predictions parquet
    meta_filename = f"prediction_metadata_{output_suffix}.json" if output_suffix else "prediction_metadata.json"
    metadata_path = output_dir / meta_filename
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved -> {metadata_path}  (phase={resolved_phase})")

    # Pretty print
    print(f"\n{'=' * 70}")
    print(f"PREDICTIONS — {year} Round {round_num}")
    print(f"{'=' * 70}")
    display_cols = ["driver_abbrev", "predicted_quali_position",
                    "predicted_race_position", "confidence"]
    if is_sprint:
        display_cols.append("predicted_sprint_position")
    display_cols = [c for c in display_cols if c in output_df.columns]
    print(output_df[display_cols]
          .sort_values("predicted_race_position")
          .to_string(index=False))

    print(f"\nSaved -> {output_path}")
    print("=" * 70)

    return output_df


# -- CLI -----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run F1 predictions for a round")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON, help="Season year")
    parser.add_argument("--force", action="store_true",
                        help="Override the race-completed guard (overwrite existing predictions)")
    parser.add_argument("--no-fp", dest="no_fp", action="store_true",
                        help="Ignore FP feature parquets even if present (priors-only prediction)")
    args = parser.parse_args()

    run_predictions(args.round, args.year, force=args.force, skip_fp=args.no_fp)


if __name__ == "__main__":
    main()
