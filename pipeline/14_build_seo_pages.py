"""14_build_seo_pages.py - generate static, crawlable per-race SEO landing pages.

The website is a single-page app, so Google only ever sees one URL with mostly
JS-rendered content. This script adds real, crawlable HTML *alongside* the app:
content-rich race-week pages for races that have predictions, early outlook
pages for upcoming horizon rounds, plus an index hub at /picks/, then refreshes
sitemap.xml.

Each page bakes the predictions into the HTML as real text (top driver and
constructor picks, best value/PPM picks, a boost/captain pick, race-specific
FAQ + structured data) and links into the live app. These pages target the big
recurring "[GP] f1 fantasy picks / tips / best team" search volume. They do NOT
replace the app - they feed it organic traffic.

Reads the already-exported web/public/data/*.json (run this AFTER
08_export_website_json.py). Pure stdlib, no external deps.

Run standalone:
    python pipeline/14_build_seo_pages.py
or as the last step of a prediction phase via run_weekend.py.
"""
from __future__ import annotations

import html
import json
import re
import runpy
import unicodedata
from datetime import datetime, timezone
from email.utils import format_datetime
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "public"
DATA = WEB / "data"
PICKS = WEB / "picks"
SITE = "https://boxboxf1fantasy.com"
YEAR = 2026
CONTACT_EMAIL = "boxboxf1fantasy@gmail.com"
INDEXNOW_KEY = "779753a5fbbf054b3ea496085a0ce1e4"

TOP_DRIVERS = 10      # rows in the "top picks" table
VALUE_DRIVERS = 6     # rows in the "best value" table
TOP_CONSTRUCTORS = 8  # rows in the constructor table


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def slugify(name: str) -> str:
    """'Monaco Grand Prix' -> 'monaco-gp-2026'."""
    s = name.lower().replace("grand prix", "gp")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return f"{s}-{YEAR}"


def short_race(name: str) -> str:
    """'Monaco Grand Prix' -> 'Monaco GP'."""
    return name.replace("Grand Prix", "GP").strip()


def plain_slug(name: str) -> str:
    """'Max Verstappen' -> 'max-verstappen'."""
    s = unicodedata.normalize("NFKD", str(name).lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def load_json(path: Path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_seed_json(name: str):
    return load_json(ROOT / "data" / "seed" / name)


def esc(x) -> str:
    return html.escape(str(x), quote=True)


MOJIBAKE_REPLACEMENTS = {
    "â€”": "-",
    "â€“": "-",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "â€˜": "'",
    "â€¦": "...",
    "â†’": "->",
    "â€”": "-",
    "â€“": "-",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "â€˜": "'",
    "â€¦": "...",
    "â†’": "->",
    "âˆ’": "-",
    "â˜°": "table",
    "ðŸ”—": "Share",
    "SÃ£o": "São",
}


def clean_legacy_text(x) -> str:
    """Repair a few old UTF-8 mojibake artifacts in legacy JSON copy."""
    s = str(x)
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        s = s.replace(bad, good)
    return s


def ld_block(objs: list) -> str:
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(objs, ensure_ascii=False, indent=1)
        + "\n</script>"
    )


def publisher_ld() -> dict:
    return {
        "@type": "Organization",
        "name": "BoxBoxF1Fantasy",
        "alternateName": ["BoxBox F1 Fantasy", "BoxBox"],
        "url": f"{SITE}/",
        "logo": f"{SITE}/logo.png",
        "email": CONTACT_EMAIL,
        "sameAs": [
            "https://x.com/BoxBoxF1Fantasy",
            "https://www.youtube.com/@BoxBoxF1Fantasy",
            "https://www.tiktok.com/@boxboxf1fantasy",
        ],
        "knowsAbout": [
            "F1 Fantasy",
            "Formula 1",
            "Fantasy sports strategy",
            "F1 Fantasy predictions",
            "F1 Fantasy lineup optimization",
            "F1 Fantasy transfer planning",
        ],
        "contactPoint": {
            "@type": "ContactPoint",
            "email": CONTACT_EMAIL,
            "contactType": "customer support",
            "availableLanguage": ["English"],
        },
    }


def webpage_ld(name: str, url: str, desc: str, page_type: str = "WebPage") -> dict:
    return {
        "@context": "https://schema.org",
        "@type": page_type,
        "name": name,
        "url": url,
        "description": desc,
        "inLanguage": "en",
        "isPartOf": {
            "@type": "WebSite",
            "name": "BoxBoxF1Fantasy",
            "url": f"{SITE}/",
        },
        "publisher": publisher_ld(),
    }


def item_list_ld(name: str, url: str, items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "url": url,
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i,
                "name": label,
                "url": item_url,
            }
            for i, (label, item_url) in enumerate(items, 1)
        ],
    }


def software_application_ld(item: dict, url: str) -> dict:
    """Structured data for free browser tools, used on /tools/... pages."""
    features = item.get("features") or [
        f"{item['crumb_self']} for F1 Fantasy 2026",
        "Free browser-based F1 Fantasy tool",
        "No login required",
    ]
    return {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": item["crumb_self"],
        "alternateName": item["title"],
        "url": url,
        "description": item["desc"],
        "applicationCategory": "SportsApplication",
        "applicationSubCategory": "Fantasy sports tool",
        "operatingSystem": "Web browser",
        "browserRequirements": "Requires JavaScript",
        "isAccessibleForFree": True,
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
        },
        "featureList": features,
        "publisher": publisher_ld(),
    }


def breadcrumb_ld(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": label, "item": url}
            for i, (label, url) in enumerate(items, 1)
        ],
    }


def _pts(item: dict) -> float:
    return float(item.get("expected_points") or 0)


def _price(item: dict) -> float:
    return float(item.get("current_price") or 0)


def fmt_date(date_text: str) -> str:
    try:
        dt = datetime.fromisoformat(str(date_text))
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except ValueError:
        return str(date_text)


def fmt_utc_datetime(date_text: str) -> str:
    try:
        dt = datetime.fromisoformat(str(date_text).replace("Z", "+00:00")).astimezone(timezone.utc)
        return f"{dt.strftime('%B')} {dt.day}, {dt.year} {dt.strftime('%H:%M')} UTC"
    except ValueError:
        return str(date_text)


def _driver_name(driver: dict) -> str:
    return f"{driver.get('first_name', '').strip()} {driver.get('last_name', '').strip()}".strip() or driver.get("driver_id", "")


def _circuit_coordinates() -> dict:
    path = ROOT / "config" / "circuit_coordinates.py"
    if not path.exists():
        return {}
    try:
        raw = runpy.run_path(str(path)).get("CIRCUIT_COORDINATES", {})
        return {clean_legacy_text(k): v for k, v in raw.items()}
    except Exception:
        return {}


CIRCUIT_COORDINATES = _circuit_coordinates()


def load_lock_deadlines() -> list[dict]:
    """Read the SPA lock-deadline table so static SEO pages match the live countdown."""
    app_js = WEB / "app.js"
    if not app_js.exists():
        return []
    text = app_js.read_text(encoding="utf-8")
    match = re.search(r"const LOCK_DEADLINES = \[(.*?)\];", text, re.S)
    if not match:
        return []
    entries = []
    pattern = re.compile(
        r"\{\s*round:\s*(?P<round>\d+),\s*race:\s*'(?P<race>[^']+)',\s*lock:\s*'(?P<lock>[^']+)',\s*sprint:\s*(?P<sprint>true|false)(?P<rest>[^}]*)\}",
        re.S,
    )
    for m in pattern.finditer(match.group(1)):
        entries.append({
            "round": int(m.group("round")),
            "race": m.group("race"),
            "lock": m.group("lock"),
            "sprint": m.group("sprint") == "true",
            "cancelled": "cancelled: true" in m.group("rest"),
        })
    return entries


def race_event_ld(race: str, race_date: str, circuit: str, canonical: str, desc: str) -> dict | None:
    """Structured data that tells crawlers a race-pick page is about a real F1 event."""
    if not race_date:
        return None

    today = datetime.now(timezone.utc).date().isoformat()
    status = "https://schema.org/EventCompleted" if race_date < today else "https://schema.org/EventScheduled"
    circuit_clean = clean_legacy_text(circuit or "")
    place = {
        "@type": "Place",
        "name": circuit_clean or clean_legacy_text(race),
    }
    coords = CIRCUIT_COORDINATES.get(circuit_clean)
    if coords:
        lat, lon, _tz = coords
        place["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": lat,
            "longitude": lon,
        }

    return {
        "@context": "https://schema.org",
        "@type": "SportsEvent",
        "name": f"{clean_legacy_text(race)} {YEAR}",
        "sport": "Formula 1",
        "url": canonical,
        "description": desc,
        "startDate": race_date,
        "eventStatus": status,
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": place,
    }


def suggested_lineup(pred: dict, budget: float = 100.0) -> dict | None:
    """Best simple current-round lineup by expected points under a normal budget.

    This is intentionally a plain public-prediction recommendation for crawlable
    SEO pages. The live optimizer remains the full interactive tool with locks,
    exclusions, chips and strategy modes.
    """
    drivers = pred.get("drivers", [])
    constructors = pred.get("constructors", [])
    if len(drivers) < 5 or len(constructors) < 2:
        return None

    con_pairs = []
    for pair in combinations(constructors, 2):
        con_pairs.append({
            "items": pair,
            "cost": sum(_price(c) for c in pair),
            "points": sum(_pts(c) for c in pair),
        })

    best = None
    for driver_combo in combinations(drivers, 5):
        driver_cost = sum(_price(d) for d in driver_combo)
        if driver_cost > budget:
            continue
        driver_points = sum(_pts(d) for d in driver_combo)
        captain = max(driver_combo, key=_pts)
        # Normal F1 Fantasy scoring doubles the best driver; add one extra copy.
        boost_points = _pts(captain)
        remaining = budget - driver_cost
        for con_pair in con_pairs:
            total_cost = driver_cost + con_pair["cost"]
            if con_pair["cost"] > remaining:
                continue
            total_points = driver_points + con_pair["points"] + boost_points
            if not best or total_points > best["points"]:
                best = {
                    "drivers": sorted(driver_combo, key=_pts, reverse=True),
                    "constructors": sorted(con_pair["items"], key=_pts, reverse=True),
                    "captain": captain,
                    "cost": total_cost,
                    "bank": budget - total_cost,
                    "points": total_points,
                    "unboosted_points": driver_points + con_pair["points"],
                    "budget": budget,
                }
    return best


def suggested_lineup_html(pred: dict) -> str:
    lineup = suggested_lineup(pred)
    if not lineup:
        return ""

    driver_rows = "".join(
        f'<tr><td>{esc(d.get("name", d.get("driver_id", "")))}</td>'
        f'<td>Driver{" / 2x boost" if d is lineup["captain"] else ""}</td>'
        f'<td class="num">${_price(d):.1f}M</td>'
        f'<td class="num">{_pts(d):.1f}</td></tr>'
        for d in lineup["drivers"]
    )
    constructor_rows = "".join(
        f'<tr><td>{esc(c.get("name", c.get("constructor_id", "")))}</td>'
        '<td>Constructor</td>'
        f'<td class="num">${_price(c):.1f}M</td>'
        f'<td class="num">{_pts(c):.1f}</td></tr>'
        for c in lineup["constructors"]
    )
    return (
        "<h2>Suggested $100M lineup</h2>"
        f'<p>This crawlable snapshot uses the current public projections and a normal 2x boost on <strong>{esc(lineup["captain"].get("name", "the top driver"))}</strong>. '
        'For locks, exclusions, chips and custom budgets, use the live Optimizer.</p>'
        '<table><thead><tr><th>Pick</th><th>Slot</th><th class="num">Price</th><th class="num">Base pts</th></tr></thead><tbody>'
        + driver_rows + constructor_rows +
        "</tbody></table>"
        f'<div class="callout"><strong>Suggested team total:</strong> {lineup["points"]:.1f} pts with normal 2x boost &middot; '
        f'<strong>Cost:</strong> ${lineup["cost"]:.1f}M &middot; <strong>Bank:</strong> ${lineup["bank"]:.1f}M.</div>'
    )


def current_captain_picks_html(pred: dict) -> str:
    drivers = sorted(pred.get("drivers", []), key=_pts, reverse=True)[:8]
    if not drivers:
        return ""

    rows = "".join(
        f'<tr><td><a href="/drivers/{plain_slug(d.get("name", d.get("driver_id", "driver")))}/">{esc(d.get("name", d.get("driver_id", "")))}</a></td>'
        f'<td class="num">{_pts(d):.1f}</td>'
        f'<td class="num">{(_pts(d) * 2):.1f}</td>'
        f'<td class="num">{(_pts(d) * 3):.1f}</td>'
        f'<td class="num">{d.get("mc_total_p5", 0):.1f}&ndash;{d.get("mc_total_p95", 0):.1f}</td>'
        f'<td class="num">{float(d.get("dnf_probability") or 0) * 100:.0f}%</td>'
        f'<td class="num">P{d.get("predicted_quali", "-")}&rarr;P{d.get("predicted_finish", "-")}</td></tr>'
        for d in drivers
    )
    leader = drivers[0]
    return (
        f'<h2>Current captain candidates: {esc(pred.get("race", "this race"))}</h2>'
        '<p>This crawlable snapshot ranks the current top driver boost candidates by expected points. '
        'Use the 90% range and DNF risk columns to separate safer captain picks from higher-volatility punts.</p>'
        '<table><thead><tr><th>Driver</th><th class="num">Base pts</th><th class="num">2x pts</th><th class="num">3x pts</th>'
        '<th class="num">90% range</th><th class="num">DNF risk</th><th class="num">Quali&rarr;Race</th></tr></thead><tbody>'
        + rows +
        "</tbody></table>"
        f'<div class="callout"><strong>Top current boost candidate:</strong> {esc(leader.get("name", "the top projected driver"))} '
        f'at {_pts(leader):.1f} base points, {(_pts(leader) * 2):.1f} with a normal 2x boost, or {(_pts(leader) * 3):.1f} with 3x Boost.</div>'
    )


def current_value_picks_html(pred: dict) -> str:
    drivers = pred.get("drivers", [])
    constructors = pred.get("constructors", [])
    if not drivers and not constructors:
        return ""

    value_drivers = sorted(drivers, key=lambda d: d.get("value_score", -999), reverse=True)[:10]
    budget_drivers = sorted(
        [d for d in drivers if _price(d) <= 12.0],
        key=lambda d: d.get("value_score", -999),
        reverse=True,
    )[:8]
    value_constructors = sorted(constructors, key=lambda c: c.get("value_score", -999), reverse=True)[:8]

    def driver_rows(items: list[dict]) -> str:
        return "".join(
            f'<tr><td><a href="/drivers/{plain_slug(d.get("name", d.get("driver_id", "driver")))}/">{esc(d.get("name", d.get("driver_id", "")))}</a></td>'
            f'<td class="num">${_price(d):.1f}M</td>'
            f'<td class="num">{_pts(d):.1f}</td>'
            f'<td class="num">{d.get("value_score", 0):.2f}</td>'
            f'<td class="num">P{d.get("predicted_quali", "-")}&rarr;P{d.get("predicted_finish", "-")}</td></tr>'
            for d in items
        )

    con_rows = "".join(
        f'<tr><td><a href="/constructors/{plain_slug(c.get("name", c.get("constructor_id", "constructor")))}/">{esc(c.get("name", c.get("constructor_id", "")))}</a></td>'
        f'<td class="num">${_price(c):.1f}M</td>'
        f'<td class="num">{_pts(c):.1f}</td>'
        f'<td class="num">{c.get("expected_pit_stop_pts", 0):.1f}</td>'
        f'<td class="num">{c.get("value_score", 0):.2f}</td></tr>'
        for c in value_constructors
    )

    return (
        "<h2>Best value drivers this week</h2>"
        '<p>Sorted by projected points per million (PPM). These are not always the top raw scorers; they are the picks giving the most projected return for their price.</p>'
        '<table><thead><tr><th>Driver</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">PPM</th><th class="num">Quali&rarr;Race</th></tr></thead><tbody>'
        + driver_rows(value_drivers) +
        "</tbody></table>"
        "<h2>Budget driver picks</h2>"
        '<p>Cheap picks can unlock premium drivers or constructors elsewhere. This table filters to drivers at $12.0M or less, then sorts by value.</p>'
        '<table><thead><tr><th>Driver</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">PPM</th><th class="num">Quali&rarr;Race</th></tr></thead><tbody>'
        + driver_rows(budget_drivers) +
        "</tbody></table>"
        "<h2>Best value constructors</h2>"
        '<p>Constructor value includes both listed drivers, qualifying teamwork bonus, pit-stop points and DNF risk.</p>'
        '<table><thead><tr><th>Constructor</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">Pit pts</th><th class="num">PPM</th></tr></thead><tbody>'
        + con_rows +
        "</tbody></table>"
    )


def current_price_changes_html(pred: dict) -> str:
    drivers = pred.get("drivers", [])
    constructors = pred.get("constructors", [])
    if not drivers and not constructors:
        return ""

    driver_risers = sorted(
        drivers,
        key=lambda d: (d.get("value_score", -999), d.get("expected_points", -999)),
        reverse=True,
    )[:8]
    driver_pressure = sorted(
        drivers,
        key=lambda d: (d.get("value_score", 999), d.get("expected_points", 999)),
    )[:8]
    constructor_risers = sorted(
        constructors,
        key=lambda c: (c.get("value_score", -999), c.get("expected_points", -999)),
        reverse=True,
    )[:6]
    constructor_pressure = sorted(
        constructors,
        key=lambda c: (c.get("value_score", 999), c.get("expected_points", 999)),
    )[:6]

    def driver_rows(items: list[dict], pressure: bool = False) -> str:
        return "".join(
            f'<tr><td><a href="/drivers/{plain_slug(d.get("name", d.get("driver_id", "driver")))}/">{esc(d.get("name", d.get("driver_id", "")))}</a></td>'
            f'<td>{esc(d.get("constructor", ""))}</td>'
            f'<td class="num">${_price(d):.1f}M</td>'
            f'<td class="num">{_pts(d):.1f}</td>'
            f'<td class="num">{d.get("value_score", 0):.2f}</td>'
            f'<td>{esc("Drop-pressure watch" if pressure else "Rise watch")}</td></tr>'
            for d in items
        )

    def constructor_rows(items: list[dict], pressure: bool = False) -> str:
        return "".join(
            f'<tr><td><a href="/constructors/{plain_slug(c.get("name", c.get("constructor_id", "constructor")))}/">{esc(c.get("name", c.get("constructor_id", "")))}</a></td>'
            f'<td class="num">${_price(c):.1f}M</td>'
            f'<td class="num">{_pts(c):.1f}</td>'
            f'<td class="num">{float(c.get("expected_pit_stop_pts") or 0):.1f}</td>'
            f'<td class="num">{c.get("value_score", 0):.2f}</td>'
            f'<td>{esc("Drop-pressure watch" if pressure else "Rise watch")}</td></tr>'
            for c in items
        )

    return (
        f'<h2>Current price-change watchlist: {esc(pred.get("race", "current race"))}</h2>'
        '<p>This crawlable watchlist uses public projection signals: expected points, current price and points-per-million/value rating. '
        'It is a practical fantasy-budget screen, not an official price-change guarantee.</p>'
        "<h3>Drivers most likely to attract price-rise interest</h3>"
        '<table><thead><tr><th>Driver</th><th>Team</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">Value</th><th>Signal</th></tr></thead><tbody>'
        + driver_rows(driver_risers) +
        "</tbody></table>"
        "<h3>Drivers under price-drop pressure</h3>"
        '<table><thead><tr><th>Driver</th><th>Team</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">Value</th><th>Signal</th></tr></thead><tbody>'
        + driver_rows(driver_pressure, pressure=True) +
        "</tbody></table>"
        "<h3>Constructor price-rise watch</h3>"
        '<table><thead><tr><th>Constructor</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">Pit pts</th><th class="num">Value</th><th>Signal</th></tr></thead><tbody>'
        + constructor_rows(constructor_risers) +
        "</tbody></table>"
        "<h3>Constructors under price-drop pressure</h3>"
        '<table><thead><tr><th>Constructor</th><th class="num">Price</th><th class="num">Exp. pts</th><th class="num">Pit pts</th><th class="num">Value</th><th>Signal</th></tr></thead><tbody>'
        + constructor_rows(constructor_pressure, pressure=True) +
        "</tbody></table>"
    )


