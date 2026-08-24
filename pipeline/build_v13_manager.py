"""Build the public V13 virtual-manager record.

V13 is the thirteenth policy produced by the 2026 manager experiments:
Budget Builder team selection with medium downside tolerance, domain-informed
chips, and a dedicated post-qualifying Final Fix decision when a trustworthy
archive exists.

The R1-R13 output is deliberately labelled a research replay.  Normal team
selection reads only archived pre-FP/post-FP forecasts.  Final Fix reads only a
post-qualifying archive and retains the outgoing driver's banked qualifying
points while comparing deterministic race points.

Usage:
    python pipeline/build_v13_manager.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import SEED_DIR, WEB_DATA_DIR
from config.driver_assets import active_driver_assets
from config.fantasy_prices import load_fantasy_price_data
from pipeline import simulate_fantasy_season_strategies as season


EXPERIMENT_PATH = (
    ROOT / "data" / "experiments" / "season_risk_tolerance_with_chips_2026.json"
)
OUTPUT_PATH = WEB_DATA_DIR / "v13_manager.json"
DECISION_DIR = ROOT / "data" / "v13" / "decisions"
V13_STRATEGY = "budget_builder"
V13_RISK_PROFILE = "medium_tolerance"
FINAL_FIX_MIN_PROJECTED_GAIN = 0.1
V13_LIVE_POLICY_VERSION = "horizon_budget_value_v2"
# Calibrated from data/experiments/budget_point_value_2026.json. A forecast
# price rise is discounted once for price realisation and once for how often
# extra budget actually converts into future points.
V13_BUDGET_VALUE_CEILING = 8.567
V13_BUDGET_VALUE_TAU = 1.8
V13_PRICE_REALISATION_DISCOUNT = 0.867
V13_POINTS_REALISATION_DISCOUNT = 0.625


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _names() -> tuple[dict[str, str], dict[str, str]]:
    drivers = _load_json(SEED_DIR / "drivers.json")["drivers"]
    constructors = _load_json(SEED_DIR / "constructors.json")["constructors"]
    return (
        {
            row["driver_id"]: f"{row['first_name']} {row['last_name']}"
            for row in drivers
        },
        {row["constructor_id"]: row["name"] for row in constructors},
    )


def _v13_manager(experiment: dict[str, Any]) -> dict[str, Any]:
    for manager in experiment["managers"]:
        if (
            manager.get("strategy") == V13_STRATEGY
            and manager.get("risk_profile") == V13_RISK_PROFILE
        ):
            return manager
    raise RuntimeError("Budget Builder / medium-tolerance manager is missing")


def _phase_archive_path(round_num: int, phase: str) -> Path:
    """Resolve an immutable phase source, including the explicit R14 fix."""
    archive = WEB_DATA_DIR / f"predictions_round{round_num}_{phase}.json"
    if round_num == 14 and phase == "pre_fp":
        corrected = WEB_DATA_DIR / (
            "predictions_round14_pre_fp_availability_corrected.json"
        )
        if corrected.exists():
            return corrected
    return archive


def live_price_gain_value(round_num: int) -> float:
    """Decision-grade point value of a forecast $1M rise after this round."""
    races = _load_json(SEED_DIR / "races.json")["races"]
    usable_future_rounds = sum(
        int(row["round"]) > int(round_num) and not row.get("cancelled", False)
        for row in races
    )
    secured_value = V13_BUDGET_VALUE_CEILING * (
        1.0 - math.exp(-usable_future_rounds / V13_BUDGET_VALUE_TAU)
    )
    return round(
        secured_value
        * V13_PRICE_REALISATION_DISCOUNT
        * V13_POINTS_REALISATION_DISCOUNT,
        3,
    )


def live_policy(round_num: int) -> dict[str, Any]:
    return {
        "policy_version": V13_LIVE_POLICY_VERSION,
        "strategy": V13_STRATEGY,
        "risk_profile": V13_RISK_PROFILE,
        "price_gain_weight": live_price_gain_value(round_num),
        "negative_p5_weight": season.RISK_PROFILE_WEIGHTS[V13_RISK_PROFILE],
        "price_value_method": "horizon curve × price reliability × points realisation",
    }


def _official_driver_points(
    official: dict[str, Any], round_num: int, asset_id: str
) -> float:
    """Resolve an active seat ID to its historical official points key."""
    rows = official[str(round_num)]["drivers"]
    if asset_id in rows:
        return float(rows[asset_id])
    for asset in active_driver_assets(14):
        if asset["asset_id"] != asset_id and asset_id not in asset.get("legacy_asset_ids", []):
            continue
        candidates = [asset.get("model_driver_id"), *asset.get("legacy_asset_ids", [])]
        for candidate in candidates:
            if candidate in rows:
                return float(rows[candidate])
        # Tsunoda has no 2026 official fantasy history because he was not in
        # the canonical season roster before this one-round seat correction.
        # A zero history is explicit and keeps R1-R13 records untouched.
        if asset.get("asset_context", "").startswith("substitute"):
            return 0.0
    # A historical asset can disappear from the active roster after a seat
    # substitution (Hadjar is absent from the R14 official field, for
    # example). It has no points for that round; do not let the missing seat
    # prevent the next-round forecast from being built.
    if int(round_num) >= 14:
        return 0.0
    raise KeyError(asset_id)


def _phase_projection(
    base: season.RoundInputs,
    *,
    phase: str,
    official: dict[str, Any],
    completed_rounds: list[int],
) -> season.RoundInputs | None:
    archive = _phase_archive_path(base.round_num, phase)
    if not archive.exists():
        return None
    payload = _load_json(archive)
    if payload.get("phase") != phase:
        return None

    driver_rows = {row["driver_id"]: row for row in payload["drivers"]}
    constructor_rows = {
        row["constructor_id"]: row for row in payload["constructors"]
    }
    prior_rounds = [value for value in completed_rounds if value < base.round_num]

    def projection(row: dict[str, Any]) -> float:
        value = row.get("mc_total_mean")
        return float(value if value is not None else row["expected_points"])

    driver_projection = np.array(
        [projection(driver_rows[key]) for key in base.drivers], dtype=float
    )
    constructor_projection = np.array(
        [projection(constructor_rows[key]) for key in base.constructors], dtype=float
    )
    driver_gain = np.array(
        [
            season._expected_price_change(
                price=float(base.driver_prices[index]),
                projected_points=float(driver_projection[index]),
                past_points=[
                    _official_driver_points(official, round_num, key)
                    for round_num in prior_rounds
                ],
            )
            for index, key in enumerate(base.drivers)
        ]
    )
    constructor_gain = np.array(
        [
            season._expected_price_change(
                price=float(base.constructor_prices[index]),
                projected_points=float(constructor_projection[index]),
                past_points=[
                    float(official[str(round_num)]["constructors"][key])
                    for round_num in prior_rounds
                ],
            )
            for index, key in enumerate(base.constructors)
        ]
    )
    weather = payload.get("weather_adjustments") or {}

    return replace(
        base,
        reconstructed=bool(payload.get("reconstructed", False)),
        archive_path=str(archive.relative_to(ROOT)).replace("\\", "/"),
        driver_projection=driver_projection,
        constructor_projection=constructor_projection,
        driver_p5=np.array(
            [float(driver_rows[key].get("mc_total_p5", 0.0)) for key in base.drivers]
        ),
        constructor_p5=np.array(
            [
                float(constructor_rows[key].get("mc_total_p5", 0.0))
                for key in base.constructors
            ]
        ),
        driver_std=np.array(
            [float(driver_rows[key].get("mc_total_std", 0.0)) for key in base.drivers]
        ),
        driver_projected_gain=driver_gain,
        constructor_projected_gain=constructor_gain,
        rain_risk=str(weather.get("rain_risk") or "NONE").upper(),
        weather_dnf_mult=float(weather.get("dnf_mult") or 1.0),
        mean_dnf_probability=float(
            np.mean(
                [
                    float(driver_rows[key].get("dnf_probability", 0.0))
                    for key in base.drivers
                ]
            )
        ),
    )


def _candidate_payload(
    candidate: season.Candidate,
    phase_row: season.RoundInputs,
    state: season.TeamState | None = None,
) -> dict[str, Any]:
    archive = ROOT / phase_row.archive_path
    payload: dict[str, Any] = {
        "round": phase_row.round_num,
        "race": phase_row.race_name,
        "status": "provisional",
        "phase": "pre_fp",
        "archive": phase_row.archive_path,
        "archive_sha256": _sha256(archive),
        "archive_reconstructed": phase_row.reconstructed,
        "drivers": list(candidate.drivers),
        "constructors": list(candidate.constructors),
        "captain": candidate.captain,
        "second_boost": candidate.second_captain,
        "projected_points": candidate.projected_points,
        "projected_price_gain": candidate.projected_gain,
        "downside_risk": candidate.downside_risk,
        "transfers": candidate.transfers,
        "transfer_penalty": candidate.transfer_penalty,
        "team_cost": candidate.cost,
        "policy": live_policy(phase_row.round_num),
    }
    if state is not None:
        payload["changes"] = {
            "drivers_out": sorted(set(state.drivers) - set(candidate.drivers)),
            "drivers_in": sorted(set(candidate.drivers) - set(state.drivers)),
            "constructors_out": sorted(
                set(state.constructors) - set(candidate.constructors)
            ),
            "constructors_in": sorted(
                set(candidate.constructors) - set(state.constructors)
            ),
        }
    return payload


def _early_thoughts(
    final_rows: list[dict[str, Any]],
    base_rounds: list[season.RoundInputs],
) -> dict[int, dict[str, Any] | None]:
    official = _load_json(SEED_DIR / "official_fantasy_points.json")["rounds"]
    completed = sorted(int(value) for value in official)
    base_by_round = {row.round_num: row for row in base_rounds}
    state: season.TeamState | None = None
    output: dict[int, dict[str, Any] | None] = {}

    for final_row in final_rows:
        round_num = int(final_row["round"])
        phase_row = _phase_projection(
            base_by_round[round_num],
            phase="pre_fp",
            official=official,
            completed_rounds=completed,
        )
        if phase_row is None:
            output[round_num] = None
        else:
            candidate = season.choose_lineup(
                round_data=phase_row,
                combos=season.build_combo_matrices(phase_row),
                state=state,
                strategy=V13_STRATEGY,
                chip=final_row.get("chip"),
                risk_profile=V13_RISK_PROFILE,
            )
            output[round_num] = _candidate_payload(candidate, phase_row)

        state = season.TeamState(
            drivers=tuple(final_row["persistent_drivers"]),
            constructors=tuple(final_row["persistent_constructors"]),
            bank=float(final_row["bank_after_transfers"]),
            budget=float(final_row["budget_after"]),
            free_transfers=int(final_row["free_transfers_next"]),
        )
    return output


def _future_phase_projection(
    round_num: int,
    phase: str,
    official: dict[str, Any],
) -> season.RoundInputs | None:
    """Build a projection row for a future round before official results exist."""
    archive = _phase_archive_path(round_num, phase)
    if not archive.exists():
        return None
    payload = _load_json(archive)
    if payload.get("phase") != phase:
        return None

    archive_drivers = {row["driver_id"]: row for row in payload["drivers"]}
    archive_constructors = {
        row["constructor_id"]: row for row in payload["constructors"]
    }
    drivers = tuple(archive_drivers)
    constructors = tuple(archive_constructors)
    prices = load_fantasy_price_data(round_num=round_num)
    driver_price_map = prices.get("drivers", {})
    constructor_price_map = prices.get("constructors", {})

    def price(group: dict[str, Any], asset_id: str, fallback: float) -> float:
        entry = group.get(asset_id) or {}
        value = entry.get("current_price")
        return float(value if value is not None else fallback)

    driver_prices = np.array(
        [
            price(
                driver_price_map,
                key,
                float(archive_drivers[key].get("current_price", archive_drivers[key].get("price", 0.0))),
            )
            for key in drivers
        ],
        dtype=float,
    )
    constructor_prices = np.array(
        [
            price(
                constructor_price_map,
                key,
                float(archive_constructors[key].get("current_price", archive_constructors[key].get("price", 0.0))),
            )
            for key in constructors
        ],
        dtype=float,
    )
    track_data = _load_json(WEB_DATA_DIR / "track_data.json")
    race_name = payload.get("race") or f"Round {round_num}"
    circuit_id = track_data["race_circuit_map"].get(race_name, "unknown")
    features = track_data["track_features"].get(circuit_id, {})
    base = season.RoundInputs(
        round_num=round_num,
        race_name=race_name,
        reconstructed=bool(payload.get("reconstructed", False)),
        archive_path=str(archive.relative_to(ROOT)).replace("\\", "/"),
        drivers=drivers,
        constructors=constructors,
        driver_projection=np.zeros(len(drivers)),
        constructor_projection=np.zeros(len(constructors)),
        driver_p5=np.zeros(len(drivers)),
        constructor_p5=np.zeros(len(constructors)),
        driver_std=np.zeros(len(drivers)),
        driver_prices=driver_prices,
        constructor_prices=constructor_prices,
        driver_close_prices=driver_prices.copy(),
        constructor_close_prices=constructor_prices.copy(),
        driver_actual=np.zeros(len(drivers)),
        constructor_actual=np.zeros(len(constructors)),
        driver_projected_gain=np.zeros(len(drivers)),
        constructor_projected_gain=np.zeros(len(constructors)),
        circuit_id=circuit_id,
        overtaking_difficulty=int(features.get("overtaking_difficulty", 5)),
        turn1_incident_risk=int(features.get("turn1_incident_risk", 5)),
        safety_car_probability=int(features.get("safety_car_probability", 5)),
    )
    completed = sorted(int(value) for value in official if int(value) < round_num)
    return _phase_projection(
        base,
        phase=phase,
        official=official,
        completed_rounds=completed,
    )


def _auto_early_thoughts(
    round_num: int,
    state: season.TeamState,
    official: dict[str, Any],
) -> dict[str, Any] | None:
    """Create a provisional next-round decision when its pre-FP archive exists."""
    phase_row = _future_phase_projection(round_num, "pre_fp", official)
    if phase_row is None:
        return None
    candidate = season.choose_lineup(
        round_data=phase_row,
        combos=season.build_combo_matrices(phase_row),
        state=state,
        strategy=V13_STRATEGY,
        chip=None,
        risk_profile=V13_RISK_PROFILE,
        price_gain_value=live_price_gain_value(round_num),
    )
    return _candidate_payload(candidate, phase_row, state=state)


def _next_scheduled_round(after_round: int) -> int | None:
    races = _load_json(SEED_DIR / "races.json")["races"]
    upcoming = [
        int(row["round"])
        for row in races
        if int(row["round"]) > int(after_round) and not row.get("cancelled", False)
    ]
    return min(upcoming) if upcoming else None


def _actual_driver_points(
    official_round: dict[str, Any], round_num: int, asset_id: str
) -> float:
    rows = official_round["drivers"]
    if asset_id in rows:
        return float(rows[asset_id])
    for asset in active_driver_assets(round_num):
        if asset["asset_id"] != asset_id and asset_id not in asset.get("legacy_asset_ids", []):
            continue
        for candidate in [asset.get("model_driver_id"), *asset.get("legacy_asset_ids", [])]:
            if candidate in rows:
                return float(rows[candidate])
        return 0.0
    raise KeyError(f"R{round_num} official points are missing {asset_id}")


def _live_actual_score(
    decision: dict[str, Any],
    official_round: dict[str, Any],
    round_num: int,
) -> tuple[float, str, str | None]:
    driver_scores = {
        key: _actual_driver_points(official_round, round_num, key)
        for key in decision["drivers"]
    }
    constructor_scores = {
        key: float(official_round["constructors"][key])
        for key in decision["constructors"]
    }
    chip = decision.get("chip")
    if chip == "no_negative":
        driver_scores = {key: max(0.0, value) for key, value in driver_scores.items()}
        constructor_scores = {
            key: max(0.0, value) for key, value in constructor_scores.items()
        }
    captain = decision.get("captain")
    second = decision.get("second_boost")
    if chip == "autopilot":
        captain = max(driver_scores, key=driver_scores.get)
        second = None
    captain_bonus = float(driver_scores[captain]) if captain else 0.0
    if chip == "3x_boost":
        captain_bonus += float(driver_scores[captain])
        if second:
            captain_bonus += float(driver_scores[second])
    gross = sum(driver_scores.values()) + sum(constructor_scores.values()) + captain_bonus
    return (
        round(gross - float(decision.get("transfer_penalty", 0)), 1),
        str(captain),
        str(second) if second else None,
    )


def _price_after_round(round_num: int) -> dict[str, Any]:
    return load_fantasy_price_data(round_num=round_num)


def _live_rounds_and_state(
    manager: dict[str, Any],
    final_fix: dict[str, Any] | None,
    official: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, int]]:
    """Roll the published V13 team through completed post-replay rounds."""
    final_drivers = list(manager["summary"]["final_drivers"])
    final_bank = float(manager["summary"]["final_bank"])
    if final_fix:
        final_drivers[final_drivers.index(final_fix["outgoing"])] = final_fix["incoming"]
        final_bank = float(final_fix["bank_after"])

    chips_used: dict[str, int] = {
        chip: int(round_num)
        for round_num, chip in manager.get("chip_schedule", {}).items()
    }
    if final_fix:
        chips_used["final_fix"] = int(final_fix["round"])
    state: dict[str, Any] = {
        "drivers": final_drivers,
        "constructors": list(manager["summary"]["final_constructors"]),
        "budget": float(manager["summary"]["final_budget"]),
        "bank": final_bank,
        "free_transfers": int(manager["rounds"][-1]["free_transfers_next"]),
    }
    cumulative = float(manager["summary"]["season_points"]) + (
        float(final_fix["actual_gain"]) if final_fix else 0.0
    )
    live_rounds: list[dict[str, Any]] = []
    replay_end = int(manager["rounds"][-1]["round"])

    for round_num in sorted(int(value) for value in official if int(value) > replay_end):
        early = _live_decision(round_num, "pre_fp")
        final = _live_decision(round_num, "post_fp") or early
        if final is None:
            break
        official_round = official[str(round_num)]
        actual_points, actual_captain, actual_second = _live_actual_score(
            final, official_round, round_num
        )
        chip = final.get("chip")
        previous_state = season.TeamState(
            drivers=tuple(state["drivers"]),
            constructors=tuple(state["constructors"]),
            bank=float(state["bank"]),
            budget=float(state["budget"]),
            free_transfers=int(state["free_transfers"]),
        )
        if chip == "limitless":
            persistent_drivers = list(previous_state.drivers)
            persistent_constructors = list(previous_state.constructors)
            bank_after = previous_state.bank
        else:
            persistent_drivers = list(final["drivers"])
            persistent_constructors = list(final["constructors"])
            bank_after = round(
                previous_state.budget - float(final.get("team_cost", 0.0)), 1
            )
        free_next = season.next_free_transfers(
            previous_state.free_transfers,
            int(final.get("transfers", 0)),
            chip,
        )

        prices = _price_after_round(round_num)
        driver_prices = prices.get("drivers", {})
        constructor_prices = prices.get("constructors", {})

        def close_price(group: dict[str, Any], asset_id: str) -> float:
            entry = group.get(asset_id) or {}
            if isinstance(entry, dict):
                value = entry.get("current_price")
            else:
                value = entry
            return float(value if value is not None else 0.0)

        budget_after = round(
            bank_after
            + sum(close_price(driver_prices, key) for key in persistent_drivers)
            + sum(close_price(constructor_prices, key) for key in persistent_constructors),
            1,
        )
        cumulative += actual_points
        final_snapshot = dict(final)
        final_snapshot.setdefault("reasons", _reason_lines(final))
        live_rounds.append(
            {
                "round": round_num,
                "race": official_round.get("race") or final.get("race") or f"Round {round_num}",
                "provenance": "live",
                "early_thoughts": early,
                "post_fp_final": final_snapshot,
                "final_fix": _live_decision(round_num, "post_quali"),
                "actual_points": round(actual_points, 1),
                "projected_points": round(float(final.get("projected_points", 0.0)), 1),
                "score_delta_vs_projection": round(
                    actual_points - float(final.get("projected_points", 0.0)), 1
                ),
                "cumulative_points": round(cumulative, 1),
                "budget_after": budget_after,
                "free_transfers_next": free_next,
                "actual_captain": actual_captain,
                "actual_second_boost": actual_second,
            }
        )
        state = {
            "drivers": persistent_drivers,
            "constructors": persistent_constructors,
            "budget": budget_after,
            "bank": round(bank_after, 1),
            "free_transfers": free_next,
        }
        if chip in season.CHIPS:
            chips_used[chip] = round_num

    return live_rounds, state, chips_used


def _valid_post_quali_archive(round_num: int) -> Path | None:
    candidates = [
        WEB_DATA_DIR / f"predictions_round{round_num}.json",
        WEB_DATA_DIR / f"predictions_round{round_num}_post_quali.json",
    ]
    valid: list[tuple[datetime, Path]] = []
    for path in candidates:
        if not path.exists():
            continue
        payload = _load_json(path)
        if payload.get("phase") != "post_quali":
            continue
        if not (payload.get("final_fix") or {}).get("qualifying_locked"):
            continue
        generated = datetime.fromisoformat(payload["generated_at"])
        valid.append((generated, path))
    if not valid:
        return None
    # The canonical file is retained when it is the earlier, genuine pre-race
    # snapshot and a later phase archive was overwritten during post-race export.
    return min(valid, key=lambda item: item[0])[1]


def _final_fix(
    row: dict[str, Any],
    driver_names: dict[str, str],
) -> dict[str, Any] | None:
    round_num = int(row["round"])
    archive = _valid_post_quali_archive(round_num)
    if archive is None:
        return None
    payload = _load_json(archive)
    drivers = {item["driver_id"]: item for item in payload["drivers"]}
    owned = list(row["persistent_drivers"])
    bank = float(row["bank_after_transfers"])
    captain = row["captain"]
    best: dict[str, Any] | None = None

    for outgoing_id in owned:
        outgoing = drivers[outgoing_id]
        available = float(outgoing["current_price"]) + bank
        multiplier = 2 if outgoing_id == captain else 1
        for incoming_id, incoming in drivers.items():
            if incoming_id in owned:
                continue
            if float(incoming["current_price"]) > available + 1e-9:
                continue
            projected_gain = multiplier * (
                float(incoming["projected_points_race"])
                - float(outgoing["projected_points_race"])
            )
            candidate = {
                "outgoing": outgoing_id,
                "incoming": incoming_id,
                "outgoing_name": driver_names[outgoing_id],
                "incoming_name": driver_names[incoming_id],
                "projected_gain": round(projected_gain, 2),
                "bank_before": round(bank, 1),
                "bank_after": round(
                    bank
                    + float(outgoing["current_price"])
                    - float(incoming["current_price"]),
                    1,
                ),
                "boost_transferred": outgoing_id == captain,
            }
            if best is None or candidate["projected_gain"] > best["projected_gain"]:
                best = candidate

    if best is None or best["projected_gain"] < FINAL_FIX_MIN_PROJECTED_GAIN:
        return None

    actual_path = ROOT / "data" / "predictions" / f"round{round_num}" / "actual_fantasy_points.json"
    actual = _load_json(actual_path)
    actual_rows = {item["driver_id"]: item for item in actual["drivers"]}
    multiplier = 2 if best["boost_transferred"] else 1
    best["actual_gain"] = round(
        multiplier
        * (
            float(actual_rows[best["incoming"]]["race_points"])
            - float(actual_rows[best["outgoing"]]["race_points"])
        ),
        1,
    )
    best.update(
        {
            "status": "played",
            "phase": "post_quali",
            "round": round_num,
            "archive": str(archive.relative_to(ROOT)).replace("\\", "/"),
            "archive_sha256": _sha256(archive),
            "generated_at": payload["generated_at"],
            "points_basis": "projected_points_race",
            "banked_qualifying_driver": best["outgoing"],
        }
    )
    return best


def _reason_lines(row: dict[str, Any]) -> list[str]:
    transfer_text = (
        f" after a {row['transfer_penalty']}-point transfer penalty"
        if row["transfer_penalty"]
        else ""
    )
    chip = row.get("chip")
    lines = [
        f"The post-FP lineup projected {row['projected_points']:.1f} points{transfer_text}.",
        f"It carried ${row['projected_price_gain']:.1f}M of forecast price movement into the budget-first objective.",
        f"Its combined negative-P5 exposure was {row['downside_risk']:.1f} under V13's medium-risk rule.",
    ]
    if chip:
        lines.append(f"V13 played {chip.replace('_', ' ').title()} under the frozen research chip policy.")
    return lines


def _live_decision(round_num: int, phase: str) -> dict[str, Any] | None:
    """Load an immutable live decision, if one has been published locally."""
    candidates = [DECISION_DIR / f"round{round_num}_{phase}.json"]
    candidates.extend(
        sorted(
            DECISION_DIR.glob(f"round{round_num}_{phase}_revision*.json"),
            key=lambda path: int(path.stem.rsplit("revision", 1)[1]),
        )
    )
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    path = existing[-1]
    decision = _load_json(path)
    if decision.get("round") != round_num or decision.get("phase") != phase:
        raise ValueError(f"Malformed V13 decision record: {path}")
    return decision


def build_payload() -> dict[str, Any]:
    experiment = _load_json(EXPERIMENT_PATH)
    manager = _v13_manager(experiment)
    driver_names, constructor_names = _names()
    official = _load_json(SEED_DIR / "official_fantasy_points.json")["rounds"]
    final_rows = manager["rounds"]
    base_rounds = season.load_rounds(through_round=int(final_rows[-1]["round"]))
    early = _early_thoughts(final_rows, base_rounds)

    final_fix = None
    # Final Fix is evaluated chronologically.  It remains unused until the
    # first trustworthy qualifying-locked archive produces a positive switch.
    for row in final_rows:
        candidate = _final_fix(row, driver_names)
        if candidate is not None:
            final_fix = candidate
            break

    score_adjustment = float(final_fix["actual_gain"]) if final_fix else 0.0
    rounds: list[dict[str, Any]] = []
    cumulative_adjustment = 0.0
    for row in final_rows:
        round_num = int(row["round"])
        round_fix = final_fix if final_fix and final_fix["round"] == round_num else None
        if round_fix:
            cumulative_adjustment += float(round_fix["actual_gain"])
        post_fp_archive = ROOT / row["archive"]
        rounds.append(
            {
                "round": round_num,
                "race": row["race"],
                "provenance": "reconstructed" if row["archive_reconstructed"] else "genuine_archive",
                "early_thoughts": early[round_num],
                "post_fp_final": {
                    "status": "frozen_replay",
                    "phase": "post_fp",
                    "archive": row["archive"],
                    "archive_sha256": _sha256(post_fp_archive),
                    "archive_reconstructed": row["archive_reconstructed"],
                    "drivers": row["drivers"],
                    "constructors": row["constructors"],
                    "persistent_drivers": row["persistent_drivers"],
                    "persistent_constructors": row["persistent_constructors"],
                    "captain": row["captain"],
                    "second_boost": row["second_boost"],
                    "chip": row["chip"],
                    "transfers": row["transfers"],
                    "transfer_penalty": row["transfer_penalty"],
                    "projected_points": row["projected_points"],
                    "projected_price_gain": row["projected_price_gain"],
                    "downside_risk": row["downside_risk"],
                    "team_cost": row["played_team_cost"],
                    "budget_before": row["budget_before"],
                    "bank_after_transfers": row["bank_after_transfers"],
                    "reasons": _reason_lines(row),
                },
                "final_fix": round_fix,
                "actual_points": round(
                    float(row["actual_points_net"])
                    + (float(round_fix["actual_gain"]) if round_fix else 0.0),
                    1,
                ),
                "cumulative_points": round(
                    float(row["season_points"]) + cumulative_adjustment, 1
                ),
                "budget_after": row["budget_after"],
                "free_transfers_next": row["free_transfers_next"],
            }
        )

    replay_final_bank = float(manager["summary"]["final_bank"])
    if final_fix:
        replay_final_bank = float(final_fix["bank_after"])
    live_rounds, live_state, chips_used = _live_rounds_and_state(
        manager,
        final_fix,
        official,
    )
    completed_rounds = sorted(int(value) for value in official)
    as_of_round = live_rounds[-1]["round"] if live_rounds else int(final_rows[-1]["round"])
    next_round = _next_scheduled_round(as_of_round)
    state_for_optimizer = season.TeamState(
        drivers=tuple(live_state["drivers"]),
        constructors=tuple(live_state["constructors"]),
        bank=float(live_state["bank"]),
        budget=float(live_state["budget"]),
        free_transfers=int(live_state["free_transfers"]),
    )
    next_early = None
    next_post_fp = None
    if next_round is not None:
        next_early = _live_decision(next_round, "pre_fp") or _auto_early_thoughts(
            next_round,
            state_for_optimizer,
            official,
        )
        next_post_fp = _live_decision(next_round, "post_fp")
    latest_live = live_rounds[-1] if live_rounds else None
    live_total = round(
        latest_live["cumulative_points"]
        if latest_live
        else float(manager["summary"]["season_points"])
        + (float(final_fix["actual_gain"]) if final_fix else 0.0),
        1,
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "manager": {
            "id": "v13",
            "name": "V13",
            "tagline": "Budget-aware. Medium-risk. Transparent at every decision.",
            "strategy": V13_STRATEGY,
            "risk_profile": V13_RISK_PROFILE,
            "policy_version": "2026.3",
            "policy": {
                "team_selection_phase": "post_fp",
                "early_thoughts_phase": "pre_fp",
                "price_gain_weight": (
                    live_price_gain_value(next_round) if next_round is not None else 0.0
                ),
                "price_gain_method": (
                    "Horizon-aware budget curve discounted for forecast reliability "
                    "and realised conversion into future points."
                ),
                "research_replay_price_gain_weight": (
                    season.BUDGET_BUILDER_PRICE_GAIN_VALUE
                ),
                "negative_p5_weight": season.RISK_PROFILE_WEIGHTS[V13_RISK_PROFILE],
                "free_transfers_per_round": season.BASE_FREE_TRANSFERS,
                "max_free_transfers_after_rollover": season.MAX_BANKED_TRANSFERS,
                "final_fix_basis": "qualifying_locked_projected_race_points",
                "three_x_timing": (
                    "At post-FP lock, play only when the selected team's extra "
                    "3x value is at least the largest remaining priors-only "
                    "top-two driver forecast; otherwise save it."
                ),
            },
        },
        "competition": {
            "status": "registration_open",
            "scoring_basis": "full_2026_official_season_total",
            "registration_open": True,
            "registration_deadline_round": 22,
            "registration_deadline_race": "Las Vegas Grand Prix",
            "registration_deadline_at": "2026-11-21T04:00:00Z",
            "registration_window": "Registration is open now and closes at the F1 Fantasy team-lock deadline for Round 22, the third-last race: 21 November 2026 at 04:00 UTC.",
            "evidence": "Confirm an email address before the deadline. After the season, submit one official F1 Fantasy team and its full-season score screenshot; a private league remains available as a verification fallback.",
            "prizes_usd": [100, 50, 30],
            "eligibility_note": "Entry is free. The registration email must be confirmed before the Round 22 team lock. Final score verification and payout terms apply.",
        },
        "research_replay": {
            "label": "R1-R13 research replay",
            "disclaimer": (
                "Full-season counterfactual. R1-R3 forecasts were reconstructed, "
                "and the V13 policy was selected after the underlying experiments."
            ),
            "start_round": 1,
            "end_round": 13,
            "base_points_before_final_fix": manager["summary"]["season_points"],
            "final_fix_adjustment": score_adjustment,
            "total_points": round(
                float(manager["summary"]["season_points"]) + score_adjustment, 1
            ),
            "final_budget": manager["summary"]["final_budget"],
            "final_bank": round(replay_final_bank, 1),
            "genuine_archive_points_before_final_fix": manager["summary"][
                "genuine_archive_points"
            ],
            "rounds": rounds,
        },
        "live_history": live_rounds,
        "live_status": {
            "status": "live" if latest_live else "replay_only",
            "through_round": as_of_round,
            "race": latest_live["race"] if latest_live else None,
            "round_points": latest_live["actual_points"] if latest_live else None,
            "projected_points": latest_live["projected_points"] if latest_live else None,
            "score_delta_vs_projection": (
                latest_live["score_delta_vs_projection"] if latest_live else None
            ),
            "total_points": live_total,
            "budget": round(float(live_state["budget"]), 1),
            "bank": round(float(live_state["bank"]), 1),
        },
        "current_state": {
            "as_of_round": as_of_round,
            "drivers": live_state["drivers"],
            "constructors": live_state["constructors"],
            "budget": round(float(live_state["budget"]), 1),
            "bank": round(float(live_state["bank"]), 1),
            "free_transfers": int(live_state["free_transfers"]),
            "chips_remaining": [chip for chip in season.CHIPS if chip not in chips_used],
            "chips_used": chips_used,
            "next_round": next_round,
            "early_thoughts": next_early,
            "post_fp_final": next_post_fp,
        },
        "labels": {
            "drivers": driver_names,
            "constructors": constructor_names,
        },
        "source": {
            "experiment": str(EXPERIMENT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "experiment_sha256": _sha256(EXPERIMENT_PATH),
            "official_points_rounds": completed_rounds,
            "live_decisions": [row["round"] for row in live_rounds],
        },
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    replay = payload["research_replay"]
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)}: "
        f"R1-R13={replay['total_points']:.1f}, "
        f"budget=${replay['final_budget']:.1f}M"
    )


if __name__ == "__main__":
    main()
