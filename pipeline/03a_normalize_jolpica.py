"""
Script 03a — Normalize Jolpica API JSON into clean CSVs.

Reads raw Jolpica/Ergast JSON (race results, qualifying, sprint, schedule)
and produces normalized CSV files per season.

Handles two raw data formats:
  - V1 (2020-2021): Single JSON per data type at year level, containing all rounds.
  - V2 (2022+):     Per-round JSON files under round{N}/ subdirectories.

Output directory: data/processed/jolpica/normalized/{year}/
  - races.csv
  - race_results.csv
  - qualifying_results.csv
  - sprint_results.csv

Usage:
    python pipeline/03a_normalize_jolpica.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    HISTORICAL_SEASONS,
    CURRENT_SEASON,
    JOLPICA_RAW_DIR,
    JOLPICA_NORMALIZED_DIR,
    SEED_DIR,
)

# Years that use V1 format (single file with all rounds)
V1_SEASONS = {2020, 2021}


# ---------------------------------------------------------------------------
# Seed-data loaders
# ---------------------------------------------------------------------------

def load_constructor_mapping(seed_dir: Path) -> dict[str, str]:
    """Build a lookup from any legacy Jolpica/Ergast constructor ID to canonical ID.

    Returns dict like {"alphatauri": "racing_bulls", "rb": "racing_bulls", ...}.
    """
    path = seed_dir / "driver_ids.json"
    if not path.exists():
        print(f"  [WARN] Constructor seed file not found: {path}")
        return {}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    mapping: dict[str, str] = {}
    for entry in data.get("constructor_mappings", []):
        canonical = entry["id"]
        # Map the primary jolpica id
        if "jolpica" in entry:
            mapping[entry["jolpica"]] = canonical
        # Map all ergast alternatives
        for alt in entry.get("ergast_alt", []):
            mapping[alt] = canonical
    return mapping


# ---------------------------------------------------------------------------
# JSON loading helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None if missing or malformed."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [WARN] Failed to read {path}: {exc}")
        return None


def _extract_races(data: dict) -> list[dict]:
    """Pull the Races list from a Jolpica MRData envelope."""
    try:
        return data["MRData"]["RaceTable"]["Races"]
    except (KeyError, TypeError):
        return []


def load_races_for_year(year: int, data_type: str) -> list[dict]:
    """Return a flat list of Race dicts for *data_type* across all rounds.

    data_type is one of: results, qualifying, sprint, races (schedule).
    """
    year_dir = JOLPICA_RAW_DIR / f"year{year}"

    if year in V1_SEASONS:
        # V1: single file at year level
        filename = f"{data_type}.json"
        data = _load_json(year_dir / filename)
        if data is None:
            return []
        return _extract_races(data)

    # V2: per-round files, or schedule.json at year level for "races"
    if data_type == "races":
        # Schedule lives at year level as schedule.json
        data = _load_json(year_dir / "schedule.json")
        if data is None:
            # Fallback: try races.json at year level (V1-style)
            data = _load_json(year_dir / "races.json")
        if data is None:
            return []
        return _extract_races(data)

    # Per-round data (results, qualifying, sprint)
    all_races: list[dict] = []
    if not year_dir.exists():
        return all_races

    round_dirs = sorted(
        (d for d in year_dir.iterdir() if d.is_dir() and d.name.startswith("round")),
        key=lambda d: int(d.name.replace("round", "")),
    )
    for rdir in round_dirs:
        fpath = rdir / f"{data_type}.json"
        data = _load_json(fpath)
        if data is None:
            continue
        races = _extract_races(data)
        all_races.extend(races)

    return all_races


# ---------------------------------------------------------------------------
# Canonicalization helpers
# ---------------------------------------------------------------------------

def canonicalize_constructor(raw_id: str, mapping: dict[str, str]) -> str:
    """Return the canonical constructor ID, falling back to the raw ID."""
    return mapping.get(raw_id, raw_id)


# ---------------------------------------------------------------------------
# Row extraction functions
# ---------------------------------------------------------------------------

def extract_race_rows(
    races: list[dict],
    sprint_rounds: set[int],
    year: int,
) -> list[dict]:
    """Extract race schedule rows."""
    rows: list[dict] = []
    for race in races:
        rnd = int(race.get("round", 0))
        rows.append({
            "season": year,
            "round": rnd,
            "race_name": race.get("raceName", ""),
            "race_date": race.get("date", ""),
            "circuit_id": race.get("Circuit", {}).get("circuitId", ""),
            "has_sprint": rnd in sprint_rounds,
        })
    return rows


def extract_race_result_rows(
    races: list[dict],
    quali_lookup: dict[tuple[int, str], str],
    constructor_map: dict[str, str],
    year: int,
) -> list[dict]:
    """Extract race result rows, merging qualifying position from quali data."""
    rows: list[dict] = []
    for race in races:
        rnd = int(race.get("round", 0))
        for res in race.get("Results", []):
            driver_id = res.get("Driver", {}).get("driverId", "")
            raw_constructor = res.get("Constructor", {}).get("constructorId", "")

            # Parse finish position — handle "R" (retired), "D" (disqualified), etc.
            pos_text = res.get("positionText", "")
            try:
                finish_pos = int(res.get("position", 0))
            except (ValueError, TypeError):
                finish_pos = None

            # Qualifying position from the lookup table
            quali_pos = quali_lookup.get((rnd, driver_id))

            rows.append({
                "season": year,
                "round": rnd,
                "driver_id": driver_id,
                "constructor_id": canonicalize_constructor(raw_constructor, constructor_map),
                "constructor_id_jolpica": raw_constructor,
                "grid": _safe_int(res.get("grid")),
                "finish_position": finish_pos,
                "position_text": pos_text,
                "points": _safe_float(res.get("points")),
                "status": res.get("status", ""),
                "laps_completed": _safe_int(res.get("laps")),
                "quali_position": _safe_int(quali_pos),
            })
    return rows


def extract_qualifying_rows(
    races: list[dict],
    constructor_map: dict[str, str],
    year: int,
) -> list[dict]:
    """Extract qualifying result rows."""
    rows: list[dict] = []
    for race in races:
        rnd = int(race.get("round", 0))
        for qr in race.get("QualifyingResults", []):
            driver_id = qr.get("Driver", {}).get("driverId", "")
            raw_constructor = qr.get("Constructor", {}).get("constructorId", "")
            rows.append({
                "season": year,
                "round": rnd,
                "driver_id": driver_id,
                "constructor_id": canonicalize_constructor(raw_constructor, constructor_map),
                "constructor_id_jolpica": raw_constructor,
                "quali_position": _safe_int(qr.get("position")),
                "q1": qr.get("Q1", ""),
                "q2": qr.get("Q2", ""),
                "q3": qr.get("Q3", ""),
            })
    return rows


def extract_sprint_rows(
    races: list[dict],
    constructor_map: dict[str, str],
    year: int,
) -> list[dict]:
    """Extract sprint result rows."""
    rows: list[dict] = []
    for race in races:
        rnd = int(race.get("round", 0))
        for sr in race.get("SprintResults", []):
            driver_id = sr.get("Driver", {}).get("driverId", "")
            raw_constructor = sr.get("Constructor", {}).get("constructorId", "")

            try:
                sprint_pos = int(sr.get("position", 0))
            except (ValueError, TypeError):
                sprint_pos = None

            rows.append({
                "season": year,
                "round": rnd,
                "driver_id": driver_id,
                "constructor_id": canonicalize_constructor(raw_constructor, constructor_map),
                "constructor_id_jolpica": raw_constructor,
                "sprint_position": sprint_pos,
                "sprint_points": _safe_float(sr.get("points")),
            })
    return rows


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_int(val) -> int | None:
    """Convert to int if possible, else None."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    """Convert to float if possible, else None."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _detect_sprint_rounds(schedule_races: list[dict]) -> set[int]:
    """Determine which rounds are sprint weekends from the schedule data."""
    sprint_rounds: set[int] = set()
    for race in schedule_races:
        if "Sprint" in race:
            sprint_rounds.add(int(race.get("round", 0)))
    return sprint_rounds


