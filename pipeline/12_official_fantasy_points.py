"""
12_official_fantasy_points.py

Manages official F1 Fantasy points data.
Supports automatic fetching from GitHub (JoshCBruce/fantasy-data) and manual input.

Usage:
    python pipeline/12_official_fantasy_points.py --fetch           # Auto-fetch all rounds from GitHub
    python pipeline/12_official_fantasy_points.py --fetch --round 1 # Fetch specific round
    python pipeline/12_official_fantasy_points.py --round 1 --input points.csv
    python pipeline/12_official_fantasy_points.py --round 1 --interactive
    python pipeline/12_official_fantasy_points.py --summary
"""

import json
import argparse
import sys
import time
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = PROJECT_ROOT / "data" / "seed" / "official_fantasy_points.json"
WEB_FILE = PROJECT_ROOT / "web" / "public" / "data" / "official_points.json"

# ── GitHub data source (JoshCBruce/fantasy-data) ──
# This repo scrapes official F1 Fantasy stats and publishes per-driver/constructor JSON.
GITHUB_BASE = "https://raw.githubusercontent.com/JoshCBruce/fantasy-data/refs/heads/main/latest"
GITHUB_DRIVER_URL = GITHUB_BASE + "/driver_data/{abbrev}.json"
GITHUB_CONSTRUCTOR_URL = GITHUB_BASE + "/constructor_data/{abbrev}.json"

# ── 2026 driver roster ──
ALL_DRIVERS = [
    "VER", "RUS", "NOR", "PIA", "ANT", "LEC", "HAM", "HAD",
    "GAS", "SAI", "ALB", "ALO", "BEA", "OCO", "LIN", "COL",
    "LAW", "STR", "BOR", "PER", "HUL", "BOT"
]

# ── Constructor mapping: our IDs → GitHub abbreviations ──
CONSTRUCTOR_MAP = {
    "mercedes":      "MER",
    "red_bull":       "RBR",
    "ferrari":        "FER",
    "mclaren":        "MCL",
    "aston_martin":   "AMR",
    "alpine":         "ALP",
    "williams":       "WIL",
    "racing_bulls":   "RB",
    "haas":           "HAS",
    "audi":           "SAU",   # Sauber → Audi rebrand
    "cadillac":       "CAD",   # New for 2026
}

ALL_CONSTRUCTORS = list(CONSTRUCTOR_MAP.keys())

RACE_NAMES = {
    1: "Australian Grand Prix",
    2: "Chinese Grand Prix",
    3: "Japanese Grand Prix",
    4: "Bahrain Grand Prix",
    5: "Saudi Arabian Grand Prix",
    6: "Miami Grand Prix",
    7: "Canadian Grand Prix",
    8: "Monaco Grand Prix",
    9: "Spanish Grand Prix",
    10: "Austrian Grand Prix",
    11: "British Grand Prix",
    12: "Belgian Grand Prix",
    13: "Hungarian Grand Prix",
    14: "Dutch Grand Prix",
    15: "Italian Grand Prix",
    16: "Spanish Grand Prix (Madrid)",
    17: "Azerbaijan Grand Prix",
    18: "Singapore Grand Prix",
    19: "United States Grand Prix",
    20: "Mexican Grand Prix",
    21: "Brazilian Grand Prix",
    22: "Las Vegas Grand Prix",
    23: "Qatar Grand Prix",
    24: "Abu Dhabi Grand Prix",
}


# ═══════════════════════════════════════════════════════════
#  Data loading / saving
# ═══════════════════════════════════════════════════════════

def load_data():
    """Load existing official points data."""
    if WEB_FILE.exists():
        with open(WEB_FILE) as f:
            return json.load(f)
    if SEED_FILE.exists():
        with open(SEED_FILE) as f:
            return json.load(f)
    return {
        "season": 2026,
        "last_updated": "",
        "description": "Official F1 Fantasy points per round.",
        "rounds": {}
    }


