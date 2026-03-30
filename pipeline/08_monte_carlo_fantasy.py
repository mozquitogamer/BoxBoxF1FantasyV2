"""
Script 08 — Monte Carlo Fantasy Points Simulation

Simulates thousands of race outcomes by sampling from probability distributions
derived from the ML model predictions. This captures the nonlinearity of F1
Fantasy scoring (position points aren't linear, DNFs wipe all race points,
overtakes are variable) that deterministic point estimates miss.

Algorithm:
  1. Load ML predictions (raw continuous model scores + confidence)
  2. For each simulation (default 10,000):
     a. Add calibrated noise to raw model scores and re-rank -> sampled positions
     b. Sample DNFs based on each driver's risk_rating
     c. Estimate overtakes from sampled grid->finish with stochastic variation
     d. Sample fastest lap (1 driver) and DOTD (1 driver) probabilistically
     e. Calculate full fantasy points using official 2026 scoring rules
  3. Aggregate: mean, median, std, P5/P25/P75/P95 percentiles per driver
  4. Output enhanced predictions with confidence intervals

Key insight: The expected fantasy points of a position DISTRIBUTION != the
fantasy points of the expected position, because scoring is nonlinear.
E.g., a driver with 50% chance P1 (25pts) and 50% P5 (10pts) has expected
17.5pts — not the 15pts you'd get from their "expected P3".

Usage:
    python pipeline/08_monte_carlo_fantasy.py --round 3
    python pipeline/08_monte_carlo_fantasy.py --round 3 --simulations 50000
    python pipeline/08_monte_carlo_fantasy.py --round 3 --seed 42

Output:
    data/predictions/round{N}/monte_carlo_fantasy.json
    data/predictions/round{N}/monte_carlo_fantasy.parquet
    web/public/data/predictions.json  (updated with MC confidence intervals)
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
    SEED_DIR,
    WEB_DATA_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
    GRID_SIZE,
)
from config.fantasy_scoring import (
    QUALIFYING_POSITION_POINTS,
    RACE_POSITION_POINTS,
    RACE_POSITIONS_GAINED_PER_POS,
    RACE_FASTEST_LAP_BONUS,
    RACE_DRIVER_OF_THE_DAY_BONUS,
    RACE_DNF_DSQ_PENALTY,
    SPRINT_POSITION_POINTS,
    SPRINT_POSITIONS_GAINED_PER_POS,
    SPRINT_FASTEST_LAP_BONUS,
    SPRINT_DNF_DSQ_PENALTY,
    CONSTRUCTOR_QUALI_BONUSES,
    PITSTOP_TIME_POINTS,
    FASTEST_PITSTOP_BONUS,
    PITSTOP_WORLD_RECORD_BONUS,
    PITSTOP_WORLD_RECORD_TIME,
)


# ==============================================================================
# Configuration — Data-Driven Calibration
# ==============================================================================
#
# All parameters below are calibrated from actual 2026 data:
#   - Position noise: derived from R1 prediction residuals (RMSE) and scaled
#     by confidence. R1 had conf=91 with FP data (RMSE ~1.4 quali, ~0.5 race).
#     Without FP data (conf ~67), errors are expected ~3-4x larger.
#   - Overtake distributions: fitted from OpenF1 R1+R2 actual data (32 samples).
#   - DNF rate: 13.6% actual across R1+R2 (6/44 drivers).
#
# With only 2 calibration rounds, these estimates have uncertainty.
# As more rounds are completed, re-run calibration for tighter estimates.
# ==============================================================================

DEFAULT_SIMULATIONS = 10_000
DEFAULT_SEED = 42

# --- Position noise calibration ---
# Source: R1 prediction errors (with FP data, confidence ~91):
#   Quali RMSE = 1.4, Race RMSE = 0.5
# These are the noise scales at confidence=100 (perfect data).
# The confidence factor scales noise UP for low-confidence predictions
# (no FP data, less history).
QUALI_NOISE_BASE = 0.3    # Calibrated for z-scored values (std=1.0).
                           # Adjacent gaps average ~0.2-0.3, so 0.3 gives
                           # ±1-2 position swaps while preserving model gaps.
RACE_NOISE_BASE = 0.3     # Same scale as quali. Z-score normalization
                           # preserves the actual performance gaps the model
                           # predicted, so noise doesn't need to compensate
                           # for uneven raw score spacing.

# Confidence scaling: how much extra noise at low confidence.
# At conf=86 (with FP): multiplier ~1.4x -> noise ≈ base * 1.4
# At conf=67 (no FP):   multiplier ~2.0x -> noise ≈ base * 2.0
# This means without FP data, position uncertainty roughly doubles.
# Formula: multiplier = 1 + CONFIDENCE_NOISE_FACTOR * (100 - confidence) / 50
CONFIDENCE_NOISE_FACTOR = 1.5

# --- Overtake calibration (from OpenF1 R1+R2 actual data) ---
# These are mean overtakes by grid bucket (n=32 finishers across 2 races).
# The MC adds positions_gained on top, then applies random variation.
OVERTAKE_BASE = {
    "front": 6,       # Grid P1-3:  actual mean=5.8, std=2.7 (n=5)
    "upper_mid": 7,   # Grid P4-6:  actual mean=7.3, std=1.9 (n=3)
    "mid": 12,         # Grid P7-12: actual mean=12.3, std=3.3 (n=10)
    "back": 14,        # Grid P13+:  actual mean=15.5, std=3.5 (n=14)
}
# Note: the base already includes the "typical" positions gained for that
# grid bucket, so we DON'T add positions_gained on top anymore.
# Instead, we add the EXCESS positions gained beyond what's typical.
# Typical gains by bucket: front=0, upper_mid=1, mid=2, back=4
TYPICAL_GAINS = {"front": 0, "upper_mid": 1, "mid": 2, "back": 4}

# Standard deviation as fraction of mean (coefficient of variation).
# From OpenF1 data: CV ranges from 0.23 (upper_mid) to 0.47 (front).
# Using 0.35 as a reasonable middle ground.
OVERTAKE_CV = 0.35

# --- Sprint overtake calibration (from OpenF1 R2 sprint data) ---
# Sprint mean=7.0, std=3.1 across all drivers (n=22)
# Fewer laps = fewer opportunities, roughly 45% of race overtakes.
SPRINT_OVERTAKE_BASE = {
    "front": 3,
    "upper_mid": 4,
    "mid": 5,
    "back": 6,
}
SPRINT_TYPICAL_GAINS = {"front": 0, "upper_mid": 0, "mid": 1, "back": 2}
SPRINT_OVERTAKE_CV = 0.45  # Higher CV in sprints (more volatile, fewer laps)


# ==============================================================================
# Data loading
# ==============================================================================

def load_predictions(round_num: int) -> pd.DataFrame:
    """Load ML predictions for a round."""
    path = PREDICTIONS_DIR / f"round{round_num}" / "predictions.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No predictions found at {path}")
    return pd.read_parquet(path)


def load_fantasy_points(round_num: int) -> pd.DataFrame:
    """Load deterministic fantasy points (for DNF probabilities etc.)."""
    path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No fantasy points found at {path}")
    return pd.read_parquet(path)


def load_driver_prices() -> dict[str, float]:
    """Load current fantasy prices by driver abbreviation."""
    path = SEED_DIR / "fantasy_prices.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return {k: v["current_price"] for k, v in data.get("drivers", {}).items()}


def load_constructor_prices() -> dict[str, float]:
    """Load current fantasy prices by constructor ID."""
    path = SEED_DIR / "fantasy_prices.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return {k: v["current_price"] for k, v in data.get("constructors", {}).items()}


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


def load_overtake_history() -> dict:
    """Load manual overtake data from data/seed/overtakes.csv.

    Returns dict keyed by driver_id with:
      - avg_overtakes: mean overtakes per race
      - avg_pos_gained: mean positions gained per race
      - avg_pos_lost: mean positions lost per race
      - races: number of data points
    """
    path = SEED_DIR / "overtakes.csv"
    if not path.exists():
        print(f"  No overtake history found at {path}")
        return {}

    df = pd.read_csv(path)
    # Drop rows where overtakes_made is empty (unfilled)
    df = df.dropna(subset=["overtakes_made"])
    if df.empty:
        print(f"  Overtakes CSV exists but has no filled data yet")
        return {}

    result = {}
    for driver_id, grp in df.groupby("driver_id"):
        entry = {
            "avg_overtakes": grp["overtakes_made"].mean(),
            "avg_pos_gained": grp["positions_gained"].mean() if "positions_gained" in grp.columns else 0,
            "avg_pos_lost": grp["positions_lost"].mean() if "positions_lost" in grp.columns else 0,
            "races": len(grp),
        }
        # Sprint data (optional columns)
        if "sprint_overtakes" in grp.columns:
            sprint_data = grp["sprint_overtakes"].dropna()
            sprint_data = sprint_data[sprint_data > 0]  # Only count rounds with actual sprint data
            entry["avg_sprint_overtakes"] = sprint_data.mean() if len(sprint_data) > 0 else 0
        if "sprint_positions_gained" in grp.columns:
            entry["avg_sprint_pos_gained"] = grp["sprint_positions_gained"].dropna().mean()
        if "sprint_positions_lost" in grp.columns:
            entry["avg_sprint_pos_lost"] = grp["sprint_positions_lost"].dropna().mean()
        result[driver_id] = entry

    print(f"  Loaded overtake history for {len(result)} drivers ({int(df['round'].max())} rounds)")
    return result


# ==============================================================================
# Pit stop modeling
# ==============================================================================

def load_pitstop_priors():
    """Load per-team pit stop time distributions from seed data or historical."""
    path = SEED_DIR / "pit_stop_priors.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    # Fallback: reasonable defaults for 2026 teams
    return {
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


def score_pitstop(time_seconds):
    """Score a single pit stop using official F1 Fantasy 2026 brackets."""
    for lower, upper, pts in PITSTOP_TIME_POINTS:
        if lower <= time_seconds < upper:
            return pts
    return 0


def sample_pitstops(constructor_ids, rng, pitstop_priors):
    """Sample pit stop times for all constructors in one simulation.

    Returns dict: constructor_id -> {points, times, is_fastest}
    """
    # Get unique constructors
    unique_constructors = list(set(constructor_ids))
    all_stops = {}  # cid -> list of stop times

    for cid in unique_constructors:
        prior = pitstop_priors.get(cid, {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5})
        # Sample number of stops (1 or 2, weighted by stops_per_race)
        n_stops = 2 if rng.random() < (prior["stops_per_race"] - 1.0) else 1
        # Sample each stop time
        times = []
        for _ in range(n_stops):
            t = max(1.5, rng.normal(prior["mean"], prior["std"]))
            times.append(round(t, 3))
        all_stops[cid] = times

    # Find fastest stop across all teams
    fastest_time = 999.0
    fastest_cid = None
    for cid, times in all_stops.items():
        best = min(times)
        if best < fastest_time:
            fastest_time = best
            fastest_cid = cid

    # Score each team
    results = {}
    for cid, times in all_stops.items():
        pts = sum(score_pitstop(t) for t in times)
        is_fastest = (cid == fastest_cid)
        if is_fastest:
            pts += FASTEST_PITSTOP_BONUS
        # World record bonus
        if min(times) < PITSTOP_WORLD_RECORD_TIME:
            pts += PITSTOP_WORLD_RECORD_BONUS
        results[cid] = {"points": pts, "times": times, "is_fastest": is_fastest}

    return results


# ==============================================================================
# Simulation engine
# ==============================================================================

def sample_positions(raw_scores: np.ndarray, noise_base: float,
                     confidences: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Sample a full grid of positions by adding noise to raw model scores.

    This naturally enforces the constraint that each position is used exactly
    once (since we re-rank after adding noise).

    Noise is scaled by confidence:
      multiplier = 1 + CONFIDENCE_NOISE_FACTOR * (100 - confidence) / 50
      At conf=91 (with FP data): multiplier ≈ 1.3 -> tight predictions
      At conf=67 (no FP data):   multiplier ≈ 2.0 -> wider uncertainty

    Args:
        raw_scores: Continuous model output scores (lower = better)
        noise_base: Base standard deviation of the noise (from calibration)
        confidences: Per-driver confidence scores (0-100)
        rng: Random number generator

    Returns:
        Array of sampled positions (1-indexed, each position used once)
    """
    n = len(raw_scores)
    # Scale noise inversely with confidence
    confidence_multipliers = 1.0 + CONFIDENCE_NOISE_FACTOR * (100.0 - confidences) / 50.0
    noise = rng.normal(0, noise_base, size=n) * confidence_multipliers
    perturbed = raw_scores + noise
    # Rank to get positions (1-based)
    order = perturbed.argsort()
    positions = np.empty(n, dtype=int)
    positions[order] = np.arange(1, n + 1)
    return positions


