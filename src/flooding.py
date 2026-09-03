# Flood distribution + pure-flooding router.
from __future__ import annotations


async def flood(transport, neighbors, pkt: dict, exclude_id: str | None) -> None:
    ttl = pkt.get("ttl")
    if not isinstance(ttl, int) or isinstance(ttl, bool):
        return
    new_ttl = ttl - 1
    if new_ttl <= 0:
        return

    out = dict(pkt)
    out["ttl"] = new_ttl
    out["from"] = transport.node_id

    for neighbor_id in neighbors.active():
        if neighbor_id == exclude_id:
            continue
        await transport.send(neighbor_id, out)


class FloodingRouter:

    def __init__(self, node_id, neighbors) -> None:
        self.node_id = node_id
        self.neighbors = neighbors

    def next_hop(self, dest: str) -> str | None:
        
        return None

    async def on_info(self, pkt: dict, from_id: str) -> None:
        return None

    def build_local_info(self) -> dict | None:
        return None

    def recompute(self) -> None:
        # No hay tabla que recalcular.
        return None
