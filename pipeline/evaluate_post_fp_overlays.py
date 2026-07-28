"""Stage-B evaluation of the actionable post-FP prediction overlays.

This evaluator compares five pre-registered transform policies while leaving
the production models and inference script untouched:

* B0: no FP qualifying blend, no grid anchor
* B1: FP weight 0.60 (0.15 sprint), no hard-track ramp, no anchor
* B2: current hard-track FP ramp, no anchor
* B3: B1 qualifying policy plus the current phase-aware grid anchor
* B4: B2 qualifying policy plus the current phase-aware grid anchor

Correctness contract
--------------------
Every qualifying and race model for event ``(season, round)`` is trained only
on strictly earlier events.  Raw qualifying scores are cached before any
overlay is applied.  Each historical race-FP training row receives the
event-prequential *blended* qualifying position for the policy being tested;
actual qualifying positions never enter the race-FP model.  Qualifying-derived
race features are then rebuilt using the shared production helper.

Race models are fitted once per distinct qualifying transform (B1/B3 and
B2/B4 share fits).  Grid anchoring is applied to the raw full-field race score
exactly in z-score space, and metrics are calculated on classified finishers.
All comparisons are paired by race event.  No driver-independent bootstrap or
driver-level significance calculation is produced.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (  # noqa: E402
    CANCELLED_ROUNDS_2026,
    CURRENT_SEASON,
    MODEL_RANDOM_STATE,
    REGULATION_WEIGHT_MULTIPLIER,
    TRAINING_DATA_DIR,
)
from config.track_classifications import (  # noqa: E402
    fp_quali_blend_weight,
    grid_anchor_weight,
)
from pipeline import evaluate_prequential_2026 as core  # noqa: E402


PACE_COLUMNS = ("best_lap_time", "best_3_lap_avg", "best_5_lap_avg")
MIN_PACE_DRIVERS = 10
FP_BASE_WEIGHT = 0.60
FP_HARD_WEIGHT = 0.80
FP_SPRINT_WEIGHT = 0.15
FP_HARD_PIVOT = 6


@dataclass(frozen=True)
class OverlayPolicy:
    code: str
    description: str
    quali_mode: str
    grid_anchor: bool


POLICIES: tuple[OverlayPolicy, ...] = (
    OverlayPolicy("B0", "no FP blend; no grid anchor", "none", False),
    OverlayPolicy(
        "B1",
        "FP 0.60 regular / 0.15 sprint; no hard ramp; no grid anchor",
        "base",
        False,
    ),
    OverlayPolicy(
        "B2",
        "current hard-track FP ramp; no grid anchor",
        "hard",
        False,
    ),
    OverlayPolicy(
        "B3",
        "FP 0.60 regular / 0.15 sprint; current grid anchor",
        "base",
        True,
    ),
    OverlayPolicy(
        "B4",
        "current hard-track FP ramp plus current grid anchor",
        "hard",
        True,
    ),
)


DEFAULT_QUALI_PARAMS = dict(core.DEFAULT_XGB_QUALI)
DEFAULT_RACE_PARAMS = dict(core.DEFAULT_XGB_RACE)
DEFAULT_CATBOOST_PARAMS = dict(core.DEFAULT_CATBOOST_RACE)


@dataclass
class StageBConfig:
    name: str
    algorithm: str = "xgboost"
    current_season_weight: float = REGULATION_WEIGHT_MULTIPLIER
    wet_weight: float = 6.0
    min_train_events: int = 10
    min_train_rows: int = 100
    first_round: int | None = None
    last_round: int | None = None
    allow_oracle_weather: bool = False
    drop_features: list[str] = field(default_factory=list)
    drop_prefixes: list[str] = field(default_factory=list)
    quali_params: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_QUALI_PARAMS)
    )
    race_params: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_RACE_PARAMS)
    )
    catboost_params: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_CATBOOST_PARAMS)
    )


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _drop_features(features: Iterable[str], config: StageBConfig) -> list[str]:
    exact = set(config.drop_features)
    return [
        feature
        for feature in features
        if feature not in exact
        and not any(feature.startswith(prefix) for prefix in config.drop_prefixes)
    ]


def build_feature_sets(
    df: pd.DataFrame, config: StageBConfig
) -> dict[str, list[str]]:
    quali = core.build_quali_feature_list(list(df.columns))
    race = core.build_race_feature_list(quali, list(df.columns))
    quali = _drop_features(quali, config)
    race = _drop_features(race, config)
    if not config.allow_oracle_weather:
        # Observed session weather is not a timestamped Fantasy-lock forecast.
        quali = [c for c in quali if not c.startswith("weather_")]
        race = [c for c in race if not c.startswith("weather_")]
    return {"quali": quali, "race_fp": race}


def completed_2026_events(
    df: pd.DataFrame, config: StageBConfig
) -> list[tuple[int, int]]:
    mask = (
        (df["season"] == CURRENT_SEASON)
        & df["finish_position"].notna()
        & ~df["round"].isin(CANCELLED_ROUNDS_2026)
    )
    rounds = sorted(int(value) for value in df.loc[mask, "round"].unique())
    if config.first_round is not None:
        rounds = [value for value in rounds if value >= config.first_round]
    if config.last_round is not None:
        rounds = [value for value in rounds if value <= config.last_round]
    return [(CURRENT_SEASON, value) for value in rounds]


def _clean_matrix(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    return df[features].replace([np.inf, -np.inf], np.nan)


def _is_sprint_event(event: pd.DataFrame) -> bool:
    if "has_sprint" in event.columns:
        values = event["has_sprint"].dropna()
        if not values.empty:
            return bool(values.astype(bool).any())
    if "sprint_position" in event.columns:
        return bool(event["sprint_position"].notna().any())
    return False


def _event_circuit(event: pd.DataFrame) -> str:
    values = event["circuit_id"].dropna().astype(str).unique()
    if len(values) != 1:
        raise ValueError(f"Expected one circuit_id in event, found {values.tolist()}")
    return str(values[0])


def _zscore(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    spread = values.std()
    return (
        (values - values.mean()) / spread
        if spread > 1e-9
        else values - values.mean()
    )


def fp_composite(event: pd.DataFrame) -> pd.Series:
    """Return the exact production FP qualifying composite for one event."""
    pace_columns = [column for column in PACE_COLUMNS if column in event.columns]
    if not pace_columns:
        return pd.Series(np.nan, index=event.index, dtype=float)
    components: list[pd.Series] = []
    for column in pace_columns:
        values = pd.to_numeric(event[column], errors="coerce")
        spread = values.std()
        components.append(
            -(values - values.mean()) / spread
            if spread and spread > 1e-9
            else values * 0.0
        )
    return pd.concat(components, axis=1).mean(axis=1, skipna=True)


def policy_blend_weight(
    policy: OverlayPolicy, circuit_id: str, is_sprint: bool
) -> float:
    if policy.quali_mode == "none":
        return 0.0
    if is_sprint:
        return FP_SPRINT_WEIGHT
    if policy.quali_mode == "base":
        return FP_BASE_WEIGHT
    if policy.quali_mode == "hard":
        return fp_quali_blend_weight(
            circuit_id,
            FP_BASE_WEIGHT,
            FP_HARD_WEIGHT,
            FP_HARD_PIVOT,
        )
    raise ValueError(f"Unknown qualifying transform: {policy.quali_mode}")


def blend_quali_event(
    event: pd.DataFrame,
    raw_scores: pd.Series,
    policy: OverlayPolicy,
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    """Apply one qualifying overlay with the exact production transform."""
    if not raw_scores.index.equals(event.index):
        raw_scores = raw_scores.reindex(event.index)
    if raw_scores.isna().any():
        raise ValueError("Qualifying raw scores are incomplete for the event")

    circuit = _event_circuit(event)
    is_sprint = _is_sprint_event(event)
    weight = policy_blend_weight(policy, circuit, is_sprint)
    composite = fp_composite(event)
    has_pace = composite.notna().to_numpy()
    pace_count = int(has_pace.sum())
    scores = raw_scores.to_numpy(dtype=float).copy()
    applied = False
    if weight > 0.0 and pace_count >= MIN_PACE_DRIVERS:
        model_z = _zscore(scores)
        composite_z = np.zeros(len(event), dtype=float)
        composite_z[has_pace] = _zscore(
            composite.to_numpy(dtype=float)[has_pace]
        )
        scores = model_z.copy()
        scores[has_pace] = (
            (1.0 - weight) * model_z[has_pace]
            + weight * composite_z[has_pace]
        )
        applied = True
    positions = pd.Series(-scores, index=event.index).rank(
        method="first"
    ).astype(int)
    return (
        pd.Series(scores, index=event.index, dtype=float),
        positions,
        {
            "circuit_id": circuit,
            "is_sprint": is_sprint,
            "fp_pace_driver_count": pace_count,
            "fp_blend_weight": float(weight),
            "fp_blend_applied": applied,
        },
    )


def _fit_quali_raw_scores(
    df: pd.DataFrame,
    features: list[str],
    config: StageBConfig,
    *,
    target_scope: str,
    verbose: bool,
) -> pd.Series:
    if target_scope not in {"history", "current"}:
        raise ValueError(f"Unknown target scope: {target_scope}")
    result = pd.Series(np.nan, index=df.index, dtype=float)
    for year, round_num in core.event_keys(df, "quali_position"):
        if target_scope == "history" and year >= CURRENT_SEASON:
            continue
        if target_scope == "current" and year != CURRENT_SEASON:
            continue
        prior = core.event_before(df, year, round_num) & df["quali_position"].notna()
        target = (
            core.event_mask(df, year, round_num)
            & df["quali_position"].notna()
        )
        prior_events = df.loc[prior, ["season", "round"]].drop_duplicates()
        if (
            len(prior_events) < config.min_train_events
            or int(prior.sum()) < config.min_train_rows
            or int(target.sum()) < 2
        ):
            continue
        train = core.apply_training_weights(
            df.loc[prior],
            "quali",
            config.current_season_weight,
            config.wet_weight,
        )
        model, used = core.train_ranker(
            train,
            features,
            "quali_position",
            "xgboost",
            config.quali_params,
        )
        test = df.loc[target].copy()
        test["_stage_b_source_index"] = test.index
        ordered = core.sort_by_race_groups(test)
        scores = np.asarray(
            model.predict(_clean_matrix(ordered, used)), dtype=float
        )
        result.loc[ordered["_stage_b_source_index"].to_numpy()] = scores
        if verbose and (year == CURRENT_SEASON or round_num == 1):
            print(
                f"  strict qualifying raw {year} R{round_num}: "
                f"{len(prior_events)} prior events"
            )
    return result


def _raw_quali_cache_identity(
    dataset_sha: str,
    config: StageBConfig,
    features: list[str],
    layer: str,
    history_identity: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "layer": layer,
        "dataset_sha256": dataset_sha,
        "source_sha256": sha256_file(Path(__file__).resolve()),
        "core_source_sha256": sha256_file(
            PROJECT_ROOT / "pipeline" / "evaluate_prequential_2026.py"
        ),
        "training_source_sha256": sha256_file(
            PROJECT_ROOT / "pipeline" / "05_train_models.py"
        ),
        "features": features,
        "quali_params": config.quali_params,
        "wet_weight": config.wet_weight,
        "min_train_events": config.min_train_events,
        "min_train_rows": config.min_train_rows,
        "allow_oracle_weather": config.allow_oracle_weather,
    }
    if layer == "current":
        payload["current_season_weight"] = config.current_season_weight
        payload["history_identity_sha256"] = history_identity
    return canonical_hash(payload)


def _write_raw_cache(path: Path, raw: pd.Series) -> None:
    pd.DataFrame(
        {
            "source_index": raw.index.to_numpy(),
            "raw_quali_score": raw.to_numpy(dtype=float),
        }
    ).to_parquet(path, index=False)


def _read_raw_cache(path: Path, expected_index: pd.Index) -> pd.Series:
    cached = pd.read_parquet(path)
    if cached["source_index"].tolist() != expected_index.tolist():
        raise ValueError(f"Strict qualifying cache index mismatch: {path}")
    return pd.Series(
        cached["raw_quali_score"].to_numpy(dtype=float),
        index=expected_index,
    )


def load_or_build_raw_quali_cache(
    df: pd.DataFrame,
    dataset_sha: str,
    config: StageBConfig,
    features: list[str],
    cache_root: Path,
    *,
    verbose: bool = True,
) -> tuple[pd.Series, dict[str, Any]]:
    """Cache raw strict qualifying scores in safe history/current layers."""
    cache_root.mkdir(parents=True, exist_ok=True)
    history_id = _raw_quali_cache_identity(
        dataset_sha, config, features, "history"
    )
    history_path = cache_root / f"stage_b_quali_history__{history_id[:16]}.parquet"
    history_hit = history_path.exists()
    if history_hit:
        history = _read_raw_cache(history_path, df.index)
    else:
        history = _fit_quali_raw_scores(
            df, features, config, target_scope="history", verbose=verbose
        )
        _write_raw_cache(history_path, history)

    current_id = _raw_quali_cache_identity(
        dataset_sha,
        config,
        features,
        "current",
        history_identity=history_id,
    )
    current_path = (
        cache_root
        / f"stage_b_quali_current_{CURRENT_SEASON}__{current_id[:16]}.parquet"
    )
    current_hit = current_path.exists()
    if current_hit:
        current = _read_raw_cache(current_path, df.index)
    else:
        current = _fit_quali_raw_scores(
            df, features, config, target_scope="current", verbose=verbose
        )
        _write_raw_cache(current_path, current)

    overlap = history.notna() & current.notna()
    if bool(overlap.any()):
        raise ValueError("Historical/current strict qualifying caches overlap")
    combined = history.combine_first(current)
    return combined, {
        "strategy": "raw_scores_history_plus_current",
        "history": {
            "identity_sha256": history_id,
            "path": str(history_path),
            "hit": history_hit,
        },
        "current": {
            "identity_sha256": current_id,
            "path": str(current_path),
            "hit": current_hit,
            "current_season_weight": config.current_season_weight,
        },
    }


def build_policy_quali_sequences(
    df: pd.DataFrame,
    raw_scores: pd.Series,
) -> tuple[dict[str, pd.Series], dict[tuple[str, int, int], dict[str, Any]]]:
    """Transform cached raw scores into one leak-free sequence per policy."""
    sequences = {
        policy.code: pd.Series(np.nan, index=df.index, dtype=float)
        for policy in POLICIES
    }
    metadata: dict[tuple[str, int, int], dict[str, Any]] = {}
    for year, round_num in core.event_keys(df, "quali_position"):
        mask = (
            core.event_mask(df, year, round_num)
            & df["quali_position"].notna()
            & raw_scores.notna()
        )
        event = df.loc[mask].copy()
        if len(event) < 2:
            continue
        event_raw = raw_scores.loc[event.index]
        for policy in POLICIES:
            _, positions, info = blend_quali_event(event, event_raw, policy)
            sequences[policy.code].loc[event.index] = positions.astype(float)
            metadata[(policy.code, year, round_num)] = info
    return sequences, metadata


def _race_training_rows(
    df: pd.DataFrame,
    prior_mask: pd.Series,
    quali_sequence: pd.Series,
) -> pd.DataFrame:
    mask = (
        prior_mask
        & core.classified_finisher_mask(df)
        & quali_sequence.notna()
    )
    out = df.loc[mask].copy()
    out["quali_position"] = quali_sequence.loc[out.index].to_numpy(dtype=float)
    return core.rederive_quali_dependent_features(out, "quali_position")


def _race_test_rows(
    df: pd.DataFrame,
    target_mask: pd.Series,
    quali_sequence: pd.Series,
) -> pd.DataFrame:
    # Predict the full known field, then score only the conditional-ranker
    # population. Filtering before ranking would compress positions incorrectly.
    mask = target_mask & df["finish_position"].notna() & quali_sequence.notna()
    out = df.loc[mask].copy()
    out["_stage_b_source_index"] = out.index
    out["quali_position"] = quali_sequence.loc[out.index].to_numpy(dtype=float)
    return core.rederive_quali_dependent_features(out, "quali_position")


def apply_grid_anchor(
    race_scores: np.ndarray,
    predicted_grid: np.ndarray,
    circuit_id: str,
    *,
    enabled: bool,
    fp_pace_driver_count: int,
) -> tuple[np.ndarray, float, bool]:
    """Apply the current phase-aware grid anchor to raw full-field scores."""
    weight = grid_anchor_weight(circuit_id) if enabled else 0.0
    applied = bool(weight > 0.0 and fp_pace_driver_count >= MIN_PACE_DRIVERS)
    if not applied:
        return np.asarray(race_scores, dtype=float).copy(), float(weight), False
    anchored = (
        (1.0 - weight) * _zscore(np.asarray(race_scores, dtype=float))
        + weight * _zscore(-np.asarray(predicted_grid, dtype=float))
    )
    return anchored, float(weight), True


def evaluate_stage_b(
    df: pd.DataFrame,
    config: StageBConfig,
    raw_quali_scores: pd.Series,
    *,
    verbose: bool = True,
) -> tuple[
    list[dict[str, Any]],
    pd.DataFrame,
    list[dict[str, Any]],
    dict[str, list[str]],
]:
    """Evaluate all policies on identical strict event folds."""
    features = build_feature_sets(df, config)
    sequences, quali_metadata = build_policy_quali_sequences(df, raw_quali_scores)
    targets = completed_2026_events(df, config)
    if not targets:
        raise ValueError("No completed 2026 events in requested range")

    policies_by_mode: dict[str, list[OverlayPolicy]] = {}
    for policy in POLICIES:
        policies_by_mode.setdefault(policy.quali_mode, []).append(policy)

    folds: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    for year, round_num in targets:
        prior = core.event_before(df, year, round_num)
        target = core.event_mask(df, year, round_num)
        cluster_id = f"{year}-R{round_num:02d}"
        for quali_mode, mode_policies in policies_by_mode.items():
            representative = mode_policies[0]
            sequence = sequences[representative.code]
            train = _race_training_rows(df, prior, sequence)
            test = _race_test_rows(df, target, sequence)
            train_events = len(
                train[["season", "round"]].drop_duplicates()
            )
            if (
                train_events < config.min_train_events
                or len(train) < config.min_train_rows
                or len(test) < 2
            ):
                continue
            train = core.apply_training_weights(
                train,
                "race_fp",
                config.current_season_weight,
                config.wet_weight,
            )
            params = (
                config.catboost_params
                if config.algorithm == "catboost"
                else config.race_params
            )
            model, used = core.train_ranker(
                train,
                features["race_fp"],
                "finish_position",
                config.algorithm,
                params,
            )
            ordered = core.sort_by_race_groups(test)
            raw_race = np.asarray(
                model.predict(_clean_matrix(ordered, used)), dtype=float
            )
            source_indices = ordered["_stage_b_source_index"].to_numpy()
            finisher = core.classified_finisher_mask(ordered).to_numpy(dtype=bool)
            actual = ordered["finish_position"].to_numpy(dtype=float)
            circuit = _event_circuit(ordered)
            race_name = (
                str(ordered["race_name"].dropna().iloc[0])
                if "race_name" in ordered.columns
                and not ordered["race_name"].dropna().empty
                else circuit
            )

            for policy in mode_policies:
                info = quali_metadata[(policy.code, year, round_num)]
                predicted_grid = sequences[policy.code].loc[
                    source_indices
                ].to_numpy(dtype=float)
                final_scores, anchor_weight, anchor_applied = apply_grid_anchor(
                    raw_race,
                    predicted_grid,
                    circuit,
                    enabled=policy.grid_anchor,
                    fp_pace_driver_count=int(info["fp_pace_driver_count"]),
                )
                final_positions = (
                    pd.Series(-final_scores).rank(method="first").astype(int).to_numpy()
                )
                metrics = core.calculate_metrics(
                    final_positions[finisher], actual[finisher]
                )
                # The ordered frame contains transformed quali_position. Retrieve
                # actual qualifying targets through the stashed source identity.
                q_actual_array = df.loc[
                    source_indices, "quali_position"
                ].to_numpy(dtype=float)
                q_metrics = core.calculate_metrics(
                    predicted_grid, q_actual_array
                )
                fold = {
                    "cluster_id": cluster_id,
                    "season": year,
                    "round": round_num,
                    "race_name": race_name,
                    "circuit_id": circuit,
                    "policy": policy.code,
                    "policy_description": policy.description,
                    "quali_mode": policy.quali_mode,
                    "algorithm": config.algorithm,
                    "train_events": train_events,
                    "train_rows": len(train),
                    "test_field_rows": len(ordered),
                    "test_classified_finishers": int(finisher.sum()),
                    "mae": metrics["mae"],
                    "kendall_tau": metrics["kendall_tau"],
                    "spearman_rho": metrics["spearman_rho"],
                    "quali_mae": q_metrics["mae"],
                    "fp_pace_driver_count": int(info["fp_pace_driver_count"]),
                    "fp_blend_weight": float(info["fp_blend_weight"]),
                    "fp_blend_applied": bool(info["fp_blend_applied"]),
                    "anchor_candidate_weight": anchor_weight,
                    "anchor_applied": anchor_applied,
                }
                folds.append(fold)
                for row_number, (_, row) in enumerate(ordered.iterrows()):
                    predictions.append(
                        {
                            "cluster_id": cluster_id,
                            "season": year,
                            "round": round_num,
                            "policy": policy.code,
                            "driver_id": str(row["driver_id"]),
                            "evaluation_eligible": bool(finisher[row_number]),
                            "actual_finish_position": float(actual[row_number]),
                            "predicted_finish_position": int(
                                final_positions[row_number]
                            ),
                            "raw_race_score": float(raw_race[row_number]),
                            "final_race_score": float(final_scores[row_number]),
                            "actual_quali_position": float(
                                q_actual_array[row_number]
                            ),
                            "prequential_quali_position": int(
                                predicted_grid[row_number]
                            ),
                        }
                    )
                if verbose:
                    print(
                        f"{cluster_id} {policy.code}: "
                        f"race MAE={metrics['mae']:.3f}, "
                        f"quali MAE={q_metrics['mae']:.3f}, "
                        f"FP w={info['fp_blend_weight']:.2f}, "
                        f"anchor={'yes' if anchor_applied else 'no'}"
                    )

    paired = paired_fold_deltas(folds)
    return folds, pd.DataFrame(predictions), paired, features


def paired_fold_deltas(folds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every policy comparison paired at the race-event cluster."""
    frame = pd.DataFrame(folds)
    rows: list[dict[str, Any]] = []
    policies = [policy.code for policy in POLICIES]
    for reference, candidate in itertools.combinations(policies, 2):
        left = frame[frame["policy"] == reference][
            ["cluster_id", "season", "round", "race_name", "mae"]
        ].rename(columns={"mae": "reference_mae"})
        right = frame[frame["policy"] == candidate][
            ["cluster_id", "mae"]
        ].rename(columns={"mae": "candidate_mae"})
        merged = left.merge(right, on="cluster_id", how="inner", validate="one_to_one")
        for row in merged.itertuples(index=False):
            rows.append(
                {
                    "cluster_id": row.cluster_id,
                    "season": int(row.season),
                    "round": int(row.round),
                    "race_name": row.race_name,
                    "reference_policy": reference,
                    "candidate_policy": candidate,
                    "reference_mae": float(row.reference_mae),
                    "candidate_mae": float(row.candidate_mae),
                    "delta_mae_candidate_minus_reference": float(
                        row.candidate_mae - row.reference_mae
                    ),
                }
            )
    return rows


