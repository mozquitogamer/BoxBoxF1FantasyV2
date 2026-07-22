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


def test_guides_publish_visible_brand_byline_and_author_profile():
    guide = seo.GUIDES[0]
    html = seo.render_content_page(guide, race_week_predictions())

    assert 'By <a href="/about/" rel="author">BoxBoxF1Fantasy</a>' in html
    assert 'href="/methodology/">How this analysis is made</a>' in html
    assert seo.guide_article_ld(guide, "https://example.com/guide/")["author"]["url"] == "https://boxboxf1fantasy.com/about/"


def test_current_race_page_is_phase_honest_and_explains_autopilot():
    _slug, html = seo.render_race_page(race_week_predictions(), True)
    assert 'By <a href="/about/" rel="author">BoxBoxF1Fantasy</a>' in html
    assert 'href="/methodology/">How this analysis is made</a>' in html
    assert '"author": {' in html
    assert '"url": "https://boxboxf1fantasy.com/about/"' in html
    assert "Pre-practice forecast" in html
    assert "No current-weekend free-practice telemetry is included yet" in html
    assert "July 18, 2026 14:00 UTC" in html
    assert "Autopilot</strong> instead protects you by applying 2x to your best actual scorer" in html
    assert "updated through race week" not in html


def test_completed_race_page_leads_with_results_and_labels_forecast_archive():
    prediction = race_week_predictions()
    prediction["date"] = "2026-07-19"
    actual = {
        "round": 12,
        "race": "Test Grand Prix",
        "drivers": [
            {
                "driver_id": "B", "name": "Driver B", "constructor": "X",
                "quali_position": 2, "race_position": 1, "positions_gained": 1,
                "overtakes": 4, "total_points": 52, "ppm": 2.6,
            },
            {
                "driver_id": "A", "name": "Driver A", "constructor": "Y",
                "quali_position": 1, "race_position": 4, "positions_gained": -3,
                "overtakes": 1, "total_points": 8, "ppm": 0.8,
            },
        ],
        "constructors": [
            {
                "constructor_id": "X", "name": "Team X", "quali_points": 15,
                "race_points": 50, "sprint_points": 0, "pitstop_points": 5,
                "total_points": 70, "ppm": 2.8,
            },
            {
                "constructor_id": "Y", "name": "Team Y", "quali_points": 10,
                "race_points": 40, "sprint_points": 0, "pitstop_points": 2,
                "total_points": 52, "ppm": 2.1,
            },
        ],
    }

    _slug, html = seo.render_race_page(prediction, False, actual=actual)

    assert "F1 Fantasy Test GP 2026 Results &amp; Review" in html
    assert "F1 Fantasy Results: Test Grand Prix 2026" in html
    assert "Driver B led the driver scoring with 52 points" in html
    assert 'aria-label="Recorded driver fantasy results"' in html
    assert 'aria-label="Recorded constructor fantasy results"' in html
    assert "Forecast top-five overlap" in html
    assert "Archived pre-race prediction" in html
    assert "Archived optimized forecast lineup: Test Grand Prix" in html
    assert "Current optimized team" not in html
    assert html.index("Recorded F1 Fantasy results") < html.index("Archived pre-race prediction")
    assert '"@type": "Dataset"' in html
    assert '"contentUrl": "https://boxboxf1fantasy.com/data/actual_round12.json"' in html
    assert "Recorded F1 Fantasy driver results for Test GP 2026" in html


def test_picks_hub_marks_completed_rounds_as_results():
    entries = [
        ("test-gp-2026", "Test Grand Prix", "2026-07-19", 12, "result"),
        ("future-gp-2026", "Future Grand Prix", "2026-07-26", 13, "future"),
    ]

    html = seo.render_index(entries, race_week_predictions(), None)

    assert '<span class="tag tag-result">Results</span>' in html
    assert "Where can I find completed F1 Fantasy race results?" in html


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


