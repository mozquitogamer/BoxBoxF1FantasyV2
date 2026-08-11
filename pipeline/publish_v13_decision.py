"""Freeze a V13 pre-FP or post-FP decision and publish it to the website.

Each decision is written once under ``data/v13/decisions``.  The source
forecast hash, its generation time, the F1 Fantasy lock time, and the previous
decision hash are stored with the lineup.  Re-running the same command never
rewrites an existing record.

Usage:
    python pipeline/publish_v13_decision.py --round 14 --phase pre_fp
    python pipeline/publish_v13_decision.py --round 14 --phase post_fp
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import SEED_DIR, WEB_DATA_DIR
from pipeline import build_v13_manager as v13
from pipeline import simulate_fantasy_season_strategies as season


DECISION_DIR = ROOT / "data" / "v13" / "decisions"
PUBLIC_PATH = WEB_DATA_DIR / "v13_manager.json"
HORIZON_PATH = WEB_DATA_DIR / "horizon_projections.json"
APP_JS_PATH = ROOT / "web" / "public" / "app.js"
PHASE_ORDER = {"pre_fp": 0, "post_fp": 1}


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _record_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lock_deadline(round_num: int) -> str:
    """Read the website's canonical deadline table without duplicating it."""
    source = APP_JS_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"\{{\s*round:\s*{round_num},\s*race:\s*'[^']+',\s*"
        rf"lock:\s*'(?P<lock>[^']+)'",
        re.S,
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(f"No lock deadline is configured for R{round_num}")
    return match.group("lock")


def _opening_prices(round_num: int) -> tuple[str, dict[str, Any]]:
    price_history = v13._load_json(SEED_DIR / "fantasy_prices.json")["price_history"]
    available = sorted(int(value) for value in price_history if int(value) < round_num)
    if not available:
        key = "0"
    else:
        key = str(available[-1])
    return key, price_history[key]


def _round_input(round_num: int, phase: str) -> season.RoundInputs:
    archive = WEB_DATA_DIR / f"predictions_round{round_num}_{phase}.json"
    if not archive.exists():
        raise FileNotFoundError(f"Missing {phase} archive: {archive}")
    payload = v13._load_json(archive)
    if payload.get("phase") != phase:
        raise ValueError(f"{archive.name} reports phase={payload.get('phase')!r}")

    generated_at = payload.get("generated_at")
    if not generated_at:
        raise ValueError(f"{archive.name} has no generated_at timestamp")
    lock = _lock_deadline(round_num)
    if _parse_time(generated_at) >= _parse_time(lock):
        raise ValueError(
            f"Refusing R{round_num} {phase}: source was generated at {generated_at}, "
            f"after the {lock} lock"
        )

    driver_roster = v13._load_json(SEED_DIR / "drivers.json")["drivers"]
    constructor_roster = v13._load_json(SEED_DIR / "constructors.json")["constructors"]
    drivers = tuple(row["driver_id"] for row in driver_roster)
    constructors = tuple(row["constructor_id"] for row in constructor_roster)
    _, prices = _opening_prices(round_num)
    driver_prices = np.array([float(prices["drivers"][key]) for key in drivers])
    constructor_prices = np.array(
        [float(prices["constructors"][key]) for key in constructors]
    )

    official = v13._load_json(SEED_DIR / "official_fantasy_points.json")["rounds"]
    completed = sorted(int(value) for value in official if int(value) < round_num)
    track_data = v13._load_json(WEB_DATA_DIR / "track_data.json")
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
    resolved = v13._phase_projection(
        base,
        phase=phase,
        official=official,
        completed_rounds=completed,
    )
    if resolved is None:
        raise RuntimeError(f"Could not resolve R{round_num} {phase}")
    return resolved


def _state(payload: dict[str, Any]) -> season.TeamState:
    current = payload["current_state"]
    return season.TeamState(
        drivers=tuple(current["drivers"]),
        constructors=tuple(current["constructors"]),
        bank=float(current["bank"]),
        budget=float(current["budget"]),
        free_transfers=int(current["free_transfers"]),
    )


