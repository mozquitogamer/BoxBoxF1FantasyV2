import json

import pytest

from pipeline.form_blend import FORM_BLEND_TUNABLES, apply_form_blend, recency_form


def _ewm(values, hl=3.0):
    n = len(values)
    w = [0.5 ** ((n - 1 - i) / hl) for i in range(n)]
    return sum(a * b for a, b in zip(w, values)) / sum(w)


@pytest.fixture
def dirs(tmp_path):
    seed, web = tmp_path / "seed", tmp_path / "web"
    seed.mkdir(); web.mkdir()
    official = {"season": 2026, "rounds": {
        "1": {"drivers": {"AAA": 10, "LAW": 4, "BBB": 2}, "constructors": {"red": 30, "blue": 8}},
        "2": {"drivers": {"AAA": 20, "LAW": 6, "BBB": 4}, "constructors": {"red": 40, "blue": 10}},
        "3": {"drivers": {"AAA": 30, "LAW": 8, "BBB": 6}, "constructors": {"red": 50, "blue": 12}},
        "4": {"drivers": {"AAA": 99}, "constructors": {"red": 99}},  # later than the forecast round
    }}
    (seed / "official_fantasy_points.json").write_text(json.dumps(official))
    for r in (1, 2, 3):
        (web / f"actual_round{r}.json").write_text(json.dumps({"drivers": [
            {"driver_id": "AAA", "constructor": "red"}, {"driver_id": "LAW", "constructor": "blue"},
            {"driver_id": "BBB", "constructor": "blue"}]}))
    return seed, web


def _payload():
    return {"drivers": [
        {"driver_id": "AAA", "constructor": "red", "current_price": 20.0, "expected_points": 40.0,
         "projected_points": 45.0, "expected_points_race": 32.0, "mc_total_mean": 40.0, "mc_total_median": 42.0,
         "mc_total_p5": 5.0, "mc_total_p95": 70.0, "mc_race_pts_mean": 32.0},
        {"driver_id": "LAW_RED_BULL", "asset_legacy_ids": ["LAW"], "constructor": "red", "current_price": 10.0,
         "expected_points": 10.0, "mc_total_mean": 10.0},
        {"driver_id": "NEW", "constructor": "blue", "current_price": 5.0, "expected_points": 1.0, "mc_total_mean": 1.0},
    ], "constructors": [
        {"constructor_id": "red", "current_price": 30.0, "expected_points": 60.0, "mc_total_mean": 60.0, "mc_total_p5": 20.0},
        {"constructor_id": "blue", "current_price": 10.0, "expected_points": 5.0, "mc_total_mean": 5.0},
    ]}


def test_blend_math_and_distribution_shift(dirs):
    seed, web = dirs
    p = _payload()
    meta = apply_form_blend(p, 4, "pre_fp", seed_dir=seed, web_dir=web)
    w = FORM_BLEND_TUNABLES["model_weight"]["pre_fp"]
    form = _ewm([10, 20, 30])
    a = p["drivers"][0]
    expected = round(w * 40.0 + (1 - w) * form, 1)
    delta = (1 - w) * (form - 40.0)
    assert meta["applied"] and meta["history_rounds"] == [1, 2, 3]
    assert a["expected_points"] == pytest.approx(expected, abs=0.051)
    assert a["mc_total_mean"] == a["expected_points"]
    assert a["mc_total_p5"] == pytest.approx(5.0 + delta, abs=0.051)
    assert a["mc_total_p95"] == pytest.approx(70.0 + delta, abs=0.051)
    assert a["expected_points_race"] == pytest.approx(32.0 + delta, abs=0.051)
    assert a["projected_points"] == 45.0  # deterministic scenario untouched
    assert a["expected_points_model"] == 40.0 and a["form_points"] == round(form, 1)
    assert a["value_score"] == round(a["expected_points"] / 20.0, 2)


def test_round_four_points_are_not_used_for_round_four(dirs):
    seed, web = dirs
    d, c, past = recency_form(_payload(), 4, seed_dir=seed, web_dir=web)
    assert past == [1, 2, 3] and d["AAA"] == pytest.approx(_ewm([10, 20, 30]))


def test_legacy_id_history_and_team_fallback(dirs):
    seed, web = dirs
    d, c, _ = recency_form(_payload(), 4, seed_dir=seed, web_dir=web)
    assert d["LAW_RED_BULL"] == pytest.approx(_ewm([4, 6, 8]))
    # NEW has no history: team "blue" mean per driver over rounds 1-3 (LAW and BBB raced for blue)
    assert d["NEW"] == pytest.approx(sum([4, 2, 6, 4, 8, 6]) / 6)
    assert c["red"] == pytest.approx(_ewm([30, 40, 50]))


def test_post_quali_is_not_blended(dirs):
    seed, web = dirs
    p = _payload()
    meta = apply_form_blend(p, 4, "post_quali", seed_dir=seed, web_dir=web)
    assert meta == {"applied": False, "phase": "post_quali", "reason": "phase_not_blended"}
    assert p["drivers"][0]["expected_points"] == 40.0


def test_never_blends_twice(dirs):
    seed, web = dirs
    p = _payload()
    apply_form_blend(p, 4, "post_fp", seed_dir=seed, web_dir=web)
    once = json.dumps(p, sort_keys=True)
    apply_form_blend(p, 4, "post_fp", seed_dir=seed, web_dir=web)
    assert json.dumps(p, sort_keys=True) == once


def test_needs_three_completed_rounds(dirs):
    seed, web = dirs
    p = _payload()
    meta = apply_form_blend(p, 3, "pre_fp", seed_dir=seed, web_dir=web)
    assert meta["applied"] is False and p["drivers"][0]["expected_points"] == 40.0


def test_disabled(dirs):
    seed, web = dirs
    p = _payload()
    meta = apply_form_blend(p, 4, "pre_fp", seed_dir=seed, web_dir=web,
                            tunables={**FORM_BLEND_TUNABLES, "enabled": False})
    assert meta["applied"] is False and p["drivers"][0]["expected_points"] == 40.0