def sample_overtakes(grid_positions: np.ndarray, race_positions: np.ndarray,
                     dnf_mask: np.ndarray, rng: np.random.Generator,
                     is_sprint: bool = False,
                     driver_ids: list[str] | None = None,
                     overtake_history: dict | None = None) -> np.ndarray:
    """Sample overtake counts for each driver.

    Uses driver-specific overtake history from data/seed/overtakes.csv when
    available. Falls back to grid-bucket estimates calibrated from OpenF1 data.

    When driver history is available:
      - Mean = driver's actual average overtakes per race
      - Std = 30% of mean (tight) since we have real data
      - Adjusted for simulated position change vs their typical gains

    When no history available:
      - Uses grid-bucket base + excess gains beyond typical
      - Distribution: Normal with CV from actual data
    """
    n = len(grid_positions)
    overtakes = np.zeros(n, dtype=int)

    base_map = SPRINT_OVERTAKE_BASE if is_sprint else OVERTAKE_BASE
    typical = SPRINT_TYPICAL_GAINS if is_sprint else TYPICAL_GAINS
    cv = SPRINT_OVERTAKE_CV if is_sprint else OVERTAKE_CV

    for i in range(n):
        if dnf_mask[i]:
            overtakes[i] = 0
            continue

        grid = grid_positions[i]
        if grid <= 3:
            bucket = "front"
        elif grid <= 6:
            bucket = "upper_mid"
        elif grid <= 12:
            bucket = "mid"
        else:
            bucket = "back"

        # Grid-bucket estimate (always computed as baseline)
        base = base_map[bucket]
        pos_gained = max(0, grid - race_positions[i])
        excess_gains = max(0, pos_gained - typical[bucket])
        bucket_ot = base + excess_gains

        # Check for driver-specific overtake data
        driver_id = driver_ids[i] if driver_ids else None
        hist = overtake_history.get(driver_id) if (overtake_history and driver_id) else None

        if hist and hist["races"] >= 1:
            # Blend driver history with bucket estimate
            # Weight driver data more as we get more races
            # At 2 races: 50% driver, 50% bucket
            # At 5 races: 80% driver, 20% bucket
            n_races = hist["races"]
            driver_weight = min(0.3 + n_races * 0.1, 0.85)

            driver_avg_ot = hist["avg_overtakes"]
            driver_avg_gained = hist["avg_pos_gained"]

            # Adjust driver average for this sim's position change vs typical
            sim_gained = max(0, grid - race_positions[i])
            gain_diff = sim_gained - max(0, driver_avg_gained)
            adjusted_driver_ot = max(0, driver_avg_ot + gain_diff * 0.5)

            if is_sprint:
                # Use sprint-specific data if available
                sprint_avg = hist.get("avg_sprint_overtakes", 0)
                if sprint_avg > 0:
                    adjusted_driver_ot = sprint_avg
                else:
                    adjusted_driver_ot *= 0.45

            expected_ot = driver_weight * adjusted_driver_ot + (1 - driver_weight) * bucket_ot
            # Wider std early on since small sample
            cv_adj = max(0.25, 0.45 - n_races * 0.03)
            std = max(1.5, expected_ot * cv_adj)
        else:
            expected_ot = bucket_ot
            std = max(1.5, expected_ot * cv)

        sampled = rng.normal(expected_ot, std)
        overtakes[i] = max(0, round(sampled))

    return overtakes


