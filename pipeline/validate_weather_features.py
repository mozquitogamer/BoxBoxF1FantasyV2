"""
Weather-Awareness Level 3 — Validation Gate (Phase C step 1)

Compares the RACE model trained WITH vs WITHOUT the new weather features,
stratifying walk-forward MAE by wet vs dry rounds. Per the Level 3 plan §3
decision gate:

  * Ship only if WET MAE improves by >= 0.30 positions on average
  * AND DRY MAE does not regress by more than 0.10 positions on average
  * AND the wet improvement's 95% CI excludes zero

If the gate fails, we don't retrain the production models. We tweak (or drop)
weather features and re-run this script.

This is read-only — it does NOT touch models/trained/. Training only happens
after the gate passes, by running pipeline/05_train_models.py.

Usage:
    python pipeline/validate_weather_features.py
    python pipeline/validate_weather_features.py --min-test-year 2024
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import kendalltau
from sklearn.metrics import mean_absolute_error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    TRAINING_DATA_DIR,
    PROCESSED_DIR,
    MODEL_RANDOM_STATE,
)

# Import what we need from the training pipeline to keep behavior consistent.
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))
from importlib import import_module
_train = import_module("05_train_models")

# Race feature list comes from the same logic the production script uses,
# so we don't drift.
build_quali_feature_list = _train.build_quali_feature_list
build_race_feature_list = _train.build_race_feature_list
sort_by_race_groups = _train.sort_by_race_groups
make_race_qids = _train.make_race_qids
position_to_relevance = _train.position_to_relevance
scores_to_positions = _train.scores_to_positions

# The weather columns we added in Phase B
WEATHER_RACE_COLS_FULL = [
    "weather_was_wet_race",
    "weather_track_temp_race",
    "weather_air_temp_race",
    "weather_humidity_race",
    "weather_precip_minutes_race",
]

# Minimal set — keep only the binary wet flag + precip intensity. Drops temp/
# humidity which may be noise on the small wet sample (11 wet rounds in test).
WEATHER_RACE_COLS_MINIMAL = [
    "weather_was_wet_race",
    "weather_precip_minutes_race",
]


def race_model_factory():
    """Same hyperparams as production race_model (see 05_train_models.py)."""
    return xgb.XGBRanker(
        n_estimators=650,
        learning_rate=0.03,
        max_depth=5,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=5,
        tree_method="hist",
        objective="rank:pairwise",
        random_state=MODEL_RANDOM_STATE,
        n_jobs=-1,
        verbosity=0,
    )


def filter_finishers(df: pd.DataFrame) -> pd.DataFrame:
    """Mirrors the race-model training filter — classified finishers only."""
    out = df[df["finish_position"].notna()].copy()
    if "is_finished" in out.columns:
        out = out[out["is_finished"] == 1]
    elif "is_dnf" in out.columns:
        out = out[out["is_dnf"] == 0]
    if "is_dsq" in out.columns:
        out = out[out["is_dsq"] == 0]
    if "is_dns" in out.columns:
        out = out[out["is_dns"] == 0]
    return out


def train_and_predict_one_round(
    train_df: pd.DataFrame,
    test_round_df: pd.DataFrame,
    feature_cols: list[str],
    wet_weight_multiplier: float = 1.0,
) -> np.ndarray:
    """Fit on train_df, return predicted finishing positions for test_round_df.

    If wet_weight_multiplier > 1, training rows from wet races get their
    sample_weight multiplied by this factor — addresses the 90/10 dry/wet
    class imbalance.
    """
    available = [c for c in feature_cols if c in train_df.columns and c in test_round_df.columns]

    train_df = sort_by_race_groups(train_df).copy()
    test_round_df = sort_by_race_groups(test_round_df)

    # Optional wet-row weight boost. Per-row weight is what we modify; XGBRanker
    # later collapses to per-group weights (first row per group wins).
    if wet_weight_multiplier != 1.0 and "weather_was_wet_race" in train_df.columns:
        is_wet = (train_df["weather_was_wet_race"].fillna(0.0) > 0.5).astype(float)
        boost = 1.0 + (wet_weight_multiplier - 1.0) * is_wet
        if "sample_weight" not in train_df.columns:
            train_df["sample_weight"] = 1.0
        train_df["sample_weight"] = train_df["sample_weight"] * boost

    X_tr = train_df[available].copy()
    y_tr_rel = position_to_relevance(train_df["finish_position"])
    qids = make_race_qids(train_df)

    if "sample_weight" in train_df.columns:
        w = train_df["sample_weight"].values
        group_weights = []
        prev_q = -1
        for i, q in enumerate(qids):
            if q != prev_q:
                group_weights.append(w[i])
                prev_q = q
        w_groups = np.array(group_weights)
    else:
        w_groups = None

    model = race_model_factory()
    model.fit(X_tr, y_tr_rel, sample_weight=w_groups, qid=qids)

    scores = model.predict(test_round_df[available])
    return scores_to_positions(scores, test_round_df)


def evaluate_per_round(
    df: pd.DataFrame,
    feature_cols: list[str],
    test_year: int,
    wet_weight_multiplier: float = 1.0,
) -> list[dict]:
    """For each round of test_year, train on everything before that round,
    predict the round, return per-round metrics."""
    train_full = df[df["season"] < test_year]
    test_df = df[df["season"] == test_year]

    results = []
    for rnd in sorted(test_df["round"].unique()):
        test_round = test_df[test_df["round"] == rnd]
        if len(test_round) < 5:
            continue
        # Strict walk-forward: train only on rounds *before* this one
        train = pd.concat([
            train_full,
            test_df[test_df["round"] < rnd],
        ], ignore_index=True)
        if len(train) < 50:
            continue

        pred_pos = train_and_predict_one_round(
            train, test_round, feature_cols, wet_weight_multiplier
        )
        actual = test_round["finish_position"].values
        mae = float(mean_absolute_error(actual, pred_pos))

        if len(actual) >= 3:
            tau, _ = kendalltau(actual, pred_pos)
            tau = 0.0 if np.isnan(tau) else float(tau)
        else:
            tau = 0.0

        results.append({
            "season": int(test_year),
            "round": int(rnd),
            "n": int(len(test_round)),
            "mae": mae,
            "tau": tau,
        })
    return results


def attach_wet_label(per_round_results: list[dict], weather_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each per-round result with whether the race was wet."""
    out = pd.DataFrame(per_round_results)
    wkey = weather_df[weather_df["session_name"] == "R"][
        ["season", "round", "was_wet", "precip_minutes"]
    ].copy()
    out = out.merge(wkey, on=["season", "round"], how="left")
    out["was_wet"] = out["was_wet"].fillna(False).astype(bool)
    return out


