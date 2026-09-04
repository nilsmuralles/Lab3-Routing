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
    neighbors = raw["neighbors"]
    topology_file = raw.get("topology_file")
    if raw["mode"] == "lsr" and topology_file:
        try:
            with open(topology_file, "r", encoding="utf-8") as f:
                topology = json.load(f)
        except (OSError, json.JSONDecodeError):
            topology = None
        if isinstance(topology, dict) and raw["node_id"] in topology:
            configured = {item["node_id"]: item for item in neighbors}
            neighbors = [
                {
                    "node_id": neighbor_id,
                    "host": configured.get(neighbor_id, {}).get("host", "127.0.0.1"),
                    "port": configured.get(
                        neighbor_id, {}
                    ).get("port", 5000 + ord(neighbor_id) - ord("A") + 1),
                    "cost": cost,
                }
                for neighbor_id, cost in topology[raw["node_id"]].items()
            ]
    return NodeConfig(
        node_id=raw["node_id"],
        host=listen["host"],
        port=listen["port"],
        mode=raw["mode"],
        neighbors=neighbors,
        params=raw["params"],
        # Only required when mode == "dijkstra" per the reference spec (15.1);
        # optional for "flooding"/"lsr".
        topology_file=topology_file,
    )
