"""Audited completed qualifying results, banked points and published grids."""
import json

from config.settings import SEED_DIR, CURRENT_SEASON
from config.driver_assets import active_driver_assets


def load_post_quali_results(round_num, year=CURRENT_SEASON):
    path = SEED_DIR / 'post_quali_results.json'
    if not path.exists():
        return {}
    result = json.loads(path.read_bytes()).get(str(year), {}).get(str(round_num), {})
    if not result:
        return {}
    drivers = result['drivers']
    active = active_driver_assets(round_num, year)
    if set(drivers) != {d['model_driver_id'] for d in active}:
        raise ValueError('Official qualifying roster does not match the active field')
    for key in ['position', 'grid']:
        if sorted(d[key] for d in drivers.values()) != list(range(1, len(active) + 1)):
            raise ValueError(f'Incomplete or duplicated official qualifying {key}')
    if set(result['constructors']) != {d['constructor_id'] for d in active}:
        raise ValueError('Incomplete banked constructor qualifying points')
    return result
