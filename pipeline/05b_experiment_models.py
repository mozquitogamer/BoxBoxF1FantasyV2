"""
Script 05b — Model Experimentation

Systematically tests different algorithms, hyperparameters, feature engineering,
and ensemble strategies to minimize Race MAE.

Goal: Get race position MAE from ~4.9 down to ~3.0
"""

import sys
import warnings
from pathlib import Path
from itertools import product

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.ensemble import (
    RandomForestRegressor,
    GradientBoostingRegressor,
    ExtraTreesRegressor,
    StackingRegressor,
    VotingRegressor,
)
from sklearn.linear_model import Ridge, Lasso, ElasticNet, BayesianRidge
from sklearn.svm import SVR
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    TRAINING_DATA_DIR,
    TRAINED_DIR,
    MODEL_RANDOM_STATE,
)


# ============================================================
# Feature sets
# ============================================================

QUALI_FEATURES_BASE = [
    "avg_lap_time", "best_lap_time", "median_lap_time",
    "pace_rank", "best_3_lap_avg", "best_5_lap_avg", "best_10_lap_avg",
    "p50_to_p95_avg", "lap_time_std", "lap_time_variance",
    "short_run_best",
    "avg_sector_1", "avg_sector_2", "avg_sector_3",
    "best_sector_1", "best_sector_2", "best_sector_3",
    "total_laps", "fp_sessions_used",
]

