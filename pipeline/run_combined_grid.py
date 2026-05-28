"""Combined grid search around the OAT-winning hyperparameters.

OAT sweeps surface single-variable winners but miss interactions. This script
tests specific combined configs that should be the strongest based on OAT
findings, plus targeted perturbations.

Each candidate is compared to baseline via paired bootstrap.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"
VALIDATOR = PROJECT_ROOT / "pipeline" / "validate_model_config.py"

# Each entry: (config_name, list of CLI args)
CANDIDATES = [
    # ---- Single-model bests ----
    # Race-only: keep all the race wins, leave quali/sprint at baseline
    ("race_best",
     ["--race-max-depth", "2", "--race-n-estimators", "1000", "--race-subsample", "1.0"]),
    # Quali-only: keep all the quali wins, leave race/sprint at baseline
    ("quali_best",
     ["--quali-learning-rate", "0.015", "--weight-2026", "2.0"]),
    # Quali with also more aggressive tuning (depth=2, n=400)
    ("quali_best_plus",
     ["--quali-learning-rate", "0.015", "--quali-max-depth", "2",
      "--quali-n-estimators", "400", "--weight-2026", "2.0"]),

    # ---- Combined race + quali bests, varying weight ----
    # Both bests with weight=2.0 (favors quali, but race weight=2.0 was -0.236 BAD at baseline tuning)
    ("all_best_w2",
     ["--weight-2026", "2.0",
      "--race-max-depth", "2", "--race-n-estimators", "1000", "--race-subsample", "1.0",
      "--quali-learning-rate", "0.015"]),
    # Both bests with weight=2.5 (baseline weight — best for race at baseline tuning)
    ("all_best_w2p5",
     ["--weight-2026", "2.5",
      "--race-max-depth", "2", "--race-n-estimators", "1000", "--race-subsample", "1.0",
      "--quali-learning-rate", "0.015"]),
    # Both bests with weight=1.5 (was significantly better for quali at baseline race)
    ("all_best_w1p5",
     ["--weight-2026", "1.5",
      "--race-max-depth", "2", "--race-n-estimators", "1000", "--race-subsample", "1.0",
      "--quali-learning-rate", "0.015"]),

    # ---- Race depth perturbations around winner ----
    # depth=3 is a more conservative bet than depth=2 — closer to baseline, less overfitting risk
    ("race_d3_n1000_sub1",
     ["--race-max-depth", "3", "--race-n-estimators", "1000", "--race-subsample", "1.0"]),
    # depth=2 + n=1200 (a few more trees to compensate for shallower depth)
    ("race_d2_n1200_sub1",
     ["--race-max-depth", "2", "--race-n-estimators", "1200", "--race-subsample", "1.0"]),
    # depth=2 + n=800 (test if 1000 is overshooting)
    ("race_d2_n800_sub1",
     ["--race-max-depth", "2", "--race-n-estimators", "800", "--race-subsample", "1.0"]),
    # Race best WITHOUT subsample=1.0 (test if subsample is the load-bearing change)
    ("race_d2_n1000",
     ["--race-max-depth", "2", "--race-n-estimators", "1000"]),
    # Race best WITHOUT n_estimators bump (test if depth alone is enough)
    ("race_d2_sub1",
     ["--race-max-depth", "2", "--race-subsample", "1.0"]),
    # Race depth=2 alone, everything else at baseline (cleanest test of the headline finding)
    ("race_d2_only",
     ["--race-max-depth", "2"]),

    # ---- Quali perturbations ----
    # Quali lr=0.012 (a touch lower than the winner 0.015)
    ("quali_lr0p012_w2",
     ["--quali-learning-rate", "0.012", "--weight-2026", "2.0"]),
    # Quali lr=0.015 with weight=2.5 (baseline weight)
    ("quali_lr0p015_only",
     ["--quali-learning-rate", "0.015"]),
]


def run_config(config_name: str, extra_args: list[str]) -> None:
    out_path = EXPERIMENTS_DIR / f"{config_name}.json"
    if out_path.exists():
        print(f"  [cache] {config_name}")
        return
    cmd = [sys.executable, str(VALIDATOR), "--config-name", config_name, *extra_args]
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [FAIL] {config_name}\n{result.stderr[-500:]}")
        raise SystemExit(1)
    print(f"  [done] {config_name} in {time.time() - t0:.0f}s")


def compare(name: str) -> None:
    cmd = [sys.executable, str(VALIDATOR), "--compare", "baseline", name]
    subprocess.run(cmd, capture_output=True, text=True)


def render_table() -> str:
    lines = []
    lines.append(f"\n{'=' * 92}")
    lines.append(f"COMBINED GRID (vs baseline; n=5 folds; bootstrap 95% CI on per-fold MAE delta)")
    lines.append(f"  Negative = candidate better. * = 95% CI excludes 0.")
    lines.append(f"{'=' * 92}")
    lines.append(f"  {'config':<26}  {'race dMAE':<24}  {'quali dMAE':<24}  {'sprint dMAE':<14}")
    lines.append(f"  {'-' * 26}  {'-' * 24}  {'-' * 24}  {'-' * 14}")
    for name, _ in CANDIDATES:
        comp_path = EXPERIMENTS_DIR / f"compare_baseline_vs_{name}.json"
        if not comp_path.exists():
            lines.append(f"  {name:<26}  (no comparison)")
            continue
        comp = json.loads(comp_path.read_text())
        cells = []
        for model in ("race", "quali", "sprint"):
            m = comp.get("models", {}).get(model)
            if not m:
                cells.append("    n/a")
                continue
            d = m["mae_delta_mean"]
            lo, hi = m["mae_delta_ci_95"]
            sig = "*" if m["excludes_zero"] else " "
            cells.append(f"{d:+.3f} [{lo:+.2f},{hi:+.2f}]{sig}")
        lines.append(f"  {name:<26}  {cells[0]:<24}  {cells[1]:<24}  {cells[2]:<14}")
    lines.append(f"{'=' * 92}")
    return "\n".join(lines)


def main() -> None:
    print(f"Running combined grid: {len(CANDIDATES)} candidates")
    for name, args in CANDIDATES:
        run_config(name, args)
    print("\nComparing each candidate to baseline...")
    for name, _ in CANDIDATES:
        compare(name)
    table = render_table()
    print(table)
    out = EXPERIMENTS_DIR / "combined_grid_summary.txt"
    out.write_text(table)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
