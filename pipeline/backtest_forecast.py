"""
Points-level backtest harness — replays each round's PRE-LOCK forecast against
the official F1 Fantasy points and scores how good the forecast was.

Positions are already gated by the walk-forward harness (validate_model_config).
This gates the thing that actually matters to a fantasy manager: the PREDICTED
POINTS and the DRIVER ORDERING at the moment the team locks. It's the standard
against which every modelling/simulation change should be measured.

The F1 Fantasy team-lock deadline is BEFORE qualifying (or at the sprint-race
start on sprint weekends), so the actionable forecast is the post-FP archive
(`predictions_round{N}_post_fp.json`), falling back to pre-FP when no FP ran.
Official points come from data/seed/official_fantasy_points.json (reconciled to
100% vs our computed actuals as of 2026-07-02).

Metrics per round (drivers and constructors separately):
  - points MAE / RMSE / bias (forecast expected_points vs official)
  - Spearman rank correlation of the forecast ORDERING vs actual points
  - top-5 overlap (how many of the forecast's top 5 were in the actual top 5)
  - 90% CI coverage (actual within MC p5..p95) — honesty of the intervals

Usage:
    python pipeline/backtest_forecast.py                 # post_fp (actionable)
    python pipeline/backtest_forecast.py --phase pre_fp  # earliest forecast
    python pipeline/backtest_forecast.py --compare       # pre_fp vs post_fp
    python pipeline/backtest_forecast.py --json out.json

Always exits 0 — it is a report, not a test runner.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import WEB_DATA_DIR, SEED_DIR

# Fallback order when a specific phase archive is missing.
PHASE_FALLBACK = {
    "post_fp": ["post_fp", "pre_fp", "canonical"],
    "pre_fp": ["pre_fp", "canonical"],
    "post_quali": ["post_quali", "post_fp", "pre_fp", "canonical"],
    "canonical": ["canonical"],
}


def _spearman(forecast: list[float], actual: list[float]) -> float | None:
    """Spearman rank correlation without a scipy dependency (rank then Pearson)."""
    n = len(forecast)
    if n < 3:
        return None

    def _rank(x):
        order = sorted(range(n), key=lambda i: x[i])
        r = [0.0] * n
        i = 0
        while i < n:  # average ties
            j = i
            while j + 1 < n and x[order[j + 1]] == x[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rf, ra = _rank(forecast), _rank(actual)
    mf, ma = sum(rf) / n, sum(ra) / n
    num = sum((rf[i] - mf) * (ra[i] - ma) for i in range(n))
    df = sum((rf[i] - mf) ** 2 for i in range(n))
    da = sum((ra[i] - ma) ** 2 for i in range(n))
    if df <= 0 or da <= 0:
        return None
    return num / (df * da) ** 0.5


def load_official() -> dict:
    path = SEED_DIR / "official_fantasy_points.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f).get("rounds", {}) or {}


def _archive_path(round_num: int, phase: str) -> Path:
    if phase == "canonical":
        return WEB_DATA_DIR / f"predictions_round{round_num}.json"
    return WEB_DATA_DIR / f"predictions_round{round_num}_{phase}.json"


def load_forecast(round_num: int, phase: str) -> tuple[dict, str | None]:
    """Load a round's forecast, honoring the phase fallback chain.

    Returns (data, resolved_phase) or ({}, None) if nothing is available.
    """
    for cand in PHASE_FALLBACK.get(phase, [phase]):
        p = _archive_path(round_num, cand)
        if p.exists():
            try:
                with open(p) as f:
                    return json.load(f), cand
            except (json.JSONDecodeError, OSError):
                continue
    return {}, None


def _driver_forecast_map(fc: dict) -> dict:
    """abbrev -> {pred, p5, p95} from a forecast archive."""
    out = {}
    for d in fc.get("drivers", []):
        key = d.get("driver_id") or d.get("driver_abbrev")
        if key is None:
            continue
        out[key] = {
            "pred": d.get("expected_points", d.get("mc_total_mean")),
            "p5": d.get("mc_total_p5"),
            "p95": d.get("mc_total_p95"),
        }
    return out


def _constructor_forecast_map(fc: dict) -> dict:
    out = {}
    for c in fc.get("constructors", []):
        cid = c.get("constructor_id")
        if cid is None:
            continue
        out[cid] = {
            "pred": c.get("expected_points", c.get("mc_total_mean")),
            "p5": c.get("mc_total_p5"),
            "p95": c.get("mc_total_p95"),
        }
    return out


def _metrics(pred_map: dict, actual_map: dict, topk: int = 5) -> dict:
    """Compute forecast-quality metrics over the entities present in both maps."""
    keys = [k for k in actual_map if k in pred_map and pred_map[k]["pred"] is not None]
    n = len(keys)
    if n == 0:
        return {"n": 0}
    preds = [float(pred_map[k]["pred"]) for k in keys]
    actuals = [float(actual_map[k]) for k in keys]
    errs = [p - a for p, a in zip(preds, actuals)]
    abs_errs = [abs(e) for e in errs]

    # top-K overlap by predicted vs actual
    pred_top = {k for k, _ in sorted(zip(keys, preds), key=lambda t: -t[1])[:topk]}
    act_top = {k for k, _ in sorted(zip(keys, actuals), key=lambda t: -t[1])[:topk]}
    top_overlap = len(pred_top & act_top)

    # 90% CI coverage (actual within p5..p95)
    covered = cov_n = 0
    for k in keys:
        p5, p95 = pred_map[k]["p5"], pred_map[k]["p95"]
        if p5 is not None and p95 is not None:
            cov_n += 1
            if p5 <= actual_map[k] <= p95:
                covered += 1

    return {
        "n": n,
        "mae": round(sum(abs_errs) / n, 2),
        "rmse": round((sum(e * e for e in errs) / n) ** 0.5, 2),
        "bias": round(sum(errs) / n, 2),
        "spearman": (round(_spearman(preds, actuals), 3)
                     if _spearman(preds, actuals) is not None else None),
        "top5_overlap": top_overlap,
        "topk": topk,
        "cov90": round(covered / cov_n, 3) if cov_n else None,
        "cov90_n": cov_n,
    }


def backtest_round(round_num: int, phase: str, official_round: dict) -> dict | None:
    fc, resolved = load_forecast(round_num, phase)
    if not fc:
        return None
    d_actual = official_round.get("drivers", {}) or {}
    c_actual = official_round.get("constructors", {}) or {}
    return {
        "round": round_num,
        "phase": resolved,
        "drivers": _metrics(_driver_forecast_map(fc), d_actual),
        "constructors": _metrics(_constructor_forecast_map(fc), c_actual),
    }


def _fmt(m: dict) -> str:
    if m.get("n", 0) == 0:
        return "no data"
    cov = f"{m['cov90']*100:.0f}%" if m.get("cov90") is not None else "n/a"
    sp = f"{m['spearman']:.3f}" if m.get("spearman") is not None else "n/a"
    return (f"MAE {m['mae']:>5} | RMSE {m['rmse']:>5} | bias {m['bias']:>+5} | "
            f"rho {sp:>6} | top5 {m['top5_overlap']}/{m['topk']} | cov90 {cov:>4}")


def _aggregate(rounds: list[dict], which: str) -> dict:
    """Mean of the per-round metrics for drivers|constructors."""
    ms = [r[which] for r in rounds if r[which].get("n", 0) > 0]
    if not ms:
        return {}

    def _mean(key):
        vals = [m[key] for m in ms if m.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "n_rounds": len(ms),
        "mae": _mean("mae"),
        "rmse": _mean("rmse"),
        "bias": _mean("bias"),
        "spearman": _mean("spearman"),
        "top5_overlap_avg": _mean("top5_overlap"),
        "cov90": _mean("cov90"),
    }


def run(phase: str, official: dict) -> dict:
    rounds = []
    for rn in sorted(int(r) for r in official.keys()):
        rd = backtest_round(rn, phase, official.get(str(rn), {}))
        if rd:
            rounds.append(rd)
    return {
        "phase_requested": phase,
        "rounds": rounds,
        "aggregate_drivers": _aggregate(rounds, "drivers"),
        "aggregate_constructors": _aggregate(rounds, "constructors"),
    }


def print_report(result: dict) -> None:
    print(f"\n{'=' * 92}")
    print(f"POINTS BACKTEST — forecast phase '{result['phase_requested']}' vs official points")
    print(f"{'=' * 92}")
    for rd in result["rounds"]:
        print(f"\n  Round {rd['round']} (forecast: {rd['phase']})")
        print(f"    Drivers      {_fmt(rd['drivers'])}")
        print(f"    Constructors {_fmt(rd['constructors'])}")

    def _agg_line(a):
        if not a:
            return "no data"
        cov = f"{a['cov90']*100:.0f}%" if a.get("cov90") is not None else "n/a"
        return (f"MAE {a['mae']} | RMSE {a['rmse']} | bias {a['bias']:+} | "
                f"rho {a['spearman']} | top5 {a['top5_overlap_avg']}/5 | cov90 {cov} "
                f"(n={a['n_rounds']} rounds)")

    print(f"\n{'=' * 92}")
    print("AGGREGATE (mean across rounds)")
    print(f"{'=' * 92}")
    print(f"  Drivers:      {_agg_line(result['aggregate_drivers'])}")
    print(f"  Constructors: {_agg_line(result['aggregate_constructors'])}")
    print("\n  MAE/RMSE/bias in fantasy points; rho = Spearman rank corr (ordering);")
    print("  top5 = avg # of the forecast's top-5 that were in the actual top-5;")
    print("  cov90 = share of actuals inside the MC 90% interval (target ~90%).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Points-level forecast backtest")
    ap.add_argument("--phase", default="post_fp",
                    choices=["post_fp", "pre_fp", "post_quali", "canonical"],
                    help="Which forecast archive to score (default post_fp = actionable)")
    ap.add_argument("--compare", action="store_true",
                    help="Show pre_fp vs post_fp side by side")
    ap.add_argument("--json", type=str, default=None, help="Dump full results to this path")
    args = ap.parse_args()

    official = load_official()
    if not official:
        print("No official_fantasy_points.json found.")
        sys.exit(0)

    if args.compare:
        results = {}
        for ph in ("pre_fp", "post_fp"):
            results[ph] = run(ph, official)
            print_report(results[ph])
        # Delta summary
        pre, post = results["pre_fp"]["aggregate_drivers"], results["post_fp"]["aggregate_drivers"]
        if pre and post and pre.get("mae") is not None and post.get("mae") is not None:
            print(f"\n{'=' * 92}")
            print("PRE-FP -> POST-FP (drivers): does FP data improve the forecast?")
            print(f"{'=' * 92}")
            print(f"  MAE  {pre['mae']} -> {post['mae']}  (delta {round(post['mae']-pre['mae'],2):+})")
            print(f"  rho  {pre['spearman']} -> {post['spearman']}  "
                  f"(delta {round(post['spearman']-pre['spearman'],3):+})")
        out = results
    else:
        result = run(args.phase, official)
        print_report(result)
        out = result

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n  Wrote {args.json}")

    sys.exit(0)


if __name__ == "__main__":
    main()
