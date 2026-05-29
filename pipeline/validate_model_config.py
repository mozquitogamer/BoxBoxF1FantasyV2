"""Walk-forward validator for model hyperparameter experiments.

For each completed 2026 round N (the "fold"):
  - Train on EVERY row strictly before round N (all 2020-2025 + 2026 rounds < N).
  - Predict round N. Compute position MAE, top-3 accuracy, Kendall's tau.

Aggregate across folds. Bootstrap 95% CI on the per-fold metric mean and on
paired deltas vs a baseline run.

Design principles
-----------------
- DETERMINISM. Fixed seed (42) at every stochastic surface (XGBoost, numpy).
- NO LEAKAGE. The wet-boost is applied AFTER the train/test split using the
  test fold's labels only as ground truth for evaluation, never during training.
  Weight overrides only affect 2026 train rows (round < N), never the test row.
- INDEPENDENT FROM 05_train_models.py. Reimplements the minimal training path
  here so a config change doesn't accidentally pollute production training.
- ONE LEVER AT A TIME. CLI is designed for OAT sweeps; combine with bash loops.

Outputs JSON to data/experiments/{config_name}.json with full fold-level metrics.

Examples
--------
    # Baseline (current production hyperparams)
    python pipeline/validate_model_config.py --config-name baseline

    # OAT: weight = 3.0
    python pipeline/validate_model_config.py \
        --config-name weight_3.0 --weight-2026 3.0

    # OAT: race depth = 4
    python pipeline/validate_model_config.py \
        --config-name race_depth_4 --race-max-depth 4

    # Compare two completed configs (paired bootstrap on per-fold deltas)
    python pipeline/validate_model_config.py --compare baseline weight_3.0
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import kendalltau

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    CANCELLED_ROUNDS_2026,
    CURRENT_SEASON,
    REGULATION_CHANGE_YEAR,
    TRAINING_DATA_DIR,
)

# Reuse the production feature-builders and ranking utilities — these define
# what the model actually sees. If they change in 05_train_models.py the
# validator picks the change up automatically (good — fold definitions stay
# tied to the production feature schema).
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "train_models_mod", PROJECT_ROOT / "pipeline" / "05_train_models.py"
)
_tm = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_tm)  # type: ignore[union-attr]

build_quali_feature_list = _tm.build_quali_feature_list
build_race_feature_list = _tm.build_race_feature_list
sort_by_race_groups = _tm.sort_by_race_groups
make_race_qids = _tm.make_race_qids
position_to_relevance = _tm.position_to_relevance
scores_to_positions = _tm.scores_to_positions
WEATHER_QUALI_FEATURES = _tm.WEATHER_QUALI_FEATURES
WEATHER_RACE_FEATURES = _tm.WEATHER_RACE_FEATURES
WEATHER_SPRINT_FEATURES = _tm.WEATHER_SPRINT_FEATURES
RACE_EXTRA_FEATURES = _tm.RACE_EXTRA_FEATURES
WET_TRAINING_WEIGHT_MULTIPLIER_DEFAULT = _tm.WET_TRAINING_WEIGHT_MULTIPLIER

RNG_SEED = 42
EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"
EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

TRAINING_DATA_PATH = TRAINING_DATA_DIR / "all_training_data.parquet"


# ============================================================
# Default model configs (current production)
# ============================================================

DEFAULT_QUALI_PARAMS: dict[str, Any] = dict(
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
    random_state=RNG_SEED,
    n_jobs=-1,
)

DEFAULT_RACE_PARAMS: dict[str, Any] = dict(
    n_estimators=650,
    learning_rate=0.03,
    max_depth=5,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=5,
    reg_alpha=0.1,
    reg_lambda=1.0,
    tree_method="hist",
    objective="rank:pairwise",
    random_state=RNG_SEED,
    n_jobs=-1,
)

DEFAULT_SPRINT_PARAMS: dict[str, Any] = dict(
    n_estimators=400,
    learning_rate=0.035,
    max_depth=4,
    subsample=0.80,
    colsample_bytree=0.80,
    min_child_weight=5,
    reg_alpha=0.2,
    reg_lambda=1.5,
    tree_method="hist",
    objective="rank:pairwise",
    random_state=RNG_SEED,
    n_jobs=-1,
)


@dataclass
class ModelConfig:
    name: str
    quali_params: dict[str, Any] = field(default_factory=lambda: deepcopy(DEFAULT_QUALI_PARAMS))
    race_params: dict[str, Any] = field(default_factory=lambda: deepcopy(DEFAULT_RACE_PARAMS))
    sprint_params: dict[str, Any] = field(default_factory=lambda: deepcopy(DEFAULT_SPRINT_PARAMS))
    weight_2026: float = 2.5
    wet_boost: float = float(WET_TRAINING_WEIGHT_MULTIPLIER_DEFAULT)


# ============================================================
# Data loading
# ============================================================

def load_training_data() -> pd.DataFrame:
    if not TRAINING_DATA_PATH.exists():
        raise SystemExit(
            f"Training data not found at {TRAINING_DATA_PATH}. "
            "Run pipeline/04_build_model_inputs.py first."
        )
    return pd.read_parquet(TRAINING_DATA_PATH)


def completed_2026_rounds(df: pd.DataFrame) -> list[int]:
    """Rounds where 2026 has a non-null finish_position (race actually run)."""
    cur = df[(df["season"] == CURRENT_SEASON) & df["finish_position"].notna()]
    rounds = sorted(int(r) for r in cur["round"].unique())
    return [r for r in rounds if r not in CANCELLED_ROUNDS_2026]


def completed_folds(df: pd.DataFrame, test_from_year: int) -> list[tuple[int, int]]:
    """Every (season, round) with a completed race from test_from_year onwards.

    These are the walk-forward TEST folds. For each fold (Y, N) the validator
    trains on every row with season < Y, or (season == Y AND round < N).

    We exclude any (year, round) marked cancelled (currently only 2026 R4/R5).
    """
    folds = []
    for season in sorted(df["season"].unique()):
        if season < test_from_year:
            continue
        season_df = df[(df["season"] == season) & df["finish_position"].notna()]
        for r in sorted(int(x) for x in season_df["round"].unique()):
            if season == CURRENT_SEASON and r in CANCELLED_ROUNDS_2026:
                continue
            folds.append((int(season), int(r)))
    return folds


def reweight_2026(df: pd.DataFrame, weight_2026: float, wet_boost: float) -> pd.DataFrame:
    """Recompute sample_weight in-place for an OAT weight experiment.

    Rule (mirrors 04_build_model_inputs.py but parameterised):
      - season < REGULATION_CHANGE_YEAR     → 1.0
      - REGULATION_CHANGE_YEAR <= season < CURRENT_SEASON → 2.5 (regulation-era base)
      - season == CURRENT_SEASON            → weight_2026
    Then multiply wet-race rows (weather_was_wet_race) by wet_boost.
    """
    df = df.copy()
    base = np.where(
        df["season"] == CURRENT_SEASON, weight_2026,
        np.where(df["season"] >= REGULATION_CHANGE_YEAR, 2.5, 1.0),
    ).astype(float)
    if "weather_was_wet_race" in df.columns:
        is_wet = (df["weather_was_wet_race"].fillna(0.0) > 0.5).astype(float)
        base = base * (1.0 + (wet_boost - 1.0) * is_wet)
    df["sample_weight"] = base
    return df


# ============================================================
# Single-fold train + predict
# ============================================================

def _group_weights_from_per_sample(qids: np.ndarray, per_sample_weights: np.ndarray) -> np.ndarray:
    out = []
    prev = -1
    for i, q in enumerate(qids):
        if q != prev:
            out.append(per_sample_weights[i])
            prev = q
    return np.asarray(out, dtype=float)


def train_one_ranker(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    xgb_params: dict[str, Any],
) -> tuple[xgb.XGBRanker, list[str]]:
    available = [c for c in feature_cols if c in train_df.columns]
    train_df = sort_by_race_groups(train_df)
    X = train_df[available].copy()
    y = position_to_relevance(train_df[target_col])
    qids = make_race_qids(train_df)
    w_per_sample = train_df["sample_weight"].to_numpy() if "sample_weight" in train_df.columns else None
    w_groups = _group_weights_from_per_sample(qids, w_per_sample) if w_per_sample is not None else None
    model = xgb.XGBRanker(**xgb_params)
    model.fit(X, y, qid=qids, sample_weight=w_groups)
    return model, available


def predict_one_fold(
    model: xgb.XGBRanker, test_df: pd.DataFrame, feature_cols: list[str]
) -> tuple[np.ndarray, pd.DataFrame]:
    """Predict positions for the test fold.

    Returns (predicted_positions, sorted_test_df). The caller should use the
    returned sorted_test_df for ground-truth alignment — sort_by_race_groups
    resets the index, so re-aligning to the original test_df order would lose
    the mapping. Returning both keeps the alignment trivial.
    """
    test_df_sorted = sort_by_race_groups(test_df)
    X_test = test_df_sorted[feature_cols].copy()
    scores = model.predict(X_test)
    positions = scores_to_positions(scores, test_df_sorted)
    return positions, test_df_sorted


# ============================================================
# Metrics
# ============================================================

def fold_metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    mask = ~(np.isnan(predicted) | np.isnan(actual))
    if mask.sum() < 5:
        return {"mae": float("nan"), "top3_acc": float("nan"), "kendall_tau": float("nan"), "n": int(mask.sum())}
    p = predicted[mask]
    a = actual[mask]
    mae = float(np.mean(np.abs(p - a)))
    # top-3 accuracy = fraction of actual top-3 finishers we put in our predicted top 3
    pred_top3 = set(np.argsort(p)[:3])
    actual_top3 = set(np.argsort(a)[:3])
    top3_acc = len(pred_top3 & actual_top3) / 3.0
    tau, _ = kendalltau(p, a)
    return {"mae": mae, "top3_acc": float(top3_acc), "kendall_tau": float(tau) if not np.isnan(tau) else 0.0, "n": int(mask.sum())}


# ============================================================
# Walk-forward driver
# ============================================================

def run_walk_forward(
    df: pd.DataFrame,
    config: ModelConfig,
    models_to_run: list[str],
    verbose: bool = True,
    test_from_year: int = CURRENT_SEASON,
) -> dict[str, Any]:
    """Walk-forward over every (season, round) from test_from_year onwards.

    For each fold (Y, N):
      - train_mask = (season < Y) OR (season == Y AND round < N)
      - test_mask  = (season == Y AND round == N)

    Default test_from_year = CURRENT_SEASON gives only 2026 folds (n=5 right
    now). Setting test_from_year=2022 gives n ≈ 75 folds across regulation
    seasons — needed for meaningful bootstrap CI power.
    """
    folds = completed_folds(df, test_from_year)
    if not folds:
        raise SystemExit(f"No completed folds found from year {test_from_year} onwards.")

    df = reweight_2026(df, config.weight_2026, config.wet_boost)

    quali_features = build_quali_feature_list(list(df.columns))
    race_features = build_race_feature_list(quali_features, list(df.columns))
    sprint_features = [c for c in race_features if c not in WEATHER_RACE_FEATURES]
    for sf in ["sprint_grid", "sprint_position", "sprint_points"]:
        if sf in df.columns and sf not in sprint_features:
            sprint_features.append(sf)
    for wcol in WEATHER_SPRINT_FEATURES:
        if wcol in df.columns and wcol not in sprint_features:
            sprint_features.append(wcol)

    all_results: dict[str, list[dict[str, Any]]] = {m: [] for m in models_to_run}

    for Y, N in folds:
        is_wet = bool(
            df[(df["season"] == Y) & (df["round"] == N)]
            .get("weather_was_wet_race", pd.Series([0.0]))
            .fillna(0.0)
            .gt(0.5)
            .any()
        )

        train_mask = (df["season"] < Y) | ((df["season"] == Y) & (df["round"] < N))
        test_mask = (df["season"] == Y) & (df["round"] == N)

        # ------ Quali ------
        if "quali" in models_to_run:
            tr = df[train_mask & df["quali_position"].notna()].copy()
            te = df[test_mask & df["quali_position"].notna()].copy()
            if len(tr) >= 100 and len(te) >= 5:
                model, used = train_one_ranker(tr, quali_features, "quali_position", config.quali_params)
                preds, te_sorted = predict_one_fold(model, te, used)
                m = fold_metrics(preds, te_sorted["quali_position"].to_numpy())
                m.update(season=Y, round=N, model="quali", is_wet=is_wet, train_n=len(tr), test_n=len(te))
                all_results["quali"].append(m)
                if verbose:
                    print(f"  {Y} R{N:>2} quali  MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}  (n_tr={len(tr):,})")

        # ------ Race ------
        if "race" in models_to_run:
            tr = df[train_mask & df["finish_position"].notna()].copy()
            te = df[test_mask & df["finish_position"].notna()].copy()
            if len(tr) >= 100 and len(te) >= 5:
                model, used = train_one_ranker(tr, race_features, "finish_position", config.race_params)
                preds, te_sorted = predict_one_fold(model, te, used)
                m = fold_metrics(preds, te_sorted["finish_position"].to_numpy())
                m.update(season=Y, round=N, model="race", is_wet=is_wet, train_n=len(tr), test_n=len(te))
                all_results["race"].append(m)
                if verbose:
                    print(f"  {Y} R{N:>2} race   MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}  (n_tr={len(tr):,})")

        # ------ Sprint (only on sprint weekends) ------
        if "sprint" in models_to_run and "sprint_position" in df.columns:
            tr = df[train_mask & df["sprint_position"].notna()].copy()
            te = df[test_mask & df["sprint_position"].notna()].copy()
            if len(tr) >= 60 and len(te) >= 5:
                model, used = train_one_ranker(tr, sprint_features, "sprint_position", config.sprint_params)
                preds, te_sorted = predict_one_fold(model, te, used)
                m = fold_metrics(preds, te_sorted["sprint_position"].to_numpy())
                m.update(season=Y, round=N, model="sprint", is_wet=is_wet, train_n=len(tr), test_n=len(te))
                all_results["sprint"].append(m)
                if verbose:
                    print(f"  {Y} R{N:>2} sprint MAE={m['mae']:.3f}  top3={m['top3_acc']:.2f}  tau={m['kendall_tau']:+.3f}  (n_tr={len(tr):,})")

    summary = summarise(all_results)
    return {
        "config_name": config.name,
        "test_from_year": test_from_year,
        "n_folds_attempted": len(folds),
        "weight_2026": config.weight_2026,
        "wet_boost": config.wet_boost,
        "quali_params": config.quali_params,
        "race_params": config.race_params,
        "sprint_params": config.sprint_params,
        "folds": all_results,
        "summary": summary,
    }


def summarise(folds: dict[str, list[dict]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model, rows in folds.items():
        if not rows:
            out[model] = None
            continue
        maes = np.array([r["mae"] for r in rows])
        top3 = np.array([r["top3_acc"] for r in rows])
        taus = np.array([r["kendall_tau"] for r in rows])
        wet_mask = np.array([r["is_wet"] for r in rows], dtype=bool)
        # Per-season stratification: when test_from_year < CURRENT_SEASON the
        # fold set spans many years and we want to see whether the result holds
        # uniformly or is driven by one outlier season.
        per_season: dict[str, dict[str, float]] = {}
        for row in rows:
            y = str(row.get("season", "?"))
            per_season.setdefault(y, {"maes": [], "wet": []})
            per_season[y]["maes"].append(row["mae"])
            per_season[y]["wet"].append(row["is_wet"])
        season_stats = {}
        for y, vals in sorted(per_season.items()):
            season_stats[y] = {
                "n_folds": len(vals["maes"]),
                "mae_mean": float(np.mean(vals["maes"])),
                "wet_folds": int(np.sum(vals["wet"])),
            }
        out[model] = {
            "n_folds": int(len(rows)),
            "mae_mean": float(np.mean(maes)),
            "mae_std": float(np.std(maes, ddof=1)) if len(maes) > 1 else 0.0,
            "mae_ci_95": _bootstrap_mean_ci(maes),
            "top3_mean": float(np.mean(top3)),
            "kendall_tau_mean": float(np.mean(taus)),
            "wet_folds": int(wet_mask.sum()),
            "wet_mae_mean": float(np.mean(maes[wet_mask])) if wet_mask.any() else None,
            "dry_mae_mean": float(np.mean(maes[~wet_mask])) if (~wet_mask).any() else None,
            "per_season": season_stats,
        }
    return out


def _bootstrap_mean_ci(values: np.ndarray, n_boot: int = 10_000, alpha: float = 0.05) -> tuple[float, float]:
    if len(values) < 2:
        return (float(values.mean()), float(values.mean()))
    rng = np.random.default_rng(RNG_SEED)
    boot = np.array([np.mean(rng.choice(values, size=len(values), replace=True)) for _ in range(n_boot)])
    return (float(np.quantile(boot, alpha / 2)), float(np.quantile(boot, 1 - alpha / 2)))


# ============================================================
# Compare two configs (paired bootstrap on per-fold deltas)
# ============================================================

def paired_compare(baseline_path: Path, candidate_path: Path) -> dict[str, Any]:
    """Paired bootstrap on (season, round) fold deltas.

    Backward compatible: rows produced before the multi-year refactor only
    have a "round" key (implicitly 2026). We fall back to that key shape.
    """
    base = json.loads(baseline_path.read_text())
    cand = json.loads(candidate_path.read_text())

    def _fold_key(r: dict) -> tuple[int, int]:
        return (int(r.get("season", CURRENT_SEASON)), int(r["round"]))

    out: dict[str, Any] = {"baseline": base["config_name"], "candidate": cand["config_name"], "models": {}}
    for model in ("quali", "race", "sprint", "race_fp"):
        b_rows = {_fold_key(r): r for r in base["folds"].get(model, [])}
        c_rows = {_fold_key(r): r for r in cand["folds"].get(model, [])}
        common = sorted(set(b_rows) & set(c_rows))
        if not common:
            out["models"][model] = None
            continue
        deltas = np.array([c_rows[k]["mae"] - b_rows[k]["mae"] for k in common])
        rng = np.random.default_rng(RNG_SEED)
        boot = np.array([np.mean(rng.choice(deltas, size=len(deltas), replace=True)) for _ in range(10_000)])
        ci = (float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975)))
        excludes_zero = (ci[1] < 0) or (ci[0] > 0)

        # Two-sided bootstrap p-value for "true mean delta == 0".
        # H0: mean delta = 0. p = 2 * min(P(boot_mean >= 0), P(boot_mean <= 0)),
        # clipped to [1/n_boot, 1.0]. Used by analyze_multiple_testing.py to
        # apply Bonferroni / Benjamini-Hochberg corrections across families of
        # sweeps. The upper-bound clip handles the identically-zero bootstrap
        # case (candidate == baseline → no-evidence → p=1, not 2).
        p_pos = float(np.mean(boot >= 0))
        p_neg = float(np.mean(boot <= 0))
        p_two_sided = min(max(2.0 * min(p_pos, p_neg), 1.0 / len(boot)), 1.0)

        # Per-season stratified delta — shows whether the improvement is uniform
        # or driven by a single year of folds.
        per_season_delta: dict[str, dict[str, float]] = {}
        for k in common:
            y = str(k[0])
            per_season_delta.setdefault(y, []).append(c_rows[k]["mae"] - b_rows[k]["mae"])
        season_delta_stats = {
            y: {
                "n_folds": len(v),
                "delta_mean": float(np.mean(v)),
                "baseline_mae_mean": float(np.mean([b_rows[(int(y), k[1])]["mae"] for k in common if k[0] == int(y)])),
                "candidate_mae_mean": float(np.mean([c_rows[(int(y), k[1])]["mae"] for k in common if k[0] == int(y)])),
            }
            for y, v in sorted(per_season_delta.items())
        }

        out["models"][model] = {
            "n_folds": len(common),
            "folds": [f"{k[0]}:{k[1]}" for k in common],
            "baseline_mae_mean": float(np.mean([b_rows[k]["mae"] for k in common])),
            "candidate_mae_mean": float(np.mean([c_rows[k]["mae"] for k in common])),
            "mae_delta_mean": float(np.mean(deltas)),
            "mae_delta_ci_95": ci,
            "p_value_uncorrected": p_two_sided,
            "excludes_zero": bool(excludes_zero),
            "direction": "candidate better" if np.mean(deltas) < 0 else "candidate worse",
            "verdict": _verdict(ci, np.mean(deltas)),
            "per_season": season_delta_stats,
        }
    return out


def _verdict(ci: tuple[float, float], delta_mean: float) -> str:
    if ci[1] < 0:
        return "STATISTICALLY BETTER (95% CI on improvement excludes zero)"
    if ci[0] > 0:
        return "STATISTICALLY WORSE (95% CI on regression excludes zero)"
    if delta_mean < 0:
        return "directional improvement (CI includes zero — not statistically significant)"
    return "no improvement"


# ============================================================
# CLI
# ============================================================

def build_config_from_args(args: argparse.Namespace) -> ModelConfig:
    config = ModelConfig(name=args.config_name)
    if args.weight_2026 is not None:
        config.weight_2026 = float(args.weight_2026)
    if args.wet_boost is not None:
        config.wet_boost = float(args.wet_boost)
    # Per-model overrides
    for model_key, params in [
        ("quali", config.quali_params),
        ("race", config.race_params),
        ("sprint", config.sprint_params),
    ]:
        for hp in ("n_estimators", "max_depth", "learning_rate", "min_child_weight",
                   "subsample", "colsample_bytree", "reg_alpha", "reg_lambda", "objective"):
            val = getattr(args, f"{model_key}_{hp}", None)
            if val is not None:
                # Cast to int where appropriate
                if hp in {"n_estimators", "max_depth", "min_child_weight"}:
                    params[hp] = int(val)
                elif hp == "objective":
                    params[hp] = str(val)
                else:
                    params[hp] = float(val)
    return config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-name", help="Name for output file (e.g. 'baseline', 'weight_3.0')")
    ap.add_argument("--models", default="quali,race,sprint",
                    help="Comma-separated list: quali,race,sprint")
    ap.add_argument("--test-from-year", type=int, default=CURRENT_SEASON,
                    help=f"First season to use as walk-forward test folds (default {CURRENT_SEASON}). "
                         "Set to 2022 for a multi-year fold set (~75 folds — much tighter CIs).")
    ap.add_argument("--weight-2026", type=float, help="2026 sample weight multiplier (default 2.5)")
    ap.add_argument("--wet-boost", type=float, help=f"Wet-row weight boost (default {WET_TRAINING_WEIGHT_MULTIPLIER_DEFAULT})")
    # Per-model hyperparam overrides
    for m in ("quali", "race", "sprint"):
        for hp in ("n_estimators", "max_depth", "learning_rate", "min_child_weight",
                   "subsample", "colsample_bytree", "reg_alpha", "reg_lambda", "objective"):
            ap.add_argument(f"--{m}-{hp.replace('_', '-')}", type=str, default=None)
    ap.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"),
                    help="Compare two existing result files (no training).")
    args = ap.parse_args()

    if args.compare:
        base = EXPERIMENTS_DIR / f"{args.compare[0]}.json"
        cand = EXPERIMENTS_DIR / f"{args.compare[1]}.json"
        if not base.exists() or not cand.exists():
            raise SystemExit(f"Need both {base} and {cand} to exist.")
        result = paired_compare(base, cand)
        out_path = EXPERIMENTS_DIR / f"compare_{args.compare[0]}_vs_{args.compare[1]}.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return

    if not args.config_name:
        raise SystemExit("--config-name required (or use --compare A B)")

    models_to_run = [m.strip() for m in args.models.split(",") if m.strip()]
    config = build_config_from_args(args)
    print(f"\n{'=' * 70}")
    print(f"Config: {config.name}")
    print(f"  weight_2026 = {config.weight_2026}   wet_boost = {config.wet_boost}")
    print(f"  models      = {models_to_run}")
    print(f"{'=' * 70}\n")

    np.random.seed(RNG_SEED)
    df = load_training_data()
    print(f"Training data: {len(df):,} rows, seasons {sorted(df['season'].unique().tolist())}")
    folds = completed_folds(df, args.test_from_year)
    print(f"Test folds (from year {args.test_from_year}): {len(folds)} total")
    if len(folds) <= 20:
        print(f"  {folds}")
    else:
        season_counts = {}
        for y, _ in folds:
            season_counts[y] = season_counts.get(y, 0) + 1
        print(f"  Per-season: {season_counts}")
    print()

    result = run_walk_forward(df, config, models_to_run, verbose=True, test_from_year=args.test_from_year)

    out_path = EXPERIMENTS_DIR / f"{config.name}.json"
    out_path.write_text(json.dumps(result, indent=2, default=float))
    print(f"\nWrote {out_path}")
    print("\nSummary:")
    print(json.dumps(result["summary"], indent=2, default=float))


if __name__ == "__main__":
    main()
