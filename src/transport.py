from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from . import envelope

logger = logging.getLogger(__name__)
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

        self._server: asyncio.base_events.Server | None = None
        self._writers: dict[str, asyncio.StreamWriter] = {}
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
        writer = self._writers.get(neighbor_id)
        if writer is None:
            return False
        lock = self._locks.setdefault(neighbor_id, asyncio.Lock())
        data = envelope.serialize(pkt).encode("utf-8")
        try:
            async with lock:
                writer.write(data)
                await writer.drain()
            return True
        except (ConnectionError, OSError):
            self._writers.pop(neighbor_id, None)
            return False

    async def stop(self) -> None:
        for task in self._reconnect_tasks.values():
            task.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in self._writers.values():
            writer.close()

    async def _handle_incoming(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                pkt = envelope.parse(line.decode("utf-8"))
                if pkt is None:
                    logger.debug("%s: dropped malformed packet from %s", self.node_id, peer)
                    continue
                from_id = pkt.get("from", "")
                if self.on_packet is not None:
                    await self.on_packet(pkt, from_id)
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _maintain_connection(self, node_id: str) -> None:
        host, port = self.neighbors[node_id]
        delay = 1.0
        while True:
            try:
                _, writer = await asyncio.open_connection(host, port)
                self._writers[node_id] = writer
                delay = 1.0
                logger.info("%s: connected to %s (%s:%d)", self.node_id, node_id, host, port)
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._writers.pop(node_id, None)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)
