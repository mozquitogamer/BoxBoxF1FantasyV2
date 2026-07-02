"""
BoxBoxF1Fantasy — Official F1 Fantasy 2026 scoring rules.

All point values are based on the official F1 Fantasy 2026 ruleset.
Key 2026 change: Sprint DNF/DSQ penalty reduced to -10 (was -20 previously).
"""

from typing import Optional


# ==============================================================================
# QUALIFYING — Drivers
# ==============================================================================

QUALIFYING_POSITION_POINTS: dict[int, int] = {
    1: 10,   # Pole
    2: 9,
    3: 8,
    4: 7,
    5: 6,
    6: 5,
    7: 4,
    8: 3,
    9: 2,
    10: 1,
    # P11–P22: 0 points (handled by .get() default)
}

QUALIFYING_NC_DSQ_PENALTY: int = -5  # No time set / DSQ / inactive


# ==============================================================================
# QUALIFYING — Constructors
# ==============================================================================
# Constructors get the combined total of both drivers' qualifying points,
# PLUS one of the following bonuses (best applicable tier only):

CONSTRUCTOR_QUALI_BONUSES: dict[str, int] = {
    "both_q3":       10,
    "one_q3":         5,
    "both_q2":        3,
    "one_q2":         1,
    "neither_q2":    -1,
}

CONSTRUCTOR_QUALI_DSQ_PENALTY: int = -5  # per driver


# ==============================================================================
# SPRINT — Drivers
# ==============================================================================

SPRINT_POSITION_POINTS: dict[int, int] = {
    1: 8,
    2: 7,
    3: 6,
    4: 5,
    5: 4,
    6: 3,
    7: 2,
    8: 1,
    # P9–P22: 0 points
}

SPRINT_POSITIONS_GAINED_PER_POS: int = 1     # +1 per position gained
SPRINT_POSITIONS_LOST_PER_POS: int = -1       # -1 per position lost
SPRINT_OVERTAKE_POINTS: int = 1               # +1 per overtake
SPRINT_FASTEST_LAP_BONUS: int = 5
SPRINT_DNF_DSQ_PENALTY: int = -10             # 2026 change (was -20)

# ==============================================================================
# SPRINT — Constructors
# ==============================================================================
# Combined total of both drivers' sprint points.

CONSTRUCTOR_SPRINT_DSQ_PENALTY: int = -10  # per driver


# ==============================================================================
# RACE — Drivers
# ==============================================================================

RACE_POSITION_POINTS: dict[int, int] = {
    1: 25,
    2: 18,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1,
    # P11–P22: 0 points
}

RACE_POSITIONS_GAINED_PER_POS: int = 1       # +1 per position gained
RACE_POSITIONS_LOST_PER_POS: int = -1         # -1 per position lost
RACE_OVERTAKE_POINTS: int = 1                 # +1 per overtake
RACE_FASTEST_LAP_BONUS: int = 10
RACE_DRIVER_OF_THE_DAY_BONUS: int = 10        # Driver only, NOT constructors
RACE_DNF_DSQ_PENALTY: int = -20
# Expected-value softener for DNFs in PROJECTIONS (not actuals). A predicted DNF
# probability includes some late/partial retirements, so projections apply 60%
# of the full -20 as the expected penalty. Used by BOTH the deterministic scorer
# (07_calculate_fantasy) and the Monte Carlo (08) so the two stay consistent.
DNF_EXPECTED_PENALTY_FACTOR: float = 0.6

# Retired drivers keep overtake points for passes made before retiring. Fitted
# from the 32 true-DNF driver-rounds in 2026 R1-R10 (corrected actuals): overtake
# count mean 3.6, std 3.2 (range 0-16, right-skewed). Used by 07 (deterministic
# DNF expected value) and 08 (per-sim retiree overtake credit), so both include
# the ~+3.6 pts a retiree earns on top of the -20 penalty. Re-fit after each race.
RETIREE_OT_MEAN: float = 3.6
RETIREE_OT_STD: float = 3.0

