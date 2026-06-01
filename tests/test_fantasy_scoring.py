"""Unit tests for config/fantasy_scoring.py — the official 2026 scoring rules.

These functions are pure and deterministic, and EVERY prediction the site shows
flows through them. A silent bug here (wrong point value, sign flip, off-by-one
bracket) corrupts every driver/constructor score without crashing — exactly the
class of bug that's hard to catch by eye. Tests assert against the official
F1 Fantasy 2026 ruleset.

Run:  python -m pytest tests/test_fantasy_scoring.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import fantasy_scoring as fs


# ---------------------------------------------------------------------------
# Qualifying — drivers
# ---------------------------------------------------------------------------

class TestQualifyingDriver:
    def test_pole_is_10(self):
        assert fs.calc_qualifying_points_driver(1) == 10

    def test_p10_is_1(self):
        assert fs.calc_qualifying_points_driver(10) == 1

    def test_p11_is_0(self):
        assert fs.calc_qualifying_points_driver(11) == 0

    def test_p22_is_0(self):
        assert fs.calc_qualifying_points_driver(22) == 0

    def test_full_top10_ladder(self):
        # Official 2026: P1..P10 = 10,9,8,7,6,5,4,3,2,1
        expected = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        assert [fs.calc_qualifying_points_driver(p) for p in range(1, 11)] == expected

    def test_dsq_penalty(self):
        assert fs.calc_qualifying_points_driver(1, is_dsq=True) == fs.QUALIFYING_NC_DSQ_PENALTY

    def test_no_time_set_penalty(self):
        assert fs.calc_qualifying_points_driver(5, no_time_set=True) == fs.QUALIFYING_NC_DSQ_PENALTY

    def test_none_position_penalty(self):
        assert fs.calc_qualifying_points_driver(None) == fs.QUALIFYING_NC_DSQ_PENALTY


# ---------------------------------------------------------------------------
# Constructor qualifying bonus (best applicable tier only)
# ---------------------------------------------------------------------------

class TestConstructorQualiBonus:
    def test_both_q3(self):
        assert fs.calc_constructor_quali_bonus("Q3", "Q3") == 10

    def test_one_q3(self):
        assert fs.calc_constructor_quali_bonus("Q3", "Q2") == 5
        assert fs.calc_constructor_quali_bonus("Q1", "Q3") == 5

    def test_both_q2(self):
        assert fs.calc_constructor_quali_bonus("Q2", "Q2") == 3

    def test_one_q2(self):
        assert fs.calc_constructor_quali_bonus("Q2", "Q1") == 1

    def test_neither_q2_is_negative(self):
        assert fs.calc_constructor_quali_bonus("Q1", "Q1") == -1

    def test_best_tier_wins_not_additive(self):
        # One Q3 + one Q2 should be 5 (one_q3), NOT 5+3.
        assert fs.calc_constructor_quali_bonus("Q3", "Q2") == 5


# ---------------------------------------------------------------------------
# Race — drivers
# ---------------------------------------------------------------------------

class TestRaceDriver:
    def test_win_no_movement_is_25(self):
        # Win from pole, no positions gained, no extras = 25
        assert fs.calc_race_points_driver(finish_position=1, grid_position=1) == 25

    def test_full_top10_ladder(self):
        # Official 2026: 25,18,15,12,10,8,6,4,2,1 — finishing from that grid slot
        # (no movement) so only position points apply.
        expected = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
        got = [fs.calc_race_points_driver(finish_position=p, grid_position=p) for p in range(1, 11)]
        assert got == expected

    def test_positions_gained_adds_points(self):
        # P10 grid -> P3 finish: 15 (P3) + 7 gained = 22
        assert fs.calc_race_points_driver(finish_position=3, grid_position=10) == 22

    def test_positions_lost_subtracts(self):
        # P1 grid -> P5 finish: 10 (P5) - 4 lost = 6
        assert fs.calc_race_points_driver(finish_position=5, grid_position=1) == 6

    def test_overtakes_add_one_each(self):
        base = fs.calc_race_points_driver(finish_position=5, grid_position=5)
        with_ot = fs.calc_race_points_driver(finish_position=5, grid_position=5, overtakes=3)
        assert with_ot - base == 3

    def test_fastest_lap_adds_10(self):
        base = fs.calc_race_points_driver(finish_position=5, grid_position=5)
        fl = fs.calc_race_points_driver(finish_position=5, grid_position=5, is_fastest_lap=True)
        assert fl - base == 10

    def test_dotd_adds_10(self):
        base = fs.calc_race_points_driver(finish_position=5, grid_position=5)
        dotd = fs.calc_race_points_driver(finish_position=5, grid_position=5, is_driver_of_the_day=True)
        assert dotd - base == 10

    def test_dnf_is_minus_20(self):
        assert fs.calc_race_points_driver(finish_position=None, grid_position=1, is_dnf=True) == -20

    def test_dsq_is_minus_20(self):
        assert fs.calc_race_points_driver(finish_position=3, grid_position=5, is_dsq=True) == -20

    def test_pitlane_start_uses_pitlane_grid(self):
        # Starting from pitlane (grid treated as last), finishing P10 = big gain.
        pts = fs.calc_race_points_driver(
            finish_position=10, grid_position=20,
            started_from_pitlane=True, pitlane_grid_position=22,
        )
        # P10 = 1 pt + (22-10)=12 gained = 13
        assert pts == 13

    def test_stacked_win_with_extras(self):
        # Win from P3, +1 overtake, fastest lap, DOTD:
        # 25 + 2 gained + 1 OT + 10 FL + 10 DOTD = 48
        pts = fs.calc_race_points_driver(
            finish_position=1, grid_position=3, overtakes=1,
            is_fastest_lap=True, is_driver_of_the_day=True,
        )
        assert pts == 48


# ---------------------------------------------------------------------------
# Sprint — drivers
# ---------------------------------------------------------------------------

class TestSprintDriver:
    def test_win_is_8(self):
        assert fs.calc_sprint_points_driver(finish_position=1, grid_position=1) == 8

    def test_p8_is_1(self):
        assert fs.calc_sprint_points_driver(finish_position=8, grid_position=8) == 1

    def test_p9_is_0(self):
        assert fs.calc_sprint_points_driver(finish_position=9, grid_position=9) == 0

    def test_dnf_is_minus_10_in_2026(self):
        # 2026 rule change: sprint DNF penalty reduced from -20 to -10.
        assert fs.calc_sprint_points_driver(finish_position=None, grid_position=3, is_dnf=True) == -10

    def test_positions_gained(self):
        # P8 grid -> P4 finish: 5 (P4) + 4 gained = 9
        assert fs.calc_sprint_points_driver(finish_position=4, grid_position=8) == 9


# ---------------------------------------------------------------------------
# Pitstop scoring (constructors) — bracket boundaries are bug-prone
# ---------------------------------------------------------------------------

class TestPitstopPoints:
    def test_under_2s_is_20(self):
        assert fs.calc_pitstop_points_constructor([1.9]) == 20

    def test_exactly_2s_is_10_not_20(self):
        # Brackets are [lower, upper): 2.0 falls in the 2.0-2.2 = 10 bracket.
        assert fs.calc_pitstop_points_constructor([2.0]) == 10

    def test_2p3_is_5(self):
        assert fs.calc_pitstop_points_constructor([2.3]) == 5

    def test_2p7_is_2(self):
        assert fs.calc_pitstop_points_constructor([2.7]) == 2

    def test_over_3s_is_0(self):
        assert fs.calc_pitstop_points_constructor([3.5]) == 0

    def test_multiple_stops_sum(self):
        # 1.9 (20) + 2.1 (10) + 2.4 (5) = 35
        assert fs.calc_pitstop_points_constructor([1.9, 2.1, 2.4]) == 35

    def test_empty_is_0(self):
        assert fs.calc_pitstop_points_constructor([]) == 0

    def test_world_record_bonus(self):
        assert fs.calc_world_record_pitstop_bonus(1.79) == fs.PITSTOP_WORLD_RECORD_BONUS
        assert fs.calc_world_record_pitstop_bonus(1.81) == 0

    def test_fastest_pitstop_bonus(self):
        assert fs.calc_fastest_pitstop_bonus(True) == fs.FASTEST_PITSTOP_BONUS
        assert fs.calc_fastest_pitstop_bonus(False) == 0


# ---------------------------------------------------------------------------
# Constructor race points — DOTD must be EXCLUDED
# ---------------------------------------------------------------------------

class TestConstructorRacePoints:
    def test_dotd_excluded_from_constructor(self):
        # Driver1 scored 48 incl a 10-pt DOTD; constructor should NOT get the DOTD.
        # d1 = 48 (incl DOTD), d2 = 20, no pitstops.
        total = fs.calc_constructor_race_points(
            driver1_race_points=48, driver2_race_points=20,
            driver1_is_dotd=True, driver2_is_dotd=False,
            pitstop_times=[],
        )
        # (48-10) + 20 = 58
        assert total == 58

    def test_plain_sum_when_no_dotd(self):
        total = fs.calc_constructor_race_points(
            driver1_race_points=25, driver2_race_points=18,
            driver1_is_dotd=False, driver2_is_dotd=False,
            pitstop_times=[],
        )
        assert total == 43

    def test_pitstops_add_to_constructor(self):
        total = fs.calc_constructor_race_points(
            driver1_race_points=25, driver2_race_points=18,
            driver1_is_dotd=False, driver2_is_dotd=False,
            pitstop_times=[1.9],  # +20
        )
        assert total == 63

    def test_dsq_penalty_per_driver(self):
        total = fs.calc_constructor_race_points(
            driver1_race_points=25, driver2_race_points=18,
            driver1_is_dotd=False, driver2_is_dotd=False,
            pitstop_times=[], driver1_dsq=True,
        )
        assert total == 43 + fs.CONSTRUCTOR_RACE_DSQ_PENALTY


# ---------------------------------------------------------------------------
# Total weekend points
# ---------------------------------------------------------------------------

class TestTotal:
    def test_simple_sum(self):
        assert fs.calc_total_expected_fantasy_points(10, 25) == 35

    def test_sprint_weekend_sum(self):
        assert fs.calc_total_expected_fantasy_points(10, 25, sprint_quali_points=0, sprint_race_points=8) == 43


# ---------------------------------------------------------------------------
# Sanity: official rule constants haven't drifted
# ---------------------------------------------------------------------------

class TestRuleConstants:
    def test_race_win_is_25(self):
        assert fs.RACE_POSITION_POINTS[1] == 25

    def test_quali_pole_is_10(self):
        assert fs.QUALIFYING_POSITION_POINTS[1] == 10

    def test_race_dnf_penalty_is_minus_20(self):
        assert fs.RACE_DNF_DSQ_PENALTY == -20

    def test_sprint_dnf_is_minus_10_2026(self):
        assert fs.SPRINT_DNF_DSQ_PENALTY == -10

    def test_extra_transfer_penalty_is_minus_10(self):
        assert fs.EXTRA_TRANSFER_PENALTY == -10
