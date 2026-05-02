"""
Script 02 — Build Laps

Creates clean lap-level datasets from raw FastF1 data for the current round.
Specifically processes free practice sessions.

For sprint weekends, only FP1 is available.
For regular weekends, FP1, FP2, and FP3 are available.

Processing steps:
- Remove in/out laps, safety car laps, VSC laps, invalid laps
- Normalize tyre compounds
- Add standardized driver/constructor IDs
- Add session metadata (track, weather, year)

Output:
    data/processed/laps/roundX/all_laps_fpX.parquet
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import fastf1
import pandas as pd
import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    FASTF1_CACHE_DIR,
    FASTF1_RAW_DIR,
    LAPS_DIR,
    SEED_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
    FP_SESSIONS,
    SPRINT_FP_SESSIONS,
    fastf1_round,
)


# -- ID Mapping ---------------------------------------------------------------

def load_id_mappings() -> tuple[dict[str, str], dict[str, str]]:
    """
    Load driver and constructor ID mappings from seed data.

    Returns:
        (driver_map, constructor_map) where keys are various source IDs
        and values are our canonical IDs.
    """
    with open(SEED_DIR / "driver_ids.json", "r") as f:
        data = json.load(f)

    driver_map: dict[str, str] = {}
    for m in data["mappings"]:
        abbrev = m["abbrev"]
        driver_map[m["fastf1"].upper()] = abbrev
        driver_map[m["jolpica"].lower()] = abbrev
        driver_map[m["full_name"].lower()] = abbrev
        # Handle common variations
        parts = m["full_name"].split()
        if len(parts) >= 2:
            driver_map[parts[-1].lower()] = abbrev  # Last name only

    constructor_map: dict[str, str] = {}
    for m in data["constructor_mappings"]:
        cid = m["id"]
        constructor_map[m["fastf1"].lower()] = cid
        constructor_map[m["jolpica"].lower()] = cid
        for alt in m.get("ergast_alt", []):
            constructor_map[alt.lower()] = cid

    return driver_map, constructor_map


# -- Tyre normalization --------------------------------------------------------

TYRE_COMPOUND_MAP: dict[str, str] = {
    "SOFT": "SOFT",
    "MEDIUM": "MEDIUM",
    "HARD": "HARD",
    "INTERMEDIATE": "INTERMEDIATE",
    "WET": "WET",
    # FastF1 sometimes uses test compound names
    "TEST_UNKNOWN": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
    # C-series compounds -> generic
    "C1": "HARD",
    "C2": "MEDIUM",
    "C3": "SOFT",
    "C4": "SOFT",
    "C5": "SOFT",
}


def normalize_compound(compound: Optional[str]) -> str:
    """Normalize a tyre compound string to a canonical form."""
    if compound is None or pd.isna(compound):
        return "UNKNOWN"
    return TYRE_COMPOUND_MAP.get(str(compound).upper().strip(), "UNKNOWN")


# -- Lap filtering -------------------------------------------------------------

def clean_laps(laps_df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove invalid laps from a FastF1 laps DataFrame.

    Removes:
    - In laps (pit entry)
    - Out laps (pit exit)
    - Safety car laps
    - Virtual safety car laps
    - Laps flagged as deleted / invalid
    - Laps with no time recorded
    """
    df = laps_df.copy()
    initial_count = len(df)

    # Remove laps with no time
    if "LapTime" in df.columns:
        df = df[df["LapTime"].notna()]

    # Remove pit in/out laps
    if "PitInTime" in df.columns:
        df = df[df["PitInTime"].isna()]
    if "PitOutTime" in df.columns:
        df = df[df["PitOutTime"].isna()]

    # Remove invalid / deleted laps
    # FastF1 uses None when not deleted and True when deleted
    if "Deleted" in df.columns:
        df = df[df["Deleted"].isna() | (df["Deleted"] == False)]

    # Remove safety car laps
    # TrackStatus is a composite string of flags: 1=Green, 2=Yellow, 4=SC, 5=Red, 6=VSC, 7=VSC Ending
    # We check if any SC/Red/VSC flags are present in the composite code
    if "TrackStatus" in df.columns:
        def is_clean_status(status):
            s = str(status)
            # Remove green (1) and yellow (2) flags, check if SC(4)/Red(5)/VSC(6) remain
            return "4" not in s and "5" not in s
        df = df[df["TrackStatus"].apply(is_clean_status)]

    removed = initial_count - len(df)
    print(f"    Cleaned: {initial_count} -> {len(df)} laps ({removed} removed)")

    return df


# -- Session processing --------------------------------------------------------

