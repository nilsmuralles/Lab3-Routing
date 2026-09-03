# Neighbor liveness via periodic hello/echo.

from __future__ import annotations

class HealthCheck:
    def __init__(self, transport, neighbors, params, proto) -> None:
        raise NotImplementedError

    async def run(self) -> None:
        raise NotImplementedError

    async def handle_hello(self, pkt: dict, from_id: str) -> None:
        raise NotImplementedError

    async def handle_echo(self, pkt: dict, from_id: str) -> None:
        raise NotImplementedError
