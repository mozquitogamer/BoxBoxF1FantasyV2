"""Session deadlines, retries, manual overrides and publication evidence."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from pipeline import auto_weekend as automatic
from pipeline.sync_post_race_official import PendingData

UTC = timezone.utc
RACE = {'round': 19, 'name': 'Singapore Grand Prix', 'date': '2026-10-11'}
START = datetime(2026, 10, 9, 8, 30, tzinfo=UTC)
FINISH = START + timedelta(hours=1)


def session(name='Practice 1', key=1, start=START, offset='08:00:00'):
    return {'session_key': key, 'meeting_key': 1296, 'session_name': name,
            'date_start': start.isoformat(), 'date_end': (start + timedelta(hours=1)).isoformat(),
            'gmt_offset': offset, 'is_cancelled': False}


def race_session(start=datetime(2026, 10, 11, 12, tzinfo=UTC)):
    return session('Race', 99, start)


def control(finish=FINISH, phase=None, message='SESSION FINISHED'):
    return [{'date': finish.isoformat(), 'category': 'SessionStatus',
             'qualifying_phase': phase, 'message': message}]


def select(now, rows=None, state=None, settled=None, live=19, messages=None, calendar=None):
    return automatic.select_due(calendar or [RACE], rows or [session(), race_session()],
                                state or {}, settled or {}, live, now,
                                lambda key: (messages or {}).get(key, control()))


@pytest.mark.parametrize('name,code', [('Practice 1', 'FP1'), ('Practice 2', 'FP2'), ('Practice 3', 'FP3')])
def test_practice_is_due_exactly_35_minutes_after_finish(name, code):
    rows = [session(name), race_session()]
    due = FINISH + timedelta(minutes=35)
    assert select(due - timedelta(microseconds=1), rows=rows) is None
    event = select(due, rows=rows)
    assert event['session'] == code
    assert event['phase'] == 'post_fp'
    assert automatic.instant(event['due_at']) == due


@pytest.mark.parametrize('name,phase', [('Sprint Qualifying', 'post_fp'), ('Qualifying', 'post_quali')])
def test_qualifying_waits_for_q3_and_uses_separate_phases(name, phase):
    now = FINISH + timedelta(minutes=35)
    rows = [session(name), race_session()]
    assert select(now, rows=rows, messages={1: control(phase=1)}) is None
    assert select(now, rows=rows, messages={1: control(phase=2)}) is None
    event = select(now, rows=rows, messages={1: control(phase=3)})
    assert event['phase'] == phase
    assert event['session'] == ('SQ' if name.startswith('Sprint') else 'Qualifying')


def test_overrun_uses_actual_finish_and_does_not_treat_red_flag_as_finished():
    now = FINISH + timedelta(minutes=35)
    assert select(now, messages={1: control(FINISH + timedelta(minutes=25))}) is None
    assert select(now, messages={1: control(message='SESSION STOPPED')}) is None
    assert select(now + timedelta(minutes=25), messages={1: control(FINISH + timedelta(minutes=25))})


def test_post_race_waits_24_hours_after_actual_finish():
    row = race_session()
    finish = automatic.instant(row['date_end']) + timedelta(hours=1, minutes=20)
    rows = [row]
    due = finish + timedelta(hours=24)
    assert select(due - timedelta(seconds=1), rows=rows, messages={99: control(finish)}) is None
    event = select(due, rows=rows, messages={99: control(finish)})
    assert event['phase'] == 'post_race'
    assert automatic.instant(event['due_at']) == due


def test_sprint_weekend_does_not_invent_fp2_or_fp3_or_settle_sprint_race():
    rows = [session(), session('Sprint Qualifying', 2, START + timedelta(hours=4)),
            session('Sprint', 3, START + timedelta(days=1)), race_session()]
    finish = FINISH + timedelta(hours=4)
    event = select(finish + timedelta(minutes=35), rows=rows, messages={2: control(finish, 3)})
    assert event['session'] == 'SQ'


def test_cancelled_rounds_sessions_unknown_meetings_and_later_live_round_skip():
    now = FINISH + timedelta(minutes=35)
    assert select(now, calendar=[{**RACE, 'cancelled': True}]) is None
    assert select(now, rows=[{**session(), 'is_cancelled': True}, race_session()]) is None
    assert select(now, rows=[{**session(), 'meeting_key': 8}, race_session()]) is None
    assert select(now, live=20) is None


def test_local_event_date_handles_las_vegas_utc_next_day():
    race = {'round': 23, 'name': 'Las Vegas', 'date': '2026-11-21'}
    start = datetime(2026, 11, 22, 4, tzinfo=UTC)
    row = session('Race', 99, start, '-08:00:00')
    assert automatic.local_date(row) == '2026-11-21'
    finish = start + timedelta(hours=2)
    event = select(finish + timedelta(hours=24), rows=[row], calendar=[race],
                   messages={99: control(finish)}, live=23)
    assert event['round'] == 23


def test_missed_updates_coalesce_and_completed_latest_prevents_downgrade():
    fp2 = session('Practice 2', 2, START + timedelta(hours=4))
    finish = FINISH + timedelta(hours=4)
    now = finish + timedelta(minutes=35)
    rows = [session(), fp2, race_session()]
    event = select(now, rows=rows, messages={2: control(finish)})
    assert event['session'] == 'FP2'
    state = {'completed': {event['key']: event}}
    assert select(now, rows=rows, state=state, messages={2: control(finish)}) is None


def test_no_practice_update_after_race_start_and_no_repeat_existing_settlement():
    now = automatic.instant(race_session()['date_start']) + timedelta(days=1, hours=3)
    assert select(now, settled={'rounds': {'19': {'completed_at': now.isoformat()}}}) is None


def setup_files(tmp_path, monkeypatch):
    monkeypatch.setattr(automatic, 'WEB_DATA_DIR', tmp_path / 'web')
    monkeypatch.setattr(automatic, 'PREDICTIONS_DIR', tmp_path / 'predictions')
    monkeypatch.setattr(automatic, 'STATE_PATH', tmp_path / 'weekend_state.json')
    monkeypatch.setattr(automatic, 'SEED_DIR', tmp_path / 'seed')
    started = datetime.now(UTC)
    event = {'round': 19, 'phase': 'post_fp', 'session': 'FP1'}
    payload = {'round': 19, 'phase': 'post_fp', 'simulation_generated_at': started.isoformat(),
               'drivers': [{'driver_id': str(i)} for i in range(22)],
               'constructors': [{'constructor_id': str(i)} for i in range(11)]}
    metadata = {'round': 19, 'phase': 'post_fp', 'generated_at': started.isoformat(),
                'fp_sessions_included': ['FP1']}
    def save(payload=payload, metadata=metadata, weather=None):
        for path, data in [(automatic.WEB_DATA_DIR / 'predictions.json', payload),
                           (automatic.PREDICTIONS_DIR / 'round19/prediction_metadata.json', metadata),
                           (automatic.WEB_DATA_DIR / 'weather.json', weather or {'round': 19, 'last_updated': started.isoformat()}),
                           (automatic.SEED_DIR / 'races.json', {'races': [RACE]})]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
    save()
    return event, started, payload, metadata, save


def test_forecast_gate_requires_fresh_unique_complete_roster(tmp_path, monkeypatch):
    event, started, payload, metadata, save = setup_files(tmp_path, monkeypatch)
    automatic.validate_forecast(event, started)
    stale = {**payload, 'simulation_generated_at': (started - timedelta(seconds=1)).isoformat()}
    save(payload=stale)
    with pytest.raises(ValueError, match='Fresh'):
        automatic.validate_forecast(event, started)
    save(payload={**payload, 'drivers': payload['drivers'][:-1]})
    with pytest.raises(ValueError, match='Fresh'):
        automatic.validate_forecast(event, started)
    save(payload={**payload, 'drivers': [payload['drivers'][0]] * 22})
    with pytest.raises(ValueError, match='Fresh'):
        automatic.validate_forecast(event, started)


def test_new_practice_sq_qualifying_and_weather_evidence_is_required(tmp_path, monkeypatch):
    event, started, payload, metadata, save = setup_files(tmp_path, monkeypatch)
    with pytest.raises(PendingData, match='practice'):
        automatic.validate_forecast({**event, 'session': 'FP2'}, started)
    with pytest.raises(PendingData, match='Sprint'):
        automatic.validate_forecast({**event, 'session': 'SQ'}, started)
    save(metadata={**metadata, 'sprint_grid_is_actual': True})
    automatic.validate_forecast({**event, 'session': 'SQ'}, started)
    payload.update(phase='post_quali', final_fix={'qualifying_locked': False})
    metadata.update(phase='post_quali')
    save()
    event.update(phase='post_quali', session='Qualifying')
    with pytest.raises(PendingData, match='locked'):
        automatic.validate_forecast(event, started)
    payload['final_fix']['qualifying_locked'] = True
    save()
    automatic.validate_forecast(event, started)
    save(weather={'round': 20, 'last_updated': started.isoformat()})
    with pytest.raises(ValueError, match='weather'):
        automatic.validate_forecast(event, started)


def test_manual_selection_bypasses_delay_but_unknown_round_is_rejected(tmp_path, monkeypatch):
    setup_files(tmp_path, monkeypatch)
    assert automatic.manual_event('post_quali', None)['round'] == 19
    assert automatic.manual_event('post_race', 19)['manual']
    with pytest.raises(ValueError, match='Unknown'):
        automatic.manual_event('post_race', 4)


def test_manual_round_only_preserves_post_race_command_and_plan_is_read_only(monkeypatch):
    requested = []
    monkeypatch.setattr(automatic, 'manual_event', lambda phase, num: requested.append((phase, num)) or {'phase': phase, 'round': num})
    monkeypatch.setattr(automatic, 'execute', lambda event: pytest.fail('plan must not execute'))
    assert automatic.main(['--round', '18', '--plan']) == 0
    assert requested == [('post_race', 18)]


def test_failed_validation_never_marks_session_complete(tmp_path, monkeypatch):
    setup_files(tmp_path, monkeypatch)
    event = automatic.event_for(RACE, session(), FINISH)
    calls = []
    monkeypatch.setattr(automatic, 'require_session', lambda event: None)
    monkeypatch.setattr(automatic.auto_post_race, 'run', lambda *args: calls.append(args))
    def pending(*args):
        raise PendingData('feed pending')
    monkeypatch.setattr(automatic, 'validate_forecast', pending)
    with pytest.raises(PendingData):
        automatic.execute(event)
    assert not automatic.STATE_PATH.exists()
    assert calls[0] == ('weather_forecast.py', '--round', 19)
    monkeypatch.setattr(automatic, 'validate_forecast', lambda *args: None)
    automatic.execute(event)
    assert event['key'] in json.loads(automatic.STATE_PATH.read_text())['completed']


def test_post_race_execution_keeps_settlement_and_next_forecast_together(tmp_path, monkeypatch):
    setup_files(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(automatic.auto_post_race, 'main', lambda args: calls.append(args))
    event = automatic.event_for(RACE, race_session(), FINISH)
    automatic.execute(event)
    assert calls == [['--round', '19']]
    assert event['key'] in json.loads(automatic.STATE_PATH.read_text())['completed']


def test_empty_automatic_plan_does_not_run_pipeline(monkeypatch):
    monkeypatch.setattr(automatic, 'plan', lambda now: None)
    monkeypatch.setattr(automatic, 'execute', lambda event: pytest.fail('nothing is due'))
    assert automatic.main([]) == 0


def test_ready_check_refreshes_fastf1_cache_and_retries_missing_telemetry(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from config import settings
    cache_calls = []
    cache = SimpleNamespace(enable_cache=lambda *args, **kwargs: cache_calls.append(kwargs))
    monkeypatch.setitem(sys.modules, 'fastf1', SimpleNamespace(Cache=cache))
    monkeypatch.setattr(settings, 'FASTF1_CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(automatic, 'load_script', lambda name: SimpleNamespace(download_fastf1_session=lambda *args: False))
    with pytest.raises(PendingData, match='telemetry'):
        automatic.require_session({'round': 19, 'session': 'FP1'})
    assert cache_calls == [{'force_renew': True}]


def test_provider_live_window_is_retried_without_running_pipeline(monkeypatch):
    import urllib.error
    def live(url):
        raise urllib.error.HTTPError(url, 401, 'Live data requires access', {}, None)
    monkeypatch.setattr(automatic, 'fetch_json', live)
    assert automatic.load_control(123) == []
