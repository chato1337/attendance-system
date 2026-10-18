# ADR-010: Canal de comandos nube → agente

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

El protocolo original es solo pull: el agente pide deltas y empuja lotes. La identificación facial, la apertura remota y el enrolamiento asistido necesitan que la nube le hable al agente sin esperar al siguiente ciclo de sync. El agente puede estar detrás de una red que corta WebSocket.

## Decisión

Cada orden se persiste como `EdgeCommand` antes de intentar entregarla. El estado recorre `PENDING`, `SENT` y después `ACKED` o `FAILED`. Si vence `expires_at` sin confirmación, pasa a `EXPIRED` y no se reintenta.

Plazos iniciales: `identification` 10 s, `open_door` 30 s, `sync_now` y `reload` 60 s, `enrollment_mode` 120 s.

Hay dos transportes sobre el mismo almacén:

- WebSocket `ws/edge/`, autenticado con el primer mensaje `auth` y la API key del nodo. Al conectar se entregan los `PENDING` vigentes. Un comando nuevo se publica al grupo del nodo.
- Long-poll `GET /api/v1/edge/commands/?wait=25`, para redes que bloquean WebSocket. La espera máxima es 25 s para caber en el timeout de Gunicorn.

Quien entrega el comando lo pasa a `SENT`. El ack es idempotente: una segunda confirmación devuelve el resultado ya guardado y no lo pisa. Confirmar un comando vencido responde `409`.

`dispatch_command(node, type, payload, timeout)` crea la orden, la publica al confirmar la transacción y, si `timeout` es mayor que cero, espera el estado terminal. La Fase 6 lo usa para responder al kiosco. El panel puede pedir lo mismo con `wait` en `POST /api/v1/nodes/{id}/commands/`.

Los tipos de esta fase son `identification`, `open_door`, `sync_now`, `enrollment_mode` y `reload`. La puerta o el lector del payload tienen que pertenecer al nodo.

## Consecuencias

- Un agente desconectado no acumula reintentos infinitos: el comando expira una vez.
- La entrega antes de expirar puede repetirse si el long-poll y el socket coinciden. El agente debe ignorar un `id` que ya esté ejecutando, y el ack lo resuelve.
- El worker HTTP que atiende el long-poll queda ocupado hasta 25 s. El WebSocket vive en el servicio Channels, no en Gunicorn.
