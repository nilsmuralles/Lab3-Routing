"""Packet envelope per docs/PROTOCOLO.md (cross-group network protocol,
agreed 2026-09-03). Owner: Persona A.

Wire format: NDJSON -- one compact JSON object per line, terminated by "\n".
Addresses (`from`/`to`) are "host:port" strings, not local node letters.
There is no top-level `id`; the packet's logical identity is the `msg_id`
header (msg_id, checksum, t0, via, trace are single-key header objects, see
header_get/header_set below).
"""
from __future__ import annotations

import hashlib
import json
import uuid
import zlib
from typing import Any

VERSION = 1

# Closed per docs/PROTOCOLO.md section "Envelope común" / "Tipos de paquete":
# "El conjunto de tipos se limita a los cuatro definidos arriba." No ERROR/ACK.
KNOWN_PROTO = {"lsr", "dijkstra", "flooding"}
KNOWN_TYPE = {"hello", "echo", "info", "message"}

# `version` and `headers` are intentionally NOT in here: a missing/wrong
# version must never cause rejection (section "Checksum"), and a packet
# missing headers is still structurally parseable -- we just treat it as [].
REQUIRED_FIELDS = ("proto", "type", "from", "to", "ttl", "payload")


def canonical_bytes(payload: Any) -> bytes:
    """Canonical serialization used for the checksum: raw UTF-8 text for a
    string payload (no quotes), or sort-keys/compact JSON for dict/list."""
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_checksum(payload: Any) -> str:
    return format(zlib.crc32(canonical_bytes(payload)) & 0xFFFFFFFF, "08x")


def header_get(headers: list, key: str) -> Any:
    for h in headers or []:
        if isinstance(h, dict) and key in h:
            return h[key]
    return None


def header_set(headers: list, key: str, value: Any) -> list:
    """Returns a new headers list with `key` set to `value` (replacing any
    existing entry for that key)."""
    out = [h for h in (headers or []) if not (isinstance(h, dict) and key in h)]
    out.append({key: value})
    return out


def msg_id(pkt: dict) -> str | None:
    return header_get(pkt.get("headers") or [], "msg_id")


def dedup_key(pkt: dict) -> str:
    """The identifier used for loop/duplicate suppression: msg_id if present,
    else a hash of (from, to, type, payload) -- TTL is deliberately excluded
    since it changes on every hop."""
    mid = msg_id(pkt)
    if mid:
        return mid
    basis = json.dumps(
        [pkt.get("from"), pkt.get("to"), pkt.get("type"), pkt.get("payload")],
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


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
    """`id`, if given, seeds the msg_id header (kept for call-site
    compatibility with earlier code); otherwise a uuid4 is generated."""
    hdrs = list(headers) if headers is not None else []
    if header_get(hdrs, "msg_id") is None:
        hdrs = header_set(hdrs, "msg_id", id if id is not None else uuid.uuid4().hex)
    hdrs = header_set(hdrs, "checksum", compute_checksum(payload))
    return {
        "version": VERSION,
        "proto": proto,
        "type": type,
        "from": frm,
        "to": to,
        "ttl": ttl,
        "headers": hdrs,
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
    if len(line.encode("utf-8")) > 65536:
        return None
    if not validate(pkt):
        return None
    pkt.setdefault("version", VERSION)
    pkt.setdefault("headers", [])
    # PROTOCOLO.md: some peers still put the packet's logical id in a
    # top-level `id` instead of the msg_id header -- fold it in so dedup and
    # LSP identity work uniformly.
    top_id = pkt.get("id")
    if header_get(pkt["headers"], "msg_id") is None and isinstance(top_id, str) and top_id:
        pkt["headers"] = header_set(pkt["headers"], "msg_id", top_id)
    return pkt


def validate(pkt: dict) -> bool:
    if not isinstance(pkt, dict):
        return False
    if not all(field in pkt for field in REQUIRED_FIELDS):
        return False
    if pkt["proto"] not in KNOWN_PROTO:
        return False
    if not isinstance(pkt["type"], str) or pkt["type"] != pkt["type"].lower():
        return False
    if pkt["type"] not in KNOWN_TYPE:
        return False
    if not isinstance(pkt["from"], str) or not pkt["from"]:
        return False
    if not isinstance(pkt["to"], str) or not pkt["to"]:
        return False
    if isinstance(pkt["ttl"], bool) or not isinstance(pkt["ttl"], int):
        return False
    if "headers" in pkt and not isinstance(pkt["headers"], list):
        return False
    # version is intentionally not validated -- an absent or non-1 version
    # must be logged, never used to reject the packet.
    return True
