from __future__ import annotations

import json
import uuid
from typing import Any

VERSION = 1

ALLOWED_PROTO = {"dijkstra", "flooding", "lsr"}
ALLOWED_TYPE = {"hello", "echo", "message", "info"}

REQUIRED_FIELDS = ("id", "proto", "type", "from", "to", "ttl", "payload")


def make(
    proto: str,
    type: str,
    frm: str,
    to: str,
    ttl: int,
    payload: Any,
    headers: list | None = None,
    id: str | None = None,
) -> dict:
    return {
        "version": VERSION,
        "id": id if id is not None else uuid.uuid4().hex,
        "proto": proto,
        "type": type,
        "from": frm,
        "to": to,
        "ttl": ttl,
        "headers": headers if headers is not None else [],
        "payload": payload,
    }


def serialize(pkt: dict) -> str:
    return json.dumps(pkt, separators=(",", ":")) + "\n"


def parse(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        pkt = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not validate(pkt):
        return None
    pkt.setdefault("version", VERSION)
    pkt.setdefault("headers", [])
    return pkt


def validate(pkt: dict) -> bool:
    if not isinstance(pkt, dict):
        return False
    if not all(field in pkt for field in REQUIRED_FIELDS):
        return False
    if not isinstance(pkt["id"], str) or not pkt["id"]:
        return False
    if pkt["proto"] not in ALLOWED_PROTO:
        return False
    if pkt["type"] not in ALLOWED_TYPE:
        return False
    if not isinstance(pkt["from"], str) or not isinstance(pkt["to"], str):
        return False
    if isinstance(pkt["ttl"], bool) or not isinstance(pkt["ttl"], int):
        return False
    if "headers" in pkt and not isinstance(pkt["headers"], list):
        return False
    if "version" in pkt and (isinstance(pkt["version"], bool) or not isinstance(pkt["version"], int)):
        return False
    return True
