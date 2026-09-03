# Link-state routing: LSDB + reflood + dijkstra.

from __future__ import annotations

class LSRRouter:
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

    async def run(self) -> None:
        """Optional background loop (e.g. announce LSP on start). node.py
        calls this if present -- see src/node.py."""
        raise NotImplementedError
