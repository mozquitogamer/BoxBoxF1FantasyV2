"""Current-weekend FP must join by driver without changing seat identity."""

import importlib

import numpy as np
import pandas as pd
import pytest


predictions = importlib.import_module("pipeline.06_run_predictions")


def _priors():
    return pd.DataFrame({
        "driver_id": ["max_verstappen", "russell"],
        "constructor_id": ["red_bull", "mercedes"],
        "round": [14, 14],
        "best_lap_time": [90.0, 92.0],
        "long_run_avg": [101.0, 102.0],
    })


def test_mixed_fp_ids_refresh_pace_but_preserve_round_and_seats():
    priors = _priors()
    before = priors.copy(deep=True)
    fp = pd.DataFrame({
        "driver_id": ["VER", "russell"],
        "constructor_id": ["ferrari", "ferrari"],
        "round": [4, 4],
        "best_lap_time": [88.0, np.nan],
        "long_run_avg": [np.nan, 99.5],
        "new_metric": [1.0, 2.0],
    })

    assembled = predictions.assemble_prediction_rows(
        priors, fp, {"VER": "max_verstappen"}, 14, 2026
    )

    assert assembled["driver_id"].tolist() == priors["driver_id"].tolist()
    assert assembled["constructor_id"].tolist() == ["red_bull", "mercedes"]
    assert assembled["round"].tolist() == [14, 14]
    assert assembled["asset_id"].tolist() == ["VER", "RUS"]
    assert assembled["new_metric"].tolist() == [1.0, 2.0]
    assert assembled.loc[0, "best_lap_time"] == 88.0
    assert pd.isna(assembled.loc[1, "best_lap_time"])
    assert pd.isna(assembled.loc[0, "long_run_avg"])
    assert assembled.loc[1, "long_run_avg"] == 99.5
    pd.testing.assert_frame_equal(priors, before)


def test_priors_only_keeps_rows_and_missing_fp_features():
    priors = _priors()
    priors["best_lap_time"] = np.nan

    assembled = predictions.assemble_prediction_rows(priors, None, {}, 14, 2026)

    assert len(assembled) == 2
    assert assembled["best_lap_time"].isna().all()
    assert assembled["asset_id"].tolist() == ["VER", "RUS"]


def test_duplicate_fp_driver_cannot_duplicate_prediction_row():
    fp = pd.DataFrame({"driver_id": ["VER", "VER"], "best_lap_time": [88.0, 89.0]})
    with pytest.raises(ValueError, match="one row per driver"):
        predictions.assemble_prediction_rows(_priors(), fp, {"VER": "max_verstappen"}, 14, 2026)
