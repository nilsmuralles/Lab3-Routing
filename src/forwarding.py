# Packet dispatch by type (message/hello/echo/info).
from __future__ import annotations

import copy
import logging

from .flooding import FloodingRouter, flood

logger = logging.getLogger(__name__)


class Forwarder:

    def __init__(self, node_id, transport, router, neighbors, dedup, params) -> None:
        self.node_id = node_id
        self.transport = transport
        self.router = router
        self.neighbors = neighbors
        self.dedup = dedup
        self.params = params
        self.healthcheck = None  # wired externally por node.py
        self.delivered: list[dict] = []  # mensajes entregados localmente (debug/tests)

    async def handle(self, pkt: dict, from_id: str) -> None:
        ttl = pkt.get("ttl")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0:
            return

        ptype = pkt.get("type")

        if ptype == "hello":
            await self._handle_hello(pkt, from_id)
            return

        if ptype == "echo":
            await self._handle_echo(pkt, from_id)
            return

        if ptype == "info":
            await self._handle_info(pkt, from_id)
            return

        if ptype == "message":
            await self._handle_message(pkt, from_id)
            return

        logger.debug("%s: paquete de tipo desconocido descartado: %r", self.node_id, ptype)


    async def _handle_hello(self, pkt: dict, from_id: str) -> None:
        if self.healthcheck is None:
            logger.debug("%s: hello recibido sin healthcheck conectado", self.node_id)
            return
        await self.healthcheck.handle_hello(pkt, from_id)

    async def _handle_echo(self, pkt: dict, from_id: str) -> None:
        if self.healthcheck is None:
            logger.debug("%s: echo recibido sin healthcheck conectado", self.node_id)
            return
        await self.healthcheck.handle_echo(pkt, from_id)


    async def _handle_info(self, pkt: dict, from_id: str) -> None:

        pkt_id = pkt.get("id")
        if pkt_id is not None:
            if self.dedup.seen(pkt_id):
                return
            self.dedup.add(pkt_id)

        await self.router.on_info(pkt, from_id)

    # message 

    async def _handle_message(self, pkt: dict, from_id: str) -> None:
        dest = pkt.get("to")
        is_flood_mode = isinstance(self.router, FloodingRouter)

        if is_flood_mode:
        
            pkt_id = pkt.get("id")
            if pkt_id is not None:
                if self.dedup.seen(pkt_id):
                    return
                self.dedup.add(pkt_id)

            if dest == self.node_id:
                
                self._deliver_local(pkt)
                return

            fwd = self._with_hop(pkt)
            if dest == "*":
                
                self._deliver_local(fwd)

            await flood(self.transport, self.neighbors, fwd, exclude_id=from_id)
            return

        if dest == self.node_id:
            self._deliver_local(pkt)
            return

        fwd = self._prepare_unicast_forward(pkt)
        if fwd is None:
            return  # ttl agotado al decrementar

        next_hop = self.router.next_hop(dest)
        if next_hop is None:
            logger.debug("%s: sin ruta a %s, mensaje descartado", self.node_id, dest)
            return
        if not self.neighbors.is_up(next_hop):
            logger.debug("%s: next-hop %s caido, mensaje descartado", self.node_id, next_hop)
            return

        await self.transport.send(next_hop, fwd)

    # helpers

    def _prepare_unicast_forward(self, pkt: dict) -> dict | None:
        new_ttl = pkt["ttl"] - 1
        if new_ttl <= 0:
            return None
        fwd = self._with_hop(pkt)
        fwd["ttl"] = new_ttl
        fwd["from"] = self.node_id
        return fwd

    def _with_hop(self, pkt: dict) -> dict:
        
        fwd = dict(pkt)
        headers = copy.deepcopy(pkt.get("headers")) or []
        for h in headers:
            if isinstance(h, dict) and "hops" in h:
                h["hops"] = list(h["hops"]) + [self.node_id]
                break
        else:
            headers.append({"hops": [self.node_id]})
        fwd["headers"] = headers
        return fwd

    def _deliver_local(self, pkt: dict) -> None:
        logger.info(
            "%s: mensaje entregado from=%s hops=%s payload=%r",
            self.node_id, pkt.get("from"), _hops(pkt), pkt.get("payload"),
        )
        self.delivered.append(pkt)


def _hops(pkt: dict) -> list:
    for header in pkt.get("headers") or []:
        if isinstance(header, dict) and isinstance(header.get("hops"), list):
            return header["hops"]
    return []
