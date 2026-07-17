"""Regression tests for live prior construction and driver-rating IDs."""

import importlib
import json

import numpy as np
import pandas as pd

from config.team_driver_ratings import (
    get_driver_overtaking,
    get_driver_quali_skill,
    get_driver_tire_mgmt,
    get_driver_wet_skill,
)


predictions = importlib.import_module("pipeline.06_run_predictions")


def test_jolpica_driver_ids_resolve_to_manual_ratings():
    assert get_driver_tire_mgmt("russell") == 8
    assert get_driver_overtaking("russell") == 8
    assert get_driver_quali_skill("russell") == 10
    assert get_driver_wet_skill("russell") == 8

    assert get_driver_tire_mgmt("hamilton") == 9
    assert get_driver_overtaking("leclerc") == 9
    assert get_driver_wet_skill("alonso") == 9

    # Existing full-name callers and Verstappen's already-canonical Jolpica ID
    # remain backward compatible.
    assert get_driver_quali_skill("george_russell") == 10
    assert get_driver_overtaking("max_verstappen") == 10


def test_live_stub_includes_latest_result_and_excludes_future_rows(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seed"
    model_rows_dir = tmp_path / "model_rows"
    seed_dir.mkdir()
    model_rows_dir.mkdir()

    (seed_dir / "drivers.json").write_text(json.dumps({
        "drivers": [
            {"driver_id": "RUS", "constructor_id": "mercedes"},
            {"driver_id": "VER", "constructor_id": "red_bull"},
        ]
    }), encoding="utf-8")
    (seed_dir / "driver_ids.json").write_text(json.dumps({
        "mappings": [
            {"abbrev": "RUS", "jolpica": "russell"},
            {"abbrev": "VER", "jolpica": "max_verstappen"},
        ]
    }), encoding="utf-8")
    (seed_dir / "races.json").write_text(json.dumps({
        "races": [
            {"round": 4, "name": "Belgian Grand Prix"},
        ]
    }), encoding="utf-8")

    rows = []
    results = {
        "russell": [(3, 3, 15), (2, 2, 18), (1, 1, 25)],
        "max_verstappen": [(6, 5, 10), (4, 4, 12), (5, 3, 15)],
    }
    constructors = {"russell": "mercedes", "max_verstappen": "red_bull"}
    circuits = ["albert_park", "shanghai", "suzuka"]
    for driver_id, driver_results in results.items():
        for round_num, (quali, finish, points) in enumerate(driver_results, start=1):
            rows.append({
                "season": 2026,
                "round": round_num,
                "driver_id": driver_id,
                "constructor_id": constructors[driver_id],
                "circuit_id": circuits[round_num - 1],
                "quali_position": float(quali),
                "finish_position": float(finish),
                "grid": float(quali),
                "points": float(points),
                "is_dnf": 0,
                "is_dns": 0,
                "is_dsq": 0,
                "is_classified": 1,
                "dnf_mechanical": 0,
                "dnf_collision": 0,
                "dnf_driver_error": 0,
                "sprint_grid": np.nan,
            })

    # A later row must not leak backward into the Round 4 reconstruction.
    rows.append({
        **rows[2],
        "round": 5,
        "quali_position": 20.0,
        "finish_position": 20.0,
        "grid": 20.0,
        "points": 0.0,
    })
    pd.DataFrame(rows).to_parquet(model_rows_dir / "all_model_rows.parquet", index=False)

    monkeypatch.setattr(predictions, "SEED_DIR", seed_dir)
    monkeypatch.setattr(predictions, "JOLPICA_MODEL_ROWS_DIR", model_rows_dir)

    live = predictions.build_live_priors(4, 2026).set_index("driver_id")

    # Round 4's shifted window must include all of R1-R3. The old copied-R3
    # fallback saw only R1-R2 and returned 2.5 here.
    assert live.loc["russell", "roll_finishpos_3"] == 2.0
    assert live.loc["russell", "roll_points_3"] == (15 + 18 + 25) / 3
    assert live.loc["russell", "driver_quali_last"] == 1.0

    assert live["sprint_grid"].isna().all()
    assert live["overtaking_difficulty"].eq(4).all()
    assert live["straight_line_importance"].eq(8).all()
    assert live.loc["russell", "quali_skill"] == 10
