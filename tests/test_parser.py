from raidbot.parser import parse_raid_message


ACTIVE_MESSAGE = """
Likes 10 | 8 [%]
Retweets 8 | 8 [%]
Replies 7 | 7 [%]

https://x.com/i/status/2036140112963313949
"""

D_RAIDBOT_MESSAGE = """
Reposts 8 | 8 [%]
Bookmarks 4 | 4 [%]
Replies 2 | 2 [%]

https://x.com/i/status/999
"""

SINGULAR_MARKER_MESSAGE = """
Like 1
Retweet 1
Reply 1
Bookmark 1

https://twitter.com/some_user/status/1234567890123456789
"""

QUEUE_MESSAGE = """
Next up... (7/10 tweets)

1/ https://x.com/i/status/2036144451249414610
2/ https://x.com/i/status/2036144840648597936
"""


def test_parse_raid_message_extracts_canonical_status_url():
    match = parse_raid_message(ACTIVE_MESSAGE)

    assert match is not None
    assert match.raw_url == "https://x.com/i/status/2036140112963313949"
    assert match.normalized_url == "https://x.com/i/status/2036140112963313949"
    assert match.requirements.like is True
    assert match.requirements.repost is True
    assert match.requirements.reply is True
    assert match.requirements.bookmark is False


def test_parse_raid_message_extracts_required_actions_from_d_raidbot_style_message():
    match = parse_raid_message(D_RAIDBOT_MESSAGE)

    assert match is not None
    assert match.normalized_url == "https://x.com/i/status/999"
    assert match.requirements.repost is True
    assert match.requirements.bookmark is True
    assert match.requirements.reply is True
    assert match.requirements.like is False


def test_parse_raid_message_normalizes_singular_synonyms_and_twitter_source_url():
    match = parse_raid_message(SINGULAR_MARKER_MESSAGE)

    assert match is not None
    assert (
        match.raw_url
        == "https://twitter.com/some_user/status/1234567890123456789"
    )
    assert match.normalized_url == "https://x.com/some_user/status/1234567890123456789"
    assert match.requirements.like is True
    assert match.requirements.repost is True
    assert match.requirements.reply is True
    assert match.requirements.bookmark is True


def test_parse_raid_message_rejects_next_up_queue_posts():
    assert parse_raid_message(QUEUE_MESSAGE) is None
