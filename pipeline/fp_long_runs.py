"""Shared, session-safe free-practice long-run extraction.

FastF1 restarts stint numbers in every practice session. Any feature that
groups a whole weekend by ``stint_number`` alone can therefore merge unrelated
FP1/FP2/FP3 runs (and even different compounds) into a fabricated long run.
This module is the single source of truth used by both the ML feature extractor
and the website's FP analysis.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from config.tyre_deg import representative_stint_laps


RACE_COMPOUNDS = frozenset({"MEDIUM", "HARD", "INTERMEDIATE", "WET"})
LONG_RUN_MIN_RAW = 5
LONG_RUN_MIN_CLEAN = 4
SESSION_PRIORITY = {"FP2": 3, "FP1": 2, "FP3": 1}
FP_STINT_SEMANTICS_VERSION = 2

_COMPOUND_ALIASES = {
    "M": "MEDIUM",
    "H": "HARD",
    "I": "INTERMEDIATE",
    "W": "WET",
    "S": "SOFT",
}


def _compound_name(value: object) -> str:
    name = str(value).strip().upper()
    return _COMPOUND_ALIASES.get(name, name)


def require_fp_stint_semantics(
    df: pd.DataFrame,
    *,
    source: object,
) -> None:
    """Reject an unstamped or stale FP feature parquet.

    A model trained with one stint definition must never consume features made
    with another. The version is stored as a metadata column in feature
    parquets, then deliberately dropped before model-feature selection.
    """
    version_col = "fp_stint_semantics_version"
    values = (
        pd.to_numeric(df[version_col], errors="coerce")
        if version_col in df.columns else pd.Series(dtype=float)
    )
    versions = set(values.dropna().astype(int))
    complete = len(values) == len(df) and not values.isna().any()
    if not complete or versions != {FP_STINT_SEMANTICS_VERSION}:
        found = sorted(versions) if versions else "unstamped legacy data"
        raise RuntimeError(
            f"FP feature semantics mismatch in {source}: found {found}, expected "
            f"v{FP_STINT_SEMANTICS_VERSION}. Re-extract FP features before use."
        )


def stint_group_columns(df: pd.DataFrame, stint_col: str = "stint_number") -> list[str]:
    """Return the safest available keys for one physical tyre stint."""
    keys = []
    if "session" in df.columns:
        keys.append("session")
    keys.append(stint_col)
    if "compound" in df.columns:
        keys.append("compound")
    return keys


def extract_representative_long_runs(
    group: pd.DataFrame,
    *,
    min_raw: int = LONG_RUN_MIN_RAW,
    min_clean: int = LONG_RUN_MIN_CLEAN,
    stint_col: str = "stint_number",
) -> list[dict]:
    """Return clean race-compound runs from one driver's FP laps.

    Each candidate is isolated by session, stint number and compound; must have
    ``min_raw`` valid laps; and is trimmed with the shared robust tyre-life-aware
    selector. Kept/excluded laps remain in chronological order so downstream
    fuel and degradation calculations can reuse the exact same evidence.
    """
    required = {"lap_time", stint_col}
    if group is None or group.empty or not required.issubset(group.columns):
        return []

    clean = group.copy()
    clean["lap_time"] = pd.to_numeric(clean["lap_time"], errors="coerce")
    clean = clean[np.isfinite(clean["lap_time"]) & (clean["lap_time"] > 0)]
    if clean.empty:
        return []

    keys = stint_group_columns(clean, stint_col)
    runs: list[dict] = []
    for key_values, stint_df in clean.groupby(keys, dropna=False, sort=False):
        key_values = key_values if isinstance(key_values, tuple) else (key_values,)
        meta = dict(zip(keys, key_values))
        compound = _compound_name(meta.get("compound", "UNKNOWN"))
        # Modern FastF1 data always carries compound. If a legacy frame lacks
        # it, retain the run rather than deleting all historical coverage.
        if "compound" in clean.columns and compound not in RACE_COMPOUNDS:
            continue

        if "lap_number" in stint_df.columns:
            stint_df = stint_df.sort_values("lap_number")
        if len(stint_df) < min_raw:
            continue

        times = stint_df["lap_time"].to_numpy(dtype=float)
        tyre_age = None
        if "tyre_life" in stint_df.columns:
            candidate_age = pd.to_numeric(
                stint_df["tyre_life"], errors="coerce"
            ).to_numpy(dtype=float)
            if np.isfinite(candidate_age).sum() >= min_clean:
                tyre_age = candidate_age
        if tyre_age is None and "lap_number" in stint_df.columns:
            laps = pd.to_numeric(
                stint_df["lap_number"], errors="coerce"
            ).to_numpy(dtype=float)
            if np.isfinite(laps).sum() >= min_clean:
                tyre_age = laps - np.nanmin(laps)

        mask = representative_stint_laps(
            times,
            tyre_age,
            min_clean=min_clean,
        )
        if int(mask.sum()) < min_clean:
            continue

        kept = times[mask]
        if tyre_age is None:
            kept_age = np.arange(len(times), dtype=float)[mask]
        else:
            kept_age = tyre_age[mask]
        excluded = times[~mask]
        session = str(meta.get("session", "?")).upper()
        stint_value = meta.get(stint_col)
        try:
            stint_value = int(stint_value)
        except (TypeError, ValueError):
            stint_value = str(stint_value)

        runs.append({
            "session": session,
            "stint": stint_value,
            "compound": compound,
            "laps": int(mask.sum()),
            "avg_pace": float(np.mean(kept)),
            "best_pace": float(np.min(kept)),
            "consistency": float(np.std(kept)),
            "kept_laps": kept.tolist(),
            "kept_tyre_age": kept_age.tolist(),
            "excluded_laps": excluded.tolist(),
        })

    return runs


def select_headline_long_run(
    runs: Iterable[dict],
    *,
    compound: str | None = None,
) -> dict | None:
    """Select a comparable headline session and lap-weight its clean runs.

    FP2 is the normal-weekend high-fuel session, FP1 is next (and the only
    practice on sprint weekends), while FP3 is mostly qualifying preparation.
    Runs from different sessions are never averaged together.
    """
    selected = list(runs)
    if compound is not None:
        wanted = _compound_name(compound)
        selected = [r for r in selected if r.get("compound") == wanted]
    if not selected:
        return None

    by_session: dict[str, list[dict]] = {}
    for run in selected:
        by_session.setdefault(str(run.get("session", "?")).upper(), []).append(run)

    headline_session = max(
        by_session,
        key=lambda session: (
            SESSION_PRIORITY.get(session, 0),
            sum(int(r["laps"]) for r in by_session[session]),
        ),
    )
    headline_runs = by_session[headline_session]
    kept_laps = [
        float(lap)
        for run in headline_runs
        for lap in run.get("kept_laps", [])
    ]
    if not kept_laps:
        return None

    return {
        "session": headline_session,
        "runs": headline_runs,
        "avg_pace": float(np.mean(kept_laps)),
        "laps": len(kept_laps),
        "total_long_run_laps": sum(int(r["laps"]) for r in selected),
    }
