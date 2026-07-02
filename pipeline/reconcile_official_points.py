"""
Reconcile computed actual fantasy points vs official F1 Fantasy points.

The pipeline computes actual fantasy points from Jolpica results
(11_actual_fantasy_points.py -> data/predictions/round{N}/actual_fantasy_points.json).
The user manually records the OFFICIAL F1 Fantasy points
(data/seed/official_fantasy_points.json). Official is ground truth. This script
diffs the two per round / driver / constructor so scoring bugs are visible and
measurable — it is the acceptance gate for the 2026-07-02 scoring-correctness
fix bundle (see docs/FIX_PLAN_2026-07-02_PROMPT.md).

Both files key entities by ABBREVIATION for drivers (e.g. "HAM") and by
constructor_id for teams (e.g. "mercedes").

Usage:
    python pipeline/reconcile_official_points.py
    python pipeline/reconcile_official_points.py --json data/experiments/reconcile.json

Always exits 0 — it is a report, not a test runner.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import PREDICTIONS_DIR, SEED_DIR

TOL = 0.01  # |diff| at or below this counts as an exact match


def load_official() -> dict:
    path = SEED_DIR / "official_fantasy_points.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f).get("rounds", {}) or {}


def load_computed(round_num: int) -> dict | None:
    path = PREDICTIONS_DIR / f"round{round_num}" / "actual_fantasy_points.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _computed_driver_map(computed: dict) -> dict:
    """abbrev -> full driver record (computed actuals key driver_id by abbrev)."""
    out = {}
    for d in computed.get("drivers", []):
        key = d.get("driver_abbrev") or d.get("driver_id")
        if key is not None:
            out[key] = d
    return out


def _computed_constructor_map(computed: dict) -> dict:
    out = {}
    for c in computed.get("constructors", []):
        cid = c.get("constructor_id")
        if cid is not None:
            out[cid] = c
    return out


def reconcile_round(round_num: int, official_round: dict, computed: dict) -> dict:
    """Return a structured diff for one round (drivers + constructors)."""
    off_drivers = official_round.get("drivers", {}) or {}
    off_cons = official_round.get("constructors", {}) or {}
    comp_drivers = _computed_driver_map(computed)
    comp_cons = _computed_constructor_map(computed)

    driver_rows = []
    for abbrev, off_pts in off_drivers.items():
        d = comp_drivers.get(abbrev)
        if d is None:
            driver_rows.append({
                "id": abbrev, "ours": None, "official": off_pts, "diff": None,
                "is_dnf": None, "status": None, "overtakes": None, "missing": True,
            })
            continue
        ours = d.get("total_points")
        diff = None if ours is None else round(ours - off_pts, 2)
        driver_rows.append({
            "id": abbrev, "ours": ours, "official": off_pts, "diff": diff,
            "is_dnf": d.get("is_dnf"), "status": d.get("status"),
            "overtakes": d.get("overtakes"), "missing": False,
        })

    cons_rows = []
    for cid, off_pts in off_cons.items():
        c = comp_cons.get(cid)
        if c is None:
            cons_rows.append({"id": cid, "ours": None, "official": off_pts,
                              "diff": None, "missing": True})
            continue
        ours = c.get("total_points")
        diff = None if ours is None else round(ours - off_pts, 2)
        cons_rows.append({"id": cid, "ours": ours, "official": off_pts,
                          "diff": diff, "missing": False})

    def _summ(rows):
        scored = [r for r in rows if r["diff"] is not None]
        n = len(scored)
        n_exact = sum(1 for r in scored if abs(r["diff"]) <= TOL)
        diffs = [r["diff"] for r in scored]
        abs_diffs = [abs(x) for x in diffs]
        return {
            "n": n,
            "n_exact": n_exact,
            "mean_diff": round(sum(diffs) / n, 3) if n else None,
            "mean_abs_diff": round(sum(abs_diffs) / n, 3) if n else None,
            "max_abs_diff": round(max(abs_diffs), 2) if n else None,
            "n_missing": sum(1 for r in rows if r["missing"]),
        }

    return {
        "round": round_num,
        "drivers": driver_rows,
        "constructors": cons_rows,
        "driver_summary": _summ(driver_rows),
        "constructor_summary": _summ(cons_rows),
    }


def print_round(rd: dict) -> None:
    n = rd["round"]
    print(f"\n{'=' * 78}")
    print(f"ROUND {n}")
    print(f"{'=' * 78}")

    def _print_mismatches(rows, kind):
        mism = [r for r in rows if r["diff"] is None or abs(r["diff"]) > TOL]
        mism.sort(key=lambda r: (-abs(r["diff"]) if r["diff"] is not None else 1e9))
        if not mism:
            print(f"  {kind}: all match official.")
            return
        print(f"  {kind} mismatches ({len(mism)}):")
        if kind == "Drivers":
            print(f"    {'id':<5} {'ours':>6} {'off':>6} {'diff':>6}  {'dnf':<5} {'ot':>3}  status")
            for r in mism:
                if r["missing"]:
                    print(f"    {r['id']:<5} {'--':>6} {r['official']:>6} {'MISSING':>6}")
                    continue
                dnf = str(r["is_dnf"])
                ot = r["overtakes"] if r["overtakes"] is not None else "-"
                print(f"    {r['id']:<5} {r['ours']:>6} {r['official']:>6} "
                      f"{r['diff']:>6.1f}  {dnf:<5} {ot:>3}  {r['status']}")
        else:
            print(f"    {'id':<14} {'ours':>6} {'off':>6} {'diff':>6}")
            for r in mism:
                if r["missing"]:
                    print(f"    {r['id']:<14} {'--':>6} {r['official']:>6} {'MISSING':>6}")
                    continue
                print(f"    {r['id']:<14} {r['ours']:>6} {r['official']:>6} {r['diff']:>6.1f}")

    _print_mismatches(rd["drivers"], "Drivers")
    ds = rd["driver_summary"]
    print(f"  Driver summary: {ds['n_exact']}/{ds['n']} exact, "
          f"mean_diff={ds['mean_diff']}, mean_abs={ds['mean_abs_diff']}, "
          f"max_abs={ds['max_abs_diff']}, missing={ds['n_missing']}")
    _print_mismatches(rd["constructors"], "Constructors")
    cs = rd["constructor_summary"]
    print(f"  Constructor summary: {cs['n_exact']}/{cs['n']} exact, "
          f"mean_diff={cs['mean_diff']}, mean_abs={cs['mean_abs_diff']}, "
          f"max_abs={cs['max_abs_diff']}, missing={cs['n_missing']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile computed vs official F1 Fantasy points")
    parser.add_argument("--json", type=str, default=None, help="Dump full diff structure to this path")
    parser.add_argument("--round", type=int, default=None, help="Only this round")
    args = parser.parse_args()

    official = load_official()
    if not official:
        print("No official_fantasy_points.json found or empty.")
        sys.exit(0)

    rounds = sorted(int(r) for r in official.keys())
    if args.round is not None:
        rounds = [args.round]

    results = []
    for rn in rounds:
        computed = load_computed(rn)
        if computed is None:
            print(f"\nROUND {rn}: no computed actuals (skipping)")
            continue
        rd = reconcile_round(rn, official.get(str(rn), {}), computed)
        results.append(rd)
        print_round(rd)

    # Season-level summary
    print(f"\n{'=' * 78}")
    print("SEASON SUMMARY")
    print(f"{'=' * 78}")
    print(f"  {'round':>5} | {'drv exact':>10} | {'drv mean_abs':>12} | "
          f"{'con exact':>10} | {'con mean_abs':>12}")
    tot_d_exact = tot_d_n = 0
    tot_c_exact = tot_c_n = 0
    d_abs_all = []
    c_abs_all = []
    for rd in results:
        ds, cs = rd["driver_summary"], rd["constructor_summary"]
        tot_d_exact += ds["n_exact"]; tot_d_n += ds["n"]
        tot_c_exact += cs["n_exact"]; tot_c_n += cs["n"]
        for r in rd["drivers"]:
            if r["diff"] is not None:
                d_abs_all.append(abs(r["diff"]))
        for r in rd["constructors"]:
            if r["diff"] is not None:
                c_abs_all.append(abs(r["diff"]))
        print(f"  {rd['round']:>5} | {ds['n_exact']:>4}/{ds['n']:<5} | "
              f"{str(ds['mean_abs_diff']):>12} | {cs['n_exact']:>4}/{cs['n']:<5} | "
              f"{str(cs['mean_abs_diff']):>12}")
    d_mean_abs = round(sum(d_abs_all) / len(d_abs_all), 3) if d_abs_all else None
    c_mean_abs = round(sum(c_abs_all) / len(c_abs_all), 3) if c_abs_all else None
    d_pct = round(100 * tot_d_exact / tot_d_n, 1) if tot_d_n else None
    c_pct = round(100 * tot_c_exact / tot_c_n, 1) if tot_c_n else None
    print(f"  {'-' * 70}")
    print(f"  TOTAL Drivers:      {tot_d_exact}/{tot_d_n} exact ({d_pct}%), "
          f"mean_abs_diff={d_mean_abs}")
    print(f"  TOTAL Constructors: {tot_c_exact}/{tot_c_n} exact ({c_pct}%), "
          f"mean_abs_diff={c_mean_abs}")

    if args.json:
        out = {
            "results": results,
            "overall": {
                "driver_exact": tot_d_exact, "driver_n": tot_d_n,
                "driver_exact_pct": d_pct, "driver_mean_abs_diff": d_mean_abs,
                "constructor_exact": tot_c_exact, "constructor_n": tot_c_n,
                "constructor_exact_pct": c_pct, "constructor_mean_abs_diff": c_mean_abs,
            },
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n  Wrote {args.json}")

    sys.exit(0)


if __name__ == "__main__":
    main()
