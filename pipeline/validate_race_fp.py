"""Walk-forward validator for race_fp_model (post-FP inference path).

The race_fp_model exists to handle the post-FP inference scenario: predictions
are needed for a race weekend BEFORE qualifying has happened, so the race
model has to consume a PREDICTED quali_position from the quali model rather
than the actual one. To eliminate the train/inference distribution shift,
race_fp_model is TRAINED on walk-forward predicted quali rather than actual.

This validator tests race_fp_model under its real inference protocol:

  For each test fold (Y, N):
    1. Use a precomputed walk-forward predicted quali for every historical row
       (one quali model per training season, trained on strict-past seasons,
       predicting that season — matches generate_walk_forward_quali_predictions
       in pipeline/05_train_models.py).
    2. Take training rows strictly before (Y, N).
    3. Override their `quali_position` with the WF predicted quali, then
       re-derive quali-dependent features (is_pole, is_front_row, etc.).
    4. Train race_fp_model on this modified training set.
    5. Override the test fold's quali_position with WF predicted quali too,
       re-derive features.
    6. Predict race position. Compare to actual.

This mirrors what happens at inference when the post-FP phase is the active
phase. Race_fp_model has been silently inheriting race_model's hyperparams
forever (they share make_race_model() in 05_train_models.py), but it has a
fundamentally different training distribution. This validator can isolate
whether it deserves its own tuning.

Outputs to data/experiments/{config_name}.json with the same schema as
validate_model_config.py so the multiple-testing analyzer works against it.
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CANCELLED_ROUNDS_2026, CURRENT_SEASON

# Import the existing validator's shared bits
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
DEFAULT_QUALI_PARAMS = _vmc.DEFAULT_QUALI_PARAMS
DEFAULT_RACE_PARAMS = _vmc.DEFAULT_RACE_PARAMS
EXPERIMENTS_DIR = _vmc.EXPERIMENTS_DIR
RNG_SEED = _vmc.RNG_SEED

# Re-derive quali-dependent features — import directly from 05_train_models
_spec2 = _ilu.spec_from_file_location("tm", PROJECT_ROOT / "pipeline" / "05_train_models.py")
_tm = _ilu.module_from_spec(_spec2)
sys.modules["tm"] = _tm
_spec2.loader.exec_module(_tm)
rederive_quali_dependent_features = _tm.rederive_quali_dependent_features


# ============================================================
# Walk-forward predicted quali — precomputed once
# ============================================================

def precompute_walk_forward_quali(
    df: pd.DataFrame, quali_params: dict, quali_features: list[str], verbose: bool = True
) -> pd.Series:
    """One predicted quali value per row, season-level walk-forward.

    Same recipe as pipeline/05_train_models.py::generate_walk_forward_quali_predictions
    but takes hyperparams as a dict so the validator can sweep them.

    Returns a Series aligned to df.index. First-season rows fall back to actual
    quali (no earlier data to train on).
    """
    available = [c for c in quali_features if c in df.columns]
    result = pd.Series(np.nan, index=df.index, dtype=float)
    seasons = sorted(df["season"].unique())

    first_mask = (df["season"] == seasons[0]) & df["quali_position"].notna()
    result.loc[first_mask] = df.loc[first_mask, "quali_position"].astype(float)
    if verbose:
        print(f"  Season {seasons[0]}: fell back to actual quali ({first_mask.sum()} rows)")

    for test_year in seasons[1:]:
        tr_mask = (df["season"] < test_year) & df["quali_position"].notna()
        te_mask = (df["season"] == test_year) & df["quali_position"].notna()
        tr_df = df[tr_mask].copy()
        te_df = df[te_mask].copy()
        if len(tr_df) < 50 or len(te_df) < 5:
            result.loc[te_mask] = df.loc[te_mask, "quali_position"].astype(float)
            if verbose:
                print(f"  Season {test_year}: insufficient train ({len(tr_df)}); fell back to actual")
            continue
        tr_df["_orig"] = tr_df.index
        te_df["_orig"] = te_df.index
        tr_sorted = sort_by_race_groups(tr_df)
        te_sorted = sort_by_race_groups(te_df)
        X_tr = tr_sorted[available].copy()
        y_tr = position_to_relevance(tr_sorted["quali_position"])
        qids = make_race_qids(tr_sorted)
        if "sample_weight" in tr_sorted.columns:
            w = tr_sorted["sample_weight"].to_numpy()
            grp_w = []
            prev = -1
            for i, q in enumerate(qids):
                if q != prev:
                    grp_w.append(w[i])
                    prev = q
            grp_w = np.asarray(grp_w, dtype=float)
        else:
            grp_w = None
        model = xgb.XGBRanker(**quali_params)
        model.fit(X_tr, y_tr, qid=qids, sample_weight=grp_w)
        scores = model.predict(te_sorted[available])
        positions = scores_to_positions(scores, te_sorted)
        for orig_idx, pos in zip(te_sorted["_orig"].values, positions):
            result.loc[orig_idx] = float(pos)
        actual = te_sorted["quali_position"].to_numpy()
        mae = float(np.mean(np.abs(actual - positions)))
        if verbose:
            print(f"  Season {test_year}: trained on {len(tr_sorted):,} rows, predicted {len(te_sorted):,}, WF MAE={mae:.3f}")

    return result


# ============================================================
# Per-fold race_fp train + predict
# ============================================================

def prepare_fp_dataset(df: pd.DataFrame, wf_quali: pd.Series, mask: pd.Series) -> pd.DataFrame:
    """Override quali_position with WF predicted quali on the masked subset,
    then re-derive quali-dependent features so the model sees a consistent
    distribution. Mirrors what 05_train_models.py does for race_fp_model.
    """
    sub = df[mask & wf_quali.notna() & df["finish_position"].notna()].copy()
    sub["quali_position"] = wf_quali.loc[sub.index].astype(float)
    sub = rederive_quali_dependent_features(sub, "quali_position")
    return sub


def run_walk_forward_fp(
    df: pd.DataFrame,
    config_name: str,
    quali_params: dict,
    race_fp_params: dict,
    weight_2026: float,
    wet_boost: float,
    test_from_year: int,
    algorithm: str = "xgboost",
    verbose: bool = True,
) -> dict[str, Any]:
    folds = completed_folds(df, test_from_year)
    if not folds:
        raise SystemExit(f"No folds from year {test_from_year}.")

    df = reweight_2026(df, weight_2026, wet_boost)

    quali_features = build_quali_feature_list(list(df.columns))
    race_features = build_race_feature_list(quali_features, list(df.columns))

    # Precompute once — WF quali for row R only depends on rows strictly
    # before R's season, so it's invariant to which fold we're validating.
    if verbose:
        print(f"\nPrecomputing walk-forward quali (one quali model per season)...")
    wf_quali = precompute_walk_forward_quali(df, quali_params, quali_features, verbose=verbose)
    if verbose:
        n_with_wf = int(wf_quali.notna().sum())
        print(f"  WF quali available for {n_with_wf:,} / {len(df):,} rows\n")

    all_results: dict[str, list[dict[str, Any]]] = {"race_fp": []}

    for Y, N in folds:
        is_wet = bool(
            df[(df["season"] == Y) & (df["round"] == N)]
            .get("weather_was_wet_race", pd.Series([0.0])).fillna(0.0).gt(0.5).any()
        )
        train_mask = (df["season"] < Y) | ((df["season"] == Y) & (df["round"] < N))
        test_mask = (df["season"] == Y) & (df["round"] == N)

        tr = prepare_fp_dataset(df, wf_quali, train_mask)
        te = prepare_fp_dataset(df, wf_quali, test_mask)
        if len(tr) < 100 or len(te) < 5:
            continue

        # Train race_fp model on WF-quali-overridden training set
        feats_avail = [c for c in race_features if c in tr.columns]
        tr_sorted = sort_by_race_groups(tr)
        te_sorted = sort_by_race_groups(te)
        qids = make_race_qids(tr_sorted)
        if algorithm == "catboost":
            # CatBoost YetiRank — mirrors validate_alt_algo_v2's CATBOOST_PARAMS
            # exactly so this is the SAME algorithm comparison, just under the
            # race_fp protocol (WF-predicted quali). Like that comparison, the
            # CatBoost path doesn't use per-group sample weights, so it's a
            # conservative test (the XGBoost baseline keeps its 2026 weighting).
            from catboost import CatBoost, Pool
            y = position_to_relevance(tr_sorted["finish_position"]).to_numpy()
            train_pool = Pool(tr_sorted[feats_avail].to_numpy(), label=y, group_id=qids)
            test_pool = Pool(te_sorted[feats_avail].to_numpy(), group_id=make_race_qids(te_sorted))
            cb = CatBoost(dict(loss_function="YetiRank", iterations=650, learning_rate=0.03,
                               depth=6, random_seed=RNG_SEED, verbose=False,
                               allow_writing_files=False))
            cb.fit(train_pool)
            scores = np.asarray(cb.predict(test_pool), dtype=float)
        else:
            X = tr_sorted[feats_avail].copy()
            y = position_to_relevance(tr_sorted["finish_position"])
            if "sample_weight" in tr_sorted.columns:
                w = tr_sorted["sample_weight"].to_numpy()
                gw = []
                prev = -1
                for i, q in enumerate(qids):
                    if q != prev:
                        gw.append(w[i])
                        prev = q
                gw = np.asarray(gw, dtype=float)
            else:
                gw = None
            model = xgb.XGBRanker(**race_fp_params)
            model.fit(X, y, qid=qids, sample_weight=gw)
            scores = model.predict(te_sorted[feats_avail])

        # Predict test fold (also WF-quali-overridden — consistent with train)
        preds = scores_to_positions(scores, te_sorted)
        m = fold_metrics(preds, te_sorted["finish_position"].to_numpy())
        m.update(season=Y, round=N, model="race_fp", is_wet=is_wet, train_n=len(tr), test_n=len(te))
        all_results["race_fp"].append(m)
        if verbose:
            print(f"  {Y} R{N:>2} race_fp MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}  (n_tr={len(tr):,})")

    summary = summarise(all_results)
    return {
        "config_name": config_name,
        "test_from_year": test_from_year,
        "model": "race_fp",
        "algorithm": algorithm,
        "weight_2026": weight_2026,
        "wet_boost": wet_boost,
        "quali_params": quali_params,
        "race_fp_params": race_fp_params,
        "folds": all_results,
        "summary": summary,
    }


def build_params(args: argparse.Namespace) -> tuple[dict, dict]:
    qp = deepcopy(DEFAULT_QUALI_PARAMS)
    rp = deepcopy(DEFAULT_RACE_PARAMS)
    for hp in ("n_estimators", "max_depth", "learning_rate", "min_child_weight",
               "subsample", "colsample_bytree", "reg_alpha", "reg_lambda", "objective"):
        v = getattr(args, f"race_fp_{hp}", None)
        if v is not None:
            if hp in {"n_estimators", "max_depth", "min_child_weight"}:
                rp[hp] = int(v)
            elif hp == "objective":
                rp[hp] = str(v)
            else:
                rp[hp] = float(v)
    return qp, rp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-name", required=True)
    ap.add_argument("--algorithm", choices=["xgboost", "catboost"], default="xgboost",
                    help="race_fp learner. catboost mirrors validate_alt_algo_v2's YetiRank config.")
    ap.add_argument("--test-from-year", type=int, default=CURRENT_SEASON)
    ap.add_argument("--weight-2026", type=float, default=2.5)
    ap.add_argument("--wet-boost", type=float, default=6.0)
    for hp in ("n_estimators", "max_depth", "learning_rate", "min_child_weight",
               "subsample", "colsample_bytree", "reg_alpha", "reg_lambda", "objective"):
        ap.add_argument(f"--race-fp-{hp.replace('_', '-')}", type=str, default=None)
    args = ap.parse_args()

    np.random.seed(RNG_SEED)
    df = load_training_data()
    print(f"Training data: {len(df):,} rows | seasons {sorted(df['season'].unique().tolist())}")
    folds = completed_folds(df, args.test_from_year)
    print(f"Test folds from {args.test_from_year}: {len(folds)} total")

    qp, rp = build_params(args)
    result = run_walk_forward_fp(
        df, args.config_name, qp, rp,
        weight_2026=args.weight_2026, wet_boost=args.wet_boost,
        test_from_year=args.test_from_year, algorithm=args.algorithm,
    )

    out_path = EXPERIMENTS_DIR / f"{args.config_name}.json"
    out_path.write_text(json.dumps(result, indent=2, default=float))
    print(f"\nWrote {out_path}")
    print(json.dumps(result["summary"], indent=2, default=float))


if __name__ == "__main__":
    main()
