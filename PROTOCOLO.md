# Protocolo de la red — Laboratorio 3

Especificación del formato en el cable para nodos de enrutamiento
interoperables. Define cómo un nodo descubre a sus vecinos, mide el enlace que
los une, difunde el estado de sus enlaces y entrega mensajes de usuario.

Cualquier implementación que respete este documento puede intercambiar tráfico
con otra, sin importar el lenguaje en que esté escrita.

## Alcance por algoritmo

El formato del paquete es **el mismo para los tres algoritmos**. Lo que cambia es
el valor de `proto` y qué se hace con cada tipo de paquete:

| | `flooding` | `dijkstra` | `lsr` |
|---|---|---|---|
| `hello` / `echo` | sí | sí | sí |
| `info` (LSP) | no se origina | no se origina | sí |
| `message` | se propaga a todos los vecinos | unicast por tabla | unicast por tabla |

Todos los nodos de una misma red deben correr el mismo algoritmo.

## Transporte

- TCP, codificación UTF-8.
- **Un objeto JSON por línea**, terminado en `\n` (NDJSON/JSONL). El receptor
  acumula bytes hasta el delimitador y procesa cada línea por separado.
- Puerto por defecto **5000**, tomado de configuración y nunca fijado en el
  código.
- **Máximo 65536 bytes por línea.** Una línea mayor se descarta y se registra.
- Una implementación puede abrir una conexión TCP por envío o mantener una por
  vecino; ambas cumplen la especificación.

> **Recomendación.** Conviene leer también de las conexiones salientes, no solo
> de las entrantes: algunas implementaciones responden por el mismo socket que
> recibieron, en vez de abrir una conexión nueva hacia la dirección de `from`.
> Soportar las dos formas evita perder respuestas en silencio.

## Envelope común

```json
{
  "version": 1,
  "proto": "lsr",
  "type": "message",
  "from": "10.0.0.1:5000",
  "to": "10.0.0.7:5000",
  "ttl": 16,
  "headers": [{"msg_id": "uuid-v4"}, {"checksum": "crc32-hex"}],
  "payload": "hola G"
}
```

Los ocho campos son obligatorios.

| Campo | Valor |
|---|---|
| `version` | entero; actualmente `1` |
| `proto` | `"lsr"`, `"dijkstra"` o `"flooding"` — el algoritmo que corre la red |
| `type` | `hello`, `echo`, `info` o `message`, **siempre en minúscula** |
| `from` | `IP:puerto` del originador (no del salto anterior) |
| `to` | destino final en `message`; vecino directo en `hello`/`echo`; **`"*"`** en un LSP inundado |
| `ttl` | entero positivo, inicial **16**; cada reenvío lo decrementa; a `0` se descarta |
| `headers` | lista de objetos de una sola clave; los desconocidos se ignoran |
| `payload` | **string** en `message`; **objeto** en `hello`, `echo` e `info` |

Una dirección sin puerto se completa con el puerto configurado de la red, de
modo que `"10.0.0.7"` y `"10.0.0.7:5000"` designan al mismo nodo cuando el
puerto común es 5000.

### Headers

| Header | Aplica a | Uso |
|---|---|---|
| `msg_id` | todos | UUID del paquete lógico; se conserva al reenviar |
| `checksum` | todos | CRC32 del `payload` |
| `t0` | `hello`, `echo` | marca de tiempo para calcular el RTT |
| `via` | `info`, `message` | dirección del salto anterior; cambia en cada reenvío |
| `trace` | `message` | direcciones ya recorridas; se agrega el nodo al reenviar |

`msg_id` y `checksum` son obligatorios. `via` y `trace` los debe escribir todo
nodo que reenvíe, pero un receptor debe aceptar paquetes que no los traigan.

### Checksum

`checksum` es el CRC32 de la **serialización canónica** del `payload`, definida
así:

- si el payload es **texto**, se toma el texto crudo en UTF-8, **sin comillas**;
- si es **objeto o lista**, se serializa como JSON con **claves ordenadas
  alfabéticamente**, separadores compactos (`,` y `:`) y sin escapar los
  caracteres no ASCII;
- el resultado se expresa en **hexadecimal, 8 dígitos, minúsculas**.

Ordenar las claves es lo que permite que dos nodos que construyan el mismo
payload en distinto orden obtengan el mismo valor.

**Vectores de prueba.** Una implementación correcta reproduce estos dos:

| Payload | Checksum |
|---|---|
| `"hola G"` | `0bded535` |
| `{"origin":"10.0.0.1:5000","seq":7,"neighbors":[{"id":"10.0.0.2:5000","weight":4.8}]}` | `cbd08356` |

> **Un checksum que no coincide se registra, pero no descarta el paquete.** El
> campo debe viajar siempre; descartar por una discrepancia haría que dos
> implementaciones con interpretaciones distintas de la serialización quedaran
> incomunicadas, en vez de degradarse a un aviso en el log.

De la misma forma, un `version` ausente o distinto de `1` no debe usarse para
rechazar un paquete: se registra y se procesa.

## Tipos de paquete

