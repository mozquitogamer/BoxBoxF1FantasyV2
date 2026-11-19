"""Exploratory tests of practice-simulation evidence weighting.

Qualifying: walk forward through completed 2026 rounds, retraining the current
ranker before each round and changing only the per-driver FP blend weight.
Race: use immutable Friday post-FP forecast snapshots and FP1-only run quality
to test conditional 90% MC interval widening. Production weights stay unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import TRAINING_DATA_DIR  # noqa: E402
from config.track_classifications import fp_quali_blend_weight  # noqa: E402
from pipeline import sweep_fp_blend as sweep  # noqa: E402
from pipeline.fp_simulations import analyze_comparable_long_runs  # noqa: E402

SPRINT_ROUNDS = {2, 6, 7, 11, 14, 18}
REPORT_PATH = ROOT / "data" / "experiments" / "sim_evidence_backtest_2026.json"


def round_bootstrap_ci(deltas: dict[int, float], seed: int = 42) -> list[float]:
    """CI on equal-weighted round differences, preserving within-round dependence."""
    values = np.array(list(deltas.values()), dtype=float)
    if len(values) < 2:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(10_000, len(values)), replace=True).mean(axis=1)
    return np.percentile(draws, [2.5, 97.5]).round(4).tolist()


def qualify() -> dict:
    data = pd.read_parquet(TRAINING_DATA_DIR / "all_training_data.parquet")
    features = [
        c for c in sweep.build_quali_feature_list(data.columns.tolist())
        if c in data.columns and not c.startswith("weather_")
    ]
    rounds = sorted(
        int(r) for r in data.loc[
            data.season.eq(2026) & data.quali_position.notna(), "round"
        ].unique()
    )
    variants = ("baseline", "gap3_shrink25", "gap3_shrink50", "gap5_shrink25", "gap5_shrink50")
    records = []
    for rnd in rounds:
        train = data.loc[
            ((data.season < 2026) | (data.season.eq(2026) & data["round"].lt(rnd)))
            & data.quali_position.notna()
        ].copy()
        test = data.loc[
            data.season.eq(2026) & data["round"].eq(rnd) & data.quali_position.notna()
        ].copy().reset_index(drop=True)
        if len(train) < 100 or len(test) < 5:
            continue
        model = sweep.fit_fold_model(train, features)
        raw = model.predict(test[features])
        z_model = sweep._zscore_np(raw)

        # Same representative gate and composite as production, for all tyres.
        best = pd.to_numeric(test.best_lap_time, errors="coerce")
        best3 = pd.to_numeric(test.best_3_lap_avg, errors="coerce")
        best5 = pd.to_numeric(test.best_5_lap_avg, errors="coerce")
        laps = pd.to_numeric(test.total_laps, errors="coerce")
        representative = laps.ge(5) & best5.sub(best).between(0, 5)
        masked = test.copy()
        for col in sweep.PACE_COLS:
            masked[col] = pd.to_numeric(masked[col], errors="coerce").where(representative)
        composite = sweep.fp_composite(masked)
        has_pace = composite.notna().to_numpy()
        pace_z = np.zeros(len(test))
        if int(has_pace.sum()) >= sweep.MIN_DRIVERS_WITH_PACE:
            pace_z[has_pace] = sweep._zscore_np(composite.to_numpy()[has_pace])
        circuit, _ = sweep.circuit_difficulty(rnd)
        base_w = (0.15 if rnd in SPRINT_ROUNDS else
                  fp_quali_blend_weight(circuit, 0.6, 0.8, 6))

        # A smaller best-3/best-5 gap means more repeatable quick laps. Rank gaps
        # within the weekend so a fast circuit is not assigned a harsher weight.
        weights = {"baseline": np.full(len(test), base_w)}
        for name, gap in (("gap3", best3 - best), ("gap5", best5 - best)):
            pct = gap.where(has_pace).rank(pct=True).fillna(1).to_numpy()
            for penalty in (0.25, 0.50):
                weights[f"{name}_shrink{int(penalty * 100)}"] = base_w * (1 - penalty * pct)

        actual = test.quali_position.to_numpy(dtype=float)
        for variant in variants:
            score = z_model.copy()
            if int(has_pace.sum()) >= sweep.MIN_DRIVERS_WITH_PACE:
                w = weights[variant]
                score[has_pace] = (1 - w[has_pace]) * z_model[has_pace] + w[has_pace] * pace_z[has_pace]
            ranks = pd.Series(-score).rank(method="first").to_numpy(dtype=int)
            for i, err in enumerate(np.abs(ranks - actual)):
                records.append({"round": rnd, "driver": str(test.iloc[i].driver_id),
                                "sprint": rnd in SPRINT_ROUNDS, "variant": variant,
                                "abs_error": float(err), "pace_available": bool(has_pace[i])})
        print(f"Quali R{rnd}: {len(test)} drivers; {int(has_pace.sum())} representative FP samples", flush=True)

    frame = pd.DataFrame(records)
    outcomes = {}
    for label, subset in (("normal", frame.loc[~frame.sprint]),
                          ("sprint", frame.loc[frame.sprint]),
                          ("all", frame)):
        if subset.empty:
            continue
        pivot = subset.pivot(index=["round", "driver"], columns="variant", values="abs_error")
        base = pivot["baseline"]
        res = {"rounds": sorted(int(r) for r in subset["round"].unique()),
               "drivers": int(len(pivot)), "baseline_mae": round(float(base.mean()), 4),
               "variants": {}}
        for variant in variants[1:]:
            delta = pivot[variant] - base
            per_round = delta.groupby(level="round").mean().to_dict()
            res["variants"][variant] = {
                "mae": round(float(pivot[variant].mean()), 4),
                "delta_mae": round(float(delta.mean()), 4),
                "round_mean_delta_ci95": round_bootstrap_ci(per_round),
                "round_deltas": {str(k): round(float(v), 4) for k, v in per_round.items()},
                "rounds_better": int(sum(v < 0 for v in per_round.values())),
            }
        outcomes[label] = res
    return outcomes


def interval_score(low: float, high: float, actual: float, alpha: float = 0.10) -> float:
    return ((high - low) + (2 / alpha) * max(low - actual, 0)
            + (2 / alpha) * max(actual - high, 0))


def comparable_fp1_pace(run_data: dict) -> dict[str, tuple[float, str]]:
    """Within-compound pace z-scores; a run's tyre never determines eligibility."""
    per_compound: dict[str, list[tuple[str, dict]]] = {}
    for driver, record in run_data.items():
        best_by_compound: dict[str, dict] = {}
        for run in record["runs"]:
            if run["quality"] not in {"clean", "partial"}:
                continue
            old = best_by_compound.get(run["compound"])
            quality_order = {"clean": 2, "partial": 1}
            if old is None or (quality_order[run["quality"]], run["laps"]) > (
                quality_order[old["quality"]], old["laps"]
            ):
                best_by_compound[run["compound"]] = run
        for compound, run in best_by_compound.items():
            per_compound.setdefault(compound, []).append((driver, run))
    signals: dict[str, list[tuple[float, str]]] = {}
    for runs in per_compound.values():
        if len(runs) < 3:
            continue
        times = np.array([run["median_pace"] for _, run in runs], dtype=float)
        std = float(times.std())
        if std <= 1e-9:
            continue
        for (driver, run), z in zip(runs, -(times - times.mean()) / std):
            signals.setdefault(driver, []).append((float(z), run["quality"]))
    return {
        driver: (float(np.mean([z for z, _ in values])),
                 "clean" if any(q == "clean" for _, q in values) else "partial")
        for driver, values in signals.items()
    }


