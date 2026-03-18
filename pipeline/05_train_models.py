"""
Script 05 — Train Models (Combined Jolpica Priors + FP Telemetry)

Trains XGBoost models for qualifying and race position prediction using
the combined two-layer feature system:
  Layer 1: Jolpica historical priors (always available, ~2600 rows)
  Layer 2: FP telemetry features (sparse, ~160 rows — NaN for rest)

XGBoost with tree_method="hist" handles NaN natively — no imputation needed.

Validation: Walk-forward (train [2020..N] → test N+1) instead of GroupKFold,
which is more realistic for time-series prediction.

Models:
  1. Qualifying model — XGBoost (1200 trees, lr=0.025, depth=3)
  2. Race model — XGBoost (650 trees, lr=0.03, depth=5)
  3. FP signal model — ExtraTrees (pace subset for confidence scoring)

Output:
    models/trained/quali_model.pkl
    models/trained/race_model.pkl
    models/trained/fp_model.pkl
"""

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.ensemble import ExtraTreesRegressor

warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    HISTORICAL_SEASONS,
    TRAINING_DATA_DIR,
    TRAINED_DIR,
    MODEL_RANDOM_STATE,
    REGULATION_CHANGE_YEAR,
    REGULATION_WEIGHT_MULTIPLIER,
)
from pipeline.feature_engineering import engineer_features

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost not installed. Run: pip install xgboost")
    sys.exit(1)


# ============================================================
# Feature Sets
# ============================================================

# --- Qualifying features (~62 features) ---
# Jolpica priors (always available)
QUALI_PRIOR_FEATURES = [
    "driver_quali_last", "driver_roll_quali_3", "driver_roll_quali_5",
    "driver_season_avg_quali", "driver_season_med_quali",
    "constructor_quali_last", "constructor_roll_quali_3", "constructor_roll_quali_5",
    "constructor_season_avg_quali",
    "field_season_avg_quali", "driver_vs_field_season", "constructor_vs_field_season",
    "team_delta_last", "team_delta_roll_3", "team_delta_roll_5",
    "driver_circuit_exp", "driver_circuit_roll_3", "constructor_circuit_exp",
]

# Track features
TRACK_FEATURES = [
    "is_street", "overtaking_difficulty", "avg_corner_speed",
    "straight_line_importance", "downforce_level", "turn1_incident_risk",
    "safety_car_probability", "track_evolution", "grip_level",
]

# Rating features relevant to qualifying
QUALI_RATING_FEATURES = [
    "driver_quali_skill", "team_strategy_rating", "team_adaptability",
]

# FP telemetry (sparse — NaN for most rows, XGBoost handles natively)
FP_PACE_FEATURES = [
    "avg_lap_time", "best_lap_time", "median_lap_time", "pace_rank",
    "best_3_lap_avg", "best_5_lap_avg", "best_10_lap_avg", "p50_to_p95_avg",
    "lap_time_std", "lap_time_variance",
    "short_run_best",
    "avg_sector_1", "avg_sector_2", "avg_sector_3",
    "best_sector_1", "best_sector_2", "best_sector_3",
    "total_laps", "fp_sessions_used",
]

# Engineered FP features (also sparse)
FP_ENGINEERED_FEATURES = [
    "pace_delta", "pace_consistency_ratio",
    "sector_1_delta", "sector_2_delta", "sector_3_delta",
    "theoretical_best", "cv_lap_time", "laps_per_session",
    "top3_vs_top5", "top5_vs_top10",
]

# Cross-layer interaction
CROSS_LAYER_FEATURES = [
    "prior_vs_fp_rank",
]

# Season meta
META_FEATURES = [
    "season_progress",
]

QUALI_FEATURES = (
    QUALI_PRIOR_FEATURES + TRACK_FEATURES + QUALI_RATING_FEATURES +
    FP_PACE_FEATURES + FP_ENGINEERED_FEATURES + CROSS_LAYER_FEATURES +
    META_FEATURES
)

# --- Race features (~85 features) ---
# All qualifying features plus race-specific priors, form, and interactions
RACE_ROLLING_FEATURES = [
    "roll_points_3", "roll_points_5",
    "roll_finishpos_3", "roll_finishpos_5",
    "roll_dnf_rate_5",
    "roll_mech_dnf_rate_5_driver", "roll_collision_dnf_rate_5_driver",
    "roll_drivererror_dnf_rate_5_driver", "roll_mech_dnf_rate_5_constructor",
]

RACE_DERIVED_FEATURES = [
    "team_avg_position", "driver_circuit_avg", "driver_overall_avg",
    "is_pole_position", "is_front_row", "is_top10_quali", "grid_advantage",
    "recent_wins", "recent_podiums", "recent_points_rate",
    "recent_form_weighted", "hot_streak", "dominant_form",
    "team_recent_form", "race_vs_quali_advantage", "teammate_gap", "form_trend",
    "grid_penalty", "season_progress",
]

