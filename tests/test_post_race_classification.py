"""Regression tests for Jolpica classified-result handling."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_pipeline_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "pipeline" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


post_race = _load_pipeline_module("post_race_analysis_test", "09_post_race_analysis.py")
actual_points = _load_pipeline_module("actual_fantasy_points_test", "11_actual_fantasy_points.py")


def _result(
    *,
    driver_id: str,
    position: int,
    position_text: str,
    status: str,
) -> dict:
    return {
        "position": str(position),
        "positionText": position_text,
        "points": "0",
        "grid": str(position),
        "status": status,
        "Driver": {"driverId": driver_id, "code": driver_id[:3].upper()},
        "Constructor": {"constructorId": "test_team"},
    }


@pytest.mark.parametrize(
    ("position_text", "status"),
    [
        ("8", "Lapped"),
        ("9", "+1 Lap"),
        ("10", "+2 Laps"),
        ("11", "Retired"),  # late retirement, but officially classified
    ],
)
def test_race_analysis_retains_all_classified_positions(position_text, status):
    raw = _result(
        driver_id="classified_driver",
        position=int(position_text),
        position_text=position_text,
        status=status,
    )

    parsed = post_race.analyze_race_results(
        {"Results": [raw]},
        {"classified_driver": "CLA"},
    )[0]

    assert parsed["is_classified"] is True
    assert parsed["is_finished"] is True
    assert parsed["finish_position"] == int(position_text)
    assert parsed["classified_position"] == int(position_text)


@pytest.mark.parametrize("status", ["Lapped", "+1 Lap", "+2 Laps", "+ 3 laps"])
def test_status_fallback_recognizes_lapped_classifications(status):
    assert post_race.is_classified_result(
        {"positionText": "", "status": status}
    ) is True


def test_race_analysis_keeps_unclassified_order_but_nulls_finish_position():
    raw = _result(
        driver_id="retired_driver",
        position=20,
        position_text="R",
        status="Retired",
    )

    parsed = post_race.analyze_race_results(
        {"Results": [raw]},
        {"retired_driver": "RET"},
    )[0]

    assert parsed["is_classified"] is False
    assert parsed["finish_position"] is None
    assert parsed["classified_position"] == 20


def test_sprint_analysis_uses_same_classification_rule():
    raw = _result(
        driver_id="lapped_driver",
        position=12,
        position_text="12",
        status="Lapped",
    )

    parsed = post_race.analyze_sprint_results(
        {"SprintResults": [raw]},
        {"lapped_driver": "LAP"},
    )[0]

    assert parsed["is_classified"] is True
    assert parsed["finish_position"] == 12


def test_actual_parser_preserves_result_order_for_true_dnf():
    raw = _result(
        driver_id="retired_driver",
        position=20,
        position_text="R",
        status="Retired",
    )
    raw["laps"] = "42"

    parsed, _ = actual_points.parse_race_results(
        {
            "MRData": {
                "RaceTable": {
                    "Races": [{
                        "raceName": "Test Grand Prix",
                        "Results": [raw],
                    }]
                }
            }
        }
    )

    assert parsed[0]["classified_position"] == 20
    assert parsed[0]["is_dnf"] is True


def test_fallback_output_separates_result_order_from_fantasy_position(monkeypatch):
    monkeypatch.setattr(actual_points, "load_id_maps", lambda: ({}, {}, {}))
    monkeypatch.setattr(
        actual_points,
        "load_drivers_info",
        lambda: {
            "LAP": {
                "driver_id": "LAP",
                "constructor_id": "test_team",
                "first_name": "Classified",
                "last_name": "Driver",
            },
            "RET": {
                "driver_id": "RET",
                "constructor_id": "test_team",
                "first_name": "Retired",
                "last_name": "Driver",
            },
        },
    )
    monkeypatch.setattr(
        actual_points,
        "load_constructors_info",
        lambda: {"test_team": {"name": "Test Team"}},
    )
    monkeypatch.setattr(
        actual_points,
        "load_fantasy_prices",
        lambda: ({"LAP": 10.0, "RET": 10.0}, {"test_team": 10.0}),
    )
    monkeypatch.setattr(actual_points, "load_detected_overtakes", lambda *_: ({}, {}))
    monkeypatch.setattr(actual_points, "load_seed_overtakes", lambda *_: ({}, {}))

    output = actual_points.calculate_from_post_race_analysis(
        13,
        2026,
        {
            "race": "Test Grand Prix",
            "results": [
                {
                    "driver_id": "LAP",
                    "constructor_id": "test_team",
                    "grid": 1,
                    "classified_position": 1,
                    "finish_position": 1,
                    "status": "Lapped",
                    "is_classified": True,
                    "is_finished": True,
                },
                {
                    "driver_id": "RET",
                    "constructor_id": "test_team",
                    "grid": 2,
                    "classified_position": 2,
                    "finish_position": None,
                    "status": "Engine",
                    "is_classified": False,
                    "is_finished": False,
                },
            ],
        },
    )
    drivers = {driver["driver_id"]: driver for driver in output["drivers"]}

    assert drivers["LAP"]["classified_position"] == 1
    assert drivers["LAP"]["race_position"] == 1
    assert drivers["LAP"]["is_dnf"] is False
    assert drivers["RET"]["classified_position"] == 2
    assert drivers["RET"]["race_position"] is None
    assert drivers["RET"]["is_dnf"] is True
    assert drivers["RET"]["race_points"] == actual_points.RACE_DNF_DSQ_PENALTY
