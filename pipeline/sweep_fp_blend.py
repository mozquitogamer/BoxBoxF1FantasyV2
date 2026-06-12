"""
Sweep the FP-pace quali-blend weight against completed 2026 rounds (leak-free).

Context
-------
06_run_predictions.py blends the quali model's raw scores toward a composite of
FP pace metrics (best lap + best-3 + best-5 lap averages) in z-score space:

    blended = (1 - w) * z(model_score) + w * z(fp_composite)     [has-pace drivers]

The deployed base weight w=0.6 came from an early 4-round backtest. This script
re-derives the optimal weight with proper leak-free round-level walk-forward:
for each completed 2026 round N, a quali model is trained ONLY on data before N
(all seasons < 2026 plus 2026 rounds < N), exactly mirroring what production
could have known at that weekend's post-FP phase. The blend math replicates
06_run_predictions.py verbatim (including its ddof quirks: per-metric z uses
pandas std ddof=1, model/composite z uses numpy std ddof=0).

Decision guidance (printed at the end):
  - GLOBAL weight verdict uses only normal-track folds (overtaking_difficulty
    <= hard_track_pivot, i.e. rounds where deploy uses the base weight).
  - Monaco-tier folds are reported separately as calibration evidence for
    `weight_hard_track` (deploy 0.80) — n is tiny, directional only.
  - Paired bootstrap CI over pooled per-driver |error| deltas vs the current
    base weight 0.6.

No production files are touched: models are trained in memory, results go to
data/experiments/fp_blend_sweep_2026.json.

Usage:
    python pipeline/sweep_fp_blend.py
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (  # noqa: E402
    TRAINING_DATA_DIR,
    MODEL_RANDOM_STATE,
    CURRENT_SEASON,
    race_name_for_round,
)
from config.track_classifications import (  # noqa: E402
    get_circuit_id_from_race_name,
    _difficulty_for,
)

# Import 05_train_models helpers (digit-leading module name -> importlib).
_spec = _ilu.spec_from_file_location(
    "train_models_mod", PROJECT_ROOT / "pipeline" / "05_train_models.py"
)
_tm = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_tm)

build_quali_feature_list = _tm.build_quali_feature_list
sort_by_race_groups = _tm.sort_by_race_groups
make_race_qids = _tm.make_race_qids
position_to_relevance = _tm.position_to_relevance
apply_wet_training_boost = _tm.apply_wet_training_boost

import xgboost as xgb  # noqa: E402

# Mirror FP_QUALI_BLEND_TUNABLES in 06_run_predictions.py
PACE_COLS = ["best_lap_time", "best_3_lap_avg", "best_5_lap_avg"]
MIN_DRIVERS_WITH_PACE = 10
CURRENT_BASE_WEIGHT = 0.6
CURRENT_HARD_WEIGHT = 0.80
HARD_TRACK_PIVOT = 6

WEIGHTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 1.0]

OUT_PATH = PROJECT_ROOT / "data" / "experiments" / "fp_blend_sweep_2026.json"


def make_quali_model():
    """EXACT copy of the production quali model (05_train_models.py::make_quali_model)."""
    return xgb.XGBRanker(
        n_estimators=1200,
        learning_rate=0.025,
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


def _zscore_np(a: np.ndarray) -> np.ndarray:
    """Deploy parity: 06_run_predictions.py::_zscore_q (numpy std, ddof=0)."""
    a = np.asarray(a, dtype=float)
    s = a.std()
    return (a - a.mean()) / s if s > 1e-9 else a - a.mean()


def fp_composite(test_df: pd.DataFrame) -> pd.Series:
    """Deploy parity: per-metric z with pandas std (ddof=1), negated, row-mean skipna."""
    zmat = []
    for c in PACE_COLS:
        col = pd.to_numeric(test_df[c], errors="coerce")
        sd = col.std()  # pandas ddof=1, NaN-aware — matches 06
        zmat.append(-(col - col.mean()) / sd if sd and sd > 1e-9 else col * 0.0)
    return pd.concat(zmat, axis=1).mean(axis=1, skipna=True)


def blend_and_rank(quali_raw: np.ndarray, comp: pd.Series, w: float) -> np.ndarray:
    """Deploy parity: z-blend for has-pace drivers, rank descending (method='first')."""
    has_pace = comp.notna().values
    z_model = _zscore_np(quali_raw)
    blended = z_model.copy()
    if w > 0 and int(has_pace.sum()) >= MIN_DRIVERS_WITH_PACE:
        comp_z = np.zeros(len(comp))
        comp_z[has_pace] = _zscore_np(comp.values[has_pace])
        blended[has_pace] = (1.0 - w) * z_model[has_pace] + w * comp_z[has_pace]
    ranks = pd.Series(-blended).rank(method="first").astype(int).values
    return ranks


def fit_fold_model(train_df: pd.DataFrame, features: list[str]):
    """Train the quali model on a fold's training slice, mirroring 05's final-fit recipe."""
    tr = apply_wet_training_boost(train_df)  # default wet_col, matches 05 quali block
    tr = sort_by_race_groups(tr)
    X = tr[features]
    y_rel = position_to_relevance(tr["quali_position"])
    qids = make_race_qids(tr)
    w = tr["sample_weight"].values if "sample_weight" in tr.columns else None
    if w is not None:
        group_weights, prev = [], -1
        for i, qid in enumerate(qids):
            if qid != prev:
                group_weights.append(w[i])
                prev = qid
        w_groups = np.array(group_weights)
    else:
        w_groups = None
    model = make_quali_model()
    model.fit(X, y_rel, sample_weight=w_groups, qid=qids)
    return model


def circuit_difficulty(round_num: int) -> tuple[str, int]:
    race_name = race_name_for_round(round_num)
    circuit = get_circuit_id_from_race_name(race_name) if race_name else None
    diff = _difficulty_for(circuit) if circuit else 5
    return circuit or "unknown", int(diff)


def paired_bootstrap_ci(err_a: np.ndarray, err_b: np.ndarray, n_boot: int = 10_000,
                        seed: int = 42) -> tuple[float, float, float]:
    """95% CI for mean(err_a - err_b) over paired per-driver absolute errors."""
    rng = np.random.default_rng(seed)
    delta = err_a - err_b
    n = len(delta)
    means = np.array([delta[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    return float(delta.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    print("=" * 72)
    print("FP-pace quali-blend weight sweep — leak-free round-level walk-forward")
    print("=" * 72)

    df = pd.read_parquet(TRAINING_DATA_DIR / "all_training_data.parquet")
    print(f"Training data: {len(df):,} rows")

    features = [c for c in build_quali_feature_list(df.columns.tolist()) if c in df.columns]
    print(f"Quali features: {len(features)}")

    folds = sorted(
        int(r) for r in df[(df.season == CURRENT_SEASON) & df.quali_position.notna()]["round"].unique()
    )
    print(f"2026 folds: {folds}")

    results = {}        # round -> {weight -> mae}
    fold_meta = {}      # round -> {circuit, difficulty, n, blend_active}
    per_driver_err = {} # (normal-folds pooled) weight -> list of |err|

    for w in WEIGHTS:
        per_driver_err[w] = []

    for rnd in folds:
        train_mask = (
            ((df.season < CURRENT_SEASON) | ((df.season == CURRENT_SEASON) & (df["round"] < rnd)))
            & df.quali_position.notna()
        )
        test_mask = (df.season == CURRENT_SEASON) & (df["round"] == rnd) & df.quali_position.notna()
        train_df = df[train_mask].copy()
        test_df = df[test_mask].copy().reset_index(drop=True)
        if len(train_df) < 100 or len(test_df) < 5:
            print(f"  R{rnd}: skipped (train={len(train_df)}, test={len(test_df)})")
            continue

        circuit, diff = circuit_difficulty(rnd)
        model = fit_fold_model(train_df, features)
        quali_raw = model.predict(test_df[features])

        comp = fp_composite(test_df)
        n_pace = int(comp.notna().sum())
        blend_active = n_pace >= MIN_DRIVERS_WITH_PACE
        actual = test_df["quali_position"].astype(float).values

        results[rnd] = {}
        for w in WEIGHTS:
            ranks = blend_and_rank(quali_raw, comp, w)
            errs = np.abs(ranks - actual)
            results[rnd][w] = float(errs.mean())
            # Pool per-driver errors for the GLOBAL decision: normal tracks only
            if diff <= HARD_TRACK_PIVOT and blend_active:
                per_driver_err[w].extend(errs.tolist())

        fold_meta[rnd] = {
            "circuit": circuit, "difficulty": diff, "n_test": len(test_df),
            "n_with_pace": n_pace, "blend_active": blend_active,
            "train_rows": len(train_df),
        }
        tag = "HARD" if diff > HARD_TRACK_PIVOT else "normal"
        status = "" if blend_active else "  [blend SKIPPED — no FP pace]"
        print(f"  R{rnd} ({circuit}, diff={diff}, {tag}): train={len(train_df):,} "
              f"test={len(test_df)} pace={n_pace}{status}")

    # ---- Report ----
    normal_folds = [r for r in results if fold_meta[r]["difficulty"] <= HARD_TRACK_PIVOT
                    and fold_meta[r]["blend_active"]]
    hard_folds = [r for r in results if fold_meta[r]["difficulty"] > HARD_TRACK_PIVOT
                  and fold_meta[r]["blend_active"]]

    print(f"\n{'weight':>7} | " + " | ".join(f"R{r:<4}" for r in results) +
          " | normal-mean | hard-mean")
    print("-" * (10 + 8 * len(results) + 26))
    summary = {}
    for w in WEIGHTS:
        row = [results[r][w] for r in results]
        nmean = float(np.mean([results[r][w] for r in normal_folds])) if normal_folds else float("nan")
        hmean = float(np.mean([results[r][w] for r in hard_folds])) if hard_folds else float("nan")
        summary[w] = {"normal_mean_mae": nmean, "hard_mean_mae": hmean}
        marker = " <- current base" if abs(w - CURRENT_BASE_WEIGHT) < 1e-9 else ""
        print(f"{w:>7.2f} | " + " | ".join(f"{v:5.2f}" for v in row) +
              f" | {nmean:11.3f} | {hmean:9.3f}{marker}")

    # Winner on normal tracks
    best_w = min(summary, key=lambda w: summary[w]["normal_mean_mae"])
    cur = summary[CURRENT_BASE_WEIGHT]["normal_mean_mae"]
    best = summary[best_w]["normal_mean_mae"]

    print(f"\nGLOBAL (normal tracks, folds {normal_folds}):")
    print(f"  current w=0.60: MAE {cur:.3f}")
    print(f"  best    w={best_w:.2f}: MAE {best:.3f}  (delta {best - cur:+.3f})")

    boot = None
    if abs(best_w - CURRENT_BASE_WEIGHT) > 1e-9:
        a = np.array(per_driver_err[best_w])
        b = np.array(per_driver_err[CURRENT_BASE_WEIGHT])
        mean_d, lo, hi = paired_bootstrap_ci(a, b)
        boot = {"mean_delta": mean_d, "ci95": [lo, hi]}
        print(f"  paired bootstrap (pooled per-driver |err|, n={len(a)}): "
              f"delta {mean_d:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]")
        # Per-round consistency
        wins = sum(1 for r in normal_folds if results[r][best_w] <= results[r][CURRENT_BASE_WEIGHT])
        print(f"  per-round: best_w no-worse than 0.60 in {wins}/{len(normal_folds)} normal folds")

    if hard_folds:
        print(f"\nHARD-TRACK ceiling calibration (folds {hard_folds}, deploy uses w=0.80):")
        for r in hard_folds:
            ordered = sorted(WEIGHTS, key=lambda w: results[r][w])
            print(f"  R{r} ({fold_meta[r]['circuit']}): " +
                  ", ".join(f"w={w:.2f}:{results[r][w]:.2f}" for w in ordered[:5]) +
                  f"  | at 0.80: {results[r][0.8]:.2f}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weights": WEIGHTS,
            "per_round_mae": {str(r): {f"{w:.2f}": v for w, v in results[r].items()} for r in results},
            "fold_meta": {str(r): m for r, m in fold_meta.items()},
            "normal_folds": normal_folds,
            "hard_folds": hard_folds,
            "summary": {f"{w:.2f}": s for w, s in summary.items()},
            "current_base_weight": CURRENT_BASE_WEIGHT,
            "best_weight_normal": best_w,
            "bootstrap_vs_current": boot,
        }, f, indent=2)
    print(f"\nSaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
