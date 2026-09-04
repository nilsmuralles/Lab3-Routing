# Neighbor liveness via periodic hello/echo.

from __future__ import annotations

import asyncio
import logging
import time

from . import envelope

logger = logging.getLogger(__name__)


class HealthCheck:
    def __init__(self, transport, neighbors, params, proto) -> None:
        self.transport = transport
        self.neighbors = neighbors
        self.params = params
        self.proto = proto
        self.node_id: str = transport.node_id

        self.interval = float(params.get("hello_interval_sec", 5))
        if hasattr(neighbors, "max_failures"):
            neighbors.max_failures = int(params.get("hello_max_failures", 3))

        self._pending: dict[str, dict] = {}

    async def run(self) -> None:
        while True:
            await self._tick()
            await asyncio.sleep(self.interval)

    async def _tick(self) -> None:
        for nid in self.neighbors.all():
            if nid in self._pending:
                if self.neighbors.on_timeout(nid):
                    logger.info("%s: neighbor %s marked DOWN", self.node_id, nid)

            t0 = time.time()
            pkt = envelope.make(
                self.proto, "hello", self.node_id, nid, 1,
                {"listen_port": self.transport.port},
            )
            self._pending[nid] = {"msg_id": envelope.msg_id(pkt), "t0": t0}
            await self.transport.send(nid, pkt)

    async def handle_hello(self, pkt: dict, from_id: str) -> None:
        headers = pkt.get("headers") or []
        mid = envelope.header_get(headers, "msg_id")
        t0 = envelope.header_get(headers, "t0")
        echo_headers = envelope.header_set([], "msg_id", mid) if mid else []
        if t0 is not None:
            echo_headers = envelope.header_set(echo_headers, "t0", t0)
        payload = pkt.get("payload") or {}
        echo = envelope.make(
            self.proto, "echo", self.node_id, from_id, 1,
            {"listen_port": self.transport.port},
            headers=echo_headers,
        )
        await self.transport.send(from_id, echo)

    async def handle_echo(self, pkt: dict, from_id: str) -> None:
        headers = pkt.get("headers") or []
        mid = envelope.header_get(headers, "msg_id")
        pending = self._pending.get(from_id)
        if pending is None or mid != pending["msg_id"]:
            return
        rtt = time.time() - pending["t0"]
        self._pending.pop(from_id, None)
        self.neighbors.on_echo(from_id, rtt)
        was_recovered = self.neighbors.is_up(from_id)
        logger.debug(
            "%s: echo from %s rtt=%.4fs (up=%s)",
            self.node_id, from_id, rtt, was_recovered,
        )

