# Shortest paths (pure) + static-topology router.
from __future__ import annotations

import heapq
import json


def compute(graph: dict[str, dict[str, float]], source: str) -> dict[str, dict]:
    
    if source not in graph:
        return {}

    dist: dict[str, float] = {source: 0.0}
    next_hop: dict[str, str | None] = {source: None}
    visited: set[str] = set()
    pq: list[tuple[float, str]] = [(0.0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)

        for v, w in graph.get(u, {}).items():
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                next_hop[v] = v if u == source else next_hop[u]
                heapq.heappush(pq, (nd, v))

    result: dict[str, dict] = {}
    for node, d in dist.items():
        if node == source:
            continue
        result[node] = {"next_hop": next_hop[node], "cost": d}
    return result


class DijkstraRouter:

    def __init__(self, node_id, neighbors, topology_file) -> None:
        self.node_id = node_id
        self.neighbors = neighbors
        self.topology_file = topology_file
        self._graph = self._load_topology(topology_file)
        self._table: dict[str, dict] = {}
        self.recompute()

    @staticmethod
    def _load_topology(path: str) -> dict[str, dict[str, float]]:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {src: dict(edges) for src, edges in raw.items()}

    def next_hop(self, dest: str) -> str | None:
        if dest == self.node_id:
            return None
        entry = self._table.get(dest)
        if entry is None:
            return None
        nh = entry["next_hop"]
        if nh is None:
            return None

        if self.neighbors is not None and not self.neighbors.is_up(nh):
            return None
        return nh

    async def on_info(self, pkt: dict, from_id: str) -> None:
        # Dijkstra estatico no participa del protocolo de LSPs.
        return None

    def build_local_info(self) -> dict | None:
        # No origina LSPs en este modo.
        return None

    def recompute(self) -> None:
        self._table = compute(self._graph, self.node_id)
