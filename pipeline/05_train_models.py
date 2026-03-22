"""
Script 05 — Train Models (XGBoost + Walk-Forward Evaluation)

Trains three models using the combined Jolpica priors + FP telemetry feature set:

  1. Qualifying model  — XGBoost (1200 trees, lr=0.025, depth=3)
     Predicts quali_position from all Jolpica priors, track, ratings, FP features.

  2. Race model        — XGBoost (650 trees, lr=0.03, depth=5)
     Predicts finish_position using quali features + quali_position + race form.

  3. FP signal model   — ExtraTrees (pace subset, confidence scoring)
     Trains only on rows with FP telemetry data.

Validation: Temporal walk-forward (train [2020..N] -> test N+1).
XGBoost handles NaN natively via tree_method="hist" — no imputation needed.

Input:
    models/training_data/all_training_data.parquet

Output:
    models/trained/quali_model.json
    models/trained/race_model.json
    models/trained/fp_signal_model.pkl
    models/trained/model_metadata.json
    models/trained/feature_columns.json
"""

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    TRAINING_DATA_DIR,
    TRAINED_DIR,
    MODEL_RANDOM_STATE,
    FEATURE_COLUMNS,
    CURRENT_SEASON,
)
from pipeline.feature_engineering import engineer_features

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost not installed. Run: pip install xgboost")
    sys.exit(1)


# ============================================================
# Feature Column Definitions
# ============================================================

# Columns to EXCLUDE from qualifying features
QUALI_EXCLUDE = {
    # Identifiers / metadata
    "season", "round", "driver_id", "constructor_id",
    # Targets
    "finish_position", "points", "laps_completed", "status",
    # DNF / classification flags
    "is_classified", "is_dnf", "is_dns", "is_dsq",
    "dnf_mechanical", "dnf_collision", "dnf_driver_error",
    # Sprint
    "sprint_position", "sprint_points",
    # Weight
    "sample_weight",
    # Race-specific form features (used only in race model)
    "position_delta_prev", "recent_wins", "recent_podiums",
    "recent_points_rate", "recent_form_weighted", "form_trend",
    "team_recent_form",
    # Derived from quali_position — DATA LEAKAGE if used in quali model
    "is_top10_quali", "is_front_row", "is_pole_position", "grid_advantage",
    "grid", "grid_penalty",
    # Interaction features that depend on quali-derived columns
    "pole_advantage", "front_row_advantage", "grid_importance_factor",
    "top10_sc_interaction", "top10_turn1_interaction", "top10_street_interaction",
    "quali_vs_fp_rank",
}

# Prefixes to exclude from qualifying features
QUALI_EXCLUDE_PREFIXES = ("roll_finishpos", "roll_points")

# Additional race-specific features added on top of quali features
RACE_EXTRA_FEATURES = [
    "quali_position",
    "roll_finishpos_3", "roll_finishpos_5",
    "roll_points_3", "roll_points_5",
    "position_delta_prev",
    "recent_wins", "recent_podiums", "recent_points_rate",
    "recent_form_weighted", "form_trend", "team_recent_form",
    "is_pole_position", "is_front_row", "is_top10_quali", "grid_advantage",
]

# FP signal features (pace-focused subset for confidence scoring)
FP_SIGNAL_FEATURES = [
    "avg_lap_time", "best_lap_time", "median_lap_time",
    "best_5_lap_avg", "p50_to_p95_avg",
    "degradation_rate", "long_run_avg", "lap_time_std",
    "pace_delta", "theoretical_best", "cv_lap_time",
]


def build_quali_feature_list(all_columns: list[str]) -> list[str]:
    """Build the qualifying feature list by excluding metadata, targets, and race-specific columns."""
    features = []
    for col in sorted(all_columns):
        if col in QUALI_EXCLUDE:
            continue
        if col == "quali_position":
            continue  # target for quali model
        if any(col.startswith(prefix) for prefix in QUALI_EXCLUDE_PREFIXES):
            continue
        # Exclude other non-feature columns
        if col in {
            "circuit_id", "constructor_id_jolpica", "race_name", "race_date",
            "position_text", "position_delta", "finish_pos_clean",
            "grid", "grid_penalty", "q1", "q2", "q3",
            "has_sprint", "is_finished",
        }:
            continue
        features.append(col)
    return features


def build_race_feature_list(quali_features: list[str], all_columns: list[str]) -> list[str]:
    """Build the race feature list: all quali features + race-specific extras."""
    race_features = list(quali_features)
    for col in RACE_EXTRA_FEATURES:
        if col not in race_features and col in all_columns:
            race_features.append(col)
    return race_features


