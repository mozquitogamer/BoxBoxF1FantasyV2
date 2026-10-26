"""The accuracy baseline must be the last genuine forecast before team lock."""

import json
from pathlib import Path

from pipeline.forecast_archive import (
    fantasy_lock_utc,
    load_lock_forecast,
    load_prelock_forecast,
)


def _save(path: Path, *, phase: str, generated: str, exported: str | None = None):
    path.write_text(json.dumps({
        "round": 17,
        "phase": phase,
        "generated_at": generated,
        "exported_at": exported or generated,
        "drivers": [],
    }), encoding="utf-8")


def test_latest_post_fp_before_real_lock_beats_fridays_first_archive(tmp_path):
    phase = tmp_path / "predictions_round17_post_fp.json"
    latest = tmp_path / "predictions_round17.json"
    _save(phase, phase="post_fp", generated="2026-09-24T10:08:09Z")
    _save(latest, phase="post_fp", generated="2026-09-25T11:25:19Z")
    assert fantasy_lock_utc(17).isoformat() == "2026-09-25T12:00:00+00:00"
    payload, path = load_lock_forecast(17, tmp_path)
    assert path == latest
    assert payload["generated_at"] == "2026-09-25T11:25:19Z"


def test_hindsight_or_unknown_deadline_cannot_enter_actionable_history(tmp_path):
    phase = tmp_path / "predictions_round17_post_fp.json"
    latest = tmp_path / "predictions_round17.json"
    _save(phase, phase="post_fp", generated="2026-09-24T10:08:09Z")

    _save(latest, phase="post_fp", generated="2026-09-25T12:01:00Z")
    assert load_lock_forecast(17, tmp_path)[1] == phase

    _save(latest, phase="post_quali", generated="2026-09-25T11:00:00Z")
    assert load_lock_forecast(17, tmp_path)[1] == phase

    _save(latest, phase="post_fp", generated="2026-09-25T11:00:00Z")
    assert load_lock_forecast(17, tmp_path, lock_source=tmp_path / "missing.js") is None

    _save(phase, phase="post_fp", generated="2026-09-25T12:02:00Z")
    _save(latest, phase="post_fp", generated="2026-09-25T12:03:00Z")
    assert load_lock_forecast(17, tmp_path) is None


def test_canonical_can_predate_retrospectively_backfilled_phase(tmp_path):
    _save(tmp_path / "predictions_round17_post_fp.json", phase="post_fp",
          generated="2026-09-27T18:00:00Z")
    canonical = tmp_path / "predictions_round17.json"
    _save(canonical, phase="post_fp", generated="2026-09-25T11:00:00Z")
    assert load_lock_forecast(17, tmp_path)[1] == canonical


def test_prefp_archive_must_also_precede_lock(tmp_path):
    phase = tmp_path / "predictions_round17_pre_fp.json"
    _save(phase, phase="pre_fp", generated="2026-09-25T11:00:00Z")
    assert load_prelock_forecast(17, tmp_path, phase="pre_fp")[1] == phase
    _save(phase, phase="pre_fp", generated="2026-09-25T12:01:00Z")
    assert load_prelock_forecast(17, tmp_path, phase="pre_fp") is None


def test_real_archives_respect_timestamp_provenance():
    data = Path(__file__).resolve().parents[1] / "web/public/data"
    for round_num in (8, 9, 11, 12, 14, 16, 17):
        payload, path = load_lock_forecast(round_num, data)
        assert payload["exported_at"] <= fantasy_lock_utc(round_num).isoformat()
        assert payload["phase"] == "post_fp"
    for round_num in (6,):
        assert load_lock_forecast(round_num, data) is None


def test_official_points_join_midseason_asset_aliases():
    from pipeline.backtest_forecast import _driver_forecast_map

    forecasts = {"drivers": [{
        "driver_id": "LAW_RED_BULL",
        "asset_legacy_ids": ["LAW"],
        "constructor": "red_bull",
        "expected_points": 20.0,
        "mc_total_p5": -5.0,
        "mc_total_p95": 42.0,
    }]}
    scored = _driver_forecast_map(forecasts, {"LAW": "red_bull"})
    assert scored["LAW"] == scored["LAW_RED_BULL"]
    assert "LAW" not in _driver_forecast_map(forecasts, {"LAW": "racing_bulls"})


def test_backtest_uses_latest_prelock_refresh_instead_of_late_canonical(tmp_path, monkeypatch):
    from pipeline import backtest_forecast as backtest

    monkeypatch.setattr(backtest, 'WEB_DATA_DIR', tmp_path)
    _save(tmp_path / 'predictions_round17_post_fp.json', phase='post_fp',
          generated='2026-09-24T10:00:00Z')
    _save(tmp_path / 'predictions_round17_post_fp_refresh_latest.json', phase='post_fp',
          generated='2026-09-25T11:30:00Z')
    _save(tmp_path / 'predictions_round17.json', phase='post_fp',
          generated='2026-09-25T12:01:00Z')

    forecast, phase = backtest.load_forecast(17, 'post_fp')

    assert phase == 'post_fp'
    assert forecast['generated_at'] == '2026-09-25T11:30:00Z'


def test_backtest_falls_back_to_prelock_prefp_but_never_late_exports(tmp_path, monkeypatch):
    from pipeline import backtest_forecast as backtest

    monkeypatch.setattr(backtest, 'WEB_DATA_DIR', tmp_path)
    _save(tmp_path / 'predictions_round17_post_fp.json', phase='post_fp',
          generated='2026-09-25T11:30:00Z', exported='2026-09-25T12:01:00Z')
    early = tmp_path / 'predictions_round17_pre_fp.json'
    _save(early, phase='pre_fp', generated='2026-09-24T08:00:00Z')

    assert backtest.load_forecast(17, 'post_fp')[1] == 'pre_fp'

    _save(early, phase='pre_fp', generated='2026-09-24T08:00:00Z',
          exported='2026-09-25T12:01:00Z')
    assert backtest.load_forecast(17, 'post_fp') == ({}, None)
    assert backtest.load_forecast(17, 'pre_fp') == ({}, None)


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
