"""Regression tests for event-grain, leak-free Jolpica priors."""

import importlib
import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from pipeline.feature_engineering import engineer_features


features = importlib.import_module("pipeline.03b_build_jolpica_features")


def _quali_rows() -> pd.DataFrame:
    rows = []
    results = {
        1: {
            "team_a": {"a1": 2.0, "a2": 4.0},
            "team_b": {"b1": 10.0, "b2": 12.0},
        },
        2: {
            "team_a": {"a1": 1.0, "a2": 20.0},
            "team_b": {"b1": 3.0, "b2": 18.0},
        },
    }
    for round_number, constructors in results.items():
        for constructor, drivers in constructors.items():
            for driver, quali_position in drivers.items():
                rows.append({
                    "season": 2025,
                    "round": round_number,
                    "driver_id": driver,
                    "constructor_id": constructor,
                    "circuit_id": f"circuit_{round_number}",
                    "quali_position": quali_position,
                })
    return pd.DataFrame(rows)


def _race_rows() -> pd.DataFrame:
    rows = []
    finishes = {
        1: {"a1": 2.0, "a2": 4.0, "b1": 10.0, "b2": 12.0},
        2: {"a1": 6.0, "a2": 8.0, "b1": 3.0, "b2": 18.0},
        3: {"a1": 1.0, "a2": 20.0, "b1": 4.0, "b2": 17.0},
    }
    for round_number, driver_finishes in finishes.items():
        for driver, finish in driver_finishes.items():
            constructor = "team_a" if driver.startswith("a") else "team_b"
            rows.append({
                "season": 2025,
                "round": round_number,
                "driver_id": driver,
                "constructor_id": constructor,
                "quali_position": finish,
                "grid": finish,
                "finish_position": finish,
                "points": max(0.0, 11.0 - finish),
                "roll_finishpos_3": 8.0,
                "roll_finishpos_5": 9.0,
            })
    return pd.DataFrame(rows)


def test_constructor_and_field_quali_priors_shift_whole_event():
    rows = _quali_rows()
    built = features.add_quali_priors(rows)

    opening = built[built["round"] == 1]
    assert opening["constructor_quali_last"].isna().all()
    assert opening["field_season_avg_quali"].isna().all()

    second_round = built[built["round"] == 2]
    team_a = second_round[second_round["constructor_id"] == "team_a"]
    assert team_a["constructor_quali_last"].tolist() == pytest.approx([3.0, 3.0])
    assert team_a["constructor_roll_quali_3"].tolist() == pytest.approx([3.0, 3.0])

    # The completed first-round field average is (2 + 4 + 10 + 12) / 4 = 7.
    assert second_round["field_season_avg_quali"].tolist() == pytest.approx(
        [7.0] * len(second_round)
    )

    changed = rows.copy()
    changed.loc[changed["round"] == 2, "quali_position"] = [22.0, 21.0, 20.0, 19.0]
    changed_built = features.add_quali_priors(changed)
    changed_second = changed_built[changed_built["round"] == 2]
    changed_team_a = changed_second[changed_second["constructor_id"] == "team_a"]

    # Current-round results cannot alter their own constructor or field prior.
    assert changed_team_a["constructor_quali_last"].tolist() == pytest.approx([3.0, 3.0])
    assert changed_second["field_season_avg_quali"].tolist() == pytest.approx(
        [7.0] * len(changed_second)
    )


def test_constructor_quali_windows_count_events_not_driver_rows():
    rows = []
    event_means = {1: 2.0, 2: 4.0, 3: 6.0, 4: 8.0, 5: 20.0}
    for round_number, event_mean in event_means.items():
        for driver, offset in (("a", -1.0), ("b", 1.0)):
            rows.append({
                "season": 2025,
                "round": round_number,
                "driver_id": driver,
                "constructor_id": "team",
                "circuit_id": f"circuit_{round_number}",
                "quali_position": event_mean + offset,
            })

    built = features.add_quali_priors(pd.DataFrame(rows))
    target = built[built["round"] == 5]

    # Three completed constructor events: means 4, 6, and 8.
    assert target["constructor_roll_quali_3"].tolist() == pytest.approx([6.0, 6.0])
    # Four completed events are available for the five-event window.
    assert target["constructor_roll_quali_5"].tolist() == pytest.approx([5.0, 5.0])


