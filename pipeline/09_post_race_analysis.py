"""
Script 09 — Post-Race Data Analysis

After each race weekend, this script analyzes actual race data to produce
insights that F1 fantasy tools typically don't show:

- Normalized race pace (adjusted for pit stops, safety cars, lap 1)
- Average pit stop times per team
- Tyre management scores per driver (degradation across stints)
- Position changes and overtake analysis
- Stint analysis (compound choices, stint lengths)
- Reliability tracking

Input:
    data/raw/jolpica/year{YYYY}/round{N}/results.json
    data/raw/jolpica/year{YYYY}/round{N}/pitstops.json
    data/raw/fastf1/year{YYYY}/round{N}/race.parquet

Output:
    data/predictions/round{N}/post_race_analysis.json

Usage:
    python pipeline/09_post_race_analysis.py --round 2
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    JOLPICA_RAW_DIR,
    FASTF1_RAW_DIR,
    PREDICTIONS_DIR,
    SEED_DIR,
    CANCELLED_ROUNDS_2026,
)


# -- Load helpers --------------------------------------------------------------

def load_race_results(year: int, round_num: int) -> dict | None:
    """Load race results from Jolpica JSON."""
    path = JOLPICA_RAW_DIR / f"year{year}" / f"round{round_num}" / "results.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    return races[0] if races else None


def load_sprint_results(year: int, round_num: int) -> dict | None:
    """Load sprint results from Jolpica JSON."""
    path = JOLPICA_RAW_DIR / f"year{year}" / f"round{round_num}" / "sprint.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    return races[0] if races else None


def load_pitstops(year: int, round_num: int) -> list[dict]:
    """Load pit stop data from Jolpica JSON."""
    path = JOLPICA_RAW_DIR / f"year{year}" / f"round{round_num}" / "pitstops.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    return races[0].get("PitStops", [])


def _load_laps_parquet(path: Path) -> pd.DataFrame | None:
    """Load lap data from a FastF1 parquet file."""
    try:
        df = pd.read_parquet(path)
        # Standardize column names
        col_map = {}
        if "LapTime_seconds" in df.columns:
            col_map["LapTime_seconds"] = "lap_time"
        elif "LapTime" in df.columns:
            df["lap_time"] = pd.to_timedelta(df["LapTime"]).dt.total_seconds()
        if "Driver" in df.columns:
            col_map["Driver"] = "driver_id"
        if "Compound" in df.columns:
            col_map["Compound"] = "compound"
        if "Stint" in df.columns:
            col_map["Stint"] = "stint"
        if "LapNumber" in df.columns:
            col_map["LapNumber"] = "lap_number"
        if "TyreLife" in df.columns:
            col_map["TyreLife"] = "tyre_life"
        if "Sector1Time_seconds" in df.columns:
            col_map["Sector1Time_seconds"] = "sector_1"
        if "Sector2Time_seconds" in df.columns:
            col_map["Sector2Time_seconds"] = "sector_2"
        if "Sector3Time_seconds" in df.columns:
            col_map["Sector3Time_seconds"] = "sector_3"
        df = df.rename(columns=col_map)
        return df
    except Exception as e:
        print(f"  Warning: could not load laps from {path.name}: {e}")
        return None


def load_sprint_laps(year: int, round_num: int) -> pd.DataFrame | None:
    """Load sprint lap data from FastF1 parquet."""
    path = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}" / "sprint.parquet"
    if not path.exists():
        return None
    return _load_laps_parquet(path)


def load_race_laps(year: int, round_num: int) -> pd.DataFrame | None:
    """Load race lap data from FastF1 parquet."""
    path = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}" / "race.parquet"
    if not path.exists():
        return None
    return _load_laps_parquet(path)


def load_driver_map() -> tuple[dict, dict]:
    """Load driver ID mappings."""
    with open(SEED_DIR / "driver_ids.json") as f:
        data = json.load(f)
    jolpica_to_abbrev = {}
    abbrev_to_name = {}
    for m in data["mappings"]:
        jolpica_to_abbrev[m["jolpica"]] = m["abbrev"]
        abbrev_to_name[m["abbrev"]] = m["full_name"]
    return jolpica_to_abbrev, abbrev_to_name


def load_constructor_map() -> dict:
    """Load constructor ID -> name mapping."""
    with open(SEED_DIR / "constructors.json") as f:
        data = json.load(f)
    return {c["constructor_id"]: c["name"] for c in data["constructors"]}


def load_driver_constructors() -> dict:
    """Load driver abbrev -> constructor_id mapping."""
    with open(SEED_DIR / "drivers.json") as f:
        data = json.load(f)
    return {d["driver_id"]: d["constructor_id"] for d in data["drivers"]}


# -- Analysis functions --------------------------------------------------------

def analyze_race_results(race_data: dict, jolpica_to_abbrev: dict) -> list[dict]:
    """Parse race results into a clean list."""
    results = []
    for r in race_data.get("Results", []):
        driver_id = r.get("Driver", {}).get("driverId", "")
        abbrev = jolpica_to_abbrev.get(driver_id, driver_id[:3].upper())
        constructor = r.get("Constructor", {}).get("constructorId", "")

        status = r.get("status", "Finished")
        is_finished = status.lower() in ["finished"] or status.startswith("+")
        grid = int(r.get("grid", 0))
        position = int(r.get("position", 0)) if is_finished else None
        points = float(r.get("points", 0))

        pos_change = (grid - position) if position and grid else 0

        results.append({
            "driver_id": abbrev,
            "constructor_id": constructor,
            "grid": grid,
            "finish_position": position,
            "status": status,
            "is_finished": is_finished,
            "points": points,
            "positions_gained": pos_change,
        })
    return results


def analyze_sprint_results(sprint_data: dict, jolpica_to_abbrev: dict) -> list[dict]:
    """Parse sprint results into a clean list."""
    results = []
    for r in sprint_data.get("SprintResults", []):
        driver_id = r.get("Driver", {}).get("driverId", "")
        abbrev = jolpica_to_abbrev.get(driver_id, driver_id[:3].upper())
        constructor = r.get("Constructor", {}).get("constructorId", "")

        status = r.get("status", "Finished")
        is_finished = status.lower() in ["finished"] or status.startswith("+")
        grid = int(r.get("grid", 0))
        position = int(r.get("position", 0)) if is_finished else None
        points = float(r.get("points", 0))

        pos_change = (grid - position) if position and grid else 0

        results.append({
            "driver_id": abbrev,
            "constructor_id": constructor,
            "grid": grid,
            "finish_position": position,
            "status": status,
            "is_finished": is_finished,
            "points": points,
            "positions_gained": pos_change,
        })
    return results


def analyze_pitstops(pitstops: list[dict], jolpica_to_abbrev: dict) -> dict:
    """Analyze pit stop performance per team."""
    team_stops = {}
    driver_stops = {}

    for stop in pitstops:
        driver_id = stop.get("driverId", "")
        abbrev = jolpica_to_abbrev.get(driver_id, driver_id[:3].upper())
        duration_str = stop.get("duration", "0")
        try:
            duration = float(duration_str)
        except (ValueError, TypeError):
            # Handle "1:23.456" format
            parts = duration_str.split(":")
            if len(parts) == 2:
                duration = float(parts[0]) * 60 + float(parts[1])
            else:
                continue

        if abbrev not in driver_stops:
            driver_stops[abbrev] = []
        driver_stops[abbrev].append({
            "lap": int(stop.get("lap", 0)),
            "stop_number": int(stop.get("stop", 0)),
            "duration": round(duration, 3),
        })

    return {
        "driver_stops": driver_stops,
    }


def analyze_race_pace(laps_df: pd.DataFrame) -> dict:
    """
    Compute normalized race pace per driver.

    Excludes: lap 1 (standing start), safety car laps, in/out laps, and
    outlier laps (>107% of driver's median).
    """
    if laps_df is None or laps_df.empty or "lap_time" not in laps_df.columns:
        return {}

    df = laps_df.copy()
    df = df[df["lap_time"].notna() & (df["lap_time"] > 0)]

    # Exclude lap 1
    if "lap_number" in df.columns:
        df = df[df["lap_number"] > 1]

    # Exclude obvious outliers (pit in/out, SC)
    driver_medians = df.groupby("driver_id")["lap_time"].transform("median")
    df = df[df["lap_time"] < driver_medians * 1.07]

    pace_data = {}
    for driver_id, group in df.groupby("driver_id"):
        times = group["lap_time"].values
        if len(times) < 5:
            continue

        avg_pace = float(np.mean(times))
        median_pace = float(np.median(times))
        best_pace = float(np.min(times))
        consistency = float(np.std(times))

        pace_data[driver_id] = {
            "avg_race_pace": round(avg_pace, 3),
            "median_race_pace": round(median_pace, 3),
            "best_race_lap": round(best_pace, 3),
            "consistency_std": round(consistency, 3),
            "laps_analyzed": len(times),
        }

    # Compute pace delta to leader
    if pace_data:
        best_avg = min(d["avg_race_pace"] for d in pace_data.values())
        for d in pace_data.values():
            d["pace_delta_to_leader"] = round(d["avg_race_pace"] - best_avg, 3)

    return pace_data


def analyze_tyre_management(laps_df: pd.DataFrame) -> dict:
    """
    Analyze tyre degradation per driver per stint.

    Returns degradation rate (seconds/lap) and management score.
    """
    if laps_df is None or laps_df.empty:
        return {}

    df = laps_df.copy()
    required = ["driver_id", "lap_time", "stint"]
    if not all(c in df.columns for c in required):
        return {}

    df = df[df["lap_time"].notna() & (df["lap_time"] > 0)]

    # Exclude lap 1 and outliers
    if "lap_number" in df.columns:
        df = df[df["lap_number"] > 1]
    driver_medians = df.groupby("driver_id")["lap_time"].transform("median")
    df = df[df["lap_time"] < driver_medians * 1.07]

    tyre_data = {}
    for driver_id, driver_group in df.groupby("driver_id"):
        stints = []
        for stint_num, stint_group in driver_group.groupby("stint"):
            times = stint_group.sort_values("lap_number" if "lap_number" in stint_group.columns else stint_group.index)["lap_time"].values
            if len(times) < 4:
                continue

            compound = stint_group["compound"].iloc[0] if "compound" in stint_group.columns else "UNKNOWN"

            # Linear regression for degradation (seconds per lap)
            x = np.arange(len(times))
            if np.std(x) > 0:
                slope = np.polyfit(x, times, 1)[0]
            else:
                slope = 0

            stints.append({
                "stint": int(stint_num),
                "compound": str(compound),
                "laps": len(times),
                "avg_pace": round(float(np.mean(times)), 3),
                "degradation_rate": round(float(slope), 4),
            })

        if stints:
            avg_deg = np.mean([s["degradation_rate"] for s in stints])
            # Management score: lower degradation = better management (0-100)
            # Typical range: 0.01 (excellent) to 0.15 (poor)
            mgmt_score = max(0, min(100, round(100 - (avg_deg / 0.15 * 100))))

            tyre_data[driver_id] = {
                "stints": stints,
                "avg_degradation": round(float(avg_deg), 4),
                "management_score": mgmt_score,
            }

    return tyre_data


def build_team_pitstop_summary(
    pitstop_data: dict,
    driver_constructors: dict,
    constructor_names: dict,
) -> list[dict]:
    """Aggregate pit stop times per constructor."""
    team_times: dict[str, list[float]] = {}
    for driver_abbrev, stops in pitstop_data.get("driver_stops", {}).items():
        cid = driver_constructors.get(driver_abbrev, "unknown")
        if cid not in team_times:
            team_times[cid] = []
        for s in stops:
            if s["duration"] < 60:  # Exclude drive-throughs
                team_times[cid].append(s["duration"])

    summary = []
    for cid, times in sorted(team_times.items()):
        if not times:
            continue
        summary.append({
            "constructor_id": cid,
            "constructor_name": constructor_names.get(cid, cid),
            "avg_pitstop": round(float(np.mean(times)), 3),
            "best_pitstop": round(float(np.min(times)), 3),
            "total_stops": len(times),
        })

    summary.sort(key=lambda x: x["avg_pitstop"])
    return summary


# -- Main ---------------------------------------------------------------------

def run_post_race_analysis(round_num: int, year: int = CURRENT_SEASON) -> dict:
    """Run full post-race analysis for a round."""
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Post-Race Analysis for {year} Round {round_num}")
    print("=" * 70)

    jolpica_to_abbrev, abbrev_to_name = load_driver_map()
    constructor_names = load_constructor_map()
    driver_constructors = load_driver_constructors()

    # Load race info
    with open(SEED_DIR / "races.json") as f:
        races = json.load(f)["races"]
    race_info = next((r for r in races if r["round"] == round_num), None)
    race_name = race_info["name"] if race_info else f"Round {round_num}"
    is_sprint = race_info.get("sprint", False) if race_info else False

    output = {
        "race": race_name,
        "round": round_num,
        "season": year,
        "type": "post_race_analysis",
        "is_sprint_weekend": is_sprint,
    }

    # 1. Race results
    print("\n[1] Loading race results...")
    race_data = load_race_results(year, round_num)
    if race_data:
        results = analyze_race_results(race_data, jolpica_to_abbrev)
        output["results"] = results
        print(f"  {len(results)} drivers")
    else:
        print("  No race results found")
        output["results"] = []

    # 2. Pit stops
    print("[2] Analyzing pit stops...")
    pitstops_raw = load_pitstops(year, round_num)
    pitstop_data = analyze_pitstops(pitstops_raw, jolpica_to_abbrev)
    team_pitstops = build_team_pitstop_summary(pitstop_data, driver_constructors, constructor_names)
    output["pitstops"] = {
        "by_driver": pitstop_data.get("driver_stops", {}),
        "by_team": team_pitstops,
    }
    print(f"  {len(team_pitstops)} teams with pit stop data")

    # 3. Race pace analysis (from FastF1 laps)
    print("[3] Analyzing race pace...")
    laps_df = load_race_laps(year, round_num)
    pace_data = analyze_race_pace(laps_df)
    output["race_pace"] = pace_data
    print(f"  {len(pace_data)} drivers with pace data")

    # 4. Tyre management
    print("[4] Analyzing tyre management...")
    tyre_data = analyze_tyre_management(laps_df)
    output["tyre_management"] = tyre_data
    print(f"  {len(tyre_data)} drivers with tyre data")

    # 5. Sprint analysis (if sprint weekend)
    if is_sprint:
        print("\n[5] Sprint Weekend — Analyzing sprint session...")

        # Sprint results
        sprint_data = load_sprint_results(year, round_num)
        if sprint_data:
            sprint_results = analyze_sprint_results(sprint_data, jolpica_to_abbrev)
            output["sprint_results"] = sprint_results
            print(f"  Sprint results: {len(sprint_results)} drivers")
        else:
            output["sprint_results"] = []
            print("  No sprint results found")

        # Sprint pace & tyre management (from FastF1 sprint laps)
        sprint_laps = load_sprint_laps(year, round_num)
        sprint_pace = analyze_race_pace(sprint_laps)
        output["sprint_pace"] = sprint_pace
        print(f"  Sprint pace: {len(sprint_pace)} drivers with pace data")

        sprint_tyre = analyze_tyre_management(sprint_laps)
        output["sprint_tyre_management"] = sprint_tyre
        print(f"  Sprint tyre management: {len(sprint_tyre)} drivers with tyre data")

    # Save
    output_dir = PREDICTIONS_DIR / f"round{round_num}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "post_race_analysis.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved -> {output_path}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Post-race data analysis")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--year", type=int, default=CURRENT_SEASON)
    args = parser.parse_args()
    run_post_race_analysis(args.round, args.year)


if __name__ == "__main__":
    main()
