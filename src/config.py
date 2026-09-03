from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

@dataclass
class NodeConfig:
    node_id: str
    host: str
    port: int
    mode: str
    neighbors: list[dict[str, Any]]
    params: dict[str, Any]
    topology_file: str | None = None


def load(path: str) -> NodeConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    listen = raw["listen"]
    return NodeConfig(
        node_id=raw["node_id"],
        host=listen["host"],
        port=listen["port"],
        mode=raw["mode"],
        neighbors=raw["neighbors"],
        params=raw["params"],
        # Only required when mode == "dijkstra" per the reference spec (15.1);
        # optional for "flooding"/"lsr".
        topology_file=raw.get("topology_file"),
    )
