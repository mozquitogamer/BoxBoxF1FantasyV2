"""Strict event-prequential evaluation for the 2026 ranking models.

This is the trustworthy experiment harness.  Every evaluated 2026 event is
trained from rows belonging to strictly earlier events:

    train = (season < target_season) OR
            (season == target_season AND round < target_round)

The harness deliberately does not retrain or overwrite production models.
It writes an immutable, provenance-rich experiment bundle containing:

* ``manifest.json`` -- dataset/source/config hashes, exact features and filters
* ``fold_metrics.json`` -- one row per model/event
* ``paired_predictions.csv`` -- driver-level rows keyed by race cluster
* ``result.json`` -- manifest, fold metrics and aggregate summaries

``race_fp`` uses event-prequential qualifying predictions for both its
historical training rows and its test event.  No row is allowed to use its
actual qualifying result as an input to that model.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (  # noqa: E402
    CANCELLED_ROUNDS_2026,
    CURRENT_SEASON,
    MODEL_RANDOM_STATE,
    REGULATION_WEIGHT_MULTIPLIER,
    TRAINING_DATA_DIR,
)


def _load_training_helpers():
    """Load production feature/filter helpers despite the numeric filename."""
    path = PROJECT_ROOT / "pipeline" / "05_train_models.py"
    spec = importlib.util.spec_from_file_location("prequential_train_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import production helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_tm = _load_training_helpers()
build_quali_feature_list = _tm.build_quali_feature_list
build_race_feature_list = _tm.build_race_feature_list
classified_finisher_mask = _tm.classified_finisher_mask
make_race_qids = _tm.make_race_qids
position_to_relevance = _tm.position_to_relevance
rederive_quali_dependent_features = _tm.rederive_quali_dependent_features
scores_to_positions = _tm.scores_to_positions
sort_by_race_groups = _tm.sort_by_race_groups

DEFAULT_XGB_QUALI: dict[str, Any] = {
    "n_estimators": 1200,
    "learning_rate": 0.025,
    "max_depth": 3,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 3,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "tree_method": "hist",
    "objective": "rank:pairwise",
    "random_state": MODEL_RANDOM_STATE,
    "n_jobs": -1,
}
DEFAULT_XGB_RACE: dict[str, Any] = {
    "n_estimators": 650,
    "learning_rate": 0.03,
    "max_depth": 5,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "tree_method": "hist",
    "objective": "rank:pairwise",
    "random_state": MODEL_RANDOM_STATE,
    "n_jobs": -1,
}
DEFAULT_CATBOOST_RACE: dict[str, Any] = {
    "loss_function": "YetiRank",
    "iterations": 650,
    "learning_rate": 0.03,
    "depth": 6,
    "random_seed": MODEL_RANDOM_STATE,
    "verbose": False,
    "allow_writing_files": False,
}

MODEL_WEIGHTS = {"quali": 0.30, "race": 0.25, "race_fp": 0.45}
SESSION_WET_COLUMN = {
    "quali": "weather_was_wet_quali",
    "race": "weather_was_wet_race",
    "race_fp": "weather_was_wet_race",
}


@dataclass
class EvaluationConfig:
    name: str
    models: list[str] = field(
        default_factory=lambda: ["quali", "race", "race_fp"]
    )
    algorithm: str = "xgboost"
    current_season_weight: float = REGULATION_WEIGHT_MULTIPLIER
    wet_weight: float = 6.0
    recency_decay: float = 0.90
    min_train_events: int = 10
    min_train_rows: int = 100
    first_round: int | None = None
    last_round: int | None = None
    allow_oracle_weather: bool = False
    drop_features: list[str] = field(default_factory=list)
    drop_prefixes: list[str] = field(default_factory=list)
    quali_params: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_XGB_QUALI)
    )
    race_params: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_XGB_RACE)
    )
    catboost_race_params: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_CATBOOST_RACE)
    )


def event_before(df: pd.DataFrame, season: int, round_num: int) -> pd.Series:
    """Boolean mask containing only events strictly before the target event."""
    return (df["season"] < season) | (
        (df["season"] == season) & (df["round"] < round_num)
    )


def event_mask(df: pd.DataFrame, season: int, round_num: int) -> pd.Series:
    return (df["season"] == season) & (df["round"] == round_num)


def event_keys(df: pd.DataFrame, target_non_null: str) -> list[tuple[int, int]]:
    observed = df[df[target_non_null].notna()][["season", "round"]].drop_duplicates()
    return sorted((int(y), int(r)) for y, r in observed.itertuples(index=False))


def completed_2026_events(df: pd.DataFrame, config: EvaluationConfig) -> list[tuple[int, int]]:
    cur = df[
        (df["season"] == CURRENT_SEASON)
        & df["finish_position"].notna()
        & ~df["round"].isin(CANCELLED_ROUNDS_2026)
    ]
    rounds = sorted(int(r) for r in cur["round"].unique())
    if config.first_round is not None:
        rounds = [r for r in rounds if r >= config.first_round]
    if config.last_round is not None:
        rounds = [r for r in rounds if r <= config.last_round]
    return [(CURRENT_SEASON, r) for r in rounds]


def _drop_features(features: Iterable[str], config: EvaluationConfig) -> list[str]:
    exact = set(config.drop_features)
    return [
        feature
        for feature in features
        if feature not in exact
        and not any(feature.startswith(prefix) for prefix in config.drop_prefixes)
    ]


def build_feature_sets(
    df: pd.DataFrame, config: EvaluationConfig
) -> dict[str, list[str]]:
    quali = _drop_features(
        build_quali_feature_list(
            list(df.columns), include_weather=config.allow_oracle_weather
        ),
        config,
    )
    race = _drop_features(
        build_race_feature_list(
            quali,
            list(df.columns),
            include_weather=config.allow_oracle_weather,
        ),
        config,
    )
    if not config.allow_oracle_weather:
        # The training parquet stores observed session weather. At a historical
        # Fantasy lock that is future information unless a timestamped forecast
        # archive is substituted. Keep the trustworthy default non-oracular.
        quali = [feature for feature in quali if not feature.startswith("weather_")]
        race = [feature for feature in race if not feature.startswith("weather_")]
    return {"quali": quali, "race": race, "race_fp": list(race)}


def apply_training_weights(
    df: pd.DataFrame,
    model_name: str,
    current_season_weight: float,
    wet_weight: float,
) -> pd.DataFrame:
    """Create production-intent event-constant weights for one model.

    Ranking libraries attach weights to query groups, not individual drivers.
    Season and session wetness are therefore reduced to one constant per event.
    A disagreement within an event is rejected rather than silently assigning
    different importance to members of the same ranking query.
    """
    out = df.copy()
    out["sample_weight"] = np.where(
        out["season"] == CURRENT_SEASON, current_season_weight, 1.0
    ).astype(float)
    wet_col = SESSION_WET_COLUMN[model_name]
    if wet_col in out.columns:
        wet = out[wet_col].fillna(0.0).gt(0.5)
        wet_nunique = wet.groupby([out["season"], out["round"]]).nunique()
        if bool((wet_nunique > 1).any()):
            bad = wet_nunique[wet_nunique > 1].index.tolist()
            raise ValueError(f"{wet_col} is inconsistent within events: {bad[:5]}")
        out.loc[wet, "sample_weight"] *= wet_weight
    return out


def group_weights(
    sorted_df: pd.DataFrame, per_row_weights: np.ndarray
) -> np.ndarray:
    """Convert event-constant row weights to XGBoost query weights."""
    if len(sorted_df) != len(per_row_weights):
        raise ValueError("Weight vector length does not match training rows")
    frame = sorted_df[["season", "round"]].copy()
    frame["_weight"] = np.asarray(per_row_weights, dtype=float)
    nunique = frame.groupby(["season", "round"])["_weight"].nunique(dropna=False)
    if bool((nunique != 1).any()):
        bad = nunique[nunique != 1].index.tolist()
        raise ValueError(f"Sample weights differ inside ranking groups: {bad[:5]}")
    return (
        frame.groupby(["season", "round"], sort=False)["_weight"]
        .first()
        .to_numpy(dtype=float)
    )


def _clean_matrix(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    available = [feature for feature in features if feature in df.columns]
    return df[available].replace([np.inf, -np.inf], np.nan)


def train_ranker(
    train_df: pd.DataFrame,
    features: list[str],
    target: str,
    algorithm: str,
    params: dict[str, Any],
):
    """Fit one ranker and return ``(model, exact_feature_order)``."""
    ordered = sort_by_race_groups(train_df)
    available = [feature for feature in features if feature in ordered.columns]
    if not available:
        raise ValueError("No requested features exist in the training data")
    X = _clean_matrix(ordered, available)
    y = position_to_relevance(ordered[target]).to_numpy(dtype=float)
    qids = make_race_qids(ordered)
    row_weights = ordered["sample_weight"].to_numpy(dtype=float)

    if algorithm == "xgboost":
        import xgboost as xgb

        model = xgb.XGBRanker(**params)
        model.fit(
            X,
            y,
            qid=qids,
            sample_weight=group_weights(ordered, row_weights),
        )
    elif algorithm == "catboost":
        from catboost import CatBoost, Pool

        pool = Pool(
            data=X,
            label=y,
            group_id=qids,
            group_weight=row_weights,
        )
        model = CatBoost(params)
        model.fit(pool)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    return model, available


def predict_event(
    model, test_df: pd.DataFrame, features: list[str]
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    ordered = sort_by_race_groups(test_df)
    scores = np.asarray(model.predict(_clean_matrix(ordered, features)), dtype=float)
    positions = scores_to_positions(scores, ordered)
    return ordered, scores, positions


def calculate_metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    predicted = np.asarray(predicted, dtype=float)
    actual = np.asarray(actual, dtype=float)
    valid = np.isfinite(predicted) & np.isfinite(actual)
    if int(valid.sum()) < 2:
        return {
            "mae": float("nan"),
            "kendall_tau": float("nan"),
            "spearman_rho": float("nan"),
        }
    pred = predicted[valid]
    truth = actual[valid]
    tau = kendalltau(pred, truth).statistic
    rho = spearmanr(pred, truth).statistic
    return {
        "mae": float(np.mean(np.abs(pred - truth))),
        "kendall_tau": float(tau),
        "spearman_rho": float(rho),
    }


def precompute_event_prequential_quali(
    df: pd.DataFrame,
    features: list[str],
    config: EvaluationConfig,
    *,
    verbose: bool = True,
    target_scope: str = "all",
) -> pd.Series:
    """Predict qualifying events from strict-prior data for one target scope.

    ``history`` predicts only target events before ``CURRENT_SEASON``. Those
    predictions cannot depend on the current-season weight and are reusable
    across its sweeps. ``current`` predicts only current-season targets.
    """
    if target_scope not in {"all", "history", "current"}:
        raise ValueError(f"Unknown qualifying target scope: {target_scope}")
    result = pd.Series(np.nan, index=df.index, dtype=float)
    keys = event_keys(df, "quali_position")
    for position, (year, round_num) in enumerate(keys):
        if target_scope == "history" and year >= CURRENT_SEASON:
            continue
        if target_scope == "current" and year != CURRENT_SEASON:
            continue
        prior = event_before(df, year, round_num) & df["quali_position"].notna()
        test = event_mask(df, year, round_num) & df["quali_position"].notna()
        prior_events = df.loc[prior, ["season", "round"]].drop_duplicates()
        if (
            len(prior_events) < config.min_train_events
            or int(prior.sum()) < config.min_train_rows
            or int(test.sum()) < 2
        ):
            continue
        train_df = apply_training_weights(
            df.loc[prior],
            "quali",
            config.current_season_weight,
            config.wet_weight,
        )
        model, used = train_ranker(
            train_df,
            features,
            "quali_position",
            "xgboost",
            config.quali_params,
        )
        test_df = df.loc[test].copy()
        # Preserve original row identity across the production helper's
        # sort/reset_index. Never rely on tied sort keys preserving driver order.
        test_df["_prequential_source_index"] = test_df.index
        ordered, _, predicted = predict_event(model, test_df, used)
        result.loc[ordered["_prequential_source_index"].to_numpy()] = predicted
        if verbose and (position % 20 == 0 or year == CURRENT_SEASON):
            print(
                f"  auxiliary quali {year} R{round_num}: "
                f"{len(prior_events)} prior events, {len(ordered)} predictions"
            )
    return result


def _eligible_rows(
    df: pd.DataFrame,
    model_name: str,
    mask: pd.Series,
    prequential_quali: pd.Series | None,
) -> pd.DataFrame:
    if model_name == "quali":
        return df.loc[mask & df["quali_position"].notna()].copy()
    finishers = classified_finisher_mask(df)
    sub_mask = mask & finishers
    if model_name == "race":
        return df.loc[sub_mask].copy()
    if prequential_quali is None:
        raise ValueError("race_fp requires event-prequential qualifying predictions")
    sub_mask = sub_mask & prequential_quali.notna()
    out = df.loc[sub_mask].copy()
    out["quali_position"] = prequential_quali.loc[out.index].to_numpy(dtype=float)
    return rederive_quali_dependent_features(out, "quali_position")


def evaluate(
    df: pd.DataFrame,
    config: EvaluationConfig,
    *,
    verbose: bool = True,
    precomputed_quali: pd.Series | None = None,
) -> tuple[list[dict[str, Any]], pd.DataFrame, dict[str, list[str]]]:
    """Run all requested 2026 folds without writing any production artifacts."""
    unknown = set(config.models) - {"quali", "race", "race_fp"}
    if unknown:
        raise ValueError(f"Unsupported models: {sorted(unknown)}")
    features = build_feature_sets(df, config)
    targets = completed_2026_events(df, config)
    if not targets:
        raise ValueError("No completed 2026 target events in the requested range")

    prequential_quali: pd.Series | None = precomputed_quali
    if "race_fp" in config.models:
        if prequential_quali is None:
            if verbose:
                print("Precomputing strict event-prequential qualifying inputs...")
            prequential_quali = precompute_event_prequential_quali(
                df, features["quali"], config, verbose=verbose
            )
        elif not prequential_quali.index.equals(df.index):
            raise ValueError("Cached qualifying predictions do not align to dataset index")

    fold_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for year, round_num in targets:
        prior = event_before(df, year, round_num)
        target = event_mask(df, year, round_num)
        for model_name in config.models:
            train_df = _eligible_rows(
                df, model_name, prior, prequential_quali
            )
            test_df = _eligible_rows(
                df, model_name, target, prequential_quali
            )
            n_events = len(train_df[["season", "round"]].drop_duplicates())
            if n_events < config.min_train_events or len(train_df) < config.min_train_rows:
                continue
            if len(test_df) < 2:
                continue
            train_df = apply_training_weights(
                train_df,
                model_name,
                config.current_season_weight,
                config.wet_weight,
            )
            target_col = "quali_position" if model_name == "quali" else "finish_position"
            algorithm = "xgboost" if model_name == "quali" else config.algorithm
            if algorithm == "catboost":
                params = config.catboost_race_params
            else:
                params = (
                    config.quali_params
                    if model_name == "quali"
                    else config.race_params
                )
            model, used = train_ranker(
                train_df, features[model_name], target_col, algorithm, params
            )
            ordered, scores, predicted = predict_event(model, test_df, used)
            actual = ordered[target_col].to_numpy(dtype=float)
            metrics = calculate_metrics(predicted, actual)
            cluster_id = f"{year}-R{round_num:02d}"
            phase = {
                "quali": "post_fp_quali",
                "race": "post_quali_race",
                "race_fp": "post_fp_race",
            }[model_name]
            fold = {
                "cluster_id": cluster_id,
                "season": year,
                "round": round_num,
                "model": model_name,
                "phase": phase,
                "algorithm": algorithm,
                "train_events": n_events,
                "train_rows": len(train_df),
                "test_rows": len(ordered),
                **metrics,
            }
            fold_rows.append(fold)
            for i, row in ordered.reset_index(drop=True).iterrows():
                prediction_rows.append(
                    {
                        "cluster_id": cluster_id,
                        "season": year,
                        "round": round_num,
                        "model": model_name,
                        "phase": fold["phase"],
                        "algorithm": algorithm,
                        "driver_id": str(row["driver_id"]),
                        "actual_position": float(actual[i]),
                        "predicted_position": float(predicted[i]),
                        "raw_score": float(scores[i]),
                        "absolute_error": float(abs(predicted[i] - actual[i])),
                    }
                )
            if verbose:
                print(
                    f"{cluster_id} {model_name:7s} "
                    f"MAE={metrics['mae']:.3f} "
                    f"tau={metrics['kendall_tau']:+.3f} "
                    f"train={len(train_df):,}/{n_events} events"
                )
    return fold_rows, pd.DataFrame(prediction_rows), features


def summarize(
    fold_rows: list[dict[str, Any]],
    recency_decay: float,
    model_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate event metrics and a recency-weighted 2026-primary score."""
    if not 0 < recency_decay <= 1:
        raise ValueError("recency_decay must be in (0, 1]")
    model_weights = model_weights or MODEL_WEIGHTS
    rows = pd.DataFrame(fold_rows)
    by_model: dict[str, dict[str, Any]] = {}
    weighted_components: list[tuple[float, float]] = []
    for model_name, group in rows.groupby("model", sort=True):
        group = group.sort_values(["season", "round"]).copy()
        ages = np.arange(len(group) - 1, -1, -1)
        weights = np.power(recency_decay, ages)
        recency_mae = float(np.average(group["mae"], weights=weights))
        recency_tau = float(np.average(group["kendall_tau"], weights=weights))
        by_model[model_name] = {
            "folds": int(len(group)),
            "mae_mean": float(group["mae"].mean()),
            "mae_recency_weighted": recency_mae,
            "kendall_tau_mean": float(group["kendall_tau"].mean()),
            "kendall_tau_recency_weighted": recency_tau,
            "spearman_rho_mean": float(group["spearman_rho"].mean()),
            "latest_round": int(group["round"].max()),
        }
        importance = float(model_weights.get(model_name, 0.0))
        if importance > 0:
            weighted_components.append((recency_mae, importance))
    importance_total = sum(weight for _, weight in weighted_components)
    primary = (
        sum(value * weight for value, weight in weighted_components)
        / importance_total
        if importance_total
        else float("nan")
    )
    return {
        "by_model": by_model,
        "primary_2026": {
            "metric": "recency-weighted MAE; lower is better",
            "score": float(primary),
            "recency_decay": recency_decay,
            "model_weights_used": {
                name: model_weights[name]
                for name in by_model
                if name in model_weights
            },
            "note": (
                "All test folds are 2026. race_fp receives the largest default "
                "weight because it is the actionable pre-qualifying race forecast."
            ),
        },
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def quali_cache_identity(
    dataset_sha256: str,
    config: EvaluationConfig,
    quali_features: list[str],
    *,
    layer: str,
    history_identity: str | None = None,
) -> str:
    """Content identity for one layer of the auxiliary qualifying sequence."""
    if layer not in {"history", "current"}:
        raise ValueError(f"Unknown qualifying cache layer: {layer}")
    payload = {
        "schema_version": 2,
        "layer": layer,
        "dataset_sha256": dataset_sha256,
        "evaluator_source_sha256": sha256_file(Path(__file__).resolve()),
        "training_helper_sha256": sha256_file(
            PROJECT_ROOT / "pipeline" / "05_train_models.py"
        ),
        "quali_features": quali_features,
        "quali_params": config.quali_params,
        "wet_weight": config.wet_weight,
        "min_train_events": config.min_train_events,
        "min_train_rows": config.min_train_rows,
        "allow_oracle_weather": config.allow_oracle_weather,
    }
    if layer == "current":
        if history_identity is None:
            raise ValueError("Current qualifying cache requires its history identity")
        payload.update(
            {
                "history_identity_sha256": history_identity,
                "current_season_weight": config.current_season_weight,
            }
        )
    return canonical_hash(payload)


def combine_quali_layers(
    history: pd.Series, current: pd.Series, expected_index: pd.Index
) -> pd.Series:
    """Combine disjoint historical/current caches with strict alignment checks."""
    if not history.index.equals(expected_index) or not current.index.equals(expected_index):
        raise ValueError("Layered qualifying cache index mismatch")
    overlap = history.notna() & current.notna()
    if bool(overlap.any()):
        raise ValueError("Historical and current qualifying caches overlap")
    return history.combine_first(current)


def _read_quali_layer(path: Path, df_index: pd.Index) -> pd.Series:
    cached = pd.read_parquet(path)
    expected = {"source_index", "predicted_quali_position"}
    if not expected.issubset(cached.columns):
        raise ValueError(f"Malformed qualifying cache: {path}")
    if cached["source_index"].tolist() != df_index.tolist():
        raise ValueError(f"Qualifying cache index mismatch: {path}")
    return pd.Series(
        cached["predicted_quali_position"].to_numpy(dtype=float),
        index=df_index,
    )


def _write_quali_layer(path: Path, series: pd.Series) -> None:
    pd.DataFrame(
        {
            "source_index": series.index.to_numpy(),
            "predicted_quali_position": series.to_numpy(dtype=float),
        }
    ).to_parquet(path, index=False)


def load_or_build_quali_cache(
    df: pd.DataFrame,
    dataset_sha256: str,
    config: EvaluationConfig,
    quali_features: list[str],
    cache_root: Path,
    *,
    verbose: bool = True,
) -> tuple[pd.Series, dict[str, Any]]:
    """Load/build weight-independent history plus weight-specific 2026 layers."""
    cache_root.mkdir(parents=True, exist_ok=True)
    history_identity = quali_cache_identity(
        dataset_sha256, config, quali_features, layer="history"
    )
    history_path = (
        cache_root
        / f"event_prequential_quali_history__{history_identity[:16]}.parquet"
    )
    history_hit = history_path.exists()
    if history_hit:
        history = _read_quali_layer(history_path, df.index)
        if verbose:
            print(f"Reusing weight-independent qualifying history: {history_path}")
    else:
        if verbose:
            print("Building weight-independent pre-2026 qualifying history...")
        history = precompute_event_prequential_quali(
            df,
            quali_features,
            config,
            verbose=verbose,
            target_scope="history",
        )
        _write_quali_layer(history_path, history)

    current_identity = quali_cache_identity(
        dataset_sha256,
        config,
        quali_features,
        layer="current",
        history_identity=history_identity,
    )
    current_path = (
        cache_root
        / f"event_prequential_quali_current_{CURRENT_SEASON}"
        f"__{current_identity[:16]}.parquet"
    )
    current_hit = current_path.exists()
    if current_hit:
        current = _read_quali_layer(current_path, df.index)
        if verbose:
            print(f"Reusing weight-specific {CURRENT_SEASON} qualifying layer: {current_path}")
    else:
        if verbose:
            print(f"Building weight-specific {CURRENT_SEASON} qualifying layer...")
        current = precompute_event_prequential_quali(
            df,
            quali_features,
            config,
            verbose=verbose,
            target_scope="current",
        )
        _write_quali_layer(current_path, current)

    combined = combine_quali_layers(history, current, df.index)
    return combined, {
        "strategy": "history_plus_current_season",
        "history": {
            "identity_sha256": history_identity,
            "path": str(history_path),
            "hit": history_hit,
            "independent_of_current_season_weight": True,
        },
        "current": {
            "season": CURRENT_SEASON,
            "identity_sha256": current_identity,
            "path": str(current_path),
            "hit": current_hit,
            "current_season_weight": config.current_season_weight,
        },
    }


def git_state() -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"sha": sha, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}


