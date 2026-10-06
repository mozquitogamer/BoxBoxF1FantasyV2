"""Publishing gates must reject incomplete sources and preserve race identity."""
import copy
import json
import io
import urllib.error
from datetime import datetime, timezone

import pytest

from pipeline import auto_post_race as automatic
from pipeline import sync_post_race_official as sync


def test_cancelled_future_and_old_races_are_not_selected():
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    calendar = [
        {'round': 4, 'date': '2026-10-04', 'cancelled': True},
        {'round': 17, 'date': '2026-09-26'},
        {'round': 18, 'date': '2026-10-04'},
        {'round': 19, 'date': '2026-10-11'},
    ]
    assert [race['round'] for race in automatic.candidate_races(calendar, now)] == [18]


def test_results_must_match_calendar_and_have_full_classification():
    race = {'round': 18, 'date': '2026-10-04'}
    payload = {'MRData': {'RaceTable': {'Races': [{'date': race['date'], 'round': '16',
        'Results': [{'Driver': {'driverId': str(index)}} for index in range(22)]}]}}}
    assert automatic.validate_results(payload, race)['round'] == '16'
    bad = copy.deepcopy(payload)
    bad['MRData']['RaceTable']['Races'][0]['date'] = '2026-09-26'
    with pytest.raises(ValueError, match='calendar'):
        automatic.validate_results(bad, race)
    with pytest.raises(sync.PendingData):
        automatic.validate_results({'MRData': {'RaceTable': {'Races': []}}}, race)
    payload['MRData']['RaceTable']['Races'][0]['Results'].pop()
    with pytest.raises(sync.PendingData):
        automatic.validate_results(payload, race)


def test_incomplete_official_scoring_is_not_treated_as_zero(monkeypatch):
    entries = {'drivers': {'VER': {'GamedayPoints': '0', 'QualifyingPoints': '10', 'RacePoints': '',
                                'SessionWisePoints': [{'sessiontype': 'Race', 'points': None}]}}, 'constructors': {}}
    monkeypatch.setattr(sync, 'roster', lambda *args: entries)
    with pytest.raises(sync.PendingData, match='pending'):
        sync.validated_snapshot(18, {'name': 'Bahrain'}, {})


def test_bad_next_prices_do_not_pass_validation(monkeypatch):
    row = {'PlayerId': '1', 'GamedayPoints': '30', 'QualifyingPoints': '10', 'RacePoints': '20',
           'Value': 20, 'SessionWisePoints': [{'sessiontype': 'Race', 'points': 20}],
           'AdditionalStats': {'dotd_pts': 10}}
    current = {'drivers': {'VER': row}, 'constructors': {}}
    next_roster = {'drivers': {'VER': {**row, 'Value': 21, 'OldPlayerValue': 19}}, 'constructors': {}}
    monkeypatch.setattr(sync, 'roster', lambda payload, round_num: current if round_num == 18 else next_roster)
    with pytest.raises(sync.PendingData, match='aligned'):
        sync.validated_snapshot(18, {'name': 'Bahrain'}, {}, {}, 19)


def test_validation_failure_leaves_seed_files_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, 'SEED_DIR', tmp_path)
    source = {'official_fantasy_points.json': {'rounds': {}},
              'fantasy_prices.json': {'price_after_round': 19, 'drivers': {}, 'constructors': {}},
              'dotd_winners.json': {'winners': {}}}
    for name, payload in source.items():
        (tmp_path / name).write_text(json.dumps(payload))
    before = {name: (tmp_path / name).read_bytes() for name in source}
    snapshot = {'points': {'drivers': {}, 'constructors': {}}, 'prices': {'drivers': {'VER': 20}, 'constructors': {}}, 'dotd_winner': 'VER'}
    with pytest.raises(sync.PendingData, match='downgrade'):
        sync.save_seeds(18, 19, snapshot)
    assert before == {name: (tmp_path / name).read_bytes() for name in source}


def test_output_gate_rejects_incomplete_actuals(tmp_path, monkeypatch):
    monkeypatch.setattr(automatic, 'WEB_DATA_DIR', tmp_path)
    monkeypatch.setattr(automatic, 'SEED_DIR', tmp_path)
    (tmp_path / 'actual_round18.json').write_text(json.dumps({'round': 18, 'points_source': 'official_f1_fantasy',
        'drivers': [{'driver_id': 'VER', 'total_points': 57}], 'constructors': []}))
    (tmp_path / 'official_fantasy_points.json').write_text(json.dumps({'rounds': {'18': {
        'drivers': {'VER': 57, 'ANT': 29}, 'constructors': {}}}}))
    with pytest.raises(ValueError, match='differ'):
        automatic.validate_outputs(18)


def test_rate_limit_retries_before_reading_feed(monkeypatch):
    responses = iter([urllib.error.HTTPError('https://example.test', 429, 'limited', {'Retry-After': '20'}, None),
                      io.BytesIO(b'{"ready": true}')])
    def open_feed(*args, **kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response
    waits = []
    monkeypatch.setattr(sync.urllib.request, 'urlopen', open_feed)
    monkeypatch.setattr(sync.time, 'sleep', waits.append)
    assert sync.fetch_json('https://example.test') == {'ready': True}
    assert waits == [20]


def test_unpublished_feed_returns_pending_without_retry(monkeypatch):
    def unpublished(*args, **kwargs):
        raise urllib.error.HTTPError('https://example.test', 404, 'pending', {}, None)
    monkeypatch.setattr(sync.urllib.request, 'urlopen', unpublished)
    with pytest.raises(sync.PendingData, match='not published'):
        sync.fetch_json('https://example.test')
