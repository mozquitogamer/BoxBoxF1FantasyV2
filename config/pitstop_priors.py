"""Shared fallback pit stop distributions for predicted constructor points."""

import json

from config.settings import SEED_DIR


DEFAULT_PITSTOP_PRIORS = {
    "red_bull":       {"mean": 2.15, "std": 0.25, "stops_per_race": 1.5},
    "mclaren":        {"mean": 2.20, "std": 0.25, "stops_per_race": 1.5},
    "ferrari":        {"mean": 2.25, "std": 0.30, "stops_per_race": 1.5},
    "mercedes":       {"mean": 2.20, "std": 0.25, "stops_per_race": 1.5},
    "aston_martin":   {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5},
    "alpine":         {"mean": 2.40, "std": 0.35, "stops_per_race": 1.5},
    "williams":       {"mean": 2.45, "std": 0.35, "stops_per_race": 1.5},
    "racing_bulls":   {"mean": 2.30, "std": 0.30, "stops_per_race": 1.5},
    "haas":           {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5},
    "audi":           {"mean": 2.55, "std": 0.40, "stops_per_race": 1.5},
    "cadillac":       {"mean": 2.60, "std": 0.45, "stops_per_race": 1.5},
}

FALLBACK_PITSTOP_PRIOR = {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5}


def load_pitstop_priors() -> dict:
    """Load team distributions from seed data, falling back to 2026 defaults."""
    path = SEED_DIR / "pit_stop_priors.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return DEFAULT_PITSTOP_PRIORS
