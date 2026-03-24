"""
Script 11 — Race Deep Dive Analysis

Comprehensive post-race deep dive producing detailed metrics, lap-by-lap
data, position tracking, gap analysis, tyre degradation, dirty-air effects,
and team-level aggregation.  All output is self-contained JSON + CSV for the
web frontend to render interactive charts.

Input:
    data/raw/fastf1/year{YYYY}/round{N}/race.parquet
    data/seed/driver_ids.json
    data/seed/drivers.json
    data/seed/races.json

Output:
    data/predictions/round{N}/race_deep_dive.json
    data/predictions/round{N}/csv/driver_pace_summary.csv
    data/predictions/round{N}/csv/sector_analysis.csv
    data/predictions/round{N}/csv/stint_analysis.csv
    data/predictions/round{N}/csv/team_summary.csv
    data/predictions/round{N}/csv/speed_trap_analysis.csv
    data/predictions/round{N}/csv/lap_times_all_drivers.csv
    web/public/data/deep_dive_round{N}.json

Usage:
    python pipeline/11_race_deep_dive.py --round 2
    python pipeline/11_race_deep_dive.py --round 3 --year 2026
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    FASTF1_RAW_DIR,
    PREDICTIONS_DIR,
    SEED_DIR,
    WEB_DATA_DIR,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FUEL_EFFECT_PER_LAP = 0.035   # seconds per lap of fuel load
OUTLIER_THRESHOLD = 1.07      # 107 % of driver median

TEAM_COLORS = {
    "red_bull": "#3671C6",
    "ferrari": "#E80020",
    "mercedes": "#27F4D2",
    "mclaren": "#FF8000",
    "aston_martin": "#229971",
    "alpine": "#FF87BC",
    "williams": "#64C4FF",
    "racing_bulls": "#6692FF",
    "audi": "#00E701",
    "haas": "#B6BABD",
    "cadillac": "#FFD700",
}

# ---------------------------------------------------------------------------
# Data-loading helpers
# ---------------------------------------------------------------------------

def load_race_laps(year: int, round_num: int) -> pd.DataFrame | None:
    """Load race lap data from FastF1 parquet."""
    path = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}" / "race.parquet"
    if not path.exists():
        print(f"  ERROR: race.parquet not found at {path}")
        return None
    try:
        df = pd.read_parquet(path)
        print(f"  Loaded {len(df)} raw laps from {path.name}")
        return df
    except Exception as exc:
        print(f"  ERROR loading parquet: {exc}")
        return None


def load_driver_map() -> tuple[dict, dict]:
    """Return (abbrev_to_name, jolpica_to_abbrev) from driver_ids.json."""
    with open(SEED_DIR / "driver_ids.json") as f:
        data = json.load(f)
    jolpica_to_abbrev: dict[str, str] = {}
    abbrev_to_name: dict[str, str] = {}
    for m in data["mappings"]:
        jolpica_to_abbrev[m["jolpica"]] = m["abbrev"]
        abbrev_to_name[m["abbrev"]] = m["full_name"]
    return abbrev_to_name, jolpica_to_abbrev


def load_driver_constructors() -> dict[str, str]:
    """Return driver_abbrev -> constructor_id."""
    with open(SEED_DIR / "drivers.json") as f:
        data = json.load(f)
    return {d["driver_id"]: d["constructor_id"] for d in data["drivers"]}


def load_race_info(round_num: int) -> dict | None:
    path = SEED_DIR / "races.json"
    if not path.exists():
        return None
    with open(path) as f:
        races = json.load(f).get("races", [])
    return next((r for r in races if r["round"] == round_num), None)


# ---------------------------------------------------------------------------
# Data cleaning
# ---------------------------------------------------------------------------

def clean_laps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rigorous cleaning pipeline:
      1. Drop null LapTime
      2. Keep IsAccurate == True
      3. Exclude pit-in / pit-out laps
      4. Exclude lap 1 (standing start)
      5. Exclude non-green-flag laps (TrackStatus not '1' or 1)
      6. Fuel correction
      7. Per-driver outlier removal (>107 % of fuel-corrected median)
    Returns a copy with an added 'fuel_corrected' column.
    """
    n0 = len(df)
    out = df.copy()

    # 1. Null LapTime
    if "LapTime" in out.columns and "LapTime_seconds" not in out.columns:
        out["LapTime_seconds"] = pd.to_timedelta(out["LapTime"]).dt.total_seconds()
    out = out.dropna(subset=["LapTime_seconds"])

    # 2. IsAccurate
    if "IsAccurate" in out.columns:
        out = out[out["IsAccurate"] == True]  # noqa: E712

    # 3. Pit-in / pit-out laps
    for col in ("PitInTime", "PitOutTime"):
        if col in out.columns:
            out = out[out[col].isna()]

    # 4. Lap 1
    if "LapNumber" in out.columns:
        out = out[out["LapNumber"] > 1]

    # 5. Green-flag only
    if "TrackStatus" in out.columns:
        out["_ts"] = out["TrackStatus"].astype(str).str.strip()
        out = out[out["_ts"] == "1"]
        out = out.drop(columns=["_ts"])

    # 6. Fuel correction
    total_laps = df["LapNumber"].max() if "LapNumber" in df.columns else out["LapNumber"].max()
    out["fuel_corrected"] = out["LapTime_seconds"] - (
        (total_laps - out["LapNumber"]) * FUEL_EFFECT_PER_LAP
    )

    # 7. Per-driver outlier removal on fuel-corrected time
    medians = out.groupby("Driver")["fuel_corrected"].transform("median")
    out = out[out["fuel_corrected"] <= medians * OUTLIER_THRESHOLD]

    print(f"  Cleaning: {n0} -> {len(out)} laps "
          f"({n0 - len(out)} removed, total race laps={total_laps})")
    return out


