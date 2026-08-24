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
from config.fantasy_prices import load_fantasy_price_data
from pipeline import build_v13_manager as v13
from pipeline import simulate_fantasy_season_strategies as season


DECISION_DIR = ROOT / "data" / "v13" / "decisions"
PUBLIC_PATH = WEB_DATA_DIR / "v13_manager.json"
HORIZON_PATH = WEB_DATA_DIR / "horizon_projections.json"
APP_JS_PATH = ROOT / "web" / "public" / "app.js"
PHASE_ORDER = {"pre_fp": 0, "post_fp": 1}
R14_CORRECTED_PRE_FP_ARCHIVE = (
    "predictions_round14_pre_fp_availability_corrected.json"
)


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
    # Keep the original frozen phase archive immutable for V13 auditability.
    # An explicit R14 availability correction may publish a separate source
    # snapshot; post-FP refreshes naturally fall back to the normal archive.
    if round_num == 14 and phase == "pre_fp":
        corrected = WEB_DATA_DIR / R14_CORRECTED_PRE_FP_ARCHIVE
        if corrected.exists():
            archive = corrected
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

    # Use the roster actually frozen into the phase archive. This keeps the
    # V13 decision aligned with a pre-FP export even when a seat correction is
    # introduced between phases or an older archive still carries its legacy
    # asset IDs.
    archive_drivers = {row["driver_id"]: row for row in payload["drivers"]}
    archive_constructors = {
        row["constructor_id"]: row for row in payload["constructors"]
    }
    drivers = tuple(archive_drivers)
    constructors = tuple(archive_constructors)
    prices = load_fantasy_price_data(round_num=round_num)
    driver_price_map = prices.get("drivers", {})
    constructor_price_map = prices.get("constructors", {})

    def price(group: dict[str, Any], key: str, fallback: float) -> float:
        entry = group.get(key) or {}
        value = entry.get("current_price") if isinstance(entry, dict) else entry
        return float(value if value is not None else fallback)

    driver_prices = np.array(
        [
            price(
                driver_price_map,
                key,
                float(archive_drivers[key].get("current_price", 0.0)),
            )
            for key in drivers
        ]
    )
    constructor_prices = np.array(
        [
            price(
                constructor_price_map,
                key,
                float(archive_constructors[key].get("current_price", 0.0)),
            )
            for key in constructors
        ]
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


def _state_for_round(payload: dict[str, Any], round_num: int) -> season.TeamState:
    """Return the genuine held team without inheriting replacement seats.

    If a held driver is absent from the active round roster, the optimizer's
    transfer counter treats that asset as a mandatory outgoing transfer. A
    new driver in the same physical seat is still a distinct Fantasy asset.
    """
    return _state(payload)


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
    records: list[tuple[int, int, int, Path]] = []
    pattern = re.compile(
        r"round(?P<round>\d+)_(?P<phase>pre_fp|post_fp)"
        r"(?:_revision(?P<revision>\d+))?\.json$"
    )
    for path in DECISION_DIR.glob("round*_*.json"):
        match = pattern.match(path.name)
        if match:
            records.append(
                (
                    int(match.group("round")),
                    PHASE_ORDER[match.group("phase")],
                    int(match.group("revision") or 1),
                    path,
                )
            )
    if not records:
        return None, None
    path = max(records)[3]
    value = v13._load_json(path)
    return str(path.relative_to(ROOT)).replace("\\", "/"), _record_sha256(value)


def _decision(
    round_num: int,
    phase: str,
    public: dict[str, Any],
) -> dict[str, Any]:
    round_data = _round_input(round_num, phase)
    state = _state_for_round(public, round_num)
    combos = season.build_combo_matrices(round_data)
    normal = season.choose_lineup(
        round_data=round_data,
        combos=combos,
        state=state,
        strategy=v13.V13_STRATEGY,
        chip=None,
        risk_profile=v13.V13_RISK_PROFILE,
        price_gain_value=v13.live_price_gain_value(round_num),
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
            price_gain_value=v13.live_price_gain_value(round_num),
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
        "policy": v13.live_policy(round_num),
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
    # Rebuild the public record first so an official post-race update rolls
    # V13's held team and budget into the next round before a new decision is
    # frozen. This is what keeps the Beat V13 page moving with the weekend
    # pipeline instead of relying on a manual refresh.
    v13.main()
    public = v13._load_json(PUBLIC_PATH)

    path = DECISION_DIR / f"round{round_num}_{phase}.json"
    if path.exists():
        existing = v13._load_json(path)
        current_archive = ROOT / existing["archive"]
        if v13._sha256(current_archive) != existing["archive_sha256"]:
            raise RuntimeError(
                f"{path.name} is frozen but its source archive has changed; investigate"
            )
        revisions = sorted(
            DECISION_DIR.glob(f"round{round_num}_{phase}_revision*.json"),
            key=lambda item: int(item.stem.rsplit("revision", 1)[1]),
        )
        active = v13._load_json(revisions[-1]) if revisions else existing
        # Older frozen decisions remain valid audit records after the public
        # state has advanced to a later round. They must stay idempotent and
        # must not rewind the live page.
        if int(public["current_state"]["next_round"]) == round_num:
            _sync_public(public, active)
        return active

    expected_round = int(public["current_state"]["next_round"])
    if round_num != expected_round:
        raise ValueError(f"V13 currently expects R{expected_round}, not R{round_num}")

    if phase == "post_fp" and not (DECISION_DIR / f"round{round_num}_pre_fp.json").exists():
        raise RuntimeError("Publish the pre-FP early-thoughts record first")

    decision = _decision(round_num, phase, public)
    DECISION_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(decision))
    _sync_public(public, decision)
    return decision


def publish_correction(round_num: int, phase: str, reason: str) -> dict[str, Any]:
    """Append an explicit audited correction without rewriting the original."""
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("A correction reason is required")
    base_path = DECISION_DIR / f"round{round_num}_{phase}.json"
    if not base_path.exists():
        raise FileNotFoundError("Publish the original decision before a correction")

    public = v13.build_payload()
    revisions = sorted(
        DECISION_DIR.glob(f"round{round_num}_{phase}_revision*.json"),
        key=lambda path: int(path.stem.rsplit("revision", 1)[1]),
    )
    if revisions:
        latest = v13._load_json(revisions[-1])
        if latest.get("correction_reason") == reason:
            _sync_public(public, latest)
            return latest

    superseded_path = revisions[-1] if revisions else base_path
    superseded = v13._load_json(superseded_path)
    revision = int(superseded.get("revision", 1)) + 1
    decision = _decision(round_num, phase, public)
    decision.update(
        {
            "revision": revision,
            "status": "corrected_provisional" if phase == "pre_fp" else "corrected_before_lock",
            "correction_reason": reason,
            "supersedes": str(superseded_path.relative_to(ROOT)).replace("\\", "/"),
            "supersedes_sha256": _record_sha256(superseded),
        }
    )
    path = DECISION_DIR / f"round{round_num}_{phase}_revision{revision}.json"
    path.write_bytes(_canonical_bytes(decision))
    _sync_public(public, decision)
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--phase", choices=tuple(PHASE_ORDER), required=True)
    parser.add_argument(
        "--correction-reason",
        help="Append an audited revision instead of rewriting the original decision.",
    )
    args = parser.parse_args()
    decision = (
        publish_correction(args.round, args.phase, args.correction_reason)
        if args.correction_reason
        else publish(args.round, args.phase)
    )
    print(
        f"V13 R{decision['round']} {decision['phase']} {decision['status']}: "
        f"{decision['projected_points']:.1f} projected, "
        f"archive {decision['archive_sha256'][:12]}"
    )


if __name__ == "__main__":
    main()
