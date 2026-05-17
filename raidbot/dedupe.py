from __future__ import annotations

from raidbot.parser import raid_status_identity


class InMemoryOpenedUrlStore:
    def __init__(self) -> None:
        self._opened_urls: set[str] = set()

    def _key(self, url: str) -> str:
        return raid_status_identity(url) or url

    def contains(self, url: str) -> bool:
        return self._key(url) in self._opened_urls

    def mark_if_new(self, url: str) -> bool:
        key = self._key(url)
        if key in self._opened_urls:
            return False
        self._opened_urls.add(key)
        return True