def sample_fastest_lap(race_positions: np.ndarray, dnf_mask: np.ndarray,
                       rng: np.random.Generator) -> int:
    """Sample which driver gets fastest lap.

    Probability weighted by race position (front-runners more likely).
    Returns index of the driver with fastest lap, or -1 if none.
    """
    n = len(race_positions)
    weights = np.zeros(n)
    for i in range(n):
        if dnf_mask[i]:
            continue
        pos = race_positions[i]
        if pos <= 3:
            weights[i] = 0.25
        elif pos <= 6:
            weights[i] = 0.12
        elif pos <= 10:
            weights[i] = 0.05
        else:
            weights[i] = 0.02

    total = weights.sum()
    if total == 0:
        return -1

    weights /= total
    return rng.choice(n, p=weights)


def sample_dotd(race_positions: np.ndarray, grid_positions: np.ndarray,
                dnf_mask: np.ndarray, rng: np.random.Generator) -> int:
    """Sample Driver of the Day.

    DOTD tends to go to drivers who made big gains or had impressive drives.
    Weight by combination of finishing position and positions gained.
    """
    n = len(race_positions)
    weights = np.zeros(n)
    for i in range(n):
        if dnf_mask[i]:
            continue
        pos = race_positions[i]
        gained = max(0, grid_positions[i] - pos)

        # Base weight from finishing position
        if pos <= 3:
            base_w = 0.15
        elif pos <= 6:
            base_w = 0.08
        elif pos <= 10:
            base_w = 0.05
        else:
            base_w = 0.02

        # Bonus for big gainers
        gain_bonus = gained * 0.02
        weights[i] = base_w + gain_bonus

    total = weights.sum()
    if total == 0:
        return -1

    weights /= total
    return rng.choice(n, p=weights)