def build_manifest(
    dataset_path: Path,
    df: pd.DataFrame,
    config: EvaluationConfig,
    features: dict[str, list[str]],
    fold_rows: list[dict[str, Any]],
    quali_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_paths = [
        Path(__file__).resolve(),
        PROJECT_ROOT / "pipeline" / "05_train_models.py",
    ]
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(dataset_path.resolve()),
            "sha256": sha256_file(dataset_path),
            "rows": len(df),
            "columns": len(df.columns),
            "season_min": int(df["season"].min()),
            "season_max": int(df["season"].max()),
        },
        "git": git_state(),
        "source_sha256": {
            str(path.relative_to(PROJECT_ROOT)): sha256_file(path)
            for path in source_paths
        },
        "config": asdict(config),
        "features": features,
        "filters": {
            "temporal": (
                "season < target_season OR "
                "(season == target_season AND round < target_round)"
            ),
            "quali": "quali_position is not null",
            "race": "pipeline/05_train_models.py::classified_finisher_mask",
            "race_fp": (
                "classified_finisher_mask AND event-prequential predicted "
                "quali_position is available"
            ),
            "deadline_weather": (
                "observed session weather admitted (oracle diagnostic only)"
                if config.allow_oracle_weather
                else "all weather_* predictors excluded; no archived lock-time forecasts"
            ),
        },
        "phases": {
            "quali": "post-FP/main qualifying prediction",
            "race": "post-qualifying conditional finisher ranking",
            "race_fp": "actionable post-FP/pre-qualifying conditional finisher ranking",
        },
        "weighting": {
            "historical_event_weight": 1.0,
            "current_season_event_weight": config.current_season_weight,
            "wet_event_multiplier": config.wet_weight,
            "semantics": "constant group/query weight for every driver in an event",
        },
        "paired_comparison": {
            "cluster_unit": "race event",
            "fold_pairing_keys": ["cluster_id", "model"],
            "driver_pairing_keys": ["cluster_id", "model", "driver_id"],
            "guidance": (
                "Compare configuration deltas at the race-cluster level. "
                "Do not treat driver rows from one race as independent samples."
            ),
        },
        "evaluated_folds": [
            {
                "cluster_id": row["cluster_id"],
                "model": row["model"],
                "train_events": row["train_events"],
                "test_rows": row["test_rows"],
            }
            for row in fold_rows
        ],
        "auxiliary_quali_cache": quali_cache,
    }
    manifest["config_sha256"] = canonical_hash(manifest["config"])
    manifest["run_identity_sha256"] = canonical_hash(
        {
            "dataset": manifest["dataset"]["sha256"],
            "source": manifest["source_sha256"],
            "config": manifest["config_sha256"],
            "folds": manifest["evaluated_folds"],
        }
    )
    return manifest


