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
    assert state["as_of_round"] == 14
    assert state["next_round"] == 15
    assert state["drivers"] == ["LEC", "HAM", "LIN", "BOR", "HUL"]
    assert state["constructors"] == ["mclaren", "ferrari"]
    assert state["budget"] == 127.0
    assert state["bank"] == 0.1
    assert state["free_transfers"] == 2
    assert state["chips_used"]["wild_card"] == 7
    assert state["chips_remaining"] == ["3x_boost"]

    live = payload["live_history"][-1]
    assert live["round"] == 14
    assert live["actual_points"] == 246.0
    assert live["projected_points"] == 221.6
    assert live["score_delta_vs_projection"] == 24.4
    assert live["cumulative_points"] == 2840.0
    assert state["early_thoughts"]["race"] == "Italian Grand Prix"
    assert state["early_thoughts"]["drivers"] == ["ANT", "HAM", "HUL", "LIN", "STR"]
    assert state["early_thoughts"]["constructors"] == ["mercedes", "ferrari"]
    assert state["early_thoughts"]["policy"]["policy_version"] == (
        "horizon_budget_value_v2"
    )


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


def test_live_price_gain_value_is_horizon_aware_and_calibrated() -> None:
    assert 4.4 < v13.live_price_gain_value(15) < 4.7
    assert v13.live_price_gain_value(24) == 0.0
    assert v13.live_price_gain_value(20) > v13.live_price_gain_value(23)


def test_live_monza_policy_no_longer_overvalues_price_growth() -> None:
    public = v13.build_payload()
    round_data = publish._round_input(15, "pre_fp")
    candidate = publish.season.choose_lineup(
        round_data=round_data,
        combos=publish.season.build_combo_matrices(round_data),
        state=publish._state(public),
        strategy=v13.V13_STRATEGY,
        chip=None,
        risk_profile=v13.V13_RISK_PROFILE,
        price_gain_value=v13.live_price_gain_value(15),
    )

    assert candidate.constructors == ("mercedes", "ferrari")
    assert candidate.projected_points == 210.2
    assert candidate.transfer_penalty == 10


def test_public_manager_distinguishes_live_policy_from_replay_policy() -> None:
    payload = v13.build_payload()

    assert payload["manager"]["policy_version"] == "2026.3"
    assert payload["manager"]["policy"]["price_gain_weight"] == 4.611
    assert payload["manager"]["policy"]["research_replay_price_gain_weight"] == 20.0
