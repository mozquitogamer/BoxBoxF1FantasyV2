"""Configure BoxBoxF1Fantasy's dormant Google AdSense integration.

This writes the public feature flags, creates the root ads.txt record, and
rebuilds the static pages so the literal account code appears in every <head>.
It never invents publisher or slot IDs.

Examples:
    python pipeline/configure_adsense.py --publisher-id ca-pub-1234567890123456
    python pipeline/configure_adsense.py --publisher-id ca-pub-1234567890123456 \
        --slot-id 1234567890 --account-code --display-ads
    python pipeline/configure_adsense.py --check
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.adsense import (  # noqa: E402
    ADSENSE_HEAD_END,
    ADSENSE_HEAD_START,
    ads_txt_line,
    render_adsense_account_head,
    validate_adsense_settings,
)

FEATURES_PATH = ROOT / "web" / "public" / "data" / "site_features.json"
ADS_TXT_PATH = ROOT / "web" / "public" / "ads.txt"
HOME_PATH = ROOT / "web" / "public" / "index.html"
GENERATOR_PATH = ROOT / "pipeline" / "14_build_seo_pages.py"


def load_features() -> dict:
    return json.loads(FEATURES_PATH.read_text(encoding="utf-8"))


def save_features(features: dict) -> None:
    FEATURES_PATH.write_text(
        json.dumps(features, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def expected_home_head(settings: dict) -> str:
    return render_adsense_account_head(settings)


def check_installation(features: dict) -> list[str]:
    errors: list[str] = []
    settings = features.get("adsense") or {}
    try:
        validate_adsense_settings(settings)
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    home = HOME_PATH.read_text(encoding="utf-8")
    match = re.search(
        re.escape(ADSENSE_HEAD_START) + r".*?" + re.escape(ADSENSE_HEAD_END),
        home,
        re.S,
    )
    if not match:
        errors.append("Homepage is missing the AdSense account-code markers")
    elif match.group(0) != expected_home_head(settings):
        errors.append("Homepage account code is out of sync; rebuild the SEO pages")

    publisher_id = str(settings.get("publisher_id") or "").strip()
    if publisher_id:
        expected_ads_txt = ads_txt_line(publisher_id) + "\n"
        if not ADS_TXT_PATH.exists():
            errors.append("ads.txt is missing")
        elif ADS_TXT_PATH.read_text(encoding="utf-8") != expected_ads_txt:
            errors.append("ads.txt does not match the configured publisher ID")
    elif ADS_TXT_PATH.exists():
        errors.append("ads.txt exists but no AdSense publisher ID is configured")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure the BoxBox AdSense account and bottom display unit")
    parser.add_argument("--publisher-id", help="Google account ID, for example ca-pub-1234567890123456")
    parser.add_argument("--slot-id", help="10-digit responsive display ad-slot ID")
    parser.add_argument(
        "--account-code",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable literal account code in every page head",
    )
    parser.add_argument(
        "--display-ads",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the bottom responsive display unit",
    )
    parser.add_argument("--skip-rebuild", action="store_true", help="Do not regenerate static pages")
    parser.add_argument("--check", action="store_true", help="Validate the current setup without writing files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    features = load_features()
    settings = features.setdefault("adsense", {})

    if args.check:
        errors = check_installation(features)
        if errors:
            for error in errors:
                print(f"[ERROR] {error}")
            return 1
        print("[OK] AdSense configuration, homepage account code, and ads.txt are consistent")
        return 0

    if args.publisher_id is not None:
        settings["publisher_id"] = args.publisher_id.strip()
    if args.slot_id is not None:
        settings["bottom_display_slot_id"] = args.slot_id.strip()
    if args.account_code is not None:
        settings["account_code_enabled"] = args.account_code
    if args.display_ads is not None:
        settings["display_ads_enabled"] = args.display_ads

    try:
        validate_adsense_settings(settings)
    except ValueError as exc:
        raise SystemExit(f"Invalid AdSense configuration: {exc}") from exc

    publisher_id = str(settings.get("publisher_id") or "").strip()
    if not publisher_id:
        raise SystemExit("Provide --publisher-id before configuring AdSense")

    save_features(features)
    ADS_TXT_PATH.write_text(ads_txt_line(publisher_id) + "\n", encoding="utf-8")

    if not args.skip_rebuild:
        subprocess.run([sys.executable, str(GENERATOR_PATH)], cwd=ROOT, check=True)

    errors = check_installation(load_features())
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 1

    print("[OK] AdSense configured; ads.txt and static page heads are synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
