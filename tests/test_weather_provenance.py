import pytest
from pipeline.weather_provenance import validate_simulation_weather


def test_matching_weather_is_accepted():
    validate_simulation_weather({'weather_features_used': {'source': '2026-10-20T02:42:05Z', 'weather_round': 20}},
                                {'source': '2026-10-20T02:42:05Z', 'round': 20})


@pytest.mark.parametrize('weather', [
    {'source': '2026-10-20T06:42:05Z', 'round': 20},
    {'source': None},
    {'source': '2026-10-20T02:42:05Z', 'round': 21},
    {'source': '2026-10-20T02:42:05Z', 'forecast_snapshot_id': 'changed'},
])
def test_mismatched_weather_blocks_simulation_and_export(weather):
    with pytest.raises(ValueError):
        validate_simulation_weather({'weather_features_used': {
            'source': '2026-10-20T02:42:05Z', 'weather_round': 20, 'forecast_snapshot_id': 'original'}}, weather)


def test_missing_prediction_provenance_is_not_silently_accepted():
    with pytest.raises(ValueError):
        validate_simulation_weather({}, {'source': '2026-10-20T02:42:05Z'})