# ==============================================================================
# RACE — Constructors
# ==============================================================================
# Combined total of both drivers' race points (EXCLUDING Driver of the Day).

CONSTRUCTOR_RACE_DSQ_PENALTY: int = -20  # per driver

# Pitstop time bonuses (constructors only)
PITSTOP_TIME_POINTS: list[tuple[float, float, int]] = [
    (0.0,   2.0,  20),   # Under 2.0s
    (2.0,   2.2,  10),   # 2.00 – 2.19s
    (2.2,   2.5,   5),   # 2.20 – 2.49s
    (2.5,   3.0,   2),   # 2.50 – 2.99s
    (3.0, 999.0,   0),   # Over 3.0s
]

FASTEST_PITSTOP_BONUS: int = 10  # overall-fastest stop of the race (2026: +10,
                                 # confirmed vs official — racing_bulls Austria
                                 # R10 = 5 bracket + 10 fastest = 15)
PITSTOP_WORLD_RECORD_BONUS: int = 15
PITSTOP_WORLD_RECORD_TIME: float = 1.80  # Current record: McLaren, Qatar 2023


# ==============================================================================
# TEAM MANAGEMENT
# ==============================================================================

EXTRA_TRANSFER_PENALTY: int = -10  # per additional transfer beyond free allowance


# ==============================================================================
# CALCULATION FUNCTIONS
# ==============================================================================

def calc_qualifying_points_driver(
    position: Optional[int],
    is_dsq: bool = False,
    no_time_set: bool = False,
) -> int:
    """Calculate qualifying fantasy points for a driver."""
    if is_dsq or no_time_set or position is None:
        return QUALIFYING_NC_DSQ_PENALTY
    return QUALIFYING_POSITION_POINTS.get(position, 0)


def calc_constructor_quali_bonus(
    driver1_best_session: str,
    driver2_best_session: str,
) -> int:
    """
    Calculate the constructor qualifying bonus.

    Args:
        driver1_best_session: Best qualifying session reached ("Q1", "Q2", or "Q3")
        driver2_best_session: Best qualifying session reached ("Q1", "Q2", or "Q3")

    Returns:
        Bonus points (only the best applicable tier).
    """
    sessions = [driver1_best_session, driver2_best_session]
    q3_count = sessions.count("Q3")
    q2_count = sessions.count("Q2")

    if q3_count == 2:
        return CONSTRUCTOR_QUALI_BONUSES["both_q3"]
    elif q3_count == 1:
        return CONSTRUCTOR_QUALI_BONUSES["one_q3"]
    elif q2_count + q3_count == 2:
        return CONSTRUCTOR_QUALI_BONUSES["both_q2"]
    elif q2_count + q3_count == 1:
        return CONSTRUCTOR_QUALI_BONUSES["one_q2"]
    else:
        return CONSTRUCTOR_QUALI_BONUSES["neither_q2"]


def calc_sprint_points_driver(
    finish_position: Optional[int],
    grid_position: int,
    overtakes: int = 0,
    is_fastest_lap: bool = False,
    is_dnf: bool = False,
    is_dsq: bool = False,
) -> int:
    """Calculate sprint fantasy points for a driver."""
    if is_dnf or is_dsq or finish_position is None:
        return SPRINT_DNF_DSQ_PENALTY

    points = SPRINT_POSITION_POINTS.get(finish_position, 0)

    # Positions gained/lost (based on grid -> finish)
    pos_change = grid_position - finish_position
    if pos_change > 0:
        points += pos_change * SPRINT_POSITIONS_GAINED_PER_POS
    elif pos_change < 0:
        points += pos_change  # negative already

    # Overtakes
    points += overtakes * SPRINT_OVERTAKE_POINTS

    # Fastest lap
    if is_fastest_lap:
        points += SPRINT_FASTEST_LAP_BONUS

    return points


