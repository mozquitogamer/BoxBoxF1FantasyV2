"""Shared validation and HTML rendering for the optional AdSense integration."""
from __future__ import annotations

import re


ADSENSE_HEAD_START = "<!-- ADSENSE_ACCOUNT_CODE_START -->"
ADSENSE_HEAD_END = "<!-- ADSENSE_ACCOUNT_CODE_END -->"
PUBLISHER_ID_RE = re.compile(r"^ca-pub-(\d{16})$")
SLOT_ID_RE = re.compile(r"^\d{10}$")


def validate_adsense_settings(settings: dict | None) -> None:
    """Reject partial or unsafe public configuration before it is deployed."""
    settings = settings or {}
    publisher_id = str(settings.get("publisher_id") or "").strip()
    slot_id = str(settings.get("bottom_display_slot_id") or "").strip()
    account_enabled = bool(settings.get("account_code_enabled"))
    display_enabled = bool(settings.get("display_ads_enabled"))

    if publisher_id and not PUBLISHER_ID_RE.fullmatch(publisher_id):
        raise ValueError("AdSense publisher_id must look like ca-pub- followed by 16 digits")
    if slot_id and not SLOT_ID_RE.fullmatch(slot_id):
        raise ValueError("AdSense bottom_display_slot_id must contain exactly 10 digits")
    if account_enabled and not publisher_id:
        raise ValueError("AdSense account code cannot be enabled without a publisher_id")
    if display_enabled and not account_enabled:
        raise ValueError("AdSense display ads require account_code_enabled=true")
    if display_enabled and not slot_id:
        raise ValueError("AdSense display ads cannot be enabled without a bottom display slot ID")


def render_adsense_account_head(settings: dict | None) -> str:
    """Return literal account verification/loader markup, wrapped in stable markers."""
    settings = settings or {}
    validate_adsense_settings(settings)
    lines = [ADSENSE_HEAD_START]

    if settings.get("account_code_enabled"):
        publisher_id = str(settings["publisher_id"]).strip()
        lines.extend([
            f'<meta name="google-adsense-account" content="{publisher_id}">',
            (
                '<script async '
                'src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
                f'?client={publisher_id}" crossorigin="anonymous"></script>'
            ),
        ])

    lines.append(ADSENSE_HEAD_END)
    return "\n".join(lines)


def ads_txt_line(publisher_id: str) -> str:
    """Build Google's authorized-seller record from a validated account ID."""
    match = PUBLISHER_ID_RE.fullmatch(str(publisher_id).strip())
    if not match:
        raise ValueError("AdSense publisher_id must look like ca-pub- followed by 16 digits")
    return f"google.com, pub-{match.group(1)}, DIRECT, f08c47fec0942fa0"