def calc_driver_fantasy_points_sim(
    quali_pos: int,
    race_pos: int,
    grid_pos: int,
    overtakes: int,
    is_fastest_lap: bool,
    is_dotd: bool,
    is_dnf: bool,
    is_sprint_weekend: bool,
    sprint_pos: int = 0,
    sprint_grid: int = 0,
    sprint_overtakes: int = 0,
    sprint_fastest_lap: bool = False,
    sprint_dnf: bool = False,
) -> dict:
    """Calculate full fantasy points for a single driver in one simulation."""

    # Qualifying points
    quali_pts = QUALIFYING_POSITION_POINTS.get(quali_pos, 0)

    # Race points
    if is_dnf:
        race_pts = RACE_DNF_DSQ_PENALTY
        race_finish_pts = 0
        pos_change_pts = 0
        overtake_pts = 0
        fl_pts = 0
        dotd_pts = 0
    else:
        race_finish_pts = RACE_POSITION_POINTS.get(race_pos, 0)
        pos_change = grid_pos - race_pos
        pos_change_pts = pos_change  # +1/-1 per position
        overtake_pts = overtakes
        fl_pts = RACE_FASTEST_LAP_BONUS if is_fastest_lap else 0
        dotd_pts = RACE_DRIVER_OF_THE_DAY_BONUS if is_dotd else 0
        race_pts = race_finish_pts + pos_change_pts + overtake_pts + fl_pts + dotd_pts

    # Sprint points
    sprint_pts = 0
    if is_sprint_weekend:
        if sprint_dnf:
            sprint_pts = SPRINT_DNF_DSQ_PENALTY
        elif sprint_pos > 0:
            sprint_finish_pts = SPRINT_POSITION_POINTS.get(sprint_pos, 0)
            sprint_pos_change = sprint_grid - sprint_pos
            sprint_pts = (sprint_finish_pts + sprint_pos_change +
                         sprint_overtakes +
                         (SPRINT_FASTEST_LAP_BONUS if sprint_fastest_lap else 0))

    total = quali_pts + race_pts + sprint_pts

    return {
        "quali_pts": quali_pts,
        "race_pts": race_pts,
        "sprint_pts": sprint_pts,
        "total_pts": total,
        "race_finish_pts": race_finish_pts if not is_dnf else 0,
        "pos_change_pts": pos_change_pts if not is_dnf else 0,
        "overtake_pts": overtake_pts if not is_dnf else 0,
        "fl_pts": fl_pts if not is_dnf else 0,
        "dotd_pts": dotd_pts if not is_dnf else 0,
    }


