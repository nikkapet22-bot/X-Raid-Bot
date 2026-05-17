from raidbot.dedupe import InMemoryOpenedUrlStore


def test_mark_if_new_returns_true_for_first_url():
    store = InMemoryOpenedUrlStore()

    assert store.mark_if_new("https://x.com/i/status/123") is True


def test_mark_if_new_returns_false_for_duplicate_url():
    store = InMemoryOpenedUrlStore()

    assert store.mark_if_new("https://x.com/i/status/123") is True
    assert store.mark_if_new("https://x.com/i/status/123") is False


def test_mark_if_new_returns_false_for_same_status_in_different_url_shape():
    store = InMemoryOpenedUrlStore()

    assert store.mark_if_new("https://x.com/i/status/123") is True
    assert store.contains("https://twitter.com/some_user/status/123") is True
    assert store.mark_if_new("https://x.com/some_user/status/123") is False
