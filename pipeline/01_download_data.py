"""
Script 01 — Download Data

Downloads Formula 1 data from two sources:
1. FastF1: Telemetry, lap times, sector times, tyre data, pit stops, weather
2. Jolpica API (Ergast replacement): Race results, qualifying, standings, pit stops

Usage:
    python pipeline/01_download_data.py

The script will prompt the user to choose between:
- Downloading current round data (2026 season)
- Downloading historical data for a custom year range
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import fastf1
import pandas as pd
import requests
from tqdm import tqdm

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    FASTF1_CACHE_DIR,
    FASTF1_RAW_DIR,
    JOLPICA_BASE_URL,
    JOLPICA_RAW_DIR,
    SEED_DIR,
    ALL_SESSIONS,
    CANCELLED_ROUNDS_2026,
)


# -- Helpers -------------------------------------------------------------------

def load_races() -> list[dict]:
    """Load the race calendar from seed data."""
    races_path = SEED_DIR / "races.json"
    with open(races_path, "r") as f:
        data = json.load(f)
    return data["races"]


def jolpica_get(endpoint: str, retries: int = 5, delay: float = 2.0) -> Optional[dict]:
    """
    GET request to the Jolpica API with retry logic.

    Args:
        endpoint: API path after the base URL (e.g., "/2024/1/results").
        retries: Number of retry attempts.
        delay: Seconds to wait between retries.

    Returns:
        Parsed JSON response or None if all retries fail.
    """
    url = f"{JOLPICA_BASE_URL}/{endpoint.lstrip('/')}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = delay * (attempt + 2)
                print(f"  Rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {resp.status_code} for {url}")
                return None
        except requests.RequestException as e:
            print(f"  Request error (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(delay)
    return None


def save_jolpica_json(data: dict, filepath: Path) -> None:
    """Save Jolpica API response to a JSON file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


# -- FastF1 Download ----------------------------------------------------------

def download_fastf1_session(
    year: int,
    round_num: int,
    session_name: str,
    output_dir: Path,
) -> bool:
    """
    Download a single FastF1 session and save lap data as Parquet.

    Args:
        year: Season year.
        round_num: Round number.
        session_name: Session type (FP1, FP2, FP3, Qualifying, Race, Sprint).
        output_dir: Directory to save the Parquet file.

    Returns:
        True if successful, False otherwise.
    """
    try:
        session = fastf1.get_session(year, round_num, session_name)
        session.load(
            laps=True,
            telemetry=False,  # Telemetry is huge — load separately if needed
            weather=True,
            messages=False,
        )
        laps = session.laps
    except Exception as e:
        print(f"    Skipping {session_name}: {e}")
        return False

    if laps is None or laps.empty:
        print(f"    No lap data for {session_name}")
        return False

    # Build a clean DataFrame with the columns we need
    df = laps.copy()

    # Add session metadata
    df["session"] = session_name
    df["year"] = year
    df["round"] = round_num
    df["track"] = session.event["EventName"] if hasattr(session, "event") else ""

    # Add weather data if available
    weather = session.weather_data
    if weather is not None and not weather.empty:
        df["track_temperature"] = weather["TrackTemp"].mean() if "TrackTemp" in weather.columns else None
        df["air_temperature"] = weather["AirTemp"].mean() if "AirTemp" in weather.columns else None
    else:
        df["track_temperature"] = None
        df["air_temperature"] = None

    # Save
    session_safe = session_name.replace(" ", "_").lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session_safe}.parquet"

    # Convert timedelta columns to seconds for cleaner storage
    timedelta_cols = df.select_dtypes(include=["timedelta64"]).columns
    for col in timedelta_cols:
        df[f"{col}_seconds"] = df[col].dt.total_seconds()

    df.to_parquet(output_path, index=False, engine="pyarrow")
    print(f"    Saved {session_name}: {len(df)} laps -> {output_path.name}")
    return True


def download_fastf1_round(year: int, round_num: int) -> None:
    """Download all available sessions for a given round via FastF1."""
    output_dir = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}"
    print(f"\n  FastF1 — {year} Round {round_num}")

    for session_name in ALL_SESSIONS:
        download_fastf1_session(year, round_num, session_name, output_dir)
        time.sleep(0.5)  # Be nice to the API


# -- Jolpica Download ---------------------------------------------------------