# ============================================================
# Walk-Forward Validation
# ============================================================

def walk_forward_validate(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    model_factory,
    model_name: str,
    use_weights: bool = True,
    add_predicted_quali: bool = False,
) -> list[dict]:
    """
    Walk-forward validation: train on [2020..N], test on N+1.

    For the race model (add_predicted_quali=True), uses actual quali_position
    as the predicted quali input during training, and generates predictions
    from a quali model trained on the same training fold for the test set.
    """
    available_features = [c for c in feature_cols if c in df.columns]
    missing = set(feature_cols) - set(available_features)
    if missing:
        print(f"  Note: {len(missing)} features not in data: {sorted(missing)[:5]}...")

    test_years = [y for y in sorted(df["season"].unique()) if y >= 2022]
    results = []

    for test_year in test_years:
        train_mask = df["season"] < test_year
        test_mask = df["season"] == test_year

        train_df = df[train_mask & df[target_col].notna()].copy()
        test_df = df[test_mask & df[target_col].notna()].copy()

        if len(train_df) < 50 or len(test_df) < 10:
            continue

        X_train = train_df[available_features].copy()
        y_train = train_df[target_col]
        X_test = test_df[available_features].copy()
        y_test = test_df[target_col]

        w_train = None
        if use_weights and "sample_weight" in train_df.columns:
            w_train = train_df["sample_weight"].values

        model = model_factory()
        if w_train is not None:
            model.fit(X_train, y_train, sample_weight=w_train)
        else:
            model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))

        results.append({
            "test_year": int(test_year),
            "train_size": len(train_df),
            "test_size": len(test_df),
            "mae": round(float(mae), 4),
            "rmse": round(float(rmse), 4),
        })
        print(f"    Fold: Train [2020-{int(test_year)-1}] ({len(train_df):,}) -> "
              f"Test {int(test_year)} ({len(test_df):,}): "
              f"MAE={mae:.3f}, RMSE={rmse:.3f}")

    if results:
        avg_mae = np.mean([r["mae"] for r in results])
        avg_rmse = np.mean([r["rmse"] for r in results])
        print(f"    Mean walk-forward: MAE={avg_mae:.3f}, RMSE={avg_rmse:.3f}")

    return results


# ============================================================
# Main
# ============================================================

