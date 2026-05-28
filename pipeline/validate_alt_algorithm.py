"""Walk-forward validator for alternative ranking algorithms.

Mirrors validate_model_config.py's fold semantics exactly (same train/test
splits, same metrics, same bootstrap CI) but swaps in:

  - LightGBM LambdaRank (lambdarank objective, NDCG-optimised)
  - An ENSEMBLE that averages the predicted positions of:
      (1) XGBoost rank:pairwise at our best config (race depth=2, quali lr=0.015)
      (2) LightGBM LambdaRank

Outputs JSON under data/experiments/ so the comparison machinery in
validate_model_config.py --compare works against the existing baseline.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("vmc", PROJECT_ROOT / "pipeline" / "validate_model_config.py")
_vmc = _ilu.module_from_spec(_spec)
sys.modules["vmc"] = _vmc  # Required for @dataclass to find module under Python 3.12+
_spec.loader.exec_module(_vmc)  # type: ignore[union-attr]

load_training_data = _vmc.load_training_data
completed_2026_rounds = _vmc.completed_2026_rounds
reweight_2026 = _vmc.reweight_2026
sort_by_race_groups = _vmc.sort_by_race_groups
make_race_qids = _vmc.make_race_qids
position_to_relevance = _vmc.position_to_relevance
scores_to_positions = _vmc.scores_to_positions
fold_metrics = _vmc.fold_metrics
summarise = _vmc.summarise
build_quali_feature_list = _vmc.build_quali_feature_list
build_race_feature_list = _vmc.build_race_feature_list
WEATHER_RACE_FEATURES = _vmc.WEATHER_RACE_FEATURES
WEATHER_SPRINT_FEATURES = _vmc.WEATHER_SPRINT_FEATURES
EXPERIMENTS_DIR = _vmc.EXPERIMENTS_DIR
RNG_SEED = _vmc.RNG_SEED
CURRENT_SEASON = _vmc.CURRENT_SEASON

# Best XGBoost params from the OAT + combined-grid sweep
XGB_BEST_QUALI = dict(
    n_estimators=1200, learning_rate=0.015, max_depth=3,
    subsample=0.85, colsample_bytree=0.85, min_child_weight=3,
    reg_alpha=0.1, reg_lambda=1.0, tree_method="hist",
    objective="rank:pairwise", random_state=RNG_SEED, n_jobs=-1,
)
XGB_BEST_RACE = dict(
    n_estimators=650, learning_rate=0.03, max_depth=2,
    subsample=0.85, colsample_bytree=0.85, min_child_weight=5,
    reg_alpha=0.1, reg_lambda=1.0, tree_method="hist",
    objective="rank:pairwise", random_state=RNG_SEED, n_jobs=-1,
)
XGB_BEST_SPRINT = dict(
    n_estimators=400, learning_rate=0.035, max_depth=4,
    subsample=0.80, colsample_bytree=0.80, min_child_weight=5,
    reg_alpha=0.2, reg_lambda=1.5, tree_method="hist",
    objective="rank:pairwise", random_state=RNG_SEED, n_jobs=-1,
)

# LightGBM LambdaRank — match XGBoost roughly so it's a fair comparison
LGBM_QUALI = dict(
    objective="lambdarank", n_estimators=1200, learning_rate=0.015,
    max_depth=-1, num_leaves=15, min_child_samples=5,
    subsample=0.85, colsample_bytree=0.85,
    random_state=RNG_SEED, verbose=-1, n_jobs=-1,
)
LGBM_RACE = dict(
    objective="lambdarank", n_estimators=650, learning_rate=0.03,
    max_depth=-1, num_leaves=7, min_child_samples=5,
    subsample=0.85, colsample_bytree=0.85,
    random_state=RNG_SEED, verbose=-1, n_jobs=-1,
)
LGBM_SPRINT = dict(
    objective="lambdarank", n_estimators=400, learning_rate=0.035,
    max_depth=-1, num_leaves=15, min_child_samples=5,
    subsample=0.80, colsample_bytree=0.80,
    random_state=RNG_SEED, verbose=-1, n_jobs=-1,
)


def _group_sizes(qids: np.ndarray) -> list[int]:
    """LightGBM wants group SIZES (a list of group lengths), not per-sample qids."""
    sizes = []
    prev = -1
    count = 0
    for q in qids:
        if q != prev:
            if prev != -1:
                sizes.append(count)
            prev = q
            count = 1
        else:
            count += 1
    sizes.append(count)
    return sizes


def _group_weights(qids: np.ndarray, per_sample_weights: np.ndarray) -> np.ndarray:
    out = []
    prev = -1
    for i, q in enumerate(qids):
        if q != prev:
            out.append(per_sample_weights[i])
            prev = q
    return np.asarray(out, dtype=float)


def train_xgb(train_df: pd.DataFrame, features: list[str], target_col: str, params: dict):
    train_df = sort_by_race_groups(train_df)
    X = train_df[features].copy()
    y = position_to_relevance(train_df[target_col])
    qids = make_race_qids(train_df)
    w_per_sample = train_df["sample_weight"].to_numpy() if "sample_weight" in train_df.columns else None
    w_groups = _group_weights(qids, w_per_sample) if w_per_sample is not None else None
    model = xgb.XGBRanker(**params)
    model.fit(X, y, qid=qids, sample_weight=w_groups)
    return model


def train_lgbm(train_df: pd.DataFrame, features: list[str], target_col: str, params: dict):
    train_df = sort_by_race_groups(train_df)
    X = train_df[features].copy()
    y = position_to_relevance(train_df[target_col]).astype(int)  # LightGBM wants int labels
    qids = make_race_qids(train_df)
    sizes = _group_sizes(qids)
    w_per_sample = train_df["sample_weight"].to_numpy() if "sample_weight" in train_df.columns else None
    w_groups = _group_weights(qids, w_per_sample) if w_per_sample is not None else None
    model = lgb.LGBMRanker(**params)
    # LightGBM uses per-group weight via the `group` arg, per-sample weight via sample_weight kwarg.
    # We pass per-sample weight here since LightGBM will internally aggregate per group.
    if w_per_sample is not None:
        model.fit(X, y, group=sizes, sample_weight=w_per_sample)
    else:
        model.fit(X, y, group=sizes)
    return model


def predict_positions(model, test_df: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, pd.DataFrame]:
    test_sorted = sort_by_race_groups(test_df)
    scores = model.predict(test_sorted[features].copy())
    positions = scores_to_positions(np.asarray(scores, dtype=float), test_sorted)
    return positions, test_sorted


def average_positions(*position_arrays: np.ndarray, sorted_df: pd.DataFrame) -> np.ndarray:
    """Average predicted positions across models, then re-rank within each race group.

    Position averaging is more stable than raw-score averaging when models output
    different score scales (XGBoost rank:pairwise vs LightGBM lambdarank).
    """
    mean_positions = np.mean(np.stack(position_arrays, axis=0), axis=0)
    # Re-rank within each race so positions are integers 1..N again
    out = np.zeros_like(mean_positions, dtype=float)
    for (season, rnd), _ in sorted_df.groupby(["season", "round"]):
        mask = (sorted_df["season"] == season) & (sorted_df["round"] == rnd)
        idx = np.where(mask.values)[0]
        sub = mean_positions[idx]
        out[idx] = (-(-sub)).argsort().argsort()[::-1] + 1
        # Actually simpler: just rank by mean position ascending (lower mean = better)
        out[idx] = sub.argsort().argsort() + 1
    return out


def run_walk_forward(df: pd.DataFrame, algorithm: str, config_name: str) -> dict:
    rounds = completed_2026_rounds(df)
    df = reweight_2026(df, weight_2026=2.5, wet_boost=6.0)  # Match baseline weight scheme

    quali_features = build_quali_feature_list(list(df.columns))
    race_features = build_race_feature_list(quali_features, list(df.columns))
    sprint_features = [c for c in race_features if c not in WEATHER_RACE_FEATURES]
    for sf in ["sprint_grid", "sprint_position", "sprint_points"]:
        if sf in df.columns and sf not in sprint_features:
            sprint_features.append(sf)
    for wcol in WEATHER_SPRINT_FEATURES:
        if wcol in df.columns and wcol not in sprint_features:
            sprint_features.append(wcol)

    all_results: dict[str, list] = {"quali": [], "race": [], "sprint": []}

    for N in rounds:
        is_wet = bool(
            df[(df["season"] == CURRENT_SEASON) & (df["round"] == N)]
            .get("weather_was_wet_race", pd.Series([0.0])).fillna(0.0).gt(0.5).any()
        )
        train_mask = (df["season"] < CURRENT_SEASON) | (
            (df["season"] == CURRENT_SEASON) & (df["round"] < N)
        )
        test_mask = (df["season"] == CURRENT_SEASON) & (df["round"] == N)

        # ---- Quali ----
        tr_q = df[train_mask & df["quali_position"].notna()].copy()
        te_q = df[test_mask & df["quali_position"].notna()].copy()
        if len(tr_q) >= 100 and len(te_q) >= 5:
            feats_avail = [c for c in quali_features if c in tr_q.columns]
            if algorithm == "lightgbm":
                m = train_lgbm(tr_q, feats_avail, "quali_position", LGBM_QUALI)
                preds, te_sorted = predict_positions(m, te_q, feats_avail)
            elif algorithm == "ensemble":
                m1 = train_xgb(tr_q, feats_avail, "quali_position", XGB_BEST_QUALI)
                m2 = train_lgbm(tr_q, feats_avail, "quali_position", LGBM_QUALI)
                p1, te_sorted = predict_positions(m1, te_q, feats_avail)
                p2, _ = predict_positions(m2, te_q, feats_avail)
                preds = average_positions(p1, p2, sorted_df=te_sorted)
            else:
                raise SystemExit(f"Unknown algorithm: {algorithm}")
            m = fold_metrics(preds, te_sorted["quali_position"].to_numpy())
            m.update(round=N, model="quali", is_wet=is_wet, train_n=len(tr_q), test_n=len(te_q))
            all_results["quali"].append(m)
            print(f"  R{N:>2} quali  MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}")

        # ---- Race ----
        tr_r = df[train_mask & df["finish_position"].notna()].copy()
        te_r = df[test_mask & df["finish_position"].notna()].copy()
        if len(tr_r) >= 100 and len(te_r) >= 5:
            feats_avail = [c for c in race_features if c in tr_r.columns]
            if algorithm == "lightgbm":
                m = train_lgbm(tr_r, feats_avail, "finish_position", LGBM_RACE)
                preds, te_sorted = predict_positions(m, te_r, feats_avail)
            elif algorithm == "ensemble":
                m1 = train_xgb(tr_r, feats_avail, "finish_position", XGB_BEST_RACE)
                m2 = train_lgbm(tr_r, feats_avail, "finish_position", LGBM_RACE)
                p1, te_sorted = predict_positions(m1, te_r, feats_avail)
                p2, _ = predict_positions(m2, te_r, feats_avail)
                preds = average_positions(p1, p2, sorted_df=te_sorted)
            m = fold_metrics(preds, te_sorted["finish_position"].to_numpy())
            m.update(round=N, model="race", is_wet=is_wet, train_n=len(tr_r), test_n=len(te_r))
            all_results["race"].append(m)
            print(f"  R{N:>2} race   MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}")

        # ---- Sprint ----
        if "sprint_position" in df.columns:
            tr_s = df[train_mask & df["sprint_position"].notna()].copy()
            te_s = df[test_mask & df["sprint_position"].notna()].copy()
            if len(tr_s) >= 60 and len(te_s) >= 5:
                feats_avail = [c for c in sprint_features if c in tr_s.columns]
                if algorithm == "lightgbm":
                    m = train_lgbm(tr_s, feats_avail, "sprint_position", LGBM_SPRINT)
                    preds, te_sorted = predict_positions(m, te_s, feats_avail)
                elif algorithm == "ensemble":
                    m1 = train_xgb(tr_s, feats_avail, "sprint_position", XGB_BEST_SPRINT)
                    m2 = train_lgbm(tr_s, feats_avail, "sprint_position", LGBM_SPRINT)
                    p1, te_sorted = predict_positions(m1, te_s, feats_avail)
                    p2, _ = predict_positions(m2, te_s, feats_avail)
                    preds = average_positions(p1, p2, sorted_df=te_sorted)
                m = fold_metrics(preds, te_sorted["sprint_position"].to_numpy())
                m.update(round=N, model="sprint", is_wet=is_wet, train_n=len(tr_s), test_n=len(te_s))
                all_results["sprint"].append(m)
                print(f"  R{N:>2} sprint MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}")

    summary = summarise(all_results)
    return {
        "config_name": config_name,
        "algorithm": algorithm,
        "folds": all_results,
        "summary": summary,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algorithm", choices=["lightgbm", "ensemble"], required=True)
    ap.add_argument("--config-name", required=True)
    args = ap.parse_args()

    np.random.seed(RNG_SEED)
    df = load_training_data()
    print(f"Training data: {len(df):,} rows | 2026 folds: {completed_2026_rounds(df)}\n")
    print(f"Running algorithm = {args.algorithm}, name = {args.config_name}\n")
    result = run_walk_forward(df, args.algorithm, args.config_name)
    out_path = EXPERIMENTS_DIR / f"{args.config_name}.json"
    out_path.write_text(json.dumps(result, indent=2, default=float))
    print(f"\nWrote {out_path}")
    print(json.dumps(result["summary"], indent=2, default=float))


if __name__ == "__main__":
    main()
