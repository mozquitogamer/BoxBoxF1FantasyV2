"""Tests for the pre-export prediction sanity guard.

Confirms the guard catches the breakage classes it's meant to — most importantly
the gross-suppression signature that the MC bias-nerf would have triggered, plus
all-zeros, NaNs, and ranking collapse. Also confirms a healthy payload passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.prediction_sanity import check_predictions, SANITY


def _healthy_payload(n=22):
    # Realistic-ish spread: top ~32, tail negative — mirrors a normal race export.
    pts = [32, 29, 27, 24, 17, 16, 15, 12, 10, 8, 7, 6, 5, 3, 2, 1, 0, -2, -3, -5, -8, -10][:n]
    drivers = [{"driver_id": f"d{i}", "expected_points": p} for i, p in enumerate(pts)]
    constructors = [{"constructor_id": f"c{i}", "expected_points": 78 - i * 6} for i in range(11)]
    return {"drivers": drivers, "constructors": constructors}


class TestHealthyPasses:
    def test_normal_payload_ok(self):
        ok, problems, warnings = check_predictions(_healthy_payload())
        assert ok, f"healthy payload flagged: {problems}"
        assert problems == []


class TestCatchesBreakage:
    def test_empty_drivers_blocks(self):
        ok, problems, _ = check_predictions({"drivers": [], "constructors": []})
        assert not ok
        assert any("no drivers" in p for p in problems)

    def test_all_zero_blocks(self):
        p = _healthy_payload()
        for d in p["drivers"]:
            d["expected_points"] = 0
        ok, problems, _ = check_predictions(p)
        assert not ok
        assert any("== 0" in pr or "only" in pr for pr in problems)

    def test_nan_expected_points_blocks(self):
        p = _healthy_payload()
        p["drivers"][0]["expected_points"] = float("nan")
        ok, problems, _ = check_predictions(p)
        assert not ok
        assert any("NaN" in pr for pr in problems)

    def test_missing_field_blocks(self):
        p = _healthy_payload()
        del p["drivers"][0]["expected_points"]
        ok, problems, _ = check_predictions(p)
        assert not ok

    def test_gross_suppression_blocks(self):
        # Every driver scaled WAY down — winner under the floor.
        p = _healthy_payload()
        for d in p["drivers"]:
            d["expected_points"] = d["expected_points"] * 0.2  # top 32 -> 6.4
        ok, problems, _ = check_predictions(p)
        assert not ok
        assert any("top predicted driver" in pr for pr in problems)

    def test_ranking_collapse_warns(self):
        # All drivers within ~2 pts of each other = weak signal (warning, not block).
        p = _healthy_payload()
        for i, d in enumerate(p["drivers"]):
            d["expected_points"] = 20 + (i % 2)  # 20 or 21
        ok, problems, warnings = check_predictions(p)
        # Not necessarily a hard block, but must surface a spread warning.
        assert any("spread" in w for w in warnings) or any("spread" in pr for pr in problems)

    def test_low_constructor_blocks(self):
        p = _healthy_payload()
        for c in p["constructors"]:
            c["expected_points"] = 5
        ok, problems, _ = check_predictions(p)
        assert not ok
        assert any("constructor" in pr for pr in problems)


class TestStrictMode:
    def test_strict_promotes_warnings(self):
        # Odd driver count is a warning normally; strict makes it a problem.
        p = _healthy_payload(n=20)
        ok_loose, _, warns = check_predictions(p)
        ok_strict, probs_strict, _ = check_predictions(p, strict=True)
        assert warns, "expected a count warning on n=20"
        assert ok_loose  # warning doesn't block in loose mode
        assert not ok_strict  # strict promotes it


class TestBiasNerfRegression:
    """The specific incident: bias correction subtracted ~6.6 from front-runners.

    The realized nerf (winner 25.5) actually still cleared the gross floor of 15
    — which is honest: a single suppressed export is hard to distinguish from a
    genuinely low-scoring Monaco by absolute threshold alone. But a HARDER
    suppression (the same bug on a larger bias, or compounded) crosses the floor
    and is caught. We assert the floor catches the catastrophic version.
    """
    def test_heavier_suppression_is_caught(self):
        p = _healthy_payload()
        for d in p["drivers"]:
            d["expected_points"] = d["expected_points"] - 18  # heavier nerf
        ok, problems, _ = check_predictions(p)
        assert not ok
        assert any("top predicted driver" in pr for pr in problems)
