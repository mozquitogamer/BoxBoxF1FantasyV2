"""Round-scoped F1 Fantasy driver assets and seat-context helpers.

The prediction models identify a driver's personal history with a Jolpica
``model_driver_id`` (for example ``lawson``).  Fantasy, however, sells a seat
asset.  Those are normally one-to-one, but a mid-season substitution can make
the same person/seat identity ambiguous.  This module keeps the historical
seed roster unchanged and resolves a target round into the active fantasy
assets that should be shown and scored.

The post-R14 roster is deliberately represented with internal seat IDs because
the public F1 Fantasy page/feed did not expose stable replacement asset IDs
when this correction was made. The IDs are deterministic and are not aliases
for the historical ``LAW`` asset. A future official-feed refresh can replace
them without rewriting R1-R13 archives.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import CURRENT_SEASON, SEED_DIR


# Public source note kept close to the fallback so the provenance cannot be
# mistaken for an official game asset ID.  Accessed 2026-08-20 UTC.
OFFICIAL_ROSTER_SOURCE = {
    "url": "https://www.formula1.com/en/drivers",
    "accessed_at": "2026-08-20",
    "result": (
        "The public F1 driver page still listed Hadjar/Red Bull and Lawson/"
        "Racing Bulls; the JavaScript F1 Fantasy page/feed was not readable in "
        "the restricted runtime. R14 therefore uses deterministic internal IDs."
    ),
    "fantasy_feed_url": "https://fantasy.formula1.com/feeds/drivers/14_en.json",
    "fantasy_feed_result": "unavailable_in_restricted_runtime",
}


# Deliberately not added to data/seed/drivers.json: that file is the canonical
# season/history roster and changing it would contaminate R1-R13 joins. These
# are the active post-R14 seat assets with a personal model identity underneath.
POST_R14_SUBSTITUTION_ASSETS: tuple[dict[str, Any], ...] = (
    {
        "asset_id": "LAW_RED_BULL",
        "driver_abbrev": "LAW_RED_BULL",
        "model_driver_id": "lawson",
        "constructor_id": "red_bull",
        "first_name": "Liam",
        "last_name": "Lawson",
        "number": 30,
        "price": 14.3,
        "starting_price": 14.3,
        "availability": {"from_round": 14, "to_round": None},
        "legacy_asset_ids": ["LAW"],
        # Applying a constructor change to a driver's model prior is useful,
        # but the seat has no same-weekend evidence before FP1.  These fields
        # are consumed by 06/08 to lower confidence and widen MC intervals.
        "confidence_multiplier": 0.68,
        "mc_noise_multiplier": 1.35,
        "asset_context": "substitute_personal_prior_new_constructor",
    },
    {
        "asset_id": "TSU_RACING_BULLS",
        "driver_abbrev": "TSU_RACING_BULLS",
        "model_driver_id": "tsunoda",
        "constructor_id": "racing_bulls",
        "first_name": "Yuki",
        "last_name": "Tsunoda",
        "number": 22,
        "price": 9.7,
        "starting_price": 9.7,
        "availability": {"from_round": 14, "to_round": None},
        "legacy_asset_ids": ["TSU"],
        "confidence_multiplier": 0.68,
        "mc_noise_multiplier": 1.35,
        "asset_context": "substitute_personal_prior_new_constructor",
    },
)


def _load_seed_drivers() -> list[dict[str, Any]]:
    with (SEED_DIR / "drivers.json").open(encoding="utf-8") as handle:
        return json.load(handle)["drivers"]


def _load_driver_id_map() -> dict[str, str]:
    path = SEED_DIR / "driver_ids.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        str(row.get("abbrev", "")): str(row.get("jolpica", ""))
        for row in data.get("mappings", [])
        if row.get("abbrev") and row.get("jolpica")
    }


def _base_assets() -> list[dict[str, Any]]:
    abbrev_to_model = _load_driver_id_map()
    assets: list[dict[str, Any]] = []
    for driver in _load_seed_drivers():
        row = copy.deepcopy(driver)
        abbrev = str(driver["driver_id"])
        row.update(
            {
                "asset_id": abbrev,
                "driver_abbrev": abbrev,
                "model_driver_id": abbrev_to_model.get(abbrev, abbrev.lower()),
                "confidence_multiplier": 1.0,
                "mc_noise_multiplier": 1.0,
                "asset_context": "canonical_season_asset",
                "availability": {"from_round": 1, "to_round": None},
                "legacy_asset_ids": [],
            }
        )
        assets.append(row)
    return assets


def active_driver_assets(
    round_num: int,
    year: int = CURRENT_SEASON,
) -> list[dict[str, Any]]:
    """Return the active fantasy driver assets for ``round_num``.

    The default is a copy of the historical 22-driver seed roster. From R14,
    the active roster replaces Hadjar and the old Racing Bulls Lawson asset:
    Lawson is re-seated at Red Bull and Tsunoda is introduced at Racing Bulls.
    """
    assets = _base_assets()
    if year != 2026 or int(round_num) < 14:
        return assets

    inactive = {"HAD", "LAW"}
    assets = [row for row in assets if row["asset_id"] not in inactive]
    assets.extend(copy.deepcopy(row) for row in POST_R14_SUBSTITUTION_ASSETS)
    if len(assets) != 22:
        raise ValueError(f"R{round_num} active driver roster must contain 22 assets, got {len(assets)}")
    if len({row["asset_id"] for row in assets}) != len(assets):
        raise ValueError(f"R{round_num} active driver roster contains duplicate asset IDs")
    return assets


def active_driver_asset_map(round_num: int, year: int = CURRENT_SEASON) -> dict[str, dict[str, Any]]:
    """Return active assets keyed by their personal/model driver ID."""
    result: dict[str, dict[str, Any]] = {}
    for asset in active_driver_assets(round_num, year):
        model_id = str(asset["model_driver_id"])
        if model_id in result:
            raise ValueError(
                f"R{round_num} has multiple active assets for model driver {model_id!r}"
            )
        result[model_id] = asset
    return result


def active_constructor_driver_assets(
    round_num: int,
    year: int = CURRENT_SEASON,
) -> dict[str, list[str]]:
    """Return constructor -> active fantasy asset IDs for a round."""
    grouped: dict[str, list[str]] = {}
    for asset in active_driver_assets(round_num, year):
        grouped.setdefault(str(asset["constructor_id"]), []).append(str(asset["asset_id"]))
    return grouped


def asset_metadata_for_model_driver(
    model_driver_id: str,
    round_num: int,
    year: int = CURRENT_SEASON,
) -> dict[str, Any] | None:
    """Resolve one model identity to its active seat asset."""
    return active_driver_asset_map(round_num, year).get(str(model_driver_id))


def apply_active_asset_context(
    frame: pd.DataFrame,
    round_num: int,
    year: int = CURRENT_SEASON,
) -> pd.DataFrame:
    """Attach seat identity/context while preserving model-driver priors.

    ``driver_id`` remains the Jolpica/model ID so rolling priors, FP joins,
    overtake history, DNF history, and weather ratings continue to resolve to
    the person's historical record.  ``asset_id``/``driver_abbrev`` are the
    round-scoped Fantasy keys used for prices, constructors, and website picks.
    """
    out = frame.copy()
    if "driver_id" not in out.columns:
        raise KeyError("driver frame must contain driver_id before seat mapping")
    mapping = active_driver_asset_map(round_num, year)
    model_ids = out["driver_id"].astype(str)
    assets = [mapping.get(model_id) for model_id in model_ids]
    missing = sorted({model_id for model_id, asset in zip(model_ids, assets) if asset is None})
    if missing:
        raise ValueError(f"R{round_num} prediction contains inactive/unmapped model drivers: {missing}")

    out["model_driver_id"] = model_ids.values
    out["asset_id"] = [asset["asset_id"] for asset in assets]
    out["driver_abbrev"] = [asset["driver_abbrev"] for asset in assets]
    out["constructor_id"] = [asset["constructor_id"] for asset in assets]
    out["asset_confidence_multiplier"] = [float(asset.get("confidence_multiplier", 1.0)) for asset in assets]
    out["asset_mc_noise_multiplier"] = [float(asset.get("mc_noise_multiplier", 1.0)) for asset in assets]
    out["asset_context"] = [asset.get("asset_context", "") for asset in assets]
    out["asset_legacy_ids"] = [list(asset.get("legacy_asset_ids", [])) for asset in assets]
    out["driver_name"] = [
        f"{asset.get('first_name', '')} {asset.get('last_name', '')}".strip()
        for asset in assets
    ]
    out["driver_number"] = [asset.get("number", 0) for asset in assets]
    return out


def active_price_overrides(
    round_num: int,
    year: int = CURRENT_SEASON,
) -> dict[str, dict[str, Any]]:
    """Return round-scoped driver price entries keyed by active asset ID."""
    if year != 2026 or int(round_num) < 14:
        return {}
    return {
        asset["asset_id"]: {
            "current_price": float(asset["price"]),
            "starting_price": float(asset.get("starting_price", asset["price"])),
            "model_driver_id": asset["model_driver_id"],
            "availability": copy.deepcopy(asset["availability"]),
            "legacy_asset_ids": list(asset.get("legacy_asset_ids", [])),
        }
        for asset in POST_R14_SUBSTITUTION_ASSETS
    }


def roster_provenance(round_num: int, year: int = CURRENT_SEASON) -> dict[str, Any]:
    """Metadata suitable for prediction/website sidecars and audit logs."""
    is_override = year == 2026 and int(round_num) >= 14
    return {
        "round": int(round_num),
        "year": int(year),
        "override_active": bool(is_override),
        "source": copy.deepcopy(OFFICIAL_ROSTER_SOURCE if is_override else {"result": "canonical_seed_roster"}),
        "active_assets": [
            {
                "asset_id": asset["asset_id"],
                "model_driver_id": asset["model_driver_id"],
                "constructor_id": asset["constructor_id"],
                "availability": copy.deepcopy(asset.get("availability")),
                "asset_context": asset.get("asset_context"),
            }
            for asset in active_driver_assets(round_num, year)
        ],
    }