def run_simulations(
    pred_df: pd.DataFrame,
    fantasy_df: pd.DataFrame,
    n_sims: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
    is_sprint: bool = False,
) -> dict:
    """Run Monte Carlo simulations and return aggregated results.

    Args:
        pred_df: Predictions DataFrame with raw model scores
        fantasy_df: Fantasy points DataFrame with dnf_probability etc.
        n_sims: Number of simulations to run
        seed: Random seed for reproducibility
        is_sprint: Whether this is a sprint weekend

    Returns:
        Dict with per-driver simulation statistics
    """
    rng = np.random.default_rng(seed)
    n_drivers = len(pred_df)

    # Handle different prediction formats (older rounds may lack some columns)
    # Get driver abbreviations
    if "driver_abbrev" in pred_df.columns:
        abbrevs = pred_df["driver_abbrev"].values
    else:
        # Fall back to fantasy_df which always has driver_abbrev
        # Match by driver_id
        id_to_abbrev = dict(zip(fantasy_df["driver_id"], fantasy_df["driver_abbrev"]))
        abbrevs = pred_df["driver_id"].map(id_to_abbrev).values

    constructors = pred_df["constructor_id"].values

    # Get raw model scores (or synthesize from positions if not available)
    if "predicted_quali_raw" in pred_df.columns:
        quali_raw = pred_df["predicted_quali_raw"].values.astype(float)
        race_raw = pred_df["predicted_race_raw"].values.astype(float)
    else:
        # Older format: synthesize continuous scores from discrete positions
        quali_raw = pred_df["predicted_quali_position"].values.astype(float)
        race_raw = pred_df["predicted_race_position"].values.astype(float)

    # Z-score normalize raw scores, preserving performance gaps.
    # Unlike quantile transform (which destroys gaps by mapping to uniform spacing),
    # z-score normalization keeps the relative gaps the model predicted while putting
    # scores on a consistent scale (mean=0, std=1).
    def normalize_scores(scores):
        """Z-score normalize raw model scores, preserving gaps."""
        mean = scores.mean()
        std = scores.std()
        if std < 1e-6:
            return scores - mean
        return (scores - mean) / std

    quali_raw = normalize_scores(quali_raw)
    race_raw = normalize_scores(race_raw)
    print(f"  Applied z-score normalization (preserving performance gaps)")

    confidences = pred_df["confidence"].values.astype(float)

    # DNF probabilities from fantasy_df (matched by driver_abbrev)
    dnf_probs = np.zeros(n_drivers)
    fp_lookup = fantasy_df.set_index("driver_abbrev")
    for i, abbrev in enumerate(abbrevs):
        if abbrev in fp_lookup.index:
            dnf_probs[i] = fp_lookup.loc[abbrev, "dnf_probability"]

    # Load driver-specific overtake history from seed data
    overtake_hist = load_overtake_history()
    # Map abbreviations to full driver_ids for overtake lookup
    abbrev_to_id = {}
    driver_info = load_drivers_info()
    for did, info in driver_info.items():
        abbrev_to_id[info.get("abbreviation", did)] = did
    # Also try pred_df driver_id column directly
    if "driver_id" in pred_df.columns:
        for i, row in pred_df.iterrows():
            abbrev_to_id[row.get("driver_abbrev", "")] = row["driver_id"]
    driver_id_list = [abbrev_to_id.get(a, a) for a in abbrevs]

    # Storage for all simulation results
    all_total_pts = np.zeros((n_sims, n_drivers))
    all_quali_pts = np.zeros((n_sims, n_drivers))
    all_race_pts = np.zeros((n_sims, n_drivers))
    all_sprint_pts = np.zeros((n_sims, n_drivers))
    all_quali_pos = np.zeros((n_sims, n_drivers), dtype=int)
    all_race_pos = np.zeros((n_sims, n_drivers), dtype=int)
    all_overtakes = np.zeros((n_sims, n_drivers), dtype=int)
    all_dnf = np.zeros((n_sims, n_drivers), dtype=bool)

    print(f"  Running {n_sims:,} simulations for {n_drivers} drivers...")

    for sim in range(n_sims):
        # 1. Sample qualifying positions
        quali_positions = sample_positions(quali_raw, QUALI_NOISE_BASE, confidences, rng)

        # 2. Sample race DNFs
        dnf_mask = rng.random(n_drivers) < dnf_probs

        # 3. Sample race positions (for non-DNF drivers)
        race_positions = sample_positions(race_raw, RACE_NOISE_BASE, confidences, rng)
        # DNF drivers get position = grid_size (last)
        race_positions[dnf_mask] = GRID_SIZE

        # 4. Sample overtakes (use driver-specific history when available)
        overtakes = sample_overtakes(quali_positions, race_positions, dnf_mask, rng,
                                     driver_ids=driver_id_list, overtake_history=overtake_hist)

        # 5. Sample fastest lap & DOTD
        fl_idx = sample_fastest_lap(race_positions, dnf_mask, rng)
        dotd_idx = sample_dotd(race_positions, quali_positions, dnf_mask, rng)

        # 6. Sprint simulation (if applicable)
        sprint_positions = np.zeros(n_drivers, dtype=int)
        sprint_overtakes = np.zeros(n_drivers, dtype=int)
        sprint_dnf_mask = np.zeros(n_drivers, dtype=bool)
        sprint_fl_idx = -1

        if is_sprint:
            # Sprint uses quali positions as grid, with separate noise
            sprint_positions = sample_positions(race_raw, RACE_NOISE_BASE * 0.8,
                                                confidences, rng)
            sprint_dnf_mask = rng.random(n_drivers) < (dnf_probs * 0.5)  # Lower DNF in sprint
            sprint_positions[sprint_dnf_mask] = GRID_SIZE
            sprint_overtakes = sample_overtakes(
                quali_positions, sprint_positions, sprint_dnf_mask, rng, is_sprint=True,
                driver_ids=driver_id_list, overtake_history=overtake_hist
            )
            sprint_fl_idx = sample_fastest_lap(sprint_positions, sprint_dnf_mask, rng)

        # 7. Calculate fantasy points for each driver
        for i in range(n_drivers):
            result = calc_driver_fantasy_points_sim(
                quali_pos=quali_positions[i],
                race_pos=race_positions[i],
                grid_pos=quali_positions[i],  # Grid = quali position (no penalties modeled)
                overtakes=overtakes[i],
                is_fastest_lap=(i == fl_idx),
                is_dotd=(i == dotd_idx),
                is_dnf=dnf_mask[i],
                is_sprint_weekend=is_sprint,
                sprint_pos=sprint_positions[i] if is_sprint else 0,
                sprint_grid=quali_positions[i] if is_sprint else 0,
                sprint_overtakes=sprint_overtakes[i] if is_sprint else 0,
                sprint_fastest_lap=(i == sprint_fl_idx) if is_sprint else False,
                sprint_dnf=sprint_dnf_mask[i] if is_sprint else False,
            )

            all_total_pts[sim, i] = result["total_pts"]
            all_quali_pts[sim, i] = result["quali_pts"]
            all_race_pts[sim, i] = result["race_pts"]
            all_sprint_pts[sim, i] = result["sprint_pts"]
            all_quali_pos[sim, i] = quali_positions[i]
            all_race_pos[sim, i] = race_positions[i]
            all_overtakes[sim, i] = overtakes[i]
            all_dnf[sim, i] = dnf_mask[i]

    # Aggregate statistics
    print(f"  Aggregating results...")
    driver_results = []

    for i in range(n_drivers):
        pts = all_total_pts[:, i]
        q_pts = all_quali_pts[:, i]
        r_pts = all_race_pts[:, i]
        s_pts = all_sprint_pts[:, i]
        q_pos = all_quali_pos[:, i]
        r_pos = all_race_pos[:, i]
        ot = all_overtakes[:, i]
        dnf = all_dnf[:, i]

        driver_results.append({
            "driver_abbrev": abbrevs[i],
            "constructor_id": constructors[i],
            # Point predictions (deterministic, for reference)
            "det_quali_position": int(pred_df.iloc[i]["predicted_quali_position"]),
            "det_race_position": int(pred_df.iloc[i]["predicted_race_position"]),
            # Monte Carlo results — total points
            "mc_total_mean": round(float(pts.mean()), 1),
            "mc_total_median": round(float(np.median(pts)), 1),
            "mc_total_std": round(float(pts.std()), 1),
            "mc_total_p5": round(float(np.percentile(pts, 5)), 1),
            "mc_total_p25": round(float(np.percentile(pts, 25)), 1),
            "mc_total_p75": round(float(np.percentile(pts, 75)), 1),
            "mc_total_p95": round(float(np.percentile(pts, 95)), 1),
            "mc_total_min": round(float(pts.min()), 1),
            "mc_total_max": round(float(pts.max()), 1),
            # Component breakdowns
            "mc_quali_pts_mean": round(float(q_pts.mean()), 1),
            "mc_race_pts_mean": round(float(r_pts.mean()), 1),
            "mc_sprint_pts_mean": round(float(s_pts.mean()), 1),
            # Position distributions
            "mc_quali_pos_mean": round(float(q_pos.mean()), 1),
            "mc_race_pos_mean": round(float(r_pos.mean()), 1),
            "mc_quali_pos_std": round(float(q_pos.std()), 1),
            "mc_race_pos_std": round(float(r_pos.std()), 1),
            # Overtakes & DNF
            "mc_overtakes_mean": round(float(ot.mean()), 1),
            "mc_overtakes_std": round(float(ot.std()), 1),
            "mc_dnf_rate": round(float(dnf.mean()), 3),
            # Upside/downside
            "mc_upside": round(float(np.percentile(pts, 90) - pts.mean()), 1),
            "mc_downside": round(float(pts.mean() - np.percentile(pts, 10)), 1),
            # Position probabilities (useful for team optimizer)
            "prob_top3": round(float((r_pos <= 3).mean()), 3),
            "prob_top5": round(float((r_pos <= 5).mean()), 3),
            "prob_top10": round(float((r_pos <= 10).mean()), 3),
            "prob_points_finish": round(float((r_pos <= 10).mean() & ~dnf.any()), 3) if False else round(float(((r_pos <= 10) & ~dnf).mean()), 3),
        })

    return {
        "drivers": driver_results,
        "simulation_params": {
            "n_simulations": n_sims,
            "seed": seed,
            "quali_noise_base": QUALI_NOISE_BASE,
            "race_noise_base": RACE_NOISE_BASE,
            "confidence_noise_factor": CONFIDENCE_NOISE_FACTOR,
            "overtake_cv": OVERTAKE_CV,
            "calibration_source": "OpenF1 R1+R2 actual data (2026)",
            "is_sprint_weekend": is_sprint,
        },
        # Return raw arrays for constructor per-iteration simulation
        "_sim_arrays": {
            "all_total_pts": all_total_pts,
            "all_quali_pts": all_quali_pts,
            "all_race_pts": all_race_pts,
            "all_quali_pos": all_quali_pos,
            "all_dnf": all_dnf,
            "abbrevs": abbrevs,
            "constructors": constructors,
        },
    }


