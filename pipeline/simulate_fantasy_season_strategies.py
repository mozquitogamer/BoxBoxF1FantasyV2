"""Sequential 2026 F1 Fantasy strategy experiment.

Simulates two managers from a $100M round-one budget:

* ``max_points`` maximises the archived post-FP projected score.
* ``balanced`` remains points-first but values each projected $1M price rise
  as eight projected points.

Both managers carry their real team, bank balance, asset price changes, and
banked transfers from round to round.  All realised scoring uses the official
fantasy totals in ``data/seed/official_fantasy_points.json``.

The experiment intentionally distinguishes genuine prediction archives from
reconstructed ones.  Rounds 1-3 currently have reconstructed post-FP archives;
R6 onward has genuine lock-time archives.

Usage:
    python pipeline/simulate_fantasy_season_strategies.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import CURRENT_SEASON, SEED_DIR, WEB_DATA_DIR


STARTING_BUDGET = 100.0
TRANSFER_PENALTY = 10
INITIAL_FREE_TRANSFERS_AFTER_R1 = 2
MAX_BANKED_TRANSFERS = 5
MAX_PAID_TRANSFERS_PER_ROUND = 1
BALANCED_PRICE_GAIN_VALUE = 8.0
SPRINT_ROUNDS = {2, 6, 7, 11, 14, 18}
CHIPS = ("wild_card", "limitless", "3x_boost", "no_negative", "autopilot")
RAIN_RISK_BONUS = {"NONE": 0.0, "LOW": 1.0, "MEDIUM": 5.0, "HIGH": 10.0}


@dataclass
class TeamState:
    drivers: tuple[str, ...]
    constructors: tuple[str, ...]
    bank: float
    budget: float
    free_transfers: int


@dataclass
class Candidate:
    drivers: tuple[str, ...]
    constructors: tuple[str, ...]
    cost: float
    projected_points: float
    projected_gain: float
    utility: float
    transfers: int
    transfer_penalty: int
    captain: str
    second_captain: str | None
    downside_risk: float
    captain_gap: float
    captain_uncertainty: float


@dataclass
class RoundInputs:
    round_num: int
    race_name: str
    reconstructed: bool
    archive_path: str
    drivers: tuple[str, ...]
    constructors: tuple[str, ...]
    driver_projection: np.ndarray
    constructor_projection: np.ndarray
    driver_p5: np.ndarray
    constructor_p5: np.ndarray
    driver_std: np.ndarray
    driver_prices: np.ndarray
    constructor_prices: np.ndarray
    driver_close_prices: np.ndarray
    constructor_close_prices: np.ndarray
    driver_actual: np.ndarray
    constructor_actual: np.ndarray
    driver_projected_gain: np.ndarray
    constructor_projected_gain: np.ndarray
    circuit_id: str = "unknown"
    overtaking_difficulty: int = 5
    turn1_incident_risk: int = 5
    safety_car_probability: int = 5
    rain_risk: str = "NONE"
    weather_dnf_mult: float = 1.0
    mean_dnf_probability: float = 0.0


@dataclass
class ComboMatrices:
    driver_indices: np.ndarray
    constructor_indices: np.ndarray
    driver_cost: np.ndarray
    constructor_cost: np.ndarray
    driver_sum: np.ndarray
    constructor_sum: np.ndarray
    driver_top: np.ndarray
    driver_second: np.ndarray
    driver_top_index: np.ndarray
    driver_second_index: np.ndarray
    driver_nonnegative_sum: np.ndarray
    constructor_nonnegative_sum: np.ndarray
    driver_gain: np.ndarray
    constructor_gain: np.ndarray
    driver_downside: np.ndarray
    constructor_downside: np.ndarray


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _expected_price_change(
    *,
    price: float,
    projected_points: float,
    past_points: list[float],
) -> float:
    """Mirror the website's rolling-three PPM price-change heuristic."""
    all_scores = [*past_points, projected_points]
    last_three = all_scores[-3:]
    average_points = sum(last_three) / len(last_three)
    ppm = average_points / price if price else 0.0
    high_tier = price > 18.5
    if high_tier:
        changes = (0.3, 0.1, -0.1, -0.3)
    else:
        changes = (0.6, 0.2, -0.2, -0.6)
    if ppm >= 1.2:
        change = changes[0]
    elif ppm >= 0.9:
        change = changes[1]
    elif ppm >= 0.6:
        change = changes[2]
    else:
        change = changes[3]
    if price <= 3.001 and change < 0:
        return 0.0
    return change


