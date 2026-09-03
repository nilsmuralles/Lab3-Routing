
from __future__ import annotations

from typing import Callable

DEFAULT_MAX_FAILURES = 3

class _Neighbor:
    __slots__ = ("node_id", "host", "port", "cost", "is_up",
                 "consecutive_failures", "last_rtt_sec")

    def __init__(self, cfg: dict) -> None:
        self.node_id = cfg["node_id"]
        self.host = cfg.get("host")
        self.port = cfg.get("port")
        self.cost = float(cfg.get("cost", 1))
        self.is_up = True
        self.consecutive_failures = 0
        self.last_rtt_sec: float | None = None

class NeighborTable:
    def __init__(self, neighbors_cfg: list[dict]) -> None:
        self._n: dict[str, _Neighbor] = {
            c["node_id"]: _Neighbor(c) for c in neighbors_cfg
        }
        self._on_change: list[Callable[[], None]] = []
        self.max_failures = DEFAULT_MAX_FAILURES

    def all(self) -> list[str]:
        return list(self._n)

    def active(self) -> list[str]:
        return [nid for nid, n in self._n.items() if n.is_up]

    def is_up(self, node_id: str) -> bool:
        n = self._n.get(node_id)
        return bool(n and n.is_up)

    def costs(self) -> dict[str, float]:
        return {nid: n.cost for nid, n in self._n.items() if n.is_up}

    def on_echo(self, neighbor_id: str, rtt_sec: float) -> None:
        n = self._n.get(neighbor_id)
        if n is None:
            return
        n.consecutive_failures = 0
        n.last_rtt_sec = rtt_sec
        if not n.is_up:
            n.is_up = True
            self._fire_change()

    def on_timeout(self, neighbor_id: str) -> bool:
        n = self._n.get(neighbor_id)
        if n is None:
            return False
        n.consecutive_failures += 1
        if n.is_up and n.consecutive_failures >= self.max_failures:
            n.is_up = False
            self._fire_change()
            return True
        return False

    def on_change(self, cb: Callable[[], None]) -> None:
        self._on_change.append(cb)

    def _fire_change(self) -> None:
        for cb in self._on_change:
            cb()
