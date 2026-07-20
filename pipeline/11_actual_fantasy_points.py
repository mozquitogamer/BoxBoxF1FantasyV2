"""
Script 11 — Calculate Actual Fantasy Points from Real Race Results

Calculates ACTUAL fantasy points scored from real race data (not predictions).
Uses Jolpica raw JSON files (results, qualifying, pitstops, sprint) as primary
source, with post_race_analysis.json as fallback for pitstop data.

Produces:
- Per-driver: actual qualifying pts, race pts, position change pts, overtake pts,
  fastest lap bonus, DNF penalty, sprint pts
- Per-constructor: combined driver pts + quali bonus + pitstop pts

Usage:
    python pipeline/11_actual_fantasy_points.py --round 1
    python pipeline/11_actual_fantasy_points.py --round 2
    python pipeline/11_actual_fantasy_points.py --all

Output:
    data/predictions/round{N}/actual_fantasy_points.json
    web/public/data/actual_round{N}.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    DATA_DIR,
    JOLPICA_RAW_DIR,
    PREDICTIONS_DIR,
    SEED_DIR,
    WEB_DATA_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
    fastf1_round,
    is_race_completed,
    load_official_pitstop_points,
)
from config.fantasy_scoring import (
    calc_qualifying_points_driver,
    calc_constructor_quali_bonus,
    calc_race_points_driver,
    calc_sprint_points_driver,
    calc_pitstop_points_constructor,
    calc_fastest_pitstop_bonus,
    calc_world_record_pitstop_bonus,
    RACE_DNF_DSQ_PENALTY,
    RACE_POSITION_POINTS,
    RACE_FASTEST_LAP_BONUS,
    RACE_POSITIONS_GAINED_PER_POS,
    RACE_OVERTAKE_POINTS,
    RACE_DRIVER_OF_THE_DAY_BONUS,
    QUALIFYING_NC_DSQ_PENALTY,
    SPRINT_DNF_DSQ_PENALTY,
    SPRINT_OVERTAKE_POINTS,
    CONSTRUCTOR_QUALI_DSQ_PENALTY,
    CONSTRUCTOR_SPRINT_DSQ_PENALTY,
    CONSTRUCTOR_RACE_DSQ_PENALTY,
)
from config.fantasy_prices import load_fantasy_price_maps

# Telemetry-detected overtakes over-count (pit-cycle swaps, SC reshuffles, blue-flag
# passes), so they're capped to a realistic ceiling. Official counts from
# overtakes.csv are the in-game truth and are NEVER capped (see _resolve_overtakes).
MAX_RACE_OVERTAKES = 8
MAX_SPRINT_OVERTAKES = 5


def _quali_session_from_position(pos):
    """Segment reached in 2026 qualifying, from final quali POSITION.

    22 cars: Q1 eliminates P17-22, Q2 eliminates P11-16, Q3 = top 10. F1
    Fantasy's constructor teamwork bonus counts the segment a driver REACHED
    (their quali classification), NOT whether they set a time in it — a P10 car
    that set no Q3 lap (e.g. LEC R9) still counts as 'reached Q3'. Deriving from
    set-time presence under-counted these; position is the correct basis and
    also gives the right Q2 cutoff (16, not 15).
    """
    if pos is None:
        return "Q1"
    if pos <= 10:
        return "Q3"
    if pos <= 16:
        return "Q2"
    return "Q1"


def _resolve_overtakes(abbrev: str, merged: dict, seed: dict, cap: int):
    """Resolve a driver's overtake count with source-aware capping.

    - overtakes.csv (official F1 Fantasy count) -> used verbatim, UNCAPPED.
    - telemetry-detected only                   -> capped at `cap` (over-counts).
    - no data                                    -> None (caller decides fallback).

    `seed` is the overtakes.csv dict; `merged` is detected∪seed (seed already
    checked first, so a `merged` hit here means detected-only).
    """
    if abbrev in seed:
        return int(seed[abbrev])            # official — verbatim
    if abbrev in merged:
        return min(int(merged[abbrev]), cap)  # telemetry — capped
    return None


# ==============================================================================
# Data loading helpers
# ==============================================================================

def load_dotd_winner(round_num: int) -> Optional[str]:
    """Load Driver of the Day winner for a given round.

    Returns driver abbreviation or None if not available.
    Source: formula1.com/en/results/2026/awards/driver-of-the-day
    """
    dotd_path = SEED_DIR / "dotd_winners.json"
    if not dotd_path.exists():
        return None
    with open(dotd_path) as f:
        data = json.load(f)
    return data.get("winners", {}).get(str(round_num))


def load_id_maps() -> tuple[dict, dict, dict]:
    """Load driver and constructor ID mappings.

    Returns:
        (jolpica_to_abbrev, abbrev_to_info, jolpica_constructor_map)
    """
    with open(SEED_DIR / "driver_ids.json") as f:
        data = json.load(f)

    jolpica_to_abbrev = {}
    for m in data["mappings"]:
        jolpica_to_abbrev[m["jolpica"]] = m["abbrev"]

    # Constructor mapping: jolpica ID -> our internal ID
    jolpica_constructor_map = {}
    for cm in data["constructor_mappings"]:
        jolpica_constructor_map[cm["jolpica"]] = cm["id"]
        for alt in cm.get("ergast_alt", []):
            jolpica_constructor_map[alt] = cm["id"]

    return jolpica_to_abbrev, data, jolpica_constructor_map


def load_drivers_info() -> dict:
    """Load driver seed data keyed by abbreviation."""
    with open(SEED_DIR / "drivers.json") as f:
        data = json.load(f)
    return {d["driver_id"]: d for d in data["drivers"]}


def load_constructors_info() -> dict:
    """Load constructor seed data keyed by constructor_id."""
    with open(SEED_DIR / "constructors.json") as f:
        data = json.load(f)
    return {c["constructor_id"]: c for c in data["constructors"]}


def load_fantasy_prices() -> tuple[dict, dict]:
    """Load current fantasy prices."""
    return load_fantasy_price_maps()


def load_jolpica_json(year: int, round_num: int, filename: str) -> Optional[dict]:
    """Load a Jolpica raw JSON file. Returns None if not found."""
    path = JOLPICA_RAW_DIR / f"year{year}" / f"round{round_num}" / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_post_race_analysis(round_num: int) -> Optional[dict]:
    """Load post_race_analysis.json as fallback data source."""
    path = PREDICTIONS_DIR / f"round{round_num}" / "post_race_analysis.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_detected_overtakes(year: int, round_num: int) -> tuple[dict, dict]:
    """Load detected overtake counts from 12_count_overtakes.py output.

    Returns:
        (race_overtakes, sprint_overtakes) — each is a dict mapping
        driver abbreviation -> overtake count, or empty dict if unavailable.
    """
    path = DATA_DIR / "overtakes" / f"year{year}" / f"round{round_num}" / "overtakes.json"
    if not path.exists():
        return {}, {}

    with open(path) as f:
        data = json.load(f)

    race_ot = {}
    sprint_ot = {}

    sessions = data.get("sessions", {})
    if "race" in sessions:
        for d in sessions["race"].get("drivers", []):
            race_ot[d["driver"]] = d["overtakes"]

    if "sprint" in sessions:
        for d in sessions["sprint"].get("drivers", []):
            sprint_ot[d["driver"]] = d["overtakes"]

    return race_ot, sprint_ot


def load_seed_overtakes(year: int, internal_round: int) -> tuple[dict, dict]:
    """Load manual overtake counts from data/seed/overtakes.csv if available.

    The seed CSV is the user's manually-maintained record of F1 Fantasy's
    OFFICIAL overtake counts (which sometimes differ from FastF1's
    telemetry-derived count). When present, these override detected counts so
    our actuals match the in-game scoring.

    The CSV uses sequential race numbering (skipping cancelled rounds — same
    compression FastF1 and Jolpica use), so we translate via fastf1_round().
    Driver IDs in the CSV are Jolpica-style (e.g. "max_verstappen", "russell")
    and are mapped to abbreviations via driver_ids.json.

    Returns (race_ot, sprint_ot) keyed by driver abbreviation, empty dicts if
    the CSV doesn't have data for this round.
    """
    import pandas as pd
    path = SEED_DIR / "overtakes.csv"
    if not path.exists():
        return {}, {}

    seed_round = fastf1_round(internal_round, year)

    with open(SEED_DIR / "driver_ids.json") as f:
        ids = json.load(f)
    j2a = {m["jolpica"]: m["abbrev"] for m in ids["mappings"]}

    df = pd.read_csv(path)
    df = df[df["round"] == seed_round].dropna(subset=["overtakes_made"])
    if df.empty:
        return {}, {}

    race_ot = {}
    sprint_ot = {}
    for _, row in df.iterrows():
        abbrev = j2a.get(row["driver_id"])
        if not abbrev:
            continue
        race_ot[abbrev] = int(row["overtakes_made"])
        if "sprint_overtakes" in df.columns:
            sp = row.get("sprint_overtakes")
            if sp is not None and not (isinstance(sp, float) and sp != sp):  # not NaN
                sprint_ot[abbrev] = int(sp)

    return race_ot, sprint_ot


def load_openf1_pitstops(year: int, round_num: int) -> Optional[dict]:
    """Load OpenF1 pit stop stationary times (stop_duration) for scoring.

    Returns dict mapping driver abbreviation -> list of stop_duration floats,
    or None if not available. These are the actual "wheels up" service times
    (2-4 seconds) used for F1 Fantasy constructor pit stop scoring.

    Stops where OpenF1 didn't record a stationary time (safety car, retirements,
    drive-through penalties, sensor dropouts) are EXCLUDED from scoring — F1
    Fantasy scoring needs a real wheels-up time. They are still counted in the
    website display via 13_fetch_pitstop_stationary.py with a "stationary_missing"
    flag, so the constructor pit stop count reflects reality.
    """
    path = DATA_DIR / "overtakes" / f"year{year}" / f"round{round_num}" / "overtakes.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    pitstops = data.get("pitstops")
    if not pitstops or not pitstops.get("by_driver"):
        return None

    # Convert to driver_abbrev -> list of stop_duration (filter out nulls — can't score them)
    result = {}
    for abbrev, stops in pitstops["by_driver"].items():
        scored = [s["stop_duration"] for s in stops if s.get("stop_duration") is not None]
        if scored:
            result[abbrev] = scored

    return result


# ==============================================================================
# Jolpica data parsers
# ==============================================================================

def parse_race_results(data: dict) -> tuple[list[dict], str]:
    """Parse Jolpica results.json into a flat list of driver results.

    Returns:
        (results_list, race_name)
    """
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return [], "Unknown"

    race = races[0]
    race_name = race.get("raceName", "Unknown")
    results = []

    for r in race.get("Results", []):
        driver_id = r["Driver"]["driverId"]
        position = int(r["position"])
        grid = int(r["grid"])
        status = r.get("status", "")
        position_text = r.get("positionText", "")
        laps = int(r.get("laps", 0))

        # Determine DNF/DSQ/DNS from positionText, NOT the status string.
        # Jolpica classifies a car that completes ~90% distance with a NUMERIC
        # positionText even if it retired late (status="Retired") — F1 scores it
        # as a finisher on its classified position. Only positionText=="R" is a
        # true (unclassified) retirement. This is the fix for classified late-
        # retirees like LEC R9 (P15, retired lap 62) being mis-scored as -20, and
        # for the old "status==Lapped" override wrongly un-DNF'ing genuine
        # retirements (ALB R9: posText=R, status=Lapped). Verified against all
        # A driver can start and retire before completing lap 1, so laps==0 is
        # not sufficient to label a DNS (for example RUS at Belgium 2026).
        # 2026 races: NUM=classified finisher, R=DNF, W=DNS, D=DSQ.
        is_dsq = position_text == "D" or status == "Disqualified"
        is_dns = position_text == "W" or status == "Did not start"
        is_dnf = (position_text == "R") and not is_dns and not is_dsq

        # Fastest lap: rank "1" in FastestLap
        fastest_lap = r.get("FastestLap", {})
        is_fastest_lap = fastest_lap.get("rank") == "1"

        results.append({
            "jolpica_driver_id": driver_id,
            "code": r["Driver"].get("code", ""),
            "jolpica_constructor_id": r["Constructor"]["constructorId"],
            "position": position,
            "grid": grid,
            "status": status,
            "position_text": position_text,
            "laps": laps,
            "is_dnf": is_dnf,
            "is_dsq": is_dsq,
            "is_dns": is_dns,
            "is_fastest_lap": is_fastest_lap,
            "given_name": r["Driver"].get("givenName", ""),
            "family_name": r["Driver"].get("familyName", ""),
        })

    return results, race_name


def parse_qualifying(data: dict) -> dict:
    """Parse Jolpica qualifying.json.

    Returns:
        dict mapping jolpica_driver_id -> {position, best_session, q1, q2, q3}
    """
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return {}

    quali_results = {}
    for qr in races[0].get("QualifyingResults", []):
        driver_id = qr["Driver"]["driverId"]
        position = int(qr["position"])

        q1 = qr.get("Q1", "")
        q2 = qr.get("Q2", "")
        q3 = qr.get("Q3", "")

        # Determine best session reached
        if q3 and q3.strip():
            best_session = "Q3"
        elif q2 and q2.strip():
            best_session = "Q2"
        elif q1 and q1.strip():
            best_session = "Q1"
        else:
            best_session = "NONE"

        # "Did not classify" in qualifying = no valid time in the mandatory Q1
        # segment (a deleted Q1 lap, or no time at all). Ergast can then show
        # later-segment times with an empty Q1 (e.g. HAD Miami R6: P22, Q1 empty
        # but Q2/Q3 present). Officially that's the -5 no-time-set penalty, not
        # the driver's classified-position points. This is the ONLY such case
        # across 2026 R1-R10; a normal Q1-eliminated driver keeps their Q1 time.
        no_time_set = not (q1 and q1.strip())

        quali_results[driver_id] = {
            "position": position,
            "best_session": best_session,
            "q1": q1,
            "q2": q2,
            "q3": q3,
            "no_time_set": no_time_set,
        }

    return quali_results


def parse_pitstops(data: dict) -> dict:
    """Parse Jolpica pitstops.json.

    Returns:
        dict mapping jolpica_driver_id -> list of pit stop durations (float seconds)
    """
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return {}

    pitstops_by_driver = {}
    for ps in races[0].get("PitStops", []):
        driver_id = ps["driverId"]
        raw_dur = ps["duration"]
        try:
            if ":" in str(raw_dur):
                # Format "mm:ss.sss" — convert to seconds
                parts = str(raw_dur).split(":")
                duration = float(parts[0]) * 60 + float(parts[1])
            else:
                duration = float(raw_dur)
        except (ValueError, IndexError):
            continue  # Skip malformed pit stop entries
        # Only include reasonable pit stops (< 60s, exclude drive-throughs etc.)
        if duration < 60:
            pitstops_by_driver.setdefault(driver_id, []).append(duration)

    return pitstops_by_driver


def parse_sprint_results(data: dict) -> list[dict]:
    """Parse Jolpica sprint.json into a flat list of sprint results."""
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []

    results = []
    for r in races[0].get("SprintResults", []):
        driver_id = r["Driver"]["driverId"]
        position = int(r["position"])
        grid = int(r["grid"])
        status = r.get("status", "")
        position_text = r.get("positionText", "")
        laps = int(r.get("laps", 0))

        # Same classification-aware rule as the race parser: numeric positionText
        # = classified finisher (even if it retired late), "R" = true DNF.
        # Do not infer DNS from laps==0; a first-lap retirement also has zero
        # completed laps.
        is_dsq = position_text == "D" or status == "Disqualified"
        is_dns = position_text == "W" or status == "Did not start"
        is_dnf = (position_text == "R") and not is_dns and not is_dsq

        fastest_lap = r.get("FastestLap", {})
        is_fastest_lap = fastest_lap.get("rank") == "1"

        results.append({
            "jolpica_driver_id": driver_id,
            "jolpica_constructor_id": r["Constructor"]["constructorId"],
            "position": position,
            "grid": grid,
            "status": status,
            "is_dnf": is_dnf,
            "is_dsq": is_dsq,
            "is_dns": is_dns,
            "is_fastest_lap": is_fastest_lap,
            "laps": laps,
        })

    return results


def get_pitstops_from_post_race(round_num: int, jolpica_to_abbrev: dict) -> dict:
    """Fallback: load pitstop durations from post_race_analysis.json.

    Returns dict mapping jolpica_driver_id -> list of durations.
    """
    analysis = load_post_race_analysis(round_num)
    if not analysis:
        return {}

    # Build reverse map: abbrev -> jolpica
    abbrev_to_jolpica = {v: k for k, v in jolpica_to_abbrev.items()}

    pitstops = {}
    by_driver = analysis.get("pitstops", {}).get("by_driver", {})
    for abbrev, stops in by_driver.items():
        jolpica_id = abbrev_to_jolpica.get(abbrev)
        if jolpica_id:
            pitstops[jolpica_id] = [s["duration"] for s in stops]

    return pitstops


# ==============================================================================
# Core calculation
# ==============================================================================

def calculate_actual_fantasy_points(round_num: int, year: int = CURRENT_SEASON) -> Optional[dict]:
    """Calculate actual fantasy points for a given round.

    Returns the full output dict, or None if data is unavailable.
    """
    is_sprint = round_num in SPRINT_ROUNDS_2026

    # -- Load mappings and seed data --
    jolpica_to_abbrev, id_data, jolpica_constructor_map = load_id_maps()
    drivers_info = load_drivers_info()
    constructors_info = load_constructors_info()
    driver_prices, constructor_prices = load_fantasy_prices()
    dotd_winner = load_dotd_winner(round_num)
    if dotd_winner:
        print(f"  Driver of the Day: {dotd_winner} (+{RACE_DRIVER_OF_THE_DAY_BONUS} pts)")
    else:
        # A completed round with no DOTD entry silently costs the winner +10 and
        # breaks their constructor/accuracy figures — warn loudly (this gap went
        # unnoticed for 4 rounds). Only warn for a round whose race has happened.
        if is_race_completed(round_num, year):
            print("  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"  !!  NO Driver of the Day recorded for completed round {round_num}.")
            print(f"  !!  The DOTD winner is missing +{RACE_DRIVER_OF_THE_DAY_BONUS} pts.")
            print(f"  !!  Add it to data/seed/dotd_winners.json and re-run this script.")
            print(f"  !!  Source: formula1.com/en/results/2026/awards/driver-of-the-day")
            print("  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    # Official F1 Fantasy pit-stop points (ground truth; overrides our unreliable
    # OpenF1 computation per constructor when recorded for this round).
    official_pitstop_points = load_official_pitstop_points()

    # -- Load Jolpica race results (required) --
    results_data = load_jolpica_json(year, round_num, "results.json")
    if not results_data:
        # Try post_race_analysis as fallback
        analysis = load_post_race_analysis(round_num)
        if not analysis:
            print(f"  No results data found for round {round_num}")
            return None
        return calculate_from_post_race_analysis(round_num, year, analysis)

    race_results, race_name = parse_race_results(results_data)
    if not race_results:
        print(f"  No race results parsed for round {round_num}")
        return None

    # -- Load qualifying --
    quali_data = load_jolpica_json(year, round_num, "qualifying.json")
    quali_map = parse_qualifying(quali_data) if quali_data else {}

    # -- Load pitstops --
    # Prefer OpenF1 stop_duration (actual stationary "wheels up" time, ~2-4s)
    # over Jolpica duration (pit lane transit time, ~17-25s).
    # F1 Fantasy scoring is based on stationary time.
    openf1_pitstops = load_openf1_pitstops(year, round_num)
    pitstop_source = None

    if openf1_pitstops:
        pitstop_source = "openf1_stop_duration"
        print(f"  Using OpenF1 stationary pit stop times ({len(openf1_pitstops)} drivers)")
    else:
        pitstop_source = "jolpica_lane_duration"
        pitstops_data = load_jolpica_json(year, round_num, "pitstops.json")
        if pitstops_data:
            pitstops_by_driver = parse_pitstops(pitstops_data)
        else:
            pitstops_by_driver = get_pitstops_from_post_race(round_num, jolpica_to_abbrev)
        print(f"  Warning: Using Jolpica lane transit times (not stationary times)")
        print(f"    Pit stop scoring may be inaccurate — run 13_fetch_openf1_overtakes.py to get stop_duration")

    # -- Load sprint (if applicable) --
    sprint_results = []
    if is_sprint:
        sprint_data = load_jolpica_json(year, round_num, "sprint.json")
        if sprint_data:
            sprint_results = parse_sprint_results(sprint_data)

    # Sprint lookup by jolpica driver ID
    sprint_map = {sr["jolpica_driver_id"]: sr for sr in sprint_results}

    # -- Load detected overtakes (from 12_count_overtakes.py) --
    detected_race_ot, detected_sprint_ot = load_detected_overtakes(year, round_num)
    if detected_race_ot:
        print(f"  Using detected overtakes for race ({len(detected_race_ot)} drivers)")
    if detected_sprint_ot:
        print(f"  Using detected overtakes for sprint ({len(detected_sprint_ot)} drivers)")
    # -- Manual overtakes.csv overrides detected counts when present --
    seed_race_ot, seed_sprint_ot = load_seed_overtakes(year, round_num)
    if seed_race_ot:
        print(f"  Manual overtakes.csv override for race ({len(seed_race_ot)} drivers)")
        detected_race_ot = {**detected_race_ot, **seed_race_ot}
    if seed_sprint_ot:
        print(f"  Manual overtakes.csv override for sprint ({len(seed_sprint_ot)} drivers)")
        detected_sprint_ot = {**detected_sprint_ot, **seed_sprint_ot}

    # -- Build constructor -> pitstop times mapping --
    constructor_pitstops: dict[str, list[float]] = {}
    if openf1_pitstops:
        # Use OpenF1 stop_duration (stationary time) keyed by abbreviation
        for abbrev, times in openf1_pitstops.items():
            if abbrev in drivers_info:
                cid = drivers_info[abbrev]["constructor_id"]
                constructor_pitstops.setdefault(cid, []).extend(times)
    else:
        # Fallback: Jolpica lane transit times keyed by jolpica driver ID
        for jol_driver_id, times in pitstops_by_driver.items():
            abbrev = jolpica_to_abbrev.get(jol_driver_id)
            if abbrev and abbrev in drivers_info:
                cid = drivers_info[abbrev]["constructor_id"]
                constructor_pitstops.setdefault(cid, []).extend(times)

    # Find fastest pitstop across all teams
    all_pitstop_times = []
    for times in constructor_pitstops.values():
        all_pitstop_times.extend(times)
    global_fastest_pitstop = min(all_pitstop_times) if all_pitstop_times else 999.0

    # -- Calculate driver fantasy points --
    driver_outputs = []
    driver_points_by_abbrev = {}  # for constructor calculation

    for r in race_results:
        jol_id = r["jolpica_driver_id"]
        abbrev = jolpica_to_abbrev.get(jol_id, r["code"])
        info = drivers_info.get(abbrev, {})
        constructor_id = jolpica_constructor_map.get(r["jolpica_constructor_id"],
                                                     r["jolpica_constructor_id"])
        full_name = f"{info.get('first_name', r['given_name'])} {info.get('last_name', r['family_name'])}"

        # Qualifying
        quali = quali_map.get(jol_id, {})
        quali_position = quali.get("position")
        quali_best_session = quali.get("best_session", "Q1")
        # No valid Q1 time = did not classify in qualifying -> -5 (not position pts)
        quali_no_time = quali.get("no_time_set", False)

        if r["is_dns"]:
            # DNS drivers: keep qualifying points (they did qualify), but race = -20 same as DNF
            if quali_position is not None:
                quali_pts = calc_qualifying_points_driver(quali_position, no_time_set=quali_no_time)
            else:
                quali_pts = QUALIFYING_NC_DSQ_PENALTY
            race_pts = RACE_DNF_DSQ_PENALTY  # DNS = same penalty as DNF (-20)
            race_position = None
            positions_gained = 0
            overtakes = 0
        elif r["is_dsq"]:
            quali_pts = calc_qualifying_points_driver(quali_position, is_dsq=True)
            race_pts = RACE_DNF_DSQ_PENALTY
            race_position = None
            positions_gained = 0
            overtakes = 0
        elif r["is_dnf"]:
            if quali_position is not None:
                quali_pts = calc_qualifying_points_driver(quali_position, no_time_set=quali_no_time)
            else:
                quali_pts = QUALIFYING_NC_DSQ_PENALTY
            # Official F1 Fantasy: a retired driver KEEPS overtake points for
            # passes made before retiring (proven exactly by R10 retirees: each
            # scored -20 + 3 overtakes = -17). Resolve from official csv
            # (uncapped) / telemetry (capped); NO estimation fallback for a car
            # that didn't finish — an unrecorded retiree gets 0.
            resolved_ot = _resolve_overtakes(abbrev, detected_race_ot, seed_race_ot, MAX_RACE_OVERTAKES)
            overtakes = resolved_ot if resolved_ot is not None else 0
            race_pts = RACE_DNF_DSQ_PENALTY + overtakes * RACE_OVERTAKE_POINTS
            race_position = None
            positions_gained = 0
        else:
            # Normal finisher (includes lapped drivers)
            if quali_position is not None:
                quali_pts = calc_qualifying_points_driver(quali_position, no_time_set=quali_no_time)
            else:
                # Driver not in qualifying data = Not Classified (NC) = -5 penalty
                # This happens when a driver didn't set a time, was excluded,
                # or had their qualifying times deleted (e.g. penalty)
                quali_pts = QUALIFYING_NC_DSQ_PENALTY

            race_position = r["position"]
            positions_gained = r["grid"] - race_position
            # Overtakes: official csv (uncapped) > telemetry-detected (capped) >
            # calibrated estimate. Caps apply ONLY to telemetry (it over-counts
            # pit-cycle/SC/blue-flag passes); official csv counts are used verbatim.
            resolved_ot = _resolve_overtakes(abbrev, detected_race_ot, seed_race_ot, MAX_RACE_OVERTAKES)
            if resolved_ot is not None:
                overtakes = resolved_ot
            else:
                # Fallback estimate — bases aligned with 07_calculate_fantasy.py
                # (retuned 2026-06-28): base[bucket] + positions_gained.
                pos_gained = max(0, positions_gained)
                if r["grid"] <= 3:
                    ot_base = 6
                elif r["grid"] <= 6:
                    ot_base = 4
                elif r["grid"] <= 12:
                    ot_base = 4
                else:
                    ot_base = 2
                overtakes = min(ot_base + pos_gained, MAX_RACE_OVERTAKES)

            race_pts = calc_race_points_driver(
                finish_position=race_position,
                grid_position=r["grid"],
                overtakes=overtakes,
                is_fastest_lap=r["is_fastest_lap"],
                is_dnf=False,
                is_dsq=False,
            )

        # Sprint points
        sprint_pts = 0
        sprint_position = None
        sprint_grid = None
        sprint_overtakes = 0
        sprint_is_dsq = False
        if is_sprint and jol_id in sprint_map:
            sr = sprint_map[jol_id]
            sprint_grid = sr["grid"]
            sprint_is_dsq = bool(sr.get("is_dsq"))
            if sr["is_dns"]:
                sprint_pts = SPRINT_DNF_DSQ_PENALTY  # DNS = same penalty as DNF (-10)
                sprint_position = None
            elif sr["is_dsq"]:
                sprint_pts = calc_sprint_points_driver(
                    finish_position=None, grid_position=sr["grid"], is_dsq=True,
                )
                sprint_position = None
            elif sr["is_dnf"]:
                # Sprint DNF keeps overtake credit (same rule as the race). No
                # estimation fallback for a retiree; official csv uncapped.
                resolved_sp = _resolve_overtakes(abbrev, detected_sprint_ot, seed_sprint_ot, MAX_SPRINT_OVERTAKES)
                sprint_overtakes = resolved_sp if resolved_sp is not None else 0
                sprint_pts = SPRINT_DNF_DSQ_PENALTY + sprint_overtakes * SPRINT_OVERTAKE_POINTS
                sprint_position = None
            else:
                sprint_position = sr["position"]
                # Official csv (uncapped) > detected (capped) > estimate.
                resolved_sp = _resolve_overtakes(abbrev, detected_sprint_ot, seed_sprint_ot, MAX_SPRINT_OVERTAKES)
                if resolved_sp is not None:
                    sprint_overtakes = resolved_sp
                else:
                    sprint_pos_gained = max(0, sr["grid"] - sr["position"])
                    # Sprint bases aligned with estimate_sprint_overtakes() in 07
                    # (retuned 2026-06-28): base[bucket] + positions_gained.
                    if sr["grid"] <= 3:
                        sprint_ot_base = 2
                    elif sr["grid"] <= 6:
                        sprint_ot_base = 2
                    elif sr["grid"] <= 12:
                        sprint_ot_base = 3
                    else:
                        sprint_ot_base = 2
                    sprint_overtakes = min(sprint_ot_base + sprint_pos_gained, MAX_SPRINT_OVERTAKES)
                sprint_pts = calc_sprint_points_driver(
                    finish_position=sr["position"],
                    grid_position=sr["grid"],
                    overtakes=sprint_overtakes,
                    is_fastest_lap=sr["is_fastest_lap"],
                )

        # Separate point components for output (must sum to race_pts)
        if r["is_dns"] or r["is_dsq"]:
            position_pts = 0
            overtake_pts = 0
            fastest_lap_pts = 0
            dnf_penalty = RACE_DNF_DSQ_PENALTY  # DNS/DSQ = -20, no overtake credit
            race_finish_pts = 0
        elif r["is_dnf"]:
            # Retiree keeps overtake points; components still sum to race_pts
            # (-20 penalty + overtakes).
            position_pts = 0
            overtake_pts = overtakes
            fastest_lap_pts = 0
            dnf_penalty = RACE_DNF_DSQ_PENALTY
            race_finish_pts = 0
        else:
            race_finish_pts = RACE_POSITION_POINTS.get(race_position, 0)
            position_pts = positions_gained * RACE_POSITIONS_GAINED_PER_POS if positions_gained > 0 else positions_gained
            overtake_pts = overtakes
            fastest_lap_pts = RACE_FASTEST_LAP_BONUS if r["is_fastest_lap"] else 0
            dnf_penalty = 0

        # Driver of the Day bonus (driver only, not constructors)
        is_dotd = (dotd_winner is not None and abbrev == dotd_winner)
        dotd_pts = RACE_DRIVER_OF_THE_DAY_BONUS if is_dotd else 0

        # DOTD is already included in calc_race_points_driver via is_driver_of_the_day param,
        # but we calculated race_pts without it above. Add it now.
        race_pts_with_dotd = race_pts + dotd_pts
        total_pts = quali_pts + race_pts_with_dotd + sprint_pts
        price = driver_prices.get(abbrev, 0.0)
        ppm = round(total_pts / price, 2) if price > 0 else 0.0

        driver_entry = {
            "driver_id": abbrev,
            "name": full_name,
            "constructor": constructor_id,
            "quali_position": quali_position,
            "race_position": race_position,
            "grid": r["grid"],
            "status": r["status"],
            "is_dnf": r["is_dnf"],
            "is_dsq": r["is_dsq"],
            "is_dns": r["is_dns"],
            "quali_no_time": quali_no_time,   # NC in qualifying (no valid Q1 time)
            "sprint_is_dsq": sprint_is_dsq,   # disqualified from the sprint
            "is_fastest_lap": r["is_fastest_lap"],
            "is_dotd": is_dotd,
            "overtakes": overtakes,
            "overtake_source": (
                "none" if (r["is_dsq"] or r["is_dns"])
                else "official_csv" if abbrev in seed_race_ot
                else "detected" if abbrev in detected_race_ot
                else "estimated"
            ),
            "positions_gained": positions_gained,
            "quali_points": quali_pts,
            "race_points": race_pts_with_dotd,
            "race_finish_points": race_finish_pts,
            "position_points": position_pts,
            "overtake_points": overtake_pts,
            "fastest_lap_points": fastest_lap_pts,
            "dotd_points": dotd_pts,
            "dnf_penalty": dnf_penalty,
            "sprint_points": sprint_pts,
            "total_points": total_pts,
            "price": price,
            "ppm": ppm,
        }

        if is_sprint:
            driver_entry["sprint_position"] = sprint_position
            driver_entry["sprint_grid"] = sprint_grid

        driver_outputs.append(driver_entry)
        driver_points_by_abbrev[abbrev] = driver_entry

    # Sort drivers by total points descending
    driver_outputs.sort(key=lambda x: x["total_points"], reverse=True)

    # -- Calculate constructor fantasy points --
    constructor_outputs = []

    # Map constructor -> driver abbreviations from seed data
    constructor_drivers: dict[str, list[str]] = {}
    for d in drivers_info.values():
        cid = d["constructor_id"]
        constructor_drivers.setdefault(cid, []).append(d["driver_id"])

    for cid, cinfo in constructors_info.items():
        c_drivers = constructor_drivers.get(cid, [])
        if not c_drivers:
            continue

        d1_abbrev = c_drivers[0] if len(c_drivers) > 0 else ""
        d2_abbrev = c_drivers[1] if len(c_drivers) > 1 else ""

        d1 = driver_points_by_abbrev.get(d1_abbrev, {})
        d2 = driver_points_by_abbrev.get(d2_abbrev, {})

        # Qualifying: combined driver quali points + bonus
        d1_quali = d1.get("quali_points", 0)
        d2_quali = d2.get("quali_points", 0)
        combined_quali = d1_quali + d2_quali

        # Quali bonus based on the qualifying SEGMENT each driver reached (their
        # quali position), not on which Q-times they set. A driver who reaches Q3
        # but sets no Q3 lap still counts as Q3 for the teamwork bonus (verified
        # vs official: LEC R9 P10, no Q3 time -> Ferrari both-Q3 +10).
        d1_session = _quali_session_from_position(d1.get("quali_position"))
        d2_session = _quali_session_from_position(d2.get("quali_position"))

        quali_bonus = calc_constructor_quali_bonus(d1_session, d2_session)

        # Race: combined driver race points (excluding DOTD)
        d1_race = d1.get("race_points", 0) - d1.get("dotd_points", 0)
        d2_race = d2.get("race_points", 0) - d2.get("dotd_points", 0)
        combined_race = d1_race + d2_race

        # Sprint: combined
        combined_sprint = d1.get("sprint_points", 0) + d2.get("sprint_points", 0)

        # Pitstop points — prefer the manually-recorded OFFICIAL F1 Fantasy value
        # (data/seed/pitstop_points.json) over our OpenF1 computation, which is
        # unreliable (null stationary times on SC/VSC stops, 1dp rounding cause
        # both misses and over-counts). Fall back to the OpenF1 computation only
        # when no official figure is recorded for this round.
        official_pit_round = official_pitstop_points.get(round_num, {})
        if cid in official_pit_round:
            pitstop_pts = official_pit_round[cid]
            pitstop_source = "official"
        else:
            team_pitstop_times = constructor_pitstops.get(cid, [])
            pitstop_pts = calc_pitstop_points_constructor(team_pitstop_times)
            team_best = min(team_pitstop_times) if team_pitstop_times else 999.0
            is_fastest_pit = (team_best == global_fastest_pitstop and team_best < 999.0)
            pitstop_pts += calc_fastest_pitstop_bonus(is_fastest_pit)
            pitstop_pts += calc_world_record_pitstop_bonus(team_best)
            pitstop_source = "computed"

        # Constructor DSQ / not-classified penalties. F1 Fantasy applies a
        # per-driver, per-session penalty to the CONSTRUCTOR (on top of summing
        # the drivers' own negative points) when a driver is disqualified or does
        # not classify: quali NC/DSQ -5, sprint DSQ -10, race DSQ -20. Verified vs
        # official R6: BOR sprint DSQ -> audi -10; HAD quali NC -> red_bull -5.
        # (These are the only DSQ/NC events across 2026 R1-R10.)
        dsq_penalty = 0
        for d in (d1, d2):
            if d.get("quali_no_time") or d.get("is_quali_dsq"):
                dsq_penalty += CONSTRUCTOR_QUALI_DSQ_PENALTY
            if d.get("sprint_is_dsq"):
                dsq_penalty += CONSTRUCTOR_SPRINT_DSQ_PENALTY
            if d.get("is_dsq"):  # race DSQ
                dsq_penalty += CONSTRUCTOR_RACE_DSQ_PENALTY

        total_constructor = (combined_quali + quali_bonus + combined_race
                             + pitstop_pts + combined_sprint + dsq_penalty)
        c_price = constructor_prices.get(cid, 0.0)
        c_ppm = round(total_constructor / c_price, 2) if c_price > 0 else 0.0

        constructor_entry = {
            "constructor_id": cid,
            "name": cinfo["name"],
            "driver_1": d1_abbrev,
            "driver_2": d2_abbrev,
            "quali_points": combined_quali,
            "quali_bonus": quali_bonus,
            "race_points": combined_race,
            "sprint_points": combined_sprint if is_sprint else 0,
            "pitstop_points": pitstop_pts,
            "pitstop_points_source": pitstop_source,
            "total_points": total_constructor,
            "price": c_price,
            "ppm": c_ppm,
        }

        constructor_outputs.append(constructor_entry)

    # Sort constructors by total points
    constructor_outputs.sort(key=lambda x: x["total_points"], reverse=True)

    return {
        "round": round_num,
        "race": race_name,
        "season": year,
        "is_sprint_weekend": is_sprint,
        "drivers": driver_outputs,
        "constructors": constructor_outputs,
    }


def calculate_from_post_race_analysis(
    round_num: int,
    year: int,
    analysis: dict,
) -> Optional[dict]:
    """Fallback calculation using only post_race_analysis.json when Jolpica data
    is unavailable. Less accurate (no quali session detail, no fastest lap from
    Jolpica), but still produces reasonable fantasy point estimates."""

    is_sprint = round_num in SPRINT_ROUNDS_2026
    jolpica_to_abbrev, _, _ = load_id_maps()
    drivers_info = load_drivers_info()
    constructors_info = load_constructors_info()
    driver_prices, constructor_prices = load_fantasy_prices()

    race_name = analysis.get("race", "Unknown")
    results = analysis.get("results", [])

    # Load detected overtakes
    detected_race_ot, detected_sprint_ot = load_detected_overtakes(year, round_num)
    if detected_race_ot:
        print(f"  Using detected overtakes for race ({len(detected_race_ot)} drivers)")
    # Manual overtakes.csv overrides detected counts when present
    seed_race_ot, seed_sprint_ot = load_seed_overtakes(year, round_num)
    if seed_race_ot:
        print(f"  Manual overtakes.csv override for race ({len(seed_race_ot)} drivers)")
        detected_race_ot = {**detected_race_ot, **seed_race_ot}
    if seed_sprint_ot:
        print(f"  Manual overtakes.csv override for sprint ({len(seed_sprint_ot)} drivers)")
        detected_sprint_ot = {**detected_sprint_ot, **seed_sprint_ot}

    driver_outputs = []
    driver_points_by_abbrev = {}

    for r in results:
        abbrev = r["driver_id"]
        info = drivers_info.get(abbrev, {})
        constructor_id = r.get("constructor_id", info.get("constructor_id", ""))
        full_name = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()

        grid = r.get("grid", 22)
        finish = r.get("finish_position")
        status = r.get("status", "")
        is_finished = r.get("is_finished", False)

        is_dns = status == "Did not start"
        is_dnf = status == "Retired" and not is_dns
        is_dsq = status == "Disqualified"
        # Lapped drivers are finishers
        if status == "Lapped":
            is_dnf = False

        # Use grid as rough quali position (post_race_analysis doesn't have quali)
        quali_position = grid
        quali_pts = calc_qualifying_points_driver(quali_position)

        if is_dns:
            race_pts = RACE_DNF_DSQ_PENALTY  # DNS = same penalty as DNF (-20)
            race_position = None
            positions_gained = 0
            overtakes = 0
        elif is_dnf or is_dsq:
            race_pts = RACE_DNF_DSQ_PENALTY
            race_position = None
            positions_gained = 0
            overtakes = 0
        else:
            # For lapped drivers, use the position from results order
            race_position = finish if finish else results.index(r) + 1
            positions_gained = grid - race_position
            # Use detected overtakes if available
            if abbrev in detected_race_ot:
                overtakes = detected_race_ot[abbrev]
            else:
                pos_gained_fb = max(0, positions_gained)
                if grid <= 3:
                    ot_base_fb = 2
                elif grid <= 6:
                    ot_base_fb = 4
                elif grid <= 12:
                    ot_base_fb = 6
                else:
                    ot_base_fb = 7
                overtakes = ot_base_fb + pos_gained_fb
            race_pts = calc_race_points_driver(
                finish_position=race_position,
                grid_position=grid,
                overtakes=overtakes,
            )

        total_pts = quali_pts + race_pts
        price = driver_prices.get(abbrev, 0.0)
        ppm = round(total_pts / price, 2) if price > 0 else 0.0

        entry = {
            "driver_id": abbrev,
            "name": full_name,
            "constructor": constructor_id,
            "quali_position": quali_position,
            "race_position": race_position,
            "grid": grid,
            "status": status,
            "is_dnf": is_dnf,
            "is_dsq": is_dsq,
            "is_dns": is_dns,
            "is_fastest_lap": False,
            "overtakes": overtakes,
            "positions_gained": positions_gained,
            "quali_points": quali_pts,
            "race_points": race_pts,
            "race_finish_points": 0,
            "position_points": 0,
            "overtake_points": overtakes,
            "fastest_lap_points": 0,
            "dotd_points": 0,
            "dnf_penalty": RACE_DNF_DSQ_PENALTY if (is_dnf or is_dsq) else 0,
            "sprint_points": 0,
            "total_points": total_pts,
            "price": price,
            "ppm": ppm,
        }
        driver_outputs.append(entry)
        driver_points_by_abbrev[abbrev] = entry

    driver_outputs.sort(key=lambda x: x["total_points"], reverse=True)

    # Constructors (simplified without detailed pitstop/quali session data)
    constructor_drivers: dict[str, list[str]] = {}
    for d in drivers_info.values():
        constructor_drivers.setdefault(d["constructor_id"], []).append(d["driver_id"])

    constructor_outputs = []
    for cid, cinfo in constructors_info.items():
        c_drivers = constructor_drivers.get(cid, [])
        d1_abbrev = c_drivers[0] if len(c_drivers) > 0 else ""
        d2_abbrev = c_drivers[1] if len(c_drivers) > 1 else ""
        d1 = driver_points_by_abbrev.get(d1_abbrev, {})
        d2 = driver_points_by_abbrev.get(d2_abbrev, {})

        combined_quali = d1.get("quali_points", 0) + d2.get("quali_points", 0)
        combined_race = d1.get("race_points", 0) + d2.get("race_points", 0)

        total = combined_quali + combined_race
        c_price = constructor_prices.get(cid, 0.0)
        c_ppm = round(total / c_price, 2) if c_price > 0 else 0.0

        constructor_outputs.append({
            "constructor_id": cid,
            "name": cinfo["name"],
            "driver_1": d1_abbrev,
            "driver_2": d2_abbrev,
            "quali_points": combined_quali,
            "quali_bonus": 0,
            "race_points": combined_race,
            "sprint_points": 0,
            "pitstop_points": 0,
            "total_points": total,
            "price": c_price,
            "ppm": c_ppm,
        })

    constructor_outputs.sort(key=lambda x: x["total_points"], reverse=True)

    return {
        "round": round_num,
        "race": race_name,
        "season": year,
        "is_sprint_weekend": is_sprint,
        "data_source": "post_race_analysis_fallback",
        "drivers": driver_outputs,
        "constructors": constructor_outputs,
    }


# ==============================================================================
# Predicted vs Actual comparison
# ==============================================================================

def compare_predicted_vs_actual(round_num: int, actual: dict) -> None:
    """Print a comparison of predicted vs actual points if predicted data exists."""
    try:
        import pandas as pd
    except ImportError:
        print("  (pandas not available, skipping comparison)")
        return

    pred_path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points.parquet"
    if not pred_path.exists():
        print(f"\n  No predicted fantasy points found at {pred_path}")
        print("  Skipping predicted vs actual comparison.")
        return

    pred_df = pd.read_parquet(pred_path)

    print(f"\n{'=' * 80}")
    print("PREDICTED vs ACTUAL COMPARISON")
    print(f"{'=' * 80}")

    # Driver comparison
    actual_drivers = {d["driver_id"]: d for d in actual["drivers"]}

    print(f"\n{'Driver':<6} {'Pred Quali':>10} {'Act Quali':>10} {'Pred Race':>10} "
          f"{'Act Race':>10} {'Pred Total':>11} {'Act Total':>10} {'Delta':>7}")
    print("-" * 80)

    deltas = []
    for _, row in pred_df.iterrows():
        abbrev = row.get("driver_abbrev", "")
        if abbrev not in actual_drivers:
            continue
        act = actual_drivers[abbrev]

        pred_quali = row.get("expected_quali_pts", 0)
        pred_race = row.get("expected_race_pts", 0)
        pred_total = row.get("total_expected_fantasy_points", 0)

        act_quali = act.get("quali_points", 0)
        act_race = act.get("race_points", 0)
        act_total = act.get("total_points", 0)
        delta = act_total - pred_total

        deltas.append(abs(delta))

        print(f"{abbrev:<6} {pred_quali:>10.1f} {act_quali:>10} {pred_race:>10.1f} "
              f"{act_race:>10} {pred_total:>11.1f} {act_total:>10} {delta:>+7.1f}")

    if deltas:
        print("-" * 80)
        mae = sum(deltas) / len(deltas)
        print(f"Mean Absolute Error: {mae:.1f} points")

    # Constructor comparison
    pred_c_path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points_constructors.parquet"
    if pred_c_path.exists():
        pred_c_df = pd.read_parquet(pred_c_path)
        actual_constructors = {c["constructor_id"]: c for c in actual["constructors"]}

        print(f"\n{'Constructor':<15} {'Pred Total':>11} {'Act Total':>10} {'Delta':>7}")
        print("-" * 50)

        for _, row in pred_c_df.iterrows():
            cid = row.get("constructor_id", "")
            if cid not in actual_constructors:
                continue
            act = actual_constructors[cid]
            pred_total = row.get("total_expected_fantasy_points", 0)
            act_total = act.get("total_points", 0)
            delta = act_total - pred_total
            print(f"{cid:<15} {pred_total:>11.1f} {act_total:>10} {delta:>+7.1f}")


# ==============================================================================
# Save outputs
# ==============================================================================

def save_outputs(output: dict, round_num: int) -> None:
    """Save actual fantasy points to predictions dir and web dir."""
    # Save to predictions directory
    pred_dir = PREDICTIONS_DIR / f"round{round_num}"
    pred_dir.mkdir(parents=True, exist_ok=True)
    pred_path = pred_dir / "actual_fantasy_points.json"
    with open(pred_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved -> {pred_path}")

    # Save to web directory
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    web_path = WEB_DATA_DIR / f"actual_round{round_num}.json"
    with open(web_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved -> {web_path}")


# ==============================================================================
# Display
# ==============================================================================

def print_summary(output: dict) -> None:
    """Print a formatted summary of the actual fantasy points."""
    print(f"\n{'=' * 80}")
    print(f"ACTUAL FANTASY POINTS — Round {output['round']}: {output['race']}")
    print(f"{'=' * 80}")

    if output.get("data_source") == "post_race_analysis_fallback":
        print("  [Using post_race_analysis fallback — limited accuracy]")

    # Drivers
    print(f"\n{'Pos':>3} {'Driver':<6} {'Team':<15} {'Quali':>5} {'Grid':>4} "
          f"{'Race':>4} {'Status':<12} {'Q Pts':>5} {'R Pts':>5} "
          f"{'Spr':>4} {'Total':>6} {'Price':>6} {'PPM':>5}")
    print("-" * 100)

    for i, d in enumerate(output["drivers"], 1):
        race_pos = d["race_position"] if d["race_position"] is not None else "-"
        sprint_pts = d.get("sprint_points", 0)
        fl_marker = " *" if d["is_fastest_lap"] else ""
        status_short = d["status"][:12]
        print(f"{i:>3} {d['driver_id']:<6} {d['constructor']:<15} "
              f"P{d['quali_position'] or '-':<4} P{d['grid']:<3} "
              f"P{str(race_pos):<3} {status_short:<12} "
              f"{d['quali_points']:>5} {d['race_points']:>5} "
              f"{sprint_pts:>4} {d['total_points']:>6} "
              f"{d['price']:>6.1f} {d['ppm']:>5.2f}{fl_marker}")

    print(f"\n  * = Fastest Lap")

    # Constructors
    print(f"\n{'Pos':>3} {'Constructor':<15} {'D1':<5} {'D2':<5} "
          f"{'Quali':>5} {'Bonus':>5} {'Race':>5} {'Pit':>4} "
          f"{'Spr':>4} {'Total':>6} {'Price':>6} {'PPM':>5}")
    print("-" * 85)

    for i, c in enumerate(output["constructors"], 1):
        sprint_pts = c.get("sprint_points", 0)
        print(f"{i:>3} {c['name']:<15} {c['driver_1']:<5} {c['driver_2']:<5} "
              f"{c['quali_points']:>5} {c['quali_bonus']:>5} {c['race_points']:>5} "
              f"{c['pitstop_points']:>4} {sprint_pts:>4} {c['total_points']:>6} "
              f"{c['price']:>6.1f} {c['ppm']:>5.2f}")


# ==============================================================================
# Main
# ==============================================================================

def get_completed_rounds(year: int) -> list[int]:
    """Determine which rounds have been completed (have results data)."""
    completed = []
    for rnd in range(1, 25):
        if rnd in CANCELLED_ROUNDS_2026:
            continue
        # Check for Jolpica results or post_race_analysis
        jolpica_path = JOLPICA_RAW_DIR / f"year{year}" / f"round{rnd}" / "results.json"
        analysis_path = PREDICTIONS_DIR / f"round{rnd}" / "post_race_analysis.json"
        if jolpica_path.exists() or analysis_path.exists():
            completed.append(rnd)
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate actual F1 Fantasy points from real race results"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--round", type=int, help="Round number to process")
    group.add_argument("--all", action="store_true", help="Process all completed rounds")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON, help="Season year")
    args = parser.parse_args()

    print("=" * 80)
    print(f"BoxBoxF1Fantasy — Actual Fantasy Points Calculator ({args.year})")
    print("=" * 80)

    if args.all:
        rounds = get_completed_rounds(args.year)
        if not rounds:
            print("No completed rounds found.")
            return
        print(f"Processing {len(rounds)} completed round(s): {rounds}")
    else:
        if args.round in CANCELLED_ROUNDS_2026:
            print(f"Round {args.round} is cancelled.")
            return
        rounds = [args.round]

    for round_num in rounds:
        print(f"\n--- Round {round_num} ---")
        output = calculate_actual_fantasy_points(round_num, args.year)

        if output is None:
            print(f"  Skipping round {round_num} (no data available)")
            continue

        print_summary(output)
        save_outputs(output, round_num)
        compare_predicted_vs_actual(round_num, output)

    print(f"\n{'=' * 80}")
    print("Done.")


if __name__ == "__main__":
    main()
