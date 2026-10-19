# ADR-006: Aforo y reconciliación de anti-passback entre nodos

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

`Employee.is_inside` ya lo define el lote de marcaciones: gana el mayor `timestamp` (ADR-005). Eso no dice en qué sede o zona está la persona, ni qué hacer cuando dos nodos estuvieron offline y reportan estados que no encajan. El panel necesita ese conteo en vivo, y un operador tiene que poder corregirlo sin borrar el historial.

Los grupos de Django Channels no aceptan `:` en el nombre. El plan hablaba de `org:<id>`.

## Decisión

La presencia guardada tiene cuatro datos: `is_inside`, `last_presence_at`, `presence_node` y `presence_zone`. Un acceso concedido `IN` deja al empleado en el nodo y en la zona de esa puerta. Un `OUT` lo deja fuera y sin zona; el nodo queda como la sede de esa salida. El aforo es la cuenta de `is_inside` agrupada por esos dos campos. `GET /api/v1/occupancy/` lo devuelve por sede y por zona.

Si llega una marcación más vieja desde **otro** nodo y su dirección contradice el estado ya guardado, no se revierte la presencia y se crea `AccessAnomaly(kind=APB_CONFLICT)`. El detalle dice que se conservó la más reciente. Si el timestamp empata, gana la que llega después y la anomalía lo registra como `arrival_order`. Una marcación atrasada del mismo nodo no es un conflicto entre sedes: se archiva y no mueve el estado, igual que en ADR-005.

`POST /api/v1/occupancy/reset/` (operador o administrador) pone fuera a un empleado o a quienes están dentro de un nodo. Anota `presence_reset_at` y un `AccessAnomaly(kind=STATE_RESET)`. Las marcaciones anteriores a ese instante siguen en el historial y no vuelven a definir la presencia. Una marcación posterior sí.

Cada noche, a las 03:20 UTC, una tarea recorre las marcaciones concedidas (posteriores al reset, si lo hubo) y corrige el estado si no coincide. Cada corrección es `AccessAnomaly(kind=OCCUPANCY_DRIFT)`.

El tablero y el kiosco escuchan por WebSocket. El primer mensaje es `auth`: el tablero usa el JWT (hace falta `org_id`) y el kiosco su token. Los grupos reales son `org.<id>`, `org.<id>.node.<id>` y `org.<id>.door.<id>`. Todo evento de la organización se publica en el grupo de la organización; el de una puerta, también en el de esa puerta. El kiosco solo entra al grupo de su puerta. Un token de otra organización no recibe el evento.

Al persistir una marcación se publican `access.granted` o `access.denied`. Si cambió la presencia, `occupancy.changed` con el aforo completo. El latido publica `node.online` y `node.offline`. El enrolamiento asistido publica `enrollment.read` y la confirmación de un comando, `command.acked`.

## Consecuencias

- El aforo puede ir un evento por detrás si el lote todavía no se confirmó. Después del commit, el tablero lo recibe por el socket y actualiza la caché.
- Reiniciar el aforo no borra marcaciones. El recálculo nocturno respeta el reset.
- `presence_node` y `presence_zone` no viajan en el delta hacia el agente. El agente sigue con su estado local.
- La Fase 6 puede publicar `face.result` en el grupo de la puerta sin cambiar este canal.
