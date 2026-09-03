# Especificación de Referencia v1

Fecha de referencia: 2026-09-01

Este documento define la implementación de referencia que usaremos para
alinear a todos los grupos del laboratorio 3.

La intención no es dejar decisiones abiertas, sino fijar un contrato común
que todos puedan implementar de la misma forma.

Si algún grupo ya tiene una variante distinta, debe ajustarse a esta
especificación o declarar explícitamente una versión distinta antes de la
prueba.

## 1. Alcance

Esta especificación cubre:
- Transporte TCP y framing.
- Formato exacto de los paquetes.
- Semántica de `from`, `to`, `ttl`, `headers` y `payload`.
- Mensajes `hello`, `echo`, `message` e `info`.
- Flooding, Dijkstra y LSR.
- Health-check de vecinos.
- Dedupe de paquetes.
- Reglas de arranque, forwarding y actualización de rutas.

Esta especificación no intenta redefinir el laboratorio. Solo fija una
implementación interoperable de referencia para el grupo.

## 2. Principios de interoperabilidad

Para que dos implementaciones sean compatibles, deben coincidir en:
- Estructura del paquete.
- Tipos permitidos.
- Semántica de `from` y `to`.
- Convención `to: "*"`.
- Regla de TTL.
- Regla de deduplicación.
- Forma del `payload` por tipo.
- Reglas de reenvío.

Campos adicionales solo se permiten si no rompen el parseo del envelope base.

## 3. Transporte y framing

### 3.1 Transporte
- Se usa TCP.
- Cada nodo mantiene conexiones persistentes con sus vecinos configurados.
- Una conexión puede transportar múltiples paquetes.

### 3.2 Framing
- Cada paquete se serializa como una sola línea JSON compacta.
- Cada línea termina en `\n`.
- No se usa pretty-print.
- No se permiten saltos de línea dentro del JSON serializado.

### 3.3 Manejo de errores
- Un paquete con JSON inválido se descarta.
- Un paquete con campos inválidos se descarta.
- Un paquete inválido no debe tumbar el nodo.
- Un paquete inválido no debe obligar a cerrar toda la conexión.

## 4. Envelope canónico

Todo paquete debe tener esta forma lógica:

```json
{
  "version": 1,
  "id": "uuid-unico",
  "proto": "<modo-activo>",
  "type": "hello",
  "from": "A",
  "to": "B",
  "ttl": 5,
  "headers": [],
  "payload": {}
}
```

### 4.1 Campos obligatorios
- `id`
- `proto`
- `type`
- `from`
- `to`
- `ttl`
- `payload`

### 4.2 Campos opcionales
- `version`
- `headers`

### 4.3 Valores por defecto
- `version`: `1`
- `headers`: `[]`

### 4.4 Tipos permitidos
- `proto`: `dijkstra`, `flooding`, `lsr`
- `type`: `hello`, `echo`, `message`, `info`

### 4.5 Reglas de envelope
- `id` debe ser único por paquete originado.
- `id` no cambia al reenviar.
- `ttl` debe ser entero.
- `ttl` se decrementa en cada salto.
- Si un paquete llega con `ttl <= 0`, se descarta.
- `headers` debe ser una lista.
- `payload` cambia según `type`.

## 5. Semántica exacta de `from` y `to`

### 5.1 `from`
- `from` representa al emisor inmediato del salto actual.
- Cuando un nodo reenvía un paquete, actualiza `from` a su propio `node_id`.
- `from` no representa necesariamente el origen absoluto del mensaje.

### 5.2 `to`
- `to` representa el destino final del paquete.
- `to` es un string opaco.
- En esta implementación de referencia usamos IDs lógicos en las pruebas
  locales, pero el mismo campo puede mapearse a IP:puerto en el entorno del
  laboratorio mediante la configuración de vecinos.
- Para broadcast lógico de LSPs se usa `to: "*"` como convención cerrada.

