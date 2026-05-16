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


VALID_PHASES = ("pre_fp", "post_fp", "post_quali")


def detect_phase(round_num: int, year: int = CURRENT_SEASON) -> str:
    """Detect which pipeline phase produced the current predictions.

    Used to tag the prediction archive (predictions_round{N}_{phase}.json) so
    the accuracy page can show how the forecast evolved as data arrived.

    NOTE: This is best-effort based on CURRENT data state. It labels by what's
    available now, not necessarily what was available when the prediction was
    made. For new predictions from run_weekend.py, --phase is passed explicitly
    and this auto-detection is bypassed.

    Detection heuristic (in priority order):
      - post_quali: jolpica/qualifying.json has QualifyingResults for this round
      - post_fp:    FP-derived feature parquets exist for this round
      - pre_fp:     otherwise (priors-only prediction)
    """
    # Post-quali check: does Jolpica have qualifying results for this round?
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

    # Post-FP check: do FP-derived feature parquets exist?
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


def load_fantasy_prices() -> dict:
    """Load current fantasy prices."""
    path = SEED_DIR / "fantasy_prices.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


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
            "predicted_finish": int(row["predicted_race_position"]),
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

        drivers_json.append(entry)

    # Merge Monte Carlo data if available
    mc_path = PREDICTIONS_DIR / f"round{round_num}" / "monte_carlo_fantasy.json"
    if mc_path.exists():
        try:
            with open(mc_path) as f:
                mc_data = json.load(f)
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

    return {
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

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Current round predictions
    print("\n[1] Exporting predictions...")
    predictions = build_predictions_json(round_num)
    if predictions:
        # Tag the payload with phase + reconstruction info
        predictions["phase"] = phase
        predictions["exported_at"] = datetime.now(timezone.utc).isoformat()
        if args.reconstructed:
            predictions["reconstructed"] = True

        # Current-round live file: always written (this is what the homepage shows)
        with open(WEB_DATA_DIR / "predictions.json", "w") as f:
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

    # 2. Season summary
    print("[2] Building season summary...")
    summary = build_season_summary()
    with open(WEB_DATA_DIR / "season_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  {len(summary['rounds'])} rounds, {len(summary['driver_prices'])} driver prices, {len(summary.get('constructor_prices', {}))} constructor prices")

    # 3. Sync official fantasy points
    print("[3] Syncing official points...")
    sync_official_points()

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
