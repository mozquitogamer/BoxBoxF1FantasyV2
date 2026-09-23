import json

import pandas as pd

from config.driver_assets import (
    active_constructor_driver_assets,
    active_driver_assets,
    apply_active_asset_context,
)
from config.fantasy_prices import load_fantasy_price_maps
from config.settings import SEED_DIR


def test_r14_substitution_roster_is_round_scoped_and_constructor_correct():
    before = {row["asset_id"]: row for row in active_driver_assets(13)}
    r14 = {row["asset_id"]: row for row in active_driver_assets(14)}
    after = {row["asset_id"]: row for row in active_driver_assets(15)}

    assert {"HAD", "LAW"}.issubset(before)
    assert {"HAD", "LAW"}.isdisjoint(r14)
    assert {"HAD", "LAW"}.isdisjoint(after)
    assert {"LAW_RED_BULL", "TSU_RACING_BULLS"}.issubset(after)
    assert r14["LAW_RED_BULL"]["model_driver_id"] == "lawson"
    assert r14["LAW_RED_BULL"]["constructor_id"] == "red_bull"
    assert r14["TSU_RACING_BULLS"]["model_driver_id"] == "tsunoda"
    assert r14["TSU_RACING_BULLS"]["constructor_id"] == "racing_bulls"
    assert active_constructor_driver_assets(14)["red_bull"] == ["VER", "LAW_RED_BULL"]
    assert active_constructor_driver_assets(14)["racing_bulls"] == [
        "LIN",
        "TSU_RACING_BULLS",
    ]


def test_r14_prices_are_seat_scoped_without_changing_history():
    r13_drivers, _ = load_fantasy_price_maps(round_num=13)
    r14_drivers, _ = load_fantasy_price_maps(round_num=14)
    r15_drivers, _ = load_fantasy_price_maps(round_num=15)
    history = json.loads((SEED_DIR / "fantasy_prices.json").read_text(encoding="utf-8"))["price_history"]

    assert {"LAW", "HAD"}.issubset(r13_drivers)
    assert "LAW_RED_BULL" not in r13_drivers
    assert history["13"]["drivers"]["LAW"] == 10.3
    assert history["13"]["drivers"]["HAD"] == 14.5
    assert "LAW" not in r14_drivers
    assert "HAD" not in r14_drivers
    assert r14_drivers["LAW_RED_BULL"] == 14.3
    assert r14_drivers["TSU_RACING_BULLS"] == 9.7
    assert {"LAW_RED_BULL", "TSU_RACING_BULLS"}.issubset(r15_drivers)
    assert {"LAW", "HAD"}.isdisjoint(r15_drivers)


def test_asset_context_preserves_model_identity_and_marks_uncertainty():
    frame = pd.DataFrame(
        {"driver_id": ["lawson", "tsunoda", "max_verstappen"]}
    )
    mapped = apply_active_asset_context(frame, 14)

    lawson = mapped.loc[mapped["driver_id"] == "lawson"].iloc[0]
    tsunoda = mapped.loc[mapped["driver_id"] == "tsunoda"].iloc[0]
    assert lawson["model_driver_id"] == "lawson"
    assert lawson["asset_id"] == "LAW_RED_BULL"
    assert lawson["constructor_id"] == "red_bull"
    assert lawson["asset_confidence_multiplier"] < 1.0
    assert lawson["asset_mc_noise_multiplier"] > 1.0
    assert lawson["asset_legacy_ids"] == ["LAW"]
    assert tsunoda["model_driver_id"] == "tsunoda"
    assert tsunoda["asset_id"] == "TSU_RACING_BULLS"
    assert tsunoda["constructor_id"] == "racing_bulls"
    assert tsunoda["asset_legacy_ids"] == ["TSU"]


def test_r17_return_restores_seats_without_erasing_tsunoda_history():
    r16 = {row["asset_id"]: row for row in active_driver_assets(16)}
    r17 = {row["asset_id"]: row for row in active_driver_assets(17)}
    r18 = {row["asset_id"]: row for row in active_driver_assets(18)}
    assert {"LAW_RED_BULL", "TSU_RACING_BULLS"}.issubset(r16)
    assert {"LAW_RED_BULL", "TSU_RACING_BULLS"}.isdisjoint(r17)
    assert len(r17) == len(r18) == 22
    assert r17["HAD"]["constructor_id"] == "red_bull"
    assert r17["LAW"]["constructor_id"] == "racing_bulls"
    assert r17["HAD"]["model_driver_id"] == "hadjar"
    assert r17["LAW"]["model_driver_id"] == "lawson"
    assert r17["HAD"]["confidence_multiplier"] < 1
    assert r17["LAW"]["mc_noise_multiplier"] > 1
    assert active_constructor_driver_assets(17)["racing_bulls"] == ["LIN", "LAW"]

    r17_prices, _ = load_fantasy_price_maps(round_num=17)
    assert r17_prices["HAD"] == 14.5  # Confirmed live Fantasy price
    assert r17_prices["LAW"] == 9.7  # R16 Racing Bulls seat price
    assert "TSU_RACING_BULLS" not in r17_prices
    assert "LAW_RED_BULL" not in r17_prices
    historical = json.loads((SEED_DIR / "fantasy_prices.json").read_text(encoding="utf-8"))
    assert historical["price_history"]["16"]["driver_asset_prices"]["TSU_RACING_BULLS"] == 9.7