def current_deadlines_html() -> str:
    deadlines = load_lock_deadlines()
    if not deadlines:
        return ""

    now = datetime.now(timezone.utc)
    active = [d for d in deadlines if not d.get("cancelled")]
    next_deadline = None
    for d in active:
        try:
            lock_dt = datetime.fromisoformat(d["lock"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if lock_dt > now:
            next_deadline = d | {"lock_dt": lock_dt}
            break

    rows = []
    for d in deadlines:
        lock_text = fmt_utc_datetime(d["lock"])
        if d.get("cancelled"):
            status = "Cancelled"
        else:
            try:
                status = "Upcoming" if datetime.fromisoformat(d["lock"].replace("Z", "+00:00")).astimezone(timezone.utc) > now else "Past"
            except ValueError:
                status = ""
        lock_type = "Sprint race lock" if d.get("sprint") else "Qualifying lock"
        rows.append(
            f'<tr><td>R{d["round"]}</td><td>{esc(d["race"])}</td><td>{esc(lock_type)}</td>'
            f'<td class="num">{esc(lock_text)}</td><td>{esc(status)}</td></tr>'
        )

    if next_deadline:
        next_html = (
            f'<div class="callout"><strong>Next F1 Fantasy deadline:</strong> R{next_deadline["round"]} '
            f'{esc(next_deadline["race"])} locks at <strong>{esc(fmt_utc_datetime(next_deadline["lock"]))}</strong>. '
            f'This is a {"sprint race" if next_deadline.get("sprint") else "qualifying"} lock deadline.</div>'
        )
    else:
        next_html = '<div class="callout"><strong>No upcoming 2026 lock deadline is currently listed.</strong> Check the live app for the latest season state.</div>'

    return (
        "<h2>F1 Fantasy lock deadline table</h2>"
        + next_html +
        "<p>Times are shown in UTC. The live site header converts the next deadline to your browser's local time and counts down automatically.</p>"
        '<table><thead><tr><th>Round</th><th>Race</th><th>Deadline type</th><th class="num">Lock time</th><th>Status</th></tr></thead><tbody>'
        + "".join(rows) +
        "</tbody></table>"
    )


def current_points_calculator_html(pred: dict) -> str:
    drivers = sorted(pred.get("drivers", []), key=_pts, reverse=True)
    constructors = sorted(pred.get("constructors", []), key=_pts, reverse=True)
    if not drivers and not constructors:
        return ""

    driver_rows = "".join(
        f'<tr><td><a href="/drivers/{plain_slug(d.get("name", d.get("driver_id", "driver")))}/">{esc(d.get("name", d.get("driver_id", "")))}</a></td>'
        f'<td class="num">{_pts(d):.1f}</td>'
        f'<td class="num">{float(d.get("expected_points_quali") or 0):.1f}</td>'
        f'<td class="num">{float(d.get("expected_points_race") or 0):.1f}</td>'
        f'<td class="num">{float(d.get("expected_overtakes") or 0):.1f}</td>'
        f'<td class="num">{d.get("mc_total_p5", 0):.1f}&ndash;{d.get("mc_total_p95", 0):.1f}</td>'
        f'<td class="num">${_price(d):.1f}M</td></tr>'
        for d in drivers
    )
    constructor_rows = "".join(
        f'<tr><td><a href="/constructors/{plain_slug(c.get("name", c.get("constructor_id", "constructor")))}/">{esc(c.get("name", c.get("constructor_id", "")))}</a></td>'
        f'<td class="num">{_pts(c):.1f}</td>'
        f'<td class="num">{float(c.get("expected_points_quali") or 0):.1f}</td>'
        f'<td class="num">{float(c.get("expected_points_race") or 0):.1f}</td>'
        f'<td class="num">{float(c.get("expected_pit_stop_pts") or 0):.1f}</td>'
        f'<td class="num">{c.get("mc_total_p5", 0):.1f}&ndash;{c.get("mc_total_p95", 0):.1f}</td>'
        f'<td class="num">${_price(c):.1f}M</td></tr>'
        for c in constructors
    )
    return (
        f'<h2>Projected points table: {esc(pred.get("race", "current race"))}</h2>'
        '<p>Current expected fantasy points by pick, with the main scoring components exposed as crawlable data. '
        'The live app has the full cards, scenario sliders and sorting controls.</p>'
        '<table><thead><tr><th>Driver</th><th class="num">Exp. pts</th><th class="num">Quali</th><th class="num">Race</th>'
        '<th class="num">Overtakes</th><th class="num">90% range</th><th class="num">Price</th></tr></thead><tbody>'
        + driver_rows +
        "</tbody></table>"
        "<h2>Constructor projected points</h2>"
        '<table><thead><tr><th>Constructor</th><th class="num">Exp. pts</th><th class="num">Quali</th><th class="num">Race</th>'
        '<th class="num">Pit stops</th><th class="num">90% range</th><th class="num">Price</th></tr></thead><tbody>'
        + constructor_rows +
        "</tbody></table>"
    )


# GA4 snippet. Plain (non-f) string so the JS braces survive. Unlike the SPA,
# each static page is a real distinct URL, so we let gtag fire its automatic
# page_view per page (no send_page_view:false) - they show up directly in GA's
# Pages report. googletagmanager/google-analytics are allowed by the site CSP.
GA_SNIPPET = """<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-T3HS76FJ7W"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', 'G-T3HS76FJ7W');
</script>"""


def page_head(title: str, desc: str, canonical: str, extra_ld: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{GA_SNIPPET}
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#0a0d12">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BoxBoxF1Fantasy">
<meta property="og:locale" content="en_US">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@BoxBoxF1Fantasy">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{SITE}/og-image.png">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="alternate" type="application/rss+xml" title="BoxBoxF1Fantasy updates" href="/feed.xml">
<link rel="alternate" type="application/feed+json" title="BoxBoxF1Fantasy updates" href="/feed.json">
<link rel="service-desc" type="application/openapi+json" title="BoxBoxF1Fantasy public data OpenAPI" href="/openapi.json">
<link rel="alternate" type="text/plain" title="LLMs guide" href="/llms.txt">
<link rel="alternate" type="text/plain" title="LLMs full site summary" href="/llms-full.txt">
<link rel="alternate" type="application/json" title="BoxBoxF1Fantasy site index" href="/search-index.json">
<link rel="author" type="text/plain" href="/humans.txt">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/picks/picks.css">
{extra_ld}
</head>
<body>
<div class="topbar"><div class="wrap">
  <a class="brand" href="/">BoxBox<span class="ac">F1</span>Fantasy</a>
  <a class="cta" href="/">Open live predictions &amp; tools &rarr;</a>
</div></div>
<main class="wrap">
"""


FOOTER = f"""</main>
<footer class="footer"><div class="wrap">
<p class="footnav"><a href="/">Predictions &amp; Tools</a> &middot; <a href="/picks/">Race Picks</a> &middot; <a href="/drivers/">Drivers</a> &middot; <a href="/constructors/">Constructors</a> &middot; <a href="/accuracy/">Accuracy</a> &middot; <a href="/changelog/">Changelog</a> &middot; <a href="/videos/">Videos</a> &middot; <a href="/articles/">Articles</a> &middot; <a href="/data/">Data</a> &middot; <a href="/guides/">Guides</a> &middot; <a href="/tools/">Tools</a> &middot; <a href="/about/">About</a> &middot; <a href="/privacy/">Privacy</a></p>
<p><a href="/">BoxBoxF1Fantasy</a> &mdash; free, data-driven F1 Fantasy predictions, a lineup optimizer and transfer tools for the {YEAR} season. Predictions are for entertainment only; Formula 1 is unpredictable.</p>
<p>Not affiliated with Formula 1, the FIA, or any F1 team or driver.</p>
</div></footer>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# per-race page
# --------------------------------------------------------------------------- #
def render_race_page(pred: dict, is_current: bool) -> tuple[str, str]:
    race = pred["race"]
    rn = pred["round"]
    short = short_race(race)
    slug = slugify(race)
    canonical = f"{SITE}/picks/{slug}/"
    gen_date = (pred.get("generated_at") or pred.get("exported_at") or "")[:10]

    drivers = pred.get("drivers", [])
    cons = pred.get("constructors", [])
    cmap = {c["constructor_id"]: c.get("name", c["constructor_id"]) for c in cons}

    by_pts = sorted(drivers, key=lambda d: d.get("expected_points", 0), reverse=True)
    by_val = sorted(drivers, key=lambda d: d.get("value_score", 0), reverse=True)
    cons_by_pts = sorted(cons, key=lambda c: c.get("expected_points", 0), reverse=True)
    captain = by_pts[0] if by_pts else None
    best_value = by_val[0] if by_val else None
    top3 = ", ".join(d["name"] for d in by_pts[:3])

    title = f"F1 Fantasy {short} {YEAR}: Best Picks, Captain & Tips | BoxBox"
    if is_current:
        desc = (f"Free F1 Fantasy picks for the upcoming {race} {YEAR}: top driver and "
                f"constructor predictions, best value (PPM) picks, the boost/captain pick "
                f"and a suggested lineup. Updated for race week.")
    else:
        desc = (f"Our F1 Fantasy predictions for the {race} {YEAR} (round {rn}): top driver "
                f"and constructor picks, best value (PPM) picks and the captain pick.")

    # --- top drivers table ---
    drows = []
    for i, d in enumerate(by_pts[:TOP_DRIVERS], 1):
        team = cmap.get(d.get("constructor"), str(d.get("constructor", "")).title())
        drows.append(
            f'<tr><td class="num">{i}</td><td>{esc(d["name"])}</td><td>{esc(team)}</td>'
            f'<td class="num">${d.get("current_price",0):.1f}M</td>'
            f'<td class="num">P{d.get("predicted_quali","-")}&rarr;P{d.get("predicted_finish","-")}</td>'
            f'<td class="num">{d.get("expected_points",0):.1f}</td>'
            f'<td class="num">{d.get("value_score",0):.2f}</td></tr>'
        )
    drivers_table = (
        '<table><thead><tr><th class="num">#</th><th>Driver</th><th>Team</th>'
        '<th class="num">Price</th><th class="num">Quali&rarr;Race</th>'
        '<th class="num">Pred. pts</th><th class="num">PPM</th></tr></thead><tbody>'
        + "".join(drows) + "</tbody></table>"
    )

    # --- value table ---
    vrows = []
    for d in by_val[:VALUE_DRIVERS]:
        team = cmap.get(d.get("constructor"), str(d.get("constructor", "")).title())
        vrows.append(
            f'<tr><td>{esc(d["name"])}</td><td>{esc(team)}</td>'
            f'<td class="num">${d.get("current_price",0):.1f}M</td>'
            f'<td class="num">{d.get("expected_points",0):.1f}</td>'
            f'<td class="num">{d.get("value_score",0):.2f}</td></tr>'
        )
    value_table = (
        '<table><thead><tr><th>Driver</th><th>Team</th><th class="num">Price</th>'
        '<th class="num">Pred. pts</th><th class="num">PPM</th></tr></thead><tbody>'
        + "".join(vrows) + "</tbody></table>"
    )

    # --- constructors table ---
    crows = []
    for c in cons_by_pts[:TOP_CONSTRUCTORS]:
        crows.append(
            f'<tr><td>{esc(c.get("name", c["constructor_id"]))}</td>'
            f'<td class="num">${c.get("current_price",0):.1f}M</td>'
            f'<td class="num">{c.get("expected_points",0):.1f}</td>'
            f'<td class="num">{c.get("expected_pit_stop_pts",0):.1f}</td>'
            f'<td class="num">{c.get("value_score",0):.2f}</td></tr>'
        )
    cons_table = (
        '<table><thead><tr><th>Constructor</th><th class="num">Price</th>'
        '<th class="num">Pred. pts</th><th class="num">Pit-stop pts</th>'
        '<th class="num">PPM</th></tr></thead><tbody>'
        + "".join(crows) + "</tbody></table>"
    )

    cap_line = ""
    if captain:
        cap_line = (
            f'<div class="callout"><strong>Boost / captain pick: {esc(captain["name"])}</strong>'
            f' &mdash; our highest projected scorer at the {esc(short)} '
            f'(~{captain.get("expected_points",0):.0f} pts). This is the driver to put your '
            f'<strong>3x Boost</strong> or <strong>Autopilot</strong> chip on. For value, '
            f'{esc(best_value["name"]) if best_value else "see the table"} offers the best points per million.</div>'
        )

    when = (f"Predictions for the upcoming round &mdash; updated through race week."
            if is_current else
            f"Our archived predictions for round {rn}. The race has run &mdash; "
            f'see how the model did in the <a href="/#accuracy">Accuracy</a> tab.')

    intro = (
        f'<p class="lede">Free, data-driven F1 Fantasy picks for the <strong>{esc(race)}</strong> '
        f'(round {rn}, {YEAR}). Below are the model\'s top driver and constructor picks, the best '
        f'value (points-per-million) options, and the pick to captain. {when}</p>'
        f'<p class="meta">Predictions generated {esc(gen_date)} &middot; '
        f'machine-learning models + 10,000-run Monte Carlo simulation.</p>'
    )

    cta = (
        '<div class="btnrow">'
        '<a class="cta" href="/#optimizer">Build your optimal team in the Optimizer &rarr;</a>'
        '<a class="cta" href="/" style="background:#1b212c;">See live driver cards &rarr;</a>'
        '</div>'
    )

    # --- FAQ (visible + structured) ---
    faqs = [
        (f"Who are the best F1 Fantasy picks for the {short}?",
         f"Our model's top projected scorers for the {race} are {top3}. "
         f"For value, {best_value['name'] if best_value else 'the leaders'} offers the best "
         f"points per million. The full ranked list is in the table above."),
        (f"What's the best F1 Fantasy team for the {short}?",
         "Build it in seconds with our free Optimizer, which checks all 1.4 million legal "
         "5-driver, 2-constructor lineups within your budget. The picks on this page are the "
         "building blocks for it."),
        (f"How are these {short} predictions made?",
         "Machine-learning models trained on 2020-2026 data predict qualifying and race "
         "positions, then a 10,000-run Monte Carlo simulation turns them into expected fantasy "
         "points. Predictions sharpen as practice and qualifying data arrive across the weekend."),
    ]
    faq_html = "".join(
        f'<p class="faq-q">{esc(q)}</p><p class="faq-a">{esc(a)}</p>' for q, a in faqs
    )

    ld_objs = [
        {
            **webpage_ld(title, canonical, desc, "Article"),
            "headline": title,
            "dateModified": gen_date or datetime.now(timezone.utc).date().isoformat(),
            "about": [
                "F1 Fantasy",
                race,
                f"{short} {YEAR}",
                "Fantasy sports predictions",
            ],
        },
        item_list_ld(
            f"Top F1 Fantasy driver picks for {short} {YEAR}",
            canonical,
            [(d["name"], canonical) for d in by_pts[:TOP_DRIVERS]],
        ),
        item_list_ld(
            f"Top F1 Fantasy constructor picks for {short} {YEAR}",
            canonical,
            [(c.get("name", c["constructor_id"]), canonical) for c in cons_by_pts[:TOP_CONSTRUCTORS]],
        ),
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "F1 Fantasy Picks", "item": f"{SITE}/picks/"},
                {"@type": "ListItem", "position": 3, "name": f"{short} {YEAR}", "item": canonical},
            ],
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ]
    event = race_event_ld(race, pred.get("date", ""), pred.get("circuit", ""), canonical, desc)
    if event:
        ld_objs.append(event)
    ld = ld_block(ld_objs)

    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/picks/">Picks</a> &rsaquo; {esc(short)} {YEAR}</p>'
        f"<h1>F1 Fantasy Picks: {esc(race)} {YEAR}</h1>"
        + intro
        + cap_line
        + cta
        + suggested_lineup_html(pred)
        + "<h2>Top driver picks</h2>"
        + f"<p>Ranked by predicted fantasy points for the {esc(short)}. PPM = points per $million (value).</p>"
        + drivers_table
        + "<h2>Best value picks (PPM)</h2>"
        + "<p>The most points per $million spent &mdash; the budget-stretchers that let you afford a premium elsewhere.</p>"
        + value_table
        + "<h2>Top constructor picks</h2>"
        + "<p>Constructors score both their drivers' points plus pit-stop points and a qualifying bonus &mdash; don't overlook them.</p>"
        + cons_table
        + "<h2>FAQ</h2>"
        + faq_html
        + cta
    )

    return slug, page_head(title, desc, canonical, ld) + body + FOOTER


def hydrate_horizon_round(
    round_info: dict,
    horizon_round: dict,
    drivers_seed: dict,
    constructors_seed: dict,
    prices: dict,
) -> dict:
    """Convert compact horizon_projections.json data into a page-friendly shape."""
    driver_prices = prices.get("drivers", {}) if isinstance(prices, dict) else {}
    constructor_prices = prices.get("constructors", {}) if isinstance(prices, dict) else {}
    constructor_names = {cid: c.get("name", cid.replace("_", " ").title()) for cid, c in constructors_seed.items()}

    drivers = []
    for driver_id, projection in (horizon_round.get("drivers") or {}).items():
        seed = drivers_seed.get(driver_id, {})
        constructor_id = seed.get("constructor_id", "")
        price = float(driver_prices.get(driver_id, {}).get("current_price") or 0)
        expected = float(projection.get("expected_points") or 0)
        breakdown = projection.get("breakdown") or {}
        drivers.append({
            "driver_id": driver_id,
            "name": _driver_name(seed) or driver_id,
            "constructor": constructor_id,
            "constructor_name": constructor_names.get(constructor_id, constructor_id.replace("_", " ").title()),
            "number": seed.get("number"),
            "predicted_quali": projection.get("predicted_quali"),
            "predicted_finish": projection.get("predicted_race"),
            "predicted_sprint": projection.get("predicted_sprint"),
            "expected_points": expected,
            "expected_points_quali": float(breakdown.get("quali_pts") or 0),
            "expected_points_race": float(breakdown.get("race_pts") or 0),
            "current_price": price,
            "value_score": expected / price if price else 0,
        })

    constructors = []
    for constructor_id, projection in (horizon_round.get("constructors") or {}).items():
        seed = constructors_seed.get(constructor_id, {})
        price = float(constructor_prices.get(constructor_id, {}).get("current_price") or 0)
        expected = float(projection.get("expected_points") or 0)
        constructor_drivers = list(projection.get("drivers") or [])
        constructors.append({
            "constructor_id": constructor_id,
            "name": seed.get("name", constructor_id.replace("_", " ").title()),
            "full_name": seed.get("full_name", seed.get("name", constructor_id)),
            "driver_1": constructor_drivers[0] if len(constructor_drivers) > 0 else None,
            "driver_2": constructor_drivers[1] if len(constructor_drivers) > 1 else None,
            "expected_points": expected,
            "current_price": price,
            "value_score": expected / price if price else 0,
        })

    return {
        "round": round_info.get("round", horizon_round.get("round")),
        "race": clean_legacy_text(round_info.get("name", horizon_round.get("name", "Grand Prix"))),
        "date": round_info.get("date", ""),
        "circuit": clean_legacy_text(round_info.get("circuit", horizon_round.get("circuit", ""))),
        "is_sprint": bool(round_info.get("sprint") or horizon_round.get("is_sprint")),
        "generated_at": horizon_round.get("generated_at", ""),
        "drivers": drivers,
        "constructors": constructors,
    }


def render_future_race_page(pred: dict, horizon_generated_at: str = "") -> tuple[str, str]:
    """Crawlable early-outlook page for future rounds from horizon projections."""
    race = clean_legacy_text(pred["race"])
    rn = pred["round"]
    short = short_race(race)
    slug = slugify(race)
    canonical = f"{SITE}/picks/{slug}/"
    race_date = fmt_date(pred.get("date", ""))
    gen_date = (horizon_generated_at or pred.get("generated_at") or datetime.now(timezone.utc).isoformat())[:10]
    sprint_note = " This is currently listed as a sprint weekend, so sprint scoring and chip timing may matter more than usual." if pred.get("is_sprint") else ""

    drivers = sorted(pred.get("drivers", []), key=lambda d: d.get("expected_points", 0), reverse=True)
    constructors = sorted(pred.get("constructors", []), key=lambda c: c.get("expected_points", 0), reverse=True)
    value_drivers = sorted(drivers, key=lambda d: d.get("value_score", 0), reverse=True)
    top3 = ", ".join(d["name"] for d in drivers[:3])
    best_value = value_drivers[0] if value_drivers else None
    captain = drivers[0] if drivers else None

    title = f"F1 Fantasy {short} {YEAR}: Early Picks & Transfer Outlook | BoxBox"
    desc = (f"Early F1 Fantasy outlook for the {race} {YEAR}: horizon projections, top drivers, "
            f"constructor options and transfer-planning notes before race-week practice data arrives.")

    driver_rows = []
    for i, d in enumerate(drivers[:TOP_DRIVERS], 1):
        driver_rows.append(
            f'<tr><td class="num">{i}</td><td>{esc(d["name"])}</td><td>{esc(d.get("constructor_name", ""))}</td>'
            f'<td class="num">${d.get("current_price", 0):.1f}M</td>'
            f'<td class="num">P{d.get("predicted_quali", "-")}&rarr;P{d.get("predicted_finish", "-")}</td>'
            f'<td class="num">{d.get("expected_points", 0):.1f}</td>'
            f'<td class="num">{d.get("value_score", 0):.2f}</td></tr>'
        )

    constructor_rows = []
    for c in constructors[:TOP_CONSTRUCTORS]:
        driver_names = " / ".join(
            d["name"] for did in [c.get("driver_1"), c.get("driver_2")]
            for d in drivers if d.get("driver_id") == did
        )
        constructor_rows.append(
            f'<tr><td>{esc(c.get("name", c.get("constructor_id", "")))}</td>'
            f'<td>{esc(driver_names)}</td>'
            f'<td class="num">${c.get("current_price", 0):.1f}M</td>'
            f'<td class="num">{c.get("expected_points", 0):.1f}</td>'
            f'<td class="num">{c.get("value_score", 0):.2f}</td></tr>'
        )

    value_rows = []
    for d in value_drivers[:VALUE_DRIVERS]:
        value_rows.append(
            f'<tr><td>{esc(d["name"])}</td><td>{esc(d.get("constructor_name", ""))}</td>'
            f'<td class="num">${d.get("current_price", 0):.1f}M</td>'
            f'<td class="num">{d.get("expected_points", 0):.1f}</td>'
            f'<td class="num">{d.get("value_score", 0):.2f}</td></tr>'
        )

    cap_line = ""
    if captain:
        cap_line = (
            f'<div class="callout"><strong>Early top scorer: {esc(captain["name"])}</strong>'
            f' &mdash; the horizon model currently has {esc(captain["name"])} as the top raw scorer for the {esc(short)} '
            f'(~{captain.get("expected_points", 0):.0f} pts). Treat this as a transfer-planning signal until race-week practice data lands.</div>'
        )

    faqs = [
        (f"Are these {short} picks final?",
         "No. This is an early horizon outlook for planning transfers before race-week telemetry, weather and session results are available. The full race-week page updates when the prediction pipeline runs for the round."),
        (f"Who are the early best F1 Fantasy picks for the {short}?",
         f"The current horizon projection likes {top3 or 'the leading current-form picks'} as the top raw scorers. "
         f"For value, {best_value['name'] if best_value else 'check the value table'} currently screens best by points per million."),
        (f"When will the {short} predictions update?",
         "The page becomes sharper across race week: pre-FP predictions use priors, post-FP predictions add practice pace, and post-quali predictions can include the actual grid."),
    ]

    ld_objs = [
        {
            **webpage_ld(title, canonical, desc, "Article"),
            "headline": title,
            "dateModified": gen_date,
            "about": ["F1 Fantasy", race, f"{short} {YEAR}", "F1 Fantasy transfer planning"],
        },
        item_list_ld(
            f"Early F1 Fantasy driver outlook for {short} {YEAR}",
            canonical,
            [(d["name"], canonical) for d in drivers[:TOP_DRIVERS]],
        ),
        item_list_ld(
            f"Early F1 Fantasy constructor outlook for {short} {YEAR}",
            canonical,
            [(c.get("name", c.get("constructor_id", "")), canonical) for c in constructors[:TOP_CONSTRUCTORS]],
        ),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("F1 Fantasy Picks", f"{SITE}/picks/"),
            (f"{short} {YEAR}", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ]
    event = race_event_ld(race, pred.get("date", ""), pred.get("circuit", ""), canonical, desc)
    if event:
        ld_objs.append(event)
    ld = ld_block(ld_objs)

    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/picks/">Picks</a> &rsaquo; {esc(short)} {YEAR}</p>'
        f"<h1>F1 Fantasy Early Outlook: {esc(race)} {YEAR}</h1>"
        f'<p class="lede">Early, data-driven F1 Fantasy planning notes for the <strong>{esc(race)}</strong> '
        f'(round {rn}, {YEAR}, scheduled for {esc(race_date)} at {esc(pred.get("circuit", ""))}). '
        f'These horizon projections are designed for transfer planning before race-week practice data is available.{sprint_note}</p>'
        f'<p class="meta">Horizon projection generated {esc(gen_date)} &middot; final race-week predictions will update when the pipeline runs for this round.</p>'
        '<div class="callout"><strong>Early outlook, not final picks.</strong> Use this page to plan transfers and watch-list drivers. Recheck the live predictions after FP sessions, qualifying and weather updates.</div>'
        + cap_line
        + '<div class="btnrow"><a class="cta" href="/#optimizer">Open Transfer Planner &amp; Optimizer &rarr;</a><a class="cta" href="/data/horizon_projections.json" style="background:#1b212c;">View horizon JSON &rarr;</a></div>'
        + "<h2>Early driver outlook</h2>"
        + f"<p>Ranked by early projected fantasy points for the {esc(short)}. PPM = projected points per $million.</p>"
        + '<table><thead><tr><th class="num">#</th><th>Driver</th><th>Team</th><th class="num">Price</th><th class="num">Quali&rarr;Race</th><th class="num">Early pts</th><th class="num">PPM</th></tr></thead><tbody>'
        + "".join(driver_rows)
        + "</tbody></table>"
        + "<h2>Early value picks</h2>"
        + "<p>These picks screen best on points per million in the horizon model, which can help when planning future budget shape.</p>"
        + '<table><thead><tr><th>Driver</th><th>Team</th><th class="num">Price</th><th class="num">Early pts</th><th class="num">PPM</th></tr></thead><tbody>'
        + "".join(value_rows)
        + "</tbody></table>"
        + "<h2>Early constructor outlook</h2>"
        + "<p>Constructor values here are horizon projections before race-week pit-stop, weather and telemetry refinements.</p>"
        + '<table><thead><tr><th>Constructor</th><th>Drivers</th><th class="num">Price</th><th class="num">Early pts</th><th class="num">PPM</th></tr></thead><tbody>'
        + "".join(constructor_rows)
        + "</tbody></table>"
        + "<h2>How to use this before race week</h2>"
        + "<ul><li>Use it to shortlist transfer targets several rounds ahead.</li><li>Check whether a premium pick is worth holding through this circuit profile.</li><li>Re-run decisions in the live Team Compare and Optimizer once race-week predictions are published.</li></ul>"
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return slug, page_head(title, desc, canonical, ld) + body + FOOTER


def _feature_label(value, high: str, mid: str, low: str) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    if v >= 7:
        return high
    if v <= 4:
        return low
    return mid


def _race_track_features(race_name: str, track_data: dict) -> tuple[str, dict]:
    circuit_id = (track_data.get("race_circuit_map") or {}).get(race_name, "")
    features = (track_data.get("track_features") or {}).get(circuit_id, {})
    return circuit_id, features


def render_calendar_race_page(round_info: dict, track_data: dict) -> tuple[str, str]:
    """Crawlable calendar/strategy page for future races before horizon projections exist."""
    race = clean_legacy_text(round_info.get("name", "Grand Prix"))
    rn = round_info.get("round")
    short = short_race(race)
    slug = slugify(race)
    canonical = f"{SITE}/picks/{slug}/"
    race_date = fmt_date(round_info.get("date", ""))
    circuit = clean_legacy_text(round_info.get("circuit", ""))
    circuit_id, features = _race_track_features(race, track_data)
    is_sprint = bool(round_info.get("sprint"))

    title = f"F1 Fantasy {short} {YEAR}: Early Strategy Watchlist | BoxBox"
    desc = (
        f"Early F1 Fantasy strategy watchlist for the {race} {YEAR}: race date, sprint status, "
        "circuit traits and what to monitor before projections are published."
    )

    overtaking = _feature_label(features.get("overtaking_difficulty"), "hard to pass", "moderate passing", "overtaking-friendly")
    downforce = _feature_label(features.get("downforce_level"), "high downforce", "balanced downforce", "low downforce")
    straight = _feature_label(features.get("straight_line_importance"), "straight-line speed matters", "balanced speed/handling", "less straight-line dependent")
    safety_car = _feature_label(features.get("safety_car_probability"), "high safety-car risk", "moderate safety-car risk", "lower safety-car risk")
    street = "street circuit" if features.get("is_street") else "permanent circuit"

    rows = []
    for label, key in [
        ("Street circuit", "is_street"),
        ("Overtaking difficulty", "overtaking_difficulty"),
        ("Average corner speed", "avg_corner_speed"),
        ("Straight-line importance", "straight_line_importance"),
        ("Downforce level", "downforce_level"),
        ("Turn 1 incident risk", "turn1_incident_risk"),
        ("Safety-car probability", "safety_car_probability"),
        ("Track evolution", "track_evolution"),
        ("Grip level", "grip_level"),
    ]:
        value = features.get(key, "-")
        if key == "is_street" and value != "-":
            value = "Yes" if value else "No"
        rows.append(f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>")
    feature_table = "<table><tbody>" + "".join(rows) + "</tbody></table>" if rows else ""

    faqs = [
        (f"Are {short} F1 Fantasy predictions available yet?",
         "Not yet. This is an early calendar and strategy watchlist page. BoxBox publishes full driver and constructor projections when the prediction pipeline reaches this round."),
        (f"What should I watch before the {short}?",
         f"Watch practice pace, qualifying confidence, DNF risk, weather and whether the {short} circuit traits favour overtaking, qualifying position or straight-line speed."),
        (f"Will this page update with picks?",
         "Yes. Once projections are exported for this round, this URL is replaced with the full race-pick page containing ranked driver picks, constructor picks, value picks and captain guidance."),
    ]

    ld_objs = [
        {
            **webpage_ld(title, canonical, desc, "Article"),
            "headline": title,
            "dateModified": datetime.now(timezone.utc).date().isoformat(),
            "about": ["F1 Fantasy", race, f"{short} {YEAR}", "F1 Fantasy strategy"],
        },
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("F1 Fantasy Picks", f"{SITE}/picks/"),
            (f"{short} {YEAR}", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ]
    event = race_event_ld(race, round_info.get("date", ""), circuit, canonical, desc)
    if event:
        ld_objs.append(event)
    ld = ld_block(ld_objs)

    sprint_note = "It is currently listed as a sprint weekend, so chip timing and extra sprint scoring may matter more than usual." if is_sprint else "It is currently listed as a standard race weekend."
    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/picks/">Picks</a> &rsaquo; {esc(short)} {YEAR}</p>'
        f"<h1>F1 Fantasy Strategy Watchlist: {esc(race)} {YEAR}</h1>"
        f'<p class="lede">A crawlable early watchlist for the <strong>{esc(race)}</strong> '
        f'(round {rn}, scheduled for {esc(race_date)} at {esc(circuit)}). Full race-week projections are not published for this round yet.</p>'
        f'<p class="meta">Circuit profile: {esc(street)} &middot; {esc(overtaking)} &middot; {esc(downforce)} &middot; {esc(straight)} &middot; {esc(safety_car)}.</p>'
        f'<div class="callout"><strong>Watchlist only.</strong> {esc(sprint_note)} Recheck this URL once the prediction pipeline reaches the round for ranked picks, value picks and captain guidance.</div>'
        '<div class="btnrow"><a class="cta" href="/#optimizer">Open live Optimizer &amp; Planner &rarr;</a><a class="cta" href="/data/track_data.json" style="background:#1b212c;">View track data JSON &rarr;</a></div>'
        "<h2>Fantasy strategy notes</h2>"
        f"<p>The {esc(short)} currently screens as a {esc(street)} with {esc(overtaking)} conditions and {esc(safety_car)}. Before locking transfers, watch whether the weekend starts to reward qualifying position, DNF avoidance, straight-line speed or overtaking volume.</p>"
        "<ul>"
        f"<li><strong>Passing:</strong> {esc(overtaking.capitalize())}; this affects positions-gained and comeback potential.</li>"
        f"<li><strong>Car profile:</strong> {esc(downforce.capitalize())} and {esc(straight)} can influence which teams suit the circuit.</li>"
        f"<li><strong>Risk:</strong> {esc(safety_car.capitalize())}; high disruption can widen confidence ranges and make No Negative-style protection more attractive.</li>"
        "</ul>"
        "<h2>Circuit traits</h2>"
        + feature_table
        + "<h2>How to use this page before projections arrive</h2>"
        "<ul><li>Use it as a transfer-planning placeholder for the later 2026 calendar.</li><li>Shortlist drivers and constructors that usually suit the circuit profile, then wait for BoxBox projections before making final moves.</li><li>Once the page updates, compare the new picks in Team Compare and the Multi-Week Planner.</li></ul>"
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return slug, page_head(title, desc, canonical, ld) + body + FOOTER


# --------------------------------------------------------------------------- #
# index hub
# --------------------------------------------------------------------------- #
def render_index(entries: list) -> str:
    """entries: list of (slug, race_name, date, round, status)."""
    canonical = f"{SITE}/picks/"
    title = f"F1 Fantasy Picks by Race - {YEAR} Season | BoxBox"
    desc = (f"Free F1 Fantasy picks, tips and predictions for every {YEAR} Grand Prix - "
            f"top drivers, best value picks and constructors for each race.")

    items = []
    for slug, name, date, rn, status in entries:
        tag = ""
        if status == "current":
            tag = '<span class="tag">This week</span>'
        elif status == "future":
            tag = '<span class="tag">Early outlook</span>'
        elif status == "calendar":
            tag = '<span class="tag">Watchlist</span>'
        items.append(
            f'<li><span><a href="/picks/{slug}/">{esc(short_race(name))} {YEAR}</a>{tag}</span>'
            f'<span class="date">{esc(date)}</span></li>'
        )

    ld = ld_block([
        webpage_ld(title, canonical, desc, "CollectionPage"),
        item_list_ld(
            f"F1 Fantasy race picks pages for {YEAR}",
            canonical,
            [(f"{short_race(name)} {YEAR}", f"{SITE}/picks/{slug}/") for slug, name, date, rn, status in entries],
        ),
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "F1 Fantasy Picks", "item": canonical},
            ],
        },
    ])

    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; Picks</p>'
        f"<h1>F1 Fantasy Picks by Race ({YEAR})</h1>"
        f'<p class="lede">Free, data-driven F1 Fantasy picks and tips for every {YEAR} Grand Prix &mdash; '
        f"the model's top drivers, best value (PPM) options and constructors for each race. "
        f"Pick a round below, or jump into the live predictions and tools.</p>"
        '<div class="btnrow"><a class="cta" href="/">Open live predictions &amp; tools &rarr;</a></div>'
        f'<ul class="racelist">{"".join(items)}</ul>'
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


