# Shortest paths (pure) + static-topology router.
from __future__ import annotations

def compute(graph: dict[str, dict[str, float]], source: str) -> dict[str, dict]:
    raise NotImplementedError

class DijkstraRouter:
    def __init__(self, node_id, neighbors, topology_file) -> None:
        raise NotImplementedError

    def next_hop(self, dest: str) -> str | None:
        raise NotImplementedError

    async def on_info(self, pkt: dict, from_id: str) -> None:
        raise NotImplementedError

    def build_local_info(self) -> dict | None:
        raise NotImplementedError

    def recompute(self) -> None:
        raise NotImplementedError