def load_rounds() -> list[RoundInputs]:
    official = _load_json(SEED_DIR / "official_fantasy_points.json")["rounds"]
    prices = _load_json(SEED_DIR / "fantasy_prices.json")["price_history"]
    track_data = _load_json(WEB_DATA_DIR / "track_data.json")
    driver_roster = _load_json(SEED_DIR / "drivers.json")["drivers"]
    constructor_roster = _load_json(SEED_DIR / "constructors.json")["constructors"]
    driver_ids = tuple(row["driver_id"] for row in driver_roster)
    constructor_ids = tuple(row["constructor_id"] for row in constructor_roster)
    completed_rounds = sorted(int(value) for value in official)
    output: list[RoundInputs] = []

    driver_history: dict[str, list[float]] = {key: [] for key in driver_ids}
    constructor_history: dict[str, list[float]] = {
        key: [] for key in constructor_ids
    }

    for round_index, round_num in enumerate(completed_rounds):
        prior_price_key = "0" if round_index == 0 else str(completed_rounds[round_index - 1])
        opening = prices[prior_price_key]
        closing = prices[str(round_num)]
        archive = WEB_DATA_DIR / f"predictions_round{round_num}_post_fp.json"
        payload = _load_json(archive)
        if payload.get("phase") != "post_fp":
            raise ValueError(f"{archive.name} is not a post_fp archive")
        driver_rows = {row["driver_id"]: row for row in payload["drivers"]}
        constructor_rows = {
            row["constructor_id"]: row for row in payload["constructors"]
        }
        actual = official[str(round_num)]
        circuit_id = track_data["race_circuit_map"].get(actual["race"], "unknown")
        track_features = track_data["track_features"].get(circuit_id, {})
        weather = payload.get("weather_adjustments") or {}

        driver_projection = np.array(
            [
                float(
                    driver_rows[key].get("mc_total_mean")
                    if driver_rows[key].get("mc_total_mean") is not None
                    else driver_rows[key]["expected_points"]
                )
                for key in driver_ids
            ]
        )
        constructor_projection = np.array(
            [
                float(
                    constructor_rows[key].get("mc_total_mean")
                    if constructor_rows[key].get("mc_total_mean") is not None
                    else constructor_rows[key]["expected_points"]
                )
                for key in constructor_ids
            ]
        )
        driver_prices = np.array(
            [float(opening["drivers"][key]) for key in driver_ids]
        )
        constructor_prices = np.array(
            [float(opening["constructors"][key]) for key in constructor_ids]
        )
        driver_gain = np.array(
            [
                _expected_price_change(
                    price=driver_prices[index],
                    projected_points=driver_projection[index],
                    past_points=driver_history[key],
                )
                for index, key in enumerate(driver_ids)
            ]
        )
        constructor_gain = np.array(
            [
                _expected_price_change(
                    price=constructor_prices[index],
                    projected_points=constructor_projection[index],
                    past_points=constructor_history[key],
                )
                for index, key in enumerate(constructor_ids)
            ]
        )

        output.append(
            RoundInputs(
                round_num=round_num,
                race_name=actual["race"],
                reconstructed=bool(payload.get("reconstructed", False)),
                archive_path=str(archive.relative_to(ROOT)).replace("\\", "/"),
                drivers=driver_ids,
                constructors=constructor_ids,
                driver_projection=driver_projection,
                constructor_projection=constructor_projection,
                driver_p5=np.array(
                    [float(driver_rows[key].get("mc_total_p5", 0.0)) for key in driver_ids]
                ),
                constructor_p5=np.array(
                    [
                        float(constructor_rows[key].get("mc_total_p5", 0.0))
                        for key in constructor_ids
                    ]
                ),
                driver_std=np.array(
                    [
                        float(driver_rows[key].get("mc_total_std", 0.0))
                        for key in driver_ids
                    ]
                ),
                driver_prices=driver_prices,
                constructor_prices=constructor_prices,
                driver_close_prices=np.array(
                    [float(closing["drivers"][key]) for key in driver_ids]
                ),
                constructor_close_prices=np.array(
                    [float(closing["constructors"][key]) for key in constructor_ids]
                ),
                driver_actual=np.array(
                    [float(actual["drivers"][key]) for key in driver_ids]
                ),
                constructor_actual=np.array(
                    [float(actual["constructors"][key]) for key in constructor_ids]
                ),
                driver_projected_gain=driver_gain,
                constructor_projected_gain=constructor_gain,
                circuit_id=circuit_id,
                overtaking_difficulty=int(
                    track_features.get("overtaking_difficulty", 5)
                ),
                turn1_incident_risk=int(
                    track_features.get("turn1_incident_risk", 5)
                ),
                safety_car_probability=int(
                    track_features.get("safety_car_probability", 5)
                ),
                rain_risk=str(weather.get("rain_risk") or "NONE").upper(),
                weather_dnf_mult=float(weather.get("dnf_mult") or 1.0),
                mean_dnf_probability=float(
                    np.mean(
                        [
                            float(driver_rows[key].get("dnf_probability", 0.0))
                            for key in driver_ids
                        ]
                    )
                ),
            )
        )

        for key in driver_ids:
            driver_history[key].append(float(actual["drivers"][key]))
        for key in constructor_ids:
            constructor_history[key].append(float(actual["constructors"][key]))

    return output


def build_combo_matrices(round_data: RoundInputs) -> ComboMatrices:
    driver_indices = np.array(
        list(itertools.combinations(range(len(round_data.drivers)), 5)),
        dtype=np.int16,
    )
    constructor_indices = np.array(
        list(itertools.combinations(range(len(round_data.constructors)), 2)),
        dtype=np.int16,
    )
    driver_values = round_data.driver_projection[driver_indices]
    sorted_order = np.argsort(driver_values, axis=1)
    rows = np.arange(len(driver_indices))
    top_column = sorted_order[:, -1]
    second_column = sorted_order[:, -2]
    top_index = driver_indices[rows, top_column]
    second_index = driver_indices[rows, second_column]
    return ComboMatrices(
        driver_indices=driver_indices,
        constructor_indices=constructor_indices,
        driver_cost=round_data.driver_prices[driver_indices].sum(axis=1),
        constructor_cost=round_data.constructor_prices[constructor_indices].sum(axis=1),
        driver_sum=driver_values.sum(axis=1),
        constructor_sum=round_data.constructor_projection[constructor_indices].sum(axis=1),
        driver_top=round_data.driver_projection[top_index],
        driver_second=round_data.driver_projection[second_index],
        driver_top_index=top_index,
        driver_second_index=second_index,
        driver_nonnegative_sum=np.maximum(driver_values, 0).sum(axis=1),
        constructor_nonnegative_sum=np.maximum(
            round_data.constructor_projection[constructor_indices], 0
        ).sum(axis=1),
        driver_gain=round_data.driver_projected_gain[driver_indices].sum(axis=1),
        constructor_gain=round_data.constructor_projected_gain[
            constructor_indices
        ].sum(axis=1),
        driver_downside=np.maximum(
            -round_data.driver_p5[driver_indices], 0
        ).sum(axis=1),
        constructor_downside=np.maximum(
            -round_data.constructor_p5[constructor_indices], 0
        ).sum(axis=1),
    )


def _count_transfers(
    combinations: np.ndarray,
    current_ids: tuple[str, ...],
    all_ids: tuple[str, ...],
    slot_count: int,
) -> np.ndarray:
    if not current_ids:
        return np.zeros(len(combinations), dtype=np.int16)
    lookup = {key: index for index, key in enumerate(all_ids)}
    current_indices = np.array([lookup[key] for key in current_ids])
    shared = np.isin(combinations, current_indices).sum(axis=1)
    return slot_count - shared


