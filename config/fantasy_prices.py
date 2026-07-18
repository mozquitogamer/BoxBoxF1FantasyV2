"""Canonical loading and validation for F1 Fantasy price data."""

from __future__ import annotations

import copy
import json
import warnings
from pathlib import Path
from typing import Any

from config.settings import SEED_DIR


class FantasyPriceDataError(ValueError):
    """Raised when a price snapshot cannot safely represent the full field."""


def _latest_history_entry(data: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    history = data.get("price_history") or {}
    if not history:
        return None

    keyed_rounds: list[tuple[int, str]] = []
    for key in history:
        try:
            keyed_rounds.append((int(key), key))
        except (TypeError, ValueError) as exc:
            raise FantasyPriceDataError(
                f"Invalid fantasy price-history round key: {key!r}"
            ) from exc

    latest_round, latest_key = max(keyed_rounds, key=lambda item: item[0])
    snapshot = history[latest_key]
    if not isinstance(snapshot, dict):
        raise FantasyPriceDataError(
            f"Fantasy price-history round {latest_round} is not an object"
        )
    return latest_round, snapshot


def current_price_mismatches(data: dict[str, Any]) -> dict[str, dict[str, tuple[Any, Any]]]:
    """Return top-level prices that differ from the applicable latest snapshot."""
    latest = _latest_history_entry(data)
    if latest is None:
        return {}

    latest_round, snapshot = latest
    declared_round = int(data.get("price_after_round", -1))
    if declared_round > latest_round:
        return {}

    mismatches: dict[str, dict[str, tuple[Any, Any]]] = {}
    for asset_type in ("drivers", "constructors"):
        current = data.get(asset_type) or {}
        historical = snapshot.get(asset_type) or {}
        group_mismatches: dict[str, tuple[Any, Any]] = {}
        for asset_id in sorted(set(current) | set(historical)):
            current_price = (current.get(asset_id) or {}).get("current_price")
            historical_price = historical.get(asset_id)
            if current_price != historical_price:
                group_mismatches[asset_id] = (current_price, historical_price)
        if group_mismatches:
            mismatches[asset_type] = group_mismatches
    return mismatches


def resolve_fantasy_price_data(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve live prices from the newest complete applicable history snapshot.

    The top-level ``current_price`` fields are convenient for consumers, while
    ``price_history`` is the round-by-round source of truth. If both describe
    the same (or a newer historical) round, the latest complete history entry
    wins. If the top-level declaration is newer than history, it is retained and
    a warning is emitted instead of rolling prices backwards.
    """
    resolved = copy.deepcopy(data)
    latest = _latest_history_entry(resolved)
    if latest is None:
        return resolved

    latest_round, snapshot = latest
    declared_round = int(resolved.get("price_after_round", -1))
    if declared_round > latest_round:
        warnings.warn(
            "fantasy_prices.json declares prices after round "
            f"{declared_round}, but price_history ends at round {latest_round}; "
            "retaining the newer top-level prices",
            RuntimeWarning,
            stacklevel=2,
        )
        return resolved

    for asset_type in ("drivers", "constructors"):
        current = resolved.get(asset_type) or {}
        historical = snapshot.get(asset_type) or {}
        current_ids = set(current)
        historical_ids = set(historical)
        if current_ids != historical_ids:
            missing = sorted(current_ids - historical_ids)
            unexpected = sorted(historical_ids - current_ids)
            raise FantasyPriceDataError(
                f"Incomplete {asset_type} price snapshot for round {latest_round}: "
                f"missing={missing}, unexpected={unexpected}"
            )
        for asset_id, current_entry in current.items():
            if not isinstance(current_entry, dict):
                raise FantasyPriceDataError(
                    f"Invalid top-level {asset_type} price entry for {asset_id}"
                )
            current_entry["current_price"] = float(historical[asset_id])

    resolved["price_after_round"] = latest_round
    return resolved


def load_fantasy_price_data(path: Path | None = None) -> dict[str, Any]:
    """Load fantasy prices with the latest complete history snapshot applied."""
    prices_path = path or (SEED_DIR / "fantasy_prices.json")
    if not prices_path.exists():
        return {}
    with prices_path.open(encoding="utf-8") as handle:
        return resolve_fantasy_price_data(json.load(handle))


def load_fantasy_price_maps(
    path: Path | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return current driver and constructor prices keyed by their IDs."""
    data = load_fantasy_price_data(path)
    driver_prices = {
        key: float(value["current_price"])
        for key, value in data.get("drivers", {}).items()
    }
    constructor_prices = {
        key: float(value["current_price"])
        for key, value in data.get("constructors", {}).items()
    }
    return driver_prices, constructor_prices
