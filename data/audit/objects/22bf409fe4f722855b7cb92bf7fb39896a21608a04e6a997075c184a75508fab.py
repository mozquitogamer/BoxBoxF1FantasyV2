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

    Numeric drops use temporary positions per FIA Article B2.5.4b. The
    lower qualifier keeps the slot on a tie. Unpenalized drivers fill the
    gaps in qualifying order, then empty slots are closed up.
    ``back_of_grid`` drivers go behind that group in qualifying order unless
    ``back_of_grid_order`` explicitly sets their relative order (lower first).
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

    back_indices = [
        idx for idx in order
        if bool(normalized_rules.get(abbrevs[idx], {}).get("back_of_grid", False))
    ]
    # An explicit forecast assumption can fix the relative back-row order even
    # when a simulated qualifying result reverses those drivers.
    back_indices.sort(key=lambda idx: (
        int(normalized_rules.get(abbrevs[idx], {}).get("back_of_grid_order", 0))
        or n_drivers + 1,
        base_position[idx],
    ))
    placed = set(back_indices)
    numeric: list[tuple[int, int, int]] = []
    for idx in order:
        if idx in placed:
            continue
        rule = normalized_rules.get(abbrevs[idx], {})
        try:
            places = max(0, int(rule.get("places", 0)))
        except (TypeError, ValueError):
            places = 0
        if places:
            rank = base_position[idx]
            numeric.append((rank + places, rank, idx))
            placed.add(idx)

    slots: dict[int, int] = {}
    for slot, _, idx in sorted(numeric, reverse=True):
        while slot in slots:
            slot -= 1
        slots[slot] = idx

    open_slots = (pos for pos in range(1, n_drivers + 1) if pos not in slots)
    unplaced = [idx for idx in order if idx not in placed]
    for slot, idx in zip(open_slots, unplaced):
        slots[slot] = idx

    grid_order = [idx for _, idx in sorted(slots.items())] + back_indices
    output = np.empty(n_drivers, dtype=int)
    for slot, idx in enumerate(grid_order, start=1):
        output[idx] = slot
    return output
