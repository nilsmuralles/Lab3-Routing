# Observador de recepcion: imprime QUIEN nos habla y QUE manda, y una tabla
# que se reimprime solo cuando la red cambia (nuevo vecino/nodo o cambio de
# estado) -- no en cada hello/echo periodico.
from __future__ import annotations

import functools
import time

from . import envelope

# stdout is block-buffered when it is not a TTY (e.g. redirected to a file or
# captured by the harness); flush so the who/what and the table are never lost
# if the process is killed.
_p = functools.partial(print, flush=True)


def _bucket(types: dict[str, int]) -> str:
    order = ["hello", "echo", "info", "message"]
    parts = [f"{t}:{types[t]}" for t in order if types.get(t)]
    parts += [f"{t}:{c}" for t, c in types.items() if t not in order]
    return " ".join(parts) or "-"


class RxMonitor:
    def __init__(self, node_id: str, neighbors, default_port=None) -> None:
        self.node_id = node_id
        self.neighbors = neighbors
        self.default_port = default_port
        self._start = time.monotonic()
        # from-address -> {"first": float, "last": float, "count": int, "types": dict}
        self._sources: dict[str, dict] = {}
        self._origins: set[str] = set()      # origenes de LSP vistos
        self._last_render: tuple = ()
        if hasattr(neighbors, "on_change"):
            neighbors.on_change(lambda: self._render("cambio de estado de un vecino"))

    # -- API llamada por el transporte por cada paquete recibido --------------

    def observe(self, pkt: dict, peer, direction: str) -> None:
        frm = pkt.get("from") or str(peer)
        ptype = pkt.get("type")
        now = self._elapsed()

        # A message we injected into our own node loops back with from == us.
        self_sent = frm == self.node_id

        s = self._sources.get(frm)
        is_new = s is None and not self_sent
        if s is None and not self_sent:
            s = {"first": now, "count": 0, "types": {}}
            self._sources[frm] = s
        if s is not None:
            s["count"] += 1
            s["last"] = now
            s["types"][ptype] = s["types"].get(ptype, 0) + 1

        if is_new:
            _p(
                f"[{self.node_id}] << nueva conexion: {frm} "
                f"(primer paquete: {ptype}, {direction.strip()})"
            )

        new_origin = False
        origin = None
        if ptype == "info" and isinstance(pkt.get("payload"), dict):
            origin = pkt["payload"].get("origin")
            if isinstance(origin, str) and origin and origin not in self._origins:
                self._origins.add(origin)
                new_origin = origin != self.node_id
                if new_origin:
                    nb = pkt["payload"].get("neighbors")
                    _p(
                        f"[{self.node_id}] << nodo nuevo en la red: {origin} "
                        f"(LSP via {frm}) enlaces={_summarize_neighbors(nb)}"
                    )

        if ptype == "message" and not self_sent:
            self._print_message(pkt, frm)

        # Reimprimir la tabla SOLO cuando la red crece de verdad: un vecino
        # que nos habla por primera vez, o un nodo remoto nuevo. Los hello/
        # echo/LSP periodicos NO reimprimen nada.
        if is_new or new_origin:
            self._render("+" + (frm if is_new else str(origin)))

    # -- tabla ---------------------------------------------------------------

    def print_table(self) -> None:
        self._render("solicitada", force=True)

    def _render(self, reason: str, force: bool = False) -> None:
        snap = {r["node_id"]: r for r in self.neighbors.snapshot()} if hasattr(self.neighbors, "snapshot") else {}

        lines = []
        lines.append(f"  {'nodo':<24} {'rol':<7} {'estado':<6} {'paq':>4}  {'tipos':<26} {'ult(T+)':>8}")
        active = 0
        for nid in sorted(snap):
            r = snap[nid]
            st = self._stats_for(nid)
            estado = "UP" if r["is_up"] else "DOWN"
            if r["is_up"]:
                active += 1
            rtt = "" if r["last_rtt_sec"] is None else f"  rtt={r['last_rtt_sec'] * 1000:.1f}ms"
            paq = st["count"] if st else 0
            tipos = _bucket(st["types"]) if st else "(sin respuesta)"
            ult = f"{st['last']:.0f}s" if st else "-"
            lines.append(f"  {nid:<24} {'vecino':<7} {estado:<6} {paq:>4}  {tipos:<26} {ult:>8}{rtt}")

        remotos = sorted(
            (self._origins | set(self._sources)) - set(snap) - {self.node_id}
        )
        remotos = [f for f in remotos if not self._is_neighbor(f)]
        for f in remotos:
            st = self._sources.get(f)
            if st:
                lines.append(
                    f"  {f:<24} {'remoto':<7} {'-':<6} {st['count']:>4}  {_bucket(st['types']):<26} {st['last']:.0f}s"
                )
            else:
                lines.append(f"  {f:<24} {'remoto':<7} {'-':<6} {'0':>4}  {'(via LSP)':<26} -")

        body = "\n".join(lines)
        # De-dupe on the *shape* of the network (who is here + up/down),
        # ignoring the volatile packet counters, so a burst of triggers in
        # the same instant prints the table once.
        sig = tuple((nid, snap[nid]["is_up"]) for nid in sorted(snap)) + tuple(remotos)
        if sig == self._last_render and not force:
            return
        self._last_render = sig
        total_nodos = len(set(snap) | self._origins | set(self._sources))
        header = (
            f"[{self.node_id}] == conexiones (T+{self._elapsed():.0f}s) · {reason} ==  "
            f"vecinos activos: {active}/{len(snap)} · nodos vistos: {total_nodos}"
        )
        _p(header + "\n" + body)

    # -- helpers -----------------------------------------------------------

    def _elapsed(self) -> float:
        return time.monotonic() - self._start

    def _candidates(self, nid: str):
        yield nid
        if ":" not in nid and self.default_port:
            yield f"{nid}:{self.default_port}"
        if ":" in nid:
            yield nid.rsplit(":", 1)[0]

    def _stats_for(self, nid: str):
        for c in self._candidates(nid):
            if c in self._sources:
                return self._sources[c]
        return None

    def _is_neighbor(self, frm: str) -> bool:
        snap = self.neighbors.snapshot() if hasattr(self.neighbors, "snapshot") else []
        ids = {r["node_id"] for r in snap}
        return any(c in ids for c in self._candidates(frm))

    def _print_message(self, pkt: dict, frm: str) -> None:
        hdrs = pkt.get("headers") or []
        trace = envelope.header_get(hdrs, "trace")
        via = envelope.header_get(hdrs, "via")
        ruta = " -> ".join(trace) if isinstance(trace, list) and trace else "(sin traza)"
        _p(
            f"[{self.node_id}] <<< MENSAJE  de={frm}  via={via or '-'}  "
            f"to={pkt.get('to')}  ttl={pkt.get('ttl')}\n"
            f"                ruta: {ruta}\n"
            f"                texto: {pkt.get('payload')!r}"
        )


def _summarize_neighbors(nb) -> str:
    if isinstance(nb, list):
        out = []
        for e in nb:
            if isinstance(e, dict):
                out.append(f"{e.get('id', e.get('node'))}={e.get('weight', e.get('cost'))}")
        return "{" + ", ".join(out) + "}"
    if isinstance(nb, dict):
        return "{" + ", ".join(f"{k}={v}" for k, v in nb.items()) + "}"
    return str(nb)
