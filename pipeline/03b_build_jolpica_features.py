"""
Script 03b — Build Jolpica Rolling Features

Reads normalized Jolpica CSV data (race results, qualifying, sprints, race info)
across all historical + current seasons, and computes time-safe rolling features
for ML model training.

CRITICAL: Every rolling/expanding window uses .shift(1) so that the current
race's actual result never leaks into its own features.

Input:
    data/processed/jolpica/normalized/{year}/race_results.csv
    data/processed/jolpica/normalized/{year}/qualifying_results.csv
    data/processed/jolpica/normalized/{year}/sprint_results.csv
    data/processed/jolpica/normalized/{year}/races.csv

Output:
    data/processed/jolpica/model_rows/model_rows_{year}.parquet   (per season)
    data/processed/jolpica/model_rows/all_model_rows.parquet      (combined)
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    HISTORICAL_SEASONS,
    CURRENT_SEASON,
    JOLPICA_NORMALIZED_DIR,
    JOLPICA_MODEL_ROWS_DIR,
    SEED_DIR,
)
from config.track_classifications import get_track_features, TRACK_FEATURE_NAMES
from config.team_driver_ratings import (
    get_team_strategy_rating,
    get_team_adaptability,
    get_driver_tire_mgmt,
    get_driver_overtaking,
    get_driver_quali_skill,
)

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALL_SEASONS = sorted(set(HISTORICAL_SEASONS + [CURRENT_SEASON]))

# Status substrings used to classify DNF causes
MECHANICAL_KEYWORDS = [
    "engine", "gearbox", "power unit", "electrical", "hydraulic",
    "oil", "fuel", "turbo", "brakes", "suspension", "water",
    "transmission", "clutch", "overheating", "radiator", "exhaust",
    "differential", "driveshaft", "throttle", "battery", "ers",
    "wheel", "tyre", "puncture", "steering",
]
COLLISION_KEYWORDS = [
    "collision", "accident", "crash", "contact", "damage",
]
DRIVER_ERROR_KEYWORDS = [
    "spun off", "off track", "spun",
]


# ============================================================================
# Step 1: Load and merge all seasons into one big DataFrame
# ============================================================================

def load_season_csvs(year: int, base_dir: Path) -> dict[str, pd.DataFrame | None]:
    """Load the four normalized CSVs for a given year, returning a dict."""
    season_dir = base_dir / str(year)
    result = {}
    for name in ("race_results", "qualifying_results", "sprint_results", "races"):
        fpath = season_dir / f"{name}.csv"
        if fpath.exists():
            result[name] = pd.read_csv(fpath)
        else:
            result[name] = None
    return result


def load_all_seasons() -> pd.DataFrame:
    """
    Load and merge race_results, qualifying, sprints, and race metadata
    across every season into a single DataFrame with one row per
    (season, round, driver_id).
    """
    all_race = []
    all_quali = []
    all_sprint = []
    all_races = []

    for year in ALL_SEASONS:
        csvs = load_season_csvs(year, JOLPICA_NORMALIZED_DIR)
        if csvs["race_results"] is not None:
            all_race.append(csvs["race_results"])
        if csvs["qualifying_results"] is not None:
            all_quali.append(csvs["qualifying_results"])
        if csvs["sprint_results"] is not None:
            all_sprint.append(csvs["sprint_results"])
        if csvs["races"] is not None:
            all_races.append(csvs["races"])

    if not all_race:
        raise FileNotFoundError(
            f"No race_results.csv found in {JOLPICA_NORMALIZED_DIR} for seasons {ALL_SEASONS}"
        )

    race_df = pd.concat(all_race, ignore_index=True)
    quali_df = pd.concat(all_quali, ignore_index=True) if all_quali else pd.DataFrame()
    sprint_df = pd.concat(all_sprint, ignore_index=True) if all_sprint else pd.DataFrame()
    races_df = pd.concat(all_races, ignore_index=True) if all_races else pd.DataFrame()

    # ----- Merge qualifying onto race results -----
    merge_keys = ["season", "round", "driver_id"]
    if not quali_df.empty:
        # Keep only columns that add information (avoid collisions)
        quali_cols = [c for c in quali_df.columns if c not in race_df.columns or c in merge_keys]
        df = race_df.merge(quali_df[quali_cols], on=merge_keys, how="left")
    else:
        df = race_df.copy()

    # If quali_position came from race_results already, keep it; otherwise fill
    if "quali_position" not in df.columns:
        df["quali_position"] = np.nan

    # ----- Merge sprint results -----
    if not sprint_df.empty:
        sprint_cols = [c for c in sprint_df.columns if c not in df.columns or c in merge_keys]
        df = df.merge(sprint_df[sprint_cols], on=merge_keys, how="left")
    for col in ("sprint_position", "sprint_points"):
        if col not in df.columns:
            df[col] = np.nan

    # ----- Merge race metadata (circuit_id, has_sprint, race_name, race_date) -----
    if not races_df.empty:
        race_meta_keys = ["season", "round"]
        meta_cols = [c for c in races_df.columns if c not in df.columns or c in race_meta_keys]
        df = df.merge(races_df[meta_cols], on=race_meta_keys, how="left")
    for col in ("circuit_id", "has_sprint", "race_name", "race_date"):
        if col not in df.columns:
            df[col] = "" if col in ("circuit_id", "race_name", "race_date") else 0

    # ----- Ensure core numeric types -----
    for col in ("grid", "finish_position", "quali_position", "points",
                "sprint_position", "sprint_points", "laps_completed"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "status" not in df.columns:
        df["status"] = "Finished"
    df["status"] = df["status"].fillna("Finished")

    df = df.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)
    print(f"  Loaded {len(df):,} rows across {df['season'].nunique()} seasons, "
          f"{df['driver_id'].nunique()} drivers")
    return df


# ============================================================================
# Step 2: Status flags and DNF classification
# ============================================================================

def compute_status_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add boolean columns for finish status and DNF cause buckets."""
    status_lower = df["status"].str.lower().fillna("finished")

    # Finished normally: "Finished", starts with "+", or "Lapped"
    is_finished = (
        (status_lower == "finished")
        | status_lower.str.startswith("+")
        | (status_lower == "lapped")
    )

    # DSQ / DNS
    is_dsq = status_lower.str.contains("disqualified", na=False)
    is_dns = status_lower.str.contains("did not start|dns|not classified|withdrew", na=False)

    # DNF = not finished AND not DSQ AND not DNS
    df["is_finished"] = is_finished.astype(int)
    df["is_dsq"] = is_dsq.astype(int)
    df["is_dns"] = is_dns.astype(int)
    df["is_dnf"] = ((~is_finished) & (~is_dsq) & (~is_dns)).astype(int)

    # DNF cause buckets (only meaningful when is_dnf == 1)
    df["dnf_mechanical"] = (
        status_lower.str.contains("|".join(MECHANICAL_KEYWORDS), na=False)
        & (df["is_dnf"] == 1)
    ).astype(int)

    df["dnf_collision"] = (
        status_lower.str.contains("|".join(COLLISION_KEYWORDS), na=False)
        & (df["is_dnf"] == 1)
    ).astype(int)

    # Driver error: spun off / off track but NOT collision
    df["dnf_driver_error"] = (
        status_lower.str.contains("|".join(DRIVER_ERROR_KEYWORDS), na=False)
        & (df["dnf_collision"] == 0)
        & (df["is_dnf"] == 1)
    ).astype(int)

    # Position delta (positive = gained places)
    df["position_delta"] = df["grid"] - df["finish_position"]

    # Clean finish position (NaN for DNFs so rolling means exclude them)
    df["finish_pos_clean"] = df["finish_position"].where(df["is_dnf"] == 0)

    return df


