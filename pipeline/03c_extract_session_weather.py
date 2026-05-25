"""
Script 03c — Extract Session Weather

Aggregates per-session weather conditions from FastF1's cached `weather_data`
into a compact Parquet that downstream model-input building (Phase B of the
Weather Awareness Level 3 plan) can join onto the training rows.

The FastF1 cache already contains the raw weather_data DataFrame for every
session we've ever downloaded (one ff1pkl per session under
`data/raw/fastf1/cache/...`). Loading via fastf1.get_session(...).load(weather=True)
hits the cache (no network calls if the session was previously downloaded),
giving us a DataFrame with columns:
    Time, AirTemp, Humidity, Pressure, Rainfall (bool), TrackTemp, WindDirection, WindSpeed
sampled roughly once per minute over the session duration.

Output: ONE row per (season, round, session_name) with aggregates.

Per the Phase A spec:
    season, round, session_name, was_wet (bool), precip_minutes (int),
    pct_session_wet (float), track_temp_avg/min/max, air_temp_avg,
    humidity_avg, wind_avg, n_samples

`was_wet` definition (from the Level 3 plan):
    Rainfall=True for >=10% of samples OR precip_minutes >=5
This catches sustained light rain AND short heavy showers, while filtering
out a few stray "drizzle" samples.

Usage:
    python pipeline/03c_extract_session_weather.py                  # incremental
    python pipeline/03c_extract_session_weather.py --year 2024      # one season
    python pipeline/03c_extract_session_weather.py --year 2024 --round 12
    python pipeline/03c_extract_session_weather.py --force          # re-process

Outputs:
    data/processed/weather/session_weather_year{Y}.parquet   (per-year)
    data/processed/weather/all_session_weather.parquet       (concat of all)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import fastf1
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    CANCELLED_ROUNDS_2026,
    CURRENT_SEASON,
    FASTF1_CACHE_DIR,
    FASTF1_RAW_DIR,
    PROCESSED_DIR,
    fastf1_round,
)

WEATHER_DIR = PROCESSED_DIR / "weather"

# Session codes we'll try to load per round. The order matters only for log
# readability; FastF1 doesn't care. We try every session and skip the ones
# that don't exist for the weekend (e.g. no FP2/FP3 on sprint weekends).
SESSION_CODES_REGULAR = ["FP1", "FP2", "FP3", "Qualifying", "Race"]
SESSION_CODES_SPRINT = ["FP1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"]

# How a session name lands in our output schema. Keeps the output keys short
# and consistent (FP1/FP2/FP3/Q/SQ/S/R) regardless of which alias FastF1 used.
SESSION_NAME_NORMALIZE = {
    "FP1": "FP1",
    "FP2": "FP2",
    "FP3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",   # 2023 alias
    "Sprint": "SR",
    "Race": "R",
}

# Wet-label thresholds (per the Level 3 plan, §4 Phase A).
WET_PCT_THRESHOLD = 0.10        # >=10% of samples Rainfall=True
WET_MINUTES_THRESHOLD = 5       # OR >=5 minutes of Rainfall


# -- Helpers ------------------------------------------------------------------

def list_completed_rounds(year: int) -> list[int]:
    """Return internal round numbers for which we have any FastF1 data on disk."""
    year_dir = FASTF1_RAW_DIR / f"year{year}"
    if not year_dir.exists():
        return []
    rounds = []
    for p in year_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if not name.startswith("round"):
            continue
        try:
            r = int(name[len("round"):])
        except ValueError:
            continue
        # Skip cancelled rounds (we won't have weather data for them anyway)
        if year == 2026 and r in CANCELLED_ROUNDS_2026:
            continue
        rounds.append(r)
    return sorted(rounds)


def session_codes_for(year: int, round_num: int) -> list[str]:
    """Decide which session codes to attempt for this weekend.

    Detected from what lap parquets are on disk. If sprint_qualifying.parquet
    or sprint.parquet exists, treat as sprint weekend.
    """
    round_dir = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}"
    if (round_dir / "sprint_qualifying.parquet").exists() or \
       (round_dir / "sprint_shootout.parquet").exists() or \
       (round_dir / "sprint.parquet").exists():
        return SESSION_CODES_SPRINT
    return SESSION_CODES_REGULAR


def aggregate_weather(weather_df: pd.DataFrame) -> dict:
    """Aggregate a FastF1 weather_data DataFrame into one row of weather stats.

    weather_df columns: Time (timedelta), AirTemp, Humidity, Pressure,
    Rainfall (bool), TrackTemp, WindDirection, WindSpeed.
    Samples are ~1/minute; len(weather_df) ~= session duration in minutes.
    """
    n = len(weather_df)
    if n == 0:
        return {}

    rainfall = weather_df["Rainfall"].astype(bool) if "Rainfall" in weather_df.columns else None
    if rainfall is not None:
        precip_minutes = int(rainfall.sum())
        pct_wet = float(rainfall.sum() / n)
        was_wet = (pct_wet >= WET_PCT_THRESHOLD) or (precip_minutes >= WET_MINUTES_THRESHOLD)
    else:
        precip_minutes, pct_wet, was_wet = 0, 0.0, False

    def _mean(col: str) -> Optional[float]:
        if col not in weather_df.columns:
            return None
        s = weather_df[col].dropna()
        return float(s.mean()) if len(s) else None

    def _min(col: str) -> Optional[float]:
        if col not in weather_df.columns:
            return None
        s = weather_df[col].dropna()
        return float(s.min()) if len(s) else None

    def _max(col: str) -> Optional[float]:
        if col not in weather_df.columns:
            return None
        s = weather_df[col].dropna()
        return float(s.max()) if len(s) else None

    return {
        "n_samples": n,
        "was_wet": bool(was_wet),
        "precip_minutes": precip_minutes,
        "pct_session_wet": round(pct_wet, 4),
        "track_temp_avg": _mean("TrackTemp"),
        "track_temp_min": _min("TrackTemp"),
        "track_temp_max": _max("TrackTemp"),
        "air_temp_avg": _mean("AirTemp"),
        "humidity_avg": _mean("Humidity"),
        "wind_avg": _mean("WindSpeed"),
    }


def extract_one_session(year: int, round_num: int, session_code: str) -> Optional[dict]:
    """Load one session via FastF1 (cached) and return one aggregated row.

    Returns None if the session doesn't exist (e.g. FP3 on a sprint weekend)
    or if loading fails for any reason. Errors are logged, not raised — we
    want partial extraction over a fully-failed run.
    """
    ff1_round = fastf1_round(round_num, year)
    try:
        session = fastf1.get_session(year, ff1_round, session_code)
        session.load(laps=False, telemetry=False, weather=True, messages=False)
    except Exception as e:
        # Common case: session doesn't exist for this weekend type
        # (e.g. asking for FP3 on a sprint weekend). Treat as soft skip.
        msg = str(e).lower()
        if "does not exist" in msg or "not exist" in msg or "could not load" in msg:
            return None
        print(f"    [WARN] {year} R{round_num} {session_code}: load failed: {e}")
        return None

    weather = getattr(session, "weather_data", None)
    if weather is None or weather.empty:
        return None

    agg = aggregate_weather(weather)
    if not agg:
        return None

    norm_name = SESSION_NAME_NORMALIZE.get(session_code, session_code)
    return {
        "season": year,
        "round": round_num,
        "session_name": norm_name,
        "session_code_raw": session_code,
        **agg,
    }


def extract_round(year: int, round_num: int) -> list[dict]:
    """Extract weather for all sessions in one round. Returns list of row dicts."""
    rows = []
    codes = session_codes_for(year, round_num)
    print(f"  R{round_num}: sessions {codes}")
    for code in codes:
        row = extract_one_session(year, round_num, code)
        if row:
            wet_tag = "WET" if row["was_wet"] else "dry"
            print(f"    {code:>18s}: {wet_tag} "
                  f"(rain {row['precip_minutes']}min / {row['pct_session_wet']*100:.0f}%, "
                  f"track {row['track_temp_avg']:.1f}C, air {row['air_temp_avg']:.1f}C)")
            rows.append(row)
    return rows


# -- Per-year orchestration ---------------------------------------------------

def existing_year_df(year: int) -> Optional[pd.DataFrame]:
    """Load the existing per-year Parquet if present."""
    path = WEATHER_DIR / f"session_weather_year{year}.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def already_extracted_keys(df: Optional[pd.DataFrame]) -> set[tuple[int, str]]:
    """Set of (round, session_code_raw) already on disk for incremental skip."""
    if df is None or df.empty:
        return set()
    return set(
        (int(r), str(s)) for r, s in zip(df["round"], df["session_code_raw"])
    )


def process_year(year: int, only_round: Optional[int], force: bool) -> int:
    """Extract weather for a season. Returns count of new rows added."""
    rounds = list_completed_rounds(year)
    if only_round is not None:
        if only_round not in rounds:
            print(f"  R{only_round} not on disk for {year} — skipping.")
            return 0
        rounds = [only_round]
    if not rounds:
        return 0

    existing = None if force else existing_year_df(year)
    skip_keys = already_extracted_keys(existing)

    print(f"\n[{year}] {len(rounds)} round(s) to consider; "
          f"{len(skip_keys)} (round, session) pairs already extracted")

    new_rows: list[dict] = []
    for r in rounds:
        codes = session_codes_for(year, r)
        if not force and all((r, c) in skip_keys for c in codes):
            continue  # nothing to do
        round_rows = extract_round(year, r)
        # Drop rows we've already extracted (unless --force)
        if not force:
            round_rows = [
                row for row in round_rows
                if (row["round"], row["session_code_raw"]) not in skip_keys
            ]
        new_rows.extend(round_rows)

    if not new_rows:
        print(f"[{year}] nothing new.")
        return 0

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True) if existing is not None else new_df
    # Dedup defensively: keep last (most recent extract wins) if duplicate (round, session)
    combined = combined.drop_duplicates(
        subset=["season", "round", "session_code_raw"], keep="last"
    ).sort_values(["round", "session_code_raw"]).reset_index(drop=True)

    WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEATHER_DIR / f"session_weather_year{year}.parquet"
    combined.to_parquet(out_path, index=False)
    print(f"[{year}] wrote {len(new_rows)} new row(s) -> {out_path}  "
          f"(total {len(combined)})")
    return len(new_rows)


def rebuild_combined() -> None:
    """Concatenate every per-year file into a single aggregate Parquet."""
    parts = []
    for p in sorted(WEATHER_DIR.glob("session_weather_year*.parquet")):
        try:
            parts.append(pd.read_parquet(p))
        except Exception as e:
            print(f"  [WARN] could not read {p}: {e}")
    if not parts:
        print("\nNo per-year files found — nothing to combine.")
        return
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.sort_values(["season", "round", "session_code_raw"]).reset_index(drop=True)
    out_path = WEATHER_DIR / "all_session_weather.parquet"
    combined.to_parquet(out_path, index=False)

    # Summary
    n_total = len(combined)
    n_wet = int(combined["was_wet"].sum())
    wet_pct = n_wet / n_total * 100 if n_total else 0
    print(f"\nCombined: {n_total} session rows, {n_wet} wet ({wet_pct:.1f}%) -> {out_path}")

    # Per-session-type breakdown
    print("  Wet rate by session type:")
    for name, sub in combined.groupby("session_name"):
        wr = sub["was_wet"].sum() / len(sub) * 100
        print(f"    {name:>4s}: {len(sub):>3d} sessions, {int(sub['was_wet'].sum()):>2d} wet ({wr:.0f}%)")


# -- Main ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate per-session weather from FastF1 cache.")
    parser.add_argument("--year", type=int, default=None,
                        help="Process only this season (default: all 2020-current).")
    parser.add_argument("--round", type=int, default=None,
                        help="Process only this round (requires --year).")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract sessions already on disk.")
    args = parser.parse_args()

    if args.round is not None and args.year is None:
        parser.error("--round requires --year")

    # FastF1 cache must be enabled — otherwise it tries to hit the API.
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))

    years = [args.year] if args.year is not None else list(range(2020, CURRENT_SEASON + 1))

    print("=" * 70)
    print("Session Weather Extraction (Level 3 / Phase A)")
    print(f"  Years: {years}")
    if args.round is not None:
        print(f"  Round filter: R{args.round}")
    if args.force:
        print("  --force: re-extracting everything")
    print("=" * 70)

    total_new = 0
    for y in years:
        total_new += process_year(y, args.round, args.force)

    rebuild_combined()

    print(f"\nDone. {total_new} new session row(s) extracted across all years.")
    print("=" * 70)


if __name__ == "__main__":
    main()
