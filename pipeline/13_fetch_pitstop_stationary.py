"""
Script 13 — Build Website Pit Stop Stationary File

Reads the canonical OpenF1 stationary times already fetched by
`13_fetch_openf1_overtakes.py` and reformats them into a per-constructor
file the website consumes for the "Pit Stops (stationary)" tooltip.

Single source of truth: data/overtakes/year{Y}/round{N}/overtakes.json
(populated under the `pitstops.by_driver` key with stop_duration values).

This script does NOT call OpenF1 — it just reformats. If the source file
doesn't have `pitstops`, re-run `13_fetch_openf1_overtakes.py` first
(typically OpenF1's stop_duration becomes available within ~24h of the race).

Output:
    web/public/data/pitstops_round{N}.json

Usage:
    python pipeline/13_fetch_pitstop_stationary.py --round 6
    python pipeline/13_fetch_pitstop_stationary.py --all
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    DATA_DIR,
    SEED_DIR,
    WEB_DATA_DIR,
    CANCELLED_ROUNDS_2026,
)


def load_driver_to_constructor() -> dict:
    """Load driver_id -> constructor_id mapping."""
    with open(SEED_DIR / "drivers.json") as f:
        drivers = json.load(f)
    return {d["driver_id"]: d["constructor_id"] for d in drivers["drivers"]}


def load_overtakes_pitstops(year: int, round_num: int) -> dict | None:
    """Load the `pitstops.by_driver` block from the OpenF1 overtakes file.

    Returns dict mapping driver_abbrev -> [list of stop_duration floats],
    or None if the file or pitstops block doesn't exist.
    """
    path = DATA_DIR / "overtakes" / f"year{year}" / f"round{round_num}" / "overtakes.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    pitstops = data.get("pitstops")
    if not pitstops or not pitstops.get("by_driver"):
        return None

    result: dict[str, list[float]] = {}
    for abbrev, stops in pitstops["by_driver"].items():
        times = [s["stop_duration"] for s in stops if s.get("stop_duration") is not None]
        if times:
            result[abbrev] = times
    return result


def by_driver_to_by_constructor(
    by_driver: dict[str, list[float]],
    driver_to_constructor: dict[str, str],
) -> dict[str, list[float]]:
    """Aggregate stationary times by constructor."""
    by_constructor: dict[str, list[float]] = {}
    for abbrev, times in by_driver.items():
        cid = driver_to_constructor.get(abbrev)
        if not cid:
            continue
        by_constructor.setdefault(cid, []).extend(round(t, 1) for t in times)
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
    """Build website pitstop file for a single round."""
    print(f"\n  Round {round_num}:")

    by_driver = load_overtakes_pitstops(year, round_num)
    if not by_driver:
        print(f"    No pitstops in data/overtakes/year{year}/round{round_num}/overtakes.json")
        print(f"    Run: python pipeline/13_fetch_openf1_overtakes.py --year {year} --round {round_num}")
        return False

    drv_to_cons = load_driver_to_constructor()
    by_constructor = by_driver_to_by_constructor(by_driver, drv_to_cons)

    if not by_constructor:
        print(f"    No constructor mapping found for any driver")
        return False

    path = save_pitstop_file(round_num, by_constructor)
    print(f"    Saved -> {path}")

    # Summary
    total_stops = sum(len(v) for v in by_constructor.values())
    print(f"    {total_stops} stops across {len(by_constructor)} constructors")
    for cid, times in sorted(by_constructor.items(), key=lambda x: min(x[1])):
        best = min(times)
        avg = sum(times) / len(times)
        print(f"      {cid:<18s} best={best:.1f}s avg={avg:.1f}s stops={len(times)}")

    return True


def load_races() -> list[dict]:
    with open(SEED_DIR / "races.json") as f:
        return json.load(f)["races"]


def main():
    parser = argparse.ArgumentParser(description="Build website pit stop stationary file")
    parser.add_argument("--round", "-r", type=int, help="Round number")
    parser.add_argument("--all", action="store_true", help="Process all completed rounds")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON)
    args = parser.parse_args()

    print("=" * 70)
    print("BoxBoxF1Fantasy — Pit Stop Stationary File (from OpenF1 cache)")
    print("=" * 70)

    if args.all:
        races = load_races()
        for race in races:
            rnd = race["round"]
            if rnd in CANCELLED_ROUNDS_2026:
                continue
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
