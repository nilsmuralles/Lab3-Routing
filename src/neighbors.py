# Neighbor table with liveness tracking.

from __future__ import annotations
from typing import Callable

class NeighborTable:
    def __init__(self, neighbors_cfg: list[dict]) -> None:
        raise NotImplementedError

    def all(self) -> list[str]:
        raise NotImplementedError

    def active(self) -> list[str]:
        raise NotImplementedError

    def is_up(self, node_id: str) -> bool:
        raise NotImplementedError

    def costs(self) -> dict[str, float]:
        raise NotImplementedError

    def on_echo(self, neighbor_id: str, rtt_sec: float) -> None:
        raise NotImplementedError

    def on_timeout(self, neighbor_id: str) -> bool:
        raise NotImplementedError

    def on_change(self, cb: Callable[[], None]) -> None:
        raise NotImplementedError
