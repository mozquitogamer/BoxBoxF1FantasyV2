"""
BoxBoxF1Fantasy -Automated Weekend Pipeline Runner

Detects the current race weekend and runs the appropriate pipeline phase.

Phases:
  pre_fp     -Prepare for the weekend: download historical data, train models
  post_fp    -After free practice: build laps, extract features, run predictions
  post_quali -After qualifying: re-run predictions with quali data
  post_race  -After the race: download results, compute actuals, analyze

Usage:
    python pipeline/run_weekend.py --phase post_fp
    python pipeline/run_weekend.py --phase post_race --round 3
    python pipeline/run_weekend.py --phase post_fp --dry-run
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"

sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import CURRENT_SEASON, CANCELLED_ROUNDS_2026, SEED_DIR


def detect_current_round():
    """Auto-detect the current/next race round based on today's date."""
    with open(SEED_DIR / "races.json") as f:
        races = json.load(f)["races"]

    today = datetime.now().date()

    # Find the current or next race
    for race in races:
        if race.get("cancelled"):
            continue
        race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
        # Race weekend window: 4 days before race to 1 day after
        if today <= race_date + timedelta(days=1):
            return race["round"], race["name"]

    # If all races have passed, return the last one
    active = [r for r in races if not r.get("cancelled")]
    if active:
        return active[-1]["round"], active[-1]["name"]
    return None, None


def run_step(script_name, args_list, step_num, total, dry_run=False, non_fatal=False):
    """Run a pipeline script as subprocess.

    non_fatal: if True, a failure prints a warning but does NOT abort the
    weekend pipeline. Used for optional steps like predict_horizon.py where
    a downstream failure (e.g. missing model file for a far-future round)
    shouldn't undo the rest of the weekend's work.
    """
    script_path = PIPELINE_DIR / script_name
    if not script_path.exists():
        print(f"  [X] Script not found: {script_path}")
        return non_fatal  # treat missing-script as success when non-fatal

    cmd = [sys.executable, str(script_path)] + args_list
    cmd_str = " ".join(cmd)

    tag = " (optional)" if non_fatal else ""
    print(f"\n  [{step_num}/{total}] {script_name}{tag} {' '.join(args_list)}")

    if dry_run:
        print(f"         -> {cmd_str}")
        return True

    start = time.time()
    try:
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f"         [OK] Done ({elapsed:.1f}s)")
            return True
        else:
            level = "WARN" if non_fatal else "FAIL"
            print(f"         [{level}] Failed (exit code {result.returncode}, {elapsed:.1f}s)")
            return non_fatal  # non-fatal: pretend it succeeded so loop continues
    except Exception as e:
        level = "WARN" if non_fatal else "FAIL"
        print(f"         [{level}] Error: {e}")
        return non_fatal


# Phase definitions
PHASES = {
    "pre_fp": {
        "description": "Prepare for race weekend - download historical data and train models",
        "steps": [
            ("01_download_data.py", ["--mode", "historical", "--start-year", "2020", "--end-year", "2025"]),
            ("03a_normalize_jolpica.py", []),
            ("03b_build_jolpica_features.py", []),
            ("04_build_model_inputs.py", ["--exclude-after", "{year}:{round}"]),
            ("05_train_models.py", []),
        ],
    },
    "pre_fp_predict": {
        "description": "Pre-FP predictions for upcoming round using priors only (no FP telemetry)",
        "steps": [
            ("01_download_data.py", ["--mode", "current", "--round", "{round}"]),
            ("03a_normalize_jolpica.py", ["--all"]),
            ("03b_build_jolpica_features.py", ["--all"]),
            ("06_run_predictions.py", ["--round", "{round}"]),
            ("07_calculate_fantasy.py", ["--round", "{round}"]),
            ("08_monte_carlo_fantasy.py", ["--round", "{round}"]),
            ("08_export_website_json.py", ["--round", "{round}", "--phase", "pre_fp"]),
            # P9: refresh ML projections for the next 5 rounds so the
            # multi-week planner sees fresh future-round data alongside the
            # updated current-round predictions. Non-fatal if it fails — the
            # planner falls back to the affinity heuristic.
            ("predict_horizon.py", ["--current-round", "{round}", "--horizon", "5"], {"non_fatal": True}),
        ],
    },
    "post_fp": {
        "description": "After free practice - generate predictions from FP data",
        "steps": [
            ("01_download_data.py", ["--mode", "current", "--round", "{round}"]),
            ("02_build_laps.py", ["--round", "{round}"]),
            ("03_extract_features.py", ["--round", "{round}"]),
            ("06_run_predictions.py", ["--round", "{round}"]),
            ("07_calculate_fantasy.py", ["--round", "{round}"]),
            ("08_monte_carlo_fantasy.py", ["--round", "{round}"]),
            ("10_fp_analysis.py", ["--round", "{round}"]),
            ("08_export_website_json.py", ["--round", "{round}", "--phase", "post_fp"]),
            ("predict_horizon.py", ["--current-round", "{round}", "--horizon", "5"], {"non_fatal": True}),
        ],
    },
    "post_quali": {
        "description": "After qualifying - re-run predictions with updated data",
        "steps": [
            ("01_download_data.py", ["--mode", "current", "--round", "{round}"]),
            ("02_build_laps.py", ["--round", "{round}"]),
            ("03_extract_features.py", ["--round", "{round}"]),
            ("06_run_predictions.py", ["--round", "{round}"]),
            ("07_calculate_fantasy.py", ["--round", "{round}"]),
            ("08_monte_carlo_fantasy.py", ["--round", "{round}"]),
            ("10_fp_analysis.py", ["--round", "{round}"]),
            ("08_export_website_json.py", ["--round", "{round}", "--phase", "post_quali"]),
            ("predict_horizon.py", ["--current-round", "{round}", "--horizon", "5"], {"non_fatal": True}),
        ],
    },
    "post_race": {
        "description": "After the race - download results, compute actuals, analyze accuracy",
        "steps": [
            ("01_download_data.py", ["--mode", "current", "--round", "{round}"]),
            ("09_post_race_analysis.py", ["--round", "{round}"]),
            # Fetch OpenF1 overtakes + pit stop stationary times BEFORE actual_fantasy_points
            # so the constructor pit stop scoring uses real wheels-up times (stop_duration),
            # not Jolpica's pit lane transit duration (~22s, all in the >3s zero-points bracket).
            # Note: OpenF1 may not have stop_duration populated immediately after the race.
            # If `pitstops` key is missing in overtakes.json, re-run this phase a day later.
            ("13_fetch_openf1_overtakes.py", ["--year", str(CURRENT_SEASON), "--round", "{round}"]),
            ("11_actual_fantasy_points.py", ["--round", "{round}"]),
            ("11_race_deep_dive.py", ["--round", "{round}"]),
            ("12_count_overtakes.py", ["--round", "{round}"]),
            ("13_fetch_pitstop_stationary.py", ["--year", str(CURRENT_SEASON), "--round", "{round}"]),
            ("08_export_website_json.py", ["--round", "{round}"]),
        ],
    },
}