def test_directory_hubs_explain_resources_and_publish_faq_schema():
    current = race_week_predictions()
    tools_html = seo.render_list_hub("tools", "Tools", seo.TOOLS_HUB, seo.TOOLS, current)
    guides_html = seo.render_list_hub("guides", "Guides", seo.GUIDES_HUB, seo.GUIDES, current)

    assert "Choose a tool for the decision you need to make" in tools_html
    assert "Current round: Test Grand Prix" in tools_html
    assert "/picks/test-gp-2026/" in tools_html
    assert 'class="listing-summary"' in tools_html
    assert "Where should a new F1 Fantasy player start?" in guides_html
    assert '"@type": "FAQPage"' in tools_html
    assert '"@type": "FAQPage"' in guides_html


def test_driver_profile_uses_unique_projection_breakdown_and_history():
    current = race_week_predictions()
    driver = current["drivers"][1]
    driver.update({
        "expected_points_quali": 6.0,
        "expected_points_race": 54.0,
        "expected_positions_gained_lost": 2,
        "expected_overtakes": 5,
        "fastest_lap_probability": 0.12,
        "dotd_probability": 0.08,
        "confidence": 72,
        "risk": "MEDIUM",
    })
    history = {
        "rounds": [
            {"round": 1, "points": 10, "is_dnf": False},
            {"round": 2, "points": 20, "is_dnf": False},
            {"round": 3, "points": -5, "is_dnf": True},
            {"round": 6, "points": 30, "is_dnf": False},
        ],
    }
    round_names = {
        1: {"name": "Australian Grand Prix"},
        2: {"name": "Chinese Grand Prix"},
        3: {"name": "Japanese Grand Prix"},
        6: {"name": "Miami Grand Prix"},
    }
    html = seo.render_driver_page(
        driver,
        current,
        1,
        {"X": current["constructors"][0]},
        history,
        round_names,
    )

    assert "Where the projection comes from" in html
    assert "Expected qualifying contribution</th><td>6.0 pts" in html
    assert "Risk and upside" in html
    assert "2026 fantasy form" in html
    assert "55 fantasy points" in html
    assert "13.8 per round on average" in html
    assert "latest three-round average is 15.0" in html
    assert "Miami GP" in html
    assert "/constructors/team-x/" in html
    assert "How has Driver B scored in F1 Fantasy this season?" in html
    assert '"name": "2026 recorded fantasy points"' in html


def test_constructor_profile_uses_driver_breakdown_and_history():
    current = race_week_predictions()
    constructor = current["constructors"][0]
    constructor.update({
        "driver_1": "A",
        "driver_2": "B",
        "expected_points_quali": 20,
        "expected_points_race": 35,
        "expected_dnf_impact": -4,
        "dnf_probability": 0.15,
        "risk": "MEDIUM",
        "mc_total_p5": 5,
        "mc_total_p95": 80,
    })
    history = {
        "rounds": [
            {"round": 1, "points": 80},
            {"round": 2, "points": 100},
            {"round": 3, "points": 40},
            {"round": 6, "points": 90},
        ],
    }
    round_names = {
        1: {"name": "Australian Grand Prix"},
        2: {"name": "Chinese Grand Prix"},
        3: {"name": "Japanese Grand Prix"},
        6: {"name": "Miami Grand Prix"},
    }
    drivers = {d["driver_id"]: d for d in current["drivers"]}
    html = seo.render_constructor_page(
        constructor,
        current,
        1,
        drivers,
        history,
        round_names,
    )

    assert "Where the constructor projection comes from" in html
    assert "Qualifying contribution estimate</th><td>20.0 pts" in html
    assert "Driver contribution outlook" in html
    assert 'href="/drivers/driver-a/"' in html
    assert "Driver boost multipliers never increase Team X" in html
    assert "2026 constructor form" in html
    assert "310 fantasy points" in html
    assert "77.5 per round on average" in html
    assert "latest three-round average is 76.7" in html
    assert "How has Team X scored in F1 Fantasy this season?" in html
    assert '"name": "2026 recorded constructor fantasy points"' in html


