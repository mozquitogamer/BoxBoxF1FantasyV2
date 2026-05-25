"""
03b_build_jolpica_features.py — Jolpica historical feature builder.

Reads normalized Jolpica CSVs (from 03a), computes time-safe rolling features
per driver/constructor, and outputs model_rows parquet files.

Usage:
    python pipeline/03b_build_jolpica_features.py --year 2022
    python pipeline/03b_build_jolpica_features.py --all

All rolling/shifted features are TIME-SAFE: they use shift(1) before rolling
so the model never sees current-round data when making predictions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    JOLPICA_NORMALIZED_DIR,
    JOLPICA_MODEL_ROWS_DIR,
    HISTORICAL_SEASONS,
    CURRENT_SEASON,
    SEED_DIR,
)
from config.track_classifications import get_track_features, TRACK_FEATURE_NAMES
from config.track_similarity import get_similarity
from config.team_driver_ratings import (
    get_team_strategy_rating,
    get_team_adaptability,
    get_driver_tire_mgmt,
    get_driver_wet_skill,
    get_driver_overtaking,
    get_driver_quali_skill,
    get_constructor_cold_skill,
)

# All seasons to load for cross-season rolling features
ALL_SEASONS = sorted(set(HISTORICAL_SEASONS + [CURRENT_SEASON]))


# ============================================================================
# Helpers
# ============================================================================

def ensure_int(s: pd.Series) -> pd.Series:
    """Best-effort numeric conversion to Int64 (nullable)."""
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def load_constructor_canonical_map() -> dict[str, str]:
    """
    Build a mapping from legacy constructor IDs to canonical 2026 IDs
    using data/seed/driver_ids.json constructor_mappings.
    """
    path = SEED_DIR / "driver_ids.json"
    if not path.exists():
        print(f"[WARN] Missing {path}, constructor canonicalization skipped.")
        return {}

    obj = json.loads(path.read_text(encoding="utf-8"))
    mappings = obj.get("constructor_mappings", [])

    canon_map: dict[str, str] = {}
    for entry in mappings:
        canonical_id = entry["id"]
        # Map the jolpica ID if it differs from canonical
        jolpica_id = entry.get("jolpica", "")
        if jolpica_id and jolpica_id != canonical_id:
            canon_map[jolpica_id] = canonical_id
        # Map all ergast_alt IDs
        for alt in entry.get("ergast_alt", []):
            if alt and alt != canonical_id:
                canon_map[alt] = canonical_id

    return canon_map


def canonicalize_constructor(series: pd.Series, canon_map: dict[str, str]) -> pd.Series:
    """Apply constructor ID canonicalization."""
    s = series.astype(str).str.strip().str.lower()
    mapped = s.map(lambda x: canon_map.get(x, x))
    changed = (s != mapped).sum()
    if changed > 0:
        print(f"  [INFO] Canonicalized {changed} constructor_id values.")
    return mapped


# ============================================================================
# Group 1: Status flags & DNF cause buckets
# ============================================================================

def status_flags(status: pd.Series) -> pd.DataFrame:
    """
    FIA-style classification flags from status strings.
    DNS (did not start) is tracked separately from DNF.
    """
    st = status.fillna("").astype(str)
    st_lower = st.str.lower()

    is_dsq = st.str.contains("disqualified", case=False, regex=False)
    is_dns = st_lower.eq("dns") | st_lower.str.contains("did not start", regex=False)

    is_finished = st_lower.eq("finished")
    is_lapped = st_lower.eq("lapped")
    is_time_gap = st.str.startswith("+")
    is_classified = is_finished | is_lapped | is_time_gap

    is_dnf = (~is_classified) & (~is_dsq) & (~is_dns)

    return pd.DataFrame({
        "is_classified": is_classified.astype(int),
        "is_dnf": is_dnf.astype(int),
        "is_dns": is_dns.astype(int),
        "is_dsq": is_dsq.astype(int),
    })


def dnf_cause_bucket(status: pd.Series, is_dnf: pd.Series, is_dsq: pd.Series) -> pd.Series:
    """Categorize DNF causes into buckets: mechanical, collision, driver_error, penalty_admin, other, none."""
    st = status.fillna("").astype(str).str.lower()

    admin = st.str.contains(
        "disqualified|black flag|excluded|did not start|dns|did not qualify|dnq",
        regex=True,
    )
    mechanical = st.str.contains(
        "engine|gearbox|power unit|electrical|hydraulic|oil|fuel|cooling|"
        "water|battery|turbo|driveshaft|transmission|mechanical|brakes|"
        "clutch|suspension|puncture|tyre|tire",
        regex=True,
    )
    collision = st.str.contains(
        "collision|crash|accident|damage|contact|spun|spin|unsafe release|hit",
        regex=True,
    )
    driver_error = st.str.contains(
        "spun|spin|lost control|driver error",
        regex=True,
    )

    out = pd.Series(["none"] * len(st), index=st.index, dtype="object")

    is_dnf_bool = is_dnf.astype(bool)
    is_dsq_bool = is_dsq.astype(bool)

    out.loc[is_dsq_bool | admin] = "penalty_admin"
    out.loc[is_dnf_bool & mechanical & ~is_dsq_bool] = "mechanical"
    out.loc[is_dnf_bool & collision & ~is_dsq_bool] = "collision"
    out.loc[is_dnf_bool & driver_error & ~is_dsq_bool] = "driver_error"
    out.loc[is_dnf_bool & (out == "none") & ~is_dsq_bool] = "other"

    return out


# ============================================================================
# Group 2: Rolling features (time-safe via shift(1))
# ============================================================================

def add_rolling_rates(df: pd.DataFrame, group_col: str, flag_col: str,
                      window: int, out_col: str) -> pd.DataFrame:
    """Compute time-safe rolling rate: shift(1) then rolling mean."""
    prev = df.groupby(group_col)[flag_col].shift(1)
    df[out_col] = (
        prev.groupby(df[group_col])
        .rolling(window, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return df


def compute_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute basic rolling features for points, finish position, quali position, and DNF rate.
    All use shift(1) before rolling to ensure time safety.
    """
    df = df.copy()

    # Shift values by 1 within each driver's history
    df["points_prev"] = df.groupby("driver_id")["points"].shift(1)
    df["finish_prev"] = df.groupby("driver_id")["finish_position"].shift(1)
    df["quali_prev"] = df.groupby("driver_id")["quali_position"].shift(1)
    df["dnf_prev"] = df.groupby("driver_id")["is_dnf"].shift(1)

    for w in (3, 5):
        df[f"roll_points_{w}"] = (
            df.groupby("driver_id")["points_prev"]
            .rolling(w, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        df[f"roll_finishpos_{w}"] = (
            df.groupby("driver_id")["finish_prev"]
            .rolling(w, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        df[f"roll_quali_{w}"] = (
            df.groupby("driver_id")["quali_prev"]
            .rolling(w, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    df["roll_dnf_rate_5"] = (
        df.groupby("driver_id")["dnf_prev"]
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df.drop(columns=["points_prev", "finish_prev", "quali_prev", "dnf_prev"], inplace=True)
    return df


# ============================================================================
# Group 2b: Track-similarity-weighted rolling features (time-safe)
# ============================================================================

def compute_similarity_weighted_rolling(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Compute rolling features where each historical race is weighted by how
    similar its circuit is to the current race's circuit.

    For each row (driver, season, round, circuit_id):
      - Look back at the driver's previous `window` races (time-safe via shift)
      - Weight each by cosine similarity between its circuit and the target circuit
      - Compute weighted averages of points, finish_position, and quali_position

    Produces 6 new features:
      - sim_weighted_points_{window}, sim_weighted_finishpos_{window},
        sim_weighted_quali_{window}
      - sim_weighted_points_3, sim_weighted_finishpos_3, sim_weighted_quali_3

    Falls back to unweighted average when all similarities are near-zero
    (which shouldn't happen since all tracks have positive feature values).
    """
    df = df.copy()

    # Pre-sort by driver + time order
    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)

    # Prepare shifted values (time-safe: we weight PREVIOUS results)
    df["_pts_prev"] = df.groupby("driver_id")["points"].shift(1)
    df["_fin_prev"] = df.groupby("driver_id")["finish_position"].shift(1)
    df["_qua_prev"] = df.groupby("driver_id")["quali_position"].shift(1)
    df["_cir_prev"] = df.groupby("driver_id")["circuit_id"].shift(1)

    # Pre-compute similarity cache for all circuit pairs in the data
    unique_circuits = df["circuit_id"].dropna().unique().tolist()
    sim_cache: dict[tuple[str, str], float] = {}
    for c1 in unique_circuits:
        for c2 in unique_circuits:
            key = (c1, c2)
            if key not in sim_cache:
                sim_cache[key] = get_similarity(c1, c2)

    # Output columns
    for w in (3, window):
        df[f"sim_weighted_points_{w}"] = np.nan
        df[f"sim_weighted_finishpos_{w}"] = np.nan
        df[f"sim_weighted_quali_{w}"] = np.nan

    # Group by driver and compute weighted rolling
    for driver_id, group in df.groupby("driver_id"):
        idx = group.index.tolist()
        circuits = group["circuit_id"].values
        pts = group["_pts_prev"].values
        fin = group["_fin_prev"].values
        qua = group["_qua_prev"].values
        cir = group["_cir_prev"].values

        for i_local, i_global in enumerate(idx):
            target_circuit = str(circuits[i_local])

            for w in (3, window):
                # Look back at the last `w` shifted values
                start = max(0, i_local - w + 1)
                slice_pts = pts[start:i_local + 1]
                slice_fin = fin[start:i_local + 1]
                slice_qua = qua[start:i_local + 1]
                slice_cir = cir[start:i_local + 1]

                # Compute weights from similarity
                weights = []
                valid_pts, valid_fin, valid_qua = [], [], []
                for j in range(len(slice_pts)):
                    p, f, q, c = slice_pts[j], slice_fin[j], slice_qua[j], slice_cir[j]
                    if pd.isna(p) and pd.isna(f) and pd.isna(q):
                        continue
                    c_str = str(c) if pd.notna(c) else "unknown"
                    sim = sim_cache.get((target_circuit, c_str), get_similarity(target_circuit, c_str))
                    # Raise similarity to power 2 to sharpen contrast
                    weight = sim * sim
                    weights.append(weight)
                    valid_pts.append(p if pd.notna(p) else np.nan)
                    valid_fin.append(f if pd.notna(f) else np.nan)
                    valid_qua.append(q if pd.notna(q) else np.nan)

                if not weights:
                    continue

                w_sum = sum(weights)
                if w_sum < 1e-9:
                    # All weights ~0 (shouldn't happen), fall back to uniform
                    w_sum = len(weights)
                    weights = [1.0] * len(weights)

                # Weighted average for points (skip NaN entries, matches finish/quali
                # treatment). Previously NaN points were coerced to 0.0 which biased the
                # average downward for drivers whose similar-track history included
                # unclassified / missed-race rows.
                pts_pairs = [(wt, v) for wt, v in zip(weights, valid_pts) if pd.notna(v)]
                if pts_pairs:
                    ws, vs = zip(*pts_pairs)
                    df.at[i_global, f"sim_weighted_points_{w}"] = sum(
                        w_ * v_ for w_, v_ in zip(ws, vs)
                    ) / sum(ws)

                # Weighted average for finish (skip NaN entries)
                fin_pairs = [(wt, v) for wt, v in zip(weights, valid_fin) if pd.notna(v)]
                if fin_pairs:
                    ws, vs = zip(*fin_pairs)
                    df.at[i_global, f"sim_weighted_finishpos_{w}"] = sum(
                        w_ * v_ for w_, v_ in zip(ws, vs)
                    ) / sum(ws)

                # Weighted average for quali (skip NaN entries)
                qua_pairs = [(wt, v) for wt, v in zip(weights, valid_qua)]
                qua_pairs = [(wt, v) for wt, v in qua_pairs if pd.notna(v)]
                if qua_pairs:
                    ws, vs = zip(*qua_pairs)
                    df.at[i_global, f"sim_weighted_quali_{w}"] = sum(
                        w_ * v_ for w_, v_ in zip(ws, vs)
                    ) / sum(ws)

    # Clean up temp columns
    df.drop(columns=["_pts_prev", "_fin_prev", "_qua_prev", "_cir_prev"], inplace=True)
    return df


# ============================================================================
# Group 3: Quali priors (time-safe)
# ============================================================================

def _teammate_value(series: pd.Series) -> pd.Series:
    """
    For each driver in a (season, round, constructor_id) group,
    return the median quali of the OTHER driver(s) on the team.
    """
    vals = series.astype(float)
    idx = vals.index
    arr = vals.to_numpy(dtype=float)

    out = np.full(len(arr), np.nan, dtype=float)
    for i in range(len(arr)):
        others = np.delete(arr, i)
        others = others[np.isfinite(others)]
        if len(others) > 0:
            out[i] = float(np.median(others))
    return pd.Series(out, index=idx, dtype=float)


def add_quali_priors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all qualifying prior features using only information
    available BEFORE the current weekend (shift-based time safety).
    """
    d = df.copy()

    # --- Driver priors (shifted) ---
    d = d.sort_values(["driver_id", "season", "round"])
    d["driver_quali_prev"] = d.groupby("driver_id")["quali_position"].shift(1)

    d["driver_quali_last"] = d["driver_quali_prev"]
    d["driver_roll_quali_3"] = d.groupby("driver_id")["driver_quali_prev"].transform(
        lambda x: x.rolling(3, min_periods=1).mean()
    )
    d["driver_roll_quali_5"] = d.groupby("driver_id")["driver_quali_prev"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )
    d["driver_season_avg_quali"] = d.groupby(["driver_id", "season"])["driver_quali_prev"].transform(
        lambda x: x.expanding(min_periods=1).mean()
    )
    d["driver_season_med_quali"] = d.groupby(["driver_id", "season"])["driver_quali_prev"].transform(
        lambda x: x.expanding(min_periods=1).median()
    )

    # --- Constructor priors (shifted) ---
    d = d.sort_values(["constructor_id", "season", "round", "driver_id"])
    d["constructor_quali_prev"] = d.groupby("constructor_id")["quali_position"].shift(1)

    d["constructor_quali_last"] = d["constructor_quali_prev"]
    d["constructor_roll_quali_3"] = d.groupby("constructor_id")["constructor_quali_prev"].transform(
        lambda x: x.rolling(3, min_periods=1).mean()
    )
    d["constructor_roll_quali_5"] = d.groupby("constructor_id")["constructor_quali_prev"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )
    d["constructor_season_avg_quali"] = d.groupby(["constructor_id", "season"])["constructor_quali_prev"].transform(
        lambda x: x.expanding(min_periods=1).mean()
    )

    # --- Field baseline (shifted) ---
    d = d.sort_values(["season", "round", "driver_id"])
    d["field_prev"] = d.groupby("season")["quali_position"].shift(1)
    d["field_season_avg_quali"] = d.groupby("season")["field_prev"].transform(
        lambda x: x.expanding(min_periods=1).mean()
    )

    d["driver_vs_field_season"] = d["driver_season_avg_quali"] - d["field_season_avg_quali"]
    d["constructor_vs_field_season"] = d["constructor_season_avg_quali"] - d["field_season_avg_quali"]

    # --- Teammate-relative priors (time-safe) ---
    d = d.sort_values(["season", "round", "constructor_id", "driver_id"])
    d["teammate_quali_this"] = d.groupby(["season", "round", "constructor_id"])["quali_position"].transform(
        _teammate_value
    )
    d["team_delta_this"] = d["quali_position"] - d["teammate_quali_this"]

    # Shift deltas by driver so they are time-safe
    d = d.sort_values(["driver_id", "season", "round"])
    d["team_delta_last"] = d.groupby("driver_id")["team_delta_this"].shift(1)
    d["team_delta_roll_3"] = d.groupby("driver_id")["team_delta_last"].transform(
        lambda x: x.rolling(3, min_periods=1).mean()
    )
    d["team_delta_roll_5"] = d.groupby("driver_id")["team_delta_last"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )

    # --- Circuit priors (time-safe, shifted) ---
    d = d.sort_values(["driver_id", "circuit_id", "season", "round"])
    d["driver_circuit_prev"] = d.groupby(["driver_id", "circuit_id"])["quali_position"].shift(1)
    d["driver_circuit_exp"] = d.groupby(["driver_id", "circuit_id"])["driver_circuit_prev"].transform(
        lambda x: x.expanding(min_periods=1).mean()
    )
    d["driver_circuit_roll_3"] = d.groupby(["driver_id", "circuit_id"])["driver_circuit_prev"].transform(
        lambda x: x.rolling(3, min_periods=1).mean()
    )

    d = d.sort_values(["constructor_id", "circuit_id", "season", "round", "driver_id"])
    d["constructor_circuit_prev"] = d.groupby(["constructor_id", "circuit_id"])["quali_position"].shift(1)
    d["constructor_circuit_exp"] = d.groupby(["constructor_id", "circuit_id"])["constructor_circuit_prev"].transform(
        lambda x: x.expanding(min_periods=1).mean()
    )

    # Clean up intermediate columns
    d.drop(columns=[
        "driver_quali_prev", "constructor_quali_prev", "field_prev",
        "teammate_quali_this", "team_delta_this",
        "driver_circuit_prev", "constructor_circuit_prev",
    ], inplace=True)

    return d


# ============================================================================
# Group 4: Race model features (derived from existing columns)
# ============================================================================

def add_race_model_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute race-oriented derived features.
    Quali-based features are known at prediction time (qualifying happens before the race).
    Rolling form features use shift(1) for time safety.
    """
    d = df.copy()

    # --- Current-round quali-based features (known at prediction time) ---
    quali_pos = d["quali_position"].astype(float)
    d["is_pole_position"] = (quali_pos == 1).astype(int)
    d["is_front_row"] = (quali_pos <= 2).astype(int)
    d["is_top10_quali"] = (quali_pos <= 10).astype(int)
    d["grid_advantage"] = 11.0 - quali_pos  # positive = better than field avg (~11)

    # --- Position delta from previous races (shifted for time safety) ---
    d = d.sort_values(["driver_id", "season", "round"])
    d["_pos_delta_raw"] = (
        d["grid"].astype(float) - d["finish_position"].astype(float)
    ).replace([np.inf, -np.inf], np.nan)
    d["position_delta_prev"] = d.groupby("driver_id")["_pos_delta_raw"].shift(1)

    # --- Rolling form features (shifted for time safety) ---
    # Recent wins: count of P1 finishes in last 5 races (shifted)
    d["_is_win"] = (d["finish_position"] == 1).astype(float)
    d["_is_win_prev"] = d.groupby("driver_id")["_is_win"].shift(1)
    d["recent_wins"] = (
        d.groupby("driver_id")["_is_win_prev"]
        .rolling(5, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    # Recent podiums: count of P1-P3 in last 5 (shifted)
    d["_is_podium"] = (d["finish_position"].astype(float) <= 3).astype(float)
    d["_is_podium_prev"] = d.groupby("driver_id")["_is_podium"].shift(1)
    d["recent_podiums"] = (
        d.groupby("driver_id")["_is_podium_prev"]
        .rolling(5, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    # Recent points rate: fraction of last 5 with points finish (shifted)
    d["_has_points"] = (d["points"].astype(float) > 0).astype(float)
    d["_has_points_prev"] = d.groupby("driver_id")["_has_points"].shift(1)
    d["recent_points_rate"] = (
        d.groupby("driver_id")["_has_points_prev"]
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Recent form weighted: exponentially weighted recent finish positions (shifted)
    d["_finish_prev"] = d.groupby("driver_id")["finish_position"].shift(1).astype(float)
    d["recent_form_weighted"] = (
        d.groupby("driver_id")["_finish_prev"]
        .transform(lambda x: x.ewm(span=5, min_periods=1).mean())
    )

    # Form trend: roll_3 - roll_5 (positive = improving, uses already-computed rolling features)
    d["form_trend"] = d["roll_finishpos_3"] - d["roll_finishpos_5"]

    # Team recent form: constructor rolling avg finish (shifted)
    d = d.sort_values(["constructor_id", "season", "round", "driver_id"])
    d["_constructor_finish_prev"] = d.groupby("constructor_id")["finish_position"].shift(1).astype(float)
    d["team_recent_form"] = (
        d.groupby("constructor_id")["_constructor_finish_prev"]
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Season progress
    max_rounds = d.groupby("season")["round"].transform("max").astype(float)
    d["season_progress"] = d["round"].astype(float) / max_rounds

    # Clean up intermediate columns
    temp_cols = [c for c in d.columns if c.startswith("_")]
    d.drop(columns=temp_cols, inplace=True)

    return d


# ============================================================================
# Group 5: Track features + team/driver ratings lookup
# ============================================================================

def add_track_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add 9 track classification features based on circuit_id."""
    records = []
    for cid in df["circuit_id"]:
        features = get_track_features(str(cid))
        records.append(features)

    track_df = pd.DataFrame(records, index=df.index)
    return pd.concat([df, track_df], axis=1)


def add_team_driver_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Look up team strategy/adaptability ratings and driver skill ratings.
    Driver ratings use Jolpica-style driver IDs (e.g., "max_verstappen").
    Constructor ratings use the canonical constructor_id.
    """
    d = df.copy()

    # Team ratings via canonical constructor_id
    d["strategy_rating"] = d["constructor_id"].map(get_team_strategy_rating)
    d["adaptability"] = d["constructor_id"].map(get_team_adaptability)
    # Per-constructor cold-weather rating (used in interaction with weather
    # features at training time, and as an MC perturbation when forecast is cold).
    d["cold_skill"] = d["constructor_id"].map(get_constructor_cold_skill)

    # Driver ratings via jolpica driver_id
    d["tire_mgmt"] = d["driver_id"].map(get_driver_tire_mgmt)
    d["wet_skill"] = d["driver_id"].map(get_driver_wet_skill)
    d["overtaking"] = d["driver_id"].map(get_driver_overtaking)
    d["quali_skill"] = d["driver_id"].map(get_driver_quali_skill)

    return d


# ============================================================================
# Group 6: Interaction features
# ============================================================================

def add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute interaction features between ratings and track characteristics."""
    d = df.copy()
    d["strategy_sc_advantage"] = d["strategy_rating"] * d["safety_car_probability"]
    d["quali_skill_x_ot_diff"] = d["quali_skill"] * d["overtaking_difficulty"]
    return d


# ============================================================================
# Data loading
# ============================================================================

def load_all_normalized_data() -> pd.DataFrame:
    """
    Load race_results, qualifying_results, and sprint_results for ALL available
    seasons. Merge into a single DataFrame with one row per (season, round, driver).
    """
    all_parts = []

    for year in ALL_SEASONS:
        year_dir = JOLPICA_NORMALIZED_DIR / str(year)

        # Race results (required)
        race_path = year_dir / "race_results.csv"
        if not race_path.exists():
            print(f"  [SKIP] No race_results for {year}")
            continue

        results = pd.read_csv(race_path)

        # Qualifying results
        quali_path = year_dir / "qualifying_results.csv"
        quali = pd.read_csv(quali_path) if quali_path.exists() else pd.DataFrame()

        # Races metadata (circuit_id, has_sprint)
        races_path = year_dir / "races.csv"
        races = pd.read_csv(races_path) if races_path.exists() else pd.DataFrame()

        # Sprint results
        sprint_path = year_dir / "sprint_results.csv"
        sprint = pd.read_csv(sprint_path) if sprint_path.exists() else pd.DataFrame()

        # Ensure integer types for season/round
        for d in [results, quali, races, sprint]:
            if d.empty:
                continue
            if "season" in d.columns:
                d["season"] = ensure_int(d["season"])
            if "round" in d.columns:
                d["round"] = ensure_int(d["round"])

        # Ensure numeric types in results
        if "grid" in results.columns:
            results["grid"] = ensure_int(results["grid"])
        if "finish_position" in results.columns:
            results["finish_position"] = ensure_int(results["finish_position"])
        if "points" in results.columns:
            results["points"] = pd.to_numeric(results["points"], errors="coerce").fillna(0.0)
        if "laps_completed" in results.columns:
            results["laps_completed"] = ensure_int(results["laps_completed"])
        if "quali_position" in results.columns:
            results["quali_position"] = ensure_int(results["quali_position"])

        if not quali.empty and "quali_position" in quali.columns:
            quali["quali_position"] = ensure_int(quali["quali_position"])

        # Select columns for merge
        result_cols = ["season", "round", "driver_id", "constructor_id",
                       "grid", "finish_position", "position_text", "points",
                       "status", "laps_completed"]
        if "quali_position" in results.columns:
            result_cols.append("quali_position")

        results_small = results[[c for c in result_cols if c in results.columns]].copy()

        # Merge qualifying data
        keys = ["season", "round", "driver_id"]
        if not quali.empty:
            quali_cols = ["season", "round", "driver_id", "quali_position", "q1", "q2", "q3"]
            quali_small = quali[[c for c in quali_cols if c in quali.columns]].copy()

            if "quali_position" in results_small.columns:
                # Already have quali_position in results; merge for q1/q2/q3 only
                quali_extra = quali_small.drop(columns=["quali_position"], errors="ignore")
                df_year = results_small.merge(quali_extra, on=keys, how="left")
            else:
                df_year = results_small.merge(quali_small, on=keys, how="outer")
        else:
            df_year = results_small.copy()

        # Merge race metadata for circuit_id and has_sprint
        if not races.empty:
            race_cols = ["season", "round", "circuit_id", "has_sprint"]
            races_small = races[[c for c in race_cols if c in races.columns]].copy()
            df_year = df_year.merge(races_small, on=["season", "round"], how="left")

        # Merge sprint results
        if not sprint.empty:
            if "sprint_position" in sprint.columns:
                sprint["sprint_position"] = ensure_int(sprint["sprint_position"])
            if "sprint_points" not in sprint.columns and "points" in sprint.columns:
                sprint["sprint_points"] = pd.to_numeric(sprint["points"], errors="coerce").fillna(0.0)
            elif "sprint_points" in sprint.columns:
                sprint["sprint_points"] = pd.to_numeric(sprint["sprint_points"], errors="coerce").fillna(0.0)

            sprint_merge_cols = ["season", "round", "driver_id"]
            if "sprint_position" in sprint.columns:
                sprint_merge_cols.append("sprint_position")
            if "sprint_points" in sprint.columns:
                sprint_merge_cols.append("sprint_points")
            # Include sprint grid (from sprint qualifying/shootout) — critical feature
            if "grid" in sprint.columns:
                sprint["sprint_grid"] = ensure_int(sprint["grid"])
                sprint_merge_cols.append("sprint_grid")

            sprint_small = sprint[[c for c in sprint_merge_cols if c in sprint.columns]].copy()
            df_year = df_year.merge(sprint_small, on=["season", "round", "driver_id"], how="left")

        all_parts.append(df_year)

    if not all_parts:
        raise FileNotFoundError("No normalized data found for any season.")

    df = pd.concat(all_parts, ignore_index=True)

    # Fill missing sprint columns
    if "sprint_position" not in df.columns:
        df["sprint_position"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    if "sprint_points" not in df.columns:
        df["sprint_points"] = 0.0
    else:
        df["sprint_points"] = df["sprint_points"].fillna(0.0)

    if "has_sprint" not in df.columns:
        df["has_sprint"] = False
    else:
        df["has_sprint"] = df["has_sprint"].fillna(False).astype(bool)

    if "circuit_id" not in df.columns:
        df["circuit_id"] = "unknown"
    else:
        df["circuit_id"] = df["circuit_id"].fillna("unknown").astype(str).str.lower().str.strip()

    # Fill grid from quali_position if missing
    if "grid" in df.columns and "quali_position" in df.columns:
        df["grid"] = df["grid"].combine_first(df["quali_position"])

    # Handle DNS rows: present in quali but missing race finish
    if "quali_position" in df.columns and "finish_position" in df.columns:
        dns_mask = df["quali_position"].notna() & df["finish_position"].isna()
        df.loc[dns_mask, "points"] = 0.0
        df.loc[dns_mask, "laps_completed"] = 0
        if "status" in df.columns:
            df.loc[dns_mask & df["status"].isna(), "status"] = "DNS"
        if "position_text" in df.columns:
            df.loc[dns_mask & df["position_text"].isna(), "position_text"] = "DNS"

    return df


# ============================================================================
# Main pipeline
# ============================================================================

def build_features(target_years: list[int]) -> None:
    """
    Build model_rows parquet files for the specified years.
    Loads ALL seasons' data for cross-season rolling continuity,
    then saves per-year outputs.
    """
    print("=" * 70)
    print("03b_build_jolpica_features — Jolpica Historical Feature Builder")
    print("=" * 70)

    # --- Load constructor canonical mapping ---
    constructor_map = load_constructor_canonical_map()
    print(f"\n[1/9] Loaded constructor mappings: {len(constructor_map)} aliases")

    # --- Load all normalized data ---
    print(f"\n[2/9] Loading normalized data for seasons {ALL_SEASONS[0]}-{ALL_SEASONS[-1]}...")
    df = load_all_normalized_data()
    print(f"  Loaded {len(df):,} rows across {df['season'].nunique()} seasons")

    # --- Canonicalize constructor IDs ---
    print(f"\n[3/9] Canonicalizing constructor IDs...")
    df["constructor_id"] = canonicalize_constructor(df["constructor_id"], constructor_map)

    # Normalize driver_id
    df["driver_id"] = df["driver_id"].astype(str).str.strip().str.lower()

    # Ensure numeric types for feature computation
    df["quali_position"] = pd.to_numeric(df["quali_position"], errors="coerce").astype(float)
    df["finish_position"] = pd.to_numeric(df["finish_position"], errors="coerce")
    df["grid"] = pd.to_numeric(df["grid"], errors="coerce")
    df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0.0)

    # --- Status flags and DNF cause buckets ---
    print(f"\n[4/9] Computing status flags and DNF cause buckets...")
    flags = status_flags(df["status"])
    df = pd.concat([df.reset_index(drop=True), flags.reset_index(drop=True)], axis=1)

    df["dnf_cause"] = dnf_cause_bucket(df["status"], df["is_dnf"], df["is_dsq"])
    df["dnf_mechanical"] = ((df["dnf_cause"] == "mechanical") & (df["is_dnf"] == 1)).astype(int)
    df["dnf_collision"] = ((df["dnf_cause"] == "collision") & (df["is_dnf"] == 1)).astype(int)
    df["dnf_driver_error"] = ((df["dnf_cause"] == "driver_error") & (df["is_dnf"] == 1)).astype(int)

    # --- Sort globally for rolling features across season boundaries ---
    df = df.sort_values(["driver_id", "season", "round"]).reset_index(drop=True)

    # --- Rolling features (Group 2) ---
    print(f"\n[5/9] Computing rolling features (time-safe)...")
    df = compute_rolling_features(df)

    # DNF cause rolling rates
    df = add_rolling_rates(df, "driver_id", "dnf_mechanical", 5, "roll_mech_dnf_rate_5_driver")
    df = add_rolling_rates(df, "constructor_id", "dnf_mechanical", 5, "roll_mech_dnf_rate_5_constructor")
    df = add_rolling_rates(df, "driver_id", "dnf_collision", 5, "roll_collision_dnf_rate_5_driver")
    df = add_rolling_rates(df, "driver_id", "dnf_driver_error", 5, "roll_drivererror_dnf_rate_5_driver")

    # --- Track-similarity-weighted rolling features (Group 2b) ---
    print(f"\n[6/9] Computing track-similarity-weighted rolling features...")
    df = compute_similarity_weighted_rolling(df, window=5)

    # --- Quali priors (Group 3) ---
    print(f"\n[7/9] Computing qualifying priors (time-safe)...")
    df = add_quali_priors(df)

    # --- Race model features (Group 4) ---
    print(f"\n[8/9] Computing race model features...")
    df = add_race_model_features(df)

    # --- Track features + ratings (Group 5 & 6) ---
    print(f"\n[9/9] Adding track features, team/driver ratings, and interaction features...")
    df = add_track_features(df)
    df = add_team_driver_ratings(df)
    df = add_interaction_features(df)

    # --- Impute NaN priors with global median ---
    impute_cols = [
        "driver_quali_last", "driver_roll_quali_3", "driver_roll_quali_5",
        "driver_season_avg_quali", "driver_season_med_quali",
        "constructor_quali_last", "constructor_roll_quali_3", "constructor_roll_quali_5",
        "constructor_season_avg_quali",
        "field_season_avg_quali", "driver_vs_field_season", "constructor_vs_field_season",
        "team_delta_last", "team_delta_roll_3", "team_delta_roll_5",
        "driver_circuit_exp", "driver_circuit_roll_3", "constructor_circuit_exp",
        "position_delta_prev", "recent_wins", "recent_podiums", "recent_points_rate",
        "recent_form_weighted", "form_trend", "team_recent_form",
        "roll_points_3", "roll_points_5", "roll_finishpos_3", "roll_finishpos_5",
        "roll_quali_3", "roll_quali_5", "roll_dnf_rate_5",
        "roll_mech_dnf_rate_5_driver", "roll_mech_dnf_rate_5_constructor",
        "roll_collision_dnf_rate_5_driver", "roll_drivererror_dnf_rate_5_driver",
        "sim_weighted_points_3", "sim_weighted_points_5",
        "sim_weighted_finishpos_3", "sim_weighted_finishpos_5",
        "sim_weighted_quali_3", "sim_weighted_quali_5",
    ]
    for c in impute_cols:
        if c in df.columns:
            med = df[c].median()
            df[c] = df[c].fillna(med if pd.notna(med) else 0.0)

    # Drop intermediate/unused columns from output
    drop_cols = ["position_text", "status", "dnf_cause",
                 "constructor_id_jolpica", "q1", "q2", "q3"]
    df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True, errors="ignore")

    # --- Save per-year parquet files ---
    JOLPICA_MODEL_ROWS_DIR.mkdir(parents=True, exist_ok=True)

    total_saved = 0
    for year in target_years:
        year_df = df[df["season"] == year].copy()
        if year_df.empty:
            print(f"\n  [SKIP] No data for {year}")
            continue

        year_df = year_df.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)
        out_path = JOLPICA_MODEL_ROWS_DIR / f"model_rows_{year}.parquet"
        year_df.to_parquet(out_path, index=False)
        total_saved += len(year_df)
        print(f"\n  Saved: {out_path}")
        print(f"    Rows: {len(year_df):,} | Columns: {len(year_df.columns)}")
        print(f"    Drivers: {year_df['driver_id'].nunique()} | Rounds: {year_df['round'].nunique()}")

    # --- Save combined all_model_rows.parquet (used by steps 04, 06, 07) ---
    all_out = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    df_all = df.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)
    df_all.to_parquet(all_out, index=False)
    print(f"\n  Saved combined: {all_out}")
    print(f"    Rows: {len(df_all):,} | Columns: {len(df_all.columns)}")

    print(f"\n{'=' * 70}")
    print(f"Done. Total rows saved: {total_saved:,}")
    print(f"Output columns ({len(df.columns)}): {sorted(df.columns.tolist())}")
    print(f"{'=' * 70}")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Build Jolpica historical features (model_rows parquet)."
    )
    parser.add_argument("--year", type=int, help="Single year to build features for")
    parser.add_argument("--all", action="store_true", help="Build for all historical seasons + current")
    args = parser.parse_args()

    if args.all:
        target_years = ALL_SEASONS
    elif args.year:
        target_years = [args.year]
    else:
        parser.error("Specify --year YYYY or --all")

    build_features(target_years)


if __name__ == "__main__":
    main()
