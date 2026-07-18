import json
from pathlib import Path

import pytest

from config.fantasy_prices import (
    FantasyPriceDataError,
    current_price_mismatches,
    resolve_fantasy_price_data,
)


ROOT = Path(__file__).resolve().parents[1]
PRICES_PATH = ROOT / "data" / "seed" / "fantasy_prices.json"


def test_current_prices_match_latest_history():
    """The live price lookup must stay in sync with the newest history row."""
    prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    latest_round = max(int(round_num) for round_num in prices["price_history"])
    latest = prices["price_history"][str(latest_round)]

    assert prices["price_after_round"] == latest_round

    for asset_type in ("drivers", "constructors"):
        current = prices[asset_type]
        historical = latest[asset_type]
        assert set(current) == set(historical)
        assert {
            asset_id: details["current_price"]
            for asset_id, details in current.items()
        } == historical


def _sample_prices() -> dict:
    return {
        "price_after_round": 10,
        "drivers": {
            "AAA": {"current_price": 1.0, "starting_price": 1.0},
            "BBB": {"current_price": 2.0, "starting_price": 2.0},
        },
        "constructors": {
            "team": {"current_price": 3.0, "starting_price": 3.0},
        },
        "price_history": {
            "9": {
                "drivers": {"AAA": 8.0, "BBB": 8.5},
                "constructors": {"team": 9.0},
            },
            "10": {
                "drivers": {"AAA": 10.0, "BBB": 10.5},
                "constructors": {"team": 11.0},
            },
        },
    }


def test_resolver_prefers_latest_numeric_history_key():
    prices = _sample_prices()

    assert current_price_mismatches(prices) == {
        "drivers": {"AAA": (1.0, 10.0), "BBB": (2.0, 10.5)},
        "constructors": {"team": (3.0, 11.0)},
    }

    resolved = resolve_fantasy_price_data(prices)

    assert resolved["drivers"]["AAA"]["current_price"] == 10.0
    assert resolved["drivers"]["BBB"]["current_price"] == 10.5
    assert resolved["constructors"]["team"]["current_price"] == 11.0
    assert prices["drivers"]["AAA"]["current_price"] == 1.0


def test_resolver_keeps_top_level_when_declared_round_is_newer():
    prices = _sample_prices()
    prices["price_after_round"] = 11

    with pytest.warns(RuntimeWarning, match="retaining the newer top-level prices"):
        resolved = resolve_fantasy_price_data(prices)

    assert resolved["drivers"]["AAA"]["current_price"] == 1.0
    assert resolved["constructors"]["team"]["current_price"] == 3.0


def test_resolver_rejects_incomplete_latest_snapshot():
    prices = _sample_prices()
    del prices["price_history"]["10"]["drivers"]["BBB"]

    with pytest.raises(FantasyPriceDataError, match="Incomplete drivers"):
        resolve_fantasy_price_data(prices)
