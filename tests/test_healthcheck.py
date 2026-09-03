import asyncio

from src.healthcheck import HealthCheck
from src.neighbors import NeighborTable

CFG = [
    {"node_id": "B", "host": "127.0.0.1", "port": 5002, "cost": 7},
    {"node_id": "C", "host": "127.0.0.1", "port": 5003, "cost": 3},
]

def run(coro):
    return asyncio.run(coro)

class FakeTransport:
    def __init__(self, node_id="A"):
        self.node_id = node_id
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

def test_hello_to_all_neighbors_monotonic_seq():
    tr, _, hc = make_hc()
    run(hc._tick())
    run(hc._tick())
    b_hellos = [p for nid, p in tr.sent if nid == "B"]
    assert len(b_hellos) == 2
    assert [p["type"] for p in b_hellos] == ["hello", "hello"]
    assert [p["payload"]["seq"] for p in b_hellos] == [1, 2]
    assert all(p["ttl"] == 1 and p["proto"] == "lsr" for p in b_hellos)
    assert "sent_at" in b_hellos[0]["payload"]
    assert {nid for nid, _ in tr.sent} == {"B", "C"}

def test_handle_hello_produces_echo():
    tr, _, hc = make_hc()
    hello = {"type": "hello", "payload": {"seq": 42, "sent_at": 100.0}}
    run(hc.handle_hello(hello, "B"))
    nid, echo = tr.sent[-1]
    assert nid == "B"
    assert echo["type"] == "echo" and echo["ttl"] == 1
    assert echo["payload"]["seq"] == 42
    assert echo["payload"]["sent_at"] == 100.0
    assert "echoed_at" in echo["payload"]

def test_handle_echo_updates_rtt():
    tr, nt, hc = make_hc()
    run(hc._tick())
    seq = hc._pending["B"]["seq"]
    sent_at = hc._pending["B"]["sent_at"]
    echo = {"type": "echo", "payload": {"seq": seq, "sent_at": sent_at}}
    run(hc.handle_echo(echo, "B"))
    assert nt._n["B"].last_rtt_sec is not None
    assert "B" not in hc._pending

def test_stale_echo_ignored():
    tr, nt, hc = make_hc()
    run(hc._tick())
    echo = {"type": "echo", "payload": {"seq": 999, "sent_at": 0.0}}
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