# ---------------------------------------------------------------------------
# Per-driver pace metrics
# ---------------------------------------------------------------------------

def _best_n_avg(times: np.ndarray, n: int) -> float | None:
    if len(times) < n:
        return None
    return float(np.mean(np.sort(times)[:n]))


def compute_driver_metrics(clean: pd.DataFrame) -> dict:
    """Return {driver_abbrev: {metric: value}} for every driver."""
    results: dict[str, dict] = {}

    for drv, grp in clean.groupby("Driver"):
        fc = grp["fuel_corrected"].values
        if len(fc) < 3:
            print(f"  Skipping {drv}: only {len(fc)} clean laps")
            continue

        # --- pace ---
        avg_lap = round(float(np.mean(fc)), 3)
        median_lap = round(float(np.median(fc)), 3)
        best_lap = round(float(np.min(fc)), 3)
        b3 = _best_n_avg(fc, 3)
        b5 = _best_n_avg(fc, 5)
        b10 = _best_n_avg(fc, 10)

        # --- theoretical best ---
        s1 = grp["Sector1Time_seconds"].dropna()
        s2 = grp["Sector2Time_seconds"].dropna()
        s3 = grp["Sector3Time_seconds"].dropna()
        theo = None
        if len(s1) and len(s2) and len(s3):
            theo = round(float(s1.min() + s2.min() + s3.min()), 3)

        # --- consistency ---
        std = round(float(np.std(fc, ddof=1)), 3) if len(fc) > 1 else 0.0
        q1, q3 = np.percentile(fc, [25, 75])
        iqr = round(float(q3 - q1), 3)
        cv = round(float(std / avg_lap * 100), 3) if avg_lap > 0 else 0.0

        # --- sectors ---
        avg_s1 = round(float(s1.mean()), 3) if len(s1) else None
        avg_s2 = round(float(s2.mean()), 3) if len(s2) else None
        avg_s3 = round(float(s3.mean()), 3) if len(s3) else None
        best_s1 = round(float(s1.min()), 3) if len(s1) else None
        best_s2 = round(float(s2.min()), 3) if len(s2) else None
        best_s3 = round(float(s3.min()), 3) if len(s3) else None

        # Sector % of total
        total_s = (avg_s1 or 0) + (avg_s2 or 0) + (avg_s3 or 0)
        pct_s1 = round(avg_s1 / total_s * 100, 1) if total_s else None
        pct_s2 = round(avg_s2 / total_s * 100, 1) if total_s else None
        pct_s3 = round(avg_s3 / total_s * 100, 1) if total_s else None

        # --- speed traps ---
        avg_st = round(float(grp["SpeedST"].mean()), 1) if "SpeedST" in grp.columns and grp["SpeedST"].notna().any() else None
        max_st = round(float(grp["SpeedST"].max()), 1) if avg_st is not None else None
        avg_fl = round(float(grp["SpeedFL"].mean()), 1) if "SpeedFL" in grp.columns and grp["SpeedFL"].notna().any() else None

        # --- position ---
        all_laps = clean if "LapNumber" in clean.columns else grp
        drv_all = grp.sort_values("LapNumber") if "LapNumber" in grp.columns else grp
        start_pos = None
        end_pos = None
        if "Position" in drv_all.columns and len(drv_all):
            start_pos = int(drv_all.iloc[0]["Position"]) if pd.notna(drv_all.iloc[0]["Position"]) else None
            end_pos = int(drv_all.iloc[-1]["Position"]) if pd.notna(drv_all.iloc[-1]["Position"]) else None

        pos_gained = (start_pos - end_pos) if start_pos is not None and end_pos is not None else None

        results[drv] = {
            "avg_lap": avg_lap,
            "median_lap": median_lap,
            "best_lap": best_lap,
            "best_3_lap_avg": round(b3, 3) if b3 is not None else None,
            "best_5_lap_avg": round(b5, 3) if b5 is not None else None,
            "best_10_lap_avg": round(b10, 3) if b10 is not None else None,
            "theoretical_best": theo,
            "lap_time_std": std,
            "lap_time_iqr": iqr,
            "coefficient_of_variation": cv,
            "avg_s1": avg_s1, "avg_s2": avg_s2, "avg_s3": avg_s3,
            "best_s1": best_s1, "best_s2": best_s2, "best_s3": best_s3,
            "pct_time_s1": pct_s1, "pct_time_s2": pct_s2, "pct_time_s3": pct_s3,
            "avg_speed_trap": avg_st,
            "max_speed_trap": max_st,
            "avg_finish_line_speed": avg_fl,
            "start_position": start_pos,
            "end_position": end_pos,
            "positions_gained": pos_gained,
            "laps_analyzed": len(fc),
        }

    # Delta to leader
    if results:
        best_avg = min(r["avg_lap"] for r in results.values())
        for r in results.values():
            r["pace_delta"] = round(r["avg_lap"] - best_avg, 3)

    return results