### 5.3 Consecuencia operativa
- El receptor usa `from` para identificar al vecino inmediato que le entregó
  el paquete.
- El origen absoluto de un LSP va en `payload.origin`.
- La traza de un mensaje de usuario puede registrarse en `headers[].hops`.

## 6. Tipos de paquete

## 6.1 `hello`

Propósito:
- Descubrimiento de vecinos.
- Health-check.
- Medición de RTT.

Forma canónica:

Nota:
- En los ejemplos, `proto` representa el modo activo del nodo emisor.
- El valor real debe ser uno de `dijkstra`, `flooding` o `lsr`.

```json
{
  "version": 1,
  "id": "uuid",
  "proto": "<modo-activo>",
  "type": "hello",
  "from": "A",
  "to": "B",
  "ttl": 1,
  "headers": [],
  "payload": {
    "seq": 42,
    "sent_at": 1756500000.123
  }
}
```

Reglas:
- `ttl` debe ser `1`.
- No se reenvía.
- Se envía solo al vecino directo.
- `proto` debe ser el modo activo del nodo emisor.
- `seq` debe ser monotónico por vecino destino.
- `sent_at` debe ser el timestamp de envío.

## 6.2 `echo`

Propósito:
- Responder al `hello`.
- Confirmar recepción.
- Alimentar el health-check.

Forma canónica:

```json
{
  "version": 1,
  "id": "uuid",
  "proto": "<modo-activo>",
  "type": "echo",
  "from": "B",
  "to": "A",
  "ttl": 1,
  "headers": [],
  "payload": {
    "seq": 42,
    "sent_at": 1756500000.123,
    "echoed_at": 1756500000.126
  }
}
```

Reglas:
- Debe copiar `seq` del `hello` original.
- Debe copiar `sent_at` del `hello` original.
- Debe agregar `echoed_at`.
- `ttl` debe ser `1`.
- No se reenvía.
- `proto` debe ser el modo activo del nodo emisor.

## 6.3 `message`

Propósito:
- Transportar mensajes de usuario.

Forma canónica:

```json
{
  "version": 1,
  "id": "uuid",
  "proto": "<modo-activo>",
  "type": "message",
  "from": "A",
  "to": "D",
  "ttl": 5,
  "headers": [
    { "hops": ["A"] }
  ],
  "payload": "Hola, este es un mensaje de prueba"
}
```

Reglas:
- `payload` debe ser texto plano.
- `payload` no debe ser un objeto anidado.
- Si el receptor coincide con `to`, el mensaje se entrega localmente.
- Si el receptor no coincide con `to`, el mensaje se reenvía según el modo.
- Si `headers[].hops` existe, se agrega el nodo que reenvía.
- Si no existe, se crea.

## 6.4 `info`

Propósito:
- Transportar LSPs.
- Difundir estado de enlaces.
- Reconstruir topología en LSR.

Forma canónica:

```json
{
  "version": 1,
  "id": "uuid",
  "proto": "<modo-activo>",
  "type": "info",
  "from": "A",
  "to": "*",
  "ttl": 5,
  "headers": [],
  "payload": {
    "origin": "A",
    "seq": 7,
    "neighbors": {
      "B": 4,
      "C": 1
    }
  }
}
```

Reglas:
- `payload.origin` es el nodo que origina el LSP.
- `payload.origin` no cambia al reenviar.
- `payload.seq` es monotónico por `origin`.
- Un `info` con `seq` menor o igual al último visto para ese `origin` se
  descarta sin aplicar ni reenviar.
- `payload.neighbors` debe contener solo vecinos activos al momento de originar
  el LSP.
- `to` debe ser `"*"`.

## 7. TTL

- Todo paquete debe incluir `ttl`.
- `ttl` se decrementa en cada salto de reenvío.
- `ttl` evita loops residuales si falla otra protección.
- Un paquete con `ttl <= 0` se descarta al recibirlo.

## 8. Deduplicación

