from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline import pit_wall_weekly_preview as preview


def sample_predictions() -> dict:
    return {
        "race": "Preview Grand Prix",
        "round": 14,
        "season": 2026,
        "phase": "post_fp",
        "generated_at": "2026-08-20T08:06:57Z",
        "drivers": [
            {"driver_id": "TOP", "name": "Top Driver", "expected_points": 25.0, "risk": "LOW", "risk_rating": 5, "current_price": 20.0},
            {"driver_id": "MID", "name": "Middle Driver", "expected_points": 10.0, "risk": "MEDIUM", "risk_rating": 15, "current_price": 10.0},
            {"driver_id": "SELL", "name": "Sell <Candidate>", "expected_points": -2.0, "risk": "HIGH", "risk_rating": 30, "current_price": 5.0},
        ],
        "constructors": [
            {"constructor_id": "FAST", "name": "Fast Constructor", "expected_points": 60.0, "risk": "LOW", "risk_rating": 4, "current_price": 30.0},
            {"constructor_id": "SLOW", "name": "Slow Constructor", "expected_points": 3.0, "risk": "HIGH", "risk_rating": 31, "current_price": 5.0},
        ],
    }


def test_classifies_top_picks_and_likely_sells_without_member_data() -> None:
    picks = preview.classify_predictions(sample_predictions(), limit=1)

    assert picks["top_drivers"][0]["id"] == "TOP"
    assert picks["top_constructors"][0]["id"] == "FAST"
    assert picks["likely_driver_sells"][0]["id"] == "SELL"
    assert picks["likely_constructor_sells"][0]["id"] == "SLOW"
    assert picks["likely_driver_sells"][0]["reason"] == "negative expected return"
    assert all("email" not in item for group in picks.values() for item in group)


def test_preview_is_explicitly_pit_wall_and_local_only() -> None:
    result = preview.build_preview(sample_predictions(), site_origin="https://preview.example", limit=2)

    assert result["audience"] == "Pit Wall paid members"
    assert result["preview_only"] is True
    assert "Pit Wall paid members" in result["text"]
    assert "Beat V13 entrants" in result["text"]
    assert "free simulation contacts" in result["text"]
    assert "Top Driver" in result["html"]
    assert "Sell &lt;Candidate&gt;" in result["html"]
    assert "https://preview.example/" in result["text"]
    assert "delivery operation" in result["text"]


def test_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        preview.classify_predictions(sample_predictions(), limit=0)


def test_cli_reads_current_published_export_without_a_delivery_flag() -> None:
    script = Path(preview.__file__)
    completed = subprocess.run(
        [sys.executable, str(script), "--limit", "1"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Preview only" in completed.stdout
    assert "Pit Wall paid members" in completed.stdout
    assert "Top driver picks" in completed.stdout
    assert "Likely sells" in completed.stdout
