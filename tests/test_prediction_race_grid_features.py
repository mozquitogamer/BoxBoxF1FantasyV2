"""Qualifying classification and penalised race start stay separate."""

import importlib

import numpy as np
import pandas as pd
import pytest

from pipeline.feature_engineering import rederive_quali_dependent_features


predictions = importlib.import_module("pipeline.06_run_predictions")


def _prediction_rows():
    return pd.DataFrame({
        "driver_id": ["a", "b", "c", "d"],
        "predicted_quali_position": [1, 2, 3, 4],
        "actual_quali_position": [1.0, 2.0, np.nan, 4.0],
        "pace_rank": [2, 1, 3, 4],
        "overtaking_difficulty": [8.0] * 4,
        "team_strategy_rating": [6.0] * 4,
        "safety_car_probability": [0.4] * 4,
        "turn1_incident_risk": [0.2] * 4,
        "is_street": [1] * 4,
    })


def test_post_quali_penalty_changes_grid_but_not_model_classification():
    rows = _prediction_rows()
    before = rows.copy(deep=True)
    result = predictions.build_race_grid_features(
        rows,
        {"a": 1, "b": 2, "d": 4},
        True,
        {"B": {"places": 2}},
        {driver: driver.upper() for driver in rows["driver_id"]},
    )

    assert result["quali_position"].tolist() == [1, 2, 3, 4]
    assert result["predicted_grid_position"].tolist() == [1, 4, 2, 3]
    assert result["grid_penalty_places"].tolist() == [0, 2, 0, 0]
    assert result["grid"].tolist() == result["predicted_grid_position"].tolist()
    assert result.loc[1, "actual_quali_position"] == 2
    assert result.loc[1, "grid_advantage"] == 9.0
    assert result.loc[1, "is_front_row"] == 1
    assert result.loc[1, "front_row_advantage"] == 1.3
    assert result.loc[1, "quali_vs_fp_rank"] == 1
    assert result.loc[1, "strategy_sc_advantage"] == pytest.approx(0.24)
    pd.testing.assert_frame_equal(rows, before)


def test_pre_quali_uses_predicted_positions_even_when_actual_map_is_supplied():
    rows = _prediction_rows().drop(columns=[
        "overtaking_difficulty", "team_strategy_rating", "safety_car_probability",
        "turn1_incident_risk", "is_street",
    ])
    result = predictions.build_race_grid_features(
        rows, {"a": 4}, False, {}, {"a": "A", "b": "B", "c": "C", "d": "D"}
    )

    assert result["quali_position"].tolist() == [1, 2, 3, 4]
    assert result["predicted_grid_position"].tolist() == [1, 2, 3, 4]
    assert result["actual_quali_position"].tolist()[:2] == [1.0, 2.0]
    assert "grid_importance_factor" not in result.columns
    assert "top10_sc_interaction" not in result.columns


def test_shared_qualifying_features_accept_walk_forward_training_column():
    rows = pd.DataFrame({
        "quali_position": [1.0, 2.0],
        "predicted_quali_wf": [2.0, 1.0],
    })
    result = rederive_quali_dependent_features(rows, "predicted_quali_wf")

    assert result["is_pole_position"].tolist() == [0, 1]
    assert result["is_front_row"].tolist() == [1, 1]
    assert result["grid_advantage"].tolist() == [9.0, 10.0]
    assert rows.columns.tolist() == ["quali_position", "predicted_quali_wf"]
