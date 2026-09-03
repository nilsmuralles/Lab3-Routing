# Lab3-Routing

Protocolo de enrutamiento sobre TCP con NDJSON. 8 nodos (`A`..`H`) 
que se comunican por sockets persistentes, soportando 3 modos: `flooding`, 
`dijkstra` (topología estática) y `lsr` (link-state con flooding de LSPs).

## Estructura

```
config/            configs por nodo (A.json..H.json) + topology.json
src/
  node.py          bootstrap de un nodo                    
  transport.py     TCP asyncio, framing NDJSON              
  envelope.py      parse/serialize/validate/make de paquete 
  config.py        loader de config/<NODO>.json             
  neighbors.py     tabla de vecinos + liveness              
  healthcheck.py   hello/echo periódico                     
  dedup.py         cache de paquetes vistos                 
  router.py        interfaz Router (Protocol)                
  forwarding.py    dispatch de paquetes por type            
  flooding.py      flood() + FloodingRouter                 
  dijkstra.py      compute() + DijkstraRouter                
  lsr.py           LSRRouter (LSDB + reflood + dijkstra)     
  harness/run_all.py   levanta los 8 nodos y prueba A->G      
tests/             un archivo de tests por módulo/persona
```

## Setup

Con `make` (Linux/Mac, o Windows con Git Bash/WSL/`make` instalado):

```bash
make venv
make run NODE=A
make run-all
make test
```

Sin `make` (por ejemplo PowerShell en Windows), los comandos equivalentes:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

.venv\Scripts\python -m src.node --config config/A.json
.venv\Scripts\python -m src.harness.run_all
.venv\Scripts\python -m pytest tests/
```

### Nota de wiring: Forwarder <-> HealthCheck

La firma congelada de `Forwarder.__init__` no recibe un `HealthCheck`, pero
`forwarding.py` debe delegarle los paquetes `hello`/`echo`. Convención usada
en `node.py`: después de construir ambos objetos, se hace

```python
forwarder.healthcheck = healthcheck
```

y `Forwarder.handle()` debe usar `self.healthcheck.handle_hello(...)` /
`self.healthcheck.handle_echo(...)` cuando `pkt["type"]` sea `hello`/`echo`.

## Topología de placeholder

`config/topology.json` trae una topología de prueba (8 nodos, pesos
arbitrarios) para poder correr `dijkstra`/`lsr` desde ya. El día de la
prueba en clase, solo se reemplaza ese archivo por la topología real —
nada más debería cambiar.

## Puertos

| Nodo | Puerto |
|------|--------|
| A    | 5001   |
| B    | 5002   |
| C    | 5003   |
| D    | 5004   |
| E    | 5005   |
| F    | 5006   |
| G    | 5007   |
| H    | 5008   |

Todos escuchan en `0.0.0.0`; los vecinos se conectan por `127.0.0.1` (todo
corre local en la misma máquina).

## Especificación de referencia (interop entre grupos)

[docs/reference-spec-v1.md](docs/reference-spec-v1.md) es el contrato de
formato de paquete que otros grupos del curso están usando para la prueba
conjunta. `envelope.py`, `config.py` y `node.py` ya están alineados a esta
versión:

- Todo paquete lleva `version` (default `1`), `id`, `proto`, `type`, `from`,
  `to`, `ttl`, `headers` (default `[]`), `payload`.
- `proto` solo puede ser `dijkstra` | `flooding` | `lsr` (= el `mode` activo
  del nodo emisor, no un nombre de protocolo inventado).
- `type` solo puede ser `hello` | `echo` | `message` | `info`.
- `to: "*"` es la convención de broadcast lógico para LSPs (`info`).
- `topology_file` en `config/<NODO>.json` es opcional, solo obligatorio si
  `mode == "dijkstra"`.