def download_jolpica_year(year: int) -> None:
    """
    Download all available data for a given year from the Jolpica API.

    Downloads: race results, qualifying, sprint, pit stops, standings.
    """
    year_dir = JOLPICA_RAW_DIR / f"year{year}"
    year_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  Jolpica API — {year} season")

    # 1. Get schedule to know how many rounds
    schedule = jolpica_get(f"{year}.json?limit=100")
    if not schedule:
        print(f"    Could not fetch {year} schedule")
        return

    races = schedule.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    num_rounds = len(races)
    print(f"    Found {num_rounds} rounds")

    # Save schedule
    save_jolpica_json(schedule, year_dir / "schedule.json")

    # 2. Download per-round data
    for race in tqdm(races, desc=f"    Downloading rounds", unit="round"):
        rnd = int(race["round"])
        round_dir = year_dir / f"round{rnd}"
        round_dir.mkdir(parents=True, exist_ok=True)

        # Race results
        data = jolpica_get(f"{year}/{rnd}/results.json")
        if data:
            save_jolpica_json(data, round_dir / "results.json")

        # Qualifying results
        data = jolpica_get(f"{year}/{rnd}/qualifying.json")
        if data:
            save_jolpica_json(data, round_dir / "qualifying.json")

        # Sprint results (may not exist for all rounds)
        data = jolpica_get(f"{year}/{rnd}/sprint.json")
        if data:
            sprint_races = (
                data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            )
            if sprint_races:
                save_jolpica_json(data, round_dir / "sprint.json")

        # Pit stops
        data = jolpica_get(f"{year}/{rnd}/pitstops.json?limit=100")
        if data:
            save_jolpica_json(data, round_dir / "pitstops.json")

        # Rate limit courtesy (Jolpica rate-limits aggressively)
        time.sleep(1.0)

    # 3. Season-level data
    print("    Downloading season standings...")

    # Driver standings
    data = jolpica_get(f"{year}/driverStandings.json")
    if data:
        save_jolpica_json(data, year_dir / "driver_standings.json")

    # Constructor standings
    data = jolpica_get(f"{year}/constructorStandings.json")
    if data:
        save_jolpica_json(data, year_dir / "constructor_standings.json")

    print(f"    Done — {year}")


def download_jolpica_round(year: int, round_num: int) -> None:
    """Download Jolpica data for a single round."""
    round_dir = JOLPICA_RAW_DIR / f"year{year}" / f"round{round_num}"
    round_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  Jolpica API — {year} Round {round_num}")

    endpoints = {
        "results.json": f"{year}/{round_num}/results.json",
        "qualifying.json": f"{year}/{round_num}/qualifying.json",
        "sprint.json": f"{year}/{round_num}/sprint.json",
        "pitstops.json": f"{year}/{round_num}/pitstops.json?limit=100",
    }

    for filename, endpoint in endpoints.items():
        data = jolpica_get(endpoint)
        if data:
            # Only save sprint if data actually exists
            if filename == "sprint.json":
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                if not races:
                    continue
            save_jolpica_json(data, round_dir / filename)
            print(f"    Saved {filename}")
        time.sleep(0.3)


# -- Main ---------------------------------------------------------------------

def get_total_rounds_for_year(year: int) -> int:
    """Get the number of rounds in a season from Jolpica."""
    data = jolpica_get(f"{year}.json?limit=100")
    if data:
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return len(races)
    return 0