# ==============================================================================
# Constructor aggregation
# ==============================================================================

def aggregate_constructors(driver_results: list[dict], drivers_info: dict,
                           constructors_info: dict, constructor_prices: dict,
                           sim_arrays=None, pitstop_priors=None,
                           n_sims=DEFAULT_SIMULATIONS, seed=DEFAULT_SEED) -> list[dict]:
    """Aggregate driver MC results into constructor-level statistics.

    Constructor F1 Fantasy scoring (2026):
      - Sum of both drivers' total points (excluding DOTD)
      - PLUS constructor qualifying tier bonus (computed per-iteration from
        actual simulated qualifying positions)
      - PLUS pit stop points (sampled per-iteration from team priors)

    When sim_arrays are provided, this does proper per-iteration simulation
    instead of approximating from summary statistics.
    """
    # Map constructor -> drivers (abbreviations)
    constructor_drivers: dict[str, list[str]] = {}
    for d in drivers_info.values():
        cid = d["constructor_id"]
        constructor_drivers.setdefault(cid, []).append(d["driver_id"])

    # Build lookup by abbreviation for fallback
    dr_lookup = {d["driver_abbrev"]: d for d in driver_results}

    # Build abbreviation -> sim array index mapping
    abbrev_to_idx = {}
    if sim_arrays is not None:
        abbrevs = sim_arrays["abbrevs"]
        for idx, abbrev in enumerate(abbrevs):
            abbrev_to_idx[abbrev] = idx

    rng = np.random.default_rng(seed + 999)  # Different seed from main sim

    constructor_results = []
    for cid, cinfo in constructors_info.items():
        c_drivers = constructor_drivers.get(cid, [])
        if len(c_drivers) < 2:
            continue

        d1_abbrev = c_drivers[0]
        d2_abbrev = c_drivers[1]

        d1 = dr_lookup.get(d1_abbrev, {})
        d2 = dr_lookup.get(d2_abbrev, {})

        if not d1 or not d2:
            continue

        c_price = constructor_prices.get(cid, 0.0)

        # Per-iteration simulation when we have the raw arrays
        if sim_arrays is not None and d1_abbrev in abbrev_to_idx and d2_abbrev in abbrev_to_idx:
            all_total_pts = sim_arrays["all_total_pts"]
            all_quali_pos = sim_arrays["all_quali_pos"]

            d1_idx = abbrev_to_idx[d1_abbrev]
            d2_idx = abbrev_to_idx[d2_abbrev]

            constructor_pts = np.zeros(n_sims)
            for sim in range(n_sims):
                # Driver points (we approximate DOTD removal since we don't
                # track which driver won DOTD per-sim; use expected DOTD pts)
                d1_pts = all_total_pts[sim, d1_idx]
                d2_pts = all_total_pts[sim, d2_idx]

                # Approximate DOTD subtraction (DOTD doesn't count for constructors)
                # ~1/22 base chance, weighted by position
                d1_race_pos_mean = d1.get("mc_race_pos_mean", 11)
                d2_race_pos_mean = d2.get("mc_race_pos_mean", 11)
                def _est_dotd(pos):
                    if pos <= 5: return 10 * 0.07
                    elif pos <= 10: return 10 * 0.05
                    else: return 10 * 0.03
                d1_pts -= _est_dotd(d1_race_pos_mean)
                d2_pts -= _est_dotd(d2_race_pos_mean)

                # Quali teamwork bonus (from actual simulated positions)
                q1 = all_quali_pos[sim, d1_idx]
                q2 = all_quali_pos[sim, d2_idx]
                both_q3 = (q1 <= 10) and (q2 <= 10)
                one_q3 = (q1 <= 10) or (q2 <= 10)
                both_q2 = (q1 <= 15) and (q2 <= 15)
                one_q2 = (q1 <= 15) or (q2 <= 15)
                if both_q3:
                    quali_bonus = 10
                elif one_q3:
                    quali_bonus = 5
                elif both_q2:
                    quali_bonus = 3
                elif one_q2:
                    quali_bonus = 1
                else:
                    quali_bonus = -1

                constructor_pts[sim] = d1_pts + d2_pts + quali_bonus

            # Add pit stop points (sampled independently for each sim)
            if pitstop_priors:
                prior = pitstop_priors.get(cid, {"mean": 2.50, "std": 0.40, "stops_per_race": 1.5})
                for sim in range(n_sims):
                    n_stops = 2 if rng.random() < (prior["stops_per_race"] - 1.0) else 1
                    pit_pts = 0
                    for _ in range(n_stops):
                        t = max(1.5, rng.normal(prior["mean"], prior["std"]))
                        pit_pts += score_pitstop(t)
                    constructor_pts[sim] += pit_pts
                # Note: fastest pit stop bonus requires comparing across all teams
                # per-sim. For simplicity, estimate as expected value addition.
                # With 11 teams, ~1/11 chance of being fastest each race.
                constructor_pts += FASTEST_PITSTOP_BONUS / len(constructors_info)

            combined_mean = float(constructor_pts.mean())
            combined_std = float(constructor_pts.std())
            combined_p5 = float(np.percentile(constructor_pts, 5))
            combined_p95 = float(np.percentile(constructor_pts, 95))
            # Compute mean quali bonus across sims for reporting
            avg_quali_bonus = float(constructor_pts.mean()) - float(
                (all_total_pts[:, d1_idx] + all_total_pts[:, d2_idx]).mean()
            )

        else:
            # Fallback: approximate from summary stats (no sim arrays)
            def est_dotd_pts(d):
                pos = d.get("mc_race_pos_mean", 11)
                if pos <= 5: return 10 * 0.07
                elif pos <= 10: return 10 * 0.05
                else: return 10 * 0.03

            d1_pts = d1.get("mc_total_mean", 0) - est_dotd_pts(d1)
            d2_pts = d2.get("mc_total_mean", 0) - est_dotd_pts(d2)

            # Approximate quali bonus from mean positions
            q1 = d1.get("mc_quali_pos_mean", 15)
            q2 = d2.get("mc_quali_pos_mean", 15)
            def q_tier_probs(mean_pos):
                p_q3 = max(0, min(1, (12 - mean_pos) / 5))
                p_q2 = max(0, min(1 - p_q3, (17 - mean_pos) / 5))
                p_q1 = 1 - p_q3 - p_q2
                return p_q3, p_q2, p_q1
            p1_q3, p1_q2, p1_q1 = q_tier_probs(q1)
            p2_q3, p2_q2, p2_q1 = q_tier_probs(q2)
            quali_bonus_est = 0.0
            quali_bonus_est += (p1_q3 * p2_q3) * 10
            quali_bonus_est += (p1_q3 * (1 - p2_q3) + p2_q3 * (1 - p1_q3)) * 5
            quali_bonus_est += ((1 - p1_q3) * p1_q2 * (1 - p2_q3) * p2_q2) * 3
            quali_bonus_est += ((1 - p1_q3) * p1_q2 * p2_q1 + (1 - p2_q3) * p2_q2 * p1_q1) * 1
            quali_bonus_est += (p1_q1 * p2_q1) * (-1)

            combined_mean = d1_pts + d2_pts + quali_bonus_est
            d1_std = d1.get("mc_total_std", 0)
            d2_std = d2.get("mc_total_std", 0)
            correlation = 0.3
            combined_std = float(np.sqrt(d1_std**2 + d2_std**2 +
                                         2 * correlation * d1_std * d2_std))
            combined_p5 = combined_mean - 1.65 * combined_std
            combined_p95 = combined_mean + 1.65 * combined_std
            avg_quali_bonus = quali_bonus_est

        constructor_results.append({
            "constructor_id": cid,
            "name": cinfo["name"],
            "driver_1": c_drivers[0],
            "driver_2": c_drivers[1],
            "mc_total_mean": round(combined_mean, 1),
            "mc_total_std": round(combined_std, 1),
            "mc_total_p5": round(combined_p5, 1),
            "mc_total_p95": round(combined_p95, 1),
            "mc_value_score": round(combined_mean / c_price, 2) if c_price > 0 else 0.0,
            "price": c_price,
            "quali_bonus": round(avg_quali_bonus, 1),
        })

    constructor_results.sort(key=lambda x: x["mc_total_mean"], reverse=True)
    return constructor_results


