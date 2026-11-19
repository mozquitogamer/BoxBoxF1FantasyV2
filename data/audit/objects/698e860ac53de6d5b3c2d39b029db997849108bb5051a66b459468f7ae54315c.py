"""Replay the 2026 season across manager philosophies and risk profiles.

The experiment holds the data, transfer rules, starting budget, and chip usage
constant.  It varies:

* Manager philosophy: max points, balanced, or budget builder.
* Risk profile: total avoidance, minimal risk accepted, medium tolerance, or
  maximum tolerance.

Risk is the combined magnitude of negative P5 asset outcomes in the archived
Monte Carlo forecast.  This directly targets the bad-weekend tail rather than
penalising ordinary projection uncertainty.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import simulate_fantasy_season_strategies as season


DEFAULT_JSON = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_experiment_2026.json"
)
DEFAULT_MARKDOWN = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_experiment_2026.md"
)
DEFAULT_CHIP_JSON = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_with_chips_2026.json"
)
DEFAULT_CHIP_MARKDOWN = (
    ROOT
    / "data"
    / "experiments"
    / "season_risk_tolerance_with_chips_2026.md"
)

MANAGERS = ("max_points", "balanced", "budget_builder")
RISK_PROFILES = (
    "total_avoidance",
    "minimal_risk_accepted",
    "medium_tolerance",
    "maximum_tolerance",
)
MANAGER_LABELS = {
    "max_points": "Max Points",
    "balanced": "Balanced",
    "budget_builder": "Budget Builder",
}
RISK_LABELS = {
    "total_avoidance": "Total avoidance",
    "minimal_risk_accepted": "Minimal risk accepted",
    "medium_tolerance": "Medium tolerance",
    "maximum_tolerance": "Maximum tolerance",
}


def _realized_risk_metrics(
    manager: dict[str, Any],
    round_lookup: dict[int, season.RoundInputs],
) -> dict[str, Any]:
    negative_asset_hits = 0
    negative_points = 0.0
    rounds_with_negative_assets = 0
    genuine_points = 0.0
    genuine_negative_points = 0.0
    round_scores = []
    genuine_round_scores = []
    genuine_forecast_downside = []

    for row in manager["rounds"]:
        round_data = round_lookup[int(row["round"])]
        driver_lookup = {
            driver_id: float(round_data.driver_actual[index])
            for index, driver_id in enumerate(round_data.drivers)
        }
        constructor_lookup = {
            constructor_id: float(round_data.constructor_actual[index])
            for index, constructor_id in enumerate(round_data.constructors)
        }
        scores = [
            *(driver_lookup[driver_id] for driver_id in row["drivers"]),
            *(
                constructor_lookup[constructor_id]
                for constructor_id in row["constructors"]
            ),
        ]
        # The standard 2x captain repeats a negative result in the realised
        # downside, just as it repeats that result in official scoring.
        captain_score = driver_lookup[row["captain"]]
        if captain_score < 0:
            scores.append(captain_score)
        if row["chip"] == "no_negative":
            scores = [max(0.0, value) for value in scores]

        round_negative = sum(value for value in scores if value < 0)
        round_hits = sum(value < 0 for value in scores)
        if round_hits:
            rounds_with_negative_assets += 1
        negative_asset_hits += round_hits
        negative_points += round_negative
        round_scores.append(float(row["actual_points_net"]))
        if not row["archive_reconstructed"]:
            genuine_points += float(row["actual_points_net"])
            genuine_negative_points += round_negative
            genuine_round_scores.append(float(row["actual_points_net"]))
            genuine_forecast_downside.append(float(row["downside_risk"]))

    forecast_downside = [
        float(row["downside_risk"]) for row in manager["rounds"]
    ]
    result = {
        "mean_forecast_negative_p5_exposure": round(
            statistics.mean(forecast_downside), 2
        ),
        "max_forecast_negative_p5_exposure": round(
            max(forecast_downside), 2
        ),
        "total_forecast_negative_p5_exposure": round(
            sum(forecast_downside), 2
        ),
        "realized_negative_points": round(negative_points, 1),
        "negative_asset_hits": negative_asset_hits,
        "rounds_with_negative_assets": rounds_with_negative_assets,
        "worst_round_points": round(min(round_scores), 1),
        "round_points_std": round(statistics.pstdev(round_scores), 2),
        "genuine_archive_points": round(genuine_points, 1),
        "genuine_mean_forecast_negative_p5_exposure": round(
            statistics.mean(genuine_forecast_downside), 2
        ),
        "genuine_archive_negative_points": round(
            genuine_negative_points, 1
        ),
        "genuine_worst_round_points": round(
            min(genuine_round_scores), 1
        ),
    }
    return result


def run_experiment(
    *,
    with_chips: bool = False,
    saved_chips: tuple[str, ...] = ("3x_boost",),
) -> dict[str, Any]:
    rounds = season.load_rounds()
    round_lookup = {round_data.round_num: round_data for round_data in rounds}
    managers = []
    for strategy in MANAGERS:
        for risk_profile in RISK_PROFILES:
            baseline = season.simulate(
                rounds,
                strategy=strategy,
                chip_schedule={},
                risk_profile=risk_profile,
            )
            baseline["summary"].update(
                _realized_risk_metrics(baseline, round_lookup)
            )
            if with_chips:
                schedule, rationale = season.choose_chip_schedule_v2(
                    rounds,
                    strategy=strategy,
                    baseline=baseline,
                    risk_profile=risk_profile,
                )
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
                            "Explicitly saved for a future round; no replacement "
                            "chip was assigned to its former round."
                        ),
                    }
                manager = season.simulate(
                    rounds,
                    strategy=strategy,
                    chip_schedule=schedule,
                    risk_profile=risk_profile,
                )
                manager["chip_rationale"] = rationale
            else:
                manager = baseline
            manager["summary"].update(
                _realized_risk_metrics(manager, round_lookup)
            )
            if with_chips:
                attribution = {}
                for round_num, chip in sorted(schedule.items()):
                    without_chip = dict(schedule)
                    del without_chip[round_num]
                    counterfactual = season.simulate(
                        rounds,
                        strategy=strategy,
                        chip_schedule=without_chip,
                        risk_profile=risk_profile,
                    )
                    counterfactual["summary"].update(
                        _realized_risk_metrics(counterfactual, round_lookup)
                    )
                    attribution[chip] = {
                        "round": round_num,
                        "season_points_delta": round(
                            manager["summary"]["season_points"]
                            - counterfactual["summary"]["season_points"],
                            1,
                        ),
                        "genuine_points_delta": round(
                            manager["summary"]["genuine_archive_points"]
                            - counterfactual["summary"][
                                "genuine_archive_points"
                            ],
                            1,
                        ),
                        "final_budget_delta": round(
                            manager["summary"]["final_budget"]
                            - counterfactual["summary"]["final_budget"],
                            1,
                        ),
                    }
                manager["chip_attribution"] = attribution
            manager["no_chip_baseline"] = baseline["summary"]
            managers.append(manager)

    comparisons = []
    for strategy in MANAGERS:
        group = [
            manager for manager in managers
            if manager["strategy"] == strategy
        ]
        reference = next(
            manager
            for manager in group
            if manager["risk_profile"] == "maximum_tolerance"
        )
        for manager in group:
            summary = manager["summary"]
            reference_summary = reference["summary"]
            comparisons.append(
                {
                    "strategy": strategy,
                    "risk_profile": manager["risk_profile"],
                    "season_points": summary["season_points"],
                    "points_vs_no_chips": round(
                        summary["season_points"]
                        - float(manager["no_chip_baseline"]["season_points"]),
                        1,
                    ),
                    "points_vs_maximum_tolerance": round(
                        summary["season_points"]
                        - reference_summary["season_points"],
                        1,
                    ),
                    "final_budget": summary["final_budget"],
                    "budget_vs_no_chips": round(
                        summary["final_budget"]
                        - float(manager["no_chip_baseline"]["final_budget"]),
                        1,
                    ),
                    "budget_vs_maximum_tolerance": round(
                        summary["final_budget"]
                        - reference_summary["final_budget"],
                        1,
                    ),
                    "mean_forecast_negative_p5_exposure": summary[
                        "mean_forecast_negative_p5_exposure"
                    ],
                    "genuine_archive_points": summary[
                        "genuine_archive_points"
                    ],
                    "genuine_points_vs_no_chips": round(
                        summary["genuine_archive_points"]
                        - float(
                            manager["no_chip_baseline"][
                                "genuine_archive_points"
                            ]
                        ),
                        1,
                    ),
                    "genuine_points_vs_maximum_tolerance": round(
                        summary["genuine_archive_points"]
                        - reference_summary["genuine_archive_points"],
                        1,
                    ),
                    "genuine_mean_forecast_negative_p5_exposure": summary[
                        "genuine_mean_forecast_negative_p5_exposure"
                    ],
                    "realized_negative_points": summary[
                        "realized_negative_points"
                    ],
                    "genuine_archive_negative_points": summary[
                        "genuine_archive_negative_points"
                    ],
                    "negative_asset_hits": summary["negative_asset_hits"],
                    "worst_round_points": summary["worst_round_points"],
                    "round_points_std": summary["round_points_std"],
                    "transfers": summary["transfers"],
                    "transfer_penalties": summary["transfer_penalties"],
                }
            )

    best_points = max(
        comparisons, key=lambda row: float(row["season_points"])
    )
    best_budget = max(
        comparisons, key=lambda row: float(row["final_budget"])
    )
    best_genuine_points = max(
        comparisons, key=lambda row: float(row["genuine_archive_points"])
    )
    lowest_forecast_risk = min(
        comparisons,
        key=lambda row: float(row["mean_forecast_negative_p5_exposure"]),
    )
    forecast_risk = np.array(
        [
            float(row["mean_forecast_negative_p5_exposure"])
            for row in comparisons
        ]
    )
    realized_negative_magnitude = np.array(
        [-float(row["realized_negative_points"]) for row in comparisons]
    )
    season_points = np.array(
        [float(row["season_points"]) for row in comparisons]
    )
    genuine_forecast_risk = np.array(
        [
            float(row["genuine_mean_forecast_negative_p5_exposure"])
            for row in comparisons
        ]
    )
    genuine_negative_magnitude = np.array(
        [
            -float(row["genuine_archive_negative_points"])
            for row in comparisons
        ]
    )
    genuine_points = np.array(
        [float(row["genuine_archive_points"]) for row in comparisons]
    )
    risk_diagnostics = {
        "forecast_vs_realized_negative_magnitude_pearson": round(
            float(np.corrcoef(forecast_risk, realized_negative_magnitude)[0, 1]),
            3,
        ),
        "forecast_risk_vs_season_points_pearson": round(
            float(np.corrcoef(forecast_risk, season_points)[0, 1]), 3
        ),
        "genuine_forecast_vs_realized_negative_magnitude_pearson": round(
            float(
                np.corrcoef(
                    genuine_forecast_risk, genuine_negative_magnitude
                )[0, 1]
            ),
            3,
        ),
        "genuine_forecast_risk_vs_points_pearson": round(
            float(np.corrcoef(genuine_forecast_risk, genuine_points)[0, 1]),
            3,
        ),
        "warning": (
            "Descriptive only: the 12 paths share rounds and many assets, so "
            "they are not independent observations."
        ),
    }
    chip_effect_summary = {}
    if with_chips:
        for chip in ("limitless", "wild_card", "no_negative", "autopilot"):
            effects = [
                {
                    "strategy": manager["strategy"],
                    "risk_profile": manager["risk_profile"],
                    **manager["chip_attribution"][chip],
                }
                for manager in managers
                if chip in manager["chip_attribution"]
            ]
            point_deltas = np.array(
                [float(row["season_points_delta"]) for row in effects]
            )
            chip_effect_summary[chip] = {
                "paths_played": len(effects),
                "positive_return_share": round(
                    float(np.mean(point_deltas > 0)), 3
                ),
                "mean_season_points_delta": round(
                    float(np.mean(point_deltas)), 2
                ),
                "median_season_points_delta": round(
                    float(np.median(point_deltas)), 2
                ),
                "minimum_season_points_delta": round(
                    float(np.min(point_deltas)), 2
                ),
                "maximum_season_points_delta": round(
                    float(np.max(point_deltas)), 2
                ),
                "mean_final_budget_delta": round(
                    float(
                        np.mean(
                            [
                                float(row["final_budget_delta"])
                                for row in effects
                            ]
                        )
                    ),
                    3,
                ),
                "effects": effects,
            }
    result = {
        "schema_version": 1,
        "season": season.CURRENT_SEASON,
        "starting_budget": season.STARTING_BUDGET,
        "completed_rounds": [
            round_data.round_num for round_data in rounds
        ],
        "reconstructed_rounds": [
            round_data.round_num
            for round_data in rounds
            if round_data.reconstructed
        ],
        "genuine_rounds": [
            round_data.round_num
            for round_data in rounds
            if not round_data.reconstructed
        ],
        "chips": (
            (
                "Domain-informed V2 chip timing was applied using genuine "
                "pre-deadline archives only. The 3x Boost was saved."
                if with_chips
                else "No chips were played so risk tolerance is the isolated variable."
            )
            + " The normal 2x captain remained active."
        ),
        "chip_policy": "v2_domain_informed" if with_chips else "none",
        "saved_chips": list(saved_chips) if with_chips else [],
        "manager_policies": {
            "max_points": "Projected points after transfer penalties.",
            "balanced": (
                "Projected points plus "
                f"{season.BALANCED_PRICE_GAIN_VALUE:.0f} points of utility "
                "per forecast $1M appreciation."
            ),
            "budget_builder": (
                "Projected points plus "
                f"{season.BUDGET_BUILDER_PRICE_GAIN_VALUE:.0f} points of utility "
                "per forecast $1M appreciation."
            ),
        },
        "risk_policies": {
            "total_avoidance": (
                "Lexicographically minimises negative P5 exposure before "
                "applying the manager philosophy."
            ),
            "minimal_risk_accepted": (
                "Subtracts 2.00 utility points per point of negative P5 exposure."
            ),
            "medium_tolerance": (
                "Subtracts 0.75 utility points per point of negative P5 exposure."
            ),
            "maximum_tolerance": (
                "No downside penalty; selects solely on manager philosophy."
            ),
        },
        "risk_measure": (
            "Sum of max(-P5, 0) across the five drivers and two constructors "
            "in each archived pre-deadline Monte Carlo forecast."
        ),
        "comparisons": comparisons,
        "headline": {
            "highest_points": best_points,
            "highest_genuine_archive_points": best_genuine_points,
            "highest_final_budget": best_budget,
            "lowest_mean_forecast_risk": lowest_forecast_risk,
        },
        "risk_signal_diagnostics": risk_diagnostics,
        "chip_effect_summary": chip_effect_summary,
        "managers": managers,
    }
    season.validate_result(result, rounds)
    return result


def _correlation_strength(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 0.7:
        return "strong"
    if magnitude >= 0.4:
        return "moderate"
    return "weak"


def build_markdown(result: dict[str, Any]) -> str:
    chip_enabled = result["chip_policy"] != "none"
    title_suffix = " with chips" if chip_enabled else ""
    lines = [
        f"# 2026 F1 Fantasy risk-tolerance season experiment{title_suffix}",
        "",
        "## Experimental design",
        "",
        (
            "Twelve virtual seasons were replayed: three manager philosophies "
            "crossed with four risk profiles. Every path started with $100.0M, "
            "used the same archived pre-deadline forecasts, carried its real "
            "lineup and prices forward, and scored against official results."
        ),
        "",
        f"- {result['chips']}",
        f"- Risk measure: {result['risk_measure']}",
        (
            "- Rounds "
            + ", ".join(str(value) for value in result["reconstructed_rounds"])
            + " use reconstructed archives; the remaining completed rounds use "
            "genuine lock-time archives."
        ),
        "",
        "## Results",
        "",
        (
            "| Manager | Risk profile | Full pts | Genuine pts | Final budget | "
            "Mean forecast downside | Realised negative pts | "
            "Worst round | Round SD |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy in MANAGERS:
        for risk_profile in RISK_PROFILES:
            row = next(
                item
                for item in result["comparisons"]
                if item["strategy"] == strategy
                and item["risk_profile"] == risk_profile
            )
            lines.append(
                f"| {MANAGER_LABELS[strategy]} | "
                f"{RISK_LABELS[risk_profile]} | "
                f"{row['season_points']:.0f} | "
                f"{row['genuine_archive_points']:.0f} | "
                f"${row['final_budget']:.1f}M | "
                f"{row['mean_forecast_negative_p5_exposure']:.1f} | "
                f"{row['realized_negative_points']:.0f} | "
                f"{row['worst_round_points']:.0f} | "
                f"{row['round_points_std']:.1f} |"
            )

    if chip_enabled:
        lines.extend(
            [
                "",
                "## Chip impact versus the matching no-chip path",
                "",
                "| Manager | Risk profile | Full-points Δ | Genuine-points Δ | Budget Δ |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for strategy in MANAGERS:
            for risk_profile in RISK_PROFILES:
                row = next(
                    item
                    for item in result["comparisons"]
                    if item["strategy"] == strategy
                    and item["risk_profile"] == risk_profile
                )
                lines.append(
                    f"| {MANAGER_LABELS[strategy]} | "
                    f"{RISK_LABELS[risk_profile]} | "
                    f"{row['points_vs_no_chips']:+.0f} | "
                    f"{row['genuine_points_vs_no_chips']:+.0f} | "
                    f"{row['budget_vs_no_chips']:+.1f}M |"
                )

        lines.extend(
            [
                "",
                "## Chip schedules",
                "",
                "| Manager | Risk profile | Limitless | Wild Card | No Negative | Autopilot | 3x Boost |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for manager in result["managers"]:
            inverse = {
                chip: int(round_num)
                for round_num, chip in manager["chip_schedule"].items()
            }
            lines.append(
                f"| {MANAGER_LABELS[manager['strategy']]} | "
                f"{RISK_LABELS[manager['risk_profile']]} | "
                f"{inverse.get('limitless', 'Saved')} | "
                f"{inverse.get('wild_card', 'Saved')} | "
                f"{inverse.get('no_negative', 'Saved')} | "
                f"{inverse.get('autopilot', 'Saved')} | "
                f"{inverse.get('3x_boost', 'Saved')} |"
            )
        lines.extend(
            [
                "",
                "## Conditional chip contribution",
                "",
                (
                    "Each value removes one chip while holding the other scheduled "
                    "chips fixed, then replays the remaining season path."
                ),
                (
                    "These conditional effects are not additive because removing "
                    "a chip can alter later transfers, budgets, and Wild Card state."
                ),
                "",
                "| Chip | Paths played | Positive return | Mean points | Median points | Range | Mean budget |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for chip, label in (
            ("limitless", "Limitless"),
            ("wild_card", "Wild Card"),
            ("no_negative", "No Negative"),
            ("autopilot", "Autopilot"),
        ):
            row = result["chip_effect_summary"][chip]
            lines.append(
                f"| {label} | {row['paths_played']} | "
                f"{100 * row['positive_return_share']:.0f}% | "
                f"{row['mean_season_points_delta']:+.1f} | "
                f"{row['median_season_points_delta']:+.1f} | "
                f"{row['minimum_season_points_delta']:+.0f} to "
                f"{row['maximum_season_points_delta']:+.0f} | "
                f"{row['mean_final_budget_delta']:+.1f}M |"
            )

    headline = result["headline"]
    lines.extend(
        [
            "",
            "## Headline outcomes",
            "",
            (
                "- Highest score: "
                f"{MANAGER_LABELS[headline['highest_points']['strategy']]} / "
                f"{RISK_LABELS[headline['highest_points']['risk_profile']]} — "
                f"{headline['highest_points']['season_points']:.0f} points."
            ),
            (
                "- Highest score on genuine lock-time archives: "
                f"{MANAGER_LABELS[headline['highest_genuine_archive_points']['strategy']]} / "
                f"{RISK_LABELS[headline['highest_genuine_archive_points']['risk_profile']]} — "
                f"{headline['highest_genuine_archive_points']['genuine_archive_points']:.0f} points."
            ),
            (
                "- Highest final budget: "
                f"{MANAGER_LABELS[headline['highest_final_budget']['strategy']]} / "
                f"{RISK_LABELS[headline['highest_final_budget']['risk_profile']]} — "
                f"${headline['highest_final_budget']['final_budget']:.1f}M."
            ),
            (
                "- Lowest forecast downside: "
                f"{MANAGER_LABELS[headline['lowest_mean_forecast_risk']['strategy']]} / "
                f"{RISK_LABELS[headline['lowest_mean_forecast_risk']['risk_profile']]} — "
                f"{headline['lowest_mean_forecast_risk']['mean_forecast_negative_p5_exposure']:.1f} "
                "mean negative-P5 exposure."
            ),
            "",
            "## Within-manager trade-offs",
            "",
        ]
    )
    for strategy in MANAGERS:
        reference = next(
            row
            for row in result["comparisons"]
            if row["strategy"] == strategy
            and row["risk_profile"] == "maximum_tolerance"
        )
        alternatives = [
            row
            for row in result["comparisons"]
            if row["strategy"] == strategy
            and row["risk_profile"] != "maximum_tolerance"
        ]
        best_alternative = max(
            alternatives,
            key=lambda row: float(row["genuine_archive_points"]),
        )
        budget_delta = float(
            best_alternative["budget_vs_maximum_tolerance"]
        )
        lines.append(
            f"- {MANAGER_LABELS[strategy]}: its strongest risk-managed version "
            f"was {RISK_LABELS[best_alternative['risk_profile']]}, scoring "
            f"{best_alternative['genuine_points_vs_maximum_tolerance']:+.0f} "
            "genuine-archive points and "
            f"finishing with ${abs(budget_delta):.1f}M "
            f"{'more' if budget_delta >= 0 else 'less'} "
            "versus maximum tolerance."
        )
    diagnostics = result["risk_signal_diagnostics"]
    best_points = headline["highest_points"]
    best_genuine_points = headline["highest_genuine_archive_points"]
    best_budget = headline["highest_final_budget"]
    headline_budget_delta = (
        float(best_budget["final_budget"])
        - float(best_points["final_budget"])
    )
    lines.extend(
        [
            (
                f"- The highest-budget path finished "
                f"{best_budget['season_points'] - best_points['season_points']:+.0f} "
                "full-season points, "
                f"{best_budget['genuine_archive_points'] - best_genuine_points['genuine_archive_points']:+.0f} "
                "genuine-archive points, and "
                f"${abs(headline_budget_delta):.1f}M "
                f"{'more' if headline_budget_delta >= 0 else 'less'} "
                "relative to the highest-scoring path."
            ),
            "",
            "## Did forecast risk predict realised damage?",
            "",
            (
                "- The descriptive correlation between mean forecast negative-P5 "
                "exposure and realised negative-point magnitude was "
                f"{diagnostics['forecast_vs_realized_negative_magnitude_pearson']:.3f}, "
                f"a {_correlation_strength(diagnostics['forecast_vs_realized_negative_magnitude_pearson'])} "
                "relationship in this sample."
            ),
            (
                "- Restricting to genuine archives, the forecast-risk versus "
                "realised-negative correlation was "
                f"{diagnostics['genuine_forecast_vs_realized_negative_magnitude_pearson']:.3f}, "
                f"also {_correlation_strength(diagnostics['genuine_forecast_vs_realized_negative_magnitude_pearson'])}."
            ),
            (
                "- Genuine-archive forecast downside and points had a "
                f"{diagnostics['genuine_forecast_risk_vs_points_pearson']:.3f} "
                f"correlation, a {_correlation_strength(diagnostics['genuine_forecast_risk_vs_points_pearson'])} "
                "relationship."
            ),
            f"- {diagnostics['warning']}",
            "",
            "## Interpretation guardrails",
            "",
            (
                "- Risk profiles use information available before the deadline. "
                "Official outcomes are used only after selection to score the paths."
            ),
            (
                "- Total avoidance is intentionally extreme: even a tiny reduction "
                "in negative-P5 exposure outranks projected points and price growth."
            ),
            (
                "- This is one partial season. The result shows how these policies "
                "behaved in 2026 so far, not a guarantee that the same risk setting "
                "will win future seasons."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-chips", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args()

    output_json = args.output_json or (
        DEFAULT_CHIP_JSON if args.with_chips else DEFAULT_JSON
    )
    output_markdown = args.output_markdown or (
        DEFAULT_CHIP_MARKDOWN if args.with_chips else DEFAULT_MARKDOWN
    )
    result = run_experiment(with_chips=args.with_chips)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    output_markdown.write_text(build_markdown(result), encoding="utf-8")
    print(f"JSON -> {output_json}")
    print(f"Report -> {output_markdown}")
    best = result["headline"]["highest_points"]
    print(
        "Highest score: "
        f"{MANAGER_LABELS[best['strategy']]} / "
        f"{RISK_LABELS[best['risk_profile']]} = "
        f"{best['season_points']:.0f}"
    )


if __name__ == "__main__":
    main()
