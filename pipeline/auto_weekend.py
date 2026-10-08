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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import CURRENT_SEASON, SEED_DIR, WEB_DATA_DIR, PREDICTIONS_DIR, FASTF1_RAW_DIR
from pipeline import auto_post_race
from pipeline.sync_post_race_official import PendingData, fetch_json, write_json

STATE_PATH = ROOT / 'data/automation/weekend_state.json'
SESSION_CODES = {'Practice 1': 'FP1', 'Practice 2': 'FP2', 'Practice 3': 'FP3',
                 'Sprint Qualifying': 'SQ', 'Qualifying': 'Qualifying', 'Race': 'Race'}


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


def plan(now):
    calendar = read_json(SEED_DIR / 'races.json', {})['races']
    if not any(not race.get('cancelled') and now.date() - timedelta(days=7) <=
               datetime.fromisoformat(race['date']).date() <= now.date() + timedelta(days=4)
               for race in calendar):
        return None
    sessions = fetch_json(f'https://api.openf1.org/v1/sessions?year={CURRENT_SEASON}')
    if not isinstance(sessions, list) or not sessions:
        raise PendingData('Session schedule is unavailable')
    return select_due(calendar, sessions, read_json(STATE_PATH, {}),
                      read_json(auto_post_race.STATE_PATH, {}),
                      read_json(WEB_DATA_DIR / 'predictions.json', {}).get('round', 0), now,
                      lambda key: fetch_json(f'https://api.openf1.org/v1/race_control?session_key={key}&category=SessionStatus'))


def manual_event(phase, round_num):
    calendar = read_json(SEED_DIR / 'races.json', {})['races']
    if phase == 'post_race' and round_num is None:
        candidates = auto_post_race.candidate_races(calendar, datetime.now(timezone.utc))
        if not candidates:
            raise ValueError('No recent race; enter an internal calendar round')
        round_num = candidates[0]['round']
    if round_num is None:
        round_num = read_json(WEB_DATA_DIR / 'predictions.json', {})['round']
    race = next((r for r in calendar if r['round'] == round_num and not r.get('cancelled')), None)
    if race is None:
        raise ValueError('Unknown or cancelled round')
    return {'round': round_num, 'phase': phase, 'race': race['name'], 'manual': True,
            'session': 'Qualifying' if phase == 'post_quali' else None}


def load_script(name):
    spec = importlib.util.spec_from_file_location('weekend_' + name[:2], ROOT / 'pipeline' / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require_session(event):
    """A downloader process can succeed while its upstream data is still missing."""
    code = event.get('session')
    if not code:
        return
    import fastf1
    from config.settings import FASTF1_CACHE_DIR, fastf1_round
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR), force_renew=True)
    if not load_script('01_download_data.py').download_fastf1_session(
            CURRENT_SEASON, event['round'], code,
            FASTF1_RAW_DIR / f'year{CURRENT_SEASON}' / f'round{event["round"]}'):
        raise PendingData(f'{code} telemetry is not available yet')
    if code == 'Qualifying':
        session = fastf1.get_session(CURRENT_SEASON, fastf1_round(event['round']), 'Qualifying')
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results
        if results is None or len(results) != 22 or results['Position'].isna().any() or set(results['Position'].astype(int)) != set(range(1, 23)):
            raise PendingData('Complete qualifying classification is not available yet')


def validate_forecast(event, started):
    payload = read_json(WEB_DATA_DIR / 'predictions.json', {})
    metadata = read_json(PREDICTIONS_DIR / f'round{event["round"]}' / 'prediction_metadata.json', {})
    if payload.get('round') != event['round'] or payload.get('phase') != event['phase'] or metadata.get('phase') != event['phase'] or metadata.get('round') != event['round']:
        raise PendingData('Forecast phase does not match the completed session')
    if (instant(metadata['generated_at']) < started or instant(payload['simulation_generated_at']) < started
            or len(payload.get('drivers', [])) != 22 or len(payload.get('constructors', [])) != 11
            or len({row['driver_id'] for row in payload['drivers']}) != 22
            or len({row['constructor_id'] for row in payload['constructors']}) != 11):
        raise ValueError('Fresh complete forecast was not generated')
    if (event.get('session') or '').startswith('FP') and event['session'] not in metadata.get('fp_sessions_included', []):
        raise PendingData('New practice telemetry has not reached the forecast')
    if event.get('session') == 'SQ' and not metadata.get('sprint_grid_is_actual'):
        raise PendingData('Sprint qualifying grid has not reached the forecast')
    if event['phase'] == 'post_quali' and not (payload.get('final_fix') or {}).get('qualifying_locked'):
        raise PendingData('Qualifying is not locked in the simulation')
    weather = read_json(WEB_DATA_DIR / 'weather.json', {})
    if weather.get('round') != event['round'] or instant(weather['last_updated']) < started.replace(microsecond=0):
        raise ValueError('Fresh weather for the forecast round was not generated')


def execute(event):
    started = datetime.now(timezone.utc)
    if event['phase'] == 'post_race':
        auto_post_race.main(['--round', str(event['round'])])
    else:
        require_session(event)
        auto_post_race.run('weather_forecast.py', '--round', event['round'])
        auto_post_race.run('run_weekend.py', '--phase', event['phase'], '--round', event['round'])
        validate_forecast(event, started)
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