def bootstrap_ci(values: np.ndarray, n_iter: int = 5000, alpha: float = 0.05) -> tuple[float, float]:
    """95% CI of the mean via bootstrap. Returns (lower, upper)."""
    if len(values) < 2:
        return (float(values.mean()), float(values.mean())) if len(values) else (0.0, 0.0)
    rng = np.random.default_rng(MODEL_RANDOM_STATE)
    samples = rng.choice(values, size=(n_iter, len(values)), replace=True).mean(axis=1)
    lo = float(np.percentile(samples, 100 * alpha / 2))
    hi = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    return lo, hi


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-test-year", type=int, default=2023,
        help="Earliest test season for walk-forward (default 2023). "
             "Earlier years have less prior data and noisier per-round MAE.",
    )
    parser.add_argument(
        "--features", choices=("full", "minimal"), default="full",
        help="'full' (default) = was_wet + precip + temp + humidity; "
             "'minimal' = was_wet + precip_minutes only. Drop temp/humidity "
             "if the small wet sample can't learn them.",
    )
    parser.add_argument(
        "--wet-weight", type=float, default=1.0,
        help="Multiply sample_weight of wet training rows by this factor "
             "(default 1.0 = no boost). Try 2.5 to compensate for the "
             "~85/15 dry/wet class imbalance.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Weather Features Validation Gate (Level 3 Phase C)")
    print("=" * 70)

    train_path = TRAINING_DATA_DIR / "all_training_data.parquet"
    weather_path = PROCESSED_DIR / "weather" / "all_session_weather.parquet"

    if not train_path.exists():
        print(f"ERROR: training data not found at {train_path}")
        print("Run pipeline/04_build_model_inputs.py --force-include-current first.")
        sys.exit(1)
    if not weather_path.exists():
        print(f"ERROR: weather data not found at {weather_path}")
        print("Run pipeline/03c_extract_session_weather.py first.")
        sys.exit(1)

    df = pd.read_parquet(train_path)
    weather_df = pd.read_parquet(weather_path)
    print(f"Loaded {len(df):,} training rows, {len(weather_df):,} session weather rows")

    weather_cols = (
        WEATHER_RACE_COLS_FULL if args.features == "full" else WEATHER_RACE_COLS_MINIMAL
    )
    print(f"Feature set: {args.features} ({len(weather_cols)} weather cols)")
    print(f"Wet weight multiplier: {args.wet_weight}x")

    # Confirm weather features are present
    missing_wcols = [c for c in weather_cols if c not in df.columns]
    if missing_wcols:
        print(f"ERROR: training data missing weather columns: {missing_wcols}")
        print("Rebuild with pipeline/04_build_model_inputs.py --force-include-current.")
        sys.exit(1)

    df = filter_finishers(df)
    print(f"After finisher filter: {len(df):,} rows")

    # Build the two feature lists
    all_cols = df.columns.tolist()
    quali_features = build_quali_feature_list(all_cols)
    race_features_baseline = build_race_feature_list(quali_features, all_cols)
    # Strip any weather columns that may have slipped in via auto-derivation
    race_features_baseline = [c for c in race_features_baseline if not c.startswith("weather_")]
    race_features_weather = race_features_baseline + [
        c for c in weather_cols if c in df.columns
    ]
    print(f"Baseline race features: {len(race_features_baseline)}")
    print(f"Weather race features:  {len(race_features_weather)} "
          f"(+{len(race_features_weather) - len(race_features_baseline)} weather cols)")

    # Walk-forward for each test season
    test_years = [y for y in sorted(df["season"].unique()) if y >= args.min_test_year]
    print(f"\nTest seasons: {test_years}")

    baseline_results = []
    weather_results = []
    for ty in test_years:
        print(f"\n--- Test season {ty} ---")
        print(f"  Training baseline model and predicting each round...")
        b_rows = evaluate_per_round(df, race_features_baseline, ty, wet_weight_multiplier=1.0)
        baseline_results.extend(b_rows)
        print(f"  Training weather model and predicting each round...")
        w_rows = evaluate_per_round(
            df, race_features_weather, ty, wet_weight_multiplier=args.wet_weight
        )
        weather_results.extend(w_rows)

    baseline_df = attach_wet_label(baseline_results, weather_df)
    weather_df_results = attach_wet_label(weather_results, weather_df)

    # Joint: side-by-side per round
    joint = baseline_df.merge(
        weather_df_results,
        on=["season", "round", "n", "was_wet", "precip_minutes"],
        suffixes=("_baseline", "_weather"),
    )
    joint["mae_delta"] = joint["mae_baseline"] - joint["mae_weather"]  # positive = improvement

    # Stratified summary
    print("\n" + "=" * 70)
    print("PER-ROUND RESULTS")
    print("=" * 70)
    print(joint.to_string(index=False))

    print("\n" + "=" * 70)
    print("STRATIFIED SUMMARY")
    print("=" * 70)
    wet = joint[joint["was_wet"]]
    dry = joint[~joint["was_wet"]]

    def _summarize(label: str, sub: pd.DataFrame) -> dict:
        if len(sub) == 0:
            print(f"\n{label}: no rounds in this stratum")
            return {}
        delta = sub["mae_delta"].values
        lo, hi = bootstrap_ci(delta)
        out = {
            "n_rounds": len(sub),
            "mae_baseline": float(sub["mae_baseline"].mean()),
            "mae_weather": float(sub["mae_weather"].mean()),
            "mae_delta_mean": float(delta.mean()),
            "mae_delta_ci_lo": lo,
            "mae_delta_ci_hi": hi,
        }
        print(f"\n{label} ({out['n_rounds']} rounds)")
        print(f"  Baseline MAE: {out['mae_baseline']:.3f}")
        print(f"  Weather MAE:  {out['mae_weather']:.3f}")
        sign = "+" if out["mae_delta_mean"] >= 0 else ""
        print(f"  Delta (baseline - weather): {sign}{out['mae_delta_mean']:.3f} positions")
        print(f"  95% bootstrap CI: [{out['mae_delta_ci_lo']:+.3f}, {out['mae_delta_ci_hi']:+.3f}]")
        return out

    wet_stats = _summarize("WET RACES", wet)
    dry_stats = _summarize("DRY RACES", dry)
    all_stats = _summarize("ALL RACES", joint)

    # Decision gate
    print("\n" + "=" * 70)
    print("DECISION GATE")
    print("=" * 70)
    gate_pass = True
    reasons = []
    if not wet_stats:
        gate_pass = False
        reasons.append("FAIL: no wet rounds in test window — can't gate")
    else:
        if wet_stats["mae_delta_mean"] < 0.30:
            gate_pass = False
            reasons.append(
                f"FAIL: wet MAE improvement {wet_stats['mae_delta_mean']:+.3f} < required +0.30"
            )
        else:
            reasons.append(
                f"PASS: wet MAE improved by {wet_stats['mae_delta_mean']:+.3f} (gate >= +0.30)"
            )
        if wet_stats["mae_delta_ci_lo"] <= 0:
            gate_pass = False
            reasons.append(
                f"FAIL: wet improvement 95% CI lower bound {wet_stats['mae_delta_ci_lo']:+.3f} "
                f"crosses zero — not statistically distinguishable from noise"
            )
        else:
            reasons.append(
                f"PASS: wet improvement CI [{wet_stats['mae_delta_ci_lo']:+.3f}, "
                f"{wet_stats['mae_delta_ci_hi']:+.3f}] excludes zero"
            )

    if dry_stats:
        # delta = baseline - weather. Negative delta = weather model worse (regression)
        if dry_stats["mae_delta_mean"] < -0.10:
            gate_pass = False
            reasons.append(
                f"FAIL: dry MAE regressed by {-dry_stats['mae_delta_mean']:+.3f} (gate <= 0.10 regression)"
            )
        else:
            reasons.append(
                f"PASS: dry MAE delta {dry_stats['mae_delta_mean']:+.3f} (gate allows up to -0.10)"
            )

    for r in reasons:
        print(f"  {r}")
    print()
    if gate_pass:
        print("  >> GATE PASSED -- safe to retrain production models with weather features.")
        print("  Next: enable weather features in 05_train_models.py and run it.")
    else:
        print("  >> GATE FAILED -- do not ship. Consider:")
        print("     (a) dropping noisy weather features (temp/humidity, keep only was_wet)")
        print("     (b) sample-weighting wet rows in training (~2-3x)")
        print("     (c) re-extracting weather with tighter thresholds")
    print("=" * 70)


if __name__ == "__main__":
    main()
