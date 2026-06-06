"""
Script 07 — Calculate Fantasy Points

Converts model predictions into expected fantasy points for both
drivers and constructors, using official F1 Fantasy 2026 scoring rules.

Reads predictions from 06_run_predictions.py (which use Jolpica driver IDs)
and maps to abbreviation IDs for seed file lookups (prices, driver info).

Produces:
- Per-driver: qualifying pts, race pts, sprint pts, overtakes, risk, value
- Per-constructor: combined driver pts + quali bonus + pit stop estimates

Usage:
    python pipeline/07_calculate_fantasy.py --round 3
    python pipeline/07_calculate_fantasy.py --round 3 --year 2026

Output:
    data/predictions/roundX/fantasy_points.parquet
    data/predictions/roundX/fantasy_points_constructors.parquet
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    PREDICTIONS_DIR,
    JOLPICA_MODEL_ROWS_DIR,
    SEED_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
    is_race_completed,
    race_name_for_round,
    load_dotd_overrides,
)
from config.track_classifications import (
    get_circuit_id_from_race_name,
    overtake_multiplier,
)
from config.fantasy_scoring import (
    QUALIFYING_POSITION_POINTS,
    QUALIFYING_NC_DSQ_PENALTY,
    RACE_POSITION_POINTS,
    RACE_FASTEST_LAP_BONUS,
    RACE_DRIVER_OF_THE_DAY_BONUS,
    RACE_DNF_DSQ_PENALTY,
    DNF_EXPECTED_PENALTY_FACTOR,
    SPRINT_POSITION_POINTS,
    SPRINT_FASTEST_LAP_BONUS,
    SPRINT_DNF_DSQ_PENALTY,
    RACE_POSITIONS_GAINED_PER_POS,
    CONSTRUCTOR_QUALI_BONUSES,
    PITSTOP_TIME_POINTS,
    FASTEST_PITSTOP_BONUS,
    calc_qualifying_points_driver,
    calc_constructor_quali_bonus,
)


# -- ID mapping ----------------------------------------------------------------

def load_id_maps() -> tuple[dict, dict]:
    """Load Jolpica <-> abbreviation mappings."""
    with open(SEED_DIR / "driver_ids.json") as f:
        data = json.load(f)
    jolpica_to_abbrev = {}
    abbrev_to_jolpica = {}
    for m in data["mappings"]:
        jolpica_to_abbrev[m["jolpica"]] = m["abbrev"]
        abbrev_to_jolpica[m["abbrev"]] = m["jolpica"]
    return jolpica_to_abbrev, abbrev_to_jolpica


# -- Risk rating from pre-computed model rows ----------------------------------

def calculate_risk_ratings(predictions: pd.DataFrame) -> dict[str, float]:
    """
    Get DNF risk per driver from pre-computed rolling DNF rates in model_rows.
    Falls back to a default if model_rows unavailable.

    Blends the historical rolling rate with the current season's actual DNF rate
    to avoid inflated probabilities from small samples or prior-season bad luck.
    """
    risk = {}
    SEASON_DEFAULT_DNF = 5.0  # 5% base rate for F1

    # Try to load pre-computed rolling DNF rates from historical data
    historical_rates = {}
    model_rows_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    if model_rows_path.exists():
        mr = pd.read_parquet(model_rows_path)
        latest = mr.sort_values(["season", "round"]).groupby("driver_id").last()
        if "roll_dnf_rate_5" in latest.columns:
            for driver_id, row in latest.iterrows():
                rate = row["roll_dnf_rate_5"]
                if pd.notna(rate):
                    historical_rates[driver_id] = rate

    # Load abbreviation -> driver_id mapping for matching actual results
    abbrev_to_driver_id = {}
    driver_ids_path = SEED_DIR / "driver_ids.json"
    if driver_ids_path.exists():
        with open(driver_ids_path) as f:
            id_data = json.load(f)
        for m in id_data.get("mappings", []):
            abbrev_to_driver_id[m["abbrev"]] = m["jolpica"]  # e.g. "VER" -> "max_verstappen"

    # Load actual 2026 DNF data from completed rounds
    season_dnfs = {}  # driver_id (full) -> [dnf_count, races_completed]
    actuals_dir = PREDICTIONS_DIR
    for rd in actuals_dir.iterdir():
        if not rd.is_dir() or not rd.name.startswith("round"):
            continue
        # Try both file names (actual_fantasy_points.json is the primary format)
        act_file = rd / "actual_fantasy_points.json"
        if not act_file.exists():
            act_file = rd / "actual_results.json"
        if act_file.exists():
            try:
                with open(act_file) as f:
                    act_data = json.load(f)
                for d in act_data.get("drivers", []):
                    raw_id = d.get("driver_id", "")
                    if not raw_id:
                        continue
                    # Map abbreviations to full driver_id
                    did = abbrev_to_driver_id.get(raw_id, raw_id)
                    if did not in season_dnfs:
                        season_dnfs[did] = [0, 0]
                    season_dnfs[did][1] += 1  # races completed
                    # Check both is_dnf flag and status string
                    is_dnf = d.get("is_dnf", False)
                    status = d.get("status", "").upper()
                    if is_dnf or status in ("DNF", "DSQ", "DNS", "RETIRED"):
                        season_dnfs[did][0] += 1
            except Exception:
                continue

    if season_dnfs:
        total_dnfs = sum(d[0] for d in season_dnfs.values())
        total_races = max(d[1] for d in season_dnfs.values())
        print(f"  Loaded {total_races} rounds of actual DNF data ({total_dnfs} total DNFs)")

    # Blend historical and current-season rates
    for driver_id in predictions["driver_id"].unique():
        hist_rate = historical_rates.get(driver_id, SEASON_DEFAULT_DNF / 100)
        season_data = season_dnfs.get(driver_id)

        if season_data and season_data[1] >= 1:
            season_rate = season_data[0] / season_data[1]
            n_races = season_data[1]
            # Weight current season more as we get more data
            # At 2 races: 60% season, 40% historical
            # At 5 races: 80% season, 20% historical
            season_weight = min(0.4 + n_races * 0.1, 0.9)
            blended = season_weight * season_rate + (1 - season_weight) * hist_rate
        else:
            blended = hist_rate

        # Cap at 15% early in season (unreliable small samples),
        # increase cap as season progresses
        max_races = max((d[1] for d in season_dnfs.values()), default=0)
        # DNF cap DECREASES through the season: cars get more reliable as
        # teething issues are fixed, and a long reliable run makes a high DNF
        # estimate less believable. ~15% now (5 races run), tapering to a 10% floor.
        cap = max(0.175 - max_races * 0.005, 0.10)
        # Floor: no driver has truly 0% DNF risk — mechanical failures, incidents etc.
        floor = 0.02  # 2% minimum baseline
        risk[driver_id] = round(min(max(blended, floor), cap) * 100, 1)

    return risk


def risk_label(rating: float) -> str:
    """Convert numeric risk rating to label."""
    if rating <= 10:
        return "LOW"
    elif rating <= 25:
        return "MEDIUM"
    elif rating <= 50:
        return "HIGH"
    else:
        return "VERY HIGH"


# -- Pit stop expected value ---------------------------------------------------

# Default pit stop priors per team (mean time in seconds, std)
_DEFAULT_PITSTOP_PRIORS = {
    "red_bull":       {"mean": 2.15, "std": 0.25, "stops_per_race": 1.5},
    "mclaren":        {"mean": 2.20, "std": 0.25, "stops_per_race": 1.5},
    "ferrari":        {"mean": 2.25, "std": 0.30, "stops_per_race": 1.5},
    "mercedes":       {"mean": 2.20, "std": 0.25, "stops_per_race": 1.5},
    "aston_martin":   {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5},
    "alpine":         {"mean": 2.40, "std": 0.35, "stops_per_race": 1.5},
    "williams":       {"mean": 2.45, "std": 0.35, "stops_per_race": 1.5},
    "racing_bulls":   {"mean": 2.30, "std": 0.30, "stops_per_race": 1.5},
    "haas":           {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5},
    "audi":           {"mean": 2.55, "std": 0.40, "stops_per_race": 1.5},
    "cadillac":       {"mean": 2.60, "std": 0.45, "stops_per_race": 1.5},
}


def _load_pitstop_priors() -> dict:
    """Load pit stop priors from seed data or use defaults."""
    path = SEED_DIR / "pit_stop_priors.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return _DEFAULT_PITSTOP_PRIORS


def _expected_pitstop_points(mean: float, std: float, stops_per_race: float,
                             n_teams: int = 11) -> float:
    """Calculate expected pit stop points analytically from a normal distribution.

    For each bracket (lower, upper, pts), compute the probability the stop time
    falls in that bracket and multiply by points. Then account for expected
    number of stops and the fastest-stop bonus (1/n_teams chance).
    """
    from scipy.stats import norm
    dist = norm(loc=mean, scale=std)

    # Expected points per single stop
    pts_per_stop = 0.0
    for lower, upper, pts in PITSTOP_TIME_POINTS:
        # Clamp lower at 1.5 (minimum realistic pit stop time)
        effective_lower = max(lower, 1.5)
        prob = dist.cdf(upper) - dist.cdf(effective_lower)
        pts_per_stop += prob * pts

    # Expected number of stops
    expected_stops = stops_per_race
    total = pts_per_stop * expected_stops

    # Fastest pit stop bonus: ~1/n_teams chance
    total += FASTEST_PITSTOP_BONUS / n_teams

    return round(total, 1)


# -- Overtake estimation -------------------------------------------------------

def estimate_overtakes(predicted_quali: int, predicted_race: int, grid_size: int = 22,
                       multiplier: float = 1.0) -> int:
    """
    Estimate expected overtakes from grid position and positions gained.

    2026 regs (active aero, ground effect) produce significantly more on-track
    passing than pre-2026. F1 Fantasy tracks overtakes via sensors — drivers
    routinely make many more overtakes than their net position change due to
    battles, re-passes, and lapped traffic.

    Calibrated from f1fantasytool.com actual data (Rounds 1-2):
      BEA R1: P12→P7, 5 gained, 9 overtakes  (base ~4)
      BEA R2: P10→P5, 5 gained, 13 overtakes (base ~8)
      LIN R1: P9→P8,  1 gained, 8 overtakes  (base ~7)
      LIN R2: P15→P12, 3 gained, 8 overtakes (base ~5)

    Model: overtakes = base(grid_position) + positions_gained
    """
    positions_gained = max(0, predicted_quali - predicted_race)

    # Base overtakes from wheel-to-wheel racing (even without net position gain)
    # Front-runners have fewer cars to battle; midfield/back have more traffic
    if predicted_quali <= 3:
        base = 2
    elif predicted_quali <= 6:
        base = 4
    elif predicted_quali <= 12:
        base = 6
    else:
        base = 7

    # multiplier (<=1) damps overtakes on hard-to-pass circuits (e.g. Monaco)
    return max(0, round((base + positions_gained) * multiplier))


def estimate_sprint_overtakes(predicted_quali: int, predicted_race: int,
                              multiplier: float = 1.0) -> int:
    """
    Estimate expected overtakes for a sprint race (~45% of race distance).

    Sprint races have fewer laps and fewer overtaking opportunities.
    Bases aligned with SPRINT_OVERTAKE_BASE in 08_monte_carlo_fantasy.py.

    Calibrated from OpenF1 R2 sprint data: mean=7.0, std=3.1 (n=22).
    """
    positions_gained = max(0, predicted_quali - predicted_race)

    # Reduced base overtakes for sprint distance (~50% of race values)
    if predicted_quali <= 3:
        base = 1
    elif predicted_quali <= 6:
        base = 2
    elif predicted_quali <= 12:
        base = 3
    else:
        base = 4

    # Fewer laps means fewer opportunities to convert position gains into counted overtakes
    sprint_gains = max(0, positions_gained - 1)
    return max(0, round((base + sprint_gains) * multiplier))


# -- Fantasy prices ------------------------------------------------------------

def load_fantasy_prices() -> tuple[dict[str, float], dict[str, float]]:
    """Load current fantasy prices (keyed by abbreviation)."""
    prices_path = SEED_DIR / "fantasy_prices.json"
    if not prices_path.exists():
        return {}, {}
    with open(prices_path) as f:
        data = json.load(f)
    driver_prices = {k: v["current_price"] for k, v in data.get("drivers", {}).items()}
    constructor_prices = {k: v["current_price"] for k, v in data.get("constructors", {}).items()}
    return driver_prices, constructor_prices


# -- Recent fantasy points for PPM --------------------------------------------

def load_recent_fantasy_points(driver_abbrev: str, current_round: int) -> float:
    """Load average fantasy points from the last 3 rounds."""
    total, count = 0.0, 0
    for rnd in range(max(1, current_round - 3), current_round):
        fp_path = PREDICTIONS_DIR / f"round{rnd}" / "fantasy_points.parquet"
        if fp_path.exists():
            try:
                df = pd.read_parquet(fp_path)
                row = df[df["driver_abbrev"] == driver_abbrev]
                if not row.empty:
                    total += row["total_expected_fantasy_points"].iloc[0]
                    count += 1
            except Exception:
                continue
    return total / count if count > 0 else 0.0


# -- Driver fantasy calculation ------------------------------------------------

def calculate_driver_fantasy(
    predictions: pd.DataFrame,
    round_num: int,
) -> pd.DataFrame:
    """Calculate expected fantasy points for all drivers."""
    is_sprint = round_num in SPRINT_ROUNDS_2026
    jolpica_to_abbrev, _ = load_id_maps()
    driver_prices, _ = load_fantasy_prices()
    risk_ratings = calculate_risk_ratings(predictions)

    # Track-difficulty overtake damping (hard-to-pass circuits like Monaco get
    # far fewer overtakes than the track-agnostic heuristic assumes).
    circuit_id = get_circuit_id_from_race_name(race_name_for_round(round_num))
    ot_mult = overtake_multiplier(circuit_id)
    if ot_mult < 1.0:
        print(f"  Overtake damping for {circuit_id}: x{ot_mult:.2f}")

    # Manual per-round DOTD overrides (judgment calls for fan-vote favourites).
    dotd_overrides = load_dotd_overrides(round_num)
    if dotd_overrides:
        print(f"  Manual DOTD overrides: {dotd_overrides}")

    rows = []
    for _, row in predictions.iterrows():
        driver_id = row["driver_id"]  # Jolpica format
        driver_abbrev = row.get("driver_abbrev") or jolpica_to_abbrev.get(driver_id, driver_id)
        constructor_id = row.get("constructor_id", "")
        pred_quali = int(row["predicted_quali_position"])
        pred_race = int(row["predicted_race_position"])
        confidence = int(row.get("confidence", 50))

        # -- Qualifying points --
        quali_pts = calc_qualifying_points_driver(pred_quali)

        # -- Race points --
        race_position_pts = RACE_POSITION_POINTS.get(pred_race, 0)

        # Positions gained/lost (quali grid -> race finish)
        pos_change = pred_quali - pred_race
        pos_pts = pos_change * RACE_POSITIONS_GAINED_PER_POS

        # Estimated overtakes
        est_overtakes = estimate_overtakes(pred_quali, pred_race, multiplier=ot_mult)
        overtake_pts = est_overtakes

        # Fastest lap probability (based on predicted race position)
        if pred_race <= 3:
            fl_prob = 0.20
        elif pred_race <= 6:
            fl_prob = 0.10
        elif pred_race <= 10:
            fl_prob = 0.05
        else:
            fl_prob = 0.02
        expected_fl_pts = fl_prob * RACE_FASTEST_LAP_BONUS

        # DOTD probability (top finishers + big gainers)
        if pos_change >= 5 or pred_race <= 3:
            dotd_prob = 0.12
        elif pred_race <= 6:
            dotd_prob = 0.08
        else:
            dotd_prob = 0.03
        # Manual override (e.g. home-hero fan-vote favourite) takes precedence so
        # the displayed DOTD % matches the MC's forced DOTD rate.
        if driver_id in dotd_overrides:
            dotd_prob = dotd_overrides[driver_id]
        expected_dotd_pts = dotd_prob * RACE_DRIVER_OF_THE_DAY_BONUS

        # DNF risk adjustment (capped at 25% by calculate_risk_ratings)
        risk = risk_ratings.get(driver_id, 5.0)
        dnf_prob = risk / 100.0

        # Total race points (adjusted for DNF probability)
        # Use softer DNF impact: a DNF driver may still score some points if they
        # retire late (partial race). Use 60% of the full penalty for expected value.
        race_pts_if_finish = (
            race_position_pts + pos_pts + overtake_pts +
            expected_fl_pts + expected_dotd_pts
        )
        soft_dnf_penalty = RACE_DNF_DSQ_PENALTY * DNF_EXPECTED_PENALTY_FACTOR
        expected_race_pts = (1 - dnf_prob) * race_pts_if_finish + dnf_prob * soft_dnf_penalty

        # -- Sprint (if applicable) --
        sprint_quali_pts = 0.0
        sprint_race_pts = 0.0

        if is_sprint:
            pred_sprint_quali = int(row.get("predicted_sprint_quali_position", pred_quali))
            pred_sprint = int(row.get("predicted_sprint_position", pred_race))

            sprint_quali_pts = float(calc_qualifying_points_driver(pred_sprint_quali))

            sprint_pos_pts = SPRINT_POSITION_POINTS.get(pred_sprint, 0)
            sprint_pos_change = pred_sprint_quali - pred_sprint
            sprint_overtakes = estimate_sprint_overtakes(pred_sprint_quali, pred_sprint, multiplier=ot_mult)

            # Sprint FL probability based on sprint finish position (not race)
            if pred_sprint <= 3:
                sprint_fl_prob = 0.20
            elif pred_sprint <= 6:
                sprint_fl_prob = 0.10
            elif pred_sprint <= 10:
                sprint_fl_prob = 0.03
            else:
                sprint_fl_prob = 0.01
            expected_sprint_fl = sprint_fl_prob * SPRINT_FASTEST_LAP_BONUS

            sprint_race_pts = (
                (1 - dnf_prob) * (sprint_pos_pts + sprint_pos_change +
                                  sprint_overtakes + expected_sprint_fl)
                + dnf_prob * SPRINT_DNF_DSQ_PENALTY
            )

        total_pts = quali_pts + expected_race_pts + sprint_quali_pts + sprint_race_pts

        # -- Value metrics --
        price = driver_prices.get(driver_abbrev, 10.0)
        recent_avg = load_recent_fantasy_points(driver_abbrev, round_num)
        ppm = recent_avg / price if price > 0 else 0.0
        value_score = total_pts / price if price > 0 else 0.0

        rows.append({
            "driver_id": driver_id,
            "driver_abbrev": driver_abbrev,
            "constructor_id": constructor_id,
            "predicted_quali_position": pred_quali,
            "predicted_race_position": pred_race,
            "confidence": confidence,
            "expected_quali_pts": round(quali_pts, 1),
            "expected_race_pts": round(expected_race_pts, 1),
            "expected_sprint_quali_pts": round(sprint_quali_pts, 1) if is_sprint else 0,
            "expected_sprint_race_pts": round(sprint_race_pts, 1) if is_sprint else 0,
            "total_expected_fantasy_points": round(total_pts, 1),
            "expected_overtakes": est_overtakes,
            "expected_positions_gained_lost": pos_change,
            "fastest_lap_probability": round(fl_prob, 2),
            "dotd_probability": round(dotd_prob, 2),
            "risk_rating": risk,
            "risk_label": risk_label(risk),
            "dnf_probability": round(dnf_prob, 2),
            "points_per_million": round(ppm, 2),
            "value_score": round(value_score, 2),
            "current_price": price,
        })

    return pd.DataFrame(rows)


# -- Constructor fantasy calculation -------------------------------------------

def calculate_constructor_fantasy(
    driver_fantasy: pd.DataFrame,
    round_num: int,
) -> pd.DataFrame:
    """Calculate expected fantasy points for constructors."""
    _, constructor_prices = load_fantasy_prices()

    with open(SEED_DIR / "constructors.json") as f:
        constructors = json.load(f)["constructors"]

    with open(SEED_DIR / "drivers.json") as f:
        drivers_data = json.load(f)["drivers"]

    # Map constructor -> driver abbreviations
    constructor_drivers: dict[str, list[str]] = {}
    for d in drivers_data:
        cid = d["constructor_id"]
        constructor_drivers.setdefault(cid, []).append(d["driver_id"])

    is_sprint = round_num in SPRINT_ROUNDS_2026
    pitstop_priors = _load_pitstop_priors()
    n_teams = len(constructors)
    rows = []

    for constructor in constructors:
        cid = constructor["constructor_id"]
        cname = constructor["name"]
        driver_abbrevs = constructor_drivers.get(cid, [])

        d_data = driver_fantasy[driver_fantasy["driver_abbrev"].isin(driver_abbrevs)]
        if d_data.empty:
            continue

        # Qualifying: combined + bonus
        combined_quali = d_data["expected_quali_pts"].sum()
        driver_positions = d_data["predicted_quali_position"].tolist()
        if len(driver_positions) >= 2:
            d1_session = "Q3" if driver_positions[0] <= 10 else ("Q2" if driver_positions[0] <= 15 else "Q1")
            d2_session = "Q3" if driver_positions[1] <= 10 else ("Q2" if driver_positions[1] <= 15 else "Q1")
            quali_bonus = calc_constructor_quali_bonus(d1_session, d2_session)
        else:
            quali_bonus = 0
        total_quali = combined_quali + quali_bonus

        # Race: combined race points from both drivers
        # Note: driver expected_race_pts already includes position change bonus,
        # overtake pts, FL/DOTD probability, and DNF risk adjustment.
        # DOTD must be excluded for constructors per official rules.
        # Subtract the expected DOTD contribution from each driver.
        expected_dotd_contribution = (d_data["dotd_probability"] * RACE_DRIVER_OF_THE_DAY_BONUS).sum()
        combined_race = d_data["expected_race_pts"].sum() - expected_dotd_contribution

        # Combined positions gained/lost and overtakes from both drivers
        combined_pos_change = int(d_data["expected_positions_gained_lost"].sum())
        combined_overtakes = int(d_data["expected_overtakes"].sum())

        # Expected pit stop points from team priors
        prior = pitstop_priors.get(cid, {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5})
        expected_pit_pts = _expected_pitstop_points(
            prior["mean"], prior["std"], prior["stops_per_race"], n_teams
        )

        # DNF impact: how much DNF risk reduces the constructor's expected points
        # (driver race pts already include DNF adjustment — calculate what the
        # loss is relative to no-DNF scenario)
        dnf_impact = 0.0
        for _, d_row in d_data.iterrows():
            dnf_prob = d_row.get("dnf_probability", 0.02)
            # The soft penalty the driver's race pts already includes
            soft_penalty = RACE_DNF_DSQ_PENALTY * 0.6
            # Impact = probability * penalty (negative value)
            dnf_impact += dnf_prob * soft_penalty

        # Sprint
        combined_sprint_quali = d_data["expected_sprint_quali_pts"].sum() if is_sprint else 0
        combined_sprint_race = d_data["expected_sprint_race_pts"].sum() if is_sprint else 0

        total = total_quali + combined_race + expected_pit_pts + combined_sprint_quali + combined_sprint_race

        price = constructor_prices.get(cid, 10.0)
        value_score = total / price if price > 0 else 0.0
        avg_risk = d_data["risk_rating"].mean()
        avg_dnf_prob = d_data["dnf_probability"].mean() if "dnf_probability" in d_data.columns else 0.02

        rows.append({
            "constructor_id": cid,
            "constructor_name": cname,
            "driver_1": driver_abbrevs[0] if len(driver_abbrevs) > 0 else "",
            "driver_2": driver_abbrevs[1] if len(driver_abbrevs) > 1 else "",
            "expected_quali_pts": round(total_quali, 1),
            "quali_bonus": quali_bonus,
            "expected_race_pts": round(combined_race, 1),
            "expected_pit_stop_pts": round(expected_pit_pts, 1),
            "expected_dnf_impact": round(dnf_impact, 1),
            "dnf_probability": round(avg_dnf_prob, 2),
            "combined_positions_gained": combined_pos_change,
            "combined_overtakes": combined_overtakes,
            "expected_sprint_quali_pts": round(combined_sprint_quali, 1) if is_sprint else 0,
            "expected_sprint_race_pts": round(combined_sprint_race, 1) if is_sprint else 0,
            "total_expected_fantasy_points": round(total, 1),
            "risk_rating": round(avg_risk, 1),
            "risk_label": risk_label(avg_risk),
            "value_score": round(value_score, 2),
            "current_price": price,
        })

    return pd.DataFrame(rows)


# -- Main ---------------------------------------------------------------------

def main() -> None:
    """Calculate fantasy points for a specified round."""
    parser = argparse.ArgumentParser(description="Calculate F1 Fantasy points")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON, help="Season year")
    parser.add_argument("--force", action="store_true",
                        help="Override the race-completed guard (overwrite existing fantasy_points)")
    args = parser.parse_args()

    round_num = args.round
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Fantasy Points for {args.year} Round {round_num}")
    print("=" * 70)

    if round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled.")
        return

    # Race-completed guard: don't overwrite fantasy_points for a past race.
    fantasy_path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points.parquet"
    if not args.force and is_race_completed(round_num, args.year) and fantasy_path.exists():
        print(f"\n  [SKIP] Race for round {round_num} has already happened and "
              f"fantasy_points.parquet exists.")
        print(f"  Refusing to overwrite — this would pollute the accuracy archive.")
        print(f"  Pass --force to override.")
        return

    # Load predictions
    pred_path = PREDICTIONS_DIR / f"round{round_num}" / "predictions.parquet"
    if not pred_path.exists():
        print(f"No predictions found at {pred_path}")
        print("Run 06_run_predictions.py first.")
        return

    predictions = pd.read_parquet(pred_path)
    print(f"\nLoaded predictions for {len(predictions)} drivers")

    is_sprint = round_num in SPRINT_ROUNDS_2026
    print(f"Sprint weekend: {'Yes' if is_sprint else 'No'}")

    # Calculate driver fantasy points
    print("\nCalculating driver fantasy points...")
    driver_fantasy = calculate_driver_fantasy(predictions, round_num)

    print(f"\n{'=' * 70}")
    print("DRIVER FANTASY POINTS")
    print(f"{'=' * 70}")
    display_cols = [
        "driver_abbrev", "predicted_quali_position", "predicted_race_position",
        "total_expected_fantasy_points", "expected_quali_pts", "expected_race_pts",
        "risk_label", "value_score", "current_price",
    ]
    print(driver_fantasy[display_cols].sort_values(
        "total_expected_fantasy_points", ascending=False
    ).to_string(index=False))

    # Calculate constructor fantasy points
    print("\nCalculating constructor fantasy points...")
    constructor_fantasy = calculate_constructor_fantasy(driver_fantasy, round_num)

    print(f"\n{'=' * 70}")
    print("CONSTRUCTOR FANTASY POINTS")
    print(f"{'=' * 70}")
    c_display = [
        "constructor_name", "total_expected_fantasy_points",
        "driver_1", "driver_2", "risk_label", "value_score", "current_price",
    ]
    print(constructor_fantasy[c_display].sort_values(
        "total_expected_fantasy_points", ascending=False
    ).to_string(index=False))

    # Save
    output_dir = PREDICTIONS_DIR / f"round{round_num}"
    output_dir.mkdir(parents=True, exist_ok=True)

    driver_path = output_dir / "fantasy_points.parquet"
    driver_fantasy.to_parquet(driver_path, index=False, engine="pyarrow")

    constructor_path = output_dir / "fantasy_points_constructors.parquet"
    constructor_fantasy.to_parquet(constructor_path, index=False, engine="pyarrow")

    print(f"\nSaved drivers -> {driver_path}")
    print(f"Saved constructors -> {constructor_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