def save_data(data):
    """Save to both seed and web locations."""
    data["last_updated"] = str(date.today())

    SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEB_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(SEED_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    with open(WEB_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"  Saved to {SEED_FILE}")
    print(f"  Saved to {WEB_FILE}")


def init_round(data, round_num):
    """Ensure a round entry exists."""
    rkey = str(round_num)
    if rkey not in data["rounds"]:
        data["rounds"][rkey] = {
            "race": RACE_NAMES.get(round_num, f"Round {round_num}"),
            "drivers": {d: None for d in ALL_DRIVERS},
            "constructors": {c: None for c in ALL_CONSTRUCTORS}
        }
    return data


# ═══════════════════════════════════════════════════════════
#  Auto-fetch from GitHub (JoshCBruce/fantasy-data)
# ═══════════════════════════════════════════════════════════

def fetch_from_github(target_round=None):
    """
    Fetch official F1 Fantasy points from JoshCBruce/fantasy-data on GitHub.
    This repo scrapes fantasy.formula1.com/en/statistics and publishes per-driver JSON
    with totalPoints per round.

    Args:
        target_round: If specified, only fetch data for this round. Otherwise fetch all.

    Returns:
        dict: {round_num: {drivers: {abbrev: pts}, constructors: {our_id: pts}}}
    """
    import requests

    results = {}
    print("\n=== Fetching from GitHub (JoshCBruce/fantasy-data) ===\n")

    # ── Fetch driver data ──
    print("Fetching driver data...")
    driver_round_points = {}  # {abbrev: {round_num: totalPoints}}

    for abbrev in ALL_DRIVERS:
        url = GITHUB_DRIVER_URL.format(abbrev=abbrev)
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                driver_data = resp.json()
                races = driver_data.get("races", [])
                for race in races:
                    rnd = int(race["round"])
                    if target_round and rnd != target_round:
                        continue
                    pts = race.get("totalPoints", 0)
                    if rnd not in driver_round_points:
                        driver_round_points[rnd] = {}
                    # Handle duplicate round entries (team swaps) — take last entry
                    driver_round_points[rnd][abbrev] = pts
                print(f"  {abbrev}: {len(races)} rounds found")
            elif resp.status_code == 404:
                print(f"  {abbrev}: not found on GitHub (may not be in repo yet)")
            else:
                print(f"  {abbrev}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  {abbrev}: Error - {e}")
        time.sleep(0.1)  # Be polite to GitHub

    # ── Fetch constructor data ──
    print("\nFetching constructor data...")
    constructor_round_points = {}  # {round_num: {our_id: totalPoints}}

    for our_id, gh_abbrev in CONSTRUCTOR_MAP.items():
        url = GITHUB_CONSTRUCTOR_URL.format(abbrev=gh_abbrev)
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                con_data = resp.json()
                races = con_data.get("races", [])
                for race in races:
                    rnd = int(race["round"])
                    if target_round and rnd != target_round:
                        continue
                    pts = race.get("totalPoints", 0)
                    if rnd not in constructor_round_points:
                        constructor_round_points[rnd] = {}
                    constructor_round_points[rnd][our_id] = pts
                print(f"  {our_id} ({gh_abbrev}): {len(races)} rounds found")
            elif resp.status_code == 404:
                print(f"  {our_id} ({gh_abbrev}): not found on GitHub")
            else:
                print(f"  {our_id} ({gh_abbrev}): HTTP {resp.status_code}")
        except Exception as e:
            print(f"  {our_id} ({gh_abbrev}): Error - {e}")
        time.sleep(0.1)

    # ── Merge into round structure ──
    all_rounds = set(list(driver_round_points.keys()) + list(constructor_round_points.keys()))
    for rnd in sorted(all_rounds):
        results[rnd] = {
            "drivers": driver_round_points.get(rnd, {}),
            "constructors": constructor_round_points.get(rnd, {}),
        }

    return results


def apply_github_data(data, github_results):
    """Merge GitHub-fetched data into our official points structure."""
    updated_rounds = 0
    for round_num, round_data in github_results.items():
        data = init_round(data, round_num)
        rkey = str(round_num)

        drivers_updated = 0
        for abbrev, pts in round_data.get("drivers", {}).items():
            if abbrev in ALL_DRIVERS:
                data["rounds"][rkey]["drivers"][abbrev] = pts
                drivers_updated += 1

        constructors_updated = 0
        for our_id, pts in round_data.get("constructors", {}).items():
            if our_id in ALL_CONSTRUCTORS:
                data["rounds"][rkey]["constructors"][our_id] = pts
                constructors_updated += 1

        if drivers_updated > 0 or constructors_updated > 0:
            updated_rounds += 1
            print(f"  Round {round_num}: {drivers_updated} drivers, {constructors_updated} constructors updated")

    return data, updated_rounds


# ═══════════════════════════════════════════════════════════
#  Manual input methods
# ═══════════════════════════════════════════════════════════

def set_points(data, round_num, entity_id, points, is_driver=True):
    """Set official points for a driver or constructor in a round."""
    rkey = str(round_num)
    data = init_round(data, round_num)
    bucket = "drivers" if is_driver else "constructors"
    data["rounds"][rkey][bucket][entity_id] = points
    return data


def interactive_input(data, round_num):
    """Interactively input points for a round."""
    data = init_round(data, round_num)
    rkey = str(round_num)
    race = data["rounds"][rkey]["race"]

    print(f"\n=== Round {round_num}: {race} ===")
    print("Enter official F1 Fantasy points for each driver.")
    print("Press Enter to skip (keep existing), type 'q' to quit.\n")

    print("--- DRIVERS ---")
    for driver in ALL_DRIVERS:
        existing = data["rounds"][rkey]["drivers"].get(driver)
        existing_str = f" (current: {existing})" if existing is not None else ""
        try:
            val = input(f"  {driver}{existing_str}: ").strip()
            if val.lower() == 'q':
                break
            if val:
                data["rounds"][rkey]["drivers"][driver] = float(val)
        except (ValueError, EOFError):
            pass

    print("\n--- CONSTRUCTORS ---")
    for constructor in ALL_CONSTRUCTORS:
        existing = data["rounds"][rkey]["constructors"].get(constructor)
        existing_str = f" (current: {existing})" if existing is not None else ""
        try:
            val = input(f"  {constructor}{existing_str}: ").strip()
            if val.lower() == 'q':
                break
            if val:
                data["rounds"][rkey]["constructors"][constructor] = float(val)
        except (ValueError, EOFError):
            pass

    return data


def import_csv(data, round_num, csv_path):
    """Import from CSV: entity_id,points (one per line)."""
    data = init_round(data, round_num)
    rkey = str(round_num)

    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 2:
                continue
            entity_id = parts[0].strip()
            try:
                points = float(parts[1].strip())
            except ValueError:
                continue

            if entity_id in ALL_DRIVERS:
                data["rounds"][rkey]["drivers"][entity_id] = points
            elif entity_id in ALL_CONSTRUCTORS:
                data["rounds"][rkey]["constructors"][entity_id] = points
            else:
                print(f"  Warning: Unknown entity '{entity_id}', skipping")

    return data


# ═══════════════════════════════════════════════════════════
#  Display
# ═══════════════════════════════════════════════════════════

def show_summary(data):
    """Print summary of all stored official points."""
    print("\n=== Official F1 Fantasy Points Summary ===\n")

    if not data.get("rounds"):
        print("No data stored yet.")
        return

    for rkey, rdata in sorted(data.get("rounds", {}).items(), key=lambda x: int(x[0])):
        race = rdata.get("race", f"Round {rkey}")
        drivers = rdata.get("drivers", {})
        constructors = rdata.get("constructors", {})

        filled_d = sum(1 for v in drivers.values() if v is not None)
        filled_c = sum(1 for v in constructors.values() if v is not None)

        print(f"Round {rkey}: {race}")
        print(f"  Drivers: {filled_d}/{len(drivers)} filled")
        print(f"  Constructors: {filled_c}/{len(constructors)} filled")

        if filled_d > 0:
            sorted_d = sorted(
                [(k, v) for k, v in drivers.items() if v is not None],
                key=lambda x: x[1], reverse=True
            )
            print(f"  Top 5: {', '.join(f'{k}={v}' for k, v in sorted_d[:5])}")
            bottom = sorted_d[-3:]
            print(f"  Bottom 3: {', '.join(f'{k}={v}' for k, v in bottom)}")

        if filled_c > 0:
            sorted_c = sorted(
                [(k, v) for k, v in constructors.items() if v is not None],
                key=lambda x: x[1], reverse=True
            )
            print(f"  Top constructors: {', '.join(f'{k}={v}' for k, v in sorted_c[:3])}")
        print()


# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Manage official F1 Fantasy points")
    parser.add_argument("--round", "-r", type=int, help="Round number")
    parser.add_argument("--fetch", "-f", action="store_true",
                        help="Auto-fetch from GitHub (JoshCBruce/fantasy-data)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive input mode")
    parser.add_argument("--input", type=str, help="CSV file to import (entity_id,points)")
    parser.add_argument("--export", "-e", action="store_true", help="Export/sync to web")
    parser.add_argument("--summary", "-s", action="store_true", help="Show summary")
    parser.add_argument("--set", nargs=3, metavar=("ENTITY", "POINTS", "TYPE"),
                        help="Set single entity: --set VER 45 driver")

    args = parser.parse_args()
    data = load_data()

    if args.summary:
        show_summary(data)
        return

    if args.fetch:
        github_results = fetch_from_github(target_round=args.round)
        if github_results:
            data, updated = apply_github_data(data, github_results)
            if updated > 0:
                save_data(data)
                print(f"\nUpdated {updated} round(s) from GitHub.")
            else:
                print("\nNo new data found on GitHub.")
        else:
            print("\nNo data returned from GitHub. The repo may not have 2026 data yet.")
            print("Alternatives:")
            print("  1. Wait for the repo to update after the first 2026 race")
            print("  2. Use --interactive to manually input points")
            print("  3. Use --input to import from CSV")
        show_summary(data)
        return

    if args.set and args.round:
        entity, pts, etype = args.set
        is_driver = etype.lower().startswith('d')
        data = set_points(data, args.round, entity, float(pts), is_driver)
        save_data(data)
        print(f"Set {entity} R{args.round} = {pts} pts")
        return

    if args.interactive and args.round:
        data = interactive_input(data, args.round)
        save_data(data)
        show_summary(data)
        return

    if args.input and args.round:
        data = import_csv(data, args.round, args.input)
        save_data(data)
        show_summary(data)
        return

    if args.export:
        save_data(data)
        show_summary(data)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
