"""Build a local-only Pit Wall weekly-email preview.

This script deliberately stops at content generation.  It reads the current
published prediction export, prints a reviewable text preview, and can write
HTML to a local path.  It does not import an HTTP client, inspect Supabase,
load a Resend segment, or offer a delivery flag.  That keeps this iteration
safe while the editorial shape is reviewed with Pit Wall members in mind.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTIONS = ROOT / "web" / "public" / "data" / "predictions.json"
DEFAULT_SITE_ORIGIN = "https://boxboxf1fantasy.com"
DEFAULT_LIMIT = 3
AUDIENCE_LABEL = "Pit Wall paid members"
PREVIEW_NOTICE = (
    "Preview only: no recipients, Beat V13 entrants, free simulation contacts, "
    "delivery operation, or email send is involved."
)

PHASE_LABELS = {
    "pre_fp": "Early thoughts",
    "post_fp": "Post-FP",
    "post_quali": "Post-qualifying",
}


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed == parsed else fallback


def _score(item: dict[str, Any]) -> float:
    """Return the published expected score used for the weekly ranking."""

    # ``expected_points`` is the Monte Carlo mean in the live export.  The
    # fallbacks keep local previews useful with older archived exports.
    for key in ("expected_points", "mc_total_mean", "projected_points"):
        if item.get(key) is not None:
            return _number(item.get(key))
    return 0.0


def _risk_rating(item: dict[str, Any]) -> float:
    return _number(item.get("risk_rating"), _number(item.get("dnf_probability")) * 100)


def _display_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("full_name") or item.get("driver_id") or item.get("constructor_id") or "Unknown")


def _asset_id(item: dict[str, Any]) -> str:
    return str(item.get("driver_id") or item.get("constructor_id") or item.get("asset_id") or "")


def _asset_type(item: dict[str, Any], default: str) -> str:
    return default if default in {"driver", "constructor"} else "asset"


def _pick_summary(item: dict[str, Any], asset_type: str, reason: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": _asset_id(item),
        "name": _display_name(item),
        "asset_type": _asset_type(item, asset_type),
        "expected_points": round(_score(item), 1),
        "current_price": item.get("current_price"),
        "points_per_million": item.get("points_per_million"),
        "risk": str(item.get("risk") or "").upper() or None,
        "risk_rating": round(_risk_rating(item), 1),
    }
    if item.get("predicted_finish") is not None:
        summary["predicted_finish"] = item.get("predicted_finish")
    if item.get("predicted_grid") is not None:
        summary["predicted_grid"] = item.get("predicted_grid")
    if reason:
        summary["reason"] = reason
    return summary


def _top_ranked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Higher expected points first; lower risk is the deterministic tie-break.
    return sorted(items, key=lambda item: (-_score(item), _risk_rating(item), _display_name(item).lower()))


def _sell_ranked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # This is a market-wide avoid list, not a personalized instruction.  Put
    # the lowest expected return first, then surface the riskier tie.
    return sorted(items, key=lambda item: (_score(item), -_risk_rating(item), _display_name(item).lower()))


def _sell_reason(item: dict[str, Any]) -> str:
    score = _score(item)
    risk = _risk_rating(item)
    if score <= 0:
        return "negative expected return"
    if risk >= 25 or str(item.get("risk") or "").upper() == "HIGH":
        return "high model risk"
    return "lowest expected return in this field"


def classify_predictions(predictions: dict[str, Any], limit: int = DEFAULT_LIMIT) -> dict[str, list[dict[str, Any]]]:
    """Select top picks and likely-sell candidates from published predictions.

    The result contains no email address or member data.  Drivers and
    constructors remain separate so the preview cannot be mistaken for a
    personalized saved-lineup recommendation.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")
    groups = {
        "drivers": list(predictions.get("drivers") or []),
        "constructors": list(predictions.get("constructors") or []),
    }
    result: dict[str, list[dict[str, Any]]] = {
        "top_drivers": [],
        "top_constructors": [],
        "likely_driver_sells": [],
        "likely_constructor_sells": [],
    }
    for plural, items in groups.items():
        singular = plural[:-1]
        top_key = f"top_{plural}"
        sell_key = f"likely_{singular}_sells"
        result[top_key] = [
            _pick_summary(item, singular)
            for item in _top_ranked(items)[:limit]
        ]
        result[sell_key] = [
            _pick_summary(item, singular, _sell_reason(item))
            for item in _sell_ranked(items)[:limit]
        ]
    return result


def _phase_label(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase.replace("_", " ").title())


def _format_points(item: dict[str, Any]) -> str:
    return f"{_number(item.get('expected_points')):.1f} pts"


def _format_price(item: dict[str, Any]) -> str:
    price = item.get("current_price")
    if price is None or price == "":
        return "price n/a"
    return f"${_number(price):.1f}M"


def _text_row(item: dict[str, Any], index: int, include_reason: bool = False) -> str:
    line = f"{index}. {item['name']} — {_format_points(item)}, {_format_price(item)}"
    if item.get("risk"):
        line += f", {item['risk']} risk"
    if include_reason and item.get("reason"):
        line += f" ({item['reason']})"
    return line


