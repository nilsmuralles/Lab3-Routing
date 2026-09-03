from src.neighbors import NeighborTable

CFG = [
    {"node_id": "B", "host": "127.0.0.1", "port": 5002, "cost": 7},
    {"node_id": "C", "host": "127.0.0.1", "port": 5003, "cost": 3},
]

def make_table(max_failures=3):
    t = NeighborTable([dict(c) for c in CFG])
    t.max_failures = max_failures
    return t

def test_all_and_active_start_equal():
    t = make_table()
    assert sorted(t.all()) == ["B", "C"]
    assert sorted(t.active()) == ["B", "C"]

def test_costs_only_active():
    t = make_table(max_failures=1)
    assert t.costs() == {"B": 7.0, "C": 3.0}
    t.on_timeout("C")
    assert t.costs() == {"B": 7.0}
    assert t.active() == ["B"]

def test_on_echo_resets_failures():
    t = make_table(max_failures=3)
    t.on_timeout("B")
    t.on_timeout("B")
    t.on_echo("B", 0.01)
    assert t.is_up("B")
    t.on_timeout("B")
    t.on_timeout("B")
    assert t.is_up("B")

def test_threshold_marks_down_and_fires_change():
    t = make_table(max_failures=3)
    calls = []
    t.on_change(lambda: calls.append(1))
    assert t.on_timeout("B") is False
    assert t.on_timeout("B") is False
    assert t.on_timeout("B") is True
    assert not t.is_up("B")
    assert len(calls) == 1
    assert t.on_timeout("B") is False
    assert len(calls) == 1

def test_recovery_fires_change():
    t = make_table(max_failures=1)
    calls = []
    t.on_change(lambda: calls.append(1))
    t.on_timeout("B")
    assert not t.is_up("B")
    t.on_echo("B", 0.02)
    assert t.is_up("B")
    assert t._n["B"].last_rtt_sec == 0.02
    assert len(calls) == 2

def test_unknown_neighbor():
    t = make_table()
    assert t.is_up("Z") is False
    assert t.on_timeout("Z") is False
    t.on_echo("Z", 0.1)  # no raise