# ============================================================================
# Step 3: Rolling features per DRIVER (cross-season, shift(1))
# ============================================================================

def _shifted_rolling(series: pd.Series, window: int) -> pd.Series:
    """shift(1) then rolling mean with min_periods=1."""
    return series.shift(1).rolling(window, min_periods=1).mean()


def _shifted_expanding_mean(series: pd.Series) -> pd.Series:
    """shift(1) then expanding mean."""
    return series.shift(1).expanding(min_periods=1).mean()


def _shifted_expanding_median(series: pd.Series) -> pd.Series:
    """shift(1) then expanding median."""
    return series.shift(1).expanding(min_periods=1).median()


def compute_driver_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-driver rolling features across all seasons (cross-season continuity).
    Sorted by (driver_id, season, round) with shift(1) applied before rolling.
    """
    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)
    g = df.groupby("driver_id", sort=False)

    # Points rolling
    df["roll_points_3"] = g["points"].transform(lambda s: _shifted_rolling(s, 3))
    df["roll_points_5"] = g["points"].transform(lambda s: _shifted_rolling(s, 5))

    # Finish position rolling (clean finishes only — use finish_pos_clean)
    df["roll_finishpos_3"] = g["finish_pos_clean"].transform(lambda s: _shifted_rolling(s, 3))
    df["roll_finishpos_5"] = g["finish_pos_clean"].transform(lambda s: _shifted_rolling(s, 5))

    # Quali rolling
    df["roll_quali_3"] = g["quali_position"].transform(lambda s: _shifted_rolling(s, 3))
    df["roll_quali_5"] = g["quali_position"].transform(lambda s: _shifted_rolling(s, 5))

    # DNF rate
    df["roll_dnf_rate_5"] = g["is_dnf"].transform(lambda s: _shifted_rolling(s, 5))

    # DNF cause rates per driver
    df["roll_mech_dnf_rate_5_driver"] = g["dnf_mechanical"].transform(
        lambda s: _shifted_rolling(s, 5)
    )
    df["roll_collision_dnf_rate_5_driver"] = g["dnf_collision"].transform(
        lambda s: _shifted_rolling(s, 5)
    )
    df["roll_drivererror_dnf_rate_5_driver"] = g["dnf_driver_error"].transform(
        lambda s: _shifted_rolling(s, 5)
    )

    return df


# ============================================================================
# Step 4: Constructor rolling features (cross-season, shift(1))
# ============================================================================

def compute_constructor_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-constructor mechanical DNF rate (aggregated across both drivers)."""
    # We need per-constructor rows; since each row is already (season, round, driver),
    # we group by constructor_id to get constructor-level rolling across all their entries.
    df = df.sort_values(["constructor_id", "season", "round"]).reset_index(drop=True)
    g = df.groupby("constructor_id", sort=False)

    df["roll_mech_dnf_rate_5_constructor"] = g["dnf_mechanical"].transform(
        lambda s: _shifted_rolling(s, 5)
    )

    # Restore canonical sort
    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)
    return df


