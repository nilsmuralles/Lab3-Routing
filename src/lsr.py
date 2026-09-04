# Link-state routing: LSDB + reflood + dijkstra.

from __future__ import annotations

import asyncio
import logging

from . import dijkstra, envelope, flooding
from .router import Router

logger = logging.getLogger(__name__)


class LSRRouter(Router):
    def __init__(self, node_id: str, neighbors, transport=None, initial_ttl: int = 8) -> None:
        self.node_id = node_id
        self.neighbors = neighbors
        self.transport = transport
        self.initial_ttl = initial_ttl
        self._seq = 0
        self.lsdb: dict[str, dict] = {}
        self._table: dict[str, dict] = {}
        self._announce_task: asyncio.Task | None = None
        self.neighbors.on_change(self._on_neighbors_change)

    def next_hop(self, dest: str) -> str | None:
        if dest == self.node_id:
            return None
        entry = self._table.get(dest)
        return None if entry is None else entry.get("next_hop")

    async def on_info(self, pkt: dict, from_id: str) -> None:
        payload = pkt.get("payload")
        if not isinstance(payload, dict):
            return
        origin = payload.get("origin")
        seq = payload.get("seq")
        announced = payload.get("neighbors")
        if (not isinstance(origin, str) or not origin or
                isinstance(seq, bool) or not isinstance(seq, int) or
                not isinstance(announced, dict)):
            return

        known = self.lsdb.get(origin, {}).get("seq", -1)
        if seq <= known:
            return

        neighbors = {
            neighbor: float(cost)
            for neighbor, cost in announced.items()
            if isinstance(neighbor, str) and neighbor and
            isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0
        }
        self.lsdb[origin] = {"seq": seq, "neighbors": neighbors}
        self.recompute()
        await flooding.flood(self.transport, self.neighbors, pkt, exclude_id=from_id)

    def build_local_info(self) -> dict | None:
        self._seq += 1
        local = {
            "origin": self.node_id,
            "seq": self._seq,
            "neighbors": dict(self.neighbors.costs()),
        }
        self.lsdb[self.node_id] = {
            "seq": self._seq,
            "neighbors": dict(local["neighbors"]),
        }
        self.recompute()
        return local

    def recompute(self) -> None:
        graph: dict[str, dict[str, float]] = {}
        for origin, record in self.lsdb.items():
            graph.setdefault(origin, {})
            for neighbor, cost in record.get("neighbors", {}).items():
                graph.setdefault(neighbor, {})
                # Conflicting advertisements are resolved deterministically:
                # the lowest valid advertised cost wins.
                graph[origin][neighbor] = min(graph[origin].get(neighbor, cost), cost)
                graph[neighbor][origin] = min(graph[neighbor].get(origin, cost), cost)
        self._table = dijkstra.compute(graph, self.node_id)

    async def run(self) -> None:
        await self._announce_local()
        await asyncio.sleep(1.0)
        await self._announce_local()
        await asyncio.Event().wait()

    def _on_neighbors_change(self) -> None:
        if self._announce_task is None or self._announce_task.done():
            try:
                self._announce_task = asyncio.create_task(self._announce_local())
            except RuntimeError:
                self._announce_task = None

    async def _announce_local(self) -> None:
        lsp = self.build_local_info()
        if self.transport is None:
            return
        pkt = envelope.make(
            proto="lsr",
            type="info",
            frm=self.node_id,
            to="*",
            ttl=self.initial_ttl,
            payload=lsp,
        )
        await flooding.flood(self.transport, self.neighbors, pkt, exclude_id=None)
