"""Estimate the marginal F1 Fantasy point value of additional team budget.

The analysis is deliberately non-circular: its primary estimate follows a
points-only manager, then measures how much extra projected scoring an
additional $0.1M-$2.0M unlocks over the remaining archived rounds.  A Balanced
manager is included as a sensitivity check, but the existing eight-point
budget utility is not used to set the headline value.

It also backtests the price-change heuristic and measures how often actual
price rises persist, flatten, or reverse.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import simulate_fantasy_season_strategies as season


DEFAULT_JSON = ROOT / "data" / "experiments" / "budget_point_value_2026.json"
DEFAULT_MARKDOWN = ROOT / "data" / "experiments" / "budget_point_value_2026.md"
DEFAULT_WEB_JSON = ROOT / "web" / "public" / "data" / "budget_value.json"
BUDGET_DELTAS = tuple(round(step / 10, 1) for step in range(1, 21))
CURVE_DELTAS = (1.0,)
STRATEGY_EXPERIMENTS = (
    ROOT / "data" / "experiments" / "season_strategy_simulation_2026_v1.json",
    ROOT / "data" / "experiments" / "season_strategy_simulation_2026_v2.json",
    ROOT
    / "data"
    / "experiments"
    / "season_strategy_simulation_2026_v3_no_3x.json",
)
RISK_EXPERIMENT = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_with_chips_2026.json"
)
_COMBO_CACHE: dict[int, season.ComboMatrices] = {}


def _fit_saturating_curve(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[float, float, float]:
    """Return RMSE, ceiling and tau for V(N)=ceiling*(1-exp(-N/tau))."""
    best: tuple[float, float, float] | None = None
    for tau in np.linspace(0.5, 30.0, 591):
        basis = 1.0 - np.exp(-x / tau)
        denominator = float(np.dot(basis, basis))
        if denominator <= 0:
            continue
        ceiling = max(0.0, float(np.dot(basis, y) / denominator))
        error = float(np.mean((y - ceiling * basis) ** 2))
        if best is None or error < best[0]:
            best = (error, ceiling, float(tau))
    if best is None:
        raise ValueError("Cannot fit budget curve without positive horizons")
    error, ceiling, tau = best
    return math.sqrt(error), ceiling, tau


def _combos(round_data: season.RoundInputs) -> season.ComboMatrices:
    if round_data.round_num not in _COMBO_CACHE:
        _COMBO_CACHE[round_data.round_num] = season.build_combo_matrices(
            round_data
        )
    return _COMBO_CACHE[round_data.round_num]


def _state_before_round(
    baseline: dict[str, Any],
    round_index: int,
) -> season.TeamState:
    if round_index == 0:
        return season.TeamState(
            drivers=(),
            constructors=(),
            bank=season.STARTING_BUDGET,
            budget=season.STARTING_BUDGET,
            free_transfers=0,
        )
    previous = baseline["rounds"][round_index - 1]
    return season.TeamState(
        drivers=tuple(previous["persistent_drivers"]),
        constructors=tuple(previous["persistent_constructors"]),
        bank=float(previous["bank_after_transfers"]),
        budget=float(previous["budget_after"]),
        free_transfers=int(previous["free_transfers_next"]),
    )


def simulate_continuation(
    rounds: list[season.RoundInputs],
    *,
    initial_state: season.TeamState,
    strategy: str,
    extra_budget: float,
) -> dict[str, float]:
    """Run a no-chip continuation from one historical deadline state."""
    state = replace(
        initial_state,
        bank=round(initial_state.bank + extra_budget, 1),
        budget=round(initial_state.budget + extra_budget, 1),
    )
    projected_total = 0.0
    actual_total = 0.0
    first_projected = 0.0
    total_penalties = 0
    total_transfers = 0

    for offset, round_data in enumerate(rounds):
        is_season_start = not state.drivers and not state.constructors
        candidate = season.choose_lineup(
            round_data=round_data,
            combos=_combos(round_data),
            state=state,
            strategy=strategy,
            chip=None,
        )
        opening_budget = state.budget
        transfer_penalty = 0 if is_season_start else candidate.transfer_penalty
        transfers = 0 if is_season_start else candidate.transfers
        projected_net = candidate.projected_points - transfer_penalty
        gross_actual, _, _, _ = season._actual_score(
            candidate=candidate,
            round_data=round_data,
            chip=None,
        )
        actual_net = gross_actual - transfer_penalty

        new_bank = round(opening_budget - candidate.cost, 1)
        if is_season_start:
            free_next = season.INITIAL_FREE_TRANSFERS_AFTER_R1
        else:
            remaining = max(0, state.free_transfers - transfers)
            free_next = min(season.MAX_BANKED_TRANSFERS, remaining + 1)
        state = season.TeamState(
            drivers=candidate.drivers,
            constructors=candidate.constructors,
            bank=new_bank,
            budget=opening_budget,
            free_transfers=free_next,
        )
        state.budget = season._closing_team_value(state, round_data)

        if offset == 0:
            first_projected = projected_net
        projected_total += projected_net
        actual_total += actual_net
        total_penalties += transfer_penalty
        total_transfers += transfers

    return {
        "projected_points": round(projected_total, 3),
        "actual_points": round(actual_total, 3),
        "first_round_projected": round(first_projected, 3),
        "final_budget": round(state.budget, 3),
        "transfer_penalties": float(total_penalties),
        "transfers": float(total_transfers),
    }


def marginal_budget_records(
    rounds: list[season.RoundInputs],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for strategy in ("max_points", "balanced"):
        deltas = (
            BUDGET_DELTAS
            if strategy == "max_points"
            else tuple(sorted({0.3, *CURVE_DELTAS}))
        )
        baseline = season.simulate(rounds, strategy=strategy, chip_schedule={})
        for round_index, round_data in enumerate(rounds):
            state = _state_before_round(baseline, round_index)
            future_rounds = rounds[round_index:]
            base = simulate_continuation(
                future_rounds,
                initial_state=state,
                strategy=strategy,
                extra_budget=0.0,
            )
            for delta in deltas:
                richer = simulate_continuation(
                    future_rounds,
                    initial_state=state,
                    strategy=strategy,
                    extra_budget=delta,
                )
                records.append(
                    {
                        "strategy": strategy,
                        "start_round": round_data.round_num,
                        "archive_reconstructed": round_data.reconstructed,
                        "races_remaining": len(future_rounds),
                        "starting_budget": state.budget,
                        "extra_budget": delta,
                        "immediate_projected_gain": round(
                            richer["first_round_projected"]
                            - base["first_round_projected"],
                            3,
                        ),
                        "continuation_projected_gain": round(
                            richer["projected_points"] - base["projected_points"],
                            3,
                        ),
                        "continuation_actual_gain": round(
                            richer["actual_points"] - base["actual_points"],
                            3,
                        ),
                        "final_budget_difference": round(
                            richer["final_budget"] - base["final_budget"],
                            3,
                        ),
                        "transfer_penalty_difference": round(
                            richer["transfer_penalties"]
                            - base["transfer_penalties"],
                            3,
                        ),
                        "transfer_difference": round(
                            richer["transfers"] - base["transfers"],
                            3,
                        ),
                    }
                )
    return records


def fit_budget_curve(
    records: list[dict[str, Any]],
    *,
    strategy: str,
    max_horizon: int,
) -> dict[str, Any]:
    """Fit V(N)=ceiling*(1-exp(-N/tau)) from a fixed $1M perturbation."""
    selected = [
        row
        for row in records
        if row["strategy"] == strategy
        and not row["archive_reconstructed"]
        and float(row["extra_budget"]) in CURVE_DELTAS
    ]
    horizons = sorted({int(row["races_remaining"]) for row in selected})
    horizon_medians = {}
    for horizon in horizons:
        values = [
            max(0.0, float(row["continuation_projected_gain"]))
            / float(row["extra_budget"])
            for row in selected
            if int(row["races_remaining"]) == horizon
        ]
        horizon_medians[str(horizon)] = round(float(np.median(values)), 3)
    x = np.array(horizons, dtype=float)
    y = np.array(
        [float(horizon_medians[str(horizon)]) for horizon in horizons]
    )
    rmse, ceiling, tau = _fit_saturating_curve(x, y)
    curve = {
        str(races): round(ceiling * (1.0 - math.exp(-races / tau)), 2)
        for races in range(0, max_horizon + 1)
    }

    # Resample deadline states, not individual budget deltas. Deltas from one
    # state are strongly dependent and should not masquerade as independent
    # evidence. The interval is descriptive because only eight genuine
    # deadline states currently exist.
    rng = np.random.default_rng(2026)
    bootstrap_curves: dict[int, list[float]] = {
        races: [] for races in range(0, max_horizon + 1)
    }
    if len(x) >= 2:
        for _ in range(1000):
            indices = rng.integers(0, len(x), len(x))
            sample_x = x[indices]
            sample_y = y[indices]
            _, sample_ceiling, sample_tau = _fit_saturating_curve(
                sample_x,
                sample_y,
            )
            for races in bootstrap_curves:
                bootstrap_curves[races].append(
                    sample_ceiling
                    * (1.0 - math.exp(-races / sample_tau))
                )
    curve_p25 = {
        str(races): round(float(np.percentile(values, 25)), 2)
        if values
        else curve[str(races)]
        for races, values in bootstrap_curves.items()
    }
    curve_p75 = {
        str(races): round(float(np.percentile(values, 75)), 2)
        if values
        else curve[str(races)]
        for races, values in bootstrap_curves.items()
    }
    all_values = np.array(
        [
            max(0.0, float(row["continuation_projected_gain"]))
            / float(row["extra_budget"])
            for row in selected
        ]
    )
    delta_0_3 = [
        row
        for row in records
        if row["strategy"] == strategy
        and not row["archive_reconstructed"]
        and math.isclose(float(row["extra_budget"]), 0.3)
    ]
    return {
        "formula": "ceiling * (1 - exp(-races_remaining / tau))",
        "curve_perturbation_millions": 1.0,
        "ceiling_points_per_million": round(ceiling, 3),
        "tau_races": round(tau, 3),
        "rmse": round(rmse, 3),
        "curve_points_per_million": curve,
        "curve_points_per_million_p25": curve_p25,
        "curve_points_per_million_p75": curve_p75,
        "bootstrap_note": (
            "25th-75th percentile from 1,000 resamples of genuine deadline "
            "states; descriptive small-sample uncertainty only."
        ),
        "observed_horizon_median_points_per_million": horizon_medians,
        "raw_median_points_per_million": round(float(np.median(all_values)), 3),
        "raw_p25_points_per_million": round(float(np.percentile(all_values, 25)), 3),
        "raw_p75_points_per_million": round(float(np.percentile(all_values, 75)), 3),
        "zero_value_share": round(float(np.mean(all_values == 0.0)), 3),
        "isolated_0_3m_observations": len(delta_0_3),
        "isolated_0_3m_zero_value_share": round(
            sum(
                math.isclose(float(row["continuation_projected_gain"]), 0.0)
                for row in delta_0_3
            )
            / len(delta_0_3),
            3,
        ),
    }


def price_forecast_backtest(
    rounds: list[season.RoundInputs],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for round_data in rounds:
        for asset_type, ids, predicted, opening, closing in (
            (
                "driver",
                round_data.drivers,
                round_data.driver_projected_gain,
                round_data.driver_prices,
                round_data.driver_close_prices,
            ),
            (
                "constructor",
                round_data.constructors,
                round_data.constructor_projected_gain,
                round_data.constructor_prices,
                round_data.constructor_close_prices,
            ),
        ):
            for index, asset_id in enumerate(ids):
                rows.append(
                    {
                        "round": round_data.round_num,
                        "archive_reconstructed": round_data.reconstructed,
                        "asset_type": asset_type,
                        "asset_id": asset_id,
                        "opening_price": float(opening[index]),
                        "predicted_change": float(predicted[index]),
                        "actual_change": round(
                            float(closing[index] - opening[index]), 3
                        ),
                    }
                )

    all_predicted_up = [row for row in rows if row["predicted_change"] > 0]
    predicted_up = [
        row
        for row in all_predicted_up
        if not row["archive_reconstructed"]
    ]
    actual_positive = np.array(
        [max(0.0, row["actual_change"]) for row in predicted_up]
    )
    predicted_positive = np.array(
        [row["predicted_change"] for row in predicted_up]
    )
    signed_actual = np.array([row["actual_change"] for row in predicted_up])
    by_bracket: dict[str, Any] = {}
    for predicted_value in sorted({row["predicted_change"] for row in predicted_up}):
        subset = [
            row
            for row in predicted_up
            if math.isclose(row["predicted_change"], predicted_value)
        ]
        by_bracket[f"{predicted_value:+.1f}"] = {
            "n": len(subset),
            "rise_hit_rate": round(
                sum(row["actual_change"] > 0 for row in subset) / len(subset),
                3,
            ),
            "mean_actual_change": round(
                float(np.mean([row["actual_change"] for row in subset])), 3
            ),
            "median_actual_change": round(
                float(np.median([row["actual_change"] for row in subset])), 3
            ),
        }
    return {
        "observations": len(rows),
        "genuine_observations": sum(
            not row["archive_reconstructed"] for row in rows
        ),
        "predicted_rise_observations": len(predicted_up),
        "predicted_rise_hit_rate": round(
            sum(row["actual_change"] > 0 for row in predicted_up)
            / len(predicted_up),
            3,
        ),
        "predicted_rise_nonloss_rate": round(
            sum(row["actual_change"] >= 0 for row in predicted_up)
            / len(predicted_up),
            3,
        ),
        "mean_predicted_rise": round(float(np.mean(predicted_positive)), 3),
        "mean_actual_signed_change": round(float(np.mean(signed_actual)), 3),
        "mean_actual_positive_change": round(float(np.mean(actual_positive)), 3),
        "signed_realization_ratio": round(
            float(np.sum(signed_actual) / np.sum(predicted_positive)), 3
        ),
        "positive_realization_ratio": round(
            float(np.sum(actual_positive) / np.sum(predicted_positive)), 3
        ),
        "by_predicted_bracket": by_bracket,
        "all_rounds_predicted_rise_observations": len(all_predicted_up),
        "rows": rows,
    }


def price_persistence() -> dict[str, Any]:
    payload = season._load_json(
        season.SEED_DIR / "fantasy_prices.json"
    )["price_history"]
    official = season._load_json(
        season.SEED_DIR / "official_fantasy_points.json"
    )["rounds"]
    ordered_keys = sorted(int(key) for key in payload)
    events: list[dict[str, Any]] = []
    next_moves: list[str] = []
    retention: dict[int, list[dict[str, float]]] = {1: [], 2: [], 3: []}

    def official_score(
        round_num: int,
        asset_type: str,
        asset_id: str,
    ) -> float | None:
        round_payload = official.get(str(round_num), {})
        group = round_payload.get(asset_type, {})
        value = group.get(asset_id)
        return float(value) if value is not None else None

    def move_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        eligible = [row for row in rows if row.get("next_move")]
        if not eligible:
            return {"n": 0, "up": None, "flat": None, "down": None}
        return {
            "n": len(eligible),
            **{
                move: round(
                    sum(row["next_move"] == move for row in eligible)
                    / len(eligible),
                    3,
                )
                for move in ("up", "flat", "down")
            },
        }

    for asset_type in ("drivers", "constructors"):
        asset_ids = tuple(payload[str(ordered_keys[0])][asset_type])
        for asset_id in asset_ids:
            prices = [
                float(payload[str(round_num)][asset_type][asset_id])
                for round_num in ordered_keys
            ]
            for index in range(1, len(prices)):
                change = round(prices[index] - prices[index - 1], 3)
                if change <= 0:
                    continue
                event = {
                    "asset_type": asset_type[:-1],
                    "asset_id": asset_id,
                    "round": ordered_keys[index],
                    "rise": change,
                    "price_after": prices[index],
                    "price_tier": (
                        "high" if prices[index] > 18.5 else "low"
                    ),
                }
                rise_streak = 1
                cursor = index - 1
                while cursor >= 1:
                    prior_change = round(
                        prices[cursor] - prices[cursor - 1],
                        3,
                    )
                    if prior_change <= 0:
                        break
                    rise_streak += 1
                    cursor -= 1
                event["rise_streak"] = rise_streak

                if index + 1 < len(prices):
                    next_change = round(prices[index + 1] - prices[index], 3)
                    next_move = (
                        "up"
                        if next_change > 0
                        else "down"
                        if next_change < 0
                        else "flat"
                    )
                    event["next_move"] = next_move
                    event["next_change"] = next_change
                    next_moves.append(next_move)

                    current_score = official_score(
                        ordered_keys[index],
                        asset_type,
                        asset_id,
                    )
                    previous_score = official_score(
                        ordered_keys[index - 1],
                        asset_type,
                        asset_id,
                    )
                    historical_scores = [
                        official_score(round_num, asset_type, asset_id)
                        for round_num in ordered_keys[1 : index + 1]
                    ]
                    historical_scores = [
                        score
                        for score in historical_scores
                        if score is not None
                    ]
                    if (
                        current_score is not None
                        and previous_score is not None
                        and historical_scores
                    ):
                        required_next = max(
                            0.0,
                            3.0 * 0.9 * prices[index]
                            - current_score
                            - previous_score,
                        )
                        trailing_average = float(
                            np.mean(historical_scores[-3:])
                        )
                        event["points_required_for_next_rise"] = round(
                            required_next,
                            3,
                        )
                        event["required_vs_trailing_average"] = round(
                            required_next - trailing_average,
                            3,
                        )
                for horizon in retention:
                    if index + horizon >= len(prices):
                        continue
                    future = prices[index + horizon]
                    start = prices[index - 1]
                    post = prices[index]
                    retention[horizon].append(
                        {
                            "ratio": (future - start) / change,
                            "above_post": float(future >= post),
                            "above_start": float(future >= start),
                        }
                    )
                events.append(event)

    persistence = {}
    for horizon, rows in retention.items():
        ratios = np.array([row["ratio"] for row in rows])
        persistence[str(horizon)] = {
            "n": len(rows),
            "median_retention_ratio": round(float(np.median(ratios)), 3),
            "mean_retention_ratio": round(float(np.mean(ratios)), 3),
            "expected_initial_rise_retained_fraction": round(
                float(np.mean(np.clip(ratios, 0.0, 1.0))),
                3,
            ),
            "probability_at_or_above_post_rise_price": round(
                float(np.mean([row["above_post"] for row in rows])), 3
            ),
            "probability_at_or_above_pre_rise_price": round(
                float(np.mean([row["above_start"] for row in rows])), 3
            ),
        }
    by_tier = {
        tier: move_summary(
            [row for row in events if row["price_tier"] == tier]
        )
        for tier in ("low", "high")
    }
    by_streak = {
        label: move_summary(
            [
                row
                for row in events
                if (
                    (label == "1" and row["rise_streak"] == 1)
                    or (label == "2" and row["rise_streak"] == 2)
                    or (label == "3+" and row["rise_streak"] >= 3)
                )
            ]
        )
        for label in ("1", "2", "3+")
    }
    required_rows = [
        row
        for row in events
        if "required_vs_trailing_average" in row
        and row.get("next_move")
    ]
    by_required_score = {}
    for label, predicate in (
        (
            "at_or_below_recent_average",
            lambda row: row["required_vs_trailing_average"] <= 0,
        ),
        (
            "above_recent_average",
            lambda row: row["required_vs_trailing_average"] > 0,
        ),
    ):
        subset = [row for row in required_rows if predicate(row)]
        by_required_score[label] = {
            "n": len(subset),
            "next_rise_rate": (
                round(
                    sum(row["next_move"] == "up" for row in subset)
                    / len(subset),
                    3,
                )
                if subset
                else None
            ),
            "median_points_required": (
                round(
                    float(
                        np.median(
                            [
                                row["points_required_for_next_rise"]
                                for row in subset
                            ]
                        )
                    ),
                    3,
                )
                if subset
                else None
            ),
        }

    return {
        "rise_events": len(events),
        "next_move_after_rise": {
            move: round(next_moves.count(move) / len(next_moves), 3)
            for move in ("up", "flat", "down")
        },
        "next_move_by_price_tier": by_tier,
        "next_move_by_consecutive_rises": by_streak,
        "next_rise_by_required_score": by_required_score,
        "retention_by_future_rounds": persistence,
        "events": events,
    }


def affordability_frontiers(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarise how much extra cash was needed to change the continuation."""
    selected = [
        row
        for row in records
        if row["strategy"] == "max_points"
        and not row["archive_reconstructed"]
    ]
    by_round: dict[int, list[dict[str, Any]]] = {}
    for row in selected:
        by_round.setdefault(int(row["start_round"]), []).append(row)

    thresholds: list[float] = []
    rows = []
    for start_round, round_rows in sorted(by_round.items()):
        ordered = sorted(round_rows, key=lambda row: float(row["extra_budget"]))
        positive = [
            row
            for row in ordered
            if float(row["continuation_projected_gain"]) > 0
        ]
        threshold = (
            float(positive[0]["extra_budget"]) if positive else None
        )
        if threshold is not None:
            thresholds.append(threshold)
        rows.append(
            {
                "start_round": start_round,
                "races_remaining": int(ordered[0]["races_remaining"]),
                "minimum_tested_unlock_millions": threshold,
            }
        )

    return {
        "genuine_deadline_states": len(rows),
        "states_with_unlock_within_2m": len(thresholds),
        "share_unlocked_by_0_3m": round(
            sum(value <= 0.3 for value in thresholds) / len(rows), 3
        ),
        "share_unlocked_by_0_5m": round(
            sum(value <= 0.5 for value in thresholds) / len(rows), 3
        ),
        "share_unlocked_by_1_0m": round(
            sum(value <= 1.0 for value in thresholds) / len(rows), 3
        ),
        "median_minimum_tested_unlock_millions": (
            round(float(np.median(thresholds)), 3) if thresholds else None
        ),
        "minimum_tested_unlock_distribution": {
            f"{delta:.1f}": sum(
                math.isclose(value, delta) for value in thresholds
            )
            for delta in BUDGET_DELTAS
            if any(math.isclose(value, delta) for value in thresholds)
        },
        "by_start_round": rows,
    }


