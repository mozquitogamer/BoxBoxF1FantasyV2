import importlib.util
import json
import re
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "14_build_seo_pages.py"
SPEC = importlib.util.spec_from_file_location("build_seo_pages", SCRIPT)
seo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(seo)


def current_predictions():
    return {
        "race": "Test Grand Prix",
        "drivers": [
            {"driver_id": "A", "name": "Driver A", "current_price": 10, "expected_points": 0, "projected_points": 100},
            {"driver_id": "B", "name": "Driver B", "current_price": 10, "expected_points": 60, "projected_points": 0},
            {"driver_id": "C", "name": "Driver C", "current_price": 10, "expected_points": 20, "projected_points": 20},
            {"driver_id": "D", "name": "Driver D", "current_price": 10, "expected_points": 18, "projected_points": 18},
            {"driver_id": "E", "name": "Driver E", "current_price": 10, "expected_points": 16, "projected_points": 16},
            {"driver_id": "F", "name": "Driver F", "current_price": 10, "expected_points": 1, "projected_points": 1},
        ],
        "constructors": [
            {"constructor_id": "X", "name": "Team X", "current_price": 10, "expected_points": 20, "projected_points": 20},
            {"constructor_id": "Y", "name": "Team Y", "current_price": 10, "expected_points": 18, "projected_points": 18},
            {"constructor_id": "Z", "name": "Team Z", "current_price": 10, "expected_points": 1, "projected_points": 1},
        ],
    }


def race_week_predictions():
    pred = current_predictions()
    pred.update({
        "round": 12,
        "date": "2026-07-19",
        "circuit": "Circuit de Spa-Francorchamps",
        "phase": "pre_fp",
        "generated_at": "2026-07-09T20:41:21Z",
    })
    for i, driver in enumerate(pred["drivers"]):
        driver["value_score"] = 1.5 - i * 0.1
        driver["mc_total_p5"] = -10 - i
        driver["mc_total_p95"] = 40 + i
        driver["dnf_probability"] = 0.05 + i * 0.02
        driver["constructor"] = "X"
        driver["predicted_quali"] = i + 1
        driver["predicted_finish"] = i + 1
    for constructor in pred["constructors"]:
        constructor["value_score"] = 1.0
        constructor["expected_pit_stop_pts"] = 3.0
    return pred


def test_suggested_lineup_matches_balanced_basis_and_normal_boost():
    lineup = seo.suggested_lineup(current_predictions())
    assert lineup is not None
    assert lineup["captain"]["driver_id"] == "A"
    assert [d["driver_id"] for d in lineup["drivers"]] == ["A", "B", "C", "D", "E"]
    assert [c["constructor_id"] for c in lineup["constructors"]] == ["X", "Y"]
    assert lineup["cost"] == 70
    assert lineup["points"] == 222


def test_optimizer_snapshot_is_current_linked_and_explains_basis():
    html = seo.suggested_lineup_html(current_predictions())
    assert "Current optimized team: Test Grand Prix" in html
    assert "Balanced" in html
    assert "Optimized team total:</strong> 222.0" in html
    assert 'href="/drivers/driver-a/"' in html
    assert 'href="/constructors/team-x/"' in html


def test_optimizer_page_includes_current_snapshot_and_item_list_schema():
    optimizer = next(item for item in seo.TOOLS if item["slug"] == "lineup-optimizer")
    html = seo.render_content_page(optimizer, current_predictions())
    assert "Free F1 Fantasy Team Optimizer 2026" in html
    assert "Current optimized team: Test Grand Prix" in html
    assert '"@type": "ItemList"' in html
    assert "Optimized F1 Fantasy team for Test Grand Prix" in html


def test_guide_modified_date_uses_controlled_content_date():
    guide = seo.GUIDES[0]
    assert seo.guide_article_ld(guide, "https://example.com/guide/")["dateModified"] == seo.SEO_CONTENT_LASTMOD


def test_current_race_page_is_phase_honest_and_explains_autopilot():
    _slug, html = seo.render_race_page(race_week_predictions(), True)
    assert "Pre-practice forecast" in html
    assert "No current-weekend free-practice telemetry is included yet" in html
    assert "July 18, 2026 14:00 UTC" in html
    assert "Autopilot</strong> instead protects you by applying 2x to your best actual scorer" in html
    assert "updated through race week" not in html


def test_race_rankings_link_profiles_and_item_lists_target_entities():
    _slug, html = seo.render_race_page(race_week_predictions(), True)

    assert '<a href="/drivers/driver-b/">Driver B</a>' in html
    assert '<a href="/constructors/team-x/">Team X</a>' in html
    ld_match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        html,
        re.DOTALL,
    )
    assert ld_match is not None
    objects = json.loads(ld_match.group(1))
    item_lists = [obj for obj in objects if obj.get("@type") == "ItemList"]
    assert len(item_lists) == 2
    driver_urls = [item["url"] for item in item_lists[0]["itemListElement"]]
    constructor_urls = [item["url"] for item in item_lists[1]["itemListElement"]]
    assert "https://boxboxf1fantasy.com/drivers/driver-b/" in driver_urls
    assert "https://boxboxf1fantasy.com/constructors/team-x/" in constructor_urls
    assert all("/picks/test-gp-2026/" not in url for url in driver_urls + constructor_urls)
    article = next(obj for obj in objects if obj.get("@type") == "Article")
    assert article["author"]["name"] == "BoxBoxF1Fantasy"


def test_current_weather_distinguishes_latest_feed_from_model_snapshot():
    pred = race_week_predictions()
    pred["race"] = "Belgian Grand Prix"
    pred["weather_adjustments"] = {
        "is_active": True,
        "rain_risk": "MEDIUM",
        "source": "2026-07-09T19:22:55Z",
    }
    weather = {
        "round": 12,
        "overall_rain_risk": "HIGH",
        "last_updated": "2026-07-12T18:51:57Z",
        "sessions": [
            {"name": "FP2", "rain_probability": 71, "rain_risk": "HIGH", "avg_temp": 20.6, "weather_description": "Light drizzle"},
            {"name": "Qualifying", "rain_probability": 42, "rain_risk": "MEDIUM", "avg_temp": 20.5, "weather_description": "Mainly clear"},
            {"name": "Race", "rain_probability": 22, "rain_risk": "LOW", "avg_temp": 18.1, "weather_description": "Partly cloudy"},
        ],
    }

    html = seo.current_weather_html(pred, weather)

    assert "Belgian GP weather outlook" in html
    assert "FP2:</strong> 71% rain probability" in html
    assert "Race:</strong> 22% rain probability" in html
    assert "earlier medium-risk weather snapshot from July 9, 2026" in html
    assert "newer forecast has not yet been applied" in html
    assert "/data/weather.json" in html
