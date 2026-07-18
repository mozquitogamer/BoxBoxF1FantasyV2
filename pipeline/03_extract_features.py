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

import argparse
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
from config.tyre_deg import (
    MIN_CLEAN_LAPS as DEG_MIN_CLEAN_LAPS,
    compound_average,
    stint_degradation,
)
from pipeline.fp_long_runs import (
    FP_STINT_SEMANTICS_VERSION,
    extract_representative_long_runs,
    select_headline_long_run,
    stint_group_columns,
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
    Estimate fuel-corrected tyre degradation from one real race-compound stint.

    Session/stint/compound isolation prevents FastF1's session-reset stint
    numbers from concatenating unrelated runs. The longest clean fit is used.
    """
    features = {"degradation_rate": np.nan}
    runs = extract_representative_long_runs(
        group,
        min_raw=DEG_MIN_CLEAN_LAPS,
        min_clean=DEG_MIN_CLEAN_LAPS,
    )
    estimates = []
    for run in runs:
        deg, n_clean = stint_degradation(
            run["kept_laps"],
            run["kept_tyre_age"],
            min_laps=DEG_MIN_CLEAN_LAPS,
        )
        if deg is not None:
            estimates.append((deg, n_clean))

    if estimates:
        # Preserve the old feature's "most representative single stint"
        # intent, but select a real physical stint instead of a cross-session
        # concatenation.
        features["degradation_rate"] = max(estimates, key=lambda x: x[1])[0]
    return pd.Series(features)


def long_run_features(group: pd.DataFrame, min_laps: int) -> pd.Series:
    """
    Compute representative race-compound pace from a comparable FP session.
    """
    features = {"long_run_avg": np.nan, "long_run_laps": 0}

    runs = extract_representative_long_runs(group, min_raw=min_laps)
    headline = select_headline_long_run(runs)
    if headline is not None:
        features["long_run_avg"] = headline["avg_pace"]
        features["long_run_laps"] = headline["laps"]

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
    group_keys = stint_group_columns(group)
    for _, stint_df in group.groupby(group_keys, dropna=False, sort=False):
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


def compound_features(
    group: pd.DataFrame,
    min_long_run_laps: int = MIN_LONG_RUN_LAPS,
) -> pd.Series:
    """
    Extract tyre-compound-aware features.

    Separates soft (qualifying sim) from medium/hard (race sim) pace.
    Compound column may be 'compound' or 'Compound'.
    """
    features = {
        "soft_best_lap": np.nan,
        "soft_avg_lap": np.nan,
        "medium_long_run_avg": np.nan,
        "hard_long_run_avg": np.nan,
        "medium_degradation": np.nan,
        "hard_degradation": np.nan,
    }

    compound_col = None
    for c in ["compound", "Compound", "tyre_compound"]:
        if c in group.columns:
            compound_col = c
            break

    if compound_col is None:
        return pd.Series(features)

    compounds = group[compound_col].str.upper()

    # Soft tyre: qualifying sims
    soft_mask = compounds.isin(["SOFT", "S"])
    soft_laps = group.loc[soft_mask, "lap_time"].dropna()
    if not soft_laps.empty:
        features["soft_best_lap"] = soft_laps.min()
        features["soft_avg_lap"] = soft_laps.mean()

    runs = extract_representative_long_runs(group, min_raw=min_long_run_laps)
    for compound, avg_key, deg_key in [
        ("MEDIUM", "medium_long_run_avg", "medium_degradation"),
        ("HARD", "hard_long_run_avg", "hard_degradation"),
    ]:
        headline = select_headline_long_run(runs, compound=compound)
        if headline is not None:
            features[avg_key] = headline["avg_pace"]

        estimates = []
        for run in runs:
            if run["compound"] != compound:
                continue
            estimates.append(stint_degradation(
                run["kept_laps"],
                run["kept_tyre_age"],
                min_laps=DEG_MIN_CLEAN_LAPS,
            ))
        avg_deg, _, _ = compound_average(estimates)
        if avg_deg is not None:
            features[deg_key] = avg_deg

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

        # Compound-specific features (Tier 2.2)
        comp = compound_features(group, min_long_run_laps)
        row.update(comp.to_dict())

        results.append(row)

    df = pd.DataFrame(results)

    # Add pace rank (1 = fastest)
    if "best_lap_time" in df.columns:
        df["pace_rank"] = df["best_lap_time"].rank(method="min")
        max_rank = df["pace_rank"].max()
        fill_val = (max_rank + 1) if pd.notna(max_rank) else 1
        df["pace_rank"] = df["pace_rank"].fillna(fill_val).astype(int)

    # Missing means "no comparable race run", not "slowest". Leave it NaN so
    # XGBoost/CatBoost can follow their learned missing branch.
    if "long_run_avg" in df.columns:
        df["long_run_rank"] = df["long_run_avg"].rank(method="min")

    # -- Relative pace normalization (Tier 2.3) --
    # These features transfer across circuits: a 0.5s delta means the same everywhere
    if "best_lap_time" in df.columns:
        session_fastest = df["best_lap_time"].min()
        session_median = df["best_lap_time"].median()
        df["pace_delta_to_fastest"] = df["best_lap_time"] - session_fastest
        df["pace_delta_to_median"] = df["best_lap_time"] - session_median

    if "avg_lap_time" in df.columns:
        avg_median = df["avg_lap_time"].median()
        df["avg_pace_delta_to_median"] = df["avg_lap_time"] - avg_median

    if "p50_to_p95_avg" in df.columns:
        race_pace_median = df["p50_to_p95_avg"].median()
        df["race_pace_delta_to_median"] = df["p50_to_p95_avg"] - race_pace_median

    # Per-sector relative pace (delta to session fastest in each sector)
    for i in range(1, 4):
        best_col = f"best_sector_{i}"
        if best_col in df.columns:
            sector_fastest = df[best_col].min()
            df[f"sector_{i}_delta_to_fastest"] = df[best_col] - sector_fastest

    # Long-run relative pace
    if "long_run_avg" in df.columns:
        lr_median = df["long_run_avg"].median()
        df["long_run_delta_to_median"] = df["long_run_avg"] - lr_median

    return df


# -- Main ---------------------------------------------------------------------

def main() -> None:
    """Extract features for a specified round."""
    parser = argparse.ArgumentParser(description="BoxBoxF1Fantasy — Extract Features")
    parser.add_argument("--round", type=int, default=None,
                        help="Round number to process")
    args, _ = parser.parse_known_args()

    print("=" * 60)
    print("BoxBoxF1Fantasy — Extract Features")
    print("=" * 60)

    if args.round is not None:
        round_num = args.round
    else:
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
    # This is metadata, not a model feature. It lets training and inference
    # reject stale parquets produced with the old cross-session stint rules.
    features_df["fp_stint_semantics_version"] = FP_STINT_SEMANTICS_VERSION

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
