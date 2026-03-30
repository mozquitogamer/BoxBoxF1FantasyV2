"""
Script 13 — Fetch Pit Stop Stationary Times from OpenF1

Fetches pit stop data from OpenF1 API, which provides:
  - pit_duration: total pit lane time (entry to exit)
  - stop_duration: stationary/wheels-up time (what F1 broadcasts show)

When stop_duration is available (OpenF1 has processed it), we use it directly.
When unavailable, we estimate it by subtracting the circuit's average pit lane
transit time from pit_duration.

Output:
    web/public/data/pitstops_round{N}.json

Usage:
    python pipeline/13_fetch_pitstop_stationary.py --round 3
    python pipeline/13_fetch_pitstop_stationary.py --all
"""

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    SEED_DIR,
    WEB_DATA_DIR,
    CANCELLED_ROUNDS_2026,
)


# When stop_duration is not available from OpenF1, we estimate stationary time
# by: transit = min(pit_durations) - ASSUMED_BEST_STOP, then stationary = pit - transit
# This assumes the fastest total pit is a ~2.0s stationary stop + full lane transit.
ASSUMED_BEST_STOP = 2.0  # seconds — a very fast stop

# Max reasonable pit duration to include (filter red flags, drive-throughs)
MAX_PIT_DURATION = 60.0  # seconds


def load_races() -> list[dict]:
    """Load race calendar."""
    with open(SEED_DIR / "races.json") as f:
        return json.load(f)["races"]


def load_driver_mapping() -> dict:
    """Load OpenF1 driver number -> (abbrev, constructor_id) mapping."""
    with open(SEED_DIR / "driver_ids.json") as f:
        ids = json.load(f)
    with open(SEED_DIR / "drivers.json") as f:
        drivers = json.load(f)

    num_to_abbrev = {}
    for m in ids["mappings"]:
        num_to_abbrev[m["openf1_num"]] = m["abbrev"]

    abbrev_to_constructor = {}
    for d in drivers["drivers"]:
        abbrev_to_constructor[d["driver_id"]] = d["constructor_id"]

    return num_to_abbrev, abbrev_to_constructor


def get_session_key(year: int, circuit_short_name: str) -> int | None:
    """Get OpenF1 session key for a race."""
    try:
        r = requests.get(
            "https://api.openf1.org/v1/sessions",
            params={
                "year": year,
                "session_name": "Race",
                "circuit_short_name": circuit_short_name,
            },
            timeout=15,
        )
        r.raise_for_status()
        sessions = r.json()
        return sessions[0]["session_key"] if sessions else None
    except Exception as e:
        print(f"  Error fetching session key: {e}")
        return None


def fetch_pitstops(session_key: int) -> list[dict]:
    """Fetch pit stop data from OpenF1."""
    try:
        r = requests.get(
            "https://api.openf1.org/v1/pit",
            params={"session_key": session_key},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  Error fetching pit stops: {e}")
        return []


def process_pitstops(
    stops: list[dict],
    num_to_abbrev: dict,
    abbrev_to_constructor: dict,
    circuit_name: str,
) -> dict:
    """Process pit stop data into constructor-keyed stationary times.

    Returns dict: constructor_id -> [list of stationary times in seconds]
    """
    # Check if stop_duration is available
    has_stationary = any(s.get("stop_duration") is not None for s in stops)

    if has_stationary:
        print(f"  Using official stationary times (stop_duration)")
    else:
        # Estimate pit lane transit from the fastest pit_duration
        # Filter out extreme values first
        normal_stops = [s for s in stops
                        if s.get("pit_duration") is not None
                        and float(s["pit_duration"]) < MAX_PIT_DURATION]
        if normal_stops:
            min_pit = min(float(s["pit_duration"]) for s in normal_stops)
            pit_transit = min_pit - ASSUMED_BEST_STOP
            print(f"  stop_duration not available. Estimated transit={pit_transit:.1f}s "
                  f"(from fastest pit={min_pit:.1f}s - {ASSUMED_BEST_STOP}s)")
        else:
            pit_transit = 20.0
            print(f"  No usable pit data, using default transit={pit_transit:.1f}s")

    by_constructor: dict[str, list[float]] = {}

    for stop in stops:
        driver_num = stop.get("driver_number")
        abbrev = num_to_abbrev.get(driver_num)
        if not abbrev:
            continue

        cid = abbrev_to_constructor.get(abbrev)
        if not cid:
            continue

        if has_stationary and stop.get("stop_duration") is not None:
            stationary = float(stop["stop_duration"])
        elif stop.get("pit_duration") is not None:
            pit_total = float(stop["pit_duration"])
            if pit_total > MAX_PIT_DURATION:
                continue  # Skip red flags, drive-throughs
            stationary = max(1.5, pit_total - pit_transit)
        else:
            continue

        if cid not in by_constructor:
            by_constructor[cid] = []
        by_constructor[cid].append(round(stationary, 1))

    return by_constructor


def save_pitstop_file(round_num: int, by_constructor: dict) -> Path:
    """Save pitstop data to web data directory."""
    output = {
        "round": round_num,
        "by_constructor": by_constructor,
    }
    path = WEB_DATA_DIR / f"pitstops_round{round_num}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    return path


def process_round(round_num: int, year: int = CURRENT_SEASON) -> bool:
    """Process pit stops for a single round."""
    races = load_races()
    race = next((r for r in races if r["round"] == round_num), None)
    if not race:
        print(f"  Round {round_num} not found in calendar")
        return False

    circuit = race.get("circuit_short_name", race.get("circuit", ""))
    print(f"\n  Round {round_num}: {race['name']} ({circuit})")

    num_to_abbrev, abbrev_to_constructor = load_driver_mapping()

    # Get session key
    session_key = get_session_key(year, circuit)
    if not session_key:
        print(f"  Could not find session key for {circuit}")
        return False

    print(f"  Session key: {session_key}")

    # Fetch pit stops
    stops = fetch_pitstops(session_key)
    if not stops:
        print(f"  No pit stop data available")
        return False

    print(f"  {len(stops)} pit stops found")

    # Process into constructor stationary times
    by_constructor = process_pitstops(stops, num_to_abbrev, abbrev_to_constructor, circuit)

    if not by_constructor:
        print(f"  No processable pit stop data")
        return False

    # Save
    path = save_pitstop_file(round_num, by_constructor)
    print(f"  Saved -> {path}")

    # Print summary
    for cid, times in sorted(by_constructor.items(), key=lambda x: min(x[1])):
        best = min(times)
        avg = sum(times) / len(times)
        print(f"    {cid:<18s} best={best:.1f}s avg={avg:.1f}s stops={len(times)}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch pit stop stationary times")
    parser.add_argument("--round", "-r", type=int, help="Round number")
    parser.add_argument("--all", action="store_true", help="Process all completed rounds")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON)
    args = parser.parse_args()

    print("=" * 70)
    print("BoxBoxF1Fantasy — Pit Stop Stationary Times (OpenF1)")
    print("=" * 70)

    if args.all:
        races = load_races()
        for race in races:
            rnd = race["round"]
            if rnd in CANCELLED_ROUNDS_2026:
                continue
            # Check if we have race data (i.e., race has happened)
            actual_path = WEB_DATA_DIR / f"actual_round{rnd}.json"
            if actual_path.exists():
                process_round(rnd, args.year)
    elif args.round:
        process_round(args.round, args.year)
    else:
        print("Specify --round N or --all")

    print("\nDone.")


if __name__ == "__main__":
    main()
