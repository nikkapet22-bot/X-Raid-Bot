from __future__ import annotations

from dataclasses import dataclass
import re

from raidbot.models import RaidActionRequirements

MARKER_GROUPS = {
    "like": ("like", "likes"),
    "repost": ("retweet", "retweets", "repost", "reposts"),
    "reply": ("reply", "replies"),
    "bookmark": ("bookmark", "bookmarks"),
}
STATUS_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/(?P<path>[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*/status/(?P<status_id>\d+))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedRaidMessage:
    raw_url: str
    normalized_url: str
    requirements: RaidActionRequirements


@dataclass(frozen=True)
class RaidMessageParseOutcome:
    match: ParsedRaidMessage | None
    reason: str | None = None


def _has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in markers)


def analyze_raid_message(text: str) -> RaidMessageParseOutcome:
    lowered_text = text.lower()
    if "next up" in lowered_text:
        return RaidMessageParseOutcome(match=None, reason="missing_action_markers")

    requirements = RaidActionRequirements(
        like=_has_any_marker(lowered_text, MARKER_GROUPS["like"]),
        repost=_has_any_marker(lowered_text, MARKER_GROUPS["repost"]),
        bookmark=_has_any_marker(lowered_text, MARKER_GROUPS["bookmark"]),
        reply=_has_any_marker(lowered_text, MARKER_GROUPS["reply"]),
    )
    if not any(
        (
            requirements.like,
            requirements.repost,
            requirements.bookmark,
            requirements.reply,
        )
    ):
        return RaidMessageParseOutcome(match=None, reason="missing_action_markers")

    url_match = STATUS_URL_RE.search(text)
    if url_match is None:
        return RaidMessageParseOutcome(match=None, reason="missing_status_url")

    raw_url = url_match.group(0)
    normalized_url = f"https://x.com/{url_match.group('path')}"
    return RaidMessageParseOutcome(
        match=ParsedRaidMessage(
            raw_url=raw_url,
            normalized_url=normalized_url,
            requirements=requirements,
        )
    )


def parse_raid_message(text: str) -> ParsedRaidMessage | None:
    return analyze_raid_message(text).match
