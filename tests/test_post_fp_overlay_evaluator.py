from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import evaluate_post_fp_overlays as stage_b


def _event(
    *,
    season: int = 2026,
    round_num: int = 8,
    circuit: str = "monaco",
    sprint: bool = False,
    drivers: int = 12,
) -> pd.DataFrame:
    values = np.arange(drivers, dtype=float)
    return pd.DataFrame(
        {
            "season": season,
            "round": round_num,
            "driver_id": [f"d{i:02d}" for i in range(drivers)],
            "constructor_id": [f"t{i // 2:02d}" for i in range(drivers)],
            "circuit_id": circuit,
            "race_name": "Monaco Grand Prix",
            "has_sprint": sprint,
            "quali_position": values + 1,
            "finish_position": values + 1,
            "is_dnf": 0,
            "is_dns": 0,
            "is_dsq": 0,
            "best_lap_time": 100.0 + values[::-1],
            "best_3_lap_avg": 101.0 + values[::-1] * 1.1,
            "best_5_lap_avg": 102.0 + values[::-1] * 0.9,
            "feature": values,
        }
    )


def test_pre_registered_policy_weights_cover_hard_and_sprint_cases():
    policies = {policy.code: policy for policy in stage_b.POLICIES}
    assert stage_b.policy_blend_weight(policies["B0"], "monaco", False) == 0.0
    assert stage_b.policy_blend_weight(policies["B1"], "monaco", False) == 0.60
    assert stage_b.policy_blend_weight(policies["B2"], "monaco", False) == 0.80
    assert stage_b.policy_blend_weight(policies["B3"], "monaco", True) == 0.15
    assert stage_b.policy_blend_weight(policies["B4"], "monaco", True) == 0.15


def test_fp_blend_and_anchor_match_production_z_space_formulas(monkeypatch):
    event = _event()
    raw = pd.Series(np.linspace(2.0, -1.0, len(event)), index=event.index)
    policy = next(policy for policy in stage_b.POLICIES if policy.code == "B2")

    scores, positions, info = stage_b.blend_quali_event(event, raw, policy)

    composite = stage_b.fp_composite(event)
    expected = (
        0.20 * stage_b._zscore(raw.to_numpy())
        + 0.80 * stage_b._zscore(composite.to_numpy())
    )
    np.testing.assert_allclose(scores.to_numpy(), expected)
    np.testing.assert_array_equal(
        positions.to_numpy(),
        pd.Series(-expected).rank(method="first").astype(int).to_numpy(),
    )
    assert info["fp_blend_applied"] is True
    assert info["fp_pace_driver_count"] == len(event)

    # Production anchoring is currently disabled after the Stage-B audit.
    # Inject the last candidate weight here to keep testing the exact formula.
    monkeypatch.setattr(stage_b, "grid_anchor_weight", lambda _circuit: 0.85)
    race_raw = np.linspace(-0.5, 0.75, len(event))
    anchored, weight, applied = stage_b.apply_grid_anchor(
        race_raw,
        positions.to_numpy(),
        "monaco",
        enabled=True,
        fp_pace_driver_count=len(event),
    )
    expected_anchor = (
        (1.0 - weight) * stage_b._zscore(race_raw)
        + weight * stage_b._zscore(-positions.to_numpy(dtype=float))
    )
    np.testing.assert_allclose(anchored, expected_anchor)
    assert weight == pytest.approx(0.85)
    assert applied is True


def test_raw_quali_training_is_strictly_earlier_event(monkeypatch):
    frames = []
    for round_num in (1, 2, 3):
        frame = _event(round_num=round_num, circuit="albert_park", drivers=4)
        frame["feature"] = np.arange(4) + round_num
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    seen: list[tuple[int, int]] = []

    class FakeModel:
        def predict(self, matrix):
            return matrix["feature"].to_numpy(dtype=float)

    def fake_train(train, features, target, algorithm, params):
        seen.append((int(train["round"].max()), len(train)))
        return FakeModel(), ["feature"]

    monkeypatch.setattr(stage_b.core, "train_ranker", fake_train)
    config = stage_b.StageBConfig(
        name="strict-test",
        min_train_events=1,
        min_train_rows=2,
    )
    raw = stage_b._fit_quali_raw_scores(
        df,
        ["feature"],
        config,
        target_scope="current",
        verbose=False,
    )

    assert seen == [(1, 4), (2, 8)]
    assert raw[df["round"] == 1].isna().all()
    assert raw[df["round"].isin([2, 3])].notna().all()


