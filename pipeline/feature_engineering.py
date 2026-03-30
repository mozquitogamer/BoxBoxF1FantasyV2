"""
Shared feature engineering utilities.

Used by both 05_train_models.py and 06_run_predictions.py to ensure
consistent feature engineering between training and inference.
"""

import numpy as np
import pandas as pd


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create interaction and ratio features from raw FP data.

    These engineered features significantly improve model accuracy by
    capturing pace consistency, sector balance, and degradation patterns
    that raw features miss.
    """
    df = df.copy()

    # Pace delta: gap between best and average (lower = more consistent)
    if "best_lap_time" in df.columns and "avg_lap_time" in df.columns:
        df["pace_delta"] = df["avg_lap_time"] - df["best_lap_time"]
        df["pace_consistency_ratio"] = df["best_lap_time"] / df["avg_lap_time"].replace(0, np.nan)

    # Sector deltas (avg - best per sector)
    for i in [1, 2, 3]:
        avg_col = f"avg_sector_{i}"
        best_col = f"best_sector_{i}"
        if avg_col in df.columns and best_col in df.columns:
            df[f"sector_{i}_delta"] = df[avg_col] - df[best_col]

    # Theoretical best lap from best sectors
    sector_cols = ["best_sector_1", "best_sector_2", "best_sector_3"]
    if all(c in df.columns for c in sector_cols):
        df["theoretical_best"] = df[sector_cols].sum(axis=1)

    # Coefficient of variation (consistency relative to pace)
    if "lap_time_std" in df.columns and "avg_lap_time" in df.columns:
        df["cv_lap_time"] = df["lap_time_std"] / df["avg_lap_time"].replace(0, np.nan)

    # Laps per session (running time indicator)
    if "total_laps" in df.columns and "fp_sessions_used" in df.columns:
        df["laps_per_session"] = df["total_laps"] / df["fp_sessions_used"].replace(0, np.nan)

    # Top-N consistency (gap between best N averages)
    if "best_3_lap_avg" in df.columns and "best_5_lap_avg" in df.columns:
        df["top3_vs_top5"] = df["best_3_lap_avg"] - df["best_5_lap_avg"]

    if "best_5_lap_avg" in df.columns and "best_10_lap_avg" in df.columns:
        df["top5_vs_top10"] = df["best_5_lap_avg"] - df["best_10_lap_avg"]

    # Long run delta (long run pace vs best lap)
    if "long_run_avg" in df.columns and "best_lap_time" in df.columns:
        df["long_run_delta"] = df["long_run_avg"] - df["best_lap_time"]

    # Degradation x laps interaction
    if "degradation_rate" in df.columns and "long_run_laps" in df.columns:
        df["deg_x_laps"] = df["degradation_rate"] * df["long_run_laps"]

    # Qualifying vs FP rank gap (for race model -- how much did quali differ from FP)
    if "qualifying_position" in df.columns and "pace_rank" in df.columns:
        df["quali_vs_fp_rank"] = df["qualifying_position"] - df["pace_rank"]

    # Cross-layer interaction: Jolpica prior vs FP telemetry rank
    if "driver_roll_quali_3" in df.columns and "pace_rank" in df.columns:
        df["prior_vs_fp_rank"] = df["driver_roll_quali_3"] - df["pace_rank"]

    # -- Compound-based features (Tier 2.2) --
    # Soft vs medium gap: how much faster on soft (qualifying pace advantage)
    if "soft_best_lap" in df.columns and "medium_long_run_avg" in df.columns:
        df["soft_medium_gap"] = df["medium_long_run_avg"] - df["soft_best_lap"]

    # Race compound preference: which gives better long-run pace
    if "medium_long_run_avg" in df.columns and "hard_long_run_avg" in df.columns:
        df["medium_hard_gap"] = df["hard_long_run_avg"] - df["medium_long_run_avg"]

    # Quali vs race pace consistency: soft best vs overall best
    if "soft_best_lap" in df.columns and "best_lap_time" in df.columns:
        df["soft_vs_overall_best"] = df["soft_best_lap"] - df["best_lap_time"]

    return df
