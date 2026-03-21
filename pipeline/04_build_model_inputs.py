"""
Script 04 -- Build Model Inputs

Merges Jolpica historical priors (rolling features from 03b) with FP telemetry
features (from 03) to create the unified training dataset for XGBoost models.

Architecture:
    Layer 1 (always available):  Jolpica priors -- 2,662 rows x 91 cols
    Layer 2 (sparse, ~160 rows): FP telemetry features from FastF1

Most rows will have NaN for all FP columns. XGBoost handles NaN natively via
its "hist" tree method, so this is fine.

Data flow:
    1. Load all_model_rows.parquet (Jolpica priors from 03b)
    2. For each (year, round), locate FP features if they exist
    3. Left-join FP features onto model_rows by (year, round, driver_id)
       -- FP features use abbreviation IDs (VER, HAM); model_rows use Jolpica IDs
       -- Convert via driver_ids.json before merging
    4. Apply feature engineering (pace deltas, theoretical best, etc.)
    5. Add sample_weight (2.5x for 2026, 1.0 for earlier)
    6. Filter to rows with valid targets (finish_position, quali_position)
    7. Save combined training data

Output:
    models/training_data/all_training_data.parquet
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
    HISTORICAL_SEASONS,
    JOLPICA_MODEL_ROWS_DIR,
    FEATURES_DIR,
    FASTF1_RAW_DIR,
    TRAINING_DATA_DIR,
    SEED_DIR,
    MODEL_INPUTS_DIR,
    MIN_LONG_RUN_LAPS,
    REGULATION_CHANGE_YEAR,
    REGULATION_WEIGHT_MULTIPLIER,
)
from pipeline.feature_engineering import engineer_features


# -- FP feature columns expected from 03_extract_features.py -------------------

FP_FEATURE_COLUMNS = [
    "avg_lap_time", "best_lap_time", "median_lap_time", "pace_rank",
    "best_3_lap_avg", "best_5_lap_avg", "best_10_lap_avg", "p50_to_p95_avg",
    "lap_time_std", "lap_time_variance",
    "degradation_rate",
    "long_run_avg", "long_run_rank", "long_run_laps",
    "short_run_best",
    "avg_sector_1", "avg_sector_2", "avg_sector_3",
    "best_sector_1", "best_sector_2", "best_sector_3",
    "total_laps", "fp_sessions_used",
]


# -- Driver ID mapping ---------------------------------------------------------

def load_abbrev_to_jolpica_map() -> dict[str, str]:
    """
    Build a mapping from FastF1 abbreviation IDs to Jolpica IDs.

    Example: "VER" -> "max_verstappen", "HAM" -> "hamilton"
    """
    driver_ids_path = SEED_DIR / "driver_ids.json"
    if not driver_ids_path.exists():
        raise FileNotFoundError(f"Driver IDs file not found: {driver_ids_path}")

    with open(driver_ids_path, "r") as f:
        data = json.load(f)

    mapping = {}
    for m in data["mappings"]:
        mapping[m["abbrev"]] = m["jolpica"]
    return mapping


# -- FP feature loading --------------------------------------------------------

def load_fp_features_for_round(
    year: int, round_num: int
) -> pd.DataFrame | None:
    """
    Attempt to load FP features for a given (year, round).

    Search order:
        1. Current season:  data/processed/features/round{N}/features.parquet
        2. Historical:      data/processed/model_inputs/year{Y}/round{N}/model_data.parquet
                            (extract FP columns only)
        3. Raw FastF1:      extract from raw lap parquet files
    """
    # 1. Current season extracted features
    if year == CURRENT_SEASON:
        fp_path = FEATURES_DIR / f"round{round_num}" / "features.parquet"
        if fp_path.exists():
            try:
                df = pd.read_parquet(fp_path)
                return _standardize_fp_df(df, year, round_num)
            except Exception as e:
                print(f"    Warning: could not read {fp_path}: {e}")

    # 2. Previously saved model_inputs (may contain FP features from prior runs)
    mi_path = MODEL_INPUTS_DIR / f"year{year}" / f"round{round_num}" / "model_data.parquet"
    if mi_path.exists():
        try:
            df = pd.read_parquet(mi_path)
            # Check if it actually has FP columns
            available_fp = [c for c in FP_FEATURE_COLUMNS if c in df.columns]
            if available_fp and df[available_fp[0]].notna().any():
                keep_cols = ["driver_id"] + [c for c in FP_FEATURE_COLUMNS if c in df.columns]
                return df[keep_cols].copy()
        except Exception:
            pass

    # 3. Extract from raw FastF1 data
    return _extract_fp_from_raw_fastf1(year, round_num)


def _standardize_fp_df(
    df: pd.DataFrame, year: int, round_num: int
) -> pd.DataFrame | None:
    """Ensure FP DataFrame has driver_id and standard FP columns."""
    if df is None or df.empty:
        return None
    keep_cols = ["driver_id"] + [c for c in FP_FEATURE_COLUMNS if c in df.columns]
    out = df[[c for c in keep_cols if c in df.columns]].copy()
    if "driver_id" not in out.columns:
        return None
    return out


def _extract_fp_from_raw_fastf1(
    year: int, round_num: int
) -> pd.DataFrame | None:
    """
    Extract FP features directly from raw FastF1 Parquet files.

    Uses the same extraction logic as 03_extract_features.py.
    """
    import importlib.util

    round_dir = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}"
    if not round_dir.exists():
        return None

    # Collect FP session files
    fp_files = []
    for session_name in ["fp1", "fp2", "fp3"]:
        fp_path = round_dir / f"{session_name}.parquet"
        if fp_path.exists():
            fp_files.append(fp_path)
    if not fp_files:
        return None

    # Load and combine FP lap data
    all_laps = []
    for fp_path in fp_files:
        try:
            df = pd.read_parquet(fp_path)
            all_laps.append(df)
        except Exception:
            continue
    if not all_laps:
        return None

    combined = pd.concat(all_laps, ignore_index=True)

    # Standardize column names from raw FastF1 format
    col_map = {}
    if "LapTime_seconds" in combined.columns:
        col_map["LapTime_seconds"] = "lap_time"
    if "Sector1Time_seconds" in combined.columns:
        col_map["Sector1Time_seconds"] = "sector_1"
    if "Sector2Time_seconds" in combined.columns:
        col_map["Sector2Time_seconds"] = "sector_2"
    if "Sector3Time_seconds" in combined.columns:
        col_map["Sector3Time_seconds"] = "sector_3"
    if "Driver" in combined.columns:
        col_map["Driver"] = "driver_id"
    if "Compound" in combined.columns:
        col_map["Compound"] = "compound"
    if "Stint" in combined.columns:
        col_map["Stint"] = "stint_number"
    if "LapNumber" in combined.columns:
        col_map["LapNumber"] = "lap_number"
    combined = combined.rename(columns=col_map)

    # Handle timedelta lap times
    if "lap_time" not in combined.columns and "LapTime" in combined.columns:
        try:
            combined["lap_time"] = pd.to_timedelta(combined["LapTime"]).dt.total_seconds()
        except Exception:
            return None

    if "lap_time" not in combined.columns:
        return None

    combined = combined[combined["lap_time"].notna() & (combined["lap_time"] > 0)]
    if combined.empty:
        return None

    # Import the extraction function from Script 03
    script_03_path = Path(__file__).parent / "03_extract_features.py"
    if not script_03_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("extract_features", script_03_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    features_df = mod.extract_driver_features(combined, MIN_LONG_RUN_LAPS)
    if features_df is None or features_df.empty:
        return None

    return _standardize_fp_df(features_df, year, round_num)


# -- Core merge logic ----------------------------------------------------------

def merge_fp_features(
    model_rows: pd.DataFrame,
    abbrev_to_jolpica: dict[str, str],
) -> pd.DataFrame:
    """
    Left-join FP telemetry features onto the Jolpica model_rows.

    For each unique (season, round) in model_rows, attempts to find FP features.
    Converts FP driver abbreviation IDs to Jolpica IDs before merging.

    Returns the model_rows DataFrame with FP columns appended (NaN where unavailable).
    """
    # Ensure FP columns exist in the output (initialize as NaN)
    for col in FP_FEATURE_COLUMNS:
        if col not in model_rows.columns:
            model_rows[col] = np.nan

    rounds_with_fp = 0
    drivers_with_fp = 0

    unique_rounds = model_rows[["season", "round"]].drop_duplicates().values
    total_rounds = len(unique_rounds)

    for year, round_num in unique_rounds:
        year = int(year)
        round_num = int(round_num)

        fp_df = load_fp_features_for_round(year, round_num)
        if fp_df is None or fp_df.empty:
            continue

        # Convert FP driver_id from abbreviation to Jolpica
        fp_df = fp_df.copy()
        fp_df["driver_id"] = fp_df["driver_id"].map(abbrev_to_jolpica)
        fp_df = fp_df.dropna(subset=["driver_id"])  # drop unmapped drivers

        if fp_df.empty:
            continue

        rounds_with_fp += 1

        # Merge FP features into the matching rows
        mask = (model_rows["season"] == year) & (model_rows["round"] == round_num)
        round_rows = model_rows.loc[mask].copy()

        # Set index for efficient update
        for _, fp_row in fp_df.iterrows():
            driver_mask = mask & (model_rows["driver_id"] == fp_row["driver_id"])
            if driver_mask.any():
                for col in FP_FEATURE_COLUMNS:
                    if col in fp_row.index and pd.notna(fp_row[col]):
                        model_rows.loc[driver_mask, col] = fp_row[col]
                        drivers_with_fp += 1

    print(f"  FP features merged for {rounds_with_fp}/{total_rounds} rounds "
          f"({drivers_with_fp} driver-feature updates)")

    return model_rows


# -- Main pipeline -------------------------------------------------------------

def main() -> None:
    """Build the unified training dataset: Jolpica priors + FP telemetry."""
    parser = argparse.ArgumentParser(description="Build model inputs with leakage prevention")
    parser.add_argument(
        "--exclude-season-round",
        type=str,
        default=None,
        help="Exclude a specific round from training data. Format: YEAR:ROUND (e.g. 2026:3)",
    )
    parser.add_argument(
        "--exclude-after",
        type=str,
        default=None,
        help="Exclude all rounds at or after this point. Format: YEAR:ROUND (e.g. 2026:1)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("04 -- Build Model Inputs (Jolpica Priors + FP Telemetry)")
    print("=" * 70)

    # Step 1: Load Jolpica model_rows
    model_rows_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    if not model_rows_path.exists():
        print(f"ERROR: Model rows not found at {model_rows_path}")
        print("Run 03b_build_jolpica_features.py first.")
        return

    print(f"\n[Step 1] Loading Jolpica model rows ...")
    model_rows = pd.read_parquet(model_rows_path)
    print(f"  Loaded {len(model_rows):,} rows, {model_rows.shape[1]} columns")
    print(f"  Seasons: {sorted(model_rows['season'].unique())}")
    print(f"  Drivers: {model_rows['driver_id'].nunique()}")

    # Step 2: Load driver ID mapping
    print(f"\n[Step 2] Loading driver ID mapping ...")
    abbrev_to_jolpica = load_abbrev_to_jolpica_map()
    print(f"  Loaded {len(abbrev_to_jolpica)} abbreviation -> Jolpica mappings")

    # Step 3: Merge FP features
    print(f"\n[Step 3] Merging FP telemetry features ...")
    model_rows = merge_fp_features(model_rows, abbrev_to_jolpica)

    # Show FP coverage
    fp_available = model_rows["best_lap_time"].notna().sum()
    print(f"  Rows with FP data: {fp_available}/{len(model_rows)} "
          f"({fp_available / len(model_rows):.1%})")

    # Step 4: Apply feature engineering (creates engineered FP columns)
    print(f"\n[Step 4] Applying feature engineering ...")
    model_rows = engineer_features(model_rows)
    print(f"  Total columns after engineering: {model_rows.shape[1]}")

    # Step 5: Add sample weights
    print(f"\n[Step 5] Adding sample weights ...")
    model_rows["sample_weight"] = np.where(
        model_rows["season"] >= REGULATION_CHANGE_YEAR,
        REGULATION_WEIGHT_MULTIPLIER,
        1.0,
    )
    weight_summary = model_rows.groupby("season")["sample_weight"].first()
    print(f"  Weight by season:\n{weight_summary.to_string()}")

    # Step 6: Filter to rows with valid targets
    print(f"\n[Step 6] Filtering to rows with valid targets ...")
    rows_before = len(model_rows)
    training_data = model_rows[
        model_rows["finish_position"].notna()
        & model_rows["quali_position"].notna()
    ].copy()
    print(f"  Kept {len(training_data):,}/{rows_before:,} rows with both "
          f"finish_position and quali_position")

    if training_data.empty:
        print("\nERROR: No valid training data after filtering.")
        return

    # Step 6b: Data leakage prevention
    print(f"\n[Step 6b] Data leakage prevention ...")

    if args.exclude_season_round:
        parts = args.exclude_season_round.split(":")
        ex_year, ex_round = int(parts[0]), int(parts[1])
        before = len(training_data)
        training_data = training_data[
            ~((training_data["season"] == ex_year) & (training_data["round"] == ex_round))
        ]
        removed = before - len(training_data)
        print(f"  LEAKAGE GUARD: Excluded season {ex_year} round {ex_round}")
        print(f"  Rows: {before:,} -> {len(training_data):,} ({removed} removed)")

    if args.exclude_after:
        parts = args.exclude_after.split(":")
        ex_year, ex_round = int(parts[0]), int(parts[1])
        before = len(training_data)
        # Remove the target round and all later rounds in that season
        training_data = training_data[
            ~((training_data["season"] == ex_year) & (training_data["round"] >= ex_round))
        ]
        # Also exclude any future seasons
        training_data = training_data[training_data["season"] <= ex_year]
        removed = before - len(training_data)
        print(f"  LEAKAGE GUARD: Excluded season {ex_year} round >= {ex_round}")
        print(f"  Rows: {before:,} -> {len(training_data):,} ({removed} removed)")

    # Automatic leakage detection warning
    current_season_rows = training_data[training_data["season"] == CURRENT_SEASON]
    if len(current_season_rows) > 0:
        rounds_present = sorted(current_season_rows["round"].unique())
        print(f"\n  !! WARNING: Current season ({CURRENT_SEASON}) data in training set !!")
        print(f"  !! Rounds present: {[int(r) for r in rounds_present]}")
        print(f"  !! If predicting any of these rounds, use --exclude-after to prevent leakage !!")
    else:
        print(f"  OK: No current season ({CURRENT_SEASON}) data in training set.")

    if training_data.empty:
        print("\nERROR: No valid training data after leakage exclusions.")
        return

    # Step 7: Save
    print(f"\n[Step 7] Saving training data ...")
    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TRAINING_DATA_DIR / "all_training_data.parquet"
    training_data.to_parquet(output_path, index=False, engine="pyarrow")

    print(f"\n{'=' * 50}")
    print(f"TRAINING DATA SUMMARY")
    print(f"{'=' * 50}")
    print(f"  Total rows:     {len(training_data):,}")
    print(f"  Total columns:  {training_data.shape[1]}")
    print(f"  Seasons:        {sorted(training_data['season'].unique())}")
    print(f"  Rounds/season:  {training_data.groupby('season')['round'].nunique().to_dict()}")
    print(f"  Drivers:        {training_data['driver_id'].nunique()}")
    print(f"  FP coverage:    {training_data['best_lap_time'].notna().sum():,} rows")
    print(f"  Saved to:       {output_path}")

    print("\n" + "=" * 70)
    print("Build Model Inputs complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
