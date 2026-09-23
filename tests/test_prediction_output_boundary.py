"""Prediction output must keep its downstream schema and archive isolation."""

import importlib
import json

import pandas as pd


predictions = importlib.import_module("pipeline.06_run_predictions")


def test_output_projection_keeps_public_fields_without_mutating_model_rows():
    model_rows = pd.DataFrame({
        "driver_id": ["max_verstappen"],
        "driver_abbrev": ["VER"],
        "predicted_quali_position": [1],
        "predicted_race_position": [2],
        "predicted_sprint_position": [3],
        "driver_roll_quali_3": [1.5],
        "private_model_feature": [99],
    })
    before = model_rows.copy(deep=True)

    sprint = predictions.build_prediction_output(model_rows, 14, 2026, True)
    regular = predictions.build_prediction_output(model_rows, 16, 2026, False)

    assert sprint["predicted_sprint_position"].tolist() == [3]
    assert "predicted_sprint_position" not in regular
    assert "private_model_feature" not in sprint
    assert sprint[["season", "round", "is_sprint_weekend"]].iloc[0].tolist() == [2026, 14, True]
    pd.testing.assert_frame_equal(model_rows, before)


def test_suffixed_artifacts_are_paired_and_do_not_write_canonical_output(tmp_path, monkeypatch):
    monkeypatch.setattr(predictions, "PREDICTIONS_DIR", tmp_path)
    canonical, canonical_metadata = predictions.prediction_artifact_paths(17)
    horizon, horizon_metadata = predictions.prediction_artifact_paths(17, "horizon")
    output = pd.DataFrame({"driver_id": ["max_verstappen"], "round": [17]})
    metadata = {"phase": "pre_fp", "round": 17}

    predictions.save_prediction_artifacts(output, metadata, horizon, horizon_metadata)

    pd.testing.assert_frame_equal(pd.read_parquet(horizon), output)
    assert json.loads(horizon_metadata.read_text(encoding="utf-8")) == metadata
    assert not canonical.exists()
    assert not canonical_metadata.exists()
