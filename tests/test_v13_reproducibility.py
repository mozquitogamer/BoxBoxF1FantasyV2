"""Frozen V13 records must work without local outputs or platform newlines."""

import hashlib
import json

import pytest

from pipeline import build_v13_manager as v13


@pytest.mark.parametrize("stored_newline", [b"\n", b"\r\n"])
@pytest.mark.parametrize("checkout_newline", [b"\n", b"\r\n"])
def test_archive_verification_accepts_only_line_ending_conversion(
    tmp_path, stored_newline, checkout_newline,
):
    source = b'{\n  "round": 14,\n  "message": "keep escaped \\n intact"\n}\n'
    original = source.replace(b"\n", stored_newline)
    checked_out = source.replace(b"\n", checkout_newline)
    expected = hashlib.sha256(original).hexdigest()
    archive = tmp_path / "forecast.json"
    archive.write_bytes(checked_out)

    assert v13._sha256(archive) == hashlib.sha256(checked_out).hexdigest()
    assert v13._archive_sha256_matches(archive, expected)
    assert archive.read_bytes() == checked_out

    for changed in [
        checked_out.replace(b"14", b"15"),
        checked_out.replace(b"  ", b"    "),
        checked_out.replace(b"\\n", b"\\r\\n"),
    ]:
        archive.write_bytes(changed)
        assert not v13._archive_sha256_matches(archive, expected)


@pytest.mark.parametrize("local_output", [False, True])
def test_final_fix_can_evaluate_from_tracked_actuals(tmp_path, monkeypatch, local_output):
    public = tmp_path / "web/public/data"
    public.mkdir(parents=True)
    archive = public / "forecast.json"
    archive.write_text(json.dumps({
        "generated_at": "2026-07-25T16:00:00Z",
        "drivers": [
            {"driver_id": "HAM", "current_price": 10, "projected_points_race": 9},
            {"driver_id": "NOR", "current_price": 10, "projected_points_race": 20},
        ],
    }), encoding="utf-8")
    published = public / "actual_round13.json"
    published.write_text(json.dumps({"drivers": [
        {"driver_id": "HAM", "race_points": 9},
        {"driver_id": "NOR", "race_points": 20},
    ]}), encoding="utf-8")
    if local_output:
        local = tmp_path / "data/predictions/round13/actual_fantasy_points.json"
        local.parent.mkdir(parents=True)
        local.write_text(json.dumps({"drivers": [
            {"driver_id": "HAM", "race_points": 9},
            {"driver_id": "NOR", "race_points": 22},
        ]}), encoding="utf-8")
    monkeypatch.setattr(v13, "ROOT", tmp_path)
    monkeypatch.setattr(v13, "WEB_DATA_DIR", public)
    monkeypatch.setattr(v13, "_valid_post_quali_archive", lambda _: archive)
    result = v13._final_fix({
        "round": 13, "persistent_drivers": ["HAM"],
        "bank_after_transfers": 0, "captain": "HAM",
    }, {"HAM": "Lewis Hamilton", "NOR": "Lando Norris"})

    assert result["outgoing"] == "HAM"
    assert result["incoming"] == "NOR"
    assert result["projected_gain"] == 22
    assert result["actual_gain"] == (26 if local_output else 22)
    assert result["banked_qualifying_driver"] == "HAM"
    assert result["archive_sha256"] == v13._sha256(archive)