# ---------------------------------------------------------------------------
# Stint / tyre degradation
# ---------------------------------------------------------------------------

def compute_stint_analysis(clean: pd.DataFrame) -> dict:
    """Per-driver per-stint degradation analysis."""
    if "Stint" not in clean.columns:
        return {}

    stint_data: dict[str, list[dict]] = {}
    for drv, drv_grp in clean.groupby("Driver"):
        stints = []
        for stint_num, sg in drv_grp.groupby("Stint"):
            sg = sg.sort_values("LapNumber")
            fc = sg["fuel_corrected"].values
            if len(fc) < 3:
                continue

            compound = str(sg["Compound"].iloc[0]) if "Compound" in sg.columns else "UNKNOWN"

            # Linear regression slope = degradation rate (seconds/lap)
            x = np.arange(len(fc))
            slope, intercept, _, _, _ = sp_stats.linregress(x, fc)

            start_pace = round(float(np.mean(fc[:3])), 3)
            end_pace = round(float(np.mean(fc[-3:])), 3) if len(fc) >= 3 else start_pace

            stints.append({
                "stint": int(stint_num),
                "compound": compound,
                "laps": len(fc),
                "degradation_rate": round(float(slope), 4),
                "avg_pace": round(float(np.mean(fc)), 3),
                "start_pace": start_pace,
                "end_pace": end_pace,
            })
        if stints:
            stint_data[drv] = stints
    return stint_data


# ---------------------------------------------------------------------------
# Tyre cliff detection
# ---------------------------------------------------------------------------

def detect_tyre_cliffs(stint_data: dict, clean: pd.DataFrame) -> dict:
    """
    Flag stints where the last 3 laps have degradation > 2x the stint average.
    """
    cliffs: dict[str, list[dict]] = {}
    if "Stint" not in clean.columns:
        return cliffs

    for drv, drv_grp in clean.groupby("Driver"):
        drv_cliffs = []
        for stint_num, sg in drv_grp.groupby("Stint"):
            sg = sg.sort_values("LapNumber")
            fc = sg["fuel_corrected"].values
            if len(fc) < 6:
                continue
            # Average lap-to-lap delta for full stint
            deltas = np.diff(fc)
            avg_delta = np.mean(deltas)
            # Last-3-lap deltas
            last3_deltas = deltas[-3:]
            last3_avg = np.mean(last3_deltas)
            if avg_delta > 0 and last3_avg > 2 * avg_delta:
                drv_cliffs.append({
                    "stint": int(stint_num),
                    "avg_deg_per_lap": round(float(avg_delta), 4),
                    "last_3_deg_per_lap": round(float(last3_avg), 4),
                    "cliff_ratio": round(float(last3_avg / avg_delta), 2),
                })
        if drv_cliffs:
            cliffs[drv] = drv_cliffs
    return cliffs