### `hello` y `echo`

Se envían solo a vecinos directos, con `ttl: 1`. **Nunca se reenvían.**

```json
{"version":1,"proto":"lsr","type":"hello","from":"10.0.0.1:5000","to":"10.0.0.2:5000",
 "ttl":1,"headers":[{"msg_id":"..."},{"t0":1770000000.125},{"checksum":"..."}],
 "payload":{"listen_port":5000}}
```

El `echo` **conserva el mismo `msg_id` y el mismo `t0`** e invierte `from` y
`to`. Quien envió el `hello` calcula `RTT = ahora - t0`.

Como el `t0` se devuelve sin modificar, el cálculo ocurre siempre contra un solo
reloj —el del emisor del `hello`— y no requiere que las máquinas estén
sincronizadas entre sí.

Un vecino se considera activo mientras se le siga oyendo. Al dejar de responder
durante el tiempo de espera configurado se marca como caído, lo que cambia el
estado del enlace y obliga a recalcular rutas.

### `info` (LSP)

```json
{"version":1,"proto":"lsr","type":"info","from":"10.0.0.1:5000","to":"*","ttl":16,
 "headers":[{"msg_id":"..."},{"checksum":"..."},{"via":"10.0.0.2:5000"}],
 "payload":{"origin":"10.0.0.1:5000","seq":7,"age_s":0,
            "neighbors":[{"id":"10.0.0.2:5000","weight":4.8}]}}
```

Campos del payload:

| Campo | Significado |
|---|---|
| `origin` | dirección del nodo que describe sus enlaces |
| `seq` | número de secuencia, creciente por cada origen |
| `age_s` | segundos transcurridos desde que se originó |
| `neighbors` | lista de objetos `{"id": dirección, "weight": costo}` |

Reglas de procesamiento:

1. La identidad lógica de un LSP es **`(origin, seq)`**, no el `msg_id`.
2. Se guarda y se reenvía **solo si `seq` es mayor** que el último aceptado para
   ese `origin`. Un `seq` igual o menor se descarta sin reenviar: es lo que
   corta la inundación.
3. Se reenvía a los vecinos activos **excepto** al indicado por `via` o al de la
   conexión por la que llegó.
4. Cada LSP registra su hora local de recepción.
5. Una entrada **expira a los 30 segundos** sin actualizarse; al expirar se
   elimina, se reconstruye la topología y se recalculan las rutas.
6. Cada nodo origina un LSP al iniciar, **cada 10 segundos**, y cada vez que
   cambia el estado o el costo de un vecino.

Con el conjunto de LSPs recibidos, cada nodo reconstruye la topología —cada LSP
aporta las aristas salientes de su origen— y calcula sus rutas con Dijkstra
desde sí mismo.

**Sobre el formato de `neighbors`:** se **emite** siempre como lista de objetos
`{id, weight}`. Al **recibir** se recomienda aceptar además las variantes
equivalentes que puedan producir otras implementaciones (un diccionario
`{dirección: costo}`, la clave `links` en lugar de `neighbors`, los nombres
`node`/`cost`, o el payload serializado como texto JSON). Emitir una sola forma
y aceptar varias mantiene el formato inequívoco sin volverse frágil.

### `message`

```json
{"version":1,"proto":"lsr","type":"message","from":"10.0.0.1:5000","to":"10.0.0.7:5000",
 "ttl":16,"headers":[{"msg_id":"..."},{"checksum":"..."},{"trace":["10.0.0.1:5000"]}],
 "payload":"Mensaje de prueba"}
```

- Si `to` es la dirección propia, el mensaje se entrega y **no** se reenvía.
- Si no, se decrementa el TTL, se actualizan `via` y `trace`, y se reenvía: al
  `next_hop` de la tabla en LSR y Dijkstra, o a todos los vecinos menos el
  remitente en flooding.
- Si no hay ruta o el TTL llega a `0`, se descarta y se registra localmente.

No existen tipos `ERROR` ni `ACK`: el conjunto de tipos se limita a los cuatro
definidos arriba.

En flooding, la detección de duplicados es obligatoria o un paquete circula
indefinidamente entre los ciclos de la topología. Se deduplica por `msg_id`; si
un paquete llega sin él, sirve un hash de `(from, to, type, payload)`. **El TTL
nunca debe entrar en ese identificador**, porque cambia en cada salto y haría
que cada copia pareciera un paquete nuevo.

## Extensión recomendada: reinicio de un nodo

Con la regla de aceptar un LSP solo si su `seq` es estrictamente mayor, un nodo
que se reinicia queda ignorado indefinidamente: vuelve a `seq = 1` y el resto de
la red conserva un número mucho más alto para ese origen, de modo que descarta
todos sus anuncios hasta que la entrada expire.

Para evitarlo se recomienda aceptar también un LSP cuyo `seq` esté muy por
debajo del conocido —por ejemplo, más de 16 unidades—, que es la señal
inequívoca de un contador reiniciado. Es un añadido a la regla, no una
relajación: un LSP viejo dentro del rango normal se sigue descartando.
