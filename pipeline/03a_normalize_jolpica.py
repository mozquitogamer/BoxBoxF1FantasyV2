"""
03a_normalize_jolpica.py — Normalize raw Jolpica JSON into clean CSVs.

Reads per-round JSON files (results.json, qualifying.json, sprint.json)
from data/raw/jolpica/year{YYYY}/round{N}/ and produces consolidated CSVs
in data/processed/jolpica/normalized/{year}/.

Output files:
  - race_results.csv
  - qualifying_results.csv
  - sprint_results.csv (only if sprint data exists)

Usage:
    python pipeline/03a_normalize_jolpica.py --year 2022
    python pipeline/03a_normalize_jolpica.py --all
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    JOLPICA_RAW_DIR,
    JOLPICA_NORMALIZED_DIR,
    HISTORICAL_SEASONS,
    CURRENT_SEASON,
    SEED_DIR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON file and return its contents."""
    return json.loads(path.read_text(encoding="utf-8"))


def safe_get(d: Dict[str, Any], keys: List[str], default=None):
    """Safely navigate nested dicts."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def safe_int(val) -> Any:
    """Convert to int if the string is all digits, else None."""
    if val is None:
        return None
    s = str(val).strip()
    if s.isdigit():
        return int(s)
    return None


def safe_float(val) -> Any:
    """Convert to float if possible, else None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to CSV, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


# ---------------------------------------------------------------------------
# Driver abbrev and constructor mappings from seed data
# ---------------------------------------------------------------------------

def load_driver_abbrev_map(seed_dir: Path) -> Dict[str, str]:
    """
    Build jolpica driverId -> abbrev mapping from driver_ids.json.
    e.g. {"max_verstappen": "VER", "leclerc": "LEC", ...}
    """
    path = seed_dir / "driver_ids.json"
    if not path.exists():
        print(f"[WARN] Missing {path}, abbrev column will be empty.")
        return {}

    obj = json.loads(path.read_text(encoding="utf-8"))
    mappings = obj.get("mappings", [])
    result: Dict[str, str] = {}
    for row in mappings:
        jolpica_id = str(row.get("jolpica", "")).strip().lower()
        abbrev = str(row.get("abbrev", "")).strip().upper()
        if jolpica_id and abbrev:
            result[jolpica_id] = abbrev
    return result


def load_constructor_map(seed_dir: Path) -> Dict[str, str]:
    """
    Build a mapping of legacy/raw constructor IDs to canonical IDs.
    e.g. {"alphatauri": "racing_bulls", "rb": "racing_bulls",
           "sauber": "audi", "alfa": "audi", "toro_rosso": "racing_bulls"}
    Only entries where the alt differs from the canonical ID are included.
    """
    path = seed_dir / "driver_ids.json"
    if not path.exists():
        print(f"[WARN] Missing {path}, constructor mapping will be identity.")
        return {}

    obj = json.loads(path.read_text(encoding="utf-8"))
    raw_to_canonical: Dict[str, str] = {}
    for entry in obj.get("constructor_mappings", []):
        canonical_id = entry.get("id", "").strip().lower()
        if not canonical_id:
            continue
        # Map the jolpica key
        jolpica_id = entry.get("jolpica", "").strip().lower()
        if jolpica_id and jolpica_id != canonical_id:
            raw_to_canonical[jolpica_id] = canonical_id
        # Map all ergast_alt keys
        for alt in entry.get("ergast_alt", []):
            alt_lower = alt.strip().lower()
            if alt_lower and alt_lower != canonical_id:
                raw_to_canonical[alt_lower] = canonical_id
    return raw_to_canonical


def add_abbrev_column(df: pd.DataFrame, abbrev_map: Dict[str, str]) -> pd.DataFrame:
    """Add an 'abbrev' column from the driver_id -> abbrev mapping."""
    if df is None or len(df) == 0 or "driver_id" not in df.columns:
        return df
    df = df.copy()
    df["abbrev"] = df["driver_id"].map(
        lambda x: abbrev_map.get(str(x).strip().lower(), "") if pd.notna(x) else ""
    )
    return df


