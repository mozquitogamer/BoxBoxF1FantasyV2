"""
Script 03 — Extract Features

Converts clean lap data into driver performance features for model input.

Automatically detects how many FP session Parquet files are available
(1, 2, or 3) and processes accordingly.

Features produced:
- Pace metrics: avg, best, median, ranked, rolling bests
- Consistency: std, variance
- Degradation: tyre deg slope estimate
- Long run pace: stints >= MIN_LONG_RUN_LAPS
- Short run pace: best fresh-tyre laps
- Sector pace: best/avg for each sector

Output:
    data/processed/features/roundX/features.parquet
"""

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    LAPS_DIR,
    FEATURES_DIR,
    MIN_LONG_RUN_LAPS,
)


# -- Feature extraction functions ----------------------------------------------

def pace_features(group: pd.DataFrame) -> pd.Series:
    """Compute pace-related features for a driver's laps."""
    times = group["lap_time"].dropna()
    if times.empty:
        return pd.Series(dtype=float)

    sorted_times = times.sort_values()

    features = {
        "avg_lap_time": times.mean(),
        "best_lap_time": times.min(),
        "median_lap_time": times.median(),
        "best_3_lap_avg": sorted_times.head(3).mean() if len(sorted_times) >= 3 else sorted_times.mean(),
        "best_5_lap_avg": sorted_times.head(5).mean() if len(sorted_times) >= 5 else sorted_times.mean(),
        "best_10_lap_avg": sorted_times.head(10).mean() if len(sorted_times) >= 10 else sorted_times.mean(),
        "total_laps": len(times),
    }

    # P50 to P95 average (representative race pace, excludes outliers)
    if len(times) >= 4:
        p50 = times.quantile(0.50)
        p95 = times.quantile(0.95)
        mask = (times >= p50) & (times <= p95)
        filtered = times[mask]
        features["p50_to_p95_avg"] = filtered.mean() if not filtered.empty else times.mean()
    else:
        features["p50_to_p95_avg"] = times.mean()

    return pd.Series(features)


def consistency_features(group: pd.DataFrame) -> pd.Series:
    """Compute consistency metrics for a driver's laps."""
    times = group["lap_time"].dropna()
    if len(times) < 2:
        return pd.Series({"lap_time_std": 0.0, "lap_time_variance": 0.0})

    return pd.Series({
        "lap_time_std": times.std(),
        "lap_time_variance": times.var(),
    })


def degradation_features(group: pd.DataFrame) -> pd.Series:
    """
    Estimate tyre degradation rate using linear regression on stint lap times.

    Uses the longest stint to estimate the slope of lap time increase.
    """
    features = {"degradation_rate": 0.0}

    if "stint_number" not in group.columns:
        return pd.Series(features)

    # Find the longest stint
    stints = group.groupby("stint_number")
    longest_stint = None
    max_len = 0

    for stint_num, stint_df in stints:
        valid = stint_df[stint_df["lap_time"].notna()]
        if len(valid) > max_len:
            max_len = len(valid)
            longest_stint = valid

    if longest_stint is None or len(longest_stint) < 3:
        return pd.Series(features)

    # Simple linear regression: lap_time vs lap_index
    x = np.arange(len(longest_stint), dtype=float)
    y = longest_stint["lap_time"].values.astype(float)

    # Remove NaN
    mask = ~np.isnan(y)
    x, y = x[mask], y[mask]

    if len(x) < 3:
        return pd.Series(features)

    # Slope via least squares
    x_mean = x.mean()
    y_mean = y.mean()
    numerator = ((x - x_mean) * (y - y_mean)).sum()
    denominator = ((x - x_mean) ** 2).sum()

    if denominator > 0:
        features["degradation_rate"] = numerator / denominator

    return pd.Series(features)


def long_run_features(group: pd.DataFrame, min_laps: int) -> pd.Series:
    """
    Compute long run pace features.

    Detects stints with at least min_laps laps and computes average pace.
    """
    features = {"long_run_avg": np.nan, "long_run_laps": 0}

    if "stint_number" not in group.columns:
        return pd.Series(features)

    long_run_times = []
    for stint_num, stint_df in group.groupby("stint_number"):
        valid = stint_df["lap_time"].dropna()
        if len(valid) >= min_laps:
            long_run_times.extend(valid.tolist())

    if long_run_times:
        features["long_run_avg"] = np.mean(long_run_times)
        features["long_run_laps"] = len(long_run_times)

    return pd.Series(features)


def short_run_features(group: pd.DataFrame) -> pd.Series:
    """
    Compute short run (qualifying sim) pace.

    Best lap pace from the first 3 laps of each stint (fresh tyres).
    """
    features = {"short_run_best": np.nan}

    if "stint_number" not in group.columns:
        times = group["lap_time"].dropna()
        if not times.empty:
            features["short_run_best"] = times.min()
        return pd.Series(features)

    fresh_tyre_times = []
    for stint_num, stint_df in group.groupby("stint_number"):
        valid = stint_df.sort_values("lap_number")["lap_time"].dropna()
        # First 3 laps of each stint
        fresh_tyre_times.extend(valid.head(3).tolist())

    if fresh_tyre_times:
        features["short_run_best"] = min(fresh_tyre_times)

    return pd.Series(features)