def _build_quali_lookup(quali_races: list[dict]) -> dict[tuple[int, str], str]:
    """Build a (round, driver_id) -> qualifying position lookup."""
    lookup: dict[tuple[int, str], str] = {}
    for race in quali_races:
        rnd = int(race.get("round", 0))
        for qr in race.get("QualifyingResults", []):
            driver_id = qr.get("Driver", {}).get("driverId", "")
            pos = qr.get("position", "")
            if driver_id and pos:
                lookup[(rnd, driver_id)] = pos
    return lookup


def save_csv(rows: list[dict], path: Path, label: str) -> None:
    """Save rows as a CSV, creating parent directories as needed."""
    if not rows:
        print(f"    {label}: 0 rows (skipped)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    print(f"    {label}: {len(df)} rows -> {path.name}")


# ---------------------------------------------------------------------------
# Per-year processing
# ---------------------------------------------------------------------------

def process_year(year: int, constructor_map: dict[str, str]) -> None:
    """Normalize all Jolpica data for a single season."""
    print(f"\n[{year}] Loading raw JSON...")

    out_dir = JOLPICA_NORMALIZED_DIR / str(year)

    # 1. Load schedule / race metadata
    schedule_races = load_races_for_year(year, "races")
    sprint_rounds = _detect_sprint_rounds(schedule_races)
    if sprint_rounds:
        print(f"  Sprint rounds detected: {sorted(sprint_rounds)}")

    # 2. Load qualifying (needed for race_results.csv quali_position column)
    quali_races = load_races_for_year(year, "qualifying")
    quali_lookup = _build_quali_lookup(quali_races)

    # 3. Load race results
    result_races = load_races_for_year(year, "results")

    # 4. Load sprint results
    sprint_races = load_races_for_year(year, "sprint")

    # --- Build rows ---
    race_rows = extract_race_rows(schedule_races, sprint_rounds, year)
    result_rows = extract_race_result_rows(result_races, quali_lookup, constructor_map, year)
    quali_rows = extract_qualifying_rows(quali_races, constructor_map, year)
    sprint_rows = extract_sprint_rows(sprint_races, constructor_map, year)

    # --- Save CSVs ---
    print(f"  Saving to {out_dir}/")
    save_csv(race_rows, out_dir / "races.csv", "races")
    save_csv(result_rows, out_dir / "race_results.csv", "race_results")
    save_csv(quali_rows, out_dir / "qualifying_results.csv", "qualifying_results")
    save_csv(sprint_rows, out_dir / "sprint_results.csv", "sprint_results")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("03a — Normalize Jolpica JSON -> CSV")
    print("=" * 60)

    all_seasons = HISTORICAL_SEASONS + [CURRENT_SEASON]
    print(f"Seasons to process: {all_seasons}")

    # Load constructor canonicalization mapping
    constructor_map = load_constructor_mapping(SEED_DIR)
    if constructor_map:
        print(f"Loaded {len(constructor_map)} constructor ID mappings from seed data.")
    else:
        print("[WARN] No constructor mappings loaded — raw IDs will be used as-is.")

    for year in all_seasons:
        process_year(year, constructor_map)

    print("\n" + "=" * 60)
    print("Done. Normalized CSVs written to:", JOLPICA_NORMALIZED_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
