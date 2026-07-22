"""Create a Resend simulation-update broadcast from the live website export.

Safe by default: with no delivery flag this prints a local preview and makes no
network request. ``--draft`` creates a reviewable Resend draft. Only ``--send``
delivers immediately to the configured simulation-alert segment.

Environment variables:
    RESEND_API_KEY
    RESEND_FROM
    RESEND_SIM_UPDATES_SEGMENT_ID
    EMAIL_POSTAL_ADDRESS (required for --draft or --send)
    SITE_ORIGIN (optional; defaults to https://boxboxf1fantasy.com)
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTIONS = ROOT / "web" / "public" / "data" / "predictions.json"
RESEND_BROADCASTS_URL = "https://api.resend.com/broadcasts"
UNSUBSCRIBE_TAG = "{{{RESEND_UNSUBSCRIBE_URL}}}"

PHASE_LABELS = {
    "pre_fp": "Pre-practice",
    "post_fp": "Post-practice",
    "post_quali": "Post-qualifying",
}


def _points(item: dict[str, Any]) -> float:
    return float(item.get("expected_points", item.get("projected_points", 0)) or 0)


def _top(items: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    return sorted(items, key=_points, reverse=True)[:limit]


def _phase_label(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase.replace("_", " ").title())


def build_broadcast(
    predictions: dict[str, Any],
    site_origin: str,
    postal_address: str = "[Add sender postal address before sending]",
) -> dict[str, str]:
    race = str(predictions.get("race") or "the next Grand Prix")
    round_number = int(predictions.get("round") or 0)
    phase = str(predictions.get("phase") or "updated")
    phase_label = _phase_label(phase)
    drivers = _top(predictions.get("drivers") or [])
    constructors = _top(predictions.get("constructors") or [])

    query = urlencode({
        "utm_source": "email",
        "utm_medium": "simulation_alert",
        "utm_campaign": f"round_{round_number}_{phase}",
    })
    predictions_url = f"{site_origin.rstrip('/')}/?{query}#drivers"

    driver_rows = "".join(
        f"<li><strong>{html.escape(str(driver.get('name') or driver.get('driver_id') or 'Driver'))}</strong>"
        f" — {_points(driver):.1f} expected pts, P{html.escape(str(driver.get('predicted_finish', '–')))} finish</li>"
        for driver in drivers
    )
    constructor_rows = "".join(
        f"<li><strong>{html.escape(str(constructor.get('name') or constructor.get('constructor_id') or 'Constructor'))}</strong>"
        f" — {_points(constructor):.1f} expected pts</li>"
        for constructor in constructors
    )

    subject = f"{race} simulations updated — {phase_label}"
    broadcast_name = f"R{round_number} {phase_label} simulation alert"
    html_body = f"""<!doctype html>
<html><body style="margin:0;background:#f4f6f8;color:#151922;font-family:Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">
  <div style="background:#0a0d12;color:#fff;border-radius:12px;overflow:hidden">
    <div style="padding:22px 26px;border-bottom:3px solid #e10600">
      <div style="font-size:13px;color:#aab4c3">BoxBox<span style="color:#e10600">F1</span>Fantasy · Round {round_number}</div>
      <h1 style="margin:7px 0 4px;font-size:25px">Fresh simulations are live</h1>
      <p style="margin:0;color:#c7d0dc">{html.escape(race)} · {html.escape(phase_label)}</p>
    </div>
    <div style="padding:22px 26px">
      <h2 style="font-size:17px;margin:0 0 8px">Top driver projections</h2>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 20px">{driver_rows}</ol>
      <h2 style="font-size:17px;margin:0 0 8px">Top constructors</h2>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 24px">{constructor_rows}</ol>
      <p style="margin:0"><a href="{predictions_url}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 17px;border-radius:7px;font-weight:700">Open the updated predictions</a></p>
    </div>
  </div>
  <p style="font-size:12px;line-height:1.5;color:#667085;text-align:center">You confirmed that you want BoxBox simulation-update alerts. <a href="{UNSUBSCRIBE_TAG}" style="color:#667085">Unsubscribe</a>.<br>BoxBoxF1Fantasy · {html.escape(postal_address)}</p>
</div></body></html>"""

    driver_text = "\n".join(
        f"{index}. {driver.get('name') or driver.get('driver_id')} — {_points(driver):.1f} expected pts, P{driver.get('predicted_finish', '–')} finish"
        for index, driver in enumerate(drivers, start=1)
    )
    constructor_text = "\n".join(
        f"{index}. {constructor.get('name') or constructor.get('constructor_id')} — {_points(constructor):.1f} expected pts"
        for index, constructor in enumerate(constructors, start=1)
    )
    text_body = f"""BoxBoxF1Fantasy — {race}
{phase_label} simulations are live.

Top driver projections
{driver_text}

Top constructors
{constructor_text}

Open the updated predictions: {predictions_url}
Unsubscribe: {UNSUBSCRIBE_TAG}
Sender: BoxBoxF1Fantasy, {postal_address}
"""

    return {
        "name": broadcast_name,
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for --draft or --send")
    return value


def create_resend_broadcast(content: dict[str, str], send: bool) -> dict[str, Any]:
    _required_env("EMAIL_POSTAL_ADDRESS")
    payload: dict[str, Any] = {
        "segment_id": _required_env("RESEND_SIM_UPDATES_SEGMENT_ID"),
        "from": _required_env("RESEND_FROM"),
        **content,
    }
    if send:
        payload["send"] = True

    response = requests.post(
        RESEND_BROADCASTS_URL,
        headers={
            "Authorization": f"Bearer {_required_env('RESEND_API_KEY')}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    try:
        data = response.json()
    except ValueError:
        data = {"message": response.text[:500]}
    if not response.ok:
        raise RuntimeError(f"Resend returned HTTP {response.status_code}: {data.get('message', data)}")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument("--draft", action="store_true", help="Create a draft in Resend for review")
    delivery.add_argument("--send", action="store_true", help="Send immediately to the configured segment")
    parser.add_argument("--preview-html", type=Path, help="Optionally write the rendered email HTML locally")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    site_origin = os.environ.get("SITE_ORIGIN", "https://boxboxf1fantasy.com")
    postal_address = os.environ.get("EMAIL_POSTAL_ADDRESS", "[Add sender postal address before sending]")
    content = build_broadcast(predictions, site_origin, postal_address)

    print(f"Subject: {content['subject']}")
    print(f"Internal name: {content['name']}")
    print(content["text"])

    if args.preview_html:
        args.preview_html.parent.mkdir(parents=True, exist_ok=True)
        args.preview_html.write_text(content["html"], encoding="utf-8")
        print(f"Wrote HTML preview: {args.preview_html}")

    if not args.draft and not args.send:
        print("Preview only — no network request made. Use --draft to create a reviewable Resend draft.")
        return

    result = create_resend_broadcast(content, send=args.send)
    action = "sent" if args.send else "created as a draft"
    print(f"Broadcast {action}: {result.get('id', result)}")


if __name__ == "__main__":
    main()