# ============================================================================
# Step 5: Qualifying priors
# ============================================================================

def compute_qualifying_priors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Qualifying-specific features: per-driver, per-constructor, per-circuit,
    field baselines, teammate deltas, circuit priors.
    """
    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)

    # ---- Per-driver quali (cross-season) ----
    gd = df.groupby("driver_id", sort=False)
    df["driver_quali_last"] = gd["quali_position"].transform(lambda s: s.shift(1))
    df["driver_roll_quali_3"] = gd["quali_position"].transform(lambda s: _shifted_rolling(s, 3))
    df["driver_roll_quali_5"] = gd["quali_position"].transform(lambda s: _shifted_rolling(s, 5))

    # Within-season expanding (reset at season boundary)
    gds = df.groupby(["driver_id", "season"], sort=False)
    df["driver_season_avg_quali"] = gds["quali_position"].transform(
        lambda s: _shifted_expanding_mean(s)
    )
    df["driver_season_med_quali"] = gds["quali_position"].transform(
        lambda s: _shifted_expanding_median(s)
    )

    # ---- Per-constructor best quali per round ----
    # First compute team best quali per (season, round, constructor_id)
    team_best = (
        df.groupby(["season", "round", "constructor_id"])["quali_position"]
        .min()
        .reset_index()
        .rename(columns={"quali_position": "team_best_quali"})
    )
    df = df.merge(team_best, on=["season", "round", "constructor_id"], how="left")

    df = df.sort_values(["constructor_id", "season", "round", "driver_id"]).reset_index(drop=True)

    # For constructor-level rolling, we need one entry per (constructor, season, round).
    # But since we're applying transform per-row grouped by constructor, and there are
    # two drivers per team per round, we need to de-duplicate within the group.
    # Use a temporary DataFrame to compute constructor-level features, then map back.
    constructor_quali_df = (
        df.groupby(["constructor_id", "season", "round"])["team_best_quali"]
        .first()
        .reset_index()
        .sort_values(["constructor_id", "season", "round"])
    )
    gc = constructor_quali_df.groupby("constructor_id", sort=False)
    constructor_quali_df["constructor_quali_last"] = gc["team_best_quali"].transform(
        lambda s: s.shift(1)
    )
    constructor_quali_df["constructor_roll_quali_3"] = gc["team_best_quali"].transform(
        lambda s: _shifted_rolling(s, 3)
    )
    constructor_quali_df["constructor_roll_quali_5"] = gc["team_best_quali"].transform(
        lambda s: _shifted_rolling(s, 5)
    )
    # Within-season expanding for constructor
    gcs = constructor_quali_df.groupby(["constructor_id", "season"], sort=False)
    constructor_quali_df["constructor_season_avg_quali"] = gcs["team_best_quali"].transform(
        lambda s: _shifted_expanding_mean(s)
    )

    # Merge constructor-level features back
    cq_cols = [
        "constructor_id", "season", "round",
        "constructor_quali_last", "constructor_roll_quali_3",
        "constructor_roll_quali_5", "constructor_season_avg_quali",
    ]
    df = df.merge(constructor_quali_df[cq_cols], on=["constructor_id", "season", "round"], how="left")

    # ---- Field baseline (all-driver average quali per round, expanded within season) ----
    round_avg_quali = (
        df.groupby(["season", "round"])["quali_position"]
        .mean()
        .reset_index()
        .rename(columns={"quali_position": "round_avg_quali"})
        .sort_values(["season", "round"])
    )
    gs = round_avg_quali.groupby("season", sort=False)
    round_avg_quali["field_season_avg_quali"] = gs["round_avg_quali"].transform(
        lambda s: _shifted_expanding_mean(s)
    )
    df = df.merge(
        round_avg_quali[["season", "round", "field_season_avg_quali"]],
        on=["season", "round"],
        how="left",
    )

    df["driver_vs_field_season"] = df["driver_season_avg_quali"] - df["field_season_avg_quali"]
    df["constructor_vs_field_season"] = df["constructor_season_avg_quali"] - df["field_season_avg_quali"]

    # ---- Teammate delta ----
    # For each driver, compute their teammate's quali position in the same round
    teammate_df = (
        df[["season", "round", "constructor_id", "driver_id", "quali_position"]]
        .copy()
    )
    # Self-join: for each row, find the other driver(s) on the same team in the same round
    teammate_merged = teammate_df.merge(
        teammate_df,
        on=["season", "round", "constructor_id"],
        suffixes=("", "_mate"),
    )
    teammate_merged = teammate_merged[
        teammate_merged["driver_id"] != teammate_merged["driver_id_mate"]
    ]
    # Average teammate quali (in case >1 teammate, e.g. 3-car team edge case)
    teammate_avg = (
        teammate_merged.groupby(["season", "round", "driver_id"])["quali_position_mate"]
        .mean()
        .reset_index()
        .rename(columns={"quali_position_mate": "teammate_quali"})
    )
    df = df.merge(teammate_avg, on=["season", "round", "driver_id"], how="left")
    df["team_delta_last_raw"] = df["quali_position"] - df["teammate_quali"]

    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)
    gd2 = df.groupby("driver_id", sort=False)
    df["team_delta_last"] = gd2["team_delta_last_raw"].transform(lambda s: s.shift(1))
    df["team_delta_roll_3"] = gd2["team_delta_last_raw"].transform(lambda s: _shifted_rolling(s, 3))
    df["team_delta_roll_5"] = gd2["team_delta_last_raw"].transform(lambda s: _shifted_rolling(s, 5))

    # ---- Circuit-specific priors ----
    gdc = df.groupby(["driver_id", "circuit_id"], sort=False)
    df["driver_circuit_exp"] = gdc["quali_position"].transform(
        lambda s: _shifted_expanding_mean(s)
    )
    df["driver_circuit_roll_3"] = gdc["quali_position"].transform(
        lambda s: _shifted_rolling(s, 3)
    )

    gcc = df.groupby(["constructor_id", "circuit_id"], sort=False)
    df["constructor_circuit_exp"] = gcc["team_best_quali"].transform(
        lambda s: _shifted_expanding_mean(s)
    )

    # Drop intermediate columns
    df.drop(columns=["team_best_quali", "team_delta_last_raw", "teammate_quali"],
            inplace=True, errors="ignore")

    return df


# ============================================================================
# Step 6: Race model derived features
# ============================================================================

def compute_race_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derived features inspired by the V1 race model: expanding means, binary
    quali flags, form features, track interactions, etc.
    """
    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)

    # ---- Expanding position means (shifted, excluding DNFs) ----
    # Team average position (constructor-level expanding, within season)
    df_sorted_c = df.sort_values(["constructor_id", "season", "round"]).reset_index(drop=True)
    gcs = df_sorted_c.groupby(["constructor_id", "season"], sort=False)
    df_sorted_c["team_avg_position"] = gcs["finish_pos_clean"].transform(
        lambda s: _shifted_expanding_mean(s)
    )
    df["team_avg_position"] = df_sorted_c.sort_values(
        ["driver_id", "season", "round"]
    )["team_avg_position"].values

    # Driver + circuit expanding (cross-season)
    gdc = df.groupby(["driver_id", "circuit_id"], sort=False)
    df["driver_circuit_avg"] = gdc["finish_pos_clean"].transform(
        lambda s: _shifted_expanding_mean(s)
    )

    # Driver overall expanding (cross-season)
    gd = df.groupby("driver_id", sort=False)
    df["driver_overall_avg"] = gd["finish_pos_clean"].transform(
        lambda s: _shifted_expanding_mean(s)
    )

    # ---- Binary features from quali ----
    df["is_pole_position"] = (df["quali_position"] == 1).astype(int)
    df["is_front_row"] = (df["quali_position"] <= 2).astype(int)
    df["is_top10_quali"] = (df["quali_position"] <= 10).astype(int)
    df["grid_advantage"] = 1.0 / (df["grid"] + 0.5)

    # ---- Track interaction features (need per-row track lookup) ----
    # We'll apply track features in Step 7; here compute the interaction terms
    # using placeholders that will be filled after track features are added.
    # For now, store grid_importance_factor placeholder.

    # ---- Form features (shifted, cross-season per driver) ----
    is_win = (df["finish_position"] == 1).astype(float)
    is_podium = (df["finish_position"] <= 3).astype(float)
    is_points_finish = (df["finish_position"] <= 10).astype(float)

    df["recent_wins"] = gd["finish_position"].transform(
        lambda s: (s == 1).astype(float).shift(1).rolling(10, min_periods=1).mean()
    )
    df["recent_podiums"] = gd["finish_position"].transform(
        lambda s: (s <= 3).astype(float).shift(1).rolling(10, min_periods=1).mean()
    )
    df["recent_points_rate"] = gd["finish_position"].transform(
        lambda s: (s <= 10).astype(float).shift(1).rolling(10, min_periods=1).mean()
    )

    df["recent_form_weighted"] = 0.9 * df["roll_finishpos_3"] + 0.1 * df["roll_finishpos_5"]
    df["hot_streak"] = (df["roll_finishpos_3"] < 3).astype(int)
    df["dominant_form"] = (df["roll_finishpos_3"] < 1.5).astype(int)

    # ---- Team recent form (constructor-level rolling 5-race, shifted) ----
    df_sorted_c2 = df.sort_values(["constructor_id", "season", "round"]).reset_index(drop=True)
    gc2 = df_sorted_c2.groupby("constructor_id", sort=False)
    df_sorted_c2["team_recent_form"] = gc2["finish_pos_clean"].transform(
        lambda s: _shifted_rolling(s, 5)
    )
    df["team_recent_form"] = df_sorted_c2.sort_values(
        ["driver_id", "season", "round"]
    )["team_recent_form"].values

    # ---- Race vs. quali advantage (rolling 8-race mean of quali_pos - finish_pos) ----
    df["quali_minus_finish"] = df["quali_position"] - df["finish_position"]
    gd3 = df.groupby("driver_id", sort=False)
    df["race_vs_quali_advantage"] = gd3["quali_minus_finish"].transform(
        lambda s: _shifted_rolling(s, 8)
    )

    # ---- Teammate gap: driver's rolling-3 finish vs team mean rolling-3 finish ----
    team_roll3_mean = (
        df.groupby(["constructor_id", "season", "round"])["roll_finishpos_3"]
        .mean()
        .reset_index()
        .rename(columns={"roll_finishpos_3": "team_mean_roll_finishpos_3"})
    )
    df = df.merge(team_roll3_mean, on=["constructor_id", "season", "round"], how="left")
    df["teammate_gap"] = df["roll_finishpos_3"] - df["team_mean_roll_finishpos_3"]

    # ---- Form trend ----
    df["form_trend"] = df["roll_finishpos_3"] - df["roll_finishpos_5"]

    # ---- Grid penalty ----
    df["grid_penalty"] = (df["grid"] - df["quali_position"]).clip(lower=0)

    # ---- Season progress ----
    max_rounds = df.groupby("season")["round"].transform("max")
    df["season_progress"] = df["round"] / max_rounds

    # Drop intermediates
    df.drop(columns=["quali_minus_finish", "team_mean_roll_finishpos_3"],
            inplace=True, errors="ignore")

    return df


