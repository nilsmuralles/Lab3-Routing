# Deduplication cache for flooded/forwarded packets. 
from __future__ import annotations

class DedupCache:
    def __init__(self, ttl_sec: float) -> None:
        raise NotImplementedError

    def seen(self, pkt_id: str) -> bool:
        raise NotImplementedError

    def add(self, pkt_id: str) -> None:
        raise NotImplementedError
