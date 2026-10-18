# Protocolo Edge v1

Contrato congelado entre la nube y el agente. Un cambio incompatible requiere un ADR nuevo. La fuente ejecutable es el OpenAPI (`/api/schema/`), etiqueta **Protocolo Edge**.

El simulador de referencia está en `edge/tools/simulator/simulator.py`.

## Autenticación

```http
Authorization: Bearer <node_api_key>
```

La llave se entrega una sola vez al crear o regenerar el nodo. La nube guarda solo su SHA-256. Una llave inválida, un nodo inactivo o una organización inactiva responden `401`. Cada petición aceptada actualiza `last_sync_at` y fija el tenant a la organización del nodo.

El JWT del panel no sirve en estos endpoints, y la API key del nodo no sirve en el panel.

Límite: 120 peticiones por minuto y por nodo. Un exceso responde `429`.

## Reloj

Las respuestas incluyen `server_time` en UTC con sufijo `Z`. El agente debe comparar ese instante con su reloj (Fase 3).

## Delta

`GET /api/v1/edge/sync/delta/?since_version={n}&limit={m}`

- `since_version` por defecto `0`. No puede ser negativo.
- `limit` por defecto 500, máximo 1000.
- Sin cambios: `200` con listas vacías. No se usa `304`.
- Incluye filas inactivas (`is_active: false`) para propagar bajas.
- Empleados, credenciales y perfiles son de la organización del nodo.
- Puertas y lectores son solo los del nodo. Mover una puerta a otro nodo no avisa al nodo anterior: ese nodo debe hacer un resync (`reload`, `since_version=0`).

```json
{
  "server_time": "2026-10-18T23:00:00Z",
  "current_version": 1058,
  "next_since_version": 500,
  "has_more": true,
  "employees": [],
  "credentials": [],
  "reader_profiles": [],
  "doors": [],
  "readers": []
}
```

El cliente guarda `next_since_version` y lo envía como `since_version` en la página siguiente. No salta a `current_version` mientras `has_more` sea verdadero. `current_version` es la versión más alta visible para ese nodo, no el último valor de la secuencia global: las versiones de otras organizaciones se intercalan y no se entregan.

Dentro de cada página, el orden de aplicación es: perfiles, empleados, credenciales, puertas, lectores.

`is_inside` viaja en el empleado como estado de la nube. El agente mantiene su propio estado local de anti-passback; el valor del delta no pisa una decisión local más reciente.

## Lote de marcaciones

`POST /api/v1/edge/logs/batch/`

```json
{
  "node_id": "opcional, debe coincidir con el nodo autenticado",
  "logs": [
    {
      "id": "uuid generado en el Edge",
      "employee_id": "uuid o null",
      "credential_id": "uuid o null",
      "door_id": "uuid o null",
      "timestamp": "2026-10-18T08:00:15Z",
      "direction": "IN",
      "status": "GRANTED",
      "denial_reason": "APB_VIOLATION",
      "method": "RFID",
      "source": "gateway"
    }
  ]
}
```

Máximo 500 marcaciones. El cuerpo inválido o un lote más grande responden `400`. Una fila inválida no rechaza el resto:

```json
{
  "server_time": "2026-10-18T23:00:00Z",
  "accepted": ["uuid"],
  "duplicated": ["uuid"],
  "rejected": [{"id": "uuid", "reason": "unknown_door"}]
}
```

Reglas:

- El `id` es la clave primaria. Reenviar el mismo lote no crea filas ni vuelve a aplicar presencia.
- Un `employee_id` o `credential_id` desconocido, o de otra organización, se guarda como nulo y la marcación se acepta.
- Un `door_id` que no pertenece al nodo rechaza esa fila (`unknown_door`).
- El timestamp debe ser consciente de zona horaria.
- Cada marcación aceptada emite la señal `access_log_created`.
- `denial_reason = APB_VIOLATION` registra un `AccessAnomaly` de tipo `APB_REPORTED`, tanto si el acceso fue denegado (APB duro) como si fue concedido (APB blando).

### Presencia (`is_inside`)

Solo un acceso `GRANTED` con empleado conocido mueve la presencia. `IN` deja al empleado dentro; `OUT` lo deja fuera. Gana el timestamp más nuevo. Un evento más viejo se archiva y no revierte el estado. Dos eventos con el mismo timestamp: gana el que llega después en el lote. Ver ADR-005.

Cambiar `is_inside` también sube `version` del empleado (ADR-003). El delta siguiente incluye ese empleado.

## Heartbeat

`POST /api/v1/edge/heartbeat/`

```json
{
  "agent_version": "0.1.0",
  "gateway_connected": true,
  "listening_devices": ["COM3"],
  "queue_size": 0,
  "last_version": 1058,
  "commands_connected": true,
  "gateway_version": "opcional"
}
```

Marca el nodo en línea y guarda el cursor reportado en `last_sync_version`. El primer latido tras estar fuera de línea emite `device.status_changed`. Si pasan 3 minutos sin latido, una tarea periódica lo marca fuera de línea y vuelve a emitir la señal.

## Comandos nube → agente

Todo comando se persiste antes de enviarse.

| Tipo | Caduca | Payload |
| --- | --- | --- |
| `identification` | 10 s | `door_id`, `type`, `payload`, `request_id` |
| `open_door` | 30 s | `door_id`, `reason`, `actor` |
| `sync_now` | 60 s | objeto, puede ir vacío |
| `enrollment_mode` | 120 s | `reader_id`, `seconds` (1–600) |
| `reload` | 60 s | objeto, puede ir vacío |

Estados: `PENDING` → `SENT` → `ACKED` o `FAILED`. Si vence el plazo en `PENDING` o `SENT`, pasa a `EXPIRED` y no se reintenta.

El panel (administrador u operador) despacha con `POST /api/v1/nodes/{id}/commands/`. `wait` (0–30 segundos, por defecto 0) espera el ack. La consulta es `GET` sobre la misma ruta y `GET /api/v1/nodes/{id}/commands/{command_id}/`.

### Long-poll

`GET /api/v1/edge/commands/?wait=25`

`wait` máximo 25 segundos. Devuelve los comandos `PENDING` no vencidos y los marca `SENT`. La entrega es al menos una vez antes de vencer; el ack es idempotente. Un segundo ack no cambia el resultado guardado. Confirmar un comando vencido responde `409`.

`POST /api/v1/edge/commands/{id}/ack/`

```json
{"result": {"status": "GRANTED", "door_opened": true, "log_id": "uuid"}}
```

`result.status` `FAILED` o `ERROR` deja el comando en `FAILED`. Cualquier otro valor lo deja en `ACKED`.

### WebSocket

`ws://<api>/ws/edge/` (en producción, `wss`). El primer mensaje es:

```json
{"op": "auth", "token": "<node_api_key>"}
```

La nube responde `auth_ok` y, enseguida, un mensaje `command` por cada pendiente. Después acepta:

```json
{"op": "ack", "id": "uuid", "result": {}}
{"op": "ping"}
```

Un comando creado con el socket abierto llega como `{"op": "command", ...}`. Nginx publica este camino en `/ws/` hacia el servicio Channels.

## Simulador

```bash
python edge/tools/simulator/simulator.py --base-url http://localhost:8000 --api-key <key> sync
python edge/tools/simulator/simulator.py --base-url http://localhost:8000 --api-key <key> heartbeat
python edge/tools/simulator/simulator.py --base-url http://localhost:8000 --api-key <key> listen --cycles 3
```

`sync` pagina el delta hasta ponerse al día. `listen` hace long-poll y confirma `open_door` e `identification`. Reintenta ante caída de red y ante `429`.
