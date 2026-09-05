from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from . import envelope

logger = logging.getLogger(__name__)
# Dedicated logger so every packet received from a neighbor is printed
# verbatim (INFO). Silence it with `logging.getLogger("rx").setLevel(...)`.
rx_logger = logging.getLogger("rx")
PacketHandler = Callable[[dict, str], Awaitable[None]]

class Transport:
    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        neighbors: dict[str, tuple[str, int]],
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.neighbors = neighbors
        self.on_packet: PacketHandler | None = None
        # Optional callback(pkt, peer, direction) invoked for every packet
        # received from a neighbor -- used by RxMonitor to print who/what.
        self.rx_observer: Callable[[dict, object, str], None] | None = None

        self._server: asyncio.base_events.Server | None = None
        # Writers we dialed ourselves (outbound), keyed by configured
        # neighbor id. These are (re)established by _maintain_connection.
        self._writers: dict[str, asyncio.StreamWriter] = {}
        # Writers for connections the peer opened to us (inbound), keyed by
        # the `from` id seen on that socket. Used as a fallback reply path
        # when our own outbound dial to that peer is not up yet (startup
        # race) or is backing off after a failure -- without this, a peer
        # can reach us but we cannot answer its hello, so it wrongly marks
        # us DOWN even though the link works.
        self._inbound_writers: dict[str, asyncio.StreamWriter] = {}
        self._locks: dict[str, asyncio.Lock] = {
            node_id: asyncio.Lock() for node_id in neighbors
        }
        self._reconnect_tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_incoming, self.host, self.port
        )
        for node_id in self.neighbors:
            self._reconnect_tasks[node_id] = asyncio.create_task(
                self._maintain_connection(node_id)
            )
        logger.info("%s: listening on %s:%d", self.node_id, self.host, self.port)

    async def send(self, neighbor_id: str, pkt: dict) -> bool:
        data = envelope.serialize(pkt).encode("utf-8")
        lock = self._locks.setdefault(neighbor_id, asyncio.Lock())
        # Try our outbound connection first, then fall back to any inbound
        # connection that peer opened to us.
        for store in (self._writers, self._inbound_writers):
            writer = store.get(neighbor_id)
            if writer is None or writer.is_closing():
                continue
            try:
                async with lock:
                    writer.write(data)
                    await writer.drain()
                return True
            except (ConnectionError, OSError):
                store.pop(neighbor_id, None)
        return False

    async def stop(self) -> None:
        for task in self._reconnect_tasks.values():
            task.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in list(self._writers.values()) + list(self._inbound_writers.values()):
            writer.close()

    async def _handle_incoming(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        try:
            await self._read_loop(reader, peer, inbound_writer=writer)
        finally:
            for k, w in list(self._inbound_writers.items()):
                if w is writer:
                    self._inbound_writers.pop(k, None)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _read_loop(
        self,
        reader: asyncio.StreamReader,
        peer,
        inbound_writer: asyncio.StreamWriter | None = None,
    ) -> None:
        """Shared by both accepted (inbound) and dialed (outbound)
        connections. Per PROTOCOLO.md: some implementations reply on the
        same socket they were addressed on instead of dialing back to
        `from` -- so we must not only write to our outbound connections,
        we must also read from them, or those replies (e.g. an echo to our
        own hello) are silently lost and the neighbor looks DOWN even
        though it answered."""
        direction = "in " if inbound_writer is not None else "out"
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").rstrip("\n")
                # Full verbatim dump only at DEBUG; the human-readable
                # who/what goes through rx_observer (RxMonitor).
                rx_logger.debug("RX [%s %s] %s", direction, peer, raw)
                pkt = envelope.parse(raw)
                if pkt is None:
                    rx_logger.warning(
                        "RX [%s %s] paquete DESCARTADO (JSON o campos invalidos): %s",
                        direction, peer, raw[:200],
                    )
                    continue
                from_id = pkt.get("from", "")
                if self.rx_observer is not None:
                    try:
                        self.rx_observer(pkt, peer, direction)
                    except Exception:  # nunca dejar que el log tumbe la lectura
                        logger.exception("rx_observer fallo")
                if inbound_writer is not None and from_id:
                    # Remember this socket as a reply path to `from_id`.
                    self._inbound_writers[from_id] = inbound_writer
                if self.on_packet is not None:
                    try:
                        await self.on_packet(pkt, from_id)
                    except (ConnectionError, OSError):
                        raise
                    except Exception:
                        # A packet from a different implementation can be
                        # well-formed per envelope.validate() but still
                        # trip an edge case in our own handling logic.
                        # That must never tear down an otherwise-healthy
                        # connection -- log it and keep reading.
                        logger.exception(
                            "%s: error procesando paquete de %s (type=%s), se descarta",
                            self.node_id, peer, pkt.get("type"),
                        )
        except (ConnectionError, OSError):
            pass

    async def _maintain_connection(self, node_id: str) -> None:
        host, port = self.neighbors[node_id]
        delay = 1.0
        while True:
            try:
                reader, writer = await asyncio.open_connection(host, port)
                self._writers[node_id] = writer
                delay = 1.0
                logger.info("%s: connected to %s (%s:%d)", self.node_id, node_id, host, port)
                await self._read_loop(reader, (host, port))
            except (ConnectionError, OSError):
                pass
            writer_ref = self._writers.pop(node_id, None)
            if writer_ref is not None:
                writer_ref.close()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)
