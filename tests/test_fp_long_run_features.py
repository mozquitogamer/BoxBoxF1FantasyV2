"""Regression coverage for session-safe FP stint features."""

import importlib

import numpy as np
import pandas as pd

from pipeline.fp_long_runs import (
    FP_STINT_SEMANTICS_VERSION,
    extract_representative_long_runs,
    require_fp_stint_semantics,
    select_headline_long_run,
)


features = importlib.import_module("pipeline.03_extract_features")
analysis = importlib.import_module("pipeline.10_fp_analysis")


def _run(
    session: str,
    stint: int,
    compound: str,
    times: list[float],
    *,
    driver: str = "AAA",
) -> pd.DataFrame:
    return pd.DataFrame({
        "driver_id": driver,
        "constructor_id": "team",
        "session": session,
        "stint_number": stint,
        "compound": compound,
        "lap_number": np.arange(1, len(times) + 1),
        "tyre_life": np.arange(1, len(times) + 1),
        "lap_time": times,
    })


def test_same_stint_number_across_sessions_does_not_create_a_long_run():
    laps = pd.concat([
        _run("FP1", 1, "MEDIUM", [110.0, 110.1, 110.2]),
        _run("FP2", 1, "MEDIUM", [109.8, 109.9, 110.0]),
    ], ignore_index=True)

    result = features.long_run_features(laps, min_laps=5)

    assert np.isnan(result["long_run_avg"])
    assert result["long_run_laps"] == 0
    assert np.isnan(features.degradation_features(laps)["degradation_rate"])


def test_same_session_stint_number_different_compounds_do_not_merge():
    laps = pd.concat([
        _run("FP2", 1, "MEDIUM", [110.0, 110.1, 110.2]),
        _run("FP2", 1, "HARD", [111.0, 111.1, 111.2]),
    ], ignore_index=True)

    assert extract_representative_long_runs(laps) == []
    assert np.isnan(features.long_run_features(laps, 5)["long_run_avg"])


def test_soft_long_run_is_shared_by_features_analysis_and_fuel_correction():
    times = [100.0, 100.1, 100.2, 100.3, 100.4, 100.5]
    for compound in ("SOFT", "S"):
        laps = _run("FP2", 2, compound, times)
        runs = extract_representative_long_runs(laps)
        assert len(runs) == 1 and runs[0]["compound"] == "SOFT"
        assert runs[0]["kept_laps"] == times
        assert features.long_run_features(laps, 5)["long_run_avg"] == np.mean(times)
        compound_features = features.compound_features(laps)
        assert compound_features["soft_long_run_avg"] == np.mean(times)
        assert np.isfinite(compound_features["soft_degradation"])
        assert np.isfinite(features.degradation_features(laps)["degradation_rate"])
        deep_dive = laps.rename(columns={"stint_number": "stint"})
        assert analysis.analyze_long_run_pace(deep_dive)["AAA"]["headline_laps"] == 6
        fuel = analysis.analyze_fuel_corrected_pace(deep_dive)["AAA"]
        expected = np.mean(np.array(times) - analysis.FUEL_EFFECT_PER_LAP * np.arange(5, -1, -1))
        assert fuel["fuel_corrected_avg"] == round(float(expected), 3)
        assert fuel["laps_used"] == 6


def test_soft_qualifying_runs_and_insufficient_clean_laps_still_do_not_qualify():
    for times in ([99.0, 99.1, 99.2, 99.3], [100.0, 100.1, 100.2, 130.0, 140.0]):
        laps = _run("FP2", 1, "SOFT", times)
        assert extract_representative_long_runs(laps) == []
        assert np.isnan(features.compound_features(laps)["soft_long_run_avg"])


def test_soft_traffic_spike_is_trimmed_without_losing_degradation_tail():
    laps = _run("FP2", 1, "SOFT", [100.0, 100.2, 108.0, 100.6, 100.8, 101.0])
    run = extract_representative_long_runs(laps)[0]
    assert run["kept_laps"] == [100.0, 100.2, 100.6, 100.8, 101.0]
    assert run["excluded_laps"] == [108.0]
    assert run["kept_tyre_age"] == [1, 2, 4, 5, 6]


def test_soft_long_run_columns_survive_training_input_loading(tmp_path, monkeypatch):
    inputs = importlib.import_module("pipeline.04_build_model_inputs")
    laps = _run("FP2", 1, "SOFT", [100.0, 100.1, 100.2, 100.3, 100.4])
    extracted = features.extract_driver_features(laps, min_long_run_laps=5)
    extracted["fp_stint_semantics_version"] = FP_STINT_SEMANTICS_VERSION
    feature_path = tmp_path / "round16" / "features.parquet"
    feature_path.parent.mkdir()
    extracted.to_parquet(feature_path, index=False)
    monkeypatch.setattr(inputs, "FEATURES_DIR", tmp_path)
    loaded = inputs.load_fp_features_for_round(inputs.CURRENT_SEASON, 16)
    assert loaded is not None
    assert np.isfinite(loaded.loc[0, "soft_long_run_avg"])
    assert np.isfinite(loaded.loc[0, "soft_degradation"])


