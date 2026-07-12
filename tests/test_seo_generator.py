import importlib.util
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
