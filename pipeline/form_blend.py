"""Blend published expected points with recency-weighted 2026 fantasy form.

    blended = w * model + (1 - w) * form

``model`` is the Monte Carlo mean the export already publishes. ``form`` is an
exponentially weighted mean (half-life 3 rounds) of the asset's official F1
Fantasy points in earlier 2026 rounds; a driver with no history takes his
current team's 2026 average per driver. Only official points from rounds that
finished before this one are used, so the overlay is available at lock.

The whole simulated distribution is shifted by the same amount
``delta = (1 - w) * (form - model)``: mean, median and percentiles move together
and interval widths are unchanged. ``projected_points`` (the deterministic
"if the predicted order holds" score) is left alone.

Evidence (accuracy lab, branch accuracy-lab, lab/reports/experiment_log.csv):
weights chosen walk-forward on R10-R18 settled at 0.4 pre-FP and 0.5 post-FP and
are re-chosen identically from R7-R22. On R19-R22 with frozen weights, pre-FP
lineup points +29.5 per round and driver MAE -0.81; post-FP driver MAE -0.77,
constructor MAE -1.11, lineup points unchanged. Post-quali is not blended:
form knows nothing about the qualifying result that is already locked in.
"""
from __future__ import annotations

import json
from pathlib import Path

from config.settings import SEED_DIR, WEB_DATA_DIR

FORM_BLEND_TUNABLES = {
    "enabled": True,
    # Weight on the model. 1.0 = model only, 0.0 = form only. Missing phase = no blend.
    "model_weight": {"pre_fp": 0.4, "post_fp": 0.5},
    "half_life_rounds": 3.0,
}

DRIVER_SHIFT_FIELDS = (
    "expected_points", "expected_points_race", "expected_points_adjusted",
    "mc_total_mean", "mc_total_median", "mc_total_p5", "mc_total_p25", "mc_total_p75", "mc_total_p95",
    "mc_race_pts_mean", "mc_race_pts_median", "mc_race_pts_p5", "mc_race_pts_p25", "mc_race_pts_p75",
    "mc_race_pts_p95",
)
CONSTRUCTOR_SHIFT_FIELDS = (
    "expected_points", "expected_points_race", "expected_points_adjusted",
    "mc_total_mean", "mc_total_median", "mc_total_p5", "mc_total_p25", "mc_total_p75", "mc_total_p95",
)


def _load_official(seed_dir: Path) -> dict[int, dict]:
    with open(seed_dir / "official_fantasy_points.json") as f:
        rounds = json.load(f)["rounds"]
    return {int(k): v for k, v in rounds.items()}


def _team_by_round(web_dir: Path, rounds: list[int]) -> dict[int, dict[str, str]]:
    out = {}
    for r in rounds:
        path = web_dir / f"actual_round{r}.json"
        if path.exists():
            with open(path) as f:
                out[r] = {d["driver_id"]: d["constructor"] for d in json.load(f).get("drivers", [])}
        else:
            out[r] = {}
    return out


def _ewm(values: list[float], half_life: float) -> float:
    n = len(values)
    weights = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
    return sum(w * v for w, v in zip(weights, values)) / sum(weights)


def _asset_keys(entry: dict) -> list[str]:
    keys = [entry.get("driver_id"), entry.get("asset_id"), *(entry.get("asset_legacy_ids") or [])]
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def recency_form(payload: dict, round_num: int, *, seed_dir: Path = SEED_DIR, web_dir: Path = WEB_DATA_DIR,
                 half_life: float | None = None) -> tuple[dict[str, float], dict[str, float], list[int]]:
    """Form points per driver entry (keyed by entry driver_id) and per constructor, plus the rounds used."""
    half_life = half_life or FORM_BLEND_TUNABLES["half_life_rounds"]
    official = _load_official(seed_dir)
    past = sorted(r for r in official if r < round_num)
    teams = _team_by_round(web_dir, past)
    drivers: dict[str, float] = {}
    for entry in payload.get("drivers", []):
        series = []
        for r in past:
            pts = official[r].get("drivers", {})
            for k in _asset_keys(entry):
                if k in pts:
                    series.append(float(pts[k]))
                    break
        if series:
            drivers[entry["driver_id"]] = _ewm(series, half_life)
            continue
        team = entry.get("constructor")
        team_pts = [float(v) for r in past for k, v in official[r].get("drivers", {}).items()
                    if teams[r].get(k) == team]
        if team_pts:
            drivers[entry["driver_id"]] = sum(team_pts) / len(team_pts)
    constructors: dict[str, float] = {}
    for entry in payload.get("constructors", []):
        cid = entry["constructor_id"]
        series = [float(official[r]["constructors"][cid]) for r in past if cid in official[r].get("constructors", {})]
        if series:
            constructors[cid] = _ewm(series, half_life)
    return drivers, constructors, past


def _shift(entry: dict, fields: tuple[str, ...], delta: float) -> None:
    for field in fields:
        if isinstance(entry.get(field), (int, float)):
            entry[field] = round(float(entry[field]) + delta, 1)
    price = entry.get("current_price") or 0
    if price > 0 and isinstance(entry.get("expected_points"), (int, float)):
        entry["value_score"] = round(entry["expected_points"] / price, 2)


def apply_form_blend(payload: dict, round_num: int, phase: str, *, seed_dir: Path = SEED_DIR,
                     web_dir: Path = WEB_DATA_DIR, tunables: dict | None = None) -> dict:
    """Blend the payload in place and record what was done under payload["form_blend"]."""
    tunables = tunables or FORM_BLEND_TUNABLES
    if payload.get("form_blend", {}).get("applied"):
        return payload["form_blend"]  # never blend twice
    weight = tunables["model_weight"].get(phase)
    if not tunables.get("enabled", True) or weight is None:
        payload["form_blend"] = {"applied": False, "phase": phase,
                                 "reason": "disabled" if not tunables.get("enabled", True) else "phase_not_blended"}
        return payload["form_blend"]
    weight = float(weight)
    drivers_form, cons_form, past = recency_form(payload, round_num, seed_dir=seed_dir, web_dir=web_dir,
                                                 half_life=tunables["half_life_rounds"])
    if len(past) < 3:
        payload["form_blend"] = {"applied": False, "phase": phase, "reason": "fewer_than_3_completed_rounds"}
        return payload["form_blend"]
    n_d = n_c = 0
    for entry in payload.get("drivers", []):
        form = drivers_form.get(entry["driver_id"])
        model = entry.get("expected_points")
        if form is None or not isinstance(model, (int, float)):
            continue
        entry["expected_points_model"] = round(float(model), 1)
        entry["form_points"] = round(form, 1)
        _shift(entry, DRIVER_SHIFT_FIELDS, (1.0 - weight) * (form - float(model)))
        n_d += 1
    for entry in payload.get("constructors", []):
        form = cons_form.get(entry["constructor_id"])
        model = entry.get("expected_points")
        if form is None or not isinstance(model, (int, float)):
            continue
        entry["expected_points_model"] = round(float(model), 1)
        entry["form_points"] = round(form, 1)
        _shift(entry, CONSTRUCTOR_SHIFT_FIELDS, (1.0 - weight) * (form - float(model)))
        n_c += 1
    payload["form_blend"] = {
        "applied": True, "phase": phase, "model_weight": weight,
        "half_life_rounds": tunables["half_life_rounds"], "history_rounds": past,
        "drivers_blended": n_d, "constructors_blended": n_c,
    }
    return payload["form_blend"]
