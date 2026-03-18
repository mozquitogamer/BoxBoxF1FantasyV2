"""
Script 10 — Free Practice Data Analysis

Crunches FP session data into detailed analysis for the website:
- Qualifying pace (best lap, best 3/5 avg)
- Long run / race pace prediction
- Tyre degradation per compound
- Sector analysis
- Temperature-pace correlation
- Consistency metrics
- Speed trap data (if available)

This goes beyond predictions — it's raw data analysis that F1 fantasy
tools don't typically provide.

Input:
    data/processed/laps/round{N}/all_laps_fp*.parquet
    data/processed/features/round{N}/features.parquet

Output:
    data/predictions/round{N}/fp_analysis.json

Usage:
    python pipeline/10_fp_analysis.py --round 3
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
    LAPS_DIR,
    FEATURES_DIR,
    PREDICTIONS_DIR,
    SEED_DIR,
    CANCELLED_ROUNDS_2026,
)


# -- Load helpers --------------------------------------------------------------

def load_fp_laps(round_num: int) -> pd.DataFrame | None:
    """Load all FP session laps for a round."""
    round_dir = LAPS_DIR / f"round{round_num}"
    if not round_dir.exists():
        return None

    all_laps = []
    for fp_file in sorted(round_dir.glob("all_laps_fp*.parquet")):
        try:
            df = pd.read_parquet(fp_file)
            session = fp_file.stem.replace("all_laps_", "").upper()
            df["session"] = session
            all_laps.append(df)
        except Exception:
            continue

    if not all_laps:
        return None

    combined = pd.concat(all_laps, ignore_index=True)
    # Ensure lap_time column exists
    if "lap_time" not in combined.columns and "lap_time_seconds" in combined.columns:
        combined["lap_time"] = combined["lap_time_seconds"]

    return combined


def load_driver_info() -> tuple[dict, dict]:
    """Load driver name and constructor mappings."""
    with open(SEED_DIR / "drivers.json") as f:
        drivers = json.load(f)["drivers"]

    abbrev_to_name = {d["driver_id"]: f"{d['first_name']} {d['last_name']}" for d in drivers}
    abbrev_to_constructor = {d["driver_id"]: d["constructor_id"] for d in drivers}
    return abbrev_to_name, abbrev_to_constructor


# -- Analysis functions --------------------------------------------------------

def analyze_qualifying_pace(df: pd.DataFrame) -> dict:
    """
    Analyze single-lap qualifying pace from FP data.
    Uses short runs (stints of 1-3 laps) as quali simulation proxy.
    """
    if df is None or df.empty or "lap_time" not in df.columns:
        return {}

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    # Exclude obvious outliers (in/out laps)
    driver_medians = clean.groupby("driver_id")["lap_time"].transform("median")
    clean = clean[clean["lap_time"] < driver_medians * 1.05]

    result = {}
    for driver_id, group in clean.groupby("driver_id"):
        times = group["lap_time"].sort_values().values

        best_lap = float(times[0]) if len(times) > 0 else None
        best_3_avg = float(np.mean(times[:3])) if len(times) >= 3 else best_lap
        best_5_avg = float(np.mean(times[:5])) if len(times) >= 5 else best_3_avg

        result[driver_id] = {
            "best_lap": round(best_lap, 3) if best_lap else None,
            "best_3_avg": round(best_3_avg, 3) if best_3_avg else None,
            "best_5_avg": round(best_5_avg, 3) if best_5_avg else None,
            "total_laps": len(times),
        }

    # Rank and delta
    if result:
        best_overall = min(d["best_lap"] for d in result.values() if d["best_lap"])
        for d in result.values():
            if d["best_lap"]:
                d["gap_to_fastest"] = round(d["best_lap"] - best_overall, 3)

    return result


def analyze_long_run_pace(df: pd.DataFrame, min_stint_laps: int = 5) -> dict:
    """
    Analyze long run pace (predicted race pace).

    Long runs = stints of 5+ laps on the same compound.
    Excludes in/out laps and lap 1 of each stint.
    """
    if df is None or df.empty:
        return {}

    required = ["driver_id", "lap_time", "stint"]
    if not all(c in df.columns for c in required):
        return {}

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, driver_group in clean.groupby("driver_id"):
        long_runs = []
        for stint, stint_group in driver_group.groupby("stint"):
            if len(stint_group) < min_stint_laps:
                continue

            # Sort by lap number and skip first lap of stint (out lap/cold tyres)
            if "lap_number" in stint_group.columns:
                stint_sorted = stint_group.sort_values("lap_number")
            else:
                stint_sorted = stint_group

            times = stint_sorted["lap_time"].values[1:]  # Skip first lap
            if len(times) < min_stint_laps - 1:
                continue

            # Remove outliers within stint
            median = np.median(times)
            times = times[times < median * 1.05]

            compound = stint_sorted["compound"].iloc[0] if "compound" in stint_sorted.columns else "UNKNOWN"

            long_runs.append({
                "compound": str(compound),
                "laps": len(times),
                "avg_pace": round(float(np.mean(times)), 3),
                "best_pace": round(float(np.min(times)), 3),
                "consistency": round(float(np.std(times)), 3),
            })

        if long_runs:
            overall_avg = np.mean([lr["avg_pace"] for lr in long_runs])
            result[driver_id] = {
                "runs": long_runs,
                "avg_long_run_pace": round(float(overall_avg), 3),
                "total_long_run_laps": sum(lr["laps"] for lr in long_runs),
            }

    # Rank
    if result:
        best_pace = min(d["avg_long_run_pace"] for d in result.values())
        for d in result.values():
            d["gap_to_fastest"] = round(d["avg_long_run_pace"] - best_pace, 3)

    return result


def analyze_tyre_degradation(df: pd.DataFrame) -> dict:
    """
    Analyze tyre degradation per driver per compound.

    Returns degradation rate (seconds/lap) for each compound used.
    """
    if df is None or df.empty:
        return {}

    required = ["driver_id", "lap_time", "stint", "compound"]
    if not all(c in df.columns for c in required):
        return {}

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, driver_group in clean.groupby("driver_id"):
        compounds = {}
        for (stint, compound), stint_group in driver_group.groupby(["stint", "compound"]):
            if len(stint_group) < 4:
                continue

            if "lap_number" in stint_group.columns:
                stint_sorted = stint_group.sort_values("lap_number")
            else:
                stint_sorted = stint_group

            times = stint_sorted["lap_time"].values
            # Remove first lap and outliers
            times = times[1:]
            median = np.median(times) if len(times) > 0 else 0
            times = times[times < median * 1.05]

            if len(times) < 3:
                continue

            x = np.arange(len(times))
            slope = np.polyfit(x, times, 1)[0]

            compound_str = str(compound)
            if compound_str not in compounds:
                compounds[compound_str] = []
            compounds[compound_str].append({
                "stint": int(stint),
                "laps": len(times),
                "deg_rate": round(float(slope), 4),
                "avg_pace": round(float(np.mean(times)), 3),
            })

        if compounds:
            result[driver_id] = {}
            for comp, stints in compounds.items():
                avg_deg = np.mean([s["deg_rate"] for s in stints])
                result[driver_id][comp] = {
                    "stints": stints,
                    "avg_degradation": round(float(avg_deg), 4),
                }

    return result


def analyze_sector_performance(df: pd.DataFrame) -> dict:
    """Analyze best sector times per driver."""
    if df is None or df.empty:
        return {}

    sector_cols = []
    for name in ["sector_1", "sector_2", "sector_3"]:
        if name in df.columns:
            sector_cols.append(name)

    if not sector_cols:
        return {}

    result = {}
    for driver_id, group in df.groupby("driver_id"):
        sectors = {}
        for col in sector_cols:
            valid = group[col].dropna()
            valid = valid[valid > 0]
            if len(valid) > 0:
                sectors[col] = {
                    "best": round(float(valid.min()), 3),
                    "avg": round(float(valid.mean()), 3),
                    "median": round(float(valid.median()), 3),
                }

        if sectors:
            # Theoretical best
            theoretical = sum(s["best"] for s in sectors.values())
            sectors["theoretical_best"] = round(theoretical, 3)
            result[driver_id] = sectors

    return result


def analyze_consistency(df: pd.DataFrame) -> dict:
    """
    Measure driver consistency: coefficient of variation, lap time spread,
    percentage of laps within 102% of personal best.
    """
    if df is None or df.empty or "lap_time" not in df.columns:
        return {}

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, group in clean.groupby("driver_id"):
        times = group["lap_time"].values
        if len(times) < 5:
            continue

        best = np.min(times)
        median = np.median(times)
        std = np.std(times)
        cv = std / np.mean(times) if np.mean(times) > 0 else 0

        # Percentage within 102% of personal best
        within_102 = np.sum(times < best * 1.02) / len(times) * 100

        result[driver_id] = {
            "cv": round(float(cv), 4),
            "std": round(float(std), 3),
            "median_lap": round(float(median), 3),
            "best_lap": round(float(best), 3),
            "laps_within_102pct": round(float(within_102), 1),
            "total_laps": len(times),
        }

    return result


def analyze_temperature_correlation(df: pd.DataFrame) -> dict | None:
    """
    Analyze correlation between track/air temperature and lap times.
    Returns per-driver correlation if temperature data exists.
    """
    if df is None or df.empty:
        return None

    temp_col = None
    for candidate in ["track_temperature", "air_temperature", "TrackTemp", "AirTemp"]:
        if candidate in df.columns:
            temp_col = candidate
            break

    if temp_col is None:
        return None

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0) & df[temp_col].notna()].copy()
    if len(clean) < 20:
        return None

    result = {}
    for driver_id, group in clean.groupby("driver_id"):
        if len(group) < 10:
            continue
        corr = group["lap_time"].corr(group[temp_col])
        if pd.notna(corr):
            result[driver_id] = {
                "correlation": round(float(corr), 3),
                "temp_type": temp_col,
                "interpretation": (
                    "faster in heat" if corr < -0.1 else
                    "slower in heat" if corr > 0.1 else
                    "neutral"
                ),
            }

    return result if result else None


def analyze_session_evolution(df: pd.DataFrame) -> dict | None:
    """
    Track how pace evolved across FP1 → FP2 → FP3.
    Shows which drivers improved most from early to late sessions.
    """
    if df is None or df.empty or "session" not in df.columns:
        return None

    sessions = df["session"].unique()
    if len(sessions) < 2:
        return None

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, driver_group in clean.groupby("driver_id"):
        session_paces = {}
        for session, sess_group in driver_group.groupby("session"):
            best = sess_group["lap_time"].min()
            session_paces[session] = round(float(best), 3)

        if len(session_paces) >= 2:
            sorted_sessions = sorted(session_paces.keys())
            first = session_paces[sorted_sessions[0]]
            last = session_paces[sorted_sessions[-1]]
            improvement = round(first - last, 3)

            result[driver_id] = {
                "sessions": session_paces,
                "improvement": improvement,
                "improved": improvement > 0,
            }

    return result if result else None


# -- Main ---------------------------------------------------------------------

def run_fp_analysis(round_num: int, year: int = CURRENT_SEASON) -> dict:
    """Run full FP analysis for a round."""
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — FP Analysis for {year} Round {round_num}")
    print("=" * 70)

    # Load race name
    with open(SEED_DIR / "races.json") as f:
        races = json.load(f)["races"]
    race_name = next((r["name"] for r in races if r["round"] == round_num), f"Round {round_num}")

    abbrev_to_name, abbrev_to_constructor = load_driver_info()

    output = {
        "race": race_name,
        "round": round_num,
        "season": year,
        "type": "fp_analysis",
    }

    # Load laps
    print("\nLoading FP lap data...")
    laps_df = load_fp_laps(round_num)
    if laps_df is None or laps_df.empty:
        print("  No FP lap data found!")
        output["error"] = "No FP data available"
        return output

    sessions = laps_df["session"].unique() if "session" in laps_df.columns else []
    print(f"  Loaded {len(laps_df):,} laps across sessions: {sorted(sessions)}")

    # 1. Qualifying pace
    print("\n[1] Analyzing qualifying pace (short runs)...")
    output["qualifying_pace"] = analyze_qualifying_pace(laps_df)
    print(f"  {len(output['qualifying_pace'])} drivers")

    # 2. Long run / race pace
    print("[2] Analyzing long run pace (predicted race pace)...")
    output["long_run_pace"] = analyze_long_run_pace(laps_df)
    print(f"  {len(output['long_run_pace'])} drivers with long runs")

    # 3. Tyre degradation
    print("[3] Analyzing tyre degradation...")
    output["tyre_degradation"] = analyze_tyre_degradation(laps_df)
    print(f"  {len(output['tyre_degradation'])} drivers")

    # 4. Sector analysis
    print("[4] Analyzing sector performance...")
    output["sectors"] = analyze_sector_performance(laps_df)
    print(f"  {len(output['sectors'])} drivers")

    # 5. Consistency
    print("[5] Analyzing consistency...")
    output["consistency"] = analyze_consistency(laps_df)
    print(f"  {len(output['consistency'])} drivers")

    # 6. Temperature correlation
    print("[6] Checking temperature-pace correlation...")
    temp_data = analyze_temperature_correlation(laps_df)
    if temp_data:
        output["temperature"] = temp_data
        print(f"  {len(temp_data)} drivers")
    else:
        print("  No temperature data available")

    # 7. Session evolution
    print("[7] Analyzing session evolution (FP1→FP2→FP3)...")
    evolution = analyze_session_evolution(laps_df)
    if evolution:
        output["session_evolution"] = evolution
        print(f"  {len(evolution)} drivers")
    else:
        print("  Not enough sessions")

    # Save
    output_dir = PREDICTIONS_DIR / f"round{round_num}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "fp_analysis.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved -> {output_path}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Free Practice data analysis")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--year", type=int, default=CURRENT_SEASON)
    args = parser.parse_args()
    run_fp_analysis(args.round, args.year)


if __name__ == "__main__":
    main()