def _html_rows(items: list[dict[str, Any]], include_reason: bool = False) -> str:
    rows = []
    for index, item in enumerate(items, start=1):
        details = f"{_format_points(item)} · {_format_price(item)}"
        if item.get("risk"):
            details += f" · {item['risk']} risk"
        reason = f" — {item['reason']}" if include_reason and item.get("reason") else ""
        rows.append(
            f"<li><strong>{html.escape(item['name'])}</strong> — "
            f"{html.escape(details)}{html.escape(reason)}</li>"
        )
    return "".join(rows) or "<li>No published candidates</li>"


def build_preview(
    predictions: dict[str, Any],
    site_origin: str = DEFAULT_SITE_ORIGIN,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Render the Pit Wall weekly preview without performing any I/O."""

    picks = classify_predictions(predictions, limit=limit)
    race = str(predictions.get("race") or "the next Grand Prix")
    round_number = int(_number(predictions.get("round")))
    phase = str(predictions.get("phase") or "updated")
    phase_label = _phase_label(phase)
    query = urlencode({
        "utm_source": "pit_wall_preview",
        "utm_medium": "weekly_email_preview",
        "utm_campaign": f"round_{round_number}_{phase}",
    })
    predictions_url = f"{site_origin.rstrip('/')}/?{query}#drivers"
    subject = f"Pit Wall weekly preview — {race} ({phase_label})"
    html_body = f"""<!doctype html>
<html><body style="margin:0;background:#f4f6f8;color:#151922;font-family:Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">
  <div style="background:#0a0d12;color:#fff;border-radius:12px;overflow:hidden">
    <div style="padding:22px 26px;border-bottom:3px solid #e10600">
      <div style="font-size:13px;color:#aab4c3">BoxBox<span style="color:#e10600">F1</span>Fantasy · Pit Wall</div>
      <h1 style="margin:7px 0 4px;font-size:25px">Weekly member preview</h1>
      <p style="margin:0;color:#c7d0dc">{html.escape(race)} · {html.escape(phase_label)}</p>
    </div>
    <div style="padding:22px 26px">
      <p><strong>Audience: {html.escape(AUDIENCE_LABEL)}</strong></p>
      <h2 style="font-size:17px;margin:20px 0 8px">Top driver picks</h2>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 20px">{_html_rows(picks['top_drivers'])}</ol>
      <h2 style="font-size:17px;margin:20px 0 8px">Top constructor picks</h2>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 20px">{_html_rows(picks['top_constructors'])}</ol>
      <h2 style="font-size:17px;margin:20px 0 8px">Likely sells / avoid candidates</h2>
      <p style="color:#475467">Market-wide signals for member discussion; these are not personalized lineup instructions.</p>
      <h3 style="font-size:15px;margin:15px 0 6px">Drivers</h3>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 16px">{_html_rows(picks['likely_driver_sells'], include_reason=True)}</ol>
      <h3 style="font-size:15px;margin:15px 0 6px">Constructors</h3>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 24px">{_html_rows(picks['likely_constructor_sells'], include_reason=True)}</ol>
      <p><a href="{html.escape(predictions_url)}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 17px;border-radius:7px;font-weight:700">Open the live predictions</a></p>
    </div>
  </div>
  <p style="font-size:12px;line-height:1.5;color:#667085;text-align:center">{html.escape(PREVIEW_NOTICE)}</p>
</div></body></html>"""

    text_sections = [
        f"{AUDIENCE_LABEL} — weekly preview",
        f"{race} · {phase_label} · Round {round_number}",
        "",
        "Top driver picks",
        *(_text_row(item, index) for index, item in enumerate(picks["top_drivers"], start=1)),
        "",
        "Top constructor picks",
        *(_text_row(item, index) for index, item in enumerate(picks["top_constructors"], start=1)),
        "",
        "Likely sells / avoid candidates (market-wide)",
        "Drivers",
        *(_text_row(item, index, include_reason=True) for index, item in enumerate(picks["likely_driver_sells"], start=1)),
        "Constructors",
        *(_text_row(item, index, include_reason=True) for index, item in enumerate(picks["likely_constructor_sells"], start=1)),
        "",
        f"Open the live predictions: {predictions_url}",
        "",
        PREVIEW_NOTICE,
    ]
    return {
        "audience": AUDIENCE_LABEL,
        "preview_only": True,
        "subject": subject,
        "race": race,
        "round": round_number,
        "phase": phase,
        "generated_at": predictions.get("generated_at") or predictions.get("exported_at"),
        "picks": picks,
        "html": html_body,
        "text": "\n".join(text_sections),
    }


def load_predictions(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Predictions export must be a JSON object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Items per pick/sell section (default: 3)")
    parser.add_argument("--site-origin", default=DEFAULT_SITE_ORIGIN)
    parser.add_argument("--preview-html", type=Path, help="Optionally write the local HTML preview")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    predictions = load_predictions(args.predictions)
    preview = build_preview(predictions, site_origin=args.site_origin, limit=args.limit)
    print(f"Subject: {preview['subject']}")
    print(preview["text"])
    if args.preview_html:
        args.preview_html.parent.mkdir(parents=True, exist_ok=True)
        args.preview_html.write_text(preview["html"], encoding="utf-8")
        print(f"Wrote local HTML preview: {args.preview_html}")
    print(PREVIEW_NOTICE)


if __name__ == "__main__":
    main()
