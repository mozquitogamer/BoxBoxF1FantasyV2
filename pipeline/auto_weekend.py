"""Run updates 35 minutes after practice/qualifying and 24 hours after a race.

The planner uses only the standard library. Schedule checks do not install the
prediction stack or run pipelines when no session is due.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import CURRENT_SEASON, SEED_DIR, WEB_DATA_DIR, PREDICTIONS_DIR, FASTF1_RAW_DIR, RAW_DIR
from pipeline import auto_post_race
from pipeline.sync_post_race_official import PendingData, fetch_json, write_json

STATE_PATH = ROOT / 'data/automation/weekend_state.json'
SESSION_CODES = {'Practice 1': 'FP1', 'Practice 2': 'FP2', 'Practice 3': 'FP3',
                 'Sprint Qualifying': 'SQ', 'Qualifying': 'Qualifying', 'Race': 'Race'}
PRACTICE_CODES = ('FP1', 'FP2', 'FP3')
OPENF1 = 'https://api.openf1.org/v1'


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Session timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def local_date(session):
    offset = session.get('gmt_offset', '00:00:00')
    sign = -1 if offset.startswith('-') else 1
    parts = [int(part) for part in offset.lstrip('+-').split(':')]
    return (instant(session['date_start']) + sign * timedelta(hours=parts[0], minutes=parts[1])).date().isoformat()


def confirmed_finish(session, messages):
    """Q1/Q2 finishes and red-flag stops are not the qualifying session finish."""
    finishes = [instant(row['date']) for row in messages
                if row.get('category') == 'SessionStatus' and row.get('message') == 'SESSION FINISHED'
                and (session['session_name'] not in ('Qualifying', 'Sprint Qualifying')
                     or row.get('qualifying_phase') == 3)]
    return max(finishes) if finishes else None


def event_for(race, session, finish):
    code = SESSION_CODES[session['session_name']]
    phase = 'post_race' if code == 'Race' else 'post_quali' if code == 'Qualifying' else 'post_fp'
    delay = timedelta(hours=24) if code == 'Race' else timedelta(minutes=35)
    return {'key': f'{CURRENT_SEASON}:{race["round"]}:{code}', 'round': race['round'],
            'race': race['name'], 'session': code, 'session_key': session['session_key'], 'phase': phase,
            'meeting_key': session['meeting_key'],
            'finished_at': finish.isoformat(), 'due_at': (finish + delay).isoformat()}


def select_due(calendar, sessions, state, settled, live_round, now, load_control):
    """Coalesce missed updates and prevent an older session replacing a newer one."""
    events = []
    completed = state.get('completed', {})
    for race in calendar:
        if race.get('cancelled') or not (now.date() - timedelta(days=7) <= datetime.fromisoformat(race['date']).date() <= now.date() + timedelta(days=4)):
            continue
        matches = [s for s in sessions if s.get('session_name') == 'Race'
                   and not s.get('is_cancelled') and local_date(s) == race['date']]
        if len(matches) != 1:
            continue
        race_session = matches[0]
        for session in sessions:
            if session.get('meeting_key') != race_session['meeting_key'] or session.get('session_name') not in SESSION_CODES or session.get('is_cancelled'):
                continue
            code = SESSION_CODES[session['session_name']]
            key = f'{CURRENT_SEASON}:{race["round"]}:{code}'
            if key in completed:
                continue
            if code == 'Race':
                # Respect verified settlements created before this scheduler.
                if str(race['round']) in settled.get('rounds', {}):
                    continue
            elif live_round > race['round'] or now >= instant(race_session['date_start']):
                continue
            delay = timedelta(hours=24) if code == 'Race' else timedelta(minutes=35)
            if now < instant(session['date_start']) + delay:
                continue
            finish = confirmed_finish(session, load_control(session['session_key']))
            if finish is None:
                continue
            if any(item.get('round') == race['round'] and instant(item['finished_at']) >= finish
                   for item in completed.values()):
                continue
            event = event_for(race, session, finish)
            if instant(event['due_at']) <= now:
                events.append(event)
    return max(events, key=lambda event: (event['round'], instant(event['finished_at']))) if events else None


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def load_control(session_key):
    # Free OpenF1 access starts after the live-data window. A delayed session
    # can still be in that window when its original scheduled end has passed.
    try:
        return fetch_json(f'{OPENF1}/race_control?session_key={session_key}&category=SessionStatus')
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return []
        raise


def session_schedule():
    try:
        sessions = fetch_json(f'{OPENF1}/sessions?year={CURRENT_SEASON}')
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise PendingData('OpenF1 session schedule is temporarily unavailable') from exc
        raise
    if not isinstance(sessions, list) or not sessions:
        raise PendingData('Session schedule is unavailable')
    return sessions


def plan(now):
    calendar = read_json(SEED_DIR / 'races.json', {})['races']
    if not any(not race.get('cancelled') and now.date() - timedelta(days=7) <=
               datetime.fromisoformat(race['date']).date() <= now.date() + timedelta(days=4)
               for race in calendar):
        return None
    sessions = session_schedule()
    return select_due(calendar, sessions, read_json(STATE_PATH, {}),
                      read_json(auto_post_race.STATE_PATH, {}),
                      read_json(WEB_DATA_DIR / 'predictions.json', {}).get('round', 0), now,
                      load_control)


def manual_event(phase, round_num, now=None):
    now = now or datetime.now(timezone.utc)
    calendar = read_json(SEED_DIR / 'races.json', {})['races']
    if phase == 'post_race' and round_num is None:
        candidates = auto_post_race.candidate_races(calendar, now)
        if not candidates:
            raise ValueError('No recent race; enter an internal calendar round')
        round_num = candidates[0]['round']
    if round_num is None:
        round_num = read_json(WEB_DATA_DIR / 'predictions.json', {})['round']
    race = next((r for r in calendar if r['round'] == round_num and not r.get('cancelled')), None)
    if race is None:
        raise ValueError('Unknown or cancelled round')
    if phase == 'post_race':
        return {'round': round_num, 'phase': phase, 'race': race['name'], 'manual': True}

    sessions = [row for row in session_schedule() if not row.get('is_cancelled')]
    races = [row for row in sessions if row['session_name'] == 'Race' and local_date(row) == race['date']]
    if len(races) != 1:
        raise PendingData('The race weekend has no unique timing schedule yet')
    if now >= instant(races[0]['date_start']):
        raise ValueError('Session forecasts close when the race starts')
    codes = PRACTICE_CODES + ('SQ',) if phase == 'post_fp' else ('Qualifying',)
    started = [row for row in sessions if row['meeting_key'] == races[0]['meeting_key']
               and SESSION_CODES.get(row['session_name']) in codes and instant(row['date_start']) <= now]
    if not started:
        raise PendingData(f'No {phase} session has started for round {round_num}')
    session = max(started, key=lambda row: instant(row['date_start']))
    finish = confirmed_finish(session, load_control(session['session_key']))
    if finish is None or finish > now:
        raise PendingData(f'{session["session_name"]} has no confirmed finish yet')
    return {**event_for(race, session, finish), 'manual': True}


def load_script(name):
    spec = importlib.util.spec_from_file_location('weekend_' + name[:2], ROOT / 'pipeline' / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expected_practice(event):
    code = event.get('session')
    if code == 'SQ':
        return ('FP1',)
    return PRACTICE_CODES[:PRACTICE_CODES.index(code) + 1] if code in PRACTICE_CODES else ()


def recover_practice(event, missing):
    meeting_key = event.get('meeting_key')
    if meeting_key is None:
        raise PendingData(f'{", ".join(missing)} telemetry is not available yet')
    try:
        sessions = fetch_json(f'{OPENF1}/sessions?meeting_key={meeting_key}')
        bundle_dir = RAW_DIR / 'openf1' / f'year{CURRENT_SEASON}' / f'round{event["round"]}' / 'practice'
        write_json(bundle_dir / 'sessions.json', sessions)
        for code in missing:
            matches = [row for row in sessions if SESSION_CODES.get(row.get('session_name')) == code
                       and row.get('meeting_key') == meeting_key and not row.get('is_cancelled')]
            if len(matches) != 1:
                raise PendingData(f'{code} session is missing from OpenF1')
            session = matches[0]
            key = session['session_key']
            if code == event['session'] and key != event['session_key']:
                raise ValueError('OpenF1 practice session does not match the selected event')
            bundle = {name: fetch_json(f'{OPENF1}/{name}?session_key={key}')
                      for name in ('race_control', 'session_result', 'laps', 'drivers', 'stints', 'weather')}
            lap_numbers = defaultdict(set)
            for lap in bundle['laps']:
                lap_numbers[lap['driver_number']].add(lap['lap_number'])
            results = bundle['session_result']
            if (not confirmed_finish(session, bundle['race_control'])
                    or len({row['driver_number'] for row in results}) != 22
                    or any(not isinstance(row.get('number_of_laps'), int)
                           or len(lap_numbers[row['driver_number']]) < row['number_of_laps']
                           for row in results)):
                raise PendingData(f'Complete {code} timing and classification are pending')
            for name, rows in bundle.items():
                write_json(bundle_dir / f'{name}_{code.lower()}.json', rows)
            auto_post_race.run('import_openf1_fp.py', '--round', event['round'],
                               '--session', code, '--session-key', key, '--bundle', bundle_dir)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise PendingData('OpenF1 practice timing is temporarily unavailable') from exc
        raise


def require_session(event):
    """A downloader process can succeed while its upstream data is still missing."""
    code = event.get('session')
    if not code:
        return
    if code == 'Qualifying':
        from config.post_quali import load_post_quali_results
        if load_post_quali_results(event['round']):
            return
    import fastf1
    from config.settings import FASTF1_CACHE_DIR, fastf1_round
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR), force_renew=True)
    if code == 'Qualifying':
        from fastf1.exceptions import DataNotLoadedError
        try:
            session = fastf1.get_session(CURRENT_SEASON, fastf1_round(event['round']), 'Qualifying')
            session.load(laps=False, telemetry=False, weather=False, messages=False)
            results = session.results
        except DataNotLoadedError as exc:
            raise PendingData('Complete qualifying classification is not available yet') from exc
        if results is None or len(results) != 22 or results['Position'].isna().any() or set(results['Position'].astype(int)) != set(range(1, 23)):
            raise PendingData('Complete qualifying classification is not available yet')
        return

    download = load_script('01_download_data.py').download_fastf1_session
    output = FASTF1_RAW_DIR / f'year{CURRENT_SEASON}' / f'round{event["round"]}'
    missing = [name for name in expected_practice(event)
               if not download(CURRENT_SEASON, event['round'], name, output)]
    if missing:
        recover_practice(event, missing)
    if code == 'SQ' and not download(CURRENT_SEASON, event['round'], code, output):
        raise PendingData('Sprint qualifying timing is not available yet')


def validate_prediction(event, started):
    metadata = read_json(PREDICTIONS_DIR / f'round{event["round"]}' / 'prediction_metadata.json', {})
    if metadata.get('phase') != event['phase'] or metadata.get('round') != event['round']:
        raise PendingData('Forecast phase does not match the completed session')
    if instant(metadata['generated_at']) < started:
        raise PendingData('The forecast was not generated by this run')
    if event['phase'] == 'post_fp':
        expected = sorted(expected_practice(event))
        included = sorted(metadata.get('fp_sessions_included', []))
        if included != expected:
            raise PendingData(f'Practice coverage requires {", ".join(expected)}. '
                              f'The model included {", ".join(included) or "no practice sessions"}')
    if event.get('session') == 'SQ' and not metadata.get('sprint_grid_is_actual'):
        raise PendingData('Sprint qualifying grid has not reached the forecast')


def validate_forecast(event, started):
    validate_prediction(event, started)
    payload = read_json(WEB_DATA_DIR / 'predictions.json', {})
    if payload.get('round') != event['round'] or payload.get('phase') != event['phase']:
        raise PendingData('Exported forecast phase does not match the completed session')
    if (instant(payload['simulation_generated_at']) < started
            or len(payload.get('drivers', [])) != 22 or len(payload.get('constructors', [])) != 11
            or len({row['driver_id'] for row in payload['drivers']}) != 22
            or len({row['constructor_id'] for row in payload['constructors']}) != 11):
        raise ValueError('Fresh complete forecast was not generated')
    if event['phase'] == 'post_quali' and not (payload.get('final_fix') or {}).get('qualifying_locked'):
        raise PendingData('Qualifying is not locked in the simulation')
    weather = read_json(WEB_DATA_DIR / 'weather.json', {})
    if weather.get('round') != event['round'] or instant(weather['last_updated']) < started.replace(microsecond=0):
        raise ValueError('Fresh weather for the forecast round was not generated')


def execute(event):
    if event['phase'] == 'post_race':
        auto_post_race.main(['--round', str(event['round'])])
    else:
        from pipeline.run_weekend import run_phase
        started = datetime.now(timezone.utc)
        require_session(event)
        result = run_phase(event['phase'], event['round'], event['race'],
                           after_prediction=lambda: validate_prediction(event, started))
        if result:
            raise RuntimeError(f'{event["phase"]} pipeline failed for round {event["round"]}')
        validate_forecast(event, started)
        print('Verified website forecast at web/public/data/predictions.json', flush=True)
    if event.get('key'):
        state = read_json(STATE_PATH, {'season': CURRENT_SEASON, 'completed': {}})
        state.setdefault('completed', {})[event['key']] = {**event, 'completed_at': datetime.now(timezone.utc).isoformat()}
        write_json(STATE_PATH, state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['auto', 'post_fp', 'post_quali', 'post_race'], default='auto')
    parser.add_argument('--round', type=int)
    parser.add_argument('--plan', '--dry-run', action='store_true', dest='plan_only')
    args = parser.parse_args(argv)
    phase = 'post_race' if args.round and args.phase == 'auto' else args.phase
    event = plan(datetime.now(timezone.utc)) if phase == 'auto' else manual_event(phase, args.round)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'due={str(event is not None).lower()}\n')
    if event is None:
        print('No session update is due. Pipelines were not run.')
        return 0
    print(json.dumps(event, indent=2), flush=True)
    if not args.plan_only:
        execute(event)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except PendingData as exc:
        print(f'PENDING: {exc}; the next schedule check will retry.', file=sys.stderr)
        sys.exit(75)
