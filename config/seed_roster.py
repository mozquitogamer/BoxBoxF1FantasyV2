"""Canonical season roster lookups, without round-specific seat replacements."""

import json

from config.settings import SEED_DIR


def load_seed_driver_map() -> dict[str, dict]:
    """Return seed drivers keyed by their canonical Fantasy driver ID."""
    with (SEED_DIR / "drivers.json").open(encoding="utf-8") as handle:
        drivers = json.load(handle)["drivers"]
    return {driver["driver_id"]: driver for driver in drivers}


def load_seed_constructor_map() -> dict[str, dict]:
    """Return seed constructors keyed by constructor ID."""
    with (SEED_DIR / "constructors.json").open(encoding="utf-8") as handle:
        constructors = json.load(handle)["constructors"]
    return {constructor["constructor_id"]: constructor for constructor in constructors}
