"""Retroactive multiple-testing correction for the hyperparameter sweep campaign.

The original campaign ran ~60+ paired comparisons against baseline without any
correction for multiple comparisons. At alpha=0.05 with 60 independent tests we
would expect ~3 false positives by chance. This script:

  1. Discovers every candidate config in data/experiments/ that has both a
     fold-level result file AND a comparable baseline (5-fold or 97-fold).
  2. Recomputes a two-sided bootstrap p-value for each comparison directly
     from fold deltas (so older files without persisted p-values still work).
  3. Applies two corrections per model family (quali, race, sprint):
       - Bonferroni: alpha_adj = alpha / m
       - Benjamini-Hochberg FDR: reject p_(i) if p_(i) <= (i/m) * alpha
  4. Prints a corrected summary table — which "significant" findings survive,
     which were probably noise.

This is the right tool to use AFTER any future sweep before declaring a
winner. Run as:

    python pipeline/analyze_multiple_testing.py
        --baseline baseline_multiyear
        --pattern '*_multiyear'   # or omit to include everything
        --alpha 0.05

Outputs `data/experiments/multiple_testing_correction.json` and prints a
table.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CURRENT_SEASON

EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"
RNG_SEED = 42
N_BOOT = 10_000


def _fold_key(row: dict) -> tuple[int, int]:
    return (int(row.get("season", CURRENT_SEASON)), int(row["round"]))


def compute_deltas(base_folds: list[dict], cand_folds: list[dict]) -> np.ndarray:
    """Paired per-fold MAE deltas (candidate - baseline). Negative = better."""
    b = {_fold_key(r): r["mae"] for r in base_folds}
    c = {_fold_key(r): r["mae"] for r in cand_folds}
    common = sorted(set(b) & set(c))
    if not common:
        return np.array([])
    return np.array([c[k] - b[k] for k in common])


def bootstrap_pvalue(deltas: np.ndarray, n_boot: int = N_BOOT) -> tuple[float, tuple[float, float]]:
    """Two-sided bootstrap p-value for H0: mean(delta) == 0.

    Returns (p_two_sided, 95% bootstrap CI).
    """
    if len(deltas) < 2:
        return (1.0, (float(deltas.mean()) if len(deltas) else 0.0,) * 2)
    rng = np.random.default_rng(RNG_SEED)
    boot = np.array([np.mean(rng.choice(deltas, size=len(deltas), replace=True)) for _ in range(n_boot)])
    ci = (float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975)))
    p_pos = float(np.mean(boot >= 0))
    p_neg = float(np.mean(boot <= 0))
    # Clip to [1/n_boot, 1.0]. The 2*min(p_pos, p_neg) two-sided formula can
    # exceed 1 when the bootstrap is identically 0 (both p_pos and p_neg = 1.0,
    # e.g. when candidate == baseline). That case is "no evidence at all" so
    # the right answer is p = 1.0, not 2.0.
    p = min(max(2.0 * min(p_pos, p_neg), 1.0 / n_boot), 1.0)
    return (p, ci)


def benjamini_hochberg(pvalues: list[float], alpha: float) -> list[bool]:
    """Returns a boolean list of same length: True = reject H0 (significant).

    BH controls FDR (expected proportion of false discoveries among rejected)
    at level alpha. Less conservative than Bonferroni.
    """
    if not pvalues:
        return []
    m = len(pvalues)
    # Sort p-values ascending, remember original positions
    order = sorted(range(m), key=lambda i: pvalues[i])
    thresholds = [(rank + 1) / m * alpha for rank in range(m)]
    # Walk from largest rejected upward — once we find a rejection, all smaller
    # p-values are also rejected. Standard BH step-up.
    largest_rejected_rank = -1
    for rank, idx in enumerate(order):
        if pvalues[idx] <= thresholds[rank]:
            largest_rejected_rank = rank
    decisions = [False] * m
    if largest_rejected_rank >= 0:
        for rank in range(largest_rejected_rank + 1):
            decisions[order[rank]] = True
    return decisions


def discover_candidates(baseline_name: str, pattern: str | None) -> list[Path]:
    """All result JSONs that aren't the baseline, comparison artifacts, or summaries."""
    baseline_file = EXPERIMENTS_DIR / f"{baseline_name}.json"
    if not baseline_file.exists():
        raise SystemExit(f"Baseline file not found: {baseline_file}")
    candidates = []
    for p in sorted(EXPERIMENTS_DIR.glob("*.json")):
        if p.name.startswith("compare_"):
            continue
        if p.name.startswith("multiple_testing"):
            continue
        if p.stem == baseline_name:
            continue
        if pattern and not fnmatch.fnmatch(p.stem, pattern):
            continue
        candidates.append(p)
    return candidates


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="Stem of the baseline result file")
    ap.add_argument("--pattern", default=None, help="Glob to filter candidate stems (e.g. '*_multiyear')")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--output", default="multiple_testing_correction.json")
    args = ap.parse_args()

    baseline_path = EXPERIMENTS_DIR / f"{args.baseline}.json"
    baseline = json.loads(baseline_path.read_text())
    candidates = discover_candidates(args.baseline, args.pattern)
    print(f"Baseline:    {args.baseline}")
    print(f"Pattern:     {args.pattern or '*'}")
    print(f"Candidates:  {len(candidates)}")
    print(f"Alpha:       {args.alpha}\n")

    # Collect results per model family
    per_model: dict[str, list[dict]] = {"quali": [], "race": [], "sprint": []}
    for cand_path in candidates:
        try:
            cand = json.loads(cand_path.read_text())
        except json.JSONDecodeError:
            continue
        for model in ("quali", "race", "sprint"):
            b_folds = baseline["folds"].get(model, [])
            c_folds = cand["folds"].get(model, [])
            deltas = compute_deltas(b_folds, c_folds)
            if len(deltas) < 2:
                continue
            p, ci = bootstrap_pvalue(deltas)
            per_model[model].append({
                "config": cand["config_name"],
                "n_folds": len(deltas),
                "delta_mean": float(np.mean(deltas)),
                "ci_lo": ci[0],
                "ci_hi": ci[1],
                "p_uncorrected": p,
            })

    # Apply corrections per model family
    output: dict[str, dict] = {}
    for model, rows in per_model.items():
        if not rows:
            output[model] = {"n_tests": 0, "results": []}
            continue
        m_tests = len(rows)
        bonf_alpha = args.alpha / m_tests
        pvals = [r["p_uncorrected"] for r in rows]
        bh_decisions = benjamini_hochberg(pvals, args.alpha)
        for r, bh in zip(rows, bh_decisions):
            r["bonferroni_significant"] = bool(r["p_uncorrected"] < bonf_alpha)
            r["bh_fdr_significant"] = bool(bh)
            r["uncorrected_significant"] = bool(r["p_uncorrected"] < args.alpha)
        # Sort: most-significant first
        rows.sort(key=lambda r: r["p_uncorrected"])
        output[model] = {
            "n_tests": m_tests,
            "bonferroni_alpha": bonf_alpha,
            "results": rows,
        }

    # Save
    out_path = EXPERIMENTS_DIR / args.output
    out_path.write_text(json.dumps({
        "baseline": args.baseline,
        "alpha": args.alpha,
        "pattern": args.pattern,
        "per_model": output,
    }, indent=2))

    # Print table
    for model in ("race", "quali", "sprint"):
        info = output[model]
        if info["n_tests"] == 0:
            continue
        print(f"\n{'=' * 95}")
        print(f"MODEL: {model.upper()}    (n_tests = {info['n_tests']})")
        print(f"  Uncorrected alpha:  {args.alpha}")
        print(f"  Bonferroni alpha:   {info['bonferroni_alpha']:.5f} (alpha / n_tests)")
        print(f"  BH-FDR controls expected false-discovery proportion at {args.alpha}")
        print(f"{'=' * 95}")
        n_unc = sum(1 for r in info["results"] if r["uncorrected_significant"])
        n_bh = sum(1 for r in info["results"] if r["bh_fdr_significant"])
        n_bonf = sum(1 for r in info["results"] if r["bonferroni_significant"])
        print(f"  Survives: uncorrected={n_unc}  BH-FDR={n_bh}  Bonferroni={n_bonf}")
        print()
        print(f"  {'config':<32}  {'delta':<8}  {'ci_lo':<8}  {'ci_hi':<8}  {'p':<10}  unc  BH  Bonf")
        print(f"  {'-' * 32}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 10}  ---  --  ----")
        # Only print rows that move the needle (anything that was uncorrected-
        # significant OR has a non-trivial delta). The full table is in JSON.
        printed = 0
        for r in info["results"]:
            interesting = (
                r["uncorrected_significant"]
                or abs(r["delta_mean"]) > 0.02
            )
            if not interesting:
                continue
            marks = (
                ("*" if r["uncorrected_significant"] else " "),
                ("*" if r["bh_fdr_significant"] else " "),
                ("*" if r["bonferroni_significant"] else " "),
            )
            print(f"  {r['config']:<32}  {r['delta_mean']:+.4f}  {r['ci_lo']:+.4f}  {r['ci_hi']:+.4f}  {r['p_uncorrected']:.4e}   {marks[0]}    {marks[1]}    {marks[2]}")
            printed += 1
        skipped = info["n_tests"] - printed
        if skipped > 0:
            print(f"  ({skipped} configs with |delta| <= 0.02 and not significant — omitted; see JSON)")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
