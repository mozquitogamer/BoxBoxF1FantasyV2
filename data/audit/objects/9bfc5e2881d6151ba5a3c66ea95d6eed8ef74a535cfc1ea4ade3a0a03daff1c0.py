"""Restore compact result history needed by predictions on a clean CI checkout."""
import argparse
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import CURRENT_SEASON, HISTORICAL_SEASONS, JOLPICA_RAW_DIR, internal_round_from_api
from pipeline.sync_post_race_official import fetch_json, write_json, PendingData


def fetch_season(year, endpoint):
    """Join pagination by round; a page can end partway through a race."""
    offset = 0
    races = {}
    result_key = {'results': 'Results', 'qualifying': 'QualifyingResults', 'sprint': 'SprintResults'}[endpoint]
    payload = None
    while True:
        page = fetch_json(f'https://api.jolpi.ca/ergast/f1/{year}/{endpoint}.json?limit=2000&offset={offset}')
        if payload is None:
            payload = copy.deepcopy(page)
        received = 0
        for race in page['MRData']['RaceTable']['Races']:
            key = race['round']
            if key not in races:
                races[key] = {**race, result_key: []}
            rows = race.get(result_key, [])
            races[key][result_key].extend(rows)
            received += len(rows)
        offset += received
        if offset >= int(page['MRData']['total']):
            break
        if received == 0:
            raise PendingData(f'Incomplete {year} {endpoint} pagination')
        time.sleep(3)
    payload['MRData']['RaceTable']['Races'] = list(races.values())
    return payload


def bootstrap(through_round):
    # Existing local history is preserved. CI caches these compact source JSONs;
    # the first run must fetch every season before rebuilding rolling features.
    for year in [*HISTORICAL_SEASONS, CURRENT_SEASON]:
        directory = JOLPICA_RAW_DIR / f'year{year}'
        marker = directory / '.automation_history_complete'
        if marker.exists():
            if year != CURRENT_SEASON:
                continue
            try:
                if json.loads(marker.read_text(encoding='utf-8')).get('through_round') == through_round:
                    continue
            except json.JSONDecodeError:
                pass
        for endpoint in ['results', 'qualifying', 'sprint']:
            payload = fetch_season(year, endpoint)
            for race in payload['MRData']['RaceTable']['Races']:
                internal = internal_round_from_api(int(race['round']), year)
                if year == CURRENT_SEASON and internal > through_round:
                    continue
                single = copy.deepcopy(payload)
                single['MRData']['RaceTable']['Races'] = [race]
                write_json(directory / f'round{internal}' / f'{endpoint}.json', single)
            time.sleep(3)
        directory.mkdir(parents=True, exist_ok=True)
        write_json(marker, {'through_round': through_round, 'season': year})
        print(f'Result history ready: {year}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through-round', required=True, type=int)
    bootstrap(parser.parse_args().through_round)
