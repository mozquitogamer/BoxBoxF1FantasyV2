"""Public prediction phase archives are write-once unless explicitly corrected."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "export_archive_contract",
    ROOT / "pipeline" / "08_export_website_json.py",
)
EXPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EXPORT)


def _payload(value: int) -> dict:
    return {
        "round": 14,
        "phase": "post_fp",
        "drivers": [{"driver_id": "VER", "predicted_finish": value}],
    }


def test_phase_archive_is_frozen_by_default(tmp_path: Path) -> None:
    path = tmp_path / "predictions_round14_post_fp.json"

    assert EXPORT.write_phase_archive_safely(
        path, _payload(1), 14, "post_fp"
    )
    assert not EXPORT.write_phase_archive_safely(
        path, _payload(9), 14, "post_fp"
    )

    saved = json.loads(path.read_text())
    assert saved["drivers"][0]["predicted_finish"] == 1


def test_phase_archive_requires_explicit_correction_to_replace(tmp_path: Path) -> None:
    path = tmp_path / "predictions_round14_post_fp.json"
    EXPORT.write_phase_archive_safely(path, _payload(1), 14, "post_fp")

    assert EXPORT.write_phase_archive_safely(
        path, _payload(2), 14, "post_fp", replace=True
    )
    saved = json.loads(path.read_text())
    assert saved["drivers"][0]["predicted_finish"] == 2


def test_phase_archive_rejects_mislabeled_payload(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="payload says"):
        EXPORT.write_phase_archive_safely(
            tmp_path / "bad.json",
            {"phase": "pre_fp"},
            14,
            "post_fp",
        )
