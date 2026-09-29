import importlib.util
import json
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "pipeline" / "publish_fp2_article.py"
SPEC = importlib.util.spec_from_file_location("publish_fp2_article", MODULE_PATH)
article = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(article)


def sample_data():
    drivers = [
        {
            "driver_id": f"D{i}", "name": f"Driver {i}",
            "expected_points": float(30 - i), "current_price": float(4 + i),
            "mc_total_p5": float(-10 - i), "mc_total_p95": float(50 - i),
        }
        for i in range(22)
    ]
    constructors = [
        {"name": f"Team {i}", "expected_points": float(50 - i),
         "mc_total_p5": float(-5 - i), "mc_total_p95": float(80 - i)}
        for i in range(11)
    ]
    predictions = {
        "season": 2026, "round": 18, "phase": "post_fp",
        "exported_at": "2026-10-03T10:00:00+00:00",
        "is_sprint_weekend": False,
        "fp_sessions_included": ["FP1", "FP2"],
        "drivers": drivers, "constructors": constructors,
    }
    calendar = {"season": 2026, "races": [
        {"round": 18, "name": "Bahrain Grand Prix", "date": "2026-10-04", "sprint": False, "cancelled": False}
    ]}
    return predictions, calendar


def test_publishes_once_with_frozen_simulation(tmp_path):
    predictions, calendar = sample_data()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    live = data_dir / "predictions.json"
    races = tmp_path / "races.json"
    live.write_text(json.dumps(predictions), encoding="utf-8")
    races.write_text(json.dumps(calendar), encoding="utf-8")

    target = article.publish(live, races, tmp_path / "articles", date(2026, 10, 3))
    assert target is not None
    text = target.read_text(encoding="utf-8")
    assert "Driver 0" in text
    assert "30.0 expected points" in text
    assert "Team 0" in text
    assert "predictions_round18_post_fp2.json" in text
    snapshot = data_dir / "predictions_round18_post_fp2.json"
    assert json.loads(snapshot.read_text(encoding="utf-8")) == predictions
    assert article.publish(live, races, tmp_path / "articles", date(2026, 10, 3)) is None


def test_requires_fp2_only_and_complete_live_simulation():
    predictions, calendar = sample_data()
    today = date(2026, 10, 3)
    for sessions in ([], ["FP1"], ["FP1", "FP2", "FP3"]):
        predictions["fp_sessions_included"] = sessions
        assert article.eligible_article(predictions, calendar, today) is None
    predictions["fp_sessions_included"] = ["FP1", "FP2"]
    assert article.eligible_article(predictions, calendar, today) is not None
    predictions["drivers"][0].pop("mc_total_p95")
    assert article.eligible_article(predictions, calendar, today) is None


def test_rejects_old_or_reconstructed_race():
    predictions, calendar = sample_data()
    assert article.eligible_article(predictions, calendar, date(2026, 10, 5)) is None
    predictions["reconstructed"] = True
    assert article.eligible_article(predictions, calendar, date(2026, 10, 3)) is None