def summarize(
    folds: list[dict[str, Any]], paired: list[dict[str, Any]]
) -> dict[str, Any]:
    frame = pd.DataFrame(folds)
    by_policy: dict[str, Any] = {}
    for policy, group in frame.groupby("policy", sort=True):
        by_policy[policy] = {
            "folds": int(len(group)),
            "race_mae_mean": float(group["mae"].mean()),
            "race_mae_median": float(group["mae"].median()),
            "quali_mae_mean": float(group["quali_mae"].mean()),
        }

    paired_frame = pd.DataFrame(paired)
    paired_summary: dict[str, Any] = {}
    if not paired_frame.empty:
        for (reference, candidate), group in paired_frame.groupby(
            ["reference_policy", "candidate_policy"], sort=True
        ):
            delta = group["delta_mae_candidate_minus_reference"]
            paired_summary[f"{candidate}_minus_{reference}"] = {
                "events": int(len(group)),
                "mean_delta_mae": float(delta.mean()),
                "median_delta_mae": float(delta.median()),
                "candidate_wins": int((delta < 0).sum()),
                "ties": int((delta == 0).sum()),
                "candidate_losses": int((delta > 0).sum()),
                "inference_unit": "race event; no driver-independent bootstrap",
            }

    named: dict[str, Any] = {}
    for label, round_num in (("monaco_r8", 8), ("hungary_r13", 13)):
        group = frame[
            (frame["season"] == CURRENT_SEASON) & (frame["round"] == round_num)
        ]
        named[label] = (
            {
                row.policy: {
                    "race_mae": float(row.mae),
                    "quali_mae": float(row.quali_mae),
                    "fp_blend_weight": float(row.fp_blend_weight),
                    "anchor_weight": float(row.anchor_candidate_weight),
                    "anchor_applied": bool(row.anchor_applied),
                }
                for row in group.itertuples(index=False)
            }
            if not group.empty
            else {"status": "not_in_evaluated_folds"}
        )
    return {
        "by_policy": by_policy,
        "paired_event_deltas": paired_summary,
        "named_hard_track_metrics": named,
        "selection_guidance": (
            "Select from paired race-event deltas, with Monaco R8 and Hungary "
            "R13 reported explicitly. Driver rows are diagnostic only."
        ),
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
    config: StageBConfig,
    features: dict[str, list[str]],
    folds: list[dict[str, Any]],
    cache_info: dict[str, Any],
) -> dict[str, Any]:
    source_paths = [
        Path(__file__).resolve(),
        PROJECT_ROOT / "pipeline" / "evaluate_prequential_2026.py",
        PROJECT_ROOT / "pipeline" / "05_train_models.py",
        PROJECT_ROOT / "pipeline" / "06_run_predictions.py",
        PROJECT_ROOT / "config" / "track_classifications.py",
    ]
    manifest = {
        "schema_version": 1,
        "stage": "B_post_fp_overlay_policy",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(dataset_path.resolve()),
            "sha256": sha256_file(dataset_path),
            "rows": len(df),
            "columns": len(df.columns),
        },
        "git": git_state(),
        "source_sha256": {
            str(path.relative_to(PROJECT_ROOT)): sha256_file(path)
            for path in source_paths
        },
        "config": asdict(config),
        "policies": [asdict(policy) for policy in POLICIES],
        "features": features,
        "strict_temporal_filter": (
            "season < target_season OR "
            "(season == target_season AND round < target_round)"
        ),
        "race_fp_contract": (
            "Historical and test quali_position are event-prequential policy-"
            "blended predictions; qualifying-derived features are rederived. "
            "Actual qualifying is target-only and never a race-FP predictor."
        ),
        "race_metric_population": (
            "Full field ranked; MAE/correlation evaluated on "
            "05_train_models.py::classified_finisher_mask"
        ),
        "pairing": {
            "unit": "race event",
            "keys": ["cluster_id"],
            "driver_independent_bootstrap": False,
        },
        "raw_quali_cache": cache_info,
        "evaluated_folds": [
            {
                "cluster_id": row["cluster_id"],
                "policy": row["policy"],
                "train_events": row["train_events"],
                "test_classified_finishers": row["test_classified_finishers"],
            }
            for row in folds
        ],
    }
    manifest["config_sha256"] = canonical_hash(manifest["config"])
    manifest["run_identity_sha256"] = canonical_hash(
        {
            "dataset": manifest["dataset"]["sha256"],
            "source": manifest["source_sha256"],
            "config": manifest["config_sha256"],
            "policies": manifest["policies"],
            "folds": manifest["evaluated_folds"],
        }
    )
    return manifest


