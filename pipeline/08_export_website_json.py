"""
Script 08 — Export Website JSON

Exports all data for the website frontend:
- Current round predictions + fantasy points
- Historical round results and predictions archive
- FP analysis (if available)
- Post-race analysis (if available)
- Season summary (standings, price trends, PPM)

Usage:
    python pipeline/08_export_website_json.py --round 3

Output:
    web/public/data/predictions.json        (current round)
    web/public/data/predictions_round{N}.json (archive)
    web/public/data/season_summary.json     (cumulative)
    web/public/data/fp_analysis.json        (current round FP)
    web/public/data/post_race_round{N}.json (per-round post-race)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    PREDICTIONS_DIR,
    WEB_DATA_DIR,
    SEED_DIR,
    RAW_DIR,
    FEATURES_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
    is_race_completed,
)
from config.track_classifications import (
    TRACK_DATABASE,
    TRACK_FEATURE_NAMES,
    RACE_NAME_TO_CIRCUIT,
)
from pipeline.audit import (
    record_prediction_event,
    load_prediction_metadata,
    load_actuals,
)
from pipeline.prediction_sanity import print_report as _sanity_report
from config.fantasy_prices import (
    current_price_mismatches,
    load_fantasy_price_data,
)


VALID_PHASES = ("pre_fp", "post_fp", "post_quali")


def detect_phase(round_num: int, year: int = CURRENT_SEASON) -> str:
    """Detect which pipeline phase produced the current predictions.

    Used to tag the prediction archive (predictions_round{N}_{phase}.json) so
    the accuracy page can show how the forecast evolved as data arrived.

    PRIORITY ORDER:
      1. **prediction_metadata.json sidecar** — written by 06_run_predictions
         at predict time. Definitive: records the phase the predictor actually
         ran in, including whether it loaded FP features and whether actual
         quali was available. This is the source of truth when present.
      2. Data-state inference (legacy fallback) — best-effort lookup based on
         what's available now. Less reliable: current data state can differ
         from what was available when the prediction was made.
    """
    # Source of truth: the sidecar written by 06_run_predictions.
    sidecar = PREDICTIONS_DIR / f"round{round_num}" / "prediction_metadata.json"
    if sidecar.exists():
        try:
            with open(sidecar) as f:
                meta = json.load(f)
            phase = meta.get("phase")
            if phase in VALID_PHASES:
                return phase
        except Exception:
            pass

    # Legacy fallback: infer from data files. Only used when the sidecar is
    # missing (e.g. for archives generated before the sidecar mechanism existed).
    quali_path = RAW_DIR / "jolpica" / f"year{year}" / f"round{round_num}" / "qualifying.json"
    if quali_path.exists():
        try:
            with open(quali_path) as f:
                data = json.load(f)
            races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            if races and races[0].get("QualifyingResults"):
                return "post_quali"
        except Exception:
            pass

    fp_features_dir = FEATURES_DIR / f"round{round_num}"
    if fp_features_dir.exists() and any(fp_features_dir.glob("*.parquet")):
        return "post_fp"

    return "pre_fp"


def write_archive_safely(
    archive_path: Path,
    payload: dict,
    round_num: int,
    label: str,
    force: bool = False,
) -> None:
    """Write a per-round archive, refusing to overwrite a past-race archive
    unless force=True. This is the second line of defense against accidentally
    polluting the accuracy archive.
    """
    if archive_path.exists() and is_race_completed(round_num) and not force:
        print(f"  [SKIP] {label}: race for round {round_num} has happened and "
              f"archive exists — refusing to overwrite (use --force to override)")
        return
    with open(archive_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  Wrote -> {archive_path}")


def load_race_info() -> dict:
    """Load race calendar."""
    with open(SEED_DIR / "races.json") as f:
        data = json.load(f)
    return {r["round"]: r for r in data["races"]}


def load_driver_info() -> dict:
    """Load driver metadata keyed by abbreviation."""
    with open(SEED_DIR / "drivers.json") as f:
        return {d["driver_id"]: d for d in json.load(f)["drivers"]}


def load_constructor_info() -> dict:
    """Load constructor metadata."""
    with open(SEED_DIR / "constructors.json") as f:
        return {c["constructor_id"]: c for c in json.load(f)["constructors"]}


def _warn_if_prices_stale() -> None:
    """Warn when price history is behind or top-level prices are inconsistent.

    Without this check, you can run a whole prediction phase with stale prices
    and silently produce wrong price-change brackets, wrong value scores, and a
    wrong PPM rating — exactly the trap that hit us at Miami (R6).
    """
    prices_path = SEED_DIR / "fantasy_prices.json"
    races_path = SEED_DIR / "races.json"
    actuals_dir = SEED_DIR.parent / "predictions"
    if not prices_path.exists() or not races_path.exists():
        return
    try:
        with open(prices_path) as f:
            prices = json.load(f)
        with open(races_path) as f:
            races = json.load(f).get("races", [])
    except Exception:
        return

    price_history = prices.get("price_history", {})
    if not price_history:
        return
    latest_priced_round = max(int(k) for k in price_history.keys())
    mismatches = current_price_mismatches(prices)

    if mismatches:
        mismatch_count = sum(len(group) for group in mismatches.values())
        print()
        print("  " + "!" * 78)
        print("  ! WARNING: top-level current prices disagree with the latest")
        print(f"  ! price_history snapshot for {mismatch_count} asset(s).")
        print("  ! Runtime consumers will use the history snapshot, but the seed")
        print("  ! file should be synchronized before committing.")
        print("  " + "!" * 78)
        print()

    # Find the highest completed round (has actual_fantasy_points.json on disk)
    highest_actual = 0
    for r in races:
        rnd = r.get("round", 0)
        if r.get("cancelled"):
            continue
        actual_path = actuals_dir / f"round{rnd}" / "actual_fantasy_points.json"
        if actual_path.exists():
            highest_actual = max(highest_actual, rnd)

    if highest_actual > latest_priced_round:
        print()
        print("  " + "!" * 78)
        print(f"  ! WARNING: prices in fantasy_prices.json look stale.")
        print(f"  !   - latest price_history entry: round {latest_priced_round}")
        print(f"  !   - highest completed race:     round {highest_actual}")
        print(f"  !")
        print(f"  ! Every downstream value (price-change brackets, PPM ratings, ")
        print(f"  ! value scores, optimizer 'budget_gain' strategy) is being computed ")
        print(f"  ! with prices from BEFORE round {highest_actual}.")
        print(f"  !")
        print(f"  ! Fix: update data/seed/fantasy_prices.json with the post-round-")
        print(f"  ! {highest_actual} prices for every driver and constructor, then re-run.")
        print("  " + "!" * 78)
        print()


def load_fantasy_prices() -> dict:
    """Load current fantasy prices."""
    return load_fantasy_price_data()


def build_predictions_json(round_num: int) -> dict | None:
    """Build the main predictions.json for a round."""
    race_info = load_race_info()
    driver_info = load_driver_info()
    constructor_info = load_constructor_info()
    prices = load_fantasy_prices()

    race = race_info.get(round_num, {})
    race_name = race.get("name", f"Round {round_num}")
    is_sprint = round_num in SPRINT_ROUNDS_2026

    # Load fantasy points
    driver_path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points.parquet"
    constructor_path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points_constructors.parquet"

    if not driver_path.exists():
        print(f"  No fantasy data for round {round_num}")
        return None

    driver_df = pd.read_parquet(driver_path)
    constructor_df = pd.read_parquet(constructor_path) if constructor_path.exists() else pd.DataFrame()

    # Load raw XGBRanker scores from predictions.parquet so the website can do
    # client-side what-if re-ranking (see web/public/scenarios.js). Without these
    # the user-scenarios overlay can't simulate per-driver pace bumps.
    raw_by_driver: dict[str, dict[str, float]] = {}
    sprint_pos_by_driver: dict[str, int] = {}
    pred_parquet_path = PREDICTIONS_DIR / f"round{round_num}" / "predictions.parquet"
    if pred_parquet_path.exists():
        try:
            pred_df = pd.read_parquet(pred_parquet_path)
            for _, prow in pred_df.iterrows():
                abbrev = prow.get("driver_abbrev", prow.get("driver_id"))
                if not abbrev:
                    continue
                entry = {}
                for col, key in [
                    ("predicted_quali_raw", "quali"),
                    ("predicted_race_raw", "race"),
                    ("predicted_sprint_raw", "sprint"),
                ]:
                    if col in prow and pd.notna(prow[col]):
                        entry[key] = float(prow[col])
                raw_by_driver[abbrev] = entry
                if "predicted_sprint_position" in prow and pd.notna(prow.get("predicted_sprint_position")):
                    sprint_pos_by_driver[abbrev] = int(prow["predicted_sprint_position"])
        except Exception as e:
            print(f"  Warning: Could not load raw scores: {e}")

    # Build price lookup from latest fantasy_prices.json
    driver_prices = {}
    if prices and "drivers" in prices:
        for abbrev, p in prices["drivers"].items():
            driver_prices[abbrev] = p["current_price"]
    constructor_prices = {}
    if prices and "constructors" in prices:
        for cid, p in prices["constructors"].items():
            constructor_prices[cid] = p["current_price"]

    # Build driver entries
    drivers_json = []
    for _, row in driver_df.sort_values("total_expected_fantasy_points", ascending=False).iterrows():
        abbrev = row.get("driver_abbrev", row.get("driver_id", ""))
        info = driver_info.get(abbrev, {})

        entry = {
            "driver_id": abbrev,
            "name": f"{info.get('first_name', '')} {info.get('last_name', '')}".strip() or abbrev,
            "constructor": info.get("constructor_id", row.get("constructor_id", "")),
            "number": info.get("number", 0),
            "predicted_quali": int(row["predicted_quali_position"]),
            "predicted_grid": int(row.get(
                "predicted_grid_position", row["predicted_quali_position"]
            )),
            "grid_penalty_places": int(row.get("grid_penalty_places", 0)),
            "grid_back_of_grid": bool(row.get("grid_back_of_grid", False)),
            "predicted_finish": int(row["predicted_race_position"]),
            # projected_points = deterministic total (score if the predicted finishing
            # order holds). expected_points is overwritten below with the risk-adjusted
            # MC mean; we keep BOTH so the UI can show projected vs risk-adjusted.
            "projected_points": round(float(row["total_expected_fantasy_points"]), 1),
            "expected_points": round(float(row["total_expected_fantasy_points"]), 1),
            "expected_points_quali": round(float(row.get("expected_quali_pts", row.get("expected_fantasy_points_from_quali", 0))), 1),
            "expected_points_race": round(float(row.get("expected_race_pts", row.get("expected_fantasy_points_from_race", 0))), 1),
            "confidence": int(row.get("confidence", 50)),
            "risk": row.get("risk_label", "MEDIUM"),
            "risk_rating": float(row.get("risk_rating", 15)),
            "dnf_probability": float(row.get("dnf_probability", 0.15)),
            "expected_overtakes": int(row.get("expected_overtakes", 0)),
            "expected_positions_gained_lost": int(row.get("expected_positions_gained_lost", 0)),
            "fastest_lap_probability": float(row.get("fastest_lap_probability", 0.05)),
            "dotd_probability": float(row.get("dotd_probability", 0.05)),
            "points_per_million": float(row.get("points_per_million", 0)),
            "value_score": float(row.get("value_score", 0)),
            "current_price": float(row.get("current_price", 10)),
        }

        # Override price from latest fantasy_prices.json if available
        if abbrev in driver_prices:
            entry["current_price"] = driver_prices[abbrev]

        if is_sprint:
            entry["expected_points_sprint_quali"] = round(
                float(row.get("expected_sprint_quali_pts", 0)), 1
            )
            entry["expected_points_sprint_race"] = round(
                float(row.get("expected_sprint_race_pts", 0)), 1
            )

        # Raw XGBRanker scores per session — consumed by the client-side
        # user-scenarios overlay to re-rank when the user dials a pace bump.
        raw = raw_by_driver.get(abbrev) or {}
        if raw:
            entry["raw_scores"] = {k: round(v, 6) for k, v in raw.items()}
        if abbrev in sprint_pos_by_driver:
            entry["predicted_sprint"] = sprint_pos_by_driver[abbrev]

        drivers_json.append(entry)

    # Merge Monte Carlo data if available
    mc_path = PREDICTIONS_DIR / f"round{round_num}" / "monte_carlo_fantasy.json"
    weather_adjustments_active = None
    calibration_meta = None
    if mc_path.exists():
        try:
            with open(mc_path) as f:
                mc_data = json.load(f)
            # Capture weather adjustments metadata for the frontend badges
            sim_params = mc_data.get("simulation_params", {})
            weather_adjustments_active = sim_params.get("weather_adjustments_active")
            # Surface calibration metadata so the frontend can show users which
            # adjustments are being applied to predictions. None of these fields
            # change the numbers (those are already baked into the per-driver
            # values above) — they only document what was done.
            calibration_meta = {
                "noise_multiplier": sim_params.get("noise_multiplier"),
                "bias_correction_global": sim_params.get("bias_correction_global"),
                "bias_correction_per_tier": sim_params.get("bias_correction_per_tier"),
                "bias_correction_applied": sim_params.get("bias_correction_applied", False),
                "calibration_rounds": sim_params.get("calibration_rounds"),
            }
            mc_by_driver = {d["driver_abbrev"]: d for d in mc_data.get("drivers", [])}
            for entry in drivers_json:
                mc = mc_by_driver.get(entry["driver_id"])
                if mc:
                    entry["mc_total_mean"] = round(mc.get("mc_total_mean", 0), 1)
                    entry["mc_total_std"] = round(mc.get("mc_total_std", 0), 1)
                    entry["mc_total_p5"] = round(mc.get("mc_total_p5", 0), 1)
                    entry["mc_total_p25"] = round(mc.get("mc_total_p25", 0), 1)
                    entry["mc_total_p75"] = round(mc.get("mc_total_p75", 0), 1)
                    entry["mc_total_p95"] = round(mc.get("mc_total_p95", 0), 1)
                    entry["mc_upside"] = round(mc.get("mc_upside", 0), 1)
                    entry["mc_dnf_rate"] = round(mc.get("mc_dnf_rate", 0), 1)
                    entry["mc_overtakes_mean"] = round(mc.get("mc_overtakes_mean", 0), 1)
                    entry["mc_quali_pts_mean"] = round(mc.get("mc_quali_pts_mean", 0), 1)
                    entry["mc_race_pts_mean"] = round(mc.get("mc_race_pts_mean", 0), 1)
                    # Use MC mean as primary expected_points (more accurate than deterministic)
                    entry["expected_points"] = round(mc.get("mc_total_mean", 0), 1)
                    entry["expected_points_quali"] = round(mc.get("mc_quali_pts_mean", 0), 1)
                    entry["expected_points_race"] = round(mc.get("mc_race_pts_mean", 0), 1)
                    # Recalculate value score with MC points
                    price = entry.get("current_price", 0)
                    if price > 0:
                        entry["value_score"] = round(entry["expected_points"] / price, 2)
            mc_by_con = {c["constructor_id"]: c for c in mc_data.get("constructors", [])}
        except Exception as e:
            print(f"  Warning: Could not load MC data: {e}")
            mc_by_con = {}
    else:
        mc_by_con = {}

    # Build constructor entries
    constructors_json = []
    for _, row in constructor_df.sort_values("total_expected_fantasy_points", ascending=False).iterrows():
        cid = row["constructor_id"]
        info = constructor_info.get(cid, {})

        entry = {
            "constructor_id": cid,
            "name": info.get("name", row.get("constructor_name", "")),
            "full_name": info.get("full_name", ""),
            "driver_1": row.get("driver_1", ""),
            "driver_2": row.get("driver_2", ""),
            # projected_points = deterministic; expected_points overwritten below with MC mean.
            "projected_points": round(float(row["total_expected_fantasy_points"]), 1),
            "expected_points": round(float(row["total_expected_fantasy_points"]), 1),
            "expected_points_quali": round(float(row.get("expected_quali_pts", 0)), 1),
            "expected_points_race": round(float(row.get("expected_race_pts", 0)), 1),
            "expected_pit_stop_pts": round(float(row.get("expected_pit_stop_pts", 0)), 1),
            "expected_dnf_impact": round(float(row.get("expected_dnf_impact", 0)), 1),
            "dnf_probability": round(float(row.get("dnf_probability", 0.02)), 2),
            "quali_bonus": int(row.get("quali_bonus", 0)),
            "risk": row.get("risk_label", "MEDIUM"),
            "risk_rating": float(row.get("risk_rating", 15)),
            "value_score": float(row.get("value_score", 0)),
            "current_price": float(row.get("current_price", 10)),
        }

        # Override price from latest fantasy_prices.json if available
        if cid in constructor_prices:
            entry["current_price"] = constructor_prices[cid]

        if is_sprint:
            entry["expected_points_sprint_quali"] = round(float(row.get("expected_sprint_quali_pts", 0)), 1)
            entry["expected_points_sprint_race"] = round(float(row.get("expected_sprint_race_pts", 0)), 1)

        # Merge MC data for constructor if available
        mc_c = mc_by_con.get(cid) if mc_by_con else None
        if mc_c:
            entry["mc_total_mean"] = round(mc_c.get("mc_total_mean", 0), 1)
            entry["mc_total_std"] = round(mc_c.get("mc_total_std", 0), 1)
            entry["mc_total_p5"] = round(mc_c.get("mc_total_p5", 0), 1)
            entry["mc_total_p25"] = round(mc_c.get("mc_total_p25", 0), 1)
            entry["mc_total_p75"] = round(mc_c.get("mc_total_p75", 0), 1)
            entry["mc_total_p95"] = round(mc_c.get("mc_total_p95", 0), 1)
            entry["mc_pit_stop_pts"] = round(mc_c.get("mc_pit_stop_pts", 0), 1)
            entry["mc_dnf_prob"] = round(mc_c.get("mc_dnf_prob", 0.02), 3)
            # Use MC mean as primary expected_points
            entry["expected_points"] = round(mc_c.get("mc_total_mean", 0), 1)
            # Override pit stop pts from MC if available
            if mc_c.get("mc_pit_stop_pts", 0) > 0:
                entry["expected_pit_stop_pts"] = round(mc_c["mc_pit_stop_pts"], 1)
            price = entry.get("current_price", 0)
            if price > 0:
                entry["value_score"] = round(entry["expected_points"] / price, 2)

        constructors_json.append(entry)

    # ----- Team upgrade adjustments (manual modifiers) -----
    # If pipeline/apply_upgrades.py wrote an adjustments.json for this round,
    # merge per-driver adjusted_expected_points / predicted_finish_adjusted etc.
    # The base ML fields (expected_points, predicted_finish) are NOT touched —
    # the adjusted values live alongside as a toggle-able overlay on the site.
    adj_path = PREDICTIONS_DIR / f"round{round_num}" / "adjustments.json"
    upgrade_meta = None
    if adj_path.exists():
        try:
            with open(adj_path) as f:
                adj_data = json.load(f)
            by_driver = {d["driver_abbrev"]: d for d in adj_data.get("drivers", [])}
            modifiers_applied = adj_data.get("modifiers_applied", {})
            driver_modifiers_applied = adj_data.get("driver_modifiers_applied", {})
            constructor_pts_delta = {cid: 0.0 for cid in modifiers_applied}
            for entry in drivers_json:
                d_adj = by_driver.get(entry["driver_id"])
                if not d_adj:
                    continue
                pts_delta = float(d_adj.get("total_points_delta", 0))
                entry["expected_points_adjusted"] = round(entry["expected_points"] + pts_delta, 1)
                entry["points_delta"] = round(pts_delta, 1)
                entry["predicted_quali_adjusted"] = d_adj["adjusted"]["quali"]
                entry["predicted_finish_adjusted"] = d_adj["adjusted"]["race"]
                if "sprint" in d_adj["adjusted"]:
                    entry["predicted_sprint_adjusted"] = d_adj["adjusted"]["sprint"]
                entry["pace_bump"] = round(float(d_adj.get("pace_bump", 0)), 2)
                # Roll up the constructor's points delta = sum of both drivers'
                # quali + race + sprint deltas (driver-level position-points only,
                # excludes DOTD — same exclusion the real constructor scoring uses).
                cid = entry.get("constructor")
                if cid in constructor_pts_delta:
                    q = d_adj.get("points_delta", {}).get("quali", 0)
                    r = d_adj.get("points_delta", {}).get("race", 0)
                    s = d_adj.get("points_delta", {}).get("sprint", 0)
                    constructor_pts_delta[cid] += float(q + r + s)
            for c_entry in constructors_json:
                cid = c_entry.get("constructor_id")
                if cid in constructor_pts_delta:
                    delta = constructor_pts_delta[cid]
                    c_entry["expected_points_adjusted"] = round(c_entry["expected_points"] + delta, 1)
                    c_entry["points_delta"] = round(delta, 1)
                    c_entry["pace_bump"] = round(float(modifiers_applied.get(cid, 0)), 2)
            upgrade_meta = {
                "modifiers": modifiers_applied,
                "driver_modifiers": driver_modifiers_applied,
                "scope": adj_data.get("scope", "all"),
            }
            print(f"  Merged upgrade adjustments: {len(modifiers_applied)} team(s), {len(driver_modifiers_applied)} driver(s), scope={upgrade_meta['scope']}")
        except Exception as e:
            print(f"  Warning: Could not load team upgrade adjustments: {e}")

    # Per-session adjacent-gap median in raw-score space. The user-scenarios
    # overlay uses these to convert "positions gained" (UI surface unit) into
    # raw-score bumps: bump_per_position ≈ gap_median. A wider gap means it
    # takes more pace to gain a position on that session.
    score_unit = {}
    for key in ("quali", "race", "sprint"):
        values = sorted(
            (r.get(key) for r in raw_by_driver.values() if key in r),
            reverse=True,
        )
        if len(values) < 2:
            continue
        gaps = [abs(values[i] - values[i + 1]) for i in range(len(values) - 1)]
        gaps.sort()
        mid = len(gaps) // 2
        median = gaps[mid] if len(gaps) % 2 else 0.5 * (gaps[mid - 1] + gaps[mid])
        # Guard against degenerate (all-zero) raw scores.
        if median > 1e-9:
            score_unit[f"{key}_gap_median"] = round(median, 6)

    payload = {
        "race": race_name,
        "round": round_num,
        "season": CURRENT_SEASON,
        "circuit": race.get("circuit", ""),
        "date": race.get("date", ""),
        "is_sprint_weekend": is_sprint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "drivers": drivers_json,
        "constructors": constructors_json,
    }
    if score_unit:
        payload["score_unit"] = score_unit
    if upgrade_meta:
        payload["upgrade_adjustments"] = upgrade_meta
    if weather_adjustments_active is not None:
        # Surfaced to the frontend so driver/constructor cards can show
        # wet/cold badges and the weather widget can render an explainer
        # of what's being adjusted in the Monte Carlo.
        payload["weather_adjustments"] = weather_adjustments_active
    if calibration_meta is not None:
        payload["calibration"] = calibration_meta
    return payload


def build_season_summary() -> dict:
    """
    Build season summary: completed rounds with results,
    price history, cumulative PPM, and standings.
    """
    race_info = load_race_info()
    driver_info = load_driver_info()
    prices = load_fantasy_prices()

    # Gather completed rounds
    completed_rounds = []
    for rnd_num in range(1, 25):
        pred_path = PREDICTIONS_DIR / f"round{rnd_num}" / "fantasy_points.parquet"
        post_race_path = PREDICTIONS_DIR / f"round{rnd_num}" / "post_race_analysis.json"
        actual_path = PREDICTIONS_DIR / f"round{rnd_num}" / "actual_fantasy_points.json"

        race = race_info.get(rnd_num, {})
        if race.get("cancelled"):
            continue

        round_entry = {
            "round": rnd_num,
            "name": race.get("name", f"Round {rnd_num}"),
            "circuit": race.get("circuit", ""),
            "date": race.get("date", ""),
            "has_predictions": pred_path.exists(),
            "has_post_race": post_race_path.exists(),
            "has_actual": actual_path.exists(),
        }
        completed_rounds.append(round_entry)

    # Driver price data
    driver_prices = {}
    if prices and "drivers" in prices:
        for abbrev, p in prices["drivers"].items():
            info = driver_info.get(abbrev, {})
            change = p["current_price"] - p["starting_price"]
            driver_prices[abbrev] = {
                "name": f"{info.get('first_name', '')} {info.get('last_name', '')}".strip() or abbrev,
                "constructor": info.get("constructor_id", ""),
                "current_price": p["current_price"],
                "starting_price": p["starting_price"],
                "price_change": round(change, 1),
                "price_trend": "up" if change > 0.2 else ("down" if change < -0.2 else "stable"),
            }

    # Constructor price data
    constructor_price_data = {}
    constructor_info = load_constructor_info()
    if prices and "constructors" in prices:
        for cid, p in prices["constructors"].items():
            info = constructor_info.get(cid, {})
            change = p["current_price"] - p["starting_price"]
            constructor_price_data[cid] = {
                "name": info.get("name", cid),
                "full_name": info.get("full_name", cid),
                "current_price": p["current_price"],
                "starting_price": p["starting_price"],
                "price_change": round(change, 1),
                "price_trend": "up" if change > 0.2 else ("down" if change < -0.2 else "stable"),
            }

    return {
        "season": CURRENT_SEASON,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rounds": completed_rounds,
        "driver_prices": driver_prices,
        "constructor_prices": constructor_price_data,
    }


def copy_analysis_files(round_num: int) -> None:
    """Copy FP and post-race analysis JSONs to web data dir."""
    # FP analysis
    fp_path = PREDICTIONS_DIR / f"round{round_num}" / "fp_analysis.json"
    if fp_path.exists():
        with open(fp_path) as f:
            data = json.load(f)
        out = WEB_DATA_DIR / "fp_analysis.json"
        with open(out, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Copied FP analysis -> {out}")

    # Post-race analysis (copy all available)
    for rnd in range(1, 25):
        pr_path = PREDICTIONS_DIR / f"round{rnd}" / "post_race_analysis.json"
        if pr_path.exists():
            with open(pr_path) as f:
                data = json.load(f)
            out = WEB_DATA_DIR / f"post_race_round{rnd}.json"
            with open(out, "w") as f:
                json.dump(data, f, indent=2)


def sync_official_points() -> None:
    """Sync official fantasy points from seed to web data directory."""
    src = SEED_DIR / "official_fantasy_points.json"
    dst = WEB_DATA_DIR / "official_points.json"
    if src.exists():
        with open(src) as f:
            data = json.load(f)
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
        n_rounds = len(data.get("rounds", {}))
        print(f"  Synced official points ({n_rounds} rounds) -> {dst}")
    else:
        print("  No official_fantasy_points.json seed file found, skipping")


def sync_pitstop_points() -> None:
    """Sync manually-recorded official pit-stop points from seed to web data."""
    src = SEED_DIR / "pitstop_points.json"
    dst = WEB_DATA_DIR / "pitstop_points.json"
    if src.exists():
        with open(src) as f:
            data = json.load(f)
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Synced official pit-stop points ({len(data.get('rounds', {}))} rounds) -> {dst}")
    else:
        print("  No pitstop_points.json seed file found, skipping")


def build_track_data_json() -> dict:
    """Export track classification data for frontend track similarity engine.

    Exports the 9-dimensional feature vectors, race-to-circuit mapping, and
    feature names for computing cosine similarity in the browser.
    Only includes circuits on the 2026 calendar (not historical one-offs).
    """
    # Load race calendar to get active circuit IDs
    with open(SEED_DIR / "races.json") as f:
        races = json.load(f)["races"]

    active_circuits = set()
    race_circuit_map = {}
    for race in races:
        if race.get("cancelled"):
            continue
        race_name = race["name"].lower().strip()
        circuit_id = RACE_NAME_TO_CIRCUIT.get(race_name, "unknown")
        if circuit_id != "unknown":
            active_circuits.add(circuit_id)
            race_circuit_map[race["name"]] = circuit_id

    # Export track features (only active circuits + some similar ones for similarity)
    track_features = {}
    for cid, features in TRACK_DATABASE.items():
        if cid in active_circuits:
            track_features[cid] = features

    return {
        "track_features": track_features,
        "race_circuit_map": race_circuit_map,
        "feature_names": TRACK_FEATURE_NAMES,
        "sprint_rounds": SPRINT_ROUNDS_2026,
    }


def build_driver_history_json() -> dict:
    """Export per-driver and per-constructor actual fantasy points by round.

    Aggregates from actual_round{N}.json files in web data directory.
    Used by the multi-week planner for track-affinity scoring.
    """
    race_info = load_race_info()
    drivers = {}
    constructors = {}

    for rnd_num in range(1, 25):
        if rnd_num in CANCELLED_ROUNDS_2026:
            continue

        actual_path = WEB_DATA_DIR / f"actual_round{rnd_num}.json"
        if not actual_path.exists():
            continue

        with open(actual_path) as f:
            actual = json.load(f)

        race = race_info.get(rnd_num, {})
        race_name = race.get("name", "").lower().strip()
        circuit_id = RACE_NAME_TO_CIRCUIT.get(race_name, "unknown")

        # Driver points
        for d in actual.get("drivers", []):
            did = d["driver_id"]
            if did not in drivers:
                drivers[did] = {"rounds": []}
            drivers[did]["rounds"].append({
                "round": rnd_num,
                "circuit_id": circuit_id,
                "points": d.get("total_points", 0),
                "is_dnf": d.get("is_dnf", False),
            })

        # Constructor points
        for c in actual.get("constructors", []):
            cid = c["constructor_id"]
            if cid not in constructors:
                constructors[cid] = {"rounds": []}
            constructors[cid]["rounds"].append({
                "round": rnd_num,
                "circuit_id": circuit_id,
                "points": c.get("total_points", 0),
            })

    return {
        "season": CURRENT_SEASON,
        "drivers": drivers,
        "constructors": constructors,
    }


def main():
    parser = argparse.ArgumentParser(description="Export website JSON data")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--phase", choices=("auto", *VALID_PHASES), default="auto",
                        help="Pipeline phase that produced this prediction "
                             "(pre_fp/post_fp/post_quali). Default 'auto' detects from data state.")
    parser.add_argument("--force", action="store_true",
                        help="Override race-completed guards (overwrite existing per-round archives)")
    parser.add_argument("--reconstructed", action="store_true",
                        help="Mark this export as a post-hoc reconstruction (sets reconstructed=true in JSON)")
    parser.add_argument("--audit-label", type=str, default=None,
                        help="Free-form note to attach to the audit log entry (e.g. 'recovery', 'manual_rerun')")
    parser.add_argument("--no-audit", action="store_true",
                        help="Skip writing an audit log entry (use sparingly; defeats the safety net)")
    args = parser.parse_args()

    round_num = args.round
    print("=" * 70)
    print(f"BoxBoxF1Fantasy — Export Website JSON (Round {round_num})")
    print("=" * 70)

    if round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled.")
        return

    # Resolve phase
    phase = args.phase if args.phase != "auto" else detect_phase(round_num)
    print(f"  Phase: {phase}{' (auto-detected)' if args.phase == 'auto' else ''}")

    # Stale-price-check: warn if seasonSummary has more actuals than fantasy_prices
    # has price_history entries. After each race, prices in F1 Fantasy update — if
    # we forget to record the new prices in fantasy_prices.json, every downstream
    # calculation (price-change brackets, value scores, PPM) uses stale prices.
    _warn_if_prices_stale()

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Current round predictions
    print("\n[1] Exporting predictions...")
    predictions = build_predictions_json(round_num)
    if predictions:
        # Sanity guard: flag grossly-broken predictions (all zeros, NaNs, a
        # winner predicted to score single digits, ranking collapse) BEFORE we
        # write them to the live site. This is a smoke alarm — it does not block
        # the export (model output is the user's call), but it prints loud
        # problems so a regression like the bias-nerf can't ship silently.
        sane = _sanity_report(predictions, label=f"R{round_num} {phase}")
        if not sane and not args.force:
            print("  NOTE: sanity problems above. Export continues; re-check the model/MC "
                  "output. Pass --force to silence this note.")

        # Tag the payload with phase + reconstruction info
        predictions["phase"] = phase
        predictions["exported_at"] = datetime.now(timezone.utc).isoformat()
        if args.reconstructed:
            predictions["reconstructed"] = True

        # Current-round live file: this is what the homepage shows. Guard against
        # accidentally overwriting it with a past round's data — that happens when
        # you re-run --round N on a completed round to refresh derived data (e.g.
        # post-race pit stop corrections). The fix is to only overwrite the live
        # file when this round is genuinely the current/next upcoming round.
        live_path = WEB_DATA_DIR / "predictions.json"
        live_round = None
        if live_path.exists():
            try:
                with open(live_path) as f:
                    live_round = json.load(f).get("round")
            except (json.JSONDecodeError, OSError):
                live_round = None

        # If the current live file is for a LATER round than the one we're
        # exporting, the user is doing a backfill/refresh — don't downgrade
        # the homepage. The phase archive + canonical archive still get written.
        if (live_round is not None and isinstance(live_round, int)
                and round_num < live_round and not args.force):
            print(f"  [SKIP] live predictions.json: file shows round {live_round}, "
                  f"refusing to overwrite with older round {round_num} "
                  f"(use --force to override)")
        else:
            with open(live_path, "w") as f:
                json.dump(predictions, f, indent=2)

        # Phase-tagged archive: always written (this is the historical record
        # of "what we predicted at phase X")
        phase_archive = WEB_DATA_DIR / f"predictions_round{round_num}_{phase}.json"
        with open(phase_archive, "w") as f:
            json.dump(predictions, f, indent=2)
        print(f"  Wrote phase archive -> {phase_archive}")

        # Canonical archive: guarded against post-race overwrite
        canonical_archive = WEB_DATA_DIR / f"predictions_round{round_num}.json"
        write_archive_safely(
            canonical_archive,
            predictions,
            round_num,
            label="canonical archive",
            force=args.force,
        )
        print(f"  {len(predictions['drivers'])} drivers, {len(predictions['constructors'])} constructors")

        # Append-only audit log: record this prediction event with a full snapshot
        # in data/audit/. Survives canonical-archive overwrites and gives us a
        # recovery path if web/public/data/ files get corrupted.
        if not args.no_audit:
            try:
                audit_result = record_prediction_event(
                    round_num=round_num,
                    phase=phase,
                    predictions_json=predictions,
                    prediction_metadata=load_prediction_metadata(round_num),
                    actuals_json=load_actuals(round_num),
                    event_label=args.audit_label or ("reconstructed" if args.reconstructed else None),
                )
                print(f"  Audit -> {audit_result['snapshot_path']}")
            except Exception as e:
                print(f"  WARNING: audit logging failed: {e}")

    # 2. Season summary
    print("[2] Building season summary...")
    summary = build_season_summary()
    with open(WEB_DATA_DIR / "season_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  {len(summary['rounds'])} rounds, {len(summary['driver_prices'])} driver prices, {len(summary.get('constructor_prices', {}))} constructor prices")

    # 3. Sync official fantasy points
    print("[3] Syncing official points...")
    sync_official_points()
    sync_pitstop_points()

    # 4. Analysis files
    print("[4] Copying analysis files...")
    copy_analysis_files(round_num)

    # 5. Track data for multi-week planner
    print("[5] Exporting track data...")
    track_data = build_track_data_json()
    with open(WEB_DATA_DIR / "track_data.json", "w") as f:
        json.dump(track_data, f, indent=2)
    print(f"  {len(track_data['track_features'])} circuits, {len(track_data['race_circuit_map'])} race mappings")

    # 6. Driver history for multi-week planner
    print("[6] Exporting driver history...")
    history = build_driver_history_json()
    with open(WEB_DATA_DIR / "driver_history.json", "w") as f:
        json.dump(history, f, indent=2)
    print(f"  {len(history['drivers'])} drivers, {len(history['constructors'])} constructors with history")

    print(f"\nAll data exported to {WEB_DATA_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
