# Neighbor liveness via periodic hello/echo (PROTOCOLO.md "hello y echo").

from __future__ import annotations

import asyncio
import logging
import time

from . import envelope

logger = logging.getLogger(__name__)


def _norm(addr: str, default_port: int | None) -> str:
    """PROTOCOLO.md: 'una direccion sin puerto se completa con el puerto
    configurado de la red'. So "10.0.0.7" and "10.0.0.7:5000" name the same
    node when the common port is 5000."""
    if not isinstance(addr, str) or not addr:
        return addr
    if ":" in addr or default_port is None:
        return addr
    return f"{addr}:{default_port}"


class HealthCheck:
    def __init__(self, transport, neighbors, params, proto) -> None:
        self.transport = transport
        self.neighbors = neighbors
        self.params = params
        self.proto = proto
        self.node_id: str = transport.node_id
        self.default_port = params.get("default_port") or getattr(transport, "port", None)

        self.interval = float(params.get("hello_interval_sec", 5))
        if hasattr(neighbors, "max_failures"):
            neighbors.max_failures = int(params.get("hello_max_failures", 3))

        # neighbor_id -> {"msg_id": str, "t0": float}
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
            # PROTOCOLO.md: hello headers carry msg_id + t0 + checksum;
            # payload is the object {"listen_port": <port>}.
            headers = envelope.header_set([], "t0", t0)
            pkt = envelope.make(
                self.proto, "hello", self.node_id, nid, 1,
                {"listen_port": self.transport.port},
                headers=headers,
            )
            self._pending[nid] = {"msg_id": envelope.msg_id(pkt), "t0": t0}
            await self.transport.send(nid, pkt)

    async def handle_hello(self, pkt: dict, from_id: str) -> None:
        # PROTOCOLO.md: the echo keeps the same msg_id and t0 and swaps
        # from/to. payload stays the {"listen_port"} object.
        headers = pkt.get("headers") or []
        mid = envelope.header_get(headers, "msg_id")
        t0 = envelope.header_get(headers, "t0")
        echo_headers: list = []
        if mid is not None:
            echo_headers = envelope.header_set(echo_headers, "msg_id", mid)
        if t0 is not None:
            echo_headers = envelope.header_set(echo_headers, "t0", t0)
        echo = envelope.make(
            self.proto, "echo", self.node_id, from_id, 1,
            {"listen_port": self.transport.port},
            headers=echo_headers,
        )
        await self.transport.send(from_id, echo)

    async def handle_echo(self, pkt: dict, from_id: str) -> None:
        headers = pkt.get("headers") or []
        mid = envelope.header_get(headers, "msg_id")

        # Match the echo to the hello that produced it. Prefer msg_id (it is
        # preserved verbatim and unique) so that a peer whose `from` address
        # is written in a different form than our neighbor id -- "10.0.0.7"
        # vs "10.0.0.7:5000", a logical label, etc. -- is still recognised
        # and does not get falsely marked DOWN.
        nid = None
        if mid is not None:
            for k, p in self._pending.items():
                if p.get("msg_id") == mid:
                    nid = k
                    break
        if nid is None:
            for cand in (from_id, _norm(from_id, self.default_port)):
                if cand in self._pending:
                    nid = cand
                    break
        if nid is None:
            return  # stale / out-of-context echo -> ignore

        pending = self._pending[nid]
        if mid is not None and pending.get("msg_id") not in (None, mid):
            return

        t0_echo = envelope.header_get(headers, "t0")
        base = (
            t0_echo
            if isinstance(t0_echo, (int, float)) and not isinstance(t0_echo, bool)
            else pending["t0"]
        )
        rtt = time.time() - base
        del self._pending[nid]
        self.neighbors.on_echo(nid, rtt)
        logger.debug(
            "%s: echo from %s (matched %s) rtt=%.4fs up=%s",
            self.node_id, from_id, nid, rtt, self.neighbors.is_up(nid),
        )