def test_feature_semantics_stamp_rejects_stale_or_missing_data():
    current = pd.DataFrame({
        "fp_stint_semantics_version": [FP_STINT_SEMANTICS_VERSION] * 2
    })
    require_fp_stint_semantics(current, source="test")

    for stale in [
        pd.DataFrame({"x": [1]}),
        pd.DataFrame({
            "fp_stint_semantics_version": [FP_STINT_SEMANTICS_VERSION - 1]
        }),
        pd.DataFrame({
            "fp_stint_semantics_version": [FP_STINT_SEMANTICS_VERSION, np.nan]
        }),
    ]:
        with np.testing.assert_raises_regex(RuntimeError, "semantics mismatch"):
            require_fp_stint_semantics(stale, source="test")


def test_fp2_is_headline_and_traffic_spike_is_trimmed():
    laps = pd.concat([
        _run("FP1", 1, "HARD", [110.0, 110.1, 110.2, 110.3, 110.4]),
        _run("FP2", 2, "MEDIUM", [112.0, 112.1, 120.0, 112.3, 112.4, 112.5]),
        _run("FP3", 3, "HARD", [108.0, 108.1, 108.2, 108.3, 108.4]),
    ], ignore_index=True)

    headline = select_headline_long_run(extract_representative_long_runs(laps))

    assert headline is not None
    assert headline["session"] == "FP2"
    assert headline["laps"] == 5
    assert headline["avg_pace"] == np.mean([112.0, 112.1, 112.3, 112.4, 112.5])


def test_missing_long_run_rank_stays_nan_and_shared_analysis_matches():
    valid = _run("FP2", 1, "MEDIUM", [111.0, 111.1, 111.2, 111.3, 111.4], driver="AAA")
    short = _run("FP2", 1, "MEDIUM", [112.0, 112.1, 112.2], driver="BBB")
    laps = pd.concat([valid, short], ignore_index=True)

    extracted = features.extract_driver_features(laps, min_long_run_laps=5)
    by_driver = extracted.set_index("driver_id")
    assert by_driver.loc["AAA", "long_run_rank"] == 1
    assert np.isnan(by_driver.loc["BBB", "long_run_rank"])

    deep_dive_input = laps.rename(columns={"stint_number": "stint"})
    deep_dive = analysis.analyze_long_run_pace(deep_dive_input)
    assert by_driver.loc["AAA", "long_run_avg"] == deep_dive["AAA"]["avg_long_run_pace"]
    assert "BBB" not in deep_dive


def test_short_run_grouping_keeps_late_session_fresh_tyre_lap():
    fp1 = _run("FP1", 1, "SOFT", [110.0, 109.0, 108.0])
    fp2 = _run("FP2", 1, "SOFT", [107.0, 106.0, 99.0])
    laps = pd.concat([fp1, fp2], ignore_index=True)

    assert features.short_run_features(laps)["short_run_best"] == 99.0


def test_fuel_corrected_table_uses_only_robust_headline_race_runs():
    fp1 = _run("FP1", 1, "MEDIUM", [110.0, 110.1, 110.2, 110.3, 110.4])
    fp2 = _run("FP2", 2, "MEDIUM", [112.0, 112.1, 112.2, 112.3, 112.4])
    soft = _run("FP2", 3, "SOFT", [111.0, 111.1, 111.2, 111.3, 111.4])
    laps = pd.concat([fp1, fp2, soft], ignore_index=True).rename(
        columns={"stint_number": "stint"}
    )

    result = analysis.analyze_fuel_corrected_pace(laps)["AAA"]

    expected = np.mean(np.array([112.0, 112.1, 112.2, 112.3, 112.4, 111.0, 111.1, 111.2, 111.3, 111.4])
                       - analysis.FUEL_EFFECT_PER_LAP * np.tile(np.arange(4, -1, -1), 2))
    assert result["laps_used"] == 10
    assert result["fuel_corrected_avg"] == round(float(expected), 3)


def test_fuel_correction_preserves_tyre_age_gap_after_traffic_trim():
    laps = _run(
        "FP2", 2, "MEDIUM", [112.0, 112.1, 120.0, 112.3, 112.4, 112.5]
    ).rename(columns={"stint_number": "stint"})

    result = analysis.analyze_fuel_corrected_pace(laps)["AAA"]
    kept_times = np.array([112.0, 112.1, 112.3, 112.4, 112.5])
    kept_ages = np.array([1.0, 2.0, 4.0, 5.0, 6.0])
    expected = np.mean(
        kept_times - analysis.FUEL_EFFECT_PER_LAP * (kept_ages.max() - kept_ages)
    )

    assert result["laps_used"] == 5
    assert result["fuel_corrected_avg"] == round(float(expected), 3)
