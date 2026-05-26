"""
Weather Awareness — Level 3.5: DNF Classifier

Trains a small per-driver DNF probability model on historical race rows
conditioned on weather + reliability features. Replaces the lookup of
`roll_dnf_rate_5` inside `08_monte_carlo_fantasy.py` with calibrated
predictions that genuinely change with rain risk and track temperature.

Why a separate model (and not just adding DNF columns to the race model):
  - The race model predicts FINISHING POSITION among classified finishers.
    DNFs are excluded from its training set entirely. Adding DNF as a
    target there would conflate two different prediction tasks.
  - DNF prediction is a small-positive-class problem (~13% base rate, ~50
    wet-DNF rows out of ~340 wet rows). Wants its own calibration step.

Algorithm:
  - LogisticRegression(class_weight='balanced') wrapped in
    CalibratedClassifierCV(method='isotonic') for honest probabilities
  - 5-fold stratified cross-validation reports Brier score + AUC +
    calibration curve agreement
  - Final model is fit on ALL data after CV passes the gate

Gate (any of these fails -> don't ship):
  - Brier score must be at least 1% better than baseline (predicting the
    base DNF rate for everyone). On a 13% base rate, baseline Brier ~= 0.113.
  - ROC AUC must be > 0.60 (some discriminative power)
  - On wet-only rows the model's mean predicted DNF prob must be
    measurably higher than on dry-only rows (confirms the weather signal
    actually flows through)

Inputs:
  models/training_data/all_training_data.parquet

Outputs:
  models/trained/dnf_classifier.pkl     (dict: model + features + cv_metrics)
  models/trained/dnf_classifier_meta.json  (human-readable metrics)

Usage:
  python pipeline/train_dnf_classifier.py
  python pipeline/train_dnf_classifier.py --no-gate    (skip gate, force ship)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import TRAINING_DATA_DIR, TRAINED_DIR


# Features the classifier sees. Mix of:
#   - Weather (conditional signal we're trying to capture)
#   - Reliability rolling rates (per-driver, per-constructor, broken down by cause)
#   - Track DNF priors (safety_car_probability, turn1_incident_risk)
#   - Skills (wet/cold; the conditional X feature)
#   - Quali grid context (front-row drivers DNF less from incidents)
DNF_FEATURES = [
    # Weather conditional
    "weather_was_wet_race",
    "weather_track_temp_race",
    "weather_air_temp_race",
    "weather_precip_minutes_race",
    # Rolling reliability (per driver / per constructor)
    "roll_dnf_rate_5",
    "roll_mech_dnf_rate_5_constructor",
    "roll_mech_dnf_rate_5_driver",
    "roll_collision_dnf_rate_5_driver",
    "roll_drivererror_dnf_rate_5_driver",
    # Track-level DNF priors
    "safety_car_probability",
    "turn1_incident_risk",
    # Skills (interact with weather features for the model to learn
    # "wet-skilled driver in rain is LESS likely to DNF than rookie in rain")
    "wet_skill",
    "cold_skill",
    # Grid / season context
    "quali_position",  # front-row drivers are safer from turn-1 carnage
    "season_progress",
]


def load_training_data() -> pd.DataFrame:
    path = TRAINING_DATA_DIR / "all_training_data.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Training data not found at {path}. "
                                f"Run pipeline/04_build_model_inputs.py first.")
    return pd.read_parquet(path)


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Build feature matrix + target. Sensible imputation for missing weather
    (older seasons we never extracted): assume dry, median temperatures.

    Drops rows with missing TARGET only (is_dnf must be present).
    """
    df = df[df["is_dnf"].notna()].copy()
    df["is_dnf"] = df["is_dnf"].astype(int)

    # Make sure all expected feature columns exist
    available = [c for c in DNF_FEATURES if c in df.columns]
    missing_cols = [c for c in DNF_FEATURES if c not in df.columns]
    if missing_cols:
        print(f"  [WARN] missing feature columns: {missing_cols} — skipping them.")

    X = df[available].copy()

    # Weather imputation: assume dry / median temps for rows missing weather
    # (older seasons that pre-date the FastF1 cache we extracted from).
    fill_values = {
        "weather_was_wet_race": 0.0,
        "weather_track_temp_race": X["weather_track_temp_race"].median() if "weather_track_temp_race" in X else 30.0,
        "weather_air_temp_race": X["weather_air_temp_race"].median() if "weather_air_temp_race" in X else 22.0,
        "weather_precip_minutes_race": 0.0,
    }
    for col, val in fill_values.items():
        if col in X.columns:
            X[col] = X[col].fillna(val)

    # All other features: median fill
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())

    return X, df["is_dnf"]