# ==============================================================================
# Output and display
# ==============================================================================

def print_summary(results: dict, constructor_results: list[dict]) -> None:
    """Print a formatted summary of Monte Carlo results."""
    drivers = results["drivers"]
    params = results["simulation_params"]

    # Sort by MC mean total points
    drivers_sorted = sorted(drivers, key=lambda d: d["mc_total_mean"], reverse=True)

    print(f"\n{'=' * 90}")
    print(f"MONTE CARLO FANTASY POINTS — {params['n_simulations']:,} Simulations")
    print(f"{'=' * 90}")

    print(f"\n{'Rk':>2} {'Driver':<6} {'Team':<14} {'Det':>4} {'MC Mean':>7} {'MC Med':>6} "
          f"{'Std':>5} {'P5':>5} {'P25':>5} {'P75':>5} {'P95':>5} "
          f"{'Top3%':>5} {'DNF%':>5}")
    print("-" * 90)

    for rank, d in enumerate(drivers_sorted, 1):
        det_pos = f"P{d['det_race_position']}"
        print(f"{rank:>2} {d['driver_abbrev']:<6} {d['constructor_id']:<14} "
              f"{det_pos:>4} {d['mc_total_mean']:>7.1f} {d['mc_total_median']:>6.1f} "
              f"{d['mc_total_std']:>5.1f} {d['mc_total_p5']:>5.1f} {d['mc_total_p25']:>5.1f} "
              f"{d['mc_total_p75']:>5.1f} {d['mc_total_p95']:>5.1f} "
              f"{d['prob_top3']*100:>5.1f} {d['mc_dnf_rate']*100:>5.1f}")

    # Constructors
    if constructor_results:
        print(f"\n{'Rk':>2} {'Constructor':<15} {'D1':<5} {'D2':<5} "
              f"{'MC Mean':>7} {'Std':>5} {'P5':>5} {'P95':>5} {'Val':>5}")
        print("-" * 60)
        for rank, c in enumerate(constructor_results, 1):
            print(f"{rank:>2} {c['name']:<15} {c['driver_1']:<5} {c['driver_2']:<5} "
                  f"{c['mc_total_mean']:>7.1f} {c['mc_total_std']:>5.1f} "
                  f"{c['mc_total_p5']:>5.1f} {c['mc_total_p95']:>5.1f} "
                  f"{c['mc_value_score']:>5.2f}")