def race() -> dict:
    rows = []
    snapshots = []
    pace_rounds = []
    for rnd in range(1, 17):
        actual_path = ROOT / "web" / "public" / "data" / f"actual_round{rnd}.json"
        fp1_path = ROOT / "data" / "processed" / "laps" / f"round{rnd}" / "all_laps_fp1.parquet"
        files = sorted((ROOT / "data" / "audit" / "snapshots" / f"round{rnd}").glob("*_post_fp.json"))
        if not (actual_path.exists() and fp1_path.exists() and files):
            continue
        actual_data = json.loads(actual_path.read_text(encoding="utf-8"))
        race_date = str(actual_data.get("date") or "")
        # The public actual file may not carry a date. Use the forecast's race date.
        eligible = []
        for path in files:
            snap = json.loads(path.read_text(encoding="utf-8"))
            if snap.get("prediction_metadata", {}).get("used_fp_features") is not True:
                continue
            event_date = str(snap.get("predictions", {}).get("date") or race_date)
            timestamp_date = str(snap.get("audit_timestamp", ""))[:10]
            if event_date and timestamp_date < event_date and snap.get("prediction_metadata", {}).get("is_post_quali") is False:
                eligible.append((path, snap))
        if not eligible:
            continue
        path, snap = eligible[0]  # earliest post-FP snapshot, before race day
        actual = {d["driver_id"]: d for d in actual_data["drivers"]}
        laps = pd.read_parquet(fp1_path).assign(session="FP1")
        run_data = analyze_comparable_long_runs(laps)["drivers"]
        pace = comparable_fp1_pace(run_data)
        driver_preds = snap["predictions"]["drivers"]
        raw_scores = [d.get("raw_scores", {}).get("race") for d in driver_preds]
        if all(s is not None for s in raw_scores):
            model_z = sweep._zscore_np(np.asarray(raw_scores, dtype=float))
            present = np.array([d["driver_id"] in pace for d in driver_preds])
            if present.sum() >= 5:
                pace_values = np.array([pace[d["driver_id"]][0] if d["driver_id"] in pace else 0
                                        for d in driver_preds])
                pace_z = np.zeros(len(driver_preds))
                pace_z[present] = sweep._zscore_np(pace_values[present])
                base_rank = pd.Series(-model_z).rank(method="first").to_numpy(dtype=int)
                if all(int(base_rank[i]) == d["predicted_finish"] for i, d in enumerate(driver_preds)):
                    for weight in (0.0, 0.10, 0.20):
                        score = model_z.copy()
                        for i, d in enumerate(driver_preds):
                            if present[i]:
                                reliability = 1.0 if pace[d["driver_id"]][1] == "clean" else 0.5
                                w = weight * reliability
                                score[i] = (1 - w) * model_z[i] + w * pace_z[i]
                        ranks = pd.Series(-score).rank(method="first").to_numpy(dtype=int)
                        for i, d in enumerate(driver_preds):
                            truth = actual.get(d["driver_id"])
                            if (not truth or truth.get("is_dnf") or truth.get("is_dsq")
                                    or truth.get("is_dns") or truth.get("race_position") is None):
                                continue
                            pace_rounds.append({"round": rnd, "driver": d["driver_id"],
                                                "weight": weight, "abs_error": float(abs(ranks[i] - truth["race_position"]))})
        n = 0
        for pred in driver_preds:
            truth = actual.get(pred["driver_id"])
            if not truth or truth.get("total_points") is None:
                continue
            qualities = {r["quality"] for r in run_data.get(pred["driver_id"], {}).get("runs", [])}
            quality = ("clean" if "clean" in qualities else
                       "partial" if "partial" in qualities else "weak_or_missing")
            low, high = pred.get("mc_total_p5"), pred.get("mc_total_p95")
            if low is None or high is None:
                continue
            center = pred.get("mc_total_median")
            if center is None:
                center = (low + high) / 2
            rows.append({"round": rnd, "driver": pred["driver_id"], "quality": quality,
                         "actual_points": float(truth["total_points"]),
                         "low": float(low), "high": float(high), "center": float(center),
                         "expected": pred.get("expected_points"),
                         "predicted_finish": pred.get("predicted_finish"),
                         "actual_finish": truth.get("race_position"),
                         "finished": not (truth.get("is_dnf") or truth.get("is_dsq") or truth.get("is_dns"))})
            n += 1
        snapshots.append({"round": rnd, "file": str(path.relative_to(ROOT)), "n": n,
                          "fp_evidence": "FP1 only"})
        print(f"Race R{rnd}: {n} drivers; {path.name}", flush=True)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"snapshots": [], "results": {}, "pace_adjustment": {}}
    variants = {
        "baseline": {"clean": 1.0, "partial": 1.0, "weak_or_missing": 1.0},
        "mild_widen": {"clean": 1.0, "partial": 1.1, "weak_or_missing": 1.2},
        "strong_widen": {"clean": 1.0, "partial": 1.2, "weak_or_missing": 1.4},
        "uniform_10pct": {"clean": 1.1, "partial": 1.1, "weak_or_missing": 1.1},
        "uniform_20pct": {"clean": 1.2, "partial": 1.2, "weak_or_missing": 1.2},
    }
    results = {}
    for name, factors in variants.items():
        work = frame.copy()
        factor = work.quality.map(factors)
        low = work.center + factor * (work.low - work.center)
        high = work.center + factor * (work.high - work.center)
        work["covered"] = (work.actual_points >= low) & (work.actual_points <= high)
        work["width"] = high - low
        work["score"] = [interval_score(l, h, y) for l, h, y in zip(low, high, work.actual_points)]
        results[name] = {
            "n": int(len(work)), "coverage": round(float(work.covered.mean()), 4),
            "mean_width": round(float(work.width.mean()), 4),
            "mean_interval_score": round(float(work.score.mean()), 4),
            "by_quality": {},
            "per_round_interval_score": {str(k): round(float(v), 4) for k, v in work.groupby("round").score.mean().items()},
        }
        for quality, group in work.groupby("quality"):
            result = {"n": int(len(group)), "coverage": round(float(group.covered.mean()), 4),
                      "mean_width": round(float(group.width.mean()), 4),
                      "mean_interval_score": round(float(group.score.mean()), 4)}
            if name == "baseline":
                finishers = group.loc[group.finished & group.actual_finish.notna() & group.predicted_finish.notna()]
                result["finishers"] = int(len(finishers))
                result["finish_mae"] = round(float((finishers.actual_finish - finishers.predicted_finish).abs().mean()), 4)
                expected = pd.to_numeric(group.expected, errors="coerce")
                result["fantasy_mae"] = round(float((expected - group.actual_points).abs().mean()), 4)
            results[name]["by_quality"][quality] = result
    baseline_rounds = results["baseline"]["per_round_interval_score"]
    for name in ("mild_widen", "strong_widen", "uniform_10pct", "uniform_20pct"):
        deltas = {int(k): results[name]["per_round_interval_score"][k] - v for k, v in baseline_rounds.items()}
        results[name]["round_mean_delta_ci95"] = round_bootstrap_ci(deltas)
        results[name]["rounds_better"] = int(sum(v < 0 for v in deltas.values()))
        results[name]["interval_score_delta"] = round(
            results[name]["mean_interval_score"] - results["baseline"]["mean_interval_score"], 4)
    for quality_name, uniform_name in (("mild_widen", "uniform_10pct"),
                                       ("strong_widen", "uniform_20pct")):
        q = results[quality_name]
        u = results[uniform_name]
        deltas = {int(k): q["per_round_interval_score"][k] - v
                  for k, v in u["per_round_interval_score"].items()}
        q["vs_similar_width_uniform"] = {
            "interval_score_delta": round(q["mean_interval_score"] - u["mean_interval_score"], 4),
            "round_mean_delta_ci95": round_bootstrap_ci(deltas),
            "rounds_better": int(sum(v < 0 for v in deltas.values())),
        }
    pace_results = {}
    if pace_rounds:
        pace_frame = pd.DataFrame(pace_rounds)
        pivot = pace_frame.pivot(index=["round", "driver"], columns="weight", values="abs_error")
        pace_results = {"rounds": sorted(int(r) for r in pace_frame["round"].unique()),
                        "finishers": int(len(pivot)),
                        "baseline_mae": round(float(pivot[0.0].mean()), 4), "variants": {}}
        for weight in (0.10, 0.20):
            delta = pivot[weight] - pivot[0.0]
            per_round = delta.groupby(level="round").mean().to_dict()
            pace_results["variants"][str(weight)] = {
                "mae": round(float(pivot[weight].mean()), 4),
                "delta_mae": round(float(delta.mean()), 4),
                "round_mean_delta_ci95": round_bootstrap_ci(per_round),
                "rounds_better": int(sum(v < 0 for v in per_round.values())),
                "round_deltas": {str(k): round(float(v), 4) for k, v in per_round.items()},
            }
    return {"snapshots": snapshots, "results": results, "pace_adjustment": pace_results}


def main() -> None:
    report = {"method": "exploratory retrospective paired test; no production changes",
              "qualifying": qualify(), "race": race()}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {REPORT_PATH}")
    for cohort, data in report["qualifying"].items():
        print(f"Quali {cohort}: baseline={data['baseline_mae']:.3f}, n={data['drivers']}")
        for name, result in data["variants"].items():
            print(f"  {name}: MAE={result['mae']:.3f}, delta={result['delta_mae']:+.3f}, "
                  f"CI={result['round_mean_delta_ci95']}")
    for name, result in report["race"]["results"].items():
        print(f"Race {name}: coverage={result['coverage']:.3f}, width={result['mean_width']:.1f}, "
              f"interval score={result['mean_interval_score']:.2f}")
    pace = report["race"]["pace_adjustment"]
    if pace:
        print(f"Race pace blend: baseline finish MAE={pace['baseline_mae']:.3f}, n={pace['finishers']}")
        for name, result in pace["variants"].items():
            print(f"  weight={name}: MAE={result['mae']:.3f}, delta={result['delta_mae']:+.3f}, "
                  f"CI={result['round_mean_delta_ci95']}")


if __name__ == "__main__":
    main()