def _json_default(value: Any):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value)}")


def write_bundle(
    output_root: Path,
    manifest: dict[str, Any],
    folds: list[dict[str, Any]],
    predictions: pd.DataFrame,
    paired: list[dict[str, Any]],
    summary: dict[str, Any],
) -> Path:
    slug = "".join(
        char if char.isalnum() or char in "-_" else "_"
        for char in manifest["config"]["name"]
    )
    bundle = output_root / (
        f"{slug}__{manifest['run_identity_sha256'][:12]}"
    )
    if bundle.exists():
        raise FileExistsError(f"Immutable Stage-B bundle already exists: {bundle}")
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=_json_default), encoding="utf-8"
    )
    (bundle / "fold_metrics.json").write_text(
        json.dumps(folds, indent=2, default=_json_default), encoding="utf-8"
    )
    (bundle / "paired_fold_deltas.json").write_text(
        json.dumps(paired, indent=2, default=_json_default), encoding="utf-8"
    )
    predictions.to_csv(bundle / "paired_predictions.csv", index=False)
    (bundle / "result.json").write_text(
        json.dumps(
            {"manifest": manifest, "summary": summary, "folds": folds},
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    return bundle


def parse_json_overrides(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    candidate = Path(value)
    payload = candidate.read_text(encoding="utf-8") if candidate.exists() else value
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Estimator overrides must decode to a JSON object")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-name", required=True)
    parser.add_argument(
        "--data",
        type=Path,
        default=TRAINING_DATA_DIR / "all_training_data.parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "experiments" / "post_fp_stage_b",
    )
    parser.add_argument("--algorithm", choices=["xgboost", "catboost"], default="xgboost")
    parser.add_argument("--first-round", type=int)
    parser.add_argument("--last-round", type=int)
    parser.add_argument(
        "--weight-2026",
        type=float,
        default=REGULATION_WEIGHT_MULTIPLIER,
    )
    parser.add_argument("--wet-weight", type=float, default=6.0)
    parser.add_argument("--min-train-events", type=int, default=10)
    parser.add_argument("--min-train-rows", type=int, default=100)
    parser.add_argument("--drop-features", default="")
    parser.add_argument("--drop-prefixes", default="")
    parser.add_argument("--quali-overrides")
    parser.add_argument("--race-overrides")
    parser.add_argument("--catboost-overrides")
    parser.add_argument(
        "--allow-oracle-weather",
        action="store_true",
        help="Diagnostic only; default excludes observed post-lock weather.",
    )
    parser.add_argument(
        "--no-quali-cache",
        action="store_true",
        help="Recompute raw strict qualifying scores without cache reuse.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Use tiny screening estimators; never use smoke output for selection.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.data.exists():
        raise SystemExit(f"Training dataset not found: {args.data}")
    config = StageBConfig(
        name=args.config_name,
        algorithm=args.algorithm,
        current_season_weight=args.weight_2026,
        wet_weight=args.wet_weight,
        min_train_events=args.min_train_events,
        min_train_rows=args.min_train_rows,
        first_round=args.first_round,
        last_round=args.last_round,
        allow_oracle_weather=args.allow_oracle_weather,
        drop_features=[
            value.strip() for value in args.drop_features.split(",") if value.strip()
        ],
        drop_prefixes=[
            value.strip() for value in args.drop_prefixes.split(",") if value.strip()
        ],
    )
    config.quali_params.update(parse_json_overrides(args.quali_overrides))
    config.race_params.update(parse_json_overrides(args.race_overrides))
    config.catboost_params.update(parse_json_overrides(args.catboost_overrides))
    if args.smoke:
        config.quali_params.update(n_estimators=8, n_jobs=1)
        config.race_params.update(n_estimators=8, n_jobs=1)
        config.catboost_params.update(iterations=8, thread_count=1)

    np.random.seed(MODEL_RANDOM_STATE)
    df = pd.read_parquet(args.data)
    features = build_feature_sets(df, config)
    dataset_sha = sha256_file(args.data)
    if args.no_quali_cache:
        history = _fit_quali_raw_scores(
            df, features["quali"], config, target_scope="history", verbose=True
        )
        current = _fit_quali_raw_scores(
            df, features["quali"], config, target_scope="current", verbose=True
        )
        raw_quali = history.combine_first(current)
        cache_info = {"strategy": "disabled"}
    else:
        raw_quali, cache_info = load_or_build_raw_quali_cache(
            df,
            dataset_sha,
            config,
            features["quali"],
            args.output_dir / "_cache",
            verbose=True,
        )
    folds, predictions, paired, features = evaluate_stage_b(
        df, config, raw_quali, verbose=True
    )
    if not folds:
        raise SystemExit("No eligible Stage-B folds")
    summary = summarize(folds, paired)
    manifest = build_manifest(
        args.data, df, config, features, folds, cache_info
    )
    bundle = write_bundle(
        args.output_dir, manifest, folds, predictions, paired, summary
    )
    print(f"\nImmutable Stage-B bundle: {bundle}")
    print(json.dumps(summary, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
