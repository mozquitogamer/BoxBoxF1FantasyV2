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
    official_pitstop_expected,
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
    RETIREE_OT_MEAN,
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

    # Observed field DNF rate, shrunk toward a historical prior so it tracks this
    # season's actual attrition without overreacting to one carnage race. 2026 has
    # run hot (~21% field DNF vs the ~12-13% historical norm), so the per-driver
    # cap below must RISE with it — the old schedule wrongly assumed reliability
    # improves through the year and clamped genuinely-unreliable cars far too low.
    PRIOR_RATE = 0.16          # field DNF prior (bumped 0.13->0.16 on 2026-06-28:
                               # 8 rounds confirm 2026 runs ~19-20% field DNF, well
                               # above the historical norm; Brier-flat, cuts under-bias)
    PRIOR_N = 40               # prior strength in pseudo car-rounds (~2 races)
    total_dnfs = sum(d[0] for d in season_dnfs.values()) if season_dnfs else 0
    total_carrounds = sum(d[1] for d in season_dnfs.values()) if season_dnfs else 0
    field_rate = ((total_dnfs + PRIOR_RATE * PRIOR_N) / (total_carrounds + PRIOR_N)
                  if total_carrounds > 0 else PRIOR_RATE)
    # The most failure-prone car runs ~2x the field rate; clamp to a sane band.
    season_cap = min(max(field_rate * 2.0, 0.20), 0.50)

    if season_dnfs:
        total_rounds = max(d[1] for d in season_dnfs.values())
        print(f"  Loaded {total_rounds} rounds of actual DNF data ({total_dnfs} total DNFs, "
              f"field rate {field_rate:.1%}, per-driver cap {season_cap:.0%})")

    # Per-driver DNF probability via Beta-Binomial shrinkage (retuned 2026-06-28
    # on 8 rounds, walk-forward Brier 0.168 -> 0.164, ~2.7% better). The old
    # approach leaned ~90% on each driver's raw season rate then FLOORED
    # non-retirees at 2% — so a clean front-runner (0 DNFs in 8 races) showed 2%
    # risk when a ~19% field-attrition season makes ~8-13% realistic, which
    # systematically OVER-predicted the points of the most valuable cars (the MC
    # almost never retired them). It also pinned bad-luck cars (e.g. 4 DNFs in 8)
    # to the cap. Now: start each driver from a field-aware prior (mostly this
    # season's field rate, a little of their historical rolling rate) with
    # strength PRIOR_K pseudo-races, then Bayesian-update with their actual season
    # DNFs. This lifts never-retired cars to a real floor and pulls bad-luck cars
    # off the cap, while leaving genuinely unreliable cars high.
    PRIOR_K = 8                # prior strength in pseudo car-rounds (~half a season)
    PRIOR_FIELD_WEIGHT = 0.75  # prior = 0.75*field_rate + 0.25*driver-historical
    floor = 0.04               # no F1 car is truly below ~4% DNF risk
    for driver_id in predictions["driver_id"].unique():
        hist_rate = historical_rates.get(driver_id, SEASON_DEFAULT_DNF / 100)
        prior = PRIOR_FIELD_WEIGHT * field_rate + (1 - PRIOR_FIELD_WEIGHT) * hist_rate
        season_dnf, season_races = season_dnfs.get(driver_id, [0, 0])
        # (season_races == 0 -> dnf_prob == prior, the natural no-data fallback)
        dnf_prob = (season_dnf + PRIOR_K * prior) / (season_races + PRIOR_K)
        # season_cap still guards the worst cars; floor keeps every car non-zero.
        risk[driver_id] = round(min(max(dnf_prob, floor), season_cap) * 100, 1)

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

    Model: overtakes = base(grid bucket) + positions_gained

    Bases retuned 2026-06-28 on 7 rounds of F1 Fantasy overtake data
    (overtakes.csv joined to starting grid; normal-track rounds R1/2/3/6/7/9,
    Monaco R8 excluded so its multiplier doesn't double-damp). The old R1-R2
    bases assumed overtakes ramp toward the back; the data shows they're roughly
    FLAT (~5) across the grid — even front-runners rack up sensor-counted passes
    (DRS trains, recoveries, lapped traffic). Each base = mean overtakes minus
    mean positions gained for that bucket, so the model is unbiased at the mean.
    """
    positions_gained = max(0, predicted_quali - predicted_race)

    # Wheel-to-wheel overtakes NOT explained by net position gain, per grid
    # bucket. front obs 6.11/gp 0.17, upper 4.72/0.78, mid 5.28/1.39, back 4.70/2.70.
    if predicted_quali <= 3:
        base = 6
    elif predicted_quali <= 6:
        base = 4
    elif predicted_quali <= 12:
        base = 4
    else:
        base = 2

    # multiplier (<=1) damps overtakes on hard-to-pass circuits (e.g. Monaco)
    return max(0, round((base + positions_gained) * multiplier))


def estimate_sprint_overtakes(predicted_quali: int, predicted_race: int,
                              multiplier: float = 1.0) -> int:
    """
    Estimate expected overtakes for a sprint race (~45% of race distance).

    Sprint races have fewer laps and fewer overtaking opportunities.
    Bases aligned with SPRINT_OVERTAKE_BASE in 08_monte_carlo_fantasy.py.

    Retuned 2026-06-28 on 3 sprints (internal R2/R6/R7, overtakes.csv
    sprint_overtakes joined to sprint grid, n=66). Same base + positions_gained
    model as the race; sprints see fewer, flatter passes (~3).
    """
    positions_gained = max(0, predicted_quali - predicted_race)

    # Per sprint-grid bucket. front obs 2.22/gp 0.22, upper 3.00/1.00,
    # mid 3.17/0.33, back 3.77/2.17 → base = mean overtakes - mean gains.
    if predicted_quali <= 3:
        base = 2
    elif predicted_quali <= 6:
        base = 2
    elif predicted_quali <= 12:
        base = 3
    else:
        base = 2

    return max(0, round((base + positions_gained) * multiplier))


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

_recent_pts_cache: dict[int, dict[str, list[float]]] = {}


def _build_recent_pts(current_round: int) -> dict[str, list[float]]:
    """Per-driver REAL points for the 3 rounds before current_round, cached.

    Resolution order per round: official F1 Fantasy points -> computed actuals
    -> our archived predicted total (last resort). Previously this averaged our
    own PREDICTED totals (circular). Cached by current_round so the per-round
    files are read once, not once per driver.
    """
    if current_round in _recent_pts_cache:
        return _recent_pts_cache[current_round]

    official = {}
    off_path = SEED_DIR / "official_fantasy_points.json"
    if off_path.exists():
        try:
            with open(off_path) as f:
                official = json.load(f).get("rounds", {}) or {}
        except Exception:
            official = {}

    per_driver: dict[str, list[float]] = {}
    for rnd in range(max(1, current_round - 3), current_round):
        off_r = (official.get(str(rnd)) or {}).get("drivers", {}) or {}
        act = {}
        act_path = PREDICTIONS_DIR / f"round{rnd}" / "actual_fantasy_points.json"
        if act_path.exists():
            try:
                with open(act_path) as f:
                    for d in json.load(f).get("drivers", []):
                        key = d.get("driver_abbrev") or d.get("driver_id")
                        if key is not None:
                            act[key] = d.get("total_points")
            except Exception:
                pass
        pred = {}
        fp_path = PREDICTIONS_DIR / f"round{rnd}" / "fantasy_points.parquet"
        if fp_path.exists():
            try:
                dfp = pd.read_parquet(fp_path)
                pred = dict(zip(dfp["driver_abbrev"], dfp["total_expected_fantasy_points"]))
            except Exception:
                pass
        for k in set(off_r) | set(act) | set(pred):
            v = off_r.get(k)
            if v is None:
                v = act.get(k)
            if v is None:
                v = pred.get(k)
            if v is not None:
                per_driver.setdefault(k, []).append(float(v))

    _recent_pts_cache[current_round] = per_driver
    return per_driver


def load_recent_fantasy_points(driver_abbrev: str, current_round: int) -> float:
    """Average REAL fantasy points over the last 3 rounds (official>actuals>pred)."""
    vals = _build_recent_pts(current_round).get(driver_abbrev, [])
    return sum(vals) / len(vals) if vals else 0.0


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

    # -- Pre-pass: normalize FL and DOTD probabilities across the field --
    # Exactly one fastest lap and one DOTD are awarded per race, so the field
    # probabilities must sum to 1.0. The raw per-driver tiers below summed to
    # ~1.3 (FL) / ~1.1 (DOTD), inflating the deterministic breakdown. DOTD manual
    # overrides are held at their exact value; the remaining drivers are scaled to
    # fill (1 - sum_overrides).
    def _raw_fl_prob(pr: int) -> float:
        if pr <= 3: return 0.20
        if pr <= 6: return 0.10
        if pr <= 10: return 0.05
        return 0.02

    def _raw_dotd_prob(pr: int, pc: int) -> float:
        if pc >= 5 or pr <= 3: return 0.12
        if pr <= 6: return 0.08
        return 0.03

    raw_fl, raw_dotd = {}, {}
    for _, prow in predictions.iterrows():
        did = prow["driver_id"]
        pr = int(prow["predicted_race_position"])
        pc = int(prow["predicted_quali_position"]) - pr
        raw_fl[did] = _raw_fl_prob(pr)
        raw_dotd[did] = _raw_dotd_prob(pr, pc)

    fl_sum = sum(raw_fl.values()) or 1.0
    fl_norm = {k: v / fl_sum for k, v in raw_fl.items()}

    override_ids = set(dotd_overrides.keys())
    override_total = min(sum(dotd_overrides[d] for d in override_ids if d in raw_dotd), 1.0)
    nonoverride_sum = sum(v for k, v in raw_dotd.items() if k not in override_ids) or 1.0
    remainder = max(0.0, 1.0 - override_total)
    dotd_norm = {}
    for k, v in raw_dotd.items():
        dotd_norm[k] = (dotd_overrides[k] if k in override_ids
                        else v / nonoverride_sum * remainder)

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

        # Fastest lap & DOTD probabilities — field-normalized (sum to 1.0) in the
        # pre-pass above so exactly one of each is awarded per race. DOTD manual
        # overrides flow through fl_norm/dotd_norm at their exact value.
        fl_prob = fl_norm.get(driver_id, 0.0)
        expected_fl_pts = fl_prob * RACE_FASTEST_LAP_BONUS

        dotd_prob = dotd_norm.get(driver_id, 0.0)
        expected_dotd_pts = dotd_prob * RACE_DRIVER_OF_THE_DAY_BONUS

        # DNF risk adjustment (per-driver %, capped at the season DNF cap in
        # calculate_risk_ratings, which tracks observed field attrition)
        risk = risk_ratings.get(driver_id, 5.0)
        dnf_prob = risk / 100.0

        # Total race points (adjusted for DNF probability)
        # Use softer DNF impact: a DNF driver may still score some points if they
        # retire late (partial race). Use 60% of the full penalty for expected value.
        race_pts_if_finish = (
            race_position_pts + pos_pts + overtake_pts +
            expected_fl_pts + expected_dotd_pts
        )
        # Softened penalty for the expected DNF outcome, plus the overtake points
        # a retiree typically banks before retiring (~RETIREE_OT_MEAN), matching
        # the corrected official rule (DNF = penalty + overtakes) and the MC.
        soft_dnf_penalty = RACE_DNF_DSQ_PENALTY * DNF_EXPECTED_PENALTY_FACTOR + RETIREE_OT_MEAN
        expected_race_pts = (1 - dnf_prob) * race_pts_if_finish + dnf_prob * soft_dnf_penalty

        # -- Sprint (if applicable) --
        sprint_quali_pts = 0.0
        sprint_race_pts = 0.0

        if is_sprint:
            # predicted_sprint_quali_position is the sprint GRID (from sprint
            # qualifying) — needed for positions-gained, but NOT itself scored:
            # official F1 Fantasy awards no points for sprint-qualifying position
            # (verified against official actuals). sprint_quali_pts stays 0.
            pred_sprint_quali = int(row.get("predicted_sprint_quali_position", pred_quali))
            pred_sprint = int(row.get("predicted_sprint_position", pred_race))

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

            # Sprint DNF probability is half the race DNF prob (shorter race,
            # fewer incidents) — matches the MC's `dnf_probs * 0.5` in 08 so the
            # deterministic and simulated sprint expectations agree.
            sprint_dnf_prob = dnf_prob * 0.5
            sprint_race_pts = (
                (1 - sprint_dnf_prob) * (sprint_pos_pts + sprint_pos_change +
                                         sprint_overtakes + expected_sprint_fl)
                + sprint_dnf_prob * SPRINT_DNF_DSQ_PENALTY
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
    # Official-history expected pit points per team (shrunk mean of actual F1
    # Fantasy pit points) — the reliable basis for future pit prediction.
    official_pit_expected = official_pitstop_expected()
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
            # 2026: 22 cars, Q2 eliminates P11-16 -> Q2 cutoff is P16 (not 15).
            d1_session = "Q3" if driver_positions[0] <= 10 else ("Q2" if driver_positions[0] <= 16 else "Q1")
            d2_session = "Q3" if driver_positions[1] <= 10 else ("Q2" if driver_positions[1] <= 16 else "Q1")
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

        # Expected pit stop points: prefer the official-history estimate (shrunk
        # mean of this team's actual F1 Fantasy pit points — far more reliable
        # than our OpenF1 time model, which misses null-stationary stops). Fall
        # back to the time-prior when a team has no official history yet.
        if cid in official_pit_expected:
            expected_pit_pts = round(official_pit_expected[cid], 1)
        else:
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
            soft_penalty = RACE_DNF_DSQ_PENALTY * DNF_EXPECTED_PENALTY_FACTOR
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
