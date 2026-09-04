import asyncio

from src.envelope import header_get, make
from src.healthcheck import HealthCheck
from src.neighbors import NeighborTable

CFG = [
    {"node_id": "B", "host": "127.0.0.1", "port": 5002, "cost": 7},
    {"node_id": "C", "host": "127.0.0.1", "port": 5003, "cost": 3},
]

def run(coro):
    return asyncio.run(coro)

class FakeTransport:
    def __init__(self, node_id="A", port=5001):
        self.node_id = node_id
        self.port = port
        self.sent: list[tuple[str, dict]] = []

    async def send(self, neighbor_id, pkt):
        self.sent.append((neighbor_id, pkt))
        return True

def make_hc(max_failures=3):
    tr = FakeTransport()
    nt = NeighborTable([dict(c) for c in CFG])
    params = {"hello_interval_sec": 0.01, "hello_max_failures": max_failures}
    return tr, nt, HealthCheck(tr, nt, params, "lsr")

def test_threshold_propagated_to_table():
    _, nt, _ = make_hc(max_failures=5)
    assert nt.max_failures == 5

def test_hello_to_all_neighbors():
    tr, _, hc = make_hc()
    run(hc._tick())
    run(hc._tick())
    b_hellos = [p for nid, p in tr.sent if nid == "B"]
    assert len(b_hellos) == 2
    assert [p["type"] for p in b_hellos] == ["hello", "hello"]
    assert all(p["ttl"] == 1 and p["proto"] == "lsr" for p in b_hellos)
    assert all(p["payload"]["listen_port"] == 5001 for p in b_hellos)
    assert header_get(b_hellos[0]["headers"], "msg_id")
    # Each hello gets its own msg_id (used to match its echo).
    assert header_get(b_hellos[0]["headers"], "msg_id") != header_get(b_hellos[1]["headers"], "msg_id")
    assert {nid for nid, _ in tr.sent} == {"B", "C"}

def test_handle_hello_produces_echo_with_same_msg_id_and_t0():
    tr, _, hc = make_hc()
    hello = make("lsr", "hello", "B", "A", 1, {"listen_port": 5002})
    run(hc.handle_hello(hello, "B"))
    nid, echo = tr.sent[-1]
    assert nid == "B"
    assert echo["type"] == "echo" and echo["ttl"] == 1
    assert header_get(echo["headers"], "msg_id") == header_get(hello["headers"], "msg_id")

def test_handle_echo_updates_rtt():
    tr, nt, hc = make_hc()
    run(hc._tick())
    pending_mid = hc._pending["B"]["msg_id"]
    echo = make("lsr", "echo", "B", "A", 1, {"listen_port": 5002}, id=pending_mid)
    run(hc.handle_echo(echo, "B"))
    assert nt._n["B"].last_rtt_sec is not None
    assert "B" not in hc._pending

def test_stale_echo_ignored():
    tr, nt, hc = make_hc()
    run(hc._tick())
    echo = make("lsr", "echo", "B", "A", 1, {"listen_port": 5002}, id="not-the-pending-one")
    run(hc.handle_echo(echo, "B"))
    assert nt._n["B"].last_rtt_sec is None
    assert "B" in hc._pending

def test_unanswered_hellos_mark_down():
    tr, nt, hc = make_hc(max_failures=3)
    fired = []
    nt.on_change(lambda: fired.append(1))
    for _ in range(4):
        run(hc._tick())
    assert not nt.is_up("B")
    assert fired
