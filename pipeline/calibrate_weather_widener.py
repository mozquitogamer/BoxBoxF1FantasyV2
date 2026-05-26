"""
MC Weather Widener Calibration

Compares completed-race actuals against the MC predictions that ran with
the weather widener active, stratifies by rain_risk bucket, and suggests
multiplier adjustments based on observed CI coverage + DNF rate vs
predicted.

Critical caveat: this only operates on rounds whose predictions ran with
the weather widener ACTIVE (shipped 2026-05-25). Earlier predictions had
no widener applied, so their `weather_adjustments` block in the audit
snapshot will be absent. Those rounds are skipped automatically.

If there are fewer than MIN_ROUNDS_PER_BUCKET (default 2) wet rounds with
widener-active predictions, the script prints "INSUFFICIENT DATA" for that
bucket and does NOT suggest changes — small samples produce noisy multipliers
that would feed back into the widener and bias future predictions.

Workflow when this script DOES have data:
  1. Run after a wet 2026 weekend's post_race phase completes
  2. Read its output carefully
  3. Manually update MC_WEATHER_TUNABLES in pipeline/08_monte_carlo_fantasy.py
     based on the suggestions (don't auto-apply — they're suggestions, not
     mandates)
  4. Re-run the MC for past rounds with --force to verify the new multipliers
     don't blow up the calibration on dry rounds

Usage:
  python pipeline/calibrate_weather_widener.py
  python pipeline/calibrate_weather_widener.py --min-rounds 1  (less strict)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    CURRENT_SEASON,
    PREDICTIONS_DIR,
    SEED_DIR,
    CANCELLED_ROUNDS_2026,
)

AUDIT_SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "audit" / "snapshots"

# Minimum widener-active rounds per rain_risk bucket before we trust the
# observed coverage / suggest changes. Below this -> "INSUFFICIENT DATA".
DEFAULT_MIN_ROUNDS_PER_BUCKET = 2

# Target coverage for 90% CI (P5-P95 band)
TARGET_COVERAGE_90 = 0.90


def latest_post_race_snapshot(round_num: int) -> Path | None:
    """Find the most recent post-race phase snapshot for this round (audit log)."""
    snap_dir = AUDIT_SNAPSHOTS_DIR / f"round{round_num}"
    if not snap_dir.exists():
        return None
    # Prefer post_quali snapshots since those are the final prediction state
    # before the race was run. Phase order: pre_fp -> post_fp -> post_quali.
    for phase in ("post_quali", "post_fp", "pre_fp"):
        matches = sorted(snap_dir.glob(f"*_{phase}.json"))
        if matches:
            return matches[-1]
    return None


def load_actuals(round_num: int) -> dict | None:
    """Load actual fantasy points for a completed round."""
    p = PREDICTIONS_DIR / f"round{round_num}" / "actual_fantasy_points.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def coverage_within_band(actual_pts: list[float], p5: list[float], p95: list[float]) -> float:
    """Fraction of drivers whose actual points fell within the 90% CI."""
    if not actual_pts:
        return 0.0
    n_in = 0
    for a, lo, hi in zip(actual_pts, p5, p95):
        if a is None or lo is None or hi is None:
            continue
        if lo <= a <= hi:
            n_in += 1
    return n_in / len(actual_pts) if actual_pts else 0.0


def analyse_round(round_num: int) -> dict | None:
    """Extract per-round calibration data. Returns None when round can't be analysed."""
    snap_path = latest_post_race_snapshot(round_num)
    if snap_path is None:
        return None
    try:
        with open(snap_path) as f:
            snap = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    pred = snap.get("predictions") or {}
    weather_adj = pred.get("weather_adjustments")
    if not weather_adj:
        # Prediction ran before the widener shipped — skip
        return None

    actuals = load_actuals(round_num)
    if not actuals:
        return None

    # Build {abbrev -> {actual, p5, mean, p95}} per driver
    actual_by_abbrev = {}
    for d in actuals.get("drivers", []):
        ab = d.get("driver_id") or d.get("driver_abbrev")
        if ab:
            actual_by_abbrev[ab] = d.get("total_points")
    pred_by_abbrev = {}
    for d in pred.get("drivers", []):
        ab = d.get("driver_id")
        if ab:
            pred_by_abbrev[ab] = d

    matched = [ab for ab in actual_by_abbrev if ab in pred_by_abbrev]
    if not matched:
        return None

    actual_pts = []
    p5, p95, means = [], [], []
    dnfs_actual, dnf_probs_predicted = 0, 0.0
    for ab in matched:
        a = actual_by_abbrev[ab]
        p = pred_by_abbrev[ab]
        if a is None:
            continue
        actual_pts.append(a)
        p5.append(p.get("mc_total_p5"))
        p95.append(p.get("mc_total_p95"))
        means.append(p.get("mc_total_mean"))
        dnf_probs_predicted += p.get("dnf_probability", 0.0) or 0.0
        # Actual DNFs flagged in actuals JSON
        actual_entry = next((x for x in actuals["drivers"] if (x.get("driver_id") or x.get("driver_abbrev")) == ab), {})
        if actual_entry.get("is_dnf"):
            dnfs_actual += 1

    n = len(actual_pts)
    if n == 0:
        return None

    cov90 = coverage_within_band(actual_pts, p5, p95)
    bias = float(np.mean(np.array(actual_pts) - np.array(means)))
    rmse = float(np.sqrt(np.mean((np.array(actual_pts) - np.array(means)) ** 2)))

    return {
        "round": round_num,
        "snapshot": snap_path.name,
        "rain_risk": weather_adj.get("rain_risk", "NONE"),
        "noise_mult": weather_adj.get("noise_mult", 1.0),
        "dnf_mult": weather_adj.get("dnf_mult", 1.0),
        "race_air_temp_C": weather_adj.get("race_air_temp_C"),
        "n_drivers": n,
        "coverage_90": cov90,
        "bias": bias,
        "rmse": rmse,
        "predicted_dnf_count": dnf_probs_predicted,
        "actual_dnf_count": dnfs_actual,
    }


