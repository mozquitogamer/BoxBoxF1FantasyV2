"""
Script 05 — Train Models (XGBoost + Walk-Forward Evaluation)

Trains four models using the combined Jolpica priors + FP telemetry feature set:

  1. Qualifying model  — XGBoost with rank:pairwise (LambdaMART)
     Ranks drivers within each race using all Jolpica priors, track, ratings, FP features.

  2. Race model        — XGBoost with rank:pairwise (LambdaMART)
     Ranks drivers within each race using quali features + quali_position + race form.

  3. FP signal model   — ExtraTrees (pace subset, confidence scoring)
     Trains only on rows with FP telemetry data.

  4. Sprint model      — XGBoost with rank:pairwise (LambdaMART)
     Dedicated model trained on sprint race data only (~500 rows).
     Lighter regularization, uses race features + quali_position.

Ranking models learn to ORDER drivers correctly within each race, rather than
predicting exact position numbers. This better handles the nonlinear nature of
positions (P1 vs P2 gap matters more than P15 vs P16 for fantasy scoring).

The models output relevance scores (not positions) — higher = better predicted
finish. These are converted to positions by ranking within each race group.

Validation: Temporal walk-forward (train [2020..N] -> test N+1).
XGBoost handles NaN natively via tree_method="hist" — no imputation needed.

Input:
    models/training_data/all_training_data.parquet

Output:
    models/trained/quali_model.json
    models/trained/race_model.json
    models/trained/sprint_model.json
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
from scipy.stats import kendalltau
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

# Weather features per session (Level 3). Each model gets ONLY its session's
# weather features; the others are excluded from the auto-derived list below.
# See pipeline/04_build_model_inputs.py::merge_session_weather for column origins.
WEATHER_QUALI_FEATURES = [
    "weather_was_wet_quali",
    "weather_precip_minutes_quali",
    "weather_track_temp_quali",
    "weather_air_temp_quali",
    "weather_humidity_quali",
]
WEATHER_RACE_FEATURES = [
    "weather_was_wet_race",
    "weather_track_temp_race",
    "weather_air_temp_race",
    "weather_humidity_race",
    "weather_precip_minutes_race",
]
WEATHER_SPRINT_FEATURES = [
    "weather_was_wet_sprint",
    "weather_precip_minutes_sprint",
    "weather_track_temp_sprint",
    "weather_air_temp_sprint",
    "weather_humidity_sprint",
]
# Wet-row sample weight multiplier — addresses the ~85/15 dry/wet imbalance.
# Calibrated via pipeline/validate_weather_features.py: 6x gives statistically
# significant wet improvement (+0.185 MAE, CI [+0.084, +0.290]) without dry
# regression. See Phase C gate report in docs/WEATHER_LEVEL3_IMPLEMENTATION_PLAN.md.
WET_TRAINING_WEIGHT_MULTIPLIER = 6.0

# Columns to EXCLUDE from qualifying features
QUALI_EXCLUDE = {
    # Identifiers / metadata
    "season", "round", "driver_id", "constructor_id",
    # Targets
    "finish_position", "points", "laps_completed", "status",
    # DNF / classification flags
    "is_classified", "is_dnf", "is_dns", "is_dsq",
    "dnf_mechanical", "dnf_collision", "dnf_driver_error",
    # Sprint: sprint_position/sprint_points come from the Saturday sprint RACE
    # (after the fantasy lock) -> keep excluded. sprint_grid is the Sprint-Qualifying
    # result (Friday, BEFORE main quali) -> a strong, leak-free predictor of the
    # main grid on sprint weekends; NOW ADMITTED to quali/race (validated +0.31 quali
    # MAE on sprint folds, non-sprint untouched). NaN on non-sprint rounds.
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
    # Weather: race + sprint session weather is irrelevant to quali model
    # (quali model gets only its own session's weather; appended via build_quali_feature_list).
    *WEATHER_RACE_FEATURES,
    *WEATHER_SPRINT_FEATURES,
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
    # Race-session weather (Level 3)
    *WEATHER_RACE_FEATURES,
]

# FP signal features (pace-focused subset for confidence scoring)
FP_SIGNAL_FEATURES = [
    "avg_lap_time", "best_lap_time", "median_lap_time",
    "best_5_lap_avg", "p50_to_p95_avg",
    "degradation_rate", "long_run_avg", "lap_time_std",
    "pace_delta", "theoretical_best", "cv_lap_time",
    # Relative pace features (Tier 2.3 — transfer across circuits)
    "pace_delta_to_fastest", "pace_delta_to_median",
    "avg_pace_delta_to_median", "race_pace_delta_to_median",
    # Compound features (Tier 2.2)
    "soft_best_lap", "soft_avg_lap",
    "medium_long_run_avg", "hard_long_run_avg",
]


def build_quali_feature_list(all_columns: list[str]) -> list[str]:
    """Build the qualifying feature list by excluding metadata, targets, and race-specific columns.

    Quali-session weather features (WEATHER_QUALI_FEATURES) are appended explicitly
    after the auto-exclusion step — they're excluded from auto-derivation only so
    that race/sprint weather doesn't leak into the quali model.
    """
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
    # Append quali-session weather (which is NOT in QUALI_EXCLUDE but we keep
    # this explicit so the model unambiguously receives it).
    for wcol in WEATHER_QUALI_FEATURES:
        if wcol in all_columns and wcol not in features:
            features.append(wcol)
    return features


def build_race_feature_list(quali_features: list[str], all_columns: list[str]) -> list[str]:
    """Build the race feature list: all quali features + race-specific extras."""
    race_features = list(quali_features)
    for col in RACE_EXTRA_FEATURES:
        if col not in race_features and col in all_columns:
            race_features.append(col)
    # Quali-session weather is part of quali_features; strip it from race
    # features (race model gets race-session weather only via RACE_EXTRA_FEATURES).
    race_features = [c for c in race_features if c not in WEATHER_QUALI_FEATURES]
    return race_features


def apply_wet_training_boost(
    df: pd.DataFrame, wet_col: str = "weather_was_wet_race"
) -> pd.DataFrame:
    """Multiply sample_weight for wet-race training rows by WET_TRAINING_WEIGHT_MULTIPLIER.

    Compensates for the ~85/15 dry/wet imbalance in historical data. Without this,
    XGBoost can ignore weather features because the dry signal dominates. Validated
    via pipeline/validate_weather_features.py at 6x (the current default).

    Returns a COPY of df with the modified sample_weight column. The original
    df is not mutated. If wet_col is missing from df, returns df unchanged.

    Use the same column (default weather_was_wet_race) for ALL model training
    blocks (quali, race, sprint) — the "wetness of the weekend" is a single fact
    per (season, round), and using the race-session label as the canonical signal
    keeps the boost stable across models.
    """
    if wet_col not in df.columns or "sample_weight" not in df.columns:
        return df
    boosted = df.copy()
    is_wet = (boosted[wet_col].fillna(0.0) > 0.5).astype(float)
    boost = 1.0 + (WET_TRAINING_WEIGHT_MULTIPLIER - 1.0) * is_wet
    boosted["sample_weight"] = boosted["sample_weight"] * boost
    n_wet = int(is_wet.sum())
    if n_wet > 0:
        print(f"    Applied {WET_TRAINING_WEIGHT_MULTIPLIER}x weight to "
              f"{n_wet:,} wet-race training rows")
    return boosted


# ============================================================
# Ranking Utilities
# ============================================================

def sort_by_race_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Sort dataframe by (season, round) so race groups are contiguous. Required by XGBRanker."""
    return df.sort_values(["season", "round"]).reset_index(drop=True)


