"""
BoxBoxF1Fantasy — Weekend Publisher

Orchestrates the full prediction pipeline for a race weekend.

Execution order:
1. 01_download_data.py   — Download current round data
2. 02_build_laps.py      — Build clean lap datasets
3. 03_extract_features.py — Extract driver performance features
4. 06_run_predictions.py  — Generate predictions
5. 07_calculate_fantasy.py — Calculate fantasy points
6. 08_export_website_json.py — Export to website JSON

Usage:
    python publish_weekend.py

Note: Scripts 04 (build_model_inputs) and 05 (train_models) are run
separately for model training. This pipeline assumes models are already trained.
"""

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"

# Scripts to run in order
PIPELINE_STEPS = [
    ("01_download_data.py", "Download Data"),
    ("02_build_laps.py", "Build Laps"),
    ("03_extract_features.py", "Extract Features"),
    ("06_run_predictions.py", "Run Predictions"),
    ("07_calculate_fantasy.py", "Calculate Fantasy Points"),
    ("08_export_website_json.py", "Export Website JSON"),
]


def run_step(script_name: str, step_name: str, step_num: int, total: int) -> bool:
    """
    Run a pipeline step as a subprocess.

    Returns True if successful, False otherwise.
    """
    script_path = PIPELINE_DIR / script_name

    if not script_path.exists():
        print(f"  ERROR: Script not found: {script_path}")
        return False

    print(f"\n{'=' * 60}")
    print(f"  Step {step_num}/{total}: {step_name}")
    print(f"  Script: {script_name}")
    print(f"{'=' * 60}\n")

    start = time.time()

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            check=False,
        )

        elapsed = time.time() - start

        if result.returncode == 0:
            print(f"\n  OK {step_name} completed ({elapsed:.1f}s)")
            return True
        else:
            print(f"\n  FAIL {step_name} failed (exit code {result.returncode})")
            return False

    except Exception as e:
        print(f"\n  FAIL {step_name} error: {e}")
        return False


def main() -> None:
    """Run the full weekend pipeline."""
    print("+" + "=" * 58 + "+")
    print("|" + "BoxBoxF1Fantasy — Weekend Publisher".center(58) + "|")
    print("+" + "=" * 58 + "+")

    # Check that models exist
    models_dir = PROJECT_ROOT / "models" / "trained"
    required_models = ["quali_model.pkl", "race_model.pkl", "fp_model.pkl"]
    missing_models = [m for m in required_models if not (models_dir / m).exists()]

    if missing_models:
        print("\n! WARNING: Missing trained models:")
        for m in missing_models:
            print(f"  - {m}")
        print("\nYou should run the training pipeline first:")
        print("  python pipeline/04_build_model_inputs.py")
        print("  python pipeline/05_train_models.py")

        proceed = input("\nContinue anyway? (y/n): ").strip().lower()
        if proceed != "y":
            print("Aborted.")
            return

    total = len(PIPELINE_STEPS)
    print(f"\nPipeline: {total} steps")
    print("-" * 40)

    start_total = time.time()
    results = []

    for i, (script, name) in enumerate(PIPELINE_STEPS, 1):
        success = run_step(script, name, i, total)
        results.append((name, success))

        if not success:
            print(f"\n! Pipeline stopped at step {i}: {name}")
            proceed = input("Continue to next step? (y/n): ").strip().lower()
            if proceed != "y":
                break

    elapsed_total = time.time() - start_total

    # Summary
    print(f"\n{'+' + '=' * 58 + '+'}")
    print(f"{'|' + ' Pipeline Summary'.center(58) + '|'}")
    print(f"{'+' + '=' * 58 + '+'}")

    for name, success in results:
        status = "OK" if success else "FAIL"
        print(f"  {status} {name}")

    successes = sum(1 for _, s in results if s)
    print(f"\n  {successes}/{len(results)} steps completed ({elapsed_total:.1f}s total)")

    # Check output
    output_path = PROJECT_ROOT / "web" / "public" / "data" / "predictions.json"
    if output_path.exists():
        print(f"\n  Output: {output_path}")
        print("  Website data is ready!")
    else:
        print(f"\n  Output not found at {output_path}")


if __name__ == "__main__":
    main()
