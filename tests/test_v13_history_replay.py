from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from pipeline import replay_v13_history as replay


def source(time, **extra):
    return {"payload": {"round": 18, "phase": "post_fp", "generated_at": time, **extra}}


def test_replay_uses_latest_practice_forecast_and_rejects_after_lock_results():
    fp1 = source("2026-10-02T09:00:00Z", fp_sessions_included=["FP1"])
    fp3 = source("2026-10-03T07:00:00Z", fp_sessions_included=["FP1", "FP2", "FP3"])
    after_lock = source("2026-10-03T08:01:00Z")
    quali = source("2026-10-03T07:30:00Z", final_fix={"qualifying_locked": True})
    rebuilt = source("2026-10-03T07:59:00Z", reconstructed=True)
    lock = datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
    assert replay.choose_source([fp1, fp3, after_lock, quali, rebuilt], 18, lock) is fp3
    with pytest.raises(ValueError, match="no genuine pre-lock"):
        replay.choose_source([after_lock, quali, rebuilt], 18, lock)


def test_three_x_replay_uses_archived_future_benchmark_and_retains_chip_when_missing():
    data = SimpleNamespace(drivers=("A", "B", "C", "D", "E"), driver_projection=np.array([30, 20, 5, 1, 0]))
    normal = SimpleNamespace(drivers=data.drivers)
    horizon = {"sha256": "archived", "payload": {"rounds": {"19": {"round": 19, "drivers": {
        "A": {"expected_points": 35}, "B": {"expected_points": 20}}}}}}
    assert replay.three_x_choice(18, normal, data, horizon)[0] is None
    horizon["payload"]["rounds"]["19"]["drivers"]["A"]["expected_points"] = 25
    assert replay.three_x_choice(18, normal, data, horizon)[0] == "3x_boost"
    assert replay.three_x_choice(18, normal, data, None)[0] is None


def test_active_replay_reconciles_scores_budget_and_chips():
    if not replay.ACTIVE_PATH.exists():
        pytest.skip("No activated correction ledger in this fixture")
    pointer = replay.v13._load_json(replay.ACTIVE_PATH)
    ledger = replay.v13._load_json(replay.ROOT / pointer["path"])
    replay.validate_ledger(ledger)
    public = replay.build_corrected_payload()
    assert public["live_status"]["total_points"] == ledger["total_points"]
    assert public["current_state"]["budget"] == ledger["state"]["budget"]
    assert public["current_state"]["chips_used"] == ledger["chips_used"]
    for row in public["research_replay"]["rounds"] + public["live_history"]:
        decision = row["post_fp_final"]
        assert decision["projected_points"] == round(decision["projected_points_gross"] - decision["transfer_penalty"], 2)
