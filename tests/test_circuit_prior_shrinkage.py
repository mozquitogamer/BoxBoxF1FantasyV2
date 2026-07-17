"""Regression tests for sparse driver-at-circuit qualifying priors."""

import importlib

import numpy as np
import pandas as pd
import pytest

from config.circuit_priors import (
    apply_driver_circuit_effect,
    driver_circuit_reliability,
)


features = importlib.import_module("pipeline.03b_build_jolpica_features")
predictions = importlib.import_module("pipeline.06_run_predictions")
trainer = importlib.import_module("pipeline.05_train_models")


def _history_rows(target_quali: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "season": 2024, "round": 1, "driver_id": "rookie",
            "constructor_id": "team", "circuit_id": "monza",
            "quali_position": 4.0,
        },
        {
            "season": 2024, "round": 2, "driver_id": "rookie",
            "constructor_id": "team", "circuit_id": "spa",
            "quali_position": 18.0,
        },
        {
            "season": 2024, "round": 3, "driver_id": "rookie",
            "constructor_id": "team", "circuit_id": "cota",
            "quali_position": 2.0,
        },
        {
            "season": 2024, "round": 4, "driver_id": "rookie",
            "constructor_id": "team", "circuit_id": "vegas",
            "quali_position": 3.0,
        },
        {
            "season": 2025, "round": 1, "driver_id": "rookie",
            "constructor_id": "team", "circuit_id": "spa",
            "quali_position": target_quali,
        },
    ])


def test_single_visit_uses_shrunk_historical_effect_without_leakage():
    built = features.add_quali_priors(_history_rows()).sort_values(["season", "round"])
    target = built.iloc[-1]

    # At the first Spa visit the driver was P18 against then-current P4 form,
    # a +14-place effect. One visit earns 1/(1+12) weight against current 6.75.
    expected = 6.75 + 14.0 / 13.0
    assert target["driver_roll_quali_5"] == pytest.approx(6.75)
    assert target["driver_circuit_exp"] == pytest.approx(expected)
    assert target["driver_circuit_roll_3"] == pytest.approx(expected)
    assert target["driver_circuit_reliability"] == pytest.approx(1.0 / 13.0)

    # The current qualifying result must not affect its own prior.
    changed = features.add_quali_priors(
        _history_rows(target_quali=22.0)
    ).sort_values(["season", "round"])
    assert changed.iloc[-1]["driver_circuit_exp"] == pytest.approx(expected)


def test_no_history_equals_recent_form_and_repeated_visits_gain_weight():
    assert apply_driver_circuit_effect(3.0, np.nan, 0) == 3.0

    one_visit = apply_driver_circuit_effect(3.0, 15.0, 1)
    four_visits = apply_driver_circuit_effect(3.0, 15.0, 4)
    assert one_visit == pytest.approx(3.0 + 15.0 / 13.0)
    assert four_visits == pytest.approx(3.0 + 15.0 / 4.0)
    assert driver_circuit_reliability(0) == 0.0
    assert driver_circuit_reliability(4) > driver_circuit_reliability(1)


def test_reliability_is_diagnostic_only_not_a_ranker_feature():
    columns = [
        "driver_roll_quali_5",
        "driver_circuit_exp",
        "driver_circuit_reliability",
        "driver_circuit_roll_3_reliability",
    ]
    selected = trainer.build_quali_feature_list(columns)
    assert "driver_circuit_exp" in selected
    assert "driver_circuit_reliability" not in selected
    assert "driver_circuit_roll_3_reliability" not in selected


