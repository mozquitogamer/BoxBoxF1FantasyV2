"""
P9 — Predict next N rounds (priors-only) for the Multi-Week Transfer Planner.

Replaces the multi-week planner's track-similarity heuristic with actual ML
predictions for future rounds. Calls `run_predictions(round, skip_fp=True,
output_suffix="horizon")` for each upcoming round, then computes simplified
expected fantasy points from the predicted quali + race positions using the
same scoring formulas as 07_calculate_fantasy.py (minus the stochastic bonuses
like Driver of the Day and fastest lap, which average out as noise across a
projection horizon).

Output:
    web/public/data/horizon_projections.json — consumed by app.js's
    projectScoresForRound() to replace the affinity-based heuristic.

Usage:
    python pipeline/predict_horizon.py --current-round 7
    python pipeline/predict_horizon.py --current-round 7 --horizon 5
    python pipeline/predict_horizon.py --current-round 7 --year 2026 --horizon 3

The script writes a single JSON consumed by the multi-week planner; the
underlying per-round parquets are kept in data/predictions/round{N}/
predictions_horizon.parquet for audit/debugging but are not used by the website
directly.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Set up paths so we can import the pipeline modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    CURRENT_SEASON,
    CANCELLED_ROUNDS_2026,
    SPRINT_ROUNDS_2026,
    SEED_DIR,
    WEB_DATA_DIR,
)
from config.fantasy_scoring import (
    RACE_POSITION_POINTS,
    RACE_POSITIONS_GAINED_PER_POS,
    RACE_FASTEST_LAP_BONUS,
    RACE_DRIVER_OF_THE_DAY_BONUS,
    RACE_DNF_DSQ_PENALTY,
    SPRINT_POSITION_POINTS,
    SPRINT_FASTEST_LAP_BONUS,
    SPRINT_DNF_DSQ_PENALTY,
    calc_qualifying_points_driver,
)

# Lazy import of run_predictions so this script can fail early on bad args
# without paying the import cost of xgboost etc.
def _lazy_import_run_predictions():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_runpred_06", Path(__file__).resolve().parent / "06_run_predictions.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_predictions


# -- Simplified expected fantasy points from predicted positions --------------

def _expected_driver_points(
    pred_quali: int,
    pred_race: int,
    is_sprint: bool,
    pred_sprint_quali: int | None,
    pred_sprint: int | None,
) -> dict:
    """
    Same scoring logic as 07_calculate_fantasy.py::calculate_driver_fantasy,
    but with a SIMPLIFIED stochastic-bonus model (FL/DOTD/DNF probability
    estimates) so this script doesn't need to load risk-rating + price data
    just to project a future round. Returns the components separately so the
    consumer can introspect.
    """
    # -- Qualifying --
    quali_pts = calc_qualifying_points_driver(pred_quali)

    # -- Race --
    race_position_pts = RACE_POSITION_POINTS.get(pred_race, 0)
    pos_change = pred_quali - pred_race
    pos_pts = pos_change * RACE_POSITIONS_GAINED_PER_POS

    # Overtake estimate: positions gained captures most of it; cap to keep
    # projections sane for big-jump scenarios that won't realistically happen
    # every race.
    est_overtakes = max(0, min(pos_change, 8))

    # FL probability (matches 07_calculate_fantasy.py)
    if pred_race <= 3:
        fl_prob = 0.20
    elif pred_race <= 6:
        fl_prob = 0.10
    elif pred_race <= 10:
        fl_prob = 0.05
    else:
        fl_prob = 0.02
    expected_fl = fl_prob * RACE_FASTEST_LAP_BONUS

    # DOTD probability
    if pos_change >= 5 or pred_race <= 3:
        dotd_prob = 0.12
    elif pred_race <= 6:
        dotd_prob = 0.08
    else:
        dotd_prob = 0.03
    expected_dotd = dotd_prob * RACE_DRIVER_OF_THE_DAY_BONUS

    # DNF: use a fixed 8% league-average since we don't have risk ratings here.
    # 07_calculate_fantasy.py uses per-driver risk; the horizon projection
    # accepts the loss of precision in exchange for not needing the risk file.
    dnf_prob = 0.08
    race_if_finish = race_position_pts + pos_pts + est_overtakes + expected_fl + expected_dotd
    soft_dnf = RACE_DNF_DSQ_PENALTY * 0.6
    expected_race = (1 - dnf_prob) * race_if_finish + dnf_prob * soft_dnf

    # -- Sprint --
    sprint_quali_pts = 0.0
    sprint_race_pts = 0.0
    if is_sprint and pred_sprint_quali is not None and pred_sprint is not None:
        sprint_quali_pts = float(calc_qualifying_points_driver(pred_sprint_quali))
        sprint_pos_pts = SPRINT_POSITION_POINTS.get(pred_sprint, 0)
        sprint_pos_change = pred_sprint_quali - pred_sprint
        sprint_overtakes = max(0, min(sprint_pos_change, 4))  # tighter cap for shorter race
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
            (1 - dnf_prob) * (sprint_pos_pts + sprint_pos_change + sprint_overtakes + expected_sprint_fl)
            + dnf_prob * SPRINT_DNF_DSQ_PENALTY
        )

    total = quali_pts + expected_race + sprint_quali_pts + sprint_race_pts
    return {
        "quali_pts": round(quali_pts, 1),
        "race_pts": round(expected_race, 1),
        "sprint_quali_pts": round(sprint_quali_pts, 1) if is_sprint else 0,
        "sprint_race_pts": round(sprint_race_pts, 1) if is_sprint else 0,
        "total": round(total, 1),
    }


def _load_driver_id_maps() -> tuple[dict, dict]:
    """Local copy of 06_run_predictions.py::load_driver_id_maps."""
    with open(SEED_DIR / "driver_ids.json") as f:
        data = json.load(f)
    abbrev_to_jolpica = {m["abbrev"]: m["jolpica"] for m in data["mappings"]}
    jolpica_to_abbrev = {m["jolpica"]: m["abbrev"] for m in data["mappings"]}
    return abbrev_to_jolpica, jolpica_to_abbrev


def _load_constructor_for_driver() -> dict[str, str]:
    """Return abbrev -> constructor_id for current-season drivers."""
    with open(SEED_DIR / "drivers.json") as f:
        data = json.load(f)
    return {d["driver_id"]: d.get("constructor_id", "") for d in data["drivers"]}


def _load_race_info(year: int) -> dict[int, dict]:
    """Return {round: race_dict} from races.json, excluding cancelled rounds."""
    with open(SEED_DIR / "races.json") as f:
        data = json.load(f)
    out = {}
    for r in data.get("races", []):
        if r.get("cancelled"):
            continue
        out[int(r["round"])] = r
    return out


def project_horizon(current_round: int, horizon: int, year: int = CURRENT_SEASON) -> dict:
    """
    Generate ML-based projections for rounds [current_round + 1, current_round + horizon].

    Returns a dict suitable for serialization to horizon_projections.json:
        {
          "year": int,
          "current_round": int,
          "horizon": int,
          "generated_at": ISO8601,
          "rounds": {
              "8": {round, name, circuit, is_sprint, drivers: {abbrev: {...}}, constructors: {id: {...}}},
              ...
          }
        }

    Each driver entry has predicted positions + the simplified expected
    fantasy points the multi-week planner consumes in place of its old
    affinity heuristic.
    """
    run_predictions = _lazy_import_run_predictions()
    abbrev_to_jolpica, jolpica_to_abbrev = _load_driver_id_maps()
    driver_constructors = _load_constructor_for_driver()
    races_by_round = _load_race_info(year)

    out: dict = {
        "year": year,
        "current_round": current_round,
        "horizon": horizon,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rounds": {},
    }

    target_rounds = []
    n = current_round
    while len(target_rounds) < horizon:
        n += 1
        if year == 2026 and n in CANCELLED_ROUNDS_2026:
            continue
        if n not in races_by_round:
            break
        target_rounds.append(n)

    if not target_rounds:
        print(f"No future rounds found after R{current_round} for {year}.")
        return out

    print(f"Projecting rounds: {target_rounds}")

    for r in target_rounds:
        race = races_by_round.get(r, {})
        is_sprint = (year == 2026 and r in SPRINT_ROUNDS_2026)
        print(f"\n--- Round {r} ({race.get('name', '?')}) ---")

        # Run priors-only prediction. force=True so we can re-run as data
        # changes between weeks; output_suffix keeps these isolated from the
        # canonical predictions.parquet (no archive pollution).
        try:
            pred_df = run_predictions(
                round_num=r,
                year=year,
                force=True,
                skip_fp=True,
                output_suffix="horizon",
            )
        except Exception as e:
            print(f"  ERROR predicting round {r}: {e}")
            continue

        if pred_df is None or pred_df.empty:
            print(f"  No predictions returned for round {r}; skipping.")
            continue

        # Aggregate per-driver
        driver_proj: dict[str, dict] = {}
        constructor_totals: dict[str, dict] = {}  # constructor_id -> {drivers: [pts], ...}

        for _, row in pred_df.iterrows():
            jolpica_id = row["driver_id"]
            abbrev = row.get("driver_abbrev") or jolpica_to_abbrev.get(jolpica_id, jolpica_id)
            pred_quali = int(row.get("predicted_quali_position", 0))
            pred_race = int(row.get("predicted_race_position", 0))
            pred_sprint_quali = (int(row["predicted_sprint_quali_position"])
                                 if is_sprint and "predicted_sprint_quali_position" in row.index
                                 and pd.notna(row.get("predicted_sprint_quali_position"))
                                 else None)
            pred_sprint = (int(row["predicted_sprint_position"])
                           if is_sprint and "predicted_sprint_position" in row.index
                           and pd.notna(row.get("predicted_sprint_position"))
                           else None)

            pts = _expected_driver_points(pred_quali, pred_race, is_sprint, pred_sprint_quali, pred_sprint)

            driver_proj[abbrev] = {
                "predicted_quali": pred_quali,
                "predicted_race": pred_race,
                "predicted_sprint_quali": pred_sprint_quali,
                "predicted_sprint": pred_sprint,
                "expected_points": pts["total"],
                "breakdown": pts,
            }

            # Constructor aggregation: sum of both drivers' base race+quali pts
            # (without DOTD, matching constructor scoring rules — but no pitstop
            # bonuses or quali-tier bonuses since those are too noisy to project).
            cid = driver_constructors.get(abbrev) or row.get("constructor_id") or ""
            if cid:
                bucket = constructor_totals.setdefault(cid, {"driver_pts_excl_dotd": 0.0, "drivers": []})
                # Subtract expected DOTD contribution from this driver since
                # constructors don't get DOTD points (per scoring rules).
                if pred_race <= 3:
                    dotd_contrib = 0.12 * RACE_DRIVER_OF_THE_DAY_BONUS
                elif pred_race <= 6:
                    dotd_contrib = 0.08 * RACE_DRIVER_OF_THE_DAY_BONUS
                else:
                    dotd_contrib = 0.03 * RACE_DRIVER_OF_THE_DAY_BONUS
                bucket["driver_pts_excl_dotd"] += pts["total"] - dotd_contrib
                bucket["drivers"].append(abbrev)

        # Materialize constructor projections
        constructor_proj: dict[str, dict] = {}
        for cid, info in constructor_totals.items():
            constructor_proj[cid] = {
                "expected_points": round(info["driver_pts_excl_dotd"], 1),
                "drivers": info["drivers"],
            }

        out["rounds"][str(r)] = {
            "round": r,
            "name": race.get("name", f"Round {r}"),
            "circuit": race.get("circuit", ""),
            "is_sprint": is_sprint,
            "drivers": driver_proj,
            "constructors": constructor_proj,
        }

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict next N rounds for the multi-week planner (priors-only)")
    parser.add_argument("--current-round", type=int, required=True, help="Current round (predictions for round+1 onward)")
    parser.add_argument("--horizon", type=int, default=5, help="How many future rounds to project")
    parser.add_argument("--year", type=int, default=CURRENT_SEASON, help="Season year")
    parser.add_argument("--output", type=Path, default=WEB_DATA_DIR / "horizon_projections.json",
                        help="Output JSON path (default: web/public/data/horizon_projections.json)")
    args = parser.parse_args()

    result = project_horizon(args.current_round, args.horizon, args.year)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    n_rounds = len(result.get("rounds", {}))
    print(f"\nWrote {n_rounds} round projections -> {args.output}")


if __name__ == "__main__":
    main()
