"""
BoxBoxF1Fantasy — Global configuration settings.

All paths, constants, and feature/target column definitions live here.
"""

import os
from pathlib import Path

# -- Project root --------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# -- Season --------------------------------------------------------------------
CURRENT_SEASON: int = 2026
HISTORICAL_SEASONS: list[int] = [2020, 2021, 2022, 2023, 2024, 2025]

# 2026 has new regulations — weight recent data more heavily during training
REGULATION_CHANGE_YEAR: int = 2026
REGULATION_WEIGHT_MULTIPLIER: float = 2.5  # 2026 samples count 2.5× in training

# -- Data paths ----------------------------------------------------------------
DATA_DIR          = PROJECT_ROOT / "data"
RAW_DIR           = DATA_DIR / "raw"
FASTF1_RAW_DIR    = RAW_DIR / "fastf1"
JOLPICA_RAW_DIR   = RAW_DIR / "jolpica"
PROCESSED_DIR     = DATA_DIR / "processed"
LAPS_DIR          = PROCESSED_DIR / "laps"
FEATURES_DIR      = PROCESSED_DIR / "features"
MODEL_INPUTS_DIR  = PROCESSED_DIR / "model_inputs"
PREDICTIONS_DIR   = DATA_DIR / "predictions"
SEED_DIR          = DATA_DIR / "seed"

# -- Jolpica processed paths ---------------------------------------------------
JOLPICA_NORMALIZED_DIR = PROCESSED_DIR / "jolpica" / "normalized"
JOLPICA_MODEL_ROWS_DIR = PROCESSED_DIR / "jolpica" / "model_rows"

MODELS_DIR        = PROJECT_ROOT / "models"
TRAINED_DIR       = MODELS_DIR / "trained"
TRAINING_DATA_DIR = MODELS_DIR / "training_data"

WEB_DATA_DIR      = PROJECT_ROOT / "web" / "public" / "data"

# FastF1 cache (speeds up repeated downloads)
FASTF1_CACHE_DIR  = FASTF1_RAW_DIR / "cache"

# -- Jolpica API ---------------------------------------------------------------
JOLPICA_BASE_URL: str = "https://api.jolpi.ca/ergast/f1"

# -- Model settings ------------------------------------------------------------
MODEL_RANDOM_STATE: int = 42
MIN_LONG_RUN_LAPS: int = 5

# Algorithm for the RACE finish models (race_model + race_model_fp) ONLY.
# Quali and sprint stay XGBoost (CatBoost showed no quali gain and was worse on
# sprint in 97-fold walk-forward). "catboost" wins race -0.18 MAE (p=0.0001, all
# 5 yrs) and race_fp -0.10 MAE (CI excludes zero); see data/experiments/
# racefp_{xgb,cat}_my.json + catboost_recheck.json. 05_train_models.py trains and
# saves BOTH formats every run (race_model.{json,cbm}); 06 loads per this flag, so
# reverting is a one-line change back to "xgboost".
RACE_MODEL_ALGORITHM: str = "catboost"  # "catboost" | "xgboost"

# -- Sessions ------------------------------------------------------------------
ALL_SESSIONS: list[str] = ["FP1", "FP2", "FP3", "Qualifying", "Race", "Sprint", "Sprint Shootout"]
FP_SESSIONS: list[str] = ["FP1", "FP2", "FP3"]
SPRINT_FP_SESSIONS: list[str] = ["FP1"]  # Sprint weekends only have FP1

# -- Feature columns (produced by 03_extract_features.py) ----------------------
FEATURE_COLUMNS: list[str] = [
    # Pace metrics
    "avg_lap_time",
    "best_lap_time",
    "median_lap_time",
    "pace_rank",
    "best_3_lap_avg",
    "best_5_lap_avg",
    "best_10_lap_avg",
    "p50_to_p95_avg",
    # Consistency
    "lap_time_std",
    "lap_time_variance",
    # Degradation
    "degradation_rate",
    # Long run
    "long_run_avg",
    "long_run_rank",
    # Short run
    "short_run_best",
    # Sector pace
    "avg_sector_1",
    "avg_sector_2",
    "avg_sector_3",
    "best_sector_1",
    "best_sector_2",
    "best_sector_3",
]

# -- Target columns (used by 04 & 05) -----------------------------------------
TARGET_COLUMNS: list[str] = [
    "qualifying_position",
    "race_finish_position",
    "fantasy_points",
]

# -- Sprint weekends for 2026 --------------------------------------------------
SPRINT_ROUNDS_2026: list[int] = [2, 6, 7, 11, 14, 18]

# -- Cancelled rounds for 2026 ------------------------------------------------
CANCELLED_ROUNDS_2026: list[int] = [4, 5]


