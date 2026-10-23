"""Import a cached, completed OpenF1 practice session when FastF1 is unavailable.

The bundle contains sessions.json and {drivers,laps,stints,race_control,
weather,session_result}_fpN.json from the public OpenF1 API. No lap times or
missing telemetry are invented. The output uses the normal FP feature schema.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import CURRENT_SEASON, LAPS_DIR, SEED_DIR


def build_practice_laps(bundle: dict, session: dict, round_num: int) -> pd.DataFrame:
    """Convert source laps, retaining physical stints and excluding invalid laps."""
    session_key = session["session_key"]
    session_name = {"Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3"}.get(session["session_name"])
    if session_name is None:
        raise ValueError("Only free-practice sessions may feed FP features")
    for records in bundle.values():
        if any(record.get("session_key") != session_key for record in records):
            raise ValueError("OpenF1 bundle mixes session keys")
    builder = importlib.import_module("pipeline.02_build_laps")
    driver_map, constructor_map = builder.load_id_mappings()
    drivers = {row["driver_number"]: row for row in bundle["drivers"]}
    deleted: dict[int, set[float]] = {}
    deleted_laps: set[tuple[int, int]] = set()
    for message in sorted(bundle["race_control"], key=lambda row: row["date"]):
        text = message.get("message", "")
        if "DELETED" not in text and "REINSTATED" not in text:
            continue
        car = re.search(r"CAR\s+(\d+)", text)
        number = int(car[1]) if car else message.get("driver_number")
        if number is None:
            continue
        lap_time = re.search(r"TIME\s+(\d+):(\d+\.\d+)", text)
        lap_number = re.search(r"\bLAP\s+(\d+)\b", text)
        if lap_time:
            seconds = round(int(lap_time[1]) * 60 + float(lap_time[2]), 3)
            times = deleted.setdefault(number, set())
            if "REINSTATED" in text:
                times.discard(seconds)
            else:
                times.add(seconds)
        elif lap_number:
            key = (number, int(lap_number[1]))
            if "REINSTATED" in text:
                deleted_laps.discard(key)
            else:
                deleted_laps.add(key)

    weather = pd.DataFrame(bundle["weather"])
    flags = sorted([
        row for row in bundle["race_control"]
        if row.get("scope") == "Track" and row.get("flag") in {"RED", "GREEN", "CLEAR", "SC", "VSC"}
    ], key=lambda row: row["date"])
    excluded_intervals = []
    flagged_at = None
    for flag in flags:
        time = pd.Timestamp(flag["date"])
        if flag["flag"] in {"RED", "SC", "VSC"}:
            if flagged_at is None:
                flagged_at = time
        elif flagged_at is not None:
            excluded_intervals.append((flagged_at, time))
            flagged_at = None
    if flagged_at is not None:
        excluded_intervals.append((flagged_at, pd.Timestamp.max.tz_localize("UTC")))

    rows = []
    for lap in bundle["laps"]:
        number, lap_number = lap["driver_number"], lap["lap_number"]
        duration = lap.get("lap_duration")
        if duration is None or duration <= 0 or lap.get("is_pit_out_lap"):
            continue
        if round(duration, 3) in deleted.get(number, set()) or (number, lap_number) in deleted_laps:
            continue
        # The lap immediately before an out-lap ends in the pits. Final laps
        # after the chequered flag are likewise excluded unless a flying lap
        # started before the flag, as in the FastF1 path.
        if any(other["driver_number"] == number and other["lap_number"] == lap_number + 1
               and other.get("is_pit_out_lap") for other in bundle["laps"]):
            continue
        if not lap.get("date_start"):
            continue
        start = pd.Timestamp(lap["date_start"]).as_unit("ns")
        end = start + pd.to_timedelta(float(duration), unit="s")
        if start > pd.Timestamp(session["date_end"]):
            continue
        if any(start < flag_end and end > flag_start for flag_start, flag_end in excluded_intervals):
            continue
        stints = [row for row in bundle["stints"] if row["driver_number"] == number
                  and row["lap_start"] <= lap_number <= row["lap_end"]]
        if len(stints) != 1:
            continue  # Unknown tyre/run identity is not comparable evidence.
        stint = stints[0]
        driver = drivers[number]
        acronym = driver["name_acronym"]
        age = stint.get("tyre_age_at_start")
        rows.append({
            "driver_id": driver_map.get(acronym, acronym),
            "constructor_id": constructor_map.get(driver["team_name"].lower(), driver["team_name"]),
            "lap_time": duration,
            **{f"sector_{i}": lap.get(f"duration_sector_{i}") for i in range(1, 4)},
            "compound": builder.normalize_compound(stint["compound"]),
            "stint_number": stint["stint_number"], "lap_number": lap_number,
            "tyre_life": age + lap_number - stint["lap_start"] + 1 if age is not None else np.nan,
            "session": session_name, "track": session["location"],
            "year": session["year"], "round": round_num,
            **{target: weather[source].mean() if source in weather else np.nan for target, source in [
                ("track_temperature", "track_temperature"), ("air_temperature", "air_temperature"),
                ("humidity", "humidity"), ("wind_speed", "wind_speed")
            ]},
            "rainfall": bool(weather["rainfall"].any()) if "rainfall" in weather else None,
            "speed_trap_1": lap.get("i1_speed"), "speed_trap_2": lap.get("i2_speed"),
            "speed_st": lap.get("st_speed"), "fp_data_source": "openf1",
            "source_session_key": session_key,
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No valid OpenF1 practice laps")
    # Reject any purported clean lap faster than the published classification.
    for result in bundle["session_result"]:
        duration = result.get("duration")
        driver = drivers.get(result["driver_number"])
        if not isinstance(duration, (float, int)) or driver is None:
            continue
        driver_id = driver_map.get(driver["name_acronym"], driver["name_acronym"])
        best = frame.loc[frame["driver_id"] == driver_id, "lap_time"].min()
        if pd.notna(best) and best < duration - 0.005:
            raise ValueError(f"Unfiltered invalid best lap for {driver_id}: {best} < {duration}")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--session", choices=["FP1", "FP2", "FP3"], required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--session-key", type=int, required=True)
    args = parser.parse_args()
    sessions = json.loads((args.bundle / "sessions.json").read_bytes())
    session = next(row for row in sessions if row["session_key"] == args.session_key)
    races = json.loads((SEED_DIR / "races.json").read_bytes())["races"]
    race = next(row for row in races if row["round"] == args.round)
    start, end = pd.Timestamp(session["date_start"]), pd.Timestamp(session["date_end"])
    race_date = pd.Timestamp(race["date"], tz="UTC")
    if session["year"] != CURRENT_SEASON or not 0 <= (race_date.date() - start.date()).days <= 3:
        raise ValueError("Session does not match the requested race weekend")
    if end > pd.Timestamp.now(tz="UTC"):
        raise ValueError("Practice has not finished")
    if session["session_name"] != f"Practice {args.session[-1]}":
        raise ValueError("Practice session mismatch")
    paths = {name: args.bundle / f"{name}_{args.session.lower()}.json" for name in
             ["drivers", "laps", "stints", "race_control", "weather", "session_result"]}
    bundle = {name: json.loads(path.read_bytes()) for name, path in paths.items()}
    frame = build_practice_laps(bundle, session, args.round)
    destination = LAPS_DIR / f"round{args.round}"
    destination.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(destination / f"all_laps_{args.session.lower()}.parquet", index=False)
    provenance = {
        "source": "openf1", "session": session, "round": args.round,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "clean_laps": len(frame), "drivers": sorted(frame["driver_id"].unique()),
        "sources": {name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "url": f"https://api.openf1.org/v1/{name}?session_key={args.session_key}"}
                    for name, path in paths.items()},
    }
    (destination / f"{args.session.lower()}_source.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"Imported {len(frame)} clean {args.session} laps for {frame['driver_id'].nunique()} drivers")
    print(frame.groupby("driver_id")["lap_time"].min().sort_values().to_string())


if __name__ == "__main__":
    main()
