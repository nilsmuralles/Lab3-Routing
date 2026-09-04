"""Manual helper: send one 'message' packet into a running node over TCP.

Usage:
    python -m scripts.send_message --host 127.0.0.1 --port 5001 \
        --from A --to G --text "hola desde A"

--host/--port is the origin node's OWN listen address (where you connect to
inject the message), --from is that node's node_id, --to is the destination
node_id it should route towards.
"""
from __future__ import annotations

import argparse
import asyncio

from src import envelope


async def send(host: str, port: int, frm: str, to: str, text: str, ttl: int) -> None:
    pkt = envelope.make("lsr", "message", frm, to, ttl, text)
    _, writer = await asyncio.open_connection(host, port)
    writer.write(envelope.serialize(pkt).encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()
    print(f"sent: {pkt}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test message into a running node")
    parser.add_argument("--host", required=True, help="listen host of the origin node")
    parser.add_argument("--port", type=int, required=True, help="listen port of the origin node")
    parser.add_argument("--from", dest="frm", required=True, help="origin node_id")
    parser.add_argument("--to", required=True, help="destination node_id")
    parser.add_argument("--text", default="mensaje de prueba")
    parser.add_argument("--ttl", type=int, default=8)
    args = parser.parse_args()
    asyncio.run(send(args.host, args.port, args.frm, args.to, args.text, args.ttl))


if __name__ == "__main__":
    main()
