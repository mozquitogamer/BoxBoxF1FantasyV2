"""Validate public F1 Fantasy feeds before saving official points and prices.

Run after results download. Incomplete feeds raise PendingData and leave seeds
unchanged. Game-day IDs use the same cancelled-round mapping as Jolpica.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import SEED_DIR, PREDICTIONS_DIR, WEB_DATA_DIR, CURRENT_SEASON, fastf1_round
from config.driver_assets import active_driver_assets

CONSTRUCTOR_IDS = {
    'MER': 'mercedes', 'MCL': 'mclaren', 'RBR': 'red_bull', 'FER': 'ferrari',
    'ALP': 'alpine', 'RBS': 'racing_bulls', 'WIL': 'williams', 'HAA': 'haas',
    'AUD': 'audi', 'AST': 'aston_martin', 'CAD': 'cadillac',
}


class PendingData(ValueError):
    """Results, complete official scoring, or the next price feed is pending."""


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'BoxBoxF1Fantasy/1.0'})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise PendingData(f'Feed is not published yet: {url}') from exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 4:
                raise PendingData(f'Provider is temporarily unavailable ({exc.code})') from exc
            retry_after = exc.headers.get('Retry-After', '') if exc.headers else ''
            delay = min(120, max(15 * (attempt + 1), int(retry_after) if retry_after.isdigit() else 0))
            print(f'Provider requested a retry; waiting {delay}s.', flush=True)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 4:
                raise PendingData('Provider connection is temporarily unavailable') from exc
            time.sleep(15 * (attempt + 1))


def feed_url(round_num):
    return f'https://fantasy.formula1.com/feeds/drivers/{fastf1_round(round_num)}_en.json'


def number(value, label):
    if value is None or value == '' or isinstance(value, bool):
        raise PendingData(f'{label} is not published')
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise PendingData(f'Invalid {label}') from exc
    if not math.isfinite(result):
        raise PendingData(f'Invalid {label}')
    return result


def roster(payload, round_num):
    rows = payload.get('Data', {}).get('Value', [])
    active = [row for row in rows if str(row.get('IsActive')) == '1']
    constructors = {CONSTRUCTOR_IDS[row['DriverTLA']]: row for row in active
                    if row.get('PositionName') == 'CONSTRUCTOR' and row.get('DriverTLA') in CONSTRUCTOR_IDS}
    team_ids = {str(row['TeamId']): cid for cid, row in constructors.items()}
    drivers = {}
    for asset in active_driver_assets(round_num):
        abbreviation = asset['asset_id'].split('_')[0]
        matches = [row for row in active if row.get('PositionName') == 'DRIVER'
                   and row.get('DriverTLA') == abbreviation
                   and team_ids.get(str(row.get('TeamId'))) == asset['constructor_id']]
        if len(matches) != 1:
            raise PendingData(f"Ambiguous official asset {asset['asset_id']}")
        drivers[asset['asset_id']] = matches[0]
    if len(drivers) != 22 or len(constructors) != 11:
        raise PendingData('The official feed does not cover the full field')
    return {'drivers': drivers, 'constructors': constructors}


def validated_snapshot(round_num, race, completed_feed, next_feed=None, next_round=None, previous_feed=None):
    current = roster(completed_feed, round_num)
    points = {'race': race['name'], 'source': feed_url(round_num), 'drivers': {}, 'constructors': {}}
    for group, entries in current.items():
        for asset_id, row in entries.items():
            sessions = row.get('SessionWisePoints') or []
            if not any(str(s.get('sessiontype', '')).lower() == 'race' and s.get('points') is not None for s in sessions):
                raise PendingData(f'Official race scoring for {asset_id} is pending')
            total = number(row.get('GamedayPoints'), f'{asset_id} total')
            components = sum(number(row.get(field), f'{asset_id} {field}') for field in ['QualifyingPoints', 'RacePoints'])
            components += number(row.get('SprintPoints') or 0, f'{asset_id} sprint')
            if abs(total - components) > .001:
                raise PendingData(f'Official components do not sum for {asset_id}')
            points[group][asset_id] = total
    prices = None
    if next_round is not None:
        next_roster = roster(next_feed or {}, next_round)
        if set(next_roster['drivers']) != set(current['drivers']):
            raise PendingData('Next-round roster changed; review the seat mapping first')
        prices = {'drivers': {}, 'constructors': {}}
        for group, entries in next_roster.items():
            for asset_id, row in entries.items():
                price = number(row.get('Value'), f'{asset_id} next price')
                old_price = number(row.get('OldPlayerValue'), f'{asset_id} old price')
                if price <= 0 or abs(old_price - number(current[group][asset_id]['Value'], 'current price')) > .001:
                    raise PendingData(f'Next price feed is not aligned for {asset_id}')
                prices[group][asset_id] = price
    winner = None
    previous_rows = {str(row['PlayerId']): row for row in (previous_feed or {}).get('Data', {}).get('Value', [])}
    winners = []
    for asset_id, row in current['drivers'].items():
        previous = previous_rows.get(str(row['PlayerId']))
        if previous is None:
            continue
        delta = number(row.get('AdditionalStats', {}).get('dotd_pts'), 'DOTD') - number(previous.get('AdditionalStats', {}).get('dotd_pts'), 'prior DOTD')
        if delta == 10:
            winners.append(asset_id.split('_')[0])
        elif delta != 0:
            raise PendingData('Official DOTD totals changed unexpectedly')
    if len(winners) == 1:
        winner = winners[0]
    elif previous_feed:
        raise PendingData('Official DOTD winner is not yet unambiguous')
    return {'points': points, 'prices': prices, 'roster': current, 'dotd_winner': winner}


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def save_seeds(round_num, next_round, snapshot):
    now = datetime.now(timezone.utc).date().isoformat()
    official_path = SEED_DIR / 'official_fantasy_points.json'
    official = json.loads(official_path.read_text(encoding='utf-8'))
    official.setdefault('rounds', {})[str(round_num)] = snapshot['points']
    official['last_updated'] = now
    prices_path = SEED_DIR / 'fantasy_prices.json'
    prices = json.loads(prices_path.read_text(encoding='utf-8'))
    new_prices = snapshot['prices']
    if new_prices:
        # This task processes the newest race. A historical refresh must never
        # roll live prices backwards or silently change the canonical seat set.
        if int(prices.get('price_after_round', 0)) > round_num:
            raise PendingData('Refusing to downgrade newer live prices')
        # Freeze the completed weekend's purchase prices. Historical scoring and
        # forecast checks must not inherit the new prices for the next race.
        overrides = prices.setdefault('round_overrides', {})
        completed_overlay = copy.deepcopy(overrides.get(str(round_num), {}))
        completed_overlay['availability'] = {'from_round': round_num, 'to_round': round_num}
        for group, entries in snapshot['roster'].items():
            frozen = completed_overlay.setdefault(group, {})
            for asset_id, row in entries.items():
                frozen[asset_id] = {**copy.deepcopy(prices[group][asset_id]), **frozen.get(asset_id, {}),
                                    'current_price': number(row['Value'], f'{asset_id} weekend price')}
        overrides[str(round_num)] = completed_overlay
        for group, entries in new_prices.items():
            if set(entries) != set(prices[group]):
                raise PendingData(f'{group} price assets need review')
            for asset_id, price in entries.items():
                prices[group][asset_id]['current_price'] = price
        prices.setdefault('price_history', {})[str(round_num)] = new_prices
        prices.update(price_after_round=round_num, last_updated=now)
        # Carry roster assumptions forward while refreshing persisted overlays.
        candidates = [(int(key), value) for key, value in prices.get('round_overrides', {}).items()
                      if int(key) <= next_round]
        if candidates:
            overlay = copy.deepcopy(max(candidates, key=lambda item: item[0])[1])
            overlay['availability'] = {'from_round': next_round, 'to_round': None}
            overlay['source'] = {'url': feed_url(next_round), 'accessed_at': now}
            for group in ['drivers', 'constructors']:
                for asset_id, entry in overlay.get(group, {}).items():
                    if asset_id in new_prices[group]:
                        entry['current_price'] = new_prices[group][asset_id]
            assumption = overlay.get('price_change_assumption')
            if assumption:
                assumption['round'] = next_round
                start = assumption.get('history_from_round')
                assumption['note'] = (
                    f'Round {next_round} returning-driver price forecasts use the recorded scoring history'
                    f'{f" from Round {start} onwards" if start else ""}. '
                    'F1 Fantasy has not published its substitution pricing rule.'
                )
            overlay['note'] = f'Round {next_round} roster and official purchase prices after Round {round_num}'
            prices['round_overrides'][str(next_round)] = overlay
    dotd_path = SEED_DIR / 'dotd_winners.json'
    dotd = json.loads(dotd_path.read_text(encoding='utf-8'))
    if snapshot['dotd_winner']:
        dotd.setdefault('winners', {})[str(round_num)] = snapshot['dotd_winner']
    elif str(round_num) not in dotd.get('winners', {}):
        raise PendingData('Driver of the Day is not yet known')
    # All validation precedes the first write.
    write_json(official_path, official)
    write_json(prices_path, prices)
    write_json(dotd_path, dotd)
    write_json(PREDICTIONS_DIR / f'round{round_num}' / 'official_feed_snapshot.json', snapshot)


def reconcile_actuals(round_num):
    """Use official session totals to reconcile the computed point breakdown."""
    import csv
    from config.fantasy_scoring import calc_sprint_points_driver
    snapshot_path = PREDICTIONS_DIR / f'round{round_num}' / 'official_feed_snapshot.json'
    if not snapshot_path.exists():
        return
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    path = PREDICTIONS_DIR / f'round{round_num}' / 'actual_fantasy_points.json'
    actual = json.loads(path.read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('actual_calculator', ROOT / 'pipeline/11_actual_fantasy_points.py')
    calculator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calculator)
    # Recompute with the confirmed DOTD winner before deriving overtake counts.
    actual = calculator.calculate_actual_fantasy_points(round_num)
    if actual is None:
        raise PendingData('Computed actuals are missing')
    assets = {a['asset_id'].split('_')[0]: a for a in active_driver_assets(round_num)}
    corrections = []
    sprint_races = calculator.load_jolpica_json(CURRENT_SEASON, round_num, 'sprint.json') or {}
    sprint_results = sprint_races.get('MRData', {}).get('RaceTable', {}).get('Races', [])
    sprint_fl = {r['Driver']['driverId'] for race in sprint_results for r in race.get('SprintResults', [])
                 if str(r.get('FastestLap', {}).get('rank')) == '1'}
    for driver in actual['drivers']:
        asset = assets[driver['driver_id']]
        official = snapshot['roster']['drivers'][asset['asset_id']]
        official_race = number(official['RacePoints'], 'official race points')
        overtakes = official_race - (driver['race_points'] - driver['overtake_points'])
        if overtakes < 0 or not float(overtakes).is_integer():
            raise PendingData(f"Cannot reconcile official race breakdown for {driver['driver_id']}")
        sprint_overtakes = 0
        if actual['is_sprint_weekend']:
            base = calc_sprint_points_driver(
                finish_position=driver.get('sprint_position'), grid_position=driver.get('sprint_grid') or 0,
                is_dnf=driver.get('sprint_position') is None, is_dsq=driver.get('sprint_is_dsq', False),
                is_fastest_lap=asset['model_driver_id'] in sprint_fl,
            )
            sprint_overtakes = number(official.get('SprintPoints') or 0, 'sprint points') - base
            if sprint_overtakes < 0 or not float(sprint_overtakes).is_integer():
                raise PendingData('Cannot reconcile official sprint breakdown')
        corrections.append({'driver_id': asset['model_driver_id'], 'round': round_num,
                            'overtakes_made': int(overtakes), 'positions_gained': max(0, driver['positions_gained']),
                            'positions_lost': max(0, -driver['positions_gained']), 'sprint_positions_gained': 0,
                            'sprint_positions_lost': 0, 'sprint_overtakes': int(sprint_overtakes)})
        driver.update(quali_points=number(official['QualifyingPoints'], 'qualifying points'),
                      race_points=official_race, sprint_points=number(official.get('SprintPoints') or 0, 'sprint points'),
                      overtakes=int(overtakes), overtake_points=int(overtakes), overtake_source='official_session_reconciliation',
                      total_points=number(official['GamedayPoints'], 'total points'))
        driver['ppm'] = round(driver['total_points'] / driver['price'], 2) if driver['price'] else 0
    driver_map = {d['driver_id']: d for d in actual['drivers']}
    pits = {}
    for constructor in actual['constructors']:
        cid = constructor['constructor_id']
        official = snapshot['roster']['constructors'][cid]
        members = [driver_map[constructor[key]] for key in ['driver_1', 'driver_2']]
        constructor['quali_points'] = sum(d['quali_points'] for d in members)
        constructor['quali_bonus'] = number(official['QualifyingPoints'], 'constructor qualifying') - constructor['quali_points']
        constructor['race_points'] = sum(d['race_points'] - d['dotd_points'] for d in members)
        # Constructor race DSQ penalties are already recorded by the calculator.
        dsq = sum(-20 for d in members if d.get('is_dsq'))
        pit_points = number(official['RacePoints'], 'constructor race') - constructor['race_points'] - dsq
        if pit_points < 0 or not float(pit_points).is_integer():
            raise PendingData(f'Cannot reconcile official pit points for {cid}')
        pits[cid] = int(pit_points)
        constructor.update(pitstop_points=int(pit_points), pitstop_source='official_session_reconciliation',
                           sprint_points=number(official.get('SprintPoints') or 0, 'constructor sprint'),
                           total_points=number(official['GamedayPoints'], 'constructor total'))
        constructor['ppm'] = round(constructor['total_points'] / constructor['price'], 2) if constructor['price'] else 0
    csv_path = SEED_DIR / 'overtakes.csv'
    with csv_path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = [row for row in reader if int(row['round']) != round_num]
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([*rows, *corrections])
    pit_path = SEED_DIR / 'pitstop_points.json'
    pit_seed = json.loads(pit_path.read_text(encoding='utf-8'))
    pit_seed.setdefault('rounds', {})[str(round_num)] = pits
    pit_seed['last_updated'] = datetime.now(timezone.utc).date().isoformat()
    write_json(pit_path, pit_seed)
    actual['points_source'] = 'official_f1_fantasy'
    actual['drivers'].sort(key=lambda row: row['total_points'], reverse=True)
    actual['constructors'].sort(key=lambda row: row['total_points'], reverse=True)
    write_json(path, actual)
    write_json(WEB_DATA_DIR / f'actual_round{round_num}.json', actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', type=int, required=True)
    parser.add_argument('--reconcile-actuals', action='store_true')
    args = parser.parse_args()
    if args.reconcile_actuals:
        reconcile_actuals(args.round)
        return
    calendar = json.loads((SEED_DIR / 'races.json').read_text(encoding='utf-8'))['races']
    race = next(r for r in calendar if r['round'] == args.round and not r.get('cancelled'))
    results_path = ROOT / 'data/raw/jolpica' / f'year{CURRENT_SEASON}' / f'round{args.round}' / 'results.json'
    results = json.loads(results_path.read_text(encoding='utf-8'))['MRData']['RaceTable']['Races']
    if len(results) != 1 or results[0].get('date') != race['date'] or len(results[0].get('Results', [])) != 22:
        raise PendingData('Complete race results for the requested calendar event are pending')
    next_race = next((r for r in calendar if r['round'] > args.round and not r.get('cancelled')), None)
    previous = [r for r in calendar if r['round'] < args.round and not r.get('cancelled')]
    snapshot = validated_snapshot(args.round, race, fetch_json(feed_url(args.round)),
        fetch_json(feed_url(next_race['round'])) if next_race else None,
        next_race['round'] if next_race else None,
        fetch_json(feed_url(previous[-1]['round'])) if previous else None)
    save_seeds(args.round, next_race['round'] if next_race else None, snapshot)
    print(f'Official points and prices synchronized for R{args.round}')


if __name__ == '__main__':
    try:
        main()
    except PendingData as exc:
        print(f'PENDING: {exc}', file=sys.stderr)
        sys.exit(75)
