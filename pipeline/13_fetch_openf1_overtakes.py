"""
Script 13 — Fetch Overtake Data from OpenF1 API

Fetches actual overtake counts from the OpenF1 API (openf1.org) which tracks
every on-track position change using F1's official timing data.

This provides more accurate overtake data than our sector-timing detection
(12_count_overtakes.py) since it uses F1's own position tracking system.

The script also fetches pit stop data to filter out pit-related position swaps,
giving a cleaner "on-track overtakes" count.

Data is saved in the same format as 12_count_overtakes.py output so it can be
consumed by 11_actual_fantasy_points.py seamlessly.

Usage:
    python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round 1
    python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round 2
    python pipeline/13_fetch_openf1_overtakes.py --year 2026 --all
    python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round 1 --include-pitstops
        (include pit-related position swaps in count; default: filter them out)
    python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round 1 --compare
        (compare with existing FastF1-based detection from script 12)

Output:
    data/overtakes/year{YYYY}/round{N}/overtakes.json
    data/overtakes/year{YYYY}/round{N}/openf1_raw.json  (raw API response)
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    DATA_DIR,
    CURRENT_SEASON,
    CANCELLED_ROUNDS_2026,
    SPRINT_ROUNDS_2026,
)

OPENF1_BASE = "https://api.openf1.org/v1"
OUTPUT_DIR = DATA_DIR / "overtakes"

# Pit stop window: overtakes within this many seconds of a pit stop are filtered
PIT_WINDOW_SECONDS = 30


# ==============================================================================
# API helpers
# ==============================================================================

def fetch_json(url: str, retries: int = 3) -> Optional[list]:
    """Fetch JSON from OpenF1 API with retry logic."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "BoxBoxF1Fantasy/1.0"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                # Rate limited — wait and retry
                wait = 2 ** (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"    HTTP error {e.code}: {e.reason}")
            return None
        except (URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            print(f"    Connection error: {e}")
            return None
    return None


def get_sessions(year: int) -> list[dict]:
    """Get all sessions for a given year."""
    url = f"{OPENF1_BASE}/sessions?year={year}"
    data = fetch_json(url)
    return data or []


def get_session_key(year: int, round_num: int, session_type: str = "Race") -> Optional[int]:
    """Find the OpenF1 session key for a given round and session type.

    Maps our round numbers to OpenF1 session keys by matching the Nth race
    event in the calendar.

    Note: OpenF1 classifies Sprints as session_type="Race" with
    session_name="Sprint", so we use session_name to distinguish.
    """
    sessions = get_sessions(year)
    if not sessions:
        return None

    # OpenF1 uses session_type="Race" for both Sprint and Race.
    # Distinguish via session_name: "Race" vs "Sprint".
    # For the main race: session_name="Race" AND session_type="Race"
    # For sprint: session_name="Sprint" AND session_type="Race"
    race_sessions = [
        s for s in sessions
        if s.get("session_type") == "Race" and s.get("session_name") == "Race"
    ]
    race_sessions.sort(key=lambda s: s.get("date_start", ""))

    # Walk through race sessions to find the Nth round (accounting for cancellations)
    active_round = 0
    target_meeting_key = None
    for rs in race_sessions:
        active_round += 1
        while active_round in CANCELLED_ROUNDS_2026:
            active_round += 1
        if active_round == round_num:
            target_meeting_key = rs.get("meeting_key")
            if session_type == "Race":
                return rs.get("session_key")
            break

    if target_meeting_key is None:
        return None

    # For Sprint, find the sprint session in the same meeting
    if session_type == "Sprint":
        sprint_sessions = [
            s for s in sessions
            if s.get("session_name") == "Sprint" and s.get("meeting_key") == target_meeting_key
        ]
        if sprint_sessions:
            return sprint_sessions[0].get("session_key")

    return None


def get_overtakes(session_key: int) -> list[dict]:
    """Fetch all overtake events for a session."""
    # The API might paginate; fetch all
    url = f"{OPENF1_BASE}/overtakes?session_key={session_key}"
    data = fetch_json(url)
    return data or []


def get_pit_stops(session_key: int) -> list[dict]:
    """Fetch pit stop data for a session (used to filter pit-related swaps)."""
    url = f"{OPENF1_BASE}/pit?session_key={session_key}"
    data = fetch_json(url)
    return data or []


def get_drivers(session_key: int) -> dict[int, str]:
    """Fetch driver number -> abbreviation mapping for a session."""
    url = f"{OPENF1_BASE}/drivers?session_key={session_key}"
    data = fetch_json(url)
    if not data:
        return {}

    num_to_abbrev = {}
    for d in data:
        num = d.get("driver_number")
        abbrev = d.get("name_acronym")
        if num and abbrev:
            num_to_abbrev[num] = abbrev

    return num_to_abbrev


def get_session_info(session_key: int) -> dict:
    """Get session metadata."""
    url = f"{OPENF1_BASE}/sessions?session_key={session_key}"
    data = fetch_json(url)
    if data and len(data) > 0:
        return data[0]
    return {}


# ==============================================================================
# Pit stop filtering
# ==============================================================================

def build_pit_windows(pit_stops: list[dict]) -> dict[int, list[tuple[str, str]]]:
    """Build time windows around each driver's pit stops.

    Returns: {driver_number: [(window_start, window_end), ...]}
    """
    from datetime import datetime, timedelta

    windows: dict[int, list[tuple[str, str]]] = {}
    for ps in pit_stops:
        driver_num = ps.get("driver_number")
        pit_time_str = ps.get("date")
        if not driver_num or not pit_time_str:
            continue

        try:
            # Parse ISO timestamp
            pit_time = datetime.fromisoformat(pit_time_str.replace("Z", "+00:00"))
            window_start = (pit_time - timedelta(seconds=PIT_WINDOW_SECONDS)).isoformat()
            window_end = (pit_time + timedelta(seconds=PIT_WINDOW_SECONDS)).isoformat()
            windows.setdefault(driver_num, []).append((window_start, window_end))
        except (ValueError, TypeError):
            continue

    return windows


def is_during_pit(overtake_time: str, driver_num: int,
                  pit_windows: dict[int, list[tuple[str, str]]]) -> bool:
    """Check if an overtake occurred during a driver's pit window."""
    driver_windows = pit_windows.get(driver_num, [])
    for start, end in driver_windows:
        if start <= overtake_time <= end:
            return True
    return False


# ==============================================================================
# Core processing
# ==============================================================================

def process_session(session_key: int, session_type: str, year: int, round_num: int,
                    include_pitstops: bool = False) -> Optional[dict]:
    """Fetch and process overtake data for a single session.

    Returns a dict with session info and per-driver overtake counts.
    """
    print(f"  Fetching {session_type} overtakes (session_key={session_key})...")

    # Fetch data
    overtakes = get_overtakes(session_key)
    if not overtakes:
        print(f"    No overtake data available")
        return None

    drivers_map = get_drivers(session_key)
    session_info = get_session_info(session_key)
    event_name = session_info.get("meeting_name", session_info.get("circuit_short_name", "Unknown"))

    print(f"    Raw overtake events: {len(overtakes)}")

    # Filter pit-related overtakes unless --include-pitstops
    if not include_pitstops:
        pit_stops = get_pit_stops(session_key)
        pit_windows = build_pit_windows(pit_stops)

        filtered = []
        pit_filtered_count = 0
        for ot in overtakes:
            ot_time = ot.get("date", "")
            overtaking = ot.get("overtaking_driver_number")
            overtaken = ot.get("overtaken_driver_number")

            # Filter if either driver is in a pit window
            if (is_during_pit(ot_time, overtaking, pit_windows) or
                    is_during_pit(ot_time, overtaken, pit_windows)):
                pit_filtered_count += 1
                continue
            filtered.append(ot)

        if pit_filtered_count > 0:
            print(f"    Filtered {pit_filtered_count} pit-related position swaps")
        overtakes = filtered

    print(f"    On-track overtakes: {len(overtakes)}")

    # Count per driver
    driver_counts: dict[int, int] = {}
    for ot in overtakes:
        driver_num = ot.get("overtaking_driver_number")
        if driver_num:
            driver_counts[driver_num] = driver_counts.get(driver_num, 0) + 1

    # Convert to abbreviations and sort by count
    driver_list = []
    for num, count in sorted(driver_counts.items(), key=lambda x: -x[1]):
        abbrev = drivers_map.get(num, f"#{num}")
        driver_list.append({
            "driver": abbrev,
            "driver_number": num,
            "overtakes": count,
        })

    return {
        "session": session_type,
        "event": event_name,
        "year": year,
        "round": round_num,
        "method": "openf1",
        "session_key": session_key,
        "total_overtakes": len(overtakes),
        "include_pitstops": include_pitstops,
        "drivers": driver_list,
    }


def fetch_pitstop_times(session_key: int, drivers_map: dict[int, str]) -> Optional[dict]:
    """Fetch pit stop stationary times (stop_duration) from OpenF1.

    OpenF1 provides both lane_duration (pit entry to exit, ~18-25s) and
    stop_duration (stationary "wheels up" time, ~2-4s). The stop_duration
    is what F1 Fantasy uses for constructor pit stop scoring.

    Returns dict with per-driver and per-constructor stop times, or None
    if stop_duration data isn't available.
    """
    print(f"  Fetching pit stop stationary times (session_key={session_key})...")
    pit_stops = get_pit_stops(session_key)
    if not pit_stops:
        print(f"    No pit stop data available")
        return None

    # Check if stop_duration is populated
    has_stop_duration = any(ps.get("stop_duration") is not None for ps in pit_stops)
    if not has_stop_duration:
        print(f"    stop_duration not available (only lane_duration)")
        return None

    by_driver: dict[str, list[dict]] = {}
    for ps in pit_stops:
        driver_num = ps.get("driver_number")
        stop_dur = ps.get("stop_duration")
        lane_dur = ps.get("lane_duration")
        lap = ps.get("lap_number")

        if driver_num is None or stop_dur is None:
            continue

        abbrev = drivers_map.get(driver_num, f"#{driver_num}")
        by_driver.setdefault(abbrev, []).append({
            "lap": lap,
            "stop_duration": round(stop_dur, 3),
            "lane_duration": round(lane_dur, 3) if lane_dur else None,
        })

    # Find fastest stop
    all_stops = []
    for abbrev, stops in by_driver.items():
        for s in stops:
            all_stops.append({"driver": abbrev, **s})

    fastest = min(all_stops, key=lambda x: x["stop_duration"]) if all_stops else None
    total_stops = len(all_stops)

    print(f"    {total_stops} pit stops with stationary times")
    if fastest:
        print(f"    Fastest: {fastest['driver']} {fastest['stop_duration']:.3f}s (lap {fastest['lap']})")

    return {
        "source": "openf1",
        "session_key": session_key,
        "total_stops": total_stops,
        "fastest_stop": fastest,
        "by_driver": by_driver,
    }


def fetch_round(year: int, round_num: int, include_pitstops: bool = False,
                compare: bool = False) -> Optional[dict]:
    """Fetch overtake data for an entire round (race + sprint if applicable)."""
    print(f"\n--- Round {round_num} ---")

    is_sprint = round_num in SPRINT_ROUNDS_2026

    # Find session keys
    print(f"  Looking up session keys...")
    race_key = get_session_key(year, round_num, "Race")
    if race_key is None:
        print(f"  No Race session found for round {round_num}")
        return None
    print(f"  Race session_key: {race_key}")

    sprint_key = None
    if is_sprint:
        sprint_key = get_session_key(year, round_num, "Sprint")
        if sprint_key:
            print(f"  Sprint session_key: {sprint_key}")

    # Process sessions
    result = {
        "year": year,
        "round": round_num,
        "method": "openf1",
        "sessions": {},
    }

    # Race
    race_data = process_session(race_key, "Race", year, round_num, include_pitstops)
    if race_data:
        result["sessions"]["race"] = race_data

    # Sprint
    if sprint_key:
        sprint_data = process_session(sprint_key, "Sprint", year, round_num, include_pitstops)
        if sprint_data:
            result["sessions"]["sprint"] = sprint_data

    if not result["sessions"]:
        print(f"  No overtake data available for round {round_num}")
        return None

    # Fetch pit stop stationary times (stop_duration) for race session
    pit_stop_data = fetch_pitstop_times(race_key, get_drivers(race_key))
    if pit_stop_data:
        result["pitstops"] = pit_stop_data

    # Save outputs
    out_dir = OUTPUT_DIR / f"year{year}" / f"round{round_num}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save main output (compatible with 11_actual_fantasy_points.py)
    out_path = out_dir / "overtakes.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Saved -> {out_path}")

    # Save raw API responses for reference
    raw_data = {"race_overtakes": get_overtakes(race_key) if race_key else []}
    if sprint_key:
        raw_data["sprint_overtakes"] = get_overtakes(sprint_key)
    raw_path = out_dir / "openf1_raw.json"
    with open(raw_path, "w") as f:
        json.dump(raw_data, f, indent=2)
    print(f"  Saved -> {raw_path}")

    # Compare with FastF1 detection if requested
    if compare:
        compare_with_fastf1(year, round_num, result)

    return result