# --------------------------------------------------------------------------- #
# driver + constructor pages
# --------------------------------------------------------------------------- #
def _driver_team_name(driver: dict, constructors_by_id: dict) -> str:
    con = constructors_by_id.get(driver.get("constructor"), {})
    return con.get("name") or str(driver.get("constructor", "")).replace("_", " ").title()


def render_drivers_hub(current: dict) -> str:
    drivers = sorted(current.get("drivers", []), key=lambda d: d.get("expected_points", 0), reverse=True)
    constructors_by_id = {c["constructor_id"]: c for c in current.get("constructors", [])}
    race = current.get("race", "the current race")
    canonical = f"{SITE}/drivers/"
    title = f"F1 Fantasy Driver Predictions {YEAR}: Points, Prices & Value | BoxBox"
    desc = f"Current F1 Fantasy {YEAR} driver projections: expected points, prices, value ratings, predicted qualifying and race finish for every driver."
    rows = []
    for i, d in enumerate(drivers, 1):
        url = f"/drivers/{plain_slug(d.get('name', d.get('driver_id', 'driver')))}/"
        rows.append(
            f'<tr><td class="num">{i}</td><td><a href="{url}">{esc(d.get("name", d.get("driver_id", "")))}</a></td>'
            f'<td>{esc(_driver_team_name(d, constructors_by_id))}</td>'
            f'<td class="num">${d.get("current_price", 0):.1f}M</td>'
            f'<td class="num">{d.get("expected_points", 0):.1f}</td>'
            f'<td class="num">{d.get("value_score", 0):.2f}</td>'
            f'<td class="num">P{d.get("predicted_quali", "-")}&rarr;P{d.get("predicted_finish", "-")}</td></tr>'
        )

    ld = ld_block([
        webpage_ld(title, canonical, desc, "CollectionPage"),
        item_list_ld(
            f"F1 Fantasy driver projections for {YEAR}",
            canonical,
            [(d.get("name", d.get("driver_id", "")), f"{SITE}/drivers/{plain_slug(d.get('name', d.get('driver_id', 'driver')))}/") for d in drivers],
        ),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Drivers", canonical),
        ]),
    ])
    table = (
        '<table><thead><tr><th class="num">#</th><th>Driver</th><th>Team</th>'
        '<th class="num">Price</th><th class="num">Exp. pts</th><th class="num">PPM</th>'
        '<th class="num">Quali&rarr;Race</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>"
    )
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Drivers</p>'
        f"<h1>F1 Fantasy Driver Predictions ({YEAR})</h1>"
        f'<p class="lede">Current driver projections for the <strong>{esc(race)}</strong>: expected points, price, value, predicted qualifying position and predicted race finish for every F1 Fantasy driver.</p>'
        '<p class="meta">These pages update whenever the prediction pipeline is exported.</p>'
        '<div class="btnrow"><a class="cta" href="/#drivers">Open live driver cards &rarr;</a></div>'
        + table
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def render_driver_page(driver: dict, current: dict, rank: int, constructors_by_id: dict) -> str:
    name = driver.get("name", driver.get("driver_id", "Driver"))
    team = _driver_team_name(driver, constructors_by_id)
    race = current.get("race", "the current race")
    short = short_race(race)
    slug = plain_slug(name)
    canonical = f"{SITE}/drivers/{slug}/"
    title = f"{name} F1 Fantasy {YEAR}: Points, Price & Value | BoxBox"
    desc = (
        f"{name} F1 Fantasy {YEAR} projection: {driver.get('expected_points', 0):.1f} expected points "
        f"for the {short}, ${driver.get('current_price', 0):.1f}M price, value rating and confidence range."
    )
    floor = driver.get("mc_total_p5", 0)
    ceiling = driver.get("mc_total_p95", 0)
    value_label = "strong value" if driver.get("value_score", 0) >= 1.0 else "premium upside" if driver.get("current_price", 0) >= 20 else "situational value"
    dnf_pct = driver.get("dnf_probability", 0) * 100
    cta = '<div class="btnrow"><a class="cta" href="/#drivers">See live driver cards &rarr;</a><a class="cta" href="/#optimizer" style="background:#1b212c;">Test in Optimizer &rarr;</a></div>'
    stats = (
        '<table><tbody>'
        f'<tr><th>Current team</th><td>{esc(team)}</td></tr>'
        f'<tr><th>Current price</th><td>${driver.get("current_price", 0):.1f}M</td></tr>'
        f'<tr><th>Expected points</th><td>{driver.get("expected_points", 0):.1f}</td></tr>'
        f'<tr><th>Projected points</th><td>{driver.get("projected_points", 0):.1f}</td></tr>'
        f'<tr><th>Value rating</th><td>{driver.get("value_score", 0):.2f} PPM</td></tr>'
        f'<tr><th>Predicted quali</th><td>P{driver.get("predicted_quali", "-")}</td></tr>'
        f'<tr><th>Predicted finish</th><td>P{driver.get("predicted_finish", "-")}</td></tr>'
        f'<tr><th>90% confidence range</th><td>{floor:.1f} to {ceiling:.1f} pts</td></tr>'
        f'<tr><th>DNF probability</th><td>{dnf_pct:.0f}%</td></tr>'
        f'<tr><th>Expected overtakes</th><td>{driver.get("expected_overtakes", 0):.1f}</td></tr>'
        '</tbody></table>'
    )
    faqs = [
        (f"How many F1 Fantasy points is {name} projected to score?",
         f"{name} is currently projected for {driver.get('expected_points', 0):.1f} expected fantasy points at the {short}. The 90% simulation range is {floor:.1f} to {ceiling:.1f} points."),
        (f"Is {name} good value in F1 Fantasy?",
         f"{name} costs ${driver.get('current_price', 0):.1f}M and has a value rating of {driver.get('value_score', 0):.2f} points per million for this round, so the model currently treats this as {value_label}."),
        (f"What team does {name} drive for?",
         f"{name} is listed with {team} in the current BoxBoxF1Fantasy prediction file."),
    ]
    ld = ld_block([
        {
            **webpage_ld(title, canonical, desc, "ProfilePage"),
            "mainEntity": {
                "@type": "Person",
                "name": name,
                "url": canonical,
                "identifier": driver.get("driver_id", slug),
                "jobTitle": "Formula 1 driver",
                "sport": "Formula 1",
                "affiliation": {"@type": "SportsTeam", "name": team},
                "memberOf": {"@type": "SportsTeam", "name": team},
                "additionalProperty": [
                    {"@type": "PropertyValue", "name": "F1 Fantasy price", "value": f"${driver.get('current_price', 0):.1f}M"},
                    {"@type": "PropertyValue", "name": "Expected F1 Fantasy points", "value": round(float(driver.get("expected_points", 0)), 1)},
                    {"@type": "PropertyValue", "name": "F1 Fantasy points per million", "value": round(float(driver.get("value_score", 0)), 2)},
                    {"@type": "PropertyValue", "name": "Predicted qualifying position", "value": driver.get("predicted_quali", "-")},
                    {"@type": "PropertyValue", "name": "Predicted race finish", "value": driver.get("predicted_finish", "-")},
                ],
            },
        },
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Drivers", f"{SITE}/drivers/"),
            (name, canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ])
    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/drivers/">Drivers</a> &rsaquo; {esc(name)}</p>'
        f"<h1>{esc(name)} F1 Fantasy {YEAR}</h1>"
        f'<p class="lede">{esc(name)} is ranked #{rank} by expected F1 Fantasy points for the <strong>{esc(race)}</strong>, with a current projection of <strong>{driver.get("expected_points", 0):.1f} points</strong>.</p>'
        f'<p class="meta">Price ${driver.get("current_price", 0):.1f}M &middot; {esc(team)} &middot; predicted P{driver.get("predicted_quali", "-")} qualifying to P{driver.get("predicted_finish", "-")} race finish.</p>'
        + cta
        + "<h2>Current projection</h2>"
        + stats
        + "<h2>Fantasy read</h2>"
        + f'<p>For this round, {esc(name)} profiles as <strong>{esc(value_label)}</strong>. The confidence range is wide because race outcomes can swing on reliability, safety cars, weather, strategy and incidents.</p>'
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
        + cta
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def render_constructors_hub(current: dict) -> str:
    constructors = sorted(current.get("constructors", []), key=lambda c: c.get("expected_points", 0), reverse=True)
    race = current.get("race", "the current race")
    canonical = f"{SITE}/constructors/"
    title = f"F1 Fantasy Constructor Predictions {YEAR}: Points, Prices & Value | BoxBox"
    desc = f"Current F1 Fantasy {YEAR} constructor projections: expected points, prices, pit-stop points, value ratings and risk for every constructor."
    rows = []
    for i, c in enumerate(constructors, 1):
        url = f"/constructors/{plain_slug(c.get('name', c.get('constructor_id', 'constructor')))}/"
        rows.append(
            f'<tr><td class="num">{i}</td><td><a href="{url}">{esc(c.get("name", c.get("constructor_id", "")))}</a></td>'
            f'<td class="num">${c.get("current_price", 0):.1f}M</td>'
            f'<td class="num">{c.get("expected_points", 0):.1f}</td>'
            f'<td class="num">{c.get("expected_pit_stop_pts", 0):.1f}</td>'
            f'<td class="num">{c.get("value_score", 0):.2f}</td>'
            f'<td class="num">{esc(c.get("risk", "-"))}</td></tr>'
        )

    ld = ld_block([
        webpage_ld(title, canonical, desc, "CollectionPage"),
        item_list_ld(
            f"F1 Fantasy constructor projections for {YEAR}",
            canonical,
            [(c.get("name", c.get("constructor_id", "")), f"{SITE}/constructors/{plain_slug(c.get('name', c.get('constructor_id', 'constructor')))}/") for c in constructors],
        ),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Constructors", canonical),
        ]),
    ])
    table = (
        '<table><thead><tr><th class="num">#</th><th>Constructor</th><th class="num">Price</th>'
        '<th class="num">Exp. pts</th><th class="num">Pit pts</th><th class="num">PPM</th>'
        '<th class="num">Risk</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>"
    )
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Constructors</p>'
        f"<h1>F1 Fantasy Constructor Predictions ({YEAR})</h1>"
        f'<p class="lede">Current constructor projections for the <strong>{esc(race)}</strong>: expected points, price, pit-stop points, value and risk for every F1 Fantasy constructor.</p>'
        '<p class="meta">Constructors include both drivers scoring, qualifying teamwork bonus, pit-stop points and DNF risk.</p>'
        '<div class="btnrow"><a class="cta" href="/#constructors">Open live constructor cards &rarr;</a></div>'
        + table
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def render_constructor_page(constructor: dict, current: dict, rank: int, drivers_by_id: dict) -> str:
    name = constructor.get("name", constructor.get("constructor_id", "Constructor"))
    full_name = constructor.get("full_name", name)
    race = current.get("race", "the current race")
    short = short_race(race)
    slug = plain_slug(name)
    canonical = f"{SITE}/constructors/{slug}/"
    title = f"{name} F1 Fantasy {YEAR}: Constructor Points, Price & Value | BoxBox"
    desc = (
        f"{name} F1 Fantasy {YEAR} constructor projection: {constructor.get('expected_points', 0):.1f} expected points "
        f"for the {short}, ${constructor.get('current_price', 0):.1f}M price, pit-stop points and value rating."
    )
    driver_names = [
        drivers_by_id.get(constructor.get("driver_1"), {}).get("name", constructor.get("driver_1", "")),
        drivers_by_id.get(constructor.get("driver_2"), {}).get("name", constructor.get("driver_2", "")),
    ]
    driver_line = " and ".join([d for d in driver_names if d])
    floor = constructor.get("mc_total_p5", 0)
    ceiling = constructor.get("mc_total_p95", 0)
    dnf_pct = constructor.get("dnf_probability", 0) * 100
    cta = '<div class="btnrow"><a class="cta" href="/#constructors">See live constructor cards &rarr;</a><a class="cta" href="/#optimizer" style="background:#1b212c;">Test in Optimizer &rarr;</a></div>'
    stats = (
        '<table><tbody>'
        f'<tr><th>Full team name</th><td>{esc(full_name)}</td></tr>'
        f'<tr><th>Listed drivers</th><td>{esc(driver_line)}</td></tr>'
        f'<tr><th>Current price</th><td>${constructor.get("current_price", 0):.1f}M</td></tr>'
        f'<tr><th>Expected points</th><td>{constructor.get("expected_points", 0):.1f}</td></tr>'
        f'<tr><th>Projected points</th><td>{constructor.get("projected_points", 0):.1f}</td></tr>'
        f'<tr><th>Expected pit-stop points</th><td>{constructor.get("expected_pit_stop_pts", 0):.1f}</td></tr>'
        f'<tr><th>Qualifying bonus</th><td>{constructor.get("quali_bonus", 0):.1f}</td></tr>'
        f'<tr><th>Value rating</th><td>{constructor.get("value_score", 0):.2f} PPM</td></tr>'
        f'<tr><th>90% confidence range</th><td>{floor:.1f} to {ceiling:.1f} pts</td></tr>'
        f'<tr><th>DNF probability</th><td>{dnf_pct:.0f}%</td></tr>'
        '</tbody></table>'
    )
    faqs = [
        (f"How many F1 Fantasy points is {name} projected to score?",
         f"{name} is currently projected for {constructor.get('expected_points', 0):.1f} expected fantasy points at the {short}. The 90% simulation range is {floor:.1f} to {ceiling:.1f} points."),
        (f"Is {name} good value in F1 Fantasy?",
         f"{name} costs ${constructor.get('current_price', 0):.1f}M and has a value rating of {constructor.get('value_score', 0):.2f} points per million for this round."),
        (f"Which drivers count toward {name} constructor points?",
         f"The current prediction file lists {driver_line} for {name}. Constructor points include both drivers' qualifying and race scoring, pit-stop points and the qualifying teamwork bonus."),
    ]
    ld = ld_block([
        {
            **webpage_ld(title, canonical, desc, "ProfilePage"),
            "mainEntity": {
                "@type": "SportsTeam",
                "name": name,
                "alternateName": full_name,
                "url": canonical,
                "identifier": constructor.get("constructor_id", slug),
                "sport": "Formula 1",
                "athlete": [
                    {
                        "@type": "Person",
                        "name": d,
                        "url": f"{SITE}/drivers/{plain_slug(d)}/",
                    }
                    for d in driver_names if d
                ],
                "additionalProperty": [
                    {"@type": "PropertyValue", "name": "F1 Fantasy price", "value": f"${constructor.get('current_price', 0):.1f}M"},
                    {"@type": "PropertyValue", "name": "Expected F1 Fantasy points", "value": round(float(constructor.get("expected_points", 0)), 1)},
                    {"@type": "PropertyValue", "name": "F1 Fantasy points per million", "value": round(float(constructor.get("value_score", 0)), 2)},
                    {"@type": "PropertyValue", "name": "Expected pit-stop points", "value": round(float(constructor.get("expected_pit_stop_pts", 0)), 1)},
                    {"@type": "PropertyValue", "name": "Qualifying teamwork bonus", "value": round(float(constructor.get("quali_bonus", 0)), 1)},
                ],
            },
        },
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Constructors", f"{SITE}/constructors/"),
            (name, canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ])
    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/constructors/">Constructors</a> &rsaquo; {esc(name)}</p>'
        f"<h1>{esc(name)} F1 Fantasy Constructor {YEAR}</h1>"
        f'<p class="lede">{esc(name)} is ranked #{rank} by expected constructor points for the <strong>{esc(race)}</strong>, with a current projection of <strong>{constructor.get("expected_points", 0):.1f} points</strong>.</p>'
        f'<p class="meta">Price ${constructor.get("current_price", 0):.1f}M &middot; listed drivers: {esc(driver_line)}.</p>'
        + cta
        + "<h2>Current projection</h2>"
        + stats
        + "<h2>Fantasy read</h2>"
        + f'<p>{esc(name)} combines both listed drivers, pit-stop scoring, qualifying teamwork bonus and DNF exposure. That makes constructor value different from driver value, and often steadier than chasing one extra premium driver.</p>'
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
        + cta
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


# --------------------------------------------------------------------------- #
# accuracy page
# --------------------------------------------------------------------------- #
def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_accuracy_summary(season: dict) -> dict:
    rows = []
    driver_errors = []
    constructor_errors = []
    position_errors = []
    ci_hits = 0
    ci_total = 0
    biggest_misses = []

    for r in season.get("rounds", []):
        if not (r.get("has_predictions") and r.get("has_actual")):
            continue
        rn = r["round"]
        pred = load_json(DATA / f"predictions_round{rn}.json")
        actual = load_json(DATA / f"actual_round{rn}.json")
        if not pred or not actual:
            continue

        pred_drivers = {d["driver_id"]: d for d in pred.get("drivers", [])}
        act_drivers = {d["driver_id"]: d for d in actual.get("drivers", [])}
        round_driver_err = []
        round_pos_err = []
        round_ci_hits = 0
        round_ci_total = 0

        for did, p in pred_drivers.items():
            a = act_drivers.get(did)
            if not a:
                continue
            pred_pts = _pts(p)
            actual_pts = float(a.get("total_points") or 0)
            err = abs(pred_pts - actual_pts)
            round_driver_err.append(err)
            driver_errors.append(err)
            biggest_misses.append({
                "round": rn,
                "race": pred.get("race", r.get("name", "")),
                "name": p.get("name", did),
                "pred": pred_pts,
                "actual": actual_pts,
                "err": err,
            })
            if p.get("predicted_finish") is not None and a.get("race_position") is not None:
                pos_err = abs(float(p["predicted_finish"]) - float(a["race_position"]))
                round_pos_err.append(pos_err)
                position_errors.append(pos_err)
            if p.get("mc_total_p5") is not None and p.get("mc_total_p95") is not None:
                round_ci_total += 1
                ci_total += 1
                if float(p["mc_total_p5"]) <= actual_pts <= float(p["mc_total_p95"]):
                    round_ci_hits += 1
                    ci_hits += 1

        pred_constructors = {c["constructor_id"]: c for c in pred.get("constructors", [])}
        act_constructors = {c["constructor_id"]: c for c in actual.get("constructors", [])}
        round_constructor_err = []
        for cid, p in pred_constructors.items():
            a = act_constructors.get(cid)
            if not a:
                continue
            err = abs(_pts(p) - float(a.get("total_points") or 0))
            round_constructor_err.append(err)
            constructor_errors.append(err)

        rows.append({
            "round": rn,
            "race": pred.get("race", r.get("name", "")),
            "driver_mae": _mean(round_driver_err),
            "constructor_mae": _mean(round_constructor_err),
            "position_mae": _mean(round_pos_err),
            "ci_coverage": (round_ci_hits / round_ci_total * 100) if round_ci_total else 0,
            "driver_count": len(round_driver_err),
            "constructor_count": len(round_constructor_err),
        })

    biggest_misses.sort(key=lambda x: x["err"], reverse=True)
    return {
        "rounds": rows,
        "driver_mae": _mean(driver_errors),
        "constructor_mae": _mean(constructor_errors),
        "position_mae": _mean(position_errors),
        "ci_coverage": (ci_hits / ci_total * 100) if ci_total else 0,
        "ci_hits": ci_hits,
        "ci_total": ci_total,
        "driver_count": len(driver_errors),
        "constructor_count": len(constructor_errors),
        "biggest_misses": biggest_misses[:8],
    }


def render_accuracy_page(summary: dict) -> str:
    canonical = f"{SITE}/accuracy/"
    completed = len(summary["rounds"])
    title = f"F1 Fantasy Prediction Accuracy {YEAR}: BoxBox Track Record"
    desc = (
        f"BoxBoxF1Fantasy prediction accuracy for completed {YEAR} rounds: driver points MAE, "
        "constructor points MAE, race-position error and 90% confidence interval coverage."
    )

    round_rows = "".join(
        f'<tr><td>R{r["round"]}</td><td>{esc(short_race(r["race"]))}</td>'
        f'<td class="num">{r["driver_mae"]:.1f}</td>'
        f'<td class="num">{r["constructor_mae"]:.1f}</td>'
        f'<td class="num">{r["position_mae"]:.1f}</td>'
        f'<td class="num">{r["ci_coverage"]:.0f}%</td></tr>'
        for r in summary["rounds"]
    )
    miss_rows = "".join(
        f'<tr><td>R{m["round"]}</td><td>{esc(m["name"])}</td>'
        f'<td class="num">{m["pred"]:.1f}</td><td class="num">{m["actual"]:.0f}</td>'
        f'<td class="num">{m["err"]:.1f}</td></tr>'
        for m in summary["biggest_misses"]
    )
    faqs = [
        ("How accurate are BoxBoxF1Fantasy predictions?",
         f"Across the completed rounds currently published here, driver fantasy-point MAE is {summary['driver_mae']:.1f} points and race-position MAE is {summary['position_mae']:.1f} positions. This page updates when completed-round actuals are exported."),
        ("What does MAE mean?",
         "MAE means mean absolute error: the average size of the miss, ignoring whether the prediction was too high or too low. Lower is better."),
        ("Why publish the misses?",
         "Publishing misses keeps the model honest. F1 Fantasy is noisy, and weather, DNFs, safety cars, penalties and strategy can all create large errors."),
    ]
    ld = ld_block([
        webpage_ld(title, canonical, desc, "WebPage"),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Accuracy", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": f"BoxBoxF1Fantasy {YEAR} prediction accuracy",
            "description": desc,
            "url": canonical,
            "creator": publisher_ld(),
            "measurementTechnique": "Mean absolute error and confidence interval coverage computed from published prediction and actual-results JSON files.",
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ])
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Accuracy</p>'
        f"<h1>F1 Fantasy Prediction Accuracy ({YEAR})</h1>"
        f'<p class="lede">A public track record for BoxBoxF1Fantasy predictions across completed {YEAR} rounds. This page shows the misses as well as the hits.</p>'
        '<p class="meta">Computed from the same prediction and actual-results JSON files used by the live Accuracy tab.</p>'
        '<div class="btnrow"><a class="cta" href="/#accuracy">Open interactive Accuracy tab &rarr;</a></div>'
        '<div class="callout">'
        f'<strong>{completed} completed rounds analyzed.</strong> Driver points MAE: <strong>{summary["driver_mae"]:.1f}</strong> &middot; '
        f'Constructor points MAE: <strong>{summary["constructor_mae"]:.1f}</strong> &middot; '
        f'Race-position MAE: <strong>{summary["position_mae"]:.1f}</strong> &middot; '
        f'90% CI coverage: <strong>{summary["ci_coverage"]:.0f}%</strong> ({summary["ci_hits"]}/{summary["ci_total"]}).'
        '</div>'
        '<h2>Round-by-round accuracy</h2>'
        '<table><thead><tr><th>Round</th><th>Race</th><th class="num">Driver pts MAE</th><th class="num">Constructor pts MAE</th><th class="num">Finish pos MAE</th><th class="num">90% CI</th></tr></thead><tbody>'
        + round_rows + "</tbody></table>"
        '<h2>Biggest driver-point misses</h2>'
        '<p>These are useful because they show where the model was most wrong, usually because of DNFs, penalties, strategy swings, weather or surprise race pace.</p>'
        '<table><thead><tr><th>Round</th><th>Driver</th><th class="num">Pred.</th><th class="num">Actual</th><th class="num">Abs. miss</th></tr></thead><tbody>'
        + miss_rows + "</tbody></table>"
        '<h2>How to read this</h2>'
        '<p>Fantasy-point accuracy is harder than finishing-position accuracy because fantasy scoring also includes qualifying, overtakes, positions gained, fastest lap, Driver of the Day, sprint scoring, constructors, pit stops and DNF penalties. Confidence interval coverage shows whether the uncertainty bands are calibrated, not whether every single pick was close.</p>'
        "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def render_changelog_page(changelog: dict) -> str:
    """Crawlable public release notes for transparency, freshness and AI discovery."""
    canonical = f"{SITE}/changelog/"
    entries = sorted(changelog.get("entries", []), key=lambda e: e.get("date", ""), reverse=True)
    title = f"BoxBoxF1Fantasy Changelog {YEAR}: Prediction & Tool Updates"
    desc = "Public BoxBoxF1Fantasy changelog: model updates, scoring fixes, feature releases and data-quality notes for the F1 Fantasy prediction site."

    latest = entries[0]["date"] if entries else datetime.now(timezone.utc).date().isoformat()
    entry_cards = []
    item_list = []
    for i, entry in enumerate(entries[:30], 1):
        date = clean_legacy_text(entry.get("date", ""))
        entry_title = clean_legacy_text(entry.get("title", "Site update"))
        tags = [
            f'<span class="tag">{esc(clean_legacy_text(t))}</span>'
            for t in entry.get("tags", [])
        ]
        body_parts = []
        for part in entry.get("body", []):
            cleaned = clean_legacy_text(part)
            stripped = cleaned.lstrip().lower()
            is_block = stripped.startswith(("<p", "<ul", "<ol", "<h", "<blockquote", "<table", "<div"))
            body_parts.append(cleaned if is_block else f"<p>{cleaned}</p>")
        body = "".join(body_parts)
        anchor = plain_slug(f"{date} {entry_title}") or f"update-{i}"
        entry_cards.append(
            f'<article id="{anchor}" class="update-card">'
            f'<p class="meta">{esc(date)}</p>'
            f'<h2>{esc(entry_title)}</h2>'
            f'<p>{" ".join(tags)}</p>'
            f'<div>{body}</div>'
            "</article>"
        )
        item_list.append((entry_title, f"{canonical}#{anchor}"))

    faqs = [
        ("Why publish a changelog?",
         "The changelog keeps a public record of meaningful model, scoring, data and tool changes so users can understand why projections or accuracy numbers moved."),
        ("Does the changelog reveal the full prediction method?",
         "No. It explains user-visible changes and validation outcomes in plain English without publishing private implementation details or every model parameter."),
        ("How often is BoxBoxF1Fantasy updated?",
         "The prediction pipeline updates through race weekends as data arrives, and the changelog is updated when a notable feature, fix or model change ships."),
    ]
    ld = ld_block([
        webpage_ld(title, canonical, desc, "CollectionPage"),
        item_list_ld(f"BoxBoxF1Fantasy {YEAR} changelog entries", canonical, item_list[:20]),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Changelog", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ])
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Changelog</p>'
        f"<h1>BoxBoxF1Fantasy Changelog ({YEAR})</h1>"
        '<p class="lede">A public record of meaningful prediction, scoring, data and tool changes. It is written for players: transparent enough to explain what changed, without giving away private model details.</p>'
        f'<p class="meta">Latest update: {esc(latest)} &middot; Showing {len(entries[:30])} recent entries.</p>'
        '<div class="btnrow"><a class="cta" href="/#changelog">Open interactive Changelog tab &rarr;</a></div>'
        + "".join(entry_cards)
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def render_videos_page(videos_data: dict) -> str:
    """Crawlable YouTube index for recent F1 Fantasy videos."""
    canonical = f"{SITE}/videos/"
    videos = sorted(videos_data.get("videos", []), key=lambda v: v.get("published", ""), reverse=True)
    title = f"F1 Fantasy Videos {YEAR}: Drafts, Tips & Strategy | BoxBox"
    desc = "Latest BoxBoxF1Fantasy videos: F1 Fantasy team drafts, race-week tips, deadline streams, strategy notes and top picks."
    channel_url = videos_data.get("channel_url") or "https://www.youtube.com/@BoxBoxF1Fantasy"

    video_cards = []
    video_ld = []
    item_list = []
    for i, video in enumerate(videos[:12], 1):
        vid = clean_legacy_text(video.get("id", ""))
        video_title = clean_legacy_text(video.get("title", "F1 Fantasy video"))
        published = clean_legacy_text(video.get("published", ""))
        url = video.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else channel_url)
        thumb = video.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "")
        embed = f"https://www.youtube.com/embed/{vid}" if vid else url
        anchor = plain_slug(f"{published} {video_title}") or f"video-{i}"
        thumb_html = (
            f'<a href="{esc(url)}" rel="noopener" target="_blank">'
            f'<img src="{esc(thumb)}" alt="{esc(video_title)} thumbnail" loading="lazy"></a>'
            if thumb else ""
        )
        video_cards.append(
            f'<article id="{anchor}" class="video-card">'
            f"{thumb_html}"
            f'<div><p class="meta">{esc(published)}</p>'
            f'<h2><a href="{esc(url)}" rel="noopener" target="_blank">{esc(video_title)}</a></h2>'
            '<p>Watch on YouTube for the latest F1 Fantasy draft thinking, race-week picks and deadline strategy.</p>'
            "</div></article>"
        )
        item_list.append((video_title, f"{canonical}#{anchor}"))
        video_ld.append({
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": video_title,
            "description": f"BoxBoxF1Fantasy video about F1 Fantasy {YEAR} strategy, team drafts, race-week tips and picks.",
            "thumbnailUrl": [thumb] if thumb else [],
            "uploadDate": published,
            "contentUrl": url,
            "embedUrl": embed,
            "publisher": publisher_ld(),
        })

    faqs = [
        ("What are the BoxBoxF1Fantasy videos about?",
         "The videos cover F1 Fantasy race-week drafts, team selection, top picks, budget strategy, deadline streams and how to use the site's data."),
        ("Are the videos separate from the predictions on the site?",
         "They use the same public projections and race-week context, but the videos add human explanation, draft examples and strategy discussion."),
        ("Where is the YouTube channel?",
         f"The channel is at {channel_url}. The crawlable videos page links to the latest videos and the live Videos tab on the site."),
    ]
    ld = ld_block([
        webpage_ld(title, canonical, desc, "CollectionPage"),
        item_list_ld(f"BoxBoxF1Fantasy {YEAR} videos", canonical, item_list),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Videos", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ] + video_ld)
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Videos</p>'
        f"<h1>F1 Fantasy Videos ({YEAR})</h1>"
        '<p class="lede">Latest BoxBoxF1Fantasy videos for race-week drafts, data-backed picks, deadline strategy and F1 Fantasy decision-making.</p>'
        f'<p class="meta">Channel: <a href="{esc(channel_url)}" rel="noopener" target="_blank">{esc(channel_url)}</a></p>'
        '<div class="btnrow"><a class="cta" href="/#videos">Open interactive Videos tab &rarr;</a></div>'
        + ("".join(video_cards) if video_cards else '<p class="no-data">No videos available yet.</p>')
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def _article_summary(article: dict) -> str:
    raw = re.sub(r"<[^>]+>", " ", clean_legacy_text(article.get("content_html", "")))
    raw = re.sub(r"\s+", " ", html.unescape(raw)).strip()
    return raw[:220].rsplit(" ", 1)[0] + "..." if len(raw) > 220 else raw


def render_article_page(article: dict) -> str:
    """Crawlable long-form article page from web/public/data/articles.json."""
    slug = plain_slug(article.get("slug") or article.get("title") or "article")
    canonical = f"{SITE}/articles/{slug}/"
    article_title = clean_legacy_text(article.get("title", "F1 Fantasy Article"))
    published = clean_legacy_text(article.get("date", ""))
    tags = [clean_legacy_text(t) for t in article.get("tags", []) if t]
    desc = _article_summary(article) or f"BoxBoxF1Fantasy article: {article_title}."
    title = f"{article_title} | BoxBoxF1Fantasy"
    content = clean_legacy_text(article.get("content_html", ""))
    tag_html = " ".join(f'<span class="tag">{esc(t)}</span>' for t in tags)

    ld = ld_block([
        webpage_ld(title, canonical, desc, "Article") | {
            "headline": article_title,
            "datePublished": published,
            "dateModified": published,
            "author": publisher_ld(),
            "about": ["F1 Fantasy", "Fantasy sports strategy", "Formula 1"] + tags[:5],
        },
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Articles", f"{SITE}/articles/"),
            (article_title, canonical),
        ]),
    ])
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/articles/">Articles</a> &rsaquo; Article</p>'
        f"<h1>{esc(article_title)}</h1>"
        f'<p class="meta">{esc(published)}{(" &middot; " + tag_html) if tag_html else ""}</p>'
        '<div class="article-body">'
        + content
        + "</div>"
        '<div class="btnrow"><a class="cta" href="/#articles">Open interactive Articles tab &rarr;</a></div>'
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


def render_articles_hub(articles_data: dict) -> str:
    """Crawlable article index for race previews/recaps and fantasy analysis."""
    canonical = f"{SITE}/articles/"
    articles = sorted(articles_data.get("articles", []), key=lambda a: a.get("date", ""), reverse=True)
    title = f"F1 Fantasy Articles {YEAR}: Race Recaps, Previews & Strategy | BoxBox"
    desc = "BoxBoxF1Fantasy articles: race weekend previews, recaps, fantasy takeaways, strategy notes and data-backed F1 Fantasy analysis."

    cards = []
    item_list = []
    for article in articles:
        slug = plain_slug(article.get("slug") or article.get("title") or "article")
        article_title = clean_legacy_text(article.get("title", "F1 Fantasy Article"))
        published = clean_legacy_text(article.get("date", ""))
        summary = _article_summary(article)
        tags = " ".join(f'<span class="tag">{esc(clean_legacy_text(t))}</span>' for t in article.get("tags", [])[:4])
        url = f"{SITE}/articles/{slug}/"
        cards.append(
            '<article class="article-card">'
            f'<p class="meta">{esc(published)}{(" &middot; " + tags) if tags else ""}</p>'
            f'<h2><a href="/articles/{slug}/">{esc(article_title)}</a></h2>'
            f'<p>{esc(summary)}</p>'
            f'<p><a href="/articles/{slug}/">Read article &rarr;</a></p>'
            "</article>"
        )
        item_list.append((article_title, url))

    faqs = [
        ("What articles are published here?",
         "The articles are race previews, recaps and F1 Fantasy strategy notes that explain the data, model context and fantasy takeaways in a more human format."),
        ("Are articles different from race-pick pages?",
         "Yes. Race-pick pages are concise current-round pick summaries. Articles are longer-form analysis, previews and recaps."),
        ("Do articles update the prediction model?",
         "No. Articles explain observations and strategy; the prediction pipeline and exported JSON remain the source of truth for current projections."),
    ]
    ld = ld_block([
        webpage_ld(title, canonical, desc, "CollectionPage"),
        item_list_ld(f"BoxBoxF1Fantasy {YEAR} articles", canonical, item_list),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Articles", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ])
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Articles</p>'
        f"<h1>F1 Fantasy Articles ({YEAR})</h1>"
        '<p class="lede">Race previews, recaps, fantasy takeaways and strategy notes from BoxBoxF1Fantasy.</p>'
        '<div class="btnrow"><a class="cta" href="/#articles">Open interactive Articles tab &rarr;</a></div>'
        + ("".join(cards) if cards else '<p class="no-data">No articles available yet.</p>')
        + "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


PUBLIC_DATASETS = [
    {
        "file": "ai-summary.json",
        "name": "AI answer summary",
        "desc": "Compact current-round answer pack for AI agents: top drivers, constructors, value picks, captain pick, confidence ranges, downside notes and a sample legal lineup.",
    },
    {
        "file": "predictions.json",
        "name": "Current F1 Fantasy predictions",
        "desc": "Current-round driver and constructor projections, expected points, confidence ranges, prices, value scores and prediction metadata.",
        "schema": "predictions.schema.json",
    },
    {
        "file": "predictions.schema.json",
        "name": "Prediction JSON schema",
        "desc": "JSON Schema describing predictions.json for agents, developers and data consumers.",
        "encoding": "application/schema+json",
    },
    {
        "file": "season_summary.json",
        "name": "Season summary",
        "desc": "Race calendar, completed-round flags, current prices and season-level driver/constructor context used by the site.",
    },
    {
        "file": "driver_history.json",
        "name": "Driver and constructor history",
        "desc": "Historical fantasy scores and price movement used by season views, form tables and value context.",
    },
    {
        "file": "track_data.json",
        "name": "Track data",
        "desc": "Circuit metadata and track-classification features for current and future race-week context.",
    },
    {
        "file": "weather.json",
        "name": "Weather forecast",
        "desc": "Race-week weather forecast metadata used by the weather widget and weather-aware prediction notes.",
    },
    {
        "file": "horizon_projections.json",
        "name": "Future-round horizon projections",
        "desc": "Forward-looking projections used by the multi-week transfer planner when planning beyond the current race.",
    },
    {
        "file": "changelog.json",
        "name": "Changelog",
        "desc": "Machine-readable release notes for notable model, scoring, data and tool changes.",
    },
    {
        "file": "articles.json",
        "name": "Articles",
        "desc": "Machine-readable source for crawlable race previews, recaps and F1 Fantasy strategy articles.",
    },
    {
        "file": "youtube_videos.json",
        "name": "YouTube videos",
        "desc": "Latest BoxBoxF1Fantasy YouTube videos with title, publish date, thumbnail and URL.",
    },
]


def compact_projection(item: dict, rank: int, kind: str) -> dict:
    """Small projection shape for answer engines that do not need raw model data."""
    out = {
        "rank": rank,
        "kind": kind,
        "id": item.get("driver_id") or item.get("constructor_id"),
        "name": item.get("name") or item.get("full_name") or item.get("driver_id") or item.get("constructor_id"),
        "expected_points": round(float(item.get("expected_points") or 0), 1),
        "projected_points": round(float(item.get("projected_points") or item.get("expected_points") or 0), 1),
        "current_price_m": round(float(item.get("current_price") or 0), 1),
        "value_score": round(float(item.get("value_score") or 0), 2),
        "risk": item.get("risk"),
        "confidence_interval_90": {
            "low": round(float(item.get("mc_total_p5") or 0), 1),
            "high": round(float(item.get("mc_total_p95") or 0), 1),
        },
        "url": f"{SITE}/{'drivers' if kind == 'driver' else 'constructors'}/{plain_slug(item.get('name') or item.get('full_name') or item.get('driver_id') or item.get('constructor_id'))}/",
    }
    if kind == "driver":
        out.update({
            "constructor": item.get("constructor"),
            "predicted_quali": item.get("predicted_quali"),
            "predicted_finish": item.get("predicted_finish"),
            "dnf_probability": round(float(item.get("dnf_probability") or 0), 3),
            "points_per_million": round(float(item.get("points_per_million") or 0), 2),
        })
    else:
        out.update({
            "driver_1": item.get("driver_1"),
            "driver_2": item.get("driver_2"),
            "expected_pit_stop_points": round(float(item.get("expected_pit_stop_pts") or 0), 1),
            "dnf_probability": round(float(item.get("dnf_probability") or 0), 3),
        })
    return out


def write_ai_summary(current: dict, season: dict) -> None:
    """Write a compact current-round answer pack for AI agents and answer engines."""
    drivers = sorted(current.get("drivers", []), key=lambda d: d.get("expected_points", 0), reverse=True)
    constructors = sorted(current.get("constructors", []), key=lambda c: c.get("expected_points", 0), reverse=True)
    value_drivers = sorted(
        drivers,
        key=lambda d: (d.get("points_per_million") or d.get("value_score") or 0, d.get("expected_points") or 0),
        reverse=True,
    )
    value_constructors = sorted(
        constructors,
        key=lambda c: (c.get("value_score") or 0, c.get("expected_points") or 0),
        reverse=True,
    )
    lineup = suggested_lineup(current)
    current_round = current.get("round")
    race_page = f"{SITE}/picks/{slugify(current.get('race', 'current-race'))}/" if current.get("race") else f"{SITE}/picks/"
    round_info = next((r for r in season.get("rounds", []) if r.get("round") == current_round), {})

    summary = {
        "schema_version": "1.0",
        "site": "BoxBoxF1Fantasy",
        "site_url": f"{SITE}/",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_predictions_generated_at": current.get("generated_at") or current.get("exported_at"),
        "season": current.get("season", YEAR),
        "round": current_round,
        "race": current.get("race"),
        "race_date": current.get("date") or round_info.get("date"),
        "circuit": current.get("circuit") or round_info.get("circuit"),
        "is_sprint_weekend": bool(current.get("is_sprint_weekend") or current.get("is_sprint")),
        "canonical_pages": {
            "home": f"{SITE}/",
            "race_picks": race_page,
            "drivers": f"{SITE}/drivers/",
            "constructors": f"{SITE}/constructors/",
            "tools": f"{SITE}/tools/",
            "data": f"{SITE}/data/",
            "full_predictions_json": f"{SITE}/data/predictions.json",
        },
        "plain_english_summary": (
            f"For the {current.get('race', 'current race')}, BoxBoxF1Fantasy currently ranks "
            f"{drivers[0].get('name', 'the top driver') if drivers else 'the top driver'} as the top projected driver "
            f"and {constructors[0].get('name', 'the top constructor') if constructors else 'the top constructor'} as the top projected constructor. "
            "Use this compact file for quick answers; use predictions.json for the full projection dataset."
        ),
        "recommended_boost_driver": compact_projection(drivers[0], 1, "driver") if drivers else None,
        "top_drivers": [compact_projection(d, i, "driver") for i, d in enumerate(drivers[:8], 1)],
        "top_constructors": [compact_projection(c, i, "constructor") for i, c in enumerate(constructors[:6], 1)],
        "value_drivers": [compact_projection(d, i, "driver") for i, d in enumerate(value_drivers[:6], 1)],
        "value_constructors": [compact_projection(c, i, "constructor") for i, c in enumerate(value_constructors[:4], 1)],
        "sample_lineup_100m": None,
        "agent_guidance": [
            "Use expected_points for current-round ranking.",
            "Use confidence_interval_90.low as a conservative downside estimate.",
            "Use value_score or points_per_million when the user asks for budget/value picks.",
            "The sample lineup is a public crawlable snapshot; the live optimizer supports locks, exclusions, chips and custom budgets.",
            "Predictions are model-based and informational, not guaranteed.",
        ],
        "disclaimer": "Independent fan-built site. Not affiliated with Formula 1, the FIA, F1 Fantasy, any F1 team, or any driver.",
    }
    if lineup:
        summary["sample_lineup_100m"] = {
            "budget_m": round(float(lineup["budget"]), 1),
            "cost_m": round(float(lineup["cost"]), 1),
            "bank_m": round(float(lineup["bank"]), 1),
            "expected_points_with_2x": round(float(lineup["points"]), 1),
            "unboosted_expected_points": round(float(lineup["unboosted_points"]), 1),
            "captain_2x": compact_projection(lineup["captain"], 1, "driver"),
            "drivers": [compact_projection(d, i, "driver") for i, d in enumerate(lineup["drivers"], 1)],
            "constructors": [compact_projection(c, i, "constructor") for i, c in enumerate(lineup["constructors"], 1)],
        }

    (DATA / "ai-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_data_page(current: dict, season: dict) -> str:
    """Crawlable index for public JSON endpoints used by AI agents and power users."""
    canonical = f"{SITE}/data/"
    race = current.get("race", "current race")
    round_no = current.get("round", "")
    title = f"BoxBoxF1Fantasy Public Data: JSON Endpoints for F1 Fantasy {YEAR}"
    desc = "Public BoxBoxF1Fantasy JSON data index for agents and developers: AI answer summary, predictions, season summary, driver history, track data, weather, articles, videos and changelog."

    rows = []
    dataset_ld = []
    for item in PUBLIC_DATASETS:
        path = DATA / item["file"]
        exists = path.exists()
        updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat() if exists else ""
        size = path.stat().st_size if exists else 0
        url = f"{SITE}/data/{item['file']}"
        encoding = item.get("encoding", "application/json")
        schema_file = item.get("schema")
        schema_link = f' <span class="meta">schema: <a href="/data/{esc(schema_file)}">{esc(schema_file)}</a></span>' if schema_file else ""
        rows.append(
            f'<tr><td><a href="/data/{esc(item["file"])}">{esc(item["file"])}</a></td>'
            f'<td>{esc(item["name"])}</td>'
            f'<td>{esc(item["desc"])}{schema_link}</td>'
            f'<td class="num">{esc(updated)}</td>'
            f'<td class="num">{size:,}</td></tr>'
        )
        dataset_ld.append({
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": item["name"],
            "description": item["desc"],
            "url": url,
            "creator": publisher_ld(),
            "encodingFormat": encoding,
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": encoding,
                "contentUrl": url,
            },
            "dateModified": updated or datetime.now(timezone.utc).date().isoformat(),
            "isAccessibleForFree": True,
            "termsOfUse": f"{SITE}/privacy/",
        })

    faqs = [
        ("Can agents use these JSON files?",
         "Yes. These are public static JSON files used by the website itself. They can be fetched directly for current projections, season context, articles, videos and other public site data."),
        ("Are these predictions guaranteed?",
         "No. The data contains model-based projections and public site metadata. F1 Fantasy outcomes depend on weather, reliability, strategy, penalties and race incidents."),
        ("Which endpoint should an AI assistant read first?",
         "Start with predictions.json for the current round and season_summary.json for calendar and price context. Use llms.txt or llms-full.txt for a plain-English site map."),
    ]
    ld = ld_block([
        webpage_ld(title, canonical, desc, "DataCatalog"),
        breadcrumb_ld([
            ("Home", f"{SITE}/"),
            ("Public Data", canonical),
        ]),
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"BoxBoxF1Fantasy public JSON endpoints {YEAR}",
            "url": canonical,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": item["name"],
                    "url": f"{SITE}/data/{item['file']}",
                }
                for i, item in enumerate(PUBLIC_DATASETS, 1)
            ],
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        },
    ] + dataset_ld)
    body = (
        '<p class="crumbs"><a href="/">Home</a> &rsaquo; Public Data</p>'
        f"<h1>BoxBoxF1Fantasy Public Data ({YEAR})</h1>"
        '<p class="lede">A crawlable index of public JSON files for agents, answer engines and power users who want to understand the data behind the site.</p>'
        f'<p class="meta">Current round: R{esc(round_no)} &middot; {esc(race)}</p>'
        '<div class="callout">For quick AI answers, start with <a href="/data/ai-summary.json">ai-summary.json</a>. For natural-language navigation, use <a href="/llms.txt">llms.txt</a> or the fuller <a href="/llms-full.txt">llms-full.txt</a>. For machine-readable endpoint discovery, use <a href="/openapi.json">openapi.json</a>. For full live projections, use <a href="/data/predictions.json">predictions.json</a> and its <a href="/data/predictions.schema.json">JSON schema</a>.</div>'
        '<table><thead><tr><th>File</th><th>Dataset</th><th>Description</th><th class="num">Updated</th><th class="num">Bytes</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        "<h2>FAQ</h2>"
        + _faq_html(faqs)
    )
    return page_head(title, desc, canonical, ld) + body + FOOTER


