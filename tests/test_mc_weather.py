"""Weather-widener calibration and loader regression tests."""

import importlib
import json


mc = importlib.import_module("pipeline.08_monte_carlo_fantasy")


def test_weather_bucket_tunables_are_toned_and_monotonic():
    expected = {
        "NONE": (1.00, 1.00, 0.00),
        "LOW": (1.02, 1.05, 0.01),
        "MEDIUM": (1.08, 1.13, 0.03),
        "HIGH": (1.15, 1.25, 0.05),
    }
    observed = {}
    for risk, values in mc.MC_WEATHER_TUNABLES["rain"].items():
        observed[risk] = (
            values["noise_mult"], values["dnf_mult"], values["wet_weight"]
        )
    assert observed == expected
    for index in range(3):
        assert [observed[r][index] for r in expected] == sorted(
            observed[r][index] for r in expected
        )


def test_race_session_risk_overrides_overall_and_resolves_temperature(tmp_path, monkeypatch):
    weather = {
        "round": 12,
        "last_updated": "test",
        "overall_rain_risk": "HIGH",
        "sessions": [
            {"name": "Qualifying", "rain_risk": "HIGH", "avg_temp": 22.0},
            {"name": "Race", "rain_risk": "MEDIUM", "avg_temp": 18.8},
        ],
    }
    (tmp_path / "weather.json").write_text(json.dumps(weather), encoding="utf-8")
    monkeypatch.setattr(mc, "WEB_DATA_DIR", tmp_path)

    result = mc.load_weather_for_mc(12)

    assert result["rain_risk"] == "MEDIUM"
    assert result["noise_mult"] == 1.08
    assert result["dnf_mult"] == 1.13
    assert result["wet_weight"] == 0.03
    assert result["cold_weight"] == 0.01
    assert result["is_active"] is True


def test_stale_weather_file_is_neutral(tmp_path, monkeypatch):
    weather = {
        "round": 11,
        "overall_rain_risk": "HIGH",
        "sessions": [{"name": "Race", "rain_risk": "HIGH", "avg_temp": 10.0}],
    }
    (tmp_path / "weather.json").write_text(json.dumps(weather), encoding="utf-8")
    monkeypatch.setattr(mc, "WEB_DATA_DIR", tmp_path)

    result = mc.load_weather_for_mc(12)

    assert result["rain_risk"] == "NONE"
    assert result["noise_mult"] == 1.0
    assert result["dnf_mult"] == 1.0
    assert result["is_active"] is False
