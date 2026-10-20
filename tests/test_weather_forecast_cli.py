from pipeline import weather_forecast


def test_failed_refresh_stops_the_pipeline(monkeypatch):
    monkeypatch.setattr(weather_forecast, 'run_weather_forecast', lambda _: {})
    assert weather_forecast.main(['--round', '20']) == 1


def test_successful_refresh_allows_the_pipeline(monkeypatch):
    monkeypatch.setattr(weather_forecast, 'run_weather_forecast', lambda _: {'round': 20})
    assert weather_forecast.main(['--round', '20']) == 0
