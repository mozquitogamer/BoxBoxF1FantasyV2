"""Read a cached OpenF1 race bundle for post-race analysis."""

import json
from collections import defaultdict

import pandas as pd

from config.settings import RAW_DIR, SEED_DIR


def load_openf1_race_laps(year: int, round_num: int) -> pd.DataFrame | None:
    directory = RAW_DIR / "openf1" / f"year{year}" / f"round{round_num}"
    if not (directory / "sessions.json").exists():
        return None

    def read(endpoint):
        return json.loads((directory / f"{endpoint}.json").read_bytes())

    session, = read("sessions")
    calendar = json.loads((SEED_DIR / "races.json").read_bytes())["races"]
    race = next(row for row in calendar if row["round"] == round_num)
    event_date = pd.Timestamp(session["date_start"]).tz_convert(session["gmt_offset"][:6]).date()
    if (session["year"] != year or session["session_name"] != "Race"
            or race["date"] != event_date.isoformat() or race.get("cancelled")):
        raise ValueError("OpenF1 session does not match the requested race")
    session_key = session["session_key"]

    def records(endpoint):
        rows = read(endpoint)
        if any(row["session_key"] != session_key for row in rows):
            raise ValueError(f"Mixed OpenF1 session keys in {endpoint}")
        return rows

    drivers = {row["driver_number"]: row["name_acronym"] for row in records("drivers")}
    completed = {row["driver_number"]: row["number_of_laps"] for row in records("session_result")}
    pit_in = {(row["driver_number"], row["lap_number"]): pd.Timestamp(row["date"])
              for row in records("pit")}
    tyres = {}
    for stint in records("stints"):
        for lap_number in range(stint["lap_start"], stint["lap_end"] + 1):
            key = stint["driver_number"], lap_number
            if key in tyres:
                raise ValueError(f"Overlapping OpenF1 tyre stints for {key}")
            tyres[key] = stint

    race_control = sorted(records("race_control"), key=lambda row: pd.Timestamp(row["date"]))
    restrictions = []
    restricted_since = None
    for message in race_control:
        flag = message.get("flag")
        time = pd.Timestamp(message["date"])
        if (flag in {"RED", "SC", "VSC"} and message.get("scope") == "Track"
                or message.get("category") == "SafetyCar"
                and message["message"] in {"SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR DEPLOYED"}):
            if restricted_since is None:
                restricted_since = time
        elif restricted_since is not None and flag in {"GREEN", "CLEAR"} and message.get("scope") == "Track":
            restrictions.append((restricted_since, time))
            restricted_since = None
    if restricted_since is not None:
        restrictions.append((restricted_since, pd.Timestamp.max.tz_localize("UTC")))

    positions = defaultdict(list)
    for row in records("position"):
        positions[row["driver_number"]].append((pd.Timestamp(row["date"]), row["position"]))
    weather = sorted((pd.Timestamp(row["date"]), row["track_temperature"])
                     for row in records("weather"))

    laps = records("laps")
    starts = {(lap["driver_number"], lap["lap_number"]): pd.Timestamp(lap["date_start"])
              for lap in laps}
    if len(starts) != len(laps):
        raise ValueError("Duplicate OpenF1 race laps")
    output = []
    for lap in laps:
        number, lap_number = lap["driver_number"], lap["lap_number"]
        if lap_number < 1 or lap_number > (completed[number] or 0):
            continue
        key = number, lap_number
        previous = number, lap_number - 1
        start = starts[key]
        duration = lap["lap_duration"]
        end = start + pd.Timedelta(seconds=duration) if duration and duration > 0 else pd.NaT
        crossing = starts.get((number, lap_number + 1), end)
        if pd.isna(crossing):
            crossing = end
        last_position = max((sample for sample in positions[number] if sample[0] <= crossing),
                            default=(None, None))
        last_weather = next((temp for time, temp in reversed(weather) if time <= start), None)
        stint = tyres.get(key)
        age = stint.get("tyre_age_at_start") if stint else None
        restricted = any(start < until and end > since for since, until in restrictions)
        output.append({
            "Driver": drivers[number], "LapNumber": lap_number,
            "LapTime_seconds": duration,
            **{f"Sector{i}Time_seconds": lap[f"duration_sector_{i}"] for i in range(1, 4)},
            "SpeedST": lap["st_speed"],
            "Stint": stint["stint_number"] if stint else None,
            "Compound": stint["compound"] if stint else "UNKNOWN",
            "TyreLife": age + lap_number - stint["lap_start"] + 1 if age is not None else None,
            "PitInTime": pit_in.get(key, pd.NaT),
            "PitOutTime": start if lap["is_pit_out_lap"] or previous in pit_in else pd.NaT,
            "TrackStatus": "restricted" if restricted else "1",
            "IsAccurate": bool(duration and duration > 0 and pd.notna(start)),
            "Position": last_position[1],
            "track_temperature": last_weather,
        })

    frame = pd.DataFrame(output)
    if frame.empty or frame["LapNumber"].max() != max(n for n in completed.values() if n is not None):
        raise ValueError("OpenF1 race bundle is missing the final lap")
    frame.attrs["lap_source"] = {"provider": "OpenF1", "session_key": session_key}
    return frame
