"""
Non-interactive script to download missing FP1/FP2/FP3 data for historical seasons.
Used by the scheduled task: download-fastf1-fp-data

NOTE: The parquet files this writes are not currently consumed by the pipeline
(02_build_laps.py loads sessions directly via FastF1). The real value of running
it is warming the FastF1 cache, which 03c_extract_session_weather.py reads.

CALENDAR MAPPING: internal round numbers diverge from FastF1's compressed
numbering once a round is cancelled (2026 R4 Bahrain + R5 Saudi). We iterate
INTERNAL rounds, skip cancelled ones, and map to the FastF1 round via
fastf1_round() at the get_session boundary — same convention as
01_download_data.py. Output paths use the internal round number.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fastf1
from config.settings import (
    FASTF1_RAW_DIR,
    FASTF1_CACHE_DIR,
    CANCELLED_ROUNDS_2026,
    CURRENT_SEASON,
    fastf1_round,
)

# Sessions to attempt per round (sprint weekends only have FP1)
FP_SESSIONS = ["FP1", "FP2", "FP3"]

fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))

# Suppress verbose fastf1 output
import logging
logging.getLogger("fastf1").setLevel(logging.WARNING)


def has_fp_data(year: int, round_num: int) -> bool:
    """Return True if FP1 parquet already exists for this round."""
    fp1_path = FASTF1_RAW_DIR / f"year{year}" / f"round{round_num}" / "fp1.parquet"
    return fp1_path.exists()


def internal_rounds_for_year(year: int, ff1_schedule_len: int) -> list[int]:
    """Internal round numbers to check for a season.

    FastF1's schedule is compressed (it omits cancelled rounds). For the current
    season we add the cancelled rounds back to recover the true internal max,
    then skip the cancelled ones. Historical seasons had no cancellations, so
    internal numbering == FastF1's compressed numbering.
    """
    if year == CURRENT_SEASON and CANCELLED_ROUNDS_2026:
        internal_max = ff1_schedule_len + len(CANCELLED_ROUNDS_2026)
        return [r for r in range(1, internal_max + 1) if r not in CANCELLED_ROUNDS_2026]
    return list(range(1, ff1_schedule_len + 1))


def download_fp_session(year: int, round_num: int, session_name: str, output_dir: Path) -> bool:
    """Download a single FP session. Returns True on success."""
    out_path = output_dir / f"{session_name.lower()}.parquet"
    if out_path.exists():
        print(f"    {session_name}: already exists, skipping")
        return True

    try:
        # Map internal round -> FastF1's compressed round at the API boundary.
        ff1_round = fastf1_round(round_num, year)
        session = fastf1.get_session(year, ff1_round, session_name)
        session.load(laps=True, telemetry=False, weather=True, messages=False)
        laps = session.laps
    except Exception as e:
        err = str(e)
        if "rate limit" in err.lower() or "429" in err:
            print(f"    RATE LIMIT hit on {session_name}")
            return None  # Signal rate limit
        print(f"    {session_name}: skipped ({err})")
        return False
    if laps is None or laps.empty:
        print(f"    {session_name}: no lap data")
        return False

    df = laps.copy()
    df["session"] = session_name
    df["year"] = year
    df["round"] = round_num
    df["track"] = session.event["EventName"] if hasattr(session, "event") else ""

    weather = session.weather_data
    if weather is not None and not weather.empty:
        df["track_temperature"] = weather["TrackTemp"].mean() if "TrackTemp" in weather.columns else None
        df["air_temperature"] = weather["AirTemp"].mean() if "AirTemp" in weather.columns else None
    else:
        df["track_temperature"] = None
        df["air_temperature"] = None

    # Convert timedelta columns to seconds
    for col in df.select_dtypes(include=["timedelta64"]).columns:
        df[f"{col}_seconds"] = df[col].dt.total_seconds()

    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False, engine="pyarrow")
    print(f"    {session_name}: {len(df)} laps saved -> {out_path.name}")
    return True


def download_missing_fp():
    downloaded_rounds = 0
    rate_limited = False

    # Priority: current season first, then historical gaps
    years_to_check = [2026, 2023, 2025, 2022, 2024]

    for year in years_to_check:
        if rate_limited:
            break

        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
            total_rounds = len(schedule)
        except Exception as e:
            print(f"Could not get {year} schedule: {e}")
            continue

        # Find missing rounds
        missing = []
        for rnd in internal_rounds_for_year(year, total_rounds):
            if not has_fp_data(year, rnd):
                missing.append(rnd)

        if not missing:
            print(f"\n{year}: All {total_rounds} rounds have FP data. Skipping.")
            continue

        print(f"\n{year}: {len(missing)} rounds missing FP data: {missing}")

        for rnd in missing:
            if rate_limited:
                break

            output_dir = FASTF1_RAW_DIR / f"year{year}" / f"round{rnd}"
            print(f"\n  Downloading {year} Round {rnd}...")

            any_success = False
            for session_name in FP_SESSIONS:
                result = download_fp_session(year, rnd, session_name, output_dir)
                if result is None:  # Rate limit
                    rate_limited = True
                    print(f"  Rate limit hit — stopping downloads")
                    break
                if result:
                    any_success = True
                time.sleep(0.5)

            if any_success:
                downloaded_rounds += 1

    # Final report
    print("\n" + "=" * 50)
    print("DOWNLOAD REPORT")
    print("=" * 50)
    print(f"New rounds with FP data downloaded: {downloaded_rounds}")
    if rate_limited:
        print("Stopped early due to rate limiting — next run will continue")

    # Count remaining gaps
    print("\nRemaining gaps by year:")
    for year in [2022, 2023, 2024, 2025, 2026]:
        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
            total = len(schedule)
            still_missing = [r for r in internal_rounds_for_year(year, total) if not has_fp_data(year, r)]
            print(f"  {year}: {len(still_missing)} of {total} rounds still missing FP data")
            if still_missing:
                print(f"    Missing rounds: {still_missing}")
        except Exception as e:
            print(f"  {year}: error checking - {e}")

    # Total FP file count
    total_fp_files = sum(1 for f in FASTF1_RAW_DIR.rglob("fp*.parquet"))
    print(f"\nTotal FP parquet files: {total_fp_files}")


if __name__ == "__main__":
    download_missing_fp()
