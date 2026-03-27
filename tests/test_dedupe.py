from raidbot.dedupe import InMemoryOpenedUrlStore


def test_mark_if_new_returns_true_for_first_url():
    store = InMemoryOpenedUrlStore()

    assert store.mark_if_new("https://x.com/i/status/123") is True


def test_mark_if_new_returns_false_for_duplicate_url():
    store = InMemoryOpenedUrlStore()

    assert store.mark_if_new("https://x.com/i/status/123") is True
    assert store.mark_if_new("https://x.com/i/status/123") is False
