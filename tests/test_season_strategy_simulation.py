"""Unit tests for the sequential F1 Fantasy season experiment."""

from __future__ import annotations

import importlib

import numpy as np


sim = importlib.import_module("pipeline.simulate_fantasy_season_strategies")


def test_expected_price_change_matches_ppm_brackets_and_floor() -> None:
    assert sim._expected_price_change(
        price=20.0, projected_points=30.0, past_points=[25.0, 25.0]
    ) == 0.3
    assert sim._expected_price_change(
        price=10.0, projected_points=10.0, past_points=[10.0, 10.0]
    ) == 0.2
    assert sim._expected_price_change(
        price=10.0, projected_points=0.0, past_points=[0.0, 0.0]
    ) == -0.6
    assert sim._expected_price_change(
        price=3.0, projected_points=0.0, past_points=[0.0, 0.0]
    ) == 0.0


def _synthetic_round() -> sim.RoundInputs:
    drivers = ("A", "B", "C", "D", "E")
    constructors = ("X", "Y")
    return sim.RoundInputs(
        round_num=1,
        race_name="Test GP",
        reconstructed=False,
        archive_path="test.json",
        drivers=drivers,
        constructors=constructors,
        driver_projection=np.array([20, 18, 5, 4, 3], dtype=float),
        constructor_projection=np.array([30, 20], dtype=float),
        driver_p5=np.zeros(5),
        constructor_p5=np.zeros(2),
        driver_std=np.ones(5),
        driver_prices=np.ones(5),
        constructor_prices=np.ones(2),
        driver_close_prices=np.ones(5),
        constructor_close_prices=np.ones(2),
        driver_actual=np.array([10, 15, -20, 5, 3], dtype=float),
        constructor_actual=np.array([25, -10], dtype=float),
        driver_projected_gain=np.zeros(5),
        constructor_projected_gain=np.zeros(2),
    )


def _candidate(second: str | None = None) -> sim.Candidate:
    return sim.Candidate(
        drivers=("A", "B", "C", "D", "E"),
        constructors=("X", "Y"),
        cost=7.0,
        projected_points=0.0,
        projected_gain=0.0,
        utility=0.0,
        transfers=0,
        transfer_penalty=0,
        captain="A",
        second_captain=second,
        downside_risk=0.0,
        captain_gap=2.0,
        captain_uncertainty=1.0,
    )


def test_actual_chip_scoring() -> None:
    round_data = _synthetic_round()

    normal, captain, _, bonus = sim._actual_score(
        candidate=_candidate(), round_data=round_data, chip=None
    )
    assert captain == "A"
    assert bonus == 10
    assert normal == 38

    triple, captain, second, bonus = sim._actual_score(
        candidate=_candidate("B"),
        round_data=round_data,
        chip="3x_boost",
    )
    assert (captain, second, bonus, triple) == ("A", "B", 35, 63)

    protected, _, _, _ = sim._actual_score(
        candidate=_candidate(), round_data=round_data, chip="no_negative"
    )
    assert protected == 68

    autopilot, captain, _, bonus = sim._actual_score(
        candidate=_candidate(), round_data=round_data, chip="autopilot"
    )
    assert captain == "B"
    assert bonus == 15
    assert autopilot == 43


def test_v2_chip_policy_uses_track_risk_and_real_lineup_churn() -> None:
    rounds = sim.load_rounds()
    baseline = sim.simulate(rounds, strategy="max_points", chip_schedule={})
    schedule, _ = sim.choose_chip_schedule_v2(
        rounds,
        strategy="max_points",
        baseline=baseline,
    )
    played = sim.simulate(
        rounds,
        strategy="max_points",
        chip_schedule=schedule,
    )

    limitless_round = next(
        round_num for round_num, chip in schedule.items() if chip == "limitless"
    )
    genuine_difficulties = [
        round_data.overtaking_difficulty
        for round_data in rounds
        if not round_data.reconstructed
    ]
    selected_round = next(
        round_data
        for round_data in rounds
        if round_data.round_num == limitless_round
    )
    assert selected_round.overtaking_difficulty == max(genuine_difficulties)

    wildcard_row = next(
        row for row in played["rounds"] if row["chip"] == "wild_card"
    )
    assert wildcard_row["transfers"] >= 4

    for round_num in schedule:
        round_data = next(
            item for item in rounds if item.round_num == round_num
        )
        assert not round_data.reconstructed


def test_risk_profiles_change_lineup_using_negative_p5_exposure() -> None:
    round_data = sim.RoundInputs(
        round_num=1,
        race_name="Risk Test GP",
        reconstructed=False,
        archive_path="risk-test.json",
        drivers=("A", "B", "C", "D", "E", "F"),
        constructors=("X", "Y", "Z"),
        driver_projection=np.array([50, 40, 30, 20, 10, 5], dtype=float),
        constructor_projection=np.array([40, 20, 5], dtype=float),
        driver_p5=np.array([-20, -10, 0, 0, 0, 0], dtype=float),
        constructor_p5=np.array([-30, 0, 0], dtype=float),
        driver_std=np.ones(6),
        driver_prices=np.ones(6),
        constructor_prices=np.ones(3),
        driver_close_prices=np.ones(6),
        constructor_close_prices=np.ones(3),
        driver_actual=np.zeros(6),
        constructor_actual=np.zeros(3),
        driver_projected_gain=np.zeros(6),
        constructor_projected_gain=np.zeros(3),
    )
    combos = sim.build_combo_matrices(round_data)

    maximum = sim.choose_lineup(
        round_data=round_data,
        combos=combos,
        state=None,
        strategy="max_points",
        chip=None,
        risk_profile="maximum_tolerance",
    )
    total_avoidance = sim.choose_lineup(
        round_data=round_data,
        combos=combos,
        state=None,
        strategy="max_points",
        chip=None,
        risk_profile="total_avoidance",
    )

    assert maximum.downside_risk == 60.0
    assert total_avoidance.downside_risk == 10.0
    assert maximum.projected_points > total_avoidance.projected_points
    assert "X" in maximum.constructors
    assert "X" not in total_avoidance.constructors