# ============================================================================
# Step 7: Track features and expert ratings
# ============================================================================

def add_track_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add track classification features based on circuit_id."""
    track_feat_rows = df["circuit_id"].apply(
        lambda cid: pd.Series(get_track_features(str(cid)))
    )
    for col in TRACK_FEATURE_NAMES:
        df[col] = track_feat_rows[col].values
    return df


def add_track_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute interaction features between grid position and track characteristics."""
    df["grid_importance_factor"] = df["overtaking_difficulty"] / 10.0
    df["pole_advantage"] = df["is_pole_position"] * (1 + 2 * df["grid_importance_factor"])
    df["front_row_advantage"] = df["is_front_row"] * (0.5 + 1 * df["grid_importance_factor"])

    # Strategy & safety car interaction
    df["strategy_sc_advantage"] = (
        df["team_strategy_rating"] * df["safety_car_probability"] / 10.0
    )
    df["top10_sc_interaction"] = df["is_top10_quali"] * df["safety_car_probability"]
    df["top10_turn1_interaction"] = df["is_top10_quali"] * df["turn1_incident_risk"]
    df["top10_street_interaction"] = df["is_top10_quali"] * df["is_street"]

    return df


def add_expert_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """Add manual expert ratings for teams and drivers."""
    df["team_strategy_rating"] = df["constructor_id"].apply(get_team_strategy_rating)
    df["team_adaptability"] = df["constructor_id"].apply(get_team_adaptability)
    df["driver_tire_mgmt"] = df["driver_id"].apply(get_driver_tire_mgmt)
    df["driver_overtaking"] = df["driver_id"].apply(get_driver_overtaking)
    df["driver_quali_skill"] = df["driver_id"].apply(get_driver_quali_skill)
    return df


