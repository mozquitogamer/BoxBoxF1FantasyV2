import copy

import pytest

from pipeline import build_v13_manager as v13


def test_settlement_does_not_revalue_history_with_newer_prices(monkeypatch):
    original_load = v13._load_json
    prices = original_load(v13.SEED_DIR / "fantasy_prices.json")
    expected = v13._price_after_round(14)
    changed = copy.deepcopy(prices)
    changed["price_history"]["99"] = {
        "drivers": {key: 999 for key in prices["drivers"]},
        "constructors": {key: 999 for key in prices["constructors"]},
    }
    monkeypatch.setattr(v13, "_load_json", lambda path: changed)
    assert v13._price_after_round(14) == expected
    assert expected["drivers"]["ANT"] == 26.0
    assert expected["drivers"]["TSU_RACING_BULLS"] == 9.7
    assert v13._price_after_round(15)["drivers"]["TSU_RACING_BULLS"] == 9.9


def test_missing_closing_snapshot_fails_instead_of_using_latest(monkeypatch):
    monkeypatch.setattr(v13, "_load_json", lambda path: {"price_history": {}})
    with pytest.raises(ValueError, match="Missing closing price snapshot"):
        v13._price_after_round(15)


def test_monza_budget_and_madrid_affordability():
    payload = v13.build_payload()
    history = {row["round"]: row for row in payload["live_history"]}
    assert history[14]["budget_after"] == 127.0
    assert history[15]["budget_after"] == 129.2
    assert history[15]["actual_points"] == 358.0
    state = payload["current_state"]
    assert state["bank"] == 0.4
    assert state["budget"] == 129.2
    assert state["early_thoughts"]["team_cost"] <= state["budget"]


def test_missing_held_asset_price_stops_settlement(monkeypatch):
    original = v13._price_after_round

    def without_antonelli(round_num):
        prices = original(round_num)
        if round_num == 15:
            prices["drivers"].pop("ANT")
        return prices

    monkeypatch.setattr(v13, "_price_after_round", without_antonelli)
    with pytest.raises(ValueError, match="closing price for ANT"):
        v13.build_payload()


def test_over_budget_locked_team_stops_settlement(monkeypatch):
    original = v13._live_decision

    def too_expensive(round_num, phase):
        decision = original(round_num, phase)
        if round_num == 15 and phase == "post_fp":
            decision = dict(decision, team_cost=999)
        return decision

    monkeypatch.setattr(v13, "_live_decision", too_expensive)
    with pytest.raises(ValueError, match="locked team exceeds its budget"):
        v13.build_payload()