def cross_validate(X: pd.DataFrame, y: pd.Series, n_splits: int = 5) -> dict:
    """Stratified k-fold CV. Returns Brier, AUC, baseline Brier, wet/dry pred
    means, and calibration agreement."""
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    briers, aucs, wet_means, dry_means = [], [], [], []
    all_y, all_p = [], []

    for fold, (tr_idx, te_idx) in enumerate(skf.split(X, y)):
        X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
        y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]

        base = LogisticRegression(
            class_weight="balanced", max_iter=1000, C=1.0, solver="liblinear",
        )
        # Use isotonic calibration on inner CV split. cv=3 to keep wet positives
        # in every fold (with cv=5 some inner folds would have ~0 wet DNFs).
        clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
        clf.fit(X_tr, y_tr)

        p = clf.predict_proba(X_te)[:, 1]
        briers.append(brier_score_loss(y_te, p))
        try:
            aucs.append(roc_auc_score(y_te, p))
        except ValueError:
            aucs.append(np.nan)

        # Wet vs dry predicted means on the held-out fold
        wet_mask = X_te["weather_was_wet_race"] == 1.0
        dry_mask = X_te["weather_was_wet_race"] == 0.0
        if wet_mask.sum() > 0:
            wet_means.append(p[wet_mask.values].mean())
        if dry_mask.sum() > 0:
            dry_means.append(p[dry_mask.values].mean())

        all_y.extend(y_te.tolist())
        all_p.extend(p.tolist())
        print(f"  Fold {fold + 1}: Brier={briers[-1]:.4f}, AUC={aucs[-1]:.3f}, "
              f"wet_mean={wet_means[-1] if wet_means else 'n/a':.3f}, "
              f"dry_mean={dry_means[-1] if dry_means else 'n/a':.3f}")

    # Baseline: predicting the base DNF rate for everyone
    base_rate = y.mean()
    baseline_brier = brier_score_loss(y, np.full(len(y), base_rate))

    # Calibration curve check: average absolute deviation from y=x line
    all_y_arr = np.array(all_y)
    all_p_arr = np.array(all_p)
    try:
        prob_true, prob_pred = calibration_curve(all_y_arr, all_p_arr, n_bins=10, strategy="quantile")
        calib_mae = float(np.abs(prob_true - prob_pred).mean())
    except Exception:
        calib_mae = None

    return {
        "n_folds": n_splits,
        "brier_mean": float(np.mean(briers)),
        "brier_std": float(np.std(briers)),
        "baseline_brier": float(baseline_brier),
        "brier_improvement_pct": float(100.0 * (baseline_brier - np.mean(briers)) / baseline_brier),
        "auc_mean": float(np.nanmean(aucs)),
        "wet_pred_mean": float(np.mean(wet_means)) if wet_means else None,
        "dry_pred_mean": float(np.mean(dry_means)) if dry_means else None,
        "wet_minus_dry": (
            float(np.mean(wet_means) - np.mean(dry_means))
            if (wet_means and dry_means) else None
        ),
        "calibration_mae": calib_mae,
        "n_samples": int(len(y)),
        "n_positives": int(y.sum()),
        "base_rate": float(base_rate),
    }


def check_gate(metrics: dict) -> tuple[bool, list[str]]:
    """Return (gate_passed, reasons)."""
    reasons = []
    passed = True
    # Brier improvement >= 1%
    imp = metrics.get("brier_improvement_pct", 0)
    if imp < 1.0:
        passed = False
        reasons.append(f"FAIL: Brier improvement {imp:.2f}% < 1% (model barely better than predicting base rate)")
    else:
        reasons.append(f"PASS: Brier improvement {imp:.2f}% (>= 1%)")
    # AUC > 0.60
    auc = metrics.get("auc_mean", 0)
    if auc < 0.60:
        passed = False
        reasons.append(f"FAIL: AUC {auc:.3f} < 0.60 (insufficient discriminative power)")
    else:
        reasons.append(f"PASS: AUC {auc:.3f} (> 0.60)")
    # Wet-minus-dry must be positive (model believes wet is riskier)
    wmd = metrics.get("wet_minus_dry")
    if wmd is None or wmd <= 0:
        passed = False
        reasons.append(f"FAIL: wet_minus_dry {wmd} <= 0 (model doesn't see wet as riskier than dry — weather signal not flowing)")
    else:
        reasons.append(f"PASS: wet_minus_dry +{wmd:.3f} (model believes wet is riskier)")
    return passed, reasons


