"""Grid-penalty resolution and fantasy-scoring regression tests."""

import importlib

import numpy as np
import pandas as pd

from config.grid_penalties import apply_grid_penalties
from config.settings import load_grid_penalties


fantasy = importlib.import_module("pipeline.07_calculate_fantasy")


QUALIFYING_ORDER = [
    "ANT", "VER", "HAM", "NOR", "HAD", "LEC", "RUS", "PIA", "LIN", "LAW", "COL",
    "GAS", "BOR", "BEA", "OCO", "ALB", "HUL", "SAI", "BOT", "PER", "STR", "ALO",
]


def test_round12_grid_is_unique_and_matches_confirmed_penalties():
    positions = np.arange(1, 23)
    rules = load_grid_penalties(12)
    grid = apply_grid_penalties(positions, QUALIFYING_ORDER, rules)
    by_driver = dict(zip(QUALIFYING_ORDER, grid))

    assert sorted(grid.tolist()) == list(range(1, 23))
    assert by_driver["NOR"] == 14
    assert by_driver["STR"] == 21
    assert by_driver["HAD"] == 22
    # Non-penalized drivers retain their relative order while filling gaps.
    assert by_driver["LEC"] == 4
    assert by_driver["ALO"] == 20


def test_no_penalties_is_identity_and_place_drop_caps_at_field_tail():
    positions = np.array([3, 1, 2])
    drivers = ["A", "B", "C"]
    assert apply_grid_penalties(positions, drivers, {}).tolist() == [3, 1, 2]

    penalized = apply_grid_penalties(positions, drivers, {"B": {"places": 10}})
    assert dict(zip(drivers, penalized)) == {"A": 2, "B": 3, "C": 1}


def test_backmarker_penalty_collision_still_builds_a_complete_grid():
    drivers = ["A", "B", "STR", "HAD"]
    positions = np.arange(1, 5)
    grid = apply_grid_penalties(
        positions,
        drivers,
        {"STR": {"places": 10}, "HAD": {"back_of_grid": True}},
    )

    assert sorted(grid.tolist()) == [1, 2, 3, 4]
    assert dict(zip(drivers, grid))["STR"] == 3
    assert dict(zip(drivers, grid))["HAD"] == 4


def test_round12_rules_resolve_every_sampled_qualifying_permutation():
    rng = np.random.default_rng(42)
    rules = load_grid_penalties(12)
    for _ in range(1_000):
        positions = rng.permutation(np.arange(1, 23))
        grid = apply_grid_penalties(positions, QUALIFYING_ORDER, rules)
        assert sorted(grid.tolist()) == list(range(1, 23))
        assert grid[QUALIFYING_ORDER.index("HAD")] == 22


def test_driver_fantasy_keeps_quali_points_but_uses_penalized_grid(monkeypatch):
    predictions = pd.DataFrame([{
        "driver_id": "norris",
        "driver_abbrev": "NOR",
        "constructor_id": "mclaren",
        "predicted_quali_position": 4,
        "predicted_grid_position": 14,
        "grid_penalty_places": 10,
        "grid_back_of_grid": False,
        "predicted_race_position": 5,
        "confidence": 80,
    }])
    monkeypatch.setattr(fantasy, "load_id_maps", lambda: ({"norris": "NOR"}, {"NOR": "norris"}))
    monkeypatch.setattr(fantasy, "load_fantasy_prices", lambda: ({"NOR": 25.0}, {}))
    monkeypatch.setattr(fantasy, "calculate_risk_ratings", lambda _: {"norris": 0.0})
    monkeypatch.setattr(fantasy, "load_recent_fantasy_points", lambda *_: 0.0)
    monkeypatch.setattr(fantasy, "load_dotd_overrides", lambda *_: {})
    monkeypatch.setattr(fantasy, "race_name_for_round", lambda *_: "Belgian Grand Prix")
    monkeypatch.setattr(fantasy, "get_circuit_id_from_race_name", lambda *_: "spa")
    monkeypatch.setattr(fantasy, "overtake_multiplier", lambda *_: 1.0)

    result = fantasy.calculate_driver_fantasy(predictions, 12).iloc[0]

    assert result["predicted_quali_position"] == 4
    assert result["predicted_grid_position"] == 14
    assert result["expected_quali_pts"] == fantasy.calc_qualifying_points_driver(4)
    assert result["expected_positions_gained_lost"] == 9
    assert result["expected_overtakes"] == fantasy.estimate_overtakes(14, 5)
