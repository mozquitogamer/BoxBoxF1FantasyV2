"""Run a one-variable-at-a-time hyperparameter sweep via validate_model_config.

Each sweep keeps every other knob at baseline and varies one parameter. Runs
walk-forward CV, writes per-config result JSON, then does paired bootstrap
comparison vs baseline and prints a comparison table.

Examples
--------
    # Run the weight sweep
    python pipeline/run_oat_sweep.py weight

    # Sweep race-model depth
    python pipeline/run_oat_sweep.py race_depth

    # Re-render the summary from already-written experiment JSONs
    python pipeline/run_oat_sweep.py weight --summary-only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"
VALIDATOR = PROJECT_ROOT / "pipeline" / "validate_model_config.py"

# Each sweep is (sweep_name, list of (config_name, cli_args))
SWEEPS: dict[str, list[tuple[str, list[str]]]] = {
    # ---- 2026 sample weight ----
    "weight": [
        (f"weight_{w:g}".replace(".", "p"), ["--weight-2026", str(w)])
        for w in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    ],
    # ---- Race model: n_estimators ----
    "race_n_estimators": [
        (f"race_n{n}", ["--race-n-estimators", str(n)])
        for n in [400, 650, 800, 1000, 1200, 1600, 2000]
    ],
    # ---- Race model: max_depth ----
    "race_depth": [
        (f"race_depth{d}", ["--race-max-depth", str(d)])
        for d in [2, 3, 4, 5, 6, 7, 8]
    ],
    # ---- Race model: learning_rate ----
    "race_lr": [
        (f"race_lr{lr:g}".replace(".", "p"), ["--race-learning-rate", str(lr)])
        for lr in [0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
    ],
    # ---- Race model: min_child_weight ----
    "race_mcw": [
        (f"race_mcw{m}", ["--race-min-child-weight", str(m)])
        for m in [1, 3, 5, 8, 12]
    ],
    # ---- Race model: subsample ----
    "race_subsample": [
        (f"race_sub{s:g}".replace(".", "p"), ["--race-subsample", str(s)])
        for s in [0.6, 0.7, 0.85, 1.0]
    ],
    # ---- Race model: colsample_bytree ----
    "race_colsample": [
        (f"race_col{c:g}".replace(".", "p"), ["--race-colsample-bytree", str(c)])
        for c in [0.6, 0.7, 0.85, 1.0]
    ],
    # ---- Quali model: n_estimators ----
    "quali_n_estimators": [
        (f"quali_n{n}", ["--quali-n-estimators", str(n)])
        for n in [400, 800, 1200, 1600, 2000]
    ],
    # ---- Quali model: max_depth ----
    "quali_depth": [
        (f"quali_depth{d}", ["--quali-max-depth", str(d)])
        for d in [2, 3, 4, 5, 6]
    ],
    # ---- Quali model: learning_rate ----
    "quali_lr": [
        (f"quali_lr{lr:g}".replace(".", "p"), ["--quali-learning-rate", str(lr)])
        for lr in [0.01, 0.015, 0.025, 0.04, 0.06, 0.10]
    ],
    # ---- Sprint model: n_estimators ----
    "sprint_n_estimators": [
        (f"sprint_n{n}", ["--sprint-n-estimators", str(n)])
        for n in [200, 400, 600, 800, 1200]
    ],
    # ---- Sprint model: max_depth ----
    "sprint_depth": [
        (f"sprint_depth{d}", ["--sprint-max-depth", str(d)])
        for d in [2, 3, 4, 5, 6]
    ],
    # ---- Sprint model: learning_rate ----
    "sprint_lr": [
        (f"sprint_lr{lr:g}".replace(".", "p"), ["--sprint-learning-rate", str(lr)])
        for lr in [0.01, 0.02, 0.035, 0.05, 0.08]
    ],
    # ---- Race model: reg_alpha (L1) — multiyear ----
    "race_reg_alpha_multiyear": [
        (f"race_reg_alpha_{a:g}_multiyear".replace(".", "p"),
         ["--race-reg-alpha", str(a), "--test-from-year", "2022"])
        for a in [0.0, 0.05, 0.1, 0.2, 0.5, 1.0]
    ],
    # ---- Race model: reg_lambda (L2) — multiyear ----
    "race_reg_lambda_multiyear": [
        (f"race_reg_lambda_{l:g}_multiyear".replace(".", "p"),
         ["--race-reg-lambda", str(l), "--test-from-year", "2022"])
        for l in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    ],
    # ---- Quali model: reg_alpha (L1) — multiyear ----
    "quali_reg_alpha_multiyear": [
        (f"quali_reg_alpha_{a:g}_multiyear".replace(".", "p"),
         ["--quali-reg-alpha", str(a), "--test-from-year", "2022"])
        for a in [0.0, 0.05, 0.1, 0.2, 0.5, 1.0]
    ],
    # ---- Quali model: reg_lambda (L2) — multiyear ----
    "quali_reg_lambda_multiyear": [
        (f"quali_reg_lambda_{l:g}_multiyear".replace(".", "p"),
         ["--quali-reg-lambda", str(l), "--test-from-year", "2022"])
        for l in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    ],
    # ---- Quali model: subsample — multiyear ----
    "quali_subsample_multiyear": [
        (f"quali_sub_{s:g}_multiyear".replace(".", "p"),
         ["--quali-subsample", str(s), "--test-from-year", "2022"])
        for s in [0.6, 0.7, 0.85, 1.0]
    ],
    # ---- Quali model: colsample_bytree — multiyear ----
    "quali_colsample_multiyear": [
        (f"quali_col_{c:g}_multiyear".replace(".", "p"),
         ["--quali-colsample-bytree", str(c), "--test-from-year", "2022"])
        for c in [0.6, 0.7, 0.85, 1.0]
    ],
    # ---- Quali model: min_child_weight — multiyear ----
    "quali_mcw_multiyear": [
        (f"quali_mcw_{m}_multiyear", ["--quali-min-child-weight", str(m), "--test-from-year", "2022"])
        for m in [1, 3, 5, 8, 12]
    ],
    # ---- Global wet_boost — multiyear (affects all models' wet-row weight) ----
    "wet_boost_multiyear": [
        (f"wet_boost_{w:g}_multiyear".replace(".", "p"),
         ["--wet-boost", str(w), "--test-from-year", "2022"])
        for w in [1.0, 3.0, 6.0, 9.0, 12.0]
    ],
    # ---- Feature ablation (#10) — multiyear ----
    # FP telemetry block: sparse (~97% NaN in training). Does dropping it help?
    "feature_ablation_multiyear": [
        ("ablate_weather_multiyear",
         ["--drop-prefixes", "weather_", "--test-from-year", "2022"]),
        ("ablate_fp_telemetry_multiyear",
         ["--drop-features",
          "avg_lap_time,best_lap_time,median_lap_time,best_5_lap_avg,p50_to_p95_avg,"
          "degradation_rate,long_run_avg,lap_time_std,pace_delta,theoretical_best,cv_lap_time,"
          "pace_delta_to_fastest,pace_delta_to_median,avg_pace_delta_to_median,race_pace_delta_to_median,"
          "soft_best_lap,soft_avg_lap,medium_long_run_avg,hard_long_run_avg,"
          "sector_1_delta,sector_2_delta,sector_3_delta,long_run_rank",
          "--test-from-year", "2022"]),
        ("ablate_skill_ratings_multiyear",
         ["--drop-features",
          "quali_skill,wet_skill,cold_skill,adaptability,overtaking,tire_mgmt,"
          "strategy_rating,quali_skill_x_ot_diff",
          "--test-from-year", "2022"]),
        ("ablate_weather_and_fp_multiyear",
         ["--drop-prefixes", "weather_,soft_,hard_,medium_",
          "--drop-features",
          "avg_lap_time,best_lap_time,median_lap_time,best_5_lap_avg,p50_to_p95_avg,"
          "degradation_rate,long_run_avg,lap_time_std,pace_delta,theoretical_best,cv_lap_time,"
          "pace_delta_to_fastest,pace_delta_to_median,avg_pace_delta_to_median,race_pace_delta_to_median,"
          "sector_1_delta,sector_2_delta,sector_3_delta,long_run_rank",
          "--test-from-year", "2022"]),
    ],
    # ---- Alternative objectives ----
    "ndcg_objective": [
        ("race_ndcg", ["--race-objective", "rank:ndcg"]),
        ("quali_ndcg", ["--quali-objective", "rank:ndcg"]),
        ("sprint_ndcg", ["--sprint-objective", "rank:ndcg"]),
        ("all_ndcg", ["--race-objective", "rank:ndcg",
                      "--quali-objective", "rank:ndcg",
                      "--sprint-objective", "rank:ndcg"]),
    ],
}


def run_config(config_name: str, extra_args: list[str], force: bool = False) -> dict:
    out_path = EXPERIMENTS_DIR / f"{config_name}.json"
    if out_path.exists() and not force:
        print(f"  [cache] {config_name} exists, skipping")
        return json.loads(out_path.read_text())
    cmd = [sys.executable, str(VALIDATOR), "--config-name", config_name, *extra_args]
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"  [FAIL] {config_name}\n{result.stderr[-500:]}")
        raise SystemExit(1)
    print(f"  [done] {config_name} in {elapsed:.0f}s")
    return json.loads(out_path.read_text())


def compare_to_baseline(candidate_name: str) -> dict:
    """Run the validator in --compare mode against baseline."""
    cmd = [
        sys.executable, str(VALIDATOR),
        "--compare", "baseline", candidate_name,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [compare FAIL] {candidate_name}\n{result.stderr[-300:]}")
        return {}
    # validator prints JSON, capture it
    comp_path = EXPERIMENTS_DIR / f"compare_baseline_vs_{candidate_name}.json"
    return json.loads(comp_path.read_text()) if comp_path.exists() else {}


def render_table(sweep_name: str, configs: list[tuple[str, list[str]]]) -> str:
    lines = []
    lines.append(f"\n{'=' * 88}")
    lines.append(f"OAT SWEEP: {sweep_name}")
    lines.append(f"  vs baseline (n=5 folds; bootstrap 95% CI on per-fold MAE delta)")
    lines.append(f"  Negative MAE delta = candidate is BETTER. CI excludes 0 = statistically significant.")
    lines.append(f"{'=' * 88}")
    lines.append(f"  {'config':<22}  {'race dMAE':<22}  {'quali dMAE':<22}  {'sprint dMAE':<22}")
    lines.append(f"  {'-' * 22}  {'-' * 22}  {'-' * 22}  {'-' * 22}")
    for config_name, _ in configs:
        if config_name == "baseline":
            continue
        comp_path = EXPERIMENTS_DIR / f"compare_baseline_vs_{config_name}.json"
        if not comp_path.exists():
            lines.append(f"  {config_name:<22}  (no comparison)")
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
        lines.append(f"  {config_name:<22}  {cells[0]:<22}  {cells[1]:<22}  {cells[2]:<22}")
    lines.append(f"{'=' * 88}")
    lines.append("  * = statistically significant (95% CI excludes 0)")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep", help="Sweep name: " + ", ".join(SWEEPS.keys()))
    ap.add_argument("--summary-only", action="store_true",
                    help="Skip training, just re-render the table from existing results")
    ap.add_argument("--force", action="store_true", help="Re-run even if cached")
    args = ap.parse_args()

    if args.sweep not in SWEEPS:
        raise SystemExit(f"Unknown sweep '{args.sweep}'. Available: {list(SWEEPS.keys())}")
    configs = SWEEPS[args.sweep]

    if not args.summary_only:
        print(f"Running sweep '{args.sweep}': {len(configs)} configs")
        for config_name, extra_args in configs:
            run_config(config_name, extra_args, force=args.force)
        print(f"\nComparing each candidate to baseline...")
        for config_name, _ in configs:
            if config_name == "baseline":
                continue
            compare_to_baseline(config_name)

    table = render_table(args.sweep, configs)
    print(table)
    table_path = EXPERIMENTS_DIR / f"sweep_{args.sweep}_summary.txt"
    table_path.write_text(table)
    print(f"\nWrote {table_path}")


if __name__ == "__main__":
    main()