def fit_final_model(X: pd.DataFrame, y: pd.Series):
    base = LogisticRegression(
        class_weight="balanced", max_iter=1000, C=1.0, solver="liblinear",
    )
    clf = CalibratedClassifierCV(base, method="isotonic", cv=5)
    clf.fit(X, y)
    return clf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-gate", action="store_true",
                        help="Skip the validation gate and ship anyway (use sparingly).")
    args = parser.parse_args()

    print("=" * 70)
    print("DNF Classifier Training (Weather Level 3.5)")
    print("=" * 70)

    df = load_training_data()
    print(f"\nLoaded {len(df):,} training rows")

    X, y = prepare_features(df)
    print(f"After target-NaN filter: {len(y):,} rows, {y.sum():,} DNFs ({y.mean()*100:.1f}% base rate)")
    print(f"Features: {len(X.columns)} columns")

    print("\nStratified 5-fold cross-validation:")
    metrics = cross_validate(X, y, n_splits=5)

    print("\n" + "=" * 70)
    print("METRICS SUMMARY")
    print("=" * 70)
    print(f"  Brier score (mean):   {metrics['brier_mean']:.4f} ± {metrics['brier_std']:.4f}")
    print(f"  Baseline Brier:       {metrics['baseline_brier']:.4f} (predicting base rate)")
    print(f"  Brier improvement:    {metrics['brier_improvement_pct']:.2f}%")
    print(f"  AUC (mean):           {metrics['auc_mean']:.3f}")
    print(f"  Wet pred mean:        {metrics['wet_pred_mean']:.3f}")
    print(f"  Dry pred mean:        {metrics['dry_pred_mean']:.3f}")
    print(f"  Wet - dry:            {metrics['wet_minus_dry']:+.3f} (positive = model believes wet is riskier)")
    if metrics.get("calibration_mae") is not None:
        print(f"  Calibration MAE:      {metrics['calibration_mae']:.3f} (lower = better calibrated)")

    print("\n" + "=" * 70)
    print("GATE CHECK")
    print("=" * 70)
    gate_passed, reasons = check_gate(metrics)
    for r in reasons:
        print(f"  {r}")

    if not gate_passed and not args.no_gate:
        print("\n  >> GATE FAILED — model NOT saved. Investigate features / class imbalance.")
        print("     Pass --no-gate to force ship.")
        return

    if not gate_passed:
        print("\n  >> Gate failed but --no-gate set; saving anyway.")

    print("\nFitting final model on all data...")
    clf = fit_final_model(X, y)

    TRAINED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TRAINED_DIR / "dnf_classifier.pkl"
    joblib.dump({
        "model": clf,
        "features": list(X.columns),
        "feature_fillna": {
            "weather_was_wet_race": 0.0,
            "weather_track_temp_race": float(X["weather_track_temp_race"].median()),
            "weather_air_temp_race": float(X["weather_air_temp_race"].median()),
            "weather_precip_minutes_race": 0.0,
        },
        "training_samples": len(y),
        "training_positives": int(y.sum()),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "algorithm": "CalibratedClassifierCV(LogisticRegression(class_weight='balanced'), method='isotonic', cv=5)",
    }, out_path)
    print(f"Saved -> {out_path}")

    # Human-readable metadata
    meta_path = TRAINED_DIR / "dnf_classifier_meta.json"
    with open(meta_path, "w") as f:
        json.dump({
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_samples": len(y),
            "training_positives": int(y.sum()),
            "features": list(X.columns),
            "metrics": metrics,
            "gate_passed": gate_passed,
            "gate_reasons": reasons,
        }, f, indent=2)
    print(f"Saved -> {meta_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
