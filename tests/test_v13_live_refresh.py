"""New practice forecasts must update V13 without rewriting its audit history."""

import hashlib
import json

import pytest

from pipeline import publish_v13_decision as publisher


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    data = tmp_path / "web/public/data"
    data.mkdir(parents=True)
    decisions = tmp_path / "data/v13/decisions"
    decisions.mkdir(parents=True)
    original = {"round": 18, "phase": "post_fp", "generated_at": "2026-10-02T06:00:00Z", "fp_sessions_included": ["FP1"]}
    archive = data / "predictions_round18_post_fp.json"
    archive.write_text(json.dumps(original), encoding="utf-8")
    live = data / "predictions.json"
    live.write_text(json.dumps({**original, "generated_at": "2026-10-02T09:00:00Z", "fp_sessions_included": ["FP1", "FP2"]}), encoding="utf-8")
    base = {
        "round": 18, "phase": "post_fp", "source_generated_at": original["generated_at"],
        "archive": archive.relative_to(tmp_path).as_posix(),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    base_path = decisions / "round18_post_fp.json"
    base_path.write_bytes(publisher._canonical_bytes(base))
    public = data / "v13_manager.json"
    payload = {"current_state": {"next_round": 18}}
    public.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(publisher, "ROOT", tmp_path)
    monkeypatch.setattr(publisher, "WEB_DATA_DIR", data)
    monkeypatch.setattr(publisher, "DECISION_DIR", decisions)
    monkeypatch.setattr(publisher, "PUBLIC_PATH", public)
    monkeypatch.setattr(publisher.v13, "main", lambda: None)
    monkeypatch.setattr(publisher.v13, "build_payload", lambda: {"current_state": {"next_round": 18}})
    monkeypatch.setattr(publisher, "_lock_deadline", lambda _: "2026-10-03T08:00:00Z")

    def decision(round_num, phase, public_payload, archive_override):
        snapshot = tmp_path / archive_override
        source = json.loads(snapshot.read_bytes())
        return {**base, "source_generated_at": source["generated_at"], "archive": archive_override,
                "archive_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()}

    monkeypatch.setattr(publisher, "_decision", decision)
    return live, archive, base_path, decisions, public


def test_fp2_refresh_preserves_fp1_and_retry_reuses_revision(workspace):
    live, archive, base_path, decisions, public = workspace
    frozen = [archive.read_bytes(), base_path.read_bytes()]
    result = publisher.publish_live(18, "post_fp")
    assert result["revision"] == 2
    assert result["source_generated_at"] == json.loads(live.read_bytes())["generated_at"]
    assert result["supersedes_sha256"] == publisher._record_sha256(json.loads(base_path.read_bytes()))
    snapshot = publisher.ROOT / result["archive"]
    assert snapshot.read_bytes() == live.read_bytes()
    assert json.loads(public.read_bytes())["current_state"]["post_fp_final"] == result
    revision_bytes = (decisions / "round18_post_fp_revision2.json").read_bytes()
    assert publisher.publish_live(18, "post_fp") == result
    assert len(list(decisions.glob("*revision*.json"))) == 1
    assert (decisions / "round18_post_fp_revision2.json").read_bytes() == revision_bytes
    assert [archive.read_bytes(), base_path.read_bytes()] == frozen


@pytest.mark.parametrize("changes", [
    {"round": 19}, {"phase": "post_quali"}, {"reconstructed": True},
    {"generated_at": "2026-10-03T08:00:00Z"},
    {"generated_at": "2026-10-02T05:00:00Z"},
])
def test_invalid_refresh_never_creates_a_revision(workspace, changes):
    live, _, _, decisions, _ = workspace
    live.write_text(json.dumps({**json.loads(live.read_bytes()), **changes}), encoding="utf-8")
    with pytest.raises(ValueError):
        publisher.publish_live(18, "post_fp")
    assert not list(decisions.glob("*revision*.json"))
    assert not list(live.parent.glob("*refresh*.json"))


def test_newer_refresh_appends_a_revision_without_changing_older_ones(workspace):
    live, _, _, decisions, _ = workspace
    first = publisher.publish_live(18, "post_fp")
    frozen = (decisions / "round18_post_fp_revision2.json").read_bytes()
    live.write_text(json.dumps({**json.loads(live.read_bytes()), "generated_at": "2026-10-02T12:00:00Z", "fp_sessions_included": ["FP1", "FP2", "FP3"]}), encoding="utf-8")
    second = publisher.publish_live(18, "post_fp")
    assert second["revision"] == 3
    assert second["supersedes_sha256"] == publisher._record_sha256(first)
    assert (decisions / "round18_post_fp_revision2.json").read_bytes() == frozen


def test_refresh_rejects_a_tampered_revision_source(workspace):
    _, _, _, decisions, _ = workspace
    first = publisher.publish_live(18, "post_fp")
    (publisher.ROOT / first["archive"]).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="frozen source archive has changed"):
        publisher.publish_live(18, "post_fp")
    assert len(list(decisions.glob("*revision*.json"))) == 1