def summarise_bucket(label: str, rounds: list[dict], min_rounds: int) -> dict:
    """Aggregate per-bucket calibration stats + emit suggestions."""
    n = len(rounds)
    out = {"rain_risk": label, "n_rounds": n}
    if n < min_rounds:
        out["status"] = "INSUFFICIENT_DATA"
        out["message"] = (
            f"{n} rounds with widener active in bucket {label} (need >= {min_rounds}). "
            f"No multiplier suggestions made."
        )
        return out

    cov = float(np.mean([r["coverage_90"] for r in rounds]))
    bias = float(np.mean([r["bias"] for r in rounds]))
    rmse = float(np.mean([r["rmse"] for r in rounds]))
    pred_dnf = sum(r["predicted_dnf_count"] for r in rounds)
    actual_dnf = sum(r["actual_dnf_count"] for r in rounds)
    noise_mults = sorted(set(r["noise_mult"] for r in rounds))
    dnf_mults = sorted(set(r["dnf_mult"] for r in rounds))

    out.update({
        "status": "OK",
        "coverage_90": cov,
        "target_coverage_90": TARGET_COVERAGE_90,
        "bias": bias,
        "rmse": rmse,
        "predicted_dnf_count": pred_dnf,
        "actual_dnf_count": actual_dnf,
        "current_noise_mults": noise_mults,
        "current_dnf_mults": dnf_mults,
    })

    # Suggestions
    suggestions = []
    coverage_gap = TARGET_COVERAGE_90 - cov
    if abs(coverage_gap) > 0.05:
        # Suggest a noise multiplier nudge proportional to the coverage gap.
        # If coverage low -> noise too tight -> increase mult by ~5-15%.
        if coverage_gap > 0:
            # Coverage under-shooting: widen
            adjust = 1.0 + min(0.20, coverage_gap * 1.0)
            suggestions.append({
                "type": "noise_mult",
                "direction": "increase",
                "factor": round(adjust, 3),
                "rationale": (
                    f"Observed coverage {cov*100:.0f}% < target {TARGET_COVERAGE_90*100:.0f}%; "
                    f"multiply current noise_mult by ~{adjust:.2f}x"
                ),
            })
        else:
            adjust = 1.0 / (1.0 + min(0.20, -coverage_gap * 1.0))
            suggestions.append({
                "type": "noise_mult",
                "direction": "decrease",
                "factor": round(adjust, 3),
                "rationale": (
                    f"Observed coverage {cov*100:.0f}% > target {TARGET_COVERAGE_90*100:.0f}%; "
                    f"multiply current noise_mult by ~{adjust:.2f}x"
                ),
            })

    # DNF rate calibration
    if pred_dnf > 0:
        dnf_ratio = actual_dnf / pred_dnf
        if abs(dnf_ratio - 1.0) > 0.20:
            suggestions.append({
                "type": "dnf_mult",
                "direction": "increase" if dnf_ratio > 1.0 else "decrease",
                "factor": round(dnf_ratio, 3),
                "rationale": (
                    f"Actual DNF count {actual_dnf} vs predicted {pred_dnf:.1f}; "
                    f"multiply current dnf_mult by ~{dnf_ratio:.2f}x"
                ),
            })

    out["suggestions"] = suggestions if suggestions else [{"type": "none", "rationale": "Calibration is on target within tolerance."}]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-rounds", type=int, default=DEFAULT_MIN_ROUNDS_PER_BUCKET,
                        help=f"Minimum widener-active rounds per rain_risk bucket "
                             f"to trust calibration (default {DEFAULT_MIN_ROUNDS_PER_BUCKET}).")
    args = parser.parse_args()

    print("=" * 70)
    print("MC Weather Widener Calibration")
    print("=" * 70)
    print(f"Min rounds per bucket: {args.min_rounds}")

    # Walk all known completed rounds
    races_path = SEED_DIR / "races.json"
    with open(races_path) as f:
        races = json.load(f).get("races", [])

    all_round_data = []
    n_skipped_no_widener = 0
    n_skipped_no_actuals = 0
    n_skipped_no_snapshot = 0

    for r in races:
        rnd = r.get("round")
        if r.get("cancelled"):
            continue
        if rnd in CANCELLED_ROUNDS_2026:
            continue
        snap = latest_post_race_snapshot(rnd)
        if snap is None:
            n_skipped_no_snapshot += 1
            continue
        analysis = analyse_round(rnd)
        if analysis is None:
            # Check why
            actuals = load_actuals(rnd)
            if not actuals:
                n_skipped_no_actuals += 1
            else:
                n_skipped_no_widener += 1
            continue
        all_round_data.append(analysis)

    print(f"\nRound coverage:")
    print(f"  {len(all_round_data)} rounds analysed (widener-active + actuals)")
    print(f"  {n_skipped_no_snapshot} rounds skipped: no audit snapshot")
    print(f"  {n_skipped_no_actuals} rounds skipped: no actuals (race not complete)")
    print(f"  {n_skipped_no_widener} rounds skipped: widener not active (pre-shipping)")

    if not all_round_data:
        print("\n>> INSUFFICIENT DATA: no widener-active completed rounds yet.")
        print("   Re-run after the first wet 2026 weekend completes its post_race phase.")
        return

    # Group by rain_risk bucket
    by_bucket = {}
    for r in all_round_data:
        by_bucket.setdefault(r["rain_risk"], []).append(r)

    print("\nPer-round detail:")
    for r in all_round_data:
        print(f"  R{r['round']:>2d} rain={r['rain_risk']:>6s} noise_x{r['noise_mult']:.2f} dnf_x{r['dnf_mult']:.2f} "
              f"coverage_90={r['coverage_90']*100:5.1f}% bias={r['bias']:+6.1f}pts "
              f"actual_DNF={r['actual_dnf_count']}/{r['predicted_dnf_count']:.1f}")

    print("\n" + "=" * 70)
    print("PER-BUCKET SUMMARY")
    print("=" * 70)
    summaries = []
    for label in ("NONE", "LOW", "MEDIUM", "HIGH"):
        if label in by_bucket:
            summary = summarise_bucket(label, by_bucket[label], args.min_rounds)
            summaries.append(summary)
            print(f"\n  Bucket {label} ({summary['n_rounds']} rounds):")
            if summary["status"] == "INSUFFICIENT_DATA":
                print(f"    >> {summary['message']}")
                continue
            print(f"    coverage_90: {summary['coverage_90']*100:.1f}% (target {summary['target_coverage_90']*100:.0f}%)")
            print(f"    bias: {summary['bias']:+.2f} pts")
            print(f"    DNF actual/predicted: {summary['actual_dnf_count']}/{summary['predicted_dnf_count']:.1f}")
            print(f"    Suggestions:")
            for s in summary["suggestions"]:
                print(f"      - {s['rationale']}")

    print("\n" + "=" * 70)
    print("NEXT STEP")
    print("=" * 70)
    if all(s["status"] != "OK" for s in summaries):
        print("  No bucket has enough data for confident calibration yet.")
    elif any(s["status"] == "OK" and s.get("suggestions", [{}])[0].get("type") != "none" for s in summaries):
        print("  Review suggestions above and manually edit MC_WEATHER_TUNABLES in")
        print("    pipeline/08_monte_carlo_fantasy.py")
        print("  Then re-run MC for past rounds to verify dry-bucket calibration is unaffected.")
    else:
        print("  Calibration looks healthy across buckets. No changes recommended.")
    print("=" * 70)


if __name__ == "__main__":
    main()
