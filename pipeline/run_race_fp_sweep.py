"""OAT hyperparameter sweep for race_fp_model.

Wraps validate_race_fp.py with a list of candidate configs and runs each
sequentially. Same pattern as run_oat_sweep.py but with the FP validator.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"
VALIDATOR = PROJECT_ROOT / "pipeline" / "validate_race_fp.py"

SWEEPS = {
    "depth": [
        (f"race_fp_d{d}_multiyear", ["--race-fp-max-depth", str(d)])
        for d in [2, 3, 4, 5, 6, 7, 8]
    ],
    "n_estimators": [
        (f"race_fp_n{n}_multiyear", ["--race-fp-n-estimators", str(n)])
        for n in [400, 650, 1000, 1500, 2000]
    ],
    "lr": [
        (f"race_fp_lr{lr:g}_multiyear".replace(".", "p"),
         ["--race-fp-learning-rate", str(lr)])
        for lr in [0.01, 0.02, 0.03, 0.05, 0.08]
    ],
}


def run_one(name: str, args: list[str], force: bool = False) -> None:
    out = EXPERIMENTS_DIR / f"{name}.json"
    if out.exists() and not force:
        print(f"  [cache] {name}")
        return
    cmd = [sys.executable, str(VALIDATOR), "--config-name", name,
           "--test-from-year", "2022", *args]
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [FAIL] {name}\n{result.stderr[-500:]}")
        return
    print(f"  [done] {name} in {time.time() - t0:.0f}s")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SWEEPS:
        print(f"usage: {sys.argv[0]} <sweep>\nAvailable: {list(SWEEPS.keys())}")
        sys.exit(1)
    sweep = sys.argv[1]
    print(f"Running sweep '{sweep}' on race_fp_model (97-fold multi-year)")
    for name, args in SWEEPS[sweep]:
        run_one(name, args)
    print("\nDone. Compare to baseline with:")
    print(f"  python pipeline/validate_model_config.py --compare race_fp_baseline_multiyear <name>")


if __name__ == "__main__":
    main()
