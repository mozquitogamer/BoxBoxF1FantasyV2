"""The Mexico reserve keeps his own evidence and does not replace historical Ocon."""
import importlib
import pandas as pd

from config.driver_assets import active_driver_assets, active_constructor_driver_assets
from config.fantasy_prices import load_fantasy_price_maps


def test_hirakawa_is_mexico_only_with_provisional_price():
    mexico = {row['asset_id']: row for row in active_driver_assets(21)}
    assert len(mexico) == 22
    assert 'OCO' not in mexico
    hir = mexico['HIR_HAAS']
    assert hir['model_driver_id'] == 'hirakawa'
    assert hir['effective_from_session'] == 'FP3'
    assert hir['price_provisional']
    assert hir['legacy_asset_ids'] == []
    assert hir['confidence_multiplier'] < 1 and hir['mc_noise_multiplier'] > 1
    assert set(active_constructor_driver_assets(21)['haas']) == {'BEA', 'HIR_HAAS'}
    for round_num, year in [(20, 2026), (22, 2026), (25, 2026), (21, 2025)]:
        roster = {row['asset_id'] for row in active_driver_assets(round_num, year)}
        assert 'OCO' in roster and 'HIR_HAAS' not in roster
    prices, _ = load_fantasy_price_maps(round_num=21)
    assert prices['HIR_HAAS'] == 10.1 and 'OCO' not in prices
    for round_num in [22, 25]:
        future, _ = load_fantasy_price_maps(round_num=round_num)
        assert future['OCO'] == 10.1 and 'HIR_HAAS' not in future
        assert {k:v for k,v in future.items() if k != 'OCO'} == {k:v for k,v in prices.items() if k != 'HIR_HAAS'}


def test_prediction_merge_uses_hirakawas_laps_and_identity():
    predict = importlib.import_module('pipeline.06_run_predictions')
    ids, _ = predict.load_driver_id_maps()
    priors = pd.DataFrame({'driver_id': ['hirakawa', 'bearman'], 'round': [21, 21]})
    fp = pd.DataFrame({'driver_id': ['HIR', 'OCO', 'BEA'],
                       'best_lap_time': [79.982, 78.774, 78.849],
                       'fp_sessions_used': [1, 1, 2]})
    merged = predict.assemble_prediction_rows(priors, fp, ids, 21, 2026).set_index('driver_id')
    assert set(merged.index) == {'hirakawa', 'bearman'}
    assert merged.loc['hirakawa', 'asset_id'] == 'HIR_HAAS'
    assert merged.loc['hirakawa', 'best_lap_time'] == 79.982
    assert merged.loc['hirakawa', 'fp_sessions_used'] == 1
    builder = importlib.import_module('pipeline.02_build_laps')
    mappings, _ = builder.load_id_mappings()
    assert mappings['HIR'] == mappings['ryo hirakawa'] == 'HIR'


def test_export_and_simulation_resolve_the_replacement_to_haas():
    exporter = importlib.import_module('pipeline.08_export_website_json')
    mc = importlib.import_module('pipeline.08_monte_carlo_fantasy')
    for roster in [exporter.load_driver_info(21), mc.load_drivers_info(21)]:
        assert len(roster) == 22 and 'OCO' not in roster
        assert roster['HIR_HAAS']['constructor_id'] == 'haas'
        assert roster['HIR_HAAS']['first_name'] == 'Ryo'
        assert roster['HIR_HAAS']['price_provisional']


def test_v13_reserve_has_no_historical_points_from_outgoing_driver():
    import pytest
    from pipeline.build_v13_manager import _official_driver_points
    official = {'1': {'drivers': {'OCO': 12.0}}}
    assert _official_driver_points(official, 1, 'HIR_HAAS') == 0.0
    assert _official_driver_points(official, 1, 'OCO') == 12.0
    with pytest.raises(KeyError):
        _official_driver_points(official, 1, 'UNKNOWN')


def test_confidence_counts_personal_sessions_without_changing_model_feature():
    import numpy as np
    predict = importlib.import_module('pipeline.06_run_predictions')
    frame = pd.DataFrame({'fp_sessions_used': [2, 2], 'driver_fp_sessions_used': [1, 2]})
    confidence = predict.calculate_confidence(frame, np.zeros(2), np.zeros(2), None)
    assert confidence.tolist() == [53, 56]
    assert frame['fp_sessions_used'].tolist() == [2, 2]


def test_personal_session_count_is_excluded_from_training_features(tmp_path, monkeypatch):
    from pipeline.fp_long_runs import FP_STINT_SEMANTICS_VERSION
    builder = importlib.import_module('pipeline.04_build_model_inputs')
    monkeypatch.setattr(builder, 'FEATURES_DIR', tmp_path)
    folder = tmp_path / 'round21'
    folder.mkdir()
    pd.DataFrame({'driver_id': ['HIR'], 'fp_sessions_used': [2],
                  'driver_fp_sessions_used': [1], 'best_lap_time': [79.982],
                  'fp_stint_semantics_version': [FP_STINT_SEMANTICS_VERSION]}).to_parquet(folder / 'features.parquet')
    loaded = builder.load_fp_features_for_round(2026, 21)
    assert 'driver_fp_sessions_used' not in loaded.columns
    assert loaded.iloc[0]['fp_sessions_used'] == 2