def test_topical_hubs_publish_current_context_guidance_and_faq_schema():
    current = race_week_predictions()
    for i, constructor in enumerate(current["constructors"]):
        constructor["mc_total_p5"] = 10 - i
    entries = [
        ("test-gp-2026", "Test Grand Prix", "2026-07-19", 12, "current"),
        ("future-gp-2026", "Future Grand Prix", "2026-07-26", 13, "future"),
    ]
    weather = {
        "round": 12,
        "sessions": [{"name": "Race", "rain_probability": 35, "rain_risk": "MEDIUM"}],
    }

    picks_html = seo.render_index(entries, current, weather)
    drivers_html = seo.render_drivers_hub(current)
    constructors_html = seo.render_constructors_hub(current)

    assert "Current F1 Fantasy picks: Test Grand Prix" in picks_html
    assert "Latest race forecast: 35% rain probability" in picks_html
    assert "How race-pick pages change through the weekend" in picks_html
    assert "Current driver rankings" in drivers_html
    assert "Driver B leads expected points at 60.0" in drivers_html
    assert 'href="/constructors/team-x/"' in drivers_html
    assert "Current constructor rankings" in constructors_html
    assert "How to read the constructor table" in constructors_html
    assert '"@type": "FAQPage"' in picks_html
    assert '"@type": "FAQPage"' in drivers_html
    assert '"@type": "FAQPage"' in constructors_html


def test_methodology_and_about_publish_trust_correction_and_schema_signals():
    methodology = next(page for page in seo.STATIC_PAGES if page["slug"] == "methodology")
    about = next(page for page in seo.STATIC_PAGES if page["slug"] == "about")

    methodology_html = seo.render_static_page(methodology)
    about_html = seo.render_static_page(about)

    assert "Race-week forecast phases" in methodology_html
    assert "Validation and leakage safeguards" in methodology_html
    assert "Corrections and version accountability" in methodology_html
    assert "without publishing proprietary feature weights" in methodology_html
    assert '"@type": "TechArticle"' in methodology_html
    assert 'By <a href="/about/" rel="author">BoxBoxF1Fantasy</a>' in methodology_html
    assert "How this analysis is made" not in methodology_html
    assert '"url": "https://boxboxf1fantasy.com/about/"' in methodology_html
    assert f'"dateModified": "{seo.SEO_CONTENT_LASTMOD}"' in methodology_html
    assert '"@type": "FAQPage"' in methodology_html
    assert "Corrections and accountability" in about_html
    assert "Editorial authorship" in about_html
    assert "rather than attributed to a fictional individual contributor" in about_html
    assert "Why is BoxBoxF1Fantasy listed as the author?" in about_html
    assert "/methodology/" in about_html
    assert '"@type": "Organization"' in about_html
    assert '"@type": "FAQPage"' in about_html


def test_fantasy_stats_page_ranks_recorded_points_prices_and_form():
    season = {
        "generated_at": "2026-07-09T20:41:22Z",
        "rounds": [
            {"round": 1, "name": "Opening Grand Prix", "date": "2026-03-08", "has_actual": True},
            {"round": 2, "name": "Latest Grand Prix", "date": "2026-03-15", "has_actual": True},
        ],
        "driver_prices": {
            "A": {"name": "Driver A", "current_price": 10.0, "starting_price": 9.0, "price_change": 1.0},
            "B": {"name": "Driver B", "current_price": 20.0, "starting_price": 20.5, "price_change": -0.5},
        },
        "constructor_prices": {
            "team_x": {"name": "Team X", "current_price": 25.0, "starting_price": 23.0, "price_change": 2.0},
        },
    }
    history = {
        "drivers": {
            "A": {"rounds": [{"round": 1, "points": 10}, {"round": 2, "points": 30}]},
            "B": {"rounds": [{"round": 1, "points": 15}, {"round": 2, "points": 5}]},
        },
        "constructors": {
            "team_x": {"rounds": [{"round": 1, "points": 50}, {"round": 2, "points": 70}]},
        },
    }

    html = seo.render_fantasy_stats_page(season, history)

    assert "F1 Fantasy Points &amp; Price Tracker 2026" in html
    assert "Fantasy scoring, not championship standings" in html
    assert 'href="/drivers/driver-a/">Driver A</a>' in html
    assert 'href="/constructors/team-x/">Team X</a>' in html
    assert "40</strong>" in html
    assert "10, 30<br><small>20.0 avg" in html
    assert "+1.0M" in html
    assert 'aria-label="2026 F1 Fantasy driver points and prices"' in html
    assert '"@type": "Dataset"' in html
    assert '"temporalCoverage": "2026-03-08/2026-03-15"' in html
    assert '"@type": "FAQPage"' in html
    assert seo.page_kind_from_relpath("stats/") == "fantasy_points_price_tracker"


