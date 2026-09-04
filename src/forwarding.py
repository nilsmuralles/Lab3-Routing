# Packet dispatch by type (message/hello/echo/info).
from __future__ import annotations

import logging

from . import envelope
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

        self._check_checksum(pkt)

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

    def _check_checksum(self, pkt: dict) -> None:
        # Per PROTOCOLO.md: a checksum mismatch is logged, never used to
        # drop the packet -- different canonicalizations must not partition
        # the network.
        claimed = envelope.header_get(pkt.get("headers") or [], "checksum")
        if claimed is None:
            return
        actual = envelope.compute_checksum(pkt.get("payload"))
        if claimed != actual:
            logger.warning(
                "%s: checksum mismatch (claimed=%s actual=%s) from=%s type=%s",
                self.node_id, claimed, actual, pkt.get("from"), pkt.get("type"),
            )

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
        key = envelope.dedup_key(pkt)
        if self.dedup.seen(key):
            return
        self.dedup.add(key)

        await self.router.on_info(pkt, from_id)

    # message

    async def _handle_message(self, pkt: dict, from_id: str) -> None:
        dest = pkt.get("to")
        is_flood_mode = isinstance(self.router, FloodingRouter)

        if is_flood_mode:
            key = envelope.dedup_key(pkt)
            if self.dedup.seen(key):
                return
            self.dedup.add(key)

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
        headers = list(pkt.get("headers") or [])
        trace = envelope.header_get(headers, "trace")
        trace = (list(trace) if isinstance(trace, list) else []) + [self.node_id]
        headers = envelope.header_set(headers, "trace", trace)
        headers = envelope.header_set(headers, "via", self.node_id)
        fwd["headers"] = headers
        return fwd

    def _deliver_local(self, pkt: dict) -> None:
        logger.info(
            "%s: mensaje entregado from=%s hops=%s payload=%r",
            self.node_id, pkt.get("from"), _trace(pkt), pkt.get("payload"),
        )
        self.delivered.append(pkt)


def _trace(pkt: dict) -> list:
    trace = envelope.header_get(pkt.get("headers") or [], "trace")
    return trace if isinstance(trace, list) else []
