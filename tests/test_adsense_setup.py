import json
from pathlib import Path

import pytest

from config.adsense import (
    ads_txt_line,
    render_adsense_account_head,
    validate_adsense_settings,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web" / "public"


def test_ads_txt_uses_pub_not_ca_pub():
    assert ads_txt_line("ca-pub-1234567890123456") == (
        "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0"
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"account_code_enabled": True, "publisher_id": ""},
        {"publisher_id": "ca-pub-123"},
        {"bottom_display_slot_id": "123"},
        {
            "account_code_enabled": False,
            "display_ads_enabled": True,
            "publisher_id": "ca-pub-1234567890123456",
            "bottom_display_slot_id": "1234567890",
        },
    ],
)
def test_invalid_or_partial_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        validate_adsense_settings(settings)


def test_enabled_account_code_is_literal_and_valid():
    markup = render_adsense_account_head(
        {
            "account_code_enabled": True,
            "display_ads_enabled": False,
            "publisher_id": "ca-pub-1234567890123456",
        }
    )
    assert '<meta name="google-adsense-account" content="ca-pub-1234567890123456">' in markup
    assert "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-1234567890123456" in markup
    assert 'crossorigin="anonymous"' in markup


def test_repository_verification_is_enabled_but_display_inventory_is_dormant():
    features = json.loads((PUBLIC / "data" / "site_features.json").read_text(encoding="utf-8"))
    adsense = features["adsense"]
    assert adsense["account_code_enabled"] is True
    assert adsense["display_ads_enabled"] is False
    assert adsense["publisher_id"] == "ca-pub-4471174873493912"
    assert adsense["bottom_display_slot_id"] == ""

    homepage = (PUBLIC / "index.html").read_text(encoding="utf-8")
    assert "ADSENSE_ACCOUNT_CODE_START" in homepage
    assert 'id="adsenseBottomUnit"' in homepage
    assert 'aria-label="Advertisement"' in homepage
    assert "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-4471174873493912" in homepage
    assert (PUBLIC / "ads.txt").read_text(encoding="utf-8") == (
        "google.com, pub-4471174873493912, DIRECT, f08c47fec0942fa0\n"
    )


def test_enforced_csp_has_not_been_silently_weakened():
    vercel = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))
    all_page_headers = next(item for item in vercel["headers"] if item["source"] == "/(.*)")
    csp = next(header["value"] for header in all_page_headers["headers"] if header["key"] == "Content-Security-Policy")
    assert "default-src 'self'" in csp
    assert "pagead2.googlesyndication.com" not in csp
