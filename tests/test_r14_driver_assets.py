import pandas as pd

from config.driver_assets import (
    active_constructor_driver_assets,
    active_driver_assets,
    apply_active_asset_context,
)
from config.fantasy_prices import load_fantasy_price_maps


def test_r14_substitution_roster_is_round_scoped_and_constructor_correct():
    before = {row["asset_id"]: row for row in active_driver_assets(13)}
    r14 = {row["asset_id"]: row for row in active_driver_assets(14)}
    after = {row["asset_id"]: row for row in active_driver_assets(15)}

    assert {"HAD", "LAW"}.issubset(before)
    assert {"HAD", "LAW"}.issubset(after)
    assert {"HAD", "LAW"}.isdisjoint(r14)
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

    assert r13_drivers["LAW"] == 10.3
    assert r13_drivers["HAD"] == 14.5
    assert "LAW" not in r14_drivers
    assert "HAD" not in r14_drivers
    assert r14_drivers["LAW_RED_BULL"] == 14.5
    assert r14_drivers["TSU_RACING_BULLS"] == 10.3
    assert r15_drivers["LAW"] == 10.3
    assert r15_drivers["HAD"] == 14.5


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

