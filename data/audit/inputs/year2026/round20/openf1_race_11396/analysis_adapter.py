"""Reproduce R20 analysis from archived OpenF1 observations when FastF1 is absent."""
import bisect
import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
import numpy as np
import pandas as pd

root = Path.cwd()
sys.path.insert(0, str(root))
bundle = root / 'data/audit/inputs/year2026/round20/openf1_race_11396'
data = {name: json.loads((bundle/(name+'.json')).read_bytes()) for name in
        ['sessions','drivers','laps','stints','race_control','position','weather','session_result']}
session = data['sessions'][0]
assert session['session_name'] == 'Race' and session['location'] == 'Austin'
assert session['date_start'].startswith('2026-10-25')
assert any(r.get('message') == 'SESSION FINISHED' for r in data['race_control'])
drivers = {r['driver_number']: r['name_acronym'] for r in data['drivers']}
assert len(drivers) == 22
race_control = sorted(data['race_control'], key=lambda r: r['date'])
intervals, flagged = [], None
for row in race_control:
    message, flag = row.get('message', ''), row.get('flag')
    t = pd.Timestamp(row['date'])
    if message in {'VSC DEPLOYED', 'SAFETY CAR DEPLOYED'} or (row.get('scope') == 'Track' and flag == 'RED'):
        flagged = t if flagged is None else flagged
    elif flagged is not None and row.get('scope') == 'Track' and flag in {'GREEN', 'CLEAR'}:
        intervals.append((flagged, t)); flagged = None
assert flagged is None
positions = {}
for number in drivers:
    rows = sorted([r for r in data['position'] if r['driver_number'] == number], key=lambda r: r['date'])
    positions[number] = ([pd.Timestamp(r['date']) for r in rows], [r['position'] for r in rows])
weather = sorted(data['weather'], key=lambda r: r['date'])
weather_times = [pd.Timestamp(r['date']) for r in weather]
outlaps = {(r['driver_number'], r['lap_number']) for r in data['laps'] if r.get('is_pit_out_lap')}
records = []
for lap in data['laps']:
    n, number = lap['lap_number'], lap['driver_number']
    duration = lap.get('lap_duration')
    if not lap.get('date_start') or duration is None or duration <= 0:
        continue
    start = pd.Timestamp(lap['date_start'])
    end = start + pd.to_timedelta(duration, unit='s')
    stints = [r for r in data['stints'] if r['driver_number'] == number and r['lap_start'] <= n <= r['lap_end']]
    if len(stints) != 1: continue
    stint = stints[0]
    ptime, pvalue = positions[number]
    ix = bisect.bisect_right(ptime, end) - 1
    wi = bisect.bisect_right(weather_times, start) - 1
    weather_row = weather[wi] if wi >= 0 else {}
    records.append({
        'Driver': drivers[number], 'DriverNumber': str(number), 'LapNumber': n,
        'LapTime_seconds': duration,
        **{f'Sector{i}Time_seconds': lap.get(f'duration_sector_{i}') for i in range(1, 4)},
        'SpeedST': lap.get('st_speed'), 'SpeedI1': lap.get('i1_speed'), 'SpeedI2': lap.get('i2_speed'),
        'Stint': stint['stint_number'], 'Compound': stint['compound'],
        'TyreLife': stint['tyre_age_at_start'] + n - stint['lap_start'] + 1 if stint.get('tyre_age_at_start') is not None else np.nan,
        'PitInTime': end if (number, n + 1) in outlaps else pd.NaT,
        'PitOutTime': start if lap.get('is_pit_out_lap') else pd.NaT,
        'TrackStatus': '6' if any(start < b and end > a for a, b in intervals) else '1',
        'Position': pvalue[ix] if ix >= 0 else np.nan,
        'track_temperature': weather_row.get('track_temperature'),
        'air_temperature': weather_row.get('air_temperature'),
        'source': 'openf1', 'session_key': 11396,
    })
frame = pd.DataFrame(records).sort_values(['Driver', 'LapNumber'])
assert frame['Driver'].nunique() == 22 and frame['LapNumber'].max() == 56
assert not frame.duplicated(['Driver', 'LapNumber']).any()
derived = bundle / 'race_laps.parquet'
frame.to_parquet(derived, index=False)
deep = importlib.import_module('pipeline.11_race_deep_dive')
deep.load_race_laps = lambda *a: frame.copy()
deep.run_deep_dive(20, 2026)
post = importlib.import_module('pipeline.09_post_race_analysis')
# Pass only clean observed racing laps to the summary's legacy cleaner.
clean = deep.clean_laps(frame)
clean_path = bundle / 'clean_race_laps.parquet'
clean.to_parquet(clean_path, index=False)
post.load_race_laps = lambda *a: post._load_laps_parquet(clean_path)
post.run_post_race_analysis(20, 2026)
provenance = {'source':'openf1','session_key':11396,'raw_laps':len(data['laps']),
              'timed_laps':len(frame),'clean_laps':len(clean),'drivers':22,
              'neutralized_intervals':[[a.isoformat(), b.isoformat()] for a,b in intervals],
              'missing_values':'Not inferred; optional telemetry remains missing.',
              'sources':{name:{'url':f'https://api.openf1.org/v1/{name}?session_key=11396',
                               'sha256':hashlib.sha256((bundle/(name+'.json')).read_bytes()).hexdigest()}
                         for name in data}}
for filename in ['race_deep_dive.json','post_race_analysis.json']:
    path = root / 'data/predictions/round20' / filename
    result = json.loads(path.read_bytes()); result['telemetry_provenance'] = provenance
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
shutil.copy2(root/'data/predictions/round20/race_deep_dive.json', root/'web/public/data/deep_dive_round20.json')
shutil.copy2(root/'data/predictions/round20/post_race_analysis.json', root/'web/public/data/post_race_round20.json')
(bundle/'analysis_provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8', newline='\n')
if Path(__file__).resolve() != (bundle/'analysis_adapter.py').resolve():
    shutil.copy2(__file__, bundle/'analysis_adapter.py')
print(json.dumps({k:provenance[k] for k in ['source','raw_laps','timed_laps','clean_laps','drivers']}))