# ---------------------------------------------------------------------------
# Lap-by-lap data (for charts)
# ---------------------------------------------------------------------------

def build_lap_data(clean: pd.DataFrame) -> dict:
    """Return {driver: [{lap, time, fuel_corrected, compound, position}]}."""
    out: dict[str, list[dict]] = {}
    for drv, grp in clean.groupby("Driver"):
        rows = []
        for _, row in grp.sort_values("LapNumber").iterrows():
            entry: dict = {
                "lap": int(row["LapNumber"]),
                "time": round(float(row["LapTime_seconds"]), 3),
                "fuel_corrected": round(float(row["fuel_corrected"]), 3),
            }
            if "Compound" in row.index and pd.notna(row["Compound"]):
                entry["compound"] = str(row["Compound"])
            if "Position" in row.index and pd.notna(row["Position"]):
                entry["position"] = int(row["Position"])
            rows.append(entry)
        out[drv] = rows
    return out


# ---------------------------------------------------------------------------
# Position tracker (uses ALL laps, not just clean)
# ---------------------------------------------------------------------------

def build_position_tracker(df: pd.DataFrame) -> dict:
    """Return {driver: [{lap, position}]} from the raw data."""
    if "Position" not in df.columns or "LapNumber" not in df.columns:
        return {}
    out: dict[str, list[dict]] = {}
    sub = df.dropna(subset=["Position", "LapNumber"])
    for drv, grp in sub.groupby("Driver"):
        rows = []
        for _, row in grp.sort_values("LapNumber").iterrows():
            rows.append({
                "lap": int(row["LapNumber"]),
                "position": int(row["Position"]),
            })
        out[drv] = rows
    return out


# ---------------------------------------------------------------------------
# Gap to leader (cumulative race time)
# ---------------------------------------------------------------------------

def build_gap_to_leader(df: pd.DataFrame) -> dict:
    """
    Cumulative time per driver per lap.  Gap = driver cumulative - leader
    cumulative at that lap.  Uses raw laps (with LapTime_seconds) so we
    capture pit time etc.
    """
    if "LapTime_seconds" not in df.columns or "LapNumber" not in df.columns:
        return {}

    sub = df.dropna(subset=["LapTime_seconds", "LapNumber"]).copy()
    sub = sub.sort_values(["Driver", "LapNumber"])
    sub["cumtime"] = sub.groupby("Driver")["LapTime_seconds"].cumsum()

    # Leader cumulative per lap (minimum cumtime)
    leader = sub.groupby("LapNumber")["cumtime"].min().rename("leader_cum")
    sub = sub.merge(leader, on="LapNumber", how="left")
    sub["gap"] = sub["cumtime"] - sub["leader_cum"]

    out: dict[str, list[dict]] = {}
    for drv, grp in sub.groupby("Driver"):
        rows = []
        for _, row in grp.sort_values("LapNumber").iterrows():
            rows.append({
                "lap": int(row["LapNumber"]),
                "gap": round(float(row["gap"]), 3),
            })
        out[drv] = rows
    return out


# ---------------------------------------------------------------------------
# Dirty-air effect
# ---------------------------------------------------------------------------