def write_bundle(
    output_root: Path,
    manifest: dict[str, Any],
    fold_rows: list[dict[str, Any]],
    predictions: pd.DataFrame,
    summary: dict[str, Any],
) -> Path:
    slug = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in manifest["config"]["name"]
    )
    run_id = manifest["run_identity_sha256"][:12]
    bundle = output_root / f"{slug}__{run_id}"
    if bundle.exists():
        raise FileExistsError(
            f"Immutable experiment bundle already exists: {bundle}. "
            "Use a different config name or remove it deliberately."
        )
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=_json_default), encoding="utf-8"
    )
    (bundle / "fold_metrics.json").write_text(
        json.dumps(fold_rows, indent=2, default=_json_default), encoding="utf-8"
    )
    predictions.to_csv(bundle / "paired_predictions.csv", index=False)
    result = {"manifest": manifest, "summary": summary, "folds": fold_rows}
    (bundle / "result.json").write_text(
        json.dumps(result, indent=2, default=_json_default), encoding="utf-8"
    )
    return bundle


def _json_default(value: Any):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value)}")


def parse_json_overrides(value: str | None) -> dict[str, Any]:
    """Parse a JSON object supplied inline or by path."""
    if not value:
        return {}
    candidate = Path(value)
    payload = candidate.read_text(encoding="utf-8") if candidate.exists() else value
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Parameter overrides must decode to a JSON object")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-name", required=True)
    parser.add_argument("--models", default="quali,race,race_fp")
    parser.add_argument("--algorithm", choices=["xgboost", "catboost"], default="xgboost")
    parser.add_argument(
        "--data",
        type=Path,
        default=TRAINING_DATA_DIR / "all_training_data.parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "experiments" / "prequential",
    )
    parser.add_argument("--first-round", type=int)
    parser.add_argument("--last-round", type=int)
    parser.add_argument(
        "--weight-2026",
        type=float,
        default=REGULATION_WEIGHT_MULTIPLIER,
    )
    parser.add_argument("--wet-weight", type=float, default=6.0)
    parser.add_argument("--recency-decay", type=float, default=0.90)
    parser.add_argument("--min-train-events", type=int, default=10)
    parser.add_argument("--min-train-rows", type=int, default=100)
    parser.add_argument("--drop-features", default="")
    parser.add_argument("--drop-prefixes", default="")
    parser.add_argument(
        "--quali-overrides",
        help="Inline JSON object or JSON-file path with XGB qualifying parameter overrides.",
    )
    parser.add_argument(
        "--race-overrides",
        help="Inline JSON object or JSON-file path with XGB race/race_fp overrides.",
    )
    parser.add_argument(
        "--catboost-race-overrides",
        help="Inline JSON object or JSON-file path with CatBoost race/race_fp overrides.",
    )
    parser.add_argument(
        "--allow-oracle-weather",
        action="store_true",
        help=(
            "Diagnostic only: admit observed session weather from the historical "
            "parquet. Default excludes it because it was unavailable at lock time."
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Use tiny models to validate mechanics, never for model selection.",
    )
    parser.add_argument(
        "--no-quali-cache",
        action="store_true",
        help="Recompute race_fp auxiliary qualifying predictions without cache reuse.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.data.exists():
        raise SystemExit(f"Training dataset not found: {args.data}")
    config = EvaluationConfig(
        name=args.config_name,
        models=[item.strip() for item in args.models.split(",") if item.strip()],
        algorithm=args.algorithm,
        current_season_weight=args.weight_2026,
        wet_weight=args.wet_weight,
        recency_decay=args.recency_decay,
        min_train_events=args.min_train_events,
        min_train_rows=args.min_train_rows,
        first_round=args.first_round,
        last_round=args.last_round,
        allow_oracle_weather=args.allow_oracle_weather,
        drop_features=[
            item.strip() for item in args.drop_features.split(",") if item.strip()
        ],
        drop_prefixes=[
            item.strip() for item in args.drop_prefixes.split(",") if item.strip()
        ],
    )
    config.quali_params.update(parse_json_overrides(args.quali_overrides))
    config.race_params.update(parse_json_overrides(args.race_overrides))
    config.catboost_race_params.update(
        parse_json_overrides(args.catboost_race_overrides)
    )
    if args.smoke:
        config.quali_params.update(n_estimators=8, n_jobs=1)
        config.race_params.update(n_estimators=8, n_jobs=1)
        config.catboost_race_params.update(iterations=8, thread_count=1)

    np.random.seed(MODEL_RANDOM_STATE)
    df = pd.read_parquet(args.data)
    print(
        f"Loaded {len(df):,} rows from {args.data}; "
        f"evaluating {config.models} with {config.algorithm}"
    )
    features = build_feature_sets(df, config)
    quali_cache_info: dict[str, Any] | None = None
    precomputed_quali: pd.Series | None = None
    if "race_fp" in config.models and not args.no_quali_cache:
        dataset_sha = sha256_file(args.data)
        precomputed_quali, quali_cache_info = load_or_build_quali_cache(
            df,
            dataset_sha,
            config,
            features["quali"],
            args.output_dir / "_cache",
            verbose=True,
        )
    folds, predictions, features = evaluate(
        df, config, verbose=True, precomputed_quali=precomputed_quali
    )
    if not folds:
        raise SystemExit("No folds were eligible; check round and minimum-train settings")
    summary = summarize(folds, config.recency_decay)
    manifest = build_manifest(
        args.data, df, config, features, folds, quali_cache=quali_cache_info
    )
    bundle = write_bundle(args.output_dir, manifest, folds, predictions, summary)
    print(f"\nImmutable result bundle: {bundle}")
    print(json.dumps(summary, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
