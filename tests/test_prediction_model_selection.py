"""Model choice must match the evidence available at prediction time."""

import importlib


predictions = importlib.import_module("pipeline.06_run_predictions")

FEATURES = {
    "race_features": ["actual_quali", "form"],
    "race_fp_features": ["predicted_quali", "form"],
    "sprint_features": ["sprint_grid", "form"],
    "sprint_fp_features": ["predicted_grid", "form"],
}


def test_race_choice_tracks_qualifying_phase_and_fp_fallback(tmp_path):
    (tmp_path / "race_model_fp.json").touch()

    pre_fp = predictions.select_race_model(tmp_path, FEATURES, False, False, "xgboost")
    post_fp = predictions.select_race_model(tmp_path, FEATURES, False, True, "xgboost")
    post_quali = predictions.select_race_model(tmp_path, FEATURES, True, True, "xgboost")

    assert pre_fp.path.name == post_fp.path.name == "race_model_fp.json"
    assert pre_fp.features == post_fp.features == FEATURES["race_fp_features"]
    assert pre_fp.uses_fp_variant and post_fp.uses_fp_variant
    assert pre_fp.phase_label.startswith("pre-FP")
    assert post_fp.phase_label.startswith("post-FP")
    assert post_quali.path.name == "race_model.json"
    assert post_quali.features == FEATURES["race_features"]
    assert not post_quali.uses_fp_variant

    (tmp_path / "race_model_fp.json").unlink()
    fallback = predictions.select_race_model(tmp_path, FEATURES, False, True, "xgboost")
    assert fallback.path.name == "race_model.json"
    assert fallback.features == FEATURES["race_features"]


def test_race_algorithm_uses_matching_model_file(tmp_path):
    (tmp_path / "race_model_fp.json").touch()
    cbm = tmp_path / "race_model_fp.cbm"
    cbm.touch()

    selected = predictions.select_race_model(tmp_path, FEATURES, False, True, "catboost")
    assert selected.path == cbm
    assert selected.algorithm == "catboost"
    assert selected.features == FEATURES["race_fp_features"]

    cbm.unlink()
    fallback = predictions.select_race_model(tmp_path, FEATURES, False, True, "catboost")
    assert fallback.path.name == "race_model_fp.json"
    assert fallback.algorithm == "xgboost"


def test_sprint_choice_tracks_actual_grid_and_available_model(tmp_path):
    (tmp_path / "sprint_model.json").touch()
    (tmp_path / "sprint_model_fp.json").touch()

    predicted_grid = predictions.select_sprint_model(tmp_path, FEATURES, ["race"], False)
    actual_grid = predictions.select_sprint_model(tmp_path, FEATURES, ["race"], True)
    assert predicted_grid.path.name == "sprint_model_fp.json"
    assert predicted_grid.features == FEATURES["sprint_fp_features"]
    assert predicted_grid.uses_fp_variant
    assert actual_grid.path.name == "sprint_model.json"
    assert actual_grid.features == FEATURES["sprint_features"]
    assert not actual_grid.uses_fp_variant

    (tmp_path / "sprint_model_fp.json").unlink()
    fallback = predictions.select_sprint_model(tmp_path, FEATURES, ["race"], False)
    assert fallback.path.name == "sprint_model.json"
    assert fallback.features == FEATURES["sprint_features"]
    assert "falling back" in fallback.phase_label
