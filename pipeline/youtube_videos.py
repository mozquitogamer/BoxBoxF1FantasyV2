"""
Fetch latest videos from the @BoxBoxF1Fantasy YouTube channel via RSS feed.

Uses only stdlib: urllib, xml.etree.ElementTree, json, datetime, re, logging.
Outputs web/public/data/youtube_videos.json with the 4 most recent videos.
"""

import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

HANDLE = "BoxBoxF1Fantasy"
CHANNEL_URL = f"https://www.youtube.com/@{HANDLE}"
MAX_VIDEOS = 4
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "youtube_videos.json"

# YouTube Atom feed namespaces
ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def fetch_url(url: str) -> bytes:
    """Fetch a URL and return raw bytes."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def resolve_channel_id() -> str:
    """Resolve the YouTube channel ID from the @handle page HTML."""
    log.info("Resolving channel ID for @%s ...", HANDLE)
    try:
        html = fetch_url(CHANNEL_URL).decode("utf-8", errors="replace")
    except (HTTPError, URLError) as exc:
        log.error("Failed to fetch channel page: %s", exc)
        raise

    # YouTube embeds the channel ID in several places in the page source.
    # Look for patterns like "channelId":"UCxxxxxxx" or "externalId":"UCxxxxxxx"
    for pattern in [
        r'"channelId"\s*:\s*"(UC[A-Za-z0-9_-]+)"',
        r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]+)"',
        r'<meta\s[^>]*content="(UC[A-Za-z0-9_-]+)"[^>]*itemprop="channelId"',
        r'data-channel-external-id="(UC[A-Za-z0-9_-]+)"',
        r'"browseId"\s*:\s*"(UC[A-Za-z0-9_-]+)"',
    ]:
        match = re.search(pattern, html)
        if match:
            channel_id = match.group(1)
            log.info("Found channel ID: %s", channel_id)
            return channel_id

    raise RuntimeError(
        f"Could not extract channel ID from {CHANNEL_URL}. "
        "The page structure may have changed."
    )


def fetch_feed(channel_id: str) -> list[dict]:
    """Fetch the YouTube RSS/Atom feed and parse video entries."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    log.info("Fetching RSS feed: %s", feed_url)

    try:
        xml_bytes = fetch_url(feed_url)
    except (HTTPError, URLError) as exc:
        log.error("Failed to fetch RSS feed: %s", exc)
        raise

    root = ET.fromstring(xml_bytes)
    entries = root.findall(f"{{{ATOM_NS}}}entry")
    log.info("Found %d entries in feed", len(entries))

    videos = []
    for entry in entries[:MAX_VIDEOS]:
        video_id_el = entry.find(f"{{{YT_NS}}}videoId")
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        published_el = entry.find(f"{{{ATOM_NS}}}published")

        if video_id_el is None or title_el is None or published_el is None:
            log.warning("Skipping entry with missing fields")
            continue

        video_id = video_id_el.text.strip()
        title = title_el.text.strip()
        # published is ISO 8601, e.g. "2026-03-20T15:00:00+00:00"
        published_raw = published_el.text.strip()
        # Parse and format as date only
        try:
            published_dt = datetime.fromisoformat(published_raw)
            published_date = published_dt.strftime("%Y-%m-%d")
        except ValueError:
            published_date = published_raw[:10]

        videos.append({
            "id": video_id,
            "title": title,
            "published": published_date,
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return videos


def main() -> None:
    try:
        channel_id = resolve_channel_id()
    except Exception:
        log.error("Could not resolve channel ID. Aborting.")
        sys.exit(1)

    try:
        videos = fetch_feed(channel_id)
    except Exception:
        log.error("Could not fetch or parse RSS feed. Aborting.")
        sys.exit(1)

    if not videos:
        log.warning("No videos found in the feed.")

    output = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel_url": CHANNEL_URL,
        "videos": videos,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log.info("Wrote %d videos to %s", len(videos), OUTPUT_PATH)


if __name__ == "__main__":
    main()
