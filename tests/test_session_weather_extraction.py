from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "pipeline" / "03c_extract_session_weather.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_session_weather", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _weather_row(round_num: int, session: str, precip_minutes: int) -> dict:
    return {
        "season": 2026,
        "round": round_num,
        "session_name": {"Qualifying": "Q", "Race": "R"}[session],
        "session_code_raw": session,
        "n_samples": 60,
        "was_wet": precip_minutes >= 5,
        "precip_minutes": precip_minutes,
        "pct_session_wet": precip_minutes / 60,
        "track_temp_avg": 30.0,
        "track_temp_min": 25.0,
        "track_temp_max": 35.0,
        "air_temp_avg": 20.0,
        "humidity_avg": 60.0,
        "wind_avg": 2.0,
    }


def test_force_single_round_preserves_other_rounds(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "WEATHER_DIR", tmp_path)
    monkeypatch.setattr(module, "list_completed_rounds", lambda year: [1, 2])

    original = pd.DataFrame(
        [
            _weather_row(1, "Race", 0),
            _weather_row(2, "Qualifying", 1),
            _weather_row(2, "Race", 2),
        ]
    )
    original.to_parquet(tmp_path / "session_weather_year2026.parquet", index=False)

    monkeypatch.setattr(
        module,
        "extract_round",
        lambda year, round_num: [
            _weather_row(round_num, "Qualifying", 8),
            _weather_row(round_num, "Race", 9),
        ],
    )

    assert module.process_year(2026, only_round=2, force=True) == 2

    refreshed = pd.read_parquet(tmp_path / "session_weather_year2026.parquet")
    assert set(refreshed["round"]) == {1, 2}
    assert len(refreshed) == 3
    assert int(
        refreshed.loc[
            (refreshed["round"] == 1)
            & (refreshed["session_code_raw"] == "Race"),
            "precip_minutes",
        ].iloc[0]
    ) == 0
    assert int(
        refreshed.loc[
            (refreshed["round"] == 2)
            & (refreshed["session_code_raw"] == "Race"),
            "precip_minutes",
        ].iloc[0]
    ) == 9


def test_force_refresh_keeps_old_session_when_reload_fails(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "WEATHER_DIR", tmp_path)
    monkeypatch.setattr(module, "list_completed_rounds", lambda year: [2])

    original = pd.DataFrame(
        [
            _weather_row(2, "Qualifying", 1),
            _weather_row(2, "Race", 2),
        ]
    )
    original.to_parquet(tmp_path / "session_weather_year2026.parquet", index=False)

    # Simulate a partial FastF1/cache failure: only qualifying re-extracts.
    monkeypatch.setattr(
        module,
        "extract_round",
        lambda year, round_num: [_weather_row(round_num, "Qualifying", 8)],
    )

    assert module.process_year(2026, only_round=2, force=True) == 1

    refreshed = pd.read_parquet(tmp_path / "session_weather_year2026.parquet")
    assert len(refreshed) == 2
    assert int(
        refreshed.loc[
            refreshed["session_code_raw"] == "Qualifying", "precip_minutes"
        ].iloc[0]
    ) == 8
    assert int(
        refreshed.loc[
            refreshed["session_code_raw"] == "Race", "precip_minutes"
        ].iloc[0]
    ) == 2
