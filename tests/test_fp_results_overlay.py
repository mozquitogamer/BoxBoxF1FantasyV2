import importlib
import json

import pandas as pd
import pytest


def fixture_bundle(tmp_path, monkeypatch):
    mod = importlib.import_module('pipeline.03_extract_features')
    monkeypatch.setattr(mod, '__file__', str(tmp_path / 'pipeline' / '03_extract_features.py'))
    monkeypatch.setattr(mod, 'SEED_DIR', tmp_path)
    (tmp_path / 'races.json').write_text(json.dumps({'races': [{'round': 21, 'date': '2026-01-04'}]}))
    (tmp_path / 'driver_ids.json').write_text(json.dumps({'mappings': [
        {'jolpica': 'hirakawa', 'openf1_num': 50, 'abbrev': 'HIR'},
    ]}))
    (tmp_path / 'sessions.json').write_text(json.dumps([{
        'session_name': 'Practice 3', 'session_key': 1, 'year': 2026,
        'date_start': '2026-01-03T17:30:00+00:00', 'date_end': '2026-01-03T18:30:00+00:00',
    }]))
    (tmp_path / 'drivers_fp3.json').write_text(json.dumps([
        {'driver_number': 31, 'name_acronym': 'OCO', 'session_key': 1},
        {'driver_number': 11, 'name_acronym': 'PER', 'session_key': 1},
    ]))
    (tmp_path / 'session_result_fp3.json').write_text(json.dumps([
        {'driver_number': 50, 'duration': 79.504, 'session_key': 1},
        {'driver_number': 11, 'duration': None, 'session_key': 1},
    ]))
    return mod


def test_results_update_only_best_pace_and_preserve_lap_evidence(tmp_path, monkeypatch):
    mod = fixture_bundle(tmp_path, monkeypatch)
    frame = pd.DataFrame({
        'driver_id': ['HIR', 'PER'], 'best_lap_time': [79.982, 80.0],
        'best_3_avg': [80.1, 80.2], 'long_run_avg': [85., 86.],
        'total_laps': [23, 20], 'fp_sessions_used': [2, 2],
        'driver_fp_sessions_used': [1, 1],
        'fp_sessions_included': ['FP1,FP2'] * 2, 'fp_data_sources': ['openf1'] * 2,
    })
    result = mod.apply_practice_results(frame, tmp_path, 'FP3', 21, 2026)
    assert result['best_lap_time'].tolist() == [79.504, 80.0]
    assert result['pace_rank'].tolist() == [1, 2]
    assert result['pace_delta_to_fastest'].tolist() == pytest.approx([0, .496])
    for col in ['best_3_avg', 'long_run_avg', 'total_laps', 'fp_sessions_used', 'driver_fp_sessions_used']:
        assert result[col].tolist() == frame[col].tolist()
    assert result['fp_sessions_included'].tolist() == ['FP1,FP2,FP3'] * 2
    assert 'best-lap results only' in result.iloc[0]['fp_coverage_note']
    assert frame.iloc[0]['best_lap_time'] == 79.982


def test_duplicate_results_rejected(tmp_path, monkeypatch):
    mod = fixture_bundle(tmp_path, monkeypatch)
    p = tmp_path / 'session_result_fp3.json'
    rows = json.loads(p.read_text())
    p.write_text(json.dumps(rows + [rows[0]]))
    with pytest.raises(AssertionError, match='Duplicate result driver'):
        mod.apply_practice_results(pd.DataFrame(), tmp_path, 'FP3', 21, 2026)
