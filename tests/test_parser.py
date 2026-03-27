from raidbot.parser import parse_raid_message


ACTIVE_MESSAGE = """
Likes 10 | 8 [%]
Retweets 8 | 8 [%]
Replies 7 | 7 [%]

https://x.com/i/status/2036140112963313949
"""

QUEUE_MESSAGE = """
Next up... (7/10 tweets)

1/ https://x.com/i/status/2036144451249414610
2/ https://x.com/i/status/2036144840648597936
"""


def test_parse_raid_message_extracts_canonical_status_url():
    match = parse_raid_message(ACTIVE_MESSAGE)

    assert match is not None
    assert match.normalized_url == "https://x.com/i/status/2036140112963313949"


def test_parse_raid_message_rejects_next_up_queue_posts():
    assert parse_raid_message(QUEUE_MESSAGE) is None
