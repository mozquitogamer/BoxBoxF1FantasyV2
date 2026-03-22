"""
Weather Forecast Fetcher — Open-Meteo API (free, no key required)

Fetches hourly precipitation probability and weather codes for the
upcoming race weekend (Friday–Sunday) and saves to website JSON.

Open-Meteo provides:
  - precipitation_probability (0-100%)
  - weathercode (WMO standard codes)
  - temperature_2m, windspeed_10m, etc.

Usage:
    python pipeline/weather_forecast.py              # auto-detect next round
    python pipeline/weather_forecast.py --round 3    # specific round

Output:
    web/public/data/weather.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import CURRENT_SEASON, SEED_DIR, WEB_DATA_DIR
from config.circuit_coordinates import get_circuit_location

# WMO Weather interpretation codes → labels and icons
WMO_CODES = {
    0:  ("Clear sky", "clear"),
    1:  ("Mainly clear", "clear"),
    2:  ("Partly cloudy", "cloudy"),
    3:  ("Overcast", "overcast"),
    45: ("Fog", "fog"),
    48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "drizzle"),
    53: ("Moderate drizzle", "drizzle"),
    55: ("Dense drizzle", "drizzle"),
    56: ("Light freezing drizzle", "drizzle"),
    57: ("Dense freezing drizzle", "drizzle"),
    61: ("Slight rain", "rain"),
    63: ("Moderate rain", "rain"),
    65: ("Heavy rain", "heavy_rain"),
    66: ("Light freezing rain", "rain"),
    67: ("Heavy freezing rain", "heavy_rain"),
    71: ("Slight snow", "snow"),
    73: ("Moderate snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Slight rain showers", "rain"),
    81: ("Moderate rain showers", "rain"),
    82: ("Violent rain showers", "heavy_rain"),
    85: ("Slight snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunderstorm"),
    96: ("Thunderstorm with slight hail", "thunderstorm"),
    99: ("Thunderstorm with heavy hail", "thunderstorm"),
}


def load_race_calendar() -> list[dict]:
    """Load 2026 race calendar."""
    with open(SEED_DIR / "races.json") as f:
        return json.load(f)["races"]


def find_next_round(races: list[dict], target_round: int | None = None) -> dict | None:
    """Find the target round or the next upcoming non-cancelled round."""
    if target_round is not None:
        for r in races:
            if r["round"] == target_round and not r.get("cancelled", False):
                return r
        return None

    today = datetime.now().date()
    for r in races:
        if r.get("cancelled", False):
            continue
        race_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
        # Include races up to 1 day after (for post-race weather check)
        if race_date >= today - timedelta(days=1):
            return r
    return None


def fetch_weather(lat: float, lon: float, timezone: str,
                  start_date: str, end_date: str) -> dict | None:
    """
    Fetch hourly weather from Open-Meteo for a date range.

    Returns raw API response as dict, or None on failure.
    """
    params = (
        f"latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,precipitation_probability,"
        f"precipitation,weathercode,windspeed_10m,windgusts_10m"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
        f"precipitation_sum,precipitation_probability_max,windspeed_10m_max"
        f"&timezone={timezone}"
        f"&start_date={start_date}&end_date={end_date}"
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    print(f"  Fetching: {url[:100]}...")
    try:
        req = Request(url, headers={"User-Agent": "BoxBoxF1Fantasy/1.0"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  ERROR fetching weather: {e}")
        return None


def classify_rain_risk(precip_prob: float) -> str:
    """Classify precipitation probability into risk labels."""
    if precip_prob >= 70:
        return "HIGH"
    elif precip_prob >= 40:
        return "MEDIUM"
    elif precip_prob >= 15:
        return "LOW"
    return "NONE"


def get_weather_icon(code_name: str) -> str:
    """Map weather code category to emoji."""
    icons = {
        "clear": "\u2600\ufe0f",        # ☀️ sunny
        "cloudy": "\u26c5",             # ⛅ partly cloudy
        "overcast": "\u2601\ufe0f",     # ☁️ cloud
        "fog": "\U0001F32B\ufe0f",      # 🌫️ fog
        "drizzle": "\U0001F326\ufe0f",  # 🌦️ sun behind rain
        "rain": "\U0001F327\ufe0f",     # 🌧️ rain
        "heavy_rain": "\u26c8\ufe0f",   # ⛈️ thunder cloud
        "snow": "\u2744\ufe0f",         # ❄️ snowflake
        "thunderstorm": "\u26a1",       # ⚡ lightning
    }
    return icons.get(code_name, "\u2601\ufe0f")


def build_session_schedule(race: dict) -> list[dict]:
    """
    Build the F1 session schedule for a race weekend.
    Returns list of {name, day_label, date, start_hour, end_hour}.

    Friday: FP1/FP2 (or FP1/Sprint Qualifying for sprint)
    Saturday: FP3/Qualifying (or Sprint/Qualifying for sprint)
    Sunday: Race
    """
    race_date = datetime.strptime(race["date"], "%Y-%m-%d")
    friday = race_date - timedelta(days=2)
    saturday = race_date - timedelta(days=1)
    sunday = race_date

    is_sprint = race.get("sprint", False)

    if is_sprint:
        sessions = [
            {"name": "FP1",               "day_label": "Friday",   "date": friday.strftime("%Y-%m-%d"),   "hours": (10, 18)},
            {"name": "Sprint Qualifying",  "day_label": "Friday",   "date": friday.strftime("%Y-%m-%d"),   "hours": (14, 18)},
            {"name": "Sprint",             "day_label": "Saturday", "date": saturday.strftime("%Y-%m-%d"), "hours": (10, 14)},
            {"name": "Qualifying",         "day_label": "Saturday", "date": saturday.strftime("%Y-%m-%d"), "hours": (14, 18)},
            {"name": "Race",               "day_label": "Sunday",   "date": sunday.strftime("%Y-%m-%d"),   "hours": (13, 17)},
        ]
    else:
        sessions = [
            {"name": "FP1",        "day_label": "Friday",   "date": friday.strftime("%Y-%m-%d"),   "hours": (10, 14)},
            {"name": "FP2",        "day_label": "Friday",   "date": friday.strftime("%Y-%m-%d"),   "hours": (14, 18)},
            {"name": "FP3",        "day_label": "Saturday", "date": saturday.strftime("%Y-%m-%d"), "hours": (10, 14)},
            {"name": "Qualifying", "day_label": "Saturday", "date": saturday.strftime("%Y-%m-%d"), "hours": (14, 18)},
            {"name": "Race",       "day_label": "Sunday",   "date": sunday.strftime("%Y-%m-%d"),   "hours": (13, 17)},
        ]

    return sessions


def process_daily_forecast(api_data: dict, target_dates: list[str]) -> list[dict]:
    """Extract daily forecast summaries for target dates."""
    daily = api_data.get("daily", {})
    dates = daily.get("time", [])
    days = []

    for i, d in enumerate(dates):
        if d not in target_dates:
            continue
        wcode = daily.get("weathercode", [None])[i]
        wmo = WMO_CODES.get(wcode, ("Unknown", "cloudy"))

        days.append({
            "date": d,
            "temp_max": daily.get("temperature_2m_max", [None])[i],
            "temp_min": daily.get("temperature_2m_min", [None])[i],
            "precip_probability_max": daily.get("precipitation_probability_max", [None])[i],
            "precip_sum_mm": daily.get("precipitation_sum", [None])[i],
            "wind_max_kmh": daily.get("windspeed_10m_max", [None])[i],
            "weather_description": wmo[0],
            "weather_category": wmo[1],
            "weather_icon": get_weather_icon(wmo[1]),
            "weather_code": wcode,
            "rain_risk": classify_rain_risk(daily.get("precipitation_probability_max", [0])[i] or 0),
        })

    return days


def process_hourly_for_sessions(api_data: dict, sessions: list[dict]) -> list[dict]:
    """Extract hourly weather data aligned to F1 session windows."""
    hourly = api_data.get("hourly", {})
    times = hourly.get("time", [])

    enriched_sessions = []
    for session in sessions:
        session_date = session["date"]
        start_h, end_h = session["hours"]

        # Find hourly indices that fall in this session window
        session_hours = []
        for i, t in enumerate(times):
            if not t.startswith(session_date):
                continue
            hour = int(t[11:13])
            if start_h <= hour < end_h:
                session_hours.append({
                    "hour": hour,
                    "temp": hourly.get("temperature_2m", [None])[i],
                    "humidity": hourly.get("relative_humidity_2m", [None])[i],
                    "precip_prob": hourly.get("precipitation_probability", [None])[i],
                    "precip_mm": hourly.get("precipitation", [None])[i],
                    "windspeed": hourly.get("windspeed_10m", [None])[i],
                    "windgusts": hourly.get("windgusts_10m", [None])[i],
                    "weather_code": hourly.get("weathercode", [None])[i],
                })

        # Aggregate session weather
        if session_hours:
            probs = [h["precip_prob"] for h in session_hours if h["precip_prob"] is not None]
            temps = [h["temp"] for h in session_hours if h["temp"] is not None]
            winds = [h["windspeed"] for h in session_hours if h["windspeed"] is not None]
            precips = [h["precip_mm"] for h in session_hours if h["precip_mm"] is not None]

            # Dominant weather code = most common non-zero, or most common
            codes = [h["weather_code"] for h in session_hours if h["weather_code"] is not None]
            dominant_code = max(set(codes), key=codes.count) if codes else 0
            wmo = WMO_CODES.get(dominant_code, ("Unknown", "cloudy"))

            max_prob = max(probs) if probs else 0

            enriched_sessions.append({
                "name": session["name"],
                "day_label": session["day_label"],
                "date": session["date"],
                "rain_probability": round(max_prob),
                "rain_risk": classify_rain_risk(max_prob),
                "avg_temp": round(sum(temps) / len(temps), 1) if temps else None,
                "avg_wind": round(sum(winds) / len(winds), 1) if winds else None,
                "total_precip_mm": round(sum(precips), 1) if precips else 0,
                "weather_description": wmo[0],
                "weather_category": wmo[1],
                "weather_icon": get_weather_icon(wmo[1]),
                "hourly": session_hours,
            })
        else:
            # No hourly data (forecast not available that far ahead)
            enriched_sessions.append({
                "name": session["name"],
                "day_label": session["day_label"],
                "date": session["date"],
                "rain_probability": None,
                "rain_risk": "UNKNOWN",
                "avg_temp": None,
                "avg_wind": None,
                "total_precip_mm": None,
                "weather_description": "Forecast not available",
                "weather_category": "unknown",
                "weather_icon": "\u2753",
                "hourly": [],
            })

    return enriched_sessions


def run_weather_forecast(round_num: int | None = None) -> dict:
    """Main entry point — fetch and process weather for a race weekend."""
    print("=" * 60)
    print("BoxBoxF1Fantasy — Weather Forecast")
    print("=" * 60)

    races = load_race_calendar()
    race = find_next_round(races, round_num)

    if not race:
        print("No upcoming race found.")
        return {}

    print(f"\nRace: {race['name']} (Round {race['round']})")
    print(f"Date: {race['date']} | Circuit: {race['circuit']}")
    print(f"Sprint: {'Yes' if race.get('sprint') else 'No'}")

    # Get coordinates
    location = get_circuit_location(race["circuit"])
    if not location:
        print(f"ERROR: No coordinates for circuit '{race['circuit']}'")
        return {}

    lat, lon, tz = location
    print(f"Location: {lat:.4f}, {lon:.4f} ({tz})")

    # Build session schedule
    sessions = build_session_schedule(race)
    race_date = datetime.strptime(race["date"], "%Y-%m-%d")
    friday = race_date - timedelta(days=2)
    sunday = race_date

    start_date = friday.strftime("%Y-%m-%d")
    end_date = sunday.strftime("%Y-%m-%d")
    print(f"Forecast window: {start_date} to {end_date}")

    # Fetch weather
    api_data = fetch_weather(lat, lon, tz, start_date, end_date)
    if not api_data:
        print("Failed to fetch weather data.")
        return {}

    # Process daily summaries
    target_dates = [
        friday.strftime("%Y-%m-%d"),
        (race_date - timedelta(days=1)).strftime("%Y-%m-%d"),
        sunday.strftime("%Y-%m-%d"),
    ]
    daily_forecast = process_daily_forecast(api_data, target_dates)

    # Process per-session forecasts
    session_forecast = process_hourly_for_sessions(api_data, sessions)

    # Calculate overall weekend rain risk
    max_rain_prob = 0
    for s in session_forecast:
        if s["rain_probability"] is not None:
            max_rain_prob = max(max_rain_prob, s["rain_probability"])

    now = datetime.now(timezone.utc)
    next_update = now + timedelta(hours=6)

    output = {
        "round": race["round"],
        "race": race["name"],
        "circuit": race["circuit"],
        "race_date": race["date"],
        "is_sprint_weekend": race.get("sprint", False),
        "location": {
            "latitude": lat,
            "longitude": lon,
            "timezone": tz,
        },
        "forecast_window": {
            "start": start_date,
            "end": end_date,
        },
        "overall_rain_risk": classify_rain_risk(max_rain_prob),
        "max_rain_probability": max_rain_prob,
        "daily": daily_forecast,
        "sessions": session_forecast,
        "last_updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_update": next_update.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_source": "Open-Meteo (open-meteo.com)",
    }

    # Save to website data
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = WEB_DATA_DIR / "weather.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"WEATHER FORECAST — {race['name']}")
    print(f"{'=' * 60}")
    print(f"  Overall rain risk: {output['overall_rain_risk']} (max {max_rain_prob}%)")
    print()

    for day in daily_forecast:
        print(f"  {day['date']}: {day['weather_icon']} {day['weather_description']}")
        print(f"    Temp: {day['temp_min']}–{day['temp_max']}°C | "
              f"Rain: {day['precip_probability_max']}% | "
              f"Wind: {day['wind_max_kmh']} km/h")

    print()
    for s in session_forecast:
        risk_badge = {"NONE": "\u2705", "LOW": "\U0001F7E1", "MEDIUM": "\U0001F7E0", "HIGH": "\U0001F534", "UNKNOWN": "\u2753"}
        badge = risk_badge.get(s["rain_risk"], "\u2753")
        rain_str = f"{s['rain_probability']}%" if s["rain_probability"] is not None else "N/A"
        print(f"  {badge} {s['name']:20s} {s['day_label']:9s} | "
              f"Rain: {rain_str:>4s} | {s['weather_icon']} {s['weather_description']}")

    print(f"\n  Last updated:  {output['last_updated']}")
    print(f"  Next update:   {output['next_update']}")
    print(f"  Saved -> {output_path}")
    print("=" * 60)

    return output


# -- CLI -----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch weather forecast for F1 race weekend")
    parser.add_argument("--round", type=int, default=None, help="Round number (auto-detects next if omitted)")
    args = parser.parse_args()

    run_weather_forecast(args.round)


if __name__ == "__main__":
    main()
