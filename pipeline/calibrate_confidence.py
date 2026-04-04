"""
Calibrate Monte Carlo confidence intervals against actual race results.

Compares MC predictions (percentile forecasts) against actual fantasy point
outcomes for all completed rounds. Computes:
  1. Empirical coverage at each percentile level (P5-P95, P25-P75)
  2. Probability Integral Transform (PIT) histogram
  3. Noise multiplier to correct under/over-dispersion
  4. Position-specific calibration (front-runners vs midfield vs back)

The calibration factor is saved to data/seed/mc_calibration.json and loaded
automatically by 08_monte_carlo_fantasy.py to adjust noise levels.

With N rounds of data, the calibration improves:
  - 1-2 rounds: limited, use heuristic defaults
  - 3-5 rounds: useful directional signal
  - 6+ rounds: reliable calibration

Usage:
    python pipeline/calibrate_confidence.py
    python pipeline/calibrate_confidence.py --verbose
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    PREDICTIONS_DIR,
    SEED_DIR,
    WEB_DATA_DIR,
    CANCELLED_ROUNDS_2026,
)


def load_mc_predictions(round_num: int) -> pd.DataFrame | None:
    """Load Monte Carlo predictions for a round."""
    path = PREDICTIONS_DIR / f"round{round_num}" / "monte_carlo_fantasy.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def load_actual_results(round_num: int) -> dict | None:
    """Load actual race results for a round."""
    path = WEB_DATA_DIR / f"actual_round{round_num}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compute_empirical_percentile(mc_row: dict, actual_pts: float) -> float:
    """Compute where the actual result falls in the MC distribution.

    Uses linear interpolation between stored percentiles (P5, P25, P50, P75, P95).
    Returns a value in [0, 1] representing the empirical CDF position.

    If calibrated, these values should be uniformly distributed across drivers.
    """
    # Stored percentile anchors
    anchors = [
        (0.00, mc_row.get("mc_total_min", mc_row["mc_total_p5"] - 20)),
        (0.05, mc_row["mc_total_p5"]),
        (0.25, mc_row["mc_total_p25"]),
        (0.50, mc_row["mc_total_median"]),
        (0.75, mc_row["mc_total_p75"]),
        (0.95, mc_row["mc_total_p95"]),
        (1.00, mc_row.get("mc_total_max", mc_row["mc_total_p95"] + 20)),
    ]

    # Handle edge cases
    if actual_pts <= anchors[0][1]:
        return 0.0
    if actual_pts >= anchors[-1][1]:
        return 1.0

    # Linear interpolation
    for i in range(len(anchors) - 1):
        p_lo, v_lo = anchors[i]
        p_hi, v_hi = anchors[i + 1]
        if v_lo <= actual_pts <= v_hi:
            if v_hi == v_lo:
                return (p_lo + p_hi) / 2
            frac = (actual_pts - v_lo) / (v_hi - v_lo)
            return p_lo + frac * (p_hi - p_lo)

    return 0.5  # Fallback


def analyze_calibration(verbose: bool = False) -> dict:
    """Analyze MC calibration across all completed rounds.

    Returns calibration metrics and recommended noise adjustment.
    """
    all_data = []

    # Scan for rounds with both MC predictions and actual results
    for round_num in range(1, 25):
        if round_num in CANCELLED_ROUNDS_2026:
            continue

        mc_df = load_mc_predictions(round_num)
        actual = load_actual_results(round_num)

        if mc_df is None or actual is None:
            continue

        actual_pts_map = {d["driver_id"]: d["total_points"] for d in actual["drivers"]}
        actual_race_pos = {d["driver_id"]: d.get("race_position") for d in actual["drivers"]}
        actual_quali_pos = {d["driver_id"]: d.get("quali_position") for d in actual["drivers"]}
        actual_dnf = {d["driver_id"]: d.get("is_dnf", False) for d in actual["drivers"]}

        for _, row in mc_df.iterrows():
            abbrev = row["driver_abbrev"]
            if abbrev not in actual_pts_map:
                continue

            act_pts = actual_pts_map[abbrev]
            mc_dict = row.to_dict()
            empirical_pct = compute_empirical_percentile(mc_dict, act_pts)

            # Classify driver tier based on predicted position
            det_pos = row["det_race_position"]
            if det_pos <= 5:
                tier = "front"
            elif det_pos <= 12:
                tier = "midfield"
            else:
                tier = "back"

            all_data.append({
                "round": round_num,
                "driver": abbrev,
                "actual_pts": act_pts,
                "mc_mean": row["mc_total_mean"],
                "mc_std": row["mc_total_std"],
                "mc_p5": row["mc_total_p5"],
                "mc_p25": row["mc_total_p25"],
                "mc_p50": row["mc_total_median"],
                "mc_p75": row["mc_total_p75"],
                "mc_p95": row["mc_total_p95"],
                "empirical_pct": empirical_pct,
                "error": act_pts - row["mc_total_mean"],
                "tier": tier,
                "is_dnf": actual_dnf.get(abbrev, False),
                "det_position": det_pos,
            })

    if not all_data:
        print("No calibration data found (need MC predictions + actual results)")
        return {}

    df = pd.DataFrame(all_data)
    n_rounds = df["round"].nunique()
    n_samples = len(df)

    print(f"\n{'=' * 70}")
    print(f"CONFIDENCE INTERVAL CALIBRATION")
    print(f"  {n_rounds} rounds, {n_samples} driver-rounds")
    print(f"{'=' * 70}")

    # 1. Coverage analysis at key percentile levels
    coverage = {}
    for lo_pct, hi_pct, label in [
        (5, 95, "90% CI (P5-P95)"),
        (25, 75, "50% CI (P25-P75)"),
        (10, 90, "80% CI (P10-P90)"),
    ]:
        lo_col = f"mc_p{lo_pct}" if f"mc_p{lo_pct}" in df.columns else None
        hi_col = f"mc_p{hi_pct}" if f"mc_p{hi_pct}" in df.columns else None

        if lo_col and hi_col:
            in_range = ((df["actual_pts"] >= df[lo_col]) &
                        (df["actual_pts"] <= df[hi_col])).mean()
        else:
            # Use empirical percentiles as fallback
            lo_frac = lo_pct / 100
            hi_frac = hi_pct / 100
            in_range = ((df["empirical_pct"] >= lo_frac) &
                        (df["empirical_pct"] <= hi_frac)).mean()

        target = (hi_pct - lo_pct) / 100
        coverage[label] = {"actual": round(float(in_range), 3),
                           "target": target,
                           "ratio": round(float(in_range / target), 3)}

    print(f"\n  Coverage Analysis:")
    print(f"  {'Interval':<25} {'Actual':>8} {'Target':>8} {'Ratio':>8}")
    print(f"  {'-' * 50}")
    for label, v in coverage.items():
        status = "OK" if 0.85 <= v["ratio"] <= 1.15 else ("NARROW" if v["ratio"] < 0.85 else "WIDE")
        print(f"  {label:<25} {v['actual']*100:>7.1f}% {v['target']*100:>7.0f}% {v['ratio']:>7.2f}  {status}")

    # 2. PIT histogram (should be uniform if well-calibrated)
    pit_values = df["empirical_pct"].values
    n_bins = 5
    bin_edges = np.linspace(0, 1, n_bins + 1)
    hist, _ = np.histogram(pit_values, bins=bin_edges)
    expected_per_bin = n_samples / n_bins

    print(f"\n  PIT Histogram (should be uniform, ~{expected_per_bin:.0f} per bin):")
    for i in range(n_bins):
        count = hist[i]
        bar = "#" * int(count * 40 / max(hist))
        label = f"  [{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f})"
        deviation = (count - expected_per_bin) / expected_per_bin * 100
        print(f"  {label:>15} {count:>4} {bar:<40} ({deviation:+.0f}%)")

    # Chi-squared test for uniformity
    chi2 = sum((h - expected_per_bin) ** 2 / expected_per_bin for h in hist)
    print(f"  Chi-squared: {chi2:.2f} (critical value at p=0.05, df={n_bins-1}: {9.49:.2f})")

    # 3. Per-tier analysis
    print(f"\n  Per-Tier Coverage (P5-P95):")
    for tier in ["front", "midfield", "back"]:
        tier_df = df[df["tier"] == tier]
        if len(tier_df) == 0:
            continue
        in_90 = ((tier_df["actual_pts"] >= tier_df["mc_p5"]) &
                 (tier_df["actual_pts"] <= tier_df["mc_p95"])).mean()
        mean_err = tier_df["error"].mean()
        rmse = np.sqrt((tier_df["error"] ** 2).mean())
        print(f"  {tier:>10}: {in_90*100:5.1f}% coverage  (n={len(tier_df):>3}, "
              f"bias={mean_err:+.1f}, RMSE={rmse:.1f})")

    # 4. DNF impact analysis
    dnf_df = df[df["is_dnf"]]
    non_dnf_df = df[~df["is_dnf"]]
    if len(dnf_df) > 0:
        dnf_in_90 = ((dnf_df["actual_pts"] >= dnf_df["mc_p5"]) &
                      (dnf_df["actual_pts"] <= dnf_df["mc_p95"])).mean()
        non_dnf_in_90 = ((non_dnf_df["actual_pts"] >= non_dnf_df["mc_p5"]) &
                          (non_dnf_df["actual_pts"] <= non_dnf_df["mc_p95"])).mean()
        print(f"\n  DNF Impact:")
        print(f"    DNF drivers:     {dnf_in_90*100:5.1f}% in 90% CI (n={len(dnf_df)})")
        print(f"    Non-DNF drivers: {non_dnf_in_90*100:5.1f}% in 90% CI (n={len(non_dnf_df)})")

    # 5. Per-round analysis
    print(f"\n  Per-Round Coverage (P5-P95):")
    round_coverages = []
    for rnd in sorted(df["round"].unique()):
        rdf = df[df["round"] == rnd]
        in_90 = ((rdf["actual_pts"] >= rdf["mc_p5"]) &
                 (rdf["actual_pts"] <= rdf["mc_p95"])).mean()
        in_50 = ((rdf["actual_pts"] >= rdf["mc_p25"]) &
                 (rdf["actual_pts"] <= rdf["mc_p75"])).mean()
        bias = rdf["error"].mean()
        rmse = np.sqrt((rdf["error"] ** 2).mean())
        print(f"    Round {rnd}: 90%CI={in_90*100:5.1f}%  50%CI={in_50*100:5.1f}%  "
              f"bias={bias:+.1f}  RMSE={rmse:.1f}")
        round_coverages.append({"round": int(rnd), "coverage_90": round(float(in_90), 4),
                                "coverage_50": round(float(in_50), 4)})

    # 6. Compute calibration adjustment
    # The noise multiplier scales all noise bases to achieve target coverage.
    # If P5-P95 covers 86% instead of 90%, intervals are too narrow.
    # We compute the factor by which to multiply noise to fix this.
    #
    # Method: For a Gaussian, the 90% CI width = 2 * 1.645 * sigma.
    # If our observed 90% CI actually captures X% of outcomes:
    #   - X < 90%: intervals too narrow -> increase noise
    #   - X > 90%: intervals too wide -> decrease noise (or leave alone)
    #
    # We use the empirical percentile distribution to estimate the correction.
    # The fraction of PIT values in [0.05, 0.95] should be 0.90.

    overall_90_coverage = coverage["90% CI (P5-P95)"]["actual"]
    overall_50_coverage = coverage["50% CI (P25-P75)"]["actual"]

    # Compute noise multiplier from coverage ratio
    # Using quantile-based approach: if coverage is too low, widen intervals
    if overall_90_coverage < 0.88:
        # Intervals too narrow - need more noise
        # Approximate: the "effective" z-value that gives our observed coverage
        from scipy.stats import norm
        target_z = norm.ppf(0.975)  # 1.96 for 95th percentile (one-sided)
        # Our effective z gives coverage = overall_90_coverage
        effective_z = norm.ppf(0.5 + overall_90_coverage / 2)
        noise_multiplier = target_z / effective_z if effective_z > 0 else 1.2
        noise_multiplier = min(noise_multiplier, 1.5)  # Cap at 1.5x
    elif overall_90_coverage > 0.95:
        # Intervals too wide - could reduce noise (conservative: don't go below 0.9x)
        from scipy.stats import norm
        target_z = norm.ppf(0.975)
        effective_z = norm.ppf(0.5 + overall_90_coverage / 2)
        noise_multiplier = target_z / effective_z if effective_z > 0 else 0.95
        noise_multiplier = max(noise_multiplier, 0.8)  # Floor at 0.8x
    else:
        noise_multiplier = 1.0  # Well-calibrated

    # Bias correction: shift the mean prediction
    overall_bias = float(df["error"].mean())
    # Only apply bias correction if significant relative to std
    overall_std = float(df["error"].std())
    bias_significant = abs(overall_bias) > 0.5 * overall_std / np.sqrt(n_samples)

    print(f"\n  {'=' * 50}")
    print(f"  CALIBRATION RESULTS")
    print(f"  {'=' * 50}")
    print(f"  Overall 90% coverage: {overall_90_coverage*100:.1f}% (target: 90%)")
    print(f"  Overall 50% coverage: {overall_50_coverage*100:.1f}% (target: 50%)")
    print(f"  Overall bias: {overall_bias:+.1f} pts (significant: {bias_significant})")
    print(f"  Overall RMSE: {np.sqrt((df['error']**2).mean()):.1f} pts")
    print(f"  Noise multiplier: {noise_multiplier:.3f}")

    if n_rounds < 3:
        print(f"\n  WARNING: Only {n_rounds} rounds of data. Calibration is preliminary.")
        print(f"  Using conservative adjustment (capped at +/- 10%).")
        noise_multiplier = max(0.9, min(1.1, noise_multiplier))

    # Build calibration output
    calibration = {
        "noise_multiplier": round(noise_multiplier, 4),
        "bias_correction": round(overall_bias, 2) if bias_significant else 0.0,
        "n_rounds": n_rounds,
        "n_samples": n_samples,
        "coverage_90": round(overall_90_coverage, 4),
        "coverage_50": round(overall_50_coverage, 4),
        "overall_rmse": round(float(np.sqrt((df["error"]**2).mean())), 2),
        "overall_bias": round(overall_bias, 2),
        "per_tier": {},
        "per_round": round_coverages,
        "pit_histogram": [int(h) for h in hist],
        "pit_chi2": round(chi2, 2),
    }

    # Per-tier multipliers
    for tier in ["front", "midfield", "back"]:
        tier_df = df[df["tier"] == tier]
        if len(tier_df) < 5:
            continue
        tier_90 = ((tier_df["actual_pts"] >= tier_df["mc_p5"]) &
                   (tier_df["actual_pts"] <= tier_df["mc_p95"])).mean()
        tier_bias = tier_df["error"].mean()
        calibration["per_tier"][tier] = {
            "coverage_90": round(float(tier_90), 4),
            "bias": round(float(tier_bias), 2),
            "n": len(tier_df),
        }

    return calibration


def save_calibration(calibration: dict) -> None:
    """Save calibration parameters to seed data."""
    path = SEED_DIR / "mc_calibration.json"
    with open(path, "w") as f:
        json.dump(calibration, f, indent=2)
    print(f"\n  Saved calibration -> {path}")


def main():
    parser = argparse.ArgumentParser(description="Calibrate MC confidence intervals")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    calibration = analyze_calibration(verbose=args.verbose)
    if calibration:
        save_calibration(calibration)
        print(f"\n  To apply: re-run 08_monte_carlo_fantasy.py (auto-loads calibration)")


if __name__ == "__main__":
    main()
