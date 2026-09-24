"""Practice-only pace comparisons for the Analysis tab.

The ranking models retain their versioned FP features. This module evaluates
race-run evidence for readers without silently changing trained feature
semantics. A stint with alternating push and cool laps is not a continuous
race simulation, even when four of its laps pass the normal pace filter.
"""

from __future__ import annotations

from itertools import groupby

import numpy as np
import pandas as pd

from config.tyre_deg import representative_stint_laps
from pipeline.fp_long_runs import SESSION_PRIORITY


WARMUP_GAP_SECONDS = 1.5


def _longest_selected_streak(mask: np.ndarray) -> int:
    return max((sum(1 for _ in laps) for selected, laps in groupby(mask) if selected), default=0)


def _practice_run(stint: pd.DataFrame, session: str, compound: str, stint_id: object) -> dict | None:
    ordered = stint.sort_values("lap_number") if "lap_number" in stint else stint
    ordered = ordered.copy()
    ordered["lap_time"] = pd.to_numeric(ordered["lap_time"], errors="coerce")
    ordered = ordered[np.isfinite(ordered["lap_time"]) & (ordered["lap_time"] > 0)]
    if len(ordered) < 3:
        return None

    times = ordered["lap_time"].to_numpy(dtype=float)
    age = None
    if "tyre_life" in ordered:
        proposed = pd.to_numeric(ordered["tyre_life"], errors="coerce").to_numpy(dtype=float)
        if np.isfinite(proposed).all():
            age = proposed
    if age is None:
        age = np.arange(len(ordered), dtype=float)

    mask = representative_stint_laps(times, age, min_clean=3)
    if int(mask.sum()) < 3:
        return None

    # A single slow opening flyer can move a short stint by a full second.
    # Remove it only with four other selected laps as independent evidence.
    selected = np.flatnonzero(mask)
    if (len(selected) >= 5
            and times[selected[0]] > np.median(times[selected[1:4]]) + WARMUP_GAP_SECONDS):
        mask[selected[0]] = False
        selected = np.flatnonzero(mask)

    internal_interruptions = int((~mask[selected[0]:selected[-1] + 1]).sum())
    longest_streak = _longest_selected_streak(mask)
    if len(ordered) < 4:
        quality = "short"
    elif (len(ordered) >= 5 and len(selected) >= 4
          and internal_interruptions <= 1 and longest_streak >= 3):
        quality = "clean"
    elif (longest_streak >= 3
          or (len(selected) >= 4 and internal_interruptions <= 2 and longest_streak >= 2)):
        quality = "partial"
    else:
        quality = "interrupted"

    lap_numbers = (
        pd.to_numeric(ordered["lap_number"], errors="coerce").to_numpy(dtype=float)
        if "lap_number" in ordered else np.arange(1, len(ordered) + 1, dtype=float)
    )
    sequence = [
        {
            "lap_number": int(number) if np.isfinite(number) else None,
            "time": round(float(time), 3),
            "selected": bool(use),
        }
        for number, time, use in zip(lap_numbers, times, mask)
    ]
    selected_times = times[mask]
    try:
        stint_id = int(stint_id)
    except (TypeError, ValueError):
        stint_id = str(stint_id)
    return {
        "session": session,
        "stint": stint_id,
        "compound": compound,
        "quality": quality,
        "laps": int(len(selected_times)),
        "median_pace": round(float(np.median(selected_times)), 3),
        "avg_pace": round(float(np.mean(selected_times)), 3),
        "interruptions": internal_interruptions,
        "lap_sequence": sequence,
    }


def analyze_comparable_long_runs(laps: pd.DataFrame) -> dict:
    """Return run evidence and session-wide comparison groups.

    Run classification depends on its sustained lap pattern, not its tyre.
    Tyre stays attached to every run so raw pace is not mistaken for an
    equal-compound gap. Interrupted push/cool patterns remain visible in detail.
    """
    if laps is None or laps.empty or not {"driver_id", "lap_time"}.issubset(laps):
        return {"default_group": None, "groups": [], "drivers": {}}

    work = laps.copy()
    if "stint" not in work and "stint_number" in work:
        work = work.rename(columns={"stint_number": "stint"})
    for column, default in (("session", "?"), ("stint", 1), ("compound", "UNKNOWN")):
        if column not in work:
            work[column] = default
    work["session"] = work["session"].fillna("?").astype(str).str.upper()
    work["compound"] = work["compound"].fillna("UNKNOWN").astype(str).str.upper()
    # Sprint Qualifying laps are useful for the one-lap indicator but are not
    # race runs, even if a long timed sequence happens to share a stint ID.
    work = work[work["session"].isin({"FP1", "FP2", "FP3"})]

    drivers: dict[str, dict] = {}
    for (driver, session, stint_id, compound), stint in work.groupby(
        ["driver_id", "session", "stint", "compound"], dropna=False, sort=False
    ):
        run = _practice_run(stint, session, compound, stint_id)
        if run is not None:
            drivers.setdefault(str(driver), {"runs": []})["runs"].append(run)

    grouped: dict[str, dict] = {}
    for driver, record in drivers.items():
        for run in record["runs"]:
            if run["quality"] not in {"clean", "partial"}:
                continue
            key = run["session"]
            entry = grouped.setdefault(key, {
                "id": key,
                "session": run["session"],
                "drivers": set(),
                "clean_drivers": set(),
                "partial_drivers": set(),
                "compounds": set(),
            })
            entry["drivers"].add(driver)
            entry[f'{run["quality"]}_drivers'].add(driver)
            entry["compounds"].add(run["compound"])

    groups = []
    for entry in grouped.values():
        if len(entry["drivers"]) < 2:
            continue
        groups.append({
            **entry,
            "drivers": len(entry["drivers"]),
            "clean_drivers": len(entry["clean_drivers"]),
            "partial_drivers": len(entry["partial_drivers"]),
            "compounds": sorted(entry["compounds"]),
        })
    groups.sort(key=lambda group: (
        group["drivers"], group["clean_drivers"],
        SESSION_PRIORITY.get(group["session"], 0)
    ), reverse=True)
    preferred_fp2 = next((group for group in groups
                          if group["session"] == "FP2" and group["drivers"] >= 5), None)
    return {
        "default_group": (preferred_fp2 or groups[0])["id"] if groups else None,
        "groups": groups,
        "drivers": drivers,
        "method": "same-session-all-compounds-per-run-median-v2",
    }
