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
    SEED_DIR,
    JOLPICA_MODEL_ROWS_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
)
from pipeline.feature_engineering import engineer_features
from config.track_classifications import get_circuit_id_from_race_name
from config.track_similarity import get_similarity


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

def run_predictions(round_num: int, year: int = CURRENT_SEASON) -> pd.DataFrame:
    """Generate predictions for a specific round."""
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Predictions for {year} Round {round_num}")
    print("=" * 70)

    if year == 2026 and round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled.")
        return pd.DataFrame()

    is_sprint = (year == 2026 and round_num in SPRINT_ROUNDS_2026)
    print(f"Sprint weekend: {'Yes' if is_sprint else 'No'}")

    # Load driver ID maps
    abbrev_to_jolpica, jolpica_to_abbrev = load_driver_id_maps()

    # ---- Step 1: Build Jolpica priors ----
    print(f"\n[Step 1] Building Jolpica priors...")
    priors_df = build_live_priors(round_num, year)
    print(f"  Prior rows: {len(priors_df)} drivers")

    # ---- Step 1b: Recompute track-similarity features for target circuit ----
    target_circuit = _resolve_circuit(round_num, year)
    if target_circuit and target_circuit != "unknown":
        print(f"  Recomputing similarity features for target circuit: {target_circuit}")
        priors_df = _recompute_sim_features(priors_df, target_circuit)
    else:
        print(f"  Could not resolve target circuit — using prior similarity features as-is")

    # ---- Step 2: Load FP features ----
    print(f"\n[Step 2] Loading FP telemetry features...")
    fp_path = FEATURES_DIR / f"round{round_num}" / "features.parquet"
    fp_df = None
    if fp_path.exists():
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
    fp_model_path = TRAINED_DIR / "fp_signal_model.pkl"
    feature_cols_path = TRAINED_DIR / "feature_columns.json"

    for p in [quali_path, race_path, feature_cols_path]:
        if not p.exists():
            print(f"ERROR: Model not found: {p}")
            print("Run 05_train_models.py first.")
            return pd.DataFrame()

    # Load XGBoost ranking models from JSON format
    # Models trained with rank:pairwise — output relevance scores (higher = better)
    quali_model = xgb.XGBRanker()
    quali_model.load_model(str(quali_path))
    race_model = xgb.XGBRanker()
    race_model.load_model(str(race_path))

    # Load feature column lists
    with open(feature_cols_path) as f:
        feature_cols_data = json.load(f)
    quali_feature_list = feature_cols_data["quali_features"]
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
    # Ranking model: higher score = better position (P1). Rank descending.
    quali_ranks = pd.Series(-quali_raw).rank(method="first").astype(int)
    pred_df["predicted_quali_position"] = quali_ranks.values
    pred_df["predicted_quali_raw"] = quali_raw

    # ---- Step 7: Build race features from predicted quali, then predict race ----
    print(f"\n[Step 7] Predicting race positions...")
    # Use predicted quali as the grid for race-specific features
    pred_df["quali_position"] = pred_df["predicted_quali_position"]
    pred_df["grid"] = pred_df["predicted_quali_position"]

    # Recompute grid-dependent features
    pred_df["is_pole_position"] = (pred_df["quali_position"] == 1).astype(int)
    pred_df["is_front_row"] = (pred_df["quali_position"] <= 2).astype(int)
    pred_df["is_top10_quali"] = (pred_df["quali_position"] <= 10).astype(int)
    pred_df["grid_advantage"] = 1.0 / (pred_df["grid"] + 0.5)
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
        sprint_feature_list = feature_cols_data.get("sprint_features", race_feature_list)

        # === Load actual sprint qualifying grid ===
        # For sprint weekends, sprint qualifying (Shootout) happens BEFORE our deadline.
        # This is analogous to how quali_position feeds the race model.
        sprint_grid_loaded = False

        # Method 1: Check normalized sprint_results.csv (for completed sprint rounds)
        sprint_csv = Path(JOLPICA_MODEL_ROWS_DIR).parent / "normalized" / str(year) / "sprint_results.csv"
        if sprint_csv.exists():
            sprint_res = pd.read_csv(sprint_csv)
            sprint_res = sprint_res[sprint_res["round"] == target_round]
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
                for sq_name in ["Sprint Shootout", "Sprint Qualifying", "SQ"]:
                    try:
                        sq_session = fastf1.get_session(year, target_round, sq_name)
                        sq_session.load(laps=False, telemetry=False, weather=False, messages=False)
                        sq_results = sq_session.results
                        if sq_results is not None and not sq_results.empty:
                            # Map FastF1 abbreviation to our driver_id
                            abbrev_to_jolpica, _ = load_driver_id_maps()
                            # FastF1 results have 'Abbreviation' and 'Position' columns
                            if "Abbreviation" in sq_results.columns and "Position" in sq_results.columns:
                                for _, row in sq_results.iterrows():
                                    abbrev = row["Abbreviation"]
                                    pos = row["Position"]
                                    # Find matching driver_id
                                    did = abbrev_to_jolpica.get(abbrev)
                                    if did is not None:
                                        mask = pred_df["driver_id"] == did
                                        pred_df.loc[mask, "sprint_grid"] = int(pos)
                                n_mapped = pred_df["sprint_grid"].notna().sum()
                                if n_mapped > 0:
                                    sprint_grid_loaded = True
                                    print(f"  Loaded sprint grid from FastF1 ({sq_name}): {n_mapped}/{len(pred_df)} drivers")
                                    break
                    except Exception:
                        continue
            except Exception as e:
                print(f"  Could not load FastF1 sprint qualifying: {e}")

        # Method 3: Fall back to predicted qualifying positions
        if not sprint_grid_loaded:
            print(f"  No sprint qualifying data available — using predicted qualifying as sprint grid proxy")
            pred_df["sprint_grid"] = pred_df["predicted_quali_position"]

        # Compute sprint-grid-derived features (same as training)
        sg = pred_df["sprint_grid"]
        pred_df["sprint_is_front_row"] = (sg <= 2).astype(int)
        pred_df["sprint_is_top3"] = (sg <= 3).astype(int)
        pred_df["sprint_is_top10"] = (sg <= 10).astype(int)
        pred_df["sprint_grid_advantage"] = 1.0 / (sg + 0.5)
        if "quali_position" in pred_df.columns:
            pred_df["quali_to_sprint_grid_delta"] = pred_df["quali_position"] - sg

        # Sprint qualifying position for display / fantasy scoring
        pred_df["predicted_sprint_quali_position"] = pred_df["sprint_grid"].astype(int)

        if sprint_model_path.exists():
            print(f"  Using dedicated sprint model")
            sprint_model = xgb.XGBRanker()
            sprint_model.load_model(str(sprint_model_path))

            for col in sprint_feature_list:
                if col not in pred_df.columns:
                    pred_df[col] = np.nan
            X_s = pred_df[sprint_feature_list].copy()
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
                        "predicted_sprint_raw"]

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
    output_path = output_dir / "predictions.parquet"
    output_df.to_parquet(output_path, index=False, engine="pyarrow")

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
    args = parser.parse_args()

    run_predictions(args.round, args.year)


if __name__ == "__main__":
    main()