def calc_race_points_driver(
    finish_position: Optional[int],
    grid_position: int,
    overtakes: int = 0,
    is_fastest_lap: bool = False,
    is_driver_of_the_day: bool = False,
    is_dnf: bool = False,
    is_dsq: bool = False,
    started_from_pitlane: bool = False,
    pitlane_grid_position: Optional[int] = None,
) -> int:
    """
    Calculate race fantasy points for a driver.

    For pitlane starters, grid_position should be set to the last position on the grid
    (or pitlane_grid_position if provided).
    """
    if is_dnf or is_dsq or finish_position is None:
        return RACE_DNF_DSQ_PENALTY

    points = RACE_POSITION_POINTS.get(finish_position, 0)

    # Positions gained/lost (grid start -> race finish)
    effective_grid = pitlane_grid_position if started_from_pitlane and pitlane_grid_position else grid_position
    pos_change = effective_grid - finish_position
    if pos_change > 0:
        points += pos_change * RACE_POSITIONS_GAINED_PER_POS
    elif pos_change < 0:
        points += pos_change  # negative

    # Overtakes
    points += overtakes * RACE_OVERTAKE_POINTS

    # Fastest lap
    if is_fastest_lap:
        points += RACE_FASTEST_LAP_BONUS

    # Driver of the Day
    if is_driver_of_the_day:
        points += RACE_DRIVER_OF_THE_DAY_BONUS

    return points


def calc_pitstop_points_constructor(pitstop_times: list[float]) -> int:
    """
    Calculate constructor pitstop fantasy points.

    Args:
        pitstop_times: List of pitstop durations in seconds for the team.

    Returns:
        Total pitstop points (time-based + fastest bonus + world record bonus).
    """
    if not pitstop_times:
        return 0

    total = 0
    for t in pitstop_times:
        for lower, upper, pts in PITSTOP_TIME_POINTS:
            if lower <= t < upper:
                total += pts
                break

    return total


def calc_fastest_pitstop_bonus(is_fastest: bool) -> int:
    """Fastest pitstop of the race bonus (constructor)."""
    return FASTEST_PITSTOP_BONUS if is_fastest else 0


def calc_world_record_pitstop_bonus(best_time: float) -> int:
    """World record pitstop bonus (constructor)."""
    return PITSTOP_WORLD_RECORD_BONUS if best_time < PITSTOP_WORLD_RECORD_TIME else 0


def calc_constructor_race_points(
    driver1_race_points: int,
    driver2_race_points: int,
    driver1_is_dotd: bool,
    driver2_is_dotd: bool,
    pitstop_times: list[float],
    is_fastest_pitstop: bool = False,
    best_pitstop_time: float = 999.0,
    driver1_dsq: bool = False,
    driver2_dsq: bool = False,
) -> int:
    """
    Calculate total constructor race fantasy points.

    Excludes Driver of the Day bonus from constructor total.
    """
    # Remove DOTD from driver points for constructor calculation
    d1_pts = driver1_race_points - (RACE_DRIVER_OF_THE_DAY_BONUS if driver1_is_dotd else 0)
    d2_pts = driver2_race_points - (RACE_DRIVER_OF_THE_DAY_BONUS if driver2_is_dotd else 0)

    total = d1_pts + d2_pts

    # Pitstop points
    total += calc_pitstop_points_constructor(pitstop_times)
    total += calc_fastest_pitstop_bonus(is_fastest_pitstop)
    total += calc_world_record_pitstop_bonus(best_pitstop_time)

    # DSQ penalties
    if driver1_dsq:
        total += CONSTRUCTOR_RACE_DSQ_PENALTY
    if driver2_dsq:
        total += CONSTRUCTOR_RACE_DSQ_PENALTY

    return total


def calc_total_expected_fantasy_points(
    quali_points: int,
    race_points: int,
    sprint_quali_points: int = 0,
    sprint_race_points: int = 0,
) -> int:
    """Calculate total expected fantasy points for a weekend."""
    return quali_points + race_points + sprint_quali_points + sprint_race_points
