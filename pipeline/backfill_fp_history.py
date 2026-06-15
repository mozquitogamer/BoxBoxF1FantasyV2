"""
One-off backfill: extract FP telemetry features for historical seasons.

WHY: the FP feature pipeline (02_build_laps + 03_extract_features) was hardcoded
to CURRENT_SEASON, so the model's Layer-2 (FP telemetry) only ever covered 2026
(~3% of training rows). But the raw FastF1 FP sessions for 2022-2025 are already
on disk / in cache, and 04_build_model_inputs.py was DESIGNED to merge historical
FP from data/processed/features/year{YYYY}/round{N}/features.parquet — that path
just never got populated.

This script reuses 02's process_fp_session and 03's extract_driver_features
(identical method to the current season — no train/inference skew) and writes the
year-keyed feature files 04 already knows how to find. Idempotent: existing files
are skipped unless --force.

After running:
    python pipeline/04_build_model_inputs.py --exclude-after 2026:8   # rebuild
    python pipeline/validate_model_config.py ...                     # compare

Usage:
    python pipeline/backfill_fp_history.py                 # 2022-2025, skip existing
    python pipeline/backfill_fp_history.py --years 2024,2025 --force
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import os
import sys
import time
from glob import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import (  # noqa: E402
    FASTF1_RAW_DIR,
    FASTF1_CACHE_DIR,
    FEATURES_DIR,
    MIN_LONG_RUN_LAPS,
    FP_SESSIONS,
)
import fastf1  # noqa: E402

DEFAULT_YEARS = [2022, 2023, 2024, 2025]


def _load_module(name: str, filename: str):
    spec = _ilu.spec_from_file_location(name, ROOT / "pipeline" / filename)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rounds_for_year(year: int) -> list[int]:
    """Round numbers we have raw FastF1 data for (from data/raw/fastf1/year{Y})."""
    dirs = glob(str(FASTF1_RAW_DIR / f"year{year}" / "round*"))
    rounds = []
    for d in dirs:
        try:
            rounds.append(int(os.path.basename(d).replace("round", "")))
        except ValueError:
            continue
    return sorted(rounds)


def process_year_round(bl, ef, year: int, rnd: int, driver_map, constructor_map):
    """Extract FP features for one (year, round). Returns (features_df | None, n_laps).

    Tries FP1/FP2/FP3 and keeps whatever loads — sprint weekends only have FP1,
    and process_fp_session returns None for sessions that don't exist.
    """
    frames = []
    for session_name in FP_SESSIONS:
        df = bl.process_fp_session(year, rnd, session_name, driver_map, constructor_map)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return None, 0
    combined = pd.concat(frames, ignore_index=True)
    feats = ef.extract_driver_features(combined, MIN_LONG_RUN_LAPS)
    # Mirror 03_extract_features.main metadata stamping (but with the REAL year).
    feats["year"] = year
    feats["round"] = rnd
    feats["fp_sessions_used"] = len(frames)
    return feats, len(combined)


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill historical FP features")
    ap.add_argument("--years", type=str, default=None,
                    help="Comma-separated years (default: 2022,2023,2024,2025)")
    ap.add_argument("--force", action="store_true",
                    help="Re-extract even if the features file already exists")
    args = ap.parse_args()

    years = ([int(y) for y in args.years.split(",")] if args.years else DEFAULT_YEARS)

    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))
    bl = _load_module("build_laps_mod", "02_build_laps.py")
    ef = _load_module("extract_features_mod", "03_extract_features.py")
    driver_map, constructor_map = bl.load_id_mappings()

    print("=" * 64)
    print("Backfill historical FP features ->", FEATURES_DIR / "year{Y}/round{N}")
    print("=" * 64)

    grand = {"rounds": 0, "with_fp": 0, "driver_rows": 0, "fp_rows": 0, "skipped": 0, "failed": []}
    t_start = time.time()

    for year in years:
        rounds = rounds_for_year(year)
        print(f"\n--- {year}: {len(rounds)} rounds with raw data ---")
        for rnd in rounds:
            out_dir = FEATURES_DIR / f"year{year}" / f"round{rnd}"
            out_path = out_dir / "features.parquet"
            if out_path.exists() and not args.force:
                grand["skipped"] += 1
                continue
            t0 = time.time()
            try:
                feats, n_laps = process_year_round(bl, ef, year, rnd, driver_map, constructor_map)
            except Exception as e:  # one bad round shouldn't kill the run
                print(f"  R{rnd}: FAILED ({type(e).__name__}: {e})")
                grand["failed"].append(f"{year}:{rnd}")
                continue
            grand["rounds"] += 1
            if feats is None or feats.empty:
                print(f"  R{rnd}: no FP laps loaded")
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            feats.to_parquet(out_path, index=False, engine="pyarrow")
            n_fp = int(feats["best_lap_time"].notna().sum()) if "best_lap_time" in feats else 0
            grand["with_fp"] += 1
            grand["driver_rows"] += len(feats)
            grand["fp_rows"] += n_fp
            print(f"  R{rnd}: {len(feats):>2} drivers, {n_fp:>2} with pace, "
                  f"{n_laps:>4} laps, {time.time()-t0:.0f}s")

    print("\n" + "=" * 64)
    print(f"Done in {time.time()-t_start:.0f}s")
    print(f"  Rounds processed: {grand['rounds']}  (skipped existing: {grand['skipped']})")
    print(f"  Rounds with FP:   {grand['with_fp']}")
    print(f"  Driver-rows written: {grand['driver_rows']}  ({grand['fp_rows']} with pace)")
    if grand["failed"]:
        print(f"  FAILED rounds: {grand['failed']}")
    print("\nNext: python pipeline/04_build_model_inputs.py --exclude-after 2026:8")


if __name__ == "__main__":
    main()
