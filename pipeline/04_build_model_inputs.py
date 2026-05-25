"""
Script 04 -- Build Model Inputs

Merges Jolpica historical features with FP telemetry features to create the
unified training dataset for XGBoost models.

Architecture:
    Layer 1 (always available):  Jolpica priors -- ~2,662 rows x 78 cols
    Layer 2 (sparse):            FP telemetry features from FastF1

Most rows will have NaN for all FP columns. XGBoost handles NaN natively via
its "hist" tree method.

Data flow:
    1. Load all_model_rows.parquet (Jolpica priors with rolling features,
       track features, ratings)
    2. For each (year, round), locate FP features if they exist
    3. Left-join FP features onto model_rows by driver_id
       -- FP features use abbreviation IDs (VER, HAM); model_rows use Jolpica IDs
       -- Convert via driver_ids.json before merging
    4. Apply feature engineering (pace deltas, theoretical best, etc.)
    5. Add sample_weight (2.5x for 2026, 1.0 for earlier)
    6. Save combined training data

Output:
    models/training_data/all_training_data.parquet

Usage:
    python pipeline/04_build_model_inputs.py
    python pipeline/04_build_model_inputs.py --exclude-after 2026:3
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    JOLPICA_MODEL_ROWS_DIR,
    FEATURES_DIR,
    TRAINING_DATA_DIR,
    FEATURE_COLUMNS,
    CURRENT_SEASON,
    HISTORICAL_SEASONS,
    REGULATION_CHANGE_YEAR,
    REGULATION_WEIGHT_MULTIPLIER,
    SEED_DIR,
    FASTF1_RAW_DIR,
    PROCESSED_DIR,
)
from pipeline.feature_engineering import engineer_features


# -- Weather features (Level 3) -----------------------------------------------
# Produced by pipeline/03c_extract_session_weather.py. Joined onto model_rows
# by (season, round) below. Each model picks the relevant session-suffix:
#   quali model      -> weather_*_quali
#   race / race_fp   -> weather_*_race
#   sprint           -> weather_*_sprint  (sprint weekends only; NaN otherwise)
#
# The model never sees raw aggregate names — only these per-session columns.

SESSION_WEATHER_PATH = PROCESSED_DIR / "weather" / "all_session_weather.parquet"

WEATHER_SESSION_MAP = {
    "Q":  "quali",
    "R":  "race",
    "SR": "sprint",
}

WEATHER_METRIC_COLS = [
    "was_wet",
    "precip_minutes",
    "track_temp_avg",
    "air_temp_avg",
    "humidity_avg",
]


# -- FP feature columns -------------------------------------------------------
# Base columns from 03_extract_features.py (config/settings.py FEATURE_COLUMNS)
# plus metadata columns that may appear in the features parquet.

FP_BASE_COLUMNS = list(FEATURE_COLUMNS)

FP_EXTRA_COLUMNS = [
    "total_laps",
    "long_run_laps",
    "fp_sessions_used",
]

FP_ALL_POSSIBLE_COLUMNS = FP_BASE_COLUMNS + FP_EXTRA_COLUMNS

# Engineered columns created by pipeline/feature_engineering.py.
# We check for these dynamically in the features parquet in case
# feature engineering was already applied before saving.
ENGINEERED_FP_COLUMNS = [
    "pace_delta",
    "pace_consistency_ratio",
    "sector_1_delta",
    "sector_2_delta",
    "sector_3_delta",
    "theoretical_best",
    "cv_lap_time",
    "laps_per_session",
    "top3_vs_top5",
    "top5_vs_top10",
    "long_run_delta",
    "deg_x_laps",
]


# -- Driver ID mapping --------------------------------------------------------

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


# -- FP feature loading -------------------------------------------------------

def load_fp_features_for_round(
    year: int, round_num: int
) -> pd.DataFrame | None:
    """
    Attempt to load FP features for a given (year, round).

    Search paths:
        Current season (2026): data/processed/features/round{N}/features.parquet
        Historical:            data/processed/features/year{YYYY}/round{N}/features.parquet
    """
    if year == CURRENT_SEASON:
        fp_path = FEATURES_DIR / f"round{round_num}" / "features.parquet"
    else:
        fp_path = FEATURES_DIR / f"year{year}" / f"round{round_num}" / "features.parquet"

    if not fp_path.exists():
        return None

    try:
        df = pd.read_parquet(fp_path)
    except Exception as e:
        print(f"    Warning: could not read {fp_path}: {e}")
        return None

    if df is None or df.empty:
        return None

    if "driver_id" not in df.columns:
        print(f"    Warning: no driver_id column in {fp_path}")
        return None

    # Keep only driver_id and recognized FP columns
    all_fp_cols = FP_ALL_POSSIBLE_COLUMNS + ENGINEERED_FP_COLUMNS
    keep_cols = ["driver_id"] + [c for c in all_fp_cols if c in df.columns]
    return df[keep_cols].copy()


# -- Core merge logic ---------------------------------------------------------

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
    unique_rounds = model_rows[["season", "round"]].drop_duplicates().values
    total_rounds = len(unique_rounds)
    rounds_with_fp = 0
    rows_with_fp = 0

    # Collect all FP dataframes keyed by (year, round) for a single merge
    fp_frames = []

    for year, round_num in unique_rounds:
        year = int(year)
        round_num = int(round_num)

        fp_df = load_fp_features_for_round(year, round_num)
        if fp_df is None or fp_df.empty:
            continue

        # Convert FP driver_id from abbreviation to Jolpica ID
        fp_df = fp_df.copy()
        fp_df["driver_id"] = fp_df["driver_id"].map(abbrev_to_jolpica)
        fp_df = fp_df.dropna(subset=["driver_id"])

        if fp_df.empty:
            continue

        # Add season/round keys for merging
        fp_df["season"] = year
        fp_df["round"] = round_num
        fp_frames.append(fp_df)
        rounds_with_fp += 1

    if fp_frames:
        # Combine all FP data and merge in one go
        all_fp = pd.concat(fp_frames, ignore_index=True)

        # Identify the FP feature columns (everything except the join keys)
        fp_feature_cols = [c for c in all_fp.columns if c not in ("season", "round", "driver_id")]

        # Drop any FP columns that already exist in model_rows to avoid suffixes
        for col in fp_feature_cols:
            if col in model_rows.columns:
                model_rows = model_rows.drop(columns=[col])

        model_rows = model_rows.merge(
            all_fp,
            on=["season", "round", "driver_id"],
            how="left",
        )

        rows_with_fp = model_rows[fp_feature_cols[0]].notna().sum() if fp_feature_cols else 0
    else:
        # No FP data found -- ensure FP columns exist as NaN
        for col in FP_ALL_POSSIBLE_COLUMNS:
            if col not in model_rows.columns:
                model_rows[col] = np.nan

    print(f"  FP features found for {rounds_with_fp}/{total_rounds} rounds")
    print(f"  Rows with FP data: {rows_with_fp:,}/{len(model_rows):,}")

    return model_rows


# -- Session weather merge (Level 3 Phase B) ----------------------------------

def merge_session_weather(model_rows: pd.DataFrame) -> pd.DataFrame:
    """Join per-session weather aggregates onto every training row.

    For each (season, round) we pivot the long-format session_weather table
    into wide weather_*_{race,quali,sprint} columns. Every row of model_rows
    for that round gets the same weather features (weather is a session-level
    fact, not driver-level).

    Rows for rounds where no weather has been extracted yet (or where the
    specific session is missing — e.g. sprint columns on a non-sprint
    weekend) become NaN. XGBoost handles those natively.

    Returns model_rows with these columns appended:
        weather_was_wet_{race,quali,sprint}            (bool, cast to float for parquet)
        weather_precip_minutes_{race,quali,sprint}     (int)
        weather_track_temp_{race,quali,sprint}         (float, deg C)
        weather_air_temp_{race,quali,sprint}           (float, deg C)
        weather_humidity_{race,quali,sprint}           (float, %)
    """
    if not SESSION_WEATHER_PATH.exists():
        print(f"  WARNING: {SESSION_WEATHER_PATH} not found — weather features will be all NaN.")
        print(f"           Run pipeline/03c_extract_session_weather.py first.")
        # Still add the columns so feature lists don't break downstream
        for sess_label in WEATHER_SESSION_MAP.values():
            for metric in WEATHER_METRIC_COLS:
                col = _weather_col(metric, sess_label)
                if col not in model_rows.columns:
                    model_rows[col] = np.nan
        return model_rows

    weather_df = pd.read_parquet(SESSION_WEATHER_PATH)
    # Keep only sessions we care about for modelling
    weather_df = weather_df[weather_df["session_name"].isin(WEATHER_SESSION_MAP.keys())].copy()

    # Pivot wide: one row per (season, round) with weather_*_{race|quali|sprint} columns
    wide_parts = []
    for sess_code, sess_label in WEATHER_SESSION_MAP.items():
        sub = weather_df[weather_df["session_name"] == sess_code]
        if sub.empty:
            continue
        keep = ["season", "round"] + WEATHER_METRIC_COLS
        sub = sub[keep].copy()
        rename_map = {m: _weather_col(m, sess_label) for m in WEATHER_METRIC_COLS}
        sub = sub.rename(columns=rename_map)
        wide_parts.append(sub)

    if not wide_parts:
        print("  WARNING: no usable weather rows found in extract.")
        return model_rows

    # Merge each per-session frame onto a (season, round) key. We don't dedup
    # — if a (season, round) appears more than once for the same session in
    # the source extract, the merge would duplicate rows. Defensive: keep
    # only one row per (season, round, session) by groupby-first before pivot.
    weather_wide = wide_parts[0]
    for part in wide_parts[1:]:
        weather_wide = weather_wide.merge(part, on=["season", "round"], how="outer")

    # Make sure all expected columns exist (handles seasons with no sprint data)
    for sess_label in WEATHER_SESSION_MAP.values():
        for metric in WEATHER_METRIC_COLS:
            col = _weather_col(metric, sess_label)
            if col not in weather_wide.columns:
                weather_wide[col] = np.nan

    # Cast booleans to float so XGBoost gets numeric 0/1 (and NaN works)
    for sess_label in WEATHER_SESSION_MAP.values():
        col = _weather_col("was_wet", sess_label)
        weather_wide[col] = weather_wide[col].astype(float)

    before = model_rows.shape[1]
    # Drop any existing weather columns to allow clean re-runs
    weather_cols_in_rows = [c for c in model_rows.columns if c.startswith("weather_")]
    if weather_cols_in_rows:
        model_rows = model_rows.drop(columns=weather_cols_in_rows)

    model_rows = model_rows.merge(weather_wide, on=["season", "round"], how="left")
    added = model_rows.shape[1] - before
    matched_rounds = weather_wide.shape[0]
    total_rounds = model_rows[["season", "round"]].drop_duplicates().shape[0]
    print(f"  Weather: {matched_rounds} (season, round) pairs in extract, "
          f"covering {total_rounds} model_rows rounds")
    print(f"  Added {added} weather feature columns")

    # Quick sanity: how many training rows have was_wet_race populated?
    if "weather_was_wet_race" in model_rows.columns:
        non_nan = model_rows["weather_was_wet_race"].notna().sum()
        wet = int(model_rows["weather_was_wet_race"].fillna(0).sum())
        print(f"  Race weather populated: {non_nan:,}/{len(model_rows):,} rows; "
              f"{wet:,} are wet ({wet / max(non_nan, 1) * 100:.1f}% of populated)")

    return model_rows


def _weather_col(metric: str, session_label: str) -> str:
    """Canonical column name. Examples:
        ("was_wet",        "race")   -> "weather_was_wet_race"
        ("track_temp_avg", "quali")  -> "weather_track_temp_quali"
        ("precip_minutes", "sprint") -> "weather_precip_minutes_sprint"
    """
    # Drop the trailing "_avg" — it's noise once the column says "track_temp_quali".
    metric_clean = metric.replace("_avg", "")
    return f"weather_{metric_clean}_{session_label}"


# -- Main pipeline ------------------------------------------------------------

def main() -> None:
    """Build the unified training dataset: Jolpica priors + FP telemetry."""
    parser = argparse.ArgumentParser(description="Build model inputs: merge Jolpica + FP features")
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
    parser.add_argument(
        "--force-include-current",
        action="store_true",
        help="Opt-in: allow current-season rows to remain in training data. "
             "Without this flag, presence of current-season rows is a hard error to "
             "prevent accidental leakage when predicting that season's upcoming rounds.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("04 -- Build Model Inputs (Jolpica Priors + FP Telemetry)")
    print("=" * 70)

    # ---- Step 1: Load Jolpica model_rows -------------------------------------
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

    # ---- Step 2: Load driver ID mapping --------------------------------------
    print(f"\n[Step 2] Loading driver ID mapping ...")
    abbrev_to_jolpica = load_abbrev_to_jolpica_map()
    print(f"  Loaded {len(abbrev_to_jolpica)} abbreviation -> Jolpica mappings")

    # ---- Step 3: Merge FP features -------------------------------------------
    print(f"\n[Step 3] Merging FP telemetry features ...")
    model_rows = merge_fp_features(model_rows, abbrev_to_jolpica)

    # ---- Step 3.5: Merge per-session weather (Level 3 Phase B) ---------------
    print(f"\n[Step 3.5] Merging per-session weather aggregates ...")
    model_rows = merge_session_weather(model_rows)

    # ---- Step 4: Apply feature engineering -----------------------------------
    print(f"\n[Step 4] Applying feature engineering ...")
    model_rows = engineer_features(model_rows)
    print(f"  Total columns after engineering: {model_rows.shape[1]}")

    # ---- Step 5: Add sample weights ------------------------------------------
    # Round-aware ramp for regulation-change weight: with only a few rounds of
    # current-season data, a flat 2.5x multiplier can over-weight noisy early
    # rounds. We ramp from REGULATION_WEIGHT_START -> REGULATION_WEIGHT_MULTIPLIER
    # as more rounds accumulate. Past-regulation seasons stay at 2.5x (they are
    # the full-season reference used to calibrate the multiplier).
    print(f"\n[Step 5] Adding sample weights ...")

    REGULATION_WEIGHT_START = 2.0
    REGULATION_WEIGHT_FULL_THRESHOLD = 10  # rounds of current-reg data for full weight

    current_reg_rows = model_rows[model_rows["season"] >= REGULATION_CHANGE_YEAR]
    if len(current_reg_rows) > 0:
        # Only the current (still-running) season ramps; past reg-era seasons are full.
        active_season_rounds = (
            current_reg_rows[current_reg_rows["season"] == CURRENT_SEASON]["round"].nunique()
        )
    else:
        active_season_rounds = 0

    if active_season_rounds >= REGULATION_WEIGHT_FULL_THRESHOLD or active_season_rounds == 0:
        current_season_weight = REGULATION_WEIGHT_MULTIPLIER
    else:
        frac = active_season_rounds / REGULATION_WEIGHT_FULL_THRESHOLD
        current_season_weight = REGULATION_WEIGHT_START + (
            REGULATION_WEIGHT_MULTIPLIER - REGULATION_WEIGHT_START
        ) * frac

    # Apply weights:
    #   - Past regulation-era seasons (>= REGULATION_CHANGE_YEAR, < CURRENT_SEASON): full multiplier
    #   - Current season (== CURRENT_SEASON): ramped weight
    #   - Older seasons: 1.0
    conds = [
        model_rows["season"] == CURRENT_SEASON,
        model_rows["season"] >= REGULATION_CHANGE_YEAR,
    ]
    choices = [current_season_weight, REGULATION_WEIGHT_MULTIPLIER]
    model_rows["sample_weight"] = np.select(conds, choices, default=1.0)

    print(f"  Current season rounds available: {active_season_rounds}")
    print(f"  Current-season weight: {current_season_weight:.2f}x "
          f"(ramp {REGULATION_WEIGHT_START}->{REGULATION_WEIGHT_MULTIPLIER} "
          f"over {REGULATION_WEIGHT_FULL_THRESHOLD} rounds)")

    weight_counts = model_rows.groupby("sample_weight").size()
    for weight_val, count in weight_counts.items():
        print(f"  Weight {weight_val}: {count:,} rows")

    # ---- Step 6: Data leakage prevention -------------------------------------
    print(f"\n[Step 6] Data leakage prevention ...")

    if args.exclude_season_round:
        parts = args.exclude_season_round.split(":")
        ex_year, ex_round = int(parts[0]), int(parts[1])
        before = len(model_rows)
        model_rows = model_rows[
            ~((model_rows["season"] == ex_year) & (model_rows["round"] == ex_round))
        ]
        removed = before - len(model_rows)
        print(f"  LEAKAGE GUARD: Excluded season {ex_year} round {ex_round}")
        print(f"  Rows: {before:,} -> {len(model_rows):,} ({removed} removed)")

    if args.exclude_after:
        parts = args.exclude_after.split(":")
        ex_year, ex_round = int(parts[0]), int(parts[1])
        before = len(model_rows)
        model_rows = model_rows[
            ~((model_rows["season"] == ex_year) & (model_rows["round"] >= ex_round))
        ]
        model_rows = model_rows[model_rows["season"] <= ex_year]
        removed = before - len(model_rows)
        print(f"  LEAKAGE GUARD: Excluded season {ex_year} round >= {ex_round}")
        print(f"  Rows: {before:,} -> {len(model_rows):,} ({removed} removed)")

    # Leakage guard: current-season rows are only safe when the caller has
    # explicitly declared a cutoff (--exclude-after / --exclude-season-round)
    # or has opted in with --force-include-current. Otherwise, accidentally
    # leaving current-season data in the training set risks leaking future-round
    # information when predicting upcoming rounds.
    current_season_rows = model_rows[model_rows["season"] == CURRENT_SEASON]
    declared_cutoff = bool(args.exclude_after) or bool(args.exclude_season_round)
    if len(current_season_rows) > 0:
        rounds_present = sorted(current_season_rows["round"].unique())
        if declared_cutoff:
            print(f"  OK: Current season ({CURRENT_SEASON}) rounds retained under "
                  f"explicit cutoff: {[int(r) for r in rounds_present]}")
        elif args.force_include_current:
            print(f"\n  NOTE: Current season ({CURRENT_SEASON}) data retained by "
                  f"--force-include-current")
            print(f"  Rounds present: {[int(r) for r in rounds_present]}")
        else:
            print(f"\n  ERROR: Current season ({CURRENT_SEASON}) data in training set "
                  f"(rounds {[int(r) for r in rounds_present]}) with no declared cutoff.")
            print(f"  This risks leaking future-round info. Pass --exclude-after "
                  f"{CURRENT_SEASON}:N to cut off, or --force-include-current to override.")
            sys.exit(2)
    else:
        print(f"  OK: No current season ({CURRENT_SEASON}) data in training set.")

    # ---- Step 7: Filter to rows with valid targets ---------------------------
    print(f"\n[Step 7] Filtering to rows with valid targets ...")
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

    # ---- Step 8: Save --------------------------------------------------------
    print(f"\n[Step 8] Saving training data ...")
    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TRAINING_DATA_DIR / "all_training_data.parquet"
    training_data.to_parquet(output_path, index=False, engine="pyarrow")

    # ---- Summary -------------------------------------------------------------
    fp_indicator_col = "best_lap_time"
    fp_coverage = (
        training_data[fp_indicator_col].notna().sum()
        if fp_indicator_col in training_data.columns
        else 0
    )
    feature_cols = [
        c for c in training_data.columns
        if c not in (
            "season", "round", "driver_id", "constructor_id",
            "finish_position", "quali_position", "qualifying_position",
            "race_finish_position", "fantasy_points",
            "sample_weight", "full_name",
        )
    ]

    print(f"\n{'=' * 60}")
    print(f"TRAINING DATA SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total rows:          {len(training_data):,}")
    print(f"  Rows with FP data:   {fp_coverage:,} ({fp_coverage / len(training_data):.1%})")
    print(f"  Feature columns:     {len(feature_cols)}")
    print(f"  Total columns:       {training_data.shape[1]}")
    print(f"  Seasons:             {sorted(training_data['season'].unique())}")
    print(f"  Rounds/season:       {training_data.groupby('season')['round'].nunique().to_dict()}")
    print(f"  Drivers:             {training_data['driver_id'].nunique()}")

    weight_dist = training_data["sample_weight"].value_counts().sort_index()
    print(f"  Sample weights:")
    for w, cnt in weight_dist.items():
        print(f"    {w}x: {cnt:,} rows")

    print(f"  Saved to:            {output_path}")
    print(f"\n{'=' * 60}")
    print("Build Model Inputs complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
