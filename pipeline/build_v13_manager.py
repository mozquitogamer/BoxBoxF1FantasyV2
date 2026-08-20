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
from pipeline import simulate_fantasy_season_strategies as season


EXPERIMENT_PATH = (
    ROOT / "data" / "experiments" / "season_risk_tolerance_with_chips_2026.json"
)
OUTPUT_PATH = WEB_DATA_DIR / "v13_manager.json"
DECISION_DIR = ROOT / "data" / "v13" / "decisions"
V13_STRATEGY = "budget_builder"
V13_RISK_PROFILE = "medium_tolerance"
FINAL_FIX_MIN_PROJECTED_GAIN = 0.1


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


def _official_driver_points(
    official: dict[str, Any], round_num: int, asset_id: str
) -> float:
    """Resolve an active seat ID to its historical official points key."""
    rows = official[str(round_num)]["drivers"]
    if asset_id in rows:
        return float(rows[asset_id])
    for asset in active_driver_assets(14):
        if asset["asset_id"] != asset_id:
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


def _candidate_payload(candidate: season.Candidate, phase_row: season.RoundInputs) -> dict[str, Any]:
    archive = ROOT / phase_row.archive_path
    return {
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
    }


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
    base_rounds = season.load_rounds()
    final_rows = manager["rounds"]
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

    final_drivers = list(manager["summary"]["final_drivers"])
    final_bank = float(manager["summary"]["final_bank"])
    if final_fix:
        final_drivers[final_drivers.index(final_fix["outgoing"])] = final_fix["incoming"]
        final_bank = float(final_fix["bank_after"])

    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "manager": {
            "id": "v13",
            "name": "V13",
            "tagline": "Budget-aware. Medium-risk. Transparent at every decision.",
            "strategy": V13_STRATEGY,
            "risk_profile": V13_RISK_PROFILE,
            "policy_version": "2026.2",
            "policy": {
                "team_selection_phase": "post_fp",
                "early_thoughts_phase": "pre_fp",
                "price_gain_weight": season.BUDGET_BUILDER_PRICE_GAIN_VALUE,
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
            "final_bank": round(final_bank, 1),
            "genuine_archive_points_before_final_fix": manager["summary"][
                "genuine_archive_points"
            ],
            "rounds": rounds,
        },
        "current_state": {
            "as_of_round": 13,
            "drivers": final_drivers,
            "constructors": manager["summary"]["final_constructors"],
            "budget": manager["summary"]["final_budget"],
            "bank": round(final_bank, 1),
            "free_transfers": final_rows[-1]["free_transfers_next"],
            "chips_remaining": ["3x_boost"],
            "chips_used": {
                **{
                    chip: int(round_num)
                    for round_num, chip in manager.get("chip_schedule", {}).items()
                },
                "final_fix": final_fix["round"] if final_fix else None,
            },
            "next_round": 14,
            "early_thoughts": _live_decision(14, "pre_fp"),
            "post_fp_final": _live_decision(14, "post_fp"),
        },
        "labels": {
            "drivers": driver_names,
            "constructors": constructor_names,
        },
        "source": {
            "experiment": str(EXPERIMENT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "experiment_sha256": _sha256(EXPERIMENT_PATH),
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
