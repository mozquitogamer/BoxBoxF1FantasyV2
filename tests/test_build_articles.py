import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "build_articles.py"
SPEC = importlib.util.spec_from_file_location("build_articles", SCRIPT)
articles = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(articles)


def test_build_preserves_json_only_articles_and_replaces_markdown_slugs(tmp_path, monkeypatch):
    source_dir = tmp_path / "articles"
    source_dir.mkdir()
    output = tmp_path / "articles.json"
    output.write_text(json.dumps({
        "articles": [
            {"slug": "json-only", "title": "Keep me", "date": "2026-04-01", "content_html": "<p>Existing</p>"},
            {"slug": "from-markdown", "title": "Old", "date": "2026-01-01", "content_html": "<p>Old</p>"},
        ],
    }), encoding="utf-8")
    (source_dir / "from-markdown.md").write_text(
        "---\ntitle: New article\ndate: 2026-07-13\ntags: preview, data\nsources: /data/predictions.json, /methodology/\n---\n\n## Fresh\n\nCurrent copy.",
        encoding="utf-8",
    )
    monkeypatch.setattr(articles, "ARTICLES_DIR", source_dir)
    monkeypatch.setattr(articles, "OUT_PATH", output)

    articles.build()

    built = json.loads(output.read_text(encoding="utf-8"))["articles"]
    assert [article["slug"] for article in built] == ["from-markdown", "json-only"]
    assert built[0]["title"] == "New article"
    assert built[0]["sources"] == ["/data/predictions.json", "/methodology/"]
    assert built[1]["title"] == "Keep me"
