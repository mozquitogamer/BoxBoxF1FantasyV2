"""Focused checks for the risk-experiment team-evolution report."""

from __future__ import annotations

from pipeline import build_risk_team_evolution_report as evolution


def test_report_reconciles_every_persistent_transfer() -> None:
    source = evolution._load_json(evolution.DEFAULT_INPUT)
    report = evolution.build_report(source)

    expected_transfers = sum(
        manager["summary"]["transfers"] for manager in source["managers"]
    )
    assert len(report["evolution"]) == 12 * 11
    assert len(report["transfer_ledger"]) == expected_transfers
    assert all(row["reasons"] for row in report["evolution"])
    assert all(row["reason"] for row in report["transfer_ledger"])


def test_limitless_is_recorded_as_temporary_not_persistent_transfer() -> None:
    source = evolution._load_json(evolution.DEFAULT_INPUT)
    report = evolution.build_report(source)
    limitless_rows = [
        row for row in report["evolution"] if row["chip"] == "limitless"
    ]

    assert len(limitless_rows) == 12
    assert all("reverted" in row["change_type"] for row in limitless_rows)
    assert not any(
        row["chip"] == "limitless" for row in report["transfer_ledger"]
    )