def analyze_dirty_air(clean: pd.DataFrame) -> dict:
    """
    Compare driver pace in dirty air (<1.5 s behind car ahead) vs clean air
    (>3 s gap).  Uses the gap derived from cumulative times within the clean
    data itself.
    """
    if "LapNumber" not in clean.columns or "Position" not in clean.columns:
        return {}

    # Build a per-lap gap-to-car-ahead table
    df = clean.sort_values(["LapNumber", "Position"]).copy()

    # Cumulative time per driver
    base = clean.dropna(subset=["LapTime_seconds", "LapNumber"]).copy()
    base = base.sort_values(["Driver", "LapNumber"])
    base["cumtime"] = base.groupby("Driver")["LapTime_seconds"].cumsum()

    # Merge cumtime back
    df = df.merge(
        base[["Driver", "LapNumber", "cumtime"]],
        on=["Driver", "LapNumber"],
        how="left",
    )

    # For each lap, the gap to the car in the position directly ahead
    records = []
    for lap_num, lap_grp in df.groupby("LapNumber"):
        lap_sorted = lap_grp.sort_values("Position")
        for i in range(1, len(lap_sorted)):
            ahead = lap_sorted.iloc[i - 1]
            behind = lap_sorted.iloc[i]
            if pd.isna(ahead["cumtime"]) or pd.isna(behind["cumtime"]):
                continue
            gap_to_ahead = behind["cumtime"] - ahead["cumtime"]
            records.append({
                "Driver": behind["Driver"],
                "LapNumber": int(lap_num),
                "gap_to_ahead": gap_to_ahead,
                "fuel_corrected": behind["fuel_corrected"],
            })

    if not records:
        return {}

    gap_df = pd.DataFrame(records)

    results: dict[str, dict] = {}
    for drv, grp in gap_df.groupby("Driver"):
        dirty = grp[grp["gap_to_ahead"] < 1.5]["fuel_corrected"]
        clean_air = grp[grp["gap_to_ahead"] > 3.0]["fuel_corrected"]
        if len(dirty) < 3 or len(clean_air) < 3:
            continue
        dirty_avg = round(float(dirty.mean()), 3)
        clean_avg = round(float(clean_air.mean()), 3)
        results[drv] = {
            "dirty_air_avg": dirty_avg,
            "clean_air_avg": clean_avg,
            "dirty_air_penalty": round(dirty_avg - clean_avg, 3),
            "dirty_air_laps": len(dirty),
            "clean_air_laps": len(clean_air),
        }
    return results


# ---------------------------------------------------------------------------
# Temperature sensitivity
# ---------------------------------------------------------------------------

def analyze_temp_sensitivity(clean: pd.DataFrame) -> dict:
    """Correlation between track temperature and fuel-corrected lap time."""
    if "track_temperature" not in clean.columns:
        return {}
    results: dict[str, dict] = {}
    for drv, grp in clean.groupby("Driver"):
        temps = grp["track_temperature"].dropna()
        fc = grp.loc[temps.index, "fuel_corrected"]
        if len(temps) < 10 or temps.std() < 0.5:
            continue
        corr, pval = sp_stats.pearsonr(temps, fc)
        results[drv] = {
            "correlation": round(float(corr), 4),
            "p_value": round(float(pval), 4),
            "significant": bool(pval < 0.05),
            "temp_range": round(float(temps.max() - temps.min()), 1),
        }
    return results


# ---------------------------------------------------------------------------
# Race momentum (thirds)
# ---------------------------------------------------------------------------

def analyze_race_momentum(clean: pd.DataFrame) -> dict:
    """Split race into thirds and rank drivers in each phase."""
    if "LapNumber" not in clean.columns:
        return {}

    max_lap = int(clean["LapNumber"].max())
    t1 = max_lap // 3
    t2 = 2 * max_lap // 3
    phases = {
        "opening": (2, t1),  # lap 1 already excluded
        "middle": (t1 + 1, t2),
        "closing": (t2 + 1, max_lap),
    }

    momentum: dict[str, dict] = {}
    for phase_name, (lo, hi) in phases.items():
        phase_df = clean[(clean["LapNumber"] >= lo) & (clean["LapNumber"] <= hi)]
        avgs = phase_df.groupby("Driver")["fuel_corrected"].mean().sort_values()
        for rank, (drv, avg_pace) in enumerate(avgs.items(), 1):
            if drv not in momentum:
                momentum[drv] = {}
            momentum[drv][phase_name] = {
                "avg_pace": round(float(avg_pace), 3),
                "rank": rank,
            }
    return momentum


# ---------------------------------------------------------------------------
# Undercut / overcut analysis
# ---------------------------------------------------------------------------