def compare_with_fastf1(year: int, round_num: int, openf1_data: dict) -> None:
    """Compare OpenF1 overtakes with FastF1 sector-timing detection."""
    fastf1_path = OUTPUT_DIR / f"year{year}" / f"round{round_num}" / "overtakes_fastf1.json"
    if not fastf1_path.exists():
        # Check if current overtakes.json was from FastF1
        current_path = OUTPUT_DIR / f"year{year}" / f"round{round_num}" / "overtakes.json"
        if current_path.exists():
            with open(current_path) as f:
                existing = json.load(f)
            if existing.get("method") == "hf":
                fastf1_path = current_path
            else:
                print("  No FastF1 detection data to compare with")
                return
        else:
            print("  No FastF1 detection data to compare with")
            return

    with open(fastf1_path) as f:
        fastf1_data = json.load(f)

    print(f"\n  {'=' * 60}")
    print(f"  COMPARISON: OpenF1 API vs FastF1 Sector-Timing Detection")
    print(f"  {'=' * 60}")

    for session_type in ["race", "sprint"]:
        of1 = openf1_data.get("sessions", {}).get(session_type, {})
        ff1 = fastf1_data.get("sessions", {}).get(session_type, {})

        if not of1 and not ff1:
            continue

        of1_total = of1.get("total_overtakes", 0)
        ff1_total = ff1.get("total_overtakes", 0)

        print(f"\n  {session_type.upper()}:")
        print(f"    OpenF1 total: {of1_total}  |  FastF1 total: {ff1_total}  |  Delta: {of1_total - ff1_total:+d}")

        # Per-driver comparison
        of1_drivers = {d["driver"]: d["overtakes"] for d in of1.get("drivers", [])}
        ff1_drivers = {d["driver"]: d["overtakes"] for d in ff1.get("drivers", [])}
        all_drivers = sorted(set(of1_drivers) | set(ff1_drivers))

        if all_drivers:
            print(f"\n    {'Driver':<6} {'OpenF1':>7} {'FastF1':>7} {'Delta':>6}")
            print(f"    {'-' * 30}")
            for drv in all_drivers:
                o = of1_drivers.get(drv, 0)
                f = ff1_drivers.get(drv, 0)
                delta = o - f
                marker = " <<<" if abs(delta) > 5 else ""
                print(f"    {drv:<6} {o:>7} {f:>7} {delta:>+6}{marker}")