def main():
    parser = argparse.ArgumentParser(
        description="BoxBoxF1Fantasy -Automated Weekend Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  pre_fp           Prepare for the weekend (download historical, train models)
  pre_fp_predict   Pre-FP predictions using priors only (no FP telemetry yet)
  post_fp          After free practice (build laps, extract features, predict)
  post_quali       After qualifying (re-run predictions with updated data)
  post_race        After the race (actuals, analysis, overtakes)

Examples:
  python pipeline/run_weekend.py --phase pre_fp_predict --round 7
  python pipeline/run_weekend.py --phase post_fp --round 7
  python pipeline/run_weekend.py --phase post_race --round 6
  python pipeline/run_weekend.py --phase post_fp --dry-run
        """,
    )
    parser.add_argument("--phase", required=True, choices=list(PHASES.keys()),
                        help="Pipeline phase to run")
    parser.add_argument("--round", type=int, default=None,
                        help="Round number (auto-detected if not provided)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without executing")
    args = parser.parse_args()

    phase = PHASES[args.phase]

    # Detect or use provided round
    round_num = args.round
    race_name = None
    if round_num is None:
        round_num, race_name = detect_current_round()
        if round_num is None:
            print("Could not auto-detect current round. Use --round N.")
            sys.exit(1)
        print(f"Auto-detected: Round {round_num} - {race_name}")
    else:
        # Load race name
        with open(SEED_DIR / "races.json") as f:
            races = json.load(f)["races"]
        match = [r for r in races if r["round"] == round_num]
        race_name = match[0]["name"] if match else f"Round {round_num}"

    if round_num in CANCELLED_ROUNDS_2026:
        print(f"Round {round_num} is cancelled. Aborting.")
        sys.exit(1)

    # Check models for prediction phases
    if args.phase in ("post_fp", "post_quali"):
        models_dir = PROJECT_ROOT / "models" / "trained"
        required = ["quali_model.json", "race_model.json"]
        missing = [m for m in required if not (models_dir / m).exists()]
        if missing:
            print(f"\n  WARNING: Missing trained models: {', '.join(missing)}")
            print("  Run: python pipeline/run_weekend.py --phase pre_fp")
            sys.exit(1)

    # Header
    mode = "DRY RUN" if args.dry_run else "EXECUTING"
    print(f"\n{'=' * 60}")
    print(f"  BoxBoxF1Fantasy Pipeline Runner - {mode}")
    print(f"  Phase: {args.phase}")
    print(f"  Round: {round_num} - {race_name}")
    print(f"  {phase['description']}")
    print(f"{'=' * 60}")

    steps = phase["steps"]
    total = len(steps)
    results = []
    start_total = time.time()

    for i, step in enumerate(steps, 1):
        # Steps are (script, args) or (script, args, options_dict)
        if len(step) == 3:
            script, step_args, opts = step
        else:
            script, step_args = step
            opts = {}
        non_fatal = bool(opts.get("non_fatal", False))
        # Replace {round} and {year} placeholders
        resolved_args = [a.replace("{round}", str(round_num)).replace("{year}", str(CURRENT_SEASON)) for a in step_args]
        success = run_step(script, resolved_args, i, total, dry_run=args.dry_run, non_fatal=non_fatal)
        results.append((script, success))
        if not success and not args.dry_run:
            print(f"\n  Pipeline stopped at step {i}. Fix the issue and re-run.")
            break

    elapsed = time.time() - start_total

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    for script, success in results:
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {script}")

    successes = sum(1 for _, s in results if s)
    print(f"\n  {successes}/{len(results)} steps completed", end="")
    if not args.dry_run:
        print(f" ({elapsed:.1f}s)")
    else:
        print(" (dry run)")

    if successes == len(results) and not args.dry_run:
        if args.phase in ("post_fp", "post_quali"):
            print(f"\n  [OK] Website data updated! Check web/public/data/predictions.json")
        elif args.phase == "pre_fp_predict":
            print(f"\n  [OK] Pre-FP predictions ready (priors only). Check web/public/data/predictions.json")
        elif args.phase == "post_race":
            print(f"\n  [OK] Post-race analysis complete! Check web/public/data/")


if __name__ == "__main__":
    main()
