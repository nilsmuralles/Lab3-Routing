# Flood distribution + pure-flooding router.
from __future__ import annotations


async def flood(transport, neighbors, pkt: dict, exclude_id: str | None) -> None:
    raise NotImplementedError


class FloodingRouter:
    def __init__(self, node_id, neighbors) -> None:
        raise NotImplementedError

    def next_hop(self, dest: str) -> str | None:
        raise NotImplementedError

    async def on_info(self, pkt: dict, from_id: str) -> None:
        raise NotImplementedError

    def build_local_info(self) -> dict | None:
        raise NotImplementedError

    def recompute(self) -> None:
        raise NotImplementedError
