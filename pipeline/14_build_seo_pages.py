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
from datetime import datetime, timezone
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
<p class="footnav"><a href="/">Predictions &amp; Tools</a> &middot; <a href="/picks/">Race Picks</a> &middot; <a href="/guides/">Guides</a> &middot; <a href="/tools/">Tools</a></p>
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
    body = f"""User-agent: *
Allow: /
Allow: /picks/
Allow: /guides/
Allow: /tools/
Allow: /data/predictions.json
Allow: /data/season_summary.json
Allow: /llms.txt

Sitemap: {SITE}/sitemap.xml
"""
    (WEB / "robots.txt").write_text(body, encoding="utf-8")


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
        "- Strategy guides hub: https://boxboxf1fantasy.com/guides/",
        "- Tool landing pages: https://boxboxf1fantasy.com/tools/",
        "- F1 Fantasy predictions: https://boxboxf1fantasy.com/tools/f1-fantasy-predictions/",
        "- Lineup optimizer: https://boxboxf1fantasy.com/tools/lineup-optimizer/",
        "- Team compare: https://boxboxf1fantasy.com/tools/team-compare/",
        "- Transfer planner: https://boxboxf1fantasy.com/tools/transfer-planner/",
        "- Budget builder: https://boxboxf1fantasy.com/tools/budget-builder/",
        "- Points calculator: https://boxboxf1fantasy.com/tools/points-calculator/",
        "",
        "Current data endpoints:",
        "- Current predictions JSON: https://boxboxf1fantasy.com/data/predictions.json",
        "- Season summary JSON: https://boxboxf1fantasy.com/data/season_summary.json",
        "- Changelog JSON: https://boxboxf1fantasy.com/data/changelog.json",
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
        "",
        "Disclosure:",
        "BoxBoxF1Fantasy is not affiliated with Formula 1, the FIA, F1 Fantasy, or any F1 team or driver. Predictions are informational and for entertainment.",
        "",
    ])
    (WEB / "llms.txt").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# guides + tool landing pages (static content) + their hubs
# --------------------------------------------------------------------------- #
def _faq_html(faqs) -> str:
    return "".join(f'<p class="faq-q">{esc(q)}</p><p class="faq-a">{esc(a)}</p>' for q, a in faqs)


def render_content_page(item: dict) -> str:
    base = item["base"]            # "guides" or "tools"
    crumb = item["crumb"]          # "Guides" or "Tools"
    canonical = f"{SITE}/{base}/{item['slug']}/"
    faqs = item.get("faqs", [])

    ld_objs = [{
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": crumb, "item": f"{SITE}/{base}/"},
            {"@type": "ListItem", "position": 3, "name": item["crumb_self"], "item": canonical},
        ],
    }]
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

    body = (
        f'<p class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/{base}/">{esc(crumb)}</a> &rsaquo; {esc(item["crumb_self"])}</p>'
        f'<h1>{esc(item["h1"])}</h1>'
        + item["intro"] + cta + item["body"] + faq_section + cta
    )
    return page_head(item["title"], item["desc"], canonical, ld_block(ld_objs)) + body + FOOTER


def render_list_hub(base, crumb, hub, items) -> str:
    canonical = f"{SITE}/{base}/"
    ld = ld_block([{
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": crumb, "item": canonical},
        ],
    }])
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
        "base": "tools", "crumb": "Tools", "slug": "lineup-optimizer",
        "crumb_self": "Lineup Optimizer",
        "title": "F1 Fantasy Lineup Optimizer (Free) | BoxBox",
        "desc": "A free F1 Fantasy lineup optimizer that checks all 1.4 million legal 5-driver, 2-constructor teams within your budget and ranks the best lineups using ML predictions.",
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

    # all sitemap URLs (relative): home + picks + guides + tools
    rel_paths = ["", "picks/"] + [f"picks/{e[0]}/" for e in entries]

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
            (d / "index.html").write_text(render_content_page(it), encoding="utf-8")
        (out_base / "index.html").write_text(render_list_hub(base, crumb, hub, items), encoding="utf-8")
        rel_paths.append(f"{base}/")
        rel_paths += [f"{base}/{it['slug']}/" for it in items]

    write_sitemap(rel_paths)
    write_robots()
    write_llms_txt(rel_paths)

    print(f"[14_build_seo_pages] wrote {written} race page(s) + {len(GUIDES)} guide(s) "
          f"+ {len(TOOLS)} tool page(s) + 3 hubs + sitemap.xml ({len(rel_paths)} URLs) "
          "+ robots.txt + llms.txt")


if __name__ == "__main__":
    main()
