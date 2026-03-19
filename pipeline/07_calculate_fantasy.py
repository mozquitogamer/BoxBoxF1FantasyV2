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
)
from config.fantasy_scoring import (
    QUALIFYING_POSITION_POINTS,
    QUALIFYING_NC_DSQ_PENALTY,
    RACE_POSITION_POINTS,
    RACE_FASTEST_LAP_BONUS,
    RACE_DRIVER_OF_THE_DAY_BONUS,
    RACE_DNF_DSQ_PENALTY,
    SPRINT_POSITION_POINTS,
    SPRINT_FASTEST_LAP_BONUS,
    SPRINT_DNF_DSQ_PENALTY,
    RACE_POSITIONS_GAINED_PER_POS,
    CONSTRUCTOR_QUALI_BONUSES,
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
    Caps at 25% to avoid inflated rates from bad luck streaks.
    """
    risk = {}

    # Try to load pre-computed rolling DNF rates
    model_rows_path = JOLPICA_MODEL_ROWS_DIR / "all_model_rows.parquet"
    if model_rows_path.exists():
        mr = pd.read_parquet(model_rows_path)
        # Get each driver's most recent roll_dnf_rate_5
        latest = mr.sort_values(["season", "round"]).groupby("driver_id").last()
        if "roll_dnf_rate_5" in latest.columns:
            for driver_id, row in latest.iterrows():
                rate = row["roll_dnf_rate_5"]
                if pd.notna(rate):
                    # Cap at 25% — historical rates can be inflated by bad luck streaks
                    risk[driver_id] = round(min(rate, 0.25) * 100, 1)
                else:
                    risk[driver_id] = 5.0  # Default 5% for drivers with no history

    # Fill defaults for any driver not found
    for driver_id in predictions["driver_id"].unique():
        if driver_id not in risk:
            risk[driver_id] = 5.0  # Low default for new/unknown drivers

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


# -- Overtake estimation -------------------------------------------------------

def estimate_overtakes(predicted_quali: int, predicted_race: int, grid_size: int = 22) -> int:
    """
    Estimate expected overtakes based on grid position and 2026 regs.

    2026 regulations with active aero and ground effect produce dramatically more
    overtaking than previous years. Early 2026 races show even front-runners making
    5-10 overtakes and midfield/backmarkers routinely making 15-25+.
    Base values calibrated from Rounds 1-2 actual overtake data.
    """
    # Base overtakes by grid position (2026 regs — much higher than pre-2026)
    if predicted_quali <= 3:
        base = 5
    elif predicted_quali <= 7:
        base = 8
    elif predicted_quali <= 12:
        base = 12
    elif predicted_quali <= 17:
        base = 15
    else:
        base = 18

    # Additional overtakes from positions gained (2026: more wheel-to-wheel racing)
    positions_gained = max(0, predicted_quali - predicted_race)
    gained_overtakes = round(positions_gained * 1.5)

    return base + gained_overtakes


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
        est_overtakes = estimate_overtakes(pred_quali, pred_race)
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
        soft_dnf_penalty = RACE_DNF_DSQ_PENALTY * 0.6
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
            sprint_overtakes = estimate_overtakes(pred_sprint_quali, pred_sprint)
            sprint_fl_prob = fl_prob
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
        # However, DOTD should be excluded for constructors. Subtract the expected
        # DOTD contribution (it's small but correct to exclude).
        combined_race = d_data["expected_race_pts"].sum()

        # Combined positions gained/lost and overtakes from both drivers
        combined_pos_change = int(d_data["expected_positions_gained_lost"].sum())
        combined_overtakes = int(d_data["expected_overtakes"].sum())

        # Sprint
        combined_sprint_quali = d_data["expected_sprint_quali_pts"].sum() if is_sprint else 0
        combined_sprint_race = d_data["expected_sprint_race_pts"].sum() if is_sprint else 0

        total = total_quali + combined_race + combined_sprint_quali + combined_sprint_race

        price = constructor_prices.get(cid, 10.0)
        value_score = total / price if price > 0 else 0.0
        avg_risk = d_data["risk_rating"].mean()

        rows.append({
            "constructor_id": cid,
            "constructor_name": cname,
            "driver_1": driver_abbrevs[0] if len(driver_abbrevs) > 0 else "",
            "driver_2": driver_abbrevs[1] if len(driver_abbrevs) > 1 else "",
            "expected_quali_pts": round(total_quali, 1),
            "quali_bonus": quali_bonus,
            "expected_race_pts": round(combined_race, 1),
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
    args = parser.parse_args()

    round_num = args.round
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Fantasy Points for {args.year} Round {round_num}")
    print("=" * 70)

    if round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled.")
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
