# Link-state routing: LSDB + reflood + dijkstra.

from __future__ import annotations

import asyncio
import logging
import time

from . import dijkstra, envelope, flooding
from .router import Router

logger = logging.getLogger(__name__)

REANNOUNCE_INTERVAL_SEC = 10.0
LSP_EXPIRY_SEC = 30.0
# Extension recomendada en PROTOCOLO.md: un origin cuyo seq cae mucho por
# debajo del ultimo conocido (reinicio) se acepta como fresco en vez de
# quedar descartado indefinidamente por la regla normal seq > known.
RESTART_SEQ_GAP = 16


def _parse_neighbors(raw) -> dict[str, float] | None:
    """Accepts the canonical list-of-{id,weight} form, plus the legacy
    dict-of-cost and {node,cost} variants some implementations may still
    send (PROTOCOLO.md: 'se recomienda aceptar ademas las variantes
    equivalentes')."""
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            nid = entry.get("id", entry.get("node"))
            cost = entry.get("weight", entry.get("cost"))
            items.append((nid, cost))
    else:
        return None

    for nid, cost in items:
        if (isinstance(nid, str) and nid and isinstance(cost, (int, float))
                and not isinstance(cost, bool) and cost >= 0):
            out[nid] = float(cost)
    return out


class LSRRouter(Router):
    def __init__(self, node_id: str, neighbors, transport=None, initial_ttl: int = 16) -> None:
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
        neighbors = _parse_neighbors(payload.get("neighbors"))
        if (not isinstance(origin, str) or not origin or
                isinstance(seq, bool) or not isinstance(seq, int) or
                neighbors is None):
            return

        known = self.lsdb.get(origin, {}).get("seq")
        is_restart = known is not None and (known - seq) > RESTART_SEQ_GAP
        if known is not None and seq <= known and not is_restart:
            return

        self.lsdb[origin] = {"seq": seq, "neighbors": neighbors, "received_at": time.time()}
        self.recompute()
        await flooding.flood(self.transport, self.neighbors, pkt, exclude_id=from_id)

    def build_local_info(self) -> dict | None:
        self._seq += 1
        costs = dict(self.neighbors.costs())
        local = {
            "origin": self.node_id,
            "seq": self._seq,
            "age_s": 0,
            "neighbors": [{"id": nid, "weight": cost} for nid, cost in costs.items()],
        }
        self.lsdb[self.node_id] = {
            "seq": self._seq, "neighbors": costs, "received_at": time.time(),
        }
        self.recompute()
        return local

    def _prune_expired(self) -> bool:
        now = time.time()
        expired = [
            origin for origin, record in self.lsdb.items()
            if origin != self.node_id and now - record.get("received_at", now) > LSP_EXPIRY_SEC
        ]
        for origin in expired:
            del self.lsdb[origin]
            logger.info("%s: LSP de %s expiro, se elimina de la LSDB", self.node_id, origin)
        return bool(expired)

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
        # Outbound connections to neighbors are still being dialed
        # asynchronously right after startup, so the very first flood above
        # can silently miss neighbors whose socket isn't up yet. A quick
        # early re-announce (before settling into the 10s steady-state
        # cadence) makes first convergence not depend on connection timing.
        await asyncio.sleep(1.0)
        await self._announce_local()
        while True:
            await asyncio.sleep(REANNOUNCE_INTERVAL_SEC)
            if self._prune_expired():
                self.recompute()
            await self._announce_local()

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