def choose_lineup(
    *,
    round_data: RoundInputs,
    combos: ComboMatrices,
    state: TeamState | None,
    strategy: str,
    chip: str | None,
) -> Candidate:
    """Return the best legal lineup for one round and manager policy."""
    cost = combos.driver_cost[:, None] + combos.constructor_cost[None, :]
    base_asset_points = combos.driver_sum[:, None] + combos.constructor_sum[None, :]
    normal_projected = base_asset_points + combos.driver_top[:, None]
    if chip == "3x_boost":
        played_projected = (
            base_asset_points
            + 2 * combos.driver_top[:, None]
            + combos.driver_second[:, None]
        )
    elif chip == "no_negative":
        played_projected = (
            combos.driver_nonnegative_sum[:, None]
            + combos.constructor_nonnegative_sum[None, :]
            + np.maximum(combos.driver_top[:, None], 0)
        )
    else:
        played_projected = normal_projected

    # Temporary scoring chips sit on top of the manager's normal transfer
    # policy.  They do not justify distorting the persistent team solely for
    # one scoring mechanic.  Limitless and Wild Card remain lineup-changing
    # chips by definition.
    if chip in {"3x_boost", "no_negative", "autopilot"}:
        selection_projected = normal_projected
    else:
        selection_projected = played_projected

    projected_gain = combos.driver_gain[:, None] + combos.constructor_gain[None, :]
    downside = combos.driver_downside[:, None] + combos.constructor_downside[None, :]

    if state is None:
        driver_transfers = np.zeros(len(combos.driver_indices), dtype=np.int16)
        constructor_transfers = np.zeros(
            len(combos.constructor_indices), dtype=np.int16
        )
        budget = STARTING_BUDGET
        free_transfers = 0
    else:
        driver_transfers = _count_transfers(
            combos.driver_indices, state.drivers, round_data.drivers, 5
        )
        constructor_transfers = _count_transfers(
            combos.constructor_indices,
            state.constructors,
            round_data.constructors,
            2,
        )
        budget = state.budget
        free_transfers = state.free_transfers

    transfers = driver_transfers[:, None] + constructor_transfers[None, :]
    if chip in {"wild_card", "limitless"} or state is None:
        penalty = np.zeros_like(transfers, dtype=float)
    else:
        penalty = (
            np.maximum(transfers - free_transfers, 0) * TRANSFER_PENALTY
        ).astype(float)

    if chip == "limitless":
        legal = np.ones_like(cost, dtype=bool)
    else:
        legal = cost <= budget + 1e-8
    if state is not None and chip not in {"wild_card", "limitless"}:
        legal &= transfers <= free_transfers + MAX_PAID_TRANSFERS_PER_ROUND

    points_after_penalty = selection_projected - penalty
    if strategy == "balanced" and chip != "limitless":
        objective = (
            points_after_penalty
            + BALANCED_PRICE_GAIN_VALUE * projected_gain
        )
    else:
        objective = points_after_penalty
    objective = np.where(legal, objective, -np.inf)
    flat_index = int(np.argmax(objective))
    if not np.isfinite(objective.flat[flat_index]):
        raise RuntimeError(
            f"No legal lineup for R{round_data.round_num}, {strategy}, {chip}"
        )
    driver_row, constructor_row = np.unravel_index(flat_index, objective.shape)
    selected_driver_indices = combos.driver_indices[driver_row]
    selected_constructor_indices = combos.constructor_indices[constructor_row]
    captain_index = int(combos.driver_top_index[driver_row])
    second_index = int(combos.driver_second_index[driver_row])
    selected_projection = np.sort(
        round_data.driver_projection[selected_driver_indices]
    )[::-1]
    gap = float(selected_projection[0] - selected_projection[1])
    captain_uncertainty = float(
        round_data.driver_std[captain_index] / (abs(gap) + 1.0)
    )
    return Candidate(
        drivers=tuple(round_data.drivers[index] for index in selected_driver_indices),
        constructors=tuple(
            round_data.constructors[index] for index in selected_constructor_indices
        ),
        cost=round(float(cost[driver_row, constructor_row]), 1),
        projected_points=round(
            float(played_projected[driver_row, constructor_row]), 2
        ),
        projected_gain=round(
            float(projected_gain[driver_row, constructor_row]), 2
        ),
        utility=float(objective[driver_row, constructor_row]),
        transfers=int(transfers[driver_row, constructor_row]),
        transfer_penalty=int(penalty[driver_row, constructor_row]),
        captain=round_data.drivers[captain_index],
        second_captain=(
            round_data.drivers[second_index] if chip == "3x_boost" else None
        ),
        downside_risk=round(float(downside[driver_row, constructor_row]), 2),
        captain_gap=round(gap, 2),
        captain_uncertainty=round(captain_uncertainty, 3),
    )


def _actual_score(
    *,
    candidate: Candidate,
    round_data: RoundInputs,
    chip: str | None,
) -> tuple[float, str, str | None, float]:
    driver_lookup = {
        key: index for index, key in enumerate(round_data.drivers)
    }
    constructor_lookup = {
        key: index for index, key in enumerate(round_data.constructors)
    }
    driver_scores = {
        key: float(round_data.driver_actual[driver_lookup[key]])
        for key in candidate.drivers
    }
    constructor_scores = {
        key: float(round_data.constructor_actual[constructor_lookup[key]])
        for key in candidate.constructors
    }
    if chip == "no_negative":
        driver_scores = {key: max(0.0, value) for key, value in driver_scores.items()}
        constructor_scores = {
            key: max(0.0, value) for key, value in constructor_scores.items()
        }
    asset_score = sum(driver_scores.values()) + sum(constructor_scores.values())
    captain = candidate.captain
    second = candidate.second_captain
    if chip == "autopilot":
        captain = max(driver_scores, key=driver_scores.get)
        second = None
        captain_bonus = driver_scores[captain]
    elif chip == "3x_boost":
        captain_bonus = 2 * driver_scores[captain]
        if second:
            captain_bonus += driver_scores[second]
    else:
        captain_bonus = driver_scores[captain]
    return asset_score + captain_bonus, captain, second, captain_bonus