def test_live_recomputation_matches_training_and_excludes_target_future(tmp_path, monkeypatch):
    model_rows_dir = tmp_path / "model_rows"
    model_rows_dir.mkdir()
    history = _history_rows(target_quali=22.0)
    history = pd.concat([
        history,
        pd.DataFrame([{
            "season": 2026, "round": 1, "driver_id": "rookie",
            "constructor_id": "team", "circuit_id": "spa",
            "quali_position": 1.0,
        }]),
    ], ignore_index=True)
    history.to_parquet(model_rows_dir / "all_model_rows.parquet", index=False)
    monkeypatch.setattr(predictions, "JOLPICA_MODEL_ROWS_DIR", model_rows_dir)

    live = pd.DataFrame([{
        "season": 2025,
        "round": 1,
        "driver_id": "rookie",
        "constructor_id": "team",
        "driver_roll_quali_5": 6.75,
        "constructor_roll_quali_5": 6.75,
        "driver_circuit_exp": np.nan,
        "driver_circuit_roll_3": np.nan,
        "constructor_circuit_exp": np.nan,
    }])
    rebuilt = predictions._recompute_circuit_features(
        live, "spa", 2025, 1
    ).iloc[0]
    expected = 6.75 + 14.0 / 13.0

    assert rebuilt["driver_circuit_exp"] == pytest.approx(expected)
    assert rebuilt["driver_circuit_roll_3"] == pytest.approx(expected)
    assert rebuilt["driver_circuit_reliability"] == pytest.approx(1.0 / 13.0)

    no_history = predictions._recompute_circuit_features(
        live.copy(), "brand_new_track", 2025, 1
    ).iloc[0]
    assert no_history["driver_circuit_exp"] == pytest.approx(6.75)
    assert no_history["driver_circuit_reliability"] == 0.0


def test_similarity_recomputation_excludes_target_and_future_rows(tmp_path, monkeypatch):
    model_rows_dir = tmp_path / "model_rows"
    model_rows_dir.mkdir()
    pd.DataFrame([
        {"season": 2024, "round": 1, "driver_id": "rookie", "circuit_id": "monza",
         "points": 10.0, "finish_position": 5.0, "quali_position": 4.0},
        {"season": 2025, "round": 1, "driver_id": "rookie", "circuit_id": "spa",
         "points": 100.0, "finish_position": 1.0, "quali_position": 1.0},
        {"season": 2026, "round": 1, "driver_id": "rookie", "circuit_id": "spa",
         "points": 200.0, "finish_position": 1.0, "quali_position": 1.0},
    ]).to_parquet(model_rows_dir / "all_model_rows.parquet", index=False)
    monkeypatch.setattr(predictions, "JOLPICA_MODEL_ROWS_DIR", model_rows_dir)
    live = pd.DataFrame([{"driver_id": "rookie"}])

    rebuilt = predictions._recompute_sim_features(live, "spa", 2025, 1).iloc[0]
    assert rebuilt["sim_weighted_points_3"] == pytest.approx(10.0)
    assert rebuilt["sim_weighted_points_5"] == pytest.approx(10.0)


def test_constructor_circuit_prior_shifts_whole_race_not_teammate_row():
    rows = pd.DataFrame([
        {"season": 2024, "round": 1, "driver_id": "a", "constructor_id": "team",
         "circuit_id": "spa", "quali_position": 5.0},
        {"season": 2024, "round": 1, "driver_id": "b", "constructor_id": "team",
         "circuit_id": "spa", "quali_position": 7.0},
        {"season": 2025, "round": 1, "driver_id": "a", "constructor_id": "team",
         "circuit_id": "spa", "quali_position": 1.0},
        {"season": 2025, "round": 1, "driver_id": "b", "constructor_id": "team",
         "circuit_id": "spa", "quali_position": 22.0},
    ])
    built = features.add_quali_priors(rows)
    target = built[(built["season"] == 2025) & (built["round"] == 1)]

    assert target["constructor_circuit_exp"].tolist() == pytest.approx([6.0, 6.0])


def test_current_season_circuit_metadata_survives_without_races_csv(tmp_path, monkeypatch):
    normalized = tmp_path / "normalized"
    year_dir = normalized / "2026"
    year_dir.mkdir(parents=True)
    pd.DataFrame([{
        "season": 2026, "round": 2, "circuit_id": "spa",
        "driver_id": "rookie", "constructor_id": "team", "grid": 3,
        "finish_position": 4, "position_text": "P4", "points": 12.0,
        "status": "Finished", "laps_completed": 44, "quali_position": 3,
    }]).to_csv(year_dir / "race_results.csv", index=False)
    pd.DataFrame([{
        "season": 2026, "round": 2, "driver_id": "rookie",
        "sprint_position": 2, "points": 7.0, "grid": 2,
    }]).to_csv(year_dir / "sprint_results.csv", index=False)

    monkeypatch.setattr(features, "JOLPICA_NORMALIZED_DIR", normalized)
    monkeypatch.setattr(features, "ALL_SEASONS", [2026])
    loaded = features.load_all_normalized_data().iloc[0]

    assert loaded["circuit_id"] == "spa"
    assert bool(loaded["has_sprint"])
