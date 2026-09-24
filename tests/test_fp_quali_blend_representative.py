"""Sparse practice laps must not create phantom qualifying position losses."""

import importlib

import pandas as pd


predictions = importlib.import_module("pipeline.06_run_predictions")


def test_representative_fp_pace_excludes_disrupted_five_lap_sample():
    features = pd.DataFrame(
        {
            "total_laps": [5, 12, 3, None],
            "best_lap_time": [107.873, 106.440, 106.0, None],
            "best_5_lap_avg": [120.8576, 108.0, 107.0, None],
        },
        index=["disrupted", "representative", "too_few", "missing"],
    )

    result = predictions.representative_fp_pace_mask(features)

    assert result.to_dict() == {
        "disrupted": False,
        "representative": True,
        "too_few": False,
        "missing": False,
    }
