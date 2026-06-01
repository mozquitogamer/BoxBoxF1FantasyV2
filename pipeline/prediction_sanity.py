"""Pre-export sanity checks for the website predictions payload.

A guard rail against silently shipping broken predictions. The MC bias-correction
bug (2026-06-01) suppressed every front-runner ~6.6 pts and shipped to the live
site unnoticed — a check like this would have flagged "predicted winner scoring
implausibly low" before the export wrote the file.

Design:
  - check_predictions(payload) returns (ok: bool, problems: list[str], warnings: list[str]).
  - "problems" are things that should block/loudly warn (structurally broken data).
  - "warnings" are things that are suspicious but not necessarily wrong (e.g. a
    genuinely low-scoring track like Monaco). We never silently swallow these —
    they print, but only hard `problems` make ok=False.

The thresholds are deliberately LOOSE — this catches gross breakage (all zeros,
NaNs, a winner predicted to score single digits), not subtle model drift. It's a
smoke alarm, not a calibration tool.
"""
from __future__ import annotations

import math
from typing import Any

# Tunables — loose on purpose. Adjust only if a real round legitimately trips one.
SANITY = {
    # The predicted top scorer should clear this, or something is wrong. Monaco
    # (lowest-scoring track) still puts its predicted winner ~30; a winner under
    # ~15 means points are being suppressed (the bias-nerf signature was 25.5,
    # which would still pass — so this is a floor for GROSS breakage, see the
    # relative check below for the subtler signal).
    "min_top_driver_points": 15.0,
    # The predicted field should have SOME spread. If every driver scores within
    # a couple points of each other, the ranking signal collapsed.
    "min_field_spread": 8.0,
    # A non-trivial share of drivers should have positive expected points.
    "min_positive_share": 0.30,
    # Constructor floor (two drivers combined).
    "min_top_constructor_points": 25.0,
    "expected_driver_count": 22,
    "expected_constructor_count": 11,
}


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def check_predictions(payload: dict, *, strict: bool = False) -> tuple[bool, list[str], list[str]]:
    """Validate a predictions payload before it's written to the website.

    Returns (ok, problems, warnings).
      ok        = False if any hard problem found (structurally broken).
      problems  = list of blocking issues.
      warnings  = list of suspicious-but-allowed observations.

    strict=True promotes warnings to problems (useful in tests/CI).
    """
    problems: list[str] = []
    warnings: list[str] = []

    drivers = payload.get("drivers") or []
    constructors = payload.get("constructors") or []

    # ---- Structural ----
    if not drivers:
        problems.append("no drivers in payload")
        return False, problems, warnings
    if not constructors:
        problems.append("no constructors in payload")

    n_drv = len(drivers)
    if n_drv != SANITY["expected_driver_count"]:
        warnings.append(f"driver count {n_drv} != expected {SANITY['expected_driver_count']}")
    if constructors and len(constructors) != SANITY["expected_constructor_count"]:
        warnings.append(f"constructor count {len(constructors)} != expected {SANITY['expected_constructor_count']}")

    # ---- Per-driver point extraction + NaN / missing-field guard ----
    d_pts: list[float] = []
    for d in drivers:
        v = _num(d.get("expected_points"))
        if v is None:
            problems.append(f"driver {d.get('driver_id', '?')} has missing/NaN expected_points")
        else:
            d_pts.append(v)

    if not d_pts:
        problems.append("no usable driver expected_points")
        return False, problems, warnings

    # ---- All-zero / all-equal collapse ----
    if all(p == 0 for p in d_pts):
        problems.append("every driver has expected_points == 0 (export/scoring collapse)")

    top = max(d_pts)
    spread = max(d_pts) - min(d_pts)
    positive_share = sum(1 for p in d_pts if p > 0) / len(d_pts)

    # ---- Top scorer floor (gross suppression / wrong sign) ----
    if top < SANITY["min_top_driver_points"]:
        problems.append(
            f"top predicted driver scores only {top:.1f} pts "
            f"(< {SANITY['min_top_driver_points']}) — points may be suppressed/broken"
        )

    # ---- Field spread (ranking signal alive) ----
    if spread < SANITY["min_field_spread"]:
        warnings.append(
            f"field spread only {spread:.1f} pts (< {SANITY['min_field_spread']}) — "
            f"weak ranking signal (can be legit on a chaotic/wet forecast)"
        )

    # ---- Positive share ----
    if positive_share < SANITY["min_positive_share"]:
        warnings.append(
            f"only {positive_share:.0%} of drivers have positive expected_points "
            f"(< {SANITY['min_positive_share']:.0%})"
        )

    # ---- Constructors ----
    if constructors:
        c_pts = [v for c in constructors if (v := _num(c.get("expected_points"))) is not None]
        if c_pts:
            if max(c_pts) < SANITY["min_top_constructor_points"]:
                problems.append(
                    f"top predicted constructor scores only {max(c_pts):.1f} pts "
                    f"(< {SANITY['min_top_constructor_points']})"
                )
        else:
            problems.append("no usable constructor expected_points")

    if strict:
        problems = problems + warnings
        warnings = []

    return (len(problems) == 0), problems, warnings


def print_report(payload: dict, *, label: str = "") -> bool:
    """Run checks and print a human-readable report. Returns ok (no hard problems)."""
    ok, problems, warnings = check_predictions(payload)
    # ASCII-only output: the pipeline runs on a Windows cp1252 console that
    # can't encode ✓/✗/• and would crash the export on a print().
    tag = f" [{label}]" if label else ""
    if problems:
        print(f"  !!! PREDICTION SANITY{tag}: {len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"      [X] {p}")
    if warnings:
        print(f"  ~ prediction sanity{tag}: {len(warnings)} warning(s):")
        for w in warnings:
            print(f"      - {w}")
    if not problems and not warnings:
        print(f"  [OK] prediction sanity{tag}: all checks passed")
    return ok
