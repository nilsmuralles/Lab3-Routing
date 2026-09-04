from src.envelope import (
    compute_checksum, dedup_key, header_get, header_set, make, msg_id,
    parse, serialize, validate,
)

def test_checksum_text_vector():
    assert compute_checksum("hola G") == "0bded535"

def test_checksum_object_vector():
    payload = {
        "origin": "10.0.0.1:5000", "seq": 7,
        "neighbors": [{"id": "10.0.0.2:5000", "weight": 4.8}],
    }
    assert compute_checksum(payload) == "cbd08356"

def test_header_get_and_set():
    headers = [{"msg_id": "a"}, {"checksum": "x"}]
    assert header_get(headers, "msg_id") == "a"
    assert header_get(headers, "missing") is None
    updated = header_set(headers, "checksum", "y")
    assert header_get(updated, "checksum") == "y"
    assert len(updated) == 2  # replaced, not duplicated

def test_make_sets_defaults():
    pkt = make("lsr", "message", "10.0.0.1:5000", "10.0.0.7:5000", 16, "hola G")
    assert pkt["version"] == 1
    assert pkt["proto"] == "lsr"
    assert pkt["type"] == "message"
    assert pkt["from"] == "10.0.0.1:5000"
    assert pkt["to"] == "10.0.0.7:5000"
    assert pkt["ttl"] == 16
    assert header_get(pkt["headers"], "checksum") == "0bded535"
    assert msg_id(pkt)

def test_make_respects_explicit_id():
    pkt = make("lsr", "message", "A", "B", 16, "hola", id="fixed-id")
    assert msg_id(pkt) == "fixed-id"

def test_serialize_is_single_line_json():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    line = serialize(pkt)
    assert line.endswith("\n")
    assert line.count("\n") == 1

def test_serialize_then_parse_roundtrip():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    line = serialize(pkt)
    assert parse(line) == pkt

def test_parse_invalid_json_returns_none():
    assert parse("not json") is None
    assert parse("") is None
    assert parse("   \n") is None

def test_parse_oversized_line_returns_none():
    huge = "x" * 70000
    pkt = make("lsr", "message", "A", "B", 16, huge)
    assert parse(serialize(pkt)) is None

def test_parse_missing_required_field_returns_none():
    assert parse('{"proto": "lsr", "type": "message"}\n') is None

def test_parse_accepts_missing_or_wrong_version():
    raw = '{"proto":"lsr","type":"hello","from":"A","to":"B","ttl":1,"payload":{}}\n'
    pkt = parse(raw)
    assert pkt is not None
    assert pkt["version"] == 1

    raw2 = '{"version":99,"proto":"lsr","type":"hello","from":"A","to":"B","ttl":1,"headers":[],"payload":{}}\n'
    pkt2 = parse(raw2)
    assert pkt2 is not None
    assert pkt2["version"] == 99  # logged elsewhere, never rejected here

def test_validate_rejects_unknown_proto():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    pkt["proto"] = "dvr"
    assert validate(pkt) is False

def test_validate_rejects_unknown_type():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    pkt["type"] = "ack"
    assert validate(pkt) is False

def test_validate_rejects_uppercase_type():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    pkt["type"] = "MESSAGE"
    assert validate(pkt) is False

def test_validate_rejects_wrong_ttl_type():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    pkt["ttl"] = "8"
    assert validate(pkt) is False

def test_validate_rejects_non_list_headers():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    pkt["headers"] = "not-a-list"
    assert validate(pkt) is False

def test_validate_accepts_broadcast_to_star():
    pkt = make("lsr", "info", "10.0.0.1:5000", "*", 16, {"origin": "10.0.0.1:5000", "seq": 1, "neighbors": []})
    assert validate(pkt) is True

def test_dedup_key_prefers_msg_id():
    pkt = make("lsr", "message", "A", "B", 16, "hola", id="fixed")
    assert dedup_key(pkt) == "fixed"

def test_dedup_key_ignores_ttl_when_falling_back():
    pkt = make("lsr", "message", "A", "B", 16, "hola")
    del pkt["headers"]  # no msg_id at all -> falls back to content hash
    pkt["headers"] = []
    pkt2 = dict(pkt)
    pkt2["ttl"] = pkt["ttl"] - 1  # simulate one hop
    assert dedup_key(pkt) == dedup_key(pkt2)
