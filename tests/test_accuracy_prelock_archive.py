import json
from pathlib import Path
from pipeline.forecast_archive import load_lock_forecast, fantasy_lock_utc

def _save(path, *, phase, generated):
    path.write_text(json.dumps({"round":17,"phase":phase,"generated_at":generated,"exported_at":generated}),encoding="utf-8")

def test_immutable_snapshot_recovers_last_prelock_forecast(tmp_path):
    audit = tmp_path / 'audit'
    folder = audit / 'round17'
    folder.mkdir(parents=True)
    path = folder / 'last_fp3.json'
    forecast = {'round': 17, 'phase': 'post_fp', 'generated_at': '2026-09-25T11:30:00Z',
                'exported_at': '2026-09-25T11:31:00Z'}
    path.write_text(json.dumps({'round': 17, 'phase': 'post_fp', 'predictions': forecast,
                               'prediction_metadata': {'generated_at': '2026-09-25T11:29:00Z'}}))
    _save(tmp_path / 'predictions_round17_post_fp.json', phase='post_fp', generated='2026-09-24T10:00:00Z')
    assert load_lock_forecast(17, tmp_path, audit_dir=audit)[1] == path
    forecast['reconstructed'] = True
    path.write_text(json.dumps({'predictions': forecast}))
    assert load_lock_forecast(17, tmp_path, audit_dir=audit)[1].name == 'predictions_round17_post_fp.json'


def test_roster_rejects_wrong_seat_incomplete_and_duplicate_aliases():
    from pipeline.forecast_archive import matching_roster
    actual = {'drivers': [{'driver_id': 'LAW', 'constructor': 'red_bull'}],
              'constructors': [{'constructor_id': 'red_bull'}]}
    forecast = {'drivers': [{'driver_id': 'LAW_RED_BULL', 'asset_legacy_ids': ['LAW'],
                             'constructor': 'red_bull', 'expected_points': 0}],
                'constructors': [{'constructor_id': 'red_bull', 'expected_points': -2}]}
    assert matching_roster(forecast, actual)
    forecast['drivers'][0]['constructor'] = 'racing_bulls'
    assert not matching_roster(forecast, actual)
    forecast['drivers'] = []
    assert not matching_roster(forecast, actual)


def test_recovered_real_rounds_and_review_metrics_are_complete():
    from pipeline.forecast_archive import build_accuracy_prelock_index
    data = Path(__file__).resolve().parents[1] / 'web/public/data'
    index = build_accuracy_prelock_index(data)
    assert set(range(7, 19)).issubset({r['round'] for r in index['rounds']})
    for row in index['rounds']:
        assert len(row['forecast']['drivers']) == 22
        assert len(row['forecast']['constructors']) == 11
    assert {1, 2, 3, 6}.issubset(set(index['excluded_rounds']))
