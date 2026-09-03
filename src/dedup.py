from __future__ import annotations

import time

class DedupCache:
    def __init__(self, ttl_sec: float) -> None:
        self.ttl_sec = float(ttl_sec)
        self._seen: dict[str, float] = {}

    def _purge(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > self.ttl_sec]
        for k in expired:
            del self._seen[k]

    def seen(self, pkt_id: str) -> bool:
        now = time.monotonic()
        self._purge(now)
        return pkt_id in self._seen

    def add(self, pkt_id: str) -> None:
        self._seen[pkt_id] = time.monotonic()