def _future_three_x_ceiling(round_num: int) -> tuple[float | None, int | None]:
    """Return the largest future top-two priors forecast available today."""
    if not HORIZON_PATH.exists():
        return None, None
    rounds = v13._load_json(HORIZON_PATH).get("rounds", {})
    items = rounds.values() if isinstance(rounds, dict) else rounds
    best_value: float | None = None
    best_round: int | None = None
    for row in items:
        candidate_round = int(row.get("round", 0))
        if candidate_round <= round_num:
            continue
        values = sorted(
            (
                float(driver.get("expected_points", 0.0))
                for driver in row.get("drivers", {}).values()
            ),
            reverse=True,
        )
        if len(values) < 2:
            continue
        total = values[0] + values[1]
        if best_value is None or total > best_value:
            best_value, best_round = total, candidate_round
    return best_value, best_round


def _three_x_decision(
    *,
    round_num: int,
    phase: str,
    round_data: season.RoundInputs,
    normal: season.Candidate,
    public: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    remaining = public["current_state"].get("chips_remaining", [])
    if phase != "post_fp" or "3x_boost" not in remaining:
        return None, {"result": "not_evaluated", "reason": "Only post-FP finals can play 3x."}

    lookup = {key: index for index, key in enumerate(round_data.drivers)}
    selected = sorted(
        (float(round_data.driver_projection[lookup[key]]) for key in normal.drivers),
        reverse=True,
    )
    current_extra = selected[0] + selected[1]
    future_ceiling, future_round = _future_three_x_ceiling(round_num)
    play = future_ceiling is None or current_extra >= future_ceiling
    return (
        "3x_boost" if play else None,
        {
            "result": "play" if play else "save",
            "current_selected_team_extra_points": round(current_extra, 2),
            "largest_remaining_priors_top_two": (
                round(future_ceiling, 2) if future_ceiling is not None else None
            ),
            "largest_remaining_priors_round": future_round,
            "policy": (
                "Play when current post-FP extra 3x value meets or exceeds the "
                "largest remaining priors-only top-two driver forecast."
            ),
        },
    )


def _previous_record() -> tuple[str | None, str | None]:
    if not DECISION_DIR.exists():
        return None, None
    records: list[tuple[int, int, Path]] = []
    pattern = re.compile(r"round(?P<round>\d+)_(?P<phase>pre_fp|post_fp)\.json$")
    for path in DECISION_DIR.glob("round*_*.json"):
        match = pattern.match(path.name)
        if match:
            records.append(
                (
                    int(match.group("round")),
                    PHASE_ORDER[match.group("phase")],
                    path,
                )
            )
    if not records:
        return None, None
    path = max(records)[2]
    value = v13._load_json(path)
    return str(path.relative_to(ROOT)).replace("\\", "/"), _record_sha256(value)


def _decision(
    round_num: int,
    phase: str,
    public: dict[str, Any],
) -> dict[str, Any]:
    round_data = _round_input(round_num, phase)
    state = _state(public)
    combos = season.build_combo_matrices(round_data)
    normal = season.choose_lineup(
        round_data=round_data,
        combos=combos,
        state=state,
        strategy=v13.V13_STRATEGY,
        chip=None,
        risk_profile=v13.V13_RISK_PROFILE,
    )
    chip, chip_decision = _three_x_decision(
        round_num=round_num,
        phase=phase,
        round_data=round_data,
        normal=normal,
        public=public,
    )
    candidate = normal
    if chip:
        candidate = season.choose_lineup(
            round_data=round_data,
            combos=combos,
            state=state,
            strategy=v13.V13_STRATEGY,
            chip=chip,
            risk_profile=v13.V13_RISK_PROFILE,
        )

    archive = ROOT / round_data.archive_path
    archive_payload = v13._load_json(archive)
    previous_path, previous_hash = _previous_record()
    outgoing_drivers = sorted(set(state.drivers) - set(candidate.drivers))
    incoming_drivers = sorted(set(candidate.drivers) - set(state.drivers))
    outgoing_constructors = sorted(set(state.constructors) - set(candidate.constructors))
    incoming_constructors = sorted(set(candidate.constructors) - set(state.constructors))
    price_key, _ = _opening_prices(round_num)
    return {
        "schema_version": 1,
        "manager": "v13",
        "round": round_num,
        "race": round_data.race_name,
        "phase": phase,
        "status": "provisional" if phase == "pre_fp" else "frozen_before_lock",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": archive_payload["generated_at"],
        "lock_deadline": _lock_deadline(round_num),
        "archive": round_data.archive_path,
        "archive_sha256": v13._sha256(archive),
        "previous_decision": previous_path,
        "previous_decision_sha256": previous_hash,
        "price_snapshot_after_round": int(price_key),
        "drivers": list(candidate.drivers),
        "constructors": list(candidate.constructors),
        "captain": candidate.captain,
        "second_boost": candidate.second_captain,
        "chip": chip,
        "projected_points": candidate.projected_points,
        "projected_price_gain": candidate.projected_gain,
        "downside_risk": candidate.downside_risk,
        "team_cost": candidate.cost,
        "transfers": candidate.transfers,
        "transfer_penalty": candidate.transfer_penalty,
        "changes": {
            "drivers_out": outgoing_drivers,
            "drivers_in": incoming_drivers,
            "constructors_out": outgoing_constructors,
            "constructors_in": incoming_constructors,
        },
        "chip_decision": chip_decision,
        "policy": {
            "strategy": v13.V13_STRATEGY,
            "risk_profile": v13.V13_RISK_PROFILE,
            "price_gain_weight": season.BUDGET_BUILDER_PRICE_GAIN_VALUE,
            "negative_p5_weight": season.RISK_PROFILE_WEIGHTS[v13.V13_RISK_PROFILE],
        },
    }


def _sync_public(public: dict[str, Any], decision: dict[str, Any]) -> None:
    if decision["round"] != public["current_state"]["next_round"]:
        raise ValueError(
            f"V13 expects R{public['current_state']['next_round']}, not R{decision['round']}"
        )
    target = "early_thoughts" if decision["phase"] == "pre_fp" else "post_fp_final"
    public["current_state"][target] = decision
    public["generated_at"] = datetime.now().astimezone().isoformat()
    PUBLIC_PATH.write_text(
        json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def publish(round_num: int, phase: str) -> dict[str, Any]:
    if phase not in PHASE_ORDER:
        raise ValueError(f"Unsupported V13 phase: {phase}")
    if not PUBLIC_PATH.exists():
        v13.main()
    public = v13._load_json(PUBLIC_PATH)
    expected_round = int(public["current_state"]["next_round"])
    if round_num != expected_round:
        raise ValueError(f"V13 currently expects R{expected_round}, not R{round_num}")

    path = DECISION_DIR / f"round{round_num}_{phase}.json"
    if path.exists():
        existing = v13._load_json(path)
        current_archive = ROOT / existing["archive"]
        if v13._sha256(current_archive) != existing["archive_sha256"]:
            raise RuntimeError(
                f"{path.name} is frozen but its source archive has changed; investigate"
            )
        _sync_public(public, existing)
        return existing

    if phase == "post_fp" and not (DECISION_DIR / f"round{round_num}_pre_fp.json").exists():
        raise RuntimeError("Publish the pre-FP early-thoughts record first")

    decision = _decision(round_num, phase, public)
    DECISION_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(decision))
    _sync_public(public, decision)
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--phase", choices=tuple(PHASE_ORDER), required=True)
    args = parser.parse_args()
    decision = publish(args.round, args.phase)
    print(
        f"V13 R{decision['round']} {decision['phase']} {decision['status']}: "
        f"{decision['projected_points']:.1f} projected, "
        f"archive {decision['archive_sha256'][:12]}"
    )


if __name__ == "__main__":
    main()