# ============================================================================
# Step 8: Save output
# ============================================================================

def save_model_rows(df: pd.DataFrame) -> None:
    """Save per-season parquet files and a combined all_model_rows.parquet."""
    JOLPICA_MODEL_ROWS_DIR.mkdir(parents=True, exist_ok=True)

    for year in df["season"].unique():
        year_df = df[df["season"] == year].copy()
        out_path = JOLPICA_MODEL_ROWS_DIR / f"model_rows_{int(year)}.parquet"
        year_df.to_parquet(out_path, index=False)
        print(f"  Saved {len(year_df):,} rows -> {out_path}")

    all_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    df.to_parquet(all_path, index=False)
    print(f"  Saved combined {len(df):,} rows -> {all_path}")


# ============================================================================
# Main pipeline
# ============================================================================

def build_jolpica_features() -> pd.DataFrame:
    """Run the full feature-building pipeline and return the final DataFrame."""
    print("=" * 70)
    print("03b — Build Jolpica Rolling Features")
    print("=" * 70)

    # Step 1: Load & merge
    print("\n[Step 1] Loading and merging all season CSVs ...")
    df = load_all_seasons()

    # Step 2: Status flags
    print("[Step 2] Computing status flags and DNF classification ...")
    df = compute_status_flags(df)
    print(f"  DNF rate: {df['is_dnf'].mean():.1%}  |  "
          f"Mechanical: {df['dnf_mechanical'].mean():.1%}  |  "
          f"Collision: {df['dnf_collision'].mean():.1%}")

    # Step 3: Driver rolling features
    print("[Step 3] Computing driver rolling features ...")
    df = compute_driver_rolling_features(df)

    # Step 4: Constructor rolling features
    print("[Step 4] Computing constructor rolling features ...")
    df = compute_constructor_rolling_features(df)

    # Step 5: Qualifying priors
    print("[Step 5] Computing qualifying priors ...")
    df = compute_qualifying_priors(df)

    # Step 7 (before 6): Add expert ratings first (needed for interactions)
    print("[Step 7a] Adding expert ratings ...")
    df = add_expert_ratings(df)

    # Step 7b: Track features
    print("[Step 7b] Adding track classification features ...")
    df = add_track_features(df)

    # Step 6: Race-derived features (needs rolling features from steps 3-4)
    print("[Step 6] Computing race-derived features ...")
    df = compute_race_derived_features(df)

    # Step 7c: Track interaction features (needs both track features and step 6 outputs)
    print("[Step 7c] Computing track interaction features ...")
    df = add_track_interaction_features(df)

    # Final sort
    df = df.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)

    # Summary
    feature_cols = [c for c in df.columns if c not in (
        "season", "round", "driver_id", "constructor_id", "circuit_id",
        "race_name", "race_date", "status",
    )]
    print(f"\n  Total features: {len(feature_cols)}")
    print(f"  Total rows: {len(df):,}")
    print(f"  NaN summary (top 10):")
    nan_counts = df[feature_cols].isna().sum().sort_values(ascending=False).head(10)
    for col_name, cnt in nan_counts.items():
        if cnt > 0:
            print(f"    {col_name}: {cnt:,} ({cnt / len(df):.1%})")

    # Step 8: Save
    print("\n[Step 8] Saving model rows ...")
    save_model_rows(df)

    print("\nDone.")
    return df


if __name__ == "__main__":
    build_jolpica_features()