def test_team_recent_form_uses_completed_constructor_events():
    rows = _race_rows()
    built = features.add_race_model_features(rows)

    round_two = built[
        (built["constructor_id"] == "team_a") & (built["round"] == 2)
    ]
    assert round_two["team_recent_form"].tolist() == pytest.approx([3.0, 3.0])

    round_three = built[
        (built["constructor_id"] == "team_a") & (built["round"] == 3)
    ]
    # Prior team event means are 3.0 and 7.0.
    assert round_three["team_recent_form"].tolist() == pytest.approx([5.0, 5.0])

    changed = rows.copy()
    changed.loc[
        (changed["constructor_id"] == "team_a") & (changed["round"] == 3),
        "finish_position",
    ] = [22.0, 21.0]
    changed_built = features.add_race_model_features(changed)
    changed_round_three = changed_built[
        (changed_built["constructor_id"] == "team_a")
        & (changed_built["round"] == 3)
    ]
    assert changed_round_three["team_recent_form"].tolist() == pytest.approx([5.0, 5.0])


def test_constructor_dnf_rate_shifts_completed_event_and_matches_teammates():
    rows = pd.DataFrame([
        {"season": 2025, "round": 1, "constructor_id": "team", "driver_id": "a",
         "dnf_mechanical": 1},
        {"season": 2025, "round": 1, "constructor_id": "team", "driver_id": "b",
         "dnf_mechanical": 0},
        {"season": 2025, "round": 2, "constructor_id": "team", "driver_id": "a",
         "dnf_mechanical": 0},
        {"season": 2025, "round": 2, "constructor_id": "team", "driver_id": "b",
         "dnf_mechanical": 0},
        {"season": 2025, "round": 3, "constructor_id": "team", "driver_id": "a",
         "dnf_mechanical": 1},
        {"season": 2025, "round": 3, "constructor_id": "team", "driver_id": "b",
         "dnf_mechanical": 1},
    ])

    built = features.add_event_rolling_rate(
        rows,
        "constructor_id",
        "dnf_mechanical",
        5,
        "constructor_rate",
    )
    assert built[built["round"] == 1]["constructor_rate"].isna().all()
    assert built[built["round"] == 2]["constructor_rate"].tolist() == pytest.approx(
        [0.5, 0.5]
    )
    # Current round 3 is excluded: mean of event rates 0.5 and 0.0.
    assert built[built["round"] == 3]["constructor_rate"].tolist() == pytest.approx(
        [0.25, 0.25]
    )


def test_season_progress_uses_active_schedule_not_loaded_max():
    schedule = {
        "season": 2099,
        "races": [
            {"round": 1, "cancelled": False},
            {"round": 2, "cancelled": True},
            {"round": 3, "cancelled": False},
            {"round": 4, "cancelled": False},
        ],
    }

    class _InMemorySchedule:
        def __truediv__(self, _name):
            return self

        @staticmethod
        def exists():
            return True

        @staticmethod
        def read_text(encoding="utf-8"):
            return json.dumps(schedule)

    rows = pd.DataFrame({
        "season": [2099, 2099],
        "round": [1, 3],
    })
    with patch.object(features, "SEED_DIR", _InMemorySchedule()):
        progress = features.compute_season_progress(rows)

    assert progress.tolist() == pytest.approx([1.0 / 3.0, 2.0 / 3.0])
    assert progress.max() < 1.0


def test_theoretical_best_requires_all_three_sectors():
    rows = pd.DataFrame({
        "best_sector_1": [30.0, 30.0],
        "best_sector_2": [31.0, np.nan],
        "best_sector_3": [32.0, 32.0],
    })
    built = engineer_features(rows)

    assert built.loc[0, "theoretical_best"] == pytest.approx(93.0)
    assert np.isnan(built.loc[1, "theoretical_best"])
