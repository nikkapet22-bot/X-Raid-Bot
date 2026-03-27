from __future__ import annotations


class InMemoryOpenedUrlStore:
    def __init__(self) -> None:
        self._opened_urls: set[str] = set()

    def contains(self, url: str) -> bool:
        return url in self._opened_urls

    def mark_if_new(self, url: str) -> bool:
        if url in self._opened_urls:
            return False
        self._opened_urls.add(url)
        return True
