"""
Script 12 — Count Actual Overtakes from FastF1 Position Data

Uses FastF1's high-frequency position data (~5Hz GPS coordinates) to detect
on-track overtakes by tracking relative car positions throughout the race.

Algorithm:
  1. Build a reference track from the leader's first lap GPS coordinates
  2. Project each car's position onto the reference track at each timestamp
     to get "track progress" (0.0 to 1.0 within a lap)
  3. Compute total race progress = completed_laps + track_fraction
  4. Detect position swaps between consecutive timestamps
  5. Filter out pit stop shuffles (only count swaps where cars are close on track)

This replicates what F1 Fantasy likely uses — sensor-based overtake detection
that counts every on-track pass, not just net position changes.

Usage:
    python pipeline/12_count_overtakes.py --year 2026 --round 1
    python pipeline/12_count_overtakes.py --year 2026 --all
    python pipeline/12_count_overtakes.py --year 2026 --round 1 --method lap  # fallback

Output:
    data/overtakes/year{YYYY}/round{N}/overtakes.json
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import fastf1
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    PROJECT_ROOT,
    CURRENT_SEASON,
    SEED_DIR,
    CANCELLED_ROUNDS_2026,
    fastf1_round,
)

CACHE_DIR = PROJECT_ROOT / "data" / "fastf1_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

OUTPUT_DIR = PROJECT_ROOT / "data" / "overtakes"


# =============================================================================
# Reference track builder
# =============================================================================

def build_reference_track(pos_data: dict, laps_df: pd.DataFrame) -> np.ndarray:
    """
    Build a reference track polyline from the race leader's first full lap.

    Returns:
        Nx2 array of (X, Y) coordinates defining the track, ordered by
        driving direction. The cumulative arc-length of this polyline
        represents track distance.
    """
    # Find the driver who led lap 1 (usually the pole sitter)
    lap1 = laps_df[laps_df["LapNumber"] == 2]  # Lap 2 = first full racing lap
    if lap1.empty:
        lap1 = laps_df[laps_df["LapNumber"] == 1]
    if lap1.empty:
        return None

    leader = lap1.sort_values("Position").iloc[0]
    driver_num = str(leader["DriverNumber"])

    if driver_num not in pos_data:
        # Try any driver with pos_data
        driver_num = list(pos_data.keys())[0]

    drv_pos = pos_data[driver_num]
    lap_num = int(leader["LapNumber"])

    # Get position data for this driver during the reference lap
    lap_start = leader["LapStartTime"] if pd.notna(leader.get("LapStartTime")) else None
    lap_end = leader["Time"] if pd.notna(leader.get("Time")) else None

    if lap_start is not None and lap_end is not None:
        mask = (drv_pos["SessionTime"] >= lap_start) & (drv_pos["SessionTime"] <= lap_end)
        ref_points = drv_pos.loc[mask, ["X", "Y"]].values
    else:
        # Fallback: use first ~600 points (roughly one lap at 5Hz with ~90s lap)
        ref_points = drv_pos[["X", "Y"]].values[:600]

    if len(ref_points) < 50:
        # Not enough points, use more
        ref_points = drv_pos[["X", "Y"]].values[:1000]

    # Downsample for efficiency (every 5th point ≈ 1Hz)
    ref_points = ref_points[::5]

    return ref_points.astype(np.float64)


def compute_track_distances(ref_track: np.ndarray) -> np.ndarray:
    """Compute cumulative arc-length distances along the reference track."""
    diffs = np.diff(ref_track, axis=0)
    segment_lengths = np.sqrt((diffs ** 2).sum(axis=1))
    cumulative = np.concatenate([[0], np.cumsum(segment_lengths)])
    return cumulative


def project_onto_track(
    points: np.ndarray,
    ref_track: np.ndarray,
    track_distances: np.ndarray,
) -> np.ndarray:
    """
    Project GPS points onto the reference track to get track progress.

    For each input point, finds the closest point on the reference track
    and returns the corresponding track distance (0 to track_length).
    """
    # Vectorized nearest-point lookup
    # For each point, compute distance to all reference track points
    # Use chunking to avoid memory issues
    n_points = len(points)
    n_ref = len(ref_track)
    result = np.zeros(n_points)

    chunk_size = 5000
    for i in range(0, n_points, chunk_size):
        chunk = points[i:i + chunk_size]
        # Distances: (chunk_size, n_ref)
        dx = chunk[:, 0:1] - ref_track[:, 0]
        dy = chunk[:, 1:2] - ref_track[:, 1]
        dists = dx ** 2 + dy ** 2  # Skip sqrt for speed
        nearest_idx = dists.argmin(axis=1)
        result[i:i + len(chunk)] = track_distances[nearest_idx]

    return result


# =============================================================================
# High-frequency overtake detection
# =============================================================================

def detect_overtakes_hf(
    session,
    sampling_interval_ms: int = 1000,
) -> dict:
    """
    Detect overtakes using timing-based race progress interpolation.

    Instead of error-prone GPS projection, uses lap crossing times to
    interpolate each driver's race progress at any moment. Position swaps
    between close drivers = overtakes.

    Algorithm:
      1. Build a timeline of S/F crossings for each driver from lap data
      2. At each second, interpolate each driver's total race progress:
         progress = last_completed_lap + (time - last_crossing) / lap_duration
      3. Compare race progress between driver pairs
      4. Smoothed zero-crossings of the gap signal = overtakes
      5. Pit stops filtered out, cooldown prevents double-counting

    Args:
        session: Loaded FastF1 session
        sampling_interval_ms: Resample interval in milliseconds

    Returns:
        Dict with per-driver overtake counts.
    """
    laps_df = session.laps

    # Build driver map
    driver_map = {}
    for _, row in laps_df.drop_duplicates("DriverNumber").iterrows():
        driver_map[str(row["DriverNumber"])] = row["Driver"]

    driver_nums = list(set(str(x) for x in laps_df["DriverNumber"].unique()))
    driver_nums = [d for d in driver_nums if d in driver_map]

    # Build sector crossing times for each driver
    # 3 crossings per lap (S1, S2, S3/S/F) = 3x resolution vs lap-only
    # Progress at S1 boundary = lap - 0.667, S2 = lap - 0.333, S3/SF = lap
    print("  Building sector crossing timelines...")
    crossings = {}  # dnum -> list of (time_sec, race_progress)
    pit_windows = {}  # dnum -> list of (start_sec, end_sec)

    for dnum in driver_nums:
        drv_laps = laps_df[laps_df["DriverNumber"] == dnum].sort_values("LapNumber")
        xings = []
        pits = []

        for _, lap in drv_laps.iterrows():
            lap_num = int(lap["LapNumber"])

            # Sector 1 crossing (end of S1 = ~1/3 of lap)
            s1_time = lap.get("Sector1SessionTime")
            if pd.notna(s1_time):
                xings.append((s1_time.total_seconds(), lap_num - 1 + 1/3))

            # Sector 2 crossing (end of S2 = ~2/3 of lap)
            s2_time = lap.get("Sector2SessionTime")
            if pd.notna(s2_time):
                xings.append((s2_time.total_seconds(), lap_num - 1 + 2/3))

            # Sector 3 / S/F crossing (end of lap)
            sf_time = lap.get("Time")
            if pd.notna(sf_time):
                xings.append((sf_time.total_seconds(), float(lap_num)))

            # Track pit stops
            pit_in = lap.get("PitInTime")
            pit_out = lap.get("PitOutTime")
            if pd.notna(pit_in):
                ps = pit_in.total_seconds()
                pe = pit_out.total_seconds() if pd.notna(pit_out) else ps + 30
                pits.append((ps - 3, pe + 8))

        crossings[dnum] = sorted(xings, key=lambda x: x[0])
        pit_windows[dnum] = pits

    # Build time grid
    all_times = [t for xings in crossings.values() for t, _ in xings]
    if not all_times:
        return count_overtakes_from_laps(laps_df)

    t_start = min(all_times) - 10
    t_end = max(all_times) + 10
    dt = sampling_interval_ms / 1000.0
    n_times = int((t_end - t_start) / dt)
    time_grid = np.linspace(t_start, t_end, n_times)
    print(f"  Time grid: {n_times} points ({dt}s intervals)")
    print(f"  Sector crossings per driver: {[len(crossings[d]) for d in driver_nums[:5]]}...")

    # Interpolate race progress for each driver at each time point
    print("  Interpolating race progress...")
    progress = {}

    for dnum in driver_nums:
        xings = crossings[dnum]
        if len(xings) < 3:
            continue

        cross_times = np.array([t for t, _ in xings])
        cross_progress = np.array([p for _, p in xings], dtype=float)

        prog = np.interp(time_grid, cross_times, cross_progress,
                         left=0, right=cross_progress[-1])
        progress[dnum] = prog

    if len(progress) < 2:
        return count_overtakes_from_laps(laps_df)

    # Detect overtakes using smoothed gap analysis with hysteresis
    print("  Detecting overtakes (smoothed + hysteresis)...")
    driver_nums_active = list(progress.keys())
    overtakes = {driver_map.get(d, d): {"total": 0, "laps": []} for d in driver_nums_active}

    def is_in_pits(dnum, t_sec):
        for ps, pe in pit_windows.get(dnum, []):
            if ps <= t_sec <= pe:
                return True
        return False

    # Smoothing: 5 samples at 1s = 5 seconds (light smoothing, timing data is clean)
    smooth_window = 5
    # Cooldown between same pair: 15 seconds (prevents double-counting)
    cooldown_samples = int(15 / dt)
    # Confirmation window: gap must be consistently on one side for N samples
    confirm_samples = 3

    n_drivers = len(driver_nums_active)
    n_pairs = n_drivers * (n_drivers - 1) // 2
    print(f"  Processing {n_pairs} driver pairs...")

    for i in range(n_drivers):
        for j in range(i + 1, n_drivers):
            dnum_i = driver_nums_active[i]
            dnum_j = driver_nums_active[j]
            abbrev_i = driver_map.get(dnum_i, dnum_i)
            abbrev_j = driver_map.get(dnum_j, dnum_j)

            prog_i = progress[dnum_i]
            prog_j = progress[dnum_j]

            # Signed gap: positive = i is ahead
            raw_gap = prog_i - prog_j

            # Only consider when both racing and within 0.6 laps
            valid = (prog_i > 0.5) & (prog_j > 0.5) & (np.abs(raw_gap) < 0.6)

            if valid.sum() < smooth_window * 3:
                continue

            # Light smoothing
            smoothed = pd.Series(raw_gap).rolling(
                window=smooth_window, center=True, min_periods=2
            ).mean().values

            # State-based sign tracking: detect sustained sign changes
            # An overtake = gap was consistently positive, then becomes consistently negative
            last_ot = -cooldown_samples * 2
            state = 0  # 0=unknown, 1=i_ahead, -1=j_ahead
            consecutive = 0

            for t in range(n_times):
                if not valid[t]:
                    state = 0
                    consecutive = 0
                    continue

                g = smoothed[t]
                if np.isnan(g):
                    continue

                if g > 0:
                    new_state = 1
                elif g < 0:
                    new_state = -1
                else:
                    continue

                if new_state == state:
                    consecutive += 1
                else:
                    # State changed
                    if state != 0 and consecutive >= confirm_samples:
                        # Confirmed state change = overtake
                        if (t - last_ot) >= cooldown_samples:
                            t_sec = time_grid[t]
                            if not is_in_pits(dnum_i, t_sec) and not is_in_pits(dnum_j, t_sec):
                                if new_state == -1:
                                    # j overtook i (gap went from + to -)
                                    overtakes[abbrev_j]["total"] += 1
                                else:
                                    # i overtook j (gap went from - to +)
                                    overtakes[abbrev_i]["total"] += 1
                                last_ot = t

                    state = new_state
                    consecutive = 1

    return overtakes


# =============================================================================
# Lap-by-lap fallback (simpler, less accurate)
# =============================================================================

def count_overtakes_from_laps(laps_df: pd.DataFrame) -> dict:
    """Fallback: count overtakes from lap-by-lap position changes."""
    pos_data = laps_df[["Driver", "LapNumber", "Position"]].dropna(
        subset=["Position"]
    ).copy()
    pos_data["Position"] = pos_data["Position"].astype(int)
    pos_data["LapNumber"] = pos_data["LapNumber"].astype(int)

    pivot = pos_data.pivot_table(
        index="LapNumber", columns="Driver", values="Position", aggfunc="first"
    ).sort_index()

    laps = pivot.index.tolist()
    drivers = pivot.columns.tolist()
    overtakes = {d: {"total": 0, "laps": []} for d in drivers}

    for i in range(1, len(laps)):
        prev = pivot.loc[laps[i - 1]]
        curr = pivot.loc[laps[i]]

        for driver_a in drivers:
            pa_prev, pa_curr = prev.get(driver_a), curr.get(driver_a)
            if pd.isna(pa_prev) or pd.isna(pa_curr):
                continue
            pa_prev, pa_curr = int(pa_prev), int(pa_curr)

            if pa_curr < pa_prev:
                ot_count = 0
                for driver_b in drivers:
                    if driver_b == driver_a:
                        continue
                    pb_prev, pb_curr = prev.get(driver_b), curr.get(driver_b)
                    if pd.isna(pb_prev) or pd.isna(pb_curr):
                        continue
                    if int(pa_prev) > int(pb_prev) and int(pa_curr) < int(pb_curr):
                        ot_count += 1
                if ot_count > 0:
                    overtakes[driver_a]["total"] += ot_count

    return overtakes


# =============================================================================
# Session processing
# =============================================================================

def count_overtakes_for_session(
    year: int, round_num: int, session_type: str = "R", method: str = "hf",
) -> dict | None:
    """Load a session and count overtakes."""
    session_name = "Race" if session_type == "R" else "Sprint"
    ff1_round = fastf1_round(round_num, year)
    try:
        session = fastf1.get_session(year, ff1_round, session_type)
        session.load(
            laps=True,
            telemetry=False,
            weather=False,
            messages=False,
        )
    except Exception as e:
        print(f"  Could not load {session_name} for {year} R{round_num}: {e}")
        return None

    if session.laps is None or session.laps.empty:
        print(f"  No lap data for {session_name} {year} R{round_num}")
        return None

    print(f"  Loaded {len(session.laps)} laps for {session_name}")

    if method == "hf":
        overtakes = detect_overtakes_hf(session)
    else:
        overtakes = count_overtakes_from_laps(session.laps)

    event_name = session.event.get("EventName", f"Round {round_num}")
    results = []
    for driver, data in sorted(overtakes.items(), key=lambda x: -x[1]["total"]):
        results.append({
            "driver": driver,
            "overtakes": data["total"],
        })

    total_overtakes = sum(d["total"] for d in overtakes.values())

    return {
        "session": session_name,
        "event": event_name,
        "year": year,
        "round": round_num,
        "method": method,
        "total_overtakes": total_overtakes,
        "drivers": results,
    }


def process_round(year: int, round_num: int, method: str = "hf") -> None:
    """Process a single round."""
    print(f"\n{'='*60}")
    print(f"  Counting overtakes: {year} Round {round_num} (method={method})")
    print(f"{'='*60}")

    output = {"year": year, "round": round_num, "method": method, "sessions": {}}

    # Race
    race_data = count_overtakes_for_session(year, round_num, "R", method)
    if race_data:
        output["sessions"]["race"] = race_data
        print(f"\n  Race overtakes by driver:")
        for d in race_data["drivers"][:12]:
            print(f"    {d['driver']:<4} {d['overtakes']:>3} overtakes")
        print(f"  Total race overtakes: {race_data['total_overtakes']}")

    # Sprint
    sprint_data = count_overtakes_for_session(year, round_num, "S", method)
    if sprint_data:
        output["sessions"]["sprint"] = sprint_data
        print(f"\n  Sprint overtakes by driver:")
        for d in sprint_data["drivers"][:12]:
            print(f"    {d['driver']:<4} {d['overtakes']:>3} overtakes")
        print(f"  Total sprint overtakes: {sprint_data['total_overtakes']}")

    if not output["sessions"]:
        print(f"  No session data available for {year} R{round_num}")
        return

    out_dir = OUTPUT_DIR / f"year{year}" / f"round{round_num}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "overtakes.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Count overtakes from FastF1 data")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON)
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--method", choices=["hf", "lap"], default="hf",
                        help="hf=high-frequency GPS, lap=lap-by-lap positions")
    parser.add_argument("--max-round", type=int, default=24)
    args = parser.parse_args()

    if args.round and not args.all:
        process_round(args.year, args.round, args.method)
    elif args.all:
        for rnd in range(1, args.max_round + 1):
            if args.year == 2026 and rnd in CANCELLED_ROUNDS_2026:
                continue
            try:
                process_round(args.year, rnd, args.method)
            except Exception as e:
                print(f"  Error processing {args.year} R{rnd}: {e}")
    else:
        print("Specify --round N or --all")


if __name__ == "__main__":
    main()
