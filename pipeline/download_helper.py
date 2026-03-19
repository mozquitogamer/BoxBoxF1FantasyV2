"""
Non-interactive download helper — called by automation.

Usage:
    python pipeline/download_helper.py --mode jolpica_historical --start 2022 --end 2025
    python pipeline/download_helper.py --mode jolpica_round --year 2026 --round 1
    python pipeline/download_helper.py --mode fastf1_round --year 2026 --round 1
"""

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fastf1
from config.settings import FASTF1_CACHE_DIR


def load_download_module():
    """Import 01_download_data.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "download_data", Path(__file__).parent / "01_download_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--year", type=int)
    parser.add_argument("--round", type=int)
    args = parser.parse_args()

    # Setup FastF1 cache
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))

    dl = load_download_module()

    if args.mode == "jolpica_historical":
        for year in range(args.start, args.end + 1):
            dl.download_jolpica_year(year)

    elif args.mode == "jolpica_round":
        dl.download_jolpica_round(args.year, args.round)

    elif args.mode == "fastf1_round":
        dl.download_fastf1_round(args.year, args.round)

    elif args.mode == "fastf1_historical":
        for year in range(args.start, args.end + 1):
            total = dl.get_total_rounds_for_year(year)
            print(f"Year {year}: {total} rounds")
            for rnd in range(1, total + 1):
                dl.download_fastf1_round(year, rnd)

    elif args.mode == "fastf1_missing":
        # Only download rounds that don't already have FP data
        from config.settings import FASTF1_RAW_DIR
        for year in range(args.start, args.end + 1):
            total = dl.get_total_rounds_for_year(year)
            print(f"Year {year}: {total} rounds total")
            for rnd in range(1, total + 1):
                round_dir = FASTF1_RAW_DIR / f"year{year}" / f"round{rnd}"
                fp_files = list(round_dir.glob("fp*.parquet")) if round_dir.exists() else []
                if len(fp_files) >= 2:  # At least FP1+FP2
                    print(f"  Skipping {year} R{rnd} — already have {len(fp_files)} FP files")
                    continue
                print(f"  Downloading {year} R{rnd}...")
                dl.download_fastf1_round(year, rnd)


if __name__ == "__main__":
    main()
