"""Shared shrinkage rules for sparse driver-at-circuit history."""

from __future__ import annotations

import math


# Walk-forward checks on 1,709 experienced driver/circuit rows found that the
# raw circuit mean was substantially noisier than current five-race form. The
# empirical variance ratio was 12.8 prior-equivalent observations; 12 preserves
# a small circuit signal while remaining close to the held-out optimum.
DRIVER_CIRCUIT_PRIOR_STRENGTH = 12.0


def driver_circuit_reliability(
    appearances: float,
    prior_strength: float = DRIVER_CIRCUIT_PRIOR_STRENGTH,
) -> float:
    """Return the empirical-Bayes weight earned by circuit observations."""
    try:
        count = float(appearances)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(count) or count <= 0:
        return 0.0
    if prior_strength <= 0:
        return 1.0
    return count / (count + prior_strength)


def apply_driver_circuit_effect(
    recent_form: float,
    circuit_effect: float,
    appearances: float,
    prior_strength: float = DRIVER_CIRCUIT_PRIOR_STRENGTH,
) -> float:
    """Apply a shrunk historical circuit effect to current qualifying form.

    ``circuit_effect`` is the historical mean of ``quali_position -
    time_safe_roll5`` at this circuit. This models whether the circuit tended
    to move the driver away from their level *at the time*, rather than treating
    an old raw position as their current ability. With no history, the posterior
    is exactly current form.
    """
    try:
        baseline = float(recent_form)
    except (TypeError, ValueError):
        return math.nan
    if not math.isfinite(baseline):
        return math.nan

    try:
        effect = float(circuit_effect)
    except (TypeError, ValueError):
        return baseline
    if not math.isfinite(effect):
        return baseline

    weight = driver_circuit_reliability(appearances, prior_strength)
    return baseline + weight * effect
