"""
Script: Recover Polluted Prediction Archives

Reconstructs honest pre-race predictions for already-completed rounds whose
`predictions_round{N}.json` archive was polluted by post-race re-runs.

The pollution happened because the pipeline had no guard against re-running
06_run_predictions / 07_calculate_fantasy / 08_export_website_json for rounds
whose race had already taken place. Re-running them used a model trained on
data INCLUDING the target round, producing artificially-good "predictions"
that contaminated the accuracy archive.

This recovery script walks each polluted round and rebuilds two honest
archives per round:

  predictions_round{N}_pre_fp.json
    Priors-only prediction. Model is retrained with --exclude-after 2026:{N}
    so it has never seen round N (or any later 2026 round).
    Layer 2 (FP telemetry) is skipped.

  predictions_round{N}_post_fp.json
    Same leak-free model + Layer 2 FP features (which themselves don't leak
    — they're just session telemetry from before the race).

Both archives are tagged with `reconstructed: true`. The canonical
predictions_round{N}.json is left alone (per the new guard); the accuracy
page should prefer the pre_fp phase archive when measuring forecasting
accuracy.

WARNING: This script retrains models. Run time is several minutes per round.
The currently-trained model on disk is REPLACED in the process. After this
script finishes, the model reflects the last round in --rounds — re-run
05_train_models.py (or `run_weekend.py --phase pre_fp`) afterwards to restore
a full-training model.

Usage:
    python pipeline/recover_archives.py --rounds 1,2,3
    python pipeline/recover_archives.py --rounds 3 --skip-pre-fp  # only post-FP
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"

sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import (
    CURRENT_SEASON,
    PREDICTIONS_DIR,
    WEB_DATA_DIR,
    CANCELLED_ROUNDS_2026,
)


def run_step(label: str, cmd: list[str]) -> bool:
    """Run a subprocess; return True on success."""
    print(f"\n  [>] {label}")
    print(f"      {' '.join(cmd)}")
    start = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    elapsed = time.time() - start
    if result.returncode == 0:
        print(f"      [OK] {elapsed:.1f}s")
        return True
    print(f"      [FAIL] exit {result.returncode}, {elapsed:.1f}s")
    return False


def reconstruct_round(round_num: int, *, skip_pre_fp: bool = False, skip_post_fp: bool = False) -> bool:
    """Reconstruct honest archives for one round.

    1. Rebuild model inputs excluding round R and later
    2. Retrain models on that leak-free training set
    3. (post_fp) Run 06 with FP, then 07/08-MC/08-export tagged post_fp
    4. (pre_fp)  Run 06 with --no-fp, then 07/08-MC/08-export tagged pre_fp
    """
    print(f"\n{'=' * 70}")
    print(f"  Reconstructing round {round_num}")
    print(f"{'=' * 70}")

    py = sys.executable

    # Step 1 & 2: Rebuild leak-free training data and retrain
    cutoff = f"2026:{round_num}"
    print(f"\n  Phase A: retrain models with --exclude-after {cutoff}")
    if not run_step(
        f"Build model inputs (exclude-after {cutoff})",
        [py, str(PIPELINE_DIR / "04_build_model_inputs.py"), "--exclude-after", cutoff],
    ):
        return False
    if not run_step(
        "Train models on leak-free data",
        [py, str(PIPELINE_DIR / "05_train_models.py")],
    ):
        return False

    # Helper: run the prediction+fantasy+MC+export chain for a phase
    def predict_and_export(phase: str, extra_args: list[str]) -> bool:
        print(f"\n  Phase B: predict + export ({phase})")
        steps = [
            ("06_run_predictions.py", [py, str(PIPELINE_DIR / "06_run_predictions.py"),
                                       "--round", str(round_num), "--force"] + extra_args),
            ("07_calculate_fantasy.py", [py, str(PIPELINE_DIR / "07_calculate_fantasy.py"),
                                         "--round", str(round_num), "--force"]),
            ("08_monte_carlo_fantasy.py", [py, str(PIPELINE_DIR / "08_monte_carlo_fantasy.py"),
                                           "--round", str(round_num), "--force"]),
            ("08_export_website_json.py", [py, str(PIPELINE_DIR / "08_export_website_json.py"),
                                           "--round", str(round_num),
                                           "--phase", phase,
                                           "--force",  # allow canonical write if archive missing for this round
                                           "--reconstructed"]),
        ]
        for label, cmd in steps:
            if not run_step(label, cmd):
                return False
        return True

    # Post-FP first (uses FP features)
    if not skip_post_fp:
        if not predict_and_export("post_fp", extra_args=[]):
            return False

    # Then pre-FP (skip FP — overwrites the post_fp parquets, which is fine
    # because the phase-tagged archive was already written)
    if not skip_pre_fp:
        if not predict_and_export("pre_fp", extra_args=["--no-fp"]):
            return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct polluted prediction archives")
    parser.add_argument("--rounds", type=str, required=True,
                        help="Comma-separated list of rounds to reconstruct (e.g. '1,2,3')")
    parser.add_argument("--skip-pre-fp", action="store_true",
                        help="Skip the priors-only reconstruction")
    parser.add_argument("--skip-post-fp", action="store_true",
                        help="Skip the priors+FP reconstruction")
    args = parser.parse_args()

    rounds = [int(r.strip()) for r in args.rounds.split(",") if r.strip()]
    rounds = [r for r in rounds if r not in CANCELLED_ROUNDS_2026]
    if not rounds:
        print("No valid rounds to reconstruct.")
        sys.exit(1)

    print("=" * 70)
    print(f"  Archive Recovery — rounds: {rounds}")
    print(f"  pre_fp:  {'SKIP' if args.skip_pre_fp else 'YES'}")
    print(f"  post_fp: {'SKIP' if args.skip_post_fp else 'YES'}")
    print("=" * 70)

    # Backup the polluted predictions/round{N} dirs so we can roll back if needed
    backup_dir = PROJECT_ROOT / "data" / "predictions" / "_polluted_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for r in rounds:
        src = PREDICTIONS_DIR / f"round{r}"
        dst = backup_dir / f"round{r}"
        if src.exists() and not dst.exists():
            shutil.copytree(src, dst)
            print(f"  Backed up {src} -> {dst}")

    results = {}
    for r in rounds:
        ok = reconstruct_round(r,
                               skip_pre_fp=args.skip_pre_fp,
                               skip_post_fp=args.skip_post_fp)
        results[r] = ok

    print(f"\n{'=' * 70}")
    print("  Recovery summary")
    print(f"{'=' * 70}")
    for r, ok in results.items():
        print(f"  Round {r}: {'[OK]' if ok else '[FAIL]'}")

    print(f"\n  Backups kept at: {backup_dir}")
    print(f"\n  NOTE: The trained model on disk now reflects training that excluded ")
    print(f"        round {max(rounds)} and later. To restore full-training models, run:")
    print(f"          python pipeline/run_weekend.py --phase pre_fp")
    print(f"        OR (more direct):")
    print(f"          python pipeline/04_build_model_inputs.py --force-include-current")
    print(f"          python pipeline/05_train_models.py")


if __name__ == "__main__":
    main()
