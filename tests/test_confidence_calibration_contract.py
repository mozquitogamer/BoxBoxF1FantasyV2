"""Calibration uses frozen, official, phase-specific forecast evidence."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from scipy.stats import norm

from pipeline import calibrate_confidence as calibration


ROOT = Path(__file__).resolve().parents[1]
MC_SPEC = importlib.util.spec_from_file_location(
    "mc_calibration_contract",
    ROOT / "pipeline" / "08_monte_carlo_fantasy.py",
)
MC = importlib.util.module_from_spec(MC_SPEC)
assert MC_SPEC.loader is not None
MC_SPEC.loader.exec_module(MC)


def _driver_payload() -> dict:
    return {
        "driver_id": "VER",
        "predicted_finish": 1,
        "expected_points": 30.0,
        "mc_total_mean": 29.0,
        "mc_total_std": 8.0,
        "mc_total_p5": 10.0,
        "mc_total_p25": 22.0,
        "mc_total_p75": 35.0,
        "mc_total_p95": 45.0,
    }


def test_p5_p95_multiplier_uses_central_90_percent_quantile() -> None:
    actual_coverage = 0.80
    result = calibration._compute_noise_multiplier(actual_coverage, 100)

    expected = norm.ppf(0.95) / norm.ppf(
        0.5 + actual_coverage / 2
    )
    assert result == expected
    assert result < norm.ppf(0.975) / norm.ppf(0.90)


def test_loader_reads_only_the_requested_frozen_phase(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(calibration, "WEB_DATA_DIR", tmp_path)
    payload = {
        "round": 14,
        "phase": "post_fp",
        "reconstructed": False,
        "drivers": [_driver_payload()],
    }
    (tmp_path / "predictions_round14_post_fp.json").write_text(
        json.dumps(payload)
    )

    frame = calibration.load_mc_predictions(14, phase="post_fp")

    assert frame is not None
    assert frame.loc[0, "driver_abbrev"] == "VER"
    assert frame.loc[0, "mc_total_median"] == 30.0
    assert frame.attrs["phase"] == "post_fp"
    assert frame.attrs["reconstructed"] is False
    assert calibration.load_mc_predictions(14, phase="pre_fp") is None


def test_reconstructed_archives_are_excluded_by_default(monkeypatch) -> None:
    import pandas as pd

    frame = pd.DataFrame([{
        "driver_abbrev": "VER",
        "det_race_position": 1,
        "mc_total_mean": 29.0,
        "mc_total_std": 8.0,
        "mc_total_median": 30.0,
        "mc_total_p5": 10.0,
        "mc_total_p25": 22.0,
        "mc_total_p75": 35.0,
        "mc_total_p95": 45.0,
    }])
    frame.attrs["reconstructed"] = True

    monkeypatch.setattr(
        calibration,
        "load_official_fantasy_points",
        lambda: {"1": {"drivers": {"VER": 32}}},
    )
    monkeypatch.setattr(
        calibration,
        "load_mc_predictions",
        lambda _round, phase: frame,
    )
    monkeypatch.setattr(
        calibration,
        "load_actual_results",
        lambda _round: {
            "drivers": [{
                "driver_id": "VER",
                "race_position": 1,
                "quali_position": 1,
                "is_dnf": False,
            }]
        },
    )

    assert calibration.analyze_calibration(phase="post_fp") == {}
    included = calibration.analyze_calibration(
        phase="post_fp",
        include_reconstructed=True,
    )
    assert included["n_rounds"] == 1
    assert included["phase"] == "post_fp"


def test_mc_loader_selects_strictly_earlier_cumulative_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(MC, "SEED_DIR", tmp_path)
    (tmp_path / "mc_calibration.json").write_text(json.dumps({
        "schema_version": 2,
        "default_phase": "post_fp",
        "phases": {
            "post_fp": {
                "noise_multiplier": 1.4,
                "bias_correction": 0.0,
                "n_rounds": 2,
                "coverage_90": 0.8,
                "per_tier": {},
                "cumulative": [
                    {
                        "through_round": 6,
                        "noise_multiplier": 1.1,
                        "bias_correction": -1.0,
                        "n_rounds": 1,
                        "coverage_90": 0.82,
                        "per_tier": {},
                    },
                    {
                        "through_round": 8,
                        "noise_multiplier": 1.2,
                        "bias_correction": 2.0,
                        "n_rounds": 2,
                        "coverage_90": 0.85,
                        "per_tier": {},
                    },
                ],
            }
        },
    }))

    round_8 = MC.load_calibration(round_num=8, phase="post_fp")
    assert round_8["noise_multiplier"] == 1.1
    assert round_8["source"] == "cumulative_through_R6"

    round_9 = MC.load_calibration(round_num=9, phase="post_fp")
    assert round_9["noise_multiplier"] == 1.2
    assert round_9["source"] == "cumulative_through_R8"

    missing = MC.load_calibration(round_num=9, phase="post_quali")
    assert missing["noise_multiplier"] == 1.0
    assert missing["source"] == "default_missing_phase:post_quali"