def main() -> None:
    """Main entry point — supports both CLI args and interactive prompts."""
    parser = argparse.ArgumentParser(description="BoxBoxF1Fantasy — Data Downloader")
    parser.add_argument("--mode", choices=["current", "historical"],
                        help="Download mode: 'current' for a specific round, 'historical' for year range")
    parser.add_argument("--round", type=int, default=None,
                        help="Round number (used with --mode current)")
    parser.add_argument("--start-year", type=int, default=None,
                        help="Start year (used with --mode historical)")
    parser.add_argument("--end-year", type=int, default=None,
                        help="End year (used with --mode historical)")
    args, _ = parser.parse_known_args()

    print("=" * 60)
    print("BoxBoxF1Fantasy — Data Downloader")
    print("=" * 60)

    # Setup FastF1 cache
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))

    print(f"\nCurrent season: {CURRENT_SEASON}")
    print(f"Cancelled rounds: {CANCELLED_ROUNDS_2026}")

    # --- CLI-driven paths ---
    if args.mode == "current":
        round_num = args.round
        if round_num is None:
            print("Error: --round is required with --mode current")
            sys.exit(1)
        if round_num in CANCELLED_ROUNDS_2026:
            print(f"Round {round_num} is cancelled. Aborting.")
            return
        print(f"\nDownloading {CURRENT_SEASON} Round {round_num}...")
        download_fastf1_round(CURRENT_SEASON, round_num)
        download_jolpica_round(CURRENT_SEASON, round_num)
        print("\n" + "=" * 60)
        print("Download complete!")
        print("=" * 60)
        return

    if args.mode == "historical":
        start_year = args.start_year
        end_year = args.end_year
        if start_year is None or end_year is None:
            print("Error: --start-year and --end-year are required with --mode historical")
            sys.exit(1)
        print(f"\nDownloading historical data from {start_year} to {end_year}...")
        for year in range(start_year, end_year + 1):
            print(f"\n{'-' * 40}")
            print(f"Season {year}")
            print(f"{'-' * 40}")
            download_jolpica_year(year)
            total_rounds = get_total_rounds_for_year(year)
            if total_rounds == 0:
                print(f"  Could not determine rounds for {year}, skipping FastF1")
                continue
            print(f"\n  FastF1 — downloading {total_rounds} rounds...")
            for rnd in tqdm(range(1, total_rounds + 1), desc=f"  FastF1 {year}", unit="round"):
                download_fastf1_round(year, rnd)
        print("\n" + "=" * 60)
        print("Download complete!")
        print("=" * 60)
        return

    # --- Interactive fallback (no --mode provided) ---
    print("\nOptions:")
    print("  1. Download current round data (specific round)")
    print("  2. Download historical data (year range)")
    print("  3. Download both current season rounds and historical data")

    choice = input("\nSelect option (1/2/3): ").strip()

    if choice == "1":
        round_num = int(input(f"Enter round number for {CURRENT_SEASON}: ").strip())

        if round_num in CANCELLED_ROUNDS_2026:
            print(f"Round {round_num} is cancelled. Aborting.")
            return

        print(f"\nDownloading {CURRENT_SEASON} Round {round_num}...")
        download_fastf1_round(CURRENT_SEASON, round_num)
        download_jolpica_round(CURRENT_SEASON, round_num)

    elif choice == "2":
        start_year = int(input("Enter start year: ").strip())
        end_year = int(input("Enter end year: ").strip())

        print(f"\nDownloading historical data from {start_year} to {end_year}...")

        for year in range(start_year, end_year + 1):
            print(f"\n{'-' * 40}")
            print(f"Season {year}")
            print(f"{'-' * 40}")

            # Jolpica first (lighter)
            download_jolpica_year(year)

            # FastF1 (heavier — only FP/Quali/Race for training data)
            total_rounds = get_total_rounds_for_year(year)
            if total_rounds == 0:
                print(f"  Could not determine rounds for {year}, skipping FastF1")
                continue

            print(f"\n  FastF1 — downloading {total_rounds} rounds...")
            for rnd in tqdm(range(1, total_rounds + 1), desc=f"  FastF1 {year}", unit="round"):
                download_fastf1_round(year, rnd)

    elif choice == "3":
        # Historical first
        start_year = int(input("Enter historical start year: ").strip())
        end_year = int(input("Enter historical end year: ").strip())

        print(f"\n-- Historical data: {start_year}–{end_year} --")
        for year in range(start_year, end_year + 1):
            print(f"\n{'-' * 40}")
            print(f"Season {year}")
            print(f"{'-' * 40}")
            download_jolpica_year(year)

            total_rounds = get_total_rounds_for_year(year)
            if total_rounds > 0:
                for rnd in tqdm(range(1, total_rounds + 1), desc=f"  FastF1 {year}", unit="round"):
                    download_fastf1_round(year, rnd)

        # Current season rounds
        print(f"\n-- Current season: {CURRENT_SEASON} --")
        rounds_input = input(
            f"Enter {CURRENT_SEASON} rounds to download (comma-separated, e.g., 1,2): "
        ).strip()
        rounds = [int(r.strip()) for r in rounds_input.split(",") if r.strip()]

        for rnd in rounds:
            if rnd in CANCELLED_ROUNDS_2026:
                print(f"  Skipping cancelled round {rnd}")
                continue
            download_fastf1_round(CURRENT_SEASON, rnd)
            download_jolpica_round(CURRENT_SEASON, rnd)

    else:
        print("Invalid option.")
        return

    print("\n" + "=" * 60)
    print("Download complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
