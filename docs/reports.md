# Reportes de asistencia

Definiciones del motor de cálculo (`apps.reports.engine`). Los reportes y las
exportaciones leen únicamente `DailyAttendance`; nunca recalculan sobre la marcha
salvo que el operador pulse «Calcular período» o se dispare la tarea nocturna.

## Entradas

| Entrada | Uso |
| --- | --- |
| `AccessLog` con `status=GRANTED` | Únicas marcaciones que cuentan. Las denegadas se ignoran. |
| `Schedule` + `Shift` | Horario esperado. El horario del empleado tiene prioridad sobre el del departamento. Si dos horarios cubren el mismo día ISO, gana el de `updated_at` más reciente. |
| `Holiday` | Día festivo de la organización. |
| Zona horaria de la `Organization` | El día laboral y las horas esperadas se interpretan en esa zona. |

Los turnos son del mismo día civil (`end_time > start_time`). No hay turnos que crucen la medianoche en esta versión.

## Emparejamiento IN/OUT

En cada día local del empleado:

1. Se ordenan las marcaciones concedidas por `timestamp`.
2. Un `IN` abre un intervalo; el siguiente `OUT` lo cierra y suma minutos.
3. Un `IN` sin `OUT` al final del día deja `orphan_in=true` y estado `INCOMPLETE`.
4. Un `OUT` sin `IN` abierto se ignora para la permanencia.
5. `first_in` es el primer `IN` del día; `last_out` es el último `OUT` que cerró un intervalo.
6. `worked_minutes` es la suma de intervalos cerrados, truncada a minutos enteros.

## Estados (`DailyAttendance.status`)

| Estado | Condición |
| --- | --- |
| `HOLIDAY` | Día festivo con horario asignado y sin marcaciones. |
| `ABSENT` | Día laborable con horario, sin marcaciones. |
| `INCOMPLETE` | Hay marcaciones y queda un `IN` abierto (marca huérfana). |
| `LATE` | Día cerrado con `late_minutes > 0` (tiene prioridad sobre salida anticipada). |
| `EARLY_LEAVE` | Día cerrado, a tiempo a la entrada, con `early_leave_minutes > 0`. |
| `PRESENT` | Día cerrado, dentro de tolerancias. |

Si el empleado no tiene horario ese día y tampoco marcaciones, no se escribe fila.

Un día festivo con marcaciones se trata como día trabajado (no como `HOLIDAY`): aplica tardanza/salida anticipada si hay turno.

## Tolerancias

- **Tardanza:** minutos entre la hora de entrada esperada y `first_in`, menos `Shift.late_tolerance_minutes`. Si el resultado es ≤ 0, no hay tardanza.
- **Salida anticipada:** minutos entre `last_out` y la hora de salida esperada, menos `Shift.early_leave_tolerance_minutes`.

Las tolerancias por defecto del seed son 10 minutos.

## Métricas del resumen

| Métrica | Definición |
| --- | --- |
| Días esperados | Filas con `scheduled=true` e `is_holiday=false`. |
| Días presentes | Filas en `PRESENT`, `LATE` o `EARLY_LEAVE`. |
| Tardanzas / salidas anticipadas | Conteo de filas con `late_minutes > 0` o `early_leave_minutes > 0`. |
| Ausentismo | `absent_days / expected_days` (null si no hay días esperados). |
| Puntualidad | Entre llegadas con horario (`first_in` no nulo, programado, no festivo): proporción con `late_minutes = 0`. |

## Recalculo y exportación

- Tarea Celery diaria `rebuild_daily_attendance`: recalcula ayer y hoy por organización.
- `POST /api/v1/reports/recalculate/` recalcula un rango bajo demanda (roles ADMIN/OPERATOR).
- Las exportaciones (CSV, XLSX, PDF, JSON) corren en Celery, recalculan el rango filtrado y entregan un enlace firmado con TTL (`EXPORT_LINK_TTL_SECONDS`, 24 h por defecto).
- El PDF resume el período y detalla hasta 1 500 filas; el archivo completo está en CSV/XLSX/JSON.

## Particionado de `AccessLog`

Los índices `(employee, timestamp)` y `(node, timestamp)` cubren el cálculo actual.
El particionado mensual de `AccessLog` se evalúa cuando el volumen de un cliente
lo justifique (pregunta abierta P10); no es requisito de esta fase.