def analyze_undercut_overcut(clean: pd.DataFrame, raw_df: pd.DataFrame) -> list[dict]:
    """
    For each pit stop window, compare pace of driver on fresh tyres vs
    the driver(s) still on old tyres in the 3 laps after the stop.
    """
    if "Stint" not in clean.columns or raw_df is None:
        return []

    # Detect pit laps from stint transitions in raw data
    raw = raw_df.sort_values(["Driver", "LapNumber"]).copy()
    if "Stint" not in raw.columns:
        return []

    pit_events = []
    for drv, grp in raw.groupby("Driver"):
        grp = grp.sort_values("LapNumber")
        stint_diff = grp["Stint"].diff()
        pit_laps = grp[stint_diff > 0]["LapNumber"].tolist()
        for pl in pit_laps:
            pit_events.append({"driver": drv, "pit_lap": int(pl)})

    if not pit_events:
        return []

    results = []
    for event in pit_events:
        drv = event["driver"]
        pl = event["pit_lap"]
        # Fresh tyre pace: 3 laps after pit
        fresh = clean[
            (clean["Driver"] == drv)
            & (clean["LapNumber"] >= pl + 1)
            & (clean["LapNumber"] <= pl + 3)
        ]["fuel_corrected"]
        if len(fresh) < 2:
            continue
        fresh_avg = float(fresh.mean())

        # Old tyre pace: other drivers who did NOT pit on that lap, same 3 laps
        others = clean[
            (clean["Driver"] != drv)
            & (clean["LapNumber"] >= pl + 1)
            & (clean["LapNumber"] <= pl + 3)
        ]
        if others.empty:
            continue
        other_avg = others.groupby("Driver")["fuel_corrected"].mean()

        for other_drv, old_avg in other_avg.items():
            delta = round(float(fresh_avg - old_avg), 3)
            results.append({
                "pitting_driver": drv,
                "pit_lap": pl,
                "compared_to": other_drv,
                "fresh_tyre_avg": round(fresh_avg, 3),
                "old_tyre_avg": round(float(old_avg), 3),
                "delta": delta,
                "undercut_effective": delta < -0.2,
            })

    return results


# ---------------------------------------------------------------------------
# Team-level aggregation
# ---------------------------------------------------------------------------

def compute_team_summary(
    driver_metrics: dict,
    driver_constructors: dict[str, str],
    abbrev_to_name: dict[str, str],
) -> list[dict]:
    """Aggregate driver metrics to team level."""
    teams: dict[str, list[str]] = {}
    for drv, cid in driver_constructors.items():
        if drv in driver_metrics:
            teams.setdefault(cid, []).append(drv)

    rows = []
    for cid, drivers in teams.items():
        paces = [driver_metrics[d]["avg_lap"] for d in drivers]
        best_paces = [driver_metrics[d]["best_lap"] for d in drivers]

        # Sector dominance
        s1s = [driver_metrics[d]["avg_s1"] for d in drivers if driver_metrics[d]["avg_s1"] is not None]
        s2s = [driver_metrics[d]["avg_s2"] for d in drivers if driver_metrics[d]["avg_s2"] is not None]
        s3s = [driver_metrics[d]["avg_s3"] for d in drivers if driver_metrics[d]["avg_s3"] is not None]

        rows.append({
            "constructor_id": cid,
            "color": TEAM_COLORS.get(cid, "#FFFFFF"),
            "drivers": drivers,
            "avg_pace": round(float(np.mean(paces)), 3),
            "best_pace": round(float(np.min(best_paces)), 3),
            "avg_s1": round(float(np.mean(s1s)), 3) if s1s else None,
            "avg_s2": round(float(np.mean(s2s)), 3) if s2s else None,
            "avg_s3": round(float(np.mean(s3s)), 3) if s3s else None,
        })

    rows.sort(key=lambda x: x["avg_pace"])

    # Sector dominance labels
    if rows:
        for sector_key in ("avg_s1", "avg_s2", "avg_s3"):
            valid = [r for r in rows if r[sector_key] is not None]
            if valid:
                best_team = min(valid, key=lambda r: r[sector_key])
                best_team[f"{sector_key}_dominant"] = True

    return rows


# ---------------------------------------------------------------------------
# CSV export helpers
# ---------------------------------------------------------------------------

