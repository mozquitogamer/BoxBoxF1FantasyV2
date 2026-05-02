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
    """Load all weekend session laps for a round.

    Regular weekends pull FP1 + FP2 + FP3. Sprint weekends pull FP1 +
    Sprint Qualifying — those are the only on-track sessions before the
    Sunday quali/race deadline.
    """
    round_dir = LAPS_DIR / f"round{round_num}"
    if not round_dir.exists():
        return None

    all_laps = []
    for lap_file in sorted(round_dir.glob("all_laps_*.parquet")):
        try:
            df = pd.read_parquet(lap_file)
            session = lap_file.stem.replace("all_laps_", "").upper()
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

    # Normalize column names so analysis functions find what they expect
    rename_map = {}
    if "stint_number" in combined.columns and "stint" not in combined.columns:
        rename_map["stint_number"] = "stint"
    if "Driver" in combined.columns and "driver_id" not in combined.columns:
        rename_map["Driver"] = "driver_id"
    if "Compound" in combined.columns and "compound" not in combined.columns:
        rename_map["Compound"] = "compound"
    if "LapNumber" in combined.columns and "lap_number" not in combined.columns:
        rename_map["LapNumber"] = "lap_number"
    if "TyreLife" in combined.columns and "tyre_life" not in combined.columns:
        rename_map["TyreLife"] = "tyre_life"
    if rename_map:
        combined.rename(columns=rename_map, inplace=True)

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


def analyze_speed_trap(df: pd.DataFrame) -> dict | None:
    """
    Analyze top speed / speed trap data if available in the telemetry.
    Returns per-driver top speed stats.
    """
    if df is None or df.empty:
        return None

    speed_col = None
    for candidate in ["speed_trap", "top_speed", "SpeedST", "SpeedI1", "SpeedI2", "SpeedFL"]:
        if candidate in df.columns:
            speed_col = candidate
            break

    if speed_col is None:
        return None

    clean = df[df[speed_col].notna() & (df[speed_col] > 0)].copy()
    if len(clean) < 10:
        return None

    result = {}
    for driver_id, group in clean.groupby("driver_id"):
        speeds = group[speed_col].values
        if len(speeds) < 2:
            continue
        result[driver_id] = {
            "top_speed": round(float(np.max(speeds)), 1),
            "avg_speed": round(float(np.mean(speeds)), 1),
            "median_speed": round(float(np.median(speeds)), 1),
            "speed_col_used": speed_col,
        }

    if result:
        best_top = max(d["top_speed"] for d in result.values())
        for d in result.values():
            d["gap_to_fastest"] = round(d["top_speed"] - best_top, 1)

    return result if result else None