- Cada nodo mantiene una caché de `id` ya vistos.
- La deduplicación aplica a `message` en flooding y a `info`/LSP.
- Si un `id` ya fue visto, el paquete se descarta sin reprocesar ni reenviar.
- Las entradas expiran por tiempo configurable.
- La deduplicación y TTL se usan juntos; no se sustituye una por la otra.

## 9. Estado de vecinos

Cada nodo debe mantener, al menos, esta información por vecino:
- `node_id`
- `host`
- `port`
- `cost`
- `is_up`
- `consecutive_failures`
- `last_rtt_sec`

Reglas:
- Los vecinos configurados inician como `is_up = true`.
- `consecutive_failures` aumenta por cada timeout no resuelto.
- `consecutive_failures` se reinicia al recibir un `echo` válido.
- `last_rtt_sec` se actualiza solo con un `echo` válido.
- Un vecino caído no debe participar como next-hop.
- En LSR, un vecino caído no debe aparecer en el LSP propio.

## 10. Health-check

El health-check usa `hello` y `echo` para verificar disponibilidad.

Reglas cerradas:
- Cada nodo debe enviar `hello` periódicamente a todos sus vecinos
  configurados.
- Debe enviar `hello` incluso a vecinos marcados como caídos, para detectar
  recuperación.
- Cada vecino debe tener su propio contador de `seq`.
- Cada `hello` debe llevar `sent_at`.
- Cada `echo` debe responder con el mismo `seq` y `sent_at`.
- El receptor de `echo` calcula RTT como `now - sent_at`.
- El RTT es solo informativo; no modifica automáticamente el costo del enlace.
- Un `echo` viejo o fuera de contexto se ignora.
- Si un vecino supera el umbral de fallos consecutivos, se marca como caído.
- Si un vecino caído responde con `echo` válido, se marca como recuperado.
- Un cambio de estado debe notificar al routing para que en LSR se reanime el
  LSP propio.

## 11. Reglas por modo

## 11.1 `dijkstra`
- La topología es estática.
- Se carga desde configuración.
- La tabla de ruteo se calcula una sola vez al arrancar.
- El forwarding usa next-hop precomputado.

## 11.2 `flooding`
- El nodo solo conoce sus vecinos directos.
- No existe tabla global de ruteo.
- Un paquete se reenvía a todos los vecinos activos excepto al vecino que lo
  envió.
- Se usa TTL y dedupe.

## 11.3 `lsr`
- La topología se reconstruye a partir de los LSP recibidos.
- Los LSP se difunden por flooding.
- Los mensajes de usuario se enrutan con Dijkstra sobre la topología
  reconstruida.
- Ante cambio de estado de vecinos, el nodo debe reanunciar su LSP propio.

## 12. Semántica de forwarding

### 12.1 Mensajes de usuario
- Si el nodo es destino, entrega localmente.
- Si no es destino, consulta next-hop.
- Si no hay ruta, descarta.
- Antes de reenviar, decrementa TTL.
- Antes de reenviar, actualiza `from` al nodo que reenvía.
- Antes de reenviar, agrega el salto a `headers[].hops` si se usa traza.

### 12.2 Flooding
- Un paquete recibido no debe reenviarse hacia el vecino que lo envió.
- Si el paquete es broadcast, puede entregarse localmente y seguir
  difundiendo su copia.
- Si el paquete está dirigido al nodo, se entrega localmente y no se sigue
  reenviando esa copia.

### 12.3 LSP
- Un LSP nuevo se aplica a la LSDB local.
- Si el LSP es nuevo, se reflood-ea.
- Si el LSP es viejo o repetido, no se reenvía.

## 13. Reglas de ruta y topología

### 13.1 Dijkstra
- Requiere topología completa.
- Calcula rutas mínimas por costo.
- La tabla resultante debe exponer `destination`, `next_hop` y `cost`.