def sector_features(group: pd.DataFrame) -> pd.Series:
    """Compute sector time features."""
    features = {}
    for i in range(1, 4):
        col = f"sector_{i}"
        if col in group.columns:
            times = group[col].dropna()
            features[f"avg_sector_{i}"] = times.mean() if not times.empty else np.nan
            features[f"best_sector_{i}"] = times.min() if not times.empty else np.nan
        else:
            features[f"avg_sector_{i}"] = np.nan
            features[f"best_sector_{i}"] = np.nan

    return pd.Series(features)


# -- Main extraction -----------------------------------------------------------

def extract_driver_features(
    all_laps: pd.DataFrame,
    min_long_run_laps: int,
) -> pd.DataFrame:
    """
    Extract all features for each driver from combined FP lap data.

    Args:
        all_laps: Combined DataFrame of all FP laps.
        min_long_run_laps: Minimum laps for a stint to count as a long run.

    Returns:
        DataFrame with one row per driver containing all features.
    """
    results = []

    for driver_id, group in all_laps.groupby("driver_id"):
        row = {"driver_id": driver_id}

        # Constructor
        if "constructor_id" in group.columns:
            row["constructor_id"] = group["constructor_id"].iloc[0]

        # Pace
        pace = pace_features(group)
        row.update(pace.to_dict())

        # Consistency
        consistency = consistency_features(group)
        row.update(consistency.to_dict())

        # Degradation
        deg = degradation_features(group)
        row.update(deg.to_dict())

        # Long run
        lr = long_run_features(group, min_long_run_laps)
        row.update(lr.to_dict())

        # Short run
        sr = short_run_features(group)
        row.update(sr.to_dict())

        # Sectors
        sec = sector_features(group)
        row.update(sec.to_dict())

        results.append(row)

    df = pd.DataFrame(results)

    # Add pace rank (1 = fastest)
    if "best_lap_time" in df.columns:
        df["pace_rank"] = df["best_lap_time"].rank(method="min")
        max_rank = df["pace_rank"].max()
        fill_val = (max_rank + 1) if pd.notna(max_rank) else 1
        df["pace_rank"] = df["pace_rank"].fillna(fill_val).astype(int)

    # Add long run rank (NaN for drivers with no long runs)
    if "long_run_avg" in df.columns:
        df["long_run_rank"] = df["long_run_avg"].rank(method="min")
        max_rank = df["long_run_rank"].max()
        fill_val = (max_rank + 1) if pd.notna(max_rank) else 1
        df["long_run_rank"] = df["long_run_rank"].fillna(fill_val).astype(int)

    return df


# -- Main ---------------------------------------------------------------------

def main() -> None:
    """Extract features for a specified round."""
    print("=" * 60)
    print("BoxBoxF1Fantasy — Extract Features")
    print("=" * 60)

    round_num = int(input(f"\nEnter round number for {CURRENT_SEASON}: ").strip())

    laps_dir = LAPS_DIR / f"round{round_num}"
    if not laps_dir.exists():
        print(f"No lap data found at {laps_dir}")
        print("Run 02_build_laps.py first.")
        return

    # Detect available FP sessions
    fp_files = sorted(laps_dir.glob("all_laps_fp*.parquet"))
    print(f"\nDetected {len(fp_files)} FP session file(s):")
    for f in fp_files:
        print(f"  -> {f.name}")

    if not fp_files:
        print("No FP session files found. Run 02_build_laps.py first.")
        return

    # Load and combine all FP data
    all_laps = []
    for fp_file in fp_files:
        df = pd.read_parquet(fp_file)
        print(f"  Loaded {fp_file.name}: {len(df)} laps, {df['driver_id'].nunique()} drivers")
        all_laps.append(df)

    combined = pd.concat(all_laps, ignore_index=True)
    print(f"\nCombined: {len(combined)} total laps across {combined['driver_id'].nunique()} drivers")

    # Extract features
    print("\nExtracting features...")
    features_df = extract_driver_features(combined, MIN_LONG_RUN_LAPS)

    # Add metadata
    features_df["year"] = CURRENT_SEASON
    features_df["round"] = round_num
    features_df["fp_sessions_used"] = len(fp_files)

    # Save
    output_dir = FEATURES_DIR / f"round{round_num}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "features.parquet"
    features_df.to_parquet(output_path, index=False, engine="pyarrow")

    print(f"\nSaved features: {output_path}")
    print(f"Shape: {features_df.shape}")
    print(f"\nFeature columns:")
    for col in features_df.columns:
        print(f"  {col}")

    print("\n" + "=" * 60)
    print("Feature extraction complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
