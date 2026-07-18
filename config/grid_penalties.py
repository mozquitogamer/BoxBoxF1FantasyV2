"""Pure helpers for applying known race-grid penalties."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np


def apply_grid_penalties(
    qualifying_positions: Sequence[int | float],
    driver_abbrevs: Sequence[str],
    penalties: Mapping[str, Mapping[str, object]],
) -> np.ndarray:
    """Return a unique starting grid after applying per-driver penalties.

    ``places`` moves a driver down from their supplied qualifying position.
    ``back_of_grid`` reserves the final available slot. Penalized slots are
    reserved first, then all other drivers fill the gaps in qualifying order.
    This mirrors the practical effect of multiple penalties: a +10 driver whose
    target is already occupied by a back-of-grid driver takes the nearest open
    slot ahead (for example STR P21 while HAD is fixed P22).
    """
    if len(qualifying_positions) != len(driver_abbrevs):
        raise ValueError("qualifying_positions and driver_abbrevs must have equal length")

    n_drivers = len(driver_abbrevs)
    if n_drivers == 0:
        return np.array([], dtype=int)

    positions = np.asarray(qualifying_positions, dtype=float)
    if not np.isfinite(positions).all():
        raise ValueError("qualifying_positions must all be finite")

    # Normalize any ties/gaps into a deterministic qualifying order.
    order = sorted(
        range(n_drivers),
        key=lambda i: (positions[i], i),
    )
    base_position = {idx: rank for rank, idx in enumerate(order, start=1)}
    abbrevs = [str(a).upper() for a in driver_abbrevs]
    normalized_rules = {str(k).upper(): v for k, v in penalties.items()}

    slots: list[int | None] = [None] * (n_drivers + 1)
    placed: set[int] = set()

    # Back-of-grid instructions have first claim on the final slots.
    back_indices = [
        idx for idx in order
        if bool(normalized_rules.get(abbrevs[idx], {}).get("back_of_grid", False))
    ]
    for idx in back_indices:
        slot = next(pos for pos in range(n_drivers, 0, -1) if slots[pos] is None)
        slots[slot] = idx
        placed.add(idx)

    # Process the deepest numeric penalties first. If the requested target is
    # occupied, use the closest open slot ahead. A driver can legitimately end
    # up ahead of their unpenalized position when another penalized driver has
    # already claimed the only slot behind them (for example a sampled STR P22
    # with HAD fixed at the back).
    numeric: list[tuple[int, int]] = []
    for idx in order:
        if idx in placed:
            continue
        rule = normalized_rules.get(abbrevs[idx], {})
        try:
            places = max(0, int(rule.get("places", 0)))
        except (TypeError, ValueError):
            places = 0
        if places:
            desired = min(n_drivers, base_position[idx] + places)
            numeric.append((desired, idx))

    for desired, idx in sorted(numeric, reverse=True):
        candidates = [pos for pos in range(desired, 0, -1) if slots[pos] is None]
        if not candidates:
            candidates = [pos for pos in range(desired + 1, n_drivers + 1) if slots[pos] is None]
        if not candidates:
            raise ValueError(f"No grid slot available for {abbrevs[idx]}")
        slots[candidates[0]] = idx
        placed.add(idx)

    # Everyone else advances into the unreserved slots without changing their
    # relative qualifying order.
    open_slots = [pos for pos in range(1, n_drivers + 1) if slots[pos] is None]
    unplaced = [idx for idx in order if idx not in placed]
    for slot, idx in zip(open_slots, unplaced):
        slots[slot] = idx

    output = np.empty(n_drivers, dtype=int)
    for slot in range(1, n_drivers + 1):
        idx = slots[slot]
        if idx is None:
            raise ValueError("Grid construction left an empty slot")
        output[idx] = slot
    return output