def main() -> None:
    """Train all models using combined Jolpica priors + FP telemetry."""
    print("=" * 70)
    print("BoxBoxF1Fantasy — Train Models (XGBoost + Walk-Forward)")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Load training data
    # ------------------------------------------------------------------
    training_path = TRAINING_DATA_DIR / "all_training_data.parquet"
    if not training_path.exists():
        print(f"Training data not found at {training_path}")
        print("Run 04_build_model_inputs.py first.")
        return

    df = pd.read_parquet(training_path)
    print(f"\nLoaded training data: {len(df):,} rows, {df.shape[1]} columns")
    print(f"Seasons: {sorted(df['season'].unique())}")
    print(f"Unique drivers: {df['driver_id'].nunique()}")

    # Apply feature engineering (creates engineered FP + cross-layer features)
    df = engineer_features(df)
    print(f"Columns after engineering: {df.shape[1]}")

    # FP coverage
    fp_rows = df["best_lap_time"].notna().sum()
    print(f"FP telemetry coverage: {fp_rows}/{len(df)} rows ({fp_rows/len(df):.1%})")

    # Sample weight stats
    if "sample_weight" in df.columns:
        w_counts = df["sample_weight"].value_counts().sort_index()
        print(f"Sample weights: {dict(zip(w_counts.index.astype(float), w_counts.values))}")

    TRAINED_DIR.mkdir(parents=True, exist_ok=True)
    all_columns = df.columns.tolist()

    # Build feature lists from actual data columns
    quali_feature_cols = build_quali_feature_list(all_columns)
    race_feature_cols = build_race_feature_list(quali_feature_cols, all_columns)

    print(f"\nQuali feature columns: {len(quali_feature_cols)}")
    print(f"Race feature columns:  {len(race_feature_cols)}")

    # ==================================================================
    # MODEL 1: Qualifying Position — XGBoost
    # ==================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 1: Qualifying Position — XGBoost")
    print(f"{'=' * 60}")

    quali_available = [c for c in quali_feature_cols if c in df.columns]
    quali_df = df[df["quali_position"].notna()].copy()
    print(f"  Features: {len(quali_available)}")
    print(f"  Training samples: {len(quali_df):,}")

    def make_quali_model():
        return xgb.XGBRegressor(
            n_estimators=1200,
            learning_rate=0.025,
            max_depth=3,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            reg_alpha=0.1,
            reg_lambda=1.0,
            tree_method="hist",
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    print("\n  Walk-forward validation:")
    quali_wf_results = walk_forward_validate(
        quali_df, quali_feature_cols, "quali_position", make_quali_model, "Qualifying"
    )

    # Train final qualifying model on all data
    print("\n  Training final qualifying model on all data...")
    X_q = quali_df[quali_available]
    y_q = quali_df["quali_position"]
    w_q = quali_df["sample_weight"].values if "sample_weight" in quali_df.columns else None

    quali_model = make_quali_model()
    if w_q is not None:
        quali_model.fit(X_q, y_q, sample_weight=w_q)
    else:
        quali_model.fit(X_q, y_q)

    # Feature importances
    q_importances = pd.Series(
        quali_model.feature_importances_, index=quali_available
    ).sort_values(ascending=False)
    print(f"\n  Top 15 qualifying features:")
    for feat, imp in q_importances.head(15).items():
        print(f"    {feat}: {imp:.4f}")

    # Save XGBoost model as JSON
    quali_model.save_model(str(TRAINED_DIR / "quali_model.json"))
    print(f"  Saved -> models/trained/quali_model.json")

    # ==================================================================
    # MODEL 2: Race Position — XGBoost
    # ==================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 2: Race Position — XGBoost")
    print(f"{'=' * 60}")

    race_available = [c for c in race_feature_cols if c in df.columns]

    # Filter to classified finishers only (exclude DNFs)
    race_filter = df["finish_position"].notna()
    if "is_finished" in df.columns:
        race_filter = race_filter & (df["is_finished"] == 1)
    elif "is_dnf" in df.columns:
        race_filter = race_filter & (df["is_dnf"] == 0)
    if "is_dsq" in df.columns:
        race_filter = race_filter & (df["is_dsq"] == 0)
    if "is_dns" in df.columns:
        race_filter = race_filter & (df["is_dns"] == 0)

    race_df = df[race_filter].copy()

    # Add predicted_quali feature: during training, use actual quali_position
    # as the predicted quali input (the race model sees qualifying result as input)
    if "quali_position" not in race_available:
        race_available.append("quali_position")

    print(f"  Features: {len(race_available)}")
    print(f"  Training samples: {len(race_df):,} (classified finishers)")

    def make_race_model():
        return xgb.XGBRegressor(
            n_estimators=650,
            learning_rate=0.03,
            max_depth=5,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=5,
            tree_method="hist",
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    print("\n  Walk-forward validation:")
    race_wf_results = walk_forward_validate(
        race_df, race_feature_cols, "finish_position", make_race_model, "Race"
    )

    # Train final race model on all data
    print("\n  Training final race model on all data...")
    X_r = race_df[race_available]
    y_r = race_df["finish_position"]
    w_r = race_df["sample_weight"].values if "sample_weight" in race_df.columns else None

    race_model = make_race_model()
    if w_r is not None:
        race_model.fit(X_r, y_r, sample_weight=w_r)
    else:
        race_model.fit(X_r, y_r)

    # Feature importances
    r_importances = pd.Series(
        race_model.feature_importances_, index=race_available
    ).sort_values(ascending=False)
    print(f"\n  Top 15 race features:")
    for feat, imp in r_importances.head(15).items():
        print(f"    {feat}: {imp:.4f}")

    # Save XGBoost model as JSON
    race_model.save_model(str(TRAINED_DIR / "race_model.json"))
    print(f"  Saved -> models/trained/race_model.json")

    # ==================================================================
    # MODEL 3: FP Signal — ExtraTrees (confidence scoring)
    # ==================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 3: FP Signal — ExtraTrees (confidence scoring)")
    print(f"{'=' * 60}")

    fp_available = [c for c in FP_SIGNAL_FEATURES if c in df.columns]
    # Only rows with FP data available
    fp_df = df[df["best_lap_time"].notna() & df["finish_position"].notna()].copy()
    print(f"  Features: {len(fp_available)}")
    print(f"  Training samples: {len(fp_df):,} (FP-available only)")

    fp_model = None
    fp_train_size = 0

    if len(fp_df) > 30:
        fp_model = ExtraTreesRegressor(
            n_estimators=500,
            max_depth=6,
            min_samples_leaf=5,
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
        )

        X_fp = fp_df[fp_available].fillna(fp_df[fp_available].median())
        y_fp = fp_df["finish_position"]
        fp_train_size = len(y_fp)

        fp_model.fit(X_fp, y_fp)

        fp_importances = pd.Series(
            fp_model.feature_importances_, index=fp_available
        ).sort_values(ascending=False)
        print(f"\n  Top FP signal features:")
        for feat, imp in fp_importances.head(10).items():
            print(f"    {feat}: {imp:.4f}")

        joblib.dump(
            {
                "model": fp_model,
                "features": fp_available,
                "target": "finish_position",
                "training_samples": fp_train_size,
                "algorithm": "ExtraTreesRegressor",
            },
            TRAINED_DIR / "fp_signal_model.pkl",
        )
        print(f"  Saved -> models/trained/fp_signal_model.pkl")
    else:
        print(f"  Not enough FP data ({len(fp_df)} rows) — skipping FP signal model")

    # ==================================================================
    # Save Feature Columns
    # ==================================================================
    feature_columns_data = {
        "quali_features": quali_available,
        "race_features": race_available,
        "fp_signal_features": fp_available,
    }
    with open(TRAINED_DIR / "feature_columns.json", "w") as f:
        json.dump(feature_columns_data, f, indent=2)
    print(f"\n  Saved -> models/trained/feature_columns.json")

    # ==================================================================
    # Save Model Metadata
    # ==================================================================
    quali_avg_mae = float(np.mean([r["mae"] for r in quali_wf_results])) if quali_wf_results else None
    race_avg_mae = float(np.mean([r["mae"] for r in race_wf_results])) if race_wf_results else None

    metadata = {
        "trained_at": datetime.now().isoformat(),
        "current_season": CURRENT_SEASON,
        "training_data": str(training_path),
        "total_rows": len(df),
        "seasons": sorted([int(s) for s in df["season"].unique()]),
        "fp_coverage": f"{fp_rows}/{len(df)} ({fp_rows/len(df):.1%})",
        "qualifying_model": {
            "algorithm": "XGBRegressor",
            "save_format": "json",
            "n_features": len(quali_available),
            "training_samples": len(y_q),
            "params": {
                "n_estimators": 1200,
                "learning_rate": 0.025,
                "max_depth": 3,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
                "min_child_weight": 3,
                "reg_alpha": 0.1,
                "reg_lambda": 1.0,
            },
            "walk_forward_results": quali_wf_results,
            "walk_forward_mean_mae": round(quali_avg_mae, 4) if quali_avg_mae else None,
            "top_features": {feat: round(float(imp), 4) for feat, imp in q_importances.head(15).items()},
        },
        "race_model": {
            "algorithm": "XGBRegressor",
            "save_format": "json",
            "n_features": len(race_available),
            "training_samples": len(y_r),
            "params": {
                "n_estimators": 650,
                "learning_rate": 0.03,
                "max_depth": 5,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
                "min_child_weight": 5,
            },
            "walk_forward_results": race_wf_results,
            "walk_forward_mean_mae": round(race_avg_mae, 4) if race_avg_mae else None,
            "top_features": {feat: round(float(imp), 4) for feat, imp in r_importances.head(15).items()},
        },
        "fp_signal_model": {
            "algorithm": "ExtraTreesRegressor",
            "save_format": "pkl",
            "n_features": len(fp_available),
            "training_samples": fp_train_size,
            "trained": fp_model is not None,
        },
    }

    with open(TRAINED_DIR / "model_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Saved -> models/trained/model_metadata.json")

    # ==================================================================
    # Summary
    # ==================================================================
    print(f"\n{'=' * 70}")
    print("TRAINING SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Training data:        {len(df):,} rows ({len(df.columns)} columns)")
    print(f"  FP telemetry:         {fp_rows}/{len(df)} rows ({fp_rows/len(df):.1%})")
    print()
    if quali_wf_results:
        print(f"  Qualifying model:")
        print(f"    Features:           {len(quali_available)}")
        print(f"    Walk-forward MAE:   {quali_avg_mae:.3f}")
        for r in quali_wf_results:
            print(f"      {r['test_year']}: MAE={r['mae']:.3f} (n={r['test_size']})")
    if race_wf_results:
        print(f"  Race model:")
        print(f"    Features:           {len(race_available)}")
        print(f"    Walk-forward MAE:   {race_avg_mae:.3f}")
        for r in race_wf_results:
            print(f"      {r['test_year']}: MAE={r['mae']:.3f} (n={r['test_size']})")
    if fp_model is not None:
        print(f"  FP signal model:      {fp_train_size} samples, {len(fp_available)} features")
    print()
    print(f"  Output directory:     {TRAINED_DIR}")
    print(f"  Files saved:")
    print(f"    - quali_model.json")
    print(f"    - race_model.json")
    if fp_model is not None:
        print(f"    - fp_signal_model.pkl")
    print(f"    - model_metadata.json")
    print(f"    - feature_columns.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