# ==============================================================================
# Main
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch overtake data from OpenF1 API"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--round", type=int, help="Round number to fetch")
    group.add_argument("--all", action="store_true", help="Fetch all available rounds")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON, help="Season year")
    parser.add_argument("--include-pitstops", action="store_true",
                        help="Include pit-related position swaps (default: filter them out)")
    parser.add_argument("--compare", action="store_true",
                        help="Compare with existing FastF1 detection data")
    args = parser.parse_args()

    print("=" * 70)
    print(f"BoxBoxF1Fantasy -- OpenF1 Overtake Data Fetcher ({args.year})")
    print("=" * 70)

    if args.all:
        # Find all rounds that have race sessions
        sessions = get_sessions(args.year)
        race_sessions = [s for s in sessions if s.get("session_type") == "Race"]
        race_sessions.sort(key=lambda s: s.get("date_start", ""))

        active_round = 0
        rounds_to_fetch = []
        for _ in race_sessions:
            active_round += 1
            while active_round in CANCELLED_ROUNDS_2026:
                active_round += 1
            rounds_to_fetch.append(active_round)

        # Only fetch rounds that are in the past
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        past_rounds = []
        for rs, rnd in zip(race_sessions, rounds_to_fetch):
            try:
                race_date = datetime.fromisoformat(rs["date_start"].replace("Z", "+00:00"))
                if race_date < now:
                    past_rounds.append(rnd)
            except (ValueError, KeyError):
                continue

        print(f"Completed rounds: {past_rounds}")

        for rnd in past_rounds:
            # Back up existing FastF1 data before overwriting
            backup_existing_fastf1(args.year, rnd)
            fetch_round(args.year, rnd, args.include_pitstops, args.compare)
    else:
        if args.round in CANCELLED_ROUNDS_2026:
            print(f"Round {args.round} is cancelled.")
            return
        # Back up existing FastF1 data before overwriting
        backup_existing_fastf1(args.year, args.round)
        fetch_round(args.year, args.round, args.include_pitstops, args.compare)

    print(f"\n{'=' * 70}")
    print("Done.")


def backup_existing_fastf1(year: int, round_num: int) -> None:
    """If existing overtakes.json is from FastF1 (method=hf), back it up."""
    path = OUTPUT_DIR / f"year{year}" / f"round{round_num}" / "overtakes.json"
    if not path.exists():
        return

    with open(path) as f:
        existing = json.load(f)

    if existing.get("method") in ("hf", "lap"):
        backup_path = path.parent / "overtakes_fastf1.json"
        if not backup_path.exists():
            with open(backup_path, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"  Backed up FastF1 data -> {backup_path}")


if __name__ == "__main__":
    main()
