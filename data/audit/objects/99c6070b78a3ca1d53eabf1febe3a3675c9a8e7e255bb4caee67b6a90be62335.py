"""Create one short, factual article when live FP2 Monte Carlo results arrive.

The source is the committed public prediction JSON, so the article describes
exactly the simulation that visitors can see. The output is frozen per round.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREDICTIONS = ROOT / "web" / "public" / "data" / "predictions.json"
CALENDAR = ROOT / "data" / "seed" / "races.json"
ARTICLES = ROOT / "articles"


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ranked(items):
    return sorted(items, key=lambda item: item["expected_points"], reverse=True)


def eligible_article(predictions, calendar, today):
    """Return the matching race only for a fresh, complete FP2-only publication."""
    if predictions.get("season") != calendar.get("season"):
        return None
    if predictions.get("phase") != "post_fp" or predictions.get("reconstructed"):
        return None
    if predictions.get("is_sprint_weekend"):
        return None
    sessions = set(predictions.get("fp_sessions_included") or [])
    if "FP2" not in sessions or "FP3" in sessions:
        return None
    try:
        published = datetime.fromisoformat(predictions["exported_at"].replace("Z", "+00:00"))
        round_num = int(predictions["round"])
    except (KeyError, ValueError, TypeError):
        return None
    if published.tzinfo is None or published.astimezone(timezone.utc).date() > today:
        return None
    race = next((r for r in calendar.get("races", []) if r.get("round") == round_num), None)
    if not race or race.get("cancelled") or race.get("sprint"):
        return None
    if not published.astimezone(timezone.utc).date() <= today <= datetime.fromisoformat(race["date"]).date():
        return None
    drivers = predictions.get("drivers") or []
    constructors = predictions.get("constructors") or []
    if len(drivers) != 22 or len(constructors) != 11:
        return None
    if len({item.get("driver_id") for item in drivers}) != 22:
        return None
    required_driver = ("name", "driver_id", "expected_points", "current_price", "mc_total_p5", "mc_total_p95")
    required_constructor = ("name", "expected_points", "mc_total_p5", "mc_total_p95")
    for item in drivers:
        if any(not item.get(key) for key in ("name", "driver_id")):
            return None
        if any(not _number(item.get(key)) for key in required_driver[2:]):
            return None
    for item in constructors:
        if not item.get("name") or any(not _number(item.get(key)) for key in required_constructor[1:]):
            return None
    if max(item["expected_points"] for item in drivers) <= 0:
        return None
    if max(item["expected_points"] for item in drivers) - min(item["expected_points"] for item in drivers) < 5:
        return None
    return race


def render_article(predictions, race):
    drivers = _ranked(predictions["drivers"])
    constructors = _ranked(predictions["constructors"])
    prices = sorted(driver["current_price"] for driver in drivers)
    median_price = (prices[10] + prices[11]) / 2
    affordable = next(driver for driver in drivers if driver["current_price"] <= median_price)
    date = predictions["exported_at"][:10]
    race_name = race["name"]
    title = f"{race_name} FP2 Fantasy briefing: what the simulations say"
    lines = [
        "---",
        f"title: {title}",
        f"date: {date}",
        f"round: {race['round']}",
        "tags: analysis, FP2, predictions, fantasy",
        f"sources: /data/predictions_round{race['round']}_post_fp2.json, /methodology/",
        "---",
        "",
        f"## {race_name}: the FP2 picture",
        "",
        f"Our post-FP2 simulation for round {race['round']} is now live. These are **average Fantasy points across the simulations**, using the practice data available so far. Qualifying and the race have not happened; the numbers will change if new information arrives.",
        "",
        "## Leading drivers",
        "",
    ]
    for rank, driver in enumerate(drivers[:3], 1):
        lines.append(
            f"{rank}. **{driver['name']}** — {driver['expected_points']:.1f} expected points "
            f"at £{driver['current_price']:.1f}m. The middle 90% of simulated outcomes runs "
            f"from {driver['mc_total_p5']:.1f} to {driver['mc_total_p95']:.1f} points."
        )
    lines.extend([
        "",
        "The wide ranges show why a high average is only part of the decision: a strong result and a difficult weekend are both possible.",
        "",
        "## Constructor watch",
        "",
    ])
    for constructor in constructors[:2]:
        lines.append(
            f"- **{constructor['name']}** — {constructor['expected_points']:.1f} expected points; "
            f"middle 90% from {constructor['mc_total_p5']:.1f} to {constructor['mc_total_p95']:.1f}."
        )
    lines.extend([
        "",
        "## A lower-cost option",
        "",
        f"**{affordable['name']}** has the highest expected points among drivers priced at or below the field's median price: {affordable['expected_points']:.1f} points at £{affordable['current_price']:.1f}m. That makes them a useful budget comparison, although the projection alone does not account for the rest of your team's balance.",
        "",
        "## Before locking your team",
        "",
        f"Use this as an early shortlist. Compare the current prices and uncertainty ranges on the [Drivers and Constructors pages](/), then revisit the predictions if FP3 or other weekend information changes the outlook. The [FP2 simulation snapshot](/data/predictions_round{race['round']}_post_fp2.json) behind this article is preserved. These are model estimates, not guaranteed scores.",
        "",
    ])
    return "\n".join(lines)


def publish(predictions_path=PREDICTIONS, calendar_path=CALENDAR, articles_dir=ARTICLES, today=None):
    today = today or datetime.now(timezone.utc).date()
    predictions = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    calendar = json.loads(Path(calendar_path).read_text(encoding="utf-8"))
    race = eligible_article(predictions, calendar, today)
    if race is None:
        return None
    target = Path(articles_dir) / f"{predictions['season']}-round{race['round']}-fp2-fantasy-briefing.md"
    if target.exists():
        return None
    snapshot = Path(predictions_path).with_name(f"predictions_round{race['round']}_post_fp2.json")
    if snapshot.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(predictions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    target.write_text(render_article(predictions, race), encoding="utf-8")
    return target


if __name__ == "__main__":
    result = publish()
    print(f"Created {result}" if result else "No eligible new FP2 article")
