from datetime import datetime

from pipeline import build_v13_manager as v13
from pipeline import publish_v13_decision as publish


def test_v13_replay_preserves_full_season_score_and_provenance() -> None:
    payload = v13.build_payload()
    replay = payload["research_replay"]

    assert replay["base_points_before_final_fix"] == 2572.0
    assert replay["final_fix_adjustment"] == 22.0
    assert replay["total_points"] == 2594.0
    assert replay["final_budget"] == 125.3

    rounds = replay["rounds"]
    assert [row["round"] for row in rounds] == [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13]
    assert all(row["post_fp_final"]["phase"] == "post_fp" for row in rounds)
    assert all(len(row["post_fp_final"]["archive_sha256"]) == 64 for row in rounds)
    assert [row["provenance"] for row in rounds[:3]] == ["reconstructed"] * 3


def test_v13_uses_only_qualifying_locked_data_for_final_fix() -> None:
    payload = v13.build_payload()
    round_13 = payload["research_replay"]["rounds"][-1]
    final_fix = round_13["final_fix"]

    assert final_fix["phase"] == "post_quali"
    assert final_fix["points_basis"] == "projected_points_race"
    assert final_fix["outgoing"] == "HAM"
    assert final_fix["incoming"] == "NOR"
    assert final_fix["actual_gain"] == 22.0
    assert round_13["actual_points"] == 223.0
    assert round_13["cumulative_points"] == 2594.0

    state = payload["current_state"]
    assert "NOR" in state["drivers"]
    assert "HAM" not in state["drivers"]
    assert state["bank"] == 1.3
    assert state["free_transfers"] == 2
    assert state["chips_used"]["wild_card"] == 7
    assert state["chips_remaining"] == ["3x_boost"]


def test_r14_early_thoughts_are_frozen_from_a_pre_lock_archive() -> None:
    decision = v13._live_decision(14, "pre_fp")

    assert decision["phase"] == "pre_fp"
    assert decision["status"] == "corrected_provisional"
    assert decision["revision"] == 6
    assert "Sprint start" in decision["correction_reason"]
    assert decision["lock_deadline"] == "2026-08-22T10:00:00Z"
    assert datetime.fromisoformat(decision["source_generated_at"]) < datetime.fromisoformat(
        decision["lock_deadline"].replace("Z", "+00:00")
    )
    assert v13._sha256(v13.ROOT / decision["archive"]) == decision["archive_sha256"]
    assert "HAD" not in decision["drivers"]
    assert "LAW" not in decision["drivers"]
    assert set(decision["drivers"]).issubset(
        {row["asset_id"] for row in v13.active_driver_assets(14)}
    )
    assert {"HAD", "LAW"}.issubset(decision["changes"]["drivers_out"])
    assert not {"HAD", "LAW"}.intersection(decision["drivers"])
    assert decision["transfers"] == 3
    assert decision["transfer_penalty"] == 10


def test_publishing_an_existing_decision_is_idempotent() -> None:
    path = v13.DECISION_DIR / "round14_pre_fp.json"
    before = path.read_bytes()
    decision = publish.publish(14, "pre_fp")

    assert path.read_bytes() == before
    assert decision["archive_sha256"] == v13._sha256(v13.ROOT / decision["archive"])
