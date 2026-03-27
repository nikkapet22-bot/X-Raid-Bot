from __future__ import annotations

import re

from raidbot.models import RaidMatch

RAID_MARKERS = ("likes", "retweets", "replies")
STATUS_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/(?P<path>[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*/status/(?P<status_id>\d+))",
    re.IGNORECASE,
)


def parse_raid_message(text: str) -> RaidMatch | None:
    lowered_text = text.lower()
    if "next up" in lowered_text:
        return None
    if not any(marker in lowered_text for marker in RAID_MARKERS):
        return None

    url_match = STATUS_URL_RE.search(text)
    if url_match is None:
        return None

    raw_url = url_match.group(0)
    normalized_url = f"https://x.com/{url_match.group('path')}"
    return RaidMatch(raw_url=raw_url, normalized_url=normalized_url)
