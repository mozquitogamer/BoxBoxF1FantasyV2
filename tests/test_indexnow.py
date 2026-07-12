import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "15_submit_indexnow.py"
SPEC = importlib.util.spec_from_file_location("submit_indexnow", SCRIPT)
indexnow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(indexnow)


class FakeResponse:
    def __init__(self, body: str, status: int = 200):
        self._body = body.encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def test_sitemap_urls_and_deduplication(tmp_path):
    sitemap = tmp_path / "sitemap.xml"
    sitemap.write_text(
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://boxboxf1fantasy.com/</loc></url>"
        "<url><loc>https://boxboxf1fantasy.com/picks/</loc></url>"
        "</urlset>",
        encoding="utf-8",
    )
    urls = indexnow.sitemap_urls(sitemap)
    assert urls == [
        "https://boxboxf1fantasy.com/",
        "https://boxboxf1fantasy.com/picks/",
    ]
    assert indexnow.unique_urls(urls + urls[:1]) == urls
    assert list(indexnow.chunks(urls, 1)) == [[urls[0]], [urls[1]]]


def test_verify_production_key_accepts_exact_key(monkeypatch):
    monkeypatch.setattr(
        indexnow.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(indexnow.INDEXNOW_KEY),
    )
    indexnow.verify_production_key()


def test_verify_production_key_rejects_mismatch(monkeypatch):
    monkeypatch.setattr(
        indexnow.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse("wrong-key"),
    )
    with pytest.raises(RuntimeError, match="key mismatch"):
        indexnow.verify_production_key()
