# Latencia de validación del agente

La medición que pide la fase es el percentil 95 desde que llega `hardware_read` (o el comando `identification`) hasta que el agente decide y envía `open_door`. No incluye el pulso del relé: el gateway espera unos 300 ms por defecto antes de `door_opened`, y ese tiempo no cuenta para el presupuesto de 200 ms.

## Qué está medido

`TestValidationP95StaysUnderBudget` corre 200 decisiones seguidas contra SQLite en la máquina de desarrollo y falla si el p95 pasa de 200 ms. En la corrida de esta sesión el umbral se cumplió con margen (la decisión es una consulta indexada y un insert).

Esa prueba no sustituye la medición en el hardware objetivo.

## Qué falta

| Medición | Estado |
| --- | --- |
| p50 / p95 / p99 en el puesto de desarrollo, prueba automática | hecha, tope 200 ms |
| p50 / p95 / p99 en Raspberry Pi 4 u otro puesto objetivo | pendiente: no hay equipo en este entorno |
| Un lector RFID y un relé LCUS-1 con el gateway real | pendiente (P17). El simulador cubre el mismo contrato WebSocket |

Cuando haya un puesto, el procedimiento es: agente con el simulador reemplazado por el gateway real, 1 000 lecturas, y anotar aquí los tres percentiles que expone `edge_validation_seconds` en `http://127.0.0.1:9090/metrics`.