def test_race_rows_use_policy_quali_and_rank_full_field():
    prior = _event(season=2025, round_num=1, drivers=12)
    target = _event(season=2026, round_num=8, drivers=12)
    df = pd.concat([prior, target], ignore_index=True)
    sequence = pd.Series(
        np.tile(np.arange(12, 0, -1), 2),
        index=df.index,
        dtype=float,
    )
    prior_mask = (df["season"] == 2025) & (df["round"] == 1)
    train = stage_b._race_training_rows(df, prior_mask, sequence)

    np.testing.assert_array_equal(
        train["quali_position"].to_numpy(), sequence.loc[train.index].to_numpy()
    )
    np.testing.assert_array_equal(
        train["grid_advantage"].to_numpy(),
        11.0 - sequence.loc[train.index].to_numpy(),
    )

    # A DNF remains in the test field for full-field ranking, but is excluded
    # from the conditional-ranker evaluation population.
    df.loc[df.index[-1], "is_dnf"] = 1
    target_mask = (df["season"] == 2026) & (df["round"] == 8)
    test = stage_b._race_test_rows(df, target_mask, sequence)
    assert len(test) == 12
    assert int(stage_b.core.classified_finisher_mask(test).sum()) == 11


def test_paired_deltas_use_events_not_driver_rows_and_name_hard_tracks():
    folds = []
    for round_num, race_name in ((8, "Monaco Grand Prix"), (13, "Hungarian Grand Prix")):
        for idx, policy in enumerate(stage_b.POLICIES):
            folds.append(
                {
                    "cluster_id": f"2026-R{round_num:02d}",
                    "season": 2026,
                    "round": round_num,
                    "race_name": race_name,
                    "policy": policy.code,
                    "mae": 4.0 - idx * 0.1,
                    "quali_mae": 2.0,
                    "fp_blend_weight": 0.6,
                    "anchor_candidate_weight": 0.0,
                    "anchor_applied": False,
                }
            )
    paired = stage_b.paired_fold_deltas(folds)
    b4_b0 = [
        row
        for row in paired
        if row["reference_policy"] == "B0" and row["candidate_policy"] == "B4"
    ]
    assert len(b4_b0) == 2
    assert all(
        row["delta_mae_candidate_minus_reference"] == pytest.approx(-0.4)
        for row in b4_b0
    )

    summary = stage_b.summarize(folds, paired)
    assert set(summary["named_hard_track_metrics"]) == {"monaco_r8", "hungary_r13"}
    assert (
        summary["paired_event_deltas"]["B4_minus_B0"]["events"] == 2
    )
    assert "driver-independent bootstrap" in (
        summary["paired_event_deltas"]["B4_minus_B0"]["inference_unit"]
    )


def test_history_cache_identity_is_weight_independent_but_current_is_not():
    config_a = stage_b.StageBConfig(name="a", current_season_weight=2.5)
    config_b = stage_b.StageBConfig(name="b", current_season_weight=4.0)
    features = ["feature"]
    history_a = stage_b._raw_quali_cache_identity(
        "dataset", config_a, features, "history"
    )
    history_b = stage_b._raw_quali_cache_identity(
        "dataset", config_b, features, "history"
    )
    assert history_a == history_b
    current_a = stage_b._raw_quali_cache_identity(
        "dataset", config_a, features, "current", history_a
    )
    current_b = stage_b._raw_quali_cache_identity(
        "dataset", config_b, features, "current", history_b
    )
    assert current_a != current_b
