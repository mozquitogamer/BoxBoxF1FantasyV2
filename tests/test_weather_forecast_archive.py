"""Weather retrievals produce immutable, timestamped evaluation evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import weather_forecast


def _forecast() -> dict:
    return {
        "round": 14,
        "race": "Dutch Grand Prix",
        "race_date": "2026-08-23",
        "forecast_window": {
            "start": "2026-08-21",
            "end": "2026-08-23",
        },
    }


def test_weather_snapshot_is_timestamped_and_contains_raw_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(weather_forecast, "FORECAST_ARCHIVE_DIR", tmp_path)
    output = _forecast()
    provider = {
        "latitude": 52.3,
        "hourly": {"time": ["2026-08-23T14:00"]},
    }
    retrieved = datetime(2026, 8, 20, 8, 30, tzinfo=timezone.utc)

    path = weather_forecast.archive_weather_snapshot(
        output,
        provider,
        retrieved_at=retrieved,
    )

    saved = json.loads(path.read_text())
    assert path.name == "2026-08-20T08-30-00.000000Z_open_meteo.json"
    assert saved["target"]["round"] == 14
    assert saved["retrieved_at"] == retrieved.isoformat()
    assert saved["provider_response"] == provider
    assert saved["provider_response_sha256"]
    assert output["forecast_snapshot_id"] in path.name


def test_weather_snapshot_never_overwrites_same_retrieval(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(weather_forecast, "FORECAST_ARCHIVE_DIR", tmp_path)
    retrieved = datetime(2026, 8, 20, 8, 30, tzinfo=timezone.utc)
    weather_forecast.archive_weather_snapshot(
        _forecast(), {"hourly": {}}, retrieved_at=retrieved
    )

    with pytest.raises(FileExistsError):
        weather_forecast.archive_weather_snapshot(
            _forecast(), {"hourly": {}}, retrieved_at=retrieved
        )