def test_belgian_model_briefing_is_dated_sourced_and_phase_honest():
    articles_data = json.loads((seo.DATA / "articles.json").read_text(encoding="utf-8"))
    briefing = next(
        article for article in articles_data["articles"]
        if article["slug"] == "2026-07-13-belgian-gp-model-briefing"
    )

    html = seo.render_article_page(briefing)

    assert "Belgian GP F1 Fantasy: Why Max Leads" in html
    assert 'By <a href="/about/" rel="author">BoxBoxF1Fantasy</a>' in html
    assert 'href="/methodology/">How this analysis is made</a>' in html
    assert '"url": "https://boxboxf1fantasy.com/about/"' in html
    assert "dated <strong>pre-practice briefing</strong>" in html
    assert "The short answer is upside, not certainty" in html
    assert "Weather is moving faster than the model" in html
    assert "Red Bull is not the top constructor projection" in html
    assert '"datePublished": "2026-07-13"' in html
    assert '"wordCount":' in html
    assert '"https://boxboxf1fantasy.com/data/predictions.json"' in html
    assert '"https://boxboxf1fantasy.com/methodology/"' in html
    assert 'property="og:type" content="article"' in html
    assert 'property="og:image" content="https://boxboxf1fantasy.com/images/belgian-gp-2026-fantasy-forecast.png"' in html
    assert '"@type": "ImageObject"' in html
    assert 'src="/images/belgian-gp-2026-fantasy-forecast.png"' in html
    assert 'loading="lazy"' in html


def test_midseason_report_is_original_dated_sourced_and_shareable():
    articles_data = json.loads((seo.DATA / "articles.json").read_text(encoding="utf-8"))
    report = next(
        article for article in articles_data["articles"]
        if article["slug"] == "2026-07-13-f1-fantasy-mid-season-report"
    )

    html = seo.render_article_page(report)

    assert "<title>F1 Fantasy 2026 Mid-Season Report | BoxBoxF1Fantasy</title>" in html
    assert "F1 Fantasy 2026 Mid-Season Report: Points, Prices &amp; Form" in html
    assert "After nine completed races" in html
    assert "Kimi Antonelli" in html
    assert "Lewis Hamilton" in html
    assert "Franco Colapinto" in html
    assert "Racing Bulls" in html
    assert "backward-looking" in html
    assert 'property="og:image" content="https://boxboxf1fantasy.com/images/f1-fantasy-2026-mid-season-points-value.png"' in html
    assert 'src="/images/f1-fantasy-2026-mid-season-points-value.png"' in html
    assert '"mainEntityOfPage": "https://boxboxf1fantasy.com/articles/2026-07-13-f1-fantasy-mid-season-report/"' in html
    assert '"isAccessibleForFree": true' in html
    assert '"wordCount":' in html
    assert '"https://boxboxf1fantasy.com/stats/"' in html
    assert '"https://boxboxf1fantasy.com/data/driver_history.json"' in html


def test_news_sitemap_metadata_only_includes_articles_from_last_two_days(tmp_path, monkeypatch):
    articles = [
        {"slug": "today", "title": "Today's Report", "date": "2026-07-13"},
        {"slug": "two-days", "title": "Two Day Report", "date": "2026-07-11"},
        {"slug": "old", "title": "Old Report", "date": "2026-07-10"},
        {"slug": "future", "title": "Future Report", "date": "2026-07-14"},
    ]
    news = seo.news_sitemap_items(articles, seo.date(2026, 7, 13))
    monkeypatch.setattr(seo, "WEB", tmp_path)

    seo.write_sitemap(
        ["articles/today/", "articles/two-days/", "articles/old/", "articles/future/"],
        {},
        news,
    )
    sitemap = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")

    assert set(news) == {"articles/today/", "articles/two-days/"}
    assert 'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"' in sitemap
    assert sitemap.count("<news:news>") == 2
    assert "<news:title>Today&#x27;s Report</news:title>" in sitemap
    assert "<news:title>Old Report</news:title>" not in sitemap
    assert "<news:title>Future Report</news:title>" not in sitemap
