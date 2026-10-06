"""Settle a recent completed race and prepare its next-round forecast.

This command can be invoked by a scheduler. It does not commit or push files.
Incomplete official feeds return 75; only verified outputs receive a success
marker. A source fingerprint picks up corrections without repeated simulations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import CURRENT_SEASON, SEED_DIR, WEB_DATA_DIR, PREDICTIONS_DIR, fastf1_round
from pipeline.sync_post_race_official import fetch_json, feed_url, validated_snapshot, PendingData, write_json

STATE_PATH = ROOT / 'data/automation/post_race_state.json'


def candidate_races(calendar, now):
    cutoff = (now - timedelta(days=7)).date().isoformat()
    return sorted([race for race in calendar if not race.get('cancelled')
                   and cutoff <= race['date'] <= now.date().isoformat()], key=lambda race: race['date'], reverse=True)


def validate_results(payload, race):
    results = payload.get('MRData', {}).get('RaceTable', {}).get('Races', [])
    if not results:
        raise PendingData(f"R{race['round']} results are pending")
    result = results[0]
    if len(results) != 1 or result.get('date') != race['date'] or str(result.get('round')) != str(fastf1_round(race['round'])):
        raise ValueError('Results do not match the requested calendar event')
    rows = result.get('Results', [])
    if len(rows) != 22 or len({row['Driver']['driverId'] for row in rows}) != 22:
        raise PendingData('Full race classification is pending')
    return result


def validate_outputs(round_num):
    actual = json.loads((WEB_DATA_DIR / f'actual_round{round_num}.json').read_text(encoding='utf-8'))
    official = json.loads((SEED_DIR / 'official_fantasy_points.json').read_text(encoding='utf-8'))['rounds'][str(round_num)]
    if actual.get('round') != round_num or actual.get('points_source') != 'official_f1_fantasy':
        raise ValueError('Official actuals were not published')
    for group, key in [('drivers', 'driver_id'), ('constructors', 'constructor_id')]:
        totals = {row[key]: row['total_points'] for row in actual[group]}
        if totals != official[group]:
            raise ValueError(f'{group} actuals differ from the official source')


def restore_public_actuals():
    for path in WEB_DATA_DIR.glob('actual_round*.json'):
        payload = json.loads(path.read_text(encoding='utf-8'))
        destination = PREDICTIONS_DIR / f"round{payload['round']}" / 'actual_fantasy_points.json'
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def run(script, *args):
    subprocess.run([sys.executable, str(ROOT / 'pipeline' / script), *map(str, args)], cwd=ROOT, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', type=int, help='Manually process a specific round')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    calendar = json.loads((SEED_DIR / 'races.json').read_text(encoding='utf-8'))['races']
    candidates = candidate_races(calendar, now)
    if args.round:
        candidates = [race for race in calendar if race['round'] == args.round and not race.get('cancelled')]
        if not candidates or candidates[0]['date'] > now.date().isoformat():
            raise ValueError('Requested round is cancelled, unknown, or has not raced yet')
    if not candidates:
        print('No recent race is due for a post-race update.')
        return 0
    race = candidates[0]
    round_num = race['round']
    next_race = next((r for r in calendar if r['round'] > round_num and not r.get('cancelled')), None)
    previous = [r for r in calendar if r['round'] < round_num and not r.get('cancelled')]
    results = fetch_json(f'https://api.jolpi.ca/ergast/f1/{CURRENT_SEASON}/{fastf1_round(round_num)}/results.json?limit=100')
    validate_results(results, race)
    snapshot = validated_snapshot(round_num, race, fetch_json(feed_url(round_num)),
        fetch_json(feed_url(next_race['round'])) if next_race else None,
        next_race['round'] if next_race else None,
        fetch_json(feed_url(previous[-1]['round'])) if previous else None)
    fingerprint = hashlib.sha256(json.dumps({'results': results, 'snapshot': snapshot}, sort_keys=True).encode()).hexdigest()
    state = json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {'season': CURRENT_SEASON, 'rounds': {}}
    live = json.loads((WEB_DATA_DIR / 'predictions.json').read_text(encoding='utf-8'))
    previous_state = state.get('rounds', {}).get(str(round_num), {})
    needs_next = next_race is not None and int(live['round']) < next_race['round']
    if previous_state.get('source_sha256') == fingerprint and not needs_next:
        validate_outputs(round_num)
        print(f'R{round_num} is already settled; no source changes.')
        return 0
    print(f"Post-race update: R{round_num} {race['name']}", flush=True)
    if args.dry_run:
        print(f"Validated official feeds. Next forecast: R{next_race['round'] if next_race else 'season complete'}")
        return 0
    restore_public_actuals()
    run('run_weekend.py', '--phase', 'post_race', '--round', round_num)
    validate_outputs(round_num)
    if needs_next:
        # Restore result history before the pre-FP phase rebuilds priors.
        run('bootstrap_result_history.py', '--through-round', round_num)
        run('weather_forecast.py', '--round', next_race['round'])
        run('run_weekend.py', '--phase', 'pre_fp_predict', '--round', next_race['round'])
        fresh = json.loads((WEB_DATA_DIR / 'predictions.json').read_text(encoding='utf-8'))
        if fresh.get('round') != next_race['round'] or fresh.get('phase') != 'pre_fp' or len(fresh.get('drivers', [])) != 22 or len(fresh.get('constructors', [])) != 11:
            raise ValueError('Next-round forecast did not export correctly')
    state.setdefault('rounds', {})[str(round_num)] = {
        'race': race['name'], 'source_sha256': fingerprint,
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'next_round': next_race['round'] if next_race else None,
    }
    write_json(STATE_PATH, state)
    print(f'R{round_num} settled and next-round state verified.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except PendingData as exc:
        print(f'PENDING: {exc}; a scheduler should retry.', file=sys.stderr)
        sys.exit(75)