def _closing_team_value(
    state: TeamState,
    round_data: RoundInputs,
) -> float:
    driver_lookup = {
        key: index for index, key in enumerate(round_data.drivers)
    }
    constructor_lookup = {
        key: index for index, key in enumerate(round_data.constructors)
    }
    held_value = sum(
        round_data.driver_close_prices[driver_lookup[key]]
        for key in state.drivers
    ) + sum(
        round_data.constructor_close_prices[constructor_lookup[key]]
        for key in state.constructors
    )
    return round(float(state.bank + held_value), 1)


def simulate(
    rounds: list[RoundInputs],
    *,
    strategy: str,
    chip_schedule: dict[int, str],
) -> dict[str, Any]:
    state: TeamState | None = None
    total_points = 0.0
    records: list[dict[str, Any]] = []

    for round_data in rounds:
        chip = chip_schedule.get(round_data.round_num)
        combos = build_combo_matrices(round_data)
        opening_budget = STARTING_BUDGET if state is None else state.budget
        free_before = 0 if state is None else state.free_transfers
        candidate = choose_lineup(
            round_data=round_data,
            combos=combos,
            state=state,
            strategy=strategy,
            chip=chip,
        )
        persistent_drivers = candidate.drivers
        persistent_constructors = candidate.constructors
        if chip == "limitless" and state is not None:
            persistent_drivers = state.drivers
            persistent_constructors = state.constructors
            new_bank = state.bank
            effective_transfers = 0
            penalty = 0
        else:
            new_bank = round(opening_budget - candidate.cost, 1)
            effective_transfers = 0 if state is None else candidate.transfers
            penalty = candidate.transfer_penalty

        if state is None:
            free_next = INITIAL_FREE_TRANSFERS_AFTER_R1
        elif chip in {"wild_card", "limitless"}:
            free_next = min(MAX_BANKED_TRANSFERS, free_before + 1)
        else:
            remaining = max(0, free_before - effective_transfers)
            free_next = min(MAX_BANKED_TRANSFERS, remaining + 1)

        persistent_state = TeamState(
            drivers=persistent_drivers,
            constructors=persistent_constructors,
            bank=new_bank,
            budget=opening_budget,
            free_transfers=free_next,
        )
        closing_budget = _closing_team_value(persistent_state, round_data)
        persistent_state.budget = closing_budget

        gross_actual, actual_captain, actual_second, captain_bonus = _actual_score(
            candidate=candidate,
            round_data=round_data,
            chip=chip,
        )
        net_actual = gross_actual - penalty
        total_points += net_actual
        records.append(
            {
                "round": round_data.round_num,
                "race": round_data.race_name,
                "archive": round_data.archive_path,
                "archive_reconstructed": round_data.reconstructed,
                "circuit_id": round_data.circuit_id,
                "overtaking_difficulty": round_data.overtaking_difficulty,
                "turn1_incident_risk": round_data.turn1_incident_risk,
                "safety_car_probability": round_data.safety_car_probability,
                "rain_risk": round_data.rain_risk,
                "weather_dnf_mult": round_data.weather_dnf_mult,
                "mean_dnf_probability": round(
                    round_data.mean_dnf_probability, 4
                ),
                "chip": chip,
                "drivers": list(candidate.drivers),
                "constructors": list(candidate.constructors),
                "persistent_drivers": list(persistent_drivers),
                "persistent_constructors": list(persistent_constructors),
                "captain": actual_captain,
                "second_boost": actual_second,
                "captain_bonus": round(captain_bonus, 1),
                "transfers": effective_transfers,
                "free_transfers_before": free_before,
                "free_transfers_next": free_next,
                "transfer_penalty": penalty,
                "projected_points": candidate.projected_points,
                "projected_price_gain": candidate.projected_gain,
                "actual_points_gross": round(gross_actual, 1),
                "actual_points_net": round(net_actual, 1),
                "season_points": round(total_points, 1),
                "budget_before": round(opening_budget, 1),
                "played_team_cost": candidate.cost,
                "bank_after_transfers": new_bank,
                "budget_after": closing_budget,
                "actual_budget_change": round(closing_budget - opening_budget, 1),
                "downside_risk": candidate.downside_risk,
                "captain_gap": candidate.captain_gap,
                "captain_uncertainty": candidate.captain_uncertainty,
            }
        )
        state = persistent_state

    return {
        "strategy": strategy,
        "chip_schedule": {str(key): value for key, value in sorted(chip_schedule.items())},
        "rounds": records,
        "summary": {
            "season_points": round(total_points, 1),
            "final_budget": round(state.budget if state else STARTING_BUDGET, 1),
            "budget_gain": round(
                (state.budget if state else STARTING_BUDGET) - STARTING_BUDGET,
                1,
            ),
            "final_bank": round(state.bank if state else 0.0, 1),
            "final_drivers": list(state.drivers if state else ()),
            "final_constructors": list(state.constructors if state else ()),
            "transfer_penalties": int(
                sum(record["transfer_penalty"] for record in records)
            ),
            "transfers": int(sum(record["transfers"] for record in records)),
        },
    }


