import importlib.util
import json
from pathlib import Path

import pytest

from config import settings
from pipeline import publish_v13_decision as publisher

spec = importlib.util.spec_from_file_location("v13_export_test", Path(__file__).parents[1] / "pipeline/08_export_website_json.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def test_standalone_export_requires_matching_v13_and_propagates_refresh_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "is_race_completed", lambda _: False)
    live = {"round": 22, "phase": "post_fp", "generated_at": "2026-11-07T14:00:00Z"}
    (tmp_path / "predictions.json").write_text(json.dumps(live), encoding="utf-8")
    monkeypatch.setattr(publisher, "publish_live", lambda n, phase: {"source_generated_at": live["generated_at"]})
    assert exporter.refresh_v13_after_export(22, "post_fp")["source_generated_at"] == live["generated_at"]
    monkeypatch.setattr(publisher, "publish_live", lambda *_: {"source_generated_at": "old"})
    with pytest.raises(RuntimeError, match="did not refresh"):
        exporter.refresh_v13_after_export(22, "post_fp")
    def fail(*_):
        raise ValueError("broken budget")
    monkeypatch.setattr(publisher, "publish_live", fail)
    with pytest.raises(ValueError, match="broken budget"):
        exporter.refresh_v13_after_export(22, "post_fp")
    assert exporter.refresh_v13_after_export(22, "post_quali") is None
    assert exporter.refresh_v13_after_export(22, "post_fp", reconstructed=True) is None
    assert exporter.refresh_v13_after_export(21, "post_fp") is None
