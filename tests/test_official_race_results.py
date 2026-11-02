import json

import pytest

from config import official_results


def test_final_classification_and_reserve_alias_preserve_raw_input(tmp_path, monkeypatch):
    monkeypatch.setattr(official_results, 'SEED_DIR', tmp_path)
    folder = tmp_path / 'round21'
    folder.mkdir()
    raw = {'MRData': {'RaceTable': {'Races': [{
        'season': '2026', 'date': '2026-11-01', 'Results': [
            {'Driver': {'driverId': 'piastri'}, 'position': '1', 'positionText': '1',
             'status': 'Finished', 'points': '25'},
            {'Driver': {'driverId': 'ryo_hirakawa'}, 'position': '2', 'positionText': '2',
             'status': 'Finished', 'points': '18'},
            {'Driver': {'driverId': 'bottas'}, 'position': '3', 'positionText': 'R',
             'status': 'Retired', 'points': '0'},
        ]}]}}}
    path = folder / 'results.json'
    path.write_text(json.dumps(raw))
    original = path.read_bytes()
    correction = {'2026:21': {'date': '2026-11-01', 'source': 'official-result',
                             'order': ['hirakawa', 'piastri', 'bottas']}}
    seed = tmp_path / 'race_result_overrides.json'
    seed.write_text(json.dumps(correction))
    result = official_results.load_result_json(path)['MRData']['RaceTable']['Races'][0]
    assert result['Results'][0]['Driver']['driverId'] == 'hirakawa'
    assert result['Results'][0]['position'] == '1'
    assert result['Results'][0]['points'] == '25'
    assert result['Results'][2]['positionText'] == 'R'
    assert path.read_bytes() == original
    correction['2026:21']['order'].pop()
    seed.write_text(json.dumps(correction))
    with pytest.raises(ValueError, match='full field'):
        official_results.load_result_json(path)
    correction['2026:21']['date'] = '2026-10-25'
    seed.write_text(json.dumps(correction))
    with pytest.raises(ValueError, match='event date'):
        official_results.load_result_json(path)


def test_unaffected_event_keeps_its_classification(tmp_path, monkeypatch):
    monkeypatch.setattr(official_results, 'SEED_DIR', tmp_path)
    path = tmp_path / 'results.json'
    raw = {'MRData': {'RaceTable': {'Races': []}}}
    path.write_text(json.dumps(raw))
    assert official_results.load_result_json(path) == raw


def test_qualifying_dsq_uses_official_classification(tmp_path, monkeypatch):
    from config import post_quali
    monkeypatch.setattr(official_results, 'SEED_DIR', tmp_path)
    monkeypatch.setattr(post_quali, 'load_post_quali_results', lambda *_: {
        'drivers': {'lawson': {'position': 22, 'status': 'DSQ'}}})
    folder = tmp_path / 'round21'
    folder.mkdir()
    path = folder / 'qualifying.json'
    path.write_text(json.dumps({'MRData': {'RaceTable': {'Races': [{
        'season': '2026', 'QualifyingResults': [
            {'Driver': {'driverId': 'lawson'}, 'position': '8', 'Q1': '1:18.0', 'Q2': '1:17.0', 'Q3': '1:17.0'}
        ]}]}}}))
    row = official_results.load_result_json(path)['MRData']['RaceTable']['Races'][0]['QualifyingResults'][0]
    assert row['position'] == '22'
    assert row['Q1'] == row['Q2'] == row['Q3'] == ''


def test_internal_overtake_round_does_not_load_a_different_race(tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module('pipeline.11_actual_fantasy_points')
    monkeypatch.setattr(module, 'SEED_DIR', tmp_path)
    (tmp_path / 'driver_ids.json').write_text(json.dumps({'mappings': [
        {'jolpica': 'lawson', 'abbrev': 'LAW'}]}))
    (tmp_path / 'overtakes.csv').write_text(
        'driver_id,round,overtakes_made,round_numbering\n'
        'lawson,19,1,\n'
        'lawson,21,11,internal\n')
    race, _ = module.load_seed_overtakes(2026, 21)
    assert race == {'LAW': 11}