def fastf1_round(internal_round: int, year: int = CURRENT_SEASON) -> int:
    """Map internal round number → FastF1 round number.

    FastF1's calendar omits cancelled races entirely, so its round numbering
    skips them. Our internal `races.json` preserves original numbering. For
    any internal round, the FastF1 equivalent is internal − (count of
    cancelled rounds strictly before it).
    """
    if year != 2026:
        return internal_round
    skipped = sum(1 for r in CANCELLED_ROUNDS_2026 if r < internal_round)
    return internal_round - skipped


def is_race_completed(round_num: int, year: int = CURRENT_SEASON) -> bool:
    """Return True if the race date for the given round is in the past.

    Used by prediction scripts to refuse to overwrite archived predictions
    for races that have already happened (which would pollute the accuracy
    archive with hindsight). Reads race date from data/seed/races.json.

    Returns False if the round is not found, is cancelled, or has no date.
    """
    import json
    from datetime import datetime
    races_path = SEED_DIR / "races.json"
    if not races_path.exists():
        return False
    try:
        with open(races_path) as f:
            races = json.load(f).get("races", [])
    except Exception:
        return False
    for r in races:
        if r.get("round") != round_num:
            continue
        if r.get("cancelled"):
            return False
        date_str = r.get("date")
        if not date_str:
            return False
        try:
            race_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return False
        return race_date < datetime.now().date()
    return False


def race_name_for_round(round_num: int, year: int = CURRENT_SEASON) -> str:
    """Return the Grand Prix name for an internal round (from races.json).

    Returns '' if the round isn't found. Used to resolve a circuit_id via
    track_classifications.get_circuit_id_from_race_name() at predict/score time.
    """
    import json
    races_path = SEED_DIR / "races.json"
    if not races_path.exists():
        return ""
    try:
        with open(races_path) as f:
            races = json.load(f).get("races", [])
    except Exception:
        return ""
    for r in races:
        if r.get("round") == round_num:
            return r.get("name", "") or ""
    return ""


def load_dotd_overrides(round_num: int) -> dict:
    """Return manual Driver-of-the-Day probability overrides for a round.

    Reads data/seed/dotd_overrides.json — a judgment-call mechanism for fan-vote
    favourites the position heuristic can't see (e.g. a home hero near-certain to
    win DOTD). Returns {jolpica_driver_id: probability} for the given internal
    round, or {} if none. Both 07_calculate_fantasy.py (display %) and
    08_monte_carlo_fantasy.py (sim points) read this so they stay consistent.
    """
    import json
    path = SEED_DIR / "dotd_overrides.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return {}
    raw = data.get(str(round_num), {}) or {}
    out = {}
    for did, prob in raw.items():
        try:
            out[did] = max(0.0, min(1.0, float(prob)))
        except (TypeError, ValueError):
            continue
    return out


def load_dnf_causes(year: int = CURRENT_SEASON) -> dict:
    """Return manual DNF cause overrides, keyed {round:int -> {jolpica_id: cause}}.

    Jolpica AND FastF1 report every recent-season DNF as a generic "Retired"
    with no cause, so 2026 DNF causes are hand-curated in
    data/seed/dnf_causes_{year}.json. Causes: mechanical | collision |
    driver_error | other. The seed file is keyed by driver ABBREVIATION (LEC)
    for readability; this loader maps to the Jolpica id (leclerc) used by the
    pipeline. Empty/blank causes are skipped (fall back to generic handling).

    Consumed by 03b_build_jolpica_features.py to override `dnf_cause` for the
    current season before the per-cause rolling-rate features are computed.
    """
    import json
    path = SEED_DIR / f"dnf_causes_{year}.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return {}

    # abbrev -> jolpica id map
    abbrev_to_jolpica = {}
    ids_path = SEED_DIR / "driver_ids.json"
    if ids_path.exists():
        try:
            with open(ids_path) as f:
                for m in json.load(f).get("mappings", []):
                    abbrev_to_jolpica[m["abbrev"]] = m["jolpica"]
        except Exception:
            pass

    valid = {"mechanical", "collision", "driver_error", "other"}
    out: dict[int, dict] = {}
    for rnd_str, drivers in (data.get("causes", {}) or {}).items():
        try:
            rnd = int(rnd_str)
        except (TypeError, ValueError):
            continue
        for abbrev, cause in (drivers or {}).items():
            if not cause or cause not in valid:
                continue
            jid = abbrev_to_jolpica.get(abbrev, abbrev)
            out.setdefault(rnd, {})[jid] = cause
    return out

# -- Number of grid positions (11 teams × 2 drivers) --------------------------
GRID_SIZE: int = 22
NUM_CONSTRUCTORS: int = 11
