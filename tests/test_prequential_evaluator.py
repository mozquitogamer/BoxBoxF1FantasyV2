"""Focused invariants for the strict 2026 prequential evaluator."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "pipeline" / "evaluate_prequential_2026.py"
SPEC = importlib.util.spec_from_file_location("prequential_evaluator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pe
SPEC.loader.exec_module(pe)


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [2025, 2025, 2026, 2026, 2026],
            "round": [24, 24, 1, 2, 3],
            "driver_id": ["a", "b", "a", "a", "a"],
            "finish_position": [1, 2, 1, 1, 1],
        }
    )


def test_event_before_is_strict_and_never_admits_target_or_future() -> None:
    df = _events()
    mask = pe.event_before(df, 2026, 2)
    assert list(zip(df.loc[mask, "season"], df.loc[mask, "round"])) == [
        (2025, 24),
        (2025, 24),
        (2026, 1),
    ]
    assert not bool((mask & pe.event_mask(df, 2026, 2)).any())


def test_group_weights_returns_one_weight_per_event_in_event_order() -> None:
    df = pd.DataFrame(
        {
            "season": [2025, 2025, 2026, 2026],
            "round": [1, 1, 1, 1],
        }
    )
    result = pe.group_weights(df, np.array([1.0, 1.0, 2.5, 2.5]))
    assert result.tolist() == [1.0, 2.5]


def test_group_weights_rejects_driver_level_weight_disagreement() -> None:
    df = pd.DataFrame({"season": [2026, 2026], "round": [1, 1]})
    with pytest.raises(ValueError, match="differ inside ranking groups"):
        pe.group_weights(df, np.array([2.5, 15.0]))


def test_race_fp_never_falls_back_to_actual_qualifying() -> None:
    df = pd.DataFrame(
        {
            "season": [2025, 2025, 2026],
            "round": [1, 2, 1],
            "driver_id": ["a", "a", "a"],
            "quali_position": [9.0, 8.0, 1.0],
            "finish_position": [9.0, 8.0, 1.0],
            "is_finished": [1, 1, 1],
            "is_dsq": [0, 0, 0],
            "is_dns": [0, 0, 0],
        }
    )
    predicted_quali = pd.Series([7.0, np.nan, 4.0], index=df.index)
    selected = pe._eligible_rows(
        df,
        "race_fp",
        pd.Series([True, True, True], index=df.index),
        predicted_quali,
    )
    assert selected["round"].tolist() == [1, 1]
    assert selected["quali_position"].tolist() == [7.0, 4.0]
    assert 8.0 not in selected["quali_position"].tolist()


def test_primary_summary_is_recency_and_actionability_weighted() -> None:
    rows = [
        {
            "season": 2026,
            "round": 1,
            "model": "quali",
            "mae": 4.0,
            "kendall_tau": 0.2,
            "spearman_rho": 0.3,
        },
        {
            "season": 2026,
            "round": 2,
            "model": "quali",
            "mae": 2.0,
            "kendall_tau": 0.6,
            "spearman_rho": 0.7,
        },
        {
            "season": 2026,
            "round": 2,
            "model": "race_fp",
            "mae": 3.0,
            "kendall_tau": 0.4,
            "spearman_rho": 0.5,
        },
    ]
    result = pe.summarize(
        rows,
        recency_decay=0.5,
        model_weights={"quali": 0.25, "race_fp": 0.75},
    )
    assert result["by_model"]["quali"]["mae_recency_weighted"] == pytest.approx(
        (4.0 * 0.5 + 2.0) / 1.5
    )
    expected = ((8 / 3) * 0.25 + 3.0 * 0.75) / 1.0
    assert result["primary_2026"]["score"] == pytest.approx(expected)


def test_canonical_hash_changes_when_config_changes() -> None:
    first = pe.canonical_hash({"weight": 2.5, "features": ["a"]})
    second = pe.canonical_hash({"weight": 3.0, "features": ["a"]})
    assert first != second


def test_observed_weather_is_excluded_from_trustworthy_default() -> None:
    df = pd.DataFrame(
        columns=[
            "season",
            "round",
            "driver_id",
            "quali_position",
            "finish_position",
            "weather_was_wet_quali",
            "weather_was_wet_race",
            "some_prior",
        ]
    )
    config = pe.EvaluationConfig(name="default")
    feature_sets = pe.build_feature_sets(df, config)
    assert "some_prior" in feature_sets["quali"]
    assert not any(
        feature.startswith("weather_")
        for features in feature_sets.values()
        for feature in features
    )

    config.allow_oracle_weather = True
    oracle_features = pe.build_feature_sets(df, config)
    assert "weather_was_wet_quali" in oracle_features["quali"]
    assert "weather_was_wet_race" in oracle_features["race"]


def test_quali_cache_identity_covers_features_parameters_and_dataset() -> None:
    config = pe.EvaluationConfig(name="candidate")
    baseline = pe.quali_cache_identity(
        "dataset-a", config, ["feature_a"], layer="history"
    )
    assert (
        pe.quali_cache_identity(
            "dataset-b", config, ["feature_a"], layer="history"
        )
        != baseline
    )
    assert (
        pe.quali_cache_identity(
            "dataset-a", config, ["feature_b"], layer="history"
        )
        != baseline
    )
    config.quali_params["max_depth"] = 99
    assert (
        pe.quali_cache_identity(
            "dataset-a", config, ["feature_a"], layer="history"
        )
        != baseline
    )


def test_history_cache_identity_is_weight_independent_but_current_is_not() -> None:
    config = pe.EvaluationConfig(name="weight-sweep")
    history_25 = pe.quali_cache_identity(
        "dataset", config, ["feature"], layer="history"
    )
    current_25 = pe.quali_cache_identity(
        "dataset",
        config,
        ["feature"],
        layer="current",
        history_identity=history_25,
    )
    config.current_season_weight += 1.0
    history_40 = pe.quali_cache_identity(
        "dataset", config, ["feature"], layer="history"
    )
    current_40 = pe.quali_cache_identity(
        "dataset",
        config,
        ["feature"],
        layer="current",
        history_identity=history_40,
    )
    assert history_40 == history_25
    assert current_40 != current_25


def test_layered_prequential_predictions_equal_full_recomputation() -> None:
    rows = []
    for season, rounds in ((2025, range(1, 5)), (2026, range(1, 3))):
        for round_num in rounds:
            for position in range(1, 5):
                rows.append(
                    {
                        "season": season,
                        "round": round_num,
                        "driver_id": f"d{position}",
                        "quali_position": float(position),
                        "signal": float(5 - position) + round_num * 0.01,
                    }
                )
    df = pd.DataFrame(rows)
    config = pe.EvaluationConfig(
        name="layer-equivalence",
        min_train_events=1,
        min_train_rows=4,
    )
    config.quali_params.update(n_estimators=2, max_depth=2, n_jobs=1)

    full = pe.precompute_event_prequential_quali(
        df, ["signal"], config, verbose=False, target_scope="all"
    )
    history = pe.precompute_event_prequential_quali(
        df, ["signal"], config, verbose=False, target_scope="history"
    )
    current = pe.precompute_event_prequential_quali(
        df, ["signal"], config, verbose=False, target_scope="current"
    )
    layered = pe.combine_quali_layers(history, current, df.index)
    np.testing.assert_allclose(
        layered.to_numpy(), full.to_numpy(), equal_nan=True
    )


def test_parameter_overrides_accept_inline_json() -> None:
    assert pe.parse_json_overrides('{"max_depth": 4}') == {"max_depth": 4}
    with pytest.raises(ValueError, match="JSON object"):
        pe.parse_json_overrides("[1, 2]")
