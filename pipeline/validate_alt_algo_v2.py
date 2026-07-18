"""Multi-year walk-forward validator for alternative algorithms.

Mirrors validate_model_config.py fold semantics exactly (same train/test splits
via completed_folds, same metrics, same per-season stratification, same output
schema so analyze_multiple_testing.py and --compare work against it). Uses the
CURRENT production XGBoost hyperparameters as the reference (NOT the reverted
"best" params), so the comparison is honest against what actually ships.

Algorithms:
  - catboost : CatBoost ranker with YetiRank loss (listwise, NDCG-family),
               group_id = race. CatBoost handles NaN natively like XGBoost.
  - randomforest : sklearn RandomForestRegressor on finish/quali POSITION
               directly (no native ranking), then rank within each race group.
               NaN is imputed to a sentinel since RF can't handle NaN; this is
               a known handicap vs the GBDTs and is reported honestly.

Usage:
    python pipeline/validate_alt_algo_v2.py --algorithm catboost \
        --config-name catboost_multiyear --test-from-year 2022 --models race
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CURRENT_SEASON

_spec = _ilu.spec_from_file_location("vmc", PROJECT_ROOT / "pipeline" / "validate_model_config.py")
_vmc = _ilu.module_from_spec(_spec)
sys.modules["vmc"] = _vmc
_spec.loader.exec_module(_vmc)

load_training_data = _vmc.load_training_data
completed_folds = _vmc.completed_folds
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

# CatBoost params chosen to roughly mirror the production race XGBoost
# (depth 5-ish, ~650 trees, similar LR) so it's an algorithm comparison, not
# a tuning comparison. YetiRank is CatBoost's listwise ranking loss.
CATBOOST_PARAMS = dict(
    loss_function="YetiRank",
    iterations=650,
    learning_rate=0.03,
    depth=6,
    random_seed=RNG_SEED,
    verbose=False,
    allow_writing_files=False,
)

RF_PARAMS = dict(
    n_estimators=500,
    max_depth=12,
    min_samples_leaf=3,
    random_state=RNG_SEED,
    n_jobs=-1,
)


def _group_sizes(qids: np.ndarray) -> list[int]:
    sizes, prev, count = [], -1, 0
    for q in qids:
        if q != prev:
            if prev != -1:
                sizes.append(count)
            prev, count = q, 1
        else:
            count += 1
    sizes.append(count)
    return sizes


def train_predict_catboost(tr, te, feats, target_col):
    from catboost import CatBoost, Pool
    tr = sort_by_race_groups(tr)
    te = sort_by_race_groups(te)
    # CatBoost group_id must be contiguous & sorted (it is, after sort).
    tr_qids = make_race_qids(tr)
    te_qids = make_race_qids(te)
    y = position_to_relevance(tr[target_col]).to_numpy()
    # Nullable pandas dtypes can emit scalar pd.NA objects from to_numpy(),
    # which CatBoost cannot coerce. Force a numeric float matrix so missing
    # values arrive as the native np.nan that CatBoost handles.
    X_tr = tr[feats].apply(pd.to_numeric, errors="coerce").to_numpy(
        dtype=float, na_value=np.nan
    )
    X_te = te[feats].apply(pd.to_numeric, errors="coerce").to_numpy(
        dtype=float, na_value=np.nan
    )
    train_pool = Pool(data=X_tr, label=y, group_id=tr_qids)
    test_pool = Pool(data=X_te, group_id=te_qids)
    model = CatBoost(CATBOOST_PARAMS)
    model.fit(train_pool)
    scores = model.predict(test_pool)
    positions = scores_to_positions(np.asarray(scores, dtype=float), te)
    return positions, te


def train_predict_rf(tr, te, feats, target_col):
    from sklearn.ensemble import RandomForestRegressor
    tr = sort_by_race_groups(tr)
    te = sort_by_race_groups(te)
    # RF can't handle NaN — impute with a sentinel (-1). This is a real
    # handicap vs the GBDTs (which split on NaN natively) and is reported.
    X_tr = tr[feats].fillna(-1.0).to_numpy()
    X_te = te[feats].fillna(-1.0).to_numpy()
    # Regress position directly; lower predicted value = better grid slot.
    y = tr[target_col].to_numpy(dtype=float)
    w = tr["sample_weight"].to_numpy() if "sample_weight" in tr.columns else None
    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(X_tr, y, sample_weight=w)
    pred_raw = model.predict(X_te)
    # Lower predicted position = better, so invert into a "score" for the
    # shared scores_to_positions (which treats higher score = better).
    positions = scores_to_positions(-pred_raw, te)
    return positions, te


def run(
    df,
    algorithm,
    config_name,
    test_from_year,
    weight_2026=2.5,
    wet_boost=6.0,
    verbose=True,
    models=("quali", "race", "sprint"),
):
    folds = completed_folds(df, test_from_year)
    df = reweight_2026(df, weight_2026, wet_boost)
    quali_features = build_quali_feature_list(list(df.columns))
    race_features = build_race_feature_list(quali_features, list(df.columns))
    sprint_features = [c for c in race_features if c not in WEATHER_RACE_FEATURES]
    for sf in ["sprint_grid", "sprint_position", "sprint_points"]:
        if sf in df.columns and sf not in sprint_features:
            sprint_features.append(sf)
    for wcol in WEATHER_SPRINT_FEATURES:
        if wcol in df.columns and wcol not in sprint_features:
            sprint_features.append(wcol)

    trainer = {"catboost": train_predict_catboost, "randomforest": train_predict_rf}[algorithm]
    all_results: dict[str, list[dict[str, Any]]] = {"quali": [], "race": [], "sprint": []}

    for Y, N in folds:
        is_wet = bool(
            df[(df["season"] == Y) & (df["round"] == N)]
            .get("weather_was_wet_race", pd.Series([0.0])).fillna(0.0).gt(0.5).any()
        )
        train_mask = (df["season"] < Y) | ((df["season"] == Y) & (df["round"] < N))
        test_mask = (df["season"] == Y) & (df["round"] == N)

        for model_name, target, feats_all, min_tr in [
            ("quali", "quali_position", quali_features, 100),
            ("race", "finish_position", race_features, 100),
            ("sprint", "sprint_position", sprint_features, 60),
        ]:
            if model_name not in models:
                continue
            if target not in df.columns:
                continue
            tr = df[train_mask & df[target].notna()].copy()
            te = df[test_mask & df[target].notna()].copy()
            if len(tr) < min_tr or len(te) < 5:
                continue
            feats = [c for c in feats_all if c in tr.columns]
            preds, te_sorted = trainer(tr, te, feats, target)
            m = fold_metrics(preds, te_sorted[target].to_numpy())
            m.update(season=Y, round=N, model=model_name, is_wet=is_wet, train_n=len(tr), test_n=len(te))
            all_results[model_name].append(m)
            if verbose:
                print(f"  {Y} R{N:>2} {model_name:<6} MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}")

    return {
        "config_name": config_name,
        "test_from_year": test_from_year,
        "algorithm": algorithm,
        "folds": all_results,
        "summary": summarise(all_results),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algorithm", choices=["catboost", "randomforest"], required=True)
    ap.add_argument("--config-name", required=True)
    ap.add_argument("--test-from-year", type=int, default=CURRENT_SEASON)
    ap.add_argument(
        "--models",
        default="quali,race,sprint",
        help="Comma-separated subset: quali,race,sprint (default: all)",
    )
    args = ap.parse_args()

    models = tuple(m.strip() for m in args.models.split(",") if m.strip())
    unknown = sorted(set(models) - {"quali", "race", "sprint"})
    if not models or unknown:
        raise SystemExit(f"Invalid --models selection: {args.models!r}")

    np.random.seed(RNG_SEED)
    df = load_training_data()
    folds = completed_folds(df, args.test_from_year)
    print(f"Training data: {len(df):,} rows | {len(folds)} folds from {args.test_from_year}")
    print(f"Algorithm: {args.algorithm}\n")
    result = run(
        df,
        args.algorithm,
        args.config_name,
        args.test_from_year,
        models=models,
    )
    out_path = EXPERIMENTS_DIR / f"{args.config_name}.json"
    out_path.write_text(json.dumps(result, indent=2, default=float))
    print(f"\nWrote {out_path}")
    print(json.dumps(result["summary"], indent=2, default=float))


if __name__ == "__main__":
    main()