def export_csvs(
    driver_metrics: dict,
    stint_data: dict,
    team_summary: list[dict],
    clean: pd.DataFrame,
    abbrev_to_name: dict,
    driver_constructors: dict,
    csv_dir: Path,
) -> None:
    """Write analysis tables to CSV."""
    csv_dir.mkdir(parents=True, exist_ok=True)

    # 1. driver_pace_summary.csv
    rows = []
    for drv, m in driver_metrics.items():
        row = {"driver": drv, "full_name": abbrev_to_name.get(drv, drv),
               "constructor": driver_constructors.get(drv, "")}
        row.update(m)
        rows.append(row)
    if rows:
        pd.DataFrame(rows).to_csv(csv_dir / "driver_pace_summary.csv", index=False)
        print(f"  -> {csv_dir / 'driver_pace_summary.csv'}")

    # 2. sector_analysis.csv
    sector_rows = []
    for drv, m in driver_metrics.items():
        sector_rows.append({
            "driver": drv,
            "avg_s1": m.get("avg_s1"), "avg_s2": m.get("avg_s2"), "avg_s3": m.get("avg_s3"),
            "best_s1": m.get("best_s1"), "best_s2": m.get("best_s2"), "best_s3": m.get("best_s3"),
            "pct_time_s1": m.get("pct_time_s1"), "pct_time_s2": m.get("pct_time_s2"),
            "pct_time_s3": m.get("pct_time_s3"),
        })
    if sector_rows:
        pd.DataFrame(sector_rows).to_csv(csv_dir / "sector_analysis.csv", index=False)
        print(f"  -> {csv_dir / 'sector_analysis.csv'}")

    # 3. stint_analysis.csv
    stint_rows = []
    for drv, stints in stint_data.items():
        for s in stints:
            stint_rows.append({"driver": drv, **s})
    if stint_rows:
        pd.DataFrame(stint_rows).to_csv(csv_dir / "stint_analysis.csv", index=False)
        print(f"  -> {csv_dir / 'stint_analysis.csv'}")

    # 4. team_summary.csv
    if team_summary:
        ts_rows = []
        for t in team_summary:
            ts_rows.append({k: v for k, v in t.items() if k != "drivers"})
            ts_rows[-1]["drivers"] = ", ".join(t["drivers"])
        pd.DataFrame(ts_rows).to_csv(csv_dir / "team_summary.csv", index=False)
        print(f"  -> {csv_dir / 'team_summary.csv'}")

    # 5. speed_trap_analysis.csv
    speed_rows = []
    for drv, m in driver_metrics.items():
        speed_rows.append({
            "driver": drv,
            "avg_speed_trap": m.get("avg_speed_trap"),
            "max_speed_trap": m.get("max_speed_trap"),
            "avg_finish_line_speed": m.get("avg_finish_line_speed"),
        })
    if speed_rows:
        pd.DataFrame(speed_rows).to_csv(csv_dir / "speed_trap_analysis.csv", index=False)
        print(f"  -> {csv_dir / 'speed_trap_analysis.csv'}")

    # 6. lap_times_all_drivers.csv
    if not clean.empty:
        lap_export = clean[["Driver", "LapNumber", "LapTime_seconds", "fuel_corrected"]].copy()
        if "Compound" in clean.columns:
            lap_export["Compound"] = clean["Compound"]
        if "Position" in clean.columns:
            lap_export["Position"] = clean["Position"]
        lap_export.to_csv(csv_dir / "lap_times_all_drivers.csv", index=False)
        print(f"  -> {csv_dir / 'lap_times_all_drivers.csv'}")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_deep_dive(round_num: int, year: int = CURRENT_SEASON) -> None:
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Race Deep Dive  |  {year} Round {round_num}")
    print("=" * 70)

    # ── load reference data ──────────────────────────────────────────────
    abbrev_to_name, jolpica_to_abbrev = load_driver_map()
    driver_constructors = load_driver_constructors()
    race_info = load_race_info(round_num)
    race_name = race_info["name"] if race_info else f"Round {round_num}"

    print(f"\nRace: {race_name}")

    # ── load laps ────────────────────────────────────────────────────────
    print("\n[1/10] Loading race laps...")
    raw_df = load_race_laps(year, round_num)
    if raw_df is None or raw_df.empty:
        print("FATAL: No lap data available. Aborting.")
        sys.exit(1)

    # ── clean ────────────────────────────────────────────────────────────
    print("\n[2/10] Cleaning lap data...")
    clean = clean_laps(raw_df)
    if clean.empty:
        print("FATAL: No clean laps after filtering. Aborting.")
        sys.exit(1)

    # ── driver metrics ───────────────────────────────────────────────────
    print("\n[3/10] Computing per-driver pace metrics...")
    driver_metrics = compute_driver_metrics(clean)
    print(f"  {len(driver_metrics)} drivers analyzed")

    # ── stint analysis ───────────────────────────────────────────────────
    print("\n[4/10] Analyzing stints & tyre degradation...")
    stint_data = compute_stint_analysis(clean)
    print(f"  {sum(len(v) for v in stint_data.values())} stints across {len(stint_data)} drivers")

    # ── tyre cliff detection ─────────────────────────────────────────────
    print("\n[5/10] Detecting tyre cliffs...")
    tyre_cliffs = detect_tyre_cliffs(stint_data, clean)
    n_cliffs = sum(len(v) for v in tyre_cliffs.values())
    print(f"  {n_cliffs} cliff events detected")

    # ── lap-by-lap, positions, gaps ──────────────────────────────────────
    print("\n[6/10] Building lap-by-lap data, position tracker, gap to leader...")
    lap_data = build_lap_data(clean)
    position_tracker = build_position_tracker(raw_df)
    gap_to_leader = build_gap_to_leader(raw_df)
    print(f"  Lap data: {sum(len(v) for v in lap_data.values())} entries")
    print(f"  Position tracker: {len(position_tracker)} drivers")
    print(f"  Gap to leader: {len(gap_to_leader)} drivers")

    # ── creative analyses ────────────────────────────────────────────────
    print("\n[7/10] Dirty air analysis...")
    dirty_air = analyze_dirty_air(clean)
    print(f"  {len(dirty_air)} drivers with enough data")

    print("\n[8/10] Temperature sensitivity...")
    temp_sensitivity = analyze_temp_sensitivity(clean)
    print(f"  {len(temp_sensitivity)} drivers with enough temp variation")

    print("\n[9/10] Race momentum (thirds) & undercut/overcut...")
    momentum = analyze_race_momentum(clean)
    undercut = analyze_undercut_overcut(clean, raw_df)
    print(f"  Momentum: {len(momentum)} drivers")
    print(f"  Undercut/overcut comparisons: {len(undercut)}")

    # ── team summary ─────────────────────────────────────────────────────
    print("\n[10/10] Team-level aggregation...")
    team_summary = compute_team_summary(driver_metrics, driver_constructors, abbrev_to_name)
    print(f"  {len(team_summary)} teams")

    # ── assemble output ──────────────────────────────────────────────────
    output = {
        "race": race_name,
        "round": round_num,
        "season": year,
        "type": "race_deep_dive",
        "total_race_laps": int(raw_df["LapNumber"].max()) if "LapNumber" in raw_df.columns else None,
        "team_colors": TEAM_COLORS,
        "driver_names": {drv: abbrev_to_name.get(drv, drv) for drv in driver_metrics},
        "driver_constructors": {drv: driver_constructors.get(drv, "") for drv in driver_metrics},
        "driver_metrics": driver_metrics,
        "stint_analysis": stint_data,
        "tyre_cliffs": tyre_cliffs,
        "lap_data": lap_data,
        "position_tracker": position_tracker,
        "gap_to_leader": gap_to_leader,
        "dirty_air": dirty_air,
        "temperature_sensitivity": temp_sensitivity,
        "race_momentum": momentum,
        "undercut_overcut": undercut,
        "team_summary": team_summary,
    }

    # ── save JSON ────────────────────────────────────────────────────────
    out_dir = PREDICTIONS_DIR / f"round{round_num}"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "race_deep_dive.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON -> {json_path}")

    # Copy to web
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    web_path = WEB_DATA_DIR / f"deep_dive_round{round_num}.json"
    with open(web_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"JSON -> {web_path}")

    # ── save CSVs ────────────────────────────────────────────────────────
    csv_dir = out_dir / "csv"
    print(f"\nExporting CSVs to {csv_dir}/")
    export_csvs(
        driver_metrics, stint_data, team_summary, clean,
        abbrev_to_name, driver_constructors, csv_dir,
    )

    print(f"\nDone. Deep dive complete for {race_name} ({year} R{round_num}).")


def main():
    parser = argparse.ArgumentParser(
        description="Script 11 — Race Deep Dive Analysis"
    )
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--year", type=int, default=CURRENT_SEASON)
    args = parser.parse_args()
    run_deep_dive(args.round, args.year)


if __name__ == "__main__":
    main()