RACE_INTERACTION_FEATURES = [
    "grid_importance_factor", "pole_advantage", "front_row_advantage",
    "strategy_sc_advantage", "top10_sc_interaction",
    "top10_turn1_interaction", "top10_street_interaction",
]

RACE_RATING_FEATURES = [
    "driver_tire_mgmt", "driver_overtaking",
    "team_strategy_rating", "team_adaptability",
]

FP_RACE_FEATURES = [
    "degradation_rate", "long_run_avg", "long_run_rank", "long_run_laps",
]

FP_RACE_ENGINEERED = [
    "long_run_delta", "deg_x_laps", "quali_vs_fp_rank",
]

RACE_FEATURES = (
    QUALI_PRIOR_FEATURES + TRACK_FEATURES +
    RACE_ROLLING_FEATURES + RACE_DERIVED_FEATURES + RACE_INTERACTION_FEATURES +
    RACE_RATING_FEATURES +
    FP_PACE_FEATURES + FP_ENGINEERED_FEATURES + CROSS_LAYER_FEATURES +
    FP_RACE_FEATURES + FP_RACE_ENGINEERED +
    ["quali_position"]  # actual or predicted quali feeds into race model
)

# FP signal: pace-focused subset for confidence scoring
FP_SIGNAL_FEATURES = [
    "avg_lap_time", "best_lap_time", "median_lap_time",
    "best_5_lap_avg", "p50_to_p95_avg",
    "degradation_rate", "long_run_avg", "lap_time_std",
    "pace_delta", "theoretical_best", "cv_lap_time",
]


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
) -> list[dict]:
    """
    Walk-forward validation: train on [2020..N], test on N+1.

    Returns list of fold results with MAE, RMSE per fold.
    """
    available_features = [c for c in feature_cols if c in df.columns]
    missing = set(feature_cols) - set(available_features)
    if missing:
        print(f"  Note: {len(missing)} features not in data (will be NaN): {sorted(missing)[:5]}...")

    # Test years: 2022, 2023, 2024, 2025
    test_years = [y for y in sorted(df["season"].unique()) if y >= 2022]
    results = []

    for test_year in test_years:
        train_mask = df["season"] < test_year
        test_mask = df["season"] == test_year

        train_df = df[train_mask & df[target_col].notna()]
        test_df = df[test_mask & df[target_col].notna()]

        if len(train_df) < 50 or len(test_df) < 10:
            continue

        X_train = train_df[available_features]
        y_train = train_df[target_col]
        X_test = test_df[available_features]
        y_test = test_df[target_col]

        # Sample weights
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
            "mae": mae,
            "rmse": rmse,
        })
        print(f"    Train [2020-{int(test_year)-1}] ({len(train_df):,}) -> "
              f"Test {int(test_year)} ({len(test_df):,}): "
              f"MAE={mae:.3f}, RMSE={rmse:.3f}")

    if results:
        avg_mae = np.mean([r["mae"] for r in results])
        avg_rmse = np.mean([r["rmse"] for r in results])
        print(f"  Walk-forward avg: MAE={avg_mae:.3f}, RMSE={avg_rmse:.3f}")

    return results


# ============================================================
# Main
# ============================================================