RACE_FEATURES_BASE = QUALI_FEATURES_BASE + [
    "degradation_rate", "long_run_avg", "long_run_rank",
    "long_run_laps", "qualifying_position",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create interaction and ratio features to help the model."""
    df = df.copy()

    # Pace deltas (relative to session, removes track-specific effects)
    if "best_lap_time" in df.columns and "avg_lap_time" in df.columns:
        df["pace_delta"] = df["avg_lap_time"] - df["best_lap_time"]
        df["pace_consistency_ratio"] = df["best_lap_time"] / df["avg_lap_time"].replace(0, np.nan)

    # Sector balance — how even are sectors vs. total
    for i in [1, 2, 3]:
        avg_col = f"avg_sector_{i}"
        best_col = f"best_sector_{i}"
        if avg_col in df.columns and best_col in df.columns:
            df[f"sector_{i}_delta"] = df[avg_col] - df[best_col]

    # Best sectors combined
    sector_cols = ["best_sector_1", "best_sector_2", "best_sector_3"]
    if all(c in df.columns for c in sector_cols):
        df["theoretical_best"] = df[sector_cols].sum(axis=1)

    # Long run quality
    if "long_run_avg" in df.columns and "best_lap_time" in df.columns:
        df["long_run_delta"] = df["long_run_avg"] - df["best_lap_time"]

    # Consistency features
    if "lap_time_std" in df.columns and "avg_lap_time" in df.columns:
        df["cv_lap_time"] = df["lap_time_std"] / df["avg_lap_time"].replace(0, np.nan)

    # Laps per session (experience/running)
    if "total_laps" in df.columns and "fp_sessions_used" in df.columns:
        df["laps_per_session"] = df["total_laps"] / df["fp_sessions_used"].replace(0, np.nan)

    # Top-N lap consistency
    if "best_3_lap_avg" in df.columns and "best_5_lap_avg" in df.columns:
        df["top3_vs_top5"] = df["best_3_lap_avg"] - df["best_5_lap_avg"]

    if "best_5_lap_avg" in df.columns and "best_10_lap_avg" in df.columns:
        df["top5_vs_top10"] = df["best_5_lap_avg"] - df["best_10_lap_avg"]

    # Degradation interaction
    if "degradation_rate" in df.columns and "long_run_laps" in df.columns:
        df["deg_x_laps"] = df["degradation_rate"] * df["long_run_laps"]

    # Qualifying gap feature (for race model)
    if "qualifying_position" in df.columns and "pace_rank" in df.columns:
        df["quali_vs_fp_rank"] = df["qualifying_position"] - df["pace_rank"]

    return df


# Extended feature lists including engineered features
QUALI_FEATURES_ENG = QUALI_FEATURES_BASE + [
    "pace_delta", "pace_consistency_ratio",
    "sector_1_delta", "sector_2_delta", "sector_3_delta",
    "theoretical_best", "cv_lap_time", "laps_per_session",
    "top3_vs_top5", "top5_vs_top10",
]

RACE_FEATURES_ENG = QUALI_FEATURES_ENG + [
    "degradation_rate", "long_run_avg", "long_run_rank",
    "long_run_laps", "qualifying_position",
    "long_run_delta", "deg_x_laps", "quali_vs_fp_rank",
]


# ============================================================
# Cross-validation harness
# ============================================================

def cross_validate(
    model,
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    sample_weights=None,
    n_splits: int = 5,
    use_weights_in_fit: bool = True,
) -> dict:
    """Run GroupKFold CV and return metrics."""
    n_splits = min(n_splits, groups.nunique())
    if n_splits < 2:
        return {"mae": np.nan, "rmse": np.nan, "mae_std": np.nan}

    gkf = GroupKFold(n_splits=n_splits)
    maes, rmses = [], []

    for train_idx, val_idx in gkf.split(X, y, groups):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        try:
            if sample_weights is not None and use_weights_in_fit:
                if hasattr(model, 'fit') and 'sample_weight' in model.fit.__code__.co_varnames:
                    model.fit(X_tr, y_tr, sample_weight=sample_weights[train_idx])
                else:
                    model.fit(X_tr, y_tr)
            else:
                model.fit(X_tr, y_tr)
        except TypeError:
            model.fit(X_tr, y_tr)

        y_pred = model.predict(X_val)
        maes.append(mean_absolute_error(y_val, y_pred))
        rmses.append(np.sqrt(mean_squared_error(y_val, y_pred)))

    return {
        "mae": np.mean(maes),
        "rmse": np.mean(rmses),
        "mae_std": np.std(maes),
        "rmse_std": np.std(rmses),
    }


# ============================================================
# Experiment runner
# ============================================================

def run_experiments():
    print("=" * 70)
    print("BoxBoxF1Fantasy — Model Experimentation")
    print("=" * 70)

    # Load data
    df = pd.read_parquet(TRAINING_DATA_DIR / "all_training_data.parquet")
    print(f"Data: {len(df)} samples, {df['year'].nunique()} years, {df.groupby('year')['round'].nunique().sum()} total rounds")

    # Engineer features
    df = engineer_features(df)

    # Prepare data
    race_valid = df[df["race_finish_position"].notna()].copy()
    quali_valid = df[df["qualifying_position"].notna()].copy()

    # ---- QUALIFYING EXPERIMENTS ----
    print(f"\n{'='*70}")
    print("QUALIFYING MODEL EXPERIMENTS")
    print(f"{'='*70}")

    quali_results = run_model_experiments(
        quali_valid, QUALI_FEATURES_BASE, QUALI_FEATURES_ENG,
        "qualifying_position", "Qualifying"
    )

    # ---- RACE EXPERIMENTS ----
    print(f"\n{'='*70}")
    print("RACE MODEL EXPERIMENTS")
    print(f"{'='*70}")

    race_results = run_model_experiments(
        race_valid, RACE_FEATURES_BASE, RACE_FEATURES_ENG,
        "race_finish_position", "Race"
    )

    # ---- ENSEMBLE EXPERIMENTS ----
    print(f"\n{'='*70}")
    print("ENSEMBLE / STACKING EXPERIMENTS")
    print(f"{'='*70}")

    ensemble_results = run_ensemble_experiments(
        race_valid, RACE_FEATURES_ENG, "race_finish_position"
    )

    # ---- SUMMARY ----
    print(f"\n{'='*70}")
    print("FINAL RESULTS SUMMARY")
    print(f"{'='*70}")

    all_results = []
    for name, res in quali_results:
        all_results.append(("QUALI", name, res))
    for name, res in race_results:
        all_results.append(("RACE", name, res))
    for name, res in ensemble_results:
        all_results.append(("RACE-ENS", name, res))

    print(f"\n{'Model':<12} {'Name':<45} {'MAE':>7} {'+-':>6} {'RMSE':>7}")
    print("-" * 80)
    for model_type, name, res in sorted(all_results, key=lambda x: (x[0], x[2].get('mae', 99))):
        mae = res.get('mae', np.nan)
        std = res.get('mae_std', np.nan)
        rmse = res.get('rmse', np.nan)
        print(f"{model_type:<12} {name:<45} {mae:>7.3f} {std:>6.3f} {rmse:>7.3f}")

    # Find best race model
    race_only = [(n, r) for t, n, r in all_results if t in ("RACE", "RACE-ENS")]
    best_name, best_res = min(race_only, key=lambda x: x[1].get('mae', 99))
    print(f"\n>>> Best Race Model: {best_name} (MAE={best_res['mae']:.3f})")

    quali_only = [(n, r) for t, n, r in all_results if t == "QUALI"]
    best_q_name, best_q_res = min(quali_only, key=lambda x: x[1].get('mae', 99))
    print(f">>> Best Quali Model: {best_q_name} (MAE={best_q_res['mae']:.3f})")

    return all_results


def run_model_experiments(df, features_base, features_eng, target, label):
    """Run experiments across algorithms and hyperparameters."""

    results = []

    # Prepare both feature sets
    avail_base = [c for c in features_base if c in df.columns]
    avail_eng = [c for c in features_eng if c in df.columns]

    X_base = df[avail_base].copy()
    X_eng = df[avail_eng].copy()
    y = df[target].copy()
    weights = df["sample_weight"].values if "sample_weight" in df.columns else None
    groups = df["year"].astype(str) + "_" + df["round"].astype(str)

    # Fill NaNs
    for X in [X_base, X_eng]:
        for col in X.columns:
            if X[col].isna().any():
                X[col] = X[col].fillna(X[col].median())

    # ---- 1. LightGBM hyperparameter grid ----
    print(f"\n--- LightGBM Grid Search ({label}) ---")

    lgb_configs = [
        # (name, params)
        ("LGB-base", {"n_estimators": 500, "max_depth": 6, "lr": 0.05, "num_leaves": 31, "min_child": 10}),
        ("LGB-deep", {"n_estimators": 500, "max_depth": 10, "lr": 0.05, "num_leaves": 63, "min_child": 5}),
        ("LGB-shallow", {"n_estimators": 500, "max_depth": 3, "lr": 0.05, "num_leaves": 8, "min_child": 15}),
        ("LGB-d4", {"n_estimators": 500, "max_depth": 4, "lr": 0.05, "num_leaves": 15, "min_child": 10}),
        ("LGB-d5", {"n_estimators": 800, "max_depth": 5, "lr": 0.03, "num_leaves": 20, "min_child": 8}),
        ("LGB-lowLR", {"n_estimators": 1000, "max_depth": 5, "lr": 0.01, "num_leaves": 20, "min_child": 10}),
        ("LGB-highReg", {"n_estimators": 500, "max_depth": 5, "lr": 0.05, "num_leaves": 20, "min_child": 15, "reg_a": 1.0, "reg_l": 1.0}),
        ("LGB-vhighReg", {"n_estimators": 500, "max_depth": 4, "lr": 0.05, "num_leaves": 12, "min_child": 20, "reg_a": 5.0, "reg_l": 5.0}),
        ("LGB-dart", {"n_estimators": 300, "max_depth": 5, "lr": 0.05, "num_leaves": 20, "min_child": 10, "boosting": "dart"}),
        ("LGB-tiny", {"n_estimators": 200, "max_depth": 3, "lr": 0.1, "num_leaves": 7, "min_child": 20}),
    ]

    for name, cfg in lgb_configs:
        params = {
            "n_estimators": cfg["n_estimators"],
            "max_depth": cfg["max_depth"],
            "learning_rate": cfg["lr"],
            "num_leaves": cfg["num_leaves"],
            "min_child_samples": cfg["min_child"],
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": cfg.get("reg_a", 0.1),
            "reg_lambda": cfg.get("reg_l", 0.1),
            "random_state": MODEL_RANDOM_STATE,
            "verbose": -1,
            "n_jobs": -1,
        }
        if "boosting" in cfg:
            params["boosting_type"] = cfg["boosting"]

        # Test with base features
        model = lgb.LGBMRegressor(**params)
        res = cross_validate(model, X_base, y, groups, weights)
        print(f"  {name:30s} base  MAE={res['mae']:.3f}+-{res['mae_std']:.3f}")
        results.append((f"{name}-base", res))

        # Test with engineered features
        model = lgb.LGBMRegressor(**params)
        res = cross_validate(model, X_eng, y, groups, weights)
        print(f"  {name:30s} eng   MAE={res['mae']:.3f}+-{res['mae_std']:.3f}")
        results.append((f"{name}-eng", res))

    # ---- 2. Other algorithms ----
    print(f"\n--- Alternative Algorithms ({label}) ---")

    alt_models = [
        ("RF-500", RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
        ("RF-1000-d8", RandomForestRegressor(n_estimators=1000, max_depth=8, min_samples_leaf=3, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
        ("RF-shallow", RandomForestRegressor(n_estimators=500, max_depth=4, min_samples_leaf=10, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
        ("ExtraTrees", ExtraTreesRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
        ("GBR-500", GradientBoostingRegressor(n_estimators=500, max_depth=4, learning_rate=0.05, min_samples_leaf=10, random_state=MODEL_RANDOM_STATE)),
        ("GBR-lowLR", GradientBoostingRegressor(n_estimators=1000, max_depth=3, learning_rate=0.01, min_samples_leaf=10, random_state=MODEL_RANDOM_STATE)),
        ("Ridge", Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])),
        ("Ridge-10", Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=10.0))])),
        ("Lasso", Pipeline([("scaler", StandardScaler()), ("model", Lasso(alpha=0.5))])),
        ("ElasticNet", Pipeline([("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.5, l1_ratio=0.5))])),
        ("BayesRidge", Pipeline([("scaler", StandardScaler()), ("model", BayesianRidge())])),
        ("KNN-5", Pipeline([("scaler", StandardScaler()), ("model", KNeighborsRegressor(n_neighbors=5))])),
        ("KNN-10", Pipeline([("scaler", StandardScaler()), ("model", KNeighborsRegressor(n_neighbors=10))])),
        ("SVR-rbf", Pipeline([("scaler", StandardScaler()), ("model", SVR(kernel="rbf", C=10))])),
        ("MLP", Pipeline([("scaler", StandardScaler()), ("model", MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=1000, random_state=MODEL_RANDOM_STATE))])),
        ("MLP-big", Pipeline([("scaler", StandardScaler()), ("model", MLPRegressor(hidden_layer_sizes=(128, 64, 32), max_iter=1500, random_state=MODEL_RANDOM_STATE))])),
    ]

    for name, model in alt_models:
        # Eng features
        res = cross_validate(model, X_eng, y, groups, weights, use_weights_in_fit=False)
        print(f"  {name:30s} eng   MAE={res['mae']:.3f}+-{res['mae_std']:.3f}")
        results.append((f"{name}-eng", res))

    return results


def run_ensemble_experiments(df, features_eng, target):
    """Try ensembles combining the best individual models."""

    results = []

    avail = [c for c in features_eng if c in df.columns]
    X = df[avail].copy()
    y = df[target].copy()
    weights = df["sample_weight"].values if "sample_weight" in df.columns else None
    groups = df["year"].astype(str) + "_" + df["round"].astype(str)

    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())

    # Voting ensemble (average predictions)
    print("\n--- Voting Ensembles ---")

    ens_configs = [
        ("Vote-LGB+RF", [
            ("lgb", lgb.LGBMRegressor(n_estimators=500, max_depth=5, learning_rate=0.03, num_leaves=20, min_child_samples=8, subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1, random_state=MODEL_RANDOM_STATE, verbose=-1)),
            ("rf", RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
        ]),
        ("Vote-LGB+GBR", [
            ("lgb", lgb.LGBMRegressor(n_estimators=500, max_depth=5, learning_rate=0.03, num_leaves=20, min_child_samples=8, subsample=0.8, colsample_bytree=0.8, random_state=MODEL_RANDOM_STATE, verbose=-1)),
            ("gbr", GradientBoostingRegressor(n_estimators=500, max_depth=4, learning_rate=0.05, min_samples_leaf=10, random_state=MODEL_RANDOM_STATE)),
        ]),
        ("Vote-LGB+RF+Ridge", [
            ("lgb", lgb.LGBMRegressor(n_estimators=500, max_depth=5, learning_rate=0.03, num_leaves=20, min_child_samples=8, subsample=0.8, colsample_bytree=0.8, random_state=MODEL_RANDOM_STATE, verbose=-1)),
            ("rf", RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
            ("ridge", Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])),
        ]),
        ("Vote-LGB+ET+GBR", [
            ("lgb", lgb.LGBMRegressor(n_estimators=800, max_depth=5, learning_rate=0.03, num_leaves=20, min_child_samples=8, subsample=0.8, colsample_bytree=0.8, random_state=MODEL_RANDOM_STATE, verbose=-1)),
            ("et", ExtraTreesRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
            ("gbr", GradientBoostingRegressor(n_estimators=500, max_depth=4, learning_rate=0.05, min_samples_leaf=10, random_state=MODEL_RANDOM_STATE)),
        ]),
        ("Vote-3xLGB-diverse", [
            ("lgb1", lgb.LGBMRegressor(n_estimators=500, max_depth=4, learning_rate=0.05, num_leaves=12, min_child_samples=15, subsample=0.7, colsample_bytree=0.7, reg_alpha=1.0, reg_lambda=1.0, random_state=42, verbose=-1)),
            ("lgb2", lgb.LGBMRegressor(n_estimators=800, max_depth=6, learning_rate=0.03, num_leaves=31, min_child_samples=8, subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1, random_state=123, verbose=-1)),
            ("lgb3", lgb.LGBMRegressor(n_estimators=300, max_depth=3, learning_rate=0.1, num_leaves=7, min_child_samples=20, subsample=0.9, colsample_bytree=0.9, reg_alpha=0.5, reg_lambda=0.5, random_state=456, verbose=-1)),
        ]),
    ]

    for name, estimators in ens_configs:
        model = VotingRegressor(estimators=estimators)
        res = cross_validate(model, X, y, groups, weights, use_weights_in_fit=False)
        print(f"  {name:40s} MAE={res['mae']:.3f}+-{res['mae_std']:.3f}")
        results.append((name, res))

    # Stacking
    print("\n--- Stacking Ensembles ---")

    stack_configs = [
        ("Stack-LGB+RF->Ridge", {
            "estimators": [
                ("lgb", lgb.LGBMRegressor(n_estimators=500, max_depth=5, learning_rate=0.03, num_leaves=20, min_child_samples=8, random_state=MODEL_RANDOM_STATE, verbose=-1)),
                ("rf", RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
            ],
            "final_estimator": Ridge(alpha=1.0),
        }),
        ("Stack-3model->Ridge", {
            "estimators": [
                ("lgb", lgb.LGBMRegressor(n_estimators=500, max_depth=5, learning_rate=0.03, num_leaves=20, min_child_samples=8, random_state=MODEL_RANDOM_STATE, verbose=-1)),
                ("rf", RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=MODEL_RANDOM_STATE, n_jobs=-1)),
                ("gbr", GradientBoostingRegressor(n_estimators=500, max_depth=4, learning_rate=0.05, min_samples_leaf=10, random_state=MODEL_RANDOM_STATE)),
            ],
            "final_estimator": Ridge(alpha=1.0),
        }),
    ]

    for name, cfg in stack_configs:
        model = StackingRegressor(
            estimators=cfg["estimators"],
            final_estimator=cfg["final_estimator"],
            cv=3,
        )
        res = cross_validate(model, X, y, groups, weights, use_weights_in_fit=False)
        print(f"  {name:40s} MAE={res['mae']:.3f}+-{res['mae_std']:.3f}")
        results.append((name, res))

    return results


if __name__ == "__main__":
    run_experiments()
