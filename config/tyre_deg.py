"""
Shared tyre-degradation estimation — single source of truth for FP and race deg.

Both pipeline/10_fp_analysis.py (free-practice long runs, the Analysis tab) and
pipeline/11_race_deep_dive.py (race stints, the Deep Dive tab) estimate how fast
a tyre loses pace within a stint. They used to do it slightly differently and the
FP version was badly biased; this module gives them one correct method.

What "degradation" means here: seconds of lap-time lost per additional lap of
tyre age, after removing the confound of fuel burn (a car gets lighter and thus
faster over a stint, which masks tyre wear).

Why the old FP method was wrong (see the 2026-06-13 audit):
  - it regressed RAW lap time (no fuel correction) -> understated deg ~0.035 s/lap,
    routinely flipping the slope negative;
  - it used a one-sided "drop laps slower than 105% of the median" filter, which
    deletes exactly the degrading tail of the stint and keeps cool-down laps;
  - it regressed on np.arange() (lap index after filtering) instead of real tyre
    age, compressing gaps;
  - it merged stints across FP sessions (FastF1 restarts stint numbers each
    session) — fixed at the call sites by grouping on session too.
"""
from __future__ import annotations

import numpy as np

# Seconds of lap time gained per lap of fuel burned off. Shared so FP and race
# degradation are expressed on the same physical scale.
FUEL_EFFECT_PER_LAP: float = 0.035

# Laps slower than this multiple of the stint's best clean lap are treated as
# in/out/cool-down/traffic laps and dropped before fitting. 1.10 is deliberately
# loose: a real long-run degrading lap stays well under +10% of the best lap
# (that would be ~0.8 s/lap deg over 10 laps — beyond any realistic F1 deg), so
# this gate removes junk without clipping the genuine degrading tail.
JUNK_LAP_MULT: float = 1.10

# Minimum clean laps required for a trustworthy slope. Below this the stint is a
# quali sim / short run and we return None rather than a noisy number.
MIN_CLEAN_LAPS: int = 5


def stint_degradation(
    lap_times,
    tyre_age=None,
    fuel_effect: float = FUEL_EFFECT_PER_LAP,
    min_laps: int = MIN_CLEAN_LAPS,
    junk_mult: float = JUNK_LAP_MULT,
):
    """Robust degradation slope (s/lap) for a SINGLE stint.

    Returns (deg_rate, n_clean_laps). deg_rate is None when the stint can't be
    fit reliably (too few clean laps / too little tyre-age spread).

    Pipeline:
      1. Drop non-finite / non-positive laps.
      2. x-axis = tyre age (laps on this tyre). Falls back to 0..n-1 when age is
         not provided — but callers should always pass real tyre age.
      3. Junk gate: keep laps within `junk_mult` of the stint's best clean lap
         (removes in/out, cool-down and badly-slow traffic laps, two-sided in
         effect because a glitchy fast lap can't beat the best by much).
      4. Robust residual trim: fit once, drop laps > 3·(1.4826·MAD) off the line
         (removes subtler traffic laps that survived the gate) — degrading laps
         lie ON the line so they are kept.
      5. Fuel-correct (add fuel_effect·age back) and regress corrected time on
         true tyre age. Slope = tyre degradation.
    """
    t = np.asarray(lap_times, dtype=float)
    age = (np.arange(len(t), dtype=float) if tyre_age is None
           else np.asarray(tyre_age, dtype=float))

    m = np.isfinite(t) & np.isfinite(age) & (t > 0)
    t, age = t[m], age[m]
    if len(t) < min_laps:
        return None, int(len(t))

    order = np.argsort(age)
    t, age = t[order], age[order]

    # 3. Junk gate
    best = t.min()
    keep = t <= best * junk_mult
    t, age = t[keep], age[keep]
    if len(t) < min_laps or np.unique(age).size < 3:
        return None, int(len(t))

    corrected = t + fuel_effect * age

    # 4. Robust residual trim (one refit)
    slope, intercept = np.polyfit(age, corrected, 1)
    resid = corrected - (slope * age + intercept)
    mad = np.median(np.abs(resid - np.median(resid)))
    if mad > 1e-9:
        keep2 = np.abs(resid) <= 3.0 * 1.4826 * mad
        if keep2.sum() >= min_laps and np.unique(age[keep2]).size >= 3:
            age, corrected = age[keep2], corrected[keep2]
            slope = np.polyfit(age, corrected, 1)[0]

    return float(slope), int(len(age))


def compound_average(stint_results):
    """Lap-weighted mean deg across a compound's stints.

    `stint_results` is an iterable of (deg_rate, n_laps); None deg_rates are
    skipped. Returns (avg_deg or None, total_clean_laps, n_stints_used).
    Weighting by lap count stops a noisy 3-lap stint from outvoting a clean
    10-lap run.
    """
    num = 0.0
    den = 0
    used = 0
    for deg, n in stint_results:
        if deg is None or n is None or n <= 0:
            continue
        num += float(deg) * int(n)
        den += int(n)
        used += 1
    if den == 0:
        return None, 0, 0
    return num / den, den, used
