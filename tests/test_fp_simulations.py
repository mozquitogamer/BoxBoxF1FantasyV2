"""Race-run evidence must remain comparable and distinguish push/cool laps."""

import importlib

import pandas as pd

from pipeline.fp_simulations import analyze_comparable_long_runs


analysis = importlib.import_module("pipeline.10_fp_analysis")


def laps(driver, session, compound, times, stint=1):
    return pd.DataFrame({
        "driver_id": driver,
        "session": session,
        "compound": compound,
        "stint": stint,
        "lap_number": range(1, len(times) + 1),
        "tyre_life": range(1, len(times) + 1),
        "lap_time": times,
    })


def test_alternating_push_cool_laps_do_not_set_race_pace():
    evidence = analyze_comparable_long_runs(laps(
        "LIN", "FP1", "HARD", [110.530, 133.723, 107.946, 146.424, 107.726, 135.686, 107.444]
    ))

    run = evidence["drivers"]["LIN"]["runs"][0]
    assert run["quality"] == "interrupted"
    assert run["interruptions"] == 3
    assert [lap["lap_number"] for lap in run["lap_sequence"]] == list(range(1, 8))
    assert evidence["groups"] == []


def test_slow_opening_lap_is_removed_with_four_other_laps():
    evidence = analyze_comparable_long_runs(laps(
        "RUS", "FP2", "MEDIUM", [112.977, 108.336, 107.905, 107.763, 107.837]
    ))

    run = evidence["drivers"]["RUS"]["runs"][0]
    assert run["quality"] == "clean"
    assert run["lap_sequence"][0]["selected"] is False
    assert run["laps"] == 4
    assert run["median_pace"] == 107.871


def test_four_lap_run_is_partial_and_all_tyre_compounds_enter_the_session():
    frame = pd.concat([
        laps("ANT", "FP2", "MEDIUM", [109.444, 108.703, 108.138, 107.793]),
        laps("RUS", "FP2", "MEDIUM", [108.1, 108.0, 107.9, 107.8, 107.7]),
        laps("PIA", "FP2", "SOFT", [108.8, 108.7, 108.6, 108.5, 108.4]),
        laps("LIN", "FP2", "HARD", [108.8, 108.7, 108.6, 108.5, 108.4]),
    ], ignore_index=True)
    evidence = analyze_comparable_long_runs(frame)

    groups = {group["id"]: group for group in evidence["groups"]}
    assert groups["FP2"]["drivers"] == 4
    assert groups["FP2"]["partial_drivers"] == 1
    assert groups["FP2"]["compounds"] == ["HARD", "MEDIUM", "SOFT"]
    assert "FP1" not in groups
    assert evidence["drivers"]["ANT"]["runs"][0]["quality"] == "partial"


def test_missing_compound_does_not_disqualify_a_sustained_run():
    evidence = analyze_comparable_long_runs(pd.concat([
        laps("AAA", "FP2", "UNKNOWN", [109, 108.8, 108.6, 108.4, 108.2]),
        laps("BBB", "FP2", "MEDIUM", [110, 109.8, 109.6, 109.4, 109.2]),
    ], ignore_index=True))
    assert evidence["drivers"]["AAA"]["runs"][0]["quality"] == "clean"
    assert evidence["groups"][0]["compounds"] == ["MEDIUM", "UNKNOWN"]


def test_sprint_qualifying_laps_cannot_enter_race_run_comparison():
    frame = pd.concat([
        laps("AAA", "FP1", "MEDIUM", [110, 109, 108, 107, 106]),
        laps("AAA", "SPRINT_QUALIFYING", "SOFT", [101, 100, 99, 98, 97], stint=2),
    ], ignore_index=True)
    evidence = analyze_comparable_long_runs(frame)
    assert [run["session"] for run in evidence["drivers"]["AAA"]["runs"]] == ["FP1"]


def test_qualifying_indicator_records_lap_conditions():
    frame = pd.concat([
        laps("AAA", "FP1", "HARD", [101.0, 101.2, 101.3]),
        laps("AAA", "FP2", "MEDIUM", [100.0, 100.4, 100.8]),
    ], ignore_index=True)
    result = analysis.analyze_qualifying_pace(frame)["AAA"]
    assert result["best_lap"] == 100.0
    assert result["best_lap_session"] == "FP2"
    assert result["best_lap_compound"] == "MEDIUM"
