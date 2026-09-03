import json

from src.dijkstra import DijkstraRouter, compute
from src.neighbors import NeighborTable

GRAPH = {
    "A": {"B": 1, "C": 4},
    "B": {"A": 1, "C": 2, "D": 5},
    "C": {"A": 4, "B": 2, "D": 1},
    "D": {"B": 5, "C": 1},
}


def test_compute_direct_neighbor():
    table = compute(GRAPH, "A")
    assert table["B"] == {"next_hop": "B", "cost": 1}


def test_compute_prefers_cheaper_indirect_path():
    table = compute(GRAPH, "A")
    assert table["C"]["cost"] == 3
    assert table["C"]["next_hop"] == "B"


def test_compute_multi_hop_next_hop_is_first_hop_from_source():
    table = compute(GRAPH, "A")
    assert table["D"]["cost"] == 4
    assert table["D"]["next_hop"] == "B"


def test_compute_excludes_source():
    table = compute(GRAPH, "A")
    assert "A" not in table


def test_compute_unreachable_node_absent():
    graph = {"A": {"B": 1}, "B": {"A": 1}, "Z": {}}
    table = compute(graph, "A")
    assert "Z" not in table


def test_compute_source_not_in_graph_returns_empty():
    assert compute(GRAPH, "Q") == {}


def test_compute_symmetric_from_other_source():
    table = compute(GRAPH, "D")
    assert table["C"] == {"next_hop": "C", "cost": 1}
    assert table["A"]["cost"] == 4
    assert table["A"]["next_hop"] == "C"


def test_dijkstra_router_next_hop_and_static_computation(tmp_path):
    topo_path = tmp_path / "topology.json"
    topo_path.write_text(json.dumps(GRAPH))

    neighbors = NeighborTable([
        {"node_id": "B", "host": "127.0.0.1", "port": 5002, "cost": 1},
        {"node_id": "C", "host": "127.0.0.1", "port": 5003, "cost": 4},
    ])

    router = DijkstraRouter("A", neighbors, str(topo_path))

    assert router.next_hop("C") == "B"
    assert router.next_hop("D") == "B"
    assert router.next_hop("A") is None


def test_dijkstra_router_skips_down_next_hop(tmp_path):
    topo_path = tmp_path / "topology.json"
    topo_path.write_text(json.dumps(GRAPH))

    neighbors = NeighborTable([
        {"node_id": "B", "host": "127.0.0.1", "port": 5002, "cost": 1},
        {"node_id": "C", "host": "127.0.0.1", "port": 5003, "cost": 4},
    ])
    neighbors.max_failures = 1
    neighbors.on_timeout("B")  # marca a B como caido

    router = DijkstraRouter("A", neighbors, str(topo_path))

    assert router.next_hop("C") is None


def test_dijkstra_router_no_route_to_unknown_dest(tmp_path):
    topo_path = tmp_path / "topology.json"
    topo_path.write_text(json.dumps(GRAPH))
    neighbors = NeighborTable([{"node_id": "B", "host": "h", "port": 1, "cost": 1}])
    router = DijkstraRouter("A", neighbors, str(topo_path))
    assert router.next_hop("Z") is None


def test_dijkstra_router_build_local_info_and_on_info_are_noop(tmp_path):
    import asyncio

    topo_path = tmp_path / "topology.json"
    topo_path.write_text(json.dumps(GRAPH))
    neighbors = NeighborTable([{"node_id": "B", "host": "h", "port": 1, "cost": 1}])
    router = DijkstraRouter("A", neighbors, str(topo_path))

    assert router.build_local_info() is None
    asyncio.run(router.on_info({"type": "info"}, "B"))  # no debe lanzar
