"""Regression tests for the actionable pre-FP/post-FP grid-anchor gate."""

import importlib

import pytest


predictions = importlib.import_module("pipeline.06_run_predictions")


def test_hard_track_anchor_is_off_before_practice():
    weight, reason = predictions.phase_aware_grid_anchor_weight(
        "hungaroring",
        fp_pace_driver_count=0,
    )

    assert weight == 0.0
    assert reason == "awaiting_fp_pace"


def test_partial_practice_file_does_not_activate_anchor():
    minimum = predictions.FP_QUALI_BLEND_TUNABLES["min_drivers_with_pace"]
    weight, reason = predictions.phase_aware_grid_anchor_weight(
        "hungaroring",
        fp_pace_driver_count=minimum - 1,
    )

    assert weight == 0.0
    assert reason == "awaiting_fp_pace"


def test_sufficient_fp_pace_activates_normal_track_scaled_anchor():
    minimum = predictions.FP_QUALI_BLEND_TUNABLES["min_drivers_with_pace"]
    weight, reason = predictions.phase_aware_grid_anchor_weight(
        "hungaroring",
        fp_pace_driver_count=minimum,
    )

    assert weight == pytest.approx(0.6375)
    assert reason == "fp_pace_available"


def test_actual_qualifying_can_anchor_retrospective_archive_without_fp():
    weight, reason = predictions.phase_aware_grid_anchor_weight(
        "hungaroring",
        fp_pace_driver_count=0,
        is_post_quali=True,
    )

    assert weight == pytest.approx(0.6375)
    assert reason == "actual_qualifying_available"


def test_normal_track_remains_unanchored_even_with_fp():
    weight, reason = predictions.phase_aware_grid_anchor_weight(
        "spa",
        fp_pace_driver_count=22,
    )

    assert weight == 0.0
    assert reason == "track_anchor_disabled"
