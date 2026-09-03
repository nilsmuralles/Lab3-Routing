from src.envelope import make, parse, serialize, validate

def test_make_sets_defaults():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    assert pkt["version"] == 1
    assert pkt["proto"] == "lsr"
    assert pkt["type"] == "message"
    assert pkt["from"] == "A"
    assert pkt["to"] == "B"
    assert pkt["ttl"] == 8
    assert pkt["headers"] == []
    assert isinstance(pkt["id"], str) and pkt["id"]

def test_make_respects_explicit_headers_and_id():
    pkt = make(
        "lsr", "message", "A", "B", 8, "hola", headers=[{"hops": ["A"]}], id="fixed-id"
    )
    assert pkt["headers"] == [{"hops": ["A"]}]
    assert pkt["id"] == "fixed-id"

def test_serialize_is_single_line_json():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    line = serialize(pkt)
    assert line.endswith("\n")
    assert line.count("\n") == 1

def test_serialize_then_parse_roundtrip():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    line = serialize(pkt)
    assert parse(line) == pkt

def test_parse_invalid_json_returns_none():
    assert parse("not json") is None
    assert parse("") is None
    assert parse("   \n") is None

def test_parse_missing_required_field_returns_none():
    assert parse('{"proto": "lsr", "type": "message"}\n') is None

def test_parse_fills_missing_optional_fields_with_defaults():
    # "version" and "headers" are optional per the reference spec (4.2/4.3).
    raw = '{"id": "x", "proto": "lsr", "type": "hello", "from": "A", "to": "B", "ttl": 1, "payload": {}}\n'
    pkt = parse(raw)
    assert pkt is not None
    assert pkt["version"] == 1
    assert pkt["headers"] == []

def test_validate_rejects_wrong_ttl_type():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    pkt["ttl"] = "8"
    assert validate(pkt) is False

def test_validate_rejects_non_list_headers():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    pkt["headers"] = "not-a-list"
    assert validate(pkt) is False

def test_validate_rejects_unknown_proto():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    pkt["proto"] = "not-a-mode"
    assert validate(pkt) is False

def test_validate_rejects_unknown_type():
    pkt = make("lsr", "message", "A", "B", 8, "hola")
    pkt["type"] = "not-a-type"
    assert validate(pkt) is False

def test_validate_accepts_broadcast_to_star():
    pkt = make("lsr", "info", "A", "*", 8, {"origin": "A", "seq": 1, "neighbors": {}})
    assert validate(pkt) is True

def test_validate_accepts_well_formed_packet():
    pkt = make("lsr", "hello", "A", "B", 1, {"seq": 1, "sent_at": 0.0})
    assert validate(pkt) is True