def marginal_gain_realization(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calibrate forecasted marginal lineup gains against official outcomes."""
    selected = [
        row
        for row in records
        if row["strategy"] == "max_points"
        and not row["archive_reconstructed"]
        and float(row["continuation_projected_gain"]) > 0
    ]
    by_round: dict[int, list[float]] = {}
    for row in selected:
        ratio = (
            float(row["continuation_actual_gain"])
            / float(row["continuation_projected_gain"])
        )
        by_round.setdefault(int(row["start_round"]), []).append(ratio)

    # Multiple deltas from the same deadline are highly correlated, so each
    # deadline contributes one median ratio rather than several pseudo-samples.
    state_ratios = np.array(
        [float(np.median(values)) for values in by_round.values()],
        dtype=float,
    )
    multiplier = (
        max(0.0, float(np.median(state_ratios)))
        if len(state_ratios)
        else 1.0
    )
    return {
        "method": (
            "Median actual/projected continuation-gain ratio per genuine "
            "deadline state, then median across states."
        ),
        "positive_projected_gain_records": len(selected),
        "deadline_states": len(state_ratios),
        "decision_grade_multiplier": round(multiplier, 3),
        "state_ratio_p25": (
            round(float(np.percentile(state_ratios, 25)), 3)
            if len(state_ratios)
            else None
        ),
        "state_ratio_p75": (
            round(float(np.percentile(state_ratios, 75)), 3)
            if len(state_ratios)
            else None
        ),
        "by_start_round": {
            str(round_num): round(float(np.median(values)), 3)
            for round_num, values in sorted(by_round.items())
        },
    }


def strategy_experiment_context() -> dict[str, Any]:
    """Record the paired season results without treating them as causal."""
    comparisons = []
    for path in STRATEGY_EXPERIMENTS:
        payload = season._load_json(path)
        managers = {
            manager["strategy"]: manager["summary"]
            for manager in payload["managers"]
        }
        max_points = managers["max_points"]
        balanced = managers["balanced"]
        point_difference = (
            float(balanced["season_points"])
            - float(max_points["season_points"])
        )
        budget_difference = (
            float(balanced["final_budget"])
            - float(max_points["final_budget"])
        )
        comparisons.append(
            {
                "experiment": path.stem,
                "balanced_points_advantage": round(point_difference, 3),
                "balanced_budget_advantage_millions": round(
                    budget_difference, 3
                ),
                "naive_points_per_extra_million": (
                    round(point_difference / budget_difference, 3)
                    if budget_difference
                    else None
                ),
            }
        )
    return {
        "comparisons": comparisons,
        "interpretation": (
            "Directional evidence only. Managers chose different assets and "
            "chips, so the paired point/budget ratios are not a causal marginal "
            "price for budget and are excluded from the headline curve."
        ),
    }


def risk_experiment_context() -> dict[str, Any]:
    """Use the 12-path risk experiment as a non-causal consistency check."""
    payload = season._load_json(RISK_EXPERIMENT)
    paths = [
        {
            "strategy": manager["strategy"],
            "risk_profile": manager["risk_profile"],
            "season_points": float(manager["summary"]["season_points"]),
            "genuine_points": float(
                manager["summary"]["genuine_archive_points"]
            ),
            "final_budget": float(manager["summary"]["final_budget"]),
        }
        for manager in payload["managers"]
    ]
    best_points = max(paths, key=lambda row: row["season_points"])
    highest_budget = max(row["final_budget"] for row in paths)
    highest_budget_paths = [
        row for row in paths if math.isclose(row["final_budget"], highest_budget)
    ]
    budget_builder = {
        row["risk_profile"]: row
        for row in paths
        if row["strategy"] == "budget_builder"
    }
    medium = budget_builder["medium_tolerance"]
    minimal = budget_builder["minimal_risk_accepted"]
    return {
        "paths": len(paths),
        "best_points_path": best_points,
        "highest_budget": highest_budget,
        "highest_budget_paths": highest_budget_paths,
        "points_spread_at_highest_budget": round(
            max(row["season_points"] for row in highest_budget_paths)
            - min(row["season_points"] for row in highest_budget_paths),
            3,
        ),
        "budget_builder_medium_vs_minimal": {
            "points_difference": round(
                medium["season_points"] - minimal["season_points"],
                3,
            ),
            "genuine_points_difference": round(
                medium["genuine_points"] - minimal["genuine_points"],
                3,
            ),
            "budget_difference": round(
                medium["final_budget"] - minimal["final_budget"],
                3,
            ),
        },
        "interpretation": (
            "The risk experiment is a consistency check, not a marginal "
            "valuation. Equal final budgets produced materially different "
            "points, confirming that budget creates options but does not score "
            "points by itself."
        ),
    }


def decision_examples(
    curve: dict[str, Any],
    forecast_backtest: dict[str, Any],
    gain_realization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plus_0_3 = forecast_backtest["by_predicted_bracket"]["+0.3"]
    expected_realized_0_3 = max(
        0.0, float(plus_0_3["mean_actual_change"])
    )
    reliability = min(1.0, expected_realized_0_3 / 0.3)
    points_multiplier = (
        float(gain_realization["decision_grade_multiplier"])
        if gain_realization
        else 1.0
    )
    examples = {}
    for races in (1, 3, 5, 8, 11):
        key = str(races)
        if key not in curve["curve_points_per_million"]:
            continue
        secured_value = float(curve["curve_points_per_million"][key])
        usable_future_races = max(0, races - 1)
        future_key = str(usable_future_races)
        forecast_value = float(
            curve["curve_points_per_million"].get(future_key, 0.0)
        )
        forecast_p25 = float(
            curve.get("curve_points_per_million_p25", {}).get(
                future_key,
                forecast_value,
            )
        )
        forecast_p75 = float(
            curve.get("curve_points_per_million_p75", {}).get(
                future_key,
                forecast_value,
            )
        )
        examples[key] = {
            "races_budget_can_be_used": usable_future_races,
            "secured_0_3m_point_value": round(0.3 * secured_value, 2),
            "predicted_0_3m_expected_point_value": round(
                expected_realized_0_3 * forecast_value, 2
            ),
            "decision_grade_secured_0_3m_point_value": round(
                0.3 * secured_value * points_multiplier, 2
            ),
            "decision_grade_predicted_0_3m_point_value": round(
                expected_realized_0_3
                * forecast_value
                * points_multiplier,
                2,
            ),
            "decision_grade_predicted_0_3m_p25": round(
                expected_realized_0_3
                * forecast_p25
                * points_multiplier,
                2,
            ),
            "decision_grade_predicted_0_3m_p75": round(
                expected_realized_0_3
                * forecast_p75
                * points_multiplier,
                2,
            ),
            "secured_1_0m_point_value": round(secured_value, 2),
            "decision_grade_secured_1_0m_point_value": round(
                secured_value * points_multiplier, 2
            ),
            "secured_budget_needed_for_10_points": (
                round(
                    10.0 / (secured_value * points_multiplier),
                    2,
                )
                if secured_value * points_multiplier > 0
                else None
            ),
            "predicted_budget_needed_for_10_points": (
                round(
                    10.0
                    / (
                        forecast_value
                        * points_multiplier
                        * reliability
                    ),
                    2,
                )
                if forecast_value * points_multiplier * reliability > 0
                else None
            ),
        }
    return {
        "price_forecast_reliability_discount": round(reliability, 3),
        "marginal_points_realization_discount": round(
            points_multiplier, 3
        ),
        "predicted_0_3m_mean_realized_change": round(
            expected_realized_0_3, 3
        ),
        "by_races_remaining": examples,
    }


def build_markdown(result: dict[str, Any]) -> str:
    primary = result["curves"]["max_points"]
    forecast = result["price_forecast_backtest"]
    persistence = result["price_persistence"]
    realization = result["marginal_gain_realization"]
    frontiers = result["affordability_frontiers"]
    experiments = result["strategy_experiment_context"]
    risk_experiment = result["risk_experiment_context"]
    examples = result["decision_examples"]["by_races_remaining"]
    lines = [
        "# 2026 marginal budget-to-points analysis",
        "",
        "## Headline metric",
        "",
        (
            "Primary fitted curve: **"
            f"{primary['ceiling_points_per_million']:.2f} × "
            f"(1 − exp(−races remaining / {primary['tau_races']:.2f})) "
            "future projected points per $1M already secured before the deadline**."
        ),
        "",
        (
            "The curve is anchored to the same +$1.0M perturbation at every "
            "historical deadline. Smaller and larger perturbations are retained "
            "for the lumpy frontier but do not set the smooth exchange rate."
        ),
        "",
        (
            "Practical shorthand for the remaining 2026 horizon: "
            "**about 5.3 decision-grade points per $1M already secured, or "
            "about 4.6 points per forecast $1M rise with 11 races left**."
        ),
        "",
        (
            "A price rise earned in the current race is available one race later. "
            "For a predicted rise, use the curve at **races left minus one**, then "
            "apply the price and points realisation discounts."
        ),
        "",
        (
            "For decisions, discount that theoretical value by the observed "
            f"marginal-points realisation multiplier of **{realization['decision_grade_multiplier']:.3f}×**. "
            "This is a small-sample calibration, not a permanent game constant."
        ),
        "",
        (
            "The Balanced-policy curve is retained in the JSON as a diagnostic "
            "only. It is excluded from the headline because that policy already "
            "assigns utility to price growth, which would make the valuation circular."
        ),
        "",
        "## Practical values",
        "",
        "| Races left | Future races using a new rise | Secured $0.3M now | Forecast $0.3M decision value | Forecast $0.3M middle 50% | Secured $1M decision value |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for races, row in examples.items():
        lines.append(
            f"| {races} | {row['races_budget_can_be_used']} | "
            f"{row['secured_0_3m_point_value']:.2f} pts | "
            f"{row['decision_grade_predicted_0_3m_point_value']:.2f} pts | "
            f"{row['decision_grade_predicted_0_3m_p25']:.2f} to "
            f"{row['decision_grade_predicted_0_3m_p75']:.2f} pts | "
            f"{row['decision_grade_secured_1_0m_point_value']:.2f} pts |"
        )
    lines.extend(
        [
            "",
            "## Affordability thresholds",
            "",
            (
                f"- Across {frontiers['genuine_deadline_states']} genuine deadline states, "
                "an extra $0.3M changed the continuation lineup in "
                f"{100 * frontiers['share_unlocked_by_0_3m']:.1f}% of states; "
                "$0.5M did so in "
                f"{100 * frontiers['share_unlocked_by_0_5m']:.1f}%."
            ),
            (
                f"- An extra $1.0M unlocked a higher-projected continuation in "
                f"{100 * frontiers['share_unlocked_by_1_0m']:.1f}% of states."
            ),
            (
                "- The median minimum tested unlock among states with an unlock was "
                f"${frontiers['median_minimum_tested_unlock_millions']:.1f}M "
                "using a $0.1M grid."
            ),
            (
                "- This is why the smooth curve should be treated as option value. "
                "The exact optimizer frontier overrides it whenever available."
            ),
            "",
            "## How the three season experiments fit in",
            "",
        ]
    )
    for row in experiments["comparisons"]:
        lines.append(
            f"- {row['experiment']}: Balanced scored "
            f"{row['balanced_points_advantage']:.0f} more points and finished "
            f"${row['balanced_budget_advantage_millions']:.1f}M higher "
            f"({row['naive_points_per_extra_million']:.1f} points per extra $1M)."
        )
    lines.extend(
        [
            (
                "- Those ratios are directional rather than causal: the managers "
                "owned different assets and had different chip outcomes. The "
                "marginal curve instead holds the deadline state and policy fixed."
            ),
            "",
            "## How the risk-tolerance follow-up fits in",
            "",
            (
                f"- The highest final budget was ${risk_experiment['highest_budget']:.1f}M. "
                "Two Budget Builder paths reached it."
            ),
            (
                "- Those equal-budget paths finished "
                f"{risk_experiment['points_spread_at_highest_budget']:.0f} points apart."
            ),
            (
                "- Budget Builder with medium tolerance scored "
                f"{risk_experiment['budget_builder_medium_vs_minimal']['points_difference']:.0f} "
                "more points than minimal risk while finishing with the same budget."
            ),
            (
                "- This supports treating budget as an option constraint, not as "
                "points already banked. Team selection quality still determines "
                "whether the spending power is converted into score."
            ),
            "",
            "## Price forecast calibration",
            "",
            f"- Predicted-rise observations: {forecast['predicted_rise_observations']}.",
            f"- Rise hit rate: {100 * forecast['predicted_rise_hit_rate']:.1f}%.",
            f"- Non-loss rate: {100 * forecast['predicted_rise_nonloss_rate']:.1f}%.",
            (
                "- Signed realised/predicted change ratio: "
                f"{forecast['signed_realization_ratio']:.3f}."
            ),
            (
                "- A forecast +$0.3M rise averaged an actual "
                f"+${forecast['by_predicted_bracket']['+0.3']['mean_actual_change']:.2f}M "
                f"with a {100 * forecast['by_predicted_bracket']['+0.3']['rise_hit_rate']:.1f}% hit rate."
            ),
            "",
            "## What happens after an actual rise",
            "",
            (
                "- Next move: "
                f"{100 * persistence['next_move_after_rise']['up']:.1f}% up, "
                f"{100 * persistence['next_move_after_rise']['flat']:.1f}% flat, "
                f"{100 * persistence['next_move_after_rise']['down']:.1f}% down."
            ),
        ]
    )
    for horizon, row in persistence["retention_by_future_rounds"].items():
        lines.append(
            f"- {horizon} rounds later: {100 * row['probability_at_or_above_pre_rise_price']:.1f}% "
            "remain at or above the pre-rise price; "
            f"{100 * row['expected_initial_rise_retained_fraction']:.1f}% of the "
            "initial rise is retained on average after clipping further gains; "
            f"median total retention ratio {row['median_retention_ratio']:.2f}×."
        )
    low_tier = persistence["next_move_by_price_tier"]["low"]
    high_tier = persistence["next_move_by_price_tier"]["high"]
    one_rise = persistence["next_move_by_consecutive_rises"]["1"]
    three_rises = persistence["next_move_by_consecutive_rises"]["3+"]
    easy_required = persistence["next_rise_by_required_score"][
        "at_or_below_recent_average"
    ]
    hard_required = persistence["next_rise_by_required_score"][
        "above_recent_average"
    ]
    lines.extend(
        [
            "",
            "## Why appreciation plateaus",
            "",
            (
                "- Any positive price bracket requires a rolling average of at least "
                "0.9 × current price; the maximum positive bracket requires 1.2 × price."
            ),
            (
                "- More precisely, the next score needed for any rise is "
                "max(0, 2.7 × current price − the previous two scores). The "
                "maximum-rise hurdle uses 3.6 × price instead."
            ),
            (
                "- Every additional $0.1M of price therefore raises the next-race "
                "hurdle by 0.27 points for any rise and 0.36 points for the "
                "maximum rise."
            ),
            "- At $10M that is 9.0 / 12.0 average points; at $15M it is 13.5 / 18.0; at $20M it is 18.0 / 24.0.",
            (
                "- Once price exceeds $18.5M, positive bracket sizes also shrink from "
                "+$0.2M / +$0.6M to +$0.1M / +$0.3M."
            ),
            (
                f"- After a low-tier rise, {100 * low_tier['up']:.1f}% rose again "
                f"next round. After a high-tier rise, {100 * high_tier['up']:.1f}% "
                "rose again."
            ),
            (
                f"- After the first rise in a streak, {100 * one_rise['up']:.1f}% "
                f"rose again. After three or more consecutive rises, "
                f"{100 * three_rises['up']:.1f}% rose again."
            ),
            (
                "- The streak result reflects momentum and selection: only assets "
                "that kept outperforming survived into the three-rise group. It "
                "does not imply that appreciation can continue indefinitely."
            ),
            (
                "- When the points required for another rise were at or below the "
                f"asset's recent average, the next-rise rate was "
                f"{100 * easy_required['next_rise_rate']:.1f}%. When the required "
                "score was above the recent average, it fell to "
                f"{100 * hard_required['next_rise_rate']:.1f}%."
            ),
            (
                "- These are the plateau controls: rising price increases the score "
                "required to keep appreciating, and the smaller high-tier brackets "
                "reduce the cash reward even when the asset keeps scoring."
            ),
            "",
            "## Decision rule",
            "",
            (
                "**Sacrifice points now only when:** points sacrificed < "
                "predicted budget rise × curve(races left − 1) × price-realisation discount "
                "× marginal-points realisation discount."
            ),
            "",
            (
                "On the current sample, an isolated extra $0.3M unlocked no different "
                f"continuation lineup in {100 * primary['isolated_0_3m_zero_value_share']:.0f}% "
                "of genuine deadline states. Treat the smoothed value as option value, "
                "not a guaranteed points gain."
            ),
            "",
            (
                "**Example:** a certain 10 points is worth more than a forecast $0.3M "
                "rise at every observed horizon unless that $0.3M crosses a specific "
                "affordability threshold identified by the optimizer."
            ),
            (
                f"With 11 races left, the current decision-grade estimate values a "
                "forecast +$0.3M at about "
                f"{examples['11']['decision_grade_predicted_0_3m_point_value']:.2f} points. "
                "Its bootstrap middle-50% range is "
                f"{examples['11']['decision_grade_predicted_0_3m_p25']:.2f} to "
                f"{examples['11']['decision_grade_predicted_0_3m_p75']:.2f} points. "
                "A forecast rise would need to be about "
                f"${examples['11']['predicted_budget_needed_for_10_points']:.2f}M "
                "to justify sacrificing 10 points under the smooth model."
            ),
            "",
            (
                "For an already secured rise, omit the forecast-reliability discount. "
                "If the extra budget does not cross a feasible-lineup price frontier, its "
                "immediate value can be zero; retain some option value for later transfers."
            ),
            "",
            "## Constraints",
            "",
            "- The fitted headline curve uses genuine R6-R13 archives only.",
            "- R1-R3 records remain in the JSON for sensitivity analysis but are excluded from the primary curve.",
            "- Choices use archived forecasts, while future price paths use realised closing prices.",
            "- The curve is fitted to one partial 2026 season and should be refreshed after every race.",
            "- The fitted uncertainty band resamples only eight genuine deadline states and is descriptive.",
            "- Values beyond eight usable races are extrapolated from the fitted saturation curve.",
            "- Greedy round-by-round optimization is not a globally optimal season search.",
            "- Budget value is lumpy because teams are discrete combinations, not divisible portfolios.",
        ]
    )
    return "\n".join(lines) + "\n"


def _cached_marginal_records(
    output_json: Path,
    completed_rounds: list[int],
) -> list[dict[str, Any]] | None:
    if not output_json.exists():
        return None
    try:
        payload = season._load_json(output_json)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("completed_rounds") != completed_rounds:
        return None
    records = payload.get("marginal_records")
    if not isinstance(records, list):
        return None
    available = {
        round(float(row["extra_budget"]), 1)
        for row in records
        if row.get("strategy") == "max_points"
    }
    if not set(BUDGET_DELTAS).issubset(available):
        return None
    return records


def build_public_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Return the compact, decision-grade subset consumed by the website."""
    curve = result["curves"]["max_points"]
    forecast = result["price_forecast_backtest"]
    realization = result["marginal_gain_realization"]
    frontier = result["affordability_frontiers"]
    bracket = forecast["by_predicted_bracket"]["+0.3"]
    genuine_rounds = sorted(
        {
            int(row["start_round"])
            for row in result["marginal_records"]
            if row.get("strategy") == "max_points"
            and not row.get("archive_reconstructed", False)
        }
    )
    return {
        "schema_version": 1,
        "season": result["season"],
        "updated_after_round": max(result["completed_rounds"]),
        "current_races_remaining": result["current_races_remaining"],
        "curve": {
            "formula": curve["formula"],
            "ceiling_points_per_million": curve[
                "ceiling_points_per_million"
            ],
            "tau_races": curve["tau_races"],
            "points_per_million": curve["curve_points_per_million"],
            "points_per_million_p25": curve[
                "curve_points_per_million_p25"
            ],
            "points_per_million_p75": curve[
                "curve_points_per_million_p75"
            ],
        },
        "calibration": {
            "decision_grade_multiplier": realization[
                "decision_grade_multiplier"
            ],
            "forecast_realization_discount": round(
                float(bracket["mean_actual_change"]) / 0.3,
                3,
            ),
            "forecast_signed_realization_discount": forecast[
                "signed_realization_ratio"
            ],
            "forecast_0_3m_mean_actual_change": bracket[
                "mean_actual_change"
            ],
            "forecast_0_3m_rise_hit_rate": bracket["rise_hit_rate"],
            "predicted_rise_hit_rate": forecast["predicted_rise_hit_rate"],
        },
        "affordability_frontier": {
            "genuine_deadline_states": frontier[
                "genuine_deadline_states"
            ],
            "median_minimum_unlock_millions": frontier[
                "median_minimum_tested_unlock_millions"
            ],
            "share_unlocked_by_0_3m": frontier["share_unlocked_by_0_3m"],
            "share_unlocked_by_0_5m": frontier["share_unlocked_by_0_5m"],
            "share_unlocked_by_1_0m": frontier["share_unlocked_by_1_0m"],
        },
        "plateau": result["price_plateau_rules"],
        "examples": result["decision_examples"],
        "source": {
            "completed_rounds": result["completed_rounds"],
            "genuine_deadline_rounds": genuine_rounds,
            "method": result["method"],
            "note": (
                "Experimental 2026 option value. Budget earned after a race "
                "can first be used at the following deadline."
            ),
        },
    }


def run(
    output_json: Path,
    output_markdown: Path,
    *,
    output_web_json: Path = DEFAULT_WEB_JSON,
    reuse_records: bool = False,
) -> dict[str, Any]:
    rounds = season.load_rounds()
    completed_rounds = [round_data.round_num for round_data in rounds]
    race_seed = season._load_json(season.SEED_DIR / "races.json")["races"]
    active_rounds = sum(not race.get("cancelled", False) for race in race_seed)
    current_races_remaining = active_rounds - len(rounds)
    records = (
        _cached_marginal_records(output_json, completed_rounds)
        if reuse_records
        else None
    )
    records_reused = records is not None
    if records is None:
        records = marginal_budget_records(rounds)
    forecast = price_forecast_backtest(rounds)
    persistence = price_persistence()
    frontiers = affordability_frontiers(records)
    realization = marginal_gain_realization(records)
    experiments = strategy_experiment_context()
    risk_experiment = risk_experiment_context()
    curves = {
        strategy: fit_budget_curve(
            records,
            strategy=strategy,
            max_horizon=max(current_races_remaining, len(rounds)),
        )
        for strategy in ("max_points", "balanced")
    }
    result = {
        "schema_version": 3,
        "season": season.CURRENT_SEASON,
        "completed_rounds": completed_rounds,
        "current_races_remaining": current_races_remaining,
        "budget_deltas_millions": list(BUDGET_DELTAS),
        "marginal_records_reused": records_reused,
        "method": (
            "Finite-difference continuation simulation from each historical "
            "deadline state; points-only policy is primary."
        ),
        "curves": curves,
        "price_plateau_rules": {
            "minimum_average_points_for_any_rise": "0.9 * current_price",
            "minimum_average_points_for_maximum_rise": "1.2 * current_price",
            "next_score_for_any_rise": (
                "max(0, 2.7 * current_price - previous_two_round_points)"
            ),
            "next_score_for_maximum_rise": (
                "max(0, 3.6 * current_price - previous_two_round_points)"
            ),
            "extra_next_score_hurdle_per_0_1m_price_rise": {
                "any_rise": 0.27,
                "maximum_rise": 0.36,
            },
            "low_tier_max_price": 18.5,
            "low_tier_positive_changes": [0.2, 0.6],
            "high_tier_positive_changes": [0.1, 0.3],
            "examples": {
                str(price): {
                    "any_rise_average_points": round(0.9 * price, 1),
                    "maximum_rise_average_points": round(1.2 * price, 1),
                }
                for price in (10, 15, 20, 25)
            },
        },
        "decision_examples": decision_examples(
            curves["max_points"], forecast, realization
        ),
        "price_forecast_backtest": forecast,
        "price_persistence": persistence,
        "affordability_frontiers": frontiers,
        "marginal_gain_realization": realization,
        "strategy_experiment_context": experiments,
        "risk_experiment_context": risk_experiment,
        "marginal_records": records,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    output_markdown.write_text(build_markdown(result), encoding="utf-8")
    output_web_json.parent.mkdir(parents=True, exist_ok=True)
    output_web_json.write_text(
        json.dumps(build_public_payload(result), indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--output-web-json", type=Path, default=DEFAULT_WEB_JSON)
    parser.add_argument(
        "--reuse-records",
        action="store_true",
        help=(
            "Reuse a complete marginal-record grid from the existing output "
            "JSON when completed rounds match."
        ),
    )
    args = parser.parse_args()
    result = run(
        args.output_json,
        args.output_markdown,
        output_web_json=args.output_web_json,
        reuse_records=args.reuse_records,
    )
    curve = result["curves"]["max_points"]
    print(f"JSON -> {args.output_json}")
    print(f"Report -> {args.output_markdown}")
    print(f"Website data -> {args.output_web_json}")
    print(
        "Primary curve: "
        f"{curve['ceiling_points_per_million']:.2f} * "
        f"(1-exp(-N/{curve['tau_races']:.2f})) points per $1M"
    )


if __name__ == "__main__":
    main()
