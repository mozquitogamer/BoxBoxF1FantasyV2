"""Inference-time weather schema and staleness regression tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_predictions_weather_contract",
    ROOT / "pipeline" / "06_run_predictions.py",
)
PREDICT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PREDICT)
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "weather_inference"


def test_all_session_models_receive_forecast_precip_minutes(monkeypatch) -> None:
    monkeypatch.setattr(PREDICT, "WEB_DATA_DIR", FIXTURE_DIR)

    enriched, metadata = PREDICT.inject_weather_features(
        pd.DataFrame({"driver_id": ["driver"]}), 99
    )

    assert enriched.loc[0, "weather_precip_minutes_quali"] == 10.0
    assert enriched.loc[0, "weather_precip_minutes_sprint"] == 5.0
    assert enriched.loc[0, "weather_precip_minutes_race"] == 15.0
    assert metadata["missing"] is False


def test_wrong_round_forecast_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(PREDICT, "WEB_DATA_DIR", FIXTURE_DIR)

    enriched, metadata = PREDICT.inject_weather_features(
        pd.DataFrame({"driver_id": ["driver"]}), 100
    )

    weather_columns = [
        f"weather_{metric}_{session}"
        for session in ("quali", "race", "sprint")
        for metric in (
            "was_wet",
            "track_temp",
            "air_temp",
            "humidity",
            "precip_minutes",
        )
    ]
    assert enriched[weather_columns].isna().all().all()
    assert metadata["missing"] is True
    assert metadata["stale"] is True
    assert metadata["weather_round"] == 99