def choose_chip_schedule(
    rounds: list[RoundInputs],
    *,
    strategy: str,
    baseline: dict[str, Any],
) -> tuple[dict[int, str], dict[str, Any]]:
    """Choose one forecast-only opportunity for each chip.

    Timing uses only genuine archives and projected opportunity—not realised
    fantasy points.  Sprint rounds are preferred for Limitless and 3x Boost.
    """
    state: TeamState | None = None
    opportunities: dict[int, dict[str, Any]] = {}
    baseline_by_round = {row["round"]: row for row in baseline["rounds"]}
    for round_data in rounds:
        combos = build_combo_matrices(round_data)
        base = baseline_by_round[round_data.round_num]
        if not round_data.reconstructed:
            chip_candidates = {}
            for chip in CHIPS:
                candidate = choose_lineup(
                    round_data=round_data,
                    combos=combos,
                    state=state,
                    strategy=strategy,
                    chip=chip,
                )
                chip_candidates[chip] = {
                    "uplift": round(
                        candidate.projected_points
                        - candidate.transfer_penalty
                        - (base["projected_points"] - base["transfer_penalty"]),
                        2,
                    ),
                    "downside_risk": candidate.downside_risk,
                    "captain_uncertainty": candidate.captain_uncertainty,
                }
            opportunities[round_data.round_num] = chip_candidates

        # Recreate the baseline state exactly.
        row = baseline_by_round[round_data.round_num]
        state = TeamState(
            drivers=tuple(row["persistent_drivers"]),
            constructors=tuple(row["persistent_constructors"]),
            bank=float(row["bank_after_transfers"]),
            budget=float(row["budget_after"]),
            free_transfers=int(row["free_transfers_next"]),
        )

    used_rounds: set[int] = set()
    schedule: dict[int, str] = {}
    rationale: dict[str, Any] = {}

    def select(chip: str, candidates: list[tuple[int, float]], reason: str) -> None:
        candidates = [
            item for item in candidates if item[0] not in used_rounds
        ]
        if not candidates:
            return
        round_num, score = max(candidates, key=lambda item: item[1])
        schedule[round_num] = chip
        used_rounds.add(round_num)
        rationale[chip] = {
            "round": round_num,
            "forecast_opportunity_score": round(float(score), 3),
            "reason": reason,
        }

    sprint_genuine = [
        round_num
        for round_num in opportunities
        if round_num in SPRINT_ROUNDS
    ]
    select(
        "limitless",
        [
            (round_num, opportunities[round_num]["limitless"]["uplift"])
            for round_num in sprint_genuine
        ],
        "Largest projected unlimited-budget uplift on a genuine sprint archive.",
    )
    select(
        "3x_boost",
        [
            (round_num, opportunities[round_num]["3x_boost"]["uplift"])
            for round_num in sprint_genuine
        ],
        "Best remaining genuine sprint-round projected 3x/2x uplift.",
    )
    ordered_rounds = [round_data.round_num for round_data in rounds]
    wildcard_rounds = [
        value
        for value in opportunities
        if ordered_rounds.index(value) >= 3
        and ordered_rounds.index(value) < len(ordered_rounds) - 1
    ]
    best_wildcard = max(
        (
            (round_num, opportunities[round_num]["wild_card"]["uplift"])
            for round_num in wildcard_rounds
            if round_num not in used_rounds
        ),
        key=lambda item: item[1],
        default=(None, 0.0),
    )
    rationale["wild_card"] = {
        "round": None,
        "forecast_opportunity_score": round(float(best_wildcard[1]), 3),
        "reason": (
            "Saved. A permanent rebuild needs archived multi-round horizon "
            "forecasts; a one-round uplift alone is not enough evidence."
        ),
    }
    select(
        "no_negative",
        [
            (
                round_num,
                opportunities[round_num]["no_negative"]["downside_risk"],
            )
            for round_num in opportunities
        ],
        "Highest forecast P5 downside exposure among remaining genuine rounds.",
    )
    select(
        "autopilot",
        [
            (
                round_num,
                opportunities[round_num]["autopilot"]["captain_uncertainty"],
            )
            for round_num in opportunities
        ],
        "Greatest captain uncertainty among remaining genuine rounds.",
    )
    return schedule, rationale


