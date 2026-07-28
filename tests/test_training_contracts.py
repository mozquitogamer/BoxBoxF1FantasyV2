"""Regression tests for model-population, feature, and weighting contracts."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "train_models_contracts", ROOT / "pipeline" / "05_train_models.py"
)
TRAIN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TRAIN)


def test_sprint_features_exclude_future_main_quali_and_targets() -> None:
    race_features = [
        "driver_roll_quali_3",
        "quali_position",
        "is_pole_position",
        "is_front_row",
        "is_top10_quali",
        "grid_advantage",
        "weather_was_wet_race",
        "sprint_position",
        "sprint_points",
    ]
    columns = race_features + [
        "sprint_grid",
        "sprint_is_front_row",
        "sprint_is_top3",
        "sprint_is_top10",
        "sprint_grid_advantage",
        "weather_was_wet_sprint",
    ]

    result = TRAIN.build_sprint_feature_list(
        race_features, columns, include_weather=True
    )

    assert "driver_roll_quali_3" in result
    assert "sprint_grid" in result
    assert "weather_was_wet_sprint" in result
    assert "weather_was_wet_race" not in result
    assert "sprint_position" not in result
    assert "sprint_points" not in result
    assert not (set(result) & TRAIN.SPRINT_FUTURE_QUALI_FEATURES)


def test_position_rankers_exclude_observed_weather_by_default() -> None:
    columns = [
        "driver_roll_quali_3",
        *TRAIN.WEATHER_QUALI_FEATURES,
        *TRAIN.WEATHER_RACE_FEATURES,
        *TRAIN.WEATHER_SPRINT_FEATURES,
    ]

    quali = TRAIN.build_quali_feature_list(columns)
    race = TRAIN.build_race_feature_list(quali, columns)
    sprint = TRAIN.build_sprint_feature_list(race, columns)

    assert not (set(quali) & TRAIN.ALL_SESSION_WEATHER_FEATURES)
    assert not (set(race) & TRAIN.ALL_SESSION_WEATHER_FEATURES)
    assert not (set(sprint) & TRAIN.ALL_SESSION_WEATHER_FEATURES)


def test_observed_weather_can_be_enabled_for_labelled_oracle_diagnostics() -> None:
    columns = [
        "driver_roll_quali_3",
        *TRAIN.WEATHER_QUALI_FEATURES,
        *TRAIN.WEATHER_RACE_FEATURES,
        *TRAIN.WEATHER_SPRINT_FEATURES,
    ]

    quali = TRAIN.build_quali_feature_list(columns, include_weather=True)
    race = TRAIN.build_race_feature_list(
        quali, columns, include_weather=True
    )
    sprint = TRAIN.build_sprint_feature_list(
        race, columns, include_weather=True
    )

    assert set(TRAIN.WEATHER_QUALI_FEATURES) <= set(quali)
    assert set(TRAIN.WEATHER_RACE_FEATURES) <= set(race)
    assert set(TRAIN.WEATHER_SPRINT_FEATURES) <= set(sprint)


def test_position_rankers_exclude_unversioned_manual_ratings() -> None:
    columns = [
        "driver_roll_quali_3",
        *sorted(TRAIN.UNVERSIONED_MANUAL_RATING_FEATURES),
    ]

    quali = TRAIN.build_quali_feature_list(columns)
    race = TRAIN.build_race_feature_list(quali, columns)

    assert "driver_roll_quali_3" in quali
    assert not (set(quali) & TRAIN.UNVERSIONED_MANUAL_RATING_FEATURES)
    assert not (set(race) & TRAIN.UNVERSIONED_MANUAL_RATING_FEATURES)


def test_missing_sprint_grid_stays_missing_in_derived_features() -> None:
    frame = pd.DataFrame({"sprint_grid": [1.0, np.nan, 11.0]})

    result = TRAIN.add_sprint_grid_features(frame)

    assert result.loc[0, "sprint_is_front_row"] == 1
    assert pd.isna(result.loc[1, "sprint_is_front_row"])
    assert result.loc[2, "sprint_is_top10"] == 0
    assert pd.isna(result.loc[1, "sprint_grid_advantage"])


def test_classified_finisher_population_excludes_retirements_and_dsq() -> None:
    frame = pd.DataFrame(
        {
            "finish_position": [1.0, 10.0, 18.0, 20.0],
            "is_dnf": [0, 0, 1, 0],
            "is_dsq": [0, 0, 0, 1],
            "is_dns": [0, 0, 0, 0],
        }
    )

    assert TRAIN.classified_finisher_mask(frame).tolist() == [
        True,
        True,
        False,
        False,
    ]


def test_catboost_receives_row_level_group_weights(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePool:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeCatBoost:
        def __init__(self, _params):
            pass

        def fit(self, _pool):
            return self

        def save_model(self, path):
            captured["saved_path"] = str(path)

    fake_module = types.SimpleNamespace(CatBoost=FakeCatBoost, Pool=FakePool)
    monkeypatch.setitem(sys.modules, "catboost", fake_module)

    weights = np.asarray([1.0, 1.0, 2.5, 2.5])
    TRAIN.train_and_save_catboost_race(
        pd.DataFrame({"feature": [1.0, 2.0, 3.0, 4.0]}),
        np.asarray([4.0, 3.0, 2.0, 1.0]),
        np.asarray([0, 0, 1, 1]),
        Path("unused.cbm"),
        "test",
        row_group_weights=weights,
    )

    assert np.array_equal(captured["group_weight"], weights)