### 13.2 LSR
- La LSDB debe reconstruir el grafo con los LSP conocidos.
- Cada `origin` aporta sus vecinos activos y costos.
- La ruta óptima debe recalcularse cuando cambie la LSDB.

### 13.3 Flooding
- No depende de una topología global.
- Solo usa vecinos activos configurados.

## 14. Reglas de arranque

- Cada nodo arranca con su archivo de configuración.
- Cada nodo conoce solo a sus vecinos directos al inicio.
- En `dijkstra`, la topología completa debe estar disponible.
- En `flooding`, no se requiere topología global.
- En `lsr`, cada nodo debe anunciar su LSP propio al iniciar.

## 15. Estructura de configuración

### 15.1 Configuración de nodo
Cada nodo debe tener:
- `node_id`
- `listen.host`
- `listen.port`
- `mode`
- `neighbors`
- `params`
- `topology_file` solo si el modo es `dijkstra`

### 15.2 Vecinos
Cada vecino debe declarar:
- `node_id`
- `host`
- `port`
- `cost`

### 15.3 Parámetros mínimos
Los parámetros configurables recomendados son:
- `initial_ttl`
- `hello_interval_sec`
- `hello_timeout_sec`
- `hello_max_failures`
- `dedup_cache_ttl_sec`
- `log_level`

## 16. Parámetros negociables

Estos parámetros pueden variar entre implementaciones locales, pero para una
red conjunta deben acordarse y usar los mismos valores en todos los nodos:
- Frecuencia de `hello`.
- Timeout de `hello`.
- Umbral de fallos antes de marcar un vecino como caído.
- TTL inicial.
- Tiempo de expiración de la caché de dedupe.
- Nivel de logging.

La interoperabilidad de formato no depende de estos valores, pero la
convergencia y la detección de caída/recuperación sí dependen de que la red
conjunta comparta los mismos umbrales.

## 17. Decisiones cerradas de esta referencia

Estas decisiones quedan fijadas para esta implementación de referencia:
- `from` significa emisor inmediato del salto actual.
- `to: "*"` se usa para broadcast lógico de LSPs.
- `message.payload` es texto plano.
- `info.payload.origin` identifica el origen real del LSP.
- `headers[].hops` se usa como traza opcional.
- TTL y dedupe se aplican siempre.
- `hello` y `echo` usan `seq`, `sent_at` y `echoed_at`.
- Los LSP se reenvían por flooding solo si son nuevos.
- Los mensajes de usuario se entregan o reenvían según el modo.

## 18. Qué debe implementar exactamente otro grupo si quiere alinearse

Si otro grupo quiere usar esta referencia, debe implementar:

1. Framing NDJSON por TCP.
2. Paquete con `version`, `id`, `proto`, `type`, `from`, `to`, `ttl`,
   `headers`, `payload`.
3. Tipos `hello`, `echo`, `message`, `info`.
4. Semántica de `from` como emisor inmediato.
5. Broadcast LSP con `to: "*"`.
6. Mensajes de usuario como string en `payload`.
7. `hello`/`echo` con `seq` y timestamps.
8. Dedupe por `id`.
9. TTL obligatorio.
10. Flooding sin loops.
11. LSR con LSP + Dijkstra.
12. Health-check de vecinos con caída y recuperación.

## 19. Compatibilidad entre grupos

Para evitar problemas en la prueba conjunta, todos los grupos deben confirmar
estos puntos antes de conectar sus nodos:
- Si usarán IDs lógicos o IP:puerto en `from` y `to`.
- Si aceptarán `to: "*"`.
- Si usarán `message.payload` como string plano.
- Si usarán `info.payload.neighbors` como mapa vecino -> costo.
- Si usarán `hello`/`echo` con `seq` y timestamps.
- Si usarán la misma semántica de `from`.
- Si usarán la misma política de dedupe y TTL.

## 20. Versionado

- Esta especificación corresponde a la versión `v1`.
- Cualquier cambio incompatible debe documentarse como nueva versión.
- No se deben introducir cambios silenciosos.
