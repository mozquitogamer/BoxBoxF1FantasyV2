import importlib.util
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "16_build_seo_charts.py"
SPEC = importlib.util.spec_from_file_location("build_seo_charts", SCRIPT)
charts = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(charts)


def test_forecast_chart_is_fixed_size_and_visually_nonblank(tmp_path):
    predictions = {
        "race": "Test Grand Prix",
        "season": 2026,
        "generated_at": "2026-07-09T20:41:21Z",
        "drivers": [
            {
                "driver_id": f"D{i}",
                "name": f"Driver {i}",
                "expected_points": 24 - i * 2,
                "mc_total_p5": -10 - i,
                "mc_total_p95": 50 - i,
            }
            for i in range(8)
        ],
    }
    output = tmp_path / "chart.png"

    charts.build_current_forecast_chart(predictions, output)

    with Image.open(output) as image:
        assert image.size == (1200, 630)
        colors = image.convert("RGB").resize((120, 63)).getcolors(maxcolors=120 * 63)
        assert colors is not None
        assert len(colors) > 40
        darkest_share = max(count for count, color in colors if max(color) < 40) / (120 * 63)
        assert darkest_share > 0.5


def test_chart_slug_is_race_specific():
    assert charts.chart_slug("Belgian Grand Prix", 2026) == "belgian-gp-2026-fantasy-forecast.png"


def test_midseason_chart_is_fixed_size_and_uses_recorded_history(tmp_path):
    season = {
        "season": 2026,
        "rounds": [{"round": 1, "name": "Test Grand Prix", "has_actual": True}],
        "driver_prices": {
            f"D{i}": {"name": f"Driver {i}", "current_price": 10 + i, "price_change": i / 10}
            for i in range(8)
        },
        "constructor_prices": {
            f"C{i}": {"name": f"Team {i}", "current_price": 12 + i, "price_change": i / 10}
            for i in range(6)
        },
    }
    history = {
        "season": 2026,
        "drivers": {
            f"D{i}": {"rounds": [{"round": 1, "points": 40 - i * 3}]}
            for i in range(8)
        },
        "constructors": {
            f"C{i}": {"rounds": [{"round": 1, "points": 70 - i * 5}]}
            for i in range(6)
        },
    }
    output = tmp_path / "midseason.png"

    charts.build_midseason_report_chart(season, history, output)

    with Image.open(output) as image:
        assert image.size == (1200, 630)
        colors = image.convert("RGB").resize((120, 63)).getcolors(maxcolors=120 * 63)
        assert colors is not None
        assert len(colors) > 40


def test_season_report_slug_is_descriptive():
    assert charts.season_report_slug(2026) == "f1-fantasy-2026-mid-season-points-value.png"
