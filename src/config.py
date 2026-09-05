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
    # Address other nodes should use to reach us (PROTOCOLO.md `from` =
    # "IP:puerto del originador"). Defaults to node_id.
    advertise: str = ""


def _addr(host: str | None, port: Any) -> str:
    return f"{host}:{port}" if host and port else ""


def _norm_id(node_id: str | None, host: str | None, port: Any) -> str:
    """The wire identity of a node is its `IP:puerto` address. Accept a
    config that already gives that, or a bare label/host that we complete
    from the neighbor's host/port."""
    if isinstance(node_id, str) and ":" in node_id:
        return node_id
    built = _addr(host, port)
    if built:
        return built
    return node_id or ""


def load(path: str) -> NodeConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    listen = raw["listen"]
    port = listen["port"]
    default_port = raw.get("default_port") or port

    # Our own wire identity: an explicit advertise_host wins (LAN test),
    # then an address-shaped node_id, then the listen host:port.
    advertise_host = raw.get("advertise_host")
    if advertise_host:
        node_id = f"{advertise_host}:{raw.get('advertise_port', port)}"
    else:
        node_id = _norm_id(raw.get("node_id"), listen.get("host"), port)

    neighbors = [
        {**n, "node_id": _norm_id(n.get("node_id"), n.get("host"), n.get("port") or default_port)}
        for n in raw["neighbors"]
    ]

    topology_file = raw.get("topology_file")
    if raw["mode"] == "lsr" and topology_file:
        try:
            with open(topology_file, "r", encoding="utf-8") as f:
                topology = json.load(f)
        except (OSError, json.JSONDecodeError):
            topology = None
        topo_key = node_id if isinstance(topology, dict) and node_id in topology else raw.get("node_id")
        if isinstance(topology, dict) and topo_key in topology:
            configured = {item["node_id"]: item for item in neighbors}
            derived = []
            for neighbor_id, cost in topology[topo_key].items():
                known = configured.get(neighbor_id)
                if known is not None:
                    derived.append({**known, "cost": cost})
                    continue
                host, _, p = neighbor_id.rpartition(":")
                if not host or not p.isdigit():
                    continue
                derived.append({
                    "node_id": neighbor_id, "host": host, "port": int(p), "cost": cost,
                })
            neighbors = derived

    params = dict(raw["params"])
    params.setdefault("default_port", default_port)

    return NodeConfig(
        node_id=node_id,
        host=listen["host"],
        port=port,
        mode=raw["mode"],
        neighbors=neighbors,
        params=params,
        topology_file=topology_file,
        advertise=node_id,
    )
