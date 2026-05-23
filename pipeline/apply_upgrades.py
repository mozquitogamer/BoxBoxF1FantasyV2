"""
BoxBoxF1Fantasy — Apply manual team-upgrade modifiers.

Reads `data/seed/team_upgrades.json` and the round's baseline
`predictions.parquet`. For each driver, adds the team's `pace_bump` to the
raw XGBRanker score, re-ranks, then computes the position-points delta vs
the baseline. Writes a sidecar `adjustments.json` per round which
`08_export_website_json.py` merges into the public JSON as
`expected_points_adjusted` / `predicted_finish_adjusted` (etc.).

The BASELINE ML prediction is preserved on disk and in the JSON. The
adjusted view is purely overlay — the user can compare the model's view
with their "if this upgrade lands" view side-by-side.

Usage:
    python pipeline/apply_upgrades.py --round 7
    python pipeline/apply_upgrades.py --round 7 --clear   # remove adjustments

Notes:
- pace_bump is in raw XGBRanker score units. From the trained models, a
  ~0.30-0.50 bump corresponds to roughly 1 finishing position. The dashboard
  UI accepts the raw number so the user can dial it in from FP signal.
- For drivers in teams not listed in team_upgrades.json::modifiers, no bump
  applies (zero delta).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PREDICTIONS_DIR, SEED_DIR
from config.fantasy_scoring import (
    QUALIFYING_POSITION_POINTS,
    RACE_POSITION_POINTS,
    SPRINT_POSITION_POINTS,
    SPRINT_POSITIONS_GAINED_PER_POS,
    RACE_POSITIONS_GAINED_PER_POS,
)


def _load_upgrades(round_num: int) -> tuple[dict[str, float], dict[str, float]]:
    """Return ({constructor_id: pace_bump}, {driver_abbrev: pace_bump}) for the round, or ({},{}).

    `modifiers` (team-level, keyed by constructor_id) and `driver_modifiers`
    (driver-level, keyed by driver_abbrev like 'VER') compose additively at
    apply time: total_bump_per_driver = team_bump + driver_bump.
    """
    path = SEED_DIR / "team_upgrades.json"
    if not path.exists():
        return {}, {}
    with open(path) as f:
        data = json.load(f)
    if data.get("round") != round_num:
        return {}, {}

    team_mods = data.get("modifiers", {}) or {}
    by_team = {
        team: float(info.get("pace_bump", 0.0) or 0.0)
        for team, info in team_mods.items()
        if float(info.get("pace_bump", 0.0) or 0.0) != 0.0
    }

    driver_mods = data.get("driver_modifiers", {}) or {}
    by_driver = {
        abbrev: float(info.get("pace_bump", 0.0) or 0.0)
        for abbrev, info in driver_mods.items()
        if float(info.get("pace_bump", 0.0) or 0.0) != 0.0
    }
    return by_team, by_driver


def _rerank(raw_scores: pd.Series, bumps: pd.Series) -> pd.Series:
    """Add per-driver bumps to raw scores, re-rank descending (best=1)."""
    adjusted = raw_scores + bumps
    # Use method='first' to break ties stably (same as 06_run_predictions)
    return pd.Series(-adjusted).rank(method="first").astype(int)


def _quali_delta(baseline_pos: int, adjusted_pos: int) -> int:
    return (QUALIFYING_POSITION_POINTS.get(adjusted_pos, 0)
            - QUALIFYING_POSITION_POINTS.get(baseline_pos, 0))


def _race_delta(baseline_pos: int, adjusted_pos: int, baseline_grid: int) -> int:
    """Race position delta = position-points delta + positions-gained delta.

    Positions-gained is measured from `baseline_grid` (the predicted qualifying
    position which we treat as the grid for adjusted view — bumps shift grid
    AND finishing position together, so the gained delta is the difference of
    differences).
    """
    pts_delta = (RACE_POSITION_POINTS.get(adjusted_pos, 0)
                 - RACE_POSITION_POINTS.get(baseline_pos, 0))
    # Positions gained vs grid (baseline_grid - finishing_pos). The grid for
    # adjusted view also moves by the team's bump effect on quali, but for
    # this overlay we approximate that the adjusted finishing-position move
    # already captures the team's pace advantage. So we only count the FINISH
    # position improvement here; the grid effect is captured in the quali delta.
    gained_delta = (baseline_pos - adjusted_pos) * RACE_POSITIONS_GAINED_PER_POS
    return pts_delta + gained_delta


def _sprint_delta(baseline_pos: int, adjusted_pos: int) -> int:
    pts_delta = (SPRINT_POSITION_POINTS.get(adjusted_pos, 0)
                 - SPRINT_POSITION_POINTS.get(baseline_pos, 0))
    gained_delta = (baseline_pos - adjusted_pos) * SPRINT_POSITIONS_GAINED_PER_POS
    return pts_delta + gained_delta


def apply_upgrades(round_num: int) -> bool:
    """Return True if an adjustments.json was written, False otherwise."""
    pred_path = PREDICTIONS_DIR / f"round{round_num}" / "predictions.parquet"
    if not pred_path.exists():
        print(f"  No predictions.parquet for round {round_num}")
        return False

    bumps_by_team, bumps_by_driver = _load_upgrades(round_num)
    adj_path = PREDICTIONS_DIR / f"round{round_num}" / "adjustments.json"

    if not bumps_by_team and not bumps_by_driver:
        # No upgrades for this round — make sure no stale adjustments.json lingers.
        if adj_path.exists():
            adj_path.unlink()
            print(f"  Cleared stale adjustments.json (no upgrades configured)")
        else:
            print(f"  No upgrades configured for round {round_num}")
        return False

    df = pd.read_parquet(pred_path)
    # Compose: bump_per_driver = team_bump + driver_bump
    team_bumps = df["constructor_id"].map(bumps_by_team).fillna(0.0)
    driver_bumps = df["driver_abbrev"].map(bumps_by_driver).fillna(0.0)
    bumps = team_bumps + driver_bumps
    n_drivers_affected = (bumps != 0).sum()
    print(f"  Round {round_num}: applying bumps to {n_drivers_affected} drivers "
          f"({len(bumps_by_team)} team-level, {len(bumps_by_driver)} driver-level)")

    # Re-rank each session
    out_rows = []
    adj_quali = _rerank(df["predicted_quali_raw"], bumps)
    adj_race = _rerank(df["predicted_race_raw"], bumps)
    has_sprint = "predicted_sprint_raw" in df.columns and df["predicted_sprint_raw"].notna().any()
    adj_sprint = _rerank(df["predicted_sprint_raw"], bumps) if has_sprint else None

    for i, row in df.iterrows():
        base_q = int(row["predicted_quali_position"])
        base_r = int(row["predicted_race_position"])
        adj_q = int(adj_quali.iloc[i])
        adj_r = int(adj_race.iloc[i])

        q_delta = _quali_delta(base_q, adj_q)
        r_delta = _race_delta(base_r, adj_r, base_q)

        entry = {
            "driver_id": row["driver_id"],
            "driver_abbrev": row.get("driver_abbrev", row["driver_id"]),
            "constructor_id": row["constructor_id"],
            "pace_bump": float(bumps.iloc[i]),
            "baseline": {
                "quali": base_q,
                "race": base_r,
            },
            "adjusted": {
                "quali": adj_q,
                "race": adj_r,
            },
            "points_delta": {
                "quali": q_delta,
                "race": r_delta,
            },
        }

        if has_sprint and pd.notna(row.get("predicted_sprint_position")):
            base_s = int(row["predicted_sprint_position"])
            adj_s = int(adj_sprint.iloc[i])
            entry["baseline"]["sprint"] = base_s
            entry["adjusted"]["sprint"] = adj_s
            entry["points_delta"]["sprint"] = _sprint_delta(base_s, adj_s)

        # Total expected-points delta — sum of quali + race (+ sprint if present)
        total = q_delta + r_delta + entry["points_delta"].get("sprint", 0)
        entry["total_points_delta"] = total
        out_rows.append(entry)

    payload = {
        "round": round_num,
        "modifiers_applied": bumps_by_team,
        "driver_modifiers_applied": bumps_by_driver,
        "drivers": out_rows,
    }

    adj_path.parent.mkdir(parents=True, exist_ok=True)
    with open(adj_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  Wrote {adj_path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply team upgrade modifiers")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--clear", action="store_true",
                        help="Delete the round's adjustments.json (no apply)")
    args = parser.parse_args()

    if args.clear:
        adj_path = PREDICTIONS_DIR / f"round{args.round}" / "adjustments.json"
        if adj_path.exists():
            adj_path.unlink()
            print(f"Deleted {adj_path}")
        else:
            print(f"No adjustments.json at {adj_path}")
        return

    apply_upgrades(args.round)


if __name__ == "__main__":
    main()
