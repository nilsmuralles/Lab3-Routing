# Node bootstrap: load config, start Transport, wire Forwarder + HealthCheck + Router.
from __future__ import annotations

import argparse
import asyncio
import logging

from . import config as config_module
from .dedup import DedupCache
from .dijkstra import DijkstraRouter
from .flooding import FloodingRouter
from .forwarding import Forwarder
from .healthcheck import HealthCheck
from .lsr import LSRRouter
from .neighbors import NeighborTable
from .transport import Transport

logger = logging.getLogger(__name__)


def _build_router(mode: str, node_id: str, neighbors: NeighborTable, cfg: config_module.NodeConfig):
    if mode == "flooding":
        return FloodingRouter(node_id, neighbors)
    if mode == "dijkstra":
        return DijkstraRouter(node_id, neighbors, cfg.topology_file)
    if mode == "lsr":
        return LSRRouter(node_id, neighbors)
    raise ValueError(f"unknown mode: {mode!r}")


async def run(config_path: str) -> None:
    cfg = config_module.load(config_path)
    logging.basicConfig(
        level=cfg.params.get("log_level", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    neighbor_addrs = {n["node_id"]: (n["host"], n["port"]) for n in cfg.neighbors}
    transport = Transport(cfg.node_id, cfg.host, cfg.port, neighbor_addrs)

    neighbors = NeighborTable(cfg.neighbors)
    dedup = DedupCache(cfg.params["dedup_cache_ttl_sec"])
    router = _build_router(cfg.mode, cfg.node_id, neighbors, cfg)
    forwarder = Forwarder(cfg.node_id, transport, router, neighbors, dedup, cfg.params)
    # `proto` on the wire must be the node's active mode (dijkstra/flooding/lsr),
    # per the reference spec section 4.4 -- not a made-up protocol name.
    healthcheck = HealthCheck(transport, neighbors, cfg.params, cfg.mode)

    # Wiring convention: Forwarder's __init__ signature is frozen and does
    # not take a HealthCheck, so it is attached here for handle() to
    # delegate 'hello'/'echo' packets to.
    forwarder.healthcheck = healthcheck

    async def on_packet(pkt: dict, from_id: str) -> None:
        await forwarder.handle(pkt, from_id)

    transport.on_packet = on_packet

    await transport.start()
    logger.info("%s: node up (mode=%s)", cfg.node_id, cfg.mode)

    tasks = [asyncio.create_task(healthcheck.run())]
    if hasattr(router, "run"):
        tasks.append(asyncio.create_task(router.run()))

    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a routing-lab node")
    parser.add_argument("--config", required=True, help="path to config/<NODE>.json")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