# --------------------------------------------------------------------------- #
# sitemap
# --------------------------------------------------------------------------- #
AI_CRAWLER_USER_AGENTS = [
    # OpenAI: search visibility, user-requested fetches, model training, and ad landing-page validation.
    "OAI-SearchBot",
    "ChatGPT-User",
    "GPTBot",
    "OAI-AdsBot",
    # Anthropic: Claude search, user-requested fetches, and model training.
    "Claude-SearchBot",
    "Claude-User",
    "ClaudeBot",
    # Perplexity: search visibility and user-requested fetches.
    "PerplexityBot",
    "Perplexity-User",
    # Google generative-AI product controls; normal Google Search remains covered by User-agent: *.
    "Google-Extended",
]


def predictions_json_schema() -> dict:
    """JSON Schema for the public current-round predictions endpoint."""
    number = {"type": "number"}
    nullable_number = {"type": ["number", "null"]}
    integer = {"type": "integer"}
    string = {"type": "string"}
    risk = {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]}
    percentile_fields = {
        "mc_total_mean": number,
        "mc_total_std": number,
        "mc_total_p5": number,
        "mc_total_p25": number,
        "mc_total_p75": number,
        "mc_total_p95": number,
    }
    driver_schema = {
        "type": "object",
        "additionalProperties": True,
        "required": [
            "driver_id", "name", "constructor", "predicted_quali", "predicted_finish",
            "expected_points", "projected_points", "current_price", "value_score",
        ],
        "properties": {
            "driver_id": string,
            "name": string,
            "constructor": string,
            "number": integer,
            "predicted_quali": integer,
            "predicted_finish": integer,
            "projected_points": number,
            "expected_points": number,
            "expected_points_quali": number,
            "expected_points_race": number,
            "confidence": number,
            "risk": risk,
            "risk_rating": number,
            "dnf_probability": nullable_number,
            "expected_overtakes": number,
            "expected_positions_gained_lost": number,
            "fastest_lap_probability": nullable_number,
            "dotd_probability": nullable_number,
            "points_per_million": number,
            "value_score": number,
            "current_price": number,
            "raw_scores": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"quali": number, "race": number},
            },
            "mc_upside": number,
            "mc_dnf_rate": number,
            "mc_overtakes_mean": number,
            "mc_quali_pts_mean": number,
            "mc_race_pts_mean": number,
            **percentile_fields,
        },
    }
    constructor_schema = {
        "type": "object",
        "additionalProperties": True,
        "required": [
            "constructor_id", "name", "driver_1", "driver_2",
            "expected_points", "projected_points", "current_price", "value_score",
        ],
        "properties": {
            "constructor_id": string,
            "name": string,
            "full_name": string,
            "driver_1": string,
            "driver_2": string,
            "projected_points": number,
            "expected_points": number,
            "expected_points_quali": number,
            "expected_points_race": number,
            "expected_pit_stop_pts": number,
            "expected_dnf_impact": number,
            "dnf_probability": nullable_number,
            "quali_bonus": number,
            "risk": risk,
            "risk_rating": number,
            "value_score": number,
            "current_price": number,
            "mc_pit_stop_pts": number,
            "mc_dnf_prob": number,
            **percentile_fields,
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SITE}/data/predictions.schema.json",
        "title": "BoxBoxF1Fantasy current predictions",
        "description": "Current-round F1 Fantasy driver and constructor projections, prices, confidence ranges, risk metrics and prediction metadata.",
        "type": "object",
        "additionalProperties": True,
        "required": ["season", "round", "race", "drivers", "constructors"],
        "properties": {
            "season": integer,
            "round": integer,
            "race": string,
            "circuit": string,
            "date": string,
            "phase": string,
            "generated_at": string,
            "exported_at": string,
            "is_sprint_weekend": {"type": "boolean"},
            "score_unit": {
                "type": ["object", "number", "null"],
                "additionalProperties": True,
                "properties": {
                    "quali_gap_median": number,
                    "race_gap_median": number,
                },
            },
            "calibration": {"type": "object", "additionalProperties": True},
            "weather_adjustments": {"type": "object", "additionalProperties": True},
            "drivers": {
                "type": "array",
                "description": "Driver projections sorted for the current race context.",
                "items": driver_schema,
            },
            "constructors": {
                "type": "array",
                "description": "Constructor projections sorted for the current race context.",
                "items": constructor_schema,
            },
        },
    }


