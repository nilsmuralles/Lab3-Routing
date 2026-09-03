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

        self._seq: dict[str, int] = {}
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

            seq = self._seq.get(nid, 0) + 1
            self._seq[nid] = seq
            sent_at = time.time()
            self._pending[nid] = {"seq": seq, "sent_at": sent_at}

            pkt = envelope.make(
                self.proto, "hello", self.node_id, nid, 1,
                {"seq": seq, "sent_at": sent_at},
            )
            await self.transport.send(nid, pkt)

    async def handle_hello(self, pkt: dict, from_id: str) -> None:
        payload = pkt.get("payload") or {}
        echo = envelope.make(
            self.proto, "echo", self.node_id, from_id, 1,
            {
                "seq": payload.get("seq"),
                "sent_at": payload.get("sent_at"),
                "echoed_at": time.time(),
            },
        )
        await self.transport.send(from_id, echo)

    async def handle_echo(self, pkt: dict, from_id: str) -> None:
        payload = pkt.get("payload") or {}
        pending = self._pending.get(from_id)
        if pending is None or payload.get("seq") != pending["seq"]:
            return
        rtt = time.time() - pending["sent_at"]
        self._pending.pop(from_id, None)
        self.neighbors.on_echo(from_id, rtt)
        was_recovered = self.neighbors.is_up(from_id)
        logger.debug(
            "%s: echo from %s rtt=%.4fs (up=%s)",
            self.node_id, from_id, rtt, was_recovered,
        )
