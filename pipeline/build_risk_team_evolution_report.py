"""Build team-evolution and transfer-reason reports for the risk experiment."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import simulate_fantasy_risk_profiles as risk
from pipeline import simulate_fantasy_season_strategies as season


DEFAULT_INPUT = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_with_chips_2026.json"
)
DEFAULT_JSON = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_with_chips_team_evolution_2026.json"
)
DEFAULT_MARKDOWN = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_with_chips_team_evolution_2026.md"
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _labels() -> tuple[dict[str, str], dict[str, str]]:
    drivers = _load_json(season.SEED_DIR / "drivers.json")["drivers"]
    constructors = _load_json(
        season.SEED_DIR / "constructors.json"
    )["constructors"]
    driver_labels = {
        row["driver_id"]: f"{row['driver_id']} ({row['first_name']} {row['last_name']})"
        for row in drivers
    }
    constructor_labels = {
        row["constructor_id"]: row["name"] for row in constructors
    }
    return driver_labels, constructor_labels


def _asset_metrics(
    round_data: season.RoundInputs,
    asset_type: str,
    asset_id: str,
) -> dict[str, float | str]:
    if asset_type == "driver":
        index = round_data.drivers.index(asset_id)
        projection = float(round_data.driver_projection[index])
        p5 = float(round_data.driver_p5[index])
        price = float(round_data.driver_prices[index])
        price_gain = float(round_data.driver_projected_gain[index])
    else:
        index = round_data.constructors.index(asset_id)
        projection = float(round_data.constructor_projection[index])
        p5 = float(round_data.constructor_p5[index])
        price = float(round_data.constructor_prices[index])
        price_gain = float(round_data.constructor_projected_gain[index])
    return {
        "asset_id": asset_id,
        "projected_points": round(projection, 2),
        "p5_points": round(p5, 2),
        "negative_p5_exposure": round(max(-p5, 0.0), 2),
        "price": round(price, 1),
        "projected_price_change": round(price_gain, 1),
    }


def _strategy_utility(
    metrics: dict[str, float | str],
    strategy: str,
    risk_profile: str,
) -> float | None:
    if risk_profile == season.TOTAL_RISK_AVOIDANCE:
        return None
    risk_weight = season.RISK_PROFILE_WEIGHTS[risk_profile]
    price_weight = season.strategy_price_gain_value(strategy)
    return round(
        float(metrics["projected_points"])
        + price_weight * float(metrics["projected_price_change"])
        - risk_weight * float(metrics["negative_p5_exposure"]),
        3,
    )


def _pair_changes(
    outgoing: list[str],
    incoming: list[str],
    *,
    round_data: season.RoundInputs,
    asset_type: str,
) -> list[tuple[str, str]]:
    """Pair swaps by current price proximity for readable explanations."""
    if not outgoing:
        return []
    best: tuple[float, tuple[str, ...]] | None = None
    for ordering in itertools.permutations(incoming):
        distance = 0.0
        for old_id, new_id in zip(outgoing, ordering):
            old = _asset_metrics(round_data, asset_type, old_id)
            new = _asset_metrics(round_data, asset_type, new_id)
            distance += abs(float(old["price"]) - float(new["price"]))
        if best is None or distance < best[0]:
            best = (distance, ordering)
    assert best is not None
    return list(zip(outgoing, best[1]))


def _transfer_reason(
    *,
    old: dict[str, float | str],
    new: dict[str, float | str],
    strategy: str,
    risk_profile: str,
    chip: str | None,
    became_captain: bool,
    wildcard_reason: str | None,
) -> tuple[str, dict[str, float | None]]:
    projection_delta = round(
        float(new["projected_points"]) - float(old["projected_points"]), 2
    )
    gain_delta = round(
        float(new["projected_price_change"])
        - float(old["projected_price_change"]),
        2,
    )
    downside_delta = round(
        float(new["negative_p5_exposure"])
        - float(old["negative_p5_exposure"]),
        2,
    )
    price_delta = round(float(new["price"]) - float(old["price"]), 1)
    old_utility = _strategy_utility(old, strategy, risk_profile)
    new_utility = _strategy_utility(new, strategy, risk_profile)
    utility_delta = (
        round(float(new_utility) - float(old_utility), 2)
        if old_utility is not None and new_utility is not None
        else None
    )

    parts = []
    if chip == "wild_card":
        parts.append("Wild Card made the permanent rebuild free")
    if wildcard_reason:
        parts.append(wildcard_reason)

    if risk_profile == season.TOTAL_RISK_AVOIDANCE:
        if downside_delta < 0:
            parts.append(
                f"cut negative-P5 exposure by {abs(downside_delta):.1f}, "
                "the profile's first priority"
            )
        elif downside_delta > 0:
            parts.append(
                f"accepted {downside_delta:.1f} more negative-P5 exposure only "
                "as part of the safest feasible full lineup"
            )
        else:
            parts.append("preserved the minimum feasible negative-P5 exposure")
    else:
        if utility_delta is not None:
            if utility_delta >= 0:
                parts.append(
                    "raised approximate per-asset strategy/risk utility by "
                    f"{utility_delta:+.1f}"
                )
            else:
                parts.append(
                    "was "
                    f"{utility_delta:.1f} utility on this explanatory pairing "
                    "but enabled the higher-utility seven-asset lineup"
                )

    if projection_delta >= 0:
        parts.append(f"projection {projection_delta:+.1f} pts")
    else:
        parts.append(f"gave up {abs(projection_delta):.1f} projected pts")
    if gain_delta:
        parts.append(f"forecast price change {gain_delta:+.1f}M")
    if downside_delta:
        parts.append(f"negative-P5 exposure {downside_delta:+.1f}")
    if price_delta < 0:
        parts.append(f"released ${abs(price_delta):.1f}M")
    elif price_delta > 0:
        parts.append(f"spent ${price_delta:.1f}M more")
    if became_captain:
        parts.append("became the projected 2x captain")

    return "; ".join(parts) + ".", {
        "projection_delta": projection_delta,
        "projected_price_change_delta": gain_delta,
        "negative_p5_exposure_delta": downside_delta,
        "price_delta": price_delta,
        "approximate_utility_delta": utility_delta,
    }


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    rounds = season.load_rounds()
    round_lookup = {round_data.round_num: round_data for round_data in rounds}
    driver_labels, constructor_labels = _labels()
    evolution = []
    ledger = []

    for manager in payload["managers"]:
        previous_drivers: tuple[str, ...] = ()
        previous_constructors: tuple[str, ...] = ()
        previous_captain: str | None = None
        rationale = manager.get("chip_rationale", {})

        for row in manager["rounds"]:
            round_num = int(row["round"])
            round_data = round_lookup[round_num]
            chip = row["chip"]
            persistent_drivers = tuple(row["persistent_drivers"])
            persistent_constructors = tuple(row["persistent_constructors"])

            if not previous_drivers:
                outgoing_drivers: list[str] = []
                incoming_drivers = list(persistent_drivers)
                outgoing_constructors: list[str] = []
                incoming_constructors = list(persistent_constructors)
                change_type = "Initial selection"
            elif chip == "limitless":
                outgoing_drivers = []
                incoming_drivers = []
                outgoing_constructors = []
                incoming_constructors = []
                change_type = "Temporary Limitless lineup; owned team reverted"
            else:
                outgoing_drivers = sorted(
                    set(previous_drivers) - set(persistent_drivers)
                )
                incoming_drivers = sorted(
                    set(persistent_drivers) - set(previous_drivers)
                )
                outgoing_constructors = sorted(
                    set(previous_constructors) - set(persistent_constructors)
                )
                incoming_constructors = sorted(
                    set(persistent_constructors) - set(previous_constructors)
                )
                change_type = (
                    "Hold"
                    if not outgoing_drivers and not outgoing_constructors
                    else "Permanent transfers"
                )

            transfer_descriptions = []
            wildcard_reason = (
                rationale.get("wild_card", {}).get("reason")
                if chip == "wild_card"
                else None
            )
            if not previous_drivers:
                transfer_descriptions.append(
                    "Initial team selected by the manager philosophy and risk "
                    "profile under the $100.0M cap."
                )
            elif chip == "limitless":
                temporary_driver_adds = sorted(
                    set(row["drivers"]) - set(previous_drivers)
                )
                temporary_constructor_adds = sorted(
                    set(row["constructors"]) - set(previous_constructors)
                )
                chip_reason = rationale.get("limitless", {}).get("reason", "")
                transfer_descriptions.append(
                    "Limitless temporarily added "
                    + ", ".join(
                        [
                            *(
                                driver_labels.get(asset_id, asset_id)
                                for asset_id in temporary_driver_adds
                            ),
                            *(
                                constructor_labels.get(asset_id, asset_id)
                                for asset_id in temporary_constructor_adds
                            ),
                        ]
                    )
                    + f". {chip_reason} The owned team reverted after the round."
                )
            else:
                for asset_type, outgoing, incoming, labels in (
                    (
                        "driver",
                        outgoing_drivers,
                        incoming_drivers,
                        driver_labels,
                    ),
                    (
                        "constructor",
                        outgoing_constructors,
                        incoming_constructors,
                        constructor_labels,
                    ),
                ):
                    for old_id, new_id in _pair_changes(
                        outgoing,
                        incoming,
                        round_data=round_data,
                        asset_type=asset_type,
                    ):
                        old = _asset_metrics(round_data, asset_type, old_id)
                        new = _asset_metrics(round_data, asset_type, new_id)
                        reason, deltas = _transfer_reason(
                            old=old,
                            new=new,
                            strategy=manager["strategy"],
                            risk_profile=manager["risk_profile"],
                            chip=chip,
                            became_captain=(
                                new_id == row["captain"]
                                and new_id != previous_captain
                            ),
                            wildcard_reason=wildcard_reason,
                        )
                        description = (
                            f"{labels.get(old_id, old_id)} → "
                            f"{labels.get(new_id, new_id)}: {reason}"
                        )
                        transfer_descriptions.append(description)
                        ledger.append(
                            {
                                "strategy": manager["strategy"],
                                "risk_profile": manager["risk_profile"],
                                "round": round_num,
                                "race": row["race"],
                                "archive_quality": (
                                    "reconstructed"
                                    if row["archive_reconstructed"]
                                    else "genuine"
                                ),
                                "chip": chip,
                                "asset_type": asset_type,
                                "outgoing": old,
                                "incoming": new,
                                **deltas,
                                "transfer_penalty_for_lineup": row[
                                    "transfer_penalty"
                                ],
                                "reason": reason,
                            }
                        )
                if not transfer_descriptions:
                    transfer_descriptions.append(
                        "Held the existing team because no permitted transfer "
                        "improved the manager's lineup-level objective enough "
                        "after transfer penalties."
                    )

            chip_reason = (
                rationale.get(chip, {}).get("reason") if chip else None
            )
            if chip_reason and chip != "wild_card" and chip != "limitless":
                transfer_descriptions.append(
                    f"{chip.replace('_', ' ').title()}: {chip_reason}"
                )

            changes = [
                *(
                    f"{driver_labels.get(old_id, old_id)} → "
                    f"{driver_labels.get(new_id, new_id)}"
                    for old_id, new_id in _pair_changes(
                        outgoing_drivers,
                        incoming_drivers,
                        round_data=round_data,
                        asset_type="driver",
                    )
                ),
                *(
                    f"{constructor_labels.get(old_id, old_id)} → "
                    f"{constructor_labels.get(new_id, new_id)}"
                    for old_id, new_id in _pair_changes(
                        outgoing_constructors,
                        incoming_constructors,
                        round_data=round_data,
                        asset_type="constructor",
                    )
                ),
            ]
            evolution.append(
                {
                    "strategy": manager["strategy"],
                    "strategy_label": risk.MANAGER_LABELS[
                        manager["strategy"]
                    ],
                    "risk_profile": manager["risk_profile"],
                    "risk_label": risk.RISK_LABELS[
                        manager["risk_profile"]
                    ],
                    "round": round_num,
                    "race": row["race"],
                    "archive_quality": (
                        "reconstructed"
                        if row["archive_reconstructed"]
                        else "genuine"
                    ),
                    "chip": chip,
                    "change_type": change_type,
                    "drivers": [
                        driver_labels.get(asset_id, asset_id)
                        for asset_id in row["drivers"]
                    ],
                    "constructors": [
                        constructor_labels.get(asset_id, asset_id)
                        for asset_id in row["constructors"]
                    ],
                    "persistent_drivers": [
                        driver_labels.get(asset_id, asset_id)
                        for asset_id in persistent_drivers
                    ],
                    "persistent_constructors": [
                        constructor_labels.get(asset_id, asset_id)
                        for asset_id in persistent_constructors
                    ],
                    "captain": driver_labels.get(
                        row["captain"], row["captain"]
                    ),
                    "transfers": row["transfers"],
                    "free_transfers_before": row["free_transfers_before"],
                    "transfer_penalty": row["transfer_penalty"],
                    "budget_before": row["budget_before"],
                    "played_team_cost": row["played_team_cost"],
                    "budget_after": row["budget_after"],
                    "projected_points": row["projected_points"],
                    "projected_price_gain": row["projected_price_gain"],
                    "forecast_downside": row["downside_risk"],
                    "actual_points": row["actual_points_net"],
                    "changes": changes,
                    "reasons": transfer_descriptions,
                }
            )
            previous_drivers = persistent_drivers
            previous_constructors = persistent_constructors
            previous_captain = row["captain"]

    return {
        "schema_version": 1,
        "source": str(DEFAULT_INPUT.relative_to(ROOT)).replace("\\", "/"),
        "pairing_note": (
            "When several assets changed together, outgoing and incoming assets "
            "are paired by current-price proximity for readability. The optimizer "
            "selects the seven-asset lineup jointly, so the lineup-level decision "
            "is authoritative rather than any single one-for-one pairing."
        ),
        "reason_method": (
            "Reasons compare archived projected points, forecast price change, "
            "negative-P5 exposure, price, risk penalty, manager price-growth "
            "weight, captain status, chip context, and transfer penalty."
        ),
        "evolution": evolution,
        "transfer_ledger": ledger,
    }


def _short_assets(values: list[str]) -> str:
    return ", ".join(value.split(" (", 1)[0] for value in values)


def build_markdown(
    source: dict[str, Any],
    report: dict[str, Any],
) -> str:
    lines = [
        "# 2026 chip-enabled risk experiment: team evolution",
        "",
        (
            "This report shows every weekend for all three manager philosophies "
            "and four risk profiles, including the played lineup, persistent team "
            "changes, and the archived evidence behind each transfer."
        ),
        "",
        f"- {report['pairing_note']}",
        f"- {report['reason_method']}",
        "- 3x Boost remained saved.",
        "",
        "## Manager summary",
        "",
        "| Manager | Risk profile | Points | Genuine points | Final budget | Transfers | Penalties | Chips |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for manager in source["managers"]:
        summary = manager["summary"]
        schedule = ", ".join(
            f"R{round_num} {chip.replace('_', ' ').title()}"
            for round_num, chip in manager["chip_schedule"].items()
        )
        lines.append(
            f"| {risk.MANAGER_LABELS[manager['strategy']]} | "
            f"{risk.RISK_LABELS[manager['risk_profile']]} | "
            f"{summary['season_points']:.0f} | "
            f"{summary['genuine_archive_points']:.0f} | "
            f"${summary['final_budget']:.1f}M | "
            f"{summary['transfers']} | "
            f"{summary['transfer_penalties']} | "
            f"{schedule or 'None'} |"
        )

    for manager in source["managers"]:
        strategy = manager["strategy"]
        risk_profile = manager["risk_profile"]
        rows = [
            row
            for row in report["evolution"]
            if row["strategy"] == strategy
            and row["risk_profile"] == risk_profile
        ]
        lines.extend(
            [
                "",
                (
                    f"## {risk.MANAGER_LABELS[strategy]} — "
                    f"{risk.RISK_LABELS[risk_profile]}"
                ),
                "",
                "| Round | Weekend | Chip | Budget | Drivers | Constructors | Changes | Why | Actual |",
                "|---:|---|---|---:|---|---|---|---|---:|",
            ]
        )
        for row in rows:
            chip = (
                row["chip"].replace("_", " ").title()
                if row["chip"]
                else "—"
            )
            changes = (
                "<br>".join(row["changes"])
                if row["changes"]
                else row["change_type"]
            )
            reasons = "<br>".join(row["reasons"])
            archive_marker = "*" if row["archive_quality"] == "reconstructed" else ""
            lines.append(
                f"| {row['round']}{archive_marker} | {row['race']} | {chip} | "
                f"${row['budget_before']:.1f}M → ${row['budget_after']:.1f}M | "
                f"{_short_assets(row['drivers'])} | "
                f"{_short_assets(row['constructors'])} | "
                f"{changes} | {reasons} | {row['actual_points']:.0f} |"
            )

    lines.extend(
        [
            "",
            "*Rounds marked with an asterisk use reconstructed prediction archives.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument(
        "--output-markdown", type=Path, default=DEFAULT_MARKDOWN
    )
    args = parser.parse_args()

    source = _load_json(args.input)
    report = build_report(source)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    args.output_markdown.write_text(
        build_markdown(source, report), encoding="utf-8"
    )
    print(f"Evolution rows: {len(report['evolution'])}")
    print(f"Transfer pairs: {len(report['transfer_ledger'])}")
    print(f"JSON -> {args.output_json}")
    print(f"Report -> {args.output_markdown}")


if __name__ == "__main__":
    main()