def process_fp_session(
    year: int,
    round_num: int,
    session_name: str,
    driver_map: dict[str, str],
    constructor_map: dict[str, str],
) -> Optional[pd.DataFrame]:
    """
    Load, clean, and structure a free practice session.

    Returns:
        Cleaned DataFrame with standardized columns, or None if unavailable.
    """
    ff1_round = fastf1_round(round_num, year)
    try:
        session = fastf1.get_session(year, ff1_round, session_name)
        session.load(laps=True, telemetry=False, weather=True, messages=False)
        laps = session.laps
    except Exception as e:
        print(f"    Could not load {session_name}: {e}")
        return None

    if laps is None or laps.empty:
        print(f"    No lap data for {session_name}")
        return None

    # Clean laps
    df = clean_laps(laps)
    if df.empty:
        print(f"    No valid laps remaining for {session_name}")
        return None

    # Map driver IDs
    if "Driver" in df.columns:
        df["driver_id"] = df["Driver"].apply(
            lambda x: driver_map.get(str(x).upper(), str(x))
        )
    else:
        df["driver_id"] = "UNKNOWN"

    # Map constructor IDs
    if "Team" in df.columns:
        df["constructor_id"] = df["Team"].apply(
            lambda x: constructor_map.get(str(x).lower(), str(x))
        )
    else:
        df["constructor_id"] = "UNKNOWN"

    # Convert lap time to seconds
    if "LapTime" in df.columns:
        df["lap_time"] = df["LapTime"].dt.total_seconds()
    else:
        df["lap_time"] = None

    # Sector times
    for i in range(1, 4):
        col = f"Sector{i}Time"
        out_col = f"sector_{i}"
        if col in df.columns:
            df[out_col] = df[col].dt.total_seconds()
        else:
            df[out_col] = None

    # Tyre compound
    if "Compound" in df.columns:
        df["compound"] = df["Compound"].apply(normalize_compound)
    else:
        df["compound"] = "UNKNOWN"

    # Stint number
    if "Stint" in df.columns:
        df["stint_number"] = df["Stint"]
    else:
        df["stint_number"] = 1

    # Lap number
    if "LapNumber" in df.columns:
        df["lap_number"] = df["LapNumber"]
    else:
        df["lap_number"] = range(1, len(df) + 1)

    # Tyre life
    if "TyreLife" in df.columns:
        df["tyre_life"] = df["TyreLife"]
    else:
        df["tyre_life"] = None

    # Speed trap
    if "SpeedI1" in df.columns:
        df["speed_trap_1"] = df["SpeedI1"]
    if "SpeedI2" in df.columns:
        df["speed_trap_2"] = df["SpeedI2"]
    if "SpeedFL" in df.columns:
        df["speed_fl"] = df["SpeedFL"]
    if "SpeedST" in df.columns:
        df["speed_st"] = df["SpeedST"]

    # Weather data
    weather = session.weather_data
    if weather is not None and not weather.empty:
        df["track_temperature"] = weather["TrackTemp"].mean() if "TrackTemp" in weather.columns else None
        df["air_temperature"] = weather["AirTemp"].mean() if "AirTemp" in weather.columns else None
        df["humidity"] = weather["Humidity"].mean() if "Humidity" in weather.columns else None
        df["wind_speed"] = weather["WindSpeed"].mean() if "WindSpeed" in weather.columns else None
        df["rainfall"] = weather["Rainfall"].any() if "Rainfall" in weather.columns else None
    else:
        df["track_temperature"] = None
        df["air_temperature"] = None
        df["humidity"] = None
        df["wind_speed"] = None
        df["rainfall"] = None

    # Metadata
    df["session"] = session_name
    df["year"] = year
    df["round"] = round_num
    df["track"] = session.event["EventName"] if hasattr(session, "event") else ""

    # Select final columns
    output_cols = [
        "driver_id", "constructor_id", "lap_time",
        "sector_1", "sector_2", "sector_3",
        "compound", "stint_number", "lap_number", "tyre_life",
        "session", "track", "year", "round",
        "track_temperature", "air_temperature", "humidity", "wind_speed", "rainfall",
    ]

    # Add optional speed columns if they exist
    for col in ["speed_trap_1", "speed_trap_2", "speed_fl", "speed_st"]:
        if col in df.columns:
            output_cols.append(col)

    # Only keep columns that exist
    output_cols = [c for c in output_cols if c in df.columns]

    return df[output_cols].reset_index(drop=True)


# -- Main ---------------------------------------------------------------------

def main() -> None:
    """Build clean lap datasets for a specified round."""
    parser = argparse.ArgumentParser(description="BoxBoxF1Fantasy — Build Laps")
    parser.add_argument("--round", type=int, default=None,
                        help="Round number to process")
    args, _ = parser.parse_known_args()

    print("=" * 60)
    print("BoxBoxF1Fantasy — Build Laps")
    print("=" * 60)

    # Setup FastF1 cache
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))

    year = CURRENT_SEASON
    if args.round is not None:
        round_num = args.round
    else:
        round_num = int(input(f"\nEnter round number for {year}: ").strip())

    if round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled.")
        return

    # Determine which FP sessions to process
    is_sprint = round_num in SPRINT_ROUNDS_2026
    fp_sessions = SPRINT_FP_SESSIONS if is_sprint else FP_SESSIONS

    print(f"\nSprint weekend: {'Yes' if is_sprint else 'No'}")
    print(f"FP sessions to process: {fp_sessions}")

    # Load ID mappings
    driver_map, constructor_map = load_id_mappings()

    # Process each FP session
    output_dir = LAPS_DIR / f"round{round_num}"
    output_dir.mkdir(parents=True, exist_ok=True)

    for session_name in fp_sessions:
        print(f"\nProcessing {session_name}...")
        df = process_fp_session(year, round_num, session_name, driver_map, constructor_map)

        if df is not None and not df.empty:
            # FP1 -> fp1, FP2 -> fp2, etc.
            fp_num = session_name.lower().replace("fp", "")
            output_path = output_dir / f"all_laps_fp{fp_num}.parquet"
            df.to_parquet(output_path, index=False, engine="pyarrow")
            print(f"  Saved: {output_path} ({len(df)} laps)")
            print(f"  Drivers: {sorted(df['driver_id'].unique())}")
            print(f"  Compounds: {sorted(df['compound'].unique())}")
        else:
            print(f"  No data available for {session_name}")

    print("\n" + "=" * 60)
    print("Build Laps complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