def canonicalize_constructors(df: pd.DataFrame, cmap: Dict[str, str]) -> pd.DataFrame:
    """Canonicalize the constructor_id column in-place."""
    if df is None or len(df) == 0 or "constructor_id" not in df.columns:
        return df
    df = df.copy()
    df["constructor_id"] = df["constructor_id"].map(
        lambda x: cmap.get(str(x).strip().lower(), str(x).strip().lower()) if pd.notna(x) else x
    )
    return df


# ---------------------------------------------------------------------------
# Per-round JSON parsers
# ---------------------------------------------------------------------------

def _extract_race_meta(race_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Extract common race-level metadata from a Jolpica Race object."""
    circuit = race_obj.get("Circuit", {}) or {}
    return {
        "season": int(race_obj["season"]) if race_obj.get("season") else None,
        "round": int(race_obj["round"]) if race_obj.get("round") else None,
        "race_name": race_obj.get("raceName"),
        "race_date": race_obj.get("date"),
        "circuit_id": circuit.get("circuitId"),
    }


def parse_round_results(results_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse a single round's results.json into a list of row dicts."""
    races = safe_get(results_json, ["MRData", "RaceTable", "Races"], []) or []
    rows: List[Dict[str, Any]] = []
    for r in races:
        meta = _extract_race_meta(r)
        for res in (r.get("Results") or []):
            drv = res.get("Driver", {}) or {}
            con = res.get("Constructor", {}) or {}
            fl = res.get("FastestLap", {}) or {}
            fl_time_obj = fl.get("Time")
            fl_time = fl_time_obj.get("time") if isinstance(fl_time_obj, dict) else None

            rows.append({
                **meta,
                "driver_id": drv.get("driverId"),
                "driver_code": drv.get("code"),
                "constructor_id": con.get("constructorId"),
                "grid": safe_int(res.get("grid")),
                "finish_position": safe_int(res.get("position")),
                "position_text": res.get("positionText"),
                "points": safe_float(res.get("points")),
                "laps_completed": safe_int(res.get("laps")),
                "status": res.get("status"),
                "fastest_lap_rank": safe_int(fl.get("rank")),
                "fastest_lap_time": fl_time,
            })
    return rows


def parse_round_qualifying(qual_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse a single round's qualifying.json into a list of row dicts."""
    races = safe_get(qual_json, ["MRData", "RaceTable", "Races"], []) or []
    rows: List[Dict[str, Any]] = []
    for r in races:
        meta = _extract_race_meta(r)
        for q in (r.get("QualifyingResults") or []):
            drv = q.get("Driver", {}) or {}
            con = q.get("Constructor", {}) or {}
            rows.append({
                **meta,
                "driver_id": drv.get("driverId"),
                "driver_code": drv.get("code"),
                "constructor_id": con.get("constructorId"),
                "quali_position": safe_int(q.get("position")),
                "q1": q.get("Q1"),
                "q2": q.get("Q2"),
                "q3": q.get("Q3"),
            })
    return rows


def parse_round_sprint(sprint_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse a single round's sprint.json into a list of row dicts."""
    races = safe_get(sprint_json, ["MRData", "RaceTable", "Races"], []) or []
    rows: List[Dict[str, Any]] = []
    for r in races:
        meta = _extract_race_meta(r)
        for s in (r.get("SprintResults") or []):
            drv = s.get("Driver", {}) or {}
            con = s.get("Constructor", {}) or {}
            rows.append({
                **meta,
                "driver_id": drv.get("driverId"),
                "driver_code": drv.get("code"),
                "constructor_id": con.get("constructorId"),
                "grid": safe_int(s.get("grid")),
                "sprint_position": safe_int(s.get("position")),
                "points": safe_float(s.get("points")),
                "laps_completed": safe_int(s.get("laps")),
                "status": s.get("status"),
            })
    return rows


# ---------------------------------------------------------------------------
# Round directory discovery
# ---------------------------------------------------------------------------

def discover_round_dirs(year_dir: Path) -> List[Path]:
    """Return sorted list of round directories (round1, round2, ...) in year_dir."""
    round_dirs: List[Path] = []
    if not year_dir.is_dir():
        return round_dirs
    for child in year_dir.iterdir():
        if child.is_dir() and re.match(r"^round\d+$", child.name):
            round_dirs.append(child)
    round_dirs.sort(key=lambda p: int(re.search(r"\d+", p.name).group()))
    return round_dirs


# ---------------------------------------------------------------------------
# Per-year processing
# ---------------------------------------------------------------------------

RACE_RESULT_COLUMNS = [
    "season", "round", "race_name", "race_date", "circuit_id",
    "driver_id", "abbrev", "driver_code", "constructor_id",
    "grid", "finish_position", "position_text", "points",
    "laps_completed", "status", "fastest_lap_rank", "fastest_lap_time",
]

QUALIFYING_COLUMNS = [
    "season", "round", "race_name", "race_date", "circuit_id",
    "driver_id", "abbrev", "driver_code", "constructor_id",
    "quali_position", "q1", "q2", "q3",
]

SPRINT_COLUMNS = [
    "season", "round", "race_name", "race_date", "circuit_id",
    "driver_id", "abbrev", "driver_code", "constructor_id",
    "grid", "sprint_position", "points", "laps_completed", "status",
]


def process_year(
    year: int,
    jolpica_raw_dir: Path,
    normalized_dir: Path,
    abbrev_map: Dict[str, str],
    constructor_map: Dict[str, str],
) -> None:
    """Process all rounds for a given year and write consolidated CSVs."""
    year_dir = jolpica_raw_dir / f"year{year}"
    out_dir = normalized_dir / str(year)

    if not year_dir.exists():
        print(f"[WARN] Year directory not found: {year_dir}")
        return

    round_dirs = discover_round_dirs(year_dir)

    print(f"\n{'='*60}")

    # Collect rows from all rounds
    all_results: List[Dict[str, Any]] = []
    all_qualifying: List[Dict[str, Any]] = []
    all_sprint: List[Dict[str, Any]] = []

    if round_dirs:
        # Per-round format (2022+): data/raw/jolpica/year{YYYY}/round{N}/results.json
        print(f"Processing year {year}: {len(round_dirs)} round directories")
        print(f"{'='*60}")

        for rdir in round_dirs:
            rnd_num = int(re.search(r"\d+", rdir.name).group())

            # IMPORTANT: Jolpica's JSON response uses compressed numbering that
            # skips cancelled rounds — e.g. Miami arrives labeled "round 4" even
            # though it's our internal R6 (because R4 Bahrain and R5 Saudi were
            # cancelled). We override the round field on every parsed row with
            # the internal round number derived from the directory name. This is
            # the source of truth — `data/raw/jolpica/year{Y}/round{N}/` is
            # always our internal numbering. Without this override, the model
            # rows for Miami silently overwrite the cancelled-Bahrain slot and
            # later rounds disappear entirely.
            def _stamp_round(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
                for r in rows:
                    r["round"] = rnd_num
                return rows

            results_path = rdir / "results.json"
            if results_path.exists():
                all_results.extend(_stamp_round(parse_round_results(read_json(results_path))))
            else:
                print(f"  [WARN] Missing results.json for round {rnd_num}")

            qual_path = rdir / "qualifying.json"
            if qual_path.exists():
                all_qualifying.extend(_stamp_round(parse_round_qualifying(read_json(qual_path))))
            else:
                print(f"  [WARN] Missing qualifying.json for round {rnd_num}")

            sprint_path = rdir / "sprint.json"
            if sprint_path.exists():
                sprint_rows = _stamp_round(parse_round_sprint(read_json(sprint_path)))
                if sprint_rows:
                    all_sprint.extend(sprint_rows)
    else:
        # Season-level bulk format (2020-2021): data/raw/jolpica/year{YYYY}/results.json
        print(f"Processing year {year}: using season-level bulk JSON files")
        print(f"{'='*60}")

        results_path = year_dir / "results.json"
        if results_path.exists():
            all_results.extend(parse_round_results(read_json(results_path)))
            print(f"  Loaded {len(all_results)} race results from bulk results.json")
        else:
            print(f"  [WARN] No results.json found for {year}")

        qual_path = year_dir / "qualifying.json"
        if qual_path.exists():
            all_qualifying.extend(parse_round_qualifying(read_json(qual_path)))
            print(f"  Loaded {len(all_qualifying)} qualifying results from bulk qualifying.json")
        else:
            print(f"  [WARN] No qualifying.json found for {year}")

        sprint_path = year_dir / "sprint.json"
        if sprint_path.exists():
            sprint_rows = parse_round_sprint(read_json(sprint_path))
            if sprint_rows:
                all_sprint.extend(sprint_rows)
                print(f"  Loaded {len(all_sprint)} sprint results from bulk sprint.json")

    # --- Build and write race_results.csv ---
    if all_results:
        df = pd.DataFrame(all_results)
        df = canonicalize_constructors(df, constructor_map)
        df = add_abbrev_column(df, abbrev_map)
        df = df.sort_values(["season", "round", "finish_position"], na_position="last")
        cols = [c for c in RACE_RESULT_COLUMNS if c in df.columns]
        df = df[cols]
        write_csv(df, out_dir / "race_results.csv")
        print(f"  Wrote race_results.csv ({len(df)} rows)")
    else:
        print(f"  [WARN] No race results found for {year}")

    # --- Build and write qualifying_results.csv ---
    if all_qualifying:
        df = pd.DataFrame(all_qualifying)
        df = canonicalize_constructors(df, constructor_map)
        df = add_abbrev_column(df, abbrev_map)
        df = df.sort_values(["season", "round", "quali_position"], na_position="last")
        cols = [c for c in QUALIFYING_COLUMNS if c in df.columns]
        df = df[cols]
        write_csv(df, out_dir / "qualifying_results.csv")
        print(f"  Wrote qualifying_results.csv ({len(df)} rows)")
    else:
        print(f"  [WARN] No qualifying results found for {year}")

    # --- Build and write sprint_results.csv ---
    if all_sprint:
        df = pd.DataFrame(all_sprint)
        df = canonicalize_constructors(df, constructor_map)
        df = add_abbrev_column(df, abbrev_map)
        df = df.sort_values(["season", "round", "sprint_position"], na_position="last")
        cols = [c for c in SPRINT_COLUMNS if c in df.columns]
        df = df[cols]
        write_csv(df, out_dir / "sprint_results.csv")
        print(f"  Wrote sprint_results.csv ({len(df)} rows)")
    else:
        print(f"  No sprint results for {year} (expected for non-sprint seasons)")

    print(f"  Done with {year}.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Normalize raw Jolpica JSON into clean CSVs for the feature builder."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Process a single season (e.g. 2022)")
    group.add_argument("--all", action="store_true", help="Process all historical + current seasons")
    args = parser.parse_args()

    # Load mappings once
    abbrev_map = load_driver_abbrev_map(SEED_DIR)
    constructor_map = load_constructor_map(SEED_DIR)

    print(f"Loaded {len(abbrev_map)} driver abbrev mappings")
    print(f"Loaded {len(constructor_map)} constructor canonical mappings")
    print(f"Raw dir:  {JOLPICA_RAW_DIR}")
    print(f"Out dir:  {JOLPICA_NORMALIZED_DIR}")

    if args.all:
        years = sorted(set(HISTORICAL_SEASONS + [CURRENT_SEASON]))
    else:
        years = [args.year]

    for year in years:
        process_year(year, JOLPICA_RAW_DIR, JOLPICA_NORMALIZED_DIR,
                     abbrev_map, constructor_map)

    print("\nAll done.")


if __name__ == "__main__":
    main()
