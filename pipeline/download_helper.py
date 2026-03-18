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


if __name__ == "__main__":
    main()
