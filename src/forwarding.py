# Packet dispatch by type (message/hello/echo/info).
from __future__ import annotations


class Forwarder:
    def __init__(self, node_id, transport, router, neighbors, dedup, params) -> None:
        raise NotImplementedError

    async def handle(self, pkt: dict, from_id: str) -> None:
        raise NotImplementedError
