"""Focused tests for the marginal budget-to-points analysis."""

from __future__ import annotations

from pipeline import analyze_budget_point_value as budget


def test_curve_excludes_reconstructed_outlier_and_is_monotonic() -> None:
    records = []
    for races in (1, 2, 3):
        for delta in (0.3, 0.5, 1.0, 2.0):
            records.append(
                {
                    "strategy": "max_points",
                    "archive_reconstructed": False,
                    "races_remaining": races,
                    "extra_budget": delta,
                    "continuation_projected_gain": races * delta,
                }
            )
    records.append(
        {
            "strategy": "max_points",
            "archive_reconstructed": True,
            "races_remaining": 4,
            "extra_budget": 1.0,
            "continuation_projected_gain": 10_000.0,
        }
    )

    fitted = budget.fit_budget_curve(
        records,
        strategy="max_points",
        max_horizon=5,
    )
    values = list(fitted["curve_points_per_million"].values())

    assert values == sorted(values)
    assert values[-1] < 10.0
    assert fitted["isolated_0_3m_observations"] == 3


def test_predicted_point_value_uses_exact_0_3m_calibration() -> None:
    curve = {
        "curve_points_per_million": {
            "0": 0.0,
            "1": 2.0,
            "2": 3.0,
            "3": 4.0,
            "4": 5.0,
            "5": 6.0,
            "7": 7.0,
            "8": 8.0,
            "10": 9.0,
            "11": 10.0,
        }
    }
    forecast = {
        "by_predicted_bracket": {
            "+0.3": {
                "mean_actual_change": 0.24,
            }
        }
    }

    result = budget.decision_examples(curve, forecast)

    assert result["price_forecast_reliability_discount"] == 0.8
    assert (
        result["by_races_remaining"]["11"][
            "predicted_0_3m_expected_point_value"
        ]
        == 2.16
    )
    assert (
        result["by_races_remaining"]["11"]["secured_0_3m_point_value"]
        == 3.0
    )


def test_decision_grade_value_applies_both_realization_discounts() -> None:
    curve = {
        "curve_points_per_million": {
            "0": 0.0,
            "1": 2.0,
            "2": 3.0,
            "3": 4.0,
            "4": 5.0,
            "5": 6.0,
            "7": 7.0,
            "8": 8.0,
            "10": 9.0,
            "11": 10.0,
        }
    }
    forecast = {
        "by_predicted_bracket": {
            "+0.3": {
                "mean_actual_change": 0.24,
            }
        }
    }
    realization = {"decision_grade_multiplier": 0.5}

    result = budget.decision_examples(curve, forecast, realization)
    current = result["by_races_remaining"]["11"]

    assert current["decision_grade_predicted_0_3m_point_value"] == 1.08
    assert current["decision_grade_secured_1_0m_point_value"] == 5.0
    assert current["secured_budget_needed_for_10_points"] == 2.0
    assert current["predicted_budget_needed_for_10_points"] == 2.78

    final_round = result["by_races_remaining"]["1"]
    assert final_round["races_budget_can_be_used"] == 0
    assert final_round["decision_grade_predicted_0_3m_point_value"] == 0.0
    assert final_round["predicted_budget_needed_for_10_points"] is None


def test_affordability_frontier_uses_smallest_positive_delta() -> None:
    records = [
        {
            "strategy": "max_points",
            "archive_reconstructed": False,
            "start_round": 6,
            "races_remaining": 3,
            "extra_budget": delta,
            "continuation_projected_gain": gain,
        }
        for delta, gain in (
            (0.3, 0.0),
            (0.5, 0.0),
            (0.6, 2.0),
            (1.0, 4.0),
            (2.0, 8.0),
        )
    ]

    result = budget.affordability_frontiers(records)

    assert result["median_minimum_tested_unlock_millions"] == 0.6
    assert result["share_unlocked_by_0_5m"] == 0.0
    assert result["share_unlocked_by_1_0m"] == 1.0


def test_risk_experiment_context_compares_equal_budget_paths() -> None:
    result = budget.risk_experiment_context()

    assert result["paths"] == 12
    assert result["highest_budget"] == 124.3
    assert result["points_spread_at_highest_budget"] == 150.0
    assert result["budget_builder_medium_vs_minimal"] == {
        "points_difference": 150.0,
        "genuine_points_difference": 73.0,
        "budget_difference": 0.0,
    }


def test_public_payload_contains_only_decision_inputs() -> None:
    result = {
        "season": 2026,
        "completed_rounds": [1, 2, 6],
        "current_races_remaining": 11,
        "method": "test method",
        "curves": {
            "max_points": {
                "formula": "ceiling * (1 - exp(-races_remaining / tau))",
                "ceiling_points_per_million": 8.5,
                "tau_races": 1.8,
                "curve_points_per_million": {"0": 0.0, "10": 8.5},
                "curve_points_per_million_p25": {"0": 0.0, "10": 8.0},
                "curve_points_per_million_p75": {"0": 0.0, "10": 9.0},
            }
        },
        "price_forecast_backtest": {
            "predicted_rise_hit_rate": 0.9,
            "signed_realization_ratio": 0.75,
            "by_predicted_bracket": {
                "+0.3": {
                    "mean_actual_change": 0.24,
                    "rise_hit_rate": 0.95,
                }
            },
        },
        "marginal_gain_realization": {
            "decision_grade_multiplier": 0.625,
        },
        "affordability_frontiers": {
            "genuine_deadline_states": 2,
            "median_minimum_tested_unlock_millions": 0.7,
            "share_unlocked_by_0_3m": 0.0,
            "share_unlocked_by_0_5m": 0.0,
            "share_unlocked_by_1_0m": 0.5,
        },
        "price_plateau_rules": {"low_tier_max_price": 18.5},
        "decision_examples": {"by_races_remaining": {}},
        "marginal_records": [
            {
                "strategy": "max_points",
                "start_round": 6,
                "archive_reconstructed": False,
            }
        ],
    }

    payload = budget.build_public_payload(result)

    assert payload["updated_after_round"] == 6
    assert payload["calibration"]["forecast_realization_discount"] == 0.8
    assert payload["calibration"][
        "forecast_signed_realization_discount"
    ] == 0.75
    assert payload["affordability_frontier"][
        "median_minimum_unlock_millions"
    ] == 0.7
    assert payload["source"]["genuine_deadline_rounds"] == [6]
    assert "marginal_records" not in payload