def make_race_qids(df: pd.DataFrame) -> np.ndarray:
    """
    Create per-sample query IDs for XGBoost ranking.
    Each race (season, round) gets a unique integer ID.
    Data MUST be sorted by (season, round) first.
    Returns array of qids, one per sample, non-decreasing.
    """
    qids = np.zeros(len(df), dtype=np.int32)
    current_id = 0
    prev_key = None
    for i, (_, row) in enumerate(df[["season", "round"]].iterrows()):
        key = (int(row["season"]), int(row["round"]))
        if key != prev_key:
            if prev_key is not None:
                current_id += 1
            prev_key = key
        qids[i] = current_id
    return qids


def position_to_relevance(positions: pd.Series, max_pos: int = 22) -> pd.Series:
    """
    Convert positions to relevance labels for ranking.
    P1 gets highest relevance (21), P22 gets 0.
    This tells the ranker that P1 > P2 > ... > P22.
    """
    return (max_pos - positions).clip(lower=0)


def scores_to_positions(scores: np.ndarray, df: pd.DataFrame) -> np.ndarray:
    """
    Convert ranking model scores to predicted positions within each race group.
    Higher score = better predicted finish = lower position number.
    """
    result = np.zeros_like(scores, dtype=float)
    for (season, rnd), group in df.groupby(["season", "round"]):
        mask = (df["season"] == season) & (df["round"] == rnd)
        idx = np.where(mask.values)[0]
        group_scores = scores[idx]
        # Rank: highest score gets position 1
        positions = (-group_scores).argsort().argsort() + 1
        result[idx] = positions.astype(float)
    return result


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
    use_ranking: bool = False,
) -> list[dict]:
    """
    Walk-forward validation: train on [2020..N], test on N+1.

    If use_ranking=True, trains with rank:pairwise objective and evaluates
    using position MAE (by converting scores back to positions per race)
    plus Kendall's tau ranking correlation.
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

        # Sort by race groups for ranking models
        if use_ranking:
            train_df = sort_by_race_groups(train_df)
            test_df = sort_by_race_groups(test_df)

        X_train = train_df[available_features].copy()
        y_train = train_df[target_col]
        X_test = test_df[available_features].copy()
        y_test = test_df[target_col]

        w_train = None
        if use_weights and "sample_weight" in train_df.columns:
            w_train = train_df["sample_weight"].values

        model = model_factory()

        if use_ranking:
            # Convert positions to relevance labels
            y_train_rel = position_to_relevance(y_train)
            train_groups = make_race_qids(train_df)

            # XGBRanker needs per-group weights, not per-sample
            if w_train is not None:
                # Take first weight from each group (all samples in a group share same season weight)
                group_weights = []
                prev_qid = -1
                for i, qid in enumerate(train_groups):
                    if qid != prev_qid:
                        group_weights.append(w_train[i])
                        prev_qid = qid
                w_groups = np.array(group_weights)
            else:
                w_groups = None

            model.fit(
                X_train, y_train_rel,
                sample_weight=w_groups,
                qid=train_groups,
            )

            # Predict scores and convert to positions
            test_scores = model.predict(X_test)
            y_pred_pos = scores_to_positions(test_scores, test_df)
        else:
            if w_train is not None:
                model.fit(X_train, y_train, sample_weight=w_train)
            else:
                model.fit(X_train, y_train)
            y_pred_pos = model.predict(X_test)

        mae = mean_absolute_error(y_test, y_pred_pos)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred_pos))

        # Ranking metrics: Kendall's tau per race, then average
        taus = []
        top3_correct = 0
        top3_total = 0
        for (season, rnd), group in test_df.groupby(["season", "round"]):
            mask = (test_df["season"] == season) & (test_df["round"] == rnd)
            idx = np.where(mask.values)[0]
            actual = y_test.values[idx]
            predicted = y_pred_pos[idx]
            if len(actual) >= 3:
                tau, _ = kendalltau(actual, predicted)
                if not np.isnan(tau):
                    taus.append(tau)
                # Top-3 accuracy: how many of actual top-3 are in predicted top-3
                actual_top3 = set(np.argsort(actual)[:3])
                pred_top3 = set(np.argsort(predicted)[:3])
                top3_correct += len(actual_top3 & pred_top3)
                top3_total += 3

        avg_tau = np.mean(taus) if taus else 0.0
        top3_acc = top3_correct / top3_total if top3_total > 0 else 0.0

        results.append({
            "test_year": int(test_year),
            "train_size": len(train_df),
            "test_size": len(test_df),
            "mae": round(float(mae), 4),
            "rmse": round(float(rmse), 4),
            "kendall_tau": round(float(avg_tau), 4),
            "top3_accuracy": round(float(top3_acc), 4),
        })
        print(f"    Fold: Train [2020-{int(test_year)-1}] ({len(train_df):,}) -> "
              f"Test {int(test_year)} ({len(test_df):,}): "
              f"MAE={mae:.3f}, RMSE={rmse:.3f}, tau={avg_tau:.3f}, Top3={top3_acc:.1%}")

    if results:
        avg_mae = np.mean([r["mae"] for r in results])
        avg_rmse = np.mean([r["rmse"] for r in results])
        avg_tau = np.mean([r["kendall_tau"] for r in results])
        avg_top3 = np.mean([r["top3_accuracy"] for r in results])
        print(f"    Mean walk-forward: MAE={avg_mae:.3f}, RMSE={avg_rmse:.3f}, "
              f"tau={avg_tau:.3f}, Top3={avg_top3:.1%}")

    return results


def _evaluate_race_model_under_post_fp(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    model_factory,
) -> list[dict]:
    """
    Evaluate the CURRENT race model training recipe (actual-quali training)
    under the post-FP scenario: trained on actual quali, tested on walk-forward
    predicted quali.

    For each test season N:
      - Train on train_df[season < N] using ACTUAL quali_position (as currently)
      - Test on test_df[season == N] which has predicted_quali already swapped in
      - Compute MAE, Kendall tau, Top-3 accuracy

    This isolates the distribution-shift penalty of the current model recipe
    without changing training data.
    """
    available = [c for c in feature_cols if c in train_df.columns and c in test_df.columns]
    test_years = [y for y in sorted(test_df["season"].unique()) if y >= 2022]
    results = []

    for test_year in test_years:
        tr_mask = train_df["season"] < test_year
        te_mask = test_df["season"] == test_year

        tr = train_df[tr_mask & train_df[target_col].notna()].copy()
        te = test_df[te_mask & test_df[target_col].notna()].copy()

        if len(tr) < 50 or len(te) < 10:
            continue

        tr = sort_by_race_groups(tr)
        te = sort_by_race_groups(te)

        X_tr = tr[available].copy()
        y_tr_rel = position_to_relevance(tr[target_col])
        X_te = te[available].copy()
        y_te = te[target_col]
        tr_qids = make_race_qids(tr)

        if "sample_weight" in tr.columns:
            w_tr = tr["sample_weight"].values
            group_weights = []
            prev_qid = -1
            for i, qid in enumerate(tr_qids):
                if qid != prev_qid:
                    group_weights.append(w_tr[i])
                    prev_qid = qid
            w_groups = np.array(group_weights)
        else:
            w_groups = None

        model = model_factory()
        model.fit(X_tr, y_tr_rel, sample_weight=w_groups, qid=tr_qids)
        scores = model.predict(X_te)
        y_pred_pos = scores_to_positions(scores, te)

        mae = mean_absolute_error(y_te, y_pred_pos)
        rmse = np.sqrt(mean_squared_error(y_te, y_pred_pos))

        taus = []
        top3_correct = 0
        top3_total = 0
        for (season, rnd), _ in te.groupby(["season", "round"]):
            mask = (te["season"] == season) & (te["round"] == rnd)
            idx = np.where(mask.values)[0]
            actual = y_te.values[idx]
            predicted = y_pred_pos[idx]
            if len(actual) >= 3:
                tau, _ = kendalltau(actual, predicted)
                if not np.isnan(tau):
                    taus.append(tau)
                actual_top3 = set(np.argsort(actual)[:3])
                pred_top3 = set(np.argsort(predicted)[:3])
                top3_correct += len(actual_top3 & pred_top3)
                top3_total += 3

        avg_tau = float(np.mean(taus)) if taus else 0.0
        top3_acc = top3_correct / top3_total if top3_total > 0 else 0.0

        results.append({
            "test_year": int(test_year),
            "train_size": len(tr),
            "test_size": len(te),
            "mae": round(float(mae), 4),
            "rmse": round(float(rmse), 4),
            "kendall_tau": round(float(avg_tau), 4),
            "top3_accuracy": round(float(top3_acc), 4),
        })
        print(f"    Fold: Train [<{int(test_year)}] ({len(tr):,}) -> "
              f"Test {int(test_year)} ({len(te):,}): "
              f"MAE={mae:.3f}, tau={avg_tau:.3f}, Top3={top3_acc:.1%}")

    return results


def generate_walk_forward_quali_predictions(
    df: pd.DataFrame,
    quali_features: list[str],
    model_factory,
) -> pd.Series:
    """
    Generate predicted qualifying positions for training data via walk-forward.

    Rationale
    ---------
    The race model is trained with `quali_position` as a feature. At training
    time this is the ACTUAL qualifying result. At inference time during the
    post-FP phase (before qualifying happens), the race model instead receives
    the PREDICTED qualifying position from the quali model, which has error
    (MAE ~1.5 positions). This creates a train/inference distribution shift:
    the race model learns to over-trust `quali_position`, then at inference it
    is given a noisy version of it.

    To remove the shift, we generate predicted quali positions for all training
    rows via walk-forward: for each test season N (starting from the second),
    train a quali model on seasons < N and predict season N's qualifying.
    The first season falls back to actual quali (not enough prior data).

    Returns a Series aligned to df.index with predicted quali positions (NaN
    where the quali target itself is NaN).
    """
    available_features = [c for c in quali_features if c in df.columns]
    result = pd.Series(np.nan, index=df.index, dtype=float)

    seasons = sorted(df["season"].unique())
    if len(seasons) < 2:
        # Single-season dataset -- fall back to actual quali
        mask = df["quali_position"].notna()
        result.loc[mask] = df.loc[mask, "quali_position"].astype(float)
        return result

    # First season: fall back to actual (no earlier data to train on)
    first_mask = (df["season"] == seasons[0]) & df["quali_position"].notna()
    result.loc[first_mask] = df.loc[first_mask, "quali_position"].astype(float)

    for test_year in seasons[1:]:
        train_mask = (df["season"] < test_year) & df["quali_position"].notna()
        test_mask_full = (df["season"] == test_year) & df["quali_position"].notna()

        train_df = df[train_mask].copy()
        test_df = df[test_mask_full].copy()

        if len(train_df) < 50 or len(test_df) < 5:
            # Not enough data -- fall back to actual quali for this season
            result.loc[test_mask_full] = df.loc[test_mask_full, "quali_position"].astype(float)
            continue

        # Preserve original indices before sorting (sort_by_race_groups uses
        # reset_index(drop=True), which would otherwise discard them).
        # We stash the original indices as a column, then read them back after
        # prediction to assign results to the right rows.
        train_df = train_df.copy()
        test_df = test_df.copy()
        train_df["_orig_index"] = train_df.index
        test_df["_orig_index"] = test_df.index

        # Sort for XGBRanker: groups must be contiguous
        train_df = sort_by_race_groups(train_df)
        test_df = sort_by_race_groups(test_df)

        X_train = train_df[available_features].copy()
        y_train_rel = position_to_relevance(train_df["quali_position"])
        X_test = test_df[available_features].copy()

        train_qids = make_race_qids(train_df)

        # Per-group weights
        if "sample_weight" in train_df.columns:
            w_train = train_df["sample_weight"].values
            group_weights = []
            prev_qid = -1
            for i, qid in enumerate(train_qids):
                if qid != prev_qid:
                    group_weights.append(w_train[i])
                    prev_qid = qid
            w_groups = np.array(group_weights)
        else:
            w_groups = None

        model = model_factory()
        model.fit(X_train, y_train_rel, sample_weight=w_groups, qid=train_qids)

        test_scores = model.predict(X_test)
        predicted_positions = scores_to_positions(test_scores, test_df)

        # Map back to original df indices via the stashed column
        for orig_idx, pos in zip(test_df["_orig_index"].values, predicted_positions):
            result.loc[orig_idx] = float(pos)

        # Report progress
        actual = test_df["quali_position"].values
        mae_wf = float(np.mean(np.abs(actual - predicted_positions)))
        print(f"    WF quali {test_year}: trained on {len(train_df):,} rows, "
              f"predicted {len(test_df):,} rows, MAE={mae_wf:.3f}")

    return result


def rederive_quali_dependent_features(
    df: pd.DataFrame, quali_col: str = "quali_position"
) -> pd.DataFrame:
    """
    Recompute quali-dependent features from `quali_col`.

    Formulas MUST match 03b_build_jolpica_features.py::add_race_model_features
    to avoid train/inference distribution shift. This function is called after
    overwriting `quali_position` with walk-forward predictions during training,
    and also at inference when the race model gets predicted quali instead of
    actual quali.
    """
    d = df.copy()
    qp = d[quali_col].astype(float)
    d["is_pole_position"] = (qp == 1).astype(int)
    d["is_front_row"] = (qp <= 2).astype(int)
    d["is_top10_quali"] = (qp <= 10).astype(int)
    d["grid_advantage"] = 11.0 - qp  # must match 03b
    return d


# ============================================================
# Main
# ============================================================

def train_and_save_catboost_race(X, y_relevance, group_qids, out_path, label):
    """Train a CatBoost YetiRank ranker for a race model and save it (.cbm).

    Mirrors the EXACT config validated in validate_alt_algo_v2.py / the race_fp
    back-test (YetiRank, 650 iters, lr 0.03, depth 6) AND that protocol's choice
    of no per-group sample weights — so what ships equals what was back-tested.
    Saved alongside the XGBoost .json so 06 selects via settings.RACE_MODEL_ALGORITHM
    and reverting is one line. CatBoost handles NaN natively; passing a DataFrame
    preserves feature names so inference aligns by column, not position. Rows must
    already be sorted into contiguous race groups (callers sort before this).
    """
    from catboost import CatBoost, Pool
    pool = Pool(data=X, label=np.asarray(y_relevance, dtype=float), group_id=group_qids)
    model = CatBoost(dict(
        loss_function="YetiRank", iterations=650, learning_rate=0.03, depth=6,
        random_seed=MODEL_RANDOM_STATE, verbose=False, allow_writing_files=False,
    ))
    model.fit(pool)
    model.save_model(str(out_path))
    print(f"  Saved -> models/trained/{out_path.name} (CatBoost YetiRank, {label})")
    return model


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
        return xgb.XGBRanker(
            n_estimators=1200,
            learning_rate=0.025,  # REVERTED 2026-05-27. Initially lowered to
                                  # 0.015 based on 5-fold 2026 CV, but the
                                  # subsequent 97-fold (2022-2026) re-validation
                                  # showed the improvement (-0.038 MAE) was
                                  # NOT statistically significant — 95% CI
                                  # [-0.077, +0.002] includes zero. The 5-fold
                                  # finding was a small-sample artifact.
            max_depth=3,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            reg_alpha=0.1,
            reg_lambda=1.0,
            tree_method="hist",
            objective="rank:pairwise",
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    print("\n  Walk-forward validation:")
    quali_wf_results = walk_forward_validate(
        quali_df, quali_feature_cols, "quali_position", make_quali_model, "Qualifying",
        use_ranking=True,
    )

    # Train final qualifying model on all data
    print("\n  Training final qualifying model on all data...")
    quali_df = apply_wet_training_boost(quali_df)
    quali_df = sort_by_race_groups(quali_df)
    X_q = quali_df[quali_available]
    y_q_rel = position_to_relevance(quali_df["quali_position"])
    w_q = quali_df["sample_weight"].values if "sample_weight" in quali_df.columns else None
    q_groups = make_race_qids(quali_df)

    # Per-group weights for ranking
    if w_q is not None:
        q_group_weights = []
        prev_qid = -1
        for i, qid in enumerate(q_groups):
            if qid != prev_qid:
                q_group_weights.append(w_q[i])
                prev_qid = qid
        w_q_groups = np.array(q_group_weights)
    else:
        w_q_groups = None

    quali_model = make_quali_model()
    quali_model.fit(X_q, y_q_rel, sample_weight=w_q_groups, qid=q_groups)

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
    # Walk-forward predicted quali (for race_model_fp training)
    # ==================================================================
    # Generate walk-forward predicted qualifying positions for all training
    # rows. These are the quali predictions the race model would have received
    # at inference during the post-FP phase for each historical race.
    #
    # We use these to train a `race_model_fp.json` variant that has seen the
    # same noise distribution in training as it will see at inference --
    # eliminating the quali -> race distribution shift.
    print(f"\n{'=' * 60}")
    print("Walk-Forward Predicted Quali (for race_model_fp)")
    print(f"{'=' * 60}")
    print(f"  Generating walk-forward quali predictions for training data...")
    wf_quali = generate_walk_forward_quali_predictions(
        df, quali_feature_cols, make_quali_model
    )
    df["predicted_quali_wf"] = wf_quali

    # Stats
    wf_n = int(wf_quali.notna().sum())
    actual_n = int(df["quali_position"].notna().sum())
    print(f"  Walk-forward quali generated for {wf_n}/{actual_n} rows")
    diff = (wf_quali - df["quali_position"]).abs()
    if diff.notna().any():
        wf_quali_mae = float(diff.mean())
        print(f"  Walk-forward quali MAE vs actual: {wf_quali_mae:.3f} positions")

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
        return xgb.XGBRanker(
            n_estimators=650,
            learning_rate=0.03,
            max_depth=5,  # REVERTED 2026-05-27. Briefly set to 2 based on
                          # 5-fold 2026 CV (showed -0.390 race MAE improvement).
                          # The subsequent 97-fold (2022-2026) re-validation
                          # exposed the headline as misleading: real
                          # improvement was only -0.087 MAE (95% CI [-0.175,
                          # -0.006], barely significant). The "8% gain" was
                          # driven by ONE anomalous 2026 fold (R7 Canada,
                          # baseline MAE=7.36). Year-stratified results showed
                          # 2023 actually regressed (+0.023). Reverting to the
                          # robust historical depth until a tuning is found
                          # that improves uniformly across all 4+ training
                          # years on the 97-fold framework. See
                          # data/experiments/compare_baseline_multiyear_vs_winner_multiyear.json
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=5,
            tree_method="hist",
            objective="rank:pairwise",
            random_state=MODEL_RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    print("\n  Walk-forward validation:")
    race_wf_results = walk_forward_validate(
        race_df, race_feature_cols, "finish_position", make_race_model, "Race",
        use_ranking=True,
    )

    # Train final race model on all data
    print("\n  Training final race model on all data...")
    race_df = apply_wet_training_boost(race_df)
    race_df = sort_by_race_groups(race_df)
    X_r = race_df[race_available]
    y_r_rel = position_to_relevance(race_df["finish_position"])
    w_r = race_df["sample_weight"].values if "sample_weight" in race_df.columns else None
    r_groups = make_race_qids(race_df)

    # Per-group weights for ranking
    if w_r is not None:
        r_group_weights = []
        prev_qid = -1
        for i, qid in enumerate(r_groups):
            if qid != prev_qid:
                r_group_weights.append(w_r[i])
                prev_qid = qid
        w_r_groups = np.array(r_group_weights)
    else:
        w_r_groups = None

    race_model = make_race_model()
    race_model.fit(X_r, y_r_rel, sample_weight=w_r_groups, qid=r_groups)

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

    # ALSO train + save a CatBoost YetiRank race model (06 picks which to use via
    # settings.RACE_MODEL_ALGORITHM). Same data/relevance/groups; no per-group
    # weights to match the back-tested config.
    train_and_save_catboost_race(
        X_r, y_r_rel, r_groups, TRAINED_DIR / "race_model.cbm", "race"
    )

    # ==================================================================
    # MODEL 2B: Race Position (FP-phase) — XGBoost trained on WF quali
    # ==================================================================
    # The post-FP race model: trained with walk-forward predicted quali as the
    # `quali_position` feature (and quali-derived features re-derived from it).
    # This removes the train/inference distribution shift that happens when the
    # post-FP race model is fed a noisy predicted-quali at inference but was
    # trained on clean actual-quali.
    print(f"\n{'=' * 60}")
    print("MODEL 2B: Race Position (FP-phase) — WF predicted quali")
    print(f"{'=' * 60}")

    race_fp_model = None
    race_fp_wf_results = []
    race_fp_train_size = 0
    r_fp_importances = pd.Series(dtype=float)
    race_fp_post_fp_delta = None  # MAE improvement vs race_model under post-FP

    if "predicted_quali_wf" not in df.columns:
        print("  ERROR: predicted_quali_wf not found; skipping race_model_fp")
    else:
        # Start from same row filter as race_df, BUT also require WF quali
        race_fp_df = df[race_filter & df["predicted_quali_wf"].notna()].copy()
        # Swap in WF quali for quali_position and re-derive dependents
        race_fp_df["quali_position"] = race_fp_df["predicted_quali_wf"].astype(float)
        race_fp_df = rederive_quali_dependent_features(race_fp_df, "quali_position")

        print(f"  Features: {len(race_available)}")
        print(f"  Training samples: {len(race_fp_df):,} (WF quali available)")

        # Walk-forward validation with WF quali at TEST time too
        # (this simulates the real post-FP inference condition)
        print("\n  Walk-forward validation (post-FP scenario):")
        race_fp_wf_results = walk_forward_validate(
            race_fp_df, race_feature_cols, "finish_position", make_race_model, "Race-FP",
            use_ranking=True,
        )

        # ALSO run the current race_model through the post-FP scenario for
        # apples-to-apples comparison. We take race_df (trained on ACTUAL quali)
        # but feed it WF predicted quali at test time -- exactly what happens
        # in production at post-FP.
        print("\n  Walk-forward validation (current race_model under post-FP):")
        # Build test set with WF quali for existing race_df rows
        race_posfp_eval_df = race_df.copy()
        # Match rows that have WF quali
        wf_index_set = set(race_fp_df.index)
        race_posfp_eval_df = race_posfp_eval_df[
            race_posfp_eval_df.index.isin(wf_index_set)
        ].copy()
        race_posfp_eval_df["quali_position"] = df.loc[
            race_posfp_eval_df.index, "predicted_quali_wf"
        ].astype(float)
        race_posfp_eval_df = rederive_quali_dependent_features(
            race_posfp_eval_df, "quali_position"
        )
        # Use the EXISTING race_model factory (trained on actual quali),
        # but test it on predicted quali. Walk-forward gives us the comparison.
        # For proper comparison, we evaluate both:
        #   (a) race_model.json trained on actual quali -> tested on predicted
        #   (b) race_model_fp.json trained on predicted -> tested on predicted
        # The training data for (a) MUST still use actual quali.
        #
        # We achieve this with a custom fold loop (not walk_forward_validate,
        # which uses the same df for train and test).
        current_race_posfp_results = _evaluate_race_model_under_post_fp(
            train_df=race_df,
            test_df=race_posfp_eval_df,
            feature_cols=race_feature_cols,
            target_col="finish_position",
            model_factory=make_race_model,
        )

        # Summaries for comparison
        if race_fp_wf_results and current_race_posfp_results:
            fp_mae = float(np.mean([r["mae"] for r in race_fp_wf_results]))
            fp_tau = float(np.mean([r["kendall_tau"] for r in race_fp_wf_results]))
            fp_top3 = float(np.mean([r["top3_accuracy"] for r in race_fp_wf_results]))
            cur_mae = float(np.mean([r["mae"] for r in current_race_posfp_results]))
            cur_tau = float(np.mean([r["kendall_tau"] for r in current_race_posfp_results]))
            cur_top3 = float(np.mean([r["top3_accuracy"] for r in current_race_posfp_results]))
            race_fp_post_fp_delta = round(cur_mae - fp_mae, 4)
            print(f"\n  === Post-FP scenario comparison ===")
            print(f"  Current race_model (train=actual, test=predicted):")
            print(f"    MAE={cur_mae:.3f}  tau={cur_tau:.3f}  Top3={cur_top3:.1%}")
            print(f"  New race_model_fp (train=predicted, test=predicted):")
            print(f"    MAE={fp_mae:.3f}  tau={fp_tau:.3f}  Top3={fp_top3:.1%}")
            improvement = cur_mae - fp_mae
            if improvement > 0:
                print(f"  IMPROVEMENT: MAE reduced by {improvement:.3f} positions "
                      f"({improvement/cur_mae:.1%})")
            else:
                print(f"  REGRESSION: MAE worse by {-improvement:.3f} positions")

        # Train final race_fp_model on all data with WF quali
        print("\n  Training final race_model_fp on all WF-quali data...")
        race_fp_df = apply_wet_training_boost(race_fp_df)
        race_fp_df = sort_by_race_groups(race_fp_df)
        # Ensure all needed columns are available and aligned
        X_r_fp = race_fp_df[race_available].copy()
        y_r_fp = position_to_relevance(race_fp_df["finish_position"])
        w_r_fp = race_fp_df["sample_weight"].values if "sample_weight" in race_fp_df.columns else None
        r_fp_groups = make_race_qids(race_fp_df)

        if w_r_fp is not None:
            r_fp_group_weights = []
            prev_qid = -1
            for i, qid in enumerate(r_fp_groups):
                if qid != prev_qid:
                    r_fp_group_weights.append(w_r_fp[i])
                    prev_qid = qid
            w_r_fp_groups = np.array(r_fp_group_weights)
        else:
            w_r_fp_groups = None

        race_fp_model = make_race_model()
        race_fp_model.fit(X_r_fp, y_r_fp, sample_weight=w_r_fp_groups, qid=r_fp_groups)
        race_fp_train_size = len(y_r_fp)

        # Feature importances
        r_fp_importances = pd.Series(
            race_fp_model.feature_importances_, index=race_available
        ).sort_values(ascending=False)
        print(f"\n  Top 15 race_fp features:")
        for feat, imp in r_fp_importances.head(15).items():
            print(f"    {feat}: {imp:.4f}")

        # Save
        race_fp_model.save_model(str(TRAINED_DIR / "race_model_fp.json"))
        print(f"  Saved -> models/trained/race_model_fp.json")

        # ALSO train + save a CatBoost YetiRank race_fp model (see flag note above).
        train_and_save_catboost_race(
            X_r_fp, y_r_fp, r_fp_groups, TRAINED_DIR / "race_model_fp.cbm", "race_fp"
        )

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
    # MODEL 4: Sprint Position — XGBoost (dedicated sprint model)
    # ==================================================================
    print(f"\n{'=' * 60}")
    print("MODEL 4: Sprint Position — XGBoost (dedicated)")
    print(f"{'=' * 60}")

    # Sprint data: only rows from sprint weekends with valid sprint_position
    sprint_filter = df["sprint_position"].notna()
    sprint_df = df[sprint_filter].copy()
    print(f"  Sprint rows available: {len(sprint_df):,}")
    print(f"  Sprint seasons: {sorted(sprint_df['season'].unique())}")

    # === Sprint grid features ===
    # Sprint grid (from sprint qualifying/shootout) is the #1 feature for sprint predictions,
    # just like quali_position is the #1 feature for race predictions.
    # At prediction time, we have ACTUAL sprint qualifying results (deadline = sprint race start).
    if "sprint_grid" in sprint_df.columns:
        sg = sprint_df["sprint_grid"]
        sprint_df["sprint_is_front_row"] = (sg <= 2).astype(int)
        sprint_df["sprint_is_top3"] = (sg <= 3).astype(int)
        sprint_df["sprint_is_top10"] = (sg <= 10).astype(int)
        sprint_df["sprint_grid_advantage"] = 1.0 / (sg + 0.5)
        # Delta between regular qualifying position and sprint qualifying position
        if "quali_position" in sprint_df.columns:
            sprint_df["quali_to_sprint_grid_delta"] = sprint_df["quali_position"] - sg
        print(f"  Sprint grid feature coverage: {sg.notna().sum()}/{len(sprint_df)} rows")
    else:
        print(f"  WARNING: sprint_grid not available — sprint model will lack key feature")

    # Sprint model uses race features PLUS sprint-grid-derived features.
    # Sprint-session weather replaces race-session weather (the sprint runs
    # on Saturday — its conditions can differ from Sunday's race).
    SPRINT_EXTRA_FEATURES = [
        "sprint_grid", "sprint_is_front_row", "sprint_is_top3",
        "sprint_is_top10", "sprint_grid_advantage", "quali_to_sprint_grid_delta",
        *WEATHER_SPRINT_FEATURES,
    ]
    sprint_feature_cols = [c for c in race_feature_cols if c not in WEATHER_RACE_FEATURES]
    for sf in SPRINT_EXTRA_FEATURES:
        if sf in sprint_df.columns and sf not in sprint_feature_cols:
            sprint_feature_cols.append(sf)
    sprint_available = [c for c in sprint_feature_cols if c in sprint_df.columns]
    sprint_wf_results = []
    sprint_model = None
    sprint_train_size = 0

    if len(sprint_df) >= 60:  # Need enough data for meaningful model
        def make_sprint_model():
            return xgb.XGBRanker(
                n_estimators=400,       # Fewer trees — smaller dataset
                learning_rate=0.035,    # Slightly higher LR for smaller data
                max_depth=4,            # Moderate depth
                subsample=0.80,
                colsample_bytree=0.80,
                min_child_weight=5,     # Higher min child — prevent overfitting
                reg_alpha=0.2,
                reg_lambda=1.5,         # Stronger regularization for small data
                tree_method="hist",
                objective="rank:pairwise",
                random_state=MODEL_RANDOM_STATE,
                n_jobs=-1,
                verbosity=0,
            )

        # Walk-forward validation (only test years with sprint data)
        print("\n  Walk-forward validation:")
        sprint_wf_results = walk_forward_validate(
            sprint_df, sprint_feature_cols, "sprint_position", make_sprint_model, "Sprint",
            use_ranking=True,
        )

        # Train final sprint model on all sprint data
        print("\n  Training final sprint model on all sprint data...")
        # Apply wet boost using the sprint's own wet label (sprint races have their
        # own wet/dry status — Belgium 2023 sprint was wet, race was dry).
        sprint_df = apply_wet_training_boost(sprint_df, wet_col="weather_was_wet_sprint")
        sprint_df = sort_by_race_groups(sprint_df)
        X_s = sprint_df[sprint_available]
        y_s_rel = position_to_relevance(sprint_df["sprint_position"])
        w_s = sprint_df["sample_weight"].values if "sample_weight" in sprint_df.columns else None
        s_groups = make_race_qids(sprint_df)

        # Per-group weights
        if w_s is not None:
            s_group_weights = []
            prev_qid = -1
            for i, qid in enumerate(s_groups):
                if qid != prev_qid:
                    s_group_weights.append(w_s[i])
                    prev_qid = qid
            w_s_groups = np.array(s_group_weights)
        else:
            w_s_groups = None

        sprint_model = make_sprint_model()
        sprint_model.fit(X_s, y_s_rel, sample_weight=w_s_groups, qid=s_groups)
        sprint_train_size = len(y_s_rel)

        # Feature importances
        s_importances = pd.Series(
            sprint_model.feature_importances_, index=sprint_available
        ).sort_values(ascending=False)
        print(f"\n  Top 15 sprint features:")
        for feat, imp in s_importances.head(15).items():
            print(f"    {feat}: {imp:.4f}")

        # Save XGBoost model as JSON
        sprint_model.save_model(str(TRAINED_DIR / "sprint_model.json"))
        print(f"  Saved -> models/trained/sprint_model.json")
    else:
        print(f"  Not enough sprint data ({len(sprint_df)} rows) — skipping sprint model")
        print(f"  Sprint predictions will fall back to race model with adjustments")

    # ==================================================================
    # MODEL 4B: Sprint Position (FP-phase) — XGBoost trained on WF quali
    # ==================================================================
    # Parallel to MODEL 2B for the race model. The post-FP sprint model:
    # trained with walk-forward predicted quali as BOTH `quali_position` AND
    # `sprint_grid` (because at post-FP inference for a sprint weekend, sprint
    # qualifying hasn't happened yet and 06_run_predictions.py falls back to
    # predicted_quali_position as a sprint_grid proxy). Quali-dependent and
    # sprint-grid-dependent features are re-derived from these substitutions
    # so training matches inference.
    #
    # Post-sprint-quali inference (sprint_grid is actual) still uses the
    # existing sprint_model.json. A future PR could also refit sprint_model.json
    # with WF-quali for quali_position (keeping sprint_grid actual) to close
    # the remaining quali-position distribution shift in that phase.
    print(f"\n{'=' * 60}")
    print("MODEL 4B: Sprint Position (FP-phase) — WF predicted quali+grid")
    print(f"{'=' * 60}")

    sprint_fp_model = None
    sprint_fp_wf_results = []
    sprint_fp_train_size = 0
    s_fp_importances = pd.Series(dtype=float)
    sprint_fp_post_fp_delta = None

    if sprint_model is None:
        print("  Skipping sprint_model_fp (base sprint_model not trained)")
    elif "predicted_quali_wf" not in df.columns:
        print("  ERROR: predicted_quali_wf not found; skipping sprint_model_fp")
    else:
        # Start from same sprint filter, require WF quali available
        sprint_fp_df = df[sprint_filter & df["predicted_quali_wf"].notna()].copy()
        if len(sprint_fp_df) < 60:
            print(f"  Not enough sprint data with WF quali ({len(sprint_fp_df)} rows) — skipping")
        else:
            # Substitute WF-predicted quali for both quali_position and sprint_grid
            # (mirrors the post-FP inference condition exactly)
            wf_quali_vals = sprint_fp_df["predicted_quali_wf"].astype(float)
            sprint_fp_df["quali_position"] = wf_quali_vals
            sprint_fp_df["sprint_grid"] = wf_quali_vals
            # Re-derive quali-dependent features (is_pole_position etc.)
            sprint_fp_df = rederive_quali_dependent_features(sprint_fp_df, "quali_position")
            # Re-derive sprint-grid-dependent features (formulas MUST match the
            # original sprint training block above AND 06_run_predictions.py)
            sg_fp = sprint_fp_df["sprint_grid"]
            sprint_fp_df["sprint_is_front_row"] = (sg_fp <= 2).astype(int)
            sprint_fp_df["sprint_is_top3"] = (sg_fp <= 3).astype(int)
            sprint_fp_df["sprint_is_top10"] = (sg_fp <= 10).astype(int)
            sprint_fp_df["sprint_grid_advantage"] = 1.0 / (sg_fp + 0.5)
            # delta is 0 by construction (both features are the same value at post-FP)
            sprint_fp_df["quali_to_sprint_grid_delta"] = 0.0

            sprint_fp_available = [c for c in sprint_feature_cols if c in sprint_fp_df.columns]
            print(f"  Features: {len(sprint_fp_available)}")
            print(f"  Training samples: {len(sprint_fp_df):,} (WF quali available)")

            # Walk-forward validation (post-FP scenario: train/test both use WF quali)
            print("\n  Walk-forward validation (post-FP scenario):")
            sprint_fp_wf_results = walk_forward_validate(
                sprint_fp_df, sprint_feature_cols, "sprint_position", make_sprint_model,
                "Sprint-FP", use_ranking=True,
            )

            # Benchmark: current sprint_model recipe under post-FP scenario.
            # Trained on actual (sprint_grid + quali_position), tested on WF-predicted.
            # sprint_fp_df already has WF-substituted quali/sprint_grid, so we can
            # pass it directly as test_df. We pull a fresh sprint_df with ACTUAL
            # features for the train side (avoiding the mutated sprint_df in outer
            # scope whose index was reset by sort_by_race_groups).
            print("\n  Walk-forward validation (current sprint_model under post-FP):")
            sprint_train_actual = df[sprint_filter].copy()
            # Re-derive the sprint-grid features on this fresh copy (same formulas
            # as the MODEL 4 training block above).
            sg_train = sprint_train_actual["sprint_grid"]
            sprint_train_actual["sprint_is_front_row"] = (sg_train <= 2).astype(int)
            sprint_train_actual["sprint_is_top3"] = (sg_train <= 3).astype(int)
            sprint_train_actual["sprint_is_top10"] = (sg_train <= 10).astype(int)
            sprint_train_actual["sprint_grid_advantage"] = 1.0 / (sg_train + 0.5)
            if "quali_position" in sprint_train_actual.columns:
                sprint_train_actual["quali_to_sprint_grid_delta"] = (
                    sprint_train_actual["quali_position"] - sg_train
                )

            current_sprint_posfp_results = _evaluate_race_model_under_post_fp(
                train_df=sprint_train_actual,
                test_df=sprint_fp_df,
                feature_cols=sprint_feature_cols,
                target_col="sprint_position",
                model_factory=make_sprint_model,
            )

            if sprint_fp_wf_results and current_sprint_posfp_results:
                fp_mae = float(np.mean([r["mae"] for r in sprint_fp_wf_results]))
                fp_tau = float(np.mean([r["kendall_tau"] for r in sprint_fp_wf_results]))
                fp_top3 = float(np.mean([r["top3_accuracy"] for r in sprint_fp_wf_results]))
                cur_mae = float(np.mean([r["mae"] for r in current_sprint_posfp_results]))
                cur_tau = float(np.mean([r["kendall_tau"] for r in current_sprint_posfp_results]))
                cur_top3 = float(np.mean([r["top3_accuracy"] for r in current_sprint_posfp_results]))
                sprint_fp_post_fp_delta = round(cur_mae - fp_mae, 4)
                print(f"\n  === Post-FP scenario comparison (sprint) ===")
                print(f"  Current sprint_model (train=actual, test=predicted):")
                print(f"    MAE={cur_mae:.3f}  tau={cur_tau:.3f}  Top3={cur_top3:.1%}")
                print(f"  New sprint_model_fp (train=predicted, test=predicted):")
                print(f"    MAE={fp_mae:.3f}  tau={fp_tau:.3f}  Top3={fp_top3:.1%}")
                improvement = cur_mae - fp_mae
                if improvement > 0:
                    pct = improvement / cur_mae if cur_mae > 0 else 0.0
                    print(f"  IMPROVEMENT: MAE reduced by {improvement:.3f} positions "
                          f"({pct:.1%})")
                else:
                    print(f"  REGRESSION: MAE worse by {-improvement:.3f} positions")

            # Only train and save the final sprint_model_fp if the benchmark
            # shows an actual improvement over the current sprint_model in the
            # post-FP scenario. With only ~500 sprint rows total and thin
            # early folds (60 rows), the walk-forward approach can be noisier
            # than the actual-quali baseline. We'd rather fall back to the
            # current sprint_model than ship a regression.
            should_save_sprint_fp = (
                sprint_fp_post_fp_delta is not None and sprint_fp_post_fp_delta > 0
            )
            # Remove any previous file to avoid 06_run_predictions.py silently
            # picking up a stale model when we've decided not to ship one.
            stale_fp_path = TRAINED_DIR / "sprint_model_fp.json"
            if stale_fp_path.exists() and not should_save_sprint_fp:
                stale_fp_path.unlink()
                print(f"\n  No improvement over current sprint_model "
                      f"(delta={sprint_fp_post_fp_delta}). Removed stale "
                      f"sprint_model_fp.json; post-FP sprint inference will "
                      f"fall back to sprint_model.json.")

            if not should_save_sprint_fp:
                print(f"  Skipping sprint_model_fp save (benchmark did not improve).")
            else:
                print("\n  Training final sprint_model_fp on all WF-quali sprint data...")
                sprint_fp_df = apply_wet_training_boost(sprint_fp_df, wet_col="weather_was_wet_sprint")
                sprint_fp_df = sort_by_race_groups(sprint_fp_df)
                X_s_fp = sprint_fp_df[sprint_fp_available].copy()
                y_s_fp = position_to_relevance(sprint_fp_df["sprint_position"])
                w_s_fp = sprint_fp_df["sample_weight"].values if "sample_weight" in sprint_fp_df.columns else None
                s_fp_groups = make_race_qids(sprint_fp_df)

                if w_s_fp is not None:
                    s_fp_group_weights = []
                    prev_qid = -1
                    for i, qid in enumerate(s_fp_groups):
                        if qid != prev_qid:
                            s_fp_group_weights.append(w_s_fp[i])
                            prev_qid = qid
                    w_s_fp_groups = np.array(s_fp_group_weights)
                else:
                    w_s_fp_groups = None

                sprint_fp_model = make_sprint_model()
                sprint_fp_model.fit(X_s_fp, y_s_fp, sample_weight=w_s_fp_groups, qid=s_fp_groups)
                sprint_fp_train_size = len(y_s_fp)

                s_fp_importances = pd.Series(
                    sprint_fp_model.feature_importances_, index=sprint_fp_available
                ).sort_values(ascending=False)
                print(f"\n  Top 10 sprint_fp features:")
                for feat, imp in s_fp_importances.head(10).items():
                    print(f"    {feat}: {imp:.4f}")

                sprint_fp_model.save_model(str(TRAINED_DIR / "sprint_model_fp.json"))
                print(f"  Saved -> models/trained/sprint_model_fp.json")

    # ==================================================================
    # Save Feature Columns
    # ==================================================================
    feature_columns_data = {
        "quali_features": quali_available,
        "race_features": race_available,
        # race_fp shares the same feature list as race -- the only difference
        # is the training recipe (WF predicted quali vs actual quali).
        "race_fp_features": race_available if race_fp_model is not None else [],
        "fp_signal_features": fp_available,
        "sprint_features": sprint_available if sprint_model else race_available,
        # sprint_fp shares the same feature list as sprint -- the only
        # difference is the training recipe (WF predicted quali as both
        # quali_position AND sprint_grid).
        "sprint_fp_features": sprint_available if sprint_fp_model is not None else [],
    }
    with open(TRAINED_DIR / "feature_columns.json", "w") as f:
        json.dump(feature_columns_data, f, indent=2)
    print(f"\n  Saved -> models/trained/feature_columns.json")

    # ==================================================================
    # Save Model Metadata
    # ==================================================================
    quali_avg_mae = float(np.mean([r["mae"] for r in quali_wf_results])) if quali_wf_results else None
    quali_avg_tau = float(np.mean([r["kendall_tau"] for r in quali_wf_results])) if quali_wf_results else None
    quali_avg_top3 = float(np.mean([r["top3_accuracy"] for r in quali_wf_results])) if quali_wf_results else None
    race_avg_mae = float(np.mean([r["mae"] for r in race_wf_results])) if race_wf_results else None
    race_avg_tau = float(np.mean([r["kendall_tau"] for r in race_wf_results])) if race_wf_results else None
    race_avg_top3 = float(np.mean([r["top3_accuracy"] for r in race_wf_results])) if race_wf_results else None

    metadata = {
        "trained_at": datetime.now().isoformat(),
        "current_season": CURRENT_SEASON,
        "training_data": str(training_path),
        "total_rows": len(df),
        "seasons": sorted([int(s) for s in df["season"].unique()]),
        "fp_coverage": f"{fp_rows}/{len(df)} ({fp_rows/len(df):.1%})",
        "qualifying_model": {
            "algorithm": "XGBRanker (rank:pairwise)",
            "save_format": "json",
            "n_features": len(quali_available),
            "training_samples": len(y_q_rel),
            "params": {
                "n_estimators": 1200,
                "learning_rate": 0.025,
                "max_depth": 3,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
                "min_child_weight": 3,
                "reg_alpha": 0.1,
                "reg_lambda": 1.0,
                "_tuning_note": "lr=0.015 was attempted on 2026-05-27 and reverted — 97-fold re-validation showed -0.038 MAE not significant (CI includes 0)",
            },
            "walk_forward_results": quali_wf_results,
            "walk_forward_mean_mae": round(quali_avg_mae, 4) if quali_avg_mae else None,
            "walk_forward_mean_kendall_tau": round(quali_avg_tau, 4) if quali_avg_tau else None,
            "walk_forward_mean_top3_accuracy": round(quali_avg_top3, 4) if quali_avg_top3 else None,
            "top_features": {feat: round(float(imp), 4) for feat, imp in q_importances.head(15).items()},
        },
        "race_model": {
            "algorithm": "XGBRanker (rank:pairwise)",
            "save_format": "json",
            "n_features": len(race_available),
            "training_samples": len(y_r_rel),
            "trained_on": "actual quali_position",
            "used_for": "post-quali inference (actual quali known)",
            "params": {
                "n_estimators": 650,
                "learning_rate": 0.03,
                "max_depth": 5,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
                "min_child_weight": 5,
                "_tuning_note": "max_depth=2 was attempted on 2026-05-27 and reverted — 97-fold re-validation showed only -0.087 MAE (driven by one anomalous 2026 fold, with 2023 actually regressing). Robust depth=5 retained until a year-stable improvement is found.",
            },
            "walk_forward_results": race_wf_results,
            "walk_forward_mean_mae": round(race_avg_mae, 4) if race_avg_mae else None,
            "walk_forward_mean_kendall_tau": round(race_avg_tau, 4) if race_avg_tau else None,
            "walk_forward_mean_top3_accuracy": round(race_avg_top3, 4) if race_avg_top3 else None,
            "top_features": {feat: round(float(imp), 4) for feat, imp in r_importances.head(15).items()},
        },
        "race_model_fp": {
            "algorithm": "XGBRanker (rank:pairwise)" if race_fp_model is not None else "N/A",
            "save_format": "json",
            "n_features": len(race_available) if race_fp_model is not None else 0,
            "training_samples": race_fp_train_size,
            "trained": race_fp_model is not None,
            "trained_on": "walk-forward predicted quali_position",
            "used_for": "post-FP inference (predicted quali only)",
            "params": {
                "n_estimators": 650,
                "learning_rate": 0.03,
                "max_depth": 5,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
                "min_child_weight": 5,
            } if race_fp_model is not None else {},
            "walk_forward_results": race_fp_wf_results,
            "walk_forward_mean_mae": round(
                float(np.mean([r["mae"] for r in race_fp_wf_results])), 4
            ) if race_fp_wf_results else None,
            "walk_forward_mean_kendall_tau": round(
                float(np.mean([r["kendall_tau"] for r in race_fp_wf_results])), 4
            ) if race_fp_wf_results else None,
            "walk_forward_mean_top3_accuracy": round(
                float(np.mean([r["top3_accuracy"] for r in race_fp_wf_results])), 4
            ) if race_fp_wf_results else None,
            "post_fp_mae_delta_vs_race_model": race_fp_post_fp_delta,
            "top_features": (
                {feat: round(float(imp), 4) for feat, imp in r_fp_importances.head(15).items()}
                if not r_fp_importances.empty else {}
            ),
        },
        "fp_signal_model": {
            "algorithm": "ExtraTreesRegressor",
            "save_format": "pkl",
            "n_features": len(fp_available),
            "training_samples": fp_train_size,
            "trained": fp_model is not None,
        },
        "sprint_model": {
            "algorithm": "XGBRanker (rank:pairwise)" if sprint_model else "N/A",
            "save_format": "json",
            "n_features": len(sprint_available) if sprint_model else 0,
            "training_samples": sprint_train_size,
            "trained": sprint_model is not None,
            "trained_on": "actual quali_position + actual sprint_grid",
            "used_for": "post-sprint-quali inference (sprint_grid known)",
            "params": {
                "n_estimators": 400,
                "learning_rate": 0.035,
                "max_depth": 4,
                "subsample": 0.80,
                "colsample_bytree": 0.80,
                "min_child_weight": 5,
                "reg_alpha": 0.2,
                "reg_lambda": 1.5,
            } if sprint_model else {},
            "walk_forward_results": sprint_wf_results if sprint_model else [],
        },
        "sprint_model_fp": {
            "algorithm": "XGBRanker (rank:pairwise)" if sprint_fp_model is not None else "N/A",
            "save_format": "json",
            "n_features": len(sprint_available) if sprint_fp_model is not None else 0,
            "training_samples": sprint_fp_train_size,
            "trained": sprint_fp_model is not None,
            "trained_on": "walk-forward predicted quali for both quali_position and sprint_grid",
            "used_for": "post-FP inference on sprint weekends (pre-sprint-quali)",
            "params": {
                "n_estimators": 400,
                "learning_rate": 0.035,
                "max_depth": 4,
                "subsample": 0.80,
                "colsample_bytree": 0.80,
                "min_child_weight": 5,
                "reg_alpha": 0.2,
                "reg_lambda": 1.5,
            } if sprint_fp_model is not None else {},
            "walk_forward_results": sprint_fp_wf_results,
            "walk_forward_mean_mae": round(
                float(np.mean([r["mae"] for r in sprint_fp_wf_results])), 4
            ) if sprint_fp_wf_results else None,
            "walk_forward_mean_kendall_tau": round(
                float(np.mean([r["kendall_tau"] for r in sprint_fp_wf_results])), 4
            ) if sprint_fp_wf_results else None,
            "walk_forward_mean_top3_accuracy": round(
                float(np.mean([r["top3_accuracy"] for r in sprint_fp_wf_results])), 4
            ) if sprint_fp_wf_results else None,
            "post_fp_mae_delta_vs_sprint_model": sprint_fp_post_fp_delta,
            "top_features": (
                {feat: round(float(imp), 4) for feat, imp in s_fp_importances.head(15).items()}
                if not s_fp_importances.empty else {}
            ),
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
        print(f"  Qualifying model (rank:pairwise):")
        print(f"    Features:           {len(quali_available)}")
        print(f"    Walk-forward MAE:   {quali_avg_mae:.3f}")
        print(f"    Kendall's tau:      {quali_avg_tau:.3f}")
        print(f"    Top-3 accuracy:     {quali_avg_top3:.1%}")
        for r in quali_wf_results:
            print(f"      {r['test_year']}: MAE={r['mae']:.3f}, tau={r['kendall_tau']:.3f}, Top3={r['top3_accuracy']:.1%} (n={r['test_size']})")
    if race_wf_results:
        print(f"  Race model (post-quali, trained on actual quali):")
        print(f"    Features:           {len(race_available)}")
        print(f"    Walk-forward MAE:   {race_avg_mae:.3f}")
        print(f"    Kendall's tau:      {race_avg_tau:.3f}")
        print(f"    Top-3 accuracy:     {race_avg_top3:.1%}")
        for r in race_wf_results:
            print(f"      {r['test_year']}: MAE={r['mae']:.3f}, tau={r['kendall_tau']:.3f}, Top3={r['top3_accuracy']:.1%} (n={r['test_size']})")
    if race_fp_model is not None and race_fp_wf_results:
        fp_avg_mae = float(np.mean([r["mae"] for r in race_fp_wf_results]))
        fp_avg_tau = float(np.mean([r["kendall_tau"] for r in race_fp_wf_results]))
        fp_avg_top3 = float(np.mean([r["top3_accuracy"] for r in race_fp_wf_results]))
        print(f"  Race FP model (post-FP, trained on WF predicted quali):")
        print(f"    Features:           {len(race_available)}")
        print(f"    Walk-forward MAE:   {fp_avg_mae:.3f} (vs predicted quali, post-FP scenario)")
        print(f"    Kendall's tau:      {fp_avg_tau:.3f}")
        print(f"    Top-3 accuracy:     {fp_avg_top3:.1%}")
        for r in race_fp_wf_results:
            print(f"      {r['test_year']}: MAE={r['mae']:.3f}, tau={r['kendall_tau']:.3f}, Top3={r['top3_accuracy']:.1%} (n={r['test_size']})")
        if race_fp_post_fp_delta is not None:
            if race_fp_post_fp_delta > 0:
                print(f"    Delta vs race_model under post-FP: improved by {race_fp_post_fp_delta:.3f} MAE")
            else:
                print(f"    Delta vs race_model under post-FP: regressed by {-race_fp_post_fp_delta:.3f} MAE")
    if fp_model is not None:
        print(f"  FP signal model:      {fp_train_size} samples, {len(fp_available)} features")
    if sprint_model is not None:
        sprint_avg_mae = float(np.mean([r["mae"] for r in sprint_wf_results])) if sprint_wf_results else None
        sprint_avg_tau = float(np.mean([r["kendall_tau"] for r in sprint_wf_results])) if sprint_wf_results else None
        sprint_avg_top3 = float(np.mean([r["top3_accuracy"] for r in sprint_wf_results])) if sprint_wf_results else None
        print(f"  Sprint model (rank:pairwise):")
        print(f"    Features:           {len(sprint_available)}")
        if sprint_avg_mae:
            print(f"    Walk-forward MAE:   {sprint_avg_mae:.3f}")
            print(f"    Kendall's tau:      {sprint_avg_tau:.3f}")
            print(f"    Top-3 accuracy:     {sprint_avg_top3:.1%}")
        for r in sprint_wf_results:
            print(f"      {r['test_year']}: MAE={r['mae']:.3f}, tau={r['kendall_tau']:.3f}, Top3={r['top3_accuracy']:.1%} (n={r['test_size']})")
    print()
    print(f"  Output directory:     {TRAINED_DIR}")
    print(f"  Files saved:")
    print(f"    - quali_model.json")
    print(f"    - race_model.json")
    if race_fp_model is not None:
        print(f"    - race_model_fp.json")
    if fp_model is not None:
        print(f"    - fp_signal_model.pkl")
    if sprint_model is not None:
        print(f"    - sprint_model.json")
    if sprint_fp_model is not None:
        print(f"    - sprint_model_fp.json")
    print(f"    - model_metadata.json")
    print(f"    - feature_columns.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
