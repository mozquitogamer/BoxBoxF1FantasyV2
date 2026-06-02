"""14_build_seo_pages.py - generate static, crawlable per-race SEO landing pages.

The website is a single-page app, so Google only ever sees one URL with mostly
JS-rendered content. This script adds real, crawlable HTML *alongside* the app:
one content-rich page per race that has predictions (e.g. /picks/monaco-gp-2026/),
plus an index hub at /picks/, then refreshes sitemap.xml.

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
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "public"
DATA = WEB / "data"
PICKS = WEB / "picks"
SITE = "https://boxboxf1fantasy.com"
YEAR = 2026

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


def load_json(path: Path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def ld_block(objs: list) -> str:
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(objs, ensure_ascii=False, indent=1)
        + "\n</script>"
    )


def page_head(title: str, desc: str, canonical: str, extra_ld: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#0a0d12">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BoxBoxF1Fantasy">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@BoxBoxF1Fantasy">
<meta name="twitter:image" content="{SITE}/og-image.png">
<link rel="icon" type="image/png" href="/favicon.png">
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

    ld = ld_block([
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
    ])

    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/picks/">Picks</a> &rsaquo; {esc(short)} {YEAR}</p>'
        f"<h1>F1 Fantasy Picks: {esc(race)} {YEAR}</h1>"
        + intro
        + cap_line
        + cta
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


# --------------------------------------------------------------------------- #
# index hub
# --------------------------------------------------------------------------- #
def render_index(entries: list) -> str:
    """entries: list of (slug, race_name, date, round, is_current)."""
    canonical = f"{SITE}/picks/"
    title = f"F1 Fantasy Picks by Race - {YEAR} Season | BoxBox"
    desc = (f"Free F1 Fantasy picks, tips and predictions for every {YEAR} Grand Prix - "
            f"top drivers, best value picks and constructors for each race.")

    items = []
    for slug, name, date, rn, is_current in entries:
        tag = '<span class="tag">This week</span>' if is_current else ""
        items.append(
            f'<li><span><a href="/picks/{slug}/">{esc(short_race(name))} {YEAR}</a>{tag}</span>'
            f'<span class="date">{esc(date)}</span></li>'
        )

    ld = ld_block([{
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "F1 Fantasy Picks", "item": canonical},
        ],
    }])

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
# sitemap
# --------------------------------------------------------------------------- #
def write_sitemap(slugs: list[str]) -> None:
    urls = [f"{SITE}/", f"{SITE}/picks/"] + [f"{SITE}/picks/{s}/" for s in slugs]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        pr = "1.0" if u == f"{SITE}/" else "0.8"
        lines.append(f"  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>{pr}</priority></url>")
    lines.append("</urlset>\n")
    (WEB / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    season = load_json(DATA / "season_summary.json")
    current = load_json(DATA / "predictions.json")
    if not season or not current:
        print("[14_build_seo_pages] missing season_summary.json or predictions.json - run export first.")
        return

    current_round = current.get("round")
    PICKS.mkdir(parents=True, exist_ok=True)

    entries = []   # for the hub + sitemap
    written = 0
    for r in season.get("rounds", []):
        if not r.get("has_predictions"):
            continue
        rn = r["round"]
        is_current = (rn == current_round)
        pred = current if is_current else load_json(DATA / f"predictions_round{rn}.json")
        if not pred or not pred.get("drivers"):
            print(f"  - round {rn}: no usable predictions, skipped")
            continue

        slug, page = render_race_page(pred, is_current)
        out_dir = PICKS / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(page, encoding="utf-8")
        entries.append((slug, pred.get("race", r["name"]), pred.get("date", r.get("date", "")), rn, is_current))
        written += 1
        print(f"  [OK] /picks/{slug}/  (round {rn}{', current' if is_current else ''})")

    # newest race first in the hub
    entries.sort(key=lambda e: e[3], reverse=True)
    (PICKS / "index.html").write_text(render_index(entries), encoding="utf-8")
    write_sitemap([e[0] for e in entries])

    print(f"[14_build_seo_pages] wrote {written} race page(s) + /picks/ hub + sitemap.xml")


if __name__ == "__main__":
    main()
