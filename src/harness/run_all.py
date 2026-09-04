"""Launch the 8 local nodes from config/topology.json, send a test
'message' A -> G and verify the route taken. Owner: Persona D.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .. import envelope


NODES = tuple("ABCDEFGH")
DELIVERY_MARKER = "mensaje entregado"
ORIGIN_LETTER = "A"
DEST_LETTER = "G"


async def _read_output(node_id: str, stream: asyncio.StreamReader, lines: list[str]) -> None:
    while line := await stream.readline():
        text = f"{node_id} | {line.decode(errors='replace').rstrip()}"
        lines.append(text)
        print(text, flush=True)


async def _connect_and_send(host: str, port: int, packet: dict, timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.write(envelope.serialize(packet).encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        except (ConnectionError, OSError):
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(f"could not connect to A at {host}:{port}")
            await asyncio.sleep(0.2)


async def _wait_with_process_checks(
    processes: list[asyncio.subprocess.Process], seconds: float
) -> bool:
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        if any(process.returncode is not None for process in processes):
            return False
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return True
        await asyncio.sleep(min(0.2, remaining))


def _load_node_address(root: Path, letter: str) -> tuple[str, int, str]:
    """Returns (listen_host_to_dial, listen_port, node_id_address) for the
    given letter's config -- node_id is now an address ("host:port") per
    PROTOCOLO.md, not the bare letter."""
    cfg = json.loads((root / "config" / f"{letter}.json").read_text(encoding="utf-8"))
    listen = cfg["listen"]
    host = "127.0.0.1" if listen["host"] == "0.0.0.0" else listen["host"]
    return host, listen["port"], cfg["node_id"]


async def run_all(convergence_sec: float, delivery_timeout: float) -> int:
    root = Path(__file__).resolve().parents[2]
    processes: list[asyncio.subprocess.Process] = []
    output: list[str] = []
    readers: list[asyncio.Task] = []
    try:
        print("Starting nodes A B C D E F G H...", flush=True)
        for node_id in NODES:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "src.node", "--config", f"config/{node_id}.json",
                cwd=root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            processes.append(process)
            readers.append(asyncio.create_task(_read_output(node_id, process.stdout, output)))

        print(f"Waiting {convergence_sec:g}s for LSR convergence...", flush=True)
        if not await _wait_with_process_checks(processes, convergence_sec):
            print("Node process exited during convergence", flush=True)
            return 1

        origin_host, origin_port, origin_addr = _load_node_address(root, ORIGIN_LETTER)
        _, _, dest_addr = _load_node_address(root, DEST_LETTER)

        packet = envelope.make(
            proto="lsr", type="message", frm=origin_addr, to=dest_addr, ttl=16,
            payload="LSR harness test",
        )
        print(f"Sending test message {origin_addr} -> {dest_addr}", flush=True)
        await _connect_and_send(origin_host, origin_port, packet, delivery_timeout)

        deadline = asyncio.get_running_loop().time() + delivery_timeout
        while not any(f"{DEST_LETTER} |" in line and DELIVERY_MARKER in line for line in output):
            if any(process.returncode is not None for process in processes):
                print("Node process exited before message delivery", flush=True)
                return 1
            if asyncio.get_running_loop().time() >= deadline:
                print(f"Message delivery failed: {DEST_LETTER} did not log a delivery", flush=True)
                return 1
            await asyncio.sleep(0.1)

        delivery = next(
            line for line in output
            if f"{DEST_LETTER} |" in line and DELIVERY_MARKER in line
        )
        print(f"Message delivered successfully: {delivery}", flush=True)
        return 0
    finally:
        for process in processes:
            if process.returncode is None:
                process.terminate()
        await asyncio.gather(*(process.wait() for process in processes), return_exceptions=True)
        for task in readers:
            task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all eight local LSR nodes")
    parser.add_argument("--convergence", type=float, default=float(os.environ.get("LSR_CONVERGENCE_SEC", "4")))
    parser.add_argument("--delivery-timeout", type=float, default=5.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_all(args.convergence, args.delivery_timeout)))


if __name__ == "__main__":
    main()