def write_prediction_schema() -> None:
    (DATA / "predictions.schema.json").write_text(
        json.dumps(predictions_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_sitemap(rel_paths: list[str]) -> None:
    """rel_paths: relative URLs like '', 'picks/', 'picks/monaco-gp-2026/', 'guides/'."""
    lastmod = datetime.now(timezone.utc).date().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in rel_paths:
        u = f"{SITE}/{p}"
        pr = "1.0" if p == "" else "0.8"
        lines.append(
            f"  <url><loc>{u}</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>{pr}</priority></url>"
        )
    lines.append("</urlset>\n")
    (WEB / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")


def write_robots() -> None:
    """Keep crawler hints explicit whenever SEO pages are regenerated."""
    ai_groups = "\n".join(
        f"User-agent: {agent}\nAllow: /\n"
        for agent in AI_CRAWLER_USER_AGENTS
    )
    body = f"""# BoxBoxF1Fantasy intentionally allows search, answer-engine, and AI-agent crawlers.
# Discovery files: /sitemap.xml, /llms.txt, /llms-full.txt, /search-index.json, /openapi.json

User-agent: *
Allow: /
Allow: /picks/
Allow: /drivers/
Allow: /constructors/
Allow: /accuracy/
Allow: /changelog/
Allow: /videos/
Allow: /articles/
Allow: /guides/
Allow: /tools/
Allow: /about/
Allow: /privacy/
Allow: /data/
Allow: /feed.xml
Allow: /feed.json
Allow: /site.webmanifest
Allow: /search-index.json
Allow: /openapi.json
Allow: /.well-known/
Allow: /.well-known/openapi.json
Allow: /.well-known/llms.txt
Allow: /.well-known/ai-plugin.json
Allow: /data/ai-summary.json
Allow: /data/predictions.json
Allow: /data/predictions.schema.json
Allow: /data/season_summary.json
Allow: /llms.txt
Allow: /llms-full.txt
Allow: /humans.txt
Allow: /.well-known/security.txt
Allow: /{INDEXNOW_KEY}.txt

# Explicit AI/search crawler groups. Kept separate so crawler-specific robots
# matching still receives a complete allow rule.
{ai_groups}
Sitemap: {SITE}/sitemap.xml
"""
    (WEB / "robots.txt").write_text(body, encoding="utf-8")


def write_openapi() -> None:
    """Machine-readable contract for public static data endpoints."""
    paths = {}
    for item in PUBLIC_DATASETS:
        encoding = item.get("encoding", "application/json")
        response_schema = predictions_json_schema() if item["file"] == "predictions.json" else {
            "type": "object",
            "additionalProperties": True,
        }
        paths[f"/data/{item['file']}"] = {
            "get": {
                "tags": ["Public data"],
                "summary": item["name"],
                "description": item["desc"],
                "operationId": "get_" + re.sub(r"[^a-zA-Z0-9_]", "_", item["file"].replace(".json", "")),
                "responses": {
                    "200": {
                        "description": f"{item['name']} as JSON.",
                        "content": {
                            encoding: {
                                "schema": response_schema
                            }
                        },
                    }
                },
            }
        }

    paths.update({
        "/search-index.json": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Machine-readable site index",
                "description": "Compact JSON index of crawlable BoxBoxF1Fantasy pages with titles, descriptions, canonicals, page types and headings.",
                "operationId": "get_search_index",
                "responses": {
                    "200": {
                        "description": "JSON page index.",
                        "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
                    }
                },
            }
        },
        "/data/": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Public data index",
                "description": "Crawlable HTML index of public BoxBoxF1Fantasy JSON endpoints and dataset metadata.",
                "operationId": "get_public_data_index",
                "responses": {
                    "200": {
                        "description": "HTML public data index.",
                        "content": {"text/html": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        "/llms.txt": {
            "get": {
                "tags": ["Discovery"],
                "summary": "LLM site guide",
                "description": "Plain-text summary of the most important BoxBoxF1Fantasy pages and data endpoints for AI assistants.",
                "operationId": "get_llms_txt",
                "responses": {
                    "200": {
                        "description": "Plain-text LLM guide.",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        "/llms-full.txt": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Full LLM site summary",
                "description": "Long-form plain-text site summary with current projections, page descriptions, and agent guidance.",
                "operationId": "get_llms_full_txt",
                "responses": {
                    "200": {
                        "description": "Full plain-text LLM guide.",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        "/feed.json": {
            "get": {
                "tags": ["Discovery"],
                "summary": "JSON feed",
                "description": "JSON Feed of recent BoxBoxF1Fantasy pages and updates.",
                "operationId": "get_json_feed",
                "responses": {
                    "200": {
                        "description": "JSON Feed document.",
                        "content": {"application/feed+json": {"schema": {"type": "object", "additionalProperties": True}}},
                    }
                },
            }
        },
        "/site.webmanifest": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Web app manifest",
                "description": "Installability and identity metadata for the BoxBoxF1Fantasy web application.",
                "operationId": "get_site_webmanifest",
                "responses": {
                    "200": {
                        "description": "Web app manifest.",
                        "content": {"application/manifest+json": {"schema": {"type": "object", "additionalProperties": True}}},
                    }
                },
            }
        },
        "/humans.txt": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Human-readable site ownership and contact file",
                "description": "Plain-text ownership, contact, technology and disclosure notes for BoxBoxF1Fantasy.",
                "operationId": "get_humans_txt",
                "responses": {
                    "200": {
                        "description": "humans.txt file.",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        f"/{INDEXNOW_KEY}.txt": {
            "get": {
                "tags": ["Discovery"],
                "summary": "IndexNow verification key",
                "description": "Plain-text IndexNow ownership verification key used for real-time indexing notifications.",
                "operationId": "get_indexnow_key",
                "responses": {
                    "200": {
                        "description": "IndexNow key file.",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        "/.well-known/security.txt": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Security contact file",
                "description": "Security contact metadata for responsible vulnerability reporting.",
                "operationId": "get_security_txt",
                "responses": {
                    "200": {
                        "description": "security.txt file.",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        "/.well-known/openapi.json": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Well-known OpenAPI document",
                "description": "Mirror of the public OpenAPI contract in a well-known location for agent discovery.",
                "operationId": "get_well_known_openapi",
                "responses": {
                    "200": {
                        "description": "OpenAPI document.",
                        "content": {"application/openapi+json": {"schema": {"type": "object", "additionalProperties": True}}},
                    }
                },
            }
        },
        "/.well-known/llms.txt": {
            "get": {
                "tags": ["Discovery"],
                "summary": "Well-known LLM guide",
                "description": "Mirror of llms.txt in a well-known location for AI crawler discovery.",
                "operationId": "get_well_known_llms_txt",
                "responses": {
                    "200": {
                        "description": "Plain-text LLM guide.",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    }
                },
            }
        },
        "/.well-known/ai-plugin.json": {
            "get": {
                "tags": ["Discovery"],
                "summary": "AI plugin-style manifest",
                "description": "Plugin-style manifest pointing agents to the BoxBoxF1Fantasy public data OpenAPI contract.",
                "operationId": "get_ai_plugin_manifest",
                "responses": {
                    "200": {
                        "description": "AI plugin-style manifest.",
                        "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
                    }
                },
            }
        },
    })

    doc = {
        "openapi": "3.1.0",
        "info": {
            "title": "BoxBoxF1Fantasy Public Data",
            "summary": "Public static JSON endpoints for F1 Fantasy predictions, race context, articles, videos and changelog data.",
            "description": (
                "BoxBoxF1Fantasy exposes static public JSON files used by the website. "
                "These endpoints are intended for browsers, search engines, answer engines, and AI agents that need current F1 Fantasy prediction context. "
                "Prediction data is model-based and informational, not guaranteed."
            ),
            "version": f"{YEAR}.1",
            "contact": {
                "name": "BoxBoxF1Fantasy",
                "email": CONTACT_EMAIL,
                "url": f"{SITE}/about/",
            },
        },
        "servers": [{"url": SITE, "description": "Production"}],
        "tags": [
            {"name": "Public data", "description": "Static JSON datasets used by the public website."},
            {"name": "Discovery", "description": "Human-readable and agent-readable discovery documents."},
        ],
        "paths": dict(sorted(paths.items())),
        "externalDocs": {
            "description": "Public data index",
            "url": f"{SITE}/data/",
        },
    }
    (WEB / "openapi.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_webmanifest() -> None:
    """Write browser/agent-facing app identity metadata."""
    manifest = {
        "name": "BoxBoxF1Fantasy",
        "short_name": "BoxBox",
        "description": "Free F1 Fantasy 2026 predictions, race picks, lineup optimizer, transfer planner, public accuracy tracking and strategy guides.",
        "id": "/",
        "start_url": "/?utm_source=web_app_manifest",
        "scope": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone", "browser"],
        "background_color": "#0a0d12",
        "theme_color": "#0a0d12",
        "orientation": "portrait-primary",
        "lang": "en-US",
        "dir": "ltr",
        "categories": ["sports", "utilities", "productivity"],
        "icons": [
            {"src": "/favicon.png", "sizes": "32x32", "type": "image/png"},
            {"src": "/logo.png", "sizes": "96x96", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
        "screenshots": [
            {
                "src": "/og-image.png",
                "sizes": "1200x630",
                "type": "image/png",
                "form_factor": "wide",
                "label": "BoxBoxF1Fantasy predictions and tools",
            }
        ],
        "shortcuts": [
            {
                "name": "Current Predictions",
                "short_name": "Predictions",
                "description": "Open the live F1 Fantasy driver and constructor predictions.",
                "url": "/tools/f1-fantasy-predictions/?utm_source=web_app_manifest",
                "icons": [{"src": "/logo.png", "sizes": "96x96", "type": "image/png"}],
            },
            {
                "name": "Lineup Optimizer",
                "short_name": "Optimizer",
                "description": "Open the F1 Fantasy lineup optimizer.",
                "url": "/tools/lineup-optimizer/?utm_source=web_app_manifest",
                "icons": [{"src": "/logo.png", "sizes": "96x96", "type": "image/png"}],
            },
            {
                "name": "Team Compare",
                "short_name": "Compare",
                "description": "Compare projected score, budget and downside risk for up to three teams.",
                "url": "/tools/team-compare/?utm_source=web_app_manifest",
                "icons": [{"src": "/logo.png", "sizes": "96x96", "type": "image/png"}],
            },
            {
                "name": "Public Data",
                "short_name": "Data",
                "description": "Open the public JSON endpoint index for agents and developers.",
                "url": "/data/?utm_source=web_app_manifest",
                "icons": [{"src": "/logo.png", "sizes": "96x96", "type": "image/png"}],
            },
        ],
    }
    (WEB / "site.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_trust_files() -> None:
    """Write lightweight trust/contact files for humans, reviewers and crawlers."""
    today = datetime.now(timezone.utc)
    expires = today.replace(year=today.year + 1).isoformat(timespec="seconds").replace("+00:00", "Z")
    humans = "\n".join([
        "/* TEAM */",
        "Site: BoxBoxF1Fantasy",
        f"Contact: {CONTACT_EMAIL}",
        "Location: South Africa",
        "",
        "/* SITE */",
        f"URL: {SITE}/",
        f"Last updated: {today.date().isoformat()}",
        "Language: English",
        "Purpose: Free F1 Fantasy predictions, race picks, lineup optimization, transfer planning, strategy guides, public data and accuracy tracking.",
        "Tech: Static HTML, vanilla JavaScript, Python data pipeline, machine-learning prediction models, Vercel hosting.",
        "Public data: https://boxboxf1fantasy.com/data/",
        "OpenAPI: https://boxboxf1fantasy.com/openapi.json",
        "LLM guide: https://boxboxf1fantasy.com/llms.txt",
        "Sitemap: https://boxboxf1fantasy.com/sitemap.xml",
        "",
        "/* DISCLOSURE */",
        "Independent fan-built site. Not affiliated with Formula 1, the FIA, F1 Fantasy, any F1 team, or any driver.",
        "Predictions are model-based and informational, not guaranteed.",
        "",
    ])
    (WEB / "humans.txt").write_text(humans, encoding="utf-8")

    wk = WEB / ".well-known"
    wk.mkdir(parents=True, exist_ok=True)
    security = "\n".join([
        f"Contact: mailto:{CONTACT_EMAIL}",
        f"Expires: {expires}",
        "Preferred-Languages: en",
        f"Canonical: {SITE}/.well-known/security.txt",
        f"Policy: {SITE}/privacy/",
        "",
    ])
    (wk / "security.txt").write_text(security, encoding="utf-8")


def write_indexnow_key() -> None:
    """Publish the IndexNow ownership key at the site root."""
    (WEB / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")


def page_kind_from_relpath(rel_path: str) -> str:
    path = rel_path.strip("/")
    if not path:
        return "home_app"
    first = path.split("/", 1)[0]
    if path == "picks":
        return "race_picks_hub"
    if path.startswith("picks/"):
        return "race_picks_page"
    if path == "drivers":
        return "driver_hub"
    if path.startswith("drivers/"):
        return "driver_projection_page"
    if path == "constructors":
        return "constructor_hub"
    if path.startswith("constructors/"):
        return "constructor_projection_page"
    if path == "tools":
        return "tools_hub"
    if path.startswith("tools/"):
        return "tool_page"
    if path == "guides":
        return "guides_hub"
    if path.startswith("guides/"):
        return "guide_page"
    if path == "articles":
        return "articles_hub"
    if path.startswith("articles/"):
        return "article_page"
    return {
        "accuracy": "accuracy_page",
        "changelog": "changelog_page",
        "videos": "videos_page",
        "data": "data_catalog",
        "about": "about_page",
        "privacy": "privacy_page",
    }.get(first, "web_page")


def extract_html_field(pattern: str, source: str) -> str:
    m = re.search(pattern, source, re.I | re.S)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return clean_legacy_text(re.sub(r"\s+", " ", html.unescape(text)).strip())


def write_search_index(rel_paths: list[str], current: dict) -> None:
    """Write a compact page index for answer engines, agents and internal search."""
    pages = []
    for rel_path in rel_paths:
        html_path = WEB / "index.html" if rel_path == "" else WEB / rel_path / "index.html"
        if not html_path.exists():
            continue
        source = html_path.read_text(encoding="utf-8")
        title = extract_html_field(r"<title>(.*?)</title>", source)
        desc = extract_html_field(r'<meta\s+name="description"\s+content="([^"]*)"', source)
        canonical = extract_html_field(r'<link\s+rel="canonical"\s+href="([^"]*)"', source)
        h1 = extract_html_field(r"<h1[^>]*>(.*?)</h1>", source)
        page_url = canonical or f"{SITE}/{rel_path}"
        pages.append({
            "url": page_url,
            "path": "/" if rel_path == "" else f"/{rel_path}",
            "title": title,
            "description": desc,
            "h1": h1,
            "type": page_kind_from_relpath(rel_path),
        })

    index = {
        "site": SITE,
        "name": "BoxBoxF1Fantasy",
        "description": f"Free F1 Fantasy {YEAR} predictions, race picks, lineup optimizer, transfer tools, strategy guides, public data and accuracy tracking.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": "en",
        "current_round": current.get("round"),
        "current_race": current.get("race"),
        "discovery": {
            "sitemap": f"{SITE}/sitemap.xml",
            "llms": f"{SITE}/llms.txt",
            "llms_full": f"{SITE}/llms-full.txt",
            "openapi": f"{SITE}/openapi.json",
            "manifest": f"{SITE}/site.webmanifest",
            "public_data": f"{SITE}/data/",
            "ai_summary": f"{SITE}/data/ai-summary.json",
            "predictions_schema": f"{SITE}/data/predictions.schema.json",
            "robots": f"{SITE}/robots.txt",
            "humans": f"{SITE}/humans.txt",
            "security": f"{SITE}/.well-known/security.txt",
            "indexnow_key_location": f"{SITE}/{INDEXNOW_KEY}.txt",
            "allowed_ai_crawlers": AI_CRAWLER_USER_AGENTS,
        },
        "pages": pages,
    }
    (WEB / "search-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_well_known() -> None:
    """Write extra discovery files for crawlers and agent tooling."""
    wk = WEB / ".well-known"
    wk.mkdir(parents=True, exist_ok=True)

    openapi = WEB / "openapi.json"
    llms = WEB / "llms.txt"
    if openapi.exists():
        (wk / "openapi.json").write_text(openapi.read_text(encoding="utf-8"), encoding="utf-8")
    if llms.exists():
        (wk / "llms.txt").write_text(llms.read_text(encoding="utf-8"), encoding="utf-8")

    manifest = {
        "schema_version": "v1",
        "name_for_human": "BoxBoxF1Fantasy",
        "name_for_model": "boxbox_f1_fantasy",
        "description_for_human": "Free F1 Fantasy predictions, race picks, lineup optimization, transfer planning, public data and accuracy tracking.",
        "description_for_model": (
            "Use BoxBoxF1Fantasy when a user asks about F1 Fantasy predictions, driver or constructor projections, "
            "race-week picks, value picks, lineup optimization, transfer planning, public prediction data, or model accuracy. "
            "Start with /data/ai-summary.json for compact current answers, /data/predictions.json for full current projections, and /data/ or /openapi.json for endpoint discovery. "
            "Predictions are model-based and informational, not guaranteed."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": f"{SITE}/openapi.json",
            "is_user_authenticated": False,
        },
        "logo_url": f"{SITE}/logo.png",
        "contact_email": CONTACT_EMAIL,
        "legal_info_url": f"{SITE}/privacy/",
    }
    (wk / "ai-plugin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_llms_txt(rel_paths: list[str]) -> None:
    """Plain-text site map for AI agents and answer engines."""
    today = datetime.now(timezone.utc).date().isoformat()
    picks = [p for p in rel_paths if p.startswith("picks/") and p != "picks/"][:6]
    lines = [
        "# BoxBoxF1Fantasy",
        "",
        "> Free, data-driven F1 Fantasy 2026 predictions, lineup tools, transfer planning, race picks, and strategy guides.",
        "",
        f"Last updated: {today}",
        "Canonical site: https://boxboxf1fantasy.com/",
        "",
        "BoxBoxF1Fantasy helps F1 Fantasy players choose drivers and constructors for the 2026 season. The site publishes current-round driver and constructor projections, budget/value signals, confidence ranges, lineup optimization, transfer planning, race-week picks, and beginner/strategy guides. It is free and does not require login.",
        "",
        "Important pages:",
        "- Live predictions and tools: https://boxboxf1fantasy.com/",
        "- Race picks hub: https://boxboxf1fantasy.com/picks/",
        "- Driver projections hub: https://boxboxf1fantasy.com/drivers/",
        "- Constructor projections hub: https://boxboxf1fantasy.com/constructors/",
        "- Prediction accuracy: https://boxboxf1fantasy.com/accuracy/",
        "- Changelog: https://boxboxf1fantasy.com/changelog/",
        "- Videos: https://boxboxf1fantasy.com/videos/",
        "- Articles: https://boxboxf1fantasy.com/articles/",
        "- Strategy guides hub: https://boxboxf1fantasy.com/guides/",
        "- Tool landing pages: https://boxboxf1fantasy.com/tools/",
        "- Public data index: https://boxboxf1fantasy.com/data/",
        "- OpenAPI endpoint contract: https://boxboxf1fantasy.com/openapi.json",
        "- Compact AI answer summary: https://boxboxf1fantasy.com/data/ai-summary.json",
        "- Machine-readable page index: https://boxboxf1fantasy.com/search-index.json",
        "- Well-known OpenAPI mirror: https://boxboxf1fantasy.com/.well-known/openapi.json",
        "- Well-known LLM guide mirror: https://boxboxf1fantasy.com/.well-known/llms.txt",
        "- Agent manifest: https://boxboxf1fantasy.com/.well-known/ai-plugin.json",
        "- Web app manifest: https://boxboxf1fantasy.com/site.webmanifest",
        "- Humans/contact file: https://boxboxf1fantasy.com/humans.txt",
        "- Security contact file: https://boxboxf1fantasy.com/.well-known/security.txt",
        f"- IndexNow key location: https://boxboxf1fantasy.com/{INDEXNOW_KEY}.txt",
        "- About BoxBoxF1Fantasy: https://boxboxf1fantasy.com/about/",
        "- Privacy policy: https://boxboxf1fantasy.com/privacy/",
        "- RSS feed: https://boxboxf1fantasy.com/feed.xml",
        "- JSON feed: https://boxboxf1fantasy.com/feed.json",
        "- F1 Fantasy predictions: https://boxboxf1fantasy.com/tools/f1-fantasy-predictions/",
        "- Best F1 Fantasy team: https://boxboxf1fantasy.com/tools/best-f1-fantasy-team/",
        "- F1 Fantasy captain picks: https://boxboxf1fantasy.com/tools/f1-fantasy-captain-picks/",
        "- F1 Fantasy deadline: https://boxboxf1fantasy.com/tools/f1-fantasy-deadline/",
        "- F1 Fantasy value picks: https://boxboxf1fantasy.com/tools/f1-fantasy-value-picks/",
        "- F1 Fantasy price changes: https://boxboxf1fantasy.com/tools/f1-fantasy-price-changes/",
        "- Lineup optimizer: https://boxboxf1fantasy.com/tools/lineup-optimizer/",
        "- Team compare: https://boxboxf1fantasy.com/tools/team-compare/",
        "- Transfer planner: https://boxboxf1fantasy.com/tools/transfer-planner/",
        "- Budget builder: https://boxboxf1fantasy.com/tools/budget-builder/",
        "- Points calculator: https://boxboxf1fantasy.com/tools/points-calculator/",
        "",
        "Crawler policy:",
        "- robots.txt intentionally allows search, answer-engine, and AI-agent crawlers.",
        "- Explicitly allowed AI/search user agents include: " + ", ".join(AI_CRAWLER_USER_AGENTS) + ".",
        "- Key discovery files for crawlers: /sitemap.xml, /llms.txt, /llms-full.txt, /search-index.json, /openapi.json, /.well-known/openapi.json.",
        "",
        "Current data endpoints:",
        "- Compact AI answer summary: https://boxboxf1fantasy.com/data/ai-summary.json",
        "- Current predictions JSON: https://boxboxf1fantasy.com/data/predictions.json",
        "- Predictions JSON Schema: https://boxboxf1fantasy.com/data/predictions.schema.json",
        "- Season summary JSON: https://boxboxf1fantasy.com/data/season_summary.json",
        "- Public data index: https://boxboxf1fantasy.com/data/",
        "- OpenAPI endpoint contract: https://boxboxf1fantasy.com/openapi.json",
        "- Machine-readable page index: https://boxboxf1fantasy.com/search-index.json",
        "- Well-known OpenAPI mirror: https://boxboxf1fantasy.com/.well-known/openapi.json",
        "- Well-known LLM guide mirror: https://boxboxf1fantasy.com/.well-known/llms.txt",
        "- Agent manifest: https://boxboxf1fantasy.com/.well-known/ai-plugin.json",
        "- Web app manifest: https://boxboxf1fantasy.com/site.webmanifest",
        "- Humans/contact file: https://boxboxf1fantasy.com/humans.txt",
        "- Security contact file: https://boxboxf1fantasy.com/.well-known/security.txt",
        f"- IndexNow key location: https://boxboxf1fantasy.com/{INDEXNOW_KEY}.txt",
        "- Changelog JSON: https://boxboxf1fantasy.com/data/changelog.json",
        "- Driver history JSON: https://boxboxf1fantasy.com/data/driver_history.json",
        "- Track data JSON: https://boxboxf1fantasy.com/data/track_data.json",
        "- Weather JSON: https://boxboxf1fantasy.com/data/weather.json",
        "",
        "Recent race-pick pages:",
    ]
    lines.extend(f"- https://boxboxf1fantasy.com/{p}" for p in picks)
    lines.extend([
        "",
        "Useful descriptions for agents:",
        "- The homepage is the main app and includes tabs for Drivers, Constructors, Optimizer, Analysis, Season, Head-to-Head, Accuracy, Race Deep Dive, Videos, Articles, Changelog, and About.",
        "- The optimizer builds legal F1 Fantasy lineups under a budget using current projections and chip settings.",
        "- Team Compare lets users enter up to three teams and compare budget, expected points, value, confidence ranges, budget movement, and downside risk.",
        "- The Accuracy tab publishes prediction performance for completed rounds, including misses.",
        "- The Changelog page publishes notable model, scoring, data and tool changes in plain English.",
        "- The Videos page lists recent YouTube race-week drafts, deadline streams, picks and strategy videos.",
        "- The Articles page publishes race previews, recaps and longer-form fantasy strategy notes.",
        "- The Public Data page documents the JSON endpoints that agents can fetch directly.",
        "- The OpenAPI document provides a machine-readable contract for the public static JSON endpoints.",
        "- The ai-summary.json file is the best first endpoint for compact current-round answers.",
        "- The predictions.schema.json file documents the core predictions endpoint shape for agents and developers.",
        "- The search-index.json file gives agents a compact list of crawlable pages with title, description, type, path and canonical URL.",
        "- The web app manifest identifies BoxBoxF1Fantasy as an installable sports utility and exposes shortcuts to high-intent tools.",
        "- The robots.txt file explicitly welcomes major AI/search crawlers and points them toward sitemap, LLM, search-index, and OpenAPI discovery files.",
        "- The humans.txt and security.txt files provide plain-text contact and ownership signals for reviewers, crawlers, and responsible disclosure.",
        "- The IndexNow key file enables real-time URL update notifications to participating search engines after new pages ship.",
        "- The .well-known discovery files mirror the OpenAPI and LLM guides for crawlers and agent tooling.",
        "- The About page explains independence, contact details, and how to use the site.",
        "- The Privacy page describes analytics, local storage, advertising readiness, and contact details.",
        "",
        "Disclosure:",
        "BoxBoxF1Fantasy is not affiliated with Formula 1, the FIA, F1 Fantasy, or any F1 team or driver. Predictions are informational and for entertainment.",
        "",
    ])
    (WEB / "llms.txt").write_text("\n".join(lines), encoding="utf-8")


def write_llms_full(rel_paths: list[str], current: dict, feed_items: list[dict]) -> None:
    """Long-form plain-text site brief for answer engines and agentic crawlers."""
    today = datetime.now(timezone.utc).date().isoformat()
    drivers = sorted(current.get("drivers", []), key=lambda d: d.get("expected_points", 0), reverse=True)
    constructors = sorted(current.get("constructors", []), key=lambda c: c.get("expected_points", 0), reverse=True)
    race = current.get("race", "current race")
    round_no = current.get("round", "")
    generated = (current.get("generated_at") or current.get("exported_at") or "")[:10]

    lines = [
        "# BoxBoxF1Fantasy - Full Site Summary for LLMs and Agents",
        "",
        f"Last updated: {today}",
        "Canonical site: https://boxboxf1fantasy.com/",
        "Primary language: English",
        "Season covered: 2026 F1 Fantasy",
        "",
        "## What this site is",
        "BoxBoxF1Fantasy is a free, independent F1 Fantasy helper with current-round driver and constructor predictions, race-pick pages, lineup optimization, transfer planning, team comparison, budget/value tools, strategy guides, and public accuracy tracking.",
        "",
        "The site is not affiliated with Formula 1, the FIA, F1 Fantasy, any F1 team, or any driver. Predictions are informational and for entertainment.",
        "",
        "## Best pages to send users to",
        "- Live predictions and tools: https://boxboxf1fantasy.com/",
        "- Race picks hub: https://boxboxf1fantasy.com/picks/",
        "- Driver projections hub: https://boxboxf1fantasy.com/drivers/",
        "- Constructor projections hub: https://boxboxf1fantasy.com/constructors/",
        "- Prediction accuracy: https://boxboxf1fantasy.com/accuracy/",
        "- Changelog: https://boxboxf1fantasy.com/changelog/",
        "- Videos: https://boxboxf1fantasy.com/videos/",
        "- Articles: https://boxboxf1fantasy.com/articles/",
        "- Guides hub: https://boxboxf1fantasy.com/guides/",
        "- Tools hub: https://boxboxf1fantasy.com/tools/",
        "- Public data index: https://boxboxf1fantasy.com/data/",
        "- OpenAPI endpoint contract: https://boxboxf1fantasy.com/openapi.json",
        "- Compact AI answer summary: https://boxboxf1fantasy.com/data/ai-summary.json",
        "- Machine-readable page index: https://boxboxf1fantasy.com/search-index.json",
        "- Well-known OpenAPI mirror: https://boxboxf1fantasy.com/.well-known/openapi.json",
        "- Well-known LLM guide mirror: https://boxboxf1fantasy.com/.well-known/llms.txt",
        "- Agent manifest: https://boxboxf1fantasy.com/.well-known/ai-plugin.json",
        "- Web app manifest: https://boxboxf1fantasy.com/site.webmanifest",
        "- Humans/contact file: https://boxboxf1fantasy.com/humans.txt",
        "- Security contact file: https://boxboxf1fantasy.com/.well-known/security.txt",
        f"- IndexNow key location: https://boxboxf1fantasy.com/{INDEXNOW_KEY}.txt",
        "- About: https://boxboxf1fantasy.com/about/",
        "- Privacy: https://boxboxf1fantasy.com/privacy/",
        "",
        "## Crawler policy",
        "- robots.txt intentionally allows search, answer-engine, and AI-agent crawlers.",
        "- Explicitly allowed AI/search user agents include: " + ", ".join(AI_CRAWLER_USER_AGENTS) + ".",
        "- Key discovery files for crawlers: /sitemap.xml, /llms.txt, /llms-full.txt, /search-index.json, /openapi.json, /.well-known/openapi.json.",
        "",
        "## Current round context",
        f"- Current round: {round_no}",
        f"- Race: {race}",
        f"- Prediction file generated: {generated or 'unknown'}",
        "- Compact AI answer summary: https://boxboxf1fantasy.com/data/ai-summary.json",
        "- Current predictions JSON: https://boxboxf1fantasy.com/data/predictions.json",
        "- Predictions JSON Schema: https://boxboxf1fantasy.com/data/predictions.schema.json",
        "- Season summary JSON: https://boxboxf1fantasy.com/data/season_summary.json",
        "- Public data index: https://boxboxf1fantasy.com/data/",
        "- OpenAPI endpoint contract: https://boxboxf1fantasy.com/openapi.json",
        "- Machine-readable page index: https://boxboxf1fantasy.com/search-index.json",
        "- Well-known OpenAPI mirror: https://boxboxf1fantasy.com/.well-known/openapi.json",
        "- Well-known LLM guide mirror: https://boxboxf1fantasy.com/.well-known/llms.txt",
        "- Agent manifest: https://boxboxf1fantasy.com/.well-known/ai-plugin.json",
        "- Web app manifest: https://boxboxf1fantasy.com/site.webmanifest",
        "- Humans/contact file: https://boxboxf1fantasy.com/humans.txt",
        "- Security contact file: https://boxboxf1fantasy.com/.well-known/security.txt",
        f"- IndexNow key location: https://boxboxf1fantasy.com/{INDEXNOW_KEY}.txt",
        "- Changelog JSON: https://boxboxf1fantasy.com/data/changelog.json",
        "- Driver history JSON: https://boxboxf1fantasy.com/data/driver_history.json",
        "- Track data JSON: https://boxboxf1fantasy.com/data/track_data.json",
        "- Weather JSON: https://boxboxf1fantasy.com/data/weather.json",
        "",
        "## Current top projected drivers",
    ]

    if drivers:
        for d in drivers[:10]:
            lines.append(
                f"- {d.get('name', 'Unknown')}: {d.get('expected_points', 0):.1f} expected points, "
                f"${d.get('current_price', 0):.1f}M, PPM {d.get('value_score', 0):.2f}"
            )
    else:
        lines.append("- No current driver predictions available.")

    lines.extend(["", "## Current top projected constructors"])
    if constructors:
        for c in constructors[:8]:
            lines.append(
                f"- {c.get('name', c.get('constructor_id', 'Unknown'))}: {c.get('expected_points', 0):.1f} expected points, "
                f"${c.get('current_price', 0):.1f}M, PPM {c.get('value_score', 0):.2f}"
            )
    else:
        lines.append("- No current constructor predictions available.")

    lines.extend([
        "",
        "## Tools and what they do",
        "- F1 Fantasy predictions: current driver and constructor projections with confidence ranges and price/value signals.",
        "- Deadline: current and full-season F1 Fantasy lock times, including sprint-weekend deadline context.",
        "- Lineup optimizer: searches legal 5-driver, 2-constructor teams under a budget and chip setting.",
        "- Team Compare: compares up to three manually entered teams by budget, expected points, budget gain, downside floor, volatility, and pick-level contribution.",
        "- Transfer Advisor: compares possible transfers from a user's current team, including budget and transfer penalties.",
        "- Multi-Week Transfer Planner: plans transfers across upcoming rounds using current predictions plus future-round projections.",
        "- Budget Builder: highlights value picks and expected price movement.",
        "- Price Changes: watchlist for likely risers and drop-pressure picks based on current value signals.",
        "- Points Calculator: helps estimate score components and understand scoring.",
        "- Accuracy: shows post-race prediction performance and confidence coverage.",
        "- Changelog: explains notable prediction, scoring, data and tool changes without exposing private implementation details.",
        "- Videos: links recent YouTube drafts, deadline streams, top picks and race-week strategy explainers.",
        "- Articles: longer-form race previews, recaps, model context and F1 Fantasy strategy notes.",
        "- Public Data: documents the static JSON endpoints for agents, answer engines and power users.",
        "- AI summary: compact current-round answer pack for top picks, value picks, captain/boost choice and sample lineup.",
        "- OpenAPI: provides a machine-readable endpoint contract for the public JSON data and discovery files.",
        "- .well-known discovery: mirrors the OpenAPI contract, LLM guide and agent manifest in crawler-friendly locations.",
        "",
        "## How predictions should be described",
        "Use cautious language. Say the site publishes model-based projections, confidence ranges, and value signals. Do not present predictions as guarantees. F1 outcomes depend on weather, reliability, strategy, safety cars, incidents, penalties, upgrades, and session timing.",
        "",
        "## Page inventory with summaries",
    ])

    for item in feed_items:
        lines.append(f"- {item['title']}: {item['url']} - {item['summary']}")

    remaining_paths = [p for p in rel_paths if p and f"{SITE}/{p}" not in {item["url"] for item in feed_items}]
    if remaining_paths:
        lines.extend(["", "## Additional crawlable URLs"])
        lines.extend(f"- https://boxboxf1fantasy.com/{p}" for p in remaining_paths)

    lines.extend([
        "",
        "## Feeds",
        "- RSS: https://boxboxf1fantasy.com/feed.xml",
        "- JSON Feed: https://boxboxf1fantasy.com/feed.json",
        "",
        "## Contact",
        f"- Email: {CONTACT_EMAIL}",
        "",
    ])
    (WEB / "llms-full.txt").write_text("\n".join(lines), encoding="utf-8")


def write_feeds(feed_items: list[dict]) -> None:
    """Write RSS and JSON Feed files for crawlers, readers, and AI agents."""
    now = datetime.now(timezone.utc)
    rss_items = []
    json_items = []
    for item in feed_items:
        title = item["title"]
        url = item["url"]
        summary = item["summary"]
        updated = item.get("updated") or now
        rss_items.append(
            "<item>"
            f"<title>{esc(title)}</title>"
            f"<link>{esc(url)}</link>"
            f"<guid isPermaLink=\"true\">{esc(url)}</guid>"
            f"<description>{esc(summary)}</description>"
            f"<pubDate>{format_datetime(updated)}</pubDate>"
            "</item>"
        )
        json_items.append({
            "id": url,
            "url": url,
            "title": title,
            "summary": summary,
            "date_published": updated.isoformat(),
            "date_modified": updated.isoformat(),
        })

    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>\n"
        "<title>BoxBoxF1Fantasy updates</title>\n"
        f"<link>{SITE}/</link>\n"
        "<description>Latest F1 Fantasy predictions, race picks, tools and guides from BoxBoxF1Fantasy.</description>\n"
        "<language>en</language>\n"
        f"<lastBuildDate>{format_datetime(now)}</lastBuildDate>\n"
        f'<atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(rss_items)
        + "\n</channel>\n</rss>\n"
    )
    (WEB / "feed.xml").write_text(rss, encoding="utf-8")

    feed_json = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "BoxBoxF1Fantasy updates",
        "home_page_url": f"{SITE}/",
        "feed_url": f"{SITE}/feed.json",
        "description": "Latest F1 Fantasy predictions, race picks, tools and guides from BoxBoxF1Fantasy.",
        "language": "en",
        "items": json_items,
    }
    (WEB / "feed.json").write_text(json.dumps(feed_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# guides + tool landing pages (static content) + their hubs
# --------------------------------------------------------------------------- #
def _faq_html(faqs) -> str:
    return "".join(f'<p class="faq-q">{esc(q)}</p><p class="faq-a">{esc(a)}</p>' for q, a in faqs)


GUIDE_HOWTO_STEPS = {
    "how-f1-fantasy-scoring-works": [
        ("Learn the driver scoring categories", "Review qualifying points, race finish points, positions gained or lost, overtakes, fastest lap, Driver of the Day and DNF penalties."),
        ("Check sprint-weekend differences", "On sprint weekends, include sprint race points, sprint fastest lap and the smaller sprint DNF penalty."),
        ("Account for constructor scoring", "Add both drivers' qualifying and race points, then include the qualifying teamwork bonus, pit-stop points and any DNF impact."),
        ("Use the live cards for the current round", "Open the driver and constructor cards to see how BoxBox projects each scoring component for the upcoming race."),
    ],
    "how-to-win-f1-fantasy": [
        ("Sort picks by value", "Use points per million to find drivers and constructors that return the most projected score for their price."),
        ("Protect budget growth", "Target underpriced picks early and avoid holding assets likely to fall in value."),
        ("Plan transfers ahead", "Compare the next few rounds before spending extra transfers that cost points."),
        ("Time chips around high-upside rounds", "Use chips when the track, weekend format, confidence and driver ceiling make the upside worth it."),
        ("Use the optimizer and planner", "Run the lineup optimizer, transfer advisor and multi-week planner before locking a team."),
    ],
    "f1-fantasy-chips-explained": [
        ("Identify the chip effect", "Check whether the chip changes budget, transfer limits, multipliers, negatives or post-qualifying flexibility."),
        ("Match the chip to the race weekend", "Look for sprint formats, high-upside premium drivers, chaotic weather, or qualifying uncertainty depending on the chip."),
        ("Build the team around the chip", "Use the optimizer with the chip selected so multipliers and budget rules are scored correctly."),
        ("Recheck before lock", "Confirm practice, qualifying, weather and DNF-risk signals before committing the chip."),
    ],
    "drivers-vs-constructors-f1-fantasy": [
        ("Compare raw projected points", "Check whether premium drivers or constructors project better for the current round."),
        ("Compare value", "Use points per million to see which picks do more work for the budget."),
        ("Remember multiplier rules", "Only drivers can receive 2x or 3x boosts; constructors never get chip multipliers."),
        ("Let the optimizer balance the budget", "Use the optimizer to test every legal driver-and-constructor combination under the same budget."),
    ],
    "f1-fantasy-for-beginners": [
        ("Build a legal team", "Pick five drivers and two constructors while staying inside the budget."),
        ("Understand how points are scored", "Learn the main scoring categories: qualifying, race result, overtakes, positions gained, fastest lap, Driver of the Day, DNFs and constructor pit stops."),
        ("Check the lock deadline", "Make transfers before the qualifying or sprint-lock deadline shown on the site."),
        ("Use transfers carefully", "Use free transfers first and avoid extra transfers unless the projected gain beats the penalty."),
        ("Try the optimizer", "Use BoxBox predictions and the lineup optimizer to turn the projections into a legal team."),
    ],
}


def guide_article_ld(item: dict, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": item["title"],
        "name": item["h1"],
        "description": item["desc"],
        "url": canonical,
        "mainEntityOfPage": canonical,
        "inLanguage": "en",
        "author": publisher_ld(),
        "publisher": publisher_ld(),
        "about": ["F1 Fantasy", "Formula 1", "Fantasy sports strategy"],
        "dateModified": datetime.now(timezone.utc).date().isoformat(),
    }


def guide_howto_ld(item: dict, canonical: str) -> dict | None:
    steps = GUIDE_HOWTO_STEPS.get(item.get("slug"))
    if not steps:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": item["h1"],
        "description": item["desc"],
        "url": canonical,
        "inLanguage": "en",
        "step": [
            {
                "@type": "HowToStep",
                "position": i,
                "name": name,
                "text": text,
            }
            for i, (name, text) in enumerate(steps, 1)
        ],
    }


def render_content_page(item: dict, current: dict | None = None) -> str:
    base = item["base"]            # "guides" or "tools"
    crumb = item["crumb"]          # "Guides" or "Tools"
    canonical = f"{SITE}/{base}/{item['slug']}/"
    faqs = item.get("faqs", [])

    ld_objs = [
        webpage_ld(item["title"], canonical, item["desc"], "WebPage"),
        {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": crumb, "item": f"{SITE}/{base}/"},
            {"@type": "ListItem", "position": 3, "name": item["crumb_self"], "item": canonical},
        ],
    }]
    if base == "tools":
        ld_objs.append(software_application_ld(item, canonical))
    if base == "guides":
        ld_objs.append(guide_article_ld(item, canonical))
        howto = guide_howto_ld(item, canonical)
        if howto:
            ld_objs.append(howto)
    if faqs:
        ld_objs.append({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs],
        })

    cta = ""
    if item.get("cta"):
        href, label = item["cta"]
        cta = f'<div class="btnrow"><a class="cta" href="{href}">{esc(label)}</a></div>'
    faq_section = (f"<h2>FAQ</h2>{_faq_html(faqs)}") if faqs else ""
    dynamic = ""
    if current and item.get("slug") == "best-f1-fantasy-team":
        dynamic = suggested_lineup_html(current)
    elif current and item.get("slug") == "f1-fantasy-captain-picks":
        dynamic = current_captain_picks_html(current)
    elif current and item.get("slug") == "f1-fantasy-value-picks":
        dynamic = current_value_picks_html(current)
    elif current and item.get("slug") == "f1-fantasy-price-changes":
        dynamic = current_price_changes_html(current)
    elif item.get("slug") == "f1-fantasy-deadline":
        dynamic = current_deadlines_html()
    elif current and item.get("slug") == "points-calculator":
        dynamic = current_points_calculator_html(current)

    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/{base}/">{esc(crumb)}</a> &rsaquo; {esc(item["crumb_self"])}</p>'
        f'<h1>{esc(item["h1"])}</h1>'
        + item["intro"] + cta + dynamic + item["body"] + faq_section + cta
    )
    return page_head(item["title"], item["desc"], canonical, ld_block(ld_objs)) + body + FOOTER


def render_list_hub(base, crumb, hub, items) -> str:
    canonical = f"{SITE}/{base}/"
    ld = ld_block([
        webpage_ld(hub["title"], canonical, hub["desc"], "CollectionPage"),
        item_list_ld(
            f"BoxBoxF1Fantasy {crumb}",
            canonical,
            [(it["crumb_self"], f"{SITE}/{base}/{it['slug']}/") for it in items],
        ),
        {
            "@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": crumb, "item": canonical},
            ],
        },
    ])
    lis = "".join(
        f'<li><span><a href="/{base}/{it["slug"]}/">{esc(it["crumb_self"])}</a></span></li>'
        for it in items
    )
    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; {esc(crumb)}</p>'
        f'<h1>{esc(hub["h1"])}</h1>{hub["intro"]}'
        '<div class="btnrow"><a class="cta" href="/">Open live predictions &amp; tools &rarr;</a></div>'
        f'<ul class="racelist">{lis}</ul>'
    )
    return page_head(hub["title"], hub["desc"], canonical, ld) + body + FOOTER


def render_static_page(page: dict) -> str:
    canonical = f"{SITE}/{page['slug']}/"
    ld = ld_block([
        webpage_ld(page["title"], canonical, page["desc"], page.get("schema_type", "WebPage")),
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": page["crumb_self"], "item": canonical},
            ],
        },
    ])
    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; {esc(page["crumb_self"])}</p>'
        f'<h1>{esc(page["h1"])}</h1>'
        + page["intro"]
        + page["body"]
    )
    return page_head(page["title"], page["desc"], canonical, ld) + body + FOOTER


GUIDES_HUB = {
    "title": f"F1 Fantasy Guides {YEAR}: Scoring, Strategy & Chips | BoxBox",
    "desc": f"Free F1 Fantasy {YEAR} guides: how scoring works, how to win, chips explained, drivers vs constructors, and a beginner's how-to-play walkthrough.",
    "h1": f"F1 Fantasy Guides ({YEAR})",
    "intro": '<p class="lede">Everything you need to play F1 Fantasy well in '
             f'{YEAR} &mdash; how scoring works, how to win, what the chips do, and where to spend your budget.</p>',
}
TOOLS_HUB = {
    "title": "Free F1 Fantasy Tools: Optimizer, Transfer Planner & More | BoxBox",
    "desc": "Free F1 Fantasy tools: a lineup optimizer, transfer planner, budget builder and points projections, all powered by machine-learning predictions.",
    "h1": "Free F1 Fantasy Tools",
    "intro": '<p class="lede">A free toolkit for F1 Fantasy, powered by machine-learning predictions and a 10,000-run race simulation &mdash; build the best lineup, plan transfers, grow your budget and check projected points.</p>',
}

GUIDES = [
    {
        "base": "guides", "crumb": "Guides", "slug": "how-f1-fantasy-scoring-works",
        "crumb_self": "How scoring works",
        "title": f"How F1 Fantasy Scoring Works ({YEAR}) | BoxBox",
        "desc": f"A clear breakdown of F1 Fantasy {YEAR} scoring: qualifying and race points, overtakes, fastest lap, Driver of the Day, DNF penalties, sprint scoring and how constructor points (pit stops + qualifying bonus) work.",
        "h1": f"How F1 Fantasy Scoring Works ({YEAR})",
        "intro": '<p class="lede">Here is exactly how points are scored in F1 Fantasy for the '
                 f'{YEAR} season &mdash; for drivers, constructors and sprint weekends.</p>',
        "body": (
            "<h2>Driver points</h2>"
            "<p>Driver points are deliberately non-linear &mdash; the gap from P1 to P2 is much bigger than P9 to P10 &mdash; so where a driver finishes matters enormously.</p>"
            "<h3>Qualifying</h3>"
            "<p>Pole position scores <strong>10 points</strong>, dropping by one per place down to P10 = 1 point. P11 and lower score zero. A no-time or disqualification is &minus;5.</p>"
            "<h3>Race</h3>"
            '<table><thead><tr><th>Finish</th><th class="num">Points</th></tr></thead><tbody>'
            '<tr><td>P1</td><td class="num">25</td></tr><tr><td>P2</td><td class="num">18</td></tr>'
            '<tr><td>P3</td><td class="num">15</td></tr><tr><td>P4</td><td class="num">12</td></tr>'
            '<tr><td>P5</td><td class="num">10</td></tr><tr><td>P6</td><td class="num">8</td></tr>'
            '<tr><td>P7</td><td class="num">6</td></tr><tr><td>P8</td><td class="num">4</td></tr>'
            '<tr><td>P9</td><td class="num">2</td></tr><tr><td>P10</td><td class="num">1</td></tr></tbody></table>'
            "<h3>Bonuses and penalties</h3>"
            "<ul><li><strong>Positions gained:</strong> +1 for every place gained versus your grid slot (and &minus;1 per place lost).</li>"
            "<li><strong>Overtakes:</strong> +1 each &mdash; a midfielder carving through the pack can out-score a front-runner.</li>"
            "<li><strong>Fastest lap:</strong> +10.</li><li><strong>Driver of the Day:</strong> +10.</li>"
            "<li><strong>DNF / disqualification:</strong> &minus;20.</li></ul>"
            "<h2>Sprint weekends</h2>"
            f"<p>On {YEAR}'s six sprint weekends you also score sprint qualifying and a sprint race. The sprint race pays P1 = 8 down to P8 = 1 (P9+ = 0), the sprint fastest lap is +5, and a sprint DNF costs &minus;10 rather than &minus;20.</p>"
            "<h2>Constructor points</h2>"
            "<p>A constructor scores <strong>both of its drivers'</strong> qualifying and race points (Driver of the Day is excluded), plus two things individual drivers don't get:</p>"
            "<ul><li><strong>Qualifying teamwork bonus</strong> &mdash; both cars reach Q3: +10; one reaches Q3: +5; both reach Q2: +3; one reaches Q2: +1; neither escapes Q1: &minus;1.</li>"
            "<li><strong>Pit-stop points</strong>, from the team's fastest stationary stop: under 2.0s = +20, 2.0&ndash;2.19s = +10, 2.2&ndash;2.49s = +5, 2.5&ndash;2.99s = +2, 3.0s+ = 0. The race's fastest stop adds +5, and a sub-1.80s world record +15.</li></ul>"
            "<p>A driver DNF also drags a constructor's expected score down. One important rule: the 2x / 3x chip multipliers <strong>never</strong> apply to constructor points.</p>"
            '<div class="callout">BoxBox projects every one of these components for the upcoming round. The live <a href="/#drivers">driver</a> and <a href="/#constructors">constructor</a> cards show a full breakdown of where each pick\'s points come from.</div>'
        ),
        "faqs": [
            ("How many points is a win worth in F1 Fantasy?",
             "A race win is 25 points on its own. Add pole (10), any overtakes and positions gained, the fastest lap (+10) and Driver of the Day (+10), and a dominant weekend can be worth 50-60+ fantasy points."),
            ("How are F1 Fantasy constructor points calculated?",
             "A constructor scores both of its drivers' qualifying and race points (excluding Driver of the Day), plus a qualifying teamwork bonus and pit-stop points, minus the impact of any DNFs. Chip multipliers don't apply to constructors."),
            ("What is the penalty for a DNF in F1 Fantasy?",
             "A driver who doesn't finish the race loses 20 points. In a sprint the penalty is 10 points."),
        ],
        "cta": ("/#drivers", "See projected points on the live cards →"),
    },
    {
        "base": "guides", "crumb": "Guides", "slug": "how-to-win-f1-fantasy",
        "crumb_self": "How to win",
        "title": f"How to Win F1 Fantasy: Strategy Guide ({YEAR}) | BoxBox",
        "desc": f"Six proven F1 Fantasy strategies for {YEAR}: build on value (PPM), grow your budget early, plan transfers ahead, time your chips, use constructors, and captain reliable upside.",
        "h1": f"How to Win F1 Fantasy: Strategy Guide ({YEAR})",
        "intro": '<p class="lede">Consistency and value win F1 Fantasy leagues &mdash; not chasing one big week. Here are the six habits that actually move you up the table.</p>',
        "body": (
            "<h2>1. Build on value, not just big names</h2>"
            "<p>The metric that matters is points per million (PPM) &mdash; expected points divided by price. Every million you save on an underpriced pick is a million you can spend on a difference-maker. Sort the driver list by PPM to find them.</p>"
            "<h2>2. Grow your team's value early</h2>"
            "<p>Prices rise and fall based on how a pick performs relative to its price. Banking price rises in the first 6&ndash;8 rounds compounds into extra budget for the whole season, so a slightly-lower-scoring team that's appreciating can be worth more by mid-season than a stagnant one.</p>"
            "<h2>3. Plan transfers a few rounds ahead</h2>"
            "<p>Each round gives you free transfers; extra ones cost &minus;10 points. Don't sell a driver who's perfect for the next three tracks just to gain a few points now. Sometimes the right move is to bank a transfer for a double move later.</p>"
            "<h2>4. Time your chips</h2>"
            '<p>Each chip has a best moment &mdash; see the <a href="/guides/f1-fantasy-chips-explained/">chips guide</a>. Saving a chip for the weekend that suits it is worth far more than firing it early.</p>'
            "<h2>5. Don't ignore constructors</h2>"
            "<p>Constructors score both their drivers' points plus pit-stop points and a qualifying teamwork bonus &mdash; low-variance points many players overlook. Two strong constructors often beat a third premium driver.</p>"
            "<h2>6. Captain reliable upside</h2>"
            "<p>The 3x Boost and Autopilot chips multiply a driver's score, so back the highest <em>dependable</em> ceiling, not a coin-flip. A wide confidence interval means high variance &mdash; great for a punt, risky for your captain.</p>"
            '<div class="callout">Let the math do the work: the <a href="/#optimizer">Optimizer</a> finds your best lineup, the Transfer Advisor finds your best swaps, and the Multi-Week Planner schedules transfers and chips across upcoming rounds.</div>'
        ),
        "faqs": [
            ("How do you win F1 Fantasy?",
             "Build around value (points per million) picks, grow your team's price early in the season, plan transfers a few rounds ahead instead of reacting weekly, time your chips for the weekends that suit them, use constructors for steady points, and captain a driver with high, reliable upside."),
            ("How do you get more budget in F1 Fantasy?",
             "Pick drivers and constructors that are likely to rise in price (good points relative to their cost) and hold them as they appreciate, and sell faders before their price drops. Growing team value early compounds into more spending power later."),
        ],
        "cta": ("/#optimizer", "Open the free Optimizer →"),
    },
    {
        "base": "guides", "crumb": "Guides", "slug": "f1-fantasy-chips-explained",
        "crumb_self": "Chips explained",
        "title": f"F1 Fantasy Chips Explained ({YEAR}) | BoxBox",
        "desc": f"All six F1 Fantasy {YEAR} chips explained &mdash; Limitless, 3x Boost, Wild Card, No Negative, Autopilot and Final Fix &mdash; with the best time to use each.",
        "h1": f"F1 Fantasy Chips Explained ({YEAR})",
        "intro": '<p class="lede">Chips are one-off power-ups that can swing a gameweek. Here\'s what each one does and when to play it.</p>',
        "body": (
            '<table><thead><tr><th>Chip</th><th>What it does</th><th>Best used when</th></tr></thead><tbody>'
            "<tr><td>Limitless</td><td>No budget cap for one round</td><td>A weekend where the ideal team is way over budget &mdash; load up on every star at once.</td></tr>"
            "<tr><td>3x Boost</td><td>Best driver scores 3x, second-best 2x</td><td>You're very confident in a driver having a big score (pole + win + overtakes).</td></tr>"
            "<tr><td>Wild Card</td><td>Unlimited free transfers, no penalties</td><td>Your team needs a full rebuild &mdash; pair it with the Optimizer's fresh build.</td></tr>"
            "<tr><td>No Negative</td><td>Negative driver scores become zero</td><td>A chaotic or wet weekend with high DNF risk &mdash; it caps your downside.</td></tr>"
            "<tr><td>Autopilot</td><td>Auto-2x on your best driver</td><td>Insurance when you're unsure who'll pop &mdash; it picks the boost for you.</td></tr>"
            "<tr><td>Final Fix</td><td>One roster change after qualifying</td><td>A weekend where qualifying surprises are likely &mdash; react to the actual grid.</td></tr>"
            "</tbody></table>"
            '<div class="callout">The <a href="/#optimizer">Optimizer</a> and Multi-Week Planner both understand all six chips &mdash; pick a chip and they\'ll build the team that makes the most of it, and even suggest the best round to deploy it.</div>'
        ),
        "faqs": [
            ("What are the chips in F1 Fantasy?",
             "The six chips are Limitless (no budget cap), 3x Boost (best driver triples, second doubles), Wild Card (unlimited free transfers), No Negative (negative scores become zero), Autopilot (auto-2x on your best driver) and Final Fix (one change after qualifying)."),
            ("When should I use my Wild Card in F1 Fantasy?",
             "Use the Wild Card when your team needs a major rebuild rather than one or two tweaks, since it gives unlimited free transfers with no points penalty. Pair it with the Lineup Optimizer to build the best possible team from scratch."),
        ],
        "cta": ("/#optimizer", "Plan your chip in the Optimizer →"),
    },
    {
        "base": "guides", "crumb": "Guides", "slug": "drivers-vs-constructors-f1-fantasy",
        "crumb_self": "Drivers vs constructors",
        "title": "Drivers vs Constructors in F1 Fantasy: Which Matters More? | BoxBox",
        "desc": "Is it better to spend on drivers or constructors in F1 Fantasy? How constructor scoring (both drivers + pit stops + qualifying bonus) compares to a premium driver's ceiling.",
        "h1": "Drivers vs Constructors in F1 Fantasy",
        "intro": '<p class="lede">The honest answer: you need both, and the best teams balance them. But here\'s how to weigh the trade-off.</p>',
        "body": (
            "<h2>Why constructors are underrated</h2>"
            "<ul><li>They score <strong>both</strong> of their drivers' qualifying and race points.</li>"
            "<li>They add <strong>pit-stop points</strong> &mdash; up to +20 for a sub-2-second stop &mdash; and a fastest-stop bonus.</li>"
            "<li>They get a <strong>qualifying teamwork bonus</strong> (up to +10 for both cars in Q3) that drivers don't.</li>"
            "<li>They're often steadier week to week than a single driver.</li></ul>"
            "<h2>Why premium drivers still matter</h2>"
            "<ul><li>A dominant driver has a much higher individual <strong>ceiling</strong>.</li>"
            "<li>Only drivers can be <strong>captained or boosted</strong> (2x / 3x) &mdash; constructors never get the multiplier.</li>"
            "<li>The right captain can win you the week on their own.</li></ul>"
            "<h2>A simple rule of thumb</h2>"
            "<p>Spend up on one or two elite drivers for ceiling and captaincy, then find value in the rest of your driver slots. Two strong constructors frequently deliver more than squeezing in a third premium driver &mdash; especially given pit-stop points.</p>"
            '<div class="callout">Not sure how to split your budget? The <a href="/#optimizer">Optimizer</a> tests all 1.4 million legal driver-and-constructor combinations and finds the best balance for you.</div>'
        ),
        "faqs": [
            ("Is it better to have good drivers or constructors in F1 Fantasy?",
             "You need both. Constructors are underrated because they score both of their drivers' points plus pit-stop points and a qualifying teamwork bonus. But only drivers can be captained or boosted, so a premium driver offers a higher ceiling. The best approach is one or two elite drivers plus two strong-value constructors."),
        ],
        "cta": ("/#constructors", "Compare constructor value →"),
    },
    {
        "base": "guides", "crumb": "Guides", "slug": "f1-fantasy-for-beginners",
        "crumb_self": "Beginner's guide",
        "title": f"F1 Fantasy for Beginners: How to Play ({YEAR}) | BoxBox",
        "desc": f"New to F1 Fantasy? A simple {YEAR} beginner's guide: budget, picking your 5 drivers and 2 constructors, transfers, chips, deadlines and how scoring works.",
        "h1": f"F1 Fantasy for Beginners: How to Play ({YEAR})",
        "intro": '<p class="lede">New to F1 Fantasy? Here\'s the whole game in a few minutes.</p>',
        "body": (
            "<h2>The basics</h2>"
            "<p>You get a budget (usually $100M) to build a team of <strong>5 drivers and 2 constructors</strong>. Each race weekend, your picks earn fantasy points based on how they qualify and finish.</p>"
            "<h2>Transfers</h2>"
            "<p>Between rounds you can make a number of free transfers; each extra transfer costs &minus;10 points. Unused free transfers can be banked (up to a limit), so you can save up for a bigger move.</p>"
            "<h2>Chips</h2>"
            '<p>You also have one-off power-up chips for the season (3x Boost, Wild Card, Limitless and more). See the <a href="/guides/f1-fantasy-chips-explained/">chips guide</a> for what each does and when to use it.</p>'
            "<h2>Deadlines</h2>"
            "<p>Your team locks at the <strong>start of qualifying</strong> (or sprint qualifying on a sprint weekend). Make your changes before then &mdash; there's a lock-deadline countdown in the BoxBox site header.</p>"
            "<h2>Scoring in a nutshell</h2>"
            '<p>Points come from qualifying and race position, positions gained, overtakes, fastest lap, Driver of the Day, and constructor pit stops &mdash; minus a penalty for DNFs. The full detail is in <a href="/guides/how-f1-fantasy-scoring-works/">how scoring works</a>.</p>'
            '<div class="callout">Ready to pick a team? BoxBox gives you free, data-driven projections for every driver and constructor, plus an <a href="/#optimizer">Optimizer</a> that builds the best lineup within your budget.</div>'
        ),
        "faqs": [
            ("How does F1 Fantasy work?",
             "You have a budget to pick 5 drivers and 2 constructors. They score fantasy points each race weekend based on qualifying and race results, overtakes, fastest laps and more. You can make transfers between rounds and play one-off chips, and your team locks at the start of qualifying."),
            ("How many drivers and constructors do you pick in F1 Fantasy?",
             "Five drivers and two constructors, within your budget."),
        ],
        "cta": ("/", "Start with free predictions →"),
    },
]

TOOLS = [
    {
        "base": "tools", "crumb": "Tools", "slug": "f1-fantasy-predictions",
        "crumb_self": "Predictions",
        "title": "F1 Fantasy Predictions 2026: Drivers, Constructors & Points | BoxBox",
        "desc": "Free F1 Fantasy 2026 predictions for every race weekend: projected driver points, constructor points, confidence ranges, value ratings, race picks and optimizer tools.",
        "features": ["Driver and constructor projections", "Expected fantasy points", "Confidence ranges", "Value ratings", "Race-week picks"],
        "h1": "F1 Fantasy Predictions 2026",
        "intro": '<p class="lede">Free F1 Fantasy predictions for every 2026 race weekend: driver points, constructor points, confidence ranges, value ratings and race-week picks.</p>',
        "body": (
            "<h2>What you get</h2>"
            "<p>BoxBox publishes current-round projections for every driver and constructor, including expected fantasy points, predicted qualifying and race positions, price/value signals, confidence intervals and risk notes.</p>"
            "<h2>How to use the predictions</h2>"
            "<ul><li>Start with the live driver and constructor cards to see projected points and confidence ranges.</li>"
            "<li>Use the race-pick page for a quick summary of the best picks, best value options and captain/boost candidate.</li>"
            "<li>Feed the projections into the Optimizer, Team Compare or Transfer Planner when you need an actual team decision.</li></ul>"
            "<h2>Why the numbers change during a race weekend</h2>"
            "<p>Before practice, projections lean on form, team strength, circuit profile and historical patterns. After free practice and qualifying, the site refreshes with new weekend evidence, so the order can move as real pace becomes clearer.</p>"
            '<div class="callout">For the full ranked list, open the live <a href="/#drivers">Drivers</a> and <a href="/#constructors">Constructors</a> tabs. For a race-week shortcut, start with the <a href="/picks/">Race Picks</a> hub.</div>'
        ),
        "faqs": [
            ("Where can I find F1 Fantasy predictions for this race?",
             "The live BoxBox homepage shows current-round projections for all drivers and constructors, and the Race Picks hub has a crawlable summary page for each Grand Prix with top picks, value picks and constructor picks."),
            ("Do the predictions update after practice?",
             "Yes. Predictions are refreshed through the race weekend. Pre-practice projections use historical and season signals; after free practice and qualifying, the model can incorporate more current weekend evidence."),
            ("Are the F1 Fantasy predictions free?",
             "Yes. BoxBox predictions, race picks, optimizer tools and transfer tools are free with no login required."),
        ],
        "cta": ("/#drivers", "Open live F1 Fantasy predictions →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "best-f1-fantasy-team",
        "crumb_self": "Best Team",
        "title": "Best F1 Fantasy Team 2026: Free Optimizer & Picks | BoxBox",
        "desc": "Find the best F1 Fantasy team for the current race weekend with free driver and constructor projections, budget checks, chips, value ratings and a lineup optimizer.",
        "features": ["Suggested F1 Fantasy lineup", "Budget check", "Captain boost context", "Driver and constructor projections", "No login required"],
        "h1": "Best F1 Fantasy Team 2026",
        "intro": '<p class="lede">Looking for the best F1 Fantasy team this week? Use current driver and constructor projections, budget checks and chip settings to build a lineup that actually fits.</p>',
        "body": (
            "<h2>What makes a good F1 Fantasy team?</h2>"
            "<p>The best team is not just the seven highest names on the points list. It has to fit your budget, use constructors efficiently, leave enough value for transfers, and put the 2x or 3x boost on the right driver.</p>"
            "<h2>Fast way to build one</h2>"
            "<ul><li>Open the Lineup Optimizer and set your real team budget.</li>"
            "<li>Choose a strategy: Max Points, Balanced, Max Value or Budget Builder.</li>"
            "<li>Lock any drivers or constructors you already know you want, and exclude picks you do not trust.</li>"
            "<li>Run the optimizer, then compare two or three realistic teams in Team Compare before locking in.</li></ul>"
            "<h2>What to check before deadline</h2>"
            "<p>Before the lock deadline, review updated practice or qualifying information, DNF risk, price-change brackets, and whether a chip changes the best lineup. A team that was best pre-practice may not still be best after fresh weekend data arrives.</p>"
            '<div class="callout">For race-specific suggestions, start with the <a href="/picks/">Race Picks</a> page. For the mathematically best legal lineup, use the <a href="/tools/lineup-optimizer/">Lineup Optimizer</a>.</div>'
        ),
        "faqs": [
            ("What is the best F1 Fantasy team this week?",
             "The best team depends on the current race, your budget, chips and any locked picks. BoxBox uses current-round projections to score legal 5-driver, 2-constructor lineups and find the strongest team for your settings."),
            ("Should I use an optimizer for F1 Fantasy?",
             "Yes, especially when budget is tight. A good optimizer checks the full driver and constructor combination space instead of guessing from the top projected scorers."),
            ("How do I compare two F1 Fantasy teams?",
             "Use Team Compare to enter up to three teams and compare expected points, budget, value, confidence range, projected budget gain and worst-case downside."),
        ],
        "cta": ("/#optimizer", "Find your best F1 Fantasy team →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "f1-fantasy-captain-picks",
        "crumb_self": "Captain Picks",
        "title": "F1 Fantasy Captain Picks 2026: 2x & 3x Boost Advice | BoxBox",
        "desc": "Free F1 Fantasy captain and boost pick advice for 2026: compare projected driver points, downside risk, confidence ranges and 3x Boost candidates.",
        "features": ["Captain pick projections", "2x boost context", "3x Boost comparison", "Downside risk", "Confidence ranges"],
        "h1": "F1 Fantasy Captain Picks 2026",
        "intro": '<p class="lede">Pick the right boosted driver for the current F1 Fantasy round by comparing projected points, confidence range and downside risk.</p>',
        "body": (
            "<h2>What makes a good captain pick?</h2>"
            "<p>Your boosted driver should combine high expected points with a strong floor. A driver with a huge ceiling but a wide downside can be worth a punt, but the safest captain is usually the top projected scorer with manageable DNF and volatility risk.</p>"
            "<h2>2x, Autopilot and 3x Boost</h2>"
            "<ul><li><strong>Normal round:</strong> your highest-scoring driver gets the 2x boost.</li>"
            "<li><strong>Autopilot:</strong> the game automatically applies 2x to your best-scoring driver after the round.</li>"
            "<li><strong>3x Boost:</strong> the top driver gets 3x and the second-best driver gets 2x, so your top two driver choices matter.</li></ul>"
            "<h2>How BoxBox helps</h2>"
            "<p>The driver cards show projected points, risk-adjusted points, confidence intervals and DNF risk. Team Compare also shows which driver receives the boost in a full team context, so you can see the real effect on your total score.</p>"
            '<div class="callout">The best captain can change after practice or qualifying. Recheck the live <a href="/#drivers">Drivers</a> tab and the race-specific <a href="/picks/">Picks</a> page before the deadline.</div>'
        ),
        "faqs": [
            ("Who should I captain in F1 Fantasy?",
             "Usually the best captain is the highest projected driver with a strong confidence floor and acceptable DNF risk. BoxBox shows projected points and confidence ranges so you can balance upside and safety."),
            ("How does 3x Boost work in F1 Fantasy?",
             "With 3x Boost, your highest-scoring driver gets triple points and your second-highest driver gets double points. That makes your top two driver choices more important than usual."),
            ("Does Team Compare show the boosted driver?",
             "Yes. Team Compare marks the boosted driver contribution, including 2x, 3x and second-driver 2x behaviour when a chip applies."),
        ],
        "cta": ("/#drivers", "See captain pick projections →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "f1-fantasy-deadline",
        "crumb_self": "Deadline",
        "title": "F1 Fantasy Deadline 2026: Lock Times & Race Calendar | BoxBox",
        "desc": "F1 Fantasy 2026 deadline tracker: see each race lock time, sprint-weekend lock rule, next deadline and the full season deadline table.",
        "features": ["F1 Fantasy lock deadlines", "Next race countdown context", "Sprint-weekend lock rules", "2026 race calendar", "UTC lock times"],
        "h1": "F1 Fantasy Deadline 2026: Lock Times & Race Calendar",
        "intro": '<p class="lede">Do not miss team lock. Check the next F1 Fantasy deadline and every 2026 race-week lock time in one place.</p>',
        "body": (
            "<h2>When does F1 Fantasy lock?</h2>"
            "<p>On a normal race weekend, F1 Fantasy locks at the start of qualifying. On the 2026 sprint weekends listed here, the lock is the sprint race start, so always check the specific race row before making transfers or playing chips.</p>"
            "<h2>How to use the deadline table</h2>"
            "<p>Use the UTC table below as the crawlable season reference, then open the live site header for a local-time countdown. Make transfers, compare teams, and set chips before the listed lock time.</p>"
            "<h2>What to check before lock</h2>"
            "<ul><li>Review the latest prediction phase: pre-practice, post-practice or post-qualifying.</li>"
            "<li>Check weather, DNF risk, price-change watchlists and confidence ranges.</li>"
            "<li>Use Team Compare or the Optimizer for the final team choice before the deadline.</li></ul>"
        ),
        "faqs": [
            ("When is the next F1 Fantasy deadline?",
             "The table on this page shows the next upcoming F1 Fantasy lock deadline and the full 2026 race calendar. Times are listed in UTC, and the live BoxBox site header shows a local countdown."),
            ("Does F1 Fantasy lock before qualifying?",
             "On normal weekends, the team lock is at qualifying. On the 2026 sprint weekends listed here, the deadline is the sprint race start, so check the specific race row before making transfers."),
            ("What should I do before the F1 Fantasy deadline?",
             "Before lock, check updated projections, confidence ranges, DNF risk, weather, price-change signals and chip settings. Then compare your final team options in the Optimizer or Team Compare."),
        ],
        "cta": ("/", "Open live deadline countdown ->"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "f1-fantasy-value-picks",
        "crumb_self": "Value Picks",
        "title": "F1 Fantasy Value Picks 2026: Best Budget Picks This Week | BoxBox",
        "desc": "Free F1 Fantasy value picks for the current race weekend: best points-per-million drivers, budget picks and constructor value based on live projections.",
        "features": ["Points-per-million rankings", "Budget driver picks", "Constructor value picks", "Projected price movement", "Current-round projections"],
        "h1": "F1 Fantasy Value Picks This Week",
        "intro": '<p class="lede">Find the best F1 Fantasy value picks for the current race weekend: drivers and constructors with the strongest projected points per million.</p>',
        "body": (
            "<h2>How to use value picks</h2>"
            "<p>Value picks are not always the highest raw scorers. They are the drivers and constructors whose projected points are strongest relative to price, which helps you fit premium picks elsewhere without wasting budget.</p>"
            "<h2>What PPM means</h2>"
            "<p>PPM means points per million: expected fantasy points divided by price. A higher PPM means a pick is doing more work for each dollar of budget.</p>"
            "<h2>When value matters most</h2>"
            "<p>Value matters most when you are trying to squeeze in a premium captain, when your budget is tight, or when you want picks that may appreciate in price after the round.</p>"
            '<div class="callout">For a full team built around value, open the <a href="/#optimizer">Optimizer</a> and choose the Max Value or Budget Builder strategy.</div>'
        ),
        "faqs": [
            ("Who are the best F1 Fantasy value picks this week?",
             "The best value picks are the current drivers and constructors with the strongest projected points per million. BoxBox lists them in the tables on this page and refreshes them when the prediction pipeline updates."),
            ("What does PPM mean in F1 Fantasy?",
             "PPM means points per million: expected fantasy points divided by current fantasy price. It is a quick way to compare value across cheap and expensive picks."),
            ("Should I pick the highest PPM drivers or the highest projected points?",
             "Use both. High projected points win the week, but high PPM picks make the budget work. The best lineups usually combine premium upside with two or three strong-value picks."),
        ],
        "cta": ("/#drivers", "Open live value rankings ->"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "f1-fantasy-price-changes",
        "crumb_self": "Price Changes",
        "title": "F1 Fantasy Price Changes 2026: Rise & Fall Watchlist | BoxBox",
        "desc": "Free F1 Fantasy price-change watchlist for 2026: see drivers and constructors under price-rise or price-drop pressure based on current projections and value signals.",
        "features": ["Price-change watchlist", "Likely risers", "Drop-pressure picks", "Driver and constructor value signals", "Current-round projections"],
        "h1": "F1 Fantasy Price Changes: Rise & Fall Watchlist",
        "intro": '<p class="lede">Track which F1 Fantasy drivers and constructors look underpriced, overpriced or under pressure before prices move.</p>',
        "body": (
            "<h2>How to read the watchlist</h2>"
            "<p>F1 Fantasy prices usually reward picks that score well relative to their price and punish picks that underperform their cost. BoxBox turns the current projections into a simple watchlist: strong value picks sit on the rise side, while low-value or poor-scoring picks sit on the pressure side.</p>"
            "<h2>Why price changes matter</h2>"
            "<p>Budget growth compounds. Catching a few early risers can leave you with enough extra team value to afford stronger premium drivers or constructors later in the season. Avoiding likely fallers protects the spending power you already have.</p>"
            "<h2>Use it with transfers</h2>"
            "<p>Do not chase price rises blindly. A budget pick still needs to fit your score plan, transfer plan and chip timing. Use the watchlist alongside the Optimizer, Team Compare and Transfer Planner before making a move.</p>"
            '<div class="callout">For the underlying projection details, open the live driver and constructor cards. For budget-first teams, use the <a href="/tools/budget-builder/">Budget Builder</a>.</div>'
        ),
        "faqs": [
            ("Who is likely to rise in price in F1 Fantasy?",
             "The best rise candidates are usually drivers and constructors with strong projected points relative to current price. The BoxBox watchlist ranks current picks by value signals and expected points to highlight likely price-rise interest."),
            ("Who is likely to fall in price in F1 Fantasy?",
             "Drop-pressure candidates are picks with weak projected points relative to current price. They may still be useful in a specific team, but they carry more budget-risk than strong value picks."),
            ("Should I transfer only for price changes?",
             "No. Price movement matters, but the best transfer also needs to improve points, fit your budget and avoid unnecessary transfer penalties. Use price-change signals as one input, not the whole decision."),
        ],
        "cta": ("/#drivers", "Open live price-change cards ->"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "lineup-optimizer",
        "crumb_self": "Lineup Optimizer",
        "title": "F1 Fantasy Lineup Optimizer (Free) | BoxBox",
        "desc": "A free F1 Fantasy lineup optimizer that checks all 1.4 million legal 5-driver, 2-constructor teams within your budget and ranks the best lineups using ML predictions.",
        "features": ["Lineup optimization", "Budget-constrained team search", "Lock and exclude picks", "Chip-aware scoring", "Strategy modes"],
        "h1": "F1 Fantasy Lineup Optimizer (Free)",
        "intro": '<p class="lede">Find the best F1 Fantasy team within your budget in about a second &mdash; free, no login.</p>',
        "body": (
            "<h2>What it does</h2>"
            "<p>The optimizer brute-forces all <strong>1.4 million</strong> legal combinations of 5 drivers and 2 constructors that fit your budget, scores each with our machine-learning predictions, and ranks the best lineups.</p>"
            "<h2>How to use it</h2>"
            "<ul><li>Set your budget and pick a strategy: Max Points, Max Value, Budget Builder or Balanced.</li>"
            "<li>Left-click any driver or constructor to <strong>lock</strong> them in; right-click to <strong>exclude</strong> them.</li>"
            "<li>Select a chip (3x Boost, Limitless, etc.) and the optimizer builds the team that makes the most of it.</li></ul>"
            '<div class="callout">Already have a team? Use the built-in <strong>Transfer Advisor</strong> to find your best one or two swaps, or the <strong>Multi-Week Planner</strong> to plan several rounds ahead.</div>'
        ),
        "faqs": [
            ("Is there a free F1 Fantasy optimizer?",
             "Yes. The BoxBox Lineup Optimizer is completely free with no login. It checks every legal 5-driver, 2-constructor lineup within your budget and ranks the best teams using machine-learning predictions."),
            ("How does the F1 Fantasy optimizer work?",
             "It evaluates all 1.4 million legal team combinations within your budget, scores each using predicted fantasy points (including chip effects), and returns the highest-scoring lineups. You can lock or exclude picks to steer it."),
        ],
        "cta": ("/#optimizer", "Open the Lineup Optimizer →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "team-compare",
        "crumb_self": "Team Compare",
        "title": "F1 Fantasy Team Compare & Score Calculator (Free) | BoxBox",
        "desc": "Free F1 Fantasy team compare tool: enter up to three candidate teams and compare budget, projected points, confidence range, price movement and downside risk.",
        "features": ["Compare up to three teams", "Projected team score", "Budget remaining", "Worst-case downside", "Pick-level contribution"],
        "h1": "F1 Fantasy Team Compare & Score Calculator",
        "intro": '<p class="lede">Compare up to three possible F1 Fantasy teams side-by-side before you lock in transfers or chips.</p>',
        "body": (
            "<h2>What it compares</h2>"
            "<p>Team Compare lets you enter full 5-driver, 2-constructor lineups and see how they stack up on expected points, total cost, budget left, projected budget gain, points-per-million, confidence range and worst-case downside.</p>"
            "<h2>Why it helps</h2>"
            "<p>The best-looking team is not always the best fantasy team. A lineup with slightly fewer headline points might have a stronger budget path, a safer floor, or better value for future transfers. Team Compare puts those trade-offs in one view.</p>"
            "<h2>How to use it</h2>"
            "<ul><li>Enter Team A, Team B and Team C, or copy your current Transfer Advisor team with <strong>Use Current</strong>.</li>"
            "<li>Watch the live budget tracker while you add drivers and constructors.</li>"
            "<li>Pick a points basis and chip, then compare team totals and per-pick contributions.</li></ul>"
            '<div class="callout">Use it after the Optimizer if you have two or three realistic teams and want to understand the trade-off before making the final call.</div>'
        ),
        "faqs": [
            ("Can I compare F1 Fantasy teams before choosing one?",
             "Yes. BoxBox Team Compare lets you enter up to three full F1 Fantasy teams and compare projected score, budget, value, confidence range, price movement and downside risk side-by-side."),
            ("Does Team Compare include the captain boost?",
             "Yes. The comparison automatically applies the normal 2x boost to the highest-scoring driver by the selected points basis. With the 3x Boost chip, the top driver gets 3x and the second driver gets 2x."),
        ],
        "cta": ("/#optimizer", "Open Team Compare →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "transfer-planner",
        "crumb_self": "Transfer Planner",
        "title": "F1 Fantasy Transfer Planner & Advisor (Free) | BoxBox",
        "desc": "Free F1 Fantasy transfer tools: find your best one or two swaps this week, or plan transfers and chips across 2-5 upcoming rounds with a multi-week planner.",
        "features": ["Transfer advisor", "Multi-week transfer planning", "Chip planning", "Budget propagation", "Transfer penalty comparison"],
        "h1": "F1 Fantasy Transfer Planner & Advisor",
        "intro": '<p class="lede">Make the right transfers &mdash; this week and several rounds ahead &mdash; without the &minus;10 guesswork.</p>',
        "body": (
            "<h2>Transfer Advisor</h2>"
            "<p>Enter your current team, budget and free transfers, and it finds your best one or two swaps. Each suggestion shows the points gained, the cash impact, and whether an extra &minus;10 transfer is actually worth it versus holding.</p>"
            "<h2>Multi-Week Planner</h2>"
            "<p>Plan transfers across 2&ndash;5 upcoming rounds at once. It projects future scores from track similarity and ML, propagates your budget forward, schedules chips, and can even chase a specific target team.</p>"
            '<div class="callout">Both respect picks you <strong>lock</strong> or <strong>exclude</strong>, so you can protect your keepers while optimising the rest.</div>'
        ),
        "faqs": [
            ("Should I take a hit for an extra F1 Fantasy transfer?",
             "Only if the extra pick is projected to gain more than the 10-point penalty versus holding. The BoxBox Transfer Advisor shows the net gain after the penalty for every option, so you can see at a glance whether a hit is worth it."),
            ("Can I plan F1 Fantasy transfers several weeks ahead?",
             "Yes. The Multi-Week Planner plans transfers and chip usage across 2-5 upcoming rounds, projecting future scores and carrying your budget forward so you don't trade away a pick that's ideal for the next few tracks."),
        ],
        "cta": ("/#optimizer", "Open the Transfer tools →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "budget-builder",
        "crumb_self": "Budget Builder",
        "title": "F1 Fantasy Budget Builder: Grow Your Team Value (Free) | BoxBox",
        "desc": "Free F1 Fantasy budget builder: find the picks most likely to rise in price so your team value compounds, leaving more to spend on stars later in the season.",
        "features": ["Budget growth strategy", "Projected price movement", "Value picks", "Points-per-million signals", "Team value planning"],
        "h1": "F1 Fantasy Budget Builder",
        "intro": '<p class="lede">Turn price rises into spending power. The Budget Builder finds picks likely to appreciate so your team value grows over the season.</p>',
        "body": (
            "<h2>Why budget matters</h2>"
            "<p>F1 Fantasy prices move based on how a pick performs relative to its cost. Catching price rises early &mdash; especially in the first 6&ndash;8 rounds &mdash; compounds into extra budget you can later spend on elite drivers.</p>"
            "<h2>How to use it</h2>"
            "<p>In the Optimizer, choose the <strong>Budget Builder</strong> strategy. It favours strong points-per-million picks that our model expects to rise in price, balancing this-week points with asset growth. The Season tab's price trackers show who's trending up or down.</p>"
            '<div class="callout">Tip: sometimes holding a fading pick one more round lets you sell just before a price drop &mdash; the price-change brackets on each card show when you\'re near a threshold.</div>'
        ),
        "faqs": [
            ("How do F1 Fantasy prices change?",
             "Prices rise or fall after each race based on a pick's points relative to its price (roughly a points-per-million rating). Strong value picks go up; underperformers drop. Catching rises early compounds into more budget."),
            ("What is the best F1 Fantasy budget strategy?",
             "Early in the season, prioritise picks likely to appreciate so your team value grows, then convert that extra budget into premium drivers later. The BoxBox Budget Builder strategy surfaces exactly those picks."),
        ],
        "cta": ("/#optimizer", "Open the Budget Builder →"),
    },
    {
        "base": "tools", "crumb": "Tools", "slug": "points-calculator",
        "crumb_self": "Points Calculator",
        "title": "F1 Fantasy Points Calculator & Predictions (Free) | BoxBox",
        "desc": "Free F1 Fantasy points calculator: see projected fantasy points for every driver and constructor this round, with a full breakdown of qualifying, race, overtakes and bonuses.",
        "features": ["Projected fantasy points", "Driver point breakdowns", "Constructor point breakdowns", "Confidence intervals", "What-if sliders"],
        "h1": "F1 Fantasy Points Calculator & Predictions",
        "intro": '<p class="lede">See how many fantasy points every driver and constructor is projected to score this round &mdash; with the full breakdown.</p>',
        "body": (
            "<h2>How the points are calculated</h2>"
            "<p>Machine-learning models predict each driver's qualifying and race position, then a 10,000-run Monte Carlo simulation turns those into <strong>expected fantasy points</strong> using the official scoring rules &mdash; qualifying, race, positions gained, overtakes, fastest lap, Driver of the Day and DNF risk, plus constructor pit stops and the qualifying bonus.</p>"
            "<h2>What you get</h2>"
            "<ul><li>Projected points for all 22 drivers and 11 constructors, sortable by points or value (PPM).</li>"
            "<li>A full per-pick breakdown so you can see where the points come from.</li>"
            "<li>A 90% confidence interval on every pick, so you know how safe or volatile it is.</li></ul>"
            '<div class="callout">Want to test a hunch? Each card has a &plusmn; slider to bump a pick\'s pace and instantly recalculate its points.</div>'
        ),
        "faqs": [
            ("Is there an F1 Fantasy points calculator?",
             "Yes. BoxBox projects expected fantasy points for every driver and constructor each round, calculated from machine-learning position predictions and a 10,000-run race simulation scored with the official rules, with a full breakdown per pick. It's free."),
            ("How accurate are the projected points?",
             "We publish our track record on the Accuracy tab, including the misses: prediction error and confidence-interval coverage for every completed round. Projections sharpen as practice and qualifying data arrive across the weekend."),
        ],
        "cta": ("/#drivers", "See projected points →"),
    },
]

STATIC_PAGES = [
    {
        "slug": "about",
        "crumb_self": "About",
        "title": "About BoxBoxF1Fantasy | Free F1 Fantasy Predictions & Tools",
        "desc": "About BoxBoxF1Fantasy: a free, independent F1 Fantasy prediction site with driver and constructor projections, optimizer tools, race picks, accuracy tracking and contact details.",
        "h1": "About BoxBoxF1Fantasy",
        "schema_type": "AboutPage",
        "intro": '<p class="lede">BoxBoxF1Fantasy is a free, independent F1 Fantasy prediction site built to help players make better driver, constructor, transfer and chip decisions.</p>',
        "body": (
            "<h2>What the site does</h2>"
            "<p>BoxBox publishes current-round F1 Fantasy projections for every driver and constructor, race-week pick summaries, a lineup optimizer, Team Compare, transfer tools, budget/value signals, and an accuracy record for completed rounds.</p>"
            "<h2>How to use it</h2>"
            "<p>Start with the live predictions, then use the Optimizer or Team Compare when you need to turn those projections into an actual team. The race-pick pages give a quicker written summary for each Grand Prix, while the guides explain scoring, chips and strategy.</p>"
            "<h2>Transparency</h2>"
            "<p>The site is open about uncertainty. Driver cards and comparison tools show confidence ranges, risk notes and downside signals because F1 Fantasy depends on weather, safety cars, reliability, strategy and race incidents. The Accuracy tab keeps a public record of how predictions performed after completed rounds.</p>"
            "<h2>Independence</h2>"
            "<p>BoxBoxF1Fantasy is an independent fan-built site. It is not affiliated with, endorsed by, or connected to Formula 1, the FIA, F1 Fantasy, any F1 team, or any driver.</p>"
            "<h2>Contact</h2>"
            f'<p>Questions, corrections, bugs or partnership enquiries: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p>'
            '<div class="callout">For the live tools, go to <a href="/">Predictions &amp; Tools</a>. For crawlable race-week summaries, start at <a href="/picks/">Race Picks</a>.</div>'
        ),
    },
    {
        "slug": "privacy",
        "crumb_self": "Privacy",
        "title": "Privacy Policy | BoxBoxF1Fantasy",
        "desc": "Privacy policy for BoxBoxF1Fantasy, covering analytics, cookies, local browser storage, advertising, external links and contact information.",
        "h1": "Privacy Policy",
        "schema_type": "WebPage",
        "intro": '<p class="lede">This privacy policy explains what BoxBoxF1Fantasy collects and how the site uses it.</p>',
        "body": (
            f"<p><strong>Last updated:</strong> {datetime.now(timezone.utc).date().isoformat()}</p>"
            "<h2>Information we collect</h2>"
            "<p>BoxBoxF1Fantasy does not require an account and does not ask visitors to create a profile. If you email us, we receive the email address and any information you choose to include in the message.</p>"
            "<h2>Analytics</h2>"
            "<p>The site uses Google Analytics to understand aggregate traffic, page usage and engagement. Analytics data may include device/browser information, approximate location, referrer, pages viewed and interaction events. This helps improve the site and understand which pages are useful.</p>"
            "<h2>Cookies and local storage</h2>"
            "<p>Google Analytics may use cookies or similar technologies. The site may also use browser local storage for convenience features such as saved scenario settings or team inputs. These are stored in your browser and are used to make the tools work better for you.</p>"
            "<h2>Advertising</h2>"
            "<p>The site may add advertising in the future. If ads are added, ad partners may use cookies or similar technologies to measure performance, prevent fraud and personalize or limit ads according to their own policies and your browser settings.</p>"
            "<h2>External links</h2>"
            "<p>BoxBoxF1Fantasy links to third-party sites such as social platforms, YouTube, Ko-fi, PayPal and data sources. Those sites have their own privacy policies and practices.</p>"
            "<h2>Data sharing</h2>"
            "<p>We do not sell personal information. Aggregated analytics and operational information may be processed by service providers used to host, measure and maintain the site.</p>"
            "<h2>Contact</h2>"
            f'<p>For privacy questions, email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p>'
        ),
    },
]


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    season = load_json(DATA / "season_summary.json")
    current = load_json(DATA / "predictions.json")
    horizon = load_json(DATA / "horizon_projections.json") or {"rounds": {}}
    track_data = load_json(DATA / "track_data.json") or {}
    changelog = load_json(DATA / "changelog.json") or {"entries": []}
    videos_data = load_json(DATA / "youtube_videos.json") or {"videos": []}
    articles_data = load_json(DATA / "articles.json") or {"articles": []}
    if not season or not current:
        print("[14_build_seo_pages] missing season_summary.json or predictions.json - run export first.")
        return

    write_prediction_schema()
    write_ai_summary(current, season)

    current_round = current.get("round")
    horizon_rounds = horizon.get("rounds") or {}
    drivers_seed = {
        d.get("driver_id"): d
        for d in (load_seed_json("drivers.json") or {}).get("drivers", [])
        if d.get("driver_id")
    }
    constructors_seed = {
        c.get("constructor_id"): c
        for c in (load_seed_json("constructors.json") or {}).get("constructors", [])
        if c.get("constructor_id")
    }
    prices = load_seed_json("fantasy_prices.json") or {}
    PICKS.mkdir(parents=True, exist_ok=True)

    entries = []   # for the hub + sitemap
    written = 0
    future_written = 0
    calendar_written = 0
    for r in season.get("rounds", []):
        rn = r["round"]
        if r.get("cancelled"):
            continue
        status = "archive"
        if r.get("has_predictions"):
            is_current = (rn == current_round)
            status = "current" if is_current else "archive"
            pred = current if is_current else load_json(DATA / f"predictions_round{rn}.json")
            if not pred or not pred.get("drivers"):
                print(f"  - round {rn}: no usable predictions, skipped")
                continue
            slug, page = render_race_page(pred, is_current)
            race_name = pred.get("race", r["name"])
            race_date = pred.get("date", r.get("date", ""))
            written += 1
        elif str(rn) in horizon_rounds:
            status = "future"
            pred = hydrate_horizon_round(r, horizon_rounds[str(rn)], drivers_seed, constructors_seed, prices)
            if not pred.get("drivers"):
                print(f"  - round {rn}: no usable horizon projections, skipped")
                continue
            slug, page = render_future_race_page(pred, horizon.get("generated_at", ""))
            race_name = pred.get("race", r["name"])
            race_date = pred.get("date", r.get("date", ""))
            future_written += 1
        elif rn > current_round:
            status = "calendar"
            slug, page = render_calendar_race_page(r, track_data)
            race_name = r["name"]
            race_date = r.get("date", "")
            calendar_written += 1
        else:
            continue

        out_dir = PICKS / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(page, encoding="utf-8")
        entries.append((slug, race_name, race_date, rn, status))
        suffix = ", current" if status == "current" else ", early outlook" if status == "future" else ""
        print(f"  [OK] /picks/{slug}/  (round {rn}{suffix})")

    # newest race first in the hub
    entries.sort(key=lambda e: e[3], reverse=True)
    (PICKS / "index.html").write_text(render_index(entries), encoding="utf-8")

    # all sitemap URLs (relative): home + picks + drivers + constructors + guides + tools
    rel_paths = ["", "picks/"] + [f"picks/{e[0]}/" for e in entries]
    now = datetime.now(timezone.utc)
    feed_items = [
        {
            "title": f"F1 Fantasy Picks: {short_race(name)} {YEAR}",
            "url": f"{SITE}/picks/{slug}/",
            "summary": (
                f"Early horizon F1 Fantasy outlook, transfer-planning notes and projected picks for {name}."
                if status == "future" else
                f"Early F1 Fantasy calendar watchlist, circuit traits and strategy notes for {name}."
                if status == "calendar" else
                f"Race-week F1 Fantasy picks, projected points, value picks and constructor choices for {name}."
            ),
            "updated": now,
        }
        for slug, name, date, rn, status in entries[:8]
    ]

    # --- current driver + constructor projection pages ---
    drivers_sorted = sorted(current.get("drivers", []), key=lambda d: d.get("expected_points", 0), reverse=True)
    constructors_sorted = sorted(current.get("constructors", []), key=lambda c: c.get("expected_points", 0), reverse=True)
    constructors_by_id = {c["constructor_id"]: c for c in current.get("constructors", [])}
    drivers_by_id = {d["driver_id"]: d for d in current.get("drivers", [])}

    drivers_dir = WEB / "drivers"
    drivers_dir.mkdir(parents=True, exist_ok=True)
    (drivers_dir / "index.html").write_text(render_drivers_hub(current), encoding="utf-8")
    rel_paths.append("drivers/")
    feed_items.append({
        "title": f"F1 Fantasy Driver Predictions {YEAR}",
        "url": f"{SITE}/drivers/",
        "summary": f"Current F1 Fantasy driver projections for {current.get('race', 'the current race')}: expected points, price, value and predicted finishing position.",
        "updated": now,
    })
    for rank, driver in enumerate(drivers_sorted, 1):
        slug = plain_slug(driver.get("name", driver.get("driver_id", "driver")))
        out_dir = drivers_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_driver_page(driver, current, rank, constructors_by_id), encoding="utf-8")
        rel_paths.append(f"drivers/{slug}/")
        feed_items.append({
            "title": f"{driver.get('name', driver.get('driver_id', 'Driver'))} F1 Fantasy {YEAR}",
            "url": f"{SITE}/drivers/{slug}/",
            "summary": f"Current F1 Fantasy projection for {driver.get('name', driver.get('driver_id', 'this driver'))}: {driver.get('expected_points', 0):.1f} expected points, ${driver.get('current_price', 0):.1f}M price and {driver.get('value_score', 0):.2f} PPM.",
            "updated": now,
        })

    constructors_dir = WEB / "constructors"
    constructors_dir.mkdir(parents=True, exist_ok=True)
    (constructors_dir / "index.html").write_text(render_constructors_hub(current), encoding="utf-8")
    rel_paths.append("constructors/")
    feed_items.append({
        "title": f"F1 Fantasy Constructor Predictions {YEAR}",
        "url": f"{SITE}/constructors/",
        "summary": f"Current F1 Fantasy constructor projections for {current.get('race', 'the current race')}: expected points, price, value, pit-stop points and risk.",
        "updated": now,
    })
    for rank, constructor in enumerate(constructors_sorted, 1):
        slug = plain_slug(constructor.get("name", constructor.get("constructor_id", "constructor")))
        out_dir = constructors_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_constructor_page(constructor, current, rank, drivers_by_id), encoding="utf-8")
        rel_paths.append(f"constructors/{slug}/")
        feed_items.append({
            "title": f"{constructor.get('name', constructor.get('constructor_id', 'Constructor'))} F1 Fantasy Constructor {YEAR}",
            "url": f"{SITE}/constructors/{slug}/",
            "summary": f"Current F1 Fantasy constructor projection for {constructor.get('name', constructor.get('constructor_id', 'this constructor'))}: {constructor.get('expected_points', 0):.1f} expected points, ${constructor.get('current_price', 0):.1f}M price and {constructor.get('value_score', 0):.2f} PPM.",
            "updated": now,
        })

    # --- static content: guides + tools + their hubs ---
    for base, crumb, items, hub in (
        ("guides", "Guides", GUIDES, GUIDES_HUB),
        ("tools", "Tools", TOOLS, TOOLS_HUB),
    ):
        out_base = WEB / base
        out_base.mkdir(parents=True, exist_ok=True)
        for it in items:
            d = out_base / it["slug"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(render_content_page(it, current), encoding="utf-8")
        (out_base / "index.html").write_text(render_list_hub(base, crumb, hub, items), encoding="utf-8")
        rel_paths.append(f"{base}/")
        rel_paths += [f"{base}/{it['slug']}/" for it in items]
        feed_items.append({
            "title": hub["h1"],
            "url": f"{SITE}/{base}/",
            "summary": hub["desc"],
            "updated": now,
        })
        for it in items:
            feed_items.append({
                "title": it["h1"],
                "url": f"{SITE}/{base}/{it['slug']}/",
                "summary": it["desc"],
                "updated": now,
            })

    # --- public accuracy / trust page ---
    accuracy_summary = build_accuracy_summary(season)
    accuracy_dir = WEB / "accuracy"
    accuracy_dir.mkdir(parents=True, exist_ok=True)
    (accuracy_dir / "index.html").write_text(render_accuracy_page(accuracy_summary), encoding="utf-8")
    rel_paths.append("accuracy/")
    feed_items.append({
        "title": f"F1 Fantasy Prediction Accuracy {YEAR}",
        "url": f"{SITE}/accuracy/",
        "summary": f"Public BoxBoxF1Fantasy track record across {len(accuracy_summary['rounds'])} completed rounds: driver points MAE {accuracy_summary['driver_mae']:.1f}, constructor points MAE {accuracy_summary['constructor_mae']:.1f}, and 90% CI coverage {accuracy_summary['ci_coverage']:.0f}%.",
        "updated": now,
    })

    # --- crawlable changelog / freshness page ---
    changelog_dir = WEB / "changelog"
    changelog_dir.mkdir(parents=True, exist_ok=True)
    (changelog_dir / "index.html").write_text(render_changelog_page(changelog), encoding="utf-8")
    rel_paths.append("changelog/")
    changelog_entries = sorted(changelog.get("entries", []), key=lambda e: e.get("date", ""), reverse=True)
    latest_change = changelog_entries[0] if changelog_entries else {}
    feed_items.append({
        "title": f"BoxBoxF1Fantasy Changelog {YEAR}",
        "url": f"{SITE}/changelog/",
        "summary": "Public release notes for BoxBoxF1Fantasy model updates, scoring fixes, data-quality improvements and feature releases."
                   + (f" Latest: {clean_legacy_text(latest_change.get('title', 'site update'))}." if latest_change else ""),
        "updated": now,
    })

    # --- crawlable videos page ---
    videos_dir = WEB / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    (videos_dir / "index.html").write_text(render_videos_page(videos_data), encoding="utf-8")
    rel_paths.append("videos/")
    latest_video = sorted(videos_data.get("videos", []), key=lambda v: v.get("published", ""), reverse=True)
    latest_video = latest_video[0] if latest_video else {}
    feed_items.append({
        "title": f"F1 Fantasy Videos {YEAR}",
        "url": f"{SITE}/videos/",
        "summary": "Latest BoxBoxF1Fantasy YouTube videos for F1 Fantasy race-week drafts, deadline strategy, top picks and data-backed team decisions."
                   + (f" Latest: {clean_legacy_text(latest_video.get('title', 'new video'))}." if latest_video else ""),
        "updated": now,
    })

    # --- crawlable articles hub + article pages ---
    articles_dir = WEB / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    articles_sorted = sorted(articles_data.get("articles", []), key=lambda a: a.get("date", ""), reverse=True)
    (articles_dir / "index.html").write_text(render_articles_hub(articles_data), encoding="utf-8")
    rel_paths.append("articles/")
    feed_items.append({
        "title": f"F1 Fantasy Articles {YEAR}",
        "url": f"{SITE}/articles/",
        "summary": "Race previews, recaps, F1 Fantasy strategy notes and longer-form BoxBoxF1Fantasy analysis.",
        "updated": now,
    })
    for article in articles_sorted:
        slug = plain_slug(article.get("slug") or article.get("title") or "article")
        out_dir = articles_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_article_page(article), encoding="utf-8")
        rel_paths.append(f"articles/{slug}/")
        feed_items.append({
            "title": clean_legacy_text(article.get("title", "F1 Fantasy Article")),
            "url": f"{SITE}/articles/{slug}/",
            "summary": _article_summary(article),
            "updated": now,
        })

    # --- public data/API index for agents and power users ---
    (DATA / "index.html").write_text(render_data_page(current, season), encoding="utf-8")
    rel_paths.append("data/")
    feed_items.append({
        "title": f"BoxBoxF1Fantasy Public Data {YEAR}",
        "url": f"{SITE}/data/",
        "summary": "Public JSON endpoint index for BoxBoxF1Fantasy predictions, season summary, driver history, track data, weather, articles, videos and changelog.",
        "updated": now,
    })

    # --- static trust/compliance pages ---
    for page in STATIC_PAGES:
        out_dir = WEB / page["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_static_page(page), encoding="utf-8")
        rel_paths.append(f"{page['slug']}/")
        feed_items.append({
            "title": page["h1"],
            "url": f"{SITE}/{page['slug']}/",
            "summary": page["desc"],
            "updated": now,
        })

    write_sitemap(rel_paths)
    write_robots()
    write_webmanifest()
    write_trust_files()
    write_indexnow_key()
    write_search_index(rel_paths, current)
    write_openapi()
    write_llms_txt(rel_paths)
    write_llms_full(rel_paths, current, feed_items)
    write_well_known()
    write_feeds(feed_items)

    print(f"[14_build_seo_pages] wrote {written} prediction race page(s) + {future_written} future outlook page(s) + {calendar_written} calendar watchlist page(s) + {len(drivers_sorted)} driver page(s) "
          f"+ {len(constructors_sorted)} constructor page(s) + {len(GUIDES)} guide(s) "
          f"+ {len(TOOLS)} tool page(s) + {len(articles_sorted)} article page(s) + {len(STATIC_PAGES)} static page(s) + accuracy page + changelog page + videos page + data page + 6 hubs "
          f"+ sitemap.xml ({len(rel_paths)} URLs) "
          "+ robots.txt + site.webmanifest + humans.txt + security.txt + IndexNow key + predictions.schema.json + search-index.json + openapi.json + .well-known discovery + llms.txt + llms-full.txt + feeds")


if __name__ == "__main__":
    main()
