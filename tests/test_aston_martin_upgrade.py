"""Regression coverage for the Round 15 Aston Martin race-only overlay."""

import importlib
import json
from pathlib import Path

import pandas as pd


upgrades = importlib.import_module("pipeline.apply_upgrades")


def test_round15_aston_modifier_is_race_only_and_team_scoped():
    team_bumps, driver_bumps, scope = upgrades._load_upgrades(15)

    assert scope == "race_only"
    assert team_bumps == {"aston_martin": 1.9}
    assert driver_bumps == {}

    config = json.loads(
        (Path(__file__).resolve().parents[1] / "data/seed/team_upgrades.json").read_text()
    )
    assert "R13-R14" in config["modifiers"]["aston_martin"]["note"]


def test_round15_aston_bump_leaves_quali_order_unchanged():
    # ALO/STR are the bottom two in this compact synthetic field. The bump is
    # deliberately applied only to the race scores: qualifying remains the
    # evidence-backed model order while both Aston cars gain one race slot.
    raw = pd.Series([0.35, 0.25, 0.20, 0.10], index=["OTH1", "OTH2", "ALO", "STR"])
    bumps = pd.Series([0.0, 0.0, 1.9, 1.9], index=raw.index)
    zero = pd.Series(0.0, index=raw.index)

    quali = upgrades._rerank(raw, zero)
    race = upgrades._rerank(raw, bumps)

    assert quali.to_dict() == {"OTH1": 1, "OTH2": 2, "ALO": 3, "STR": 4}
    assert race["ALO"] < quali["ALO"]
    assert race["STR"] < quali["STR"]


def test_round15_public_export_contains_aston_overlay_effects():
    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "web/public/data/predictions_round15.json").read_text()
    )

    assert payload["upgrade_adjustments"] == {
        "modifiers": {"aston_martin": 1.9},
        "driver_modifiers": {},
        "scope": "race_only",
    }
    drivers = {
        d["driver_id"]: d for d in payload["drivers"] if d["constructor"] == "aston_martin"
    }
    assert drivers["ALO"]["predicted_finish"] == 19
    assert drivers["ALO"]["predicted_finish_adjusted"] == 12
    assert drivers["ALO"]["points_delta"] == 7.0
    assert drivers["STR"]["predicted_finish"] == 20
    assert drivers["STR"]["predicted_finish_adjusted"] == 16
    assert drivers["STR"]["points_delta"] == 4.0

    constructor = next(
        c for c in payload["constructors"] if c["constructor_id"] == "aston_martin"
    )
    assert constructor["expected_points_adjusted"] == constructor["expected_points"] + 11.0
    assert constructor["points_delta"] == 11.0
