"""Regression checks for a shared transform that must preserve live forecasts."""
import numpy as np
import pandas as pd
import pytest
from pipeline.qualifying_transform import blend_qualifying_scores, blend_event_scores


def sample():
    return pd.DataFrame({'season': 2026, 'round': 17, 'circuit_id': 'baku',
                         'total_laps': [10]*22, 'best_lap_time': np.arange(22)+90.0,
                         'best_3_lap_avg': np.arange(22)+90.4,
                         'best_5_lap_avg': np.arange(22)+90.8})


def test_frozen_live_formula_and_sparse_driver_prior_are_preserved():
    frame = sample();frame.loc[7, 'best_5_lap_avg'] = 140
    scores = np.linspace(-1, 2, 22)
    blended, evidence = blend_qualifying_scores(frame, scores, 'baku')
    z = (scores - scores.mean()) / scores.std()
    pace = -np.arange(22, dtype=float);valid = np.ones(22, dtype=bool);valid[7] = False
    pace_z = (pace[valid]-pace[valid].mean())/pace[valid].std()
    expected = z.copy();expected[valid] = 0.4*z[valid]+0.6*pace_z
    np.testing.assert_allclose(blended, expected, atol=1e-14)
    assert evidence['driver_count'] == 21 and evidence['applied']
    assert blended[7] == pytest.approx(z[7])


def test_priors_only_and_insufficient_field_do_not_rescale_scores():
    scores = np.arange(22, dtype=float)
    for frame in [pd.DataFrame(index=range(22)), sample().iloc[:8]]:
        values = scores[:len(frame)]
        result, evidence = blend_qualifying_scores(frame, values, 'monaco')
        np.testing.assert_array_equal(result, values)
        assert not evidence['applied']


def test_each_event_has_its_own_composite_and_sprint_weight():
    first = sample();second = sample();second['round'] = 19;second['circuit_id'] = 'marina_bay';second['sprint_grid'] = np.arange(1,23)
    frame = pd.concat([first,second],ignore_index=True)
    scores = np.tile(np.linspace(-1,2,22),2)
    result = blend_event_scores(frame,scores)
    a,_ = blend_qualifying_scores(first,scores[:22],'baku')
    b,evidence = blend_qualifying_scores(second,scores[22:],'marina_bay',True)
    np.testing.assert_allclose(result,np.concatenate([a,b]))
    assert evidence['weight'] == 0.15