def choose_chip_schedule_v2(
    rounds: list[RoundInputs],
    *,
    strategy: str,
    baseline: dict[str, Any],
) -> tuple[dict[int, str], dict[str, Any]]:
    """Choose chips using domain rules and only pre-race forecast evidence.

    Limitless prioritises qualifying-heavy circuits, 3x prioritises an
    affordable pair of strong drivers, Wild Card responds to major forecasted
    lineup churn, and No Negative prioritises weather/attrition risk.
    """
    baseline_by_round = {row["round"]: row for row in baseline["rounds"]}
    state: TeamState | None = None
    signals: dict[int, dict[str, Any]] = {}

    for round_data in rounds:
        row = baseline_by_round[round_data.round_num]
        if not round_data.reconstructed:
            combos = build_combo_matrices(round_data)
            wildcard = choose_lineup(
                round_data=round_data,
                combos=combos,
                state=state,
                strategy=strategy,
                chip="wild_card",
            )
            limitless = choose_lineup(
                round_data=round_data,
                combos=combos,
                state=state,
                strategy=strategy,
                chip="limitless",
            )
            selected_driver_points = sorted(
                (
                    float(
                        round_data.driver_projection[
                            round_data.drivers.index(driver_id)
                        ]
                    ),
                    driver_id,
                )
                for driver_id in row["drivers"]
            )
            top_projection, top_driver = selected_driver_points[-1]
            second_projection, second_driver = selected_driver_points[-2]
            baseline_utility = (
                float(row["projected_points"])
                - float(row["transfer_penalty"])
                + (
                    BALANCED_PRICE_GAIN_VALUE
                    * float(row["projected_price_gain"])
                    if strategy == "balanced"
                    else 0.0
                )
            )
            wildcard_uplift = max(
                0.0, float(wildcard.utility) - baseline_utility
            )
            rain_bonus = RAIN_RISK_BONUS.get(round_data.rain_risk, 0.0)
            attrition_risk = (
                100.0
                * round_data.mean_dnf_probability
                * round_data.weather_dnf_mult
                + rain_bonus
                + 0.5
                * (
                    round_data.turn1_incident_risk
                    + round_data.safety_car_probability
                )
            )
            signals[round_data.round_num] = {
                "overtaking_difficulty": round_data.overtaking_difficulty,
                "limitless_uplift": (
                    limitless.projected_points
                    - limitless.transfer_penalty
                    - (
                        float(row["projected_points"])
                        - float(row["transfer_penalty"])
                    )
                ),
                "top_driver": top_driver,
                "second_driver": second_driver,
                "top_projection": top_projection,
                "second_projection": second_projection,
                "pair_projection": top_projection + second_projection,
                "wildcard_transfers": wildcard.transfers,
                "wildcard_uplift": wildcard_uplift,
                "wildcard_score": wildcard.transfers * wildcard_uplift,
                "attrition_risk": attrition_risk,
                "mean_dnf_probability": round_data.mean_dnf_probability,
                "weather_dnf_mult": round_data.weather_dnf_mult,
                "rain_risk": round_data.rain_risk,
                "captain_uncertainty": float(row["captain_uncertainty"]),
            }

        state = TeamState(
            drivers=tuple(row["persistent_drivers"]),
            constructors=tuple(row["persistent_constructors"]),
            bank=float(row["bank_after_transfers"]),
            budget=float(row["budget_after"]),
            free_transfers=int(row["free_transfers_next"]),
        )

    schedule: dict[int, str] = {}
    rationale: dict[str, Any] = {}
    used_rounds: set[int] = set()

    def assign(
        chip: str,
        round_num: int,
        score: float,
        reason: str,
    ) -> None:
        schedule[round_num] = chip
        used_rounds.add(round_num)
        rationale[chip] = {
            "round": round_num,
            "forecast_opportunity_score": round(float(score), 3),
            "reason": reason,
        }

    limitless_round = max(
        signals,
        key=lambda round_num: (
            signals[round_num]["overtaking_difficulty"],
            signals[round_num]["limitless_uplift"],
        ),
    )
    limitless_signal = signals[limitless_round]
    assign(
        "limitless",
        limitless_round,
        limitless_signal["overtaking_difficulty"],
        (
            "Most qualifying-dependent completed circuit: "
            f"{limitless_signal['overtaking_difficulty']}/10 overtaking "
            "difficulty, where an unrestricted premium lineup should create "
            "the largest advantage over budget-constrained teams."
        ),
    )

    triple_round = max(
        (round_num for round_num in signals if round_num not in used_rounds),
        key=lambda round_num: (
            signals[round_num]["second_projection"],
            signals[round_num]["pair_projection"],
        ),
    )
    triple_signal = signals[triple_round]
    assign(
        "3x_boost",
        triple_round,
        triple_signal["pair_projection"],
        (
            "Strongest affordable two-driver pairing in the normal lineup: "
            f"{triple_signal['top_driver']} "
            f"({triple_signal['top_projection']:.1f}) and "
            f"{triple_signal['second_driver']} "
            f"({triple_signal['second_projection']:.1f}) projected points."
        ),
    )

    no_negative_round = max(
        (round_num for round_num in signals if round_num not in used_rounds),
        key=lambda round_num: signals[round_num]["attrition_risk"],
    )
    no_negative_signal = signals[no_negative_round]
    assign(
        "no_negative",
        no_negative_round,
        no_negative_signal["attrition_risk"],
        (
            "Highest combined pre-race attrition signal after accounting for "
            f"field DNF probability ({100 * no_negative_signal['mean_dnf_probability']:.1f}%), "
            f"weather DNF multiplier ({no_negative_signal['weather_dnf_mult']:.2f}x), "
            f"and rain risk ({no_negative_signal['rain_risk']})."
        ),
    )

    # Re-evaluate Wild Card after the already-selected chips have altered the
    # persistent team path.  This keeps the "several changes" rule true for
    # the team the manager would actually own at that deadline.
    provisional = simulate(rounds, strategy=strategy, chip_schedule=schedule)
    provisional_by_round = {
        row["round"]: row for row in provisional["rounds"]
    }
    wildcard_signals: dict[int, dict[str, float]] = {}
    state = None
    for round_data in rounds:
        row = provisional_by_round[round_data.round_num]
        if (
            not round_data.reconstructed
            and round_data.round_num not in used_rounds
        ):
            wildcard = choose_lineup(
                round_data=round_data,
                combos=build_combo_matrices(round_data),
                state=state,
                strategy=strategy,
                chip="wild_card",
            )
            baseline_utility = (
                float(row["projected_points"])
                - float(row["transfer_penalty"])
                + (
                    BALANCED_PRICE_GAIN_VALUE
                    * float(row["projected_price_gain"])
                    if strategy == "balanced"
                    else 0.0
                )
            )
            uplift = max(0.0, float(wildcard.utility) - baseline_utility)
            wildcard_signals[round_data.round_num] = {
                "transfers": float(wildcard.transfers),
                "uplift": uplift,
                "score": float(wildcard.transfers) * uplift,
            }
        state = TeamState(
            drivers=tuple(row["persistent_drivers"]),
            constructors=tuple(row["persistent_constructors"]),
            bank=float(row["bank_after_transfers"]),
            budget=float(row["budget_after"]),
            free_transfers=int(row["free_transfers_next"]),
        )

    wildcard_candidates = [
        round_num
        for round_num, signal in wildcard_signals.items()
        if signal["transfers"] >= 4 and signal["uplift"] >= 10.0
    ]
    if wildcard_candidates:
        wildcard_round = max(
            wildcard_candidates,
            key=lambda round_num: wildcard_signals[round_num]["score"],
        )
        wildcard_signal = wildcard_signals[wildcard_round]
        assign(
            "wild_card",
            wildcard_round,
            wildcard_signal["score"],
            (
                "Forecasted competitive-order change called for "
                f"{int(wildcard_signal['transfers'])} lineup changes and "
                f"a {wildcard_signal['uplift']:.1f}-utility improvement; "
                "this is the upgrade/order-shift proxy."
            ),
        )
    else:
        rationale["wild_card"] = {
            "round": None,
            "forecast_opportunity_score": 0.0,
            "reason": (
                "Saved because no remaining genuine round required at least "
                "four forecast-supported changes with a meaningful uplift."
            ),
        }

    # Wild Card can also change captain choices later, so use that final
    # provisional path when selecting the remaining Autopilot opportunity.
    final_provisional = simulate(
        rounds, strategy=strategy, chip_schedule=schedule
    )
    final_by_round = {
        row["round"]: row for row in final_provisional["rounds"]
    }
    autopilot_round = max(
        (round_num for round_num in signals if round_num not in used_rounds),
        key=lambda round_num: final_by_round[round_num]["captain_uncertainty"],
    )
    assign(
        "autopilot",
        autopilot_round,
        final_by_round[autopilot_round]["captain_uncertainty"],
        "Greatest remaining forecast uncertainty between captain candidates.",
    )
    return schedule, rationale


