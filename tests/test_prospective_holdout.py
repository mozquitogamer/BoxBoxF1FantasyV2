"""Prospective manifests make phase-archive mutation detectable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import prospective_holdout as holdout


def _archive(path: Path, finish: int = 1, reconstructed: bool = False) -> None:
    path.write_text(json.dumps({
        "season": 2026,
        "round": 14,
        "phase": "post_fp",
        "reconstructed": reconstructed,
        "exported_at": "2026-08-22T12:00:00+00:00",
        "drivers": [{"driver_id": "VER", "predicted_finish": finish}],
    }))


def test_holdout_manifest_is_idempotent_and_detects_changes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(holdout, "HOLDOUT_DIR", tmp_path / "holdouts")
    archive = tmp_path / "predictions_round14_post_fp.json"
    _archive(archive)

    manifest = holdout.freeze_phase_archive(
        archive,
        14,
        "post_fp",
        prediction_metadata={
            "quali_model_sha256_16": "abc",
            "weather_features_used": {
                "forecast_snapshot_id": "snapshot-1",
            },
        },
    )
    assert holdout.freeze_phase_archive(archive, 14, "post_fp") == manifest
    saved = json.loads(manifest.read_text())
    assert saved["model_identity"]["quali_model_sha256_16"] == "abc"
    assert saved["weather_snapshot"]["snapshot_id"] == "snapshot-1"

    _archive(archive, finish=2)
    with pytest.raises(RuntimeError, match="changed"):
        holdout.freeze_phase_archive(archive, 14, "post_fp")


def test_reconstructed_archive_cannot_be_registered(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(holdout, "HOLDOUT_DIR", tmp_path / "holdouts")
    archive = tmp_path / "predictions_round14_post_fp.json"
    _archive(archive, reconstructed=True)

    with pytest.raises(ValueError, match="Reconstructed"):
        holdout.freeze_phase_archive(archive, 14, "post_fp")