def main() -> None:
    """Train all models using combined Jolpica priors + FP telemetry."""
    print("=" * 70)
    print("BoxBoxF1Fantasy — Train Models (Combined Jolpica + FP)")
    print("=" * 70)

    # Load training data
    training_path = TRAINING_DATA_DIR / "all_training_data.parquet"
    if not training_path.exists():
        print(f"Training data not found at {training_path}")
        print("Run 04_build_model_inputs.py first.")
        return

    df = pd.read_parquet(training_path)
    print(f"\nLoaded training data: {len(df):,} samples")
    print(f"Seasons: {sorted(df['season'].unique())}")
    print(f"Drivers: {df['driver_id'].nunique()}")

    # Apply feature engineering (creates engineered FP + cross-layer features)
    df = engineer_features(df)
    print(f"Columns after engineering: {df.shape[1]}")

    # FP coverage
    fp_rows = df["best_lap_time"].notna().sum()
    print(f"FP coverage: {fp_rows}/{len(df)} rows ({fp_rows/len(df):.1%})")

    TRAINED_DIR.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # MODEL 1: Qualifying — XGBoost
    # ================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 1: Qualifying Position — XGBoost")
    print(f"{'=' * 60}")

    quali_available = [c for c in QUALI_FEATURES if c in df.columns]
    quali_df = df[df["quali_position"].notna()].copy()
    print(f"  Features: {len(quali_available)}, Samples: {len(quali_df):,}")

    def make_quali_model():
        return xgb.XGBRegressor(
            n_estimators=1200,
            learning_rate=0.025,
            max_depth=3,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            gamma=0.05,
            reg_alpha=0.05,
            reg_lambda=1.0,
            tree_method="hist",
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    print("\n  Walk-forward validation:")
    quali_results = walk_forward_validate(
        quali_df, QUALI_FEATURES, "quali_position", make_quali_model, "Qualifying"
    )

    # Train final model on all data
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
    importances = pd.Series(
        quali_model.feature_importances_, index=quali_available
    ).sort_values(ascending=False)
    print(f"\n  Top 15 features:")
    for feat, imp in importances.head(15).items():
        print(f"    {feat}: {imp:.4f}")

    model_info = {
        "model": quali_model,
        "features": quali_available,
        "target": "quali_position",
        "training_samples": len(y_q),
        "algorithm": "XGBRegressor",
        "walk_forward_results": quali_results,
    }
    joblib.dump(model_info, TRAINED_DIR / "quali_model.pkl")
    print(f"  Saved -> models/trained/quali_model.pkl")

    # ================================================================
    # MODEL 2: Race — XGBoost
    # ================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 2: Race Position — XGBoost")
    print(f"{'=' * 60}")

    race_available = [c for c in RACE_FEATURES if c in df.columns]
    # Clean finishers only (no DNFs)
    race_df = df[
        (df["finish_position"].notna())
        & (df["is_dnf"] == 0)
        & (df["is_dsq"] == 0)
        & (df["is_dns"] == 0)
    ].copy()
    print(f"  Features: {len(race_available)}, Samples: {len(race_df):,} (clean finishers)")

    def make_race_model():
        return xgb.XGBRegressor(
            n_estimators=650,
            learning_rate=0.03,
            max_depth=5,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            gamma=0.1,
            reg_alpha=0.1,
            reg_lambda=1.0,
            tree_method="hist",
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    print("\n  Walk-forward validation:")
    race_results = walk_forward_validate(
        race_df, RACE_FEATURES, "finish_position", make_race_model, "Race"
    )

    # Train final model on all data
    print("\n  Training final race model on all data...")
    X_r = race_df[race_available]
    y_r = race_df["finish_position"]
    w_r = race_df["sample_weight"].values if "sample_weight" in race_df.columns else None

    race_model = make_race_model()
    if w_r is not None:
        race_model.fit(X_r, y_r, sample_weight=w_r)
    else:
        race_model.fit(X_r, y_r)

    importances = pd.Series(
        race_model.feature_importances_, index=race_available
    ).sort_values(ascending=False)
    print(f"\n  Top 15 features:")
    for feat, imp in importances.head(15).items():
        print(f"    {feat}: {imp:.4f}")

    model_info = {
        "model": race_model,
        "features": race_available,
        "target": "finish_position",
        "training_samples": len(y_r),
        "algorithm": "XGBRegressor",
        "walk_forward_results": race_results,
    }
    joblib.dump(model_info, TRAINED_DIR / "race_model.pkl")
    print(f"  Saved -> models/trained/race_model.pkl")

    # ================================================================
    # MODEL 3: FP Signal — ExtraTrees (for confidence scoring)
    # ================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 3: FP Signal — ExtraTrees (confidence scoring)")
    print(f"{'=' * 60}")

    fp_available = [c for c in FP_SIGNAL_FEATURES if c in df.columns]
    # Only rows with FP data
    fp_df = df[df["best_lap_time"].notna() & df["finish_position"].notna()].copy()
    print(f"  Features: {len(fp_available)}, Samples: {len(fp_df):,} (FP-available only)")

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

        fp_model.fit(X_fp, y_fp)

        importances = pd.Series(
            fp_model.feature_importances_, index=fp_available
        ).sort_values(ascending=False)
        print(f"\n  Top features:")
        for feat, imp in importances.head(10).items():
            print(f"    {feat}: {imp:.4f}")

        model_info = {
            "model": fp_model,
            "features": fp_available,
            "target": "finish_position",
            "training_samples": len(y_fp),
            "algorithm": "ExtraTreesRegressor",
        }
        joblib.dump(model_info, TRAINED_DIR / "fp_model.pkl")
        print(f"  Saved -> models/trained/fp_model.pkl")
    else:
        print(f"  Not enough FP data ({len(fp_df)} rows) — skipping FP signal model")

    # ================================================================
    # Summary
    # ================================================================
    print(f"\n{'=' * 70}")
    print("TRAINING SUMMARY")
    print(f"{'=' * 70}")
    if quali_results:
        avg_q = np.mean([r["mae"] for r in quali_results])
        print(f"  Qualifying walk-forward MAE: {avg_q:.3f}")
    if race_results:
        avg_r = np.mean([r["mae"] for r in race_results])
        print(f"  Race walk-forward MAE:       {avg_r:.3f}")
    print(f"  Models saved to: {TRAINED_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
