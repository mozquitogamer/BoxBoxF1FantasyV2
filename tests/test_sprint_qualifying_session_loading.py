"""Completed Sprint Qualifying must use segment classification and the refreshed cache."""
import importlib
from types import SimpleNamespace
import numpy as np
import pandas as pd
import fastf1

predictions = importlib.import_module("pipeline.06_run_predictions")


def test_downloaded_sprint_qualifying_preserves_segment_order(monkeypatch, tmp_path):
    from config import settings
    cache = tmp_path / 'cache'
    monkeypatch.setattr(settings, 'FASTF1_CACHE_DIR', cache)
    monkeypatch.setattr(predictions, 'JOLPICA_MODEL_ROWS_DIR', tmp_path / 'model_rows')
    monkeypatch.setattr(predictions, 'load_driver_id_maps',
                        lambda: ({'AAA': 'a', 'BBB': 'b', 'CCC': 'c'}, {}))
    configured = []
    monkeypatch.setattr(fastf1.Cache, 'enable_cache', lambda directory: configured.append(directory))

    class Session:
        results = pd.DataFrame({'Abbreviation': ['AAA', 'BBB', 'CCC'],
                                'Position': [np.nan] * 3})
        # AAA has an earlier-segment lap faster than BBB, but BBB qualified P1.
        laps = pd.DataFrame({'Driver': ['AAA', 'BBB', 'CCC'],
                             'LapTime': pd.to_timedelta([90, 91, 92], unit='s')})

        def load(self, **options):
            assert configured == [str(cache)]
            if options.get('messages'):
                self.results = self.results.assign(Position=[2.0, 1.0, 3.0])

    def get_session(year, round_num, name):
        assert (year, round_num) == (2026, 17)
        if name == 'Sprint Shootout':
            raise ValueError('Session uses its current name')
        return Session()

    monkeypatch.setattr(fastf1, 'get_session', get_session)
    frame = pd.DataFrame({'driver_id': ['a', 'b', 'c']})
    assert predictions._load_actual_sprint_grid(frame, 19, 2026)
    assert frame['sprint_grid'].tolist() == [2.0, 1.0, 3.0]