def save_outputs(results: dict, constructor_results: list[dict],
                 round_num: int, driver_prices: dict) -> None:
    """Save Monte Carlo results to disk."""
    pred_dir = PREDICTIONS_DIR / f"round{round_num}"
    pred_dir.mkdir(parents=True, exist_ok=True)

    # Add prices and value scores to driver results
    for d in results["drivers"]:
        price = driver_prices.get(d["driver_abbrev"], 0.0)
        d["price"] = price
        d["mc_value_score"] = round(d["mc_total_mean"] / price, 2) if price > 0 else 0.0

    # Save full MC results as JSON
    output = {
        "round": round_num,
        "simulation_params": results["simulation_params"],
        "drivers": sorted(results["drivers"],
                          key=lambda d: d["mc_total_mean"], reverse=True),
        "constructors": constructor_results,
    }

    json_path = pred_dir / "monte_carlo_fantasy.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved -> {json_path}")

    # Save as parquet for downstream use
    drivers_df = pd.DataFrame(results["drivers"])
    parquet_path = pred_dir / "monte_carlo_fantasy.parquet"
    drivers_df.to_parquet(parquet_path, index=False)
    print(f"  Saved -> {parquet_path}")

    # Update web predictions.json with MC data
    update_web_predictions(round_num, results, constructor_results)


def update_web_predictions(round_num: int, results: dict,
                           constructor_results: list[dict]) -> None:
    """Update the web predictions.json to include MC confidence intervals."""
    web_path = WEB_DATA_DIR / "predictions.json"
    if not web_path.exists():
        print(f"  Warning: {web_path} not found, skipping web update")
        return

    with open(web_path) as f:
        web_data = json.load(f)

    # Only update if this is for the current round
    if web_data.get("round") != round_num:
        print(f"  Warning: predictions.json is for round {web_data.get('round')}, "
              f"not round {round_num}. Skipping web update.")
        return

    # Build MC lookup
    mc_lookup = {d["driver_abbrev"]: d for d in results["drivers"]}
    mc_c_lookup = {c["constructor_id"]: c for c in constructor_results}

    # Enrich driver data
    for driver in web_data.get("drivers", []):
        abbrev = driver.get("driver_abbrev") or driver.get("driver_id")
        mc = mc_lookup.get(abbrev)
        if mc:
            driver["mc_total_mean"] = mc["mc_total_mean"]
            driver["mc_total_std"] = mc["mc_total_std"]
            driver["mc_total_p5"] = mc["mc_total_p5"]
            driver["mc_total_p25"] = mc["mc_total_p25"]
            driver["mc_total_p75"] = mc["mc_total_p75"]
            driver["mc_total_p95"] = mc["mc_total_p95"]
            driver["mc_upside"] = mc["mc_upside"]
            driver["mc_downside"] = mc["mc_downside"]
            driver["prob_top3"] = mc["prob_top3"]
            driver["prob_top5"] = mc["prob_top5"]
            driver["prob_top10"] = mc["prob_top10"]
            driver["mc_value_score"] = mc.get("mc_value_score", 0)

    # Enrich constructor data
    for constructor in web_data.get("constructors", []):
        cid = constructor.get("constructor_id")
        mc_c = mc_c_lookup.get(cid)
        if mc_c:
            constructor["mc_total_mean"] = mc_c["mc_total_mean"]
            constructor["mc_total_std"] = mc_c["mc_total_std"]
            constructor["mc_total_p5"] = mc_c["mc_total_p5"]
            constructor["mc_total_p95"] = mc_c["mc_total_p95"]
            constructor["mc_value_score"] = mc_c["mc_value_score"]

    # Add MC metadata
    web_data["monte_carlo"] = {
        "n_simulations": results["simulation_params"]["n_simulations"],
        "seed": results["simulation_params"]["seed"],
    }

    with open(web_path, "w") as f:
        json.dump(web_data, f, indent=2)
    print(f"  Updated -> {web_path} (with MC confidence intervals)")

    # Also update the per-round archive file
    archive_path = WEB_DATA_DIR / f"predictions_round{round_num}.json"
    if archive_path.exists():
        with open(archive_path, "w") as f:
            json.dump(web_data, f, indent=2)
        print(f"  Updated -> {archive_path} (with MC confidence intervals)")


# ==============================================================================
# Main
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monte Carlo Fantasy Points Simulation"
    )
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON, help="Season year")
    parser.add_argument("--simulations", "-n", type=int, default=DEFAULT_SIMULATIONS,
                        help=f"Number of simulations (default: {DEFAULT_SIMULATIONS:,})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed (default: {DEFAULT_SEED})")
    args = parser.parse_args()

    if args.round in CANCELLED_ROUNDS_2026:
        print(f"Round {args.round} is cancelled.")
        return

    is_sprint = args.round in SPRINT_ROUNDS_2026

    print("=" * 90)
    print(f"BoxBoxF1Fantasy — Monte Carlo Fantasy Simulation")
    print(f"  Round {args.round} | {args.simulations:,} simulations | "
          f"Seed {args.seed} | Sprint: {is_sprint}")
    print("=" * 90)

    # Load data
    print("\n  Loading predictions...")
    pred_df = load_predictions(args.round)
    fantasy_df = load_fantasy_points(args.round)
    driver_prices = load_driver_prices()
    constructor_prices = load_constructor_prices()
    drivers_info = load_drivers_info()
    constructors_info = load_constructors_info()

    print(f"  {len(pred_df)} drivers loaded")

    # Run simulations
    results = run_simulations(
        pred_df=pred_df,
        fantasy_df=fantasy_df,
        n_sims=args.simulations,
        seed=args.seed,
        is_sprint=is_sprint,
    )

    # Load pitstop priors for constructor simulation
    pitstop_priors = load_pitstop_priors()
    print(f"  Loaded pit stop priors for {len(pitstop_priors)} teams")

    # Aggregate constructors (per-iteration simulation with pit stops)
    constructor_results = aggregate_constructors(
        results["drivers"], drivers_info, constructors_info, constructor_prices,
        sim_arrays=results.get("_sim_arrays"),
        pitstop_priors=pitstop_priors,
        n_sims=args.simulations,
        seed=args.seed,
    )

    # Display and save
    print_summary(results, constructor_results)
    save_outputs(results, constructor_results, args.round, driver_prices)

    print(f"\n{'=' * 90}")
    print("Done.")


if __name__ == "__main__":
    main()
