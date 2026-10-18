# ADR-005: Idempotencia de marcaciones y resolución de `is_inside`

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

La especificación proponía un `local_id` del estilo `tmp_001` para el lote de marcaciones. Eso no sobrevive a un reintento: el mismo acceso se insertaría dos veces y podría voltear `is_inside` otra vez. Además, un lote atrasado (el nodo estuvo sin red) puede llegar después de un evento más nuevo del mismo empleado.

## Decisión

El agente genera un UUID y la nube lo usa como clave primaria de `AccessLog`. `POST /api/v1/edge/logs/batch/` inserta cada fila en un savepoint. Si la clave ya existe, la fila va a `duplicated` y no se vuelve a aplicar la presencia.

Solo un acceso `GRANTED` con empleado de la misma organización mueve `Employee.is_inside`. `IN` significa dentro y `OUT` significa fuera. Gana el mayor `timestamp`. El instante de esa decisión queda en `Employee.last_presence_at`. Un evento más viejo se conserva como historial y no revierte el estado. Si dos eventos traen el mismo timestamp, gana el que aparece más tarde en el lote.

Un `employee_id` desconocido o de otra organización se guarda como nulo: la marcación ocurrió, pero no se cruza el límite del tenant. Una puerta que no es del nodo sí rechaza la fila, porque no hay forma honesta de atribuirla.

`denial_reason = APB_VIOLATION` crea `AccessAnomaly(kind=APB_REPORTED)`. El modelo queda listo para la reconciliación de la Fase 5; esta fase solo registra lo que el nodo ya decidió. El APB blando puede venir como `GRANTED` con ese motivo: en ese caso sí se actualiza la presencia. El APB duro viene como `DENIED` y no la mueve.

Cada marcación nueva emite `access_log_created` después del commit. Un duplicado no la emite.

## Consecuencias

- Reenviar un lote deja la base igual.
- Actualizar `is_inside` también sube `version` del empleado, así que el delta se vuelve ruidoso. ADR-003 ya acepta ese costo.
- El agente no debe tratar el `is_inside` del delta como más fresco que su estado local.