def analyze_temperature_pace(df: pd.DataFrame) -> dict | None:
    """
    Analyze how each driver's pace changes with temperature.
    Groups laps by temperature ranges and shows avg pace per range.
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

    clean = df[
        df["lap_time"].notna() & (df["lap_time"] > 0) & df[temp_col].notna()
    ].copy()
    if len(clean) < 20:
        return None

    # Define temperature bins
    temp_min = clean[temp_col].min()
    temp_max = clean[temp_col].max()
    temp_range = temp_max - temp_min

    if temp_range < 3:
        return None  # Not enough temperature variation

    # Create 3-4 bins dynamically
    n_bins = min(4, max(2, int(temp_range / 5)))
    bins = np.linspace(temp_min, temp_max + 0.1, n_bins + 1)
    labels = [f"{bins[i]:.0f}-{bins[i+1]:.0f}" for i in range(len(bins) - 1)]
    clean["temp_bin"] = pd.cut(clean[temp_col], bins=bins, labels=labels, include_lowest=True)

    result = {}
    for driver_id, group in clean.groupby("driver_id"):
        if len(group) < 10:
            continue

        temp_paces = {}
        for temp_bin, bin_group in group.groupby("temp_bin", observed=True):
            if len(bin_group) >= 3:
                times = bin_group["lap_time"].values
                # Remove outliers
                median = np.median(times)
                times = times[times < median * 1.05]
                if len(times) >= 2:
                    temp_paces[str(temp_bin)] = {
                        "avg_pace": round(float(np.mean(times)), 3),
                        "laps": len(times),
                    }

        if len(temp_paces) >= 2:
            result[driver_id] = {
                "temp_type": temp_col,
                "pace_by_temp_range": temp_paces,
            }

    return result if result else None


def analyze_stint_breakdown(df: pd.DataFrame) -> dict:
    """
    Show each driver's stints with: compound, lap count, first-lap pace,
    last-lap pace, degradation rate, avg pace.
    Helps identify who manages tyres better on long runs.
    """
    if df is None or df.empty:
        return {}

    required = ["driver_id", "lap_time", "stint"]
    if not all(c in df.columns for c in required):
        return {}

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, driver_group in clean.groupby("driver_id"):
        stints = []
        for stint, stint_group in driver_group.groupby("stint"):
            if len(stint_group) < 3:
                continue

            if "lap_number" in stint_group.columns:
                stint_sorted = stint_group.sort_values("lap_number")
            else:
                stint_sorted = stint_group

            times = stint_sorted["lap_time"].values
            compound = str(stint_sorted["compound"].iloc[0]) if "compound" in stint_sorted.columns else "UNKNOWN"
            session = str(stint_sorted["session"].iloc[0]) if "session" in stint_sorted.columns else "?"

            # Remove first lap (out lap / cold tyres) for pace analysis
            pace_times = times[1:] if len(times) > 1 else times
            # Remove extreme outliers for calculations
            if len(pace_times) > 2:
                median = np.median(pace_times)
                pace_clean = pace_times[pace_times < median * 1.08]
            else:
                pace_clean = pace_times

            if len(pace_clean) < 2:
                continue

            # Degradation: linear fit
            x = np.arange(len(pace_clean))
            slope = float(np.polyfit(x, pace_clean, 1)[0]) if len(pace_clean) >= 3 else 0.0

            stints.append({
                "stint": int(stint),
                "session": session,
                "compound": compound,
                "total_laps": len(times),
                "first_lap_pace": round(float(times[0]), 3),
                "last_lap_pace": round(float(times[-1]), 3),
                "avg_pace": round(float(np.mean(pace_clean)), 3),
                "best_pace": round(float(np.min(pace_clean)), 3),
                "degradation_rate": round(slope, 4),
            })

        if stints:
            result[driver_id] = {
                "stints": stints,
                "total_stints": len(stints),
                "avg_degradation": round(float(np.mean([s["degradation_rate"] for s in stints])), 4),
            }

    return result


def analyze_sector_rankings(df: pd.DataFrame) -> dict | None:
    """
    Show which driver was fastest in each sector (S1, S2, S3)
    with gaps to the leader.
    """
    if df is None or df.empty:
        return None

    sector_cols = [c for c in ["sector_1", "sector_2", "sector_3"] if c in df.columns]
    if not sector_cols:
        return None

    clean = df.copy()
    result = {}

    for sector in sector_cols:
        valid = clean[clean[sector].notna() & (clean[sector] > 0)]
        if valid.empty:
            continue

        sector_best = {}
        for driver_id, group in valid.groupby("driver_id"):
            times = group[sector].values
            best = float(np.min(times))
            avg_best3 = float(np.mean(np.sort(times)[:3])) if len(times) >= 3 else best
            sector_best[driver_id] = {
                "best": round(best, 3),
                "avg_best_3": round(avg_best3, 3),
            }

        if sector_best:
            fastest = min(d["best"] for d in sector_best.values())
            ranking = []
            for driver_id, d in sector_best.items():
                gap = round(d["best"] - fastest, 3)
                ranking.append({
                    "driver_id": driver_id,
                    "best": d["best"],
                    "avg_best_3": d["avg_best_3"],
                    "gap": gap,
                })
            ranking.sort(key=lambda x: x["best"])
            result[sector] = ranking

    return result if result else None


def analyze_fuel_corrected_pace(df: pd.DataFrame, fuel_effect: float = 0.05) -> dict:
    """
    Estimate fuel-corrected pace.
    In FP, cars run different fuel loads. Early laps tend to be heavier.
    Apply a simple fuel correction of ~0.05s/lap of fuel burn to estimate true race pace.

    For each stint, we assume the first lap is the heaviest and apply
    a progressive correction.
    """
    if df is None or df.empty:
        return {}

    required = ["driver_id", "lap_time", "stint"]
    if not all(c in df.columns for c in required):
        return {}

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, driver_group in clean.groupby("driver_id"):
        corrected_times = []
        for stint, stint_group in driver_group.groupby("stint"):
            if len(stint_group) < 3:
                continue

            if "lap_number" in stint_group.columns:
                stint_sorted = stint_group.sort_values("lap_number")
            else:
                stint_sorted = stint_group

            times = stint_sorted["lap_time"].values[1:]  # Skip first lap (out/cold)
            if len(times) < 2:
                continue

            # Apply fuel correction: earlier laps in stint are heavier
            # We subtract fuel_effect * (laps remaining in stint) from each lap time
            n = len(times)
            corrections = np.array([fuel_effect * (n - 1 - i) for i in range(n)])
            corrected = times - corrections

            # Remove outliers
            median = np.median(corrected)
            corrected = corrected[corrected < median * 1.05]
            corrected_times.extend(corrected.tolist())

        if corrected_times:
            arr = np.array(corrected_times)
            result[driver_id] = {
                "fuel_corrected_avg": round(float(np.mean(arr)), 3),
                "fuel_corrected_best": round(float(np.min(arr)), 3),
                "fuel_corrected_median": round(float(np.median(arr)), 3),
                "laps_used": len(corrected_times),
                "fuel_correction_per_lap": fuel_effect,
            }

    if result:
        best_pace = min(d["fuel_corrected_avg"] for d in result.values())
        for d in result.values():
            d["gap_to_fastest"] = round(d["fuel_corrected_avg"] - best_pace, 3)

    return result


def analyze_improvement_trajectory(df: pd.DataFrame) -> dict | None:
    """
    How much each driver improved from their first run to their last run
    in each session. Shows who found setup improvements.
    """
    if df is None or df.empty or "session" not in df.columns:
        return None

    required = ["driver_id", "lap_time", "stint", "session"]
    if not all(c in df.columns for c in required):
        return None

    clean = df[df["lap_time"].notna() & (df["lap_time"] > 0)].copy()

    result = {}
    for driver_id, driver_group in clean.groupby("driver_id"):
        session_trajectories = {}
        for session, sess_group in driver_group.groupby("session"):
            stints = sorted(sess_group["stint"].unique())
            if len(stints) < 2:
                continue

            # First run: average of first stint
            first_stint = sess_group[sess_group["stint"] == stints[0]]
            if "lap_number" in first_stint.columns:
                first_stint = first_stint.sort_values("lap_number")
            first_times = first_stint["lap_time"].values
            if len(first_times) > 1:
                first_times = first_times[1:]  # Skip out lap
            first_avg = float(np.mean(np.sort(first_times)[:3])) if len(first_times) >= 3 else float(np.mean(first_times))

            # Last run: average of last stint
            last_stint = sess_group[sess_group["stint"] == stints[-1]]
            if "lap_number" in last_stint.columns:
                last_stint = last_stint.sort_values("lap_number")
            last_times = last_stint["lap_time"].values
            if len(last_times) > 1:
                last_times = last_times[1:]  # Skip out lap
            last_avg = float(np.mean(np.sort(last_times)[:3])) if len(last_times) >= 3 else float(np.mean(last_times))

            session_trajectories[session] = {
                "first_run_avg": round(first_avg, 3),
                "last_run_avg": round(last_avg, 3),
                "improvement": round(first_avg - last_avg, 3),
                "improved": first_avg > last_avg,
            }

        if session_trajectories:
            total_improvement = sum(s["improvement"] for s in session_trajectories.values())
            result[driver_id] = {
                "sessions": session_trajectories,
                "total_improvement": round(total_improvement, 3),
                "avg_improvement_per_session": round(total_improvement / len(session_trajectories), 3),
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
    print("[7] Analyzing session evolution (FP1->FP2->FP3)...")
    evolution = analyze_session_evolution(laps_df)
    if evolution:
        output["session_evolution"] = evolution
        print(f"  {len(evolution)} drivers")
    else:
        print("  Not enough sessions")

    # 8. Speed trap / top speed analysis
    print("[8] Analyzing speed trap data...")
    speed_data = analyze_speed_trap(laps_df)
    if speed_data:
        output["speed_trap"] = speed_data
        print(f"  {len(speed_data)} drivers")
    else:
        print("  No speed trap data available")

    # 9. Temperature-pace relationship (by temp ranges)
    print("[9] Analyzing temperature-pace relationship...")
    temp_pace = analyze_temperature_pace(laps_df)
    if temp_pace:
        output["temperature_pace"] = temp_pace
        print(f"  {len(temp_pace)} drivers")
    else:
        print("  Insufficient temperature variation")

    # 10. Stint-by-stint breakdown
    print("[10] Analyzing stint-by-stint breakdown...")
    output["stint_breakdown"] = analyze_stint_breakdown(laps_df)
    print(f"  {len(output['stint_breakdown'])} drivers")

    # 11. Sector-by-sector rankings
    print("[11] Analyzing sector rankings...")
    sector_rankings = analyze_sector_rankings(laps_df)
    if sector_rankings:
        output["sector_rankings"] = sector_rankings
        print(f"  {len(sector_rankings)} sectors analyzed")
    else:
        print("  No sector data available")

    # 12. Fuel-corrected pace estimate
    print("[12] Estimating fuel-corrected pace...")
    output["fuel_corrected_pace"] = analyze_fuel_corrected_pace(laps_df)
    print(f"  {len(output['fuel_corrected_pace'])} drivers")

    # 13. Improvement trajectory
    print("[13] Analyzing improvement trajectory...")
    trajectory = analyze_improvement_trajectory(laps_df)
    if trajectory:
        output["improvement_trajectory"] = trajectory
        print(f"  {len(trajectory)} drivers")
    else:
        print("  Not enough data for trajectory analysis")

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
