import time

from src.dedup import DedupCache

def test_add_and_seen():
    c = DedupCache(ttl_sec=60)
    assert c.seen("x") is False
    c.add("x")
    assert c.seen("x") is True

def test_add_is_idempotent():
    c = DedupCache(ttl_sec=60)
    c.add("x")
    c.add("x")
    assert c.seen("x") is True

def test_unseen_id():
    c = DedupCache(ttl_sec=60)
    c.add("a")
    assert c.seen("b") is False

def test_expiration(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = DedupCache(ttl_sec=5)
    c.add("x")
    now[0] = 1004.0
    assert c.seen("x") is True
    now[0] = 1006.0
    assert c.seen("x") is False