def build_markdown(result: dict[str, Any]) -> str:
    chip_policy = result["chip_policy"]
    title_detail = chip_policy.upper()
    if result.get("saved_chips"):
        title_detail += "; " + ", ".join(result["saved_chips"]) + " saved"
    lines = [
        f"# 2026 sequential F1 Fantasy strategy experiment ({title_detail})",
        "",
        f"Generated from completed {CURRENT_SEASON} rounds using archived post-FP forecasts, "
        "official fantasy totals, and official round-by-round prices.",
        "",
        "## Rules used",
        "",
        "- Start with $100.0M and select 5 drivers plus 2 constructors.",
        "- Default boost is 2x on the highest projected driver in the selected team.",
        "- Two free transfers become available after round 1; one unused transfer is added per subsequent round, capped at five.",
        "- At most one paid transfer is allowed per round at a 10-point penalty.",
        "- Max Points optimises projected fantasy points after transfer penalties.",
        f"- Balanced optimises projected points plus {BALANCED_PRICE_GAIN_VALUE:.0f} points for every projected $1M of appreciation.",
        "- Chip timing is selected from genuine archives using forecast opportunity only; realised results are never used to choose the round.",
        "- Limitless is temporary and the persistent team reverts after the round. Wild Card changes the persistent team permanently.",
    ]
    if chip_policy == "v2":
        lines.extend(
            [
                "- V2 Limitless targets the highest overtaking-difficulty circuit.",
                "- V2 3x Boost targets the strongest two-driver pairing affordable in the normal team.",
                "- V2 Wild Card requires at least four forecast-supported lineup changes and a meaningful utility gain.",
                "- V2 No Negative combines archived DNF probability, weather DNF multiplier, rain risk, and circuit incident risk.",
                "",
            ]
        )
    else:
        lines.append("")
    if result.get("saved_chips"):
        lines.extend(
            [
                "- Explicitly saved chips: "
                + ", ".join(result["saved_chips"])
                + ".",
                "",
            ]
        )
    lines.extend(
        [
        "> Caveat: R1-R3 post-FP files are reconstructed archives, not genuine lock-time forecasts. "
        "R6-R13 are genuine live archives. Full-season totals are therefore an indicative experiment, "
        "not a clean claim of prospective performance.",
        "",
        ]
    )
    for manager in result["managers"]:
        summary = manager["summary"]
        round_one = next(row for row in manager["rounds"] if row["round"] == 1)
        genuine_points = sum(
            row["actual_points_net"]
            for row in manager["rounds"]
            if not row["archive_reconstructed"]
        )
        title = "Max Points" if manager["strategy"] == "max_points" else "Balanced"
        lines.extend(
            [
                f"## {title}",
                "",
                f"- Season points: **{summary['season_points']:.1f}**",
                (
                    f"- Round 1 result: **{round_one['actual_points_net']:.1f} points**, "
                    f"budget grew to **${round_one['budget_after']:.1f}M**"
                ),
                f"- Genuine-archive segment (R6-R13): **{genuine_points:.1f} points**",
                f"- Final team value: **${summary['final_budget']:.1f}M** "
                f"({summary['budget_gain']:+.1f}M)",
                f"- Transfers: {summary['transfers']} "
                f"(penalties: {summary['transfer_penalties']} points)",
                f"- No-chip comparison: {manager['no_chip_baseline']['season_points']:.1f} points, "
                f"${manager['no_chip_baseline']['final_budget']:.1f}M "
                f"({summary['season_points'] - manager['no_chip_baseline']['season_points']:+.1f} "
                "net season-point difference; Limitless also changes the later team/budget path)",
                f"- Final drivers: {', '.join(summary['final_drivers'])}",
                f"- Final constructors: {', '.join(summary['final_constructors'])}",
                "",
                "| R | Archive | Chip | Transfers | Net pts | Season pts | Budget before | Budget after | Captain |",
                "|---:|:---:|:---|---:|---:|---:|---:|---:|:---|",
            ]
        )
        for row in manager["rounds"]:
            provenance = "reconstructed" if row["archive_reconstructed"] else "genuine"
            chip = row["chip"] or "—"
            lines.append(
                f"| {row['round']} | {provenance} | {chip} | "
                f"{row['transfers']} | {row['actual_points_net']:.1f} | "
                f"{row['season_points']:.1f} | ${row['budget_before']:.1f}M | "
                f"${row['budget_after']:.1f}M | {row['captain']} |"
            )
        lines.extend(["", "### Chip rationale", ""])
        for chip, detail in manager["chip_rationale"].items():
            if detail["round"] is None:
                lines.append(
                    f"- **{chip} — saved:** {detail['reason']} "
                    f"(best one-round signal {detail['forecast_opportunity_score']:.3f})"
                )
            else:
                lines.append(
                    f"- **{chip} — R{detail['round']}:** {detail['reason']} "
                    f"(forecast opportunity {detail['forecast_opportunity_score']:.3f})"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validate_result(result: dict[str, Any], rounds: list[RoundInputs]) -> None:
    expected_rounds = [item.round_num for item in rounds]
    round_lookup = {item.round_num: item for item in rounds}
    for manager in result["managers"]:
        rows = manager["rounds"]
        assert [row["round"] for row in rows] == expected_rounds
        assert len(manager["chip_schedule"]) == len(set(manager["chip_schedule"].values()))
        assert set(manager["chip_schedule"].values()).issubset(set(CHIPS))
        for round_key in manager["chip_schedule"]:
            assert not round_lookup[int(round_key)].reconstructed
        if result.get("chip_policy") == "v2":
            limitless_round = next(
                int(round_key)
                for round_key, chip in manager["chip_schedule"].items()
                if chip == "limitless"
            )
            genuine_difficulties = [
                item.overtaking_difficulty
                for item in rounds
                if not item.reconstructed
            ]
            assert (
                round_lookup[limitless_round].overtaking_difficulty
                == max(genuine_difficulties)
            )
        previous_budget = STARTING_BUDGET
        for row in rows:
            round_data = round_lookup[row["round"]]
            assert len(row["drivers"]) == 5
            assert len(set(row["drivers"])) == 5
            assert len(row["constructors"]) == 2
            assert len(set(row["constructors"])) == 2
            if row["chip"] != "limitless":
                assert row["played_team_cost"] <= row["budget_before"] + 1e-8
            assert row["budget_after"] >= 0
            assert math.isclose(row["budget_before"], previous_budget)

            driver_lookup = {
                key: index for index, key in enumerate(round_data.drivers)
            }
            constructor_lookup = {
                key: index for index, key in enumerate(round_data.constructors)
            }
            held_close_value = sum(
                round_data.driver_close_prices[driver_lookup[key]]
                for key in row["persistent_drivers"]
            ) + sum(
                round_data.constructor_close_prices[constructor_lookup[key]]
                for key in row["persistent_constructors"]
            )
            expected_budget = round(
                float(row["bank_after_transfers"] + held_close_value), 1
            )
            assert math.isclose(expected_budget, row["budget_after"])

            driver_actual = {
                key: float(round_data.driver_actual[driver_lookup[key]])
                for key in row["drivers"]
            }
            constructor_actual = {
                key: float(
                    round_data.constructor_actual[constructor_lookup[key]]
                )
                for key in row["constructors"]
            }
            if row["chip"] == "no_negative":
                driver_actual = {
                    key: max(0.0, value)
                    for key, value in driver_actual.items()
                }
                constructor_actual = {
                    key: max(0.0, value)
                    for key, value in constructor_actual.items()
                }
            expected_gross = sum(driver_actual.values()) + sum(
                constructor_actual.values()
            )
            if row["chip"] == "3x_boost":
                expected_gross += 2 * driver_actual[row["captain"]]
                expected_gross += driver_actual[row["second_boost"]]
            else:
                expected_gross += driver_actual[row["captain"]]
            assert math.isclose(expected_gross, row["actual_points_gross"])
            assert math.isclose(
                expected_gross - row["transfer_penalty"],
                row["actual_points_net"],
            )
            previous_budget = row["budget_after"]
        calculated = round(sum(row["actual_points_net"] for row in rows), 1)
        assert math.isclose(calculated, manager["summary"]["season_points"])
        if result.get("chip_policy") == "v2" and "wild_card" in set(
            manager["chip_schedule"].values()
        ):
            wildcard_row = next(row for row in rows if row["chip"] == "wild_card")
            assert wildcard_row["transfers"] >= 4


def run(
    output_json: Path,
    output_markdown: Path,
    *,
    chip_policy: str = "v2",
    saved_chips: tuple[str, ...] = (),
) -> dict[str, Any]:
    rounds = load_rounds()
    managers = []
    for strategy in ("max_points", "balanced"):
        baseline = simulate(rounds, strategy=strategy, chip_schedule={})
        chooser = (
            choose_chip_schedule_v2
            if chip_policy == "v2"
            else choose_chip_schedule
        )
        schedule, rationale = chooser(rounds, strategy=strategy, baseline=baseline)
        for saved_chip in saved_chips:
            scheduled_round = next(
                (
                    round_num
                    for round_num, chip in schedule.items()
                    if chip == saved_chip
                ),
                None,
            )
            if scheduled_round is not None:
                del schedule[scheduled_round]
            prior = rationale.get(saved_chip, {})
            rationale[saved_chip] = {
                "round": None,
                "forecast_opportunity_score": float(
                    prior.get("forecast_opportunity_score", 0.0)
                ),
                "reason": (
                    "Explicitly saved for a future round in this counterfactual; "
                    "no replacement chip was assigned to its former round."
                ),
            }
        manager = simulate(rounds, strategy=strategy, chip_schedule=schedule)
        manager["chip_rationale"] = rationale
        manager["no_chip_baseline"] = baseline["summary"]
        managers.append(manager)
    result = {
        "schema_version": 2,
        "season": CURRENT_SEASON,
        "chip_policy": chip_policy,
        "saved_chips": list(saved_chips),
        "starting_budget": STARTING_BUDGET,
        "completed_rounds": [item.round_num for item in rounds],
        "forecast_phase": "post_fp",
        "reconstructed_rounds": [
            item.round_num for item in rounds if item.reconstructed
        ],
        "genuine_rounds": [
            item.round_num for item in rounds if not item.reconstructed
        ],
        "policy": {
            "max_points": "Projected points after transfer penalties.",
            "balanced": (
                "Projected points after penalties plus "
                f"{BALANCED_PRICE_GAIN_VALUE:.0f} points per projected $1M gain."
            ),
            "paid_transfer_limit": MAX_PAID_TRANSFERS_PER_ROUND,
            "transfer_penalty": TRANSFER_PENALTY,
            "max_banked_transfers": MAX_BANKED_TRANSFERS,
        },
        "managers": managers,
    }
    validate_result(result, rounds)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    output_markdown.write_text(build_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT
        / "data"
        / "experiments"
        / "season_strategy_simulation_2026_v2.json",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=ROOT
        / "data"
        / "experiments"
        / "season_strategy_simulation_2026_v2.md",
    )
    parser.add_argument(
        "--chip-policy",
        choices=("v1", "v2"),
        default="v2",
        help="Chip-timing policy to apply (default: v2 domain-informed rules).",
    )
    parser.add_argument(
        "--save-chip",
        action="append",
        choices=CHIPS,
        default=[],
        help="Hold this chip instead of playing it; may be supplied more than once.",
    )
    args = parser.parse_args()
    result = run(
        args.output_json,
        args.output_markdown,
        chip_policy=args.chip_policy,
        saved_chips=tuple(args.save_chip),
    )
    print(f"JSON -> {args.output_json}")
    print(f"Report -> {args.output_markdown}")
    for manager in result["managers"]:
        summary = manager["summary"]
        print(
            f"{manager['strategy']}: {summary['season_points']:.1f} pts, "
            f"${summary['final_budget']:.1f}M, "
            f"chips={manager['chip_schedule']}"
        )


if __name__ == "__main__":
    main()
