"""
Build articles JSON from Markdown files in /articles folder.

Each .md file should have YAML-like frontmatter:
---
title: My Article Title
date: 2026-03-16
round: 1
tags: preview, analysis
---

Article body in Markdown here...

Run: python pipeline/build_articles.py
Output: web/public/data/articles.json
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "articles"
OUT_PATH = ROOT / "web" / "public" / "data" / "articles.json"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-like frontmatter and body from markdown text."""
    meta = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if m:
        for line in m.group(1).strip().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip()
        body = m.group(2)
    return meta, body


def md_to_html(md: str) -> str:
    """Simple Markdown to HTML converter (no dependencies)."""
    lines = md.split("\n")
    html_lines = []
    in_ul = False
    in_ol = False
    in_blockquote = False
    in_p = False

    def inline(text):
        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
        # Italic
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
        # Links
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
        # Inline code
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        return text

    def close_lists():
        nonlocal in_ul, in_ol
        result = []
        if in_ul:
            result.append("</ul>")
            in_ul = False
        if in_ol:
            result.append("</ol>")
            in_ol = False
        return result

    def close_p():
        nonlocal in_p
        if in_p:
            in_p = False
            return ["</p>"]
        return []

    for line in lines:
        stripped = line.strip()

        # Empty line
        if not stripped:
            html_lines.extend(close_p())
            html_lines.extend(close_lists())
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            continue

        # Headers
        hm = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if hm:
            html_lines.extend(close_p())
            html_lines.extend(close_lists())
            level = len(hm.group(1))
            html_lines.append(f"<h{level}>{inline(hm.group(2))}</h{level}>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            html_lines.extend(close_p())
            html_lines.extend(close_lists())
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{inline(stripped[2:])}</p>")
            continue

        # Unordered list
        um = re.match(r"^[-*+]\s+(.+)$", stripped)
        if um:
            html_lines.extend(close_p())
            if not in_ul:
                html_lines.extend(close_lists())
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{inline(um.group(1))}</li>")
            continue

        # Ordered list
        om = re.match(r"^\d+\.\s+(.+)$", stripped)
        if om:
            html_lines.extend(close_p())
            if not in_ol:
                html_lines.extend(close_lists())
                html_lines.append("<ol>")
                in_ol = True
            html_lines.append(f"<li>{inline(om.group(1))}</li>")
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            html_lines.extend(close_p())
            html_lines.extend(close_lists())
            html_lines.append("<hr>")
            continue

        # Regular paragraph
        if not in_p:
            html_lines.append("<p>")
            in_p = True
            html_lines.append(inline(stripped))
        else:
            html_lines.append(" " + inline(stripped))

    # Close any open tags
    html_lines.extend(close_p())
    html_lines.extend(close_lists())
    if in_blockquote:
        html_lines.append("</blockquote>")

    return "\n".join(html_lines)


def build():
    if not ARTICLES_DIR.exists():
        ARTICLES_DIR.mkdir(parents=True)

    articles = []
    for md_file in sorted(ARTICLES_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        round_num = None
        if "round" in meta:
            try:
                round_num = int(meta["round"])
            except ValueError:
                pass

        articles.append({
            "slug": md_file.stem,
            "title": meta.get("title", md_file.stem.replace("-", " ").replace("_", " ").title()),
            "date": meta.get("date", ""),
            "round": round_num,
            "tags": tags,
            "content_html": md_to_html(body.strip()),
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"articles": articles}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Built {len(articles)} article(s) -> {OUT_PATH}")


if __name__ == "__main__":
    build()
